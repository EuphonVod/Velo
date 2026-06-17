import asyncio
from app.database import engine
from sqlalchemy import text

async def run():
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE \"user\" SET is_superuser = true WHERE email = 'hi@gmail.com'"))
        print("Admin OK !")

asyncio.run(run())