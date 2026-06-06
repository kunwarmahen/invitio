import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime.datetime:
    # Naive UTC: the DateTime columns are TIMESTAMP WITHOUT TIME ZONE, and
    # Postgres/asyncpg rejects tz-aware values for them. The whole app stores
    # naive UTC (see schemas._to_naive_utc and reminder_service._naive_utcnow).
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    events: Mapped[list["Event"]] = relationship(back_populates="host", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Null when the event was created via the no-account "quick create" flow —
    # such events are administered with manage_token instead of a logged-in host.
    host_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)

    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String, default="")
    event_date: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    event_end: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # Optional cutoff by which guests are asked to RSVP, shown on the invite so
    # the host/co-hosts can plan a headcount. Soft (informational only) — the
    # public RSVP endpoint still accepts responses after it passes. Stored
    # naive-UTC like the other event datetimes.
    rsvp_deadline: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # IANA timezone the event happens in (e.g. "America/New_York"), captured from
    # the host. event_date/event_end are stored naive-UTC; this is how the front
    # end renders them in the event's local time for every guest. Null = legacy.
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    host_display_name: Mapped[str] = mapped_column(String, default="")
    host_email: Mapped[str | None] = mapped_column(String, nullable=True)
    # Denormalized mirror of the cover EventImage's path (kept in sync by
    # event_service._sync_cover). The image gallery lives in `event_images`;
    # this column stays so the OG-tag/email/envelope/thumbnail read-paths keep
    # working with a single cheap field. Null when the event has no images.
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # Denormalized mirror of the cover EventImage's thumbnail (kept in sync by
    # _sync_cover). Served for host cards + the envelope so they load a small file
    # instead of the full hero. Null for the legacy/no-image case.
    image_thumb_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # How the invite image is displayed: "contain" (default) shows the whole
    # image over a blurred backdrop; "cover" crops it to fill the hero.
    image_fit: Mapped[str] = mapped_column(String, default="contain")
    # Focal point of the cover image (percent, 0-100) used when image_fit="cover"
    # so the crop keeps the chosen subject visible instead of dead-centering.
    # Tied to whichever image is the cover; reset to 50/50 when the cover changes.
    image_focal_x: Mapped[float] = mapped_column(default=50.0)
    image_focal_y: Mapped[float] = mapped_column(default=50.0)
    theme: Mapped[str] = mapped_column(String, default="violet")
    allow_plus_ones: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional public guest wall: a well-wishes board and/or a "who's coming"
    # list on the invite page. Both off by default for privacy.
    wall_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    guestlist_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Public, unguessable token used for the shareable RSVP link (/e/<token>).
    public_token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    # Secret token that grants management of an account-less event (/m/<token>).
    manage_token: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)

    # Set once the pre-event reminder/nudge batch has been sent, so the reminder
    # loop emails each event at most once.
    reminder_sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    host: Mapped["User"] = relationship(back_populates="events")
    invites: Mapped[list["Invite"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    rsvps: Mapped[list["Rsvp"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    questions: Mapped[list["EventQuestion"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventQuestion.position",
    )
    wall_posts: Mapped[list["WallPost"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="WallPost.created_at.desc()",
    )
    cohosts: Mapped[list["EventCohost"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    images: Mapped[list["EventImage"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventImage.position",
    )
    views: Mapped[list["InviteView"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    guest_email: Mapped[str] = mapped_column(String, nullable=False)
    guest_name: Mapped[str] = mapped_column(String, default="")
    # Per-guest token for the personalized RSVP link (/i/<token>).
    token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # First time the guest opened their personalized invite link, so the host can
    # see who has actually looked at the invitation. Stamped once (first view).
    # viewed_at/last_viewed_at/view_count are all maintained by the view beacon
    # (POST /public/view/<token>) so link-preview bots that don't run JS don't
    # inflate them; the per-open detail (incl. IP) lives in `invite_views`.
    viewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    last_viewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    # Soft email-open signal from the tracking pixel in the invite/reminder email.
    # IP-free on purpose: email opens are mostly fetched by provider proxies
    # (Apple Mail Privacy Protection, Gmail's image proxy) rather than the guest,
    # so this is a weak "the email was rendered somewhere" hint, kept separate
    # from the browser-accurate page-open counters above.
    email_opened_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    email_open_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    event: Mapped["Event"] = relationship(back_populates="invites")


class InviteView(Base):
    """One logged open of an invite/event link, recorded by a browser beacon
    (POST /public/view/<token>) so link-preview bots that don't run JS don't
    pollute the log. `invite_id` is the personalized-link guest; null for opens
    of the public shareable link (/e/<token>). Stores the raw client IP and
    user-agent so the host can see who/where an invite has been viewed from."""
    __tablename__ = "invite_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    invite_id: Mapped[int | None] = mapped_column(
        ForeignKey("invites.id", ondelete="SET NULL"), index=True, nullable=True
    )
    ip: Mapped[str] = mapped_column(String, default="")
    user_agent: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    event: Mapped["Event"] = relationship(back_populates="views")
    invite: Mapped["Invite | None"] = relationship()


class EventImage(Base):
    """One photo in an event's gallery. Exactly one row per event is the cover
    (`is_cover`), which is mirrored into `Event.image_path`. `position` orders the
    gallery strip on the invite page."""
    __tablename__ = "event_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    # Small thumbnail generated at upload time; served for cards/the envelope.
    # Null for legacy rows uploaded before thumbnails existed (read-paths fall
    # back to `path`).
    thumb_path: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    event: Mapped["Event"] = relationship(back_populates="images")


class Rsvp(Base):
    __tablename__ = "rsvps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    invite_id: Mapped[int | None] = mapped_column(
        ForeignKey("invites.id", ondelete="SET NULL"), nullable=True
    )

    guest_name: Mapped[str] = mapped_column(String, nullable=False)
    guest_email: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="yes")  # yes | no | maybe
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    message: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    event: Mapped["Event"] = relationship(back_populates="rsvps")
    answers: Mapped[list["RsvpAnswer"]] = relationship(
        back_populates="rsvp", cascade="all, delete-orphan"
    )


class EventQuestion(Base):
    """A host-defined RSVP question. `qtype` is "text" (free input), "choice"
    (pick one option) or "multi" (pick several); `options` holds the choices for
    the latter two and is empty for "text"."""
    __tablename__ = "event_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    qtype: Mapped[str] = mapped_column(String, default="text")  # text | choice | multi
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    event: Mapped["Event"] = relationship(back_populates="questions")
    answers: Mapped[list["RsvpAnswer"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class RsvpAnswer(Base):
    """One guest's answer to one EventQuestion. `value` is a string for
    text/choice questions and a list[str] for multi-select."""
    __tablename__ = "rsvp_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rsvp_id: Mapped[int] = mapped_column(ForeignKey("rsvps.id"), index=True, nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("event_questions.id"), index=True, nullable=False)
    value: Mapped[object] = mapped_column(JSON, default="")

    rsvp: Mapped["Rsvp"] = relationship(back_populates="answers")
    question: Mapped["EventQuestion"] = relationship(back_populates="answers")


class WallPost(Base):
    """A public well-wish left on an event's guest wall by anyone with the link."""
    __tablename__ = "wall_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    guest_name: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    event: Mapped["Event"] = relationship(back_populates="wall_posts")


class EventCohost(Base):
    """Grants another registered account full management of an event (except
    deleting it or managing co-hosts, which stay owner-only)."""
    __tablename__ = "event_cohosts"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_cohost"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    event: Mapped["Event"] = relationship(back_populates="cohosts")
    user: Mapped["User"] = relationship()

    # Proxied from the linked user so CohostOut (user_id/email/name) maps directly
    # from this row. Requires `user` to be eager-loaded.
    @property
    def email(self) -> str:
        return self.user.email

    @property
    def name(self) -> str:
        return self.user.name
