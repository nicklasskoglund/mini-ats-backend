"""
Admin-only account management: creating admin accounts (admin sets the
password directly, active immediately, no email sent) and inviting
customer accounts (customer sets their own password via Supabase's invite
email - an admin is never in a position to know or set it), plus listing
customers to fuel a future frontend's "act as a customer" picker (see
app/auth/effective_customer.py for how that acting-as flow actually works
once a customer id is chosen).
"""

from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from supabase_auth.errors import AuthApiError

from app.auth.profile import CurrentProfile, require_admin
from app.db.client import get_supabase
from app.models.admin import AdminAccountCreate, AdminAccountRead, CustomerSummary

router = APIRouter(prefix="/admin", tags=["admin"])


@contextmanager
def _translate_email_exists():
    """Wrap a Supabase Auth Admin API call; re-raise a duplicate-email
    error as 409, instead of letting Supabase's own 422 leak through.

    Verified locally against both calls this router makes:
    create_user() and invite_user_by_email() each raise AuthApiError with
    code="email_exists" (status 422 from Supabase itself) for an email
    that belongs to an existing, confirmed user - checked independently
    for each, since they're different API calls and nothing guarantees
    they'd share an error shape. Re-inviting an unconfirmed/pending invite
    does NOT error (Supabase just resends it), which is fine as-is.
    """
    try:
        yield
    except AuthApiError as exc:
        if exc.code == "email_exists":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc
        raise


@router.post(
    "/accounts", response_model=AdminAccountRead, status_code=status.HTTP_201_CREATED
)
def create_account(
    account_in: AdminAccountCreate,
    _admin: CurrentProfile = Depends(require_admin),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Create a new admin account, or invite a new customer account - the
    two paths differ, not just in which Supabase Admin API call is made:

    - role="admin": password required. Created via create_user() with
      email_confirm=True - active immediately, no email sent.
    - role="customer": password must be omitted (400 if present - an
      admin never sets a customer's password). Created via
      invite_user_by_email() instead; redirect_to is left at Supabase's
      default since there's no frontend yet to send the customer to. The
      customer sets their own password by following the link in the
      invite email.

    Either way, role/full_name/company_name are passed as user metadata
    for handle_new_user (supabase/schemas/profiles.sql) to read - no
    separate UPDATE against profiles happens afterwards. Verified locally
    that the profiles row exists as soon as the invite is sent, not when
    the customer confirms it - so "act as a customer" (see
    app/auth/effective_customer.py) already works for a newly invited,
    still-unconfirmed customer.
    """
    if account_in.role == "customer":
        if not account_in.company_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="company_name is required when role is 'customer'",
            )
        if account_in.password is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "password must not be set when role is 'customer' - "
                    "the customer sets their own via the invite email"
                ),
            )

        with _translate_email_exists():
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
    else:
        if account_in.password is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="password is required when role is 'admin'",
            )

        with _translate_email_exists():
            result = supabase.auth.admin.create_user(
                {
                    "email": account_in.email,
                    "password": account_in.password,
                    "email_confirm": True,
                    "user_metadata": {
                        "role": account_in.role,
                        "full_name": account_in.full_name,
                        "company_name": account_in.company_name,
                    },
                }
            )

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


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: UUID,
    _admin: CurrentProfile = Depends(require_admin),
    supabase: Client = Depends(get_supabase),
) -> None:
    """Delete an admin or customer account. Always admin-only - there is
    no self-service account deletion for customers (same reasoning as
    PATCH /profile being the only customer-facing account-editing surface).

    For a customer account: explicitly deletes their candidates, then
    their jobs, then the auth user itself. Deliberately explicit even
    though it's technically redundant: verified locally that
    auth.admin.delete_user() alone already cascades through profiles ->
    jobs -> candidates via the existing ON DELETE CASCADE chain. Kept
    explicit anyway so this endpoint doesn't silently depend on a cascade
    three tables deep never changing, and so each step is independently
    auditable/testable.

    For an admin account: no jobs/candidates to touch, just the auth user.

    auth.admin.delete_user() removes the auth.users row (not just
    `profiles`) - deleting only the profiles row would leave a stray,
    unusable auth account behind and never free up the email address.
    """
    profile_response = (
        supabase.table("profiles")
        .select("id, role")
        .eq("id", str(account_id))
        .maybe_single()
        .execute()
    )
    if profile_response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )

    if profile_response.data["role"] == "customer":
        owned_jobs = (
            supabase.table("jobs")
            .select("id")
            .eq("customer_id", str(account_id))
            .execute()
        )
        job_ids = [row["id"] for row in owned_jobs.data]
        if job_ids:
            supabase.table("candidates").delete().in_("job_id", job_ids).execute()
            supabase.table("jobs").delete().eq(
                "customer_id", str(account_id)
            ).execute()

    try:
        supabase.auth.admin.delete_user(str(account_id))
    except AuthApiError as exc:
        # Shouldn't happen - we just confirmed the profile exists - but
        # treated as a controlled 404 rather than an unhandled 500 if that
        # invariant is ever violated (e.g. a profiles row somehow outliving
        # its auth.users row).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        ) from exc
