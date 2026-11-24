# Writing your own module

A module adds capabilities to a
space: a *role* — publishing previews, design-system tokens, team comments, syncing mockups with git — and, with `api: 2`,
its own *tools* in the island and *actions* in ⌘K and the menus. Built-in modules live in `app/modules/`; **your own modules live in the space**, in
`<space>/modules/<id>/`, so they travel with the space through git. Their code runs on your computer only after **you**
trust it.

**Коротко (uk).** Свій модуль — тека `<простір>/modules/<id>/` з `module.json` і `server.py`. Канвас його бачить одразу,
але код не виконує, доки людина не довіриться: «Налаштування» → «Модулі» → картка модуля → «Довірити» → діалог із файлами → «Довірити» → системне
вікно ОС. Довіра — до точних байтів: канвас копіює їх у знімок `~/.deai/trusted/<відбиток>/` і виконує лише знімок. Зміна
теки не діє до повторної довіри. Агент може написати модуль, але довіритись — ні; межа — код, що приходить крізь теку
простору, git і сторінки макетів, а не локальний процес із вашими правами (він може сам правити `~/.deai/trust.json`).
Модуль може ще й додати **свої інструменти в острівець** (панель у пісочниці) і **дії** (⌘K, меню задачі та ітерації) — див.
розділ 7; приклад — `docs/modules/examples/page-notes/`. Інструмент може отримати дозволи `page`: через помічника ядра він читає
макет, помічає елементи, тимчасово змінює вигляд і стежить за кліками (код модуля в макет не потрапляє); приклад —
`docs/modules/examples/contrast/`.

## 1. The folder

```
<space>/modules/acme-publish/
  module.json      the manifest
  server.py        the functions of the role (standard library only)
  adapter.js       browser files — only for the comments role, listed in "client"
  panel/           the HTML, scripts and styles of a tool panel (api 2) — see section 7
```

* The folder name is the module `id`: `[a-z0-9][a-z0-9-]{0,39}`, the same as `id` in the manifest. A subfolder with any
  other name, or without a `module.json`, is not a module and is ignored.
* An id that a built-in module already has is skipped (Settings → Modules says so). At most 32 own modules per space
  (alphabetical order; the rest are skipped with a note).
* Folder rules — a folder that breaks one cannot be trusted, and the trust dialog says which rule:
  at most **200 files**, **5 MiB** in total, **8** levels of folders; only regular files and folders — no symbolic or
  hard links, no devices or pipes; file names without control, bidirectional or invisible characters, without a trailing
  dot or space, without names reserved on Windows (`CON`, `NUL`, `COM1`…), and no two names in one folder that differ only
  in letter case or Unicode form. `.DS_Store`, `__pycache__/`, `.git/` and `*.pyc` are ignored; every other file — hidden
  ones included — is part of what you trust.

## 2. The manifest (`module.json`)

```json
{"api": 1, "id": "acme-publish", "name": "Acme hosting", "version": "1.0.0",
 "roles": ["publish"], "publish_target": "url",
 "settings": [
   {"key": "site", "type": "text", "label": "Site id", "required": true},
   {"key": "token", "type": "secret", "label": "API token"}
 ]}
```

* `api` — `1` or `2`. `2` adds `tools` and `actions` (section 7); an older Deai does not trust such a manifest («a newer
  Deai is needed») instead of silently ignoring a part of it. `name` and `version` — strings shown to people.
* `roles` — **always present, as a list** (a module with only tools and actions has `"roles": []`); the roles the module provides: `publish`, `tokens`, `comments`, `vcs`, `dashboard`, `tracker`, `notify` (all of
  them are called by the core; no role name is reserved any more, and a role the core does not know makes the manifest
  invalid). One provider per role per space.
* `publish_target` (publish only) — `folder` (default) or `url`. The canvas serves the local copy of a published preview
  (`/published/…`) only for the built-in `static-publish`.
* `check_timeout_s` (optional) — an integer from 1 to 150: how many seconds the core waits for your `check` (default 5).
  Ask for more only when `check` starts a process that may be slow to start (`vercel-publish` in `cli` mode runs
  `npx --yes vercel whoami`, and a cold `npx` downloads the CLI first: 130). Any other value (0, 151, a float, a string,
  `null`) makes the manifest invalid. The canvas lets the request of «Check» / «Enable» wait for this long plus a margin, so
  keep your own limit below it. The same time is not given to `client_config` or to `validate`.
* `client` (comments only) — the browser files; see [comments.md](comments.md).
* `tools`, `actions` (`api: 2`) — own tools in the island and actions in ⌘K and the menus; see section 7.
* `settings` — what the module asks for: `text`, `path`, `bool`, `select` (with `options`) or `secret`; `required`,
  `default` and (secret only) `public` as in the built-in modules. Settings are stored in the space's `space.json`;
  secrets — in `~/.deai/secrets.json`, never in the space.

A manifest that breaks these rules cannot be trusted: the card says why, and nothing of the module runs.

## 3. `server.py`

Every module has `check(ctx) -> {"ok": bool, "error"?: str, "detail"?: str}` — a read-only health check (5 s, or the `check_timeout_s` of the manifest). A role
adds its own functions:

