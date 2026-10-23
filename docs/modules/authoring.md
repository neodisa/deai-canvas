# Writing your own module

For Deai Canvas **0.7.0**. A module adds one capability — a *role* — to a space: publishing previews, design-system
tokens, team comments. Built-in modules live in `app/modules/`; **your own modules live in the space**, in
`<space>/modules/<id>/`, so they travel with the space through git. Their code runs on your computer only after **you**
trust it.

**Коротко (uk).** Свій модуль — тека `<простір>/modules/<id>/` з `module.json` і `server.py`. Канвас його бачить одразу,
але код не виконує, доки людина не довіриться: «Підключення» → «Довіритись…» → діалог із файлами → «Довіряю» → системне
вікно ОС. Довіра — до точних байтів: канвас копіює їх у знімок `~/.deai/trusted/<відбиток>/` і виконує лише знімок. Зміна
теки не діє до повторної довіри. Агент може написати модуль, але довіритись — ні.

## 1. The folder

```
<space>/modules/acme-publish/
  module.json      the manifest
  server.py        the functions of the role (standard library only)
  adapter.js       browser files — only for the comments role, listed in "client"
```

* The folder name is the module `id`: `[a-z0-9][a-z0-9-]{0,39}`, the same as `id` in the manifest. A subfolder with any
  other name, or without a `module.json`, is not a module and is ignored.
* An id that a built-in module already has is skipped (the Connections screen says so). At most 32 own modules per space
  (alphabetical order; the rest are skipped with a note).
* Folder rules — a folder that breaks one cannot be trusted, and the trust dialog says which rule:
  at most **200 files**, **5 MiB** in total, **8** levels of folders; only regular files and folders — no symbolic or
  hard links, no devices or pipes; file names without control, bidirectional or invisible characters, without a trailing
  dot or space, without names reserved on Windows (`CON`, `NUL`, `COM1`…), and no two names in one folder that differ only
  in letter case or Unicode form. `.DS_Store`, `__pycache__/`, `.git/` and `*.pyc` are ignored; every other file — hidden
  ones included — is part of what you trust.

## 2. The manifest (`module.json`)

```json
{"api": 1, "id": "acme-publish", "name": "Acme hosting", "version": "1.0.0",
 "roles": ["publish"], "publish_target": "url",
 "settings": [
   {"key": "site", "type": "text", "label": "Site id", "required": true},
   {"key": "token", "type": "secret", "label": "API token"}
 ]}
```

* `api` — `1`. `name` and `version` — strings shown to people.
* `roles` — the roles the module provides: `publish`, `tokens`, `comments` (called by the core today); `vcs`,
  `tracker`, `dashboard`, `notify` are reserved. One provider per role per space.
* `publish_target` (publish only) — `folder` (default) or `url`. The canvas serves the local copy of a published preview
  (`/published/…`) only for the built-in `static-publish`.
* `client` (comments only) — the browser files; see [comments.md](comments.md).
* `settings` — what the module asks for: `text`, `path`, `bool`, `select` (with `options`) or `secret`; `required`,
  `default` and (secret only) `public` as in the built-in modules. Settings are stored in the space's `space.json`;
  secrets — in `~/.deai/secrets.json`, never in the space.

A manifest that breaks these rules cannot be trusted: the card says why, and nothing of the module runs.

## 3. `server.py`

Every module has `check(ctx) -> {"ok": bool, "error"?: str, "detail"?: str}` — a read-only health check (5 s). A role
adds its own functions:

| role | functions |
|---|---|
| `publish` | `publish(ctx, build_dir, task)` |
| `tokens` | `tokens(ctx)` |
| `comments` | `client_config(ctx)`, `list(ctx, channel)`, `resolve(ctx, channel, id, reason)` |

A module that lacks `check` or a function of its roles shows as broken. The exact return values are those of the built-in
modules — read `app/modules/static-publish/` (`folder`), `app/modules/vercel-publish/` (`url`), `app/modules/css-tokens/`
and [comments.md](comments.md).

`ctx` is `{"space": {id, path}, "settings": {…}, "secrets": {…only this module's…}, "folder_ok": f, "ModuleError": class}`.
Raise `ctx["ModuleError"](code, "message")` for a failure; texts are cut to 300 characters and scrubbed of your secrets.
A code the core knows (`bad-folder`, for example) is passed on as it is; any other code is reported as `module-error`.

`server.py` (at most 1 MiB) is executed by the core (not imported): write it against the **standard library only**. The
module is not put into `sys.modules`, so `@dataclass` together with `from __future__ import annotations` fails and its
classes cannot be pickled; functions and plain dicts are enough.

## 4. Trust

1. Put the folder into `<space>/modules/`. The Connections screen shows the module with «own» and «Needs trust»; its
   code has not run.
2. «Trust…» opens a dialog: what the module asks for, every file with its size, the fingerprint. «Trust» then asks the
   **operating system** to confirm in its own window (macOS dialog, Windows message box, Linux `zenity`/`kdialog`). Only
   a person at the computer can answer it: a script on a page and an agent without control of the screen cannot.
   After «No», asking again for the same version within 30 s is refused without a window.
3. The canvas copies exactly the bytes you saw into `~/.deai/trusted/<fingerprint>/` (read-only) and runs only that
   snapshot. Write the module's state into the space folder or your own cache, never next to `__file__`.
4. Editing the folder does not change what runs: the card says «The folder has changes» and the previous version keeps
   working until you trust the new one. A new version that breaks a folder rule cannot be trusted; the old one keeps
   running.
5. «Revoke trust» (card panel or dialog) stops the code; `space.json` and the settings stay. A module that is on in the
   space but not trusted on this computer keeps its role «on paper»: the role reports an error instead of falling back
   to another provider.
6. In the new-space wizard your module is marked «own». Until you trust it, its option is disabled and has a «Trust…»
   button (the same dialog, the same system window); a folder that cannot be trusted shows the reason instead of the
   button. If a teammate already turned it on in `space.json`, it stays selected; the settings step writes nothing for it
   and says it is waiting for trust. A module whose folder has changes can be selected — the previous version runs; trust
   the new one on the Connections screen.

The module's top level gets **5 s** to load; a module that hangs is shown as broken (its thread lives until the server
restarts). Browser code of a trusted `comments` module runs in canvas pages and published previews with the canvas's
own access — that is part of what you trust.

## 5. The agent

An agent can write the folder, read `GET /api/modules?space=<id>` and `GET /api/module-trust?space=<id>&id=<module>`, and
— after **you** trust the module — connect and configure it (`POST /api/module-enable`, `/api/module-settings`). It cannot
trust: `POST /api/module-trust` needs the canvas page in a browser (`Origin` and `Sec-Fetch-Site: same-origin`; a script
or `curl` gets `403 trust-needs-ui`) and then the system window. It may revoke trust (`POST /api/module-untrust {space, id}`).
Ask the person to trust the module.

## 6. Trying it locally

Create the folder in a test space, open «Connections», trust it, connect it and press «Check»: the verdict of your
`check` is shown on the card. After every edit, trust again — that is the point.
