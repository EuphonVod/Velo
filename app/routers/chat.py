from fastapi import APIRouter, WebSocket, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.dependencies import get_db
from fastapi import APIRouter, WebSocket, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database import AsyncSessionLocal
from app.dependencies import get_db
from app.models.message import Message
from app.models.user import User
from pydantic import BaseModel
from app.dependencies import get_current_user, get_db
import os
import uuid
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

UPLOAD_DIR = "uploads_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def _update_last_seen(user_id: int):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        u = result.scalar_one_or_none()
        if u:
            u.last_seen = datetime.now()
            await db.commit()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(user_id, websocket)
    await _update_last_seen(user_id)
    try:
        while True:
            data = await websocket.receive_text()
            receiver_id, message = data.split(":", 1)
            # Les signaux typing ne sont pas sauvegardés
            if message == "[TYPING]" or message == "[STOP_TYPING]":
                await manager.send_to_user(int(receiver_id), f"{user_id}:{message}")
                continue
            async with AsyncSessionLocal() as db:
                new_message = Message(
                    sender_id=user_id,
                    receiver_id=int(receiver_id),
                    content=message
                )
                db.add(new_message)
                await db.commit()
            await manager.send_to_user(int(receiver_id), f"{user_id}:{message}")
    except Exception as e:
        print(f"Erreur: {e}")
        await _update_last_seen(user_id)
        manager.disconnect(user_id)

@router.websocket("/group_ws/{group_id}/{user_id}")
async def group_websocket(websocket: WebSocket, group_id: int, user_id: int):
    await group_manager.connect(group_id, user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Vérifie que l'utilisateur est toujours membre
            from app.models.group import GroupMember
            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(GroupMember).where(
                        (GroupMember.group_id == group_id) &
                        (GroupMember.user_id == user_id)
                    )
                )
                is_member = res.scalar_one_or_none() is not None
            if not is_member:
                # Plus membre → on ferme la connexion
                await websocket.close()
                group_manager.disconnect(group_id, user_id)
                break
            # Sauvegarde et diffuse le message
            from app.models.group import GroupMessage
            async with AsyncSessionLocal() as db:
                gm = GroupMessage(group_id=group_id, sender_id=user_id, content=data)
                db.add(gm)
                await db.commit()
            async with AsyncSessionLocal() as db:
                res = await db.execute(select(User).where(User.id == user_id))
                u = res.scalar_one_or_none()
                sender_name = u.username if u else "?"
            await group_manager.broadcast(group_id, f"{sender_name}:{data}")
    except Exception as e:
        print(f"Group WS error: {e}")
        group_manager.disconnect(group_id, user_id)
@router.get("/history/{user_id}")
async def get_history(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message).where(
            or_(
                Message.sender_id == user_id,
                Message.receiver_id == user_id
            )
        )
    )
    return result.scalars().all()

@router.post("/mark_read")
async def mark_read(data: MarkReadData, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    from sqlalchemy import update
    await db.execute(
        update(Message)
        .where(
            (Message.sender_id == data.other_user_id) &
            (Message.receiver_id == current_user.id) &
            (Message.is_read == False)
        )
        .values(is_read=True)
    )
    await db.commit()
    # Notifie l'expéditeur en temps réel que ses messages sont lus
    await manager.send_to_user(data.other_user_id, f"[READ]{current_user.id}")
    return {"status": "ok"}

@router.post("/upload_file")
async def upload_file(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    ext = os.path.splitext(file.filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    # Détermine le type
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        ftype = "image"
    elif ext in (".mp4", ".webm", ".mov", ".avi", ".mkv"):
        ftype = "video"
    else:
        ftype = "file"
    return {
        "url": f"/chat/file/{safe_name}",
        "type": ftype,
        "name": file.filename,
    }

@router.get("/file/{filename}")
async def get_file(filename: str):
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Not found")
    return FileResponse(path)


#gestionnaire de connexion
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, message: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

manager = ConnectionManager()

# Gestionnaire de connexions pour les groupes
class GroupConnectionManager:
    def __init__(self):
        # {group_id: {user_id: websocket}}
        self.groups: dict = {}

    async def connect(self, group_id: int, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if group_id not in self.groups:
            self.groups[group_id] = {}
        self.groups[group_id][user_id] = websocket

    def disconnect(self, group_id: int, user_id: int):
        if group_id in self.groups:
            self.groups[group_id].pop(user_id, None)

    async def broadcast(self, group_id: int, message: str):
        if group_id in self.groups:
            for ws in self.groups[group_id].values():
                await ws.send_text(message)

group_manager = GroupConnectionManager()

class MarkReadData(BaseModel):
    other_user_id: int