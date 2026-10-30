# Writing your own module

For Deai Canvas **0.8.0**. A module adds one capability — a *role* — to a space: publishing previews, design-system
tokens, team comments, syncing mockups with git. Built-in modules live in `app/modules/`; **your own modules live in the space**, in
`<space>/modules/<id>/`, so they travel with the space through git. Their code runs on your computer only after **you**
trust it.

**Коротко (uk).** Свій модуль — тека `<простір>/modules/<id>/` з `module.json` і `server.py`. Канвас його бачить одразу,
але код не виконує, доки людина не довіриться: «Підключення» → «Довіритись…» → діалог із файлами → «Довіряю» → системне
вікно ОС. Довіра — до точних байтів: канвас копіює їх у знімок `~/.deai/trusted/<відбиток>/` і виконує лише знімок. Зміна
теки не діє до повторної довіри. Агент може написати модуль, але довіритись — ні; межа — код, що приходить крізь теку
простору, git і сторінки макетів, а не локальний процес із вашими правами (він може сам правити `~/.deai/trust.json`).

## 1. The folder

```
<space>/modules/acme-publish/
  module.json      the manifest
  server.py        the functions of the role (standard library only)
  adapter.js       browser files — only for the comments role, listed in "client"
```

* The folder name is the module `id`: `[a-z0-9][a-z0-9-]{0,39}`, the same as `id` in the manifest. A subfolder with any
  other name, or without a `module.json`, is not a module and is ignored.
* An id that a built-in module already has is skipped (the Connections screen says so). At most 32 own modules per space
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

* `api` — `1`. `name` and `version` — strings shown to people.
* `roles` — the roles the module provides: `publish`, `tokens`, `comments`, `vcs` (called by the core today);
  `tracker`, `dashboard`, `notify` are reserved names the core does not call yet. One provider per role per space.
* `publish_target` (publish only) — `folder` (default) or `url`. The canvas serves the local copy of a published preview
  (`/published/…`) only for the built-in `static-publish`.
* `client` (comments only) — the browser files; see [comments.md](comments.md).
* `settings` — what the module asks for: `text`, `path`, `bool`, `select` (with `options`) or `secret`; `required`,
  `default` and (secret only) `public` as in the built-in modules. Settings are stored in the space's `space.json`;
  secrets — in `~/.deai/secrets.json`, never in the space.

A manifest that breaks these rules cannot be trusted: the card says why, and nothing of the module runs.

## 3. `server.py`

Every module has `check(ctx) -> {"ok": bool, "error"?: str, "detail"?: str}` — a read-only health check (5 s). A role
adds its own functions:

| role | functions |
|---|---|
| `publish` | `publish(ctx, build_dir, task)` |
| `tokens` | `tokens(ctx)` |
| `comments` | `client_config(ctx)`, `list(ctx, channel)`, `resolve(ctx, channel, id, reason)` |
| `vcs` | `status(ctx, target)`, `push(ctx, target, src, meta)`, `pull(ctx, target, dst, opts)`; optional `validate(ctx, target)`, `mirror_dir(ctx, target)` — see [The `vcs` role](#the-vcs-role) |

A module that lacks `check` or a function of its roles shows as broken (the optional functions of `vcs` may be missing). The
exact return values are those of the built-in modules — read `app/modules/static-publish/` (`folder`),
`app/modules/vercel-publish/` (`url`), `app/modules/css-tokens/`, `app/modules/git-sync/` (`vcs`) and
[comments.md](comments.md).

`ctx` is `{"space": {id, path}, "settings": {…}, "secrets": {…only this module's…}, "folder_ok": f, "ModuleError": class,
"cache_dir": path}`. Raise `ctx["ModuleError"](code, "message")` for a failure; texts are cut to 300 characters and scrubbed
of your secrets. A code the core knows (`bad-folder`, `vcs-offline`, for example) is passed on as it is; any other code is
reported as `module-error`. `cache_dir` is the path `~/.deai/cache/<space id>/<module id>` (under `DEAI_HOME`, when that is
set), a place for what the module can rebuild — mirrors, downloads. The core only computes the path and never creates
the folder: create it yourself when you need it (`os.makedirs(path, mode=0o700, exist_ok=True)`).

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
  every reply — does nothing and answers `reason: "autosync-off"`. Declare them in the manifest to get these features.

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

## 4. Trust

1. Put the folder into `<space>/modules/`. The Connections screen shows the module with «own» and «Needs trust»; its
   code has not run.
2. «Trust…» opens a dialog: what the module asks for, every file with its size, the fingerprint. «Trust» then asks the
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
5. «Revoke trust» (card panel or dialog) stops the code; `space.json` and the settings stay. A module that is on in the
   space but not trusted on this computer keeps its role «on paper»: the role reports an error instead of falling back
   to another provider.
6. In the new-space wizard your module is marked «own». Until you trust it, its option is disabled and has a «Trust…»
   button (the same dialog, the same system window); a folder that cannot be trusted shows the reason instead of the
   button. If a teammate already turned it on in `space.json`, it stays selected; the settings step writes nothing for it
   and says it is waiting for trust. A module whose folder has changes can be selected — the previous version runs; trust
   the new one on the Connections screen.

The module's top level gets **5 s** to load; a module that hangs is shown as broken (its thread lives until the server
restarts, and if it loops it may slow the canvas down). Browser code of a trusted `comments` module runs in canvas pages and published previews with the canvas's
own access — that is part of what you trust.

## 5. The agent

An agent can write the folder, read `GET /api/modules?space=<id>` and `GET /api/module-trust?space=<id>&id=<module>`, and
— after **you** trust the module — connect and configure it (`POST /api/module-enable`, `/api/module-settings`). It cannot
trust: `POST /api/module-trust` needs the canvas page in a browser (`Origin` and `Sec-Fetch-Site: same-origin`; a script
or `curl` gets `403 trust-needs-ui`) and then the system window. It may revoke trust (`POST /api/module-untrust {space, id}`).
Ask the person to trust the module.

An agent that runs as you can still edit `~/.deai/trust.json` and `~/.deai/trusted/` or drive the system window itself —
that is outside the boundary. Trust protects against code that arrives through the space folder, git and mockup pages,
not against a local process with your rights.

## 6. Trying it locally

Create the folder in a test space, open «Connections», trust it, connect it and press «Check»: the verdict of your
`check` is shown on the card. After every edit, trust again — that is the point.
