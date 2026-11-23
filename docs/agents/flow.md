# Flow map
Flow map of an iteration: screens and arrows in `flow.json`.

The flow map shows the screens of an iteration as boxes and the transitions between them as arrows. It lives in
`iterations/<itN>/flow.json`; no file means no flow described yet. Every call acts on one task: send the header
`X-Canvas-Task: <task-id>` (or the `/t/<task-id>` prefix); without it, on the current task.

## Read

    GET http://127.0.0.1:8765/api/flow?it=itN

`{"flow": {…}}` with the content of `flow.json`; `{"flow": null}` when there is no file; `{"flow": null, "error": "…"}` when
the file cannot be read or is not an object. A bad `it` is `400`.

## Save

    POST http://127.0.0.1:8765/api/flow-save {"it": "itN", "flow": {"flows": [ … ]}}

Replaces the whole `flow.json` with the object `flow` (`400` when it is not an object): read it first and send everything
back. Answer `{"ok": true}`, or `{"ok": false, "error"}` when the file could not be written.

## The file

    {"flows": [{"id": "first-run", "title": "First run",
                "nodes": [{"id": "n-home", "page": "home", "label": "Home", "pos": {"col": 0, "row": 0}},
                          {"id": "n-list", "page": "list", "state": {"state": "empty"}}],
                "edges": [{"from": "n-home", "to": "n-list", "label": "Open the list"}]}]}

- `flows` is a list of lanes; each has an `id`, an optional `title`, `nodes` and `edges`.
- A node is one screen: a unique `id` in the lane, `page` (the id of an openable page of the iteration, not a folder),
  optional `label` (default: the page name), optional `state` (an object of URL parameters that puts the page in a state;
  the names `it`, `page`, `bare`, `ch`, `v`, `host` are reserved) and optional `pos` `{col, row}`. Two nodes may not show the
  same page in the same state.
- An edge joins two node ids with `from` and `to`, and an optional `label`; an edge from a node to itself is dropped.
- A flow with a closed loop of edges is dropped as a whole lane. The canvas lists every problem it finds (a missing page, a
  duplicate id, a loop) and keeps the rest, so read the problems it shows after a save. Pages that appear in no node are
  shown as «not in a flow».
- Screenshots of the nodes are taken with the topic `shots`; a node with a `state` gets its own frame.
