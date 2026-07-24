"""
Composes customer-facing messages and logs them.

No real delivery channel is wired up — this project has no Zalo OA or
SMS gateway credentials. Faking a "delivered" status would be worse than
not having this at all, since staff would trust a message went out when
it didn't. Instead, every notification is composed here, stored, and
surfaced to staff (see /api/v1/notifications) so a dispatcher can read it
and manually call or text the customer until a real channel exists.

Swapping in a real provider later means adding a `channel="zalo"` (or
"sms") branch here that actually calls out, and changing `status` from
"pending_manual_relay" to "sent"/"failed" based on the real result — the
rest of the system (composition, storage, the staff-facing list) doesn't
change.
"""

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.notification import Notification
from app.models.trip import Trip


def _fmt_time(dt) -> str:
    return dt.strftime("%H:%M") if dt else "chưa xác định"


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


def notify_trip_sealed(db: Session, trip: Trip) -> list[Notification]:
    """Called once a pool is sealed — the customer's ride is now real."""
    created = []
    for booking in trip.bookings:
        if booking.status.value in ("cancelled", "no_show"):
            continue
        note = Notification(
            booking_id=booking.id,
            trip_id=trip.id,
            event="sealed",
            message=_compose_sealed_message(booking, trip),
        )
        db.add(note)
        created.append(note)
    return created


def notify_driver_assigned(
    db: Session, trip: Trip, driver_name: str | None
) -> list[Notification]:
    created = []
    for booking in trip.bookings:
        if booking.status.value in ("cancelled", "no_show"):
            continue
        note = Notification(
            booking_id=booking.id,
            trip_id=trip.id,
            event="driver_assigned",
            message=_compose_driver_assigned_message(booking, trip, driver_name),
        )
        db.add(note)
        created.append(note)
    return created


def notify_booking_cancelled(db: Session, booking: Booking, reason: str) -> Notification:
    note = Notification(
        booking_id=booking.id,
        trip_id=booking.trip_id,
        event="cancelled",
        message=_compose_cancelled_message(booking, reason),
    )
    db.add(note)
    return note
