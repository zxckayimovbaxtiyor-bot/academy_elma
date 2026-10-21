from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app import clock
from app.models import AuditEvent


def record(
    db: Session,
    action: str,
    *,
    actor_id: int | None = None,
    target_user_id: int | None = None,
    entity: str | None = None,
    entity_id: str | int | None = None,
    reason: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            at=clock.utcnow(),
            action=action,
            actor_id=actor_id,
            target_user_id=target_user_id,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id),
            reason=reason,
            data=data or {},
        )
    )
