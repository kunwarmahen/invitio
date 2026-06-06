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


async def test_view_beacon_tracks_opens_and_logs_ip(client, host):
    _, headers = host
    ev = (await client.post("/api/events", json={"title": "Gala"}, headers=headers)).json()
    r = await client.post(
        f"/api/events/{ev['id']}/invites",
        json={"emails": ["g@example.com"], "send_email": False},
        headers=headers,
    )
    invite_token = r.json()["added"][0]["token"]

    # Merely fetching the invite (e.g. a link-preview bot) no longer counts as a
    # view — only the browser beacon does.
    assert (await client.get(f"/api/public/invite/{invite_token}")).status_code == 200
    page = (await client.get(f"/api/events/{ev['id']}/invites", headers=headers)).json()
    assert page["items"][0]["viewed_at"] is None
    assert page["items"][0]["view_count"] == 0

    # The beacon stamps viewed_at, bumps the count, and logs the open with its IP.
    assert (await client.post(f"/api/public/view/{invite_token}")).status_code == 204
    assert (await client.post(f"/api/public/view/{invite_token}")).status_code == 204
    page = (await client.get(f"/api/events/{ev['id']}/invites", headers=headers)).json()
    assert page["items"][0]["viewed_at"] is not None
    assert page["items"][0]["view_count"] == 2

    log = (await client.get(f"/api/events/{ev['id']}/views", headers=headers)).json()
    assert log["total"] == 2
    assert log["items"][0]["guest_name"] == "" or log["items"][0]["invite_id"]
    assert log["items"][0]["ip"]  # an IP was captured

    # A public-link open is logged as anonymous (no invite).
    assert (await client.post(f"/api/public/view/{ev['public_token']}")).status_code == 204
    log = (await client.get(f"/api/events/{ev['id']}/views", headers=headers)).json()
    assert log["total"] == 3
    assert log["anonymous"] == 1


async def test_view_beacon_bad_token_is_noop(client):
    # A stale/invalid link must never surface an error to the guest.
    assert (await client.post("/api/public/view/nope-not-a-token")).status_code == 204


async def test_email_open_pixel_tracks_and_always_returns_gif(client, host):
    _, headers = host
    ev = (await client.post("/api/events", json={"title": "Gala"}, headers=headers)).json()
    r = await client.post(
        f"/api/events/{ev['id']}/invites",
        json={"emails": ["g@example.com"], "send_email": False},
        headers=headers,
    )
    invite_token = r.json()["added"][0]["token"]

    # The pixel returns a GIF and stamps the soft email-open signal (no IP).
    px = await client.get(f"/api/public/track/{invite_token}.gif")
    assert px.status_code == 200
    assert px.headers["content-type"] == "image/gif"
    assert px.content[:6] == b"GIF89a"
    await client.get(f"/api/public/track/{invite_token}.gif")

    page = (await client.get(f"/api/events/{ev['id']}/invites", headers=headers)).json()
    assert page["items"][0]["email_opened_at"] is not None
    assert page["items"][0]["email_open_count"] == 2
    # Email opens stay out of the IP'd page-view log.
    assert (await client.get(f"/api/events/{ev['id']}/views", headers=headers)).json()["total"] == 0

    # An unknown token still returns the pixel, never an error.
    bad = await client.get("/api/public/track/not-a-real-token.gif")
    assert bad.status_code == 200
    assert bad.headers["content-type"] == "image/gif"


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
