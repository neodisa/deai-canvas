# <img src="app/pwa/icon-192.png" alt="" width="40" height="40" align="top"> Deai Canvas

**A local workspace for reviewing the HTML mockups an AI agent writes.** The agent (Claude Code or any
other) makes the pages. Deai Canvas keeps every iteration, shows all screens at once, lets you point at an
element and tell the agent what to change, and publishes a protected preview for your team.

![Deai Canvas: the workplace with the page tree, a mockup, pinned comments and the agent status](docs/screenshots/hero.png)

## Why

- **The agent rewrites, you need to compare.** Every pass is kept as an iteration: a frozen, editable copy you can rename,
  duplicate and open next to the others.
- **A mockup is many screens, not one.** The Overview shows every page and state as a grid of full-page snapshots at desktop,
  tablet and mobile widths. The Flow view lays the same screens out as a user flow with arrows.
- **"Make this button smaller" needs an address.** Pin a comment on the element itself. The agent reads the pins, fixes the
  page and closes each pin with a note about what it did.
- **Hand-made values drift from the design system.** The inspector shows spacing, type and colour of any element, and, if you
  connect a CSS file of tokens, whether each value is on the system. The tuner turns tweaks into a change request for the agent.
- **The team needs a link, not a build.** Publish the iterations you marked to a folder or to your own Vercel account,
  optionally behind a password. Team comments can live on your own Supabase.
- **You want to know what the agent is doing.** The island at the bottom of the window shows its status; each open task is a tab
  with a state dot.
- **Local first.** Mockups, comments and snapshots are files on your disk. Publishing, team comments, git sync and the rest
  are modules you connect yourself.

## Features

- **Iterations** with notes, rename, duplicate and a marker for what goes into the preview.
- **Pages and states** as a tree of any depth: pages, folders, states; filter, drag and drop.
- **Overview**: a zoomable grid of full-page snapshots (Playwright), re-shot incrementally; desktop, tablet and mobile widths.
- **Flow map**: screens and arrows described in `flow.json`, dragged into place on the canvas.
- **Comments panel** for Claude or for the team: pins on elements, search, closed pins with the agent's note, carry-over from
  earlier iterations.
- **Inspector and tuner**: a DevTools-style overlay with a ruler, token check against your design system, and a change request
  for the agent.
- **Agent status**: a state in the island and a dot on every task tab.
- **Tasks screen**: search, sort, tags, issue-tracker statuses and a team dashboard if you connect them.
- **Publish** to a folder or to your own Vercel account, with an optional password gate.
- **Git sync**: send an iteration to any git repository and pull a colleague's changes back as a new iteration.
- **Spaces, wizard and Settings**: several projects on one machine; modules are connected and checked from the UI.
- **Modules**: built-in ones for publishing, tokens, team comments, git, dashboard, tracker and Teams notifications; your
  own in `<space>/modules/`, run only after you trust them.
- **To Figma**: copies the live mockup to the clipboard for pasting into Figma.
- **App**: installable as a PWA; ⌘K palette; English and Ukrainian UI.

## Screenshots

The screenshots show a made-up budgeting app on demo data. `node ops/readme-shots.mjs` regenerates them.

![Overview: every page and state of an iteration as a grid of snapshots, with comment counts](docs/screenshots/overview.png)
*Overview: all pages and states of an iteration at once, with the number of open comments on each.*

![Flow map: screens connected by arrows with the user action on each](docs/screenshots/flow.png)
*Flow map: screens as a user flow; pages that are not in the flow are grouped below.*

![Comments panel next to the mockup](docs/screenshots/comments.png)
*Comments: pins on elements, the list for Claude, and a closed pin with the agent's note.*

![Tasks screen with four task cards](docs/screenshots/tasks.png)
*Tasks: every task of a space with its latest frame, tags and iteration count.*

![A published preview of the mockup](docs/screenshots/preview.png)
*Published preview: the same pages behind an optional password, ready to share by link.*

## Status

