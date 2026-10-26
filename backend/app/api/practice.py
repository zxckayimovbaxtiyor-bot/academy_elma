from __future__ import annotations

import base64
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import ValidationError
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.common import body_reader
from app.auth.deps import current_user, require_roles
from app.db import get_db
from app.errors import AppError, not_found
from app.models import AppUser
from app.models.enums import AccessRole
from app.models.practice import (
    PracticeAsset,
    PracticeAssignment,
    PracticeScenario,
    PracticeSession,
)
from app.schemas.practice import (
    AssignmentIn,
    ActivityIn,
    Command,
    Definition,
    DraftIn,
    Mode,
    PreviewIn,
    PublishIn,
    ScenarioIn,
    StartIn,
)
from app.services import audit, practice as service, practice_engine
from app.services import practice_time
from app import clock

router = APIRouter(tags=["practice"])
author = require_roles(AccessRole.methodologist)
reporter = require_roles(AccessRole.branch_head, AccessRole.methodologist)


@router.get("/me/practices")
def available(
    module_id: int | None = None,
    lesson_id: int | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.catalog(db, user, module_id, lesson_id)


@router.post("/me/practices/{scenario_id}/sessions")
def start(
    scenario_id: int,
    data: StartIn,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    s = service.start(db, user, scenario_id, data.mode)
    db.commit()
    return service.payload(db, s)


@router.get("/me/practice-sessions/{session_id}")
def resume(
    session_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.payload(db, service.owned(db, user, session_id))


@router.post("/me/practice-sessions/{session_id}/commands")
def command(
    session_id: int,
    data: Command,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    response = service.command(db, user, session_id, data)
    db.commit()
    return response


@router.post("/me/practice-sessions/{session_id}/activity")
def activity(
    session_id: int,
    data: ActivityIn,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    s = service.owned(db, user, session_id, lock=True)
    now = clock.utcnow()
    if s.status == "active":
        s.timing = practice_time.activity(
            s.timing, now, data.client_id, data.active, data.sequence
        )
        db.commit()
    return {"elapsed_s": practice_time.seconds(s.timing, now)}


@router.get("/me/practice-sessions/{session_id}/result")
def result(
    session_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    s = service.owned(db, user, session_id)
    if s.status != "completed":
        raise AppError(409, "practice.incomplete")
    return service.result_data(db, s.id)


@router.get("/me/practice-sessions/{session_id}/actions")
def history(
    session_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    service.owned(db, user, session_id)
    from app.models.practice import PracticeAction

    rows = db.scalars(
        select(PracticeAction)
        .where(PracticeAction.session_id == session_id)
        .order_by(PracticeAction.id)
    )
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "screen_id": r.screen_id,
            "at": r.created_at.isoformat(),
            "invalid": bool(r.errors),
        }
        for r in rows
    ]


@router.get("/admin/practices/template")
def template(
    kind: Literal["credit", "client", "transfer", "deposit"] = "credit",
    _: AppUser = Depends(author),
):
    from app.services.practice_templates import template_definition

    return template_definition(kind).model_dump()


@router.get("/admin/practices")
def list_scenarios(_: AppUser = Depends(author), db: Session = Depends(get_db)):
    return [
        service.detail(db, s)
        for s in db.scalars(select(PracticeScenario).order_by(PracticeScenario.id))
    ]


@router.post("/admin/practices", status_code=201)
def create(
    data: ScenarioIn, user: AppUser = Depends(author), db: Session = Depends(get_db)
):
    s = service.create(db, user, data)
    db.commit()
    return service.detail(db, s)


@router.get("/admin/practices/{scenario_id}")
def detail(
    scenario_id: int, _: AppUser = Depends(author), db: Session = Depends(get_db)
):
    return service.detail(db, service.scenario(db, scenario_id))


@router.put("/admin/practices/{scenario_id}/draft")
def edit(
    scenario_id: int,
    data: DraftIn,
    user: AppUser = Depends(author),
    db: Session = Depends(get_db),
):
    service.edit(db, user, scenario_id, data)
    db.commit()
    return service.detail(db, service.scenario(db, scenario_id))


@router.post("/admin/practices/preview")
def preview(data: Definition, _: AppUser = Depends(author)):
    return practice_engine.public_state(data, practice_engine.initial(data), "guided")


@router.post("/admin/practices/preview/step")
def preview_step(data: PreviewIn, _: AppUser = Depends(author)):
    # Preview state is untrusted and never persisted as an employee result.
    try:
        state = (
            practice_engine.initial(data.definition, data.state.task_id, data.mode)
            if data.initialize
            else data.state.model_dump()
        )
        if (
            data.definition.metadata.time_limit_s
            and state.get("elapsed_s", 0) >= data.definition.metadata.time_limit_s
        ):
            state.update(screen=data.definition.completion[0], expired=True)
            errors, finished = [], True
        else:
            state, errors, finished = practice_engine.apply(
                data.definition, state, data.command, data.mode
            )
    except (KeyError, StopIteration, TypeError, AttributeError):
        raise AppError(422, "practice.invalid_values")
    score, passed = (
        practice_engine.grade(data.definition, state, data.mode, data.pass_pct)
        if finished
        else (None, None)
    )
    return {
        "state": state,
        **practice_engine.public_state(data.definition, state, data.mode),
        "feedback": errors,
        "finished": finished,
        "result": (
            {
                "score_pct": score,
                "passed": passed,
                "duration_s": state.get("elapsed_s", 0),
                "errors": state["mistakes"],
                "expired": state.get("expired", False),
            }
            if finished
            else None
        ),
    }


@router.post("/admin/practices/{scenario_id}/publish")
def publish(
    scenario_id: int,
    data: PublishIn,
    user: AppUser = Depends(author),
    db: Session = Depends(get_db),
):
    service.publish(db, user, scenario_id, data.expected_revision)
    db.commit()
    return service.detail(db, service.scenario(db, scenario_id))


@router.put("/admin/practices/{scenario_id}/assignment")
def assign(
    scenario_id: int,
    data: AssignmentIn,
    user: AppUser = Depends(author),
    db: Session = Depends(get_db),
):
    service.scenario(db, scenario_id, lock=True)
    row = db.get(PracticeAssignment, scenario_id)
    row.policy = data.model_dump()
    audit.record(
        db,
        "practice.assigned",
        actor_id=user.id,
        entity="practice",
        entity_id=scenario_id,
        data=row.policy,
    )
    db.commit()
    return data


@router.post("/admin/practices/{scenario_id}/preview")
def review(
    scenario_id: int,
    data: PublishIn,
    _: AppUser = Depends(author),
    db: Session = Depends(get_db),
):
    service.scenario(db, scenario_id, lock=True)
    v = service.version(db, scenario_id, published=False) or service.version(
        db, scenario_id
    )
    if v.revision != data.expected_revision:
        raise AppError(409, "practice.conflict")
    try:
        Definition.model_validate(v.definition)
    except ValidationError:
        raise AppError(422, "practice.invalid_definition")
    if v.published_at is None:
        v.preview_revision = v.revision
        db.commit()
    return {"revision": v.revision}


@router.put("/admin/practices/{scenario_id}/screenshots", status_code=201)
def screenshot(
    scenario_id: int,
    synthetic_data_confirmed: bool = Query(False),
    raw: bytes = Depends(body_reader(2 * 1024 * 1024, "image.too_large", author)),
    user: AppUser = Depends(author),
    db: Session = Depends(get_db),
):
    service.scenario(db, scenario_id)
    if not synthetic_data_confirmed:
        raise AppError(422, "video.synthetic_confirmation_required")
    try:
        with Image.open(BytesIO(raw)) as img:
            if img.format not in ("PNG", "JPEG") or img.width * img.height > 8_000_000:
                raise ValueError("image")
            output = BytesIO()
            img.convert("RGB").save(output, format="PNG")
            if output.tell() > 8 * 1024 * 1024:
                raise ValueError("image")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise AppError(422, "image.invalid")
    asset = PracticeAsset(
        scenario_id=scenario_id,
        data=base64.b64encode(output.getvalue()).decode(),
        created_by=user.id,
    )
    db.add(asset)
    db.flush()
    audit.record(
        db,
        "practice.screenshot_added",
        actor_id=user.id,
        entity="practice_asset",
        entity_id=asset.id,
    )
    db.commit()
    return {"id": asset.id}


@router.get("/practice-assets/{asset_id}")
def asset(
    asset_id: int,
    session_id: int | None = None,
    cover: bool = False,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(PracticeAsset, asset_id)
    if row is None:
        raise not_found("practice")
    if user.access_role not in (AccessRole.admin, AccessRole.methodologist):
        if cover:
            scenario = service.scenario(db, row.scenario_id)
            version = service.version(db, scenario.id)
            if (
                not version
                or scenario.archived_at
                or version.definition.get("metadata", {}).get("cover_asset_id")
                != asset_id
            ):
                raise not_found("practice")
            service.ensure_access(db, user, scenario, version)
            return Response(
                base64.b64decode(row.data),
                media_type=row.content_type,
                headers={"X-Content-Type-Options": "nosniff"},
            )
        if not session_id:
            raise not_found("practice")
        s = service.owned(db, user, session_id)
        from app.models.practice import PracticeScenarioVersion

        definition = db.get(PracticeScenarioVersion, s.version_id).definition
        if row.scenario_id != s.scenario_id or not any(
            c.get("asset_id") == asset_id
            for screen in definition["screens"]
            for c in screen["components"]
        ):
            raise not_found("practice")
    return Response(
        base64.b64decode(row.data),
        media_type=row.content_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/reports/practice")
def analytics(
    module_id: int | None = None,
    user_id: int | None = None,
    branch_id: int | None = None,
    job_role_id: int | None = None,
    mode: Mode | None = None,
    wave_id: int | None = None,
    region_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: AppUser = Depends(reporter),
    db: Session = Depends(get_db),
):
    return service.analytics(
        db,
        user,
        module_id,
        user_id,
        branch_id,
        job_role_id,
        mode,
        wave_id,
        region_id,
        page,
        page_size,
    )


@router.post("/admin/practices/check/definition")
def check_definition(data: DraftIn, _: AppUser = Depends(author)):
    try:
        Definition.model_validate(data.definition.model_dump())
    except ValidationError as exc:
        return {
            "valid": False,
            "issues": [
                {
                    "path": list(e["loc"]),
                    "message": e["msg"],
                    "code": (
                        e["msg"].removeprefix("Value error, ").replace(" ", "_")
                        if e["type"] == "value_error"
                        else e["type"]
                    ),
                }
                for e in exc.errors()
            ],
        }
    return {"valid": True, "issues": []}


@router.post("/admin/practices/{scenario_id}/archive")
def archive(
    scenario_id: int,
    archived: bool = Query(True),
    user: AppUser = Depends(author),
    db: Session = Depends(get_db),
):
    row = service.scenario(db, scenario_id, lock=True)
    row.archived_at = clock.utcnow() if archived else None
    audit.record(
        db,
        "practice.archived" if archived else "practice.restored",
        actor_id=user.id,
        entity="practice",
        entity_id=scenario_id,
    )
    db.commit()
    return service.detail(db, row)


@router.post("/admin/practices/{scenario_id}/copy", status_code=201)
def copy_scenario(
    scenario_id: int, user: AppUser = Depends(author), db: Session = Depends(get_db)
):
    from copy import deepcopy
    from app.models.practice import PracticeScenarioVersion

    old = service.scenario(db, scenario_id)
    source = service.detail(db, old)["definition"]
    definition = deepcopy(source)
    definition["title"] = {
        "ru": source["title"]["ru"][:1980] + " — копия",
        "uz": source["title"]["uz"][:1980] + " — nusxa",
    }
    assets = {
        c.get("asset_id")
        for s in definition["screens"]
        for c in s["components"]
        if c.get("asset_id")
    }
    cover = definition.get("metadata", {}).get("cover_asset_id")
    if cover:
        assets.add(cover)
    for screen in definition["screens"]:
        for c in screen["components"]:
            c["asset_id"] = None
    if "metadata" in definition:
        definition["metadata"]["cover_asset_id"] = None
    row = service.create(
        db,
        user,
        ScenarioIn(
            module_id=old.module_id, lesson_id=old.lesson_id, definition=definition
        ),
    )
    remap = {}
    for asset_id in assets:
        original = db.get(PracticeAsset, asset_id)
        if original is None or original.scenario_id != old.id:
            raise AppError(422, "practice.invalid_asset")
        asset = PracticeAsset(
            scenario_id=row.id,
            data=original.data,
            content_type=original.content_type,
            created_by=user.id,
        )
        db.add(asset)
        db.flush()
        remap[asset_id] = asset.id
    for screen, original_screen in zip(definition["screens"], source["screens"]):
        for c, original_c in zip(screen["components"], original_screen["components"]):
            c["asset_id"] = remap.get(original_c.get("asset_id"))
    if cover:
        definition["metadata"]["cover_asset_id"] = remap[cover]
    db.scalar(
        select(PracticeScenarioVersion).where(
            PracticeScenarioVersion.scenario_id == row.id
        )
    ).definition = definition
    db.commit()
    return service.detail(db, row)


@router.put("/admin/practices/{scenario_id}/video", status_code=201)
def upload_video(
    scenario_id: int,
    synthetic_data_confirmed: bool = Query(False),
    raw: bytes = Depends(body_reader(20 * 1024 * 1024, "image.too_large", author)),
    user: AppUser = Depends(author),
    db: Session = Depends(get_db),
):
    service.scenario(db, scenario_id)
    if not synthetic_data_confirmed:
        raise AppError(422, "video.synthetic_confirmation_required")
    if (
        len(raw) < 16
        or raw[4:8] != b"ftyp"
        or raw[8:12] not in (b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V ")
    ):
        raise AppError(422, "image.invalid")
    row = PracticeAsset(
        scenario_id=scenario_id,
        data=base64.b64encode(raw).decode(),
        content_type="video/mp4",
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    db.commit()
    return {"id": row.id}


@router.put("/me/practice-sessions/{session_id}/files/{component_id}", status_code=201)
def upload_practice_file(
    session_id: int,
    component_id: str,
    filename: str = Query("document.pdf", max_length=200),
    raw: bytes = Depends(body_reader(2 * 1024 * 1024, "image.too_large", current_user)),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.models.practice import PracticeUpload, PracticeScenarioVersion

    session = service.owned(db, user, session_id, lock=True)
    definition = Definition.model_validate(
        db.get(PracticeScenarioVersion, session.version_id).definition
    )
    public = practice_engine.public_state(definition, session.state, session.mode)
    if session.status != "active" or not any(
        c["id"] == component_id and c["type"] == "file" and c["editable"]
        for c in public["screen"]["components"]
    ):
        raise AppError(409, "practice.invalid_action")
    if (
        db.scalar(
            select(func.count())
            .select_from(PracticeUpload)
            .where(PracticeUpload.session_id == session_id)
        )
        >= 30
    ):
        raise AppError(409, "practice.action_limit")
    if raw.startswith(b"%PDF-"):
        content_type = "application/pdf"
    else:
        try:
            with Image.open(BytesIO(raw)) as img:
                if (
                    img.format not in ("PNG", "JPEG")
                    or img.width * img.height > 8_000_000
                ):
                    raise ValueError("image")
                output = BytesIO()
                img.convert("RGB").save(output, format="PNG")
                raw = output.getvalue()
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("image")
                content_type = "image/png"
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
        ):
            raise AppError(422, "image.invalid")
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    filename = "".join(c for c in filename if c.isprintable())[:200] or "document.pdf"
    row = PracticeUpload(
        session_id=session_id,
        component_id=component_id,
        filename=filename,
        content_type=content_type,
        data=base64.b64encode(raw).decode(),
    )
    db.add(row)
    db.flush()
    db.commit()
    return {"value": f"upload_{row.id}", "filename": row.filename}


@router.get("/me/practice-sessions/{session_id}/files/{upload_id}")
def download_practice_file(
    session_id: int,
    upload_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.models.practice import PracticeUpload

    service.owned(db, user, session_id)
    row = db.get(PracticeUpload, upload_id)
    if row is None or row.session_id != session_id:
        raise not_found("practice")
    return Response(
        base64.b64decode(row.data),
        media_type=row.content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "attachment; filename=practice-document",
        },
    )


@router.get("/reports/practice/sessions/{session_id}")
def report_session(
    session_id: int, user: AppUser = Depends(reporter), db: Session = Depends(get_db)
):
    from app.models.practice import PracticeAction, PracticeScenarioVersion

    session = db.get(PracticeSession, session_id)
    if session is None:
        raise not_found("practice")
    owner = db.get(AppUser, session.user_id)
    if user.access_role == AccessRole.branch_head and (
        not user.branch_id or owner.branch_id != user.branch_id
    ):
        raise not_found("practice")
    version = db.get(PracticeScenarioVersion, session.version_id)
    screens = {screen["id"]: screen for screen in version.definition["screens"]}
    fields = {
        c["id"]: c
        for screen in version.definition["screens"]
        for c in screen["components"]
    }

    def describe(action):
        component = fields.get(action.details.get("action"), {})
        values = []
        for key, value in action.details.get("values", {}).items():
            field = fields.get(key, {})
            option = next(
                (o["label"] for o in field.get("options", []) if o["value"] == value),
                None,
            )
            values.append(
                {
                    "field": key,
                    "label": field.get("label", {"ru": key, "uz": key}),
                    "value": option or value,
                }
            )
        return {
            "id": action.id,
            "at": action.created_at,
            "screen": action.screen_id,
            "screen_title": screens.get(action.screen_id, {}).get("title"),
            "action_label": component.get("label"),
            "kind": action.kind,
            "details": action.details,
            "values": values,
            "errors": action.errors,
        }

    return {
        "task": next(
            (
                t["description"]
                for t in version.definition.get("tasks", [])
                if t["id"] == session.state.get("task_id")
            ),
            None,
        ),
        "version": version.number,
        "task_id": session.state.get("task_id"),
        "started_at": session.started_at,
        "finished_at": session.finished_at,
        "hints_used": session.state.get("hints_used", []),
        "result": service.result_data(db, session_id),
        "actions": [
            describe(a)
            for a in db.scalars(
                select(PracticeAction)
                .where(PracticeAction.session_id == session_id)
                .order_by(PracticeAction.id)
            )
        ],
    }
