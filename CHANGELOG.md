# Changelog

All notable changes to Deai Canvas, newest first. Format follows
[Keep a Changelog](https://keepachangelog.com/); dates are DD.MM.YYYY.

## [0.6.0] — 22.10.2026

Stage 3b: the new-space wizard. A new space is no longer a dialog with three fields and an empty
screen after it: four steps lead from the space through its modules and their settings to the first
task, which can now come from a mockup folder that already exists on disk. Design:
`docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`; plan:
`docs/superpowers/plans/2026-10-21-first-run-wizard.md`. The legacy (in-house) space is unchanged:
`tests/legacy-golden.test.mjs` is green without a re-shoot.

### Added

- **The new-space wizard** (`app/wizard.js`, `app/wizard-model.js`, `app/wizard-view.js`): the third
  page of the home overlay, next to «Tasks» and «Connections» (the same entry, exit and clean view).
  Four steps: Space → Modules → Settings → First task. The first run (no spaces) and «New space…»
  (the space menu, ⌘K) open the same page. The space is created on step 1 with the real
  `POST /api/space-new`, and every later request carries an explicit `space`, so closing the wizard
  at any step leaves a working space whose connections can be finished on «Connections»; if an agent
  switches the active space meanwhile, the wizard keeps writing to its own. A space that disappears
  under the wizard closes it with a toast.
  - **Space** (step 1): the fields of the old dialog (name, colour, folder, with the «this folder is
    already a space» and «already added» hints). «Back» to step 1 after the creation shows the same
    step in edit mode: name and colour can change (one `space-update`, only when something changed),
    the folder is read-only.
  - **Modules** (step 2): the sections of the Connections screen, one choice per role — a module
    or «No module» with what that means for the role. The option that would take the role from the
    current provider says so («instead of …»; the choice is the consent, so the next step does not
    ask again). A current provider that fails stays selectable and shows its reason in plain words.
    The initial choice is who provides each role now, the implicit `static-publish` included.
    Nothing is written on this step.
  - **Settings** (step 3): a card per chosen module with the same fields as the Connections side
    panel, secrets included (never rendered, shown only as set / not set / unknown, and cleared after
    every server response), and a line for each provider that «No module» turns off. «Save and
    continue» checks the required fields first (no request until they are filled), then re-reads the
    module list and writes one by one: `module-enable` with `replace` and `module-settings` in the
    order of the sections, then the switch-offs. A switch-off that depends on a replacement waits until
    the replacement is saved, so a role is never left empty by a failed write. A role that an agent
    changed while the person was choosing is not written: the card says «The role changed while you
    were choosing — go back to the Modules step» and names who holds it now; the other roles are
    written as usual. If a picked module has disappeared by the time the step opens, the wizard returns
    to Modules with a notice. Each answer is drawn in its card (connected and checked, saved but the
    check failed with the reason, or not saved with the reason); when anything failed the wizard stays
    on the step, and pressing the button again repeats only what is not written. If the module list
    cannot be read at «Save», the toast says so, nothing is sent and what was typed (secrets
    included) stays.
  - **First task** (step 4): a blank page, **an existing mockup folder** (copied into the first
    iteration; the task title is taken from the folder name until the person types one), or a phrase
    to give the agent (with «Copy»); or «Skip» (the label is «Go to tasks» when the space already has
    some). A refusal of the server (`from-*`, `task-dir-exists`) is shown in plain words in the form,
    and the field it is about gets the focus.
  - **Leaving.** «Cancel» (only before the space exists; the logo does the same there) returns to
    where the wizard was opened — the welcome screen, «Tasks», «Connections» or the canvas of a task.
    «Close the wizard» (after the creation) and the logo go to «Tasks» of the new space with a toast.
    Unsaved fields of step 3 are asked about first («Discard unsaved settings?»); Esc closes nothing,
    as this is a page and a stray Esc must not throw away a typed token. The bar shows a flat crumb
    «New space» with no space chip, and ⌘K has no space actions there.
- **`from` in `POST /api/task-new`** — copies a folder that has an `index.html` into the first
  iteration of the new task (`app/serve.py`: `adopt_scan`, `adopt_copy`, `AdoptRefused`; the limits
  are the constants `ADOPT_MAX_FILES` and `ADOPT_MAX_BYTES`). Only in a space without integrations
  (`400 from-needs-plain-space`, also for `gitlab`). The path must be absolute (`~` is expanded) and
  is resolved to the real folder. Every check and the walk of the folder come before any write:
  `400 bad-request` (not a non-empty string), `400 bad-task-id` (the id is checked before the disk),
  `400 from-not-found` (not a folder, a relative path, a NUL in the path, an unreadable file or
  subfolder), `400 from-no-index` (no plain `index.html` at the root), `400 from-contains-space` (the
  task folder would lie inside the source, so the copy would go into itself; compared with
  `samefile` over the ancestors, so `~/WORK` and `~/work` on a case-insensitive disk are one folder),
  `409 task-dir-exists` (the task folder is claimed atomically: of two requests with the same id the
  second is refused, and a folder that is not ours is never touched), `413 from-too-big` (more than
  2000 files or 200 MB, the limits themselves are allowed; the answer carries `files` and `bytes` at
  the moment of the stop, so picking a home folder by mistake does not copy half a disk). Symbolic links are never copied (a file or a folder, and every
  file is checked again at copy time against a swap after the walk); `.git`, `node_modules` and
  `.DS_Store` are skipped at any level, the tool's own junk and the publish state
  `.canvas-state.json` at the root. Copied files get a fresh modification time, so the task does not
  show the date of the old folder. Any failure up to and including the write of `tasks.json` removes
  the task folder, writes nothing to `tasks.json` and answers `500 task-create-failed`; a retry with
  the same id goes through. The answer is the usual one plus `copied: {files, bytes, skipped_links}` —
  what was actually copied, not what the walk saw. Without `from` the endpoint answers as before.
- The welcome screen gets a second button, «Open an existing space folder»: it opens step 1 with an
  empty name and the cursor in the folder field, and a folder that already is a space fills in its own
  name and colour.

### Changed

- «New space…» in the space menu and in ⌘K, and «Create a space» on the welcome screen, lead to the
  wizard instead of the dialog. The space dialog stays only for «Name and colour…».

### Fixed

- The crumb of a home page («Tasks», «Connections», «New space») no longer collapses its icon to zero
  width in Ukrainian: the 110 px `max-width` meant for the crumbs of the layer tree overrode the
  260 px limit of the bar's crumbs. Home-page crumbs now carry their own modifier (`crumb--page`, no
  cap); the flat crumb of the external preview shell is untouched.

