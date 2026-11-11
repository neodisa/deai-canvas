"""Відгук, T6: кільце помилок сервера, збирач діагностики, `POST /api/feedback-preview`.

⛔ Ізоляція: тимчасові `HOME`, `DEAI_HOME`, `DC_TASKS_FILE`; мережі нема; справжній `~/.deai` стереже `spaces_guard`."""
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
import deai_modules  # noqa: E402
import feedback  # noqa: E402
import liga_fixture  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class ErrorRing(unittest.TestCase):
    def setUp(self):
        feedback.reset_errors()

    def test_ring_keeps_last_50_newest_last(self):
        for i in range(70):
            feedback.record_error('/api/r%d' % i, ValueError('e%d' % i))
        got = feedback.server_errors()
        self.assertEqual(len(got), 50)
        self.assertEqual((got[0]['route'], got[-1]['route']), ('/api/r20', '/api/r69'))

    def test_unknown_exception_stores_type_and_inner_app_frame_never_the_text(self):
        try:
            feedback.validate(None)                     # AttributeError зсередини app/feedback.py
        except AttributeError as e:
            feedback.record_error('/api/task?it=it1&secret=zzz', e)
        e = feedback.server_errors()[-1]
        self.assertEqual((e['route'], e['type']), ('/api/task', 'AttributeError'))
        self.assertRegex(e['msg'], r'^at feedback\.py:\d+$')
        self.assertNotIn('NoneType', json.dumps(e), 'текст винятку не зберігається')
        feedback.record_error('/api/x', ValueError('secret detail /Users/me/ClientB-Acme/x.json 12345678'))
        self.assertEqual(feedback.server_errors()[-1]['msg'], '', 'без кадру всередині застосунку — порожньо')

    def test_oserror_keeps_the_errno_name_only_never_the_filename(self):
        import errno
        exc = OSError(errno.ENOENT, 'No such file', '/Users/me/ClientB-Acme/x/y.json')
        feedback.record_error('/api/x', exc)
        e = feedback.server_errors()[-1]
        self.assertEqual((e['type'], e['msg']), ('FileNotFoundError', 'ENOENT'))
        feedback.record_error('/api/x', PermissionError(errno.EACCES, 'denied', '/Volumes/Work/ClientB/z.py'))
        self.assertEqual(feedback.server_errors()[-1]['msg'], 'EACCES')
        self.assertNotIn('ClientB', json.dumps(feedback.server_errors()))

    def test_route_never_carries_names(self):
        for path, want in (('/it-assets/it1/секретна-назва/x.png', '/it-assets'), ('/t/some-task/api/x', '/api/x'), ('/api/task/it1/node/9', '/api/task'),
                           ('/api/a/b/c/d', '/api/a'), ('/api/спільний/x', '/api/*'), ('/api', '/api'), ('/', '/'), ('', '/')):
            self.assertEqual(feedback.route_of(path), want, path)

    def test_thread_safe(self):
        def work():
            for i in range(100):
                feedback.record_error('/api/t', RuntimeError('x%d' % i))
                feedback.server_errors()
        ts = [threading.Thread(target=work) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(feedback.server_errors()), 50)

    def test_operational_failures_recorded_by_code_only(self):
        """Операційні відмови: у тексті шляхи — у кільці лише код, без `str(e)`."""
        feedback.record_error('/api/task', OSError('cannot read /some/private/path/tasks.json'), code='space-unavailable')
        e = feedback.server_errors()[-1]
        self.assertEqual((e['code'], e['msg']), ('space-unavailable', ''))
        self.assertNotIn('private', json.dumps(e))


