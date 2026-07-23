"""
Runs the dispatch cycle on a timer.

This is the piece that makes the system autonomous. Everything else could
be perfect and it would still require a human to click a button — which
defeats the stated business goal of reducing operational staff.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.dispatch_config import DISPATCH_TICK_SECONDS
from app.db.session import SessionLocal
from app.services.dispatch_service import run_dispatch_cycle

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _tick() -> None:
    """
    One dispatch pass. Exceptions are swallowed deliberately: a failed
    tick must never kill the scheduler thread, or dispatch silently stops
    forever and nobody notices until customers complain.
    """
    db = SessionLocal()
    try:
        run_dispatch_cycle(db)
    except Exception:
        logger.exception("dispatch cycle failed; will retry next tick")
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    _scheduler.add_job(
        _tick,
        "interval",
        seconds=DISPATCH_TICK_SECONDS,
        id="dispatch_cycle",
        # If a tick runs long, skip rather than pile up overlapping runs
        # that would fight over the same rows.
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("dispatch scheduler started (every %ss)", DISPATCH_TICK_SECONDS)


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