| role | functions |
|---|---|
| `publish` | `publish(ctx, build_dir, task)` |
| `tokens` | `tokens(ctx)` |
| `comments` | `client_config(ctx)`, `list(ctx, channel)`, `resolve(ctx, channel, id, reason)` |
| `vcs` | `status(ctx, target)`, `push(ctx, target, src, meta)`, `pull(ctx, target, dst, opts)`; optional `validate(ctx, target)`, `mirror_dir(ctx, target)` — see [The `vcs` role](#the-vcs-role) |
| `dashboard` | `rows(ctx)`, `push(ctx, cards, mode)`; optional `open_comments(ctx)` — see [The `dashboard` role](#the-dashboard-role) |
| `tracker` | `statuses(ctx, keys)` — see [The `tracker` role](#the-tracker-role) |
| `notify` | `mute_state(ctx)`, `mute_set(ctx, channel, muted, by)` — see [The `notify` role](#the-notify-role) |

A module that lacks `check` or a function of its roles shows as broken (the optional functions of `vcs` may be missing). The
exact return values are those of the built-in modules — read `app/modules/static-publish/` (`folder`),
`app/modules/vercel-publish/` (`url`), `app/modules/css-tokens/`, `app/modules/git-sync/` (`vcs`) and
[comments.md](comments.md).

`ctx` is `{"space": {id, path}, "settings": {…}, "secrets": {…only this module's…}, "folder_ok": f, "ModuleError": class,
"cache_dir": path, "find_tool": f}`. Raise `ctx["ModuleError"](code, "message")` for a failure; texts are cut to 300
characters and scrubbed of your secrets; the whole text, up to 64 KiB, is kept in the property `full` of the error (the
caller in the core may read it; the secrets are scrubbed from it too). A code the core knows (`bad-folder`, `vcs-offline`, for example) is passed on as it is; any other code is
reported as `module-error`. `cache_dir` is the path `~/.deai/cache/<space id>/<module id>` (under `DEAI_HOME`, when that is
set), a place for what the module can rebuild — mirrors, downloads. The core only computes the path and never creates
the folder: create it yourself when you need it (`os.makedirs(path, mode=0o700, exist_ok=True)`).

`ctx["find_tool"]("npx")` (or `"node"`) returns the path of that program on this computer, or `None`; any other name
gives `None`. Use it instead of `PATH`: a desktop app has a shorter `PATH` than a terminal, and the core's finder also
looks where nvm, volta and Homebrew put Node. The search can be slow, so call it only when you really need the tool
(`vercel-publish` does it in `cli` mode only). A module that starts the program should pass no secrets to it.

### The `publish` role

`publish(ctx, build_dir, task)` gets the folder of the built preview and
`task = {"id", "title", "dir", "state", "gated"}`:

* `state` — what this module returned in `state` the last time for this task, or `{}`; do not trust it blindly (a task
  can be copied to another one).
* `gated` — a boolean: `true` when the core put the password gate into the pages (the module never sees the password).
  A module that checks its own preview can use it to know whether a gate marker is expected in the page.

A module with `publish_target: "folder"` returns `{"path": <the folder it wrote to>}`; a module with `"url"` returns
`{"url": "https://…", "verified": bool, "warnings": [str, …], "state": {…}}` — `url` an `https` address without
credentials or a fragment, `state` a flat object (strings, numbers, booleans or `null` as values; at most 4096
characters as JSON), `warnings` at most 5 strings of at most 300 characters. Three more keys are **optional**; the core
reads them only for the in-house legacy space and ignores them everywhere else, so a module may always return them:

| key | meaning |
|---|---|
| `deploy_url` | the address of this publish itself, as opposed to the permanent `url` (a string) |
| `verify` | `{"reason": str}` — why `verified` is false; `vercel-publish` uses the reason `vercel_protection` when the sign-in of Vercel is in the way, and the legacy space turns that into its own hint |
| `cleanup_warning` | a string: the cleanup of old publishes did not finish (the publish itself succeeded) |

A module that runs a command-line tool should report **codes**, not finished sentences: keep the raw output in
`ModuleError.full` and let the caller decide what to tell the person. Besides `vercel-auth` and `vercel-busy`, the core's
table has these codes for that: `no-node` (409, no `npx`), `vercel-login` (409, the CLI is not signed in),
`vercel-scope` (409, no access to the team), `vercel-deploy` (502, the deploy failed), `vercel-no-url` (502, the deploy
printed no address). Any other code of your own is reported as `module-error`.

The built-in `vercel-publish` is the reference for the `url` kind (`token` mode: REST; `cli` mode: `npx vercel`).

`server.py` (at most 1 MiB) is executed by the core (not imported): write it against the **standard library only**. The
module is not put into `sys.modules`, so `@dataclass` together with `from __future__ import annotations` fails and its
classes cannot be pickled; functions and plain dicts are enough.

### The `vcs` role

`vcs` syncs a task's mockups with a remote repository: **send** an iteration, **pull** a colleague's work back as a new
iteration, and show the state (the dot in the task bar). The built-in module is `app/modules/git-sync/` (any git remote,
through the system `git`); read it next to this section.

**A transport, not a model of iterations.** The module keeps whatever local copy it needs, puts a folder it is given
into the remote, and copies a folder of the remote out. It knows nothing about iterations, authors or `iterations.json`.
The core decides *what* is sent (the clean mockup of the chosen iteration, a `README.md` for a multi-page one,
`.canvas-state.json`), never sends a colleague's iteration, makes a new iteration of what was pulled, forks from a
foreign or newer one and records the state. A module that tried to do that too would only duplicate it; and a module
for another transport gets the same behaviour for free.

**The target.** Every call gets `target`, what to sync for this task, computed by the core:

```
target = {"repo": str, "path": str, "branch": str, "task": <task id>, "ssh_key"?: str, "host_ip"?: str}
```

* The sources, first non-empty wins: the task's own `vcs: {repo, path?, branch?}` (written by `POST /api/task-new`, or by
  hand in the task file) → in a space with integrations, the task's older `gitlab` mapping → the module's settings
  `repo`, `path`, `branch`. A `path` or `branch` the task does not give comes from the settings, and then from the
  defaults `mockup/{task}` and `main`.
* An empty string anywhere means «not set». `{task}` in `path` becomes the task id; `path` has no `/` at either end.
  No `repo` at all: the task is *not configured* — the core does not call the module and the bar offers «Configure
  repository…».
* `ssh_key` and `host_ip` are put into the target only in a space with integrations (from the task or the shared root of
  the task file). Elsewhere read them from your own settings, as `git-sync` does (a value in `target` wins over the
  setting of the same name).
* The core reads these settings of your module by name: `repo`, `branch`, `path` (the target defaults above) and
  `autosync` (a boolean). While `autosync` is not true, `POST /api/autosync` — what an agent's Stop hook calls after
  every reply — sends nothing and answers `reason: "autosync-off"`. Local history is separate from sending: after every
  reply the core still commits the agent's edits to your own iterations locally (`itN: зміни AI`, one commit per
  iteration, never pushed). Declare them in the manifest to get these features.

**The functions.** Each takes `ctx` first and reports a failure with `ctx["ModuleError"]` (the codes are below).

* `status(ctx, target)` → `{"behind", "behind_path", "unpushed", "on_remote", "web", "label"}`.
  * `behind` — commits the remote has and the local copy lacks, whole repository; `behind_path` — the same, only under
    `path` (`git-sync` stops a send on it, while `behind` alone is caught up with a fast-forward); `unpushed` — local commits that are not
    on the remote; `on_remote` — is `path` on the remote branch: `true`, `false`, or `null` when the branch itself is not
    there; `web` — the address of the history of `path`, or `null` (the page offers «History» only for `http(s)://`);
    `label` — a short name of the service: only `GitLab`, `GitHub` and `Git` are shown, anything else is replaced.
  * The core adds what it knows about iterations (`dirty`, `synced_at`…). The bar asks on every start and after every
    action: answer fast, and when the local copy is busy with another operation raise `vcs-busy` instead of waiting
    (`git-sync` does; the bar asks again every 5 s, up to 4 times).
* `push(ctx, target, src, meta)` — `src` is a folder the core prepared outside the task folder (it removes it afterwards:
  do not keep it or change it). Its content must become `path` in the remote — the folder is replaced, dot-files
  included — and be committed and pushed, never forced. `meta` is `{"message": str, "author": {"name": str, "email": str}}`:
  the commit text and identity. The core has already removed control characters (only `\n`, `\t` and `\r` stay in `message`, which is multi-line) and made both author fields non-empty;
  use them and do not invent an identity. Results, in the shapes of `git-sync`:
  * `{"ok": true, "synced": true, "changed": true, "pushed": true, "sha": "<short>", "error": null}` — sent. Without `sha`
    the core does not record the sync (it prints a warning).
  * `{"ok": true, "synced": true, "changed": false, "pushed": false}` — nothing changed, and the remote already has it.
  * `"changed": false` with `"catchup": true` — nothing new to commit, but an earlier local commit had not reached the
    remote and now did (`"ok": false` with `error` and `code` if that push was refused).
  * `{"ok": false, "synced": false, "blocked": "behind", "behind": n, "behind_path": n, "behind_top": {author, date, subject}}`
    — somebody changed `path` on the remote: do not send over it, the person pulls first.
  * `{"ok": false, "synced": false, "blocked": "diverged", "behind": n, "ahead": n, "behind_top": {…}, "error": str}` — the
    local copy cannot be fast-forwarded to the remote.
  * the remote refused the push: `{"ok": false, "synced": false, "changed": bool, "pushed": false, "error": str, "code": str}`.

  The core decides that the remote has the mockup by `synced`, not `ok`, and adds `remote` (`<repo>:<path>`) to what it
  answers.
* `pull(ctx, target, dst, opts)` — `dst` is an existing **empty** folder: copy the remote's `path` into it. `opts` is
  `{"ignore": ["shots"]}`: sub-folders of `path` whose changes are not «work» (the snapshots the canvas re-shoots by
  itself). Returns `{"found": true, "last_commit": {"author": str, "time": int | null}}`, or
  `{"found": false, "last_commit": null}` when `path` is not in the remote (or the remote is empty): that is not an
  error. `author` — the author of the last commit that touched `path` (the core takes the author from the mockup's own
  `.canvas-state.json` first); `time` — the Unix time of the last such commit **outside** `ignore`, or `null`; the core
  uses it to tell whether the remote is older than the person's own iteration. When the pull cannot be done (the local copy
  diverged) raise: stale files would become an iteration. The core is strict: `found` must be exactly `true` and `dst`
  not empty.
* `validate(ctx, target)` — optional. Returns the normalized target (a dict) or raises `vcs-bad-target`; no network, no
  `git`. The core calls it, when it exists, on `POST /api/task-new` with the task's `vcs`, before anything is written
  (a refusal is `400 vcs-bad-target`), and gives it 5 seconds (`check-timeout` after that). A module without it is not
  checked there.
* `mirror_dir(ctx, target)` — optional. Returns the path of the local copy as a string, for diagnostics and tests;
  creates nothing.

The core checks the shape: `status`, `push`, `pull` and `validate` must return a dict, `mirror_dir` a string, otherwise
the call is a `module-error`. The strings at the top level of what `status`, `push` and `pull` return are passed through
a filter that hides the credentials of an address (`https://TOKEN@host/…` becomes `https://***@host/…`) — do not put
credentials into your texts anyway.

**The error codes.** All five are in the core's table, so they pass as they are; any other code is a `module-error`.

| code | HTTP | raise it when |
|---|---|---|
| `vcs-offline` | 502 | no network, DNS or VPN; the remote did not answer in time |
| `vcs-auth` | 502 | the remote refused access: key, saved sign-in, host key |
| `vcs-bad-target` | 400 | the address, branch or folder failed the checks — before any network call |
| `vcs-busy` | 409 | this local copy is busy with another operation |
| `vcs-error` | 502 | any other failure; the text is at most 300 characters and carries no access data |

The routes answer a refusal with `200 {"ok": false, "error", "code"}` (`GET /api/vcs-status`: `{"configured": true,
"error", "code"}`), and automatic sync treats any refusal of the module as a quiet `offline` with the `code`. The HTTP column is what
`POST /api/task-new` answers when `validate` refuses.

**Time.** The core sets no limit on `status`, `push` and `pull`: they may take minutes (a first clone). Keep your own and
turn a timeout into `vcs-offline` (`git-sync`: 120 s for a git command, 180 s for a clone). `validate` gets 5 s.

**Your own module of this role** lives in `<space>/modules/<id>/` and runs after trust, like any other (section 4). It
then talks to the network and runs programs with your permissions: read the code before you trust it. A module that is
on in the space but not trusted on this computer keeps the role «on paper»: sync reports its error (for example
`module-untrusted`) and does not fall back to the built-in `git-sync`.

### The `dashboard` role

`dashboard` is the team board of a space: it **stores the cards of the tasks** the core builds and **gives back the rows
of the team** for the «Team» tab of the Tasks screen. The built-in module is `app/modules/supabase-dashboard/`.

**A store, not a model of tasks.** The core (`app/dashboard.py`) decides what a card is: it collects it from the task, the
iterations, the Jira status and the open comments, drops registry fixtures and cards with personal data, and tells when to
send. The module only keeps what it is given and returns what it has. The same cards go to every provider of the role.

**The functions.** Each takes `ctx` first and reports a failure with `ctx["ModuleError"]` (the codes are below).

* `rows(ctx)` → a list of dicts, the rows of the team. The core keeps only the keys of `TEAM_KEYS`
  (`id`, `name`, `jira`, `jira_status`, `jira_status_cat`, `open_comments`, `thumb_url`, `code_url`, `updated_at`,
  `designer`, `iterations`, `pages`), drops a row without a string `id` and keeps at most 500 rows. Anything that is not a
  list is a `module-error`. Answer fast: the core waits **6 seconds** for `rows` (the Tasks screen is the first page); keep
  your own socket timeout below that (the built-in module uses 4 s), so you can answer with your own text instead of a bare
  `check-timeout`.
* `push(ctx, cards, mode)` — `cards` is a list of dicts the core built; `mode` is `"merge"` (update the row of an
  existing card, the new fields on top) or `"insert"` (add only the cards that are not there yet, never touch an existing
  row: the base cards of the registry). Returns `{"ok": n, "failed": {"<card id>": "<text>"}}`: how many cards were stored
  and the reason for each that was not. Raise a `ModuleError` only when the service cannot be reached at all. The core
  does not send `None` values, but a module should not rely on that. The core gives the whole call 60 seconds. When one
  call carries the same card `id` twice, the **last** card wins (a store that refuses one request with a repeated key would
  lose the whole batch); a card without a string `id` is reported in `failed`. If the service takes several cards in one
  request, group them by their set of keys: a key missing from one card must not become `null` and wipe the stored value
  (the built-in module sends at most 50 cards per request and keeps cards with different key sets in separate requests).
* `open_comments(ctx)` — optional. Returns `{"<comment channel>": <number of open comments>}`: the core uses the number to
  tell the status `review` from `pub` of a card. A module without it, or one that fails, gives `{}`. The built-in module
  reads the table `comments` of `supabase-comments` in the same project (no such table — `{}`); Supabase cuts any answer at
  its `max-rows` (1000 by default), so with more open comments than that the numbers are lower than the truth.
* `check(ctx)` — as for every module (section 3): a verdict dict `{"ok": bool, "error"?: str, "detail"?: str}`, never an
  exception. The built-in module refuses a **public** key here (`public-key`) and answers `no-schema`, `bad-key` or
  `network` for the rest; `check` is the only place that judges the key, `rows`, `push` and `open_comments` never do.

**Who is asked, and when.** A space has the «Team» tab when it has a provider of the role; without one `team` is `null` and
the tab is hidden. A broken module of its own does not hide the tab: it shows an error banner that names the reason. The rows
are cached **per space** (60 s; an error for 10 s, and a failure keeps the last rows that were read), and a different provider
never shows the rows of the previous one. The cards are sent by a background process (`bin/overview_push.py sync`) after a
publish, after a git sync that pushed and after an autosync that changed something — one process per space at a time (a
trigger that comes while it runs only asks for one more run). `DC_NO_OVERVIEW` silences the writing for every provider. For
the in-house LIGA setup (an implicit provider, not a module) `DC_TASKS_FILE` silences it too: an isolated run never writes to
the shared state. Modules of an ordinary space are not under this law: their config is the space's own `space.json` and
`secrets.json`.

**The error codes.** Both are in the core's table, so they pass as they are; any other code is a `module-error`.

| code | HTTP | raise it when |
|---|---|---|
| `dashboard-unconfigured` | 409 | the service has no address or key to talk to |
| `dashboard-error` | 502 | the service refused or did not answer; the text carries no key and no body of a request |

**Your own module of this role** lives in `<space>/modules/<id>/` and runs after trust, like any other (section 4). Keep
the key of a service that can write in a `secret` setting and do not mark it `public`.

### The `tracker` role

`tracker` tells the status of tasks in the issue tracker of a space (Jira, Linear…). The core asks for the statuses of the
task keys of the space and shows them as the badge of a task on the Tasks screen and on the cards of the team board. The
built-in module is `app/modules/jira-tracker/`.

**The function.** `statuses(ctx, keys)` takes `ctx` first and reports a failure with `ctx["ModuleError"]` (the codes are
below). Read-only: it never changes anything in the tracker.

* `keys` — a list of strings, at most **100**, without repeats. The core sends only the keys of the form
  `[A-Z][A-Z0-9_]{0,31}-[1-9][0-9]{0,9}` (`KEY_RE`, a whole-string match: `DEMO-1`, `AB_2-10`; not `demo-1`, `DEMO-0`,
  `DEMO-01`, `DEMO 1`); everything else — a hand-edited junk in the task file — is dropped **before** the call, so it never
  reaches a query. More than 100 keys are cut into several calls.
* Returns `{"<key>": {"name": str, "cat": str | None}}`. `name` is the status as the tracker shows it; `cat` is its
  category: `new`, `indeterminate` or `done` (the categories of Jira), `None` when the tracker has none. A task the tracker
  does not know is simply absent from the answer — not an error. The core keeps only the keys it asked for, cuts `name` to
  **80** characters and drops an entry whose `name` is empty, not a string or holds a control character; a `cat` outside the
  three values becomes `None`. An answer that is not a dict is a `tracker-error`.
* `ctx["timeout_s"]` — the budget **in seconds for your own socket**; the core waits longer than that, so keep your
  requests within it and answer with your own text instead of a bare `check-timeout`. The Tasks screen gives a socket
  **4 s** (the core waits 6 s per call); the sync of the team board gives **15 s** (the core waits 30 s per call). The field
  is new in the contract of this role; the `ctx` of other roles has none.
* `check(ctx)` — as for every module (section 3): a verdict dict, never an exception. The built-in module answers
  `module-error` for settings that do not fit (address, e-mail, token), **`tracker-auth`** for HTTP 401/403 (a wrong e-mail or
  token; its own code, because Settings → Modules labels a `module-error` «the module crashed during the check»), `network`
  when the tracker cannot be reached, and `tracker-error` or `module-error` (with the HTTP status) for any other answer. The
  codes of a verdict are free text for the screen: the table of error codes below lists only the codes you **raise**.

**Who is asked, and when.** A space has a tracker when it has a provider of the role; without one the Tasks screen shows no
status from a tracker. A space with integrations and no module of its own uses the built-in `jira-tracker` through the
address and the credentials of the installation (`jira_base` in the legacy `tasks.json`, `JIRA_EMAIL` / `JIRA_TOKEN`). In an isolated run (`DC_TASKS_FILE` or `DC_NO_OVERVIEW`) the
credentials of the installation come only from the root of the tasks file (`jira_email`, `jira_token`), never from the
environment; the contract of a module is the same.

**The error codes.** Both are in the core's table, so they pass as they are; any other code is a `module-error`. The table is
for the codes you **raise** from `statuses`; the verdict codes of `check` (above) are separate.

| code | HTTP | raise it when |
|---|---|---|
| `tracker-unconfigured` | 409 | the tracker has no address or credentials to talk to |
| `tracker-error` | 502 | the tracker refused or did not answer (a 5xx, a timeout, a rate limit, an answer of the wrong shape); the text carries no token and no body of a request |

The built-in `jira-tracker` raises `module-error` for what a person has to fix (bad settings, HTTP 400 with a fixed hint «check
the task keys», 401/403, a redirect) and `tracker-error` for the rest (a network failure, 5xx, and the transient 408 and 429).
It re-checks the keys against `KEY_RE` (a list of at most 100) and answers `module-error` to anything else. The core also
turns a failure it caused itself into a `tracker-error` («the answer is not a dict»).

**Your own module of this role** lives in `<space>/modules/<id>/` and runs after trust, like any other (section 4). Keep
the token of a tracker in a `secret` setting and do not mark it `public`.

### The `notify` role

`notify` keeps the **mute** of the Teams notifications of a space: the switch «Notify Teams» in the publish menu of the
canvas shows whether the comment channel of a task is silenced and silences or un-silences it. Sending the card itself is
not done by the core: the service behind the module (the database, in the built-in `supabase-teams`) sends a card to Teams
for each new pin and looks at the mute before it does. The built-in module is `app/modules/supabase-teams/`.

**The functions.** Both are required: a module that declares the role `notify` and lacks `mute_state` or `mute_set` is
`bad-manifest` (as for `tracker`). Both take `ctx` first and report a failure with `ctx["ModuleError"]` (the codes are below).

* `mute_state(ctx)` — returns a **list** of the silenced channels:
  `[{"project_id": str, "muted_at": str | None, "muted_by": str}]`. `project_id` is the channel (`dc/t1`), `muted_at` the time
  of the switch as the service wrote it, `muted_by` the signature of the person (a short hash of an e-mail, never a name or
  an e-mail: the list is readable by anyone who may call the service). The core keeps only the dicts whose `project_id` is a
  string of 1..**200** characters, turns a `muted_by` that is not a string or is longer than **200** into `''` and a
  `muted_at` that is not a string or is longer than **40** into `None`, drops every other key and keeps at most **1000** rows.
  An answer that is not a list is a `notify-error`: «I do not know» is never shown as «nothing is silenced».
* `mute_set(ctx, channel, muted, by)` — silences (`muted` is `True`) or un-silences (`False`) one channel and returns the new
  state as a **bool**. `channel` is a non-empty string of at most **200** characters, `muted` is a real `bool` (not `1` or
  `"true"`), `by` is the signature of the person, a string of at most **200** characters (may be empty). The core checks the
  arguments **before** the call, so a module never sees a bad one. Anything but a bool in the answer is a `notify-error`.
* `check(ctx)` — as for every module (section 3): a verdict dict, never an exception. The built-in module answers
  `module-error` for settings that do not fit (address, key), **`public-key`** for a public key (`sb_publishable_…` or a JWT with
  `"role": "anon"`; its own code, because Settings → Modules labels a `module-error` «the module crashed during the
  check»; `supabase-dashboard` answers it too), **`notify-no-schema`** when the database has no notification functions (the
  shared `no-schema` is worded «no table comments», which is wrong here), **`notify-no-webhook`** when the Vault secret
  `teams_webhook_url` is missing, `bad-key` for HTTP 401/403, `network` when the service cannot be reached, and `notify-error`
  (with the HTTP status) for any other answer. For the implicit LIGA path it neither refuses a public key nor asks for the
  health of the delivery. The codes of a verdict are free text for the screen: the table of error codes below lists only the codes
  you **raise**.

**What the core does with the state.** A silenced channel covers its sub-channels: with `dc/t1` silenced, `dc/t1/internal` is
silenced too (`via` names the channel that covers it). The match is by `<channel>/`, not by a bare prefix: `dc/t10` and
`dc/t1x` are **not** sub-channels of `dc/t1`. A switch is «mine» only when its `muted_by` is not empty and equals the signature
of this computer; a row without `muted_by` (an old one) is never «mine». The core waits **10 s** for a call
(`NOTIFY_TIMEOUT`); keep the socket of your own requests shorter (the built-in module uses 8 s) and answer with your own text
instead of a bare `check-timeout`.

**Who is asked, and when.** A space has notifications when it has a provider of the role; without one the canvas shows no
switch and the route `/api/teams-mute` answers `409` with the code `notify-off`. The role no longer depends on the `integrations`
flag. A module of your own that is on in the space but cannot run (not trusted, a manifest that broke) is reported with its
reason, not shown as «no notifications». A space with integrations and no module of its own uses the built-in
`supabase-teams` through the address and the key of the installation (the same Supabase as the team comments).

**The error codes.** Both are in the core's table, so they pass as they are; any other code is a `module-error`. The table is
for the codes you **raise** from `mute_state` and `mute_set`; the verdict codes of `check` are separate.

| code | HTTP | raise it when |
|---|---|---|
| `notify-unconfigured` | 409 | the service has no address or key to talk to |
| `notify-error` | 502 | the service refused or did not answer; the text carries no key and no body of a request |

**Your own module of this role** lives in `<space>/modules/<id>/` and runs after trust, like any other (section 4). Keep the
key of a service that can write in a `secret` setting and do not mark it `public`: the switch is made from the canvas with a
private key and never from a page.

### The `compat` setting, `shared_state` and `ctx['legacy']`

Three things concern the in-house LIGA setup and what its migration (0.17.0 to 0.19.0, `bin/migrate_liga.py`) writes into
`space.json`. An ordinary module does not need any of them.

* **`compat`** is an optional `select` setting of five built-in modules, each with its own meaning (the core reads it only for a
  **built-in** module with that exact id, never for a module of your own that declares a setting of the same name):
  * `supabase-dashboard` and `supabase-teams`: `""` (default) or `"comment-layer"`. It says that the Supabase base is the old
    comment-layer schema: a **public** key is allowed (`check` does not answer `public-key`), and `supabase-teams` does not call
    `teams_notify_health`, which that schema does not have. The migration writes it into the explicit record of the LIGA space; the
    implicit path puts it into `settings` too.
  * `supabase-comments` (0.18): `""` (default) or `"comment-layer"`. `comment-layer` keeps the old **channel scheme** of the
    comments: `comment_project` of the task, or `dc/<task>`, plus `/internal`; empty means `deai/<space>/<task>`. The scheme is
    decided by one function of the core, `deai_modules.comment_channel_of`, in every place (pins, `/api/task`, the Teams silence,
    the dashboard counters), so the module itself never has to know it. Changing the value on a live space cuts off the existing
    pin history: the channel is another one.
  * `git-sync` (0.18): `""` (default) or `"design-canvas"`. `design-canvas` is the behaviour of the old implicit provider: the core
    lays `cache_dir` (the old mirrors folder: `DC_MIRRORS_DIR` or `<ROOT>/.mirrors`) and `mirror_flat: true` over your `ctx` (flat
    folders `<slug>` instead of `<host>/<slug>-<hash8>`), and the texts («design-canvas: sync», README, «GitLab» / «repository»,
    the fork note) are the old ones (one predicate, `serve.vcs_legacy_texts`). The module does not know `ROOT`; it only honours
    `ctx['mirror_flat']` and `ctx['cache_dir']`. Changing the value makes the mirror folders and the texts different.
  * `vercel-publish` (0.19, module version 1.2.0; the last setting): `""` (default) or `"design-canvas"`. `design-canvas` sends
    the publishing down the **path of LIGA**: the core does not call `publish` of the module, but runs its old branch (the
    project `pv-…` and the scope kept in `tasks.json`, old safe project names accepted, the preview password of the task / of the
    root / `1100`, the build mark `legacy`, the old side effects and answer keys). In this mode `auth`, `team` and `password` of
    the record are **not read** (the label says so). One predicate decides it, `deai_modules.publish_legacy_path` (the implicit
    provider, or the built-in `vercel-publish` with this `compat`); `deai_modules.publish_module` returns `None` for that path.
    Changing the value on a live space moves the publishing to the module path: new projects, other URLs, and the password is
    the module secret `password` (empty means no gate).

  **The «built-in + id» rule.** A space's own module cannot take the id of a built-in one (Settings → Modules shows the note
  `id-taken` and the module is skipped), and the predicates above also test `origin == 'builtin'` and the exact id (for the
  publish predicate: `origin == 'builtin'` and `id == 'vercel-publish'`); so a module of your own called anything else cannot
  pick up the LIGA channel scheme, the LIGA texts or the LIGA publishing path by declaring `compat`.
