"""Small immutable authentication domain models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserAccount:
    username: str
    password_hash: str
    role: str
    allowed_entities: tuple[str, ...]
    is_active: bool
    display_name: str
    account_type: str
    is_admin: bool = False

    def public_dict(self) -> dict[str, object]:
        return {
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "account_type": self.account_type,
            "allowed_entities": list(self.allowed_entities),
            "is_admin": self.is_admin,
        }
