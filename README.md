# mini-ats-backend

Backend for a minimal ATS (applicant tracking system), built with FastAPI.
See `kickoff-prompt.md` for the full spec.

## Status

- Done: health check endpoint (deployed); JWT verification against
  Supabase's JWKS endpoint, exposed via a protected `GET /me`; profiles,
  jobs and candidates table schemas with RLS, migrated to production;
  CRUD endpoints for jobs and candidates with role/ownership-based
  authorization; `name` filter on `GET /candidates` and a kanban board
  endpoint (`GET /candidates/kanban`) grouping candidates by stage; admin
  account creation (`POST /admin/accounts`, no self-signup - admins get a
  password set directly, customers set their own via an invite email) and
  "act as a customer" (`GET /admin/customers`, `X-Acting-As-Customer`
  header) with audit logging; extended profile fields (`GET`/`PATCH /profile`)
  and candidate `phone`/`notes` fields; AI CV assessment
  (`POST /candidates/{id}/assess`)
- Next up: Postman collection covering every endpoint, `/openapi.json` export

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
- Jobs / candidates CRUD: http://127.0.0.1:8000/jobs, http://127.0.0.1:8000/candidates
  (same bearer header; customers see/edit only their own, admins see everything -
  full request/response shapes are in `/docs`)
- Kanban board: http://127.0.0.1:8000/candidates/kanban - same ownership rules
  as `GET /candidates`, plus optional `job_id` and `name` (case-insensitive
  partial match) query filters; response is candidates grouped by stage
- Admin accounts: http://127.0.0.1:8000/admin/accounts (`POST`, admin-only) - the
  password flow differs by role: `role=admin` requires a `password` in the body
  and the account is active immediately (no email sent); `role=customer` must
  *omit* `password` (`400` if present) and is created via an invite email instead
  - the customer sets their own password by following its link. There is no
  self-signup anywhere in the API
- Customer list: http://127.0.0.1:8000/admin/customers (`GET`, admin-only) -
  fuels a future frontend's "act as a customer" picker
- Profile: http://127.0.0.1:8000/profile (`GET`/`PATCH`) - the effective
  customer's own profile (`website_url`, `linkedin_url`, `phone`,
  `contact_email`, `address`, `description`, plus `full_name`/`company_name`
  which are now editable here too). Scoped by the same effective-customer
  rules as jobs/candidates: a customer gets their own row, an admin gets
  `400` without `X-Acting-As-Customer` and the chosen customer's row with
  it. `GET /me` is unaffected - it stays a plain identity check
- AI CV assessment: `POST /candidates/{id}/assess` scores how well a
  candidate's `cv_text` matches their job's `description` (Anthropic
  Claude), saving `ai_score`, `ai_summary`, `ai_strengths`, `ai_gaps`
  together on success - never partially. `422` if the candidate has no
  `cv_text`; `502` (generic message, no provider detail) if the AI call
  times out, is rate-limited, or returns something unusable. Same
  ownership rules as the rest of `/candidates`
- Acting as a customer: any admin request to `/jobs` or `/candidates` accepts
  an `X-Acting-As-Customer: <customer-id>` header to scope the request to that
  customer instead of seeing everything; an unknown id or a non-customer id
  returns `404`. Every time the header actually resolves, a structured JSON
  audit line is written to stdout (`admin_id`, `acting_as_customer_id`,
  `endpoint`, `timestamp`)
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
| `SUPABASE_SECRET_KEY` | **yes** | Service-role key; used for every jobs/candidates database read and write (bypasses RLS, since FastAPI - not Postgres - enforces ownership) and for admin account creation via Supabase's Admin API. Never logged or returned in a response. |
| `ANTHROPIC_API_KEY` | **yes** | Used by `POST /candidates/{id}/assess` to call Claude for CV assessments. Never logged or returned in a response. |

## Tests

```bash
python -m pytest -v
```

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
│   └── ai_assessment.py # get_anthropic_client / assess_candidate - CV scoring
├── models/
│   ├── jobs.py       # JobCreate / JobUpdate / JobRead
│   ├── candidates.py # CandidateCreate / CandidateUpdate / CandidateRead / KanbanBoard
│   ├── admin.py      # AdminAccountCreate / AdminAccountRead / CustomerSummary
│   └── profile.py    # ProfileRead / ProfileUpdate
└── routers/
    ├── me.py          # GET /me - protected identity check
    ├── jobs.py        # jobs CRUD, scoped by get_effective_customer_id
    ├── candidates.py  # candidates CRUD + POST /{id}/assess, ownership via parent job
    ├── admin.py       # admin-only: account creation, customer list
    └── profile.py     # GET/PATCH /profile, scoped by get_effective_customer_id
tests/
supabase/         # Supabase CLI project (schemas, migrations, config)
```
