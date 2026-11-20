"""`app/modules/supabase-comments`: власний проєкт Supabase людини як сервіс командних коментарів (роль `comments`, 2b-2, Task 5).

Модуль вантажиться через справжній `deai_modules.catalog()` (маніфест, `client`, `public`, `module_ctx`, `call`, `check`,
`comments_client`): так тест бачить саме те, що виконає сервер, зокрема `ctx['ModuleError']`, який ядро кладе в `ctx`.

⛔ Жодного реального запиту до Supabase чи будь-якого хоста поза машиною. Світ тесту:
  * ПІДСТАВНИЙ REST Supabase — `ThreadingHTTPServer` на `127.0.0.1:0` у потоці: `GET`/`PATCH /rest/v1/comments` з
    фільтрами `eq.` із запиту, `apikey`, `Prefer: return=representation`; записує КОЖЕН запит; уміє 401, «нема таблиці»
    (`PGRST205`, `42P01`, голе 404), переадресацію на «чужий» сервер, довільні перевизначення відповіді;
  * ДРУГИЙ такий сервер (`evil`) — куди веде переадресація: він мусить лишитись без жодного запиту;
  * РОЗТЯЖКА (`Tripwire`): `socket.getaddrinfo` і `socket.socket.connect` пропускають лише `127.0.0.1`; будь-яка спроба
    піти деінде — запис і відмова, а прибирання тесту падає, навіть якщо модуль цю відмову проковтнув.

Шов мережі. Модуль працює лише з `https://<проєкт>.supabase.co` (це вимога модуля, і її не послаблено), тож локальному HTTP-серверу
така адреса не підходить, а піднімати TLS заради тесту зайве. Шов — імʼя `_open` у глобалах модуля: ЄДИНЕ місце, де запит іде в
мережу (`_opener.open(req, timeout=timeout)`; тайм-аут приходить із виклику: `check` — 4 с, `list`/`resolve` — 8 с). Тест ОБГОРТАЄ справжню функцію: записує, ЩО модуль адресував (повний `https://`-URL,
метод, заголовки, тіло), а до справжньої `_open` передає той самий запит, переписаний на `http://127.0.0.1:<порт підставного
сервера>`. Решта шляху справжня: побудова запиту й заголовків, власний обробник редиректів, що нікуди не веде, розбір `HTTPError`.
У виробничому коді спеціального «тестового» входу нема: `_open(req)` — звичайна функція.

Кожен тест має власні `HOME`, `DEAI_HOME`, `DC_TASKS_FILE`; справжній `~/.deai` стереже `spaces_guard`.
"""
import ast
import base64
import hashlib
import http.client
import json
import os
import random
import re
import socket
import socketserver
import ssl
import stat
import sys
import threading
import time
import traceback
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_comments_agent as tca  # noqa: E402  — `ServerEnv` (два простори, сервер, `inbox`), `cl`
import sbconf  # noqa: E402
import test_comments_role as tcr  # noqa: E402
import test_modules as tm  # noqa: E402  — `Env`

MODULE_DIR = os.path.join(ROOT, 'app', 'modules', 'supabase-comments')
SERVER = os.path.join(MODULE_DIR, 'server.py')
ADAPTER = os.path.join(MODULE_DIR, 'adapter.js')
BUNDLE = os.path.join(MODULE_DIR, 'supabase.min.js')
MID = 'supabase-comments'
HOST = 'abcdefghijkl.supabase.co'                       # вигаданий проєкт: ні справжніх імен, ні справжніх ref
URL = f'https://{HOST}'
KEY = 'eyJhbGciOiJIUzI1NiJ9.TEST-payload_x.TEST-signature_y'
#: SHA-256 `supabase-js@2.110.0` UMD (`dist/umd/supabase.js`) — чужий код, вендорений БЕЗ змін.
BUNDLE_SHA256 = '2db2912f16939a3b21b472980a7ada746b33a6a40708bc555cb0be255c6eb5b1'
LOOPBACK = ('127.0.0.1',)
PROXY_VARS = ('http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy', 'no_proxy')
TABLE = '/rest/v1/comments'
REPLIES = '/rest/v1/comment_replies'
_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _read(path, mode='rb'):
    with open(path, mode) as f:
        return f.read()


def sha256(path):
    return hashlib.sha256(_read(path)).hexdigest()


def q(text):
    """Те саме кодування значень фільтра, що чекаємо від модуля: усе, крім `[A-Za-z0-9_.~-]`, — `%XX`."""
    return urllib.parse.quote(text, safe='')


def row(cid, channel, **over):
    """Рядок таблиці `comments` у формі PostgREST (snake_case + службові колонки)."""
    out = {'id': cid, 'project_id': channel, 'author': 'Олена', 'text': f'текст {cid}', 'status': 'open',
           'fp': {'tag': 'button', 'path': ['div[1]', 'button[0]']},
           'html_snapshot': {'text': 'Купити', 'outerHTML': '<button>Купити</button>'},
           'meta': {'version': '2/x', 'seq': 3}, 'born_v': 2, 'resolved_v': None, 'resolve_reason': None,
           'ts': '19.10.2026 10:00', 'created_at': '2026-10-19T10:00:00Z'}
    out.update(over)
    return out


# ------------------------------------------------------------------------------------- підставні сервери

class _HTTPD(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):                              # без `getfqdn`: жодних зайвих DNS-запитів навіть на старті
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = '127.0.0.1', self.server_address[1]


