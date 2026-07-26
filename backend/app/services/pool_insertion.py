"""
Decides whether a booking can join an existing pool, and how good that
fit is.

Two things here that the previous implementation could not do at all:

  1. PER-PASSENGER DETOUR GUARANTEE. The old check asked "does the whole
     route get more than N km longer?" — a fleet cost question. It said
     nothing about what any individual passenger suffers, so a passenger
     picked up first and dropped last could absorb 40+ minutes while
     every insertion technically passed. Here, every passenger's ride
     time is compared against their own stored solo baseline, and the
     insertion is rejected if ANY of them exceeds the promised cap. That
     is the constraint a customer actually experiences.

  2. STAGED EVALUATION. Cheap in-memory rejects run before any paid API
     call, so routing spend stays proportional to plausible matches
     rather than attempted ones.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.dispatch_config import (
    EARLY_PICKUP_TOLERANCE_MINUTES,
    LATE_PICKUP_TOLERANCE_MINUTES,
    MAX_ACCEPTABLE_SCORE,
    MAX_PASSENGER_DETOUR_MINUTES,
    MAX_PASSENGERS,
    MAX_POOL_DETOUR_MINUTES,
    PICKUP_WINDOW_MINUTES,
    WEIGHT_ADDED_DISTANCE,
    WEIGHT_DEADLINE_PRESSURE,
    WEIGHT_OCCUPANCY,
    WEIGHT_PICKUP_WAIT,
    WEIGHT_WORST_DETOUR,
)
from app.services.geo import haversine_m
from app.services.route_solver import solve_pdp
from app.services.traffic import travel_multiplier
from app.services.routing import Coord, routing_service

# Beyond this straight-line gap there is no plausible road route worth
# evaluating on this corridor; used only as a free pre-filter.
COARSE_PREFILTER_METERS = 25_000


@dataclass
class PoolMember:
    """A booking already in the pool, with its stored solo baseline."""

    booking_id: UUID
    pickup: Coord
    dropoff: Coord
    requested_pickup_at: datetime
    solo_duration_seconds: float
    # Physical seats this booking occupies — a family travelling
    # together is one member worth several seats. Defaults to 1 so
    # every existing construction site stays correct.
    seats: int = 1


@dataclass
class Stop:
    booking_id: UUID
    kind: str  # "pickup" | "dropoff"
    coord: Coord


@dataclass
class InsertionResult:
    feasible: bool
    reason: str | None = None
    score: float | None = None
    ordered_stops: list[Stop] | None = None
    total_duration_seconds: float = 0.0
    worst_detour_minutes: float = 0.0
    # Cumulative seconds from route start to each booking's pickup and
    # dropoff, keyed booking_id -> {"pickup": x, "dropoff": y}. This is
    # what makes real per-stop ETAs possible: the old _apply_etas split
    # total route duration EVENLY across stops and gave every passenger
    # the same dropoff time, which then fed find_returning_vehicle
    # fabricated arrival numbers.
    stop_offsets_seconds: dict[UUID, dict[str, float]] | None = None



def _as_utc(dt: datetime) -> datetime:
    """
    Normalizes any datetime to timezone-aware UTC.

    Postgres `timestamptz` columns can come back either aware or naive
    depending on driver and session settings, and mixing the two raises
    `TypeError: can't subtract offset-naive and offset-aware datetimes`
    the moment a stored booking is compared against a fresh
    `datetime.now(timezone.utc)`. Normalizing at every boundary is the
    only reliable fix — every comparison in this module goes through
    here first.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_solo_baseline(pickup: Coord, dropoff: Coord) -> float:
    """
    A booking's direct point-to-point ride time, in seconds.

    MUST be the sole way `PoolMember.solo_duration_seconds` is produced.
    Detour is measured as (in-car time) minus (this baseline), so if the
    baseline is ever computed by a different method — a hand-entered
    guess, a different API, a stale value from before an address change —
    every detour figure silently becomes meaningless and the per-passenger
    guarantee stops guaranteeing anything.

    Deriving it here, from the same RoutingService the pool route uses,
    keeps both sides of that subtraction consistent by construction,
    including when the service is running in degraded estimate mode.
    """
    return routing_service.leg(pickup, dropoff).duration_seconds


