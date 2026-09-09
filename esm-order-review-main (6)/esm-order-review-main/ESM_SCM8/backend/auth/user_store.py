"""Environment-backed account repository for the first deployment phase."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from backend.auth.models import UserAccount
from backend.auth.passwords import verify_password
from backend.entities import ENTITY_CODES


class UserStore(Protocol):
    def get(self, username: str) -> UserAccount | None: ...

    def all(self) -> tuple[UserAccount, ...]: ...

    def authenticate(self, username: str, password: str) -> UserAccount | None: ...


@dataclass(frozen=True, slots=True)
class AccountSpec:
    username: str
    password_hash_env: str
    role: str
    allowed_entities: tuple[str, ...]
    display_name: str
    account_type: str
    is_admin: bool = False


ACCOUNT_SPECS: tuple[AccountSpec, ...] = (
    AccountSpec("adminmaster", "AUTH_ADMINMASTER_PASSWORD_HASH", "MASTER", ENTITY_CODES, "마스터", "MASTER", True),
    AccountSpec("eu_manager", "AUTH_EU_MANAGER_PASSWORD_HASH", "EU_KEYMAN", ("HQ", "PL", "UK"), "유럽 법인 매니저", "TEAM"),
    AccountSpec("bm1", "AUTH_BM1_PASSWORD_HASH", "BM_TEAM", ("HQ", "PL", "UK", "USA", "ME"), "BM 1팀", "TEAM"),
    AccountSpec("bm2", "AUTH_BM2_PASSWORD_HASH", "BM_TEAM", ("HQ", "PL", "UK", "USA", "ME"), "BM 2팀", "TEAM"),
    AccountSpec("bm3", "AUTH_BM3_PASSWORD_HASH", "BM_TEAM", ("HQ", "PL", "UK", "USA", "ME"), "BM 3팀", "TEAM"),
    AccountSpec("hnb_team", "AUTH_HNB_TEAM_PASSWORD_HASH", "HNB_TEAM", ("HQ", "PL", "USA"), "H&B 담당팀", "TEAM"),
    AccountSpec("ia", "AUTH_IA_PASSWORD_HASH", "INTERNAL_AUDIT", ENTITY_CODES, "내부감사", "TEAM", True),
    AccountSpec("my_team", "AUTH_MY_TEAM_PASSWORD_HASH", "MY_TEAM", ("HQ", "MY"), "말레이시아 담당팀", "TEAM"),
    AccountSpec("sales_team", "AUTH_SALES_TEAM_PASSWORD_HASH", "SALES_TEAM", ("HQ", "PL"), "영업팀", "TEAM"),
    AccountSpec("vn_team", "AUTH_VN_TEAM_PASSWORD_HASH", "VN_TEAM", ("HQ", "VN"), "베트남 담당팀", "TEAM"),
)


def _env_flag(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class EnvironmentUserStore:
    """Loads public account metadata from code and secret hashes from env."""

    def __init__(self) -> None:
        accounts = tuple(
            UserAccount(
                username=spec.username,
                password_hash=os.environ.get(spec.password_hash_env, "").strip(),
                role=spec.role,
                allowed_entities=spec.allowed_entities,
                is_active=_env_flag(f"AUTH_{spec.username.upper()}_ACTIVE", True),
                display_name=spec.display_name,
                account_type=spec.account_type,
                is_admin=spec.is_admin,
            )
            for spec in ACCOUNT_SPECS
        )
        self._accounts = accounts
        self._by_username = {account.username: account for account in accounts}

    def get(self, username: str) -> UserAccount | None:
        return self._by_username.get(username)

    def all(self) -> tuple[UserAccount, ...]:
        return self._accounts

    def authenticate(self, username: str, password: str) -> UserAccount | None:
        account = self.get(username)
        if account is None or not account.is_active or not account.password_hash:
            return None
        return account if verify_password(password, account.password_hash) else None


def validate_user_store(store: UserStore, *, require_all_hashes: bool) -> None:
    problems: list[str] = []
    accounts = store.all()
    usernames = [account.username for account in accounts]
    if len(usernames) != len(set(usernames)):
        problems.append("동일한 사용자 아이디가 중복되어 있습니다.")
    valid_entities = set(ENTITY_CODES)
    for account in accounts:
        invalid = sorted(set(account.allowed_entities) - valid_entities)
        if invalid:
            problems.append(f"{account.username}: 존재하지 않는 법인 코드 {', '.join(invalid)}")
        if not account.allowed_entities:
            problems.append(f"{account.username}: 허용 법인 목록이 비어 있습니다.")
        if require_all_hashes and not account.password_hash:
            problems.append(f"{account.username}: 비밀번호 해시 환경변수가 없습니다.")
    master = next((account for account in accounts if account.username == "adminmaster"), None)
    if master is None or set(master.allowed_entities) != valid_entities:
        problems.append("adminmaster 계정에는 8개 법인이 모두 허용되어야 합니다.")
    if not any(account.is_active for account in accounts):
        problems.append("활성화된 계정이 하나도 없습니다.")
    if problems:
        raise RuntimeError("계정 설정 오류:\n  - " + "\n  - ".join(problems))


_user_store: UserStore = EnvironmentUserStore()


def get_user_store() -> UserStore:
    return _user_store


def replace_user_store(store: UserStore) -> None:
    """Test/DB migration seam; production callers should not replace it."""

    global _user_store
    _user_store = store
