
from app.models.audit import AuditLog


async def record(db, actor_id, action, target_id=None, details=""):

    try:
        db.add(AuditLog(
            actor_id=actor_id,
            action=action,
            target_id=target_id,
            details=(details or "")[:1000],
        ))
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