* **`shared_state`** is a boolean on a module record in `space.json` (`"modules": {"<id>": {"enabled": true, "settings": {…},
  "shared_state": true}}`). The migration writes it; a value that is not a boolean is ignored. A record marked `true` is the
  shared state of the LIGA space although it is explicit, so for the roles `dashboard`, `tracker` and `notify` it is under the
  **isolation law**: in an isolated run (`DC_TASKS_FILE` or `DC_NO_OVERVIEW`) the core does not call the module, but answers like
  for the implicit provider (a test seam first, then a refusal, then the real call). Since 0.18 the law covers `comments` and `vcs`
  too: there a **built-in** record with the flag builds its `ctx` like the implicit path (the Supabase key comes from the root of
  the tasks file, never from `secrets.json` of the real home; the git mirrors are flat in `DC_MIRRORS_DIR`), and outside isolation
  the record's own `module_ctx` is used. `publish_comments` refuses such a comments record in a preview built by a publish module
  (the key must not travel in a preview; this also refuses a module of your own with a hand-set flag). The module **«Check»**
  of a record with the flag does not read the secrets and does not call the module in an isolated run: the answer is
  `{"ok": false, "error": "isolated"}` and the last real check result is kept (all five roles).
  `deai_modules.shared_state(space, module_id)` is the question; Settings → Modules does not show or change the flag. Do not
  set it on a module of your own unless it really talks to a state that tests must never touch.
