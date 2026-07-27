import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.booking import Booking
from app.models.corridor import Corridor
from app.models.enums import (
    BookingDirection,
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
    TripExtendWait,
    TripOut,
    TripRejectAssignment,
    TripRejectCompletion,
    TripReportIssue,
)
from app.services.audit import log_pii_access
from app.services.booking_service import to_booking_out
from app.services.dispatch_engine import SealDecision, evaluate_pool
from app.services.dispatch_service import (
    extend_pool_wait,
    merge_trips,
    report_trip_disrupted,
    seal_trip,
    log_event,
    pool_snapshot,
    release_vehicle_if_free,
    run_dispatch_cycle,
    trip_capacity,
    upgrade_to_private,
)
from app.services.notification_service import notify_driver_assigned
from app.core.dispatch_config import (
    IDLE_AWAY_ATTENTION_MINUTES,
    IDLE_AWAY_RETURN_MINUTES,
)
from app.services.vehicle_return import idle_away_from_base
from app.services.trip_state import (
    DRIVER_ACTIVE_STATUSES,
    TransitionError,
    TransitionForbidden,
    allowed_transitions,
    apply_transition,
    check_transition,
)

router = APIRouter(tags=["dispatch"])

# The transition table used to live here, and described a workflow the
# service layer didn't follow — it claimed `forming -> sealed ->
# assigned` while seal_trip jumped straight to `assigned`, and it was
# consulted by exactly one of the eight places that wrote trip.status.
# It now lives in app/services/trip_state.py, which every status write
# goes through. See docs/STATE_MACHINE.md.


def _http_error(exc: TransitionError) -> HTTPException:
    """Translate the service layer's refusal into the right status code.
    The service layer stays free of FastAPI so it can be unit-tested
    without one."""
    return HTTPException(
        status_code=(
            status.HTTP_403_FORBIDDEN
            if isinstance(exc, TransitionForbidden)
            else status.HTTP_400_BAD_REQUEST
        ),
        detail=str(exc),
    )


# A trip that's over is a historical record — it should still show who
# cancelled or no-showed, because that IS what happened on that trip.
# A trip that's still live is an operating instruction, and someone who
# cancelled is simply not on it any more.
FINISHED_TRIP_STATUSES = (TripStatus.completed, TripStatus.cancelled)

# A driver can be put on a trip only while it is still waiting to depart
# or looking for a replacement car. Not once it is rolling, and
# certainly not once it is over.
DRIVER_ASSIGNABLE_STATUSES = (
    TripStatus.forming,
    TripStatus.sealed,
    TripStatus.assigned,
    TripStatus.driver_accepted,
    TripStatus.reassigning,
)


def _to_trip_out(trip: Trip, actor: User | None = None) -> TripOut:
    """
    Serialize a trip for the API.

    Cancelled and no-show riders are dropped from a LIVE trip. Leaving
    them in meant the driver's stop list still showed someone who had
    cancelled (so the car would drive to a pickup nobody was waiting
    at), and every UI that sums over trip.bookings — seat occupancy,
    expected revenue — counted them too.

    `actor` decides what goes in `available_actions`: the same
    transition table the write path enforces, so a client never renders
    a button the server would reject.
    """
    if trip.status in FINISHED_TRIP_STATUSES:
        relevant = list(trip.bookings)
    else:
        relevant = [
            b
            for b in trip.bookings
            if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
        ]

    return TripOut(
        id=trip.id,
        status=trip.status,
        driver_id=trip.driver_id,
        vehicle_id=trip.vehicle_id,
        vehicle_label=trip.vehicle_label,
        is_private=len(relevant) == 1 and relevant[0].is_private,
        bookings=[to_booking_out(b, actor) for b in relevant],
        created_at=trip.created_at,
        completed_at=trip.completed_at,
        cancelled_at=trip.cancelled_at,
        driver_accepted_at=trip.driver_accepted_at,
        completion_requested_at=trip.completion_requested_at,
        finalized_at=trip.finalized_at,
        finalized_by_user_id=trip.finalized_by_user_id,
        available_actions=(
            sorted(allowed_transitions(trip.status, actor), key=lambda s: s.value)
            if actor is not None
            else []
        ),
    )


