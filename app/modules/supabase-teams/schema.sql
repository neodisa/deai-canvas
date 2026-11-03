-- Deai Canvas · module `supabase-teams` · Teams notifications of new comments (schema).
--
-- Run this ONCE in the SQL editor of YOUR Supabase project (Dashboard -> SQL Editor -> New query -> Run), AFTER the schema of
-- the `supabase-comments` module (this one builds on its `public.comments` table: the trigger below fires on every new pin).
-- The module never changes the schema itself: that would need rights it should not have.
-- The script is idempotent: running it again is safe.
--
-- !! USE A DEDICATED SUPABASE PROJECT. `create table if not exists` does NOT check what is already there: if the project has
-- !! tables `public.teams_delivery_log` or `public.teams_project_mute` of its own, this script ADOPTS them — it turns row-level
-- !! security on and takes the public (anon / authenticated) roles' access away. Run it only in a project where those names
-- !! are yours to hand over.
--
-- !! LIGA INSTALLATION: DO NOT RUN THIS. The LIGA database already has its own version of all of this (comment-layer schema).
-- !! Running it there would replace its functions and trigger.
--
-- !! THE KEY OF THE MODULE MUST BE NON-PUBLIC (the `service_role` key or the key of a role of your own). The mute RPCs below are
-- !! granted to `service_role` ONLY: the canvas calls them with the module's key, a published page never does. The public
-- !! (anon / publishable) key of a project goes into every page you publish, so it must not be able to mute or read anything here.
--
-- !! Needs the `pg_net` extension and Vault (both ship with Supabase). The address of your Teams webhook lives in Vault, never
-- !! in this script:   select vault.create_secret('<webhook address>', 'teams_webhook_url');
create extension if not exists pg_net;

-- Delivery log (observability, NOT an outbox: no retries): ties a pg_net request id to a comment so `teams_notify_health` can
-- count failures. Closed to the public roles.
create table if not exists public.teams_delivery_log (
  request_id bigint primary key,
  comment_id text not null,
  created_at timestamptz not null default now()
);
alter table public.teams_delivery_log enable row level security;
revoke all on public.teams_delivery_log from anon, authenticated;

-- Mute per channel. The key is `comments.project_id`; no row = notify (the default is "make noise"). Closed to the public
-- roles: read and switch only through the DEFINER functions below.
create table if not exists public.teams_project_mute (
  project_id text primary key check (length(project_id) between 1 and 200),
  muted_at timestamptz not null default now(),
  muted_by text not null default '' check (length(muted_by) <= 200)
);
alter table public.teams_project_mute enable row level security;
revoke all on public.teams_project_mute from anon, authenticated;

-- Pure Adaptive Card builder from a comment row (no secrets, no HTTP). Everything goes through jsonb_build_* — never string
-- concatenation over the comment's fields (the class of bug that gave an XSS in the panel); the only `||` is the cut of the
-- text to 500 characters. The labels (what the card says) are all in the one `declare` block below: change them there.
-- The image and the button are taken only when their address is https://.
create or replace function public.comment_teams_card(c public.comments)
returns jsonb
language plpgsql
immutable
set search_path = pg_catalog, public
as $$
declare
  l_title   text := 'Новий коментар';
  l_project text := 'Проєкт';
  l_iter    text := 'Ітерація';
  l_page    text := 'Сторінка';
  l_author  text := 'Автор';
  l_status  text := 'Статус';
  l_alt     text := 'Знімок коментаря';
  l_open    text := 'Відкрити сторінку';
  ver       text := coalesce(c.meta->>'version', '');
  iter      text := nullif(split_part(ver, '/', 1), '');
  page      text := coalesce(nullif(split_part(ver, '/', 2), ''), nullif(c.meta->>'route', ''));
  shot_url  text := case when c.meta->>'shotUrl' ~* '^https://[^[:space:]]+$' then c.meta->>'shotUrl' end;
  open_url  text := case when c.meta->>'url' ~* '^https://[^[:space:]]+$' then c.meta->>'url' end;
  txt       text := left(c.text, 500) || case when length(c.text) > 500 then '…' else '' end;
  facts     jsonb;
  body      jsonb;
  content   jsonb;
begin
  select jsonb_agg(jsonb_build_object('title', f.t, 'value', f.v) order by f.n) into facts
    from (values (1, l_project, c.project_id), (2, l_iter, iter), (3, l_page, page),
                 (4, l_author, c.author), (5, l_status, c.status)) as f(n, t, v)
   where nullif(f.v, '') is not null;

  select jsonb_agg(x.e order by x.n) into body
    from (values
      (1, jsonb_build_object('type', 'TextBlock', 'size', 'Medium', 'weight', 'Bolder', 'wrap', true, 'text', l_title)),
      (2, jsonb_build_object('type', 'FactSet', 'facts', facts)),
      (3, jsonb_build_object('type', 'TextBlock', 'wrap', true, 'text', txt)),
      (4, case when shot_url is not null then
            jsonb_build_object('type', 'Image', 'url', shot_url, 'size', 'Stretch', 'altText', l_alt) end)
    ) as x(n, e)
   where x.e is not null;

  content := jsonb_strip_nulls(jsonb_build_object(
    '$schema', 'http://adaptivecards.io/schemas/adaptive-card.json',
    'type', 'AdaptiveCard', 'version', '1.4', 'body', body,
    'actions', case when open_url is not null then
      jsonb_build_array(jsonb_build_object('type', 'Action.OpenUrl', 'title', l_open, 'url', open_url)) end));

  return jsonb_build_object(
    'type', 'message',
    'attachments', jsonb_build_array(jsonb_build_object(
      'contentType', 'application/vnd.microsoft.card.adaptive',
      'content', content)));
