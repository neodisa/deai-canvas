"""API модулів, `capabilities` у відповідях і `/api/ds-tokens` (етап 2а, Task 6).

Маршрути (усі — у `Handler._REGISTRY_ROUTES`: заголовок `X-Canvas-Task` і префікс `/t/<id>/` на них не діють;
простір — параметр `space`, типово — простір, зафіксований на вході):

  GET  /api/modules?space=         → {modules: [{id, name, version, api, roles, builtin, enabled, implicit,
                                       status, last_check?, settings: [{key, type, label, required, value? | set,
                                       options?}], error?}]}
  POST /api/module-enable          {space?, id, settings?, secrets?, replace?} → {ok, module, check[, replaced]}
  POST /api/module-disable         {space?, id}                      → {ok, module}
  POST /api/module-settings        {space?, id, settings?, secrets?} → {ok, module, check}
  POST /api/module-check           {space?, id}                      → {ok, module, check}
  GET  /api/ds-tokens?space=       → {profile: 'space:<id>', tokens, source} | {profile: null[, error]}

Що доводиться:
  * кожен маршрут і кожен код відмови (`unknown-space` 404, `unknown-module` 404, `bad-settings` 400,
    `role-taken` 409, `space-json-unreadable` 409, `spaces-off` 409, Origin 403); `X-Canvas-Task` ігнорується,
    `/t/<id>/` — 400;
  * СЕКРЕТИ НІКОЛИ не у відповідях: лише `set: true|false`; сирі тіла ВСІХ відповідей світу перевіряються на
    значення секрету (і в `check.detail` модуля, що сам його виводить чи кидає в винятку);
  * порядок запису: СПЕРШУ секрети, ПОТІМ `space.json`, ПОТІМ `check`; відмова налаштувань не лишає секрет
    записаним (перевірка до запису);
  * `check`, що ВІДБУВСЯ, — вердикт у тілі (200): `bad-settings`, `module-error`, `check-timeout`, `bad-manifest`
    лягають у `check: {ok: false, error, detail}`; `unknown-module`/`space-json-unreadable`/`spaces-off` — HTTP-відмови;
  * `replace: true` у `module-enable`: ролі модуля звільняються в ТОМУ САМОМУ записі `space.json` під локом
    (`replaced` — кого звільнено); не `bool` і явний `null` — `bad-settings` ДО секрету; на модуль, що не
    завантажився, — відмова (`module-error`/`bad-manifest`) ДО секрету й до запису, інакше простір лишився б без
    постачальника; два паралельні `replace` лишають рівно одного постачальника ролі;
  * `status` модуля: `missing` (увімкнений, але не в каталозі), `error` (не завантажився / останній `check` не ok),
    `unchecked` (завантажився, `check` ще не було), `ok`;
  * `capabilities` — поле `space.capabilities` у `/api/task|tasks|tasks-overview` і `capabilities` у кожному записі
    `/api/spaces` (НЕ в `spaces.describe`); бита `space.json` одного простору не ламає `/api/spaces`;
  * `/api/ds-tokens`: профіль, `{profile: null}` без постачальника й з порожньою мапою, `{profile: null, error}` на
    помилку модуля (завжди 200 — інспектор мусить працювати).

⛔ Ізоляція: власні тимчасові `HOME`/`DEAI_HOME`/`DC_TASKS_FILE` (+ `DC_NO_OVERVIEW`), справжній `~/.deai` стереже
`spaces_guard` (знімок на вході в модуль, звірка на виході). Розтяжка: сокет лише на порт власного сервера тесту.
"""
import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # пакета `tests` нема — охоронець поруч
import deai_modules as dm  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
from atomic_io import atomic_write_json  # noqa: E402

_REAL = None

SECRET = 'S3cr3t-пароль-Zq91!'
ROUTES_POST = ('/api/module-enable', '/api/module-disable', '/api/module-settings', '/api/module-check')
ROUTES_GET = ('/api/modules', '/api/ds-tokens')
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
#: Вбудовані модулі справжнього `app/modules` за абеткою: новий вбудований модуль — тут і лише тут.
BUILTIN_IDS = ['css-tokens', 'static-publish', 'supabase-comments', 'vercel-publish']


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _read(path):
    with open(path, 'rb') as fh:
        return fh.read()


def _json(path):
    return json.loads(_read(path).decode('utf-8'))


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def _manifest(mid, roles=(), settings=()):
    return {'api': 1, 'id': mid, 'name': mid, 'version': '0.0.1', 'roles': list(roles),
            'settings': list(settings)}


#: Модулі-фікстури для `builtin_dir`, що підміняється: id → (ролі, налаштування, `server.py`).
FIXTURES = {
    # друга роль `publish`: проти неї `role-taken`
    'alt-publish': (['publish'], [{'key': 'note', 'type': 'text', 'label': 'Note'},
                                  {'key': 'token', 'type': 'secret', 'label': 'Token'}],
                    "def check(ctx):\n    return {'ok': True}\n\ndef publish(ctx, built, *a, **k):\n    return {}\n"),
    # синтаксична помилка: модуль у каталозі зі `status: error`
    'broken': (['tokens'], [], 'def check(ctx:\n'),
    # той самий дефект, але з роллю `publish` (манифест дійсний → роль лишається за ним): ціль для `replace`
    'broken-publish': (['publish'], [{'key': 'token', 'type': 'secret', 'label': 'Token'}], 'def check(ctx:\n'),
    # роль `publish`, а функції `publish()` нема → `bad-manifest` (інший `error_code`, ніж у синтаксичної помилки)
    'headless-publish': (['publish'], [{'key': 'token', 'type': 'secret', 'label': 'Token'}],
                         "def check(ctx):\n    return {'ok': True}\n"),
    # свій `ok: false`
    'fail-check': ([], [], "def check(ctx):\n    return {'ok': False, 'error': 'nope', 'detail': 'because'}\n"),
    # своя відмова з кодом ядра (його клас модуль бере з `ctx`): після запису стану це вердикт, а не HTTP-збій
    'bad-folder': ([], [], "def check(ctx):\n    raise ctx['ModuleError']('bad-folder', message='path-system')\n"),
    'slow': ([], [], "import time\n\ndef check(ctx):\n    time.sleep(1.5)\n    return {'ok': True}\n"),
    # сам виводить секрет у `detail` чи кидає його у винятку — ядро мусить вирізати
    'vault': ([], [{'key': 'token', 'type': 'secret', 'label': 'Token'},
                   {'key': 'mode', 'type': 'select', 'label': 'Mode', 'default': 'echo',
                    'options': [{'value': 'echo', 'label': 'Echo'}, {'value': 'boom', 'label': 'Boom'}]}],
              "def check(ctx):\n    t = ctx['secrets'].get('token', '')\n"
              "    if ctx['settings'].get('mode') == 'boom':\n        raise RuntimeError('bad token ' + t)\n"
              "    return {'ok': True, 'detail': 'token ' + t}\n"),
    'slow-tokens': (['tokens'], [],
                    "import time\n\ndef check(ctx):\n    return {'ok': True}\n\n"
                    "def tokens(ctx):\n    time.sleep(1.5)\n    return {'tokens': {'--a': ['1']}, 'source': 'x'}\n"),
    'odd-tokens': (['tokens'], [{'key': 'shape', 'type': 'text', 'label': 'Shape', 'default': 'str'}],
                   "def check(ctx):\n    return {'ok': True}\n\n"
                   "def tokens(ctx):\n    s = ctx['settings'].get('shape')\n"
                   "    if s == 'str':\n        return {'tokens': 'nope'}\n"
                   "    if s == 'scalar':\n        return {'tokens': {'--a': 'x'}}\n    return 5\n"),
}


class Http:
    """Запити до сервера в процесі; сирі тіла ВСІХ відповідей — у `self.raw` (грепаються на секрет)."""
    base = None

    def _call(self, method, path, payload=None, headers=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                code, raw = r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read().decode('utf-8')
        self.raw.append((method, path, raw))
        try:
            return code, json.loads(raw)
        except ValueError:
            return code, raw                    # `send_error` відповідає HTML

    def get(self, path, headers=None):
        return self._call('GET', path, None, headers)

    def post(self, path, payload=None, headers=None):
        return self._call('POST', path, {} if payload is None else payload, headers)

    def headers_of(self, method, path, payload=None):
        """Заголовки відповіді (`{імʼя в нижньому регістрі: значення}`) разом зі статусом."""
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}

    def refused(self, st, body, status, code):
        """Відмова в єдиній формі ядра: `{ok: false, code, error}` зі статусом із таблиці кодів."""
        self.assertEqual((st, body.get('ok'), body.get('code')), (status, False, code), body)
        self.assertIsInstance(body.get('error'), str)

    def assert_never_seen(self, *values):
        """Жодна відповідь світу не містить значення (ні сире, ні у JSON-екрані)."""
        for v in values:
            forms = {v, json.dumps(v), json.dumps(v, ensure_ascii=False)[1:-1]}
            for method, path, raw in self.raw:
                for f in forms:
                    self.assertNotIn(f, raw, f'секрет у відповіді {method} {path}')


def _serve(case):
    """Сервер у процесі на ефемерному порту; повертає базову адресу."""
    httpd = serve.make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def stop():
        httpd.shutdown()
        httpd.server_close()
    case.addCleanup(stop)
    return f'http://127.0.0.1:{httpd.server_address[1]}'


def _no_network(case, own_port):
    """Сокет лише на порт власного сервера тесту (8765 справжнього канваса — теж «вихід»)."""
    hits = []
    real = socket.create_connection

    def guarded(address, *a, **kw):
        if address[0] in LOOPBACK and address[1] == own_port:
            return real(address, *a, **kw)
        hits.append(f'{address[0]}:{address[1]}')
        raise OSError('tripwire')
    p = mock.patch.object(socket, 'create_connection', guarded)
    p.start()
    case.addCleanup(p.stop)
    case.addCleanup(lambda: case.assertEqual(hits, [], 'вихід назовні з маршрутів модулів'))


