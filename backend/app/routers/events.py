from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app import event_service
from app.auth import get_current_user, new_token
from app.config import settings
from app.database import get_db
from app.email_service import email_configured
from app.models import Event, EventCohost, Rsvp, User
from app.schemas import (
    AddCohostRequest,
    AddInvitesRequest,
    AddInvitesResult,
    AiImageRequest,
    BroadcastRequest,
    BroadcastResult,
    CohostOut,
    EventCreate,
    EventDetail,
    EventOut,
    EventSummary,
    EventUpdate,
    InviteOut,
    InvitePage,
    QuestionOut,
    QuestionsUpdate,
    ReorderImagesRequest,
    RsvpOut,
    RsvpPage,
)

router = APIRouter(prefix="/api/events", tags=["events"])


def _is_owner(event: Event, user: User) -> bool:
    return event.host_id == user.id


def _can_manage(event: Event, user: User) -> bool:
    return _is_owner(event, user) or any(c.user_id == user.id for c in event.cohosts)


async def _load_event(event_id: int, user: User, db: AsyncSession, *, owner_only: bool = False) -> Event:
    """Load an event the user may manage. Owners and co-hosts both pass; a few
    actions (delete, co-host management) require ownership via owner_only=True."""
    event = (
        await db.execute(
            select(Event)
            .where(Event.id == event_id)
            .options(
                selectinload(Event.invites),
                selectinload(Event.rsvps).selectinload(Rsvp.answers),
                selectinload(Event.questions),
                selectinload(Event.wall_posts),
                selectinload(Event.cohosts).selectinload(EventCohost.user),
                selectinload(Event.images),
            )
        )
    ).scalar_one_or_none()
    if not event or not _can_manage(event, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if owner_only and not _is_owner(event, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the event owner can do that")
    return event


def _detail(event: Event, user: User) -> EventDetail:
    detail = EventDetail.model_validate(event)  # cohosts auto-map via EventCohost.email/name
    detail.is_owner = _is_owner(event, user)
    event_service.cap_detail(detail, event)  # embed only the first page of invites/rsvps
    return detail


async def _load_event_slim(event_id: int, user: User, db: AsyncSession) -> Event:
    """Lightweight load for the paginated list endpoints: just enough to check the
    user may manage the event, without eager-loading every invite/RSVP."""
    event = (
        await db.execute(
            select(Event).where(Event.id == event_id).options(selectinload(Event.cohosts))
        )
    ).scalar_one_or_none()
    if not event or not _can_manage(event, user):
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
        rsvp_deadline=body.rsvp_deadline,
        timezone=body.timezone,
        host_display_name=(body.host_display_name or user.name).strip(),
        host_email=user.email,
        theme=body.theme,
        image_fit=body.image_fit,
        allow_plus_ones=body.allow_plus_ones,
        public_token=new_token(),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return EventOut.model_validate(event)


@router.get("", response_model=list[EventOut])
async def list_events(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Events the user owns, plus events shared with them as a co-host.
    cohosted = select(EventCohost.event_id).where(EventCohost.user_id == user.id)
    rows = (
        await db.execute(
            select(Event)
            .where(or_(Event.host_id == user.id, Event.id.in_(cohosted)))
            .order_by(Event.created_at.desc())
        )
    ).scalars().all()
    out = []
    for e in rows:
        item = EventOut.model_validate(e)
        item.is_owner = _is_owner(e, user)
        out.append(item)
    return out


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(event_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _detail(await _load_event(event_id, user, db), user)


@router.get("/{event_id}/invites", response_model=InvitePage)
async def list_invites(
    event_id: int,
    limit: int = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await _load_event_slim(event_id, user, db)
    limit = limit or settings.list_page_size
    items, total = await event_service.fetch_invite_page(event.id, db, limit, offset)
    return InvitePage(items=[InviteOut.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/{event_id}/rsvps", response_model=RsvpPage)
async def list_rsvps(
    event_id: int,
    limit: int = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await _load_event_slim(event_id, user, db)
    limit = limit or settings.list_page_size
    items, total = await event_service.fetch_rsvp_page(event.id, db, limit, offset)
    return RsvpPage(items=[RsvpOut.model_validate(r) for r in items], total=total, limit=limit, offset=offset)


@router.put("/{event_id}", response_model=EventOut)
async def update_event(event_id: int, body: EventUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    event_service.apply_update(event, body)
    await db.commit()
    await db.refresh(event)
    return EventOut.model_validate(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await event_service.delete_event(await _load_event(event_id, user, db, owner_only=True), db)


@router.post("/{event_id}/image", response_model=EventOut)
async def upload_image(event_id: int, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    await event_service.save_image(event, file, db)
    return EventOut.model_validate(event)


@router.post("/{event_id}/images", response_model=EventDetail)
async def add_images(event_id: int, files: list[UploadFile] = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    await event_service.add_images(event, files, db)
    return _detail(event, user)


@router.post("/{event_id}/images/{image_id}/cover", response_model=EventOut)
async def set_cover_image(event_id: int, image_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    await event_service.set_cover(event, image_id, db)
    return EventOut.model_validate(event)


@router.put("/{event_id}/images/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_images(event_id: int, body: ReorderImagesRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    await event_service.reorder_images(event, body.ids, db)


@router.delete("/{event_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(event_id: int, image_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    await event_service.delete_image(event, image_id, db)


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


@router.put("/{event_id}/questions", response_model=list[QuestionOut])
async def set_questions(event_id: int, body: QuestionsUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    questions = await event_service.replace_questions(event, body.questions, db)
    return [QuestionOut.model_validate(q) for q in questions]


@router.post("/{event_id}/broadcast", response_model=BroadcastResult)
async def broadcast(event_id: int, body: BroadcastRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await event_service.send_broadcast(await _load_event(event_id, user, db), body)


@router.post("/{event_id}/ai/image", response_model=EventOut)
async def ai_image(event_id: int, body: AiImageRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db)
    await event_service.generate_event_image(event, body.prompt, db)
    return EventOut.model_validate(event)


@router.delete("/{event_id}/wall/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wall_post(event_id: int, post_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await event_service.delete_wall_post(await _load_event(event_id, user, db), post_id, db)


@router.post("/{event_id}/cohosts", response_model=CohostOut, status_code=status.HTTP_201_CREATED)
async def add_cohost(event_id: int, body: AddCohostRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db, owner_only=True)
    return await event_service.add_cohost(event, str(body.email), db)


@router.delete("/{event_id}/cohosts/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_cohost(event_id: int, user_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    event = await _load_event(event_id, user, db, owner_only=True)
    await event_service.remove_cohost(event, user_id, db)
