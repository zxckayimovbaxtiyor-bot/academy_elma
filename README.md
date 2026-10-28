# Yagona oyna Akademiyasi

Internal learning platform for the Single Window (Yagona oyna) rollout on Elma365: videos, tests, certificates, and per-release recertification. It runs on-prem with Docker Compose and needs no internet at runtime.

The design, schema, endpoints and phases are in [docs/PLAN.md](docs/PLAN.md).

For the prepared Windows installation without Docker, see [LOCAL-RUN.md](LOCAL-RUN.md).
The audit, staged modernization plan and completed first-stage fixes are recorded in
[docs/MODERNIZATION.md](docs/MODERNIZATION.md).

## Interactive practice

The Practice module adds a versioned scenario engine, guided training,
server-graded practical exams, a visual RU/UZ constructor,
and branch-scoped analytics. Open `/practice` or `/admin/practice`.
Existing certification rules stay unchanged until an author explicitly requires practice.

After applying migrations, `python -m app.cli seed --practice` from `backend/` publishes
the synthetic consumer-loan example in Core (requires an existing admin).
`seed --demo` also includes it. No real bank integrations are used.

See [the architecture audit](docs/PRACTICE_ARCHITECTURE.md) and
[implementation, API, author/learner instructions and verification](docs/PRACTICE_IMPLEMENTATION.md).

**Status: Phase 7 (staff screens).** Done so far:
- Phase 1: schema, auth, CSV user import, seed, worker and containers.
- Phase 2: modules and lessons, Elma365 releases (draft → publish), video upload with HLS transcoding, subtitles and PDFs, and the server-side 90 % watch rule.
- Phase 3: question bank with approval, test publishing (pool ≥ 3×N), test assembly, timed attempts, grading, attempt limit and cooldown, remediation fragments, item statistics and admin attempt reset.
- Phase 4: certificates (module and operator) with PDF and QR verification, per-module recertification after a release, the certification-status API, waves, readiness reports with CSV, the access list and the learner home page.
- Phase 5: AI drafting of questions from a lesson's transcript, with every draft checked on the server and reviewed by a methodologist.
- Phase 6: the learner web app in Uzbek (default) and Russian: home, courses, lessons with the video player, tests, results with remediation, certificates, FAQ and the public verification page.
- Phase 7: the admin, methodologist and branch-head screens, also in Uzbek and Russian: reports, users and CSV import, waves, content and video upload, Elma365 releases, and the question bank with AI drafts.

## Run (machine with internet)

Copy the settings file, then set `POSTGRES_PASSWORD` and `PUBLIC_BASE_URL` in `.env`:

```sh
cp .env.example .env
```

Both values are required: Compose refuses to start with an empty database password
or public address. Use a unique random hex password (at least 48 characters) so it
can also be embedded safely in the database URL. Direct Python startup requires
an explicit `DATABASE_URL`; there is no shared fallback password.

Protected media are checked per resource and per request: assignments, Core prerequisite,
published versions and ownership of test images. API responses and protected files use
`Cache-Control: no-store`; nginx does not cache a positive session authorization.

Build and start postgres, api, worker and nginx; load the course, regions, job roles and the 7 modules; create the first admin (it prints a one-time password):

```sh
make up
make seed
make admin ID=ADM-0001 NAME="Full Name"
```

Command blocks in this file carry no inline `#` comments, because macOS's default shell (zsh) does not treat `#` as a comment when commands are pasted. Quote passwords containing `!` with single quotes in zsh.

Everyone opens `http://<server>/` and signs in with their employee ID. A first login with the one-time password has to change it before anything else works. Learners and branch heads land on the learning home page; admins and methodologists land in the panel at `/admin`.

