"""Shared event operations used by both the authenticated host router
(`routers/events.py`) and the token-based no-account manage router
(`routers/manage.py`). Keeps image handling, invite creation/emailing, and
summary math in one place."""
import datetime
import os
import shutil
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app import image_service
from app.auth import new_token
from app.config import settings
from app.email_service import email_configured, send_broadcast_email, send_invite_email
from app.models import (
    Broadcast,
    Event,
    EventCohost,
    EventImage,
    EventQuestion,
    Invite,
    InviteView,
    Rsvp,
    RsvpAnswer,
    User,
    WallPost,
)
from app.schemas import (
    AddInvitesRequest,
    AnswerIn,
    BroadcastOut,
    BroadcastRequest,
    BroadcastResult,
    CancelResult,
    CohostOut,
    ComingOut,
    EventSummary,
    EventUpdate,
    InviteOut,
    InviteViewOut,
    QuestionIn,
    RsvpOut,
    ViewLog,
)


def _naive_utcnow() -> datetime.datetime:
    # All DateTime columns are naive-UTC (see models._utcnow); strip tzinfo so
    # asyncpg accepts the value.
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


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


def _remove_image(img: EventImage) -> None:
    """Delete both the full image and its thumbnail from disk."""
    _remove_image_file(img.path)
    _remove_image_file(img.thumb_path)


def _write_file(data: bytes, ext: str) -> str:
    """Write already-processed bytes to the uploads dir, return the public path."""
    os.makedirs(settings.upload_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(settings.upload_dir, fname), "wb") as fh:
        fh.write(data)
    return f"/uploads/{fname}"


def _process_and_store(data: bytes) -> tuple[str, str]:
    """Validate (magic bytes), downsize/compress, and thumbnail an upload, writing
    both files. Returns (full_path, thumb_path). Raises HTTP 400 on bad input."""
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Image too large (max {settings.max_upload_mb} MB)")
    full_bytes, full_ext, thumb_bytes, thumb_ext = image_service.process(data)
    return _write_file(full_bytes, full_ext), _write_file(thumb_bytes, thumb_ext)


def _cover_image(event: Event) -> EventImage | None:
    """The event's cover image: the one flagged `is_cover`, else the first by
    position, else None."""
    if not event.images:
        return None
    for img in event.images:
        if img.is_cover:
            return img
    return min(event.images, key=lambda i: i.position)


def _sync_cover(event: Event) -> None:
    """Mirror the cover image's path + thumbnail into `event.image_path` /
    `event.image_thumb_path` (the denormalized fields read-paths use). Clears them
    when no images remain. Caller commits."""
    cover = _cover_image(event)
    event.image_path = cover.path if cover else None
    event.image_thumb_path = cover.thumb_path if cover else None


async def _add_image(event: Event, data: bytes, db: AsyncSession, *, make_cover: bool) -> EventImage:
    """Process raw upload bytes into a new gallery image (validated, downsized,
    thumbnailed) appended after the current last one. Becomes the cover when
    asked, or automatically if the event had none."""
    path, thumb_path = _process_and_store(data)
    next_pos = max((i.position for i in event.images), default=-1) + 1
    img = EventImage(event_id=event.id, path=path, thumb_path=thumb_path, position=next_pos)
    db.add(img)
    event.images.append(img)
    if make_cover or len(event.images) == 1:
        for other in event.images:
            other.is_cover = other is img
        if make_cover:
            event.image_focal_x = event.image_focal_y = 50.0
    _sync_cover(event)
    await db.commit()
    return img


async def save_image(event: Event, file: UploadFile, db: AsyncSession) -> None:
    """Upload a single image and make it the cover (the "Change image" button)."""
    await _add_image(event, await file.read(), db, make_cover=True)


async def add_images(event: Event, files: list[UploadFile], db: AsyncSession) -> None:
    """Append one or more images to the gallery. The first becomes the cover only
    if the event had none. Each upload is validated by its bytes (not its
    Content-Type) in image_service."""
    for file in files:
        await _add_image(event, await file.read(), db, make_cover=False)


def _find_image(event: Event, image_id: int) -> EventImage:
    for img in event.images:
        if img.id == image_id:
            return img
    raise HTTPException(status_code=404, detail="Image not found")


async def set_cover(event: Event, image_id: int, db: AsyncSession) -> None:
    target = _find_image(event, image_id)
    for img in event.images:
        img.is_cover = img is target
    event.image_focal_x = event.image_focal_y = 50.0  # focal was tuned for the old cover
    _sync_cover(event)
    await db.commit()


