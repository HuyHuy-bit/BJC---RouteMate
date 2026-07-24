from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_role
from app.db.session import get_db
from app.models.booking import Booking
from app.models.enums import UserRole
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationOut
from app.services.audit import log_pii_access

router = APIRouter(tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    No SMS/Zalo integration exists yet — this is the manual-relay queue:
    every composed message, newest first, so a dispatcher can read one
    and call or text the customer directly. See
    app/services/notification_service.py for why this is log-only.
    """
    notes = (
        db.query(Notification)
        .options(joinedload(Notification.booking).joinedload(Booking.customer))
        .order_by(Notification.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )

    for n in notes:
        log_pii_access(
            db,
            actor_user_id=current_user.id,
            action="read_notification",
            target_type="booking",
            target_id=n.booking_id,
        )
    db.commit()

    return [
        NotificationOut(
            id=n.id,
            booking_id=n.booking_id,
            customer_name=n.booking.customer.full_name,
            customer_phone=n.booking.customer.phone,
            event=n.event,
            message=n.message,
            status=n.status,
            created_at=n.created_at,
        )
        for n in notes
    ]
