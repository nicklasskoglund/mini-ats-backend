"""
Tests for POST /candidates/{id}/assess.

The Anthropic API is never called for real here - `mock_ai_assessment`
(conftest.py) swaps in a fake client via app.dependency_overrides on
get_anthropic_client, configured per test with either a canned JSON
response or an exception to simulate a failed call.
"""

import json

import anthropic
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import CUSTOMER_ID, OTHER_CUSTOMER_ID

client = TestClient(app)

VALID_PAYLOAD = {
    "score": 8,
    "strengths": ["Strong Python background", "Clear communicator", "Relevant industry experience"],
    "gaps": ["No cloud certifications", "Limited leadership experience"],
    "summary": "Solid match for the role with minor gaps in cloud experience.",
}


def _create_candidate_with_cv(act_as, owner_id: str, cv_text: str | None = "Experienced backend engineer.") -> dict:
    """Act as `owner_id`, create a job and a candidate on it (optionally
    without cv_text), returning the created candidate. Leaves the client
    acting as that owner afterwards."""
    act_as(id=owner_id, role="customer")
    job_id = client.post(
        "/jobs", json={"title": "Backend engineer", "description": "Needs Python and AWS."}
    ).json()["id"]
    payload = {"job_id": job_id, "name": "Alice"}
    if cv_text is not None:
        payload["cv_text"] = cv_text
    return client.post("/candidates", json=payload).json()


def test_successful_assessment_saves_all_four_fields_together(act_as, mock_ai_assessment):
    candidate = _create_candidate_with_cv(act_as, CUSTOMER_ID)
    mock_ai_assessment(payload=VALID_PAYLOAD)

    response = client.post(f"/candidates/{candidate['id']}/assess")

    assert response.status_code == 200
    body = response.json()
    assert body["ai_score"] == 8
    assert body["ai_strengths"] == VALID_PAYLOAD["strengths"]
    assert body["ai_gaps"] == VALID_PAYLOAD["gaps"]
    assert body["ai_summary"] == VALID_PAYLOAD["summary"]


def test_anthropic_failure_returns_502_without_partial_save(act_as, mock_ai_assessment):
    candidate = _create_candidate_with_cv(act_as, CUSTOMER_ID)
    mock_ai_assessment(error=anthropic.AnthropicError("simulated timeout"))

    response = client.post(f"/candidates/{candidate['id']}/assess")
    assert response.status_code == 502
    # Generic message only - no provider-specific detail leaked.
    assert "anthropic" not in response.json()["detail"].lower()
    assert "timeout" not in response.json()["detail"].lower()

    # Nothing was saved - a failed assessment can't leave partial data.
    refetched = client.get(f"/candidates/{candidate['id']}").json()
    assert refetched["ai_score"] is None
    assert refetched["ai_summary"] is None
    assert refetched["ai_strengths"] is None
    assert refetched["ai_gaps"] is None


def test_response_wrapped_in_markdown_code_fence_is_parsed(act_as, mock_ai_assessment):
    """Regression test: Haiku sometimes wraps its JSON answer in a
    ```json ... ``` fence despite the system prompt saying not to - this
    used to crash json.loads. A plain `payload` mock (clean JSON) doesn't
    exercise this path, hence the explicit `text` override here."""
    candidate = _create_candidate_with_cv(act_as, CUSTOMER_ID)
    fenced_text = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
    mock_ai_assessment(text=fenced_text)

    response = client.post(f"/candidates/{candidate['id']}/assess")

    assert response.status_code == 200
    assert response.json()["ai_score"] == 8


def test_malformed_ai_response_returns_502(act_as, mock_ai_assessment):
    """A response that isn't valid JSON matching the expected schema is
    treated the same as a network failure - 502, nothing saved."""
    candidate = _create_candidate_with_cv(act_as, CUSTOMER_ID)
    mock_ai_assessment(payload={"score": 5})  # missing strengths/gaps/summary

    response = client.post(f"/candidates/{candidate['id']}/assess")

    assert response.status_code == 502


def test_missing_cv_text_returns_422(act_as, mock_ai_assessment):
    candidate = _create_candidate_with_cv(act_as, CUSTOMER_ID, cv_text=None)
    mock_ai_assessment(payload=VALID_PAYLOAD)

    response = client.post(f"/candidates/{candidate['id']}/assess")

    assert response.status_code == 422


def test_non_owner_cannot_assess_others_candidate(act_as, mock_ai_assessment):
    candidate = _create_candidate_with_cv(act_as, CUSTOMER_ID)
    mock_ai_assessment(payload=VALID_PAYLOAD)

    act_as(id=OTHER_CUSTOMER_ID, role="customer")
    response = client.post(f"/candidates/{candidate['id']}/assess")

    assert response.status_code == 403
