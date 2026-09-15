"""
Supabase client used for all database reads/writes.

Initialized with the secret (service-role) key, which bypasses Row Level
Security - see CLAUDE.md's Security section for why: FastAPI, not Postgres,
enforces who may see/edit what, so every request that reaches this client
has already passed JWT verification and, where relevant, an ownership/role
check in the router itself. RLS stays enabled on every table as a defense
-in-depth layer in case the PostgREST API is ever reached directly with an
anon/authenticated key instead of through this backend.

get_supabase is a plain FastAPI dependency (not a bare module-level client)
so tests can swap it out via app.dependency_overrides instead of hitting a
real database.
"""

from functools import lru_cache

from app.core.config import settings
from supabase import Client, create_client


@lru_cache
def get_supabase() -> Client:
    """Return a process-wide cached Supabase client using the secret key."""
    return create_client(settings.supabase_url, settings.supabase_secret_key)
