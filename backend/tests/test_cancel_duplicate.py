"""Cancel (soft, reversible) + duplicate event flows."""


async def _create_event(client, headers, title="Party", **fields):
    r = await client.post("/api/events", json={"title": title, **fields}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def test_cancel_marks_event_and_blocks_rsvp(client, host):
    _, headers = host
    ev = await _create_event(client, headers, "Gala")

    # Public invite is open before cancelling.
    pub = await client.get(f"/api/public/event/{ev['public_token']}")
    assert pub.json()["cancelled_at"] is None

    # Cancel with a note (no notify → email isn't attempted).
    r = await client.post(
        f"/api/events/{ev['id']}/cancel",
        json={"message": "Venue flooded — so sorry!", "notify": False},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cancelled_at"] is not None
    assert body["notified"] is None

    # Surfaced to guests, with the host's message.
    pub = await client.get(f"/api/public/event/{ev['public_token']}")
    assert pub.json()["cancelled_at"] is not None
    assert pub.json()["cancellation_message"] == "Venue flooded — so sorry!"

    # New RSVPs are rejected.
    rsvp = await client.post(
        f"/api/public/rsvp/{ev['public_token']}",
        json={"guest_name": "Sam", "status": "yes"},
    )
    assert rsvp.status_code == 409

    # Host detail reflects the cancellation.
    detail = await client.get(f"/api/events/{ev['id']}", headers=headers)
    assert detail.json()["cancelled_at"] is not None


async def test_reinstate_reopens_rsvp(client, host):
    _, headers = host
    ev = await _create_event(client, headers)
    await client.post(f"/api/events/{ev['id']}/cancel", json={"message": "x"}, headers=headers)

    r = await client.post(f"/api/events/{ev['id']}/reinstate", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["cancelled_at"] is None
    assert r.json()["cancellation_message"] == ""

    # RSVP works again.
    rsvp = await client.post(
        f"/api/public/rsvp/{ev['public_token']}",
        json={"guest_name": "Sam", "status": "yes"},
    )
    assert rsvp.status_code == 200, rsvp.text


async def test_duplicate_copies_details_not_guests(client, host, png_bytes):
    _, headers = host
    ev = await _create_event(
        client, headers, "Annual Bash",
        description="Come party", location="Rooftop", theme="sunset",
        rsvp_deadline="2030-01-01T17:00:00Z",
    )
    # Add a photo, a custom question, an invite, and an RSVP to the original.
    files = {"files": ("p.png", png_bytes((800, 600)), "image/png")}
    await client.post(f"/api/events/{ev['id']}/images", files=files, headers=headers)
    await client.put(
        f"/api/events/{ev['id']}/questions",
        json={"questions": [{"prompt": "Chicken or fish?", "qtype": "choice",
                             "options": ["Chicken", "Fish"], "required": True}]},
        headers=headers,
    )
    await client.post(
        f"/api/events/{ev['id']}/invites",
        json={"emails": ["guest@example.com"], "send_email": False}, headers=headers,
    )
    await client.post(
        f"/api/public/rsvp/{ev['public_token']}",
        json={"guest_name": "Sam", "status": "yes"},
    )

    # Duplicate it.
    r = await client.post(f"/api/events/{ev['id']}/duplicate", headers=headers)
    assert r.status_code == 201, r.text
    clone = r.json()
    assert clone["title"] == "Annual Bash (copy)"
    assert clone["id"] != ev["id"]
    assert clone["public_token"] != ev["public_token"]
    assert clone["event_date"] is None          # date cleared for the new occasion
    assert clone["rsvp_deadline"] is None
    assert clone["description"] == "Come party"
    assert clone["theme"] == "sunset"
    assert clone["image_path"]                  # gallery copied (new file)
    assert clone["image_path"] != ev["image_path"]

    # The clone copies the creative work but starts fresh on people.
    detail = (await client.get(f"/api/events/{clone['id']}", headers=headers)).json()
    assert detail["invites_total"] == 0
    assert detail["rsvps_total"] == 0
    assert len(detail["images"]) == 1
    assert len(detail["questions"]) == 1
    assert detail["questions"][0]["prompt"] == "Chicken or fish?"


async def test_cohost_can_cancel_but_not_delete(client, host, register):
    _, headers = host
    ev = await _create_event(client, headers)
    # Add a co-host.
    await register(email="cohost@example.com")
    await client.post(
        f"/api/events/{ev['id']}/cohosts", json={"email": "cohost@example.com"}, headers=headers,
    )
    login = await client.post(
        "/api/auth/login", json={"email": "cohost@example.com", "password": "secret123"}
    )
    co = {"Authorization": f"Bearer {login.json()['token']}"}

    # Co-host may cancel (a management action)...
    assert (await client.post(f"/api/events/{ev['id']}/cancel", json={}, headers=co)).status_code == 200
    # ...but not delete (owner-only).
    assert (await client.delete(f"/api/events/{ev['id']}", headers=co)).status_code == 403


async def test_manage_token_cancel_and_duplicate(client):
    # Quick-create (no account) event.
    r = await client.post("/api/public/events", json={"title": "Picnic", "description": "BYO"})
    assert r.status_code == 201, r.text
    created = r.json()
    token = created["manage_token"]

    # Cancel via the manage token.
    c = await client.post(f"/api/public/manage/{token}/cancel", json={"message": "Rain"})
    assert c.status_code == 200, c.text
    assert c.json()["cancelled_at"] is not None

    # Duplicate mints a brand-new managed event with its own token.
    d = await client.post(f"/api/public/manage/{token}/duplicate")
    assert d.status_code == 201, d.text
    dup = d.json()
    assert dup["manage_token"] != token
    assert dup["event"]["title"] == "Picnic (copy)"
    # The clone is not cancelled.
    assert dup["event"]["cancelled_at"] is None
