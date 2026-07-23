import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    dispatcher = "dispatcher"
    driver = "driver"


class BookingDirection(str, enum.Enum):
    outbound = "outbound"  # toward Bắc Giang
    return_leg = "return"  # toward Hà Nội


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
    """

    forming = "forming"
    sealed = "sealed"             # locked for departure, awaiting a vehicle
    assigned = "assigned"         # vehicle + driver committed
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    reassigning = "reassigning"   # driver rejected / breakdown, needs new vehicle


class VehicleStatus(str, enum.Enum):
    available = "available"
    on_trip = "on_trip"
    maintenance = "maintenance"
    inactive = "inactive"


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
