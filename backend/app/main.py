import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import Base, engine
from app.routers import auth, events, manage, rsvp

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# Cache-busting build id, stamped into each page's ?v= query at startup. Baked
# at image-build time via BUILD_VERSION (a git sha + timestamp from deploy.sh)
# so a mere container restart doesn't churn caches; falls back to the process
# start time when unset (local dev), so every `uvicorn` restart busts assets.
BUILD_VERSION = re.sub(r"[^\w.-]", "", os.getenv("BUILD_VERSION") or str(int(time.time())))
_PAGE_FILES = ["index.html", "rsvp.html", "quick.html", "manage.html"]
_pages: dict[str, str] = {}


def _load_pages() -> None:
    for name in _PAGE_FILES:
        path = FRONTEND_DIR / name
        if path.exists():
            _pages[name] = re.sub(r"\?v=[\w.-]+", f"?v={BUILD_VERSION}", path.read_text())


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.upload_dir, exist_ok=True)
    _load_pages()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Idempotent column adds for events created before these fields existed.
    # create_all() won't ALTER existing tables, so do it explicitly (matches the
    # calorieapp migration style). Each is a no-op once the column is present.
    event_column_migrations = [
        ("event_end", "TIMESTAMP"),
        ("host_email", "VARCHAR"),
        ("manage_token", "VARCHAR"),
        ("image_fit", "VARCHAR NOT NULL DEFAULT 'contain'"),
    ]
    for col, decl in event_column_migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"ALTER TABLE events ADD COLUMN {col} {decl}"))
            print(f"[MIGRATION] Added events.{col}")
        except Exception:
            pass  # column already exists
    print("=" * 56)
    print("  invitio API")
    print("=" * 56)
    print(f"  Debug:        {settings.debug}")
    print(f"  DB Provider:  {settings.database_provider}")
    print(f"  DB URL:       {settings.database_url}")
    print(f"  Upload dir:   {settings.upload_dir}")
    print(f"  Public URL:   {settings.public_base_url}")
    print(f"  Email:        {'configured' if settings.gmail_app_password else 'disabled (links only)'}")
    print(f"  Build:        {BUILD_VERSION}")
    print("=" * 56)
    yield
    print("[SHUTDOWN] invitio shutting down")


app = FastAPI(title="invitio API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(events.router)
app.include_router(manage.router)
app.include_router(rsvp.router)

# Uploaded invite images (bind-mounted volume on the NAS).
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
# Frontend static assets (css/js).
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

_NO_CACHE = {"Cache-Control": "no-cache"}


def _page(name: str) -> HTMLResponse:
    # Served no-cache (the page carries the build-stamped ?v=), so a new deploy
    # is picked up immediately and in turn busts the versioned css/js URLs.
    html = _pages.get(name)
    if html is None:  # not preloaded (e.g. reload edge case) — read on demand
        html = re.sub(r"\?v=[\w.-]+", f"?v={BUILD_VERSION}", (FRONTEND_DIR / name).read_text())
    return HTMLResponse(content=html, headers=_NO_CACHE)


@app.get("/")
def index():
    return _page("index.html")


@app.get("/quick")
def quick_create_page():
    # No-account event creation. Posts to /api/public/events, then redirects to /m/<token>.
    return _page("quick.html")


@app.get("/e/{token}")
def share_rsvp_page(token: str):
    # Public RSVP via the shareable event link. Token is read client-side.
    return _page("rsvp.html")


@app.get("/i/{token}")
def invite_rsvp_page(token: str):
    # Public RSVP via a personalized invite link. Token is read client-side.
    return _page("rsvp.html")


@app.get("/m/{token}")
def manage_page(token: str):
    # No-account management UI. Token is read client-side and never sent to the host app.
    return _page("manage.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}
