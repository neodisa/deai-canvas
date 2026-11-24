# Iterations
Versions of a task: create, rename, delete and restore, history, list pages, turn iterations into pages.

Every call here acts on one task: send the header `X-Canvas-Task: <task-id>` (or prefix the path with `/t/<task-id>`).
Without it the call acts on the current task of this computer.

## Create

    POST http://127.0.0.1:8765/api/iteration {"from": "itN", "note": "what this iteration is"}

Copies `itN` into the next number; without a known `from` it creates an empty iteration with an `index.html`. `note` keeps
up to 300 characters. Answer: `{"ok": true, "iteration": {"id": "itM", "date": …, "note": …, "published": false,
"from": "itN"}, "git": {…}}` (`from` only when a source was copied). A folder created by hand is not registered and does
not show in the canvas.

## Rename

    POST http://127.0.0.1:8765/api/iteration-rename {"id": "itN", "label": "Category", "note": "full note"}

`label` (up to 40 characters) is the short name on the pill; an empty `label` brings back «It.N». `note` (up to 300) is the
full note. Either key may be left out. Answer: `{"ok": true, "id", "label", "note"}`; `404` for an unknown id. Labels help
when the iterations of a task are different pages rather than versions.

## Delete

    POST http://127.0.0.1:8765/api/iteration-delete {"id": "itN"}

A soft delete: the iteration's folder and its entry move to the task's trash (`.trash/iterations/` in the task folder,
outside git) and are kept at least 7 days: the next delete in this task erases the slots older than that. Answer
`{"ok": true, "deleted": "itN", "trash": "<slot>"}`; keep `<slot>` to restore it (or read it from `iteration_trash`, below).
`404` for an unknown id; `409 {"ok": false, "error": "last-iteration"}` when it is the only iteration of the task (a task
is never left without one). The task's git history records `delete iteration itN`.

## Restore

    POST http://127.0.0.1:8765/api/iteration-restore {"trash": "<slot>"}

Brings an iteration back from the trash. Answer `{"ok": true, "id", "renamed", "iteration": {…}}`: when its old id is taken
by another iteration, it returns under the next free number and `renamed` is `true`. `404 {"error": "not-in-trash"}` for a
slot that is not in the trash (restored already, or erased by a later delete), `400` for a malformed slot. Reading the trash
does not erase anything; a slot older than 7 days that no delete has erased yet can still be restored by its `<slot>`. The task's git history records
`restore iteration itN`.

## The trash list

    GET http://127.0.0.1:8765/api/task   → "iteration_trash": [{"trash": "<slot>", "id": "itN", "label_text": "…", "deleted_at": "…Z", "expires_at": "…Z"}]

Deleted iterations of the task, newest first (`label_text` is the pill text, `deleted_at` / `expires_at` are UTC, `expires_at`
is 7 days later; `trash` is the `<slot>` for `iteration-restore`). Slots past `expires_at`, without a readable record or with
an unsafe id are left out; `[]` when the trash is empty or cannot be read. The designer sees the list as «Видалені» at the
bottom of the iteration list (and as «Видалені ітерації» in ⌘K, only when the trash is not empty).

## History

    GET http://127.0.0.1:8765/api/iteration-history?id=itN

The change history of one iteration, read from the task folder's git: `{"ok": true, "id", "entries": […], "pending": …,
"degraded": false}`. `entries` come newest first (up to 300 commits are read); each is `{"sha", "at", "actor": {"kind":
"ai" | "person", "name"}, "kind", "args", "text", "files", "more"}`: `kind` is `create`, `copy`, `merge`, `rename`, `delete`,
`restore`, `page-new`, `page-rename`, `page-move`, `tree`, `publish`, `ai` (your edits), `sync` (a commit `itN: автосинк`
without the AI trailer; older ones with the trailer show as `ai` with `args.synced: true`) or `other`; `files` are up to 5
files of this iteration the commit touched and `more` counts the rest. `pending` is the not yet committed changes of the
iteration (`{"files", "more", "at"}`) or `null`. `"degraded": true` means the history is not read from git: the task
folder has no `.git`, or a git call failed (error, timeout), and `entries` is then one `create` entry built from the
iteration's own record, `pending` is `null`. If
`iterations.json` itself cannot be read the answer is `200 {"ok": false, "error": "meta-unreadable", "entries": [],
"pending": null, "degraded": true}`. `404 {"error": "iteration-not-found"}` for an unknown id.

Your own edits show as `actor.kind: "ai"`: after finishing edits to an iteration, call `POST /api/autosync {}` (topic
`hooks`); the canvas commits them locally as `itN: зміни AI` with the trailer `Deai-Actor: ai`. Do not commit the task folder
yourself. Without this call your edits stay uncommitted until the next canvas action that commits the whole task folder
(creating, renaming or deleting an iteration, a page action, publishing — including your own calls to these routes). That
commit carries no `Deai-Actor` trailer, so the history shows your edits as a person's, under this computer's git identity.
A colleague's iteration is never committed by this call.

## Pages of an iteration

    GET http://127.0.0.1:8765/api/iteration-pages?it=itN

`{"it", "pages", "rev"}`: the page tree of `pages.json`; an iteration without a folder gives empty `pages`. To change pages,
see the topic `pages`.

## Iterations used as pages

    POST http://127.0.0.1:8765/api/pages-from-iterations {"itIds": ["it2", "it3"]}

Makes a new iteration whose pages are the chosen iterations (at least two, else `400`); each page is named after the
iteration's label or note. The originals stay as they are.

## A built app as an iteration

    <deai>/bin/deploy-build-to-iteration.command <dist dir> <task-id> <itN>

Copies a built single-page app (many files) into an iteration; build it with `--base-href=/it-assets/<itN>/`. The target
is `~/deai-work/<task-id>/iterations/<itN>` unless the environment variable `DC_ITERATION_DIR` names the iteration folder:
set it to `<task dir>/iterations/<itN>` (`dir` in the answer of `POST /api/task-new`), because new tasks usually do not
live in the default folder. The script removes hashed `*.js` and `*.css` bundles of an earlier build that the new
build does not have, and leaves other files (`pages.json`, `shots/`, page folders) alone. Create the iteration first with
`POST /api/iteration`: the script only copies files.
