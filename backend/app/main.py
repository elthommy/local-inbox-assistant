import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse

from .api import router
from .db import apply_setting_overrides, init_db
from .indexer import run_index

logging.basicConfig(level=logging.INFO)

# Browser-facing origins allowed to call the API (the frontend on any localhost
# port). Other local processes are trusted anyway (see AGENTS.md security model).
LOCAL_ORIGIN_RE = r"http://(localhost|127\.0\.0\.1)(:\d+)?"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Init the DB and kick a background index run for the app's lifetime."""
    init_db()
    apply_setting_overrides()
    # Kick an incremental index in the background on startup.
    index_task = asyncio.create_task(run_index())
    yield
    index_task.cancel()


app = FastAPI(title="local-inbox-assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # the vite dev proxy makes /api same-origin; this only matters when the
    # frontend talks to the backend directly, so allow any localhost port
    allow_origin_regex=LOCAL_ORIGIN_RE,
    allow_methods=["*"],
    allow_headers=["*"],
)
# DNS rebinding: reject requests whose Host is not loopback (a rebound
# attacker page sends its own domain). Starlette ignores the port.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


@app.middleware("http")
async def reject_cross_site_writes(request, call_next):
    """Block state-changing requests from non-localhost web origins (CSRF).

    Body-less and form POSTs are CORS "simple requests": the browser sends them
    cross-site without a preflight, so CORS alone does not stop them.
    """
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (
            origin is not None and not re.fullmatch(LOCAL_ORIGIN_RE, origin)
        ):
            return PlainTextResponse("cross-site request blocked", status_code=403)
    return await call_next(request)


app.include_router(router)
