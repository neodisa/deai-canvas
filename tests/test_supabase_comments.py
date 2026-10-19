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
мережу (`_opener.open(req, timeout=TIMEOUT_S)`). Тест ОБГОРТАЄ справжню функцію: записує, ЩО модуль адресував (повний `https://`-URL,
метод, заголовки, тіло), а до справжньої `_open` передає той самий запит, переписаний на `http://127.0.0.1:<порт підставного
сервера>`. Решта шляху справжня: побудова запиту й заголовків, власний обробник редиректів, що нікуди не веде, розбір `HTTPError`.
У виробничому коді спеціального «тестового» входу нема: `_open(req)` — звичайна функція.

Кожен тест має власні `HOME`, `DEAI_HOME`, `DC_TASKS_FILE`; справжній `~/.deai` стереже `spaces_guard`.
"""
import ast
import hashlib
import http.client
import json
import os
import re
import socket
import socketserver
import stat
import sys
import threading
import time
import traceback
import unittest
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
TABLE = '/rest/v1/comments'
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
    def override(self, method, status, body=None, headers=None, delay=0, times=None):
        self.overrides.append({'method': method, 'status': status, 'body': body, 'headers': headers or {},
                               'delay': delay, 'times': times})

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
            if o['method'] in (None, rec['method']) and (o['times'] is None or o['times'] > 0):
                if o['times'] is not None:
                    o['times'] -= 1
                return o['status'], o['body'], o['headers'], o['delay']
        if self.redirect_to:
            return self.redirect_code, None, {'Location': self.redirect_to + rec['raw_path']}, 0
        if rec['headers'].get('apikey') != self.key:
            return self._err(rec, 401, 'PGRST301', 'Invalid API key')
        if rec['path'] != TABLE:
            return 404, {'message': 'no such route'}, {}, 0
        if self.no_table == 'PGRST205':
            return self._err(rec, 404, 'PGRST205', "Could not find the table 'public.comments' in the schema cache")
        if self.no_table == '42P01':
            return self._err(rec, 404, '42P01', 'relation "public.comments" does not exist')
        if self.no_table == 'plain':
            return 404, 'Not Found', {}, 0
        reserved = ('select', 'order', 'limit', 'offset')
        matched = list(self.rows)
        for k, vals in rec['query'].items():
            if k in reserved:
                continue
            for v in vals:
                if not v.startswith('eq.'):
                    return self._err(rec, 400, 'PGRST100', f'unsupported operator in {k}')
                matched = [r for r in matched if str(r.get(k)) == v[3:]]
        if rec['method'] == 'GET':
            if (rec['query'].get('order') or [''])[0] == 'id':
                matched.sort(key=lambda r: r['id'])
            cols = (rec['query'].get('select') or ['*'])[0]
            if cols != '*':
                matched = [{c: r.get(c) for c in cols.split(',')} for r in matched]
            lim = (rec['query'].get('limit') or [None])[0]
            if lim is not None:
                matched = matched[:int(lim)]
            return 200, matched, {}, 0
        if rec['method'] == 'PATCH':
            patch = json.loads(rec['body'] or b'{}')
            for r in matched:
                r.update(patch)
            if 'return=representation' in rec['headers'].get('prefer', ''):
                return 200, matched, {}, 0
            return 204, None, {}, 0
        return 405, {'message': 'method not allowed'}, {}, 0


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

        def mapped(req):
            self.seen.append({'url': req.full_url, 'method': req.get_method(), 'data': req.data,
                              'headers': {k.lower(): v for k, v in req.header_items()}})
            sp = urllib.parse.urlsplit(req.full_url)
            new = urllib.request.Request(f'{self.api.base}{sp.path}' + (f'?{sp.query}' if sp.query else ''),
                                         data=req.data, method=req.get_method(), headers=dict(req.header_items()))
            return real_open(new)
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
        self.assertEqual((m.roles, m.name, m.version, m.api, m.dir), (['comments'], 'Supabase', '1.0.0', 1, MODULE_DIR))
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
            'api': 1, 'id': 'supabase-comments', 'name': 'Supabase', 'version': '1.0.0', 'roles': ['comments'],
            'client': ['supabase.min.js', 'adapter.js'],
            'settings': [
                {'key': 'url', 'type': 'text', 'label': 'Адреса проєкту (https://<ref>.supabase.co)', 'required': True},
                {'key': 'key', 'type': 'secret', 'public': True, 'label': 'Публічний ключ (anon / publishable)',
                 'required': True}]})

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
                         ['LICENSE-supabase-js', 'README.md', 'adapter.js', 'module.json', 'schema.sql', 'server.py',
                          'supabase.min.js'])

    def test_loading_leaves_no_bytecode_behind(self):
        dm.catalog()
        self.assertFalse(os.path.exists(os.path.join(MODULE_DIR, '__pycache__')))

    def test_the_constants_are_the_documented_ones(self):
        self.assertEqual((self.g['TIMEOUT_S'], self.g['MAX_ROWS']), (10, 5000))


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
                         [('GET', f'{URL}{TABLE}?project_id=eq.{q(chan)}&order=id&select=*&limit=5001')])
        (rec,) = self.api.requests
        self.assertEqual(rec['raw_path'], f'{TABLE}?project_id=eq.deai%2F{self.sp["id"]}%2Ftask-1&order=id&select=*&limit=5001')
        self.assertEqual(rec['body'], b'')
        self.assertEqual({k: v for k, v in rec['headers'].items() if k in ('apikey', 'authorization', 'accept')},
                         {'apikey': KEY, 'authorization': 'Bearer ' + KEY, 'accept': 'application/json'})

    def test_hostile_channels_stay_inside_one_filter(self):
        ctx = self.ctx()
        for chan in ('deai/s/t&status=eq.open', 'a#b', 'a%26b', 'a+b', 'a b', 'a,b(c)', 'a=b', "o'neil", 'a"b', 'a\\b', 'а/б/в',
                     '../x', 'a?b', 'x' * 190):
            self.api.requests.clear()
            self.fn('list')(ctx, chan)
            (rec,) = self.api.requests
            self.assertEqual(set(rec['query']), {'project_id', 'order', 'select', 'limit'}, chan)
            self.assertEqual(rec['query']['project_id'], ['eq.' + chan], chan)

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
        self.patch_globals(TIMEOUT_S=0.2)
        self.api.override('GET', 200, [], delay=1.5)
        started = time.monotonic()
        e = self.fails('list', self.chan())
        self.assertLess(time.monotonic() - started, 1.4)
        self.assertIn('недоступний', e.message)

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
                         [('PATCH', f'{URL}{TABLE}?id=eq.c1&project_id=eq.{q(self.chan1)}')])
        (rec,) = self.api.requests
        self.assertEqual(rec['raw_path'], f'{TABLE}?id=eq.c1&project_id=eq.deai%2F{self.sp["id"]}%2Ft1')
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
            self.assertEqual(set(rec['query']), {'id', 'project_id'}, repr(cid))
            self.assertEqual(rec['query']['id'], ['eq.' + cid], repr(cid))
        self.assertTrue(all(r['status'] == 'open' for r in self.api.rows), 'жоден рядок не закрився')

    def test_an_empty_id_or_channel_never_becomes_an_unfiltered_patch(self):
        for chan, cid in (('', 'c1'), (self.chan1, ''), (None, 'c1'), (self.chan1, None), (self.chan1, 5), (5, 'c1')):
            with self.assertRaises(dm.ModuleError, msg=repr((chan, cid))) as cm:
                self.fn('resolve')(self.ctx(), chan, cid, 'r')
            self.assertEqual(cm.exception.code, 'module-error')
        self.assertEqual(self.seen, [])
        self.assertTrue(all(r['status'] == 'open' for r in self.api.rows))

    def test_the_reason_may_be_empty_or_missing(self):
        ctx = self.ctx()
        for reason in (None, ''):
            self.api.requests.clear()
            self.fn('resolve')(ctx, self.chan1, 'c2', reason)
            self.assertEqual(json.loads(self.api.requests[0]['body']), {'status': 'resolved', 'resolve_reason': None}, repr(reason))

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
            self.assertEqual(res, {'ok': True, 'detail': 'таблиця comments доступна'})
            (rec,) = self.api.requests
            self.assertEqual((rec['method'], rec['raw_path'], rec['body']), ('GET', f'{TABLE}?select=id&limit=1', b''))
            self.assertEqual((rec['headers']['apikey'], rec['headers']['authorization']), (KEY, 'Bearer ' + KEY))

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
        self.patch_globals(TIMEOUT_S=0.2)
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
        self.assertEqual(dm.check(self.sp, MID), {'ok': True, 'detail': 'таблиця comments доступна'})
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
        self.assertEqual(len(self.seen), 4, 'list, resolve ×2, check; client_config у мережу не ходить')
        for req in self.seen:
            self.assertTrue(req['url'].startswith(f'https://{HOST}/rest/v1/comments'), req['url'])
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
        self.assertEqual(mods, {'json', 're', 'urllib'})
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
        self.assertEqual(sigs['resolve'], ['ctx', 'channel', 'id', 'reason'])
        self.assertEqual(sigs['check'], ['ctx'])
        self.assertEqual(sigs['_open'], ['req'])

    def test_nothing_identifying_ships_in_the_files_we_wrote(self):
        """Файли модуля публічні: ні справжніх імен, ні хостів, ні пошт, ні ref проєкту Supabase (їх 20 малих літер)."""
        bad = re.compile(r'liga\b|ліга|neodisa|@[a-z0-9.-]+\.[a-z]{2,}|\b[a-z]{20}\.supabase\.co|'
                         r'design-canvas|design office|\.vercel\.app', re.I)
        for name in ('server.py', 'adapter.js', 'schema.sql', 'README.md', 'module.json', 'LICENSE-supabase-js'):
            text = _read(os.path.join(MODULE_DIR, name)).decode('utf-8')
            found = [m.group(0) for m in bad.finditer(text)]
            self.assertEqual(found, [], f'{name}: {found}')

    def test_the_schema_keeps_its_guards(self):
        sql = _read(os.path.join(MODULE_DIR, 'schema.sql')).decode('utf-8')
        for must in ('create table if not exists comments', 'enable row level security', 'cl_project_id_immutable',
                     'cl_delete_scope_guard', 'revoke truncate, references, trigger', 'supabase_realtime',
                     'drop policy if exists "anon rw"', 'at most 25 comments may be deleted per request'):
            self.assertIn(must, sql, must)
        active = '\n'.join(ln for ln in sql.splitlines() if not ln.lstrip().startswith('--'))
        self.assertNotIn('for all using (true)', active, 'стара відкрита політика "anon rw" не повертається')

    def test_the_readme_covers_setup_security_and_cors(self):
        text = _read(os.path.join(MODULE_DIR, 'README.md')).decode('utf-8')
        for must in ('schema.sql', 'SQL', '/api/module-enable', '"supabase-comments"', '"url"', '"key"', 'https://<ref>.supabase.co',
                     'anon', 'publishable', 'CORS', 'null', 'Access-Control-Allow-Origin'):
            self.assertIn(must, text, must)


# --------------------------------------------------------------------------------------- наскрізно через ядро

class EndToEndTest(SeamMixin, tca.ServerEnv):
    """Модуль, увімкнений у просторі ЧЕРЕЗ API (налаштування + секрет), проти справжнього сервера в процесі: сторінка задачі,
    «Огляд», роздача файлів адаптера, шлях агента (`ProjectComments`, `inbox`). REST Supabase — підставний, мережа — лише
    127.0.0.1."""

    def setUp(self):
        super().setUp()
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
        self.assertEqual(body['check'], {'ok': True, 'detail': 'таблиця comments доступна'})
        self.assertEqual(body['module']['id'], MID)
        self.assertEqual([(r['method'], r['url']) for r in self.seen], [('GET', f'{URL}{TABLE}?select=id&limit=1')])
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
        for gone in (serve.SUPABASE_URL, serve.SUPABASE_KEY, 'cdn.jsdelivr.net', 'CommentLayerSupabase'):
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
        self.assertEqual(len(self.seen), 1, 'після порчі адреси в мережу більше не ходили')

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
        pc.resolve({}, 'px', 'c0ffee01-aaaa', 'кнопку вирівняно', legacy=lambda: self.fail('legacy'))
        patch = self.api.reqs('PATCH')[-1]
        self.assertEqual(patch['raw_path'], f'{TABLE}?id=eq.c0ffee01-aaaa&project_id=eq.{q(chan)}')
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
        rc, out, err = self.inbox([])
        self.assertEqual((rc, err), (0, ''), out)
        self.assertIn('модуль supabase-comments', out)
        self.assertIn('• P#7 [2/me--welcome] Кнопку вирівняти  [c0ffee01 · Олена]', out)
        self.assertNotIn('Старе', out)
        self.assertNotIn(KEY, out)
        rc, out, _ = self.inbox(['resolve', 'c0ffee01', '--reason', 'кнопку вирівняно'])
        self.assertEqual(rc, 0, out)
        self.assertIn('✓ c0ffee01 закрито (проєкт): «кнопку вирівняно»', out)
        self.assertEqual(self.api.rows[0]['status'], 'resolved')
        rc, out, _ = self.inbox([])
        self.assertIn('проєкт: (+ 2 вирішених в історії)', out)
        self.assertNotIn('Кнопку вирівняти', out)
        self.assert_no_legacy()

    def test_the_comments_route_answers_with_the_service_pins(self):
        self.enable_via_api()
        self.api.rows = [row('c0ffee01-aaaa', self.channel('px'), text='Кнопку вирівняти')]
        st, raw = self.fetch('/comments?it=it1&channel=project')
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

    def test_the_league_space_is_untouched_by_the_module(self):
        self.use(self.liga)
        self.net.rows = []
        html = self.page('project')
        self.assertNotIn('supabase-comments', html)
        self.assertEqual(self.seen, [])


if __name__ == '__main__':
    unittest.main()
