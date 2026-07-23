from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine
from app.services.routing import routing_service

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    # Routing health is operationally important: a wide-open circuit or a
    # collapsing cache hit rate both mean matching quality is silently
    # degrading before anyone notices bad dispatches.
    routing = routing_service.health()

    healthy = db_ok and not routing["circuit_open"]
    return {
        "status": "ok" if healthy else "degraded",
        "database": db_ok,
        "routing": routing,
    }
