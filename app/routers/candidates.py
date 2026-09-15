"""
Candidates CRUD endpoints.

Candidates have no customer_id of their own - ownership flows through
candidates.job_id -> jobs.customer_id, so every check here ultimately
delegates to the job the candidate belongs to (get_job_or_404 /
check_job_ownership, imported from app/routers/jobs.py). Like jobs.py,
every endpoint here is scoped by get_effective_customer_id rather than the
caller's raw role - see app/auth/effective_customer.py.
"""

from uuid import UUID

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.auth.effective_customer import get_effective_customer_id
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
from app.services.ai_assessment import (
    AssessmentFailed,
    assess_candidate,
    get_anthropic_client,
)

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
    supabase: Client, candidate: dict, effective_customer_id: str | None
) -> None:
    """Raise 403 unless there's no restriction (admin, not acting as
    anyone) or the candidate's job belongs to the effective customer. A
    missing job is treated as "forbidden" (deny by default) rather than
    assumed impossible - even though ON DELETE CASCADE means a candidate
    can't normally outlive its job."""
    if effective_customer_id is None:
        return

    job_response = (
        supabase.table("jobs")
        .select("customer_id")
        .eq("id", candidate["job_id"])
        .maybe_single()
        .execute()
    )
    if job_response is None or job_response.data["customer_id"] != effective_customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your candidate"
        )


def _filtered_candidates(
    supabase: Client,
    effective_customer_id: str | None,
    job_id: UUID | None,
    name: str | None,
) -> list[dict]:
    """Shared filtering/ownership logic behind GET /candidates and
    GET /candidates/kanban - kept in one place so the two response shapes
    (flat list vs. grouped-by-stage board) can never drift apart on what
    they actually show.

    If job_id is given, its ownership is checked directly (404 if it
    doesn't exist, 403 if it doesn't belong to the effective customer) -
    an invalid or unowned job_id is a hard error here, never a silent
    empty result. If omitted, results are restricted to the effective
    customer's own job ids up front (two plain queries rather than one
    embedded-join filter, kept simple and easy to audit since this is
    security-critical code); no effective customer (plain admin) sees
    everything.

    name, if given, is a case-insensitive partial match against
    candidates.name (PostgREST handles the value safely - no SQL
    injection risk - though a literal '%' or '_' in the search term is
    still interpreted as a wildcard).
    """
    if job_id is not None:
        job = get_job_or_404(supabase, job_id)
        check_job_ownership(job, effective_customer_id)
        query = supabase.table("candidates").select("*").eq("job_id", str(job_id))
    elif effective_customer_id is None:
        query = supabase.table("candidates").select("*")
    else:
        owned_jobs = (
            supabase.table("jobs")
            .select("id")
            .eq("customer_id", effective_customer_id)
            .execute()
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
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> list[dict]:
    """List candidates, optionally filtered by job_id and/or name (case-
    insensitive partial match). See _filtered_candidates for the full
    filtering/ownership rules."""
    return _filtered_candidates(supabase, effective_customer_id, job_id, name)


@router.get("/kanban", response_model=KanbanBoard)
def list_candidates_kanban(
    job_id: UUID | None = None,
    name: str | None = None,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
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
    candidates = _filtered_candidates(supabase, effective_customer_id, job_id, name)
    grouped: dict[str, list[dict]] = {stage: [] for stage in STAGES}
    for candidate in candidates:
        grouped[candidate["stage"]].append(candidate)
    return KanbanBoard(**grouped)


@router.post("", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
def create_candidate(
    candidate_in: CandidateCreate,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Create a candidate under a job. Ownership of the job determines who
    may add candidates to it - same rule as reading/updating one. Unlike
    POST /jobs, there's no "no effective customer" 400 here: the job
    already has an owner, so an admin with no X-Acting-As-Customer header
    can add a candidate to any job (no restriction applies)."""
    job = get_job_or_404(supabase, candidate_in.job_id)
    check_job_ownership(job, effective_customer_id)

    payload = candidate_in.model_dump(mode="json")

    with translate_constraint_violations():
        response = supabase.table("candidates").insert(payload).execute()
    return response.data[0]


@router.get("/{candidate_id}", response_model=CandidateRead)
def get_candidate(
    candidate_id: UUID,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Get a single candidate by id."""
    candidate = _get_candidate_or_404(supabase, candidate_id)
    _check_candidate_ownership(supabase, candidate, effective_customer_id)
    return candidate


@router.patch("/{candidate_id}", response_model=CandidateRead)
def update_candidate(
    candidate_id: UUID,
    candidate_in: CandidateUpdate,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Partially update a candidate, including its stage."""
    candidate = _get_candidate_or_404(supabase, candidate_id)
    _check_candidate_ownership(supabase, candidate, effective_customer_id)

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


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: UUID,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> None:
    """Delete a candidate. No child rows to worry about, so no cascade
    check needed (unlike DELETE /jobs/{id})."""
    candidate = _get_candidate_or_404(supabase, candidate_id)
    _check_candidate_ownership(supabase, candidate, effective_customer_id)

    supabase.table("candidates").delete().eq("id", str(candidate_id)).execute()


@router.post("/{candidate_id}/assess", response_model=CandidateRead)
def assess_candidate_endpoint(
    candidate_id: UUID,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
    ai_client: anthropic.Anthropic = Depends(get_anthropic_client),
) -> dict:
    """Run an AI assessment of the candidate's CV against their job's
    description (see app/services/ai_assessment.py), saving ai_score,
    ai_summary, ai_strengths, and ai_gaps together on success - never
    partially, so a failed or malformed AI response can't leave the
    candidate with some fields updated and others stale.

    Same ownership rule as reading/updating a candidate. A 502 (not 500)
    on any AI failure - timeout, rate limit, or an unusable response -
    with a generic message; no Anthropic-specific detail reaches the
    client (see AssessmentFailed's docstring).
    """
    candidate = _get_candidate_or_404(supabase, candidate_id)
    _check_candidate_ownership(supabase, candidate, effective_customer_id)

    if not candidate.get("cv_text"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="cv_text is required to run an assessment",
        )

    job = get_job_or_404(supabase, UUID(candidate["job_id"]))

    try:
        result = assess_candidate(
            ai_client, job.get("description") or "", candidate["cv_text"]
        )
    except AssessmentFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI assessment is temporarily unavailable, try again shortly",
        ) from exc

    updates = {
        "ai_score": result.score,
        "ai_summary": result.summary,
        "ai_strengths": result.strengths,
        "ai_gaps": result.gaps,
    }
    response = (
        supabase.table("candidates")
        .update(updates)
        .eq("id", str(candidate_id))
        .execute()
    )
    return response.data[0]
