"""`GET /api/setup` (0.33.0): версія, шляхи установки й стан знімків «Огляду» (`shots`). Node підміняє `DEAI_SHOTS_NODE` —
скрипт у тимчасовій теці друкує те, що надрукував би справжній `node -e`."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
sys.path.insert(0, HERE)
import serve  # noqa: E402
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class SetupApi(base.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['DEAI_NO_UPDATE_CHECK'] = '1'
        cls.addClassCleanup(os.environ.pop, 'DEAI_NO_UPDATE_CHECK', None)

    def setUp(self):
        super().setUp()
        serve._SETUP_CACHE.clear()
        self.addCleanup(serve._SETUP_CACHE.clear)
        self.dir = tempfile.mkdtemp(prefix='fake-node-')
        self.addCleanup(shutil.rmtree, self.dir, True)

    def node(self, body):
        """Підроблений `node`: кожен виклик дописує рядок у `calls`, далі — `body` (shell)."""
        p = os.path.join(self.dir, 'node')
        with open(p, 'w') as f:
            f.write(f'#!/bin/sh\necho x >> "{self.dir}/calls"\n{body}\n')
        os.chmod(p, 0o755)
        return p

    def calls(self):
        try:
            with open(os.path.join(self.dir, 'calls')) as f:
                return len(f.read().split())
        except FileNotFoundError:
            return 0

    def shots(self, node, path='/api/setup'):
        with mock.patch.dict(os.environ, {'DEAI_SHOTS_NODE': node}):
            st, body = self.jget(path)
        self.assertEqual(st, 200)
        return body

    def test_shape_paths_and_version(self):
        body = self.shots(self.node("printf '%s' '{\"v\":\"22.1.0\",\"pw\":true,\"browser\":true}'"))
        self.assertTrue(body['ok'])
        self.assertEqual(body['paths'], {'deai': serve.ROOT, 'setup': os.path.join(serve.ROOT, 'SETUP.md')})
        self.assertEqual(body['version'], self.jget('/api/update')[1]['current'])
        self.assertRegex(body['python'], r'^\d+\.\d+\.\d+$')
        self.assertEqual(body['platform'], sys.platform)
        self.assertEqual(body['shots'], {'state': 'ok', 'node': '22.1.0', 'command': None})

    def test_every_shots_state(self):
        cases = {
            'no-browser': "printf '%s' '{\"v\":\"22.1.0\",\"pw\":true,\"browser\":false}'",
            'no-playwright': "printf '%s' '{\"v\":\"20.3.0\",\"pw\":false,\"browser\":false}'",
            'unknown': 'echo not-json; exit 1',
        }
        for want, body in cases.items():
            with self.subTest(state=want):
                serve._SETUP_CACHE.clear()
                got = self.shots(self.node(body))['shots']
                self.assertEqual(got['state'], want)
                if want == 'unknown':
                    self.assertEqual(got['command'], None)
                else:
                    self.assertIn('npx playwright install chromium', got['command'])
                    self.assertIn('npm install', got['command'])
        self.assertEqual(self.shots('/nonexistent/node')['shots'], {'state': 'no-node', 'node': None, 'command': None})
        self.assertEqual(self.shots('relative/node')['shots']['state'], 'no-node')

    def test_cache_and_fresh(self):
        node = self.node("printf '%s' '{\"v\":\"22.1.0\",\"pw\":true,\"browser\":false}'")
        self.shots(node)
        self.shots(node)
        self.assertEqual(self.calls(), 1, 'другий запит у межах 30 с — з кешу')
        self.shots(node, '/api/setup?fresh=1')
        self.assertEqual(self.calls(), 2, '`fresh=1` обходить кеш')

    def test_timeout_gives_unknown(self):
        with mock.patch.object(serve, '_SETUP_TIMEOUT', 0.5):
            got = self.shots(self.node('sleep 5'))['shots']
        self.assertEqual(got['state'], 'unknown')

    def test_foreign_page_cannot_run_node(self):
        node = self.node("printf '%s' '{}'")
        for headers in ({'Origin': 'http://example.com'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers), mock.patch.dict(os.environ, {'DEAI_SHOTS_NODE': node}):
                st, body = self.jget('/api/setup', headers=headers)
                self.assertEqual((st, body['ok']), (403, False))
        self.assertEqual(self.calls(), 0)


class ShootFailure(unittest.TestCase):
    """Playwright без завантаженого Chromium падає з «Executable doesn't exist» — `/api/shoot` каже `no-browser` і команду."""

    DUMP = ("browserType.launch: Executable doesn't exist at /x/ms-playwright/chromium-1/chrome\n"
            "Looks like Playwright was just installed or updated.")

    def test_stderr_or_raw_report_gives_no_browser(self):
        for err, report in ((self.DUMP, {}), ('', {'raw': self.DUMP}), (self.DUMP, None)):
            with self.subTest(err=bool(err)):
                self.assertEqual(serve.shoot_failure(err, report), {'code': 'no-browser', 'command': serve.shots_command()})

    def test_other_failures_stay_as_they_are(self):
        self.assertIsNone(serve.shoot_failure('Error: page crashed', {'failed': [{'id': 'p', 'problem': 'x'}]}))
        self.assertIsNone(serve.shoot_failure('', {}))

    def test_the_shoot_route_uses_it(self):
        import inspect
        src = inspect.getsource(serve)
        self.assertIn('shoot_failure(err, report)', src)


if __name__ == '__main__':
    unittest.main()
