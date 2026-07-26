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
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.dispatch_config import LOCAL_TIMEZONE
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentStatus, TripStatus, UserRole
from app.models.payment import Payment
from app.models.trip import Trip
from app.models.user import User
from app.schemas.admin import AdminDashboard, DailyRevenuePoint, RevenueSummary

router = APIRouter(tags=["admin"])


def _sum_where(status: PaymentStatus):
    """Total expected fare for payments sitting in one status."""
    return func.coalesce(
        func.sum(case((Payment.status == status, Payment.expected_amount_vnd), else_=0)),
        0,
    )


def _local(column):
    """
    A timestamp read in the corridor's local clock.

    Revenue is bucketed by the day the business actually ran the trip.
    A 23:30 run finalized in Hà Nội is 16:30 UTC — grouping on the raw
    UTC timestamp would file half the evening under the wrong day and
    make every daily figure quietly wrong.
    """
    return func.timezone(LOCAL_TIMEZONE, column)


def _finalized_in(since: datetime):
    """Bookings that actually travelled on a trip a dispatcher signed
    off. A driver's unreviewed completion claim is not revenue."""
    return (
        (Trip.status == TripStatus.completed)
        & (Trip.finalized_at.isnot(None))
        & (Trip.finalized_at >= since)
        & (Booking.status == BookingStatus.completed)
    )


def _revenue_since(db: Session, since: datetime) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(Booking.price_vnd), 0))
        .select_from(Booking)
        .join(Trip, Booking.trip_id == Trip.id)
        .where(_finalized_in(since))
    ).scalar()
    return int(total or 0)


@router.get("/dashboard", response_model=AdminDashboard)
def admin_dashboard(
    days: int = Query(default=30, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """
    The business dashboard: revenue, its trend, collection health, and
    how the operation performed.

    Every figure counts FINALIZED trips only. A driver saying they
    finished is a claim; revenue that moves on an unreviewed claim is
    a number the business can't stand behind.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)

    # Local-clock day boundaries, so "today" means today in Hà Nội.
    local_now = now.astimezone(ZoneInfo(LOCAL_TIMEZONE))
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=local_now.weekday())
    month_start = today_start.replace(day=1)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    daily_rows = db.execute(
        select(
            func.date(_local(Trip.finalized_at)).label("day"),
            func.coalesce(func.sum(Booking.price_vnd), 0),
            func.count(func.distinct(Trip.id)),
        )
        .select_from(Booking)
        .join(Trip, Booking.trip_id == Trip.id)
        .where(_finalized_in(window_start))
        .group_by("day")
        .order_by("day")
    ).all()

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
        .where(_finalized_in(window_start))
    ).one()

    counts = db.execute(
        select(
            func.count(func.distinct(Trip.id)),
            func.count(Booking.id),
            func.coalesce(func.sum(Booking.seats), 0),
        )
        .select_from(Booking)
        .join(Trip, Booking.trip_id == Trip.id)
        .where(_finalized_in(window_start))
    ).one()

    cancelled = db.execute(
        select(func.count(Trip.id))
        .where(Trip.status == TripStatus.cancelled)
        .where(Trip.cancelled_at.isnot(None))
        .where(Trip.cancelled_at >= window_start)
    ).scalar()

    trips_finalized = int(counts[0] or 0)
    window_revenue = sum(int(r[1] or 0) for r in daily_rows)
    seats = int(counts[2] or 0)

    return AdminDashboard(
        generated_at=now,
        revenue_today_vnd=_revenue_since(db, today_start),
        revenue_week_vnd=_revenue_since(db, week_start),
        revenue_month_vnd=_revenue_since(db, month_start),
        revenue_total_vnd=_revenue_since(db, epoch),
        daily=[
            DailyRevenuePoint(day=r[0], revenue_vnd=int(r[1] or 0), trips=int(r[2] or 0))
            for r in daily_rows
        ],
        expected_vnd=int(money[0] or 0),
        collected_vnd=int(money[1] or 0),
        outstanding_vnd=int(money[2] or 0),
        disputed_vnd=int(money[3] or 0),
        waived_vnd=int(money[4] or 0),
        trips_finalized=trips_finalized,
        passengers_carried=int(counts[1] or 0),
        seats_carried=seats,
        trips_cancelled=int(cancelled or 0),
        # Guarded rather than assumed non-zero: a fresh install, or any
        # window with no finalized trips, would otherwise divide by zero
        # and 500 the whole dashboard.
        avg_revenue_per_trip_vnd=(
            round(window_revenue / trips_finalized) if trips_finalized else 0
        ),
        avg_seats_per_trip=(
            round(seats / trips_finalized, 1) if trips_finalized else 0.0
        ),
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
