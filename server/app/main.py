from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import make_router
from .db import init_db
from .mcp_server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="learnos", version="0.1.0", lifespan=lifespan)
app.include_router(make_router())
app.mount("/", mcp.streamable_http_app())