### Removed

- The «New space» dialog (mode `new` of the space dialog) and its dictionary keys.

### Known issues

- At window widths below about 680 px the logo button and the page crumbs in the top bar are squeezed.
  This is older than the wizard and is tracked separately.

### Not in this release

- Picking a folder with the system dialog (both folder fields are text); resuming an unfinished
  wizard after a restart (the space already exists; the rest is on «Connections» and «Tasks»); a space's
  own modules and the trust dialog (3c, 0.7.0); starting an agent from the wizard (step 4 only gives
  the phrase to say to it).

### Tests

`npm test` at 0.6.0 is green: 1629 node tests (plus `inspector-core`), 2381 Python tests in
`tests/` (1 skipped), 168 in `bin/`, 170 in `app/` (0.5.0: 1458, 2349 with 1 skipped, 168, 170), on
Python 3.13. The new server tests, `tests/test_task_from.py`, also pass on Python 3.9.6, the oldest
supported version; the full Python suites were not repeated there for this release.

New: unit tests `tests/wizard-model.test.mjs` (the choice per role, the plan of writes and its
order, freshness, the dependent switch-off, names from the folder; roles are data, so a role named
`__proto__` is an ordinary key), `tests/wizard-view.test.mjs` (every step, the hooks, `aria-current`,
`fieldset` and `legend`, everything from data is escaped, secret fields are empty),
`tests/wizard-css.test.mjs` (every class of the markup has a rule, narrow widths, the clean view hides
the page, only tokens, contrast of the selected card) and `tests/wizard-wiring.test.mjs` (the entry
points, the explicit `space` in every request of steps 2–4, the light path after a write); the bar,
palette and dialog tests were extended (`tests/shell-bar.test.mjs`, `tests/bar-model.test.mjs`,
`tests/shell-palette.test.mjs`, `tests/ext-bar.test.mjs`, `tests/space-dialogs.test.mjs`,
`tests/spaces-wiring.test.mjs`). On the
server, `tests/test_task_from.py` (31 tests): every refusal of `from`, the limits (inclusive, lowered
in the test), symbolic links not copied and counted (also one swapped in after the walk), `.git`,
`node_modules` and a fifo skipped, a folder that contains the space or its parent, a differently cased
path, a failure in the middle of the copy or after it leaves no folder and no record (a retry works),
a task folder that appears after the check is not touched, a fresh modification time, a space with
integrations refuses.

