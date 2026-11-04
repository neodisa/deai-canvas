# Deai Canvas

**A local workspace for prototypes made with AI.** An agent (Claude Code or any other)
writes HTML mockups; Deai Canvas turns them into something you can review and ship:
iterations, a bird's-eye overview of every screen, user-flow maps, a design-token
inspector, comments addressed straight to the agent, and password-protected preview
links for your team.

> **Status — v0.15.0 (private; extracted from an in-house tool, source 1.55.0 @ `796b3df`).**
> Spaces (several projects on one machine) and the first **modules** are in: publishing to
> a folder or to your own Vercel account, design-system tokens from a CSS file, team
> comments on your own Supabase (or any service, through a small module), and **git sync** —
> iterations to and from any git repository, GitHub or GitLab or your own server — work in any
> space. A **wizard** creates a space and takes you through its modules and a first task, and a
> **Connections** screen manages the modules afterwards — no command line. Your own Vercel can be reached with a token
> or with the `vercel login` of the computer. The in-house publishing and comments of the legacy space now run on these same
> modules, and so does the **team dashboard** (the «Team» tab of «Tasks»): any space can get it through the
> `supabase-dashboard` module and its own Supabase project, and the **issue tracker** (task statuses from Jira Cloud) through
> the `jira-tracker` module, and the **Teams notifications** (a card in a Teams channel for every new comment, and the
> silence switch) through the `supabase-teams` module and the same Supabase project as the comments. The legacy space
> runs on all of these modules too; what is left of it is the `integrations` flag (stage 4d). The old «profile» of a task
> is now a general **track of a space** (a folder, a repository and a design system per line of work, described in
> `space.json`). A space can carry **its own modules** in `<space>/modules/`; their code runs only
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
| **Team dashboard** | The «Team» tab of «Tasks»: the cards of the whole team's tasks (Jira status, open comments, preview, designer) from **your own Supabase project**, in any space, through the `supabase-dashboard` module. See *Team dashboard*. |
| **Issue tracker** | The status of a task («In progress», «Done») from **your own Jira Cloud** as a badge on the «Tasks» screen — in any space, with no dashboard needed — through the `jira-tracker` module. See *Issue tracker*. |
| **Teams notifications** | A card in your Teams channel for every new comment, and a switch «Notify Teams» in the publish menu to silence a task's channel — from **your own Supabase project**, in any space, through the `supabase-teams` module. See *Teams notifications*. |
| **Space tracks** | Several lines of work in one space — each with its own folder for the tasks, default repository, design system and label — described in `space.json`; a task carries its `track`. See *Space tracks*. |
| **Tasks** | A home screen with all your tasks: search, sort, filters, and **tags** — give a task tags when you create it or with the «Мітки» button on its card, filter by them and find them with the search. See *Tasks and tags*. |
| **New-space wizard** | Four steps — space, modules, settings, first task (a blank page, an existing mockup folder, or a phrase for the agent). The same wizard opens on the first run and for «New space…». See *Spaces*. |
| **Connections** | A page per space to connect, configure, check, replace and turn off modules (publishing, team comments, git sync, the team dashboard, the issue tracker, Teams notifications, design-system tokens) from the UI. See *Modules*. |
| **App** | Installable as a PWA (own window and Dock/taskbar icon); macOS launcher with auto-start. |

UI in English and Ukrainian.

## Quick start