def _load_trip(db: Session, trip_id: uuid.UUID) -> Trip:
    trip = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer), joinedload(Trip.bookings).joinedload(Booking.payment))
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
        .options(joinedload(Trip.bookings).joinedload(Booking.customer), joinedload(Trip.bookings).joinedload(Booking.payment))
        .filter(
            Trip.status.in_(
                [TripStatus.sealed, TripStatus.assigned, TripStatus.driver_accepted]
            )
        )
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

    trips_out = [_to_trip_out(t, current_user) for t in full_trips]
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
        .options(joinedload(Trip.bookings).joinedload(Booking.customer), joinedload(Trip.bookings).joinedload(Booking.payment))
        .filter(Trip.bookings.any())
        .filter(Trip.status.notin_([TripStatus.completed, TripStatus.cancelled]))
        .order_by(Trip.created_at.desc())
        .all()
    )
    return [_to_trip_out(t, current_user) for t in trips]


@router.get("/my-trips", response_model=list[TripOut])
def my_trips(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.driver)),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer), joinedload(Trip.bookings).joinedload(Booking.payment))
        .filter(Trip.driver_id == current_user.id)
        .filter(Trip.status.in_(DRIVER_ACTIVE_STATUSES))
        .filter(Trip.bookings.any())
        .order_by(Trip.created_at.asc())
        .all()
    )
    return [_to_trip_out(t, current_user) for t in trips]


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
        .options(joinedload(Trip.bookings).joinedload(Booking.customer), joinedload(Trip.bookings).joinedload(Booking.payment))
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
    return [_to_trip_out(t, current_user) for t in trips]


@router.get("/my-history", response_model=list[TripOut])
def my_trip_history(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.driver)),
):
    """Same as /history, scoped to trips this driver actually drove."""
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.bookings).joinedload(Booking.customer), joinedload(Trip.bookings).joinedload(Booking.payment))
        .filter(Trip.driver_id == current_user.id)
        .filter(Trip.status.in_([TripStatus.completed, TripStatus.cancelled]))
        .filter(Trip.bookings.any())
        .order_by(
            Trip.completed_at.desc().nullslast(), Trip.cancelled_at.desc().nullslast()
        )
        .limit(min(limit, 300))
        .all()
    )
    return [_to_trip_out(t, current_user) for t in trips]


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
        .options(joinedload(Trip.bookings).joinedload(Booking.customer), joinedload(Trip.bookings).joinedload(Booking.payment))
        .filter(Trip.status == TripStatus.forming)
        .filter(Trip.bookings.any())
        .all()
    )
    items: list[AttentionItem] = []
    for trip in trips:
        active = [
            b for b in trip.bookings if b.status.value not in ("cancelled", "no_show")
        ]
        if not active:
            continue

        snap = pool_snapshot(trip, db)
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
                    bookings=[to_booking_out(b, current_user) for b in active],
                )
            )

    # Pools that already decided to depart and are waiting on a car.
    # This used to be inferred by re-running evaluate_pool over every
    # forming pool and cross-checking the fleet on each request; it is
    # now simply a stored status, which is the whole reason `sealed`
    # was made reachable.
    awaiting_vehicle = (
        db.query(Trip)
        .options(
            joinedload(Trip.bookings).joinedload(Booking.customer),
            joinedload(Trip.bookings).joinedload(Booking.payment),
        )
        .filter(Trip.status == TripStatus.sealed)
        .filter(Trip.vehicle_id.is_(None))
        .filter(Trip.bookings.any())
        .all()
    )
    for trip in awaiting_vehicle:
        active = [
            b for b in trip.bookings if b.status.value not in ("cancelled", "no_show")
        ]
        if not active:
            continue
        overdue = (
            max(0.0, (now - trip.departure_deadline).total_seconds() / 60)
            if trip.departure_deadline
            else 0.0
        )
        items.append(
            AttentionItem(
                kind="no_vehicle",
                trip_id=trip.id,
                direction=trip.direction.value,
                passenger_count=len(active),
                minutes_overdue=overdue,
                reason="Sẵn sàng chạy nhưng đội xe đã kín",
                options=None,
                bookings=[to_booking_out(b, current_user) for b in active],
            )
        )

    # Trips a driver reported disrupted (see report_trip_disrupted) that
    # couldn't find a replacement vehicle right away — the automatic
    # cycle keeps retrying these every tick, but a dispatcher needs to
    # see them in the meantime, same as any other no_vehicle situation.
    disrupted_trips = (
        db.query(Trip)
        .options(
            joinedload(Trip.bookings).joinedload(Booking.customer),
            joinedload(Trip.bookings).joinedload(Booking.payment),
        )
        .filter(Trip.status == TripStatus.reassigning)
        .filter(Trip.vehicle_id.is_(None))
        .filter(Trip.bookings.any())
        .all()
    )
    # Free cars parked away from base. Nothing surfaced these before:
    # a car that finished in Hà Nội at 09:00 simply sat there, its
    # driver looking at an empty screen, until the end-of-day sweep at
    # 22:00 — and the one person who could have decided otherwise was
    # never asked. Raised well before the automatic send-home so a
    # dispatcher who knows a return fare is coming can hold the car.
    for vehicle, idle_minutes in idle_away_from_base(
        db, IDLE_AWAY_ATTENTION_MINUTES
    ):
        items.append(
            AttentionItem(
                kind="idle_away",
                vehicle_id=vehicle.id,
                vehicle_label=vehicle.label or vehicle.plate_number,
                minutes_overdue=round(idle_minutes),
                reason=(
                    f"Xe đang rảnh ngoài Bắc Giang {round(idle_minutes)} phút — "
                    f"tự động gọi về sau {IDLE_AWAY_RETURN_MINUTES} phút"
                ),
            )
        )

    for trip in disrupted_trips:
        active = [
            b for b in trip.bookings if b.status.value not in ("cancelled", "no_show")
        ]
        if not active:
            continue
        items.append(
            AttentionItem(
                kind="vehicle_down",
                trip_id=trip.id,
                direction=trip.direction.value,
                passenger_count=len(active),
                minutes_overdue=0.0,
                reason="Xe gặp sự cố, đang chờ xe thay thế",
                options=None,
                bookings=[to_booking_out(b, current_user) for b in active],
            )
        )

    return items


