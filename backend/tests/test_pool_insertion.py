"""
Phase 1 coverage: the exact pickup-and-delivery ordering search.

The core correctness claim is that solve_pdp returns the true minimum
over ALL valid orderings — not a subset biased by a raw-permutation cap,
which is what the code this replaced actually did (it counted up to
MAX_PERMUTATIONS=5000 RAW permutations before filtering, but 4 riders
have 40,320 raw permutations and only 2,520 valid ones, so the cap fired
before every valid ordering was seen). These tests pin that down by
comparing against an independent exhaustive reference.
"""

import random
from itertools import permutations
from uuid import uuid4

from app.services.route_solver import solve_pdp


def _reference_best(kinds, owners, cost):
    """
    Dead-simple exhaustive reference: every permutation of stop indices,
    keep the valid ones (each owner's pickup before its dropoff), return
    the minimum total cost. Deliberately the naive O(n!) version — slow
    but obviously correct — to validate the branch-and-bound solver.
    """
    n = len(kinds)
    best = float("inf")
    best_order = []
    for perm in permutations(range(n)):
        picked = set()
        ok = True
        for idx in perm:
            if kinds[idx] == "pickup":
                picked.add(owners[idx])
            elif owners[idx] not in picked:
                ok = False
                break
        if not ok:
            continue
        total = sum(cost(perm[k], perm[k + 1]) for k in range(n - 1))
        if total < best:
            best = total
            best_order = list(perm)
    return best, best_order


def _stops(n_riders):
    """Parallel kinds/owners arrays for n riders, pickup then dropoff."""
    kinds, owners = [], []
    for _ in range(n_riders):
        oid = uuid4()
        kinds.append("pickup")
        owners.append(oid)
        kinds.append("dropoff")
        owners.append(oid)
    return kinds, owners


def test_respects_pickup_before_dropoff_precedence():
    kinds, owners = _stops(3)
    matrix = {(i, j): random.random() for i in range(6) for j in range(6)}
    _, order, _arrivals = solve_pdp(kinds, owners, lambda i, j: matrix[(i, j)])
    seen = set()
    for idx in order:
        if kinds[idx] == "pickup":
            seen.add(owners[idx])
        else:
            assert owners[idx] in seen, "dropoff scheduled before its own pickup"


def test_matches_exhaustive_reference_on_random_matrices():
    rng = random.Random(1234)
    for n_riders in (2, 3, 4):
        for _ in range(20):
            kinds, owners = _stops(n_riders)
            n = len(kinds)
            matrix = {(i, j): rng.uniform(1, 100) for i in range(n) for j in range(n)}
            cost = lambda i, j: matrix[(i, j)]  # noqa: E731
            got_cost, _, _arrivals = solve_pdp(kinds, owners, cost)
            ref_cost, _ = _reference_best(kinds, owners, cost)
            assert abs(got_cost - ref_cost) < 1e-9, (
                f"{n_riders} riders: solver {got_cost} != reference {ref_cost}"
            )


def test_finds_interleaved_optimum_not_naive_fifo():
    # Two riders A and B. Construct costs so the cheapest route
    # interleaves (pickup A, pickup B, dropoff A, dropoff B) and the
    # naive "serve each rider fully in join order" route (pA, dA, pB, dB)
    # is strictly worse.
    A, B = uuid4(), uuid4()
    kinds = ["pickup", "dropoff", "pickup", "dropoff"]
    owners = [A, A, B, B]
    # indices: 0=pA, 1=dA, 2=pB, 3=dB
    # Make legs pA->pB, pB->dA, dA->dB all cheap; make pA->dA expensive so
    # dropping A off before picking up B is costly.
    big, small = 100.0, 1.0
    legs = {
        (0, 1): big, (0, 2): small, (0, 3): big,
        (1, 0): big, (1, 2): big, (1, 3): big,
        (2, 0): big, (2, 1): small, (2, 3): big,
        (3, 0): big, (3, 1): big, (3, 2): big,
    }
    cost = lambda i, j: legs[(i, j)]  # noqa: E731
    total, order, _arrivals = solve_pdp(kinds, owners, cost)
    # Optimal interleaved route: pA(0) -> pB(2) -> dA(1) -> dB(3)
    assert order == [0, 2, 1, 3]
    assert total == small + small + big  # 1 + 1 + 100 = 102

    fifo_cost = legs[(0, 1)] + legs[(1, 2)] + legs[(2, 3)]  # pA->dA->pB->dB
    assert total < fifo_cost


def test_optimum_late_in_lexicographic_order_is_still_found():
    # The old raw-permutation search walked permutations lexicographically
    # and capped how many it inspected. Put the unique optimum at a
    # permutation that sorts LATE, to prove the new search isn't
    # order-biased. With 4 riders (8 stops) the optimal here pins the
    # last-joined rider's pickup first.
    riders = [uuid4() for _ in range(4)]
    kinds, owners = [], []
    for oid in riders:
        kinds += ["pickup", "dropoff"]
        owners += [oid, oid]
    n = 8
    # Uniform high cost everywhere...
    legs = {(i, j): 50.0 for i in range(n) for j in range(n)}
    # ...except a single cheap chain that happens to start at the LAST
    # rider's pickup (index 6) — lexicographically late.
    cheap_chain = [6, 7, 4, 5, 2, 3, 0, 1]
    for a, b in zip(cheap_chain, cheap_chain[1:]):
        legs[(a, b)] = 1.0
    cost = lambda i, j: legs[(i, j)]  # noqa: E731

    total, order, _arrivals = solve_pdp(kinds, owners, cost)
    ref_total, _ = _reference_best(kinds, owners, cost)
    assert abs(total - ref_total) < 1e-9
    assert order == cheap_chain


def test_start_cost_anchors_the_route_and_is_included_in_total():
    # Phase 4: a fixed starting point (a vehicle's position) should
    # change which stop gets visited first, and the leg from that start
    # to the first real stop should count toward the total — deadhead
    # distance becomes part of what's minimized, not invisible to it.
    A, B = uuid4(), uuid4()
    kinds = ["pickup", "dropoff", "pickup", "dropoff"]
    owners = [A, A, B, B]
    # 0=pA, 1=dA, 2=pB, 3=dB — a uniform-cost chain, so without an
    # anchor the search is free to start wherever, and any minimal
    # route costs exactly 3 legs.
    legs = {(i, j): 1.0 for i in range(4) for j in range(4)}
    cost = lambda i, j: legs[(i, j)]  # noqa: E731

    total_free, _order_free, _ = solve_pdp(kinds, owners, cost)
    assert total_free == 3.0

    # Anchor makes starting at B's pickup (index 2) nearly free and
    # starting at A's pickup (index 0) hugely expensive.
    def start_cost(i):
        return 0.0 if i == 2 else 1000.0

    total_anchored, order_anchored, arrivals = solve_pdp(
        kinds, owners, cost, start_cost=start_cost
    )
    assert order_anchored[0] == 2  # starts at pB, not pA
    assert arrivals[0] == 0.0  # the (cheap) start leg is baked into the schedule
    assert total_anchored < 1000.0  # never seriously considers starting at pA
