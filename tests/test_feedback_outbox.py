"""Відгук, T7: конфіг приймача, локальна черга, повтори, надсилання в Supabase (insert + Storage).

⛔ Мережі нема: відправник перевіряється підробним `opener` або приймачем на `http://127.0.0.1:<порт>` у потоці тесту (дозволено лише при
`isolation.isolated()`). Тимчасові `HOME`/`DEAI_HOME`; справжній `~/.deai` стереже `spaces_guard`."""
import http.server
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), 'app')
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import feedback  # noqa: E402
import isolation  # noqa: E402
import spaces_guard  # noqa: E402

_REAL = None
URL, KEY = 'https://sb.example.com', 'sb_publishable_test'
WEBP = b'RIFF\x04\x00\x00\x00WEBPVP8 '


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class FakeReceiver:
    """Приймач на `127.0.0.1:0`: `POST /rest/v1/feedback` (дубль id → 409) і `POST /storage/v1/object/feedback-shots/<name>` (дубль → 409)."""

    def __init__(self):
        self.requests, self.rows_, self.shots_ = [], [], {}
        self.rest_status, self.storage_status = 201, 200
        self._lock = threading.Lock()
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                with outer._lock:
                    outer.requests.append({'path': self.path, 'headers': {k.lower(): v for k, v in self.headers.items()}, 'body': body})
                    status = 404
                    if self.path == '/rest/v1/feedback':
                        row = json.loads(body)
                        status = outer.rest_status
                        if status == 201:
                            if any(r['id'] == row['id'] for r in outer.rows_):
                                status = 409
                            else:
                                outer.rows_.append(row)
                    elif self.path.startswith('/storage/v1/object/feedback-shots/'):
                        name = self.path.rsplit('/', 1)[1]
                        status = outer.storage_status
                        if status == 200:
                            if name in outer.shots_:
                                status = 409
                            else:
                                outer.shots_[name] = body
                self.send_response(status)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = 'http://127.0.0.1:%d' % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def rows(self):
        with self._lock:
            return list(self.rows_)

    def shots(self):
        with self._lock:
            return dict(self.shots_)


class FakeOpener:
    """`opener(req, timeout)`: відповіді за сценарієм (`status` або виняток), усі запити — у `calls`."""

    class Resp:
        def __init__(self, status, body=b'{}'):
            self.status, self._b = status, body

        def read(self, n=-1):
            return self._b[:n] if n and n > 0 else self._b

        def close(self):
            pass

        def getcode(self):
            return self.status

    def __init__(self, script=None, default=201):
        self.calls, self.script, self.default = [], list(script or []), default

    def __call__(self, req, timeout=None):
        self.calls.append({'url': req.full_url, 'headers': {k.lower(): v for k, v in req.header_items()}, 'body': req.data, 'timeout': timeout})
        item = self.script.pop(0) if self.script else self.default
        if isinstance(item, BaseException):
            raise item
        status, body = item if isinstance(item, tuple) else (item, b'{}')
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, 'x', {}, __import__('io').BytesIO(body))
        return self.Resp(status, body)


