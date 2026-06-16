from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, delete
from pydantic import BaseModel

from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.message import Message
from app.models.conversation import ConversationSettings

router = APIRouter()


class EphemeralUpdate(BaseModel):
    other_user_id: int
    ephemeral: bool


def _ordered(a, b):
    return (a, b) if a < b else (b, a)


#lire settings d'une conv
@router.get("/settings/{other_user_id}")
async def get_settings(
    other_user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    a, b = _ordered(current_user.id, other_user_id)
    res = await db.execute(
        select(ConversationSettings).where(and_(
            ConversationSettings.user_a_id == a,
            ConversationSettings.user_b_id == b,
        ))
    )
    cs = res.scalar_one_or_none()
    return {"ephemeral": cs.ephemeral if cs else False}


#modifier settings
@router.post("/settings")
async def set_settings(
    data: EphemeralUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    a, b = _ordered(current_user.id, data.other_user_id)
    res = await db.execute(
        select(ConversationSettings).where(and_(
            ConversationSettings.user_a_id == a,
            ConversationSettings.user_b_id == b,
        ))
    )
    cs = res.scalar_one_or_none()
    if cs:
        cs.ephemeral = data.ephemeral
    else:
        cs = ConversationSettings(user_a_id=a, user_b_id=b, ephemeral=data.ephemeral)
        db.add(cs)
    await db.commit()
    return {"ephemeral": data.ephemeral}


#delete msg lu si settings on del after reading
@router.post("/clear_read/{other_user_id}")
async def clear_read(
    other_user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    a, b = _ordered(current_user.id, other_user_id)
    #verifi mode del on read
    res = await db.execute(
        select(ConversationSettings).where(and_(
            ConversationSettings.user_a_id == a,
            ConversationSettings.user_b_id == b,
        ))
    )
    cs = res.scalar_one_or_none()
    if not cs or not cs.ephemeral:
        return {"deleted": 0}
    #delete les messages aux deux users
    await db.execute(
        delete(Message).where(and_(
            Message.is_read == True,
            or_(
                and_(Message.sender_id == current_user.id, Message.receiver_id == other_user_id),
                and_(Message.sender_id == other_user_id, Message.receiver_id == current_user.id),
            )
        ))
    )
    await db.commit()
    return {"status": "cleared"}