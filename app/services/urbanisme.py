"""Cadastre and planning data from IGN API Carto (WGS84 GeoJSON)."""
import asyncio
import json
import logging
import math
import time
from typing import Any

import httpx

from ..config import settings
from .common import cached, cache_key

BASE_URL = "https://apicarto.ign.fr/api"
LOGGER = logging.getLogger("homecheck.urbanisme")
LOGGER.setLevel(logging.DEBUG)  # Temporary integration diagnostics requested for API Carto.
OAP_TYPES = {"18"}
PRESCRIPTION_LAYERS = ("prescription-surf", "prescription-lin", "prescription-pct")
SUP_LAYERS = ("assiette-sup-s", "assiette-sup-l", "assiette-sup-p")

def _point(point): return {"type": "Point", "coordinates": [point["lon"], point["lat"]]}

def _buffer(point, metres=250, vertices=32):
    lat, lon = point["lat"], point["lon"]
    dy, dx = metres / 111_320, metres / (111_320 * max(math.cos(math.radians(lat)), .01))
    ring = [[lon + dx*math.cos(2*math.pi*i/vertices), lat + dy*math.sin(2*math.pi*i/vertices)] for i in range(vertices)]
    ring.append(ring[0])
    return {"type":"Polygon", "coordinates":[ring]}

def _pick(props, *names, default=None):
    for name in names:
        value=props.get(name)
        if value not in (None, ""): return value
    return default

async def _query(client, path, geom, errors):
    url=f"{BASE_URL}/{path}"; started=time.perf_counter()
    try:
        response=await client.get(url,params={"geom":json.dumps(geom,separators=(",",":"))})
        elapsed=(time.perf_counter()-started)*1000; response.raise_for_status()
        features=response.json().get("features",[]); first=features[0].get("properties",{}) if features else {}
        LOGGER.debug("url=%s status=%s elapsed_ms=%.0f features=%d first_properties=%s",response.request.url,response.status_code,elapsed,len(features),first)
        return features
    except (httpx.HTTPError,ValueError,AttributeError) as exc:
        elapsed=(time.perf_counter()-started)*1000; status=getattr(getattr(exc,"response",None),"status_code","network_error")
        errors.append(f"{path}: HTTP {status} - {type(exc).__name__}: {exc}")
        LOGGER.debug("url=%s status=%s elapsed_ms=%.0f error=%s",url,status,elapsed,exc)
        return []

def _parse_parcel(feature):
    if not feature: return None
    p=feature.get("properties") or {}; section=str(_pick(p,"section",default="")); number=str(_pick(p,"numero",default=""))
    return {"insee":_pick(p,"code_insee","insee"),"prefix":_pick(p,"com_abs","prefixe"),"section":section,"number":number,"label":" ".join(v for v in (section,number) if v) or "Non disponible","id":_pick(p,"idu","id","identifiant"),"area_m2":_pick(p,"contenance","surface"),"geometry":feature.get("geometry"),"properties":p}

def _is_oap(feature):
    p=feature.get("properties") or {}; text=" ".join(str(v) for v in p.values() if v is not None).lower()
    return str(p.get("typepsc","")) in OAP_TYPES or "oap" in text or "orientation" in text

def _summaries(features,kind):
    rows=[]
    for feature in features:
        p=feature.get("properties") or {}
        rows.append({"kind":kind,"label":_pick(p,"libelle","nomsuplitt","nomass","typeass","suptype",default="Sans libellé"),"type":_pick(p,"typepsc","suptype"),"subtype":_pick(p,"stypepsc"),"id":_pick(p,"idpsc","idass","lib_idpsc","gid")})
    return rows

async def analyze(point: dict[str,Any]):
    errors=[]
    async with httpx.AsyncClient(timeout=settings.http_timeout,headers={"User-Agent":"HomeCheck/1.0 local"}) as client:
        parcel_features=await _query(client,"cadastre/parcelle",_point(point),errors)
        parcel=_parse_parcel(parcel_features[0] if parcel_features else None)
        intersection=parcel.get("geometry") if parcel and parcel.get("geometry") else _point(point)
        zoning_f,document_f,municipality_f=await asyncio.gather(_query(client,"gpu/zone-urba",intersection,errors),_query(client,"gpu/document",intersection,errors),_query(client,"gpu/municipality",_point(point),errors))
        parcel_layers=await asyncio.gather(*[_query(client,f"gpu/{layer}",intersection,errors) for layer in PRESCRIPTION_LAYERS+SUP_LAYERS])
        nearby_layers=await asyncio.gather(*[_query(client,f"gpu/{layer}",_buffer(point),errors) for layer in PRESCRIPTION_LAYERS])
    zone_p=(zoning_f[0].get("properties") or {}) if zoning_f else {}; doc_p=(document_f[0].get("properties") or {}) if document_f else {}; municipality_p=(municipality_f[0].get("properties") or {}) if municipality_f else {}
    prescription_features=[f for group in parcel_layers[:3] for f in group]; servitude_features=[f for group in parcel_layers[3:] for f in group]; near_prescriptions=[f for group in nearby_layers for f in group]
    oap_on=[f for f in prescription_features if _is_oap(f)]; oap_near=[f for f in near_prescriptions if _is_oap(f)]
    document_type=_pick(doc_p,"du_type","type",default="RNU" if municipality_p.get("is_rnu") else "Non disponible")
    zoning={"zone":_pick(zone_p,"libelle","typezone","lib_idzone",default="Non disponible"),"label":_pick(zone_p,"libelong","libelle",default="Non disponible"),"insee":_pick(zone_p,"insee",default=(parcel or {}).get("insee") or _pick(municipality_p,"insee")),"document_id":_pick(zone_p,"gpu_doc_id",default=_pick(doc_p,"gpu_doc_id","id")),"document_name":_pick(doc_p,"name","grid_title"),"document_type":document_type,"version":_pick(zone_p,"datvalid","datappro",default=_pick(doc_p,"gpu_timestamp")),"regulation_file":_pick(zone_p,"nomfic"),"regulation_url":_pick(zone_p,"urlfic"),"properties":zone_p}
    return {"available":bool(parcel or zoning_f or document_f),"parcel":parcel,"parcel_label":parcel["label"] if parcel else "Non disponible","zone":zoning["zone"],"zoning":zoning,"document":document_type,"oap":{"on_parcel":"oui" if oap_on else "non" if not errors else "inconnu","nearby_250m":"oui" if oap_near else "non","details":_summaries(oap_on+oap_near,"OAP")},"prescriptions":_summaries(prescription_features,"Prescription"),"servitudes":_summaries(servitude_features,"Servitude"),"prescription_count":len(prescription_features),"servitude_count":len(servitude_features),"neighbor_potential":"Inconnu","reliability":"Haute" if zoning_f and parcel else "Moyenne" if parcel or zoning_f else "Inconnue","source":"API Carto IGN / Cadastre / GPU","errors":errors,"link":f'https://www.geoportail-urbanisme.gouv.fr/map/#tile=1&lon={point["lon"]}&lat={point["lat"]}&zoom=17',"notice":"Le zonage ne permet pas, à lui seul, de conclure à la constructibilité. Les règles doivent être confirmées dans le règlement écrit et auprès du service urbanisme."}

@cached(lambda point:cache_key("urbanisme-v2",point["lat"],point["lon"]),days=7)
async def inspect(point): return await analyze(point)