class BuildDiag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.normpath(tempfile.mkdtemp(prefix='fb-diag-'))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        env = {'HOME': os.path.join(cls.tmp, 'home'), 'DEAI_HOME': os.path.join(cls.tmp, 'deai'),
               'DC_TASKS_FILE': os.path.join(cls.tmp, 'legacy', 'tasks.json'), 'DC_NO_OVERVIEW': '1', 'DEAI_NO_UPDATE_CHECK': '1'}
        os.makedirs(env['HOME'])
        os.makedirs(os.path.dirname(env['DC_TASKS_FILE']))
        with open(env['DC_TASKS_FILE'], 'w') as f:
            json.dump({'tasks': {}}, f)
        p = mock.patch.dict(os.environ, {'HOME': env['HOME'], 'DEAI_HOME': env['DEAI_HOME'], 'DC_TASKS_FILE': env['DC_TASKS_FILE'],
                                         'DC_NO_OVERVIEW': '1', 'DEAI_NO_UPDATE_CHECK': '1'})
        p.start()
        cls.addClassCleanup(p.stop)
        cls.deai = env['DEAI_HOME']
        spaces.clear_request_space()
        cls.space_path = os.path.join(env['HOME'], 'deai-work', 'Конфіденційно-простір')
        cls.sid = spaces.create_space('Конфіденційно', 'space-2', cls.space_path)
        cls.task_dir = os.path.join(cls.space_path, 'x')
        os.makedirs(os.path.join(cls.task_dir, 'iterations', 'it1', 'shots'))
        with open(os.path.join(cls.space_path, 'tasks.json'), 'w', encoding='utf-8') as f:
            json.dump({'design_work_root': cls.space_path, 'current': 'x',
                       'tasks': {'x': {'title': 'Секрет', 'dir': cls.task_dir, 'track': 'tool'}}}, f, ensure_ascii=False)
        liga_fixture.write_records(cls.space_path, cls.deai, cls.sid, roles=('comments', 'tracker'), name='Конфіденційно')
        cls.sp = next(s for s in spaces.read_registry()['spaces'] if s['id'] == cls.sid)

    def setUp(self):
        feedback.reset_errors()

    def ctx(self, **kw):
        base = {'space': self.sp, 'task_id': 'x', 'iteration': 'it1', 'page': 'home', 'screen': 'canvas', 'lang': 'uk', 'version': '0.23.0',
                'roots': [(self.space_path, '<space>'), (self.task_dir, '<task>')]}
        base.update(kw)
        return base

    def test_fields_exactly(self):
        d = feedback.build_diag(self.ctx())
        self.assertEqual(sorted(d), ['errors', 'lang', 'os', 'space', 'task', 'version'])
        self.assertEqual(sorted(d['os']), ['python', 'release', 'system'])
        self.assertEqual(sorted(d['space']), ['kind', 'migration', 'roles'])
        self.assertEqual(d['task'], {'id': 'x', 'iteration': 'it1', 'page': 'home', 'screen': 'canvas'})
        self.assertEqual(sorted(d['errors']), ['client', 'server'])
        self.assertEqual((d['version'], d['lang']), ('0.23.0', 'uk'))

    def test_no_task_title_no_paths_no_settings(self):
        feedback.record_error('/api/task', OSError('failed at %s/tasks.json' % self.space_path))
        raw = json.dumps(feedback.build_diag(self.ctx(), [{'msg': 'oops in ' + self.task_dir, 'file': 'app/app.js', 'line': 3}]), ensure_ascii=False)
        for needle in ('Конфіденційно', 'Секрет', self.space_path, self.task_dir, self.tmp, os.path.expanduser('~'), 'sb.example.com', 'sb_fixture_key_alpha',
                       liga_fixture.JIRA_BASE, 'alpha@example.com'):
            self.assertNotIn(needle, raw, needle)

    def test_foreign_space_paths_never_leave_the_machine(self):
        """Помилка записана під ІНШИМ простором, відгук зібраний з цього: імена чужих тек і користувача в корисному навантаженні відсутні."""
        feedback.record_error('/api/x', OSError('boom at /Users/me/ClientB-Acme/x/y.json'), code=None)
        for raw in ('/Users/me/ClientB-Acme/x/y.json', '/Volumes/Work/ClientB/z.py', 'C:\\Users\\Іван\\proj\\a.py', '\\\\srv\\sh\\ClientB\\q.py',
                    'file:///Users/me/ClientB-Acme/f.json', '%2FUsers%2Fme%2FClientB-Acme%2Fg.json'):
            feedback.record_error('/api/x', RuntimeError('x'))
        client = [{'msg': 'fetch failed for %s' % raw, 'file': 'app/a.js', 'line': 1} for raw in
                  ('/Users/me/ClientB-Acme/x/y.json', '/Volumes/Work/ClientB/z.py', 'C:\\Users\\Іван\\proj\\a.py', '"/Users/me/Client B/e.py"')]
        payload = json.dumps(feedback.build_diag(self.ctx(), client), ensure_ascii=False)
        for needle in ('ClientB', 'Client B', 'Acme', '/Users/', 'Іван', 'proj', '/Volumes', 'Work/'):
            self.assertNotIn(needle, payload, needle)
        self.assertIn('…/y.json', payload)
        self.assertIn('…/z.py', payload)
        self.assertIn('…/a.py', payload)

    def test_build_diag_recollapses_ring_entries_defence_in_depth(self):
        """Навіть запис у кільці, що потрапив туди неочищеним (старий код, шов), у діагностику йде зі згорнутими шляхами."""
        with feedback._RING_LOCK:
            feedback._RING.append({'route': '/api/x', 'type': 'OSError', 'msg': 'open /Users/me/ClientB-Acme/x/y.json'})
        payload = json.dumps(feedback.build_diag(self.ctx()), ensure_ascii=False)
        self.assertNotIn('ClientB-Acme', payload)
        self.assertIn('…/y.json', payload)

    def test_client_messages_pass_the_extended_redaction(self):
        got = feedback.sanitize_client_errors([{'msg': 'ЄДРПОУ 12345678 ІПН 1234567890 UA213223130000026007233566001 password=hunter2', 'file': '', 'line': 1}])
        m = got[0]['msg']
        for needle in ('12345678', '1234567890', 'UA2132', 'hunter2'):
            self.assertNotIn(needle, m)

    def test_roles_are_ids_only_and_own_modules_are_anonymised(self):
        d = feedback.build_diag(self.ctx())
        self.assertEqual(d['space']['roles']['comments'], 'supabase-comments')
        self.assertEqual(d['space']['roles']['tracker'], 'jira-tracker')
        self.assertIsNone(d['space']['roles']['vcs'])
        with mock.patch.object(deai_modules, 'capabilities', return_value={'comments': 'my-secret-module'}):
            d = feedback.build_diag(self.ctx())
        self.assertEqual(d['space']['roles']['comments'], 'own')
        self.assertNotIn('my-secret-module', json.dumps(d))

    def test_migration_names_whitelisted(self):
        with mock.patch.object(deai_modules, '_load_space_json',
                               return_value={'migrations': {'liga-4d3a': {'at': 'x'}, 'liga-4d4b': {}, 'Мій приватний крок': {}, '../x': {}}}):
            d = feedback.build_diag(self.ctx())
        self.assertEqual(d['space']['migration'], {'liga-4d3a': 'applied', 'liga-4d4b': 'applied'})

    def test_client_errors_sanitised_and_capped(self):
        raw = [{'msg': 'm%d' % i, 'file': 'app/app.js', 'line': i} for i in range(100)]
        raw += ['junk', 5, None, ['x']]
        got = feedback.sanitize_client_errors(raw)
        self.assertEqual(len(got), 20)
        self.assertEqual(got[-1]['msg'], 'm99')
        got = feedback.sanitize_client_errors([{'msg': 'z' * 900, 'file': 'http://evil/x.js', 'line': 'NaN', 'extra': 'x'},
                                               {'msg': 'ok', 'file': 'app/ok.js', 'line': -3},
                                               {'msg': 'a', 'file': 'app/../../etc/passwd', 'line': 7}])
        self.assertEqual(len(got[0]['msg']), 200, 'клієнтський msg ≤ 200')
        self.assertEqual((got[0]['file'], got[0]['line']), ('', None))
        self.assertEqual(sorted(got[0]), ['file', 'line', 'msg'])
        self.assertEqual((got[1]['file'], got[1]['line']), ('app/ok.js', None))
        self.assertEqual(got[2]['file'], '', 'шлях з `..` не приймається')
        self.assertEqual(feedback.sanitize_client_errors('x'), [])
        self.assertEqual(feedback.sanitize_client_errors(None), [])

    def test_size_cap_64k_drops_errors_first(self):
        big = [{'msg': 'x' * 300, 'file': 'app/app.js', 'line': 1}] * 20
        with mock.patch.object(feedback, 'DIAG_MAX_BYTES', 1500):
            d = feedback.build_diag(self.ctx(), big)
        self.assertEqual(d['errors'], {'server': [], 'client': [], 'dropped': True})
        self.assertEqual(d['version'], '0.23.0')

    def test_total_function_on_broken_registry_and_no_task(self):
        d = feedback.build_diag({'space': None, 'task_id': None})
        self.assertIsNone(d['space'])
        self.assertIsNone(d['task'])
        d = feedback.build_diag(None)
        self.assertEqual(sorted(d), ['errors', 'lang', 'os', 'space', 'task', 'version'])
        d = feedback.build_diag(self.ctx(space={'id': 'zz', 'path': os.path.join(self.tmp, 'nowhere')}, task_id=5, page='../x', screen='a b'))
        self.assertEqual(d['task'], {'id': None, 'iteration': 'it1', 'page': None, 'screen': None})

    def test_secret_like_strings_in_errors_are_hidden(self):
        secret = 'sb_secret_' + 'A1b2C3d4E5f6G7h8'
        jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.abcdefghijk'
        feedback.record_error('/api/x', RuntimeError('boom %s and %s mail bob@example.com https://h.example/p?token=zzz' % (secret, jwt)))
        raw = json.dumps(feedback.build_diag(self.ctx(), [{'msg': 'client ' + secret + ' ' + jwt, 'file': 'app/a.js', 'line': 1}]))
        for needle in (secret, jwt, 'bob@example.com', 'token=zzz'):
            self.assertNotIn(needle, raw)

    def test_every_string_goes_through_redact(self):
        """Кожен рядок діагностики проходить `redact.text`: підміна його видимо діє на всі поля."""
        calls = []
        real = feedback.redact.text

        def spy(value, *a, **k):
            calls.append(value)
            return real(value, *a, **k)
        feedback.record_error('/api/x', RuntimeError('boom'))
        with mock.patch.object(feedback.redact, 'text', spy):
            feedback.build_diag(self.ctx(), [{'msg': 'client-msg', 'file': 'app/a.js', 'line': 1}])
        for want in ('0.23.0', 'client-msg', 'RuntimeError', '/api/x', 'x', 'it1', 'home', 'canvas'):
            self.assertIn(want, calls)


