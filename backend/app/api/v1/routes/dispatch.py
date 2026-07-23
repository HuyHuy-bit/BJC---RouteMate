import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import TripStatus, UserRole, VehicleStatus
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.trip import (
    MatchingRunResult,
    TripAssignDriver,
    TripOut,
    TripStatusUpdate,
)
from app.services.audit import log_pii_access
from app.services.booking_service import to_booking_out
from app.services.dispatch_service import run_dispatch_cycle

router = APIRouter(tags=["dispatch"])

# Only these forward transitions are allowed — no skipping steps, no going
# backwards. Any role-appropriate caller can cancel from most states.
ALLOWED_TRANSITIONS: dict[TripStatus, set[TripStatus]] = {
    TripStatus.forming: {TripStatus.sealed, TripStatus.cancelled},
    TripStatus.sealed: {TripStatus.assigned, TripStatus.cancelled},
    TripStatus.assigned: {
        TripStatus.in_progress,
        TripStatus.reassigning,
        TripStatus.cancelled,
    },
    TripStatus.in_progress: {TripStatus.completed, TripStatus.cancelled},
    TripStatus.reassigning: {TripStatus.assigned, TripStatus.cancelled},
    TripStatus.completed: set(),
    TripStatus.cancelled: set(),
}


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


def _load_trip(db: Session, trip_id: uuid.UUID) -> Trip:
    trip = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer))
        .filter(Trip.id == trip_id)
        .first()
    )
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


@router.post("/run", response_model=MatchingRunResult)
def run_dispatch(
    radius_meters: float = 3000,  # retained for API compatibility; unused
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Manual trigger for the dispatch cycle.

    The cycle now also runs automatically on a timer, so this is an
    override rather than the only way trips ever leave — a dispatcher
    who wants to push things along immediately, not a required step.
    """
    summary = run_dispatch_cycle(db)

    full_trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer))
        .filter(Trip.status.in_([TripStatus.assigned, TripStatus.sealed]))
        .order_by(Trip.created_at.desc())
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

    trips_out = [_to_trip_out(t) for t in full_trips]
    return MatchingRunResult(trips_created=summary["sealed"], trips=trips_out)


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
        .filter(Trip.bookings.any())
        .order_by(Trip.created_at.desc())
        .all()
    )
    return [_to_trip_out(t) for t in trips]


@router.get("/my-trips", response_model=list[TripOut])
def my_trips(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.driver)),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer))
        .filter(Trip.driver_id == current_user.id)
        .filter(Trip.status.in_([TripStatus.assigned, TripStatus.in_progress]))
        .filter(Trip.bookings.any())
        .order_by(Trip.created_at.asc())
        .all()
    )
    return [_to_trip_out(t) for t in trips]


@router.patch("/trips/{trip_id}/driver", response_model=TripOut)
def assign_driver(
    trip_id: uuid.UUID,
    payload: TripAssignDriver,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    trip = _load_trip(db, trip_id)

    driver = db.get(User, payload.driver_id)
    if driver is None or driver.role != UserRole.driver:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="driver_id must belong to a user with role=driver",
        )

    trip.driver_id = driver.id
    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip)


@router.patch("/trips/{trip_id}/status", response_model=TripOut)
def update_trip_status(
    trip_id: uuid.UUID,
    payload: TripStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trip = _load_trip(db, trip_id)

    is_staff = current_user.role in (UserRole.admin, UserRole.dispatcher)
    is_assigned_driver = (
        current_user.role == UserRole.driver and trip.driver_id == current_user.id
    )
    if not (is_staff or is_assigned_driver):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff or this trip's assigned driver can update its status",
        )

    if payload.status not in ALLOWED_TRANSITIONS.get(trip.status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot move trip from {trip.status.value} to {payload.status.value}",
        )

    trip.status = payload.status

    # A completed or cancelled trip releases its vehicle. Without this, a
    # vehicle stays marked on_trip forever after finishing, which means
    # it can never be picked for the next outbound run OR offered as a
    # returning vehicle for someone else's return leg — silently shrinking
    # the usable fleet over the course of a day.
    if (
        payload.status in (TripStatus.completed, TripStatus.cancelled)
        and trip.vehicle_id is not None
    ):
        still_committed = (
            db.query(Trip)
            .filter(Trip.vehicle_id == trip.vehicle_id)
            .filter(Trip.id != trip.id)
            .filter(
                Trip.status.in_(
                    [
                        TripStatus.sealed,
                        TripStatus.assigned,
                        TripStatus.in_progress,
                        TripStatus.reassigning,
                    ]
                )
            )
            .first()
        )
        if still_committed is None:
            vehicle = db.get(Vehicle, trip.vehicle_id)
            if vehicle is not None and vehicle.status == VehicleStatus.on_trip:
                vehicle.status = VehicleStatus.available

    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip)