class FakeSupabase:
    """REST Supabase на `127.0.0.1`: таблиця `comments` у памʼяті, журнал запитів, сценарії відмов."""

    def __init__(self, key=KEY):
        self.key = key
        self.rows = []
        self.replies = []                               # таблиця `comment_replies` (рядки у формі PostgREST)
        self.no_replies_table = None                    # те саме, що `no_table`, але лише для `comment_replies`
        self.requests = []                              # {method, path, raw_path, raw_query, query, headers, body}
        self.no_table = None                            # None | 'PGRST205' | '42P01' | 'plain'
        self.redirect_to = None                         # `http://127.0.0.1:<порт>` «чужого» сервера: відповідь — 3xx на нього
        self.redirect_code = 302
        self.echo_key = False                           # тіла помилок повторюють ключ із заголовка (як би міг якийсь проксі)
        self.overrides = []                             # {method, status, body, headers, delay, times}
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def _serve(self):
                n = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(n) if n else b''
                parts = urllib.parse.urlsplit(self.path)
                rec = {'method': self.command, 'path': parts.path, 'raw_path': self.path, 'raw_query': parts.query,
                       'query': urllib.parse.parse_qs(parts.query, keep_blank_values=True),
                       'headers': {k.lower(): v for k, v in self.headers.items()}, 'body': body}
                with outer._lock:
                    outer.requests.append(rec)
                status, payload, headers, delay = outer.respond(rec)
                if delay:
                    time.sleep(delay)
                if payload is None:
                    data, ctype = b'', 'application/json'
                elif isinstance(payload, (dict, type([]))):
                    data, ctype = json.dumps(payload).encode('utf-8'), 'application/json'
                elif isinstance(payload, bytes):
                    data, ctype = payload, 'application/json'
                else:
                    data, ctype = str(payload).encode('utf-8'), 'text/html; charset=utf-8'
                try:
                    self.send_response(status)
                    for k, v in (headers or {}).items():
                        self.send_header(k, v)
                    self.send_header('Content-Type', ctype)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_GET = do_PATCH = do_POST = do_DELETE = _serve

            def log_message(self, *args):
                pass

        self.httpd = _HTTPD(('127.0.0.1', 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base = f'http://127.0.0.1:{self.port}'
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        self.stopped = False

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)

    # ---- сценарій
    def override(self, method, status, body=None, headers=None, delay=0, times=None, path=None, when=None):
        """`path` — лише для запитів на цей шлях (`TABLE`, `REPLIES`); `when(rec)` — лише коли предикат істинний; без них — на будь-який."""
        self.overrides.append({'method': method, 'status': status, 'body': body, 'headers': headers or {},
                               'delay': delay, 'times': times, 'path': path, 'when': when})

    def reqs(self, method=None):
        return [r for r in self.requests if method is None or r['method'] == method]

    def _err(self, rec, status, code, message):
        """Тіло помилки PostgREST; з `echo_key` повторює ключ із заголовка (і в `hint`, `details`)."""
        sent = rec['headers'].get('apikey', '')
        msg = f'{message} [{sent}]' if self.echo_key else message
        body = {'code': code, 'message': msg, 'details': f'key={sent}' if self.echo_key else None,
                'hint': f'Authorization: Bearer {sent}' if self.echo_key else None}
        return status, body, {}, 0

    # ---- відповіді
    def respond(self, rec):
        for o in self.overrides:
            if (o['method'] in (None, rec['method']) and o.get('path') in (None, rec['path']) and (o.get('when') is None or o['when'](rec))
                    and (o['times'] is None or o['times'] > 0)):
                if o['times'] is not None:
                    o['times'] -= 1
                return o['status'], o['body'], o['headers'], o['delay']
        if self.redirect_to:
            return self.redirect_code, None, {'Location': self.redirect_to + rec['raw_path']}, 0
        if rec['headers'].get('apikey') != self.key:
            return self._err(rec, 401, 'PGRST301', 'Invalid API key')
        if rec['path'] not in (TABLE, REPLIES):
            return 404, {'message': 'no such route'}, {}, 0
        replies = rec['path'] == REPLIES
        name = 'comment_replies' if replies else 'comments'
        scenario = self.no_replies_table if replies else self.no_table
        if scenario == 'PGRST205':
            return self._err(rec, 404, 'PGRST205', f"Could not find the table 'public.{name}' in the schema cache")
        if scenario == '42P01':
            return self._err(rec, 404, '42P01', f'relation "public.{name}" does not exist')
        if scenario == 'plain':
            return 404, 'Not Found', {}, 0
        store = self.replies if replies else self.rows
        if rec['method'] == 'POST':
            if not replies:
                return 405, {'message': 'method not allowed'}, {}, 0
            new = json.loads(rec['body'] or b'{}')
            new.setdefault('created_at', f'2026-11-20T10:{len(store):02d}:00Z')
            store.append(new)
            if 'return=representation' in rec['headers'].get('prefer', ''):
                return 201, [dict(new)], {}, 0
            return 201, None, {}, 0
        reserved = ('select', 'order', 'limit', 'offset')
        matched = list(store)
        for k, vals in rec['query'].items():
            if k in reserved:
                continue
            for v in vals:
                if v.startswith('in.(') and v.endswith(')'):
                    allowed = self._in_values(v[4:-1])
                    matched = [r for r in matched if str(r.get(k)) in allowed]
                elif v.startswith('eq.'):
                    matched = [r for r in matched if str(r.get(k)) == v[3:]]
                else:
                    return self._err(rec, 400, 'PGRST100', f'unsupported operator in {k}')
        cols = (rec['query'].get('select') or ['*'])[0]
        if rec['method'] == 'GET':
            order = (rec['query'].get('order') or [''])[0]
            for part in reversed([x for x in order.split(',') if x]):     # `a.desc,b.asc`: стабільне сортування з останнього ключа
                col, _, direction = part.partition('.')
                matched.sort(key=lambda r, col=col: str(r.get(col)), reverse=direction == 'desc')
            if cols != '*':
                matched = [{c.split(':')[0]: self._col(r, c) for c in cols.split(',')} for r in matched]
            lim = (rec['query'].get('limit') or [None])[0]
            if lim is not None:
                matched = matched[:int(lim)]
            return 200, matched, {}, 0
        if rec['method'] == 'PATCH':
            patch = json.loads(rec['body'] or b'{}')
            for r in matched:
                r.update(patch)
            if 'return=representation' in rec['headers'].get('prefer', ''):
                return 200, ([{c: r.get(c) for c in cols.split(',')} for r in matched] if cols != '*' else matched), {}, 0
            return 204, None, {}, 0
        return 405, {'message': 'method not allowed'}, {}, 0

    @staticmethod
    def _col(r, c):
        """Колонка `select`: `ім'я` або псевдонім `alias:meta->>key` (текст ключа jsonb `meta`, як у PostgREST)."""
        if ':' not in c:
            return r.get(c)
        _, expr = c.split(':', 1)
        col, key = expr.split('->>')
        val = (r.get(col) or {}).get(key)
        return None if val is None else str(val)

    @staticmethod
    def _in_values(text):
        """Вміст `in.(…)` PostgREST: значення через кому, у подвійних лапках — з `\\"` і `\\\\` усередині (кома в лапках — не роздільник)."""
        out, cur, quoted, i = [], '', False, 0
        while i < len(text):
            ch = text[i]
            if quoted and ch == '\\' and i + 1 < len(text):
                cur += text[i + 1]
                i += 2
                continue
            if ch == '"':
                quoted = not quoted
            elif ch == ',' and not quoted:
                out.append(cur)
                cur = ''
            else:
                cur += ch
            i += 1
        out.append(cur)
        return out


class Tripwire:
    """Лише `127.0.0.1`: усе інше — запис у `violations` і `OSError`. Стереже `getaddrinfo` (імена) і `socket.connect` (сама
    спроба зʼєднання, навіть за готовою адресою)."""

    def __init__(self):
        self.violations = []
        self._patches = []

    def start(self):
        real_gai, real_connect, real_connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex
        outer = self

        def gai(host, *a, **k):
            if host not in LOOPBACK:
                outer.violations.append(('getaddrinfo', str(host)))
                raise OSError(f'tripwire: {host}')
            return real_gai(host, *a, **k)

        def connect(sock, address):
            host = address[0] if isinstance(address, tuple) else address
            if host not in LOOPBACK:
                outer.violations.append(('connect', str(host)))
                raise OSError(f'tripwire: {host}')
            return real_connect(sock, address)

        def connect_ex(sock, address):
            host = address[0] if isinstance(address, tuple) else address
            if host not in LOOPBACK:
                outer.violations.append(('connect_ex', str(host)))
                return 1
            return real_connect_ex(sock, address)

        for obj, name, fn in ((socket, 'getaddrinfo', gai), (socket.socket, 'connect', connect),
                              (socket.socket, 'connect_ex', connect_ex)):
            p = mock.patch.object(obj, name, fn)
            p.start()
            self._patches.append(p)

    def stop(self):
        for p in reversed(self._patches):
            p.stop()
        self._patches = []


class SeamMixin:
    """Підставний світ для тестів модуля: тека/простір/секрети (`tm.Env`), справжній каталог `app/modules`, розтяжка, REST
    Supabase і шов `_open` (див. docstring файла). `self.seen` — те, що МОДУЛЬ адресував (до переписування на loopback)."""

    def no_proxy_env(self):
        """Проксі з оточення машини вимкнено ДО завантаження модуля (його `_opener` читає оточення при створенні): запит на
        loopback не мусить іти через чужий проксі. Чіпає лише змінні проксі й відновлює їх."""
        saved = {k: v for k, v in os.environ.items() if k.lower() in PROXY_VARS}
        for k in saved:
            del os.environ[k]
        os.environ['NO_PROXY'] = os.environ['no_proxy'] = '*'

        def restore():
            for k in ('NO_PROXY', 'no_proxy'):
                os.environ.pop(k, None)
            os.environ.update(saved)
        self.addCleanup(restore)

    def seam_up(self, module=None):
        mod = module or dm.catalog()[MID]
        self.m = mod
        self.g = mod.fn('check').__globals__
        self.trip = Tripwire()
        self.trip.start()
        self.addCleanup(self._tripwire_end)
        self.api = FakeSupabase()
        self.addCleanup(self.api.stop)
        self.evil = None
        self.seen = []
        real_open = self.g['_open']

        def mapped(req, timeout):
            self.seen.append({'url': req.full_url, 'method': req.get_method(), 'data': req.data, 'timeout': timeout,
                              'headers': {k.lower(): v for k, v in req.header_items()}})
            sp = urllib.parse.urlsplit(req.full_url)
            new = urllib.request.Request(f'{self.api.base}{sp.path}' + (f'?{sp.query}' if sp.query else ''),
                                         data=req.data, method=req.get_method(), headers=dict(req.header_items()))
            return real_open(new, timeout)
        patch = mock.patch.dict(self.g, {'_open': mapped})
        patch.start()
        self.addCleanup(patch.stop)

    def _tripwire_end(self):
        self.trip.stop()
        self.assertEqual(self.trip.violations, [], 'вихід за межі 127.0.0.1')

    def evil_server(self):
        """«Чужий» сервер: куди веде переадресація; ключ у нього зʼявитись не може."""
        if self.evil is None:
            self.evil = FakeSupabase()
            self.addCleanup(self.evil.stop)
        return self.evil

    def patch_globals(self, **over):
        p = mock.patch.dict(self.g, over)
        p.start()
        self.addCleanup(p.stop)

    # ---- допоміжне
    def ctx(self, url=URL, key=KEY):
        """Справжній `ctx` ядра: секрет `key` — через `write_secrets`, `url` — через налаштування модуля."""
        dm.write_secrets(self.sp['id'], MID, {'key': key} if key is not None else {})
        dm.write_module_state(self.sp, MID, settings={'url': url})
        return dm.module_ctx(self.sp, self.m)

    def hand_ctx(self, settings=None, secrets=None):
        """Рукописний `ctx` (як складає ядро) із довільними налаштуваннями — те, що `write_module_state` не пропустив би."""
        return {'space': {'id': self.sp['id'], 'path': self.sp['path']}, 'settings': settings if settings is not None else {'url': URL},
                'secrets': secrets if secrets is not None else {'key': KEY}, 'folder_ok': lambda f: (True, None),
                'ModuleError': dm.ModuleError}

    def fn(self, name):
        return self.m.fn(name)

    def fails(self, fn, *args, ctx=None):
        try:
            self.fn(fn)(ctx if ctx is not None else self.ctx(), *args)
        except BaseException as e:  # noqa: BLE001
            return e
        self.fail('очікували виняток')

    @staticmethod
    def exc_texts(e):
        out = [str(e), repr(e), getattr(e, 'message', ''), getattr(e, '_full', '')]
        out.append(''.join(traceback.format_exception(type(e), e, e.__traceback__)))
        return out

    def blob(self, rec, skip_auth=False):
        heads = ''.join(f'{k}: {v}\n' for k, v in rec['headers'].items() if not (skip_auth and k in ('apikey', 'authorization')))
        return (rec['method'] + ' ' + rec['raw_path'] + '\n' + heads).encode('utf-8') + rec['body']


class Base(SeamMixin, tm.Env):
    """Справжній `app/modules`, справжній `deai_modules`; тимчасові HOME/DEAI_HOME/DC_TASKS_FILE; підставний Supabase."""

    def setUp(self):
        super().setUp()
        self.no_proxy_env()
        # Простори пишуться в тимчасовий `DEAI_HOME`, а не у справжній `~/.deai`: `Env.setUp` його вже виставив, тут він підтверджений
        # явно (так вимагає охоронець `test_serve.TestsCannotWriteLiveConfig`); оточення відновлює `Env.tearDown`.
        os.environ['DEAI_HOME'] = self.deai
        patch = mock.patch.object(dm, 'builtin_dir', tm._REAL_BUILTIN_DIR)         # `Env` підмінив її на порожню теку
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()
        self.sp = self.new_space('Alpha')
        dm.write_module_state(self.sp, MID, enabled=True, settings={'url': URL})
        dm.write_secrets(self.sp['id'], MID, {'key': KEY})
        self.seam_up()

    def chan(self, tid='task-1', internal=False):
        return dm.channel_for(self.sp, tid, internal)


# ---------------------------------------------------------------------------------------------- каталог

class CatalogTest(Base):
    def test_the_real_catalog_loads_the_module_as_a_comments_provider(self):
        m = dm.catalog()[MID]
        self.assertEqual((m.status, m.error), ('ok', None))
        self.assertEqual((m.roles, m.name, m.version, m.api, m.dir), (['comments'], 'Supabase', '1.3.0', 1, MODULE_DIR))
        self.assertEqual(m.client, ('supabase.min.js', 'adapter.js'))
        self.assertEqual(m.secret_keys(), ['key'])
        self.assertEqual(m.private_secret_keys(), [], 'публічний ключ — єдиний секрет модуля, і він public')
        for name in ('check', 'client_config', 'list', 'resolve'):
            self.assertTrue(callable(m.fn(name)), name)
        self.assertEqual(dm.provider('comments', self.sp).id, MID)
        self.assertEqual(dm.capabilities(self.sp)['comments'], MID)

    def test_the_manifest_on_disk_is_the_one_of_the_spec(self):
        with open(os.path.join(MODULE_DIR, 'module.json'), encoding='utf-8') as f:
            man = json.load(f)
        self.assertEqual(man, {
            'api': 1, 'id': 'supabase-comments', 'name': 'Supabase', 'version': '1.3.0', 'roles': ['comments'],
            'client': ['supabase.min.js', 'adapter.js'],
            'settings': [
                {'key': 'url', 'type': 'text', 'label': 'Адреса проєкту (https://<ref>.supabase.co)', 'required': True},
                {'key': 'key', 'type': 'secret', 'public': True, 'label': 'Публічний ключ (anon / publishable)',
                 'required': True},
                {'key': 'shots_bucket', 'type': 'text', 'label': 'Кошик Storage для скріншотів пінів (необовʼязково)',
                 'required': False},
                {'key': 'compat', 'type': 'select', 'required': False, 'default': '',
                 'label': 'Канали коментарів (⚠ зміна значення на живому просторі відриває наявну історію пінів: канал інший)',
                 'options': [{'value': '', 'label': 'Deai: deai/<простір>/<задача>'},
                             {'value': 'comment-layer', 'label': 'comment-layer: comment_project або dc/<задача>'}]}]})

    def test_the_declared_client_files_are_regular_unlinked_and_small(self):
        for name in dm.catalog()[MID].client:
            st = os.lstat(os.path.join(MODULE_DIR, name))
            self.assertTrue(stat.S_ISREG(st.st_mode), name)
            self.assertEqual(st.st_nlink, 1, name)
            self.assertLessEqual(st.st_size, dm.MAX_CLIENT_BYTES, name)
            self.assertRegex(name, dm.CLIENT_RE.pattern)

    def test_the_vendored_supabase_js_is_pinned_unchanged(self):
        self.assertEqual(sha256(BUNDLE), BUNDLE_SHA256)
        text = _read(BUNDLE).decode('utf-8')
        self.assertIn('2.110.0', text)
        self.assertIn('supabase-js/2.110.0', text)

    def test_the_license_of_supabase_js_is_shipped_with_it(self):
        lic = _read(os.path.join(MODULE_DIR, 'LICENSE-supabase-js')).decode('utf-8')
        self.assertTrue(lic.startswith('MIT License'))
        self.assertIn('Copyright (c) 2020 Supabase', lic)
        self.assertIn('Permission is hereby granted, free of charge', lic)

    def test_the_folder_ships_the_schema_the_readme_and_nothing_stray(self):
        self.assertEqual(sorted(n for n in os.listdir(MODULE_DIR) if n != '__pycache__'),
                         ['LICENSE-supabase-js', 'README.md', 'adapter.js', 'module.json', 'replies.sql', 'schema.sql', 'server.py',
                          'supabase.min.js'])

    def test_loading_leaves_no_bytecode_behind(self):
        dm.catalog()
        self.assertFalse(os.path.exists(os.path.join(MODULE_DIR, '__pycache__')))

    def test_the_constants_are_the_documented_ones(self):
        self.assertEqual((self.g['CHECK_TIMEOUT_S'], self.g['CALL_TIMEOUT_S'], self.g['MAX_ROWS']), (4, 8, 5000))
        self.assertLess(self.g['CHECK_TIMEOUT_S'], dm.CHECK_TIMEOUT, 'модуль мусить відповісти РАНІШЕ за ядро: інакше check-timeout')
        self.assertLess(self.g['CALL_TIMEOUT_S'], dm.COMMENTS_TIMEOUT)


# ------------------------------------------------------------------------------------------ правило адреси

BAD_URLS = [
    'http://abcdefghijkl.supabase.co', 'HTTP://abcdefghijkl.supabase.co', 'ftp://abcdefghijkl.supabase.co',
    'file:///etc/passwd', 'abcdefghijkl.supabase.co', '//abcdefghijkl.supabase.co', 'https:abcdefghijkl.supabase.co',
    'https:/abcdefghijkl.supabase.co', 'https://', 'https:///rest', '',
    'https://127.0.0.1', 'https://127.0.0.1:8000', 'https://2130706433', 'https://0x7f.1', 'https://169.254.169.254',
    'https://10.0.0.1', 'https://[::1]', 'https://[::1]:443', 'https://localhost', 'https://localhost:8443',
    'https://supabase', 'https://abcdefghijkl.supabase.co.', 'https://.supabase.co', 'https://a..supabase.co',
    'https://-a.supabase.co', 'https://a-.supabase.co', 'https://abc.123', 'https://abc.supabase.1',
    'https://abcdefghijkl.supabase.co/rest/v1', 'https://abcdefghijkl.supabase.co/rest/v1/', 'https://abcdefghijkl.supabase.co//',
    'https://abcdefghijkl.supabase.co/?x=1', 'https://abcdefghijkl.supabase.co?x=1', 'https://abcdefghijkl.supabase.co/#f',
    'https://abcdefghijkl.supabase.co#f', 'https://abcdefghijkl.supabase.co/?',
    'https://user@abcdefghijkl.supabase.co', 'https://user:pw@abcdefghijkl.supabase.co', 'https://@abcdefghijkl.supabase.co',
    'https://abcdefghijkl.supabase.co@evil.example.com', 'https://abcdefghijkl.supabase.co\\@evil.example.com',
    'https://abcdefghijkl.supabase.co\\evil', 'https://abcdefghijkl.supabase.co:99999', 'https://abcdefghijkl.supabase.co:abc',
    'https://abcdefghijkl.supabase.co:', 'https://абв.укр', 'https://abcdefghijkl.supabase.co/путь', 'https://abc de.supabase.co',
    'https://abcdefghijkl.supabase.co\x00', 'https://abc\ndefghijkl.supabase.co', 'https://abc\tdefghijkl.supabase.co',
    'https://abcdefghijkl.supabase.co/ x', 'https://' + 'a' * 64 + '.supabase.co',
    'https://' + 'a.' * 130 + 'co',
]
OK_URLS = {
    'https://abcdefghijkl.supabase.co': 'https://abcdefghijkl.supabase.co',
    'https://abcdefghijkl.supabase.co/': 'https://abcdefghijkl.supabase.co',
    '  https://abcdefghijkl.supabase.co/  ': 'https://abcdefghijkl.supabase.co',
    'HTTPS://ABCDEFGHIJKL.Supabase.CO/': 'https://abcdefghijkl.supabase.co',
    'https://abcdefghijkl.supabase.co:443': 'https://abcdefghijkl.supabase.co:443',
    'https://db.team.example.org': 'https://db.team.example.org',
    'https://db.team.example.org:8443/': 'https://db.team.example.org:8443',
    'https://xn--e1afmkfd.xn--p1ai': 'https://xn--e1afmkfd.xn--p1ai',
    'https://a.bc': 'https://a.bc',
}


class UrlRuleTest(Base):
    """`url` — лише `https://`, хост — DNS-імʼя (те саме правило, що в ядра для `url`-модулів: ≥ 2 міток, остання з літери, жодних
    IP і `localhost`), без облікових даних, фрагмента, параметрів і шляху, окрім порожнього чи `/`. Відмова — `bad-settings`, текст
    без самої адреси (вона могла б нести пароль), і запиту в мережу не було."""

    def test_good_addresses_become_the_canonical_origin(self):
        for given, want in OK_URLS.items():
            cfg = self.fn('client_config')(self.hand_ctx({'url': given}))
            self.assertEqual(cfg, {'url': want, 'key': KEY}, given)

    def test_every_bad_address_is_a_bad_settings_refusal_everywhere_without_a_request(self):
        messages = set()
        for bad in BAD_URLS:
            ctx = self.hand_ctx({'url': bad})
            for name, args in (('client_config', ()), ('list', (self.chan(),)), ('resolve', (self.chan(), 'c1', 'r'))):
                with self.assertRaises(dm.ModuleError, msg=f'{name} {bad!r}') as cm:
                    self.fn(name)(ctx, *args)
                self.assertEqual(cm.exception.code, 'bad-settings', f'{name} {bad!r}')
                self.assertEqual(cm.exception.status, 400)
                self.assertTrue(cm.exception.message)
                messages.add(cm.exception.message)
            res = self.fn('check')(ctx)
            self.assertEqual((res['ok'], res['error']), (False, 'bad-settings'), bad)
            self.assertTrue(res['detail'])
            messages.add(res['detail'])
        self.assertEqual(len(messages), 1, 'один фіксований текст на всі адреси: самої адреси (з паролем?) в ньому нема')
        self.assertEqual(self.seen, [], 'жодного запиту до мережі')
        self.assertEqual(self.api.requests, [])

    def test_a_non_text_address_is_refused_the_same_way(self):
        for bad in (None, 5, True, ['https://abcdefghijkl.supabase.co'], {'url': URL}, b'https://abcdefghijkl.supabase.co'):
            ctx = self.hand_ctx({'url': bad})
            with self.assertRaises(dm.ModuleError, msg=repr(bad)) as cm:
                self.fn('client_config')(ctx)
            self.assertEqual(cm.exception.code, 'bad-settings')
            self.assertEqual(self.fn('check')(ctx)['error'], 'bad-settings')
        ctx = self.hand_ctx({})
        self.assertEqual(self.fn('check')(ctx)['error'], 'bad-settings')
        self.assertEqual(self.seen, [])

    def test_the_refusal_keeps_its_code_through_the_core(self):
        ctx = self.ctx(url='http://abcdefghijkl.supabase.co')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(self.m, 'client_config', ctx)
        self.assertEqual((cm.exception.code, cm.exception.status), ('bad-settings', 400))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.comments_client(self.sp, self.m)
        self.assertEqual(cm.exception.code, 'bad-settings')
        verdict = dm.check(self.sp, MID)
        self.assertEqual((verdict['ok'], verdict['error']), (False, 'bad-settings'))
        self.assertEqual(self.seen, [])

    def test_a_handwritten_ctx_without_the_core_class_still_refuses_loudly(self):
        ctx = self.hand_ctx({'url': 'http://abcdefghijkl.supabase.co'})
        del ctx['ModuleError']
        with self.assertRaises(RuntimeError) as cm:
            self.fn('client_config')(ctx)
        self.assertIn('bad-settings', str(cm.exception))


# ------------------------------------------------------------------------------------------ client_config

class ClientConfigTest(Base):
    def test_the_exact_shape_is_the_url_and_the_public_key(self):
        cfg = self.fn('client_config')(self.ctx())
        self.assertEqual(cfg, {'url': URL, 'key': KEY})
        self.assertEqual(self.seen, [], 'client_config у мережу не ходить')

    def test_the_core_accepts_it_as_a_public_config(self):
        self.ctx()
        cfg = dm.comments_client(self.sp, self.m)
        self.assertEqual(cfg, {'url': URL, 'key': KEY})
        self.assertEqual(self.seen, [])

    def test_the_address_is_normalised_and_the_key_trimmed(self):
        cfg = self.fn('client_config')(self.hand_ctx({'url': URL + '/'}, {'key': '  ' + KEY + '\n'}))
        self.assertEqual(cfg, {'url': URL, 'key': KEY})

    def test_a_missing_or_unusable_key_is_a_bad_settings_refusal(self):
        messages = set()
        for secrets in ({}, {'key': ''}, {'key': '   '}, {'key': 'two words'}, {'key': 'a\nb'}, {'key': 'k\r\nX-Evil: 1'},
                        {'key': 'ключ'}, {'key': 'k\x00'}, {'key': None}, {'key': 5}):
            ctx = self.hand_ctx(secrets=secrets)
            with self.assertRaises(dm.ModuleError, msg=repr(secrets)) as cm:
                self.fn('client_config')(ctx)
            self.assertEqual(cm.exception.code, 'bad-settings')
            messages.add(cm.exception.message)
            for name, args in (('list', (self.chan(),)), ('resolve', (self.chan(), 'c1', 'r'))):
                with self.assertRaises(dm.ModuleError):
                    self.fn(name)(ctx, *args)
            res = self.fn('check')(ctx)
            self.assertEqual((res['ok'], res['error']), (False, 'bad-key'), secrets)
            for v in secrets.values():
                if isinstance(v, str) and v.isascii() and len(v.strip()) > 2:
                    self.assertNotIn(v.strip(), ' '.join(self.exc_texts(cm.exception)) + res['detail'])
        self.assertEqual(len(messages), 2, 'два фіксовані тексти (не задано / недопустимі символи): значення ключа в них не потрапляє')
        self.assertEqual(self.seen, [], 'зіпсований ключ не доходить до заголовка (і не ламає його переносом рядка)')

    def test_shots_bucket_in_config(self):
        cfg = self.fn('client_config')(self.hand_ctx({'url': URL, 'shots_bucket': 'overview-thumbs'}))
        self.assertEqual(cfg, {'url': URL, 'key': KEY, 'shotsBucket': 'overview-thumbs'})
        for raw in (None, '', '  ', ' \t\n'):
            st = {'url': URL} if raw is None else {'url': URL, 'shots_bucket': raw}
            self.assertEqual(self.fn('client_config')(self.hand_ctx(st)), {'url': URL, 'key': KEY}, repr(raw))
        self.assertEqual(self.seen, [])

    def test_bad_shots_bucket(self):
        for bad in ('Overview', 'a/b', '../x', '-x', 'x' * 64, 5, ['a'], True, 'ключ', 'a b', 'a\nb', '_x'):
            ctx = self.hand_ctx({'url': URL, 'shots_bucket': bad})
            with self.assertRaises(dm.ModuleError, msg=repr(bad)) as cm:
                self.fn('client_config')(ctx)
            self.assertEqual(cm.exception.code, 'bad-settings')
            if isinstance(bad, str) and len(bad.strip()) > 2:
                self.assertNotIn(bad.strip(), cm.exception.message, 'текст без значення')
        self.assertEqual(self.seen, [])

    def test_a_trimmed_bucket_is_accepted_and_trimmed(self):
        cfg = self.fn('client_config')(self.hand_ctx({'url': URL, 'shots_bucket': '  thumbs_2 \n'}))
        self.assertEqual(cfg['shotsBucket'], 'thumbs_2')

    def test_both_values_are_plain_text_in_the_page_config(self):
        cfg = self.fn('client_config')(self.ctx())
        self.assertEqual({type(v) for v in cfg.values()}, {str})
        self.assertLess(len(json.dumps(cfg)), dm.MAX_CLIENT_CONFIG)


# ------------------------------------------------------------------------------------------------- list

class ListTest(Base):
    def seed(self, chan, ids):
        self.api.rows += [row(i, chan) for i in ids]

    def test_the_request_is_one_get_filtered_by_the_quoted_channel(self):
        chan = self.chan('task-1')
        self.assertIn('/', chan)
        self.fn('list')(self.ctx(), chan)
        self.assertEqual([(r['method'], r['url']) for r in self.seen],
                         [('GET', f'{URL}{TABLE}?project_id=eq.{q(chan)}&order=id&select=*&limit=5001'),
                          ('GET', f'{URL}{REPLIES}?project_id=eq.{q(chan)}&order=created_at.asc,id.asc'
                                  f'&select=id,comment_id,author,text,ts,edited_ts,agent&limit=20001')])
        rec, rrec = self.api.requests
        self.assertEqual(rec['raw_path'], f'{TABLE}?project_id=eq.deai%2F{self.sp["id"]}%2Ftask-1&order=id&select=*&limit=5001')
        self.assertEqual(rec['body'], b'')
        self.assertEqual({k: v for k, v in rec['headers'].items() if k in ('apikey', 'authorization', 'accept')},
                         {'apikey': KEY, 'authorization': 'Bearer ' + KEY, 'accept': 'application/json'})
        self.assertEqual((rrec['path'], rrec['body']), (REPLIES, b''))

    def test_hostile_channels_stay_inside_one_filter(self):
        ctx = self.ctx()
        for chan in ('deai/s/t&status=eq.open', 'a#b', 'a%26b', 'a+b', 'a b', 'a,b(c)', 'a=b', "o'neil", 'a"b', 'a\\b', 'а/б/в',
                     '../x', 'a?b', 'x' * 190):
            self.api.requests.clear()
            self.fn('list')(ctx, chan)
            rec, rrec = self.api.requests
            self.assertEqual(set(rec['query']), {'project_id', 'order', 'select', 'limit'}, chan)
            self.assertEqual(rec['query']['project_id'], ['eq.' + chan], chan)
            self.assertEqual(rrec['query']['project_id'], ['eq.' + chan], chan)

    def test_only_rows_of_the_channel_come_back_ordered_by_id(self):
        chan, other = self.chan('t1'), self.chan('t2')
        self.seed(chan, ['c', 'a', 'b'])
        self.seed(other, ['z'])
        self.seed(self.chan('t1', internal=True), ['y'])
        got = self.fn('list')(self.ctx(), chan)
        self.assertEqual([c['id'] for c in got], ['a', 'b', 'c'])
        self.assertEqual(self.fn('list')(self.ctx(), self.chan('nothing')), [])

    def test_rows_are_mapped_into_the_commentlayer_shape(self):
        chan = self.chan()
        self.api.rows = [row('a', chan), row('b', chan, html_snapshot=None, meta=None, resolved_v=5, resolve_reason='готово',
                                             status='resolved', born_v=None, ts=None)]
        a, b = self.fn('list')(self.ctx(), chan)
        keys = ['id', 'author', 'text', 'status', 'fp', 'htmlSnapshot', 'meta', 'bornV', 'resolvedV', 'resolveReason', 'ts']
        self.assertEqual(sorted(a), sorted(keys))
        self.assertEqual(a, {'id': 'a', 'author': 'Олена', 'text': 'текст a', 'status': 'open',
                             'fp': {'tag': 'button', 'path': ['div[1]', 'button[0]']},
                             'htmlSnapshot': {'text': 'Купити', 'outerHTML': '<button>Купити</button>'},
                             'meta': {'version': '2/x', 'seq': 3}, 'bornV': 2, 'resolvedV': None, 'resolveReason': None,
                             'ts': '19.10.2026 10:00'})
        self.assertEqual((b['htmlSnapshot'], b['meta'], b['resolvedV'], b['resolveReason'], b['status'], b['bornV'], b['ts']),
                         (None, None, 5, 'готово', 'resolved', None, None))
        self.assertNotIn('project_id', a)
        self.assertNotIn('created_at', a)

    def test_the_core_reads_the_answer_as_pins_of_the_rest_shape(self):
        chan = self.chan()
        self.seed(chan, ['c0ffee01-aaaa', 'c0ffee02-bbbb'])
        pins = serve.agent_pins(self.fn('list')(self.ctx(), chan))
        self.assertEqual((pins.skipped, pins.truncated), (0, 0))
        self.assertEqual([p['id'] for p in pins], ['c0ffee01-aaaa', 'c0ffee02-bbbb'])
        self.assertEqual(pins[0]['born_v'], 2)
        self.assertEqual(pins[0]['author'], 'Олена')

    def test_the_request_is_capped_and_an_overflow_is_visible_to_the_core(self):
        """`limit` = `MAX_ROWS + 1`: рівно на одну більше за межу агента. Модуль нічого не обрізає — тож зайвий рядок
        доходить до ядра, і воно ЗАЯВЛЯЄ відкинуте (`truncated`), а не віддає «повний» список мовчки."""
        chan = self.chan()
        self.api.rows = [row(f'id{i:05d}', chan) for i in range(5003)]
        got = self.fn('list')(self.ctx(), chan)
        self.assertEqual(len(got), 5001)
        self.assertEqual(self.api.requests[0]['query']['limit'], ['5001'])
        pins = serve.agent_pins(got)
        self.assertEqual((len(pins), pins.truncated), (5000, 1))
        self.api.rows = self.api.rows[:5000]
        self.assertEqual(len(self.fn('list')(self.ctx(), chan)), 5000)

    def test_an_element_that_is_not_an_object_goes_through_for_the_core_to_count(self):
        self.api.override('GET', 200, [row('a', self.chan()), 'junk', 5, None])
        got = self.fn('list')(self.ctx(), self.chan())
        self.assertEqual([c['id'] if isinstance(c, dict) else c for c in got], ['a', 'junk', 5, None])
        self.assertEqual(serve.agent_pins(got).skipped, 3)

    def test_a_reply_that_is_not_a_list_is_an_error_never_an_empty_answer(self):
        for body in ({'message': 'x'}, 'not json at all', b'\xff\xfe', None, b'null', b'"str"', b'5', b'<html></html>'):
            self.api.overrides.clear()
            self.api.override('GET', 200, body)
            e = self.fails('list', self.chan())
            self.assertIsInstance(e, dm.ModuleError, repr(body))
            self.assertEqual(e.code, 'module-error', repr(body))
            self.assertTrue(e.message)
        self.api.overrides.clear()
        self.api.override('GET', 200, [])
        self.assertEqual(self.fn('list')(self.ctx(), self.chan()), [])

    def test_failures_are_module_errors_with_readable_texts(self):
        chan = self.chan()
        cases = [(401, {'code': 'PGRST301', 'message': 'Invalid API key'}, 'не прийняв ключ'),
                 (403, {'message': 'permission denied for table comments'}, 'відмовив у доступі'),
                 (404, {'code': 'PGRST205', 'message': "Could not find the table 'public.comments' in the schema cache"}, 'schema.sql'),
                 (400, {'code': '42P01', 'message': 'relation "public.comments" does not exist'}, 'schema.sql'),
                 (404, 'Not Found', 'schema.sql'),
                 (500, {'message': 'boom inside'}, 'HTTP 500'),
                 (503, None, 'HTTP 503')]
        for status, body, part in cases:
            self.api.overrides.clear()
            self.api.override('GET', status, body)
            e = self.fails('list', chan)
            self.assertIsInstance(e, dm.ModuleError, (status, body))
            self.assertEqual(e.code, 'module-error', (status, body))
            self.assertIn(part, e.message, (status, body))
            self.assertNotRegex(e.message, r'^_?\w*(?:Error|Exception)\b')
            self.assertLessEqual(len(e.message), 300)
        self.api.overrides.clear()
        self.api.override('GET', 500, {'message': 'boom inside'})
        self.assertIn('boom inside', self.fails('list', chan).message, 'текст самого сервісу — людині корисний')

    def test_a_dead_service_is_a_network_error(self):
        self.api.stop()
        e = self.fails('list', self.chan())
        self.assertEqual(e.code, 'module-error')
        self.assertIn('недоступний', e.message)

    def test_a_slow_service_is_cut_off_by_the_timeout(self):
        self.patch_globals(CALL_TIMEOUT_S=0.2)
        self.api.override('GET', 200, [], delay=1.5)
        started = time.monotonic()
        e = self.fails('list', self.chan())
        self.assertLess(time.monotonic() - started, 1.4)
        self.assertIn('недоступний', e.message)

    def test_list_and_resolve_use_the_call_budget_and_check_the_shorter_one(self):
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.fn('list')(self.ctx(), chan)
        self.fn('resolve')(self.ctx(), chan, 'a', 'r')
        self.fn('check')(self.ctx())
        # один дедлайн на виклик: кожен запит іде з `min(свій строк, що лишилося)` — трохи менше за повний бюджет, але ніколи не більше
        got = [r['timeout'] for r in self.seen]
        for t, full in zip(got, [8, 8, 8, 4, 4]):
            self.assertLessEqual(t, full)
            self.assertGreater(t, full - 1)
        self.assertEqual(len(got), 5, 'list: коментарі+відповіді, resolve, check: коментарі+відповіді')
        self.assertEqual(got[2], 8, 'resolve — один запит: його строк і є бюджет')

    def test_a_giant_answer_is_refused(self):
        self.patch_globals(MAX_BODY=1000)
        self.api.override('GET', 200, json.dumps([row('a', self.chan(), text='x' * 5000)]))
        e = self.fails('list', self.chan())
        self.assertEqual(e.code, 'module-error')
        self.assertIn('завелика', e.message)

    def test_an_empty_or_foreign_channel_is_refused_before_any_request(self):
        for chan in ('', None, 5, ['a'], b'x'):
            with self.assertRaises(dm.ModuleError, msg=repr(chan)) as cm:
                self.fn('list')(self.ctx(), chan)
            self.assertEqual(cm.exception.code, 'module-error')
        self.assertEqual(self.seen, [])

    def test_through_the_core_with_the_call_timeout(self):
        chan = self.chan()
        self.seed(chan, ['a'])
        ctx = self.ctx()
        got = dm.call(self.m, 'list', ctx, chan, timeout=dm.COMMENTS_TIMEOUT)
        self.assertEqual([c['id'] for c in got], ['a'])


class RecentTest(Base):
    """`recent` (Deai 0.27.0, необовʼязкова функція ролі): легкий опит відкритих для числа «нових» на вкладках."""

    def test_the_request_is_one_light_get_without_snapshots(self):
        chan = self.chan('x')
        self.api.override('GET', 200, [{'id': 'a', 'ts': 't', 'author': 'o', 'status': 'open', 'version': '2'}])
        got = self.fn('recent')(self.ctx(), chan)
        self.assertEqual(got, [{'id': 'a', 'ts': 't', 'author': 'o', 'status': 'open', 'version': '2'}])
        rec = self.api.requests[0]
        self.assertEqual(rec['method'], 'GET')
        self.assertEqual(rec['query']['project_id'], ['eq.' + chan])
        self.assertEqual(rec['query']['status'], ['eq.open'])
        self.assertEqual(rec['query']['select'], ['id,ts,author,status,version:meta->>version'])
        self.assertEqual(rec['query']['order'], ['created_at.desc'])
        self.assertEqual(rec['query']['limit'], ['200'])
        for heavy in ('html_snapshot', 'meta,', '*'):
            self.assertNotIn(heavy, rec['query']['select'][0])
        self.assertIn('project_id=eq.deai%2F', rec['raw_path'])

    def test_a_reply_that_is_not_a_list_is_a_module_error(self):
        for body in ({'message': 'x'}, 'not json', None, b'5'):
            self.api.overrides.clear()
            self.api.override('GET', 200, body)
            e = self.fails('recent', self.chan('x'))
            self.assertIsInstance(e, dm.ModuleError, repr(body))
            self.assertEqual(e.code, 'module-error', repr(body))

    def test_the_module_declares_recent_as_an_optional_role_function(self):
        self.assertTrue(callable(self.m.fn('recent')))


# --------------------------------------------------------------------------------------------- resolve

class ResolveTest(Base):
    def setUp(self):
        super().setUp()
        self.chan1, self.chan2 = self.chan('t1'), self.chan('t2')
        self.api.rows = [row('c1', self.chan1, resolved_v=7), row('c2', self.chan1), row('c3', self.chan2),
                         row('c1', self.chan2, text='same id in another project')]       # у справжній таблиці `id` — PK; тут перевіряємо ФІЛЬТР

    def test_the_patch_is_filtered_by_the_id_and_the_channel_and_sets_status_and_reason(self):
        self.assertIsNone(self.fn('resolve')(self.ctx(), self.chan1, 'c1', 'виправлено в it2'))
        self.assertEqual([(r['method'], r['url']) for r in self.seen],
                         [('PATCH', f'{URL}{TABLE}?id=eq.c1&project_id=eq.{q(self.chan1)}&select=id')])
        (rec,) = self.api.requests
        self.assertEqual(rec['raw_path'], f'{TABLE}?id=eq.c1&project_id=eq.deai%2F{self.sp["id"]}%2Ft1&select=id')
        self.assertEqual(json.loads(rec['body']), {'status': 'resolved', 'resolve_reason': 'виправлено в it2'})
        self.assertEqual(rec['headers']['prefer'], 'return=representation')
        self.assertEqual(rec['headers']['content-type'], 'application/json')
        self.assertEqual((rec['headers']['apikey'], rec['headers']['authorization']), (KEY, 'Bearer ' + KEY))
        self.assertEqual(rec['body'].decode('utf-8'), json.dumps({'status': 'resolved', 'resolve_reason': 'виправлено в it2'}, ensure_ascii=False),
                         'тіло — UTF-8 без \\u-екранів')

    def test_only_that_row_changes_and_the_iteration_is_left_alone(self):
        self.fn('resolve')(self.ctx(), self.chan1, 'c1', 'ok')
        by = {(r['id'], r['project_id']): r for r in self.api.rows}
        self.assertEqual((by[('c1', self.chan1)]['status'], by[('c1', self.chan1)]['resolve_reason']), ('resolved', 'ok'))
        self.assertEqual(by[('c1', self.chan1)]['resolved_v'], 7, 'номер ітерації в контракті ролі відсутній — стовпець не чіпаємо')
        for k in (('c2', self.chan1), ('c3', self.chan2), ('c1', self.chan2)):
            self.assertEqual((by[k]['status'], by[k]['resolve_reason']), ('open', None), k)
        self.assertNotIn('project_id', json.loads(self.api.requests[0]['body']), 'project_id незмінний: тригер його не пустить')

    def test_iteration_sets_resolved_v(self):
        self.assertIsNone(self.fn('resolve')(self.ctx(), self.chan1, 'c1', 'r', 3))
        (rec,) = self.api.requests
        self.assertEqual(json.loads(rec['body']), {'status': 'resolved', 'resolve_reason': 'r', 'resolved_v': 3})
        by = {(r['id'], r['project_id']): r for r in self.api.rows}
        self.assertEqual(by[('c1', self.chan1)]['resolved_v'], 3)
        for bad in (None, 0, -1, True, False, '3', 2.0, 3.5, [3], {}):
            self.api.requests.clear()
            self.fn('resolve')(self.ctx(), self.chan1, 'c2', 'r', bad)
            (rec,) = self.api.requests
            self.assertEqual(json.loads(rec['body']), {'status': 'resolved', 'resolve_reason': 'r'}, repr(bad))

    def test_it_is_effective_the_list_shows_the_comment_resolved(self):
        ctx = self.ctx()
        self.fn('resolve')(ctx, self.chan1, 'c1', 'готово')
        got = {c['id']: c for c in self.fn('list')(ctx, self.chan1)}
        self.assertEqual((got['c1']['status'], got['c1']['resolveReason']), ('resolved', 'готово'))
        self.assertEqual(got['c2']['status'], 'open')

    def test_it_is_idempotent(self):
        ctx = self.ctx()
        self.assertIsNone(self.fn('resolve')(ctx, self.chan1, 'c1', 'вперше'))
        self.assertIsNone(self.fn('resolve')(ctx, self.chan1, 'c1', 'вдруге'))
        self.assertEqual([c['status'] for c in self.fn('list')(ctx, self.chan1) if c['id'] == 'c1'], ['resolved'])

    def test_no_matching_row_is_an_error_with_the_spec_text(self):
        for chan, cid in ((self.chan1, 'nope'), (self.chan('t9'), 'c1'), (self.chan1, 'c3')):
            e = self.fails('resolve', chan, cid, 'r')
            self.assertIsInstance(e, dm.ModuleError)
            self.assertEqual((e.code, e.message), ('module-error', 'коментар не знайдено'), (chan, cid))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(self.m, 'resolve', self.ctx(), self.chan1, 'nope', 'r')
        self.assertEqual((cm.exception.code, cm.exception.message), ('module-error', 'коментар не знайдено'))

    def test_hostile_ids_never_add_a_filter_or_leave_their_parameter(self):
        ctx = self.ctx()
        for cid in ('x&status=eq.open', 'a#b', 'a%26b', 'a+b', 'a b', '../x', 'a?b', 'c1,c2', 'c1)', '*', 'ід', '\n', 'c1\r\nX: y'):
            self.api.requests.clear()
            e = self.fails('resolve', self.chan1, cid, 'r', ctx=ctx)
            self.assertEqual(e.message, 'коментар не знайдено', repr(cid))
            (rec,) = self.api.requests
            self.assertEqual(set(rec['query']), {'id', 'project_id', 'select'}, repr(cid))
            self.assertEqual(rec['query']['id'], ['eq.' + cid], repr(cid))
        self.assertTrue(all(r['status'] == 'open' for r in self.api.rows), 'жоден рядок не закрився')

    def test_an_empty_id_or_channel_never_becomes_an_unfiltered_patch(self):
        for chan, cid in (('', 'c1'), (self.chan1, ''), (None, 'c1'), (self.chan1, None), (self.chan1, 5), (5, 'c1')):
            with self.assertRaises(dm.ModuleError, msg=repr((chan, cid))) as cm:
                self.fn('resolve')(self.ctx(), chan, cid, 'r')
            self.assertEqual(cm.exception.code, 'module-error')
        self.assertEqual(self.seen, [])
        self.assertTrue(all(r['status'] == 'open' for r in self.api.rows))

    def test_the_reason_may_be_empty_or_missing_and_then_the_old_one_is_not_wiped(self):
        ctx = self.ctx()
        for reason in (None, '', 5, ['x']):
            self.api.requests.clear()
            self.fn('resolve')(ctx, self.chan1, 'c2', reason)
            self.assertEqual(json.loads(self.api.requests[0]['body']), {'status': 'resolved'}, repr(reason))
        self.fn('resolve')(ctx, self.chan1, 'c2', 'перша причина')
        self.fn('resolve')(ctx, self.chan1, 'c2', '')
        self.assertEqual(next(r for r in self.api.rows if (r['id'], r['project_id']) == ('c2', self.chan1))['resolve_reason'], 'перша причина')

    def test_the_answer_carries_only_ids_and_the_reply_is_counted_not_trusted_for_content(self):
        self.fn('resolve')(self.ctx(), self.chan1, 'c1', 'ok')
        self.assertEqual(self.api.requests[0]['query']['select'], ['id'])
        self.api.override('PATCH', 200, [{'id': 'c1'}])
        self.assertIsNone(self.fn('resolve')(self.ctx(), self.chan1, 'c1', 'ok'))

    def test_a_reply_that_cannot_confirm_the_change_is_an_error(self):
        for status, body in ((204, None), (200, {'message': 'x'}), (200, 'not json'), (200, None), (200, b'null')):
            self.api.overrides.clear()
            self.api.override('PATCH', status, body)
            e = self.fails('resolve', self.chan1, 'c1', 'r')
            self.assertEqual(e.code, 'module-error', (status, body))
            self.assertIn('не підтвердив', e.message, (status, body))

    def test_failures_are_module_errors_with_readable_texts(self):
        cases = [(401, {'message': 'Invalid API key'}, 'не прийняв ключ'), (403, None, 'відмовив у доступі'),
                 (404, {'code': 'PGRST205', 'message': 'no table'}, 'schema.sql'), (500, {'message': 'boom inside'}, 'boom inside')]
        for status, body, part in cases:
            self.api.overrides.clear()
            self.api.override('PATCH', status, body)
            e = self.fails('resolve', self.chan1, 'c1', 'r')
            self.assertEqual(e.code, 'module-error', (status, body))
            self.assertIn(part, e.message, (status, body))
        self.api.stop()
        e = self.fails('resolve', self.chan1, 'c1', 'r')
        self.assertIn('недоступний', e.message)

    def test_through_the_core_with_the_call_timeout_and_the_agent_whitelist_ids(self):
        ctx = self.ctx()
        for cid in ('c1', 'c0ffee01-aaaa-4bbb-8ccc-0123456789ab', 'c-1729000000000-k3j9x2', 'a.b:c_d-e'):
            if not any((r['id'], r['project_id']) == (cid, self.chan1) for r in self.api.rows):
                self.api.rows.append(row(cid, self.chan1))
            self.assertIsNone(dm.call(self.m, 'resolve', ctx, self.chan1, cid, 'ok', timeout=dm.COMMENTS_TIMEOUT))
        self.assertEqual(sum(r['status'] == 'resolved' for r in self.api.rows), 4)


# ----------------------------------------------------------------------------------------------- check

class CheckTest(Base):
    def test_ok_when_the_table_answers_and_it_only_reads_one_row(self):
        for body in ([], [{'id': 'a'}]):
            self.api.requests.clear()
            self.api.overrides.clear()
            self.api.override('GET', 200, body)
            res = self.fn('check')(self.ctx())
            self.assertEqual(res, {'ok': True, 'replies': True, 'detail': 'таблиці comments і comment_replies доступні'})
            rec, rrec = self.api.requests
            self.assertEqual((rrec['method'], rrec['raw_path'], rrec['body']), ('GET', f'{REPLIES}?select=id&limit=1', b''))
            self.assertEqual((rec['method'], rec['raw_path'], rec['body']), ('GET', f'{TABLE}?select=id&limit=1', b''))
            self.assertEqual((rec['headers']['apikey'], rec['headers']['authorization']), (KEY, 'Bearer ' + KEY))

    def test_bad_shots_bucket_verdict(self):
        for bad in ('Overview', 'a/b', '../x', '-x', 'x' * 64, 5):
            res = self.fn('check')(self.hand_ctx({'url': URL, 'shots_bucket': bad}))
            self.assertEqual((res['ok'], res['error']), (False, 'bad-settings'), repr(bad))
            if isinstance(bad, str) and len(bad) > 2:
                self.assertNotIn(bad, res['detail'])
        self.assertEqual(self.seen, [], 'вердикт — без мережі')
        self.assertEqual(self.api.requests, [])

    def test_bad_key_on_401_and_403(self):
        for status in (401, 403):
            self.api.overrides.clear()
            self.api.override('GET', status, {'message': 'Invalid API key'})
            res = self.fn('check')(self.ctx())
            self.assertEqual((res['ok'], res['error']), (False, 'bad-key'), status)
            self.assertIn(str(status), res['detail'])
        self.api.overrides.clear()
        self.api.override('GET', 401, None)
        self.assertEqual(self.fn('check')(self.ctx())['error'], 'bad-key')

    def test_a_wrong_key_at_the_real_server_is_bad_key(self):
        res = self.fn('check')(self.ctx(key='eyJ.some-other-key.sig'))
        self.assertEqual((res['ok'], res['error']), (False, 'bad-key'))

    def test_no_schema_on_404_and_on_the_postgrest_codes(self):
        for how in ('plain', 'PGRST205', '42P01'):
            self.api.no_table = how
            res = self.fn('check')(self.ctx())
            self.assertEqual((res['ok'], res['error']), (False, 'no-schema'), how)
            self.assertEqual(res['detail'], 'виконайте schema.sql у SQL-редакторі проєкту', how)
        self.api.no_table = None
        for status in (400, 404, 500):                                       # код таблиці важить більше за статус
            for code in ('42P01', 'PGRST205'):
                self.api.overrides.clear()
                self.api.override('GET', status, {'code': code, 'message': 'x'})
                self.assertEqual(self.fn('check')(self.ctx())['error'], 'no-schema', (status, code))

    def test_a_dead_service_is_network(self):
        self.api.stop()
        res = self.fn('check')(self.ctx())
        self.assertEqual((res['ok'], res['error']), (False, 'network'))
        self.assertIn('недоступний', res['detail'])

    def test_a_slow_service_is_network_after_the_timeout(self):
        self.patch_globals(CHECK_TIMEOUT_S=0.2)
        self.api.override('GET', 200, [], delay=1.5)
        started = time.monotonic()
        res = self.fn('check')(self.ctx())
        self.assertLess(time.monotonic() - started, 1.4)
        self.assertEqual((res['ok'], res['error']), (False, 'network'))

    def test_other_answers_are_a_supabase_error_with_the_status(self):
        for status in (400, 429, 500, 502, 503):
            self.api.overrides.clear()
            self.api.override('GET', status, {'message': 'boom inside'})
            res = self.fn('check')(self.ctx())
            self.assertEqual((res['ok'], res['error']), (False, 'supabase-error'), status)
            self.assertIn(f'HTTP {status}', res['detail'])
        for body in ({'message': 'x'}, 'captive portal', b'\xff\xfe', b'null', b'5'):          # 200, але не таблиця PostgREST
            self.api.overrides.clear()
            self.api.override('GET', 200, body)
            res = self.fn('check')(self.ctx())
            self.assertEqual((res['ok'], res['error']), (False, 'supabase-error'), repr(body))

    def test_a_redirect_is_an_error_not_a_hop(self):
        for code in (301, 302, 303, 307, 308):
            self.api.requests.clear()
            self.api.overrides.clear()
            self.api.override('GET', code, None, headers={'Location': 'https://elsewhere.example.com/rest/v1/comments'})
            res = self.fn('check')(self.ctx())
            self.assertEqual((res['ok'], res['error']), (False, 'supabase-error'), code)
            self.assertIn(f'HTTP {code}', res['detail'])
            self.assertEqual(len(self.api.requests), 1)

    def test_it_never_raises_and_never_writes(self):
        shapes = [(200, b''), (200, b'\x00' * 100), (500, b'\xff' * 100), (200, '<' * 100000), (401, json.dumps({'message': 5})),
                  (400, json.dumps({'code': ['x'], 'message': {'a': 1}})), (200, b'[' * 5000), (502, 'x' * 10000)]
        for status, body in shapes:
            self.api.overrides.clear()
            self.api.override('GET', status, body)
            res = self.fn('check')(self.ctx())
            self.assertIsInstance(res, dict)
            self.assertIsInstance(res['ok'], bool)
            self.assertLessEqual(len(res.get('detail', '')), 300)
        self.assertEqual({r['method'] for r in self.api.requests}, {'GET'})
        self.assertEqual({r['body'] for r in self.api.requests}, {b''})

    def test_through_the_core_it_is_the_same_verdict_scrubbed(self):
        self.ctx()
        # ядро лишає у вердикті лише `ok`/`error`/`detail`: поле `replies` модуля до нього не доходить
        self.assertEqual(dm.check(self.sp, MID), {'ok': True, 'detail': 'таблиці comments і comment_replies доступні'})
        self.api.override('GET', 401, {'message': 'Invalid API key'})
        res = dm.check(self.sp, MID)
        self.assertEqual((res['ok'], res['error']), (False, 'bad-key'))
        self.assertEqual(dm.last_check(self.sp['id'], MID), res)


# --------------------------------------------------------------------------- ключ: лише заголовки до `url`

class KeySafetyTest(Base):
    def run_everything(self):
        """Усі чотири функції модуля проти підставного сервера (частина — з помилками)."""
        ctx, chan = self.ctx(), self.chan()
        self.api.rows = [row('a', chan)]
        out = []
        for name, args in (('client_config', ()), ('list', (chan,)), ('resolve', (chan, 'a', 'r')), ('resolve', (chan, 'zzz', 'r')),
                           ('check', ())):
            try:
                out.append(self.fn(name)(ctx, *args))
            except BaseException as e:  # noqa: BLE001
                out.append(e)
        return out

    def test_the_key_is_only_in_the_two_headers_of_requests_to_the_configured_host(self):
        self.run_everything()
        self.assertEqual(len(self.seen), 6, 'list ×2 (коментарі, відповіді), resolve ×2, check ×2; client_config у мережу не ходить')
        for req in self.seen:
            self.assertTrue(req['url'].startswith((f'https://{HOST}/rest/v1/comments', f'https://{HOST}/rest/v1/comment_replies')),
                            req['url'])
            self.assertEqual(urllib.parse.urlsplit(req['url']).hostname, HOST)
            self.assertEqual(req['headers']['apikey'], KEY)
            self.assertEqual(req['headers']['authorization'], 'Bearer ' + KEY)
            self.assertNotIn(KEY, req['url'])
            self.assertNotIn(KEY.encode(), req['data'] or b'')
            for name, value in req['headers'].items():
                if name not in ('apikey', 'authorization'):
                    self.assertNotIn(KEY, value, name)
        for rec in self.api.requests:
            self.assertNotIn(KEY.encode(), self.blob(rec, skip_auth=True), rec['raw_path'])
            self.assertEqual(rec['headers']['apikey'], KEY)

    def test_no_request_ever_leaves_https_or_the_configured_host(self):
        self.run_everything()
        for req in self.seen:
            sp = urllib.parse.urlsplit(req['url'])
            self.assertEqual((sp.scheme, sp.netloc, sp.fragment, sp.username), ('https', HOST, '', None), req['url'])

    def test_errors_never_carry_the_key_even_when_the_service_echoes_it(self):
        self.api.echo_key = True
        chan = self.chan()
        texts = []
        for status in (400, 401, 403, 404, 500, 503):
            for method, name, args in (('GET', 'list', (chan,)), ('PATCH', 'resolve', (chan, 'a', 'r')), ('GET', 'check', ())):
                self.api.overrides.clear()
                self.api.override(method, status, {'code': 'XX000', 'message': f'oops {KEY}', 'details': f'key={KEY}',
                                                   'hint': f'Authorization: Bearer {KEY}'})
                try:
                    res = self.fn(name)(self.ctx(), *args)
                    texts.append(json.dumps(res))
                except BaseException as e:  # noqa: BLE001
                    texts += self.exc_texts(e)
        self.assertTrue(texts)
        for t in texts:
            self.assertNotIn(KEY, t)
            for part in KEY.split('.'):
                if len(part) > 8:
                    self.assertNotIn(part, t)

    def test_nor_do_the_core_wrapped_calls_and_the_verdicts(self):
        self.api.echo_key = True
        chan = self.chan()
        ctx = self.ctx()
        self.api.override(None, 500, {'message': f'oops {KEY}'})
        texts = []
        for name, args in (('list', (chan,)), ('resolve', (chan, 'a', 'r'))):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.call(self.m, name, ctx, *args)
            texts += self.exc_texts(cm.exception)
        texts.append(json.dumps(dm.check(self.sp, MID)))
        self.assertTrue(texts)
        for t in texts:
            self.assertNotIn(KEY, t)

    def test_a_redirect_never_carries_the_key_to_another_host(self):
        evil = self.evil_server()
        chan = self.chan()
        for code in (301, 302, 303, 307, 308):
            self.api.redirect_to, self.api.redirect_code = evil.base, code
            for name, args in (('list', (chan,)), ('resolve', (chan, 'a', 'r'))):
                e = self.fails(name, *args)
                self.assertEqual(e.code, 'module-error', (code, name))
                self.assertIn(f'HTTP {code}', e.message)
                self.assertNotIn(KEY, ' '.join(self.exc_texts(e)))
            res = self.fn('check')(self.ctx())
            self.assertEqual((res['ok'], res['error']), (False, 'supabase-error'), code)
        self.assertEqual(evil.requests, [], 'ключ поїхав за переадресацією')
        self.assertEqual([r['method'] for r in self.api.requests], ['GET', 'PATCH', 'GET'] * 5, 'свій сервер питаємо по разу')

    def test_the_only_way_to_the_network_is_the_one_seam(self):
        tree = ast.parse(_read(SERVER).decode('utf-8'))
        opens = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'open']
        self.assertEqual(len(opens), 1, 'запит іде в мережу в одному місці — `_open`')
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_open')
        self.assertIn(opens[0], list(ast.walk(fn)))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for banned in ('urlopen', 'socket', 'create_connection', 'HTTPSConnection', 'HTTPConnection', 'requests', 'getaddrinfo'):
            self.assertNotIn(banned, names, banned)


