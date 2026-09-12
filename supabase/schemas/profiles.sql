-- Extends auth.users with app-specific role and display data.
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  role text not null default 'customer' check (role in ('admin', 'customer')),
  full_name text,
  company_name text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Every user can read their own profile.
create policy "Users can view own profile"
  on public.profiles for select
  to authenticated
  using (auth.uid() = id);

-- security definer avoids re-triggering RLS recursively when checking role.
create function public.is_admin()
  returns boolean
  language sql
  security definer
  set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'admin'
  );
$$;

create policy "Admins can view all profiles"
  on public.profiles for select
  to authenticated
  using (public.is_admin());

-- Auto-creates a profile row whenever admin creates a new auth user,
-- reading role/full_name/company_name from user_metadata passed at creation.
create function public.handle_new_user()
  returns trigger
  language plpgsql
  security definer
  set search_path = public
as $$
begin
  insert into public.profiles (id, role, full_name, company_name)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'role', 'customer'),
    new.raw_user_meta_data->>'full_name',
    new.raw_user_meta_data->>'company_name'
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
