-- Candidates belong to a job; ownership therefore flows through
-- candidates.job_id -> jobs.customer_id, enforced in application code
-- (FastAPI), same rationale as jobs.sql.
create table public.candidates (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs(id) on delete cascade,
  name text not null,
  email text,
  linkedin_url text,
  cv_text text,
  stage text not null default 'new'
    check (stage in ('new', 'screening', 'interview', 'offer', 'hired', 'rejected')),
  ai_score int,
  ai_summary text,
  created_at timestamptz not null default now()
);

alter table public.candidates enable row level security;

-- No policies - see jobs.sql: all access goes through the backend.