* **`ctx['legacy']`**: the built-in modules **do not read it any more**; they read `settings.compat`. The flag stays in the ctx
  of the implicit path only for foreign modules and goes with the implicit path in 4d-4. A module of your own that checks it will
  keep working there, but must not expect it anywhere else.

## 4. Trust

1. Put the folder into `<space>/modules/`. Settings → Modules shows it as a card marked «own» and «Waiting for trust»; its
   code has not run.
2. The card's main button «Trust» (and «Code» in the «⋯» menu) opens a dialog: what the module asks for, every file with its size, the fingerprint. «Trust» in it then asks the
   **operating system** to confirm in its own window (macOS dialog, Windows message box, Linux `zenity`/`kdialog`). Only
   a person at the computer can answer it: a script on a page and an agent without control of the screen cannot.
   After «No», asking again for the same version within 30 s is refused without a window.
3. The canvas copies exactly the bytes you saw into `~/.deai/trusted/<fingerprint>/` (read-only) and runs only that
   snapshot. Write the module's state into the space folder or `ctx["cache_dir"]`, never next to `__file__`. The record is
   keyed by `realpath(<space>/modules/<id>)` on this computer: moving or renaming the space folder (or the module's
   folder) is a new trust, and the old record and its snapshot stay behind.
4. Editing the folder does not change what runs: the card says «The folder has changes» and the previous version keeps
   working until you trust the new one. A new version that breaks a folder rule cannot be trusted; the old one keeps
   running.
