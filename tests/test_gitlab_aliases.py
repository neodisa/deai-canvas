"""Псевдоніми `/api/gitlab-*` (4d-4c, Р4): ті самі відповіді, що `vcs-*`, плюс `Deprecation` і `Link` на наступника."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
for _p in ('app', 'bin'):
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), _p))
import serve  # noqa: E402


class AliasDeprecation(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix='alias-')
        self.addCleanup(d.cleanup)
        tmp = os.path.realpath(d.name)
        tdir = os.path.join(tmp, 't1')
        os.makedirs(tdir)
        with open(os.path.join(tdir, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [], 'publish_url': None}, f)
        cfg = os.path.join(tmp, 'tasks.json')
        with open(cfg, 'w') as f:
            json.dump({'current': 't1', 'design_work_root': tmp, 'tasks': {'t1': {'dir': tdir, 'title': 'T'}}}, f)
        p = mock.patch.dict(os.environ, {'HOME': tmp, 'DC_TASKS_FILE': cfg})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('DEAI_HOME', None)
        q = mock.patch.object(serve.Handler, 'log_message', lambda *a, **k: None)
        q.start()
        self.addCleanup(q.stop)
        self.httpd = serve.make_server(0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))
        self.port = self.httpd.server_address[1]

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        h = {'Origin': 'http://127.0.0.1:%d' % self.port}
        if body is not None:
            h['Content-Type'] = 'application/json'
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        out = (r.status, r.getheader('Deprecation'), r.getheader('Link'), data)
        c.close()
        return out

    def test_aliases_carry_the_headers_and_the_same_answer(self):
        for method, old, new, body in (('GET', '/api/gitlab-status', '/api/vcs-status', None),
                                       ('POST', '/api/gitlab-sync', '/api/vcs-push', {'it': 'it1'}),
                                       ('POST', '/api/gitlab-pull', '/api/vcs-pull', {})):
            s1, dep, link, b1 = self.call(method, old, body)
            s2, dep2, link2, b2 = self.call(method, new, body)
            self.assertEqual((s1, b1), (s2, b2), old)
            self.assertEqual(dep, 'true', old)
            self.assertEqual(link, '<%s>; rel="successor-version"' % new, old)
            self.assertIsNone(dep2, new)
            self.assertIsNone(link2, new)

    def test_the_marker_is_reset_for_every_guarded_request(self):
        # Сервер говорить HTTP/1.0 (зʼєднання не живе довше за запит), тож скидання — захист на випадок keep-alive;
        # перевіряється прямо на обробнику, якому лишився маркер попереднього запиту.
        h = object.__new__(serve.Handler)
        h._successor = '/api/vcs-push'
        h._guarded(lambda: None)
        self.assertIsNone(h._successor)


if __name__ == '__main__':
    unittest.main()
