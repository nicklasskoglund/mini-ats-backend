"""
Pydantic schemas for admin-only endpoints: account creation and the
customer list that fuels a future "act as a customer" picker in the
frontend.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

Role = Literal["admin", "customer"]


class AdminAccountCreate(BaseModel):
    """Request body for POST /admin/accounts.

    The password flow differs by role (checked in app/routers/admin.py,
    not here, since both checks depend on another field's value and the
    spec calls for 400s, not the 422s a Pydantic validator would produce):

    - role="admin": password is required (min 8 chars) - the admin sets it
      directly via create_user(email_confirm=True), no email is sent.
    - role="customer": password must be omitted - the customer sets their
      own via Supabase's invite email (invite_user_by_email()). An admin
      is never in a position to know or set a customer's password.

    company_name is required when role="customer", same as before.
    """

    email: EmailStr
    password: str | None = Field(default=None, min_length=8)
    role: Role
    full_name: str | None = None
    company_name: str | None = None


class AdminAccountRead(BaseModel):
    """The created account, as returned by POST /admin/accounts."""

    id: UUID
    email: str
    role: Role
    full_name: str | None
    company_name: str | None


class CustomerSummary(BaseModel):
    """One row in GET /admin/customers - fuels the "act as a customer" picker."""

    id: UUID
    full_name: str | None
    company_name: str | None
    # Optional despite every profile having a corresponding auth.users row
    # (FK-enforced): defensive against list_users() pagination ever leaving
    # a user out of the id->email join - see app/routers/admin.py.
    email: str | None
