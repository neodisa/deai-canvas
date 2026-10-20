# Spaces, modules and onboarding — design (draft)

Status: agreed direction, 2026-10-09. Clickable prototype reviewed by the owner.
Built so far: stage 1 (spaces, 0.1.0), stage 2a (module framework, publishing to a
folder, tokens from CSS, 0.2.0), stage 2b-1 (publishing to your own Vercel, 0.3.0) and
stage 2b-2 (the universal `comments` role and your own Supabase, 0.4.0) and stage 3a (the
Connections screen, 0.5.0) — see *Status* at the end. Next: 3b (the first-run wizard, 0.6.0) and
3c (a space's own modules with a trust dialog, 0.7.0).

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
  | Issue tracker (`tracker`) | Jira, Linear |
  | Team dashboard (`dashboard`) | — |
  | Notifications (`notify`) | — |

- Built-in modules ship in `app/modules/`; a space's own modules live in
  `<space>/modules/` and are loaded the same way — but only after the person trusts them
  (stage 3c: a trust dialog in Connections; until then only built-in modules load). A
  module may implement an existing role
  (e.g. publish to Netlify) or add its own integration (e.g. notifications to a chat).
- **Nothing is required.** Without modules the canvas works fully: local comments for
  the agent, publishing into a folder, the inspector without a design system.

## Onboarding

- **First run** (no spaces): a wizard — space name, colour and folder → pick modules by
  role → settings with «Check» → first task (new / adopt an existing folder of HTML /
  let the agent create it). *Stage 3b, 0.6.0 — not built yet; it reuses the cards and the
  side panel of the Connections screen.*
- **Connections** screen per space: module cards with status (connected / error with the
  reason / off), configure in a side panel (secrets marked as stored outside the space),
  check, disable. *Built in stage 3a (0.5.0)*: entered from the space menu, ⌘K, or the head
  of «Tasks» in a space without integrations; cards grouped by role with a «Now: …» line;
  secrets shown only as set / not set / unknown; replacing the provider of a role in one
  step; turning a module off with its consequences. See *Status → Stage 3a*.
- **A space's own modules** from `<space>/modules/`, loaded only after the person trusts
  them in a dialog (shown on the Connections screen, with a «custom» mark on the card).
  *Stage 3c, 0.7.0 — not built yet.*
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
   - the in-house integrations (git sync, team dashboard, tracker, team chat notifications)
     follow later as that company's modules.
3. Onboarding, split into three parts:
   - ✅ **3a** (0.5.0) — the Connections screen;
   - **3b** (0.6.0) — the first-run wizard (space → modules → settings → first task);
   - **3c** (0.7.0) — a space's own modules from `<space>/modules/` with the trust dialog.
4. Company-specific integrations move out of the core into that company's space modules.
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
  core: `publish`, `tokens`; the others are reserved.
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

### What stays for later

- The roles `vcs`, `tracker`, `dashboard`, `notify` are reserved names that the core does not
  call yet.
- **Stage 3b**: the first-run wizard (0.6.0).
- **Stage 3c**: a space's own modules from `<space>/modules/` with the trust dialog (hash of
  the whole folder, no symlinks, trust keyed on the real path), and a «custom» mark on the
  card (0.7.0).
- Left out of 3a: picking a folder with a system dialog; a banner «N connections with an
  error» on «Tasks»; icons and descriptions from manifests (today only the built-in modules
  have them).
- **Not handled in 0.2** (a later security stage or on demand): a `Host`-header check on the
  canvas server (DNS rebinding); keychain storage for secrets (they sit in a `0600` file);
  `HEAD` and `/t/<id>/published/…` on the local copy; design tokens from an npm package;
  following `@import` in CSS tokens (`var()` resolves only within one file).
- **Known limits of the folder module** (owner-accepted, listed in the spec, «Межі»): the
  sandboxed local copy needs `Access-Control-Allow-Origin: *`, so a page in the same browser
  that guesses the URL can read it including the gate password (the gate is client-side,
  like on a static host); with a password, inner pages re-ask it locally; `file://` and
  root-absolute asset URLs do not work under the `/published/…` subpath.
