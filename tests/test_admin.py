"""
Tests for the /admin/* endpoints (account creation and the customer list),
using the fake Supabase client's .auth.admin stand-in (conftest.py) instead
of a real Supabase Auth Admin API.

Account creation has two distinct flows by role: role="admin" requires a
password (create_user, active immediately); role="customer" forbids one
(invite_user_by_email, customer sets their own via the invite email).
"""

from fastapi.testclient import TestClient

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
