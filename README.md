# mini-ats-backend

Backend API for a lightweight applicant tracking system (ATS): customers post jobs,
track candidates through a kanban-style pipeline, and get AI-assisted help screening
CVs against a job description. Admins manage accounts and can act on behalf of a
specific customer (e.g. for support or onboarding) without impersonation.

## Tech stack

- **API:** FastAPI (Python 3.12), Pydantic v2, type hints throughout
- **Database & auth:** Supabase (Postgres + Auth) - schema managed declaratively via
  the Supabase CLI
- **AI:** Anthropic Claude, for CV-to-job-description scoring
- **Deployment:** Railway

## Architecture

- The frontend authenticates directly against Supabase Auth and sends the resulting
  JWT as `Authorization: Bearer <token>` on every request.
- This service verifies that JWT against Supabase's JWKS endpoint on every protected
  request - it never trusts a role or user id merely because a client claims it.
- Authorization is role-based (`admin` / `customer`), looked up from a `profiles`
  table populated automatically when an account is created. Customers only ever
  see/edit their own jobs and candidates; admins can see everything, or scope a
  request to one specific customer via an `X-Acting-As-Customer` header. Every use
  of that header is logged.
- Row Level Security is enabled on every table as a defense-in-depth layer, but the
  actual authorization decisions are made and tested in the API layer, not left to
  the database alone.
- There is no self-service sign-up: accounts are created by an admin.

## Local setup

Requirements: Python 3.12, the [Supabase CLI](https://supabase.com/docs/guides/cli),
and Docker (for running Supabase locally).

```bash
python -m venv .venv
source .venv/scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes `requirements.txt` plus test tooling (pytest, ruff).
Use `requirements.txt` alone for a production install.

Copy `.env.example` to `.env` and fill in real values (never commit `.env` - it's
gitignored):

| Variable | Required | Purpose |
|---|---|---|
| `APP_NAME` | no | Display name for the app |
| `ENVIRONMENT` | no | `development` / `production` |
| `SUPABASE_URL` | **yes** | Base URL of the Supabase project |
| `SUPABASE_JWKS_URL` | **yes** | JWKS endpoint used to verify JWTs; the app fails to start without it |
| `SUPABASE_SECRET_KEY` | **yes** | Service-role key; used for every database read/write and for admin account management via Supabase's Admin API. Never logged or returned in a response. |
| `ANTHROPIC_API_KEY` | **yes** | Used for AI-assisted CV assessment. Never logged or returned in a response. |
| `CORS_ALLOWED_ORIGINS` | no | Comma-separated list of browser origins allowed to call this API. Defaults to Vite's local dev server; set to the real frontend origin(s) on every other deployment. |

### Database

Schema lives declaratively in `supabase/schemas/*.sql`; migrations are generated
from it, not written by hand. To work with the database locally:

```bash
supabase link                              # connect the CLI to your Supabase project
supabase start                             # run Postgres + Auth locally in Docker
supabase db schema declarative sync --name <change_name> --no-apply   # generate a migration from a schema change
supabase migration up                      # apply pending migrations locally
```

Migrations are applied to production automatically by Supabase's GitHub integration
on merge to `main`.

## Running locally

```bash
uvicorn app.main:app --reload
```

- Health check: http://127.0.0.1:8000/health
- Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

The endpoints, request/response shapes, and auth requirements are all defined in the
OpenAPI schema above - that's the authoritative reference. At a glance, the API
covers:

- **Jobs & candidates** - CRUD, ownership-scoped, plus a kanban view of candidates
  grouped by stage with name/job filters
- **CV assessment** - scores a candidate's CV against their job's description and
  saves a score, a summary, and structured strengths/gaps
- **Accounts** - admin-only creation, listing, and deletion, including acting on
  behalf of a specific customer
- **Profile** - read/update the effective customer's own profile

## Deploying

Set the start command explicitly on the deploy platform:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT` (auto-detection doesn't find it,
since the entrypoint lives in `app/main.py`, not the repo root). Set all required
environment variables above on the platform before deploying.

## Tests

```bash
python -m pytest -v
```

Tests run against a fake in-memory Supabase/Auth client - no real database or
external API calls are made.

## Project structure

```
app/
├── main.py          # FastAPI app instance, wires up routers + health check
├── core/
│   └── config.py    # Settings (env vars), single source of truth
├── auth/
│   ├── jwt.py                # get_current_user: verifies JWTs via Supabase JWKS
│   ├── profile.py            # get_current_profile / require_admin
│   └── effective_customer.py # get_effective_customer_id: role + acting-as + audit log
├── db/
│   ├── client.py    # get_supabase: cached client, service-role key
│   └── errors.py    # translates Postgres constraint violations to 422
├── services/
│   └── ai_assessment.py # Anthropic client + CV scoring
├── models/
│   ├── jobs.py       # JobCreate / JobUpdate / JobRead
│   ├── candidates.py # CandidateCreate / CandidateUpdate / CandidateRead / KanbanBoard
│   ├── admin.py      # AdminAccountCreate / AdminAccountRead / CustomerSummary
│   └── profile.py    # ProfileRead / ProfileUpdate
└── routers/
    ├── me.py          # GET /me - identity check
    ├── jobs.py        # jobs CRUD
    ├── candidates.py  # candidates CRUD + AI assessment
    ├── admin.py       # account management
    └── profile.py     # profile read/update
tests/
supabase/         # Supabase CLI project (schemas, migrations, config)
```
