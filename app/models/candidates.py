"""
Pydantic schemas for the candidates resource.

Ownership of a candidate flows through candidates.job_id -> jobs.customer_id
(see app/routers/candidates.py) rather than a direct customer_id column, so
there's nothing here equivalent to JobCreate's admin-only customer_id -
`job_id` itself is what gets ownership-checked.
"""

from datetime import datetime
from typing import Literal, get_args
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

Stage = Literal["new", "screening", "interview", "offer", "hired", "rejected"]
STAGES: tuple[str, ...] = get_args(Stage)


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


class KanbanBoard(BaseModel):
    """Candidates grouped by stage, for a kanban board view.

    All six stages are always present (as an empty list if there are no
    candidates in that stage yet), so clients can render every column
    without special-casing a missing key.
    """

    new: list[CandidateRead] = []
    screening: list[CandidateRead] = []
    interview: list[CandidateRead] = []
    offer: list[CandidateRead] = []
    hired: list[CandidateRead] = []
    rejected: list[CandidateRead] = []
