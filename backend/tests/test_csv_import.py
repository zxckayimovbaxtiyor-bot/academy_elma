from __future__ import annotations

from sqlalchemy import select

from app.models import AppUser, AuditEvent
from app.models.enums import AccessRole
from tests.factories import error_code, login, make_user

IMPORT = "/api/v1/admin/users/import"
HEADER = "employee_id;full_name;branch_code;region;role;preferred_language"


def _csv(*rows: str, header: str = HEADER, bom: bool = True) -> bytes:
    text = "\r\n".join([header, *rows]) + "\r\n"
    return ("﻿" if bom else "").encode() + text.encode("utf-8")


def _admin(db, client):
    admin = make_user(db, role=AccessRole.admin)
    login(client, admin)
    return admin


def _upload(client, data: bytes, filename: str = "xodimlar.csv"):
    return client.post(
        IMPORT, params={"filename": filename}, content=data, headers={"Content-Type": "text/csv"}
    )


def test_valid_file_with_bom_and_semicolons(db, client, reference):
    _admin(db, client)
    data = _csv(
        "XB-100231;Dilnoza Rahimova;01-101;Toshkent shahri;Menejer;uz",
        "xb-100232;  Sardor   Tursunov ;01-101;город Ташкент;menejer;RU",
        "XB-100233;Elena Kim;11-101;11;Anderrayter;",
    )
    resp = _upload(client, data)
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert (report["total_rows"], report["valid_rows"], report["error_rows"]) == (3, 3, 0)
    assert (report["to_create"], report["to_update"]) == (3, 0)


def test_windows_1251_with_commas_and_russian_role_names(db, client, reference):
    _admin(db, client)
    text = (
        "employee_id,full_name,branch_code,region,role,preferred_language\r\n"
        "XB-200001,Ольга Пак,11-101,Самаркандская область,Андеррайтер,ru\r\n"
    )
    resp = _upload(client, text.encode("cp1251"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["valid_rows"] == 1


def test_region_matching_ignores_case_spaces_and_apostrophe_style(db, client, reference):
    _admin(db, client)
    resp = _upload(client, _csv("XB-1;Ali Valiyev;01-101;  toshkent   SHAHRI ;Filial rahbari;uz"))
    assert resp.json()["valid_rows"] == 1


def test_missing_columns_rejects_the_whole_file(db, client, reference):
    _admin(db, client)
    resp = _upload(client, _csv("XB-1;Ali", header="employee_id;full_name"))
    assert resp.status_code == 400
    assert error_code(resp) == "import.missing_columns"
    assert resp.json()["error"]["params"]["columns"] == [
        "branch_code", "region", "role", "preferred_language",
    ]  # fmt: skip


def test_empty_and_oversized_files(db, client, reference):
    _admin(db, client)
    assert error_code(_upload(client, b"   \r\n")) == "import.empty"
    resp = _upload(client, b"x" * (5 * 1024 * 1024 + 1))
    assert resp.status_code == 413
    assert error_code(resp) == "import.file_too_large"


def test_every_row_problem_is_reported_with_its_line_number(db, client, reference):
    _admin(db, client)
    data = _csv(
        "XB-1;Ali Valiyev;01-101;Toshkent shahri;Menejer;uz",  # line 2: valid
        ";Bo'sh ID;01-101;Toshkent shahri;Menejer;uz",  # 3
        "XB-1;Takror;01-101;Toshkent shahri;Menejer;uz",  # 4: duplicate of line 2
        "XB 3;Probel;01-101;Toshkent shahri;Menejer;uz",  # 5: invalid id
        "XB-4;;01-101;Toshkent shahri;Menejer;uz",  # 6
        "XB-5;Filialsiz;01-117;Toshkent shahri;Menejer;uz",  # 7
        "XB-6;Hududsiz;01-101;;Menejer;uz",  # 8
        "XB-7;Boshqa hudud;01-101;Samarqand viloyati;Menejer;uz",  # 9
        "XB-8;Kassir;01-101;Toshkent shahri;Kassir;uz",  # 10
        "XB-9;Tilsiz;01-101;Toshkent shahri;Menejer;en",  # 11
        "XB-10;Rolsiz;01-101;Toshkent shahri;;uz",  # 12
    )
    report = _upload(client, data).json()
    got = {(e["row"], e["code"]) for e in report["errors"]}
    assert got == {
        (3, "employee_id_empty"),
        (4, "employee_id_duplicate"),
        (5, "employee_id_invalid"),
        (6, "full_name_empty"),
        (7, "branch_not_found"),
        (8, "region_empty"),
        (9, "region_mismatch"),
        (10, "role_unknown"),
        (11, "language_invalid"),
        (12, "role_empty"),
    }
    dup = next(e for e in report["errors"] if e["code"] == "employee_id_duplicate")
    assert dup["params"] == {"first_row": 2}
    assert (report["total_rows"], report["valid_rows"], report["error_rows"]) == (11, 1, 10)


def test_error_report_csv_in_both_languages(db, client, reference):
    _admin(db, client)
    data = _csv(
        "XB-1;Kassir;01-101;Toshkent shahri;Kassir;uz",
        "XB-2;Filialsiz;01-117;Toshkent shahri;Menejer;uz",
    )
    import_id = _upload(client, data).json()["import_id"]
    uz = client.get(f"{IMPORT}/{import_id}/errors.csv", params={"lang": "uz"})
    assert uz.headers["content-type"].startswith("text/csv")
    body = uz.content.decode("utf-8-sig")
    assert "Qator;employee_id;Muammo" in body
    assert "Rol nomaʼlum: «Kassir»" in body
    assert "Filial kodi topilmadi: 01-117" in body
    ru = client.get(f"{IMPORT}/{import_id}/errors.csv", params={"lang": "ru"}).content
    assert "Неизвестная роль: «Kassir»" in ru.decode("utf-8-sig")


def test_commit_creates_users_with_one_time_passwords(db, client, make_client, reference):
    _admin(db, client)
    data = _csv(
        "XB-100231;Dilnoza Rahimova;01-101;Toshkent shahri;Menejer;uz",
        "XB-100240;Malika Ergasheva;01-101;Toshkent shahri;Filial rahbari;ru",
        "XB-100241;Kassir;01-101;Toshkent shahri;Kassir;uz",  # error row: skipped
    )
    import_id = _upload(client, data).json()["import_id"]
    resp = client.post(f"{IMPORT}/{import_id}/commit")
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert (result["created"], result["updated"], result["unchanged"]) == (2, 0, 0)

    rows = db.scalars(select(AppUser).where(AppUser.employee_id.like("XB-1002%")))
    users = {u.employee_id: u for u in rows}
    assert set(users) == {"XB-100231", "XB-100240"}
    assert users["XB-100231"].access_role == AccessRole.learner
    assert users["XB-100240"].access_role == AccessRole.branch_head  # derived from job role
    assert all(u.must_change_password for u in users.values())

    lines = result["temp_passwords_csv"].lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("employee_id;F.I.Sh.;Filial kodi;Filial;")
    temp = {line.split(";")[0]: line.split(";")[-1] for line in lines[1:]}
    learner = make_client()
    assert login(learner, "XB-100231", temp["XB-100231"]).status_code == 200
    assert learner.get("/api/v1/auth/me").json()["must_change_password"] is True

    created_events = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "user.created",
                                 AuditEvent.target_user_id == users["XB-100231"].id)
    ).all()  # fmt: skip
    assert len(created_events) == 1