# ------------------------------------------------------------------------------ сервісний ключ не приймається

def b64u(raw, pad=False):
    out = base64.urlsafe_b64encode(raw).decode('ascii')
    return out if pad else out.rstrip('=')


def jwt(claims, pad=False, std=False):
    """JWT у формі Supabase: header.payload.signature; `claims` — корисна частина (dict чи готовий текст)."""
    raw = (claims if isinstance(claims, str) else json.dumps(claims)).encode('utf-8')
    payload = b64u(raw, pad)
    if std:                                                  # стандартний base64 (`+`, `/`) замість base64url — теж читається
        payload = base64.b64encode(raw).decode('ascii').rstrip('=')
    return '.'.join([b64u(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode()), payload, 'c2lnbmF0dXJlLVRFU1Q'])


SERVICE_TEXT = 'key: це сервісний ключ — потрібен публічний anon/publishable'
SERVICE_CLAIMS = {'iss': 'supabase', 'ref': 'abcdefghijkl', 'role': 'service_role', 'iat': 1700000000, 'exp': 2000000000}
SERVICE_KEYS = [
    'sb_secret_' + 'A1b2C3d4' * 5, 'sb_secret_x', 'sb_secret_',
    jwt(SERVICE_CLAIMS), jwt(SERVICE_CLAIMS, pad=True), jwt(SERVICE_CLAIMS, std=True), jwt({'role': 'service_role'}),
    jwt('{"role" : "service_role"}'), jwt('{ "exp": 1,\n "role":\t"service_role" }'), jwt({'role': 'service_role', 'role2': 'anon'}),
    jwt({'role': 'anon', 'role': 'service_role'}),         # у JSON останній ключ перемагає
    '  ' + jwt(SERVICE_CLAIMS) + '\n',                      # обрізається, як і при читанні налаштувань
]
PUBLIC_KEYS = [
    KEY, 'sb_publishable_' + 'A1b2C3d4' * 4, jwt({'iss': 'supabase', 'ref': 'abcdefghijkl', 'role': 'anon', 'iat': 1, 'exp': 2}),
    jwt({'role': 'anon'}, pad=True), jwt({'role': 'authenticated'}),
    # те, що ми не вміємо розібрати, не називаємо сервісним: відмовляти з підозри було б відмовою живим ключам
    'a.b.c', 'one-part-key', 'a.b', 'a.b.c.d', jwt('not json'), jwt('null'), jwt('[1,2]'), jwt('"service_role"'),
    jwt({'role': ['service_role']}), jwt({'role': 'Service_Role'}), jwt({'role': 'service_role_x'}), jwt({'x': {'role': 'service_role'}}),
    jwt('[' * 5000), 'eyJ.!!!.sig', 'sb_Secret_x', 'xsb_secret_x',
]


