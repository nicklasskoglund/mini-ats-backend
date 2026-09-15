"""
Shared pytest fixtures.

Sets dummy environment variables for settings that are required in
production (e.g. Supabase URLs) but irrelevant to most unit tests, so the
test suite doesn't depend on a local .env file being present. Also provides
fixtures for signing fake Supabase-style JWTs and for making the auth
dependency trust our test key pair instead of calling Supabase's real JWKS
endpoint over the network, plus a fake in-memory Supabase client (see
FakeSupabase below) used by the jobs/candidates/admin CRUD tests instead of
a real database.
"""

import json
import os
import re
import uuid
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault(
    "SUPABASE_JWKS_URL",
    "https://test.supabase.co/auth/v1/.well-known/jwks.json",
)
os.environ.setdefault("SUPABASE_SECRET_KEY", "test-secret-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")


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


# --- jobs/candidates/admin test support ------------------------------------
#
# These tests never touch a real database. FakeSupabase implements just the
# slice of the postgrest query-builder chain (select/insert/update, eq/in_/
# ilike/maybe_single/execute) and the three supabase.auth.admin methods
# (create_user/invite_user_by_email/list_users) that app/routers/*.py
# actually call, against plain in-memory lists. It's swapped in via
# app.dependency_overrides on get_supabase, the same mechanism FastAPI's
# own docs recommend for
# replacing a dependency in tests.

CUSTOMER_ID = "00000000-0000-0000-0000-0000000000c1"
OTHER_CUSTOMER_ID = "00000000-0000-0000-0000-0000000000c2"
ADMIN_ID = "00000000-0000-0000-0000-00000000ad01"


def _ilike_pattern_to_regex(pattern: str) -> re.Pattern:
    """Translate a Postgres ILIKE pattern (%/_ wildcards) into a compiled,
    case-insensitive regex - just enough to mimic .ilike("name", "%x%") for
    the tests, not a general SQL LIKE implementation.

    Built character by character (% -> ".*", _ -> ".", anything else
    escaped literally) rather than escaping the whole pattern up front and
    substituting wildcards afterwards - re.escape leaves plain % and _
    untouched (neither is a special regex character), so a substitute-after
    approach would never find them.
    """
    regex_parts = [
        ".*" if char == "%" else "." if char == "_" else re.escape(char)
        for char in pattern
    ]
    return re.compile("^" + "".join(regex_parts) + "$", re.IGNORECASE)


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

    def ilike(self, field, pattern):
        self._filters.append(("ilike", field, _ilike_pattern_to_regex(pattern)))
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
            if kind == "ilike" and not value.match(str(row.get(field, ""))):
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
            if self.table_name == "jobs":
                profile_ids = {p["id"] for p in self.db.tables["profiles"]}
                if row["customer_id"] not in profile_ids:
                    # Mirrors the real jobs_customer_id_fkey violation - same
                    # SQLSTATE postgrest surfaces, verified against the real
                    # local database while building app/db/errors.py. Not
                    # reachable via the API anymore since get_effective_customer_id
                    # already validates the customer exists, but kept as
                    # defense-in-depth parity with the real schema.
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
                for optional_field in (
                    "email",
                    "phone",
                    "linkedin_url",
                    "cv_text",
                    "notes",
                    "ai_score",
                    "ai_summary",
                    "ai_strengths",
                    "ai_gaps",
                ):
                    row.setdefault(optional_field, None)
            self.rows.append(row)
            return _FakeResponse([dict(row)])

        if kind == "update":
            matched = [r for r in self.rows if self._matches(r)]
            for row in matched:
                row.update(payload)
            return _FakeResponse([dict(r) for r in matched])

        raise AssertionError(f"FakeSupabase: unsupported operation {kind!r}")


_PROFILE_OPTIONAL_FIELDS = (
    "full_name",
    "company_name",
    "website_url",
    "linkedin_url",
    "phone",
    "contact_email",
    "address",
    "description",
)


def _new_profile_row(user_id: str, role: str, metadata: dict | None = None) -> dict:
    """Build a full profiles row (every column ProfileRead/CustomerSummary
    expect present, even if None) - mirrors what handle_new_user actually
    populates: role/full_name/company_name from metadata, everything else
    left null until a later PATCH /profile."""
    metadata = metadata or {}
    row = {field: None for field in _PROFILE_OPTIONAL_FIELDS}
    row["id"] = user_id
    row["role"] = role
    row["full_name"] = metadata.get("full_name")
    row["company_name"] = metadata.get("company_name")
    row["created_at"] = "2026-01-01T00:00:00+00:00"
    return row


