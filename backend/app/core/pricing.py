"""
Fare calculation.

Used to be a single flat number regardless of distance or corridor — a
passenger going the full corridor and one going a short middle segment
paid the same price, which loses money on every short-hop booking and
can't express more than one corridor's worth of distance at all. Now the
fare is corridor-scoped (see app/models/corridor.py:base_fare_vnd/
per_km_vnd) and grows with the booking's actual point-to-point distance.
"""

from app.models.corridor import Corridor

# Floor so a very short hop still covers dispatch overhead.
MIN_FARE_VND = 30_000

# Cash-friendly denomination — this market is still cash-heavy, and a
# price like "153,482 ₫" is not something a driver can make change for.
CASH_ROUNDING_VND = 5_000

# A private booking pays what a fully-occupied shared car would earn for
# the same distance — unchanged business rule, just now applied to a
# distance-based fare instead of a flat one.
PRIVATE_MULTIPLIER = 4


def _round_to_cash(amount: float) -> int:
    return int(round(amount / CASH_ROUNDING_VND) * CASH_ROUNDING_VND)


def price_for(corridor: Corridor, is_private: bool, distance_meters: float) -> int:
    km = distance_meters / 1000.0
    shared = max(MIN_FARE_VND, corridor.base_fare_vnd + corridor.per_km_vnd * km)
    shared = _round_to_cash(shared)
    return shared * PRIVATE_MULTIPLIER if is_private else shared
