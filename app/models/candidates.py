"""
Pydantic schemas for the candidates resource.

Ownership of a candidate flows through candidates.job_id -> jobs.customer_id
(see app/routers/candidates.py) rather than a direct customer_id column, so
there's nothing here equivalent to JobCreate's admin-only customer_id -
`job_id` itself is what gets ownership-checked.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

Stage = Literal["new", "screening", "interview", "offer", "hired", "rejected"]


class CandidateCreate(BaseModel):
    """Request body for creating a candidate."""

    job_id: UUID
    name: str = Field(min_length=1)
    email: EmailStr | None = None
    linkedin_url: str | None = None
    cv_text: str | None = None


class CandidateUpdate(BaseModel):
    """Request body for updating a candidate, including its stage. All
    fields optional (partial update)."""

    name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None
    linkedin_url: str | None = None
    cv_text: str | None = None
    stage: Stage | None = None


class CandidateRead(BaseModel):
    """Candidate as returned by the API."""

    id: UUID
    job_id: UUID
    name: str
    email: str | None
    linkedin_url: str | None
    cv_text: str | None
    stage: Stage
    ai_score: int | None
    ai_summary: str | None
    created_at: datetime
