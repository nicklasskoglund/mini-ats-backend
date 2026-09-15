"""
Tests for the /admin/* endpoints (account creation and the customer list),
using the fake Supabase client's .auth.admin stand-in (conftest.py) instead
of a real Supabase Auth Admin API.

Account creation has two distinct flows by role: role="admin" requires a
password (create_user, active immediately); role="customer" forbids one
(invite_user_by_email, customer sets their own via the invite email).
"""

from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError

from app.main import app
from tests.conftest import ADMIN_ID, CUSTOMER_ID

client = TestClient(app)


def test_admin_creates_admin_account(act_as):
    act_as(id=ADMIN_ID, role="admin")

    response = client.post(
        "/admin/accounts",
        json={
            "email": "new-admin@example.com",
            "password": "supersecret123",
            "role": "admin",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new-admin@example.com"
    assert body["role"] == "admin"
    assert "password" not in body


def test_admin_invites_customer_account(act_as):
    """Happy path for role=customer: no password in the request, the
    account is created via invite_user_by_email instead of create_user."""
    act_as(id=ADMIN_ID, role="admin")

    response = client.post(
        "/admin/accounts",
        json={
            "email": "new-customer@example.com",
            "role": "customer",
            "full_name": "Jane Doe",
            "company_name": "Acme Inc",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new-customer@example.com"
    assert body["role"] == "customer"
    assert body["company_name"] == "Acme Inc"


def test_customer_role_with_password_returns_400(act_as):
    """An admin never sets a customer's password - if the body includes
    one anyway, that must be rejected outright, not silently ignored (a
    silently ignored password would look like it was used when it wasn't)."""
    act_as(id=ADMIN_ID, role="admin")

    response = client.post(
        "/admin/accounts",
        json={
            "email": "new-customer@example.com",
            "password": "supersecret123",
            "role": "customer",
            "company_name": "Acme Inc",
        },
    )

    assert response.status_code == 400


def test_customer_role_without_company_name_returns_400(act_as):
    act_as(id=ADMIN_ID, role="admin")

    response = client.post(
        "/admin/accounts",
        json={"email": "new-customer@example.com", "role": "customer"},
    )

    assert response.status_code == 400


def test_admin_role_without_password_returns_400(act_as):
    act_as(id=ADMIN_ID, role="admin")

    response = client.post(
        "/admin/accounts",
        json={"email": "new-admin@example.com", "role": "admin"},
    )

    assert response.status_code == 400


def test_admin_password_too_short_returns_422(act_as):
    act_as(id=ADMIN_ID, role="admin")

    response = client.post(
        "/admin/accounts",
        json={
            "email": "new-admin@example.com",
            "password": "short",
            "role": "admin",
        },
    )

    assert response.status_code == 422


def test_non_admin_cannot_create_accounts(act_as):
    act_as(id=CUSTOMER_ID, role="customer")

    response = client.post(
        "/admin/accounts",
        json={
            "email": "new-customer@example.com",
            "role": "customer",
            "company_name": "Acme Inc",
        },
    )

    assert response.status_code == 403


def test_duplicate_admin_email_returns_409(act_as):
    act_as(id=ADMIN_ID, role="admin")
    payload = {
        "email": "existing-admin@example.com",
        "password": "supersecret123",
        "role": "admin",
    }

    first = client.post("/admin/accounts", json=payload)
    assert first.status_code == 201

    second = client.post("/admin/accounts", json=payload)
    assert second.status_code == 409


def test_duplicate_customer_email_returns_409(act_as):
    act_as(id=ADMIN_ID, role="admin")
    payload = {
        "email": "existing-customer@example.com",
        "role": "customer",
        "company_name": "Acme Inc",
    }

    first = client.post("/admin/accounts", json=payload)
    assert first.status_code == 201

    second = client.post("/admin/accounts", json=payload)
    assert second.status_code == 409


def test_invalid_email_from_supabase_returns_502(act_as, fake_db):
    """Regression test: a non-email_exists AuthApiError (confirmed in
    production for an invalid email domain, and separately for Supabase's
    email rate limit) used to bubble up as an unhandled 500. Supabase's
    own message is included in the 502 detail - this endpoint is
    admin-only, so that's useful operational feedback, not a leak to an
    untrusted caller."""
    act_as(id=ADMIN_ID, role="admin")
    fake_db.auth.admin.next_error = AuthApiError(
        'Email address "nope@example.com" is invalid', 422, "email_address_invalid"
    )

    response = client.post(
        "/admin/accounts",
        json={
            "email": "nope@example.com",
            "role": "customer",
            "company_name": "Acme Inc",
        },
    )

    assert response.status_code == 502
    assert "is invalid" in response.json()["detail"]


def test_rate_limit_from_supabase_returns_502(act_as, fake_db):
    """Same broad handling, exercised via the admin (create_user) path
    rather than the customer (invite_user_by_email) path, since both
    calls share the same error translation."""
    act_as(id=ADMIN_ID, role="admin")
    fake_db.auth.admin.next_error = AuthApiError(
        "email rate limit exceeded", 429, "over_email_send_rate_limit"
    )

    response = client.post(
        "/admin/accounts",
        json={
            "email": "new-admin@example.com",
            "password": "supersecret123",
            "role": "admin",
        },
    )

    assert response.status_code == 502
    assert "rate limit" in response.json()["detail"]


def test_acting_as_newly_invited_customer_works_before_confirmation(act_as):
    """The handle_new_user trigger creates the profiles row when the
    customer is invited, not when they confirm - verified against a real
    local Supabase project. So "act as this customer" must already work
    immediately after POST /admin/accounts, with no confirmation step
    simulated here at all."""
    act_as(id=ADMIN_ID, role="admin")

    created = client.post(
        "/admin/accounts",
        json={
            "email": "brand-new-customer@example.com",
            "role": "customer",
            "company_name": "Acme Inc",
        },
    )
    assert created.status_code == 201
    new_customer_id = created.json()["id"]

    response = client.post(
        "/jobs",
        json={"title": "x"},
        headers={"X-Acting-As-Customer": new_customer_id},
    )

    assert response.status_code == 201
    assert response.json()["customer_id"] == new_customer_id


def test_list_customers_returns_email_and_profile_fields(act_as):
    act_as(id=ADMIN_ID, role="admin")
    client.post(
        "/admin/accounts",
        json={
            "email": "customer-a@example.com",
            "role": "customer",
            "full_name": "Customer A",
            "company_name": "Acme Inc",
        },
    )
    client.post(
        "/admin/accounts",
        json={
            "email": "admin-b@example.com",
            "password": "supersecret123",
            "role": "admin",
        },
    )

    response = client.get("/admin/customers")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["email"] == "customer-a@example.com"
    assert body[0]["company_name"] == "Acme Inc"


def test_non_admin_cannot_list_customers(act_as):
    act_as(id=CUSTOMER_ID, role="customer")
    response = client.get("/admin/customers")
    assert response.status_code == 403


def test_admin_deletes_customer_account_cascades_jobs_and_candidates(act_as):
    """The explicit cascade (candidates -> jobs -> account) removes
    everything, not just the account row."""
    act_as(id=ADMIN_ID, role="admin")
    customer_id = client.post(
        "/admin/accounts",
        json={
            "email": "to-delete@example.com",
            "role": "customer",
            "company_name": "Acme Inc",
        },
    ).json()["id"]

    job_id = client.post(
        "/jobs", json={"title": "x"}, headers={"X-Acting-As-Customer": customer_id}
    ).json()["id"]
    client.post(
        "/candidates",
        json={"job_id": job_id, "name": "Alice"},
        headers={"X-Acting-As-Customer": customer_id},
    )

    response = client.delete(f"/admin/accounts/{customer_id}")
    assert response.status_code == 204

    # Account gone.
    remaining_customers = client.get("/admin/customers").json()
    assert customer_id not in [c["id"] for c in remaining_customers]

    # Acting as that (now nonexistent) customer fails - no profile left.
    acting_as_response = client.get(
        "/jobs", headers={"X-Acting-As-Customer": customer_id}
    )
    assert acting_as_response.status_code == 404

    # Their job is gone too, not just orphaned.
    all_jobs = client.get("/jobs").json()
    assert job_id not in [j["id"] for j in all_jobs]


def test_admin_deletes_admin_account(act_as):
    """An admin account has no jobs/candidates to cascade - just deleted."""
    act_as(id=ADMIN_ID, role="admin")
    other_admin_id = client.post(
        "/admin/accounts",
        json={
            "email": "admin-to-delete@example.com",
            "password": "supersecret123",
            "role": "admin",
        },
    ).json()["id"]

    response = client.delete(f"/admin/accounts/{other_admin_id}")

    assert response.status_code == 204


def test_non_admin_cannot_delete_account(act_as):
    act_as(id=ADMIN_ID, role="admin")
    target_id = client.post(
        "/admin/accounts",
        json={
            "email": "target@example.com",
            "role": "customer",
            "company_name": "Acme Inc",
        },
    ).json()["id"]

    act_as(id=CUSTOMER_ID, role="customer")
    response = client.delete(f"/admin/accounts/{target_id}")

    assert response.status_code == 403


def test_deleting_unknown_account_returns_404(act_as):
    act_as(id=ADMIN_ID, role="admin")
    response = client.delete(
        "/admin/accounts/00000000-0000-0000-0000-000000000099"
    )
    assert response.status_code == 404
