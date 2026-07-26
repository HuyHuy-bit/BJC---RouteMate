# Trip & Vehicle State Machine

This document is the contract. Every status write in the backend goes
through one guarded helper that enforces the tables below, and the
frontend renders actions from the same role mapping. If a transition
isn't in this document, it isn't legal.

## 1. Why this document exists

Before this, the workflow had three structural problems:

1. **Dispatchers could drive the trip.** `update_trip_status` accepted
   any transition from any staff member, and the dispatcher board
   rendered "Bắt đầu chuyến" / "Hoàn thành chuyến" buttons. The role
   boundary the business actually operates on existed nowhere in code.
2. **The transition table described a workflow that didn't run.**
   `ALLOWED_TRANSITIONS` claimed `forming → sealed → assigned`, but
   nothing ever wrote `sealed`; `seal_trip` jumped straight to
   `assigned`. A pool that was ready to depart but had no car sat in
   `forming`, indistinguishable from one still gathering riders.
3. **Half the status writes bypassed the table entirely.** `seal_trip`,
   `merge_trips`, `detach_booking_from_trip`, and
   `report_trip_disrupted` all assigned `trip.status` directly, so the
   only validated path was the one endpoint that happened to check.

## 2. Trip states

| State | Meaning | Requirements doc name |
|---|---|---|
| `forming` | Pool is still accreting bookings | Pending |
| `sealed` | Route locked and departing, but no vehicle free yet | — |
| `assigned` | Vehicle + driver committed; driver notified | Assigned |
| `driver_accepted` | Driver has acknowledged the assignment | Driver Accepted |
| `in_progress` | Driver has started; car is on the road | In Progress |
| `completion_requested` | Driver finished; awaiting dispatcher review | Completion Requested |
| `completed` | Dispatcher finalized. Terminal. | Finalized / Completed |
| `cancelled` | Terminal. | Cancelled |
| `reassigning` | Breakdown or rejection; needs a replacement vehicle | — |

Two states have no counterpart in the requirements doc and are retained
deliberately:

- **`sealed`** separates "we have riders and a locked route" from "we
  have a car for them". Without it, `/dispatch/attention` has to re-run
  `evaluate_pool` over every forming pool on every request just to
  rediscover which ones are stuck waiting for a vehicle.
- **`reassigning`** is the live-breakdown recovery path. A car failing
  mid-route with passengers aboard is not the same event as a
  cancellation, and collapsing them loses the retry behaviour in
  `run_dispatch_cycle`.

## 3. Trip transitions

`system` means the automatic dispatch cycle (`run_dispatch_cycle`), not
a human actor.

| From | To | Who | Trigger |
|---|---|---|---|
| `forming` | `sealed` | system, dispatcher, admin | Deadline reached, or force-seal. No vehicle available yet. |
| `forming` | `assigned` | system, dispatcher, admin | Seal that immediately found a vehicle. |
| `forming` | `cancelled` | dispatcher, admin, system | Last active booking removed. |
| `sealed` | `assigned` | system, dispatcher, admin | A vehicle came free; retried each cycle tick. |
| `sealed` | `cancelled` | dispatcher, admin, system | Last active booking removed. |
| `assigned` | `driver_accepted` | **driver only** | Driver accepts. |
| `assigned` | `reassigning` | driver, dispatcher, admin | Driver rejects, or breakdown reported. |
| `assigned` | `cancelled` | dispatcher, admin, system | Customer cancels / dispatcher kills the trip. |
| `driver_accepted` | `in_progress` | **driver only** | Driver presses Start Trip. |
| `driver_accepted` | `reassigning` | driver, dispatcher, admin | Driver cancels before starting, or breakdown. |
| `driver_accepted` | `cancelled` | dispatcher, admin, system | Customer cancels. |
| `in_progress` | `completion_requested` | **driver only** | Driver presses Complete Trip. |
| `in_progress` | `reassigning` | driver, dispatcher, admin | Breakdown mid-route. |
| `in_progress` | `cancelled` | dispatcher, admin, system | Trip abandoned mid-route. `system` only via the last-rider-left cascade — an in-progress trip whose final passenger no-shows has nobody left in it. |
| `completion_requested` | `completed` | **dispatcher, admin only** | Dispatcher presses Finalize Trip. |
| `completion_requested` | `in_progress` | **dispatcher, admin only** | Dispatcher rejects the completion request. |
| `reassigning` | `assigned` | system, dispatcher, admin | Replacement vehicle found. |
| `reassigning` | `cancelled` | dispatcher, admin | No replacement; trip abandoned. |
| `completed` | — | — | Terminal. |
| `cancelled` | — | — | Terminal. |

