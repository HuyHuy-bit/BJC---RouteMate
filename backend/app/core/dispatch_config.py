"""
Every tunable dispatch parameter in one place, so operations can be
adjusted without hunting through algorithm code — and so a peak/holiday
profile can override them wholesale later.
"""

# --- Capacity ---
# Passenger seats, excluding the driver. If Thành Công's "xe 4 chỗ" means
# 4 seats TOTAL (driver + 3 passengers), change this to 3 — it is the
# single source of truth for capacity across matching and dispatch.
MAX_PASSENGERS = 4

# --- Routing provider limits ---
# Goong's Distance Matrix rejects any request above this many
# origin x destination elements with a bare HTTP 400. Verified
# empirically against the live API: 10x10 (100) succeeds, 11x11 (121)
# does not. RoutingService.matrix chunks larger requests rather than
# letting them fail — a failed matrix silently degrades every pair in
# it to straight-line estimates, which is far worse than issuing two
# requests.
MATRIX_MAX_ELEMENTS = 100

# --- Vehicle position ---
# A Vehicle.last_location_at older than this is treated the same as "no
# location at all" (sorted last, never excluded) when picking the
# nearest vehicle for a trip — a driver's phone that stopped pinging an
# hour ago is not still telling the truth about where the car is.
VEHICLE_LOCATION_STALE_MINUTES = 10

# --- Time windows ---
# Two bookings can only share a car if their requested pickup times fall
# within this window of each other. Replaces the old "same calendar date"
# bucketing, which wrongly matched 06:00 with 22:00 and wrongly refused
# to match 23:50 with 00:10. This is the absolute ceiling — never
# exceeded regardless of anything else.
#
# Note this ceiling is NOT the limit you will observe in practice. The
# per-passenger detour cap below binds first: whoever boards earliest
# sits in the car for the whole gap, and that time counts against their
# own detour allowance. Measured end to end, two otherwise-identical
# bookings stop being poolable around 20 minutes apart. This number was
# lowered 45 -> 30 so the config stops advertising a window the system
# will not actually honour.
PICKUP_WINDOW_MINUTES = 30

# How close pickup times need to be to count as "the same wave" of
# demand for the periodic re-clustering pass (see reclustering.py) —
# deliberately tighter than PICKUP_WINDOW_MINUTES. Time is the PRIMARY
# grouping signal now: passengers leaving around the same time get
# grouped together first, and only get split across multiple cars by
# geographic proximity once one wave has more demand than a single car.
TIME_CLUSTER_MINUTES = 20

# --- Schedule-window enforcement ---
# A pickup stop's SCHEDULED arrival — from the real per-leg route walk,
# not just the raw pairwise "requested times within 45 min" check above —
# must fall within these tolerances of that passenger's own
# requested_pickup_at. Deliberately asymmetric: arriving early costs the
# passenger nothing (the vehicle waits for them rather than picking them
# up "for free" early — see the forced-wait modeling in
# pool_insertion.py), arriving late breaks the promise actually made.
EARLY_PICKUP_TOLERANCE_MINUTES = 5
LATE_PICKUP_TOLERANCE_MINUTES = 15

# How long a forming pool waits for more passengers before it must decide
# to depart or escalate.
#
# Lowered 45 -> 30 by operator decision, for punctuality. Worth knowing
# what it costs: a round trip on this corridor needs roughly 3 paid
# seats to break even, and cutting the fill window by a third gives a
# pool fewer chances to reach that. If average seats per trip falls
# after this change, this is the first knob to put back.
MAX_POOL_WAIT_MINUTES = 30

# --- Rush hour ---
# Peak doesn't change how long a pool WAITS to fill — it changes how
# long the drive takes. See app/services/traffic.py. Hours are LOCAL
# clock hours, half-open [start, end): (17, 19) means 17:00–18:59.
LOCAL_TIMEZONE = "Asia/Ho_Chi_Minh"
PEAK_HOURS_LOCAL = ((17, 19),)

# How much longer the same route takes during those hours. 1.3 = 30%
# longer. A starting estimate, not a measurement — worth revisiting
# against real completed-trip durations once there's a season of them.
PEAK_TRAVEL_MULTIPLIER = 1.3

# --- Return-leg vehicle reuse ---
# A vehicle finishing its outbound run is treated as a candidate for a
# return booking instead of always dispatching (or waiting for) a
# separate car — the van is going back to base regardless. These bound
# how good a fit has to be time-wise: too late and the customer waits
# past their requested pickup; too early and the vehicle would sit idle
# for an unreasonable stretch rather than this being a genuine "already
# heading that way" match.
RETURN_VEHICLE_LATE_TOLERANCE_MINUTES = 15
RETURN_VEHICLE_MATCH_WINDOW_MINUTES = 60

# --- Per-passenger service guarantee ---
# No passenger may spend more than this many minutes longer in the car
# than they would have on a direct solo trip. This is a PASSENGER
# experience constraint, unlike the old fleet-cost "max added km" check.
MAX_PASSENGER_DETOUR_MINUTES = 15

