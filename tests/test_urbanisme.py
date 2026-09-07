import pytest

from app.scoring import urbanism_score
from app.services.urbanisme import analyze


@pytest.mark.asyncio
async def test_api_carto_real_reference_point():
    result = await analyze({"lon": 1.562082, "lat": 43.216163})
    assert result["parcel"]["id"] == "092820000A1819"
    assert result["parcel"]["area_m2"] == 3530
    assert result["zone"] == "A"
    assert result["document"] == "PLU"
    assert result["oap"]["on_parcel"] in {"oui", "non", "inconnu"}


def test_urbanism_score_uses_available_reliable_fields():
    value = urbanism_score({"available": True, "parcel": {"id": "x"}, "zone": "UB", "document": "PLU", "oap": {"on_parcel": "non"}})
    assert value == 90
