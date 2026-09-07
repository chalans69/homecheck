import asyncio
from . import pois,internet

WEIGHTS={"food":25,"school":20,"health":20,"transport":20,"fiber":15}

def proximity_score(poi,net):
    score=0;c=poi.get("categories",{})
    if poi.get("food_count_1km",0)>0:score+=WEIGHTS["food"]
    if c.get("school") and c["school"]["distance_m"]<1000:score+=WEIGHTS["school"]
    if any(c.get(k) and c[k]["distance_m"]<2000 for k in ("doctor","pharmacy")):score+=WEIGHTS["health"]
    if any(c.get(k) and c[k]["distance_m"]<500 for k in ("bus","station")):score+=WEIGHTS["transport"]
    if net.get("ftth_coverage",0)>=80:score+=WEIGHTS["fiber"]
    return score

async def inspect(point):
    poi,net=await asyncio.gather(pois.inspect(point),internet.inspect(point))
    return {"available":poi.get("available") or net.get("available"),"pois":poi,"internet":net,"score":proximity_score(poi,net),"score_label":"Score de proximité HomeCheck","reliability":"moyenne","errors":poi.get("errors",[])+net.get("errors",[]),"source":"OpenStreetMap / Overpass + ARCEP"}
