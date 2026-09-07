import httpx
from ..config import settings
from ..models import GeoPoint
from .common import cached, cache_key

class GeocodingError(ValueError): pass

@cached(lambda address: cache_key("geo", address), days=30)
async def geocode(address: str):
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout, headers={"User-Agent":"HomeCheck/1.0 local"}) as client:
            r = await client.get("https://data.geopf.fr/geocodage/search", params={"q": address, "limit": 1})
            r.raise_for_status(); features = r.json().get("features", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise GeocodingError("Service de géocodage temporairement indisponible") from exc
    if not features: raise GeocodingError(f"Adresse introuvable : {address}")
    f=features[0]; p=f.get("properties",{}); lon,lat=f["geometry"]["coordinates"]
    return GeoPoint(label=p.get("label",address),lat=lat,lon=lon,city=p.get("city",p.get("municipality","")),postcode=p.get("postcode",""),insee=p.get("citycode","")).model_dump()

async def reverse_geocode(lat:float,lon:float):
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout,headers={"User-Agent":"HomeCheck/1.0 local"}) as client:
            r=await client.get("https://data.geopf.fr/geocodage/reverse",params={"lat":lat,"lon":lon,"limit":1});r.raise_for_status();features=r.json().get("features",[])
        if not features:raise GeocodingError("Coordonnées non reconnues")
        f=features[0];p=f.get("properties",{});x,y=f["geometry"]["coordinates"]
        return GeoPoint(label=p.get("label","Coordonnées fournies"),lat=y,lon=x,city=p.get("city",p.get("municipality","")),postcode=p.get("postcode",""),insee=p.get("citycode","")).model_dump()
    except (httpx.HTTPError,ValueError,KeyError) as exc:raise GeocodingError("Géocodage inverse indisponible") from exc
