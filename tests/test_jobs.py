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


def test_admin_must_supply_customer_id(act_as):
    act_as(id=ADMIN_ID, role="admin")
    response = client.post("/jobs", json={"title": "x"})
    assert response.status_code == 422


def test_admin_with_unknown_customer_id_returns_422(act_as):
    """A foreign key violation (no such profile) is translated to 422, not 500."""
    act_as(id=ADMIN_ID, role="admin")
    response = client.post(
        "/jobs",
        json={"title": "x", "customer_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert response.status_code == 422


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