class World(Http, unittest.TestCase):
    """Шар просторів УВІМКНЕНО: `off` (без інтеграцій, задача `tx`, поточний) і `on` (з інтеграціями, `ty`)."""

    def setUp(self):
        self.raw = []
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='dc-modapi-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, 'home')
        # DEAI_HOME — у домівці (як в інших тестах модулів): інакше тимчасова тека macOS (`/var`) дала б `path-system`
        self.deai = os.path.join(self.home, 'stuff', 'deai')
        self.tool = os.path.join(self.home, 'tools', 'dc')
        os.makedirs(self.tool)
        os.makedirs(self.deai, mode=0o700)
        env = mock.patch.dict(os.environ, {
            'HOME': self.home, 'DEAI_HOME': self.deai,
            'DC_TASKS_FILE': os.path.join(self.tmp, 'legacy', 'tasks.json'),     # старого файла нема
            'DC_NO_OVERVIEW': '1', 'DC_IDENTITY_NAME': 'Я', 'DC_IDENTITY_EMAIL': 'me@x'})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DEAI_EXTRA_MODULES', None)       # каталог тесту — лише `app/modules`; `env.stop` повертає змінну
        tool = mock.patch.object(spaces, 'ROOT', self.tool)
        tool.start()
        self.addCleanup(tool.stop)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        self.off_path = os.path.join(self.home, 'deai-work', 'off')
        self.on_path = os.path.join(self.home, 'deai-work', 'on')
        self.off = self._space('off', self.off_path, False, 'tx')
        self.on = self._space('on', self.on_path, True, 'ty')
        atomic_write_json(os.path.join(self.deai, 'spaces.json'),
                          {'version': 1, 'current': 'off', 'spaces': [self.off, self.on]})
        self.secrets_path = os.path.join(self.deai, 'secrets.json')
        self.base = _serve(self)
        _no_network(self, int(self.base.rsplit(':', 1)[1]))

    def _space(self, sid, path, integrations, tid):
        """Простір `sid` із задачею `tid`. Повертає запис реєстру."""
        _write(os.path.join(path, 'space.json'), json.dumps({'name': sid.title(), 'color': 'space-1'}))
        os.makedirs(os.path.join(path, tid))
        _write(os.path.join(path, 'tasks.json'), json.dumps({
            'design_work_root': path, 'current': tid,
            'tasks': {tid: {'title': f'Задача {tid}', 'dir': os.path.join(path, tid)}}}))
        return {'id': sid, 'path': path, 'legacy': False, 'integrations': integrations}

    # ---- фікстури й читачі ----

    def sj(self, space=None):
        return _json(os.path.join((space or self.off)['path'], 'space.json'))

    def sj_bytes(self, space=None):
        return _read(os.path.join((space or self.off)['path'], 'space.json'))

    def modules(self, extra=(), copy=('css-tokens', 'static-publish')):
        """Підмінити `builtin_dir` на тимчасову теку: копії вбудованих `copy` + модулі-фікстури `extra`."""
        d = os.path.join(self.tmp, 'modules')
        os.makedirs(d, exist_ok=True)
        for mid in copy:
            shutil.copytree(os.path.join(ROOT, 'app', 'modules', mid), os.path.join(d, mid),
                            ignore=shutil.ignore_patterns('__pycache__'))
        for mid in extra:
            roles, settings, src = FIXTURES[mid]
            _write(os.path.join(d, mid, 'module.json'), json.dumps(_manifest(mid, roles, settings)))
            _write(os.path.join(d, mid, 'server.py'), src)
        p = mock.patch.object(dm, 'builtin_dir', lambda: d)
        p.start()
        self.addCleanup(p.stop)
        dm.reset_caches()
        return d

    def listing(self, space=None):
        q = f'?space={space}' if space else ''
        st, body = self.get('/api/modules' + q)
        self.assertEqual(st, 200, body)
        return {m['id']: m for m in body['modules']}

    def entry(self, mid, space=None):
        return self.listing(space)[mid]

    def css(self, text=':root{--c-primary:#123456;--gap:4px}', name='ds.css', space=None):
        p = os.path.join((space or self.off)['path'], name)
        _write(p, text)
        return p

    def enable_tokens(self, **kw):
        self.css(**kw)
        st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '{space}/ds.css'}})
        self.assertEqual((st, body['ok']), (200, True), body)
        return body



# ===================================================================================== маршрути й простір

class Routes(World):

    def test_all_six_routes_are_registry_routes(self):
        for r in ROUTES_POST + ROUTES_GET:
            with self.subTest(route=r):
                self.assertIn(r, serve.Handler._REGISTRY_ROUTES)

    def test_the_task_header_is_ignored_on_every_route(self):
        """Заголовок задачі на цих маршрутах не діє: невідома задача не дає 404 «unknown task», а ЧУЖА задача не
        перемикає простір (`ty` живе в `on`, поточний — `off`)."""
        for header in ('ghost', 'ty'):
            h = {'X-Canvas-Task': header}
            with self.subTest(header=header):
                st, body = self.get('/api/modules', h)
                self.assertEqual(st, 200, body)
                self.assertTrue({m['id']: m for m in body['modules']}['static-publish']['implicit'])   # простір `off`
                self.assertEqual(self.get('/api/ds-tokens', h), (200, {'profile': None}))
                for r in ROUTES_POST:
                    st, body = self.post(r, {'id': 'css-tokens'}, h)
                    self.assertEqual(st, 200, (r, body))

    def test_the_task_prefix_is_refused_on_every_route(self):
        for r in ROUTES_GET + ROUTES_POST:
            st, body = self.get('/t/tx' + r) if r in ROUTES_GET else self.post('/t/tx' + r, {'id': 'css-tokens'})
            self.assertEqual(st, 400, r)
            self.assertIn('реєстр задач не привʼязаний', body['error'])
            # текст відмови називає й маршрути модулів, а не лише `/api/space*`
            for named in ('/api/modules', '/api/module-*', '/api/ds-tokens'):
                self.assertIn(named, body['error'])

    def test_a_foreign_origin_is_refused_on_every_post_and_nothing_is_written(self):
        before = self.sj_bytes()
        for r in ROUTES_POST:
            with self.subTest(route=r):
                st, body = self.post(r, {'id': 'css-tokens', 'settings': {'file': 'x.css'}},
                                     {'Origin': 'http://evil.example'})
                self.assertEqual((st, body), (403, {'ok': False, 'error': 'foreign origin'}))
        self.assertEqual(self.sj_bytes(), before)
        self.assertFalse(os.path.exists(self.secrets_path))
        # власний origin проходить: перевірка не «глуха»
        st, body = self.post('/api/module-check', {'id': 'css-tokens'}, {'Origin': self.base})
        self.assertEqual(st, 200, body)

    def test_the_reads_carry_no_cors_header(self):
        """Чужа вебсторінка не мусить читати конфігурацію модулів і токени ДС: ні `Access-Control-Allow-Origin`, ні на
        200, ні на відмові (`/published/…` його має — там інший розмір; тут — ні)."""
        self.enable_tokens()
        for path in ('/api/modules', '/api/ds-tokens', '/api/modules?space=ghost', '/api/ds-tokens?space=ghost'):
            with self.subTest(path=path):
                st, headers = self.headers_of('GET', path)
                self.assertIn(st, (200, 404))
                self.assertNotIn('access-control-allow-origin', headers)
                self.assertEqual(headers['content-type'], 'application/json')
        st, headers = self.headers_of('POST', '/api/module-check', {'id': 'css-tokens'})
        self.assertEqual(st, 200)
        self.assertNotIn('access-control-allow-origin', headers)

    def test_the_default_space_is_the_pinned_one_and_follows_the_current_space(self):
        self.assertTrue(self.entry('static-publish')['implicit'])           # поточний `off`: без інтеграцій
        spaces.switch_space('on')
        e = self.entry('static-publish')
        self.assertEqual((e['enabled'], e['implicit']), (False, False))     # поточний `on`: з інтеграціями

    def test_an_explicit_space_wins_over_the_current_one(self):
        e = self.entry('static-publish', 'on')
        self.assertEqual((e['enabled'], e['implicit']), (False, False))
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'css-tokens',
                                                    'settings': {'file': 'ds.css'}})
        self.assertEqual(st, 200, body)
        self.assertIn('css-tokens', self.sj(self.on)['modules'])
        self.assertNotIn('modules', self.sj(self.off))

    def test_the_space_of_the_request_is_the_named_one_else_the_pinned_one(self):
        """Названий простір стає простором запиту (воркер `call` його успадковує); без назви — зафіксований на вході."""
        seen = []
        real = dm.check

        def spy(space, mid):
            seen.append((space['id'], spaces.request_space_id()))
            return real(space, mid)
        with mock.patch.object(dm, 'check', spy):
            self.post('/api/module-check', {'space': 'on', 'id': 'css-tokens'})
            self.post('/api/module-check', {'id': 'css-tokens'})
        self.assertEqual(seen, [('on', 'on'), ('off', 'off')])

    def test_an_unknown_space_is_404_on_every_route(self):
        for want in ('ghost', 5, '', ['off']):
            for r in ROUTES_POST:
                with self.subTest(route=r, space=want):
                    st, body = self.post(r, {'space': want, 'id': 'css-tokens'})
                    self.refused(st, body, 404, 'unknown-space')
        for r in ROUTES_GET:
            st, body = self.get(r + '?space=ghost')
            self.refused(st, body, 404, 'unknown-space')

    def test_a_lone_surrogate_is_a_json_404_not_a_dropped_connection(self):
        """`{"space": "\\ud800"}` — валідний JSON, а в Python це рядок, що не кодується в UTF-8: текст відмови
        з ним раніше валив `_send_json` (`ensure_ascii=False` + `.encode()`), і зʼєднання рвалось без відповіді. Тепер
        — звичайна JSON-відмова (екранована); наявний маршрут просторів — теж."""
        for route, payload, code in (('/api/module-check', {'space': '\ud800'}, 'unknown-space'),
                                     ('/api/module-check', {'id': '\ud800'}, 'unknown-module'),
                                     ('/api/module-enable', {'id': '\ud800'}, 'unknown-module'),
                                     ('/api/space-switch', {'id': '\ud800'}, 'unknown-space')):
            with self.subTest(route=route, payload=payload):
                st, body = self.post(route, payload)
                self.refused(st, body, 404, code)
                self.assertIn('\ud800', body['error'])
        st, body = self.get('/api/modules?space=%ED%A0%80')       # у query сурогат не виживає, але маршрут тримається
        self.assertEqual(st, 404)

    def test_ordinary_responses_stay_raw_utf8(self):
        """Запасний шлях `_send_json` (екранування) — лише для відмови кодування; решта відповідей — як і була,
        з живою кирилицею, байт у байт."""
        st, body = self.get('/api/modules')
        self.assertEqual(st, 200)
        raw = self.raw[-1][2]
        self.assertIn('Токени з CSS', raw)
        self.assertNotIn('\\u0422', raw)

    def test_a_blank_query_space_means_the_default(self):
        st, body = self.get('/api/modules?space=')
        self.assertEqual(st, 200, body)

    def test_a_machine_without_spaces_has_no_space_to_ask_about(self):
        atomic_write_json(os.path.join(self.deai, 'spaces.json'), {'version': 1, 'current': None, 'spaces': []})
        for r in ROUTES_GET:
            st, body = self.get(r)
            self.refused(st, body, 404, 'unknown-space')
        st, body = self.post('/api/module-check', {'id': 'css-tokens'})
        self.refused(st, body, 404, 'unknown-space')