def _windows_overlap(a: datetime, b: datetime) -> bool:
    return abs(
        (_as_utc(a) - _as_utc(b)).total_seconds()
    ) <= PICKUP_WINDOW_MINUTES * 60


def _stops_of(members: list[PoolMember]) -> list[Stop]:
    """The 2n pickup/dropoff stops for a set of members, pickup then
    dropoff per member — the stable ordering solve_pdp indexes into."""
    stops: list[Stop] = []
    for m in members:
        stops.append(Stop(m.booking_id, "pickup", m.pickup))
        stops.append(Stop(m.booking_id, "dropoff", m.dropoff))
    return stops


def _marginal_disturbance_seconds(
    members: list[PoolMember],
    baseline_offsets: dict[UUID, dict[str, float]],
    offsets: dict[UUID, dict[str, float]],
) -> float:
    """
    How much LATER does inserting a candidate push whichever EXISTING
    member's own pickup is worst-affected — comparing their scheduled
    pickup in the pool's best route WITHOUT the candidate
    (baseline_offsets) against the best route WITH it (offsets). 0 if
    nobody's pickup moves later (or moves earlier).

    This is what wait_term is built on: a real measure of who the
    insertion actually inconveniences, replacing a raw "how far is the
    candidate's requested time from the pool's earliest member" gap that
    said nothing about whether anyone already in the car was actually
    delayed — two candidates requesting similar times score identically
    under that gap even when one insertion pushes an existing rider's
    pickup back 20 minutes and the other doesn't move it at all.
    """
    max_disturbance = 0.0
    for m in members:
        before = baseline_offsets.get(m.booking_id, {}).get("pickup")
        after = offsets.get(m.booking_id, {}).get("pickup")
        if before is not None and after is not None:
            max_disturbance = max(max_disturbance, after - before)
    return max_disturbance


