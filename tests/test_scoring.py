from app.scoring import calculate

def test_score_redistributes_missing_categories():
    result=calculate({"mobility":80,"risks":100,"noise":None,"urbanism":None,"environment":None,"market":None},"trajet")
    assert result["total"]==87
    assert round(sum(result["weights"].values()))==100

def test_no_available_data():
    result=calculate({"mobility":None,"risks":None},"trajet")
    assert result["total"] is None

