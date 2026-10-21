# Yagona oyna Akademiyasi: Phase 0 plan

Status: **Phases 1–7 built.** "As built" notes record where the implementation settled details this plan left open.
Items marked **[DECIDE]** need your answer before Phase 1. Items marked **[DEFAULT]** are what I will do unless you object.
Mockup numbers refer to the 11 reference screens (1 · Bosh sahifa … 11 · Elma365 relizlari).

---

## 0. Summary

- **Four containers:** `postgres`, `api` (FastAPI, sync SQLAlchemy 2 + psycopg 3), `worker` (same image; ffmpeg transcodes, AI drafts, periodic sweeps), `nginx` (built SPA, HLS/VTT/PDF media behind `auth_request`, `/api` proxy). The job queue is a Postgres table read with `FOR UPDATE SKIP LOCKED`, so there is no Redis or Celery.
- **The server makes every learner-facing decision:** watch credit, unlocks, test assembly, timer, grading, remediation and certificates. The browser only renders and reports.
- **Content is versioned per Elma365 release.** Each lesson has one `lesson_version` per release that changed it. New videos and questions are prepared inside a draft release and go live in one transaction when it is published. Only modules touched by that release flip to "recertification required". This is how rule 9 is enforced, and it also keeps half-prepared content away from learners.
- **The full schema (25 tables) is created in Phase 1**, so later phases need no schema changes.
- **Offline:** images are built once on a machine with internet, exported with `docker save` and loaded on the bank server. After that, `docker compose up` needs no network. nginx sends `Content-Security-Policy: default-src 'self'`, so any accidental external request fails visibly in the browser.

---

## 1. Mockups vs. spec

### 1.1 Conflicts and gaps [DECIDE]

**D1. Remediation unit: rule 7 vs mockup 4.**
Rule 7 says the learner re-watches the linked *lessons*. Mockup 4 shows *fragments* ("fragment 2:40–4:10").
- (a) Whole lesson. This is exactly rule 7, with no heuristics.
- (b) Fragment. Each missed question gives a window from its timestamp −15 s to +75 s. The windows are merged per lesson into one span. The item is done when ≥ 90 % of the span has been played after the failure.

The schema is the same either way: a remediation item stores a span, and a whole lesson is just `[0, duration]`.
**Recommendation: (b).** The per-question timestamp exists for exactly this, and the UI is already designed around it.

**D2. Grace period after a new release: rule 9 vs mockup 11 ("O'tish davri — 14 kun").**
Rule 9 flips certified learners to "recertification required" immediately. The mockup adds a transition period during which the old certificate stays valid.
**Recommendation:** make it a per-release setting with a **default of 0 days**, which is exactly rule 9.
- With N > 0 days, the learner sees "recertify by <date>" straight away.
- The access-gate API keeps returning `valid` (plus `recert_due_at`) until that date, then returns `recert_required`.

It costs one column.

**D3. Shuffling options in screenshot questions: rule 6 vs mockup 3.**
The letters A–D are drawn on the screenshot and the options refer to them. Shuffling the display order therefore changes nothing: the mapping from letter to region stays fixed. It only makes the list harder to read.
**Recommendation:**
- Shuffle options for every type except screenshot questions, which are shown in A→D order.
- The methodologist draws the letters onto the image, so no hotspot editor is needed.

**D4. Attempt reset: a gap in rule 6 (mockup 10 has "Urinishlarni tiklash").**
After 3 failed attempts the spec gives no way forward. The learner can never be certified, so they never get Single Window access.
**Recommendation:** an admin-only "reset attempts" action per learner and module.
- The admin must enter a reason, which is written to the audit log.
- A reset starts a fresh cycle: 3 attempts, and the earlier cooldown and remediation no longer apply.

**D5. Two different meanings of "role" (spec ambiguity; mockups 9–10).**
The spec uses "role" both for permissions (learner, branch_head, methodologist, admin) and for the CSV column that drives module assignment. The mockups show job positions in that column (Menejer, Korporativ menejer, Anderrayter, Filial rahbari), and reject "Kassir" as unknown.
**Recommendation: two separate fields.**
- `job_role` comes from the CSV, uses a seeded list and drives assignments.
- `access_role` controls permissions.
- On import, a user gets `branch_head` if their job role is flagged as branch head, otherwise `learner`.
- Methodologist and admin can only be granted in the admin UI, so a CSV file can never create an admin.

**What I need from you:** the final job-role list. The mockup has 4 roles; your context also mentions operations staff.

**D6. First passwords for about 6,000 users (gap).**
Local login is specified, but there is no way to get a first password to each learner.
**Recommendation:**
1. When a CSV import is committed, every new user gets a random temporary password.
2. The admin downloads these passwords **once** as a CSV (employee_id, name, branch, temp password) and hands them out through branch heads. The plaintext is never stored.
3. The first login forces a password change.
4. The admin can reset one user's password; the new temporary password is shown once.

An alternative that scales better is to let branch heads reset passwords for their own branch. That is an extra feature; tell me if you want it.

**D7. Dependencies outside the stated stack.** See §8.

**D8. Seed data.**
- Confirm the final front-office product list (your placeholder). The seed uses the 7 modules from the spec.
- Real branch list: for now I'll seed synthetic branches. Real branches are loaded with `cli import-branches branches.csv` (columns: `code, name_uz, name_ru, region_code`). Tell me if you need an admin screen for branches instead.

### 1.2 Mockup details I will build (they fit the spec)

