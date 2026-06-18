from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from pydantic import BaseModel

from app.dependencies import get_db
from app.models.friendship import Friendship
from app.models.group import Group, GroupMember, GroupMessage, GroupBan, GroupInvite, GroupBannedIP
from app.models.message import Message
from app.models.moderation import Report, AdminNote
from app.models.user import User, GlobalBannedIP
from app.routers.auth import get_current_user
from datetime import datetime
from app.models.moderation import Warnings

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
    phone: str | None = ""
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
            "id": u.id, "username": u.username, "phone": u.phone,
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
                "id": u.id, "username": u.username, "phone": u.phone,
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
        {"id": u.id, "username": u.username, "phone": u.phone,
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
        rec = await db.execute(select(User).where(User.id == m.receiver_id))
        ru = rec.scalar_one_or_none()
        to = ru.username if ru else f"#{m.receiver_id}"
        msgs.append({"type": "DM", "content": m.content, "to": to,
                     "at": m.created_at.isoformat() if m.created_at else ""})
    for m in gm.scalars().all():
        gres = await db.execute(select(Group).where(Group.id == m.group_id))
        g = gres.scalar_one_or_none()
        to = g.name if g else f"group #{m.group_id}"
        msgs.append({"type": "Group", "content": m.content, "to": to,
                     "at": m.created_at.isoformat() if m.created_at else ""})
    msgs.sort(key=lambda x: x["at"], reverse=True)
    return msgs[:30]

@router.get("/search_messages")
async def admin_search_messages(
    q: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    if not q or len(q) < 2:
        return []
    results = []
    #dm avec mot clé
    dm = await db.execute(
        select(Message).where(Message.content.ilike(f"%{q}%"))
        .order_by(Message.created_at.desc()).limit(40))
    for m in dm.scalars().all():
        s = await db.execute(select(User).where(User.id == m.sender_id))
        su = s.scalar_one_or_none()
        results.append({"msg_id": m.id, "kind": "dm", "type": "DM",
                        "content": m.content,
                        "sender": su.username if su else f"#{m.sender_id}",
                        "sender_id": m.sender_id,
                        "at": m.created_at.isoformat() if m.created_at else ""})
    #msg de grp
    gm = await db.execute(
        select(GroupMessage).where(GroupMessage.content.ilike(f"%{q}%"))
        .order_by(GroupMessage.created_at.desc()).limit(40))
    for m in gm.scalars().all():
        s = await db.execute(select(User).where(User.id == m.sender_id))
        su = s.scalar_one_or_none()
        results.append({"msg_id": m.id, "kind": "group", "type": "Group",
                        "content": m.content,
                        "sender": su.username if su else f"#{m.sender_id}",
                        "sender_id": m.sender_id,
                        "at": m.created_at.isoformat() if m.created_at else ""})
    results.sort(key=lambda x: x["at"], reverse=True)
    return results[:60]


class DeleteMsg(BaseModel):
    msg_id: int
    kind: str  #dm ou grp

@router.post("/delete_message")
async def admin_delete_message(
    data: DeleteMsg,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    if data.kind == "dm":
        await db.execute(delete(Message).where(Message.id == data.msg_id))
    else:
        await db.execute(delete(GroupMessage).where(GroupMessage.id == data.msg_id))
    await db.commit()
    return {"status": "deleted"}

class CreateReport(BaseModel):
    reported_user_id: int
    reason: str

#route called par clien
@router.post("/report")
async def create_report(
    data: CreateReport,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    db.add(Report(reporter_id=current_user.id,
                  reported_user_id=data.reported_user_id, reason=data.reason))
    await db.commit()
    return {"status": "ok"}

@router.get("/reports")
async def admin_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(Report).order_by(Report.created_at.desc()).limit(100))
    out = []
    for r in res.scalars().all():
        rep = await db.execute(select(User).where(User.id == r.reporter_id))
        tgt = await db.execute(select(User).where(User.id == r.reported_user_id))
        ru, tu = rep.scalar_one_or_none(), tgt.scalar_one_or_none()
        out.append({"id": r.id, "reason": r.reason, "status": r.status,
                    "reporter": ru.username if ru else f"#{r.reporter_id}",
                    "reported": tu.username if tu else f"#{r.reported_user_id}",
                    "reported_id": r.reported_user_id,
                    "at": r.created_at.isoformat() if r.created_at else ""})
    return out

class ReportAction(BaseModel):
    report_id: int

@router.post("/resolve_report")
async def admin_resolve_report(
    data: ReportAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(Report).where(Report.id == data.report_id))
    r = res.scalar_one_or_none()
    if r:
        r.status = "resolved"
        await db.commit()
    return {"status": "ok"}

@router.get("/group_bans")
async def admin_group_bans(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    out = []
    #bans par user
    res = await db.execute(select(GroupBan).where(GroupBan.group_id == group_id))
    for b in res.scalars().all():
        u = await db.execute(select(User).where(User.id == b.user_id))
        uu = u.scalar_one_or_none()
        out.append({"kind": "user", "ban_id": b.id,
                    "label": uu.username if uu else f"#{b.user_id}",
                    "until": b.until.isoformat() if b.until else "permanent"})
    #bans par IP
    res2 = await db.execute(select(GroupBannedIP).where(GroupBannedIP.group_id == group_id))
    for b in res2.scalars().all():
        out.append({"kind": "ip", "ban_id": b.id, "label": b.ip, "until": "permanent"})
    return out


class GroupUnban(BaseModel):
    ban_id: int
    kind: str  #user ou ip

@router.post("/group_unban")
async def admin_group_unban(
    data: GroupUnban,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    if data.kind == "user":
        await db.execute(delete(GroupBan).where(GroupBan.id == data.ban_id))
    else:
        await db.execute(delete(GroupBannedIP).where(GroupBannedIP.id == data.ban_id))
    await db.commit()
    return {"status": "ok"}

class AddNote(BaseModel):
    user_id: int
    note: str

@router.get("/notes")
async def admin_get_notes(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(
        select(AdminNote).where(AdminNote.user_id == user_id)
        .order_by(AdminNote.created_at.desc()))
    return [{"id": n.id, "note": n.note,
             "at": n.created_at.isoformat() if n.created_at else ""}
            for n in res.scalars().all()]

@router.post("/add_note")
async def admin_add_note(
    data: AddNote,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    db.add(AdminNote(user_id=data.user_id, note=data.note))
    await db.commit()
    return {"status": "ok"}

class NoteAction(BaseModel):
    note_id: int

@router.post("/delete_note")
async def admin_delete_note(
    data: NoteAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    await db.execute(delete(AdminNote).where(AdminNote.id == data.note_id))
    await db.commit()
    return {"status": "ok"}

class AddWarning(BaseModel):
    user_id: int
    reason: str
    severity: str = "warning"  #warning ou severe

@router.post("/add_warning")
async def admin_add_warning(
    data: AddWarning,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    db.add(Warnings(user_id=data.user_id, reason=data.reason, severity=data.severity))
    await db.commit()
    return {"status": "ok"}

@router.get("/warnings")
async def admin_get_warnings(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(
        select(Warnings).where(Warnings.user_id == user_id)
        .order_by(Warnings.created_at.desc()))
    return [{"id": w.id, "reason": w.reason, "severity": w.severity,
             "at": w.created_at.isoformat() if w.created_at else ""}
            for w in res.scalars().all()]

class WarningAction(BaseModel):
    warning_id: int

@router.post("/delete_warning")
async def admin_delete_warning(
    data: WarningAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    await db.execute(delete(Warnings).where(Warnings.id == data.warning_id))
    await db.commit()
    return {"status": "ok"}