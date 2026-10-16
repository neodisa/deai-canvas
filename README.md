# Deai Canvas

**A local workspace for prototypes made with AI.** An agent (Claude Code or any other)
writes HTML mockups; Deai Canvas turns them into something you can review and ship:
iterations, a bird's-eye overview of every screen, user-flow maps, a design-token
inspector, comments addressed straight to the agent, and password-protected preview
links for your team.

> **Status — v0.2.0 (private; extracted from an in-house tool, source 1.55.0 @ `796b3df`).**
> Spaces (several projects on one machine) and the first **modules** are in: publishing to
> a folder and design-system tokens from a CSS file work in any space. A few integrations
> (team dashboard, git sync, shared comments, Vercel publishing) are still wired for the
> original setup and only run in a migrated legacy space; they are being turned into
> optional per-space modules with a first-run onboarding. See *Roadmap*.

## What it does

| | |
|---|---|
| **Iterations** | Every iteration is a frozen, editable copy of the mockup; compare, rename, duplicate. |
| **Pages & states** | A tree of pages, folders and states (any depth), with a filter and drag-and-drop. |
| **Overview** | All pages of an iteration as a zoomable grid of full-page snapshots (Playwright), re-shot incrementally when a page changes. Desktop / tablet / mobile widths. |
| **Flow** | Arrange screens as a user flow with arrows (`flow.json`). |
| **Inspector & tuner** | DevTools-style overlay: spacing, typography, colours, a ruler, and — if you connect your design tokens (a CSS file, see *Modules*) — whether each value is on-system. The tuner turns tweaks into a change request for the agent. |
| **Comments** | Pin comments on any element (via [CommentLayer](https://github.com/neodisa/CommentLayer)); a local channel for the agent, an optional shared channel for the team. |
| **Agent status** | Shows what the agent is doing right now and which pages it just changed. |
| **Publish** | Build a static preview of the iterations you marked and publish it to a folder (any space), optionally behind a password gate. Vercel only in a legacy space for now. |
| **Tasks** | A home screen with all your tasks: search, sort, filters. |
| **App** | Installable as a PWA (own window and Dock/taskbar icon); macOS launcher with auto-start. |

UI in English and Ukrainian.

## Quick start

Requirements: Python 3.9+, Chrome or Edge. Optional: Node.js (snapshots via Playwright,
publishing via the Vercel CLI).

```bash
cp tasks.example.json tasks.json      # edit paths: where your mockups live
python3 app/serve.py                  # http://localhost:8765/app/
```

Each task points to a folder with `iterations/it1/<page>/index.html`; `flows/demo` is a
small example. Snapshots for the Overview:

```bash
npm install && npx playwright install chromium
```

Tests: `npm test` (unit, Python) and `npm run test:live` (real Chromium).

## Modules

A **module** is a folder `app/modules/<id>/` with `module.json` (manifest and the settings
it asks for) and `server.py` (functions for its role). A *role* is an interface the core
calls: `publish` and `tokens` today; `comments`, `vcs`, `tracker`, `dashboard`, `notify`
are reserved. One provider per role per space. In 0.2 only built-in modules exist; a
space's own modules and a UI for connecting them come with stage 3, so for now you manage
modules over the HTTP API (the agent can do it for you).

Settings and on/off live in the space's `space.json`; **secrets** go to
`~/.deai/secrets.json` (user-only permissions), never into the space folder, so the folder
stays safe to commit. Secrets are not encrypted.

| Module | Role | What it does |
|---|---|---|
| `static-publish` | `publish` | Builds the preview and publishes it to a folder, by default `~/deai-published/<space-id>/<task>/` — outside the space. On by default in a space without integrations. Optional `password` secret adds a client-side gate. |
| `css-tokens` | `tokens` | Reads design tokens from one CSS file so the inspector can tell on-system values from hard-coded ones. Setting: `file`. |

**Publishing to a folder.** Mark iterations with the green dot, press *Publish*: the
result is a plain static site in the folder (host it anywhere; the task id must be
`A–Z a–z 0–9 _ -`, up to 128 characters). The canvas also serves a
sandboxed local copy at `http://localhost:8765/published/<space-id>/<task>/`. The folder
is re-checked on every publish and serve; it must not be your home folder, the tool or
space folders, or a system folder, and a folder without the `.deai-published` marker is
never overwritten.

**Tokens from CSS.** A token is a `--name: value` declaration in a `:root`, `html` or
`[data-*theme*]` rule (Bootstrap `[data-bs-theme=dark]` too) or directly in Tailwind v4
`@theme { … }`. Values are collected per name (themes, media), `var()` is resolved within
the file, `@import` is not followed; the file must be a regular file up to 2 MiB.

**Module API.**

| Call | |
|---|---|
| `GET /api/modules?space=<id>` | catalog with status and settings; secrets only as `set: true\|false` |
| `POST /api/module-enable` `{space?, id, settings?, secrets?}` | enable and configure; answers `{ok, module, check}` — `ok` means «processed», `check.ok` is the verdict |
| `POST /api/module-settings` `{space?, id, settings?, secrets?}` | change settings or secrets (omit a key to keep it, `null` deletes) |
| `POST /api/module-disable` `{space?, id}` | turn off; settings and secrets are kept |
| `POST /api/module-check` `{space?, id}` | run the module's `check` |
| `GET /api/ds-tokens?space=<id>` | the space's tokens, as the inspector reads them |
| `GET /published/<space-id>/<task>/…` | the local copy of a published preview |

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

Design and deviations from the spec: `docs/superpowers/specs/2026-10-14-modules-2a-design.md`.
Direction: `docs/design/spaces-and-modules.md`. Release notes: `CHANGELOG.md`.

## Layout

```
app/          server (serve.py, stdlib only) + UI (ES modules, no build step)
app/modules/  built-in modules (static-publish, css-tokens); the core is app/deai_modules.py
bin/          CLI tools: snapshots, pages, state, inbox
ops/          macOS launcher (Design Canvas.app), preview gate tools
flows/demo    example flow
tests/        unit, Python and live (Playwright) tests
```

## Roadmap

1. ✅ **Spaces** (0.1) — several projects/companies on one machine, each with its own task list and settings.
2. **Modules**
   - ✅ **2a** (0.2) — module framework, publishing to a folder, design-system tokens from CSS.
   - **2b** — your own Vercel (publish) and your own Supabase (shared comments) as modules.
   - Later — git sync, team dashboard, issue tracker, notifications: modules you connect per project.
3. **Onboarding** — a first-run flow that sets up a project and connects modules from the UI;
   a Connections screen; a space's own modules, loaded only after you trust them.
4. **Claude Code plugin** — a generic task → mockup → iterations → review → publish loop.
5. **Cross-platform start** — one command on macOS, Windows and Linux.

## License

MIT © Sergey Arkhipov
