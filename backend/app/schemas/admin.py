from datetime import date, datetime

from pydantic import BaseModel


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
