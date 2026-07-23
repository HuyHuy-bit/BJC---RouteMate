import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    dispatcher = "dispatcher"
    driver = "driver"


class BookingStatus(str, enum.Enum):
    queued = "queued"       # waiting to be matched
    matched = "matched"     # assigned to a trip with 2+ riders, or private
    waiting = "waiting"     # shared booking with no match yet (needs 2+)
    cancelled = "cancelled"


class TripStatus(str, enum.Enum):
    forming = "forming"           # still accepting riders (shared, <4 seats)
    confirmed = "confirmed"       # locked, ready to depart
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