# ================================================================================================== GET /api/modules

class Listing(World):

    def test_the_shape_of_an_untouched_module(self):
        self.assertEqual(self.entry('css-tokens'), {
            'id': 'css-tokens', 'name': 'Токени з CSS', 'version': '1.0.0', 'api': 1, 'roles': ['tokens'],
            'builtin': True, 'enabled': False, 'implicit': False, 'status': 'unchecked',
            'settings': [{'key': 'file', 'type': 'path', 'label': 'CSS-файл із токенами дизайн-системи',
                          'required': True}]})

    def test_the_implicit_publisher_and_its_secret_setting(self):
        e = self.entry('static-publish')
        self.assertEqual((e['enabled'], e['implicit'], e['status'], e['roles']), (True, True, 'unchecked', ['publish']))
        folder, password = e['settings']
        self.assertEqual(folder, {'key': 'folder', 'type': 'path', 'label': 'Тека для превʼю', 'required': True,
                                  'value': '{home}/deai-published/{space_id}'})      # символьне, не підставлене
        self.assertEqual(password, {'key': 'password', 'type': 'secret',
                                    'label': 'Пароль превʼю (необовʼязково)', 'required': False, 'set': False})
        self.assertNotIn('last_check', e)
        self.assertNotIn('error', e)

    def test_the_listing_is_alphabetical_and_has_nothing_else(self):
        st, body = self.get('/api/modules')
        self.assertEqual((st, list(body)), (200, ['modules']))
        self.assertEqual([m['id'] for m in body['modules']], BUILTIN_IDS)

    def test_a_secret_is_never_listed_only_whether_it_is_set(self):
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish',
                                                    'settings': {'folder': '{home}/pub/{space_id}'},
                                                    'secrets': {'password': SECRET}})
        self.assertEqual(st, 200, body)
        pw = self.entry('static-publish', 'on')['settings'][1]
        self.assertEqual(pw, {'key': 'password', 'type': 'secret', 'label': 'Пароль превʼю (необовʼязково)',
                              'required': False, 'set': True})
        self.assert_never_seen(SECRET)
        self.assertIn(SECRET, _read(self.secrets_path).decode('utf-8'))     # він записаний — просто не віддається

    def test_an_empty_secret_does_not_count_as_set(self):
        st, body = self.post('/api/module-settings', {'space': 'on', 'id': 'static-publish',
                                                      'secrets': {'password': ''}})
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(_json(self.secrets_path), {'on': {'static-publish': {'password': ''}}})   # записано, але не «задано»
        self.assertIs(self.entry('static-publish', 'on')['settings'][1]['set'], False)

    def test_the_select_options_and_bool_values_pass_through(self):
        self.modules(extra=('vault',))
        v = self.entry('vault')
        mode = next(s for s in v['settings'] if s['key'] == 'mode')
        self.assertEqual(mode, {'key': 'mode', 'type': 'select', 'label': 'Mode', 'required': False,
                                'value': 'echo', 'options': [{'value': 'echo', 'label': 'Echo'},
                                                             {'value': 'boom', 'label': 'Boom'}]})

    def test_missing_an_enabled_module_that_is_not_in_the_catalog(self):
        sj = self.sj()
        sj['modules'] = {'gone-mod': {'enabled': True, 'settings': {'x': 1}}, 'also-gone': {'enabled': False}}
        _write(os.path.join(self.off_path, 'space.json'), json.dumps(sj))
        mods = self.listing()
        self.assertEqual(sorted(mods), sorted([*BUILTIN_IDS, 'gone-mod']))    # вимкнений відсутній — без запису
        self.assertEqual(mods['gone-mod'], {
            'id': 'gone-mod', 'name': 'gone-mod', 'version': '', 'api': None, 'roles': [], 'builtin': False,
            'enabled': True, 'implicit': False, 'status': 'missing', 'settings': [],
            'error': 'module is not installed on this machine'})
        # постачальником він не є: на каталозі це не відбилось
        st, body = self.get('/api/task')
        self.assertEqual(body['space']['capabilities'], {'publish': 'static-publish', 'tokens': None, 'comments': None})

    def test_a_module_that_did_not_load_is_error_with_its_text(self):
        self.modules(extra=('broken',))
        e = self.entry('broken')
        self.assertEqual((e['status'], e['enabled']), ('error', False))
        self.assertIn('SyntaxError', e['error'])
        self.assertNotIn('last_check', e)

    def test_status_follows_the_last_check(self):
        self.modules(extra=('fail-check',), copy=())
        self.assertEqual(self.entry('fail-check')['status'], 'unchecked')
        st, body = self.post('/api/module-check', {'id': 'fail-check'})
        self.assertEqual((st, body['check']), (200, {'ok': False, 'error': 'nope', 'detail': 'because'}))
        e = self.entry('fail-check')
        self.assertEqual((e['status'], e['error'], e['last_check']),
                         ('error', 'nope', {'ok': False, 'error': 'nope', 'detail': 'because'}))

    def test_status_ok_after_a_good_check_and_it_is_per_space(self):
        self.enable_tokens()
        e = self.entry('css-tokens')
        self.assertEqual((e['status'], e['last_check']), ('ok', {'ok': True, 'detail': '2 tokens'}))
        self.assertNotIn('error', e)
        self.assertEqual(self.entry('css-tokens', 'on')['status'], 'unchecked')    # інший простір — свій стан

    def test_an_unreadable_space_json_is_409(self):
        _write(os.path.join(self.off_path, 'space.json'), '{not json')
        st, body = self.get('/api/modules')
        self.refused(st, body, 409, 'space-json-unreadable')

    def test_an_unreadable_secrets_file_marks_the_module_instead_of_hiding_the_listing(self):
        _write(self.secrets_path, '{not json')
        e = self.entry('static-publish')
        self.assertEqual((e['status'], e['error']), ('error', 'secrets-unreadable'))
        self.assertIsNone(e['settings'][1]['set'])                      # «невідомо», а не «не задано»
        self.assertEqual(self.entry('css-tokens')['status'], 'unchecked')    # модуль без секретів не зачеплено


# ================================================================================================== module-enable

