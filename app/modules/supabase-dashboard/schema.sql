-- Deai Canvas · module `supabase-dashboard` · schema of the team dashboard table.
--
-- Run this ONCE in the SQL editor of YOUR Supabase project (Dashboard -> SQL Editor -> New query -> Run).
-- The module never changes the schema itself: that would need more rights than it should have.
-- The script is idempotent: running it again is safe.
--
-- !! USE A DEDICATED SUPABASE PROJECT. `create table if not exists` does NOT check what is already there: if the project
-- !! has a table `public.deai_dashboard` of its own, this script ADOPTS it — it turns row-level security on for it and
-- !! takes the public (anon) role's access away. Run it only in a project where `public.deai_dashboard` is yours to hand over.
--
-- !! THE KEY OF THE MODULE MUST BE NON-PUBLIC (the `service_role` key or the key of a role of your own). The cards hold the
-- !! name and the e-mail of a designer, and the public (anon / publishable) key of a project goes into every page you
-- !! publish. So this table has NO policy for `anon`: with the public key it is unreadable and unwritable, and the module's
-- !! `check` refuses a public key. Never add an `anon` policy here.
create table if not exists public.deai_dashboard (
  -- Id of the task card (set by the canvas); one row per task.
  id              text primary key,
  name            text,
  status          text,
  jira            text,
  jira_status     text,
  jira_status_cat text,
  jira_synced_at  timestamptz,
  open_comments   int,
  figma_url       text,
  code_url        text,
  thumb_url       text,
  thumb_source    text,
  iterations      int,
  pages           int,
  gitlab_url      text,
  gitlab_repo     text,
  gitlab_path     text,
  comment_project text,
  backup_at       timestamptz,
  source          text,
  designer        text,
  designer_key    text,
  updated_at      timestamptz,
  synced_at       timestamptz
);

-- Row-level security on and NO policies: only a role that bypasses RLS (service_role) reads and writes the table.
alter table public.deai_dashboard enable row level security;

-- Belt and braces: a fresh project may grant table privileges to `anon` and `authenticated` by default; take them back.
revoke all on public.deai_dashboard from anon;
revoke all on public.deai_dashboard from authenticated;
