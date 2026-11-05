# Spaces, modules and onboarding — design (draft)

Status: agreed direction, 2026-10-09. Clickable prototype reviewed by the owner.
Built so far: stage 1 (spaces, 0.1.0), stage 2a (module framework, publishing to a
folder, tokens from CSS, 0.2.0), stage 2b-1 (publishing to your own Vercel, 0.3.0),
stage 2b-2 (the universal `comments` role and your own Supabase, 0.4.0), stage 3a (the
Connections screen, 0.5.0), stage 3b (the new-space wizard, 0.6.0), stage 3c (a space's own
modules with a trust dialog, 0.7.0), stage 4a (git sync as the `vcs` role and the `git-sync` module, 0.8.0) and stage
4b-1 (the in-house publishing through `vercel-publish`, 0.9.0), stage 4b-2 (the in-house comments through
`supabase-comments`, 0.10.0), stage 4b-3 (task tags instead of profiles on the «Tasks» screen, 0.11.0), stage 4c-1 (the
team dashboard as the role `dashboard` and the module `supabase-dashboard`, 0.12.0), stage 4c-2 (tracker statuses as the
role `tracker` and the module `jira-tracker`, 0.13.0) and stage 4c-3 (the Teams notifications as the role `notify` and the
module `supabase-teams`, 0.14.0) and stage 4d-1 (the profile of a task becomes the general tracks of a space, 0.15.0) — see
*Status* at the end.
Next: stage 4d-2 — the layer-off seam and the isolation of shared state without the literal `'legacy'`; stage 4d goes on to
4d-3 and 4d-4 and ends with the original setup becoming an ordinary space.

## Goal

Deai Canvas is independent of any company. One installation serves many projects;
each project brings its own integrations. The core is a functional base; everything
company- or team-specific is a module you connect per project. Anyone can extend the
canvas for their workflow without touching the core.

## Spaces

- A **space** is a company, a client, or your own work. It is a folder on disk:
  - `space.json` — name, colour/icon, enabled modules and their (non-secret) settings;
  - the space's tasks (iterations, pages, snapshots, comments);
  - `modules/` — the space's own modules.
- **Secrets** (tokens, keys) never live in the space folder: they go to
  `~/.deai/secrets.json` (user-only permissions). A space folder can be committed to git
  and shared with a team.
- Known spaces are listed in `~/.deai/spaces.json`. The UI has a space switcher (Tasks
  screen title, ⌘K, task switcher). Tasks inherit the modules of their space.
- Migration: an existing `tasks.json` becomes the first space automatically.

## Modules

- A **module** is a folder: `module.json` (what it does, which settings to ask for:
  text / secret / path / select) + `server.py` (functions for its role) + `check()` for
  the «Check» button.
- **Roles** (the interfaces the core calls):

  | Role | Built-in modules |
  |---|---|
  | Mockup sync (`vcs`) | Git (GitHub, GitLab, any remote) |
  | Team comments (`comments`) | Supabase (your own project), via CommentLayer; any other service through a module that follows `docs/modules/comments.md` |
  | Publish previews (`publish`) | Static folder (always available), Vercel |
  | Design-system tokens (`tokens`) | CSS custom properties file or npm package |
  | Issue tracker (`tracker`) | Jira Cloud, through `jira-tracker` (Linear and others as modules later) |
  | Team dashboard (`dashboard`) | Supabase (your own project), through `supabase-dashboard` |
  | Notifications (`notify`) | Supabase (your own project), through `supabase-teams`: a card in Teams for every new comment, the silence per channel |

- Built-in modules ship in `app/modules/`; a space's own modules live in
  `<space>/modules/` and are loaded the same way — but only after the person trusts them
  (stage 3c, 0.7.0: a trust dialog in Connections). A
  module may implement an existing role
  (e.g. publish to Netlify) or add its own integration (e.g. notifications to a chat).
- **Nothing is required.** Without modules the canvas works fully: local comments for
  the agent, publishing into a folder, the inspector without a design system.

## Onboarding

- **First run** (no spaces): a wizard — space name, colour and folder → pick modules by
  role → settings with «Check» → first task (new / adopt an existing folder of HTML /
  let the agent create it). The same wizard serves «New space…». *Built in stage 3b
  (0.6.0)* — see *Status → Stage 3b*.
- **Connections** screen per space: module cards with status (connected / error with the
  reason / off), configure in a side panel (secrets marked as stored outside the space),
  check, disable. *Built in stage 3a (0.5.0)*: entered from the space menu, ⌘K, or the head
  of «Tasks» in a space without integrations; cards grouped by role with a «Now: …» line;
  secrets shown only as set / not set / unknown; replacing the provider of a role in one
  step; turning a module off with its consequences. See *Status → Stage 3a*.
- **A space's own modules** from `<space>/modules/`, loaded only after the person trusts
  them in a dialog (shown on the Connections screen, with an «own» mark on the card).
  *Built in stage 3c (0.7.0)* — see *Status → Stage 3c*.
- **Agent**: the same operations over the HTTP API, so you can ask the agent
  «connect my GitHub repo and the tokens from this CSS file to space X».

## Stages

1. ✅ Spaces + migration of the existing `tasks.json` (0.1.0).
2. Module system: extract built-in modules from the integrations that are hard-wired today
   (git sync, Supabase comments, Vercel publishing, design tokens, tracker statuses). Split
   into three parts:
   - ✅ **2a** (0.2.0) — the framework, `static-publish`, `css-tokens`;
   - ✅ **2b-1** (0.3.0) — your own Vercel (publish);
   - ✅ **2b-2** (0.4.0) — the `comments` role and your own Supabase (team comments);
   - the in-house integrations follow as stage 4: git sync first (4a), then the team dashboard, tracker
     and team chat notifications as that company's modules.
