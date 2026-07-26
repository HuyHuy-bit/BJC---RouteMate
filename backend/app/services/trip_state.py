"""
The one place that decides how a trip may move, and who may move it.

Before this module, trip status was written from eight different places
— five of them in dispatch_service, three in the routes — and only one
of those consulted the transition table. The table itself described a
workflow that didn't run: it claimed `forming -> sealed -> assigned`
while `seal_trip` jumped straight to `assigned`, so `sealed` was a state
nothing could ever reach. Permissions were checked per-endpoint with
hand-rolled `if is_staff` branches, which is why a dispatcher could
start and complete a trip they had never sat in.

Everything now goes through `apply_transition`. It answers three
questions in one place — is this move legal, is this actor allowed to
make it, and what else has to change when it happens — so none of them
can drift apart again.

See docs/STATE_MACHINE.md for the full contract, including the
reasoning behind the two states the requirements document doesn't name
(`sealed`, `reassigning`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentStatus, TripStatus, UserRole
from app.models.trip import Trip
from app.models.user import User

# The automatic dispatch cycle acting on its own — not a human. Kept as
# a plain string alongside the role values so a transition's permitted
# actors are one flat, printable set.
SYSTEM = "system"

_STAFF = frozenset({UserRole.admin.value, UserRole.dispatcher.value})
_DRIVER = frozenset({UserRole.driver.value})
_SYSTEM = frozenset({SYSTEM})

_STAFF_SYSTEM = _STAFF | _SYSTEM
_DRIVER_STAFF = _DRIVER | _STAFF
_DRIVER_STAFF_SYSTEM = _DRIVER | _STAFF | _SYSTEM


# (from, to) -> who may make this move.
#
# Absence from this table means the move is illegal for everyone; there
# is no implicit fallthrough. `completed` and `cancelled` are terminal
# and therefore appear only as destinations.
TRANSITIONS: dict[tuple[TripStatus, TripStatus], frozenset[str]] = {
    # --- Pool formation -------------------------------------------------
    # Sealing with a vehicle in hand and sealing without one are two
    # different outcomes, not one. Splitting them is what makes "ready
    # to go but the fleet is full" a stored fact instead of something
    # /dispatch/attention has to recompute on every request.
    (TripStatus.forming, TripStatus.sealed): _STAFF_SYSTEM,
    (TripStatus.forming, TripStatus.assigned): _STAFF_SYSTEM,
    (TripStatus.forming, TripStatus.cancelled): _STAFF_SYSTEM,
    (TripStatus.sealed, TripStatus.assigned): _STAFF_SYSTEM,
    (TripStatus.sealed, TripStatus.cancelled): _STAFF_SYSTEM,
    # --- Driver's half of the workflow ----------------------------------
    # These four are the whole point of the module. Staff are absent
    # from every one of them on purpose: an admin is not a superuser
    # here, because the value of the record comes from it being made by
    # the person who was actually in the car.
    (TripStatus.assigned, TripStatus.driver_accepted): _DRIVER,
    (TripStatus.driver_accepted, TripStatus.in_progress): _DRIVER,
    (TripStatus.in_progress, TripStatus.completion_requested): _DRIVER,
    # --- Dispatcher's ruling on the driver's claim ----------------------
    (TripStatus.completion_requested, TripStatus.completed): _STAFF,
    (TripStatus.completion_requested, TripStatus.in_progress): _STAFF,
    # --- Disruption recovery --------------------------------------------
    # A driver rejecting an assignment, cancelling before departure, and
    # breaking down mid-route are the same transition with different
    # reasons — all three keep the passengers and the route, and only
    # change which car is under them.
    (TripStatus.assigned, TripStatus.reassigning): _DRIVER_STAFF,
    (TripStatus.driver_accepted, TripStatus.reassigning): _DRIVER_STAFF,
    (TripStatus.in_progress, TripStatus.reassigning): _DRIVER_STAFF,
    (TripStatus.reassigning, TripStatus.assigned): _STAFF_SYSTEM,
    (TripStatus.reassigning, TripStatus.cancelled): _STAFF,
    # Handing the trip to a different driver revokes the previous
    # driver's acceptance — the new one has agreed to nothing yet, so
    # they get the same accept/reject choice. See
    # dispatch.assign_driver.
    (TripStatus.driver_accepted, TripStatus.assigned): _STAFF,
    # --- Cancellation ----------------------------------------------------
    # `system` appears here for one specific cascade: the last active
    # rider leaving a trip dissolves it (see
    # dispatch_service.detach_booking_from_trip). That includes an
    # in-progress trip whose final passenger just no-showed — the car is
    # moving, but there is by definition nobody left in it, which is
    # exactly when it's safe for the system to decide. No other
    # automatic path cancels a departed trip.
    (TripStatus.assigned, TripStatus.cancelled): _STAFF_SYSTEM,
    (TripStatus.driver_accepted, TripStatus.cancelled): _STAFF_SYSTEM,
    (TripStatus.in_progress, TripStatus.cancelled): _STAFF_SYSTEM,
}

TERMINAL_STATUSES = frozenset({TripStatus.completed, TripStatus.cancelled})

# Statuses in which a trip is committed to a specific car, so that car
# cannot be handed to anything else. Kept here rather than duplicated in
# vehicles.py / users.py / dispatch_service.py, which each had their own
# copy of this list.
VEHICLE_COMMITTED_STATUSES = (
    TripStatus.sealed,
    TripStatus.assigned,
    TripStatus.driver_accepted,
    TripStatus.in_progress,
    TripStatus.completion_requested,
    TripStatus.reassigning,
)

# Trips sitting on a driver's plate: assigned to them and not yet
# resolved. `completion_requested` belongs here — the driver has done
# their part but the trip is still theirs until a dispatcher signs it
# off, and it must stay visible on their dashboard until then.
#
# Every one of these lists used to be spelled out by hand at each call
# site, which is how adding a state silently dropped trips out of the
# driver's own dashboard, out of the vehicle-deletion guard, and out of
# the location-ping permission check all at once.
DRIVER_ACTIVE_STATUSES = (
    TripStatus.assigned,
    TripStatus.driver_accepted,
    TripStatus.in_progress,
    TripStatus.completion_requested,
)


class TransitionError(Exception):
    """Base for anything apply_transition refuses to do."""


class InvalidTransition(TransitionError):
    """The move itself isn't legal, for anyone. Maps to HTTP 400."""


