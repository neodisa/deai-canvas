# Hooks
Agent heartbeat for the island and the git autosync step of a Stop hook.

Hooks of your own agent (for example the Stop hook of Claude Code) can call two canvas routes. Add hooks only when the person
asks for it (`SETUP.md` in `<deai>`, section «Agent status»): nothing else in the canvas depends on them.

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
`GET /api/claude-statuses` lists all tasks with a fresh heartbeat: `{"tasks": {"<task>": {"state", "age_s"}}}`; it does not
take the task header (or the prefix).

## Autosync

    POST http://127.0.0.1:8765/api/autosync {}

The quiet step of a Stop hook, with the `vcs` role (topic `vcs`): it commits the task folder locally and sends your newest
own iteration to the repository when it changed since the last send. It never answers with a server error. When nothing is
sent the answer is `{"ok": true, "changed": false, "reason": …}`: `no-gitlab` (no `vcs` role or no repository for the task),
`autosync-off` (the module's «Send after every agent reply» is off; nothing is sent or committed), `no-iterations`,
`foreign-only` (only colleagues' iterations), `clean` (nothing new). A failed send is `reason: "offline"` (usually the
network; with a `code` when the module gave one), and `reason: "error"` is a local failure (unreadable task files,
permissions): it is written to the server log, and the Stop hook reports it instead of staying silent. When a send happens the answer is the result of the send, as for `POST /api/vcs-push`,
plus `it` and `local_sha`. The task is named by `X-Canvas-Task`, as everywhere; without it, the current one.
