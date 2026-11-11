"""HTTP-шар оновлення (0.23.0): `GET /api/update`, `POST /api/update-check`. Сервер — справжній `make_server(0)` на 127.0.0.1; корінь оновлення —
викидний git-світ (`UPDATER_ROOT`), remote — шлях файлової системи (мережі нема); `DEAI_HOME`, `HOME`, `DC_TASKS_FILE` — тимчасові."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import serve  # noqa: E402
import spaces_guard  # noqa: E402
import test_updater as tu  # noqa: E402  (лише помічники `make_world`/`push_tag`/`git`)
import test_updater_apply as ta  # noqa: E402  (`make_app_world`/`release`/`head`)

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class UpdateApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-upd-')
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        cls.deai_home = os.path.join(cls.tmp, 'deai')
        env = {**tu.GIT_ENV, 'HOME': os.path.join(cls.tmp, 'home'), 'DEAI_HOME': cls.deai_home,
               'DC_TASKS_FILE': os.path.join(cls.tmp, 'tasks.json'), 'DC_NO_OVERVIEW': '1', 'DEAI_NO_UPDATE_CHECK': '1'}
        os.makedirs(env['HOME'])
        p = mock.patch.dict(os.environ, env)
        p.start()
        cls.addClassCleanup(p.stop)
        for k in ('DEAI_UPDATE_REMOTE',):
            os.environ.pop(k, None)
        old_root, old_upd = serve.UPDATER_ROOT, serve._UPDATER
        cls.addClassCleanup(lambda: (setattr(serve, 'UPDATER_ROOT', old_root), setattr(serve, '_UPDATER', old_upd)))
        cls.httpd = serve.make_server(0)
        cls.base = 'http://127.0.0.1:%d' % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.httpd.shutdown)

    def setUp(self):
        """Свіжий git-світ на кожен тест (теги не тече між тестами); стан оновлення скинуто."""
        world = tempfile.mkdtemp(prefix='world-', dir=self.tmp)
        self.remote, self.work = ta.make_app_world(world)
        serve.UPDATER_ROOT, serve._UPDATER = self.work, None
        try:
            os.remove(os.path.join(self.deai_home, 'update.json'))
        except OSError:
            pass

    def call(self, method, path, body=None, origin=None, headers=None):
        h = {'Content-Type': 'application/json', **(headers or {})}
        if origin:
            h['Origin'] = origin
        data = json.dumps(body if body is not None else {}).encode() if method == 'POST' else None
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_get_update_shape_and_no_paths(self):
        st, raw = self.call('GET', '/api/update')
        self.assertEqual(st, 200)
        body = json.loads(raw)
        for k in ('current', 'latest', 'available', 'checked_at', 'state', 'reason', 'blocked', 'remote_host', 'boot'):
            self.assertIn(k, body)
        self.assertEqual(body['current'], '0.1.0')
        self.assertEqual(body['boot'], serve.updater.BOOT)
        for needle in (self.tmp, self.remote, self.work):
            self.assertNotIn(needle, raw)

    def test_post_check_sees_a_new_tag_and_origin_gate(self):
        tu.push_tag(self.work, '0.2.0')
        before = os.path.exists(os.path.join(self.deai_home, 'update.json'))
        st, raw = self.call('POST', '/api/update-check', origin='https://evil.example')
        self.assertEqual(st, 403)
        self.assertEqual(os.path.exists(os.path.join(self.deai_home, 'update.json')), before, 'відмова Origin не запускає перевірку')
        for origin in (None, 'http://localhost:8765', 'http://127.0.0.1:8765'):
            st, raw = self.call('POST', '/api/update-check', origin=origin)
            body = json.loads(raw)
            self.assertEqual(st, 200, origin)
            self.assertTrue(body['ok'])
            self.assertEqual((body['latest'], body['available'], body['state']), ('0.2.0', True, 'ok'), origin)
        st, raw = self.call('GET', '/api/update')
        self.assertTrue(json.loads(raw)['available'])
        self.assertTrue(os.path.isfile(os.path.join(self.deai_home, 'update.json')))
        self.assertNotIn(self.tmp, raw)

    def test_works_on_an_empty_machine_and_ignores_task_header_and_query(self):
        """Порожня машина: простору й задач нема, `tasks.json` не існує — маршрут «машини» все одно відповідає."""
        self.assertFalse(os.path.exists(os.environ['DC_TASKS_FILE']))
        for path in ('/api/update', '/api/update?x=1'):
            st, _ = self.call('GET', path, headers={'X-Canvas-Task': 'no-such-task'})
            self.assertEqual(st, 200, path)
        st, _ = self.call('POST', '/api/update-check', headers={'X-Canvas-Task': 'no-such-task'})
        self.assertEqual(st, 200)

    def test_works_with_a_broken_registry(self):
        os.makedirs(self.deai_home, exist_ok=True)
        reg = os.path.join(self.deai_home, 'spaces.json')
        with open(reg, 'w') as f:
            f.write('{')
        self.addCleanup(lambda: os.path.exists(reg) and os.remove(reg))
        st, _ = self.call('GET', '/api/task')                       # контроль: реєстрові маршрути від битого реєстру падають
        self.assertNotEqual(st, 200)
        st, raw = self.call('GET', '/api/update')
        self.assertEqual(st, 200, raw)
        st, raw = self.call('POST', '/api/update-check')
        self.assertEqual(st, 200, raw)

    def test_get_update_notes_reads_the_remote_tag_and_leaks_no_paths(self):
        ta.release(self.work, '0.2.0', files={'CHANGELOG.md': '## [0.2.0] — 11.11.2026\n\nTwo <b>.\n\n## [0.1.0] — 10.11.2026\n\nOne.\n'})
        self.call('POST', '/api/update-check')
        st, raw = self.call('GET', '/api/update-notes?x=1', headers={'X-Canvas-Task': 'no-such-task'})
        self.assertEqual(st, 200, raw)
        body = json.loads(raw)
        self.assertEqual((body['ok'], body['version'], [s['version'] for s in body['sections']]), (True, '0.2.0', ['0.2.0']))
        self.assertEqual(body['sections'][0]['body'], 'Two <b>.')
        for needle in (self.tmp, self.remote, self.work):
            self.assertNotIn(needle, raw)
        self.assertEqual(self.call('GET', '/t/x/api/update-notes')[0], 400)

    def test_get_update_notes_without_an_update_is_an_empty_reason(self):
        st, raw = self.call('GET', '/api/update-notes')
        self.assertEqual((st, json.loads(raw)), (200, {'ok': True, 'sections': [], 'reason': 'no-update'}))

    def test_task_prefix_form_is_refused(self):
        st, raw = self.call('GET', '/t/x/api/update')
        self.assertEqual(st, 400)
        self.assertFalse(json.loads(raw)['ok'])
        st, raw = self.call('POST', '/t/x/api/update-check')
        self.assertEqual(st, 400)

    def test_busy_makes_the_update_blocked(self):
        tu.push_tag(self.work, '0.3.0')
        self.call('POST', '/api/update-check')
        with mock.patch.dict(serve._SHOOTS, {('t', 'it1'): object()}):
            st, raw = self.call('GET', '/api/update')
        self.assertEqual(json.loads(raw)['blocked'], 'busy')
        st, raw = self.call('GET', '/api/update')
        self.assertIsNone(json.loads(raw)['blocked'])

    def test_machine_routes_table(self):
        for r in ('/api/update', '/api/update-check', '/api/update-apply'):
            self.assertIn(r, serve.Handler._MACHINE_ROUTES)
            self.assertNotIn(r, serve.Handler._REGISTRY_ROUTES)

    # --- застосування ---

    class FakeTimer:
        made = []

        def __init__(self, delay, fn):
            self.delay, self.fn, self.daemon, self.started = delay, fn, False, False
            type(self).made.append(self)

        def start(self):
            self.started = True

    def _ready(self, version='0.2.0', **rel):
        ta.release(self.work, version, **rel)
        self.call('POST', '/api/update-check')

    def test_apply_updates_and_schedules_the_restart_after_the_response(self):
        self._ready()
        self.FakeTimer.made = []
        restarts, order = [], []
        real_send = serve.Handler._send_json

        def send(h, obj, status=200):
            real_send(h, obj, status)
            order.append('response-sent')
        orig_start = self.FakeTimer.start
        self.FakeTimer.start = lambda t: (order.append('timer-started'), orig_start(t))
        self.addCleanup(setattr, self.FakeTimer, 'start', orig_start)
        with mock.patch.object(serve.threading, 'Timer', self.FakeTimer), mock.patch.object(serve, '_restart', lambda: restarts.append(1)), \
                mock.patch.object(serve.Handler, '_send_json', send):
            st, raw = self.call('POST', '/api/update-apply', {'version': '9.9.9', 'remote': '/evil', 'path': '/x'})
            self.assertEqual((st, json.loads(raw)), (202, {'ok': True, 'to': '0.2.0', 'restart': 'auto'}))
            self.assertEqual(restarts, [], 'рестарт не виконано до таймера')
            self.assertEqual(order, ['response-sent', 'timer-started'], 'таймер рестарту — ПІСЛЯ відправки відповіді')
            (t,) = self.FakeTimer.made
            self.assertEqual((t.delay, t.started, t.daemon), (0.5, True, True))
            t.fn()
            self.assertEqual(restarts, [1])
        self.assertEqual(ta.head(self.work), tu.git(['rev-parse', 'v0.2.0^{commit}'], self.work).strip())
        st, raw = self.call('GET', '/api/update')
        body = json.loads(raw)
        self.assertEqual((body['current'], body['available']), ('0.2.0', False))
        self.assertEqual(body['last_update']['to'], '0.2.0')
        self.assertNotIn(self.tmp, raw)

    def test_apply_restart_really_fires_once_after_about_half_a_second(self):
        self._ready()
        fired = threading.Event()
        count = []
        with mock.patch.object(serve, '_restart', lambda: (count.append(1), fired.set())):
            st, _ = self.call('POST', '/api/update-apply')
            self.assertEqual(st, 202)
            self.assertTrue(fired.wait(5))
            threading.Event().wait(0.8)
        self.assertEqual(count, [1])

    def test_apply_refusals_schedule_no_restart_and_change_nothing(self):
        old = ta.head(self.work)
        self.FakeTimer.made = []
        with mock.patch.object(serve.threading, 'Timer', self.FakeTimer):
            st, raw = self.call('POST', '/api/update-apply')                           # нема оновлення
            self.assertEqual((st, json.loads(raw)['code']), (409, 'nothing-to-update'))
            self._ready('0.2.0', files={'app/x.py': 'def broken(:\n'})
            st, raw = self.call('POST', '/api/update-apply')                           # смоук не пройшов
            self.assertEqual((st, json.loads(raw)['code']), (500, 'rolled-back'))
            with mock.patch.object(serve.updater, '_is_windows', lambda: True):        # Windows: рестарт вручну
                ta.release(self.work, '0.3.0')
                self.call('POST', '/api/update-check')
                st, raw = self.call('POST', '/api/update-apply')
                self.assertEqual((st, json.loads(raw)['restart']), (202, 'manual'))
        self.assertEqual(self.FakeTimer.made, [])
        self.assertNotEqual(ta.head(self.work), old)                                   # 0.3.0 застосовано (Windows-гілка)

    def test_failed_restart_is_logged_and_flagged_for_the_ui(self):
        import contextlib
        import io
        self._ready()
        self.FakeTimer.made = []
        with mock.patch.object(serve.threading, 'Timer', self.FakeTimer):
            self.assertEqual(self.call('POST', '/api/update-apply')[0], 202)
        (t,) = self.FakeTimer.made
        self.assertFalse(json.loads(self.call('GET', '/api/update')[1])['restart_failed'])
        for fake in (lambda: False, mock.Mock(side_effect=FileNotFoundError('/secret/python'))):
            err = io.StringIO()
            with mock.patch.object(serve, '_restart', fake), contextlib.redirect_stderr(err):
                t.fn()
            self.assertEqual(err.getvalue().count('\n'), 1)
            self.assertNotIn('/secret', err.getvalue())
            body = json.loads(self.call('GET', '/api/update')[1])
            self.assertTrue(body['restart_failed'])
        # прапорець привʼязаний до процесу: «чужий» boot-токен не рахується
        u = serve._updater()
        st = u._load()
        st['restart_failed'] = 'some-older-boot'
        u._save(st)
        self.assertFalse(json.loads(self.call('GET', '/api/update')[1])['restart_failed'])
        # успішний (для тесту — «нічого не повернув») рестарт нічого не пише
        err = io.StringIO()
        with mock.patch.object(serve, '_restart', lambda: None), contextlib.redirect_stderr(err):
            t.fn()
        self.assertEqual(err.getvalue(), '')
        self.assertFalse(json.loads(self.call('GET', '/api/update')[1])['restart_failed'])

    def test_apply_origin_gate_bad_body_and_task_prefix(self):
        self._ready()
        old = ta.head(self.work)
        self.FakeTimer.made = []
        with mock.patch.object(serve.threading, 'Timer', self.FakeTimer):
            st, _ = self.call('POST', '/api/update-apply', origin='https://evil.example')
            self.assertEqual(st, 403)
            st, raw = self.call('POST', '/api/update-apply', body=[])
            self.assertEqual((st, json.loads(raw)['code']), (400, 'bad-body'))
            st, _ = self.call('POST', '/t/x/api/update-apply')
            self.assertEqual(st, 400)
        self.assertEqual((ta.head(self.work), self.FakeTimer.made), (old, []))


if __name__ == '__main__':
    unittest.main()
