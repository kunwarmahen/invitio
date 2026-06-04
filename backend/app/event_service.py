"""Shared event operations used by both the authenticated host router
(`routers/events.py`) and the token-based no-account manage router
(`routers/manage.py`). Keeps image handling, invite creation/emailing, and
summary math in one place."""
import datetime
import os
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import new_token
from app.config import settings
from app.email_service import email_configured, send_invite_email
from app.models import Event, Invite
from app.schemas import AddInvitesRequest, EventSummary, EventUpdate, InviteOut

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def apply_update(event: Event, body: EventUpdate) -> None:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(event, field, value)


def _remove_image_file(image_path: str | None) -> None:
    if not image_path:
        return
    try:
        os.remove(os.path.join(settings.upload_dir, os.path.basename(image_path)))
    except OSError:
        pass


async def save_image(event: Event, file: UploadFile, db: AsyncSession) -> None:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type (use JPEG, PNG, WebP, or GIF)")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Image too large (max {settings.max_upload_mb} MB)")

    os.makedirs(settings.upload_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{_EXT.get(file.content_type, '.img')}"
    with open(os.path.join(settings.upload_dir, fname), "wb") as fh:
        fh.write(data)

    _remove_image_file(event.image_path)  # drop the previous one
    event.image_path = f"/uploads/{fname}"
    await db.commit()
    await db.refresh(event)


async def delete_event(event: Event, db: AsyncSession) -> None:
    _remove_image_file(event.image_path)
    await db.delete(event)
    await db.commit()


async def add_invites(event: Event, body: AddInvitesRequest, db: AsyncSession) -> tuple[list[Invite], int]:
    """Create invites for new guest emails and (best-effort) email each a link.
    Returns (added_invites, emailed_count)."""
    wanted: dict[str, str] = {}
    for e in body.emails:
        wanted[str(e).lower().strip()] = ""
    for g in body.guests:
        wanted[str(g.email).lower().strip()] = g.name.strip()

    existing_emails = {inv.guest_email for inv in event.invites}
    added: list[Invite] = []
    for email, name in wanted.items():
        if email in existing_emails:
            continue
        inv = Invite(event_id=event.id, guest_email=email, guest_name=name, token=new_token())
        db.add(inv)
        added.append(inv)

    await db.commit()
    for inv in added:
        await db.refresh(inv)

    emailed = 0
    if body.send_email and email_configured():
        image_url = (settings.public_base_url + event.image_path) if event.image_path else None
        for inv in added:
            rsvp_url = f"{settings.public_base_url}/i/{inv.token}"
            try:
                sent = await send_invite_email(
                    to_email=inv.guest_email,
                    guest_name=inv.guest_name,
                    event_title=event.title,
                    host_name=event.host_display_name,
                    when=event.event_date,
                    location=event.location,
                    rsvp_url=rsvp_url,
                    image_url=image_url,
                )
                if sent:
                    inv.sent_at = datetime.datetime.now(datetime.timezone.utc)
                    emailed += 1
            except Exception as exc:
                if settings.debug:
                    print(f"[EMAIL] failed to {inv.guest_email}: {exc}")
        await db.commit()
        for inv in added:
            await db.refresh(inv)

    return added, emailed


def summarize(event: Event) -> EventSummary:
    s = EventSummary(invited=len(event.invites))
    for r in event.rsvps:
        if r.status == "yes":
            s.yes += 1
            s.head_count += max(r.party_size, 1)
        elif r.status == "no":
            s.no += 1
        elif r.status == "maybe":
            s.maybe += 1
    s.responded = s.yes + s.no + s.maybe
    return s
