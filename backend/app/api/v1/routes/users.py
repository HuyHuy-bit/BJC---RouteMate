from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    role: UserRole | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.dispatcher)),
):
    """
    Mainly exists so the dispatch board can populate a driver-assignment
    dropdown (?role=driver). Restricted to admin/dispatcher since it lists
    staff accounts, not something a driver needs to see.
    """
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    return query.order_by(User.full_name).all()
