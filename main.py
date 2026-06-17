from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import init_db
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.friends import router as friends_router
from app.routers.groups import router as groups_router
from app.routers.conversation import router as conversation_router
from app.routers.calls import router as calls_router
from app.routers import admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # code exécuté au démarrage
    await init_db()
    yield
    # code exécuté à l'arrêt de l'api


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok"}


app.include_router(auth_router, prefix="/auth")
app.include_router(chat_router, prefix="/chat")
app.include_router(friends_router, prefix="/friends")
app.include_router(groups_router, prefix="/groups")
app.include_router(conversation_router, prefix="/conversation")
app.include_router(calls_router, prefix="/calls")
app.include_router(admin.router)