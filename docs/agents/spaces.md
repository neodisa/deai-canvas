# Spaces
Spaces of this computer: list, create, rename, switch, tools, AGENTS.md and CLAUDE.md.

A space is a folder with `space.json` (name, colour, enabled modules and their settings), its tasks in `tasks.json` and,
optionally, its own modules. The calls here act on the machine, not on a task: the task header is ignored and the
`/t/<task-id>/` prefix is `400`.

## List, peek, create

    GET  http://127.0.0.1:8765/api/spaces
    GET  http://127.0.0.1:8765/api/space-peek?path=/abs/folder
    POST http://127.0.0.1:8765/api/space-new {"name": "Personal", "color": "space-1", "path": "/abs/folder"}

`spaces` answers `{"current", "spaces": [{"id", "name", "color", "path", "tasks", "available", "capabilities", "tools",
"tracks", …}]}`; with the spaces layer off `{"current": null, "spaces": [], "off": true}`. `space-peek` tells what lies in a
folder before you make a space of it: `{"path", "exists", "registered"?, "name"?, "color"?, "tasks"?}`. `space-new` takes the
name (up to 60 characters) and one of the colours `space-1` … `space-6`, makes the folder with `space.json` and `tasks.json`
(an existing space folder is adopted), registers it, makes it current and writes `AGENTS.md` and `CLAUDE.md` into it;
answer `{"ok": true, "id"}`. A folder that is already a space is refused (`path-registered`, `409`).

## Rename, switch, tools

    POST http://127.0.0.1:8765/api/space-update {"id": "<id>", "name": "New name", "color": "space-2"}
    POST http://127.0.0.1:8765/api/space-switch {"id": "<id>"}
    POST http://127.0.0.1:8765/api/space-tool   {"space": "<id>", "tool": "figma", "on": false}

`space-update` changes name and colour, keeps the rest of `space.json`; answer `{"ok", "id", "name", "color"}`.
`space-switch` makes the space current: `{"ok": true, "current", "task"}` (`task` is its current task or `null`).
`space-tool` turns a tool of the space on or off (`figma` is the only one): `{"ok", "space", "tools"}`. Refusals are
`{"ok": false, "code", "error"}`: `unknown-space` `404`, `name-required`, `unknown-tool`, `bad-value` `400`, `spaces-off` `409`.

## AGENTS.md and CLAUDE.md

    GET  http://127.0.0.1:8765/api/agents-md?space=<id>
    POST http://127.0.0.1:8765/api/agents-md {"space": "<id>"}
    POST http://127.0.0.1:8765/api/agents-md {"space": "<id>", "claude": true}

`GET` reports the state of the space's `AGENTS.md` (`exists`, `hasBlock`, `outdated`, `newer`, the text) and of `CLAUDE.md`
(`claude.state`: `ok`, `missing`, `no-import`, `unreadable`), plus `paths` of this installation: `deai`, `inbox`, `authoring`, `agents`.
`POST` creates or updates the generated block between the `deai:begin` and `deai:end` markers and keeps your text around it
byte for byte; when it creates `AGENTS.md` it also creates `CLAUDE.md` with the line `@AGENTS.md` if there is none.
With `"claude": true` it only connects `CLAUDE.md` (adds `@AGENTS.md` at the top, or creates the file) and leaves `AGENTS.md`
alone. Refusals: `409 no-folder` (no real folder), `409 newer` (the file comes from a newer Deai Canvas, never downgraded),
`409 changed`, `503 unreadable`. The block refreshes itself when the canvas starts if it is stale; a file or a block that is
absent is not created, and a block the person removed is not put back.

## The live guide

    GET http://127.0.0.1:8765/api/agent-guide?path=/abs/folder&have=<guide mark>
    GET http://127.0.0.1:8765/api/agent-guide?topic=<topic>
    GET http://127.0.0.1:8765/api/agent-guide?space=<id>&format=json

Answers in markdown (`format=json` gives an object). Without `topic`: the `guide` mark of this canvas, its version, the
space (`space` id, or the one whose folder holds `path`, or the current one) with the state of its `AGENTS.md`, the current
task, enabled modules, own modules (only the path of their `agent.md`), the topics, and the current block. `have` is the
`(guide xxxxxxxx)` mark of your AGENTS.md block: if it equals the canvas's, the block is current; otherwise the answer says
it is outdated and carries the current block: follow that. With `topic`: the text of that topic (`404 unknown-topic`);
with `format=json` `{"ok", "topic", "text"}`. Read-only; a request from another site is `403`.
