import asyncio
import html
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
from app.models import Event, EventImage, Invite
from app import reminder_service
from app.routers import ai, auth, events, manage, rsvp

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# Cache-busting build id, stamped into each page's ?v= query at startup. Baked
# at image-build time via BUILD_VERSION (a git sha + timestamp from deploy.sh)
# so a mere container restart doesn't churn caches; falls back to the process
# start time when unset (local dev), so every `uvicorn` restart busts assets.
BUILD_VERSION = re.sub(r"[^\w.-]", "", os.getenv("BUILD_VERSION") or str(int(time.time())))
_PAGE_FILES = ["index.html", "rsvp.html", "quick.html", "manage.html"]
_pages: dict[str, str] = {}
# Service worker, served from root with its cache name stamped to the build id so
# every deploy invalidates the installed PWA's cache. Filled by _load_pages().
_sw_js: str = ""


def _load_pages() -> None:
    global _sw_js
    for name in _PAGE_FILES:
        path = FRONTEND_DIR / name
        if path.exists():
            _pages[name] = re.sub(r"\?v=[\w.-]+", f"?v={BUILD_VERSION}", path.read_text())
    sw_path = FRONTEND_DIR / "sw.js"
    if sw_path.exists():
        _sw_js = re.sub(r"invitio-v[\w.-]+", f"invitio-v{BUILD_VERSION}", sw_path.read_text())


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
        ("rsvp_deadline", "TIMESTAMP"),
        ("host_email", "VARCHAR"),
        ("manage_token", "VARCHAR"),
        ("image_fit", "VARCHAR NOT NULL DEFAULT 'contain'"),
        ("reminder_sent_at", "TIMESTAMP"),
        ("timezone", "VARCHAR"),
        ("wall_enabled", "BOOLEAN NOT NULL DEFAULT false"),
        ("guestlist_public", "BOOLEAN NOT NULL DEFAULT false"),
        ("image_focal_x", "FLOAT NOT NULL DEFAULT 50"),
        ("image_focal_y", "FLOAT NOT NULL DEFAULT 50"),
        ("image_thumb_path", "VARCHAR"),
    ]
    for col, decl in event_column_migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"ALTER TABLE events ADD COLUMN {col} {decl}"))
            print(f"[MIGRATION] Added events.{col}")
        except Exception:
            pass  # column already exists

    # Same idempotent pattern for columns added to other tables after they existed.
    other_column_migrations = [
        ("invites", "viewed_at", "TIMESTAMP"),
        ("invites", "last_viewed_at", "TIMESTAMP"),
        ("invites", "view_count", "INTEGER NOT NULL DEFAULT 0"),
        ("invites", "email_opened_at", "TIMESTAMP"),
        ("invites", "email_open_count", "INTEGER NOT NULL DEFAULT 0"),
        ("event_images", "thumb_path", "VARCHAR"),
    ]
    for table, col, decl in other_column_migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))
            print(f"[MIGRATION] Added {table}.{col}")
        except Exception:
            pass  # column already exists

    # The invite_id FKs on rsvps/invite_views were originally created without an
    # ON DELETE rule, so deleting an event (which cascade-deletes both invites and
    # rsvps) could hit a FK violation if invites were deleted first. Recreate the
    # constraints with ON DELETE SET NULL so the DB resolves the ordering itself.
    # Postgres-only: SQLite can't ALTER constraints and create_all() already bakes
    # the rule into fresh sqlite DBs (where FK enforcement is off by default).
    if settings.database_provider == "postgres":
        fk_migrations = [
            ("rsvps", "rsvps_invite_id_fkey"),
            ("invite_views", "invite_views_invite_id_fkey"),
        ]
        for table, constraint in fk_migrations:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"))
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                        f"FOREIGN KEY (invite_id) REFERENCES invites(id) ON DELETE SET NULL"
                    ))
                print(f"[MIGRATION] {table}.invite_id -> ON DELETE SET NULL")
            except Exception as exc:
                print(f"[MIGRATION] {constraint} skipped: {exc}")

    # Backfill the gallery for events created before event_images existed: each
    # event with a cover path but no rows gets one cover image. Idempotent.
    try:
        async with AsyncSessionLocal() as db:
            with_images = set((await db.execute(select(EventImage.event_id))).scalars().all())
            legacy = (
                await db.execute(select(Event).where(Event.image_path.is_not(None)))
            ).scalars().all()
            added = 0
            for ev in legacy:
                if ev.id in with_images:
                    continue
                db.add(EventImage(event_id=ev.id, path=ev.image_path, position=0, is_cover=True))
                added += 1
            if added:
                await db.commit()
                print(f"[MIGRATION] Backfilled {added} cover image(s) into event_images")
    except Exception as exc:
        print(f"[MIGRATION] image backfill skipped: {exc}")
    print("=" * 56)
    print("  invitio API")
    print("=" * 56)
    print(f"  Debug:        {settings.debug}")
    print(f"  DB Provider:  {settings.database_provider}")
    print(f"  DB URL:       {settings.database_url}")
    print(f"  Upload dir:   {settings.upload_dir}")
    print(f"  Public URL:   {settings.public_base_url}")
    print(f"  Email:        {'configured' if settings.gmail_app_password else 'disabled (links only)'}")
    print(f"  Reminders:    {'on' if reminder_service.should_run() else 'off'}")
    print(f"  Quick create: {'on' if settings.quick_create_enabled else 'off'}")
    print(f"  Build:        {BUILD_VERSION}")
    print("=" * 56)

    reminder_task: asyncio.Task | None = None
    if reminder_service.should_run():
        reminder_task = asyncio.create_task(reminder_service.reminder_loop())

    yield

    print("[SHUTDOWN] invitio shutting down")
    if reminder_task:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass


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
app.include_router(ai.router)

