"""
Tests for the /jobs CRUD endpoints.

Uses the fake in-memory Supabase client (conftest.py's FakeSupabase, via
the `act_as` fixture) instead of a real database - see app/db/client.py's
docstring for why get_supabase is a plain FastAPI dependency, which is
exactly what makes this swap possible.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import ADMIN_ID, CUSTOMER_ID, OTHER_CUSTOMER_ID

client = TestClient(app)


def test_customer_creates_and_lists_own_job(act_as):
    """Happy path: a customer creates a job and sees it in their own list."""
    act_as(id=CUSTOMER_ID, role="customer")

    created = client.post("/jobs", json={"title": "Backend engineer"})
    assert created.status_code == 201
    assert created.json()["customer_id"] == CUSTOMER_ID

    listed = client.get("/jobs")
    assert listed.status_code == 200
    assert [job["id"] for job in listed.json()] == [created.json()["id"]]


def test_customer_cannot_read_other_customers_job(act_as):
    """Authorization failure: ownership blocks reading another customer's job."""
    act_as(id=CUSTOMER_ID, role="customer")
    job_id = client.post("/jobs", json={"title": "x"}).json()["id"]

    act_as(id=OTHER_CUSTOMER_ID, role="customer")
    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 403


def test_customer_cannot_update_other_customers_job(act_as):
    """Authorization failure: ownership blocks updating another customer's job."""
    act_as(id=CUSTOMER_ID, role="customer")
    job_id = client.post("/jobs", json={"title": "x"}).json()["id"]

    act_as(id=OTHER_CUSTOMER_ID, role="customer")
    response = client.patch(f"/jobs/{job_id}", json={"title": "hijacked"})

    assert response.status_code == 403


def test_get_missing_job_returns_404(act_as):
    act_as(id=CUSTOMER_ID, role="customer")
    response = client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_admin_sees_jobs_from_every_customer(act_as):
    """Admin bypasses ownership entirely and sees every job."""
    act_as(id=CUSTOMER_ID, role="customer")
    client.post("/jobs", json={"title": "job 1"})

    act_as(id=OTHER_CUSTOMER_ID, role="customer")
    client.post("/jobs", json={"title": "job 2"})

    act_as(id=ADMIN_ID, role="admin")
    response = client.get("/jobs")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_admin_without_acting_as_header_cannot_create_job(act_as):
    """No effective customer (plain admin, no header) - 400, not a silently
    unowned job."""
    act_as(id=ADMIN_ID, role="admin")
    response = client.post("/jobs", json={"title": "x"})
    assert response.status_code == 400


def test_admin_acting_as_unknown_customer_returns_404(act_as):
    """A header that doesn't resolve to a real customer profile is a hard
    404 from get_effective_customer_id, not a silent bypass."""
    act_as(id=ADMIN_ID, role="admin")
    response = client.post(
        "/jobs",
        json={"title": "x"},
        headers={"X-Acting-As-Customer": "00000000-0000-0000-0000-000000000099"},
    )
    assert response.status_code == 404


def test_admin_acting_as_another_admin_returns_404(act_as):
    """The header must resolve to a customer specifically - pointing it at
    another admin's id is also a 404, not a role bypass."""
    act_as(id=ADMIN_ID, role="admin")
    other_admin_id = "00000000-0000-0000-0000-00000000ad02"
    act_as(id=other_admin_id, role="admin")  # registers it as a real profile
    act_as(id=ADMIN_ID, role="admin")  # switch back to the acting admin

    response = client.post(
        "/jobs",
        json={"title": "x"},
        headers={"X-Acting-As-Customer": other_admin_id},
    )
    assert response.status_code == 404


def test_admin_acting_as_customer_creates_job_for_them(act_as):
    """Happy path: admin + valid header creates the job for that customer,
    exactly like the customer would themselves."""
    act_as(id=ADMIN_ID, role="admin")
    act_as(id=CUSTOMER_ID, role="customer")  # registers the customer profile
    act_as(id=ADMIN_ID, role="admin")  # switch back to the acting admin

    response = client.post(
        "/jobs",
        json={"title": "x"},
        headers={"X-Acting-As-Customer": CUSTOMER_ID},
    )
    assert response.status_code == 201
    assert response.json()["customer_id"] == CUSTOMER_ID


def test_customer_acting_as_header_is_ignored(act_as):
    """A customer can never use the header to act as someone else - it's
    silently ignored regardless of what it contains."""
    act_as(id=CUSTOMER_ID, role="customer")

    response = client.post(
        "/jobs",
        json={"title": "x"},
        headers={"X-Acting-As-Customer": OTHER_CUSTOMER_ID},
    )

    assert response.status_code == 201
    assert response.json()["customer_id"] == CUSTOMER_ID


def test_create_job_requires_title(act_as):
    act_as(id=CUSTOMER_ID, role="customer")
    response = client.post("/jobs", json={})
    assert response.status_code == 422


def test_owner_updates_job(act_as):
    act_as(id=CUSTOMER_ID, role="customer")
    job_id = client.post("/jobs", json={"title": "x"}).json()["id"]

    response = client.patch(f"/jobs/{job_id}", json={"status": "closed"})

    assert response.status_code == 200
    assert response.json()["status"] == "closed"
