import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import TripStatus
from app.schemas.booking import BookingOut


class TripOut(BaseModel):
    id: uuid.UUID
    status: TripStatus
    driver_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
    vehicle_label: str | None
    is_private: bool
    bookings: list[BookingOut]
    created_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None

    # Each handover in the driver/dispatcher workflow, so the UI can
    # show who is waiting on whom without re-deriving it from `status`.
    driver_accepted_at: datetime | None = None
    completion_requested_at: datetime | None = None
    finalized_at: datetime | None = None
    finalized_by_user_id: uuid.UUID | None = None

    # What the CALLER may do to this trip next, straight from the
    # transition table. Without this the frontend keeps its own second
    # copy of the rules and the two drift — which is exactly how the
    # dispatch board ended up rendering a "Complete trip" button the
    # backend would have refused.
    available_actions: list[TripStatus] = []


class MatchingRunResult(BaseModel):
    trips_created: int
    trips: list[TripOut]


class TripAssignDriver(BaseModel):
    driver_id: uuid.UUID


class TripStatusUpdate(BaseModel):
    status: TripStatus


class TripReportIssue(BaseModel):
    reason: Literal["breakdown", "accident", "driver_unavailable", "other"]
    notes: str | None = Field(default=None, max_length=500)


class TripRejectAssignment(BaseModel):
    """A driver declining a trip, or standing down from one they'd
    already accepted. Same machinery as a breakdown report — the
    passengers and route survive, only the car changes — so the reason
    vocabulary is shared."""

    reason: Literal["driver_unavailable", "breakdown", "accident", "other"] = (
        "driver_unavailable"
    )
    notes: str | None = Field(default=None, max_length=500)


class TripRejectCompletion(BaseModel):
    """A dispatcher sending a completion claim back to the driver. The
    reason is required: this puts a trip the driver believed was over
    back on their plate, and they need to know why."""

    reason: str = Field(min_length=1, max_length=500)


class TripExtendWait(BaseModel):
    """Dispatcher resolving an escalation by giving the pool more time.
    Bounded so a stray value can't push a customer's departure hours
    out — anything longer than this is really a rebooking, not a wait."""

    extra_minutes: int = Field(default=20, ge=5, le=120)


class AttentionItem(BaseModel):
    """
    A trip that needs a human decision right now — a forming pool that
    couldn't fill by deadline (escalated), the fleet is fully committed
    (no_vehicle), or a trip a driver reported disrupted couldn't find a
    replacement vehicle on its own (vehicle_down). Previously these were
    only ever written to the dispatch_events audit log; nothing ever
    surfaced them to a dispatcher.
    """

    kind: str  # "escalated" | "no_vehicle" | "vehicle_down"
    trip_id: uuid.UUID
    direction: str
    passenger_count: int
    minutes_overdue: float
    reason: str
    options: list[str] | None
    bookings: list[BookingOut]


class MergeTripsResult(BaseModel):
    target: TripOut
