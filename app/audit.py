from app.models.audit import AuditLog
from app.database import AsyncSessionLocal


async def record(db, actor_id, action, target_id=None, details=""):
    try:
        async with AsyncSessionLocal() as session:
            session.add(AuditLog(
                actor_id=actor_id,
                action=action,
                target_id=target_id,
                details=(details or "")[:1000],
            ))
            await session.commit()
    except Exception:
        # L'audit ne doit jamais faire échouer l'action principale.
        pass