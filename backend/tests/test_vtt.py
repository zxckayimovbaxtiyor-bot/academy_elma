from __future__ import annotations

import pytest

from app.services.vtt import VttError, decode, parse

GOOD = """WEBVTT - Garov hujjatlari

NOTE yozuv muallifi uchun izoh

1
00:00:00.000 --> 00:00:04.500 line:85%
<v Diktor>Dars maqsadi</v> &amp; qamrovi

00:04.500 --> 00:09.000
Endi «Garov» yorligʻini oching
va hujjat turini tanlang.

01:00:00.000 --> 01:00:01.000
Soat bilan
"""


def test_parses_cues_with_ids_settings_tags_notes_and_short_timestamps():
    cues = parse(GOOD)
    assert [(c.start, c.end) for c in cues] == [(0, 4.5), (4.5, 9), (3600, 3601)]
    assert cues[0].text == "Dars maqsadi & qamrovi"
    assert cues[1].text == "Endi «Garov» yorligʻini oching va hujjat turini tanlang."


def test_bom_and_windows_newlines_are_accepted():
    data = ("﻿" + GOOD.replace("\n", "\r\n")).encode("utf-8")
    assert len(parse(decode(data))) == 3


@pytest.mark.parametrize(
    ("text", "code", "line"),
    [
        ("WEBVT\n\n00:00.000 --> 00:01.000\nx\n", "vtt.not_webvtt", 1),
        ("WEBVTT\n\n00:00.000 -> 00:01.000\nx\n", "vtt.bad_timing", 4),
        ("WEBVTT\n\n00:00.000 --> 00:61.000\nx\n", "vtt.bad_timing", 3),
        ("WEBVTT\n\n00:05.000 --> 00:01.000\nx\n", "vtt.end_before_start", 3),
        (
            "WEBVTT\n\n00:05.000 --> 00:06.000\na\n\n00:01.000 --> 00:02.000\nb\n",
            "vtt.unordered",
            6,
        ),
        ("WEBVTT\n\nNOTE only a note\n", "vtt.no_cues", 1),
    ],
)
def test_invalid_files_report_code_and_line(text, code, line):
    with pytest.raises(VttError) as err:
        parse(text)
    assert (err.value.code, err.value.line) == (code, line)


def test_encoding_and_size_limits():
    with pytest.raises(VttError, match="vtt.not_utf8"):
        decode("WEBVTT\n\n00:00.000 --> 00:01.000\nТест\n".encode("cp1251"))
    with pytest.raises(VttError, match="vtt.too_large"):
        decode(b"x" * (2 * 1024 * 1024 + 1))
