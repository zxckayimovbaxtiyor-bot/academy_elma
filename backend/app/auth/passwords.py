"""argon2id hashing.

User-chosen passwords use the full cost from settings. One-time temporary
passwords (CSV import, admin reset) are random 10-character secrets that must be
changed at first login, so they are hashed with a cheaper profile: a bulk import
of several thousand users would otherwise take minutes.
"""

from __future__ import annotations

import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import settings

# No 0/O, 1/l/I: temporary passwords are read off paper.
_TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
TEMP_PASSWORD_LENGTH = 10
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_kib,
        parallelism=settings.argon2_parallelism,
    )


@lru_cache(maxsize=1)
def _temp_hasher() -> PasswordHasher:
    return PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)


@lru_cache(maxsize=1)
def dummy_hash() -> str:
    """Verified against when the user does not exist, so timing doesn't reveal valid logins."""
    return _hasher().hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def hash_temp_password(password: str) -> str:
    return _temp_hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher().check_needs_rehash(password_hash)


def generate_temp_password() -> str:
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(TEMP_PASSWORD_LENGTH))


def new_password_problem(password: str, employee_id: str) -> str | None:
    """Error code for an unacceptable new password, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return "password.too_short"
    if len(password) > MAX_PASSWORD_LENGTH:
        return "password.too_long"
    if password.strip().upper() == employee_id.upper():
        return "password.equals_employee_id"
    return None
