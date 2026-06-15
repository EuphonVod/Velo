from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    identifier: Optional[str] = None  
    email: Optional[str] = None
    password: str


class UserUpdate(BaseModel):
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    username: Optional[str] = None
    is_private: Optional[bool] = None
    show_online: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    bio: Optional[str] = ""
    avatar_url: Optional[str] = ""
    is_private: Optional[bool] = False
    show_online: Optional[bool] = True
    last_seen: Optional[datetime] = None
    created_at: datetime
    slug: Optional[str] = ""

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class EmailChange(BaseModel):
    new_email: EmailStr
    password: str

class AccountDelete(BaseModel):
    password: str