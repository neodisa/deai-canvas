-- Deai Canvas · module `supabase-comments` · schema of the shared comments table.
--
-- Run this ONCE in the SQL editor of YOUR Supabase project (Dashboard -> SQL Editor -> New query -> Run).
-- The module never changes the schema itself: that would need a service key, and it is deliberately not given one.
-- The script is idempotent: running it again is safe.
create table if not exists comments (
  -- Client-assigned globally-unique id (uuid string). Sequential ids collide
  -- across reviewers, so the browser layer generates a uuid; the DB never assigns one.
  id             text primary key,
  project_id     text not null,
  author         text not null,
  text           text not null,
  status         text not null default 'open',
  fp             jsonb not null,
  html_snapshot  jsonb,
  meta           jsonb,
  born_v         int,
  resolved_v     int,
  resolve_reason text,
  ts             text,
  created_at     timestamptz default now()
);

create index if not exists comments_project_idx on comments(project_id);

alter table comments enable row level security;

-- Least privilege for the public (anon / publishable) key. It ships inside every published page,
-- so it cannot be kept secret — bound what it can DO instead.
--
-- Do NOT restore the old single `for all using (true) with check (true)` policy named "anon rw":
-- with it, anyone holding a preview link can read, rewrite or wipe the comments of EVERY project
-- sharing the database.
drop policy if exists "anon rw" on comments;
drop policy if exists cl_read   on comments;
drop policy if exists cl_insert on comments;
drop policy if exists cl_update on comments;
drop policy if exists cl_delete on comments;
create policy cl_read   on comments for select using (true);
create policy cl_insert on comments for insert with check (true);
create policy cl_update on comments for update using (true) with check (true);
create policy cl_delete on comments for delete using (true);

-- Grants and RLS are separate layers: the TRUNCATE privilege ignores policies entirely.
revoke truncate, references, trigger on comments from anon, authenticated;

-- project_id is immutable, and one request cannot wipe more than one project's
-- comments (the browser layer deletes exactly one comment per request). `row_security_active()`
-- keeps both guards off service_role/owner, which bypass RLS anyway.
create or replace function cl_project_id_immutable() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
  if row_security_active('comments')
     and new.project_id is distinct from old.project_id then
    raise exception 'comments.project_id is immutable (% -> %)', old.project_id, new.project_id
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

drop trigger if exists cl_project_id_immutable on comments;
create trigger cl_project_id_immutable before update on comments
for each row execute function cl_project_id_immutable();

create or replace function cl_delete_scope_guard() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
declare n int; p int;
begin
  if not row_security_active('comments') then
    return null;
  end if;
  select count(*), count(distinct project_id) into n, p from removed;
  if p > 1 then
    raise exception 'a delete must stay within one project_id (got %)', p
      using errcode = 'check_violation';
  end if;
  if n > 25 then
    raise exception 'at most 25 comments may be deleted per request (got %)', n
      using errcode = 'check_violation';
  end if;
  return null;
end $$;

drop trigger if exists cl_delete_scope_guard on comments;
create trigger cl_delete_scope_guard after delete on comments
referencing old table as removed
for each statement execute function cl_delete_scope_guard();

-- Still open by design: reading and writing OTHER projects' comments. Real isolation needs a
-- signed per-project token (a project_id claim checked in the policy), not a shared public key.
-- Deliberate trade-off: use a DEDICATED Supabase project per team, and treat everyone who holds
-- the public key (it is in every published page) as able to read and write its comments.

-- Realtime for live multi-reviewer updates (no error when the table is already published).
do $$
begin
  alter publication supabase_realtime add table comments;
exception when duplicate_object then
  null;
end $$;