async def delete_image(event: Event, image_id: int, db: AsyncSession) -> None:
    target = _find_image(event, image_id)
    was_cover = target.is_cover
    _remove_image(target)
    event.images.remove(target)
    await db.delete(target)
    if was_cover:
        # Promote the next image (lowest position) so the event keeps a cover.
        remaining = sorted(event.images, key=lambda i: i.position)
        if remaining:
            remaining[0].is_cover = True
    _sync_cover(event)
    await db.commit()


async def reorder_images(event: Event, ordered_ids: list[int], db: AsyncSession) -> None:
    """Apply gallery order from the submitted id list; any image not listed keeps
    its relative order after the listed ones."""
    pos = {img_id: i for i, img_id in enumerate(ordered_ids)}
    tail = len(ordered_ids)
    for img in event.images:
        img.position = pos.get(img.id, tail + img.id)
    await db.commit()


async def generate_event_image(event: Event, extra_prompt: str, db: AsyncSession) -> None:
    """Generate a hero image from the event details and save it as the cover."""
    from app import ai_service
    ctx = {"title": event.title, "location": event.location, "theme": event.theme}
    data = await ai_service.generate_image_png(ai_service.image_prompt(ctx, extra_prompt))
    await _add_image(event, data, db, make_cover=True)


def _copy_upload(path: str | None) -> str | None:
    """Copy an existing uploads file to a fresh name so a clone owns its own image
    files (deleting the original event won't take the copy's images with it).
    Returns the new public path, or None if there's nothing to copy."""
    if not path:
        return None
    src = os.path.join(settings.upload_dir, os.path.basename(path))
    if not os.path.exists(src):
        return None
    os.makedirs(settings.upload_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{os.path.splitext(src)[1]}"
    try:
        shutil.copyfile(src, os.path.join(settings.upload_dir, fname))
    except OSError:
        return None
    return f"/uploads/{fname}"


async def duplicate_event(event: Event, db: AsyncSession, *, host_id: int | None, make_manage_token: bool) -> Event:
    """Clone an event into a fresh draft the host can edit for the next occasion.
    Copies the creative work — details, theme, image settings, the photo gallery
    (as new files), and the custom questions — but NOT guests, RSVPs, wall posts,
    views, or cancelled state. The clone gets brand-new tokens and a cleared date
    so the host re-picks one. `event` must be loaded with `images`/`questions`."""
    clone = Event(
        host_id=host_id,
        title=f"{event.title} (copy)",
        description=event.description,
        location=event.location,
        event_date=None,  # cleared — the host re-picks a date for the new occasion
        event_end=None,
        rsvp_deadline=None,
        timezone=event.timezone,
        host_display_name=event.host_display_name,
        host_email=event.host_email,
        image_fit=event.image_fit,
        image_focal_x=event.image_focal_x,
        image_focal_y=event.image_focal_y,
        theme=event.theme,
        allow_plus_ones=event.allow_plus_ones,
        wall_enabled=event.wall_enabled,
        guestlist_public=event.guestlist_public,
        public_token=new_token(),
        manage_token=new_token(24) if make_manage_token else None,
    )
    db.add(clone)
    await db.flush()  # assign clone.id for the child rows below

    new_images: list[EventImage] = []
    for img in sorted(event.images, key=lambda i: i.position):
        new_path = _copy_upload(img.path)
        if new_path is None:
            continue
        ni = EventImage(
            event_id=clone.id, path=new_path, thumb_path=_copy_upload(img.thumb_path),
            position=img.position, is_cover=img.is_cover,
        )
        db.add(ni)
        new_images.append(ni)
    # Mirror the cover into the denormalized fields directly (clone.images isn't
    # loaded yet, so _sync_cover can't walk the relationship).
    cover = next((i for i in new_images if i.is_cover), new_images[0] if new_images else None)
    clone.image_path = cover.path if cover else None
    clone.image_thumb_path = cover.thumb_path if cover else None

    for q in sorted(event.questions, key=lambda q: q.position):
        db.add(EventQuestion(
            event_id=clone.id, prompt=q.prompt, qtype=q.qtype,
            options=list(q.options or []), required=q.required, position=q.position,
        ))

    await db.commit()
    await db.refresh(clone)
    return clone


async def delete_event(event: Event, db: AsyncSession) -> None:
    for img in event.images:
        _remove_image(img)
    _remove_image_file(event.image_path)  # legacy events may predate the gallery
    # View + broadcast rows aren't eager-loaded here, so clear them explicitly
    # before the event goes (same reason replace_questions deletes RsvpAnswer).
    await db.execute(delete(InviteView).where(InviteView.event_id == event.id))
    await db.execute(delete(Broadcast).where(Broadcast.event_id == event.id))
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
                    view_token=inv.token,
                )
                if sent:
                    inv.sent_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
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


