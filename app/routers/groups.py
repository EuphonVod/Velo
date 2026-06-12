from fastapi import APIRouter, Depends, HTTPException, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

from app.database import AsyncSessionLocal
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.group import Group, GroupMember, GroupMessage
from app.models.group import Group, GroupMember, GroupMessage, GroupInvite, GroupBan


router = APIRouter()


# ── Schemas ───────────────────────────────────────────────
class GroupCreate(BaseModel):
    name: str
    is_private: bool = False
    bio: str = ""


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

class GroupAction(BaseModel):
    user_id: int

class GroupOut(BaseModel):
    id: int
    name: str
    bio: str = ""
    avatar_url: str = ""
    is_private: bool
    owner_id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    user_id: int
    username: str
    avatar_url: str = ""
    slug: str = ""
    role: str

class ModAction(BaseModel):
    user_id: int


class BanAction(BaseModel):
    user_id: int
    days: int = 0  # 0 = permanent


async def _get_role(db, group_id, user_id):
    res = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        ))
    )
    m = res.scalar_one_or_none()
    return m.role if m else None

async def _is_banned(db, group_id, user_id):
    res = await db.execute(
        select(GroupBan).where(and_(
            GroupBan.group_id == group_id,
            GroupBan.user_id == user_id,
        ))
    )
    ban = res.scalar_one_or_none()
    if not ban:
        return False
    if ban.until is None:
        return True
    if ban.until < datetime.now():
        await db.delete(ban)
        await db.commit()
        return False
    return True


# ── Créer un groupe ───────────────────────────────────────
@router.post("/create", response_model=GroupOut)
async def create_group(
    data: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owner_id = current_user.id  # capture avant
    g = Group(
        name=data.name,
        bio=data.bio,
        is_private=data.is_private,
        owner_id=owner_id,
    )
    db.add(g)
    await db.commit()
    await db.refresh(g)
    group_id = g.id  # capture avant
    member = GroupMember(group_id=group_id, user_id=owner_id, role="owner")
    db.add(member)
    await db.commit()
    await db.refresh(g)
    return g


# ── Mes groupes ───────────────────────────────────────────
@router.get("/my", response_model=list[GroupOut])
async def my_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GroupMember).where(GroupMember.user_id == current_user.id)
    )
    group_ids = [m.group_id for m in result.scalars().all()]
    if not group_ids:
        return []
    res = await db.execute(select(Group).where(Group.id.in_(group_ids)))
    return res.scalars().all()


# ── Détails d'un groupe ───────────────────────────────────
@router.get("/{group_id}", response_model=GroupOut)
async def get_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Group).where(Group.id == group_id))
    g = res.scalar_one_or_none()
    if not g:
        raise HTTPException(404, "Group not found")
    return g


# ── Membres d'un groupe ───────────────────────────────────
@router.get("/{group_id}/members", response_model=list[MemberOut])
async def group_members(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id)
    )
    members = res.scalars().all()
    out = []
    for m in members:
        ures = await db.execute(select(User).where(User.id == m.user_id))
        u = ures.scalar_one_or_none()
        if u:
            out.append({
                "user_id": u.id, "username": u.username,
                "avatar_url": u.avatar_url or "", "slug": u.slug,
                "role": m.role,
            })
    return out


# ── Historique des messages du groupe ─────────────────────
@router.get("/{group_id}/history")
async def group_history(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(GroupMessage).where(GroupMessage.group_id == group_id)
        .order_by(GroupMessage.created_at)
    )
    msgs = res.scalars().all()
    out = []
    for m in msgs:
        ures = await db.execute(select(User).where(User.id == m.sender_id))
        u = ures.scalar_one_or_none()
        out.append({
            "sender_id": m.sender_id,
            "sender_name": u.username if u else "?",
            "content": m.content,
        })
    return out

# ── Quitter un groupe ─────────────────────────────────────
@router.post("/{group_id}/leave")
async def leave_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id,
        ))
    )
    m = res.scalar_one_or_none()
    if m:
        if m.role == "owner":
            raise HTTPException(400, "Owner cannot leave. Delete the group instead.")
        await db.delete(m)
        await db.commit()
    return {"status": "left"}


# ── Modifier le groupe (owner/admin) ──────────────────────
@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int,
    data: GroupUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Vérifie le rôle
    res = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id,
        ))
    )
    m = res.scalar_one_or_none()
    if not m or m.role not in ("owner", "admin"):
        raise HTTPException(403, "Not allowed")
    gres = await db.execute(select(Group).where(Group.id == group_id))
    g = gres.scalar_one_or_none()
    if not g:
        raise HTTPException(404, "Group not found")
    if data.name is not None: g.name = data.name
    if data.bio is not None: g.bio = data.bio
    if data.avatar_url is not None: g.avatar_url = data.avatar_url
    await db.commit()
    await db.refresh(g)
    return g

# ── Rechercher des groupes publics par nom ────────────────
@router.get("/search/public", response_model=list[GroupOut])
async def search_public_groups(
    q: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = q.strip().lower()
    if not q:
        return []
    res = await db.execute(
        select(Group).where(and_(
            Group.is_private == False,
            Group.name.ilike(f"%{q}%"),
        )).limit(20)
    )
    return res.scalars().all()


# ── Rejoindre un groupe public ────────────────────────────
@router.post("/{group_id}/join")
async def join_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    gres = await db.execute(select(Group).where(Group.id == group_id))
    g = gres.scalar_one_or_none()
    if not g:
        raise HTTPException(404, "Group not found")
    if g.is_private:
        raise HTTPException(403, "This group is private, you need an invitation")
    if await _is_banned(db, group_id, current_user.id):
        raise HTTPException(403, "You are banned from this group")
    # Déjà membre ?
    existing = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id,
        ))
    )
    if existing.scalar_one_or_none():
        return {"status": "already_member"}
    m = GroupMember(group_id=group_id, user_id=current_user.id, role="member")
    db.add(m)
    await db.commit()
    return {"status": "joined"}

