"""`app/modules/vercel-publish`: публікація зібраного превʼю на ВЛАСНИЙ Vercel людини через REST API (stdlib).

Модуль вантажиться через справжній `deai_modules.catalog()` (маніфест, `publish_target: url`, `module_ctx`, `call`,
`check`): так тест бачить саме те, що виконає сервер, зокрема `ctx['ModuleError']`, який ядро кладе в `ctx`.

⛔ Жодного реального запиту до Vercel чи будь-якого хоста поза машиною. Світ тесту:
  * ПІДСТАВНИЙ `api.vercel.com` — `ThreadingHTTPServer` на `127.0.0.1:0` у потоці; записує КОЖЕН запит (метод, шлях,
    запит, заголовки, тіло); відповіді за сценарієм тесту (послідовність `readyState`, `alias`, список публікацій,
    коди помилок, зайняте імʼя проєкту, довільні перевизначення);
  * ПІДСТАВНИЙ САЙТ превʼю — другий такий сервер для перевірки «чи відкривається без входу» (200 / редирект на вхід
    Vercel / 401 …);
  * РОЗТЯЖКА (`Tripwire`): `socket.getaddrinfo` і `socket.socket.connect` пропускають лише `127.0.0.1`; будь-яка
    спроба піти деінде — запис і відмова, а `tearDown` падає, навіть якщо модуль цю відмову проковтнув.

Шов перевірки превʼю. Адреса, яку модуль перевіряє, — `https://<alias>.vercel.app` (https — вимога ядра), тож
локальному HTTP-серверу вона не підходить, а піднімати TLS заради тесту зайве. Шов — імʼя `_fetch_preview` у
глобалах модуля: тест ОБГОРТАЄ справжню функцію (запамʼятовує оригінал, а до нього передає ту саму адресу, переписану
на `http://127.0.0.1:<порт сайту>`). Решта шляху справжня: побудова запиту (без `Authorization`), власний
обробник редиректів, що нікуди не веде, обробка `HTTPError` 3xx/4xx, розбір `Location`. У виробничому коді
спеціального «тестового» входу нема: `_fetch_preview(url)` — звичайна функція.

Кожен тест має власні `HOME`, `DEAI_HOME`, `DC_TASKS_FILE`; справжній `~/.deai` стереже `spaces_guard`.
"""
import ast
import hashlib
import io
import json
import os
import shutil
import socket
import socketserver
import sys
import tempfile
import threading
import time
import traceback
import unittest
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, _HERE)
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import deai_modules as dm  # noqa: E402
import serve  # noqa: E402  — лише `_checked_url_result`: перевірка відповіді модуля тими ж правилами, що в ядра