Demo data, never for production:
- `make demo-seed PASSWORD=...` adds 25 synthetic branches, 245 synthetic employees and one demo wave. Every account shares that password.
- `docker compose exec api python -m app.cli seed --demo` generates five short test-pattern lessons for Core and Farovon (with synthetic uz/ru subtitles), transcodes them and publishes them as release 2026.11. An admin must exist first.
  - It also writes 45 approved demo questions per module (3×N for N = 15) and publishes both tests, with the cooldown set to 0.
  - The questions are simple arithmetic, so whoever runs the demo can pass or fail on purpose.
  - It creates the learner `DEMO-0001` (one-time password printed once), assigned exactly Core + Farovon. That covers the whole path: fail → re-watch → pass Core → Farovon → both module certificates and the operator certificate → PDF and verification.

## Learner web app

Served by nginx from the same origin as the API. Every string is in `frontend/src/i18n/uz.json` and `ru.json`; the language switch (UZ/RU) is remembered per user.

- **Home:** wave, deadline, x/y modules certified, the learning path (Core first; product modules locked until Core is certified), the lesson to resume, certificate status, FAQ.
- **Lesson:** HLS video with quality choice, uz/ru subtitles, transcript and the reference PDF.
  - On a first viewing the player blocks seeking past the furthest point reached and keeps 1× speed. The page says the lesson counts at 90 %; after completion both are free.
  - It reports what was actually played every 15 s, on pause and when the page is left. The server decides what counts (see the 90 % rule in the plan).
- **Test:** question navigator, a countdown driven by the server's clock, answers saved as they are given (the newest change wins; retried if the network drops), "come back later" flags. At 0:00 the test is submitted with the saved answers.
- **Result:** score, attempts left, the retake countdown, the lesson fragments to re-watch (each opens the lesson at the fragment) and the attempt history. Correct answers are never shown.
- **Certificates:** PDF download and a link to the verification page. The QR code on the PDF opens the same page.

Videos are H.264/AAC, which Chrome, Edge, Yandex Browser and Firefox on Windows all decode.

**Frontend development:** with the stack running (`make up`), `cd frontend && npm ci && npm run dev` serves the app on port 5173, proxying `/api` and `/media` to nginx on port 80.

## Staff screens

The panel at `/admin` is a separate bundle, so learners never download it. What each role sees:

| Role | Screens |
|---|---|
| Admin | Reports · Content · Question bank · Waves · Users · Elma365 releases |
| Methodologist | Content · Question bank (an admin-only address sends them back to the bank) |
| Branch head | "Hisobot" in the learner menu: the same report, limited by the server to their own branch, with CSV export |

- **Reports:** readiness by wave, region, module and role. KPI tiles (click one to list those people), a branch table (≥ 90 % certified = ready), a learner table with search, and a drill-down per person. CSV export and the Elma365 access list (admin only).
- **Users:** CSV import in two steps. The check lists row errors in the reader's language and offers them as a CSV; the commit offers the new one-time passwords once as a file. Per person: module status, attempt reset (a reason is required and goes to the audit log), password reset (the temporary password is shown once), permission level, deactivation, and the audit journal.
- **Waves:** names, the three dates (start ≤ deadline ≤ go-live), branches (a branch can be in one wave only; the picker shows where the others are) and the role × module matrix (Core is always required).
- **Content:** modules, lessons, ordering, test settings with the bank size needed. Per lesson: MP4 upload with the mandatory synthetic-data confirmation, upload progress and transcode status, a preview with the transcript, uz/ru subtitles and the optional PDFs.
- **Elma365 releases:** a timeline; in the draft, tick the lessons whose screens changed. The page shows who will have to recertify (only in the touched modules), the transition period, and a checklist that unlocks publishing.
- **Question bank:** queue per module (drafts, approved, flagged by item statistics, retired), an editor for the four question types, approval with the server's reasons when it refuses, wording-only edits on approved questions (duplicate to change the key), and the pool banner that publishes or withdraws the test. With AI enabled, "Transkriptdan qoralama yaratish" asks for drafts and shows what was created and why items were dropped.

## Content workflow

Content only reaches learners through an Elma365 release:

