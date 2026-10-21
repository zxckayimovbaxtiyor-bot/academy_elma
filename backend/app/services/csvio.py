"""CSV in and out, shaped for Excel in ru/uz locales: UTF-8 with BOM and ';' separators."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence

DELIMITER = ";"
BOM = "﻿"
# Cells starting with these are run as formulas by spreadsheet software.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def to_csv(header: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=DELIMITER)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_safe(v) for v in row])
    return BOM + buf.getvalue()


def decode(data: bytes) -> str:
    """UTF-8 (with or without BOM) first, then Windows-1251, which Excel in Russian saves."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1251")


def detect_delimiter(header_line: str, required: Sequence[str]) -> str:
    """Pick ';' or ',' (whichever splits the header into the required column names)."""
    best, best_hits = ",", -1
    for delim in (";", ",", "\t"):
        names = {normalize_header(n) for n in header_line.split(delim)}
        hits = sum(1 for col in required if col in names)
        if hits > best_hits:
            best, best_hits = delim, hits
    return best


def normalize_header(name: str) -> str:
    return name.strip().strip('"').strip().lower().replace(BOM, "")
