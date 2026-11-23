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


@unittest.skipUnless(CURL and shutil.which('sh'), 'потрібні sh і curl')
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
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertEqual(_git(self.x_dir, 'log', '-1', '--format=%s').strip(), 'it2: зміни AI')
        self.assertIn('Deai-Actor: ai', _git(self.x_dir, 'log', '-1', '--format=%b'))
        self.assertEqual(_git(self.x_dir, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/'), '')

    def test_a_second_call_after_the_same_reply_is_safe(self):
        self.dirty()
        self.run_hook(self.cmd, self.session())
        head = _git(self.x_dir, 'rev-parse', 'HEAD')
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertEqual(_git(self.x_dir, 'rev-parse', 'HEAD'), head)

    def test_with_the_canvas_stopped_the_hook_is_silent_and_exits_zero(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            free = s.getsockname()[1]                     # порт, на якому ніхто не слухає
        r = self.run_hook(claude_hook.command(free), self.session())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))

    def test_an_oversized_session_json_is_silent_and_commits_nothing_the_next_reply_does(self):
        self.dirty()
        big = self.session(last_assistant_message='x' * (serve.AUTOSYNC_BODY_MAX + 1024))
        r = self.run_hook(self.cmd, big)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertIn('iterations/it2/index.html', _git(self.x_dir, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/'))
        r = self.run_hook(self.cmd, self.session())
        self.assertEqual(r.returncode, 0)
        self.assertEqual(_git(self.x_dir, 'log', '-1', '--format=%s').strip(), 'it2: зміни AI')

    def test_a_session_started_outside_every_space_does_nothing(self):
        self.dirty()
        r = self.run_hook(self.cmd, self.session(cwd=self.tmp))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        self.assertIn('iterations/it2/index.html', _git(self.x_dir, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/'))


if __name__ == '__main__':
    unittest.main()
