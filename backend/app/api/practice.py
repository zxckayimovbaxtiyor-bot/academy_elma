from __future__ import annotations

import base64
from io import BytesIO

from fastapi import APIRouter, Depends, Query, Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
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
from app.services.practice_demo import demo_definition

router = APIRouter(tags=["practice"])
author = require_roles(AccessRole.methodologist)
reporter = require_roles(AccessRole.branch_head)


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
def template(_: AppUser = Depends(author)):
    return demo_definition().model_dump()


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
        state, errors, finished = practice_engine.apply(
            data.definition, data.state.model_dump(), data.command, "guided"
        )
    except (KeyError, StopIteration, TypeError, AttributeError):
        raise AppError(422, "practice.invalid_values")
    return {
        "state": state,
        **practice_engine.public_state(data.definition, state, "guided"),
        "feedback": errors,
        "finished": finished,
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
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(PracticeAsset, asset_id)
    if row is None:
        raise not_found("practice")
    if user.access_role not in (AccessRole.admin, AccessRole.methodologist):
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
        media_type="image/png",
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