Version 0.28.2 (16.11.2026), pre-1.0, MIT. The start script and the launcher are macOS-first; see the Roadmap for the
cross-platform start. What changed in each release is in [CHANGELOG.md](CHANGELOG.md).

## Feature reference

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
| **Settings** | A page per space to connect, configure, check, replace and turn off modules (publishing, team comments, git sync, the team dashboard, the issue tracker, Teams notifications, design-system tokens) from the UI. See *Modules*. |
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
listed in `~/.deai/spaces.json`; the space chip on the Tasks screen switches between them.

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
3. **Settings** — the fields of each chosen module, the same as in the Settings side panel
   (secrets are written, never shown). One pass writes the choices and checks each module; if
   something fails, the wizard stays on the step with the reason in the card. If an agent changed a
   role while you were choosing, that module is not written and its card says so.
4. **First task** — a blank page, **an existing folder with an `index.html`** (the server copies it
   into the first iteration; the original is untouched), or a phrase to tell your agent. «Skip» goes
   to the tasks of the new space.

Unsaved settings are asked about before «Back» or «Close the wizard»; Esc does not close the page.
Not part of the wizard: picking a folder with the system dialog, and resuming an unfinished wizard
after a restart (what was created stays, and the rest is on «Settings»).

**A task from an existing folder** is also available over the API: `POST /api/task-new` with
`from` (see *Module API* below). It works in a space without integrations only; symbolic links,
`.git` and `node_modules` are not copied, and a folder of more than 2000 files or 200 MB is refused.

## Modules

A **module** is a folder — built in at `app/modules/<id>/` or a space's own at
`<space>/modules/<id>/` — with `module.json` (manifest and the settings
it asks for) and `server.py` (functions for its role). A *role* is an interface the core
calls: `publish`, `tokens`, `comments`, `vcs`, `dashboard`, `tracker` and `notify`; no role name is
reserved any more. One provider per role per space.