def _best_ordering(
    members: list[PoolMember],
    durations: dict[tuple[int, int], float],
    index: dict[tuple[UUID, str], int],
    trip_start: datetime | None = None,
) -> tuple[float, list[Stop], dict[UUID, dict[str, float]]]:
    """
    Exact minimum-duration valid stop ordering for `members`, via the
    shared branch-and-bound PDP solver. Replaces the old
    raw-permutation search whose MAX_PERMUTATIONS cap could fire before
    every valid ordering was even seen (40,320 raw permutations at 4
    riders vs. only 2,520 valid ones), biasing the result toward
    whoever joined the pool first.

    `durations`/`index` are the batched leg matrix and the
    coord-position lookup already built by evaluate_insertion — the
    solver's cost callback reads real road-network leg times straight
    out of them.

    When `trip_start` is given, two things are pruned DURING the search
    rather than checked after the fact on whatever the search happened
    to find first:

      - every PICKUP stop must land within
        [requested_pickup_at - EARLY_TOLERANCE, +LATE_TOLERANCE] of that
        passenger's own request. Arriving early doesn't violate
        anything; it forces a wait, which is folded into the running
        schedule so it correctly delays every stop visited after it
        (see solve_pdp).
      - every DROPOFF stop must keep that rider's in-car time (their own
        boarded_at, tracked by solve_pdp, to this dropoff) within
        MAX_PASSENGER_DETOUR_MINUTES of their solo baseline. Without
        this, the search could return the globally-shortest route only
        to have it rejected afterward for blowing one passenger's
        detour cap, even when a slightly-longer, still-feasible
        ordering existed and was never considered because it wasn't the
        minimum.

    Without `trip_start`, both constraints are skipped — a pure
    duration-minimizing reference search, useful for isolating "does the
    solver find the right route" from "does it also respect these two
    promises."

    Returns `(total_duration_seconds, ordered_stops, stop_offsets)` —
    offsets are the SAME schedule the search used to prune (so any
    forced wait is already baked in), keyed
    `booking_id -> {"pickup": seconds, "dropoff": seconds}`. This is the
    single source of truth for the committed ETAs downstream.
    """
    stops = _stops_of(members)
    if not stops:
        return 0.0, [], {}
    kinds = [s.kind for s in stops]
    owners = [s.booking_id for s in stops]

    # Rush hour makes the same roads slower. Scale every leg — and, in
    # the detour check below, the solo baseline it's measured against —
    # by the same factor, so ETAs get realistic without the detour
    # subtraction quietly losing its meaning. See traffic.py.
    slowdown = travel_multiplier(trip_start)

    def cost(i: int, j: int) -> float:
        return slowdown * durations[
            (index[(stops[i].booking_id, stops[i].kind)],
             index[(stops[j].booking_id, stops[j].kind)])
        ]

    feasible = None
    if trip_start is not None:
        member_by_id = {m.booking_id: m for m in members}
        early = timedelta(minutes=EARLY_PICKUP_TOLERANCE_MINUTES)
        late = timedelta(minutes=LATE_PICKUP_TOLERANCE_MINUTES)
        max_detour_seconds = MAX_PASSENGER_DETOUR_MINUTES * 60

        def feasible(
            stop_index: int, arrival_seconds: float, boarded_at: dict
        ) -> tuple[bool, float]:
            stop = stops[stop_index]
            if stop.kind == "pickup":
                requested = _as_utc(member_by_id[stop.booking_id].requested_pickup_at)
                arrival_at = trip_start + timedelta(seconds=arrival_seconds)
                if arrival_at > requested + late:
                    return False, 0.0  # would arrive too late — reject this route
                if arrival_at < requested - early:
                    wait = (requested - early - arrival_at).total_seconds()
                    return True, wait  # too early — wait, don't pick up for free
                return True, 0.0
            # Dropoff: reject if THIS rider's own in-car time would blow
            # their detour cap — boarded_at[owner] is exactly their own
            # pickup's arrival (including any wait), maintained by
            # solve_pdp in lockstep with the search itself. The stored
            # baseline is a free-flow number, so it gets the same
            # slowdown as the legs it's being compared with.
            boarded = boarded_at.get(stop.booking_id)
            if boarded is not None:
                solo = (
                    member_by_id[stop.booking_id].solo_duration_seconds * slowdown
                )
                if (arrival_seconds - boarded) - solo > max_detour_seconds:
                    return False, 0.0
            return True, 0.0

    total, order, arrivals = solve_pdp(kinds, owners, cost, feasible)
    ordered_stops = [stops[i] for i in order]
    offsets: dict[UUID, dict[str, float]] = {}
    for stop, arrival in zip(ordered_stops, arrivals):
        offsets.setdefault(stop.booking_id, {})[stop.kind] = arrival
    return total, ordered_stops, offsets


def best_ordering_from_position(
    members: list[PoolMember], vehicle_position: Coord
) -> tuple[float, list[Stop], dict[UUID, dict[str, float]]]:
    """
    Same exact search as _best_ordering, but the route is anchored to
    start from `vehicle_position` (a vehicle's current, non-stale
    last_location) instead of being free to start at whichever stop is
    cheapest. The vehicle -> first-pickup leg becomes part of what's
    minimized, so deadhead distance actually shapes the chosen stop
    order and approach direction instead of being invisible to it.

    No schedule-window pruning here — this re-solves stop ORDER for an
    already-accepted group of members once a specific vehicle is
    committed, not new-member feasibility (already decided by
    evaluate_insertion when each member joined). Returns the same
    `(total_duration_seconds, ordered_stops, stop_offsets)` shape as
    _best_ordering.
    """
    stops = _stops_of(members)
    if not stops:
        return 0.0, [], {}

    coords = [vehicle_position] + [s.coord for s in stops]
    matrix = routing_service.matrix(coords, coords)
    durations = {
        (i, j): matrix[i][j].duration_seconds
        for i in range(len(coords))
        for j in range(len(coords))
    }
    # Stop i lives at matrix slot i+1 — slot 0 is the vehicle's position.
    kinds = [s.kind for s in stops]
    owners = [s.booking_id for s in stops]

    # Same rush-hour slowdown as every other route computation, applied
    # to the deadhead leg too — driving out to the first pickup is no
    # faster in traffic than the rest of the run.
    slowdown = travel_multiplier(
        min(_as_utc(m.requested_pickup_at) for m in members)
    )

    def cost(i: int, j: int) -> float:
        return slowdown * durations[(i + 1, j + 1)]

    def start_cost(i: int) -> float:
        return slowdown * durations[(0, i + 1)]

    total, order, arrivals = solve_pdp(kinds, owners, cost, start_cost=start_cost)
    ordered_stops = [stops[i] for i in order]
    offsets: dict[UUID, dict[str, float]] = {}
    for stop, arrival in zip(ordered_stops, arrivals):
        offsets.setdefault(stop.booking_id, {})[stop.kind] = arrival
    return total, ordered_stops, offsets


