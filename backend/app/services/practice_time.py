"""Server-clock time spent in visible practice tabs, with bounded presence leases."""

from copy import deepcopy
from datetime import datetime, timedelta

LEASE_S = 45
MAX_CLIENTS = 8


def initial(now: datetime) -> dict:
    return {
        "elapsed_s": 0.0,
        "last_at": now.isoformat(),
        "clients": {
            "initial": {
                "until": (now + timedelta(seconds=LEASE_S)).isoformat(),
                "sequence": 0,
                "active": True,
            }
        },
        "presence": False,
        "estimated": False,
    }


def advance(timing: dict, now: datetime) -> dict:
    """Count overlapping tabs once, stopping at the last confirmed presence lease."""
    value = deepcopy(timing)
    last = datetime.fromisoformat(value["last_at"]) if value.get("last_at") else now
    clients = value.get("clients", {})
    until = max(
        (
            datetime.fromisoformat(client["until"])
            for client in clients.values()
            if client["active"]
        ),
        default=last,
    )
    value["elapsed_s"] = float(value.get("elapsed_s", 0)) + max(
        0, (min(now, until) - last).total_seconds()
    )
    value["last_at"] = max(now, last).isoformat()
    value["clients"] = {
        key: client
        for key, client in clients.items()
        if datetime.fromisoformat(client["until"]) > now
    }
    return value


def activity(
    timing: dict, now: datetime, client_id: str, active: bool, sequence: int
) -> dict:
    value = advance(timing, now)
    previous = value["clients"].get(client_id)
    if previous and sequence <= previous["sequence"]:
        return value  # A delayed heartbeat must not undo a newer pause/resume.
    value["presence"] = True
    value["clients"].pop("initial", None)
    value["clients"][client_id] = {
        "until": (now + timedelta(seconds=LEASE_S)).isoformat(),
        "active": active,
        "sequence": sequence,
    }
    newest = sorted(
        value["clients"].items(), key=lambda item: item[1]["until"], reverse=True
    )
    value["clients"] = dict(newest[:MAX_CLIENTS])
    return value


def command(timing: dict, now: datetime, *, finished: bool) -> dict:
    value = advance(timing, now)
    if finished:
        value["clients"] = {}
    elif not value.get("presence"):
        # Compatibility for an already-open browser running the previous UI.
        value["clients"]["initial"] = {
            "until": (now + timedelta(seconds=LEASE_S)).isoformat(),
            "sequence": 0,
            "active": True,
        }
    return value


def seconds(timing: dict, now: datetime) -> int:
    return max(0, int(advance(timing, now)["elapsed_s"]))
