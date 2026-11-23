"""Повні знімки локальних пінів (0.35.1): `POST /api/local-shots` кладе JPEG у `<тека задачі>/.dc-local-shots/<id>.jpg`,
`GET /api/local-shots/<id>.jpg` його віддає; тека не їде в git макета (`TASK_IGNORE`). Живий сервер у тимчасовій теці, тимчасовий HOME."""
import base64
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve  # noqa: E402
from test_serve import league_stand  # noqa: E402

JPEG = b'\xff\xd8\xff\xe0' + b'\x00\x10JFIF\x00' + b'x' * 200 + b'\xff\xd9'


def data_url(raw=JPEG, mime='image/jpeg'):
    return f'data:{mime};base64,' + base64.b64encode(raw).decode()


class LocalShots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-cfg-')
        cls.tasks_file = os.path.join(cls.cfgdir, 'tasks.json')
        cls.dwroot = tempfile.mkdtemp(prefix='dc-dwroot-')
        league_stand(cls, cls.tasks_file, cls.dwroot)
        cls.tmp = tempfile.mkdtemp(prefix='dc-task-')
        cls.other = tempfile.mkdtemp(prefix='dc-task2-')
        os.makedirs(os.path.join(cls.tmp, 'iterations', 'it1'))
        with open(os.path.join(cls.tmp, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': '', 'published': False}],
                       'publish_url': None}, f)
        os.environ['DC_TASKS_FILE'] = cls.tasks_file
        os.environ['DC_NO_OVERVIEW'] = '1'
        with open(cls.tasks_file, 'w') as f:
            json.dump({'current': 'fixture', 'design_work_root': cls.dwroot,
                       'tasks': {'fixture': {'dir': cls.tmp, 'title': 'Фікстура'},
                                 'beta': {'dir': cls.other, 'title': 'Бета'}}}, f)
        cls.httpd = serve.make_server(0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.port}'
        cls.shots = os.path.join(cls.tmp, '.dc-local-shots')

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        for d in (cls.tmp, cls.other, cls.dwroot, cls.cfgdir):
            shutil.rmtree(d, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(self.shots, ignore_errors=True)

    def post(self, payload, path='/api/local-shots'):
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                return e.code, json.loads(body)
            except ValueError:
                return e.code, None

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def written(self):
        return sorted(os.listdir(self.shots)) if os.path.isdir(self.shots) else []

    # ---- POST ----

    def test_post_writes_file_and_returns_url(self):
        st, body = self.post({'id': 'c-1700000000-abc', 'dataUrl': data_url()})
        self.assertEqual(st, 200)
        self.assertEqual(body, {'ok': True, 'url': '/api/local-shots/c-1700000000-abc.jpg'})
        with open(os.path.join(self.shots, 'c-1700000000-abc.jpg'), 'rb') as f:
            self.assertEqual(f.read(), JPEG)
        self.assertEqual(self.written(), ['c-1700000000-abc.jpg'])          # без осиротілих tmp

    def test_post_uuid_id_and_overwrite(self):
        uid = '3f2b8c1e-5d4a-4b7e-9c11-0a1b2c3d4e5f'
        self.assertEqual(self.post({'id': uid, 'dataUrl': data_url()})[0], 200)
        newer = JPEG + b'more'
        self.assertEqual(self.post({'id': uid, 'dataUrl': data_url(newer)})[0], 200)
        with open(os.path.join(self.shots, uid + '.jpg'), 'rb') as f:
            self.assertEqual(f.read(), newer)

    def test_post_rejects_bad_input_and_writes_nothing(self):
        cases = {
            'id із шляхом': {'id': '../evil', 'dataUrl': data_url()},
            'id зі скісною': {'id': 'a/b', 'dataUrl': data_url()},
            'id з крапкою': {'id': 'a.b', 'dataUrl': data_url()},
            'id порожній': {'id': '', 'dataUrl': data_url()},
            'id не рядок': {'id': 5, 'dataUrl': data_url()},
            'id починається з дефіса': {'id': '-a', 'dataUrl': data_url()},
            'id задовгий': {'id': 'a' * 101, 'dataUrl': data_url()},
            'не jpeg (png)': {'id': 'x1', 'dataUrl': data_url(mime='image/png')},
            'не data-url': {'id': 'x1', 'dataUrl': 'https://example.test/a.jpg'},
            'без base64': {'id': 'x1', 'dataUrl': 'data:image/jpeg,abc'},
            'сміття base64': {'id': 'x1', 'dataUrl': 'data:image/jpeg;base64,@@@@'},
            'base64 із пробілами': {'id': 'x1', 'dataUrl': 'data:image/jpeg;base64,/9j/ 4AAQ'},
            'не JPEG-байти': {'id': 'x1', 'dataUrl': data_url(b'GIF89a-not-a-jpeg')},
            'порожнє тіло зображення': {'id': 'x1', 'dataUrl': 'data:image/jpeg;base64,'},
            'dataUrl не рядок': {'id': 'x1', 'dataUrl': 7},
            'без dataUrl': {'id': 'x1'},
        }
        for name, payload in cases.items():
            st, body = self.post(payload)
            self.assertIn(st, (400, 413), name)
            self.assertIsInstance(body, dict, name)
            self.assertFalse(body.get('ok'), name)
            self.assertTrue(body.get('error'), name)
        self.assertEqual(self.written(), [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'evil.jpg')))

    def test_post_decoded_size_limit(self):
        big = b'\xff\xd8\xff' + b'a' * (8 * 1024 * 1024)                 # 8 МіБ + 3 байти: декодоване понад стелю
        st, body = self.post({'id': 'big1', 'dataUrl': data_url(big)})
        self.assertEqual(st, 413)
        self.assertFalse(body['ok'])
        ok = b'\xff\xd8\xff' + b'a' * (1024 * 1024)
        self.assertEqual(self.post({'id': 'ok1', 'dataUrl': data_url(ok)})[0], 200)
        self.assertEqual(self.written(), ['ok1.jpg'])

    def test_post_oversized_body_is_refused_before_reading(self):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        c.putrequest('POST', '/api/local-shots')
        c.putheader('Content-Type', 'application/json')
        c.putheader('Content-Length', str(200 * 1024 * 1024))
        c.endheaders()                                                   # тіло не шлемо
        r = c.getresponse()
        self.assertEqual(r.status, 413)
        self.assertFalse(json.loads(r.read())['ok'])
        c.close()
        self.assertEqual(self.written(), [])

    def test_post_foreign_origin_is_refused(self):
        req = urllib.request.Request(self.base + '/api/local-shots', data=json.dumps({'id': 'a1', 'dataUrl': data_url()}).encode(),
                                     headers={'Content-Type': 'application/json', 'Origin': 'https://evil.example'}, method='POST')
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)
        self.assertEqual(self.written(), [])

    def test_named_task_override_writes_into_that_task(self):
        """Як `/api/local-comments`: префікс `/t/<id>/` вибирає задачу запиту."""
        st, body = self.post({'id': 'n1', 'dataUrl': data_url()}, path='/t/beta/api/local-shots')
        self.assertEqual(st, 200)
        self.assertTrue(os.path.isfile(os.path.join(self.other, '.dc-local-shots', 'n1.jpg')))
        self.assertEqual(self.written(), [])
        st, raw, _ = self.get('/t/beta/api/local-shots/n1.jpg')
        self.assertEqual((st, raw), (200, JPEG))
        self.assertEqual(self.get('/api/local-shots/n1.jpg')[0], 404)    # поточна задача цього файла не має

    # ---- GET ----

    def test_get_serves_bytes_with_headers(self):
        self.post({'id': 'g1', 'dataUrl': data_url()})
        st, raw, h = self.get('/api/local-shots/g1.jpg')
        self.assertEqual((st, raw), (200, JPEG))
        self.assertEqual(h['Content-Type'], 'image/jpeg')
        self.assertEqual(h['Cache-Control'], 'no-cache')
        self.assertEqual(h['X-Content-Type-Options'], 'nosniff')

    def test_get_missing_and_bad_ids(self):
        self.assertEqual(self.get('/api/local-shots/nope.jpg')[0], 404)
        for bad in ('/api/local-shots/..%2Fiterations.json', '/api/local-shots/a.b.jpg', '/api/local-shots/x.png',
                    '/api/local-shots/.jpg', '/api/local-shots/', '/api/local-shots/%2e%2e%2fx.jpg',
                    '/api/local-shots/' + 'a' * 101 + '.jpg'):
            st = self.get(bad)[0]
            self.assertIn(st, (400, 404), bad)

    def test_get_does_not_follow_a_symlink_out_of_the_folder(self):
        outside = os.path.join(self.cfgdir, 'secret.jpg')
        with open(outside, 'wb') as f:
            f.write(JPEG)
        os.makedirs(self.shots, exist_ok=True)
        os.symlink(outside, os.path.join(self.shots, 'link1.jpg'))
        self.assertEqual(self.get('/api/local-shots/link1.jpg')[0], 404)

    def test_post_does_not_write_through_a_symlinked_folder(self):
        target = tempfile.mkdtemp(prefix='dc-out-')
        try:
            os.symlink(target, self.shots)
            st, _ = self.post({'id': 'sl1', 'dataUrl': data_url()})
            self.assertIn(st, (400, 500))
            self.assertEqual(os.listdir(target), [])
        finally:
            os.unlink(self.shots)
            shutil.rmtree(target, ignore_errors=True)

    # ---- git ----

    def test_rule_is_in_task_ignore_and_topped_up(self):
        self.assertIn('.dc-local-shots/', serve.TASK_IGNORE)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, '.gitignore'), 'w', encoding='utf-8') as fh:
                fh.write('refs/\n*.bak\n')
            added = serve.ensure_task_gitignore(tmp)
            self.assertIn('.dc-local-shots/', added)
            with open(os.path.join(tmp, '.gitignore'), encoding='utf-8') as fh:
                self.assertEqual(fh.read().split().count('.dc-local-shots/'), 1)

    def test_shots_folder_does_not_land_in_the_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, '.dc-local-shots'))
            with open(os.path.join(tmp, '.dc-local-shots', 'a1.jpg'), 'wb') as fh:
                fh.write(JPEG)
            open(os.path.join(tmp, 'index.html'), 'w').close()
            serve.git_autocommit(tmp, 'тест')
            tracked = subprocess.run(['git', 'ls-files'], cwd=tmp, capture_output=True, text=True).stdout.split()
            self.assertIn('index.html', tracked)
            self.assertNotIn('.dc-local-shots/a1.jpg', tracked)

    def test_static_export_skips_the_folder(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            os.makedirs(os.path.join(src, '.dc-local-shots'))
            with open(os.path.join(src, '.dc-local-shots', 'a1.jpg'), 'wb') as fh:
                fh.write(JPEG)
            open(os.path.join(src, 'index.html'), 'w').close()
            serve.copy_mockup(src, dst)
            self.assertEqual(os.listdir(dst), ['index.html'])


if __name__ == '__main__':
    unittest.main()