Requirements: Python 3.9+, Chrome or Edge. Optional: Node.js 20+ (snapshots via Playwright;
the System Vercel CLI sign-in of `vercel-publish` and the in-house publishing of a legacy space — the Vercel module with a
token needs no Node).

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
calls: `publish`, `tokens`, `comments`, `vcs`, `dashboard`, `tracker` and `notify`; no role name is
reserved any more. One provider per role per space.

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
| `vercel-publish` | `publish` | Publishes the preview to **your own Vercel account**: one project per task, a public `https://pv-<8 digits>.vercel.app` address, old deployments cleaned. Two ways to sign in (`auth`): a **token** through the REST API (no Node, no CLI; the default) or the **System Vercel CLI** (`npx vercel` under the `vercel login` of the computer; needs Node.js, stores no token). Settings: `auth`, `token` (secret), `team`, optional `password` (secret). Off by default. See *Publishing to your own Vercel*. |
| `css-tokens` | `tokens` | Reads design tokens from one CSS file so the inspector can tell on-system values from hard-coded ones. Setting: `file`. |
| `supabase-comments` | `comments` | Team comments in **your own Supabase project**: the pins are stored there, shown on the canvas, the Overview and in published previews, and read and closed by the agent. Settings: `url`, `key` (the public key; a secret that is allowed into pages), optional `shots_bucket` (screenshots of pins). Off by default. See *Comments*. |
| `supabase-dashboard` | `dashboard` | The team dashboard in **your own Supabase project**: the canvas stores the cards of your tasks there and the «Team» tab reads the rows of the whole team back. Settings: `url`, `key` (a **non-public** secret: `service_role` or the key of a role of your own), optional `table` (`deai_dashboard`). Off by default. See *Team dashboard*. |
| `jira-tracker` | `tracker` | The status of your tasks from **your own Jira Cloud**: the canvas asks Jira for the keys of your tasks (`DEMO-1`…) and shows the status as a badge on the «Tasks» screen and on the cards of the team dashboard. Read-only. Settings: `base` (`https://<site>.atlassian.net`), `email`, `token` (a secret: the Atlassian API token). Off by default. See *Issue tracker*. |
| `supabase-teams` | `notify` | Teams notifications in **your own Supabase project**: the database sends a card to Teams for every new comment (its own `schema.sql`, the webhook address in Vault), and the canvas switches the silence of a task's channel. Settings: `url`, `key` (a **non-public** secret: `service_role` or the key of a role of your own). Off by default. See *Teams notifications*. |
| `git-sync` | `vcs` | Syncs a task's iterations with **any git repository** — GitHub, GitLab, your own server — through the git on your computer: nothing is stored by Deai, access is your SSH key or saved HTTPS sign-in. Settings: `repo` (the default for tasks; optional), `branch` (`main`), `path` (`mockup/{task}`), `ssh_key`, `host_ip`, `autosync`. Off by default. See *Git sync*. |

**Publishing to a folder.** Mark iterations with the green dot, press *Publish*: the
result is a plain static site in the folder (host it anywhere; the task id must be
`A–Z a–z 0–9 _ -`, up to 128 characters). The canvas also serves a
sandboxed local copy at `http://localhost:8765/published/<space-id>/<task>/`. The folder
is re-checked on every publish and serve; it must not be your home folder, the tool or
space folders, or a system folder, and a folder without the `.deai-published` marker is
never overwritten.

**Publishing to your own Vercel.** `vercel-publish` signs in in one of two ways, the setting `auth`. **Token** (the
default) needs only a token — no `vercel login`, no CLI, no Node on the machine. **System Vercel CLI** (`cli`) uses the
`vercel login` of this computer through `npx vercel`: no token is stored, Node.js (`npx`) is required, and the section
*System Vercel CLI* below applies. The rest of this section is about the token.

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