The live test `tests/live/wizard.test.mjs` (a real server in an isolated machine, a real Chromium,
15 scenarios, one file at a time) covers the first run from the welcome screen to a task, replacing
the provider («instead of …») with the fixture module `memo-publish`, a secret that shows up nowhere,
a task from a folder with a symbolic link (the toast, the copy, the mockup in the frame), a refusal on
step 1 and «Cancel» back to the canvas, «Back» to step 1 and the rename, unsaved fields (Esc, the logo,
«Back», «Close the wizard»), a role that an agent took while the person was choosing, opening an
existing space folder, a failed read of the list at «Save», a saved card that is no longer «changed»,
the focus on the first failed card, a server refusal that still clears the password field, a language
switch in the middle of step 1, «No module» for publishing, and ⌘K while the creation request is in
flight. The live tests of the old dialog (`tests/live/spaces.test.mjs`, `tests/live/spaces-flows.test.mjs`)
now go through step 1 of the wizard. The leak watchers of `tests/live/wizard.test.mjs` and
`tests/live/connections.test.mjs` compare request addresses in three shapes (raw, percent-encoded,
decoded), so a secret that reaches a URL percent-encoded is caught.

## [0.5.0] — 20.10.2026

Stage 3a «Connections»: the modules API finally has a screen. Connecting a publisher, team
comments or design-system tokens no longer takes `curl` or an agent: the space menu opens a page
with module cards grouped by role, a side panel for settings and secrets, a check, a one-step
replacement of the provider of a role, and turning a module off. The server gains one thing, an
atomic `replace` in `module-enable`. Design:
`docs/superpowers/specs/2026-10-20-connections-screen-design.md`; plan:
`docs/superpowers/plans/2026-10-20-connections-screen.md`. The legacy (in-house) space is
unchanged: `tests/legacy-golden.test.mjs` is green without a re-shoot.

### Added

- **`replace` and `replaced` in `POST /api/module-enable`** (`app/deai_modules.py`,
  `app/serve.py`). `replace: true` turns off every other module that holds one of the roles of
  the module being enabled (an explicitly enabled one or the implicit `static-publish`) in the
  SAME write of `space.json`, under the same lock, and the answer lists them in `replaced`
  (`[]` when nothing was in the way). Their settings and secrets stay. A space is never without
  a provider between the two steps. Without `replace` the old `409 role-taken` stays; a
  `replace` that is not a boolean (an explicit `null` too) is `400 bad-settings` before anything
  is written; `module-settings` and `module-disable` ignore the key. `replace` is refused for a
  module that did not load (a damaged `module.json` or a `server.py` that fails): the answer is the
  module's own code, `module-error` or `bad-manifest`, before any secret is written — otherwise the
  working provider would be turned off and nobody would take the role. Enabling such a module
  without `replace` works as before: a free role is taken and its `check` says why it does not
  work.