class Enable(World):

    def test_enable_css_tokens_writes_the_symbolic_setting_and_checks(self):
        self.css()
        before = self.sj()
        st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '{space}/ds.css'}})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['ok'], True)
        self.assertEqual(body['check'], {'ok': True, 'detail': '2 tokens'})
        m = body['module']
        self.assertEqual((m['id'], m['enabled'], m['implicit'], m['status'], m['last_check']),
                         ('css-tokens', True, False, 'ok', {'ok': True, 'detail': '2 tokens'}))
        self.assertEqual(m['settings'], [{'key': 'file', 'type': 'path', 'required': True,
                                          'label': 'CSS-файл із токенами дизайн-системи',
                                          'value': '{space}/ds.css'}])
        after = self.sj()
        self.assertEqual(after['modules'], {'css-tokens': {'enabled': True, 'settings': {'file': '{space}/ds.css'}}})
        self.assertEqual({k: v for k, v in after.items() if k != 'modules'}, before)    # решта файла живе
        self.assertEqual(self.entry('css-tokens'), m)                    # і в списку те саме

    def test_a_check_that_says_no_is_a_verdict_not_a_failure(self):
        st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '{space}/none.css'}})
        self.assertEqual((st, body['ok']), (200, True))                  # запис відбувся
        self.assertEqual(body['check'], {'ok': False, 'error': 'file: not found'})
        self.assertEqual((body['module']['enabled'], body['module']['status']), (True, 'error'))

    def test_a_required_setting_that_is_missing_is_an_in_band_bad_settings_check(self):
        st, body = self.post('/api/module-enable', {'id': 'css-tokens'})
        self.assertEqual((st, body['ok']), (200, True))
        self.assertEqual(body['check'], {'ok': False, 'error': 'bad-settings', 'detail': 'file: required'})
        self.assertEqual((body['module']['enabled'], body['module']['status'], body['module']['error']),
                         (True, 'error', 'bad-settings'))
        self.assertTrue(self.sj()['modules']['css-tokens']['enabled'])

    def test_a_coded_error_of_the_module_itself_is_a_verdict_after_the_state_was_written(self):
        """Свій `ctx['ModuleError']('bad-folder', …)` з `check`: стан уже записано, тож це вердикт (200), а не 409."""
        self.modules(extra=('bad-folder',), copy=())
        for route in ('/api/module-enable', '/api/module-settings', '/api/module-check'):
            with self.subTest(route=route):
                st, body = self.post(route, {'id': 'bad-folder'})
                self.assertEqual((st, body['ok']), (200, True), body)
                self.assertEqual(body['check'], {'ok': False, 'error': 'bad-folder', 'detail': 'path-system'})
        e = self.entry('bad-folder')
        self.assertEqual((e['enabled'], e['status'], e['error']), (True, 'error', 'bad-folder'))

    def test_enabling_twice_is_fine(self):
        self.enable_tokens()
        st, body = self.post('/api/module-enable', {'id': 'css-tokens'})
        self.assertEqual((st, body['ok'], body['check']['ok']), (200, True, True))       # налаштування лишились

    def test_unknown_module_is_404(self):
        for mid in ('ghost', '', 5, None, ['css-tokens']):
            with self.subTest(id=mid):
                payload = {} if mid is None else {'id': mid}
                st, body = self.post('/api/module-enable', payload)
                self.refused(st, body, 404, 'unknown-module')
        self.assertNotIn('modules', self.sj())

    def test_bad_settings_are_400_and_write_nothing(self):
        before = self.sj_bytes()
        for what, settings in (('wrong type', {'file': 5}), ('unknown key', {'nope': 'x'}), ('not an object', [])):
            with self.subTest(what=what):
                st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': settings})
                self.refused(st, body, 400, 'bad-settings')
        self.assertEqual(self.sj_bytes(), before)

    def test_a_secret_cannot_go_through_the_settings_and_a_setting_cannot_go_through_the_secrets(self):
        st, body = self.post('/api/module-enable', {'id': 'static-publish', 'settings': {'password': SECRET}})
        self.refused(st, body, 400, 'bad-settings')
        st, body = self.post('/api/module-enable', {'id': 'static-publish', 'secrets': {'folder': 'x'}})
        self.refused(st, body, 400, 'bad-settings')
        st, body = self.post('/api/module-enable', {'id': 'static-publish', 'secrets': []})
        self.refused(st, body, 400, 'bad-settings')
        st, body = self.post('/api/module-enable', {'id': 'static-publish', 'secrets': {'password': 5}})
        self.refused(st, body, 400, 'bad-settings')
        self.assertFalse(os.path.exists(self.secrets_path))
        self.assert_never_seen(SECRET)

    def test_bad_settings_do_not_leave_the_secret_written(self):
        """Відмова налаштувань — ДО запису секрету: клієнт, що отримав 400, не мусить мати змінений пароль."""
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish',
                                                    'settings': {'folder': 5}, 'secrets': {'password': SECRET}})
        self.refused(st, body, 400, 'bad-settings')
        self.assertFalse(os.path.exists(self.secrets_path))
        self.assertNotIn('modules', self.sj(self.on))

    def test_role_taken_409_and_the_state_is_untouched(self):
        self.modules(extra=('alt-publish',))
        before = self.sj_bytes()
        st, body = self.post('/api/module-enable', {'id': 'alt-publish'})        # `off`: static-publish тримає `publish` неявно
        self.refused(st, body, 409, 'role-taken')
        self.assertIn('static-publish', body['error'])
        self.assertEqual(self.sj_bytes(), before)
        # у просторі з інтеграціями роль вільна; друге вмикання — знову role-taken
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'alt-publish'})
        self.assertEqual((st, body['ok'], body['check']), (200, True, {'ok': True}))
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish'})
        self.refused(st, body, 409, 'role-taken')
        self.assertIn('alt-publish', body['error'])
        # вимкнути перший — роль знову вільна
        self.assertEqual(self.post('/api/module-disable', {'space': 'on', 'id': 'alt-publish'})[0], 200)
        self.assertEqual(self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish'})[0], 200)

    def test_a_module_that_did_not_load_can_be_enabled_but_its_check_says_why(self):
        self.modules(extra=('broken',))
        st, body = self.post('/api/module-enable', {'id': 'broken'})
        self.assertEqual((st, body['ok'], body['check']['ok'], body['check']['error']), (200, True, False, 'module-error'))
        self.assertIn('SyntaxError', body['check']['detail'])
        self.assertEqual((body['module']['enabled'], body['module']['status']), (True, 'error'))

    def test_unreadable_space_json_is_409_and_the_file_is_not_overwritten(self):
        _write(os.path.join(self.off_path, 'space.json'), '{not json')
        st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': 'x.css'}})
        self.refused(st, body, 409, 'space-json-unreadable')
        self.assertEqual(self.sj_bytes(), b'{not json')

    def test_check_timeout_is_an_in_band_verdict(self):
        self.modules(extra=('slow',), copy=())
        with mock.patch.object(dm, 'CHECK_TIMEOUT', 0.2):
            st, body = self.post('/api/module-enable', {'id': 'slow'})
        self.assertEqual((st, body['ok']), (200, True))
        self.assertEqual((body['check']['ok'], body['check']['error']), (False, 'check-timeout'))
        self.assertEqual(self.entry('slow')['status'], 'error')

    def test_secrets_are_scrubbed_from_what_a_module_echoes_or_raises(self):
        self.modules(extra=('vault',), copy=())
        st, body = self.post('/api/module-enable', {'id': 'vault', 'secrets': {'token': SECRET}})
        self.assertEqual((st, body['check']), (200, {'ok': True, 'detail': 'token ***'}))
        st, body = self.post('/api/module-settings', {'id': 'vault', 'settings': {'mode': 'boom'}})
        self.assertEqual((st, body['check']['error'], body['check']['ok']), (200, 'module-error', False))
        self.assertIn('bad token ***', body['check']['detail'])
        self.assertEqual(self.entry('vault')['status'], 'error')
        self.assert_never_seen(SECRET)

    def test_secrets_are_written_with_private_permissions(self):
        self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish', 'secrets': {'password': SECRET}})
        self.assertEqual(stat.S_IMODE(os.stat(self.secrets_path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.deai).st_mode), 0o700)
        self.assertEqual(_json(self.secrets_path), {'on': {'static-publish': {'password': SECRET}}})
        self.assertNotIn(SECRET, self.sj_bytes(self.on).decode('utf-8'))     # у space.json секрету нема

    def test_the_order_is_secrets_then_state_then_check(self):
        calls = []

        def spy(name):
            real = getattr(dm, name)

            def wrapper(*a, **kw):
                calls.append(name)
                return real(*a, **kw)
            return wrapper
        with mock.patch.object(dm, 'write_secrets', spy('write_secrets')), \
                mock.patch.object(dm, 'write_module_state', spy('write_module_state')), \
                mock.patch.object(dm, 'check', spy('check')):
            st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish',
                                                        'secrets': {'password': SECRET}})
        self.assertEqual(st, 200, body)
        self.assertEqual(calls, ['write_secrets', 'write_module_state', 'check'])

    def test_a_secret_that_cannot_be_written_stops_the_enabling(self):
        """Увімкнений модуль без секрету — гірше за сирітський секрет: невдалий запис секрету — ДО `space.json`."""
        boom = dm.ModuleError('unwritable', message='secrets.json: OSError')
        before = self.sj_bytes(self.on)
        with mock.patch.object(dm, 'write_secrets', side_effect=boom):
            st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish',
                                                        'secrets': {'password': SECRET}})
        self.refused(st, body, 500, 'unwritable')
        self.assertEqual(self.sj_bytes(self.on), before)

    def test_an_unreadable_secrets_file_refuses_a_secret_write_before_the_state(self):
        _write(self.secrets_path, '{not json')
        before = self.sj_bytes(self.on)
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish',
                                                    'secrets': {'password': SECRET}})
        self.refused(st, body, 409, 'secrets-unreadable')
        self.assertEqual(self.sj_bytes(self.on), before)
        self.assertEqual(_read(self.secrets_path), b'{not json')            # зіпсований файл не перезаписано
        self.assert_never_seen(SECRET)

    def test_an_unreadable_secrets_file_is_a_verdict_when_the_body_has_no_secrets(self):
        """Стан записано, `check` не міг прочитати секрети — це вердикт модуля, а не 409 «нічого не змінилось»."""
        _write(self.secrets_path, '{not json')
        for route in ('/api/module-enable', '/api/module-settings', '/api/module-check'):
            with self.subTest(route=route):
                st, body = self.post(route, {'space': 'on', 'id': 'static-publish'})
                self.assertEqual((st, body['ok'], body['check']['ok'], body['check']['error']),
                                 (200, True, False, 'secrets-unreadable'), body)
        self.assertTrue(self.sj(self.on)['modules']['static-publish']['enabled'])

    def test_without_secrets_in_the_body_the_secrets_are_not_touched(self):
        with mock.patch.object(dm, 'write_secrets') as ws:
            st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish'})
        self.assertEqual(st, 200, body)
        ws.assert_not_called()
        self.assertFalse(os.path.exists(self.secrets_path))


