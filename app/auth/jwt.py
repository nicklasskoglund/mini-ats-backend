"""
JWT verification against Supabase's JWKS endpoint.

Supabase signs tokens with a per-project asymmetric key pair; the public
keys are published at SUPABASE_JWKS_URL. Verifying the signature against
this published JWKS means the backend never has to hold Supabase's private
signing key, and never trusts a role or user id merely because the client
claims it - the identity below is only trusted once the signature, expiry,
audience, and required-claim checks below have all passed.

Role-based authorization (admin vs customer) is layered on top of this once
the `profiles` table exists (step 3+); this module only establishes *who*
is making the request, not what they're allowed to do. Every invalid state
here is raised as a controlled 401, never left to bubble up as a 500.
"""

from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

_INVALID_TOKEN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
)


@lru_cache
def get_jwks_client() -> PyJWKClient:
    """Return a process-wide cached PyJWKClient.

    PyJWKClient caches individual signing keys internally (keyed by `kid`)
    and only re-fetches the JWKS when it sees an unknown `kid`, so reusing
    one client across requests avoids hitting Supabase's JWKS endpoint on
    every single request while still picking up rotated keys automatically.
    """
    return PyJWKClient(settings.supabase_jwks_url)


class CurrentUser:
    """Authenticated user identity extracted from a verified JWT."""

    def __init__(self, user_id: str, email: str | None, claims: dict):
        self.user_id = user_id
        self.email = email
        self.claims = claims


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """FastAPI dependency: verify the Supabase-issued JWT on the request.

    Raises 401 if the token is missing, malformed, expired, fails
    signature/audience verification, or is otherwise well-formed but
    missing the `sub` claim we rely on for identity. Reusable on every
    protected endpoint.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=settings.supabase_jwt_algorithms,
            audience=settings.supabase_jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise _INVALID_TOKEN_ERROR from exc

    user_id = claims.get("sub")
    if not user_id:
        # A token can be validly signed and unexpired yet still lack `sub`
        # (e.g. a service token, or a malformed one) - without this check
        # that would surface as an unhandled KeyError -> 500 below instead
        # of the controlled 401 every invalid-token path here returns.
        raise _INVALID_TOKEN_ERROR

    return CurrentUser(user_id=user_id, email=claims.get("email"), claims=claims)