# ------------------------------------------------------------------------------------------ відповіді (0.34)

def reply_row(rid, comment_id, channel, **over):
    """Рядок таблиці `comment_replies` у формі PostgREST."""
    out = {'id': rid, 'comment_id': comment_id, 'project_id': channel, 'author': 'Олена', 'text': f'відповідь {rid}',
           'ts': '20.11.2026 10:00', 'edited_ts': None, 'agent': False, 'created_at': f'2026-11-20T10:00:{len(rid) % 60:02d}Z'}
    out.update(over)
    return out


class RepliesBase(Base):
    def reply(self, *args, ctx=None):
        """`reply` ядро поки не вантажить (його немає в `ROLE_OPTIONAL_FUNCTIONS`: це справа агента) — беремо з глобалів модуля."""
        return self.g['reply'](ctx if ctx is not None else self.ctx(), *args)

    def reply_fails(self, *args, ctx=None):
        try:
            self.reply(*args, ctx=ctx)
        except BaseException as e:  # noqa: BLE001
            return e
        self.fail('очікували виняток')

    def breaks_network_for_replies(self):
        real = self.g['_open']

        def op(req, timeout):
            if '/comment_replies' in req.full_url:
                raise OSError('обрив')
            return real(req, timeout)
        self.patch_globals(_open=op)


