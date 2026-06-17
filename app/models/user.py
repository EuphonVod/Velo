from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text
from datetime import datetime
from app.models import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    username: Mapped[str] = mapped_column(index=True, unique=True)
    slug: Mapped[str] = mapped_column(index=True, unique=True)
    email: Mapped[str] = mapped_column(index=True, unique=True)
    hashed_password: Mapped[str]
    is_superuser: Mapped[bool] = mapped_column(default=False)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=True)
    avatar_url: Mapped[str] = mapped_column(default="", nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    is_private: Mapped[bool] = mapped_column(default=False, nullable=True)
    show_online: Mapped[bool] = mapped_column(default=True, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(default=datetime.now, nullable=True)
    ip: Mapped[str] = mapped_column(index=True, nullable=True, default="")

class GlobalBannedIP(Base):
    __tablename__ = "global_banned_ip"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(index=True, unique=True)
    reason: Mapped[str] = mapped_column(default="", nullable=True)
