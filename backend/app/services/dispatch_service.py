"""
Connects the pure matching/dispatch algorithms to the database.

The algorithm modules (pool_insertion, dispatch_engine) are deliberately
free of SQLAlchemy so they stay testable without a database. This module
is the only place that translates between ORM rows and those pure
dataclasses, and the only place that writes dispatch decisions.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dispatch_config import (
    MAX_PASSENGERS,
    MAX_POOL_WAIT_MINUTES,
    PICKUP_WINDOW_MINUTES,
    RETURN_VEHICLE_LATE_TOLERANCE_MINUTES,
    RETURN_VEHICLE_MATCH_WINDOW_MINUTES,
)
from app.models.booking import Booking
from app.models.dispatch_event import DispatchEvent
from app.models.enums import (
    BookingDirection,
    BookingStatus,
    DispatchEventType,
    TripStatus,
    VehicleStatus,
)
from app.models.trip import Trip
from app.models.vehicle import Vehicle
from app.services.dispatch_engine import (
    PoolSnapshot,
    SealDecision,
    departure_deadline,
    evaluate_pool,
    find_merge_candidate,
)
from app.services.pool_insertion import (
    PoolMember,
    compute_solo_baseline,
    evaluate_insertion,
)
from app.services.routing import routing_service
from app.services.notification_service import notify_trip_sealed

logger = logging.getLogger(__name__)

# Pools whose centroid is further than this from the booking are not
# worth evaluating. Runs as an indexed PostGIS query, so it costs
# nothing compared to a routing call.
CANDIDATE_RADIUS_METERS = 30_000


def _coords(booking: Booking) -> tuple[tuple[float, float], tuple[float, float]]:
    p = to_shape(booking.pickup_point)
    d = to_shape(booking.dropoff_point)
    return (p.y, p.x), (d.y, d.x)


def _to_member(booking: Booking) -> PoolMember:
    pickup, dropoff = _coords(booking)
    return PoolMember(
        booking_id=booking.id,
        pickup=pickup,
        dropoff=dropoff,
        requested_pickup_at=booking.requested_pickup_at,
        solo_duration_seconds=booking.solo_duration_seconds or 0.0,
    )


def log_event(
    db: Session,
    event_type: DispatchEventType,
    *,
    trip_id: UUID | None = None,
    booking_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    reason: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        DispatchEvent(
            event_type=event_type,
            trip_id=trip_id,
            booking_id=booking_id,
            vehicle_id=vehicle_id,
            actor_user_id=actor_user_id,
            is_automatic=actor_user_id is None,
            reason=reason,
            details=details,
        )
    )


def ensure_baseline(db: Session, booking: Booking) -> None:
    """
    Computes and stores the solo trip baseline if missing. Idempotent —
    the address pair never changes, so this runs once per booking.
    """
    if booking.solo_duration_seconds is not None:
        return
    pickup, dropoff = _coords(booking)
    leg = routing_service.leg(pickup, dropoff)
    booking.solo_duration_seconds = leg.duration_seconds
    booking.solo_distance_meters = leg.distance_meters


def _refresh_pool_geometry(db: Session, trip: Trip) -> None:
    """Recomputes centroid, deadline, and cached route after a change."""
    active = [
        b
        for b in trip.bookings
        if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
    ]
    if not active:
        return

    pickups = [_coords(b)[0] for b in active]
    lat = sum(p[0] for p in pickups) / len(pickups)
    lng = sum(p[1] for p in pickups) / len(pickups)
    trip.centroid = WKTElement(f"POINT({lng} {lat})", srid=4326)

    earliest = min(b.requested_pickup_at for b in active)
    trip.departure_deadline = earliest + timedelta(minutes=MAX_POOL_WAIT_MINUTES)

    members = [_to_member(b) for b in active]
    if len(members) == 1:
        m = members[0]
        route = routing_service.route([m.pickup, m.dropoff])
    else:
        # Reuse the insertion evaluator's ordering for a consistent route.
        result = evaluate_insertion(members[:-1], members[-1])
        if result.feasible and result.ordered_stops:
            route = routing_service.route([s.coord for s in result.ordered_stops])
            for rank, stop in enumerate(
                [s for s in result.ordered_stops if s.kind == "pickup"], start=1
            ):
                for b in active:
                    if b.id == stop.booking_id:
                        b.stop_order = rank
        else:
            route = routing_service.route(
                [c for m in members for c in (m.pickup, m.dropoff)]
            )

    trip.route_distance_meters = route.total_distance_meters
    trip.route_duration_seconds = route.total_duration_seconds
    trip.route_geometry = route.geometry
    trip.route_is_estimate = route.is_estimate


def find_pool_for_booking(db: Session, booking: Booking) -> Trip | None:
    """
    The core of continuous matching: try to place this booking into an
    already-forming pool before opening a new one.

    The previous design could not do this at all — pools were built in
    one batch pass and frozen, so a booking arriving a minute later
    started a second car even when it fit the first perfectly.
    """
    ensure_baseline(db, booking)
    candidate = _to_member(booking)

    window = timedelta(minutes=PICKUP_WINDOW_MINUTES)
    pickup, _ = _coords(booking)
    point = WKTElement(f"POINT({pickup[1]} {pickup[0]})", srid=4326)

    # Cheap, indexed prefilter — direction, status, time window, and
    # coarse proximity — before spending a single routing call.
    stmt = (
        select(Trip)
        .where(Trip.status == TripStatus.forming)
        .where(Trip.direction == booking.direction)
        .where(
            (Trip.departure_deadline.is_(None))
            | (Trip.departure_deadline >= booking.requested_pickup_at - window)
        )
        .where(
            (Trip.centroid.is_(None))
            | (func.ST_DWithin(Trip.centroid, point, CANDIDATE_RADIUS_METERS))
        )
    )
    pools = db.execute(stmt).scalars().all()

    best_trip: Trip | None = None
    best_score = float("inf")
    best_reason = "no forming pools in range"

    for trip in pools:
        members = [
            _to_member(b)
            for b in trip.bookings
            if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
            and b.id != booking.id
        ]
        if len(members) >= MAX_PASSENGERS:
            continue
        if any(m.solo_duration_seconds <= 0 for m in members):
            continue  # baseline missing; skip rather than compute garbage

        result = evaluate_insertion(
            members, candidate, departure_deadline=trip.departure_deadline
        )
        if result.feasible and result.score is not None and result.score < best_score:
            best_trip, best_score = trip, result.score
        elif not result.feasible:
            best_reason = result.reason or best_reason

    if best_trip is None:
        logger.info("no pool for booking %s: %s", booking.id, best_reason)
        return None
    return best_trip


def find_returning_vehicle(db: Session, booking: Booking) -> Vehicle | None:
    """
    Prefers a vehicle already committed to the corresponding outbound run
    over dispatching (or waiting for) a separate car for a return booking.

    This is the core of return-trip optimization: a van doing
    Bắc Giang -> Hà Nội has to drive back to base whether or not it's
    carrying anyone, so a return passenger who fits its timing costs the
    business nothing extra. Before this, the system only ever asked "is
    any vehicle free right now" — it had no notion that a specific
    vehicle was about to become free AT THE PASSENGER'S ORIGIN, which
    meant it could open a second car (or leave the booking waiting) while
    a perfectly good one was minutes away.

    "Vehicle position" here is inferred, not GPS-tracked: it's the
    estimated dropoff time already computed for the outbound trip's last
    stop (see _apply_etas), which is the same estimate the customer was
    shown. There's no live telemetry in this system, so this is a
    forecast, not a fact — a badly delayed outbound run could make the
    van later than predicted. Good enough to prefer a real candidate over
    guessing blind, not a substitute for actual vehicle tracking.

    Only called for `direction == return_leg` bookings when no existing
    forming pool already fits (see assign_booking) — an outbound trip
    only becomes a candidate once nothing simpler works.
    """
    if booking.direction != BookingDirection.return_leg:
        return None

    outbound_trips = (
        db.execute(
            select(Trip)
            .where(Trip.direction == BookingDirection.outbound)
            .where(Trip.status.in_([TripStatus.assigned, TripStatus.in_progress]))
            .where(Trip.vehicle_id.isnot(None))
        )
        .scalars()
        .all()
    )
    if not outbound_trips:
        return None

    # A vehicle already earmarked for some OTHER forming/assigned return
    # trip must not be offered twice — that would double-book its return
    # leg to two different pools.
    reserved_vehicle_ids = {
        t.vehicle_id
        for t in db.execute(
            select(Trip)
            .where(Trip.direction == BookingDirection.return_leg)
            .where(
                Trip.status.in_(
                    [TripStatus.forming, TripStatus.assigned, TripStatus.in_progress]
                )
            )
            .where(Trip.vehicle_id.isnot(None))
        ).scalars()
    }

    best_vehicle: Vehicle | None = None
    best_gap_minutes: float | None = None

    for trip in outbound_trips:
        if trip.vehicle_id in reserved_vehicle_ids:
            continue

        arrivals = [
            b.estimated_dropoff_at for b in trip.bookings if b.estimated_dropoff_at
        ]
        if not arrivals:
            continue  # ETAs not yet computed for this trip; skip rather than guess

        estimated_arrival = max(arrivals)
        gap_minutes = (
            booking.requested_pickup_at - estimated_arrival
        ).total_seconds() / 60

        too_late = gap_minutes < -RETURN_VEHICLE_LATE_TOLERANCE_MINUTES
        too_early = gap_minutes > RETURN_VEHICLE_MATCH_WINDOW_MINUTES
        if too_late or too_early:
            continue

        if best_gap_minutes is None or abs(gap_minutes) < abs(best_gap_minutes):
            candidate = db.get(Vehicle, trip.vehicle_id)
            if candidate is not None and candidate.status == VehicleStatus.on_trip:
                best_vehicle = candidate
                best_gap_minutes = gap_minutes

    if best_vehicle is not None:
        logger.info(
            "return-leg booking %s matched to returning vehicle %s (gap %.0f min)",
            booking.id,
            best_vehicle.plate_number,
            best_gap_minutes,
        )
    return best_vehicle


def assign_booking(db: Session, booking: Booking) -> Trip:
    """Places a booking into the best pool, or opens a new one."""
    trip = find_pool_for_booking(db, booking)

    if trip is None:
        # For a return-leg booking with nowhere existing to go, check
        # whether a vehicle already out on the matching outbound run will
        # be free at roughly the right time — see find_returning_vehicle
        # for why this is worth doing before opening a fresh pool.
        returning_vehicle = find_returning_vehicle(db, booking)

        trip = Trip(
            direction=booking.direction,
            status=TripStatus.forming,
            departure_deadline=booking.requested_pickup_at
            + timedelta(minutes=MAX_POOL_WAIT_MINUTES),
        )
        if returning_vehicle is not None:
            trip.vehicle_id = returning_vehicle.id
            trip.vehicle_label = (
                returning_vehicle.label or returning_vehicle.plate_number
            )
            if returning_vehicle.default_driver_id:
                trip.driver_id = returning_vehicle.default_driver_id

        db.add(trip)
        db.flush()

        if returning_vehicle is not None:
            log_event(
                db,
                DispatchEventType.pool_created,
                trip_id=trip.id,
                booking_id=booking.id,
                vehicle_id=returning_vehicle.id,
                reason="matched to a vehicle already returning from its outbound run",
                details={"plate_number": returning_vehicle.plate_number},
            )
        else:
            log_event(
                db,
                DispatchEventType.pool_created,
                trip_id=trip.id,
                booking_id=booking.id,
                reason="no existing pool was a viable fit",
            )

    booking.trip_id = trip.id
    booking.status = BookingStatus.matched
    db.flush()

    _refresh_pool_geometry(db, trip)
    log_event(
        db,
        DispatchEventType.booking_pooled,
        trip_id=trip.id,
        booking_id=booking.id,
        details={"passengers": len(trip.bookings)},
    )
    return trip


def pool_snapshot(trip: Trip) -> PoolSnapshot:
    active = [
        b
        for b in trip.bookings
        if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
    ]
    earliest = (
        min(b.requested_pickup_at for b in active) if active else trip.created_at
    )
    return PoolSnapshot(
        pool_id=trip.id,
        direction=(
            "return" if trip.direction == BookingDirection.return_leg else "outbound"
        ),
        passenger_count=len(active),
        earliest_requested_pickup=earliest,
        created_at=trip.created_at,
        is_private=any(b.is_private for b in active),
    )


def _assign_vehicle(db: Session, trip: Trip) -> Vehicle | None:
    """
    Commits a physical car. Returns None when the fleet is fully
    committed — which the previous design could not even detect, since
    it had no concept of vehicles at all.
    """
    # A vehicle may already be earmarked for this trip — most notably by
    # find_returning_vehicle at pool-creation time, reserving a vehicle
    # still finishing its outbound run for this return leg. Re-searching
    # here instead of honoring that would silently discard a correct
    # reservation (the reserved vehicle isn't `available` yet — it's
    # still `on_trip` on its outbound leg — so a fresh search would skip
    # right past it) and hand the trip an unrelated vehicle.
    if trip.vehicle_id is not None:
        reserved = db.get(Vehicle, trip.vehicle_id)
        if reserved is not None and reserved.status in (
            VehicleStatus.available,
            VehicleStatus.on_trip,
        ):
            trip.vehicle_label = reserved.label or reserved.plate_number
            if trip.driver_id is None and reserved.default_driver_id:
                trip.driver_id = reserved.default_driver_id
            reserved.status = VehicleStatus.on_trip
            return reserved
        # Reservation no longer usable (e.g. pulled into maintenance
        # since being earmarked) — fall through to a fresh search rather
        # than blocking this trip's departure entirely.
        trip.vehicle_id = None

    vehicle = (
        db.execute(
            select(Vehicle)
            .where(Vehicle.status == VehicleStatus.available)
            .limit(1)
        )
        .scalars()
        .first()
    )
    if vehicle is None:
        return None

    vehicle.status = VehicleStatus.on_trip
    trip.vehicle_id = vehicle.id
    trip.vehicle_label = vehicle.label or vehicle.plate_number
    if trip.driver_id is None and vehicle.default_driver_id:
        trip.driver_id = vehicle.default_driver_id
    return vehicle


def _apply_etas(trip: Trip) -> None:
    """
    Writes firm pickup/dropoff estimates once a pool seals, so customers
    get a real time instead of silence.
    """
    active = sorted(
        [
            b
            for b in trip.bookings
            if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
        ],
        key=lambda b: (b.stop_order or 0),
    )
    if not active:
        return
    start = min(b.requested_pickup_at for b in active)
    per_stop = (trip.route_duration_seconds or 0) / max(1, len(active) * 2)
    for i, b in enumerate(active):
        b.estimated_pickup_at = start + timedelta(seconds=per_stop * i)
        b.estimated_dropoff_at = start + timedelta(
            seconds=(trip.route_duration_seconds or 0)
        )


def release_vehicle_if_free(db: Session, trip: Trip) -> None:
    """
    Frees a trip's vehicle back to `available` — but only if that vehicle
    isn't also committed to some OTHER still-active trip. Shared by trip
    completion/cancellation and by detach/no-show handling, so a vehicle
    can never get stuck permanently marked on_trip after it's actually
    done driving.
    """
    if trip.vehicle_id is None:
        return
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


def detach_booking_from_trip(
    db: Session,
    booking: Booking,
    new_status: BookingStatus,
    reason: str,
    actor_user_id: UUID | None = None,
) -> None:
    """
    Handles both cancellation and no-show — the two events a naive
    "just flip the status" implementation gets wrong. A booking leaving a
    trip mid-formation, or mid-route, has real consequences for everyone
    still in that car:

      - if it was the trip's only passenger, the trip and its vehicle
        reservation are released, not left dangling
      - if others remain, their route is re-optimized (stop order, ETAs)
        rather than driving to a stop that's no longer needed
    """
    old_trip = booking.trip
    booking.status = new_status
    booking.stop_order = None

    if old_trip is None:
        return

    remaining = [
        b
        for b in old_trip.bookings
        if b.id != booking.id
        and b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
    ]

    if not remaining:
        old_trip.status = TripStatus.cancelled
        release_vehicle_if_free(db, old_trip)
        log_event(
            db,
            DispatchEventType.trip_cancelled,
            trip_id=old_trip.id,
            booking_id=booking.id,
            actor_user_id=actor_user_id,
            reason=f"{reason} — last passenger removed, trip dissolved",
        )
        return

    _refresh_pool_geometry(db, old_trip)
    if old_trip.status in (TripStatus.assigned, TripStatus.in_progress):
        _apply_etas(old_trip)

    log_event(
        db,
        DispatchEventType.booking_removed,
        trip_id=old_trip.id,
        booking_id=booking.id,
        actor_user_id=actor_user_id,
        reason=reason,
        details={"remaining_passengers": len(remaining)},
    )


def seal_trip(
    db: Session, trip: Trip, now: datetime, reason: str
) -> Vehicle | None:
    """
    The actual seal action — commit a vehicle, lock the route, notify
    riders. Shared by the automatic dispatch cycle and the manual
    force-seal override, so both paths behave identically instead of
    the override being a second, subtly different implementation.
    """
    vehicle = _assign_vehicle(db, trip)
    if vehicle is None:
        log_event(
            db,
            DispatchEventType.pool_sealed,
            trip_id=trip.id,
            reason="ready to seal but no vehicle available",
        )
        return None

    trip.status = TripStatus.assigned
    trip.sealed_at = now
    _refresh_pool_geometry(db, trip)
    _apply_etas(trip)
    for b in trip.bookings:
        if b.status == BookingStatus.matched:
            b.status = BookingStatus.locked

    notify_trip_sealed(db, trip)

    log_event(
        db,
        DispatchEventType.pool_sealed,
        trip_id=trip.id,
        vehicle_id=vehicle.id,
        reason=reason,
        details={"passengers": len(trip.bookings)},
    )
    return vehicle


def merge_trips(
    db: Session,
    source: Trip,
    target: Trip,
    reason: str,
    actor_user_id: UUID | None = None,
) -> None:
    """Moves every active booking from `source` into `target`, dissolving
    `source`. Shared by automatic escalation-merge and the manual
    dispatcher override."""
    for b in list(source.bookings):
        if b.status not in (BookingStatus.cancelled, BookingStatus.no_show):
            b.trip_id = target.id
    source.status = TripStatus.cancelled
    db.flush()
    _refresh_pool_geometry(db, target)
    log_event(
        db,
        DispatchEventType.pool_merged,
        trip_id=target.id,
        actor_user_id=actor_user_id,
        reason=reason,
        details={"absorbed_pool": str(source.id)},
    )


def sweep_unmatched_bookings(db: Session) -> int:
    """
    Retries matching for any booking sitting queued with no trip.

    Without this, the ONLY moment a booking ever gets matched is at
    creation (see bookings.py's create route). If that initial match
    attempt failed — a routing hiccup, or simply no pool existed yet at
    that exact second — the booking would sit invisible forever, since
    the dispatch cycle previously only ever looked at pools that already
    existed. This closes that gap and is also what makes the manual
    "unassign" override actually useful: a booking sent back to `queued`
    needs somewhere that will pick it up again.
    """
    orphaned = (
        db.execute(
            select(Booking)
            .where(Booking.status == BookingStatus.queued)
            .where(Booking.trip_id.is_(None))
        )
        .scalars()
        .all()
    )
    matched = 0
    for booking in orphaned:
        try:
            assign_booking(db, booking)
            matched += 1
        except Exception:
            logger.exception(
                "sweep: matching failed for booking %s; will retry next cycle",
                booking.id,
            )
            db.rollback()
    return matched


def run_dispatch_cycle(db: Session, now: datetime | None = None) -> dict:
    """
    One automated pass: first retry any unmatched booking, then evaluate
    every forming pool for seal/escalate/merge. This is what removes the
    human from the loop — previously nothing was ever dispatched unless
    someone clicked a button, and unmatched bookings had no path back
    into the system at all.
    """
    now = now or datetime.now(timezone.utc)

    newly_matched = sweep_unmatched_bookings(db)

    trips = (
        db.execute(select(Trip).where(Trip.status == TripStatus.forming))
        .scalars()
        .all()
    )
    snapshots = {t.id: pool_snapshot(t) for t in trips}

    sealed = escalated = merged = 0
    no_vehicle = 0

    for trip in trips:
        snap = snapshots[trip.id]
        if snap.passenger_count == 0:
            continue

        decision = evaluate_pool(snap, now)

        if decision.decision is SealDecision.WAIT:
            continue

        if decision.decision is SealDecision.ESCALATE:
            others = [
                s
                for tid, s in snapshots.items()
                if tid != trip.id and s.passenger_count > 0
            ]
            partner = find_merge_candidate(snap, others)
            if partner is not None:
                partner_trip = next(t for t in trips if t.id == partner.pool_id)
                merge_trips(
                    db,
                    trip,
                    partner_trip,
                    reason=f"merged under-filled pool {trip.id} at deadline",
                )
                merged += 1
                continue

            log_event(
                db,
                DispatchEventType.pool_escalated,
                trip_id=trip.id,
                reason=decision.reason,
                details={"options": decision.options},
            )
            escalated += 1
            continue

        # SEAL
        vehicle = seal_trip(db, trip, now, decision.reason)
        if vehicle is None:
            no_vehicle += 1
        else:
            sealed += 1

    db.commit()
    summary = {
        "newly_matched": newly_matched,
        "pools_examined": len(trips),
        "sealed": sealed,
        "escalated": escalated,
        "merged": merged,
        "blocked_no_vehicle": no_vehicle,
    }
    if newly_matched or sealed or escalated or merged or no_vehicle:
        logger.info("dispatch cycle: %s", summary)
    return summary
