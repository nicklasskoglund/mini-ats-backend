"""
Pydantic schemas for the jobs resource.

Separate Create/Update/Read models because the fields a client may submit
differ from what an endpoint accepts as an update and from what's
returned in a response. In particular, `customer_id` on JobCreate is
optional at the schema level only because who's allowed to set it (and to
what) depends on the caller's role - a customer's own id is used and any
value they send is ignored, while an admin must send it explicitly. That
branching is enforced in app/routers/jobs.py, not here.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    """Request body for creating a job."""

    title: str = Field(min_length=1)
    description: str | None = None
    status: str = "open"
    customer_id: UUID | None = None


class JobUpdate(BaseModel):
    """Request body for updating a job. All fields optional (partial update)."""

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: str | None = None


class JobRead(BaseModel):
    """Job as returned by the API."""

    id: UUID
    customer_id: UUID
    title: str
    description: str | None
    status: str
    created_at: datetime
