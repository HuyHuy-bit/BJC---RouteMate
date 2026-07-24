"""
Pure-function coverage for fare calculation — no database needed.
"""

from app.core.pricing import (
    CASH_ROUNDING_VND,
    MIN_FARE_VND,
    PRIVATE_MULTIPLIER,
    price_for,
)
from app.models.corridor import Corridor

CORRIDOR = Corridor(
    name="Bắc Giang ⇄ Hà Nội",
    home_hub_name="Bắc Giang",
    home_hub_lat=21.2731,
    home_hub_lng=106.1946,
    away_hub_name="Hà Nội",
    away_hub_lat=21.0285,
    away_hub_lng=105.8542,
    base_fare_vnd=50_000,
    per_km_vnd=2_000,
)


def test_full_corridor_distance_matches_legacy_flat_price():
    # 50km was chosen when seeding this corridor specifically so the
    # full-length fare lands on the flat price this replaced.
    price = price_for(CORRIDOR, is_private=False, distance_meters=50_000)
    assert price == 150_000


def test_short_hop_costs_less_than_full_corridor():
    short = price_for(CORRIDOR, is_private=False, distance_meters=5_000)
    full = price_for(CORRIDOR, is_private=False, distance_meters=50_000)
    assert short < full


def test_floor_applies_when_corridor_rate_would_undercut_it():
    # A corridor whose base fare alone sits below the floor — the floor
    # exists precisely to guard against a low/misconfigured rate like
    # this, not something the seeded production corridor ever triggers.
    cheap_corridor = Corridor(
        name="test-cheap",
        home_hub_name="A",
        home_hub_lat=0,
        home_hub_lng=0,
        away_hub_name="B",
        away_hub_lat=0,
        away_hub_lng=0,
        base_fare_vnd=5_000,
        per_km_vnd=100,
    )
    price = price_for(cheap_corridor, is_private=False, distance_meters=0)
    assert price == MIN_FARE_VND


def test_price_is_rounded_to_cash_denomination():
    # An odd distance that would otherwise produce a non-round number.
    price = price_for(CORRIDOR, is_private=False, distance_meters=17_345)
    assert price % CASH_ROUNDING_VND == 0


def test_private_is_multiplier_times_shared():
    shared = price_for(CORRIDOR, is_private=False, distance_meters=30_000)
    private = price_for(CORRIDOR, is_private=True, distance_meters=30_000)
    assert private == shared * PRIVATE_MULTIPLIER
