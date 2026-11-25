# Tasks
Tasks of a space: list, create, switch, rename, tags, trash.

A task is a folder with iterations. `/api/task` and the iteration calls of other topics act on one task: send the header
`X-Canvas-Task: <task-id>` (or prefix the path with `/t/<task-id>`); without it they act on the current task of this
computer. The calls that create, switch and change tasks (`task-new`, `task-switch`, `task-rename`, `task-tags`,
`task-delete`, `task-restore`, `task-purge`) name the task in the body, ignore the header and answer `400` to the
`/t/<task-id>/` prefix.

## Read

    GET http://127.0.0.1:8765/api/tasks
    GET http://127.0.0.1:8765/api/tasks?all=1

`{"current", "tasks": [{"id", "title", "jira", "track", "missing", "tags"}], "space"}`: the tasks of the current space, most
recent first. `?all=1` lists the tasks of all spaces, each row with a `space` id: use it to find out whether a task id
already exists. `missing: true` means the task folder is not on this computer.

    GET http://127.0.0.1:8765/api/task

The named (or current) task: `id`, `title`, `jira`, `tags`, `track`, `space`, `iterations`, `publish_url`, `published_at`,
`preview_password`, `comment_channel`. `404 no-task` when there is none.

## Create

    POST http://127.0.0.1:8765/api/task-new {"id": "<task-id>", "title": "<title>", "space": "<space-id>", "from": "/abs/path"}

`id`: letters, digits, `_` and `-`. `title` keeps 200 characters. `space` is the space id; without it the new task goes to the
default space of this computer, and `400 unknown-space` if the id is wrong. `from` is optional: an absolute path (or `~/…`)
of a folder with an `index.html`, which becomes the first iteration; otherwise a placeholder `index.html` is created.
Optional too: `tags` (a list of up to 10 strings of up to 32 characters), `track`, `jira`, and `vcs`
`{"repo", "path", "branch"}` for the git sync target (see the topic `vcs`).

Answer: `{"ok": true, "id", "dir", "space", "space_switched", …}` (and `copied` with `from`). The new task becomes the current
task and its space the current space. Refusals are `{"ok": false, "code", "error"}`: `task-exists` or `bad-task-id` (`400`),
`from-not-found`, `from-no-index` (`400`), `task-dir-exists` (`409`), `no-space` (`409`).

## Switch, rename, tags

    POST http://127.0.0.1:8765/api/task-switch {"id": "<task-id>"}
    POST http://127.0.0.1:8765/api/task-rename {"id": "<task-id>", "title": "<new title>"}
    POST http://127.0.0.1:8765/api/task-tags   {"id": "<task-id>", "tags": ["a", "b"]}

`task-switch` makes the task, and its space, the current one of this computer: answer `{"ok", "current", "space"}`, `404` for
an unknown task. It changes what the designer's canvas opens, so in parallel sessions name the task with the header instead.
`task-rename` changes only the title (`400 bad-title` when empty; the id and the folder stay). `task-tags` replaces the whole
list (`[]` clears it; `400 bad-tags`); answer `{"ok", "tags"}`.

## Trash

    POST http://127.0.0.1:8765/api/task-delete  {"id": "<task-id>"}
    POST http://127.0.0.1:8765/api/task-restore {"id": "<task-id>", "space": "<space-id>"}
    POST http://127.0.0.1:8765/api/task-purge   {"id": "<task-id>", "space": "<space-id>"}

`task-delete` moves the task folder to the trash of its space: answer `{"ok", "id", "current", "trash"}`; if it was the
current task, `current` moves to another one. `task-restore` brings it back (`404 not-in-trash`, `409 task-exists`,
`409 task-dir-exists`). `task-purge` deletes it for good and cannot be undone.

## Where we are

    python3 <deai>/bin/state.py
    python3 <deai>/bin/state.py --task <task-id>

Run it when you enter a task: it prints the iterations (which is the latest, which is published), the publication, the git
sync state and the open comments, so that you continue the work instead of starting a mockup from scratch. `--task` names
the task instead of the current one (use it when several sessions work in parallel).

## Links

Give the owner a link to a place in the canvas: space, task, iteration, page, mode — «here is where I worked».

The canvas window keeps its current place in the address, so a place can be shared as a link and the canvas opens right
there. The address is `/app/` of the running Deai plus a hash:

    http://127.0.0.1:8765/app/#sp=<space-id>&t=<task-id>&it=<iteration-id>&p=<page-id>

Keys (all optional; unknown keys are ignored; every value goes through `encodeURIComponent`):

- `sp=` the space id (`GET /api/spaces`); `t=` the task id (`GET /api/tasks?all=1`); `it=` the iteration id, e.g. `it2`;
- `p=` the page id from the iteration's `pages.json` (the same key as in a published preview link `#p=<page-id>`);
- `st=` a state of the page, only together with `p=`;
- `m=o` — «Огляд» (the overview canvas); without `m` it is «Макет». `v=flow` — the flow view of the overview, only with `m=o`;
- `h=tasks` or `h=settings` — the «Задачі» screen or the settings over the task.

Opening a link switches the canvas to the task in it. A reload or a restored (back/forward) tab follows the server's current
task instead if the task in the link is no longer the current one (it was switched by an agent, the CLI or another window):
only the view (`m`, `v`, `h`) is kept. A link with only `sp=` (no `t=`) does not switch the space. A task in a space that
cannot be read right now leaves the canvas at its usual place. An unknown task opens the current task at its usual place (the
last iteration, the first page), and `m`, `v`, `h` of that link are dropped too; an unknown iteration or page falls back to the
nearest one. Compose the link from ids you read through the API, never from names; the port is the one Deai runs on (default 8765).
