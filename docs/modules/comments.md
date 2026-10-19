# Writing a `comments` module

For Deai Canvas **0.4.0**. A `comments` module connects *any* comment service (Supabase, PocketBase, Firebase, your own
API…) to the team comments of the canvas: pins on the canvas pages, on the Overview, in published previews, and for the
agent (`inbox`). The core knows nothing about your service except what the module tells it.

**Коротко (uk).** Роль `comments` має дві половини: браузерний адаптер (`window.DeaiComments.create(cfg)` → сховище для
шару коментатора) і серверні функції `client_config` / `list` / `resolve` / `check` у `server.py`. Канал задачі
(`deai/<простір>/<задача>`) дає ядро, модуль його не будує. До сторінок потрапляє лише публічна конфігурація: значення
секретів — тільки з `"public": true`. У 0.4.0 працюють **лише вбудовані модулі** (JS адаптера виконується в origin
канваса); власні модулі з теки простору — етап 3, після діалогу довіри. Сервіс коментарів мусить дозволяти CORS і для
`Origin: null` (локальний перегляд опублікованого). Реальний приклад — [`supabase-comments`](../../app/modules/supabase-comments/README.md).

## 1. The two halves

```
 browser page ──► adapter.js ── fetch / SDK ──► your service ◄── server.py ◄── core ◄── agent (bin/inbox.py)
 (canvas, Overview, preview)                                     client_config · list · resolve · check
```

A module is a folder `<modules-dir>/<id>/` with `module.json`, `server.py` and the browser files listed in `client`. The
`id` must equal the folder name (`[a-z0-9][a-z0-9-]{0,39}`).

### Manifest

```json
{"api": 1, "id": "my-comments", "name": "My comments service", "version": "1.0.0",
 "roles": ["comments"], "client": ["adapter.js"],
 "settings": [
   {"key": "endpoint", "type": "text", "label": "Service address", "required": true},
   {"key": "token", "type": "secret", "label": "Token (server only)"},
   {"key": "pubkey", "type": "secret", "public": true, "label": "Public key (goes into pages)"}
 ]}
```

* `client` — the browser files, loaded in this order as classic `<script src>` tags; the last one registers the factory.
  Required for the role (forbidden without it): 1 to 8 names matching `[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\.js`, each a plain file
  of the module folder (no symlink, no hard link), at most 512 KiB, spelled exactly as on disk, listed once. Anything else
  is `bad-manifest`: the module shows as broken and nothing of it runs. Do not name a file like a core bundle
  (`comment-layer.min.js`, `supabase-adapter.min.js`, in any letter case): building a preview refuses it. The core serves only
  the listed files, at `GET /api/module-client/<id>/<file>` (`text/javascript`, `nosniff`).
* Settings are `text`, `path`, `bool`, `select` or `secret`. Secrets live in `~/.deai/secrets.json`, never in `space.json`.
  `"public": true` is allowed on a **secret only** and means: the value stays out of `space.json` but may be shown to pages.
  Every other secret is private and must never appear in what you give to pages (see `client_config`).
* Enable it with `POST /api/module-enable {"space", "id", "settings", "secrets"}`; the answer carries the verdict of `check`.
  One `comments` provider per space.

## 2. The browser half

```js
window.DeaiComments = { create(cfg) { return store; } };
```

`cfg` is `{ ...client_config, channel, onChange }`. `channel` and `onChange` are the core's: a module key with the same name
is overridden. `onChange` is an empty hook — the comment layer listens through `store.subscribe`.

| `store` member | contract |
|---|---|
| `load()` | **required.** The current array of comments, synchronously, from your cache. |
| `save(comments)` | **required.** `Promise`. Persist the whole array (upsert by `id`). |
| `ready` | optional `Promise`, settled after the first load. The layer starts only after it settles, so **resolve it even when the service is down** (with an empty cache): a rejection shows the red banner «Коментарі недоступні», and a promise that never settles hangs the layer. |
| `remove(ids)` | optional. `Promise`. Hard-delete. |
| `subscribe(fn)` | optional. Call `fn(comments)` on external changes (polling, websocket, realtime). |
| `close()` | optional. Release timers and sockets. The layer calls it on `destroy` and the Overview calls it when a run is stale; make it idempotent. |

