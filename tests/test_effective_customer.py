"""
Tests for get_effective_customer_id (app/auth/effective_customer.py), the
single dependency jobs/candidates authorization delegates to for "which
customer does this request act on behalf of".

The role/header branching itself is already exercised end-to-end through
the jobs endpoints (see test_jobs.py); this file focuses on what those
tests can't easily cover from the outside: that the audit log line is
written exactly when the header actually resolves to a customer, and not
otherwise.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import ADMIN_ID, CUSTOMER_ID

client = TestClient(app)


def test_audit_log_written_when_admin_acts_as_customer(act_as, monkeypatch):
    """The audit log fires on the one path that matters: admin + a header
    that resolves to a real customer."""
    calls = []
    monkeypatch.setattr(
        "app.auth.effective_customer.log_acting_as",
        lambda **kwargs: calls.append(kwargs),
    )

    act_as(id=ADMIN_ID, role="admin")
    act_as(id=CUSTOMER_ID, role="customer")  # registers the customer profile
    act_as(id=ADMIN_ID, role="admin")  # switch back to the acting admin

    response = client.get(
        "/jobs", headers={"X-Acting-As-Customer": CUSTOMER_ID}
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["admin_id"] == ADMIN_ID
    assert calls[0]["acting_as_customer_id"] == CUSTOMER_ID
    assert calls[0]["endpoint"] == "/jobs"


def test_audit_log_not_written_for_plain_admin(act_as, monkeypatch):
    """No header, no acting-as, nothing to log."""
    calls = []
    monkeypatch.setattr(
        "app.auth.effective_customer.log_acting_as",
        lambda **kwargs: calls.append(kwargs),
    )

    act_as(id=ADMIN_ID, role="admin")
    response = client.get("/jobs")

    assert response.status_code == 200
    assert calls == []


def test_audit_log_not_written_for_customer(act_as, monkeypatch):
    """A customer's own requests never count as "acting as", even if they
    somehow sent the header (it's ignored - see test_jobs.py)."""
    calls = []
    monkeypatch.setattr(
        "app.auth.effective_customer.log_acting_as",
        lambda **kwargs: calls.append(kwargs),
    )

    act_as(id=CUSTOMER_ID, role="customer")
    response = client.get(
        "/jobs", headers={"X-Acting-As-Customer": CUSTOMER_ID}
    )

    assert response.status_code == 200
    assert calls == []


def test_audit_log_not_written_when_header_is_invalid(act_as, monkeypatch):
    """A header that fails to resolve (404) must not be logged as a
    successful acting-as - nothing was actually resolved."""
    calls = []
    monkeypatch.setattr(
        "app.auth.effective_customer.log_acting_as",
        lambda **kwargs: calls.append(kwargs),
    )

    act_as(id=ADMIN_ID, role="admin")
    response = client.get(
        "/jobs",
        headers={"X-Acting-As-Customer": "00000000-0000-0000-0000-000000000099"},
    )

    assert response.status_code == 404
    assert calls == []