**System Vercel CLI.** Choose «System Vercel CLI» in the setting `auth` (labelled «Вхід у Vercel»; Connections → Vercel, or the wizard);
the token field is then ignored, and `team` is the `--scope` of the CLI (empty: your personal account). Run
`npx vercel login` once in a terminal; «Check» asks `vercel whoami` and says `no Node.js` or `not logged in` in plain
words. A publish runs `link` and `deploy --prod` in the built folder, takes the shortest `*.vercel.app` address and
verifies the preview. Names: the project is the one recorded for the task, otherwise a random `pv-<8 digits>`; a project
name or a team that does not fit is refused before anything runs: a project name is lowercase letters, digits, `.`, `_` and
`-` (the first character a letter or a digit), a team (scope) is letters, digits, `_` and `-` (no `.`; the first character a
letter or a digit). In an ordinary space the project must be a `pv-<8 digits>` name — the state that comes from the task's
`iterations.json` travels through git, so a project with another name there is not reused (a new `pv-` project is created and
a warning says so) and the team always comes from the setting, never from that state. A failed `vercel link` stops the publish
with its output. «Check» may take a while on the first run (a cold `npx` downloads the CLI): it is given up to 130 seconds. **Cleanup:** after a publish the 3 newest deployments of the project are kept (the current one
among them) and the older ones are removed by address — only `*.vercel.app` deployments of that project, with `--safe`,
never the project itself; if the cleanup cannot finish, the publish still succeeds and shows a warning. Limits: a
publish that fails after `link` can leave an empty `pv-` project in your account (delete it in the Vercel dashboard); the
cleanup reads up to 5 pages of the list and needs a CLI that has `list --json` and `remove --safe` (checked with 65.x).

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
Supabase until you enable a module there — through the same `supabase-comments` module, as an
implicit provider — and **a disabled module in such a space returns it to
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

**Pin screenshots.** Set the optional `shots_bucket` (the name of a **public** Storage bucket of the
same project) and the browser adapter uploads the screenshot of a pin to
`<bucket>/comment-shots/<id>.jpg` and keeps the public address in the pin; without it pins have no
uploaded screenshot. The bucket and its policies are yours to create (details in the module README).

**The legacy (LIGA) space** has no module to enable: the address and the **public** key of its shared
Supabase are read from the installation — the root of its `tasks.json`:

```json
{ "supabase_url": "https://<ref>.supabase.co", "supabase_key": "sb_publishable_…" }
```

(or the environment variables `SUPABASE_URL` and `SUPABASE_KEY`). The same pair feeds the
team dashboard and the Teams silence (through the modules `supabase-dashboard` and `supabase-teams`). Without it the team comments of that space are off — the page shows the local pins
and a notice, and `inbox` reports `comments-unconfigured`. The screenshot bucket there is `overview-thumbs`.

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
not a real project. Screenshots are not part of the role contract: the role has no file storage, so a module may offer an optional `uploadShot` (as `supabase-comments` does with `shots_bucket`), and without it the layer keeps no uploaded screenshot.

## Tasks and tags

Every task can carry **tags** — short labels in any space. Set them in the field «Мітки» of «New task» (comma-separated, optional)
or later with the button «Мітки» on a card of the «Mine» tab; the chips under the search are built from them (the more tasks
a tag has, the earlier its chip; several chips mean «any of them»), and the search looks into them too. A tag is 1–32
characters without a comma, a task has at most 10, and `Alpha` and `alpha` are one tag. Over the API: the key `tags` of the
task rows, the optional `tags` of `POST /api/task-new` and `POST /api/task-tags` `{id, tags}`. The «Team» tab has no tags yet (its rows come from the dashboard).

**The LIGA space.** A task there without tags shows its track (`United`, `LIGA360`, `SEO`; the old name was «profile») as a tag,
so the screen looks as before. The track still decides the folder and the default repository of a task (see *Space tracks*); the table «profile → repository» is read
from the root of the legacy `tasks.json` (the same file as the Supabase pair):

```json
{ "profile_repos": { "united": "git@git.example:org/united-design.git", "seo": "git@git.example:org/seo-design.git" } }
```

A profile is `[a-z0-9-]` up to 32 characters; a repository is printable ASCII without spaces and does not start with `-`.
Without the table new LIGA tasks get no default repository.

## Space tracks

A space can have several **tracks** — lines of work such as «Web» and «Mobile». Each track has its own **folder for the tasks**,
a **default repository** of mockups, a **design system** for the inspector and a **label**; a task carries the id of its track
in the key `track`, and without tags it shows the label of its track on the «Tasks» screen. A space with no tracks works as
before. Tracks are described by hand in the `space.json` of the space (there is no screen for them yet); the file is read on every
request, so no restart is needed. Example, with invented values:

