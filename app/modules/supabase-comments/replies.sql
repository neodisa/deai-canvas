-- Deai Canvas · module `supabase-comments` · table of comment REPLIES (`public.comment_replies`).
--
-- Run this ONCE in the SQL editor of each Supabase project that ALREADY has the comments schema (Dashboard -> SQL Editor ->
-- New query -> Run). A new project needs only `schema.sql`: it now creates this table as well, with the same block.
-- The script is idempotent: running it again is safe. The module never changes the schema itself.
--
-- !! In a SHARED or organisation database whose `comments` policies differ from the open ones in `schema.sql` (e.g. a database shared with other products),
-- !! run ONLY this file and NEVER the whole `schema.sql`: that would replace the policies of `public.comments`.
--
-- !! BEFORE running: make sure the project has no UNRELATED table named `public.comment_replies`. `create table if not exists`
-- !! does NOT check what is already there: such a table would be ADOPTED — row-level security turned on, its policies replaced
-- !! with the open ones below, and the public (anon) key granted full read/write access to it.
--
-- No foreign key and no `on delete cascade` on purpose: older clients (frozen previews, the live product) delete only the
-- `comments` row, and a foreign key without cascade would make that delete fail. The new adapter deletes a comment's replies
-- itself, before the comment. An orphan reply is harmless: nobody shows a reply without its comment.
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
