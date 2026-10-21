"""AI drafting (rule 11): provider contract, server-side validation, the job, isolation."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from sqlalchemy import select

from app.ai import (
    DraftOption,
    DraftQuestion,
    GenerationError,
    GenerationInput,
    GenerationResult,
    NoopProvider,
    ReferencePdf,
    TranscriptLine,
    get_generator,
)
from app.ai.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.models import Job, LessonVersion, Question
from app.models.enums import AccessRole, JobStatus, QuestionOrigin, QuestionStatus
from app.services import ai_drafts, media
from app.worker import ai_draft  # noqa: F401  (registers the job handler)
from app.worker.runner import run_job
from tests.factories import error_code, login, make_live_lesson, make_release, make_user

BACKEND = Path(__file__).resolve().parent.parent
VTT_UZ = "WEBVTT\n\n00:00.000 --> 00:08.000\nMijozni qidirish uchun JSHSHIR kiriting.\n\n" \
         "00:08.000 --> 00:20.000\nSoʻng «Qidirish» tugmasini bosing.\n"  # fmt: skip
VTT_RU = "WEBVTT\n\n00:00.000 --> 00:08.000\nДля поиска клиента введите ПИНФЛ.\n\n" \
         "00:08.000 --> 00:20.000\nЗатем нажмите «Поиск».\n"  # fmt: skip


def _item(**overrides) -> DraftQuestion:
    base = DraftQuestion(
        type="single", difficulty=1,
        text_uz="Mijoz qanday qidiriladi?", text_ru="Как ищут клиента?",
        explanation_uz="Darsda JSHSHIR boʻyicha qidirish koʻrsatilgan.",
        explanation_ru="В уроке показан поиск по ПИНФЛ.",
        options=(
            DraftOption("JSHSHIR boʻyicha", "По ПИНФЛ", True),
            DraftOption("Telefon boʻyicha", "По телефону", False),
            DraftOption("Ism boʻyicha", "По имени", False),
            DraftOption("Manzil boʻyicha", "По адресу", False),
        ),
        source_start_s=0.0, source_end_s=8.0,
        source_excerpt="Mijozni qidirish uchun JSHSHIR kiriting.",
    )  # fmt: skip
    return replace(base, **overrides)


def _json(items: list[DraftQuestion]) -> str:
    def plain(q: DraftQuestion) -> dict:
        out = q.__dict__ | {"options": [o.__dict__ for o in q.options]}
        return out

    return json.dumps({"questions": [plain(q) for q in items]}, ensure_ascii=False)


# --- the switch: no key, no feature -------------------------------------------------------


def test_without_a_key_the_feature_is_hidden(db, client, reference, monkeypatch):
    monkeypatch.setattr("app.config.settings.anthropic_api_key", "")
    assert isinstance(get_generator(), NoopProvider)
    with pytest.raises(GenerationError) as err:
        NoopProvider().generate(GenerationInput("M", "L", "L", 60.0, 5))
    assert err.value.code == "ai.disabled"

    _, version = make_live_lesson(db, reference.modules["CORE"])
    login(client, make_user(db, role=AccessRole.methodologist))
    assert client.get("/api/v1/admin/ai/status").json() == {"enabled": False, "model": None}
    refused = client.post(f"/api/v1/admin/lesson-versions/{version.id}/ai-drafts", json={})
    assert refused.status_code == 409 and error_code(refused) == "ai.disabled"


def test_with_a_key_the_status_names_the_model(db, client, reference, monkeypatch):
    monkeypatch.setattr("app.config.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.config.settings.anthropic_model", "claude-opus-5-5")
    login(client, make_user(db, role=AccessRole.methodologist))
    assert client.get("/api/v1/admin/ai/status").json() == {
        "enabled": True, "model": "claude-opus-5-5",
    }  # fmt: skip
    learner = make_user(db)
    login(client, learner)
    assert client.get("/api/v1/admin/ai/status").status_code == 403


def test_learner_routes_never_import_the_ai_package():
    learner_modules = ["app.api.learner", "app.api.attempts", "app.api.certificates",
                       "app.api.auth", "app.api.system"]  # fmt: skip
    for name in learner_modules:  # static: no import statement mentions them
        tree = ast.parse((BACKEND / Path(*name.split("."))).with_suffix(".py").read_text())
        imported = [
            n.module if isinstance(n, ast.ImportFrom) else a.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [None])
        ]
        forbidden = [m for m in imported if m and m.startswith(("app.ai", "anthropic"))]
        assert not forbidden, (name, forbidden)
    # dynamic: importing them (and everything they import) loads neither
    code = (
        f"import sys; import {', '.join(learner_modules)}; "
        "bad = [m for m in sys.modules if m.startswith(('anthropic', 'app.ai'))]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    run = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    # the whole API process doesn't load the SDK either: only the provider does, lazily
    code = "import sys, app.main; sys.exit(1 if 'anthropic' in sys.modules else 0)"
    run = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


# --- the provider ---------------------------------------------------------------------------


class _FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class _FakeClient:
    """Stands in for anthropic.Anthropic: records the request, returns a canned message."""

    def __init__(self, message=None, error: Exception | None = None):
        self.calls: list[dict] = []
        self.message, self.error = message, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return _FakeStream(self.message)


def _message(*blocks, stop_reason="end_turn", stop_details=None, iterations=None):
    return SimpleNamespace(
        content=list(blocks), stop_reason=stop_reason, stop_details=stop_details,
        model="claude-opus-5-5", usage=SimpleNamespace(iterations=iterations),
    )  # fmt: skip


def _text(text):
    return SimpleNamespace(type="text", text=text)


GEN_INPUT = GenerationInput(
    module_title="Asosiy / Основной", lesson_title_uz="Mijozni qidirish",
    lesson_title_ru="Поиск клиента", duration_s=20.0, count=4, types=("single", "ordering"),
    transcript_uz=(TranscriptLine(0.0, 8.0, "Mijozni qidirish uchun JSHSHIR kiriting."),),
    transcript_ru=(TranscriptLine(0.0, 8.0, "Для поиска клиента введите ПИНФЛ."),),
    reference_pdfs=(ReferencePdf("Qoʻllanma (uz)", b"%PDF-1.4 test"),),
)  # fmt: skip


def test_provider_request_uses_structured_output_pdfs_and_fallbacks():
    thinking = SimpleNamespace(type="thinking", thinking="")
    fake = _FakeClient(_message(thinking, _text(_json([_item()]))))
    provider = AnthropicProvider(api_key="sk-test", model="claude-opus-5-5", client=fake)
    result = provider.generate(GEN_INPUT)

    [request] = fake.calls
    assert request["model"] == "claude-opus-5-5" and request["max_tokens"] == 64000
    assert request["betas"] == [FALLBACK_BETA] == ["server-side-fallback-2026-07-01"]
    assert request["fallbacks"] == "default"
    assert request["output_config"]["effort"] == "medium"
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in request  # adaptive is the model's default
    doc, text = request["messages"][0]["content"]
    assert doc["type"] == "document" and doc["source"]["media_type"] == "application/pdf"
    assert doc["source"]["data"] == "JVBERi0xLjQgdGVzdA==" and doc["title"] == "Qoʻllanma (uz)"
    assert "[0.0-8.0] Mijozni qidirish uchun JSHSHIR kiriting." in text["text"]
    assert "Write 4 questions. Allowed types: single, ordering." in text["text"]
    assert "Do not use outside knowledge" in request["system"]
    assert result.questions == [_item()] and result.malformed == 0 and not result.fell_back


def test_provider_reads_a_reply_continued_by_a_fallback_model():
    whole = _json([_item(), _item(text_uz="Ikkinchi savol?")])
    middle = len(whole) // 2
    fake = _FakeClient(_message(
        _text(whole[:middle]), SimpleNamespace(type="fallback"), _text(whole[middle:]),
        iterations=[SimpleNamespace(type="message"), SimpleNamespace(type="fallback_message")],
    ))  # fmt: skip
    result = AnthropicProvider("sk", "claude-opus-5-5", client=fake).generate(GEN_INPUT)
    assert len(result.questions) == 2 and result.fell_back is True


def test_provider_reports_refusals_truncation_and_bad_output():
    cases = [
        (_message(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")),
         "ai.refused", {"category": "cyber"}),
        (_message(stop_reason="refusal"), "ai.refused", {"category": None}),
        (_message(_text('{"questions": [{"type": "sin'), stop_reason="max_tokens"),
         "ai.truncated", {}),
        (_message(_text("not json")), "ai.output_invalid", {}),
        (_message(_text('{"items": []}')), "ai.output_invalid", {}),
    ]  # fmt: skip
    for message, code, params in cases:
        provider = AnthropicProvider("sk", "claude-opus-5-5", client=_FakeClient(message))
        with pytest.raises(GenerationError) as err:
            provider.generate(GEN_INPUT)
        assert (err.value.code, err.value.params) == (code, params)


def test_provider_maps_api_errors_to_codes():
    import anthropic

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    errors = [
        (anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=request),
                                  body=None), "ai.rate_limited"),
        (anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=request),
                                       body=None), "ai.auth_failed"),
        (anthropic.InternalServerError("boom", response=httpx2.Response(500, request=request),
                                       body=None), "ai.api_error"),
        (anthropic.APIConnectionError(request=request), "ai.unreachable"),
    ]  # fmt: skip
    for error, code in errors:
        provider = AnthropicProvider("sk", "claude-opus-5-5", client=_FakeClient(error=error))
        with pytest.raises(GenerationError) as err:
            provider.generate(GEN_INPUT)
        assert err.value.code == code


def test_malformed_items_are_counted_not_fatal():
    good = json.loads(_json([_item()]))["questions"][0]
    reply = json.dumps({"questions": [good, {"type": "single"}, dict(good, difficulty="2")]})
    fake = _FakeClient(_message(_text(reply)))
    result = AnthropicProvider("sk", "claude-opus-5-5", client=fake).generate(GEN_INPUT)
    assert (len(result.questions), result.malformed) == (1, 2)


def test_the_real_sdk_sends_our_request(monkeypatch):
    """The official SDK on a mocked transport: our arguments are accepted and streamed back."""
    import anthropic

    seen = {}
    reply = _json([_item()])

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["beta"] = request.headers.get("anthropic-beta")
        seen["body"] = json.loads(request.content)
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                "content": [], "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0,
                                     "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta", "text": reply}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta",
                               "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                               "usage": {"output_tokens": 50}}),
            ("message_stop", {"type": "message_stop"}),
        ]  # fmt: skip
        body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    client = anthropic.Anthropic(
        api_key="sk-test", max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )  # fmt: skip
    result = AnthropicProvider("sk-test", "claude-opus-5-5", client=client).generate(GEN_INPUT)
    assert result.questions == [_item()]
    assert FALLBACK_BETA in seen["beta"]
    body = seen["body"]
    assert body["fallbacks"] == "default" and body["stream"] is True
    assert body["output_config"]["format"]["schema"]["required"] == ["questions"]
    assert body["messages"][0]["content"][0]["type"] == "document"


# --- server-side validation ---------------------------------------------------------------


ALL = {"single", "multiple", "ordering"}


@pytest.mark.parametrize(
    ("item", "problem"),
    [
        (_item(options=_item().options[:1]), "options_count"),
        (_item(options=tuple(replace(o, is_correct=True) for o in _item().options[:2])
                + _item().options[2:]), "needs_exactly_one_correct"),
        (_item(type="multiple"), "needs_two_correct_and_one_wrong"),
        (_item(text_ru=""), "text_missing"),
        (_item(explanation_uz=""), "explanation_missing"),
        (_item(options=(replace(_item().options[0], text_ru=""),) + _item().options[1:]),
         "option_text_missing"),
        (_item(text_uz="x" * 2001), "too_long"),
        (_item(difficulty=4), "difficulty_invalid"),
        (_item(source_end_s=60.0), "timestamp_outside_video"),
        (_item(source_start_s=9.0, source_end_s=3.0), "timestamp_outside_video"),
        (_item(source_start_s=None, source_end_s=None), "timestamp_missing"),
        (_item(type="screenshot"), "type_not_allowed"),
    ],
)  # fmt: skip
def test_each_rule_drops_an_item(item, problem):
    assert problem in ai_drafts.problems(item, ALL, duration=20.0, timestamped=True)


def test_valid_items_pass_and_ordering_ignores_correct_flags():
    assert ai_drafts.problems(_item(), ALL, 20.0, True) == []
    assert ai_drafts.problems(_item(source_end_s=20.9), ALL, 20.0, True) == []  # 1 s slack
    steps = tuple(DraftOption(f"{i}-qadam", f"Шаг {i}", i == 1) for i in range(1, 4))
    assert ai_drafts.problems(_item(type="ordering", options=steps), ALL, 20.0, True) == []
    pasted = _item(source_start_s=None, source_end_s=None)
    assert ai_drafts.problems(pasted, ALL, None, timestamped=False) == []
    assert ai_drafts.problems(_item(), {"multiple"}, 20.0, True) == ["type_not_allowed"]


# --- the job --------------------------------------------------------------------------------


class _FakeGenerator:
    enabled = True
    model = "claude-opus-5-5"

    def __init__(self, result=None, error=None):
        self.result, self.error, self.inputs = result, error, []

    def generate(self, inp):
        self.inputs.append(inp)
        if self.error:
            raise self.error
        return self.result


def _lesson_with_subtitles(db, reference):
    lesson, version = make_live_lesson(db, reference.modules["CORE"], duration=20, title="Qidirish")
    version.vtt_uz_path = media.write_new("vtt", f"{version.id}-uz", ".vtt", VTT_UZ.encode())
    version.vtt_ru_path = media.write_new("vtt", f"{version.id}-ru", ".vtt", VTT_RU.encode())
    db.flush()
    return lesson, version


def _use(monkeypatch, generator):
    monkeypatch.setattr("app.api.admin_ai.get_generator", lambda: generator)
    monkeypatch.setattr("app.worker.ai_draft.get_generator", lambda: generator)


def test_job_saves_valid_items_as_ai_drafts_and_counts_the_rest(
    db, client, reference, monkeypatch, clock
):
    lesson, version = _lesson_with_subtitles(db, reference)
    existing = Question(
        module_id=lesson.module_id, seq=1, lesson_version_id=version.id, type="single",
        text_uz="Allaqachon bor savol", text_ru="Уже есть", status=QuestionStatus.approved,
    )  # fmt: skip
    db.add(existing)
    db.flush()
    steps = tuple(DraftOption(f"{i}-qadam", f"Шаг {i}", False) for i in range(1, 4))
    generator = _FakeGenerator(GenerationResult(
        questions=[
            _item(),
            _item(type="ordering", text_uz="Tartibni tiklang", options=steps,
                  source_start_s=8.4, source_end_s=20.0, difficulty=2),
            _item(text_uz="Allaqachon bor savol"),  # duplicate of the bank
            _item(text_uz="Yana bir savol", source_end_s=99.0),  # past the video
            _item(text_uz="Ortiqcha savol"),  # beyond the requested count
        ],
        malformed=1, model="claude-opus-5-5",
    ))  # fmt: skip
    _use(monkeypatch, generator)
    staff = make_user(db, role=AccessRole.methodologist)
    login(client, staff)

    body = {"count": 2, "types": ["single", "ordering"]}
    resp = client.post(f"/api/v1/admin/lesson-versions/{version.id}/ai-drafts", json=body)
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["id"]
    assert resp.json()["status"] == "queued"
    again = client.post(f"/api/v1/admin/lesson-versions/{version.id}/ai-drafts", json=body)
    assert again.status_code == 409 and error_code(again) == "ai.job_in_progress"

    job = db.get(Job, job_id)
    run_job(db, job)
    status = client.get(f"/api/v1/admin/jobs/{job_id}").json()
    assert status["status"] == "done"
    result = status["result"]
    assert (result["created"], result["dropped"]) == (2, 4)
    assert result["problems"] == {
        "duplicate": 1, "malformed": 1, "over_count": 1, "timestamp_outside_video": 1,
    }  # fmt: skip

    [inp] = generator.inputs
    assert inp.count == 2 and inp.types == ("single", "ordering") and inp.duration_s == 20
    assert inp.transcript_uz[1] == TranscriptLine(8.0, 20.0, "Soʻng «Qidirish» tugmasini bosing.")
    assert inp.transcript_ru[0].text == "Для поиска клиента введите ПИНФЛ."

    drafts = db.scalars(select(Question).where(Question.id.in_(result["question_ids"]))).all()
    by_type = {q.type: q for q in drafts}
    single, ordering = by_type["single"], by_type["ordering"]
    assert {q.origin for q in drafts} == {QuestionOrigin.ai}
    assert {q.status for q in drafts} == {QuestionStatus.draft}
    assert {q.ai_job_id for q in drafts} == {job_id}
    assert {q.lesson_version_id for q in drafts} == {version.id}
    span = (ordering.video_ts_s, ordering.ai_source_start_s, ordering.ai_source_end_s)
    assert span == (8, 8.4, 20.0)
    assert [o.is_correct for o in ordering.options] == [False, False, False]
    assert single.ai_source_excerpt == "Mijozni qidirish uchun JSHSHIR kiriting."

    # Drafts go through the same review as hand-written questions.
    approved = client.post(f"/api/v1/admin/questions/{single.id}/approve")
    assert approved.status_code == 200 and approved.json()["origin"] == "ai"
    listed = client.get(
        f"/api/v1/admin/modules/{lesson.module_id}/questions", params={"origin": "ai"}
    ).json()
    assert {q["id"] for q in listed} == {single.id, ordering.id}
    assert listed[0]["ai_source_excerpt"]


def test_a_declined_request_fails_the_job_with_a_code(db, client, reference, monkeypatch):
    _, version = _lesson_with_subtitles(db, reference)
    _use(monkeypatch, _FakeGenerator(error=GenerationError("ai.refused", {"category": "cyber"})))
    login(client, make_user(db, role=AccessRole.methodologist))
    job_id = client.post(
        f"/api/v1/admin/lesson-versions/{version.id}/ai-drafts", json={}
    ).json()["id"]
    run_job(db, db.get(Job, job_id))
    status = client.get(f"/api/v1/admin/jobs/{job_id}").json()
    assert status["status"] == JobStatus.failed
    assert status["result"] == {"error": {"code": "ai.refused", "params": {"category": "cyber"}}}
    assert db.scalar(select(Question).where(Question.lesson_version_id == version.id)) is None


def test_requests_are_checked_before_queueing(db, client, reference, monkeypatch, media_root):
    _use(monkeypatch, _FakeGenerator(GenerationResult(questions=[])))
    core = reference.modules["CORE"]
    _, bare = make_live_lesson(db, core)  # subtitle paths point at files never written
    bare.vtt_uz_path = bare.vtt_ru_path = None
    login(client, make_user(db, role=AccessRole.methodologist))
    url = f"/api/v1/admin/lesson-versions/{bare.id}/ai-drafts"

    assert error_code(client.post(url, json={})) == "ai.transcript_missing"
    assert error_code(client.post(url, json={"source": "text", "text": "  "})) == "ai.text_missing"
    pasted = client.post(url, json={"source": "text", "text": "Mijoz JSHSHIR bilan qidiriladi."})
    assert pasted.status_code == 202
    no_pdf = {"source": "text", "text": "Matn", "include_lesson_pdf": True}
    _, other = make_live_lesson(db, core)
    other_url = f"/api/v1/admin/lesson-versions/{other.id}/ai-drafts"
    assert error_code(client.post(other_url, json=no_pdf)) == "ai.pdf_missing"
    assert client.post(other_url, json={"types": []}).status_code == 422
    assert client.post(other_url, json={"count": 31}).status_code == 422
    assert client.post(other_url, json={"types": ["screenshot"]}).status_code == 422

    faq_lesson, faq_version = make_live_lesson(db, reference.modules["FAQ"])
    resp = client.post(f"/api/v1/admin/lesson-versions/{faq_version.id}/ai-drafts",
                       json={"source": "text", "text": "Matn"})  # fmt: skip
    assert error_code(resp) == "module.no_test"
    old = LessonVersion(lesson_id=faq_lesson.id, release_id=make_release(db, "T-OLD").id,
                        status="superseded")  # fmt: skip
    db.add(old)
    db.flush()
    resp = client.post(f"/api/v1/admin/lesson-versions/{old.id}/ai-drafts",
                       json={"source": "text", "text": "Matn"})  # fmt: skip
    assert resp.status_code == 409 and error_code(resp) == "lesson_version.superseded"

    login(client, make_user(db))
    assert client.post(other_url, json={}).status_code == 403


def test_lesson_pdfs_go_along_as_documents(db, client, reference, monkeypatch):
    lesson, version = _lesson_with_subtitles(db, reference)
    version.pdf_uz_path = media.write_new("pdf", "q-uz", ".pdf", b"%PDF-1.4 uz")
    version.pdf_ru_path = media.write_new("pdf", "q-ru", ".pdf", b"%PDF-1.4 ru")
    db.flush()
    generator = _FakeGenerator(GenerationResult(questions=[]))
    _use(monkeypatch, generator)
    login(client, make_user(db, role=AccessRole.methodologist))
    body = {"include_lesson_pdf": True, "reference_text": "Limit: 3 ta urinish."}
    job_id = client.post(
        f"/api/v1/admin/lesson-versions/{version.id}/ai-drafts", json=body
    ).json()["id"]
    run_job(db, db.get(Job, job_id))
    [inp] = generator.inputs
    assert [p.data for p in inp.reference_pdfs] == [b"%PDF-1.4 uz", b"%PDF-1.4 ru"]
    assert inp.reference_text == "Limit: 3 ta urinish."
    assert db.get(Job, job_id).result["created"] == 0


def test_output_schema_stays_inside_the_supported_subset():
    """Structured outputs: every object closed, no numeric/string/array constraints."""
    from app.ai.schema import OUTPUT_SCHEMA

    unsupported = {"minimum", "maximum", "multipleOf", "minLength", "maxLength", "minItems",
                   "maxItems", "pattern"}  # fmt: skip

    def walk(node):
        if isinstance(node, dict):
            assert not unsupported & node.keys(), node
            assert not isinstance(node.get("type"), list), "use anyOf for nullable fields"
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(OUTPUT_SCHEMA)