def test_reimport_updates_but_never_deletes_or_touches_staff_roles(db, client, reference):
    _admin(db, client)
    methodologist = make_user(db, role=AccessRole.methodologist, employee_id="XB-9")
    first = _csv(
        "XB-1;Ali Valiyev;01-101;Toshkent shahri;Menejer;uz",
        "XB-2;Vali Aliyev;01-101;Toshkent shahri;Menejer;uz",
    )
    client.post(f"{IMPORT}/{_upload(client, first).json()['import_id']}/commit")

    second = _csv(
        "XB-1;Ali Valiyev;11-101;Samarqand viloyati;Filial rahbari;ru",  # moved + promoted
        "XB-9;Metodist Ismi;01-101;Toshkent shahri;Menejer;uz",  # staff role stays
    )
    report = _upload(client, second).json()
    assert (report["to_create"], report["to_update"]) == (0, 2)
    result = client.post(f"{IMPORT}/{report['import_id']}/commit").json()
    assert (result["created"], result["updated"]) == (0, 2)
    assert result["temp_passwords_csv"].lstrip("﻿").strip().count("\n") == 0  # header only

    ali = db.scalar(select(AppUser).where(AppUser.employee_id == "XB-1"))
    assert ali.branch_id == reference.samarqand.id
    assert ali.access_role == AccessRole.branch_head
    assert db.scalar(select(AppUser).where(AppUser.employee_id == "XB-2")) is not None
    db.refresh(methodologist)
    assert methodologist.access_role == AccessRole.methodologist


def test_import_cannot_be_committed_twice(db, client, reference):
    _admin(db, client)
    import_id = _upload(client, _csv("XB-1;Ali Valiyev;01-101;Toshkent shahri;Menejer;uz")).json()[
        "import_id"
    ]
    assert client.post(f"{IMPORT}/{import_id}/commit").status_code == 200
    again = client.post(f"{IMPORT}/{import_id}/commit")
    assert again.status_code == 409
    assert error_code(again) == "import.already_committed"


def test_template_has_the_spec_columns(db, client, reference):
    _admin(db, client)
    resp = client.get(f"{IMPORT}/template.csv")
    assert resp.content.decode("utf-8-sig").strip() == HEADER


def test_import_is_admin_only(db, client, reference):
    login(client, make_user(db, role=AccessRole.methodologist))
    assert _upload(client, _csv()).status_code == 403


def test_moving_people_queues_an_operator_certificate_check(db, client, reference):
    from app.models import Job
    from app.models.enums import JobKind

    _admin(db, client)
    first = _csv(
        "XB-100231;Dilnoza Rahimova;01-101;Toshkent shahri;Menejer;uz",
        "XB-100232;Sardor Tursunov;01-101;Toshkent shahri;Menejer;uz",
    )
    client.post(f"{IMPORT}/{_upload(client, first).json()['import_id']}/commit")
    assert db.scalar(select(Job).where(Job.kind == JobKind.operator_cert_eval)) is None
    moved = _csv(
        "XB-100231;Dilnoza Rahimova;11-101;11;Menejer;uz",  # new branch
        "XB-100232;Sardor Tursunov;01-101;Toshkent shahri;Menejer;ru",  # language only
    )
    client.post(f"{IMPORT}/{_upload(client, moved).json()['import_id']}/commit")
    job = db.scalar(select(Job).where(Job.kind == JobKind.operator_cert_eval))
    dilnoza = db.scalar(select(AppUser).where(AppUser.employee_id == "XB-100231"))
    assert job.payload == {"user_ids": [dilnoza.id]}