class ListRepliesTest(RepliesBase):
    def test_replies_are_attached_to_their_comments_in_created_order(self):
        chan = self.chan()
        self.api.rows = [row('a', chan), row('b', chan), row('c', chan)]
        self.api.replies = [
            reply_row('r2', 'a', chan, created_at='2026-11-20T10:02:00Z', agent=True, edited_ts='20.11.2026 11:00', text='друга'),
            reply_row('r1', 'a', chan, created_at='2026-11-20T10:01:00Z', text='перша'),
            reply_row('r3', 'b', chan, created_at='2026-11-20T10:03:00Z', ts=None),
            reply_row('rx', 'a', self.chan('other'), created_at='2026-11-20T10:00:00Z')]
        a, b, c = self.fn('list')(self.ctx(), chan)
        self.assertEqual(a['replies'], [
            {'id': 'r1', 'author': 'Олена', 'text': 'перша', 'ts': '20.11.2026 10:00'},
            {'id': 'r2', 'author': 'Олена', 'text': 'друга', 'ts': '20.11.2026 10:00', 'editedTs': '20.11.2026 11:00', 'agent': True}])
        self.assertEqual(b['replies'], [{'id': 'r3', 'author': 'Олена', 'text': 'відповідь r3', 'ts': None}])
        self.assertNotIn('replies', c, 'коментар без відповідей лишається таким, як був')
        self.assertNotIn('editedTs', a['replies'][0])
        self.assertNotIn('agent', a['replies'][0], '`agent` лише коли true')

    def test_orphan_replies_are_dropped(self):
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.api.replies = [reply_row('r1', 'gone', chan), reply_row('r2', 'a', chan, created_at='2026-11-20T10:05:00Z')]
        (a,) = self.fn('list')(self.ctx(), chan)
        self.assertEqual([r['id'] for r in a['replies']], ['r2'])

    def test_a_missing_replies_table_gives_the_comments_without_replies_and_no_error(self):
        chan = self.chan()
        for how in ('plain', 'PGRST205', '42P01'):
            self.api.no_replies_table = how
            self.api.rows = [row('a', chan)]
            got = self.fn('list')(self.ctx(), chan)
            self.assertEqual([c['id'] for c in got], ['a'], how)
            self.assertNotIn('replies', got[0], how)

    def test_any_failure_of_the_replies_request_keeps_the_comments(self):
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        for status, body in ((500, {'message': 'oops'}), (401, {'message': 'Invalid API key'}), (403, None), (302, None),
                             (200, {'message': 'not a list'}), (200, 'not json')):
            self.api.overrides.clear()
            self.api.override('GET', status, body, path=REPLIES)
            got = self.fn('list')(self.ctx(), chan)
            self.assertEqual([c['id'] for c in got], ['a'], status)
            self.assertNotIn('replies', got[0], status)

    def test_a_network_failure_and_an_oversize_answer_of_the_replies_keep_the_comments(self):
        chan = self.chan()
        self.api.rows = [row('a', chan, fp=None, html_snapshot=None, meta=None)]
        self.api.override('GET', 200, json.dumps([reply_row('r1', 'a', chan, text='x' * 5000)]), path=REPLIES)
        self.patch_globals(MAX_BODY=1000)
        got = self.fn('list')(self.ctx(), chan)
        self.assertEqual([c['id'] for c in got], ['a'])
        self.assertNotIn('replies', got[0])
        self.api.overrides.clear()
        self.breaks_network_for_replies()
        got = self.fn('list')(self.ctx(), chan)
        self.assertEqual([c['id'] for c in got], ['a'])

    def test_the_comments_failure_is_still_an_error_and_replies_are_not_asked_for(self):
        self.api.no_table = 'PGRST205'
        e = self.fails('list', self.chan())
        self.assertEqual(e.code, 'module-error')
        self.assertEqual(len(self.api.requests), 1)


class RecentRepliesTest(RepliesBase):
    def seed(self, chan):
        self.api.rows = [row('a', chan, created_at='2026-11-20T09:01:00Z'), row('b', chan, created_at='2026-11-20T09:02:00Z', meta={}),
                         row('c', chan, status='resolved', created_at='2026-11-20T09:03:00Z')]
        self.api.replies = [reply_row('r1', 'a', chan, created_at='2026-11-20T10:01:00Z'),
                            reply_row('r2', 'c', chan, created_at='2026-11-20T10:02:00Z'),
                            reply_row('r3', 'b', chan, created_at='2026-11-20T10:03:00Z', author='Агент'),
                            reply_row('r4', 'a', chan, created_at='2026-11-20T10:04:00Z')]

    def test_comment_items_then_replies_of_open_comments_newest_first(self):
        chan = self.chan()
        self.seed(chan)
        got = self.fn('recent')(self.ctx(), chan)
        self.assertEqual(got, [
            {'id': 'b', 'ts': '19.10.2026 10:00', 'author': 'Олена', 'status': 'open', 'version': None},
            {'id': 'a', 'ts': '19.10.2026 10:00', 'author': 'Олена', 'status': 'open', 'version': '2/x'},
            {'id': 'r4', 'ts': '20.11.2026 10:00', 'author': 'Олена', 'status': 'open', 'version': '2/x', 'parent': 'a'},
            {'id': 'r3', 'ts': '20.11.2026 10:00', 'author': 'Агент', 'status': 'open', 'version': None, 'parent': 'b'},
            {'id': 'r1', 'ts': '20.11.2026 10:00', 'author': 'Олена', 'status': 'open', 'version': '2/x', 'parent': 'a'}])
        self.assertNotIn('r2', [i['id'] for i in got], 'відповідь на закритий коментар не рахується')
        for item in got:
            self.assertFalse({'text', 'htmlSnapshot', 'html_snapshot', 'fp', 'meta'} & set(item), item)

    def test_the_requests_are_light_and_the_parent_filter_is_quoted(self):
        chan = self.chan()
        self.seed(chan)
        self.fn('recent')(self.ctx(), chan)
        c, r, p = self.api.requests
        self.assertEqual((c['path'], r['path'], p['path']), (TABLE, REPLIES, TABLE))
        self.assertEqual(r['query']['select'], ['id,comment_id,author,ts'])
        self.assertEqual((r['query']['order'], r['query']['limit']), (['created_at.desc,id.desc'], ['200']))
        self.assertEqual(r['query']['project_id'], ['eq.' + chan])
        self.assertEqual(p['query']['id'], ['in.("a","b","c")'])
        self.assertIn('id=in.(%22a%22,%22b%22,%22c%22)', p['raw_query'])
        self.assertEqual((p['query']['status'], p['query']['project_id']), (['eq.open'], ['eq.' + chan]))
        self.assertEqual(p['query']['select'], ['id,version:meta->>version'])

    def test_awkward_comment_ids_stay_inside_their_quotes(self):
        chan = self.chan()
        weird = 'x,"y)\\z&=#'
        self.api.rows = [row(weird, chan), row('plain', chan)]
        self.api.replies = [reply_row('r1', weird, chan, created_at='2026-11-20T10:01:00Z'),
                            reply_row('r2', 'plain', chan, created_at='2026-11-20T10:02:00Z')]
        got = self.fn('recent')(self.ctx(), chan)
        self.assertEqual([i['parent'] for i in got if 'parent' in i], ['plain', weird])

    def test_a_long_parent_list_is_asked_in_chunks(self):
        chan = self.chan()
        self.patch_globals(IN_CHUNK=2)
        self.api.rows = [row(f'k{i}', chan) for i in range(5)]
        self.api.replies = [reply_row(f'rr{i}', f'k{i}', chan, created_at=f'2026-11-20T10:0{i}:00Z') for i in range(5)]
        got = self.fn('recent')(self.ctx(), chan)
        self.assertEqual([i['parent'] for i in got if 'parent' in i], ['k4', 'k3', 'k2', 'k1', 'k0'])
        parents = [r for r in self.api.requests if r['path'] == TABLE and 'id' in r['query']]
        self.assertEqual([r['query']['id'][0].count('","') + 1 for r in parents], [2, 2, 1])

    def test_a_replies_failure_returns_just_the_comments(self):
        chan = self.chan()
        self.seed(chan)
        want = [i for i in self.fn('recent')(self.ctx(), chan) if 'parent' not in i]
        self.assertEqual([i['id'] for i in want], ['b', 'a'])
        for how in ('no-table', 500, 'not-list', 'parents-500', 'parents-not-list', 'network'):
            self.api.overrides.clear()
            self.api.no_replies_table = None
            if how == 'no-table':
                self.api.no_replies_table = 'PGRST205'
            elif how == 500:
                self.api.override('GET', 500, {'message': 'oops'}, path=REPLIES)
            elif how == 'not-list':
                self.api.override('GET', 200, {'x': 1}, path=REPLIES)
            elif how == 'parents-500':
                self.api.override('GET', 500, {'message': 'oops'}, path=TABLE, when=lambda rec: 'in.' in rec['query'].get('id', [''])[0])
            elif how == 'parents-not-list':
                self.api.override('GET', 200, {'x': 1}, path=TABLE, when=lambda rec: 'in.' in rec['query'].get('id', [''])[0])
            elif how == 'network':
                self.breaks_network_for_replies()
            self.assertEqual(self.fn('recent')(self.ctx(), chan), want, how)

    def test_without_replies_no_parent_request_is_made(self):
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.fn('recent')(self.ctx(), chan)
        self.assertEqual([r['path'] for r in self.api.requests], [TABLE, REPLIES])


