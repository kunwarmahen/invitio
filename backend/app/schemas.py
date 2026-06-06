import datetime
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, EmailStr, Field, PlainSerializer


# ── Datetime handling ─────────────────────────────────────────────────────────
# Event datetimes are stored naive-UTC. On input we normalise any tz-aware value
# to naive UTC; on output we re-attach UTC and emit an ISO string *with* the `Z`
# offset, so the browser parses the correct absolute instant (a bare naive string
# would be read as the viewer's local time). The event's own IANA `timezone`
# (captured from the host) is what the frontend uses to render the event in its
# local time for every guest.
def _to_naive_utc(v: datetime.datetime | None) -> datetime.datetime | None:
    if v is not None and v.tzinfo is not None:
        v = v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return v


def _utc_iso(v: datetime.datetime | None) -> str | None:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=datetime.timezone.utc)
    return v.isoformat().replace("+00:00", "Z")


# Input field: parse the datetime, then coerce any offset to naive UTC for storage.
EventDateIn = Annotated[Optional[datetime.datetime], AfterValidator(_to_naive_utc)]
# Output field: serialize naive-UTC back to an ISO string carrying the Z offset.
EventDateOut = Annotated[
    Optional[datetime.datetime], PlainSerializer(_utc_iso, return_type=str, when_used="json")
]


# ── Auth ──────────────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: str
    name: str

    class Config:
        from_attributes = True


# ── Events ────────────────────────────────────────────────────────────────────
class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    location: str = ""
    event_date: EventDateIn = None
    event_end: EventDateIn = None
    # Optional cutoff by which guests are asked to RSVP (informational/soft).
    rsvp_deadline: EventDateIn = None
    # IANA timezone of the event (e.g. "America/New_York"), captured from the
    # host's browser so the event renders in its own local time for all guests.
    timezone: str | None = Field(default=None, max_length=64)
    host_display_name: str = ""
    theme: str = "violet"
    image_fit: str = Field(default="contain", pattern="^(cover|contain)$")
    image_focal_x: float = Field(default=50.0, ge=0, le=100)
    image_focal_y: float = Field(default=50.0, ge=0, le=100)
    allow_plus_ones: bool = True
    wall_enabled: bool = False
    guestlist_public: bool = False


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    event_date: EventDateIn = None
    event_end: EventDateIn = None
    rsvp_deadline: EventDateIn = None
    timezone: str | None = Field(default=None, max_length=64)
    host_display_name: str | None = None
    theme: str | None = None
    image_fit: str | None = Field(default=None, pattern="^(cover|contain)$")
    image_focal_x: float | None = Field(default=None, ge=0, le=100)
    image_focal_y: float | None = Field(default=None, ge=0, le=100)
    allow_plus_ones: bool | None = None
    wall_enabled: bool | None = None
    guestlist_public: bool | None = None


class QuickCreate(EventCreate):
    """Create an event with no account. The optional host_email is where the
    management link is sent (and lets the host claim the event later)."""
    host_email: EmailStr | None = None


class InviteOut(BaseModel):
    id: int
    guest_email: str
    guest_name: str
    token: str
    sent_at: datetime.datetime | None
    viewed_at: datetime.datetime | None = None
    last_viewed_at: datetime.datetime | None = None
    view_count: int = 0
    email_opened_at: datetime.datetime | None = None
    email_open_count: int = 0

    class Config:
        from_attributes = True


# ── Invite-open tracking (view log) ──────────────────────────────────────────
class InviteViewOut(BaseModel):
    id: int
    invite_id: int | None = None
    # Resolved from the invite; "" for opens of the public shareable link.
    guest_name: str = ""
    guest_email: str = ""
    ip: str = ""
    user_agent: str = ""
    created_at: datetime.datetime


class ViewLog(BaseModel):
    items: list[InviteViewOut] = []
    total: int = 0
    unique_ips: int = 0
    # How many of `total` came from the public/forwarded link (no invite).
    anonymous: int = 0


# ── Image gallery ─────────────────────────────────────────────────────────────
class EventImageOut(BaseModel):
    id: int
    path: str
    thumb_path: str | None = None
    position: int
    is_cover: bool

    class Config:
        from_attributes = True


class ReorderImagesRequest(BaseModel):
    ids: list[int] = []


# ── Custom RSVP questions ───────────────────────────────────────────────────
class QuestionIn(BaseModel):
    # id present => update existing question; absent => create new. Omitting a
    # previously-saved id deletes that question (and its answers).
    id: int | None = None
    prompt: str = Field(min_length=1, max_length=300)
    qtype: Literal["text", "choice", "multi"] = "text"
    options: list[str] = []
    required: bool = False


class QuestionsUpdate(BaseModel):
    questions: list[QuestionIn] = []


class QuestionOut(BaseModel):
    id: int
    prompt: str
    qtype: str
    options: list[str]
    required: bool

    class Config:
        from_attributes = True


class AnswerIn(BaseModel):
    question_id: int
    value: str | list[str] = ""


class AnswerOut(BaseModel):
    question_id: int
    value: str | list[str]

    class Config:
        from_attributes = True


class RsvpOut(BaseModel):
    id: int
    guest_name: str
    guest_email: str
    status: str
    party_size: int
    message: str
    answers: list[AnswerOut] = []
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