# --- Fleet-level cost guard (secondary to the per-passenger rule) ---
MAX_POOL_DETOUR_MINUTES = 35

# --- Scoring weights (must sum to 1.0) ---
# Occupancy used to be weighted highest (0.30) on the reasoning that
# filling one car before opening a second is the primary business
# objective — true, but that objective is already served STRUCTURALLY:
# continuous matching always tries an existing pool before opening a new
# one, and the seal logic refuses to leave a lone outbound passenger
# dispatched without escalating first (see dispatch_engine.py). Weighting
# it this heavily in the score on TOP of that double-counts it and
# crowds out what the score is actually needed to distinguish between —
# which of several already-feasible insertions is best for the people
# actually in the car. Lowered to 0.18 and the freed weight moved to the
# three passenger-experience terms (distance, detour, wait), which is
# also why WEIGHT_PICKUP_WAIT is no longer the smallest: wait_term now
# measures real marginal schedule disturbance to existing riders, not
# just how far apart two requested times are, so it deserves to matter
# more than it used to.
WEIGHT_OCCUPANCY = 0.18
WEIGHT_ADDED_DISTANCE = 0.28
WEIGHT_WORST_DETOUR = 0.24
WEIGHT_PICKUP_WAIT = 0.20
WEIGHT_DEADLINE_PRESSURE = 0.10

# An insertion scoring worse than this is rejected even if feasible —
# prevents technically-legal but terrible matches.
MAX_ACCEPTABLE_SCORE = 0.75

# --- Corridor matching ---
# A booking is only assigned to a corridor if its pickup AND dropoff sit
# within this far off that corridor's hub-to-hub line. Beyond this, it's
# not "on" the corridor, it's a different trip entirely — better to
# reject with a clear "outside service area" than silently guess.
#
# Two values, interpolated along the route by
# geo.corridor_deviation_limit_m rather than switched at the midpoint.
# The home hub end is wider because that is where the tolerance actually
# binds: sparse rural roads, houses set back from the highway, and
# landmark-approximate pickup pins that a strict boundary turns into
# wrongly-rejected real customers.
#
# The away hub value is deliberately UNCHANGED from the single 20 km
# tolerance these replace. This pass only ever loosens: interpolating
# between 20 km and 28 km can never produce anything under 20 km, so no
# booking accepted before this change is rejected after it. Tightening
# the Hà Nội end may well be right, but not before there is data —
# nothing today records how far off-corridor a rejected booking actually
# was, so any narrower number would be a guess that costs real fares.
MAX_CORRIDOR_DEVIATION_HOME_HUB_METERS = 28_000
MAX_CORRIDOR_DEVIATION_AWAY_HUB_METERS = 20_000

# --- Minimum viable pool size, by direction ---
# Outbound must fill seats to be worth running. Return dispatches solo
# because the vehicle drives back to base regardless.
MIN_POOL_SIZE_OUTBOUND = 2
MIN_POOL_SIZE_RETURN = 1

# --- Routing service ---
ROUTE_CACHE_TTL_SECONDS = 3600
ROUTING_TIMEOUT_SECONDS = 8.0
ROUTING_MAX_RETRIES = 2
# If Goong fails this many times consecutively, stop calling it for
# CIRCUIT_RESET_SECONDS and fall back to haversine estimates rather than
# taking dispatch offline entirely.
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RESET_SECONDS = 60

# Rough average corridor speed, used ONLY by the degraded fallback path
# when Goong is unreachable. Deliberately conservative.
FALLBACK_SPEED_KMH = 38.0

# --- Dispatch engine ---
DISPATCH_TICK_SECONDS = 60

# --- End of the operating day ---
# Every vehicle is based at its corridor's home hub (Bắc Giang) and is
# stationed there overnight, whatever it was doing during the day. At
# this LOCAL hour the end-of-day sweep sends any car that finished
# elsewhere back to base, so the next morning's dispatch starts from
# where the cars actually are rather than from yesterday's last dropoff.
OPERATING_DAY_END_HOUR_LOCAL = 22

# How close to its home hub a vehicle has to be to already count as "at
# base", so the sweep and the manual call-home skip cars that are
# already there instead of issuing pointless return instructions.
AT_BASE_RADIUS_METERS = 3_000

# How long a free car may sit away from base before the system sends it
# home on its own, rather than leaving it parked in Hà Nội earning
# nothing until the end of the day.
#
# Matched to RETURN_VEHICLE_MATCH_WINDOW_MINUTES on purpose: that is
# already the furthest ahead a return booking will be matched to a car
# heading back, so beyond it there is no fare this car could plausibly
# still be waiting for. Waiting longer is just an idle car.
IDLE_AWAY_RETURN_MINUTES = 60

# How long a car has to be idle away from base before it shows up on the
# dispatcher's attention panel. Deliberately well short of the automatic
# send-home above, so a human gets the chance to decide first — they may
# know a return fare is about to be booked.
IDLE_AWAY_ATTENTION_MINUTES = 15