- **The «Connections» screen.** A page of the existing home overlay, next to «Tasks» (the same
  entry, exit and clean view; the bar shows a flat crumb «Connections»). It shows the space that
  was current on entry; every request carries an explicit `space`, so a write goes where the
  person is looking even if an agent switches the active space meanwhile. Switching the space
  with the chip while the page is open keeps you on Connections of the new space. Returning to
  the window re-reads the modules (an agent may have changed them over the API); an open panel
  keeps its form.
  - **Entry points:** the space menu, «Connections…»; ⌘K, «Connections of the space “…”» (also
    found by «connections», «integrations» and «modules»); and a «Connections» button in the
    head of the «Tasks» page of a space without integrations (the head of a space with
    integrations is unchanged). On the page itself the menu and ⌘K entries are not offered.
  - **Cards by role** — Publishing, Team comments, Design-system tokens, then other roles
    alphabetically; a module with several roles stands in the section of its first one. Each
    section carries a line **«Now: …»** with the current provider of the role from
    `capabilities`: a module, the built-in in-house integration (a module in that role
    overrides it), or none, with what that means for the role (no publish button in the bar;
    comments only local; the inspector compares without the space's tokens). Modules that are
    on in `space.json` but not installed on this computer sit in their own section. A card has
    the role icon, the name, the roles, a badge (Connected, Not checked, Error, Off, Not
    installed; the implicit `static-publish` is also marked «default»), a description for the
    built-in modules, the reason in plain words for a module that is on and fails (the code of
    the check, plus its `detail`), and the actions: Configure, Check and Turn off, or Connect.
    The card's «Check» runs `POST /api/module-check` and re-reads the list.
  - **The side panel** (420 px, full width under 720 px; `role="dialog"`): the fields come from
    the `settings[]` of the entry — text, path (with the hint on `{home}`, `{space}` and
    `{space_id}`), a flag, a list, a secret. Required fields are checked before any request;
    only changed keys are sent. Two modes: «Connect» (`module-enable`) and «Configure» (then
    «Save», `module-settings`). The footer «Check» checks what is SAVED, so it is disabled while
    there are unsaved changes. A passed check closes the panel with a toast; a failed one leaves
    it open with «Saved, but the check failed.» and the cause (the state is already written,
    as the API has always done); an HTTP refusal is shown in the form, nothing is saved. Esc and
    the cross close the panel and, with unsaved changes, ask «Discard…». Leaving the page,
    opening another panel or «Turn off» of the module whose panel is open go through the same
    question; focus returns to the control it was on after every repaint.
  - **Secrets are set, not set, or unknown** (the secret store cannot be read) and are never
    shown: the server never returns a value, the field is always empty (empty means keep), and
    «Erase» marks an optional secret that is set for erasing (`null` on save). Password fields
    are cleared after every answer; a typed value lives only as a property of the field, never
    in the markup (it also survives a language switch).
  - **Replacing the provider of a role.** If the module's role is held (a module or the implicit
    `static-publish`), the screen asks «… is currently handled by “…”. Connect “…” instead? “…”
    will be turned off; its settings stay.» and sends `module-enable` with `replace: true`. The
    consent is fresh: after «Replace» the list is re-read and compared with whom the question
    was about; if the holders changed while it was open the screen asks again with the new names
    (a second change is a refusal, «Another module already holds this role — reload the page and
    try again», and nothing is written); if the role
    became free the write goes without `replace`. The toast names the modules that were turned
    off.
  - **Turning a module off** asks first, and when the module is the current provider of its
    role it spells out the consequence (no module left in the role, or the built-in in-house
    integration takes the role back). Settings and secrets stay; it can be connected again.
  - **Human texts** for the codes of the check (`bad-settings`, `module-error`,
    `check-timeout`, `secrets-unreadable`, `bad-manifest`, `bad-folder`, `not-writable`,
    `no-token`, `vercel-auth`, `vercel-error`, `vercel-busy`, `bad-key`, `no-schema`,
    `supabase-error`, `network`; an unknown code shows «The check failed.» with its text as the
    detail) and for HTTP refusals (`role-taken`, `bad-settings`, `unknown-module`,
    `unknown-space`, `space-json-unreadable`, `spaces-off`, `unwritable`), in Ukrainian and
    English. Names, descriptions and field labels of the four built-in modules are in the
    dictionary; for any other module the page shows the manifest's own labels.
  - **Page errors:** a failed `GET /api/modules` is a banner with «Try again»; an unreadable
    `space.json` says where to fix it and draws no cards.
  - **«Through the agent»** — a dashed block at the bottom with the real API routes of this
    space.
