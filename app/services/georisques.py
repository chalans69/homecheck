import httpx
from datetime import datetime, timezone
from ..config import settings
from .common import cached, cache_key

@cached(lambda point: cache_key("risks",point["lat"],point["lon"]), days=7)
async def risks(point):
    now=datetime.now(timezone.utc).date().isoformat()
    result={"available":False,"items":[],"source":"Géorisques","retrieved_at":now,"reliability":"Inconnue"}
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout,headers={"User-Agent":"HomeCheck/1.0 local"}) as client:
            r=await client.get("https://georisques.gouv.fr/api/v1/gaspar/risques",params={"latlon":f'{point["lon"]},{point["lat"]}'})
            r.raise_for_status(); data=r.json().get("data",[])
        names=[]
        for item in data:
            name=item.get("libelle_risque_long") or item.get("libelle_risque_jo") or item.get("libelle_risque")
            if name and name not in names: names.append(name)
        result.update(available=True,items=[{"name":n,"level":"Présence recensée","detail":"Risque communal recensé","source":"Géorisques","reliability":"Haute"} for n in names[:12]],reliability="Haute")
    except (httpx.HTTPError,ValueError,KeyError):
        result["message"]="Données Géorisques non disponibles automatiquement"
    return result

