# Changelog

All notable changes to Deai Canvas, newest first. Format follows
[Keep a Changelog](https://keepachangelog.com/); dates are DD.MM.YYYY.

## [0.23.2] — 12.11.2026

### Fixed
- **Feedback never left a Mac with the Python from python.org.** The sender opened HTTPS with the default certificate store, which that
  Python does not have, so every send failed with `CERTIFICATE_VERIFY_FAILED`, was counted as a network error and stayed in
  `outbox` (retried every hour, never delivered). It now uses the `certifi` store when the package is present, like the dashboard
  and the other modules; queued notes go out on the first retry after the update.

## [0.23.1] — 12.11.2026

Before the team release: feedback now reaches the maintainer from every copy, and the tails of 0.23.0.

### Added
- **The feedback collector ships with the product.** `app/feedback.json` carries the address and the publishable key of the Deai
  feedback project, so a note sent from any copy reaches the maintainer without setup; notes that waited in `outbox` since 0.23.0
  go out on the first background retry after the update. The key is public by design: it can only insert (checked against the
  live project with that key: insert is accepted; select, update, delete, a forged `created_at`, and listing, reading, overwriting or
  deleting screenshots are refused). A fork points at its own collector as before (`DEAI_FEEDBACK_URL`/`DEAI_FEEDBACK_KEY` or
  `config.json`).
- **An empty `DEAI_FEEDBACK_URL` turns the collector off** (the variable is present, the value is blank): neither `config.json` nor
  `app/feedback.json` is read. Tests and live fixtures rely on it; a guard (`tests/test_no_network.py`) fails any test that starts
  the server without switching the collector off.

### Fixed
- **«What's new» fetched the tag again on every open** when the tag had no `CHANGELOG.md` or did not resolve: these outcomes are
  now cached for a minute, like a failed fetch.
- **The bar of Tasks, Connections and the new-space wizard at narrow widths**: the crumb collapsed to 20px and its label painted over
  «Back», and a long task id in «Back» pushed the bar 219px past the window at 320px. These pages now give the whole bar to the left
  zone; the decorative icon yields first, labels end in an ellipsis (the full id stays in the tooltip). The canvas task bar and the
  external preview bar are unchanged.
- **The fixture heuristic of the task registry** (`bin/registry.py`) took every task of a home folder that itself lives in a temporary
  folder for a test fixture; a home equal to a temporary root (`HOME=/tmp`) still keeps the detection on.
- `ops/feedback-collector.sql` creates `pg_net` in the `extensions` schema (Supabase security advisor «Extension in Public»). A
  project that ran the 0.23.0 script keeps working; to move it: `drop extension pg_net; create extension pg_net with schema extensions;`
  (the trigger calls `net.http_post`, which stays in schema `net`).

### Tests
- `inspector-ds` checks verdicts against the tokens of a space (`css-tokens`), not against the static snapshot, which is empty in
  Deai by design; it got its own port band. New live test `bar-narrow` (320–520px, long task id).

## [0.23.0] — 11.11.2026

Feedback and updates. Two things a person asked for: tell the maintainer about a bug or an idea without leaving the canvas, and
learn that a new release exists (and install it) without a terminal. The update side checks release tags `vX.Y.Z` of the
remote the install came from; the feedback side queues a note locally and sends it to a collector the owner configures. In an isolated
process (tests) neither reaches the network: the update thread only records `disabled` (unless the remote is a local path),
the feedback flush thread does not start, and `apply` refuses without the test seam. Design: `docs/superpowers/specs/2026-11-11-feedback-and-updates-design.md`;
plan: `docs/superpowers/plans/2026-11-11-feedback-and-updates.md`.

### Added

- **`app/updater.py`**: the version (`package.json` is the only source; `liga_migrate._tool_version` reads it, a test pins they agree),
  the remote, the check of tags, the state file `<DEAI_HOME>/update.json` (0600; not written when the process is isolated: the
  state then lives in memory), a background thread (first check 5-30 s after start, then every 6 h with jitter), and the apply.
- **`app/feedback.py`**: the diagnostics builder, the ring of server errors, the local queue
  `<DEAI_HOME>/feedback/{outbox,sent,failed}/<id>.json` (directories 0700, files 0600; the record is written BEFORE any network call;
  `failed/` after 20 attempts or 30 days, never deleted), the sender (one insert into the table and, if asked, one screenshot into
  the bucket), and the config chain `DEAI_FEEDBACK_URL`/`DEAI_FEEDBACK_KEY` > `<DEAI_HOME>/config.json` > `app/feedback.json`
  (only `https://`; loopback `http://` only for an isolated test run).
- **`app/redact.py`**: one filter for every line of the diagnostics (see *Privacy* below).
- **Routes** (flat names, "machine" routes: no space is pinned, they work with a broken registry; the prefixed form `/t/<id>/api/…` is `400`):
  `GET /api/update`, `GET /api/update-notes`, `POST /api/update-check`, `POST /api/update-apply`, `POST /api/feedback-preview`,
  `POST /api/feedback`.
  - Apply: `202 {ok, to, restart: auto|manual}`; `409 isolated|busy|nothing-to-update|not-git|dirty|detached|worktree|diverged|tag-conflict|tag-missing|tag-mismatch|fetch-rejected|disabled|bad-remote|no-remote`, `503 offline`, `500 error|merge-failed|rolled-back|rollback-failed`.
  - Notes: `{ok, notes|reason}`, reasons `busy|offline|disabled|no-update|no-git|fetch-rejected|tag-missing|tag-conflict|no-changelog|error|bad-remote|no-remote`; a cross-site request is `403`.
  - Feedback preview: `{ok, diag, diag_hash, ring_seq, shot}`; send: `{ok, id, state: sent|queued, reason?, memory_only?}`, queued reasons `no-collector|offline|rejected|network-blocked`; `409 diag-changed`, `413 body-too-large`.
- **UI:** a pill in the bar when a release tag exists, a dialog «What's new» with the CHANGELOG sections between the installed version and the
  latest (English, as in the repo), a button «Відгук» on every screen and ⌘K entries «Баг / ідея» and «Перевірити оновлення»
  (also on the Tasks, Connections and wizard screens), a feedback dialog that shows exactly what will be sent, a ring of the last 20 client errors.
- **`ops/feedback-collector.sql`** (the collector for the owner's own Supabase project), **`app/feedback.json`** (`{"url": "", "key": ""}` shipped empty).
- **Environment:** `DEAI_NO_UPDATE_CHECK=1` (no checks, no network), `DEAI_UPDATE_REMOTE` (a remote name or an `https://`/`ssh://`
  address instead of the default), `DEAI_FEEDBACK_URL`, `DEAI_FEEDBACK_KEY`; `DEAI_UPDATE_TEST_APPLY=1` is a seam for tests only
  (without it an isolated process refuses `apply` and the restart).
- **Tests:** a no-network check (the live fixture environment blocks the update check and the feedback sender, `tests/test_no_network.py`),
  an insert-only check of the collector SQL (`tests/test_feedback_sql.py`), a check of the shipped `app/feedback.json`
  (`tests/test_feedback_outbox.py`), and live tests of the pill, the update dialog, `apply` in a throwaway clone and the feedback dialog with a fake collector.

### Changed

- **`zone1` of the bar** gets two controls at the END (`feedback`, `update`), so the existing indexes are unchanged; the palette
  gets `appActions` on the home, Connections and wizard screens too.
- **`_guarded` records unexpected exceptions** into the error ring and re-raises (the response is unchanged); client disconnects are not recorded.
- **`isolation.writes_allowed(home)`**: the new files are written only to a home that the process may really write to.
- **Amendments to the spec, in one line:** flat route names (a nested path would be invisible to the `bad-body` guard); the
  screenshot is `image/webp` or `png` up to 2 MB, a bigger one is skipped (`shot.skipped: too-big`); the response of `/api/update`
  carries `boot` (the process id of the server) so the page can tell an old process from a restarted one; `disabled` is a state of the check.

### Hardening decided in review

- **Update.** The tag is verified again against the CURRENT remote at apply time, and `package.json` of the tag must carry the same
  version (`tag-missing|tag-conflict|tag-mismatch`); the fetch runs with `fsck` and without submodules (`fetch-rejected`); the tree is
  rechecked clean right before the merge; the merge is `--ff-only`. A rollback (`reset --hard` to the recorded old head) happens only
  after a merge that succeeded or one that our own timeout killed — a user's edit is never reset. A failed restart sets
  `restart_failed` for that boot. «What's new» fetches without blocking the apply, caches a failure for 60 s, and refuses cross-site pages.
- **Smoke test.** After the merge a child `python3 -B` compiles every `app/*.py` and `bin/*.py` (no `.pyc` is written) and imports `serve`
  in an isolated environment; a failure rolls back.
- **Privacy (`redact`).** Absolute paths shrink to the last segment, local canvas URLs keep the file extension only, 8+ digit runs,
  card numbers, IBANs and labelled secrets (`token=…`, `password: …`, `Authorization: Bearer …`) are hidden, e-mails and `user:pass@` are removed,
  a key-like string is hidden. The server error ring stores the exception type and the application frame only, never the message.
  The preview equals what is sent: `diag_hash` and `ring_seq` of the preview come back in the send, and a changed diagnostics is `409 diag-changed`.
- **Collector (SQL).** The public key may only insert (rows and screenshot objects; no select, update, delete, no listing); the Teams
  card is throttled (more than 10 rows in 60 s send no card), markdown and links are neutralised, a missing or non-https webhook secret never fails the insert.

### Differences for a person

1. A pill appears in the bar when a release tag newer than the installed version exists; a click opens «What's new» and «Update».
   An install that is not a clean git checkout of a release line (local edits, a detached head, a local commit) gets an honest refusal and the command to run.
2. A button «Відгук» is on every screen. Until the owner configures a collector the note is stored on this machine (`<DEAI_HOME>/feedback/outbox`)
   and the dialog says so; it is sent by itself once a collector is configured.
3. Nothing is sent without a click: the dialog shows the diagnostics and the screenshot choice first.
4. `DEAI_NO_UPDATE_CHECK=1` turns the checks off completely.

### Rolling back 0.23 → 0.22.1

Safe: `git checkout v0.22.1` and restart. 0.22.x ignores `update.json` and the `feedback/` directory; both can be deleted.

### Left for 1.0 / next

- **Signed release tags.** The update trusts the remote tag: whoever can move or publish a tag on the remote runs code on every install. Verification of signatures belongs before 1.0.
- Rate limits and quotas on the collector (the Teams card is throttled, rows are not).
- A reader or an admin screen for the collected feedback (today: the Supabase dashboard).
- A restart on Windows (the update applies and asks for a manual restart).
- A persistent server error ring (it lives in memory and is reset by a restart, an update included).
- Notes with `no-changelog` or `error` are not cached (each opening of the dialog tries again).
- The dashboard push has a 60 s budget while compat batches are of 3 cards.

### What the owner does

1. Create a Supabase project «deai» (dedicated: the script does not check what is already in a project) and run `ops/feedback-collector.sql` in its SQL editor.
2. Put the Teams webhook into Vault under the name the script uses: `select vault.create_secret('<webhook address>', 'teams_feedback_webhook_url');`
3. Verify with the anon key that select, update and delete on `public.feedback`, and reading or listing objects of the `feedback-shots` bucket, are refused.
4. Put the project URL and the publishable key into `app/feedback.json` (in a later release) or into `<DEAI_HOME>/config.json` as `{"feedback": {"url": "…", "key": "…"}}`.
5. Make the GitLab mirror receive release tags (the update reads tags from the remote the install came from).

## [0.22.1] — 11.11.2026

### Fixed
- **The LIGA dashboard sync failed for most cards with `HTTP 400 [23514]`.** The comment-layer schema keeps the trigger
  `ov_update_scope_guard` on `overview_projects`: a key under row-level security (the public key Deai uses) may update at most
  3 dashboard rows per request, and a bigger request is refused whole (`check_violation`). `supabase-dashboard` sent up to 50 cards per request (design-office sent one).
  With `compat: comment-layer` the module now sends batches of `COMPAT_BATCH` = 3; other spaces keep 50.

## [0.22.0] — 10.11.2026

Stage 4d-4c: no runtime decision depends on the space flag `integrations` any more, and the API value `'legacy'` is gone. The
question «may this space push outward?» is answered by a record: the space has an **enabled `vcs` record with the LIGA scheme**
(`compat: design-canvas`), the same fact the browser already read as `isLegacyVcs`. `static-publish` becomes an explicit record
instead of an implicit default, the dashboard sync log becomes one, and the JS fallback branches, `_liga_flow` and `_liga_like`
leave. For a person nothing changes in the usual case (a migrated LIGA or a plain space); the differences are listed below.
Design: `docs/superpowers/specs/2026-11-10-legacy-surface-gone-design.md`; plan: `docs/superpowers/plans/2026-11-10-legacy-surface-gone.md`;
behaviour of 0.21.0 pinned by `tests/fixtures/outbound/before-4d4c.json`.

### Added

- **`deai_modules.vcs_outbound(space)`**: true only for an enabled `vcs` record with the LIGA scheme; any error (module, registry,
  layer off, space not fixed) means false (fail-closed). It gates autopush, the push of the team registry, the shared ssh key, the
  `gitlab` target of `task-new` and the comment channel.
- **`spaces.ensure_static_publish` / `spaces.materialize_static_publish`** and **`spaces.RoleOff`**; `liga_migrate.liga_space`
  (the predicate «is this space a LIGA», by the key or by the root markers).
- **Headers `Deprecation: true` and `Link: </api/vcs-…>; rel="successor-version"`** on `/api/gitlab-status|sync|pull`.
- **Error code `gitlab-needs-vcs-scheme`** (400) of `task-new`.
- **Guards:** `NoIntegrationsFlag` (AST; per-function exceptions `spaces._validate` and `liga_migrate._liga_integrations`),
  `NoLegacyApiValue`, `NoIntegrationsInClient`; a leaf-exact parity test against the 0.21 snapshot.

### Changed

- **`task-new` without `space`** goes to the first registry entry with `legacy: true`, otherwise to the current space.
- **`from` is allowed in any space** (LIGA included); `from` together with `gitlab` is `400 bad-request`. **`gitlab` needs the LIGA
  scheme**, otherwise `400 gitlab-needs-vcs-scheme`.
- **`static-publish` is an explicit record** in `space.json`: new spaces get it, existing spaces get it at startup when they have
  no enabled publisher (this includes a `legacy: true` space that is not a LIGA, an old pre-spaces install: parity with the 0.21
  implicit publisher). A record disabled by a person is left alone.
- **The dashboard sync log** moved from `~/.claude/pipeline-feedback/overview-sync.log` to `<DEAI_HOME>/logs/dashboard-sync.log`
  (directory 0700, file 0600): one log for all spaces, each run starts with a header line `--- <ts> sync <target>`.
- **`describe` has no `integrations`**; `/api/task` has `comment_channel: null` where the space has no comments provider.
- The bin hints of `bin/state.py` point to `/api/vcs-*`.

### Removed

- `spaces.integrations_for`, `spaces.integrations_on`, `spaces.require_integrations`, `spaces.IntegrationsOff`, `serve._outbound_ok`,
  `serve._liga_flow`, `serve._liga_like`, `OVERVIEW_LOG`, `API_IMPLICIT`, `IMPLICIT_MODULE`.
- The responses 409 `no-integrations-space`, 400 `gitlab-needs-integrations`, 400 `from-needs-plain-space`.
- The i18n keys `cnNowLegacy`, `cnDisableLegacy`, `wzErrFromPlain`.

### Fixed

- **A LIGA migration without the `integrations` key** decides by the root markers of the legacy `tasks.json` (Amendment 1), so a
  fresh LIGA migrates instead of being stuck at `skip-integrations-off`. When the key is absent, a read error of the legacy root
  counts as a LIGA (nothing is materialised; the migration gives `skip-tasks-unreadable`).

### Differences for a person

1. **A plain space:** nothing visible. Publishing works as before, but `space.json` now holds a `static-publish` record. Connections
   shows it as an ordinary enabled module, not as a default, and it can be disabled like any other module.
2. **A migrated LIGA:** nothing visible. The sync log moves (see above); the `gitlab-*` aliases answer with `Deprecation`.
3. **An unmigrated LIGA:** as in 0.21, except for outbound actions. It no longer autopushes, pushes the team registry or uses the
   shared ssh key until its migration completes. This is fail-closed: an outbound action needs an explicit `vcs` record with the
   LIGA scheme. Migration normally runs at startup, so this is transient; if it is skipped or aborted, pushing stops until it is fixed.
4. **A setup where dev-pipeline sends `task-new` with `jira`/`track` and there is no LIGA:** instead of 409 `no-integrations-space`
   the task goes to the current space (or 400 `unknown-track` when it has no such track).
5. **Developers and tests:** with the layer off (`DC_TASKS_FILE` without `DEAI_HOME`) there is no autopush (there was one).
   A test that needs a push builds an explicit space with a `git-sync` record plus `compat`.
6. **`comment_channel` in `/api/task` is null** where the space has no comments provider: layer off, an unmigrated LIGA, an
   unreadable `space.json`. The Teams-mute toggle still uses the fallback channel.
7. **`gitlab` in `task-new` needs the LIGA scheme**, otherwise 400 `gitlab-needs-vcs-scheme`; that includes an unmigrated LIGA and
   layer-off. A plain `git-sync` space without `compat` no longer clones from `gitlab` alone (client and server agree).
8. **Tasks home:** an unmigrated LIGA now shows the head buttons «Підключення / Нова задача», plus the empty-space hint when it has
   no tasks; its Team tab was already hidden in 0.21 once data loaded, and it no longer flashes while loading. A plain space WITH
   a dashboard module keeps its Team tab and no longer shows those head buttons or the hint.
9. **`/api/gitlab-status|sync|pull`** return identical bodies and status codes, now with `Deprecation: true` and a `Link` to the
   successor. Removal comes in 1.0, after the dev-pipeline skill switches over.

### Rolling back 0.22 → 0.21

Safe. The `integrations` key is not deleted from existing registry entries; 0.21 parses an entry without the key (pinned by a
test), and 0.21 reads a materialised `static-publish` as an ordinary record. The old `overview-sync.log` is left in place (it is
no longer written).

### Left for 1.0

- Removal of the `/api/gitlab-*` aliases (after the dev-pipeline skill uses `/api/vcs-*`), the `profile` record,
  `design_work_roots` / `profile_repos`, the `implicit` key of `/api/modules`.

## [0.21.0] — 09.11.2026

Stage 4d-4b: the originals of the LIGA space are gone from the runtime, and the implicit provider leaves. A **fifth migration step,
`liga-4d4b`**, copies the last originals of the root of the LIGA `tasks.json` into the explicit records and then removes from that
root every original whose value provably lives in a record. After that the runtime reads **no original**: not the root of
`tasks.json`, not the environment, not `pipeline-feedback` — including a root key that a person edits by hand after the migration
(it simply has no effect). `Implicit` is removed: a role of LIGA without an explicit enabled record is off. For a person nothing
changes in the usual case (a migrated LIGA): the same comments, dashboard, statuses, git sync and publishing. The differences are
listed below. Deleting the originals **outside** `tasks.json` (environment variables, the `pipeline-feedback` files) is not the job
of Deai: they are shared with the separate LIGA tool; Deai only stops reading them.
Design: `docs/superpowers/specs/2026-11-07-liga-originals-gone-design.md`; plan: `docs/superpowers/plans/2026-11-07-liga-originals-gone.md`.
The behaviour of 0.20.0 is pinned by the snapshot `tests/fixtures/liga-migration/before-4d4b.json`.

### Added

- **A fifth migration step `liga-4d4b`** in `app/liga_migrate.py` (`ALL_STEPS = (A, B, C, D, E)`, the new field `Step.originals`). It
  has its own mark (`migrations.liga-4d4b`: `copied`, `removed`, `kept`, `notes` — key names only, never values), its own dated
  backup and its own restore. **What it copies:** `gitlab_ssh_key` / `gitlab_host_ip` into the settings `ssh_key` / `host_ip` of the
  `git-sync` record, and `preview_password` into the secret `password` of the `vercel-publish` record (only into an existing record).
  **What it removes** from the root: `supabase_url`, `supabase_key`, `jira_base`, `jira_email`, `jira_token`, `gitlab_ssh_key`,
  `gitlab_host_ip`, `preview_password` — each only when its effective value is proven in the holder (the `partial:supabase` rule keeps
  the Supabase pair unless all three records hold it). `design_work_root(s)`, `profile_repos`, `registry`, `current` and `tasks` are
  never touched. The order is copy, verify by reading, then delete under the write lock with `tasks.json.bak` next to the file and an
  `fsync` before the deletion. A marker guard (`marker-kept:<key>`) keeps the registry from being rebuilt as a space without
  integrations. Environment variables and `pipeline-feedback` are not touched.
- **New statuses and notes.** `abort-originals` (the root was not written; the copies lie there, nothing was deleted — the next
  start repeats), `abort-secrets` (the secrets of the module cannot be written, or the secrets file is not writable; `space.json` is not changed, the
  next start repeats), `abort-verify` (a copy does not read back; nothing deleted), `abort-write` (the space folder is read-only);
  restore of the step has `refuse-tasks-unreadable` (the live `tasks.json` is unreadable **or missing** — recreate the file, `{}` is
  enough). Notes: `differs:<key>`, `no-record:<module>`, `partial:supabase`, `unfit:<key>`, `marker-kept:<key>`,
  `replaced:preview_password`. A root `preview_password` of `0`, `0.0` or a boolean is `unfit`.
- **Unmigrated LIGA: all six roles are off, and the start and `status` name them.** When a step is skipped or aborted (`skip-held`,
  `skip-path-in-git`, `skip-tasks-unreadable`, `skip-space-json-unreadable`, `abort-*`…) the roles `publish`, `comments`, `vcs`,
  `dashboard`, `tracker` and `notify` are simply off. `liga_migrate.roles_state()` gives one line per role (the module, the reason
  code, the command to fix it); the start prints them and `bin/migrate_liga.py status` has a section «Ролі ЛІГИ». A LIGA with
  `integrations` off had no roles in 0.20 either and says so.
- **`bin/migrate_liga.py unhold <mark>`** removes a `{held: true}` mark (it removes nothing else); the old way was a hand edit of
  `space.json`. `status` names it for a held step, and `restore` prints the keys it **kept live** (`kept_live` of the root and
  `kept_live_secrets`; key names only).
- **The isolation law lives in `app/isolation.py`** (it replaces `app/implicit.py`): `route(role)` for the layer-off seam, the fake
  seams `DC_TEAM_FAKE` / `DC_TRACKER_FAKE` / `DC_TEAMS_FAKE` for `shared_state` records, and `real_home()` (the home by `pwd`, not by
  `$HOME`). An isolated run in the **real** Deai home never reaches the shared service: comments answer **`comments-isolated`**
  (HTTP 409), and the preview password is `1100`; in a temporary home of a test the secrets of the record work.
- **A capability error is named per role.** `capabilities.error` stays the first error code, and the new `capabilities.errors`
  (`{role: code}`) names every failed role. Only `error == "space-json-unreadable"` means «the space file is unreadable» (the
  Connections screen hides the cards); a lost module of one role is shown on the line «Now» of that role and the other cards stay.
- **Guards:** `NoOriginalsRead` (AST: no runtime reader of an original except the migration, `LEGACY_MARKERS` and the log path),
  `NoImplicit`, `ProviderCallersPinTheSpace`, a parity test `AfterMigrationParity4d4b` (five stands, the exact table of differences,
  the exact count of stopped network attempts) and the mutation table of the plan.

### Changed

- **The preview password is: the task, then the secret `password` of `vercel-publish`, then `1100`.** The root `preview_password` is
  never read. An unreadable `secrets.json` **fails closed**: publishing answers 409 «секрети простору не читаються», setting a
  password through `/api/preview-password` is refused (a non-empty per-task password needs no secrets file and is still set), the
  daily rotation script skips the task, the interface shows the message in the bar and refuses to copy a link (no empty `#k=` link).
- **Owner decision 09.11.2026: a root `preview_password` that differs from the secret of the record replaces the secret.** People keep
  the password they used; the old secret goes to the backup of the step, the summary names `replaced:preview_password`, and `restore`
  puts the old secret back (a secret that a person changed after the step is not overwritten: `kept_live_secrets`). Every other
  `differs:*` keeps the root and the record untouched.
- **The git key comes from the `git-sync` record** (`ssh_key`, `host_ip`); the root `gitlab_*` keys are not read any more, the
  shared registry (`bin/registry.py`) takes the key from the record too and ignores a disabled record. Without a key the default
  `~/.ssh/gitlab_ed25519` stays.
- **An enabled built-in record whose module cannot be loaded is `module-error` for every role** (it was a silent «none» or a
  «not loaded»); publishing with an enabled but unloadable `vercel-publish` answers **502 `module-error`** (it was 409
  `no-publish-module`). A broken module catalog is `vcs-error` instead of a raw exception.
- **`capabilities` of a space whose `space.json` is unreadable has `None` for every role** (it had `'legacy'` for `publish` and
  `vcs`), so for such a LIGA the publish and sync buttons are hidden and the Connections screen shows the error.
- **After a migration a publish whose root pair was removed still carries the comment layer:** the comments follow the record (a
  disabled or removed `supabase-comments` record gives a preview with no layer, as before).
- **The texts «not configured» of comments, dashboard, notify and tracker name the «Підключення» screen** instead of `tasks.json` or
  the environment. `bin/overview_push.py` reads no environment: with no dashboard record it says «нема постачальника командного
  дашборда»; the service key is entered as the secret `key` of `supabase-dashboard`.
- **`vercel-publish` 1.3.0:** the label of the setting `compat` now says that the preview password is the task's first, then the
  secret of the module (it used to say «from `tasks.json`»).
- **Signatures:** `serve.vcs_target`, `vcs_task`, `gitlab_cfg` and `preview_password(task, space)` have no `cfg` argument;
  `serve.supabase_config`, `serve.jira_config` and `install_config.{supabase,jira,service_key}_*` are removed (the copies live in
  `liga_migrate`).

### Removed

- **`Implicit`** (`app/implicit.py`, the `'legacy'` provider of a role) and the reading of the root of `tasks.json`, of
  `SUPABASE_*`, `JIRA_*` and of `~/.claude/pipeline-feedback/` by the runtime and by `bin/overview_push.py`.

### Upgrading

- **Five steps, five backups.** A user who comes from 0.16 gets `<stamp>-liga-4d3a`, `-4d3b`, `-4d3c`, `-4d4a`, `-4d4b`; from 0.20 only
  the last one. Roll them back in reverse order (the newest first).
- **⛔ Before a downgrade to 0.20 run `python3 bin/migrate_liga.py restore <stamp-E> --hold`** (the stamp of the `liga-4d4b`
  backup). It puts back `space.json` and the LIGA secrets and **merges the deleted keys back** into the live `tasks.json` (a key a
  person wrote there after the step is kept; the file is never rewritten as a whole). Without it 0.20 works without the preview
  password (the gate falls to `1100`), without the git key of the registry and without the Supabase and Jira fallbacks.
  `tasks.json.bak` is a manual rollback (the bytes before the last deleting run); copying it back erases the tasks created after
  the step. Further, if needed, `restore` of `-4d4a`, `-4d3c`, `-4d3b`, `-4d3a` (LIFO).
- On a machine where the step did not run (an unmigrated LIGA) there is nothing to roll back; 0.20 brings the implicit provider back.
- Rotation: the keys of LIGA live in `secrets.json`; rotate them on the Connections screen.

### Known limits

- **The copies of the credentials are in the Deai home** (`secrets.json` and `backups/` side by side) **and in `tasks.json.bak`**
  next to the LIGA `tasks.json` (the bytes before the last deleting run, in plaintext; the file is created with mode 0600). After
  the step the root of `tasks.json` no longer holds them; keep your own copy of the home if you need one, and do not share the
  folder that holds `tasks.json.bak`.
- **`tasks.json.bak` is the manual rollback**, not a copy of the original: a second deleting run overwrites it.
- **The root `preview_password` of an ordinary space no longer works** (only the task or the secret of `vercel-publish`).
  If step E did not complete (`skip-path-in-git`, `skip-held`, `skip-tasks-unreadable`, `abort-*`, or the note
  `no-record:vercel-publish`) a root `preview_password` stays on disk unread and a closed preview would fall to the shared `1100`;
  so the start prints one line (the key name only) and `bin/migrate_liga.py status` repeats it until the key is consumed: run
  `bin/migrate_liga.py run` (after `unhold` for a held step) or set the same value as the secret `password` of `vercel-publish`.
  When the record already holds a DIFFERENT password (e.g. after `restore` or a manual change) the line says so instead: the record
  wins; remove the root key, or run the migration to let the root win.
- **`restore` of step E puts the root keys back, but 0.21 does not read them:** the runtime keeps using `space.json` and
  `secrets.json`; the restored keys matter only for a downgrade to 0.20.
- **`isolation.real_home()` recognises only `<home>/.deai`:** a custom `DEAI_HOME` that points at a real location is not protected
  by the isolation law.
- **`skip-path-in-git` is permanent** while the space folder is inside a git work tree: the roles do not come back until the
  folder moves out of it.
- **The law of isolation (Д6) guards the real-home location, not the content:** an isolated run whose Deai home is a copy of the
  real one still reaches the live service.
- A partial migration is final, and the Supabase pair is all or nothing (`partial:supabase`).

## [0.20.0] — 07.11.2026

Stage 4d-4a: the tracks of LIGA become explicit for good, and the implicit track adapter leaves the runtime. A **fourth migration
step, `liga-4d4a`**, writes the tracks of the adapter into the LIGA `space.json` (when the adapter still applies) and gives the old
task records that have a `profile` but no `track` a `track` equal to it. After that the runtime has no adapter: `tracks.of_task`
reads only `track`, the API does not return `profile`, and `profile` is read on three boundaries only (`task-new`, the shared
registry, `_liga_flow`). For a person nothing changes in the usual case: the same labels, `?ds=`, repositories and folders of new
tasks. The differences are listed below.
Stage 4d-4 is split into three releases (the tracks, 4d-4a, 0.20.0; the last copies and the implicit provider, 4d-4b, 0.21.0; the
`integrations` flag and the API value `'legacy'`, 4d-4c, 0.22.0); 1.0 comes after 0.22.0. Deleting the **originals outside
`tasks.json`** (environment variables, the `pipeline-feedback` files) is not the job of Deai: they are shared with the separate
LIGA tool. Deai stops reading them in 4d-4b; removing them is a decision of the person when that tool goes.
Design: `docs/superpowers/specs/2026-11-07-liga-tracks-final-design.md`; plan: `docs/superpowers/plans/2026-11-07-liga-tracks-final.md`.
The behaviour of 0.19.0 is pinned by the snapshot `tests/fixtures/liga-migration/before-4d4a.json`.

### Added

- **A fourth migration step `liga-4d4a`** in `app/liga_migrate.py` (`ALL_STEPS = (A, B, C, D)`). The first step without roles and
  without the parity gate (`ungated`). It has its own mark, its own dated backup and its own restore. On the first start of 0.20
  the server runs the steps in order; a user who jumps from 0.16 gets **four steps at one start and four backups**.
- **What `liga-4d4a` writes**:
  - **the tracks** — exactly when the adapter applies now (`tracks` is absent, or empty/unusable after `tracks.normalize`; the
    single predicate `tracks.adapter_applies(raw, path)`): the ids of the adapter in its order, `label`, `root`, `repo`, `ds = id`,
    `default_track: "united"`, with no parity gate. A non-empty `tracks` of the person is never touched (`tracks-present`);
  - **the records** — every task of the LIGA `tasks.json` whose `track` is not a non-empty string and whose `profile` is one gets
    `track = profile` (the value as is: LIGA always kept a free string). `profile` stays in the record. The file is written under
    the write lock, with `tasks.json.bak` next to it; a failed write is `abort-records` and `space.json` is not changed;
  - the mark `migrations.liga-4d4a` (`at`, `roles: []`, `tracks`, `records`, `notes`, `backup`).
- **Notes of the mark** (codes only, no paths or values; ids of tracks are allowed), printed in one line at the start and in `status`
  (`напрямки: записано; записи: N; нотатки: …`):
  - `root-dropped:<id>` — `normalize` dropped the root of the track (a system or hidden folder, an overlap with another space): a
    new task of that track goes to the folder of the LIGA space;
  - `root-rebased:<id>` — a relative root of the adapter was rebased onto the folder of the space (the adapter's own behaviour,
    now visible);
  - `unknown-values` — some task has a non-empty track that is not in the list (only non-empty values count; the gate of 4d-3a
    still counts empty ones);
  - `default-root-differs` — the root of `united` differs from the shared root of the adapter;
  - `non-id-keys` — a key of `design_work_roots` / `profile_repos` is not an `ID_RE` id: its own root/repo no longer applies to NEW tasks.
- **Codes:** `abort-tracks` (the computed ids or the default differ from the adapter, and always for more than 20 ids — see Known
  limits) and `abort-records` (the write of the records failed) in `ABORT_CODES`; `skip-nothing` now also requires that there are
  no records to fix. `Step.ungated` is the new field of the step.
- **A guard `NoTracksAdapter`** (AST, `tests/test_no_adapter.py`): `app/**/*.py` (except `liga_migrate.py`) and `bin/*.py` do not
  mention `legacy_tracks`, `legacy_root`, `legacy_repos`, `_LEGACY_LABELS`, `profile_repos`, and do not read `profile` from a
  record. The adapter lives on as private `_legacy_*` names inside `liga_migrate` (the migration still reads the old root).
- **A line at the start** for a LIGA that was not migrated (`held`, a folder in git, an unreadable file): «напрямки ЛІГИ не
  мігровані — нові задачі лягають у теку простору».
- **`serve.default_task_root(cfg)`** — `design_work_root` of the config, else `~/deai-work`; `track_root(space, track_id)` lost its
  `cfg` argument and returns: the root of the found track, the root of the default track, the folder of the space, or `None` (an
  implicit space without a path).

### Status codes

- **New codes:** `abort-tracks`, `abort-records` (`ABORT_CODES`); the notes above (not statuses).
- `skip-nothing` of 4d-4a: no tracks to write and no record without `track`; the mark is not written.
- `skip-held`, `skip-busy`, `skip-integrations-off`, `skip-path-in-git`, `skip-no-path`, `skip-tasks-unreadable` apply as in 0.19.
  `skip-busy`, `skip-nothing` and the other quiet statuses do not print the «tracks not migrated» hint.

### Unchanged public contract

- The tests `tests/legacy-golden.test.mjs` and `GoldenPinTest` are green without a re-shoot; the snapshots of 4d-3a … 4d-3c still
  pass (their stands run the fourth step or pin `STEPS` to the first three). The snapshot of 0.19.0 for this stage is
  `before-4d4a.json`, compared by `AfterMigrationParity4d4a` on four stands (parity, notes, explicit tracks, an ordinary space)
  with an exact table of expected differences.
- Retired with their subject, with a correspondence table in the commit messages: the 0.14.0 classes `LegacyTracks`,
  `ServerLegacyParity`, `LegacyParity`, `BinParity`. The adapter-specific ones moved to `tests/test_liga_adapter.py` and aim at
  `liga_migrate._legacy_*`.
- `profile` stays in the records of `tasks.json` on disk and is still written into new LIGA records (old colleagues and the external
  dev-pipeline read it). Nothing is removed from `tasks.json` except by the person.

### Upgrading

- **Four steps, four backups.** A user who comes from 0.16 gets `<stamp>-liga-4d3a`, `-4d3b`, `-4d3c`, `-4d4a`; from 0.17 the last
  three; from 0.18 the last two; from 0.19 only the fourth. Roll them back in reverse order (the newest first).
- **⛔ Before a downgrade to 0.19 run `python3 bin/migrate_liga.py restore <stamp-d> --hold`.** The restore returns `space.json`
  (the tracks written by the step disappear; the mark of the step goes) and **does not return `tasks.json`**: it is the live file of the
  person (new tasks, statuses), and putting an old copy back would erase them. The records keep `track = profile`; that is safe for
  0.19, whose `of_task` reads `track` first and then `profile` (they are equal). `tasks.json.bak` next to the file is **manual**: copy
  it back yourself only if you want the records as they were.
- **Downgrade to 0.18 (steps c and d applied):** `restore <stamp-d> --hold`, `restore <stamp-c> --hold`. **To 0.17:** also
  `restore <stamp-b> --hold`; **to 0.16:** also `restore <stamp-a> --hold`. An earlier step alone is refused
  (`refuse-later-applied`) while a later one is applied.
- Nothing to rotate: the step copies no secret.
- The first start of 0.20 prints the notes of the step; read the line and check the tracks on the Connections screen or in
  `space.json` if it names `root-dropped`, `root-rebased`, `default-root-differs` or `non-id-keys`.

### Deliberate differences from 0.19.0

(everything else is checked against the snapshot, on a migrated and a non-migrated stand; the differences are pinned literally in
`AfterMigrationParity4d4a`)

1. **After the migration the tracks of LIGA are explicit** in `space.json`: `capabilities` and the screens read them like in any
   space. For a LIGA that is not migrated (the step skipped or aborted) there are **no tracks**: the label of a task is its raw
   value, the folder of a new task is the folder of the space, and the start says so.
2. **Records of a task with only `profile` in an ordinary (non-LIGA) space lose the label and `?ds=`.** Such a space never wrote
   `track`, so after 0.20 a record with only `profile` has no track. (For LIGA the step copies `profile` into `track`, so nothing is lost.)
3. **`task-new` is strict about `track` in every space**, LIGA too: `track` not of the shape of an id (`'United'`, any uppercase or
   odd character) → 400 **`bad-track`** (malformed); a well-formed id that is not in the list → **`unknown-track`**. A `track` that is not a
   string → `bad-track` as before. A layer-off run (`DC_TASKS_FILE` without `DEAI_HOME`) has no tracks, so any `track` there is
   `unknown-track`.
4. **`profile` of `task-new` is a lenient boundary input.** It is used only when it is a track id of the space; otherwise it is ignored,
   and the task goes to the default track. So `profile: 'United'` or `'zzz'` gives a task in the default track `united` with the
   repository mapping of `united` (the `gitlab` key), and `profile`/`track` of the record equal `united` (0.19 stored the raw
   profile and had no `gitlab` key). A conflict of `track` with a used `profile` is `bad-track`.
5. **Unknown or missing track → the root of the default track** for a new task (`task-new`) and for the folder of a task pulled
   from the registry (`bin/registry.py`), instead of the shared root of the adapter. For known tracks nothing changes.
6. **`/api/task` and `/api/tasks` do not return `profile`.** No client reads it; `track` stays.
7. **`bin/roots.py` never moves a task whose track is missing or unknown, or whose track has no root of its own.** They are listed
   with the reason «напрямок невідомий — не чіпаю» / «корінь напрямку не задано — не чіпаю». The «own root» flag of a track now
   means that the explicit track has a `root`. Before, such tasks were pulled into the shared root or the folder of the space.
8. **Registry pull: an entry WITHOUT its own `track` was written by an old machine, so its `profile` is authoritative:** the local
   `track` is replaced with it (a hand-edited local track is overwritten until the first 0.20 push). An entry with a `track` keeps
   it. The first `push` from 0.20 writes `track` into the registry entries.
9. **`_liga_flow` without a LIGA space in the registry** answers `no-space` instead of `no-integrations-space` for a sign that comes
   from `profile` alone, because the source of the repositories is now the explicit tracks of that space.
10. **The notes of the mark are visible effects on NEW tasks only** (the old folders stay where they are): `root-dropped` (a new task
    goes to the folder of the space), `non-id-keys` (the root/repo of such a key no longer applies), `default-root-differs` (an
    unknown track of the registry goes to the root of `united`).
11. **`restore` of the fourth step returns `space.json` only** (see Upgrading).

### Known limits

- **`abort-tracks` for more than 20 track ids is permanent** (`MAX_TRACKS = 20`): the person must clean `profile_repos` /
  `design_work_roots` of the old file; LIGA stays without tracks in `space.json`, new tasks go to the LIGA space folder (`track_root`).
- **A small TOCTOU between the re-stat and the atomic write of the records** (`_commit_records`): a concurrent external edit of
  `tasks.json` in that window is overwritten (the `.bak` has the pre-step bytes).
- **`tasks.json.bak` is a manual restore** (see Upgrading).
- **`profile` stays in the records of `tasks.json`.** The external dev-pipeline reads `profile` straight from the records and posts
  `profile` to `task-new`; this is covered by the boundary rules, but it is a risk of that tool, not of this repo.
- The first `push` of 0.20 adds `track` to the registry entries of the machine (no `status` drift: only keys present in the entry are compared).
- `serve._liga_like` has no callers after this stage (pinned by `LigaLikePin`); it goes in 4d-4c.
- **Backlog:** the live tests need a git identity in `HOME` (`overview-comments` #14/#20 fail with a bare temporary `HOME`); this is not a regression.
- A partial migration is final; the missing `flock` on Windows and a CLI `run` racing with UI edits: as before.

## [0.19.0] — 06.11.2026

Stage 4d-3c: the last of the three steps that turn the LIGA space into an ordinary one. The role `publish` of LIGA becomes an
explicit built-in module (`vercel-publish`) through a **third migration step, `liga-4d3c`**, and the one thing an explicit record
could not express before (the publishing path of LIGA: the projects `pv-…` and the scope kept in `tasks.json`, the preview password
of the task / of the root / `1100`, the build mark `legacy`, the side effects and the answer keys) becomes the setting `compat` of
`vercel-publish`. For a person nothing changes: the same projects and URLs (no new ones), the same scope, the same password, the
same `#k=` in «Copy link», the same side effects, answer keys and texts. 4d-4 (0.20.0) follows.
Design: `docs/superpowers/specs/2026-11-06-liga-migration-c-design.md`; plan: `docs/superpowers/plans/2026-11-06-liga-migration-c.md`.
The behaviour of 0.18.0 is pinned by the snapshot `tests/fixtures/liga-migration/before-4d3c.json`.

### Added

- **A third migration step `liga-4d3c`** in `app/liga_migrate.py` (`ALL_STEPS = (STEP_A, STEP_B, STEP_C)`). It has its own mark, its
  own dated backup and its own restore, like the first two. On the first start of 0.19 the server runs `liga-4d3a`, `liga-4d3b`,
  `liga-4d3c` in order; a user who jumps from 0.16 gets **three steps at one start and three backups**.
- **What `liga-4d3c` writes** (the LIGA `space.json` is merged: foreign keys and modules stay):
  - `publish` -> `vercel-publish` with `enabled: true`, `shared_state: true` and `settings {auth: "cli", team: "", compat:
    "design-canvas"}`. **No secrets**: there is no token (the sign-in is the `vercel login` of the machine) and the preview password
    stays in `tasks.json` (4d-4). `auth: "cli"` only makes the «Check» of the card (`vercel whoami`) truthful; the LIGA path does
    not read it;
  - the mark `migrations.liga-4d3c` (`at`, `roles`, `backup`; no `tracks`);
  - the check `abort-provider`: on the `space.json` calculated in memory the core must resolve `publish` with exactly the
    `vercel-publish` module, otherwise nothing is written.
- **Skip codes of the role:** `module-present` (`vercel-publish` is already in `space.json`) and **`publisher-present`** (a person
  has already enabled another explicit publish module in the space: the step does not override it, and does not leave an eternal
  `abort-provider` at every start). `publisher-present` is quiet at the start line and visible in `status` and `dry-run`; a
  broken module of the space's own (`ModuleError`) counts as not present, so the later check gives `abort-provider`; any other error
  of the presence check is `abort-internal`.
- **The setting `compat` of `vercel-publish`** (`select`: empty or `design-canvas`, default empty; module version 1.2.0, `compat`
  is the last setting). `design-canvas` keeps the path of LIGA: the projects and the scope from `tasks.json`, the password of the
  task / of the root / `1100`, the legacy build mark, the old side effects and answer keys. The label warns that in this mode `auth`,
  `team` and `password` of the record are **not read**, and that changing the value on a live space switches the publishing to the
  module path (new projects, other URLs).
- **One predicate for «the publishing path of LIGA»**, `deai_modules.publish_legacy_path(prov, space=None)`: the implicit provider,
  or a **built-in** `vercel-publish` (`origin == 'builtin'` and exactly this id) with `compat == "design-canvas"`. It is total (a
  failure is `False`). Every consumer reads it: `Handler._publish`, `Handler._preview_password`, and `deai_modules.publish_module`
  (which returns `None` for the LIGA path, so `task_preview_gate` and `task_publish_share` need no change). An AST guard forbids
  `isinstance(..., Implicit)` in those four functions and keeps `publish_module(` to its two callers in `serve.py`.
- **`compat.publish` in `/api/spaces`** (next to `compat.comments` and `compat.vcs`; the key is present only for an explicit built-in
  record with a non-empty `compat`). `isLegacyPublish` in `spaces-model.js` reads `capabilities.publish === 'legacy' ||
  compat.publish === 'design-canvas'`; the preview password row of the bar, the «Copy link» with `#k=`, the publish reaction and
  the Connections screen read that one function.
- **`capabilities.publish` of a migrated LIGA is `'vercel-publish'`**; `'legacy'` stays for a LIGA that is not migrated, a switched-off
  record, a broken built-in module and a failed resolution, until 4d-4.
- **`last.json` and the CLI for three steps.** `restore <stamp-a>` while steps b and c are applied is refused
  (`refuse-later-applied`) and the text names the **last** applied step, the one to roll back first (0.18 named the first later one).
  The start line and `bin/migrate_liga.py run` print `бекап: <stamp>` for every step done, then ONE `відкат:` hint (for the latest
  step done only) and a line `раніші кроки (…) — лише після відкату пізніших, у зворотному порядку`; the hint of every step at once
  would have told the person to run a refused restore first.

### Status codes

- **New skip code:** `publisher-present` (benign, a role code of `liga-4d3c`).
- **Codes of the role of 4d-3c** (in `skipped` of `last.json`): `module-present`, `publisher-present`.
- `skip-nothing` of 4d-3c: the role is already explicit; the mark is not written. `skip-held` and `skip-integrations-off` apply as in
  0.18.

### Unchanged public contract

- The tests `tests/legacy-golden.test.mjs` and `GoldenPinTest` are green without a re-shoot, and so are the snapshot tests of
  4d-3a and 4d-3b. Four stands of `tests/test_liga_migrate_b.py` pin `STEPS` to `ALL_STEPS[:2]` (they see the first two steps only),
  and the shape test checks `ALL_STEPS[2] is STEP_C`; `tests/test_vercel_publish.py` pins the new module version and the new
  setting. These are the only changes of existing tests.
- The branch of LIGA in `Handler._publish` is **not changed**: it is switched by the predicate. The projects, the scope, the
  `legacy_state`, the gate, the build mark, the comments of the preview (`module_publish=False`) and every side effect and key
  are the code of 0.18.
- The implicit path stays as a fallback until 4d-4: switch the explicit record off and the built-in mode is back.
- The migration does not run in an isolated run, except with the seam `DC_MIGRATE_LIGA=1` and a temporary `DEAI_HOME`; the real
  `~/.deai` is always refused.

### Upgrading

- **Three steps, three backups.** A user who comes from 0.16 gets `<stamp>-liga-4d3a`, `<stamp>-liga-4d3b` and
  `<stamp>-liga-4d3c`; from 0.17 the last two; from 0.18 only the third. Roll them back in reverse order (the newest first).
- **⛔ Before a downgrade to 0.18 run `python3 bin/migrate_liga.py restore <stamp-c> --hold`.** 0.18 ignores the setting `compat`
  of `vercel-publish`, so the migrated record would be published by the **module path**: a new project and a new URL for every
  published task, and the preview **without the gate** (the record has no `password` secret). Without the restore the people who
  already have your old URLs lose them.
- **⛔ Downgrade to 0.17 (steps b and c applied):** `restore <stamp-c> --hold`, then `restore <stamp-b> --hold`.
  **Downgrade to 0.16 (all three applied):** `restore <stamp-c> --hold`, `restore <stamp-b> --hold`, `restore <stamp-a> --hold`.
  An earlier step alone is refused (`refuse-later-applied`) while a later one is applied.
- Nothing to rotate: the step copies no secret. The preview password, `vercel_project` and `vercel_scope` stay in `tasks.json`.

### Deliberate differences from 0.18.0

(everything else is checked against the snapshot, on the migrated space too: two stands, «nothing migrated» and «after 4d-3a and
4d-3b»; the only diffs of the JS predicates are `is_vercel_publish` and `disable_consequences_publish`)

1. **After the migration `publish` of LIGA is an explicit module**: its id is in `capabilities`, there is one `vercel-publish` card
   on the Connections screen, and `/api/spaces` has the key `compat.publish`.
2. **`auth`, `team` and `password` on the card are decorative in the mode `design-canvas`** (the path of LIGA does not read them);
   the label of `compat` says so. The preview password is changed from the bar, as before.
3. **`restore <stamp-a>` with several later steps applied names the LAST applied one** (0.18: the first later one).
4. **The start line and the CLI `run` print two lines for a single step** (`бекап: <stamp>` and `відкат: …`) where 0.18 printed one
   combined line; with several steps the rollback hint names the latest done step only, plus the line about the earlier ones
   (see Added).
5. **The disable dialog of the newly enabled `vercel-publish` card has one more line**, «The role "publish" is taken back by the
   built-in LIGA integration» (`cnDisableLegacy`): switching the record off returns the implicit provider, and that is true. It is
   the only visible text that changes.
6. **`publisher-present`**: a LIGA space whose person already enabled another publish module keeps it; the step is skipped
   and without an eternal `abort-provider`.
7. **The note of 0.18.0 «lifted in 4d-3c» was wrong**: the refusal of `publish_comments(module_publish=True)` for comments records
   with `shared_state` **stays**. LIGA publishes through the LIGA branch (`module_publish=False`, the comments work), and the refusal
   guards the real builds of a MODULE (another publish module, or `vercel-publish` without `compat`) from carrying the Supabase key
   of LIGA into a preview. The two notes of `[0.18.0]` are corrected (see below), the docstring of `publish_comments` too.
8. **Enabling another publish module by hand in a migrated LIGA answers `role-taken`** unless «replace» is chosen: the role is now
   held by the explicit `vercel-publish` record, while in 0.18 the implicit provider did not occupy it. «Replace» works; the
   replaced record keeps its settings, as for any replaced module.

### Known limits

- **A downgrade to 0.18 after 4d-3c is unsafe without `restore <stamp-c> --hold`** (see Upgrading): the module path, new URLs, no
  gate.
- **`vercel-publish` enabled by hand in a LIGA space WITHOUT `compat` is the module path**: new projects, new URLs, and the password
  is the module secret `password` (empty means no gate). The card does not warn about it; the warning is in the label of `compat`.
- **The cold «Check» of the card is untested without a network.** For a record with `shared_state` in an isolated run the answer is
  `isolated` (no `npx`), covered by a unit test; the real first «Check» (`npx vercel whoami`, `check_timeout_s: 130`) can be slow
  while `npx` fetches the package. **A note for the owner's first live run.**
- **The carry-over of the scope is proven by the non-isolated unit test only** (`RealPublishNonIsolated`: the first publish mints
  `pv-…` and writes the scope, the second reuses the same project, URL and scope). The live test is isolated and has no network,
  so it proves the same `link` / `deploy` argv and texts, not the saved URL.
- The preview password, `vercel_project` and `vercel_scope` stay in `tasks.json` (4d-4); there is no copy in `space.json`.
- A partial migration is final (as in 0.17 and 0.18); `skip-path-in-git` and `skip-no-path`, the missing `flock` on Windows, and a
  CLI `run` racing with UI edits: as before.
- The publishing of LIGA has no seam and no isolation branch (and never had): an isolated run under the LIGA branch calls the real
  `npx`; only the tests' substitutes isolate it.

## [0.18.0] — 06.11.2026

Stage 4d-3b: the second of the three steps that turn the LIGA space into an ordinary one. The roles `comments` and `vcs` of LIGA
become explicit built-in modules (`supabase-comments`, `git-sync`) through a **second migration step, `liga-4d3b`**, and the
two things that an explicit record could not express before (the old channel scheme of the comments, the flat mirrors of git
sync with their texts) become the setting `compat` of those two modules. For a person nothing changes: the same channels
(`comment_project`, `dc/<task>`), the same pin history, the same Teams silence and counters, the same mirror folders (no
re-clone, no orphaned commits), the same «design-canvas» / «GitLab» texts, the same «New task» form without a Repository field.
4d-3c (0.19.0) `publish` and 4d-4 (0.20.0) follow.
Design: `docs/superpowers/specs/2026-11-06-liga-migration-b-design.md`; plan: `docs/superpowers/plans/2026-11-06-liga-migration-b.md`.
The behaviour of 0.17.0 is pinned by the snapshot `tests/fixtures/liga-migration/before-4d3b.json`.

### Added

- **A second migration step `liga-4d3b`** in `app/liga_migrate.py`, which is now an ordered list of steps (`STEPS`). Every step is
  independent and has its own mark, its own dated backup and its own restore. On the first start of 0.18 the server runs
  `liga-4d3a`, then `liga-4d3b`; a user who jumps from 0.16 gets **both steps at one start and two backups**. The plan of the
  second step is calculated AFTER the first one is written (it reads the current `space.json`).
- **What `liga-4d3b` writes** (the LIGA `space.json` is merged: foreign keys and modules stay; a role that already has a module is
  `module-present`):
  - `comments` -> `supabase-comments` with `shared_state: true`, `settings {url, shots_bucket: "overview-thumbs", compat:
    "comment-layer"}` and the Supabase key as a copy in `secrets.json` (the address and the key come from
    `install_config.supabase_from`, by the same rules as the implicit path). Skip codes of the role: `no-supabase`, `bad-url`
    (`user:pass@` in the address), `module-present`;
  - `vcs` -> `git-sync` with `shared_state: true`, `settings {branch: "main", path: "mockup/{task}", autosync: true, compat:
    "design-canvas"}`; no secrets; `ssh_key` and `host_ip` are NOT copied (see Upgrading); the setting `repo` is not written (the
    repository comes from the target of a task);
  - the mark `migrations.liga-4d3b` (`at`, `roles`, `backup`; no `tracks`);
  - the check `abort-provider`: on the `space.json` calculated in memory the core must resolve every migrated role with exactly
    this module, otherwise nothing is written.
  A partial migration is final, as in 0.17: without a Supabase config `vcs` migrates, the mark is written and `comments` stays
  implicit; the start line, `status` and `last.json` (`skipped`) name the code.
- **Restore is LIFO.** The name of a backup says whose step it is: `bin/migrate_liga.py restore <stamp-b>` puts back `space.json`
  and the LIGA part of the secrets as they were after 4d-3a (4d-3a stays applied). `restore <stamp-a>` while 4d-3b is applied
  (a mark without `held`) is refused with **`refuse-later-applied`** (exit code 1, nothing is written; the text names the backup
  to roll back first). `--hold` writes `{"held": true}` into the mark of that step only. **A held earlier step holds the later
  ones** (the later step answers `skip-held` with its own reason): otherwise `restore <b>` followed by `restore <a> --hold` would
  bring step b back to life at the next start.
- **Order and stopping rules at one start:** `abort-*` and `skip-busy` of a step stop the later steps at this start (the state is
  doubtful, or another process may be in the middle of a step); the other `skip-*` codes (`skip-nothing`, `skip-done`, ...) do not
  block the later steps.
- **`skip-integrations-off`** (new, benign): a LIGA registry record with `integrations` off is not migrated at all, because in 0.17
  its roles are off (there is no implicit provider) and explicit records would switch them on. It is checked in the plan of EVERY
  step, so it also applies to step 4d-3a (nothing is written, not even a mark).
- **`last.json`** keeps its 4d-3a shape at the top level (the report of the last action, now with `step`) and adds
  `steps: {mark: report}`, so a report of 4d-3b does not erase the one of 4d-3a. The CLI `status`, `dry-run` and `run` print every
  step; `restore <stamp>` finds the step by the name of the backup. The line `напрямки` of the `run` output is printed only for a
  step that has tracks (4d-3a); the output of a single step is byte-for-byte what 0.17 printed.
- **The setting `compat` of `supabase-comments`** (`select`: empty or `comment-layer`, default empty; module version 1.2.0).
  `comment-layer` keeps the old channel scheme (`comment_project` of the task, or `dc/<task>`, plus `/internal`); empty means
  `deai/<space>/<task>`. The label warns that changing the value on a live space cuts off the existing pin history.
- **The setting `compat` of `git-sync`** (`select`: empty or `design-canvas`, default empty; module version 1.1.0).
  `design-canvas` means exactly what the implicit provider did: flat mirrors in the old mirrors folder (`DC_MIRRORS_DIR` or
  `<ROOT>/.mirrors`, laid over the module ctx by the core as `cache_dir` and `mirror_flat`), the texts «design-canvas: sync», the
  README and the label «GitLab» / «repository», the fork note. The label warns that a change makes the mirror folders and the
  texts different.
- **One function for the comment channel**, `deai_modules.comment_channel_of(space, prov, task, tid, internal=False)`: the
  implicit provider or a **built-in** `supabase-comments` with `compat == "comment-layer"` gives the comment-layer scheme, every
  other provider gives `channel_for` (`deai/<space>/<task>`). All six places go through it: `comments_route` (and with it
  `/commented`, `/api/comment-config`, `publish_comments`), `ProjectComments.channel`, `GET /api/task`, `GET` and `POST
  /api/teams-mute`, and the counters of the dashboard (`dashboard.sync` takes an optional callback `channel_of`, built by
  `bin/overview_push.cmd_sync`). `serve.comment_channel` and `dashboard.comment_project_key` are thin wrappers; an AST guard
  forbids a direct call outside them. `deai_modules.compat_of(space, module_id)` is total (an empty string on any failure). Where
  the provider cannot be resolved (`ModuleError`) `api/task`, the silence and the counters fall back to the comment-layer scheme,
  as in 0.17.
- **One predicate for the legacy texts**, `serve.vcs_legacy_texts(prov, space)` (the implicit provider, or a built-in `git-sync`
  with `compat == "design-canvas"`), computed once in `vcs_provider` and read by every consumer through the third element of the
  tuple; a guard forbids `isinstance(..., Implicit)` for decisions about texts or channels anywhere else.
- **`compat` map in `/api/spaces`**: a neighbouring key `compat` of the space object (`{role: value}`, only for roles whose
  explicit built-in module has a non-empty `compat`; absent otherwise). `isLegacyVcs` in `spaces-model.js` reads
  `capabilities.vcs === 'legacy' || compat.vcs === 'design-canvas'`, so the «New task» form of a migrated LIGA still has no
  Repository field and the labels stay «GitLab».
- **`ProjectComments` for the agent** keeps the LIGA look after the migration: the label stays «Supabase», and `bin/inbox.py`
  keeps the minimum prefix length (the rule that drops it applies to modules that are not on the comment-layer scheme).
- **The isolation law covers `comments` and `vcs`** records marked `shared_state`: in an isolated run (`DC_TASKS_FILE`,
  `DC_NO_OVERVIEW`) a **built-in** record builds its ctx like the implicit path (`_comments_legacy_ctx()` /
  `_vcs_legacy_ctx()`: the key comes from the root of the tasks file, never from `secrets.json` of a real `DEAI_HOME`); the
  condition lives only in the two branches of `comments_route` and `vcs_provider` (`_builtin_shared`). Outside isolation the
  record's own `module_ctx` is used. A module of your own with a hand-set `shared_state` stays an ordinary module there.
- **`publish_comments(module_publish=True)` refuses** (returns `False`) a comments record with `shared_state`, as it already
  did for the implicit provider: a preview built by a publish module must not carry the Supabase key of LIGA. It also refuses a
  module of your own with a hand-set flag (the safe side). Stays (see 4d-3c).
- **`LEGACY_SHOTS_BUCKET`** moved to `install_config.py` (the migration needs it and does not import `serve`); `serve` keeps an
  alias, and a test compares the values. `serve._vcs_legacy_ctx()['settings']` and the record of the migration share
  `branch`, `path` and `autosync`, and a test compares them.

### Improved

- **«Check» of a module with `shared_state` no longer reads secrets and no longer touches the network in an isolated run**
  (`POST /api/module-check` and the tail of a module write answer `{ok: false, error: "isolated"}`; `last_check` is not
  overwritten). It applies to all five roles (`comments`, `vcs`, `dashboard`, `tracker`, `notify`) and closes a gap of 0.17, where
  an isolated run over a real `DEAI_HOME` could read the real `secrets.json` through «Check». New label `cnErrIsolated`.
- **Every built-in module field has a compat label** in the Connections screen (`compat_view` is built for built-in modules only,
  and a test covers the labels of all built-in modules). New field labels: `cnFieldSbDashCompat` (`supabase-dashboard` `compat`),
  `cnFieldSbTeamsCompat` (`supabase-teams` `compat`) and `cnFieldVercelAuth` (`vercel-publish` `auth`), next to
  `cnFieldSbCompat` and `cnFieldGitCompat`.
- **Start order (final review).** The server binds the port first (`serve.serve_main`), then runs the migration, then serves: the
  migration is after the port opens and before the first request. A busy port stops the start BEFORE anything is migrated (before,
  an older server holding the port would have kept serving a space it does not understand). Connections wait in the backlog during
  the migration. This replaces «before the port opens» of 0.17.0.
- **The start line of a finished step names the backup** (`бекап: <stamp>; відкат: bin/migrate_liga.py restore <stamp> --hold`;
  the name only, no path, no values).
- `compat` of a role in `/api/spaces` is returned only when it is the allowed value of that module (`design-canvas` for
  `git-sync`, `comment-layer` for `supabase-comments`); the palette state of the canvas carries `compat` too.

### Status codes

- **New skip code:** `skip-integrations-off` (benign; also for 4d-3a). `skip-held` of a later step may now come from an earlier
  held step (the reason says so).
- **New refusal of `restore`:** `refuse-later-applied`.
- **Codes of the roles of 4d-3b** (in `skipped` of `last.json`): `no-supabase`, `bad-url`, `module-present`.
- `skip-nothing` of 4d-3b: both roles are already explicit; the mark is not written.

### Unchanged public contract

- `publish` of the LIGA space stays implicit (`'legacy'` in `capabilities`) until 4d-3c. The tests `tests/legacy-golden.test.mjs`
  and `GoldenPinTest` are green without a re-shoot, and so are the 4d-3a snapshot tests (their stand sees one step: one line in `_Stand.setUp` of `tests/test_liga_migrate.py`
  is the only change of the 4d-3a tests; the other changed existing tests only pin the new module versions and the new
  `compat` setting).
- The implicit path stays as a fallback until 4d-4: switch the explicit record off and the built-in mode is back.
- The migration does not run in an isolated run, except with the seam `DC_MIGRATE_LIGA=1` and a temporary `DEAI_HOME`; the real
  `~/.deai` is always refused.

### Upgrading

- **Two steps, two backups.** A user who comes from 0.16 gets `<stamp>-liga-4d3a` and `<stamp>-liga-4d3b`; from 0.17 only the
  second. Roll them back in reverse order (the newest first).
- **⛔ Before a downgrade to 0.17 run `python3 bin/migrate_liga.py restore <stamp-b> --hold`.** 0.17 ignores the setting
  `compat`: without the restore the comment channels switch to `deai/<space>/<task>` (the history and the silence «disappear»)
  and the mirrors are cloned again under `<DEAI_HOME>/cache` (orphaned unpushed commits of the old mirrors).
- **⛔ Downgrade to 0.16 (two steps applied):** `restore <stamp-b> --hold`, then `restore <stamp-a> --hold`. `restore <stamp-a>`
  alone is refused (`refuse-later-applied`) while step b is applied; the `liga-4d3a` stamp is not enough.
- **Rotation.** The Supabase key for the comments is now a copy in `secrets.json`: rotating `supabase_key` in the old `tasks.json`
  (or in the environment) no longer reaches the comments; rotate it on the Connections screen (the same as for the dashboard and
  Teams since 0.17).
- `gitlab_ssh_key` and `gitlab_host_ip` in the root of `tasks.json` keep working (`_vcs_ssh` reads them for any provider); they
  move in 4d-4.

### Deliberate differences from 0.17.0

(everything else is checked against the snapshot, on the migrated space too)

1. **After the migration `comments` and `vcs` of LIGA are explicit modules**: their ids are in `capabilities` (`publish` stays
   `'legacy'`), there is one card per role on the Connections screen, and the settings can be edited there. `/api/spaces` has the new
   key `compat`.
2. **A Supabase key changed in the environment or the root of `tasks.json` no longer affects the comments of LIGA** (the copy
   lives in `secrets.json`).
3. **A space with an explicit comments module without `compat` now has its real channel `deai/<space>/<task>` in `GET /api/task`,
   in the Teams silence and in the dashboard counters** (before, these three always used `dc/<task>`, so the silence and the
   counters looked past the pins). Plan amendment 5: `/api/teams-mute` and the counters have no `integrations` gate, so this also
   applies to spaces without integrations.
4. **The ctx of the migrated roles** is built by `module_ctx` (`space.path` and the other extras; the same values plus `compat`).
5. **`publish_comments` refuses a comments record with `shared_state`** in a preview built by a publish module (also one of your
   own with a hand-set flag).
6. **Teams and dashboard counters, the silence, `api/task`, `inbox` and the labels follow `compat`, not the kind of the provider**
   (the lesson of 4d-3a: «LIGA» is a registry record, not a provider type).

### Known limits

- **A partial migration is final** (as in 0.17): without a Supabase config at the first start `comments` stays implicit and is not
  retried; add the `supabase-comments` card on the Connections screen.
- **A downgrade to 0.17 after 4d-3b is unsafe without `restore`** (see Upgrading).
- **LIGA has no in-UI entry point to the «New task» form** (pre-existing); the Repository field stays hidden for LIGA even when a
  `repo` is set on the `git-sync` card (the setting works for tasks without a target, but the form does not offer it).
- `skip-path-in-git` and `skip-no-path`, the missing `flock` on Windows, and a CLI `run` racing with UI edits: as in 0.17.
- `publish` is still implicit: a preview built by a publish module carries no comments of LIGA (stays, see 4d-3c).

## [0.17.0] — 06.11.2026

Stage 4d-3a: the first of three steps that turn the LIGA space into an ordinary one. A **migration** moves the config the LIGA
space used to take from the root of the old `tasks.json` and from the environment into its own `space.json` and `secrets.json`:
the roles `tracker`, `dashboard` and `notify` become explicit built-in modules (`jira-tracker`, `supabase-dashboard`,
`supabase-teams`), and its tracks become explicit `tracks`. The owner split 4d-3 into three releases (05.11.2026), because the
other three roles do things that the built-in modules cannot express through `space.json` yet: 4d-3a (this one) the mechanism,
the tracks and `tracker`/`dashboard`/`notify`; 4d-3b (0.18.0) `comments` and `vcs`; 4d-3c (0.19.0) `publish`; 4d-4 becomes 0.20.0.
Design: `docs/superpowers/specs/2026-11-05-liga-migration-a-design.md`; plan: `docs/superpowers/plans/2026-11-06-liga-migration-a.md`.
The behaviour of 0.16.0 is pinned by the snapshot `tests/fixtures/liga-migration/before-4d3a.json`.

### Added

- **`app/liga_migrate.py`**, the LIGA migration. It runs automatically **once**, at the start of the canvas server, before the
  port opens (`serve.main` calls `liga_migrate.startup()`), and on demand through the CLI. A failure never stops the start: the
  server starts as 0.16 would, and the reason goes to stderr and to `<DEAI_HOME>/migrations/last.json` (never a secret).
  `plan()` is a pure calculation (nothing is written; the secrets live only in the plan, `report()` prints key names, never
  values); `run()` writes.
- **A dated backup** `<DEAI_HOME>/backups/<stamp>-liga-4d3a/` (folder 0700, files 0600): copies of the old `tasks.json`, of the
  LIGA `space.json` (if there was one), of `secrets.json` and of `spaces.json`, and a `manifest.json` with the source paths and
  the sha256 of every file. The backup is verified (the source is hashed before and after the copy, and again at the end), and a
  half-written folder is removed. A failed backup is `abort-backup` and nothing else is written.
- **The mark `migrations.liga-4d3a`** in the LIGA `space.json` (`at`, `roles`, `tracks`, `backup`). A mark means the migration
  does not run again, even if a person later turns a module off on the Connections screen: that is their decision.
- **Copied secrets, the originals kept.** The Jira token and the Supabase key are copied into `secrets.json` under the id of the
  LIGA space; the root of the old `tasks.json`, the environment and `~/.claude/pipeline-feedback/` are not touched, so the tools in
  `bin/` keep reading them and a downgrade needs no manual steps beyond the one below. The write order is: backup → secrets →
  ONE atomic write of `space.json` (existing keys such as `name`, `color` and foreign ones are kept). A failure between the last
  two leaves secrets that nobody reads, and the next start repeats the migration.
- **A cross-process lock** `<DEAI_HOME>/migrations/.lock` (`flock`, no waiting) around `run` and `restore`; a second process gets
  `skip-busy`. A `flock` error other than «busy» (for example `ENOLCK`) is a visible `abort-lock`, not a silent skip. `plan()` is
  calculated inside the lock; the first look (to decide that there is nothing to do) is outside it and creates neither `migrations/`
  nor `.lock`.
- **Restore.** `bin/migrate_liga.py restore <stamp> [--hold]` puts back the LIGA `space.json` and **only the LIGA entry** of
  `secrets.json` (foreign entries added after the migration stay) and verifies the manifest sha256 first. Before it writes, it
  copies the current `space.json` and the LIGA part of the secrets to `backups/<stamp>-pre-restore/`, so edits made after the
  migration are not lost. After a restore the mark is gone and the next start migrates again; `--hold` writes
  `migrations.liga-4d3a: {"held": true}` so it does not. An unknown or forged stamp is refused (`refuse-stamp`,
  `refuse-tampered`, `refuse-no-liga`) and nothing is written.
- **The CLI `bin/migrate_liga.py status|dry-run|run|restore <stamp> [--hold]`** (exit 0 or 1; it prints codes, role names and key
  names, never secret values or addresses).
- **The setting `compat`** (`select`: empty or `comment-layer`, default empty) of `supabase-dashboard` and `supabase-teams`. It
  replaces the flag `ctx['legacy']`: `comment-layer` means that the base is the old comment-layer schema (a public key is
  allowed, and `teams_notify_health` does not exist). The implicit path (`dashboard.legacy_ctx`, `notify.legacy_ctx`) puts it into
  `settings`, and the migration writes it into `space.json`.
- **`shared_state`** on the module records of `space.json` (a boolean the migration writes; a non-boolean is ignored) and
  **`deai_modules.shared_state(space, module_id)`**. A record marked `shared_state: true` is the shared state of the LIGA space
  even though it is explicit, so it falls under the isolation law: in an isolated run (`DC_TASKS_FILE` or `DC_NO_OVERVIEW`) it
  behaves as the implicit provider (a test seam, then a refusal, then the real call). The Connections screen does not show or
  change the flag.
- **The `install_config` refactor**: `supabase_from(cfg)` and `jira_from(cfg)` are the bodies of `supabase_config()` and
  `jira_config()`, moved out unchanged, so the migration takes the credentials by the same rules and in the same order as the
  implicit path, not by a copy of them.
- **`_provider_for(…, explicit_override=…)`**: the migration checks a calculated `space.json` in memory (every migrated role must
  be resolved by exactly its module, otherwise `abort-provider`) without writing anything.

### Status codes

Every code is in the report, in `last.json` and in the CLI output.

- **Skip** (nothing is written; `skip-*` never overwrite the journal): `skip-layer-off`, `skip-no-liga`, `skip-done`,
  `skip-held`, `skip-no-path`, `skip-path-in-git`, `skip-space-json-unreadable`, `skip-registry-unreadable`,
  `skip-tasks-unreadable`, `skip-nothing` (no role and no tracks to migrate: the mark is not written, the next start looks
  again), `skip-busy`.
- **Abort** (nothing is written, or the next run starts again): `abort-provider`, `abort-internal`, `abort-lock` (from the
  calculation or the lock); `abort-backup`, `abort-secrets`, `abort-changed` (the LIGA record of the registry changed between the
  calculation and the write), `abort-write` (the secrets are in, `space.json` is not: harmless) from `run`; `abort-restore`
  from `restore`.
- **Done:** `done` (migration), `restored` (restore). A restore may also answer `refuse-stamp`, `refuse-tampered` or
  `refuse-no-liga`; the server start answers `refuse-real-home` when the test seam `DC_MIGRATE_LIGA=1` meets the real `~/.deai`.
- **Why the tracks are not migrated** (`tracks_reason`; the roles migrate anyway): `tracks-present` (the space already has
  `tracks`, even an empty list), `tracks-parity` (the calculated tracks do not match the adapter) and `tracks-unknown-values`.
- `last.json` is written only for `done`, the `abort-*` codes and `restored`. The permanent `skip-path-in-git` goes into its own
  key `skip` of `last.json`, so a real report is not erased by it.

### Improved

- **«Check» of the LIGA modules on the Connections screen really checks.** In 0.16.0 it answered `bad-settings` for all three
  modules; after the migration it is the ordinary check of a module with settings.

### Unchanged public contract

- `publish`, `comments` and `vcs` of the LIGA space stay implicit (`'legacy'` in `capabilities`) until 4d-3b / 4d-3c. The tests
  `tests/legacy-golden.test.mjs` and `GoldenPinTest` of `tests/test_comments_role.py` are green without a re-shoot.
- The migration does not run in an isolated run (`DC_TASKS_FILE`, `DC_NO_OVERVIEW`), except with the test seam
  `DC_MIGRATE_LIGA=1` together with a temporary `DEAI_HOME`; the real `~/.deai` is always refused. With the layer off nothing runs.

### Upgrading

After the migration the Jira token and the Supabase key of LIGA live in `secrets.json`: **rotate them on the Connections
screen**. The old sources (the environment, `pipeline-feedback`, the root of `tasks.json`) stay only as a fallback for the tools
in `bin/` (for example `bin/overview_push.py`), so a rotation made there does not reach the canvas.

### Deliberate differences from 0.16.0

(everything else is checked against the snapshot, on the migrated space too)

1. **After the migration `tracker`, `dashboard` and `notify` of LIGA are explicit modules**: their ids are in `capabilities`,
   there is one card per role on the Connections screen, and the settings can be edited there.
2. **A Jira token or a Supabase key changed in the environment, in `pipeline-feedback` or in the root of `tasks.json` no longer
   affects LIGA.** The copy lives in `secrets.json`; change it on the Connections screen.
3. **Built-in modules ignore `ctx['legacy']`**: `supabase-dashboard` and `supabase-teams` read `settings.compat`. A module of your
   own can no longer pretend to be LIGA with the flag; the flag stays in the ctx of the implicit path, for foreign modules only.
4. **The ctx of the migrated roles** is built by `module_ctx` like for any module, so it now has `space.path` and the other
   extras; the values of the settings and the secrets are the same, and `compat` replaces `legacy`.
5. **Explicit tracks are a snapshot.** Once the tracks are migrated, later edits of `design_work_root`, `design_work_roots` or
   `profile_repos` in the old `tasks.json` no longer affect LIGA. Edit `tracks` in the `space.json` of the LIGA space instead.
6. **«The LIGA space» is the registry record (`legacy: true`), not the implicit provider.** The dashboard sync of a migrated LIGA
   (an explicit `supabase-dashboard` with `shared_state`) keeps its GitLab-registry step, `overview_push.py discover` and the
   log in `pipeline-feedback/overview-sync.log`, exactly as before the migration.

### Known limits

- **A partial migration is final.** If the first start of 0.17 comes from the Dock or the PWA (no shell environment) while the Jira
  credentials live only in the environment, the tracker is not migrated (`no-jira`), the mark is written, and the tracker is never
  retried: it stays implicit and works as in 0.16. Put the credentials in `tasks.json` or in `pipeline-feedback` before the first
  start, or add the `jira-tracker` card on the Connections screen. The start line in stderr, `bin/migrate_liga.py status` and
  `last.json` (`skipped`) name every role that was not migrated with its reason code, never a value.
- **The tracks are often NOT migrated.** They are skipped (`tracks-unknown-values`) when the LIGA `united` track has its own root
  different from the shared `design_work_root`, when a task carries an unknown track value (anything that is not a migrated id,
  including `None`, an empty string or another letter case), or when `design_work_roots` / `profile_repos` has a key outside the id
  pattern; and on a parity miss (`tracks-parity`). The reason: the adapter sends an unknown value into the shared root, while
  explicit `tracks` send it into the root of the default track, so a new task could land in another folder. In those cases the
  tracks adapter stays exactly as in 0.16.0 and the roles migrate anyway. This is likely common for real LIGA setups; the tracks
  then move in 4d-4.
- **A downgrade to 0.16 after the migration breaks the dashboard and the notifications** (`public-key`: 0.16 does not know
  `compat`). Run `bin/migrate_liga.py restore <stamp> --hold` first.
- `skip-path-in-git` and `skip-no-path`: a LIGA folder inside a git work tree, or one that does not exist, is not migrated, and
  LIGA stays as in 0.16.0.
- `bin/migrate_liga.py run` while a canvas of the same home is serving can race with edits made on the screen; the lock guards the
  migration against another migration or restore, not against the UI. The canvas itself migrates only at the start.
- There is no `flock` on Windows (`fcntl` is missing): one copy of the canvas per home is the limit there.
- The migrated secrets are not synchronized with their originals.
- `SUPABASE_SERVICE_KEY` (environment only, used by `bin/overview_push.py`) is not migrated: the most privileged secret has no
  place in a space.
- The originals, the `integrations` flag, `gitlab_*` and `profile` stay until 4d-4.

## [0.16.0] — 05.11.2026

Stage 4d-2: the core stops comparing the provider of a role with the string `'legacy'`. `deai_modules.provider()` now returns a
`Module`, an **`Implicit`** object (the in-house setup of the LIGA space, or a space whose layer is switched off) or `None`; the
layer-off case has one seam, and the isolation of shared state one law. The public contract does not change. This is the second of
the four sub-releases of stage 4d (owner decision 04.11.2026): 4d-1 tracks (0.15.0), 4d-2 this one, 4d-3 explicit LIGA modules with
an automatic, backed-up migration of its config, 4d-4 the `integrations` flag and the old aliases go. Design:
`docs/superpowers/specs/2026-11-05-implicit-provider-seam-design.md`; plan:
`docs/superpowers/plans/2026-11-05-implicit-provider-seam.md`. The behaviour of 0.15.0 is pinned by the snapshot
`tests/fixtures/implicit/before-4d2.json`.

### Added

- **`app/implicit.py`**, a pure core (no network, no import of `serve`): the class `Implicit` (immutable; `role`, `module_id`,
  `shared`, `fake_env`), the role table `IMPLICIT_ROLES` (`publish`, `comments`, `vcs`, `dashboard`, `tracker`, `notify`) with
  `for_role`, the law `isolated()` (`DC_TASKS_FILE` or `DC_NO_OVERVIEW`) and `route(prov)`, which answers `('fake', path)`,
  `('isolated', None)` or `('live', None)` in the same order for every role (a test seam first, then the refusal of an isolated
  run, then the real call). What each role answers in each case stays with the role, as in 0.15.0.
- **`spaces.effective_space()`**, the layer-off seam: with the layer off, or with no space fixed for the request, it returns a
  copy of `IMPLICIT` without reading the registry; otherwise `active_space()`. `deai_modules.provider()` goes through it.
- **`deai_modules.api_value(p)` and `API_IMPLICIT`**: the only place where an `Implicit` turns into the public string `'legacy'`
  (a `Module` gives its id, `None` gives `None`; anything else is a `TypeError`).
- **`deai_modules.publish_module(space)`**: the module that publishes in a space, or `None`; total, and with the same cache as
  `capabilities` (it keeps the 0.15.0 condition «layer on and request space fixed»).
- **New optional keys `jira_email` and `jira_token`** in the root of a tasks file: the only place an isolated run reads Jira
  credentials from (meant for test fixtures; see below).
- **A guard in the tests**: an AST check (`NoLegacyLiteral` in `tests/test_implicit.py`) keeps comparisons with `'legacy'` out of
  `app/*.py` and `bin/*.py`; its list of allowed places is empty. Next to it, `RolesParity`, `PublishModule` and `LigaLikePin`.

### Changed

- **One path for every role.** The branches of `serve.py`, `bin/overview_push.py` and `bin/state.py` ask `isinstance(prov, Implicit)`
  instead of `== 'legacy'`, and `implicit.route` replaces the per-role decisions about test seams and refusals.
- **One isolation law for `dashboard`, `tracker` and `notify`**: the same function and the same order. The refusals keep their
  text from 0.15.0. `publish`, `comments` and `vcs` still have no refusal of their own (their tests stand on substituted
  functions and local fakes).
- **An isolated run reads the install config only from the root of the tasks file** (`DC_TASKS_FILE`): `supabase_config()` takes
  `supabase_url`/`supabase_key` from there and `jira_config()` takes `jira_base`, `jira_email` and `jira_token` from there; see
  *Deliberate differences*.
- **`_overview_sync`** uses `implicit.isolated()` for the in-house path rather than `route`, so a test seam such as `DC_TEAM_FAKE`
  together with `DC_TASKS_FILE` still does not sync.
- **The cache owner `who`** of the team rows (`dashboard`) and of the tracker statuses takes `api_value(prov)`.
- **Tests**: the Supabase pair of the old fixtures moved into the root of the fixture tasks file (`sbconf.write_root`), and the
  tests that deliberately run outside isolation clear `DC_TASKS_FILE` and `DC_NO_OVERVIEW` both.

### Removed

- The constants `LEGACY_ROLES`, `LEGACY_ON_ERROR_ROLES` and `STRICT_LEGACY_ROLES` of `app/deai_modules.py`, renamed to
  `IMPLICIT_ROLES`, `IMPLICIT_ON_ERROR_ROLES` and `STRICT_IMPLICIT_ROLES` (same members, same meaning). **No aliases**: scripts
  that imported the old names must move.

### Unchanged public contract

- `capabilities.<role>` stays `'legacy'` in `GET /api/spaces` and `GET /api/task`; the `build` key of `manifest.json` stays
  `legacy|module`; there are no JS changes. The snapshot and the goldens (`tests/legacy-golden.test.mjs`, the comments golden pin)
  are green without a re-shoot.

### Deliberate differences from 0.15.0

(everything else is checked against the snapshot)

1. **An isolated run no longer sees the machine's credentials.** In a run with `DC_TASKS_FILE` or `DC_NO_OVERVIEW`,
   `supabase_config()` and `jira_config()` no longer read the environment (`SUPABASE_*`, `JIRA_*`) or
   `~/.claude/pipeline-feedback/jira-*`. This includes someone who sets `DC_NO_OVERVIEW` on purpose: their environment and
   pipeline-feedback credentials are ignored, and they need the pair in the root of the tasks file. Outside isolation nothing
   changed.
   The fallback service key follows the same rule: `service_key_config()` (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY`, used by
   `bin/overview_push.py`) returns `(None, None)` in an isolated run, because the root of the tasks file has no service-key
   form. Outside isolation it is unchanged.
2. **Internal API.** Providers are `Implicit` objects, not the string `'legacy'` (`provider()`, `comments_provider()`,
   `team_resolve()` and the like). The constants are renamed: `LEGACY_ROLES` → `IMPLICIT_ROLES`, `LEGACY_ON_ERROR_ROLES` →
   `IMPLICIT_ON_ERROR_ROLES`, `STRICT_LEGACY_ROLES` → `STRICT_IMPLICIT_ROLES`. No aliases.
3. **`ProjectComments.kind`** (the internal state of the comments channel) changed from `'legacy'` to `'implicit'`; `bin/state.py`
   reads it. It is not an API value.

### Known limits

- `'legacy'` stays in the public API, in the build manifest, in the id of the implicit space and in the registry field until
  4d-3 / 4d-4.
- `bin/overview_push.py` run by hand and the tools in `ops/` do not know about `isolated()` (not a test path).
- `bin/registry.py` computes `TASKS_PATH` at import time.
- `tests/live/dashboard-role.test.mjs` reads the real `~/.claude/pipeline-feedback/overview-sync.log`, read-only (a backlog item).

## [0.15.0] — 05.11.2026

Stage 4d-1: the **profile** of a task (`united` / `liga360` / `seo`), a notion of one company welded into the core, is replaced by
**tracks of a space**: a general mechanism that any space can use. A space describes its tracks in its `space.json` (an id, a label,
a folder for the tasks, a default repository of mockups, a design system of the inspector), and a task carries `track`. The LIGA
space stays ONE space with three tracks, supplied by an implicit adapter that reads what already lies in the root of its
`tasks.json` — so for its designers nothing changes: the same folders, repositories, labels and `?ds=` in the markup, byte for byte.
The old key `profile` stays a synonym until 4d-4. This is the first of four sub-releases of stage 4d (owner decision 04.11.2026):
4d-1 profile → tracks (this one), 4d-2 the layer-off seam and the isolation of shared state without the literal `'legacy'`,
4d-3 explicit LIGA modules with an automatic, backed-up migration of its config, 4d-4 the `integrations` flag and the old aliases
go. Design: `docs/superpowers/specs/2026-11-04-space-tracks-design.md`; plan: `docs/superpowers/plans/2026-11-04-space-tracks.md`.
The behaviour of 0.14.0 is pinned by the snapshot `tests/fixtures/tracks/before-4d1.json`.

### Added

- **`app/tracks.py`**, a pure core (no network, no import of `serve`): `ID_RE` (`[a-z0-9-]{1,32}`), `MAX_TRACKS` (20), `ROOT_MAX`
  (1024), `normalize(raw, space_path, roots=True)` (the `tracks` of a `space.json` → `[{id, label, root, repo, ds}]`; it never
  raises: a bad entry is dropped, a bad field counts as absent), `default_id`, `of_task` (the stored string `track`, otherwise
  `profile`), `find`, `label_tag` and the LIGA adapter `legacy_tracks(cfg)` with `legacy_root`, `legacy_repos` and
  `_LEGACY_LABELS`. The rules of a tag label, the repository rule and the id pattern now live here, and `serve` imports them.
- **Tracks in `space.json`** of an ordinary space: `tracks` (a list) and `default_track`. A track has `id`, `label`, `root` (the
  folder of its tasks: absolute, `~/…` or relative to the space), `repo` (the default repository of a new task) and `ds` (the name
  of a static design system of the inspector). The rules and an example are in the README, «Space tracks».
- **In `serve`:** `space_tracks(sp)` → `(tracks, default_id)`; `_TrackView` (the tracks of one space, built once per request and
  space, and lazily, so a loop over tasks does not read the registry or the file system per task); `track_root`, `track_repo`,
  `task_ds`.
- **The API.** `track` in the records of new tasks and in the rows of `GET /api/tasks` and `GET /api/task`; `tracks: [{id, label}]`
  and `default_track` in every entry of `GET /api/spaces` (never the `root` or the `repo` of a track: folders and addresses do not
  travel to the browser); `POST /api/task-new` takes `track` (`profile` is its synonym). The new error codes `bad-track` and
  `unknown-track` (both 400).
- **In `bin/`:** `track` is in the `SHARED` keys of the task registry, and `roots.py` and `state.py` go through `tracks`. The head
  of the `state.py` page now reads «Напрямок:» (it read «Профіль:»; nothing parses it).

### Changed

- **The folder of a new task is the folder of its track.** In an ordinary space with tracks it is the `root` of the track (or the
  path of the space when the track has none); a track that is not found falls back to the default track. The route reads
  `default_track` where it used to say `profile or 'united'`.
- **The default repository of a track becomes the `vcs` of the task**, but only when the space has a provider of the role `vcs`
  and the body of the request carries no `vcs` of its own (an explicit one wins). Without a provider the repository of a track is
  silently not applied, and an explicit `vcs` with no provider is still 409, as before. In LIGA the repository still goes into
  `gitlab: {repo, path: mockup/<id>}`.
- **The label of a task** without `tags` comes from the label of its track (LIGA: `United` / `LIGA360` / `SEO`, an unknown track as
  it is). `task_tags(task, sp)` takes the space explicitly; `?all=1` labels every row by its **own** space.
- **The design system of the inspector** (`?ds=`) is the `ds` of the track of the task (LIGA: the id itself).
- **LIGA records write both keys.** A new LIGA task gets `track` **and** `profile` with the same value, so teammates on 0.14.0 keep
  reading `profile` from the shared registry. An ordinary space writes `track` only when there is one, and the old `profile: null`
  as before.
- **Robustness of LIGA** (places where 0.14.0 crashed; see *Deliberate differences*).

### Removed

- From the core of `serve.py`: `_LEGACY_PROFILE_TAGS` (it moved into the adapter as `tracks._LEGACY_LABELS`), `_PROFILE_KEY` (now
  `tracks.ID_RE`), `_REPO_OK`, `_TAG_BAD` / `_clean_tag` / `_read_tag` / `TAG_MAX_LEN` (now in `tracks.py`), `FALLBACK_WORK_ROOT` and
  `work_root`. `serve.py` no longer contains the names `united`, `liga360` or `seo` at all, and a test enforces it.
- **Kept until 4d-4, as a thin wrapper:** `profile_repos()` (over `tracks.legacy_repos`); it is still used by `_liga_flow`,
  `track_repo` and the tests that patch it.

### Upgrading

- **LIGA: nothing to do.** Designers see no change; the folders, repositories, labels and design systems are the same.
- **Teams with mixed versions.** Records of LIGA tasks carry `track` and `profile` with the same value, so a teammate on 0.14.0
  reads the folder, the repository and the label as before. A 0.14.0 machine that round-trips a record drops `track`, but the
  `profile` of that record carries the same value, and 0.15.0 reads it.
- **Old clients that send `profile`** (the dev-pipeline skill) keep working everywhere. In an ordinary space a `profile` that is a
  known track is used as the track; any other `profile` value is ignored, exactly as in 0.14.0. Only the new key `track` is strict
  (`bad-track`, `unknown-track`).
- **An ordinary space:** to use tracks, describe them in its `space.json` (README, «Space tracks»). It is read on every request, so
  no restart is needed. Without `tracks` the space behaves as before.
- Scripts that imported `work_root`, `_LEGACY_PROFILE_TAGS` or `_PROFILE_KEY` from `app/serve.py` must move to `app/tracks.py`.

### Deliberate differences from 0.14.0

(everything else is checked against the snapshot)

1. **New fields.** Records get `track`; responses get `track` / `tracks` / `default_track`.
2. **New codes** `bad-track` and `unknown-track` (400). Only the new key `track` raises them, and `unknown-track` only in an
   ordinary space (LIGA accepts any string as a track, as it accepted any profile; a space with no tracks of its own refuses any
   named track).
3. **An ordinary space with tracks:** the folder of the task is the root of its track (it was the path of the space), and the
   repository of the track becomes the `vcs` of the task — only when a `vcs` provider exists and the body has no explicit `vcs`.
4. **LIGA robustness** — the places where 0.14.0 crashed now answer sensibly:
   - a `design_work_roots` that is not an object → the shared root (it was a 500, `AttributeError`);
   - an own root or a `design_work_root` that is not a string → the fallback chain (own → shared → `~/deai-work`) (it was a
     `TypeError`);
   - the page of a task whose profile is a number renders cleanly, with no `?ds=` (it was a dropped connection);
   - `bin/roots.py roots_in_use` no longer raises `TypeError` on a numeric profile mixed with strings, and `bin/roots.py plan`
     shows a numeric profile as `None`.
5. **`?ds=`.** A track that is found uses its own `ds`, so `ds: ''` gives no `?ds=` at all. A stored value that matches no track
   falls back to the raw value, as in 0.14.0 (a golden pins `?ds=tool` for a task of an ordinary space).
6. **`?all=1` labels every row by its own space** (an intermediate version of this release labelled by the space of the caller,
   which showed the label of a LIGA task as a raw id from an ordinary space; fixed during review).

### Known limits

- Tracks are edited only in `space.json`; there is no UI. Only the API (the pipeline skill) puts a task into a track.
- An invalid `root` of a track — a system folder, a hidden folder or `Library` in the home, the home itself, a folder inside the
  repository of the tool, a folder that equals, lies inside **or contains** another registered space (the overlap is checked in
  both directions), or a path longer than 1024 characters — silently falls back to the path of the space. No warning is shown.
- The roots of tracks are checked (`realpath`, plus one read of the registry) **only when a task is created** (its folder). Labels,
  the design system of the inspector, `/api/tasks`, `/api/task`, the overview and `/api/spaces` read the tracks without
  checking roots, so none of them waits for a slow or unmounted volume.
- A LIGA space that has its own **non-empty** `tracks` in `space.json` is a plain space with those tracks: the adapter semantics
  end (a task id outside the list no longer falls back to the shared root; the «any string is a track» acceptance stops),
  and `design_work_roots` and `profile_repos` of the old `tasks.json` are ignored. Only an empty list (or one that normalizes to
  empty) leaves the adapter in force. The migration of 4d-3 must write all of it.
- `profile` lives on in the records and in the API until 4d-4.
- The names United / LIGA360 / SEO and the default `united` live in the adapter of `tracks.py` until the migration of 4d-3.
- `_liga_flow` looks at `profile` only, not at `track` (the 409 `no-integrations-space` path); it is revisited in 4d-4.

### Tests

- The behaviour of 0.14.0 is pinned by `tests/fixtures/tracks/before-4d1.json`, generated by `tests/make_before_4d1.py` from
  `c8c3a8b`. The generator is frozen: it describes 0.14.0, its guard is fail-closed, and it must not be re-run on the new code.
- `tests/test_tracks.py` (about 160 tests: the snapshot, the core, differential tests of LIGA against the snapshot, the API); the
  live test is `tests/live/tracks.test.mjs` (`PORT_BASE` 23000). Every new guard is proven by a mutation.

## [0.14.0] — 04.11.2026

Stage 4c-3: the Teams notifications become a role, the last one of the in-house integrations. The switch «Notify Teams» in the
publish menu and the route `/api/teams-mute` no longer depend on the `integrations` flag and on the database of one company: they
belong to whoever provides the role **`notify`** in the space. The built-in module `supabase-teams` provides it for anyone with a
Supabase project, and it brings its own `schema.sql`, so an ordinary space now gets the **whole thing** — a card in a Teams
channel for every new comment, the mute per channel and a delivery log — and not only the switch. The LIGA space reaches its own
database through the same module as an implicit provider (as in 0.8.0–0.13.0 for the other roles) and keeps its own triggers. The
core decides how the state of the mute is read and checked (`app/notify.py`); the module only talks to the service. After this
release **no role name is reserved any more**. Design: `docs/superpowers/specs/2026-11-03-notify-role-design.md`; plan:
`docs/superpowers/plans/2026-11-03-notify-role.md`. The behaviour of 0.13.0 is pinned by the snapshot
`tests/fixtures/notify/before-4c3.json`.

### Added

- **The role `notify`** in the core: it is called now, `ROLES_RESERVED` is empty, and `capabilities.notify` carries the module id,
  `'legacy'` or `null`. The functions of a module: `mute_state(ctx)` → a list of `{project_id, muted_at, muted_by}` and
  `mute_set(ctx, channel, muted, by)` → a bool. The core normalizes the state (`notify.normalize_mutes`: `project_id` a string of
  1..200 characters, `muted_by` a string of at most 200 or `''`, `muted_at` a string of at most 40 or `None`, at most 1000 rows;
  an answer that is not a list is an error, never «nothing is silenced») and checks the arguments of `mute_set` **before** the
  call. A silenced channel covers its sub-channels (`dc/t1` silences `dc/t1/internal`, not `dc/t10`). The error codes
  `notify-unconfigured` (409) and `notify-error` (502); the core waits `NOTIFY_TIMEOUT` = 10 s. The contract is in
  `docs/modules/authoring.md`, «The `notify` role».
- **The module `supabase-teams` 1.0.0** (built-in). Settings: `url` (the project address: https only, a DNS name, no IP, no
  `localhost`, no path) and `key` (a secret, **not** `public`: the `service_role` key or the key of a role of your own). The
  schema `app/modules/supabase-teams/schema.sql` is run once by a person in the SQL editor, **after** the schema of
  `supabase-comments`; it is idempotent and adds `pg_net`, the tables `teams_delivery_log` and `teams_project_mute` (RLS on, closed to
  `anon` and `authenticated`), the card builder `comment_teams_card` (an Adaptive Card 1.4 made with `jsonb_build_*`; the only string
  concatenation is the cut of the comment text to 500 characters, `left(c.text, 500) || '…'`), the privileged sender `cl_send_teams` (a freshness guard of 2 minutes, the mute of a channel and
  of its sub-channels, the webhook address from **Vault** under `teams_webhook_url`, `pg_net`), the trigger `cl_notify_teams` on new
  comments, and the three functions the module calls: `teams_mute_state`, `teams_mute_set` and `teams_notify_health`. Those three are
  granted to `service_role` only. The module calls them over `POST /rest/v1/rpc/…` with an 8 s socket timeout; it follows no
  redirects, and no key or body of a request or answer ever gets into a text. See `app/modules/supabase-teams/README.md`.
- **The verdicts of `check`** on the Connections screen: `notify-no-schema` (the database has no notification functions: run
  `schema.sql`), `notify-no-webhook` (no `teams_webhook_url` secret in Vault: cards will not go) and `public-key` (a public key where
  a non-public one is needed). The detail of a healthy check reads «доставок за 6 год: N, невдалих: M» (deliveries in 6 h, failed).
- **The role on the Connections screen** (the card «Teams notifications», between «Issue tracker» and the tokens) and in the
  new-space wizard; the texts are in `app/i18n.js` (UK and EN). The role icon is «eye»: the icon set has no bell.
- **The client helper `hasNotify(space)`** (`app/spaces-model.js`): the Teams item of the publish menu and the polling of
  `/api/teams-mute` follow `capabilities.notify`.

### Changed

- **The Teams item and the route follow the role, not the flag.** A space with a provider of `notify` has the item and the route
  whatever its `integrations` flag says; a space without one has neither. For LIGA nothing changes.
- **LIGA goes through the module.** `notify.legacy_ctx` and `notify.legacy_module` build the call for the built-in `supabase-teams`
  from the config of the installation (`supabase_url` / `supabase_key`, the same pair as the comments and the dashboard). The
  requests of the mute (method, path, body, headers, 8 s timeout) are the same as in 0.13.0 and are pinned by the snapshot. For LIGA
  the module does **not** require a non-public key and does **not** call `teams_notify_health` (the LIGA database has no such
  function, and its key is the public key of the page).
- **The text of a failure comes from the module.** When the network or the service fails for LIGA, the error text is now the
  module's (for example «Supabase недоступний (…)»); the shape of the answer is unchanged: GET `{channel, error}`, POST 502. LIGA with
  no Supabase config raises `notify-unconfigured` with the same text «Supabase не налаштовано», and the route answers as in 0.13.0.
- **The answers of a module are checked.** `mute_set` must return a real JSON bool and `mute_state` must return a list; anything
  else is a `notify-error` (LIGA's `teams_mute_set` already `returns boolean`, so nothing changes for LIGA).
- **`notify_call` checks its arguments too:** it runs `notify.check_set_args`, so a channel longer than 200 characters now gets 400.
- **A broken own module of the role is reported with its reason**, not shown as «off». This follows the `dashboard` and `tracker`
  precedent.
- **`DC_TEAMS_FAKE`** (the test seam: a local JSON instead of the database) acts only for the `'legacy'` provider; a `muted_at` in it
  that is not a string becomes `None`.
- **`supabase-dashboard`:** a public key in `check` now gives the verdict `public-key` (it was `module-error`, which the screen
  labels «the module crashed during the check»). Nothing else in that module changed.

### Removed

- `serve.teams_rpc` and `serve.teams_mute_view`; their place is taken by `notify_resolve` / `notify_call` in `serve.py` and
  `notify.mute_view` in `app/notify.py`.
- The client helper `noOutward` (`app/app.js`); the replacement is `noNotify` / `hasNotify(space)`.

### Upgrading

- **LIGA: nothing to do.** It still needs `jira_base` in `tasks.json` from 0.13.0, if that is not done yet.
- **An ordinary space:** to get the cards and the switch, (1) run the schema of `supabase-comments`, then `schema.sql` of
  `supabase-teams`, in the SQL editor of the **same** project; (2) put the address of your Teams webhook into Vault:
  `select vault.create_secret('<webhook address>', 'teams_webhook_url');` (https only); (3) enable the module (Connections →
  «Teams notifications», or the wizard) with the project address and a **non-public** key (`service_role` or the key of a role of
  your own); (4) create the receiving side in Teams (a Power Automate flow or an incoming webhook that posts the card as it is).
  Without the module nothing changes. Read `app/modules/supabase-teams/README.md`.
- **Authors of their own modules:** a module that declares the role `notify` must now provide `mute_state` and `mute_set`, otherwise
  it is `bad-manifest` (the same rule applied to `tracker` in 0.13.0).
- Scripts that imported `teams_rpc` or `teams_mute_view` from `app/serve.py` must move to `notify_call` and `app/notify.py`.

### Deliberate differences from 0.13.0

(everything else is checked against the snapshot)

- **The code of a refusal without a provider is `notify-off`** (it was `integrations-off`): a space without a `notify` provider
  answers `/api/teams-mute` with 409 `{code: 'notify-off'}`. The Teams item of the dropdown follows the role, not the integrations
  flag.
- **Failures read differently** (see *Changed*): the error text of a LIGA failure comes from the module; a module answer of the
  wrong shape is a `notify-error`; a channel over 200 characters is 400.
- **The schema of the module is stricter than the LIGA one:** the mute RPCs are granted to `service_role` only (LIGA grants them to
  the key of the page, and its database does not change).
- **`cl_send_teams` de-duplicates by the delivery log:** a comment that already has a row there is never posted again, so a replayed
  insert (or a replayed call with the same id inside the 2 minutes) does not send a second card. The LIGA trigger does not do this.
- **Isolation:** with `DC_TASKS_FILE` or `DC_NO_OVERVIEW` the LIGA path never goes to the network (the answer is an `OSError`
  «ізольований конфіг…»); `DC_TEAMS_FAKE` is the seam of that path, and a space with a module does not see it.

### Known limits

- `normalize_mutes` keeps at most 1000 rows: a silenced channel past row 1000 shows as not silenced.
- `schema.sql` was checked **statically only** (there is no Postgres in CI or on the development machine). The first run on a real
  Supabase is a manual step of the owner.
- The card carries the id of the channel, not a project name, and its labels are Ukrainian; the receiving side (Power Automate or
  another) is set up by a person. `pg_net` and Vault must be available in the project.
- Delivery is fire-and-forget (no retries), as in LIGA; its health is visible only in `check` on the Connections screen.
- `cl_send_teams` is callable with the public key (`anon`), and its checks are not atomic: two parallel calls for the same comment
  can both pass the delivery-log dedupe before either inserts its log row, and send two cards. The 2-minute freshness guard trusts
  `comments.created_at`, which a public-key client can set. The effect is at most extra cards; no data or secret is exposed. This
  is inherent to the open public-key model.
- `cl_send_teams` logs only `sqlstate` on a failure (never `sqlerrm`, which could echo the signed webhook address from a `pg_net`
  error): a deliberate difference from the LIGA original.
- The text of the shared verdict `no-schema` («нема таблиці comments») is still shown for `supabase-dashboard`; changing it is out
  of scope of 4c-3 (the verdict of `supabase-teams` has its own code, `notify-no-schema`).
- The error texts of the server are Ukrainian also in the English interface (as for the other roles).
- The snapshot generator `tests/make_before_4c3.py` is frozen: it describes 0.13.0 and must not be re-run on the new code.

### Tests

- The behaviour of 0.13.0 is pinned by `tests/fixtures/notify/before-4c3.json`; the live test is
  `tests/live/notify-role.test.mjs` (a fake module, the item with and without a provider, a failure, the Connections screen,
  LIGA through `DC_TEAMS_FAKE`).

## [0.13.0] — 03.11.2026

Stage 4c-2: the task statuses of the issue tracker become a role. The badge with the status of a task («In progress», «Done»…)
no longer depends on the team dashboard and no longer on the Jira of one company hard-wired in `bin/overview_push.py`: it
belongs to whoever provides the role **`tracker`** in the space. The built-in module `jira-tracker` provides it for anyone with a
Jira Cloud site, and the LIGA space reaches its Jira through the same module as an implicit provider (as in 0.8.0–0.12.0 for the
other roles), with the address moved from the code into `tasks.json` (see *Upgrading*). The core decides which keys are asked
and how the answer is read (`app/tracker.py`); the module only talks to the tracker. Design:
`docs/superpowers/specs/2026-11-03-tracker-role-design.md`; plan: `docs/superpowers/plans/2026-11-03-tracker-role.md`. The
behaviour of 0.12.0 is pinned by the snapshot `tests/fixtures/tracker/before-4c2.json`.

### Added

- **The role `tracker`** in the core: it is called now (only `notify` is still reserved), and `capabilities.tracker` carries the
  module id, `'legacy'` or `null`. The function of a module: `statuses(ctx, keys)` → `{key: {"name", "cat"}}`; the core sends
  only keys of the form `KEY_RE` (`[A-Z][A-Z0-9_]{0,31}-[1-9][0-9]{0,9}`), at most 100 per call, and normalizes the answer
  (`name` ≤ 80 characters with no control characters, `cat` one of `new` / `indeterminate` / `done` or `None`). The new field
  `ctx["timeout_s"]` is the socket budget of the module (4 s on the Tasks screen, 15 s in the sync; the core waits 6 s and 30 s).
  The error codes `tracker-unconfigured` (409) and `tracker-error` (502). The contract is in `docs/modules/authoring.md`,
  «The `tracker` role».
- **The module `jira-tracker` 1.0.0** (built-in). Settings: `base` (`https://<site>.atlassian.net` or your own domain: https only,
  a DNS name, no IP, no `localhost`, no path), `email` and `token` (a secret, the Atlassian API token). `statuses` is
  `POST /rest/api/3/search/jql` (the same request as the 0.12.0 sync), `check` is `GET /rest/api/3/myself` and answers
  `tracker-auth` on HTTP 401/403 and `network` when Jira cannot be reached. No redirects are followed, and no token, e-mail or
  body of a request or answer ever gets into a text. See `app/modules/jira-tracker/README.md`.
- **Statuses on the «Tasks» screen without a dashboard.** `/api/tasks-overview` asks the tracker of the space for the keys of
  «Mine» (the first 100) and shows the badge on the cards; a space with a tracker and no team dashboard now has statuses too.
  The priority is the tracker, then the row of the dashboard, then «unknown» (no badge). The «Team» rows are unchanged (their
  statuses come from the dashboard).
- **The banner «Issue tracker unavailable: …»** over «Mine» when the tracker did not answer, with the note «data as of HH:MM» when
  earlier statuses are still shown. The cache is **per space** under its own lock (`TRACKER_TTL` 300 s, an error for 30 s;
  «Try again» skips it), and a failure never wipes the last statuses.
- **The role on the Connections screen** (the card «Issue tracker», between «Team dashboard» and the tokens) and in the new-space
  wizard; the texts are in `app/i18n.js` (UK and EN).

### Changed

- **LIGA goes through the module.** `tracker.legacy_ctx` and `tracker.legacy_module` build the call for the built-in
  `jira-tracker` from the config of the installation: `jira_base` in the legacy `tasks.json` (new) and the credentials as before
  (`JIRA_EMAIL` / `JIRA_TOKEN`, or the files `~/.claude/pipeline-feedback/jira-email|jira-token`). The request to Jira is the
  same as in 0.12.0. `install_config.jira_config()` reads the e-mail and the token independently (as 0.12.0 did): a bad value of
  the environment falls through to the file.
- **The sync takes the statuses from the provider of the role `tracker`** of the space, any space (0.12.0: LIGA only, through
  `jira_statuses`). A space with no provider, or LIGA with no config, skips the step.
- **A failure of the tracker in the sync goes into the log**, never silently: `⚠ overview: статуси трекера недоступні: <the text of
  the module error | the class name>`. The statuses already on the cards are not wiped (as before).
- **Keys outside `KEY_RE` do not go to the tracker** (0.12.0 put them into the query as they were); the module checks the keys
  once more because they end up in a JQL.
- **Connections:** the role has the icon `task`; turning it off outside LIGA has its own consequence text.

### Removed

- The Jira code of `bin/overview_push.py`: `_JIRA_BASE` (the address was a constant), `_jira_creds`, `jira_statuses`,
  `_ssl_context`. The callback of the sync is built from the provider of the role. The tests of `jira_statuses`
  (`TestJiraStatuses` in `bin/test_overview_push.py`) are replaced by the tests of the module and the core.

### Upgrading

- **LIGA: add `jira_base` to `tasks.json`** (the legacy file that already carries `supabase_url`), for example
  `"jira_base": "https://demo.atlassian.example"`. The credentials stay as they were: `JIRA_EMAIL` and `JIRA_TOKEN` in the
  environment, or the two files in `~/.claude/pipeline-feedback/`. **Without `jira_base` LIGA gets no statuses at all**, and when
  tasks have Jira keys the «Mine» tab shows the banner «Jira не налаштовано…» until the key is added (intended: a status cannot be
  asked without an address). The dashboard sync then simply skips the statuses.
- **An ordinary space:** to get statuses, enable the module (Connections → «Issue tracker», or the wizard) with the site
  address, your Atlassian e-mail and an API token. Without it nothing changes.
- Scripts that imported `jira_statuses`, `_jira_creds` or `_JIRA_BASE` from `bin/overview_push.py` must move to
  `app/tracker.py` and the module `app/modules/jira-tracker/`.

### Deliberate differences from 0.12.0

(everything else is checked against the snapshot)

- The address of the LIGA Jira comes from `tasks.json` (`jira_base`), not from the code.
- The Tasks screen of LIGA asks Jira directly (once per 5 minutes per computer; up to 6 s of waiting on a cache miss): the
  status of your own task is fresher than the dashboard's (it lagged by up to 30 minutes).
- A failure of Jira in the sync is a line in the log, not silence.
- Keys outside `KEY_RE` no longer go to Jira.
- HTTP 400 gets a fixed hint («check the task keys»); HTTP 408 and 429 count as transient (`tracker-error`); the body of an error
  answer is not read at all.
- An empty list of keys makes no call and shows no banner; keys that failed are remembered in the cache for the error time, so a
  dead tracker is asked once per 30 s and not on every visit.
- **Isolation:** with `DC_TASKS_FILE` or `DC_NO_OVERVIEW` the LIGA path never goes to Jira; the screen behaves as a space without a
  tracker (`tracker: null`, statuses only from the rows of the dashboard). `DC_TRACKER_FAKE` (a local JSON `{key: {name, cat}}`)
  is the test seam of that path.

### Known limits

- One key the tracker does not know fails its whole batch: Jira answers HTTP 400 to the whole query, so the batch gets no statuses
  and the 400 hint (before 4c-2 it failed silently). Fix the task key.
- Jira Cloud only (Basic `email:token`); Jira Server / Data Center and other trackers are separate modules later.
- The screen asks for the first 100 keys of «Mine» only (one call).
- The worst case of `/api/tasks-overview` is about **12 s** on a cache miss or «Try again»: the team rows (6 s) and then the
  tracker (6 s), one after the other.
- One lock (`_TRACKER_LOCK`) serves the tracker cache of **all** spaces: a dead Jira in one space can hold the «Tasks» screen of
  another for up to 6 s (as the team rows do).
- The error texts of the server are Ukrainian also in the English interface (as the isolation text of the team tab).
- The statuses of the «Team» rows come from the dashboard only; there is no link from a key to the page of the task, and no task
  title or assignee from the tracker.

### Tests

- Test-only: the live guard of the `dashboard` role over the real sync log now checks content markers in the **appended tail** of
  the log instead of comparing its length (a flake fix; no change in the product).

## [0.12.0] — 02.11.2026

Stage 4c-1: the team dashboard becomes a role. The «Team» tab of the «Tasks» screen and the writing of the task cards no longer
depend on the flag `integrations`: they belong to whoever provides the role **`dashboard`** in the space. The built-in module
`supabase-dashboard` provides it for anyone with their own Supabase project, and the LIGA space reaches its shared Supabase
through the same module as an implicit provider (as `git-sync`, `vercel-publish` and `supabase-comments` did in 0.8.0–0.10.0),
so it needs no new step (see *Upgrading*). The core decides what a card is (`app/dashboard.py`); the module only stores the
cards and returns the rows. Design: `docs/superpowers/specs/2026-11-02-dashboard-role-design.md`; plan:
`docs/superpowers/plans/2026-11-02-dashboard-role.md`. The behaviour of 0.11.0 is pinned by the snapshot
`tests/fixtures/dashboard/before-4c1.json`.

### Added

- **The role `dashboard`** in the core: it is called now (it was only reserved), and `capabilities.dashboard` carries the module
  id, `'legacy'` or `null`. The functions of a module: `rows(ctx)`, `push(ctx, cards, mode)` (`'merge'` | `'insert'`) and the
  optional `open_comments(ctx)`; the error codes `dashboard-unconfigured` (409) and `dashboard-error` (502). The contract is in
  `docs/modules/authoring.md`, «The `dashboard` role».
- **The module `supabase-dashboard` 1.0.0** (built-in) with its own `schema.sql`. Settings: `url`, `key` (a secret that is
  **not** public) and `table` (default `deai_dashboard`). The cards hold the name and the e-mail of a designer, and the public
  key of a project goes into every published preview, so the table has no policy for `anon` and `check` refuses a public key
  (`sb_publishable_…`, a JWT with `"role": "anon"`). `check` answers `no-schema` when the table is missing and `bad-key` on HTTP
  401/403. See `app/modules/supabase-dashboard/README.md`.
- **The «Team» tab in any space that has the role**, not only in LIGA. A space without a provider has no tab (`team: null`); a
  broken module of its own (or an unreadable `space.json`) keeps the tab and shows an error banner with the reason.
- **The role on the Connections screen** (the card «Team dashboard», between «Git sync» and the tokens) and in the new-space
  wizard; the texts are in `app/i18n.js` (UK and EN).
- **`bin/overview_push.py` is a thin CLI** over `app/dashboard.py`: `sync [--space ID | --legacy]` and `discover` (LIGA only).
  `sync` without a flag is the LIGA space, as before, so the external scheduler keeps working unchanged. Exit codes: 0 — the
  pass ran (a failure of single cards is in the log, not in the code), 1 — it could not start, 2 — wrong use.
- **The log of the sync of an ordinary space:** `<DEAI_HOME>/logs/dashboard-sync.log` (the folder is created for the owner
  only, the file is `0600`). LIGA keeps its old log file (`OVERVIEW_LOG` in `app/serve.py`).

### Changed

- **LIGA goes through the module.** The cards are stored and the team rows are read by `supabase-dashboard` with the address and
  the key of the installation (`supabase_config()`, now in `app/install_config.py`; `serve` still exports the name) and the
  table `overview_projects`. The rows of the «Team» tab and the cards in the database are the same; `schema.sql` is **not** run
  on the shared project. The steps that are not roles yet stay LIGA's: the base cards from the task registry (until 4d) and the
  Jira statuses (until 4c-2); they are handed to the sync as callbacks, so an ordinary space never reaches the registry or Jira.
- **The sync is one per space.** While the sync child of a space lives, a new trigger only marks «once more», and exactly one
  repeat starts after it ends (0.11.0 started a process per trigger, and two could run at once). The triggers are the same:
  after a publish, after a git sync that pushed and after an autosync that changed something. A child that lives longer than
  `SYNC_DEADLINE_S` = 600 s is terminated by the next trigger of that space, one line goes into the log, and a fresh child starts.
- **The gate of the sync** is the provider of the role in the space of the request, not `integrations`. No provider — silence.
- **The cache of the team rows is per space** (`team_snapshot`: 60 s, an error for 10 s, a failure keeps the last rows read). It
  remembers who gave the rows (`who`): a different provider never shows the rows of the previous one as «last known».
- **`app/dashboard.py`** now holds the building of the cards that was in `bin/overview_push.py` (`build_card`, `discover_card`,
  `card_has_pii`, `map_status`, …) with no change of behaviour; the CLI still exports the old names for its tests.
- **`overview_push.py` reads the config of the installation the way the server does:** the file `tasks.json` first, then
  `SUPABASE_URL`/`SUPABASE_KEY` (the limit of 0.10.0, «the environment is read first», is closed). `SUPABASE_URL` with
  `SUPABASE_SERVICE_KEY` is now only a **fallback** of the CLI, used when the installation has no pair at all.
- **Deliberate differences from 0.11.0** (everything else is checked against the snapshot):
  - the tab and the sync depend on a provider of `dashboard`, not on `integrations` (the same for LIGA, which has `'legacy'`);
  - the cards go in batches of up to 50 (0.11.0 sent them one by one), and cards with a different set of keys go in separate
    requests (PostgREST would fill a missing key with `null`, and `merge-duplicates` would wipe the stored value); one failed
    request puts all its card ids into `failed`, and LIGA sees that in the log;
  - one call carries each card id once — the **last** card wins (Postgres refuses a request with the same key twice as a
    whole); a card without a string `id` is reported in `failed`;
  - the core waits **6 s** for `rows`, and the own socket timeout of the module is **4 s** (0.11.0: 3 s per HTTP request), so the
    worst case of the «Team» tab is 6 s instead of 3 s; the core waits longer than the module so that the person sees the text of
    the module and not a bare `check-timeout`;
  - the error texts of the tab come from the module («Supabase недоступний (…)», or the HTTP status and the PostgREST code,
    never the key or a body of a request); the rows of the real path without a string `id` are dropped (a row that is not an
    object was dropped before);
  - **LIGA with `DC_TASKS_FILE` no longer starts the sync child** (0.11.0 started it: the gate was on reading only), because an
    isolated run must not write into the shared Supabase. `DC_NO_OVERVIEW` silences the writing for every provider. The
    isolation of reading (`DC_TASKS_FILE`, `DC_NO_OVERVIEW` and the test seam `DC_TEAM_FAKE`) applies to the `'legacy'` path
    only; a space with its own module is not affected by it;
  - the sync child is started as `sys.executable bin/overview_push.py sync --space <id>` (0.11.0: the literal `python3`, no
    space, the Supabase pair in the environment of the child); LIGA with no space of the request is `sync --legacy`, and the
    child reads the config of the installation itself;
  - a failure to add a base card from the registry is now written to the log by `sync` (0.11.0 swallowed it there; `discover`
    reported it);
  - a broken module of its own for the role, or an unreadable `space.json`, in a space with `integrations` does not turn the role
    into `'legacy'` (as for `comments`): the shared Supabase of LIGA is not a fallback;
  - the LIGA path now goes through the `supabase-dashboard` module, whose address check (`_base`) wants a DNS host name with at
    least two labels (`x.localhost` and the like pass; bare `localhost` and IP literals do not). A LIGA config with an IP or a
    single-label host, which the regex of `install_config` still accepts, now gets `module-error` instead of working (the same
    as the comments in 0.10.0).

### Removed

- `_supabase`, `upsert_project` and `open_comment_counts` of `bin/overview_push.py` (its Supabase client) and `from serve import …`
  in it: the script no longer imports the server. `TEAM_COLS` and the hard-wired `urlopen` of the team read left `app/serve.py`.

### Upgrading

- **LIGA: nothing to do** — no new step, no schema. **Check one thing before updating** if your scheduler runs
  `overview_push.py sync` with `SUPABASE_URL`/`SUPABASE_KEY` or `SUPABASE_SERVICE_KEY` in its environment: it now writes to the
  pair of the legacy `tasks.json` when that file has one (the same pair the comments use), and the environment is read only when
  the file has none. Make sure that pair may write the table `overview_projects`, or take it out of the file so the pair of the
  environment is used. After updating, look at the log of the LIGA sync (`OVERVIEW_LOG`) after the next run. Also, a scheduled
  `sync` now resolves the provider of the role through the spaces registry (`spaces.load_registry()`): a legacy entry with
  `integrations` off and no `supabase-dashboard` enabled in its `space.json` is silent (no provider, nothing is synced), a
  registry with no legacy entry ends with exit code 2, and loading the registry may run its migration, which writes the legacy
  entry to the registry file.
- **An ordinary space:** create a dedicated Supabase project, run `app/modules/supabase-dashboard/schema.sql` in its SQL editor,
  then enable the module (Connections → «Team dashboard», or the wizard) with the project URL and a **non-public** key
  (`service_role` or the key of a role of your own — such a role needs explicit grants and policies, see the module README).
  Without the module the space has no «Team» tab and sends no cards.
- Scripts that imported `_supabase`, `upsert_project` or `open_comment_counts` from `bin/overview_push.py` must move to the
  module (`app/modules/supabase-dashboard/`) or to `app/dashboard.py`.

### Known limits

- LIGA keeps using the key of the installation: the check «non-public key» is not applied to it, and its table is guarded by the
  policies of its database, not by `schema.sql`.
- The task registry and the base cards from it are LIGA's own step until 4d; the Jira statuses are LIGA's until 4c-2. An ordinary
  space has no tracker statuses on its cards until 4c-2.
- The schedule of the sync is an external scheduler, not the canvas; the canvas starts a sync only after a publish, a git sync
  or an autosync.
- One lock (`_TEAM_LOCK`) serves the team rows of **all** spaces: an unreachable service of one space can hold the «Tasks» screen
  of another for up to 6 s (the error is then cached for 10 s).
- The deadline of a hung sync child has no timer: the next trigger of the space checks it, so a child that hangs with no trigger
  after it stays alive. Two narrow races are left as they are: the registry is read before `_SYNC_LOCK`, so two runs are possible
  only if the registry changes (or fails to read) at that very instant; `_overview_stop` may hold `_SYNC_LOCK` for up to 5 s (only
  when a child is hung). `--legacy` is parsed and not read (no `--space` means LIGA).
- If the folder of `OVERVIEW_LOG` does not exist, the sync child of LIGA silently does not start (the log cannot be opened; as in
  0.11.0). An ordinary space creates its own log folder.
- `open_comments` reads one answer of Supabase, which cuts it at its `max-rows` (1000 by default): with more open comments than
  that the numbers, and so the status `review`, are lower than the truth. `rows` returns at most 500 rows.
- The key of an ordinary space lives in `~/.deai/secrets.json` (owner only, plain text), as the other keys do.

## [0.11.0] — 02.11.2026

Stage 4b-3: the profile stops being the label of the «Tasks» screen. A task gets general **tags** (any space), the chips, the
filter and the search of the screen are built from them, and a LIGA task without its own tags shows its profile as a tag, so
the LIGA screen looks as before. The table «profile → repository» of the LIGA space left the code and is read from the
installation (see *Upgrading*). Design: `docs/superpowers/specs/2026-11-02-task-tags-design.md`; plan:
`docs/superpowers/plans/2026-11-02-task-tags.md`. The behaviour of 0.10.0 is pinned by the snapshot
`tests/fixtures/task-tags/before-4b3.json`.

### Added

- **The task field `tags`** (a list of strings, in any space). Normalising (`normalize_tags`): spaces trimmed and runs of
  spaces collapsed, 1–32 characters, no control characters, no invisible or bidirectional-control characters (zero-width
  U+200B–U+200F, U+2060–U+2064, U+FEFF; U+202A–U+202E, U+2066–U+2069) and no comma, empty ones dropped, case-insensitive
  duplicates dropped (the first spelling stays), at most 10. Anything else (not a list, a list of more than 100 items, a
  non-string, too long, a comma, a control or invisible character, more than 10) is `400 bad-tags` — no silent trimming.
- **The API.** `tags` is the **last** key of every row of `/api/tasks` (before `space` with `?all=1`) and of the «mine» rows of
  `/api/tasks-overview`; in `/api/task` it follows `profile`; the key `profile` stays. `/api/task-new` takes an optional `tags` (written only when the list is not empty).
  **New `POST /api/task-tags` `{id, tags}`** replaces the tags of the task `id` (the space is found by the task, as
  `task-switch` does; the current task and space are not changed) and answers `{ok: true, tags}`; an empty list is valid and
  is kept as `[]`. Errors: `404 unknown-task`, `409 ambiguous-task` (the id is in two spaces), `400 bad-tags` (checked before
  the task is looked up), `503 space-unavailable` (the task file cannot be read). After the write the registry is synced, as
  after the other task changes.
- **The registry carries `tags`** (`bin/registry.py`, `SHARED`), and an empty list `[]` travels too: without it another
  machine would keep its old tags (a pull merges a key only when the entry has it) or show the derived one.
- **The screen.** Chips of the tags (the «Mine» tab), the tag filter, the search over the tags, the button «Мітки» on a card
  of «Mine» (a dialog with one field, «tags, comma-separated», filled with the current ones; `bad-tags` is shown under the
  field, any other failure is a toast), and the optional field «Мітки» of «New task» (sent only when not empty). The state of
  the screen saved by 0.10.0 (`dc-tasks-ui.profiles`) is migrated: the old profile keys become tag keys.

### Changed

- **The chips and the meta line of a card come from the tags** instead of the profile. A chip is keyed by the tag in lower
  case and labelled with its first-seen spelling; the chips follow the status chips. The first part of the meta line of a
  «Mine» card is the tags joined with «, ». The «Team» tab is as before.
- **The derived tags of LIGA.** `task_tags`: the saved `tags` when the key exists (even an empty list: a person removed them
  all on purpose); otherwise a non-empty `profile` gives the tag `United`, `LIGA360` or `SEO` (an unknown profile is shown as
  it is); otherwise none. The task files are not rewritten. A derived tag goes through the same rules as a saved one, so a
  profile with a comma or longer than 32 characters gives no derived tag.
- **`profile_repos()` replaces the constant `PROFILE_REPOS`.** The table is read from the root of the legacy `tasks.json`
  (the same file and reader as `supabase_config`): a key is a profile `[a-z0-9-]{1,32}`, a value is a repository — printable
  ASCII without spaces, not starting with `-` (git would take it for an option); bad pairs are dropped, an unreadable file or
  a missing key gives `{}`. A new LIGA task takes `{repo: profile_repos()[profile], path: mockup/<id>}` as its default
  GitLab, and `_liga_flow` recognises the profile by the same table.
- **Conscious differences from 0.10.0** (everything else is checked against the snapshot):
  - a task without tags is hidden while a tag filter is on (the profile filter let a task without a profile through);
  - the chips are ordered by the number of tasks, then alphabetically, not United → LIGA360 → SEO;
  - a profile outside the three known ones is shown as it is (as before), now also in an ordinary space when it was written
    by hand;
  - **without `profile_repos`** a new LIGA task is created with no default GitLab repository, and a body that has only a
    `profile` is no longer a sign of the LIGA flow.

### Removed

- `PROFILE_REPOS` of `app/serve.py`; `PROFILE_KEYS`, `PROFILE_ORDER` and `profileLabel` of `app/tasks-home.js`; the i18n keys
  `profUnited`, `profLiga360`, `profSeo`.

### Upgrading

**Before updating**, add the table «profile → repository» to the root of the legacy `tasks.json` (the file of the LIGA
space), with the repositories you used to get from the code:

```json
{ "profile_repos": { "united": "git@git.example:org/united-design.git", "liga360": "git@git.example:org/liga360-design.git", "seo": "git@git.example:org/seo-design.git" } }
```

Without it, after the update new LIGA tasks get no default GitLab repository (the tasks that exist keep theirs). Tags need
nothing: a LIGA task without `tags` shows its profile as before. `tasks.example.json` does not carry `profile_repos` on
purpose (a placeholder would pass as a real config).

### Known limits

- The «Team» tab has no tags (its rows come from the dashboard) — until stage 4c.
- A tag cannot be renamed in all tasks at once, only task by task.
- An **old client** that syncs the registry does not know `tags`: when it writes a task it drops the tags of that task from
  the registry entry. A newer client puts them back on its next write of that task, so until every machine is updated the
  entry may flip back and forth, one commit each time.
- `POST /api/task-tags` does **not** hold `spaces.WRITE_LOCK` across its read-modify-write (a deviation from the spec):
  `save_tasks` takes the lock for the write itself, but the read before it is unlocked (the same as `task-switch`). So a
  concurrent change of the same `tasks.json` by another route — any field, not only tags — can be lost: the last write wins.
- The search does not highlight a match inside the tags.
- A chip is labelled with the first-seen spelling of the tag, so its case may change when the order of the tasks changes
  (`Alpha` and `alpha` are one chip).
- The button «Мітки» sits inside the card (the card itself is a control), so it is one more Tab stop per card.

## [0.10.0] — 30.10.2026

Stage 4b-2: the comments of the legacy space become a module too. The shared Supabase of the in-house setup is now reached
through the built-in `supabase-comments` module as an implicit provider (as `vercel-publish` and `git-sync` were in 0.9.0 and
0.8.0), and the address and the public key of that Supabase left the code: they are read from the installation (see
*Upgrading*). The legacy space looks the same apart from the changes listed below
(`tests/legacy-golden.test.mjs` is green without a re-shoot; the behaviour of 0.9.0 is pinned by the snapshot
`tests/fixtures/legacy-comments/before-4b2.json`). Design: `docs/superpowers/specs/2026-10-30-legacy-comments-module-design.md`;
plan: `docs/superpowers/plans/2026-10-30-legacy-comments-module.md` (its «Поправки до спеки» override the spec).

### Added

- **`supabase-comments` 1.1.0: the setting `shots_bucket`** (optional; the name of a public Storage bucket of the same
  project: lowercase letters, digits, `-` and `_`, up to 63 characters). When it is set, the page config carries `shotsBucket`
  and the browser adapter gains `uploadShot(id, dataUrl)`: it uploads the screenshot of a pin to
  `<bucket>/comment-shots/<id>.jpg` (upsert, with the public key) and returns the public address, or `null` when the upload
  fails or the arguments are not safe. Without the setting nothing changes. A bad name is `bad-settings` (also in `check`).
- **`resolve(ctx, channel, id, reason, iteration=None)`:** a whole `iteration` ≥ 1 is written to `resolved_v` too (a `bool` is
  not an iteration number); without it the call is as before. **Only the built-in `supabase-comments` module receives the
  number** — a space's own module keeps the four arguments of the contract (see *For module authors*).
- **TLS with `certifi`:** the HTTP client of `supabase-comments` uses the `certifi` store when the package is installed (the
  Python of python.org on macOS does not see the system one), otherwise the default context.
- **The core's error code `comments-unconfigured`** (409): the installation has no `supabase_url`/`supabase_key`. It shows in
  the client as the raw code, like the other codes of the comment config.

### Changed

- **The legacy space keeps its comments through `supabase-comments`** (an implicit provider, `comments_route(space, prov)` in
  `serve.py`; `comments_provider` keeps its shape). The channel is still `comment_project` (or `dc/<task>`, with `/internal`
  for the internal one), the table is the same, and the `ctx` is built from the installation (`shots_bucket` is
  `overview-thumbs`), without `~/.deai`. The canvas page `/commented`, the published preview, `/api/comment-config`, the
  Overview, `inbox`, `inbox resolve` and `state` all go through the module; `inbox resolve` still passes the number of the
  iteration. `spaces.require_integrations()` still guards this path.
- **Where the Supabase of the legacy space is configured:** the root of the legacy `tasks.json` (`supabase_url`,
  `supabase_key`; the same file that carries `gitlab_ssh_key`), or the environment variables `SUPABASE_URL` and
  `SUPABASE_KEY` as a fallback. The pair comes whole from one source, `https` only, and the key must be a public one
  (`sb_publishable_…` or an anon JWT; a secret key is refused by the rules of the module). The same pair now feeds the
  team dashboard, the Teams silence and the dashboard push (`bin/overview_push.py`); without it they report «not configured»
  (the Teams mute answers `Supabase не налаштовано`, the team rows show that text, a standalone `overview_push.py` stops with
  an error; the background sync after a publish stays silent). Anything that is not a plain `https://<host>[:port]` address
  or a printable key without spaces (for example the placeholders `https://<ref>.supabase.co` and `sb_publishable_…`) counts as
  «no config», and that source is skipped whole. Error texts never contain the key.
- **Without the pair the comments of the legacy space are «unavailable»:** the page shows the local pins and a notice, a
  publish goes on without team comments and with `comments_unavailable`, the comment config answers `comments-unconfigured`.
- **Small conscious differences for the legacy space** (everything else is checked against the snapshot of 0.9.0):
  - the published preview and the page `/commented` use the markup of the module and supabase-js from its own copy (no
    jsdelivr, no floating `@2`); the adapter signs in without keeping a session (the legacy space had none);
  - resolving also filters by the channel and says so when the pin is not found (0.9.0: silently zero rows); the
    `inbox resolve --dry-run` line is now `[dry-run] Supabase: resolve <channel> <id> Іт.N "reason"` (the reason as a JSON string), the same for every
    space, instead of the raw PATCH;
  - `list` comes in the order of `id` with the ceiling of 5000, as in any space, and its rows pass the sanitizing of the
    agent's pins; the anchor of a pin for the agent (`fp`) keeps the whole `text` up to 2000 characters and the **last** 50
    entries of `path` (the first 50 would drop the tail that `inbox --where` compares), where 0.9.0 handed over the raw `fp`;
  - the realtime refetch is debounced (120 ms) and `close()` closes the socket;
  - `state`: when the Supabase of the legacy space does not answer, the line says «проєктні: не дістати (<code>)» instead of a
    quiet `0`, and «проєктні: Supabase не налаштовано» when the installation has no pair;
  - `build_preview(comments=…)` accepts only `False` or the dictionary of a module; `True` is a `ValueError`, like `'legacy'`.
- `bin/import_preview.py` recognises the old preview snippet by frozen markers (the snippet itself is gone from the core), so
  previews already in circulation are still imported.
- `app/overview-comments.js` and `app/index.html` have only the module path: no `SB_JS` branch, no
  `CommentLayerSupabase`, no old adapter.
- The two golden files of the legacy preview page and comment config
  (`tests/fixtures/comments-role/page-legacy-project.html`, `config-legacy-project.json`) were rewritten on purpose (the page
  is now the markup of the module); the other four are byte-identical.

### Removed

- The constants `SUPABASE_URL` and `SUPABASE_KEY` of `app/serve.py` (replaced by `supabase_config()`).
- The old comment snippet and its injector (`COMMENT_SNIPPET`, `inject_comment_layer`), the dead `INTERNAL_TINT` (no call
  ever passed `internal=True`), and the old adapter `app/vendor/supabase-adapter.min.js`: it moved to
  `tests/fixtures/legacy-comments/supabase-adapter.min.js` as the reference of the parity tests, and is not shipped.
- `supabase_pins`, `patch_project_pin` (`bin/inbox.py`), `project_body`, `state._open_pins`, the `legacy=` callbacks of
  `ProjectComments.pins/resolve` (the kind `'legacy'` of `ProjectComments` itself stays: it now runs on the module), and the value `True` of `build_preview(comments=…)`. `BUNDLES` and `BUILD_KINDS` stay: `ops/reseal_gate.py`
  reads them for builds made before 0.10.0.

### Upgrading

**Before updating**, add the address and the public key of the shared Supabase to the root of the legacy `tasks.json`
(the file of the LIGA space; or put `SUPABASE_URL` and `SUPABASE_KEY` into the environment):

```json
{ "supabase_url": "https://<ref>.supabase.co", "supabase_key": "sb_publishable_…" }
```

Without them, after the update the team comments of the LIGA space switch off (the local page and a notice, no network),
and the dashboard and the Teams silence report «not configured».

### For module authors

- `resolve` of a space's own module is still called with four arguments; the iteration number goes only to the built-in
  `supabase-comments` (a module that declared `resolve(ctx, channel, id, reason)` would break on a fifth).
- A store may have an optional `uploadShot(id, dataUrl)` (see `docs/modules/comments.md`); the layer uses it when it is there.

### Known limits

- PostgREST `max-rows` (1000 by default) may still cut `list` silently, as before.
- Previews of the legacy space published earlier carry the old key and the old adapter inside: changing the key in the config
  does not update them. They are not touched.
- The `html2canvas` layer still loads from jsdelivr (out of this stage).
- The key sits in `tasks.json` in plain text (it is a public key; it used to be in the code).
- The order of the sources differs between two readers: `serve.supabase_config()` prefers `tasks.json` over the environment,
  while `bin/overview_push.py` prefers the environment (including `SUPABASE_SERVICE_KEY`) and falls back to that config. The
  server hands its config to the sync it starts through the environment, so there they agree; a standalone or scheduled
  `overview_push.py sync` with a stray `SUPABASE_URL`/`SUPABASE_KEY` writes to that project. The dashboard is stage 4c, so
  this is left as is.
- `schema.sql` of the module is **not** to be run on the shared project of the legacy space (it rewrites the policies); the
  table there already has the same shape.

## [0.9.0] — 30.10.2026

Stage 4b-1: publishing becomes a module for the legacy space too. The built-in `vercel-publish` module learns a second way
to sign in — the **system Vercel CLI** (`auth: cli`): no token, the `vercel login` of the computer — and the in-house
legacy space publishes through it as an implicit provider. The Vercel transport left `app/serve.py`; the legacy space
looks the same (`tests/legacy-golden.test.mjs` is green without a re-shoot) apart from the changes listed below. Design:
`docs/superpowers/specs/2026-10-30-legacy-publish-module-design.md`; plan:
`docs/superpowers/plans/2026-10-30-legacy-publish-module.md`.

### Added

- **`vercel-publish` 1.1.0: the setting `auth`** — «Token» (`token`, the default; the code of 1.0.0, REST API, no Node) or
  «System Vercel CLI» (`cli`). `cli` runs `npx --yes vercel` under the sign-in of the computer (`vercel login`): `link`,
  `deploy --prod`, `inspect` for the shortest `*.vercel.app` address, a check of the preview, then the cleanup below. No
  token is read, stored or put into a subprocess; `team` is the `--scope` (empty: the personal account). The project name
  and the scope go into the command line, so they are checked first (see *Changed*). Any space can choose it on the
  Connections screen and in the wizard.
- **Cleanup of old deployments in `cli` mode.** After a publish the module lists the project's deployments
  (`vercel list <project> --json`, up to 5 pages) and removes the old ones: the 3 newest are kept, the current one among
  them. Only records whose `name` is the project and whose address ends in `.vercel.app` are touched, with
  `vercel remove <address> --safe --yes`; **a project name is never passed to `remove`** (the CLI would delete the whole
  project). Any failure — a list that cannot be read, a timeout, a refused removal — is a warning, never an error, and
  nothing is removed when the list was not understood. The whole cleanup has a hard limit of 60 s.
- **`ctx["find_tool"]`** for every module: a function `find_tool("npx" | "node") -> path | None` (any other name gives
  `None`). The core registers its own finder, which knows nvm, volta and Homebrew locations that a GUI app does not have
  in its `PATH`, and calls it only when a module asks.
- **The manifest key `check_timeout_s`** (optional, an integer 1..150; anything else makes the manifest invalid): how long the
  core waits for the module's `check` (default 5 s). `vercel-publish` asks for 130 s: in `cli` mode `check` runs
  `npx --yes vercel whoami`, and a cold `npx` downloads the CLI first. `GET /api/modules` shows the key when a module has it,
  and the canvas lets the request of «Check», «Enable» and the settings panel (and the wizard) wait for it plus a margin of
  15 s (the other modules keep 20 s).
- **`ModuleError.full`** — the whole error text (up to 64 KiB, secrets already removed by the core); `message` stays at
  300 characters.
- **Error codes** in the core's table: `no-node` (409), `vercel-login` (409), `vercel-scope` (409), `vercel-deploy` (502),
  `vercel-no-url` (502).
- **Client texts** for those codes, in English and Ukrainian: in the publish dialog, and on the Connections screen
  (`no-node` and `vercel-login` for «Check»).

### Changed

- **The in-house legacy space publishes through `vercel-publish` in `cli` mode** (an implicit provider, as `git-sync` did in
  0.8.0). The core still builds the preview, mints the project name in `tasks.json`, pushes to the registry and the
  dashboard, and composes the same answer of `/api/publish` with the same keys in the same order; `iterations.json`,
  `tasks.json`, the commands and their time limits are those of 0.8.0. The error texts of that space (the sign-in hint,
  the scope hint, the Deployment Protection hint, «URL not found») stay in the core and are built from the new codes. It
  does not write `publish_remote`: its state is in `tasks.json`, as before.
- **The legacy space now cleans up old deployments too** (decision of 30.10.2026; 0.8.0 never did, and on 09.10.2026 that
  hit the storage limit of Vercel). The permanent `pv-….vercel.app` addresses live on; only the direct addresses of old
  publishes stop opening. The answer of `/api/publish` has a new optional last key, `cleanup_warning`, when the cleanup
  did not finish; the publish dialog shows it next to the other warnings.
- The module is called with `task["gated"]`: `true` when the core put the password gate into the pages. In `cli` mode a
  preview is `verified` only when the page carries the gate marker (with a gate) or answers 200 (without one); `token`
  mode ignores the field.
- The setting `token` of `vercel-publish` is no longer marked `required` and has a new label, «Токен Vercel (для входу
  «Токен»)»: the generic form has no conditional fields. The module itself demands the token in `token` mode, as before
  (`vercel-auth`).
- `check` in `cli` mode runs `npx vercel whoami` (120 s of its own, inside the 130 s of the manifest) and answers `no-node`,
  `vercel-login` or `check-timeout`.
- **In `cli` mode the stored state of an ordinary space is not trusted** (it comes from `iterations.json`, which travels
  through git). The project name is taken from it only when it is `pv-<8 digits>`; any other name (a `dc-…` name, the name of
  another project of yours) gives a new `pv-…` project and a warning, as in `token` mode — a cloned state can no longer make
  `vercel link --yes` bind, and the cleanup prune, a project it names. The scope comes only from the setting `team`, never
  from the state. The legacy space is the exception: the core marks its call with `task["legacy_state"] = true`, because that
  state is built from the local `tasks.json` and registry, and then any safe name (`dc-…`) and the state's scope are accepted
  as before. An ordinary space never sets that key.
- **A failed `vercel link` now stops a `cli` publish** (a conscious difference from 0.8.0, which ignored its exit code): the
  publish ends with the code of the output (`vercel-login`, `vercel-scope`, `vercel-auth`, `vercel-deploy`) and runs neither
  `deploy` nor the cleanup. Before, a failed `link` could deploy into a project named after the folder and then clean up the
  intended project without its current deployment.
- In an ordinary space a `vercel-deploy` failure shows the **end** of the CLI output (the last 300 characters of it, where the
  reason is), not the first 300 characters of the last 4000 that the error message holds. The legacy space is unchanged.
- The text «Vercel denied access» no longer says only «check the token»: it names the sign-in (token or `vercel login`) and the
  team. The project and scope errors no longer mention «the state».
- **Small conscious differences for the legacy space** (everything else is checked against a snapshot of 0.8.0,
  `tests/fixtures/legacy-publish/before-4b1.json`):
  - a `vercel deploy` that fails with no output at all now gets a human line («vercel завершився з помилкою, але нічого
    не надрукував…»); 0.8.0 answered an empty `deploy_error`, which the interface could take for a success;
  - the check of the preview sends a `User-Agent` and an `Accept` header (0.8.0 used the defaults of `urllib`), and the
    reason «address unreachable» has its whitespace collapsed;
  - the project name and the scope are checked before anything runs: the project `[a-z0-9][a-z0-9._-]{0,99}`, the scope
    `[A-Za-z0-9][A-Za-z0-9_-]{0,99}`; an odd value (for example, one that starts with `-`) is refused instead of being
    passed to the CLI;
  - a `vercel link` that exits with an error ends the publish (see above) — 0.8.0 went on to `deploy`;
  - `check` has the codes `no-node` and `check-timeout` (a new path).

### Removed

- The Vercel transport of the core, `app/serve.py`: `_deploy_urls`, `_stable_alias`, `_check_published`, `_deploy_hint`
  and the `npx vercel` subprocess block of `Handler._publish`. They moved into the module, or, for the in-house texts
  (`_deploy_hint`, the hint of Deployment Protection), into one adapter of the legacy space (`_publish_legacy_call`,
  `_legacy_deploy_error`).

### For module authors

- `ctx["find_tool"]`, `task["gated"]` and `ModuleError.full` are available to every module (see
  `docs/modules/authoring.md`). The manifest may carry `check_timeout_s` (1..150) to lengthen the `check` of a module that
  starts a process. (`task["legacy_state"]` is private to the core and the built-in `vercel-publish`; do not rely on it.)
- A `publish` result may carry three optional keys: `deploy_url` (the address of the publish itself, as opposed to the
  permanent `url`), `verify` (`{"reason"}` — why `verified` is false) and `cleanup_warning` (a string). The core
  reads them only for the in-house legacy space; in other spaces they are ignored (the cleanup text is also in
  `warnings`).
- The five new codes above are in the core's table, so they pass as they are.

### Known limits

- In `cli` mode of an ordinary space a project that an older state names with a non-`pv-` name is not reused: a new `pv-…`
  project is made, with a warning (the state of an ordinary space is not trusted; see *Changed*).
- In `cli` mode of an ordinary space the project name is a random `pv-<8 digits>` with no probe whether the name is
  taken (`token` mode probes it).
- In `cli` mode of an ordinary space, if `deploy` fails after `link`, an empty `pv-…` project stays in Vercel and the next
  try creates another one (the legacy space mints its name in `tasks.json` before the deploy, so it does not).
- The cleanup reads at most 5 pages of `vercel list`; older deployments go in later runs.
- The flags `vercel list --json` and `remove --safe` are those of CLI 65.x (checked on 30.10.2026). With an older CLI the
  cleanup ends in a warning and the publish is not affected.
- `cli` mode verifies the preview by the gate marker (when there is a gate), `token` mode by HTTP 200.
- The preview check of `token` mode has no `certifi` context (a backlog item); `cli` mode has one.

### Tests

- A fake `npx` (`tests/fake_npx.py`) drives the new tests without any network and without a real `vercel`:
  `tests/test_vercel_publish_cli.py` (the `cli` mode, the cleanup, `check`) and the legacy branch of
  `tests/test_serve.py` and `tests/test_publish_module.py`, which also compares a publish of the legacy space with a
  snapshot of the 0.8.0 answer, the files and the commands (`tests/fixtures/legacy-publish/before-4b1.json`).
  `tests/legacy-golden.test.mjs` is unchanged and green. A live test, `tests/live/legacy-publish-cli.test.mjs`, presses
  «Publish» of the legacy bar with the fake `npx` (the path that needs no network: `deploy` without an address).

## [0.8.0] — 30.10.2026

Stage 4a: git sync becomes a module. The new role `vcs` and the built-in module `git-sync` sync a task's iterations with
any git repository — GitHub, GitLab, your own server — in any space, not only in the in-house legacy one. The git
transport left `app/serve.py`; the legacy space runs on the same module and looks the same
(`tests/legacy-golden.test.mjs` is green without a re-shoot). Design:
`docs/superpowers/specs/2026-10-26-git-sync-module-design.md`; plan:
`docs/superpowers/plans/2026-10-26-git-sync-module.md`.

### Added

- **The `vcs` role and the `git-sync` module** (`app/modules/git-sync/`, `app/deai_modules.py`). `vcs` moved from the
  reserved roles to the roles the core calls. The module is a transport: a mirror clone per repository address, `fetch`,
  a push without force, `pull --ff-only`, the address of the history for GitHub and GitLab; it knows nothing about
  iterations. Six settings: `repo` (the default for tasks, optional), `branch` (`main`), `path` (`mockup/{task}`),
  `ssh_key`, `host_ip`, `autosync` (off by default). Addresses: `ssh://`, `https://`, `file://`, `user@host:path` or an
  absolute local path. Access is the git of the computer — an SSH key or a saved HTTPS sign-in; Deai stores no git
  secrets. `check` asks the remote for the branch (`git ls-remote`, 4 s). One operation per mirror, with a lock that works
  between processes. New error codes in the core's table: `vcs-offline`, `vcs-auth`, `vcs-bad-target`, `vcs-busy`,
  `vcs-error`; `ctx["cache_dir"]` for every module.
- **Routes**: `GET /api/vcs-status?it=`, `POST /api/vcs-push`, `POST /api/vcs-pull`. `GET /api/gitlab-status`,
  `POST /api/gitlab-sync` and `POST /api/gitlab-pull` stay as aliases with the same handlers and answers (an agent's Stop
  hook and scripts rely on them). A refusal now carries `code`. `POST /api/task-new` accepts
  `vcs: {repo, path?, branch?}`.
- **Connections**: the section «Git sync» and the Git card — the six fields, «Check» and the verdicts for `vcs-offline`,
  `vcs-auth`, `vcs-bad-target`, `vcs-busy` and `vcs-error`. In the legacy space, turning an explicit `git-sync` off
  returns the built-in sync.
- **New task**: an optional «Repository» field (not in the legacy space; its hint is the default repository of the
  module). A request that really clones — the field is filled, or a space with integrations and a `vcs` role — has a
  ceiling of 400 s instead of 20 s, the button says «Creating…» and a line says «The first clone of the repository may
  take a few minutes»; every other request is as before.
- **Wizard**: the section «Git sync» on step 2; no module is selected by default.
- **Task bar and palette**: the sync zone follows the `vcs` role, not the legacy space only. The label comes from the
  module and is one of GitLab, GitHub, Git («Git» in a regular space when the label is not known); «History» only for an
  `http(s)` address; a busy state, when another operation holds the mirror, asks again every 5 s, up to 4 times;
  «Configure repository…» outside the legacy space opens Connections on the Git card, on a cold start too.
- The credentials part of an address (`https://***@host/…`) is masked in every answer, error text, `remote`, the Stop hook
  line and `bin/state.py`.

### Changed

- **The legacy space syncs through the same module** (an implicit provider, `'legacy'`): the old mirror folders
  (`DC_MIRRORS_DIR`, or `.mirrors` in the tool folder), the label «GitLab», the commit subject `design-canvas: sync …` and
  all the texts are as before. An explicit `git-sync` in the legacy space wins over the implicit one, like any other role.
- **What the legacy space can see differently in git** (the module checks and runs git more strictly than 0.7.0 did):
  - `validate` refuses what 0.7.0 let through — an `http://` or `git://` address, a relative local path, an `ssh_key` that
    is not an existing file, a branch that `git check-ref-format` would refuse, a path with `*`, `?`, `[` or `\` or with a
    `.git` segment, and the other refusals listed under *Security* — as `vcs-bad-target` in status, send and pull.
  - When a task has an `ssh_key`, and on the retry through `host_ip`, the ssh command gets `-o BatchMode=yes`: a key with a
    passphrase that is not in `ssh-agent` ends in `vcs-auth` instead of a prompt. Without a key and without a retry the
    ssh of the person (`core.sshCommand`, `~/.ssh/config`) is left alone.
  - The environment of git: `GIT_ALLOW_PROTOCOL=ssh:https:file`, `GIT_TERMINAL_PROMPT=0`, `LC_ALL=C` (the errors are read
    in English), `GIT_LITERAL_PATHSPECS=1` for paths, and the `GIT_AUTHOR_*`, `GIT_COMMITTER_*`, `GIT_DIR`… of the parent
    process are dropped. The base of an ssh command the module builds is the `GIT_SSH_COMMAND` of the environment, else
    `ssh`.
  - `ssh://git@host/…` in `remote`, `web` and in the texts is now `ssh://***@host/…` (the whole userinfo is masked; the
    scp form `git@host:path` is as it was).
  - The folder of the mirror keeps its 0.7.0 name, but a folder whose recorded `origin` is **another repository** (another
    path or another host, for example after a project was renamed or moved) is no longer rewritten with `set-url`: status,
    send and pull stop with `vcs-error` («the mirror folder … holds another repository») and the folder has to be deleted
    by hand. The same repository in another form (`file://` ↔ a path, `ssh://` ↔ `user@host:path`, a name ↔ the bypass
    IP of 0.7.0) is still followed.
- **The mirror folder of a regular space has a hash suffix**: `mirrors/<host>/<slug>-<8 hex of the normalized address>`.
  The slug turns `/` and `-` into the same character, so `o/r` and `o-r` used to share one folder, and a send to the second
  repository carried the whole history of the first one to its remote. In a regular space, different repositories never share a folder now (the legacy space keeps its 0.7.0 folder names and refuses a foreign origin instead).
- A regular space: the commit subject is `deai: sync …`, the local autocommit says `автосинк (deai)`, a pulled iteration is
  noted «оновлення з репозиторію» and a task started from a repository continues as «продовження макета з репозиторію»,
  the README of a multi-page push says «Deai Canvas». These are texts of data, Ukrainian whatever the UI language; the
  legacy space keeps `design-canvas: sync …`, «оновлення з GitLab», «продовження макета з GitLab» and «design-canvas».
- The texts of the bar that name the repository take its label as the last parameter, «GitLab» by default.
- The mirror is a cache of the tool: before every send or pull its tree is reset (`reset --hard`) and cleaned
  (`clean -fd`). Hand edits in a mirror do not survive; commits that were not pushed do.
- `status` does not wait for a busy mirror (`vcs-busy` at once); `push` and `pull` wait up to 60 s.
- A branch that is missing on a non-empty remote is an error: Deai does not create branches in a shared repository. On an
  empty remote the first send creates it.
- A git command that does not answer in time is `offline` (`vcs-offline`), not an unhandled exception. A refused pull is no
  longer swallowed (0.7.0 copied the stale mirror into a new iteration, signed with the colleague's name): it stops with
  the error.
- Control characters in a task title or in the author's name are removed by the core before a commit; the module refuses
  them, so a single stray character would otherwise block every send.
- Autosync (`POST /api/autosync`): `autosync` off in the module → `reason: "autosync-off"`, with neither a send nor the
  local autocommit; a refusal of the network or of the module → the quiet `offline` with the `code`; a refusal of the
  provider (an unreadable `space.json`, an own module «on paper») → the quiet `no-gitlab` with the `code`; a failure
  outside the send itself (reading or parsing `iterations.json`, reading the task) → `reason: "error"`, which the Stop hook
  reports; a failure inside the send (network, the module, no `git` in the path, permissions while the folder is
  prepared) → the quiet `offline`, with the `code` when the module gave one — as in 0.7.0; the central states of the
  space → 404, 503 or 409 as for any route.
- An iteration that is invalid or not a string in `vcs-push` and `vcs-status` is `400 bad iteration`, instead of a dropped
  connection or a read of another folder.
- `bin/state.py`: the label comes from the module; a busy mirror reads as «try again», not as an error.
- The SSH key and the server IP: the task's own, then the setting of the module, then the shared ones in the root of
  `tasks.json` (the root only in a space with integrations).
- `POST /api/task-new` with `vcs` refuses with `400 bad-request`, `400 vcs-needs-role` (no `vcs` role in the space),
  `400 vcs-bad-target`, `409` with the provider's code (an unreadable `space.json`, an own module on paper),
  `504 check-timeout` or `502 module-error`; for a code it has no text for, the form says «Failed: <reason>».

### Removed

- The git transport in `app/serve.py` — the mirror, `fetch`, push, pull, the retry through `host_ip` — it moved into the
  module.
- 15 dead keys of the UI dictionary, in both languages: `glCatchUpLabel`, `glDirtyTitle`, `glErrorLabel`,
  `glHistoryLabel`, `glHistoryTitle`, `glIterationFallback`, `glPullBadge`, `glPullTitle`, `glSendLabel`,
  `glSyncedLabel`, `glSyncedLabelBare`, `glSyncedTitle`, `glSyncingLabel`, `glThisIterationFallback`,
  `glUnpushedTitle`.

### For module authors

- `vcs` is a called role: `status`, `push` and `pull` are required, `validate` and `mirror_dir` optional; `tracker`,
  `dashboard` and `notify` are the reserved ones now. The contract — the target, the functions and their results, the
  codes — is in `docs/modules/authoring.md`, *The `vcs` role*.
- **An own module of 0.7.0 with `roles: ["vcs"]` and only `check` is now `bad-manifest`** (`server.py: no callable
  status()`); it passed before, because the role was only reserved.
- The core checks the shape of a result (`status`, `push`, `pull` and `validate` a dict, `mirror_dir` a string; otherwise
  `module-error`), refuses a dict that JSON cannot carry (a `set`, `bytes`: `module-error` too, instead of a dropped
  connection) and masks the credentials part of an address in every top-level string of the result of `status`,
  `push` and `pull`.
- `validate` is called with a short limit of the frame (5 s, then `check-timeout`).
- `ctx["cache_dir"]` is a path, `~/.deai/cache/<space id>/<module id>`; the core does not create the folder, the module
  does.
- A transport, not a model of iterations: the iterations, the authorship and `iterations.json` stay in the core. The
  core reads the settings `repo`, `branch`, `path` and `autosync` of the module by name.

### Security

- The address, the branch, the folder, the key and the IP are checked before any `git` runs; every path goes after `--`
  with `GIT_LITERAL_PATHSPECS=1`, `GIT_ALLOW_PROTOCOL` is `ssh:https:file` (no `ext::` or `fd::`), the host and the user of
  a `user@host:path` address are plain names, the key is quoted.
- A password inside an address is refused — `https://user:pass@host/…` and the scp form `user:pass@host:path` (which
  reads as the host `user`): access lives in git, not in Deai. A `%` in the host or the user of an `ssh://` or `https://`
  address (`host%0a`, `us%20er`) is refused as well. An IPv6 host (`https://[::1]/x`) is accepted; only `<scheme>::…`
  (`ext::`, `fd::`) is a transport helper.
- A repository that is not the one the mirror was cloned from is never given the mirror's history: separate folders by
  the hash of the address, and a refusal where a folder is shared (the legacy space).
- No force-push, `pull --ff-only` only, a colleague's iteration is never sent, and a change under `<path>` on the remote
  stops a send.
- Symbolic links are not copied in either direction; a link on the way to `<path>` in a mirror is `vcs-error`.

### Known limits

- HTTPS without a sign-in saved in git: `vcs-auth` with a hint to set git up.
- The retry through `host_ip` covers only scp-style addresses (`[user@]host:path`), not `ssh://`, `https://`, `file://` or
  a local path.
- Windows was not checked on a real machine, as for the other modules.
- A regular space does not read the old `.mirrors` folder: its first status clones again into the cache.
- The `git push` of a task folder's local history (`git_autocommit`) is as it was: only in a space with integrations, and
  it is not part of the role.
- The `.gitignore` of the repository may silently keep mockup files out (for example `*.html`), as in 0.7.0; ignored
  leftovers of such a send come back with a pull.
- `status` for a branch that is missing on a non-empty remote, when the mirror is already cloned, gives zeros and
  `on_remote: null`; the error shows on the first send or pull.
- `.clone-*` folders stay after a killed process; a git `*.lock` in a mirror, after a process killed on a timeout, gives
  `vcs-busy` until it is removed by hand.
- The global `commit.gpgsign` and `core.hooksPath` of the person apply to the commits in a mirror; a failure is `vcs-error`.
- A token in the user position of an address (`https://TOKEN@host/…`) cannot be told from a name: it is accepted and sits
  in the task file in plain text, though it is hidden from every answer and text (and, in the legacy space, it appears in
  the name of the local mirror folder).
- Right after switching a task the status is asked before the page draws with an empty iteration, so the dot may say
  «ahead» until something refreshes it — as in 0.7.0.
- The worst path of «New task» with a retry through `host_ip` (a clone with `--branch`, a clone without it, `ls-remote`)
  can take longer than the 400 s ceiling: the form shows a timeout, and the task appears anyway.
- A hanging own module (`validate`, `check`) leaves a daemon thread until it returns; every new call adds one.
- The frame cuts the text of a `ModuleError` to 300 characters before the core masks an address, so an own module that
  puts an address with credentials exactly on that edge may leave the start of a token (`git-sync` masks its own texts).
- POST handlers outside `vcs` (`/api/it-*`, `/api/task-*`) do not check the type of string fields: a value that is not a
  string drops the connection instead of `400`. The routes of `vcs`, `gitlab` and `autosync` do check.

### Tests

`npm test` at 0.8.0 is green: 1890 node tests (plus `inspector-core`), 3056 Python tests in `tests/` (2 skipped), 168 in
`bin/`, 170 in `app/` (0.7.0: 1749, 2656 with 2 skipped, 168, 170). The three Python suites were also run on Python
3.9.6, the oldest supported version, with the same result (3056 with 2 skipped, 168, 170); `npm test` itself uses
Python 3.13. Nothing in the tests touches the network: git runs only on local bare repositories (an absolute path or
`file://`), and a transition over `ssh` or `https` goes through a stand-in for `subprocess.run`.

New: `tests/test_git_sync_module.py` (196 tests: the module on a real git — the checks of the target, the mirror folder,
the transport, the lock between processes, `status`, `push`, `pull`, `check`), `tests/test_vcs_core.py` (173: the core —
the target, the provider, the legacy space, a regular space, the routes and their aliases, `task-new` with `vcs`,
autosync) and `tests/vcs-client.test.mjs` (128: the bar, the palette, the section and the card of Connections, the field
of «New task», the error texts, the dictionary). The transport tests of `tests/test_gitlab_sync.py` moved into the file of
the module, the exact `capabilities` dicts of the other suites got the key `vcs`, and `tests/legacy-golden.test.mjs` is
untouched and green.

The live test `tests/live/git-sync.test.mjs` (a real server in an isolated machine, a real Chromium, a real git on a
local bare repository, 13 scenarios, ports 13700–13799, one file at a time) covers the ways that exist only in the whole:
a space without the role, the section and the card on Connections, a first send, a pull after a colleague's change,
autosync, «New task» with a repository, the legacy space unchanged, «Configure repository…» (also on a cold start), the
wizard step and a busy mirror; the map of every scenario to the line of the application it guards is in the header of the
file. `tests/live/gitlab-pull-older.test.mjs` runs on the new addresses.

## [0.7.0] — 23.10.2026

Stage 3c: a space's own modules and the trust dialog. A space can carry modules in `<space>/modules/<id>/`;
their code runs only after a person trusts exactly the bytes they saw. Design:
`docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`; plan:
`docs/superpowers/plans/2026-10-22-own-modules-trust.md`. The legacy space is unchanged
(`tests/legacy-golden.test.mjs` is green without a re-shoot).

### Added

- **Own modules** (`app/deai_modules.py`): `catalog(space)` adds the space's modules to the built-in ones. An
  untrusted module is listed from its manifest and never executed; a trusted one runs from a read-only snapshot
  (`<DEAI_HOME>/trusted/<fingerprint>/`) with a 5 s load timeout. Folder rules (200 files, 5 MiB, depth 8, no links
  or special files, safe names) and notes for skipped folders (`id-taken`, `too-many-modules`, `modules-link`,
  `modules-unreadable`). In `GET /api/modules` an own module carries `custom: true`, `builtin: false`, `trust` (`untrusted`,
  `trusted`, `changed`, `refused`), `record`, `runs`, `source` and, when there is a reason, `trust_error`, and `notes`
  lists the skipped folders; the entry of a built-in module and the answer for a space without own modules are
  byte-for-byte as before. New core error codes: `module-untrusted`,
  `module-changed`, `module-refused`, `trust-needs-ui`, `trust-declined`, `trust-no-confirm`, `trust-busy`,
  `trust-unreadable`.
- **Trust** (`app/module_trust.py`): scanner and fingerprint, `trust.json` records, snapshots, and the operating
  system's own confirmation window (macOS `osascript`, Windows message box, Linux `zenity`/`kdialog`) as the final
  word. API: `GET /api/module-trust`, `POST /api/module-trust` (only from the canvas page: `Origin` +
  `Sec-Fetch-Site: same-origin`), `POST /api/module-untrust`.
- **The trust dialog** (`app/trust-view.js`): the name, version, roles, the folder path (cut from the middle, the same
  way as in the system window), the fingerprint, what the module asks for (a secret is marked, and a secret that goes
  into pages is marked as public), every file with its size and, for a changed folder, marks of what changed since the last trust, and a
  «Removed» line (up to 10 names, then «and N more»). The focus is on «Cancel». For a folder that cannot be trusted the
  title is «“X” cannot be trusted» and there is no «Trust» button, only the reason.
- **Connections**: «own» tag, «Needs trust» badge, «Trust…» / «Why not…», trust lines («The folder has changes»…),
  notes under the head, «Revoke trust» in the panel and in the dialog.
- **Wizard**: on step 2 an own module has the «own» tag and «Trust…» in its row (the option stays disabled until
  trusted); step 3 shows a «waiting for trust» line, and writes nothing, for a module that a colleague turned on in
  `space.json`.
- `docs/modules/authoring.md` — writing your own module.

### Changed

- A role held «on paper» by an own module that is on in `space.json` but does not run here reports
  `module-untrusted`/`module-error` instead of falling back to the implicit `static-publish` or to the legacy path;
  `capabilities` gives `null` for it without `error`. Enabling an own module writes its `roles` into `space.json`.
- The comments adapter of an own module is served at `/api/module-client/<space>/<id>/<file>`, from its snapshot
  (the preview build takes the adapter files from the snapshot too).
- `README.md` and `docs/modules/comments.md` no longer say that only built-in modules load.

### Security

- Trust is bound to the bytes shown: changed folder → «changed», the old snapshot keeps running until re-trust.
- `POST /api/module-trust` is accepted only from the canvas page (`Origin` present and local, and
  `Sec-Fetch-Site: same-origin`); an agent or `curl` gets `403 trust-needs-ui`. This is a filter, not the boundary —
  a script in a mockup page sends the same headers — the boundary is the system window.
- After «No» in the system window, a repeat request for the same version within 30 s is refused without a window
  (`trust-declined`); only one window is open at a time (`trust-busy`).
- `DEAI_TRUST_CONFIRM` (`yes` / `no` / `unavailable`) is a test seam that answers the system window; it works only
  with a non-default `DEAI_HOME` (any other value, or the default home, means the real window), and the server prints
  a warning when it is on.

### Known limits

- No sandbox: a trusted module runs with your permissions.
- An agent that runs as you can still edit `~/.deai/trust.json` and `~/.deai/trusted/` or drive the system window itself
  — that is outside the boundary. Trust protects against code that arrives through the space folder, git and mockup
  pages, not against a local process with your rights.
- The Windows and Linux system windows are covered by command-building unit tests only; the macOS window was checked by
  hand (it was shown once and closed by itself with the answer «no», and quotes and a backslash in the module name
  arrived as they are).
- If an own module was turned on by hand in `space.json` (for example a colleague committed it) while another module
  still holds its role — for `publish`, typically the implicit «Publish to a folder» (`static-publish`) of a space
  without integrations — «Trust…» answers `role-taken` (for example `publish is already provided by static-publish`)
  before the system window opens. Turn the other card off first. Turning a module on through «Connections» never
  creates this state.
- A trusted module that hangs or loops at the top level is shown as broken after 5 s, but its thread lives until the
  server restarts and may slow the canvas down.
- Safari older than 16.4 does not send `Sec-Fetch-Site`.
- Snapshots replaced by a re-trust are not cleaned up (each up to 5 MiB, read-only, in `<DEAI_HOME>/trusted/`).
- On Windows the read-only modes of snapshots are not set (as for `secrets.json`).

### Tests

`npm test` at 0.7.0 is green: 1749 node tests (plus `inspector-core`), 2656 Python tests in `tests/` (2 skipped), 168 in
`bin/`, 170 in `app/` (0.6.0: 1630, 2381 with 1 skipped, 168, 170). The three Python suites were also run on Python
3.9.6, the oldest supported version, with the same result (2656 with 2 skipped, 168, 170); `npm test` itself uses
Python 3.13.

New: `tests/test_module_trust.py` (the scanner and its folder rules, the fingerprint, `trust.json` records, snapshots,
the command of the system window for each platform — the window itself is never shown), `tests/test_modules_own.py`
(own modules in the catalog: an untrusted one never runs, a trusted one runs from its snapshot, notes, the load timeout,
roles «on paper», `trust_view`, `grant_trust`, `revoke_trust`), `tests/test_modules_trust_api.py` (the HTTP routes, the
fields of an own module, `trust-needs-ui`, the adapter address with the space), `tests/trust-view.test.mjs`,
`tests/connections-own.test.mjs`, `tests/wizard-own.test.mjs` and `tests/trust-flow.test.mjs` (the dialog, the cards, the
wizard rows, and the behaviour of the wiring in `app.js` run with stand-in dependencies); the CSS, wiring and
dictionary tests were extended.

The live test `tests/live/own-modules.test.mjs` (a real server in an isolated machine, a real Chromium, 9 scenarios, one
file at a time; the system window is answered by `DEAI_TRUST_CONFIRM`) covers the whole way from an untrusted folder to
«Revoke trust», a refusal in the system window, a module that a colleague committed, «Trust…» in the wizard, a request
without the headers of a browser (and one with a forged `Origin`), a folder changed while the dialog is open, «Revoke
trust» from the dialog, a folder with a symbolic link, and a module that a colleague turned on in the folder of a space
being added. The guard of the real `~/.deai` in `tests/live/_spaces-kit.mjs` now also watches `trust.json` and the
contents of `trusted/`.

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

`npm test` at 0.6.0 is green: 1630 node tests (plus `inspector-core`), 2381 Python tests in
`tests/` (1 skipped), 168 in `bin/`, 170 in `app/` (0.5.0: 1458, 2349 with 1 skipped, 168, 170).
The three Python suites were also run on Python 3.9.6, the oldest supported version, with the same
result (2381 with 1 skipped, 168, 170); `npm test` itself uses Python 3.13.

New: unit tests `tests/wizard-model.test.mjs` (the choice per role, the plan of writes and its
order, freshness, the dependent switch-off, names from the folder; roles are data, so a role named
`__proto__` is an ordinary key), `tests/wizard-view.test.mjs` (every step, the hooks, `aria-current`,
`fieldset` and `legend`, everything from data is escaped, secret fields are empty, a failed save shows
one message in the card, not the reason twice),
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