- **Files:** `app/connections-model.js` (pure logic: grouping, the «Now» line, card, reason,
  form, patch, role holders, texts of codes) and `app/connections-view.js` (markup), wired into
  `app/app.js`; `.cn-*` rules in `app/styles.css`; keys `cn*` and `spaceConn` in `app/i18n.js`.
  Everything that comes from the server or a manifest goes through `esc()`; `detail` is cut to
  300 characters.

### Changed

- The text of the publish error `vercel-auth` now says where the screen is («space menu →
  Connections»); before it referred to a screen that did not exist yet.
- After every successful `module-enable`, `module-settings` and `module-disable` the canvas
  refreshes lightly (`afterModulesChange`): the spaces are re-read and the bar is re-rendered
  with the fresh `capabilities` (the publish buttons), without reloading the hidden frame. The
  frame is refreshed by `render()` when the person leaves the overlay, so the comment adapter and
  the inspector's tokens are the new ones. The picked iteration, the filters of «Tasks», the
  publish notices and the tuner's package are not reset. (A first version reloaded the old
  document over a task opened right after leaving the screen — a 404 in the frame — and a full
  re-render reset the picked iteration; both are covered by live tests.)
- `preflight` with `replace` does not check the role: the write frees it under the lock.
- The Overview commenter re-reads the comments provider after a module change: `afterModulesChange`
  first calls `overviewComments().invalidate()` (it destroys the layer, which closes the old store
  and its polling, and forgets the «iteration | channel» key; a start still in flight is dropped
  by an epoch), so new pins on «Overview» go to the service the person has just configured, not
  to the one they left, with no reload needed. From the same final review: the frame is kept
  untouched only while the overlay is open (`render({ keepFrame: homeOpen })`; if the person left
  before the write answered, nothing would reload it later); the logo is no longer lit as the
  current page on «Connections» (the crumb names it); Esc during an IME composition no longer
  closes the panel.

### Known limits

- **No real Vercel or Supabase in the live tests.** Their `check` goes to the network from the
  server process, so the live scenarios use the fixture module `memo-publish` (role `publish`, a
  local check) behind the `DEAI_EXTRA_MODULES` seam. The two modules themselves are still tested
  against fakes, as in 0.3.0 and 0.4.0.
- Not in this release: the first-run wizard (3b, 0.6.0); a space's own modules from
  `<space>/modules/` with a trust dialog, and a «custom» mark on the card (3c, 0.7.0); picking a
  folder with a system dialog; a banner «N connections with an error» on «Tasks»; icons and
  descriptions from manifests (only the built-in modules have them).

### Tests

`npm test` at 0.5.0 is green: 1458 node tests (plus `inspector-core`), 2349 Python tests in
`tests/` (1 skipped), 168 in `bin/`, 170 in `app/` (0.4.0: 1336, 2332 with 1 skipped, 168, 170).
The three Python suites were also run on Python 3.9.6, the oldest supported version, with the
same result (2349 with 1 skipped, 168, 170); `npm test` itself uses Python 3.13. One timing test
(`test_two_mebibytes_of_css_parse_in_time`, a 4-second budget) fails when two full suites share the
machine; run alone or in a quiet suite it passes.

New: `tests/connections-model.test.mjs` and `tests/connections-view.test.mjs` (hostile names,
labels and details are escaped, only known icons, no secret value in the markup);
`tests/connections-css.test.mjs` (every class of the markup has a rule, long strings wrap, the
panel is hidden outside the overlay and in the clean view, only tokens);
`tests/connections-wiring.test.mjs`; the entry points in `tests/shell-bar.test.mjs`,
`tests/shell-palette.test.mjs` and `tests/tasks-home.test.mjs`; `invalidate()` of the Overview
commenter in `tests/overview-comments-module.test.mjs` (a new store after the change, a start in
flight at the moment of the change, a stale start that fails) and the logo on «Connections» in
`tests/bar-model.test.mjs` and `tests/shell-bar.test.mjs`. On the server, the class `Replace`
(17 tests) in `tests/test_modules_api.py`: one write of `space.json` for both changes, the
implicit and an explicit holder, no conflict, a non-boolean `replace`, a module that did not load,
the settings of the replaced module stay, `role-taken` without `replace`, parallel replaces.

