"""Local market comparables from the lightweight official Geo-DVF commune CSVs."""
import asyncio, csv, io, logging, math, statistics, time
from collections import defaultdict
from datetime import date, datetime
import httpx
from ..config import settings
from .common import cached, cache_key

LOGGER=logging.getLogger("homecheck.dvf");LOGGER.setLevel(logging.DEBUG)
BASE="https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/communes/{department}/{insee}.csv"
TYPE_LABEL={"maison":"Maison","appartement":"Appartement"}

def distance_m(lat1,lon1,lat2,lon2):
    r=6_371_000;p1,p2=math.radians(lat1),math.radians(lat2);dp=p2-p1;dl=math.radians(lon2-lon1)
    return 2*r*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))

def _number(value):
    try:return float(str(value).replace(",",".")) if value not in (None,"") else None
    except (TypeError,ValueError):return None

def _department(insee):return insee[:3] if insee.startswith(("2A","2B","97")) else insee[:2]

async def _fetch_year(client,year,insee,errors,timings):
    url=BASE.format(year=year,department=_department(insee),insee=insee);started=time.perf_counter()
    try:
        response=await client.get(url);elapsed=(time.perf_counter()-started)*1000;timings[url]=round(elapsed);response.raise_for_status();rows=list(csv.DictReader(io.StringIO(response.text)))
        LOGGER.debug("url=%s status=%s elapsed_ms=%.0f rows=%d",url,response.status_code,elapsed,len(rows));return rows
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code!=404:errors.append(f"DVF {year}: HTTP {exc.response.status_code}")
        return []
    except (httpx.HTTPError,UnicodeError,csv.Error) as exc:
        errors.append(f"DVF {year}: {type(exc).__name__}: {exc}");return []

def filter_transactions(rows,point,property_type,radius,months=36,now=None):
    now=now or date.today();cutoff=date(now.year-(months//12),now.month,1);groups=defaultdict(list)
    for row in rows:groups[row.get("id_mutation")].append(row)
    retained=[]
    wanted=TYPE_LABEL.get(property_type)
    for mutation_id,group in groups.items():
        try:mutation_date=datetime.strptime(group[0]["date_mutation"],"%Y-%m-%d").date()
        except (KeyError,ValueError):continue
        if mutation_date<cutoff:continue
        built=[r for r in group if r.get("type_local") in {"Maison","Appartement"}]
        if not built or (wanted and any(r.get("type_local")!=wanted for r in built)):continue
        # A comparable must represent exactly one built local; multi-local mutations are ambiguous.
        unique={(r.get("type_local"),r.get("surface_reelle_bati"),r.get("adresse_numero"),r.get("adresse_nom_voie")) for r in built}
        if len(unique)!=1:continue
        row=built[0];surface=_number(row.get("surface_reelle_bati"));price=_number(row.get("valeur_fonciere"));lat=_number(row.get("latitude"));lon=_number(row.get("longitude"))
        if not surface or not price or not lat or not lon or surface<9 or price<=0:continue
        distance=distance_m(point["lat"],point["lon"],lat,lon)
        if distance>radius:continue
        price_m2=price/surface
        if not 300<=price_m2<=20_000:continue
        address=" ".join(x for x in (row.get("adresse_numero"),row.get("adresse_nom_voie"),row.get("code_postal"),row.get("nom_commune")) if x)
        retained.append({"id":mutation_id,"date":row["date_mutation"],"price":round(price),"address":address,"lat":lat,"lon":lon,"type":row.get("type_local"),"surface_built":surface,"surface_land":_number(row.get("surface_terrain")),"rooms":_number(row.get("nombre_pieces_principales")),"price_m2":round(price_m2),"distance_m":round(distance)})
    if len(retained)>=4:
        values=sorted(x["price_m2"] for x in retained);q1=statistics.quantiles(values,n=4,method="inclusive")[0];q3=statistics.quantiles(values,n=4,method="inclusive")[2];iqr=q3-q1
        retained=[x for x in retained if q1-1.5*iqr<=x["price_m2"]<=q3+1.5*iqr]
    return sorted(retained,key=lambda x:x["distance_m"])

async def analyze(point,property_type="maison",radius=2000,months=36):
    started=time.perf_counter();errors=[];timings={};insee=point.get("insee","")
    if not insee:return {"available":False,"errors":["Code INSEE absent"],"raw_transactions":[],"sales":[]}
    years=range(date.today().year-3,date.today().year+1)
    async with httpx.AsyncClient(timeout=max(settings.http_timeout,20),headers={"User-Agent":"HomeCheck/1.0 local"},follow_redirects=True) as client:
        batches=await asyncio.gather(*[_fetch_year(client,y,insee,errors,timings) for y in years])
    rows=[r for batch in batches for r in batch];sales=filter_transactions(rows,point,property_type,radius,months);values=[x["price_m2"] for x in sales]
    reliability="haute" if len(sales)>=20 else "moyenne" if len(sales)>=8 else "faible" if len(sales)>=3 else "insuffisante"
    return {"available":len(sales)>=3,"endpoint":BASE,"commune":rows[0].get("nom_commune") if rows else insee,"transactions_found":len({r.get("id_mutation") for r in rows}),"transactions_retained":len(sales),"median":round(statistics.median(values)) if values else None,"mean":round(statistics.mean(values)) if values else None,"price_m2":round(statistics.median(values)) if values else None,"sales":sales[:10],"raw_transactions":rows,"reliability":reliability,"period_months":months,"radius_m":radius,"errors":errors,"response_time_ms":round((time.perf_counter()-started)*1000),"timings":timings,"message":"Comparables DVF géolocalisés et filtrés" if sales else "Aucune transaction comparable fiable dans le rayon.","source":"DVF géolocalisé — DGFiP / data.gouv.fr"}

@cached(lambda point,property_type="maison",radius=2000,months=36:cache_key("dvf-v1",point.get("insee"),point["lat"],point["lon"],property_type,radius,months),days=7)
async def inspect(point,property_type="maison",radius=2000,months=36):return await analyze(point,property_type,radius,months)