**Connecting a module — the Settings screen.** Click the gear at the top right, or open the space menu
(the space chip on the Tasks screen) → «Settings…», or press ⌘K and pick «Settings of the space …»; in a space
without integrations the head of the Tasks page also has a «Settings» button. The page lists
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
see `docs/modules/authoring.md`). Settings shows it with «own» and «Needs trust»; nothing of it runs yet. «Trust…»
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
- *Enable it* on the Settings screen (Publishing → Vercel → «Connect»: the token and,
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

**System Vercel CLI.** Choose «System Vercel CLI» in the setting `auth` (labelled «Вхід у Vercel»; Settings → Vercel, or the wizard);
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
| `POST /api/task-new` `{id, title?, space?, from?, vcs?, …}` | create a task. `vcs` — `{repo, path?, branch?}`, the task's own repository (needs a `vcs` module in the space: `400 vcs-needs-role`; the module checks the address, branch and folder: `400 vcs-bad-target`); if `path` of that repository already holds an `index.html`, the first iteration is taken from it, and if it cannot be fetched the task starts with a blank page. `from` — an absolute path (`~` is expanded; a relative one is `from-not-found`) to a folder with an `index.html` that the server copies into the first iteration (any space; not together with `gitlab`; symlinks, `.git`, `node_modules` are not copied; ≤ 2000 files and 200 MB); the answer then carries `copied: {files, bytes, skipped_links}` — what was actually copied. `gitlab` (clone a repository into the task) needs a space whose `vcs` record has the LIGA scheme, otherwise `400 gitlab-needs-vcs-scheme`; `from` with `gitlab` is `400 bad-request`. Without `space` the task goes to the first space marked `legacy`, otherwise to the current one. Refusals: `400 gitlab-needs-vcs-scheme\|from-not-found\|from-no-index\|from-contains-space\|bad-request`, `409 task-dir-exists`, `413 from-too-big` |
| `GET /api/update` | the update state: `{state, available, current, latest, blocked, checked_at, remote_host, boot, restart_failed, …}`. A "machine" route: it works with a broken registry; `/t/<id>/api/update` is `400` |
| `POST /api/update-check` | check the remote's release tags now (a read-only `git ls-remote`); the same answer as `GET /api/update` |
| `GET /api/update-notes` | the CHANGELOG sections between the installed version and the latest, read from the remote tag; `{ok, notes}` or `{ok: false, reason}` with `busy\|offline\|disabled\|no-update\|no-git\|fetch-rejected\|tag-missing\|tag-conflict\|no-changelog\|error\|bad-remote\|no-remote`; a cross-site request is `403` |
| `POST /api/update-apply` | install the latest tag (fetch with fsck, a re-check of the tag, `--ff-only`, a smoke test, restart); `202 {ok, to, restart: auto\|manual}`; refusals `409 isolated\|busy\|nothing-to-update\|not-git\|dirty\|detached\|worktree\|diverged\|tag-conflict\|tag-missing\|tag-mismatch\|fetch-rejected\|disabled\|bad-remote\|no-remote`, `503 offline`, `500 error\|merge-failed\|rolled-back\|rollback-failed` |
| `POST /api/feedback-preview` `{task?, it?, node?, screen?, lang?, client_errors?}` | exactly what a feedback would send: `{ok, diag, diag_hash, ring_seq, shot: {available, bytes?, skipped?}}` |
| `POST /api/feedback` `{kind: bug\|idea, text, contact?, include_diag?, include_shot?, diag_hash?, ring_seq?, …}` | queue and send a note: `{ok, id, state: sent\|queued, reason?, memory_only?}`, `reason` is `no-collector\|offline\|rejected\|network-blocked`; `409 diag-changed` (the diagnostics changed since the preview), `413 body-too-large` |
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
channel; enabling one adds it. A migrated legacy (in-house) space has its shared Supabase as an
ordinary `supabase-comments` record (since 0.21 there is no implicit provider): **a disabled or
removed record means no team comments** in that space, and nothing brings the shared service
back. If an enabled module is
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
4. Enable the module on the Settings screen (Team comments → Supabase → «Connect»: the
   project URL and the public key), or over the API:

   ```bash
   curl -s localhost:8765/api/module-enable -H 'Content-Type: application/json' \
     -d '{"space":"<id>","id":"supabase-comments","settings":{"url":"https://<ref>.supabase.co"},"secrets":{"key":"<public key>"}}'
   ```

   The answer carries the verdict of `check`: `bad-key`, `no-schema` (run step 2), `network`.

**Addressee, assignment, news (0.27.0).** In a workplace with a team channel the compose form asks who the pin is for:
**Claude** (stays on this machine) or **the team** (goes to the service). The panel filter is «For Claude / Team / All»; «For Claude» is what Claude picks up — your comments for Claude plus team comments assigned to it.
**The agent sees only what was assigned to it:** `bin/inbox.py`, `bin/state.py` and `/comments` show local pins and team pins
with `meta.assignee = "claude"` («Assign to Claude» / «Take back» on a team card). `python3 bin/inbox.py --all` (or
`/comments?all=1`) shows every team pin. The history line «(+ N resolved in history)» counts only the assigned team pins by
default; `hidden` in `/comments` counts all hidden pins, resolved ones too. New team comments are marked in the panel, on the
island and on the tabs of other tasks (the optional `recent` function of the module feeds the tab numbers). If the team
channel is down, a strip says why and local pins keep working.

**Pin screenshots.** Set the optional `shots_bucket` (the name of a **public** Storage bucket of the
same project) and the browser adapter uploads the screenshot of a pin to
`<bucket>/comment-shots/<id>.jpg` and keeps the public address in the pin; without it pins have no
uploaded screenshot. The bucket and its policies are yours to create (details in the module README).

**The legacy (LIGA) space** keeps the address and the **public** key of its shared Supabase in its
`supabase-comments` record (the address in the settings, the key as a secret) — the migration of
0.17–0.21 copies them there, and you enter or rotate them on the **Settings** screen. **The old
sources are not read any more** (since 0.21): not the root of `tasks.json` (`supabase_url`,
`supabase_key`), not the environment variables `SUPABASE_URL` and `SUPABASE_KEY`, not
`pipeline-feedback`; a key added to the root by hand has no effect. The same address and key feed the
team dashboard and the Teams silence (the records of `supabase-dashboard` and `supabase-teams`).
Without the record the team comments of that space are off — the page shows the local pins and a
notice, and `inbox` reports `comments-unconfigured`. The screenshot bucket there is `overview-thumbs`.

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

**The comments panel (0.26).** In the work area and on the Overview the shell has its own «Comments» panel on the right. Open it
with the island button (it shows the number of open comments), the **C** key or ⌘K → «Comments»; **H** hides the pins while it is
open and **Esc** closes it. It lists open comments, comments from earlier iterations (with a «carry to the current one» action) and
closed ones — with «Done · It.N» and the explanation the agent left — and searches by text or by `#N`. The «Claude / Team» channel
switch sits in the panel header. The commenter's own handle and panel are hidden there (it only draws pins and the compose form);
published previews and `/commented` opened without `host=1` look exactly as before.

**Building the commenter.** Its source is in [`commenter/`](commenter/README.md). After changing it:
`cd commenter && npm ci && npm run build` — the build writes into `app/vendor/` and `commenter/build-stamp.json`, and
`tests/commenter-stamp.test.mjs` fails if the committed bundle does not match the source.

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
inside this tool's own repository, a folder that equals, lies inside or contains **another** space of this machine, a path longer than 1024
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
4. Settings → «Team dashboard» → «Supabase dashboard» → «Connect» (or the same step of the new-space wizard). The key is
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

**Connect it:** Settings → «Issue tracker» → «Jira Cloud» → «Connect» (or the same step of the new-space wizard) with the
site address (`https://<site>.atlassian.net`), the e-mail of your Atlassian account and an **API token** (create it in the
security settings of the Atlassian account; the key is kept in `~/.deai/secrets.json`, owner only, and never goes into a page).
«Check» says «connected», or «Jira rejected the email or token» for a wrong pair. The details and the network calls are in
[the module README](app/modules/jira-tracker/README.md).

**When it does not answer.** The banner «Issue tracker unavailable: …» appears over «Mine» (with «data as of HH:MM» when older
statuses are still shown); «Try again» asks again, and the badges of the last good answer stay. A task key that Jira does not
know fails the whole batch of keys (Jira answers HTTP 400 to the query) — fix that key.

**The LIGA space** reaches its Jira through the same module, and since 0.21 only through its explicit `jira-tracker` record: the
address, the email and the token are entered on the **Settings** screen (the migration copied the old values there). The old
sources — `jira_base`, `jira_email`, `jira_token` in the root of `tasks.json`, `JIRA_EMAIL` and `JIRA_TOKEN` in the environment, the
two files in `~/.claude/pipeline-feedback/` — are not read any more. Without the record that space has no statuses, and when its
tasks carry Jira keys «Mine» says that Jira is not configured.

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
4. Settings → «Teams notifications» → «Supabase Teams» → «Connect» (or the same step of the new-space wizard) with the project
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

**Connect it.** Settings → «Git sync» → «Git» → «Connect»: the repository (the default for the tasks of the space; it
may stay empty and be given per task), the branch (`main`), the folder in the repository (`mockup/{task}` — `{task}` is the
task id), and, optionally, an SSH key and a server IP (for a VPN where the server's name does not resolve; only for
scp-style addresses, `[user@]host:path` — not for `ssh://`, `https://`, `file://` or a local path). «Check» asks the repository for the branch (`git ls-remote`, 4 seconds). The same section is
in the new-space wizard, step 2.

**A repository per task.** «New task» has an optional «Repository» field (not in the in-house legacy space): empty means
the default of the module for the later sync, but the task starts from a blank page. Only a filled field (or a space
with integrations) makes the first iteration come from the repository: if `<path>` of the
new task already holds an `index.html` there, it is taken. A task without any repository has no sync, and the task bar offers «Configure repository…»,
which opens Settings on the Git card. Addresses: `ssh://`, `https://`, `file://`, `user@host:path` or an absolute local path.

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
as deprecated aliases with the same answers (they carry `Deprecation: true` and a `Link` to the `/api/vcs-*` successor; removal in 1.0). Codes: `vcs-offline`, `vcs-auth`, `vcs-bad-target`, `vcs-busy`, `vcs-error`. To write a
provider of this role yourself, see [`docs/modules/authoring.md`](docs/modules/authoring.md), *The `vcs` role*.

**Limits.** HTTPS works only when git already has the sign-in saved; the retry through `host_ip` covers only
scp-style addresses (`[user@]host:path`); Windows is not checked on a real machine; a token placed in the user position of an address
(`https://TOKEN@host/…`) is accepted and sits in the task file in plain text, though it is hidden from every answer and
text. The full list is in `CHANGELOG.md`, 0.8.0.

## Feedback and updates

**Updates.** The canvas checks the release tags `vX.Y.Z` of the remote it was installed from (`git ls-remote`, read-only; first
check shortly after start, then every 6 hours). When a newer tag exists, a pill appears in the bar; it opens «What's new» (the
CHANGELOG sections of the new releases) and the button to update, as a popover under the pill (from ⌘K it is a centred card). Updating fetches the tag, fast-forwards the checkout, runs a smoke test
and restarts; on a failed smoke test it goes back to the previous commit. It refuses, with the command to run by hand, when
the folder is not a git checkout, has local edits, a detached head or local commits. Windows: the update applies, the restart is manual.
- `DEAI_NO_UPDATE_CHECK=1` turns the update checks and the background feedback retries off (no network from them; a feedback
  you send by hand still goes to a configured collector).
