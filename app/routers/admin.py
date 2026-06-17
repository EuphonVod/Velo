from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from app.dependencies import get_db
from app.models.user import User, GlobalBannedIP
from app.routers.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserAction(BaseModel):
    user_id: int


def _require_admin(current_user: User):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin only")


#del account
@router.post("/delete_user")
async def admin_delete_user(
    data: AdminUserAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(User).where(User.id == data.user_id))
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    if target.is_superuser:
        raise HTTPException(403, "Cannot delete another admin")
    await db.delete(target)
    await db.commit()
    return {"status": "deleted"}


#global ban
@router.post("/ban_user")
async def admin_ban_user(
    data: AdminUserAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(User).where(User.id == data.user_id))
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    if target.is_superuser:
        raise HTTPException(403, "Cannot ban another admin")
    #blaklist ip
    if target.ip:
        ex = await db.execute(
            select(GlobalBannedIP).where(GlobalBannedIP.ip == target.ip))
        if not ex.scalar_one_or_none():
            db.add(GlobalBannedIP(ip=target.ip, reason=f"Banned user {target.username}"))
    # Supprime le compte
    await db.delete(target)
    await db.commit()
    return {"status": "banned"}

@router.get("/users")
async def admin_list_users(
    q: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    query = select(User)
    if q:
        # Recherche par username ou id
        if q.isdigit():
            query = query.where(User.id == int(q))
        else:
            query = query.where(User.slug.ilike(f"%{q.lower()}%"))
    res = await db.execute(query)
    users = res.scalars().all()
    return [
        {
            "id": u.id, "username": u.username, "email": u.email,
            "ip": u.ip or "", "is_superuser": u.is_superuser,
            "created_at": str(u.created_at),
        }
        for u in users
    ]