class ReplyTest(RepliesBase):
    def open_comment(self, cid='a', **over):
        chan = self.chan()
        self.api.rows = [row(cid, chan, **over)]
        return chan

    def test_posts_a_reply_of_the_agent_to_an_open_comment(self):
        chan = self.open_comment()
        got = self.reply(chan, 'a', 'Зроблено', 'Агент')
        self.assertEqual(set(got), {'id'})
        self.assertRegex(got['id'], r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
        get, post = self.api.requests
        self.assertEqual((get['method'], get['path']), ('GET', TABLE))
        self.assertEqual(get['raw_query'], f'id=eq.a&project_id=eq.{q(chan)}&select=id,status')
        self.assertEqual((post['method'], post['path']), ('POST', REPLIES))
        self.assertEqual(post['headers']['prefer'], 'return=representation')
        self.assertEqual(post['headers']['content-type'], 'application/json')
        body = json.loads(post['body'])
        self.assertRegex(body.pop('ts'), r'^\d\d\.\d\d\.\d{4} \d\d:\d\d$')
        self.assertEqual(body, {'id': got['id'], 'comment_id': 'a', 'project_id': chan, 'author': 'Агент', 'text': 'Зроблено',
                                'agent': True})
        self.assertIs(json.loads(post['body'])['agent'], True)
        for rec in (get, post):
            self.assertEqual((rec['headers']['apikey'], rec['headers']['authorization']), (KEY, 'Bearer ' + KEY))
        self.assertEqual([r['id'] for r in self.api.replies], [got['id']])
        (a,) = self.fn('list')(self.ctx(), chan)
        self.assertEqual([(r['text'], r['agent']) for r in a['replies']], [('Зроблено', True)])

    def test_every_reply_gets_its_own_id(self):
        chan = self.open_comment()
        self.assertNotEqual(self.reply(chan, 'a', 't', 'x')['id'], self.reply(chan, 'a', 't', 'x')['id'])

    def test_a_missing_comment_is_refused_and_nothing_is_posted(self):
        chan = self.open_comment()
        for cid, ch in (('zzz', chan), ('a', self.chan('other'))):
            e = self.reply_fails(ch, cid, 'текст', 'Агент')
            self.assertIsInstance(e, dm.ModuleError)
            self.assertEqual((e.code, e.message), ('module-error', 'коментар не знайдено'))
        self.assertEqual(self.api.reqs('POST'), [])

    def test_a_closed_comment_is_refused_and_nothing_is_posted(self):
        chan = self.open_comment(status='resolved')
        e = self.reply_fails(chan, 'a', 'текст', 'Агент')
        self.assertEqual((e.code, e.message), ('module-error', 'коментар закрито — відповідати можна лише на відкритий'))
        self.assertEqual(self.api.reqs('POST'), [])
        self.assertEqual(self.api.replies, [])

    def test_a_missing_replies_table_says_to_run_replies_sql(self):
        chan = self.open_comment()
        for how in ('plain', 'PGRST205', '42P01'):
            self.api.no_replies_table = how
            e = self.reply_fails(chan, 'a', 'текст', 'Агент')
            self.assertEqual((e.code, e.message), ('module-error',
                                                    'у проєкті нема таблиці відповідей — виконайте replies.sql у SQL-редакторі проєкту'), how)

    def test_a_missing_comments_table_is_the_comments_text(self):
        self.api.no_table = 'PGRST205'
        e = self.reply_fails(self.chan(), 'a', 'текст', 'Агент')
        self.assertIn('schema.sql', e.message)

    def test_other_errors_go_through_the_common_classification(self):
        chan = self.open_comment()
        self.api.override('POST', 500, {'message': 'oops'}, path=REPLIES)
        e = self.reply_fails(chan, 'a', 'текст', 'Агент')
        self.assertEqual((e.code, e.message), ('module-error', 'Supabase відповів HTTP 500: oops'))
        self.api.overrides.clear()
        self.api.override('GET', 503, None, path=TABLE)
        self.assertIn('HTTP 503', self.reply_fails(chan, 'a', 'текст', 'Агент').message)
        self.api.overrides.clear()
        self.breaks_network_for_replies()
        self.assertIn('недоступний', self.reply_fails(chan, 'a', 'текст', 'Агент').message)

    def test_a_2xx_answer_without_the_created_row_is_not_a_confirmation(self):
        chan = self.open_comment()
        for body in (None, [], {'id': 'x'}, 'not json', b'5'):
            self.api.overrides.clear()
            self.api.override('POST', 201, body, path=REPLIES)
            e = self.reply_fails(chan, 'a', 'текст', 'Агент')
            self.assertEqual(e.code, 'module-error', repr(body))
            self.assertIn('не підтвердив', e.message, repr(body))

    def test_bad_input_is_refused_before_any_request(self):
        chan = self.open_comment()
        cases = [(chan, 'a', '', 'Агент'), (chan, 'a', '   \n', 'Агент'), (chan, 'a', None, 'Агент'), (chan, 'a', 5, 'Агент'),
                 (chan, 'a', 'т', ''), (chan, 'a', 'т', '  '), (chan, 'a', 'т', None), (chan, 'a', 'т', 7),
                 ('', 'a', 'т', 'А'), (None, 'a', 'т', 'А'), (chan, '', 'т', 'А'), (chan, None, 'т', 'А'), (chan, 5, 'т', 'А'),
                 (chan, 'a\ud800', 'т', 'А')]
        for args in cases:
            e = self.reply_fails(*args)
            self.assertIsInstance(e, dm.ModuleError, repr(args))
            self.assertEqual(e.code, 'module-error', repr(args))
        self.assertEqual(self.seen, [])

    def test_text_and_author_are_trimmed_and_cut(self):
        chan = self.open_comment()
        self.reply(chan, 'a', '  ' + 'ж' * 4500 + '  ', ' ' + 'А' * 150)
        body = json.loads(self.api.reqs('POST')[-1]['body'])
        self.assertEqual(body['text'], 'ж' * 4000)
        self.assertEqual(body['author'], 'А' * 100)
        self.reply(chan, 'a', 'ж' * 4000, 'x')
        self.assertEqual(len(json.loads(self.api.reqs('POST')[-1]['body'])['text']), 4000)
        self.reply(chan, 'a', '  привіт\n', 'x')
        self.assertEqual(json.loads(self.api.reqs('POST')[-1]['body'])['text'], 'привіт')

    def test_a_lone_surrogate_in_the_text_becomes_a_question_mark(self):
        chan = self.open_comment()
        self.reply(chan, 'a', 'a\ud800b', 'Агент\udc00')
        body = json.loads(self.api.reqs('POST')[-1]['body'])
        self.assertEqual((body['text'], body['author']), ('a?b', 'Агент?'))

    def test_hostile_ids_stay_inside_their_filters(self):
        chan = self.chan()
        weird = 'a&status=eq.resolved#'
        self.api.rows = [row(weird, chan)]
        self.reply(chan, weird, 'т', 'А')
        get = self.api.requests[0]
        self.assertEqual(get['query']['id'], ['eq.' + weird])
        self.assertEqual(set(get['query']), {'id', 'project_id', 'select'})

    def test_the_module_stays_valid_when_the_core_does_not_know_reply_yet(self):
        m = dm.catalog()[MID]
        self.assertEqual((m.status, m.error), ('ok', None))
        self.assertTrue(callable(self.g['reply']))
        self.assertNotIn('reply', sum(dm.ROLE_OPTIONAL_FUNCTIONS.values(), ()), 'додати `reply` у ядро — Task 9')
        self.assertEqual(dm.ROLE_OPTIONAL_FUNCTIONS['comments'], ('recent',))


class CheckRepliesTest(RepliesBase):
    BASE = 'таблиця comments доступна'

    def test_both_tables_answer(self):
        self.assertEqual(self.fn('check')(self.ctx()),
                         {'ok': True, 'replies': True, 'detail': 'таблиці comments і comment_replies доступні'})

    def test_a_missing_replies_table_keeps_ok_and_says_what_to_run(self):
        for how in ('plain', 'PGRST205', '42P01'):
            self.api.no_replies_table = how
            self.assertEqual(self.fn('check')(self.ctx()),
                             {'ok': True, 'replies': False,
                              'detail': self.BASE + '; для відповідей виконайте replies.sql у SQL-редакторі проєкту'}, how)

    def test_an_erroring_replies_probe_keeps_ok_and_carries_the_classified_text(self):
        for status, body, text in ((500, {'message': 'oops'}, 'Supabase відповів HTTP 500: oops'),
                                   (401, {'message': 'Invalid API key'}, 'Supabase не прийняв ключ (HTTP 401): Invalid API key'),
                                   (200, {'x': 1}, 'Supabase відповів HTTP 200, але не списком рядків')):
            self.api.overrides.clear()
            self.api.override('GET', status, body, path=REPLIES)
            res = self.fn('check')(self.ctx())
            self.assertEqual(res, {'ok': True, 'replies': False,
                                   'detail': self.BASE + '; таблиця відповідей не відповіла: ' + text}, status)
        self.api.overrides.clear()
        self.breaks_network_for_replies()
        res = self.fn('check')(self.ctx())
        self.assertEqual((res['ok'], res['replies']), (True, False))
        self.assertEqual(res['detail'], self.BASE + '; таблиця відповідей не відповіла: Supabase недоступний (OSError)')

    def test_a_failing_comments_probe_is_not_followed_by_a_replies_probe(self):
        self.api.no_table = 'PGRST205'
        res = self.fn('check')(self.ctx())
        self.assertEqual((res['ok'], res['error']), (False, 'no-schema'))
        self.assertNotIn('replies', res)
        self.assertEqual([r['path'] for r in self.api.requests], [TABLE])

    def test_both_probes_use_the_check_budget(self):
        self.fn('check')(self.ctx())
        got = [(r['url'].split('?')[0][len(URL):], r['timeout']) for r in self.seen]
        self.assertEqual([g[0] for g in got], [TABLE, REPLIES])
        for _, t in got:
            self.assertTrue(3 < t <= 4, t)             # спільний дедлайн 4 с: другий запит — з тим, що лишилося


class BudgetTest(RepliesBase):
    """Один спільний дедлайн на виклик: повільна таблиця відповідей не з'їдає бюджет коментарів (ядро чекає 5 с на `check`, 10 с на решту)."""

    def tight(self, budget=0.6):
        self.patch_globals(CALL_TIMEOUT_S=budget, CHECK_TIMEOUT_S=budget, REPLIES_MIN_S=0.3, REPLY_POST_MIN_S=0.3)

    def timed(self, fn, *args):
        t0 = time.monotonic()
        out = fn(*args)
        return out, time.monotonic() - t0

    def test_a_slow_replies_table_still_gives_the_comments_within_the_budget(self):
        self.tight()
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.api.override('GET', 200, [], path=REPLIES, delay=3)
        got, spent = self.timed(self.fn('list'), self.ctx(), chan)
        self.assertEqual([c['id'] for c in got], ['a'])
        self.assertNotIn('replies', got[0])
        self.assertLess(spent, 1.5, 'не чекали 3 с відповіді таблиці відповідей')

    def test_list_does_not_even_ask_for_replies_when_the_comments_ate_the_budget(self):
        self.tight()
        chan = self.chan()
        self.api.override('GET', 200, [row('a', chan)], path=TABLE, delay=0.4)
        self.api.override('GET', 200, [reply_row('r1', 'a', chan)], path=REPLIES, delay=0.4)
        got, spent = self.timed(self.fn('list'), self.ctx(), chan)
        self.assertEqual([c['id'] for c in got], ['a'])
        self.assertNotIn('replies', got[0])
        self.assertEqual([r['path'] for r in self.api.requests], [TABLE], 'залишок < REPLIES_MIN_S: запиту до відповідей нема')
        self.assertLess(spent, 0.6)

    def test_check_stays_ok_and_says_replies_were_not_checked(self):
        self.tight()
        self.api.override('GET', 200, [], path=TABLE, delay=0.4)
        res, spent = self.timed(self.fn('check'), self.ctx())
        self.assertEqual(res, {'ok': True, 'replies': None,
                               'detail': 'таблиця comments доступна; таблицю відповідей не перевірено — не вистачило часу'})
        self.assertEqual([r['path'] for r in self.api.requests], [TABLE])
        self.assertLess(spent, 0.6)

    def test_check_with_a_slow_replies_probe_answers_inside_the_budget(self):
        self.tight()
        self.api.override('GET', 200, [], path=REPLIES, delay=3)
        res, spent = self.timed(self.fn('check'), self.ctx())
        self.assertEqual((res['ok'], res['replies']), (True, False))
        self.assertIn('таблиця відповідей не відповіла', res['detail'])
        self.assertLess(spent, 1.5)

    def test_recent_returns_only_comments_when_the_budget_is_spent(self):
        self.tight()
        chan = self.chan()
        self.api.override('GET', 200, [{'id': 'a', 'ts': 't', 'author': 'o', 'status': 'open', 'version': '2'}], path=TABLE, delay=0.4)
        got, spent = self.timed(self.fn('recent'), self.ctx(), chan)
        self.assertEqual([i['id'] for i in got], ['a'])
        self.assertEqual([r['path'] for r in self.api.requests], [TABLE])
        self.assertLess(spent, 0.6)

    def test_recent_with_a_slow_replies_table_returns_the_comments(self):
        self.tight()
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.api.override('GET', 200, [], path=REPLIES, delay=3)
        got, spent = self.timed(self.fn('recent'), self.ctx(), chan)
        self.assertEqual([i['id'] for i in got], ['a'])
        self.assertLess(spent, 1.5)

    def test_recent_stops_between_parent_chunks_when_the_budget_is_gone(self):
        self.tight(0.6)
        self.patch_globals(IN_CHUNK=1)
        chan = self.chan()
        self.api.rows = [row('a', chan), row('b', chan)]
        self.api.replies = [reply_row('r1', 'a', chan), reply_row('r2', 'b', chan)]
        self.api.override('GET', 200, [{'id': 'a', 'version': '2'}], path=TABLE, delay=0.4,
                          when=lambda rec: 'in.' in rec['query'].get('id', [''])[0])
        got = self.fn('recent')(self.ctx(), chan)
        self.assertEqual([i for i in got if 'parent' in i], [], 'частину батьків не дочекались — самі коментарі')
        asked = [r for r in self.api.requests if r['path'] == TABLE and 'in.' in r['query'].get('id', [''])[0]]
        self.assertEqual(len(asked), 1, 'після першої пачки бюджету не лишилось — другої нема')

    def test_reply_does_not_post_when_too_little_budget_is_left(self):
        self.tight()
        chan = self.chan()
        self.api.override('GET', 200, [{'id': 'a', 'status': 'open'}], path=TABLE, delay=0.4)
        e = self.reply_fails(chan, 'a', 'текст', 'Агент')
        self.assertIsInstance(e, dm.ModuleError)
        self.assertEqual(e.code, 'module-error')
        self.assertIn('відповідь не надіслано', e.message)
        self.assertEqual(self.api.reqs('POST'), [], 'POST не йшов')
        self.assertEqual(self.api.replies, [])

    def test_reply_posts_when_the_budget_is_enough(self):
        self.tight(3)
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.assertTrue(self.reply(chan, 'a', 'текст', 'Агент')['id'])
        post = self.seen[-1]
        self.assertEqual(post['method'], 'POST')
        self.assertLessEqual(post['timeout'], 3)


class OrderAndTextsTest(RepliesBase):
    def test_list_orders_replies_by_created_at_then_id(self):
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.api.replies = [reply_row('r2', 'a', chan), reply_row('r1', 'a', chan)]        # однаковий `created_at`
        (a,) = self.fn('list')(self.ctx(), chan)
        self.assertEqual([r['id'] for r in a['replies']], ['r1', 'r2'])
        self.assertEqual(self.api.requests[1]['query']['order'], ['created_at.asc,id.asc'])

    def test_recent_orders_replies_newest_first_then_by_id_descending(self):
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.api.replies = [reply_row('r1', 'a', chan), reply_row('r2', 'a', chan),
                            reply_row('r0', 'a', chan, created_at='2026-11-20T09:00:00Z')]
        got = self.fn('recent')(self.ctx(), chan)
        self.assertEqual([i['id'] for i in got if 'parent' in i], ['r2', 'r1', 'r0'])
        self.assertEqual(self.api.requests[1]['query']['order'], ['created_at.desc,id.desc'])

    def test_the_fake_honours_a_multi_key_order(self):
        self.api.replies = [{'id': 'b', 'created_at': '1'}, {'id': 'a', 'created_at': '1'}, {'id': 'c', 'created_at': '0'}]
        status, payload = self.g['_request'](self.ctx(), 'GET', 'order=created_at.asc,id.desc&select=id', timeout=4,
                                             table='/rest/v1/comment_replies')
        self.assertEqual([r['id'] for r in json.loads(payload)], ['c', 'b', 'a'])

    def test_a_403_on_the_replies_table_names_it_and_replies_sql(self):
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        self.api.override('GET', 403, {'message': 'denied'}, path=REPLIES)
        res = self.fn('check')(self.ctx())
        self.assertIn('таблицю comment_replies (replies.sql)', res['detail'])
        self.assertNotIn('schema.sql', res['detail'])
        self.api.overrides.clear()
        self.api.override('POST', 403, {'message': 'denied'}, path=REPLIES)
        e = self.reply_fails(chan, 'a', 'т', 'А')
        self.assertIn('таблицю comment_replies (replies.sql)', e.message)
        self.assertNotIn('schema.sql', e.message)

    def test_a_403_on_the_comments_table_keeps_its_old_text(self):
        self.api.override('GET', 403, {'message': 'denied'}, path=TABLE)
        res = self.fn('check')(self.ctx())
        self.assertIn('таблицю comments (schema.sql)', res['detail'])


class RepliesKeySafetyTest(RepliesBase):
    def test_errors_of_every_replies_path_never_carry_the_key(self):
        self.api.echo_key = True
        chan = self.chan()
        self.api.rows = [row('a', chan)]
        texts = []
        for status in (400, 401, 403, 404, 500, 503):
            self.api.overrides.clear()
            self.api.override(None, status, {'code': 'XX000', 'message': f'oops {KEY}', 'details': f'key={KEY}',
                                             'hint': f'Authorization: Bearer {KEY}'}, path=REPLIES)
            for call in (lambda: self.reply(chan, 'a', 'т', 'А'), lambda: self.fn('check')(self.ctx()),
                         lambda: self.fn('list')(self.ctx(), chan), lambda: self.fn('recent')(self.ctx(), chan)):
                try:
                    texts.append(json.dumps(call()))
                except BaseException as e:  # noqa: BLE001
                    texts += self.exc_texts(e)
        self.assertTrue(texts)
        for t in texts:
            self.assertNotIn(KEY, t)
            for part in KEY.split('.'):
                if len(part) > 8:
                    self.assertNotIn(part, t)

    def test_request_with_a_table_sends_the_key_only_to_the_project_url(self):
        ctx = self.ctx()
        status, _ = self.g['_request'](ctx, 'GET', 'select=id&limit=1', timeout=4, table=self.g['REPLIES_PATH'])
        self.assertEqual(status, 200)
        (req,) = self.seen
        self.assertEqual(req['url'], f'{URL}{REPLIES}?select=id&limit=1')
        self.assertEqual((req['headers']['apikey'], req['headers']['authorization']), (KEY, 'Bearer ' + KEY))
        self.assertNotIn(KEY, req['url'])
        self.g['_request'](ctx, 'GET', 'select=id', timeout=4)
        self.assertEqual(self.seen[-1]['url'], f'{URL}{TABLE}?select=id', 'без `table` — як і раніше таблиця comments')

    def test_a_redirect_on_the_replies_path_does_not_leak_the_key(self):
        evil = self.evil_server()
        self.api.redirect_to = evil.base
        status, _ = self.g['_request'](self.ctx(), 'GET', 'select=id', timeout=4, table=self.g['REPLIES_PATH'])
        self.assertEqual(status, 302)
        self.assertEqual(evil.requests, [], 'за переадресацією не йдемо: ключ чужому хосту не віддано')
        res = self.fn('check')(self.ctx())
        self.assertTrue(res['ok'] is False or res.get('replies') is False)
        self.assertEqual(evil.requests, [])

    def test_only_the_request_function_knows_the_key_headers(self):
        src = _read(SERVER).decode('utf-8')
        self.assertEqual(len(re.findall(r"'apikey'", src)), 1)
        self.assertEqual(len(re.findall(r"'Authorization'", src)), 1)



class ServiceKeyTest(Base):
    """Ключ модуля — `public: true`: він потрапляє в КОЖНУ сторінку й превʼю. Сервісний ключ (`sb_secret_…` чи JWT з
    `"role": "service_role"`) обходить усі правила доступу — це повний доступ до бази, тож його модуль не приймає ніде."""

    def test_every_service_key_is_refused_by_every_function_with_one_fixed_text_and_no_request(self):
        messages = set()
        for key in SERVICE_KEYS:
            ctx = self.hand_ctx(secrets={'key': key})
            for name, args in (('client_config', ()), ('list', (self.chan(),)), ('resolve', (self.chan(), 'c1', 'r'))):
                with self.assertRaises(dm.ModuleError, msg=f'{name} {key[:24]!r}') as cm:
                    self.fn(name)(ctx, *args)
                self.assertEqual((cm.exception.code, cm.exception.status), ('bad-settings', 400))
                messages.add(cm.exception.message)
                text = ' '.join(self.exc_texts(cm.exception))
                for part in key.strip().split('.') + [key.strip()]:
                    if len(part) > 8:
                        self.assertNotIn(part, text, 'сервісний ключ у тексті відмови')
            res = self.fn('check')(ctx)
            self.assertEqual((res['ok'], res['error'], res['detail']), (False, 'bad-key', SERVICE_TEXT), key[:24])
        self.assertEqual(messages, {SERVICE_TEXT})
        self.assertEqual(self.seen, [], 'з сервісним ключем у мережу не ходимо (він пішов би в заголовок)')
        self.assertEqual(self.api.requests, [])

    def test_public_keys_and_keys_that_cannot_be_read_pass(self):
        for key in PUBLIC_KEYS:
            ctx = self.hand_ctx(secrets={'key': key})
            self.assertEqual(self.fn('client_config')(ctx), {'url': URL, 'key': key.strip()}, key[:24])
        self.assertEqual(self.seen, [])
        res = self.fn('check')(self.hand_ctx(secrets={'key': PUBLIC_KEYS[1]}))
        self.assertEqual(res['error'] if not res['ok'] else 'ok', 'bad-key', 'підставний сервер знає лише KEY, але запит ПІШОВ')
        self.assertEqual(len(self.seen), 1)

    def test_the_refusal_comes_through_the_core_and_the_key_stays_out_of_every_text(self):
        key = jwt(SERVICE_CLAIMS)
        ctx = self.ctx(key=key)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(self.m, 'client_config', ctx)
        self.assertEqual((cm.exception.code, cm.exception.message), ('bad-settings', SERVICE_TEXT))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.comments_client(self.sp, self.m)
        self.assertEqual(cm.exception.code, 'bad-settings')
        verdict = dm.check(self.sp, MID)
        self.assertEqual((verdict['ok'], verdict['error'], verdict['detail']), (False, 'bad-key', SERVICE_TEXT))
        self.assertEqual(self.seen, [])

    def test_the_detector_handles_hostile_payloads_without_raising(self):
        detect = self.g['_is_service_key']
        for key in ('.' * 2, 'a..', '..c', jwt('\x00' * 10), jwt('{"role":"service_role"'), jwt('\udcff'.encode('utf-8', 'surrogateescape').decode('latin-1')),
                    'x.' + 'A' * 100000 + '.y', 'x.%%%.y', 'x.====.y', 'x.a.y'):
            self.assertIs(detect(key), False, key[:30])
        self.assertIs(detect(jwt(SERVICE_CLAIMS)), True)


# ------------------------------------------------------------------- самотні сурогати в значеннях фільтра

class SurrogateTest(Base):
    """Самотній сурогат (непрочитний байт аргументу CLI) у каналі чи `id` не закодувати в запит: відмова — наша, з фіксованим
    текстом, а не виняток `quote`, що несе сам символ."""

    def test_a_lone_surrogate_in_the_channel_or_the_id_is_a_clean_refusal_before_any_request(self):
        for bad in ('deai/x/\ud800', '\udfff', 'a\ud83dz', 'ok\udc80'):
            for name, args in (('list', (bad,)), ('resolve', (bad, 'c1', 'r')), ('resolve', (self.chan(), bad, 'r'))):
                e = self.fails(name, *args)
                self.assertIsInstance(e, dm.ModuleError, (name, bad))
                self.assertEqual(e.code, 'module-error')
                self.assertIn('недопустимі символи', e.message)
                text = ' '.join(self.exc_texts(e)).lower()
                for frag in ('ud800', 'udfff', 'ud83d', 'udc80', 'codec', 'surrogates not allowed'):
                    self.assertNotIn(frag, text, (name, frag))
                self.assertNotIn(bad[-1], ' '.join(self.exc_texts(e)))
        self.assertEqual(self.seen, [])

    def test_a_lone_surrogate_in_the_reason_does_not_lose_the_closing(self):
        chan = self.chan('t1')
        self.api.rows = [row('c1', chan)]
        self.assertIsNone(self.fn('resolve')(self.ctx(), chan, 'c1', 'готово\ud800!'))
        self.assertEqual(self.api.rows[0]['status'], 'resolved')
        self.assertEqual(self.api.rows[0]['resolve_reason'], 'готово?!')


# ------------------------------------------------------- зависла служба: власні тайм-аути коротші за ядра

class HungServiceTest(Base):
    def test_at_the_default_budgets_the_module_answers_before_the_core_gives_up(self):
        """Служба приймає зʼєднання й мовчить. На ДЕФОЛТНИХ сталих (4 і 8 с) модуль віддає СВОЮ причину раніше, ніж ядро
        скаже `check-timeout` (5 с) чи обірве `list`/`resolve` (10 с): людина бачить «недоступний», а не «не відповів модуль»."""
        self.api.override(None, 200, [], delay=15)
        self.ctx()
        chan = self.chan()
        out, lock = {}, threading.Lock()

        def timed(name, fn):
            def run():
                t0 = time.monotonic()
                try:
                    with spaces.request_space(self.sp['id']):
                        res = ('ok', fn())
                except BaseException as e:  # noqa: BLE001
                    res = ('err', e)
                with lock:
                    out[name] = (res, time.monotonic() - t0)
            t = threading.Thread(target=run, daemon=True)
            t.start()
            return t
        threads = [timed('check', lambda: dm.check(self.sp, MID)),
                   timed('list', lambda: dm.call(self.m, 'list', dm.module_ctx(self.sp, self.m), chan, timeout=dm.COMMENTS_TIMEOUT)),
                   timed('resolve', lambda: dm.call(self.m, 'resolve', dm.module_ctx(self.sp, self.m), chan, 'c1', 'r',
                                                    timeout=dm.COMMENTS_TIMEOUT))]
        for t in threads:
            t.join(30)
        self.assertEqual(set(out), {'check', 'list', 'resolve'})
        (kind, verdict), took = out['check']
        self.assertEqual(kind, 'ok', verdict)
        self.assertEqual((verdict['ok'], verdict['error']), (False, 'network'), 'вердикт МОДУЛЯ, а не `check-timeout` ядра')
        self.assertIn('недоступний', verdict['detail'])
        self.assertGreater(took, 3.5, 'дефолтний бюджет — 4 с, а не миттєвий збій')
        for name in ('list', 'resolve'):
            (kind, err), took = out[name]
            self.assertEqual(kind, 'err', name)
            self.assertEqual((err.code, 'недоступний' in err.message), ('module-error', True), (name, err.code, err.message))
            self.assertGreater(took, 7.0, name)
            self.assertLess(took, 9.9, f'{name}: модуль мусить відповісти раніше за ядро (10 с)')


# ---------------------------------------------------------- паритет із правилом адреси ядра (`serve._url_host_ok`)

class ParityTest(Base):
    """Правило хоста модуля — те саме, що в ядра для `url`-модулів (`serve._url_host_ok`): на спільному корпусі вони не
    розходяться. Адресу модуль приймає ВУЖЧЕ за ядро (лише порожній шлях, порт 1–65535), тож усе, що прийняв він, приймає й ядро."""

    def corpus(self):
        rng = random.Random(20261019)
        alphabet = 'ab1-.xn0z9_Aé'
        hosts = {'a.b', 'a.bc', 'a.b1', 'a.1', '1.a', 'a-.b', '-a.b', 'a.-b', 'a.b-', 'a..b', '.a.b', 'a.b.', 'localhost', '127.0.0.1',
                 '0x7f.1', '2130706433', 'xn--e1afmkfd.xn--p1ai', 'a' * 63 + '.co', 'a' * 64 + '.co', ('a.' * 126) + 'co', ('a.' * 127) + 'co',
                 'A.B', 'a.B', 'абв.укр', 'a_b.co', 'a b.co', '', '.', 'a', 'ab.cd.ef.gh', 'x.y.z.1', '1.2.3.4', 'a.1a', 'a.a1'}
        for _ in range(4000):
            labels = [''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 5))) for _ in range(rng.randint(1, 4))]
            hosts.add('.'.join(labels))
        return sorted(hosts)

    def test_the_host_rule_never_differs_from_the_cores(self):
        host_ok = self.g['_host_ok']
        for host in self.corpus():
            self.assertEqual(host_ok(host), serve._url_host_ok(host), repr(host))

    def test_every_address_the_module_accepts_the_core_accepts_too_and_host_decides_the_rest(self):
        base = self.g['_base']
        accepted = 0
        for host in self.corpus():
            for tail in ('', '/', ':443', ':1', ':65535', ':0', ':65536', ':', ':x'):
                url = f'https://{host}{tail}'
                try:
                    got = base(self.hand_ctx({'url': url}))
                except dm.ModuleError:
                    got = None
                if got is not None:
                    accepted += 1
                    self.assertTrue(serve._url_result_url_ok(got), (url, got))
                    self.assertTrue(serve._url_host_ok(host.lower()), url)
                elif tail in ('', '/', ':443') and host.isascii() and all(c.isalnum() or c in '.-' for c in host):
                    self.assertFalse(serve._url_host_ok(host.lower()), f'ядро прийняло б хост, який відхилив модуль: {url}')
        self.assertGreater(accepted, 20, 'корпус мусить містити й прийнятні адреси: інакше порівняння порожнє')