@router.post("/trips/{trip_id}/extend-wait", response_model=TripOut)
def extend_wait(
    trip_id: uuid.UUID,
    payload: TripExtendWait,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Escalation outcome: the dispatcher phoned the waiting customer(s),
    they're happy to wait a bit longer, so give the pool more time
    rather than cancelling it.

    There is no customer-facing channel in this system — offers like
    this are made by phone (see notification_service's module docstring);
    this endpoint records the outcome of that call.
    """
    trip = _load_trip(db, trip_id)
    if trip.status != TripStatus.forming:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trip is {trip.status.value}, not forming — nothing to extend",
        )

    extend_pool_wait(
        db, trip, payload.extra_minutes, actor_user_id=current_user.id
    )
    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip, current_user)


@router.post("/trips/{trip_id}/upgrade-private", response_model=TripOut)
def upgrade_private(
    trip_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Escalation outcome: the lone passenger agreed on the phone to take
    the car as a private hire instead of waiting for companions who
    aren't coming. Re-prices at the private rate and departs.
    """
    trip = _load_trip(db, trip_id)
    if trip.status != TripStatus.forming:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trip is {trip.status.value}, not forming — cannot upgrade",
        )

    try:
        vehicle = upgrade_to_private(db, trip, actor_user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    if vehicle is None:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Khách đã đồng ý bao xe nhưng hiện không còn xe trống",
        )

    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip, current_user)


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
    return _to_trip_out(trip, current_user)


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
    # Seats, not booking rows — and against the target's real capacity,
    # since that's the car the merged group actually travels in.
    combined_seats = sum(b.seats or 1 for b in source_active + target_active)
    capacity = trip_capacity(db, target)
    if combined_seats > capacity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Combined would need {combined_seats} seats, car holds {capacity}",
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
    return MergeTripsResult(target=_to_trip_out(target, current_user))


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

    # This endpoint previously had no status check at all — a driver
    # could be assigned to a trip that had already finished, been
    # cancelled, or was halfway down the road with someone else driving.
    if trip.status not in DRIVER_ASSIGNABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Trip is {trip.status.value} — a driver can only be assigned "
                "before the trip departs"
            ),
        )

    # Swapping the driver on a trip the previous driver had already
    # accepted invalidates that acceptance: the new driver has agreed to
    # nothing yet. Drop back to `assigned` so they get the same
    # accept/reject choice anyone else would.
    if trip.status is TripStatus.driver_accepted and trip.driver_id != driver.id:
        try:
            apply_transition(
                db,
                trip,
                TripStatus.assigned,
                actor=current_user,
                reason="reassigned to a different driver",
            )
        except TransitionError as exc:
            raise _http_error(exc)
        trip.driver_accepted_at = None

    trip.driver_id = driver.id
    # Riders were told a vehicle was coming when the trip sealed; now
    # tell them who's actually driving.
    notify_driver_assigned(db, trip, driver.full_name)
    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip, current_user)


