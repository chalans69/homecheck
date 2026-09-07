"""Multi-level noise analysis: official models first, geographic proximity second."""
import asyncio, logging, math, time
import httpx
from ..config import settings
from .common import cached, cache_key
from .noise_providers.toulouse import ToulouseNoiseProvider

LOGGER=logging.getLogger("homecheck.noise"); LOGGER.setLevel(logging.DEBUG)
OVERPASS="https://overpass-api.de/api/interpreter"
GEORISQUES_ICPE="https://georisques.gouv.fr/api/v1/installations_classees"

def _distance(a_lat,a_lon,b_lat,b_lon):
    r=6_371_000;p1,p2=math.radians(a_lat),math.radians(b_lat);dp=p2-p1;dl=math.radians(b_lon-a_lon)
    return 2*r*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))

def _segment_distance(lat,lon,a,b):
    scale=math.cos(math.radians(lat));px,py=lon*scale,lat;ax,ay=a["lon"]*scale,a["lat"];bx,by=b["lon"]*scale,b["lat"]
    dx,dy=bx-ax,by-ay;t=0 if dx*dx+dy*dy==0 else max(0,min(1,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)))
    return _distance(lat,lon,ay+t*dy,(ax+t*dx)/scale)

def _element_distance(point,element):
    geometry=element.get("geometry") or []
    if len(geometry)>1:return min(_segment_distance(point["lat"],point["lon"],a,b) for a,b in zip(geometry,geometry[1:]))
    center=element.get("center") or element
    return _distance(point["lat"],point["lon"],center["lat"],center["lon"]) if "lat" in center and "lon" in center else float("inf")

def _level(distance):
    if distance<50:return "very_high"
    if distance<100:return "high"
    if distance<250:return "medium"
    if distance<500:return "low"
    return "very_low"

def _indicator(element,point,category):
    tags=element.get("tags") or {};distance=round(_element_distance(point,element));name=tags.get("ref") or tags.get("name") or tags.get("operator") or {"road":"Axe principal","railway":"Voie ferrée","aircraft":"Aérodrome","industry":"Zone industrielle"}.get(category,"Site")
    details="Estimation basée sur la proximité de l’infrastructure, pas sur une mesure acoustique."
    if category=="aircraft":details="Proximité uniquement : l’exposition réelle dépend notamment des trajectoires aériennes et d’un éventuel PEB."
    return {"status":"available","level":_level(distance),"value_db":None,"indicator":"proximity","nearest_source":name,"distance_m":distance,"source":"OpenStreetMap / Overpass","confidence":"medium","official":False,"details":details,"type":tags.get("highway") or tags.get("railway") or tags.get("aeroway")}

def refresh_levels(data):
    """HomeCheck heuristic: motorway proximity warrants wider vigilance bands."""
    road = data.get("road")
    if isinstance(road, dict) and road.get("indicator") == "proximity" and road.get("distance_m") is not None:
        distance = road["distance_m"]
        thresholds = (100, 300, 600, 1000) if road.get("type") in {"motorway", "trunk"} else (50, 100, 250, 500)
        road["level"] = next((level for threshold, level in zip(thresholds, ("very_high", "high", "medium", "low")) if distance < threshold), "very_low")
    return data

def _unavailable(details):return {"status":"unavailable","level":"unknown","value_db":None,"indicator":"none","nearest_source":None,"distance_m":None,"source":None,"confidence":"unknown","official":False,"details":details}

async def _overpass(client,point,errors):
    lat,lon=point["lat"],point["lon"]
    query=f'''[out:json][timeout:25];(way(around:5000,{lat},{lon})[highway~"^(motorway|trunk|primary|secondary|tertiary)$"];way(around:5000,{lat},{lon})[railway~"^(rail|light_rail|tram)$"];node(around:5000,{lat},{lon})[railway=station];nwr(around:50000,{lat},{lon})[aeroway~"^(aerodrome|airport)$"];nwr(around:2000,{lat},{lon})[landuse=industrial];);out tags center geom;'''
    started=time.perf_counter()
    try:
        response=await client.post(OVERPASS,data={"data":query});elapsed=(time.perf_counter()-started)*1000;response.raise_for_status();elements=response.json().get("elements",[])
        LOGGER.debug("url=%s status=%s elapsed_ms=%.0f elements=%d",response.request.url,response.status_code,elapsed,len(elements));return elements
    except (httpx.HTTPError,ValueError) as exc:
        errors.append(f"Overpass: {type(exc).__name__}: {exc}");LOGGER.debug("url=%s error=%s",OVERPASS,exc);return []

