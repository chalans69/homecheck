from datetime import date
import pytest
import httpx

from app.services.dvf import filter_transactions, distance_m
from app.services import pois, internet

def _row(mid,price,surface,lat=43.2162,lon=1.5621,kind="Maison",day="2025-01-10"):
    return {"id_mutation":mid,"date_mutation":day,"type_local":kind,"surface_reelle_bati":str(surface),"valeur_fonciere":str(price),"latitude":str(lat),"longitude":str(lon),"adresse_numero":"1","adresse_nom_voie":"RUE TEST","code_postal":"09700","nom_commune":"Saverdun","surface_terrain":"500","nombre_pieces_principales":"4"}

def test_dvf_median_and_radius_filter():
    rows=[_row("a",100_000,100),_row("b",200_000,100,43.2163),_row("c",300_000,100,43.2164),_row("far",150_000,100,44.0)]
    kept=filter_transactions(rows,{"lat":43.216163,"lon":1.562082},"maison",2000,now=date(2026,1,1))
    assert len(kept)==3
    assert sorted(x["price_m2"] for x in kept)[1]==2000

def test_dvf_rejects_aberrant_and_mixed_mutations():
    rows=[_row("bad",9_000_000,20),_row("mixed",100_000,50,"43.2162","1.5621","Maison"),_row("mixed",100_000,30,"43.2162","1.5621","Appartement")]
    assert filter_transactions(rows,{"lat":43.216163,"lon":1.562082},"maison",2000,now=date(2026,1,1))==[]

def test_poi_distance():
    assert 0 < distance_m(43.216163,1.562082,43.217,1.562082) < 100

@pytest.mark.asyncio
async def test_overpass_unavailable(monkeypatch):
    async def fail(*args,**kwargs):raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx.AsyncClient,"post",fail)
    result=await pois.analyze({"lat":43.216163,"lon":1.562082})
    assert result["available"] is False
    assert result["errors"]

@pytest.mark.asyncio
async def test_arcep_unavailable(monkeypatch):
    async def fail(*args,**kwargs):raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx.AsyncClient,"get",fail)
    result=await internet.analyze({"lat":43.216163,"lon":1.562082,"insee":"09282"})
    assert result["available"] is False
    assert result["errors"]
