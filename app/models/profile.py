"""
Pydantic schemas for the /profile endpoint - the effective customer's own
profile, or (for an admin acting as a customer) that customer's profile.

Distinct from app/auth/profile.py's CurrentProfile: that's the internal
"who is making this request" object built from a verified JWT + a role
lookup, not an API request/response shape. This module is the shape
clients actually send and receive over HTTP.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class ProfileUpdate(BaseModel):
    """Request body for PATCH /profile. All fields optional (partial
    update) - only fields present in the request are changed. role is
    deliberately not here: changing your own (or an acted-as customer's)
    role is not something this endpoint allows.
    """

    full_name: str | None = None
    company_name: str | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    contact_email: EmailStr | None = None
    address: str | None = None
    description: str | None = None


class ProfileRead(BaseModel):
    """Profile as returned by GET/PATCH /profile."""

    id: UUID
    role: str
    full_name: str | None
    company_name: str | None
    website_url: str | None
    linkedin_url: str | None
    phone: str | None
    contact_email: str | None
    address: str | None
    description: str | None
    created_at: datetime
