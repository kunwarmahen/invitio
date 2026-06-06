"""Optional AI generation for invite copy and hero images.

Everything here speaks the OpenAI-compatible HTTP shape, so the same code drives
local servers (Ollama / llama.cpp for text, LocalAI for images) and hosted
providers — only the base URL / key / model differ (see config.py). Both text and
image generation are off unless explicitly configured, and each is independent.
"""
import base64

import httpx
from fastapi import HTTPException

from app.config import settings


def llm_enabled() -> bool:
    return bool(settings.ai_llm_enabled and settings.ai_llm_base_url)


def image_enabled() -> bool:
    return bool(settings.ai_image_enabled and settings.ai_image_base_url)


def _headers(api_key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


# ── Text (LLM) ───────────────────────────────────────────────────────────────
async def generate_text(system: str, user: str) -> str:
    if not llm_enabled():
        raise HTTPException(status_code=503, detail="AI text generation is not configured")
    payload = {
        "model": settings.ai_llm_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "temperature": 0.8,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ai_llm_timeout) as client:
            resp = await client.post(
                _url(settings.ai_llm_base_url, "chat/completions"),
                json=payload, headers=_headers(settings.ai_llm_api_key),
            )
            resp.raise_for_status()
            data = resp.json()
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AI request failed: {exc}") from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected AI response: {exc}") from exc
    if not text:
        raise HTTPException(status_code=502, detail="The model returned an empty response")
    return text


# ── Image ────────────────────────────────────────────────────────────────────
async def generate_image_png(prompt: str) -> bytes:
    if not image_enabled():
        raise HTTPException(status_code=503, detail="AI image generation is not configured")
    payload = {
        "model": settings.ai_image_model,
        "prompt": prompt,
        "n": 1,
        "size": settings.ai_image_size,
        "response_format": "b64_json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ai_image_timeout) as client:
            resp = await client.post(
                _url(settings.ai_image_base_url, "images/generations"),
                json=payload, headers=_headers(settings.ai_image_api_key),
            )
            resp.raise_for_status()
            item = resp.json()["data"][0]
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"])
            # Some servers ignore response_format and return a URL instead.
            if item.get("url"):
                img = await client.get(item["url"])
                img.raise_for_status()
                return img.content
        raise HTTPException(status_code=502, detail="AI response had no image data")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AI request failed: {exc}") from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected AI response: {exc}") from exc


# ── Prompt builders ──────────────────────────────────────────────────────────
def _event_lines(ctx: dict) -> str:
    bits = []
    if ctx.get("title"):
        bits.append(f"Event: {ctx['title']}")
    if ctx.get("host_display_name"):
        bits.append(f"Host: {ctx['host_display_name']}")
    if ctx.get("event_date"):
        bits.append(f"When: {ctx['event_date']}")
    if ctx.get("location"):
        bits.append(f"Where: {ctx['location']}")
    return "\n".join(bits) or "An event"


def description_messages(ctx: dict) -> tuple[str, str]:
    tone = (ctx.get("tone") or "warm and inviting").strip()
    system = (
        "You write short, vivid event invitation descriptions. Return 2-4 sentences "
        "of plain text only — no markdown, no title, no sign-off, no placeholders."
    )
    user = (
        f"Write a {tone} invitation description for guests.\n\n{_event_lines(ctx)}\n\n"
        "Make guests excited to attend. Do not restate the date/location as a list."
    )
    return system, user


def broadcast_messages(ctx: dict) -> tuple[str, str]:
    intent = (ctx.get("instructions") or "a friendly update about the event").strip()
    system = (
        "You write short, clear event update emails to guests. Return plain-text body "
        "only — no subject line, no markdown, no sign-off placeholder like [Name]."
    )
    user = (
        f"Write a brief message to guests: {intent}.\n\n{_event_lines(ctx)}\n\n"
        "Keep it to a short paragraph or two."
    )
    return system, user


async def text_from_request(body) -> str:
    """Dispatch an AiTextRequest to the right prompt builder + LLM call."""
    ctx = {
        "title": body.title, "event_date": body.event_date, "location": body.location,
        "host_display_name": body.host_display_name, "theme": body.theme,
        "tone": body.tone, "instructions": body.instructions,
    }
    system, user = broadcast_messages(ctx) if body.kind == "broadcast" else description_messages(ctx)
    return await generate_text(system, user)


def image_prompt(ctx: dict, extra: str = "") -> str:
    parts = []
    if ctx.get("title"):
        parts.append(ctx["title"])
    if ctx.get("location"):
        parts.append(f"at {ctx['location']}")
    if ctx.get("theme"):
        parts.append(f"{ctx['theme']} color theme")
    base = ", ".join(parts) or "a celebration"
    extra = (extra or "").strip()
    tail = f", {extra}" if extra else ""
    return (
        f"An elegant, festive invitation hero image for {base}{tail}. "
        "Tasteful, high quality, vibrant, no text or lettering, no watermark."
    )
