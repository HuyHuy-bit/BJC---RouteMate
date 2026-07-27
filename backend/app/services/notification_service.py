"""
Composes customer-facing messages.

Nothing is transmitted. Every message is stored and surfaced to staff
(see /api/v1/notifications), who phone or Zalo the customer themselves —
which is how this business already works, since customers book by phone
in the first place. There is no Zalo Official Account registered, and
registering one is an admin step, not a coding one.

`pending_manual_relay` is the honest status for that. Reporting a
message as "sent" when nothing was sent is the one thing this module
must never do: staff would trust the screen and stop calling.

To connect Zalo later: register an OA, put the token in the env, and
send from _queue below before the row is written, recording the real
channel and status on the row instead of the two constants.
"""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.notification import Notification
from app.models.trip import Trip


def _fmt_time(dt) -> str:
    return dt.strftime("%H:%M") if dt else "chưa xác định"


def _queue(
    db: Session,
    booking: Booking,
    trip_id: UUID | None,
    event: str,
    message: str,
) -> Notification:
    """
    Store one composed message for staff to relay. Single choke point on
    purpose — five notify_* functions used to construct this row
    themselves, so a change to how delivery is tracked meant editing all
    five.
    """
    note = Notification(
        booking_id=booking.id,
        trip_id=trip_id,
        event=event,
        message=message,
        channel="manual",
        status="pending_manual_relay",
    )
    db.add(note)
    return note


def _queue_for_trip(
    db: Session,
    trip: Trip,
    event: str,
    compose: Callable[[Booking], str],
) -> list[Notification]:
    """Message every rider still actually on `trip`."""
    created = []
    for booking in trip.bookings:
        if booking.status.value in ("cancelled", "no_show"):
            continue
        created.append(_queue(db, booking, trip.id, event, compose(booking)))
    return created


def _compose_sealed_message(booking: Booking, trip: Trip) -> str:
    pickup_time = _fmt_time(booking.estimated_pickup_at)
    driver_line = ""
    if trip.vehicle_label:
        driver_line = f" Xe: {trip.vehicle_label}."
    return (
        f"Chào {booking.customer.full_name}, chuyến của bạn đã được xếp xe. "
        f"Dự kiến đón lúc {pickup_time} tại {booking.pickup_address}.{driver_line} "
        f"Cảm ơn bạn đã sử dụng dịch vụ Thành Công Limousine."
    )


def _compose_driver_assigned_message(
    booking: Booking, trip: Trip, driver_name: str | None
) -> str:
    who = f"Tài xế {driver_name}" if driver_name else "Tài xế"
    plate = f" ({trip.vehicle_label})" if trip.vehicle_label else ""
    return (
        f"{who}{plate} sẽ đón bạn tại {booking.pickup_address} "
        f"lúc {_fmt_time(booking.estimated_pickup_at)}."
    )


def _compose_cancelled_message(booking: Booking, reason: str) -> str:
    return (
        f"Chào {booking.customer.full_name}, chuyến đón lúc "
        f"{booking.requested_pickup_at.strftime('%H:%M %d/%m')} của bạn đã bị huỷ. "
        f"Lý do: {reason}. Vui lòng liên hệ tổng đài nếu cần hỗ trợ đặt lại."
    )


def _compose_disrupted_message(booking: Booking) -> str:
    return (
        f"Chào {booking.customer.full_name}, xe của bạn gặp sự cố. "
        f"Chúng tôi đang tìm xe thay thế và sẽ báo lại thời gian đón mới sớm nhất. "
        f"Xin lỗi vì sự bất tiện này."
    )


def _compose_wait_extended_message(booking: Booking, extra_minutes: int) -> str:
    return (
        f"Chào {booking.customer.full_name}, chuyến của bạn cần thêm khoảng "
        f"{extra_minutes} phút để ghép đủ khách. Chúng tôi sẽ báo lại ngay khi "
        f"xếp được xe. Cảm ơn bạn đã chờ."
    )


def notify_trip_sealed(db: Session, trip: Trip) -> list[Notification]:
    """Called once a pool is sealed — the customer's ride is now real."""
    return _queue_for_trip(
        db, trip, "sealed", lambda b: _compose_sealed_message(b, trip)
    )


def notify_driver_assigned(
    db: Session, trip: Trip, driver_name: str | None
) -> list[Notification]:
    """Riders were told a car was coming when the trip sealed; this says
    who is actually driving it."""
    return _queue_for_trip(
        db,
        trip,
        "driver_assigned",
        lambda b: _compose_driver_assigned_message(b, trip, driver_name),
    )


def notify_booking_cancelled(db: Session, booking: Booking, reason: str) -> Notification:
    """One rider's booking is off — unlike the others, this is addressed
    to a single booking rather than everyone on a trip."""
    return _queue(
        db,
        booking,
        booking.trip_id,
        "cancelled",
        _compose_cancelled_message(booking, reason),
    )


def notify_trip_disrupted(db: Session, trip: Trip) -> list[Notification]:
    """Called when a driver reports a breakdown/issue mid-trip — see
    dispatch_service.py:report_trip_disrupted. A replacement-vehicle
    assignment (or lack of one) is notified separately, same as any
    other seal, via notify_trip_sealed."""
    return _queue_for_trip(db, trip, "disrupted", _compose_disrupted_message)


def notify_wait_extended(
    db: Session, trip: Trip, extra_minutes: int
) -> list[Notification]:
    """Called when a dispatcher gives an under-filled pool more time —
    see dispatch_service.py:extend_pool_wait. Someone who was promised a
    departure and is now waiting longer deserves to be told."""
    return _queue_for_trip(
        db,
        trip,
        "wait_extended",
        lambda b: _compose_wait_extended_message(b, extra_minutes),
    )