class Hooks(unittest.TestCase):
    """`_guarded` пише в кільце; поведінка відповіді не змінюється."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='fb-hook-')
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        env = {'HOME': os.path.join(cls.tmp, 'home'), 'DEAI_HOME': os.path.join(cls.tmp, 'deai'),
               'DC_TASKS_FILE': os.path.join(cls.tmp, 'tasks.json'), 'DC_NO_OVERVIEW': '1', 'DEAI_NO_UPDATE_CHECK': '1'}
        os.makedirs(env['HOME'])
        p = mock.patch.dict(os.environ, env)
        p.start()
        cls.addClassCleanup(p.stop)
        cls.httpd = serve.make_server(0)
        cls.httpd.handle_error = lambda request, client_address: None      # обрив зʼєднання — це і є очікуваний результат
        cls.base = 'http://127.0.0.1:%d' % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.httpd.shutdown)

    def setUp(self):
        feedback.reset_errors()

    def post(self, path='/api/feedback-preview'):
        req = urllib.request.Request(self.base + path, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def boom(self, exc):
        def handler(handler_self, payload):
            raise exc
        return mock.patch.object(serve.Handler, '_feedback_preview', handler)

    def test_guarded_records_unexpected_and_reraises(self):
        with self.boom(RuntimeError('secret detail at %s/x' % os.path.expanduser('~'))):
            with self.assertRaises((urllib.error.URLError, ConnectionError, OSError, Exception)):
                self.post()
        e = feedback.server_errors()[-1]
        self.assertEqual((e['route'], e['type']), ('/api/feedback-preview', 'RuntimeError'))
        self.assertNotIn('secret detail', json.dumps(e), 'текст винятку не потрапляє в кільце')
        self.assertRegex(e['msg'], r'^at serve\.py:\d+$')

    def test_disconnects_not_recorded(self):
        for exc in (BrokenPipeError(), ConnectionResetError(), ConnectionAbortedError()):
            with self.boom(exc):
                try:
                    self.post()
                except Exception:  # noqa: BLE001 — зʼєднання рветься, як і раніше
                    pass
        self.assertEqual(feedback.server_errors(), [])

    def test_expected_4xx_not_recorded(self):
        for exc, status in ((spaces.NoTask(None), 404), (spaces.AmbiguousTask('x'), 409), (deai_modules.ModuleError('unknown-module', 404), 404)):
            with self.boom(exc):
                st, body = self.post()
            self.assertEqual(st, status)
        self.assertEqual(feedback.server_errors(), [])

    def test_operational_failures_recorded_by_code_only(self):
        cases = ((serve.SpaceUnavailable('/very/private/tasks.json'), 503, 'space-unavailable'),
                 (spaces.SpacesError('spaces-unreadable', '/very/private/spaces.json', 'bad'), 503, 'spaces-unreadable'),
                 (deai_modules.ModuleError('module-error', 502, 'leak /very/private/x'), 502, 'module-error'))
        for exc, status, code in cases:
            feedback.reset_errors()
            with self.boom(exc):
                st, body = self.post()
            self.assertEqual((st, body.get('code')), (status, code))
            e = feedback.server_errors()[-1]
            self.assertEqual((e['code'], e['msg']), (code, ''))
            self.assertNotIn('private', json.dumps(e))


class ShotChoice(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.normpath(tempfile.mkdtemp(prefix='fb-shot-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.task = {'dir': os.path.join(self.tmp, 't')}
        self.shots = os.path.join(self.task['dir'], 'iterations', 'it1', 'shots')
        os.makedirs(self.shots)
        with open(os.path.join(self.shots, 'home.webp'), 'wb') as f:
            f.write(b'RIFFxxxxWEBP')

    def test_shot_file_double_lock(self):
        self.assertEqual(serve._shot_file(self.task, 'it1', 'home'), os.path.realpath(os.path.join(self.shots, 'home.webp')))
        for it, node in (('it1', '../x'), ('../it1', 'home'), ('it1', 'absent'), (None, 'home'), ('it1', 5), ('it1', 'home\n')):
            self.assertIsNone(serve._shot_file(self.task, it, node), (it, node))
        outside = os.path.join(self.tmp, 'outside.webp')
        with open(outside, 'wb') as f:
            f.write(b'x')
        os.symlink(outside, os.path.join(self.shots, 'link.webp'))
        self.assertIsNone(serve._shot_file(self.task, 'it1', 'link'))

    def test_shot_over_2mb_is_skipped_not_truncated(self):
        big = os.path.join(self.shots, 'big.webp')
        with open(big, 'wb') as f:
            f.truncate(feedback.SHOT_MAX_BYTES + 1)
        self.assertEqual(feedback.shot_info(big), {'available': False, 'bytes': feedback.SHOT_MAX_BYTES + 1, 'skipped': 'too-big'})
        ok = os.path.join(self.shots, 'home.webp')
        self.assertEqual(feedback.shot_info(ok), {'available': True, 'bytes': 12})
        self.assertEqual(feedback.shot_info(None), {'available': False})
        self.assertEqual(feedback.shot_info(os.path.join(self.shots, 'nope.webp')), {'available': False})


class PreviewApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.normpath(tempfile.mkdtemp(prefix='fb-prev-'))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        env = {'HOME': os.path.join(cls.tmp, 'home'), 'DEAI_HOME': os.path.join(cls.tmp, 'deai'),
               'DC_TASKS_FILE': os.path.join(cls.tmp, 'legacy', 'tasks.json'), 'DC_NO_OVERVIEW': '1', 'DEAI_NO_UPDATE_CHECK': '1'}
        os.makedirs(env['HOME'])
        p = mock.patch.dict(os.environ, env)
        p.start()
        cls.addClassCleanup(p.stop)
        cls.deai = env['DEAI_HOME']
        spaces.clear_request_space()
        cls.httpd = serve.make_server(0)
        cls.base = 'http://127.0.0.1:%d' % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.httpd.shutdown)

    def call(self, body, origin=None, path='/api/feedback-preview', raw=None):
        h = {'Content-Type': 'application/json'}
        if origin:
            h['Origin'] = origin
        data = raw if raw is not None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers=h, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_empty_machine_answers(self):
        st, body = self.call({'lang': 'uk', 'task': 'nope', 'client_errors': [{'msg': 'boom', 'file': 'app/app.js', 'line': 4}]})
        self.assertEqual(st, 200, body)
        self.assertTrue(body['ok'])
        self.assertEqual(body['shot'], {'available': False})
        self.assertIsNone(body['diag']['task'])
        self.assertEqual(body['diag']['lang'], 'uk')
        self.assertEqual(body['diag']['errors']['client'], [{'msg': 'boom', 'file': 'app/app.js', 'line': 4}])
        self.assertNotIn(self.tmp, json.dumps(body))

    def test_origin_gate_bad_body_and_task_prefix(self):
        self.assertEqual(self.call({}, origin='https://evil.example')[0], 403)
        for ok_origin in (None, 'http://localhost:8765', 'http://127.0.0.1:8765'):
            self.assertEqual(self.call({}, origin=ok_origin)[0], 200, ok_origin)
        st, body = self.call(None, raw=b'[]')
        self.assertEqual((st, body.get('code')), (400, 'bad-body'))
        self.assertEqual(self.call({}, path='/t/x/api/feedback-preview')[0], 400)

    def test_works_with_a_broken_registry(self):
        os.makedirs(self.deai, exist_ok=True)
        reg = os.path.join(self.deai, 'spaces.json')
        with open(reg, 'w') as f:
            f.write('{')
        self.addCleanup(lambda: os.path.exists(reg) and os.remove(reg))
        st, body = self.call({'task': 'x'})
        self.assertEqual(st, 200, body)
        self.assertIsNone(body['diag']['space'])

    def test_real_task_space_and_shot(self):
        space_path = os.path.join(os.environ['HOME'], 'deai-work', 'sp')
        sid = spaces.create_space('Приватна назва', 'space-2', space_path)
        self.addCleanup(lambda: None)
        tdir = os.path.join(space_path, 'x')
        shots = os.path.join(tdir, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        with open(os.path.join(shots, 'home.webp'), 'wb') as f:
            f.write(b'RIFFxxxxWEBP')
        with open(os.path.join(space_path, 'tasks.json'), 'w', encoding='utf-8') as f:
            json.dump({'design_work_root': space_path, 'current': 'x', 'tasks': {'x': {'title': 'Назва Задачі', 'dir': tdir, 'track': 'tool'}}}, f, ensure_ascii=False)
        st, body = self.call({'task': 'x', 'it': 'it1', 'node': 'home', 'screen': 'canvas', 'lang': 'en'})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['shot'], {'available': True, 'bytes': 12})
        self.assertEqual(body['diag']['task'], {'id': 'x', 'iteration': 'it1', 'page': 'home', 'screen': 'canvas'})
        self.assertEqual(body['diag']['space']['kind'], 'regular')
        raw = json.dumps(body, ensure_ascii=False)
        for needle in ('Назва Задачі', 'Приватна назва', space_path, tdir):
            self.assertNotIn(needle, raw)
        for bad in ({'it': '../x', 'node': 'home'}, {'it': 'it1', 'node': '../x'}, {'it': 5, 'node': 'home'}, {'it': 'it1', 'node': 'absent'}):
            st, body = self.call(dict(bad, task='x'))
            self.assertEqual((st, body['shot']), (200, {'available': False}), bad)
        self.assertTrue(sid)


if __name__ == '__main__':
    unittest.main()
