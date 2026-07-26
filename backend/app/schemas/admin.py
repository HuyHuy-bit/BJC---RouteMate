from datetime import datetime

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
