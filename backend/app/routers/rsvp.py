"""Public, no-auth RSVP endpoints.

A token in the URL is either an Event.public_token (the shareable link) or an
Invite.token (a personalized link emailed to one guest). Both resolve to an
event; an invite token additionally prefills/links the guest's response.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app import event_service
from app.config import settings
from app.database import get_db
from app.email_service import email_configured, send_host_rsvp_notification
from app.models import Event, Invite, Rsvp
from app.schemas import PublicEventOut, QuestionOut, RsvpOut, RsvpSubmit

router = APIRouter(prefix="/api/public", tags=["public"])


_WITH_QUESTIONS = (selectinload(Event.questions),)


async def _event_by_public_token(token: str, db: AsyncSession) -> Event:
    event = (
        await db.execute(
            select(Event).where(Event.public_token == token).options(*_WITH_QUESTIONS)
        )
    ).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


async def _resolve_token(token: str, db: AsyncSession) -> tuple[Event, Invite | None]:
    """Resolve a URL token to (event, invite|None). Tries the invite token
    first, then the event's public token."""
    invite = (await db.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if invite:
        event = (
            await db.execute(
                select(Event).where(Event.id == invite.event_id).options(*_WITH_QUESTIONS)
            )
        ).scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return event, invite
    return await _event_by_public_token(token, db), None


def _has_value(value) -> bool:
    """An answer counts as provided if it's a non-empty string or a list with at
    least one non-empty entry."""
    if isinstance(value, list):
        return any(str(v).strip() for v in value)
    return bool(str(value or "").strip())


def _public_event(event: Event, invite: Invite | None, existing: Rsvp | None) -> PublicEventOut:
    return PublicEventOut(
        title=event.title,
        description=event.description,
        location=event.location,
        event_date=event.event_date,
        event_end=event.event_end,
        timezone=event.timezone,
        host_display_name=event.host_display_name,
        image_path=event.image_path,
        image_fit=event.image_fit,
        theme=event.theme,
        allow_plus_ones=event.allow_plus_ones,
        public_token=event.public_token,
        questions=[QuestionOut.model_validate(q) for q in event.questions],
        guest_name=invite.guest_name if invite else "",
        guest_email=invite.guest_email if invite else "",
        existing_rsvp=RsvpOut.model_validate(existing) if existing else None,
    )


@router.get("/event/{token}", response_model=PublicEventOut)
async def public_event(token: str, db: AsyncSession = Depends(get_db)):
    event = await _event_by_public_token(token, db)
    return _public_event(event, None, None)


@router.get("/invite/{token}", response_model=PublicEventOut)
async def public_invite(token: str, db: AsyncSession = Depends(get_db)):
    event, invite = await _resolve_token(token, db)
    existing = None
    if invite:
        existing = (
            await db.execute(
                select(Rsvp).where(Rsvp.invite_id == invite.id).options(selectinload(Rsvp.answers))
            )
        ).scalar_one_or_none()
    return _public_event(event, invite, existing)


@router.post("/rsvp/{token}", response_model=RsvpOut)
async def submit_rsvp(
    token: str,
    body: RsvpSubmit,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    event, invite = await _resolve_token(token, db)

    party_size = body.party_size if (event.allow_plus_ones and body.status == "yes") else 1
    email = (str(body.guest_email).lower().strip() if body.guest_email else "")

    # Required questions are only enforced for attendees — a "no" never needs them.
    if body.status != "no":
        answered = {a.question_id for a in body.answers if _has_value(a.value)}
        for q in event.questions:
            if q.required and q.id not in answered:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Please answer: {q.prompt}",
                )

    # Find an existing RSVP to update so re-submitting edits rather than dupes:
    # by invite (personalized link) or by email for this event (shared link).
    existing: Rsvp | None = None
    if invite:
        existing = (
            await db.execute(select(Rsvp).where(Rsvp.invite_id == invite.id))
        ).scalar_one_or_none()
    elif email:
        existing = (
            await db.execute(
                select(Rsvp).where(Rsvp.event_id == event.id, Rsvp.guest_email == email)
            )
        ).scalar_one_or_none()

    if existing:
        existing.guest_name = body.guest_name.strip()
        if email:
            existing.guest_email = email
        existing.status = body.status
        existing.party_size = party_size
        existing.message = body.message
        rsvp = existing
    else:
        rsvp = Rsvp(
            event_id=event.id,
            invite_id=invite.id if invite else None,
            guest_name=body.guest_name.strip(),
            guest_email=email or (invite.guest_email if invite else ""),
            status=body.status,
            party_size=party_size,
            message=body.message,
        )
        db.add(rsvp)

    await db.commit()
    await db.refresh(rsvp)

    # Persist custom-question answers, then reload them onto the rsvp for the response.
    await event_service.save_answers(rsvp, body.answers, event.questions, db)
    await db.refresh(rsvp, attribute_names=["answers"])

    # Best-effort host notification, sent after the response is returned so the
    # guest never waits on SMTP. Skipped silently when email isn't configured or
    # the event has no host email (some quick-create events).
    if event.host_email and email_configured():
        manage_url = f"{settings.public_base_url}/m/{event.manage_token}" if event.manage_token else None
        background.add_task(
            _notify_host,
            to_email=event.host_email,
            host_name=event.host_display_name,
            event_title=event.title,
            guest_name=rsvp.guest_name,
            status=rsvp.status,
            party_size=rsvp.party_size,
            message=rsvp.message or "",
            manage_url=manage_url,
            updated=bool(existing),
        )

    return RsvpOut.model_validate(rsvp)


async def _notify_host(**kwargs) -> None:
    try:
        await send_host_rsvp_notification(**kwargs)
    except Exception as exc:
        if settings.debug:
            print(f"[EMAIL] host RSVP notification failed: {exc}")