class Replace(World):
    """`replace: true` у `module-enable`: ролі цього модуля звільняються в ТОМУ САМОМУ записі `space.json`."""

    def test_replace_takes_the_role_from_the_implicit_static_publish_in_one_write(self):
        self.modules(extra=('alt-publish',))
        writes = []
        real = spaces._write_public

        def spy(path, data):
            writes.append((path, json.loads(json.dumps(data))))
            return real(path, data)

        with mock.patch.object(spaces, '_write_public', spy):
            st, body = self.post('/api/module-enable', {'id': 'alt-publish', 'replace': True})
        self.assertEqual((st, body['ok'], body['check']), (200, True, {'ok': True}), body)
        self.assertEqual(body['replaced'], ['static-publish'])
        mods = self.sj()['modules']
        self.assertEqual(mods['static-publish'], {'enabled': False})
        self.assertEqual(mods['alt-publish'], {'enabled': True})
        sj_writes = [w for w in writes if w[0].endswith('space.json')]
        self.assertEqual(len(sj_writes), 1, 'обидві зміни — одним записом файла')
        self.assertEqual(sj_writes[0][1]['modules']['static-publish']['enabled'], False)
        self.assertEqual(sj_writes[0][1]['modules']['alt-publish']['enabled'], True)
        listing = self.listing()
        self.assertEqual((listing['static-publish']['enabled'], listing['alt-publish']['enabled']), (False, True))

    def test_replace_keeps_the_settings_of_the_replaced_module(self):
        self.modules(extra=('alt-publish',))
        st, body = self.post('/api/module-settings', {'id': 'static-publish', 'settings': {'folder': '{home}/pv'}})
        self.assertEqual(st, 200, body)
        st, body = self.post('/api/module-enable', {'id': 'alt-publish', 'replace': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.sj()['modules']['static-publish'], {'enabled': False, 'settings': {'folder': '{home}/pv'}})

    def test_replace_takes_the_role_from_an_explicit_holder_too(self):
        self.modules(extra=('alt-publish',))
        st, _ = self.post('/api/module-enable', {'space': 'on', 'id': 'alt-publish'})
        self.assertEqual(st, 200)
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish', 'replace': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['replaced'], ['alt-publish'])
        mods = self.sj(self.on)['modules']
        self.assertEqual((mods['alt-publish']['enabled'], mods['static-publish']['enabled']), (False, True))

    def test_replace_without_a_conflict_answers_an_empty_list(self):
        self.css()
        st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '{space}/ds.css'},
                                                    'replace': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['replaced'], [])

    def test_no_replace_key_in_the_answer_without_replace(self):
        self.css()
        st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '{space}/ds.css'}})
        self.assertEqual(st, 200, body)
        self.assertNotIn('replaced', body)

    def test_without_replace_the_role_is_still_taken(self):
        self.modules(extra=('alt-publish',))
        before = self.sj_bytes()
        for payload in ({'id': 'alt-publish'}, {'id': 'alt-publish', 'replace': False}):
            with self.subTest(payload=payload):
                st, body = self.post('/api/module-enable', payload)
                self.refused(st, body, 409, 'role-taken')
        self.assertEqual(self.sj_bytes(), before)

    def test_replace_must_be_a_boolean_and_nothing_is_written(self):
        self.modules(extra=('alt-publish',))
        before = self.sj_bytes()
        for bad in ('yes', 1, None, [], {}):
            with self.subTest(replace=bad):
                st, body = self.post('/api/module-enable', {'id': 'alt-publish', 'replace': bad,
                                                            'secrets': {'token': SECRET}})
                self.refused(st, body, 400, 'bad-settings')
        self.assertEqual(self.sj_bytes(), before)
        self.assertFalse(os.path.exists(self.secrets_path), 'відмова replace — ДО запису секрету')
        self.assert_never_seen(SECRET)

    def test_replace_is_ignored_by_the_other_routes(self):
        """`replace` має сенс лише в `module-enable`: на `settings` і `disable` ключ мовчки ігнорується — і `True`, і
        нетиповий (`None`, `'x'`: помилкою він є лише там, де його читають)."""
        self.modules(extra=('alt-publish',))
        for bad in (True, None, 'x'):
            with self.subTest(route='settings', replace=bad):
                st, body = self.post('/api/module-settings', {'id': 'alt-publish', 'settings': {'note': 'x'},
                                                              'replace': bad})
                self.assertEqual(st, 200, body)
                self.assertNotIn('replaced', body)
        self.assertNotIn('static-publish', self.sj()['modules'], 'settings не вмикає і не замінює')
        listing = self.listing()
        self.assertEqual((listing['static-publish']['enabled'], listing['alt-publish']['enabled']), (True, False))
        for bad in (True, None, 'x'):
            with self.subTest(route='disable', replace=bad):
                st, body = self.post('/api/module-disable', {'id': 'static-publish', 'replace': bad})
                self.assertEqual(st, 200, body)
                self.assertNotIn('replaced', body)
        listing = self.listing()
        self.assertEqual((listing['static-publish']['enabled'], listing['alt-publish']['enabled']), (False, False),
                         'disable вимикає лише названий модуль')

    def test_preflight_with_replace_does_not_refuse(self):
        self.modules(extra=('alt-publish',))
        dm.preflight(self.off, 'alt-publish', enabling=True, replace=True)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.preflight(self.off, 'alt-publish', enabling=True)
        self.assertEqual(cm.exception.code, 'role-taken')

    def test_write_module_state_reports_what_it_replaced(self):
        self.modules(extra=('alt-publish',))
        st = dm.write_module_state(self.off, 'alt-publish', enabled=True, replace=True)
        self.assertEqual(st['replaced'], ['static-publish'])
        st = dm.write_module_state(self.off, 'alt-publish', enabled=True)
        self.assertNotIn('replaced', st)

    # ---- краї ----

    def test_a_non_object_entry_of_the_holder_does_not_crash_and_ends_sane(self):
        """Запис `static-publish` у `space.json` — не обʼєкт: `_normalize` його пропускає, неявний типовий лишається
        постачальником, `replace` перезаписує запис нормальним `{enabled: false}`."""
        self.modules(extra=('alt-publish',))
        data = self.sj()
        data['modules'] = {'static-publish': 'x'}
        _write(os.path.join(self.off_path, 'space.json'), json.dumps(data))
        st, body = self.post('/api/module-enable', {'id': 'alt-publish', 'replace': True})
        self.assertEqual((st, body['ok'], body['replaced']), (200, True, ['static-publish']), body)
        self.assertEqual(self.sj()['modules'], {'static-publish': {'enabled': False}, 'alt-publish': {'enabled': True}})
        listing = self.listing()
        self.assertEqual((listing['static-publish']['enabled'], listing['alt-publish']['enabled']), (False, True))

    def test_replace_in_the_space_with_integrations_takes_the_role_from_an_explicit_static_publish(self):
        self.modules(extra=('alt-publish',))
        st, _ = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish'})
        self.assertEqual(st, 200)
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'alt-publish', 'replace': True})
        self.assertEqual((st, body['ok'], body['replaced']), (200, True, ['static-publish']), body)
        mods = self.sj(self.on)['modules']
        self.assertEqual((mods['static-publish']['enabled'], mods['alt-publish']['enabled']), (False, True))

    # ---- ціль, що не завантажилась ----

    def test_replace_onto_a_module_that_did_not_load_is_refused_and_nothing_changes(self):
        """Модуль із дійсним манифестом, але зламаним `server.py`, ТРИМАЄ свої ролі (`status: error`, а не «нема»):
        заміна на нього вимкнула б робочого постачальника, лишивши роль без виконавця. Відмова — ДО секрету й до
        `space.json`; код — `error_code` модуля (`module-error` 502 / `bad-manifest` 500)."""
        self.modules(extra=('broken-publish', 'headless-publish'))
        before = self.sj_bytes()
        for mid, status, code in (('broken-publish', 502, 'module-error'), ('headless-publish', 500, 'bad-manifest')):
            with self.subTest(module=mid):
                self.assertEqual(self.entry(mid)['status'], 'error')
                st, body = self.post('/api/module-enable', {'id': mid, 'replace': True, 'secrets': {'token': SECRET}})
                self.refused(st, body, status, code)
                self.assertIn('cannot replace with a module that did not load', body['error'])
                self.assertEqual(self.sj_bytes(), before)
                self.assertFalse(os.path.exists(self.secrets_path), 'відмова — ДО запису секрету')
                self.assertEqual(dm.provider('publish', self.off).id, 'static-publish')
                self.assertTrue(self.entry('static-publish')['enabled'])
        self.assert_never_seen(SECRET)

    def test_the_refusal_is_in_preflight_and_again_in_write_module_state(self):
        """Дві межі: пре-перевірка (до секрету) і запис під локом (гонка: каталог міг змінитись між ними)."""
        self.modules(extra=('broken-publish',))
        before = self.sj_bytes()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.preflight(self.off, 'broken-publish', enabling=True, replace=True)
        self.assertEqual(cm.exception.code, 'module-error')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(self.off, 'broken-publish', enabled=True, replace=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('module-error', 502))
        self.assertEqual(self.sj_bytes(), before)

    def test_enabling_a_module_that_did_not_load_without_replace_is_unchanged(self):
        """Без `replace` усе як було: вільна роль — вмикається (а `check` каже, чому не працює), зайнята — `role-taken`."""
        self.modules(extra=('broken-publish',))
        st, body = self.post('/api/module-enable', {'id': 'broken-publish'})
        self.refused(st, body, 409, 'role-taken')                       # static-publish тримає `publish`
        st, body = self.post('/api/module-disable', {'id': 'static-publish'})
        self.assertEqual(st, 200, body)
        st, body = self.post('/api/module-enable', {'id': 'broken-publish'})
        self.assertEqual((st, body['ok'], body['check']['ok'], body['module']['enabled']), (200, True, False, True))

    # ---- гонка двох замін ----

    def _race(self, first, second):
        """Два ПАРАЛЕЛЬНІ `module-enable` із `replace` (по одному на модуль). Порядок детермінований: обидва запити
        спершу ДОХОДЯТЬ до `WRITE_LOCK` (уся робота до локу — каталог, пре-перевірка, будь-яке читання `space.json` —
        вже зроблена), а далі `first` бере лок раніше за `second`. Тому читання «хто тримає роль» до локу дало б
        застаріле знання: правильна реалізація дивиться на файл під локом."""
        arrived = threading.Barrier(2, timeout=15)
        first_done = threading.Event()
        mine = threading.local()
        real_lock, real_write = spaces.WRITE_LOCK, dm.write_module_state
        test = self

        def tagged(space, module_id, *a, **kw):
            mine.mid = module_id                                       # який модуль пише ЦЕЙ потік
            return real_write(space, module_id, *a, **kw)

        class Gate:
            def __enter__(self):
                mid = getattr(mine, 'mid', None)
                if mid is not None and not getattr(mine, 'passed', False):
                    mine.passed = True
                    arrived.wait()
                    if mid != first:
                        test.assertTrue(first_done.wait(15), 'перший запис не завершився')
                real_lock.acquire()

            def __exit__(self, *exc):
                real_lock.release()
                if getattr(mine, 'mid', None) == first:
                    first_done.set()
                return False

        out = {}

        def call(mid):
            out[mid] = self.post('/api/module-enable', {'id': mid, 'replace': True})

        threads = [threading.Thread(target=call, args=(mid,)) for mid in (first, second)]
        with mock.patch.object(dm, 'write_module_state', tagged), mock.patch.object(spaces, 'WRITE_LOCK', Gate()):
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
        self.assertFalse(any(t.is_alive() for t in threads), 'запит завис')
        for mid in (first, second):
            self.assertEqual((out[mid][0], out[mid][1].get('ok')), (200, True), out[mid])
        mods = self.sj()['modules']
        on = [mid for mid in ('alt-publish', 'static-publish') if mods.get(mid, {}).get('enabled') is True]
        self.assertEqual(len(on), 1, f'рівно один постачальник `publish`, а в файлі {mods}')
        listing = self.listing()
        self.assertEqual(sorted(mid for mid in ('alt-publish', 'static-publish') if listing[mid]['enabled']), on)
        self.assertEqual(dm.provider('publish', self.off).id, on[0])
        return out

    def test_two_parallel_replaces_leave_exactly_one_provider_alt_publish_goes_first(self):
        self.modules(extra=('alt-publish',))
        out = self._race('alt-publish', 'static-publish')
        self.assertEqual(out['alt-publish'][1]['replaced'], ['static-publish'])
        self.assertEqual(out['static-publish'][1]['replaced'], ['alt-publish'])

    def test_two_parallel_replaces_leave_exactly_one_provider_static_publish_goes_first(self):
        self.modules(extra=('alt-publish',))
        out = self._race('static-publish', 'alt-publish')
        self.assertEqual(out['static-publish'][1]['replaced'], [])
        self.assertEqual(out['alt-publish'][1]['replaced'], ['static-publish'])


