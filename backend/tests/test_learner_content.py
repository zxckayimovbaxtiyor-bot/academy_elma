from __future__ import annotations

from tests.factories import give_certificate, login, make_learner, make_live_lesson, make_wave


def test_module_list_and_detail_show_progress_and_test_rules(db, client, reference, clock):
    core = reference.modules["CORE"]
    core.test_question_count = 15
    make_wave(db, [reference.tashkent], {})
    first, version = make_live_lesson(db, core, duration=100, title="Kirish")
    make_live_lesson(db, core, duration=200, title="Mijozni qidirish")
    learner = make_learner(db, reference)
    login(client, learner)

    beat = f"/api/v1/me/lessons/{first.id}/heartbeat"
    client.post(beat, json={"version_id": version.id, "ranges": []})
    for start in range(0, 90, 10):
        clock.advance(seconds=10)
        client.post(beat, json={"version_id": version.id, "ranges": [[start, start + 10]]})

    [module] = client.get("/api/v1/me/modules").json()
    assert (module["lessons_total"], module["lessons_completed"]) == (2, 1)
    assert module["duration_s"] == 300 and module["release_code"] == "T-LIVE"

    detail = client.get(f"/api/v1/me/modules/{core.id}").json()
    assert [lsn["title_uz"] for lsn in detail["lessons"]] == ["Kirish", "Mijozni qidirish"]
    assert [lsn["completed"] for lsn in detail["lessons"]] == [True, False]
    assert detail["lessons"][0]["watched_pct"] == 90
    test = detail["test"]
    status = test.pop("status")
    assert test == {
        "question_count": 15, "pass_pct": 80, "time_limit_min": 20, "max_attempts": 3,
        "published": False, "lessons_complete": False,
    }  # fmt: skip
    assert status["can_start"] is False
    assert [r["code"] for r in status["reasons"]] == ["lessons_incomplete", "test_not_published"]
    assert status["reasons"][0]["params"] == {"completed": 1, "total": 2}
    assert (status["attempts_used"], status["attempts_max"]) == (0, 3)


def test_player_payload(db, client, reference):
    farovon = reference.modules["FAROVON"]
    make_wave(db, [reference.tashkent], {reference.roles["menejer"]: [farovon]})
    one, _ = make_live_lesson(db, farovon, title="Mahsulot")
    two, v2 = make_live_lesson(db, farovon, title="Ariza", pdf=True)
    three, _ = make_live_lesson(db, farovon, title="Garov")
    learner = make_learner(db, reference)
    give_certificate(db, learner, reference.modules["CORE"])
    login(client, learner)

    player = client.get(f"/api/v1/me/lessons/{two.id}").json()
    assert player["hls_url"] == f"/media/hls/{v2.video_asset_id}/master.m3u8"
    assert player["subtitles"] == {
        "uz": f"/media/{v2.vtt_uz_path}",
        "ru": f"/media/{v2.vtt_ru_path}",
    }
    assert player["pdf"] == {"uz": f"/media/{v2.pdf_uz_path}", "ru": f"/media/{v2.pdf_ru_path}"}
    assert (player["prev_lesson_id"], player["next_lesson_id"]) == (one.id, three.id)
    assert player["progress"]["watched_pct"] == 0 and player["seek_limit_s"] == 0
    assert client.get(f"/api/v1/me/lessons/{one.id}").json()["pdf"] is None


def test_pdf_is_shown_only_in_both_languages(db, client, reference):
    core = reference.modules["CORE"]
    make_wave(db, [reference.tashkent], {})
    lesson, version = make_live_lesson(db, core, pdf=True)
    version.pdf_ru_path = None
    db.flush()
    login(client, make_learner(db, reference))
    assert client.get(f"/api/v1/me/lessons/{lesson.id}").json()["pdf"] is None


def test_faq_player_is_untracked_and_only_for_faq_lessons(db, client, reference):
    faq_lesson, _ = make_live_lesson(db, reference.modules["FAQ"], title="Xatolar")
    core_lesson, _ = make_live_lesson(db, reference.modules["CORE"])
    make_wave(db, [reference.tashkent], {})
    login(client, make_learner(db, reference))
    player = client.get(f"/api/v1/me/faq/{faq_lesson.id}").json()
    assert (player["tracking"], player["seek_limit_s"], player["progress"]) == (False, None, None)
    assert client.get(f"/api/v1/me/faq/{core_lesson.id}").status_code == 404