The live test `tests/live/connections.test.mjs` (a real server in an isolated machine, a real
Chromium, 19 scenarios, one file at a time) covers the entry from the menu, the sections and the
«default» mark, connecting `css-tokens`, replacing the publisher with the fixture module,
declining a replacement, a failed check, erasing a secret, a secret that shows up nowhere (a DOM
snapshot, a watcher on every DOM mutation, request addresses and response bodies), switching the
space with a panel open, the frame after leaving the screen, the fresh consent, and focus and Esc.
Scenario `e2` of `tests/live/comments.test.mjs` changes the address of the comments service on
the «Connections» screen and checks that «Overview» then reads the pins of the new service and
makes no request to the old one.

## [0.4.0] — 20.10.2026

Stage 2b-2 «Team comments as a module»: the role `comments` becomes a contract that does not
depend on the service — a browser adapter plus four server functions — and the first module on
it connects the person's own Supabase project. Design and the list of deviations from the
original spec: `docs/superpowers/specs/2026-10-19-comments-role-design.md`. How to write a
module for another service: `docs/modules/comments.md`.

### Added

- **The `comments` role** (`app/deai_modules.py`, `app/serve.py`). A module has two halves.
  The *browser adapter*: the files listed in the new manifest field `client` (1–8 plain `.js`
  files, up to 512 KiB each, loaded in order); the last one registers
  `window.DeaiComments.create(cfg)`, which returns the comment layer's store (`load` and `save`;
  optionally `ready`, `remove`, `subscribe`, `close`). The *server half*: `client_config`,
  `list`, `resolve`, `check`. The core builds the channel of a task (`deai/<space>/<task>`,
  `…/internal`) and gives it to both halves; `capabilities` gains `comments`.
- **`public` secrets.** A `secret` setting may be marked `"public": true`: the value stays out
  of `space.json` like any secret, but may reach pages. The core checks `client_config` (a flat
  object of up to 4 KiB; no value of a non-public secret in a key or a value) before it goes
  anywhere.
- **Adapter route** `GET /api/module-client/<id>/<file>`: built-in modules of the role, only the
  files their manifest lists, `text/javascript`, `nosniff`, ETag/304, opened by walking
  directory descriptors (no symlinks, no hard links); every refusal is the same 404.
