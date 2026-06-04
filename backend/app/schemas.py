import datetime

from pydantic import BaseModel, EmailStr, Field


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
    event_date: datetime.datetime | None = None
    event_end: datetime.datetime | None = None
    host_display_name: str = ""
    theme: str = "violet"
    image_fit: str = Field(default="cover", pattern="^(cover|contain)$")
    allow_plus_ones: bool = True


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    event_date: datetime.datetime | None = None
    event_end: datetime.datetime | None = None
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
    event_date: datetime.datetime | None
    event_end: datetime.datetime | None
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
    event_date: datetime.datetime | None
    event_end: datetime.datetime | None
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