def _apply_side_effects(
    db: Session, trip: Trip, new_status: TripStatus, actor: User
) -> None:
    """
    What has to happen to the world outside the trip row once it moves.

    Booking cascades and timestamps belong to the transition itself and
    live in trip_state; this is the part that touches vehicles.
    """
    if new_status is TripStatus.in_progress:
        # The car is now genuinely out with passengers, not just
        # earmarked at the hub.
        if trip.vehicle_id is not None:
            vehicle = db.get(Vehicle, trip.vehicle_id)
            if vehicle is not None and vehicle.status is VehicleStatus.assigned:
                vehicle.status = VehicleStatus.on_trip

    elif new_status is TripStatus.completed:
        _capture_final_location(db, trip)
        release_vehicle_if_free(db, trip)

    elif new_status is TripStatus.cancelled:
        release_vehicle_if_free(db, trip)


def _capture_final_location(db: Session, trip: Trip) -> None:
    """
    Where the car ended up — written at FINALIZATION, not when the
    driver says they're done. A completion is a claim until a dispatcher
    confirms it, and the fleet's picture of where its cars are should be
    built from confirmed facts.

    Falls back to the corridor's destination hub when every booking
    ended cancelled/no-show. The old code skipped the write entirely in
    that case, leaving the car pinned to wherever it started while it
    was in fact sitting at the other end of the corridor — and
    _assign_vehicle would then keep choosing it for trips near a place
    it had already driven away from.
    """
    if trip.vehicle_id is None:
        return
    vehicle = db.get(Vehicle, trip.vehicle_id)
    if vehicle is None:
        return

    active = [
        b for b in trip.bookings if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
    ]
    if active:
        last_stop = max(active, key=lambda b: (b.stop_order or 0))
        point = to_shape(last_stop.dropoff_point)
        lng, lat = point.x, point.y
    else:
        corridor = db.get(Corridor, trip.corridor_id)
        if corridor is None:
            return
        # Outbound ends at the away hub; a return leg ends back at base.
        if trip.direction is BookingDirection.return_leg:
            lat, lng = corridor.home_hub_lat, corridor.home_hub_lng
        else:
            lat, lng = corridor.away_hub_lat, corridor.away_hub_lng

    vehicle.last_location = WKTElement(f"POINT({lng} {lat})", srid=4326)
    vehicle.last_location_at = datetime.now(timezone.utc)


def _advance(
    db: Session,
    trip: Trip,
    to_status: TripStatus,
    actor: User,
    event: DispatchEventType,
    reason: str,
) -> TripOut:
    """
    Shared body for every named workflow action below.

    Each one is the same three steps — move the trip, apply the
    vehicle-side effects, write the audit event — differing only in
    which transition and which event type. Writing them out six times
    is how the old code ended up with a completion path that cascaded
    booking statuses and a cancellation path that forgot to.
    """
    try:
        apply_transition(db, trip, to_status, actor=actor, reason=reason)
    except TransitionError as exc:
        raise _http_error(exc)

    _apply_side_effects(db, trip, to_status, actor)
    log_event(db, event, trip_id=trip.id, actor_user_id=actor.id, reason=reason)

    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip, actor)


# --- The driver's half of the workflow --------------------------------
#
# None of these carry a `require_role` dependency. The role check lives
# in the transition table, which is also what the write path enforces —
# adding a second check here would be a second source of truth, and the
# two would eventually disagree. A dispatcher calling /start gets a 403
# from apply_transition, not from a decorator.


