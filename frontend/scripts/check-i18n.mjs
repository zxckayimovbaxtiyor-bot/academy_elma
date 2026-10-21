// Translation check, run before every build (no dependencies):
//  - uz.json and ru.json have the same keys and the same {{placeholders}};
//  - every key the code uses exists (static t("…") calls plus the dynamic families below);
//  - Uzbek uses the modifier letters ʻ (U+02BB) and ʼ (U+02BC), never a plain apostrophe.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src/", import.meta.url));
const PLURAL = /_(zero|one|two|few|many|other)$/;
const load = (lang) => JSON.parse(readFileSync(join(root, "i18n", `${lang}.json`), "utf8"));

function flatten(obj, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === "object") flatten(v, `${prefix}${k}.`, out);
    else out[`${prefix}${k}`] = v;
  }
  return out;
}

const langs = { uz: flatten(load("uz")), ru: flatten(load("ru")) };
const base = (key) => key.replace(PLURAL, "");
const bases = Object.fromEntries(Object.entries(langs).map(([l, d]) => [l, new Set(Object.keys(d).map(base))]));
const problems = [];

for (const [a, b] of [["uz", "ru"], ["ru", "uz"]]) {
  for (const key of bases[a]) if (!bases[b].has(key)) problems.push(`${key}: missing in ${b}.json`);
}

const placeholders = (text) => new Set([...String(text).matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]));
const byBase = (dict) => {
  const out = {};
  for (const [key, text] of Object.entries(dict)) {
    const set = (out[base(key)] ??= new Set());
    for (const name of placeholders(text)) set.add(name);
  }
  return out;
};
const [uzVars, ruVars] = [byBase(langs.uz), byBase(langs.ru)];
for (const key of Object.keys(uzVars)) {
  const u = [...uzVars[key]].sort().join(",");
  const r = [...(ruVars[key] ?? [])].sort().join(",");
  if (ruVars[key] && u !== r) problems.push(`${key}: placeholders differ (uz: ${u || "-"}, ru: ${r || "-"})`);
}