- Wave has three dates: training start, certification deadline (the spec's "deadline"), and Single Window go-live (shown on the learner banner, mockup 1). Wave status (planned / active / completed) is derived from the dates.
- Role × module matrix **per wave** (mockup 9). This is how I read "assign modules to roles and to waves". Core is always included and cannot be unticked.
- Global Elma365 release (mockup 11):
  - "changed" ticks per lesson;
  - impact preview (N learners re-certify in module X, 0 elsewhere);
  - pre-publish checklist: new videos uploaded with the test-environment flag, UZ + RU subtitles present, no pending drafts on changed lessons, pool ≥ 3×N;
  - irreversible publish.
- Per-module test settings (N, pass %, minutes, attempts, cooldown hours) with the "31 / 45" pool indicator (mockup 8).
- Transcode progress %, and a lesson table showing video, subtitle and question state with ▲▼ reordering (mockup 8).
- AI draft review (mockup 7): UZ/RU side by side, source excerpt and span, "Tasdiqlash va keyingisi", and a queue badge with the draft count.
- Two-step CSV import (mockup 10): row-level error report, error CSV download, upsert by employee_id, never deletes.
- User detail (mockup 10): per-module status, the attempt reset from D4, audit journal, "Oxirgi faollik" (last activity).
- Test screen (mockup 3): question navigator (answered / current / "Keyinroq qaytish"), server-synced timer, "Testni yakunlash", screenshot click-to-enlarge (plain CSS lightbox).
- Result page (mockup 4): score donut (SVG), attempts left, retake countdown, remediation list, attempt history.
- Lesson page (mockup 2): caption box, transcript tab with clickable timestamps (first-viewing seek limit still applies), PDF tab, quality selector, subtitle UZ/RU toggle.
- Branch readiness label in reports: "Tayyor" at ≥ 90 % certified (from mockup 6). For "Xavf ostida" and "Tayyor emas" I'll use 60–89 % and < 60 % [DEFAULT].
- Certificate laid out like mockup 5: number `YO-YYYY-NNNNNN`, both languages on one A4 landscape page, module list, release, signatory, QR code.
- The "Elma365 kirish ro'yxati" button is the rule 13 CSV export (mockup 6).

### 1.3 Mockup details I will not build

- The two wave toggles in mockup 9 ("Elma365 roli faqat sertifikat bilan", "Filial rahbari muddati o'tganlarni ko'radi") become fixed behaviour: the access list contains only fully certified learners, and branch heads always see overdue staff.
- "Kompetensiyalar markaziga yozing" (mockup 1) stays as static text. No messaging.
- Drag-and-drop reordering is replaced by ▲▼ buttons. This avoids a DnD library and gives larger click targets.
- Lesson-to-lesson gating (the greyed "Keyingi dars" in mockup 2): the spec does not gate lessons against each other, so "next" stays enabled. Only the test waits for all lessons [DEFAULT].

---

## 2. Repository structure

```
academy_elma/
├── docker-compose.yml        # postgres, api, worker, nginx
├── .env.example              # every setting, documented
├── Makefile                  # build, test, seed, bundle (docker save) for offline install
├── README.md                 # run, offline install, backup/restore
├── docs/PLAN.md
├── backend/
│   ├── Dockerfile            # python:3.12-slim + ffmpeg; used by api and worker
│   ├── requirements*.txt     # pinned dependencies (runtime / dev)
│   ├── alembic.ini · alembic/versions/
│   ├── app/
│   │   ├── main.py           # app factory, routers, error handler (returns codes, never UI text)
│   │   ├── config.py         # env → settings
│   │   ├── db.py             # engine, session, transaction helper
│   │   ├── models/           # org, users, content, progress, assessment, certification, waves, jobs, audit
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── auth/             # AuthBackend interface, LocalAuthBackend (argon2id), sessions, role dependencies
│   │   ├── api/              # auth, learner, verify, integration, media_auth,
│   │   │                     # admin_content, admin_questions, admin_releases, admin_waves, admin_users, reports
│   │   ├── services/         # business rules as plain functions (the pytest targets)
│   │   │   ├── watch.py      #   interval merge, heartbeat crediting, 90 % rule
│   │   │   ├── access.py     #   assignments, prerequisites, test eligibility
│   │   │   ├── assembly.py   #   balanced draw, shuffling
│   │   │   ├── grading.py    #   scoring, pass/fail, item statistics
│   │   │   ├── remediation.py
│   │   │   ├── certificates.py   # issue, supersede, status, operator certificate
│   │   │   ├── releases.py   #   checklist, impact, publish
│   │   │   ├── reports.py    #   status buckets (SQL)
│   │   │   ├── csv_import.py #   UTF-8/BOM/CP1251, "," or ";", validate, upsert
│   │   │   ├── vtt.py        #   WebVTT parse/validate → transcript cues
│   │   │   └── media.py      #   storage paths, ffprobe
│   │   ├── ai/               # QuestionGenerator, AnthropicProvider, NoopProvider, prompt, output schema
│   │   ├── pdf/              # certificate renderer + bundled TTF fonts
│   │   ├── i18n/             # uz.json, ru.json for server-generated text (PDF, CSV headers)
│   │   ├── worker/           # job loop (media lane + general lane), transcode, ai_draft, sweeps
│   │   └── cli.py            # migrate, seed [--demo], create-admin, import-branches
│   └── tests/                # pytest against real PostgreSQL 16
├── frontend/
│   ├── package.json · vite.config.ts · tsconfig.json · index.html
│   ├── scripts/check-i18n.mjs  # uz/ru key and placeholder parity, used keys, ʻ ʼ (runs on every build)
│   ├── tests/                # node:test unit tests (range tracker, Tashkent dates)
│   └── src/
│       ├── main.tsx · App.tsx (routes)
│       ├── api/              # fetch wrapper + typed endpoint functions
│       ├── i18n/             # setup, uz.json (default), ru.json
│       ├── layouts/          # LearnerLayout (top nav), AdminLayout (sidebar), TestLayout (focused)
│       ├── pages/learner/    # Login, ChangePassword, Home, Courses, Module, Lesson, TestIntro, TestTake,
│       │                     # TestResult, Certificates, Faq, Verify, BranchReport
│       ├── pages/admin/      # Reports, Content, LessonEdit, Questions, QuestionEdit, Releases, Waves, Users
│       ├── components/       # VideoPlayer (hls.js + heartbeat + seek guard), QuestionView, StatusBadge,
│       │                     # ProgressBar, Donut, DataTable (+ CSV link), Lightbox …
│       ├── styles/           # tokens.css (colours/spacing taken from the mockups), base.css
│       └── assets/           # logo placeholder, woff2 fonts
└── nginx/
    ├── Dockerfile            # stage 1: build frontend with node; stage 2: nginx + dist
    └── nginx.conf
```

---

## 3. Runtime architecture

| Service | Image | Notes |
|---|---|---|
| `postgres` | `postgres:16` | volume `pgdata` |
| `api` | `academy-api` | `uvicorn --workers 4`; volume `media` |
| `worker` | `academy-api` (cmd `python -m app.worker`) | volume `media`; ffmpeg inside |
| `nginx` | `academy-web` | ports 80 (443 if TLS terminates here); volume `media` read-only |

`media` volume layout: `originals/`, `hls/<asset-uuid>/`, `vtt/`, `pdf/`, `img/`, `certs/`. Stored paths are always UUIDs, never user-supplied filenames.

- **Sessions.** An opaque random token is sent in an `HttpOnly`, `SameSite=Strict` cookie (`Secure` under TLS); only its SHA-256 hash is stored. Idle timeout is 60 min and the absolute limit is 12 h. Login lockout: 5 failures lock the account for 15 min. CSRF protection is SameSite plus a required custom header on writes.
- **Media protection.** nginx `auth_request` calls `/api/v1/internal/media-auth`, which checks the session. The result is cached for 60 s per cookie, so HLS segments don't hit the database each time.
- **Uploads.** The video is sent as a raw streaming `PUT` body (no multipart parsing). nginx allows `client_max_body_size 2100m` with `proxy_request_buffering off` on that route only, and 10 MB elsewhere. The server rejects the upload unless `synthetic_data_confirmed=true` (the UI checkbox also blocks it).
- **Worker.** It claims jobs with `SKIP LOCKED` in two lanes:
  - media lane: one transcode at a time;
  - general lane: AI drafts and operator-certificate re-evaluation.

  Sweeps run every 60 s to finalize expired test attempts and purge expired sessions.
- **Transcode.**
  - ffprobe validates the upload first.
  - One ffmpeg pass produces HLS (H.264/AAC) in 3 renditions: 360p, 480p and 720p, with maxrate ≈ 400 / 700 / 1200 kbps. Screencasts usually come in lower.
  - Segments are 6 s with a 2 s GOP, plus a master playlist.
  - Progress % is parsed from `-progress`.
  - The original MP4 is kept so it can be re-transcoded [DEFAULT].
- **Subtitles.** WebVTT files are attached as `<track>` elements and rendered through the TextTrack API. This gives the custom caption box and the transcript highlight from mockup 2.
- **Time.** Stored in UTC, displayed in Asia/Tashkent. Deadlines are dates and end at the end of that day in Tashkent.
- **Offline delivery.**
  - `make bundle` builds the 2 app images and saves them, together with `postgres:16` and the nginx base, into one tar.
  - On the server: `docker load -i academy.tar && docker compose up -d`.
  - Note: on a machine with no internet, `docker compose up` cannot *build* images (pip and npm need the network), so the offline target must receive pre-built images.
- **The only outbound call in the system** is `AnthropicProvider`. It runs at authoring time only, and only when `ANTHROPIC_API_KEY` is set and the bank allows the egress. Learner routers never import `app.ai`, and a test enforces this.

---

## 4. Database schema

Conventions:
- Primary keys are `bigint` identity (`video_asset` uses a uuid).
- Timestamps are `timestamptz` in UTC.
- Bilingual text is stored in `*_uz` / `*_ru` columns.
- Fixed value sets are PostgreSQL enums.
- Foreign keys use `ON DELETE RESTRICT` unless marked CASCADE.

### Organisation and users
| Table | Key columns |
|---|---|
| `region` | `code` UNIQUE, `name_uz`, `name_ru` |
| `branch` | `code` UNIQUE (e.g. `01-117`), `name_uz`, `name_ru`, `region_id`→region |
| `job_role` | `code` UNIQUE, `name_uz`, `name_ru`, `is_branch_head`, `sort` (D5) |
| `app_user` | `employee_id` UNIQUE (also the login, e.g. `XB-100231`), `full_name`, `branch_id`→branch NULL (HQ staff), `job_role_id`→job_role NULL, `access_role` (learner · branch_head · methodologist · admin), `preferred_language` (uz · ru, default uz), `password_hash`, `must_change_password`, `failed_logins`, `locked_until`, `is_active`, `last_seen_at`, timestamps |
| `user_session` | `token_hash` UNIQUE, `user_id`→app_user CASCADE, `created_at`, `last_used_at`, `expires_at` |
| `user_import` | `uploaded_by`, `filename`, `total_rows`, `valid_rows` jsonb (normalised rows waiting for commit), `errors` jsonb `[{row, employee_id, code, params}]`, `committed_at`, `created_count`, `updated_count` |
| `audit_event` | `at`, `actor_id` NULL (system), `action` (e.g. `user.import`, `attempts.reset`, `cert.issued`, `release.published`, `user.password_reset`, `user.role_changed`), `target_user_id` NULL, `entity`, `entity_id`, `reason` NULL, `data` jsonb |

### Content and releases
| Table | Key columns |
|---|---|
| `course` | `code` UNIQUE, `title_uz`, `title_ru` (one row: Single Window) |
| `module` | `course_id`, `code` UNIQUE, `qprefix` UNIQUE (question number prefix, e.g. `F`), `type` (core · product · faq), `title_uz`, `title_ru`, `sort`, `current_release_id`→elma_release NULL, `test_question_count`=15, `test_pass_pct`=80, `test_time_limit_min`=20, `test_max_attempts`=3, `test_cooldown_hours`=24, `test_published_at` NULL. Partial UNIQUE: only one `core` module |
| `lesson` | `module_id`, `sort`, `title_uz`, `title_ru`. This is the lesson's identity, stable across releases |
| `elma_release` | `code` UNIQUE (e.g. `2026.12`), `notes`, `status` (draft · published), `transition_days`=0 (D2), `created_by/at`, `published_by/at`. Partial UNIQUE: at most one draft |
| `lesson_version` | `lesson_id`, `release_id`, `status` (draft · published · superseded), `video_asset_id` NULL, `vtt_uz_path`, `vtt_ru_path`, `pdf_uz_path` NULL, `pdf_ru_path` NULL, `published_at`, `superseded_at`. UNIQUE(`lesson_id`, `release_id`); partial UNIQUE(`lesson_id`) where published; partial UNIQUE(`lesson_id`) where draft |
| `video_asset` | uuid PK, `original_filename`, `size_bytes`, `status` (uploaded · processing · ready · failed), `progress_pct`, `duration_s`, `width`, `height`, `error`, `synthetic_confirmed_by` NOT NULL, `synthetic_confirmed_at` NOT NULL, `uploaded_by`, `created_at`, `finished_at` |

### Watch progress
| Table | Key columns |
|---|---|
| `lesson_progress` | PK(`user_id`, `lesson_version_id`), `watched` jsonb (merged `[[start, end], …]` in seconds), `watched_s`, `max_position_s`, `last_position_s`, `last_heartbeat_at`, `started_at`, `completed_at` NULL |

### Assessment
| Table | Key columns |
|---|---|
| `question` | `module_id`, `seq` (UNIQUE per module; displayed as `F-031`), `lesson_version_id`→lesson_version, `video_ts_s`, `type` (single · multiple · ordering · screenshot), `text_uz/ru`, `explanation_uz/ru`, `difficulty` 1–3, `status` (draft · approved · retired), `retired_reason` (rejected · manual · lesson_changed) NULL, `image_path` NULL, `origin` (manual · ai), `ai_job_id` NULL, `ai_source_start_s`, `ai_source_end_s`, `ai_source_excerpt`, `stat_attempts`, `stat_correct`, `created_by/at`, `approved_by/at`, `retired_by/at`, `updated_at` |
| `question_option` | `question_id` CASCADE, `sort` (for ordering questions this is the correct order), `text_uz`, `text_ru`, `is_correct` |
| `test_attempt` | `user_id`, `module_id`, `release_id` (module release at start), `status` (in_progress · submitted · expired), `started_at`, `expires_at`, `submitted_at`, `question_count` and `pass_pct` (copied from the module at start), `correct_count`, `score_pct`, `passed`. Partial UNIQUE(`user_id`, `module_id`) where in_progress |
| `attempt_question` | PK(`attempt_id`, `position`), `question_id`, `option_order` int[] (display order), `answer` jsonb NULL (option ids, ordered for ordering questions), `flagged`, `answered_at`, `is_correct` NULL (set at grading) |
| `remediation_item` | `attempt_id`, `user_id`, `lesson_id`, `lesson_version_id`, `span_start_s`, `span_end_s` (D1), `missed_count`, `watched` jsonb, `satisfied_at` NULL, `satisfied_reason` (watched · superseded) NULL |
| `attempt_reset` | `user_id`, `module_id`, `reset_by`, `reason` NOT NULL, `created_at` (D4) |

### Certification
| Table | Key columns |
|---|---|
| `certificate` | `number` UNIQUE (`YO-2026-000123`, from a sequence), `verify_code` (random; printed and embedded in the QR), `kind` (module · operator), `user_id`, `module_id` NULL, `release_id` NULL, `attempt_id` NULL, `score_pct` NULL, `issued_at`, `recert_due_at` NULL, `superseded_at` NULL, `superseded_by_id`→certificate NULL, `covers` bigint[] (operator certificate: the module certificate ids it covers), `snapshot` jsonb (holder name, employee_id, branch, region, modules and releases; the PDF is rendered from this, so later renames don't alter issued certificates), `pdf_path` NULL (cache) |

### Waves and assignments
| Table | Key columns |
|---|---|
| `wave` | `name_uz`, `name_ru`, `training_start`, `deadline`, `go_live` (dates) |
| `wave_branch` | `wave_id` CASCADE, `branch_id` UNIQUE (a branch belongs to at most one wave) |
| `wave_module_role` | PK(`wave_id`, `module_id`, `job_role_id`). Core is implicit for every role |

### Jobs
| Table | Key columns |
|---|---|
| `job` | `kind` (transcode · ai_draft · operator_cert_eval), `lane` (media · general), `payload` jsonb, `status` (queued · running · done · failed), `attempts`, `last_error`, `result` jsonb, `created_by`, `created_at`, `started_at`, `finished_at` |

### Relations
```
region 1─* branch 1─* app_user *─1 job_role
wave 1─* wave_branch *─1 branch          wave 1─* wave_module_role *─1 module / job_role
course 1─* module 1─* lesson 1─* lesson_version *─1 elma_release
                                        lesson_version *─1 video_asset
module 1─* question *─1 lesson_version   question 1─* question_option
app_user 1─* lesson_progress *─1 lesson_version
app_user 1─* test_attempt *─1 module     test_attempt 1─* attempt_question *─1 question
                                        test_attempt 1─* remediation_item
app_user 1─* certificate (→ module, elma_release, test_attempt; operator → covers[])
```

### Derived values (computed on read, never stored)
- **Assigned modules** = Core ∪ {module | (wave of the user's branch, module, user's job_role) ∈ `wave_module_role`}.
- **Module certificate status:**
  - `superseded` if a newer certificate exists;
  - otherwise `recert_required` if `recert_due_at ≤ now`;
  - otherwise `valid` (with a "recertify by" date if `recert_due_at > now`).
- **Operator certificate status:** `superseded` if replaced; otherwise `recert_required` if any covered module certificate is not valid; otherwise `valid`.
- **Learner module status:** certified · recert_required · in_progress · not_started. **Overdue** = wave deadline passed and not certified.
- **Question elma_release** = the release of its `lesson_version`.
- **Question flagged** = `stat_attempts ≥ 30` and % correct < 20 or > 95.

---

## 5. Core rules → implementation

**R1 Content model.**
- The hierarchy is course → module (core | product | faq) → lesson → lesson_version.
- A version holds the video, VTT uz/ru and the optional PDF uz/ru [DEFAULT: one PDF per language, both or neither]. Its release is the lesson's `elma_release`.
- The uz/ru transcript is the text of the VTT cues, shown with timestamps. There is no separate transcript upload [DEFAULT]. The AI form also accepts pasted text (rule 11).

**R2 Prerequisites.**
- Product modules unlock once the learner holds a Core certificate, either valid or awaiting recertification [DEFAULT]. A later Core release does not re-lock products that are already open.
- FAQ is visible to every logged-in user. It has no test, is not part of assignments, allows free seeking and is not tracked [DEFAULT].

**R3 The 90 % rule (server-side).**
The player sends a heartbeat every 15 s, and on pause or unload via `fetch(..., {keepalive: true})`. Each heartbeat carries the ranges actually played since the previous one. With the progress row locked, the server:
1. clips the ranges to `[0, duration]`;
2. before completion, drops anything that starts beyond `max_position + 5 s` (seek block);
3. caps the played seconds this heartbeat can earn at `min(now − last_heartbeat, 30 s) × speed_cap × 1.15`, where `speed_cap` is 1.0 before completion and 2.0 after [DEFAULT: the speed selector only appears after completion, like seeking]. The 15 % jitter allowance is proportional, so sending heartbeats more often never earns extra credit. The first heartbeat only starts the clock, and the resume point is clamped to the seek limit;
4. merges the ranges into `watched` and sets `completed_at` once `watched_s ≥ 0.9 × duration`.

Re-watching a range adds nothing. Two open tabs can't double-count, because the cap uses wall-clock time per row. The client applies the same seek limit for usability, but the server never accepts a completion flag from it.

**R4 Test unlock.**
The test opens when every *current* published lesson version of the module is completed. A release that replaces a lesson resets only that lesson: it gets a new version with no progress.

**R5 Question bank.**
- Approved questions can have their wording fixed. Their answer key and option set cannot change; to change those you retire the question and duplicate it, which keeps item statistics meaningful [DEFAULT].
- Rejecting a draft sets status `retired` with reason `rejected`, so AI acceptance rates stay visible.
- Scoring is all-or-nothing per question [DEFAULT]: multiple choice needs the exact set, ordering needs the exact order.
- AI produces single, multiple and ordering questions only. Screenshot questions are created manually.
- A lesson that never went live can still be deleted, or unmarked from a release, while its only questions are rejected ones: they were never served, so they go with it. Draft or approved questions block deletion.

**R6 Test assembly and attempts.**
- **Pool:** approved questions of the module that are linked to a *published* lesson version. "Publish test" is blocked while the pool is under 3×N, and the same check runs at release publish.
- **Draw:**
  - Targets are ⌊N/3⌋ questions per difficulty; the remainder goes to difficulty 2, then 1.
  - A bucket that runs short is filled from the adjacent difficulty.
  - Questions are picked at random within each bucket, and the question order is shuffled.
  - Options are shuffled, except in screenshot questions (D3).
  - An ordering question never starts in the correct order.
- **Snapshot:** settings are copied onto the attempt when it starts.
- **Timer:** the server holds `expires_at`. Answers are autosaved per question and accepted until `expires_at + 30 s` (to allow for network latency). Unanswered questions count as wrong. The worker finalizes abandoned attempts.
- **Attempt cycle:** attempts are counted per cycle. A cycle starts at the learner's latest certificate for that module or the latest attempt reset, whichever is later.
  - A pass in the current cycle blocks further attempts.
  - So does a certificate with no recertification pending: once Phase 4 issues the certificate, the new cycle opens only when a release sets `recert_due_at`.
- **Eligibility:** the check returns *all* blocking reasons (prerequisite, lessons, not published, attempts used, cooldown until T, remediation x/y), so the UI can show both conditions the way mockup 4 does.
- **No answer key in learner payloads:** learners see options by display position and send their answers the same way. The server maps positions to option ids. Option ids are never sent, because they follow the authored order, which is the answer to an ordering question.
- **Item statistics:** each graded attempt adds one to every question it served, and adds a correct to each question answered right. Expired and reset attempts count too, with unanswered questions counted as wrong.

**R7 Remediation.**
- On a fail, each missed question (wrong or unanswered) points to its linked lesson, and one item is created per lesson, with a span per D1.
- The result page lists the lessons, how many questions were missed in each, and the spans. Correct answers and explanations are never sent.
- The next attempt requires every item to be satisfied **and** the cooldown to have passed.

**R8 Certificates.**
- **Module certificate on pass:** it gets a number and a random verify code, a snapshot is stored, and the learner's previous certificate for that module is superseded.
- **Operator certificate:** issued automatically once Core and every assigned module hold valid certificates. It is reissued (the old one superseded) after any recertification, and when assignments change for a learner who is complete.
  - A module assigned later, which the learner hasn't passed yet, does not invalidate the operator certificate itself. It does keep the learner off the access list (rule 13) until they pass it.
  - A certificate earned on an attempt that started before a release replaced that module's lessons needs renewal at once, the same as every other certificate on the old content.
- **PDF:**
  - Rendered with ReportLab on A4 landscape, uz and ru on one page, laid out like mockup 5.
  - Fonts are bundled and cover ʻ, ʼ and Cyrillic.
  - The QR code points to `{PUBLIC_BASE_URL}/verify/{number}?c={code}`.
  - The PDF is generated on first download and cached.
- **Verification page:**
  - It is public, but needs the number **and** the code [DEFAULT]. Certificate numbers are sequential, so without the code anyone on the intranet could enumerate them to collect names and branches.
  - It shows holder, branch, certificate type, modules, date, release and current status.

**R9 Release versioning.** Publishing runs as one transaction:
1. Run the checklist.
2. Draft versions become published; the old versions become superseded.
3. Each affected module gets `current_release = R`.
4. Module certificates in affected modules issued on an older release get `recert_due_at = now + transition_days`.
5. Questions linked to superseded versions are retired with reason `lesson_changed`.
6. Open remediation items on superseded versions are closed.
7. Write the audit event.

By construction, certificates of other modules are not touched. Recertification means watching the replaced lessons (new versions) and passing the test again in a fresh cycle.
- **Edits allowed without a release** (no recertification): titles, ordering, replacing subtitles or PDFs.
- **Replacing a video** always goes through a release.
- **Deleting a lesson** is only possible before its first publish [DEFAULT].

> Sequencing note: content can't go live without a release, so the *minimal* release flow (create draft → publish lessons) moves into Phase 2. Phase 3 adds the question-bank parts:
> - the checklist items "no pending drafts on changed lessons" and "pool ≥ 3×N";
> - steps 5 and 6 above.
>
> The impact preview and the recertification effects came in Phase 4.

**R10 Assignments.**
- A wave has a name (uz/ru), three dates, a list of branches and a role × module matrix.
- Learners whose branch is in no wave see no modules (FAQ only).
- A learner sees their assigned modules, the wave deadline and the go-live date.

**R11 AI drafting.**
- **Interface:** `QuestionGenerator` exposes `enabled` and `generate(GenerationInput) -> list[DraftQuestion]`.
- **`AnthropicProvider`:**
  - uses the official SDK, with the model taken from `ANTHROPIC_MODEL` (default `claude-opus-5-5`);
  - requests structured JSON output and validates it against a schema;
  - sends the optional reference PDF as a document block, so no PDF-parsing library is needed;
  - handles refusal stop reasons.
- **Activation:** the provider is used only when `ANTHROPIC_API_KEY` is set. Otherwise `NoopProvider` is used and the button is hidden.
- **Execution:** generation runs as a worker job, because calls take tens of seconds.
- **Server-side validation:** question types, option counts, exactly one correct answer for single choice, timestamps within the video, both languages present. Invalid items are dropped and counted.
- **Saving:** drafts are saved with `origin=ai`, plus the source excerpt and span (mockup 7).
- **As built:**
  - `generate()` returns the draft list wrapped with the count of malformed items, the model that answered and whether a fallback model ran.
  - Requests use streaming, `effort: medium`, and server-side `fallbacks: "default"`, so a policy decline is retried on Anthropic's recommended model.
  - A failed job stores a stable error code (`ai.refused`, `ai.truncated`, `ai.rate_limited`, `ai.unreachable`, ...) for the UI.
  - One drafting job per lesson version at a time. Drafts attach to the version whose transcript was used.
  - Items repeating a question already in the module are dropped as duplicates.

**R12 Item statistics.**
Counters are updated in the grading transaction. A question is flagged at ≥ 30 attempts with < 20 % or > 95 % correct, and the question bank has a filter for flagged questions.

**R13 Access gate.**
- **Endpoint:** `GET /api/v1/certification-status?employee_id=` with an `X-API-Key` header. Keys come from the env variable `CERT_STATUS_API_KEYS` and are compared in constant time.
- **Response:** the operator certificate status, plus, for each core and product module: assigned, status (`valid` · `recert_required` · `missing`), certificate number, release, issued_at and recert_due_at.
- The endpoint is read-only.
- **Access-list CSV:** per wave or branch, the users holding a valid operator certificate.
- No Elma365 integration.

**Roles and auth.**
The `AuthBackend` interface has one implementation, `LocalAuthBackend`. Other details follow D5 and D6. No LDAP code.

**Reports.**
- Computed live in SQL; about 6,000 users × ~6 modules is small.
- **Per-learner buckets** (mutually exclusive): certified (all assigned modules valid), recert_required, in_progress, not_started. Overdue is a separate flag.
- With a module filter set, buckets are computed for that module.
- **Screens:** KPIs, a by-branch table and per-user drill-down, filtered by wave, region, module and job role.
- **CSV on every table:** UTF-8 with BOM and `;` as separator, so Excel with a ru or uz locale opens it directly [DEFAULT].
- Branch heads use the same endpoints, forced to their own branch.

**i18n.**
- Every UI string, learner and admin, lives in `uz.json` / `ru.json`, with uz as the default.
- API errors are codes plus parameters, translated in the browser.
- Server-generated text (PDF, CSV headers) comes from backend uz/ru JSON files.
- Content validation requires both languages before a question can be approved or a release published.
- Uzbek Latin uses ʻ (U+02BB) and ʼ (U+02BC). I'll draft the copy; it needs a native-speaker review at the bank.

---

## 6. API endpoints (`/api/v1`)

Roles: L = any logged-in learner (includes branch_head), BH = branch_head, M = methodologist, A = admin.

**Auth**
| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/auth/login` | public | employee_id + password → session cookie |
| POST | `/auth/logout` | any | end session |
| GET | `/auth/me` | any | profile, access_role, must_change_password |
| POST | `/auth/change-password` | any | required on first login |
| PATCH | `/auth/me` | any | preferred_language |

**Learner**
| Method | Path | Purpose |
|---|---|---|
| GET | `/me/dashboard` | wave, deadline, go-live, x/y certified, path, resume item, certificate summary |
| GET | `/me/modules` | assigned modules with status/progress |
| GET | `/me/modules/{id}` | lessons + progress, test card (settings, eligibility reasons, attempts left, cooldown_until), attempt history |
| GET | `/me/lessons/{id}` | player payload: version, HLS/VTT/PDF URLs, duration, progress, remediation spans, prev/next |
| POST | `/me/lessons/{id}/heartbeat` | played ranges → coverage, max_position, completed, remediation state |
| POST | `/me/modules/{id}/attempts` | start (or resume) an attempt |
| GET | `/me/attempts/{id}` | questions without answer keys, saved answers, flags, `expires_at`, `server_now` |
| PUT | `/me/attempts/{id}/answers/{position}` | autosave answer / flag |
| POST | `/me/attempts/{id}/submit` | grade |
| GET | `/me/attempts/{id}/result` | score, pass/fail, remediation items, next attempt time, history |
| GET | `/me/certificates` | list with status |
| GET | `/me/certificates/{number}/pdf` | PDF download |
| GET | `/me/faq` · `/me/faq/{lesson_id}` | FAQ list and player payload (untracked) |

**Public / integration / internal**
| Method | Path | Purpose |
|---|---|---|
| GET | `/verify/{number}?c=` | certificate verification (no login) |
| GET | `/certification-status?employee_id=` | access gate (`X-API-Key`) |
| GET | `/internal/media-auth` | nginx `auth_request` |
| GET | `/health` | liveness/DB check |

**Reports (A everything; BH forced to own branch)**
| Method | Path | Purpose |
|---|---|---|
| GET | `/reports/summary` | KPI buckets (filters: wave, region, module, job_role) |
| GET | `/reports/branches` | per-branch rows + readiness |
| GET | `/reports/users` | per-user rows (filters + status) |
| GET | `/reports/users/{id}` | drill-down: modules, progress, attempts |
| GET | `/exports/access-list.csv` | A: certified users per wave/branch (rule 13) |

Every report endpoint also accepts `?format=csv`.

**Admin: content (M, A; module create/reorder A only)**
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/admin/modules` | list / create |
| PATCH | `/admin/modules/{id}` | titles, type, test settings |
| POST | `/admin/modules/reorder` | order |
| POST | `/admin/modules/{id}/test/publish` · `/unpublish` | blocked while pool < 3×N |
| GET/POST | `/admin/modules/{id}/lessons` | list / create (new lesson goes into the open draft release) |
| POST | `/admin/modules/{id}/lessons/reorder` | order |
| GET/PATCH/DELETE | `/admin/lessons/{id}` | edit titles; delete only if never published |
| PUT | `/admin/lesson-versions/{id}/video?synthetic_data_confirmed=true` | raw MP4 body ≤ 2 GB → transcode job |
| PUT | `/admin/lesson-versions/{id}/subtitles/{uz\|ru}` | VTT (validated) |
| PUT/DELETE | `/admin/lesson-versions/{id}/pdf/{uz\|ru}` | reference PDF |
| GET | `/admin/lesson-versions/{id}/transcript?lang=` | parsed cues (timestamp picking, AI form) |
| GET | `/admin/video-assets/{id}` | transcode status / progress |

**Admin: questions (M, A)**
| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/modules/{id}/questions` | filter by status, lesson, flagged, origin; includes item stats |
| GET | `/admin/modules/{id}/pool` | active pool by difficulty, required 3×N, publishable |
| POST | `/admin/modules/{id}/questions` | create draft |
| GET/PATCH | `/admin/questions/{id}` | read / edit |
| PUT | `/admin/questions/{id}/image` | screenshot image |
| POST | `/admin/questions/{id}/approve` · `/reject` · `/retire` · `/duplicate` | workflow |
| GET | `/admin/ai/status` | `{enabled}`; UI hides the feature when false |
| POST | `/admin/lesson-versions/{id}/ai-drafts` | enqueue drafting (lesson transcript or pasted text + optional reference PDF/text) |
| GET | `/admin/jobs/{id}` | job status/result |

**Admin: releases (A)**
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/admin/releases` | timeline / create draft |
| GET/PATCH | `/admin/releases/{id}` | modules + lessons with changed flags, impact, checklist / edit code, notes, transition_days |
| POST/DELETE | `/admin/releases/{id}/lessons/{lesson_id}` | mark/unmark changed (creates/discards draft version) |
| POST | `/admin/releases/{id}/publish` | irreversible |

**Admin: waves (A)**
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/admin/waves` | list / create |
| GET/PATCH | `/admin/waves/{id}` | detail / names and dates |
| PUT | `/admin/waves/{id}/branches` | branch set |
| PUT | `/admin/waves/{id}/assignments` | role × module matrix |
| GET | `/admin/regions` · `/admin/branches` · `/admin/job-roles` | reference lists |

**Admin: users (A)**
| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/users` | search (name/employee_id), branch, status |
| GET/PATCH | `/admin/users/{id}` | detail (statuses, attempts, audit) / access_role, is_active |
| POST | `/admin/users/{id}/reset-password` | new temp password, shown once |
| POST | `/admin/users/{id}/reset-attempts` | `{module_id, reason}` (D4) |
| GET | `/admin/users/import/template.csv` | CSV template |
| POST | `/admin/users/import` | raw CSV → validation report + import id |
| GET | `/admin/users/import/{id}/errors.csv` | error rows |
| POST | `/admin/users/import/{id}/commit` | upsert valid rows → summary + one-time temp-password CSV |

---

## 7. Pages

**Learner (top-nav layout: Bosh sahifa · Kurslarim · Sertifikatlarim · Savol-javob, plus Hisobot for branch heads)**
| Route | Page | Mockup |
|---|---|---|
| `/login`, `/change-password` | login, forced password change | — |
| `/` | home: wave banner, deadline, x/y certified, learning path, resume card, certificates, FAQ hint | 1 |
| `/courses` | assigned modules | 1 (cards) |
| `/courses/:moduleId` | module: lessons, progress, test card with lock reasons, attempts | 2 (side panel) |
| `/courses/:moduleId/lessons/:lessonId` | player, 90 % notice, transcript, PDF, outline | 2 |
| `/courses/:moduleId/test` | test intro: N, minutes, threshold, attempts left | — |
| `/attempts/:id` | test taking | 3 |
| `/attempts/:id/result` | pass / fail + remediation + history | 4 |
| `/certificates` | certificates, status, PDF download | 5 (PDF) |
| `/faq`, `/faq/:lessonId` | FAQ videos (untracked) | — |
| `/verify/:number` | public verification | — |
| `/reports` | branch head: own-branch report + drill-down | 6 (scoped) |

**Admin / methodologist (sidebar layout)**
| Route | Page | Who | Mockup |
|---|---|---|---|
| `/admin/reports` (+ `/users/:id`) | readiness by wave/region/branch, drill-down, CSV, access list | A | 6 |
| `/admin/content` (+ `/modules/:id`) | modules, lessons, upload, subtitles, PDF, test settings | M, A | 8 |
| `/admin/content/lessons/:id` | lesson versions, transcode status, transcript | M, A | 8 |
| `/admin/questions` (+ `/:id`) | bank per module, pool indicator, item stats/flags, draft review queue, editor | M, A | 7 |
| AI dialog in `/admin/questions` | "Transkriptdan qoralama yaratish" (hidden if disabled) | M, A | 7 |
| `/admin/waves` | waves, dates, branches, role × module matrix | A | 9 |
| `/admin/users` | list, CSV import wizard, user detail, actions, audit | A | 10 |
| `/admin/releases` | timeline, changed lessons, impact, checklist, publish | A | 11 |

Layouts target 1366×768 and up, with click targets of at least 44 px and the colour tokens taken from the mockups.

**As built (Phase 6, learner side):**
- All learner routes above exist except `/reports` (branch head), which comes with Phase 7. The test page has its own focused top bar instead of a separate layout file.
- **Player:** hls.js light build (no subtitle/DRM code; Safari plays HLS natively), loaded only on lesson pages. Own controls: play, −10 s, time, Sub UZ / Sub RU, speed, quality (Auto + renditions), full screen. Captions and the transcript come from the `<track>` cues.
  - First viewing: seeking past the furthest point reached (+5 s, as on the server) snaps back with a message, and the speed stays 1×.
  - Heartbeats: one baseline on open, then every 15 s while playing, and on pause, end, tab hidden and leaving the page (`keepalive`). One request at a time; ranges from a failed request go out with the next one. A `lesson.version_changed` answer reloads the lesson.
  - It resumes at the last position. `?t=` (from the result page) opens a remediation fragment, which is also marked on the seek bar.
- **Test:** the countdown uses the offset between `server_now` and the browser clock. Answers are saved per question as they change (newest change wins, retried while offline); at 0:00 the test is submitted with what was saved.
- **Result:** attempts left, cooldown and the retake button appear only on the module's latest attempt, not on older results.
- **i18n:** Uzbek (default) and Russian JSON files, Russian plural forms, Uzbek ʻ (U+02BB) and ʼ (U+02BC). The language follows the user's `preferred_language` and is saved on change.
- No dependencies beyond §8. Unit tests use Node's built-in runner; the browser walkthrough was run with a Playwright outside the repo.

**As built (Phase 7, staff side):**
- All routes in the table above exist, plus `/reports` and `/reports/users/:id` for branch heads inside the learner layout (the "Hisobot" menu item). The `/admin/*` screens are one lazily loaded bundle.
- **Roles:** admins land on reports, methodologists on the question bank. A methodologist who opens an admin-only address is sent back to the bank; anyone else who opens `/admin` goes to the learner home. The server still checks every request.
- **i18n:** all staff strings live in the same `uz.json`/`ru.json` as the learner ones (≈ 830 keys). Where an API error code needs different wording for staff (e.g. `test.pool_too_small` with the have/need numbers), an `admin.errors.*` key overrides `errors.*` inside the panel. The build-time check also covers keys built at runtime (`roles.*`, `bank.type.*`, …) and every admin error code.
- **Users:** the import check shows row errors translated from their codes, with the server's error CSV as a download; after commit the one-time passwords are offered once as a CSV file and never shown again. The reset reason is required in the UI as well as on the server.
- **Releases:** the publish confirmation counts the module certificates that will need renewal (a sum over modules; people with two touched modules would be counted twice by a people count).
- **Content:** once a video is ready, the upload area folds into a "replace" button. The preview uses the same player as learners with tracking off, and clicking a transcript line seeks the preview.
- **Question bank:** an approved question allows wording changes only (the server rejects key changes); "Nusxa olish" makes an editable draft copy. The AI button only appears when `/admin/ai/status` says AI is enabled; the PDF option is offered when the lesson has at least one guide PDF (the server accepts one or both).
- **nginx:** `client_max_body_size` is 51 MB on the lesson PDF upload route so that the API's own 50 MB check (with a translated message) is what an oversized PDF hits; other routes keep 10 MB, video keeps 2.1 GB.
- **Not built from the mockups:** mockup 9's "Kirish nazorati" toggles. Those rules (access list = certified only; branch heads see overdue people) are fixed in the system, so switches would have no effect.
- Walkthrough (Playwright, outside the repo) at 1366×768 against the compose stack with synthetic data: admin reports/users/waves/content/releases, methodologist bank, branch-head report, learner smoke test, the AI dialog against mocked endpoints; no console or CSP errors and no external requests.

---

## 8. Dependencies outside the stated stack [DECIDE]

| Package | Why | Alternative considered |
|---|---|---|
| `uvicorn` | ASGI server; FastAPI can't run without one | — |
| `psycopg[binary]` (v3) | PostgreSQL driver for SQLAlchemy | asyncpg: async adds complexity with no gain at this load |
| `argon2-cffi` | argon2id hashing (named in the spec) | — |
| `reportlab` | certificate PDF; its built-in QR widget means no separate QR library | WeasyPrint needs Pango system libraries |
| `anthropic` | official SDK for `AnthropicProvider`; imported only when the key is set | hand-written HTTP calls (more code to own) |
| `pytest`, `httpx2` | tests (FastAPI's `TestClient` uses httpx2, the successor of httpx); dev only | — |
| `react-router-dom` | routing | hand-rolled router |
| `i18next` | required peer of react-i18next | — |
| `typescript`, `@vitejs/plugin-react`, `@types/react`, `@types/react-dom` | standard Vite React toolchain; dev only | — |
| Inter font files (OFL) | bundled UI/PDF font with Uzbek ʻ ʼ and Cyrillic | another OFL font if you have the mockups' font |

Deliberately **not** used: Celery/Redis (Postgres job table instead), python-multipart (raw-body uploads), recharts (no chart needed; donut and bars are SVG/CSS), UI kits, state libraries, axios.

---

## 9. Tests (pytest, real PostgreSQL 16)

**Required by you:**
1. **90 % rule:** interval merge; wall-clock cap; seek block before completion and free seeking after; completion at exactly 90 %; replays don't count twice; two tabs don't count twice.
2. **Prerequisite:** product modules locked without a Core certificate; unlocked with a valid or recert-pending one.
3. **Pool ≥ 3×N:** test publish blocked at 3N−1 and allowed at 3N; release publish behaves the same.
4. **Attempt limit + cooldown:** 4th attempt refused; retake refused before 24 h and allowed after (injected clock); a reset starts a new cycle.
5. **Remediation:** retake refused until every item is satisfied; only playback after the failure counts; correct answers never appear in any learner payload.
6. **Pass threshold:** 12/15 = 80 % passes and 11/15 fails; unanswered counts as wrong; expired attempts are graded.
7. **Delta recert:** a release touching module B flips only B's certificates and leaves A's valid; the operator certificate becomes recert_required; passing B again issues new B and operator certificates; `transition_days` is honoured.
8. **Certification-status API:** 401 with no key or a wrong key; valid / recert_required / missing; unknown employee gives 404; GET only.

**Also:** assembly balancing and shuffling; CSV import (encodings, delimiters, duplicates, unknown branch/role, upsert never deletes); auth (lockout, forced change); report scoping for branch heads; learner modules never import `app.ai`.

---

## 10. Other open questions (non-blocking)

1. Readiness bands: is "Xavf ostida" 60–89 %?
2. TLS: does our nginx terminate it with a bank-issued certificate, or is there an upstream load balancer?
3. Which browsers and versions run on branch PCs? hls.js needs current Chromium/Edge/Firefox; IE is not supported.
4. What are typical branch link speeds and how many people watch at once? This tunes the bitrate ladder.
5. Official logo files (SVG/PNG), certificate signatory name and title, the internal verification base URL, and whether the number prefix is "YO".
6. AI: will the bank allow egress to api.anthropic.com for authoring, and will infosec approve sending transcripts (test environment, synthetic data) outside the network?
7. Explanations: rule 7 means they are never shown to learners, because they would reveal answers. They are for methodologists only. Please confirm.
8. Should original MP4s be kept after transcoding (up to 2 GB each)? Default: keep.

---

## 11. What each phase delivers

| Phase | Delivers | pytest focus |
|---|---|---|
| 1 | compose (4 services), full schema + initial Alembic migration, auth (login, sessions, lockout, forced change, roles), CSV import (validate → commit → temp passwords), CLI: seed (synthetic regions, branches, job roles, users, 7 modules, 1 wave), create-admin, import-branches | auth, import, scoping |
| 2 | module/lesson CRUD, minimal release draft → publish, raw upload + transcode worker with progress, VTT/PDF, heartbeat + player API | 90 % rule |
| 3 | question bank + approval, pool/publish block, assembly, attempts, timer, grading, cooldown, remediation, item stats | 3×N, attempts + cooldown, remediation, threshold |
| 4 | certificates, PDF, verification, release checklist/impact/recert, certification-status API, exports, report endpoints | delta recert, status API |
| 5 | `QuestionGenerator` + providers + job + draft endpoints | validation of model output, Noop hides the feature, no LLM import from learner routes |
| 6 | learner UI uz/ru | — (manual walkthrough against `done_when`) |
| 7 | admin / methodologist / branch-head UI | — |

**Demo for `done_when`.** `cli seed --demo` adds:
- short generated test-pattern videos, VTT files and ≥ 3×N synthetic approved questions for Core and one product module;
- a demo role assigned Core + that product.

The demo modules use cooldown 0 (configurable per module), so "fail → remediate → pass → product → both certificates → verify PDF" fits in one sitting. A release publish on the product module then shows that only its certified learners flip.
