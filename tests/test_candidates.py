"""
Tests for the /candidates CRUD endpoints.

Same fake-Supabase approach as test_jobs.py. Candidate ownership has no
customer_id of its own - it flows through job_id -> jobs.customer_id, so
most tests here create a job first via the `act_as` fixture's current
profile.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import ADMIN_ID, CUSTOMER_ID, OTHER_CUSTOMER_ID

client = TestClient(app)


def _create_job(act_as, owner_id: str) -> str:
    """Act as `owner_id` and create a job, returning its id. Leaves the
    client acting as that owner afterwards."""
    act_as(id=owner_id, role="customer")
    return client.post("/jobs", json={"title": "Backend engineer"}).json()["id"]


def test_owner_creates_and_lists_candidate(act_as):
    """Happy path: job owner adds a candidate and can filter for it by job_id."""
    job_id = _create_job(act_as, CUSTOMER_ID)

    created = client.post(
        "/candidates",
        json={"job_id": job_id, "name": "Alice", "email": "alice@example.com"},
    )
    assert created.status_code == 201
    assert created.json()["stage"] == "new"

    listed = client.get("/candidates", params={"job_id": job_id})
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [created.json()["id"]]


def test_non_owner_cannot_create_candidate_on_others_job(act_as):
    """Authorization failure: can't add a candidate to a job you don't own."""
    job_id = _create_job(act_as, CUSTOMER_ID)

    act_as(id=OTHER_CUSTOMER_ID, role="customer")
    response = client.post("/candidates", json={"job_id": job_id, "name": "Mallory"})

    assert response.status_code == 403


def test_creating_candidate_on_missing_job_returns_404(act_as):
    act_as(id=CUSTOMER_ID, role="customer")
    response = client.post(
        "/candidates",
        json={"job_id": "00000000-0000-0000-0000-000000000000", "name": "Alice"},
    )
    assert response.status_code == 404


def test_non_owner_cannot_read_others_candidate(act_as):
    """Authorization failure: reading a candidate checks the parent job's owner."""
    job_id = _create_job(act_as, CUSTOMER_ID)
    candidate_id = client.post(
        "/candidates", json={"job_id": job_id, "name": "Alice"}
    ).json()["id"]

    act_as(id=OTHER_CUSTOMER_ID, role="customer")
    response = client.get(f"/candidates/{candidate_id}")

    assert response.status_code == 403


def test_non_owner_filtering_by_others_job_id_returns_403(act_as):
    job_id = _create_job(act_as, CUSTOMER_ID)

    act_as(id=OTHER_CUSTOMER_ID, role="customer")
    response = client.get("/candidates", params={"job_id": job_id})

    assert response.status_code == 403


def test_owner_updates_candidate_stage(act_as):
    job_id = _create_job(act_as, CUSTOMER_ID)
    candidate_id = client.post(
        "/candidates", json={"job_id": job_id, "name": "Alice"}
    ).json()["id"]

    response = client.patch(f"/candidates/{candidate_id}", json={"stage": "screening"})

    assert response.status_code == 200
    assert response.json()["stage"] == "screening"


def test_invalid_stage_is_rejected(act_as):
    job_id = _create_job(act_as, CUSTOMER_ID)
    candidate_id = client.post(
        "/candidates", json={"job_id": job_id, "name": "Alice"}
    ).json()["id"]

    response = client.patch(
        f"/candidates/{candidate_id}", json={"stage": "not-a-real-stage"}
    )

    assert response.status_code == 422


def test_list_candidates_without_job_id_scopes_to_owned_jobs(act_as):
    """Without a job_id filter, a customer only sees candidates on jobs they own."""
    job1 = _create_job(act_as, CUSTOMER_ID)
    client.post("/candidates", json={"job_id": job1, "name": "Alice"})

    job2 = _create_job(act_as, OTHER_CUSTOMER_ID)
    client.post("/candidates", json={"job_id": job2, "name": "Bob"})

    act_as(id=CUSTOMER_ID, role="customer")
    response = client.get("/candidates")

    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["Alice"]


def test_admin_lists_candidates_from_every_job(act_as):
    job_id = _create_job(act_as, CUSTOMER_ID)
    client.post("/candidates", json={"job_id": job_id, "name": "Alice"})

    act_as(id=ADMIN_ID, role="admin")
    response = client.get("/candidates")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_name_filter_matches_case_insensitive_partial(act_as):
    job_id = _create_job(act_as, CUSTOMER_ID)
    client.post("/candidates", json={"job_id": job_id, "name": "Alice Andersson"})
    client.post("/candidates", json={"job_id": job_id, "name": "Bob"})

    response = client.get("/candidates", params={"name": "ali"})

    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["Alice Andersson"]


def test_kanban_groups_candidates_by_stage(act_as):
    """The kanban board always has all six stage keys, and candidates land
    in the right one."""
    job_id = _create_job(act_as, CUSTOMER_ID)
    alice_id = client.post(
        "/candidates", json={"job_id": job_id, "name": "Alice"}
    ).json()["id"]
    client.post("/candidates", json={"job_id": job_id, "name": "Bob"})
    client.patch(f"/candidates/{alice_id}", json={"stage": "interview"})

    response = client.get("/candidates/kanban")

    assert response.status_code == 200
    board = response.json()
    assert set(board.keys()) == {
        "new",
        "screening",
        "interview",
        "offer",
        "hired",
        "rejected",
    }
    assert [c["name"] for c in board["interview"]] == ["Alice"]
    assert [c["name"] for c in board["new"]] == ["Bob"]
    assert board["screening"] == []


def test_kanban_unowned_job_id_returns_403_not_empty_board(act_as):
    """An unowned job_id is a hard error, never a silently empty board."""
    job_id = _create_job(act_as, CUSTOMER_ID)

    act_as(id=OTHER_CUSTOMER_ID, role="customer")
    response = client.get("/candidates/kanban", params={"job_id": job_id})

    assert response.status_code == 403


def test_kanban_missing_job_id_returns_404(act_as):
    act_as(id=CUSTOMER_ID, role="customer")
    response = client.get(
        "/candidates/kanban",
        params={"job_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_kanban_admin_sees_candidates_from_every_job(act_as):
    job1 = _create_job(act_as, CUSTOMER_ID)
    client.post("/candidates", json={"job_id": job1, "name": "Alice"})

    job2 = _create_job(act_as, OTHER_CUSTOMER_ID)
    client.post("/candidates", json={"job_id": job2, "name": "Bob"})

    act_as(id=ADMIN_ID, role="admin")
    response = client.get("/candidates/kanban")

    assert response.status_code == 200
    board = response.json()
    assert {c["name"] for c in board["new"]} == {"Alice", "Bob"}


def test_kanban_combines_job_id_and_name_filter(act_as):
    job_id = _create_job(act_as, CUSTOMER_ID)
    client.post("/candidates", json={"job_id": job_id, "name": "Alice"})
    client.post("/candidates", json={"job_id": job_id, "name": "Bob"})

    response = client.get(
        "/candidates/kanban", params={"job_id": job_id, "name": "ali"}
    )

    assert response.status_code == 200
    board = response.json()
    assert [c["name"] for c in board["new"]] == ["Alice"]
