# Setting up Deai Canvas — instructions for an AI agent

You are helping a person install and set up Deai Canvas on their computer. Follow the steps in order and check the result
after every step. Talk to the person in their language; keep messages short.

## Rules

- Ask before installing system software (Xcode Command Line Tools, Node.js, Homebrew). Use `sudo` only with the person's consent.
- Passwords and tokens come only from the person and go only into the `secrets` field of the module API. Never invent them,
  never repeat them back, never write them into files.
- Do not edit files inside the Deai Canvas folder. Updates are installed from the canvas (Settings → Updates).
- If `GET <api>/api/setup` already answers, Deai Canvas is installed and running: skip steps 2–5.
- `<api>` is the address named in the prompt, if the prompt names one (the welcome screen's prompt does); otherwise `http://127.0.0.1:8765`. Send JSON bodies with `Content-Type: application/json`.

## Steps

### 1. Check the computer

`git --version`; `python3 --version` (3.9 or newer); Google Chrome or Microsoft Edge is installed; `node --version` (20 or
newer). Node is optional: without it the Overview screenshots and the "System Vercel CLI" login do not work. If something
required is missing, tell the person what and how to install it, and ask before doing it.

### 2. Get the code

`git clone https://github.com/neodisa/deai-canvas.git ~/deai-canvas` — or into the folder the person named. If the folder
already exists and is a Deai Canvas checkout, use it as it is. Below, `<deai>` is that folder.

### 3. Screenshots for Overview

In `<deai>`: `npm ci && npx playwright install chromium`. No Node — tell the person and go on.

### 4. App icon and autostart (macOS)

`bash <deai>/ops/canvas-app/install.sh`, then check it: `bash <deai>/ops/canvas-app/install.sh --check`.

### 5. Start

Run `<deai>/start.command`. Wait until `GET <api>/api/setup` answers (up to 30 seconds).

### 6. Check

`GET /api/setup` → `shots.state` should be `ok`. Otherwise tell the person why: `no-node` — Node.js 20+ is needed;
`no-playwright` or `no-browser` — run `shots.command`; `unknown` — the check itself failed, go on.

### 7. Ask once

Send ONE message with four questions; each has a default the person can accept with one word:

1. Space name and folder — default: "Personal", `~/deai-work/personal`.
2. Where to publish previews — a folder on this computer (default) or their own Vercel.
3. One password for the previews of all tasks in the space — default: no password.
4. A git repository for the mockups — default: later.

### 8. Create the space

`POST /api/space-new {"name": "…", "color": "space-1", "path": "…"}` → `{ok, id}`. The canvas puts `AGENTS.md` and
`CLAUDE.md` (the line `@AGENTS.md`, so Claude Code reads `AGENTS.md`) into the folder. If the folder already is a space,
the canvas picks it up.

### 9. Modules

The fields of every module: `GET /api/modules?space=<id>`.

- Publishing to a folder: `POST /api/module-enable {"space": "<id>", "id": "static-publish"}`; the password —
  `POST /api/module-settings {"space": "<id>", "id": "static-publish", "secrets": {"password": "…"}}`.
- Publishing to Vercel: every new space already publishes to a folder (`static-publish` holds the `publish` role), so enable
  Vercel with `replace: true` — one call: `POST /api/module-enable {"space": "<id>", "id": "vercel-publish", "replace": true, "secrets": {"token": "…", "password": "…"}, "settings": {"auth": "token", "team": "…"}}`.
  Send only what the person gave: `token` is the Vercel token, `password` the preview password, `team` a Vercel team slug
  (empty — personal account); `auth` is `token` (default) or `cli` (system Vercel CLI, needs Node). The person can type the
  token in themselves: Settings → Modules → Vercel; then enable with `replace: true` and no token.
- Git: `git-sync` with the repository the person gave — `module-enable`, then `module-settings`.

After each module: `POST /api/module-check {"space": "<id>", "id": "…"}`, and tell the person the result.

### 10. Demo task

`POST /api/demo-task {"space": "<id>", "reuse": true}` → `{ok, id, space[, existed]}` (`reuse` — a retry does not create a second demo): a made-up budgeting app "Tally" with five pages, two states, a flow
and two pins — to try Overview, comments and the inspector without an agent.

### 11. Open the canvas

If the icon is installed: `open -a "Design Canvas"`. Otherwise: `open http://localhost:8765/app/` — or `<api>/app/` when the
prompt named another address (the icon opens `localhost` too, so the browser keeps one set of preferences).

### 12. The last message

Tell the person:

- what is done and what is not (with the reason);
- what is where, in 5–6 lines: task tabs at the top; the bar with Layout, Overview, Flow and Publish; the page tree on the
  left; the island at the bottom with comments (C), the inspector (I) and bug or idea; ⌘K for every action;
- how to work next: `cd <space folder> && claude`, then phrases like "make a payment screen" or "work through the comments";
- ⌘K → "Canvas tour" shows the map again.

## Agent status

The island shows what the agent is doing only from a heartbeat: `POST /api/claude-status {"task", "phase", "status",
"note", "session"}`. Without it everything else works. Add hooks that send it to the person's Claude Code only if the
person asks for it.

Agents read `AGENTS.md` once, when a session starts. To also give Claude Code the live state of the canvas (the space,
the current task, modules, and the current guide when the file is out of date), add a `SessionStart` hook — again only if
the person asks for it — to `.claude/settings.json` of the space folder (merge it into existing `hooks` instead of
replacing the file):

```json
{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "curl -sfG --max-time 2 http://127.0.0.1:8765/api/agent-guide --data-urlencode \"path=$CLAUDE_PROJECT_DIR\" -d \"have=$(grep -o 'guide [0-9a-f]\\{8\\}' \"$CLAUDE_PROJECT_DIR/AGENTS.md\" 2>/dev/null | head -1 | cut -c7-)\" || true"}]}]}}
```

Claude Code adds what the hook prints to the session's context; with the canvas stopped the hook prints nothing.
`$CLAUDE_PROJECT_DIR` is the folder the session started in, so the hook works from any working directory.
