"""
Admin-only surface: the financial and business view of the operation.

Requirements §3 splits what a dispatcher may see from what an admin
may see. The operational half already existed and stays where it is —
this module is the other half, and it exists so that "dispatchers have
no revenue dashboard" is a fact about the API rather than a fact about
which buttons the frontend happens to render.

Scope note: only the revenue summary is built here. Full financial
reports, business KPIs and analytics were explicitly deferred — none of
them existed in this codebase before, and they are a product to design,
not a permission to flip. What this module establishes now is the
boundary they will live behind.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentStatus, TripStatus, UserRole
from app.models.payment import Payment
from app.models.trip import Trip
from app.models.user import User
from app.schemas.admin import RevenueSummary

router = APIRouter(tags=["admin"])


def _sum_where(status: PaymentStatus):
    """Total expected fare for payments sitting in one status."""
    return func.coalesce(
        func.sum(case((Payment.status == status, Payment.expected_amount_vnd), else_=0)),
        0,
    )


@router.get("/revenue-summary", response_model=RevenueSummary)
def revenue_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """
    Money earned over the last `days`, from finalized trips only.

    This is the aggregate the dispatch board used to compute in the
    browser by summing `price_vnd` across every trip it had loaded —
    which meant the number was available to anyone who could see the
    board, and was only ever as correct as whatever happened to be on
    screen. It is now one query, over finalized trips, behind an admin
    role check.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    counts = db.execute(
        select(
            func.count(func.distinct(Trip.id)),
            func.count(Booking.id),
            func.coalesce(func.sum(Booking.seats), 0),
        )
        .select_from(Booking)
        .join(Trip, Booking.trip_id == Trip.id)
        .where(Trip.status == TripStatus.completed)
        .where(Trip.finalized_at.isnot(None))
        .where(Trip.finalized_at >= start)
        .where(Booking.status == BookingStatus.completed)
    ).one()

    money = db.execute(
        select(
            func.coalesce(func.sum(Payment.expected_amount_vnd), 0),
            func.coalesce(func.sum(Payment.collected_amount_vnd), 0),
            _sum_where(PaymentStatus.pending),
            _sum_where(PaymentStatus.disputed),
            _sum_where(PaymentStatus.waived),
        )
        .select_from(Payment)
        .join(Booking, Payment.booking_id == Booking.id)
        .join(Trip, Booking.trip_id == Trip.id)
        .where(Trip.status == TripStatus.completed)
        .where(Trip.finalized_at.isnot(None))
        .where(Trip.finalized_at >= start)
        .where(Booking.status == BookingStatus.completed)
    ).one()

    # No log_pii_access call here on purpose: this returns aggregate
    # totals and contains no customer PII. That audit log exists to
    # record who decrypted whose phone number, and padding it with
    # rows that touched no personal data makes the real entries harder
    # to find.
    return RevenueSummary(
        period_start=start,
        period_end=now,
        trips_finalized=counts[0] or 0,
        passengers_carried=counts[1] or 0,
        seats_carried=int(counts[2] or 0),
        expected_vnd=int(money[0] or 0),
        collected_vnd=int(money[1] or 0),
        outstanding_vnd=int(money[2] or 0),
        disputed_vnd=int(money[3] or 0),
        waived_vnd=int(money[4] or 0),
    )
