from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.core.pricing import price_for
from app.models.booking import Booking
from app.models.customer import Customer
from app.models.enums import BookingDirection
from app.schemas.booking import BookingCreate, BookingOut
from app.schemas.customer import CustomerOut
from app.services.geo import classify_direction


def _point(lat: float, lng: float) -> WKTElement:
    # WKT point order is (x, y) = (lng, lat) — easy to get backwards, hence
    # this one helper used everywhere a point gets constructed.
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def create_booking(db: Session, customer: Customer, payload: BookingCreate) -> Booking:
    booking = Booking(
        customer_id=customer.id,
        pickup_address=payload.pickup_address,
        pickup_point=_point(payload.pickup_lat, payload.pickup_lng),
        dropoff_address=payload.dropoff_address,
        dropoff_point=_point(payload.dropoff_lat, payload.dropoff_lng),
        requested_pickup_at=payload.requested_pickup_at,
        is_private=payload.is_private,
        price_vnd=price_for(payload.is_private),
        # Inferred automatically, not customer-supplied — see
        # app/services/geo.py:classify_direction. This business only
        # serves the Bắc Giang <-> Hà Nội corridor, so nearest-hub is a
        # reliable signal without asking the customer to specify it.
        direction=BookingDirection(classify_direction(payload.pickup_lat, payload.pickup_lng)),
    )
    db.add(booking)
    db.flush()
    return booking


def to_booking_out(booking: Booking) -> BookingOut:
    pickup_shape = to_shape(booking.pickup_point)
    dropoff_shape = to_shape(booking.dropoff_point)
    return BookingOut(
        id=booking.id,
        customer=CustomerOut(
            id=booking.customer.id,
            full_name=booking.customer.full_name,
            phone=booking.customer.phone,
            created_at=booking.customer.created_at,
        ),
        pickup_address=booking.pickup_address,
        pickup_lat=pickup_shape.y,
        pickup_lng=pickup_shape.x,
        dropoff_address=booking.dropoff_address,
        dropoff_lat=dropoff_shape.y,
        dropoff_lng=dropoff_shape.x,
        requested_pickup_at=booking.requested_pickup_at,
        direction=booking.direction,
        is_private=booking.is_private,
        price_vnd=booking.price_vnd,
        status=booking.status,
        trip_id=booking.trip_id,
        created_at=booking.created_at,
    )