- `DEAI_UPDATE_REMOTE=<remote name, https:// or ssh:// address, user@host:path, or an absolute local path>` overrides the remote.
- The update trusts the tag on the remote: use a remote you trust (tag signatures are planned).

**Install & updates.** Deai installs and updates from the public GitHub repository over https: no account, no key, no VPN.

    git clone https://github.com/neodisa/deai-canvas.git
    cd deai-canvas && ops/canvas-app/install.sh

After that the in-app button (the pill in the bar → «What's new» → update) is the way to update: it follows the release tags
`vX.Y.Z` of the remote the checkout was cloned from. A release is published by pushing exactly the branch and the tag, by name:
`git push <remote> main vX.Y.Z` (not `--tags`, `--mirror` or `--all`: local tags such as `backup-*` must not travel). A private
mirror is optional: clone from it instead, and the updater honours the clone's own `core.sshCommand` (0.24.0), so a mirror behind
its own SSH key works without any global setting.

**Feedback.** The button «Відгук» opens a popover above it (⌘K «Баг / ідея» opens the same form as a centred card): kind, text, optional contact, and a preview of the diagnostics
that will be sent. A closed popover keeps your draft until it is sent. Nothing leaves the machine before you press send.
- *Collected, if you leave it on:* the Deai version, the operating system and Python version, the language, the kind of space and the ids of
  its built-in modules (own modules show as `own`), the task, iteration and page ids, the last 50 server errors (the exception type and the application
  frame only, no messages) and the last 20 errors of the page, and, if you tick it, the screenshot of the current page (webp or png up to 2 MB).
- *Redacted:* absolute paths shrink to the last segment, local canvas URLs keep only the extension, e-mails, `user:pass@`, tokens and key-like
  strings, labelled secrets, card and IBAN numbers and any run of 8 or more digits are hidden; no task titles, no settings, no secrets.
- *Where the queue lives:* `<DEAI_HOME>/feedback/{outbox,sent,failed}/` (default `~/.deai`). The record is written before any
  network call and retried every hour; after 20 attempts or 30 days it moves to `failed/` and is never deleted.
- *The collector* is the owner's own Supabase project: run `ops/feedback-collector.sql` (insert-only for the public key, a private bucket for screenshots,
  a throttled Teams card through a webhook kept in Vault). Point a copy of Deai at it with `DEAI_FEEDBACK_URL` and
  `DEAI_FEEDBACK_KEY`, or `{"feedback": {"url": "https://…", "key": "…"}}` in `<DEAI_HOME>/config.json`; the order is environment, then `config.json`,
  then `app/feedback.json`. Only `https://` addresses are used. An empty `DEAI_FEEDBACK_URL` turns the collector off (nothing is read from `config.json` or `app/feedback.json`). Without a collector the notes stay in `outbox` and the dialog says so.

