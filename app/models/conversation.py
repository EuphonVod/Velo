from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class ConversationSettings(Base):
    __tablename__ = "conversation_settings"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_a_id: Mapped[int] = mapped_column(index=True)
    user_b_id: Mapped[int] = mapped_column(index=True)
    ephemeral: Mapped[bool] = mapped_column(default=False)