def clean(kind='bug', text='Кнопка не працює, коли я натискаю', contact=None, include_diag=True):
    return {'kind': kind, 'text': text, 'contact': contact, 'include_diag': include_diag, 'include_shot': True}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.normpath(tempfile.mkdtemp(prefix='fb-out-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, 'deai')
        env = {'DEAI_HOME': self.home, 'HOME': os.path.join(self.tmp, 'home')}
        os.makedirs(env['HOME'])
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for k in ('DEAI_FEEDBACK_URL', 'DEAI_FEEDBACK_KEY', 'DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
            os.environ.pop(k, None)
        empty = os.path.join(self.tmp, 'shipped.json')
        with open(empty, 'w') as f:
            f.write('{"url": "", "key": ""}')
        p2 = mock.patch.object(feedback, 'SHIPPED_CONFIG', empty)
        p2.start()
        self.addCleanup(p2.stop)
        self.ob = feedback.Outbox(home_fn=lambda: self.home)
        p3 = mock.patch.object(feedback, 'OUTBOX', self.ob)
        p3.start()
        self.addCleanup(p3.stop)

    def configure(self, url=URL, key=KEY):
        os.environ['DEAI_FEEDBACK_URL'] = url
        os.environ['DEAI_FEEDBACK_KEY'] = key

    def sender(self, opener):
        return feedback.SupabaseSender(URL, KEY, opener=opener)

    def box(self, bucket='outbox'):
        d = os.path.join(self.home, 'feedback', bucket)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []


class Config(Base):
    def write_home_cfg(self, data):
        os.makedirs(self.home, exist_ok=True)
        with open(os.path.join(self.home, 'config.json'), 'w') as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def write_shipped(self, url, key):
        with open(feedback.SHIPPED_CONFIG, 'w') as f:
            json.dump({'url': url, 'key': key}, f)

    def test_precedence_env_over_home_config_over_app_file(self):
        self.write_shipped('https://shipped.example.com', 'sb_publishable_shipped')
        self.assertEqual(feedback.config(env={}, home=self.home), {'url': 'https://shipped.example.com', 'key': 'sb_publishable_shipped'})
        self.write_home_cfg({'feedback': {'url': 'https://home.example.com/', 'key': 'sb_publishable_home'}})
        self.assertEqual(feedback.config(env={}, home=self.home), {'url': 'https://home.example.com', 'key': 'sb_publishable_home'})
        env = {'DEAI_FEEDBACK_URL': 'https://env.example.com', 'DEAI_FEEDBACK_KEY': 'sb_publishable_env'}
        self.assertEqual(feedback.config(env=env, home=self.home), {'url': 'https://env.example.com', 'key': 'sb_publishable_env'})

    def test_empty_env_url_switches_the_collector_off(self):
        """Явно порожній `DEAI_FEEDBACK_URL` — вимикач, навіть коли постачальний файл і config.json мають адресу+ключ."""
        self.write_shipped('https://shipped.example.com', 'sb_publishable_shipped')
        self.write_home_cfg({'feedback': {'url': 'https://home.example.com', 'key': 'sb_publishable_home'}})
        self.assertIsNotNone(feedback.config(env={}, home=self.home))
        for blank in ('', '   '):
            self.assertIsNone(feedback.config(env={'DEAI_FEEDBACK_URL': blank, 'DEAI_FEEDBACK_KEY': ''}, home=self.home))
            self.assertIsNone(feedback.config(env={'DEAI_FEEDBACK_URL': blank}, home=self.home))
        # лише порожній ключ без адреси — як раніше «не задано»: ланцюг іде далі
        self.assertEqual(feedback.config(env={'DEAI_FEEDBACK_KEY': ''}, home=self.home)['url'], 'https://home.example.com')

    def test_pair_is_never_mixed_across_sources(self):
        """Ключ одного джерела не їде на адресу іншого: частково заданий env → `None`, а не URL з env + ключ із файла."""
        self.write_shipped('https://shipped.example.com', 'sb_publishable_shipped')
        self.assertIsNone(feedback.config(env={'DEAI_FEEDBACK_URL': 'https://env.example.com'}, home=self.home))
        self.assertIsNone(feedback.config(env={'DEAI_FEEDBACK_KEY': 'sb_publishable_env'}, home=self.home))

    def test_empty_config_means_local_queue_only(self):
        self.assertIsNone(feedback.config(env={}, home=self.home))
        with mock.patch.object(feedback, 'SupabaseSender', side_effect=AssertionError('мережі не було б')):
            out = feedback.submit(clean(), {'version': '0.23.0'})
        self.assertEqual((out['state'], out['reason']), ('queued', 'no-collector'))
        self.assertEqual(len(self.box()), 1)

    def test_only_https_or_isolated_loopback(self):
        for bad in ('http://example.com', 'ftp://example.com', 'javascript:alert(1)', 'file:///etc/passwd', 'https://', 'https://u:p@example.com',
                    'https://example.com?x=1', 'https://example.com#x', 'https://exa mple.com', 'http://127.0.0.1:1', 'http://localhost:1', '', None, 5):
            self.assertIsNone(feedback.net_allowed(bad), bad)
        self.assertEqual(feedback.net_allowed('https://sb.example.com/'), 'https://sb.example.com')
        self.assertEqual(feedback.net_allowed('https://sb.example.com:8443/api'), 'https://sb.example.com:8443/api')
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            self.assertEqual(feedback.net_allowed('http://127.0.0.1:5555'), 'http://127.0.0.1:5555')
            self.assertEqual(feedback.net_allowed('http://localhost:5555'), 'http://localhost:5555')
            self.assertEqual(feedback.net_allowed('http://[::1]:5555'), 'http://[::1]:5555')
            self.assertIsNone(feedback.net_allowed('http://example.com'))
            self.assertIsNone(feedback.net_allowed('http://127.0.0.1.evil.example:80'))

    def test_unreadable_or_invalid_home_config_ignored(self):
        self.write_shipped('https://shipped.example.com', 'sb_publishable_shipped')
        for data in ('{broken', '[]', '"x"', {'feedback': 5}, {'feedback': []}, {'other': 1}):
            self.write_home_cfg(data)
            self.assertEqual(feedback.config(env={}, home=self.home), {'url': 'https://shipped.example.com', 'key': 'sb_publishable_shipped'}, data)
        self.write_home_cfg({'feedback': {'url': 'http://example.com', 'key': 'sb_publishable_x'}})
        self.assertIsNone(feedback.config(env={}, home=self.home), 'задане, але невалідне — не мовчазний перехід до нижчого джерела')

    def test_secret_keys_are_refused(self):
        self.assertFalse(feedback.key_ok('sb_secret_abcdefghijklmnop'))
        import base64
        jwt = 'eyJhbGciOiJIUzI1NiJ9.' + base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip('=') + '.sig'
        self.assertFalse(feedback.key_ok(jwt))
        anon = 'eyJhbGciOiJIUzI1NiJ9.' + base64.urlsafe_b64encode(b'{"role":"anon"}').decode().rstrip('=') + '.sig'
        self.assertTrue(feedback.key_ok(anon))
        self.assertTrue(feedback.key_ok('sb_publishable_abc'))
        for bad in ('', None, 'a b', 'a\nb', 'x' * 2000, 5):
            self.assertFalse(feedback.key_ok(bad), bad)
        self.assertIsNone(feedback.config(env={'DEAI_FEEDBACK_URL': URL, 'DEAI_FEEDBACK_KEY': 'sb_secret_abcdefghijklmnop'}, home=self.home))

    def test_shipped_feedback_json_is_safe(self):
        """Файл, що їде в релізі: лише `url`/`key`; url порожній АБО `https://<проєкт>.supabase.co`; ключ порожній АБО публікований (`sb_publishable_…` чи
        JWT `role=anon`). `sb_secret_…`/`service_role` у релізі — падіння."""
        import base64
        with open(os.path.join(APP, 'feedback.json'), encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(sorted(data), ['key', 'url'])
        url, key = data['url'], data['key']
        self.assertTrue(url == '' or re.match(r'^https://[a-z0-9]{8,40}\.supabase\.co/?$', url), 'у релізі лише адреса проєкту Supabase')
        if key:
            if key.startswith('eyJ'):
                seg = key.split('.')[1]
                self.assertEqual(json.loads(base64.urlsafe_b64decode(seg + '=' * (-len(seg) % 4))).get('role'), 'anon')
            else:
                self.assertTrue(key.startswith('sb_publishable_'), 'ключ у релізі — лише публікований')
            self.assertNotIn('service_role', key)
            self.assertNotIn('sb_secret_', key)


class Outbox(Base):
    def test_record_is_written_before_any_network(self):
        self.configure()
        op = FakeOpener(default=503)
        out = feedback.submit(clean(contact='a@example.com'), {'version': '0.23.0', 'os': {}}, sender=self.sender(op))
        self.assertEqual((out['state'], out['reason']), ('queued', 'offline'))
        fn = out['id'] + '.json'
        self.assertEqual(self.box(), [fn])
        path = os.path.join(self.home, 'feedback', 'outbox', fn)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        for d in ('feedback', 'feedback/outbox', 'feedback/sent', 'feedback/failed'):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.home, d)).st_mode), 0o700, d)
        with open(path, encoding='utf-8') as f:
            rec = json.load(f)
        self.assertEqual(sorted(rec), sorted(['id', 'created_at', 'kind', 'text', 'contact', 'version', 'os', 'diag', 'shot_path', 'attempts', 'last_error']))
        self.assertEqual((rec['kind'], rec['contact'], rec['attempts'], rec['last_error']), ('bug', 'a@example.com', 0, 'http-503'))        # мережа лежить — спробу не рахуємо
        self.assertTrue(re.match(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$', rec['created_at']))

    def test_shot_bytes_file_is_private_too(self):
        self.configure()
        out = feedback.submit(clean(), {}, shot=(WEBP, 'webp'), sender=self.sender(FakeOpener(default=503)))
        p = os.path.join(self.home, 'feedback', 'outbox', out['id'] + '.webp')
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    def test_offline_then_sent_moves_to_sent(self):
        self.configure()
        op = FakeOpener(script=[503])
        first = feedback.submit(clean(), {}, sender=self.sender(op))
        self.assertEqual(first['state'], 'queued')
        sent = self.ob.flush(self.sender(op))
        self.assertEqual(sent, {first['id']})
        self.assertEqual((self.box('outbox'), self.box('sent')), ([], [first['id'] + '.json']))

    def test_submit_tries_only_its_own_record_the_backlog_is_the_background_jobs(self):
        self.configure()
        a = feedback.submit(clean(), {}, sender=self.sender(FakeOpener(default=503)))
        op = FakeOpener(default=201)
        b = feedback.submit(clean(), {}, sender=self.sender(op))
        self.assertEqual(b['state'], 'sent')
        self.assertEqual(len(op.calls), 1, 'запит торкнувся лише свого запису')
        self.assertEqual((self.box('outbox'), self.box('sent')), ([a['id'] + '.json'], [b['id'] + '.json']))
        self.assertEqual(self.ob.flush(self.sender(FakeOpener(default=201))), {a['id']})       # фоновий прохід бере хвіст

    def _rec(self, **kw):
        return dict({'id': str(uuid.uuid4()), 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'kind': 'bug',
                     'text': 'Дуже важливий текст відгуку', 'contact': None, 'version': '0.23.0', 'os': 'x', 'diag': {}, 'shot_path': None,
                     'attempts': 0, 'last_error': ''}, **kw)

    def _attempts(self, rid, bucket='outbox'):
        with open(os.path.join(self.home, 'feedback', bucket, rid + '.json'), encoding='utf-8') as f:
            return json.load(f)['attempts']

    def test_transient_failures_never_count_toward_the_attempt_cap(self):
        r = self._rec()
        self.ob.add(r)
        for _ in range(25):
            self.ob.flush(self.sender(FakeOpener(default=503)))
        self.assertEqual((self.box('outbox'), self.box('failed')), ([r['id'] + '.json'], []))
        self.assertEqual(self._attempts(r['id']), 0)
        self.assertEqual(self.ob.flush(self.sender(FakeOpener(default=201))), {r['id']})       # мережа повернулась — іде

    def test_only_permanent_failures_count_and_cap_at_20_then_failed(self):
        r = self._rec()
        self.ob.add(r)
        for n in range(20):
            self.ob.flush(self.sender(FakeOpener(default=400)))
            self.assertEqual(self._attempts(r['id']), n + 1)
        op = FakeOpener()
        self.ob.flush(self.sender(op))
        self.assertEqual((op.calls, self.box('outbox'), self.box('failed')), ([], [], [r['id'] + '.json']))

    def test_expiry_is_by_age_only_even_with_zero_attempts(self):
        old = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 31 * 24 * 3600))
        young = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 29 * 24 * 3600))
        a, b = self._rec(created_at=old), self._rec(created_at=young)
        self.ob.add(a)
        self.ob.add(b)
        self.ob.flush(self.sender(FakeOpener(default=503)))
        self.assertEqual((self.box('failed'), self.box('outbox')), ([a['id'] + '.json'], [b['id'] + '.json']))

    def test_state_is_sent_even_when_moving_to_sent_fails(self):
        r = self._rec()
        self.ob.add(r)
        op = FakeOpener()
        with mock.patch.object(feedback.Outbox, 'move', side_effect=OSError('disk full')):
            self.assertEqual(self.ob.flush(self.sender(op)), {r['id']})
        self.assertEqual(self.ob.state_of(r['id']), 'sent', 'успіх записано першим')
        self.assertEqual(self.box('outbox'), [r['id'] + '.json'], 'файл лишився в outbox')
        self.assertEqual(self.ob.pending(), [], 'уже надісланий запис не повторюємо')
        self.ob.flush(self.sender(op))
        self.assertEqual(len(op.calls), 1)

    def test_lone_surrogates_and_nul_never_raise_and_one_bad_record_never_blocks_the_queue(self):
        bad = self._rec(text='abc \ud800 def', contact='a\x00b')
        good = self._rec(created_at='2999-01-01T00:00:00Z')
        self.assertTrue(self.ob.add(bad))
        self.assertTrue(self.ob.add(good))
        with open(os.path.join(self.home, 'feedback', 'outbox', bad['id'] + '.json'), 'rb') as f:
            rec = json.loads(f.read().decode('utf-8'))
        self.assertEqual((rec['text'], rec['contact']), ('abc ? def', 'ab'))
        self.assertEqual(feedback.validate({'kind': 'bug', 'text': 'abc \ud800 def x', 'contact': 'a\x00b'})[0]['text'], 'abc ? def x')
        self.assertEqual(feedback.validate({'kind': 'bug', 'text': 'a\x00b' * 5})[0]['text'], 'ab' * 5)
        # неочікуваний виняток на записі: Permanent, решта черги йде
        class Boom(feedback.SupabaseSender):
            def send_row(self, row):
                if row['id'] == bad['id']:
                    raise UnicodeEncodeError('utf-8', 'x', 0, 1, 'boom')
                super().send_row(row)
        self.assertEqual(self.ob.flush(Boom(URL, KEY, opener=FakeOpener())), {good['id']})
        self.assertEqual(self._attempts(bad['id']), 1)
        # і справжній send_row на самотньому сурогаті не кидає
        feedback.SupabaseSender(URL, KEY, opener=FakeOpener()).send_row(dict(bad, text='abc \ud800'))

    def test_add_removes_the_shot_when_the_json_write_fails(self):
        r = self._rec()
        with mock.patch.object(feedback.Outbox, '_write_json', side_effect=OSError('no space')):
            self.assertFalse(self.ob.add(r, shot=(WEBP, 'webp')))
        self.assertEqual([n for n in self.box() if not n.endswith('.json')], [], 'файл знімка-сирота прибрано')
        self.assertEqual(self.ob.shot_of(r['id']), (WEBP, 'webp'), 'а в памʼяті запис живий')

    def test_transient_failure_stops_the_pass_after_one_request(self):
        self.configure()
        for _ in range(3):
            feedback.submit(clean(), {}, sender=self.sender(FakeOpener(default=503)))
        op = FakeOpener(default=503)
        feedback.submit(clean(), {}, sender=self.sender(op))
        self.assertEqual(len(op.calls), 1, 'мережа лежить — решта черги не штурмується')

    def test_duplicate_409_counts_as_sent(self):
        self.configure()
        out = feedback.submit(clean(), {}, sender=self.sender(FakeOpener(script=[(409, b'{"code":"23505"}')])))
        self.assertEqual(out['state'], 'sent')
        self.assertEqual(self.box('sent'), [out['id'] + '.json'])

    def test_permanent_rejection_stays_queued_with_reason_and_counts_attempts(self):
        self.configure()
        out = feedback.submit(clean(), {}, sender=self.sender(FakeOpener(default=401)))
        self.assertEqual((out['state'], out['reason']), ('queued', 'rejected'))
        with open(os.path.join(self.home, 'feedback', 'outbox', out['id'] + '.json'), encoding='utf-8') as f:
            rec = json.load(f)
        self.assertEqual((rec['attempts'], rec['last_error']), (1, 'http-401'))

    def test_request_shape(self):
        self.configure()
        op = FakeOpener()
        out = feedback.submit(clean(kind='idea', contact='c@example.com'), {'version': '0.23.0', 'os': {'system': 'X'}, 'errors': {}}, sender=self.sender(op))
        self.assertEqual(out['state'], 'sent')
        self.assertEqual(len(op.calls), 1)
        c = op.calls[0]
        self.assertEqual(c['url'], URL + '/rest/v1/feedback')
        h = c['headers']
        self.assertEqual((h['apikey'], h['authorization'], h['content-type'], h['prefer']), (KEY, 'Bearer ' + KEY, 'application/json', 'return=minimal'))
        self.assertEqual(c['timeout'], 10)
        body = json.loads(c['body'])
        self.assertEqual(sorted(body), sorted(feedback.ROW_COLUMNS))
        self.assertNotIn('created_at', body)
        self.assertEqual(str(uuid.UUID(body['id'], version=4)), body['id'])
        self.assertEqual((body['kind'], body['contact'], body['version'], body['shot_path']), ('idea', 'c@example.com', '0.23.0', None))
        self.assertEqual(body['diag'], {'version': '0.23.0', 'os': {'system': 'X'}, 'errors': {}})
        self.assertNotIn(KEY, c['body'].decode())

    def test_shot_goes_first_to_storage_then_row_has_shot_path(self):
        self.configure()
        op = FakeOpener()
        out = feedback.submit(clean(), {}, shot=(WEBP, 'webp'), sender=self.sender(op))
        self.assertEqual(out['state'], 'sent')
        self.assertEqual([c['url'] for c in op.calls], ['%s/storage/v1/object/feedback-shots/%s.webp' % (URL, out['id']), URL + '/rest/v1/feedback'])
        s = op.calls[0]
        self.assertEqual((s['headers']['content-type'], s['headers']['x-upsert'], s['body']), ('image/webp', 'false', WEBP))
        self.assertEqual(json.loads(op.calls[1]['body'])['shot_path'], out['id'] + '.webp')
        self.assertEqual(self.box('outbox'), [], 'байти скриншота після відправки не лежать у черзі')

    def test_shot_409_is_ok_shot_4xx_drops_shot_but_sends_row(self):
        self.configure()
        op = FakeOpener(script=[409, 201])
        out = feedback.submit(clean(), {}, shot=(WEBP, 'webp'), sender=self.sender(op))
        self.assertEqual(json.loads(op.calls[1]['body'])['shot_path'], out['id'] + '.webp')
        op = FakeOpener(script=[413, 201])
        out = feedback.submit(clean(), {}, shot=(WEBP, 'webp'), sender=self.sender(op))
        self.assertEqual(out['state'], 'sent')
        self.assertIsNone(json.loads(op.calls[1]['body'])['shot_path'])
        op = FakeOpener(script=[(400, b'{"error":"Duplicate"}'), 201])
        out = feedback.submit(clean(), {}, shot=(WEBP, 'webp'), sender=self.sender(op))
        self.assertEqual(json.loads(op.calls[1]['body'])['shot_path'], out['id'] + '.webp')

    def test_shot_transient_failure_keeps_everything_queued(self):
        self.configure()
        out = feedback.submit(clean(), {}, shot=(WEBP, 'webp'), sender=self.sender(FakeOpener(script=[503])))
        self.assertEqual(out['state'], 'queued')
        self.assertEqual(sorted(self.box()), sorted([out['id'] + '.json', out['id'] + '.webp']))
        op = FakeOpener()
        self.ob.flush(self.sender(op))
        self.assertEqual(len(op.calls), 2)

    def test_shot_over_2mb_never_sent_and_garbage_shot_dropped(self):
        self.configure()
        op = FakeOpener()
        big = WEBP + b'x' * feedback.SHOT_MAX_BYTES
        feedback.submit(clean(), {}, shot=(big, 'webp'), sender=self.sender(op))
        feedback.submit(clean(), {}, shot=(b'not an image at all', 'webp'), sender=self.sender(op))
        self.assertEqual([c['url'] for c in op.calls], [URL + '/rest/v1/feedback'] * 2)
        self.assertTrue(all(json.loads(c['body'])['shot_path'] is None for c in op.calls))

    def test_old_or_20_attempts_go_to_failed_not_deleted(self):
        self.configure()
        old = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 31 * 24 * 3600))
        mk = lambda **kw: dict({'id': str(uuid.uuid4()), 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'kind': 'bug',
                                'text': 'Дуже важливий текст відгуку', 'contact': None, 'version': '0.23.0', 'os': 'x', 'diag': {}, 'shot_path': None,
                                'attempts': 0, 'last_error': ''}, **kw)
        r_old, r_many, r_ok = mk(created_at=old), mk(attempts=20), mk()
        for r in (r_old, r_many, r_ok):
            self.ob.add(r)
        op = FakeOpener()
        self.ob.flush(self.sender(op))
        self.assertEqual(len(op.calls), 1, 'на мережу пішов лише живий запис')
        self.assertEqual(sorted(self.box('failed')), sorted([r_old['id'] + '.json', r_many['id'] + '.json']))
        with open(os.path.join(self.home, 'feedback', 'failed', r_old['id'] + '.json'), encoding='utf-8') as f:
            kept = json.load(f)
        self.assertEqual(kept['text'], 'Дуже важливий текст відгуку', 'файл ЦІЛИЙ: текст не загублено')
        self.assertEqual(self.box('sent'), [r_ok['id'] + '.json'])

    def test_validation(self):
        v = feedback.validate
        ok, bad = v({'kind': 'bug', 'text': '  Достатньо довгий текст  ', 'contact': '  me@example.com ', 'include_diag': False})
        self.assertIsNone(bad)
        self.assertEqual((ok['text'], ok['contact'], ok['include_diag'], ok['include_shot']), ('Достатньо довгий текст', 'me@example.com', False, False))
        cases = ({'kind': 'oops', 'text': 'x' * 20}, {'kind': 'bug', 'text': 'x' * 9}, {'kind': 'bug', 'text': ' ' * 30}, {'kind': 'bug', 'text': 5},
                 {'kind': 'bug', 'text': 'x' * 10001}, {'kind': 'bug', 'text': 'x' * 20, 'contact': 'c' * 201}, {'kind': 'bug', 'text': 'x' * 20, 'contact': 5},
                 {'kind': 'bug', 'text': 'x' * 20, 'include_diag': 'yes'}, {'kind': 'bug', 'text': 'x' * 20, 'include_shot': 1}, {})
        for body in cases:
            self.assertIsNone(v(body)[0], body)
            self.assertIsNotNone(v(body)[1], body)
        self.assertEqual(v({'kind': 'idea', 'text': 'x' * 10})[1], None)
        self.assertEqual(v({'kind': 'idea', 'text': 'x' * 10000})[1], None)
        self.assertEqual(v({'kind': 'idea', 'text': 'x' * 10, 'contact': 'c' * 200})[1], None)

    def test_concurrent_flush_sends_each_once(self):
        self.configure()
        rec = {'id': str(uuid.uuid4()), 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'kind': 'bug', 'text': 'Текст відгуку для гонки',
               'contact': None, 'version': '0.23.0', 'os': 'x', 'diag': {}, 'shot_path': None, 'attempts': 0, 'last_error': ''}
        self.ob.add(rec)
        rx = FakeReceiver()
        self.addCleanup(rx.close)
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            sender = feedback.SupabaseSender(rx.url, KEY)
            ts = [threading.Thread(target=lambda: self.ob.flush(sender)) for _ in range(4)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(len([r for r in rx.requests if r['path'] == '/rest/v1/feedback']), 1)
        self.assertEqual(self.box('sent'), [rec['id'] + '.json'])

    def test_real_loopback_receiver_roundtrip(self):
        rx = FakeReceiver()
        self.addCleanup(rx.close)
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json'), 'DEAI_FEEDBACK_URL': rx.url, 'DEAI_FEEDBACK_KEY': KEY}):
            out = feedback.submit(clean(), {'version': '0.23.0'}, shot=(WEBP, 'webp'))
        self.assertEqual(out['state'], 'sent')
        self.assertEqual(rx.rows()[0]['id'], out['id'])
        self.assertEqual(rx.shots(), {out['id'] + '.webp': WEBP})
        self.assertEqual(rx.requests[0]['headers']['apikey'], KEY)

    def test_no_writes_in_real_home_when_isolated(self):
        self.configure()
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}), mock.patch.object(isolation, 'real_home', return_value=True):
            out = feedback.submit(clean(), {}, shot=(WEBP, 'webp'), sender=self.sender(FakeOpener(default=503)))
            self.assertEqual((out['state'], out.get('memory_only')), ('queued', True))
            self.assertFalse(os.path.exists(os.path.join(self.home, 'feedback')))
            self.assertEqual(len(self.ob.pending()), 1)
            self.assertEqual(self.ob.shot_of(out['id'])[0], WEBP)

    def test_network_refused_for_non_loopback_when_isolated(self):
        self.configure()
        op = FakeOpener()
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            out = feedback.submit(clean(), {}, sender=self.sender(op))
        self.assertEqual((out['state'], out['reason']), ('queued', 'network-blocked'))
        self.assertEqual(op.calls, [])
        self.assertEqual(len(self.box()), 1)

    def test_flush_pending_is_a_noop_without_config_or_when_isolated_non_loopback(self):
        self.assertEqual(feedback.flush_pending(), 0)
        self.configure()
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}), \
                mock.patch.object(feedback, 'SupabaseSender', side_effect=AssertionError('мережі не було б')):
            self.assertEqual(feedback.flush_pending(), 0)

    def test_background_thread_not_started_without_config_or_when_disabled_or_isolated(self):
        self.assertIsNone(feedback.start_background())
        self.configure()
        with mock.patch.dict(os.environ, {'DEAI_NO_UPDATE_CHECK': '1'}):
            self.assertIsNone(feedback.start_background())
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            self.assertIsNone(feedback.start_background())
        stop = threading.Event()
        t = feedback.start_background(first_delay=3600, stop=stop)
        try:
            self.assertTrue(t.daemon)
            self.assertEqual(t.name, 'deai-feedback-flush')
        finally:
            stop.set()
            t.join(2)

    def test_key_and_url_never_in_exception_text_or_state(self):
        self.configure()
        boom = urllib.error.URLError('cannot reach %s with key %s' % (URL, KEY))
        for script in ([boom], [OSError('x ' + URL + KEY)], [401], [503]):
            op = FakeOpener(script=script)
            s = self.sender(op)
            with self.assertRaises((feedback.Transient, feedback.Permanent)) as cm:
                s.send_row({'id': str(uuid.uuid4()), 'kind': 'bug', 'text': 'x'})
            for needle in (URL, KEY, 'sb.example.com'):
                self.assertNotIn(needle, str(cm.exception))
                self.assertNotIn(needle, repr(cm.exception))
            self.assertIsNone(cm.exception.__cause__)
        self.assertNotIn(KEY, repr(self.sender(FakeOpener())))
        out = feedback.submit(clean(), {}, sender=self.sender(FakeOpener(default=503)))
        with open(os.path.join(self.home, 'feedback', 'outbox', out['id'] + '.json'), encoding='utf-8') as f:
            raw = f.read()
        for needle in (URL, KEY, 'sb.example.com'):
            self.assertNotIn(needle, raw)

    def test_redirects_are_not_followed(self):
        """Відповідь-перенаправлення не веде ключ на чужу адресу: `Permanent('redirect')`."""
        s = self.sender(FakeOpener(script=[301]))
        with self.assertRaises(feedback.Permanent) as cm:
            s.send_row({'id': 'x'})
        self.assertEqual(str(cm.exception), 'redirect')
        h = feedback._NoRedirect()
        self.assertIsNone(h.redirect_request(None, None, 302, 'x', {}, 'https://evil.example/'))



