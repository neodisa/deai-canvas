"""Роздача панелі інструмента модуля й набору панелі (M1, Task 3): `GET /api/module-ui/<простір>/<модуль>/<шлях>` і
`GET /api/module-ui-kit/<імʼя>`.

Що доводиться:
  * панель (html) віддається з набором (`KIT_TAGS` одразу після doctype чи на початку, BOM лишається першим), ресурси — з
    правильними типами; на КОЖНІЙ відповіді (200, 304) захисні заголовки `MODULE_UI_HEADERS`, і CSP закріплено дослівно;
  * шлях: лише тека панелі якогось інструмента й лише дозволені розширення; `..`, `%2f`, `%5c`, `%00`, порожня складова,
    >6 складових, посилання (тека, файл), жорстке посилання — той самий сталий 404;
  * модуль: лише справний, api 2, явно увімкнений, з інструментами, у ТОМУ Ж просторі; свій — зі знімка довіри;
  * набір: рівно `kit.css` і `bridge.js`.

⛔ Ізоляція: тимчасові `HOME`/`DEAI_HOME` (`OwnEnv`); сокет — лише до власного сервера тесту.
"""
import http.client
import json
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deai_modules as dm  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_modules_own as tmo  # noqa: E402
from test_modules import _write, _read  # noqa: E402

_REAL = None

CSP = ("sandbox allow-scripts allow-forms; default-src 'self' 'unsafe-inline' data:; connect-src 'none'; "
       "frame-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'")
KIT = '<link rel="stylesheet" href="/api/module-ui-kit/kit.css"><script src="/api/module-ui-kit/bridge.js"></script>'
TOOL = {'id': 'board', 'label': 'Board', 'icon': 'task', 'panel': 'ui/panel.html'}
SERVER = tmo.OwnToolsTest.SERVER
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 16


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))