for (const [key, text] of Object.entries(langs.uz)) {
  if (/['`‘’]/.test(text)) problems.push(`${key}: uz text uses an apostrophe instead of ʻ / ʼ`);
}

function sources(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}
const used = new Set();
for (const file of sources(root)) {
  const code = readFileSync(file, "utf8");
  for (const m of code.matchAll(/\bt\(\s*"([a-z0-9_.]+)"/g)) used.add(m[1]);
  for (const m of code.matchAll(/\bt\(\s*[\w.?!=" ]*?\?\s*"([a-z0-9_.]+)"\s*:\s*"([a-z0-9_.]+)"/g)) {
    used.add(m[1]); // t(flag ? "a.b" : "c.d")
    used.add(m[2]);
  }
  for (const m of code.matchAll(/i18nKey="([a-z0-9_.]+)"/g)) used.add(m[1]);
}

// Keys built at runtime (`state.${key}` and the like) and the API error codes the screens can get.
const expand = (prefix, names) => names.map((n) => `${prefix}${n}`);
const statuses = ["valid", "recert_required", "superseded", "missing"];
const dynamic = [
  ...expand("state.", ["certified", "in_progress", "not_started", "recert_required", "locked"]),
  ...expand("cert_status.", statuses),
  ...expand("home.cert_", statuses),
  ...expand("verify.status_", statuses),
  ...expand("verify.hint_", statuses),
  ...expand("player.sub_", ["uz", "ru"]),
  ...expand("player.sub_short_", ["uz", "ru"]),
  ...expand("lesson.pdf_", ["uz", "ru"]),
  ...expand("intro.rule_", ["random", "timer", "autosave", "unanswered", "no_answers", "after_fail"]),
  ...expand("reason.", [
    "module_no_test", "prerequisite_core", "lessons_incomplete", "test_not_published",
    "attempt_in_progress", "already_passed", "attempts_exhausted", "cooldown", "remediation_pending",
  ]),
  ...expand("errors.", [
    "network", "request.invalid", "auth.invalid_credentials", "auth.locked", "auth.required",
    "auth.forbidden", "auth.password_change_required", "auth.csrf", "password.current_invalid",
    "password.too_short", "password.too_long", "password.equals_employee_id", "password.same_as_current",
    "module.not_found", "module.locked", "module.no_test", "lesson.not_found", "lesson.version_changed",
    "lesson.not_tracked", "attempt.not_found", "attempt.expired", "attempt.finished", "attempt.in_progress",
    "attempt.answer_invalid", "attempt_question.not_found", "test.not_available", "test.pool_too_small",
    "certificate.not_found",
  ]),
  // Staff screens (Phase 7).
  ...expand("roles.", ["learner", "branch_head", "methodologist", "admin"]),
  ...expand("reports.kpi.", ["total", "certified", "in_progress", "not_started", "recert_required", "overdue"]),
  ...expand("reports.readiness.", ["ready", "at_risk", "not_ready"]),
  ...expand("waves.status.", ["planned", "active", "completed"]),
  ...expand("content.type.", ["core", "product", "faq"]),
  ...expand("content.type_long.", ["core", "product", "faq"]),
  ...expand("releases.kind.", ["draft", "current", "archive"]),
  ...expand("release.problem.", [
    "video_missing", "video_not_ready", "vtt_uz_missing", "vtt_ru_missing", "vtt_uz_exceeds_video",
    "vtt_ru_exceeds_video", "pdf_pair_incomplete", "questions_pending",
  ]),
  ...expand("lesson_admin.subtitles_", ["uz", "ru"]),
  ...expand("lesson_admin.pdf_", ["uz", "ru"]),
  ...expand("bank.show.", ["draft", "approved", "flagged", "retired", "all"]),
  ...expand("bank.status.", ["draft", "approved", "retired"]),
  ...expand("bank.retired.", ["rejected", "manual", "lesson_changed"]),
  ...expand("bank.type.", ["single", "multiple", "ordering", "screenshot"]),
  ...expand("bank.rule.", ["single", "multiple", "ordering", "screenshot"]),
  ...expand("bank.difficulty_", ["1", "2", "3"]),
  ...expand("bank.problem.", [
    "options_count", "needs_exactly_one_correct", "needs_two_correct_and_one_wrong", "text_missing",
    "option_text_missing", "explanation_uz_missing", "explanation_ru_missing", "image_missing",
  ]),
  ...expand("bank.ai_drop.", [
    "type_not_allowed", "difficulty_invalid", "text_missing", "explanation_missing", "option_text_missing", "too_long",
    "options_count", "needs_exactly_one_correct", "needs_two_correct_and_one_wrong", "timestamp_missing",
    "timestamp_outside_video", "duplicate", "over_count", "malformed",
  ]),
  ...expand("audit.", [
    "user_created", "user_updated", "user_password_changed", "user_password_reset", "user_role_changed",
    "user_activated", "user_deactivated", "attempts_reset", "cert_issued",
  ]),
  ...expand("audit.source.", ["csv", "cli", "cli-demo", "admin"]),
  ...expand("import.", [
    "employee_id_empty", "employee_id_invalid", "employee_id_duplicate", "full_name_empty", "full_name_too_long",
    "branch_code_empty", "branch_not_found", "region_empty", "region_mismatch", "role_empty", "role_unknown",
    "language_invalid",
  ]),
  ...expand("admin.errors.", ["test.pool_too_small", "module.not_found"]),
  ...expand("errors.", [
    "user.cannot_modify_self", "user.branch_required", "user.not_found", "reset.reason_required",
    "import.empty", "import.missing_columns", "import.file_too_large", "import.already_committed", "import.conflict",
    "import.not_found", "wave.dates_invalid", "wave.branch_in_other_wave", "wave.branch_unknown", "wave.job_role_unknown",
    "wave.module_not_assignable", "wave.not_found", "module.code_taken", "module.qprefix_taken", "module.core_exists",
    "course.missing", "reorder.mismatch", "lesson.already_published", "lesson.has_questions", "lesson.no_version",
    "lesson.not_published", "lesson.already_in_release", "lesson.new_in_release", "version.not_draft",
    "version.superseded", "version.not_found", "lesson_version.superseded", "lesson_version.not_found",
    "video.synthetic_confirmation_required", "video.too_large", "video.empty", "video.unreadable",
    "video.no_video_stream", "video.too_long", "video.transcode_failed", "video.not_found", "vtt.too_large",
    "vtt.not_utf8", "vtt.not_webvtt", "vtt.bad_timing", "vtt.end_before_start", "vtt.unordered", "vtt.no_cues",
    "vtt.exceeds_video", "pdf.invalid", "pdf.too_large", "image.invalid", "image.too_large", "question.invalid",
    "question.incomplete", "question.answer_key_locked", "question.lesson_not_in_module",
    "question.lesson_version_retired", "question.not_approved", "question.not_draft", "question.not_screenshot",
    "question.retired", "question.timestamp_after_video", "question.not_found", "release.code_invalid",
    "release.code_taken", "release.draft_exists", "release.no_draft", "release.not_draft", "release.not_empty",
    "release.not_ready", "release.not_found", "release_lesson.not_found", "subtitles.not_found", "job.not_found",
    "ai.disabled", "ai.job_in_progress", "ai.transcript_missing", "ai.text_missing", "ai.pdf_missing",
    "ai.reference_too_large", "ai.refused", "ai.truncated", "ai.rate_limited", "ai.unreachable", "ai.auth_failed",
    "ai.permission_denied", "ai.request_rejected", "ai.api_error", "ai.output_invalid",
  ]),
];
for (const key of [...used, ...dynamic]) {
  for (const lang of Object.keys(langs)) {
    if (!bases[lang].has(key)) problems.push(`${key}: used but missing in ${lang}.json`);
  }
}

if (problems.length) {
  console.error(`i18n: ${problems.length} problem(s)\n  ${problems.join("\n  ")}`);
  process.exit(1);
}
console.log(`i18n: ok (${bases.uz.size} keys, ${used.size} used directly, ${dynamic.length} dynamic)`);
