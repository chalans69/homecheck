import logging,time
import httpx
from ..config import settings
from .common import cached,cache_key

LOGGER=logging.getLogger("homecheck.internet");LOGGER.setLevel(logging.DEBUG)
BASE="https://comparateurinternet.fr/api/v1/communes"

async def analyze(point):
    insee=point.get("insee");started=time.perf_counter();errors=[]
    if not insee:return {"available":False,"errors":["Code INSEE absent"]}
    url=f"{BASE}/{insee}"
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout,headers={"User-Agent":"HomeCheck/1.0 local"}) as client:response=await client.get(url)
        response.raise_for_status();data=response.json();tech=data.get("technologies",{});ftth=tech.get("ftth",{});best=next((name for name in ("ftth","coaxial","thd_radio","quatre_g_fixe","cuivre","satellite") if tech.get(name,{}).get("couverture",0)>0),None)
        LOGGER.debug("url=%s status=%s elapsed_ms=%.0f",response.request.url,response.status_code,(time.perf_counter()-started)*1000)
        return {"available":True,"insee":insee,"commune":data.get("commune"),"ftth_coverage":ftth.get("couverture"),"ftth_eligible":ftth.get("eligibles"),"premises":data.get("locaux"),"best_technology":best,"vintage":data.get("millesime"),"source":data.get("source","ARCEP — Ma connexion internet"),"endpoint":url,"reliability":"haute","scope":"commune","notice":"Donnée communale — l’éligibilité exacte du logement doit être confirmée.","errors":errors,"response_time_ms":round((time.perf_counter()-started)*1000)}
    except (httpx.HTTPError,ValueError) as exc:return {"available":False,"endpoint":url,"errors":[f"ARCEP: {type(exc).__name__}: {exc}"],"notice":"Donnée internet indisponible"}

@cached(lambda point:cache_key("internet-v1",point.get("insee")),days=30)
async def inspect(point):return await analyze(point)
