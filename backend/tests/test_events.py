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
