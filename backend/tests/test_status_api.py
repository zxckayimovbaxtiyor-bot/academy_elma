"""Access gate (rule 13): GET /certification-status behind X-API-Key."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models.enums import AccessRole
from app.services import certificates
from tests.factories import (
    give_certificate,
    make_learner,
    make_live_lesson,
    make_user,
    make_wave,
)

URL = "/api/v1/certification-status"
KEY = "gate-key-1"


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr("app.config.settings.cert_status_api_keys", (KEY, "gate-key-2"))


def _get(client, employee_id: str, key: str | None = KEY):
    headers = {"X-API-Key": key} if key is not None else {}
    return client.get(URL, params={"employee_id": employee_id}, headers=headers)


def test_a_valid_api_key_is_required(db, client, reference, keys):
    learner = make_learner(db, reference)
    missing = _get(client, learner.employee_id, key=None)
    assert missing.status_code == 401 and missing.json()["error"]["code"] == "api_key.invalid"
    assert _get(client, learner.employee_id, key="wrong").status_code == 401
    assert _get(client, learner.employee_id, key="").status_code == 401
    assert _get(client, learner.employee_id, key="gate-key-2").status_code == 200


def test_no_configured_keys_means_no_access(db, client, reference, monkeypatch):
    monkeypatch.setattr("app.config.settings.cert_status_api_keys", ())
    learner = make_learner(db, reference)
    assert _get(client, learner.employee_id, key="anything").status_code == 401


def test_status_per_module_and_for_the_operator_certificate(db, client, reference, keys, clock):
    core, farovon = reference.modules["CORE"], reference.modules["FAROVON"]
    uzcard = reference.modules["UZCARD"]
    make_wave(db, [reference.tashkent], {reference.roles["menejer"]: [farovon]})
    for module in (core, farovon):
        make_live_lesson(db, module)
    learner = make_learner(db, reference)
    core_cert = give_certificate(db, learner, core)
    farovon_cert = give_certificate(db, learner, farovon)
    operator = certificates.evaluate_operator(db, learner, clock.now)

    body = _get(client, learner.employee_id.lower()).json()  # ids are case-insensitive
    assert body["employee_id"] == learner.employee_id and body["is_active"] is True
    assert body["operator"] == {
        "status": "valid", "number": operator.number,
        "issued_at": operator.issued_at.isoformat().replace("+00:00", "Z"), "recert_due_at": None,
    }  # fmt: skip
    modules = {m["code"]: m for m in body["modules"]}
    assert "FAQ" not in modules
    assert (modules["CORE"]["assigned"], modules["CORE"]["status"]) == (True, "valid")
    assert modules["CORE"]["number"] == core_cert.number
    assert (modules["UZCARD"]["assigned"], modules["UZCARD"]["status"]) == (False, "missing")
    assert modules["UZCARD"]["number"] is None and uzcard.code == "UZCARD"

    # A release with a 7-day transition: still valid, with the date announced...
    farovon_cert.recert_due_at = clock.now + timedelta(days=7)
    db.flush()
    body = _get(client, learner.employee_id).json()
    farovon_row = next(m for m in body["modules"] if m["code"] == "FAROVON")
    assert farovon_row["status"] == "valid" and farovon_row["recert_due_at"]
    assert body["operator"]["status"] == "valid" and body["operator"]["recert_due_at"]
    # ...and recert_required once the date has passed.
    clock.advance(days=7)
    body = _get(client, learner.employee_id).json()
    assert next(m for m in body["modules"] if m["code"] == "FAROVON")["status"] == (
        "recert_required"
    )
    assert body["operator"]["status"] == "recert_required"
    assert next(m for m in body["modules"] if m["code"] == "CORE")["status"] == "valid"


def test_learner_without_certificates(db, client, reference, keys):
    learner = make_learner(db, reference)
    body = _get(client, learner.employee_id).json()
    assert body["operator"] == {
        "status": "missing", "number": None, "issued_at": None, "recert_due_at": None,
    }  # fmt: skip
    assert {m["status"] for m in body["modules"]} == {"missing"}
    assert {m["assigned"] for m in body["modules"]} == {False}  # branch in no wave


def test_unknown_employee_is_404(client, reference, keys):
    resp = _get(client, "XB-999999")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "user.not_found"


def test_the_gate_is_read_only(db, client, reference, keys):
    learner = make_learner(db, reference)
    headers = {"X-API-Key": KEY}
    params = {"employee_id": learner.employee_id}
    for method in ("post", "put", "patch", "delete"):
        resp = getattr(client, method)(URL, params=params, headers=headers)
        assert resp.status_code == 405, method


def test_session_login_does_not_open_the_gate(db, client, reference, keys):
    from tests.factories import login

    admin = make_user(db, role=AccessRole.admin)
    login(client, admin)
    resp = client.get(URL, params={"employee_id": admin.employee_id})
    assert resp.status_code == 401  # only the API key counts
