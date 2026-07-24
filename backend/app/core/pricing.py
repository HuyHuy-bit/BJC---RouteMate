"""
Fare calculation.

Deliberately flat per corridor, not distance-scaled. An earlier version
of this made price grow with the booking's point-to-point distance —
more defensible on paper, but it broke the thing that actually drives
this business: a customer can quote the price from memory before they
even open the app, every single time, with zero "how much will it be
this time" hesitation. That predictability is the product, not a
simplification of it.

Flat is still corridor-scoped rather than a single hardcoded constant,
so a future corridor with very different economics (a much longer
route, say) isn't forced to reuse this one's number — see
app/models/corridor.py:base_fare_vnd. Today there is exactly one
corridor and its rate is 150,000₫, so in practice this behaves exactly
like the original flat price.
"""

from app.models.corridor import Corridor

# A private booking pays what a fully-occupied shared car would earn.
PRIVATE_MULTIPLIER = 4


def price_for(corridor: Corridor, is_private: bool) -> int:
    shared = corridor.base_fare_vnd
    return shared * PRIVATE_MULTIPLIER if is_private else shared
