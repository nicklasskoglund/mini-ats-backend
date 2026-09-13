"""
Jobs CRUD endpoints.

Ownership: a job belongs to jobs.customer_id. Customers only ever see/edit
their own jobs; admins bypass ownership entirely. There is no "act as a
specific customer" yet (that's step 6) - see the customer_id handling in
create_job for the temporary stand-in.

get_job_or_404 and check_job_ownership are also imported by
app/routers/candidates.py, since candidate ownership flows through the
job a candidate belongs to.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.auth.profile import CurrentProfile, get_current_profile
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


def check_job_ownership(job: dict, profile: CurrentProfile) -> None:
    """Raise 403 unless the caller is admin or owns this job."""
    if not profile.is_admin and job["customer_id"] != profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your job"
        )


@router.get("", response_model=list[JobRead])
def list_jobs(
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> list[dict]:
    """List jobs: customers see only their own, admins see all."""
    query = supabase.table("jobs").select("*")
    if not profile.is_admin:
        query = query.eq("customer_id", profile.id)
    return query.execute().data


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(
    job_in: JobCreate,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Create a job.

    Customers: `customer_id` is always their own id - any value they send
    is ignored. Admins: must supply `customer_id` explicitly in the body.
    This is a temporary stand-in until "act as a customer" (step 6) exists;
    it's not validated against `profiles` here, so an admin sending an id
    that doesn't belong to a real profile gets a 422 (foreign key
    violation, translated by translate_constraint_violations) rather than
    silently creating an orphaned job.
    """
    if profile.is_admin:
        if job_in.customer_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="customer_id is required when creating a job as admin",
            )
        customer_id = job_in.customer_id
    else:
        customer_id = profile.id

    payload = job_in.model_dump(exclude={"customer_id"}, mode="json")
    payload["customer_id"] = str(customer_id)

    with translate_constraint_violations():
        response = supabase.table("jobs").insert(payload).execute()
    return response.data[0]


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: UUID,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Get a single job by id."""
    job = get_job_or_404(supabase, job_id)
    check_job_ownership(job, profile)
    return job


@router.patch("/{job_id}", response_model=JobRead)
def update_job(
    job_id: UUID,
    job_in: JobUpdate,
    profile: CurrentProfile = Depends(get_current_profile),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Partially update a job (only fields present in the request body)."""
    job = get_job_or_404(supabase, job_id)
    check_job_ownership(job, profile)

    updates = job_in.model_dump(exclude_unset=True, mode="json")
    if not updates:
        return job

    with translate_constraint_violations():
        response = (
            supabase.table("jobs").update(updates).eq("id", str(job_id)).execute()
        )
    return response.data[0]
