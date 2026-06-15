from fastapi import APIRouter, Depends, HTTPException
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token, UserUpdate
import bcrypt
from app.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from sqlalchemy import select, or_
from app.dependencies import get_current_user
import jwt
import os


router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Vérifie si username ou email existe déjà
    existing = await db.execute(select(User).where(User.username == user.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    existing_email = await db.execute(select(User).where(User.email == user.email))
    if existing_email.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    password_bytes = user.password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    user_db = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        slug=user.username.lower(),
        bio="",
        avatar_url="",
    )
    db.add(user_db)
    await db.commit()
    await db.refresh(user_db)
    return user_db


@router.post("/login", response_model=Token)
async def login(user: UserLogin, db: AsyncSession = Depends(get_db)):
    # Accepte email OU username via le champ "identifier"
    identifier = (user.identifier or user.email or "").strip()
    result_user = await db.execute(
        select(User).where(
            or_(User.email == identifier, User.slug == identifier.lower())
        )
    )
    db_user = result_user.scalar_one_or_none()

    if db_user is None:
        raise HTTPException(status_code=404, detail="Unknown")

    password_ok = bcrypt.checkpw(
        user.password.encode("utf-8"),
        db_user.hashed_password.encode("utf-8")
    )
    if not password_ok:
        raise HTTPException(status_code=401, detail="Wrong password")

    SECRET_KEY = os.getenv("SECRET_KEY")
    token = jwt.encode(
        {"user_id": db_user.id},
        SECRET_KEY,
        algorithm="HS256"
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
        data: UserUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user_db = result.scalar_one_or_none()

    if data.bio is not None:
        user_db.bio = data.bio
    if data.avatar_url is not None:
        user_db.avatar_url = data.avatar_url
    if data.username is not None:
        user_db.username = data.username
        user_db.slug = data.username.lower()
    if data.is_private is not None:
        user_db.is_private = data.is_private
    if data.show_online is not None:
        user_db.show_online = data.show_online


    await db.commit()
    await db.refresh(user_db)
    return user_db


@router.get("/users", response_model=list[UserResponse])
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

