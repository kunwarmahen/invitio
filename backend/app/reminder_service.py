"""Pre-event reminder emails, via a background loop started in the app lifespan.

On each tick the loop finds events that start within `reminder_window_hours` and
haven't been reminded yet, then emails every "yes" guest a reminder and nudges
anyone who was invited but hasn't responded. Each event is marked
`reminder_sent_at` so it's only reminded once.

The loop is best-effort: it only runs when Gmail is configured and
`reminders_enabled` is set, and any per-send failure is swallowed so one bad
address can't stall the batch.
"""
import asyncio
import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.email_service import email_configured, send_guest_reminder
from app.models import Event


def _naive_utcnow() -> datetime.datetime:
    # event_date is stored naive (see the timezone-correctness backlog item), so
    # compare against a naive UTC now to avoid aware/naive mismatch errors.
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _as_naive(dt: datetime.datetime) -> datetime.datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _image_url(event: Event) -> str | None:
    return (settings.public_base_url + event.image_path) if event.image_path else None


def _rsvp_url_for_invite_token(token: str | None, event: Event) -> str:
    """A personal invite link when we have the guest's token, else the event's
    public share link."""
    if token:
        return f"{settings.public_base_url}/i/{token}"
    return f"{settings.public_base_url}/e/{event.public_token}"


async def _remind_event(event: Event) -> int:
    """Email reminders + nudges for one event. Returns the number sent."""
    when = _as_naive(event.event_date) if event.event_date else None
    image_url = _image_url(event)
    invite_token_by_id = {inv.id: inv.token for inv in event.invites}

    # Who has already responded — by invite (personal link) and by email (shared
    # link), so we don't nudge someone who replied without their invite token.
    responded_invite_ids = {r.invite_id for r in event.rsvps if r.invite_id}
    responded_emails = {r.guest_email.lower() for r in event.rsvps if r.guest_email}

    sent = 0

    # "See you soon" to everyone who said yes (and gave an email).
    for rsvp in event.rsvps:
        if rsvp.status != "yes" or not rsvp.guest_email:
            continue
        url = _rsvp_url_for_invite_token(invite_token_by_id.get(rsvp.invite_id), event)
        try:
            if await send_guest_reminder(
                to_email=rsvp.guest_email,
                guest_name=rsvp.guest_name,
                event_title=event.title,
                host_name=event.host_display_name,
                when=when,
                location=event.location,
                rsvp_url=url,
                image_url=image_url,
                nudge=False,
            ):
                sent += 1
        except Exception as exc:
            if settings.debug:
                print(f"[REMINDER] reminder to {rsvp.guest_email} failed: {exc}")

    # Nudge invited guests who never responded.
    for inv in event.invites:
        if not inv.guest_email or inv.id in responded_invite_ids or inv.guest_email.lower() in responded_emails:
            continue
        try:
            if await send_guest_reminder(
                to_email=inv.guest_email,
                guest_name=inv.guest_name,
                event_title=event.title,
                host_name=event.host_display_name,
                when=when,
                location=event.location,
                rsvp_url=f"{settings.public_base_url}/i/{inv.token}",
                image_url=image_url,
                nudge=True,
            ):
                sent += 1
        except Exception as exc:
            if settings.debug:
                print(f"[REMINDER] nudge to {inv.guest_email} failed: {exc}")

    return sent


async def run_reminders_once() -> int:
    """One sweep: remind every due event. Returns the number of events reminded."""
    now = _naive_utcnow()
    window_end = now + datetime.timedelta(hours=settings.reminder_window_hours)

    async with AsyncSessionLocal() as db:
        events = (
            await db.execute(
                select(Event)
                .where(
                    Event.reminder_sent_at.is_(None),
                    Event.event_date.is_not(None),
                    Event.event_date >= now,
                    Event.event_date <= window_end,
                )
                .options(selectinload(Event.invites), selectinload(Event.rsvps))
            )
        ).scalars().all()

        reminded = 0
        for event in events:
            sent = await _remind_event(event)
            # Mark reminded regardless of count so we don't re-scan it every tick;
            # an event with no emailable guests is still "handled".
            event.reminder_sent_at = datetime.datetime.now(datetime.timezone.utc)
            reminded += 1
            if settings.debug:
                print(f"[REMINDER] event {event.id} '{event.title}': {sent} email(s) sent")
        await db.commit()
        return reminded


async def reminder_loop() -> None:
    interval = max(1, settings.reminder_check_interval_minutes) * 60
    print(f"[REMINDER] loop started (window {settings.reminder_window_hours}h, every {interval}s)")
    while True:
        try:
            await run_reminders_once()
        except Exception as exc:
            print(f"[REMINDER] sweep failed: {exc}")
        await asyncio.sleep(interval)


def should_run() -> bool:
    return settings.reminders_enabled and email_configured()