If `create` throws, or the store has no `load`/`save`, the page shows the banner instead of the layer.

**A comment** is the comment layer's shape; keep unknown fields as they are:
`{ id, author, text, status: 'open'|'resolved', fp, htmlSnapshot, meta, bornV, resolvedV, resolveReason, ts }`. `meta` may
carry a screenshot, `meta.shot` — a JPEG data URL (the layer fetches `html2canvas` from jsDelivr when a pin is created; the
role has no file storage, so the screenshot travels inside the comment and the agent side drops it).

**Where the same files run:** the canvas page (`/commented?…&ch=project`, in the frame), the Overview (in the shell
document; the core captures `window.DeaiComments` right after the last file loads), and the published preview (copied to
`comment-layer/` next to the pages, the same snippet with relative paths). So: classic scripts, no `import`, no other
globals than `window.DeaiComments`, and **no `localStorage`, cookies or `sessionStorage`** — the local `/published` view is a
sandbox with an opaque origin where they throw.

**CORS.** Pages are served from the canvas origin (`http://127.0.0.1:<port>`), from the sandbox of the local `/published`
view (`Origin: null`), or from your real hosting. The service must answer with `Access-Control-Allow-Origin: *` (or the
origin). A `text/plain` body keeps the request "simple", with no preflight; if you send JSON or custom headers the service
must also answer `OPTIONS` with `Access-Control-Allow-Headers`. Without it pins do not load in the local `/published` view.

## 3. The server half (`server.py`)

Loaded by the core with `exec` (not imported): write it against the **standard library only** — it cannot import the core or
sibling files (a test holds the built-in modules to a stdlib allowlist). Each function gets a
`ctx`: `{'space': {id, path}, 'settings': {…}, 'secrets': {…only this module's…}, 'ModuleError': <class>}`.
⚠️ `def list` shadows the builtin `list` in your file: write `type([])`, never `list(…)`.

| function | contract |
|---|---|
| `client_config(ctx) -> dict` | the **public** configuration for pages. |
| `list(ctx, channel) -> [comment]` | the channel's comments, for the agent. |
| `resolve(ctx, channel, id, reason) -> None` | close a comment (the agent). |
| `check(ctx) -> {ok, error?, detail?}` | read-only health check; never create anything. |

Timeouts: `client_config` and `check` get 5 s (then `check-timeout`), `list` and `resolve` 10 s. Time out your own requests
earlier. A timed-out call is abandoned, its thread finishes in the background.

* **`client_config`** — a flat JSON object of at most 4096 bytes (`json.dumps`), values `str`/`int`/`float`/`bool`/`null`, no
  nesting. The core refuses the answer (`module-error`) if the value of any secret that is **not** `public` appears in a key or
  a value (also URL-decoded or JSON-escaped). That guard stops accidents (a token put into an address); it is not a trust
  boundary. Everything you return is readable by whoever opens a page or a published preview.
