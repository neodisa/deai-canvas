# Publish
Publish marked iterations as a preview link; preview password; import someone's preview.

Publishing is done by the space's module with the role `publish` (see the topic `modules`). Every call acts on one task:
send the header `X-Canvas-Task: <task-id>` (or the `/t/<task-id>` prefix); without it, on the current task. Publishing deploys the marked
iterations; the preview link can be shared with others.

## Mark iterations

    POST http://127.0.0.1:8765/api/publish-toggle {"id": "itN"}

Flips the «publish» mark of an iteration (the green dot in the canvas); answer `{"ok": true, "id", "published"}`, `404` for an
unknown iteration. Only marked iterations are published. To hide one page of an iteration, see `page-publish-toggle` in the
topic `pages`.

## Publish

    POST http://127.0.0.1:8765/api/publish {}
    POST http://127.0.0.1:8765/api/publish {"build_only": true}

Builds the preview from the marked iterations and hands it to the publish module. `build_only` only builds it and does not
deploy. Refusals: `400` when no iteration is marked («toggle the green dot first»); `409 no-publish-module` when the space
has no module with the role `publish`; `409 publish-busy` (folder modules) when another publish of the same task is running. The answer
starts with `"ok": true` and then depends on the kind of publisher:

- a module that publishes to a folder: `{"local": {"path", "url": "/published/<space-id>/<task-id>/"}, "iterations", "frames"}`;
  the canvas shows the page at that address;
- the Vercel module: `url` (the preview link), `deploy_url`, `verified`; a failed deploy still answers `200` with
  `deploy_error` (and `deploy_blocked: "no-node"` when Node is missing). The `deploy_*` keys exist only on this path;
- a module with `publish_target: "url"` (publishes to a remote address): `{"url", "verified", "warnings"?, "frames_warnings"?}`;
  its failures are module errors (`{"ok": false, "code", "error"}`), not `deploy_error`.

`comments_unavailable` in the answer means the preview was built without team comments (the reason is its value).

## Preview password

    POST http://127.0.0.1:8765/api/preview-password {"password": "<password>"}

Sets the password of this task's preview gate (the Vercel module's gate): a string of up to 64 characters without control
characters; an empty string brings back the default password of the space. Answer `{"ok": true, "preview_password",
"preview_password_custom", "preview_gate"}`. The new password reaches the preview with the NEXT publish: until then
`preview_gate` says it is stale. `409` when the space's publisher has no such gate (other modules keep their own `password`
in the module secrets, see the topic `modules`). A password, like any secret, comes from the person; never invent it.

## Import someone's preview

    python3 <deai>/bin/import_preview.py --task-dir <task folder> <preview url> [--it itN] [--dry-run]

For a colleague's published preview of the same task: it reads the preview's manifest, fetches the pages and their
files, removes the publication inserts (comment layer, gate, neutral title) and writes the result as a NEW iteration marked as
someone else's, with your own working copy beside it. `--it` picks the iteration of the preview (default: the latest),
`--dry-run` only shows what would be imported. A page whose gate cannot be removed is not written and the import stops. It does
not commit or push to git. `<task folder>` is the one that holds `iterations/`.
