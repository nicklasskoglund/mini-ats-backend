"""
Tests for JWT verification (app.auth.jwt), exercised via the protected
/me endpoint.

No real Supabase JWKS endpoint is ever contacted here: the `mock_jwks`
fixture (see conftest.py) swaps in a test key pair so signature
verification runs for real, against tokens we sign ourselves.
"""

import time

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import jwt as pyjwt

from app.main import app

client = TestClient(app)

VALID_USER_ID = "11111111-1111-1111-1111-111111111111"


def _valid_claims(**overrides) -> dict:
    now = int(time.time())
    claims = {
        "sub": VALID_USER_ID,
        "email": "person@example.com",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return claims


def test_me_returns_current_user_with_valid_token(make_token, mock_jwks):
    """A validly signed, unexpired token should authenticate successfully."""
    token = make_token(_valid_claims())

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"user_id": VALID_USER_ID, "email": "person@example.com"}


def test_me_requires_bearer_token():
    """No Authorization header at all must be rejected."""
    response = client.get("/me")

    assert response.status_code == 401


def test_me_rejects_expired_token(make_token, mock_jwks):
    """A token whose exp claim is in the past must be rejected."""
    now = int(time.time())
    token = make_token(_valid_claims(iat=now - 7200, exp=now - 3600))

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_rejects_wrong_audience(make_token, mock_jwks):
    """A token issued for a different audience must be rejected."""
    token = make_token(_valid_claims(aud="something-else"))

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_rejects_token_missing_sub(make_token, mock_jwks):
    """A validly signed token that lacks `sub` must be rejected with a
    controlled 401, not an unhandled KeyError -> 500."""
    claims = _valid_claims()
    del claims["sub"]
    token = make_token(claims)

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_rejects_wrong_signature(mock_jwks):
    """A token signed with a key other than the one the JWKS client trusts
    (e.g. forged, or signed for a different project) must be rejected."""
    forged_private_key = ec.generate_private_key(ec.SECP256R1())
    token = pyjwt.encode(_valid_claims(), forged_private_key, algorithm="ES256")

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
