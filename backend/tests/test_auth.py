async def test_signup_login_and_me(client):
    r = await client.post(
        "/api/auth/signup",
        json={"email": "A@Example.com", "password": "secret123", "name": "Ann"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["user"]["email"] == "a@example.com"  # normalised

    # Login with the same credentials.
    r = await client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": "secret123"}
    )
    assert r.status_code == 200

    # /me echoes the authenticated user.
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["name"] == "Ann"


async def test_duplicate_signup_conflicts(client, register):
    assert (await register(email="dup@example.com")).status_code == 200
    r = await register(email="dup@example.com")
    assert r.status_code == 409


async def test_login_wrong_password(client, register):
    await register(email="x@example.com", password="rightpass")
    r = await client.post(
        "/api/auth/login", json={"email": "x@example.com", "password": "wrongpass"}
    )
    assert r.status_code == 401


async def test_me_requires_auth(client):
    assert (await client.get("/api/auth/me")).status_code in (401, 403)
