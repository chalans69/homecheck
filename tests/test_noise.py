import pytest
from app.scoring import noise_score
from app.services.noise import analyze, _level

def test_proximity_thresholds():
    assert _level(49)=="very_high"
    assert _level(80)=="high"
    assert _level(145)=="medium"
    assert _level(400)=="low"
    assert _level(900)=="very_low"

def test_noise_score_available_data():
    result={"available":True,"road":{"status":"available","level":"high"},"railway":{"status":"unavailable"},"aircraft":{"status":"available","level":"very_low"},"industry":{"status":"available","level":"low"}}
    assert noise_score(result) == 35

def test_motorway_186m_cannot_be_diluted_by_other_categories():
    from app.services.noise import refresh_levels
    result={"available":True,"road":{"status":"available","indicator":"proximity","type":"motorway","distance_m":186,"level":"medium"}}
    for category in ("railway","aircraft","industry"):
        result[category]={"status":"available","level":"very_low"}
    refresh_levels(result)
    assert result["road"]["level"] == "high"
    assert noise_score(result) == 35
    result.pop("industry")
    assert noise_score(result) == 35

@pytest.mark.asyncio
async def test_real_reference_point_has_geographic_fallbacks():
    result=await analyze({"lon":1.562082,"lat":43.216163})
    if result["errors"] and result["road"]["distance_m"] is None:
        pytest.skip("Overpass temporairement indisponible pendant ce test d’intégration")
    assert result["road"]["distance_m"] is not None
    assert result["railway"]["distance_m"] is not None
    assert result["aircraft"]["distance_m"] is not None
    assert result["industry"]["counts_by_radius"]["2000"] >= 1
    assert result["road"]["value_db"] is None
