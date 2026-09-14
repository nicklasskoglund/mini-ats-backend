"""
Pydantic schemas for the jobs resource.

Separate Create/Update/Read models because the fields a client may submit
differ from what an endpoint accepts as an update and from what's returned
in a response. Notably, JobCreate has no customer_id field at all: it's
always derived server-side from get_effective_customer_id (see
app/routers/jobs.py) - a client (customer or admin) can never set it
directly.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    """Request body for creating a job."""

    title: str = Field(min_length=1)
    description: str | None = None
    status: str = "open"


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