## Layout

```
app/          server (serve.py, stdlib only) + UI (ES modules, no build step)
app/modules/  built-in modules (static-publish, vercel-publish, css-tokens, supabase-comments, supabase-dashboard, jira-tracker, supabase-teams, git-sync); the core is app/deai_modules.py
docs/         design notes and the guides for module authors (docs/modules/authoring.md, docs/modules/comments.md); docs/screenshots/ is the README images
bin/          CLI tools: snapshots, pages, state, inbox
ops/          macOS launcher, feedback collector SQL (Design Canvas.app), preview gate tools, ops/readme-shots.mjs (regenerates docs/screenshots on demo data)
flows/demo    example flow
tests/        unit, Python and live (Playwright) tests
```

## LIGA migration

The in-house LIGA space moves its config into its own `space.json` and `secrets.json` by itself, once, when the canvas starts
(right after the port is bound, before the first request is served; a busy port stops the start before anything is migrated). The old file and the environment are not touched; a dated backup is made first. From the command line:

```
python3 bin/migrate_liga.py status                      # the mark, the last report, the backups
python3 bin/migrate_liga.py dry-run                     # what would be migrated; nothing is written, no secret is printed
python3 bin/migrate_liga.py run                         # migrate now (backup -> secrets -> space.json)
python3 bin/migrate_liga.py restore <stamp> [--hold]    # put back space.json and the LIGA secrets from <DEAI_HOME>/backups/<stamp>
```

