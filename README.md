# mini-ats-backend

Backend for a minimal ATS (applicant tracking system), built with FastAPI.
See `kickoff-prompt.md` for the full spec.

## Status

- Done: health check endpoint (deployed); JWT verification against
  Supabase's JWKS endpoint, exposed via a protected `GET /me`
- Next up: database schema, CRUD endpoints (jobs, candidates), kanban
  filtering, admin account creation, AI CV assessment

## Requirements

- Python 3.12
- A virtual environment in `.venv` (already set up in this repo)

## Local setup

```bash
source .venv/scripts/activate   # Windows Git Bash
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes `requirements.txt` plus test tooling
(pytest). Use `requirements.txt` alone for a production install.

## Running locally

```bash
uvicorn app.main:app --reload
```

- Health check: http://127.0.0.1:8000/health
- Authenticated identity check: http://127.0.0.1:8000/me (needs a
  `Authorization: Bearer <supabase-jwt>` header)
- Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

## Deploying

Set the start command explicitly on the deploy platform:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Auto-detection doesn't
find it, since the entrypoint lives in `app/main.py`, not the repo root.

## Environment variables

Copy `.env.example` to `.env` and fill in real values. `.env` is
gitignored and must never be committed.

| Variable | Required | Purpose |
|---|---|---|
| `APP_NAME` | no | Display name for the app |
| `ENVIRONMENT` | no | `development` / `production` |
| `SUPABASE_URL` | **yes** | Base URL of the Supabase project |
| `SUPABASE_JWKS_URL` | **yes** | JWKS endpoint used to verify JWTs; the app fails to start without it |
| `SUPABASE_SECRET_KEY` | from step 3+ | Server-side only; used for admin account creation and DB writes where FastAPI (not RLS) enforces authorization. Never logged or returned in a response. |

## Tests

```bash
python -m pytest -v
```

## Project structure

```
app/
├── main.py       # FastAPI app instance, wires up routers + health check
├── core/
│   └── config.py # Settings (env vars), single source of truth
├── auth/
│   └── jwt.py    # get_current_user dependency: verifies JWTs via Supabase JWKS
└── routers/
    └── me.py     # GET /me - protected identity check
tests/
supabase/         # Supabase CLI project (schemas, migrations, config)
```