# ── Pagination (guest list / RSVPs) ──────────────────────────────────────────
# Stable orderings shared by the embedded first page (sliced from the already-
# loaded relationship) and the paginated DB endpoints, so "show more" appends in
# the same order it started: invites oldest-first, RSVPs newest-first.
def ordered_invites(event: Event) -> list[Invite]:
    return sorted(event.invites, key=lambda i: i.id)


def ordered_rsvps(event: Event) -> list[Rsvp]:
    return sorted(event.rsvps, key=lambda r: (r.updated_at, r.id), reverse=True)


async def fetch_invite_page(
    event_id: int, db: AsyncSession, limit: int, offset: int
) -> tuple[list[Invite], int]:
    total = (
        await db.execute(select(func.count(Invite.id)).where(Invite.event_id == event_id))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Invite)
            .where(Invite.event_id == event_id)
            .order_by(Invite.id)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), total


def cap_detail(detail, event: Event) -> None:
    """Trim an EventDetail's embedded invite/RSVP lists to the first page and set
    the *_total counts, so the dashboard ships a bounded payload and pages in the
    rest via the /invites and /rsvps endpoints. Mutates `detail` in place."""
    limit = settings.list_page_size
    invites = ordered_invites(event)
    rsvps = ordered_rsvps(event)
    detail.invites = [InviteOut.model_validate(i) for i in invites[:limit]]
    detail.invites_total = len(invites)
    detail.rsvps = [RsvpOut.model_validate(r) for r in rsvps[:limit]]
    detail.rsvps_total = len(rsvps)


async def fetch_rsvp_page(
    event_id: int, db: AsyncSession, limit: int, offset: int
) -> tuple[list[Rsvp], int]:
    total = (
        await db.execute(select(func.count(Rsvp.id)).where(Rsvp.event_id == event_id))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Rsvp)
            .where(Rsvp.event_id == event_id)
            .order_by(Rsvp.updated_at.desc(), Rsvp.id.desc())
            .options(selectinload(Rsvp.answers))
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), total


# ── Invite-open tracking (view log) ──────────────────────────────────────────
async def record_view(
    event: Event, invite: Invite | None, ip: str, user_agent: str, db: AsyncSession
) -> None:
    """Log one open of an invite/event link (raw IP + user-agent) and, for a
    personalized invite, bump its view counters. Called from the browser beacon,
    so bots that don't run JS never reach here."""
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    db.add(InviteView(
        event_id=event.id,
        invite_id=invite.id if invite else None,
        ip=(ip or "")[:64],
        user_agent=(user_agent or "")[:500],
    ))
    if invite:
        invite.view_count = (invite.view_count or 0) + 1
        invite.last_viewed_at = now
        if invite.viewed_at is None:
            invite.viewed_at = now
    await db.commit()


async def record_email_open(token: str, db: AsyncSession) -> None:
    """Bump an invite's email-open counters from the tracking pixel. Best-effort
    and deliberately IP-free: email opens are mostly fetched by provider proxies
    (Apple/Gmail), so only the soft 'was rendered' signal is recorded, never an
    IP. A bad/unknown token is a silent no-op (the pixel still returns)."""
    invite = (
        await db.execute(select(Invite).where(Invite.token == token))
    ).scalar_one_or_none()
    if not invite:
        return
    invite.email_open_count = (invite.email_open_count or 0) + 1
    if invite.email_opened_at is None:
        invite.email_opened_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    await db.commit()


