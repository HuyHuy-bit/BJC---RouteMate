"""
Solves the actual best stop order for a small group of riders sharing a
car — this is a Pickup-and-Delivery Problem (PDP), not a plain TSP: each
rider has a pickup AND a dropoff, and the only hard constraint is that a
rider's pickup must come before their own dropoff (stops from different
riders can freely interleave, e.g. pick up A, pick up B, drop off A, drop
off B — realistic for a shared van).

For n riders there are 2n stops. The number of VALID orderings is
(2n)! / 2^n (dropoff-before-pickup orderings are pruned during
construction, never generated and thrown away). At the n<=4 seats this
app allows, that's at most 2520 candidate orderings — cheap to
brute-force exactly, and branch-and-bound pruning makes it far cheaper in
practice.

`solve_pdp` is the shared core: it takes a `cost(i, j)` callback so the
same exact search can minimize either straight-line distance or real
road-network duration (used by pool_insertion, passing a precomputed
duration matrix). This is what
lets pool_insertion drop its old raw-`itertools.permutations` search,
which capped the number of RAW permutations inspected (40,320 at 4
riders) below the cap before all VALID orderings (2,520) were even seen,
silently biasing results toward whoever joined the pool first.
"""

from collections.abc import Callable


def solve_pdp(
    kinds: list[str],
    owners: list,
    cost: Callable[[int, int], float],
    feasible: Callable[[int, float, dict], tuple[bool, float]] | None = None,
    start_cost: Callable[[int], float] | None = None,
) -> tuple[float, list[int], list[float]]:
    """
    Minimum-cost pickup-and-delivery ordering over `len(kinds)` stops, by
    exact constrained backtracking with branch-and-bound pruning.

    Each stop index i is a pickup or dropoff (`kinds[i]`) belonging to
    `owners[i]`; the only hard constraint is that an owner's pickup
    precedes their own dropoff. `cost(i, j)` is the leg cost from stop i
    to stop j — any non-negative metric (distance or duration).

    `feasible(stop_index, arrival, boarded_at)`, if given, is called
    before a stop is tentatively visited, with `arrival` = cumulative
    cost to reach it (before any wait) and `boarded_at` = a dict of
    owner -> arrival time at THEIR OWN pickup, for every owner currently
    "in the car" at this point in the partial route being built (kept in
    lockstep with the search's own pickup/backtrack bookkeeping, so it's
    always correct for whichever branch is being explored — a per-rider
    detour check at a dropoff stop just reads `boarded_at[owner]`
    straight out of it). Returns `(ok, wait)`: `ok=False` prunes that
    branch entirely (this stop can never be visited at this point in any
    route built from here); `wait` is additional time forced onto the
    schedule at that stop (e.g. the vehicle arrived early and must wait)
    — it's added to the running total and so correctly carries forward
    into every later stop's arrival time, exactly like a real delay
    would. Passing `feasible=None` recovers the original unconstrained
    search.

    `start_cost(stop_index)`, if given, is the cost of visiting that stop
    AS THE FIRST STOP — e.g. the leg from a vehicle's current position to
    that pickup. Without it, the first stop in any sequence costs 0 to
    "arrive" at (the search is free to start anywhere); with it, that
    deadhead leg becomes part of what the search minimizes, not invisible
    to it, and whichever stop actually gets visited first pays a real
    cost to reach.

    Returns `(best_total_cost, ordered_stop_indices, arrival_at_each)` —
    the third list is the actual schedule (cumulative cost, including any
    forced waits) at each stop in `ordered_stop_indices`, positionally
    aligned with it. Because dropoff-before-own-pickup branches are never
    entered, this only ever generates VALID orderings — so, unlike a
    raw-permutation search, it can't be truncated by a cap that fires
    before all valid orderings are seen.
    """
    n = len(kinds)
    if n == 0:
        return 0.0, [], []

    used = [False] * n
    picked: set = set()
    boarded_at: dict = {}
    seq: list[int] = []
    arrivals: list[float] = []
    best_cost = float("inf")
    best_order: list[int] = []
    best_arrivals: list[float] = []

    def backtrack(running: float) -> None:
        nonlocal best_cost, best_order, best_arrivals
        # Branch-and-bound: every remaining leg (and any forced wait) is
        # non-negative, so a partial route already at or above the best
        # complete route found so far can never beat it — abandon it now.
        if running >= best_cost:
            return
        if len(seq) == n:
            best_cost = running
            best_order = list(seq)
            best_arrivals = list(arrivals)
            return
        for i in range(n):
            if used[i]:
                continue
            if kinds[i] == "dropoff" and owners[i] not in picked:
                continue  # can't drop off before that rider's pickup
            if not seq:
                step = start_cost(i) if start_cost is not None else 0.0
            else:
                step = cost(seq[-1], i)
            arrival = running + step
            wait = 0.0
            if feasible is not None:
                ok, wait = feasible(i, arrival, boarded_at)
                if not ok:
                    continue  # this stop can't be scheduled here — prune
            used[i] = True
            is_pickup = kinds[i] == "pickup"
            if is_pickup:
                picked.add(owners[i])
                boarded_at[owners[i]] = arrival + wait
            seq.append(i)
            arrivals.append(arrival + wait)
            backtrack(arrival + wait)
            arrivals.pop()
            seq.pop()
            if is_pickup:
                picked.discard(owners[i])
                del boarded_at[owners[i]]
            used[i] = False

    backtrack(0.0)
    return best_cost, best_order, best_arrivals