@router.post("/trips/{trip_id}/accept", response_model=TripOut)
def accept_trip(
    trip_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver acknowledges an assignment. Only the assigned driver."""
    trip = _load_trip(db, trip_id)
    return _advance(
        db,
        trip,
        TripStatus.driver_accepted,
        current_user,
        DispatchEventType.driver_accepted,
        "driver accepted the assignment",
    )


@router.post("/trips/{trip_id}/start", response_model=TripOut)
def start_trip(
    trip_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Driver presses Start Trip. Dispatchers and admins are refused —
    this endpoint and the board button that used to call it were the
    concrete way the role boundary was being violated.
    """
    trip = _load_trip(db, trip_id)
    return _advance(
        db,
        trip,
        TripStatus.in_progress,
        current_user,
        DispatchEventType.trip_started,
        "driver started the trip",
    )


@router.post("/trips/{trip_id}/request-completion", response_model=TripOut)
def request_completion(
    trip_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Driver presses Complete Trip. This does NOT complete the trip — it
    raises a finalization request for a dispatcher to review. The
    vehicle stays `on_trip` and its location is not updated until
    someone signs off.
    """
    trip = _load_trip(db, trip_id)
    return _advance(
        db,
        trip,
        TripStatus.completion_requested,
        current_user,
        DispatchEventType.completion_requested,
        "driver reported the trip finished",
    )


@router.post("/trips/{trip_id}/reject", response_model=TripOut)
def reject_assignment(
    trip_id: uuid.UUID,
    payload: TripRejectAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Driver declines a trip, or stands down from one they had accepted.

    Deliberately the same machinery as a breakdown report: the
    passengers, route and ETAs all survive, and the system starts
    hunting for a replacement car immediately rather than dropping the
    trip on a dispatcher's desk.
    """
    trip = _load_trip(db, trip_id)

    try:
        check_transition(trip, TripStatus.reassigning, current_user)
    except TransitionError as exc:
        raise _http_error(exc)

    report_trip_disrupted(
        db,
        trip,
        reason=payload.reason,
        notes=payload.notes,
        actor=current_user,
    )
    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip, current_user)


# --- The dispatcher's ruling ------------------------------------------


@router.post("/trips/{trip_id}/finalize", response_model=TripOut)
def finalize_trip(
    trip_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Dispatcher confirms the driver's completion claim. This is the only
    way a trip reaches `completed`.

    Finalizing is what updates the vehicle's location to where it
    actually finished and returns it to the available pool — see
    _capture_final_location. A car that finishes in Hà Nội at 08:29 is
    an available Hà Nội car from 08:29.
    """
    trip = _load_trip(db, trip_id)
    return _advance(
        db,
        trip,
        TripStatus.completed,
        current_user,
        DispatchEventType.trip_finalized,
        "dispatcher finalized the trip",
    )


@router.post("/trips/{trip_id}/reject-completion", response_model=TripOut)
def reject_completion(
    trip_id: uuid.UUID,
    payload: TripRejectCompletion,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Dispatcher sends a completion claim back: the trip isn't actually
    finished. It returns to `in_progress` with its passengers still
    aboard, the vehicle still `on_trip`, and no location captured —
    nothing about the claim is treated as fact.
    """
    trip = _load_trip(db, trip_id)
    return _advance(
        db,
        trip,
        TripStatus.in_progress,
        current_user,
        DispatchEventType.completion_rejected,
        payload.reason,
    )


@router.post("/trips/{trip_id}/report-issue", response_model=TripOut)
def report_issue(
    trip_id: uuid.UUID,
    payload: TripReportIssue,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    A driver (or staff, on a driver's behalf) reports a trip can't
    continue as assigned — breakdown, accident, or otherwise. See
    dispatch_service.py:report_trip_disrupted for what this actually
    does: it doesn't just flip a status, it tries to recover the trip
    onto a different vehicle immediately, keeping the same route and
    passengers.
    """
    trip = _load_trip(db, trip_id)

    # Who may do this, and from which states, both come from the
    # transition table — including the rule that a driver may only touch
    # their own trip. The hand-rolled `is_staff or is_assigned_driver`
    # check that used to sit here was a second copy of that rule.
    try:
        check_transition(trip, TripStatus.reassigning, current_user)
    except TransitionError as exc:
        raise _http_error(exc)

    report_trip_disrupted(
        db,
        trip,
        reason=payload.reason,
        notes=payload.notes,
        actor=current_user,
    )
    db.commit()
    db.refresh(trip)
    return _to_trip_out(trip, current_user)
