"""
Rush-hour travel time.

The operator's actual observation: nothing about WAITING changes during
rush hour — what changes is that the drive itself takes longer. A pool
departing at 17:30 covers the same corridor more slowly than one leaving
at 14:00, and the routing provider's estimate reflects traffic at the
moment it was QUERIED, not at the moment the car will actually depart.
A pool sealed at 16:00 for a 17:30 run was being planned on 16:00 roads.

That mattered in three places at once, all of them silently optimistic:
  - ETAs promised to the customer
  - whether a pickup lands inside its schedule window
  - the per-passenger detour guarantee

The multiplier below is applied CONSISTENTLY to route legs and to the
stored solo baseline they're compared against. That consistency is the
whole game: scale one side only and "detour = in-car minus solo" stops
meaning anything (see compute_solo_baseline's docstring for why that
subtraction has to stay honest). Scaling both means a 10-minute detour
in traffic correctly reads as ~13 minutes rather than staying 10.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.dispatch_config import (
    LOCAL_TIMEZONE,
    PEAK_HOURS_LOCAL,
    PEAK_TRAVEL_MULTIPLIER,
)
from app.core.timeutil import as_utc

_LOCAL_TZ = ZoneInfo(LOCAL_TIMEZONE)


def travel_multiplier(at: datetime | None) -> float:
    """
    How much longer a drive takes if it happens at `at`.

    1.0 outside peak hours. Evaluated in LOCAL time — the business and
    its traffic are in one place, and comparing a stored UTC timestamp
    against local clock hours without converting would shift the peak
    window by the UTC offset (7 hours here, i.e. completely wrong).

    Deliberately a function of departure time only, not of each leg's
    own moment. A leg-by-leg model would be more precise for a trip
    straddling the boundary, but it needs the schedule to compute the
    multiplier and the multiplier to compute the schedule — and this
    corridor's runs are short enough relative to the 2-hour window that
    the extra machinery buys very little.
    """
    if at is None:
        return 1.0
    hour = as_utc(at).astimezone(_LOCAL_TZ).hour
    for start_hour, end_hour in PEAK_HOURS_LOCAL:
        if start_hour <= hour < end_hour:
            return PEAK_TRAVEL_MULTIPLIER
    return 1.0
