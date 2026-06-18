from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class PhoneCode(Base):
    __tablename__ = "phone_code"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(index=True)
    code: Mapped[str] = mapped_column()
    purpose: Mapped[str] = mapped_column(default="login")  # login | delete_account | nuke_messages
    expires_at: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
