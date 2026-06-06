async def _create_event(client, headers, title="Party"):
    r = await client.post("/api/events", json={"title": title}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_and_get_event(client, host):
    _, headers = host
    ev = await _create_event(client, headers, "Rooftop")
    assert ev["title"] == "Rooftop"
    assert ev["public_token"]

    r = await client.get(f"/api/events/{ev['id']}", headers=headers)
    assert r.status_code == 200
    detail = r.json()
    assert detail["invites_total"] == 0
    assert detail["rsvps_total"] == 0
    assert detail["images"] == []


async def test_rsvp_deadline_round_trips_to_create_update_and_public(client, host):
    _, headers = host
    deadline = "2030-01-01T17:00:00Z"
    r = await client.post(
        "/api/events", json={"title": "Gala", "rsvp_deadline": deadline}, headers=headers
    )
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["rsvp_deadline"] == deadline

    # Visible to guests on the public invite (soft/informational).
    pub = await client.get(f"/api/public/event/{ev['public_token']}")
    assert pub.json()["rsvp_deadline"] == deadline

    # Editable, including clearing it.
    upd = await client.put(
        f"/api/events/{ev['id']}", json={"rsvp_deadline": None}, headers=headers
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["rsvp_deadline"] is None


async def test_other_user_cannot_see_event(client, host, register):
    _, headers = host
    ev = await _create_event(client, headers)
    res = await register(email="intruder@example.com")
    other = {"Authorization": f"Bearer {res.json()['token']}"}
    assert (await client.get(f"/api/events/{ev['id']}", headers=other)).status_code == 404


async def test_image_upload_generates_thumbnail(client, host, png_bytes):
    _, headers = host
    ev = await _create_event(client, headers)
    files = {"files": ("photo.png", png_bytes((2000, 1500)), "image/png")}
    r = await client.post(f"/api/events/{ev['id']}/images", files=files, headers=headers)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert len(detail["images"]) == 1
    img = detail["images"][0]
    assert img["is_cover"] is True
    assert img["thumb_path"] and img["thumb_path"] != img["path"]
    # The cover thumbnail is mirrored onto the event for cards/the envelope.
    assert detail["image_thumb_path"] == img["thumb_path"]


async def test_upload_rejects_non_image_bytes(client, host):
    _, headers = host
    ev = await _create_event(client, headers)
    # A .png name + image content-type, but the bytes are not an image.
    files = {"files": ("evil.png", b"#!/bin/sh\necho pwned\n", "image/png")}
    r = await client.post(f"/api/events/{ev['id']}/images", files=files, headers=headers)
    assert r.status_code == 400


async def test_invite_and_rsvp_pagination(client, host):
    _, headers = host
    ev = await _create_event(client, headers)
    emails = [f"guest{n}@example.com" for n in range(7)]
    r = await client.post(
        f"/api/events/{ev['id']}/invites",
        json={"emails": emails, "send_email": False},
        headers=headers,
    )
    assert r.status_code == 200
    assert len(r.json()["added"]) == 7

    # First page of 3.
    r = await client.get(f"/api/events/{ev['id']}/invites?limit=3&offset=0", headers=headers)
    page = r.json()
    assert page["total"] == 7
    assert len(page["items"]) == 3
    assert page["limit"] == 3 and page["offset"] == 0

    # Last page has the remainder.
    r = await client.get(f"/api/events/{ev['id']}/invites?limit=3&offset=6", headers=headers)
    assert len(r.json()["items"]) == 1

    # Detail embeds the totals.
    detail = (await client.get(f"/api/events/{ev['id']}", headers=headers)).json()
    assert detail["invites_total"] == 7


async def test_delete_event_with_invite_linked_rsvp():
    """Regression: deleting an event cascade-deletes both invites and rsvps, and a
    guest who RSVP'd via their personal link has rsvp.invite_id pointing at an
    invite. The cascade must not hit a FK violation regardless of which table the
    ORM deletes first. The shared SQLite test DB doesn't enforce foreign keys, so
    this uses a dedicated engine with PRAGMA foreign_keys=ON to actually exercise
    the constraint (mirrors Postgres in prod)."""
    import tempfile
    from pathlib import Path

    from sqlalchemy import event as sa_event, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.orm import selectinload

    from app import event_service
    from app.database import Base
    from app.models import Event, Invite, Rsvp

    tmp = tempfile.mkdtemp(prefix="invitio-fk-")
    fk_engine = create_async_engine(f"sqlite+aiosqlite:///{Path(tmp)/'fk.db'}")

    @sa_event.listens_for(fk_engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with fk_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(fk_engine, expire_on_commit=False)
    async with Session() as db:
        ev = Event(title="Bash", public_token="pub-tok")
        db.add(ev)
        await db.flush()
        inv = Invite(event_id=ev.id, guest_email="g@example.com", token="inv-tok")
        db.add(inv)
        await db.flush()
        db.add(Rsvp(event_id=ev.id, invite_id=inv.id, guest_name="G", status="yes"))
        await db.commit()
        event_id = ev.id

    async with Session() as db:
        ev = (
            await db.execute(
                select(Event)
                .where(Event.id == event_id)
                .options(
                    selectinload(Event.invites),
                    selectinload(Event.rsvps).selectinload(Rsvp.answers),
                    selectinload(Event.images),
                )
            )
        ).scalar_one()
        await event_service.delete_event(ev, db)

    async with Session() as db:
        assert (await db.execute(select(Event))).scalars().all() == []
        assert (await db.execute(select(Invite))).scalars().all() == []
        assert (await db.execute(select(Rsvp))).scalars().all() == []

    await fk_engine.dispose()
