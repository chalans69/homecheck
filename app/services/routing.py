import math, httpx
from ..config import settings
from .common import cached, cache_key

def crow_distance(a,b):
    r=6371; p1,p2=math.radians(a["lat"]),math.radians(b["lat"]); dp=p2-p1; dl=math.radians(b["lon"]-a["lon"])
    return 2*r*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))

@cached(lambda a,b: cache_key("route",a["lat"],a["lon"],b["lat"],b["lon"]), hours=24)
async def route(a,b):
    url=f'https://router.project-osrm.org/route/v1/driving/{a["lon"]},{a["lat"]};{b["lon"]},{b["lat"]}'
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout, headers={"User-Agent":"HomeCheck/1.0 local"}) as client:
            r=await client.get(url,params={"overview":"full","geometries":"geojson"}); r.raise_for_status(); data=r.json(); best=data["routes"][0]
            return {"available":True,"distance_km":round(best["distance"]/1000,1),"duration_min":round(best["duration"]/60),"geometry":best["geometry"],"source":"OSRM / OpenStreetMap","reliability":"Moyenne","note":"Temps calculé hors trafic temps réel"}
    except (httpx.HTTPError,KeyError,IndexError,ValueError):
        d=round(crow_distance(a,b),1)
        return {"available":False,"distance_km":d,"duration_min":None,"geometry":None,"source":"Calcul géodésique local","reliability":"Faible","note":"Itinéraire indisponible ; distance à vol d’oiseau"}

