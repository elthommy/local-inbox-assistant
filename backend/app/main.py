import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .db import init_db
from .indexer import run_index

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Kick an incremental index in the background on startup.
    index_task = asyncio.create_task(run_index())
    yield
    index_task.cancel()


app = FastAPI(title="local-inbox-assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # the vite dev proxy makes /api same-origin; this only matters when the
    # frontend talks to the backend directly, so allow any localhost port
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