MODULE_DIR = os.path.join(os.path.dirname(_HERE), 'app', 'modules', 'vercel-publish')
SERVER = os.path.join(MODULE_DIR, 'server.py')
MID = 'vercel-publish'
TOKEN = 'vcp_SECRET-token-9f3a1c7e'
PASSWORD = 'preview-pw-ONLY-for-the-gate'
_ENV = ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE')
_REAL = None
LOOPBACK = ('127.0.0.1',)
SITE_URL = 'https://pv-x.vercel.app'


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def put(path, text='x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def sha1(data):
    return hashlib.sha1(data).hexdigest()


# ------------------------------------------------------------------------------------- підставні сервери

class _HTTPD(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):                              # без `getfqdn`: жодних зайвих DNS-запитів навіть на старті
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = '127.0.0.1', self.server_address[1]


class _Server:
    """Сервер у потоці на `127.0.0.1:0`. `respond(rec) -> (статус, тіло, заголовки)`; тіло: dict/list → JSON,
    str/bytes — як є, `None` — порожнє. Кожен запит — у `requests` (повні заголовки з малими літерами, тіло)."""

    def __init__(self, respond):
        self.requests = []
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def _serve(self):
                n = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(n) if n else b''
                parts = urllib.parse.urlsplit(self.path)
                query = {k: (v[0] if len(v) == 1 else v)
                         for k, v in urllib.parse.parse_qs(parts.query, keep_blank_values=True).items()}
                rec = {'method': self.command, 'path': parts.path, 'raw_path': self.path, 'query': query,
                       'headers': {k.lower(): v for k, v in self.headers.items()}, 'body': body}
                with outer._lock:
                    outer.requests.append(rec)
                status, payload, headers = respond(rec)
                if status == 'drop':                    # обрив: зʼєднання закрито без відповіді
                    self.close_connection = True
                    return
                ctype = 'application/json'
                if payload is None:
                    data = b''
                elif isinstance(payload, (dict, list)):
                    data = json.dumps(payload).encode('utf-8')
                elif isinstance(payload, bytes):
                    data = payload
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

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _serve

            def log_message(self, *args):
                pass

        self.httpd = _HTTPD(('127.0.0.1', 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base = f'http://127.0.0.1:{self.port}'
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()
        self.stopped = False

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)


class FakeVercel(_Server):
    """Підставний `api.vercel.com`: сценарій задають поля, а `overrides` перебивають будь-який маршрут."""

    def __init__(self, token=TOKEN):
        self.token = token
        self.project_id = 'prj_mine'
        self.dep_project_id = None                      # projectId у відповідях про публікацію (типово — `project_id`)
        self.taken = 0                                  # перші N перевірок імені проєкту — «зайнято» (200)
        self.states = ['QUEUED', 'BUILDING', 'READY']   # послідовність readyState; остання повторюється
        self.aliases = ['pv-x.vercel.app']
        self.deployment_url = 'pv-x-abc123-team.vercel.app'
        self.dep_id = 'dpl_cur'
        self.error_message = 'Build failed: boom'
        self.listing = []
        self.delete_fail = set()
        self.overrides = []
        self.digest_mismatch = []
        self.projects = {}                              # імʼя → id проєктів, що «вже є в акаунті»
        self.project_delete_fail = False
        self.bad_token_status = 401                     # 401 чи 403+invalidToken — Vercel роблять обидва
        self.alias_lag = 0                              # скільки відповідей READY іще БЕЗ alias (`aliasAssigned: null`)
        self.alias_never = False                        # alias так і не призначається
        self.alias_error = None                         # `aliasError` у відповіді READY
        self.omit_project_id = False                    # відповіді про публікацію без `projectId`
        self.known_deployments = {}                     # id давніших публікацій → їхній projectId
        self.ready_polls = 0
        self._state_lock = threading.Lock()
        super().__init__(self.respond)

    # ---- сценарій
    def override(self, method, prefix, status, body=None, headers=None, delay=0, times=None):
        """Перебити маршрут; `times=N` — лише N перших разів; `status='drop'` — обрив зʼєднання без відповіді."""
        self.overrides.append({'method': method, 'prefix': prefix, 'status': status, 'body': body,
                               'headers': headers or {}, 'delay': delay, 'times': times})

    def reqs(self, method=None, prefix=None):
        return [r for r in self.requests
                if (method is None or r['method'] == method) and (prefix is None or r['path'].startswith(prefix))]

    def bodies(self, prefix):
        return [json.loads(r['body']) for r in self.reqs('POST', prefix)]

    # ---- відповіді
    def respond(self, rec):
        for o in self.overrides:
            if o['method'] == rec['method'] and rec['path'].startswith(o['prefix']):
                with self._state_lock:
                    if o['times'] is not None:
                        if o['times'] <= 0:
                            continue
                        o['times'] -= 1
                if o['status'] == 'pass':               # цей виклик — звичайна відповідь (для чергування збоїв і успіхів)
                    break
                if o['delay']:
                    time.sleep(o['delay'])
                return o['status'], o['body'], o['headers']
        if rec['headers'].get('authorization') != 'Bearer ' + self.token:
            return self.bad_token_status, {'error': {'code': 'forbidden', 'message': 'Not authorized',
                                                      'invalidToken': True}}, {}
        m, p = rec['method'], rec['path']
        pid = self.dep_project_id or self.project_id
        if m == 'GET' and p == '/v2/user':
            return 200, {'user': {'username': 'alice', 'name': 'Alice A.', 'email': 'alice@example.com'}}, {}
        if m == 'GET' and p.startswith('/v2/teams/'):
            return 200, {'id': 'team_abc', 'slug': 'acme', 'name': 'Acme Inc'}, {}
        if m == 'GET' and p.startswith('/v9/projects/'):
            with self._state_lock:
                taken = self.taken > 0
                if taken:
                    self.taken -= 1
            key = p.rsplit('/', 1)[1]                    # Vercel приймає і імʼя, і id проєкту
            if taken:
                return 200, {'id': 'prj_taken', 'name': key}, {}
            for name, prj in reversed(list(self.projects.items())):       # в усіх проєктів один id — береться останній
                if key in (name, prj):
                    return 200, {'id': prj, 'name': name}, {}
            return 404, {'error': {'code': 'not_found', 'message': 'Project not found'}}, {}
        if m == 'DELETE' and p.startswith('/v9/projects/'):
            if self.project_delete_fail:
                return 500, {'error': {'code': 'internal', 'message': 'cannot delete project'}}, {}
            key = p.rsplit('/', 1)[1]
            for name in [n for n, prj in self.projects.items() if key in (n, prj)]:
                del self.projects[name]
            return 200, {}, {}
        if m == 'POST' and p == '/v2/files':
            if rec['headers'].get('x-vercel-digest') != sha1(rec['body']):
                self.digest_mismatch.append(rec['headers'].get('x-vercel-digest'))
            return 200, {'urls': []}, {}
        if m == 'POST' and p == '/v13/deployments':
            try:
                self.projects.setdefault(json.loads(rec['body'])['name'], pid)     # проєкт «створився» разом із публікацією
            except (ValueError, KeyError):
                pass
            body = {'id': self.dep_id, 'url': self.deployment_url, 'readyState': 'QUEUED', 'projectId': pid}
            if self.omit_project_id:
                del body['projectId']
            return 200, body, {}
        if m == 'GET' and p.startswith('/v13/deployments/'):
            uid = p.rsplit('/', 1)[1]
            if uid in self.known_deployments:           # давніша публікація: лише її проєкт, станів не чіпаємо
                return 200, {'id': uid, 'readyState': 'READY', 'projectId': self.known_deployments[uid]}, {}
            if uid != self.dep_id:
                return 404, {'error': {'code': 'not_found', 'message': 'Deployment not found'}}, {}
            with self._state_lock:
                st = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            body = {'id': uid, 'readyState': st, 'url': self.deployment_url, 'projectId': pid}
            if self.omit_project_id:
                del body['projectId']
            if st == 'READY':
                with self._state_lock:
                    self.ready_polls += 1
                    assigned = not self.alias_never and not self.alias_error and self.ready_polls > self.alias_lag
                body['alias'] = list(self.aliases) if assigned else []
                body['aliasAssigned'] = 1760000000000 if assigned else None
                if self.alias_error:
                    body['aliasError'] = dict(self.alias_error) if isinstance(self.alias_error, dict) else self.alias_error
            if st in ('ERROR', 'CANCELED', 'BLOCKED', 'DELETED'):
                body['errorMessage'] = self.error_message
            return 200, body, {}
        if m == 'GET' and p == '/v6/deployments':
            return 200, {'deployments': list(self.listing)}, {}
        if m == 'DELETE' and p.startswith('/v13/deployments/'):
            uid = p.rsplit('/', 1)[1]
            if uid in self.delete_fail:
                return 500, {'error': {'code': 'internal', 'message': 'cannot delete ' + uid}}, {}
            return 200, {'uid': uid, 'state': 'DELETED'}, {}
        return 404, {'error': {'code': 'not_found', 'message': 'no such route'}}, {}


class FakeSite(_Server):
    """Підставний сайт превʼю: `mode` вирішує, що бачить перевірка «відкривається без входу?»."""

    def __init__(self):
        self.mode = '200'
        self.script = []                                # режими «по одному на запит», далі — `mode`
        super().__init__(self.respond)

    def respond(self, rec):
        m = self.script.pop(0) if self.script else self.mode
        if m == '200':
            return 200, '<h1>preview</h1>', {}
        if m == 'login':
            return 302, '', {'Location': 'https://vercel.com/login?next=%2F&teamId=team_x'}
        if m == 'sso':
            return 307, '', {'Location': 'https://vercel.com/sso-api?url=https%3A%2F%2Fpv-x.vercel.app'}
        if m == 'sub-login':
            return 302, '', {'Location': 'https://accounts.vercel.com/login'}
        if m == 'lookalike':                            # `evilvercel.com` НЕ `vercel.com`
            return 302, '', {'Location': 'https://evilvercel.com/login'}
        if m == 'same-host':
            return 301, '', {'Location': '/index.html'}
        if m in ('401', '403', '404', '500'):
            return int(m), 'nope', {}
        raise AssertionError(m)


class _Runaway(BaseException):
    """НЕ `Exception`: модуль, що ковтає `Exception` (очікування alias, прибирання…), цього не проковтне."""


class _TimeGuard:
    """Підміна `time` у глобалах модуля: рахує `sleep` і після `LIMIT` кидає `_Runaway`. Цикл опитування, що (через
    помилку в модулі) не закінчується, падає за секунди, а не висить до тайм-ауту всього прогону."""
    LIMIT = 2000

    def __init__(self):
        self.sleeps = 0

    def sleep(self, seconds):
        self.sleeps += 1
        if self.sleeps > self.LIMIT:
            raise _Runaway('runaway polling loop in the module')
        time.sleep(seconds)

    def monotonic(self):
        return time.monotonic()


class Tripwire:
    """Лише `127.0.0.1`: усе інше — запис у `violations` і `OSError`. Стереже `getaddrinfo` (імена) і
    `socket.connect` (сама спроба зʼєднання, навіть за готовою адресою)."""

    def __init__(self):
        self.violations = []
        self._patches = []

    def start(self):
        real_gai = socket.getaddrinfo
        real_connect = socket.socket.connect
        real_connect_ex = socket.socket.connect_ex
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


def entries(n, pid='prj_mine', current='dpl_cur', name='pv-12345678'):
    """Список публікацій для `GET /v6/deployments`: `current` найновіша, далі `o1`…`o<n-1>` усе старішими. Порядок у
    відповіді — НЕ за часом (модуль сортує сам)."""
    out = [{'uid': current, 'created': 1000, 'projectId': pid, 'name': name}]
    out += [{'uid': f'o{i}', 'created': 1000 - i * 10, 'projectId': pid, 'name': name} for i in range(1, n)]
    return out[1:] + out[:1]


STATE = {'project': 'pv-12345678', 'project_id': 'prj_mine', 'deployment': 'dpl_old', 'task': 't1'}


class Base(unittest.TestCase):
    """Справжній `app/modules`, справжній `deai_modules`; тимчасові HOME/DEAI_HOME/DC_TASKS_FILE; підставні сервери."""

    def setUp(self):
        self.tmp = os.path.normpath(tempfile.mkdtemp(prefix='vercelpub-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.saved = {k: os.environ.get(k) for k in _ENV}
        self.home = os.path.join(self.tmp, 'home')
        os.makedirs(self.home)
        self.deai = os.path.join(self.home, 'stuff', 'deai')
        os.environ['HOME'] = self.home
        os.environ['DEAI_HOME'] = self.deai
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp, 'legacy', 'tasks.json')
        self.tool = os.path.join(self.home, 'tools', 'dc')
        os.makedirs(self.tool)
        patch = mock.patch.object(spaces, 'ROOT', self.tool)
        patch.start()
        self.addCleanup(patch.stop)
        spaces.clear_request_space()
        dm.reset_caches()
        self.deadlock = threading.Event()

        def wake():
            self.deadlock.set()
            try:
                spaces.WRITE_LOCK.release()
            except RuntimeError:
                pass
        self.watchdog = threading.Timer(20, wake)
        self.watchdog.daemon = True
        self.watchdog.start()
        sid = spaces.create_space('Alpha', 'space-1', os.path.join(self.home, 'work', 'alpha'))
        self.sp = next(s for s in spaces.read_registry()['spaces'] if s['id'] == sid)
        self.m = dm.catalog()[MID]
        self.api = FakeVercel()
        self.addCleanup(self.api.stop)
        self.site = FakeSite()
        self.addCleanup(self.site.stop)
        self.api.projects['pv-12345678'] = 'prj_mine'    # проєкт зі `STATE` у акаунті є, і його остання публікація теж
        self.api.known_deployments['dpl_old'] = 'prj_mine'
        self.evil = _Server(lambda rec: (200, {'stolen': True}, {}))     # «чужий хост», куди токен потрапляти не мусить
        self.addCleanup(self.evil.stop)
        # розтяжка — ПІСЛЯ серверів; системні проксі не мають підмінити loopback на машині дизайнера
        proxies = mock.patch('urllib.request.getproxies', return_value={})
        proxies.start()
        self.addCleanup(proxies.stop)
        self.trip = Tripwire()
        self.trip.start()
        self.addCleanup(self.trip.stop)
        self.preview_urls = []
        self.build = os.path.join(self.tmp, 'build')
        self.make_build({'index.html': '<h1>v1</h1>', 'assets/app.css': 'a{}'})

    def tearDown(self):
        self.watchdog.cancel()
        spaces.clear_request_space()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        dm.reset_caches()
        violations = list(self.trip.violations)
        self.trip.stop()
        if self.deadlock.is_set():
            self.fail('тест завис на WRITE_LOCK')
        self.assertEqual(violations, [], 'модуль спробував вийти за межі 127.0.0.1')

    # ---- фікстури
    def hp(self, *parts):
        return os.path.join(self.home, *parts)

    def make_build(self, files):
        shutil.rmtree(self.build, ignore_errors=True)
        os.makedirs(self.build)
        for rel, text in files.items():
            put(os.path.join(self.build, rel), text)

    def ctx(self, token=TOKEN, team=None):
        """Справжній `ctx` ядра: токен і пароль — через `write_secrets`, `team` — через налаштування модуля."""
        dm.write_secrets(self.sp['id'], MID, {'token': token, 'password': PASSWORD})
        if team is not None:
            dm.write_module_state(self.sp, MID, settings={'team': team})
        return dm.module_ctx(self.sp, MID)

    def fn(self, name):
        return self.m.fn(name)

    def patched(self, **extra):
        """Глобали модуля на час виклику: база підставного API, швидке опитування, шов перевірки превʼю."""
        g = self.fn('publish').__globals__
        real_fetch = g['_fetch_preview']

        def mapped(url, *a, **k):
            self.preview_urls.append(url)
            sp = urllib.parse.urlsplit(url)
            return real_fetch(f'http://127.0.0.1:{self.site.port}{sp.path or "/"}', *a, **k)
        over = {'API_BASE': self.api.base, 'POLL_S': 0.001, 'POLL_MAX_S': 10, 'ALIAS_MAX_S': 1,
                'VERIFY_RETRY_S': 0.001, '_fetch_preview': mapped, 'time': _TimeGuard()}
        over.update(extra)
        return mock.patch.dict(g, over)

    def publish(self, state=None, ctx=None, core=False, tid='t1', **extra):
        """Публікація. `core=True` — через `dm.call` (як диспетчер: коди й статуси ядра, секрети вирізаються);
        інакше — функція модуля напряму (так видно, що кидає САМ модуль)."""
        ctx = ctx if ctx is not None else self.ctx()
        task = {'id': tid, 'title': 'T', 'dir': self.hp('t', tid), 'state': {} if state is None else state}
        with self.patched(**extra):
            if core:
                return dm.call(self.m, 'publish', ctx, self.build, task)
            return self.fn('publish')(ctx, self.build, task)

    def fails(self, **kw):
        try:
            self.publish(**kw)
        except BaseException as e:  # noqa: BLE001
            return e
        self.fail('очікували виняток')

    def check(self, ctx=None):
        with self.patched():
            return self.fn('check')(ctx if ctx is not None else self.ctx())

    # ---- перевірки
    @staticmethod
    def msg(e):
        """Текст, який побачить людина: `message` помилки ядра (без префікса `module-error: ` з `str`) чи `str`."""
        m = getattr(e, 'message', None)
        return m if isinstance(m, str) else str(e)

    def assertUncoded(self, e):
        """Збій без власного коду: `ModuleError('module-error')` ядра (502) — і з чистим текстом: без імені класу
        (`RuntimeError: …`, `_NetworkError: …`, `_HttpError: …`), яке ядро дописало б само до звичайного винятку й яке
        людина побачила б у діалозі. Коди `vercel-auth`/`vercel-busy` сюди не підходять."""
        self.assertIsInstance(e, dm.ModuleError, repr(e))
        self.assertEqual(e.code, 'module-error', repr(e))
        self.assertNotRegex(e.message, r'^_?\w*(?:Error|Exception)\b', 'у тексті — імʼя класу винятку')
        self.assertTrue(e.message.strip(), 'порожній текст помилки')

    @staticmethod
    def blob(rec, skip_auth=False):
        heads = ''.join(f'{k}: {v}\n' for k, v in rec['headers'].items() if not (skip_auth and k == 'authorization'))
        return (rec['method'] + ' ' + rec['raw_path'] + '\n' + heads).encode('utf-8') + rec['body']

    def exc_texts(self, e):
        out = [str(e), repr(e), getattr(e, 'message', ''), getattr(e, '_full', '')]
        out.append(''.join(traceback.format_exception(type(e), e, e.__traceback__)))
        return out


# -------------------------------------------------------------------------------------------------- каталог

class Catalog(Base):
    def test_the_real_catalog_loads_vercel_publish(self):
        m = dm.catalog()[MID]
        self.assertEqual((m.status, m.error), ('ok', None))
        self.assertEqual(m.roles, ['publish'])
        self.assertEqual(m.publish_target, 'url')
        self.assertEqual((m.api, m.name, m.version, m.dir), (1, 'Vercel', '1.2.0', MODULE_DIR))
        by = {s['key']: s for s in m.settings}
        self.assertEqual(list(by), ['auth', 'token', 'team', 'password', 'compat'])        # 4b-1: `auth` (token | cli) — перший
        self.assertEqual((by['token']['type'], by['token']['required']), ('secret', False))   # обовʼязковість у режимі `token` — у модулі
        self.assertEqual((by['team']['type'], by['team']['required']), ('text', False))
        self.assertEqual((by['password']['type'], by['password']['required']), ('secret', False))
        self.assertEqual(m.secret_keys(), ['token', 'password'])
        self.assertTrue(callable(m.fn('check')) and callable(m.fn('publish')))

    def test_manifest_on_disk(self):
        with open(os.path.join(MODULE_DIR, 'module.json'), encoding='utf-8') as f:
            man = json.load(f)
        self.assertEqual((man['api'], man['id'], man['roles'], man['publish_target']), (1, MID, ['publish'], 'url'))

    def test_loading_leaves_no_bytecode_behind(self):
        dm.catalog()
        self.assertFalse(os.path.exists(os.path.join(MODULE_DIR, '__pycache__')))

    def test_the_constants_are_the_documented_ones(self):
        g = self.fn('publish').__globals__
        self.assertEqual((g['API_BASE'], g['POLL_S'], g['POLL_MAX_S'], g['KEEP']),
                         ('https://api.vercel.com', 1.5, 180, 3))
        self.assertEqual((g['ALIAS_MAX_S'], g['UPLOAD_TOTAL_S'], g['CLEANUP_MAX_S'], g['MAX_FILES'], g['MAX_FILE_BYTES'],
                          g['VERIFY_RETRIES'], g['VERIFY_RETRY_S'], g['POLL_TRANSIENT'], g['UPLOAD_RETRIES']),
                         (30, 300, 60, 5000, 50 << 20, 2, 1.5, 3, 1))


# ------------------------------------------------------------------------------------------ повний цикл

class FullCycle(Base):
    def test_the_whole_cycle_request_by_request(self):
        self.make_build({'index.html': 'A', 'a/b.css': 'B', 'c/dup.txt': 'A'})     # index.html і c/dup.txt — один вміст
        self.api.listing = entries(1)
        res = self.publish()
        reqs = [(r['method'], r['path']) for r in self.api.requests]
        probe = reqs[0]
        self.assertEqual(probe[0], 'GET')
        self.assertRegex(probe[1], r'^/v9/projects/pv-\d{8}$')
        name = probe[1].rsplit('/', 1)[1]
        self.assertEqual(reqs[1:4], [('POST', '/v2/files'), ('POST', '/v2/files'), ('POST', '/v13/deployments')])
        polls = [r for r in reqs[4:] if r[0] == 'GET' and r[1] == '/v13/deployments/dpl_cur']
        self.assertEqual(len(polls), 3)                                             # QUEUED, BUILDING, READY
        self.assertEqual(reqs[4:7], polls)
        self.assertEqual(reqs[7:], [('GET', '/v6/deployments')])                    # одна публікація: видаляти нічого
        # файли: по разу на вміст, у порядку першого зустрічання за відсортованими шляхами (a/b.css → B, c/dup.txt → A)
        up = self.api.reqs('POST', '/v2/files')
        self.assertEqual([r['body'] for r in up], [b'B', b'A'])
        for r in up:
            self.assertEqual(r['headers']['content-type'], 'application/octet-stream')
            self.assertEqual(r['headers']['x-vercel-digest'], sha1(r['body']))
            self.assertEqual(r['headers']['content-length'], str(len(r['body'])))
        self.assertEqual(self.api.digest_mismatch, [])
        # тіло публікації
        (body,) = self.api.bodies('/v13/deployments')
        self.assertEqual(set(body), {'name', 'project', 'target', 'files', 'projectSettings'})
        self.assertEqual((body['name'], body['project'], body['target']), (name, name, 'production'))
        self.assertEqual(body['projectSettings'], {'framework': None})
        self.assertEqual(body['files'], [
            {'file': 'a/b.css', 'sha': sha1(b'B'), 'size': 1},
            {'file': 'c/dup.txt', 'sha': sha1(b'A'), 'size': 1},
            {'file': 'index.html', 'sha': sha1(b'A'), 'size': 1}])
        self.assertEqual(self.api.reqs('POST', '/v13/deployments')[0]['headers']['content-type'], 'application/json')
        # результат
        self.assertEqual(res, {'url': SITE_URL, 'verified': True, 'warnings': [],
                               'state': {'project': name, 'project_id': 'prj_mine', 'deployment': 'dpl_cur',
                                         'task': 't1'}})
        self.assertEqual(self.preview_urls, [SITE_URL])
        for r in self.api.requests:
            self.assertEqual(r['headers']['authorization'], 'Bearer ' + TOKEN)

    def test_nested_and_hidden_files_are_published_with_posix_paths(self):
        self.make_build({'index.html': 'i', 'a/b/c.js': 'c', '.well-known/x': 'x', 'ü/файл.txt': 'u'})
        self.publish()
        (body,) = self.api.bodies('/v13/deployments')
        self.assertEqual([f['file'] for f in body['files']], sorted(['index.html', 'a/b/c.js', '.well-known/x', 'ü/файл.txt']))

    def test_an_empty_file_is_uploaded_too(self):
        self.make_build({'index.html': 'i', 'empty.txt': ''})
        self.publish()
        up = self.api.reqs('POST', '/v2/files')
        self.assertIn(b'', [r['body'] for r in up])
        self.assertEqual(self.api.digest_mismatch, [])

    def test_the_same_content_is_uploaded_once(self):
        self.make_build({'a.txt': 'same', 'b.txt': 'same', 'c.txt': 'same', 'd.txt': 'other'})
        self.publish()
        up = self.api.reqs('POST', '/v2/files')
        self.assertEqual(sorted(r['body'] for r in up), [b'other', b'same'])

    def test_the_second_publish_with_the_state_looks_the_project_up_by_id_and_reuses_it(self):
        first = self.publish()
        self.api.requests.clear()
        self.api.dep_id = 'dpl_two'
        second = self.publish(state=first['state'])
        probes = self.api.reqs('GET', '/v9/projects')
        self.assertEqual([r['path'] for r in probes], ['/v9/projects/prj_mine'])                        # одна: за id
        (body,) = self.api.bodies('/v13/deployments')
        self.assertEqual((body['name'], body['project']), (first['state']['project'],) * 2)
        self.assertEqual(second['state'], {'project': first['state']['project'], 'project_id': 'prj_mine',
                                          'deployment': 'dpl_two', 'task': 't1'})
        self.assertEqual(second['url'], first['url'])

    def test_the_result_passes_the_core_validation(self):
        self.api.aliases = []                           # попередження про адресу + захист — найбагатший вихід
        self.site.mode = '401'
        self.api.listing = entries(6)
        self.api.delete_fail = {'o3'}
        res = self.publish(state=STATE)
        self.assertEqual(set(res), {'url', 'state', 'verified', 'warnings'})
        self.assertIs(res['verified'], False)
        url, state, verified, warnings = serve._checked_url_result(res)          # те саме, що перевірить ядро
        self.assertEqual((url, verified, warnings), (res['url'], False, res['warnings']))
        self.assertTrue(url.startswith('https://'))
        self.assertNotIn('#', url)
        self.assertFalse(any(ord(c) <= 32 or c == '\\' for c in url))
        self.assertLessEqual(len(url), 2048)
        self.assertEqual(set(state), {'project', 'project_id', 'deployment', 'task'})
        self.assertTrue(all(v is None or isinstance(v, (str, int, float, bool)) for v in state.values()))
        self.assertLessEqual(len(json.dumps(state)), 4096)
        self.assertLessEqual(len(warnings), 5)
        self.assertTrue(len(warnings) >= 3)
        self.assertTrue(all(isinstance(w, str) and 0 < len(w) <= 300 for w in warnings))

    def test_every_request_has_its_own_timeout(self):
        calls = []
        orig = urllib.request.OpenerDirector.open

        def spy(opener, fullurl, data=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
            req_url = fullurl.full_url if hasattr(fullurl, 'full_url') else fullurl
            method = fullurl.get_method() if hasattr(fullurl, 'get_method') else 'GET'
            calls.append((method, urllib.parse.urlsplit(req_url).path, timeout))
            return orig(opener, fullurl, data, timeout)
        self.api.listing = entries(1)
        with mock.patch.object(urllib.request.OpenerDirector, 'open', spy):
            self.publish()
        self.assertTrue(calls)
        for method, path, timeout in calls:
            self.assertIsInstance(timeout, (int, float), (method, path))
            if path == '/v2/files':
                self.assertEqual(timeout, 60)
            elif path.startswith('/v') and path.split('/')[1][1:].isdigit():
                self.assertEqual(timeout, 30, (method, path))
            else:                                       # перевірка превʼю
                self.assertEqual((path, timeout), ('/', 20))
        self.assertTrue(any(p == '/v2/files' for _, p, _ in calls))

    def test_a_silent_api_ends_in_a_network_error_not_a_hang(self):
        self.api.override('GET', '/v9/projects/', 200, {}, delay=1.5)
        g = self.fn('publish').__globals__
        t0 = time.monotonic()
        with self.patched():
            with self.assertRaises(RuntimeError) as cm:
                g['_req'](self.ctx(), 'GET', '/v9/projects/pv-1', timeout=0.2)
        self.assertLess(time.monotonic() - t0, 1.2)
        self.assertRegex(str(cm.exception), r'^Vercel недоступний \(\w+\)$')      # з імʼям класу збою, без подробиць


# ------------------------------------------------------------------------------------------------ team

class Team(Base):
    def run_all_request_types(self, team):
        self.api.listing = entries(6)
        return self.publish(ctx=self.ctx(team=team))    # перша публікація: перевірка імені, файли, публікація, опитування, список, DELETE

    def test_a_team_id_goes_on_every_request(self):
        self.run_all_request_types('team_abc123')
        def kind(r):
            for pre in ('/v9/projects/', '/v13/deployments/'):
                if r['path'].startswith(pre):
                    return r['method'], pre + '*'
            return r['method'], r['path']
        kinds = {kind(r) for r in self.api.requests}
        self.assertTrue({('GET', '/v9/projects/*'), ('POST', '/v2/files'), ('POST', '/v13/deployments'),
                         ('GET', '/v13/deployments/*'), ('GET', '/v6/deployments'),
                         ('DELETE', '/v13/deployments/*')} <= kinds, kinds)
        for r in self.api.requests:
            self.assertEqual(r['query'].get('teamId'), 'team_abc123', (r['method'], r['path']))
            self.assertNotIn('slug', r['query'])

    def test_a_team_slug_goes_on_every_request(self):
        self.run_all_request_types('acme')
        self.assertGreaterEqual(len(self.api.requests), 8)
        for r in self.api.requests:
            self.assertEqual(r['query'].get('slug'), 'acme', (r['method'], r['path']))
            self.assertNotIn('teamId', r['query'])

    def test_no_team_means_no_team_parameter(self):
        self.api.listing = entries(6)
        self.publish()
        for r in self.api.requests:
            self.assertNotIn('teamId', r['query'])
            self.assertNotIn('slug', r['query'])

    def test_a_blank_team_means_no_team_parameter(self):
        self.publish(ctx=self.ctx(team='   '))
        for r in self.api.requests:
            self.assertNotIn('teamId', r['query'])
            self.assertNotIn('slug', r['query'])

    def test_the_team_value_is_url_encoded(self):
        self.publish(ctx=self.ctx(team='a b&c=d'))
        for r in self.api.requests:
            self.assertEqual(r['query'].get('slug'), 'a b&c=d')
            self.assertNotIn('c', r['query'])


# ---------------------------------------------------------------------------------------- очікування

class Waiting(Base):
    def test_ready_after_several_building_polls(self):
        self.api.states = ['QUEUED', 'INITIALIZING', 'BUILDING', 'BUILDING', 'BUILDING', 'READY']
        res = self.publish()
        self.assertEqual(len(self.api.reqs('GET', '/v13/deployments/')), 6)
        self.assertEqual(res['url'], SITE_URL)

    def test_the_poll_sleeps_between_requests(self):
        self.api.states = ['BUILDING', 'BUILDING', 'READY']
        t0 = time.monotonic()
        self.publish(POLL_S=0.15)
        self.assertGreaterEqual(time.monotonic() - t0, 0.28)               # два проміжки по 0.15

    def test_an_error_state_raises_with_the_vercel_text(self):
        self.api.states = ['BUILDING', 'ERROR']
        e = self.fails()
        self.assertUncoded(e)
        self.assertIn('Build failed: boom', self.msg(e))
        self.assertEqual([r for r in self.api.reqs('GET', '/v6/deployments') if 'target' in r['query']], [])   # без успіху старе не прибирається
        self.assertEqual(self.site.requests, [])

    def test_through_the_core_an_error_state_is_a_module_error_with_the_text(self):
        self.api.states = ['ERROR']
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(core=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('module-error', 502))
        self.assertIn('Build failed: boom', cm.exception.message)

    def test_a_canceled_state_raises_too(self):
        self.api.states = ['CANCELED']
        self.api.error_message = 'Canceled by user'
        e = self.fails()
        self.assertUncoded(e)
        self.assertIn('Canceled by user', self.msg(e))

    def test_an_error_state_without_a_message_still_says_what_happened(self):
        self.api.states = ['ERROR']
        self.api.error_message = None
        e = self.fails()
        self.assertIn('ERROR', self.msg(e))

    def test_a_poll_that_never_finishes_times_out(self):
        self.api.states = ['BUILDING']
        t0 = time.monotonic()
        e = self.fails(POLL_MAX_S=0.1, POLL_S=0.02)
        self.assertUncoded(e)
        self.assertIn('timeout', self.msg(e))
        self.assertLess(time.monotonic() - t0, 3)
        self.assertGreaterEqual(len(self.api.reqs('GET', '/v13/deployments/')), 2)
        self.assertEqual([r for r in self.api.reqs('GET', '/v6/deployments') if 'target' in r['query']], [])
        self.assertEqual(self.site.requests, [])

    def test_a_long_error_text_is_cut(self):
        self.api.states = ['ERROR']
        self.api.error_message = 'x' * 5000
        e = self.fails()
        self.assertLessEqual(len(self.msg(e)), 300)


# --------------------------------------------------------------------------------------------- адреса

class UrlChoice(Base):
    def test_the_shortest_vercel_app_alias_is_the_main_url(self):
        self.api.aliases = ['pv-x-team-abc12.vercel.app', 'a.io', 'pv-x.vercel.app', 'pv-x-git-main-team.vercel.app',
                            'x.vercel.app.evil.io', 'www.example.com']
        res = self.publish()
        self.assertEqual(res['url'], 'https://pv-x.vercel.app')
        self.assertEqual(self.preview_urls, ['https://pv-x.vercel.app'])
        self.assertEqual(res['warnings'], [])

    def test_a_custom_domain_alias_is_not_the_main_url(self):
        self.api.aliases = ['a.io', 'my-preview.example.com', 'long-name-here.vercel.app']
        res = self.publish()
        self.assertEqual(res['url'], 'https://long-name-here.vercel.app')

    def test_lookalike_aliases_are_not_vercel_app(self):
        self.api.aliases = ['evil-vercel.app', 'vercel.app', '.vercel.app', 'ok.vercel.app']
        res = self.publish()
        self.assertEqual(res['url'], 'https://ok.vercel.app')

    def test_malformed_aliases_are_ignored(self):
        self.api.aliases = ['bad host.vercel.app', 'x.vercel.app/path', 'user@x.vercel.app', 'x.vercel.app#frag',
                            'evil\\.vercel.app', 'a..vercel.app', '-a.vercel.app', 'a-.vercel.app', 'ü.vercel.app',
                            'x' * 70 + '.vercel.app', 123, None, 'good.vercel.app']
        res = self.publish()
        self.assertEqual(res['url'], 'https://good.vercel.app')

    def test_without_a_vercel_app_alias_the_deployment_url_is_used_with_a_warning(self):
        self.api.aliases = ['preview.example.com']
        res = self.publish()
        self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')
        self.assertEqual(self.preview_urls, ['https://pv-x-abc123-team.vercel.app'])
        self.assertEqual(len(res['warnings']), 1)
        self.assertIn('захист', res['warnings'][0])

    def test_without_any_alias_the_deployment_url_is_used_with_a_warning(self):
        self.api.aliases = []
        res = self.publish()
        self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')
        self.assertTrue(res['warnings'])

    def test_a_deployment_url_that_already_has_a_scheme_is_normalised(self):
        self.api.aliases = []
        self.api.deployment_url = 'https://pv-x-abc123-team.vercel.app'
        res = self.publish()
        self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')

    def test_no_usable_address_at_all_is_an_error(self):
        self.api.aliases = []
        self.api.deployment_url = 'bad host/../x'
        e = self.fails()
        self.assertUncoded(e)


# ----------------------------------------------------------------------------------------- перевірка

class Verification(Base):
    def assert_protected(self, res):
        self.assertIs(res['verified'], False)
        self.assertEqual(len([w for w in res['warnings'] if 'Deployment Protection' in w]), 1)
        w = next(w for w in res['warnings'] if 'Deployment Protection' in w)
        self.assertIn('Settings', w)
        self.assertLessEqual(len(w), 300)

    def test_a_200_is_verified(self):
        res = self.publish()
        self.assertIs(res['verified'], True)
        self.assertEqual(res['warnings'], [])
        self.assertEqual(len(self.site.requests), 1)
        self.assertEqual(self.site.requests[0]['method'], 'GET')

    def test_a_redirect_to_the_vercel_login_is_not_verified_and_warns_about_protection(self):
        self.site.mode = 'login'
        res = self.publish()
        self.assert_protected(res)
        self.assertEqual(len(self.site.requests), 1)                        # редирект НЕ виконувався
        self.assertEqual(res['url'], SITE_URL)                              # публікація є, адреса віддана

    def test_the_redirect_is_not_followed(self):
        self.site.mode = 'login'
        self.publish()
        self.assertEqual(self.trip.violations, [])                          # перехід на vercel.com мав би потрапити сюди

    def test_a_sso_redirect_and_a_vercel_subdomain_count_as_protection(self):
        for mode in ('sso', 'sub-login'):
            with self.subTest(mode):
                self.site.mode = mode
                self.assert_protected(self.publish())

    def test_401_and_403_mean_protection(self):
        for mode in ('401', '403'):
            with self.subTest(mode):
                self.site.mode = mode
                self.assert_protected(self.publish())

    def test_other_outcomes_are_unverified_without_the_protection_warning(self):
        for mode in ('404', '500', 'same-host', 'lookalike'):
            with self.subTest(mode):
                self.site.mode = mode
                res = self.publish()
                self.assertIs(res['verified'], False)
                self.assertFalse(any('Deployment Protection' in w for w in res['warnings']), res['warnings'])
                self.assertEqual(res['url'], SITE_URL)

    def test_a_dead_site_is_unverified_and_the_publish_still_returns(self):
        self.site.stop()
        res = self.publish()
        self.assertIs(res['verified'], False)
        self.assertEqual(res['url'], SITE_URL)
        self.assertFalse(any('Deployment Protection' in w for w in res['warnings']))

    def test_the_verification_request_carries_no_credentials(self):
        self.publish()
        (rec,) = self.site.requests
        self.assertNotIn('authorization', rec['headers'])
        self.assertNotIn('cookie', rec['headers'])
        self.assertNotIn(TOKEN.encode(), self.blob(rec))
        self.assertEqual(self.preview_urls, [SITE_URL])

    def test_a_preview_that_is_not_there_yet_is_retried(self):
        self.site.script = ['404', '500']
        res = self.publish()
        self.assertIs(res['verified'], True)
        self.assertEqual(res['warnings'], [])
        self.assertEqual(len(self.site.requests), 3)

    def test_it_gives_up_after_two_retries(self):
        self.site.mode = '404'
        res = self.publish()
        self.assertIs(res['verified'], False)
        self.assertEqual(len(self.site.requests), 3)                              # спроба + 2 повтори
        self.assertTrue(res['warnings'])

    def test_no_answer_is_retried_too(self):
        self.site.stop()
        res = self.publish()
        self.assertIs(res['verified'], False)
        self.assertEqual(self.preview_urls, [SITE_URL] * 3)

    def test_the_retries_are_spaced(self):
        self.site.mode = '500'
        t0 = time.monotonic()
        self.publish(VERIFY_RETRY_S=0.1)
        self.assertGreaterEqual(time.monotonic() - t0, 0.19)

    def test_protection_and_redirects_are_not_retried(self):
        for mode in ('login', '401', '403', 'sso', 'same-host', 'lookalike'):
            with self.subTest(mode):
                self.site.requests.clear()
                self.site.mode = mode
                self.publish()
                self.assertEqual(len(self.site.requests), 1)

    def test_the_verification_helper_refuses_non_http_schemes(self):
        g = self.fn('publish').__globals__
        self.assertEqual(g['_fetch_preview']('file:///etc/passwd'), (None, ''))
        self.assertEqual(g['_fetch_preview']('ftp://127.0.0.1/x'), (None, ''))


# ---------------------------------------------------------------------------------------------- помилки

class Errors(Base):
    STEPS = (('GET', '/v9/projects/'), ('POST', '/v2/files'), ('POST', '/v13/deployments'),
             ('GET', '/v13/deployments/'))

    def test_401_and_403_at_any_step_is_vercel_auth(self):
        for method, prefix in self.STEPS:
            for status in (401, 403):
                with self.subTest(step=f'{method} {prefix}', status=status):
                    self.api.overrides = []
                    self.api.override(method, prefix, status, {'error': {'code': 'forbidden', 'message': 'Not authorized'}})
                    with self.assertRaises(dm.ModuleError) as cm:
                        self.publish(core=True)
                    self.assertEqual((cm.exception.code, cm.exception.status), ('vercel-auth', 409))
                    self.assertIn('Not authorized', cm.exception.message)

    def test_vercel_auth_also_on_the_state_path(self):
        self.api.override('POST', '/v2/files', 401, {'error': {'message': 'Not authorized'}})
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(state=STATE, core=True)
        self.assertEqual(cm.exception.code, 'vercel-auth')

    def test_a_wrong_token_is_vercel_auth(self):
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(ctx=self.ctx(token='vcp_some-other-token'), core=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('vercel-auth', 409))
        self.assertEqual(self.api.reqs('POST'), [])

    def test_429_at_any_step_is_vercel_busy(self):
        for method, prefix in self.STEPS:
            with self.subTest(step=f'{method} {prefix}'):
                self.api.overrides = []
                self.api.override(method, prefix, 429, {'error': {'code': 'rate_limited', 'message': 'Too many requests'}})
                with self.assertRaises(dm.ModuleError) as cm:
                    self.publish(core=True)
                self.assertEqual((cm.exception.code, cm.exception.status), ('vercel-busy', 409))
                self.assertIn('Too many requests', cm.exception.message)

    def test_a_429_without_a_body_still_says_busy(self):
        self.api.override('POST', '/v13/deployments', 429, None)
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(core=True)
        self.assertEqual(cm.exception.code, 'vercel-busy')
        self.assertTrue(cm.exception.message)

    def test_other_http_errors_are_module_errors_with_the_vercel_text(self):
        self.api.override('POST', '/v13/deployments', 500, {'error': {'code': 'internal', 'message': 'Boom happened'}})
        e = self.fails()
        self.assertUncoded(e)
        self.assertIn('Boom happened', self.msg(e))
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(core=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('module-error', 502))

    def test_a_long_vercel_message_is_cut_to_200(self):
        self.api.override('POST', '/v13/deployments', 400, {'error': {'message': 'm' * 3000}})
        e = self.fails()
        self.assertLessEqual(len(self.msg(e)), 200)

    def test_a_string_error_body_is_used_as_the_text(self):
        self.api.override('POST', '/v13/deployments', 400, {'error': 'Plain string error'})
        self.assertIn('Plain string error', self.msg(self.fails()))
        self.api.overrides = []
        self.api.override('POST', '/v13/deployments', 400, {'message': 'Top level message'})
        self.assertIn('Top level message', self.msg(self.fails()))

    def test_an_http_error_without_a_readable_body_names_the_status(self):
        self.api.override('POST', '/v13/deployments', 502, 'Bad gateway <html>')
        e = self.fails()
        self.assertUncoded(e)
        self.assertIn('502', self.msg(e))

    def test_a_non_json_success_is_an_error(self):
        self.api.override('POST', '/v13/deployments', 200, 'not json at all')
        self.assertUncoded(self.fails())

    def test_a_deployment_without_an_id_is_an_error(self):
        self.api.override('POST', '/v13/deployments', 200, {'url': 'x.vercel.app'})
        self.assertUncoded(self.fails())

    def test_the_network_being_down_is_a_module_error(self):
        self.api.stop()
        e = self.fails()
        self.assertUncoded(e)
        self.assertRegex(self.msg(e), r'^Vercel недоступний \(\w+\)$')
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(core=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('module-error', 502))
        self.assertIn('Vercel недоступний', cm.exception.message)

    def test_no_redirect_from_the_api_is_followed_for_any_request_type(self):
        """`urllib` сам НЕ йде за 307/308 на POST, але йде за 301/302/303 на GET (і POST → GET): заголовок Authorization
        поїхав би на чужий хост. Тому — КОЖЕН тип запиту й усі коди редиректу, а «чужий хост» — справжній сервер, що
        записує все, що до нього дійшло."""
        steps = [('GET', '/v9/projects/', None), ('POST', '/v2/files', None), ('POST', '/v13/deployments', None),
                 ('GET', '/v13/deployments/', None), ('GET', '/v6/deployments', STATE),
                 ('DELETE', '/v13/deployments/', STATE)]
        for method, prefix, state in steps:
            for status in (301, 302, 303, 307, 308):
                with self.subTest(step=f'{method} {prefix}', status=status):
                    self.api.overrides = []
                    self.api.requests.clear()
                    self.api.listing = entries(6)
                    self.api.override(method, prefix, status, None, {'Location': self.evil.base + '/steal'})
                    try:
                        self.publish(state=state)
                    except Exception:  # noqa: BLE001 — тут важить лише, чи дійшло що-небудь до чужого хоста
                        pass
                    self.assertEqual(self.evil.requests, [])

    def test_a_redirect_from_the_api_is_an_error_not_a_success(self):
        self.api.override('POST', '/v13/deployments', 307, None, {'Location': self.evil.base + '/steal'})
        e = self.fails()
        self.assertUncoded(e)
        self.assertIn('307', self.msg(e))

    def test_check_does_not_follow_redirects_either(self):
        for team, prefix in ((None, '/v2/user'), ('acme', '/v6/deployments')):
            for status in (301, 302, 303, 307, 308):
                with self.subTest(prefix=prefix, status=status):
                    self.api.overrides = []
                    self.api.override('GET', prefix, status, None, {'Location': self.evil.base + '/steal'})
                    res = self.check(self.ctx(team=team))
                    self.assertEqual((res['ok'], res['error']), (False, 'vercel-error'))
                    self.assertEqual(self.evil.requests, [])

    def test_a_plain_403_says_access_denied_not_a_rejected_token(self):
        self.api.override('POST', '/v2/files', 403, {'error': {'code': 'forbidden', 'message': 'Plan limit reached'}})
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(core=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('vercel-auth', 409))
        self.assertIn('Vercel відмовив у доступі (HTTP 403)', cm.exception.message)
        self.assertIn('Plan limit reached', cm.exception.message)
        self.assertNotIn('не прийняв токен', cm.exception.message)
        self.api.overrides = []
        self.api.override('POST', '/v2/files', 403, None)
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(core=True)
        self.assertIn('Vercel відмовив у доступі (HTTP 403)', cm.exception.message)

    def test_a_401_and_a_403_with_invalid_token_say_the_token_was_not_accepted(self):
        for status, body in ((401, {'error': {'message': 'Nope'}}), (401, None),
                             (403, {'error': {'message': 'Nope', 'invalidToken': True}})):
            with self.subTest(status=status, body=body):
                self.api.overrides = []
                self.api.override('POST', '/v2/files', status, body)
                with self.assertRaises(dm.ModuleError) as cm:
                    self.publish(core=True)
                self.assertEqual(cm.exception.code, 'vercel-auth')
                self.assertIn('Vercel не прийняв токен', cm.exception.message)

    def test_a_bad_token_answered_with_403_and_invalid_token_is_a_rejected_token(self):
        self.api.bad_token_status = 403
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(ctx=self.ctx(token='vcp_wrong'), core=True)
        self.assertEqual(cm.exception.code, 'vercel-auth')
        self.assertIn('Vercel не прийняв токен', cm.exception.message)
        res = self.check(self.ctx(token='vcp_wrong'))
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-auth'))
        self.assertIn('токен', res['detail'])

    def test_an_invalid_token_is_refused_before_any_request(self):
        for token in ('', '   ', 'bad token', 'tok\nen', 'tök', 'a' * 5 + '\r\nX-Evil: 1'):
            with self.subTest(token=token):
                ctx = self.ctx()
                ctx['secrets'] = {'token': token}
                e = self.fails(ctx=ctx)
                self.assertEqual(getattr(e, 'code', None), 'vercel-auth')
                self.assertEqual(self.api.requests, [])
                for text in self.exc_texts(e):
                    self.assertNotIn(token.strip() or '\0', text)

    def test_a_missing_secrets_dict_is_vercel_auth_not_a_crash(self):
        for secrets in (None, {}, {'token': None}, {'token': 5}):
            with self.subTest(secrets=secrets):
                ctx = self.ctx()
                ctx['secrets'] = secrets
                self.assertEqual(getattr(self.fails(ctx=ctx), 'code', None), 'vercel-auth')
        self.assertEqual(self.api.requests, [])

    def test_without_a_core_error_class_the_module_still_raises_with_the_code(self):
        ctx = self.ctx()
        del ctx['ModuleError']
        self.api.override('POST', '/v13/deployments', 401, {'error': {'message': 'Not authorized'}})
        e = self.fails(ctx=ctx)
        self.assertIsInstance(e, RuntimeError)
        self.assertEqual(getattr(e, 'code', None), 'vercel-auth')
        self.assertIn('vercel-auth', str(e))

    def test_without_a_core_error_class_a_plain_failure_stays_a_runtime_error(self):
        ctx = self.ctx()
        del ctx['ModuleError']
        self.api.override('POST', '/v13/deployments', 500, {'error': {'message': 'Boom happened'}})
        e = self.fails(ctx=ctx)
        self.assertIsInstance(e, RuntimeError)
        self.assertIsNone(getattr(e, 'code', None))
        self.assertIn('Boom happened', str(e))

    def test_every_plain_failure_reaches_the_core_as_a_module_error_without_a_class_prefix(self):
        """Звичайний виняток ядро показує як `<Клас>: <текст>`, а цей текст людина бачить у діалозі: модуль кидає
        `ModuleError('module-error')` сам, з чистим текстом (кожна родина збоїв: HTTP, мережа, відповідь, очікування,
        збірка)."""
        big = {f'f{i}.txt': str(i) for i in range(4)}
        cases = {
            '5xx on the deployment': (lambda: self.api.override('POST', '/v13/deployments', 500, {'error': {'message': 'Boom'}}), {}, None),
            '4xx on a probe': (lambda: self.api.override('GET', '/v9/projects/', 400, {'error': {'message': 'Bad'}}), {}, None),
            'a redirect': (lambda: self.api.override('POST', '/v13/deployments', 307, None, {'Location': self.evil.base}), {}, None),
            'not json': (lambda: self.api.override('POST', '/v13/deployments', 200, 'not json'), {}, None),
            'a JSON array': (lambda: self.api.override('POST', '/v13/deployments', 200, [1]), {}, None),
            'no deployment id': (lambda: self.api.override('POST', '/v13/deployments', 200, {'url': 'x.vercel.app'}), {}, None),
            'an error state': (lambda: setattr(self.api, 'states', ['ERROR']), {}, None),
            'blocked': (lambda: setattr(self.api, 'states', ['BLOCKED']), {}, None),
            'deleted': (lambda: setattr(self.api, 'states', ['DELETED']), {}, None),
            'polling timeout': (lambda: setattr(self.api, 'states', ['BUILDING']), {'POLL_MAX_S': 0.05, 'POLL_S': 0.01}, None),
            'a poll that is refused (404)': (lambda: self.api.override('GET', '/v13/deployments/', 404, {'error': {'message': 'x'}}), {}, None),
            'too many files': (lambda: None, {'MAX_FILES': 3}, big),
            'a file over the limit': (lambda: None, {'MAX_FILE_BYTES': 0}, {'index.html': 'x'}),
            'an empty build': (lambda: None, {}, {}),
            'the upload deadline': (lambda: self.api.override('POST', '/v2/files', 200, {}, delay=0.06), {'UPLOAD_TOTAL_S': 0.05}, big),
            'the network is down': (lambda: self.api.stop(), {}, None),
        }
        for name, (setup, extra, build) in cases.items():
            with self.subTest(name):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['QUEUED', 'READY']
                if build is not None:
                    self.make_build(build)
                setup()
                with self.assertRaises(dm.ModuleError) as cm:
                    self.publish(core=True, **extra)
                e = cm.exception
                self.assertEqual((e.code, e.status), ('module-error', 502))
                self.assertTrue(e.message.strip())
                self.assertNotRegex(e.message, r'^_?\w*(?:Error|Exception)\b')
                for cls_name in ('RuntimeError', '_HttpError', '_NetworkError', 'ModuleError', 'Traceback'):
                    self.assertNotIn(cls_name, e.message)
                if name == 'the network is down':
                    break                                                         # сервера більше нема

    def test_a_failure_the_module_does_not_know_keeps_its_class_name_for_the_bug_report(self):
        """Не `RuntimeError`-родина (помилка в самому модулі) модуль не маскує: ядро покаже `<Клас>: <текст>`."""
        g = self.fn('publish').__globals__
        with mock.patch.dict(g, {'_scan': mock.Mock(side_effect=KeyError('x'))}):
            with self.assertRaises(dm.ModuleError) as cm:
                self.publish(core=True)
        self.assertTrue(cm.exception.message.startswith('KeyError'), cm.exception.message)


# ------------------------------------------------------------------------------------------- токен

class TokenSecrecy(Base):
    def test_the_token_is_only_in_the_authorization_header_to_the_api(self):
        self.api.listing = entries(6)
        self.api.delete_fail = {'o4'}
        self.site.mode = 'login'
        self.publish(ctx=self.ctx(team='team_abc'))
        self.assertGreater(len(self.api.requests), 8)
        for rec in self.api.requests:
            self.assertEqual(rec['headers'].get('authorization'), 'Bearer ' + TOKEN)
            blob = self.blob(rec, skip_auth=True)
            self.assertNotIn(TOKEN.encode(), blob, (rec['method'], rec['path']))
            self.assertNotIn(PASSWORD.encode(), blob)                      # пароль превʼю — справа ядра, не модуля
        for rec in self.site.requests + self.evil.requests:
            self.assertNotIn('authorization', rec['headers'])
            self.assertNotIn(TOKEN.encode(), self.blob(rec))
            self.assertNotIn(PASSWORD.encode(), self.blob(rec))

    def test_the_token_is_in_no_exception_text(self):
        echo = {'error': {'code': 'x', 'message': f'bad credentials Bearer {TOKEN} and {TOKEN}'}}
        scenarios = {
            '401 echo': lambda: self.api.override('GET', '/v9/projects/', 401, echo),
            '403 echo': lambda: self.api.override('POST', '/v2/files', 403, echo),
            '429 echo': lambda: self.api.override('POST', '/v13/deployments', 429, echo),
            '500 echo': lambda: self.api.override('POST', '/v13/deployments', 500, echo),
            '400 raw echo': lambda: self.api.override('POST', '/v13/deployments', 400, f'oops {TOKEN}'),
            '200 not json': lambda: self.api.override('POST', '/v13/deployments', 200, f'oops {TOKEN}'),
            'redirect': lambda: self.api.override('POST', '/v13/deployments', 307, None,
                                                  {'Location': self.evil.base + '/?t=' + TOKEN}),
            'error state': lambda: (setattr(self.api, 'states', ['ERROR']),
                                    setattr(self.api, 'error_message', f'build saw {TOKEN}')),
            'timeout': lambda: setattr(self.api, 'states', ['BUILDING']),
            'network down': lambda: self.api.stop(),                     # останнім: далі сервера нема
        }
        for name, setup in scenarios.items():
            with self.subTest(name):
                self.api.overrides = []
                self.api.states = ['QUEUED', 'READY']
                self.api.error_message = 'Build failed: boom'
                setup()
                extra = {'POLL_MAX_S': 0.05, 'POLL_S': 0.01} if name == 'timeout' else {}
                e = self.fails(**extra)
                for text in self.exc_texts(e):
                    self.assertNotIn(TOKEN, text)
                    self.assertNotIn(TOKEN[:12], text)
                # і через ядро (де секрети вирізає ще й `_run`): код — той самий, текст чистий
                try:
                    self.publish(core=True, **extra)
                except dm.ModuleError as ce:
                    self.assertNotIn(TOKEN, ce.message)
                except Exception:   # noqa: BLE001 — не-ModuleError з `core=True` недопустимий
                    self.fail('call() віддає лише ModuleError')

    def test_check_results_never_contain_the_token(self):
        echo = {'error': {'message': f'nope {TOKEN}'}}
        for status in (401, 403, 429, 500):
            with self.subTest(status):
                self.api.overrides = []
                self.api.override('GET', '/v2/user', status, echo)
                self.assertNotIn(TOKEN, json.dumps(self.check()))

    def test_warnings_never_contain_the_token(self):
        self.api.states = ['READY']
        self.api.aliases = []
        self.api.listing = entries(6)
        self.api.delete_fail = {'o3'}
        self.site.mode = '401'
        res = self.publish(state=STATE)
        self.assertTrue(res['warnings'])
        self.assertNotIn(TOKEN, json.dumps(res))


# ---------------------------------------------------------------------------------------- прибирання

class Cleanup(Base):
    def deleted(self):
        return sorted(r['path'].rsplit('/', 1)[1] for r in self.api.reqs('DELETE'))

    def test_six_deployments_keep_the_newest_three_including_the_current(self):
        self.api.listing = entries(6)                   # dpl_cur + o1…o5, у перемішаному порядку
        res = self.publish(state=STATE)
        self.assertEqual(self.deleted(), ['o3', 'o4', 'o5'])
        (lst,) = self.api.reqs('GET', '/v6/deployments')
        self.assertEqual(lst['query'], {'projectId': 'prj_mine', 'target': 'production', 'limit': '20'})
        for r in self.api.reqs('DELETE'):
            self.assertTrue(r['path'].startswith('/v13/deployments/'))
        self.assertEqual(res['warnings'], [])
        # DELETE — після успішної публікації й перевірки
        order = [(r['method'], r['path']) for r in self.api.requests]
        self.assertLess(order.index(('GET', '/v13/deployments/dpl_cur')), order.index(('GET', '/v6/deployments')))

    def test_three_or_fewer_deployments_delete_nothing(self):
        for n in (1, 2, 3):
            with self.subTest(n=n):
                self.api.requests.clear()
                self.api.listing = entries(n)
                self.publish(state=STATE)
                self.assertEqual(self.deleted(), [])

    def test_the_current_deployment_always_stays_even_if_the_list_misdates_it(self):
        lst = entries(6)
        for e in lst:
            if e['uid'] == 'dpl_cur':
                e['created'] = 1                         # годинник «поїхав»: поточна виглядає найстарішою
        self.api.listing = lst
        self.publish(state=STATE)
        self.assertNotIn('dpl_cur', self.deleted())
        self.assertEqual(len(self.deleted()), 3)         # 5 інших у списку − 2 найновіші

    def test_a_current_deployment_missing_from_the_list_still_keeps_three_in_total(self):
        self.api.listing = [e for e in entries(6) if e['uid'] != 'dpl_cur']      # o1…o5
        self.publish(state=STATE)
        self.assertEqual(self.deleted(), ['o3', 'o4', 'o5'])

    def test_a_foreign_project_id_deletes_nothing(self):
        self.api.dep_project_id = 'prj_foreign'          # публікація прийшла в ІНШИЙ проєкт, ніж записано в стані
        self.api.listing = entries(6, pid='prj_foreign')
        res = self.publish(state=STATE)
        self.assertEqual(self.api.reqs('DELETE'), [])
        self.assertEqual(res['state']['project_id'], 'prj_mine')            # чужий id не «усиновлюємо»
        self.assertTrue(any('прибира' in w for w in res['warnings']))

    def test_entries_of_another_project_in_the_list_are_never_deleted(self):
        lst = entries(6)
        lst += [{'uid': 'x1', 'created': 1, 'projectId': 'prj_other'}, {'uid': 'x2', 'created': 2, 'projectId': 'prj_other'}]
        self.api.listing = lst
        self.publish(state=STATE)
        self.assertEqual(self.deleted(), ['o3', 'o4', 'o5'])

    def test_entries_without_a_project_id_need_a_matching_name(self):
        """Позитивне розпізнавання: `projectId` збігається, АБО його нема й `name` — наш проєкт. Інакше — не чіпаємо
        (якщо Vercel проігнорував фільтр, у списку можуть бути чужі публікації без `projectId`)."""
        lst = entries(6)
        names = {'o1': 'pv-12345678', 'o2': 'pv-12345678', 'o3': 'someone-elses-site', 'o4': 'someone-elses-site',
                 'o5': 'pv-12345678'}
        for e in lst:
            if e['uid'] != 'dpl_cur':
                e.pop('projectId')
                e['name'] = names[e['uid']]
        lst += [{'uid': 'o6', 'created': 1}, {'uid': 'o7', 'created': 2, 'name': None},
                {'uid': 'o8', 'created': 3, 'projectId': None, 'name': 'someone-elses-site'}]
        self.api.listing = lst
        self.publish(state=STATE)
        self.assertEqual(self.deleted(), ['o5'])                                  # лише впізнані: o1, o2 лишились, o5 — на видалення

    def test_an_entry_with_a_foreign_project_id_is_skipped_even_if_its_name_matches(self):
        lst = entries(6)
        lst += [{'uid': 'x1', 'created': 1, 'projectId': 'prj_other', 'name': 'pv-12345678'}]
        self.api.listing = lst
        self.publish(state=STATE)
        self.assertEqual(self.deleted(), ['o3', 'o4', 'o5'])

    def test_a_slow_cleanup_is_cut_with_a_warning(self):
        self.api.listing = entries(8)                                             # 5 на видалення
        self.api.override('DELETE', '/v13/deployments/', 200, {}, delay=0.06)
        res = self.publish(state=STATE, CLEANUP_MAX_S=0.1)
        n = len(self.api.reqs('DELETE'))
        self.assertTrue(1 <= n < 5, n)
        self.assertTrue(any('часом' in w for w in res['warnings']), res['warnings'])
        self.assertEqual(res['url'], SITE_URL)

    def test_entries_without_a_usable_created_or_uid_are_left_alone(self):
        lst = entries(5)
        lst += [{'uid': 'nodate', 'projectId': 'prj_mine'}, {'uid': 'bad', 'created': 'yesterday', 'projectId': 'prj_mine'},
                {'created': 5, 'projectId': 'prj_mine'}, 'junk', None, {'uid': 'bool', 'created': True, 'projectId': 'prj_mine'},
                {'uid': 'nan', 'created': float('nan'), 'projectId': 'prj_mine'},
                {'uid': 'inf', 'created': float('inf'), 'projectId': 'prj_mine'}]
        self.api.listing = lst
        self.publish(state=STATE)
        self.assertEqual(self.deleted(), ['o3', 'o4'])

    def test_a_project_created_by_this_call_is_cleaned_too(self):
        self.api.listing = entries(6)
        res = self.publish()                             # стану нема → проєкт створив САМЕ цей виклик
        self.assertEqual(self.deleted(), ['o3', 'o4', 'o5'])
        self.assertEqual(res['state']['project_id'], 'prj_mine')

    def test_a_failing_delete_is_a_warning_not_an_error(self):
        self.api.listing = entries(6)
        self.api.delete_fail = {'o4'}
        res = self.publish(state=STATE)
        self.assertEqual(self.deleted(), ['o3', 'o4', 'o5'])                # решту все одно пробуємо
        self.assertEqual(len(res['warnings']), 1)
        self.assertIn('1', res['warnings'][0])
        self.assertEqual(res['url'], SITE_URL)
        self.assertEqual(res['state']['deployment'], 'dpl_cur')

    def test_a_failing_listing_is_a_warning(self):
        for status in (500, 401, 403, 429):
            with self.subTest(status):
                self.api.overrides = []
                self.api.override('GET', '/v6/deployments', status, {'error': {'message': 'nope'}})
                res = self.publish(state=STATE)
                self.assertEqual(self.api.reqs('DELETE'), [])
                self.assertEqual(len(res['warnings']), 1)
                self.assertEqual(res['url'], SITE_URL)

    def test_a_listing_with_a_wrong_shape_is_a_warning(self):
        self.api.override('GET', '/v6/deployments', 200, {'deployments': 'nope'})
        res = self.publish(state=STATE)
        self.assertEqual(self.api.reqs('DELETE'), [])
        self.assertTrue(res['warnings'])

    def test_an_auth_failure_while_deleting_stops_the_deleting(self):
        self.api.listing = entries(8)
        self.api.override('DELETE', '/v13/deployments/', 401, {'error': {'message': 'Not authorized'}})
        res = self.publish(state=STATE)
        self.assertEqual(len(self.api.reqs('DELETE')), 1)
        self.assertTrue(res['warnings'])
        self.assertEqual(res['url'], SITE_URL)

    def test_the_uid_is_quoted_in_the_delete_path(self):
        lst = entries(5)
        lst.append({'uid': 'a/../b c', 'created': 1, 'projectId': 'prj_mine'})
        self.api.listing = lst
        self.publish(state=STATE)
        paths = [r['raw_path'].split('?')[0] for r in self.api.reqs('DELETE')]
        self.assertIn('/v13/deployments/a%2F..%2Fb%20c', paths)


# ------------------------------------------------------------------------------------- імʼя й стан

class Naming(Base):
    def test_the_first_publish_probes_a_new_opaque_name(self):
        res = self.publish()
        probes = self.api.reqs('GET', '/v9/projects')
        self.assertEqual(len(probes), 1)
        self.assertRegex(probes[0]['path'], r'^/v9/projects/pv-\d{8}$')
        self.assertEqual(res['state']['project'], probes[0]['path'].rsplit('/', 1)[1])
        order = [(r['method'], r['path']) for r in self.api.requests]
        self.assertEqual(order[0][1], probes[0]['path'])                    # перевірка — ДО першого завантаження

    def test_a_taken_name_makes_the_module_pick_another(self):
        self.api.taken = 1
        with mock.patch('secrets.randbelow', side_effect=[1, 2]):
            res = self.publish()
        self.assertEqual([r['path'] for r in self.api.reqs('GET', '/v9/projects')],
                         ['/v9/projects/pv-00000001', '/v9/projects/pv-00000002'])
        self.assertEqual(res['state']['project'], 'pv-00000002')
        (body,) = self.api.bodies('/v13/deployments')
        self.assertEqual((body['name'], body['project']), ('pv-00000002',) * 2)

    def test_three_taken_names_is_an_error_before_any_upload(self):
        self.api.taken = 99
        e = self.fails()
        self.assertUncoded(e)
        self.assertEqual(len(self.api.reqs('GET', '/v9/projects')), 3)
        self.assertEqual(self.api.reqs('POST'), [])

    def test_the_state_project_is_looked_up_by_id_before_any_upload(self):
        res = self.publish(state=STATE)
        order = [(r['method'], r['path']) for r in self.api.requests]
        self.assertEqual(order[0], ('GET', '/v9/projects/prj_mine'))               # за id, а не за імʼям
        self.assertEqual(len(self.api.reqs('GET', '/v9/projects')), 1)
        self.assertLess(order.index(('GET', '/v9/projects/prj_mine')), order.index(('POST', '/v2/files')))
        (body,) = self.api.bodies('/v13/deployments')
        self.assertEqual((body['name'], body['project']), ('pv-12345678',) * 2)
        self.assertEqual(res['state'], {'project': 'pv-12345678', 'project_id': 'prj_mine', 'deployment': 'dpl_cur',
                                        'task': 't1'})
        self.assertEqual(res['warnings'], [])

    def test_a_state_that_is_not_ours_is_ignored(self):
        """`iterations.json` можна склонувати чи поділити: стан із чужою назвою (чи з іншої задачі) не має привести
        публікацію в чужий проєкт. Кожен випадок має `task` задачі, щоб він сам не маскував решту дефектів."""
        victim = 'victim-prod-site'

        def st(**kw):
            base = {'project': 'pv-12345678', 'project_id': 'prj_mine', 'deployment': 'dpl_old', 'task': 't1'}
            base.update(kw)
            return {k: v for k, v in base.items() if v is not ...}
        bad_states = [
            st(project=victim, project_id='prj_victim'),                            # чужа назва
            st(project='PV-12345678'), st(project='pv-1234567'), st(project='pv-123456789'),
            st(project='pv-12345678 '), st(project='pv-12345678\n'),
            st(project='pv-\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668'),   # арабські цифри
            st(project_id=...),                                                     # без project_id
            st(project_id=''), st(project_id=5), st(project=5), st(project=''),
            st(project=...),
            st(task=...), st(task=''), st(task='other-task'), st(task=5),           # без задачі чи інша задача
            'nonsense', None, []]
        for bad in bad_states:
            with self.subTest(bad=bad):
                self.api.requests.clear()
                self.api.projects[victim] = 'prj_victim'
                self.api.listing = entries(6, pid='prj_victim', name=victim)       # старі продакшн-публікації жертви
                res = self.publish(state=bad)
                probes = self.api.reqs('GET', '/v9/projects')
                self.assertEqual(len(probes), 1)                                    # лише перевірка НОВОГО імені
                new = probes[0]['path'].rsplit('/', 1)[1]
                self.assertRegex(new, r'^pv-\d{8}$')
                (body,) = self.api.bodies('/v13/deployments')
                self.assertEqual((body['name'], body['project']), (new, new))
                self.assertRegex(res['state']['project'], r'^pv-\d{8}$')
                self.assertEqual(self.api.reqs('DELETE'), [])
                for r in self.api.requests:
                    self.assertNotIn(victim.encode(), self.blob(r))
                    self.assertNotIn(b'prj_victim', self.blob(r))
                self.assertNotIn('/v9/projects/prj_mine', [r['path'] for r in self.api.requests])   # за id зі стану теж не ходили

    def test_the_state_carries_the_task_id_and_binds_to_it(self):
        first = self.publish(tid='t7')
        self.assertEqual(first['state']['task'], 't7')
        self.api.requests.clear()
        second = self.publish(state=first['state'], tid='t7')                       # та сама задача — той самий проєкт
        self.assertEqual(second['state']['project'], first['state']['project'])
        self.assertEqual([r['path'] for r in self.api.reqs('GET', '/v9/projects')], ['/v9/projects/prj_mine'])
        self.api.requests.clear()
        third = self.publish(state=first['state'], tid='t8')                        # скопійований стан ІНШОЇ задачі
        self.assertNotEqual(third['state']['project'], first['state']['project'])
        self.assertEqual(third['state']['task'], 't8')
        probes = [r['path'] for r in self.api.reqs('GET', '/v9/projects')]
        self.assertEqual(len(probes), 1)                                            # лише нове імʼя, у старий проєкт не ходили
        self.assertNotIn('/v9/projects/prj_mine', probes)

    def test_a_task_without_an_id_never_matches_a_state(self):
        ctx = self.ctx()
        with self.patched():
            res = self.fn('publish')(ctx, self.build, {'title': 'T', 'dir': self.hp('t'), 'state': dict(STATE, task='')})
        self.assertNotEqual(res['state']['project'], 'pv-12345678')
        self.assertEqual(res['state']['task'], '')

    def test_a_forged_state_never_deploys_to_or_deletes_in_a_foreign_project(self):
        victim = 'victim-prod-site'
        self.api.projects[victim] = 'prj_victim'
        self.api.listing = entries(6, pid='prj_victim', name=victim)
        first = self.publish(state={'project': victim, 'project_id': 'prj_victim', 'task': 't1'})
        second = self.publish(state=first['state'])                                  # наступна публікація — уже зі своїм станом
        self.assertEqual(self.api.reqs('DELETE'), [])
        for body in self.api.bodies('/v13/deployments'):
            self.assertRegex(body['name'], r'^pv-\d{8}$')
        self.assertEqual(second['state']['project'], first['state']['project'])

    def test_a_state_project_deleted_in_the_dashboard_is_recreated_under_the_same_name(self):
        self.api.projects.clear()                                                    # id такого проєкту нема, імʼя вільне
        self.api.project_id = 'prj_new'
        self.api.listing = entries(6, pid='prj_new')
        res = self.publish(state=STATE)
        self.assertEqual([r['path'] for r in self.api.reqs('GET', '/v9/projects')],
                         ['/v9/projects/prj_mine', '/v9/projects/pv-12345678'])      # спершу за id, потім — чи вільне імʼя
        (body,) = self.api.bodies('/v13/deployments')
        self.assertEqual((body['name'], body['project']), ('pv-12345678',) * 2)
        self.assertEqual(res['state'], {'project': 'pv-12345678', 'project_id': 'prj_new', 'deployment': 'dpl_cur',
                                        'task': 't1'})
        self.assertEqual(sorted(r['path'].rsplit('/', 1)[1] for r in self.api.reqs('DELETE')), ['o3', 'o4', 'o5'])

    def test_a_deleted_state_project_whose_name_is_now_taken_gets_a_new_project(self):
        """id зі стану вже нема, але під записаним імʼям у акаунті тепер ІНШИЙ проєкт (клон, інша задача): деплой туди
        перетворив би його на «створений цим викликом» і, може, зніс би."""
        self.api.projects.clear()
        self.api.projects['pv-12345678'] = 'prj_someone_else'
        self.api.listing = entries(6, pid='prj_someone_else')
        res = self.publish(state=STATE)
        probes = [r['path'] for r in self.api.reqs('GET', '/v9/projects')]
        self.assertEqual(probes[:2], ['/v9/projects/prj_mine', '/v9/projects/pv-12345678'])
        self.assertEqual(len(probes), 3)
        self.assertRegex(probes[2], r'^/v9/projects/pv-\d{8}$')
        order = [(r['method'], r['path']) for r in self.api.requests]
        self.assertLess(order.index(('GET', probes[1])), order.index(('POST', '/v2/files')))
        (body,) = self.api.bodies('/v13/deployments')
        self.assertEqual((body['name'], body['project']), (probes[2].rsplit('/', 1)[1],) * 2)
        self.assertEqual(self.api.reqs('DELETE'), [])
        self.assertTrue(any('новий проєкт' in w for w in res['warnings']), res['warnings'])
        self.assertEqual(res['state']['project'], probes[2].rsplit('/', 1)[1])

    def test_a_lookup_that_returns_another_id_is_not_trusted(self):
        self.api.override('GET', '/v9/projects/prj_mine', 200, {'id': 'prj_other', 'name': 'pv-12345678'})
        res = self.publish(state=STATE)
        (body,) = self.api.bodies('/v13/deployments')
        self.assertRegex(body['name'], r'^pv-\d{8}$')
        self.assertNotEqual(body['name'], 'pv-12345678')
        self.assertTrue(any('новий проєкт' in w for w in res['warnings']))

    def test_a_project_under_another_name_than_the_state_is_foreign_whatever_the_reason(self):
        """Перейменування НЕ підтримується: `project_id` зі стану збігається, а `name` — ні (перейменували в панелі чи
        `project_id` підроблено на чужий проєкт) — це «не наш»: нового проєкту `pv-…` і попередження, у той — жодного
        `POST` і жодного `DELETE`, а доказу «остання публікація належить проєкту» модуль більше не шукає."""
        for other in ('my-pretty-name', 'acme-production-site', 'pv-87654321', 'PV-12345678', 'pv-12345678-x'):
            with self.subTest(other):
                self.api.requests.clear()
                self.api.projects.clear()
                self.api.projects[other] = 'prj_mine'                            # id збігається, імʼя — ІНШЕ
                self.api.known_deployments['dpl_old'] = 'prj_mine'
                self.api.project_id = 'prj_new'                                  # новий проєкт отримає СВІЙ id
                self.api.listing = entries(6, pid='prj_mine', name=other)
                res = self.publish(state=STATE)
                (body,) = self.api.bodies('/v13/deployments')
                self.assertRegex(body['name'], r'^pv-\d{8}$')
                self.assertNotIn(body['name'], (other, 'pv-12345678'))           # ні в той проєкт, ні під записаним імʼям
                self.assertEqual(body['name'], body['project'])
                self.assertTrue(any('новий проєкт' in w and 'не збігається' in w for w in res['warnings']), res['warnings'])
                self.assertEqual(self.api.reqs('DELETE'), [])                    # старі публікації «того» проєкту не чіпали
                for r in self.api.reqs('GET', '/v6/deployments'):                # старі публікації «того» проєкту навіть не читали
                    self.assertEqual(r['query']['projectId'], 'prj_new')
                self.assertEqual(self.api.reqs('GET', '/v13/deployments/dpl_old'), [])   # доказу перейменування нема
                self.assertEqual(res['state'], {'project': body['name'], 'project_id': 'prj_new',
                                                'deployment': 'dpl_cur', 'task': 't1'})
                self.assertNotIn(other.encode(), b''.join(self.blob(r) for r in self.api.reqs('POST')))

    def test_a_forged_state_with_a_victim_project_id_and_a_victim_deployment_changes_nothing_there(self):
        """Відтворення зауваження ревʼю: склонований чи підроблений `iterations.json` із
        `{project: pv-…, project_id: <id чужого проєкту>, deployment: <публікація чужого проєкту>, task: <ця задача>}`.
        Раніше реальне імʼя відрізнялось → «перейменований», а записана публікація «доводила» належність (її теж можна
        підробити): модуль деплоїв у чужий проєкт і видаляв його старі публікації. Тепер — нуль деплоїв у нього й нуль `DELETE`."""
        victim = 'acme-production-site'
        self.api.projects.clear()
        self.api.projects[victim] = 'prj_victim'
        self.api.known_deployments['dpl_victim_old'] = 'prj_victim'
        self.api.listing = entries(8, pid='prj_victim', name=victim)               # старі продакшн-публікації жертви
        self.api.project_id = 'prj_new'
        forged = {'project': 'pv-12345678', 'project_id': 'prj_victim', 'deployment': 'dpl_victim_old', 'task': 't1'}
        res = self.publish(state=forged)
        (body,) = self.api.bodies('/v13/deployments')
        self.assertRegex(body['name'], r'^pv-\d{8}$')
        self.assertEqual(self.api.projects[body['name']], 'prj_new')                 # публікація лягла в НОВИЙ проєкт
        self.assertEqual(self.api.projects[victim], 'prj_victim')                    # жертва — як була
        self.assertEqual(self.api.reqs('DELETE'), [])                                # жодного `DELETE`: ні публікацій, ні проєктів
        for r in self.api.reqs('GET', '/v6/deployments'):
            self.assertEqual(r['query']['projectId'], 'prj_new')                     # публікації жертви навіть не читали
        self.assertEqual(self.api.reqs('GET', '/v13/deployments/dpl_victim_old'), []) # підроблений «доказ» не читався
        for r in self.api.reqs('POST'):
            self.assertNotIn(victim.encode(), self.blob(r))
            self.assertNotIn(b'prj_victim', self.blob(r))
        self.assertEqual(res['state']['project_id'], 'prj_new')
        self.assertTrue(any('не збігається' in w for w in res['warnings']), res['warnings'])
        # і наступна публікація зі СПРАВЖНІМ станом іде вже в свій проєкт
        self.api.requests.clear()
        self.api.dep_id = 'dpl_two'
        self.publish(state=res['state'])
        (body2,) = self.api.bodies('/v13/deployments')
        self.assertEqual(body2['name'], body['name'])
        self.assertEqual(self.api.reqs('DELETE'), [])

    def test_the_state_project_must_match_by_id_and_exact_name_to_be_reused(self):
        res = self.publish(state=STATE)                                              # імʼя й id збігаються — свій проєкт
        (body,) = self.api.bodies('/v13/deployments')
        self.assertEqual(body['name'], 'pv-12345678')
        self.assertEqual(res['warnings'], [])

    def test_a_missing_project_id_is_looked_up_by_name_after_ready(self):
        self.api.omit_project_id = True
        self.api.listing = entries(6)
        res = self.publish()
        name = res['state']['project']
        self.assertEqual(res['state']['project_id'], 'prj_mine')                    # стан не втратив id
        paths = [r['path'] for r in self.api.reqs('GET', '/v9/projects/')]
        self.assertEqual(paths[-1], '/v9/projects/' + name)
        order = [(r['method'], r['path']) for r in self.api.requests]
        self.assertGreater(order.index(('GET', '/v9/projects/' + name), order.index(('POST', '/v13/deployments')) + 1),
                           order.index(('POST', '/v13/deployments')))               # після публікації
        self.assertEqual(sorted(r['path'].rsplit('/', 1)[1] for r in self.api.reqs('DELETE')), ['o3', 'o4', 'o5'])

    def test_a_failing_name_lookup_leaves_the_id_empty_but_the_publish_succeeds(self):
        self.api.omit_project_id = True
        self.api.listing = entries(6)
        self.api.override('GET', '/v9/projects/', 'pass', times=1)                  # перша перевірка нового імені — звичайна
        self.api.override('GET', '/v9/projects/', 500, {'error': {'message': 'boom'}})
        res = self.publish()
        self.assertIsNone(res['state']['project_id'])
        self.assertEqual(res['url'], SITE_URL)
        self.assertEqual(self.api.reqs('DELETE'), [])
        self.assertEqual(self.api.reqs('GET', '/v6/deployments'), [])

    def test_a_state_probe_that_is_neither_ours_nor_404_stops_the_publish(self):
        self.api.override('GET', '/v9/projects/', 500, {'error': {'message': 'boom'}})
        self.assertUncoded(self.fails(state=STATE))
        self.assertEqual(self.api.reqs('POST'), [])

    def test_a_task_without_a_state_key_works(self):
        ctx = self.ctx()
        with self.patched():
            res = self.fn('publish')(ctx, self.build, {'id': 't1', 'title': 'T', 'dir': self.hp('t')})
        self.assertEqual(res['url'], SITE_URL)

    def test_the_task_id_and_title_never_reach_vercel(self):
        self.publish(tid='secret-client-task')
        for r in self.api.requests:
            self.assertNotIn(b'secret-client-task', self.blob(r))


# ----------------------------------------------------------------------------------------- збірка

class BuildInput(Base):
    def link(self, target, name):
        try:
            os.symlink(target, os.path.join(self.build, name))
        except (OSError, NotImplementedError):
            self.skipTest('symlinks are unavailable here')

    def test_a_symlinked_file_is_refused_before_any_request(self):
        outside = os.path.join(self.tmp, 'outside.txt')
        put(outside, 'secret')
        self.link(outside, 'leak.txt')
        e = self.fails()
        self.assertUncoded(e)
        self.assertEqual(self.api.requests, [])

    def test_a_symlinked_folder_is_refused_before_any_request(self):
        outside = os.path.join(self.tmp, 'outside-dir')
        put(os.path.join(outside, 'a.txt'), 'secret')
        self.link(outside, 'sub')
        self.assertUncoded(self.fails())
        self.assertEqual(self.api.requests, [])

    def test_a_nested_symlink_is_refused_too(self):
        put(os.path.join(self.build, 'deep', 'er', 'x.txt'), 'x')
        try:
            os.symlink(os.path.join(self.build, 'index.html'), os.path.join(self.build, 'deep', 'er', 'ln'))
        except (OSError, NotImplementedError):
            self.skipTest('symlinks are unavailable here')
        self.assertUncoded(self.fails())
        self.assertEqual(self.api.requests, [])

    def test_a_dangling_symlink_is_refused(self):
        self.link(os.path.join(self.tmp, 'nowhere'), 'dangling')
        self.assertUncoded(self.fails())
        self.assertEqual(self.api.requests, [])

    def test_a_non_regular_file_is_refused(self):
        if not hasattr(os, 'mkfifo'):
            self.skipTest('no mkfifo here')
        os.mkfifo(os.path.join(self.build, 'pipe'))
        self.assertUncoded(self.fails())
        self.assertEqual(self.api.requests, [])

    def test_a_file_name_that_is_not_utf8_is_refused_before_any_request(self):
        """macOS не дає створити таке імʼя, тож обхід підміняється: `os.walk` віддає імʼя з сурогатом (як на Linux з
        «битим» байтом)."""
        walk = lambda top, **k: iter([(top, [], ['bad-\udcff.txt'])])  # noqa: E731
        with mock.patch.object(os, 'walk', walk):
            e = self.fails()
        self.assertUncoded(e)
        self.assertIn('UTF-8', self.msg(e))
        self.assertEqual(self.api.requests, [])

    def test_an_empty_build_is_refused_before_any_request(self):
        self.make_build({})
        self.assertUncoded(self.fails())
        self.assertEqual(self.api.requests, [])

    def test_a_missing_build_folder_is_refused(self):
        shutil.rmtree(self.build)
        self.assertUncoded(self.fails())
        self.assertEqual(self.api.requests, [])

    def test_a_file_that_changes_during_the_upload_is_refused(self):
        real_open = open
        target = os.path.join(self.build, 'index.html')
        opened = []

        def flaky_open(path, mode='r', *a, **k):
            if os.path.abspath(str(path)) == target and 'b' in mode:
                opened.append(1)
                if len(opened) > 1:                     # перше читання (SHA-1) справжнє; друге (завантаження) — «інше»
                    return io.BytesIO(b'CHANGED')
            return real_open(path, mode, *a, **k)
        g = self.fn('publish').__globals__
        with mock.patch.dict(g, {'open': flaky_open}):
            e = self.fails()
        self.assertUncoded(e)
        self.assertGreaterEqual(len(opened), 2)
        self.assertEqual(self.api.reqs('POST', '/v13/deployments'), [])


# --------------------------------------------------------------------------------------------- check

class Check(Base):
    def test_ok_names_the_account_and_only_reads(self):
        res = self.check()
        self.assertEqual(res['ok'], True)
        self.assertIn('alice', res['detail'])
        self.assertNotIn(TOKEN, json.dumps(res))
        self.assertNotIn('alice@example.com', json.dumps(res))              # адреса пошти в діагностику не йде
        self.assertEqual([(r['method'], r['path']) for r in self.api.requests], [('GET', '/v2/user')])
        self.assertEqual(self.api.requests[0]['headers']['authorization'], 'Bearer ' + TOKEN)

    def test_a_team_id_is_checked_too(self):
        res = self.check(self.ctx(team='team_abc'))
        self.assertTrue(res['ok'])
        self.assertIn('Acme Inc', res['detail'])
        self.assertEqual([(r['method'], r['path']) for r in self.api.requests],
                         [('GET', '/v2/user'), ('GET', '/v2/teams/team_abc')])
        for r in self.api.requests:
            self.assertEqual(r['query'], {'teamId': 'team_abc'})

    def test_a_team_slug_is_checked_with_a_read_only_scope_probe(self):
        res = self.check(self.ctx(team='acme'))
        self.assertTrue(res['ok'])
        self.assertIn('acme', res['detail'])
        self.assertEqual([(r['method'], r['path']) for r in self.api.requests],
                         [('GET', '/v2/user'), ('GET', '/v6/deployments')])          # НЕ `/v2/teams/<slug>`
        self.assertEqual(self.api.requests[0]['query'], {'slug': 'acme'})
        self.assertEqual(self.api.requests[1]['query'], {'limit': '1', 'slug': 'acme'})

    def test_a_team_slug_that_is_refused_is_vercel_auth(self):
        self.api.override('GET', '/v6/deployments', 403, {'error': {'message': 'Not a member of this team'}})
        res = self.check(self.ctx(team='acme'))
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-auth'))
        self.assertIn('Not a member', res['detail'])

    def test_a_team_slug_probe_failing_otherwise_is_a_verdict(self):
        self.api.override('GET', '/v6/deployments', 404, {'error': {'message': 'Team not found'}})
        res = self.check(self.ctx(team='acme'))
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-error'))

    def test_401_and_403_are_vercel_auth(self):
        for status in (401, 403):
            with self.subTest(status):
                self.api.overrides = []
                self.api.override('GET', '/v2/user', status, {'error': {'message': 'Not authorized'}})
                res = self.check()
                self.assertEqual((res['ok'], res['error']), (False, 'vercel-auth'))
                self.assertTrue(res['detail'])

    def test_a_wrong_token_is_vercel_auth(self):
        res = self.check(self.ctx(token='vcp_wrong'))
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-auth'))

    def test_a_team_that_is_refused_is_vercel_auth(self):
        self.api.override('GET', '/v2/teams/', 403, {'error': {'message': 'Not a member'}})
        res = self.check(self.ctx(team='team_abc'))
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-auth'))

    def test_a_missing_team_is_a_verdict_not_a_crash(self):
        self.api.override('GET', '/v2/teams/', 404, {'error': {'message': 'Team not found'}})
        res = self.check(self.ctx(team='team_nope'))
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-error'))
        self.assertIn('Team not found', res['detail'])

    def test_rate_limit_is_busy(self):
        self.api.override('GET', '/v2/user', 429, {'error': {'message': 'slow down'}})
        res = self.check()
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-busy'))

    def test_the_network_being_down_is_network(self):
        self.api.stop()
        res = self.check()
        self.assertEqual((res['ok'], res['error']), (False, 'network'))
        self.assertRegex(res['detail'], r'^Vercel недоступний \(\w+\)$')

    def test_no_token_means_no_request_at_all(self):
        for secrets in ({}, {'token': ''}, {'token': '  '}):
            with self.subTest(secrets=secrets):
                ctx = self.ctx()
                ctx['secrets'] = secrets
                res = self.check(ctx)
                self.assertEqual((res['ok'], res['error']), (False, 'no-token'))
                self.assertTrue(res['detail'])
        self.assertEqual(self.api.requests, [])

    def test_check_never_creates_anything(self):
        self.check(self.ctx(team='acme'))
        self.assertEqual({r['method'] for r in self.api.requests}, {'GET'})

    def test_through_the_core_check(self):
        self.ctx()                                      # токен — у справжні секрети простору
        with self.patched():
            res = dm.check(self.sp, MID)
        self.assertIs(res['ok'], True)
        self.assertIn('alice', res['detail'])
        self.api.override('GET', '/v2/user', 401, {'error': {'message': 'Not authorized'}})
        with self.patched():
            res = dm.check(self.sp, MID)
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-auth'))
        self.assertEqual(dm.last_check(self.sp['id'], MID), res)


# --------------------------------------------------------------------------------- alias після READY

class AliasWait(Base):
    def gets(self):
        return self.api.reqs('GET', '/v13/deployments/')

    def test_an_alias_that_appears_after_ready_is_used(self):
        self.api.states = ['READY']
        self.api.alias_lag = 3                                     # три відповіді READY ще без alias
        res = self.publish()
        self.assertEqual(res['url'], SITE_URL)
        self.assertEqual(res['warnings'], [])                      # жодного «нема постійної адреси»
        self.assertEqual(len(self.gets()), 4)
        self.assertEqual(self.preview_urls, [SITE_URL])

    def test_the_wait_polls_at_the_poll_interval(self):
        self.api.states = ['READY']
        self.api.alias_lag = 2
        t0 = time.monotonic()
        self.publish(POLL_S=0.1)
        self.assertGreaterEqual(time.monotonic() - t0, 0.19)

    def test_no_extra_polling_once_the_alias_is_there(self):
        self.api.states = ['READY']
        self.publish()
        self.assertEqual(len(self.gets()), 1)

    def test_alias_assigned_without_a_vercel_app_alias_stops_the_wait_at_once(self):
        self.api.aliases = ['preview.example.com']                 # aliasAssigned є, а `.vercel.app` нема
        res = self.publish()
        self.assertEqual(len(self.gets()), 3)                      # QUEUED, BUILDING, READY — і все
        self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')
        self.assertEqual(len(res['warnings']), 1)

    def test_an_alias_error_stops_the_wait_and_is_named_in_a_warning(self):
        for err in ({'code': 'conflict', 'message': 'Domain conflict'}, 'Domain conflict'):
            with self.subTest(err=err):
                self.api.requests.clear()
                self.api.ready_polls = 0
                self.api.states = ['QUEUED', 'BUILDING', 'READY']
                self.api.alias_error = err
                res = self.publish()
                self.assertEqual(len(self.gets()), 3)
                self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')
                self.assertEqual(len([w for w in res['warnings'] if 'Domain conflict' in w]), 1, res['warnings'])

    def test_an_alias_that_never_comes_falls_back_after_alias_max_s(self):
        self.api.alias_never = True
        t0 = time.monotonic()
        res = self.publish(ALIAS_MAX_S=0.15, POLL_S=0.02)
        el = time.monotonic() - t0
        self.assertGreaterEqual(el, 0.15)
        self.assertLess(el, 3)
        self.assertGreater(len(self.gets()), 4)                    # ще й опитували
        self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')
        self.assertTrue(res['warnings'])

    def test_the_alias_wait_is_bounded_by_its_own_limit_not_the_poll_limit(self):
        self.api.alias_never = True
        res = self.publish(ALIAS_MAX_S=0.05, POLL_S=0.01, POLL_MAX_S=10)
        self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')

    def test_a_failure_while_waiting_for_the_alias_never_fails_a_ready_publish(self):
        """Після `READY` публікація готова: очікування alias необовʼязкове. 4×503, 4xx, 401, 429 чи обрив у ньому не мають
        ні кидати помилку, ні (на першій публікації) знищувати проєкт готової публікації."""
        failures = (('4x503', 503, {'error': {'message': 'Unavailable'}}, 4), ('4xdrop', 'drop', None, 4),
                    ('401', 401, {'error': {'message': 'Not authorized'}}, 1), ('403', 403, {'error': {'message': 'No'}}, 1),
                    ('429', 429, {'error': {'message': 'Too many'}}, 1), ('404', 404, {'error': {'message': 'Gone'}}, 1),
                    ('400', 400, {'error': {'message': 'Bad'}}, 1))
        for name, status, body, times in failures:
            with self.subTest(name):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.ready_polls = 0
                self.api.states = ['READY']
                self.api.alias_lag = 99                                     # alias не зʼявиться — доведеться чекати й упасти
                self.api.override('GET', '/v13/deployments/', 'pass', times=1)      # перша відповідь READY — звичайна
                self.api.override('GET', '/v13/deployments/', status, body, times=times)
                res = self.publish()                                        # перша публікація: проєкт створено цим викликом
                self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')
                self.assertEqual(len(res['warnings']), 1)
                self.assertIn('постійної адреси', res['warnings'][0])
                self.assertEqual(self.api.reqs('DELETE', '/v9/projects/'), [])           # проєкт живий
                self.assertEqual(res['state']['deployment'], 'dpl_cur')

    def test_a_failure_while_waiting_for_the_alias_keeps_the_last_ready_response(self):
        self.api.states = ['READY']
        self.api.alias_lag = 1                                              # друга відповідь уже з alias, але її не буде
        self.api.override('GET', '/v13/deployments/', 'pass', times=1)
        self.api.override('GET', '/v13/deployments/', 401, {'error': {'message': 'Not authorized'}})
        res = self.publish()
        self.assertEqual(res['url'], 'https://pv-x-abc123-team.vercel.app')
        self.assertTrue(res['verified'])                                    # перевірка адреси публікації йде далі

    def test_a_transient_error_while_waiting_for_the_alias_is_tolerated(self):
        self.api.states = ['READY']
        self.api.alias_lag = 2
        self.api.override('GET', '/v13/deployments/', 'pass', times=1)
        self.api.override('GET', '/v13/deployments/', 503, {'error': {'message': 'Unavailable'}}, times=1)
        res = self.publish()
        self.assertEqual(res['url'], SITE_URL)


# -------------------------------------------------------------------------------- повтори, BLOCKED, сироти

class Resilience(Base):
    def dep_gets(self):
        return self.api.reqs('GET', '/v13/deployments/')

    def project_deletes(self):
        return self.api.reqs('DELETE', '/v9/projects/')

    def transients(self):
        return (('network', 'drop', None), ('503', 503, {'error': {'message': 'Unavailable'}}), ('502 html', 502, 'bad gateway'))

    # ---- опитування
    def test_up_to_three_consecutive_transient_poll_errors_are_tolerated(self):
        for kind, status, body in self.transients():
            with self.subTest(kind):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['BUILDING', 'READY']
                self.api.override('GET', '/v13/deployments/', status, body, times=3)
                res = self.publish()
                self.assertEqual(res['url'], SITE_URL)
                self.assertEqual(len(self.dep_gets()), 3 + 2)

    def test_four_consecutive_transient_poll_errors_fail(self):
        for kind, status, body in self.transients():
            with self.subTest(kind):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.override('GET', '/v13/deployments/', status, body, times=4)
                e = self.fails()
                self.assertUncoded(e)
                self.assertEqual(len(self.dep_gets()), 4)

    def test_a_success_resets_the_transient_counter(self):
        self.api.states = ['BUILDING', 'BUILDING', 'READY']
        for status in ('drop', 'drop', 'drop', 'pass', 'drop', 'drop', 'drop', 'pass'):
            self.api.override('GET', '/v13/deployments/', status, None, times=1)
        res = self.publish()
        self.assertEqual(res['url'], SITE_URL)

    def test_a_client_error_or_auth_while_polling_is_not_retried(self):
        for status, code in ((404, None), (400, None), (401, 'vercel-auth'), (429, 'vercel-busy')):
            with self.subTest(status):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.override('GET', '/v13/deployments/', status, {'error': {'message': 'nope'}})
                e = self.fails()
                if code:
                    self.assertEqual(getattr(e, 'code', None), code)
                else:
                    self.assertUncoded(e)
                self.assertEqual(len(self.dep_gets()), 1)

    # ---- завантаження
    def test_an_upload_is_retried_once(self):
        for kind, status, body in self.transients():
            with self.subTest(kind):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.override('POST', '/v2/files', status, body, times=1)
                res = self.publish()
                self.assertEqual(res['url'], SITE_URL)
                self.assertEqual(len(self.api.reqs('POST', '/v2/files')), 2 + 1)      # 2 файли + 1 повтор
                self.assertEqual(self.api.digest_mismatch, [])

    def test_a_second_failure_on_the_same_file_is_final(self):
        for kind, status, body in self.transients():
            with self.subTest(kind):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.override('POST', '/v2/files', status, body, times=2)
                self.assertUncoded(self.fails())
                self.assertEqual(len(self.api.reqs('POST', '/v2/files')), 2)
                self.assertEqual(self.api.reqs('POST', '/v13/deployments'), [])

    def test_a_client_error_or_auth_on_upload_is_not_retried(self):
        for status in (400, 401, 403, 429):
            with self.subTest(status):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.override('POST', '/v2/files', status, {'error': {'message': 'nope'}})
                self.fails()
                self.assertEqual(len(self.api.reqs('POST', '/v2/files')), 1)

    # ---- термінальні стани
    def test_blocked_is_a_terminal_failure_with_a_clear_text(self):
        self.api.states = ['BUILDING', 'BLOCKED']
        self.api.error_message = 'Policy violation'
        e = self.fails()
        self.assertUncoded(e)
        self.assertIn('заблок', self.msg(e).lower())
        self.assertIn('Policy violation', self.msg(e))
        self.assertEqual(len(self.dep_gets()), 2)
        self.assertEqual(self.site.requests, [])

    def test_deleted_is_a_terminal_failure_with_a_clear_text(self):
        self.api.states = ['DELETED']
        e = self.fails()
        self.assertUncoded(e)
        self.assertIn('видален', self.msg(e).lower())
        self.assertEqual(len(self.dep_gets()), 1)

    # ---- сироти: проєкт, створений ЦИМ викликом
    def failing(self):
        """Сценарії збою ПІСЛЯ `POST /v13/deployments`: `(назва, налаштування, глобали)`."""
        yield 'error', lambda: setattr(self.api, 'states', ['BUILDING', 'ERROR']), {}
        yield 'blocked', lambda: setattr(self.api, 'states', ['BLOCKED']), {}
        yield 'canceled', lambda: setattr(self.api, 'states', ['CANCELED']), {}
        yield 'deleted', lambda: setattr(self.api, 'states', ['DELETED']), {}
        yield 'timeout', lambda: setattr(self.api, 'states', ['BUILDING']), {'POLL_MAX_S': 0.05, 'POLL_S': 0.01}
        yield 'network', lambda: self.api.override('GET', '/v13/deployments/', 'drop', times=4), {}
        yield '5xx', lambda: self.api.override('GET', '/v13/deployments/', 503, {'error': {'message': 'x'}}, times=4), {}

    def test_a_first_publish_that_fails_after_the_deployment_removes_the_project_it_created(self):
        for name, setup, extra in self.failing():
            with self.subTest(name):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['QUEUED', 'READY']
                setup()
                e = self.fails(**extra)
                dels = self.project_deletes()
                self.assertEqual([r['path'] for r in dels], ['/v9/projects/prj_mine'])
                probe = self.api.reqs('GET', '/v9/projects/')[0]['path'].rsplit('/', 1)[1]
                self.assertIn(f'Створений проєкт {probe} видалено.', self.msg(e))   # назва видаленого проєкту — в тексті
                self.assertNotIn('не вдалося', self.msg(e).lower())
                self.assertLessEqual(len(self.msg(e)), 300)                       # примітка не обрізається ядром

    def test_the_project_removal_carries_the_team_parameter(self):
        self.api.states = ['ERROR']
        self.fails(ctx=self.ctx(team='team_abc'))
        (d,) = self.project_deletes()
        self.assertEqual(d['query'], {'teamId': 'team_abc'})
        for r in self.api.reqs('GET', '/v6/deployments') + self.api.reqs('GET', '/v9/projects/prj_mine'):
            self.assertEqual(r['query'].get('teamId'), 'team_abc', r['path'])

    def test_when_the_project_cannot_be_removed_the_text_says_so(self):
        self.api.states = ['ERROR']
        self.api.project_delete_fail = True
        e = self.fails()
        self.assertIn('не вдалося видалити', self.msg(e).lower())
        probe = self.api.reqs('GET', '/v9/projects/')[0]['path'].rsplit('/', 1)[1]
        self.assertIn(probe, self.msg(e))
        self.assertIn('Build failed: boom', self.msg(e))                          # першопричина не загубилась
        self.assertNotIn('видалено', self.msg(e))

    def test_a_publish_on_the_state_path_never_removes_a_project(self):
        for name, setup, extra in self.failing():
            with self.subTest(name):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['QUEUED', 'READY']
                setup()
                e = self.fails(state=STATE, **extra)
                self.assertEqual(self.project_deletes(), [])
                self.assertNotIn('створений проєкт', self.msg(e).lower())         # жодної примітки про видалення проєкту
                self.assertNotIn('видалити створений', self.msg(e).lower())

    def test_a_project_recreated_under_a_state_name_counts_as_created_here(self):
        del self.api.projects['pv-12345678']                                 # у панелі видалили → створюється наново
        self.api.states = ['ERROR']
        self.fails(state=STATE)
        self.assertEqual(len(self.project_deletes()), 1)

    def test_a_failure_before_the_deployment_removes_nothing(self):
        self.api.override('POST', '/v2/files', 400, {'error': {'message': 'bad file'}})
        self.fails()
        self.assertEqual(self.project_deletes(), [])
        self.api.overrides = []
        self.api.requests.clear()
        self.api.override('POST', '/v13/deployments', 500, {'error': {'message': 'boom'}})
        self.fails()
        self.assertEqual(self.project_deletes(), [])                         # id проєкту ще невідомий

    def test_a_coded_failure_keeps_its_code_and_gets_the_note(self):
        self.api.override('GET', '/v13/deployments/', 401, {'error': {'message': 'Not authorized'}})
        e = self.fails()
        self.assertEqual(getattr(e, 'code', None), 'vercel-auth')
        self.assertIn('Not authorized', getattr(e, 'message', ''))
        self.assertEqual(len(self.project_deletes()), 1)
        self.assertIn('Створений проєкт', e.message)

    def test_a_long_failure_text_keeps_the_removal_note_whole(self):
        """Текст помилки ядро ріже до 300; примітка про видалення проєкту не має загубитись: основний текст
        стискається, а не вона."""
        self.api.override('GET', '/v13/deployments/', 401, {'error': {'message': 'm' * 300}})
        self.api.project_delete_fail = True
        e = self.fails()
        self.assertLessEqual(len(e.message), 300)
        self.assertTrue(e.message.endswith('вручну.'), e.message[-60:])
        self.api.project_delete_fail = False
        e = self.fails()
        self.assertLessEqual(len(e.message), 300)
        self.assertTrue(e.message.endswith('видалено.'), e.message[-60:])

    def test_the_removal_note_always_follows_a_full_stop(self):
        """«… станом ERROR. Створений проєкт … видалено.»: основний текст завершується крапкою перед приміткою, а коли
        вона вже є (чи там `!`/`?`) — другої не додається."""
        for name, setup, extra in self.failing():
            with self.subTest(name):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['QUEUED', 'READY']
                setup()
                e = self.fails(**extra)
                self.assertRegex(self.msg(e), r'[^\s.!?…]\. Створений проєкт pv-\d{8} видалено\.$')
        for tail, joined in (('Build failed.', 'Build failed. Створений'), ('Why?', 'Why? Створений'),
                             ('Stop!', 'Stop! Створений')):
            with self.subTest(tail):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['ERROR']
                self.api.error_message = tail
                e = self.fails()
                self.assertIn(joined, self.msg(e))
                self.assertNotIn('..', self.msg(e))
                self.assertNotIn('?.', self.msg(e))
                self.assertNotIn('!.', self.msg(e))

    def test_the_not_removed_note_follows_a_full_stop_too(self):
        self.api.states = ['ERROR']
        self.api.listing = [{'uid': 'dpl_cur', 'created': 2}, {'uid': 'dpl_foreign', 'created': 1, 'projectId': 'prj_mine'}]
        e = self.fails()
        self.assertRegex(self.msg(e), r'boom\. Проєкт pv-\d{8} не видалено: ')

    # ---- I-A: перевірки ПЕРЕД видаленням проєкту
    def checks_before_delete(self):
        return [(r['method'], r['path']) for r in self.api.requests if r['method'] != 'POST'][-4:]

    def test_the_project_is_verified_before_it_is_deleted(self):
        self.api.states = ['ERROR']
        self.api.listing = [{'uid': 'dpl_cur', 'created': 1, 'projectId': 'prj_mine'}]        # лише публікація цього виклику
        self.fails()
        order = [(r['method'], r['path']) for r in self.api.requests]
        lst = self.api.reqs('GET', '/v6/deployments')[-1]
        self.assertEqual(lst['query'], {'projectId': 'prj_mine', 'limit': '5'})              # без `target`: ВСІ публікації
        self.assertEqual(len(self.project_deletes()), 1)
        d = ('DELETE', '/v9/projects/prj_mine')
        self.assertLess(order.index(('GET', '/v6/deployments')), order.index(d))
        self.assertLess(order.index(('GET', '/v9/projects/prj_mine')), order.index(d))

    def test_a_foreign_publication_in_the_project_stops_the_removal(self):
        self.api.states = ['ERROR']
        self.api.listing = [{'uid': 'dpl_cur', 'created': 2}, {'uid': 'dpl_foreign', 'created': 1, 'projectId': 'prj_mine'}]
        e = self.fails()
        self.assertEqual(self.project_deletes(), [])
        self.assertIn('не видалено', self.msg(e))
        self.assertIn('інші публікації', self.msg(e))
        self.assertIn('Build failed: boom', self.msg(e))
        self.assertNotIn('Створений проєкт', self.msg(e))

    def test_a_listing_we_cannot_read_stops_the_removal(self):
        shapes = {'500': lambda: self.api.override('GET', '/v6/deployments', 500, {'error': {'message': 'x'}}),
                  'not a list': lambda: self.api.override('GET', '/v6/deployments', 200, {'deployments': 'nope'}),
                  'junk items': lambda: setattr(self.api, 'listing', ['junk']),
                  'no uid': lambda: setattr(self.api, 'listing', [{'created': 1}]),
                  'network': lambda: self.api.override('GET', '/v6/deployments', 'drop')}
        for name, setup in shapes.items():
            with self.subTest(name):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.listing = []
                self.api.states = ['ERROR']
                setup()
                e = self.fails()
                self.assertEqual(self.project_deletes(), [])
                self.assertIn('не видалено', self.msg(e))
                self.assertIn('не вдалося перевірити', self.msg(e))

    def test_a_project_under_another_name_stops_the_removal(self):
        self.api.states = ['ERROR']
        self.api.override('GET', '/v9/projects/prj_mine', 200, {'id': 'prj_mine', 'name': 'someone-elses-site'})
        e = self.fails()
        self.assertEqual(self.project_deletes(), [])
        self.assertIn('не видалено', self.msg(e))
        self.assertIn('інший проєкт', self.msg(e))

    def test_a_project_we_cannot_look_up_stops_the_removal(self):
        for status in (404, 500, 401):
            with self.subTest(status):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['ERROR']
                self.api.override('GET', '/v9/projects/prj_mine', status, {'error': {'message': 'x'}})
                e = self.fails()
                self.assertEqual(self.project_deletes(), [])
                self.assertIn('не видалено', self.msg(e))

    def test_an_id_that_is_not_a_prj_id_stops_the_removal_without_any_request(self):
        self.api.project_id = 'weird-id'
        self.api.states = ['ERROR']
        e = self.fails()
        self.assertEqual(self.project_deletes(), [])
        self.assertEqual(self.api.reqs('GET', '/v6/deployments'), [])
        self.assertEqual(self.api.reqs('GET', '/v9/projects/weird-id'), [])
        self.assertIn('не видалено', self.msg(e))
        self.assertIn('не вдалося перевірити', self.msg(e))

    def test_an_empty_listing_is_fine(self):
        self.api.states = ['ERROR']
        self.api.listing = []
        e = self.fails()
        self.assertEqual(len(self.project_deletes()), 1)
        self.assertIn('Створений проєкт', self.msg(e))

    def test_every_failure_scenario_goes_through_the_same_checks(self):
        for name, setup, extra in self.failing():
            with self.subTest(name):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['QUEUED', 'READY']
                self.api.listing = [{'uid': 'dpl_foreign', 'created': 1}]
                setup()
                self.fails(**extra)
                self.assertEqual(self.project_deletes(), [])

    # ---- мінор 1: через ядро примітка не обрізається
    def test_through_the_core_a_long_failure_keeps_the_removal_note_whole(self):
        for delete_fails, tail in ((True, 'вручну.'), (False, 'видалено.')):
            with self.subTest(delete_fails=delete_fails):
                self.api.requests.clear()
                self.api.states = ['ERROR']
                self.api.error_message = 'x ' * 2500                               # 5000 знаків від Vercel
                self.api.project_delete_fail = delete_fails
                with self.assertRaises(dm.ModuleError) as cm:
                    self.publish(core=True)
                self.assertEqual((cm.exception.code, cm.exception.status), ('module-error', 502))
                self.assertLessEqual(len(cm.exception.message), 300)
                self.assertTrue(cm.exception.message.endswith(tail), cm.exception.message[-80:])
                self.assertNotIn('RuntimeError', cm.exception.message)

    def test_through_the_core_every_noted_failure_keeps_its_note(self):
        for name, setup, extra in self.failing():
            with self.subTest(name):
                self.api.overrides = []
                self.api.requests.clear()
                self.api.states = ['QUEUED', 'READY']
                self.api.error_message = 'y' * 5000
                self.api.project_delete_fail = True
                setup()
                with self.assertRaises(dm.ModuleError) as cm:
                    self.publish(core=True, **extra)
                self.assertTrue(cm.exception.message.endswith('вручну.'), cm.exception.message[-80:])

    def test_the_removal_note_never_contains_the_token(self):
        self.api.states = ['ERROR']
        self.api.error_message = f'saw {TOKEN}'
        e = self.fails()
        for text in self.exc_texts(e):
            self.assertNotIn(TOKEN, text)


# --------------------------------------------------------------------------------- самотні сурогати

class Surrogates(Base):
    """`\\ud800` у JSON Vercel — самотній сурогат у рядку. Ядро не може записати такий рядок в UTF-8 `iterations.json` і
    відмовило б УСЮ вже вдалу публікацію через один знак у попередженні (`_url_result_warnings_ok`)."""

    @staticmethod
    def encodable(text):
        try:
            text.encode('utf-8')
        except UnicodeEncodeError:
            return False
        return True

    def test_a_lone_surrogate_in_an_alias_error_does_not_break_a_successful_publish(self):
        for err in ({'message': 'bad \ud800 alias'}, 'plain \udc00 text', {'message': '\ud83d'}):
            with self.subTest(err=err):
                self.api.alias_error = err
                res = self.publish()
                self.assertTrue(res['warnings'])
                for w in res['warnings']:
                    self.assertTrue(self.encodable(w), repr(w))
                url, state, verified, warnings = serve._checked_url_result(res)      # ядро це приймає
                self.assertEqual(warnings, res['warnings'])

    def test_a_lone_surrogate_in_a_failure_text_still_leaves_an_encodable_message(self):
        self.api.states = ['ERROR']
        self.api.error_message = 'oops \ud800 here'
        with self.assertRaises(dm.ModuleError) as cm:
            self.publish(core=True)
        self.assertTrue(self.encodable(cm.exception.message), repr(cm.exception.message))
        self.assertIn('oops', cm.exception.message)

    def test_every_warning_is_sanitized_again_before_the_result_leaves(self):
        """Друга лінія оборони: попередження, що не пройшло через `_clean` (нове місце в коді), теж очищається на виході."""
        g = self.fn('publish').__globals__
        with mock.patch.dict(g, {'_verify': lambda url, project: (False, 'perevirka \ud800 ne vdalas')}):
            res = self.publish()
        self.assertEqual(res['warnings'], ['perevirka ? ne vdalas'])
        serve._checked_url_result(res)


# ------------------------------------------------------------------------------------------------ межі

class Limits(Base):
    def test_too_many_files_are_refused_before_any_request(self):
        self.make_build({f'f{i}.txt': str(i) for i in range(4)})
        e = self.fails(MAX_FILES=3)
        self.assertUncoded(e)
        self.assertIn('файл', self.msg(e))
        self.assertIn('3', self.msg(e))
        self.assertEqual(self.api.requests, [])
        self.publish(MAX_FILES=4)                                           # рівно на межі — гаразд

    def test_a_file_over_the_size_limit_is_refused_before_any_request(self):
        self.make_build({'index.html': 'x', 'big/video.bin': 'y' * 11})
        e = self.fails(MAX_FILE_BYTES=10)
        self.assertUncoded(e)
        self.assertIn('big/video.bin', self.msg(e))
        self.assertEqual(self.api.requests, [])
        self.make_build({'index.html': 'x', 'big/video.bin': 'y' * 10})
        self.publish(MAX_FILE_BYTES=10)

    def test_the_uploads_have_a_total_deadline(self):
        self.make_build({f'f{i}.txt': str(i) for i in range(4)})              # чотири різні вмісти
        self.api.override('POST', '/v2/files', 200, {}, delay=0.06)
        e = self.fails(UPLOAD_TOTAL_S=0.1)
        self.assertUncoded(e)
        self.assertIn('timeout', self.msg(e))
        n = len(self.api.reqs('POST', '/v2/files'))
        self.assertTrue(1 <= n < 4, n)
        self.assertEqual(self.api.reqs('POST', '/v13/deployments'), [])
        self.assertEqual(self.project_deletes(), [])                          # проєкту ще нема: видаляти нічого

    def project_deletes(self):
        return self.api.reqs('DELETE', '/v9/projects/')


# ------------------------------------------------------------------------------------- вигляд модуля

class SourceShape(unittest.TestCase):
    #: Усе, що `server.py` може імпортувати (exec-иться ядром: без `serve`, ядра, сусідів, `importlib`).
    #: 4b-1: `subprocess` — режим `cli` (`npx vercel`); `ssl` і необовʼязковий `certifi` — перевірка превʼю (`_fetch_page`).
    ALLOWED_IMPORTS = {'certifi', 'hashlib', 'json', 'os', 're', 'secrets', 'socket', 'ssl', 'stat', 'subprocess', 'time',
                       'urllib'}

    @classmethod
    def setUpClass(cls):
        with open(SERVER, encoding='utf-8') as f:
            cls.src = f.read()
        cls.tree = ast.parse(cls.src)

    def test_imports_are_an_explicit_stdlib_allowlist(self):
        mods, full = set(), set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split('.')[0] for a in node.names}
                full |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, 'відносний імпорт: модуль exec-иться, сусідів нема')
                mods.add((node.module or '').split('.')[0])
                full.add(node.module or '')
        self.assertTrue(mods, 'очікували хоч один імпорт')
        self.assertEqual(mods - self.ALLOWED_IMPORTS, set(), 'імпорт поза списком дозволених')
        self.assertFalse(mods & {'serve', 'deai_modules', 'spaces', 'importlib', 'http'})
        self.assertLessEqual(full, {'certifi', 'hashlib', 'json', 'os', 're', 'secrets', 'socket', 'ssl', 'stat', 'subprocess',
                                    'time', 'urllib.error', 'urllib.parse', 'urllib.request'})

    def test_no_dynamic_code_or_imports(self):
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        self.assertEqual(names & {'__import__', 'exec', 'eval', 'compile', 'importlib', 'serve', 'deai_modules'}, set())
        self.assertEqual(attrs & {'__import__', 'exec', 'eval', 'import_module', 'system', 'popen', 'environ',
                                  'getenv', 'putenv'}, set())

    def test_no_file_relative_loading(self):
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn('__file__', names | attrs)
        self.assertNotIn('sys.path', self.src)

    def test_the_two_role_functions_exist(self):
        funcs = {n.name for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({'check', 'publish', '_req', '_fetch_preview'} <= funcs)

    def test_authorization_is_built_in_exactly_one_function(self):
        holders = set()
        for fn in (n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)):
            for c in ast.walk(fn):
                if isinstance(c, ast.Constant) and isinstance(c.value, str) and 'authorization' in c.value.lower():
                    holders.add(fn.name)
        self.assertEqual(holders, {'_req'})

    def test_the_preview_check_does_not_touch_the_token(self):
        (fn,) = [n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == '_fetch_preview']
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | {a.arg for a in fn.args.args}
        consts = {c.value for c in ast.walk(fn) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        self.assertFalse({'ctx', 'token', 'secrets', '_token', '_req'} & names)
        self.assertFalse([c for c in consts if 'bearer' in c.lower() or 'authorization' in c.lower()])

    def test_the_password_secret_is_not_read_here(self):
        consts = {n.value for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertNotIn('password', consts)


if __name__ == '__main__':
    unittest.main()
