"""No-account event flow.

`POST /api/public/events` creates an event without a login and returns a secret
``manage_token``. Everything under `/api/public/manage/{token}` then administers
that event by presenting the token instead of a JWT — the same operations the
authenticated host router offers.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai_service, event_service, rate_limit
from app.auth import new_token
from app.config import settings
from app.database import get_db
from app.email_service import email_configured, send_manage_link_email
from app.models import Event, EventCohost, Rsvp
from app.schemas import (
    AddInvitesRequest,
    AddInvitesResult,
    AiImageRequest,
    AiTextRequest,
    AiTextResult,
    BroadcastRequest,
    BroadcastResult,
    EventDetail,
    EventOut,
    EventSummary,
    EventUpdate,
    InviteOut,
    InvitePage,
    QuestionOut,
    QuestionsUpdate,
    QuickCreate,
    QuickCreateResult,
    ReorderImagesRequest,
    RsvpOut,
    RsvpPage,
)

router = APIRouter(prefix="/api/public", tags=["public"])


async def _load_managed(token: str, db: AsyncSession) -> Event:
    event = (
        await db.execute(
            select(Event)
            .where(Event.manage_token == token)
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
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found or link expired")
    return event


async def _load_managed_slim(token: str, db: AsyncSession) -> Event:
    """Lightweight token lookup for the paginated list endpoints (no eager-loading
    of every invite/RSVP). The token itself is the authorization."""
    event = (
        await db.execute(select(Event).where(Event.manage_token == token))
    ).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found or link expired")
    return event


@router.post("/events", response_model=QuickCreateResult, status_code=status.HTTP_201_CREATED)
async def quick_create(body: QuickCreate, request: Request, db: AsyncSession = Depends(get_db)):
    rate_limit.check(request, "create", settings.rate_limit_create_per_hour)
    host_email = str(body.host_email).lower().strip() if body.host_email else None
    event = Event(
        host_id=None,
        title=body.title.strip(),
        description=body.description,
        location=body.location,
        event_date=body.event_date,
        event_end=body.event_end,
        timezone=body.timezone,
        host_display_name=body.host_display_name.strip(),
        host_email=host_email,
        theme=body.theme,
        image_fit=body.image_fit,
        allow_plus_ones=body.allow_plus_ones,
        public_token=new_token(),
        manage_token=new_token(24),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    manage_url = f"{settings.public_base_url}/m/{event.manage_token}"
    share_url = f"{settings.public_base_url}/e/{event.public_token}"

    emailed = False
    if host_email and email_configured():
        try:
            emailed = await send_manage_link_email(host_email, event.title, manage_url, share_url)
        except Exception as exc:
            if settings.debug:
                print(f"[EMAIL] manage link to {host_email} failed: {exc}")

    return QuickCreateResult(
        event=EventOut.model_validate(event),
        manage_token=event.manage_token,
        manage_url=manage_url,
        share_url=share_url,
        emailed=emailed,
    )


@router.get("/manage/{token}", response_model=EventDetail)
async def manage_get(token: str, db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    detail = EventDetail.model_validate(event)
    event_service.cap_detail(detail, event)  # embed only the first page of invites/rsvps
    return detail


@router.get("/manage/{token}/invites", response_model=InvitePage)
async def manage_list_invites(
    token: str,
    limit: int = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    event = await _load_managed_slim(token, db)
    limit = limit or settings.list_page_size
    items, total = await event_service.fetch_invite_page(event.id, db, limit, offset)
    return InvitePage(items=[InviteOut.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/manage/{token}/rsvps", response_model=RsvpPage)
async def manage_list_rsvps(
    token: str,
    limit: int = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    event = await _load_managed_slim(token, db)
    limit = limit or settings.list_page_size
    items, total = await event_service.fetch_rsvp_page(event.id, db, limit, offset)
    return RsvpPage(items=[RsvpOut.model_validate(r) for r in items], total=total, limit=limit, offset=offset)


@router.put("/manage/{token}", response_model=EventOut)
async def manage_update(token: str, body: EventUpdate, db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    event_service.apply_update(event, body)
    await db.commit()
    await db.refresh(event)
    return EventOut.model_validate(event)


@router.delete("/manage/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def manage_delete(token: str, db: AsyncSession = Depends(get_db)):
    await event_service.delete_event(await _load_managed(token, db), db)


@router.post("/manage/{token}/image", response_model=EventOut)
async def manage_image(token: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    await event_service.save_image(event, file, db)
    return EventOut.model_validate(event)


@router.post("/manage/{token}/images", response_model=EventDetail)
async def manage_add_images(token: str, files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    await event_service.add_images(event, files, db)
    return EventDetail.model_validate(event)


@router.post("/manage/{token}/images/{image_id}/cover", response_model=EventOut)
async def manage_set_cover(token: str, image_id: int, db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    await event_service.set_cover(event, image_id, db)
    return EventOut.model_validate(event)


@router.put("/manage/{token}/images/order", status_code=status.HTTP_204_NO_CONTENT)
async def manage_reorder_images(token: str, body: ReorderImagesRequest, db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    await event_service.reorder_images(event, body.ids, db)


@router.delete("/manage/{token}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def manage_delete_image(token: str, image_id: int, db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    await event_service.delete_image(event, image_id, db)


@router.post("/manage/{token}/invites", response_model=AddInvitesResult)
async def manage_invites(token: str, body: AddInvitesRequest, db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    added, emailed = await event_service.add_invites(event, body, db)
    return AddInvitesResult(
        added=[InviteOut.model_validate(i) for i in added],
        emailed=emailed,
        email_enabled=email_configured(),
    )


@router.get("/manage/{token}/summary", response_model=EventSummary)
async def manage_summary(token: str, db: AsyncSession = Depends(get_db)):
    return event_service.summarize(await _load_managed(token, db))


@router.put("/manage/{token}/questions", response_model=list[QuestionOut])
async def manage_questions(token: str, body: QuestionsUpdate, db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    questions = await event_service.replace_questions(event, body.questions, db)
    return [QuestionOut.model_validate(q) for q in questions]


@router.post("/manage/{token}/broadcast", response_model=BroadcastResult)
async def manage_broadcast(token: str, body: BroadcastRequest, db: AsyncSession = Depends(get_db)):
    return await event_service.send_broadcast(await _load_managed(token, db), body)


@router.post("/manage/{token}/ai/text", response_model=AiTextResult)
async def manage_ai_text(token: str, body: AiTextRequest, db: AsyncSession = Depends(get_db)):
    await _load_managed(token, db)  # token must be valid (not an open LLM proxy)
    return AiTextResult(text=await ai_service.text_from_request(body))


@router.post("/manage/{token}/ai/image", response_model=EventOut)
async def manage_ai_image(token: str, body: AiImageRequest, db: AsyncSession = Depends(get_db)):
    event = await _load_managed(token, db)
    await event_service.generate_event_image(event, body.prompt, db)
    return EventOut.model_validate(event)


@router.delete("/manage/{token}/wall/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def manage_delete_wall_post(token: str, post_id: int, db: AsyncSession = Depends(get_db)):
    await event_service.delete_wall_post(await _load_managed(token, db), post_id, db)
