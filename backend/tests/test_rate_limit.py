from app.config import settings


async def test_quick_create_rate_limited(client, monkeypatch):
    # Enable limiting with a tiny budget (monkeypatch restores after the test).
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_create_per_hour", 2)

    body = {"title": "Bash", "host_display_name": "Sam"}
    assert (await client.post("/api/public/events", json=body)).status_code == 201
    assert (await client.post("/api/public/events", json=body)).status_code == 201
    # Third one within the window is blocked.
    r = await client.post("/api/public/events", json=body)
    assert r.status_code == 429
    assert "Retry-After" in r.headers


async def test_rate_limit_disabled_is_noop(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    body = {"title": "Bash", "host_display_name": "Sam"}
    for _ in range(5):
        assert (await client.post("/api/public/events", json=body)).status_code == 201


async def test_quick_create_can_be_disabled(client, monkeypatch):
    # /api/config advertises the flag; the create endpoint refuses with 403.
    monkeypatch.setattr(settings, "quick_create_enabled", False)
    assert (await client.get("/api/config")).json()["quick_create"] is False
    body = {"title": "Bash", "host_display_name": "Sam"}
    assert (await client.post("/api/public/events", json=body)).status_code == 403
