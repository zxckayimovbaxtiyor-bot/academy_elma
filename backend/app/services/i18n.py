"""Text the server itself produces (CSV error reports, later certificate PDFs).

Everything shown in the browser is translated in the frontend; this covers only
files generated on the server, from app/i18n/uz.json and ru.json.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from app.models.enums import Language

_DIR = Path(__file__).resolve().parent.parent / "i18n"


@cache
def _catalog(lang: str) -> dict[str, Any]:
    return json.loads((_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def t(lang: Language | str, key: str, **params: Any) -> str:
    node: Any = _catalog(Language(lang).value)
    for part in key.split("."):
        node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            return key
    return str(node).format_map({k: "" if v is None else v for k, v in params.items()})
