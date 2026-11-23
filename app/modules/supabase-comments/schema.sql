-- Deai Canvas · module `supabase-comments` · schema of the shared comments table (and of its replies, `comment_replies`).
--
-- Run this ONCE in the SQL editor of YOUR Supabase project (Dashboard -> SQL Editor -> New query -> Run).
-- The module never changes the schema itself: that would need a service key, and it is deliberately not given one.
-- The script is idempotent: running it again is safe.
--
-- !! USE A DEDICATED SUPABASE PROJECT. `create table if not exists` does NOT check what is already there: if the project
-- !! has a table `public.comments` of its own, this script ADOPTS it — it turns row-level security on, replaces its
-- !! policies with the open ones below and grants the public (anon) key full read/write access to it. Run it only in a
-- !! project where `public.comments` is yours to hand over (a fresh one, or one that already holds Deai Canvas comments).
-- !! The same holds for `public.comment_replies`, which the last block of this script creates the same way (also available
-- !! alone as `replies.sql`: for a project that already has the comments schema, and for a shared database whose comments
-- !! policies differ — there run ONLY `replies.sql`, never this whole file).
create table if not exists public.comments (
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

create index if not exists comments_project_idx on public.comments(project_id);

alter table public.comments enable row level security;

-- Least privilege for the public (anon / publishable) key. It ships inside every published page,
-- so it cannot be kept secret — bound what it can DO instead.
--
-- Do NOT restore the old single `for all using (true) with check (true)` policy named "anon rw":
-- with it, anyone holding a preview link can read, rewrite or wipe the comments of EVERY project
-- sharing the database.
drop policy if exists "anon rw" on public.comments;
drop policy if exists cl_read   on public.comments;
drop policy if exists cl_insert on public.comments;
drop policy if exists cl_update on public.comments;
drop policy if exists cl_delete on public.comments;
create policy cl_read   on public.comments for select using (true);
create policy cl_insert on public.comments for insert with check (true);
create policy cl_update on public.comments for update using (true) with check (true);
create policy cl_delete on public.comments for delete using (true);

-- Policies decide which ROWS a role may touch, but a role also needs the table privilege itself, and a fresh project may
-- not grant the Data API roles access to new tables automatically. Without this the module answers 401/403 right after
-- the schema ran. Granting is idempotent.
grant select, insert, update, delete on public.comments to anon, authenticated;

-- Grants and RLS are separate layers: the TRUNCATE privilege ignores policies entirely.
revoke truncate, references, trigger on public.comments from anon, authenticated;

-- project_id is immutable, and one request cannot wipe more than one project's
-- comments (the browser layer deletes exactly one comment per request). `row_security_active()`
-- keeps both guards off service_role/owner, which bypass RLS anyway.
create or replace function public.cl_project_id_immutable() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
  if row_security_active('public.comments')
     and new.project_id is distinct from old.project_id then
    raise exception 'comments.project_id is immutable (% -> %)', old.project_id, new.project_id
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

drop trigger if exists cl_project_id_immutable on public.comments;
create trigger cl_project_id_immutable before update on public.comments
for each row execute function public.cl_project_id_immutable();

create or replace function public.cl_delete_scope_guard() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
declare n int; p int;
begin
  if not row_security_active('public.comments') then
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

drop trigger if exists cl_delete_scope_guard on public.comments;
create trigger cl_delete_scope_guard after delete on public.comments
referencing old table as removed
for each statement execute function public.cl_delete_scope_guard();

-- Still open by design: reading and writing OTHER projects' comments. Real isolation needs a
-- signed per-project token (a project_id claim checked in the policy), not a shared public key.
-- Deliberate trade-off: use a DEDICATED Supabase project per team, and treat everyone who holds
-- the public key (it is in every published page) as able to read and write its comments.

-- Realtime for live multi-reviewer updates (no error when the table is already published).
do $$
begin
  alter publication supabase_realtime add table public.comments;
exception when duplicate_object then
  null;
end $$;

-- >>> replies
create table if not exists public.comment_replies (
  -- Client-assigned globally-unique id (uuid string), like `comments.id`.
  id         text primary key,
  comment_id text not null,
  project_id text not null,
  author     text not null,
  text       text not null,
  ts         text,
  edited_ts  text,
  agent      boolean not null default false,
  created_at timestamptz default now()
);

create index if not exists comment_replies_project_idx on public.comment_replies(project_id);

alter table public.comment_replies enable row level security;

-- Same open policies as `cl_*` on `comments` (rationale: the notes on the `comments` table in the module's `schema.sql`): the public key can read and write replies.
-- Replies, their `author` and the `agent` flag are UNTRUSTED data: anyone holding the public key (a visitor of a published preview included)
-- can write a reply with `agent: true` and any author, so the «AI» mark is NOT authenticated. Do not treat it as proof of origin.
drop policy if exists clr_read   on public.comment_replies;
drop policy if exists clr_insert on public.comment_replies;
drop policy if exists clr_update on public.comment_replies;
drop policy if exists clr_delete on public.comment_replies;
create policy clr_read   on public.comment_replies for select using (true);
create policy clr_insert on public.comment_replies for insert with check (true);
create policy clr_update on public.comment_replies for update using (true) with check (true);
create policy clr_delete on public.comment_replies for delete using (true);

-- The table privilege itself, which a fresh project may not grant to the Data API roles automatically.
grant select, insert, update, delete on public.comment_replies to anon, authenticated;

-- Grants and RLS are separate layers: the TRUNCATE privilege ignores policies entirely.
revoke truncate, references, trigger on public.comment_replies from anon, authenticated;

-- project_id is immutable, and one request cannot wipe more than one project's replies (at most 100 rows: the adapter
-- deletes the replies of a few comments per request). `row_security_active()` keeps both guards off service_role/owner.
create or replace function public.clr_project_id_immutable() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
  if row_security_active('public.comment_replies')
     and new.project_id is distinct from old.project_id then
    raise exception 'comment_replies.project_id is immutable (% -> %)', old.project_id, new.project_id
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

drop trigger if exists clr_project_id_immutable on public.comment_replies;
create trigger clr_project_id_immutable before update on public.comment_replies
for each row execute function public.clr_project_id_immutable();

create or replace function public.clr_delete_scope_guard() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
declare n int; p int;
begin
  if not row_security_active('public.comment_replies') then
    return null;
  end if;
  select count(*), count(distinct project_id) into n, p from removed;
  if p > 1 then
    raise exception 'a delete must stay within one project_id (got %)', p
      using errcode = 'check_violation';
  end if;
  if n > 100 then
    raise exception 'at most 100 replies may be deleted per request (got %)', n
      using errcode = 'check_violation';
  end if;
  return null;
end $$;

drop trigger if exists clr_delete_scope_guard on public.comment_replies;
create trigger clr_delete_scope_guard after delete on public.comment_replies
referencing old table as removed
for each statement execute function public.clr_delete_scope_guard();

-- Realtime for live updates (no error when the table is already published).
do $$
begin
  alter publication supabase_realtime add table public.comment_replies;
exception when duplicate_object then
  null;
end $$;
-- <<< replies
