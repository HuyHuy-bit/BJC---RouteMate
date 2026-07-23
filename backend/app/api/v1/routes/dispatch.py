from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.booking import Booking
from app.models.trip import Trip
from app.models.user import User
from app.schemas.trip import MatchingRunResult, TripOut
from app.services.audit import log_pii_access
from app.services.booking_service import to_booking_out
from app.services.matching import run_matching

router = APIRouter(tags=["dispatch"])


def _to_trip_out(trip: Trip) -> TripOut:
    bookings_out = [to_booking_out(b) for b in trip.bookings]
    return TripOut(
        id=trip.id,
        status=trip.status,
        driver_id=trip.driver_id,
        vehicle_label=trip.vehicle_label,
        is_private=len(trip.bookings) == 1 and trip.bookings[0].is_private,
        bookings=bookings_out,
        created_at=trip.created_at,
    )


@router.post("/run", response_model=MatchingRunResult)
def run_dispatch(
    radius_meters: float = 3000,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Runs one matching pass over all queued bookings. In production this
    would also run on a schedule (e.g. every 15 min) — see
    docs/ARCHITECTURE.md section 5 — but a manual trigger is what you want
    while testing.
    """
    trips = run_matching(db, radius_meters=radius_meters)

    trip_ids = [t.id for t in trips]
    full_trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer))
        .filter(Trip.id.in_(trip_ids))
        .all()
    )

    for trip in full_trips:
        for booking in trip.bookings:
            log_pii_access(
                db,
                actor_user_id=current_user.id,
                action="dispatch_match_read_customer",
                target_type="customer",
                target_id=booking.customer_id,
            )

    db.commit()
    for trip in full_trips:
        db.refresh(trip)

    trips_out = [_to_trip_out(t) for t in full_trips]
    return MatchingRunResult(trips_created=len(trips_out), trips=trips_out)


@router.get("/trips", response_model=list[TripOut])
def list_trips(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.admin, UserRole.dispatcher, UserRole.driver)
    ),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer))
        .order_by(Trip.created_at.desc())
        .all()
    )
    return [_to_trip_out(t) for t in trips]
