"""Виклики інструментів і дій модуля (M1, Task 4): `POST /api/module-tool` і `POST /api/module-action`.

Що доводиться:
  * `module-tool`: лише `tool_*` (`TOOL_FN_RE`) справного, api 2, явно увімкненого модуля з інструментами; `check`, `action_*`,
    `__init__`, ролі недосяжні; результат — лише JSON ≤ 256 КіБ; тайм-аут `check-timeout`; секрет у тексті винятку вирізано;
  * `module-action`: `from` ∈ `where`; задача — лише цього простору; ітерація — `None` чи її id; `target` — рівно як описано;
    результат нормалізується (`ok` — bool, `text` ≤ 300, `url` лише http(s) ≤ 2048 без пробілів/керівних);
  * обидва: тіло ≤ 64 КіБ (413 `body-too-large`), чужий Origin — 403, `/t/<id>/…` — 400, закон ізоляції (`shared_state`);
  * CSP панелі закінчується `frame-ancestors 'self'`.

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
import isolation  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_modules_own as tmo  # noqa: E402
from test_modules import _write, _read  # noqa: E402

_REAL = None
SECRET = 'S3cr3t-Zq91-tok'
TOOL = {'id': 'board', 'label': 'Board', 'icon': 'task', 'panel': 'ui/panel.html'}
URL_CASES = {
    'good': 'https://x.example/a?b=1', 'upper': 'HTTPS://x.example/Y', 'plain': 'http://x.example',
    'js': 'javascript:alert(1)', 'data': 'data:text/html,<b>x</b>', 'lead': ' https://x.example', 'ctrl': 'https://x.example/\nz',
    'tab': 'https://x.example/\tz', 'space': 'https://x.example/a b', 'long': 'https://x.example/' + 'a' * 3000,
    'edge': 'https://x.example/' + 'a' * (2048 - len('https://x.example/')), 'over': 'https://x.example/' + 'a' * (2049 - len('https://x.example/')),
    'nohost': 'https://', 'nohost2': 'https:///path', 'zwsp': 'https://x\u200by', 'bidi': 'https://x\u202ey', 'c1': 'https://x\x9bz',
    'nbsp': 'https://x\u00a0y', 'backslash': 'https:\\\\evil', 'ipv6': 'https://[::1', 'num': 5, 'ftp': 'ftp://x.example/',
    'bs-userinfo': 'https://evil.example\\@good.example', 'userinfo': 'https://u:p@h.example/', 'user-only': 'https://u@h.example/',
    'bs-path': 'https://h.example/a\\b', 'at-path': 'https://h.example/a@b',
}
SERVER = tmo.OWN_SERVER + '''
import json
import threading
import time
URLS = %r


def tool_echo(ctx, args):
    return {"args": args}


def tool_slow(ctx, args):
    time.sleep(1)
    return 1


def tool_boom(ctx, args):
    raise RuntimeError("bad token " + ctx["secrets"].get("token", ""))


def tool_set(ctx, args):
    return {1, 2}


def tool_nan(ctx, args):
    return float("nan")


def tool_big(ctx, args):
    return "x" * (300 * 1024)


class Evil(dict):
    def items(self):
        raise RuntimeError("leak " + __file__)


def tool_evil(ctx, args):
    return Evil(a=1)


class Sub(dict):
    pass


def tool_sub(ctx, args):
    return Sub(a=[1, 2])


_gate = threading.Event()


def tool_block(ctx, args):
    _gate.wait(10)
    return "done"


def tool_release(ctx, args=None):
    _gate.set()


def action_evil(ctx, target):
    return Evil(ok=True)


def action_subdict(ctx, target):
    return Sub(ok=True, text="a\\x00b\\u200bc\\u202ed\\nline\\x9bx" + "z" * 400)


def tool_edge(ctx, args):
    return "x" * (256 * 1024 - 2)


def action_echo(ctx, target):
    return {"ok": True, "text": json.dumps(target, sort_keys=True)}


SHAPES = {
    "long": {"ok": True, "text": "t" * 500}, "noook": {"text": "x"}, "strok": {"ok": "yes"}, "intok": {"ok": 1},
    "notdict": "fine", "junk": {"ok": False, "text": 5, "url": ["https://x.example"], "extra": 1},
}


def action_shape(ctx, target):
    return SHAPES[os.environ["SHAPE_CASE"]]


def action_url(ctx, target):
    return {"ok": True, "text": "u", "url": URLS[os.environ["URL_CASE"]]}


def action_slow(ctx, target):
    time.sleep(1.5)
    return {"ok": True}


def action_fast_fail(ctx, target):
    raise RuntimeError("bad token " + ctx["secrets"].get("token", ""))


def action_with_dash(ctx, target):
    return {"ok": True, "text": "dash"}


''' % (URL_CASES,)

ACTIONS = [{'id': 'echo', 'label': 'Echo', 'where': ['palette', 'task']},
           {'id': 'shape', 'label': 'Shape', 'where': ['palette']}, {'id': 'url', 'label': 'Url', 'where': ['palette']},
           {'id': 'slow', 'label': 'Slow', 'where': ['palette'], 'timeout_s': 1},
           {'id': 'fast-fail', 'label': 'F', 'where': ['palette']}, {'id': 'with-dash', 'label': 'W', 'where': ['palette']},
           {'id': 'evil', 'label': 'E', 'where': ['palette']}, {'id': 'subdict', 'label': 'S', 'where': ['palette']}]


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class Calls(tmo.OwnEnv):
    """Власний модуль `acme` (інструменти й дії), сервер у процесі, запити до нього."""

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
        self.raw = []
        self.addCleanup(self.drain_inflight)

    def drain_inflight(self):
        """Потоки-сироти (тайм-аути) доживають: відпускаємо засув, чекаємо, поки лічильник спаде, і лише тоді чистимо стан."""
        try:
            dm.catalog(self.sp)['acme'].fn('tool_release')(None, None)
        except Exception:  # noqa: BLE001 — модуля `acme` у тесті могло не бути
            pass
        for _ in range(120):
            if not dm._inflight:
                break
            threading.Event().wait(0.05)
        dm._inflight.clear()

    def mod(self, mid='acme', tools=(TOOL,), actions=ACTIONS, api=2, trusted=True, enabled=True, sp=None):
        extra = {'api': api}
        if tools is not None:
            extra['tools'] = list(tools)
        if actions is not None:
            extra['actions'] = list(actions)
        d = self.own(mid, server=SERVER, extra=extra, sp=sp)
        _write(os.path.join(d, 'ui', 'panel.html'), '<p>hi</p>')
        if trusted:
            self.trust(mid, sp=sp)
        if enabled:
            self.enable_raw(mid, sp=sp)
        dm.write_secrets((sp or self.sp)['id'], mid, {'token': SECRET}, space=sp or self.sp)
        return d

    def req(self, path, payload=None, headers=None, raw=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        try:
            body = raw if raw is not None else json.dumps(payload).encode()
            c.request('POST', path, body=body, headers={'Content-Type': 'application/json', **(headers or {})})
            r = c.getresponse()
            data = r.read().decode('utf-8')
            self.raw.append(data)
            try:
                return r.status, json.loads(data)
            except ValueError:
                return r.status, data
        finally:
            c.close()

    def tool(self, fn, args=None, mid='acme', **kw):
        body = {'module': mid, 'fn': fn, 'space': self.sp['id']}
        if args is not None:
            body['args'] = args
        body.update(kw)
        return self.req('/api/module-tool', body)

    def refused(self, st, body, status, code):
        self.assertEqual((st, body.get('ok'), body.get('code')), (status, False, code), body)

    # ---- задачі -------------------------------------------------------------------------------------------------
    def task(self, tid='t1', title='Task One', iterations=('it-1', 'it-2'), sp=None, mkdir=True):
        sp = sp or self.sp
        tdir = os.path.join(sp['path'], 'tasks-data', tid)
        if mkdir:
            os.makedirs(tdir, exist_ok=True)
        tf = spaces.tasks_file(sp)
        try:
            cfg = _read(tf)
        except OSError:
            cfg = {'current': tid, 'tasks': {}}
        cfg['tasks'][tid] = {'dir': tdir, 'title': title}
        _write(tf, cfg)
        if mkdir:
            _write(os.path.join(tdir, 'iterations.json'), {'iterations': [
                {'id': i, 'note': 'Note ' + i} for i in iterations], 'publish_url': None})
        return tdir

    def act(self, action='echo', frm='palette', task='t1', iteration=None, mid='acme', **kw):
        body = {'module': mid, 'action': action, 'from': frm, 'task': task, 'iteration': iteration, 'space': self.sp['id']}
        body.update(kw)
        return self.req('/api/module-action', body)


class ToolTests(Calls):
    def test_echo_roundtrip_and_default_args(self):
        self.mod()
        self.assertEqual(self.tool('tool_echo', {'a': [1, 'б', None]}), (200, {'value': {'args': {'a': [1, 'б', None]}}}))
        self.assertEqual(self.tool('tool_echo'), (200, {'value': {'args': None}}))
        self.assertEqual(self.tool('tool_echo', 0), (200, {'value': {'args': 0}}))

    def test_module_must_be_enabled_ok_api2_with_tools(self):
        self.mod('off', enabled=False)
        self.mod('raw', trusted=False)
        self.mod('old', tools=None, actions=None, api=1)
        self.mod('notools', tools=None)
        for mid in ('off', 'raw', 'old', 'notools', 'ghost'):
            with self.subTest(mid=mid):
                self.refused(*self.tool('tool_echo', {}, mid=mid), 404, 'unknown-module')

    def test_implicit_space_is_the_current_one(self):
        self.mod()
        self.assertEqual(self.req('/api/module-tool', {'module': 'acme', 'fn': 'tool_echo', 'args': 1}), (200, {'value': {'args': 1}}))

    def test_non_tool_functions_are_unreachable(self):
        self.mod()
        for fn in ('check', 'action_echo', '__init__', 'tool-echo', 'tool_', 'publish', 'tokens', 'TOOL_echo', 'tool_missing',
                   'tool_ECHO', 'tool_echo ', ' tool_echo', 'tool_echo\n', 'tool_' + 'a' * 41, '', 'tool_ping.x'):
            with self.subTest(fn=fn):
                self.refused(*self.tool(fn, {}), 404, 'unknown-function')
        for fn in (None, 5, ['tool_echo'], {'a': 1}, True):
            with self.subTest(fn=fn):
                self.refused(*self.req('/api/module-tool', {'module': 'acme', 'fn': fn}), 404, 'unknown-function')
        self.refused(*self.req('/api/module-tool', {'module': 'acme'}), 404, 'unknown-function')
        self.refused(*self.req('/api/module-tool', {'module': ['acme'], 'fn': 'tool_echo'}), 404, 'unknown-module')

    def test_timeout_is_check_timeout(self):
        self.mod()
        with mock.patch.object(dm, 'TOOL_TIMEOUT', 0.3):
            st, body = self.tool('tool_slow', {})
        self.refused(st, body, 504, 'check-timeout')

    def test_exception_text_is_scrubbed(self):
        self.mod()
        st, body = self.tool('tool_boom', {})
        self.refused(st, body, 502, 'module-error')
        self.assertNotIn(SECRET, json.dumps(body))
        for r in self.raw:
            self.assertNotIn(SECRET, r)

    def test_result_must_be_json_and_small(self):
        self.mod()
        for fn, text in (('tool_set', 'result is not JSON'), ('tool_nan', 'result is not JSON'), ('tool_big', 'result is too big')):
            with self.subTest(fn=fn):
                st, body = self.tool(fn, {})
                self.refused(st, body, 502, 'module-error')
                self.assertEqual(body['error'], text)
        st, body = self.tool('tool_edge', {})
        self.assertEqual((st, len(body['value'])), (200, 256 * 1024 - 2))

    def test_body_over_64k_is_413_and_nothing_runs(self):
        self.mod()
        st, body = self.req('/api/module-tool', {'module': 'acme', 'fn': 'tool_echo', 'args': 'x' * (65 * 1024)})
        self.refused(st, body, 413, 'body-too-large')
        st, body = self.req('/api/module-tool', {'module': 'acme', 'fn': 'tool_echo', 'args': 'x' * 60000})
        self.assertEqual(st, 200)

    def test_bad_bodies(self):
        self.mod()
        self.assertEqual(self.req('/api/module-tool', raw=b'{nope')[0], 400)
        self.assertEqual(self.req('/api/module-tool', raw=b'[1]')[0], 400)
        self.assertEqual(self.req('/api/module-tool', raw=b'')[1].get('code'), 'unknown-module')

    def test_foreign_origin_prefix_and_space(self):
        self.mod()
        body = {'module': 'acme', 'fn': 'tool_echo', 'args': 1}
        st, out = self.req('/api/module-tool', body, {'Origin': 'http://evil.example'})
        self.assertEqual((st, out), (403, {'ok': False, 'error': 'foreign origin'}))
        st, out = self.req('/api/module-tool', body, {'Origin': 'http://127.0.0.1:%d' % self.port})
        self.assertEqual(st, 200)
        self.assertEqual(self.req('/t/tx/api/module-tool', body)[0], 400)
        self.refused(*self.req('/api/module-tool', dict(body, space='ghost')), 404, 'unknown-space')

    def test_other_space_module_is_not_reachable(self):
        other = self.new_space('Beta')
        self.mod('acme', sp=other)
        self.refused(*self.tool('tool_echo', {}), 404, 'unknown-module')
        self.assertEqual(self.tool('tool_echo', 1, space=other['id'])[0], 200)

    def test_isolation_law_for_shared_state(self):
        self.mod()
        p = self.space_json(self.sp)
        data = _read(p)
        data['modules']['acme']['shared_state'] = True
        _write(p, data)
        self.assertTrue(isolation.isolated())
        self.refused(*self.tool('tool_echo', {}), 409, 'isolated')
        with mock.patch.object(isolation, 'isolated', return_value=False):
            self.assertEqual(self.tool('tool_echo', 7), (200, {'value': {'args': 7}}))


class ActionTests(Calls):
    def setUp(self):
        super().setUp()
        self.mod()
        self.tdir = self.task()

    def test_target_content(self):
        st, body = self.act('echo', 'task', iteration='it-2')
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(json.loads(body['text']), {
            'from': 'task', 'task': {'id': 't1', 'name': 'Task One', 'dir': self.tdir},
            'iteration': {'id': 'it-2', 'name': 'Note it-2'}})
        self.assertTrue(os.path.isabs(json.loads(body['text'])['task']['dir']))

    def test_iteration_none_and_absent_are_accepted(self):
        st, body = self.act('echo')
        self.assertEqual(json.loads(body['text'])['iteration'], None)
        body = {'module': 'acme', 'action': 'echo', 'from': 'palette', 'task': 't1'}
        st, out = self.req('/api/module-action', body)
        self.assertEqual((st, json.loads(out['text'])['iteration']), (200, None))

    def test_works_without_tools_and_hyphen_ids(self):
        self.mod('plain', tools=None, actions=[{'id': 'with-dash', 'label': 'W', 'where': ['palette']}])
        self.assertEqual(self.act('with-dash', mid='plain'), (200, {'ok': True, 'text': 'dash'}))

    def test_module_and_action_gates(self):
        self.mod('off', enabled=False)
        self.mod('raw', trusted=False)
        self.mod('old', tools=None, actions=None, api=1)
        for mid in ('off', 'raw', 'old', 'ghost', None, ['acme']):
            with self.subTest(mid=mid):
                self.refused(*self.act(mid=mid), 404, 'unknown-module')
        self.mod('noact', actions=None)
        self.refused(*self.act(mid='noact'), 404, 'unknown-action')
        for a in ('nope', 'tool_echo', 'echo ', 'ECHO', None, 5, ['echo'], 'with_dash', '__init__', 'check'):
            with self.subTest(action=a):
                self.refused(*self.act(a), 404, 'unknown-action')

    def test_from_must_be_in_where(self):
        for frm in ('task', 'palette'):
            self.assertEqual(self.act('echo', frm)[0], 200)
        for frm in ('shell', None, 5, ['palette'], '', 'PALETTE'):
            with self.subTest(frm=frm):
                self.refused(*self.act('echo', frm), 400, 'bad-request')
        self.refused(*self.act('shape', 'task'), 400, 'bad-request')

    def test_task_must_belong_to_this_space(self):
        other = self.new_space('Beta')
        self.task('t2', sp=other)
        self.refused(*self.act(task='t2'), 404, 'unknown-task')
        self.assertEqual(self.act(task='t2', space=other['id'], mid='acme')[1].get('code'), 'unknown-module')
        self.mod('acme', sp=other)
        st, body = self.act(task='t2', space=other['id'])
        self.assertEqual((st, body['ok']), (200, True), body)
        self.refused(*self.act(task='t1', space=other['id']), 404, 'unknown-task')

    def test_unknown_task_and_iteration(self):
        for t in ('ghost', None, 5, ['t1'], '', '../t1'):
            with self.subTest(task=t):
                self.refused(*self.act(task=t), 404, 'unknown-task')
        for i in ('it-9', 5, ['it-1'], '', {'id': 'it-1'}):
            with self.subTest(iteration=i):
                self.refused(*self.act(iteration=i), 404, 'unknown-iteration')
        self.task('t3', mkdir=False)
        self.refused(*self.act(task='t3'), 404, 'unknown-task')            # теки задачі на цій машині нема
        os.remove(os.path.join(self.task('t4'), 'iterations.json'))
        self.assertEqual(self.act(task='t4')[0], 200)
        self.refused(*self.act(task='t4', iteration='it-1'), 404, 'unknown-iteration')

    def test_result_normalization(self):
        with mock.patch.dict(os.environ, {'SHAPE_CASE': 'long'}):
            self.assertEqual(self.act('shape')[1], {'ok': True, 'text': 't' * 300})
        for a in ('noook', 'strok', 'intok', 'notdict'):
            with self.subTest(a=a), mock.patch.dict(os.environ, {'SHAPE_CASE': a}):
                st, body = self.act('shape')
                self.refused(st, body, 502, 'module-error')
                self.assertEqual(body['error'], 'action result must be {"ok": bool, ...}')
        with mock.patch.dict(os.environ, {'SHAPE_CASE': 'junk'}):
            self.assertEqual(self.act('shape'), (200, {'ok': False}))

    def test_url_filter(self):
        keep = {'good', 'upper', 'plain', 'edge', 'at-path'}   # решта — відкинуто
        for k, v in URL_CASES.items():
            with self.subTest(case=k), mock.patch.dict(os.environ, {'URL_CASE': k}):
                st, body = self.act('url')
                self.assertEqual(st, 200)
                self.assertEqual(body.get('url'), v if k in keep else None, k)
                self.assertEqual(body['text'], 'u')

    def test_timeout_s_is_honored_and_default_is_used(self):
        st, body = self.act('slow')                              # `timeout_s: 1` у маніфесті
        self.refused(st, body, 504, 'check-timeout')
        self.mod('plain', tools=None, actions=[{'id': 'slow', 'label': 'S', 'where': ['palette']}])
        with mock.patch.object(dm, 'ACTION_TIMEOUT', 0.3):
            self.refused(*self.act('slow', mid='plain'), 504, 'check-timeout')

    def test_exception_text_is_scrubbed(self):
        st, body = self.act('fast-fail')
        self.refused(st, body, 502, 'module-error')
        for r in self.raw:
            self.assertNotIn(SECRET, r)

    def test_body_cap_origin_and_isolation(self):
        st, body = self.act(junk='x' * (65 * 1024))
        self.refused(st, body, 413, 'body-too-large')
        st, out = self.req('/api/module-action', {'module': 'acme', 'action': 'echo', 'from': 'palette', 'task': 't1'},
                           {'Origin': 'http://evil.example'})
        self.assertEqual((st, out), (403, {'ok': False, 'error': 'foreign origin'}))
        self.assertEqual(self.req('/api/module-action', raw=b'{x')[0], 400)
        p = self.space_json(self.sp)
        data = _read(p)
        data['modules']['acme']['shared_state'] = True
        _write(p, data)
        self.refused(*self.act(), 409, 'isolated')
        with mock.patch.object(isolation, 'isolated', return_value=False):
            self.assertEqual(self.act()[0], 200)


class HardeningTests(Calls):
    def test_hostile_result_objects_never_escape(self):
        self.mod()
        self.task()
        st, body = self.tool('tool_evil', {})
        self.refused(st, body, 502, 'module-error')
        self.assertEqual(body['error'], 'result is not JSON')
        self.assertNotIn('leak', json.dumps(body))
        self.assertEqual(self.tool('tool_sub', {}), (200, {'value': {'a': [1, 2]}}))
        st, body = self.act('evil')
        self.refused(st, body, 502, 'module-error')
        self.assertEqual(body['error'], 'result is not JSON')

    def test_action_text_is_stripped_of_control_and_format_chars(self):
        self.mod()
        self.task()
        st, body = self.act('subdict')
        self.assertEqual((st, body['ok']), (200, True))
        self.assertEqual(body['text'], 'abcd\nlinex' + 'z' * (300 - len('abcd\nlinex')))

    def test_tool_result_is_a_sanitized_copy(self):
        self.mod()
        self.assertEqual(dm.call_tool(self.sp, 'acme', 'tool_sub', None), {'a': [1, 2]})
        self.assertIs(type(dm.call_tool(self.sp, 'acme', 'tool_sub', None)), dict)

    def test_inflight_cap_per_module(self):
        self.mod()
        self.task()
        with mock.patch.object(dm, 'TOOL_TIMEOUT', 0.2):
            for i in range(dm.MAX_INFLIGHT):
                self.refused(*self.tool('tool_block', {}), 504, 'check-timeout')
            st, body = self.tool('tool_echo', 1)
            self.refused(st, body, 429, 'module-busy')
            st, body = self.act('echo')
            self.refused(st, body, 429, 'module-busy')
            # інший модуль того ж простору — не зачеплений
            self.mod('other')
            self.assertEqual(self.tool('tool_echo', 1, mid='other')[0], 200)
        m = dm.catalog(self.sp)['acme']
        m.fn('tool_release')(None, None)
        for _ in range(100):
            if not dm._inflight.get((self.sp['id'], 'acme')):
                break
            threading.Event().wait(0.05)
        self.assertEqual(self.tool('tool_echo', 2), (200, {'value': {'args': 2}}))
        self.assertFalse(dm._inflight.get((self.sp['id'], 'acme')))

    def test_inflight_is_released_after_an_exception(self):
        self.mod()
        for _ in range(dm.MAX_INFLIGHT + 2):
            self.refused(*self.tool('tool_boom', {}), 502, 'module-error')
        self.assertEqual(self.tool('tool_echo', 1)[0], 200)

    def raw_req(self, head, body=b''):
        import socket
        s = socket.create_connection(('127.0.0.1', self.port), timeout=4)
        try:
            s.sendall(head.encode() + body)
            buf = b''
            while True:
                try:
                    d = s.recv(65536)
                except socket.timeout:
                    self.fail('no prompt answer: %r' % buf)
                if not d:
                    break
                buf += d
                if b'\r\n\r\n' in buf and buf.endswith(b'}'):
                    break
            return buf.decode('utf-8', 'replace')
        finally:
            s.close()

    def head(self, path, length):
        return ('POST %s HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: %s\r\n\r\n' % (path, length))

    def test_negative_and_garbage_content_length(self):
        self.mod()
        for path in ('/api/module-tool', '/api/module-action'):
            for ln in ('-1', 'abc'):
                with self.subTest(path=path, ln=ln):
                    out = self.raw_req(self.head(path, ln))
                    self.assertIn(' 400 ', out.split('\r\n')[0])
                    self.assertIn('"code": "bad-request"', out)

    def test_huge_content_length_is_413_without_waiting(self):
        self.mod()
        for path in ('/api/module-tool', '/api/module-action'):
            with self.subTest(path=path):
                out = self.raw_req(self.head(path, '99999999999'))
                self.assertIn(' 413 ', out.split('\r\n')[0])
                self.assertIn('"code": "body-too-large"', out)
                self.assertIn('Connection: close', out)

    def test_other_routes_keep_their_behaviour(self):
        self.mod()
        self.assertEqual(self.req('/api/module-check', {'id': 'acme', 'space': self.sp['id']})[0], 200)


class CspPin(unittest.TestCase):
    def test_frame_ancestors_is_pinned(self):
        csp = dict(serve.MODULE_UI_HEADERS)['Content-Security-Policy']
        self.assertEqual(csp, "sandbox allow-scripts allow-forms; default-src 'self' 'unsafe-inline' data:; connect-src 'none'; "
                              "frame-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'self'")


if __name__ == '__main__':
    unittest.main()