### Role summary

**Driver can:** accept, reject, start, request completion, report a
breakdown. Only on trips where `trip.driver_id` is their own user id.

**Driver cannot:** finalize, assign a vehicle, assign a driver, merge
pools, seal, or cancel.

**Dispatcher can:** merge, assign vehicles, assign drivers, seal,
review and finalize completion requests, reject a completion request,
cancel, report a breakdown on a driver's behalf.

**Dispatcher cannot:** accept, start, or complete a trip. These are the
driver's actions and are refused with 403 even for admins — see §6.

**Admin** has every dispatcher permission plus financial and
administrative access. Admin is *not* a superuser for driver actions:
the point of the workflow is that the person who physically drove the
car is the one who attests it started and finished.

## 4. Vehicle states

| State | Meaning | Requirements doc name |
|---|---|---|
| `available` | Free and assignable, wherever it currently is | Available / Idle |
| `assigned` | Committed to a trip that has not departed | Assigned |
| `on_trip` | Out on the road with passengers | In Trip |
| `returning` | Deadheading back to base, empty | — |
| `maintenance` | Broken down or being serviced | Maintenance |
| `offline` | Retired or otherwise out of service | Offline |

"Idle" is folded into `available`. The requirements use "Idle /
Available" as a single concept in §1 while listing them separately in
§5; a second synonym state would add ambiguity without adding a
decision anyone makes differently.

`offline` replaces the old `inactive`.

### Vehicle transitions

| From | To | Trigger |
|---|---|---|
| `available` | `assigned` | `_assign_vehicle` commits it to a trip |
| `assigned` | `on_trip` | Driver starts the trip |
| `assigned` | `available` | Trip cancelled before departure, or driver rejected |
| `assigned` | `maintenance` | Breakdown reported before departure |
| `on_trip` | `available` | **Trip finalized** — location updated first |
| `on_trip` | `available` | Trip cancelled mid-route (non-breakdown) |
| `on_trip` | `maintenance` | Breakdown reported mid-route |
| `available` | `returning` | Called home by a dispatcher, or by the end-of-day sweep |
| `returning` | `available` | Driver confirms arrival at base, or the return is cancelled |
| `maintenance` | `available` | Repaired; set manually by staff |
| any | `offline` | Retired; set manually by admin |
| `offline` | `available` | Returned to service; set manually by admin |

A vehicle is only released if it isn't also committed to some other
still-active trip — see `release_vehicle_if_free`.

## 4a. Return to base

Every vehicle is based at its corridor's **home hub** (Bắc Giang) and is
stationed there overnight. A car that finishes its last run in Hà Nội
has to get back, or the next morning's first booking is matched against
yesterday's last dropoff.

Home base is **derived**, never hardcoded: `Vehicle.home_corridor_id`
→ `Corridor.home_hub_lat/lng`. The `Corridor` table exists precisely
because these hubs were once constants in `geo.py`, which silently
misclassified every booking on a second route.

Two ways a return starts, both landing in `returning` with a
`return_requested_at` stamp:

- a **dispatcher calls the car home** early, when Hà Nội has no demand left
- the **end-of-day sweep** (`OPERATING_DAY_END_HOUR_LOCAL`, local time)
  sends home whatever is still out

It ends one of two ways:

- the **driver confirms arrival** — the only thing that moves the
  recorded position to base
- a **dispatcher cancels** it, usually because a booking turned up and
  the car is wanted where it is. Position untouched.

Three properties worth stating, because each rules out a specific
inconsistency:

1. **A `returning` car is not dispatchable.** It is physically driving
   to Bắc Giang; handing it a Hà Nội pickup would be a lie. To reclaim
   it, cancel the return first. (A `returning` car could in principle
   still carry a Hà Nội→Bắc Giang passenger, since that is exactly
   where it's going — real value, deliberately deferred rather than
   half-built.)
2. **The sweep never teleports a car.** It raises the same request a
   dispatcher would. The business rule says cars sleep at base, but
   the system still must not claim a car arrived until its driver says
   so — an assumption wearing a fresh timestamp is worse than an
   honestly stale one, because `_assign_vehicle` trusts fresh
   timestamps and discards stale ones.
3. **A return is refused** for a car that is mid-trip, already
   returning, or already at base. Being at base is judged by real
   distance (`AT_BASE_RADIUS_METERS`); an *unknown* position does not
   count as being home, since that car is exactly the one worth asking
   about.

## 5. Vehicle location and the finalize boundary

This is the fix for requirements §1.