Credentials go in on the **Settings** screen. Before the first start of the migration the old values must be in the root of
`tasks.json` (a first start from the Dock/PWA has no environment, so the shell variables are not enough, and `pipeline-feedback` is
not read by the runtime any more); a role that had nothing to migrate from (`no-jira`, `no-supabase`) is not retried — add its card on
Settings. The start line and `status` list every role that is **off**, with its reason code and the command to fix it (a role that was
not migrated is simply off since 0.21; `python3 bin/migrate_liga.py unhold <mark>` lifts a manual hold).
Upgrading: after the migration the Jira token, the Supabase key and the preview password of LIGA live in `secrets.json`, and the
git key and the host IP in the settings of `git-sync`; **the old sources (the root of `tasks.json`, the environment, `pipeline-feedback`) are
not read by Deai any more**, and a root key edited by hand after the migration has no effect. Rotate on the Settings screen.
Migrated tracks are a snapshot: edit `tracks` in the LIGA `space.json`, not `design_work_roots`/`profile_repos` in the old file.

**Where a value lives now (the map «key → holder»).** Look for it on the Settings screen:

| Old place (root of `tasks.json`, environment, `pipeline-feedback`) | Holder since 0.21 |
|---|---|
| `supabase_url`, `SUPABASE_URL` | the setting `url` of `supabase-comments`, `supabase-dashboard`, `supabase-teams` |
| `supabase_key`, `SUPABASE_KEY` (and `SUPABASE_SERVICE_KEY` for `bin/overview_push.py`) | the secret `key` of the same three records |
| `jira_base`, `jira_email` | the settings `base`, `email` of `jira-tracker` |
| `jira_token`, `JIRA_TOKEN` and the `pipeline-feedback` files | the secret `token` of `jira-tracker` |
| `gitlab_ssh_key`, `gitlab_host_ip` | the settings `ssh_key`, `host_ip` of `git-sync` |
| `preview_password` | the secret `password` of `vercel-publish` (a password of a task wins over it; without either, `1100`) |

