import websocket
websocket.enableTrace(True)  # affiche tous les détails

ws = websocket.WebSocket()
try:
    ws.connect("wss://velo-n1cd.onrender.com/chat/ws/1")
    print("✓ CONNECTÉ")
    ws.close()
except Exception as e:
    print("✗ Erreur:", e)