"""
Solves the actual best stop order for a small group of riders sharing a
car — this is a Pickup-and-Delivery Problem (PDP), not a plain TSP: each
rider has a pickup AND a dropoff, and the only hard constraint is that a
rider's pickup must come before their own dropoff (stops from different
riders can freely interleave, e.g. pick up A, pick up B, drop off A, drop
off B — realistic for a shared van).

For n riders there are 2n stops. The number of valid orderings is
(2n)! / 2^n (dropoff-before-pickup orderings are pruned during
construction, not generated and thrown away). At the n<=4 seats this app
allows, that's at most 2520 candidate orderings — cheap to brute-force
exactly in Python; no need for an approximate heuristic here.
"""

from dataclasses import dataclass
from uuid import UUID

from app.services.geo import Candidate, haversine_m


@dataclass
class Stop:
    booking_id: UUID
    kind: str  # "pickup" | "dropoff"
    lat: float
    lng: float


def _stops_for(members: list[Candidate]) -> list[Stop]:
    stops = []
    for m in members:
        stops.append(Stop(m.booking_id, "pickup", m.pickup_lat, m.pickup_lng))
        stops.append(Stop(m.booking_id, "dropoff", m.dropoff_lat, m.dropoff_lng))
    return stops


def _route_distance(order: list[Stop]) -> float:
    total = 0.0
    for a, b in zip(order, order[1:]):
        total += haversine_m(a.lat, a.lng, b.lat, b.lng)
    return total


def best_route(members: list[Candidate]) -> tuple[float, list[Stop]]:
    """
    Returns (total_distance_meters, ordered_stops) for the shortest valid
    stop sequence. For a single rider this is just their direct
    pickup->dropoff distance.
    """
    if not members:
        return 0.0, []
    if len(members) == 1:
        m = members[0]
        stops = _stops_for(members)
        return haversine_m(m.pickup_lat, m.pickup_lng, m.dropoff_lat, m.dropoff_lng), stops

    stops = _stops_for(members)
    picked_up: set[UUID] = set()
    used = [False] * len(stops)
    sequence: list[int] = []

    best_cost = float("inf")
    best_order: list[Stop] = []

    def backtrack():
        nonlocal best_cost, best_order
        if len(sequence) == len(stops):
            order = [stops[i] for i in sequence]
            cost = _route_distance(order)
            if cost < best_cost:
                best_cost = cost
                best_order = order
            return

        for i, stop in enumerate(stops):
            if used[i]:
                continue
            if stop.kind == "dropoff" and stop.booking_id not in picked_up:
                continue  # can't drop off before that rider's pickup

            used[i] = True
            added_pickup = False
            if stop.kind == "pickup":
                picked_up.add(stop.booking_id)
                added_pickup = True
            sequence.append(i)

            backtrack()

            sequence.pop()
            if added_pickup:
                picked_up.discard(stop.booking_id)
            used[i] = False

    backtrack()
    return best_cost, best_order


def pickup_order_ranks(ordered_stops: list[Stop]) -> dict[UUID, int]:
    """Maps booking_id -> 1-indexed rank of when that rider gets picked up."""
    ranks: dict[UUID, int] = {}
    rank = 0
    for stop in ordered_stops:
        if stop.kind == "pickup":
            rank += 1
            ranks[stop.booking_id] = rank
    return ranks
