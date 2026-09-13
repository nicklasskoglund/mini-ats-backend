-- Jobs posted by a customer. Ownership (who may see/edit a job) is
-- enforced in application code (FastAPI), not via RLS policies here -
-- see CLAUDE.md's Security section for the rationale.
create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references public.profiles(id) on delete cascade,
  title text not null,
  description text,
  status text not null default 'open',
  created_at timestamptz not null default now()
);

alter table public.jobs enable row level security;

-- No policies: every request goes through the backend, which uses the
-- Supabase secret key (bypasses RLS) and enforces ownership itself. RLS
-- being enabled with zero policies means anon/authenticated keys get zero
-- access by default if Supabase's auto-generated PostgREST API is ever
-- reached directly.