# ================================================================================================= disable / settings

class DisableAndSettings(World):

    def test_disable_keeps_settings_and_secrets_and_enable_brings_them_back(self):
        self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish',
                                         'settings': {'folder': '{home}/pub/{space_id}'},
                                         'secrets': {'password': SECRET}})
        st, body = self.post('/api/module-disable', {'space': 'on', 'id': 'static-publish'})
        self.assertEqual((st, body['ok']), (200, True))
        self.assertNotIn('check', body)
        m = body['module']
        self.assertEqual((m['enabled'], m['implicit']), (False, False))
        self.assertEqual(self.sj(self.on)['modules']['static-publish'],
                         {'enabled': False, 'settings': {'folder': '{home}/pub/{space_id}'}})
        self.assertEqual(_json(self.secrets_path), {'on': {'static-publish': {'password': SECRET}}})
        self.assertEqual(m['settings'][0]['value'], '{home}/pub/{space_id}')
        self.assertIs(m['settings'][1]['set'], True)
        # повторне вмикання — без налаштувань у тілі — повертає їх
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish'})
        self.assertEqual(st, 200, body)
        m = body['module']
        self.assertEqual((m['enabled'], m['settings'][0]['value'], m['settings'][1]['set']),
                         (True, '{home}/pub/{space_id}', True))
        self.assert_never_seen(SECRET)

    def test_disable_ignores_settings_and_secrets_in_the_body(self):
        self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish', 'secrets': {'password': SECRET}})
        self.post('/api/module-disable', {'space': 'on', 'id': 'static-publish', 'settings': {'folder': 'x'},
                                          'secrets': {'password': None}})
        self.assertEqual(_json(self.secrets_path), {'on': {'static-publish': {'password': SECRET}}})
        self.assertNotIn('settings', self.sj(self.on)['modules']['static-publish'])

    def test_disabling_the_implicit_publisher_makes_the_decision_explicit(self):
        st, body = self.get('/api/task')
        self.assertEqual(body['space']['capabilities']['publish'], 'static-publish')
        st, body = self.post('/api/module-disable', {'id': 'static-publish'})
        self.assertEqual((st, body['module']['enabled'], body['module']['implicit']), (200, False, False))
        self.assertEqual(self.sj()['modules'], {'static-publish': {'enabled': False}})
        st, body = self.get('/api/task')
        self.assertEqual(body['space']['capabilities'], {'publish': None, 'tokens': None, 'comments': None})

    def test_disable_unknown_module_is_404_and_a_disabled_one_is_still_fine(self):
        st, body = self.post('/api/module-disable', {'id': 'ghost'})
        self.refused(st, body, 404, 'unknown-module')
        st, body = self.post('/api/module-disable', {'id': 'css-tokens'})        # ще не вмикали
        self.assertEqual((st, body['module']['enabled']), (200, False))

    def test_settings_patch_check_and_removal_by_null(self):
        self.enable_tokens()
        self.css(':root{--a:1}', 'other.css')
        st, body = self.post('/api/module-settings', {'id': 'css-tokens', 'settings': {'file': '{space}/other.css'}})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['ok'], body['check']), (True, {'ok': True, 'detail': '1 tokens'}))
        self.assertEqual(self.sj()['modules']['css-tokens'],
                         {'enabled': True, 'settings': {'file': '{space}/other.css'}})
        st, body = self.post('/api/module-settings', {'id': 'css-tokens', 'settings': {'file': None}})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['check'], {'ok': False, 'error': 'bad-settings', 'detail': 'file: required'})
        self.assertEqual(self.sj()['modules']['css-tokens'], {'enabled': True, 'settings': {}})

    def test_settings_do_not_enable_and_run_the_check_anyway(self):
        st, body = self.post('/api/module-settings', {'id': 'css-tokens', 'settings': {'file': '{space}/ds.css'}})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['module']['enabled'], body['check']['ok']), (False, False))   # файла нема
        self.assertEqual(self.sj()['modules']['css-tokens']['enabled'], False)

    def test_settings_on_the_implicit_publisher_keep_it_enabled(self):
        st, body = self.post('/api/module-settings', {'id': 'static-publish',
                                                      'settings': {'folder': '{home}/pub/{space_id}'}})
        self.assertEqual((st, body['module']['enabled']), (200, True))
        self.assertEqual(self.sj()['modules']['static-publish']['enabled'], True)

    def test_settings_secret_set_then_deleted_by_null(self):
        st, body = self.post('/api/module-settings', {'space': 'on', 'id': 'static-publish',
                                                      'secrets': {'password': SECRET}})
        self.assertEqual((st, body['module']['settings'][1]['set']), (200, True))
        st, body = self.post('/api/module-settings', {'space': 'on', 'id': 'static-publish',
                                                      'secrets': {'password': None}})
        self.assertEqual((st, body['module']['settings'][1]['set']), (200, False))
        self.assertEqual(_json(self.secrets_path), {})
        self.assert_never_seen(SECRET)

    def test_settings_nothing_to_write_still_answers(self):
        before = self.sj_bytes()
        st, body = self.post('/api/module-settings', {'id': 'css-tokens'})
        self.assertEqual((st, body['ok']), (200, True))
        self.assertEqual(self.sj_bytes(), before)

    def test_settings_refusals(self):
        st, body = self.post('/api/module-settings', {'id': 'ghost', 'settings': {}})
        self.refused(st, body, 404, 'unknown-module')
        st, body = self.post('/api/module-settings', {'id': 'css-tokens', 'settings': {'file': 5}})
        self.refused(st, body, 400, 'bad-settings')
        st, body = self.post('/api/module-settings', {'id': 'css-tokens', 'secrets': {'password': 'x'}})
        self.refused(st, body, 400, 'bad-settings')


class MissingModule(World):
    """Модуль, ЯВНО увімкнений у `space.json`, а на цій машині його нема (`status: missing`): його можна лише
    ВИМКНУТИ — інакше запис лишався б у списку назавжди (ядро кидало `unknown-module`, бо каталог його не знає)."""

    def put_modules(self, mods, space=None):
        sp = space or self.off
        sj = self.sj(sp)
        sj['modules'] = mods
        _write(os.path.join(sp['path'], 'space.json'), json.dumps(sj))

    def test_a_missing_module_can_be_disabled_and_is_no_longer_listed(self):
        self.put_modules({'gone-mod': {'enabled': True, 'settings': {'x': 1}}, 'other-gone': {'enabled': True}})
        self.assertEqual(self.entry('gone-mod')['status'], 'missing')
        before = self.sj()
        st, body = self.post('/api/module-disable', {'id': 'gone-mod'})
        # запису модуля вже нема в списку (вимкнений відсутній не показується) — `module: null` тут нормальний
        self.assertEqual((st, body), (200, {'ok': True, 'module': None}))
        after = self.sj()
        self.assertEqual(after['modules']['gone-mod'], {'enabled': False, 'settings': {'x': 1}})    # налаштування живуть
        self.assertEqual(after['modules']['other-gone'], {'enabled': True})                          # решта не зачеплена
        self.assertEqual({k: v for k, v in after.items() if k != 'modules'},
                         {k: v for k, v in before.items() if k != 'modules'})
        mods = self.listing()
        self.assertNotIn('gone-mod', mods)
        self.assertEqual(mods['other-gone']['status'], 'missing')
        # повторне вимкнення — так само нормальна відповідь
        self.assertEqual(self.post('/api/module-disable', {'id': 'gone-mod'}), (200, {'ok': True, 'module': None}))

    def test_an_id_that_is_not_in_the_file_is_still_404_and_nothing_is_written(self):
        self.put_modules({'gone-mod': {'enabled': True}, 'weird': 5})
        before = self.sj_bytes()
        for mid in ('ghost', 'weird', '', 5):
            with self.subTest(id=mid):
                st, body = self.post('/api/module-disable', {'id': mid})
                self.refused(st, body, 404, 'unknown-module')
        self.assertEqual(self.sj_bytes(), before)

    def test_only_the_disabling_is_open_to_a_missing_module(self):
        self.put_modules({'gone-mod': {'enabled': True}})
        before = self.sj_bytes()
        for route in ('/api/module-enable', '/api/module-settings', '/api/module-check'):
            with self.subTest(route=route):
                st, body = self.post(route, {'id': 'gone-mod'})
                self.refused(st, body, 404, 'unknown-module')
        # і саме `enabled=False` без налаштувань: патч налаштувань чи `enabled=True` — як було
        space = dict(self.off)
        for kw in ({'enabled': False, 'settings': {'x': 1}}, {'enabled': True}, {'settings': {'x': 1}}, {}):
            with self.subTest(core=kw):
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.write_module_state(space, 'gone-mod', **kw)
                self.assertEqual(cm.exception.code, 'unknown-module')
        self.assertEqual(self.sj_bytes(), before)

    def test_the_core_answer_for_a_missing_module(self):
        self.put_modules({'gone-mod': {'enabled': True, 'settings': {'x': 1}}})
        st = dm.write_module_state(dict(self.off), 'gone-mod', enabled=False)
        self.assertEqual(st, {'enabled': False, 'implicit': False, 'settings': {'x': 1}})
        self.assertEqual(self.sj()['modules']['gone-mod'], {'enabled': False, 'settings': {'x': 1}})

    def test_the_disabling_does_not_pass_role_taken_and_needs_no_role(self):
        """Вимкнення нічого не займає: ні `role-taken`, ні перевірки ролей (модуля в каталозі нема)."""
        self.put_modules({'gone-mod': {'enabled': True}, 'static-publish': {'enabled': True}})
        self.assertEqual(self.post('/api/module-disable', {'id': 'gone-mod'})[0], 200)
        self.assertTrue(self.entry('static-publish')['enabled'])

    def test_an_unreadable_space_json_is_409_not_404(self):
        _write(os.path.join(self.off_path, 'space.json'), '{not json')
        st, body = self.post('/api/module-disable', {'id': 'gone-mod'})
        self.refused(st, body, 409, 'space-json-unreadable')
        self.assertEqual(self.sj_bytes(), b'{not json')