* **Channel** — a string `deai/<space-id>/<task-id>` (the internal sub-channel ends in `/internal`), built by the core and the
  same on the page and for the agent. Use it as an opaque partition key: never build, parse or normalise it, and always filter
  by it (a write or delete by `id` alone can touch another channel's rows).
* **`list`** — a list of comments. The core keeps only known fields, drops `meta.shot`, strips control and invisible characters,
  skips malformed or repeated ids (and says how many), and takes at most 5000 comments / 2 MiB. An `id` must match
  `[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}` (the layer produces UUIDs or `c-<digits>-<base36>`): any other is skipped. A non-list
  answer is `module-error`: «empty» would be a lie.
* **`resolve`** — must be **idempotent** (closing a closed comment is not an error) and **effective**: afterwards `list` returns
  it with `status: 'resolved'`, because the agent does not re-read the service. Closing a comment that does not exist should be an
  error: the agent must not believe a close that changed nothing. The core passes only whitelisted ids.
* **`check`** — report failures as a verdict, `{'ok': False, 'error': 'bad-key', 'detail': '…'}`; raising gives `module-error`.
  Strings are scrubbed of your secrets and cut to 300 characters.
* **Errors** — raise `ctx['ModuleError'](code, 'message')`. A code from the core's table passes through with its HTTP status
  (`module-error` 502, `bad-settings` 400, …); an unknown code, or any other exception, becomes `module-error`. Texts are scrubbed
  of your secrets and cut to 300 characters; the agent sees them as one clean line. Do not put anything in a message you would
  not print in a terminal.

## 4. Security

* The adapter runs **on the canvas origin** — the same origin as the canvas API. It has the full power of the canvas page.
  That is why 0.4.0 loads **built-in modules only** (`app/modules/`); a space's own modules arrive in stage 3 with a trust
  dialog, and their browser code is part of what the person trusts.
* `DEAI_EXTRA_MODULES=<dir>` is a **test seam**: a second folder of modules that act as built-ins (the server prints one line
  about it on stderr). Use it for development, never as an installation method.
* Pages and previews carry your `client_config`, so keep the service's rules as strict as the service allows: with a public key
  in every page, whoever has it reads and writes. Prefer a dedicated service (project, database) per team.
* The token goes only into headers of requests to your service, from one place; use `https://` and a DNS name, and never follow
  redirects with credentials (the example below refuses them). Plain `http://127.0.0.1` is for local tests only.

## 5. Testing

The core's own Python suite does not run your module. Three loops:

1. **The server half, by itself** — load it as the core does and call the four functions against a fake or real service:

   ```python
   import os, sys
   sys.path.insert(0, 'app')                                    # the canvas checkout
   os.environ['DEAI_EXTRA_MODULES'] = '/path/to/my-modules'
   import deai_modules as dm
   mod = dm.catalog()['my-comments']
   assert mod.status == 'ok', mod.error                         # a manifest or import error shows up here
   ctx = {'space': {'id': 'demo', 'path': '/tmp'}, 'settings': {'endpoint': 'http://127.0.0.1:9000'},
          'secrets': {'token': 'x'}, 'ModuleError': dm.ModuleError}
   print(dm.call(mod, 'client_config', ctx, timeout=5))        # the same wrapper, scrubbing and timeouts as the core
   print(dm.call(mod, 'list', ctx, 'deai/demo/t1', timeout=10))
   ```

2. **In the canvas** — `DEAI_EXTRA_MODULES=/path/to/my-modules python3 app/serve.py`, then enable the module
   (`POST /api/module-enable`, read `check`), open `/commented?it=it1&page=<page>&ch=project` (or the «Team» tab), check
   `GET /api/comment-config?ch=project`, publish a preview and open `/published/<space>/<task>/`, and run `python3 bin/inbox.py`
   for the agent side.
3. **A live scenario** — [`tests/live/comments.test.mjs`](../../tests/live/comments.test.mjs) is the template: a tiny service,
   the module enabled over the API, a seeded pin seen on the canvas, on the Overview and in the preview, a pin created in the UI
   arriving in the service. Point its `MODULES_DIR`, module id and fake service at yours.

Set `DEAI_EXTRA_MODULES` per command, not for a whole `unittest discover` run: four tests of the core that list the catalog
(`test_modules`, `test_modules_api`) assume it holds only the built-in modules and fail when an extra one is present.

## 6. A minimal complete example

A service with four routes — `GET /c/<channel>` (a JSON array), `POST /c/<channel>` with `{"comments": […]}` (upsert by `id`),
`POST /c/<channel>/remove` with `{"ids": […]}` and `POST /c/<channel>/resolve` with `{"id", "reason"}` — answering with CORS
`Access-Control-Allow-Origin: *`. This is the reference fixture `tests/fixtures/modules/memo-comments/`, trimmed. For the
real thing see [`supabase-comments`](../../app/modules/supabase-comments/README.md): an SDK in the browser, a REST client in
`server.py`, a schema you run once, strict URL checks.

`module.json` — see section 1 (drop `pubkey` if you do not need a public key).

`server.py`:

```python
import json
import urllib.request
from urllib.parse import quote, urlsplit

TIMEOUT = 4                      # the core waits 5 s for client_config/check and 10 s for list/resolve


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None              # a 3xx is an error, never a second request that carries the token


_opener = urllib.request.build_opener(_NoRedirect)


def _call(ctx, method, channel, tail='', body=None):
    base = ctx['settings']['endpoint'].rstrip('/')
    u = urlsplit(base)
    if u.scheme != 'https' and not (u.scheme == 'http' and u.hostname == '127.0.0.1'):   # plain http: loopback tests only
        raise ctx['ModuleError']('bad-settings', 'endpoint must be an https:// address')
    headers = {'Content-Type': 'application/json'}
    if ctx['secrets'].get('token'):
        headers['Authorization'] = 'Bearer ' + ctx['secrets']['token']
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}/c/{quote(channel, safe='')}{tail}", data=data, method=method, headers=headers)
    with _opener.open(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read() or b'null')


def client_config(ctx):
    return {'endpoint': ctx['settings']['endpoint']}          # public values only: this goes into every page


def list(ctx, channel):                                       # shadows the builtin: never call list(...) in this file
    rows = _call(ctx, 'GET', channel)
    return rows if isinstance(rows, type([])) else []


def resolve(ctx, channel, id, reason):
    _call(ctx, 'POST', channel, '/resolve', {'id': id, 'reason': reason})


def check(ctx):
    try:
        _call(ctx, 'GET', 'deai/check')                      # read-only: creates nothing in the service
    except Exception as e:                                    # a verdict, not a crash
        return {'ok': False, 'error': 'network', 'detail': type(e).__name__}
    return {'ok': True}
```

`adapter.js`:

```js
(function () {
  function create(cfg) {                                      // cfg = { ...client_config, channel, onChange }
    var base = String(cfg.endpoint).replace(/\/+$/, '') + '/c/' + encodeURIComponent(cfg.channel);
    var cache = [], subs = [], timer = null, pending = 0;

    function notify() { subs.forEach(function (fn) { try { fn(cache); } catch (e) { /* one listener never breaks the rest */ } }); }
    function read() {
      return fetch(base).then(function (r) { if (!r.ok) throw new Error('load ' + r.status); return r.json(); });
    }
    function send(tail, body) {                               // text/plain: a "simple" request, no CORS preflight
      pending++;
      return fetch(base + tail, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=UTF-8' }, body: JSON.stringify(body) })
        .then(function (r) { if (!r.ok) throw new Error('save ' + r.status); })
        .finally(function () { pending--; });
    }
    function poll() {                                         // external changes; never while a write is in flight
      if (pending) return;
      read().then(function (rows) {
        if (pending || JSON.stringify(rows) === JSON.stringify(cache)) return;
        cache = rows; notify();
      }).catch(function () { /* next time */ });
    }

    return {
      ready: read().then(function (rows) { cache = rows; }, function () { cache = []; }),
      load: function () { return cache; },
      save: function (comments) { cache = comments.slice(); notify(); return send('', { comments: comments }); },
      remove: function (ids) { cache = cache.filter(function (c) { return ids.indexOf(c.id) < 0; }); notify(); return send('/remove', { ids: ids }); },
      subscribe: function (fn) { subs.push(fn); if (!timer) timer = setInterval(poll, 1000); },
      close: function () { subs.length = 0; clearInterval(timer); timer = null; }
    };
  }
  window.DeaiComments = { create: create };
})();
```

If your adapter needs a key from the browser, declare it `"public": true`, return it from `client_config` and send it from the
adapter. A custom request header makes the request non-simple — answer the preflight.
