from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.friendship import Friendship
from app.schemas.user import UserResponse
from app.dependencies import get_current_user
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


class FriendRequestAction(BaseModel):
    user_id: int


class FriendRequestInfo(BaseModel):
    friendship_id: int
    user: UserResponse


# ── Recherche d'utilisateurs par @username ────────────────
@router.get("/search", response_model=list[UserResponse])
async def search_users(
    q: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = q.strip().lstrip("@").lower()
    if not q:
        return []
    result = await db.execute(
        select(User).where(User.slug.like(f"%{q}%")).limit(20)
    )
    users = [u for u in result.scalars().all() if u.id != current_user.id]
    return users


# ── Statut de relation avec un utilisateur ────────────────
@router.get("/status/{user_id}")
async def friendship_status(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.requester_id == current_user.id,
                     Friendship.addressee_id == user_id),
                and_(Friendship.requester_id == user_id,
                     Friendship.addressee_id == current_user.id),
            )
        )
    )
    fr = result.scalar_one_or_none()
    if fr is None:
        return {"status": "none"}
    if fr.status == "accepted":
        return {"status": "friends"}
    # pending — distinguer envoyé / reçu
    if fr.requester_id == current_user.id:
        return {"status": "request_sent"}
    return {"status": "request_received", "friendship_id": fr.id}


# ── Envoyer une demande d'ami ─────────────────────────────
@router.post("/request")
async def send_request(
    data: FriendRequestAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.user_id == current_user.id:
        raise HTTPException(400, "Cannot add yourself")

    existing = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.requester_id == current_user.id,
                     Friendship.addressee_id == data.user_id),
                and_(Friendship.requester_id == data.user_id,
                     Friendship.addressee_id == current_user.id),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Request already exists")

    fr = Friendship(
        requester_id=current_user.id,
        addressee_id=data.user_id,
        status="pending",
    )
    db.add(fr)
    await db.commit()
    return {"status": "request_sent"}


# ── Accepter une demande ──────────────────────────────────
@router.post("/accept")
async def accept_request(
    data: FriendRequestAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # data.user_id = id de la personne qui a envoyé la demande
    result = await db.execute(
        select(Friendship).where(
            and_(
                Friendship.requester_id == data.user_id,
                Friendship.addressee_id == current_user.id,
                Friendship.status == "pending",
            )
        )
    )
    fr = result.scalar_one_or_none()
    if fr is None:
        raise HTTPException(404, "Request not found")
    fr.status = "accepted"
    await db.commit()
    return {"status": "friends"}


# ── Refuser / annuler une demande ─────────────────────────
@router.post("/decline")
async def decline_request(
    data: FriendRequestAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.requester_id == data.user_id,
                     Friendship.addressee_id == current_user.id),
                and_(Friendship.requester_id == current_user.id,
                     Friendship.addressee_id == data.user_id),
            )
        )
    )
    fr = result.scalar_one_or_none()
    if fr:
        await db.delete(fr)
        await db.commit()
    return {"status": "none"}


# ── Liste des amis ────────────────────────────────────────
@router.get("/list", response_model=list[UserResponse])
async def list_friends(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Friendship).where(
            and_(
                Friendship.status == "accepted",
                or_(
                    Friendship.requester_id == current_user.id,
                    Friendship.addressee_id == current_user.id,
                ),
            )
        )
    )
    friendships = result.scalars().all()
    friend_ids = [
        f.addressee_id if f.requester_id == current_user.id else f.requester_id
        for f in friendships
    ]
    if not friend_ids:
        return []
    res = await db.execute(select(User).where(User.id.in_(friend_ids)))
    return res.scalars().all()


# ── Demandes reçues (en attente) ──────────────────────────
@router.get("/requests", response_model=list[FriendRequestInfo])
async def pending_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Friendship).where(
            and_(
                Friendship.addressee_id == current_user.id,
                Friendship.status == "pending",
            )
        )
    )
    out = []
    for fr in result.scalars().all():
        ures = await db.execute(select(User).where(User.id == fr.requester_id))
        u = ures.scalar_one_or_none()
        if u:
            out.append({"friendship_id": fr.id, "user": u})
    return out