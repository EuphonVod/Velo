from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import init_db
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.friends import router as friends_router
from app.routers.groups import router as groups_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    #code executer au démarage
    await init_db()
    yield
    #code executer à larret api


app = FastAPI(lifespan=lifespan)

app.include_router(auth_router, prefix="/auth")
app.include_router(chat_router, prefix="/chat")

@app.get("/")
async def root():
    return {"status": "ok"}

app.include_router(auth_router, prefix="/auth")
app.include_router(chat_router, prefix="/chat")
app.include_router(friends_router, prefix="/friends")
app.include_router(groups_router, prefix="/groups")