A vehicle's `last_location` is written on **finalization**, not on the
driver pressing Complete. The driver's completion is a claim; the
dispatcher's finalization is the confirmation, and the fleet's picture
of where its cars are should be built from confirmed facts.

On `completion_requested → completed`:

1. `vehicle.last_location` ← the dropoff point of the last stop in
   route order.
2. If every booking on the trip ended `cancelled`/`no_show`, fall back
   to the corridor's destination hub (`away_hub` for outbound,
   `home_hub` for return) rather than skipping the write. The old code
   skipped it, leaving the car pinned to a stale position it had
   already driven away from.
3. `vehicle.last_location_at` ← now.
4. `vehicle.status` ← `available`, via `release_vehicle_if_free`.

The vehicle is then immediately eligible for dispatch from its new
location, which is the behaviour §1 asks for: a car that finishes in
Hà Nội at 08:29 is an available Hà Nội car at 08:29.

**The vehicle never disappears.** The dispatcher's fleet view is built
from the vehicle roster, not from live trips. A car with no active trip
renders as available at its last known location instead of vanishing
from the board, which is what the old trip-derived view did.

## 6. Booking cascade

A trip transition also moves the bookings riding on it. These cascades
are part of the transition, applied by the same helper — not left to
whichever endpoint happens to remember.

| Trip transition | Booking effect |
|---|---|
| `forming` → `sealed` / `assigned` | `matched` → `locked`. Route frozen, customer has a final ETA. |
| `driver_accepted` → `in_progress` | `locked` → `onboard`. |
| `completion_requested` → `completed` | `onboard`/`locked` → `completed`. |
| `completion_requested` → `in_progress` | No change — the riders never stopped riding. |
| any → `cancelled` | Anything not already `cancelled`/`no_show`/`completed` → `cancelled`, fare waived. |
| `*` → `reassigning` | No change. Passengers keep their bookings; only the car changes. |

`onboard` was the second state in this codebase that was declared,
given a UI label ("Đang trên xe"), and never written by anything — the
completion path commented that bookings "stayed stuck at locked/onboard
forever" while nothing could actually reach `onboard`.

Setting it at trip start is a trip-level approximation: it means "the
car has departed, this rider is expected aboard", not "the driver
confirmed this specific person got in". That is the honest limit of the
current data. Per-stop pickup confirmation would make it exact, and is
the natural follow-up if the business wants passenger-level truth —
but a state that is approximately right beats one that is permanently
unreachable.

## 7. Edge cases

Each of these maps to a concrete transition above.

| Case | Handling |
|---|---|
| **Driver rejects assignment** | `assigned → reassigning`. Vehicle released to `available`, `driver_id` cleared, replacement sought immediately via `seal_trip`; retried every cycle tick if none free. |
| **Driver cancels before starting** | `driver_accepted → reassigning`. Identical handling to rejection. |
| **Dispatcher reassigns a trip** | `assign_driver` is legal only in `sealed`, `assigned`, `driver_accepted`, `reassigning`. Reassigning a driver on a trip already in progress, completed, or cancelled is refused. Changing the driver on an `driver_accepted` trip resets it to `assigned` — the new driver has not accepted anything yet. |
| **Dispatcher rejects a completion request** | `completion_requested → in_progress`. The trip is live again, no location write, vehicle stays `on_trip`. Logged as `completion_rejected` with the dispatcher's reason. |
| **Vehicle becomes unavailable** | `report_trip_disrupted`. Breakdown reasons send the car to `maintenance`; others release it to `available`. Route and passengers are preserved. |
| **Customer cancels** | `detach_booking_from_trip`. Fare waived, route re-solved for remaining riders. If they were the last active rider, the trip cancels and the vehicle is released. |
| **Multiple pending requests for the same vehicle** | `_assign_vehicle` selects candidate rows `FOR UPDATE SKIP LOCKED`, so two concurrent seals cannot commit the same car. Previously unguarded. |
| **Invalid state transitions** | Rejected with 400 by the single guarded helper. Every status write in the codebase routes through it, including the service-layer paths that previously assigned `trip.status` directly. |

## 8. Enforcement

- **Backend, structural:** one `TRANSITIONS` table keyed
  `(from, to) → {roles}` in `app/services/trip_state.py`. One function,
  `apply_transition(db, trip, to, actor)`, validates and writes. No
  other code assigns `trip.status`.
- **Backend, per-route:** `require_role` on every endpoint, plus an
  ownership check that the acting driver owns the trip.
- **Frontend:** actions are rendered from a role-keyed map, so a
  dispatcher is never shown a Start button. This is a usability layer,
  not a security layer — the backend refuses the call regardless.