5. «Revoke trust» («⋯» menu of the card, or the dialog) stops the code; `space.json` and the settings stay. A module that is on in the
   space but not trusted on this computer keeps its role «on paper»: the role reports an error instead of falling back
   to another provider.
6. In the new-space wizard your module is marked «own». Until you trust it, its option is disabled and has a «Trust»
   button (the same dialog, the same system window); a folder that cannot be trusted shows the reason instead of the
   button. If a teammate already turned it on in `space.json`, it stays selected; the settings step writes nothing for it
   and says it is waiting for trust. A module whose folder has changes can be selected — the previous version runs; trust
   the new one in Settings → Modules.

The module's top level gets **5 s** to load; a module that hangs is shown as broken (its thread lives until the server
restarts, and if it loops it may slow the canvas down). Browser code of a trusted `comments` module runs in canvas pages and published previews with the canvas's
own access — that is part of what you trust. The panel of a tool (section 7) does not: it runs in a sandbox without that access.

## 5. The agent

An agent can write the folder, read `GET /api/modules?space=<id>` and `GET /api/module-trust?space=<id>&id=<module>`, and
— after **you** trust the module — connect and configure it (`POST /api/module-enable`, `/api/module-settings`). It cannot
trust: `POST /api/module-trust` needs the canvas page in a browser (`Origin` and `Sec-Fetch-Site: same-origin`; a script
or `curl` gets `403 trust-needs-ui`) and then the system window. It may revoke trust (`POST /api/module-untrust {space, id}`).
Ask the person to trust the module.

An agent that runs as you can still edit `~/.deai/trust.json` and `~/.deai/trusted/` or drive the system window itself —
that is outside the boundary. Trust protects against code that arrives through the space folder, git and mockup pages,
not against a local process with your rights.

A module may also carry `agent.md` next to `module.json`: line 1 `# Title`, line 2 one line about the module, then notes
for agents. The canvas never copies it into `AGENTS.md`: `GET /api/agent-guide` lists its path (relative to the space
folder) with the module's trust state, marked as data written by the space's authors. Built-in modules use the same file as
the topic `module-<id>`.

## 6. Trying it locally

Create the folder in a test space, open Settings → Modules, trust it, connect it and press «Check»: the verdict of your
`check` is shown on the card. After every edit, trust again — that is the point.

## 7. Tools and actions (`api: 2`)

