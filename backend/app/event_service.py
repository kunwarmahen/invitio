"""Shared event operations used by both the authenticated host router
(`routers/events.py`) and the token-based no-account manage router
(`routers/manage.py`). Keeps image handling, invite creation/emailing, and
summary math in one place."""
import datetime
import os
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import new_token
from app.config import settings
from app.email_service import email_configured, send_broadcast_email, send_invite_email
from app.models import Event, EventQuestion, Invite, Rsvp, RsvpAnswer
from app.schemas import (
    AddInvitesRequest,
    AnswerIn,
    BroadcastRequest,
    BroadcastResult,
    EventSummary,
    EventUpdate,
    InviteOut,
    QuestionIn,
)

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


# ── Custom RSVP questions ────────────────────────────────────────────────────
def _clean_options(item: QuestionIn) -> list[str]:
    if item.qtype == "text":
        return []
    return [o.strip() for o in item.options if o and o.strip()]


async def replace_questions(event: Event, items: list[QuestionIn], db: AsyncSession) -> list[EventQuestion]:
    """Apply the host's full question list by id-diff: update existing questions,
    insert new ones, and delete any whose id was dropped. Updating in place (rather
    than wipe-and-recreate) preserves answers already collected for kept questions.
    `position` follows the submitted order."""
    existing = {q.id: q for q in event.questions}
    seen: set[int] = set()
    for pos, item in enumerate(items):
        options = _clean_options(item)
        if item.id and item.id in existing:
            q = existing[item.id]
            q.prompt, q.qtype, q.options, q.required, q.position = (
                item.prompt.strip(), item.qtype, options, item.required, pos,
            )
            seen.add(item.id)
        else:
            db.add(EventQuestion(
                event_id=event.id, prompt=item.prompt.strip(), qtype=item.qtype,
                options=options, required=item.required, position=pos,
            ))
    removed = [qid for qid in existing if qid not in seen]
    if removed:
        # Drop answers first: the question.answers relationship isn't loaded here,
        # so the ORM delete-orphan cascade wouldn't fire under async.
        await db.execute(delete(RsvpAnswer).where(RsvpAnswer.question_id.in_(removed)))
        for qid in removed:
            await db.delete(existing[qid])
    await db.commit()
    return (
        await db.execute(
            select(EventQuestion)
            .where(EventQuestion.event_id == event.id)
            .order_by(EventQuestion.position)
        )
    ).scalars().all()


async def save_answers(
    rsvp: Rsvp, answers: list[AnswerIn], questions: list[EventQuestion], db: AsyncSession
) -> None:
    """Replace a guest's answers. Answers for questions not on the event are
    ignored; multi values are normalised to a list, others to a string."""
    qtype_by_id = {q.id: q.qtype for q in questions}
    await db.execute(delete(RsvpAnswer).where(RsvpAnswer.rsvp_id == rsvp.id))
    for ans in answers:
        qtype = qtype_by_id.get(ans.question_id)
        if qtype is None:
            continue
        if qtype == "multi":
            value = ans.value if isinstance(ans.value, list) else [ans.value]
            value = [str(v).strip() for v in value if str(v).strip()]
        else:
            value = ans.value[0] if isinstance(ans.value, list) else ans.value
            value = str(value or "").strip()
        db.add(RsvpAnswer(rsvp_id=rsvp.id, question_id=ans.question_id, value=value))
    await db.commit()


# ── Broadcast ("message all guests") ─────────────────────────────────────────
def collect_broadcast_recipients(event: Event, audience: str) -> list[tuple[str, str]]:
    """Deduped (email, name) list for the chosen audience. Mirrors the responder
    bookkeeping used by the reminder loop for the 'pending' (non-responder) case."""
    recipients: dict[str, str] = {}

    def add(email: str, name: str) -> None:
        if not email:
            return
        key = email.lower()
        if key not in recipients or (not recipients[key] and name):
            recipients[key] = name or ""

    if audience in ("yes", "maybe", "no"):
        for r in event.rsvps:
            if r.status == audience:
                add(r.guest_email, r.guest_name)
    elif audience == "pending":
        responded_invite_ids = {r.invite_id for r in event.rsvps if r.invite_id}
        responded_emails = {r.guest_email.lower() for r in event.rsvps if r.guest_email}
        for inv in event.invites:
            if inv.guest_email and inv.id not in responded_invite_ids \
                    and inv.guest_email.lower() not in responded_emails:
                add(inv.guest_email, inv.guest_name)
    else:  # all
        for inv in event.invites:
            add(inv.guest_email, inv.guest_name)
        for r in event.rsvps:
            add(r.guest_email, r.guest_name)

    return list(recipients.items())


async def send_broadcast(event: Event, body: BroadcastRequest) -> BroadcastResult:
    """Email the host's message to the chosen audience, best-effort per recipient."""
    recipients = collect_broadcast_recipients(event, body.audience)
    if not email_configured():
        return BroadcastResult(sent=0, recipients=len(recipients), email_enabled=False)

    event_url = f"{settings.public_base_url}/e/{event.public_token}"
    sent = 0
    for email, name in recipients:
        try:
            if await send_broadcast_email(
                to_email=email,
                guest_name=name,
                event_title=event.title,
                host_name=event.host_display_name,
                subject=body.subject,
                message=body.message,
                event_url=event_url,
            ):
                sent += 1
        except Exception as exc:
            if settings.debug:
                print(f"[BROADCAST] to {email} failed: {exc}")
    return BroadcastResult(sent=sent, recipients=len(recipients), email_enabled=True)
