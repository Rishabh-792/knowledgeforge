"""JWT auth and the role model.

Roles form a strict hierarchy: reader < curator < admin.
  * reader  — search + chat over documents their groups can see
  * curator — everything a reader can, plus ingesting documents
  * admin   — everything, plus index management; bypasses ACL filtering

Anonymous requests are rejected unless ALLOW_ANONYMOUS_DEV_ADMIN=true is
set explicitly (local mode only; refused at startup in azure mode), which
grants a dev admin principal so the quickstart works with plain curl. Any
presented token is always verified, in every mode.
"""

import datetime as dt
import logging

import jwt
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

ROLE_RANK = {"reader": 0, "curator": 1, "admin": 2}


class Principal(BaseModel):
    sub: str
    role: str = "reader"
    groups: list[str] = []

    @property
    def acl_groups(self) -> list[str] | None:
        """Groups used to filter search results; None means unrestricted."""
        return None if self.role == "admin" else self.groups


def create_access_token(
    sub: str, role: str, groups: list[str], settings: Settings
) -> str:
    if role not in ROLE_RANK:
        raise ValueError(f"unknown role: {role}")
    now = dt.datetime.now(dt.timezone.utc)
    claims = {
        "sub": sub,
        "role": role,
        "groups": groups,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings) -> Principal:
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
    return Principal(
        sub=claims.get("sub", "unknown"),
        role=claims.get("role", "reader"),
        groups=claims.get("groups", []),
    )


async def get_current_principal(
    request: Request, settings: Settings = Depends(get_settings)
) -> Principal:
    auth = request.headers.get("Authorization", "")
    if not auth:
        if settings.mode == "local" and settings.allow_anonymous_dev_admin:
            # Frictionless quickstart — but only when explicitly opted in;
            # config refuses to start with this flag set in azure mode.
            return Principal(sub="dev-user", role="admin", groups=["everyone"])
        raise HTTPException(status_code=401, detail="missing bearer token")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="expected 'Bearer <token>'")
    return decode_token(token, settings)


def require_role(minimum: str):
    """Dependency factory enforcing the role hierarchy."""

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if ROLE_RANK[principal.role] < ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=403,
                detail=f"role '{principal.role}' lacks '{minimum}' privileges",
            )
        return principal

    return dependency
