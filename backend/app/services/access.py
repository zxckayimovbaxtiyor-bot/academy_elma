"""Which modules a learner sees, and the Core-first prerequisite.

Assigned modules = Core plus the modules ticked for the learner's job role in the
role x module matrix of the wave their branch belongs to. FAQ is open to everyone
and never assigned. A product module unlocks once the learner holds a Core
certificate, valid or awaiting recertification: a later Core release does not
re-lock products that were already opened.
"""

from __future__ import annotations

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.models import AppUser, Certificate, Module, Wave, WaveBranch, WaveModuleRole
from app.models.enums import CertificateKind, ModuleType


def user_wave(db: Session, user: AppUser) -> Wave | None:
    if user.branch_id is None:
        return None
    return db.scalar(
        select(Wave)
        .join(WaveBranch, WaveBranch.wave_id == Wave.id)
        .where(WaveBranch.branch_id == user.branch_id)
    )


def assigned_modules(db: Session, user: AppUser) -> list[Module]:
    wave = user_wave(db, user)
    if wave is None or user.job_role_id is None:
        return []
    for_role = select(WaveModuleRole.module_id).where(
        WaveModuleRole.wave_id == wave.id, WaveModuleRole.job_role_id == user.job_role_id
    )
    return list(
        db.scalars(
            select(Module)
            .where(
                or_(
                    Module.type == ModuleType.core,
                    Module.id.in_(for_role) & (Module.type == ModuleType.product),
                )
            )
            .order_by(Module.sort, Module.id)
        )
    )


def holds_core_certificate(db: Session, user_id: int) -> bool:
    core_ids = select(Module.id).where(Module.type == ModuleType.core)
    return bool(
        db.scalar(
            select(
                exists().where(
                    Certificate.user_id == user_id,
                    Certificate.kind == CertificateKind.module,
                    Certificate.module_id.in_(core_ids),
                    Certificate.superseded_at.is_(None),
                )
            )
        )
    )


def is_locked(module: Module, core_certified: bool) -> bool:
    return module.type == ModuleType.product and not core_certified
