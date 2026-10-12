"""Fail-closed operator authorization for shared ATS mutation HTTP endpoints.

Operator access is explicitly granted to a *server-resolved user ID*. Matching
email, a frontend role field, an HTTP header, and OIDC/Cloudflare claims alone
never grant permission to change shared source policies or job inventory.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re

from .identity import UserProfileBinding


_OPERATOR_ID_PATTERN = re.compile(r"usr-[0-9a-f]{32}\Z")
_MAX_OPERATORS = 16


class OperatorConfigurationError(ValueError):
    """Operator access environment configuration is not safe to use."""


@dataclass(frozen=True)
class OperatorAccessPolicy:
    user_ids: frozenset[str]

    @classmethod
    def from_env(cls) -> "OperatorAccessPolicy":
        raw = os.getenv("SMARTPLOY_OPERATOR_USER_IDS", "")
        if not raw.strip():
            return cls(user_ids=frozenset())
        if len(raw) > 1024:
            raise OperatorConfigurationError(
                "SMARTPLOY_OPERATOR_USER_IDS is too long"
            )
        parts = [value.strip() for value in raw.split(",")]
        if (
            len(parts) > _MAX_OPERATORS
            or not all(_OPERATOR_ID_PATTERN.fullmatch(value) for value in parts)
            or len(set(parts)) != len(parts)
        ):
            raise OperatorConfigurationError(
                "SMARTPLOY_OPERATOR_USER_IDS must contain distinct server-issued "
                "usr- IDs separated by commas, with no email or wildcard entries"
            )
        return cls(user_ids=frozenset(parts))

    def allows(self, binding: UserProfileBinding | None) -> bool:
        return bool(
            binding is not None
            and binding.status == "active"
            and binding.user_id in self.user_ids
        )
