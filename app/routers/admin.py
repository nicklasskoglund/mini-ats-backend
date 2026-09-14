"""
Admin-only account management: creating admin/customer accounts via
Supabase's invite flow, and listing customers to fuel a future frontend's
"act as a customer" picker (see app/auth/effective_customer.py for how
that acting-as flow actually works once a customer id is chosen).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from supabase_auth.errors import AuthApiError

from app.auth.profile import CurrentProfile, require_admin
from app.db.client import get_supabase
from app.models.admin import AdminAccountCreate, AdminAccountRead, CustomerSummary

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/accounts", response_model=AdminAccountRead, status_code=status.HTTP_201_CREATED
)
def create_account(
    account_in: AdminAccountCreate,
    _admin: CurrentProfile = Depends(require_admin),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Invite a new admin or customer account.

    No password is ever set here - Supabase's invite flow emails the new
    user a link to set their own. role/full_name/company_name are passed
    as user_metadata, which handle_new_user (supabase/schemas/profiles.sql)
    reads to populate the profiles row in the same step - no separate
    UPDATE against profiles happens afterwards.

    redirect_to is left at Supabase's default for v1 (there's no frontend
    yet to send invited users to - see the assumptions doc; this gets
    pointed at mini-ats-frontend once it exists).

    Verified locally against Supabase's Admin API: inviting an email that
    belongs to an already-confirmed user raises AuthApiError with
    code="email_exists" (status 422 from Supabase itself) - translated to
    409 here. Re-inviting an unconfirmed/pending invite does NOT error
    (Supabase just resends it), which is also the desired behavior.
    """
    if account_in.role == "customer" and not account_in.company_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="company_name is required when role is 'customer'",
        )

    try:
        result = supabase.auth.admin.invite_user_by_email(
            account_in.email,
            {
                "data": {
                    "role": account_in.role,
                    "full_name": account_in.full_name,
                    "company_name": account_in.company_name,
                }
            },
        )
    except AuthApiError as exc:
        if exc.code == "email_exists":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc
        raise

    return {
        "id": result.user.id,
        "email": result.user.email,
        "role": account_in.role,
        "full_name": account_in.full_name,
        "company_name": account_in.company_name,
    }


@router.get("/customers", response_model=list[CustomerSummary])
def list_customers(
    _admin: CurrentProfile = Depends(require_admin),
    supabase: Client = Depends(get_supabase),
) -> list[dict]:
    """List every customer profile, with email joined in from auth.users
    (profiles has no email column of its own - see
    supabase/schemas/profiles.sql).

    Note: list_users() is paginated by Supabase's Admin API; at the current
    (single-digit) customer count this returns everyone in one page, but a
    large customer base would need explicit pagination here eventually -
    not a concern for this project's scale/timeframe.
    """
    profiles = (
        supabase.table("profiles")
        .select("id, full_name, company_name")
        .eq("role", "customer")
        .execute()
        .data
    )
    emails_by_id = {user.id: user.email for user in supabase.auth.admin.list_users()}
    return [
        {**profile, "email": emails_by_id.get(profile["id"])} for profile in profiles
    ]
