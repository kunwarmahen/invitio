"""Shared pytest fixtures.

A throwaway SQLite file DB + uploads dir are configured via the environment
*before* `app` is imported, so the app's engine/settings bind to them. Each test
gets a freshly recreated schema for isolation, and the in-memory rate limiter is
reset between tests.
"""
import io
import os
import sys
import tempfile
from pathlib import Path

# Make `app` importable and point it at a disposable environment BEFORE importing.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_TMP = tempfile.mkdtemp(prefix="invitio-test-")
os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
        "UPLOAD_DIR": f"{_TMP}/uploads",
        "PUBLIC_BASE_URL": "http://testserver",
        "JWT_SECRET_KEY": "test-secret",
        "RATE_LIMIT_ENABLED": "false",  # individual tests opt in
        "REMINDERS_ENABLED": "false",
    }
)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import rate_limit  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    rate_limit.reset()
    yield


@pytest_asyncio.fixture
async def client():
    # Fresh schema per test for isolation.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def png_bytes():
    """Factory for valid PNG bytes of a given size + colour."""
    def _make(size=(800, 600), color=(120, 80, 200)):
        buf = io.BytesIO()
        Image.new("RGB", size, color).save(buf, "PNG")
        return buf.getvalue()
    return _make


@pytest_asyncio.fixture
def register(client):
    async def _register(email="host@example.com", password="secret123", name="Host"):
        return await client.post(
            "/api/auth/signup", json={"email": email, "password": password, "name": name}
        )
    return _register


@pytest_asyncio.fixture
async def host(register):
    """A registered user; returns (token, auth_headers)."""
    res = await register()
    token = res.json()["token"]
    return token, {"Authorization": f"Bearer {token}"}