Besides a role, a module with `"api": 2` can add **tools** (a button in the island that opens a right-hand panel with the
module's own HTML) and **actions** (items in ⌘K and in the «⋯» menus of a task or an iteration). `api: 2` needs a Deai
Canvas that knows it; an older one refuses the manifest. **Tools** show only in the working canvas of a task, in «Layout»
(the island, up to 3, and ⌘K). **Actions** show in ⌘K on an open task, in «Layout» and in «Overview» alike, in the «⋯» menu of
a task card (the task list and the home screen) and in the iteration dropdown. Neither is in a published preview. A small working example is
`docs/modules/examples/page-notes/` («Page notes»): copy the folder to `<space>/modules/page-notes/`, trust it, enable
it. It is also the fixture of the live test of this contract.

### The manifest: `tools` and `actions`

```json
{"api": 2, "id": "page-notes", "name": "Нотатки сторінок", "version": "1.0.0", "roles": [],
 "tools": [{"id": "notes", "label": "Нотатки", "icon": "doc", "panel": "panel/index.html", "key": "N"}],
 "actions": [{"id": "summary", "label": "Нотатки задачі", "where": ["palette", "task"]}]}
```

**`tools`** — a list of 1 to **4** objects (an empty list or more than 4 is refused). Fields:

| field | rule |
|---|---|
| `id` | `[a-z0-9][a-z0-9-]{0,39}`, unique in the module |
| `label` | a non-empty string of at most **40** characters (the text of the button, its tooltip and the ⌘K item) |
| `icon` | a name from the core's icon set (`app/icons.js`); an unknown name is refused. Your own SVG is not supported yet |
| `panel` | a relative path to an `.html` file of **2 to 4 segments** (the panel always lives in a subfolder, not next to `server.py`); a regular file of at most **256 KiB**; each segment `[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}` (no hidden names, no `..`) |
| `key` | optional: one ASCII letter, case-insensitive (it is upper-cased). A core letter (**C, I, H, M, P**) or a letter repeated by two tools of the **same** module **refuses the manifest** (`tools[i].key: 'C' is reserved by Deai` / `duplicate 'N'`). The same letter claimed by tools of **different** modules: neither gets a key (⌘K still works) |
| `page` | optional: a non-empty list without repeats of `read`, `mark`, `change`, `listen` — what the tool may do with the mockup page through `deai.page` (see «Working with the mockup»). `mark`, `change` and `listen` require `read` (`tools[i].page: "change" requires "read"`); an unknown value is refused (`unknown permission 'x'`). **Needs Deai 0.39 or newer**: an older Deai refuses a manifest with `page` as an unknown key. Changing it changes the bytes of the folder, so trust is asked again |
| `frame` | **not supported — use `page`**: a manifest with this key is refused with `tools[i].frame: not supported — use "page"` (code inside the mockup is not possible — see section 8) |

Any other key is refused (`unknown key`). The island shows the built-in tools first, then up to **3** tools of modules (in
the order of the space's modules); the rest are reachable through ⌘K and the key only.

**`actions`** — a list of 1 to **8** objects: `id` (as above), `label` (at most **60** characters), `where` — a non-empty
list without repeats of `palette` (⌘K), `task` (the «⋯» menu of a task card), `iteration` (the iteration dropdown), and an
optional `timeout_s`, an integer from 1 to 150 (default 15). Any other key or value is refused.

A refusal reads like `tools[0].icon: unknown icon 'nope'` or `tools: requires api 2` (with `api: 1` the keys `tools` and
`actions` are refused); the module's card in Settings shows the reason and nothing of the module runs. A module with only
tools and actions has `"roles": []` — the key cannot be left out.

### The tool panel

The panel is the module's HTML in an `<iframe sandbox="allow-scripts allow-forms">` **without** `allow-same-origin`: it
has an opaque origin.

* No cookies, no `localStorage` or other storage of the canvas, no access to `/api/*` or to the shell itself.
* The network is closed by the content policy (`connect-src 'none'`, also `frame-src`, `form-action`, `object-src`):
  `fetch` and `XMLHttpRequest` are rejected. Anything that needs the network or secrets is done by the module's
  `server.py`; the panel reaches it through `deai.call`.
* The server serves only files from the **panel's folder** (the folder of the `panel` path: `panel/` for
  `panel/index.html`) and only with the extensions `.html`, `.js`, `.css`, `.svg`, `.png`, `.json`, `.woff2`; `server.py`,
  `module.json` and the rest of the folder are unreachable. Link scripts and styles with relative paths
  (`<script src="notes.js">`); inline ones are allowed too. Files come from the trusted snapshot, not from the live folder.
* The core adds `kit.css` (the `dk-*` classes) and `bridge.js` (`window.deai`) to every panel page itself — there is
  nothing to include. If the panel navigates elsewhere or loads another page, the tool is closed.
* There is one right-hand panel: comments, the inspector and a tool panel push each other out. A tool is closed by «×»,
  `deai.close()`, the same key again, or leaving «Layout».

**`window.deai`** (a bridge over `postMessage`; replies are accepted only from the shell):

| call | what it gives |
|---|---|
| `await deai.ready` | the first `init`: `{context, theme, vars}` |
| `deai.hello()` | the handshake (`bridge.js` does it itself) |
| `deai.context()` | `{space: {id, name}, task: {id, name}, iteration: {id, name} \| null, page: {id, title} \| null, lang, theme}` |
| `deai.selection()` | the element selected in the inspector on the current page: `{selector, tag, styles}` or `null` |
| `deai.call(fn, args)` | a `tool_*` function of the module (below); resolves with its result |
| `deai.toast(text)` | a shell toast «Tool name: text» (at most 200 characters) |
| `deai.close()` | close the panel |
| `deai.on(event, fn)` | subscribe; returns an unsubscribe function |

Events: `init` (together with `ready`), `context` (the task, iteration or page changed — `data` as in `deai.context()`),
`theme` (`{theme, vars}`: the theme or the space colour changed), `close` (the panel is about to be closed). A change of
the inspector selection is not an event — read `deai.selection()` when you need it.

A rejected promise is an `Error` with a `code`. Bridge-local codes: `too-big` (a message over **64 KiB**), `busy` (more than
**64** pending requests in the panel, or more than **4** concurrent `call`s), `timeout` (the shell did not answer in
**60 s**; the pending request is then dropped), `unknown-method`, `bad-message`, `bad-args`. For `call`, the codes of the
server that can reach the panel: `unknown-module` (the module is gone or trust was revoked), `unknown-function`,
`module-busy`, `check-timeout`, `module-error`, `isolated`, `bad-request`, `body-too-large`. A `ModuleError` of the module
with a code unknown to Deai arrives as `module-error` (only the codes of the core's own table pass as they are). A `call` sent before the panel was closed **still
runs**, but its result is dropped.

**Styles.** `kit.css` gives `dk-btn` (+ `dk-btn--primary`), `dk-field` (input, textarea, select), `dk-list` and `dk-row`,
`dk-muted`, `dk-empty`. The theme and colours of the shell arrive in `init` and `theme`: the bridge sets `data-theme` and
the CSS variables (`--s1`, `--s2`, `--s3`, `--line`, `--line2`, `--hi`, `--mid`, `--dim`, `--sel`, `--sel-hover`,
`--on-sel`, `--bad`, `--r`, `--r-sm`, `--h-ctl`) on `<html>`. Your own styles are fine, preferably built on these variables.

### Working with the mockup (`deai.page`)

A tool that declares `page` permissions can look at the mockup page, mark elements, change its look for a moment and watch
what the person does. The module's code never enters the mockup: the panel stays in its sandbox and asks the **core helper**
(`app/page-agent.js`), which works on the page of the frame from the shell's side. Every method returns a `Promise`; a
failure is an `Error` with a `code`.

**Permissions.** What is not declared is refused with `not-allowed`.

| permission | methods |
|---|---|
| `read` | `info`, `query`, `get`, `snapshot`, `pick`, `cancelPick`, `reveal` |
| `mark` | `mark`, `unmark`, `clearMarks` |
| `change` | `setStyle`, `setClass`, `setAttr`, `setText`, `revert`, `revertAll` |
| `listen` | `listen` (and the events `page-click`, `page-hover`) |

`mark`, `change` and `listen` need `read`: without it the module never gets an element reference. The trust dialog lists
the permissions in a block of their own.

**`Node`.** `{ref, tag, id, cls, text, rect: {x, y, w, h}, visible, attrs?, styles?}`.

* `ref` — an opaque string such as `"r…-17"`: valid until the page reloads, the same for the same element. A stale one is `stale-ref`.
* `text` — the element's **own** text (not its children's), whitespace collapsed, at most **300** characters; `cls` — at most **200**.
* `rect` — in document coordinates (scroll included).
* `visible` — the element has a box (width and height above 0) and its computed `display` is not `none` and `visibility` is
  not `hidden`. It says nothing about `opacity`, covering by other elements or being scrolled out of view.
* `attrs` (only with `attrs: true`) — the attributes, at most **30**, each value at most **300** characters; the core's own
  `data-deai-*`, `data-canvas-*`, `data-comment-*`, `data-h2d-*`, `data-dc-*` are never shown.
* `styles` — only the computed properties you asked for in `styles: [...]` (at most **24** names, values at most 500
  characters; a name is a standard property or a custom property `--x`).
* `snapshot` nodes also carry `parent` — the `ref` of the parent element, `null` for `<body>`.

Nodes of the core's overlays and `script`, `style`, `template`, `noscript` never appear in results.

**Read (`read`)**

| call | result |
|---|---|
| `deai.page.info()` | `{page: {id, title}, viewport: {w, h}, scroll: {x, y}, size: {w, h}}` |
| `deai.page.query(selector, {limit, styles, attrs})` | `Node[]`; `limit` defaults to **100**, at most **500**; a selector the browser rejects is `bad-selector`. The answer is also held to **2 MiB**: when the nodes would not fit, the list simply ends early — there is no `truncated` flag in `query`, so ask for a smaller `limit` or fewer `styles`/`attrs` if you need to be sure |
| `deai.page.get(ref, {styles, attrs})` | `Node` |
| `deai.page.snapshot({styles, attrs, maxNodes})` | `{info, truncated, nodes}` — a flat list in document order; `maxNodes` defaults to **2000**, at most **4000**; the answer is at most **2 MiB**; `truncated: true` means the list stopped early, either at `maxNodes` or because the next node would not fit in the 2 MiB (the rest of the page is not in `nodes`) |
| `deai.page.pick()` | the person clicks an element in the mockup → `Node`; `null` on Esc, on `cancelPick()`, on another `pick`, or on a click that hits nothing. It ends when the panel closes (the reply is dropped because the panel is gone). There is no bridge timeout; the click does not reach the page and marks are hidden while picking |
| `deai.page.cancelPick()` | `null`; ends the current `pick` with `null` (nothing happens when no pick is running) |
| `deai.page.reveal(ref)` | scroll to the element (centered) and a short flash of its mark, or of a temporary frame (at most 20 of those at once; past that only the scroll). `prefers-reduced-motion` turns the smooth scroll and the animation off. Resolves with `null` |

`pick`: **Esc** cancels it — in the canvas, in the mockup and in the panel (the bridge sends `cancelPick` itself when Esc
is pressed in the panel while a pick is pending). `deai.page.cancelPick()` does the same from your own button.

Selector rules (`query`): a non-empty string of at most **300** characters, no backslash escapes, at most **8** parentheses
and at most **4** functional pseudo-classes (`:has`, `:is`, `:not`, `:where`); a violation is `bad-args`.

**Mark (`mark`)**

| call | result |
|---|---|
| `deai.page.mark(ref, {tone, label})` | `markId` (a string); `tone` is `error`, `warn`, `ok` or `info` (default `info`); `label` at most **60** characters (longer is cut with «…») |
| `deai.page.unmark(markId)` | — |
| `deai.page.clearMarks()` | — |

The core draws marks in one host over the page, outside the page's layout, with `pointer-events: none` — clicks reach the
page. A mark follows its element on scroll, resize and changes of the document; an element that left the document hides its
mark. At most **300** marks per panel (`too-many`). Marks never go into «To Figma».

**Change (`change`)**

| call | result |
|---|---|
| `deai.page.setStyle(ref, {prop: value \| null, …})` | `{id: string \| null, applied: [prop], rejected: [prop]}`; 1 to **40** properties, values at most **500** characters; `null` removes that property; an empty string is `bad-args` (use `null`) |
| `deai.page.setClass(ref, {add: [], remove: []})` | `{id: string \| null}`; names `[A-Za-z_-][\w-]{0,99}`, at most **20** per list |
| `deai.page.setAttr(ref, name, value \| null)` | `{id: string \| null}`; `null` removes the attribute; a value is at most **300** characters |
| `deai.page.setText(ref, text)` | `{id: string \| null}`; only on an element without child elements (`not-leaf`); at most **2000** characters; set as plain text |
| `deai.page.revert(id)` | `{reverted, skipped}` |
| `deai.page.revertAll()` | `{reverted, skipped}` |

* Styles are set inline with `!important`, like the tuner. A value the browser does not accept, or one that would make the
  page load something (`url(`, `image(`, `image-set(`, `cross-fade(`, `element(`, `src(`, `attr(`) or that contains a
  backslash, comes back in `rejected` and the old value stays; so does a value that carries `!important` (the helper sets the
  priority itself). Custom properties (`--x`) are allowed.
* Attributes allowed: `role`, `hidden`, `title`, `alt`, `lang`, `dir`, `tabindex`, `disabled`, `placeholder`, `open`,
  `aria-*` and `data-*` (not `data-deai-*`, `data-canvas-*`, `data-comment-*`, `data-h2d-*`, `data-dc-*`). A name is lowercase
  ASCII letters, digits and hyphens only, starting with a letter; anything else is `not-allowed`, as is any other name —
  `on*` handlers, `src`, `href`, `srcdoc`, `style`, `class`, `id` — is `not-allowed` (`style` and `class` have their own
  methods). No markup from a module ever reaches the document: not through text, not through a value.
* Restoring (`revert`, `revertAll`): the element's inline `style` is put back byte for byte only when the page did not change
  it after your change. Otherwise each declaration is restored on its own, so the text may be re-serialized (`color:red`
  becomes `color: red;`). A shorthand written with CSS variables (`margin: var(--g)`) is restored as a whole only when the
  page left all its parts alone; anything the canvas cannot restore safely is left as it is and counted in `skipped`. Pass
  values without `!important`: the helper sets the priority itself.
* At most **500** active changes (`too-many`). The count is per journal entry: every successful change call that returns a
  non-null `id` is one entry, however many properties or declarations it touched.
* `id` is `null` when nothing changed, so there is nothing to revert and no slot is used: `setStyle` when every value was
  rejected; `setClass` when every name is already as asked; an
  identical `setAttr` or `setText`. `setStyle` with a value the element already has still returns an `id` (the entry holds
  that property until it is reverted).

**What is temporary.** Marks and changes live while the panel is open and the page is not reloaded. They are reverted when:
the panel closes (×, `deai.close()`, the tool's key, another right-hand panel, leaving «Layout», the clean mode, a change
of space, trust taken back); the page reloads or another page opens (the document and the journal go together); you call
`revert(id)` or `revertAll()`. Nothing is written to files, previews, snapshots or history. After a reload the helper does
**not** reapply changes: a tool that wants them listens to `page` and applies them again.

**«Still ours».** A revert puts the old value back only where the current value is still the one your change set. If the page's
own script (or the tuner) changed it after you, the value is left alone and counted in `skipped`. Reverting an entry out of
order (`revert(id)` of an older one while newer ones touch the same thing) hands your layer down to the newer entry when the
layers were contiguous — the newer entry then reverts to what was before yours; if something else changed the value between
the layers, the older entry is `skipped`. When nothing changed since your change, the page's own `style` string is restored
exactly as it was (including `var()` inside shorthands), and an empty `style=""` or `class=""` that your change created is removed.

**Events** (subscribe with `deai.on`):

| event | data | when |
|---|---|---|
| `page` | `{page: {id, title}}` or `{page: null}` | the page is ready for requests: right after `init` when a page is already loaded, and after every later load (any `read` tool gets it, `listen` is not needed). Old refs, marks and changes are invalid after it. `{page: null}` means the mockup has no live page for the helper any more (another origin, still loading, clean view, canvas mode): `deai.page.*` calls answer `no-page` until the next `page` with a page |
| `page-click` | `{node: Node, x, y, button, alt, shift, meta, ctrl}` | the person clicks (`listen({click: true})`); the click is not intercepted; not sent during `pick` |
| `page-hover` | `{node: Node}` | the pointer moves onto another element (`listen({hover: true})`); at most 10 per second and only when the element changes |

`page` is also delivered to a handler that subscribes after it arrived (the latest one), asynchronously and once; other events are not replayed.

Only the person's real input is reported: events the page's scripts dispatch themselves (`el.click()` and the like) are not.
`deai.page.listen({click, hover})` switches each subscription on or off; both are off by default. A subscription ends with
the page: call `listen` again after every `page` event.

**Errors.** `not-allowed` (no permission, or a forbidden attribute), `no-page` (no live mockup page: «Overview», between
loads, a link that left the mockup), `stale-ref`, `bad-selector`, `bad-args`, `not-leaf`, `too-many`, `busy` (more than 64
pending requests in the panel), plus the bridge codes of the previous section. The texts are English, for the module's
author.

**Caveats.**

* `data-*` attributes can change what the page's scripts do if they read them.
* A custom property carries a string that the page's CSS may use anywhere (inside `calc()`, `content`…).
* `visible` is a box test, not a visual one (see `Node`).
* «To Figma» takes the page as it looks, with your temporary changes; marks are not included.
* A panel request is at most 64 KiB (as before); keep arguments short.

**Example.** `docs/modules/examples/contrast/` («Contrast») uses all four permissions:

* `read`: takes a `snapshot` with `color`, `background-color`, `font-size` and `font-weight` (and the attributes), finds text
  under the WCAG ratio, fields without a label and images without a description; `reveal`s the element of a row; `pick`s an
  element to find its row (the same button cancels a pick with `cancelPick`).
* `mark`: puts a mark on every finding and swaps it for a green one after a fix; `clearMarks` before each check.
* `change`: «Try a fix» sets a readable `color` with `setStyle`; the temporary changes are counted and `revertAll` undoes them.
* `listen`: after every `page` event it calls `listen({click: true})`, and a click in the mockup highlights the row of the
  clicked element (or of its nearest ancestor with a finding).

It checks the page again on every `page` event. The logic is plain JavaScript in the panel; its `server.py` has only `check`.

### The functions of `server.py` for tools and actions

A module with `tools` or `actions` has `check(ctx)` like any other; the rest is below. `ctx` is the same as for roles
(section 3), including `ctx["cache_dir"]` for the module's files and `ctx["ModuleError"]`.

* **`tool_<name>(ctx, args)`** — the panel calls `deai.call("tool_<name>", args)`. The core lets through only top-level
  functions matching `tool_[a-z0-9_]{1,40}`: `check`, `action_*`, the functions of roles and any other names are
  unreachable from a panel. Any `tool_*` function is available to any panel of the same module; `args` is what the panel
  passed (it may be `None`). The result is any JSON up to **256 KiB** (otherwise `module-error`: `result is not JSON` or
  `result is too big`). The timeout is **15 s** (`check-timeout`). At most **4** calls of `tool_*`/`action_*` of one module
  run at once (otherwise `module-busy`, 429); a thread that outlived its timeout still counts until it finishes. A code of
  your own that the core does not know reaches the panel as `module-error`. ⚠️ The result of a tool is **not** scrubbed of
  the module's own secrets: never return secrets to a panel.
* **`action_<id>(ctx, target)`** — required for every action of the manifest: without it the module is broken
  (`server.py: no callable action_…()`). Hyphens of the action `id` become underscores (`my-action` → `action_my_action`).
  `target` is `{"from": "palette" | "task" | "iteration", "task": {"id", "name", "dir"}, "iteration": {"id", "name"} | None}`;
  `dir` is the absolute path of the task folder, `iteration` is set only when the action was called from the iteration
  dropdown. The result is `{"ok": bool, "text"?: str, "url"?: str}`; `ok` must be a real `bool`, otherwise `module-error`.
  The core normalizes it: `text` loses control (Cc) and format (Cf) characters, except the newline, and is then cut to **300**; `url` must be `http(s)://`,
  at most **2048** characters, with a host, without spaces, invisible characters, `\` or `user@` (an unfit address is dropped
  silently); other keys are dropped. The shell shows a toast: the text of the reply (or «Done»), and for `ok: false`
  «Action name: text»; with a `url` the toast has an «Open» button. The timeout is the action's `timeout_s` or **15 s**;
  starting the same action again while the first is still running is ignored.
* The body of `POST /api/module-tool` and `/api/module-action` is at most **64 KiB**: a larger one is refused with `413`
  **without being read**, so a large `fetch` body may surface as a network error. Pass short arguments from the panel.

Storage in `ctx["cache_dir"]`: create the folder yourself (`os.makedirs(…, mode=0o700, exist_ok=True)`), write atomically
(a temporary file plus `os.replace`), and never build paths from strings you do not control (a task id, a page title) —
keep them as keys inside a JSON file, as `page-notes` does.

### Trust for tools

What is trusted are the exact bytes of the **whole folder**, including the HTML, scripts and styles of the panel: editing
any file means trusting again. The trust dialog lists the tools (name and icon) and the actions (name) of the module next to
the list of files. A newer version that did not get trust (the folder changed after trust, or it breaks a folder rule) does
not run: the module keeps running from its last trusted snapshot — its `server.py`, panels and actions — so its tools do not
disappear. The sandbox of a panel is a boundary of stability and of an explicit API, not protection from the module itself:
its `server.py` runs with your rights after trust, so the security boundary is the trust dialog.

## 8. Limits

What a module can and cannot do — three layers.

1. **The frame is fixed.** Only a release of Deai changes it; a module can neither replace, hide nor move: the shell (the
   tab row, the task bar, the left page panel, the right panel as a place, the island, ⌘K, the key help), the data model
   (`tasks.json`, `iterations.json`, `pages.json`, `flow.json`, `space.json`, the preview manifest), the «Layout» and
   «Overview» modes, the camera, the snapshots, the inspector, the comments panel, the preview wrapper, Settings, updates,
   the trust model, the `AGENTS.md` generator and the keys of the core.
2. **Extension points.** A role (functions of `server.py` under the role's contract), the `settings` fields, a **tool**
   (an icon, a name, its own panel, an optional key) and an **action** (a name and a function) — all in one manifest if
   needed.
3. **«No».** Your own buttons or markup outside the tool panel; changes to the layout, the theme, the colours or the keys of
   the core; scripts in a published preview (except the adapter of the `comments` role); writing directly into the core's
   data formats (only through the canvas's public API, like an agent); other modules' secrets (`ctx["secrets"]` holds only
   your own); replacing built-in tools (comments, the inspector — a module adds its own beside them). A wish that runs into
   a «no» is a request to the core, not a module.

**Code inside the mockup — no; the core helper instead.** A module's code never runs in the mockup page: the mockup
document has the origin of the canvas itself, so a script there could do everything the canvas can (publish, GitLab, tasks),
and it cannot be restricted on the same origin. What a tool gets instead is the core helper behind `deai.page` (section 7,
«Working with the mockup»): reading the page, marks drawn by the core outside the page's layout, temporary changes that are
all reverted, and the person's clicks — each behind a permission the person sees in the trust dialog. Working illustrations of these limits are `docs/modules/examples/page-notes/` and
`docs/modules/examples/contrast/`.