**Five steps.** The migration is an ordered list of independent steps, each with its own mark, its own dated backup and its own
restore: `liga-4d3a` (0.17: tracks and the roles `tracker`, `dashboard`, `notify`), `liga-4d3b` (0.18: the roles `comments` and
`vcs` as the built-in modules `supabase-comments` and `git-sync`, with the setting `compat` that keeps the old channels, flat
mirrors and «design-canvas» / «GitLab» texts), `liga-4d3c` (0.19: the role `publish` as the built-in module `vercel-publish`
with `compat: design-canvas`, which keeps the projects and the scope of `tasks.json`, the preview password and the old URLs; no
secrets are written), `liga-4d4a` (0.20: the tracks of the old adapter are written into `space.json` whenever it still applied,
and an old task record that has a `profile` but no `track` gets `track = profile`, with `tasks.json.bak` next to the file; the
start line prints the notes of the step) and `liga-4d4b` (0.21: the last originals are copied — `gitlab_ssh_key` / `gitlab_host_ip`
into `git-sync`, `preview_password` into the secret of `vercel-publish` — and then every original whose value provably lives in a
record is removed from the root of `tasks.json`, with `tasks.json.bak` next to the file; a root password that differs from the
secret replaces it, and the old secret stays in the backup). One start runs them in order (a jump from 0.16 gives five backups,
`<stamp>-liga-4d3a`, `-4d3b`, `-4d3c`, `-4d4a` and `-4d4b`); an `abort-*` or `skip-busy` of a step stops the later ones at that start. A LIGA with
`integrations` off is not migrated at all (`skip-integrations-off`). `status`, `dry-run` and `run` print every step; the journal
`<DEAI_HOME>/migrations/last.json` keeps the report of the last action and a map `steps` with the report of each step.

**Restore is LIFO.** `restore <stamp>` finds the step by the name of the backup and puts back `space.json` and the LIGA secrets as
they were before that step. While a later step is applied, restoring an earlier one is refused (`refuse-later-applied`, exit code 1,
nothing is written; the message names the backup to roll back first). `restore` first saves the current files to
`backups/<stamp>-pre-restore/`. `--hold` keeps the next start from migrating that step again, and a held earlier step holds
the later ones too.

⛔ Before downgrading from 0.21 to 0.20 run `python3 bin/migrate_liga.py restore <stamp-e> --hold` (the stamp of the `liga-4d4b`
backup): it puts back `space.json` and the secrets and **merges the deleted keys back** into the live `tasks.json` (a key a person
wrote there after the step is kept). Without it 0.20 has no preview password, no git key for the registry and no fallbacks. Then,
if needed, the older steps in reverse order. `tasks.json.bak` is a manual rollback only.

⛔ Before downgrading from 0.20 to 0.19 run `python3 bin/migrate_liga.py restore <stamp-d> --hold` (the stamp of the `liga-4d4a`
backup). It puts back `space.json` only: `tasks.json` is the live file of the person, so it keeps `track = profile` (safe for 0.19),
and `tasks.json.bak` is a manual copy.

⛔ Before downgrading from 0.19 to 0.18 run `python3 bin/migrate_liga.py restore <stamp-c> --hold` (the stamp of the
`liga-4d3c` backup): 0.18 ignores `compat` of `vercel-publish`, so the module path would be taken: a new project and a new URL
for every published task, and the preview without the gate. To 0.17: `restore <stamp-c> --hold`, then `restore <stamp-b> --hold`
(0.17 ignores `compat` of the comments and git sync, so the comment channels would switch to `deai/<space>/<task>` and the git mirrors would
be cloned again under `<DEAI_HOME>/cache`). Rotation: the Supabase key of the comments is a copy in `secrets.json` too (rotate it on
Settings); since 0.21 `gitlab_ssh_key` / `gitlab_host_ip` of the root are copied into `git-sync` by the fifth step and the root is not read.