```json
{
  "name": "Studio",
  "tracks": [
    { "id": "web",    "label": "Web",    "root": "~/work/web", "repo": "git@example.com:studio/web.git", "ds": "" },
    { "id": "mobile", "label": "Mobile", "root": "mobile",     "repo": "",                               "ds": "" }
  ],
  "default_track": "web"
}
```

| Field | Rule | When absent or bad |
|---|---|---|
| `id` | **Required.** `[a-z0-9-]`, 1–32 characters, unique in the space. | The whole track is dropped (on a duplicate the first one wins). |
| `label` | The caption and the derived tag of a task: 1–32 characters, no comma, no control or invisible characters. | The `id`. |
| `root` | The folder where the tasks of the track are created. Absolute, `~/…`, or relative to the folder of the space. | The folder of the space. |
| `repo` | The default repository of a new task: printable ASCII without spaces, not starting with `-`. | No default repository. |
| `ds` | The name of a static design system of the inspector (`[a-z0-9-]`, up to 32); today the inspector knows `united` and `liga360`, and for any other name it honestly says there is none. | `''`: no static design system, the inspector takes the tokens of the space. |
| `default_track` | The track for a task created with no `track`. | The first track (no tracks: none). |

At most **20** tracks count; the rest are ignored. Reading never fails: a bad entry is dropped and a bad field counts as absent, so
the rest of the file keeps working.

**The `root` must be a sensible folder.** A system folder, a hidden folder or `Library` in your home, your home itself, a folder
inside this tool's own repository, a folder equal to or inside **another** space of this machine, a path longer than 1024
characters or a file — all of these are silently replaced by the folder of the space (no warning yet). A folder inside the space
itself is fine.

**Creating a task in a track.** Only the API puts a task into a track today (the pipeline skill does it): `POST /api/task-new` with
`"track": "web"`. A body with no `track` goes to `default_track`. An unknown track is `400 unknown-track` and **nothing is
created**; a `track` that is not a lowercase id is `400 bad-track`. The task folder is created under the `root` of the track. If
the track has a `repo`, **and** the space has a provider of the role `vcs` (see *Git sync*), **and** the body has no `vcs` of its
own, the task gets `vcs: {repo}` and is bootstrapped from that repository; without a provider the `repo` is just not applied.
The old key `profile` still works as a synonym of `track`; old clients that send a `profile` that is not a track of the space are
simply ignored, exactly as before. `GET /api/tasks` and `GET /api/task` give `track` for every task, and `GET /api/spaces` lists
`tracks: [{id, label}]` and `default_track` — never the folders or repositories.

**The LIGA space** has three tracks (`united`, `liga360`, `seo`) that come from the root of its `tasks.json` (`design_work_roots`,
`design_work_root`, `profile_repos`) — see *Tasks and tags*. Nothing is to be done there; its tasks keep both `track` and `profile`
so that teammates on an older version still read them.

## Team dashboard

The `supabase-dashboard` module (role `dashboard`) turns a Supabase project of yours into a shared board of the team's tasks.
The canvas builds a **card** of every task that has a folder on this computer — name, Jira status, open comments, links to
the preview and the code, designer, iterations and pages — and the module stores it; the tab «Team» of the «Tasks» screen
reads the rows of all designers back. A space without a provider of the role has no «Team» tab. The module only stores and
returns: what a card is, and when to send it, is decided by the core (`app/dashboard.py`).

**Connect it**, in four steps — the check codes and the security notes are in
[the module README](app/modules/supabase-dashboard/README.md):

1. Create **a dedicated Supabase project** (the cards hold the name and the e-mail of a designer).
2. Run [`app/modules/supabase-dashboard/schema.sql`](app/modules/supabase-dashboard/schema.sql) in its SQL editor. It creates
   `public.deai_dashboard`, turns row-level security on and gives **no access to `anon` or `authenticated`**.
3. Take the project URL and a **non-public** key from Project Settings → API (`service_role`, or the key of a role of your own
   with explicit grants and policies on the table). The module refuses a public (anon / publishable) key: that one is inside
   every published preview.