LegCache = dict[tuple[Coord, Coord], float]


def build_leg_cache(coords: list[Coord]) -> LegCache:
    """
    One matrix call covering every pair among `coords`, keyed by the
    COORDINATES themselves rather than by position.

    Position-keyed lookups can't be shared between calls — each
    evaluate_insertion builds its own coords list, so index 3 means
    something different every time. Keying by coordinate makes one fetch
    reusable across every insertion evaluated within a dispatch group
    (see dispatch_service.recluster_forming_pools), turning a per-
    candidate-per-group API cost into one call for the whole group.
    """
    matrix = routing_service.matrix(coords, coords)
    return {
        (a, b): matrix[i][j].duration_seconds
        for i, a in enumerate(coords)
        for j, b in enumerate(coords)
    }


def _leg_lookup(
    coords: list[Coord], leg_cache: LegCache | None = None
) -> dict[tuple[int, int], float]:
    """
    Position-keyed stop-to-stop durations for one evaluation.

    Served from `leg_cache` when every needed pair is already in it —
    zero API calls. Any gap falls back to a live batched fetch rather
    than guessing, so a partial or stale cache degrades to the old
    behavior instead of producing wrong numbers.
    """
    if leg_cache is not None:
        lookup: dict[tuple[int, int], float] = {}
        complete = True
        for i, a in enumerate(coords):
            for j, b in enumerate(coords):
                hit = leg_cache.get((a, b))
                if hit is None:
                    complete = False
                    break
                lookup[(i, j)] = hit
            if not complete:
                break
        if complete:
            return lookup

    matrix = routing_service.matrix(coords, coords)
    return {
        (i, j): matrix[i][j].duration_seconds
        for i in range(len(coords))
        for j in range(len(coords))
    }