3. Onboarding, split into three parts:
   - ✅ **3a** (0.5.0) — the Connections screen;
   - ✅ **3b** (0.6.0) — the new-space wizard (space → modules → settings → first task);
   - ✅ **3c** (0.7.0) — a space's own modules from `<space>/modules/` with the trust dialog.
4. Company-specific integrations move out of the core into modules. The goal is a clean core plus parity: everything
   the legacy space does becomes a module, so that space can later be an ordinary one. Four releases:
   - ✅ **4a** (0.8.0) — git sync: the `vcs` role and the `git-sync` module;
   - **4b** — the legacy publishing and comments move onto the existing modules (`vercel-publish`,
     `supabase-comments`); the hard-wired constants and the profiles go. Three releases:
     - ✅ **4b-1** (0.9.0) — publishing: `vercel-publish` gets the sign-in «System Vercel CLI» and the legacy space
       publishes through it;
     - ✅ **4b-2** (0.10.0) — comments: the legacy space keeps its comments through `supabase-comments`; the Supabase
       constants leave the code;
     - ✅ **4b-3** (0.11.0) — the profiles: general task tags; the profile table moves to `tasks.json`;
   - **4c** — the roles `dashboard`, `tracker` and `notify` in the core, and the team dashboard, tracker statuses and
     team chat notifications as modules of that company. Three releases:
     - ✅ **4c-1** (0.12.0) — the team dashboard: the role `dashboard`, the module `supabase-dashboard`; the legacy space
       goes through it as an implicit provider;
     - ✅ **4c-2** (0.13.0) — tracker statuses: the role `tracker`, the module `jira-tracker`; the legacy space goes through it
       as an implicit provider;
     - ✅ **4c-3** (0.14.0) — Teams notifications: the role `notify`, the module `supabase-teams` with its own `schema.sql`; the
       legacy space goes through it as an implicit provider;
   - **4d** — the `integrations` flag goes. Split into four releases (owner decision 04.11.2026):
     - ✅ **4d-1** (0.15.0) — the profile of a task becomes **tracks of a space** (`tracks` in `space.json`, the key `track` of a
       task); the LIGA space gets its three tracks from an implicit adapter, `profile` stays a synonym;
     - **4d-2** (0.16.0) — the layer-off seam (a space with the layer switched off) and the isolation of shared state, without the
       literal `'legacy'`;
     - **4d-3** (0.17.0) — explicit LIGA modules, with an **automatic migration of its config with a backup**: the same
       migration also writes its tracks into its `space.json`, and the adapter of 4d-1 goes;
     - **4d-4** (0.18.0) — the `integrations` flag and the old aliases (`profile`, `gitlab_*`) go.
5. Agent API + a lightweight Claude Code plugin (task → mockup → iterations → review → publish).

Each stage gets its own spec, plan and tests.

## Status

### Stage 1 — spaces (0.1.0)

Done as described under *Spaces*: registry in `~/.deai/spaces.json`, automatic migration of
a legacy `tasks.json`, a space per request, an integrations kill-switch, a space switcher.

### Stage 2a — modules (0.2.0, 16.10.2026)

Spec (with the list of deviations from its second revision):
`docs/superpowers/specs/2026-10-14-modules-2a-design.md`. What is built:

- **Framework** (`app/deai_modules.py`): manifest, `exec`-loading of `server.py`, per-space
  settings in `space.json`, secrets in `<DEAI_HOME>/secrets.json`, one provider per role,
  `capabilities` (`{publish, tokens}`) in the task and space responses. Roles called by the
  core at 2a: `publish`, `tokens`; the others were reserved (at 2a; since 4c-3 none is: every role is called).
- **`static-publish`**: publishes the preview to a folder **outside** the space (default
  `~/deai-published/<space-id>/<task>/`), implicit in a space without integrations. The
  folder is re-checked on every publish and serve; replacement is marker-guarded and done as
  two renames (old folder aside, new one into place), so a request landing between them
  gets a brief 404.
  A local sandboxed copy is served at `/published/<space-id>/<task>/`.
- **`css-tokens`**: tokens from one CSS file (`:root`, `html`, `[data-*theme*]`, Tailwind v4
  `@theme`) for the inspector, through `GET /api/ds-tokens`.
- **Module API** (`/api/modules`, `/api/module-enable|disable|settings|check`) and a minimal
  UI: the publish zone follows `capabilities.publish`; a local publish shows a persistent
  notice with «Open». The Connections screen is **not** built — modules are managed over
  the API (the agent can do it, as the *Onboarding* section intends).
- The hard-wired in-house code path (Vercel publishing, git sync, dashboard, team comments)
  is untouched: it still runs only in a space with `integrations: true`.

### Stage 2b-1 — your own Vercel (0.3.0, 16.10.2026)

Spec (with the list of deviations from its first revision):
`docs/superpowers/specs/2026-10-16-vercel-publish-design.md`. What is built:

- **Contract of the `publish` role extended.** A manifest may carry `publish_target`:
  `folder` (the default, as in 0.2) or `url`. A `url` module has no folder and returns
  `{url, state, verified, warnings?}`; the core validates the result (strict `https://`
  address, a flat `state` of at most 4096 characters, no secret of the module in the
  result), records `publish_url`, `published_at`, `publish_verified` and `publish_remote`
  in `iterations.json`, hands `state` back on the next publish, and in `/api/task` adds
  `publish_remote`, `publish_gate`, `publish_gate_stale` and `publish_share_url`. The legacy
  path and `folder` modules answer exactly as before.
