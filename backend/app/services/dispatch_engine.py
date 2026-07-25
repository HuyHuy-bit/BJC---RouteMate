"""
The DispatchEngine turns this from a calculator into a dispatch system.

The previous design required a human to click "Ghép chuyến" or nothing
ever left the depot: bookings accumulated invisibly and a customer who
booked at 08:00 waited until someone remembered to press a button. Since
the stated business goal is reducing operational staff, that was the
central flaw — the math was automated, the job was not.

This runs on a timer and answers one question per tick: for each pool
still forming, should it depart now, wait, or escalate?

Seal triggers, in priority order:
  1. FULL          — no reason to hold a full car
  2. DEADLINE + viable  — enough passengers to justify the run
  3. DEADLINE + return leg — the vehicle drives home regardless, so a
     single passenger still departs (this rule came from the operator and
     is genuinely good economics)
  4. DEADLINE + outbound + only 1 passenger — NOT silently stranded:
     escalated explicitly, because this is where a naive system quietly
     loses customers.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

from app.core.dispatch_config import (
    MAX_PASSENGERS,
    MAX_POOL_WAIT_MINUTES,
    MIN_POOL_SIZE_OUTBOUND,
    MIN_POOL_SIZE_RETURN,
)

logger = logging.getLogger(__name__)


class SealDecision(str, Enum):
    SEAL = "seal"
    WAIT = "wait"
    ESCALATE = "escalate"


@dataclass
class PoolSnapshot:
    """Just enough pool state to make a dispatch decision."""

    pool_id: UUID
    direction: str  # "outbound" | "return"
    passenger_count: int
    earliest_requested_pickup: datetime
    created_at: datetime
    is_private: bool = False
    # Physical seats occupied (one booking can be a family of several)
    # and what the committed vehicle can actually hold. Kept distinct
    # from passenger_count, which is a BOOKING count — "is this car
    # full?" is a seat question, but "is this pool viable to run?" is a
    # booking question, and conflating them was wrong in both
    # directions. Defaults keep every existing construction site valid.
    seat_count: int = 0
    capacity: int = MAX_PASSENGERS


@dataclass
class DispatchDecision:
    pool_id: UUID
    decision: SealDecision
    reason: str
    # Populated on ESCALATE so the dispatcher sees actionable options
    # rather than a bare failure.
    options: list[str] | None = None


def departure_deadline(
    pool: PoolSnapshot, max_wait_minutes: int = MAX_POOL_WAIT_MINUTES
) -> datetime:
    """
    A pool must decide by this time. Anchored to the EARLIEST requested
    pickup in the pool, not to when the pool was created — the promise
    belongs to the customer who has been waiting longest.
    """
    return pool.earliest_requested_pickup + timedelta(minutes=max_wait_minutes)


def min_viable_size(direction: str) -> int:
    return (
        MIN_POOL_SIZE_RETURN
        if direction == "return"
        else MIN_POOL_SIZE_OUTBOUND
    )


def evaluate_pool(
    pool: PoolSnapshot,
    now: datetime | None = None,
    max_wait_minutes: int = MAX_POOL_WAIT_MINUTES,
) -> DispatchDecision:
    """Decides what should happen to one forming pool, right now."""
    now = now or datetime.now(timezone.utc)

    # A private booking is its own car by definition — never held waiting
    # for companions it will never accept.
    if pool.is_private:
        return DispatchDecision(pool.pool_id, SealDecision.SEAL, "private hire")

    # Full is a SEAT question, not a booking-count one: two bookings of
    # two seats each fill a 4-seat car just as completely as four solo
    # riders do, and counting rows would have kept that car waiting for
    # passengers it has no room for.
    if pool.seat_count >= pool.capacity:
        return DispatchDecision(
            pool.pool_id, SealDecision.SEAL, f"full ({pool.seat_count} seats)"
        )

    deadline = departure_deadline(pool, max_wait_minutes)
    if now < deadline:
        remaining = (deadline - now).total_seconds() / 60
        return DispatchDecision(
            pool.pool_id,
            SealDecision.WAIT,
            f"{remaining:.0f} min left to fill",
        )

    # Past deadline from here on.
    needed = min_viable_size(pool.direction)
    if pool.passenger_count >= needed:
        return DispatchDecision(
            pool.pool_id,
            SealDecision.SEAL,
            f"deadline reached with {pool.passenger_count} passenger(s)",
        )

    if pool.passenger_count == 0:
        return DispatchDecision(
            pool.pool_id, SealDecision.WAIT, "empty pool, nothing to dispatch"
        )

    # Outbound, past deadline, under-filled. The customer must not be left
    # in silence — surface real choices instead.
    return DispatchDecision(
        pool.pool_id,
        SealDecision.ESCALATE,
        f"outbound pool has {pool.passenger_count} of {needed} needed passengers",
        # Note "cancel", not "refund_and_cancel": customers pay only
        # after the trip is finished, so a booking that never runs has
        # no money to give back. The old label implied a refund step
        # that doesn't exist in this business.
        options=[
            "merge_with_nearby_pool",
            "offer_extended_wait",
            "offer_private_upgrade",
            "dispatch_at_loss",
            "cancel",
        ],
    )


def run_dispatch_tick(
    pools: list[PoolSnapshot],
    now: datetime | None = None,
    max_wait_minutes: int = MAX_POOL_WAIT_MINUTES,
) -> list[DispatchDecision]:
    """
    One pass over every forming pool. Pure function of its inputs so it
    can be tested without a database, and so the persistence layer stays
    free to apply the decisions transactionally.
    """
    now = now or datetime.now(timezone.utc)
    decisions = [evaluate_pool(p, now, max_wait_minutes) for p in pools]

    sealed = sum(1 for d in decisions if d.decision is SealDecision.SEAL)
    escalated = sum(1 for d in decisions if d.decision is SealDecision.ESCALATE)
    if sealed or escalated:
        logger.info(
            "dispatch tick: %s pools -> %s sealed, %s escalated",
            len(pools),
            sealed,
            escalated,
        )
    return decisions


def find_merge_candidate(
    lonely: PoolSnapshot, others: list[PoolSnapshot]
) -> PoolSnapshot | None:
    """
    Last resort before stranding an under-filled outbound pool: another
    under-filled pool going the same way at a compatible time. Merging two
    half-empty cars into one is the single most valuable action available
    at deadline — it serves both sets of customers AND removes a vehicle
    from the road.
    """
    best: PoolSnapshot | None = None
    best_gap = None

    for other in others:
        if other.pool_id == lonely.pool_id:
            continue
        if other.direction != lonely.direction:
            continue
        if other.is_private or lonely.is_private:
            continue
        # Seats, not bookings — and against the smaller of the two
        # pools' capacities, since the merged group has to fit whichever
        # car actually ends up taking it.
        if other.seat_count + lonely.seat_count > min(other.capacity, lonely.capacity):
            continue

        gap = abs(
            (
                other.earliest_requested_pickup - lonely.earliest_requested_pickup
            ).total_seconds()
        )
        if best_gap is None or gap < best_gap:
            best, best_gap = other, gap

    return best
