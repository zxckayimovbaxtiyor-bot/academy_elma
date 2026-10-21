from __future__ import annotations

from app.models.enums import AccessRole
from tests.factories import PASSWORD, error_code, login, make_user

USERS = "/api/v1/admin/users"


def test_list_search_filter_and_paginate(db, client, reference):
    login(client, make_user(db, role=AccessRole.admin, full_name="Admin Adminov"))
    make_user(db, employee_id="XB-100231", full_name="Dilnoza Rahimova", branch=reference.tashkent)
    make_user(db, employee_id="XB-100877", full_name="Sardor Tursunov", branch=reference.tashkent)
    make_user(db, employee_id="XB-101540", full_name="Elena Kim", branch=reference.samarqand)

    by_name = client.get(USERS, params={"q": "rahim"}).json()
    assert [u["employee_id"] for u in by_name["items"]] == ["XB-100231"]
    by_id = client.get(USERS, params={"q": "1015"}).json()
    assert [u["full_name"] for u in by_id["items"]] == ["Elena Kim"]
    in_branch = client.get(USERS, params={"branch_id": reference.tashkent.id}).json()
    assert in_branch["total"] == 2
    page = client.get(USERS, params={"page": 2, "page_size": 2}).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    assert client.get(USERS, params={"q": "%"}).json()["total"] == 0  # wildcards are literal


def test_change_role_is_audited(db, client):
    admin = make_user(db, role=AccessRole.admin)
    target = make_user(db)
    login(client, admin)
    resp = client.patch(f"{USERS}/{target.id}", json={"access_role": "methodologist"})
    assert resp.status_code == 200
    assert resp.json()["access_role"] == "methodologist"
    detail = client.get(f"{USERS}/{target.id}").json()
    event = detail["audit"][0]
    assert event["action"] == "user.role_changed"
    assert event["actor_id"] == admin.id
    assert event["data"] == {"from": "learner", "to": "methodologist"}


def test_branch_head_needs_a_branch_and_admin_cannot_demote_self(db, client):
    admin = make_user(db, role=AccessRole.admin)
    no_branch = make_user(db)
    login(client, admin)
    resp = client.patch(f"{USERS}/{no_branch.id}", json={"access_role": "branch_head"})
    assert error_code(resp) == "user.branch_required"
    for body in ({"access_role": "learner"}, {"is_active": False}):
        resp = client.patch(f"{USERS}/{admin.id}", json=body)
        assert resp.status_code == 400
        assert error_code(resp) == "user.cannot_modify_self"


def test_deactivation_ends_sessions_and_blocks_login(db, client, make_client):
    target = make_user(db)
    browser = make_client()
    login(browser, target)
    login(client, make_user(db, role=AccessRole.admin))
    assert client.patch(f"{USERS}/{target.id}", json={"is_active": False}).status_code == 200
    assert browser.get("/api/v1/auth/me").status_code == 401
    assert login(make_client(), target).status_code == 401


def test_reset_password_unlocks_and_forces_a_change(db, client, make_client):
    target = make_user(db)
    for _ in range(5):
        login(make_client(), target, "wrong")
    login(client, make_user(db, role=AccessRole.admin))
    resp = client.post(f"{USERS}/{target.id}/reset-password")
    assert resp.status_code == 200
    temp = resp.json()["temp_password"]
    assert len(temp) == 10

    browser = make_client()
    assert login(browser, target, PASSWORD).status_code == 401  # old password is gone
    assert login(browser, target, temp).status_code == 200  # and the lock was cleared
    assert browser.get(USERS).status_code == 403
    actions = [e["action"] for e in client.get(f"{USERS}/{target.id}").json()["audit"]]
    assert "user.password_reset" in actions


def test_unknown_user_is_404(db, client):
    login(client, make_user(db, role=AccessRole.admin))
    resp = client.get(f"{USERS}/999999")
    assert resp.status_code == 404
    assert error_code(resp) == "user.not_found"


def test_reference_lists(db, client, reference):
    login(client, make_user(db, role=AccessRole.admin))
    roles = client.get("/api/v1/admin/job-roles").json()
    assert [r["code"] for r in roles][-1] == "filial_rahbari"
    assert next(r for r in roles if r["code"] == "filial_rahbari")["is_branch_head"] is True
    assert len(client.get("/api/v1/admin/regions").json()) == 14
    assert {b["code"] for b in client.get("/api/v1/admin/branches").json()} == {"01-101", "11-101"}
