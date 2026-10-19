# supabase-comments — your own Supabase project as the team-comments service

Built-in module of Deai Canvas (role `comments`). Pins left in the canvas, on the overview and in published previews
are stored in **your** Supabase project; the agent (`inbox`) reads and closes them through the same project.
The module changes nothing in the project's schema: you run `schema.sql` yourself, once.

Модуль `comments`: коментарі команди зберігаються у **вашому** проєкті Supabase. Схему таблиці модуль не змінює —
її один раз виконуєте ви (`schema.sql`).

## 1. Create the project and the table

1. Create a project at [supabase.com](https://supabase.com) — **a dedicated one per team** (see "Security" below).
2. Open **SQL Editor → New query**, paste the whole of [`schema.sql`](schema.sql) and **Run**. It creates the `comments`
   table, row-level security, two guard triggers (immutable `project_id`, a delete cannot cross channels or exceed 25 rows)
   and adds the table to the realtime publication. It is safe to run twice.
3. Take two values from **Project Settings → API** (or **Connect**):
   * the project URL — `https://<ref>.supabase.co` (a custom domain works too);
   * the public key — the `anon` JWT or the new `publishable` key (`sb_publishable_…`). **Never** the `service_role` /
     `secret` key: it bypasses every rule and must not go into the canvas.

## 2. Enable the module in a space

Through the canvas module settings, or with the API of the running canvas (`<port>` is the one of your canvas):

```sh
curl -X POST http://127.0.0.1:<port>/api/module-enable \
  -H 'Content-Type: application/json' \
  -d '{"space": "<space-id>", "id": "supabase-comments",
       "settings": {"url": "https://<ref>.supabase.co"},
       "secrets": {"key": "<public key>"}}'
```

The answer carries the verdict of `check`:

| `error` | meaning |
|---|---|
| *(ok)* | the table `comments` answers |
| `bad-key` | Supabase did not accept the key (HTTP 401/403) — re-copy the public key |
| `no-schema` | the table does not exist — run `schema.sql` (step 1) |
| `network` | the project is not reachable (paused project, wrong ref, no internet) |
| `bad-settings` | the URL is not `https://<name>.<tld>` (no IP addresses, no `localhost`, no path or query) |

The key is stored outside `space.json` (like a secret) but, being public by design, it **is** put into the pages that
load the adapter (`"public": true` in the manifest). The URL accepts only `https://`; requests never follow redirects,
so the key is sent to that one host and nowhere else.

## 3. What you get

* the **Team** tab and project comments in the canvas, on the overview and in published previews (`static-publish`,
  `vercel-publish`) — one channel per task: `deai/<space-id>/<task-id>` (`…/internal` for the internal one);
* live updates between reviewers (realtime `postgres_changes` → re-read of the channel);
* `inbox` and `inbox resolve` for the agent: `list` / `resolve` through the REST API of the same project.

`supabase.min.js` is `@supabase/supabase-js` **2.110.0** (MIT, [license](LICENSE-supabase-js)), the UMD build, unchanged;
no CDN is involved.

## Security — read this

The rules in `schema.sql` are **open**: anyone who has the public key — and it is inside every page you publish — can read
and write the comments of this project, including other channels. The guards only limit the damage (no truncate, no
cross-channel or bulk deletes, `project_id` cannot be rewritten). Hence:

* use **a dedicated Supabase project per team**, not a project that holds anything else;
* never put the `service_role` / `secret` key here;
* treat comment text as visible to everyone with a preview link.

## CORS and the local `/published` view

Supabase accepts browser requests from any origin (`Access-Control-Allow-Origin: *`), including the opaque origin
`null` that the local sandbox of `/published/…` runs in. If pins do not load in that view (browser console shows a CORS
error for `…supabase.co/rest/v1/comments` or the realtime socket), check that no proxy, firewall extension or custom
domain in front of the project strips or rewrites `Access-Control-Allow-Origin`. On a real host the requests come from the
page's own origin and need nothing extra.

## Files

| file | purpose |
|---|---|
| `module.json` | manifest: role `comments`, the two client files, settings `url` and `key` (public secret) |
| `server.py` | `client_config`, `list`, `resolve`, `check` — stdlib REST client for the agent and the core |
| `adapter.js` | `window.DeaiComments.create(cfg)` over supabase-js (port of `CommentLayerSupabase`) |
| `supabase.min.js`, `LICENSE-supabase-js` | the vendored SDK and its license |
| `schema.sql` | the table, RLS, guard triggers, realtime — run once by you |
