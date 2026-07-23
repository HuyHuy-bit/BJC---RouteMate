from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.geocode import GeocodeResponse
from app.services.geocoding import GeocodingError, geocode_address

router = APIRouter(tags=["geocode"])


@router.get("", response_model=GeocodeResponse)
def geocode(address: str, current_user: User = Depends(get_current_user)):
    """
    Any logged-in staff member can geocode — this just looks up an
    address, it doesn't touch customer data, so it doesn't need
    role-restriction the way booking/customer routes do.
    """
    if not address.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="address is required"
        )
    try:
        return geocode_address(address)
    except GeocodingError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
