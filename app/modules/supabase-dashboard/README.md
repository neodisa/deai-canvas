# supabase-dashboard — the team dashboard in your own Supabase project

Built-in module of Deai Canvas (role `dashboard`). The canvas builds a **card** of every task (name, Jira status, open
comments, preview and code links, designer, iterations) and this module **stores** the cards in a table of your Supabase
project and **returns** the rows of the whole team for the «Team» tab of the Tasks screen. The module does not decide what
a card is — the core does; it only keeps and gives back.

Модуль `dashboard`: картки задач команди зберігаються у **вашому** проєкті Supabase, а вкладка «Команда» читає їх звідти.

## 1. Create the table

1. Use **a dedicated Supabase project** (see "Security" below).
2. Open **SQL Editor → New query**, paste the whole of [`schema.sql`](schema.sql) and **Run**. It creates `public.deai_dashboard`,
   turns row-level security on and creates **no policy for `anon`**. It is safe to run twice.
3. Take from **Project Settings → API**: the project URL (`https://<ref>.supabase.co`) and a **non-public** key.

## 2. Settings

| setting | meaning |
|---|---|
| `url` | project address, `https://<name>.<tld>` only (no IP, no `localhost`, no path or query); requests never follow redirects |
| `key` | **non-public** key: `service_role` / `sb_secret_…` or the key of a role of your own. Stored as a secret, never put into a page |
| `table` | table name, default `deai_dashboard` (`[a-z_][a-z0-9_]{0,62}`) |

`check` answers `ok` only when the table is reachable. Its refusals: the address or the table name is wrong, the key is
missing or **public** (`sb_publishable_…`, or a JWT whose payload says `"role": "anon"`), the table does not exist (run
`schema.sql`), the project did not answer within 4 s.

## 3. What it does

* `rows` — `GET <url>/rest/v1/<table>?select=<team columns>&limit=500`, 4 s;
* `push(cards, mode)` — `POST <url>/rest/v1/<table>?on_conflict=id`, `Prefer: resolution=merge-duplicates|ignore-duplicates,return=minimal`,
  up to 50 cards per request (cards with a different set of keys go in separate requests, so a missing key never turns into
  `null`); a failed request puts all its card ids into `failed`, the rest are stored. A value `None` is never sent;
* `open_comments` — `GET <url>/rest/v1/comments?status=eq.open&select=project_id`: the numbers of open comments per channel,
  read from the table of `supabase-comments` in the same project. No such table — `{}`. Supabase cuts any answer at its
  `max-rows` (default 1000), so with more open comments than that the numbers are lower than the truth.

Error texts carry no key and no body of a request or an answer: only the HTTP status and the PostgREST code.

## Security — read this

* **The key is non-public.** The cards hold the name and e-mail of a designer. The public (anon / publishable) key of a
  project is inside every page you publish, so the table has no `anon` policy and the module refuses a public key;
* the key lives in `~/.deai/secrets.json` (owner only) and goes only to `apikey` / `Authorization: Bearer` of requests to `url`;
* use **a dedicated project**: `schema.sql` adopts an existing `public.deai_dashboard` of the same name.
