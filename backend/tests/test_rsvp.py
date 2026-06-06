async def _quick_create(client, title="Bash"):
    r = await client.post(
        "/api/public/events",
        json={"title": title, "host_display_name": "Sam"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_quick_create_public_event_and_rsvp(client):
    qc = await _quick_create(client)
    token = qc["event"]["public_token"]

    # The public event is visible without auth.
    r = await client.get(f"/api/public/event/{token}")
    assert r.status_code == 200
    assert r.json()["title"] == "Bash"

    # Submit an RSVP via the shared link.
    r = await client.post(
        f"/api/public/rsvp/{token}",
        json={"guest_name": "Pat", "guest_email": "pat@example.com", "status": "yes", "party_size": 2},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "yes"

    # Re-submitting with the same email updates rather than duplicating.
    r = await client.post(
        f"/api/public/rsvp/{token}",
        json={"guest_name": "Pat", "guest_email": "pat@example.com", "status": "maybe"},
    )
    assert r.status_code == 200

    detail = (await client.get(f"/api/public/manage/{qc['manage_token']}")).json()
    assert detail["rsvps_total"] == 1
    assert detail["rsvps"][0]["status"] == "maybe"


async def test_invite_link_marks_viewed(client, host):
    _, headers = host
    ev = (await client.post("/api/events", json={"title": "Gala"}, headers=headers)).json()
    r = await client.post(
        f"/api/events/{ev['id']}/invites",
        json={"emails": ["g@example.com"], "send_email": False},
        headers=headers,
    )
    invite_token = r.json()["added"][0]["token"]

    # Before opening: not viewed.
    page = (await client.get(f"/api/events/{ev['id']}/invites", headers=headers)).json()
    assert page["items"][0]["viewed_at"] is None

    # Opening the personalized link stamps viewed_at.
    assert (await client.get(f"/api/public/invite/{invite_token}")).status_code == 200
    page = (await client.get(f"/api/events/{ev['id']}/invites", headers=headers)).json()
    assert page["items"][0]["viewed_at"] is not None


async def test_required_question_enforced(client):
    qc = await _quick_create(client)
    token = qc["event"]["public_token"]
    # Add a required question via manage.
    r = await client.put(
        f"/api/public/manage/{qc['manage_token']}/questions",
        json={"questions": [{"prompt": "Chicken or fish?", "qtype": "choice",
                             "options": ["Chicken", "Fish"], "required": True}]},
    )
    assert r.status_code == 200

    # A "yes" without answering the required question is rejected.
    r = await client.post(
        f"/api/public/rsvp/{token}",
        json={"guest_name": "Lee", "status": "yes"},
    )
    assert r.status_code == 422


async def test_wall_closed_by_default(client):
    qc = await _quick_create(client)
    token = qc["event"]["public_token"]
    r = await client.post(
        f"/api/public/wall/{token}",
        json={"guest_name": "Jo", "message": "Congrats!"},
    )
    assert r.status_code == 403  # wall disabled until the host enables it

    # Enable the wall, then a post succeeds.
    await client.put(
        f"/api/public/manage/{qc['manage_token']}", json={"wall_enabled": True}
    )
    r = await client.post(
        f"/api/public/wall/{token}",
        json={"guest_name": "Jo", "message": "Congrats!"},
    )
    assert r.status_code == 200


async def test_unknown_token_404(client):
    assert (await client.get("/api/public/event/nope")).status_code == 404
