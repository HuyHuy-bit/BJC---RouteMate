from datetime import date, datetime

from pydantic import BaseModel


class RevenueSummary(BaseModel):
    """
    The money view of a period. Admin-only by construction — this is the
    "revenue dashboard / financial report / income statistics" that
    requirements §3 removes from dispatchers.

    Reports FINALIZED trips only. A trip a driver has claimed is
    finished but no dispatcher has signed off is not yet revenue, and
    counting it would let the number move on one person's unreviewed
    say-so.
    """

    period_start: datetime
    period_end: datetime

    trips_finalized: int
    passengers_carried: int
    seats_carried: int

    # What the fares came to, versus what actually reached the business.
    expected_vnd: int
    collected_vnd: int
    outstanding_vnd: int  # still `pending` — owed but not yet collected
    disputed_vnd: int     # collected less than owed, needs reconciliation
    waived_vnd: int       # written off; only an admin can create these

    @property
    def shortfall_vnd(self) -> int:
        return self.expected_vnd - self.collected_vnd


class DailyRevenuePoint(BaseModel):
    """One local calendar day. Bucketed in Asia/Ho_Chi_Minh, not UTC —
    a 23:30 trip belongs to the day the business actually ran it, and
    UTC bucketing would file it under tomorrow."""

    day: date
    revenue_vnd: int
    trips: int


class AdminDashboard(BaseModel):
    """
    The business view: what the company earned, and how the operation
    performed. Admin-only in its entirety — this is the dashboard
    requirements §2 moves out of the dispatcher's reach.
    """

    generated_at: datetime

    # Headline figures. These are stat tiles, not a chart: four numbers
    # compared against nothing don't need axes.
    revenue_today_vnd: int
    revenue_week_vnd: int
    revenue_month_vnd: int
    revenue_total_vnd: int

    # Trend, for the chart. Oldest first.
    daily: list[DailyRevenuePoint]

    # Collection health over the charted window.
    expected_vnd: int
    collected_vnd: int
    outstanding_vnd: int
    disputed_vnd: int
    waived_vnd: int

    # Operational performance over the same window.
    trips_finalized: int
    passengers_carried: int
    seats_carried: int
    trips_cancelled: int
    # Average fare per finalized trip — the cheapest read on whether
    # pooling is working: more riders per car pushes this up.
    avg_revenue_per_trip_vnd: int
    avg_seats_per_trip: float
