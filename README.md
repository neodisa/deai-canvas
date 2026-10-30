# Deai Canvas

**A local workspace for prototypes made with AI.** An agent (Claude Code or any other)
writes HTML mockups; Deai Canvas turns them into something you can review and ship:
iterations, a bird's-eye overview of every screen, user-flow maps, a design-token
inspector, comments addressed straight to the agent, and password-protected preview
links for your team.

> **Status — v0.8.0 (private; extracted from an in-house tool, source 1.55.0 @ `796b3df`).**
> Spaces (several projects on one machine) and the first **modules** are in: publishing to
> a folder or to your own Vercel account, design-system tokens from a CSS file, team
> comments on your own Supabase (or any service, through a small module), and **git sync** —
> iterations to and from any git repository, GitHub or GitLab or your own server — work in any
> space. A **wizard** creates a space and takes you through its modules and a first task, and a
> **Connections** screen manages the modules afterwards — no command line. A few integrations
> (publishing and comments of the legacy space, team dashboard, tracker statuses, team chat notifications) are still wired for the original
> setup and only run in a migrated legacy space; they are being turned into optional per-space
> modules. A space can carry **its own modules** in `<space>/modules/`; their code runs only
> after you trust it. See *Roadmap*.

## What it does

| | |
|---|---|
| **Iterations** | Every iteration is a frozen, editable copy of the mockup; compare, rename, duplicate. |
| **Pages & states** | A tree of pages, folders and states (any depth), with a filter and drag-and-drop. |
| **Overview** | All pages of an iteration as a zoomable grid of full-page snapshots (Playwright), re-shot incrementally when a page changes. Desktop / tablet / mobile widths. |
| **Flow** | Arrange screens as a user flow with arrows (`flow.json`). |
| **Inspector & tuner** | DevTools-style overlay: spacing, typography, colours, a ruler, and — if you connect your design tokens (a CSS file, see *Modules*) — whether each value is on-system. The tuner turns tweaks into a change request for the agent. |
| **Comments** | Pin comments on any element (via [CommentLayer](https://github.com/neodisa/CommentLayer)); a local channel for the agent, an optional team channel on your own service — Supabase or anything else — through a `comments` module (canvas, Overview, published previews, the agent's `inbox`). See *Comments*. |
| **Agent status** | Shows what the agent is doing right now and which pages it just changed. |
| **Publish** | Build a static preview of the iterations you marked and publish it to a folder or to your own Vercel account (any space), optionally behind a password gate. |
| **Git sync** | Send an iteration to a git repository (GitHub, GitLab, your own server) and pull a colleague's changes back as a new iteration; the state is a dot in the task bar. Any space, through the `git-sync` module. See *Git sync*. |
| **Tasks** | A home screen with all your tasks: search, sort, filters. |
| **New-space wizard** | Four steps — space, modules, settings, first task (a blank page, an existing mockup folder, or a phrase for the agent). The same wizard opens on the first run and for «New space…». See *Spaces*. |
| **Connections** | A page per space to connect, configure, check, replace and turn off modules (publishing, team comments, git sync, design-system tokens) from the UI. See *Modules*. |
| **App** | Installable as a PWA (own window and Dock/taskbar icon); macOS launcher with auto-start. |

UI in English and Ukrainian.

## Quick start

Requirements: Python 3.9+, Chrome or Edge. Optional: Node.js 20+ (snapshots via Playwright;
the in-house Vercel CLI publishing of a legacy space — the Vercel module needs no Node).

```bash
cp tasks.example.json tasks.json      # edit paths: where your mockups live
python3 app/serve.py                  # http://localhost:8765/app/
```

Each task points to a folder with `iterations/it1/<page>/index.html`; `flows/demo` is a
small example. Snapshots for the Overview:

```bash
npm install && npx playwright install chromium
```

Tests: `npm test` (unit, Python) and `npm run test:live` (real Chromium). The Python
suites (`tests/`, `bin/`, `app/`) were run for 0.8.0 on Python 3.9.6, the oldest supported version, and on Python 3.13.

## Spaces

A **space** is a company, a client or your own work: a folder on disk with a `space.json` (name,
colour, the enabled modules and their settings) and the space's tasks. The spaces of a machine are
listed in `~/.deai/spaces.json`; the space chip in the top bar switches between them.

**Creating a space — the wizard.** The welcome screen (no spaces yet) and «New space…» in the
space menu and in ⌘K open the same four-step page; the welcome screen also has «Open an existing
space folder», which starts with the cursor in the folder field.

1. **Space** — name, colour and folder (a text field; `~` is expanded). A folder that already is a
   space — say, one shared through git — is recognised: it keeps its own name and colour and brings
   its tasks and modules. The space is created here, for real, so closing the wizard at any later
   step leaves a working space; «Back» to this step edits its name and colour (the folder cannot
   change), and «Cancel» before the creation returns to where you were.
2. **Modules** — one choice per role (publishing, team comments, git sync, design-system tokens): a
   module, or «No module» with what that means. A choice that replaces the current provider says
   «instead of …». Nothing is required, and nothing is written yet; no git module is pre-selected.
3. **Settings** — the fields of each chosen module, the same as in the Connections side panel
   (secrets are written, never shown). One pass writes the choices and checks each module; if
   something fails, the wizard stays on the step with the reason in the card. If an agent changed a
   role while you were choosing, that module is not written and its card says so.
4. **First task** — a blank page, **an existing folder with an `index.html`** (the server copies it
   into the first iteration; the original is untouched), or a phrase to tell your agent. «Skip» goes
   to the tasks of the new space.

Unsaved settings are asked about before «Back» or «Close the wizard»; Esc does not close the page.
Not part of the wizard: picking a folder with the system dialog, and resuming an unfinished wizard
after a restart (what was created stays, and the rest is on «Connections»).

**A task from an existing folder** is also available over the API: `POST /api/task-new` with
`from` (see *Module API* below). It works in a space without integrations only; symbolic links,
`.git` and `node_modules` are not copied, and a folder of more than 2000 files or 200 MB is refused.

## Modules

A **module** is a folder — built in at `app/modules/<id>/` or a space's own at
`<space>/modules/<id>/` — with `module.json` (manifest and the settings
it asks for) and `server.py` (functions for its role). A *role* is an interface the core
calls: `publish`, `tokens`, `comments` and `vcs` today; `tracker`, `dashboard`, `notify`
are reserved. One provider per role per space.

**Connecting a module — the Connections screen.** Open the space menu (the space chip in the
top bar) → «Connections…», or press ⌘K and pick «Connections of the space …»; in a space
without integrations the head of the Tasks page also has a «Connections» button. The page lists
the modules of the space by role (Publishing, Team comments, Git sync, Design-system tokens), says who
provides each role now, shows the state of each module and, for one that fails, the reason in
plain words. «Connect» and «Configure» open a side panel with the module's settings; secrets
are written there but never shown again — the panel only says «set» or «not set», and
«Erase» removes one. «Check» asks the module whether it works. If the role is already taken
(a space without integrations publishes with `static-publish` by default), the screen asks
«… is currently handled by “…”. Connect “…” instead?» and swaps the two in one step;
«Turn off» keeps the settings and secrets, so the module can be connected again. No
command line is needed.

**Own modules.** Put a module folder into `<space>/modules/<id>/` (by hand, from git, or ask the agent to write one —
see `docs/modules/authoring.md`). Connections shows it with «own» and «Needs trust»; nothing of it runs yet. «Trust…»
lists its files and settings, and «Trust» asks the operating system to confirm in its own window. The canvas then runs
a read-only snapshot of exactly those bytes (`~/.deai/trusted/`); a later edit of the folder waits for a new trust
(«The folder has changes»), and «Revoke trust» stops it without touching `space.json`. A module a colleague turned on
in `space.json` stays «on, but not trusted» on your computer until you trust it. An agent can write and connect an own
module but cannot trust it — ask the person. Trust guards against code that arrives through the space
folder, git and mockup pages, not against a local process with your rights: an agent that runs as you could still edit
`~/.deai/trust.json` or drive the system window itself (see `docs/modules/authoring.md`, *The agent*).

**Through the agent or a script.** Everything the screen does is the HTTP API (see *Module
API* below), so an agent can connect modules for you, and the screen shows the routes of
the current space at its bottom. The `curl` examples in this README are that path.

Settings and on/off live in the space's `space.json`; **secrets** go to
`~/.deai/secrets.json` (user-only permissions), never into the space folder, so the folder
stays safe to commit. Secrets are not encrypted. One deliberate exception: the optional
`password` of `static-publish` and `vercel-publish` is baked into the built pages
(`<space>/<task>/publish/` and the published folder or site) because the preview gate is
client-side, so treat the password as readable by anyone who can open the preview and keep
those folders out of public commits.

| Module | Role | What it does |
|---|---|---|
| `static-publish` | `publish` | Builds the preview and publishes it to a folder, by default `~/deai-published/<space-id>/<task>/` — outside the space. On by default in a space without integrations. Optional `password` secret adds a client-side gate. |
| `vercel-publish` | `publish` | Publishes the preview to **your own Vercel account** through the REST API (no Node, no CLI): one project per task, a public `https://pv-<8 digits>.vercel.app` address, old deployments cleaned. Settings: `token` (secret), `team`, optional `password` (secret). Off by default. See *Publishing to your own Vercel*. |
| `css-tokens` | `tokens` | Reads design tokens from one CSS file so the inspector can tell on-system values from hard-coded ones. Setting: `file`. |
| `supabase-comments` | `comments` | Team comments in **your own Supabase project**: the pins are stored there, shown on the canvas, the Overview and in published previews, and read and closed by the agent. Settings: `url`, `key` (the public key; a secret that is allowed into pages). Off by default. See *Comments*. |
| `git-sync` | `vcs` | Syncs a task's iterations with **any git repository** — GitHub, GitLab, your own server — through the git on your computer: nothing is stored by Deai, access is your SSH key or saved HTTPS sign-in. Settings: `repo` (the default for tasks; optional), `branch` (`main`), `path` (`mockup/{task}`), `ssh_key`, `host_ip`, `autosync`. Off by default. See *Git sync*. |

**Publishing to a folder.** Mark iterations with the green dot, press *Publish*: the
result is a plain static site in the folder (host it anywhere; the task id must be
`A–Z a–z 0–9 _ -`, up to 128 characters). The canvas also serves a
sandboxed local copy at `http://localhost:8765/published/<space-id>/<task>/`. The folder
is re-checked on every publish and serve; it must not be your home folder, the tool or
space folders, or a system folder, and a folder without the `.deai-published` marker is
never overwritten.

**Publishing to your own Vercel.** `vercel-publish` needs only a token — no `vercel login`,
no CLI, no Node on the machine.

- *Token.* In Vercel: Account Settings → Tokens → create a token. If you publish into a team,
  scope the token to that team and set the `team` setting (a slug such as `<slug>`, or an id
  `team_…`); empty means your personal account.
- *Enable it* on the Connections screen (Publishing → Vercel → «Connect»: the token and,
  for a team, its slug). A space has one publisher and a space without integrations publishes
  with `static-publish` by default, so the screen asks «Publishing is currently handled by …
  Connect “Vercel” instead?» and swaps them in one step. Over the API, pass `replace: true`:
  the current publisher is turned off in the same write (without it the enable answers
  `409 role-taken`; turning the old publisher off first with `POST /api/module-disable` works
  too, but leaves the space without a publisher in between):

  ```bash
  curl -s localhost:8765/api/module-enable -H 'Content-Type: application/json' \
    -d '{"space":"<id>","id":"vercel-publish","replace":true,"secrets":{"token":"<TOKEN>"},"settings":{"team":"<slug>"}}'
  ```

  The answer carries `check`: it asks Vercel whose token this is (and whether the team is
  reachable) and creates nothing. The token is stored in `~/.deai/secrets.json` and is sent
  only to `api.vercel.com`. The core gives `check` 5 seconds, so on a slow link the enable
  can answer `check-timeout`: the module is enabled and still works, run
  `POST /api/module-check` again later. That endpoint, and `POST /api/module-settings`, run
  `check()` — a read-only request to `api.vercel.com` — **even for a disabled module** when
  you call them explicitly; nothing automatic does (opening the canvas, `GET /api/modules`
  or publishing with another module never reach Vercel).
- *Password (optional).* Set the secret `password` of the same module (the «Configure» panel,
  or `POST /api/module-settings` with `"secrets":{"password":"<PASSWORD>"}`): the pages get the
  client-side gate, and «Open» and «Copy link» append `#k=<password>`, so the link opens
  without asking. **Without a password the preview is public: anyone who has the link sees
  it** — the publish dropdown says so. With one, the gate is a courtesy, not security:
  the password is baked into the pages.
- *What it creates in your account.* One project per task, named `pv-<8 digits>` (no task or
  client name in the address). Each publish uploads the built pages, makes a production
  deployment, waits until it is ready and checks that the project's `*.vercel.app` address
  opens without signing in. The address is the shortest `*.vercel.app` alias Vercel assigns
  to the deployment — usually `https://pv-<8 digits>.vercel.app`; if Vercel assigns none, the
  module falls back to the address of the single deployment and warns that Vercel usually
  protects it. Old deployments of that project are deleted — the current one and two more
  are kept. The module deploys only into the `pv-` project recorded for the task and
  verified on every publish by id **and** exact name (a project that was renamed in the
  Vercel dashboard, or a recorded id that points to another project, is treated as foreign:
  a new `pv-` project is created with a warning). It deletes deployments only of that
  project, and deletes a project only when it created it in the same call and the publish
  then failed. Limits: 5000 files and 50 MB per file, plus whatever your Vercel plan allows.
- *Upload budget.* Files are uploaded one after another, the whole build on every publish
  (a file is sent once per content, but nothing is skipped between publishes), within 300
  seconds in total; a bigger build on a slow link fails with a timeout. If the network drops
  right after the deployment was requested, before Vercel's answer arrives, an empty `pv-`
  project may be left in your account: the module never saw the deployment id, so it cannot
  clean up. Delete it in the Vercel dashboard; the next publish starts a new project.
- *Deployment Protection.* Vercel can ask for a login even on a production address
  (Project → Settings → Deployment Protection → Vercel Authentication). The module cannot
  and does not change that; if the check fails the notice says so. Turn it off for these
  projects (or the team) if colleagues should open the link.
- With a `comments` module enabled in the space, the preview carries the comment layer and
  talks to that module's service (see *Comments*); without one it has no comments.

**Tokens from CSS.** A token is a `--name: value` declaration in a `:root`, `html` or
`[data-*theme*]` rule (Bootstrap `[data-bs-theme=dark]` too) or directly in Tailwind v4
`@theme { … }`. Values are collected per name (themes, media), `var()` is resolved within
the file, `@import` is not followed; the file must be a regular file up to 2 MiB.

**Module API.**

| Call | |
|---|---|
| `GET /api/modules?space=<id>` | catalog with status and settings; secrets only as `set: true\|false`; the space's own modules are listed too (with `custom: true`, `builtin: false`, `trust`, `record`, `runs`, `source` and, when there is a reason, `trust_error`), and `notes` names the folders of `modules/` that were skipped |
| `GET /api/module-trust?space=<id>&id=<module>` | what the trust dialog shows for an own module: files with sizes, the fingerprint, changes since the last trust, or the reason it cannot be trusted; never runs the folder's code (for a module that is already trusted, only its own snapshot is loaded) |
| `POST /api/module-trust` `{space, id, hash, lang?}` | trust an own module — exactly the version with this `hash`. Only from the canvas page in a browser (`Origin` and `Sec-Fetch-Site: same-origin`; otherwise `403 trust-needs-ui`), and only after the operating system's window confirms |
| `POST /api/module-untrust` `{space, id}` | revoke trust; `space.json` is not touched |
| `POST /api/module-enable` `{space?, id, settings?, secrets?, replace?}` | enable and configure; answers `{ok, module, check[, replaced]}` — `ok` means «processed», `check.ok` is the verdict; `replace: true` takes the module's roles from their current holders in the same write (their settings stay) and lists them in `replaced`; refused with `module-error` / `bad-manifest` if the module did not load, `400 bad-settings` if `replace` is not a boolean |
| `POST /api/module-settings` `{space?, id, settings?, secrets?}` | change settings or secrets (omit a key to keep it, `null` deletes) |
| `POST /api/module-disable` `{space?, id}` | turn off; settings and secrets are kept |
| `POST /api/module-check` `{space?, id}` | run the module's `check` |
| `GET /api/ds-tokens?space=<id>` | the space's tokens, as the inspector reads them |
| `GET /api/module-client/<id>/<file>` | a browser file of a `comments` module (only the files its manifest lists); for a space's own module `GET /api/module-client/<space>/<id>/<file>`, served from its trusted snapshot |
| `POST /api/task-new` `{id, title?, space?, from?, vcs?, …}` | create a task. `vcs` — `{repo, path?, branch?}`, the task's own repository (needs a `vcs` module in the space: `400 vcs-needs-role`; the module checks the address, branch and folder: `400 vcs-bad-target`); if `path` of that repository already holds an `index.html`, the first iteration is taken from it, and if it cannot be fetched the task starts with a blank page. `from` — an absolute path (`~` is expanded; a relative one is `from-not-found`) to a folder with an `index.html` that the server copies into the first iteration (only in a space without integrations; symlinks, `.git`, `node_modules` are not copied; ≤ 2000 files and 200 MB); the answer then carries `copied: {files, bytes, skipped_links}` — what was actually copied. Refusals: `400 from-needs-plain-space\|from-not-found\|from-no-index\|from-contains-space\|bad-request`, `409 task-dir-exists`, `413 from-too-big` |
| `GET /published/<space-id>/<task>/…` | the local copy of a folder-published preview |

```bash
curl -s localhost:8765/api/module-enable -H 'Content-Type: application/json' \
  -d '{"space":"my-space","id":"css-tokens","settings":{"file":"~/work/app/tokens.css"}}'
```

**Limitations** (accepted for 0.2; details in the spec):
- The local copy runs in a CSP sandbox, which needs `Access-Control-Allow-Origin: *`: any
  web page open in the same browser that guesses a `/published/<space>/<task>/` URL can read
  it, including the gate password. The gate is client-side, as on any static host — the
  password is not a secret.
- With a password, inner pages ask for it again in the local copy (the sandbox has no
  `sessionStorage`); on real hosting it is asked once.
- Opening the folder via `file://` is not supported, and root-absolute asset URLs in a
  mockup break under the `/published/…` subpath (they work at a domain root).
- The canvas server does not check the `Host` header (DNS rebinding) — a later security stage.
- On Windows (and macOS with Python < 3.9) `/published` uses a weaker path-based fallback;
  the server prints the active mode at startup. Secret file permissions are not set on Windows.

Design and deviations from the spec: `docs/superpowers/specs/2026-10-14-modules-2a-design.md`
(modules, folder publishing, tokens) and `docs/superpowers/specs/2026-10-16-vercel-publish-design.md`
(Vercel).
Direction: `docs/design/spaces-and-modules.md`. Release notes: `CHANGELOG.md`.

## Comments

Comments have two channels. The **local** one is for the agent: pins you leave for it, kept in
`<task>/.dc-local-comments.json` and read with `bin/inbox.py`. The **team** channel is the
`comments` *role*: a module connects a comment service, and the same pins then appear on the
canvas pages (the «Team» tab), on the Overview, in published previews (folder and Vercel) and
for the agent (`inbox`, `inbox resolve`). A space without a `comments` module has no team
channel; enabling one adds it. A migrated legacy (in-house) space keeps its original shared
service until you enable a module there, and **a disabled module in such a space returns it to
the shared service** (so does removing its entry from `space.json`). If an enabled module is
broken — in any space — a canvas page shows local comments with a notice and the Overview and
`inbox` report the error; nothing falls back silently to the shared service. (A stale entry of
some unknown module, one that never was a comments module, is not an enabled comments module and
changes nothing.)

**Your own Supabase** (`supabase-comments`), in four steps — the check codes and the security
notes are in [the module README](app/modules/supabase-comments/README.md):

1. Create a Supabase project — **a dedicated one per team**.
2. Run [`app/modules/supabase-comments/schema.sql`](app/modules/supabase-comments/schema.sql)
   in its SQL editor, once (the module never changes your schema).
3. Take the project URL (`https://<ref>.supabase.co`) and the **public** key (`anon` or
   `publishable`) from Project Settings → API — never the `service_role` / `secret` key (the
   module refuses it: this key goes into every page).
4. Enable the module on the Connections screen (Team comments → Supabase → «Connect»: the
   project URL and the public key), or over the API:

   ```bash
   curl -s localhost:8765/api/module-enable -H 'Content-Type: application/json' \
     -d '{"space":"<id>","id":"supabase-comments","settings":{"url":"https://<ref>.supabase.co"},"secrets":{"key":"<public key>"}}'
   ```

   The answer carries the verdict of `check`: `bad-key`, `no-schema` (run step 2), `network`.

**Your own service.** Any comment service — PocketBase, Firebase, your own API — connects with
a small module: a browser adapter (`window.DeaiComments.create(cfg)`) and four server
functions (`client_config`, `list`, `resolve`, `check`). The channel of a task
(`deai/<space>/<task>`) is given by the core. The guide, with a complete example, is
[`docs/modules/comments.md`](docs/modules/comments.md). The module can live in the space itself
(`<space>/modules/<id>/`) and runs after you trust it — see [`docs/modules/authoring.md`](docs/modules/authoring.md).

**Limits.** The rules in `schema.sql` are open: whoever has the public key — and it is inside
every page you publish — reads and writes the comments of that project, so use a dedicated
project; the agent reads those comments as work items, so treat their text as untrusted input.
The adapter's JavaScript runs on the canvas origin, which is why a space's own module
runs only after you trust it. The service has to allow CORS for the opaque origin `null` too (the local
`/published` view; Supabase does). Supabase is tested against an in-process fake REST server,
not a real project. Screenshots of pins are not part of the role (the role has no file storage).

## Git sync

The `git-sync` module (role `vcs`) keeps a task's iterations in a git repository — GitHub, GitLab or your own server —
so a colleague gets your mockup and you get theirs. It works in any space. It is a transport only: what to send and how
to take what arrives (a new iteration, a fork from a colleague's one) is the core's job, the same for every provider of
the role.

**Connect it.** Connections → «Git sync» → «Git» → «Connect»: the repository (the default for the tasks of the space; it
may stay empty and be given per task), the branch (`main`), the folder in the repository (`mockup/{task}` — `{task}` is the
task id), and, optionally, an SSH key and a server IP (for a VPN where the server's name does not resolve; only for
scp-style addresses, `[user@]host:path` — not for `ssh://`, `https://`, `file://` or a local path). «Check» asks the repository for the branch (`git ls-remote`, 4 seconds). The same section is
in the new-space wizard, step 2.

**A repository per task.** «New task» has an optional «Repository» field (not in the in-house legacy space): empty means
the default of the module for the later sync, but the task starts from a blank page. Only a filled field (or a space
with integrations) makes the first iteration come from the repository: if `<path>` of the
new task already holds an `index.html` there, it is taken. A task without any repository has no sync, and the task bar offers «Configure repository…»,
which opens Connections on the Git card. Addresses: `ssh://`, `https://`, `file://`, `user@host:path` or an absolute local path.

**Access is git's, not Deai's.** The module runs the git that is on your computer and never asks for a password
(`GIT_TERMINAL_PROMPT=0`): use an SSH key (in the agent, in `~/.ssh/config`, or the module's `ssh_key`) or a saved HTTPS
sign-in (a git credential helper, for example the GitHub CLI's). A password inside an address (`https://user:pass@host/…`) is refused. Without
access the answer is `vcs-auth`.

**In the task bar.** A dot and a menu: «Send» an iteration, «Pull» (offered when the repository is ahead), «History» (for
GitHub and GitLab addresses), and the state — in sync, ahead, behind, error. The label is the service's name: GitHub,
GitLab or Git.

* **Send** puts the iteration into `<path>` of the repository — the clean mockup, a `README.md` for a multi-page one and
  `.canvas-state.json` — as one commit signed with this machine's identity (subject `deai: sync <path> (<title>) · <it>`)
  and pushes it without force. A colleague's iteration is never sent. If somebody changed `<path>` in the meantime, nothing
  is sent over it: pull first.
* **Pull** is `pull --ff-only`: the repository's `<path>` arrives as a new iteration signed by its author, with a copy to
  continue in when it is a colleague's (or older than your own newest work); if it equals an iteration you already have,
  nothing is created.
* In a regular space the repository is cloned once per address into
  `~/.deai/cache/<space id>/git-sync/mirrors/<host>/<slug>-<8 hex>` (the slug of the repository path plus a short hash of the normalized address: `o/r.git` becomes `o-r.git-1a2b3c4d`, so `o/r` and `o-r` never share a folder) and shared by the tasks that use it; the first
  clone can take minutes (the legacy space keeps its old mirror folders). The mirror is a cache of the tool: before every
  send or pull its tree is reset and cleaned, so edit nothing there by hand (local commits that were not pushed stay).
* A branch that is missing on a non-empty repository is an error: Deai does not create branches in a shared repository.
  On an empty repository the first send creates it.
* **Autosync.** With the module's «Send after every agent reply» on, the agent's Stop hook calls `POST /api/autosync` after
  each reply; it sends your newest own iteration when it changed. Off by default.

**For an agent or a script.**

| Call | |
|---|---|
| `GET /api/vcs-status?it=<iteration>` | `{configured, behind, behind_path, unpushed, on_remote, dirty, web, label, …}`; `{configured: false}` when the space has no `vcs` module or the task has no repository; a refusal is `{configured: true, error, code}` |
| `POST /api/vcs-push` `{it}` | send an iteration; `{ok, synced, changed, pushed, sha?, remote, …}` or `blocked: "behind" \| "diverged" \| "foreign"`; a refusal is `{ok: false, error, code}` |
| `POST /api/vcs-pull` | pull the repository's version as a new iteration |
| `POST /api/autosync` | the quiet step for a Stop hook; `reason` says why nothing was sent (`no-gitlab`, `autosync-off`, `no-iterations`, `foreign-only`, `clean`, `offline`, `error`) |

`GET /api/gitlab-status`, `POST /api/gitlab-sync` and `POST /api/gitlab-pull` are the old names of the first three and stay
as aliases with the same answers. Codes: `vcs-offline`, `vcs-auth`, `vcs-bad-target`, `vcs-busy`, `vcs-error`. To write a
provider of this role yourself, see [`docs/modules/authoring.md`](docs/modules/authoring.md), *The `vcs` role*.

**Limits.** HTTPS works only when git already has the sign-in saved; the retry through `host_ip` covers only
scp-style addresses (`[user@]host:path`); Windows is not checked on a real machine; a token placed in the user position of an address
(`https://TOKEN@host/…`) is accepted and sits in the task file in plain text, though it is hidden from every answer and
text. The full list is in `CHANGELOG.md`, 0.8.0.

## Layout

```
app/          server (serve.py, stdlib only) + UI (ES modules, no build step)
app/modules/  built-in modules (static-publish, vercel-publish, css-tokens, supabase-comments, git-sync); the core is app/deai_modules.py
docs/         design notes and the guides for module authors (docs/modules/authoring.md, docs/modules/comments.md)
bin/          CLI tools: snapshots, pages, state, inbox
ops/          macOS launcher (Design Canvas.app), preview gate tools
flows/demo    example flow
tests/        unit, Python and live (Playwright) tests
```

## Roadmap

1. ✅ **Spaces** (0.1) — several projects/companies on one machine, each with its own task list and settings.
2. **Modules**
   - ✅ **2a** (0.2) — module framework, publishing to a folder, design-system tokens from CSS.
   - ✅ **2b-1** (0.3) — your own Vercel (publish) as a module.
   - ✅ **2b-2** (0.4) — the universal `comments` role (browser adapter + server functions) and
     your own Supabase (team comments) as the first module; a guide for writing your own.
   - Later — the legacy publishing and comments, team dashboard, issue tracker, notifications: modules you connect per
     project (stage 4).
3. **Onboarding**
   - ✅ **3a** (0.5) — the Connections screen: connect, configure, check, replace and turn off
     modules from the UI; `replace` in `module-enable`.
   - ✅ **3b** (0.6) — the new-space wizard: space → modules → settings → first task, and a task
     from an existing mockup folder (`from` in `task-new`).
   - ✅ **3c** (0.7) — a space's own modules from `<space>/modules/`, run from a snapshot only after a person trusts them (dialog + system window).
4. **Company integrations leave the core** — the goal is a clean core and parity: everything the original in-house
   setup does becomes modules, so that setup can move to an ordinary space without losing anything. Four releases
   (the same numbering as in `docs/design/spaces-and-modules.md`):
   - ✅ **4a** (0.8) — git sync: the `vcs` role and the `git-sync` module (any git remote).
   - **4b** — the in-house publishing and comments move onto the existing modules (`vercel-publish`,
     `supabase-comments`); their hard-wired constants go.
   - **4c** — team dashboard, tracker statuses and team chat notifications: the roles `dashboard`, `tracker`, `notify`
     in the core, and the modules for them.
   - **4d** — the `integrations` flag goes: the original setup becomes an ordinary space.
5. **Claude Code plugin** — a generic task → mockup → iterations → review → publish loop.
6. **Cross-platform start** — one command on macOS, Windows and Linux.

## License

MIT © neodisa
