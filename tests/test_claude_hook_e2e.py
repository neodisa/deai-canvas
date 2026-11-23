"""Наскрізно (23.11.2026): рядок команди з «Підключити» запускається через `sh -c` з підробленим JSON сесії Claude Code на stdin
проти тестового сервера в процесі (порт 0). Хук тихий за будь-яких обставин: порожній stdout/stderr і код 0. Лише loopback; справжні
`~/.deai`, `~/.claude` і порт 8765 не чіпаються."""
import json
import os
import shutil
import socket
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import claude_hook  # noqa: E402
import serve  # noqa: E402,F401
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402

_REAL = None
CURL = shutil.which('curl')


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _git(d, *args):
    return subprocess.run(['git', *args], cwd=d, capture_output=True, text=True).stdout


@unittest.skipUnless(CURL and shutil.which('sh') and shutil.which('git'), 'потрібні sh, curl і git')
class HookEndToEnd(base.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['DEAI_HOME'] = cls.deai          # стенд уже ізолює; присвоєння — для охоронця test_serve
        os.environ['DEAI_NO_UPDATE_CHECK'] = '1'
        cls.addClassCleanup(os.environ.pop, 'DEAI_NO_UPDATE_CHECK', None)
        patcher = mock.patch.dict(os.environ, {'GIT_AUTHOR_NAME': 'Lead', 'GIT_AUTHOR_EMAIL': 'lead@example.com',
                                               'GIT_COMMITTER_NAME': 'Lead', 'GIT_COMMITTER_EMAIL': 'lead@example.com'})
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        # герметичність git: жодних чужих GIT_*/глобальних конфігів (дочірній `sh -c` успадкує це оточення)
        for k in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG_GLOBAL', 'XDG_CONFIG_HOME'):
            os.environ.pop(k, None)
        hermetic = mock.patch.dict(os.environ, {'GIT_CONFIG_NOSYSTEM': '1'})
        hermetic.start()
        cls.addClassCleanup(hermetic.stop)

    def setUp(self):
        super().setUp()
        shutil.rmtree(self.x_dir, ignore_errors=True)
        base._task_dir(self.x_dir, 'x')
        st, _ = self.post('/api/iteration', {'from': 'it1', 'note': 'Друга'}, {'X-Canvas-Task': 'x'})     # it2 + git init + коміт
        self.assertEqual(st, 200)
        shutil.rmtree(os.path.join(self.p_path, '.claude'), ignore_errors=True)
        for name in ('CLAUDE.md', 'AGENTS.md'):
            p = os.path.join(self.p_path, name)
            if os.path.lexists(p):
                os.remove(p)
        # хук ставимо справжньою кнопкою, а команду беремо з файла, який вона записала
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['hook']['state']), (200, 'ok'))
        with open(os.path.join(self.p_path, '.claude', 'settings.local.json'), encoding='utf-8') as f:
            self.cmd = json.load(f)['hooks']['Stop'][0]['hooks'][0]['command']
        self.assertEqual(self.cmd, claude_hook.command(self.port))
        # шпигуни: усе, чим сервер відповів через `_send_json`/`_refuse_unread`, і чи викликався обробник `_autosync`
        self.sent, self.refused = [], []
        orig_send, orig_refuse = serve.Handler._send_json, serve.Handler._refuse_unread

        def send(h, obj, status=200):
            self.sent.append((status, obj))
            return orig_send(h, obj, status)

        def refuse(h, status, code, error):
            self.refused.append((status, code))
            return orig_refuse(h, status, code, error)
        for name, fn in (('_send_json', send), ('_refuse_unread', refuse)):
            patcher = mock.patch.object(serve.Handler, name, autospec=True, side_effect=fn)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(serve.Handler, '_autosync', autospec=True, side_effect=serve.Handler._autosync)
        self.autosync_spy = patcher.start()
        self.addCleanup(patcher.stop)

    def count(self, d=None):
        return int(_git(d or self.x_dir, 'rev-list', '--count', 'HEAD').strip())

    def head(self, d=None):
        return _git(d or self.x_dir, 'rev-parse', 'HEAD').strip()

    def porcelain(self):
        return _git(self.x_dir, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/')

    def hook_reply(self):
        """Остання JSON-відповідь `/api/autosync` із шпигуна (виклик хука — єдиний автосинк у тесті)."""
        replies = [o for st, o in self.sent if isinstance(o, dict) and 'reason' in o]
        self.assertTrue(replies, 'сервер не відповів на автосинк')
        return replies[-1]

    def run_hook(self, cmd, stdin):
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}     # loopback — без проксі оточення
        env['HOME'] = self.home                                                              # дочірні sh/curl/git — лише тимчасовий HOME
        return subprocess.run(['sh', '-c', cmd], input=stdin, capture_output=True, text=True, env=env, timeout=30, cwd=self.tmp)

    def session(self, **extra):
        return json.dumps({'session_id': 's-1', 'transcript_path': '/t/x.jsonl', 'cwd': self.p_path, 'hook_event_name': 'Stop',
                           'stop_hook_active': False, 'last_assistant_message': 'готово', **extra})

    def dirty(self):
        with open(os.path.join(self.x_dir, 'iterations', 'it2', 'index.html'), 'a', encoding='utf-8') as f:
            f.write('<p>AI</p>')

    def test_a_dirty_own_iteration_becomes_an_ai_commit(self):
        self.dirty()
        head0, n0 = self.head(), self.count()
        self.sent.clear()
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertNotEqual(self.head(), head0)
        self.assertEqual(self.count(), n0 + 1)
        self.assertEqual(_git(self.x_dir, 'log', '-1', '--format=%s').strip(), 'it2: зміни AI')
        self.assertEqual(_git(self.x_dir, 'log', '-1', '--format=%(trailers:key=Deai-Actor,valueonly)').strip(), 'ai')
        files = [f for f in _git(self.x_dir, 'show', '--name-only', '--format=', 'HEAD').split('\n') if f]
        self.assertTrue(files and all(f.startswith('iterations/it2/') for f in files), files)
        self.assertEqual(self.porcelain(), '')
        self.assertIn('x', self.hook_reply()['ai_tasks'])

    def test_a_second_call_after_the_same_reply_is_safe(self):
        self.dirty()
        head0, n0 = self.head(), self.count()
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        head1 = self.head()
        self.assertNotEqual(head1, head0)
        self.assertEqual(self.count(), n0 + 1)
        self.assertEqual(_git(self.x_dir, 'log', '-1', '--format=%s').strip(), 'it2: зміни AI')
        status1 = self.porcelain()
        self.sent.clear()
        calls = self.autosync_spy.call_count
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertEqual(self.autosync_spy.call_count, calls + 1, 'другий виклик дійшов до сервера')
        reply = self.hook_reply()
        self.assertEqual(reply['ai_tasks'], {})
        self.assertIsNone(reply['ai'])
        self.assertEqual((self.head(), self.count(), self.porcelain()), (head1, n0 + 1, status1))

    def test_with_the_canvas_stopped_the_hook_is_silent_and_exits_zero(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))                      # звільняємо порт (bind без listen змусив би curl на macOS чекати весь --max-time)
            free = s.getsockname()[1]                     # порт, на якому ніхто не слухає
        r = self.run_hook(claude_hook.command(free), self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))

    def test_an_oversized_session_json_is_silent_and_commits_nothing_the_next_reply_does(self):
        self.dirty()
        head0, n0 = self.head(), self.count()
        big = self.session(last_assistant_message='x' * (3 * 1024 * 1024))      # фіксований розмір: зміна ліміту не роздуває тіло
        self.assertGreater(len(big), serve.AUTOSYNC_BODY_MAX)
        self.sent.clear()
        calls = self.autosync_spy.call_count
        r = self.run_hook(self.cmd, big)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertEqual(self.refused, [(413, 'body-too-large')])
        self.assertEqual(self.autosync_spy.call_count, calls, 'обробник не мав запускатися')
        self.assertEqual((self.head(), self.count()), (head0, n0))
        self.assertIn('iterations/it2/index.html', self.porcelain())
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.autosync_spy.call_count, calls + 1)
        self.assertEqual(self.count(), n0 + 1)
        self.assertEqual(_git(self.x_dir, 'log', '-1', '--format=%s').strip(), 'it2: зміни AI')

    def test_a_session_started_outside_every_space_does_nothing(self):
        self.dirty()
        before = {d: (os.path.exists(os.path.join(d, '.git')), self.head(d) if os.path.exists(os.path.join(d, '.git')) else None)
                  for d in (self.x_dir, os.path.join(self.p_path, 'nowhere'), self.a_dir)}   # усі задачі простору P + старий простір
        self.sent.clear()
        r = self.run_hook(self.cmd, self.session(cwd=self.tmp))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertEqual(self.hook_reply()['reason'], 'no-space')
        after = {d: (os.path.exists(os.path.join(d, '.git')), self.head(d) if os.path.exists(os.path.join(d, '.git')) else None)
                 for d in before}
        self.assertEqual(after, before)
        self.assertIn('iterations/it2/index.html', self.porcelain())


if __name__ == '__main__':
    unittest.main()
