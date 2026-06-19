from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import MetaData
from dotenv import load_dotenv
import os
from app.models import Base
from app.models.message import Message
from app.models.friendship import Friendship
from app.models.group import Group, GroupMember, GroupMessage
from app.models.group import Group, GroupMember, GroupMessage, GroupInvite
from app.models.group import Group, GroupMember, GroupMessage, GroupInvite, GroupBan
from app.models.conversation import ConversationSettings
from app.models.verification import PhoneCode
from app.models.moderation import Warnings, Report, AdminNote
from app.models.audit import AuditLog

#load la file en .env
load_dotenv()
#récupère l'url de la base de donné à partir de la file .env
db_url = os.getenv('DATABASE_URL')
engine = create_async_engine(db_url)

meta = MetaData()
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
