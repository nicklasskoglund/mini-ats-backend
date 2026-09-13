"""
Shared pytest fixtures.

Sets dummy environment variables for settings that are required in
production (e.g. Supabase URLs) but irrelevant to most unit tests, so the
test suite doesn't depend on a local .env file being present. Also provides
fixtures for signing fake Supabase-style JWTs and for making the auth
dependency trust our test key pair instead of calling Supabase's real JWKS
endpoint over the network, plus a fake in-memory Supabase client (see
FakeSupabase below) used by the jobs/candidates CRUD tests instead of a
real database.
"""

import os
import uuid
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from postgrest.exceptions import APIError

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


# --- jobs/candidates CRUD test support -------------------------------------
#
# These tests never touch a real database. FakeSupabase implements just the
# slice of the postgrest query-builder chain app/routers/jobs.py and
# app/routers/candidates.py actually call (select/insert/update, eq/in_/
# maybe_single/execute) against plain in-memory lists. It's swapped in via
# app.dependency_overrides on get_supabase, the same mechanism FastAPI's own
# docs recommend for replacing a dependency in tests.

CUSTOMER_ID = "00000000-0000-0000-0000-0000000000c1"
OTHER_CUSTOMER_ID = "00000000-0000-0000-0000-0000000000c2"
ADMIN_ID = "00000000-0000-0000-0000-00000000ad01"


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, db, table_name):
        self.db = db
        self.table_name = table_name
        self.rows = db.tables[table_name]
        self._filters: list[tuple[str, str, object]] = []
        self._single = False
        self._op = ("select", None)

    def select(self, *_args, **_kwargs):
        self._op = ("select", None)
        return self

    def insert(self, payload):
        self._op = ("insert", payload)
        return self

    def update(self, payload):
        self._op = ("update", payload)
        return self

    def eq(self, field, value):
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self._filters.append(("in", field, list(values)))
        return self

    def maybe_single(self):
        self._single = True
        return self

    def _matches(self, row) -> bool:
        for kind, field, value in self._filters:
            if kind == "eq" and row.get(field) != value:
                return False
            if kind == "in" and row.get(field) not in value:
                return False
        return True

    def execute(self):
        kind, payload = self._op

        if kind == "select":
            matched = [dict(r) for r in self.rows if self._matches(r)]
            if self._single:
                return _FakeResponse(matched[0]) if matched else None
            return _FakeResponse(matched)

        if kind == "insert":
            row = dict(payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", "2026-01-01T00:00:00+00:00")
            if self.table_name == "jobs" and row["customer_id"] not in self.db.valid_customer_ids:
                # Mirrors the real jobs_customer_id_fkey violation - same
                # SQLSTATE postgrest surfaces, verified against the real
                # local database while building app/db/errors.py.
                raise APIError(
                    {
                        "code": "23503",
                        "message": (
                            'insert or update on table "jobs" violates '
                            'foreign key constraint "jobs_customer_id_fkey"'
                        ),
                        "details": None,
                        "hint": None,
                    }
                )
            if self.table_name == "candidates":
                row.setdefault("stage", "new")
                for optional_field in ("email", "linkedin_url", "cv_text", "ai_score", "ai_summary"):
                    row.setdefault(optional_field, None)
            self.rows.append(row)
            return _FakeResponse([dict(row)])

        if kind == "update":
            matched = [r for r in self.rows if self._matches(r)]
            for row in matched:
                row.update(payload)
            return _FakeResponse([dict(r) for r in matched])

        raise AssertionError(f"FakeSupabase: unsupported operation {kind!r}")


class FakeSupabase:
    """In-memory stand-in for the Supabase client, scoped to jobs/candidates."""

    def __init__(self, valid_customer_ids: set[str] = frozenset()):
        self.tables: dict[str, list[dict]] = {"jobs": [], "candidates": []}
        self.valid_customer_ids = set(valid_customer_ids)

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, name)


@pytest.fixture
def fake_db():
    """A fresh FakeSupabase per test, seeded with the two standard test
    customer ids as valid job owners (so normal job creation succeeds;
    an id outside this set simulates an admin passing an unknown
    customer_id)."""
    return FakeSupabase(valid_customer_ids={CUSTOMER_ID, OTHER_CUSTOMER_ID})


@pytest.fixture
def act_as(fake_db):
    """Configure the app to treat the request as coming from a given
    profile, backed by fake_db instead of a real Supabase project.
    Overrides are cleared after the test regardless of outcome."""
    from app.auth.profile import CurrentProfile, get_current_profile
    from app.db.client import get_supabase
    from app.main import app

    app.dependency_overrides[get_supabase] = lambda: fake_db

    def _act_as(*, id: str, role: str) -> None:
        app.dependency_overrides[get_current_profile] = lambda: CurrentProfile(
            id=id, role=role, full_name="Test", company_name=None
        )

    yield _act_as

    app.dependency_overrides.clear()
