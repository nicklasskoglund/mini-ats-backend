"""
Minimal protected endpoint proving JWT verification works end-to-end.

Returns the identity FastAPI derived from the caller's verified token.
Kept deliberately separate from role-based authorization: this endpoint
only proves *authentication* (who you are); it does not check *what
you're allowed to do*, since that requires the `profiles` table (step 3+).
"""

from fastapi import APIRouter, Depends

from app.auth.jwt import CurrentUser, get_current_user

router = APIRouter()


@router.get("/me")
def read_current_user(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, str | None]:
    """Return the authenticated caller's user id and email from their JWT."""
    return {"user_id": current_user.user_id, "email": current_user.email}
