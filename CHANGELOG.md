# Changelog

All notable changes to Deai Canvas, newest first. Format follows
[Keep a Changelog](https://keepachangelog.com/); dates are DD.MM.YYYY.

## [0.3.0] — 16.10.2026

Stage 2b-1 «Your own Vercel»: a built-in module publishes the task's preview to the
person's own Vercel account through the REST API (no Node, no CLI), the core learns
publish modules that return an address instead of a folder, and the UI shows the result.
Design and the list of deviations from the original spec:
`docs/superpowers/specs/2026-10-16-vercel-publish-design.md`.

### Added

- **`vercel-publish`** (role `publish`, `publish_target: url`). Settings: `token` (secret,
  required), `team` (a slug or `team_…`; empty means the personal account), `password`
  (secret, optional — adds the client-side preview gate). Standard library only, no
  subprocesses. One publish: the build is read and checked locally (no symlinks, up to
  5000 files, up to 50 MB per file) → files are uploaded by SHA-1, once per content →
  a production deployment without a build step → wait for `READY` → wait (up to 30 s) for
  the project's permanent `*.vercel.app` address → check that the address opens without
  signing in → clean up old deployments. Each task gets an opaque project `pv-<8 digits>`
  (no task or client name in the address). `check` reads the account (and the team) and
  creates nothing. Enable it over the API (see the README); `static-publish` has to be
  turned off first (`role-taken` otherwise).
- **Core: publish modules «by address».** The manifest gets an optional `publish_target`
  (`folder`, the default and the 0.2.0 behaviour, or `url`). A `url` module has no folder:
  it gets the built preview and the state it returned last time, and returns `{url, state,
  verified, warnings?}`. The core records `publish_url`, `published_at`, `publish_verified`
  and `publish_remote` (`{module, state, published_at, url, gated[, gate_hash]}`) in
  `iterations.json`, builds the preview without the comment layer and, when the module has
  a `password` secret, with the gate. `/api/task` adds `publish_remote`, `publish_gate`
  (is the published preview protected by a password), `publish_gate_stale` (the password
  changed since the publish) and `publish_share_url` (the address plus `#k=<password>` for
  a protected preview). New error codes `vercel-auth` and `vercel-busy` (409).
- **UI.** A persistent «Published on Vercel» notice with «Open» and «Copy link»; the module's
  warnings go under it as plain text. «Open» and «Copy link» (also in the publish dropdown)
  use the share link with the password, so the owner does not hit their own gate. The
  dropdown warns «the preview is public» when it is published without a password and
  «the password changed — republish» when it differs from the published one. Human
  texts (uk, en) for `vercel-auth`, `vercel-busy` and `module-error`, with the server's
  reason as a second paragraph. If you switch to another task while a publish is running,
  the result is a toast with the task name instead of a notice on the wrong task. «Copy
  link» for an address left over from another provider (the space was switched from Vercel
  to `static-publish`) copies the bare address; the legacy `#k=<password>&p=<page>` fragment
  is added only for the legacy provider. The Publish button comes back on every path, also
  when redrawing the bar throws.

### Security

- The token goes only into the `Authorization` header of requests to `api.vercel.com`, from
  one place in the module. Not into process arguments or the environment, not into the
  preview check (it carries no credentials and follows no redirects), not into error
  texts; API requests do not follow redirects either.
- The core does not take a module's word for its result: `url` must be `https://` with an
  ASCII DNS host (at least two labels, the last one starting with a letter, so IP addresses
  in any form — `127.0.0.1`, `2130706433`, `0x7f.1` — and `localhost` are refused; the UI
  applies the same rule before it opens or copies an address), no credentials and no fragment; `state` a flat object of at most 4096
  characters; `warnings` at most 5 lines of 300 characters. A result that contains a secret
  of the module (8 characters or more; the preview `password` is the exception, because it
  is baked into the pages by design) is refused and not recorded, and warnings are scrubbed
  of every secret.
- The stored state is not trusted (`iterations.json` can be copied, shared or forged): it is
  used only as `pv-<8 digits>` plus a project id plus the id of this task. The project is
  looked up by id before any upload and used only when the id **and the exact name** match
  the record. Any other name is a foreign project (a forged project id, or a rename in the
  Vercel dashboard): nothing is deployed into it or deleted from it, a new `pv-` project is
  created with a warning. Renaming is deliberately not supported — the proof that «the
  recorded deployment belongs to the project» lived in the same forgeable state. A project
  deleted in the panel is recreated only under the recorded name and only if that name is
  free.
- Module failures reach the dialog as clean texts: everything that has no code of its own is
  raised as `module-error` without a class prefix (`RuntimeError: …`), and a text that is
  cut for the removal note ends with a full stop before it. A lone surrogate in a text
  from Vercel (`\ud800` in JSON) is replaced before the result leaves the module, so one
  bad character cannot make the core refuse an already successful publish.
- A project is deleted (after a failed publish) only if the same call created it, and only
  after three checks: the id starts with `prj_`, the project has no deployments except this
  call's, and its name is the expected one. A project taken from the state is never deleted.
- Cleanup removes only deployments positively identified as the project's own and keeps
  the newest three (the current one and two more) among the 20 latest production deployments.

### Known limits

- **Not run against the real Vercel in CI.** The module is tested against a faithful
  in-process fake of the API with a network guard, and the live tests fake the Vercel space
  in the browser; the module's `check()` is never run live. A first run with a real token
  should confirm: how long the permanent address takes to appear after `READY`, the item
  shape of `GET /v6/deployments` (used for cleanup), the team-by-slug access check
  (`GET /v6/deployments?limit=1` in that team) and the error body of an invalid token.
- Deployment Protection is a Vercel account/project setting. If it is on, the preview does
  not open without signing in to Vercel; the module detects it (401/403 or a redirect to
  the Vercel login) and warns with the place to switch it off, but never changes it.
- The preview password is not a secret from viewers (it is baked into the pages, the gate
  is client-side), so `/api/task` returns the share link with it. The **token** never
  leaves the machine except to `api.vercel.com`.
- Module management has no UI yet (stage 3): enable and configure it over the API.
- A `publish_remote.state` written by development builds before 0.3.0 (without the task
  binding) is ignored: the next publish creates a new project.
- A project renamed in the Vercel dashboard is no longer the task's project: the next
  publish creates a new `pv-` project (new address) and warns; the renamed one stays as it
  was.
- If the network drops right after the deployment was requested but before Vercel's answer
  arrives, an empty `pv-` project may be left in the account (the module never saw the
  deployment id). Delete it in the dashboard.
- Uploads are sequential and the whole build is sent on every publish (a file once per
  content), within 300 seconds in total.
- The core gives `check` 5 seconds: on a slow link enabling the module can answer
  `check-timeout`, the module still works. Explicit `POST /api/module-check` and
  `POST /api/module-settings` run `check()` against `api.vercel.com` even for a disabled
  module; nothing automatic does.
- A DNS name that resolves to a local address (`127.0.0.1.nip.io`) is not caught by the
  syntax check of the result address.
- The comment layer is not on the Vercel preview (shared comments are stage 2b-2, 0.4.0).

### Tests

`npm test` at 0.3.0 is green: 1258 node tests (plus `inspector-core`), 1938 Python tests in
`tests/` (1 skipped), 156 in `bin/`, 170 in `app/` (0.2.0: 1195 and 1684). The three Python
suites also pass on Python 3.9.6, the oldest supported. New before the tag:
`tests/test_vercel_integration.py` joins the real module with the real dispatcher
(`POST /api/publish`, `/api/task`, `iterations.json`) against the in-process fake API under
two network tripwires — first publish, republish into the same project, the password table
(none / set after publish / gated publish / changed / removed), a failed first publish, a
forged state, a lone surrogate, and «the token is nowhere but `secrets.json`» (the guard is
itself proven able to fail). Each fix of the pre-tag review was proven by a mutation
(accepting a different project name, no clean error text, no full stop before the note, no
surrogate cleaning, the old host rule, the old copy fragment, the Publish button restored
only on fall-through): each turns its tests red. Live: the new
`tests/live/vercel.test.mjs` (7 tests: publish with a password, the dropdown warnings, error
dialogs, the switch-task race, the legacy space unchanged, no request leaves the machine,
the real `~/.deai` untouched) passes together with `modules.test.mjs` and `spaces.test.mjs`
(20 tests); a mutation run confirmed each scenario guards its rule (`noopener` on «Open»
turns the first one red).

## [0.2.0] — 16.10.2026

Stage 2a «Modules»: a module framework, publishing to a folder, design-system tokens from
a CSS file. Design and the list of deviations from the original spec:
`docs/superpowers/specs/2026-10-14-modules-2a-design.md`.

### Added

- **Module framework** (`app/deai_modules.py`). A module is a folder
  `app/modules/<id>/{module.json, server.py}`; a role is an interface the core calls.
  Called roles: `publish`, `tokens`; reserved (not called yet): `comments`, `vcs`,
  `tracker`, `dashboard`, `notify`. In 0.2 only built-in modules exist; a space's own
  modules arrive with the trust dialog in stage 3.
  - Settings and on/off live in the space's `space.json` (`modules`); paths are stored
    symbolically (`{home}`, `{space}`, `{space_id}`). Secrets live in
    `<DEAI_HOME>/secrets.json` (file `0600`, folder `0700`; not set on Windows) and never
    reach `space.json`, API responses, logs or error texts.
  - `server.py` is loaded with `exec` (no `importlib`, no `__pycache__`) and gets a `ctx`
    (`space`, `settings`, its own `secrets`, `folder_ok`, `ModuleError`) instead of
    importing the core. Any module failure becomes a `module-error` with secrets scrubbed.
  - One provider per role per space (`role-taken` otherwise). A space without
    integrations gets `static-publish` implicitly, with nothing written to disk.
  - `capabilities` (`{publish, tokens}`) in `/api/task`, `/api/tasks`,
    `/api/tasks-overview` and `/api/spaces`.
- **`static-publish`** (role `publish`). Builds the static preview of the marked
  iterations and publishes it to a folder, by default `~/deai-published/<space-id>/<task>/`
  — outside the space. The folder is re-checked on every publish and every serve (not
  your home or its ancestors, not `DEAI_HOME`, not the tool, not a space or task folder or
  anything above or inside one, not a system or hidden folder). Replacement is two renames
  (old folder aside, new one into place), so a request landing between them gets a brief
  404; it is guarded by a `.deai-published` marker, a folder without the marker is never
  touched, and an interrupted replacement is recovered from `.old-*`. Concurrent publishes
  of one destination answer `409 publish-busy`. Optional `password` secret adds the
  client-side preview gate. Module builds carry no comment layer. Result is recorded as `publish_local`
  in `iterations.json`.
- **Local serving** `GET /published/<space>/<task>/…`: every response (200, 304, 301, 404)
  carries `Content-Security-Policy: sandbox allow-scripts allow-forms allow-popups`,
  `nosniff` and `Access-Control-Allow-Origin: *`; 404 is constant. Only folders with the
  marker, only for spaces whose publisher is `static-publish`. On macOS/Linux files are
  opened by walking directory descriptors (`O_NOFOLLOW`, same `dev/ino`, hard links
  refused, kernel path re-checked); where the OS cannot do that (Windows, macOS with
  Python < 3.9, Linux without `/proc/self/fd`) a weaker path-based fallback runs and the
  server prints the active mode at startup.
- **`css-tokens`** (role `tokens`). Reads design tokens from one CSS file (regular file,
  up to 2 MiB). A token is `--name: value` in a rule whose subject is `html`, `:root` or a
  `[data-*theme*]` attribute (Bootstrap `[data-bs-theme=dark]` included), or directly in
  Tailwind v4 `@theme { … }`; values are collected per name (themes, media), `var()` is
  resolved within the file (up to 5 hops, no cycles, with expansion caps), `@import` is not
  followed. Nested `@media`/`@layer`/`@supports`/`@container` are traversed.
- **Module API.** `GET /api/modules?space=`, `POST /api/module-enable`,
  `/api/module-disable`, `/api/module-settings`, `/api/module-check`;
  `GET /api/ds-tokens?space=` for the inspector. All POSTs sit behind the central Origin
  check; secrets are exposed only as `set: true|false`.
- **Inspector** uses the space's tokens (`/api/ds-tokens`, fetched in the background once per
  frame load, 7 s client timeout) and reports their source in the tuner package; the
  `space:<id>` profile is told apart from the static product tracks.
