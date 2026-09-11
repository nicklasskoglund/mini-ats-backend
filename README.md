# mini-ats-backend

Backend for a minimal ATS (applicant tracking system), built with FastAPI.
See `kickoff-prompt.md` for the full spec.

## Status

- Done: health check endpoint, deployed
- Next up: JWT verification against Supabase, CRUD endpoints (jobs,
  candidates), kanban filtering, admin account creation, AI CV assessment

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
- Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

## Environment variables

Copy `.env.example` to `.env` and fill in real values. `.env` is
gitignored and must never be committed.

| Variable | Required from | Purpose |
|---|---|---|
| `APP_NAME` | step 1 | Display name for the app |
| `ENVIRONMENT` | step 1 | `development` / `production` |
| `SUPABASE_URL` | step 2 | Base URL of the Supabase project |
| `SUPABASE_JWKS_URL` | step 2 | JWKS endpoint used to verify JWTs |
| `SUPABASE_SECRET_KEY` | step 3+ | Server-side only; used for admin account creation and DB writes where FastAPI (not RLS) enforces authorization. Never logged or returned in a response. |

## Tests

```bash
python -m pytest -v
```

## Project structure

```
app/
├── main.py       # FastAPI app instance + health check
└── core/
    └── config.py # Settings (env vars), single source of truth
tests/
supabase/         # Supabase CLI project (schemas, migrations, config)
```
