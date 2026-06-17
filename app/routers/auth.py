import urllib
from urllib import request

from fastapi import APIRouter, Depends, HTTPException
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token, UserUpdate, PasswordChange, EmailChange, AccountDelete
import bcrypt
from app.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, GlobalBannedIP
from sqlalchemy import select, or_
from app.dependencies import get_current_user
import jwt
import os
from app.models.moderation import Warning



router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


from fastapi import Request

@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == user.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    existing_email = await db.execute(select(User).where(User.email == user.email))
    if existing_email.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.client.host
    banned = await db.execute(
        select(GlobalBannedIP).where(GlobalBannedIP.ip == client_ip))
    if banned.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Access denied")

    password_bytes = user.password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    user_db = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        slug=user.username.lower(),
        bio="",
        avatar_url="",
        ip=client_ip,
    )
    db.add(user_db)
    await db.commit()
    await db.refresh(user_db)
    return user_db

@router.post("/login", response_model=Token)
async def login(user: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.client.host
    banned = await db.execute(
        select(GlobalBannedIP).where(GlobalBannedIP.ip == client_ip))
    if banned.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Access denied")

    #accepte mail ou username via login
    identifier = (user.identifier or user.email or "").strip()
    result_user = await db.execute(
        select(User).where(
            or_(User.email == identifier, User.slug == identifier.lower())
        )
    )
    db_user = result_user.scalar_one_or_none()

    if db_user is None:
        raise HTTPException(status_code=404, detail="Unknown")

    password_ok = bcrypt.checkpw(
        user.password.encode("utf-8"),
        db_user.hashed_password.encode("utf-8")
    )
    if not password_ok:
        raise HTTPException(status_code=401, detail="Wrong password")

    SECRET_KEY = os.getenv("SECRET_KEY")
    token = jwt.encode(
        {"user_id": db_user.id},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
        data: UserUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user_db = result.scalar_one_or_none()

    if data.bio is not None:
        user_db.bio = data.bio
    if data.avatar_url is not None:
        user_db.avatar_url = data.avatar_url
    if data.username is not None:
        user_db.username = data.username
        user_db.slug = data.username.lower()
    if data.is_private is not None:
        user_db.is_private = data.is_private
    if data.show_online is not None:
        user_db.show_online = data.show_online


    await db.commit()
    await db.refresh(user_db)
    return user_db


@router.get("/users", response_model=list[UserResponse])
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/change_password")
async def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user_db = result.scalar_one_or_none()
    #verifier old mdp
    if not bcrypt.checkpw(data.current_password.encode("utf-8"),
                          user_db.hashed_password.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Wrong current password")
    #defini nv mdp
    salt = bcrypt.gensalt()
    user_db.hashed_password = bcrypt.hashpw(data.new_password.encode("utf-8"), salt).decode("utf-8")
    await db.commit()
    return {"status": "ok"}


@router.post("/change_email")
async def change_email(
    data: EmailChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user_db = result.scalar_one_or_none()
    if not bcrypt.checkpw(data.password.encode("utf-8"),
                          user_db.hashed_password.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Wrong password")
    #verifier email doublons
    existing = await db.execute(select(User).where(User.email == data.new_email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already in use")
    user_db.email = data.new_email
    await db.commit()
    return {"status": "ok"}


@router.post("/delete_account")
async def delete_account(
    data: AccountDelete,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user_db = result.scalar_one_or_none()
    if not bcrypt.checkpw(data.password.encode("utf-8"),
                          user_db.hashed_password.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Wrong password")
    await db.delete(user_db)
    await db.commit()
    return {"status": "ok"}


@router.get("/my_standing")
async def my_standing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Warning).where(Warning.user_id == current_user.id)
        .order_by(Warning.created_at.desc()))
    warnings = res.scalars().all()
    severe = sum(1 for w in warnings if w.severity == "severe")
    total = len(warnings)
    # Détermine le statut global du compte
    if severe >= 2 or total >= 4:
        status = "limited"      # compte limité
    elif total >= 1:
        status = "warning"      # avertissements actifs
    else:
        status = "good"         # tout va bien
    return {
        "status": status,
        "total": total,
        "warnings": [
            {"reason": w.reason, "severity": w.severity,
             "at": w.created_at.isoformat() if w.created_at else ""}
            for w in warnings
        ],
    }

