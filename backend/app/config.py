"""Runtime settings, read once from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass
class Settings:
    app_env: str
    database_url: str
    media_root: str
    public_base_url: str
    timezone: str
    cookie_secure: bool
    session_idle_minutes: int
    session_absolute_hours: int
    login_max_failures: int
    login_lock_minutes: int
    # argon2id cost for user-chosen passwords (OWASP minimum: m=19 MiB, t=2, p=1).
    argon2_time_cost: int
    argon2_memory_kib: int
    argon2_parallelism: int
    cert_status_api_keys: tuple[str, ...] = field(repr=False)  # secrets stay out of logs
    # Printed above "Kompetensiyalar markazi rahbari" on certificates (kept in each snapshot).
    cert_signatory_name: str
    # AI question drafting (authoring only). Empty key: the feature is hidden.
    anthropic_api_key: str = field(repr=False)
    anthropic_model: str

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"


def load_settings() -> Settings:
    return Settings(
        app_env=_str("APP_ENV", "production"),
        database_url=_str("DATABASE_URL", ""),
        media_root=_str("MEDIA_ROOT", "/data/media"),
        public_base_url=_str("PUBLIC_BASE_URL", "http://localhost").rstrip("/"),
        timezone=_str("APP_TIMEZONE", "Asia/Tashkent"),
        cookie_secure=_bool("COOKIE_SECURE", False),
        session_idle_minutes=_int("SESSION_IDLE_MINUTES", 60),
        session_absolute_hours=_int("SESSION_ABSOLUTE_HOURS", 12),
        login_max_failures=_int("LOGIN_MAX_FAILURES", 5),
        login_lock_minutes=_int("LOGIN_LOCK_MINUTES", 15),
        argon2_time_cost=_int("ARGON2_TIME_COST", 2),
        argon2_memory_kib=_int("ARGON2_MEMORY_KIB", 19456),
        argon2_parallelism=_int("ARGON2_PARALLELISM", 1),
        cert_status_api_keys=_list("CERT_STATUS_API_KEYS"),
        cert_signatory_name=_str("CERT_SIGNATORY_NAME", "").strip(),
        anthropic_api_key=_str("ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=_str("ANTHROPIC_MODEL", "claude-opus-5-5").strip() or "claude-opus-5-5",
    )


settings = load_settings()
