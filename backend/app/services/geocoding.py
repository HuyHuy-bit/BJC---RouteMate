"""
Client for Goong Maps' Geocoding API. This is a drop-in HTTP-level
replacement for Google's Geocoding API — same request/response shape,
different base URL and key param name. See https://docs.goong.io/rest/geocode/

Real network call, not a mock: this replaces the prototype's fake
keyword-matching geocoder entirely. If GOONG_API_KEY isn't set (still a
placeholder from .env.example), this raises clearly rather than silently
returning fake data.
"""

import httpx

from app.core.config import settings
from app.schemas.geocode import GeocodeResponse, GeocodeResult

GOONG_GEOCODE_URL = "https://rsapi.goong.io/geocode"


class GeocodingError(Exception):
    pass


def geocode_address(address: str) -> GeocodeResponse:
    if not settings.goong_api_key or settings.goong_api_key == "your_goong_api_key":
        raise GeocodingError(
            "GOONG_API_KEY is not configured — set a real key in .env "
            "(get one at https://goong.io)"
        )

    response = httpx.get(
        GOONG_GEOCODE_URL,
        params={"address": address, "api_key": settings.goong_api_key},
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()

    status = data.get("status")
    if status == "ZERO_RESULTS":
        return GeocodeResponse(query=address, results=[])
    if status != "OK":
        raise GeocodingError(
            f"Goong geocoding failed with status={status}: "
            f"{data.get('error_message', 'no error message provided')}"
        )

    results = [
        GeocodeResult(
            formatted_address=r["formatted_address"],
            lat=r["geometry"]["location"]["lat"],
            lng=r["geometry"]["location"]["lng"],
            place_id=r["place_id"],
        )
        for r in data.get("results", [])
    ]
    return GeocodeResponse(query=address, results=results)
