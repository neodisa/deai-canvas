-- Deai Canvas · feedback collector (schema) — the receiving side of "Report a problem / idea" (release 0.23).
--
-- Run this ONCE in the SQL editor of the Supabase project that collects feedback (Dashboard -> SQL Editor -> New query -> Run).
-- The script is idempotent: running it again is safe. It holds NO secrets and NO addresses: the project address and the
-- publishable key go into `app/feedback.json` of the product (or `config.json` / environment of a fork), the Teams webhook
-- address goes into Vault (see below).
--
-- !! USE A DEDICATED SUPABASE PROJECT FOR DEAI FEEDBACK. `create table if not exists` does NOT check what is already there:
-- !! if the project has a table `public.feedback` of its own, this script ADOPTS it (turns row-level security on and takes the
-- !! public roles' access away). Never run it in a project that serves comments, a dashboard or notifications of a space.
--
-- !! THE PUBLISHABLE KEY IS PUBLIC BY DESIGN (it ships inside the product). It can only INSERT: the public roles get no select,
-- !! update or delete on the table or on the screenshots bucket, so a leaked key means spam, never reading. Reading happens
-- !! in the dashboard or with the owner's own key.
--
-- !! THE PUBLISHABLE KEY IS PUBLIC, SO ANYONE CAN INSERT ROWS. Before going live set rate limits and quotas in the Supabase
-- !! dashboard (Auth / API rate limits, storage and database size alerts); inside the database the table only has size checks and
-- !! the Teams card is throttled (below), so a flood costs rows, never a flood of Teams messages.
-- !! AFTER RUNNING THIS SCRIPT, CHECK WITH THE PUBLISHABLE KEY (anon) that: select, update and delete on `public.feedback` are
-- !! refused, and reading or listing objects in the `feedback-shots` bucket is refused. Only insert may succeed.
--
-- !! Needs the `pg_net` extension and Vault (both ship with Supabase). The address of the Teams webhook lives in Vault only:
-- !!   select vault.create_secret('<webhook address>', 'teams_feedback_webhook_url');
create extension if not exists pg_net;

-- ------------------------------------------------------------------------------------------------------------- table
create table if not exists public.feedback (
  id uuid primary key,
  created_at timestamptz not null default now(),
  kind text not null check (kind in ('bug', 'idea')),
  text text not null check (char_length(text) between 10 and 10000),
  contact text check (contact is null or char_length(contact) <= 200),
  version text check (version is null or char_length(version) <= 40),
  os text check (os is null or char_length(os) <= 120),
  diag jsonb not null default '{}'::jsonb check (octet_length(diag::text) <= 65536),
  shot_path text check (shot_path is null or shot_path ~ '^[0-9a-f-]{36}\.(webp|png)$')
);

-- `diag` must be a JSON object (not a string, array or number): the Teams card and the dashboard read it as one.
alter table public.feedback drop constraint if exists feedback_diag_object;
alter table public.feedback add constraint feedback_diag_object check (jsonb_typeof(diag) = 'object');

alter table public.feedback enable row level security;

-- The anonymous role may only INSERT, and only these columns: `created_at` is the database's own clock (nobody forges it).
revoke all on public.feedback from anon, authenticated, public;
grant insert (id, kind, text, contact, version, os, diag, shot_path) on public.feedback to anon;

drop policy if exists feedback_insert_anon on public.feedback;
create policy feedback_insert_anon on public.feedback for insert to anon with check (true);

-- ------------------------------------------------------------------------------------------------------- screenshots
-- Private bucket: webp / png up to 2 MB. The public roles may only INSERT objects (the client sends `x-upsert: false`).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('feedback-shots', 'feedback-shots', false, 2097152, array['image/webp', 'image/png'])
on conflict (id) do update
  set public = false, file_size_limit = 2097152, allowed_mime_types = array['image/webp', 'image/png'];

drop policy if exists feedback_shots_insert_anon on storage.objects;
create policy feedback_shots_insert_anon on storage.objects for insert to anon
  with check (bucket_id = 'feedback-shots' and name ~ '^[0-9a-f-]{36}\.(webp|png)$');

-- ------------------------------------------------------------------------------------------------------------- Teams
-- Message text and contact come from anyone holding the public key: before they go into a card, markdown and link syntax is
-- neutralised (links -> a plain marker, then the characters [ ] ( ) * _ ` < > # \ ~ | are stripped), so nobody can inject a link,
-- a mention-like heading or formatting into the team's channel.
create or replace function public.feedback_plain(v text)
returns text
language sql
immutable
set search_path = pg_catalog
as $f$
  select regexp_replace(regexp_replace(v, '(https?|ftp|file)://\S+|www\.\S+', '[link removed]', 'gi'), '[][()*_`<>#\\~|]', '', 'g')
$f$;

revoke all on function public.feedback_plain(text) from public, anon, authenticated;

-- A new row -> a card in Teams (through pg_net, address from Vault). Privileged function, but it takes nothing from the caller:
-- it only reads the row that fired the trigger. The card is built with jsonb_build_object / jsonb_build_array only (the one
-- text concatenation is the 500-character cut of the message). It swallows every error: a notification never rejects feedback.
-- Throttle: when more than 10 rows arrived in the last 60 seconds (counted by created_at) the row is still stored, but no card is sent.
create or replace function public.feedback_notify_teams()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, vault, net
as $$
declare
  hook text;
  req_id bigint;
  plain text := public.feedback_plain(new.text);
  txt text := left(plain, 500) || case when length(plain) > 500 then '…' else '' end;
  recent integer;
  facts jsonb;
  card jsonb;
begin
  select count(*) into recent from public.feedback where created_at > now() - interval '60 seconds';
  if recent > 10 then
    return new;
  end if;

  select decrypted_secret into hook from vault.decrypted_secrets
   where name = 'teams_feedback_webhook_url' limit 1;
  if hook is null or hook !~* '^https://' then
    raise warning 'feedback_notify_teams: secret teams_feedback_webhook_url missing or not https';
    return new;
  end if;

  select jsonb_agg(jsonb_build_object('title', f.t, 'value', f.v) order by f.n) into facts
    from (values (1, 'Kind', new.kind), (2, 'Number', left(new.id::text, 8)), (3, 'Version', public.feedback_plain(new.version)),
                 (4, 'System', public.feedback_plain(new.os)), (5, 'Contact', public.feedback_plain(new.contact))) as f(n, t, v)
   where nullif(f.v, '') is not null;

  card := jsonb_build_object(
    'type', 'message',
    'attachments', jsonb_build_array(jsonb_build_object(
      'contentType', 'application/vnd.microsoft.card.adaptive',
      'content', jsonb_build_object(
        'type', 'AdaptiveCard',
        'version', '1.4',
        'body', jsonb_build_array(
          jsonb_build_object('type', 'TextBlock', 'size', 'Medium', 'weight', 'Bolder', 'wrap', true, 'text', 'Deai feedback'),
          jsonb_build_object('type', 'FactSet', 'facts', coalesce(facts, '[]'::jsonb)),
          jsonb_build_object('type', 'TextBlock', 'wrap', true, 'text', txt))))));

  select net.http_post(
    url := hook,
    body := card,
    headers := '{"Content-Type":"application/json"}'::jsonb
  ) into req_id;
  return new;
exception when others then
  -- only sqlstate: the error text of pg_net could echo the webhook address (it carries a signature) into the Postgres logs
  raise warning 'feedback_notify_teams failed: sqlstate %', sqlstate;
  return new;
end;
$$;

revoke all on function public.feedback_notify_teams() from public, anon, authenticated;

drop trigger if exists feedback_notify_teams on public.feedback;
create trigger feedback_notify_teams
  after insert on public.feedback
  for each row execute function public.feedback_notify_teams();