1. An admin opens a draft release (Elma365 relizlari → Yangi reliz).
2. A methodologist adds lessons (Kontent → module → Dars qoʻshish). For a live lesson whose screen changed, the admin ticks it in the draft release instead, which opens a new version.
3. Upload the MP4 (up to 2 GB) and tick the synthetic-data confirmation. The worker transcodes it to 360p/480p/720p HLS.
4. Upload the uz and ru WebVTT subtitles, plus an optional reference PDF in both languages (up to 50 MB each).
5. Publish. The checklist blocks publishing until every lesson has a ready video and both subtitle files.

Subtitle and PDF fixes on live lessons don't need a release. Replacing a live video always does.

On publish, questions about a replaced video are retired, and open remediation on it is closed. The checklist also blocks publishing while:
- draft questions on a changed lesson are still waiting for review;
- a module with a published test would end up with fewer than 3×N approved questions.

## Assessment

Question bank (methodologist or admin, under `/api/v1/admin`):
- Questions are written against a lesson and a moment in its video (`video_ts_s`). A question starts as a draft. Approving it needs both languages, both explanations and, for screenshot questions, the image.
- Once a question is approved, its wording can still be fixed, but its answer key cannot change. To change the key, retire the question and duplicate it.
- `POST /modules/{id}/test/publish` is refused while the pool (approved questions on live lessons) holds fewer than 3×N.

Learners (under `/api/v1/me`):
- `GET /modules/{id}` returns `test.status`: whether the learner can start, and every reason they can't (lessons, prerequisite, attempts used, cooldown end, remediation x/y).
- `POST /modules/{id}/attempts` starts an attempt, or resumes the open one. The test has N questions, balanced across difficulty 1–3, with options shuffled (screenshot options stay in A–D order).
- Answers autosave per question (`PUT /attempts/{id}/answers/{position}`) and are accepted until 30 s after the deadline.
- `POST /attempts/{id}/submit` returns the score.
- On a fail, the result lists the video fragments to re-watch. Correct answers and explanations are never sent.
- The next attempt needs both the cooldown and every fragment watched. An admin can grant a fresh cycle with a mandatory reason (`POST /api/v1/admin/users/{id}/reset-attempts`).

## AI question drafting (optional)

Off unless `ANTHROPIC_API_KEY` is set. Without a key, `GET /api/v1/admin/ai/status` returns `{"enabled": false}`, the UI hides the feature, and nothing leaves the network.

With a key:
- A methodologist calls `POST /api/v1/admin/lesson-versions/{id}/ai-drafts` with `{"count": 10, "types": ["single", "multiple", "ordering"]}`. The source is the lesson's uz/ru subtitles by default; it can instead be `{"source": "text", "text": "..."}` (pasted text). Optionally add `"include_lesson_pdf": true` (the lesson's reference PDFs) or `"reference_text"`.
- The worker calls Claude (`ANTHROPIC_MODEL`, default `claude-opus-5-5`) with structured JSON output. Progress shows on `GET /api/v1/admin/jobs/{id}`.
- Every returned item is checked before it is saved: allowed type, option count, exactly one correct answer for single choice, a source span inside the video, both languages. Invalid items are dropped and counted by reason in the job result.
- Saved items are **drafts** with `origin=ai`, the source span and the quoted transcript excerpt. They go through the same approval as hand-written questions. Screenshot questions are always written by hand.
- If the model declines a request, it is retried server-side on Anthropic's recommended fallback model. If every model declines, the job fails with `ai.refused`.

Learner-facing code never imports the AI package; a test enforces this.

## Certificates and access