- **Module comments wherever the layer runs.** On the canvas page (`/commented?ch=project`) and
  the «Team» tab — now also in a space without integrations, as soon as a module provides the
  role. On the Overview (the adapter loads into the shell; the hard-coded CDN is not used). In
  the published previews of both publish modules, folder and Vercel (`comment-layer/` holds the
  layer and the adapter files, relative paths, the task's channel) — the Vercel preview finally
  has comments. For the agent: `bin/inbox.py`, `bin/state.py` and the `/comments` route read
  and close project pins through the module's `list` and `resolve`. `resolve` must be idempotent
  and effective (afterwards `list` shows the comment as resolved).
- **`supabase-comments`** (role `comments`). Your own Supabase project as the team-comments
  service. Settings: `url` (`https://<ref>.supabase.co`) and `key` (the public key, a secret that
  is allowed into pages). `supabase.min.js` is supabase-js 2.110.0 (MIT), vendored unchanged
  with its licence, so there is no CDN. `schema.sql` (table, row-level security, guard triggers,
  realtime) is run once by the person; the module never changes the schema. `server.py` is a
  standard-library REST client: `list`, `resolve`, and `check` with the verdicts `bad-key`,
  `no-schema`, `network` (and `supabase-error`). It refuses a **service key** (`sb_secret_…`, or a
  JWT whose payload says `"role": "service_role"`) with `bad-settings`: the key is public by design
  and goes into every page and preview, so a service key there would be full access to the
  database. The adapter creates its supabase-js client without user authentication (no token
  refresh interval, no `BroadcastChannel`, no session writes), smooths a burst of realtime events
  into one re-read, offers `refresh()` to the Overview, and `close()` leaves the channel *and*
  closes the realtime socket. `schema.sql` qualifies every name with `public.`, grants the table
  to the API roles and warns that an existing table `public.comments` of your own would be
  adopted. Off by default; the *Comments* section of the main README has the four steps, and the
  module README the details, the verdicts of `check` and the security notes.
- **Guide for module authors** `docs/modules/comments.md`: both halves, the comment shape, the
  channel, `client`, `public`, CORS (including `Origin: null`), security notes, how to test, a
  complete minimal example. The reference is the test module
  `tests/fixtures/modules/memo-comments/` (a tiny HTTP service): it passes the same end-to-end
  checks as Supabase, which is the proof that the role does not depend on the service.
  `DEAI_EXTRA_MODULES=<dir>` — a second folder of modules that act as built-in — is a test seam
  only (the server prints one line about it at start).
- **Live tests** `tests/live/comments.test.mjs`: a real server in an isolated machine, a real
  Chromium and a tiny comment service on `127.0.0.1` — the pin on the canvas page and the «Team»
  tab, on the Overview and in the published preview (the sandbox with `Origin: null`, with a
  negative control without CORS); a pin created in the UI arriving in the service and in a second
  window; the ЛІГА space unchanged.

### Security and privacy

- **No silent fallback to the shared in-house comments service.** In a space with integrations
  the hard-wired channel is a Supabase project shared by the whole company, where pins carry
  snapshots of private mockups. When a module the person enabled is missing or broken, or
  `space.json` cannot be read, `provider('comments')` raises instead of answering `'legacy'`:
  the canvas page shows local comments with a notice, the Overview and `inbox` report the
  error, a publish goes on without comments and says `comments_unavailable`. The same error
  — instead of silence — in a space *without* integrations, where there is no shared service
  to fall back to but «no team comments» with no reason would be a lie. Only an entry that
  could have been a comments module counts as lost (its manifest declares `comments`; or the
  manifest cannot be read and the id is not a built-in module of another role; or it is the
  built-in `supabase-comments` missing from the catalog): a stale entry of some unknown module
  does not take the ЛІГА comments away.
- `client_config` guard: no value of a non-public secret may appear in a key or a value, in raw,
  escaped or URL-encoded form; lone surrogates and huge integers are refused; the object is
  copied before it is checked, and the copy is what pages get. It stops accidents; it is not a
  trust boundary.
- **Agent output is sanitised.** Texts of module errors and module comments lose control and
  invisible characters (ESC and the other C0/C1 codes, zero-width and bidirectional marks,
  Hangul and Khmer fillers, the blank Braille cell, musical beam and tie controls, variation
  selectors, tag characters, surrogates), one-line fields lose line breaks, errors are
  cut to 300 characters, `meta.shot` is dropped. A comment id must match
  `[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}` (the layer produces UUIDs or `c-<digits>-<base36>`): any
  other is skipped, and `resolve` never passes the module another one. At most 5000 comments
  and 2 MiB per `list`; the number of skipped and cut items is reported.
- The adapter is served from an opened file descriptor (no symlinks, no hard links), only the
  files the manifest lists, and its names are compared with the core bundles without regard to
  letter case (a file named `Comment-Layer.min.js` would overwrite the layer on macOS).
- The local `/published` sandbox gets `allow-modals` (without it `prompt()` and `confirm()` of the
  comment layer return `null` and `false`: every author is «Anonymous» and «Delete» does
  nothing); `allow-same-origin` is still absent.

### Changed

- The `manifest.json` of a preview gains one field, `"build"`: `"legacy"` for the in-house build,
  `"module"` for a publish module. Everything else of the ЛІГА build is byte for byte the same;
  `ops/reseal_gate.py` now re-seals exactly the `legacy` builds (old builds without the field
  fall back to the previous rule).
- A space with integrations whose `space.json` cannot be read now publishes the ЛІГА way
  without shared comments and says `comments_unavailable` (before: with the shared Supabase).
- A publish module (`static-publish`, `vercel-publish`) in a space whose comments are the
  in-house shared channel (`'legacy'`) publishes without comments, as in 0.3.0.
- The «Team» tab, the comment mode `project` and the palette follow `capabilities.comments`
  instead of `integrations`; a response without the key (an older server) falls back to
  `integrations`.
- `bin/import_preview.py` knows the comment snippet of a module (with and without the gate).

### Known limits

- The rules in `schema.sql` are open: whoever has the public key — and it is inside every page
  you publish — reads and writes the comments of that project, other channels included. Use a
  dedicated Supabase project per team.
- The adapter's JavaScript runs on the canvas origin, with the power of the canvas page. So only
  built-in modules load; a space's own modules come with the trust dialog in stage 3.
- **Not run against a real Supabase in CI.** `supabase-comments` is tested against an in-process
  fake REST server and a fake supabase-js; a first real run should confirm the realtime
  delivery, the `no-schema` verdict on a fresh project and the effect of
  `Prefer: return=representation` on `resolve`.
- Screenshots of pins are not supported by the role (it has no file storage): the one the layer
  adds travels inside the comment (`meta.shot`) and the agent side drops it. The layer loads
  `html2canvas` from jsDelivr when a pin is created (as before modules).
- The core gives `check` and `client_config` 5 seconds and `list` and `resolve` 10;
  `supabase-comments` answers inside shorter budgets of its own — 4 seconds for `check`, 8 for a
  `list` or `resolve` request (per socket operation) — so a slow project is reported as
  `network` with its reason. A DNS lookup that never returns lies outside that budget and can
  still end as the core's `check-timeout`.
- Supabase's own `max-rows` setting (default 1000) cuts every API answer silently, so `list`
  shows the agent at most that many comments of a channel; raise it for the project if channels
  can grow that big.
- **Comment text is untrusted input for the agent.** Anyone who holds the public key — it is
  inside every published page — can *write* comments, and the agent reads them as work items.
  The sanitiser only removes terminal and invisible-character attacks; multi-line `text` is
  printed as is, so a visible instruction inside a comment is still an instruction the agent
  sees.
- A page that saves its whole cache after it missed a realtime event can re-open a comment the
  agent resolved in the meantime (the same as the in-house channel always did).
- The local `/published` view runs in a sandbox with the opaque origin `null`: the comment
  service has to allow CORS for it (`Access-Control-Allow-Origin: *`; Supabase does).
- Module management has no UI yet (stage 3): enable and configure modules over the API.

### Tests

`npm test` at 0.4.0 is green: 1336 node tests (plus `inspector-core`), 2332 Python tests in
`tests/` (1 skipped), 168 in `bin/`, 170 in `app/` (0.3.0: 1258, 1938, 156, 170). The three
Python suites were also run on Python 3.9.6, the oldest supported version, with the same result
(2332 with 1 skipped, 168, 170); `npm test` itself uses Python 3.13. Of them,
`supabase-comments` has 89 Python tests (a fake REST server under a network tripwire, end to end
through the core: the page, the Overview, the adapter route, `inbox`; service keys, timeouts at
the default budgets against a hung service, a parity check of the host rule with the core's),
25 node tests (the adapter against a fake supabase-js) and 3 that run the REAL vendored
supabase-js with the adapter in a `vm` (the wire shape, no timers left after `close()`); the
generic role is covered on the `memo-comments` fixture. The Python suite also passes with
`DEAI_EXTRA_MODULES` exported for the whole run (the core tests that list or load a catalog unset
it for their own).
The fixes of the per-task reviews carry their mutation proofs in the commit messages. Live (run on
20.10.2026): the new `tests/live/comments.test.mjs` (7 tests) passes together with
`modules.test.mjs` (5), `vercel.test.mjs` (7), `spaces.test.mjs` (8),
`comment-audience.test.mjs` (4) and `overview-comments.test.mjs` (21) — 52 tests in total.
Mutation runs confirmed that each scenario guards its rule (a refusing adapter route turns the
canvas, Overview and UI-creation scenarios red; a core without module comments in builds turns
the preview scenario red; losing `'legacy'` turns the ЛІГА scenario red).

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