class Tls(unittest.TestCase):
    """0.23.2: Python з python.org на macOS не бачить системного сховища сертифікатів — без certifi HTTPS до приймача падав
    `CERTIFICATE_VERIFY_FAILED`, відгук назавжди лишався в `outbox` як `network`. Відправник бере контекст certifi, як інші модулі."""

    def _https_context(self, url):
        handlers = feedback._default_opener(url).__self__.handlers
        https = [h for h in handlers if isinstance(h, urllib.request.HTTPSHandler)]
        self.assertEqual(len(https), 1, 'рівно один HTTPSHandler')
        return https[0]._context

    def test_the_sender_uses_the_certifi_store_when_present(self):
        fake = type(sys)('certifi')
        fake.where = lambda: '/fake/cacert.pem'
        seen = []
        sentinel = object()

        def ctx(**kw):
            seen.append(kw)
            return sentinel
        with mock.patch.dict(sys.modules, {'certifi': fake}), mock.patch.object(feedback.ssl, 'create_default_context', ctx):
            got = self._https_context('https://abc.supabase.co')
        self.assertIs(got, sentinel)
        self.assertEqual(seen, [{'cafile': '/fake/cacert.pem'}])

    def test_without_certifi_the_default_context(self):
        seen = []
        sentinel = object()

        def ctx(**kw):
            seen.append(kw)
            return sentinel
        with mock.patch.dict(sys.modules, {'certifi': None}), mock.patch.object(feedback.ssl, 'create_default_context', ctx):
            got = self._https_context('https://abc.supabase.co')
        self.assertIs(got, sentinel)
        self.assertEqual(seen, [{}])


if __name__ == '__main__':
    unittest.main()
