"""Outbound email for invitations, via Gmail SMTP + App Password.

Sending is best-effort: when no Gmail credentials are configured every send is a
silent no-op, so the rest of the app (creating events, generating shareable
links) works fine without email. The host can always copy the link manually.
"""
import asyncio
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from app.config import settings


def email_configured() -> bool:
    return bool(settings.gmail_address and settings.gmail_app_password)


def _send_via_gmail(to_email: str, subject: str, html: str, text: str) -> None:
    """Blocking SMTP send — call via asyncio.to_thread."""
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    msg["Subject"] = subject
    msg["From"] = f"{settings.email_from_name} <{settings.gmail_address}>"
    msg["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls()
        server.login(settings.gmail_address, settings.gmail_app_password)
        server.sendmail(settings.gmail_address, [to_email], msg.as_string())


def _fmt_when(when: datetime.datetime | None) -> str:
    if not when:
        return ""
    try:
        return when.strftime("%A, %B %-d, %Y · %-I:%M %p")
    except ValueError:  # platforms without %-d / %-I (e.g. some libc)
        return when.strftime("%A, %B %d, %Y · %I:%M %p")


async def send_invite_email(
    to_email: str,
    guest_name: str,
    event_title: str,
    host_name: str,
    when: datetime.datetime | None,
    location: str,
    rsvp_url: str,
    image_url: str | None = None,
) -> bool:
    """Email a single tokenized RSVP link. Returns False (no-op) when Gmail
    isn't configured; raises only on a genuine SMTP failure."""
    if not email_configured():
        return False

    greeting = f"Hi {escape(guest_name)}," if guest_name else "Hi there,"
    when_str = _fmt_when(when)
    safe_title = escape(event_title)
    safe_host = escape(host_name or "Your host")
    safe_loc = escape(location)
    safe_url = escape(rsvp_url)

    img_html = (
        f"<img src='{escape(image_url)}' alt='' "
        f"style='width:100%;max-height:280px;object-fit:cover;border-radius:12px 12px 0 0'>"
        if image_url else ""
    )
    detail_rows = ""
    if when_str:
        detail_rows += f"<p style='margin:6px 0'>🗓️ <b>{escape(when_str)}</b></p>"
    if safe_loc:
        detail_rows += f"<p style='margin:6px 0'>📍 {safe_loc}</p>"

    html = (
        f"<div style='font-family:system-ui,-apple-system,sans-serif;max-width:520px;"
        f"margin:auto;border:1px solid #eee;border-radius:14px;overflow:hidden'>"
        f"{img_html}"
        f"<div style='padding:24px'>"
        f"<p style='color:#888;font-size:13px;margin:0 0 4px'>{safe_host} invites you to</p>"
        f"<h1 style='margin:0 0 12px;font-size:24px;color:#1a1a2e'>{safe_title}</h1>"
        f"{detail_rows}"
        f"<p style='margin:18px 0 6px;color:#444'>{greeting} please let us know if you can make it.</p>"
        f"<p style='margin:18px 0'><a href='{safe_url}' style='display:inline-block;"
        f"padding:13px 26px;background:#7c3aed;color:#fff;border-radius:10px;"
        f"text-decoration:none;font-weight:600'>RSVP now</a></p>"
        f"<p style='color:#999;font-size:12px'>Or paste this link into your browser:<br>{safe_url}</p>"
        f"</div></div>"
    )
    text = (
        f"{safe_host} invites you to {event_title}.\n"
        + (f"When: {when_str}\n" if when_str else "")
        + (f"Where: {location}\n" if location else "")
        + f"\nRSVP here: {rsvp_url}\n"
    )
    await asyncio.to_thread(_send_via_gmail, to_email, f"You're invited: {event_title}", html, text)
    return True


async def send_manage_link_email(to_email: str, event_title: str, manage_url: str, share_url: str) -> bool:
    """Email the host of a no-account event their private management link plus the
    public share link. Returns False (no-op) when Gmail isn't configured."""
    if not email_configured():
        return False
    safe_title = escape(event_title)
    html = (
        f"<div style='font-family:system-ui,-apple-system,sans-serif;max-width:520px;margin:auto'>"
        f"<h2 style='color:#1a1a2e'>Your event “{safe_title}” is ready 🎉</h2>"
        f"<p style='color:#444'>Keep this email — the link below is the only way to manage your "
        f"event (edit details, add guests, see RSVPs) without an account:</p>"
        f"<p><a href='{escape(manage_url)}' style='display:inline-block;padding:12px 22px;"
        f"background:#7c3aed;color:#fff;border-radius:10px;text-decoration:none;font-weight:600'>"
        f"Manage my event</a></p>"
        f"<p style='color:#444;margin-top:18px'>Share this link with your guests so they can RSVP:</p>"
        f"<p style='font-family:monospace;background:#f5f3ff;padding:10px 12px;border-radius:8px;"
        f"word-break:break-all'>{escape(share_url)}</p>"
        f"</div>"
    )
    text = (
        f"Your event \"{event_title}\" is ready.\n\n"
        f"Manage it (keep private): {manage_url}\n"
        f"Share with guests to RSVP: {share_url}\n"
    )
    await asyncio.to_thread(_send_via_gmail, to_email, f"Manage your event: {event_title}", html, text)
    return True
