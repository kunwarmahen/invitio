import datetime
from typing import Annotated, Optional

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
    # IANA timezone of the event (e.g. "America/New_York"), captured from the
    # host's browser so the event renders in its own local time for all guests.
    timezone: str | None = Field(default=None, max_length=64)
    host_display_name: str = ""
    theme: str = "violet"
    image_fit: str = Field(default="contain", pattern="^(cover|contain)$")
    allow_plus_ones: bool = True


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    event_date: EventDateIn = None
    event_end: EventDateIn = None
    timezone: str | None = Field(default=None, max_length=64)
    host_display_name: str | None = None
    theme: str | None = None
    image_fit: str | None = Field(default=None, pattern="^(cover|contain)$")
    allow_plus_ones: bool | None = None


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

    class Config:
        from_attributes = True


class RsvpOut(BaseModel):
    id: int
    guest_name: str
    guest_email: str
    status: str
    party_size: int
    message: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    title: str
    description: str
    location: str
    event_date: EventDateOut
    event_end: EventDateOut
    timezone: str | None
    host_display_name: str
    image_path: str | None
    image_fit: str
    theme: str
    allow_plus_ones: bool
    public_token: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class QuickCreateResult(BaseModel):
    event: EventOut
    manage_token: str
    manage_url: str
    share_url: str
    emailed: bool


class EventDetail(EventOut):
    invites: list[InviteOut] = []
    rsvps: list[RsvpOut] = []


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
    timezone: str | None
    host_display_name: str
    image_path: str | None
    image_fit: str
    theme: str
    allow_plus_ones: bool
    public_token: str
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


TokenResponse.model_rebuild()
AddInvitesRequest.model_rebuild()