4. Connections → «Team dashboard» → «Supabase dashboard» → «Connect» (or the same step of the new-space wizard). The key is
   kept in `~/.deai/secrets.json` (owner only) and never goes into a page.

**When the cards are sent.** After a publish, after a git sync that pushed and after an autosync that changed something —
by a background process (`bin/overview_push.py sync --space <id>`), one at a time per space, with its log in
`<DEAI_HOME>/logs/dashboard-sync.log`. Running it from a scheduler is the same: `bin/overview_push.py sync` without a flag syncs
the LIGA space, `sync --space <id>` an ordinary one. The «Team» tab waits for the rows up to 6 s and keeps the last rows it
read when the service goes quiet. A migrated legacy space keeps its shared Supabase through the same module and needs no step.
The statuses on the cards come from the provider of the role `tracker` (see *Issue tracker*); the base cards from the task
registry are still a part of that legacy space only.

## Issue tracker

The `jira-tracker` module (role `tracker`) shows the status of a task — «In progress», «Done» and so on — as the badge of its
card on the «Tasks» screen. A task is tied to the tracker by its **key** (`DEMO-1`; the field `jira` of the task). The canvas
asks Jira for the keys of the tasks on «Mine» (the first 100, one call), keeps the answer for 5 minutes per space and shows
the badge; without the module the screen shows no status from a tracker, and statuses never need the team dashboard. A space
that also has the dashboard sends the same statuses on its cards. The module only reads: it creates and changes nothing in
Jira. Jira Cloud only; Jira Server / Data Center is a separate module later.

**Connect it:** Connections → «Issue tracker» → «Jira Cloud» → «Connect» (or the same step of the new-space wizard) with the
site address (`https://<site>.atlassian.net`), the e-mail of your Atlassian account and an **API token** (create it in the
security settings of the Atlassian account; the key is kept in `~/.deai/secrets.json`, owner only, and never goes into a page).
«Check» says «connected», or «Jira rejected the email or token» for a wrong pair. The details and the network calls are in
[the module README](app/modules/jira-tracker/README.md).

**When it does not answer.** The banner «Issue tracker unavailable: …» appears over «Mine» (with «data as of HH:MM» when older
statuses are still shown); «Try again» asks again, and the badges of the last good answer stay. A task key that Jira does not
know fails the whole batch of keys (Jira answers HTTP 400 to the query) — fix that key.

**The LIGA space** reaches its Jira through the same module with no wizard step: add the address as `jira_base` to the legacy
`tasks.json` (the file with `supabase_url`), for example `"jira_base": "https://demo.atlassian.example"`; the credentials are
`JIRA_EMAIL` and `JIRA_TOKEN` in the environment or the two files in `~/.claude/pipeline-feedback/`. Without `jira_base` that
space has no statuses, and when its tasks carry Jira keys «Mine» says that Jira is not configured.

## Teams notifications

The `supabase-teams` module (role `notify`) puts a **card in a Teams channel for every new comment** (pin) and gives you a
switch **«Notify Teams»** in the publish menu of a task that silences its comment channel (a silenced channel covers its
sub-channels; the comments themselves are not touched). The sending is done by **your Supabase database**, not by the canvas:
a trigger on the table of the comments posts the card through a webhook whose address lives in Vault. The canvas only reads
and switches the silence, and its «Check» tells whether everything is in place. Without the module the space has neither the
cards nor the switch, and the Teams item of the menu is not shown.

**Connect it** (once per Supabase project; the comments of the space must already be on **that** project):

1. In the SQL editor run the schema of `supabase-comments`, then
   [`app/modules/supabase-teams/schema.sql`](app/modules/supabase-teams/schema.sql). Use a dedicated project: the script takes
   over tables with its own names. **Do not run it in the LIGA database** — it has its own version.
2. Put the address of your Teams webhook into Vault (https only):
   `select vault.create_secret('<webhook address>', 'teams_webhook_url');`