# ── Inviter quelqu'un (owner/admin, groupe privé) ─────────
@router.post("/{group_id}/invite")
async def invite_to_group(
    group_id: int,
    data: GroupAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id,
        ))
    )
    m = res.scalar_one_or_none()
    if not m or m.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owner/admin can invite")
    # Déjà membre ?
    ex = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == data.user_id,
        ))
    )
    if ex.scalar_one_or_none():
        raise HTTPException(400, "Already a member")
    # Envoie un message DM spécial (carte invitation)
    from app.models.message import Message
    invite_msg = Message(
        sender_id=current_user.id,
        receiver_id=data.user_id,
        content=f"[GROUP_INVITE]{group_id}",
    )
    db.add(invite_msg)
    await db.commit()
    return {"status": "invited"}


# ── Mes invitations reçues ────────────────────────────────
@router.get("/invites/mine")
async def my_invites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(GroupInvite).where(GroupInvite.invited_user_id == current_user.id)
    )
    out = []
    for inv in res.scalars().all():
        gres = await db.execute(select(Group).where(Group.id == inv.group_id))
        g = gres.scalar_one_or_none()
        if g:
            out.append({
                "invite_id": inv.id, "group_id": g.id,
                "group_name": g.name, "avatar_url": g.avatar_url or "",
            })
    return out


# ── Accepter une invitation ───────────────────────────────
@router.post("/invites/{invite_id}/accept")
async def accept_invite(
    invite_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(GroupInvite).where(GroupInvite.id == invite_id))
    inv = res.scalar_one_or_none()
    if not inv or inv.invited_user_id != current_user.id:
        raise HTTPException(404, "Invite not found")
    m = GroupMember(group_id=inv.group_id, user_id=current_user.id, role="member")
    db.add(m)
    await db.delete(inv)
    await db.commit()
    return {"status": "joined"}


# ── Refuser une invitation ────────────────────────────────
@router.post("/invites/{invite_id}/decline")
async def decline_invite(
    invite_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(GroupInvite).where(GroupInvite.id == invite_id))
    inv = res.scalar_one_or_none()
    if inv and inv.invited_user_id == current_user.id:
        await db.delete(inv)
        await db.commit()
    return {"status": "declined"}

@router.post("/{group_id}/join_invited")
async def join_invited(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if await _is_banned(db, group_id, current_user.id):
        raise HTTPException(403, "You are banned from this group")
    # Déjà membre ?
    ex = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id,
        ))
    )
    if ex.scalar_one_or_none():
        return {"status": "already_member"}
    m = GroupMember(group_id=group_id, user_id=current_user.id, role="member")
    db.add(m)
    await db.commit()
    return {"status": "joined"}

# ── Promouvoir admin (owner only) ─────────────────────────
@router.post("/{group_id}/promote")
async def promote(
    group_id: int, data: ModAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    my_role = await _get_role(db, group_id, current_user.id)
    if my_role != "owner":
        raise HTTPException(403, "Only owner can promote")
    res = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == data.user_id,
        ))
    )
    m = res.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Member not found")
    m.role = "admin"
    await db.commit()
    return {"status": "promoted"}


# ── Rétrograder admin (owner only) ────────────────────────
@router.post("/{group_id}/demote")
async def demote(
    group_id: int, data: ModAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    my_role = await _get_role(db, group_id, current_user.id)
    if my_role != "owner":
        raise HTTPException(403, "Only owner can demote")
    res = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == data.user_id,
        ))
    )
    m = res.scalar_one_or_none()
    if m: m.role = "member"; await db.commit()
    return {"status": "demoted"}


# ── Exclure (kick) ────────────────────────────────────────
@router.post("/{group_id}/kick")
async def kick(
    group_id: int, data: ModAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    my_role = await _get_role(db, group_id, current_user.id)
    target_role = await _get_role(db, group_id, data.user_id)
    if my_role not in ("owner", "admin"):
        raise HTTPException(403, "Not allowed")
    if target_role == "owner":
        raise HTTPException(403, "Cannot kick the owner")
    if my_role == "admin" and target_role == "admin":
        raise HTTPException(403, "Admins cannot kick other admins")
    res = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == data.user_id,
        ))
    )
    m = res.scalar_one_or_none()
    if m: await db.delete(m); await db.commit()
    return {"status": "kicked"}


# ── Bannir (kick + empêche de revenir) ────────────────────
@router.post("/{group_id}/ban")
async def ban(
    group_id: int, data: BanAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    my_role = await _get_role(db, group_id, current_user.id)
    target_role = await _get_role(db, group_id, data.user_id)
    if my_role not in ("owner", "admin"):
        raise HTTPException(403, "Not allowed")
    if target_role == "owner":
        raise HTTPException(403, "Cannot ban the owner")
    if my_role == "admin" and target_role == "admin":
        raise HTTPException(403, "Admins cannot ban other admins")
    # Retire de la liste des membres
    res = await db.execute(
        select(GroupMember).where(and_(
            GroupMember.group_id == group_id,
            GroupMember.user_id == data.user_id,
        ))
    )
    m = res.scalar_one_or_none()
    if m: await db.delete(m)
    # Crée le ban
    until = None
    if data.days > 0:
        until = datetime.now() + timedelta(days=data.days)
    b = GroupBan(group_id=group_id, user_id=data.user_id, until=until)
    db.add(b)
    await db.commit()
    return {"status": "banned"}