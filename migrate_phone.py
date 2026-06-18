"""Migration : passage du login email/mot de passe au login par téléphone.

`Base.metadata.create_all` ne modifie PAS les tables déjà existantes : sur une
base déjà déployée (Render), il faut donc altérer la table `user` à la main.
À lancer UNE fois après le déploiement :  python migrate_phone.py

Sur une base vierge, ce script n'est pas nécessaire (create_all suffit).
ATTENTION : les comptes existants n'ont pas de numéro et ne pourront plus se
connecter tant qu'on ne leur en attribue pas un.
"""
import asyncio
from app.database import engine
from sqlalchemy import text

STATEMENTS = [
    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS phone VARCHAR',
    'ALTER TABLE "user" DROP COLUMN IF EXISTS email',
    'ALTER TABLE "user" DROP COLUMN IF EXISTS hashed_password',
    'CREATE UNIQUE INDEX IF NOT EXISTS ix_user_phone ON "user" (phone)',
]


async def run():
    async with engine.begin() as conn:
        for stmt in STATEMENTS:
            print(f"-> {stmt}")
            await conn.execute(text(stmt))
    print("Migration terminée.")


asyncio.run(run())
