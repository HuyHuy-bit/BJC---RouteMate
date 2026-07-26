import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    dispatcher = "dispatcher"
    driver = "driver"


class BookingDirection(str, enum.Enum):
    outbound = "outbound"    # leaving the home base: Bắc Giang -> Hà Nội
    return_leg = "return"    # heading back to base: Hà Nội -> Bắc Giang


class BookingStatus(str, enum.Enum):
    queued = "queued"       # awaiting a pool
    matched = "matched"     # in a pool that is still forming — can be re-pooled
    waiting = "waiting"     # tried, no viable pool yet
    locked = "locked"       # pool sealed; route frozen, customer has final ETA
    onboard = "onboard"     # physically picked up
    completed = "completed"
    no_show = "no_show"     # driver waited, passenger absent
    cancelled = "cancelled"


class TripStatus(str, enum.Enum):
    """
    A trip in `forming` IS the pool — it accretes bookings until sealed.
    Keeping one entity rather than a separate Pool table avoids a painful
    migration and matches the shape the data already had.

    The legal moves between these are NOT defined here — see
    app/services/trip_state.py, which is the single place that decides
    both which transitions exist and who is allowed to make them.
    docs/STATE_MACHINE.md explains why.
    """

    forming = "forming"
    sealed = "sealed"             # locked for departure, awaiting a vehicle
    assigned = "assigned"         # vehicle + driver committed
    driver_accepted = "driver_accepted"   # driver acknowledged the assignment
    in_progress = "in_progress"
    # Driver says they're done; a dispatcher still has to confirm it.
    # Completion is a claim until someone reviews it — which is also why
    # the vehicle's location is not updated until finalization.
    completion_requested = "completion_requested"
    completed = "completed"
    cancelled = "cancelled"
    reassigning = "reassigning"   # driver rejected / breakdown, needs new vehicle


class VehicleStatus(str, enum.Enum):
    available = "available"
    # Committed to a trip that has not departed yet. Distinct from
    # on_trip: a car waiting at the hub with a driver assigned can still
    # be swapped onto a more urgent run, one already carrying passengers
    # cannot.
    assigned = "assigned"
    on_trip = "on_trip"
    maintenance = "maintenance"
    offline = "offline"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    bank_transfer = "bank_transfer"
    other = "other"


class PaymentStatus(str, enum.Enum):
    pending = "pending"       # not yet collected
    collected = "collected"   # collected amount met or exceeded what was owed
    disputed = "disputed"     # collected less than owed — needs reconciliation
    waived = "waived"         # staff decided not to collect (goodwill, error, etc.)


class DispatchEventType(str, enum.Enum):
    """Audit trail. Every automatic decision is recorded alongside manual
    overrides, so a disputed trip can always be reconstructed."""

    pool_created = "pool_created"
    booking_pooled = "booking_pooled"
    booking_removed = "booking_removed"
    pool_sealed = "pool_sealed"
    pool_escalated = "pool_escalated"
    pool_merged = "pool_merged"
    vehicle_assigned = "vehicle_assigned"
    trip_started = "trip_started"
    trip_completed = "trip_completed"
    trip_cancelled = "trip_cancelled"
    driver_rejected = "driver_rejected"
    manual_override = "manual_override"
    pool_reclustered = "pool_reclustered"
    driver_accepted = "driver_accepted"
    # The driver's end-of-trip claim, and the dispatcher's ruling on it.
    # Logged separately from trip_completed so a disputed trip shows both
    # when the driver said they finished and when a human agreed.
    completion_requested = "completion_requested"
    completion_rejected = "completion_rejected"
    trip_finalized = "trip_finalized"
