import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


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
    host_display_name: Mapped[str] = mapped_column(String, default="")
    host_email: Mapped[str | None] = mapped_column(String, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # How the invite image is displayed: "cover" crops to fill the hero,
    # "contain" shows the whole image (letterboxed over a blurred backdrop).
    image_fit: Mapped[str] = mapped_column(String, default="cover")
    theme: Mapped[str] = mapped_column(String, default="violet")
    allow_plus_ones: Mapped[bool] = mapped_column(Boolean, default=True)

    # Public, unguessable token used for the shareable RSVP link (/e/<token>).
    public_token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    # Secret token that grants management of an account-less event (/m/<token>).
    manage_token: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    host: Mapped["User"] = relationship(back_populates="events")
    invites: Mapped[list["Invite"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    rsvps: Mapped[list["Rsvp"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    guest_email: Mapped[str] = mapped_column(String, nullable=False)
    guest_name: Mapped[str] = mapped_column(String, default="")
    # Per-guest token for the personalized RSVP link (/i/<token>).
    token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)

    event: Mapped["Event"] = relationship(back_populates="invites")


class Rsvp(Base):
    __tablename__ = "rsvps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True, nullable=False)
    invite_id: Mapped[int | None] = mapped_column(ForeignKey("invites.id"), nullable=True)

    guest_name: Mapped[str] = mapped_column(String, nullable=False)
    guest_email: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="yes")  # yes | no | maybe
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    message: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    event: Mapped["Event"] = relationship(back_populates="rsvps")
