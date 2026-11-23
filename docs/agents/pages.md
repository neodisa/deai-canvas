# Pages
Pages of an iteration: create, rename, move, group, folders, delete and restore.

An iteration keeps its pages as a tree in `pages.json`; each page or state is a folder `<page-id>/index.html` in the
iteration folder (flat, whatever the depth in the tree). A node is a `folder` (only organises, has no files), a `page`, or a
`state` of a page (a child of a page; nothing can be put inside a state). **Never rewrite `pages.json` by hand**: the designer
arranges the tree in the canvas, and writing the whole file silently destroys their folders. Use the calls below or
`<deai>/bin/pages.py` (it takes the same lock as the canvas).

Every call acts on one task: send the header `X-Canvas-Task: <task-id>` (or the `/t/<task-id>` prefix); without it, on the
current task. Every body has `"it": "itN"`. Refusals are `{"ok": false, "error", "code"}`: `stale` `409`, `busy` `503`,
`not-found` `404`, `corrupt` `500` (`pages.json` does not parse), others `400`, among them `bad-iteration`, `bad-page`, `bad-ids`, `bad-id`,
`bad-mode`, `bad-prev`, `bad-form`, `bad-kind`, `bad-index`, `empty-name`, `dup-id`, `cycle`, `not-siblings`, `too-deep`,
`state-has-children`, `state-outside-page`, `missing-rev`.

## Read and rev

    GET http://127.0.0.1:8765/api/iteration-pages?it=itN

Gives `pages` and `rev`. The tree calls marked «rev» need `"rev": "<rev>"` (a string; `""` is a valid rev of a missing file):
without it `400 missing-rev`, and when the file changed since you read it `409 stale`: read again and repeat.

## Create, rename

    POST http://127.0.0.1:8765/api/page-new    {"it": "itN", "name": "Pricing", "parent": "<id>", "kind": "page"}
    POST http://127.0.0.1:8765/api/page-rename {"it": "itN", "page": "<id>", "name": "New name"}

`page-new`: `parent` (optional, else the root) and `kind` (`page` or `state`) are optional; answer `{"ok": true, "page":
{"id", "name", "kind", "published"}}`; the id comes from the name, and the new page gets a starter `index.html` that you
then overwrite. `page-rename` answers `{"ok": true}`.

## Delete

    POST http://127.0.0.1:8765/api/page-delete {"it": "itN", "page": "<id>", "mode": "all", "rev": "<rev>"}

`mode` is `all` (the node with everything under it; the default) or `unwrap` (the children stay in its place). With `mode`
a `rev` is required; answer `{"ok": true, "rev", "failed"?}`, where `failed` lists page folders that could not be erased.

## Move, nest, order

    POST http://127.0.0.1:8765/api/page-move     {"it": "itN", "ids": ["a", "b"], "parent": "<id>|null", "index": 0, "rev": "<rev>"}
    POST http://127.0.0.1:8765/api/page-move     {"it": "itN", "page": "<id>", "index": 2}
    POST http://127.0.0.1:8765/api/page-move     {"it": "itN", "page": "<id>", "delta": -1}
    POST http://127.0.0.1:8765/api/page-reparent {"it": "itN", "page": "<id>", "parent": "<id>|null"}

The first form moves nodes under `parent` (`null` is the root) at `index` among its children, after lifting them out; it
needs `rev` and answers `{"ok": true, "rev"}`; a node cannot go into itself (`cycle`) or into a state. The short forms only
reorder among siblings: `index`, or `delta` of `-1` or `1` (one place up or down); `parent` in a short form is
`400 bad-form`. `page-reparent` moves a page under a parent (`null`: the root).

## Folders and groups

    POST http://127.0.0.1:8765/api/folder-add {"it": "itN", "name": "Flows", "parent": "<id>", "index": 0, "rev": "<rev>"}
    POST http://127.0.0.1:8765/api/page-group {"it": "itN", "ids": ["a", "b"], "name": "Flows", "rev": "<rev>"}
    POST http://127.0.0.1:8765/api/page-ungroup {"it": "itN", "id": "<folder id>", "rev": "<rev>"}

`folder-add` and `page-group` answer `{"ok": true, "node", "rev"}`; `page-group` wraps sibling nodes in a new folder at the
place of the first (`not-siblings` otherwise). `page-ungroup` dissolves a folder and keeps its children in its place; only a
folder can be ungrouped (`bad-kind`).

## Kind, visibility, restore

    POST http://127.0.0.1:8765/api/page-kind {"it": "itN", "id": "<id>", "kind": "page|state", "rev": "<rev>"}
    POST http://127.0.0.1:8765/api/page-publish-toggle {"it": "itN", "page": "<id>"}
    POST http://127.0.0.1:8765/api/page-restore {"it": "itN", "prev": [<tree>], "rev": "<rev>"}

`page-kind` turns a page into a state or back (not a folder). `page-publish-toggle` flips whether the page goes to the
published preview (`published`, true by default). `page-restore` is not an undelete: it puts the folders and kinds of the
tree `prev` (what the canvas saw before the file was rewritten from outside) back over the tree on disk; answer
`{"ok": true, "restored", "rev"}`.

## From the terminal

    python3 <deai>/bin/pages.py list   --task-dir <task folder> --it itN
    python3 <deai>/bin/pages.py add    --task-dir <task folder> --it itN --kind page|state|folder --name "…" [--into ID] [--after ID]
    python3 <deai>/bin/pages.py move   --task-dir <task folder> --it itN --id ID (--into ID | --after ID | --root)
    python3 <deai>/bin/pages.py rename --task-dir <task folder> --it itN --id ID --name "…"
    python3 <deai>/bin/pages.py kind   --task-dir <task folder> --it itN --id ID --kind page|state

`<task folder>` is the one that holds `iterations/` (`dir` in the answer of `POST /api/task-new`). `add` without a target puts
the node at the end of the root; `move` needs exactly one of `--into`, `--after`, `--root`. `add`, `move`, `rename` and `kind` print JSON on success; `list` prints the tree as text, one line `id  [kind]  name` per node, indented by depth. A refused
rule exits with code 2 and `error <code>: <text>` on stderr, and the tree is unchanged. The tool does not commit to git.
