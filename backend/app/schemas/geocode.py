from pydantic import BaseModel


class GeocodeResult(BaseModel):
    formatted_address: str
    lat: float
    lng: float
    place_id: str


class GeocodeResponse(BaseModel):
    query: str
    results: list[GeocodeResult]
