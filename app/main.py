"""FastAPI entry point.

Serves the JSON API under /api and (when built) the static Next.js export at /,
on a single origin bound to 0.0.0.0 so a phone on the Tailnet can reach it.

Run (daily): uvicorn app.main:app --host 0.0.0.0 --port 8000
Run (dev):   uvicorn app.main:app --reload   (frontend via `next dev` proxying /api)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import get_config
from app.db import init_db
from app.routers import (
    actions,
    artifacts,
    attention,
    chat,
    health,
    notes,
    opportunities,
    runs,
    settings,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Opportunity Hunter", version=__version__, lifespan=lifespan)

app.include_router(health.router)
app.include_router(settings.router)
app.include_router(chat.router)
app.include_router(notes.router)
app.include_router(runs.router)
app.include_router(opportunities.router)
app.include_router(opportunities.board_router)
app.include_router(actions.router)
app.include_router(artifacts.router)
app.include_router(attention.router)

# Serve the built frontend (static export) at / when it exists. Mounted last so
# /api/* routes take precedence. html=True serves index.html for the SPA root.
_frontend_dir = get_config().frontend_dir
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
