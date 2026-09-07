from typing import Any, Literal
from pydantic import BaseModel, Field

class AnalysisRequest(BaseModel):
    property_address: str = Field(min_length=5, max_length=250)
    work_address: str = Field(min_length=2, max_length=250)
    arrival_time: str = "09:00"
    departure_time: str = "18:00"
    property_type: Literal["maison", "appartement", "terrain"] = "maison"
    priority: Literal["trajet", "calme", "risques", "urbanisme", "environnement", "prix"] = "trajet"

class GeoPoint(BaseModel):
    label: str
    lat: float
    lon: float
    city: str = ""
    postcode: str = ""
    insee: str = ""
    source: str = "BAN"
    reliability: str = "Haute"

class AnalysisRecord(BaseModel):
    id: int | None = None
    created_at: str
    request: dict[str, Any]
    result: dict[str, Any]

