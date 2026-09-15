"""
Tests for GET/PATCH /profile, using the same fake in-memory Supabase client
and act_as fixture as the jobs/candidates tests.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import ADMIN_ID, CUSTOMER_ID

client = TestClient(app)


def test_customer_reads_own_profile(act_as):
    act_as(id=CUSTOMER_ID, role="customer")

    response = client.get("/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == CUSTOMER_ID
    assert body["role"] == "customer"


def test_customer_partially_updates_own_profile(act_as):
    """Only fields present in the request body change."""
    act_as(id=CUSTOMER_ID, role="customer")
    client.patch("/profile", json={"company_name": "Acme Inc", "phone": "+46701234567"})

    response = client.patch("/profile", json={"phone": "+46709999999"})

    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+46709999999"
    assert body["company_name"] == "Acme Inc"  # untouched by the second PATCH


def test_admin_without_header_gets_400_on_profile(act_as):
    act_as(id=ADMIN_ID, role="admin")

    get_response = client.get("/profile")
    patch_response = client.patch("/profile", json={"phone": "+46701234567"})

    assert get_response.status_code == 400
    assert patch_response.status_code == 400


def test_admin_with_valid_header_reads_and_updates_customers_profile(act_as):
    act_as(id=ADMIN_ID, role="admin")
    act_as(id=CUSTOMER_ID, role="customer")  # registers the customer profile
    act_as(id=ADMIN_ID, role="admin")  # switch back to the acting admin

    headers = {"X-Acting-As-Customer": CUSTOMER_ID}

    get_response = client.get("/profile", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == CUSTOMER_ID

    patch_response = client.patch(
        "/profile", json={"description": "A growing startup"}, headers=headers
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["description"] == "A growing startup"
    assert patch_response.json()["id"] == CUSTOMER_ID


def test_admin_with_unknown_header_gets_404_on_profile(act_as):
    act_as(id=ADMIN_ID, role="admin")
    headers = {"X-Acting-As-Customer": "00000000-0000-0000-0000-000000000099"}

    get_response = client.get("/profile", headers=headers)
    patch_response = client.patch("/profile", json={"phone": "x"}, headers=headers)

    assert get_response.status_code == 404
    assert patch_response.status_code == 404


def test_admin_with_another_admins_id_gets_404_on_profile(act_as):
    """The header must resolve to a customer specifically."""
    act_as(id=ADMIN_ID, role="admin")
    other_admin_id = "00000000-0000-0000-0000-00000000ad02"
    act_as(id=other_admin_id, role="admin")  # registers it as a real profile
    act_as(id=ADMIN_ID, role="admin")  # switch back to the acting admin

    response = client.get(
        "/profile", headers={"X-Acting-As-Customer": other_admin_id}
    )

    assert response.status_code == 404