async def _icpe(client,point,errors):
    started=time.perf_counter()
    try:
        response=await client.get(GEORISQUES_ICPE,params={"latlon":f'{point["lon"]},{point["lat"]}',"rayon":2000});elapsed=(time.perf_counter()-started)*1000;response.raise_for_status();rows=response.json().get("data",[])
        LOGGER.debug("url=%s status=%s elapsed_ms=%.0f installations=%d",response.request.url,response.status_code,elapsed,len(rows));return rows
    except (httpx.HTTPError,ValueError) as exc:
        errors.append(f"Géorisques ICPE: {type(exc).__name__}: {exc}");LOGGER.debug("url=%s error=%s",GEORISQUES_ICPE,exc);return []

def _nearest(elements,point,predicate,category):
    matches=[e for e in elements if predicate(e.get("tags") or {})]
    return _indicator(min(matches,key=lambda e:_element_distance(point,e)),point,category) if matches else _unavailable("Aucune infrastructure correspondante retournée dans le rayon de recherche.")

def _industry(rows,point,osm):
    sites=[]
    for row in rows:
        if row.get("latitude") is not None and row.get("longitude") is not None:sites.append({"name":row.get("raisonSociale") or "ICPE","distance_m":round(_distance(point["lat"],point["lon"],row["latitude"],row["longitude"])),"official":True})
    if sites:
        nearest=min(sites,key=lambda x:x["distance_m"]);counts={str(r):sum(s["distance_m"]<=r for s in sites) for r in (250,500,1000,2000)}
        return {"status":"available","level":_level(nearest["distance_m"]),"value_db":None,"indicator":"proximity","nearest_source":nearest["name"],"distance_m":nearest["distance_m"],"source":"Géorisques — installations classées","confidence":"high","official":True,"details":"Nuisance industrielle potentielle : une ICPE n’est pas nécessairement une source de bruit.","counts_by_radius":counts,"sites":sites}
    return _nearest(osm,point,lambda t:t.get("landuse")=="industrial","industry")

async def analyze(point):
    errors=[]
    async with httpx.AsyncClient(timeout=max(settings.http_timeout,30),headers={"User-Agent":"HomeCheck/1.0 local"}) as client:
        elements,icpe,official=await asyncio.gather(_overpass(client,point,errors),_icpe(client,point,errors),ToulouseNoiseProvider().query(client,point,errors))
    road=_nearest(elements,point,lambda t:t.get("highway") in {"motorway","trunk","primary","secondary","tertiary"},"road")
    railway=_nearest(elements,point,lambda t:t.get("railway") in {"rail","light_rail","tram"},"railway");stations=[e for e in elements if (e.get("tags") or {}).get("railway")=="station"]
    if stations:railway["station"]=_indicator(min(stations,key=lambda e:_element_distance(point,e)),point,"railway")
    aircraft=_nearest(elements,point,lambda t:t.get("aeroway") in {"aerodrome","airport"},"aircraft")
    if official.get("railway"):railway={**official["railway"],"proximity":railway}
    industry=_industry(icpe,point,elements)
    refresh_levels({"road":road})
    sources=official.get("sources",[])
    return {"available":any(x.get("status")=="available" for x in (road,railway,aircraft,industry)),"road":road,"railway":railway,"aircraft":aircraft,"industry":industry,"official_noise_sources_found":sources,"provider":official.get("provider") if sources else "fallback OSM + Géorisques","errors":errors,"message":"Les valeurs en dB ne sont affichées que lorsqu’une source réglementaire les fournit.","source":"OSM / Géorisques / fournisseurs CBS"}

@cached(lambda point:cache_key("noise-v3",point["lat"],point["lon"]),days=7)
async def inspect(point):return await analyze(point)
