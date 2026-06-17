from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Warning(Base):
    __tablename__ = "warning"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    reason: Mapped[str] = mapped_column()
    severity: Mapped[str] = mapped_column(default="warning")  # warning | severe
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

class Report(Base):
    __tablename__ = "report"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    reported_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    reason: Mapped[str] = mapped_column()
    status: Mapped[str] = mapped_column(default="pending")  # pending | resolved
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

class AdminNote(Base):
    __tablename__ = "admin_note"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    note: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)