class Http(tmo.OwnEnv):
    """Сервер у процесі й запити до нього."""

    def setUp(self):
        super().setUp()
        os.environ['DEAI_HOME'] = self.deai
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.port = httpd.server_address[1]

        def stop():
            httpd.shutdown()
            httpd.server_close()
        self.addCleanup(stop)

    def get(self, path, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            c.request('GET', path, headers=headers or {})
            r = c.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            c.close()

    def url(self, rest, mid='acme', sid=None):
        return '/api/module-ui/%s/%s/%s' % (sid or self.sp['id'], mid, rest)

    def assert_404(self, path, headers=None):
        st, h, body = self.get(path, headers)
        self.assertEqual((st, body), (404, b'not found\n'), path)
        self.assertEqual(h.get('x-content-type-options'), 'nosniff', path)
        self.assertEqual(h.get('content-type'), 'text/plain; charset=utf-8', path)

    def assert_guarded(self, h):
        self.assertEqual(h.get('content-security-policy'), CSP)
        self.assertEqual(h.get('x-content-type-options'), 'nosniff')
        self.assertEqual(h.get('access-control-allow-origin'), '*')
        self.assertEqual(h.get('referrer-policy'), 'no-referrer')


class Ui(Http):
    """Власний модуль `acme` у просторі: довірений, увімкнений, з однією панеллю `ui/panel.html`."""

    def mod(self, mid='acme', tools=(TOOL,), api=2, trusted=True, enabled=True, files=None, sp=None):
        extra = {'api': api}
        if tools is not None:
            extra['tools'] = list(tools)
        d = self.own(mid, server=SERVER, extra=extra, sp=sp)
        for rel, data in (files if files is not None else {
                'ui/panel.html': '<!doctype html><p>hi</p>', 'ui/app.js': 'x=1', 'ui/app.css': 'a{}',
                'ui/logo.png': PNG, 'ui/data.json': '{}', 'ui/icon.svg': '<svg/>', 'ui/f.woff2': b'wOF2',
                'ui/sub/deep.js': 'y=2', 'ui/notes.txt': 'n', 'ui/run.py': 'import os', 'other/x.js': 'z=3',
                'ui/UP.JS': 'u=4'}).items():
            _put(os.path.join(d, rel), data)
        if trusted:
            self.trust(mid, sp=sp)
        if enabled:
            self.enable_raw(mid, sp=sp)
        return d


class Serve(Ui):
    def test_html_gets_kit_after_doctype(self):
        self.mod()
        st, h, body = self.get(self.url('ui/panel.html'))
        self.assertEqual(st, 200)
        self.assertEqual(body.decode(), '<!doctype html>' + KIT + '<p>hi</p>')
        self.assertEqual(h['content-type'], 'text/html; charset=utf-8')
        self.assertEqual(h['cache-control'], 'no-store')
        self.assertEqual(h['content-length'], str(len(body)))
        self.assert_guarded(h)

    def test_html_kit_position_variants(self):
        cases = {
            'no doctype': ('<p>x</p>', KIT + '<p>x</p>'),
            'uppercase doctype with lead space': ('  <!DOCTYPE HTML PUBLIC "x">\n<p>', '  <!DOCTYPE HTML PUBLIC "x">' + KIT + '\n<p>'),
            'bom then doctype': ('﻿<!doctype html><p>', '﻿<!doctype html>' + KIT + '<p>'),
            'bom without doctype': ('﻿<p>', '﻿' + KIT + '<p>'),
            'doctype later is not leading': ('<p><!doctype html>', KIT + '<p><!doctype html>'),
        }
        for name, (src, want) in cases.items():
            with self.subTest(name):
                self.mod(files={'ui/panel.html': src})
                dm.reset_caches()
                st, _, body = self.get(self.url('ui/panel.html'))
                self.assertEqual((st, body.decode('utf-8')), (200, want))

    def test_assets_types_and_headers(self):
        self.mod()
        want = {'app.js': 'text/javascript; charset=utf-8', 'app.css': 'text/css; charset=utf-8',
                'logo.png': 'image/png', 'data.json': 'application/json', 'icon.svg': 'image/svg+xml',
                'f.woff2': 'font/woff2', 'sub/deep.js': 'text/javascript; charset=utf-8', 'UP.JS': 'text/javascript; charset=utf-8'}
        for name, ctype in want.items():
            with self.subTest(name):
                st, h, body = self.get(self.url('ui/' + name))
                self.assertEqual(st, 200)
                self.assertEqual(h['content-type'].split(';')[0], ctype.split(';')[0])
                if ctype.startswith('text/'):
                    self.assertEqual(h['content-type'], ctype)
                else:
                    self.assertEqual(h['content-type'], ctype.split(';')[0])
                self.assert_guarded(h)
        self.assertEqual(self.get(self.url('ui/logo.png'))[2], PNG)

    def test_asset_304_keeps_the_guard_headers(self):
        self.mod()
        _, h, _ = self.get(self.url('ui/app.js'))
        st, h2, body = self.get(self.url('ui/app.js'), {'If-None-Match': h['etag']})
        self.assertEqual((st, body), (304, b''))
        self.assert_guarded(h2)

    def test_query_string_is_ignored(self):
        self.mod()
        self.assertEqual(self.get(self.url('ui/app.js') + '?v=3&x=%00')[0], 200)

    def test_only_the_panel_folder_of_a_tool_is_served(self):
        self.mod()
        for rest in ('server.py', 'module.json', 'other/x.js', 'ui', 'ui/', 'ui/nope.js', 'ui/sub', 'ui/sub/'):
            with self.subTest(rest):
                self.assert_404(self.url(rest))

    def test_second_tool_folder_is_served_too(self):
        t2 = dict(TOOL, id='two', panel='alt/two.html')
        self.mod(tools=[TOOL, t2], files={'ui/panel.html': '<p>1', 'alt/two.html': '<p>2', 'alt/a.js': 'a', 'oth/b.js': 'b'})
        self.assertEqual(self.get(self.url('alt/a.js'))[0], 200)
        self.assertEqual(self.get(self.url('alt/two.html'))[0], 200)
        self.assert_404(self.url('oth/b.js'))

    def test_a_panel_in_the_module_root_has_no_extra_files(self):
        """Панель на 2 складових (`ui/p.html`) — мінімум; файли поза її текою не віддаються."""
        self.mod(tools=[dict(TOOL, panel='ui/p.html')], files={'ui/p.html': '<p>', 'ui/q.js': 'q', 'module_x.js': 'k'})
        self.assertEqual(self.get(self.url('ui/q.js'))[0], 200)
        self.assert_404(self.url('module_x.js'))

    def test_disallowed_extensions(self):
        self.mod()
        for name in ('run.py', 'notes.txt'):
            with self.subTest(name):
                self.assert_404(self.url('ui/' + name))

    def test_hostile_paths(self):
        self.mod()
        sid = self.sp['id']
        cases = ['ui/../server.py', 'ui/%2e%2e/server.py', 'ui%2fapp.js', 'ui/app.js%2f', 'ui%5capp.js', 'ui/app.js%5c',
                 'ui/app.js%00', 'ui/app.js%00.png', 'ui//app.js', '/ui/app.js', 'ui/%ff.js', 'ui/%c0%af.js',
                 'ui/.hidden.js', 'ui/a/b/c/d/e/f.js', 'ui/app.js/', '%2e%2e/%2e%2e/x.js', 'ui/%2e/app.js']
        for rest in cases:
            with self.subTest(rest):
                self.assert_404(self.url(rest))
        for bad in ('/api/module-ui/', '/api/module-ui/%s' % sid, '/api/module-ui/%s/acme' % sid,
                    '/api/module-ui/%s/acme/' % sid, '/api/module-ui/%s/acme/ui' % sid,
                    '/api/module-ui//acme/ui/app.js', '/api/module-ui/%s//ui/app.js' % sid,
                    '/api/module-ui/%2e%2e/acme/ui/app.js', '/api/module-ui/' + sid + '/%2e%2e/ui/app.js'):
            with self.subTest(bad):
                self.assert_404(bad)

    def test_seven_segments_are_refused_but_six_pass(self):
        deep = dict(TOOL, panel='a/b/c/p.html')
        self.mod(tools=[deep], files={'a/b/c/p.html': '<p>', 'a/b/c/d/e.js': 'e', 'a/b/c/d/e/f.js': 'f'})
        self.assertEqual(self.get(self.url('a/b/c/d/e.js'))[0], 200)
        self.assertEqual(self.get(self.url('a/b/c/d/e/f.js'))[0], 200)       # 6 складових
        _put(os.path.join(self.sp['path'], 'x'), b'')
        self.assert_404(self.url('a/b/c/d/e/f/g.js'))                         # 7

    def test_unknown_space_other_space_and_unknown_module(self):
        self.mod()
        other = self.new_space('Beta')
        self.assert_404(self.url('ui/app.js', sid='ghost'))
        self.assert_404(self.url('ui/app.js', sid=other['id']))               # модуль чужого простору
        self.assert_404(self.url('ui/app.js', mid='nobody'))
        self.assert_404(self.url('ui/app.js', mid='ACME'))

    def test_module_states_that_must_not_serve(self):
        self.mod('off', enabled=False)
        self.mod('raw', trusted=False)
        self.mod('old', tools=None, api=1)
        self.mod('plain', tools=None)
        self.mod('bad', tools=[dict(TOOL, panel='ui/none.html')])
        for mid in ('off', 'raw', 'old', 'plain', 'bad'):
            with self.subTest(mid):
                self.assert_404(self.url('ui/app.js', mid=mid))
        self.mod('on')
        self.assertEqual(self.get(self.url('ui/app.js', mid='on'))[0], 200)

    def test_enabled_must_be_explicit(self):
        self.mod(enabled=False)
        p = self.space_json(self.sp)
        data = _read(p)
        data.setdefault('modules', {})['acme'] = {'enabled': 'yes'}
        _write(p, data)
        self.assert_404(self.url('ui/app.js'))

    def test_the_trusted_snapshot_is_served_not_the_space_folder(self):
        d = self.mod(files={'ui/panel.html': '<p>old</p>', 'ui/app.js': 'old'})
        _put(os.path.join(d, 'ui', 'app.js'), 'NEW-EDIT')
        _put(os.path.join(d, 'ui', 'extra.js'), 'planted')
        _put(os.path.join(d, 'ui', 'panel.html'), '<p>NEW</p>')
        self.assertEqual(self.get(self.url('ui/app.js'))[2], b'old')
        self.assert_404(self.url('ui/extra.js'))
        self.assertIn(b'<p>old</p>', self.get(self.url('ui/panel.html'))[2])

    def test_no_task_header_effect_and_no_prefix(self):
        self.mod()
        self.assertEqual(self.get(self.url('ui/app.js'), {'X-Canvas-Task': 'ghost'})[0], 200)
        self.assertEqual(self.get('/t/x' + self.url('ui/app.js'))[0], 404)       # префікс задачі до маршруту не доходить

    def test_oversized_html_is_refused(self):
        d = self.mod()
        self.assertEqual(self.get(self.url('ui/panel.html'))[0], 200)
        with mock.patch.object(dm, 'MAX_PANEL_BYTES', 8):
            self.assert_404(self.url('ui/panel.html'))
        self.assertEqual(self.get(self.url('ui/panel.html'))[0], 200)
        self.assertTrue(os.path.isdir(d))


class Builtin(Http):
    """Файлова система проти атак: вбудований модуль (`m.dir` — жива тека, у якій можна підкласти посилання)."""

    def bmod(self, mid='bi'):
        d = os.path.join(self.mods, mid)
        _write(os.path.join(d, 'module.json'), {'api': 2, 'id': mid, 'name': mid, 'version': '1', 'roles': [],
                                                'settings': [], 'tools': [TOOL]})
        _write(os.path.join(d, 'server.py'), SERVER)
        _put(os.path.join(d, 'ui', 'panel.html'), '<p>x')
        _put(os.path.join(d, 'ui', 'app.js'), 'ok')
        _put(os.path.join(d, 'other', 'secret.js'), 'secret')
        p = self.space_json(self.sp)
        data = _read(p)
        data.setdefault('modules', {})[mid] = {'enabled': True}
        _write(p, data)
        dm.reset_caches()
        return d

    def test_baseline_serves(self):
        self.bmod()
        self.assertEqual(self.get(self.url('ui/app.js', mid='bi'))[::2], (200, b'ok'))

    def test_a_directory_symlink_segment_is_refused(self):
        d = self.bmod()
        os.symlink(os.path.join(d, 'other'), os.path.join(d, 'ui', 'linked'))
        self.assert_404(self.url('ui/linked/secret.js', mid='bi'))

    def test_a_file_symlink_is_refused(self):
        d = self.bmod()
        os.symlink(os.path.join(d, 'other', 'secret.js'), os.path.join(d, 'ui', 'link.js'))
        self.assert_404(self.url('ui/link.js', mid='bi'))

    def test_a_hard_link_is_refused(self):
        d = self.bmod()
        os.link(os.path.join(d, 'other', 'secret.js'), os.path.join(d, 'ui', 'hard.js'))
        self.assert_404(self.url('ui/hard.js', mid='bi'))

    def test_a_directory_named_like_a_file_is_refused(self):
        d = self.bmod()
        os.makedirs(os.path.join(d, 'ui', 'dir.js'))
        self.assert_404(self.url('ui/dir.js', mid='bi'))

    def test_without_dir_fd_the_fallback_still_refuses_symlinks(self):
        d = self.bmod()
        os.symlink(os.path.join(d, 'other', 'secret.js'), os.path.join(d, 'ui', 'link.js'))
        os.symlink(os.path.join(d, 'other'), os.path.join(d, 'ui', 'linked'))
        with mock.patch.object(serve, '_PUBLISHED_DIRFD', False):
            self.assertEqual(self.get(self.url('ui/app.js', mid='bi'))[::2], (200, b'ok'))
            self.assert_404(self.url('ui/link.js', mid='bi'))
            self.assert_404(self.url('ui/linked/secret.js', mid='bi'))


class Kit(Http):
    def test_the_two_kit_files_are_served(self):
        for name, ctype in (('kit.css', 'text/css; charset=utf-8'), ('bridge.js', 'text/javascript; charset=utf-8')):
            with self.subTest(name):
                st, h, body = self.get('/api/module-ui-kit/' + name)
                self.assertEqual(st, 200)
                self.assertEqual(h['content-type'], ctype)
                self.assert_guarded(h)
                with open(os.path.join(serve.APP_DIR, 'module-kit', name), 'rb') as f:
                    self.assertEqual(body, f.read())

    def test_kit_304_keeps_the_guard_headers(self):
        _, h, _ = self.get('/api/module-ui-kit/kit.css')
        st, h2, _ = self.get('/api/module-ui-kit/kit.css', {'If-None-Match': h['etag']})
        self.assertEqual(st, 304)
        self.assert_guarded(h2)

    def test_anything_else_is_404(self):
        for rest in ('kit-vars.js', 'nope.css', '', 'kit.css/', 'kit.css/x', '../kit.css', '%2e%2e/module-kit/kit.css',
                     'kit.css%00', 'kit.css%2fx', 'sub/kit.css', 'KIT.CSS', 'bridge.js%5c', '%ff', 'kit.css.map'):
            with self.subTest(rest):
                self.assert_404('/api/module-ui-kit/' + rest)


if __name__ == '__main__':
    unittest.main()
