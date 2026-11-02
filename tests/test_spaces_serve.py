"""Сервер і CLI з просторами: кожен запит працює з файлом задач СВОГО простору.

Етап 1 Deai 1.0, Task 2 (спека 2026-10-13-deai-spaces-design.md, «Файл задач запиту»).
Що доводиться:
  * простір запиту береться з названої задачі (заголовок, префікс, Referer) або з
    поточного простору і фіксується НА ВХОДІ — паралельний `space-switch` посеред
    запиту його не міняє, а keep-alive зʼєднання не несе простір попереднього запиту;
  * `no-task` / `space-unavailable` / `ambiguous-task` / `spaces-*` — центральні JSON-відповіді
    (404/503/409/503) замість обірваного зʼєднання, і тіло POST вичитується;
  * `bin/state.py` і `bin/inbox.py` знаходять задачу в будь-якому просторі й не падають
    traceback-ом, коли задач немає;
  * фонові потоки зʼємки живуть у просторі запиту, що їх запустив.

Task 3 (маршрути просторів і задачі між ними):
  * `GET /api/spaces`, `GET /api/space-peek`, `POST /api/space-new|space-update|space-switch` —
    форми відповідей, коди відмов (400/404/409/503), заголовок і префікс задачі на них не діють;
  * `/api/task`, `/api/tasks`, `/api/tasks-overview` називають простір; `/api/tasks?all=1` — усі
    простори (кожен рядок з `space`), простір запиту повертається; просторів нема — порожні 200;
  * `task-switch` між просторами (файл задач — ПЕРЕД реєстром; конкурентний тест), `task-new` між
    просторами (дефолт — простір з інтеграціями, id унікальний через усі простори, без інтеграцій —
    `profile: null`, без `gitlab`, тека в `path` простору);
  * шар вимкнено (`LayerOff`): `space: null` скрізь, запис просторів — 409 `spaces-off`.

⛔ Ізоляція: власні тимчасові `HOME`, `DEAI_HOME`, `DC_TASKS_FILE` (шар просторів увімкнено:
`DEAI_HOME` + `DC_TASKS_FILE`), `DC_NO_OVERVIEW=1`; все повертається в `tearDownClass`. Справжній
`~/.deai` стереже `spaces_guard`. Живі `tasks.json` і порт 8765 не чіпаються.
"""
import ast
import contextlib
import hashlib
import http.client
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbconf  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import state  # noqa: E402
import inbox  # noqa: E402
import registry as rg  # noqa: E402
import roots  # noqa: E402
import reseal_gate  # noqa: E402

_ENV = ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE', 'DC_NO_OVERVIEW',
        'DC_IDENTITY_NAME', 'DC_IDENTITY_EMAIL')
_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()
    # Конфіг Supabase ЛІГА — підставний на весь модуль (4b-2: констант нема, а справжній `tasks.json` установки не читаємо):
    # тут перевіряється розмітка/збірка, а не пошук конфігу (його стережуть `test_legacy_comments`).
    cfg = mock.patch.object(serve, 'supabase_config', return_value=(sbconf.SB_URL, sbconf.SB_KEY))
    cfg.start()
    unittest.addModuleCleanup(cfg.stop)


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False)


def _read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def _md5(path):
    return hashlib.md5(_bytes(path)).hexdigest()


def _task_dir(path, marker):
    """Тека задачі: `iterations.json`, одна ітерація `it1` з index.html і `root-abs.svg`
    (корене-абсолютний ассет, за яким видно, ЧИЯ це ітерація)."""
    _write(os.path.join(path, 'iterations.json'),
           {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'start',
                            'published': False}], 'publish_url': None})
    _write(os.path.join(path, 'iterations', 'it1', 'index.html'),
           f'<!DOCTYPE html><html><body><h1>{marker}</h1></body></html>')
    _write(os.path.join(path, 'iterations', 'it1', 'root-abs.svg'),
           f'<svg xmlns="http://www.w3.org/2000/svg" id="{marker}-root"/>')


