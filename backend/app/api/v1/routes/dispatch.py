import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_role
from app.core.dispatch_config import MAX_PASSENGERS
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import (
    BookingStatus,
    DispatchEventType,
    TripStatus,
    UserRole,
    VehicleStatus,
)
from app.models.trip import Trip
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.trip import (
    AttentionItem,
    MatchingRunResult,
    MergeTripsResult,
    TripAssignDriver,
    TripOut,
    TripStatusUpdate,
)
from app.services.audit import log_pii_access
from app.services.booking_service import to_booking_out
from app.services.dispatch_engine import SealDecision, evaluate_pool
from app.services.dispatch_service import (
    merge_trips,
    seal_trip,
    log_event,
    pool_snapshot,
    release_vehicle_if_free,
    run_dispatch_cycle,
)
from app.services.notification_service import notify_driver_assigned

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
        completed_at=trip.completed_at,
        cancelled_at=trip.cancelled_at,
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
        .filter(Trip.status.notin_([TripStatus.completed, TripStatus.cancelled]))
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


@router.get("/history", response_model=list[TripOut])
def trip_history(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Past rides — every completed or cancelled trip. Requested alongside
    the fact that customers and vehicles are never deleted after a ride
    finishes: this is where that history actually becomes visible,
    instead of just sitting unreachable in the database.
    """
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer))
        .filter(Trip.status.in_([TripStatus.completed, TripStatus.cancelled]))
        .filter(Trip.bookings.any())
        .order_by(
            Trip.completed_at.desc().nullslast(), Trip.cancelled_at.desc().nullslast()
        )
        .limit(min(limit, 300))
        .all()
    )
    for trip in trips:
        for booking in trip.bookings:
            log_pii_access(
                db,
                actor_user_id=current_user.id,
                action="read_trip_history",
                target_type="customer",
                target_id=booking.customer_id,
            )
    db.commit()
    return [_to_trip_out(t) for t in trips]


@router.get("/my-history", response_model=list[TripOut])
def my_trip_history(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.driver)),
):
    """Same as /history, scoped to trips this driver actually drove."""
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer))
        .filter(Trip.driver_id == current_user.id)
        .filter(Trip.status.in_([TripStatus.completed, TripStatus.cancelled]))
        .filter(Trip.bookings.any())
        .order_by(
            Trip.completed_at.desc().nullslast(), Trip.cancelled_at.desc().nullslast()
        )
        .limit(min(limit, 300))
        .all()
    )
    return [_to_trip_out(t) for t in trips]


@router.get("/attention", response_model=list[AttentionItem])
def list_attention_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Pools that need a human decision right now. Before this endpoint,
    escalation decisions were written to the audit log and never shown
    to anyone — a dispatcher had no way to know a booking needed a phone
    call instead of an algorithm.
    """
    now = datetime.now(timezone.utc)
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer))
        .filter(Trip.status == TripStatus.forming)
        .filter(Trip.bookings.any())
        .all()
    )
    any_vehicle_available = (
        db.query(Vehicle).filter(Vehicle.status == VehicleStatus.available).first()
        is not None
    )

    items: list[AttentionItem] = []
    for trip in trips:
        active = [
            b for b in trip.bookings if b.status.value not in ("cancelled", "no_show")
        ]
        if not active:
            continue

        snap = pool_snapshot(trip)
        decision = evaluate_pool(snap, now)
        overdue = (
            max(0.0, (now - trip.departure_deadline).total_seconds() / 60)
            if trip.departure_deadline
            else 0.0
        )

        if decision.decision is SealDecision.ESCALATE:
            items.append(
                AttentionItem(
                    kind="escalated",
                    trip_id=trip.id,
                    direction=trip.direction.value,
                    passenger_count=len(active),
                    minutes_overdue=overdue,
                    reason=decision.reason,
                    options=decision.options,
                    bookings=[to_booking_out(b) for b in active],
                )
            )
        elif (
            decision.decision is SealDecision.SEAL
            and trip.vehicle_id is None
            and not any_vehicle_available
        ):
            items.append(
                AttentionItem(
                    kind="no_vehicle",
                    trip_id=trip.id,
                    direction=trip.direction.value,
                    passenger_count=len(active),
                    minutes_overdue=overdue,
                    reason="Sẵn sàng chạy nhưng đội xe đã kín",
                    options=None,
                    bookings=[to_booking_out(b) for b in active],
                )
            )

    return items


@router.post("/trips/{trip_id}/seal", response_model=TripOut)
def forceseal_trip(
    trip_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Manual override: seal a forming pool right now, bypassing the
    deadline and minimum-passenger checks. No automated system gets
    every case right on day one — an operator who cannot override it
    will stop trusting it.
    """
    trip = _load_trip(db, trip_id)
    if trip.status != TripStatus.forming:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trip is {trip.status.value}, not forming — nothing to seal",
        )
    active = [b for b in trip.bookings if b.status.value not in ("cancelled", "no_show")]
    if not active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Trip has no active bookings"
        )

    vehicle = seal_trip(
        db, trip, datetime.now(timezone.utc), reason="manually sealed by dispatcher"
    )
    if vehicle is None:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No vehicle available to seal this trip",
        )

    log_event(
        db,
        DispatchEventType.manual_override,
        trip_id=trip.id,
        actor_user_id=current_user.id,
        reason="dispatcher forced seal ahead of schedule",
    )
    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip)


@router.post("/trips/{source_id}/merge/{target_id}", response_model=MergeTripsResult)
def forcemerge_trips(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """Manual override: combine two forming pools into one car."""
    if source_id == target_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot merge a trip into itself")

    source = _load_trip(db, source_id)
    target = _load_trip(db, target_id)

    for t, label in ((source, "Source"), (target, "Target")):
        if t.status != TripStatus.forming:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} trip is {t.status.value}, not forming",
            )
    if source.direction != target.direction:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge trips going different directions",
        )

    source_active = [b for b in source.bookings if b.status.value not in ("cancelled", "no_show")]
    target_active = [b for b in target.bookings if b.status.value not in ("cancelled", "no_show")]
    if len(source_active) + len(target_active) > MAX_PASSENGERS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Combined would exceed {MAX_PASSENGERS} seats",
        )

    merge_trips(
        db,
        source,
        target,
        reason="manually merged by dispatcher",
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(target)
    return MergeTripsResult(target=_to_trip_out(target))


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
    # Riders were told a vehicle was coming when the trip sealed; now
    # tell them who's actually driving.
    notify_driver_assigned(db, trip, driver.full_name)
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

    if payload.status == TripStatus.completed:
        trip.completed_at = datetime.now(timezone.utc)
        # Previously only the TRIP's status flipped to completed — every
        # booking inside it stayed stuck at locked/onboard forever, which
        # is what made a real ride-history view impossible: nothing was
        # ever actually marked as a finished ride from the customer's
        # side. Cascade it here, once, rather than requiring a separate
        # per-passenger dropoff-confirmation flow that doesn't exist yet.
        for b in trip.bookings:
            if b.status.value not in ("cancelled", "no_show"):
                b.status = BookingStatus.completed

    elif payload.status == TripStatus.cancelled:
        trip.cancelled_at = datetime.now(timezone.utc)
        for b in trip.bookings:
            if b.status.value not in ("cancelled", "no_show", "completed"):
                b.status = BookingStatus.cancelled

    if payload.status in (TripStatus.completed, TripStatus.cancelled):
        release_vehicle_if_free(db, trip)

    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip)
