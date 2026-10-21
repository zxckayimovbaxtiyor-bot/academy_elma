from __future__ import annotations

from app.auth.sessions import COOKIE_NAME
from app.models.enums import AccessRole
from tests.factories import PASSWORD, error_code, login, make_user

ME = "/api/v1/auth/me"
CHANGE = "/api/v1/auth/change-password"
ADMIN_USERS = "/api/v1/admin/users"


def test_login_sets_session_cookie_and_returns_profile(db, client, reference):
    user = make_user(db, branch=reference.tashkent, job_role=reference.roles["menejer"])
    resp = login(client, user)
    assert resp.status_code == 200
    assert resp.json()["employee_id"] == user.employee_id
    assert resp.json()["branch"]["code"] == "01-101"
    assert resp.json()["region"]["code"] == "01"
    cookie = resp.headers["set-cookie"]
    assert COOKIE_NAME in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert client.get(ME).status_code == 200


def test_login_is_case_insensitive_on_employee_id(db, client):
    user = make_user(db, employee_id="XB-100231")
    assert login(client, "xb-100231").status_code == 200
    assert user.last_seen_at is not None


def test_wrong_password_unknown_user_and_inactive_user_look_the_same(db, client):
    user = make_user(db)
    inactive = make_user(db, is_active=False)
    for resp in (
        login(client, user, "wrong-password"),
        login(client, "NOBODY-1"),
        login(client, inactive),
    ):
        assert resp.status_code == 401
        assert error_code(resp) == "auth.invalid_credentials"


def test_account_locks_after_five_failures_and_unlocks_after_fifteen_minutes(db, client, clock):
    user = make_user(db)
    for _ in range(5):
        assert login(client, user, "wrong").status_code == 401
    locked = login(client, user)  # even the right password is refused while locked
    assert locked.status_code == 403
    assert error_code(locked) == "auth.locked"
    clock.advance(minutes=14)
    assert login(client, user).status_code == 403
    clock.advance(minutes=2)
    assert login(client, user).status_code == 200


def test_successful_login_resets_failure_counter(db, client):
    user = make_user(db)
    for _ in range(4):
        login(client, user, "wrong")
    assert login(client, user).status_code == 200
    for _ in range(4):
        login(client, user, "wrong")
    assert login(client, user).status_code == 200


def test_temporary_password_must_be_changed_before_anything_else(db, client):
    admin = make_user(db, role=AccessRole.admin, must_change=True)
    assert login(client, admin).status_code == 200
    assert client.get(ME).json()["must_change_password"] is True
    blocked = client.get(ADMIN_USERS)
    assert blocked.status_code == 403
    assert error_code(blocked) == "auth.password_change_required"
    resp = client.post(CHANGE, json={"current_password": PASSWORD, "new_password": "Yangi-parol-1"})
    assert resp.status_code == 204
    assert client.get(ADMIN_USERS).status_code == 200


def test_change_password_rules(db, client):
    user = make_user(db, employee_id="XB-555555")
    login(client, user)
    cases = [
        (("wrong", "Yangi-parol-1"), "password.current_invalid"),
        ((PASSWORD, "short"), "password.too_short"),
        ((PASSWORD, "xb-555555"), "password.equals_employee_id"),
        ((PASSWORD, PASSWORD), "password.same_as_current"),
    ]
    for (current, new), code in cases:
        resp = client.post(CHANGE, json={"current_password": current, "new_password": new})
        assert resp.status_code == 400, code
        assert error_code(resp) == code


def test_changing_password_signs_out_other_sessions(db, client, make_client):
    user = make_user(db)
    other = make_client()
    login(client, user)
    login(other, user)
    resp = client.post(CHANGE, json={"current_password": PASSWORD, "new_password": "Yangi-parol-1"})
    assert resp.status_code == 204
    assert client.get(ME).status_code == 200
    assert other.get(ME).status_code == 401


def test_logout_ends_the_session(db, client):
    login(client, make_user(db))
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get(ME).status_code == 401


def test_session_expires_after_idle_hour_but_activity_keeps_it_alive(db, client, clock):
    login(client, make_user(db))
    clock.advance(minutes=50)
    assert client.get(ME).status_code == 200
    clock.advance(minutes=50)
    assert client.get(ME).status_code == 200  # 100 min since login, 50 since last use
    clock.advance(minutes=61)
    resp = client.get(ME)
    assert resp.status_code == 401
    assert error_code(resp) == "auth.required"


def test_session_has_an_absolute_twelve_hour_limit(db, client, clock):
    login(client, make_user(db))
    for _ in range(14):  # active every 50 minutes for 11h40m
        clock.advance(minutes=50)
        assert client.get(ME).status_code == 200
    clock.advance(minutes=21)
    assert client.get(ME).status_code == 401


def test_writes_require_the_csrf_header(db, make_client):
    bare = make_client(csrf=False)
    resp = bare.post("/api/v1/auth/login", json={"username": "x", "password": "y"})
    assert resp.status_code == 403
    assert error_code(resp) == "auth.csrf"


def test_admin_endpoints_are_admin_only(db, client, make_client, reference):
    for role in (AccessRole.learner, AccessRole.branch_head, AccessRole.methodologist):
        c = make_client()
        login(c, make_user(db, role=role, branch=reference.tashkent))
        resp = c.get(ADMIN_USERS)
        assert resp.status_code == 403, role
        assert error_code(resp) == "auth.forbidden"
    login(client, make_user(db, role=AccessRole.admin))
    assert client.get(ADMIN_USERS).status_code == 200


def test_unauthenticated_requests_get_401(client):
    resp = client.get(ADMIN_USERS)
    assert resp.status_code == 401
    assert error_code(resp) == "auth.required"


def test_language_can_be_switched(db, client):
    login(client, make_user(db))
    resp = client.patch(ME, json={"preferred_language": "ru"})
    assert resp.status_code == 200
    assert client.get(ME).json()["preferred_language"] == "ru"


def test_media_auth_requires_a_valid_session(db, client):
    assert client.get("/api/v1/internal/media-auth").status_code == 401
    login(client, make_user(db))
    # Authentication alone is insufficient: nginx must identify the requested file.
    assert client.get("/api/v1/internal/media-auth").status_code == 403


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
