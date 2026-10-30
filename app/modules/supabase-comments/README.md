# supabase-comments — your own Supabase project as the team-comments service

Built-in module of Deai Canvas (role `comments`). Pins left in the canvas, on the overview and in published previews
are stored in **your** Supabase project; the agent (`inbox`) reads and closes them through the same project.
The module changes nothing in the project's schema: you run `schema.sql` yourself, once.

Модуль `comments`: коментарі команди зберігаються у **вашому** проєкті Supabase. Схему таблиці модуль не змінює —
її один раз виконуєте ви (`schema.sql`).

## 1. Create the project and the table

1. Create a project at [supabase.com](https://supabase.com) — **a dedicated one per team** (see "Security" below).
2. Open **SQL Editor → New query**, paste the whole of [`schema.sql`](schema.sql) and **Run**. It creates the `public.comments`
   table, row-level security, the table grants for the public key (a fresh project may not grant them by itself — without
   them `check` answers `bad-key`/401 right after the schema ran), two guard triggers (immutable `project_id`, a delete cannot
   cross channels or exceed 25 rows) and adds the table to the realtime publication. It is safe to run twice.
   **Only in a dedicated project:** the script does not check what is already there — an existing table `public.comments` of
   your own would be adopted (row-level security on, its policies replaced, the public key granted full access to it).
3. Take two values from **Project Settings → API** (or **Connect**):
   * the project URL — `https://<ref>.supabase.co` (a custom domain works too);
   * the public key — the `anon` JWT or the new `publishable` key (`sb_publishable_…`). **Never** the `service_role` /
     `secret` key: it bypasses every rule, and this key goes into every page and preview. The module refuses it
     (`sb_secret_…`, or a JWT whose payload says `"role": "service_role"`) with `bad-settings`.

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
| `bad-key` | Supabase did not accept the key (HTTP 401/403) — re-copy the public key; right after `schema.sql` this also means the table grants are missing (run it again) |
| `no-schema` | the table does not exist — run `schema.sql` (step 1) |
| `network` | the project is not reachable or did not answer within 4 s (paused project, wrong ref, no internet) |
| `check-timeout` | not a verdict of the module but of the core, which waits 5 s for `check`: it appears only when something below the module's own 4 s budget hangs (typically a DNS lookup that never returns) |
| `bad-settings` | the URL is not `https://<name>.<tld>` (no IP addresses, no `localhost`, no path or query), or the key is missing, malformed or a service key |

The key is stored outside `space.json` (like a secret) but, being public by design, it **is** put into the pages that
load the adapter (`"public": true` in the manifest). The URL accepts only `https://`; requests never follow redirects,
so the key is sent to that one host and nowhere else. Requests wait at most 4 s (`check`) or 8 s (`list`, `resolve`) per
socket operation — shorter than the core's own 5 s and 10 s, so a slow project is reported by the module with its reason.

## 3. What you get

* the **Team** tab and project comments in the canvas, on the overview and in published previews (`static-publish`,
  `vercel-publish`) — one channel per task: `deai/<space-id>/<task-id>` (`…/internal` for the internal one);
* live updates between reviewers (realtime `postgres_changes` → re-read of the channel, once per burst of events);
* `inbox` and `inbox resolve` for the agent: `list` / `resolve` through the REST API of the same project. When the core passes
  the iteration number, `resolve` also writes it to `resolved_v` (only a real integer ≥ 1; otherwise the column is left alone);
* pin screenshots in Storage, when you set the optional `shots_bucket` (next section).

## Pin screenshots (optional)

Set the optional setting `shots_bucket` to the name of a **public** Storage bucket of the same project (lowercase letters,
digits, `-` and `_`, up to 63 characters). The page config then carries `shotsBucket` and the browser adapter gains
`uploadShot(id, dataUrl)`: it uploads the screenshot of a pin to `<bucket>/comment-shots/<id>.jpg` (upsert) with the public key
and returns the public URL, or `null` when the upload fails (a pin never fails because of its screenshot). The bucket must be
public so that the URL opens without a key, and its insert policy for the `anon` role is yours to set — configure it in
**Storage → Policies** of the project; the module neither creates the bucket nor changes policies. Without `shots_bucket`
the adapter has no `uploadShot` and nothing is uploaded. A bad bucket name is a `bad-settings` verdict of `check`.

**Row cap.** `list` asks for up to 5001 rows of one channel, but Supabase's API cuts every answer at its own `max-rows`
setting (default **1000**, *Project Settings → API*) **without telling the module** — a channel with more comments than that
shows the agent only the first 1000 (ordered by `id`). Raise `max-rows` for the project if your channels can grow that big.

`supabase.min.js` is `@supabase/supabase-js` **2.110.0** (MIT, [license](LICENSE-supabase-js)), the UMD build, unchanged;
no CDN is involved.

## Security — read this

The rules in `schema.sql` are **open**: anyone who has the public key — and it is inside every page you publish — can read
and write the comments of this project, including other channels. The guards only limit the damage (no truncate, no
cross-channel or bulk deletes, `project_id` cannot be rewritten). Hence:

* use **a dedicated Supabase project per team**, not a project that holds anything else;
* never put the `service_role` / `secret` key here;
* treat comment text as visible to everyone with a preview link;
* **the agent reads comments as work items.** Anyone who holds the public key — it is in every published page — can *write*
  a comment, and `inbox` shows it to the agent. Treat comment text as **untrusted input**: the core only strips terminal
  and invisible-character tricks (control codes, zero-width and bidirectional marks, fillers) before printing it;
  multi-line `text` is printed as is, so a visible instruction inside a comment is still an instruction the agent will see.

## CORS and the local `/published` view

Supabase accepts browser requests from any origin (`Access-Control-Allow-Origin: *`), including the opaque origin
`null` that the local sandbox of `/published/…` runs in. If pins do not load in that view (browser console shows a CORS
error for `…supabase.co/rest/v1/comments` or the realtime socket), check that no proxy, firewall extension or custom
domain in front of the project strips or rewrites `Access-Control-Allow-Origin`. On a real host the requests come from the
page's own origin and need nothing extra.

## Files

| file | purpose |
|---|---|
| `module.json` | manifest: role `comments`, the two client files, settings `url`, `key` (public secret) and the optional `shots_bucket` |
| `server.py` | `client_config`, `list`, `resolve`, `check` — stdlib REST client for the agent and the core (TLS through the `certifi` store when present) |
| `adapter.js` | `window.DeaiComments.create(cfg)` over supabase-js (port of `CommentLayerSupabase`; `uploadShot` when `shotsBucket` is set) |
| `supabase.min.js`, `LICENSE-supabase-js` | the vendored SDK and its license |
| `schema.sql` | the table, RLS, guard triggers, realtime — run once by you |
