from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey
from datetime import datetime
from app.models import Base

class Friendship(Base):
    __tablename__ = "friendship"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    addressee_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    status: Mapped[str] = mapped_column(default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)