class SecretPreflight(World):
    """Секрет пишеться РАНІШЕ за `space.json` (спека), тож усе, що можна знати до запису, перевіряється ДО нього
    (читання без запису): нечитабельна `space.json` і `role-taken`. Відмова після живого секрету — 409, а пароль
    уже новий; це якраз той випадок, який перевірка до запису закриває."""

    def seed_secret(self):
        self.post('/api/module-settings', {'space': 'on', 'id': 'static-publish', 'secrets': {'password': 'old-pw'}})
        return _read(self.secrets_path)

    def stops_the_secret(self, route):
        before_secrets = self.seed_secret()
        _write(os.path.join(self.on_path, 'space.json'), '{not json')
        st, body = self.post(route, {'space': 'on', 'id': 'static-publish', 'secrets': {'password': SECRET}})
        self.refused(st, body, 409, 'space-json-unreadable')
        self.assertEqual(_read(self.secrets_path), before_secrets)                  # пароль НЕ змінився (байт у байт)
        self.assertEqual(self.sj_bytes(self.on), b'{not json')
        self.assert_never_seen(SECRET)

    def test_an_unreadable_space_json_stops_a_secret_write_on_settings(self):
        self.stops_the_secret('/api/module-settings')

    def test_an_unreadable_space_json_stops_a_secret_write_on_enable(self):
        self.stops_the_secret('/api/module-enable')

    def test_an_unreadable_space_json_writes_no_secrets_file_at_all(self):
        _write(os.path.join(self.on_path, 'space.json'), '{not json')
        st, body = self.post('/api/module-settings', {'space': 'on', 'id': 'static-publish',
                                                      'secrets': {'password': SECRET}})
        self.refused(st, body, 409, 'space-json-unreadable')
        self.assertFalse(os.path.exists(self.secrets_path))

    def test_role_taken_is_known_before_the_secret_is_written(self):
        self.modules(extra=('alt-publish',))
        st, body = self.post('/api/module-enable', {'id': 'alt-publish', 'secrets': {'token': SECRET}})
        self.refused(st, body, 409, 'role-taken')                      # `off`: static-publish тримає `publish` неявно
        self.assertFalse(os.path.exists(self.secrets_path))
        self.assert_never_seen(SECRET)
        # у просторі з інтеграціями роль вільна — секрет пишеться
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'alt-publish', 'secrets': {'token': SECRET}})
        self.assertEqual(st, 200, body)
        self.assertEqual(_json(self.secrets_path), {'on': {'alt-publish': {'token': SECRET}}})

    def test_the_settings_of_a_module_that_stays_disabled_are_not_blocked_by_a_role_it_does_not_take(self):
        """Пре-перевірка `role-taken` — лише для вмикання: налаштування й секрет модуля, який вимкнений і НЕ вмикається
        (`static-publish` тримає `publish` у `off`), ролі не займають — 200, секрет записано, `enabled` лишився `false`."""
        self.modules(extra=('alt-publish',))
        st, body = self.post('/api/module-settings', {'id': 'alt-publish', 'secrets': {'token': SECRET}})
        self.assertEqual((st, body['ok'], body['module']['enabled']), (200, True, False), body)
        self.assertEqual(_json(self.secrets_path), {'off': {'alt-publish': {'token': SECRET}}})

    def test_a_readable_space_json_does_not_change_the_flow(self):
        st, body = self.post('/api/module-settings', {'space': 'on', 'id': 'static-publish',
                                                      'secrets': {'password': SECRET}})
        self.assertEqual((st, body['module']['settings'][1]['set']), (200, True))


class Check(World):

    def test_check_runs_and_is_remembered(self):
        self.css()
        sj = self.sj()
        sj['modules'] = {'css-tokens': {'enabled': True, 'settings': {'file': '{space}/ds.css'}}}   # мимо API: check не було
        _write(os.path.join(self.off_path, 'space.json'), json.dumps(sj))
        self.assertEqual(self.entry('css-tokens')['status'], 'unchecked')
        st, body = self.post('/api/module-check', {'id': 'css-tokens'})
        self.assertEqual((st, body['ok'], body['check']), (200, True, {'ok': True, 'detail': '2 tokens'}))
        self.assertEqual(body['module']['status'], 'ok')
        self.assertEqual(self.entry('css-tokens')['last_check'], {'ok': True, 'detail': '2 tokens'})

    def test_check_of_an_unknown_module_is_404(self):
        st, body = self.post('/api/module-check', {'id': 'ghost'})
        self.refused(st, body, 404, 'unknown-module')

    def test_a_broken_setting_and_a_timeout_and_a_load_error_are_verdicts(self):
        self.modules(extra=('slow', 'broken'))
        st, body = self.post('/api/module-check', {'id': 'css-tokens'})
        self.assertEqual((st, body['check']['error']), (200, 'bad-settings'))
        with mock.patch.object(dm, 'CHECK_TIMEOUT', 0.2):
            st, body = self.post('/api/module-check', {'id': 'slow'})
        self.assertEqual((st, body['check']['ok'], body['check']['error']), (200, False, 'check-timeout'))
        st, body = self.post('/api/module-check', {'id': 'broken'})
        self.assertEqual((st, body['check']['error']), (200, 'module-error'))
        self.assertIn('SyntaxError', body['check']['detail'])

    def test_unreadable_space_json_is_a_refusal_not_a_verdict(self):
        _write(os.path.join(self.off_path, 'space.json'), '{not json')
        st, body = self.post('/api/module-check', {'id': 'css-tokens'})
        self.refused(st, body, 409, 'space-json-unreadable')


# ============================================================================================== шар вимкнено

class LayerOff(Http, unittest.TestCase):
    """Лише `DC_TASKS_FILE` (без `DEAI_HOME`): шар просторів вимкнено — модулі нічого не пишуть, секрети теж."""

    def setUp(self):
        self.raw = []
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='dc-modapi-off-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, 'home')
        os.makedirs(self.home)
        env = mock.patch.dict(os.environ, {'HOME': self.home, 'DC_TASKS_FILE': os.path.join(self.tmp, 'tasks.json'),
                                           'DC_NO_OVERVIEW': '1'})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DEAI_HOME', None)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        self.assertFalse(spaces.layer_on())
        self.base = _serve(self)
        _no_network(self, int(self.base.rsplit(':', 1)[1]))

    def assert_nothing_written(self):
        self.assertEqual(sorted(os.listdir(self.home)), [], 'шар вимкнено, а на диск щось записано (~/.deai?)')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'tasks.json')))

    def test_every_write_is_409_spaces_off_and_nothing_hits_the_disk(self):
        for r, payload in (('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '/x.css'}}),
                           ('/api/module-enable', {'id': 'static-publish', 'secrets': {'password': SECRET}}),
                           ('/api/module-disable', {'id': 'css-tokens'}),
                           ('/api/module-settings', {'id': 'css-tokens', 'settings': {'file': '/x.css'}}),
                           ('/api/module-settings', {'id': 'static-publish', 'secrets': {'password': SECRET}})):
            with self.subTest(route=r, payload=sorted(payload)):
                st, body = self.post(r, payload)
                self.assertEqual((st, body['ok'], body['code']), (409, False, 'spaces-off'), body)
        self.assert_nothing_written()
        self.assert_never_seen(SECRET)

    def test_disabling_an_unknown_or_missing_id_is_spaces_off_before_anything_else(self):
        st, body = self.post('/api/module-disable', {'id': 'gone-mod'})
        self.assertEqual((st, body['code']), (409, 'spaces-off'), body)
        self.assert_nothing_written()

    def test_the_listing_and_the_check_still_answer(self):
        st, body = self.get('/api/modules')
        self.assertEqual(st, 200, body)
        mods = {m['id']: m for m in body['modules']}
        self.assertEqual((mods['css-tokens']['enabled'], mods['static-publish']['enabled']), (False, False))
        st, body = self.post('/api/module-check', {'id': 'css-tokens'})
        self.assertEqual((st, body['check']['error']), (200, 'bad-settings'))
        self.assert_nothing_written()

    def test_ds_tokens_and_the_listing_of_spaces_stay_as_they_were(self):
        self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None}))
        self.assertEqual(self.get('/api/spaces'), (200, {'current': None, 'spaces': [], 'off': True}))
        self.assertEqual(self.get('/api/ds-tokens?space=legacy'), (200, {'profile': None}))
        st, body = self.get('/api/modules?space=ghost')
        self.refused(st, body, 404, 'unknown-space')
        self.assert_nothing_written()


