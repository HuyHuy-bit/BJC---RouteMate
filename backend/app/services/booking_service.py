from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.core.pricing import price_for
from app.models.booking import Booking
from app.models.customer import Customer
from app.models.enums import BookingDirection, PaymentStatus
from app.models.payment import Payment
from app.schemas.booking import BookingCreate, BookingOut
from app.schemas.customer import CustomerOut
from app.schemas.payment import PaymentOut
from app.services.corridors import find_corridor_for_points
from app.services.geo import classify_direction
from app.services.routing import routing_service


class OutsideServiceAreaError(Exception):
    """Raised when a booking's pickup/dropoff don't sit close enough to
    any active corridor's route to be classified at all — a booking with
    nowhere to belong, not a guess we should make anyway."""


def _point(lat: float, lng: float) -> WKTElement:
    # WKT point order is (x, y) = (lng, lat) — easy to get backwards, hence
    # this one helper used everywhere a point gets constructed.
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def create_booking(db: Session, customer: Customer, payload: BookingCreate) -> Booking:
    corridor = find_corridor_for_points(
        db,
        payload.pickup_lat,
        payload.pickup_lng,
        payload.dropoff_lat,
        payload.dropoff_lng,
    )
    if corridor is None:
        raise OutsideServiceAreaError(
            "pickup/dropoff do not sit on any active corridor"
        )

    # Real point-to-point distance/duration, computed once up front.
    # Not used for pricing (that's a flat per-corridor rate — see
    # app/core/pricing.py) but stored as this booking's solo baseline,
    # which is what makes the per-passenger detour guarantee enforceable
    # during matching (see pool_insertion.py).
    leg = routing_service.leg(
        (payload.pickup_lat, payload.pickup_lng),
        (payload.dropoff_lat, payload.dropoff_lng),
    )

    booking = Booking(
        customer_id=customer.id,
        pickup_address=payload.pickup_address,
        pickup_point=_point(payload.pickup_lat, payload.pickup_lng),
        dropoff_address=payload.dropoff_address,
        dropoff_point=_point(payload.dropoff_lat, payload.dropoff_lng),
        requested_pickup_at=payload.requested_pickup_at,
        is_private=payload.is_private,
        corridor_id=corridor.id,
        solo_duration_seconds=leg.duration_seconds,
        solo_distance_meters=leg.distance_meters,
        price_vnd=price_for(corridor, payload.is_private),
        # Inferred automatically, not customer-supplied — see
        # app/services/geo.py:classify_direction. Direction is decided by
        # which way the passenger moves ALONG the corridor (comparing
        # pickup and dropoff projections), not by which hub the pickup
        # happens to sit nearer — the latter misclassified every booking
        # from midpoint towns like Bắc Ninh.
        direction=BookingDirection(
            classify_direction(
                corridor,
                payload.pickup_lat,
                payload.pickup_lng,
                payload.dropoff_lat,
                payload.dropoff_lng,
            )
        ),
    )
    db.add(booking)
    db.flush()

    db.add(
        Payment(
            booking_id=booking.id,
            status=PaymentStatus.pending,
            expected_amount_vnd=booking.price_vnd,
        )
    )
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
        payment=PaymentOut.model_validate(booking.payment) if booking.payment else None,
        status=booking.status,
        trip_id=booking.trip_id,
        created_at=booking.created_at,
    )
