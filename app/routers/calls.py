from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()


class CallManager:
    def __init__(self):
        # {user_id: websocket}
        self.connections: dict = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections[user_id] = websocket

    def disconnect(self, user_id: int):
        self.connections.pop(user_id, None)

    async def relay(self, to_user: int, message: dict):
        if to_user in self.connections:
            await self.connections[to_user].send_text(json.dumps(message))
            return True
        return False


call_manager = CallManager()


@router.websocket("/ws/{user_id}")
async def call_signaling(websocket: WebSocket, user_id: int):
    await call_manager.connect(user_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            # Chaque message a un champ "to" (destinataire) et "type"
            to_user = msg.get("to")
            msg["from"] = user_id
            if to_user is not None:
                delivered = await call_manager.relay(int(to_user), msg)
                # Si le destinataire n'est pas connecté, on informe l'appelant
                if not delivered and msg.get("type") == "call_invite":
                    await websocket.send_text(json.dumps({
                        "type": "call_unavailable",
                        "from": to_user,
                    }))
    except WebSocketDisconnect:
        call_manager.disconnect(user_id)
    except Exception as e:
        print(f"Call signaling error: {e}")
        call_manager.disconnect(user_id)