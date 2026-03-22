from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from uuid import uuid4

ALLOWED_ROLES = frozenset({"user", "reviewer", "admin"})


@dataclass(frozen=True)
class AuthContext:
    actor_id: str
    tenant_id: str
    roles: frozenset[str]
    correlation_id: str


class AuthzError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, correlation_id: str | None = None):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.correlation_id = correlation_id or str(uuid4())
        super().__init__(message)


def authorize_request(
    claims: dict[str, Any],
    *,
    expected_issuer: str,
    expected_audience: str,
    now: int,
    requested_tenant: str | None = None,
    required_roles: set[str] | None = None,
    allowed_clock_skew_seconds: int = 60,
) -> AuthContext:
    correlation_id = str(uuid4())

    for claim in ("sub", "iss", "aud", "exp", "iat", "nbf", "roles"):
        if claim not in claims:
            raise AuthzError(401, "auth.invalid_token", f"Missing required claim: {claim}", correlation_id)

    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        raise AuthzError(403, "authz.deny", "Tenant context missing.", correlation_id)

    if claims["iss"] != expected_issuer:
        raise AuthzError(401, "auth.invalid_token", "Issuer mismatch.", correlation_id)

    if not _audience_matches(claims["aud"], expected_audience):
        raise AuthzError(401, "auth.invalid_token", "Audience mismatch.", correlation_id)

    exp = _coerce_int(claims["exp"], "exp", correlation_id)
    nbf = _coerce_int(claims["nbf"], "nbf", correlation_id)
    iat = _coerce_int(claims["iat"], "iat", correlation_id)

    if now > exp + allowed_clock_skew_seconds:
        raise AuthzError(401, "auth.expired", "Token expired.", correlation_id)

    if now < nbf - allowed_clock_skew_seconds:
        raise AuthzError(401, "auth.invalid_token", "Token not yet valid.", correlation_id)

    if now + allowed_clock_skew_seconds < iat:
        raise AuthzError(401, "auth.invalid_token", "Issued-at is in the future.", correlation_id)

    roles = _parse_roles(claims["roles"], correlation_id)
    if required_roles and roles.isdisjoint(required_roles):
        raise AuthzError(403, "authz.deny", "Role not permitted for operation.", correlation_id)

    if requested_tenant and requested_tenant != tenant_id:
        raise AuthzError(403, "authz.deny", "Tenant mismatch.", correlation_id)

    return AuthContext(
        actor_id=str(claims["sub"]),
        tenant_id=str(tenant_id),
        roles=roles,
        correlation_id=correlation_id,
    )


def _parse_roles(raw_roles: Any, correlation_id: str) -> frozenset[str]:
    if not isinstance(raw_roles, list):
        raise AuthzError(401, "auth.invalid_token", "Roles claim must be a list.", correlation_id)

    roles = frozenset(str(role) for role in raw_roles)
    if not roles:
        raise AuthzError(403, "authz.deny", "No roles provided.", correlation_id)

    if not roles.issubset(ALLOWED_ROLES):
        raise AuthzError(403, "authz.deny", "Role is not allowed.", correlation_id)

    return roles


def _audience_matches(raw_audience: Any, expected_audience: str) -> bool:
    if isinstance(raw_audience, str):
        return raw_audience == expected_audience

    if isinstance(raw_audience, Iterable):
        return expected_audience in {str(value) for value in raw_audience}

    return False


def _coerce_int(value: Any, claim_name: str, correlation_id: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise AuthzError(401, "auth.invalid_token", f"Claim {claim_name} is not numeric.", correlation_id)
