from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import clock
from app.api.common import body_reader, csv_response
from app.api.reports import learner_detail_out
from app.auth import sessions
from app.auth.deps import require_roles
from app.db import get_db
from app.errors import AppError, not_found
from app.models import AppUser, AuditEvent, Branch, Module, UserImport
from app.models.enums import AccessRole, Language, ModuleType
from app.schemas.common import Page
from app.schemas.users import (
    AttemptResetIn,
    AttemptResetOut,
    AuditOut,
    ImportCommitOut,
    ImportProblem,
    ImportReport,
    TempPasswordOut,
    UserDetail,
    UserPatchIn,
    UserRow,
)
from app.services import attempts, audit, csv_import
from app.services.users import issue_temp_password

router = APIRouter(prefix="/admin/users", tags=["admin: users"])
admin_only = require_roles()
read_csv = body_reader(csv_import.MAX_FILE_BYTES, "import.file_too_large", admin_only)


def _like(term: str) -> str:
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _get_user(db: Session, user_id: int) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise not_found("user")
    return user


@router.get("", response_model=Page[UserRow])
def list_users(
    q: str | None = Query(None, max_length=100),
    branch_id: int | None = None,
    access_role: AccessRole | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AppUser = Depends(admin_only),
) -> Page[UserRow]:
    stmt = select(AppUser)
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                AppUser.employee_id.ilike(pattern, escape="\\"),
                AppUser.full_name.ilike(pattern, escape="\\"),
            )
        )
    if branch_id is not None:
        stmt = stmt.where(AppUser.branch_id == branch_id)
    if access_role is not None:
        stmt = stmt.where(AppUser.access_role == access_role)
    if is_active is not None:
        stmt = stmt.where(AppUser.is_active == is_active)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    users = db.scalars(
        stmt.options(
            selectinload(AppUser.branch).selectinload(Branch.region),
            selectinload(AppUser.job_role),
        )
        .order_by(AppUser.full_name, AppUser.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=[UserRow.of(u) for u in users], total=total, page=page, page_size=page_size)


# --- CSV import (declared before /{user_id} routes) -------------------------------


@router.get("/import/template.csv")
def import_template(_: AppUser = Depends(admin_only)) -> Response:
    return csv_response(csv_import.template_csv(), "users_template.csv")


@router.post("/import", response_model=ImportReport)
def import_validate(
    data: bytes = Depends(read_csv),
    filename: str = Query("import.csv", max_length=255),
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
) -> ImportReport:
    result = csv_import.validate_csv(db, data)
    imp = UserImport(
        uploaded_by=actor.id,
        filename=filename,
        total_rows=result.total_rows,
        valid_rows=result.valid_rows,
        errors=result.errors,
    )
    db.add(imp)
    db.commit()
    to_update = csv_import.count_existing(db, [r["employee_id"] for r in result.valid_rows])
    return ImportReport(
        import_id=imp.id,
        filename=filename,
        total_rows=result.total_rows,
        valid_rows=len(result.valid_rows),
        error_rows=result.error_rows,
        to_create=len(result.valid_rows) - to_update,
        to_update=to_update,
        errors=[ImportProblem(**e) for e in result.errors],
    )


@router.get("/import/{import_id}/errors.csv")
def import_errors(
    import_id: int,
    lang: Language | None = None,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
) -> Response:
    imp = db.get(UserImport, import_id)
    if imp is None:
        raise not_found("import")
    text = csv_import.errors_csv(imp, lang or actor.preferred_language)
    return csv_response(text, f"import_{import_id}_errors.csv")


@router.post("/import/{import_id}/commit", response_model=ImportCommitOut)
def import_commit(
    import_id: int,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
) -> ImportCommitOut:
    imp = db.scalar(select(UserImport).where(UserImport.id == import_id).with_for_update())
    if imp is None:
        raise not_found("import")
    try:
        result = csv_import.commit_import(db, imp, actor, actor.preferred_language)
        db.commit()
    except IntegrityError as exc:  # someone created the same employee_id meanwhile
        db.rollback()
        raise AppError(409, "import.conflict") from exc
    return ImportCommitOut(
        import_id=imp.id,
        created=result.created,
        updated=result.updated,
        unchanged=result.unchanged,
        skipped=[ImportProblem(**s) for s in result.skipped],
        temp_passwords_csv=result.temp_passwords_csv,
    )


# --- single user ------------------------------------------------------------------


@router.get("/{user_id}", response_model=UserDetail)
def get_user(
    user_id: int, db: Session = Depends(get_db), _: AppUser = Depends(admin_only)
) -> UserDetail:
    user = _get_user(db, user_id)
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.target_user_id == user.id)
        .order_by(AuditEvent.at.desc(), AuditEvent.id.desc())
        .limit(50)
    ).all()
    return UserDetail(
        **UserRow.of(user).model_dump(),
        audit=[AuditOut.of(e) for e in events],
        learning=learner_detail_out(db, user),
    )


@router.patch("/{user_id}", response_model=UserRow)
def patch_user(
    user_id: int,
    body: UserPatchIn,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
) -> UserRow:
    user = _get_user(db, user_id)
    role_change = body.access_role is not None and body.access_role != user.access_role
    active_change = body.is_active is not None and body.is_active != user.is_active
    if user.id == actor.id and (role_change or active_change):
        raise AppError(400, "user.cannot_modify_self")
    if role_change:
        if body.access_role == AccessRole.branch_head and user.branch_id is None:
            raise AppError(400, "user.branch_required")
        audit.record(
            db,
            "user.role_changed",
            actor_id=actor.id,
            target_user_id=user.id,
            data={"from": user.access_role.value, "to": body.access_role.value},
        )
        user.access_role = body.access_role
    if active_change:
        user.is_active = bool(body.is_active)
        if not user.is_active:
            sessions.revoke_user_sessions(db, user.id)
        audit.record(
            db,
            "user.activated" if user.is_active else "user.deactivated",
            actor_id=actor.id,
            target_user_id=user.id,
        )
    db.commit()
    return UserRow.of(user)


@router.post("/{user_id}/reset-password", response_model=TempPasswordOut)
def reset_password(
    user_id: int,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
) -> TempPasswordOut:
    user = _get_user(db, user_id)
    if user.id == actor.id:
        raise AppError(400, "user.cannot_modify_self")
    temp = issue_temp_password(user)
    sessions.revoke_user_sessions(db, user.id)
    audit.record(db, "user.password_reset", actor_id=actor.id, target_user_id=user.id)
    db.commit()
    return TempPasswordOut(temp_password=temp)


@router.post("/{user_id}/reset-attempts", response_model=AttemptResetOut, status_code=201)
def reset_attempts(
    user_id: int,
    body: AttemptResetIn,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
) -> AttemptResetOut:
    """A fresh attempt cycle for one module (D4). An attempt in progress is graded first."""
    user = _get_user(db, user_id)
    module = db.get(Module, body.module_id)
    if module is None or module.type == ModuleType.faq:
        raise not_found("module")
    reason = body.reason.strip()
    if not reason:
        raise AppError(400, "reset.reason_required")
    row = attempts.reset(db, user, module, reason, actor.id, clock.utcnow())
    db.commit()
    return AttemptResetOut(
        id=row.id, user_id=user.id, module_id=module.id, reason=row.reason,
        created_at=row.created_at,
    )  # fmt: skip
