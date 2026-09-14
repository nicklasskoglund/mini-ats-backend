"""
Pydantic schemas for admin-only endpoints: account creation and the
customer list that fuels a future "act as a customer" picker in the
frontend.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

Role = Literal["admin", "customer"]


class AdminAccountCreate(BaseModel):
    """Request body for POST /admin/accounts.

    No password field: admins never set a password for someone else - the
    invited user sets their own via Supabase's invite email. Whether
    company_name is actually required (only when role="customer") is
    checked in app/routers/admin.py rather than here, since it depends on
    another field's value and the spec calls for a 400, not the 422
    FastAPI would produce from a Pydantic validator.
    """

    email: EmailStr
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
