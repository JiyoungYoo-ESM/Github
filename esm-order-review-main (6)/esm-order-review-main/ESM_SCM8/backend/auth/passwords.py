"""Dependency-free PBKDF2 password hashing for deployment secrets.

The encoded value contains only algorithm parameters, salt and derived key;
the plaintext password is never persisted.  Keeping this behind two functions
makes a later Argon2/DB migration local to the user-store boundary.
"""

from __future__ import annotations

import base64
import hashlib
import secrets


ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    if not password:
        raise ValueError("비밀번호는 비어 있을 수 없습니다.")
    if iterations < 100_000:
        raise ValueError("PBKDF2 반복 횟수는 100000 이상이어야 합니다.")
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        (
            ALGORITHM,
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(derived).decode("ascii").rstrip("="),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, raw_salt, raw_expected = encoded.split("$", 3)
        if algorithm != ALGORITHM:
            return False
        iterations = int(raw_iterations)
        if iterations < 100_000:
            return False
        salt = base64.urlsafe_b64decode(raw_salt + "=" * (-len(raw_salt) % 4))
        expected = base64.urlsafe_b64decode(raw_expected + "=" * (-len(raw_expected) % 4))
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)
