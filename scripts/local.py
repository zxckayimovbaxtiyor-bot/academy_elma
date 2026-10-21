"""Manage the isolated Windows development installation (no system services)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".local"
TOOLS = ROOT / "scripts" / "local-tools" / "node_modules"
PG = TOOLS / "@embedded-postgres" / "windows-x64" / "native" / "bin"
BACKEND = ROOT / "backend"
URL = "http://127.0.0.1:5173"
PG_PORT = 54329


def run(*args, capture=False):
    return subprocess.run([str(a) for a in args], cwd=BACKEND, check=True,
                          text=True, encoding="utf-8", capture_output=capture)


def configure():
    STATE.mkdir(exist_ok=True)
    config_file = STATE / "config.json"
    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
    else:
        config = {"database_password": secrets.token_hex(24)}
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
    os.environ.update(
        DATABASE_URL=f"postgresql+psycopg://academy:{config['database_password']}@127.0.0.1:{PG_PORT}/academy",
        MEDIA_ROOT=str(STATE / "media"), PUBLIC_BASE_URL=URL, APP_ENV="dev",
        APP_TIMEZONE="Asia/Tashkent", COOKIE_SECURE="false", PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8", ANTHROPIC_API_KEY="",
    )
    os.environ["PATH"] = os.pathsep.join([
        str(TOOLS / "ffmpeg-static"),
        str(TOOLS / "ffprobe-static" / "bin" / "win32" / "x64"),
        os.environ["PATH"],
    ])
    (STATE / "media").mkdir(exist_ok=True)
    return config


def healthy():
    try:
        with urllib.request.urlopen(URL + "/api/v1/health", timeout=2) as response:
            return json.load(response) == {"status": "ok"}
    except Exception:
        return False


def start_database(config):
    data = STATE / "postgres"
    if not (data / "PG_VERSION").exists():
        password_file = STATE / "pg-password.tmp"
        password_file.write_text(config["database_password"], encoding="utf-8")
        try:
            run(PG / "initdb.exe", "-D", data, "-U", "academy", "--encoding=UTF8",
                "--locale=C", "--auth=scram-sha-256", f"--pwfile={password_file}")
        finally:
            password_file.unlink(missing_ok=True)
    status = subprocess.run([str(PG / "pg_ctl.exe"), "-D", str(data), "status"],
                            capture_output=True)
    if status.returncode:
        run(PG / "pg_ctl.exe", "-D", data, "-l", STATE / "postgres.log", "-o",
            f"-h 127.0.0.1 -p {PG_PORT} -c timezone=UTC", "-w", "start")
    import psycopg
    from psycopg import sql
    with psycopg.connect(host="127.0.0.1", port=PG_PORT, user="academy",
                         password=config["database_password"], dbname="postgres",
                         autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='academy'").fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("academy")))


def seed(demo):
    run(sys.executable, "-m", "alembic", "upgrade", "head")
    credentials_file = STATE / "credentials.json"
    credentials = json.loads(credentials_file.read_text()) if credentials_file.exists() else {}
    if "admin" not in credentials:
        run(sys.executable, "-m", "app.cli", "seed")
        result = run(sys.executable, "-m", "app.cli", "create-admin", "--employee-id",
                     "ADM-0001", "--full-name", "Local Administrator", capture=True)
        password = result.stdout.strip().splitlines()[-1].rsplit(": ", 1)[-1]
        credentials["admin"] = {"username": "ADM-0001", "temporary_password": password}
        credentials_file.write_text(json.dumps(credentials, indent=2))
    if demo and "learner" not in credentials:
        demo_password = secrets.token_urlsafe(15)
        run(sys.executable, "-m", "app.cli", "seed", "--synthetic", "--password", demo_password)
        credentials["synthetic_users"] = {"example_username": "XB-100001", "password": demo_password}
        credentials_file.write_text(json.dumps(credentials, indent=2))
        print("Generating five synthetic video lessons and 90 questions...", flush=True)
        result = run(sys.executable, "-m", "app.cli", "seed", "--demo", capture=True)
        print(result.stdout.split("Temporary password")[0], flush=True)
        if "Temporary password" in result.stdout:
            password = result.stdout.strip().splitlines()[-1].rsplit(": ", 1)[-1]
            credentials["learner"] = {"username": "DEMO-0001", "temporary_password": password}
            credentials_file.write_text(json.dumps(credentials, indent=2))


def start(demo):
    config = configure()
    start_database(config)
    seed(demo)
    process_file = STATE / "processes.json"
    processes = json.loads(process_file.read_text()) if process_file.exists() else {}
    if not healthy():
        launch("api", ["-m", "uvicorn", "local_server:app", "--host", "127.0.0.1",
                       "--port", "5173"], processes)
        process_file.write_text(json.dumps(processes, indent=2))
        for _ in range(40):
            if healthy():
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("API failed to start; see .local/api.err.log")
    if not process_alive(processes.get("worker", {})):
        launch("worker", ["-m", "app.worker"], processes)
    process_file.write_text(json.dumps(processes, indent=2))
    print(f"Academy is running: {URL}\nCredentials: {STATE / 'credentials.json'}", flush=True)


def process_alive(record):
    if not record:
        return False
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-Command",
        f"$p = Get-Process -Id {int(record['pid'])} -ErrorAction SilentlyContinue; "
        f"if ($p -and $p.StartTime.ToUniversalTime().Ticks -eq {int(record['start_ticks'])}) {{ exit 0 }}; exit 1",
    ], capture_output=True)
    return result.returncode == 0


def launch(name, args, processes):
    # Start-Process keeps background services independent of the launching terminal.
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    argument_list = "@(" + ",".join(quote(arg) for arg in args) + ")"
    script = (
        f"$p = Start-Process -FilePath {quote(sys.executable)} -ArgumentList {argument_list} "
        f"-WorkingDirectory {quote(BACKEND)} -WindowStyle Hidden -PassThru "
        f"-RedirectStandardOutput {quote(STATE / f'{name}.out.log')} "
        f"-RedirectStandardError {quote(STATE / f'{name}.err.log')}; "
        "@{pid=$p.Id; start_ticks=$p.StartTime.ToUniversalTime().Ticks} | ConvertTo-Json -Compress"
    )
    # Do not capture a pipe: Windows children may inherit its handle, keeping
    # communicate() waiting even after the launcher has exited.
    result_file = STATE / f"{name}.launch.json"
    with result_file.open("w", encoding="utf-8") as output:
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                       stdout=output, stderr=subprocess.DEVNULL, check=True)
    processes[name] = json.loads(result_file.read_text(encoding="utf-8-sig"))


def stop():
    process_file = STATE / "processes.json"
    if process_file.exists():
        for record in json.loads(process_file.read_text()).values():
            if process_alive(record):
                subprocess.run(["taskkill.exe", "/PID", str(record["pid"]), "/T", "/F"], check=True)
        process_file.unlink()
    if (STATE / "postgres" / "PG_VERSION").exists():
        run(PG / "pg_ctl.exe", "-D", STATE / "postgres", "-m", "fast", "-w", "stop")
    print("Local academy stopped; database and media preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "test"])
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if args.command == "start":
        start(args.demo)
    elif args.command == "stop":
        stop()
    else:
        configure()
        os.environ["TEST_DATABASE_URL"] = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/academy_test"
        run(sys.executable, "-m", "pytest", "-q")
