"""
Tests for the /admin/* endpoints (account creation and the customer list),
using the fake Supabase client's .auth.admin stand-in (conftest.py) instead
of a real Supabase Auth Admin API.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import ADMIN_ID, CUSTOMER_ID

client = TestClient(app)


def test_admin_creates_customer_account(act_as):
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


def test_admin_creates_admin_account_without_company_name(act_as):
    """company_name is only required for role=customer."""
    act_as(id=ADMIN_ID, role="admin")

    response = client.post(
        "/admin/accounts",
        json={"email": "new-admin@example.com", "role": "admin"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "admin"


def test_customer_role_without_company_name_returns_400(act_as):
    act_as(id=ADMIN_ID, role="admin")

    response = client.post(
        "/admin/accounts",
        json={"email": "new-customer@example.com", "role": "customer"},
    )

    assert response.status_code == 400


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


def test_duplicate_email_returns_409(act_as):
    act_as(id=ADMIN_ID, role="admin")
    payload = {
        "email": "existing@example.com",
        "role": "customer",
        "company_name": "Acme Inc",
    }

    first = client.post("/admin/accounts", json=payload)
    assert first.status_code == 201

    second = client.post("/admin/accounts", json=payload)
    assert second.status_code == 409


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
        json={"email": "admin-b@example.com", "role": "admin"},
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
