"""
Regression test for CORS: without CORSMiddleware configured, a browser
refuses every cross-origin request before it reaches FastAPI at all,
regardless of how valid the JWT is - this can't be caught by any of the
other tests, which all go straight through TestClient without a browser's
preflight step in between.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_preflight_allows_configured_origin_and_acting_as_header():
    """A CORS preflight (OPTIONS) for a real cross-origin request must come
    back allowing the configured frontend origin, the methods the API
    actually uses, and - easy to forget, since only admin requests send it
    - the X-Acting-As-Customer header."""
    response = client.options(
        "/jobs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-acting-as-customer",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert (
        "x-acting-as-customer"
        in response.headers["access-control-allow-headers"].lower()
    )


def test_preflight_rejects_unconfigured_origin():
    """An origin that isn't in CORS_ALLOWED_ORIGINS must not be echoed back
    as allowed - otherwise the allow-list isn't doing anything."""
    response = client.options(
        "/jobs",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
