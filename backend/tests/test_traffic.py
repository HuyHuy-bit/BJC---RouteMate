"""
Rush hour makes the drive longer, not the wait.

The operator's actual observation was that a trip around 5-7pm takes
longer to complete — not that pools should sit waiting longer. So the
correction belongs on travel time, and it has to reach every number
derived from it: the ETA the customer is given, whether a pickup still
lands inside its window, and the detour each passenger absorbs.

The subtle part is CONSISTENCY. Route legs and the stored solo baseline
they're compared against must be scaled by the same factor, or
"detour = in-car minus solo" silently stops meaning anything.
"""

import time
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.dispatch_config import (
    LOCAL_TIMEZONE,
    PEAK_HOURS_LOCAL,
    PEAK_TRAVEL_MULTIPLIER,
)
from app.services.pool_insertion import (
    PoolMember,
    _best_ordering,
    compute_solo_baseline,
)
from app.services.routing import routing_service
from app.services.traffic import travel_multiplier

LOCAL = ZoneInfo(LOCAL_TIMEZONE)
BAC_GIANG = (21.2731, 106.1946)
HA_NOI = (21.0285, 105.8542)


@pytest.fixture(autouse=True)
def force_degraded_routing():
    original = routing_service._circuit_open_until
    routing_service._circuit_open_until = time.time() + 3600
    yield
    routing_service._circuit_open_until = original


def _local(hour, minute=0):
    return datetime(2026, 7, 27, hour, minute, tzinfo=LOCAL)


# -- the multiplier itself --------------------------------------------


def test_offpeak_hours_are_unscaled():
    assert travel_multiplier(_local(9)) == 1.0
    assert travel_multiplier(_local(14)) == 1.0
    assert travel_multiplier(_local(23)) == 1.0


def test_peak_hours_are_scaled():
    start, end = PEAK_HOURS_LOCAL[0]
    assert travel_multiplier(_local(start)) == PEAK_TRAVEL_MULTIPLIER
    assert travel_multiplier(_local(end - 1, 59)) == PEAK_TRAVEL_MULTIPLIER


def test_the_window_is_half_open_so_it_ends_cleanly():
    start, end = PEAK_HOURS_LOCAL[0]
    # The hour BEFORE the window starts, and the hour the window ends
    # on, are both ordinary traffic.
    assert travel_multiplier(_local(start - 1)) == 1.0
    assert travel_multiplier(_local(end)) == 1.0


def test_peak_is_judged_in_local_time_not_utc():
    # The whole point: these timestamps are stored in UTC, and Hà Nội is
    # UTC+7. Comparing a UTC hour against local clock hours without
    # converting would shift the rush-hour window by seven hours — i.e.
    # apply it to the wrong half of the day entirely.
    start, _end = PEAK_HOURS_LOCAL[0]
    peak_local = _local(start, 30)
    same_moment_utc = peak_local.astimezone(timezone.utc)

    assert same_moment_utc.hour != peak_local.hour  # genuinely differs
    assert travel_multiplier(same_moment_utc) == PEAK_TRAVEL_MULTIPLIER


def test_none_is_treated_as_ordinary_traffic():
    assert travel_multiplier(None) == 1.0


# -- effect on real routing -------------------------------------------


def _member(pickup, at):
    return PoolMember(
        booking_id=uuid4(),
        pickup=pickup,
        dropoff=HA_NOI,
        requested_pickup_at=at,
        solo_duration_seconds=compute_solo_baseline(pickup, HA_NOI),
    )


def _index_for(members):
    index, slot = {}, 0
    for m in members:
        index[(m.booking_id, "pickup")] = slot
        slot += 1
        index[(m.booking_id, "dropoff")] = slot
        slot += 1
    return index


def _durations(index, n_slots, per_leg=600.0):
    return {(i, j): per_leg for i in range(n_slots) for j in range(n_slots)}


def test_a_peak_hour_route_is_reported_as_taking_longer():
    peak_at = _local(PEAK_HOURS_LOCAL[0][0], 30)
    quiet_at = _local(10, 30)

    def total_for(when):
        members = [_member(BAC_GIANG, when)]
        index = _index_for(members)
        total, _order, _offsets = _best_ordering(
            members, _durations(index, 2), index, when
        )
        return total

    peak_total = total_for(peak_at)
    quiet_total = total_for(quiet_at)

    assert peak_total > quiet_total, "rush hour must lengthen the estimate"
    assert peak_total == pytest.approx(quiet_total * PEAK_TRAVEL_MULTIPLIER)


def test_the_solo_rider_fast_path_is_scaled_too():
    # Regression. The multiplier was originally only wired into the
    # multi-rider search, but a pool with ONE booking skips that search
    # entirely via a fast path — and one booking is how every pool
    # starts. The feature looked correct in unit tests and did nothing
    # at all to real single-rider ETAs until this path was fixed too.
    from app.services.pool_insertion import solve_group_ordering

    peak_at = _local(PEAK_HOURS_LOCAL[0][0], 30)
    quiet_at = _local(10, 30)

    peak_total, _o, _off = solve_group_ordering([_member(BAC_GIANG, peak_at)])
    quiet_total, _o2, _off2 = solve_group_ordering([_member(BAC_GIANG, quiet_at)])

    assert peak_total > quiet_total, (
        "a single-rider trip ignored rush hour — the fast path skipped the "
        "multiplier"
    )
    assert peak_total == pytest.approx(quiet_total * PEAK_TRAVEL_MULTIPLIER)


def test_detour_is_not_inflated_just_because_it_is_rush_hour():
    # The consistency guarantee. A solo rider's in-car time and their own
    # baseline both stretch by the same factor at peak, so their detour
    # stays ~0 — traffic is not their detour. Scaling only the route side
    # would have made every peak trip look like a guarantee breach.
    for when in (_local(10, 30), _local(PEAK_HOURS_LOCAL[0][0], 30)):
        members = [_member(BAC_GIANG, when)]
        index = _index_for(members)
        leg = members[0].solo_duration_seconds
        _total, _order, offsets = _best_ordering(
            members, _durations(index, 2, per_leg=leg), index, when
        )
        off = offsets[members[0].booking_id]
        in_car = off["dropoff"] - off["pickup"]
        scaled_baseline = members[0].solo_duration_seconds * travel_multiplier(when)
        detour_minutes = (in_car - scaled_baseline) / 60.0
        assert abs(detour_minutes) < 1.0, (
            f"a solo rider showed a {detour_minutes:.1f} min detour at "
            f"{when:%H:%M} — the two sides of the subtraction disagree"
        )