end;
$$;

revoke all on function public.comment_teams_card(public.comments) from public, anon, authenticated;

-- Privileged send: reads the webhook address from Vault and posts to Teams. It takes only an id and rebuilds the body itself
-- (the public key cannot post anything of its own) + a 2-minute freshness guard (blocks replays). It swallows every error:
-- a notification never aborts the comment itself.
create or replace function public.cl_send_teams(p_comment_id text)
returns void
language plpgsql
security definer
set search_path = pg_catalog, public, vault, net
as $$
declare
  c public.comments;
  hook text;
  req_id bigint;
begin
  select * into c from public.comments
   where id = p_comment_id and created_at > now() - interval '2 minutes';
  if not found then return; end if;

  -- Mute per channel. Here, not in the trigger: it holds for ANY caller. Sub-channels (`<channel>/…`) are muted together
  -- with the channel — "the whole project".
  if exists (select 1 from public.teams_project_mute m
              where c.project_id = m.project_id
                 or left(c.project_id, length(m.project_id) + 1) = m.project_id || '/') then
    return;
  end if;

  select decrypted_secret into hook from vault.decrypted_secrets
   where name = 'teams_webhook_url' limit 1;
  if hook is null or hook !~* '^https://' then
    raise warning 'cl_send_teams: secret teams_webhook_url missing or not https';
    return;
  end if;

  select net.http_post(
    url := hook,
    body := public.comment_teams_card(c),
    headers := '{"Content-Type":"application/json"}'::jsonb
  ) into req_id;

  insert into public.teams_delivery_log(request_id, comment_id) values (req_id, c.id);
exception when others then
  raise warning 'cl_send_teams failed: %', sqlerrm;
  return;
end;
$$;

revoke all on function public.cl_send_teams(text) from public;
grant execute on function public.cl_send_teams(text) to anon, authenticated;

-- The guard lives in an INVOKER trigger (not in the DEFINER function: there current_user is the owner, which bypasses RLS, so
-- row_security_active() would always be false). It sends only for real reviewers (anon / authenticated); bulk inserts made by
-- an admin or `service_role` go past it.
create or replace function public.cl_notify_teams()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
  if row_security_active('public.comments') then
    begin
      perform public.cl_send_teams(new.id);
    exception when others then
      null;  -- a notification NEVER aborts the write of a comment
    end;
  end if;
  return null;
end;
$$;

drop trigger if exists cl_notify_teams on public.comments;
create trigger cl_notify_teams after insert on public.comments
for each row execute function public.cl_notify_teams();

-- Switch of the mute (the canvas, the publish dropdown). Called with the MODULE'S key only: `service_role`.
create or replace function public.teams_mute_set(p_project text, p_muted boolean, p_by text default '')
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if p_project is null or length(p_project) not between 1 and 200 or p_muted is null then
    raise exception 'teams_mute_set: bad arguments';
  end if;
  if p_muted then
    insert into public.teams_project_mute(project_id, muted_by)
    values (p_project, left(coalesce(p_by, ''), 200))
    on conflict (project_id) do update set muted_at = now(), muted_by = excluded.muted_by;
  else
    delete from public.teams_project_mute where project_id = p_project;
  end if;
  return p_muted;
end;
$$;

-- State of the mute: for the canvas (to show the switch).
create or replace function public.teams_mute_state()
returns table(project_id text, muted_at timestamptz, muted_by text)
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select m.project_id, m.muted_at, m.muted_by from public.teams_project_mute m order by m.project_id;
$$;

-- Health of the delivery for the module's `check`: only aggregates and the FACT that the secret exists (never its value, never
-- a body). `net._http_response` is ephemeral (TTL), so the window is at most that; "no answer yet" is not counted as a failure.
create or replace function public.teams_notify_health(window_hours int default 6)
returns table(webhook_set boolean, sent bigint, responded bigint, failed bigint,
              last_failed_at timestamptz, last_sent_at timestamptz)
language sql
security definer
set search_path = pg_catalog, public, vault, net
as $$
  select
    exists (select 1 from vault.decrypted_secrets s
             where s.name = 'teams_webhook_url' and coalesce(s.decrypted_secret, '') <> ''),
    count(*)::bigint,
    count(r.id)::bigint,
    count(*) filter (where r.status_code >= 400 or r.timed_out or r.error_msg is not null)::bigint,
    max(l.created_at) filter (where r.status_code >= 400 or r.timed_out or r.error_msg is not null),
    max(l.created_at)
  from public.teams_delivery_log l
  left join net._http_response r on r.id = l.request_id
  where l.created_at > now() - make_interval(hours => least(greatest(coalesce(window_hours, 6), 1), 168));
$$;

-- ONLY `service_role` may call the three functions above. A new function in `public` is executable by `anon` and
-- `authenticated` by default in Supabase, so take it back explicitly. Never grant these to a public role: the page's key
-- would be able to mute the channel.
revoke all on function public.teams_mute_set(text, boolean, text) from public, anon, authenticated;
grant execute on function public.teams_mute_set(text, boolean, text) to service_role;
revoke all on function public.teams_mute_state() from public, anon, authenticated;
grant execute on function public.teams_mute_state() to service_role;
revoke all on function public.teams_notify_health(int) from public, anon, authenticated;
grant execute on function public.teams_notify_health(int) to service_role;