# Uploaded invite images (bind-mounted volume on the NAS).
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
# Frontend static assets (css/js).
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

_NO_CACHE = {"Cache-Control": "no-cache"}


def _page(name: str) -> HTMLResponse:
    # Served no-cache (the page carries the build-stamped ?v=), so a new deploy
    # is picked up immediately and in turn busts the versioned css/js URLs.
    content = _pages.get(name)
    if content is None:  # not preloaded (e.g. reload edge case) — read on demand
        content = re.sub(r"\?v=[\w.-]+", f"?v={BUILD_VERSION}", (FRONTEND_DIR / name).read_text())
    return HTMLResponse(content=content, headers=_NO_CACHE)


# --- Social link previews (Open Graph / Twitter Card) -----------------------
# rsvp.html carries a <!--SOCIAL_META--> placeholder. For tokened RSVP routes we
# look up the event and replace it with per-event og:/twitter: tags so links
# pasted into iMessage/WhatsApp/Facebook/Slack unfurl with the invite image and
# title instead of a generic "invitio" card.

_SOCIAL_PLACEHOLDER = "<!--SOCIAL_META-->"
_DEFAULT_TITLE = "You're invited — invitio"
_DEFAULT_DESC = "You've been invited! RSVP now."


def _event_summary(event: Event) -> str:
    """A one-line human description from date/location, for events with no
    description of their own."""
    bits: list[str] = []
    if event.host_display_name:
        bits.append(f"Hosted by {event.host_display_name}")
    if event.event_date:
        bits.append(event.event_date.strftime("%a, %b %-d · %-I:%M %p"))
    if event.location:
        bits.append(event.location)
    return " · ".join(bits) or "You're invited! RSVP now."


def _meta(prop: str, content: str, *, name: bool = False) -> str:
    attr = "name" if name else "property"
    return f'    <meta {attr}="{html.escape(prop, quote=True)}" content="{html.escape(content, quote=True)}">'


def _social_meta(event: Event | None, url: str) -> str:
    """Build the <title> + og/twitter meta block injected into rsvp.html."""
    if event is None:
        title, desc, image = _DEFAULT_TITLE, _DEFAULT_DESC, None
    else:
        title = event.title or "You're invited"
        desc = (event.description or "").strip() or _event_summary(event)
        if len(desc) > 200:
            desc = desc[:197].rstrip() + "…"
        image = (settings.public_base_url + event.image_path) if event.image_path else None

    lines = [
        f"    <title>{html.escape(title)}</title>",
        _meta("description", desc, name=True),
        _meta("og:title", title),
        _meta("og:description", desc),
        _meta("og:type", "website"),
        _meta("og:url", url),
        _meta("og:site_name", "invitio"),
    ]
    if image:
        lines += [
            _meta("og:image", image),
            _meta("twitter:card", "summary_large_image", name=True),
            _meta("twitter:image", image, name=True),
        ]
    else:
        lines.append(_meta("twitter:card", "summary", name=True))
    lines += [
        _meta("twitter:title", title, name=True),
        _meta("twitter:description", desc, name=True),
    ]
    return "\n".join(lines)


async def _event_for_token(token: str, *, invite: bool) -> Event | None:
    """Resolve a URL token to its Event for OG injection. /i/ tokens are invite
    tokens; /e/ tokens are the event's public token. Returns None if unknown."""
    async with AsyncSessionLocal() as db:
        if invite:
            inv = (await db.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
            if not inv:
                return None
            return (await db.execute(select(Event).where(Event.id == inv.event_id))).scalar_one_or_none()
        return (await db.execute(select(Event).where(Event.public_token == token))).scalar_one_or_none()


async def _rsvp_page(token: str, *, invite: bool) -> HTMLResponse:
    resp = _page("rsvp.html")
    path = f"/i/{token}" if invite else f"/e/{token}"
    try:
        event = await _event_for_token(token, invite=invite)
    except Exception:
        event = None  # never let a lookup hiccup break the page render
    meta = _social_meta(event, f"{settings.public_base_url}{path}")
    resp.body = resp.body.replace(_SOCIAL_PLACEHOLDER.encode(), meta.encode())
    resp.headers["content-length"] = str(len(resp.body))
    return resp


@app.get("/")
def index():
    return _page("index.html")


@app.get("/sw.js")
def service_worker():
    # Served from root so its scope covers the whole app (a SW under /static could
    # only control /static/*). Build-stamped at startup; no-cache so the browser
    # always re-checks it and picks up a new version.
    return Response(_sw_js, media_type="application/javascript", headers=_NO_CACHE)


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(FRONTEND_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/api/config")
def app_config():
    # Public feature flags the frontend reads to show/hide no-account UI.
    return {"quick_create": settings.quick_create_enabled}


@app.get("/quick")
def quick_create_page():
    # No-account event creation. Posts to /api/public/events, then redirects to /m/<token>.
    if not settings.quick_create_enabled:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return _page("quick.html")


@app.get("/e/{token}")
async def share_rsvp_page(token: str):
    # Public RSVP via the shareable event link. Token is read client-side; the
    # server injects per-event Open Graph tags so the link unfurls when shared.
    return await _rsvp_page(token, invite=False)


@app.get("/i/{token}")
async def invite_rsvp_page(token: str):
    # Public RSVP via a personalized invite link. Token is read client-side; the
    # server injects per-event Open Graph tags so the link unfurls when shared.
    return await _rsvp_page(token, invite=True)


@app.get("/m/{token}")
def manage_page(token: str):
    # No-account management UI. Token is read client-side and never sent to the host app.
    return _page("manage.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}
