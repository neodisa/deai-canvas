# Deai Canvas

**A local workspace for prototypes made with AI.** An agent (Claude Code or any other)
writes HTML mockups; Deai Canvas turns them into something you can review and ship:
iterations, a bird's-eye overview of every screen, user-flow maps, a design-token
inspector, comments addressed straight to the agent, and password-protected preview
links for your team.

> **Status — v0.1.0 (private; extracted from an in-house tool, source 1.55.0 @ `796b3df`).**
> Spaces are in (several projects on one machine, each with its own task list). A few
> integrations (team dashboard, git sync, shared comments, Vercel publishing) are still
> wired for the original setup and only run in a migrated legacy space; they are being
> turned into optional per-space modules with a first-run onboarding. See *Roadmap*.

## What it does

| | |
|---|---|
| **Iterations** | Every iteration is a frozen, editable copy of the mockup; compare, rename, duplicate. |
| **Pages & states** | A tree of pages, folders and states (any depth), with a filter and drag-and-drop. |
| **Overview** | All pages of an iteration as a zoomable grid of full-page snapshots (Playwright), re-shot incrementally when a page changes. Desktop / tablet / mobile widths. |
| **Flow** | Arrange screens as a user flow with arrows (`flow.json`). |
| **Inspector & tuner** | DevTools-style overlay: spacing, typography, colours, a ruler, and — if you plug in your design tokens — whether each value is on-system. The tuner turns tweaks into a change request for the agent. |
| **Comments** | Pin comments on any element (via [CommentLayer](https://github.com/neodisa/CommentLayer)); a local channel for the agent, an optional shared channel for the team. |
| **Agent status** | Shows what the agent is doing right now and which pages it just changed. |
| **Publish** | Build a static, password-gated preview of all iterations (Vercel today). |
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

## Layout

```
app/        server (serve.py, stdlib only) + UI (ES modules, no build step)
bin/        CLI tools: snapshots, pages, state, inbox
ops/        macOS launcher (Design Canvas.app), preview gate tools
flows/demo  example flow
tests/      unit, Python and live (Playwright) tests
```

## Roadmap

1. ✅ **Spaces** (0.1) — several projects/companies on one machine, each with its own task list and settings.
2. **Modules** — git sync, shared comments backend, publishing target, design-system tokens,
   issue tracker, team dashboard: optional modules you connect per project.
3. **Onboarding** — a first-run flow that sets up a project and connects modules from the UI.
4. **Claude Code plugin** — a generic task → mockup → iterations → review → publish loop.
5. **Cross-platform start** — one command on macOS, Windows and Linux.

## License

MIT © Sergey Arkhipov