Known limits: a downgrade needs the `restore ... --hold` above (to 0.16: `restore <stamp-d> --hold`, `<stamp-c>`, `<stamp-b>`, then `<stamp-a>`, since an earlier step is refused while a later one is applied); a `vercel-publish` card enabled by hand without `compat` publishes through the module path (new URLs, no gate); the fourth step writes the tracks even when they differ from the old adapter (the differences are notes of the step, see `CHANGELOG.md`), except for more than 20 track ids, which stays `abort-tracks` until `profile_repos` / `design_work_roots` are cleaned; a LIGA folder inside a git work tree is not
migrated; a partial migration is final; the copies of the credentials are in the Deai home (`secrets.json` and `backups/`) and in `tasks.json.bak` (mode 0600), and `skip-path-in-git` keeps the roles of LIGA off until the folder leaves the git work tree. The full list and the status codes are in `CHANGELOG.md`, `[0.21.0]`, `[0.20.0]`, `[0.19.0]`, `[0.18.0]` and `[0.17.0]`.

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
   - ✅ **3a** (0.5) — the Connections screen (called Settings since 0.25): connect, configure, check, replace and turn off
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
     - ✅ **4d-2** (0.16) — the implicit provider (`app/implicit.py`) instead of the literal `'legacy'`, one layer-off seam
       (`spaces.effective_space()`) and one isolation law: an isolated run reads the install config only from the root of its
       tasks file; the public contract (`capabilities` = `'legacy'`) is unchanged;
     - ✅ **4d-3** — explicit LIGA modules, with an automatic migration of its config (with a backup); the API value `'legacy'`
       stays for a non-migrated LIGA until 4d-4c (0.22). Three releases (owner decision 05.11.2026):
       - ✅ **4d-3a** (0.17) — the migration mechanism (a dated backup, a mark, a restore, the CLI `bin/migrate_liga.py`), the
         explicit tracks, and the roles `tracker`, `dashboard` and `notify` as explicit modules; the setting `compat` replaces
         `ctx['legacy']`;
       - ✅ **4d-3b** (0.18) — the roles `comments` and `vcs` as explicit modules, through a second migration step
         (`liga-4d3b`, LIFO restore); the setting `compat` of `supabase-comments` and `git-sync` keeps the old channels, the flat
         mirrors and the texts; the isolation law covers both roles;
       - ✅ **4d-3c** (0.19) — the role `publish` as the explicit module `vercel-publish` with `compat: design-canvas`, through a
         third migration step (`liga-4d3c`, LIFO restore on three steps); one predicate, `publish_legacy_path`, keeps the
         projects, URLs and the preview password of LIGA;
     - **4d-4** — the `integrations` flag and the old aliases go. Three releases (the first split of 4d-4, 07.11.2026):
       - ✅ **4d-4a** (0.20) — the tracks of LIGA are explicit for good (a fourth migration step, `liga-4d4a`, LIFO restore on
         four steps), the implicit track adapter leaves the runtime, and `profile` is read on the boundaries only (`task-new`,
         the shared registry, `_liga_flow`);
       - ✅ **4d-4b** (0.21) — the last copies (`gitlab_ssh_key` / `gitlab_host_ip` into `git-sync`, the preview password into
         `vercel-publish`) by a fifth migration step (`liga-4d4b`), the implicit provider goes, the core stops reading the originals
         (the root of `tasks.json`, the environment, `pipeline-feedback`; deleting those is not Deai's job: they are shared with the
         separate LIGA tool); a LIGA that was not migrated has all six roles off, named at the start;
       - ✅ **4d-4c** (0.22) — the `integrations` flag, the API value `'legacy'`, the fallback branches of the JS, `_liga_flow`
         and the `/api/gitlab-*` aliases leave the runtime: an outbound action (autopush, the team registry, the shared ssh key) is
         decided by the `vcs` record with the LIGA scheme, `static-publish` is an explicit record, the dashboard sync log is one
         (`<DEAI_HOME>/logs/dashboard-sync.log`); the `/api/gitlab-*` routes stay as deprecated aliases until 1.0.
5. ✅ **Feedback and updates** (0.23) — the «Відгук» button with a redacted diagnostics preview, a local queue and an owner-run Supabase collector;
   the update pill, «What's new» and a one-click update from release tags of the remote.
6. **Claude Code plugin** — a generic task → mockup → iterations → review → publish loop.
7. **Cross-platform start** — one command on macOS, Windows and Linux.

## License

MIT © neodisa
