"""A tiny in-memory rate limiter for the no-account public endpoints.

The quick-create / RSVP / wall flows take no login, so without a brake they can
be trivially spammed. This is a fixed-window counter keyed by client IP + a
named bucket — good enough for a single-instance self-hosted deploy (no Redis or
extra services). Controlled by `RATE_LIMIT_*` settings; the whole thing is a
no-op when `rate_limit_enabled` is false.

Not a substitute for a real WAF, but it stops casual abuse of the open flows.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.config import settings

# bucket+ip -> list of hit timestamps within the current window.
_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    # Behind the NAS reverse proxy the real client is in X-Forwarded-For; take the
    # first hop. Falls back to the socket peer for direct connections.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def reset() -> None:
    """Clear all counters (used by tests)."""
    _hits.clear()


def check(request: Request, bucket: str, limit: int, window_seconds: int = 3600) -> None:
    """Record one hit for (bucket, client-IP) and raise HTTP 429 once `limit` hits
    occur within `window_seconds`. No-op when rate limiting is disabled."""
    if not settings.rate_limit_enabled or limit <= 0:
        return
    now = time.time()
    cutoff = now - window_seconds
    key = (bucket, _client_ip(request))
    times = _hits[key]
    # Drop hits that have aged out of the window.
    times[:] = [t for t in times if t >= cutoff]
    if len(times) >= limit:
        retry = int(times[0] + window_seconds - now) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests — please slow down and try again shortly.",
            headers={"Retry-After": str(max(retry, 1))},
        )
    times.append(now)
    # Opportunistic prune so abandoned keys don't accumulate forever.
    if len(_hits) > 4096:
        for k in [k for k, v in _hits.items() if not v or v[-1] < cutoff]:
            _hits.pop(k, None)
