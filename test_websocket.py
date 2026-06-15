import websocket

ws = websocket.WebSocket()
try:
    ws.connect("wss://velo-n1cd.onrender.com/chat/ws/1")
    print("✓ WebSocket CONNECTÉ !")
    ws.close()
except Exception as e:
    print("✗ Erreur:", e)