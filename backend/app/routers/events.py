from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app import event_service
from app.auth import get_current_user, new_token
from app.database import get_db
from app.email_service import email_configured
from app.models import Event, User
from app.schemas import (
    AddInvitesRequest,
    AddInvitesResult,
    EventCreate,
    EventDetail,
    EventOut,
    EventSummary,
    EventUpdate,
    InviteOut,
)

router = APIRouter(prefix="/api/events", tags=["events"])


async def _load_event(event_id: int, user: User, db: AsyncSession) -> Event:
    event = (
        await db.execute(
            select(Event)
            .where(Event.id == event_id)
            .options(selectinload(Event.invites), selectinload(Event.rsvps))
        )
    ).scalar_one_or_none()
    if not event or event.host_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(body: EventCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = Event(
        host_id=user.id,
        title=body.title.strip(),
        description=body.description,
        location=body.location,
        event_date=body.event_date,
        event_end=body.event_end,
        host_display_name=(body.host_display_name or user.name).strip(),
        host_email=user.email,
        theme=body.theme,
        allow_plus_ones=body.allow_plus_ones,
        public_token=new_token(),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return EventOut.model_validate(event)


@router.get("", response_model=list[EventOut])
async def list_events(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Event).where(Event.host_id == user.id).order_by(Event.created_at.desc())
        )
    ).scalars().all()
    return [EventOut.model_validate(e) for e in rows]


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(event_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return EventDetail.model_validate(await _load_event(event_id, user, db))


@router.put("/{event_id}", response_model=EventOut)
async def update_event(event_id: int, body: EventUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    event_service.apply_update(event, body)
    await db.commit()
    await db.refresh(event)
    return EventOut.model_validate(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await event_service.delete_event(await _load_event(event_id, user, db), db)


@router.post("/{event_id}/image", response_model=EventOut)
async def upload_image(event_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    await event_service.save_image(event, file, db)
    return EventOut.model_validate(event)


@router.post("/{event_id}/invites", response_model=AddInvitesResult)
async def add_invites(event_id: int, body: AddInvitesRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    added, emailed = await event_service.add_invites(event, body, db)
    return AddInvitesResult(
        added=[InviteOut.model_validate(i) for i in added],
        emailed=emailed,
        email_enabled=email_configured(),
    )


@router.get("/{event_id}/summary", response_model=EventSummary)
async def event_summary(event_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return event_service.summarize(await _load_event(event_id, user, db))
