"""
Candidates CRUD endpoints.

Candidates have no customer_id of their own - ownership flows through
candidates.job_id -> jobs.customer_id, so every check here ultimately
delegates to the job the candidate belongs to (get_job_or_404 /
check_job_ownership, imported from app/routers/jobs.py).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.auth.profile import CurrentProfile, get_current_profile
from app.db.client import get_supabase
from app.db.errors import translate_constraint_violations
from app.models.candidates import (
    CandidateCreate,
    CandidateRead,
    CandidateUpdate,
    KanbanBoard,
    STAGES,
)
from app.routers.jobs import check_job_ownership, get_job_or_404

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _get_candidate_or_404(supabase: Client, candidate_id: UUID) -> dict:
    """Fetch a candidate row by id, raising 404 if it doesn't exist."""
    response = (
        supabase.table("candidates")
        .select("*")
        .eq("id", str(candidate_id))
        .maybe_single()
        .execute()
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found"
        )
    return response.data


def _check_candidate_ownership(
    supabase: Client, candidate: dict, profile: CurrentProfile
) -> None:
    """Raise 403 unless the caller is admin or owns the job this candidate
    belongs to. A missing job is treated as "forbidden" (deny by default)
    rather than assumed impossible - even though ON DELETE CASCADE means a
    candidate can't normally outlive its job."""
    if profile.is_admin:
        return

    job_response = (
        supabase.table("jobs")
        .select("customer_id")
        .eq("id", candidate["job_id"])
        .maybe_single()
        .execute()
    )
    if job_response is None or job_response.data["customer_id"] != profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your candidate"
        )


def _filtered_candidates(
    supabase: Client,
    profile: CurrentProfile,
    job_id: UUID | None,
    name: str | None,
) -> list[dict]:
    """Shared filtering/ownership logic behind GET /candidates and
    GET /candidates/kanban - kept in one place so the two response shapes
    (flat list vs. grouped-by-stage board) can never drift apart on what
    they actually show.

    If job_id is given, its ownership is checked directly (404 if it
    doesn't exist, 403 if the caller doesn't own it and isn't admin) -
    an invalid or unowned job_id is a hard error here, never a silent
    empty result. If omitted, a customer's results are restricted to
    their own job ids up front (two plain queries rather than one
    embedded-join filter, kept simple and easy to audit since this is
    security-critical code); an admin without job_id sees everything.

    name, if given, is a case-insensitive partial match against
    candidates.name (PostgREST handles the value safely - no SQL
    injection risk - though a literal '%' or '_' in the search term is
    still interpreted as a wildcard).
    """
    if job_id is not None:
        job = get_job_or_404(supabase, job_id)
        check_job_ownership(job, profile)
        query = supabase.table("candidates").select("*").eq("job_id", str(job_id))
    elif profile.is_admin:
        query = supabase.table("candidates").select("*")
    else:
        owned_jobs = (
            supabase.table("jobs").select("id").eq("customer_id", profile.id).execute()
        )
        owned_job_ids = [row["id"] for row in owned_jobs.data]
        if not owned_job_ids:
            return []
        query = supabase.table("candidates").select("*").in_("job_id", owned_job_ids)

    if name is not None:
        query = query.ilike("name", f"%{name}%")

    return query.execute().data


@router.get("", response_model=list[CandidateRead])
def list_candidates(
    job_id: UUID | None = None,
    name: str | None = None,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> list[dict]:
    """List candidates, optionally filtered by job_id and/or name (case-
    insensitive partial match). See _filtered_candidates for the full
    filtering/ownership rules."""
    return _filtered_candidates(supabase, profile, job_id, name)


@router.get("/kanban", response_model=KanbanBoard)
def list_candidates_kanban(
    job_id: UUID | None = None,
    name: str | None = None,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> KanbanBoard:
    """Same filtering/ownership rules as GET /candidates, grouped by stage
    for a kanban board view instead of a flat list.

    Registered before GET /{candidate_id} on purpose: FastAPI/Starlette
    matches path routes in registration order, and both "/kanban" and
    "/{candidate_id}" are single path segments under /candidates - if
    {candidate_id} were registered first, a request to /candidates/kanban
    would match it instead, trying (and failing) to parse "kanban" as a
    UUID.
    """
    candidates = _filtered_candidates(supabase, profile, job_id, name)
    grouped: dict[str, list[dict]] = {stage: [] for stage in STAGES}
    for candidate in candidates:
        grouped[candidate["stage"]].append(candidate)
    return KanbanBoard(**grouped)


@router.post("", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
def create_candidate(
    candidate_in: CandidateCreate,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Create a candidate under a job. Ownership of the job determines who
    may add candidates to it - same rule as reading/updating one."""
    job = get_job_or_404(supabase, candidate_in.job_id)
    check_job_ownership(job, profile)

    payload = candidate_in.model_dump(mode="json")

    with translate_constraint_violations():
        response = supabase.table("candidates").insert(payload).execute()
    return response.data[0]


@router.get("/{candidate_id}", response_model=CandidateRead)
def get_candidate(
    candidate_id: UUID,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Get a single candidate by id."""
    candidate = _get_candidate_or_404(supabase, candidate_id)
    _check_candidate_ownership(supabase, candidate, profile)
    return candidate


@router.patch("/{candidate_id}", response_model=CandidateRead)
def update_candidate(
    candidate_id: UUID,
    candidate_in: CandidateUpdate,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Partially update a candidate, including its stage."""
    candidate = _get_candidate_or_404(supabase, candidate_id)
    _check_candidate_ownership(supabase, candidate, profile)

    updates = candidate_in.model_dump(exclude_unset=True, mode="json")
    if not updates:
        return candidate

    with translate_constraint_violations():
        response = (
            supabase.table("candidates")
            .update(updates)
            .eq("id", str(candidate_id))
            .execute()
        )
    return response.data[0]
