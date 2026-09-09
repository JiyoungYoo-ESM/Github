"""Prompt for one password and print only its PBKDF2 hash."""

from __future__ import annotations

from getpass import getpass

from backend.auth.passwords import hash_password


def main() -> None:
    password = getpass("새 비밀번호: ")
    confirmation = getpass("새 비밀번호 확인: ")
    if password != confirmation:
        raise SystemExit("비밀번호가 일치하지 않습니다.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
