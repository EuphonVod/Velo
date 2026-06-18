from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
import jwt
import os

from app.database import AsyncSessionLocal

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/verify_code")
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
    user_id = payload.get("user_id")
    get_user_id = await db.execute(select(User).where(User.id == user_id))
    db_user = get_user_id.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return db_user
