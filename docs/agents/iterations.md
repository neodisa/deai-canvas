# Iterations
Versions of a task: create, rename, delete, list pages, turn iterations into pages.

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

Removes the iteration's folder and entry; answer `{"ok": true, "deleted": "itN"}`, `404` for an unknown id. The task's git
history records the deletion.

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
set it to `<task dir>/iterations/<itN>` (`dir` from `POST /api/task-new` or `GET /api/tasks`), because new tasks usually do not
live in the default folder. The script removes hashed `*.js` and `*.css` bundles of an earlier build that the new
build does not have, and leaves other files (`pages.json`, `shots/`, page folders) alone. Create the iteration first with
`POST /api/iteration`: the script only copies files.
