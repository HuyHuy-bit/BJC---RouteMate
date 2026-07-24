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
) -> tuple[float, list[Stop]]:
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
    """
    stops = _stops_of(members)
    if not stops:
        return 0.0, []
    kinds = [s.kind for s in stops]
    owners = [s.booking_id for s in stops]

    def cost(i: int, j: int) -> float:
        return durations[
            (index[(stops[i].booking_id, stops[i].kind)],
             index[(stops[j].booking_id, stops[j].kind)])
        ]

    total, order = solve_pdp(kinds, owners, cost)
    return total, [stops[i] for i in order]


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

    # ---- Stage 3: exact ordering (branch-and-bound, no cap) --------
    best_total, best_order = _best_ordering(everyone, durations, index)
    if not best_order:
        return InsertionResult(False, "no valid stop ordering found")

    # ---- Stage 4: per-passenger service guarantee ------------------
    # Walk the chosen route accumulating elapsed time, so each passenger's
    # in-car duration can be compared to their own solo baseline.
    elapsed = 0.0
    boarded_at: dict[UUID, float] = {}
    detours: dict[UUID, float] = {}

    for i, stop in enumerate(best_order):
        if i > 0:
            prev = best_order[i - 1]
            elapsed += durations[
                (index[(prev.booking_id, prev.kind)], index[(stop.booking_id, stop.kind)])
            ]
        if stop.kind == "pickup":
            boarded_at[stop.booking_id] = elapsed
        else:
            solo = next(m.solo_duration_seconds for m in everyone if m.booking_id == stop.booking_id)
            in_car = elapsed - boarded_at[stop.booking_id]
            detours[stop.booking_id] = (in_car - solo) / 60.0

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
    added_seconds = max(0.0, best_total - _baseline_without(members, durations, index))

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
    )


def _baseline_without(
    members: list[PoolMember],
    durations: dict[tuple[int, int], float],
    index: dict[tuple[UUID, str], int],
) -> float:
    """Best route duration for the pool as it stands, before insertion."""
    if not members:
        return 0.0
    total, _ = _best_ordering(members, durations, index)
    return total
