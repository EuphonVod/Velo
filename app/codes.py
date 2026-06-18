"""Génération et vérification des codes de connexion à 6 chiffres.

Pas de fournisseur SMS (Twilio, etc.) pour l'instant : le code est simplement
généré, affiché dans les logs du serveur et renvoyé dans la réponse API en mode
dev pour pouvoir tester l'interface. À remplacer par un vrai envoi SMS plus tard.
"""
import random
from datetime import datetime, timedelta

from sqlalchemy import select, delete

from app.models.verification import PhoneCode

CODE_TTL_MINUTES = 10


async def create_code(db, phone: str, purpose: str = "login") -> str:
    """Génère un code, remplace tout code précédent pour ce (phone, purpose)."""
    code = f"{random.randint(0, 999999):06d}"
    await db.execute(
        delete(PhoneCode).where(
            (PhoneCode.phone == phone) & (PhoneCode.purpose == purpose)
        )
    )
    db.add(PhoneCode(
        phone=phone,
        code=code,
        purpose=purpose,
        expires_at=datetime.now() + timedelta(minutes=CODE_TTL_MINUTES),
    ))
    await db.commit()
    # En attendant un vrai SMS : on log le code côté serveur.
    print(f"[DEV] Code de vérification pour {phone} ({purpose}) : {code}")
    return code


async def verify_code(db, phone: str, code: str, purpose: str = "login") -> bool:
    """Vérifie un code et le consomme (suppression) s'il est valide."""
    res = await db.execute(
        select(PhoneCode).where(
            (PhoneCode.phone == phone) & (PhoneCode.purpose == purpose)
        )
    )
    pc = res.scalar_one_or_none()
    if pc is None:
        return False
    if pc.expires_at < datetime.now():
        await db.execute(delete(PhoneCode).where(PhoneCode.id == pc.id))
        await db.commit()
        return False
    if pc.code != code.strip():
        return False
    await db.execute(delete(PhoneCode).where(PhoneCode.id == pc.id))
    await db.commit()
    return True
