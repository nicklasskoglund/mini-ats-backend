"""
Looks up the caller's role and profile data in the `profiles` table.

get_current_user (app/auth/jwt.py) only proves *who* is making the request
- a verified JWT subject. It has no idea about roles, because Supabase's
own JWT claims don't carry our app-specific role; that lives in
`profiles`, populated by the handle_new_user trigger (see
supabase/schemas/profiles.sql). Every endpoint that branches on
admin-vs-customer depends on get_current_profile below, not on anything
claimed by the client.
"""

from fastapi import Depends, HTTPException, status
from supabase import Client

from app.auth.jwt import CurrentUser, get_current_user
from app.db.client import get_supabase


class CurrentProfile:
    """The authenticated caller's row from `profiles`."""

    def __init__(
        self,
        id: str,
        role: str,
        full_name: str | None,
        company_name: str | None,
    ):
        self.id = id
        self.role = role
        self.full_name = full_name
        self.company_name = company_name

    @property
    def is_admin(self) -> bool:
        """Whether this caller may bypass ownership checks entirely."""
        return self.role == "admin"


def get_current_profile(
    current_user: CurrentUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> CurrentProfile:
    """FastAPI dependency: fetch the caller's profile row.

    Raises 403 if the JWT is valid but no matching profile row exists. This
    should never happen in practice (the handle_new_user trigger guarantees
    one for every auth.users row), but a client without a profile is not
    verifiably admin or customer, so treating it as "forbidden" is the safe
    default - not a 500 from an unhandled missing-row case.

    Note: postgrest-py's `.maybe_single().execute()` returns `None` itself
    (not a response object with `.data = None`) when no row matches -
    verified locally, since it's an easy thing to get wrong and would
    otherwise surface as an unhandled AttributeError.
    """
    response = (
        supabase.table("profiles")
        .select("id, role, full_name, company_name")
        .eq("id", current_user.user_id)
        .maybe_single()
        .execute()
    )

    if response is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No profile found for this account",
        )

    row = response.data
    return CurrentProfile(
        id=row["id"],
        role=row["role"],
        full_name=row.get("full_name"),
        company_name=row.get("company_name"),
    )


def require_admin(
    profile: CurrentProfile = Depends(get_current_profile),
) -> CurrentProfile:
    """FastAPI dependency: only let admins through.

    Used on the /admin/* endpoints, where there is no ownership concept to
    fall back on - a non-admin caller is refused outright, not scoped to
    "their own" anything.
    """
    if not profile.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return profile