- Passing a test issues a **module certificate** (`YO-2026-000123`). Once Core and every module assigned to the learner hold valid certificates, an **operator certificate** follows.
- The PDF (A4 landscape, uz + ru, bundled Inter font) is drawn on first download from a snapshot taken at issue time, so later renames never change it. Its QR code opens `{PUBLIC_BASE_URL}/verify/{number}?c={code}`. Verification is public but needs the printed code as well as the number.
- **Recertification:** publishing a release flags only the certificates of the modules it touched. With `transition_days` > 0 the old certificate stays valid until that date ("recertify by"); with 0 (the default) it needs renewal at once. Learners re-watch the changed lessons and pass that module's test again in a fresh attempt cycle.
- **Access gate:** `GET /api/v1/certification-status?employee_id=...` with an `X-API-Key` header (keys in `CERT_STATUS_API_KEYS`). It returns the operator status and, per module, `valid` · `recert_required` · `missing`.
- **Access list:** `GET /api/v1/exports/access-list.csv` (admin, optionally `?wave_id=` or `?branch_id=`) lists learners who hold a valid operator certificate *and* a valid certificate for every module assigned to them now.
- **Reports** (`/api/v1/reports/summary`, `/branches`, `/users`, `/users/{id}`, all with `?format=csv`): one bucket per learner (certified · recert_required · in_progress · not_started), an overdue flag after the wave deadline, and branch readiness (≥ 90 % certified = ready, 60–89 % at risk). Branch heads always get their own branch.
- **Waves** (`/api/v1/admin/waves`): dates, branches (each in at most one wave) and the role × module matrix. Changing branches or the matrix makes the worker re-check the operator certificates of the learners concerned.

Set `CERT_SIGNATORY_NAME` to print the signatory's name on certificates.

## Offline server

`docker compose up` cannot build images without internet (pip and npm need the network), so the bank server gets pre-built images:

On a machine with internet, build the bundle (`dist/academy-1.0.tar`):

```sh
make bundle VERSION=1.0
```

Copy the tar, `docker-compose.yml` and `.env` to the server, then:

```sh
docker load -i academy-1.0.tar
APP_VERSION=1.0 docker compose up -d
```

The platform makes no outbound calls at runtime:
- nginx sends `Content-Security-Policy: default-src 'self'`. The web app bundles its fonts and scripts and has no inline script.
- The `academy-web` image holds only nginx and the built app; Node.js is used only while building it.
- The API's Swagger page (which loads from a CDN) only exists with `APP_ENV=dev`.

## Users and branches

- **HR CSV import** (admin, Xodimlar → CSV import; API: `POST /api/v1/admin/users/import`, then `…/import/{id}/commit`). The template is linked on the page.
  - Columns: `employee_id, full_name, branch_code, region, role, preferred_language`.
  - Accepts UTF-8 (with or without BOM) or Windows-1251, separated by `;` or `,`.
  - Existing employees are updated and never deleted.
  - New employees get one-time passwords, returned once as a CSV.
- `role` is the **job role** (Menejer, Anderrayter, …), which decides module assignment. The permission level follows from it: "Filial rahbari" becomes branch head, everyone else a learner. Methodologist and admin can only be granted by an admin.
- **Branches:** `docker compose exec api python -m app.cli import-branches /path/branches.csv` with columns `code, name_uz, name_ru, region_code`.

## Tests

pytest runs inside the api image, against a throwaway `academy_test` database:

```sh
make test
```

Without Docker, run from `backend/` with `TEST_DATABASE_URL=postgresql+psycopg://USER@HOST:5432/academy_test pytest`. The suite refuses to run on a database whose name doesn't end in `_test`.

The web app is checked whenever it is built (`cd frontend && npm run build`, and inside the `academy-web` image build):
- `tsc` type check;
- `npm run check:i18n`: uz and ru have the same keys and placeholders, every key the code uses exists (including keys built at runtime and the API error codes), and Uzbek text uses ʻ and ʼ rather than apostrophes;
- `npm test`: unit tests of the played-range tracker behind the heartbeats and of the Tashkent-time formatting (Node's built-in runner, no extra packages).

## Backup

```sh
docker compose exec -T postgres pg_dump -U academy academy > academy.sql
```

Also back up the `academy_media` Docker volume (videos, subtitles, PDFs).
