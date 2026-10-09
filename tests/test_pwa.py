"""Канвас як застосунок (PWA «Deai Canvas», P1): що віддає СЕРВЕР.

Юніти `tests/pwa.test.mjs` перевіряють вміст маніфесту й значків, живий
`tests/live/pwa.test.mjs` — що Chrome вважає це встановлюваним. Тут — те, що
лежить між ними й ловиться лише на справжньому HTTP:

  · маніфест віддається з `application/manifest+json` (на старих Python
    `.webmanifest` у таблиці MIME нема, і без явного запису він ішов би як
    `application/octet-stream`);
  · `sw.js` — JavaScript і `Cache-Control: no-cache`: інакше оновлення worker
    доїжджало б із запізненням, а worker — єдине місце, де застарілий код
    ламає ВСІ вкладки одразу;
  · значки — `image/png`;
  · оболонка опублікованих превʼю маніфесту й worker НЕ отримує.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
import serve  # noqa: E402


class PwaServing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Конфіг задач — тимчасовий, як у решти класів цього пакета: статика
        # його не читає, але сервер без явного шляху потягнувся б до живого.
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-pwa-cfg-')
        os.environ['DC_TASKS_FILE'] = os.path.join(cls.cfgdir, 'tasks.json')
        os.environ['DC_NO_OVERVIEW'] = '1'
        with open(os.environ['DC_TASKS_FILE'], 'w') as f:
            json.dump({'current': None, 'tasks': {}}, f)
        cls.httpd = serve.make_server(0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        shutil.rmtree(cls.cfgdir, ignore_errors=True)

    def _get(self, path):
        return urllib.request.urlopen(self.base + path)

    def test_manifest_is_served_as_manifest_json(self):
        r = self._get('/app/manifest.webmanifest')
        self.assertEqual(r.status, 200)
        self.assertEqual(r.headers['Content-Type'].split(';')[0], 'application/manifest+json')
        m = json.load(r)
        self.assertEqual(m['scope'], '/app/')

    def test_manifest_mime_does_not_depend_on_the_python_mimetypes_table(self):
        """Явний запис у `extensions_map`, а не везіння версії Python: на
        системному python3 macOS `.webmanifest` у таблиці `mimetypes` може не
        бути, і без запису Chrome отримав би `application/octet-stream`."""
        self.assertEqual(serve.Handler.extensions_map.get('.webmanifest'),
                         'application/manifest+json')

    def test_service_worker_is_javascript_and_never_cached(self):
        r = self._get('/app/sw.js')
        self.assertEqual(r.status, 200)
        self.assertIn('javascript', r.headers['Content-Type'])
        self.assertIn('no-cache', r.headers['Cache-Control'])
        self.assertIn(b'addEventListener', r.read())

    def test_icons_are_png(self):
        for name in ('icon-192.png', 'icon-512.png', 'icon-maskable-512.png'):
            r = self._get(f'/app/pwa/{name}')
            self.assertEqual(r.status, 200, name)
            self.assertEqual(r.headers['Content-Type'], 'image/png', name)
            self.assertEqual(r.read(8), b'\x89PNG\r\n\x1a\n', name)

    def test_local_tool_page_links_the_manifest(self):
        html = self._get('/app/').read().decode('utf-8')
        self.assertIn('<link rel="manifest" href="manifest.webmanifest">', html)
        # Заголовок встановленого вікна = імʼя застосунку з маніфесту.
        self.assertIn('<title>Deai Canvas</title>', html)


class PreviewHasNoPwa(unittest.TestCase):
    """Оболонка опублікованих превʼю — інший продукт, для рецензентів: вона не
    встановлюється й не реєструє worker. Маніфест — лише в локальному
    `app/index.html`."""

    FORBIDDEN = re.compile(
        r'manifest\.webmanifest|rel=["\']manifest["\']|serviceWorker|sw\.js'
        r'|beforeinstallprompt|appinstalled')

    def test_preview_wrapper_has_no_manifest_or_worker(self):
        html = serve.preview_index_html('<!--gate-->', '1100')
        self.assertIsNone(self.FORBIDDEN.search(html), self.FORBIDDEN.search(html))

    def test_page_template_has_no_manifest_or_worker(self):
        self.assertIsNone(self.FORBIDDEN.search(serve.PAGES_PREVIEW_PAGE))

    def test_shell_modules_know_nothing_about_pwa(self):
        for name in serve.SHELL_MODULES:
            with open(os.path.join(ROOT, 'app', name), encoding='utf-8') as fh:
                body = fh.read()
            self.assertIsNone(self.FORBIDDEN.search(body), f'{name} їде в превʼю, а згадує PWA')

    def test_pwa_files_are_not_in_the_shell_list(self):
        for own in ('pwa.js', 'pwa-offline.js', 'sw.js', 'manifest.webmanifest'):
            self.assertNotIn(own, serve.SHELL_MODULES)


if __name__ == '__main__':
    unittest.main()
