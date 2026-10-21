"""WebVTT subtitles: parse and validate. The uz/ru transcript is the cue text."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

MAX_BYTES = 2 * 1024 * 1024
_TIMESTAMP = r"(?:\d+:)?\d{2}:\d{2}\.\d{3}"
_TIMING_RE = re.compile(rf"^(?P<start>{_TIMESTAMP})\s+-->\s+(?P<end>{_TIMESTAMP})(?:\s.*)?$")
_TAG_RE = re.compile(r"<[^>]+>")
_SKIPPED_BLOCKS = ("NOTE", "STYLE", "REGION")


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


class VttError(Exception):
    def __init__(self, code: str, line: int = 0) -> None:
        super().__init__(code)
        self.code = code
        self.line = line


def decode(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise VttError("vtt.too_large")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise VttError("vtt.not_utf8") from exc


def _seconds(stamp: str) -> float:
    parts = stamp.split(":")
    hours = int(parts[0]) if len(parts) == 3 else 0
    minutes = int(parts[-2])
    seconds = float(parts[-1])
    if minutes > 59 or seconds >= 60:
        raise ValueError(stamp)
    return hours * 3600 + minutes * 60 + seconds


def parse(text: str) -> list[Cue]:
    lines = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    header = lines[0] if lines else ""
    if not (header == "WEBVTT" or header.startswith(("WEBVTT ", "WEBVTT\t"))):
        raise VttError("vtt.not_webvtt", 1)

    i = 1
    while i < len(lines) and lines[i].strip():  # header block
        i += 1
    cues: list[Cue] = []
    while i < len(lines):
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            break
        first_line_no = i + 1
        block: list[str] = []
        while i < len(lines) and lines[i].strip():
            block.append(lines[i])
            i += 1
        if block[0].startswith(_SKIPPED_BLOCKS):
            continue
        timing_at = 0 if "-->" in block[0] else 1
        line_no = first_line_no + timing_at
        match = _TIMING_RE.match(block[timing_at].strip()) if timing_at < len(block) else None
        if match is None:
            raise VttError("vtt.bad_timing", line_no)
        try:
            start, end = _seconds(match["start"]), _seconds(match["end"])
        except ValueError as exc:
            raise VttError("vtt.bad_timing", line_no) from exc
        if end <= start:
            raise VttError("vtt.end_before_start", line_no)
        if cues and start < cues[-1].start:
            raise VttError("vtt.unordered", line_no)
        body = " ".join(_TAG_RE.sub("", line).strip() for line in block[timing_at + 1 :])
        cues.append(Cue(start=start, end=end, text=html.unescape(body).strip()))
    if not cues:
        raise VttError("vtt.no_cues", 1)
    return cues


def last_cue_end(cues: list[Cue]) -> float:
    return max(c.end for c in cues)