class TlsTest(Base):
    """Перевірений TLS із сховищем certifi і версія агента 1.1 (модуль 1.1.0)."""

    def fresh_load(self):
        """Модуль завантажений ЗАНОВО зі шпигуном на `ssl.create_default_context`: `(модуль, виклики, повернуті контексти)`."""
        calls, made = [], []
        real = ssl.create_default_context

        def spy(*a, **kw):
            if 'supabase-comments' not in sys._getframe(1).f_code.co_filename:      # `_tls` інших модулів (supabase-dashboard) — не наші
                return real(*a, **kw)
            calls.append((a, kw))
            made.append(real(*a, **kw))
            return made[-1]
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        with mock.patch.object(ssl, 'create_default_context', spy):
            mod = dm.catalog()[MID]
        return mod, calls, made

    def test_the_opener_verifies_tls_with_the_certifi_store(self):
        try:
            import certifi
        except ImportError:                                  # без certifi — типовий контекст (нижче)
            self.skipTest('certifi не встановлено')
        mod, calls, made = self.fresh_load()
        self.assertEqual(calls, [((), {'cafile': certifi.where()})], 'контекст зі сховищем certifi')
        handlers = [h for h in mod.fn('check').__globals__['_opener'].handlers if isinstance(h, urllib.request.HTTPSHandler)]
        self.assertEqual(len(handlers), 1, 'один HTTPSHandler')
        self.assertIs(handlers[0]._context, made[0], 'саме наш контекст, а не типовий із build_opener')
        self.assertTrue(made[0].check_hostname)
        self.assertEqual(made[0].verify_mode, ssl.CERT_REQUIRED)

    def test_without_certifi_the_default_verified_context_is_used(self):
        with mock.patch.dict(sys.modules, {'certifi': None}):                 # `import certifi` → ImportError
            mod, calls, made = self.fresh_load()
        self.assertEqual(calls, [((), {})])
        handlers = [h for h in mod.fn('check').__globals__['_opener'].handlers if isinstance(h, urllib.request.HTTPSHandler)]
        self.assertIs(handlers[0]._context, made[0])
        self.assertEqual(made[0].verify_mode, ssl.CERT_REQUIRED)

    def test_the_user_agent_is_1_1(self):
        self.assertEqual(self.g['UA'], 'deai-canvas-supabase-comments/1.1')


# ------------------------------------------------------------------------------------ статичні перевірки

