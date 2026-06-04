"""Public, no-auth RSVP endpoints.

A token in the URL is either an Event.public_token (the shareable link) or an
Invite.token (a personalized link emailed to one guest). Both resolve to an
event; an invite token additionally prefills/links the guest's response.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Event, Invite, Rsvp
from app.schemas import PublicEventOut, RsvpOut, RsvpSubmit

router = APIRouter(prefix="/api/public", tags=["public"])


async def _event_by_public_token(token: str, db: AsyncSession) -> Event:
    event = (await db.execute(select(Event).where(Event.public_token == token))).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


async def _resolve_token(token: str, db: AsyncSession) -> tuple[Event, Invite | None]:
    """Resolve a URL token to (event, invite|None). Tries the invite token
    first, then the event's public token."""
    invite = (await db.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if invite:
        event = (await db.execute(select(Event).where(Event.id == invite.event_id))).scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return event, invite
    return await _event_by_public_token(token, db), None


def _public_event(event: Event, invite: Invite | None, existing: Rsvp | None) -> PublicEventOut:
    return PublicEventOut(
        title=event.title,
        description=event.description,
        location=event.location,
        event_date=event.event_date,
        event_end=event.event_end,
        host_display_name=event.host_display_name,
        image_path=event.image_path,
        theme=event.theme,
        allow_plus_ones=event.allow_plus_ones,
        public_token=event.public_token,
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
            await db.execute(select(Rsvp).where(Rsvp.invite_id == invite.id))
        ).scalar_one_or_none()
    return _public_event(event, invite, existing)


@router.post("/rsvp/{token}", response_model=RsvpOut)
async def submit_rsvp(token: str, body: RsvpSubmit, db: AsyncSession = Depends(get_db)):
    event, invite = await _resolve_token(token, db)

    party_size = body.party_size if (event.allow_plus_ones and body.status == "yes") else 1
    email = (str(body.guest_email).lower().strip() if body.guest_email else "")

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
    return RsvpOut.model_validate(rsvp)