class _FakeAuthAdmin:
    """Stand-in for supabase.auth.admin - the three methods
    app/routers/admin.py calls: create_user, invite_user_by_email, and
    list_users."""

    def __init__(self, db: "FakeSupabase"):
        self.db = db
        self.users: dict[str, str] = {}  # id -> email

    def _register(self, email: str, metadata: dict):
        if email in self.users.values():
            raise AuthApiError(
                "A user with this email address has already been registered",
                422,
                "email_exists",
            )
        user_id = str(uuid.uuid4())
        self.users[user_id] = email
        # Mirrors the real handle_new_user trigger: the profiles row is a
        # side effect of the user being created or invited, not a separate
        # step - and not gated on email confirmation either (verified
        # locally: "act as a customer" works right after an invite, before
        # the customer ever confirms it).
        self.db.tables["profiles"].append(
            _new_profile_row(user_id, metadata.get("role", "customer"), metadata)
        )
        return SimpleNamespace(user=SimpleNamespace(id=user_id, email=email))

    def create_user(self, attributes: dict):
        return self._register(attributes["email"], attributes.get("user_metadata", {}))

    def invite_user_by_email(self, email: str, options: dict | None = None):
        return self._register(email, (options or {}).get("data", {}))

    def list_users(self):
        return [
            SimpleNamespace(id=user_id, email=email)
            for user_id, email in self.users.items()
        ]


class FakeSupabase:
    """In-memory stand-in for the Supabase client, scoped to jobs/candidates
    (via .table()) and admin account management (via .auth.admin)."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "jobs": [],
            "candidates": [],
            "profiles": [],
        }
        self.auth = SimpleNamespace(admin=_FakeAuthAdmin(self))

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, name)


@pytest.fixture
def fake_db():
    """A fresh FakeSupabase per test."""
    return FakeSupabase()


def _upsert_profile(fake_db: FakeSupabase, *, id: str, role: str) -> None:
    """Ensure a profiles row (and a matching auth.admin email) exists for
    `id` - every acted-as identity needs both, mirroring how a real JWT
    always corresponds to a real auth.users + profiles row."""
    for profile in fake_db.tables["profiles"]:
        if profile["id"] == id:
            profile["role"] = role
            return
    fake_db.tables["profiles"].append(
        _new_profile_row(id, role, {"full_name": "Test"})
    )
    fake_db.auth.admin.users.setdefault(id, f"{id}@example.com")


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
        _upsert_profile(fake_db, id=id, role=role)

    yield _act_as

    app.dependency_overrides.clear()


# --- AI assessment test support ---------------------------------------------
#
# POST /candidates/{id}/assess never calls the real Anthropic API. FakeAI
# stands in for the one method app/services/ai_assessment.py calls
# (messages.create), returning a canned response or raising a canned error -
# swapped in via app.dependency_overrides on get_anthropic_client.


class _FakeAIResponse:
    """Mimics an Anthropic Message enough for assess_candidate: a list of
    text content blocks, same shape app/services/ai_assessment.py reads
    (block.type == "text", block.text)."""

    def __init__(self, text: str):
        self.content = [SimpleNamespace(type="text", text=text)]


class FakeAI:
    """Stand-in for anthropic.Anthropic - just messages.create."""

    def __init__(
        self,
        *,
        payload: dict | None = None,
        text: str | None = None,
        error: Exception | None = None,
    ):
        self._payload = payload
        self._text = text
        self._error = error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **_kwargs):
        if self._error is not None:
            raise self._error
        # `text` wins when given (e.g. a payload wrapped in a markdown
        # code fence, to test that assess_candidate strips it) - it's the
        # raw response body, whereas `payload` is the convenience path
        # that's always clean JSON.
        return _FakeAIResponse(self._text if self._text is not None else json.dumps(self._payload))


@pytest.fixture
def mock_ai_assessment():
    """Returns a function to configure the AI client behind
    POST /candidates/{id}/assess: pass `payload` for a canned successful
    JSON response, `text` for a raw response body (e.g. wrapped in a
    markdown code fence), or `error` to simulate an Anthropic failure.
    Override is cleared after the test regardless of outcome."""
    from app.main import app
    from app.services.ai_assessment import get_anthropic_client

    def _mock(
        *,
        payload: dict | None = None,
        text: str | None = None,
        error: Exception | None = None,
    ):
        app.dependency_overrides[get_anthropic_client] = lambda: FakeAI(
            payload=payload, text=text, error=error
        )

    yield _mock

    app.dependency_overrides.pop(get_anthropic_client, None)
