import asyncio
from app.database import engine
from sqlalchemy import text

# Mets ici le numéro de téléphone du compte à promouvoir admin.
ADMIN_PHONE = "+33600000000"


async def run():
    async with engine.begin() as conn:
        await conn.execute(text(
            'UPDATE "user" SET is_superuser = true WHERE phone = :phone'
        ), {"phone": ADMIN_PHONE})
        print("Admin OK !")

asyncio.run(run())
