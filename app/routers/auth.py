import os
import random

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.dependencies import get_current_user
from app.codes import create_code, verify_code
from app.limiter import limiter
from app.models.user import User, GlobalBannedIP
from app.models.moderation import Warnings
from app.schemas.user import (
    UserResponse, MeResponse, UserUpdate, Token,
    PhoneRequest, CodeVerify, AccountDelete, ActionCodeRequest,
)

router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host


def _normalize_phone(phone: str) -> str:
    # Retire tous les séparateurs courants (espaces, tirets, points, parenthèses…)
    raw = (phone or "").strip()
    plus = raw.startswith("+")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not (6 <= len(digits) <= 15):
        raise HTTPException(status_code=400, detail="Invalid phone number")
    # Format canonique : on garde le '+' initial s'il y était.
    return ("+" + digits) if plus else digits


async def _generate_username(db: AsyncSession) -> str:
    """Username par défaut du type user12345, modifiable ensuite dans les réglages."""
    while True:
        candidate = f"user{random.randint(1000, 999999)}"
        existing = await db.execute(select(User).where(User.slug == candidate))
        if existing.scalar_one_or_none() is None:
            return candidate


def _make_token(user_id: int) -> str:
    return jwt.encode({"user_id": user_id}, os.getenv("SECRET_KEY"), algorithm="HS256")


# ── Connexion par téléphone + code ─────────────────────────
@router.post("/request_code")
@limiter.limit("5/minute;20/hour")
async def request_code(data: PhoneRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Étape 1 : l'utilisateur saisit son numéro, on lui envoie un code."""
    phone = _normalize_phone(data.phone)
    client_ip = _client_ip(request)
    banned = await db.execute(select(GlobalBannedIP).where(GlobalBannedIP.ip == client_ip))
    if banned.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Access denied")

    code = await create_code(db, phone, purpose="login")
    # dev_code : renvoyé tant qu'il n'y a pas de vrai SMS, pour tester l'UI.
    return {"status": "ok", "dev_code": code}


@router.post("/verify_code", response_model=Token)
@limiter.limit("10/minute;60/hour")
async def verify_code_route(data: CodeVerify, request: Request, db: AsyncSession = Depends(get_db)):
    """Étape 2 : vérifie le code. Crée le compte si le numéro est nouveau."""
    phone = _normalize_phone(data.phone)
    if not await verify_code(db, phone, data.code, purpose="login"):
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()

    if user is None:
        username = await _generate_username(db)
        user = User(
            username=username,
            slug=username,
            phone=phone,
            bio="",
            avatar_url="",
            ip=_client_ip(request),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {"access_token": _make_token(user.id), "token_type": "bearer"}


@router.post("/request_action_code")
@limiter.limit("5/minute;20/hour")
async def request_action_code(
    data: ActionCodeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Code de confirmation pour une action sensible (suppression, etc.)."""
    if data.purpose not in ("delete_account", "nuke_messages"):
        raise HTTPException(status_code=400, detail="Invalid purpose")
    code = await create_code(db, current_user.phone, purpose=data.purpose)
    return {"status": "ok", "dev_code": code}


# ── Profil ─────────────────────────────────────────────────
@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=MeResponse)
async def update_me(
        data: UserUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user_db = result.scalar_one_or_none()

    if data.username is not None:
        new_slug = data.username.strip().lower()
        if new_slug != user_db.slug:
            taken = await db.execute(select(User).where(User.slug == new_slug))
            if taken.scalar_one_or_none() is not None:
                raise HTTPException(status_code=400, detail="Username already taken")
        user_db.username = data.username.strip()
        user_db.slug = new_slug
    if data.bio is not None:
        user_db.bio = data.bio
    if data.avatar_url is not None:
        user_db.avatar_url = data.avatar_url
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


@router.post("/delete_account")
async def delete_account(
    data: AccountDelete,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await verify_code(db, current_user.phone, data.code, purpose="delete_account"):
        raise HTTPException(status_code=401, detail="Invalid or expired code")
    result = await db.execute(select(User).where(User.id == current_user.id))
    user_db = result.scalar_one_or_none()
    await db.delete(user_db)
    await db.commit()
    return {"status": "ok"}


@router.get("/my_standing")
async def my_standing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Warnings).where(Warnings.user_id == current_user.id)
        .order_by(Warnings.created_at.desc()))
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
