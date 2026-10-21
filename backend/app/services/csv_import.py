"""Bulk user import from the HR CSV, in two steps.

1. ``validate_csv`` checks every row and stores the clean rows on a UserImport.
2. ``commit_import`` upserts them by employee_id. It never deletes or deactivates
   anyone. New users get a one-time temporary password, returned once as CSV and
   never stored in plaintext.

Columns (spec): employee_id, full_name, branch_code, region, role, preferred_language.
``role`` is the job role (Menejer, Anderrayter, ...). Its permission level is derived;
methodologist/admin are only granted in the admin UI.
"""

from __future__ import annotations

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth import passwords
from app.errors import AppError
from app.models import AppUser, Branch, JobRole, Region, UserImport
from app.models.enums import Language
from app.services import audit, certificates, csvio
from app.services.i18n import t
from app.services.users import EMPLOYEE_ID_RE, access_role_for, normalize_employee_id

REQUIRED_COLUMNS = (
    "employee_id",
    "full_name",
    "branch_code",
    "region",
    "role",
    "preferred_language",
)
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_NAME_LENGTH = 200
_APOSTROPHES = str.maketrans({"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'", "`": "'", "´": "'"})


def normalize_key(value: str) -> str:
    """Case-, space- and apostrophe-insensitive key ("Oʻzbekiston" == "o'zbekiston")."""
    return " ".join(value.translate(_APOSTROPHES).casefold().split())


@dataclass
class ValidationResult:
    total_rows: int
    valid_rows: list[dict[str, Any]]
    errors: list[dict[str, Any]]

    @property
    def error_rows(self) -> int:
        return len({e["row"] for e in self.errors})


@dataclass
class CommitResult:
    created: int
    updated: int
    unchanged: int
    skipped: list[dict[str, Any]] = field(default_factory=list)
    temp_passwords_csv: str = ""


class _Lookups:
    def __init__(self, db: Session) -> None:
        regions = {r.id: r for r in db.scalars(select(Region))}
        self.branches = {b.code.upper(): b for b in db.scalars(select(Branch))}
        self.region_keys = {
            rid: {normalize_key(r.code), normalize_key(r.name_uz), normalize_key(r.name_ru)}
            for rid, r in regions.items()
        }
        self.region_label = {rid: r.name_uz for rid, r in regions.items()}
        self.roles: dict[str, JobRole] = {}
        for role in db.scalars(select(JobRole)):
            for key in (role.code, role.name_uz, role.name_ru):
                self.roles[normalize_key(key)] = role


def template_csv() -> str:
    return csvio.to_csv(REQUIRED_COLUMNS, [])


