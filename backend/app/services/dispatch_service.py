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
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.dispatch_config import (
    MAX_PASSENGERS,
    MAX_POOL_WAIT_MINUTES,
    PICKUP_WINDOW_MINUTES,
    RETURN_VEHICLE_LATE_TOLERANCE_MINUTES,
    RETURN_VEHICLE_MATCH_WINDOW_MINUTES,
    VEHICLE_LOCATION_STALE_MINUTES,
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
    _as_utc,
    best_ordering_from_position,
    compute_solo_baseline,
    evaluate_insertion,
    solve_group_ordering,
)
from app.services.reclustering import cluster_by_proximity, time_cluster
from app.services.routing import routing_service
from app.services.notification_service import notify_trip_disrupted, notify_trip_sealed

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
        seats=booking.seats or 1,
    )


def active_bookings(trip: Trip) -> list[Booking]:
    """Bookings still really on this trip — cancelled/no-show riders
    are gone and must never count toward capacity or geometry."""
    return [
        b
        for b in trip.bookings
        if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
    ]


def seats_taken(trip: Trip) -> int:
    """Physical seats occupied on a trip. Sums each booking's own seat
    count rather than counting rows — one booking can be a family."""
    return sum(b.seats or 1 for b in active_bookings(trip))


def trip_capacity(db: Session, trip: Trip) -> int:
    """
    How many seats this trip can actually hold.

    Uses the committed vehicle's real seat_capacity when one is already
    reserved or assigned (Vehicle.seat_capacity has existed all along
    but nothing read it — matching always assumed the global constant,
    so a 7-seat van could never be filled past 4). Falls back to
    MAX_PASSENGERS, the smallest car in the fleet, while no specific
    vehicle is committed: a pool built assuming a big van might not fit
    the car it eventually gets, so the conservative bound is correct
    until the real one is known.
    """
    if trip.vehicle_id is not None:
        vehicle = db.get(Vehicle, trip.vehicle_id)
        if vehicle is not None and vehicle.seat_capacity:
            return vehicle.seat_capacity
    return MAX_PASSENGERS


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

    # Nothing to do if neither WHO is in this pool nor WHICH vehicle it's
    # anchored to has changed since the last solve — centroid, deadline,
    # route, and every booking's stop_order/ETA are all still correct.
    # Skips the routing-service call(s) and the solver entirely, not just
    # a cheap early return; see Trip.solved_booking_ids docstring.
    active_ids = sorted(str(b.id) for b in active)
    if (
        trip.solved_booking_ids == active_ids
        and trip.solved_vehicle_id == trip.vehicle_id
    ):
        return

    pickups = [_coords(b)[0] for b in active]
    lat = sum(p[0] for p in pickups) / len(pickups)
    lng = sum(p[1] for p in pickups) / len(pickups)
    trip.centroid = WKTElement(f"POINT({lng} {lat})", srid=4326)

    earliest = min(b.requested_pickup_at for b in active)
    trip.departure_deadline = earliest + timedelta(minutes=MAX_POOL_WAIT_MINUTES)

    members = [_to_member(b) for b in active]
    offsets: dict | None = None

    # If a vehicle is already committed to this trip (most notably right
    # after seal_trip's _assign_vehicle call) and we have a fresh fix on
    # where it actually is, anchor the route there instead of letting
    # the search start wherever happens to be cheapest. This is what
    # makes deadhead distance and real approach direction part of the
    # committed order rather than invisible to it — see
    # pool_insertion.best_ordering_from_position.
    vehicle_position = None
    if trip.vehicle_id is not None:
        vehicle = db.get(Vehicle, trip.vehicle_id)
        if (
            vehicle is not None
            and vehicle.last_location is not None
            and vehicle.last_location_at is not None
        ):
            stale_cutoff = datetime.now(timezone.utc) - timedelta(
                minutes=VEHICLE_LOCATION_STALE_MINUTES
            )
            if _as_utc(vehicle.last_location_at) >= stale_cutoff:
                pos = to_shape(vehicle.last_location)
                vehicle_position = (pos.y, pos.x)

    if len(members) == 1:
        m = members[0]
        route = routing_service.route([m.pickup, m.dropoff])
        active[0].stop_order = 1
        offsets = {
            m.booking_id: {"pickup": 0.0, "dropoff": route.total_duration_seconds}
        }
    elif vehicle_position is not None:
        _total, ordered_stops, position_offsets = best_ordering_from_position(
            members, vehicle_position
        )
        if ordered_stops:
            route = routing_service.route(
                [vehicle_position] + [s.coord for s in ordered_stops]
            )
            offsets = position_offsets
            for rank, stop in enumerate(
                [s for s in ordered_stops if s.kind == "pickup"], start=1
            ):
                for b in active:
                    if b.id == stop.booking_id:
                        b.stop_order = rank
        else:
            route = routing_service.route(
                [c for m in members for c in (m.pickup, m.dropoff)]
            )
    else:
        # Solve for the actual whole group — not the old
        # members[:-1]/[-1] split, which had no principled meaning (see
        # solve_group_ordering's docstring).
        _total, ordered_stops, group_offsets = solve_group_ordering(members)
        if ordered_stops:
            route = routing_service.route([s.coord for s in ordered_stops])
            offsets = group_offsets
            for rank, stop in enumerate(
                [s for s in ordered_stops if s.kind == "pickup"], start=1
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

    _write_etas(active, offsets, route.total_duration_seconds)

    trip.solved_booking_ids = active_ids
    trip.solved_vehicle_id = trip.vehicle_id


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
        # Corridor-scoped: without this, two corridors that happen to
        # pass near each other (both radiating from Hà Nội, say) could
        # pool bookings that aren't actually on the same route just
        # because they're geometrically close. Costs nothing while only
        # one corridor exists; becomes load-bearing the moment a second
        # one does.
        .where(Trip.corridor_id == booking.corridor_id)
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
        # Seats, not member count, against THIS trip's real capacity
        # (the committed vehicle's, if it has one).
        capacity = trip_capacity(db, trip)
        if sum(m.seats for m in members) + candidate.seats > capacity:
            continue
        if any(m.solo_duration_seconds <= 0 for m in members):
            continue  # baseline missing; skip rather than compute garbage

        result = evaluate_insertion(
            members,
            candidate,
            departure_deadline=trip.departure_deadline,
            capacity=capacity,
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

    "Vehicle position" here is inferred from timing, not the vehicle's
    actual GPS location: it's the estimated dropoff time already
    computed for the outbound trip's last stop (see _write_etas), which
    is the same estimate the customer was shown. This is a forecast, not
    a fact — a badly delayed outbound run could make the
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
            # A van finishing an outbound run on a different corridor
            # isn't "going back the same way" this return passenger
            # needs — only a same-corridor outbound trip is a genuine
            # free-mileage match.
            .where(Trip.corridor_id == booking.corridor_id)
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
        # Both sides normalized to aware-UTC before subtracting —
        # estimated_dropoff_at and requested_pickup_at can come back from
        # Postgres with differing tzinfo, and mixing naive/aware raises
        # TypeError mid-cycle.
        gap_minutes = (
            _as_utc(booking.requested_pickup_at) - _as_utc(estimated_arrival)
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
            corridor_id=booking.corridor_id,
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

    # Through the relationship, not the raw trip_id column — required,
    # not stylistic. `trip` may already be loaded in this session's
    # identity map (e.g. find_pool_for_booking just iterated it while
    # evaluating candidates); a raw trip_id write doesn't retroactively
    # add this booking to that already-cached trip.bookings collection,
    # so _refresh_pool_geometry below would compute geometry as if this
    # booking didn't exist yet. Same class of bug fixed in
    # recluster_forming_pools's reconciliation loop.
    booking.trip = trip
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


def pool_snapshot(trip: Trip, db: Session | None = None) -> PoolSnapshot:
    active = active_bookings(trip)
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
        seat_count=sum(b.seats or 1 for b in active),
        capacity=trip_capacity(db, trip) if db is not None else MAX_PASSENGERS,
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
    required_seats = seats_taken(trip)

    if trip.vehicle_id is not None:
        reserved = db.get(Vehicle, trip.vehicle_id)
        if (
            reserved is not None
            and reserved.status
            in (VehicleStatus.available, VehicleStatus.on_trip)
            # A reservation made when the pool was smaller must still
            # actually fit it now — pools keep accreting bookings after
            # a vehicle is earmarked (find_returning_vehicle reserves at
            # pool-creation time), so this can genuinely outgrow the car.
            and reserved.seat_capacity >= required_seats
        ):
            trip.vehicle_label = reserved.label or reserved.plate_number
            if trip.driver_id is None and reserved.default_driver_id:
                trip.driver_id = reserved.default_driver_id
            reserved.status = VehicleStatus.on_trip
            return reserved
        # Reservation no longer usable (pulled into maintenance since
        # being earmarked, or the pool outgrew it) — fall through to a
        # fresh search rather than blocking this trip's departure.
        trip.vehicle_id = None

    # Used to be "whichever available vehicle the database happens to
    # return first" — no ordering at all, and Vehicle.last_location was
    # written nowhere and read nowhere. That meant a car parked at one
    # end of the corridor could get sent to a pickup at the other end
    # while a closer car sat idle. Order by real distance to where this
    # trip actually needs a car (its centroid, already maintained by
    # _refresh_pool_geometry); a vehicle with no known OR STALE location
    # sorts last rather than being excluded outright — never block a
    # trip's departure over a location-tracking gap. A ping older than
    # VEHICLE_LOCATION_STALE_MINUTES is treated identically to no ping at
    # all: a phone that stopped reporting an hour ago is not still
    # telling the truth about where the car is.
    base_query = (
        select(Vehicle)
        .where(Vehicle.status == VehicleStatus.available)
        # Must physically seat everyone already in this pool. Without
        # this, a 4-seat pool could be handed a car too small for it and
        # only fail later at the database's capacity trigger.
        .where(Vehicle.seat_capacity >= required_seats)
    )
    if trip.centroid is not None:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=VEHICLE_LOCATION_STALE_MINUTES
        )
        order_expr = case(
            (Vehicle.last_location_at.is_(None), 1_000_000_000),
            (Vehicle.last_location_at < stale_cutoff, 1_000_000_000),
            else_=func.coalesce(
                func.ST_Distance(Vehicle.last_location, trip.centroid), 1_000_000_000
            ),
        )
        base_query = base_query.order_by(order_expr)

    # Prefer a vehicle homed on this trip's corridor; only fall back to
    # an out-of-corridor or untagged vehicle if none is available there —
    # again, never block dispatch over a tagging gap.
    vehicle = (
        db.execute(base_query.where(Vehicle.home_corridor_id == trip.corridor_id).limit(1))
        .scalars()
        .first()
    )
    if vehicle is None:
        vehicle = db.execute(base_query.limit(1)).scalars().first()
    if vehicle is None:
        return None

    vehicle.status = VehicleStatus.on_trip
    trip.vehicle_id = vehicle.id
    trip.vehicle_label = vehicle.label or vehicle.plate_number
    if trip.driver_id is None and vehicle.default_driver_id:
        trip.driver_id = vehicle.default_driver_id
    return vehicle


def _write_etas(
    active: list[Booking],
    offsets: dict | None,
    total_duration_seconds: float,
) -> None:
    """
    Writes firm pickup/dropoff estimates from the route's REAL per-stop
    offsets (see pool_insertion._best_ordering, which folds any forced
    early-arrival wait into these same numbers), anchored to the
    earliest requested pickup. Replaces an even-split that gave every
    passenger the same fabricated dropoff time — numbers
    find_returning_vehicle then matched return bookings against.
    """
    if not active:
        return
    start = min(b.requested_pickup_at for b in active)
    for b in active:
        off = offsets.get(b.id) if offsets else None
        if off is not None:
            b.estimated_pickup_at = start + timedelta(seconds=off.get("pickup", 0.0))
            b.estimated_dropoff_at = start + timedelta(
                seconds=off.get("dropoff", total_duration_seconds or 0.0)
            )
        else:
            # Degraded fallback (no feasible ordering / no offsets): a
            # coarse but honest estimate rather than a wrong-precise one.
            b.estimated_pickup_at = start
            b.estimated_dropoff_at = start + timedelta(
                seconds=total_duration_seconds or 0.0
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

    # _refresh_pool_geometry now writes real per-stop ETAs itself, so
    # the remaining passengers' pickup/dropoff estimates are already
    # up to date after a booking leaves — no separate ETA pass needed.
    _refresh_pool_geometry(db, old_trip)

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
    # Refreshes geometry AND writes real per-stop ETAs in one pass.
    _refresh_pool_geometry(db, trip)
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
            # Through the relationship, not the raw column — `target` is
            # passed in already loaded, so a raw trip_id write wouldn't
            # be reflected in target.bookings when _refresh_pool_geometry
            # reads it two lines down. See assign_booking for the same
            # bug in its original form.
            b.trip = target
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


def recluster_forming_pools(db: Session, now: datetime) -> int:
    """
    Periodically re-groups still-forming pools by pickup time first,
    geographic proximity second (see reclustering.py for the actual
    grouping logic and why). Continuous matching (assign_booking) still
    places a booking the instant it's created — this corrects that
    greedy, order-dependent placement shortly after, every dispatch
    tick, rather than replacing it.

    Only ever touches trips still `status == forming`. A trip that's
    sealed/assigned/in_progress is never read or written here — once a
    customer has a firm car and ETA, reclustering cannot change it.

    Returns how many (corridor, direction) groups actually changed.
    """
    trips = (
        db.execute(select(Trip).where(Trip.status == TripStatus.forming))
        .scalars()
        .all()
    )

    # Private hires are solo by definition and never subject to
    # grouping — excluded entirely, not just their bookings, so a
    # private trip can never accidentally get claimed as the "target"
    # for someone else's group during reconciliation below.
    groups: dict[tuple, list[Trip]] = {}
    for trip in trips:
        active = [
            b
            for b in trip.bookings
            if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
        ]
        if any(b.is_private for b in active):
            continue
        groups.setdefault((trip.corridor_id, trip.direction), []).append(trip)

    changed_groups = 0

    for (corridor_id, direction), group_trips in groups.items():
        active_by_trip: dict[UUID, list[Booking]] = {}
        all_bookings: list[Booking] = []
        for trip in group_trips:
            active = [
                b
                for b in trip.bookings
                if b.status not in (BookingStatus.cancelled, BookingStatus.no_show)
            ]
            active_by_trip[trip.id] = active
            all_bookings.extend(active)

        if not all_bookings:
            continue

        if any(b.solo_duration_seconds is None or b.solo_duration_seconds <= 0 for b in all_bookings):
            continue  # baseline missing for someone; skip rather than compute garbage

        booking_by_id = {b.id: b for b in all_bookings}
        members = [_to_member(b) for b in all_bookings]

        # Cheap, pure pre-check: if this is a single trip whose members
        # already form one time-cluster (nothing a time-first regroup
        # would split apart) and it isn't over capacity, there's
        # nothing to gain from the expensive proximity pass below. This
        # must check time cohesion, not just capacity — a single
        # under-capacity trip can still span multiple time waves (e.g.
        # someone requested at 4:00, someone else at 4:35) that time-
        # first grouping should still split apart even though all of
        # them would happily fit in one car.
        time_clusters = time_cluster(members)
        if (
            len(group_trips) == 1
            and len(time_clusters) == 1
            and sum(b.seats or 1 for b in all_bookings) <= MAX_PASSENGERS
        ):
            continue

        new_groups = [
            {m.booking_id for m in g}
            for cluster in time_clusters
            for g in cluster_by_proximity(cluster)
        ]

        current_groups = {
            trip.id: {b.id for b in active_by_trip[trip.id]} for trip in group_trips
        }
        if {frozenset(s) for s in current_groups.values()} == {
            frozenset(s) for s in new_groups
        }:
            continue  # identical grouping — nothing to apply

        # Match each new group to whichever existing trip it overlaps
        # with most, preferring one that already has a vehicle reserved
        # — so a return-leg trip's find_returning_vehicle reservation
        # (or an already-assigned vehicle) survives a regroup instead of
        # being silently dropped when membership barely changes.
        available_trips = list(group_trips)
        assignments: list[tuple[set, Trip | None]] = []
        for new_group_ids in new_groups:
            best_trip: Trip | None = None
            best_key = (-1, 0)
            for trip in available_trips:
                overlap = len(current_groups[trip.id] & new_group_ids)
                key = (overlap, 1 if trip.vehicle_id else 0)
                if key > best_key:
                    best_trip, best_key = trip, key
            assignments.append((new_group_ids, best_trip))
            if best_trip is not None:
                available_trips.remove(best_trip)

        # Every trip touched this pass — the pre-existing ones plus any
        # freshly created below — needs its geometry refreshed at the
        # end. Tracking newly-created trips separately from group_trips
        # (which only ever holds trips that existed at the start of this
        # function) is what makes that possible.
        touched_trips = list(group_trips)

        moves: list[tuple[Booking, Trip]] = []
        for new_group_ids, target_trip in assignments:
            if target_trip is None:
                earliest_pickup = min(
                    booking_by_id[bid].requested_pickup_at for bid in new_group_ids
                )
                target_trip = Trip(
                    direction=direction,
                    corridor_id=corridor_id,
                    status=TripStatus.forming,
                    departure_deadline=earliest_pickup
                    + timedelta(minutes=MAX_POOL_WAIT_MINUTES),
                )
                db.add(target_trip)
                db.flush()
                touched_trips.append(target_trip)

            for booking_id in new_group_ids:
                booking = booking_by_id[booking_id]
                if booking.trip_id != target_trip.id:
                    moves.append((booking, target_trip))

        any_booking_moved = bool(moves)

        # Two-phase move: detach everyone that's changing trips first,
        # flush, THEN attach to their real target and flush again.
        # Moving straight to the new trip in one pass can transiently
        # overfill a trip's 4-seat capacity mid-flush — e.g. group X
        # gains a booking that's still, for one more UPDATE statement,
        # also claimed by group Y — and the database enforces capacity
        # with a row-level trigger (enforce_trip_capacity) that rejects
        # that transient state outright, even though the FINAL state
        # would be perfectly legal. Detaching everyone first guarantees
        # no trip is ever seen over capacity by that trigger.
        #
        # Assigning through the relationship (booking.trip = ...), not
        # the raw trip_id column, is also required, not stylistic — it
        # keeps the OLD trip's in-memory `.bookings` collection
        # consistent immediately via back_populates. A raw trip_id
        # write leaves that collection stale in the session for the
        # rest of this request, which previously caused a trip we'd
        # just shrunk from 4 bookings to 2 to still evaluate as "full
        # (4 passengers)" a few lines later and seal wrongly.
        for booking, _ in moves:
            booking.trip = None
        db.flush()
        for booking, target_trip in moves:
            booking.trip = target_trip
        db.flush()

        # Dissolve any trip a regroup emptied out entirely. Only
        # pre-existing trips can end up empty here — anything just
        # created only ever gains bookings in this same pass.
        for trip in group_trips:
            remaining = (
                db.query(Booking)
                .filter(Booking.trip_id == trip.id)
                .filter(Booking.status.notin_([BookingStatus.cancelled, BookingStatus.no_show]))
                .count()
            )
            if remaining == 0:
                trip.status = TripStatus.cancelled

        for trip in touched_trips:
            if trip.status == TripStatus.forming:
                _refresh_pool_geometry(db, trip)

        if any_booking_moved:
            changed_groups += 1
            log_event(
                db,
                DispatchEventType.pool_reclustered,
                reason="regrouped by pickup-time then proximity",
                details={
                    "corridor_id": str(corridor_id),
                    "direction": direction.value,
                    "groups": len(new_groups),
                },
            )

    return changed_groups


DISRUPTION_MEANS_BREAKDOWN = {"breakdown", "accident"}


def report_trip_disrupted(
    db: Session,
    trip: Trip,
    reason: str,
    notes: str | None,
    actor_user_id: UUID | None,
) -> Trip:
    """
    A driver or dispatcher reports a trip can't continue as assigned —
    breakdown, accident, or the driver simply can't take it. Before this,
    TripStatus.reassigning and DispatchEventType.driver_rejected existed
    as enum values with zero code path ever setting or emitting them: a
    live breakdown had no supported recovery, just an undocumented manual
    workaround.

    Keeps the trip's already-computed route/passengers intact and tries
    to recover immediately by reusing seal_trip — the exact same
    vehicle-assignment and notify path a normal seal takes, so a
    reassignment doesn't get a subtly different implementation. If no
    vehicle is free right now, run_dispatch_cycle retries this same trip
    every tick (see below), same as an under-vehicled forming pool.
    """
    old_vehicle_id = trip.vehicle_id
    trip.status = TripStatus.reassigning
    trip.vehicle_id = None
    trip.driver_id = None
    trip.vehicle_label = None

    if old_vehicle_id is not None:
        old_vehicle = db.get(Vehicle, old_vehicle_id)
        if old_vehicle is not None:
            old_vehicle.status = (
                VehicleStatus.maintenance
                if reason in DISRUPTION_MEANS_BREAKDOWN
                else VehicleStatus.available
            )

    notify_trip_disrupted(db, trip)

    log_event(
        db,
        DispatchEventType.driver_rejected,
        trip_id=trip.id,
        vehicle_id=old_vehicle_id,
        actor_user_id=actor_user_id,
        reason=reason,
        details={"notes": notes} if notes else None,
    )

    seal_trip(db, trip, datetime.now(timezone.utc), reason=f"reassigned after: {reason}")
    return trip


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

    # Time-first, distance-second regroup of everything still forming —
    # corrects continuous matching's greedy, order-dependent placement
    # before this same tick decides what to seal. See reclustering.py.
    reclustered = recluster_forming_pools(db, now)

    # A trip a driver reported disrupted (report_trip_disrupted) that
    # couldn't find a replacement vehicle immediately stays `reassigning`
    # with no vehicle — retry it every tick, exactly like an under-
    # vehicled forming pool below, rather than leaving it stuck until a
    # dispatcher manually intervenes.
    stuck_reassigning = (
        db.execute(
            select(Trip)
            .where(Trip.status == TripStatus.reassigning)
            .where(Trip.vehicle_id.is_(None))
        )
        .scalars()
        .all()
    )
    reassigned = 0
    for trip in stuck_reassigning:
        if seal_trip(db, trip, now, reason="vehicle freed up after driver-reported issue"):
            reassigned += 1

    trips = (
        db.execute(select(Trip).where(Trip.status == TripStatus.forming))
        .scalars()
        .all()
    )
    snapshots = {t.id: pool_snapshot(t, db) for t in trips}

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
        "reclustered": reclustered,
        "pools_examined": len(trips),
        "sealed": sealed,
        "escalated": escalated,
        "merged": merged,
        "blocked_no_vehicle": no_vehicle,
        "reassigned": reassigned,
    }
    if newly_matched or reclustered or sealed or escalated or merged or no_vehicle or reassigned:
        logger.info("dispatch cycle: %s", summary)
    return summary