def evaluate_insertion(
    members: list[PoolMember],
    candidate: PoolMember,
    departure_deadline: datetime | None = None,
    now: datetime | None = None,
    capacity: int = MAX_PASSENGERS,
    leg_cache: LegCache | None = None,
) -> InsertionResult:
    """
    Evaluates adding `candidate` to a pool already holding `members`.
    Returns feasibility plus a 0..1 score where LOWER is better.

    `capacity` is the seat count of the car this pool will actually
    travel in, when that's already known (a trip with a reserved or
    assigned vehicle). It defaults to MAX_PASSENGERS — the smallest
    vehicle in the fleet — which is the right conservative assumption
    while no specific car is committed yet: a pool built assuming a
    bigger car might not fit the one it eventually gets.

    `leg_cache` is a coordinate-keyed leg-duration table covering every
    stop this call could need (see build_leg_cache). Supplying one makes
    this evaluation free of routing API calls; omitting it fetches as
    before.
    """
    now = _as_utc(now or datetime.now(timezone.utc))

    # ---- Stage 1: free rejects -------------------------------------
    # Seats, not member count — one booking can be a family of three.
    occupied_seats = sum(m.seats for m in members)
    if occupied_seats + candidate.seats > capacity:
        return InsertionResult(
            False,
            f"not enough seats ({occupied_seats} of {capacity} taken, "
            f"booking needs {candidate.seats})",
        )

    for m in members:
        if not _windows_overlap(m.requested_pickup_at, candidate.requested_pickup_at):
            return InsertionResult(
                False,
                f"pickup times more than {PICKUP_WINDOW_MINUTES} min apart",
            )

    for m in members:
        if (
            haversine_m(*m.pickup, *candidate.pickup) > COARSE_PREFILTER_METERS
            and haversine_m(*m.dropoff, *candidate.dropoff) > COARSE_PREFILTER_METERS
        ):
            return InsertionResult(False, "pickup and dropoff both too far")

    # ---- Stage 2: batched routing ----------------------------------
    everyone = members + [candidate]
    coords: list[Coord] = []
    index: dict[tuple[UUID, str], int] = {}
    for m in everyone:
        index[(m.booking_id, "pickup")] = len(coords)
        coords.append(m.pickup)
        index[(m.booking_id, "dropoff")] = len(coords)
        coords.append(m.dropoff)

    durations = _leg_lookup(coords, leg_cache)

    # Anchor for the schedule-window check below — the promise belongs
    # to whoever in this candidate route has been waiting longest,
    # same convention used everywhere else a pool's start time matters
    # (departure_deadline, _write_etas).
    trip_start = min(_as_utc(m.requested_pickup_at) for m in everyone)

    # ---- Stage 3: exact ordering, pruned by schedule window AND detour -
    # Both the pickup-time promise and the per-passenger detour cap are
    # now enforced INSIDE the search (see _best_ordering) — the ordering
    # returned here, if any, is already the best ordering that satisfies
    # both, not just the shortest one checked against them afterward.
    best_total, best_order, offsets = _best_ordering(
        everyone, durations, index, trip_start
    )
    if not best_order:
        # Precedence alone (pickup-before-own-dropoff) is always
        # satisfiable for any non-empty member set — the only things that
        # can make every ordering infeasible here are the schedule-window
        # and per-passenger detour constraints just applied.
        return InsertionResult(
            False, "no ordering satisfies pickup time windows and the detour cap"
        )

    # Per-passenger in-car time vs. solo baseline — already guaranteed
    # within MAX_PASSENGER_DETOUR_MINUTES by construction (Stage 3), this
    # is purely descriptive now: feeding detour_term below and the
    # returned worst_detour_minutes, not a second accept/reject gate.
    # Every route number below came out of a search scaled for rush-hour
    # slowdown, so each stored (free-flow) baseline it gets compared
    # against has to be scaled the same way — otherwise a peak-hour trip
    # would look like it had a huge detour purely because traffic was
    # priced into one side of the subtraction and not the other.
    slowdown = travel_multiplier(trip_start)

    detours: dict[UUID, float] = {}
    for m in everyone:
        off = offsets[m.booking_id]
        in_car = off["dropoff"] - off["pickup"]
        detours[m.booking_id] = (
            in_car - m.solo_duration_seconds * slowdown
        ) / 60.0
    worst_detour = max(detours.values()) if detours else 0.0

    if best_total / 60.0 > (
        max(m.solo_duration_seconds for m in everyone) * slowdown / 60.0
        + MAX_POOL_DETOUR_MINUTES
    ):
        return InsertionResult(False, "pool route too long overall")

    # ---- Stage 4: score (lower is better) --------------------------
    # No Directions call here on purpose. This used to fetch the full
    # route geometry just to populate total_distance_meters/is_estimate
    # on the result — fields no caller ever read (every consumer uses
    # feasible/score/reason only), at the cost of one API request per
    # candidate evaluated. The trip's real geometry is fetched once when
    # it's actually committed, in _refresh_pool_geometry.
    # Same reasoning: added_seconds is a scaled figure, so the baseline
    # it's expressed as a fraction of has to be scaled too.
    solo_baseline = candidate.solo_duration_seconds * slowdown
    baseline_total, _baseline_order, baseline_offsets = _best_ordering(
        members, durations, index, trip_start
    )
    added_seconds = max(0.0, best_total - baseline_total)

    # Seats filled, not bookings counted — a single 3-seat family
    # booking fills a car far more than three separate 1-seat bookings
    # would suggest by row count.
    seats_after = sum(m.seats for m in everyone)
    # Prefer nearly-full vehicles: filling one car before opening a second
    # is a real business objective (though see dispatch_config's weight
    # comment for why it isn't weighted as heavily as it once was).
    occupancy_term = 1.0 - (seats_after - 1) / max(1, capacity - 1)

    distance_term = min(1.0, added_seconds / (solo_baseline or 1.0))
    detour_term = min(1.0, worst_detour / MAX_PASSENGER_DETOUR_MINUTES)

    max_disturbance_seconds = _marginal_disturbance_seconds(
        members, baseline_offsets, offsets
    )
    wait_term = min(1.0, max(0.0, max_disturbance_seconds) / (PICKUP_WINDOW_MINUTES * 60))

    if departure_deadline:
        remaining = (_as_utc(departure_deadline) - now).total_seconds()
        # Closer to deadline == more urgent to fill == better score.
        deadline_term = max(0.0, min(1.0, remaining / (PICKUP_WINDOW_MINUTES * 60)))
    else:
        deadline_term = 0.5

    score = (
        WEIGHT_OCCUPANCY * occupancy_term
        + WEIGHT_ADDED_DISTANCE * distance_term
        + WEIGHT_WORST_DETOUR * detour_term
        + WEIGHT_PICKUP_WAIT * wait_term
        + WEIGHT_DEADLINE_PRESSURE * deadline_term
    )

    if score > MAX_ACCEPTABLE_SCORE:
        return InsertionResult(
            False, f"fit quality too poor (score {score:.2f})", score=score
        )

    return InsertionResult(
        feasible=True,
        score=score,
        ordered_stops=best_order,
        total_duration_seconds=best_total,
        worst_detour_minutes=worst_detour,
        stop_offsets_seconds=offsets,
    )