- **UI.** The publish zone follows `capabilities.publish` instead of the old
  `integrations` flag; a local publish shows a persistent «Published locally» notice with
  «Open»; «Copy link» gives the absolute canvas URL without the password fragment.

### Changed

- Publishing in a space without integrations no longer answers `409`: it goes to
  `static-publish`. The legacy (in-house) path keeps its responses and builds — the
  existing publish tests pass unchanged, the bar and palette markup of such a space is
  guarded by a golden-snapshot test, and in published builds only `shell/i18n.js` changes
  (new keys, plus the reworded `integrationsOff` text in uk and en); pages, wrapper and
  comment layer are unchanged.
- The preview build is one function (`build_preview`) shared by the legacy path and modules.

### Known issues

- Module management has no UI yet (stage 3): enable and configure modules through the API.
- Accepted limits (see the spec, «Межі»): `ACAO: *` is required by the sandbox, so any web
  page in the same browser that guesses a `/published/…` URL can read it, including the
  gate password (the gate is client-side, the password is not a secret); with a password,
  inner pages re-ask it in the local view; `file://` is not supported and root-absolute
  asset URLs break under the `/published/…` subpath; the canvas server does not check the
  `Host` header (DNS rebinding) — a later security stage; `/t/<id>/published/…` and `HEAD`
  on `/published` are not handled; secrets are not encrypted.
