"""
The trip state machine: what moves are legal, who may make them, and
what else changes when they happen.

This is the test for the rule the business actually asked for — the
dispatcher runs the operation, but only the driver who sat in the car
can say the trip started and finished, and only a dispatcher can sign
that off. Before this existed, `update_trip_status` accepted any
transition from any staff member and the dispatch board rendered
"Bắt đầu chuyến" / "Hoàn thành chuyến" buttons to dispatchers.

No database: apply_transition takes a Session only to flush, so a stub
with a flush() is enough. See docs/STATE_MACHINE.md for the contract
these assertions encode.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.models.enums import (
    BookingStatus,
    PaymentStatus,
    TripStatus,
    UserRole,
)
from app.services.trip_state import (
    DRIVER_ACTIVE_STATUSES,
    SYSTEM,
    TERMINAL_STATUSES,
    TRANSITIONS,
    VEHICLE_COMMITTED_STATUSES,
    InvalidTransition,
    TransitionForbidden,
    allowed_transitions,
    apply_transition,
    check_transition,
)


class FakeDB:
    """apply_transition only ever calls flush()."""

    def __init__(self):
        self.flushes = 0

    def flush(self):
        self.flushes += 1


@dataclass
class FakePayment:
    status: PaymentStatus = PaymentStatus.pending
    notes: str | None = None


@dataclass
class FakeBooking:
    status: BookingStatus = BookingStatus.matched
    payment: FakePayment | None = field(default_factory=FakePayment)


@dataclass
class FakeTrip:
    status: TripStatus
    bookings: list = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    driver_id: UUID | None = None
    driver_accepted_at: datetime | None = None
    completion_requested_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    finalized_at: datetime | None = None
    finalized_by_user_id: UUID | None = None


@dataclass
class FakeUser:
    role: UserRole
    id: UUID = field(default_factory=uuid4)


DRIVER_ID = uuid4()


def driver(owns=True):
    return FakeUser(UserRole.driver, DRIVER_ID if owns else uuid4())


def trip_for_driver(status: TripStatus, bookings=None) -> FakeTrip:
    return FakeTrip(status=status, driver_id=DRIVER_ID, bookings=bookings or [])


# --------------------------------------------------------------------
# The rule the requirements are actually about
# --------------------------------------------------------------------


@pytest.mark.parametrize("role", [UserRole.dispatcher, UserRole.admin])
@pytest.mark.parametrize(
    "frm,to",
    [
        (TripStatus.assigned, TripStatus.driver_accepted),
        (TripStatus.driver_accepted, TripStatus.in_progress),
        (TripStatus.in_progress, TripStatus.completion_requested),
    ],
)
def test_staff_cannot_perform_driver_actions(role, frm, to):
    """
    Accepting, starting and finishing a trip belong to the driver.

    Admin is included on purpose: an admin outranks a dispatcher on
    every financial and administrative question, but not on this one.
    The record is worth having precisely because the person who was in
    the car is the one who made it.
    """
    with pytest.raises(TransitionForbidden):
        check_transition(trip_for_driver(frm), to, FakeUser(role))


def test_driver_cannot_finalize_even_their_own_trip():
    with pytest.raises(TransitionForbidden):
        check_transition(
            trip_for_driver(TripStatus.completion_requested),
            TripStatus.completed,
            driver(),
        )


@pytest.mark.parametrize("role", [UserRole.dispatcher, UserRole.admin])
def test_staff_finalize_and_reject_completion(role):
    staff = FakeUser(role)
    trip = trip_for_driver(TripStatus.completion_requested)
    check_transition(trip, TripStatus.completed, staff)
    check_transition(trip, TripStatus.in_progress, staff)


def test_completion_is_a_claim_not_a_completion():
    """in_progress -> completed must not be reachable by anyone. The
    driver can only raise a request; a dispatcher turns it into a
    completed trip."""
    assert (TripStatus.in_progress, TripStatus.completed) not in TRANSITIONS


# --------------------------------------------------------------------
# Ownership
# --------------------------------------------------------------------


def test_driver_may_only_act_on_their_own_trip():
    with pytest.raises(TransitionForbidden, match="assigned to them"):
        check_transition(
            trip_for_driver(TripStatus.assigned),
            TripStatus.driver_accepted,
            driver(owns=False),
        )


def test_driver_may_act_on_their_own_trip():
    check_transition(
        trip_for_driver(TripStatus.assigned), TripStatus.driver_accepted, driver()
    )


# --------------------------------------------------------------------
# Structural guarantees about the table itself
# --------------------------------------------------------------------


def test_terminal_states_have_no_way_out():
    for terminal in TERMINAL_STATUSES:
        assert not [t for (f, t) in TRANSITIONS if f is terminal], (
            f"{terminal.value} is terminal but the table lets it move"
        )


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATUSES, key=lambda s: s.value))
def test_finished_trips_are_immutable(terminal):
    with pytest.raises(InvalidTransition, match="finished trip"):
        check_transition(
            trip_for_driver(terminal), TripStatus.in_progress, FakeUser(UserRole.admin)
        )


def test_no_self_transitions():
    for frm, to in TRANSITIONS:
        assert frm is not to, f"{frm.value} -> itself is in the table"


def test_moving_to_the_same_status_is_refused():
    with pytest.raises(InvalidTransition, match="already"):
        check_transition(
            trip_for_driver(TripStatus.in_progress),
            TripStatus.in_progress,
            FakeUser(UserRole.admin),
        )


def test_unknown_transition_is_refused_for_everyone():
    # forming -> in_progress skips the entire assignment workflow.
    for role in (UserRole.admin, UserRole.dispatcher, UserRole.driver):
        with pytest.raises(InvalidTransition):
            check_transition(
                trip_for_driver(TripStatus.forming),
                TripStatus.in_progress,
                FakeUser(role, DRIVER_ID),
            )


def test_every_non_terminal_status_is_reachable():
    """A state nothing can reach is dead weight — `sealed` was exactly
    that before this work, and the transition table claimed otherwise."""
    reachable = {to for (_f, to) in TRANSITIONS}
    for status in TripStatus:
        if status is TripStatus.forming:
            continue  # where trips are born
        assert status in reachable, f"{status.value} is unreachable"


def test_every_status_except_terminals_can_move():
    for status in TripStatus:
        if status in TERMINAL_STATUSES:
            continue
        assert [t for (f, t) in TRANSITIONS if f is status], (
            f"{status.value} is a dead end but is not terminal"
        )


def test_status_groupings_cover_the_new_states():
    """These constants replaced four hand-maintained copies of the same
    list. A new state must not silently fall out of them."""
    for s in (TripStatus.driver_accepted, TripStatus.completion_requested):
        assert s in DRIVER_ACTIVE_STATUSES
        assert s in VEHICLE_COMMITTED_STATUSES


# --------------------------------------------------------------------
# allowed_transitions — what the API hands the frontend
# --------------------------------------------------------------------


def test_allowed_transitions_matches_the_role():
    accepted = trip_for_driver(TripStatus.driver_accepted)
    assert allowed_transitions(accepted.status, driver()) == {
        TripStatus.in_progress,
        TripStatus.reassigning,
    }
    assert TripStatus.in_progress not in allowed_transitions(
        accepted.status, FakeUser(UserRole.dispatcher)
    )


def test_dispatcher_is_never_offered_start_or_accept():
    disp = FakeUser(UserRole.dispatcher)
    for status in TripStatus:
        offered = allowed_transitions(status, disp)
        assert TripStatus.driver_accepted not in offered
        # in_progress IS offered from completion_requested — that is the
        # dispatcher bouncing a claim back, not starting a trip.
        if status is not TripStatus.completion_requested:
            assert TripStatus.in_progress not in offered


def test_system_actor_is_the_absence_of_a_user():
    assert TripStatus.sealed in allowed_transitions(TripStatus.forming, None)
    assert SYSTEM in TRANSITIONS[(TripStatus.forming, TripStatus.sealed)]
    # ...but the system never drives the car.
    assert SYSTEM not in TRANSITIONS[(TripStatus.assigned, TripStatus.driver_accepted)]


# --------------------------------------------------------------------
# Booking cascade
# --------------------------------------------------------------------


def test_sealing_locks_matched_bookings():
    trip = trip_for_driver(
        TripStatus.forming, [FakeBooking(BookingStatus.matched)]
    )
    apply_transition(FakeDB(), trip, TripStatus.sealed, actor=None)
    assert trip.bookings[0].status is BookingStatus.locked


def test_starting_puts_riders_onboard():
    """`onboard` was declared, labelled in the UI, and written by
    nothing at all before this."""
    trip = trip_for_driver(
        TripStatus.driver_accepted, [FakeBooking(BookingStatus.locked)]
    )
    apply_transition(FakeDB(), trip, TripStatus.in_progress, actor=driver())
    assert trip.bookings[0].status is BookingStatus.onboard


def test_finalizing_completes_riders():
    trip = trip_for_driver(
        TripStatus.completion_requested,
        [FakeBooking(BookingStatus.onboard), FakeBooking(BookingStatus.locked)],
    )
    apply_transition(
        FakeDB(), trip, TripStatus.completed, actor=FakeUser(UserRole.dispatcher)
    )
    assert all(b.status is BookingStatus.completed for b in trip.bookings)


def test_cancelling_waives_pending_fares():
    """A whole-trip cancellation used to flip booking statuses but never
    touch the money, so fares for rides that never happened sat in the
    books as owed — while cancelling the SAME booking individually
    waived it correctly."""
    trip = trip_for_driver(TripStatus.assigned, [FakeBooking(BookingStatus.locked)])
    apply_transition(
        FakeDB(), trip, TripStatus.cancelled, actor=FakeUser(UserRole.dispatcher)
    )
    assert trip.bookings[0].status is BookingStatus.cancelled
    assert trip.bookings[0].payment.status is PaymentStatus.waived


def test_cancelling_does_not_overwrite_settled_money():
    """A collected or disputed payment is a real record of something
    that happened, not ours to rewrite."""
    collected = FakeBooking(
        BookingStatus.onboard, FakePayment(status=PaymentStatus.collected)
    )
    trip = trip_for_driver(TripStatus.in_progress, [collected])
    apply_transition(
        FakeDB(), trip, TripStatus.cancelled, actor=FakeUser(UserRole.dispatcher)
    )
    assert collected.payment.status is PaymentStatus.collected


def test_cancelling_leaves_already_finished_riders_alone():
    done = FakeBooking(BookingStatus.completed)
    no_show = FakeBooking(BookingStatus.no_show)
    trip = trip_for_driver(TripStatus.in_progress, [done, no_show])
    apply_transition(
        FakeDB(), trip, TripStatus.cancelled, actor=FakeUser(UserRole.dispatcher)
    )
    assert done.status is BookingStatus.completed
    assert no_show.status is BookingStatus.no_show


def test_reassigning_keeps_every_passenger():
    """A breakdown changes the car, not who is riding in it."""
    riders = [FakeBooking(BookingStatus.onboard), FakeBooking(BookingStatus.locked)]
    before = [b.status for b in riders]
    trip = trip_for_driver(TripStatus.in_progress, riders)
    apply_transition(FakeDB(), trip, TripStatus.reassigning, actor=driver())
    assert [b.status for b in riders] == before


def test_bouncing_a_completion_leaves_riders_untouched():
    riders = [FakeBooking(BookingStatus.onboard)]
    trip = trip_for_driver(TripStatus.completion_requested, riders)
    apply_transition(
        FakeDB(), trip, TripStatus.in_progress, actor=FakeUser(UserRole.dispatcher)
    )
    assert riders[0].status is BookingStatus.onboard
    assert trip.completed_at is None


# --------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------


def test_each_handover_is_stamped():
    now = datetime(2026, 7, 26, 8, 29, tzinfo=timezone.utc)

    trip = trip_for_driver(TripStatus.assigned)
    apply_transition(FakeDB(), trip, TripStatus.driver_accepted, actor=driver(), now=now)
    assert trip.driver_accepted_at == now

    apply_transition(FakeDB(), trip, TripStatus.in_progress, actor=driver(), now=now)
    apply_transition(
        FakeDB(), trip, TripStatus.completion_requested, actor=driver(), now=now
    )
    assert trip.completion_requested_at == now

    disp = FakeUser(UserRole.dispatcher)
    apply_transition(FakeDB(), trip, TripStatus.completed, actor=disp, now=now)
    assert trip.completed_at == now
    assert trip.finalized_at == now
    assert trip.finalized_by_user_id == disp.id


def test_the_finalizer_is_recorded_not_the_driver():
    trip = trip_for_driver(TripStatus.completion_requested)
    disp = FakeUser(UserRole.dispatcher)
    apply_transition(FakeDB(), trip, TripStatus.completed, actor=disp)
    assert trip.finalized_by_user_id == disp.id
    assert trip.finalized_by_user_id != DRIVER_ID


# --------------------------------------------------------------------
# Requirements §5 edge cases
# --------------------------------------------------------------------


def test_driver_rejects_assignment():
    check_transition(
        trip_for_driver(TripStatus.assigned), TripStatus.reassigning, driver()
    )


def test_driver_cancels_before_starting():
    check_transition(
        trip_for_driver(TripStatus.driver_accepted), TripStatus.reassigning, driver()
    )


def test_driver_cannot_cancel_the_trip_outright():
    """Standing down hands the trip to another car. Cancelling strands
    the passengers, and is a dispatcher's call."""
    for status in (TripStatus.assigned, TripStatus.driver_accepted, TripStatus.in_progress):
        with pytest.raises(TransitionForbidden):
            check_transition(trip_for_driver(status), TripStatus.cancelled, driver())


def test_system_may_dissolve_a_moving_trip_whose_last_rider_left():
    """The one automatic path that cancels a departed trip: the final
    passenger no-showed, so there is by definition nobody aboard."""
    check_transition(
        trip_for_driver(TripStatus.in_progress), TripStatus.cancelled, None
    )


def test_a_pool_waiting_for_a_car_can_still_be_crewed_or_cancelled():
    assert allowed_transitions(TripStatus.sealed, None) == {TripStatus.assigned, TripStatus.cancelled}


def test_reassigning_recovers_to_assigned():
    check_transition(
        trip_for_driver(TripStatus.reassigning),
        TripStatus.assigned,
        FakeUser(UserRole.dispatcher),
    )


def test_handing_the_trip_to_a_new_driver_revokes_acceptance():
    """The replacement driver has agreed to nothing, so the trip drops
    back to `assigned` and they get their own accept/reject choice."""
    check_transition(
        trip_for_driver(TripStatus.driver_accepted),
        TripStatus.assigned,
        FakeUser(UserRole.dispatcher),
    )
