import uuid

from pydantic import BaseModel, Field

from app.models.enums import UserRole


class UserRegister(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    # role defaults to dispatcher; only an existing admin can create other
    # admins (enforced in the route, not here) — see auth.py TODO on
    # locking down open registration before real deployment
    role: UserRole = UserRole.dispatcher


class UserLogin(BaseModel):
    phone: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
