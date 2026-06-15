import asyncio
from app.database import engine
from sqlalchemy import text

async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text('ALTER TABLE group_message ADD COLUMN IF NOT EXISTS edited BOOLEAN DEFAULT FALSE'))
        print("Migration OK !")

asyncio.run(migrate())