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
    total_distance_meters: float = 0.0
    worst_detour_minutes: float = 0.0
    is_estimate: bool = False
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

    When `trip_start` is given, every PICKUP stop is also constrained to
    land within [requested_pickup_at - EARLY_TOLERANCE, +LATE_TOLERANCE]
    of that passenger's own request — an ordering that can't satisfy
    this for every rider is pruned during the search, not accepted and
    checked afterward. Arriving early doesn't violate anything; it
    forces a wait, which is folded into the running schedule so it
    correctly delays every stop visited after it (see solve_pdp).
    Without `trip_start`, this constraint is skipped entirely — used by
    _baseline_without's "old pool as it stands" reference, which needs
    the same schedule model but not a hard gate that could make even
    the existing membership solve-infeasible mid-computation.

    Returns `(total_duration_seconds, ordered_stops, stop_offsets)` —
    offsets are the SAME schedule the search used to prune (so any
    forced wait is already baked in), keyed
    `booking_id -> {"pickup": seconds, "dropoff": seconds}`. This is the
    single source of truth for both the detour check and the committed
    ETAs downstream, so those two can never disagree.
    """
    stops = _stops_of(members)
    if not stops:
        return 0.0, [], {}
    kinds = [s.kind for s in stops]
    owners = [s.booking_id for s in stops]

    def cost(i: int, j: int) -> float:
        return durations[
            (index[(stops[i].booking_id, stops[i].kind)],
             index[(stops[j].booking_id, stops[j].kind)])
        ]

    feasible = None
    if trip_start is not None:
        member_by_id = {m.booking_id: m for m in members}
        early = timedelta(minutes=EARLY_PICKUP_TOLERANCE_MINUTES)
        late = timedelta(minutes=LATE_PICKUP_TOLERANCE_MINUTES)

        def feasible(stop_index: int, arrival_seconds: float) -> tuple[bool, float]:
            stop = stops[stop_index]
            if stop.kind != "pickup":
                return True, 0.0  # only pickup promises a specific time
            requested = _as_utc(member_by_id[stop.booking_id].requested_pickup_at)
            arrival_at = trip_start + timedelta(seconds=arrival_seconds)
            if arrival_at > requested + late:
                return False, 0.0  # would arrive too late — reject this route
            if arrival_at < requested - early:
                wait = (requested - early - arrival_at).total_seconds()
                return True, wait  # too early — wait, don't pick up for free
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

    def cost(i: int, j: int) -> float:
        return durations[(i + 1, j + 1)]

    def start_cost(i: int) -> float:
        return durations[(0, i + 1)]

    total, order, arrivals = solve_pdp(kinds, owners, cost, start_cost=start_cost)
    ordered_stops = [stops[i] for i in order]
    offsets: dict[UUID, dict[str, float]] = {}
    for stop, arrival in zip(ordered_stops, arrivals):
        offsets.setdefault(stop.booking_id, {})[stop.kind] = arrival
    return total, ordered_stops, offsets


def _leg_lookup(coords: list[Coord]) -> dict[tuple[int, int], float]:
    """One batched matrix call covering every stop-to-stop pair."""
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
) -> InsertionResult:
    """
    Evaluates adding `candidate` to a pool already holding `members`.
    Returns feasibility plus a 0..1 score where LOWER is better.
    """
    now = _as_utc(now or datetime.now(timezone.utc))

    # ---- Stage 1: free rejects -------------------------------------
    if len(members) >= MAX_PASSENGERS:
        return InsertionResult(False, "pool is full")

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

    durations = _leg_lookup(coords)

    # Anchor for the schedule-window check below — the promise belongs
    # to whoever in this candidate route has been waiting longest,
    # same convention used everywhere else a pool's start time matters
    # (departure_deadline, _write_etas).
    trip_start = min(_as_utc(m.requested_pickup_at) for m in everyone)

    # ---- Stage 3: exact ordering, pruned by pickup schedule window --
    best_total, best_order, offsets = _best_ordering(
        everyone, durations, index, trip_start
    )
    if not best_order:
        # Precedence alone (pickup-before-own-dropoff) is always
        # satisfiable for any non-empty member set — the only thing that
        # can make every ordering infeasible here is the schedule-window
        # constraint just applied.
        return InsertionResult(False, "no ordering satisfies pickup time windows")

    # ---- Stage 4: per-passenger service guarantee ------------------
    # in-car time (dropoff offset minus pickup offset) compared against
    # each passenger's own solo baseline. offsets already include any
    # forced wait from Stage 3, so a wait correctly inflates the in-car
    # time (and therefore detour) of everyone already aboard when it
    # happens.
    detours: dict[UUID, float] = {}
    for m in everyone:
        off = offsets[m.booking_id]
        in_car = off["dropoff"] - off["pickup"]
        detours[m.booking_id] = (in_car - m.solo_duration_seconds) / 60.0

    worst_detour = max(detours.values()) if detours else 0.0
    if worst_detour > MAX_PASSENGER_DETOUR_MINUTES:
        return InsertionResult(
            False,
            f"would add {worst_detour:.0f} min for one passenger "
            f"(limit {MAX_PASSENGER_DETOUR_MINUTES})",
            worst_detour_minutes=worst_detour,
        )

    if best_total / 60.0 > (
        max(m.solo_duration_seconds for m in everyone) / 60.0 + MAX_POOL_DETOUR_MINUTES
    ):
        return InsertionResult(False, "pool route too long overall")

    # ---- Stage 5: score (lower is better) --------------------------
    route = routing_service.route([s.coord for s in best_order])

    solo_baseline = candidate.solo_duration_seconds
    added_seconds = max(
        0.0, best_total - _baseline_without(members, durations, index, trip_start)
    )

    occupancy_after = len(everyone)
    # Prefer nearly-full vehicles: filling one car before opening a second
    # is the primary business objective, so this term rewards higher
    # occupancy most strongly.
    occupancy_term = 1.0 - (occupancy_after - 1) / max(1, MAX_PASSENGERS - 1)

    distance_term = min(1.0, added_seconds / (solo_baseline or 1.0))
    detour_term = min(1.0, worst_detour / MAX_PASSENGER_DETOUR_MINUTES)

    wait_seconds = abs(
        (
            _as_utc(candidate.requested_pickup_at)
            - min(_as_utc(m.requested_pickup_at) for m in everyone)
        ).total_seconds()
    )
    wait_term = min(1.0, wait_seconds / (PICKUP_WINDOW_MINUTES * 60))

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
        total_distance_meters=route.total_distance_meters,
        worst_detour_minutes=worst_detour,
        is_estimate=route.is_estimate,
        stop_offsets_seconds=offsets,
    )


def _baseline_without(
    members: list[PoolMember],
    durations: dict[tuple[int, int], float],
    index: dict[tuple[UUID, str], int],
    trip_start: datetime | None = None,
) -> float:
    """Best route duration for the pool as it stands, before insertion —
    same trip_start anchor as the main search, so the schedule model
    (including any forced waits) stays consistent between the two
    numbers this gets subtracted from/into."""
    if not members:
        return 0.0
    total, _order, _offsets = _best_ordering(members, durations, index, trip_start)
    return total
