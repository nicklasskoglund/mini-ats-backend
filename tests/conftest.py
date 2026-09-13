"""
Shared pytest fixtures.

Sets dummy environment variables for settings that are required in
production (e.g. Supabase URLs) but irrelevant to most unit tests, so the
test suite doesn't depend on a local .env file being present. Also provides
fixtures for signing fake Supabase-style JWTs and for making the auth
dependency trust our test key pair instead of calling Supabase's real JWKS
endpoint over the network.
"""

import os
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault(
    "SUPABASE_JWKS_URL",
    "https://test.supabase.co/auth/v1/.well-known/jwks.json",
)
os.environ.setdefault("SUPABASE_SECRET_KEY", "test-secret-key")


@pytest.fixture
def ec_keypair():
    """A fresh EC key pair, playing the role of Supabase's project signing key."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


@pytest.fixture
def make_token(ec_keypair):
    """Factory for signing a fake Supabase-style JWT with the test key pair."""
    private_key, _ = ec_keypair

    def _make_token(claims: dict, algorithm: str = "ES256") -> str:
        return jwt.encode(claims, private_key, algorithm=algorithm)

    return _make_token


@pytest.fixture
def mock_jwks(monkeypatch, ec_keypair):
    """Make the auth dependency resolve signing keys to our test public key,
    instead of fetching Supabase's real JWKS endpoint over the network."""
    import app.auth.jwt as auth_jwt

    _, public_key = ec_keypair

    def _fake_get_jwks_client():
        return SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
        )

    monkeypatch.setattr(auth_jwt, "get_jwks_client", _fake_get_jwks_client)
