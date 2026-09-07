import logging,math,time
import httpx
from ..config import settings
from .common import cached,cache_key

LOGGER=logging.getLogger("homecheck.pois");LOGGER.setLevel(logging.DEBUG)
OVERPASS="https://overpass-api.de/api/interpreter"

def distance_m(a,b):
    r=6_371_000;p1,p2=math.radians(a["lat"]),math.radians(b["lat"]);dp=p2-p1;dl=math.radians(b["lon"]-a["lon"])
    return 2*r*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))

def _location(element):return element.get("center") or ({"lat":element.get("lat"),"lon":element.get("lon")} if element.get("lat") is not None else None)
def _nearest(items,point,predicate):
    found=[]
    for e in items:
        tags=e.get("tags") or {};loc=_location(e)
        if loc and predicate(tags):found.append({"name":tags.get("name") or "Sans nom","distance_m":round(distance_m(point,loc)),"tags":tags})
    return min(found,key=lambda x:x["distance_m"]) if found else None

async def analyze(point,radius=3000):
    errors=[];lat,lon=point["lat"],point["lon"]
    query=f'''[out:json][timeout:25];(nwr(around:{radius},{lat},{lon})[shop~"^(supermarket|convenience|bakery|butcher)$"];nwr(around:{radius},{lat},{lon})[amenity=marketplace];nwr(around:{radius},{lat},{lon})[amenity~"^(school|kindergarten|college)$"];nwr(around:{radius},{lat},{lon})[amenity~"^(doctors|clinic|pharmacy|hospital)$"];nwr(around:{radius},{lat},{lon})[highway=bus_stop];nwr(around:{radius},{lat},{lon})[railway~"^(station|tram_stop|subway_entrance)$"];nwr(around:{radius},{lat},{lon})[amenity=parking][park_ride];);out tags center;'''
    started=time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=max(settings.http_timeout,30),headers={"User-Agent":"HomeCheck/1.0 local"}) as client:response=await client.post(OVERPASS,data={"data":query})
        response.raise_for_status();items=response.json().get("elements",[]);LOGGER.debug("url=%s status=%s elapsed_ms=%.0f elements=%d",response.request.url,response.status_code,(time.perf_counter()-started)*1000,len(items))
    except (httpx.HTTPError,ValueError) as exc:
        errors.append(f"Overpass POI: {type(exc).__name__}: {exc}");items=[]
    food=[e for e in items if (e.get("tags") or {}).get("shop") in {"supermarket","convenience","bakery","butcher"} or (e.get("tags") or {}).get("amenity")=="marketplace"]
    food_1km=sum(1 for e in food if _location(e) and distance_m(point,_location(e))<=1000)
    categories={"supermarket":_nearest(items,point,lambda t:t.get("shop")=="supermarket"),"bakery":_nearest(items,point,lambda t:t.get("shop")=="bakery"),"school":_nearest(items,point,lambda t:t.get("amenity") in {"school","kindergarten","college"}),"doctor":_nearest(items,point,lambda t:t.get("amenity") in {"doctors","clinic"}),"pharmacy":_nearest(items,point,lambda t:t.get("amenity")=="pharmacy"),"hospital":_nearest(items,point,lambda t:t.get("amenity")=="hospital"),"bus":_nearest(items,point,lambda t:t.get("highway")=="bus_stop"),"station":_nearest(items,point,lambda t:t.get("railway")=="station"),"park_ride":_nearest(items,point,lambda t:t.get("park_ride") in {"yes","designated"})}
    return {"available":bool(items),"categories":categories,"food_count_1km":food_1km,"items_found":len(items),"endpoint":OVERPASS,"radius_m":radius,"source":"OpenStreetMap / Overpass","reliability":"moyenne","errors":errors,"response_time_ms":round((time.perf_counter()-started)*1000)}

@cached(lambda point,radius=3000:cache_key("pois-v1",point["lat"],point["lon"],radius),days=7)
async def inspect(point,radius=3000):return await analyze(point,radius)
