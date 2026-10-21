"""Operator commands: ``python -m app.cli <command>``.

  seed                         reference data (course, regions, job roles, 7 modules)
  seed --synthetic --password  + synthetic branches, ~245 users and a demo wave (demo only)
  seed --demo                  + generated demo lessons for Core and Farovon with approved
                                 demo questions and published tests (needs ffmpeg and an
                                 existing admin; demo only)
  create-admin                 bootstrap an admin or methodologist (prints a temp password)
  import-branches FILE         upsert branches from CSV: code, name_uz, name_ru, region_code
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, seed_data
from app.auth import passwords
from app.models import (
    AppUser,
    Branch,
    Course,
    ElmaRelease,
    JobRole,
    Module,
    Region,
    VideoAsset,
    Wave,
    WaveBranch,
    WaveModuleRole,
)
from app.models.enums import AccessRole, Language, ModuleType, QuestionType, ReleaseStatus
from app.services import audit, content, csvio, media, questions, releases
from app.services.users import (
    EMPLOYEE_ID_RE,
    access_role_for,
    issue_temp_password,
    normalize_employee_id,
)


@dataclass
class SeedCounts:
    created: int = 0
    existing: int = 0


def seed_reference(db: Session) -> dict[str, SeedCounts]:
    """Idempotent: only inserts what is missing, never overwrites admin edits."""
    counts = {name: SeedCounts() for name in ("course", "regions", "job_roles", "modules")}

    course = db.scalar(select(Course).where(Course.code == seed_data.COURSE["code"]))
    if course is None:
        course = Course(**seed_data.COURSE)
        db.add(course)
        db.flush()
        counts["course"].created += 1
    else:
        counts["course"].existing += 1

    have = set(db.scalars(select(Region.code)))
    for code, name_uz, name_ru in seed_data.REGIONS:
        if code in have:
            counts["regions"].existing += 1
            continue
        db.add(Region(code=code, name_uz=name_uz, name_ru=name_ru))
        counts["regions"].created += 1

    have = set(db.scalars(select(JobRole.code)))
    for code, name_uz, name_ru, sort, is_head in seed_data.JOB_ROLES:
        if code in have:
            counts["job_roles"].existing += 1
            continue
        db.add(
            JobRole(code=code, name_uz=name_uz, name_ru=name_ru, sort=sort, is_branch_head=is_head)
        )
        counts["job_roles"].created += 1

    have = set(db.scalars(select(Module.code)))
    for sort, (code, qprefix, mtype, title_uz, title_ru) in enumerate(seed_data.MODULES, start=1):
        if code in have:
            counts["modules"].existing += 1
            continue
        db.add(
            Module(
                course_id=course.id,
                code=code,
                qprefix=qprefix,
                type=ModuleType(mtype),
                title_uz=title_uz,
                title_ru=title_ru,
                sort=sort,
            )
        )
        counts["modules"].created += 1
    db.flush()
    return counts


def seed_synthetic(db: Session, password: str, rng_seed: int = 2026) -> dict[str, int]:
    """Invented branches, people and one demo wave. Never run this on production data."""
    regions = {r.code: r for r in db.scalars(select(Region))}
    roles = {r.code: r for r in db.scalars(select(JobRole))}
    modules = {m.code: m for m in db.scalars(select(Module))}
    branches_by_code = {b.code: b for b in db.scalars(select(Branch))}

    planned: list[tuple[Branch, list[str]]] = []
    created_branches = 0

    def ensure_branch(code: str, name_uz: str, name_ru: str, region_code: str) -> Branch:
        nonlocal created_branches
        branch = branches_by_code.get(code)
        if branch is None:
            branch = Branch(
                code=code, name_uz=name_uz, name_ru=name_ru, region_id=regions[region_code].id
            )
            db.add(branch)
            branches_by_code[code] = branch
            created_branches += 1
        return branch

    tashkent: list[Branch] = []
    for i, (uz, ru) in enumerate(seed_data.TASHKENT_DISTRICTS, start=101):
        branch = ensure_branch(f"01-{i}", f"{uz} BXM", f"ЦБУ {ru}", "01")
        tashkent.append(branch)
        planned.append((branch, seed_data.TASHKENT_BRANCH_STAFF))
    for region_code, uz, ru in seed_data.REGIONAL_CITIES:
        branch = ensure_branch(f"{region_code}-101", f"{uz} BXM", f"ЦБУ {ru}", region_code)
        planned.append((branch, seed_data.REGIONAL_BRANCH_STAFF))
    db.flush()

    rng = random.Random(rng_seed)
    password_hash = passwords.hash_password(password)  # one hash for all demo accounts
    existing_ids = set(db.scalars(select(AppUser.employee_id)))
    created_users = 0
    number = 100001
    for branch, staff in planned:
        for role_code in staff:
            employee_id = f"XB-{number}"
            number += 1
            if employee_id in existing_ids:
                continue
            full_name, language = _synthetic_person(rng)
            role = roles[role_code]
            db.add(
                AppUser(
                    employee_id=employee_id,
                    full_name=full_name,
                    branch_id=branch.id,
                    job_role_id=role.id,
                    access_role=access_role_for(role),
                    preferred_language=language,
                    password_hash=password_hash,
                    must_change_password=False,
                )
            )
            created_users += 1

    wave = db.scalar(select(Wave).where(Wave.name_uz == seed_data.DEMO_WAVE["name_uz"]))
    created_waves = 0
    if wave is None:
        today = clock.utcnow().date()
        cfg = seed_data.DEMO_WAVE
        wave = Wave(
            name_uz=cfg["name_uz"],
            name_ru=cfg["name_ru"],
            training_start=today + timedelta(days=cfg["training_start_offset_days"]),
            deadline=today + timedelta(days=cfg["deadline_offset_days"]),
            go_live=today + timedelta(days=cfg["go_live_offset_days"]),
        )
        db.add(wave)
        db.flush()
        created_waves = 1
        in_a_wave = set(db.scalars(select(WaveBranch.branch_id)))
        for branch in tashkent:
            if branch.id not in in_a_wave:
                db.add(WaveBranch(wave_id=wave.id, branch_id=branch.id))
        for role_code, module_codes in seed_data.DEMO_ASSIGNMENTS.items():
            for module_code in module_codes:
                db.add(
                    WaveModuleRole(
                        wave_id=wave.id,
                        module_id=modules[module_code].id,
                        job_role_id=roles[role_code].id,
                    )
                )
    db.flush()
    return {"branches": created_branches, "users": created_users, "waves": created_waves}


def _synthetic_person(rng: random.Random) -> tuple[str, Language]:
    female = rng.random() < 0.5
    if rng.random() < 0.15:
        first = rng.choice(seed_data.RU_FEMALE_NAMES if female else seed_data.RU_MALE_NAMES)
        return f"{first} {rng.choice(seed_data.RU_SURNAMES)}", Language.ru
    first = rng.choice(seed_data.FEMALE_NAMES if female else seed_data.MALE_NAMES)
    surname = rng.choice(seed_data.SURNAMES) + ("a" if female else "")
    language = Language.ru if rng.random() < 0.15 else Language.uz
    return f"{first} {surname}", language


def seed_demo_content(db: Session, actor_id: int, seconds: int | None = None) -> dict[str, int]:
    """Generated test-pattern lessons with synthetic subtitles, published as one release."""
    from app.worker.transcode import transcode_asset  # needs ffmpeg; imported only here

    code = seed_data.DEMO_RELEASE_CODE
    existing = db.scalar(select(ElmaRelease).where(ElmaRelease.code == code))
    if existing is not None:
        if existing.status == ReleaseStatus.draft:  # an earlier run stopped half-way
            raise ValueError(f"release {code} is still a draft; delete it, then run again")
        return {"lessons": 0}
    if releases.get_draft(db) is not None:
        raise ValueError("a draft release is open; publish or delete it first")
    seconds = seconds or seed_data.DEMO_VIDEO_SECONDS
    release = releases.create_release(db, code, "Demo content (synthetic videos)", actor_id)
    modules = {m.code: m for m in db.scalars(select(Module))}
    created = 0
    for module_code, titles in seed_data.DEMO_LESSONS.items():
        for n, (title_uz, title_ru) in enumerate(titles, start=1):
            module = modules[module_code]
            _, version = releases.create_lesson(db, module, title_uz, title_ru, actor_id)
            asset_id = uuid.uuid4()
            source = media.original_path(asset_id)
            _generate_demo_video(source, seconds)
            asset = VideoAsset(
                id=asset_id,
                original_filename=f"demo-{module_code.lower()}-{n}.mp4",
                size_bytes=source.stat().st_size,
                synthetic_confirmed_by=actor_id,
                synthetic_confirmed_at=clock.utcnow(),
                uploaded_by=actor_id,
            )
            db.add(asset)
            db.flush()
            version.video_asset_id = asset.id
            version.vtt_uz_path = media.write_new(
                "vtt", f"{version.id}-uz", ".vtt", _demo_vtt(f"{title_uz}: {{n}}-qism", seconds)
            )
            version.vtt_ru_path = media.write_new(
                "vtt", f"{version.id}-ru", ".vtt", _demo_vtt(f"{title_ru}: часть {{n}}", seconds)
            )
            transcode_asset(db, asset)
            created += 1
    releases.publish(db, release.id, actor_id)
    return {"lessons": created, "questions": seed_demo_questions(db, actor_id)}


# Single, single, multiple, ordering: the mix of question types in the demo bank.
_DEMO_TYPES = (
    QuestionType.single, QuestionType.single, QuestionType.multiple, QuestionType.ordering,
)  # fmt: skip


def seed_demo_questions(db: Session, actor_id: int) -> int:
    """3 x N approved arithmetic questions per demo module, then publish the test.

    Arithmetic, so whoever runs the demo can pass or fail on purpose. Cooldown is set
    to 0 so fail → re-watch → pass fits in one sitting.
    """
    rng = random.Random(2026)
    created = 0
    for code in seed_data.DEMO_LESSONS:
        module = db.scalar(select(Module).where(Module.code == code))
        live = content.published_lessons(db, module.id)
        for i in range(questions.POOL_FACTOR * module.test_question_count):
            lesson, version = live[i % len(live)]
            duration = int(content.duration_of(version) or 1)
            q_type = _DEMO_TYPES[i % len(_DEMO_TYPES)]
            text_uz, text_ru, options, explain_uz, explain_ru = _demo_question(q_type, rng)
            q = questions.create_draft(
                db, module=module, lesson=lesson, q_type=q_type, text_uz=text_uz,
                text_ru=text_ru, explanation_uz=explain_uz, explanation_ru=explain_ru,
                difficulty=i % 3 + 1, video_ts_s=(i * 7) % duration, options=options,
                actor_id=actor_id,
            )  # fmt: skip
            questions.approve(db, q, actor_id)
            created += 1
        module.test_cooldown_hours = 0
        questions.publish_test(db, module, actor_id)
    db.flush()
    return created


def _demo_question(q_type: QuestionType, rng: random.Random):
    """(text_uz, text_ru, options, explanation_uz, explanation_ru) for one demo question."""
    option = questions.OptionData
    if q_type == QuestionType.single:
        a, b = rng.randint(2, 20), rng.randint(2, 20)
        right = a + b
        values = [right, *rng.sample([right - 2, right - 1, right + 1, right + 2, right + 10], 3)]
        rng.shuffle(values)
        return (
            f"[Demo] {a} + {b} nechaga teng?", f"[Демо] Сколько будет {a} + {b}?",
            [option(str(v), str(v), v == right) for v in values],
            f"[Demo] {a} + {b} = {right}.", f"[Демо] {a} + {b} = {right}.",
        )  # fmt: skip
    if q_type == QuestionType.multiple:
        values = rng.sample(range(2, 40, 2), 2) + rng.sample(range(1, 40, 2), 2)
        rng.shuffle(values)
        return (
            "[Demo] Qaysi sonlar juft?", "[Демо] Какие числа чётные?",
            [option(str(v), str(v), v % 2 == 0) for v in values],
            "[Demo] Juft son 2 ga qoldiqsiz boʻlinadi.", "[Демо] Чётное число делится на 2.",
        )  # fmt: skip
    values = sorted(rng.sample(range(1, 100), 4))  # authored order is the answer
    shown = ", ".join(map(str, values))
    return (
        "[Demo] Sonlarni kichigidan kattasiga tartiblang.",
        "[Демо] Расположите числа по возрастанию.",
        [option(str(v), str(v)) for v in values],
        f"[Demo] Toʻgʻri tartib: {shown}.", f"[Демо] Правильный порядок: {shown}.",
    )


def seed_demo_learner(db: Session) -> str | None:
    """One learner assigned exactly Core + Farovon (the demo content), in a wave of their own.

    Returns their one-time password, or None if they already exist.
    """
    cfg = seed_data.DEMO_PATH
    if db.scalar(select(AppUser.id).where(AppUser.employee_id == cfg["employee_id"])):
        return None
    region = db.scalar(select(Region).where(Region.code == cfg["region_code"]))
    branch = db.scalar(select(Branch).where(Branch.code == cfg["branch_code"]))
    if branch is None:
        branch = Branch(
            code=cfg["branch_code"], name_uz=cfg["branch_uz"], name_ru=cfg["branch_ru"],
            region_id=region.id,
        )  # fmt: skip
        db.add(branch)
    wave = db.scalar(select(Wave).where(Wave.name_uz == cfg["wave_uz"]))
    if wave is None:
        today = clock.today()
        wave = Wave(
            name_uz=cfg["wave_uz"], name_ru=cfg["wave_ru"],
            training_start=today - timedelta(days=1), deadline=today + timedelta(days=30),
            go_live=today + timedelta(days=45),
        )  # fmt: skip
        db.add(wave)
    db.flush()
    if db.scalar(select(WaveBranch).where(WaveBranch.branch_id == branch.id)) is None:
        db.add(WaveBranch(wave_id=wave.id, branch_id=branch.id))
    role = db.scalar(select(JobRole).where(JobRole.code == cfg["job_role"]))
    for code in cfg["products"]:
        module = db.scalar(select(Module).where(Module.code == code))
        key = {"wave_id": wave.id, "module_id": module.id, "job_role_id": role.id}
        if db.get(WaveModuleRole, key) is None:
            db.add(WaveModuleRole(**key))
    user = AppUser(
        employee_id=cfg["employee_id"], full_name=cfg["full_name"], branch_id=branch.id,
        job_role_id=role.id, access_role=access_role_for(role), password_hash="",
    )  # fmt: skip
    temp = issue_temp_password(user)
    db.add(user)
    db.flush()
    audit.record(db, "user.created", target_user_id=user.id, data={"source": "cli-demo"})
    return temp


def _generate_demo_video(target, seconds: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
         "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", str(target)],
        check=True, timeout=600,
    )  # fmt: skip


def _demo_vtt(template: str, seconds: int, cue_s: int = 8) -> bytes:
    lines = ["WEBVTT", ""]
    for n, start in enumerate(range(0, seconds, cue_s), start=1):
        end = min(start + cue_s, seconds)
        timing = f"00:{start // 60:02d}:{start % 60:02d}.000 --> "
        timing += f"00:{end // 60:02d}:{end % 60:02d}.000"
        lines += [timing, "[Demo] " + template.format(n=n), ""]
    return "\n".join(lines).encode("utf-8")


def create_staff(db: Session, employee_id: str, full_name: str, role: AccessRole) -> str:
    """Create an admin/methodologist; returns the one-time password to hand over."""
    if role not in (AccessRole.admin, AccessRole.methodologist):
        raise ValueError("role must be admin or methodologist")
    employee_id = normalize_employee_id(employee_id)
    if not EMPLOYEE_ID_RE.match(employee_id):
        raise ValueError(f"invalid employee_id: {employee_id!r}")
    if db.scalar(select(AppUser).where(AppUser.employee_id == employee_id)) is not None:
        raise ValueError(f"user {employee_id} already exists")
    user = AppUser(
        employee_id=employee_id,
        full_name=full_name.strip(),
        access_role=role,
        password_hash="",
    )
    temp = issue_temp_password(user)
    db.add(user)
    db.flush()
    audit.record(db, "user.created", target_user_id=user.id, data={"source": "cli", "role": role})
    return temp


def import_branches(db: Session, data: bytes) -> tuple[int, int, list[str]]:
    """Upsert branches by code. Returns (created, updated, problems)."""
    text = csvio.decode(data)
    header_line = next((line for line in text.splitlines() if line.strip()), "")
    required = ("code", "name_uz", "name_ru", "region_code")
    reader = csv.DictReader(
        io.StringIO(text), delimiter=csvio.detect_delimiter(header_line, required)
    )
    reader.fieldnames = [csvio.normalize_header(n) for n in reader.fieldnames or []]
    missing = [c for c in required if c not in reader.fieldnames]
    if missing:
        return 0, 0, [f"missing columns: {', '.join(missing)}"]
    regions = {r.code: r for r in db.scalars(select(Region))}
    branches = {b.code: b for b in db.scalars(select(Branch))}
    created = updated = 0
    problems: list[str] = []
    for row in reader:
        code = (row.get("code") or "").strip().upper()
        if not code:
            continue
        region = regions.get((row.get("region_code") or "").strip())
        name_uz, name_ru = (row.get("name_uz") or "").strip(), (row.get("name_ru") or "").strip()
        if region is None or not name_uz or not name_ru:
            problems.append(f"line {reader.line_num}: {code}: unknown region or empty name")
            continue
        branch = branches.get(code)
        if branch is None:
            branch = Branch(code=code, name_uz=name_uz, name_ru=name_ru, region_id=region.id)
            branches[code] = branch
            db.add(branch)
            created += 1
        elif (branch.name_uz, branch.name_ru, branch.region_id) != (name_uz, name_ru, region.id):
            branch.name_uz, branch.name_ru, branch.region_id = name_uz, name_ru, region.id
            updated += 1
    db.flush()
    return created, updated, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="reference data; --synthetic adds demo people")
    p_seed.add_argument("--synthetic", action="store_true")
    p_seed.add_argument("--password", help="password for all synthetic users (required)")
    p_seed.add_argument("--demo", action="store_true", help="generated demo lessons (needs ffmpeg)")

    p_admin = sub.add_parser("create-admin", help="bootstrap an admin or methodologist")
    p_admin.add_argument("--employee-id", required=True)
    p_admin.add_argument("--full-name", required=True)
    p_admin.add_argument("--role", choices=["admin", "methodologist"], default="admin")

    p_branches = sub.add_parser("import-branches", help="upsert branches from CSV")
    p_branches.add_argument("path")

    args = parser.parse_args(argv)
    from app.db import SessionLocal  # only connect when a command actually runs

    with SessionLocal() as db:
        if args.command == "seed":
            if args.synthetic and not args.password:
                parser.error("--synthetic needs --password")
            for name, c in seed_reference(db).items():
                print(f"{name}: {c.created} created, {c.existing} already present")
            if args.synthetic:
                for name, n in seed_synthetic(db, args.password).items():
                    print(f"synthetic {name}: {n} created")
            if args.demo:
                admin = db.scalar(
                    select(AppUser)
                    .where(AppUser.access_role == AccessRole.admin)
                    .order_by(AppUser.id)
                )
                if admin is None:
                    print("error: create an admin first (create-admin)", file=sys.stderr)
                    return 1
                try:
                    result = seed_demo_content(db, admin.id)
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 1
                print(f"demo lessons: {result['lessons']} created and published")
                if result["lessons"]:
                    print(f"demo questions: {result['questions']} approved; tests published")
                temp = seed_demo_learner(db)
                if temp is not None:
                    employee_id = seed_data.DEMO_PATH["employee_id"]
                    print(f"demo learner {employee_id} (Core + Farovon) created.")
                    print(f"Temporary password (shown once, change at first login): {temp}")
        elif args.command == "create-admin":
            try:
                temp = create_staff(db, args.employee_id, args.full_name, AccessRole(args.role))
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print(f"{args.role} {normalize_employee_id(args.employee_id)} created.")
            print(f"Temporary password (shown once, must be changed at first login): {temp}")
        elif args.command == "import-branches":
            with open(args.path, "rb") as fh:
                created, updated, problems = import_branches(db, fh.read())
            print(f"branches: {created} created, {updated} updated, {len(problems)} problems")
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
        db.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
