"""
Resolves the "effective customer" a request should be scoped to - the one
place authorization in the jobs/candidates endpoints delegates to. If a
future need for token-based impersonation ever arises, it's an isolated
change to this file; nothing else in the codebase has to know how the
effective customer was determined.

Rules:
- role=customer: always their own id - the X-Acting-As-Customer header is
  ignored entirely, regardless of its content.
- role=admin, no header: None, meaning "no restriction" (today's
  see-everything behavior for admins is unchanged).
- role=admin, with header: the header value is looked up as a profiles.id;
  if it doesn't resolve to an existing customer profile, 404 (never a
  silent bypass or an empty result).

Every time the header actually resolves to a customer id, a structured
audit log line is written to stdout (Railway captures it) - most of the
traceability a token-based impersonation scheme would give, without its
code overhead, and no new database table for v1.
"""

import json
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from postgrest.exceptions import APIError

from app.auth.profile import CurrentProfile, get_current_profile
from app.db.client import get_supabase
from supabase import Client


def log_acting_as(admin_id: str, acting_as_customer_id: str, endpoint: str) -> None:
    """Write one structured audit log line for an admin acting as a
    customer. Kept as a standalone function (not inlined) so tests can
    monkeypatch/assert on it directly, instead of parsing captured stdout.
    """
    print(
        json.dumps(
            {
                "event": "admin_acting_as_customer",
                "admin_id": admin_id,
                "acting_as_customer_id": acting_as_customer_id,
                "endpoint": endpoint,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ),
        flush=True,
    )


def get_effective_customer_id(
    request: Request,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
    x_acting_as_customer: str | None = Header(default=None),
) -> str | None:
    """FastAPI dependency: the customer id jobs/candidates endpoints should
    scope their queries to, or None for "no restriction" (admin, no
    header)."""
    if not profile.is_admin:
        return profile.id

    if x_acting_as_customer is None:
        return None

    try:
        response = (
            supabase.table("profiles")
            .select("id, role")
            .eq("id", x_acting_as_customer)
            .maybe_single()
            .execute()
        )
    except APIError:
        # A malformed (non-UUID) header value fails the query outright
        # (verified locally: postgrest raises 22P02 invalid_text_representation
        # rather than just returning no rows) - treated the same as "no such
        # customer" rather than leaking as a 500.
        response = None

    if response is None or response.data["role"] != "customer":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No customer found for X-Acting-As-Customer",
        )

    log_acting_as(
        admin_id=profile.id,
        acting_as_customer_id=x_acting_as_customer,
        endpoint=request.url.path,
    )
    return x_acting_as_customer