class TransitionForbidden(TransitionError):
    """The move is legal, but not for this actor. Maps to HTTP 403."""


def actor_role(actor: User | None) -> str:
    """`None` means the automatic dispatch cycle acting on its own."""
    return SYSTEM if actor is None else actor.role.value


def allowed_transitions(trip_status: TripStatus, actor: User | None) -> set[TripStatus]:
    """
    Every move this actor could legally make from here.

    Exposed so the API can tell a client what it may do next, rather
    than the frontend keeping its own second copy of these rules and
    slowly disagreeing with the backend.
    """
    role = actor_role(actor)
    return {
        to
        for (frm, to), roles in TRANSITIONS.items()
        if frm is trip_status and role in roles
    }


def check_transition(
    trip: Trip, to_status: TripStatus, actor: User | None
) -> None:
    """
    Validate without writing. Raises the same errors as
    `apply_transition`; used by callers that need to know whether a move
    would succeed before committing to a larger operation.
    """
    frm = trip.status

    if frm is to_status:
        raise InvalidTransition(f"Trip is already {to_status.value}")

    if frm in TERMINAL_STATUSES:
        raise InvalidTransition(
            f"Trip is {frm.value} — a finished trip cannot change state"
        )

    permitted = TRANSITIONS.get((frm, to_status))
    if permitted is None:
        raise InvalidTransition(
            f"Cannot move trip from {frm.value} to {to_status.value}"
        )

    role = actor_role(actor)
    if role not in permitted:
        raise TransitionForbidden(
            f"{role} may not move a trip from {frm.value} to {to_status.value}"
        )

    # A driver may only ever act on their own trip. Checked here rather
    # than per-endpoint because it is a property of the transition, not
    # of the URL that triggered it.
    if actor is not None and actor.role is UserRole.driver and trip.driver_id != actor.id:
        raise TransitionForbidden(
            "Drivers may only act on trips assigned to them"
        )