def solve_group_ordering(
    members: list[PoolMember],
) -> tuple[float, list[Stop], dict[UUID, dict[str, float]]]:
    """
    Exact ordering for an already-accepted group, solved for the WHOLE
    group at once — the entry point _refresh_pool_geometry uses to
    re-derive geometry after membership changes.

    Replaces the old `evaluate_insertion(members[:-1], members[-1])`
    trick, which treated "everyone except however trip.bookings happens
    to iterate last" as the existing pool and one arbitrary member as
    the "candidate" — a split with no principled meaning (join order
    isn't tracked, so "last" was just whatever the ORM relationship
    happened to return) that could produce a different, or silently
    worse, route than the one actually accepted when each member joined.
    This solves directly for the real group, with the same schedule
    window + detour pruning evaluate_insertion applies at insertion time
    (every member here already passed those checks individually when
    they joined, so this should always find a feasible ordering — same
    exact search, not a different one).
    """
    if not members:
        return 0.0, [], {}
    if len(members) == 1:
        # A lone rider skips the search — but must NOT skip the
        # rush-hour slowdown with it, or a solo trip departing at 17:30
        # gets quoted a free-flow arrival time while a shared one
        # doesn't. This branch is the common case (every pool starts
        # here), so missing it made the whole feature invisible in
        # practice.
        m = members[0]
        slowdown = travel_multiplier(_as_utc(m.requested_pickup_at))
        duration = routing_service.leg(m.pickup, m.dropoff).duration_seconds * slowdown
        stops = [Stop(m.booking_id, "pickup", m.pickup), Stop(m.booking_id, "dropoff", m.dropoff)]
        offsets = {m.booking_id: {"pickup": 0.0, "dropoff": duration}}
        return duration, stops, offsets

    coords: list[Coord] = []
    index: dict[tuple[UUID, str], int] = {}
    for m in members:
        index[(m.booking_id, "pickup")] = len(coords)
        coords.append(m.pickup)
        index[(m.booking_id, "dropoff")] = len(coords)
        coords.append(m.dropoff)
    durations = _leg_lookup(coords)
    trip_start = min(_as_utc(m.requested_pickup_at) for m in members)
    return _best_ordering(members, durations, index, trip_start)