# ── Guest wall ───────────────────────────────────────────────────────────────
class WallPostOut(BaseModel):
    id: int
    guest_name: str
    message: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class WallPostCreate(BaseModel):
    guest_name: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)


class ComingOut(BaseModel):
    guest_name: str
    party_size: int


# ── Co-hosts ─────────────────────────────────────────────────────────────────
class CohostOut(BaseModel):
    user_id: int
    email: str
    name: str

    class Config:
        from_attributes = True


class AddCohostRequest(BaseModel):
    email: EmailStr


class EventOut(BaseModel):
    id: int
    title: str
    description: str
    location: str
    event_date: EventDateOut
    event_end: EventDateOut
    rsvp_deadline: EventDateOut = None
    timezone: str | None
    host_display_name: str
    image_path: str | None
    image_thumb_path: str | None = None
    image_fit: str
    image_focal_x: float = 50.0
    image_focal_y: float = 50.0
    theme: str
    allow_plus_ones: bool
    wall_enabled: bool
    guestlist_public: bool
    public_token: str
    created_at: datetime.datetime
    # True when the current viewer owns the event (vs. a co-host). Set per-request
    # in the router; defaults true for action-returns where the actor manages it.
    is_owner: bool = True

    class Config:
        from_attributes = True


class QuickCreateResult(BaseModel):
    event: EventOut
    manage_token: str
    manage_url: str
    share_url: str
    emailed: bool


class EventDetail(EventOut):
    # `invites`/`rsvps` carry only the first page (newest RSVPs first); the rest
    # are fetched from the paginated /invites and /rsvps endpoints. The *_total
    # fields are the full counts so the UI can show "(N)" and a "show more".
    invites: list[InviteOut] = []
    invites_total: int = 0
    rsvps: list[RsvpOut] = []
    rsvps_total: int = 0
    questions: list[QuestionOut] = []
    wall_posts: list[WallPostOut] = []
    cohosts: list[CohostOut] = []
    images: list[EventImageOut] = []


# ── Pagination ───────────────────────────────────────────────────────────────
class InvitePage(BaseModel):
    items: list[InviteOut]
    total: int
    limit: int
    offset: int


class RsvpPage(BaseModel):
    items: list[RsvpOut]
    total: int
    limit: int
    offset: int


# ── Broadcast ("message all guests") ─────────────────────────────────────────
class BroadcastRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1)
    audience: Literal["all", "yes", "maybe", "no", "pending"] = "all"


class BroadcastResult(BaseModel):
    sent: int
    recipients: int
    email_enabled: bool


# ── AI generation ────────────────────────────────────────────────────────────
class AiStatus(BaseModel):
    llm: bool
    image: bool


class AiTextRequest(BaseModel):
    # Stateless: the create form may be unsaved, so the event fields come in here
    # rather than via an event id.
    kind: Literal["description", "broadcast"]
    title: str = ""
    event_date: str | None = None
    location: str = ""
    host_display_name: str = ""
    theme: str = ""
    tone: str = ""           # description only
    audience: str = ""       # broadcast only (informational)
    instructions: str = ""   # broadcast intent


class AiTextResult(BaseModel):
    text: str


class AiImageRequest(BaseModel):
    prompt: str = ""  # optional extra guidance; the server seeds the rest from the event


class EventSummary(BaseModel):
    yes: int = 0
    no: int = 0
    maybe: int = 0
    head_count: int = 0          # total attending people (sum of party_size for yes)
    invited: int = 0
    responded: int = 0


# ── Invites (add guests) ────────────────────────────────────────────────────
class AddInvitesRequest(BaseModel):
    # Either a list of structured guests or raw emails; both supported.
    emails: list[EmailStr] = []
    guests: list["GuestEntry"] = []
    send_email: bool = True


class GuestEntry(BaseModel):
    email: EmailStr
    name: str = ""


class AddInvitesResult(BaseModel):
    added: list[InviteOut]
    emailed: int
    email_enabled: bool


# ── Public RSVP ───────────────────────────────────────────────────────────────
class PublicEventOut(BaseModel):
    title: str
    description: str
    location: str
    event_date: EventDateOut
    event_end: EventDateOut
    rsvp_deadline: EventDateOut = None
    timezone: str | None
    host_display_name: str
    image_path: str | None
    image_thumb_path: str | None = None
    image_fit: str
    image_focal_x: float = 50.0
    image_focal_y: float = 50.0
    theme: str
    allow_plus_ones: bool
    public_token: str
    images: list[EventImageOut] = []
    questions: list[QuestionOut] = []
    # Guest wall (only populated when the respective toggle is on).
    wall_enabled: bool = False
    guestlist_public: bool = False
    wall_posts: list[WallPostOut] = []
    coming: list[ComingOut] = []
    # Prefilled from the personal invite link, when present.
    guest_name: str = ""
    guest_email: str = ""
    # The guest's existing response, if they already RSVP'd.
    existing_rsvp: RsvpOut | None = None


class RsvpSubmit(BaseModel):
    guest_name: str = Field(min_length=1, max_length=120)
    guest_email: EmailStr | None = None
    status: str = Field(pattern="^(yes|no|maybe)$")
    party_size: int = Field(default=1, ge=1, le=50)
    message: str = ""
    answers: list[AnswerIn] = []


TokenResponse.model_rebuild()
AddInvitesRequest.model_rebuild()
