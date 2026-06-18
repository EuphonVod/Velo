from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserUpdate(BaseModel):
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    username: Optional[str] = None
    is_private: Optional[bool] = None
    show_online: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    username: str
    bio: Optional[str] = ""
    avatar_url: Optional[str] = ""
    is_private: Optional[bool] = False
    show_online: Optional[bool] = True
    last_seen: Optional[datetime] = None
    created_at: datetime
    slug: Optional[str] = ""
    is_superuser: Optional[bool] = False

    model_config = {"from_attributes": True}


class MeResponse(UserResponse):
    # Le numéro n'est exposé que sur /auth/me (jamais sur les autres profils).
    phone: Optional[str] = ""


class Token(BaseModel):
    access_token: str
    token_type: str


# ── Authentification par téléphone + code ──────────────────
class PhoneRequest(BaseModel):
    phone: str
    purpose: str = "login"  # login | delete_account | nuke_messages


class CodeVerify(BaseModel):
    phone: str
    code: str


class ActionCodeRequest(BaseModel):
    # Le numéro provient du compte connecté, on ne demande que le motif.
    purpose: str


# Actions sensibles : confirmées par un code reçu sur le téléphone.
class AccountDelete(BaseModel):
    code: str


class NukeMessages(BaseModel):
    code: str
