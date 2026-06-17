from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from pydantic import BaseModel

from app.dependencies import get_db
from app.models.friendship import Friendship
from app.models.group import Group, GroupMember, GroupMessage, GroupBan, GroupInvite, GroupBannedIP
from app.models.message import Message
from app.models.user import User, GlobalBannedIP
from app.routers.auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserAction(BaseModel):
    user_id: int


def _require_admin(current_user: User):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin only")



async def _purge_user(db, user_id):
    await db.execute(delete(Message).where(Message.sender_id == user_id))
    await db.execute(delete(Message).where(Message.receiver_id == user_id))
    await db.execute(delete(GroupMessage).where(GroupMessage.sender_id == user_id))
    await db.execute(delete(GroupMember).where(GroupMember.user_id == user_id))
    await db.execute(delete(GroupBan).where(GroupBan.user_id == user_id))
    await db.execute(delete(GroupInvite).where(GroupInvite.invited_user_id == user_id))
    await db.execute(delete(GroupInvite).where(GroupInvite.invited_by_id == user_id))
    await db.execute(delete(Friendship).where(Friendship.requester_id == user_id))
    await db.execute(delete(Friendship).where(Friendship.addressee_id == user_id))


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
    await _purge_user(db, target.id)
    await db.delete(target)
    await db.commit()
    return {"status": "deleted"}


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
    if target.ip:
        ex = await db.execute(
            select(GlobalBannedIP).where(GlobalBannedIP.ip == target.ip))
        if not ex.scalar_one_or_none():
            db.add(GlobalBannedIP(ip=target.ip, reason=f"Banned user {target.username}"))
    await _purge_user(db, target.id)
    await db.delete(target)
    await db.commit()
    return {"status": "banned"}


class AdminUserView(BaseModel):
    id: int
    username: str
    email: str
    ip: str | None = ""
    is_superuser: bool = False
    is_private: bool = False
    created_at: datetime | None = None
    class Config:
        from_attributes = True


@router.get("/users")
async def admin_list_users(
    q: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    query = select(User)
    if q:
        if q.isdigit():
            query = query.where(User.id == int(q))
        else:
            query = query.where(User.username.ilike(f"%{q}%"))
    res = await db.execute(query.order_by(User.id))
    users = res.scalars().all()
    return [
        {
            "id": u.id, "username": u.username, "email": u.email,
            "ip": u.ip or "", "is_superuser": u.is_superuser,
            "is_private": u.is_private,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]

@router.get("/groups")
async def admin_list_groups(
    q: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    query = select(Group)
    if q:
        if q.isdigit():
            query = query.where(Group.id == int(q))
        else:
            query = query.where(Group.name.ilike(f"%{q}%"))
    res = await db.execute(query.order_by(Group.id))
    groups = res.scalars().all()
    result = []
    for g in groups:
        cnt = await db.execute(
            select(GroupMember).where(GroupMember.group_id == g.id))
        members = len(cnt.scalars().all())
        result.append({
            "id": g.id, "name": g.name,
            "is_private": getattr(g, "is_private", False),
            "members": members,
        })
    return result


class AdminGroupAction(BaseModel):
    group_id: int


@router.post("/delete_group")
async def admin_delete_group(
    data: AdminGroupAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(Group).where(Group.id == data.group_id))
    g = res.scalar_one_or_none()
    if not g:
        raise HTTPException(404, "Group not found")
    gid = data.group_id
    await db.execute(delete(GroupMessage).where(GroupMessage.group_id == gid))
    await db.execute(delete(GroupMember).where(GroupMember.group_id == gid))
    await db.execute(delete(GroupBan).where(GroupBan.group_id == gid))
    await db.execute(delete(GroupInvite).where(GroupInvite.group_id == gid))
    await db.execute(delete(GroupBannedIP).where(GroupBannedIP.group_id == gid))
    await db.delete(g)
    await db.commit()
    return {"status": "deleted"}

@router.get("/group_members")
async def admin_group_members(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id))
    members = res.scalars().all()
    result = []
    for m in members:
        ures = await db.execute(select(User).where(User.id == m.user_id))
        u = ures.scalar_one_or_none()
        if u:
            result.append({
                "id": u.id, "username": u.username, "email": u.email,
                "ip": u.ip or "", "is_superuser": u.is_superuser,
                "is_private": u.is_private,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "role": m.role,
            })
    return result

@router.get("/alt_accounts")
async def admin_alt_accounts(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(User).where(User.id == user_id))
    target = res.scalar_one_or_none()
    if not target or not target.ip:
        return []
    others = await db.execute(
        select(User).where(User.ip == target.ip, User.id != user_id).order_by(User.id))
    return [
        {"id": u.id, "username": u.username, "email": u.email,
         "ip": u.ip or "", "is_superuser": u.is_superuser,
         "is_private": u.is_private,
         "created_at": u.created_at.isoformat() if u.created_at else None}
        for u in others.scalars().all()
    ]

@router.get("/stats")
async def admin_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    users = await db.scalar(select(func.count()).select_from(User))
    groups = await db.scalar(select(func.count()).select_from(Group))
    dms = await db.scalar(select(func.count()).select_from(Message))
    gmsgs = await db.scalar(select(func.count()).select_from(GroupMessage))
    banned = await db.scalar(select(func.count()).select_from(GlobalBannedIP))
    return {"users": users or 0, "groups": groups or 0,
            "dm_messages": dms or 0, "group_messages": gmsgs or 0,
            "banned_ips": banned or 0}

class UnbanIP(BaseModel):
    ip: str

@router.get("/banned_ips")
async def admin_banned_ips(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(GlobalBannedIP).order_by(GlobalBannedIP.id))
    return [{"id": b.id, "ip": b.ip, "reason": b.reason or ""}
            for b in res.scalars().all()]

@router.post("/unban_ip")
async def admin_unban_ip(
    data: UnbanIP,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    await db.execute(delete(GlobalBannedIP).where(GlobalBannedIP.ip == data.ip))
    await db.commit()
    return {"status": "unbanned"}

class SetAdmin(BaseModel):
    user_id: int
    make_admin: bool

@router.post("/set_admin")
async def admin_set_admin(
    data: SetAdmin,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(User).where(User.id == data.user_id))
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    target.is_superuser = data.make_admin
    await db.commit()
    return {"status": "ok", "is_superuser": target.is_superuser}

@router.get("/user_messages")
async def admin_user_messages(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    dm = await db.execute(
        select(Message).where(Message.sender_id == user_id)
        .order_by(Message.created_at.desc()).limit(20))
    gm = await db.execute(
        select(GroupMessage).where(GroupMessage.sender_id == user_id)
        .order_by(GroupMessage.created_at.desc()).limit(20))
    msgs = []
    for m in dm.scalars().all():
        msgs.append({"type": "DM", "content": m.content,
                     "at": m.created_at.isoformat() if m.created_at else ""})
    for m in gm.scalars().all():
        msgs.append({"type": "Group", "content": m.content,
                     "at": m.created_at.isoformat() if m.created_at else ""})
    msgs.sort(key=lambda x: x["at"], reverse=True)
    return msgs[:30]