def _waive_pending_fare(booking: Booking, reason: str) -> None:
    """
    A ride that never happened has nothing to collect. Only touches a
    still-`pending` payment: one already collected, disputed or waived
    is a real record, not ours to overwrite.
    """
    payment = getattr(booking, "payment", None)
    if payment is None or payment.status is not PaymentStatus.pending:
        return
    payment.status = PaymentStatus.waived
    note = f"Tự động huỷ thu tiền: {reason}"
    payment.notes = f"{payment.notes} | {note}" if payment.notes else note


def _cascade_to_bookings(trip: Trip, to_status: TripStatus, reason: str) -> None:
    """
    Move the riders along with the trip they're on.

    These cascades used to live in whichever endpoint remembered to do
    them, which is how bookings ended up stranded at `locked` forever
    when a trip completed, and how a whole-trip cancellation left every
    fare sitting in the books as money owed while a single-booking
    cancellation correctly waived it.
    """
    if to_status in (TripStatus.sealed, TripStatus.assigned):
        for b in trip.bookings:
            if b.status is BookingStatus.matched:
                b.status = BookingStatus.locked

    elif to_status is TripStatus.in_progress:
        # Trip-level approximation: the car has departed, so these
        # riders are expected aboard. Not a per-passenger confirmation —
        # see docs/STATE_MACHINE.md §6.
        for b in trip.bookings:
            if b.status is BookingStatus.locked:
                b.status = BookingStatus.onboard

    elif to_status is TripStatus.completed:
        for b in trip.bookings:
            if b.status in (BookingStatus.locked, BookingStatus.onboard):
                b.status = BookingStatus.completed

    elif to_status is TripStatus.cancelled:
        for b in trip.bookings:
            if b.status not in (
                BookingStatus.cancelled,
                BookingStatus.no_show,
                BookingStatus.completed,
            ):
                b.status = BookingStatus.cancelled
                _waive_pending_fare(b, reason)


def _stamp_timestamps(
    trip: Trip, to_status: TripStatus, actor: User | None, now: datetime
) -> None:
    if to_status is TripStatus.driver_accepted:
        trip.driver_accepted_at = now
    elif to_status is TripStatus.completion_requested:
        trip.completion_requested_at = now
    elif to_status is TripStatus.completed:
        # completed_at is what the history view sorts on and predates
        # this workflow; finalized_at records the review specifically.
        # They're written together today but mean different things, and
        # a later "auto-finalize after N hours" would separate them.
        trip.completed_at = now
        trip.finalized_at = now
        trip.finalized_by_user_id = actor.id if actor is not None else None
    elif to_status is TripStatus.cancelled:
        trip.cancelled_at = now


def apply_transition(
    db: Session,
    trip: Trip,
    to_status: TripStatus,
    actor: User | None = None,
    reason: str = "",
    now: datetime | None = None,
) -> None:
    """
    Move a trip to `to_status`, or refuse.

    `actor=None` means the automatic dispatch cycle. Does not commit —
    the caller owns the transaction boundary, so a transition can be
    part of a larger atomic operation (sealing assigns a vehicle and
    moves the trip; both land together or neither does).
    """
    check_transition(trip, to_status, actor)

    now = now or datetime.now(timezone.utc)
    trip.status = to_status
    _stamp_timestamps(trip, to_status, actor, now)
    _cascade_to_bookings(trip, to_status, reason or to_status.value)
    db.flush()
