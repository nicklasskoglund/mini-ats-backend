"""
Jobs CRUD endpoints.

Ownership: a job belongs to jobs.customer_id. Every endpoint here is scoped
by get_effective_customer_id (app/auth/effective_customer.py) rather than
checking the caller's role directly - for a plain customer that's always
their own id; for an admin it's None ("no restriction", i.e. see/act on
everything) unless they're acting as a specific customer via the
X-Acting-As-Customer header, in which case it's that customer's id. This
means customer and admin-acting-as-customer share the exact same code path
below; there's no separate admin branch to keep in sync.

get_job_or_404 and check_job_ownership are also imported by
app/routers/candidates.py, since candidate ownership flows through the
job a candidate belongs to.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.auth.effective_customer import get_effective_customer_id
from app.db.client import get_supabase
from app.db.errors import translate_constraint_violations
from app.models.jobs import JobCreate, JobRead, JobUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_or_404(supabase: Client, job_id: UUID) -> dict:
    """Fetch a job row by id, raising 404 if it doesn't exist."""
    response = (
        supabase.table("jobs")
        .select("*")
        .eq("id", str(job_id))
        .maybe_single()
        .execute()
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return response.data


def check_job_ownership(job: dict, effective_customer_id: str | None) -> None:
    """Raise 403 unless there's no restriction (admin, not acting as
    anyone) or the job belongs to the effective customer."""
    if effective_customer_id is not None and job["customer_id"] != effective_customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your job"
        )


@router.get("", response_model=list[JobRead])
def list_jobs(
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> list[dict]:
    """List jobs: scoped to the effective customer, or all of them if
    there's no restriction (plain admin)."""
    query = supabase.table("jobs").select("*")
    if effective_customer_id is not None:
        query = query.eq("customer_id", effective_customer_id)
    return query.execute().data


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(
    job_in: JobCreate,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Create a job for the effective customer.

    An admin with no X-Acting-As-Customer header has no effective customer
    to create the job for, hence 400 - admins must act as a specific
    customer to create a job on their behalf (no "unowned" jobs).
    """
    if effective_customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No effective customer - admins must set X-Acting-As-Customer "
                "to create a job"
            ),
        )

    payload = job_in.model_dump(mode="json")
    payload["customer_id"] = effective_customer_id

    with translate_constraint_violations():
        response = supabase.table("jobs").insert(payload).execute()
    return response.data[0]


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: UUID,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Get a single job by id."""
    job = get_job_or_404(supabase, job_id)
    check_job_ownership(job, effective_customer_id)
    return job


@router.patch("/{job_id}", response_model=JobRead)
def update_job(
    job_id: UUID,
    job_in: JobUpdate,
    effective_customer_id: str | None = Depends(get_effective_customer_id),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Partially update a job (only fields present in the request body)."""
    job = get_job_or_404(supabase, job_id)
    check_job_ownership(job, effective_customer_id)

    updates = job_in.model_dump(exclude_unset=True, mode="json")
    if not updates:
        return job

    with translate_constraint_violations():
        response = (
            supabase.table("jobs").update(updates).eq("id", str(job_id)).execute()
        )
    return response.data[0]
