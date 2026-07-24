"""
Pure-function coverage for fare calculation — no database needed.

Pricing is deliberately flat per corridor (see app/core/pricing.py for
why) — there is no distance input at all, on purpose.
"""

from app.core.pricing import PRIVATE_MULTIPLIER, price_for
from app.models.corridor import Corridor

CORRIDOR = Corridor(
    name="Bắc Giang ⇄ Hà Nội",
    home_hub_name="Bắc Giang",
    home_hub_lat=21.2731,
    home_hub_lng=106.1946,
    away_hub_name="Hà Nội",
    away_hub_lat=21.0285,
    away_hub_lng=105.8542,
    base_fare_vnd=150_000,
)


def test_shared_price_is_the_corridor_flat_rate():
    assert price_for(CORRIDOR, is_private=False) == 150_000


def test_price_does_not_vary_by_anything_except_privacy():
    # Same corridor, called repeatedly — must always return the same
    # number. There is nothing else for it to depend on.
    prices = {price_for(CORRIDOR, is_private=False) for _ in range(5)}
    assert prices == {150_000}


def test_private_is_multiplier_times_shared():
    shared = price_for(CORRIDOR, is_private=False)
    private = price_for(CORRIDOR, is_private=True)
    assert private == shared * PRIVATE_MULTIPLIER
    assert private == 600_000


def test_different_corridors_can_have_different_flat_rates():
    other = Corridor(
        name="test-other-corridor",
        home_hub_name="A",
        home_hub_lat=0,
        home_hub_lng=0,
        away_hub_name="B",
        away_hub_lat=0,
        away_hub_lng=0,
        base_fare_vnd=200_000,
    )
    assert price_for(CORRIDOR, is_private=False) == 150_000
    assert price_for(other, is_private=False) == 200_000
