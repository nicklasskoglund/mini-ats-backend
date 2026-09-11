"""
FastAPI application entrypoint.

Creates the app instance, wires up routers, and exposes a health check
endpoint used to verify the deployment is alive before any real features
are built on top of it (see CLAUDE.md deploy cadence).
"""

from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Report that the service is up.

    Used by the deploy platform (Railway/Render) and by us to confirm the
    live URL responds before wiring up JWT verification, the database, or
    any other feature that could fail silently.
    """
    return {"status": "ok"}
