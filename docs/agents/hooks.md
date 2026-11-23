# Hooks
Agent heartbeat for the island and the git autosync step of a Stop hook.

Hooks of your own agent (for example the Stop hook of Claude Code) can call two canvas routes. Add hooks only when the person
asks for it (`SETUP.md` in `<deai>`, section «Agent status»): nothing else in the canvas depends on them.
The same section has a `SessionStart` hook that prints the live guide (`GET /api/agent-guide`) at the start of a Claude Code session.

## The Stop hook the canvas installs

The person presses «Підключити» in Settings → AGENTS.md, row «Claude Code» (the button then reads «Оновити» or «Відключити»).
The canvas writes ONE Stop hook into `<space>/.claude/settings.local.json`: Claude Code's per-user, local file (Claude Code
git-ignores it when it creates it; when the canvas creates it in a repository root it adds one line to `.git/info/exclude`).
It never touches the team's `.claude/settings.json` or `~/.claude/settings.json`. The entry is merged into `hooks.Stop`; the
command ends with the mark `# deai-autosync`, which is how the canvas recognises its own entry. Foreign hooks and other keys are
never changed. The command (timeout 10):

    curl -s --noproxy '*' --max-time 5 -o /dev/null -X POST -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:<port>/api/autosync || true # deai-autosync

After every reply Claude Code pipes a JSON to the hook's stdin; the canvas reads only `cwd` from it. The hook is silent and never
blocks Claude: `-o /dev/null` drops the body, curl (without `--fail`) exits 0 even on `413`, and `|| true` covers transport
failures (canvas stopped, 5 s timeout, connection reset). `<port>` is the port of the canvas that was running when the button was
pressed. Do not write this hook by hand: ask the person to press the button.

States of the row: ok; missing; stale (the hook points at another canvas port: the canvas moved ports, or two canvases on
different ports serve one space; «Оновити» fixes it); unreadable (the file cannot be merged safely: invalid JSON, duplicate keys,
NaN/Infinity, a symlink or a non-regular file; it is left alone); elsewhere (the space folder is inside another git repository,
so Claude Code reads that repository's root settings; no hook is installed). «Відключити» removes only our entry (an emptied file
the canvas created is deleted). A canvas restart changes nothing.

Limits: Claude Code started INSIDE a task folder (each task folder is its own git repository) reads that repository's
`.claude/settings.local.json`, so the hook does not fire there: start Claude Code in the space folder. Only Claude Code and only
this one file are covered: no team or global settings, no other agents, no automatic install at canvas start. For agents
without the hook use the manual call below (`POST /api/autosync {}` with `X-Canvas-Task`; see `AGENTS.md`).

When Claude ends a reply, every own changed iteration of every task of the space is committed as `itN: зміни AI` (see
«Autosync by folder» below). A change a person makes outside the canvas in the same minute is committed as AI too.

## Heartbeat

    POST http://127.0.0.1:8765/api/claude-status {"task": "<task-id>", "phase": "design", "status": "in_progress", "note": "…", "session": "<session id>"}
    GET  http://127.0.0.1:8765/api/claude-status
    GET  http://127.0.0.1:8765/api/claude-statuses

The island of the canvas shows what the agent does only from these heartbeats. `task` is the task id (or its Jira key), up to
200 characters. `phase` is one of `understanding`, `design`, `dev`, `checks`, `fixation`. `status` is `in_progress`,
`waiting`, `blocked` or `done`. `note` and `session` are optional strings of up to 200 characters; heartbeats are kept per
`session` (else per `task`), the last 50 sessions. The server stamps the time itself. Answer `{"ok": true}`; a malformed
heartbeat is `400 bad heartbeat`, a request from another site `403`.

A heartbeat expires: `in_progress` after 3 minutes, `done` after 10, `waiting` and `blocked` after 30; send a new one to keep
the status. It lives in memory only, so a canvas restart forgets it.

`GET /api/claude-status` answers for the task named by `X-Canvas-Task` (or the current one): `{"state": "working" | "waiting" |
"blocked" | "done" | null, "phase", "note", "age_s"}`; `state` is `null` when there is no fresh heartbeat.
`GET /api/claude-statuses` lists all tasks with a fresh heartbeat: `{"tasks": {"<task-id>": {"state", "age_s"}}}`; it does not
take the task header (or the prefix).

## Autosync

    POST http://127.0.0.1:8765/api/autosync {}

The quiet step of a Stop hook, with the `vcs` role (topic `vcs`). It does two things, in this order:

1. Always, even with autosync off or without a `vcs` role: it commits each of this computer's own changed iterations of the
   task as its own local commit `itN: зміни AI` with the trailer `Deai-Actor: ai`, touching only `iterations/<itN>/`
   (colleagues' iterations and other files stay uncommitted). It never pushes. A task folder without `.git` gets no AI
   commit. The answer carries it as `ai`: `{"it", "sha", "its"}` (the newest commit and every iteration committed) or
   `null` when nothing was committed.
2. Then it sends your newest own iteration to the repository when it changed since the last send. It never answers with a
   server error.

When nothing is sent the answer is `{"ok": true, "changed": false, "reason": …, "ai": …}`: `no-gitlab` (no `vcs` role or no
repository for the task), `autosync-off` (the module's «Send after every agent reply» is off: nothing is sent, but the
local AI commit of step 1 is still made), `no-iterations`, `foreign-only` (only colleagues' iterations), `clean` (nothing
new). A failed send is `reason: "offline"` (usually the network; with a `code` when the module gave one), and
`reason: "error"` is a local failure (unreadable task files, permissions): it is written to the server log, and the Stop
hook reports it instead of staying silent. When a send happens the answer is the result of the send, as for
`POST /api/vcs-push`, plus `it`, `local_sha` and `ai`. The task is named by `X-Canvas-Task`, as everywhere; without it, the
current one.

### Autosync by folder

    POST http://127.0.0.1:8765/api/autosync {"cwd": "/absolute/path/inside/the/space"}

Without `X-Canvas-Task` (or the `/t/<task-id>` prefix) and with a JSON body containing `cwd`, the canvas finds the space by the
longest matching registered folder (Claude Code may have started anywhere inside it) and commits the own changed iterations of
EVERY task of that space that has a `.git` as `itN: зміни AI` with the `Deai-Actor: ai` trailer (a failure in one task is logged,
the rest go on). The push step then runs only for the space's CURRENT task, as above. The answer has the fields of that step
plus `ai` (the current task's AI commit) and `ai_tasks`: `{"<task-id>": {"it", "sha", "its"}}` for every task where something was
committed (`{}` when nothing was). `reason: "no-space"` means `cwd` is in no registered space and nothing is done;
`reason: "no-task"` means the space has no current task (the AI commits of the other tasks were still made). With `X-Canvas-Task`
or the prefix the behaviour is the old one and the header wins over `cwd`. Concurrent calls (for example another Stop hook
firing at the same moment) are serialised per task folder. Only `cwd` is read from the body, nothing of it is kept; a body over
2 MiB is `413 body-too-large`, answered before reading.
