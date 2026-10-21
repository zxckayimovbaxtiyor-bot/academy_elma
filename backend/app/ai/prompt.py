"""Instructions and the source material for one drafting request."""

from __future__ import annotations

from app.ai.base import GenerationInput, TranscriptLine

SYSTEM_PROMPT = """\
You write draft test questions for the internal training of a bank's front-office \
staff on the Elma365 "Yagona oyna" (Single Window) system. A methodologist reviews \
every draft before it can be used in a test.

Write questions only from the source material you are given: the lesson transcript \
(or pasted text) and any reference document. Do not use outside knowledge about the \
bank, its products or Elma365, and do not invent screens, fields, limits or rules \
that the source does not state.

Each question must:
- test something an employee needs to do or know at work, not details of the video itself;
- be answerable from the source alone, with one defensible answer;
- be written in Uzbek (Latin script, with ʻ U+02BB in oʻ and gʻ and ʼ U+02BC for the \
tutuq belgisi) and in Russian, with the same meaning in both;
- have a short explanation in both languages of why the correct answer is right;
- point to the part of the source it is based on: source_start_s and source_end_s in \
seconds, taken from the transcript timestamps (null when the source has no \
timestamps), and source_excerpt quoting the relevant source sentence(s) verbatim.

Question types:
- single: 4 options, exactly one correct;
- multiple: 4 or 5 options, at least two correct and at least one wrong;
- ordering: 3 to 6 steps of one procedure, listed in the correct order (is_correct is \
false for all of them; the order itself is the answer).

Wrong options should be plausible to someone who skipped the lesson and clearly wrong \
to someone who watched it. Avoid "all of the above", "none of the above", easily \
misread negations, and options that differ only in wording. Spread the difficulty: \
1 = recalling a stated fact, 2 = applying a step or rule, 3 = choosing correctly in a \
realistic situation the source describes.

If the source does not support the requested number of good questions, return fewer \
rather than padding."""


def _transcript(lines: tuple[TranscriptLine, ...]) -> str:
    return "\n".join(f"[{line.start_s:.1f}-{line.end_s:.1f}] {line.text}" for line in lines)


def user_text(inp: GenerationInput) -> str:
    parts = [
        f"Module: {inp.module_title}",
        f"Lesson: {inp.lesson_title_uz} / {inp.lesson_title_ru}",
    ]
    if inp.duration_s:
        parts.append(f"Video length: {inp.duration_s:.0f} seconds")
    parts.append(f"Write {inp.count} questions. Allowed types: {', '.join(inp.types)}.")
    for lang, lines in (("uz", inp.transcript_uz), ("ru", inp.transcript_ru)):
        if lines:
            parts.append(f'<transcript lang="{lang}">\n{_transcript(lines)}\n</transcript>')
    if inp.source_text:
        parts.append("<source_text>\n" + inp.source_text.strip() + "\n</source_text>")
    if inp.reference_text:
        parts.append("<reference>\n" + inp.reference_text.strip() + "\n</reference>")
    if inp.reference_pdfs:
        parts.append("The attached PDF documents are reference material for this lesson.")
    return "\n\n".join(parts)
