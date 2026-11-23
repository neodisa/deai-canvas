# Git sync
Git sync of a task: status, push an iteration, pull changes as a new iteration.

Needs a space module with the role `vcs` (for example `git-sync`, see the topic `modules`) and a repository for the task: the
task's own `vcs` target (`POST /api/task-new`, topic `tasks`) or the module's settings. Every call acts on one task: send
the header `X-Canvas-Task: <task-id>` (or the `/t/<task-id>` prefix); without it, on the current task.

## Status

    GET http://127.0.0.1:8765/api/vcs-status?it=itN

`{"configured": false}` when the space has no `vcs` module or the task has no repository. Otherwise `{"configured": true,
"behind", "behind_path", "unpushed", "on_remote", "dirty", "synced_at", "synced_it", "gitlab_it", "remote_path", "web",
"label"}`: `behind` is how many commits the repository has that the local copy lacks, `behind_path` the same under the task's
path, `unpushed` the local commits not sent, `on_remote` whether the path exists on the remote branch, `dirty` whether the
chosen iteration changed since its last send. A refusal of the provider (for example an unreadable `space.json`) comes as `{"configured": false, "code"}`; a refusal of
the module as `{"configured": true, "error", "code"}`.
`it` is optional; a bad name is `400`.

## Push

    POST http://127.0.0.1:8765/api/vcs-push {"it": "itN"}

Sends the iteration into the task's path of the repository as one commit and pushes it without force. Answer `{"ok", "synced",
"changed", "pushed", "sha"?, "remote"}`. Nothing is sent when:

- the iteration is a colleague's: `{"ok": false, "synced": false, "blocked": "foreign"}`; someone else's work is never sent
  under your signature;
- the repository has newer work under the path: `blocked` says why (`behind`, `diverged`); pull first.

No `vcs` role or no repository for the task: `400 no gitlab configured for this task`. A bad `it`: `400 bad iteration`; an
unknown iteration is a refusal below (`error` without a `code`).

## Pull

    POST http://127.0.0.1:8765/api/vcs-pull {}

Takes the repository's version of the task's path as a NEW iteration; your working iteration is not touched. A colleague's
work arrives signed as theirs, with a copy of it to continue in. When the repository equals an iteration you already have,
nothing is created: `{"ok": true, "unchanged": true, "iteration": null, "same_as": "itN"}`. Otherwise `{"ok": true,
"iteration": {…}}`. A path missing in the repository is a refusal.

## Refusals

A refusal of the provider or the module is `200` with `{"ok": false, "error", "code"}`; the codes are `vcs-offline`,
`vcs-auth`, `vcs-bad-target`, `vcs-busy`, `vcs-error`. `vcs-busy` means a send or a pull is already running: try again.
The repository address in messages is masked.

With the module's `autosync` setting on, the Stop hook sends after each agent reply (topic `hooks`); otherwise sending happens on
`POST /api/vcs-push`.
