from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey
from datetime import datetime
from app.models import Base

class Group(Base):
    __tablename__ = "group"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(index=True)
    bio: Mapped[str] = mapped_column(default="", nullable=True)
    avatar_url: Mapped[str] = mapped_column(default="", nullable=True)
    is_private: Mapped[bool] = mapped_column(default=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class GroupMember(Base):
    __tablename__ = "group_member"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    role: Mapped[str] = mapped_column(default="member")  # owner | admin | member
    joined_at: Mapped[datetime] = mapped_column(default=datetime.now)


class GroupMessage(Base):
    __tablename__ = "group_message"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    content: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    edited: Mapped[bool] = mapped_column(default=False, nullable=True)


class GroupInvite(Base):
    __tablename__ = "group_invite"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"), index=True)
    invited_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    invited_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

class GroupBan(Base):
    __tablename__ = "group_ban"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    until: Mapped[datetime] = mapped_column(nullable=True)  # None = permanent
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

class GroupBannedIP(Base):
    __tablename__ = "group_banned_ip"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(index=True)
    ip: Mapped[str] = mapped_column(index=True)