- **`vercel-publish`**: publishes the preview to the person's own Vercel account over the
  REST API — no Node, no CLI, standard library only. Settings `token` (secret), `team`,
  optional `password` (secret). One opaque project `pv-<8 digits>` per task; files by SHA-1,
  a production deployment, wait for `READY` and the permanent address, a check that it opens
  without signing in, cleanup of old deployments (three kept). The token reaches only
  `api.vercel.com`. Not enabled implicitly: `static-publish` has to be turned off first.
- **UI**: a persistent «Published on Vercel» notice with «Open» and «Copy link» (the link
  carries `#k=<password>` for a protected preview), the module's warnings as text, a
  «the preview is public» note in the publish dropdown when there is no password, and human
  texts for `vercel-auth`, `vercel-busy` and `module-error`. The module is managed over the
  API (the Connections screen is still stage 3).
- **Not verified against the real Vercel**: the module is tested against a faithful fake
  API; the first live run should confirm the alias timing after `READY`, the item shape of
  `GET /v6/deployments`, the team-by-slug check and the invalid-token error body.

### Stage 2b-2 — the `comments` role and your own Supabase (0.4.0, 19.10.2026)

Spec (with «Відхилення (стан на 0.4.0)»): `docs/superpowers/specs/2026-10-19-comments-role-design.md`.
Guide for module authors: `docs/modules/comments.md`. What is built:

- **The role `comments` is a contract that does not depend on the service**, in two halves: a
  browser adapter (`window.DeaiComments.create(cfg)` → the comment layer's store, files listed in
  the manifest field `client` and served at `GET /api/module-client/<id>/<file>`) and the server
  functions `client_config`, `list`, `resolve`, `check`. The core builds the channel
  (`deai/<space>/<task>`), checks `client_config` (only values of secrets marked `"public": true`
  may appear in it) and puts the adapter into the canvas pages, the Overview, the published
  previews of both publish modules and the agent's `inbox`. Without a module the space has no team
  channel; a migrated legacy space keeps its shared service until a module is enabled in it, and
  a broken module never falls back to that shared service.
- **`supabase-comments`**: your own Supabase project (a schema you run once, a public key,
  supabase-js 2.110.0 vendored, no CDN). Proof of universality: the test module `memo-comments`
  (a tiny HTTP service) passes the same end-to-end checks, live included.
- **Not verified against a real Supabase** (a faithful fake REST server in CI).

### Stage 3a — the Connections screen (0.5.0, 20.10.2026)

Spec: `docs/superpowers/specs/2026-10-20-connections-screen-design.md`; plan:
`docs/superpowers/plans/2026-10-20-connections-screen.md`. What is built:

- **The screen** is a page of the home overlay (next to «Tasks»), entered from the space menu
  («Connections…»), from ⌘K, and from a button in the head of «Tasks» in a space without
  integrations. It shows module cards grouped by role with a «Now: …» line (who provides the
  role, from `capabilities`), the state of each module and the reason for an error in plain words;
  a side panel for settings and secrets (a secret is only ever «set / not set / unknown» and is
  never shown); check; replacing the provider of a role with a confirmation; turning a module
  off with its consequences. UI texts in Ukrainian and English. The legacy space is unchanged.
- **`replace` in `POST /api/module-enable`**: one write of `space.json` turns off the modules
  that hold the roles of the one being enabled (the implicit `static-publish` included) and
  turns the new one on — the space is never without a provider between the two steps. The
  answer lists them in `replaced`. A module that did not load cannot be a target of `replace`
  (`module-error` / `bad-manifest`). The screen asks for consent again against a fresh list
  before it sends `replace`.
- After a change the bar and `capabilities` are refreshed lightly, without resetting the
  picked iteration, filters or notices of the task under the overlay.
- **Not verified against a real Vercel or Supabase**: the live tests use a local fixture
  module (`tests/fixtures/modules-conn/`), because the `check` of those two goes to the network.

### Stage 3b — the new-space wizard (0.6.0, 22.10.2026)

Spec: `docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`; plan:
`docs/superpowers/plans/2026-10-21-first-run-wizard.md`. What is built:

- **The wizard** is the third page of the home overlay (`wiz`, next to «Tasks» and «Connections»):
  Space → Modules → Settings → First task. The first run and «New space…» (space menu, ⌘K) open the
  same page; the «New space» dialog is gone (the space dialog stays for «Name and colour…»). The
  space is created for real on step 1, so closing the wizard anywhere leaves a working space.
- **Steps 2 and 3 reuse the model and the fields of the Connections screen**: one choice per role
  («instead of …» names the provider it replaces — that is the consent), then one pass of writes
  (`module-enable` with `replace`, `module-settings`, `module-disable`) against a freshly read list.
  A role an agent changed in the meantime is refused, not overwritten; secrets live only in the
  field and are cleared after each answer.
- **`from` in `POST /api/task-new`**: step 4 can copy an existing folder with an `index.html` into
  the first iteration. Space without integrations only; every check and the walk come before any
  write; symbolic links, `.git` and `node_modules` are never copied; at most 2000 files and 200 MB;
  the task folder is claimed atomically and removed on any failure; the answer says what was
  actually copied.
- **Not verified against a real Vercel or Supabase**: as in 3a, the live tests use a local fixture
  module, because the `check` of those two goes to the network.

### Stage 3c — own modules and trust (0.7.0, 23.10.2026)

Spec: `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md` (revision 2 + the planning amendments listed in
`docs/superpowers/plans/2026-10-22-own-modules-trust.md`). What is built:

- **Own modules** in `<space>/modules/<id>/`: listed from the manifest, executed only from a trusted snapshot.
- **Trust**: the dialog shows files, sizes and the fingerprint; the operating system's own window is the boundary
  (`POST /api/module-trust` also accepts only the canvas page — `Origin` + `Sec-Fetch-Site: same-origin` — as a filter
  against an agent's `curl`, not as the boundary). Records in `<DEAI_HOME>/trust.json`, snapshots in
  `<DEAI_HOME>/trusted/`, untrust keeps `space.json`.
- **Roles on paper**: an own module that is on in the space but does not run here keeps its role and reports an
  error; no implicit or legacy fallback.
- **UI**: Connections (cards, notes, panel), the trust dialog, wizard step 2/3.

### Stage 4a — git sync as a module (0.8.0, 30.10.2026)

Spec: `docs/superpowers/specs/2026-10-26-git-sync-module-design.md` (revision 2 + the planning amendments);
plan: `docs/superpowers/plans/2026-10-26-git-sync-module.md`. What is built:

- **The `vcs` role** is called by the core: `status`, `push`, `pull` (and the optional `validate`, `mirror_dir`) on a
  *target* the core computes for the task — the task's own `vcs{repo, path?, branch?}`, in a space with integrations the
  older `gitlab{}`, then the module's settings. Five codes, `vcs-offline`, `vcs-auth`, `vcs-bad-target`, `vcs-busy` and
  `vcs-error`; `ctx["cache_dir"]` for every module. The module is a **transport**: the iterations, authorship, the
  «never send a colleague's work» rule and the new iteration made of a pull stay in the core.
- **`git-sync`**: any git remote through the system `git` (SSH key or saved HTTPS sign-in; Deai keeps no git secrets). One
  mirror clone per address in `<DEAI_HOME>/cache/<space>/git-sync/mirrors/`, one operation per mirror (a lock that works
  between processes), push without force, `pull --ff-only`, the address of the history for GitHub and GitLab.
- **The git transport left `serve.py`**; the old names of the core (`gitlab_cfg`, `gitlab_status`, `gitlab_sync`,
  `gitlab_pull`) and of the routes (`/api/gitlab-*`) stay as wrappers and aliases until 4d. New routes:
  `/api/vcs-status`, `/api/vcs-push`, `/api/vcs-pull`; `task-new` accepts `vcs`.
- **The legacy space runs on the same module** through an implicit provider (`'legacy'`), with its old mirror folders, the
  label «GitLab» and its commit text; `tests/legacy-golden.test.mjs` is green without a re-shoot.
- **UI**: a «Git sync» section and a Git card on Connections and in the wizard, a «Repository» field in «New task», the
  sync zone of the task bar and the palette for any space that has the role, with the service's label.
- **Tested** on local bare repositories (a path and `file://`); a real GitHub, GitLab or HTTPS server is not part of the
  tests, and Windows was not run on a real machine.

### Stage 4b-1 — legacy publishing through `vercel-publish` (0.9.0, 30.10.2026)

Spec: `docs/superpowers/specs/2026-10-30-legacy-publish-module-design.md` (and its «Поправки»); plan:
`docs/superpowers/plans/2026-10-30-legacy-publish-module.md`. What is built:

- **`vercel-publish` 1.1.0 has a second sign-in, the setting `auth`:** `token` (the REST code of 1.0.0, unchanged) or `cli`
  — the system Vercel CLI, `npx --yes vercel` under the `vercel login` of the computer, with no secret. `cli` does
  `link`, `deploy --prod`, `inspect` (the shortest `*.vercel.app` address), a check of the preview and then the cleanup
  of old deployments (3 kept, the current one among them; only `*.vercel.app` addresses of that project, with `--safe`,
  never a project name). Any space can use it; the state is kept in the same place as in `token` mode, `publish_remote.state`
  (`project`, `scope` and `task`; there is no `project_id`, the CLI works by name).
- **Framework additions for every module:** `ctx["find_tool"]("npx" | "node")` (the core registers its finder once,
  `deai_modules.set_tool_finder(_node_bin)`, and it runs only when a module asks), `ModuleError.full` (the whole text
  next to the 300-character `message`), `task["gated"]` and the optional publish-result keys `deploy_url`, `verify`,
  `cleanup_warning`. New codes: `no-node`, `vercel-login`, `vercel-scope`, `vercel-deploy`, `vercel-no-url`. The module
  returns **codes and raw output**; the human texts are built by the caller.
- **The legacy space publishes through the same module** (an implicit provider, `'legacy'`): `_publish_legacy_call` in
  `serve.py` is the only seam. It keeps what belongs to the company — the project name minted in `tasks.json`, the
  scope in `tasks.json`, the registry and the dashboard, `git_autocommit`, and the error texts (`_LEGACY_DEPLOY_HINTS`,
  `_LEGACY_PROTECTION_HINT`, `_LEGACY_NO_URL`) — so the answer of `/api/publish` has the same keys in the same order.
  `publish_remote` is still not written there.
- **The legacy space now cleans up old deployments too** (owner's decision of 30.10.2026); the answer may carry a last
  key `cleanup_warning`, shown by the publish dialog.
- **The Vercel transport left `serve.py`:** `_deploy_urls`, `_stable_alias`, `_check_published`, `_deploy_hint` and the
  `npx vercel` block. `tests/legacy-golden.test.mjs` is green without a re-shoot, and a snapshot of the 0.8.0 answer
  (`tests/fixtures/legacy-publish/before-4b1.json`) is compared with the new code.
- **UI:** the Vercel card and the wizard get the choice of the sign-in (the token field stays, labelled «for the token
  sign-in»); `check` in `cli` mode runs `vercel whoami` (`no-node`, `vercel-login`); publish texts for the new codes and a
  line for `cleanup_warning`.
- **Small conscious differences** from 0.8.0 for the legacy space are listed in the changelog (a human line for a deploy
  that fails with no output, headers of the preview check, a stricter check of the project name and the scope).
- **Known limits:** a random `pv-` name without a probe whether it is taken, and an empty project left after a failed
  deploy (ordinary space, `cli`); at most 5 pages of the deployment list; CLI 65.x flags; `cli` verifies the gate marker
  and `token` verifies HTTP 200; the preview check of `token` mode has no `certifi` context (backlog).
- **Tested** with a fake `npx` (no network, no real `vercel`); a real Vercel account and a real `vercel login` are not part
  of the tests.

### Stage 4b-2 — legacy comments through `supabase-comments` (0.10.0)

Status: done (the date and the tag are set at the release). Spec: `docs/superpowers/specs/2026-10-30-legacy-comments-module-design.md`
(and the «Поправки до спеки» of its plan); plan: `docs/superpowers/plans/2026-10-30-legacy-comments-module.md`. What is built:

- **`supabase-comments` 1.1.0:** the optional setting `shots_bucket` (the config gets `shotsBucket`, the adapter gets
  `uploadShot`), `resolve(…, iteration=None)` writing `resolved_v` (the core gives the number to the built-in module only,
  `ProjectComments.takes_iteration`; a space's own module keeps four arguments), TLS with `certifi` when it is installed.
- **The legacy space runs on the same module** (an implicit provider, `'legacy'`): `comments_route(space, prov)` gives
  `(module, ctx, channel)`; the channel is still `comment_project` / `dc/<task>` (+ `/internal`), the table is the same;
  `comments_client(…, ctx=None)` takes a ready `ctx` built from the installation, without `space.json` and `~/.deai`.
  The canvas page `/commented`, the published preview, `/api/comment-config`, the Overview, `inbox` and `state` go through the module.
- **The Supabase of the legacy space left the code:** `supabase_config()` reads `supabase_url`/`supabase_key` from the root of
  the legacy `tasks.json` (fallback: `SUPABASE_URL`/`SUPABASE_KEY`); the dashboard, the Teams silence and
  `bin/overview_push.py` take the same pair. Without it the comments are «unavailable» (code `comments-unconfigured`, 409)
  and the 4c parts are quiet.
- **Gone from the core:** the constants, the old snippet and injector, `INTERNAL_TINT`, `supabase_pins`, `patch_project_pin`,
  `project_body`, `state._open_pins`, `build_preview(comments=True)`; the old adapter lives on only as a test fixture.
  `BUNDLES`/`BUILD_KINDS` stay for `ops/reseal_gate.py` (builds before 0.10.0).
- **Conscious differences** (full list in the changelog): the markup of the module on the pages, supabase-js from its own copy,
  resolving filtered by channel and reporting a missing pin, the order and the ceiling of `list`, the anchor of a pin
  (`fp` text up to 2000, the last 50 of `path`), `--dry-run` and `state` lines. Previews published earlier are not touched.
- **Tested** against the snapshot of 0.9.0 (`tests/fixtures/legacy-comments/before-4b2.json`) and the old adapter kept as a
  fixture; no network and no real Supabase (the module's `_open` seam, intercepted requests in the browser tests).
- **Left for 4c / 4d:** (4b-3 — the profiles — is done, see below); 4c — the dashboard, tracker statuses and Teams silence as roles and
  modules (today they only read the pair from `supabase_config()`); 4d — the `integrations` flag and the literal `'legacy'` in `capabilities` go. Known limits: PostgREST
  `max-rows` can still cut `list`; `html2canvas` loads from jsdelivr; the key is in `tasks.json` in plain text.

### Stage 4b-3 — task tags instead of profiles (0.11.0)

Status: done (the date and the tag are set at the release). Spec: `docs/superpowers/specs/2026-11-02-task-tags-design.md`; plan:
`docs/superpowers/plans/2026-11-02-task-tags.md`. What is built:

- **The field `tags`** of a task, in any space: `normalize_tags` (trim, collapse spaces, 1–32 characters, no comma or control
  characters, no invisible or bidi-control characters, case-insensitive dedupe, at most 10; anything else is `400 bad-tags`).
  `tags` is the last key of the rows of `/api/tasks` (before `space` with `?all=1`) and of the «mine» rows of `/api/tasks-overview`,
  and follows `profile` in `/api/task`; `POST /api/task-new` takes an optional `tags`;
  the new `POST /api/task-tags {id, tags}` replaces them (`404 unknown-task`, `409 ambiguous-task`, `400 bad-tags`, `503`).
  `tags` is in the registry `SHARED`, and an empty list travels too.
- **Derived tags of LIGA:** `task_tags` gives the saved `tags` when the key exists (even `[]`), otherwise the profile as
  `United` / `LIGA360` / `SEO` (`tracks._LEGACY_LABELS` through `tracks.label_tag`, an adapter of the core that goes in 4d-3). The task files are not rewritten.
- **The screen:** chips, filter (any of the selected tags), search, the meta line of a card, the button and the dialog «Мітки»,
  the field in «New task»; `dc-tasks-ui.profiles` of 0.10.0 is migrated to tag keys. The profile stays a field of LIGA for the
  folders (`design_work_roots`), the repository and the inspector's design system.
- **`PROFILE_REPOS` left the code:** `profile_repos()` reads the table from the root of the legacy `tasks.json`
  (`[a-z0-9-]{1,32}` → a printable-ASCII repository without spaces, not starting with `-`; bad pairs dropped). Without it a new
  LIGA task has no default GitLab repository, and a body with only a `profile` is no longer a sign of the LIGA flow.
- **Conscious differences:** a task without tags is hidden under a tag filter; the chips are ordered by the number of tasks.
- **Known limits:** the «Team» tab has no tags (4c); no bulk rename; an old client syncing the registry drops the `tags` of a
  task it writes (a newer one puts them back on its next write); `task-tags` does not hold `WRITE_LOCK` across read-modify-write (`save_tasks` locks only the write, so a concurrent change of the same file by another route can be lost: last write wins);
  the search does not highlight inside tags; a chip shows the first-seen spelling; the button «Мітки» is one more Tab stop.
- **Tested** against the snapshot of 0.10.0 (`tests/fixtures/task-tags/before-4b3.json`); no network.
- **Left for 4c / 4d:** the dashboard (done in 4c-1), tracker statuses (done in 4c-2) and notifications (done in 4c-3), see below; the `integrations` flag and the profile
  adapter go in 4d.

### Stage 4c-1 — the team dashboard as a role (0.12.0)

Status: done (the date and the tag are set at the release). Spec: `docs/superpowers/specs/2026-11-02-dashboard-role-design.md`;
plan: `docs/superpowers/plans/2026-11-02-dashboard-role.md`. What is built:

- **The role `dashboard`** is called by the core (`ROLES_CALLED`; `tracker` and `notify` stay reserved at 4c-1 — `tracker` is called since 4c-2): `rows(ctx)`,
  `push(ctx, cards, mode)` with `'merge'` / `'insert'`, and the optional `open_comments(ctx)`; the codes `dashboard-unconfigured`
  (409) and `dashboard-error` (502); `capabilities.dashboard`. The contract is in `docs/modules/authoring.md`. Like `comments`, it
  has the hard-wired path of the legacy space (`LEGACY_ROLES`) but never falls back to it on an error (not in `LEGACY_ON_ERROR_ROLES`; an unreadable `space.json` is not `'legacy'` either, `STRICT_LEGACY_ROLES`).
- **The module `supabase-dashboard` 1.0.0** (built-in; `schema.sql`; a **non-public** key: no `anon` policy, `check` refuses a
  public key). The core builds the cards (`app/dashboard.py`: `build_card`, the PII filter, the registry fixtures), the module
  only stores them and returns the rows. The legacy space reaches its shared Supabase (table `overview_projects`) through the
  same module as an implicit provider, with the `ctx` built from the installation (`dashboard.legacy_ctx`); the base cards from
  the task registry and the Jira statuses stay its own steps, handed to the sync as callbacks.
- **The tab «Team» and the sync depend on the provider** of the role, not on `integrations`. The sync is a background child
  (`bin/overview_push.py sync [--space ID | --legacy]`), one per space at a time, with a deadline of 600 s checked by the next
  trigger; the rows are cached per space. The Connections screen and the wizard carry the role.
- **Conscious differences from 0.11.0:** batches of up to 50 cards grouped by their key set (the last card of a repeated id
  wins); the core waits 6 s for `rows` and the module's own timeout is 4 s (was 3 s); the sync child is not started for LIGA
  under `DC_TASKS_FILE`; the config of the CLI is read from `tasks.json` before the environment.
- **Known limits:** LIGA's key is not checked for being non-public; the registry and Jira steps are LIGA's until 4d / 4c-2 (Jira: done in 4c-2); one
  lock for the team rows of all spaces (a dead service holds another space for up to 6 s); no timer for a hung child; the sync
  of LIGA does not start when the folder of its log is missing; `open_comments` is cut at Supabase's `max-rows`. The full
  list is in the CHANGELOG, `[0.12.0]`.
- **Tested** against the snapshot of 0.11.0 (`tests/fixtures/dashboard/before-4c1.json`), a fake module and a fake vcs in the live
  tests (`tests/live/dashboard-role.test.mjs`); no network and no real Supabase.
- **Left for 4c-2 / 4c-3 / 4d:** tracker statuses (done in 4c-2) and the Teams silence (done in 4c-3), see below; the `integrations` flag and the
  literal `'legacy'` go in 4d.

### Stage 4c-2 — tracker statuses as a role (0.13.0)

Status: done (the date and the tag are set at the release). Spec: `docs/superpowers/specs/2026-11-03-tracker-role-design.md`;
plan: `docs/superpowers/plans/2026-11-03-tracker-role.md`. What is built:

- **The role `tracker`** is called by the core (`ROLES_CALLED`; only `notify` stayed reserved until 4c-3): `statuses(ctx, keys)` →
  `{key: {name, cat}}`; the codes `tracker-unconfigured` (409) and `tracker-error` (502); `capabilities.tracker`; the new
  field `ctx["timeout_s"]` (the socket budget of the module). Like `dashboard`, it has the hard-wired path of the legacy space
  (`LEGACY_ROLES`) but never falls back to it on an error (not in `LEGACY_ON_ERROR_ROLES`; an unreadable `space.json` is not
  `'legacy'` either, `STRICT_LEGACY_ROLES`). The contract is in `docs/modules/authoring.md`.
- **The core `app/tracker.py`** (no import of `serve`): `KEY_RE`, `keys_of`, `normalize`, `statuses` (batches of 100),
  `legacy_ctx` and `legacy_module`. It filters the keys before the call and normalizes the answer, so a module only talks to
  the tracker.
- **The module `jira-tracker` 1.0.0** (built-in; Jira Cloud, Basic `email:token`; the token is a secret): `statuses` is the
  same request the 0.12.0 sync made, `check` is `GET /myself` with the verdict `tracker-auth` for a wrong pair. No redirects,
  no token, e-mail or body in any text.
- **Two consumers of the statuses:** the dashboard sync (any space with a provider of the role; the Jira code left
  `bin/overview_push.py`) and the «Tasks» screen, which asks the tracker itself for the keys of «Mine» — so a space with a
  tracker and no dashboard has statuses too. The screen keeps a cache per space under its own lock (300 s, an error 30 s), a
  failure never wipes the last statuses, and a banner «Tracker unavailable» (with «data as of» when there are older
  statuses) appears over «Mine». The priority is the tracker, then the dashboard row, then «unknown».
- **LIGA through the module** as an implicit provider: the address is `jira_base` in the legacy `tasks.json` (it left the code),
  the credentials are as before. Isolation (`DC_TASKS_FILE`, `DC_NO_OVERVIEW`): the LIGA path never goes to Jira; the screen
  behaves as without a tracker (`DC_TRACKER_FAKE` is the test seam).
- **Conscious differences from 0.12.0:** the address comes from `tasks.json`, so LIGA without `jira_base` has no statuses; the
  screen asks Jira itself (a fresher status than the dashboard's); a failure in the sync is a log line, not silence; keys
  outside `KEY_RE` no longer reach Jira; HTTP 400 has a fixed hint and 408/429 are transient; the body of an error answer is not
  read; the e-mail and the token of LIGA are read independently, as before.
- **Known limits:** one key unknown to Jira fails its whole batch (HTTP 400); Jira Cloud only; the screen asks for the first 100
  keys; the worst case of `/api/tasks-overview` is about 12 s on a cache miss (the team rows 6 s, then the tracker 6 s); one
  global tracker lock for all spaces (a dead Jira holds another space for up to 6 s); the texts of the server errors are
  Ukrainian in the English interface too. The full list is in the CHANGELOG, `[0.13.0]`.
- **Tested** against the snapshot of 0.12.0 (`tests/fixtures/tracker/before-4c2.json`), the module and the core with a stubbed
  network, and a fake module in the live tests (`tests/live/tracker-role.test.mjs`); no network and no real Jira.
- **Left for 4c-3 / 4d:** the Teams silence as the role `notify` (done in 4c-3, see below); the `integrations` flag and the literal `'legacy'` go in 4d.

### Stage 4c-3 — Teams notifications as a role (0.14.0)

Status: done (the date and the tag are set at the release). Spec: `docs/superpowers/specs/2026-11-03-notify-role-design.md`;
plan: `docs/superpowers/plans/2026-11-03-notify-role.md`. What is built:

- **The role `notify`** is called by the core (`ROLES_CALLED`; `ROLES_RESERVED` is empty — **no role name is reserved any
  more**): `mute_state(ctx)` → a list of silenced channels and `mute_set(ctx, channel, muted, by)` → a bool; the codes
  `notify-unconfigured` (409) and `notify-error` (502); `capabilities.notify`. Like `tracker`, it has the hard-wired path of the
  legacy space (`LEGACY_ROLES`) but never falls back to it on an error (not in `LEGACY_ON_ERROR_ROLES`; an unreadable
  `space.json` is not `'legacy'` either, `STRICT_LEGACY_ROLES`). The contract is in `docs/modules/authoring.md`.
- **The core `app/notify.py`** (no import of `serve`): `normalize_mutes`, `mute_view` (a silenced channel covers its
  sub-channels), `check_set_args`, `legacy_ctx` and `legacy_module`. `serve.py` gets `notify_resolve()` and `notify_call()` in
  place of `teams_rpc`, and the route `/api/teams-mute` is gated by the role.
- **The module `supabase-teams` 1.0.0** (built-in) with its own **`schema.sql`**: the person runs it once in the Supabase of the
  comments (after the schema of `supabase-comments`), and a new pin sends a card to Teams through a webhook kept in Vault, with the
  silence per channel and a delivery log; the module calls the RPC `teams_mute_state` / `teams_mute_set` /
  `teams_notify_health`, granted to `service_role` only, with a **non-public** key. `check` tells apart `public-key`,
  `notify-no-schema` and `notify-no-webhook`.
- **LIGA through the module** as an implicit provider: the same RPC with the public key of the page, from the config of the
  installation; its own triggers and the card stay in its database. Isolation: with `DC_TASKS_FILE` or
  `DC_NO_OVERVIEW` the LIGA path never goes to the network; `DC_TEAMS_FAKE` is the seam of that path only.
- **The client** follows the role: `hasNotify(space)` gates the Teams item and the polling (`noOutward` is gone); the role is on
  the Connections screen and in the wizard (icon «eye»: there is no bell in the set).
- **Conscious differences from 0.13.0:** the refusal without a provider is `notify-off` (not `integrations-off`); the error text of a
  LIGA failure comes from the module; a module answer of the wrong shape is a `notify-error`; a channel over 200 characters is 400;
  a broken own module is reported with its reason; `public-key` is also the verdict of `supabase-dashboard` (it was `module-error`);
  the schema of the module de-duplicates the send by its delivery log (the LIGA trigger does not). The full list is in the CHANGELOG,
  `[0.14.0]`.
- **Known limits:** the state is cut at 1000 rows; `schema.sql` was checked statically only (no Postgres in CI), the first run on a
  real Supabase is a manual step; fire-and-forget delivery with the health visible only in `check`; the card carries the channel id
  in Ukrainian; the shared `no-schema` text is still worded «no table comments» for `supabase-dashboard`.
- **Tested** against the snapshot of 0.13.0 (`tests/fixtures/notify/before-4c3.json`), the module and the core with a stubbed
  network, static checks of the schema, and a fake module in the live tests (`tests/live/notify-role.test.mjs`); no network, no
  Postgres and no real Teams.
- **Left for 4d:** the `integrations` flag and the literal `'legacy'` go; every in-house integration is a role by now.

### Stage 4d-1 — tracks of a space instead of the profile (0.15.0)

Status: done (the date and the tag are set at the release). Spec: `docs/superpowers/specs/2026-11-04-space-tracks-design.md`;
plan: `docs/superpowers/plans/2026-11-04-space-tracks.md`. This is the first of the four sub-releases of 4d (owner decision
04.11.2026). What is built:

- **The core `app/tracks.py`** (no network, no import of `serve`): `ID_RE`, `MAX_TRACKS` (20), `ROOT_MAX` (1024), `normalize`
  (`tracks` of a `space.json` → `[{id, label, root, repo, ds}]`, never raises), `default_id`, `of_task` (`track`, otherwise
  `profile`), `find`, `label_tag` and the adapter `legacy_tracks(cfg)` with `legacy_root` and `legacy_repos`. The tag rules, the repo
  rule and the id pattern moved here from `serve`.
- **`serve`:** `space_tracks(sp)`, `_TrackView` (the tracks of one space, once per request and lazily), `track_root`, `track_repo`,
  `task_ds`; `task_tags(task, sp)`. A task has `track`; it is in `/api/tasks`, `/api/task` and `/api/spaces` (`tracks`,
  `default_track`, never `root` or `repo`); `POST /api/task-new` takes `track` (and `profile` as a synonym), with the codes
  `bad-track` and `unknown-track`.
- **The LIGA space as an adapter:** its tracks come from the root of the old `tasks.json` (`design_work_roots`,
  `design_work_root`, `profile_repos`; labels `United` / `LIGA360` / `SEO`; the default `united`; `ds` = the id), unless its
  `space.json` already has `tracks`. A LIGA record writes `track` **and** `profile` with the same value, so teammates on 0.14.0 keep
  reading the shared registry. `bin/registry.py` (`SHARED` has `track`), `bin/roots.py` and `bin/state.py` go through `tracks`.
- **An ordinary space with tracks:** the task folder is the `root` of the track, and its `repo` becomes the `vcs` of the task when a
  `vcs` provider exists and the body has no `vcs`.
- **Removed from the core:** `_LEGACY_PROFILE_TAGS`, `_PROFILE_KEY`, `_REPO_OK`, `work_root`, the tag helpers (all in `tracks.py` now);
  `serve.py` has no `united` / `liga360` / `seo` left (a test checks it). Kept until 4d-4: the wrapper `profile_repos`.
- **Conscious differences from 0.14.0:** new fields and the codes `bad-track` / `unknown-track`; the folder and repository of a track in an
  ordinary space; LIGA no longer crashes on a non-object `design_work_roots`, a non-string root, a numeric profile (page and
  `bin/roots.py`); `?ds=` follows the `ds` of the found track; `?all=1` labels each row by its own space. The full list is in the
  CHANGELOG, `[0.15.0]`.
- **Known limits:** tracks are edited in `space.json` only (no UI; only the API puts a task into a track); an invalid root falls
  back to the space path with no warning; roots are validated only on task creation (labels, the inspector's design system, `/api/tasks`, `/api/task` and `/api/spaces` read tracks without the check); a LIGA space with its own non-empty `tracks` loses the adapter semantics (an unknown id no longer falls back to the shared root, «any string» is no longer accepted, `design_work_roots` and `profile_repos` are ignored) while an empty list keeps the adapter; `profile`
  lives on until 4d-4; the names of the LIGA tracks live in the adapter until 4d-3; `_liga_flow` looks at `profile` only.
- **Tested** against the snapshot of 0.14.0 (`tests/fixtures/tracks/before-4d1.json`, about 160 tests in `tests/test_tracks.py`),
  with fake `vcs` modules and local fixture repos, and in the live test `tests/live/tracks.test.mjs`; no network.
- **Left for 4d-2…4d-4:** see below.

### What stays for later

- **Left for 4d-2…4d-4** (stage 4d, four releases):
  - **4d-2** (0.16.0): the layer-off seam and the isolation of shared state without the literal `'legacy'`;
  - **4d-3** (0.17.0): explicit LIGA modules with an automatic migration of its config (with a backup) — it also writes the LIGA
    tracks into its `space.json`, so `tracks._LEGACY_LABELS`, the default `united` and the adapter go;
  - **4d-4** (0.18.0): the `integrations` flag and the old aliases go — `profile` in the records and the API, the thin wrapper
    `profile_repos`, and the `profile`-only look of `_liga_flow`.
  Not planned in 4d-1: a UI to edit tracks, a track choice in the «New task» dialog.

- No role is reserved any more (every role of the map is called by the core since 4c-3).
- Left out of 3c (listed in its spec): a sandbox for module code (a trusted module runs with the person's
  permissions); cleaning of snapshots that a re-trust replaced or whose folder vanished; viewing or comparing code in
  the dialog; signatures and a catalog of modules; installing a module from a URL; machine-wide modules; a banner
  «N modules wait for trust» on «Tasks»; the local `/published/…` copy for an own publish-to-folder module. The
  Windows and Linux system windows are covered by unit tests of the command only.
- Left out of 3a: picking a folder with a system dialog; a banner «N connections with an
  error» on «Tasks»; icons and descriptions from manifests (today only the built-in modules
  have them).
- Left out of 3b: resuming an unfinished wizard after a restart (the space already exists; the
  rest is on «Connections» and «Tasks»); starting an agent from the wizard (step 4 only gives the
  phrase to say to it).
- **Not handled in 0.2** (a later security stage or on demand): a `Host`-header check on the
  canvas server (DNS rebinding); keychain storage for secrets (they sit in a `0600` file);
  `HEAD` and `/t/<id>/published/…` on the local copy; design tokens from an npm package;
  following `@import` in CSS tokens (`var()` resolves only within one file).
- **Known limits of the folder module** (owner-accepted, listed in the spec, «Межі»): the
  sandboxed local copy needs `Access-Control-Allow-Origin: *`, so a page in the same browser
  that guesses the URL can read it including the gate password (the gate is client-side,
  like on a static host); with a password, inner pages re-ask it locally; `file://` and
  root-absolute asset URLs do not work under the `/published/…` subpath.
