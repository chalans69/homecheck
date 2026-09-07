import logging,time
LOGGER=logging.getLogger("homecheck.noise.toulouse")
URL="https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets/isoph-fer-lden/records"

def _inside_ring(lon,lat,ring):
    inside=False;j=len(ring)-1
    for i,(x,y,*_) in enumerate(ring):
        xj,yj=ring[j][0],ring[j][1]
        if ((y>lat)!=(yj>lat)) and lon<(xj-x)*(lat-y)/(yj-y+1e-15)+x:inside=not inside
        j=i
    return inside

def _contains(geometry,lon,lat):
    if not geometry:return False
    coords=geometry.get("coordinates",[]);polygons=[coords] if geometry.get("type")=="Polygon" else coords if geometry.get("type")=="MultiPolygon" else []
    return any(poly and _inside_ring(lon,lat,poly[0]) for poly in polygons)

class ToulouseNoiseProvider:
    name="Toulouse Métropole Open Data"
    async def query(self,client,point,errors):
        started=time.perf_counter()
        try:
            response=await client.get(URL,params={"limit":100});response.raise_for_status();rows=response.json().get("results",[])
            LOGGER.debug("url=%s status=%s elapsed_ms=%.0f records=%d",response.request.url,response.status_code,(time.perf_counter()-started)*1000,len(rows));hits=[]
            for row in rows:
                shape=row.get("geo_shape") or {};geometry=shape.get("geometry",shape)
                if _contains(geometry,point["lon"],point["lat"]):hits.append(row)
            if not hits:return {"provider":self.name,"sources":[]}
            values=[str(x.get("db")) for x in hits if x.get("db") not in (None,"")];value=max(values) if values else None
            railway={"status":"available","level":"medium","value_db":value,"indicator":"Lden","nearest_source":"Carte ferroviaire","distance_m":None,"source":"Carte du bruit ferroviaire Toulouse Métropole","confidence":"high","official":True,"details":"Niveau modélisé Lden publié par Toulouse Métropole."}
            return {"provider":self.name,"sources":["isoph-fer-lden"],"railway":railway}
        except Exception as exc:
            errors.append(f"Toulouse CBS: {type(exc).__name__}: {exc}");return {"provider":self.name,"sources":[]}
