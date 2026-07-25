"""
Groups a set of bookings by time first, distance second.

Continuous matching (pool_insertion.py's evaluate_insertion, called from
find_pool_for_booking) still handles a booking the moment it's created —
nobody sits unassigned waiting for a batch. This module is what runs
periodically afterward (see dispatch_service.py:recluster_forming_pools)
to correct that greedy, order-dependent initial placement: passengers
who want pickup around the same time are grouped together first, and
distance only decides how to SPLIT that group across multiple cars once
there's more demand than one car holds — not the other way around, which
is what the per-booking continuous scoring effectively did before (it
weighted route efficiency well above pickup-time closeness).

Deliberately a greedy heuristic, not a globally-optimal partition
solver — true optimal partitioning into groups is a much harder
combinatorial problem, and this fleet's real per-wave volume (a handful
of bookings, not hundreds) doesn't need or reward that complexity. Every
group this produces is still validated through the exact same
evaluate_insertion feasibility engine (per-passenger detour cap, pool
detour cap, MAX_PASSENGERS) the rest of the system already relies on —
this module decides ORDER, not what counts as feasible.
"""

from datetime import datetime, timezone

from app.core.dispatch_config import MAX_PASSENGERS, TIME_CLUSTER_MINUTES
from app.services.geo import haversine_m
from app.services.pool_insertion import PoolMember, evaluate_insertion


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def time_cluster(
    members: list[PoolMember], threshold_minutes: float = TIME_CLUSTER_MINUTES
) -> list[list[PoolMember]]:
    """
    Sequential bucketing by requested pickup time: a new cluster starts
    whenever the gap to the previous booking (in time order) exceeds
    `threshold_minutes`. Chaining (A-B-C where A and C are further apart
    than the threshold but each adjacent pair isn't) is fine here — this
    only decides which bookings get CONSIDERED together for
    `cluster_by_proximity`; the hard PICKUP_WINDOW_MINUTES pairwise limit
    is still separately enforced inside evaluate_insertion regardless.
    """
    if not members:
        return []

    ordered = sorted(members, key=lambda m: _as_utc(m.requested_pickup_at))
    clusters: list[list[PoolMember]] = [[ordered[0]]]

    for prev, curr in zip(ordered, ordered[1:]):
        gap_minutes = (
            _as_utc(curr.requested_pickup_at) - _as_utc(prev.requested_pickup_at)
        ).total_seconds() / 60
        if gap_minutes > threshold_minutes:
            clusters.append([curr])
        else:
            clusters[-1].append(curr)

    return clusters


def cluster_by_proximity(members: list[PoolMember]) -> list[list[PoolMember]]:
    """
    Greedy nearest-neighbor grouping within a single time cluster. Seeds
    each group with the earliest-pickup unassigned booking, then
    repeatedly pulls in whichever remaining booking is geographically
    closest to the group (nearest-to-farthest, trying each in turn) and
    actually fits — same feasibility check used everywhere else in the
    system. A close-by candidate that fails (bad time-window fit, or
    would blow the detour guarantee) doesn't stall the group; the next-
    nearest one that fits gets tried instead.
    """
    remaining = sorted(members, key=lambda m: _as_utc(m.requested_pickup_at))
    groups: list[list[PoolMember]] = []

    while remaining:
        group = [remaining.pop(0)]

        # Seats, not member count — evaluate_insertion enforces the same
        # bound authoritatively below, this just stops looping once the
        # car is physically full.
        while sum(m.seats for m in group) < MAX_PASSENGERS and remaining:
            nearest_first = sorted(
                range(len(remaining)),
                key=lambda i: min(
                    haversine_m(*m.pickup, *remaining[i].pickup) for m in group
                ),
            )
            added = False
            for idx in nearest_first:
                candidate = remaining[idx]
                result = evaluate_insertion(group, candidate)
                if result.feasible:
                    group.append(candidate)
                    remaining.pop(idx)
                    added = True
                    break
            if not added:
                break  # nobody left fits this group

        groups.append(group)

    return groups


def regroup(members: list[PoolMember]) -> list[list[PoolMember]]:
    """Time-first, distance-second: the two steps combined."""
    result: list[list[PoolMember]] = []
    for cluster in time_cluster(members):
        result.extend(cluster_by_proximity(cluster))
    return result
