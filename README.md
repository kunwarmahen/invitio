# ✦ invitio

A self-hosted, **Evite-style** invitation app. Create an event, upload your own
image, then invite guests by email or just share a link — they RSVP from any
device without needing an account. Watch responses roll in on a live dashboard.

Built to slot into the same NAS workflow as
[calorieapp](https://github.com/kunwarmahen/calorieapp): FastAPI + async
SQLAlchemy backend, a vanilla-JS frontend, Gmail SMTP for outbound mail, shipped
as a single Docker image deployed over SSH by `deploy.sh` behind the Asustor
reverse proxy.

## Features

- **Host accounts** — email/password signup, JWT sessions.
- **No-account "quick create"** — make one event with no signup at `/quick`; you
  get a secret manage link (`/m/<token>`, optionally emailed to you) that
  administers the event without logging in. Gated by `QUICK_CREATE_ENABLED` — set
  it to `false` to require an account (the page redirects home, the API returns
  403, and the link is hidden; existing quick events keep working).
- **Create events** — title, start/end date/time, location, description, host
  name, theme, and a **custom uploaded hero image**, shown **whole/uncropped by
  default** (over a blurred backdrop); a toggle switches to crop-to-fill.
- **Templates** — pick from plain accent palettes or **seasonal/occasion
  templates** (Birthday, Wedding, Christmas, Halloween, Baby, New Year, Autumn,
  Spring), each with its own palette and decorative motif on the envelope.
- **Photo gallery** — add **multiple photos** per event, drag to reorder, and
  choose any one as the cover; extra photos show as a strip on the invite with a
  full-screen lightbox carousel.
- **Focal-point crop** — in crop-to-fill mode, drag a point on the cover photo to
  choose what stays visible in the hero, cards, and thumbnails.
- **Punchbowl-style envelope reveal** — guests land on a sealed, themed envelope
  that opens and slides *your invitation image* out, then shows the full invite
  (plays once per visit; honours reduced-motion).
- **Tap to zoom** — guests can open the invite image full-screen.
- **Invite by email** — each guest gets a unique tokenized RSVP link (emailed
  via Gmail when configured).
- **Share a link** — one public link anyone can open and RSVP through, with
  one-tap **WhatsApp / SMS / email share buttons** (plus the native share sheet
  on mobile) on the host + manage dashboards.
- **Social link previews** — RSVP links carry per-event Open Graph / Twitter
  Card tags (title, description, invite image), so pasting one into
  iMessage/WhatsApp/Facebook/Slack unfurls with the actual invite.
- **Open tracking** — a browser beacon records when a guest actually opens their
  invite (so link-preview bots that don't run JS don't inflate it). The guest list
  shows open count + last-opened time, and an **"Invite opens" log** on the host +
  manage dashboards lists each open with its **IP, device, and time** (opens of the
  forwardable public link show as anonymous). Invite + reminder emails also carry a
  soft, **IP-free email-open pixel** — a weak "rendered somewhere" hint shown as
  *📧 email opened*, kept separate from the browser-accurate counts because
  Apple/Gmail privacy proxies over- and under-count email opens.
- **Invite a friend** — a forwardable share row on the RSVP page that passes the
  *public* event link (never the guest's personal token), so anyone can pass the
  invite along without being able to RSVP as someone else.
- **RSVP without login** — yes / maybe / no, party size (+1s), and a note.
  Re-submitting updates the existing response instead of duplicating it. A
  "yes" gets a celebratory confetti burst (skipped under reduced-motion).
- **RSVP deadline** — set an optional "RSVP by" date; guests see it on the invite
  and the host/co-hosts see it on the dashboard for headcount planning. Soft by
  design — responses are still accepted after it passes.
- **Custom RSVP questions** — host-defined questions (free text, single-choice,
  or multi-select), optionally required; answers show on the dashboard.
- **Message all guests** — broadcast an update or cancellation by email,
  targeted by RSVP status (everyone / yes / maybe / no / not-yet-responded).
- **Cancel an event** — call off an event without deleting it: guests see a
  "cancelled" notice (plus your optional message) on the invite and can no longer
  RSVP, while you keep the guest list and all responses. Optionally email everyone
  the cancellation, and **reinstate** it later to reopen.
- **Duplicate an event** — clone last year's invite into a fresh draft: it copies
  the details, theme, photos, and custom questions but starts with a clean guest
  list, no responses, new links, and a blank date for you to set.
- **Guest wall** — optional public well-wishes board and a "who's coming" list
  on the invite, each toggleable per event; the host can moderate posts.
- **Co-hosts** — share full event management with another invitio account
  (owner keeps delete + co-host control).
- **AI generation (optional)** — generate invite copy, broadcast drafts, and a
  hero image from any OpenAI-compatible endpoint. Local-first: Ollama / llama.cpp
  for text, LocalAI (SDXL/FLUX) for images. Invite copy takes a **tone** (warm,
  funny, heartfelt, elegant, playful, exciting, somber, casual) and **builds on
  whatever you've already typed** in the description rather than rewriting from the
  title — so it polishes your draft and won't invent names or pronouns. Off until
  configured; see `.env.example`.
- **Host RSVP notifications** — the host gets an email the moment a guest
  responds (works for both account and quick-create events).
- **Reminder emails** — a background loop emails a reminder to "yes" guests and
  nudges non-responders before each event (once per event; configurable window).
- **Add to Calendar** — guests get Google Calendar + `.ics` (Apple/Outlook)
  buttons on the invite and after RSVPing yes.
- **Timezone-correct times** — each event captures its timezone, so every guest
  sees the same local time (e.g. "6:00 PM EDT") no matter where they are.
- **Location map** — when an event has a location, the invite shows an embedded
  map preview + an "Open in Maps" link (keyless Google Maps; opens the native app
  on mobile).
- **Dark mode** — the whole UI (dashboard, manage, invite) adapts to a light or
  dark scheme; follows the device by default with a 🖥️/☀️/🌙 toggle on the host
  chrome (persisted).
- **Installable PWA** — add invitio to your home screen; a service worker caches
  the app shell so the dashboard loads offline (network-first, so data/invites are
  never stale).
- **Dashboard** — response counts, head count, and a paginated guest + response
  list ("Show more" loads the rest on demand for large events).
- **Optimized images** — uploads are validated by their real bytes (not a
  trusted Content-Type), auto-downsized + recompressed, and thumbnailed, so the
  envelope and cards load a small file instead of a 12 MP phone photo.
- **Anti-abuse rate limiting** — the open no-account flows (quick-create, RSVP,
  guest wall) and auth are rate-limited per IP so they can't be trivially spammed
  (configurable; off-switch in `.env`).

## Tech stack

FastAPI · async SQLAlchemy 2 · SQLite (dev) / PostgreSQL (prod) · bcrypt + JWT ·
Gmail SMTP · Pillow · vanilla HTML/CSS/JS · Docker · pytest.

## Quick start (local)

```bash
cp .env.example .env          # optional — deploy.sh does this for you
./deploy.sh local up          # build + run on http://localhost:8080
```

Or without Docker:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=backend uvicorn app.main:app --reload --port 8080
# open http://localhost:8080
```

1. Sign up as a host.
2. Create an event and upload an image.
3. Copy the **share link**, or add guest emails under **Invite by email**.
4. Open the share link in another browser/incognito to RSVP.

> Emailing invites is optional. Without `GMAIL_APP_PASSWORD` set, the app still
> creates events and links — you just copy and share them yourself.

### Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
cd backend && pytest
```

The suite (`backend/tests/`) runs against a throwaway SQLite DB via httpx's
ASGITransport — no server or network needed. It covers auth, the RSVP/manage
flows, open tracking (the view beacon's IP log + the email-open pixel), the image
pipeline (resize + magic-byte sniffing), pagination, and rate limiting.

> **SQLite-only caveat.** Because the tests use SQLite, Postgres-specific issues
> aren't caught — e.g. SQLite accepts tz-aware datetimes while asyncpg rejects
> them for the naive (`TIMESTAMP WITHOUT TIME ZONE`) columns. The app stores
> **naive UTC** everywhere for this reason; keep new `datetime` writes naive
> (`...replace(tzinfo=None)`).

### Asset cache-busting

`deploy.sh` bakes a `BUILD_VERSION` (git sha + timestamp) into the image and the
backend stamps it into each page's `?v=` query, so every deploy invalidates the
CSS/JS automatically — no hard-refresh needed. In plain `uvicorn` dev the build
id falls back to the process start time, so each restart re-stamps too.

## Deploy to the NAS

Same flow as calorieapp. Set the connection env vars and run:

```bash
NAS_HOST=192.168.1.100 NAS_USER=admin NAS_PATH=/volume1/docker/invitio \
  ./deploy.sh nas deploy
```

This builds the image locally, `docker save | ssh`-es it to the NAS, loads it,
and starts the containers. nginx listens on `127.0.0.1:18080`; point an Asustor
**Reverse Proxy** rule (HTTPS :443 → HTTP 127.0.0.1:18080) at it. See the header
of [docker-compose.nas.yml](docker-compose.nas.yml) for the one-time ADM setup.

> Running another app's nginx on the NAS already (e.g. calorieapp on 18080)?
> Give invitio its own port: `NAS_HTTP_PORT=18081 ./deploy.sh nas deploy` (or set
> `INVITIO_HTTP_PORT` in `.env`), then point invitio's reverse-proxy rule at
> `127.0.0.1:18081`. Each app keeps its own nginx + its own proxy rule.

### PostgreSQL: new or existing

`nas deploy` asks which database to use and deploys only the containers that mode
needs:

- **Create a new postgres container** (default) — deploys `app + nginx + postgres`
  via [docker-compose.nas.yml](docker-compose.nas.yml); the DB lives in the
  bind-mounted `./postgres-data`. Just set `POSTGRES_PASSWORD` in `.env`.
- **Reuse an existing postgres instance** — deploys only `app + nginx` via
  [docker-compose.nas-extdb.yml](docker-compose.nas-extdb.yml) and points
  `DATABASE_URL` at your existing database. You'll be prompted for host, port,
  database, user, and password. The instance must be reachable from the app
  container — by host/LAN address, or, if it's another Docker container, supply
  the **shared Docker network** when asked so the app can reach it by container
  name. Create the database + user first:

  ```sql
  CREATE USER invitio WITH PASSWORD '...';
  CREATE DATABASE invitio OWNER invitio;
  ```

Set the `NAS_DB_*` env vars to skip the prompt for unattended deploys:

```bash
NAS_HOST=192.168.1.100 NAS_DB_MODE=existing NAS_DB_HOST=pg \
  NAS_DB_PASSWORD=secret NAS_DB_NETWORK=db-net ./deploy.sh nas deploy
```

Run `./deploy.sh` with no args for the full list (`NAS_DB_MODE`, `NAS_DB_HOST`,
`NAS_DB_PORT`, `NAS_DB_NAME`, `NAS_DB_USER`, `NAS_DB_PASSWORD`, `NAS_DB_NETWORK`).

Before the first NAS deploy, set in `.env`:

```ini
JWT_SECRET_KEY=<python -c "import secrets;print(secrets.token_urlsafe(48))">
POSTGRES_PASSWORD=<strong-password>   # only for a NEW bundled postgres; ignored when reusing one
PUBLIC_BASE_URL=https://invite.mahensingh.ddns.info
ALLOWED_ORIGINS=["https://invite.mahensingh.ddns.info"]
GMAIL_ADDRESS=you@gmail.com          # optional
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx   # optional (App Password, not your login)
```

> Reusing an existing postgres? You don't need `POSTGRES_PASSWORD` — `deploy.sh`
> writes the full `DATABASE_URL` into the deployed `.env` from the details you
> give at the prompt (your local `.env` is left untouched).

`deploy.sh nas {deploy|up|down|logs|shell}` — run `./deploy.sh` with no args for
the full help.

## Data persistence

Bind-mounted on the NAS so data survives container/image churn and firmware
updates:

| Path             | Holds                          |
|------------------|--------------------------------|
| `./uploads`      | uploaded invite images         |
| `./postgres-data`| the PostgreSQL database (bundled postgres only) |

`./postgres-data` is only created/used when you deploy a **new** bundled postgres.
When reusing an existing instance, persistence is whatever that database already
has — invitio only bind-mounts `./uploads`.

Locally (`docker-compose.yml`), `./data` holds the SQLite file and `./uploads`
the images.

## API

Interactive docs at `/docs` when running. Summary:

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/auth/signup` · `/login` | — | get a token |
| GET  | `/api/auth/me` | ✓ | current user |
| POST/GET | `/api/events` | ✓ | create / list events |
| GET/PUT/DELETE | `/api/events/{id}` | ✓ | manage one event |
| POST | `/api/events/{id}/cancel` · `/reinstate` | ✓ | cancel (soft) / reopen an event |
| POST | `/api/events/{id}/duplicate` | ✓ | clone into a fresh draft |
| POST | `/api/events/{id}/image` | ✓ | upload hero image (sets cover) |
| POST/DELETE | `/api/events/{id}/images[/{img}]` | ✓ | add photos / delete one |
| POST/PUT | `/api/events/{id}/images/{img}/cover` · `/images/order` | ✓ | set cover / reorder |
| POST | `/api/events/{id}/invites` | ✓ | add guests + email links |
| GET  | `/api/events/{id}/invites` · `/rsvps` | ✓ | paginated lists (`limit`/`offset`) |
| GET  | `/api/events/{id}/summary` | ✓ | response counts |
| GET  | `/api/events/{id}/views` | ✓ | invite-open log (IP/device/time) |
| GET  | `/api/public/event/{token}` | — | event by share link |
| GET  | `/api/public/invite/{token}` | — | event by personal link (prefilled) |
| POST | `/api/public/rsvp/{token}` | — | submit / update an RSVP |
| POST | `/api/public/view/{token}` | — | view beacon (logs a real-browser open) |
| GET  | `/api/public/track/{token}.gif` | — | email open-tracking pixel (1×1 GIF) |
| POST | `/api/public/events` | — | quick-create an event (no account) |
| GET/PUT/DELETE | `/api/public/manage/{token}` | token | manage a no-account event |
| POST | `/api/public/manage/{token}/image` · `/invites` | token | image / invites |
| GET  | `/api/public/manage/{token}/views` | token | invite-open log (no-account event) |

Pages: `/` (host app), `/quick` (no-account create), `/m/{token}` (no-account
manage), `/e/{token}` (shared RSVP), `/i/{token}` (personal RSVP). The "Add to
Calendar" links (Google + `.ics`) are generated client-side on the RSVP page.

## Project layout

```
invitio/
├── deploy.sh                local + NAS deploy (prompts: new vs existing postgres)
├── docker-compose.yml       local dev (SQLite, :8080)
├── docker-compose.nas.yml   NAS, new bundled postgres (app + nginx + db, :18080)
├── docker-compose.nas-extdb.yml      NAS, reuse an existing postgres (app + nginx)
├── docker-compose.nas-extdb-net.yml  override: join the DB's shared Docker network
├── Dockerfile · docker-entrypoint.sh · nginx/
├── requirements.txt · requirements-dev.txt · .env.example
├── backend/app/             FastAPI: models, schemas, auth, email_service,
│                            event_service, image_service, rate_limit,
│                            routers/{auth,events,manage,rsvp,ai}
├── backend/tests/           pytest suite (auth, RSVP/manage, images, limits)
├── frontend/                index.html (host) · quick.html · manage.html ·
│                            rsvp.html (guest) · css · js
└── local_docs/PLAN.md       design + scope (git-ignored, local only)
```