def validate_csv(db: Session, data: bytes) -> ValidationResult:
    if len(data) > MAX_FILE_BYTES:
        raise AppError(413, "import.file_too_large", {"max_mb": MAX_FILE_BYTES // (1024 * 1024)})
    text = csvio.decode(data)
    header_line = next((line for line in text.splitlines() if line.strip()), "")
    if not header_line:
        raise AppError(400, "import.empty")
    reader = csv.reader(
        io.StringIO(text), delimiter=csvio.detect_delimiter(header_line, REQUIRED_COLUMNS)
    )
    header = next((row for row in reader if any(cell.strip() for cell in row)), None)
    if header is None:
        raise AppError(400, "import.empty")
    index: dict[str, int] = {}
    for i, name in enumerate(header):
        index.setdefault(csvio.normalize_header(name), i)
    missing = [col for col in REQUIRED_COLUMNS if col not in index]
    if missing:
        raise AppError(400, "import.missing_columns", {"columns": missing})

    lookups = _Lookups(db)
    first_seen: dict[str, int] = {}
    valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total = 0

    for raw in reader:
        if not any(cell.strip() for cell in raw):
            continue
        total += 1
        row_no = reader.line_num  # physical line, header = 1 (what Excel shows)

        cells = {col: (raw[i].strip() if i < len(raw) else "") for col, i in index.items()}
        problems: list[tuple[str, dict[str, Any]]] = []

        emp_raw = cells["employee_id"]
        emp = normalize_employee_id(emp_raw)
        if not emp:
            problems.append(("employee_id_empty", {}))
        elif not EMPLOYEE_ID_RE.match(emp):
            problems.append(("employee_id_invalid", {"value": emp_raw}))
        elif emp in first_seen:
            problems.append(("employee_id_duplicate", {"first_row": first_seen[emp]}))
        else:
            first_seen[emp] = row_no

        full_name = " ".join(cells["full_name"].split())
        if not full_name:
            problems.append(("full_name_empty", {}))
        elif len(full_name) > MAX_NAME_LENGTH:
            problems.append(("full_name_too_long", {}))

        branch_code = cells["branch_code"].upper()
        branch = lookups.branches.get(branch_code) if branch_code else None
        if not branch_code:
            problems.append(("branch_code_empty", {}))
        elif branch is None:
            problems.append(("branch_not_found", {"code": branch_code}))

        region_raw = cells["region"]
        if not region_raw:
            problems.append(("region_empty", {}))
        elif branch is not None and normalize_key(region_raw) not in lookups.region_keys.get(
            branch.region_id, set()
        ):
            problems.append(
                (
                    "region_mismatch",
                    {"value": region_raw, "expected": lookups.region_label[branch.region_id]},
                )
            )

        role_raw = cells["role"]
        role = lookups.roles.get(normalize_key(role_raw)) if role_raw else None
        if not role_raw:
            problems.append(("role_empty", {}))
        elif role is None:
            problems.append(("role_unknown", {"value": role_raw}))

        lang_raw = cells["preferred_language"]
        lang = lang_raw.lower() or Language.uz.value
        if lang not in (Language.uz.value, Language.ru.value):
            problems.append(("language_invalid", {"value": lang_raw}))

        if problems:
            errors.extend(
                {"row": row_no, "employee_id": emp or None, "code": code, "params": params}
                for code, params in problems
            )
        else:
            valid.append(
                {
                    "row": row_no,
                    "employee_id": emp,
                    "full_name": full_name,
                    "branch_code": branch_code,
                    "job_role_code": role.code,
                    "preferred_language": lang,
                }
            )

    return ValidationResult(total_rows=total, valid_rows=valid, errors=errors)


def count_existing(db: Session, employee_ids: list[str]) -> int:
    if not employee_ids:
        return 0
    return len(
        db.scalars(select(AppUser.employee_id).where(AppUser.employee_id.in_(employee_ids))).all()
    )


def errors_csv(imp: UserImport, lang: Language) -> str:
    header = [t(lang, "csv.row"), t(lang, "csv.employee_id"), t(lang, "csv.problem")]
    rows = [
        [e["row"], e["employee_id"] or "", t(lang, f"import.{e['code']}", **e["params"])]
        for e in imp.errors
    ]
    return csvio.to_csv(header, rows)


def commit_import(db: Session, imp: UserImport, actor: AppUser, lang: Language) -> CommitResult:
    """Upsert the validated rows. The caller holds a row lock on ``imp`` and commits."""
    if imp.committed_at is not None:
        raise AppError(409, "import.already_committed")

    lookups = _Lookups(db)
    ids = [row["employee_id"] for row in imp.valid_rows]
    existing = {
        u.employee_id: u for u in db.scalars(select(AppUser).where(AppUser.employee_id.in_(ids)))
    }
    result = CommitResult(created=0, updated=0, unchanged=0)
    new_rows: list[tuple[dict[str, Any], Branch, JobRole]] = []
    reassigned: list[int] = []  # branch or job role changed: assignments may differ

    for row in imp.valid_rows:
        branch = lookups.branches.get(row["branch_code"])
        role = lookups.roles.get(normalize_key(row["job_role_code"]))
        if branch is None or role is None:  # reference data changed since validation
            code, params = (
                ("branch_not_found", {"code": row["branch_code"]})
                if branch is None
                else ("role_unknown", {"value": row["job_role_code"]})
            )
            result.skipped.append(
                {
                    "row": row["row"],
                    "employee_id": row["employee_id"],
                    "code": code,
                    "params": params,
                }
            )
            continue
        user = existing.get(row["employee_id"])
        if user is None:
            new_rows.append((row, branch, role))
            continue
        changes = _apply_update(user, row, branch, role)
        if {"branch_id", "job_role_id"} & changes.keys():
            reassigned.append(user.id)
        if changes:
            result.updated += 1
            audit.record(
                db,
                "user.updated",
                actor_id=actor.id,
                target_user_id=user.id,
                data={"source": "csv", "import_id": imp.id, "changes": changes},
            )
        else:
            result.unchanged += 1

    temp_passwords = [passwords.generate_temp_password() for _ in new_rows]
    # argon2 releases the GIL, so a few threads cut a large first import to seconds.
    with ThreadPoolExecutor(max_workers=4) as pool:
        hashes = list(pool.map(passwords.hash_temp_password, temp_passwords))

    created: list[tuple[AppUser, str, Branch]] = []
    rows = zip(new_rows, temp_passwords, hashes, strict=True)
    for (row, branch, role), temp, password_hash in rows:
        user = AppUser(
            employee_id=row["employee_id"],
            full_name=row["full_name"],
            branch_id=branch.id,
            job_role_id=role.id,
            access_role=access_role_for(role),
            preferred_language=Language(row["preferred_language"]),
            password_hash=password_hash,
            must_change_password=True,
        )
        db.add(user)
        created.append((user, temp, branch))
    db.flush()
    for user, _, _ in created:
        audit.record(
            db,
            "user.created",
            actor_id=actor.id,
            target_user_id=user.id,
            data={"source": "csv", "import_id": imp.id},
        )
    result.created = len(created)

    certificates.enqueue_evaluation(db, reassigned, actor.id)
    imp.committed_at = clock.utcnow()
    imp.created_count = result.created
    imp.updated_count = result.updated
    audit.record(
        db,
        "user.import",
        actor_id=actor.id,
        entity="user_import",
        entity_id=imp.id,
        data={
            "filename": imp.filename,
            "created": result.created,
            "updated": result.updated,
            "unchanged": result.unchanged,
            "skipped": len(result.skipped),
        },
    )

    name_attr = "name_ru" if lang == Language.ru else "name_uz"
    created.sort(key=lambda item: (item[2].code, item[0].full_name))
    result.temp_passwords_csv = csvio.to_csv(
        [
            t(lang, "csv.employee_id"),
            t(lang, "csv.full_name"),
            t(lang, "csv.branch_code"),
            t(lang, "csv.branch"),
            t(lang, "csv.temp_password"),
        ],
        [
            [u.employee_id, u.full_name, b.code, getattr(b, name_attr), temp]
            for u, temp, b in created
        ],
    )
    return result


def _apply_update(
    user: AppUser, row: dict[str, Any], branch: Branch, role: JobRole
) -> dict[str, list[str]]:
    changes: dict[str, list[str]] = {}
    new_values: dict[str, Any] = {
        "full_name": row["full_name"],
        "branch_id": branch.id,
        "job_role_id": role.id,
        "preferred_language": Language(row["preferred_language"]),
        "access_role": access_role_for(role, user.access_role),
    }
    for attr, new in new_values.items():
        old = getattr(user, attr)
        if old != new:
            changes[attr] = [str(old), str(new)]
            setattr(user, attr, new)
    return changes
