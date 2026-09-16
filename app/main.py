"""
FastAPI application entrypoint.

Creates the app instance, wires up routers, and exposes a health check
endpoint used to verify the deployment is alive before any real features
are built on top of it (see CLAUDE.md deploy cadence).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import admin, candidates, jobs, me, profile

app = FastAPI(title=settings.app_name)

# Without this, a browser refuses every request from the frontend's origin
# before it ever reaches FastAPI, no matter how valid the JWT is - CORS is
# enforced client-side by the browser, on top of (not instead of) our own
# JWT/authorization checks.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.cors_allowed_origins.split(",")
    ],
    allow_credentials=False,  # the JWT travels in Authorization, not cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    # X-Acting-As-Customer is easy to forget here since only admin requests
    # send it - omitting it wouldn't break the app, just silently break
    # "act as a customer" specifically, which is a lot harder to notice.
    allow_headers=["Authorization", "Content-Type", "X-Acting-As-Customer"],
)

app.include_router(me.router)
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(admin.router)
app.include_router(profile.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Report that the service is up.

    Used by the deploy platform (Railway/Render) and by us to confirm the
    live URL responds before wiring up JWT verification, the database, or
    any other feature that could fail silently.
    """
    return {"status": "ok"}
