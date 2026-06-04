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
  administers the event without logging in.
- **Create events** — title, start/end date/time, location, description, host
  name, theme, and a **custom uploaded hero image**.
- **Invite by email** — each guest gets a unique tokenized RSVP link (emailed
  via Gmail when configured).
- **Share a link** — one public link anyone can open and RSVP through.
- **RSVP without login** — yes / maybe / no, party size (+1s), and a note.
  Re-submitting updates the existing response instead of duplicating it.
- **Add to Calendar** — guests get Google Calendar + `.ics` (Apple/Outlook)
  buttons on the invite and after RSVPing yes.
- **Dashboard** — response counts, head count, full guest + response list.

## Tech stack

FastAPI · async SQLAlchemy 2 · SQLite (dev) / PostgreSQL (prod) · bcrypt + JWT ·
Gmail SMTP · vanilla HTML/CSS/JS · Docker.

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

## Deploy to the NAS

Same flow as calorieapp. Set the connection env vars and run:

```bash
NAS_HOST=192.168.1.100 NAS_USER=admin NAS_PATH=/volume1/docker/invitio \
  ./deploy.sh nas deploy
```

This builds the image locally, `docker save | ssh`-es it to the NAS, loads it,
and starts `app + nginx + postgres` via `docker-compose.nas.yml`. nginx listens
on `127.0.0.1:18080`; point an Asustor **Reverse Proxy** rule (HTTPS :443 →
HTTP 127.0.0.1:18080) at it. See the header of
[docker-compose.nas.yml](docker-compose.nas.yml) for the one-time ADM setup.

Before the first NAS deploy, set in `.env`:

```ini
JWT_SECRET_KEY=<python -c "import secrets;print(secrets.token_urlsafe(48))">
POSTGRES_PASSWORD=<strong-password>
PUBLIC_BASE_URL=https://invite.mahensingh.ddns.info
ALLOWED_ORIGINS=["https://invite.mahensingh.ddns.info"]
GMAIL_ADDRESS=you@gmail.com          # optional
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx   # optional (App Password, not your login)
```

`deploy.sh nas {deploy|up|down|logs|shell}` — run `./deploy.sh` with no args for
the full help.

## Data persistence

Bind-mounted on the NAS so data survives container/image churn and firmware
updates:

| Path             | Holds                          |
|------------------|--------------------------------|
| `./uploads`      | uploaded invite images         |
| `./postgres-data`| the PostgreSQL database         |

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
| POST | `/api/events/{id}/image` | ✓ | upload hero image |
| POST | `/api/events/{id}/invites` | ✓ | add guests + email links |
| GET  | `/api/events/{id}/summary` | ✓ | response counts |
| GET  | `/api/public/event/{token}` | — | event by share link |
| GET  | `/api/public/invite/{token}` | — | event by personal link (prefilled) |
| POST | `/api/public/rsvp/{token}` | — | submit / update an RSVP |
| POST | `/api/public/events` | — | quick-create an event (no account) |
| GET/PUT/DELETE | `/api/public/manage/{token}` | token | manage a no-account event |
| POST | `/api/public/manage/{token}/image` · `/invites` | token | image / invites |

Pages: `/` (host app), `/quick` (no-account create), `/m/{token}` (no-account
manage), `/e/{token}` (shared RSVP), `/i/{token}` (personal RSVP). The "Add to
Calendar" links (Google + `.ics`) are generated client-side on the RSVP page.

## Project layout

```
invitio/
├── deploy.sh                local + NAS deploy
├── docker-compose.yml       local dev (SQLite, :8080)
├── docker-compose.nas.yml   NAS (postgres + nginx, :18080)
├── Dockerfile · docker-entrypoint.sh · nginx/
├── requirements.txt · .env.example
├── backend/app/             FastAPI: models, schemas, auth, email_service,
│                            event_service, routers/{auth,events,manage,rsvp}
├── frontend/                index.html (host) · quick.html · manage.html ·
│                            rsvp.html (guest) · css · js
└── local_docs/PLAN.md       design + scope (git-ignored, local only)
```