- Pre-existing, not from 2a: live tests `tests/live/canvas.test.mjs` K2 (flaky palette
  click) and `tests/live/inspector-ds.test.mjs` tests 2 and 4 (no static `united` design-system
  snapshot in this repo).
- Tech debt: the static fallback in `Handler.do_GET` raises a traceback on `%00` paths; the
  build-folder lock exists only on the module path; the 409 text of `/api/preview-password`
  («публікація зʼявиться з модулями») is stale (the UI does not show it).

### Tests

`npm test` at 0.2.0 is green: 1195 node tests (plus `inspector-core`), 1684 Python tests in
`tests/` (1 skipped), 156 in `bin/`, 170 in `app/`. The three Python suites also pass on
Python 3.9.6 (the oldest supported). The live (Playwright) suite is run separately
(`npm run test:live`); its known failures are listed above.

## [0.1.0] — 14.10.2026

Stage 1 «Spaces»: the first extraction of Deai Canvas from an in-house tool (source
1.55.0 @ `796b3df`; the in-house doctor test is not part of the product).

### Added

- **Spaces.** Several projects or companies on one machine, each a folder with its own
  `space.json` and task list. Registry at `~/.deai/spaces.json`; an existing `tasks.json`
  is migrated into the first space automatically; the space of a request is pinned per
  request; an integrations kill-switch turns off everything that talks outward; space
  switcher, new-space and new-task dialogs, welcome screen, `?all=1`.
- The canvas itself, as carried over: iterations, a tree of pages, folders and states,
  the Overview of full-page snapshots at desktop / tablet / mobile widths, user-flow
  maps, the inspector and tuner, comments addressed to the agent, agent status, a tasks
  home, installable PWA, macOS launcher. UI in English and Ukrainian.
- Publishing worked only through the original hard-wired setup (a legacy space with
  integrations); everything company-specific was meant to become per-space modules.
