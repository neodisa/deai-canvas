# Spaces, modules and onboarding — design (draft)

Status: agreed direction, 2026-10-09. Clickable prototype reviewed by the owner.
Next step: a detailed spec for stage 1 (spaces + migration).

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
  | Team comments (`comments`) | Supabase (your own project), via CommentLayer |
  | Publish previews (`publish`) | Static folder (always available), Vercel |
  | Design-system tokens (`tokens`) | CSS custom properties file or npm package |
  | Issue tracker (`tracker`) | Jira, Linear |
  | Team dashboard (`dashboard`) | — |
  | Notifications (`notify`) | — |

- Built-in modules ship in `app/modules/`; a space's own modules live in
  `<space>/modules/` and are loaded the same way. A module may implement an existing role
  (e.g. publish to Netlify) or add its own integration (e.g. notifications to a chat).
- **Nothing is required.** Without modules the canvas works fully: local comments for
  the agent, publishing into a folder, the inspector without a design system.

## Onboarding

- **First run** (no spaces): a wizard — space name, colour and folder → pick modules by
  role → settings with «Check» → first task (new / adopt an existing folder of HTML /
  let the agent create it).
- **Connections** screen per space: module cards with status (connected / error with the
  reason / off), configure in a side panel (secrets marked as stored outside the space),
  check, disable.
- **Agent**: the same operations over the HTTP API, so you can ask the agent
  «connect my GitHub repo and the tokens from this CSS file to space X».

## Stages

1. Spaces + migration of the existing `tasks.json`.
2. Module system: extract built-in modules from the integrations that are hard-wired today
   (git sync, Supabase comments, Vercel publishing, design tokens, tracker statuses).
3. Onboarding wizard + Connections screen.
4. Company-specific integrations move out of the core into that company's space modules.
5. Agent API + a lightweight Claude Code plugin (task → mockup → iterations → review → publish).

Each stage gets its own spec, plan and tests.