async def fetch_views(event_id: int, db: AsyncSession, limit: int = 200) -> ViewLog:
    """Recent invite opens for an event (newest first, capped), plus headline
    totals, for the host's view log. Guest names are resolved from the invite;
    public-link opens have no invite and show as anonymous."""
    base = select(func.count(InviteView.id)).where(InviteView.event_id == event_id)
    total = (await db.execute(base)).scalar_one()
    unique_ips = (
        await db.execute(
            select(func.count(func.distinct(InviteView.ip)))
            .where(InviteView.event_id == event_id, InviteView.ip != "")
        )
    ).scalar_one()
    anonymous = (
        await db.execute(base.where(InviteView.invite_id.is_(None)))
    ).scalar_one()
    rows = (
        await db.execute(
            select(InviteView)
            .where(InviteView.event_id == event_id)
            .order_by(InviteView.created_at.desc(), InviteView.id.desc())
            .options(selectinload(InviteView.invite))
            .limit(limit)
        )
    ).scalars().all()
    items = [
        InviteViewOut(
            id=v.id,
            invite_id=v.invite_id,
            guest_name=v.invite.guest_name if v.invite else "",
            guest_email=v.invite.guest_email if v.invite else "",
            ip=v.ip,
            user_agent=v.user_agent,
            created_at=v.created_at,
        )
        for v in rows
    ]
    return ViewLog(items=items, total=total, unique_ips=unique_ips, anonymous=anonymous)


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


async def send_broadcast(event: Event, body: BroadcastRequest, db: AsyncSession) -> BroadcastResult:
    """Email the host's message to the chosen audience, best-effort per recipient,
    and record the send so the dashboard can show a history. Nothing is logged
    when email isn't configured (no message actually went out)."""
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

    if recipients:
        db.add(Broadcast(
            event_id=event.id, subject=body.subject, message=body.message,
            audience=body.audience, recipients=len(recipients), sent=sent,
        ))
        await db.commit()
    return BroadcastResult(sent=sent, recipients=len(recipients), email_enabled=True)


async def fetch_broadcasts(event_id: int, db: AsyncSession, limit: int = 50) -> list[BroadcastOut]:
    """Past broadcasts for an event, newest first, for the dashboard history."""
    rows = (
        await db.execute(
            select(Broadcast)
            .where(Broadcast.event_id == event_id)
            .order_by(Broadcast.created_at.desc(), Broadcast.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [BroadcastOut.model_validate(b) for b in rows]


# ── Cancel / reinstate ───────────────────────────────────────────────────────
async def cancel_event(event: Event, message: str, notify: bool, db: AsyncSession) -> CancelResult:
    """Soft-cancel the event (reversible) and stamp the host's note. When `notify`
    is set, also email all guests the cancellation via the broadcast sender."""
    event.cancelled_at = _naive_utcnow()
    event.cancellation_message = (message or "").strip()
    await db.commit()

    notified = None
    if notify:
        note = event.cancellation_message or f"{event.host_display_name or 'The host'} has cancelled this event."
        notified = await send_broadcast(event, BroadcastRequest(
            subject=f"Cancelled: {event.title}",
            message=note,
            audience="all",
        ), db)
    return CancelResult(cancelled_at=event.cancelled_at, notified=notified)


async def reinstate_event(event: Event, db: AsyncSession) -> None:
    """Reverse a cancellation: clear the stamp and note so the invite reopens and
    the RSVP form comes back."""
    event.cancelled_at = None
    event.cancellation_message = ""
    await db.commit()


# ── Guest wall ───────────────────────────────────────────────────────────────
def coming_list(event: Event) -> list[ComingOut]:
    """Names (and party size) of guests who said yes — for the public 'who's
    coming' list. Never exposes emails."""
    return [
        ComingOut(guest_name=r.guest_name, party_size=max(r.party_size, 1))
        for r in event.rsvps if r.status == "yes"
    ]


async def delete_wall_post(event: Event, post_id: int, db: AsyncSession) -> None:
    post = (
        await db.execute(
            select(WallPost).where(WallPost.id == post_id, WallPost.event_id == event.id)
        )
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    await db.delete(post)
    await db.commit()


# ── Co-hosts ─────────────────────────────────────────────────────────────────
async def add_cohost(event: Event, email: str, db: AsyncSession) -> CohostOut:
    target = (
        await db.execute(select(User).where(User.email == email.lower().strip()))
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="No invitio account with that email — ask them to sign up first")
    if target.id == event.host_id:
        raise HTTPException(status_code=400, detail="That person owns this event")
    if any(c.user_id == target.id for c in event.cohosts):
        raise HTTPException(status_code=400, detail="They're already a co-host")
    db.add(EventCohost(event_id=event.id, user_id=target.id))
    await db.commit()
    return CohostOut(user_id=target.id, email=target.email, name=target.name)


async def remove_cohost(event: Event, user_id: int, db: AsyncSession) -> None:
    row = (
        await db.execute(
            select(EventCohost).where(EventCohost.event_id == event.id, EventCohost.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Co-host not found")
    await db.delete(row)
    await db.commit()