class StaticTest(unittest.TestCase):
    def tree(self):
        return ast.parse(_read(SERVER).decode('utf-8'))

    def test_only_the_stdlib_allowlist_is_imported_and_never_the_core(self):
        mods = set()
        for n in ast.walk(self.tree()):
            if isinstance(n, ast.Import):
                mods |= {a.name.split('.')[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or '').split('.')[0])
        self.assertEqual(mods, {'base64', 'json', 're', 'ssl', 'certifi', 'urllib', 'time', 'uuid'})
        for core in ('serve', 'deai_modules', 'spaces'):
            self.assertNotIn(core, mods)

    def test_no_dynamic_code_and_no_process_or_file_access(self):
        names = {n.id for n in ast.walk(self.tree()) if isinstance(n, ast.Name)}
        for banned in ('exec', 'eval', 'compile', '__import__', 'open', 'input', 'globals', 'locals', 'vars', 'print'):
            self.assertNotIn(banned, names, banned)

    def test_the_builtin_list_is_never_called_because_the_module_shadows_it(self):
        tree = self.tree()
        defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        self.assertIn('list', [d.name for d in defs], 'роль `comments` вимагає функції `list`')
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'list']
        self.assertEqual(calls, [], '`def list` тінить вбудовану в усьому exec-модулі: `list(...)` викликав би функцію ролі')
        for n in ast.walk(tree):                                              # і не як значення (`isinstance(x, list)`, `map(list, …)`)
            if isinstance(n, ast.Name) and n.id == 'list':
                self.assertIsInstance(n.ctx, ast.Store, 'ім’я `list` лише в оголошенні')

    def test_the_four_role_functions_have_the_core_signatures(self):
        sigs = {d.name: [a.arg for a in d.args.args] for d in self.tree().body if isinstance(d, ast.FunctionDef)}
        self.assertEqual(sigs['client_config'], ['ctx'])
        self.assertEqual(sigs['list'], ['ctx', 'channel'])
        self.assertEqual(sigs['resolve'], ['ctx', 'channel', 'id', 'reason', 'iteration'])
        self.assertEqual(sigs['check'], ['ctx'])
        self.assertEqual(sigs['_open'], ['req', 'timeout'])

    def test_nothing_identifying_ships_in_the_files_we_wrote(self):
        """Файли модуля публічні: ні справжніх імен, ні хостів, ні пошт, ні ref проєкту Supabase (їх 20 малих літер)."""
        bad = re.compile(r'liga\b|ліга|neodisa|@[a-z0-9.-]+\.[a-z]{2,}|\b[a-z]{20}\.supabase\.co|'
                         r'design-canvas|design office|\.vercel\.app', re.I)
        # Справжні імена й домен звіряємо за SHA-256 слів: тест сам не повинен їх містити (репо публікується).
        forbidden = {
            '1ec49b8f2651da80d5e265bb07aad65d46d1c25279ea6778a14d3b1ed37022f0',
            'e2d279cba45ada22aa30991a04f8fcc7280c7250dcf6454a41e348de6d4627b1',
            '33a9c0fc9430786e1aa9f6401b27357191e471b17c74a4703789eafd88613706',
            '0b16f09772ce87b27dc32a8c609ab5f999f7e5ba7f6cf885621fb81db4a318ef',
            '30586794ac1f653b9561b422dba527afec6fe4f95f832e293bdfeedc1ecffb42',
            '5a68fe329bb3d7474b136e44739ed3ea655bf381c6104297c9c536f5387a59a8',
            '48c6e1190dd76af4a94fcf5827775d9e434743caf23920146c8bb5dc374a8d6a',
        }
        for name in ('server.py', 'adapter.js', 'schema.sql', 'replies.sql', 'README.md', 'module.json', 'LICENSE-supabase-js'):
            text = _read(os.path.join(MODULE_DIR, name)).decode('utf-8')
            found = [m.group(0) for m in bad.finditer(text)]
            found += [w for w in re.findall(r'\w+', text.lower())
                      if hashlib.sha256(w.encode('utf-8')).hexdigest() in forbidden]
            self.assertEqual(found, [], f'{name}: {found}')

    def test_the_schema_keeps_its_guards(self):
        sql = _read(os.path.join(MODULE_DIR, 'schema.sql')).decode('utf-8')
        for must in ('create table if not exists public.comments', 'alter table public.comments enable row level security',
                     'public.cl_project_id_immutable', 'public.cl_delete_scope_guard',
                     'grant select, insert, update, delete on public.comments to anon, authenticated;',
                     'revoke truncate, references, trigger on public.comments from anon, authenticated;',
                     'alter publication supabase_realtime add table public.comments',
                     'drop policy if exists "anon rw" on public.comments', 'at most 25 comments may be deleted per request',
                     'DEDICATED SUPABASE PROJECT', 'ADOPTS'):
            self.assertIn(must, sql, must)
        active = '\n'.join(ln for ln in sql.splitlines() if not ln.lstrip().startswith('--'))
        self.assertNotIn('for all using (true)', active, 'стара відкрита політика "anon rw" не повертається')
        self.assertLess(active.index('grant select, insert, update, delete'), active.index('revoke ' + 'truncate'),
                        'спершу права, потім відібрані зайві (інакше grant повернув би їх)')
        self.assertEqual(re.findall(r'\b(?:on|table|exists|from|into|add table) comments\b', active), [],
                         'кожне імʼя таблиці — з `public.` (не залежить від search_path сесії SQL-редактора)')

    def test_the_readme_covers_setup_security_and_cors(self):
        text = _read(os.path.join(MODULE_DIR, 'README.md')).decode('utf-8')
        for must in ('schema.sql', 'SQL', '/api/module-enable', '"supabase-comments"', '"url"', '"key"', 'https://<ref>.supabase.co',
                     'anon', 'publishable', 'CORS', 'null', 'Access-Control-Allow-Origin', 'service_role', 'sb_secret_', 'max-rows',
                     '1000', 'check-timeout', 'grants', 'dedicated project'):
            self.assertIn(must, text, must)


# --------------------------------------------------------------------------------------- наскрізно через ядро

class EndToEndTest(SeamMixin, tca.ServerEnv):
    """Модуль, увімкнений у просторі ЧЕРЕЗ API (налаштування + секрет), проти справжнього сервера в процесі: сторінка задачі,
    «Огляд», роздача файлів адаптера, шлях агента (`ProjectComments`, `inbox`). REST Supabase — підставний, мережа — лише
    127.0.0.1."""

    def setUp(self):
        super().setUp()
        self.no_proxy_env()
        patch = mock.patch.object(dm, 'builtin_dir', tm._REAL_BUILTIN_DIR)         # `Env` підмінив її на порожню теку
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()
        self.sp = self.plain
        self.origin = f'http://127.0.0.1:{self.port}'
        self.seam_up()
        self.use(self.plain)

    def post(self, path, payload):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=20)
        try:
            conn.request('POST', path, json.dumps(payload).encode('utf-8'), {'Content-Type': 'application/json'})
            r = conn.getresponse()
            raw = r.read().decode('utf-8')
            return r.status, json.loads(raw), raw
        finally:
            conn.close()

    def get_bytes(self, path):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request('GET', path)
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def enable_via_api(self, url=URL, key=KEY):
        st, body, raw = self.post('/api/module-enable', {'space': self.plain['id'], 'id': MID, 'settings': {'url': url},
                                                         'secrets': {'key': key}})
        self.assertEqual(st, 200, raw)
        self.assertNotIn(key, raw, 'ключ у відповіді API')
        return body

    def channel(self, tid='px', internal=False):
        return dm.channel_for(self.plain, tid, internal)

    def page(self, ch='project'):
        st, html = self.fetch(f'/commented?it=it1&ch={ch}')
        self.assertEqual(st, 200, html[:300])
        return html

    def cfg_of(self, html):
        m = re.search(r'window\.__deaiCommentsCfg = (\{.*?\});\n', html)
        self.assertIsNotNone(m, 'у сторінці нема window.__deaiCommentsCfg')
        return json.loads(m.group(1))

    def test_enabling_through_the_api_runs_the_check_against_the_service(self):
        body = self.enable_via_api()
        self.assertEqual(body['check'], {'ok': True, 'detail': 'таблиці comments і comment_replies доступні'})
        self.assertEqual(body['module']['id'], MID)
        self.assertEqual([(r['method'], r['url']) for r in self.seen],
                         [('GET', f'{URL}{TABLE}?select=id&limit=1'), ('GET', f'{URL}{REPLIES}?select=id&limit=1')])
        self.assertEqual(dm.provider('comments', self.plain).id, MID)
        self.assertEqual(dm.capabilities(self.plain)['comments'], MID)

    def test_a_missing_schema_is_reported_as_no_schema_by_the_enable_check(self):
        self.api.no_table = 'PGRST205'
        body = self.enable_via_api()
        self.assertEqual((body['check']['ok'], body['check']['error']), (False, 'no-schema'))
        self.assertIn('schema.sql', body['check']['detail'])

    def test_the_task_page_carries_the_module_snippet_with_the_public_config_and_the_channel(self):
        self.enable_via_api()
        html = self.page('project')
        at = [html.index(s) for s in (
            'window.__clDown = function',
            f'<script src="{self.origin}/app/vendor/comment-layer.min.js"',
            '<script src="/api/module-client/supabase-comments/supabase.min.js"',
            '<script src="/api/module-client/supabase-comments/adapter.js"',
            'window.__deaiCommentsCfg = ', 'window.DeaiComments.create(')]
        self.assertEqual(at, sorted(at), 'банер → шар → supabase-js → адаптер → конфіг → завантажувач')
        self.assertEqual(self.cfg_of(html), {'url': URL, 'key': KEY, 'channel': self.channel()})
        for gone in (sbconf.SB_URL, sbconf.SB_KEY, 'cdn.jsdelivr.net', 'CommentLayerSupabase'):
            self.assertNotIn(gone, html, gone)

    def test_the_two_client_files_are_served_byte_for_byte(self):
        self.enable_via_api()
        for name, path in (('supabase.min.js', BUNDLE), ('adapter.js', ADAPTER)):
            st, heads, data = self.get_bytes(f'/api/module-client/{MID}/{name}')
            self.assertEqual(st, 200, name)
            self.assertEqual(data, _read(path), name)
            self.assertEqual(heads['content-type'], 'text/javascript; charset=utf-8')
            self.assertEqual(heads['x-content-type-options'], 'nosniff')
        st, _, _ = self.get_bytes(f'/api/module-client/{MID}/schema.sql')
        self.assertEqual(st, 404, 'не оголошений файл теки не роздається')
        st, _, _ = self.get_bytes(f'/api/module-client/{MID}/server.py')
        self.assertEqual(st, 404)

    def test_the_overview_config_names_the_adapter_files_and_the_public_config(self):
        self.enable_via_api()
        st, raw = self.fetch('/api/comment-config?ch=project&it=it1')
        self.assertEqual(st, 200, raw)
        body = json.loads(raw)
        self.assertEqual((body['ch'], body['module'], body['channel'], body['config']),
                         ('project', MID, self.channel(), {'url': URL, 'key': KEY}))
        self.assertEqual(body['client'], [f'/api/module-client/{MID}/supabase.min.js', f'/api/module-client/{MID}/adapter.js'])

    def test_a_bad_address_leaves_the_page_local_and_the_check_says_why(self):
        self.enable_via_api()
        st, body, raw = self.post('/api/module-settings', {'space': self.plain['id'], 'id': MID, 'settings': {'url': 'http://abcdefghijkl.supabase.co'}})
        self.assertEqual(st, 200, raw)
        self.assertEqual((body['check']['ok'], body['check']['error']), (False, 'bad-settings'))
        html = self.page('project')
        self.assertNotIn('window.__deaiCommentsCfg', html)
        self.assertNotIn(KEY, html)
        self.assertEqual(len(self.seen), 2, 'після порчі адреси в мережу більше не ходили (лише check при вмиканні: comments і відповіді)')

    def test_a_service_key_never_reaches_a_page_or_the_overview_config(self):
        key = jwt(SERVICE_CLAIMS)
        body = self.enable_via_api(key=key)
        self.assertEqual((body['check']['ok'], body['check']['error'], body['check']['detail']), (False, 'bad-key', SERVICE_TEXT))
        html = self.page('project')
        self.assertNotIn('window.__deaiCommentsCfg', html, 'модуль не вдався: сторінка лишається локальною')
        self.assertNotIn(key, html)
        st, raw = self.fetch('/api/comment-config?ch=project&it=it1')
        self.assertLess(st, 500, raw)
        self.assertNotIn(key, raw)
        self.assertNotIn('"config"', raw)
        self.assertEqual(self.seen, [], 'з сервісним ключем у мережу не ходили')

    def test_the_agent_reads_and_resolves_through_the_module_against_the_service(self):
        self.enable_via_api()
        chan = self.channel('px')
        self.api.rows = [row('c0ffee01-aaaa', chan, text='Кнопку вирівняти', meta={'version': '2/me--welcome', 'seq': 7}),
                         row('c0ffee02-bbbb', chan, text='Інше'),
                         row('c0ffee09-zzzz', self.channel('px', internal=True), text='Внутрішній'),
                         row('c0ffee10-cccc', self.channel('other'), text='Чужа задача')]
        pc = self.pc(self.plain)
        self.assertEqual(pc.kind, 'module')
        pins = pc.pins({}, 'px')
        self.assertEqual([p['id'] for p in pins], ['c0ffee01-aaaa', 'c0ffee02-bbbb'])
        self.assertEqual(pins[0]['text'], 'Кнопку вирівняти')
        self.assertEqual(pins[0]['meta']['seq'], 7)
        pc.resolve({}, 'px', 'c0ffee01-aaaa', 'кнопку вирівняно')
        patch = self.api.reqs('PATCH')[-1]
        self.assertEqual(patch['raw_path'], f'{TABLE}?id=eq.c0ffee01-aaaa&project_id=eq.{q(chan)}&select=id')
        self.assertEqual(json.loads(patch['body']), {'status': 'resolved', 'resolve_reason': 'кнопку вирівняно'})
        after = {p['id']: p for p in pc.pins({}, 'px')}
        self.assertEqual((after['c0ffee01-aaaa']['status'], after['c0ffee01-aaaa']['resolve_reason']), ('resolved', 'кнопку вирівняно'))
        self.assertEqual(after['c0ffee02-bbbb']['status'], 'open')
        self.assertEqual([r['status'] for r in self.api.rows if r['id'] in ('c0ffee09-zzzz', 'c0ffee10-cccc')], ['open', 'open'])
        self.assert_no_legacy()

    def test_the_inbox_cli_lists_and_closes_the_pins_of_the_service(self):
        self.enable_via_api()
        chan = self.channel('px')
        self.api.rows = [row('c0ffee01-aaaa', chan, text='Кнопку вирівняти', meta={'version': '2/me--welcome', 'seq': 7}),
                         row('c0ffee02-bbbb', chan, text='Старе', status='resolved', resolved_v=2)]
        rc, out, err = self.inbox(['--all'])
        self.assertEqual((rc, err), (0, ''), out)
        self.assertIn('модуль supabase-comments', out)
        self.assertIn('• P#7 [2/me--welcome] Кнопку вирівняти  [c0ffee01 · Олена]', out)
        self.assertNotIn('Старе', out)
        self.assertNotIn(KEY, out)
        rc, out, _ = self.inbox(['resolve', 'c0ffee01', '--reason', 'кнопку вирівняно'])
        self.assertEqual(rc, 0, out)
        # 4b-2 (поправка 4): вбудований `supabase-comments` отримує номер ітерації й у звичайному просторі — як у ЛІГИ
        # (колись «(проєкт)» без номера, бо контракт ролі його не мав); власний модуль простору його й далі не отримує
        self.assertIn('✓ c0ffee01 закрито (проєкт, Іт.1): «кнопку вирівняно»', out)
        self.assertEqual(json.loads(self.api.reqs('PATCH')[-1]['body']),
                         {'status': 'resolved', 'resolve_reason': 'кнопку вирівняно', 'resolved_v': 1})
        self.assertEqual(self.api.rows[0]['status'], 'resolved')
        rc, out, _ = self.inbox(['--all'])
        self.assertIn('проєкт: (+ 2 вирішених в історії)', out)
        self.assertNotIn('Кнопку вирівняти', out)
        self.assert_no_legacy()

    def test_the_comments_route_answers_with_the_service_pins(self):
        self.enable_via_api()
        self.api.rows = [row('c0ffee01-aaaa', self.channel('px'), text='Кнопку вирівняти')]
        st, raw = self.fetch('/comments?it=it1&channel=project&all=1')
        self.assertEqual(st, 200, raw)
        body = json.loads(raw)
        self.assertEqual(body['project'], self.channel('px'))
        self.assertEqual([c['id'] for c in body['comments']], ['c0ffee01-aaaa'])
        self.assertNotIn(KEY, raw)

    def test_a_service_that_is_down_degrades_the_agent_path_to_a_clean_error(self):
        self.enable_via_api()
        self.api.stop()
        with self.assertRaises(dm.ModuleError) as cm:
            self.pc(self.plain).pins({}, 'px')
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertNotIn(KEY, ' '.join(self.exc_texts(cm.exception)))
        self.assert_no_legacy()

    def test_the_league_space_takes_the_install_config_not_the_settings_of_the_module_in_another_space(self):
        """4b-2: ЛІГА теж веде коментарі цим модулем (було: «простір ЛІГА модуля не отримує»), але з конфігу УСТАНОВКИ й
        каналом ЛІГИ — а не з налаштувань чи секретів модуля, увімкненого в іншому просторі."""
        self.enable_via_api()                                   # модуль увімкнено в `plain` зі СВОЇМИ адресою й ключем
        self.seen.clear()
        self.use(self.liga)
        self.net.rows = []
        html = self.page('project')
        cfg = self.cfg_of(html)
        self.assertEqual((cfg['url'], cfg['key'], cfg['channel']), (sbconf.SB_URL, sbconf.SB_KEY, 'dc/lx'))
        self.assertNotEqual((URL, KEY), (sbconf.SB_URL, sbconf.SB_KEY), 'контроль: адреси різні')
        self.assertNotIn(KEY, html)
        self.assertEqual(self.seen, [], 'сторінка не ходить у мережу')


if __name__ == '__main__':
    unittest.main()