# ================================================================================================== capabilities

class Capabilities(World):

    LEGACY_SHAPE = {'publish': 'legacy', 'tokens': None, 'comments': 'legacy'}
    NO_INTEGRATIONS = {'publish': 'static-publish', 'tokens': None, 'comments': None}

    def caps_everywhere(self):
        """`space.capabilities` у `/api/task|tasks|tasks-overview` (простір `off`, він поточний) і в записі `/api/spaces`."""
        out = {}
        st, body = self.get('/api/task')
        self.assertEqual(st, 200, body)
        out['task'] = body['space']['capabilities']
        st, body = self.get('/api/tasks')
        self.assertEqual(st, 200, body)
        out['tasks'] = body['space']['capabilities']
        st, body = self.get('/api/tasks-overview')
        self.assertEqual(st, 200, body)
        out['overview'] = body['space']['capabilities']
        st, body = self.get('/api/spaces')
        self.assertEqual(st, 200, body)
        out['spaces'] = {s['id']: s['capabilities'] for s in body['spaces']}
        return out

    def test_every_response_names_the_capabilities(self):
        got = self.caps_everywhere()
        self.assertEqual(got['task'], self.NO_INTEGRATIONS)
        self.assertEqual(got['tasks'], self.NO_INTEGRATIONS)
        self.assertEqual(got['overview'], self.NO_INTEGRATIONS)
        self.assertEqual(got['spaces'], {'off': self.NO_INTEGRATIONS, 'on': self.LEGACY_SHAPE})

    def test_a_task_of_another_space_names_its_own_capabilities(self):
        st, body = self.get('/t/ty/api/task')
        self.assertEqual(st, 200, body)
        self.assertEqual((body['space']['id'], body['space']['capabilities']), ('on', self.LEGACY_SHAPE))

    def test_all_tasks_listing_carries_the_space_of_the_request(self):
        st, body = self.get('/api/tasks?all=1')
        self.assertEqual(st, 200, body)
        self.assertEqual(body['space']['capabilities'], self.NO_INTEGRATIONS)

    def test_enabling_and_disabling_shows_up_everywhere_without_a_restart(self):
        self.enable_tokens()
        got = self.caps_everywhere()
        want = {'publish': 'static-publish', 'tokens': 'css-tokens', 'comments': None}
        self.assertEqual((got['task'], got['tasks'], got['overview'], got['spaces']['off']), (want,) * 4)
        self.post('/api/module-disable', {'id': 'css-tokens'})
        self.post('/api/module-disable', {'id': 'static-publish'})
        got = self.caps_everywhere()
        self.assertEqual(got['spaces']['off'], {'publish': None, 'tokens': None, 'comments': None})
        self.assertEqual(got['task'], {'publish': None, 'tokens': None, 'comments': None})

    def test_describe_and_the_registry_listing_stay_as_they_were(self):
        d = spaces.describe(self.off)
        self.assertEqual(set(d), {'id', 'name', 'color', 'path', 'legacy', 'integrations'})
        self.assertNotIn('capabilities', d)
        self.assertEqual(set(spaces.listing()['spaces'][0]),
                         {'id', 'name', 'color', 'path', 'legacy', 'integrations', 'tasks', 'available'})

    def test_a_broken_space_json_of_one_space_does_not_break_the_listing(self):
        _write(os.path.join(self.off_path, 'space.json'), '{not json')
        st, body = self.get('/api/spaces')
        self.assertEqual(st, 200, body)
        caps = {s['id']: s['capabilities'] for s in body['spaces']}
        self.assertEqual(caps['off'], {'publish': None, 'tokens': None, 'comments': None, 'error': 'space-json-unreadable'})
        self.assertEqual(caps['on'], self.LEGACY_SHAPE)             # решта просторів — як були
        self.assertEqual([s['id'] for s in body['spaces']], ['off', 'on'])
        st, body = self.get('/api/task')                            # і єдина задача теж відповідає
        self.assertEqual(st, 200, body)
        self.assertEqual(body['space']['capabilities'],
                         {'publish': None, 'tokens': None, 'comments': None, 'error': 'space-json-unreadable'})
        st, body = self.get('/api/tasks')
        self.assertEqual(body['space']['capabilities']['error'], 'space-json-unreadable')

    def test_a_space_whose_resolution_raises_something_unexpected_still_lists(self):
        """Тотальність — контракт `capabilities`, а не лише відповідь на `ModuleError`: збій, якого ніхто не
        передбачав (тут `RuntimeError` із розв'язання ролі), лягає в `error` цього простору, а список і задача
        відповідають. Без цього один простір гасив би `/api/spaces` — а за ним увесь інтерфейс."""
        real = dm._provider_for

        def boom(role, space):
            if space.get('id') == 'off':
                raise RuntimeError('boom')
            return real(role, space)
        with mock.patch.object(dm, '_provider_for', boom):
            st, body = self.get('/api/spaces')
            self.assertEqual(st, 200, body)
            caps = {s['id']: s['capabilities'] for s in body['spaces']}
            st2, task = self.get('/api/task')
        self.assertEqual(caps['off'], {'publish': None, 'tokens': None, 'comments': None, 'error': 'module-error'})
        self.assertEqual(caps['on'], self.LEGACY_SHAPE)
        self.assertEqual((st2, task['space']['capabilities']['error']), (200, 'module-error'))

    def test_a_broken_space_json_of_a_space_with_integrations_keeps_the_league_publish_but_never_reroutes_comments(self):
        _write(os.path.join(self.on_path, 'space.json'), '{not json')
        st, body = self.get('/api/spaces')
        self.assertEqual(st, 200, body)
        caps = {s['id']: s['capabilities'] for s in body['spaces']}
        # публікація — шлях ЛІГА недоторканий; коментарі — НЕ 'legacy' (спільний Supabase не запасний варіант) + помилка
        self.assertEqual(caps['on'], {'publish': 'legacy', 'tokens': None, 'comments': None,
                                      'error': 'space-json-unreadable'})

    def test_a_broken_catalog_does_not_break_the_listing(self):
        """Не завантажений модуль УВІМКНЕНО (роль `tokens`) — він постачальником не стає, а списки відповідають."""
        self.modules(extra=('broken',))
        st, body = self.post('/api/module-enable', {'id': 'broken'})
        self.assertEqual((st, body['module']['enabled'], body['module']['status']), (200, True, 'error'), body)
        st, body = self.get('/api/spaces')
        self.assertEqual(st, 200, body)
        self.assertEqual({s['id']: s['capabilities'] for s in body['spaces']},
                         {'off': {'publish': 'static-publish', 'tokens': None, 'comments': None},
                          'on': {'publish': 'legacy', 'tokens': None, 'comments': 'legacy'}})
        st, body = self.get('/api/task')
        self.assertEqual((st, body['space']['capabilities']),
                         (200, {'publish': 'static-publish', 'tokens': None, 'comments': None}))


# ================================================================================================== /api/ds-tokens

class DsTokens(World):

    def test_the_profile_of_a_space_with_css_tokens(self):
        self.enable_tokens()
        st, body = self.get('/api/ds-tokens')
        self.assertEqual(st, 200, body)
        self.assertEqual(body, {'profile': 'space:off', 'tokens': {'--c-primary': ['#123456'], '--gap': ['4px']},
                                'source': 'ds.css'})
        self.assertEqual(list(body), ['profile', 'tokens', 'source'])

    def test_an_explicit_space_is_served_regardless_of_the_current_one(self):
        self.enable_tokens()
        spaces.switch_space('on')
        self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None}))
        st, body = self.get('/api/ds-tokens?space=off')
        self.assertEqual((st, body['profile']), (200, 'space:off'))

    def test_no_provider_is_profile_null(self):
        self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None}))
        self.assertEqual(self.get('/api/ds-tokens?space=on'), (200, {'profile': None}))

    def test_a_disabled_provider_is_no_provider(self):
        self.enable_tokens()
        self.post('/api/module-disable', {'id': 'css-tokens'})
        self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None}))

    def test_an_empty_token_map_is_profile_null_without_an_error(self):
        self.enable_tokens(text='body{color:red}')
        self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None}))

    def test_a_module_error_is_profile_null_with_the_code_and_still_200(self):
        self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '{space}/none.css'}})
        st, body = self.get('/api/ds-tokens')
        self.assertEqual((st, body), (200, {'profile': None, 'error': 'module-error'}))

    def test_a_missing_required_setting_is_profile_null_with_bad_settings(self):
        self.post('/api/module-enable', {'id': 'css-tokens'})
        self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None, 'error': 'bad-settings'}))

    def test_an_unreadable_space_json_is_profile_null_with_the_code(self):
        _write(os.path.join(self.off_path, 'space.json'), '{not json')
        self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None, 'error': 'space-json-unreadable'}))

    def test_a_timeout_is_profile_null_with_check_timeout(self):
        self.modules(extra=('slow-tokens',), copy=())
        self.post('/api/module-enable', {'id': 'slow-tokens'})
        with mock.patch.object(dm, 'CHECK_TIMEOUT', 0.2):
            self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None, 'error': 'check-timeout'}))

    def test_a_malformed_answer_of_a_module_is_module_error_not_a_500(self):
        self.modules(extra=('odd-tokens',), copy=())
        self.post('/api/module-enable', {'id': 'odd-tokens'})
        for shape in ('str', 'scalar', 'other'):
            with self.subTest(shape=shape):
                self.post('/api/module-settings', {'id': 'odd-tokens', 'settings': {'shape': shape}})
                self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None, 'error': 'module-error'}))

    def test_a_module_that_did_not_load_is_never_a_provider(self):
        self.modules(extra=('broken',), copy=())
        self.post('/api/module-enable', {'id': 'broken'})
        self.assertEqual(self.get('/api/ds-tokens'), (200, {'profile': None}))


if __name__ == '__main__':
    unittest.main()
