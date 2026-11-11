"""Відгук, T7: `POST /api/feedback` — HTTP-шар. Сервер у процесі (`make_server(0)`), приймач — фейк на `127.0.0.1` (дозволено лише ізольованому прогону:
`DC_TASKS_FILE`). Мережі нема; `DEAI_HOME`, `HOME`, `DC_TASKS_FILE` — тимчасові."""
import json
import os
import shutil
import stat
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
import feedback  # noqa: E402
import liga_fixture  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
from test_feedback_outbox import FakeReceiver, WEBP  # noqa: E402

_REAL = None
TEXT = 'Кнопка «Опублікувати» нічого не робить'


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class FeedbackApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.normpath(tempfile.mkdtemp(prefix='fb-api-'))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        cls.home = os.path.join(cls.tmp, 'home')
        cls.deai = os.path.join(cls.tmp, 'deai')
        os.makedirs(cls.home)
        os.makedirs(os.path.join(cls.tmp, 'legacy'))
        with open(os.path.join(cls.tmp, 'legacy', 'tasks.json'), 'w') as f:
            json.dump({'tasks': {}}, f)
        p = mock.patch.dict(os.environ, {'HOME': cls.home, 'DEAI_HOME': cls.deai, 'DC_TASKS_FILE': os.path.join(cls.tmp, 'legacy', 'tasks.json'),
                                         'DC_NO_OVERVIEW': '1', 'DEAI_NO_UPDATE_CHECK': '1'})
        p.start()
        cls.addClassCleanup(p.stop)
        spaces.clear_request_space()
        cls.httpd = serve.make_server(0)
        cls.base = 'http://127.0.0.1:%d' % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.httpd.shutdown)

    def setUp(self):
        for k in ('DEAI_FEEDBACK_URL', 'DEAI_FEEDBACK_KEY'):
            os.environ.pop(k, None)
        empty = os.path.join(self.tmp, 'shipped.json')
        with open(empty, 'w') as f:
            f.write('{"url": "", "key": ""}')
        for patcher in (mock.patch.object(feedback, 'SHIPPED_CONFIG', empty), mock.patch.object(feedback, 'OUTBOX', feedback.Outbox())):
            patcher.start()
            self.addCleanup(patcher.stop)
        shutil.rmtree(self.deai, ignore_errors=True)                 # свіжий реєстр на кожен тест: задача `x` не двічі
        shutil.rmtree(os.path.join(self.home, 'deai-work'), ignore_errors=True)
        feedback.reset_errors()

    def receiver(self, **kw):
        rx = FakeReceiver()
        self.addCleanup(rx.close)
        for k, v in kw.items():
            setattr(rx, k, v)
        os.environ['DEAI_FEEDBACK_URL'], os.environ['DEAI_FEEDBACK_KEY'] = rx.url, 'sb_publishable_test'
        return rx

    def call(self, body, origin=None, path='/api/feedback', raw=None, headers=None, hashed=True):
        """`hashed`: перед відправкою з діагностикою людина «бачить» перегляд, тож `diag_hash` береться з нього (як робить інтерфейс)."""
        if (hashed and raw is None and path == '/api/feedback' and isinstance(body, dict) and body.get('include_diag', True) is True
                and 'diag_hash' not in body and origin in (None, 'http://localhost:8765', 'http://127.0.0.1:8765')):
            _, pv = self.call(body, path='/api/feedback-preview', hashed=False)
            body = dict(body, diag_hash=pv.get('diag_hash'), ring_seq=pv.get('ring_seq'))
        h = {'Content-Type': 'application/json', **(headers or {})}
        if origin:
            h['Origin'] = origin
        data = raw if raw is not None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers=h, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def box(self, bucket='outbox'):
        d = os.path.join(self.deai, 'feedback', bucket)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def make_task(self, title='Секретна назва задачі', shot=True):
        space_path = os.path.join(self.home, 'deai-work', 'sp')
        sid = spaces.create_space('Конфіденційний простір', 'space-2', space_path)
        tdir = os.path.join(space_path, 'x')
        shots = os.path.join(tdir, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        if shot:
            with open(os.path.join(shots, 'home.webp'), 'wb') as f:
                f.write(WEBP)
        with open(os.path.join(space_path, 'tasks.json'), 'w', encoding='utf-8') as f:
            json.dump({'design_work_root': space_path, 'current': 'x', 'tasks': {'x': {'title': title, 'dir': tdir, 'track': 'tool'}}}, f, ensure_ascii=False)
        return sid, space_path, tdir

    # --- форма й ворота ---

    def test_shape_and_no_collector_goes_to_the_local_queue(self):
        st, body = self.call({'kind': 'bug', 'text': TEXT, 'contact': 'me@example.com'})
        self.assertEqual(st, 200, body)
        self.assertEqual(sorted(body), ['id', 'number', 'ok', 'reason', 'state'])
        self.assertEqual((body['ok'], body['state'], body['reason']), (True, 'queued', 'no-collector'))
        self.assertEqual(body['number'], body['id'][:8])
        self.assertEqual(self.box(), [body['id'] + '.json'])
        path = os.path.join(self.deai, 'feedback', 'outbox', body['id'] + '.json')
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)
        with open(path, encoding='utf-8') as f:
            rec = json.load(f)
        self.assertEqual((rec['text'], rec['contact'], rec['kind']), (TEXT, 'me@example.com', 'bug'))
        self.assertNotIn(self.tmp, json.dumps(rec['diag']))

    def test_a_space_with_supabase_modules_still_yields_no_collector(self):
        """⛔ Відгук НІКОЛИ не береться з Supabase/секретів модулів простору (коментарі, дашборд, Teams ЛІГИ): лише власний ланцюг конфігу."""
        sid, space_path, tdir = self.make_task()
        liga_fixture.write_records(space_path, self.deai, sid, roles=('comments', 'dashboard', 'notify'), name='Конфіденційний простір')
        with mock.patch.object(feedback, 'SupabaseSender', side_effect=AssertionError('мережі не було б')):
            st, body = self.call({'kind': 'bug', 'text': TEXT, 'task': 'x'})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['state'], body['reason']), ('queued', 'no-collector'))
        self.assertIsNone(feedback.config())

    def test_origin_gate_bad_body_task_prefix(self):
        self.assertEqual(self.call({'kind': 'bug', 'text': TEXT}, origin='https://evil.example')[0], 403)
        self.assertEqual(self.box(), [], 'відмова Origin нічого не пише')
        for ok_origin in (None, 'http://localhost:8765', 'http://127.0.0.1:8765'):
            self.assertEqual(self.call({'kind': 'bug', 'text': TEXT}, origin=ok_origin)[0], 200, ok_origin)
        st, body = self.call(None, raw=b'[]')
        self.assertEqual((st, body.get('code')), (400, 'bad-body'))
        self.assertEqual(self.call({'kind': 'bug', 'text': TEXT}, path='/t/x/api/feedback')[0], 400)

    def test_works_on_an_empty_machine_and_with_a_broken_registry(self):
        self.assertEqual(self.call({'kind': 'idea', 'text': TEXT, 'task': 'no-such-task'})[0], 200)
        os.makedirs(self.deai, exist_ok=True)
        reg = os.path.join(self.deai, 'spaces.json')
        with open(reg, 'w') as f:
            f.write('{')
        self.addCleanup(lambda: os.path.exists(reg) and os.remove(reg))
        st, body = self.call({'kind': 'idea', 'text': TEXT})
        self.assertEqual((st, body['state']), (200, 'queued'))

    def test_validation_errors_write_nothing(self):
        cases = ({'kind': 'x', 'text': TEXT}, {'kind': 'bug', 'text': 'коротко'}, {'kind': 'bug', 'text': 'я' * 10001},
                 {'kind': 'bug', 'text': TEXT, 'contact': 'c' * 201}, {'kind': 'bug', 'text': TEXT, 'include_diag': 'так'},
                 {'kind': 'bug', 'text': TEXT, 'include_shot': 1}, {'text': TEXT})
        for body in cases:
            st, got = self.call(body)
            self.assertEqual((st, got['ok']), (400, False), body)
            self.assertIn(got['code'], ('bad-kind', 'text-too-short', 'text-too-long', 'contact-too-long', 'bad-flag'))
        self.assertEqual(self.box(), [])

    def test_oversized_body_is_413_before_reading(self):
        st, got = self.call({'kind': 'bug', 'text': TEXT, 'pad': 'x' * (feedback.BODY_MAX + 10)})
        self.assertEqual((st, got['code']), (413, 'body-too-large'))
        self.assertEqual(self.call({'kind': 'bug', 'text': TEXT, 'pad': 'x' * (feedback.BODY_MAX + 10)}, path='/api/feedback-preview')[0], 413)
        self.assertEqual(self.box(), [])

    # --- з приймачем ---

    def test_row_arrives_with_redacted_diagnostics_without_the_task_title(self):
        rx = self.receiver()
        sid, space_path, tdir = self.make_task()
        st, body = self.call({'kind': 'bug', 'text': TEXT, 'task': 'x', 'it': 'it1', 'node': 'home', 'screen': 'canvas', 'lang': 'uk',
                              'client_errors': [{'msg': 'boom at ' + tdir, 'file': 'app/app.js', 'line': 9}], 'include_diag': True})
        self.assertEqual((st, body['state']), (200, 'sent'), body)
        self.assertNotIn('reason', body)
        row = rx.rows()[0]
        self.assertEqual(sorted(row), sorted(feedback.ROW_COLUMNS))
        self.assertEqual((row['id'], row['kind'], row['text']), (body['id'], 'bug', TEXT))
        self.assertEqual(row['diag']['task'], {'id': 'x', 'iteration': 'it1', 'page': 'home', 'screen': 'canvas'})
        self.assertEqual(row['diag']['errors']['client'][0]['msg'], 'boom at <task>')
        raw = json.dumps(row, ensure_ascii=False)
        for needle in ('Секретна назва задачі', 'Конфіденційний простір', tdir, space_path, self.tmp):
            self.assertNotIn(needle, raw)
        self.assertEqual(self.box('sent'), [body['id'] + '.json'])
        self.assertEqual(rx.requests[0]['headers']['apikey'], 'sb_publishable_test')

    def test_include_diag_false_sends_an_empty_object(self):
        rx = self.receiver()
        self.make_task()
        st, body = self.call({'kind': 'idea', 'text': TEXT, 'task': 'x', 'include_diag': False})
        self.assertEqual(body['state'], 'sent')
        self.assertEqual(rx.rows()[0]['diag'], {})

    def test_include_shot_without_a_frame_sends_the_row_without_it(self):
        rx = self.receiver()
        self.make_task(shot=False)
        st, body = self.call({'kind': 'bug', 'text': TEXT, 'task': 'x', 'it': 'it1', 'node': 'home', 'include_shot': True})
        self.assertEqual((st, body['state']), (200, 'sent'))
        self.assertIsNone(rx.rows()[0]['shot_path'])
        self.assertEqual(rx.shots(), {})
        st, body = self.call({'kind': 'bug', 'text': TEXT, 'include_shot': True})              # без задачі взагалі
        self.assertEqual((st, body['state']), (200, 'sent'))

    def test_include_shot_with_a_frame_uploads_it_first(self):
        rx = self.receiver()
        self.make_task()
        st, body = self.call({'kind': 'bug', 'text': TEXT, 'task': 'x', 'it': 'it1', 'node': 'home', 'include_shot': True})
        self.assertEqual((st, body['state']), (200, 'sent'), body)
        self.assertEqual(rx.rows()[0]['shot_path'], body['id'] + '.webp')
        self.assertEqual(rx.shots(), {body['id'] + '.webp': WEBP})
        self.assertEqual([r['path'].split('/')[1] for r in rx.requests], ['storage', 'rest'])
        # кадр не названо (чи названо криво) — рядок без скриншота, не помилка
        st, body = self.call({'kind': 'bug', 'text': TEXT, 'task': 'x', 'it': '../x', 'node': 'home', 'include_shot': True})
        self.assertEqual((st, body['state']), (200, 'sent'))
        self.assertIsNone(rx.rows()[1]['shot_path'])

    def test_network_down_is_queued_and_the_request_never_drains_the_backlog(self):
        """Запит пробує ЛИШЕ свій запис: хвіст черги — справа фонового потоку (`flush_pending`), запит ніколи на нього не чекає."""
        rx = self.receiver(rest_status=503)
        st, first = self.call({'kind': 'bug', 'text': TEXT})
        self.assertEqual((st, first['ok'], first['state'], first['reason']), (200, True, 'queued', 'offline'))
        self.assertEqual(self.box(), [first['id'] + '.json'])
        rx.rest_status = 201
        n = len(rx.requests)
        st, second = self.call({'kind': 'idea', 'text': TEXT + ' (другий)'})
        self.assertEqual(second['state'], 'sent')
        self.assertEqual(len(rx.requests) - n, 1, 'другий запит торкнувся лише свого запису')
        self.assertEqual([r['id'] for r in rx.rows()], [second['id']])
        self.assertEqual(self.box('outbox'), [first['id'] + '.json'])
        self.assertEqual(feedback.flush_pending(), 1)                        # фоновий прохід дочищає хвіст
        self.assertEqual(sorted(r['id'] for r in rx.rows()), sorted([first['id'], second['id']]))
        self.assertEqual((self.box('outbox'), len(self.box('sent'))), ([], 2))

    def test_diag_hash_must_match_the_preview(self):
        rx = self.receiver()
        self.make_task()
        body = {'kind': 'bug', 'text': TEXT, 'task': 'x', 'lang': 'uk', 'client_errors': [{'msg': 'a', 'file': 'app/a.js', 'line': 1}]}
        st, pv = self.call(body, path='/api/feedback-preview')
        self.assertEqual(sorted(pv), ['diag', 'diag_hash', 'ok', 'ring_seq', 'shot'])
        self.assertEqual(pv['diag_hash'], feedback.diag_hash(pv['diag']))
        self.assertRegex(pv['diag_hash'], r'^[0-9a-f]{64}$')
        self.assertIsInstance(pv['ring_seq'], int)
        pinned = dict(body, diag_hash=pv['diag_hash'], ring_seq=pv['ring_seq'])
        # не-кільцева зміна (мова, задача) → 409 з новою діагностикою; нічого не записано й не надіслано
        st, got = self.call(dict(pinned, lang='en'), hashed=False)
        self.assertEqual((st, got['ok'], got['code']), (409, False, 'diag-changed'))
        self.assertEqual(got['diag_hash'], feedback.diag_hash(got['diag']))
        self.assertNotEqual(got['diag_hash'], pv['diag_hash'])
        self.assertEqual(got['ring_seq'], pv['ring_seq'])
        self.assertEqual(self.call(dict(pinned, task='no-such'), hashed=False)[1].get('code'), 'diag-changed')
        self.assertEqual((self.box(), self.box('sent'), rx.rows()), ([], [], []))
        # хеш відсутній чи чужий → теж 409
        for bad in ({'diag_hash': None}, {'diag_hash': 5}, {'diag_hash': 'x' * 64}):
            self.assertEqual(self.call(dict(pinned, **bad), hashed=False)[1].get('code'), 'diag-changed', bad)
        self.assertEqual(self.box(), [])
        # свіжий хеш → відправка
        st, ok = self.call(dict(pinned, lang='en', diag_hash=got['diag_hash']), hashed=False)
        self.assertEqual((st, ok['state']), (200, 'sent'))
        # без діагностики хеш не потрібен
        st, ok = self.call(dict(body, include_diag=False), hashed=False)
        self.assertEqual((st, ok['state']), (200, 'sent'))

    def test_new_ring_entries_after_the_preview_never_block_the_send(self):
        """Опитуваний маршрут, що падає на КОЖЕН запит: кільце змінюється між переглядом і відправкою, а відправка все одно йде з першого разу."""
        rx = self.receiver()
        body = {'kind': 'bug', 'text': TEXT, 'lang': 'uk'}
        feedback.record_error('/api/poll', RuntimeError('x'))
        for n in range(3):
            st, pv = self.call(body, path='/api/feedback-preview')
            feedback.record_error('/api/poll', RuntimeError('x'))          # дубль (count росте)…
            feedback.record_error('/api/fresh%d' % n, RuntimeError('x'))   # …і зовсім новий запис
            st, got = self.call(dict(body, diag_hash=pv['diag_hash'], ring_seq=pv['ring_seq']), hashed=False)
            self.assertEqual((st, got['state']), (200, 'sent'), got)
            sent = rx.rows()[-1]['diag']['errors']['server']
            self.assertEqual(sent, pv['diag']['errors']['server'], 'надіслано рівно те, що бачили')
            self.assertFalse(any(e['route'].startswith('/api/fresh') and e['route'] == '/api/fresh%d' % n for e in sent))

    def test_lone_surrogates_and_nul_never_break_the_queue(self):
        rx = self.receiver()
        st, a = self.call({'kind': 'bug', 'text': TEXT + ' abc \ud800 def', 'contact': 'a\x00b \udfff'})
        self.assertEqual((st, a['state']), (200, 'sent'), a)
        row = rx.rows()[0]
        self.assertEqual(row['text'], TEXT + ' abc ? def')
        self.assertEqual(row['contact'], 'ab ?')
        rx.close()
        st, b = self.call({'kind': 'bug', 'text': TEXT + ' a\x00b \ud800'})
        self.assertEqual((st, b['state']), (200, 'queued'))
        with open(os.path.join(self.deai, 'feedback', 'outbox', b['id'] + '.json'), 'rb') as f:
            json.loads(f.read().decode('utf-8'))

    def test_unreachable_receiver_is_queued(self):
        rx = self.receiver()
        rx.close()                                                                                # порт закрито: connection refused
        st, body = self.call({'kind': 'bug', 'text': TEXT})
        self.assertEqual((st, body['ok'], body['state'], body['reason']), (200, True, 'queued', 'offline'))
        self.addCleanup(lambda: None)

    def test_the_message_text_is_never_logged_to_stderr(self):
        import io
        import contextlib
        err = io.StringIO()
        self.receiver(rest_status=503)
        with contextlib.redirect_stderr(err):
            self.call({'kind': 'bug', 'text': TEXT, 'contact': 'private@example.com'})
        self.assertNotIn(TEXT, err.getvalue())
        self.assertNotIn('private@example.com', err.getvalue())
        self.assertNotIn(TEXT, json.dumps(feedback.server_errors(), ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
