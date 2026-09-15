"""
GET/PATCH /profile - the effective customer's own profile.

Reuses get_effective_customer_id (app/auth/effective_customer.py) exactly
as jobs/candidates do: no new authorization logic. A customer always gets
their own row; an admin gets 400 without an X-Acting-As-Customer header
(no "whose profile?" to answer otherwise) and the chosen customer's row
with one.

Deliberately excluded: GET /me (app/routers/me.py) stays a plain "who am
I" identity check, unaffected by X-Acting-As-Customer - it answers a
different question than this endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.effective_customer import get_effective_customer_id
from app.db.client import get_supabase
from app.models.profile import ProfileRead, ProfileUpdate
from supabase import Client

router = APIRouter(prefix="/profile", tags=["profile"])


def _require_effective_customer(effective_customer_id: str | None) -> str:
    """Raise 400 if there's no effective customer to read/update a profile
    for (a plain admin, no X-Acting-As-Customer header) - same "no
    effective customer" pattern as POST /jobs."""
    if effective_customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No effective customer - admins must set X-Acting-As-Customer "
                "to read or update a profile"
            ),
        )
    return effective_customer_id


def _get_profile_or_404(supabase: Client, customer_id: str) -> dict:
    """Fetch a profile row by id, raising 404 if it doesn't exist.

    Shouldn't happen in practice: get_effective_customer_id already
    confirmed this id belongs to a real customer profile (either it's the
    caller's own, verified via get_current_profile, or the header was
    already resolved against profiles). Checked anyway rather than assumed
    - a defensive 404 beats an unhandled crash if that invariant is ever
    violated.
    """
    response = (
        supabase.table("profiles")
        .select("*")
        .eq("id", customer_id)
        .maybe_single()
        .execute()
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )
    return response.data


@router.get("", response_model=ProfileRead)
def get_profile(
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Get the effective customer's profile."""
    customer_id = _require_effective_customer(effective_customer_id)
    return _get_profile_or_404(supabase, customer_id)


@router.patch("", response_model=ProfileRead)
def update_profile(
    profile_in: ProfileUpdate,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Partially update the effective customer's profile (only fields
    present in the request body)."""
    customer_id = _require_effective_customer(effective_customer_id)
    profile_row = _get_profile_or_404(supabase, customer_id)

    updates = profile_in.model_dump(exclude_unset=True, mode="json")
    if not updates:
        return profile_row

    response = (
        supabase.table("profiles").update(updates).eq("id", customer_id).execute()
    )
    return response.data[0]
