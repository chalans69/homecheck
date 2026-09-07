import pytest
from app.services.routing import crow_distance
from app.services.geocoding import geocode, GeocodingError

def test_distance():
    d=crow_distance({"lat":48.8566,"lon":2.3522},{"lat":48.8584,"lon":2.2945})
    assert 3 < d < 6

@pytest.mark.asyncio
async def test_geocoding_real():
    point=await geocode("1 place de l'Hôtel de Ville, Paris")
    assert point["lat"] > 48
    assert point["source"] == "BAN"

@pytest.mark.asyncio
async def test_geocoding_unavailable(monkeypatch):
    import httpx
    async def fail(*args,**kwargs): raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx.AsyncClient,"get",fail)
    with pytest.raises(GeocodingError): await geocode("adresse spéciale sans cache 987654")

