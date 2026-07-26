"""
Runs the dispatch cycle on a timer.

This is the piece that makes the system autonomous. Everything else could
be perfect and it would still require a human to click a button — which
defeats the stated business goal of reducing operational staff.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.dispatch_config import (
    DISPATCH_TICK_SECONDS,
    LOCAL_TIMEZONE,
    OPERATING_DAY_END_HOUR_LOCAL,
)
from app.db.session import SessionLocal
from app.services.dispatch_service import run_dispatch_cycle
from app.services.vehicle_return import send_stranded_vehicles_home

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


def _end_of_day() -> None:
    """
    Send home whatever is still out at the end of the operating day.

    Same swallow-everything discipline as _tick: this runs once a day,
    so an exception that killed the job would go unnoticed until
    someone wondered why the fleet map was wrong every morning.
    """
    db = SessionLocal()
    try:
        send_stranded_vehicles_home(db)
    except Exception:
        logger.exception("end-of-day return sweep failed")
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=LOCAL_TIMEZONE)
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
    # Cars sleep at base. Anything still out when the operating day
    # ends gets told to come home, so tomorrow's first booking is
    # matched against where the fleet actually is rather than against
    # yesterday's last dropoff. Local clock hour — the scheduler's
    # timezone is the corridor's, not the server's.
    _scheduler.add_job(
        _end_of_day,
        "cron",
        hour=OPERATING_DAY_END_HOUR_LOCAL,
        minute=0,
        id="end_of_day_return",
        max_instances=1,
        coalesce=True,
        # A restart shortly after the hour should still run the sweep
        # rather than skip the night entirely.
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        "scheduler started (dispatch every %ss, return-to-base at %02d:00 %s)",
        DISPATCH_TICK_SECONDS,
        OPERATING_DAY_END_HOUR_LOCAL,
        LOCAL_TIMEZONE,
    )


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