3. Create the receiving side in Teams — usually a Power Automate flow «When a Teams webhook request is received» that posts
   the Adaptive Card it gets as it is.
4. Connections → «Teams notifications» → «Supabase Teams» → «Connect» (or the same step of the new-space wizard) with the project
   address and a **non-public** key (`service_role` or the key of a role of your own; kept in `~/.deai/secrets.json`, never put
   into a page — a public key is refused, because the public key goes into every published preview).

«Check» says «connected» with the number of deliveries of the last 6 hours and of the failed ones, or names what is missing: no
functions in the database (run `schema.sql`), no `teams_webhook_url` in Vault, a public key instead of a non-public one. Delivery
is fire-and-forget (no retries), and the card carries the id of the channel, not a project name. A comment that already has a row
in the delivery log is never posted twice. The details, the grants and the network calls are in
[the module README](app/modules/supabase-teams/README.md).

**The LIGA space** reaches its own database through the same module with no wizard step and no schema to run (its database has
all of this already): the address and the public key come from the same `tasks.json` pair as the comments.

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
app/modules/  built-in modules (static-publish, vercel-publish, css-tokens, supabase-comments, supabase-dashboard, jira-tracker, supabase-teams, git-sync); the core is app/deai_modules.py
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
   - Later — team dashboard, issue tracker, notifications: modules you connect per
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
   - **4b** — the in-house publishing and comments move onto the existing modules; the hard-wired constants and the
     profiles go. Three releases:
     - ✅ **4b-1** (0.9) — publishing: the in-house space publishes through `vercel-publish` (new sign-in «System Vercel
       CLI»), with cleanup of old deployments; the Vercel transport leaves the core.
     - ✅ **4b-2** (0.10) — comments: the in-house space keeps its comments through `supabase-comments` (module 1.1.0:
       pin screenshots, the iteration number on resolve); the Supabase address and key move from the code to `tasks.json`.
     - ✅ **4b-3** (0.11) — the profiles: tasks get general tags (chips, filter, search, a dialog to edit them); a LIGA task
       without tags shows its profile as a tag; the table «profile → repository» moves from the code to `tasks.json`
       (`profile_repos`).
   - **4c** — team dashboard, tracker statuses and team chat notifications: the roles `dashboard`, `tracker`, `notify`
     in the core, and the modules for them. Three releases:
     - ✅ **4c-1** (0.12) — the team dashboard: the role `dashboard` and the built-in module `supabase-dashboard` (any space
       with its own Supabase gets the «Team» tab); the legacy space goes through the same module as an implicit provider;
     - ✅ **4c-2** (0.13) — tracker statuses: the role `tracker` and the built-in module `jira-tracker` (statuses on the «Tasks»
       screen of any space, no dashboard needed); the legacy space goes through it as an implicit provider, its Jira address
       moves from the code into `tasks.json` (`jira_base`);
     - ✅ **4c-3** (0.14) — Teams notifications: the role `notify` and the built-in module `supabase-teams` with its own
       `schema.sql` (a card for every new comment, the silence per channel, a delivery log); the legacy space goes through it as
       an implicit provider, and no role name is reserved any more.
   - **4d** — the `integrations` flag goes: the original setup becomes an ordinary space. Four releases (owner decision
     04.11.2026):
     - ✅ **4d-1** (0.15) — tracks: the profile of a task becomes a general **track of a space** (`tracks` in `space.json`: a
       folder, a repository, a design system and a label per line of work); the LIGA space gets its three tracks from an implicit
       adapter, with no change for its designers;
     - **4d-2** (0.16) — the layer-off seam and the isolation of shared state without the literal `'legacy'`;
     - **4d-3** (0.17) — explicit LIGA modules, with an automatic migration of its config (with a backup);
     - **4d-4** (0.18) — the `integrations` flag and the old aliases (including `profile`) go.
5. **Claude Code plugin** — a generic task → mockup → iterations → review → publish loop.
6. **Cross-platform start** — one command on macOS, Windows and Linux.

## License

MIT © neodisa
