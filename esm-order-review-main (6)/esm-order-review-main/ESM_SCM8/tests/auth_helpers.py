from __future__ import annotations

import secrets

from backend.auth.models import UserAccount


TEST_PASSWORDS = {
    "adminmaster": "test-adminmaster-password",
    "eu_manager": "test-eu-manager-password",
    "bm1": "test-bm1-password",
    "bm2": "test-bm2-password",
    "bm3": "test-bm3-password",
    "hnb_team": "test-hnb-password",
    "ia": "test-ia-password",
    "my_team": "test-my-password",
    "sales_team": "test-sales-team-password",
    "vn_team": "test-vn-password",
}

TEST_ALLOWED_ENTITIES = {
    "adminmaster": ("HQ", "PL", "UK", "USA", "ME", "MX", "MY", "VN"),
    "eu_manager": ("HQ", "PL", "UK"),
    "bm1": ("HQ", "PL", "UK", "USA", "ME"),
    "bm2": ("HQ", "PL", "UK", "USA", "ME"),
    "bm3": ("HQ", "PL", "UK", "USA", "ME"),
    "hnb_team": ("HQ", "PL", "USA"),
    "ia": ("HQ", "PL", "UK", "USA", "ME", "MX", "MY", "VN"),
    "my_team": ("HQ", "MY"),
    "sales_team": ("HQ", "PL"),
    "vn_team": ("HQ", "VN"),
}


class TestUserStore:
    __test__ = False

    def __init__(self, *, inactive: set[str] | None = None) -> None:
        inactive = inactive or set()
        self._accounts = tuple(
            UserAccount(
                username=username,
                password_hash="test-only",
                role="MASTER" if username == "adminmaster" else "TEAM",
                allowed_entities=allowed,
                is_active=username not in inactive,
                display_name=username,
                account_type="TEST",
                is_admin=username in {"adminmaster", "ia"},
            )
            for username, allowed in TEST_ALLOWED_ENTITIES.items()
        )
        self._by_name = {account.username: account for account in self._accounts}

    def get(self, username: str) -> UserAccount | None:
        return self._by_name.get(username)

    def all(self) -> tuple[UserAccount, ...]:
        return self._accounts

    def authenticate(self, username: str, password: str) -> UserAccount | None:
        account = self.get(username)
        expected = TEST_PASSWORDS.get(username, "")
        valid = secrets.compare_digest(password.encode(), expected.encode())
        return account if account and account.is_active and valid else None