@contextlib.contextmanager
def env(**kv):
    """Тимчасово виставити/прибрати змінні оточення (None — прибрати)."""
    saved = {k: os.environ.get(k) for k in kv}
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run(fn, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = fn(argv)
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class Fixture(unittest.TestCase):
    """Сервер у процесі + два простори: старий (`a`, інтеграції) і `P` (`x`), порожній `E`."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.normpath(tempfile.mkdtemp(prefix='spaces-serve-'))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        saved = {k: os.environ.get(k) for k in _ENV}

        def restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        cls.addClassCleanup(restore)
        cls.home = os.path.join(cls.tmp, 'home')
        cls.deai = os.path.join(cls.tmp, 'deai')
        cls.legacy_file = os.path.join(cls.tmp, 'legacy', 'tasks.json')
        os.makedirs(cls.home)
        os.environ['HOME'] = cls.home
        os.environ['DEAI_HOME'] = cls.deai
        os.environ['DC_TASKS_FILE'] = cls.legacy_file
        os.environ['DC_NO_OVERVIEW'] = '1'              # жодного пуша в прод-Supabase
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        spaces.clear_request_space()

        # Старий простір: задача `a`, маркер `registry` → інтеграції ввімкнені.
        work = os.path.join(cls.tmp, 'work')
        cls.a_dir = os.path.join(work, 'a')
        _task_dir(cls.a_dir, 'a')
        _write(cls.legacy_file, {'current': 'a', 'design_work_root': work, 'registry': {},
                                 'tasks': {'a': {'title': 'Альфа', 'dir': cls.a_dir,
                                                 'profile': 'tool'}}})
        # Другий простір `P` з задачею `x` (+ `gone`: є в реєстрі, теки на машині нема).
        cls.p_path = os.path.join(cls.home, 'deai-work', 'p')
        cls.p_id = spaces.create_space('P', 'space-2', cls.p_path)
        cls.legacy_id = next(s['id'] for s in spaces.read_registry()['spaces'] if s.get('legacy'))
        cls.x_dir = os.path.join(cls.p_path, 'x')
        _task_dir(cls.x_dir, 'x')
        cls.p_file = os.path.join(cls.p_path, 'tasks.json')
        _write(cls.p_file, {'design_work_root': cls.p_path, 'current': 'x', 'tasks': {
            'x': {'title': 'Ікс', 'dir': cls.x_dir, 'profile': 'tool'},
            'gone': {'title': 'Зникла', 'dir': os.path.join(cls.p_path, 'nowhere'),
                     'profile': 'tool'}}})
        # Порожній простір `E`.
        cls.e_path = os.path.join(cls.home, 'deai-work', 'e')
        cls.e_id = spaces.create_space('E', 'space-3', cls.e_path)
        cls.e_file = os.path.join(cls.e_path, 'tasks.json')

        cls.httpd = serve.make_server(0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.httpd.server_close)
        cls.addClassCleanup(cls.httpd.shutdown)
        cls.base = f'http://127.0.0.1:{cls.port}'

    def setUp(self):
        spaces.clear_request_space()
        spaces.switch_space(self.legacy_id)         # поточний простір — старий

    def tearDown(self):
        spaces.clear_request_space()

    # ---------- HTTP ----------

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8')

    def jget(self, path, headers=None):
        st, body = self.get(path, headers)
        return st, json.loads(body)

    def post(self, path, payload, headers=None):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(), method='POST',
            headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode('utf-8'))

    def post_raw(self, path, payload, headers=None):
        """POST, відповідь якого може бути й не JSON (`send_error` — HTML): `(статус, текст)`."""
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(), method='POST',
            headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8')

    def big_post(self, path, headers=None):
        """POST із тілом ~900 КБ СИРИМ зʼєднанням. Відмова, що не вичитала тіло, закриває
        зʼєднання з непрочитаним у буфері — клієнт отримує RST замість відповіді (або
        висне до таймауту). Тому саме велике тіло доводить, що воно вичитане."""
        body = b'{"pad":"' + b'x' * 900_000 + b'"}'
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request('POST', path, body,
                         {'Content-Type': 'application/json', **(headers or {})})
            r = conn.getresponse()
            return r.status, json.loads(r.read().decode('utf-8'))
        finally:
            conn.close()

    def restore_bytes(self, path):
        """Повернути файл у стан «до тесту» (cleanup)."""
        before = _bytes(path)

        def back():
            with open(path, 'wb') as f:
                f.write(before)
        self.addCleanup(back)


class RequestSpace(Fixture):
    """Який файл задач діє для запиту."""

    def test_current_space_serves_its_current_task(self):
        st, body = self.jget('/api/task')
        self.assertEqual((st, body['id']), (200, 'a'))
        spaces.switch_space(self.p_id)
        st, body = self.jget('/api/task')
        self.assertEqual((st, body['id']), (200, 'x'))

    def test_named_task_of_another_space_header_and_prefix(self):
        self.assertEqual(self.jget('/api/task', {'X-Canvas-Task': 'x'})[1]['id'], 'x')
        self.assertEqual(self.jget('/t/x/api/task')[1]['id'], 'x')
        # і навпаки: поточний — P, названа — із старого простору
        spaces.switch_space(self.p_id)
        self.assertEqual(self.jget('/t/a/api/task')[1]['id'], 'a')
        self.assertEqual(self.jget('/api/task', {'X-Canvas-Task': 'a'})[1]['id'], 'a')

    def test_write_to_a_task_of_another_space_goes_to_its_own_file(self):
        """`a` живе в старому просторі, поточний — `P`. Пароль превʼю — саме такий запис, який
        вимикач Task 4 не закриє: `a` у просторі з інтеграціями."""
        spaces.switch_space(self.p_id)
        before_p = _md5(self.p_file)
        st, body = self.post('/t/a/api/preview-password', {'password': 'abcd'})
        self.assertEqual(st, 200, body)
        self.assertEqual(_read(self.legacy_file)['tasks']['a']['preview_password'], 'abcd')
        self.assertEqual(_md5(self.p_file), before_p, 'запис у задачу `a` зачепив файл простору P')
        self.assertEqual(spaces.read_registry()['current'], self.p_id, 'запис перемкнув простір')
        # `.bak` ліг поруч зі СТАРИМ файлом, а не поруч із P
        self.assertTrue(os.path.isfile(self.legacy_file + '.bak'))
        self.assertFalse(os.path.exists(self.p_file + '.bak'))

    def test_request_space_is_pinned_on_entry(self):
        """Простір запиту видно обробнику: названа задача — її простір, не названа — поточний
        машини НА ВХОДІ (а не `None`, що читав би реєстр щоразу заново)."""
        seen = []
        real = serve.Handler._current_task

        def spy(h):
            seen.append(spaces.request_space_id())
            return real(h)
        with mock.patch.object(serve.Handler, '_current_task', spy):
            self.get('/api/task')
            self.get('/t/x/api/task')
            self.get('/api/task', {'X-Canvas-Task': 'a'})
        self.assertEqual(seen, [self.legacy_id, self.p_id, self.legacy_id])

    def test_a_parallel_space_switch_in_the_middle_of_a_request_does_not_move_it(self):
        """Запит, що вже зайшов у простір, дочитує його, навіть коли хтось перемкнув поточний
        простір, поки обробник працював (друге вікно канваса, агент через `space-switch`)."""
        real = serve.Handler._current_task

        def switching(h):
            spaces.switch_space(self.p_id)
            return real(h)
        with mock.patch.object(serve.Handler, '_current_task', switching):
            st, body = self.jget('/api/task')
        self.assertEqual((st, body['id']), (200, 'a'))
        self.assertEqual(spaces.read_registry()['current'], self.p_id)

    def test_request_space_is_cleared_at_entry_and_again_in_finally(self):
        """Пряме свідчення двох скидань: `clear_request_space` кличеться НА ВХОДІ запиту (до
        обробника) і ще раз у `finally` (після нього). Окремо прибране будь-яке — червоніє."""
        events = []
        real_clear = spaces.clear_request_space

        def clear():
            events.append('clear')
            real_clear()
        real = serve.Handler._current_task

        def spy(h):
            events.append('handler')
            return real(h)

        def run(path, want):
            events.clear()
            self.get(path)
            deadline = time.monotonic() + 2        # `finally` йде ПІСЛЯ відповіді клієнту
            while len(events) < len(want) and time.monotonic() < deadline:
                time.sleep(0.01)
            time.sleep(0.05)                       # і зайвих викликів теж не має бути
            return list(events)
        with mock.patch.object(spaces, 'clear_request_space', clear), \
                mock.patch.object(serve.Handler, '_current_task', spy):
            self.assertEqual(run('/api/task', ['clear', 'handler', 'clear']),
                             ['clear', 'handler', 'clear'])
            # відмова ще на вході (`/t/<id>/app/`): обробник не заходив, а `finally` усе одно скидає
            self.assertEqual(run('/t/x/app/', ['clear', 'clear']), ['clear', 'clear'])

    def test_guarded_keeps_the_return_value_of_the_handler(self):
        h = serve.Handler.__new__(serve.Handler)
        self.assertEqual(h._guarded(lambda: 7), 7)

        @serve._guarded_request
        def handler(self_):
            return 9
        self.assertEqual(handler(h), 9)

    def test_keep_alive_connection_does_not_carry_the_space_of_the_previous_request(self):
        # ОКРЕМИЙ сервер з HTTP/1.1: на основному кожен запит на новому зʼєднанні, а тут
        # усі йдуть одним потоком обробника — саме так простір міг би прилипнути.
        # ⚠️ Цей тест — СВІДОК ОБʼЄДНАННЯ трьох захистів (скидання на вході `_take_task`, скидання
        # у `finally` `_guarded`, фіксація поточного для не названого запиту): падає, лише коли
        # зламано ВСІ три. Кожен окремо доводять `test_request_space_is_pinned_on_entry` і
        # `test_request_space_is_cleared_at_entry_and_again_in_finally`.
        httpd = serve.make_server(0)
        httpd.RequestHandlerClass.protocol_version = 'HTTP/1.1'
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        conn = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
        self.addCleanup(conn.close)
        ids = []
        for path in ('/t/x/api/task', '/api/task', '/api/task'):
            conn.request('GET', path)
            r = conn.getresponse()
            ids.append(json.loads(r.read().decode('utf-8'))['id'])
        self.assertEqual(ids, ['x', 'a', 'a'])

    def test_referer_naming_a_task_of_another_space(self):
        ref = f'{self.base}/t/x/commented?it=it1'
        st, body = self.get('/root-abs.svg', {'Referer': ref})
        self.assertEqual(st, 200)
        self.assertIn('x-root', body)
        # без префікса в Referer — як було: поточна задача поточного простору
        plain = f'{self.base}/commented?it=it1'
        self.assertIn('a-root', self.get('/root-abs.svg', {'Referer': plain})[1])
        spaces.switch_space(self.p_id)
        self.assertIn('x-root', self.get('/root-abs.svg', {'Referer': plain})[1])
        self.assertIn('a-root', self.get('/root-abs.svg', {
            'Referer': f'{self.base}/t/a/commented?it=it1'})[1])

    def test_referer_naming_a_task_not_here_or_unknown_is_ignored(self):
        """Як і до просторів (`test_18c_*`): Referer із задачею, якої теки тут нема, чи
        невідомою ігнорується ЦІЛИМ — ітерацію не віддає ні та задача, ні поточна."""
        for tid in ('gone', 'nope'):
            with self.subTest(tid=tid):
                st, body = self.get('/root-abs.svg', {
                    'Referer': f'{self.base}/t/{tid}/commented?it=it1'})
                self.assertEqual(st, 404)
                self.assertNotIn('-root', body)

    def test_referer_naming_an_ambiguous_task_is_ignored_not_a_409(self):
        """Дубль id у двох просторах у Referer — Referer ігнорується, як невідомий: статичний
        ассет не відповідає JSON-409 (ця відмова — для API, а не для картинки)."""
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['tasks']['a'] = {'title': 'Дубль', 'dir': self.a_dir, 'profile': 'tool'}
        _write(self.p_file, cfg)
        st, body = self.get('/root-abs.svg', {'Referer': f'{self.base}/t/a/commented?it=it1'})
        self.assertEqual(st, 404)
        self.assertNotIn('-root', body)

    def test_unknown_named_task_is_still_a_plain_404(self):
        st, body = self.jget('/api/task', {'X-Canvas-Task': 'nope'})
        self.assertEqual((st, body['error']), (404, 'unknown task: nope'))
        st, body = self.jget('/t/gone/api/task')
        self.assertEqual((st, body['error']), (404, 'task not on this machine: gone'))

    def test_registry_routes_are_listed_and_take_no_prefix(self):
        """Маршрути просторів — у `_REGISTRY_ROUTES` (самі маршрути — Task 3): префікс `/t/<id>/`
        відхиляється, заголовок не діє."""
        for route in ('/api/spaces', '/api/space-peek', '/api/space-new', '/api/space-update',
                      '/api/space-switch'):
            with self.subTest(route=route):
                self.assertIn(route, serve.Handler._REGISTRY_ROUTES)
        st, body = self.post('/t/x/api/space-switch', {'id': self.p_id})
        self.assertEqual(st, 400)
        self.assertIn('реєстр задач не привʼязаний', body['error'])

    def test_who_text_survives_a_task_gone_between_entry_and_the_404_text(self):
        """`/it-assets/…` не знайдено → текст 404 називає поточну задачу. Якщо задачі ВЖЕ нема
        (простір спорожнів між входом і текстом) — `who` стає «—», а не падінням."""
        task = {'dir': self.x_dir}
        calls = [('x', task), spaces.NoTask(self.p_id)]
        with mock.patch.object(serve.Handler, '_current_task', side_effect=calls):
            st, body = self.get('/it-assets/it1/nope.css')
        self.assertEqual(st, 404)
        self.assertIn('Поточна задача — —', body)


class InspectorSpace(Fixture):
    """Етап 2а, Task 7: інспектор у документі макета дізнається про простір з `sp` у власному URL
    і питає `/api/ds-tokens?space=<id>`. Простір — той, ЧИЯ задача віддає сторінку: `/commented`
    читає задачу з файла простору запиту, тож `active_space()` і є простором задачі (під НАЗВАНОЮ
    задачею сторінка з коментатором не віддається взагалі — 400, див. нижче)."""

    @staticmethod
    def _query(html):
        """Хвіст URL тега інспектора: `?ds=…&sp=…` (порожній рядок, якщо параметрів нема)."""
        m = re.search(r'src="[^"]*/inspector\.js([^"]*)"', html)
        assert m, 'у сторінці нема тега інспектора'
        return m.group(1)

    def _page(self, query='', headers=None):
        st, html = self.get('/commented?it=it1' + query, headers)
        self.assertEqual(st, 200, html[:200])
        return html

    def test_local_channel_names_the_current_space(self):
        self.assertEqual(self._query(self._page()), f'?ds=tool&sp={self.legacy_id}')
        spaces.switch_space(self.p_id)
        self.assertEqual(self._query(self._page()), f'?ds=tool&sp={self.p_id}')

    def test_project_channel_names_it_too(self):
        """`ch=project` — другий виклик інʼєкції. Старий простір має інтеграції (маркер `registry`),
        тож канал справді проєктний, а не знижений до локального."""
        html = self._page('&ch=project')
        self.assertIn('dc/a', html)
        self.assertNotIn('local-adapter.js', html)
        self.assertEqual(self._query(html), f'?ds=tool&sp={self.legacy_id}')

    def test_project_channel_demoted_in_a_space_without_integrations_still_names_it(self):
        spaces.switch_space(self.p_id)
        html = self._page('&ch=project')
        self.assertIn('local-adapter.js', html)                 # знижено до локального
        self.assertEqual(self._query(html), f'?ds=tool&sp={self.p_id}')

    def test_the_space_is_the_one_of_the_pinned_request_not_a_later_switch(self):
        """Простір запиту фіксується НА ВХОДІ; `sp` береться з нього, а не з реєстру на мить рендера.
        Поточний простір перемикається ПІСЛЯ того, як задачу прочитано, але ДО рендера сторінки (як
        друге вікно канваса посеред запиту): задача — з P, і `sp` мусить назвати P, а не новий
        поточний."""
        spaces.switch_space(self.p_id)
        real = serve.Handler._current_task

        def switching(handler):
            out = real(handler)
            spaces.switch_space(self.legacy_id)
            return out
        with mock.patch.object(serve.Handler, '_current_task', switching):
            html = self._page()
        self.assertIn('<h1>x</h1>', html, 'сторінка — задачі `x` простору P')
        self.assertEqual(self._query(html), f'?ds=tool&sp={self.p_id}')
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id, 'контроль: перемикання відбулось')

    def test_no_inspector_no_sp_in_the_bare_page(self):
        st, html = self.get('/commented?it=it1&bare=1')
        self.assertEqual(st, 200)
        self.assertNotIn('inspector.js', html)
        self.assertNotIn('sp=', html)

    def test_a_named_task_gets_no_commented_page_so_sp_cannot_name_a_foreign_space(self):
        st, body = self.get('/t/x/commented?it=it1')
        self.assertEqual(st, 400, body[:200])
        st, body = self.get('/commented?it=it1', {'X-Canvas-Task': 'x'})
        self.assertEqual(st, 400, body[:200])

    def test_the_sp_the_page_names_is_one_the_tokens_route_accepts(self):
        """Дорога ціла: id із сторінки → `/api/ds-tokens?space=<id>` → 200 (не `unknown-space`)."""
        for sid in (self.legacy_id, self.p_id):
            spaces.switch_space(sid)
            sp = self._query(self._page()).split('sp=')[1]
            self.assertEqual(sp, sid)
            st, body = self.jget(f'/api/ds-tokens?space={sp}')
            self.assertEqual(st, 200, body)
            self.assertIn('profile', body)


class TaskPathAndHelpers(Fixture):
    """`tasks_path` / `load_tasks` / `task_for` / `task_anywhere` напряму."""

    def test_tasks_path_follows_the_request_space(self):
        self.assertEqual(serve.tasks_path(), self.legacy_file)
        with spaces.request_space(self.p_id):
            self.assertEqual(serve.tasks_path(), self.p_file)
            self.assertEqual(serve.load_tasks()['current'], 'x')
        with spaces.request_space(''):
            with self.assertRaises(spaces.NoTask):
                serve.tasks_path()

    def test_legacy_file_is_independent_of_the_request_space(self):
        with spaces.request_space(self.p_id):
            self.assertEqual(serve.legacy_tasks_path(), self.legacy_file)
            self.assertEqual(serve.load_legacy_tasks()['current'], 'a')
        with env(DC_TASKS_FILE=os.path.join(self.tmp, 'nope.json')):
            with self.assertRaises(FileNotFoundError):
                serve.load_legacy_tasks()

    def test_layer_off_is_exactly_as_before(self):
        """Лише `DC_TASKS_FILE`: файл — він, у який би простір не вказував запит; биті файли —
        сирими винятками (не `SpaceUnavailable`), як було."""
        with env(DEAI_HOME=None):
            with spaces.request_space(self.p_id):
                self.assertEqual(serve.tasks_path(), self.legacy_file)
            bad = os.path.join(self.tmp, 'bad.json')
            _write(bad, '{')
            with env(DC_TASKS_FILE=bad):
                with self.assertRaises(ValueError) as ctx:
                    serve.load_tasks()
                self.assertNotIsInstance(ctx.exception, serve.SpaceUnavailable)
            with env(DC_TASKS_FILE=os.path.join(self.tmp, 'nope.json')):
                with self.assertRaises(FileNotFoundError):
                    serve.load_tasks()

    def test_space_unavailable_is_both_oserror_and_valueerror_with_a_path(self):
        e = serve.SpaceUnavailable('/x/tasks.json')
        self.assertIsInstance(e, OSError)
        self.assertIsInstance(e, ValueError)
        self.assertEqual(e.path, '/x/tasks.json')

    def test_load_tasks_wraps_every_unreadable_shape_when_the_layer_is_on(self):
        self.addCleanup(lambda: _write(self.e_file, {'design_work_root': self.e_path, 'tasks': {}}))
        with spaces.request_space(self.e_id):
            for raw in ('{', '[]', '5', '"s"', '￾\x00', '[' * 100000):
                with self.subTest(raw=raw[:10]):
                    _write(self.e_file, raw)
                    with self.assertRaises(serve.SpaceUnavailable) as ctx:
                        serve.load_tasks()
                    self.assertEqual(ctx.exception.path, self.e_file)
            os.remove(self.e_file)
            with self.assertRaises(serve.SpaceUnavailable):
                serve.load_tasks()

    def test_task_for_without_a_current_task_is_notask_not_keyerror(self):
        for cfg in ({}, {'tasks': {}}, {'current': None, 'tasks': {'a': {}}},
                    {'current': 'zzz', 'tasks': {'a': {}}}, {'current': 5, 'tasks': {'a': {}}},
                    {'current': 'a', 'tasks': None}, {'current': 'a', 'tasks': []}):
            with self.subTest(cfg=cfg):
                with self.assertRaises(serve.NoTask):
                    serve.task_for(cfg)
        self.assertEqual(serve.task_for({'current': 'a', 'tasks': {'a': {'t': 1}}}), ('a', {'t': 1}))
        self.assertIs(serve.NoTask, spaces.NoTask)
        self.assertIs(serve.AmbiguousTask, spaces.AmbiguousTask)
        # NoTask називає простір запиту; шар вимкнено — простору нема (`null`)
        with spaces.request_space(self.e_id):
            with self.assertRaises(serve.NoTask) as ctx:
                serve.task_for({'tasks': {}})
            self.assertEqual(ctx.exception.space, self.e_id)
        with env(DEAI_HOME=None), spaces.request_space('legacy'):
            with self.assertRaises(serve.NoTask) as ctx:
                serve.task_for({'tasks': {}})
            self.assertIsNone(ctx.exception.space)

    def test_task_for_with_an_explicit_id_is_unchanged(self):
        cfg = {'current': 'a', 'tasks': {'a': {'dir': self.a_dir}, 'n': {'title': 'N'}}}
        self.assertEqual(serve.task_for(cfg, 'a'), ('a', {'dir': self.a_dir}))
        with self.assertRaises(serve.TaskNotHere):
            serve.task_for(cfg, 'n')
        with self.assertRaises(serve.UnknownTask):
            serve.task_for(cfg, 'nope')

    def test_task_anywhere_finds_the_space_and_pins_it(self):
        tid, task = serve.task_anywhere('x')
        self.assertEqual((tid, task['dir']), ('x', self.x_dir))
        self.assertEqual(spaces.request_space_id(), self.p_id)
        tid, _ = serve.task_anywhere(None)               # поточний простір машини
        self.assertEqual((tid, spaces.request_space_id()), ('a', self.legacy_id))
        with self.assertRaises(serve.UnknownTask):
            serve.task_anywhere('nope')
        with self.assertRaises(serve.TaskNotHere):
            serve.task_anywhere('gone')
        spaces.switch_space(self.e_id)
        with self.assertRaises(serve.NoTask):
            serve.task_anywhere(None)

    def test_the_first_migration_inside_tasks_path_does_not_deadlock_save_tasks(self):
        """Свіжий `DEAI_HOME` без реєстру + старий файл є: перше ж `tasks_path()` мігрує
        (бере `WRITE_LOCK`). Якщо `save_tasks` кличе його ПІД локом — дедлок. Два порядки: і
        `save_tasks(load_tasks())` (міграція в `load_tasks`), і `save_tasks(cfg)` першим (міграція
        в самому `save_tasks` — саме тут лок і міг би охопити `tasks_path()`)."""
        for name, make_cfg in (('after-load', lambda: serve.load_tasks()),
                               ('save-first', lambda: _read(self.legacy_file))):
            with self.subTest(order=name):
                fresh = os.path.join(self.tmp, f'fresh-deai-{name}')
                legacy = os.path.join(self.tmp, f'fresh-legacy-{name}', 'tasks.json')
                _write(legacy, _read(self.legacy_file))
                result = {}

                def work():
                    try:
                        serve.save_tasks(make_cfg())
                        result['ok'] = True
                    except BaseException as e:  # noqa: BLE001
                        result['err'] = e
                with env(DEAI_HOME=fresh, DC_TASKS_FILE=legacy):
                    t = threading.Thread(target=work, daemon=True)
                    t.start()
                    t.join(5)
                    if t.is_alive():
                        with contextlib.suppress(RuntimeError):
                            spaces.WRITE_LOCK.release()      # не лишити лок усім іншим тестам
                        t.join(5)
                        self.fail('save_tasks завис на WRITE_LOCK: міграція в tasks_path() під локом')
                self.assertEqual(result, {'ok': True})
                self.assertTrue(os.path.isfile(os.path.join(fresh, 'spaces.json')))


class CentralResponses(Fixture):
    """`no-task` / `space-unavailable` / `ambiguous-task` / `spaces-*` замість обриву."""

    def test_empty_space_is_404_no_task(self):
        spaces.switch_space(self.e_id)
        st, body = self.jget('/api/task')
        self.assertEqual(st, 404)
        self.assertIs(body['ok'], False)
        self.assertEqual((body['code'], body['space']), ('no-task', self.e_id))
        self.assertIsInstance(body['error'], str)
        self.assertTrue(body['error'])
        # список задач порожнього простору — не помилка
        st, body = self.jget('/api/tasks')
        self.assertEqual((st, body['current'], body['tasks']), (200, None, []))

    def test_no_task_post_with_a_big_body_gets_its_answer(self):
        spaces.switch_space(self.e_id)
        st, body = self.big_post('/api/iteration')
        self.assertEqual((st, body['code']), (404, 'no-task'))

    def test_broken_tasks_file_of_the_current_space_is_503_space_unavailable(self):
        spaces.switch_space(self.e_id)
        self.addCleanup(lambda: _write(self.e_file, {'design_work_root': self.e_path, 'tasks': {}}))
        _write(self.e_file, '{')
        st, body = self.jget('/api/task')
        self.assertEqual(st, 503)
        self.assertEqual((body['ok'], body['code'], body['path']),
                         (False, 'space-unavailable', self.e_file))
        self.assertTrue(body['error'])
        # POST: відповідь приходить, зʼєднання не висне
        st, body = self.post('/api/iteration', {})
        self.assertEqual((st, body['code']), (503, 'space-unavailable'))
        st, body = self.big_post('/api/iteration')
        self.assertEqual((st, body['code']), (503, 'space-unavailable'))

    def test_ambiguous_task_is_409_and_the_body_is_drained(self):
        """Той самий id у двох просторах. Відмова стається у `_take_task` — ДО читання тіла,
        тому велике тіло мусить бути вичитане центральною гілкою."""
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['tasks']['a'] = {'title': 'Дубль', 'dir': self.a_dir, 'profile': 'tool'}
        _write(self.p_file, cfg)
        for path, headers in (('/api/task', {'X-Canvas-Task': 'a'}), ('/t/a/api/task', {})):
            with self.subTest(path=path):
                st, body = self.jget(path, headers)
                self.assertEqual((st, body['code'], body['ok']), (409, 'ambiguous-task', False))
                self.assertTrue(body['error'])
        st, body = self.big_post('/api/iteration', {'X-Canvas-Task': 'a'})
        self.assertEqual((st, body['code']), (409, 'ambiguous-task'))
        # не названа — поточний простір, дубль їй не заважає
        self.assertEqual(self.jget('/api/task')[1]['id'], 'a')

    def test_named_task_with_an_unreadable_registry_is_503_and_the_body_is_drained(self):
        """`find_task` читає реєстр у `_take_task`, до тіла: помилка реєстру — теж центральна."""
        self.restore_bytes(os.path.join(self.deai, 'spaces.json'))
        _write(os.path.join(self.deai, 'spaces.json'), '{')
        st, body = self.big_post('/api/iteration', {'X-Canvas-Task': 'x'})
        self.assertEqual((st, body['code']), (503, 'spaces-unreadable'))
        self.assertEqual(body['path'], os.path.join(self.deai, 'spaces.json'))

    def test_unreadable_registry_is_503_for_the_api_but_the_ui_still_loads(self):
        """Битий `spaces.json`: UI мусить завантажитись, щоб показати смугу помилки, — тож
        статика віддається, а API каже `spaces-unreadable` з шляхом."""
        self.restore_bytes(os.path.join(self.deai, 'spaces.json'))
        _write(os.path.join(self.deai, 'spaces.json'), '{')
        for path in ('/api/task', '/api/tasks'):
            with self.subTest(path=path):
                st, body = self.jget(path)
                self.assertEqual((st, body['code']), (503, 'spaces-unreadable'))
                self.assertEqual(body['path'], os.path.join(self.deai, 'spaces.json'))
                self.assertTrue(body['error'])
        st, _ = self.get('/app/app.js')
        self.assertEqual(st, 200)
        st, body = self.post('/api/iteration', {})
        self.assertEqual((st, body['code']), (503, 'spaces-unreadable'))

    def test_with_an_unreadable_registry_no_api_handler_is_ever_entered(self):
        """Простір запиту не зафіксовано → `integrations_on()` каже «так» (мережа відкрита). Тому
        API-запит при битому реєстрі не доходить до обробника ВЗАГАЛІ: 503 на вході. Лише статика
        UI (`/app/*`) іде без простору — вона не читає задач."""
        self.restore_bytes(os.path.join(self.deai, 'spaces.json'))
        _write(os.path.join(self.deai, 'spaces.json'), '{')
        entered = []

        def spy(name):
            def handler(h, *args):
                entered.append(name)
                h._send_json({'entered': name})
            return handler
        routes = (('GET', '/comments?it=it1', '_comments'),
                  ('GET', '/commented?it=it1', '_commented'),
                  ('GET', '/shot?it=it1&page=main', '_shot'),
                  ('POST', '/api/publish', '_publish'),
                  ('POST', '/api/gitlab-sync', '_gitlab_sync'),
                  ('POST', '/api/vcs-push', '_gitlab_sync'),
                  ('POST', '/api/vcs-pull', '_gitlab_pull'),
                  ('POST', '/api/autosync', '_autosync'),
                  ('GET', '/api/vcs-status?it=it1', '_gitlab_status'))
        with contextlib.ExitStack() as stack:
            for _, _, name in routes:
                stack.enter_context(mock.patch.object(serve.Handler, name, spy(name)))
            for method, path, name in routes:
                with self.subTest(path=path):
                    if method == 'GET':
                        st, body = self.jget(path)
                    else:
                        st, body = self.post(path, {})
                    self.assertEqual((st, body.get('code')), (503, 'spaces-unreadable'), body)
                    st, body = self.big_post(path) if method == 'POST' else (503, {})
                    self.assertEqual(st, 503)
            # `/it-assets/…` — обробник у самому `do_GET`, без окремого методу: 503 на вході теж
            st, body = self.jget('/it-assets/it1/index.html')
            self.assertEqual((st, body['code']), (503, 'spaces-unreadable'))
        self.assertEqual(entered, [], f'обробники виконались без простору: {entered}')
        for path in ('/app/', '/app/app.js'):
            self.assertEqual(self.get(path)[0], 200, path)

    def test_unwritable_home_is_503_spaces_unwritable(self):
        """Перша міграція на незаписуваний `DEAI_HOME`: `spaces-unwritable`, а не обрив."""
        fresh = os.path.join(self.tmp, 'ro-deai')
        os.makedirs(fresh, mode=0o500)
        self.addCleanup(os.chmod, fresh, 0o700)
        if os.access(fresh, os.W_OK):
            self.skipTest('файлова система не відрізняє права (root?)')
        with env(DEAI_HOME=fresh):
            st, body = self.jget('/api/task')
            self.assertEqual((st, body['code']), (503, 'spaces-unwritable'))
            self.assertEqual(body['path'], os.path.join(fresh, 'spaces.json'))
            self.assertTrue(body['error'])
        self.assertFalse(os.path.exists(os.path.join(fresh, 'spaces.json')))

    def test_no_spaces_at_all_is_404_no_task_with_a_null_space(self):
        empty = os.path.join(self.tmp, 'empty-deai')
        with env(DEAI_HOME=empty, DC_TASKS_FILE=os.path.join(self.tmp, 'nowhere', 'tasks.json')):
            st, body = self.jget('/api/task')
            self.assertEqual((st, body['code'], body['space']), (404, 'no-task', None))
            # названа задача, якої немає ніде, — звичайне «невідома»
            st, body = self.jget('/api/task', {'X-Canvas-Task': 'a'})
            self.assertEqual((st, body['error']), (404, 'unknown task: a'))
        self.assertFalse(os.path.exists(empty), 'читання просторів створило <DEAI_HOME>')

    def test_a_response_already_started_is_not_followed_by_a_second_one(self):
        """Виняток ПІСЛЯ початку відповіді: другої відповіді слати не можна (вона зіпсувала б
        перший потік байтів), зʼєднання просто закривається."""
        real = serve.Handler._send_json

        def late(h, obj, status=200):
            real(h, obj, status)
            raise spaces.NoTask(self.e_id)
        with mock.patch.object(serve.Handler, '_send_json', late):
            with socket.create_connection(('127.0.0.1', self.port), timeout=5) as s:
                s.sendall(b'GET /api/task HTTP/1.0\r\n\r\n')
                data = b''
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    data += chunk
        self.assertEqual(data.count(b'HTTP/1.'), 1, data)
        self.assertIn(b'200 OK', data)


class Cli(Fixture):
    """`bin/state.py` і `bin/inbox.py` знаходять задачу в будь-якому просторі."""

    def patched_state(self):
        self.registry_cfgs = []             # який конфіг побачив `_registry_line` (його простір)
        stack = contextlib.ExitStack()
        for name, repl in (('_registry_line',
                            lambda cfg: self.registry_cfgs.append(sorted(cfg['tasks'])) or 'Реєстр: тест'),
                           ('find_canvas_port', lambda *a, **k: 8766)):
            stack.enter_context(mock.patch.object(state, name, repl))
        self.addCleanup(stack.close)
        sbconf.patch_open(self, sbconf.empty_open)           # командні піни ЛІГИ — модулем; мережі нема

    def test_state_finds_a_task_in_another_space(self):
        self.patched_state()
        rc, out, err = _run(state.main, ['--task', 'x'])
        self.assertEqual(rc, 0, err)
        self.assertIn('«Ікс» (x)', out)
        # конфіг, з яким працює решта команди, — з простору ЗАДАЧІ (P), а не поточного (старого)
        self.assertEqual(self.registry_cfgs, [['gone', 'x']])
        self.assertIsNone(spaces.request_space_id(), 'main() лишив простір запиту в потоці')
        rc, out, _ = _run(state.main, [])                     # без назви — поточний простір
        self.assertEqual(rc, 0)
        self.assertIn('«Альфа» (a)', out)
        self.assertEqual(self.registry_cfgs[-1], ['a'])

    def test_state_prints_a_dash_for_a_task_without_a_profile(self):
        """Задача простору без інтеграцій має `profile: null`: «Профіль: None» — вигадка, а не стан."""
        self.patched_state()
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['tasks']['x']['profile'] = None
        _write(self.p_file, cfg)
        rc, out, err = _run(state.main, ['--task', 'x'])
        self.assertEqual(rc, 0, err)
        self.assertIn('Профіль: — ·', out)
        self.assertNotIn('None', out)
        rc, out, _ = _run(state.main, ['--task', 'a'])                # із профілем — як було
        self.assertIn('Профіль: tool ·', out)

    def test_state_unknown_task_is_exit_2(self):
        self.patched_state()
        rc, out, err = _run(state.main, ['--task', 'nope'])
        self.assertEqual(rc, 2)
        self.assertIn("'nope'", err)
        self.assertEqual(out, '')

    def test_state_task_not_on_this_machine_keeps_its_own_message(self):
        self.patched_state()
        rc, out, err = _run(state.main, ['--task', 'gone'])
        self.assertEqual(rc, 2)
        self.assertIn("задачі 'gone' немає на цій машині", err)

    def test_state_empty_space_says_so_without_a_traceback(self):
        """Поточний простір порожній, а в інших задачі є: «створи простір» брехало б (простір є) —
        кажемо про `--task` і перемикання."""
        self.patched_state()
        spaces.switch_space(self.e_id)
        rc, out, err = _run(state.main, [])
        self.assertEqual(rc, 2)
        self.assertIn('у поточному просторі задач нема; є в інших', err)
        self.assertIn('--task <id>', err)
        self.assertNotIn('створи простір', err)
        self.assertNotIn('Traceback', err)
        self.assertEqual(out, '')

    def test_state_and_inbox_keep_create_a_space_when_no_space_has_a_task(self):
        self.patched_state()
        for f in (self.p_file, self.legacy_file):
            self.restore_bytes(f)
            _write(f, {'tasks': {}})
        spaces.switch_space(self.e_id)
        rc, out, err = _run(state.main, [])
        self.assertEqual(rc, 2)
        self.assertIn('задач немає — створи простір і задачу в канвасі', err)
        self.assertNotIn('є в інших', err)
        sbconf.patch_open(self, sbconf.empty_open)           # командні піни ЛІГИ — модулем; мережі нема
        rc, out, err = _run(inbox.main, [])
        self.assertEqual(rc, 2)
        self.assertIn('задач немає — створи простір і задачу в канвасі', err)
        self.assertNotIn('є в інших', err)

    def test_state_broken_space_file_and_ambiguous_task_are_messages_not_tracebacks(self):
        self.patched_state()
        spaces.switch_space(self.e_id)
        self.addCleanup(lambda: _write(self.e_file, {'design_work_root': self.e_path, 'tasks': {}}))
        _write(self.e_file, '{')
        rc, _, err = _run(state.main, [])
        self.assertEqual(rc, 2)
        self.assertIn(self.e_file, err)
        self.assertNotIn('Traceback', err)
        _write(self.e_file, {'design_work_root': self.e_path, 'tasks': {}})
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['tasks']['a'] = {'title': 'Дубль', 'dir': self.a_dir}
        _write(self.p_file, cfg)
        rc, _, err = _run(state.main, ['--task', 'a'])
        self.assertEqual(rc, 2)
        self.assertIn('кількох просторах', err)
        self.assertNotIn('Traceback', err)

    def test_state_with_an_unreadable_registry_is_a_message(self):
        self.patched_state()
        self.restore_bytes(os.path.join(self.deai, 'spaces.json'))
        _write(os.path.join(self.deai, 'spaces.json'), '{')
        for argv in ([], ['--task', 'x']):
            with self.subTest(argv=argv):
                rc, out, err = _run(state.main, argv)
                self.assertEqual(rc, 2)
                self.assertIn('spaces-unreadable', err)
                self.assertNotIn('Traceback', err)

    def test_inbox_ambiguous_broken_file_and_unreadable_registry_are_exit_2_not_a_traceback(self):
        self.restore_bytes(self.p_file)
        self.addCleanup(lambda: _write(self.e_file, {'design_work_root': self.e_path, 'tasks': {}}))
        self.restore_bytes(os.path.join(self.deai, 'spaces.json'))
        sbconf.patch_open(self, sbconf.empty_open)           # командні піни ЛІГИ — модулем; мережі нема
        # id у двох просторах
        cfg = _read(self.p_file)
        cfg['tasks']['a'] = {'title': 'Дубль', 'dir': self.a_dir}
        _write(self.p_file, cfg)
        for argv in (['--task', 'a'], ['--task', 'a', 'resolve', 'abcdef', '--reason', 'x']):
            with self.subTest(argv=argv):
                rc, _, err = _run(inbox.main, argv)
                self.assertEqual(rc, 2)
                self.assertIn('кількох просторах', err)
                self.assertNotIn('Traceback', err)
        # битий файл поточного простору
        spaces.switch_space(self.e_id)
        _write(self.e_file, '{')
        rc, _, err = _run(inbox.main, [])
        self.assertEqual(rc, 2)
        self.assertIn('простір недоступний', err)
        self.assertIn(self.e_file, err)
        self.assertNotIn('Traceback', err)
        # реєстр не прочитати
        _write(os.path.join(self.deai, 'spaces.json'), '{')
        for argv in ([], ['--task', 'x']):
            with self.subTest(argv=argv):
                rc, _, err = _run(inbox.main, argv)
                self.assertEqual(rc, 2)
                self.assertIn('spaces-unreadable', err)
                self.assertNotIn('Traceback', err)

    def test_inbox_finds_a_task_in_another_space(self):
        sbconf.patch_open(self, sbconf.empty_open)           # командні піни ЛІГИ — модулем; мережі нема
        rc, out, err = _run(inbox.main, ['--task', 'x'])
        self.assertEqual(rc, 0, err)
        self.assertIn('Inbox задачи «Ікс»', out)
        self.assertIsNone(spaces.request_space_id(), 'main() лишив простір запиту в потоці')
        rc, out, err = _run(inbox.main, ['--task', 'nope'])
        self.assertEqual(rc, 2)
        self.assertIn("'nope'", err)
        spaces.switch_space(self.e_id)
        rc, out, err = _run(inbox.main, [])
        self.assertEqual(rc, 2)
        self.assertIn('у поточному просторі задач нема; є в інших', err)
        self.assertIn('--task <id>', err)
        self.assertNotIn('створи простір', err)
        self.assertNotIn('Traceback', err)

    def run_subprocess(self, script, *args, **overrides):
        e = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', **overrides}
        return subprocess.run([sys.executable, '-B', os.path.join(ROOT, 'bin', script), *args],
                              env=e, cwd=ROOT, capture_output=True, text=True, timeout=60)

    def test_state_with_no_spaces_at_all_exits_2_without_a_traceback(self):
        """Клас «просторів нема»: порожній DEAI_HOME, старого файла нема. Справжній процес —
        щоб довести, що traceback не лізе й з-під `if __name__ == '__main__'`."""
        empty = os.path.join(self.tmp, 'cli-empty-deai')
        for args in ((), ('--task', 'nope')):
            with self.subTest(args=args):
                r = self.run_subprocess(
                    'state.py', *args, HOME=self.home, DEAI_HOME=empty,
                    DC_TASKS_FILE=os.path.join(self.tmp, 'nowhere', 'tasks.json'))
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertNotIn('Traceback', r.stderr)
                self.assertTrue(r.stderr.strip())
        self.assertFalse(os.path.exists(empty), 'читання просторів створило <DEAI_HOME>')

    def test_the_cli_with_an_unreadable_old_file_and_no_spaces_names_the_file(self):
        """Перший запуск зі зіпсованим `tasks.json`: не «створи простір» (воно б відправило людину
        заводити простір поруч із задачами, яких вона не бачить), а «простір недоступний» з назвою файла."""
        empty = os.path.join(self.tmp, 'cli-broken-deai')
        broken = os.path.join(self.tmp, 'cli-broken', 'tasks.json')
        _write(broken, '{"tasks": {"a": {"dir": ')
        for script, args in (('state.py', ()), ('state.py', ('--task', 'a')),
                             ('inbox.py', ()), ('inbox.py', ('--task', 'a'))):
            with self.subTest(script=script, args=args):
                r = self.run_subprocess(script, *args, HOME=self.home, DEAI_HOME=empty, DC_TASKS_FILE=broken)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn('простір недоступний', r.stderr)
                self.assertIn(broken, r.stderr)
                self.assertNotIn('створи простір', r.stderr)
                self.assertNotIn('Traceback', r.stderr)
        self.assertFalse(os.path.exists(empty), 'читання створило <DEAI_HOME>')
        self.assertEqual(_bytes(broken), b'{"tasks": {"a": {"dir": ')


class RegistryPull(Fixture):
    """`bin/registry.py pull`: задача з командного реєстру не ліпиться в старий файл, якщо її id
    уже є в ІНШОМУ просторі цієї машини."""

    def pull(self, legacy_copy, tasks_path):
        """`cmd_pull` без мережі; повертає (stdout, stderr). Реєстр віддає `x` (вона є в `P`) і `fresh`."""
        reg = {'x': {'title': 'Чужий Ікс', 'profile': 'tool'},
               'fresh': {'title': 'Нова', 'profile': 'tool'}}

        class R:
            stdout = 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef'
            stderr = ''
            returncode = 0
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(rg, 'TASKS_PATH', tasks_path), \
                mock.patch.object(rg, 'ensure_clone', lambda cfg, **kw: self.tmp), \
                mock.patch.object(rg, '_git', lambda *a, **k: R()), \
                mock.patch.object(rg, 'read_registry', lambda d: dict(reg)), \
                mock.patch.object(rg, '_work_root', lambda cfg, profile: self.tmp), \
                env(DC_TASKS_FILE=legacy_copy), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rg.cmd_pull(None)
        return out.getvalue(), err.getvalue()

    def legacy_copy(self):
        path = os.path.join(self.tmp, 'pull-copy', 'tasks.json')
        _write(path, _read(self.legacy_file))
        return path

    def test_pull_skips_an_id_that_lives_in_another_space(self):
        copy = self.legacy_copy()
        _, err = self.pull(copy, copy)
        tasks = _read(copy)['tasks']
        self.assertNotIn('x', tasks, 'задача з іншого простору приїхала в старий файл')
        self.assertIn('fresh', tasks, 'контроль: звичайна задача приїхала')
        self.assertIn('x: такий id уже є в іншому просторі — пропущено', err)

    def test_pull_with_an_unreadable_registry_warns_once_and_still_pulls(self):
        """Реєстр просторів не прочитати: pull ЛІГА не блокуємо, але кажемо вголос, і РІВНО раз
        (далі перевірку вимкнено, а не повторюємо помилку на кожну задачу)."""
        self.restore_bytes(os.path.join(self.deai, 'spaces.json'))
        _write(os.path.join(self.deai, 'spaces.json'), '{')
        copy = self.legacy_copy()
        _, err = self.pull(copy, copy)
        tasks = _read(copy)['tasks']
        self.assertIn('x', tasks, 'без перевірки задача мусить приїхати, як до просторів')
        self.assertIn('fresh', tasks)
        self.assertEqual(err.count('реєстр просторів не прочитати (spaces-unreadable)'), 1, err)

    def test_pull_into_a_file_that_is_not_the_legacy_one_does_not_look_at_spaces(self):
        """Інший `TASKS_PATH` (тести підміняють його) — це не простір ЛІГА: до реєстру просторів
        не ліземо взагалі (інакше `npm test` читав би й мігрував справжній `~/.deai`)."""
        copy = self.legacy_copy()
        other = os.path.join(self.tmp, 'pull-other', 'tasks.json')
        _write(other, {'tasks': {}})
        with mock.patch.object(spaces, 'find_task',
                               side_effect=AssertionError('pull поліз у простори')):
            self.pull(copy, other)
        self.assertEqual(sorted(_read(other)['tasks']), ['fresh', 'x'])


class LigaTools(Fixture):
    """Інструменти старого простору (`roots.py`, `ops/reseal_gate.py`; доктора в продукті нема) беруть СТАРИЙ файл, а не файл
    «поточного простору машини»: поточним може бути «Особисте» (`P`), а перевіряють вони ЛІГУ."""

    def test_roots_works_on_the_legacy_space_whatever_space_is_current(self):
        spaces.switch_space(self.p_id)
        seen = []
        with mock.patch.object(roots, 'cmd_status', lambda cfg: seen.append(cfg) or 0):
            self.assertEqual(roots.main(['status']), 0)
        self.assertEqual([sorted(c['tasks']) for c in seen], [['a']])
        self.assertIsNone(spaces.request_space_id(), 'roots.main() лишив простір запиту')

    def test_roots_without_the_layer_is_as_before(self):
        seen = []
        with env(DEAI_HOME=None), mock.patch.object(roots, 'cmd_status',
                                                     lambda cfg: seen.append(cfg) or 0):
            self.assertEqual(roots.main([]), 0)
        self.assertEqual([sorted(c['tasks']) for c in seen], [['a']])

    def roots_status(self, **env_kv):
        """`roots.main(['status'])` із підміненим `cmd_status` → (код, побачені cfg, stderr)."""
        seen = []
        with env(**env_kv), mock.patch.object(roots, 'cmd_status',
                                              lambda cfg: seen.append(cfg) or 0):
            rc, _, err = _run(roots.main, ['status'])
        return rc, seen, err

    def test_roots_migrates_the_legacy_file_in_when_the_registry_lacks_it(self):
        """Реєстр уже є (інший простір), старий файл зʼявився ПІЗНІШЕ: `load_registry()` мігрує
        його в реєстр, і roots працює з ним, а не з файлом поточного простору."""
        deai = os.path.join(self.tmp, 'roots-deai-late')
        legacy = os.path.join(self.tmp, 'roots-late-legacy', 'tasks.json')
        with env(DEAI_HOME=deai, DC_TASKS_FILE=legacy):
            spaces.create_space('Other', 'space-2', os.path.join(self.home, 'deai-work', 'other'))
            self.assertFalse(any(s.get('legacy') for s in spaces.read_registry()['spaces']))
            _write(legacy, {'current': 'late', 'design_work_root': os.path.join(self.tmp, 'late-work'),
                            'tasks': {'late': {'title': 'Пізня',
                                               'dir': os.path.join(self.tmp, 'late-work', 'late')}}})
            rc, seen, err = self.roots_status()
            self.assertEqual(rc, 0, err)
            self.assertEqual([sorted(c['tasks']) for c in seen], [['late']])
            self.assertTrue(any(s.get('legacy') for s in spaces.read_registry()['spaces']))
            self.assertIsNone(spaces.request_space_id(), 'roots.main() лишив простір запиту')

    def test_roots_without_a_legacy_space_is_exit_2_not_the_current_space(self):
        deai = os.path.join(self.tmp, 'roots-deai-none')
        rc, seen, err = self.roots_status(DEAI_HOME=deai, DC_TASKS_FILE=os.path.join(
            self.tmp, 'roots-none', 'tasks.json'))
        self.assertEqual(rc, 2)
        self.assertEqual(seen, [], 'roots взявся за файл не того простору')
        self.assertIn('legacy', err)
        self.assertNotIn('Traceback', err)
        self.assertFalse(os.path.exists(deai))
        # поточний простір не порожній, але старого простору немає — теж відмова, а не мовчазна підміна
        with env(DEAI_HOME=deai, DC_TASKS_FILE=os.path.join(self.tmp, 'roots-none', 'tasks.json')):
            spaces.create_space('Only', 'space-2', os.path.join(self.home, 'deai-work', 'only'))
        rc, seen, err = self.roots_status(DEAI_HOME=deai, DC_TASKS_FILE=os.path.join(
            self.tmp, 'roots-none', 'tasks.json'))
        self.assertEqual((rc, seen), (2, []))
        self.assertIn('legacy', err)

    def test_roots_says_unreadable_when_the_legacy_file_exists_but_cannot_be_read(self):
        """«Старого файла не знайдено» для файла, який лежить поруч, але битий чи завеликий, —
        брехня, що шле дизайнера шукати те, що він має: повідомлення розрізняє «нема» і «не вдалося прочитати»."""
        deai = os.path.join(self.tmp, 'roots-deai-broken')
        legacy = os.path.join(self.tmp, 'roots-broken', 'tasks.json')
        bodies = {'битий JSON': '{',
                  'JSON, але не обʼєкт': '[]',
                  'більше 1 МіБ': json.dumps({'tasks': {}, 'pad': 'x' * spaces.MAX_JSON_BYTES})}
        for what, body in bodies.items():
            with self.subTest(what):
                _write(legacy, body)
                rc, seen, err = self.roots_status(DEAI_HOME=deai, DC_TASKS_FILE=legacy)
                self.assertEqual((rc, seen), (2, []))
                self.assertIn('не вдалося прочитати як JSON-обʼєкт ≤1 МіБ', err)
                self.assertIn(legacy, err)
                self.assertNotIn('не знайдено', err)
                self.assertIn('legacy', err)
                self.assertNotIn('Traceback', err)
                self.assertFalse(os.path.exists(deai), 'roots створив реєстр через нечитабельний файл')
        # контроль: файла справді нема — стара фраза на місці, а «не читається» не зʼявляється
        os.remove(legacy)
        rc, seen, err = self.roots_status(DEAI_HOME=deai, DC_TASKS_FILE=legacy)
        self.assertEqual((rc, seen), (2, []))
        self.assertIn('не знайдено', err)
        self.assertNotIn('не вдалося прочитати', err)

    def test_roots_with_an_unreadable_registry_is_exit_2_not_a_traceback(self):
        self.restore_bytes(os.path.join(self.deai, 'spaces.json'))
        _write(os.path.join(self.deai, 'spaces.json'), '{')
        rc, seen, err = self.roots_status()
        self.assertEqual((rc, seen), (2, []))
        self.assertIn('spaces-unreadable', err)
        self.assertNotIn('Traceback', err)

    def test_reseal_gate_reads_the_legacy_file(self):
        spaces.switch_space(self.p_id)
        self.assertEqual(reseal_gate.load_tasks()['current'], 'a')


class BackgroundThreads(Fixture):
    """Потоки, які запускає сервер, не успадковують `threading.local`."""

    def fake_child(self, stdout=None, stderr=''):
        out = stdout or io.StringIO('{"shot":["main"],"failed":[],"left":[]}')
        err = io.StringIO(stderr)

        class Child:
            returncode = 0
            pid = 2 ** 31 - 1        # неможливий pid: тест, що впав, не посигналить справжній групі

            def __init__(self, *a, **k):
                self.stdout, self.stderr = out, err

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode
        return Child

    def test_shoot_reader_thread_lives_in_the_space_of_its_request(self):
        seen = []

        def spy(line, progress, tail):
            seen.append((spaces.request_space_id(), serve.tasks_path(), spaces.integrations_on()))
        killed = []
        with mock.patch.object(serve.subprocess, 'Popen', self.fake_child(stderr='рядок\n')), \
                mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
                mock.patch.object(serve, '_killpg', lambda proc, sig: killed.append(sig)), \
                mock.patch.object(serve, '_consume_stderr_line', spy):
            st, body = self.post('/t/x/api/shoot', {'it': 'it1'})
        self.assertEqual(st, 200, body)
        self.assertEqual(killed, [], 'тест зʼємки сигналив групі процесів')
        # поточний — старий простір (з інтеграціями), запит — про `x` із `P` (без них)
        self.assertEqual(seen, [(self.p_id, self.p_file, False)])

    def test_shoot_watchdog_timer_lives_in_the_space_of_its_request(self):
        killed = threading.Event()
        seen = []

        class Blocking:
            def read(self):
                killed.wait(10)
                return ''

        def spy_kill(proc, sig):
            seen.append((spaces.request_space_id(), serve.tasks_path()))
            killed.set()
        with mock.patch.object(serve.subprocess, 'Popen', self.fake_child(stdout=Blocking())), \
                mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
                mock.patch.object(serve, '_killpg', spy_kill), \
                mock.patch.object(serve, 'SHOOT_TIMEOUT_S', 0.2):
            st, body = self.post('/t/x/api/shoot', {'it': 'it1'})
        self.assertEqual(st, 200, body)
        self.assertIn('не вклалася', body['error'])
        self.assertEqual(seen, [(self.p_id, self.p_file)])

    @staticmethod
    def unbound_threads(source):
        """Рядки `threading.Thread(...)` / `threading.Timer(...)`, де ціль не загорнута в `_in_space`."""
        bad = []
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'threading'
                    and node.func.attr in ('Thread', 'Timer')):
                continue
            if node.func.attr == 'Thread':
                target = next((k.value for k in node.keywords if k.arg == 'target'), None)
            else:
                target = node.args[1] if len(node.args) > 1 else None
            wrapped = (isinstance(target, ast.Call) and isinstance(target.func, ast.Name)
                       and target.func.id == '_in_space')
            if not wrapped:
                bad.append(node.lineno)
        return sorted(bad)

    def test_every_thread_and_timer_in_serve_is_bound_to_the_request_space(self):
        with open(serve.__file__, encoding='utf-8') as f:
            source = f.read()
        self.assertEqual(self.unbound_threads(source), [],
                         'потік чи таймер у serve.py без `_in_space(...)`: він не успадковує простір запиту')
        # охоронець бачить справжні потоки (інакше він зелений і порожній)
        self.assertGreaterEqual(source.count('threading.Thread(') + source.count('threading.Timer('), 3)

    def test_the_thread_scanner_flags_an_unbound_thread(self):
        src = ("import threading\n"
               "t1 = threading.Thread(target=_in_space(f), daemon=True)\n"
               "t2 = threading.Thread(target=f)\n"
               "t3 = threading.Timer(5, _in_space(f))\n"
               "t4 = threading.Timer(5, lambda: f())\n")
        self.assertEqual(self.unbound_threads(src), [3, 5])


class SpaceRoutes(Fixture):
    """Task 3: `GET /api/spaces`, `GET /api/space-peek`, `POST /api/space-new|space-update|space-switch`."""

    @property
    def reg_path(self):
        return os.path.join(self.deai, 'spaces.json')

    def keep_registry(self):
        self.restore_bytes(self.reg_path)

    def fresh_dir(self, name):
        """Тека майбутнього простору (її знесе cleanup, навіть коли тест створив у ній простір)."""
        p = os.path.join(self.home, 'deai-work', name)
        self.addCleanup(shutil.rmtree, p, True)
        return p

    def peek(self, path):
        return self.jget('/api/space-peek?path=' + urllib.parse.quote(path, safe=''))

    # ---------- GET /api/spaces, /api/space-peek ----------

    def test_listing_shape_and_flags(self):
        st, body = self.jget('/api/spaces')
        self.assertEqual(st, 200)
        self.assertEqual(body['current'], self.legacy_id)
        self.assertEqual([s['id'] for s in body['spaces']], [self.legacy_id, self.p_id, self.e_id])
        self.assertNotIn('off', body)
        for s in body['spaces']:
            # `capabilities` (етап 2а, Task 6) додає `serve.spaces_listing`; `spaces.listing()` і `describe` — без нього
            self.assertEqual(set(s), {'id', 'name', 'color', 'path', 'tasks', 'available',
                                      'integrations', 'legacy', 'capabilities'})
        legacy, p, e = body['spaces']
        self.assertEqual(legacy['capabilities'], {'publish': 'legacy', 'tokens': None, 'comments': 'legacy', 'vcs': 'legacy', 'dashboard': 'legacy'})   # з інтеграціями
        self.assertEqual(p['capabilities'], {'publish': 'static-publish', 'tokens': None, 'comments': None, 'vcs': None, 'dashboard': None})   # без — локальна публікація
        self.assertEqual((legacy['integrations'], legacy['legacy'], legacy['tasks'], legacy['available']),
                         (True, True, 1, True))
        self.assertEqual((p['name'], p['color'], p['path'], p['integrations'], p['legacy']),
                         ('P', 'space-2', self.p_path, False, False))
        self.assertEqual((p['tasks'], p['available']), (2, True))      # `x` і `gone`
        self.assertEqual((e['name'], e['tasks'], e['available']), ('E', 0, True))

    def test_listing_follows_the_current_space_and_marks_a_missing_file_unavailable(self):
        spaces.switch_space(self.p_id)
        self.restore_bytes(self.e_file)
        os.remove(self.e_file)
        body = self.jget('/api/spaces?t=1')[1]          # query-кеш-бастер не ламає маршрут
        self.assertEqual(body['current'], self.p_id)
        e = next(s for s in body['spaces'] if s['id'] == self.e_id)
        self.assertEqual((e['available'], e['tasks']), (False, 0))

    def test_listing_and_peek_are_registry_routes_the_header_and_prefix_do_not_apply(self):
        spaces.switch_space(self.p_id)
        st, body = self.jget('/api/spaces', {'X-Canvas-Task': 'a'})   # заголовок задачі тут не діє
        self.assertEqual((st, body['current']), (200, self.p_id))
        for path in ('/t/a/api/spaces', '/t/x/api/space-peek?path=%2Ftmp'):
            with self.subTest(path=path):
                st, body = self.jget(path)
                self.assertEqual(st, 400)
                self.assertIs(body['ok'], False)

    def test_peek_finds_an_existing_space(self):
        st, body = self.peek(self.p_path)
        self.assertEqual((st, body), (200, {'path': self.p_path, 'exists': True, 'name': 'P',
                                            'color': 'space-2', 'tasks': 2, 'registered': True}))
        before = _md5(self.reg_path)
        self.peek(self.fresh_dir('nothing-here'))
        self.assertEqual(_md5(self.reg_path), before, 'peek щось записав у реєстр')

    def case_variant_of(self, path):
        """Той самий каталог іншим регістром останнього імені; пропуск, коли ФС розрізняє регістр."""
        head, tail = os.path.split(path)
        variant = os.path.join(head, tail.swapcase())
        if variant == path or not os.path.exists(variant) or not os.path.samefile(variant, path):
            self.skipTest('файлова система тимчасової теки розрізняє регістр імен: варіант регістру там — інша тека')
        return variant

    def test_peek_says_registered_for_a_registered_folder_and_its_case_variant(self):
        body = self.peek(self.e_path)[1]
        self.assertEqual((body['exists'], body['registered']), (True, True))
        free = self.fresh_dir('free')
        os.makedirs(free)
        self.assertNotIn('registered', self.peek(free)[1])
        variant = self.case_variant_of(self.p_path)
        body = self.peek(variant)[1]
        self.assertEqual((body['path'], body['exists'], body['registered']), (variant, True, True))

    def test_a_lone_surrogate_or_nul_in_a_typed_path_is_a_400_not_a_dropped_connection(self):
        """JSON приймає `\\ud800` і `\\u0000`; `realpath` на них кидав посеред відповіді."""
        self.keep_registry()
        before = _md5(self.reg_path)
        for bad in (os.path.join(self.home, 'deai-work', '\ud800x'), os.path.join(self.home, 'deai-work', 'a\0b')):
            with self.subTest(path=bad):
                st, body = self.post('/api/space-new', {'name': 'Q', 'path': bad})
                self.assertEqual((st, body['ok'], body['code']), (400, False, 'path-not-absolute'), body)
        self.assertEqual(_md5(self.reg_path), before)

    def test_space_new_refuses_a_case_variant_of_a_registered_folder(self):
        """macOS (APFS без урахування регістру): `…/P` і `…/p` — одна тека. Раніше `space-new` на варіант
        регістру віддавав 200 і дописував у реєстр ДУБЛЬ запису про ту саму теку."""
        variant = self.case_variant_of(self.p_path)
        self.keep_registry()
        before = (_md5(self.reg_path), _md5(self.p_file), _md5(self.legacy_file))
        st, body = self.post('/api/space-new', {'name': 'Дубль', 'color': 'space-4', 'path': variant})
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'path-registered'), body)
        st, body = self.post('/api/space-new', {'name': 'Дубль', 'path': os.path.join(variant, 'sub')})
        self.assertEqual((st, body['ok'], body['code']), (400, False, 'path-overlap'), body)
        self.assertEqual((_md5(self.reg_path), _md5(self.p_file), _md5(self.legacy_file)), before)
        self.assertEqual(sum(1 for sp in spaces.read_registry()['spaces'] if sp['path'] == self.p_path), 1)
        self.assertFalse(os.path.exists(os.path.join(self.p_path, 'sub')), 'відмова створила теку в чужому просторі')

    def test_peek_of_a_missing_folder_and_of_a_bad_path(self):
        missing = self.fresh_dir('nothing-here')
        self.assertEqual(self.peek(missing)[1], {'path': missing, 'exists': False})
        for path in ('deai-work/p', ''):
            with self.subTest(path=path):
                st, body = self.peek(path)
                self.assertEqual((st, body['exists'], body['error']), (200, False, 'path-not-absolute'))
        st, body = self.jget('/api/space-peek')              # без параметра взагалі
        self.assertEqual((st, body['error']), (200, 'path-not-absolute'))
        self.assertFalse(os.path.exists(missing), 'peek створив теку')

    # ---------- POST /api/space-new ----------

    def test_space_new_creates_registers_and_switches(self):
        self.keep_registry()
        path = self.fresh_dir('q')
        st, body = self.post('/api/space-new', {'name': 'Q', 'color': 'space-4', 'path': path})
        self.assertEqual((st, body), (200, {'ok': True, 'id': 'q'}))
        self.assertEqual(spaces.read_registry()['current'], 'q')
        self.assertEqual(_read(os.path.join(path, 'space.json')), {'name': 'Q', 'color': 'space-4'})
        self.assertEqual(_read(os.path.join(path, 'tasks.json')),
                         {'design_work_root': path, 'tasks': {}})
        listed = {s['id']: s for s in self.jget('/api/spaces')[1]['spaces']}['q']
        self.assertEqual((listed['name'], listed['integrations'], listed['tasks'], listed['legacy']),
                         ('Q', False, 0, False))

    def test_space_new_ignores_the_task_header_and_refuses_the_prefix(self):
        self.keep_registry()
        before_old = _md5(self.legacy_file)
        path = self.fresh_dir('q2')
        st, body = self.post('/api/space-new', {'name': 'Q2', 'path': path}, {'X-Canvas-Task': 'a'})
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(_md5(self.legacy_file), before_old)
        before_reg = _md5(self.reg_path)
        st, body = self.post('/t/a/api/space-new', {'name': 'Q3', 'path': self.fresh_dir('q3')})
        self.assertEqual((st, body['ok']), (400, False))
        self.assertEqual(_md5(self.reg_path), before_reg)

    def test_space_new_bad_input_is_400_with_a_code(self):
        before = _md5(self.reg_path)
        cases = [
            ({'name': 'Q', 'path': self.home}, 'path-too-broad'),
            ({'name': 'Q', 'path': 'deai-work/q'}, 'path-not-absolute'),
            ({'name': 'Q', 'path': 5}, 'path-not-absolute'),               # не рядок — без винятку
            ({'name': 'Q'}, 'path-not-absolute'),
            ({'name': '  ', 'path': self.fresh_dir('q')}, 'name-required'),
            ({'path': self.fresh_dir('q')}, 'name-required'),
            ({'name': 'Q', 'path': os.path.join(self.p_path, 'inner')}, 'path-overlap'),
            ({'name': 'Q', 'path': os.path.dirname(self.p_path)}, 'path-overlap'),          # над P і E
        ]
        for payload, code in cases:
            with self.subTest(payload=payload):
                st, body = self.post('/api/space-new', payload)
                self.assertEqual((st, body['ok'], body['code']), (400, False, code), body)
                self.assertTrue(body['error'])
        self.assertEqual(_md5(self.reg_path), before, 'відмова щось записала в реєстр')

    def test_space_new_conflicts_are_409(self):
        """`path-registered` і `task-id-collision` — конфлікт зі СТАНОМ (409), решта — поганий ввід (400)."""
        self.keep_registry()
        path = self.fresh_dir('q4')
        self.assertEqual(self.post('/api/space-new', {'name': 'Q4', 'path': path})[0], 200)
        st, body = self.post('/api/space-new', {'name': 'Q4 удруге', 'path': path})
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'path-registered'), body)
        # тека з власним tasks.json, де вже є `a` зі старого простору
        clash = self.fresh_dir('clash')
        _write(os.path.join(clash, 'tasks.json'), {'tasks': {'a': {'title': 'Дубль'}, 'fresh': {}}})
        before = _md5(self.reg_path)
        st, body = self.post('/api/space-new', {'name': 'Clash', 'path': clash})
        self.assertEqual((st, body['code']), (409, 'task-id-collision'), body)
        self.assertIn('a', body['error'])
        self.assertEqual(_md5(self.reg_path), before)
        self.assertFalse(os.path.exists(os.path.join(clash, 'space.json')), 'простір створено попри колізію')

    def test_space_new_with_an_unreadable_tasks_file_of_another_space_is_503(self):
        """Файл задач P не читається: id в ньому невидимі, колізію з ними не перевірити — простір НЕ
        створюється (інакше `task-id-collision` пропускав би дубль)."""
        self.keep_registry()
        self.restore_bytes(self.p_file)
        before = _md5(self.reg_path)
        q = self.fresh_dir('q6')
        for raw in ('{ битий', '{"tasks": []}', '{"tasks": {"x": 5}}'):
            with self.subTest(raw=raw):
                _write(self.p_file, raw)
                st, body = self.post('/api/space-new', {'name': 'Q6', 'path': q})
                self.assertEqual((st, body['ok'], body['code'], body['path']),
                                 (503, False, 'space-unavailable', self.p_file), body)
                self.assertEqual(_md5(self.reg_path), before)
                self.assertFalse(os.path.exists(q), 'теку створено попри відмову')

    def test_space_new_with_an_unreadable_adopted_tasks_file_is_503(self):
        self.keep_registry()
        adopt = self.fresh_dir('adopt-broken')
        _write(os.path.join(adopt, 'tasks.json'), '{ битий')
        before = _md5(self.reg_path)
        st, body = self.post('/api/space-new', {'name': 'Adopt', 'path': adopt})
        self.assertEqual((st, body['code'], body['path']),
                         (503, 'space-unavailable', os.path.join(adopt, 'tasks.json')), body)
        self.assertEqual(_md5(self.reg_path), before)
        self.assertFalse(os.path.exists(os.path.join(adopt, 'space.json')))

    def test_space_new_adopts_a_folder_with_its_own_tasks(self):
        self.keep_registry()
        adopt = self.fresh_dir('adopt')
        _write(os.path.join(adopt, 'tasks.json'), {'tasks': {'own1': {}, 'own2': {}}})
        st, body = self.post('/api/space-new', {'name': 'Adopt', 'path': adopt})
        self.assertEqual((st, body['id']), (200, 'adopt'))
        listed = {s['id']: s for s in self.jget('/api/spaces')[1]['spaces']}['adopt']
        self.assertEqual(listed['tasks'], 2)

    def test_an_unwritable_registry_is_503_not_swallowed_by_the_route(self):
        self.keep_registry()
        before = _md5(self.reg_path)
        boom = spaces.SpacesError('spaces-unwritable', self.reg_path, 'disk')
        with mock.patch.object(spaces, '_write_locked', side_effect=boom):
            st, body = self.post('/api/space-new', {'name': 'Q5', 'path': self.fresh_dir('q5')})
        self.assertEqual((st, body['code'], body['path']), (503, 'spaces-unwritable', self.reg_path))
        self.assertEqual(_md5(self.reg_path), before)

    # ---------- POST /api/space-update ----------

    def test_space_update_writes_space_json(self):
        self.restore_bytes(os.path.join(self.p_path, 'space.json'))
        st, body = self.post('/api/space-update', {'id': self.p_id, 'name': 'Pp'})
        self.assertEqual((st, body), (200, {'ok': True, 'id': self.p_id, 'name': 'Pp', 'color': 'space-2'}))
        self.assertEqual(_read(os.path.join(self.p_path, 'space.json')), {'name': 'Pp', 'color': 'space-2'})
        st, body = self.post('/api/space-update', {'id': self.p_id, 'color': 'space-5'})
        self.assertEqual((st, body['name'], body['color']), (200, 'Pp', 'space-5'))
        listed = {s['id']: s for s in self.jget('/api/spaces')[1]['spaces']}[self.p_id]
        self.assertEqual((listed['name'], listed['color']), ('Pp', 'space-5'))

    def test_space_update_refuses_an_empty_name_and_an_unknown_id(self):
        space_json = os.path.join(self.p_path, 'space.json')
        before = _md5(space_json)
        st, body = self.post('/api/space-update', {'id': self.p_id, 'name': '   '})
        self.assertEqual((st, body['ok'], body['code']), (400, False, 'name-required'), body)
        self.assertEqual(_md5(space_json), before)
        for payload in ({'id': 'nope', 'name': 'X'}, {'name': 'X'}, {'id': ['p'], 'name': 'X'}):
            with self.subTest(payload=payload):
                st, body = self.post('/api/space-update', payload)
                self.assertEqual((st, body['ok'], body['code']), (404, False, 'unknown-space'), body)
        self.assertEqual(_md5(space_json), before)

    # ---------- POST /api/space-switch ----------

    def test_space_switch_returns_the_current_task_of_the_space(self):
        self.keep_registry()
        st, body = self.post('/api/space-switch', {'id': self.p_id})
        self.assertEqual((st, body), (200, {'ok': True, 'current': self.p_id, 'task': 'x'}))
        self.assertEqual(spaces.read_registry()['current'], self.p_id)
        self.assertEqual(self.jget('/api/task')[1]['id'], 'x')        # наступні запити — вже в P
        # порожній простір — задачі нема
        st, body = self.post('/api/space-switch', {'id': self.e_id}, {'X-Canvas-Task': 'a'})
        self.assertEqual((st, body), (200, {'ok': True, 'current': self.e_id, 'task': None}))
        # застарілий `current` у файлі простору — теж «нема»
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['current'] = 'ghost'
        _write(self.p_file, cfg)
        self.assertEqual(self.post('/api/space-switch', {'id': self.p_id})[1]['task'], None)

    def test_space_switch_unknown_id_is_404_and_changes_nothing(self):
        before = _md5(self.reg_path)
        for payload in ({'id': 'nope'}, {}, {'id': 5}):
            with self.subTest(payload=payload):
                st, body = self.post('/api/space-switch', payload)
                self.assertEqual((st, body['ok'], body['code']), (404, False, 'unknown-space'), body)
        self.assertEqual(_md5(self.reg_path), before)
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id)


class TaskResponses(Fixture):
    """`/api/task`, `/api/tasks`, `/api/tasks-overview` називають простір; `?all=1` — усі простори."""

    def test_task_names_its_space_and_the_comment_channel(self):
        st, body = self.jget('/api/task')
        self.assertEqual(st, 200)
        # `capabilities` — поле відповіді (етап 2а, Task 6), його додає `serve.space_view`, а не `spaces.describe`
        self.assertEqual(body['space'], {'id': self.legacy_id, 'name': os.path.basename(os.path.dirname(self.a_dir)),
                                         'color': 'space-1', 'path': os.path.dirname(self.a_dir),
                                         'legacy': True, 'integrations': True,
                                         'capabilities': {'publish': 'legacy', 'tokens': None,
                                                          'comments': 'legacy', 'vcs': 'legacy', 'dashboard': 'legacy'}})
        self.assertEqual(body['comment_channel'], 'dc/a')
        # задача іншого простору — його простір, і без інтеграцій каналу коментарів немає
        st, body = self.jget('/t/x/api/task')
        self.assertEqual((st, body['id'], body['space']['id'], body['space']['integrations']),
                         (200, 'x', self.p_id, False))
        self.assertEqual((body['space']['name'], body['space']['color']), ('P', 'space-2'))
        self.assertIsNone(body['comment_channel'])

    def test_comment_channel_honours_comment_project_where_integrations_are_on(self):
        self.restore_bytes(self.legacy_file)
        cfg = _read(self.legacy_file)
        cfg['tasks']['a']['comment_project'] = 'dc/custom'
        _write(self.legacy_file, cfg)
        self.assertEqual(self.jget('/api/task')[1]['comment_channel'], 'dc/custom')
        # без інтеграцій навіть заданий `comment_project` каналу не дає
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['tasks']['x']['comment_project'] = 'dc/p-custom'
        _write(self.p_file, cfg)
        self.assertIsNone(self.jget('/t/x/api/task')[1]['comment_channel'])

    def test_tasks_list_is_of_the_request_space_and_names_it(self):
        st, body = self.jget('/api/tasks')
        self.assertEqual((st, body['current'], [t['id'] for t in body['tasks']]), (200, 'a', ['a']))
        self.assertEqual(body['space']['id'], self.legacy_id)
        self.assertNotIn('space', body['tasks'][0], 'без all=1 рядки лишаються як були')
        self.assertEqual(set(body['tasks'][0]), {'id', 'title', 'jira', 'profile', 'missing', 'tags'})   # `tags` — 4b-3
        spaces.switch_space(self.p_id)
        body = self.jget('/api/tasks')[1]
        self.assertEqual((body['current'], body['space']['id']), ('x', self.p_id))
        self.assertEqual({t['id']: t['missing'] for t in body['tasks']}, {'x': False, 'gone': True})

    def test_tasks_all_lists_every_space_and_labels_each_row(self):
        st, body = self.jget('/api/tasks?all=1')
        self.assertEqual(st, 200)
        self.assertEqual({t['id']: t['space'] for t in body['tasks']},
                         {'a': self.legacy_id, 'x': self.p_id, 'gone': self.p_id})
        self.assertEqual({t['id']: t['missing'] for t in body['tasks']},
                         {'a': False, 'x': False, 'gone': True})
        self.assertEqual(set(body['tasks'][0]), {'id', 'title', 'jira', 'profile', 'missing', 'tags', 'space'})   # `tags` — 4b-3

    def test_tasks_all_restores_the_request_space_for_the_rest_of_the_response(self):
        """Обхід просторів не лишає запит у ОСТАННЬОМУ з них: `space` і `current` у відповіді —
        простору запиту (останній у реєстрі — порожній `E`)."""
        for sid, cur in ((self.legacy_id, 'a'), (self.p_id, 'x')):
            with self.subTest(current=sid):
                spaces.switch_space(sid)
                body = self.jget('/api/tasks?all=1')[1]
                self.assertEqual((body['space']['id'], body['current']), (sid, cur))
                self.assertEqual(len(body['tasks']), 3)

    def test_only_all_equal_one_means_all(self):
        for q in ('?all=0', '?all=', '?all=true', '?al=1', ''):
            with self.subTest(query=q):
                body = self.jget('/api/tasks' + q)[1]
                self.assertEqual([t['id'] for t in body['tasks']], ['a'])

    def test_tasks_all_skips_an_unreadable_space_instead_of_failing(self):
        self.restore_bytes(self.p_file)
        _write(self.p_file, '{ битий')
        st, body = self.jget('/api/tasks?all=1')
        self.assertEqual((st, sorted(t['id'] for t in body['tasks'])), (200, ['a']))
        # Поточний простір з битим файлом: звичайний список — 503, а `?all=1` від простору запиту НЕ
        # залежить: решта просторів на місці, `current` — `null`, `space` каже, ЯКИЙ простір битий.
        spaces.switch_space(self.p_id)
        st, body = self.jget('/api/tasks')
        self.assertEqual((st, body['code']), (503, 'space-unavailable'))
        st, body = self.jget('/api/tasks?all=1')
        self.assertEqual((st, [t['id'] for t in body['tasks']], body['current'], body['space']['id']),
                         (200, ['a'], None, self.p_id))

    def test_tasks_all_with_a_dangling_current_space_still_lists_everything(self):
        self.restore_bytes(os.path.join(self.deai, 'spaces.json'))
        reg = spaces.read_registry()
        reg['current'] = 'ghost'
        _write(os.path.join(self.deai, 'spaces.json'), reg)
        st, body = self.jget('/api/tasks?all=1')
        self.assertEqual(st, 200)
        self.assertEqual({t['id']: t['space'] for t in body['tasks']},
                         {'a': self.legacy_id, 'x': self.p_id, 'gone': self.p_id})
        self.assertEqual((body['current'], body['space']), (None, None))
        # без all — як і було: порожній список (простору запиту нема)
        self.assertEqual(self.jget('/api/tasks'), (200, {'current': None, 'tasks': [], 'space': None}))

    MALFORMED = ({'tasks': []}, {'tasks': None}, {'tasks': 'x'}, {'tasks': {'x': 5}}, {'tasks': {'x': None}},
                 {'tasks': {'x': {}, 'y': []}}, [], 5)

    def test_tasks_all_skips_a_space_with_a_malformed_tasks_shape(self):
        """`{"tasks": []}` чи `{"tasks": {"x": 5}}` у НЕпоточному просторі валили `AttributeError` у
        `tasks_by_recent`, і зʼєднання рвалось без відповіді на ВЕСЬ список."""
        self.restore_bytes(self.p_file)
        for cfg in self.MALFORMED:
            with self.subTest(cfg=cfg):
                _write(self.p_file, cfg)
                st, body = self.jget('/api/tasks?all=1')
                self.assertEqual((st, sorted(t['id'] for t in body['tasks'])), (200, ['a']))

    MIXED_OPENED = {'tasks': {'x': {'opened': 5}, 'y': {'opened': '2026-01-01T10:00:00Z'},
                              'z': {'opened': ['2026']}, 'w': {'opened': None},
                              'v': {'opened': '2026-02-01T10:00:00Z'}, 'u': {'opened': True}}}

    def test_mixed_opened_types_do_not_tear_the_task_lists(self):
        """`opened` пише і рука: число, список, `true`, `null` поряд з ISO-рядками. Ключ сортування
        `tasks_by_recent` порівнював би `int` із `str` — `TypeError`, зʼєднання рвалось без
        відповіді (спершу `?all=1` мовчки викидав такий простір цілком). Тепер ознакою є лише
        рядок; решта — «без мітки», у хвіст у порядку файла. Те саме для списку, огляду й `?all=1`."""
        self.restore_bytes(self.p_file)
        _write(self.p_file, self.MIXED_OPENED)
        want = ['v', 'y', 'x', 'z', 'w', 'u']               # рядки за спаданням, далі — порядок файла
        spaces.switch_space(self.p_id)
        st, body = self.jget('/api/tasks')
        self.assertEqual((st, [t['id'] for t in body['tasks']]), (200, want))
        st, body = self.jget('/api/tasks-overview')
        self.assertEqual((st, [r['id'] for r in body['mine']]), (200, want))
        st, body = self.jget('/api/tasks?all=1')
        self.assertEqual((st, [t['id'] for t in body['tasks'] if t['space'] == self.p_id]), (200, want))
        self.assertIn('a', [t['id'] for t in body['tasks']])         # сусід-простір на місці

    def test_a_malformed_shape_of_the_current_space_is_503_not_a_dropped_connection(self):
        self.restore_bytes(self.p_file)
        spaces.switch_space(self.p_id)
        for cfg in self.MALFORMED:
            with self.subTest(cfg=cfg):
                _write(self.p_file, cfg)
                for path in ('/api/task', '/api/tasks', '/api/tasks-overview'):
                    st, body = self.jget(path)
                    self.assertEqual((st, body['code'], body['path']), (503, 'space-unavailable', self.p_file), path)

    def test_load_tasks_rejects_a_malformed_shape_with_the_layer_on(self):
        self.restore_bytes(self.p_file)
        for cfg in self.MALFORMED:
            with self.subTest(cfg=cfg):
                _write(self.p_file, cfg)
                with spaces.request_space(self.p_id):
                    with self.assertRaises(serve.SpaceUnavailable) as cm:
                        serve.load_tasks()
                self.assertEqual(cm.exception.path, self.p_file)
        _write(self.p_file, {'tasks': {}})                         # порожній обʼєкт задач — валідний
        with spaces.request_space(self.p_id):
            self.assertEqual(serve.load_tasks()['tasks'], {})
        _write(self.p_file, {'design_work_root': self.p_path})     # без ключа `tasks` — теж як було
        with spaces.request_space(self.p_id):
            self.assertNotIn('tasks', serve.load_tasks())

    def test_tasks_all_keeps_a_duplicate_id_visible_in_both_spaces(self):
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['tasks']['a'] = {'title': 'Дубль', 'dir': self.a_dir, 'profile': 'tool'}
        _write(self.p_file, cfg)
        rows = [(t['id'], t['space']) for t in self.jget('/api/tasks?all=1')[1]['tasks'] if t['id'] == 'a']
        self.assertEqual(sorted(rows), sorted([('a', self.legacy_id), ('a', self.p_id)]))

    def test_tasks_all_helper_gives_the_request_space_back(self):
        """Те саме без HTTP: хто кличе обхід усередині `request_space`, лишається в своєму."""
        with spaces.request_space(self.p_id):
            rows = serve._all_space_task_rows()
            self.assertEqual(spaces.request_space_id(), self.p_id)
        self.assertEqual(sorted(r['id'] for r in rows), ['a', 'gone', 'x'])
        self.assertIsNone(spaces.request_space_id())

    def test_overview_names_the_space(self):
        body = self.jget('/api/tasks-overview')[1]
        self.assertEqual((body['current'], body['space']['id']), ('a', self.legacy_id))
        self.assertEqual([r['id'] for r in body['mine']], ['a'])
        spaces.switch_space(self.p_id)
        body = self.jget('/api/tasks-overview')[1]
        self.assertEqual((body['current'], body['space']['id']), ('x', self.p_id))
        self.assertEqual([r['id'] for r in body['mine']], ['x', 'gone'])
        self.assertEqual(body['space']['integrations'], False)


class TaskSwitch(Fixture):
    """`task-switch` між просторами: файл задач цільового простору, ПОТІМ `current` реєстру."""

    @property
    def reg_path(self):
        return os.path.join(self.deai, 'spaces.json')

    def test_switch_to_a_task_of_another_space_switches_the_space_too(self):
        self.restore_bytes(self.reg_path)
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['current'] = 'gone'
        _write(self.p_file, cfg)
        old_before = _md5(self.legacy_file)
        st, body = self.post('/api/task-switch', {'id': 'x'})
        self.assertEqual((st, body), (200, {'ok': True, 'current': 'x', 'space': self.p_id}))
        self.assertEqual(spaces.read_registry()['current'], self.p_id)
        after = _read(self.p_file)
        self.assertEqual(after['current'], 'x')
        self.assertIn('opened', after['tasks']['x'])             # `mark_opened` — у файлі P, не в старому
        self.assertEqual(_md5(self.legacy_file), old_before, 'старий файл змінився від перемикання в P')
        self.assertEqual(self.jget('/api/task')[1]['id'], 'x')

    def test_switch_back_to_the_old_space(self):
        self.restore_bytes(self.legacy_file)
        spaces.switch_space(self.p_id)
        p_before = _md5(self.p_file)
        st, body = self.post('/api/task-switch', {'id': 'a'})
        self.assertEqual((st, body), (200, {'ok': True, 'current': 'a', 'space': self.legacy_id}))
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id)
        self.assertIn('opened', _read(self.legacy_file)['tasks']['a'])
        self.assertEqual(_md5(self.p_file), p_before)

    def test_unknown_or_malformed_id_is_404_and_changes_nothing(self):
        before = (_md5(self.reg_path), _md5(self.legacy_file), _md5(self.p_file))
        for payload in ({'id': 'nope'}, {}, {'id': 5}, {'id': ['x']}, {'id': None}, {'id': ''}):
            with self.subTest(payload=payload):
                st, _ = self.post_raw('/api/task-switch', payload)
                self.assertEqual(st, 404)
        self.assertEqual((_md5(self.reg_path), _md5(self.legacy_file), _md5(self.p_file)), before)

    def test_a_task_that_vanished_between_the_lookup_and_the_read_is_404(self):
        """`find_task` сказав «є в P», а до читання файла задачу вилучили (друге вікно, агент): 404, а
        не `current` на задачу, якої нема, і не перемкнутий на P реєстр."""
        self.restore_bytes(self.reg_path)
        self.restore_bytes(self.p_file)
        p_space = next(s for s in spaces.read_registry()['spaces'] if s['id'] == self.p_id)
        before = (_md5(self.reg_path), _md5(self.p_file), _md5(self.legacy_file))
        with mock.patch.object(spaces, 'find_task', return_value=p_space):
            st, _ = self.post_raw('/api/task-switch', {'id': 'vanished'})
        self.assertEqual(st, 404)
        self.assertEqual((_md5(self.reg_path), _md5(self.p_file), _md5(self.legacy_file)), before)

    def test_an_id_in_two_spaces_is_ambiguous_409_and_nothing_moves(self):
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['tasks']['a'] = {'title': 'Дубль', 'dir': self.a_dir, 'profile': 'tool'}
        _write(self.p_file, cfg)
        before = (_md5(self.reg_path), _md5(self.legacy_file), _md5(self.p_file))
        st, body = self.post('/api/task-switch', {'id': 'a'})
        self.assertEqual((st, body['code']), (409, 'ambiguous-task'))
        self.assertEqual((_md5(self.reg_path), _md5(self.legacy_file), _md5(self.p_file)), before)

    def test_the_tasks_file_is_written_before_the_registry(self):
        """Порядок запису з спеки: спершу `current` у файлі цільового простору, потім `current`
        реєстру. Збій другого кроку лишає файл уже оновленим (наступний `space-switch` у цей
        простір відкриє саме цю задачу), а збій першого НЕ перемикає реєстр на простір, у якому
        `current` ще старий."""
        self.restore_bytes(self.reg_path)
        self.restore_bytes(self.p_file)
        cfg = _read(self.p_file)
        cfg['current'] = 'gone'
        _write(self.p_file, cfg)
        boom = spaces.SpacesError('spaces-unwritable', self.reg_path, 'disk')
        with mock.patch.object(spaces, 'switch_space', side_effect=boom):
            st, body = self.post('/api/task-switch', {'id': 'x'})
        self.assertEqual((st, body['code']), (503, 'spaces-unwritable'))
        self.assertEqual(_read(self.p_file)['current'], 'x', 'файл задач не записано до реєстру')
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id)
        # і навпаки: файл не записався — реєстр не торкаємо
        _write(self.p_file, cfg)
        failing = serve.SpaceUnavailable(self.p_file)
        with mock.patch.object(serve, 'save_tasks', side_effect=failing):
            st, body = self.post('/api/task-switch', {'id': 'x'})
        self.assertEqual((st, body['code']), (503, 'space-unavailable'))
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id,
                         'реєстр перемкнуто, хоч файл задач не записано')
        self.assertEqual(_read(self.p_file)['current'], 'gone')

    def test_concurrent_password_writes_and_switches_never_cross_the_files(self):
        """Потік 1 пише пароль у `a` (старий простір), потік 2 вдвічі частіше перемикає між `a`
        і `x` (простір змінюється щоразу): жоден запис не лягає в чужий файл. Останнє
        перемикання — на `x`: у P це `x`, а в старому файлі `current` лишився `a` (запис в
        чужий файл дав би там `x` або `a` у задачах P)."""
        for path in (self.reg_path, self.legacy_file, self.p_file):
            self.restore_bytes(path)
        cfg = _read(self.p_file)
        cfg['current'] = 'gone'
        _write(self.p_file, cfg)
        errors = []

        def passwords():
            for i in range(200):
                st, body = self.post('/t/a/api/preview-password',
                                     {'password': 'abcd' if i % 2 == 0 else 'efgh'})
                if st != 200:
                    errors.append(('password', i, st, body))

        def switches():
            for i in range(200):
                st, body = self.post('/api/task-switch', {'id': 'a' if i % 2 == 0 else 'x'})
                if st != 200:
                    errors.append(('switch', i, st, body))
        threads = [threading.Thread(target=passwords), threading.Thread(target=switches)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        self.assertEqual(errors, [])
        old, new = _read(self.legacy_file), _read(self.p_file)     # обидва — валідний JSON
        self.assertEqual(sorted(old['tasks']), ['a'], 'у старий файл потрапили чужі задачі')
        self.assertEqual(sorted(new['tasks']), ['gone', 'x'], 'у файл P потрапили чужі задачі')
        self.assertEqual(old['current'], 'a', 'перемикання на `x` записалось у старий файл')
        self.assertEqual(new['current'], 'x', 'перемикання на `x` не дійшло до файла P')
        self.assertIn(old['tasks']['a'].get('preview_password', 'abcd'), ('abcd', 'efgh'))
        self.assertNotIn('preview_password', new['tasks']['x'])
        self.assertEqual(spaces.read_registry()['current'], self.p_id)


class TaskNew(Fixture):
    """`task-new` між просторами: куди лягає задача, що вона отримує, що відмовляється."""

    @property
    def reg_path(self):
        return os.path.join(self.deai, 'spaces.json')

    def setUp(self):
        super().setUp()
        for path in (self.reg_path, self.legacy_file, self.p_file):
            self.restore_bytes(path)

    def made(self, *names):
        """Теки, що їх може лишити `task-new` (стирає cleanup)."""
        for p in names:
            self.addCleanup(shutil.rmtree, p, True)

    def old_dir(self, tid):
        return os.path.join(os.path.dirname(self.a_dir), tid)

    def test_without_space_the_task_goes_to_the_integrations_space_and_that_becomes_current(self):
        """Усі сьогоднішні виклики без `space` — потік dev-pipeline ЛІГА: навіть коли
        поточний простір — «Особисте», задача йде у простір з інтеграціями."""
        self.made(self.old_dir('n1'))
        spaces.switch_space(self.p_id)
        p_before = _md5(self.p_file)
        st, body = self.post('/api/task-new', {'id': 'n1', 'title': 'N', 'profile': 'tool'})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['ok'], body['id'], body['space'], body['space_switched']),
                         (True, 'n1', self.legacy_id, True))
        old = _read(self.legacy_file)
        self.assertEqual(old['current'], 'n1')
        self.assertEqual((old['tasks']['n1']['dir'], old['tasks']['n1']['profile']),
                         (self.old_dir('n1'), 'tool'))
        # Сусіди нової задачі вижили: конфіг ЦІЛЬОВОГО простору прочитано ПІСЛЯ фіксації простору.
        # Інакше в старий файл ліг би конфіг ПОТОЧНОГО (P): `a` зник би, а `x`/`gone` зʼявились.
        self.assertEqual(sorted(old['tasks']), ['a', 'n1'])
        self.assertEqual(old['tasks']['a']['title'], 'Альфа')
        self.assertEqual(_md5(self.p_file), p_before, 'задача лягла у файл поточного P')
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id)
        self.assertEqual(self.jget('/api/task')[1]['id'], 'n1')

    def test_into_a_space_without_integrations(self):
        self.made(os.path.join(self.p_path, 'n2'))
        old_before = _md5(self.legacy_file)
        st, body = self.post('/api/task-new', {'id': 'n2', 'title': 'N2', 'space': self.p_id,
                                               'profile': 'united', 'jira': 'LIGA-1'})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['space'], body['dir'], body['cloned'], body['registered']),
                         (self.p_id, os.path.join(self.p_path, 'n2'), False, False))
        # Сусіди вижили: тут поточний простір на вході — старий, і прочитай `task-new` конфіг
        # ДО фіксації простору P, у файл P лягла б копія старого (`x` і `gone` зникли б).
        self.assertEqual(sorted(_read(self.p_file)['tasks']), ['gone', 'n2', 'x'])
        self.assertEqual(_read(self.p_file)['tasks']['x']['title'], 'Ікс')
        task = _read(self.p_file)['tasks']['n2']
        self.assertEqual(task['dir'], os.path.join(self.p_path, 'n2'))
        self.assertIsNone(task['profile'])                       # `profile` із тіла ігнорується
        self.assertNotIn('gitlab', task)
        self.assertEqual((task['title'], task['jira']), ('N2', 'LIGA-1'))
        self.assertEqual(_read(self.p_file)['current'], 'n2')
        self.assertTrue(os.path.isfile(os.path.join(self.p_path, 'n2', 'iterations', 'it1', 'index.html')))
        self.assertEqual(spaces.read_registry()['current'], self.p_id)      # став поточним
        self.assertEqual(_md5(self.legacy_file), old_before)                 # старий файл — байт-у-байт
        st, body = self.jget('/api/task')
        self.assertEqual((st, body['id'], body['profile'], body['comment_channel']), (200, 'n2', None, None))

    BROKEN = ('{ битий', '[]', '{"tasks": []}', '{"tasks": {"x": 5}}', '{"tasks": null}')

    def test_an_unreadable_tasks_file_of_another_space_blocks_task_new(self):
        """Id, що лежить у нечитабельному файлі простору P, невидимий для `find_task`: створити такий
        самий деінде — дубль через простори. Відмова 503 `space-unavailable` з назвою файла, у будь-який
        цільовий простір (дефолтний, явний і сам битий)."""
        before = (_md5(self.reg_path), _md5(self.legacy_file))
        for raw in self.BROKEN:
            _write(self.p_file, raw)
            for payload in ({'id': 'n12', 'profile': 'tool'},                  # дефолт — старий простір
                            {'id': 'n12', 'space': self.e_id},                  # явний — порожній E
                            {'id': 'n12', 'space': self.legacy_id},
                            {'id': 'n12', 'space': self.p_id}):                 # сам битий
                with self.subTest(raw=raw, payload=payload):
                    st, body = self.post('/api/task-new', payload)
                    self.assertEqual((st, body['ok'], body['code'], body['path']),
                                     (503, False, 'space-unavailable', self.p_file), body)
        self.assertEqual((_md5(self.reg_path), _md5(self.legacy_file)), before)
        self.assertEqual(_read(self.e_file), {'design_work_root': self.e_path, 'tasks': {}})
        self.assertFalse(os.path.exists(self.old_dir('n12')))
        self.assertFalse(os.path.exists(os.path.join(self.e_path, 'n12')))

    def test_the_old_file_unreadable_blocks_task_new_into_another_space_too(self):
        _write(self.legacy_file, '{ битий')
        st, body = self.post('/api/task-new', {'id': 'n13', 'space': self.p_id})
        self.assertEqual((st, body['code'], body['path']), (503, 'space-unavailable', self.legacy_file))
        self.assertNotIn('n13', _read(self.p_file)['tasks'])

    def test_a_missing_tasks_file_of_another_space_does_not_block_task_new(self):
        """Файла нема — це «недоступний простір» (`available: false`), а не битий: id там не сховати."""
        self.made(os.path.join(self.p_path, 'n14'))
        self.restore_bytes(self.e_file)
        os.remove(self.e_file)
        st, body = self.post('/api/task-new', {'id': 'n14', 'space': self.p_id})
        self.assertEqual(st, 200, body)

    def test_a_registry_that_cannot_be_switched_after_creation_is_still_a_200(self):
        """Задачу створено (теку, запис, коміт) — 503 після цього збрехав би, що її нема й можна
        повторити. Відповідь 200 каже чесно: створено, а простір не перемкнуто."""
        self.made(os.path.join(self.p_path, 'n10'))
        boom = spaces.SpacesError('spaces-unwritable', self.reg_path, 'disk')
        with mock.patch.object(spaces, 'switch_space', side_effect=boom):
            st, body = self.post('/api/task-new', {'id': 'n10', 'space': self.p_id})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['ok'], body['id'], body['space'], body['space_switched']),
                         (True, 'n10', self.p_id, False))
        self.assertIn('n10', _read(self.p_file)['tasks'])
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id)

    def test_an_os_error_while_creating_is_a_500_with_a_code(self):
        before = (_md5(self.legacy_file), _md5(self.p_file))
        with mock.patch.object(serve, 'task_new', side_effect=OSError('disk full')):
            st, body = self.post('/api/task-new', {'id': 'n11', 'space': self.p_id})
        self.assertEqual((st, body['ok'], body['code']), (500, False, 'task-create-failed'), body)
        self.assertIn('disk full', body['error'])
        self.assertEqual((_md5(self.legacy_file), _md5(self.p_file)), before)
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id)    # простір не перемкнуто

    def test_a_non_string_profile_is_400_bad_profile(self):
        before = (_md5(self.legacy_file), _md5(self.p_file))
        for profile in (5, ['united'], {'a': 1}, True, 0, False):
            for space in (None, self.p_id):
                with self.subTest(profile=profile, space=space):
                    payload = {'id': 'n15', 'profile': profile}
                    if space:
                        payload['space'] = space
                    st, body = self.post('/api/task-new', payload)
                    self.assertEqual((st, body['ok'], body['code']), (400, False, 'bad-profile'), body)
        self.assertEqual((_md5(self.legacy_file), _md5(self.p_file)), before)
        self.assertFalse(os.path.exists(self.old_dir('n15')))
        self.made(os.path.join(self.p_path, 'n16'), self.old_dir('n16'))
        for profile in (None, '', 'tool'):                      # рядок і відсутнє — як було
            with self.subTest(profile=profile):
                st, _ = self.post('/api/task-new', {'id': 'n16', 'space': self.p_id, 'profile': profile})
                self.assertEqual(st, 200)
                cfg = _read(self.p_file)
                del cfg['tasks']['n16']
                _write(self.p_file, cfg)

    def test_a_title_with_markup_is_escaped_in_the_starter_page(self):
        """Назву вводить людина (форма «Нова задача»): у стартовий `index.html` вона лягає екранованою."""
        self.made(os.path.join(self.p_path, 'n17'))
        title = '<script>alert(1)</script> & "x"'
        st, body = self.post('/api/task-new', {'id': 'n17', 'space': self.p_id, 'title': title})
        self.assertEqual(st, 200, body)
        with open(os.path.join(self.p_path, 'n17', 'iterations', 'it1', 'index.html'), encoding='utf-8') as f:
            page = f.read()
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;x&quot;', page)
        self.assertEqual(_read(self.p_file)['tasks']['n17']['title'], title)      # у файлі задач — як ввели

    def test_a_new_iteration_escapes_the_title_too(self):
        cfg = _read(self.p_file)
        cfg['tasks']['x']['title'] = '<img src=x onerror=alert(1)>'
        _write(self.p_file, cfg)
        shutil.rmtree(os.path.join(self.x_dir, 'iterations', 'it2'), ignore_errors=True)
        self.addCleanup(shutil.rmtree, os.path.join(self.x_dir, 'iterations', 'it2'), True)
        self.restore_bytes(os.path.join(self.x_dir, 'iterations.json'))
        st, body = self.post('/t/x/api/iteration', {})
        self.assertEqual(st, 200, body)
        with open(os.path.join(self.x_dir, 'iterations', 'it2', 'index.html'), encoding='utf-8') as f:
            page = f.read()
        self.assertNotIn('<img', page)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', page)

    def test_the_task_folder_is_under_the_space_path_whatever_the_tasks_file_says(self):
        """Тека задачі — у `path` простору, а не там, куди вказує `design_work_root(s)` файла задач
        (його міг написати інший інструмент чи людина), і тим паче не в `FALLBACK_WORK_ROOT`
        (на машині власника це справжня тека United). Фолбек тут — пастка в тимчасовій теці."""
        self.made(os.path.join(self.p_path, 'n9'))
        cfg = _read(self.p_file)
        cfg.pop('design_work_root')
        cfg['design_work_roots'] = {'united': os.path.join(self.tmp, 'elsewhere')}
        _write(self.p_file, cfg)
        trap = os.path.join(self.tmp, 'fallback-trap')
        self.made(trap, os.path.join(self.tmp, 'elsewhere'))
        with mock.patch.object(serve, 'FALLBACK_WORK_ROOT', trap):
            st, body = self.post('/api/task-new', {'id': 'n9', 'space': self.p_id})
        self.assertEqual((st, body['dir']), (200, os.path.join(self.p_path, 'n9')), body)
        self.assertFalse(os.path.exists(trap), 'задачу кинуло в FALLBACK_WORK_ROOT')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'elsewhere')))

    def test_gitlab_is_refused_without_integrations_and_nothing_is_created(self):
        self.made(os.path.join(self.p_path, 'n3'))
        before = _md5(self.p_file)
        st, body = self.post('/api/task-new', {'id': 'n3', 'space': self.p_id,
                                               'gitlab': {'repo': 'git@x:y/z.git', 'path': 'mockup/n3'}})
        self.assertEqual((st, body['ok'], body['code']), (400, False, 'gitlab-needs-integrations'), body)
        self.assertEqual(_md5(self.p_file), before)
        self.assertFalse(os.path.exists(os.path.join(self.p_path, 'n3')))
        self.assertEqual(spaces.read_registry()['current'], self.legacy_id)

    def test_an_id_that_exists_anywhere_is_refused(self):
        """Id унікальний на машині через УСІ простори, а не лише в цільовому."""
        before = (_md5(self.legacy_file), _md5(self.p_file), _md5(self.reg_path))
        for payload in ({'id': 'x', 'space': self.p_id},          # є в цільовому
                        {'id': 'a', 'space': self.p_id},          # є в ІНШОМУ просторі
                        {'id': 'x'},                              # без `space`: ціль — старий, `x` — у P
                        {'id': 'gone', 'space': self.e_id}):
            with self.subTest(payload=payload):
                st, body = self.post('/api/task-new', payload)
                self.assertEqual((st, body['ok'], body['code'], body['error']),
                                 (400, False, 'task-exists', 'task already exists'), body)
        self.assertEqual((_md5(self.legacy_file), _md5(self.p_file), _md5(self.reg_path)), before)

    def test_an_id_already_in_two_spaces_is_still_just_a_400(self):
        cfg = _read(self.p_file)
        cfg['tasks']['a'] = {'title': 'Дубль', 'dir': self.a_dir, 'profile': 'tool'}
        _write(self.p_file, cfg)
        st, body = self.post('/api/task-new', {'id': 'a', 'space': self.e_id})
        self.assertEqual((st, body['code']), (400, 'task-exists'))

    def test_unknown_space_is_400_and_an_explicit_empty_one_does_not_fall_back(self):
        """`space` названо, але такого нема, — відмова. Мовчки віддати це в простір з інтеграціями
        означало б завести «особисту» задачу в реєстр ЛІГА."""
        before = (_md5(self.legacy_file), _md5(self.p_file))
        for space in ('nope', '', 5, ['p'], 0):
            with self.subTest(space=space):
                st, body = self.post('/api/task-new', {'id': 'n4', 'space': space})
                self.assertEqual((st, body['code'], body['error']), (400, 'unknown-space', 'unknown space'), body)
        self.assertEqual((_md5(self.legacy_file), _md5(self.p_file)), before)
        self.assertFalse(os.path.exists(self.old_dir('n4')))

    def test_bad_ids_are_400_and_create_nothing(self):
        """`NAME_RE.fullmatch`: `$` пускав id із хвостовим переводом рядка, а не-рядок валив
        обробник TypeError-ом."""
        before = (_md5(self.legacy_file), _md5(self.p_file))
        listed = (sorted(os.listdir(self.p_path)), sorted(os.listdir(os.path.dirname(self.a_dir))))
        names = ('n5\n', '../evil', 'a/b', '', ' ', 5, None, ['n5'], 'n 5')
        for tid in names:
            with self.subTest(id=tid):
                st, body = self.post('/api/task-new', {'id': tid, 'space': self.p_id})
                self.assertEqual((st, body['code']), (400, 'bad-task-id'), body)
        self.assertEqual((_md5(self.legacy_file), _md5(self.p_file)), before)
        self.assertEqual((sorted(os.listdir(self.p_path)), sorted(os.listdir(os.path.dirname(self.a_dir)))), listed,
                         'відмова лишила теку задачі')

    def test_the_header_names_nothing_for_task_new(self):
        self.made(os.path.join(self.p_path, 'n6'))
        st, body = self.post('/api/task-new', {'id': 'n6', 'space': self.p_id}, {'X-Canvas-Task': 'a'})
        self.assertEqual((st, body['space']), (200, self.p_id), body)

    def test_the_default_space_goes_to_the_first_integrations_space_not_to_the_request_one(self):
        """Реєстр: простір з інтеграціями — НЕ перший. Дефолт — він, а не поточний і не перший."""
        self.made(self.old_dir('n7'))
        reg = _read(self.reg_path)
        reg['spaces'].sort(key=lambda s: s['id'] != self.e_id)          # `E` — перший у реєстрі
        reg['current'] = self.e_id
        _write(self.reg_path, reg)
        st, body = self.post('/api/task-new', {'id': 'n7', 'profile': 'tool'})
        self.assertEqual((st, body['space']), (200, self.legacy_id), body)
        self.assertIn('n7', _read(self.legacy_file)['tasks'])

    def test_no_integrations_space_anywhere_the_default_is_the_current_one(self):
        self.made(os.path.join(self.p_path, 'n8'))
        reg = _read(self.reg_path)
        for sp in reg['spaces']:
            sp['integrations'] = False
        reg['current'] = self.p_id
        _write(self.reg_path, reg)
        st, body = self.post('/api/task-new', {'id': 'n8'})
        self.assertEqual((st, body['space']), (200, self.p_id), body)
        self.assertIsNone(_read(self.p_file)['tasks']['n8']['profile'])

    # ---------- `task-new` без `space` і без простору ЛІГА ----------

    LIGA_ERROR = ('простір ЛІГА береться з design-canvas/tasks.json (копія tasks.example.json), '
                  'а не з «Новий простір»')

    def no_liga(self):
        """Реєстр БЕЗ простору з інтеграціями (так виглядає машина дизайнера без старого файла);
        поточний — P."""
        reg = _read(self.reg_path)
        for sp in reg['spaces']:
            sp['integrations'] = False
        reg['current'] = self.p_id
        _write(self.reg_path, reg)

    def test_liga_signs_without_space_and_without_a_liga_space_are_409_and_create_nothing(self):
        """Потік dev-pipeline ЛІГА (`jira`, `profile` напрямку, `gitlab`) без `space`, а простору з
        інтеграціями нема: тихо завести задачу в ПОТОЧНИЙ простір означало б Jira/GitLab-бутстрап,
        що став локальною задачею з `profile: null`. Відмова JSON-ом, нічого не створено,
        поточний простір не змінено."""
        self.no_liga()
        before = (_md5(self.legacy_file), _md5(self.p_file), _md5(self.reg_path), _md5(self.e_file))
        listed = (sorted(os.listdir(self.p_path)), sorted(os.listdir(self.e_path)),
                  sorted(os.listdir(os.path.dirname(self.a_dir))))
        # 4b-3: профіль — ознака потоку ЛІГА лише коли він є в `profile_repos` конфігу установки (константи в коді нема);
        # у фікстурі такого конфігу нема, тож таблицю підставляє тест (вигадані репо).
        table = {p: f'git@git.example:org/{p}-design.git' for p in ('united', 'liga360', 'seo')}
        for sign in ({'jira': 'LIGA-1'}, {'profile': 'united'}, {'profile': 'liga360'}, {'profile': 'seo'},
                     {'gitlab': {'repo': 'git@x:y/z.git', 'path': 'mockup/n20'}},
                     {'jira': 'LIGA-1', 'profile': 'tool', 'title': 'Т'}):
            with self.subTest(sign=sign), mock.patch.object(serve, 'profile_repos', return_value=table):
                st, body = self.post('/api/task-new', {'id': 'n20', **sign})
                self.assertEqual((st, body['ok'], body['code'], body['error']),
                                 (409, False, 'no-integrations-space', self.LIGA_ERROR), body)
        self.assertEqual((_md5(self.legacy_file), _md5(self.p_file), _md5(self.reg_path), _md5(self.e_file)),
                         before)
        self.assertEqual((sorted(os.listdir(self.p_path)), sorted(os.listdir(self.e_path)),
                          sorted(os.listdir(os.path.dirname(self.a_dir)))), listed, 'відмова лишила теку')
        self.assertEqual(spaces.read_registry()['current'], self.p_id)

    def test_without_liga_signs_the_task_still_goes_to_the_current_space(self):
        """Не-ознаки: порожній/пробіловий `jira`, не-рядок, профіль не з `profile_repos()`, порожній
        `gitlab` — як було (поточний простір, `profile: null`)."""
        self.no_liga()
        for i, extra in enumerate(({}, {'jira': ''}, {'jira': '   '}, {'jira': 5}, {'jira': None},
                                   {'profile': 'tool'}, {'profile': ''}, {'profile': None}, {'profile': 'United'},
                                   {'gitlab': None}, {'gitlab': {}}, {'gitlab': ''}, {'title': 'Т'})):
            tid = f'n21-{i}'
            self.made(os.path.join(self.p_path, tid))
            with self.subTest(extra=extra):
                st, body = self.post('/api/task-new', {'id': tid, **extra})
                self.assertEqual((st, body['space']), (200, self.p_id), body)
                self.assertIsNone(_read(self.p_file)['tasks'][tid]['profile'])

    def test_a_profile_without_profile_repos_in_the_config_is_not_a_liga_sign(self):
        """4b-3: у конфігу установки нема `profile_repos` (так у фікстурі) — `profile: united` не ознака потоку ЛІГА: без
        409 `no-integrations-space`, задача лягає в ПОТОЧНИЙ простір, як звичайна, без типового `gitlab`."""
        self.no_liga()
        self.assertNotIn('profile_repos', _read(self.legacy_file))
        self.made(os.path.join(self.p_path, 'n25'))
        st, body = self.post('/api/task-new', {'id': 'n25', 'profile': 'united'})
        self.assertEqual((st, body['ok'], body['space']), (200, True, self.p_id), body)
        entry = _read(self.p_file)['tasks']['n25']
        self.assertNotIn('gitlab', entry)

    def test_liga_signs_with_a_liga_space_or_an_explicit_space_are_not_refused(self):
        """409 лише коли простору ЛІГА нема. Є він — задача йде в нього; явний `space` — у названий
        (для `gitlab` у просторі без інтеграцій лишається своя відмова 400)."""
        self.made(self.old_dir('n22'), os.path.join(self.p_path, 'n23'))
        spaces.switch_space(self.p_id)
        st, body = self.post('/api/task-new', {'id': 'n22', 'jira': 'LIGA-2', 'profile': 'tool'})
        self.assertEqual((st, body['space']), (200, self.legacy_id), body)
        self.no_liga()
        st, body = self.post('/api/task-new', {'id': 'n23', 'space': self.p_id, 'jira': 'LIGA-3',
                                               'profile': 'united'})
        self.assertEqual((st, body['space']), (200, self.p_id), body)
        st, body = self.post('/api/task-new', {'id': 'n24', 'space': self.p_id,
                                               'gitlab': {'repo': 'git@x:y/z.git', 'path': 'mockup/n24'}})
        self.assertEqual((st, body['code']), (400, 'gitlab-needs-integrations'), body)


class ForeignOrigin(Fixture):
    """Чужа вебсторінка шле POST «простим запитом» без preflight: `Origin` перевіряється ОДИН раз на
    всі POST, ще до розбору задачі й тіла, — тож жодна з нових записувальних точок реєстру не
    дістається чужому сайту."""

    def test_a_foreign_origin_gets_403_and_nothing_is_written(self):
        reg = os.path.join(self.deai, 'spaces.json')
        q = os.path.join(self.home, 'deai-work', 'evil')
        self.addCleanup(shutil.rmtree, q, True)
        self.addCleanup(shutil.rmtree, os.path.join(self.p_path, 'evil-task'), True)
        snapshot = lambda: (_md5(reg), _md5(self.legacy_file), _md5(self.p_file), _md5(self.e_file),  # noqa: E731
                            _md5(os.path.join(self.p_path, 'space.json')),
                            sorted(os.listdir(os.path.join(self.home, 'deai-work'))), sorted(os.listdir(self.p_path)))
        before = snapshot()
        routes = (('/api/space-new', {'name': 'Evil', 'path': q}),
                  ('/api/space-update', {'id': self.p_id, 'name': 'Evil'}),
                  ('/api/space-switch', {'id': self.p_id}),
                  ('/api/task-new', {'id': 'evil-task', 'space': self.p_id}),
                  ('/api/task-switch', {'id': 'x'}))
        for origin in ('http://evil.example', 'null', 'http://localhost.evil.example', 'https://127.0.0.1.evil.example'):
            for path, payload in routes:
                with self.subTest(origin=origin, path=path):
                    st, body = self.post(path, payload, {'Origin': origin})
                    self.assertEqual((st, body), (403, {'ok': False, 'error': 'foreign origin'}))
        self.assertEqual(snapshot(), before)

    def test_the_local_origin_still_works(self):
        """Контроль: тест вище не червоний лише тому, що маршрути взагалі мертві."""
        self.addCleanup(self.restore_registry_current)
        for origin in (f'http://127.0.0.1:{self.port}', f'http://localhost:{self.port}'):
            with self.subTest(origin=origin):
                st, body = self.post('/api/space-switch', {'id': self.p_id}, {'Origin': origin})
                self.assertEqual((st, body['ok']), (200, True))

    def restore_registry_current(self):
        spaces.switch_space(self.legacy_id)


class Bare(Fixture):
    """Сервер БЕЗ просторів у реєстрі: `LAYER_ON` — шар увімкнено, реєстр порожній (нічого мігрувати);
    інакше шар вимкнено (лише `DC_TASKS_FILE`, як усі наявні тести) зі старим файлом із задачею `a`."""
    LAYER_ON = True

    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.normpath(tempfile.mkdtemp(prefix='spaces-bare-'))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        saved = {k: os.environ.get(k) for k in _ENV}

        def restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        cls.addClassCleanup(restore)
        cls.home = os.path.join(cls.tmp, 'home')
        cls.deai = os.path.join(cls.tmp, 'deai')
        cls.legacy_file = os.path.join(cls.tmp, 'legacy', 'tasks.json')
        os.makedirs(cls.home)
        os.environ['HOME'] = cls.home
        if cls.LAYER_ON:
            os.environ['DEAI_HOME'] = cls.deai
        else:
            os.environ.pop('DEAI_HOME', None)
        os.environ['DC_TASKS_FILE'] = cls.legacy_file
        os.environ['DC_NO_OVERVIEW'] = '1'
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        spaces.clear_request_space()
        if not cls.LAYER_ON:
            cls.a_dir = os.path.join(cls.tmp, 'work', 'a')
            _task_dir(cls.a_dir, 'a')
            _write(cls.legacy_file, {'current': 'a', 'design_work_root': os.path.join(cls.tmp, 'work'),
                                     'tasks': {'a': {'title': 'Альфа', 'dir': cls.a_dir, 'profile': 'tool'}}})
        cls.httpd = serve.make_server(0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.httpd.server_close)
        cls.addClassCleanup(cls.httpd.shutdown)
        cls.base = f'http://127.0.0.1:{cls.port}'

    def setUp(self):
        spaces.clear_request_space()


class NoSpaces(Bare):
    """Просторів нема зовсім: списки задач — порожні 200 (UI іде на привітання), `/api/task` — `no-task`."""

    def test_spaces_listing_is_empty_and_not_off(self):
        st, body = self.jget('/api/spaces')
        self.assertEqual((st, body), (200, {'current': None, 'spaces': []}))

    def test_task_lists_are_empty_200s_not_no_task_404s(self):
        for path in ('/api/tasks', '/api/tasks?all=1'):
            with self.subTest(path=path):
                self.assertEqual(self.jget(path), (200, {'current': None, 'tasks': [], 'space': None}))
        st, body = self.jget('/api/tasks-overview')
        self.assertEqual((st, body), (200, {'current': None, 'mine': [], 'team': None, 'space': None}))

    def test_the_single_task_is_still_404_no_task(self):
        st, body = self.jget('/api/task')
        self.assertEqual((st, body['code'], body['space']), (404, 'no-task', None))

    def test_a_task_cannot_be_created_or_switched_to(self):
        st, body = self.post('/api/task-new', {'id': 'n1', 'title': 'N'})
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'no-space'), body)
        st, _ = self.post_raw('/api/task-switch', {'id': 'a'})
        self.assertEqual(st, 404)
        st, body = self.post('/api/space-switch', {'id': 'nope'})
        self.assertEqual((st, body['code']), (404, 'unknown-space'))

    def test_liga_signs_get_the_liga_refusal_not_the_create_a_space_one(self):
        """Простору ЛІГА нема й нічого нема: «створіть простір» послало б агента в «Новий простір»,
        який простору ЛІГА не дає. Без ознак — `no-space`, як було (тест вище)."""
        for sign in ({'jira': 'LIGA-1'}, {'profile': 'united'},
                     {'gitlab': {'repo': 'git@x:y/z.git', 'path': 'mockup/n1'}}):
            # 4b-3: профіль — ознака ЛІГИ лише з `profile_repos` конфігу установки; у цій фікстурі конфігу нема
            with self.subTest(sign=sign), mock.patch.object(serve, 'profile_repos',
                                                            return_value={'united': 'git@git.example:org/united-design.git'}):
                st, body = self.post('/api/task-new', {'id': 'n1', **sign})
                self.assertEqual((st, body['ok'], body['code'], body['error']),
                                 (409, False, 'no-integrations-space', TaskNew.LIGA_ERROR), body)

    def test_nothing_of_the_above_wrote_to_the_deai_home(self):
        for path in ('/api/spaces', '/api/tasks', '/api/tasks?all=1', '/api/tasks-overview', '/api/task'):
            self.get(path)
        self.post('/api/task-new', {'id': 'n1'})
        self.post('/api/task-new', {'id': 'n1', 'jira': 'LIGA-1'})
        self.assertFalse(os.path.exists(self.deai), 'читання порожнього реєстру створило <DEAI_HOME>')


class BrokenLegacyFirstStart(Bare):
    """Перший запуск: `<DEAI_HOME>` порожній, а старий `tasks.json` є й НЕ читається (обрізаний, не
    обʼєкт, понад мегабайт). Раніше це виглядало як чиста машина: `/api/spaces` → порожньо, `/api/task`
    → 404 `no-task`, UI → привітання. Тепер — 503 `space-unavailable` з назвою файла (смуга помилки), а
    `/api/spaces` каже про файл (`legacy_error`), тож привітання нема. Полагодили — наступне читання
    мігрує як завжди."""

    UNREADABLE = {
        'обрізаний JSON': '{"current": "a", "tasks": {"a": {"dir": "/x',
        'не JSON': '{ не json',
        'масив': '[]',
        'число': '5',
        'понад мегабайт': '{"pad": "' + 'a' * (1 << 20) + '"}',
    }

    def setUp(self):
        super().setUp()
        self.addCleanup(lambda: os.path.exists(self.legacy_file) and os.remove(self.legacy_file))
        self.addCleanup(shutil.rmtree, self.deai, True)

    def break_it(self, raw):
        _write(self.legacy_file, raw)

    def test_the_listing_names_the_file_instead_of_looking_empty(self):
        for what, raw in self.UNREADABLE.items():
            with self.subTest(what=what):
                self.break_it(raw)
                self.assertEqual(self.jget('/api/spaces'), (200, {
                    'current': None, 'spaces': [],
                    'legacy_error': {'path': self.legacy_file, 'code': 'space-unavailable'}}))

    def test_the_three_reads_answer_503_space_unavailable_with_the_file(self):
        for what, raw in self.UNREADABLE.items():
            self.break_it(raw)
            for path in ('/api/task', '/api/tasks', '/api/tasks-overview'):
                with self.subTest(what=what, path=path):
                    st, body = self.jget(path)
                    self.assertEqual((st, body['ok'], body['code'], body['path']),
                                     (503, False, 'space-unavailable', self.legacy_file), body)
                    self.assertTrue(body['error'])

    def test_all_spaces_listing_skips_it_like_any_unreadable_space(self):
        self.break_it('{')
        self.assertEqual(self.jget('/api/tasks?all=1'), (200, {'current': None, 'tasks': [], 'space': None}))

    def test_a_named_task_is_503_not_an_unknown_task_404(self):
        self.break_it('{')
        for path in ('/api/task', '/api/tasks'):
            with self.subTest(path=path):
                st, body = self.jget(path, {'X-Canvas-Task': 'a'})
                self.assertEqual((st, body['code'], body['path']), (503, 'space-unavailable', self.legacy_file), body)
        st, body = self.jget('/t/a/api/task')
        self.assertEqual((st, body['code']), (503, 'space-unavailable'), body)

    def test_creating_and_switching_are_refused_the_same_way(self):
        """Простору й задач, які вже лежать у файлі, не видно: нове id могло б зіткнутись з ними."""
        self.break_it('{')
        for path, payload in (('/api/task-new', {'id': 'n1', 'title': 'N'}),
                              ('/api/task-new', {'id': 'n1', 'jira': 'LIGA-1'}),
                              ('/api/task-new', {'id': 'n1', 'space': 'liga'}),
                              ('/api/task-switch', {'id': 'a'}),
                              ('/api/space-new', {'name': 'Q', 'path': os.path.join(self.home, 'deai-work', 'q')})):
            with self.subTest(path=path, payload=payload):
                st, body = self.post(path, payload)
                self.assertEqual((st, body['ok'], body['code'], body['path']),
                                 (503, False, 'space-unavailable', self.legacy_file), body)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-work')), 'щось створено попри відмову')
        self.assertFalse(os.path.exists(self.deai), 'реєстр записано попри відмову')

    def test_a_bad_profile_is_still_a_400_before_the_file_matters(self):
        self.break_it('{')
        st, body = self.post('/api/task-new', {'id': 'n1', 'profile': 5})
        self.assertEqual((st, body['code']), (400, 'bad-profile'), body)

    def test_nothing_was_written_to_the_deai_home_and_the_file_is_untouched(self):
        self.break_it('{ не json')
        before = _md5(self.legacy_file)
        for path in ('/api/spaces', '/api/task', '/api/tasks', '/api/tasks-overview'):
            self.get(path)
        self.assertFalse(os.path.exists(self.deai), 'читання створило <DEAI_HOME>')
        self.assertEqual(_md5(self.legacy_file), before)

    def test_fixing_the_file_makes_the_next_read_migrate_as_usual(self):
        self.break_it('{ не json')
        self.assertEqual(self.jget('/api/task')[0], 503)
        work = os.path.join(self.tmp, 'work')
        a_dir = os.path.join(work, 'a')
        _task_dir(a_dir, 'a')
        _write(self.legacy_file, {'current': 'a', 'design_work_root': work, 'registry': {},
                                  'tasks': {'a': {'title': 'Альфа', 'dir': a_dir, 'profile': 'tool'}}})
        st, body = self.jget('/api/spaces')
        self.assertEqual(st, 200)
        self.assertNotIn('legacy_error', body)
        self.assertEqual([s['tasks'] for s in body['spaces']], [1])
        st, body = self.jget('/api/task')
        self.assertEqual((st, body['id']), (200, 'a'))

    def test_a_valid_object_with_a_bad_tasks_shape_is_still_the_old_503(self):
        """Обʼєкт мігрується (простір є), далі `load_tasks()` відмовляє тим самим 503 — і `legacy_error`
        тут нема: простір у реєстрі, файл нечитабельний як файл ПРОСТОРУ."""
        self.break_it('{"tasks": []}')
        st, body = self.jget('/api/spaces')
        self.assertEqual(st, 200)
        self.assertNotIn('legacy_error', body)
        self.assertEqual(len(body['spaces']), 1)
        st, body = self.jget('/api/task')
        self.assertEqual((st, body['code'], body['path']), (503, 'space-unavailable', self.legacy_file))


class FirstSpace(Bare):
    """Привітання → перший простір → перша задача: шлях, яким іде чиста машина."""

    def test_the_first_space_then_the_first_task(self):
        path = os.path.join(self.home, 'deai-work', 'personal')
        st, body = self.post('/api/space-new', {'name': 'Особисте', 'color': 'space-3', 'path': path})
        self.assertEqual(st, 200, body)
        sid = body['id']
        self.assertEqual(self.jget('/api/spaces')[1]['current'], sid)
        st, body = self.jget('/api/tasks')
        self.assertEqual((st, body['current'], body['tasks'], body['space']['id']), (200, None, [], sid))
        self.assertEqual(self.jget('/api/task')[1]['code'], 'no-task')
        # Ознаки потоку ЛІГА (`profile: united`) без `space` у просторі без інтеграцій — відмова
        # (раніше тут була тиха локальна задача з `profile: null`); нічого не створено.
        # 4b-3: профіль — ознака ЛІГИ лише з `profile_repos` конфігу установки (у фікстурі його нема — таблицю дає тест)
        with mock.patch.object(serve, 'profile_repos',
                               return_value={'united': 'git@git.example:org/united-design.git'}):
            st, body = self.post('/api/task-new', {'id': 'first', 'title': 'Перша', 'profile': 'united'})
        self.assertEqual((st, body['code']), (409, 'no-integrations-space'), body)
        self.assertFalse(os.path.exists(os.path.join(path, 'first')))
        st, body = self.post('/api/task-new', {'id': 'first', 'title': 'Перша'})
        self.assertEqual((st, body['space'], body['dir']), (200, sid, os.path.join(path, 'first')), body)
        st, body = self.jget('/api/task')
        self.assertEqual((st, body['id'], body['profile'], body['comment_channel'], body['space']['name']),
                         (200, 'first', None, None, 'Особисте'))
        self.assertEqual(self.jget('/api/tasks?all=1')[1]['tasks'][0]['space'], sid)


class LayerOff(Bare):
    """Шар вимкнено (лише `DC_TASKS_FILE`, усі наявні тести): простору немає ніде — `space: null`."""
    LAYER_ON = False

    def test_spaces_listing_says_off(self):
        self.assertEqual(self.jget('/api/spaces'), (200, {'current': None, 'spaces': [], 'off': True}))

    def test_responses_carry_a_null_space_and_the_channel_as_before(self):
        body = self.jget('/api/task')[1]
        self.assertEqual((body['id'], body['space'], body['comment_channel']), ('a', None, 'dc/a'))
        body = self.jget('/api/tasks')[1]
        self.assertEqual((body['current'], body['space'], [t['id'] for t in body['tasks']]), ('a', None, ['a']))
        body = self.jget('/api/tasks?all=1')[1]
        self.assertEqual([(t['id'], t['space']) for t in body['tasks']], [('a', None)])
        self.assertIsNone(body['space'])
        body = self.jget('/api/tasks-overview')[1]
        self.assertEqual((body['current'], body['space']), ('a', None))

    def test_the_inspector_gets_no_sp_when_the_layer_is_off(self):
        """Неявний простір (`legacy` без шляху) — не простір реєстру: `/api/ds-tokens?space=legacy`
        питав би про те, чого нема. Напрямок їде як і раніше."""
        for q in ('', '&ch=project'):
            st, html = self.get('/commented?it=it1' + q)
            self.assertEqual(st, 200, html[:200])
            m = re.search(r'src="[^"]*/inspector\.js([^"]*)"', html)
            self.assertIsNotNone(m, q)
            self.assertEqual(m.group(1), '?ds=tool', q)
            self.assertNotIn('sp=', m.group(1))

    def test_a_broken_old_file_adds_nothing_to_the_listing_when_the_layer_is_off(self):
        """`legacy_error` — лише про шар просторів: вимкнений читає й пише як до просторів."""
        self.restore_bytes(self.legacy_file)
        _write(self.legacy_file, '{')
        self.assertEqual(self.jget('/api/spaces'), (200, {'current': None, 'spaces': [], 'off': True}))
        self.assertFalse(os.path.exists(os.path.join(self.home, '.deai')))

    def test_the_space_writers_say_spaces_off_409(self):
        for path, payload in (('/api/space-new', {'name': 'Q', 'path': os.path.join(self.home, 'deai-work', 'q')}),
                              ('/api/space-update', {'id': 'legacy', 'name': 'Q'}),
                              ('/api/space-switch', {'id': 'legacy'})):
            with self.subTest(path=path):
                st, body = self.post(path, payload)
                self.assertEqual((st, body['ok'], body['code']), (409, False, 'spaces-off'), body)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-work')))
        self.assertFalse(os.path.exists(os.path.join(self.home, '.deai')))

    def test_liga_signs_are_no_reason_to_refuse_when_the_layer_is_off(self):
        """Шар вимкнено: неявний простір — з інтеграціями, тож `jira` (і решта ознак) без `space`
        проходить, як до просторів."""
        self.restore_bytes(self.legacy_file)
        self.addCleanup(shutil.rmtree, os.path.join(self.tmp, 'work', 'n2'), True)
        st, body = self.post('/api/task-new', {'id': 'n2', 'title': 'N', 'jira': 'LIGA-1', 'profile': 'tool'})
        self.assertEqual((st, body['space']), (200, None), body)
        self.assertEqual(_read(self.legacy_file)['tasks']['n2']['jira'], 'LIGA-1')

    def test_task_switch_and_new_work_as_before_with_a_null_space(self):
        self.restore_bytes(self.legacy_file)
        self.addCleanup(shutil.rmtree, os.path.join(self.tmp, 'work', 'n1'), True)
        st, body = self.post('/api/task-switch', {'id': 'a'})
        self.assertEqual((st, body), (200, {'ok': True, 'current': 'a', 'space': None}))
        st, body = self.post('/api/task-new', {'id': 'n1', 'title': 'N', 'profile': 'tool'})
        self.assertEqual((st, body['space']), (200, None), body)
        task = _read(self.legacy_file)['tasks']['n1']
        self.assertEqual((task['profile'], task['dir']), ('tool', os.path.join(self.tmp, 'work', 'n1')))
        self.assertFalse(os.path.exists(os.path.join(self.home, '.deai')))


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spaces-guard-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, '.deai')

    def test_the_real_home_does_not_come_from_the_environment(self):
        """Справжня домівка — з бази користувачів, а не з `$HOME`: тест, що підмінив `HOME`,
        не відводить охоронця від справжнього `~/.deai`. Модуль перечитується під підміненим
        `HOME`/`DEAI_HOME` (він фіксує шлях при імпорті) і потім повертається як був."""
        import importlib
        import pwd
        real = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, '.deai')
        self.addCleanup(importlib.reload, spaces_guard)
        with env(HOME=self.tmp, DEAI_HOME=None):
            importlib.reload(spaces_guard)
            watched = spaces_guard.WATCHED
        self.assertIn(real, watched)
        self.assertNotIn(os.path.join(self.tmp, '.deai'), watched)

    def test_the_guard_sees_the_dir_the_registry_and_its_backup(self):
        """Охоронець червоніє, коли зʼявилась тека, змінився реєстр, зʼявилась `.bak` чи будь-який
        інший файл у теці, і мовчить, коли нічого не змінилось."""
        homes = (self.home,)
        before = spaces_guard.snapshot(homes)
        spaces_guard.assert_untouched(before, homes)
        os.makedirs(self.home)
        with self.assertRaises(AssertionError):
            spaces_guard.assert_untouched(before, homes)             # тека зʼявилась
        empty = spaces_guard.snapshot(homes)
        _write(os.path.join(self.home, 'spaces.json'), '{}')
        with self.assertRaises(AssertionError):
            spaces_guard.assert_untouched(empty, homes)              # зʼявився реєстр
        with_registry = spaces_guard.snapshot(homes)
        spaces_guard.assert_untouched(with_registry, homes)
        _write(os.path.join(self.home, 'spaces.json'), '{"a": 1}')
        with self.assertRaises(AssertionError):
            spaces_guard.assert_untouched(with_registry, homes)      # реєстр змінився
        changed = spaces_guard.snapshot(homes)
        _write(os.path.join(self.home, 'spaces.json.bak'), '{}')
        with self.assertRaises(AssertionError):
            spaces_guard.assert_untouched(changed, homes)            # зʼявилась .bak
        with_bak = spaces_guard.snapshot(homes)
        _write(os.path.join(self.home, 'spaces.json.bak'), '{"b": 2}')
        with self.assertRaises(AssertionError):
            spaces_guard.assert_untouched(with_bak, homes)           # .bak змінилась
        with_bak = spaces_guard.snapshot(homes)
        _write(os.path.join(self.home, 'other.tmp'), 'x')
        with self.assertRaises(AssertionError):
            spaces_guard.assert_untouched(with_bak, homes)           # чужий файл у теці

    def test_the_default_snapshot_is_of_the_real_machine(self):
        snap = spaces_guard.snapshot()
        self.assertEqual(set(snap), set(spaces_guard.WATCHED))
        spaces_guard.assert_untouched(snap)


if __name__ == '__main__':
    unittest.main()
