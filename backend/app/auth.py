"""Login: the website signs users in with Supabase Auth and sends the session's
access token as `Authorization: Bearer <token>`. We verify it here and use the
token's `sub` (the Supabase user id) as the owner of every meeting.

Supabase projects sign tokens either with asymmetric keys (current default,
published at /auth/v1/.well-known/jwks.json) or with a legacy shared secret
(HS256). Both are supported. AUTH_DISABLED=1 skips login for local development.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import jwt
from fastapi import Header, HTTPException

from app import config

AUDIENCE = "authenticated"


@dataclass
class User:
    id: str
    email: Optional[str] = None


LOCAL_USER = User(id="local", email=None)


@lru_cache(maxsize=1)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_keys=True)


def verify_token(token: str) -> User:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not config.SUPABASE_JWT_SECRET:
                raise HTTPException(401, "Server is not configured for HS256 tokens")
            claims = jwt.decode(token, config.SUPABASE_JWT_SECRET, algorithms=["HS256"], audience=AUDIENCE)
        else:
            if not config.SUPABASE_URL:
                raise HTTPException(401, "Server is not configured with SUPABASE_URL")
            key = _jwks_client(config.SUPABASE_URL).get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=AUDIENCE)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired. Sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid session token")
    if not claims.get("sub"):
        raise HTTPException(401, "Token has no user id")
    return User(id=claims["sub"], email=claims.get("email"))


def current_user(authorization: Optional[str] = Header(default=None)) -> User:
    """FastAPI dependency: every protected route gets the signed-in user."""
    if config.AUTH_DISABLED:
        return LOCAL_USER
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return verify_token(authorization.split(" ", 1)[1].strip())
