"""`POST /api/autosync` за шляхом (23.11.2026): без задачі в запиті й з абсолютним `cwd` у тілі простір знаходиться за префіксом,
і КОЖНА його задача з `.git` фіксує свої брудні власні ітерації як `itN: зміни AI`. Заголовок/префікс задачі важать більше за `cwd`.
З тіла сервер бере лише `cwd`. Усе — у тимчасових `HOME`/`DEAI_HOME`; мережі й справжніх конфігів нема (простір `P` без ролі `vcs`)."""
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402

_REAL = None
MARK = 'SECRET-REPLY-7f3a91'


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _git(d, *args):
    return subprocess.run(['git', *args], cwd=d, capture_output=True, text=True).stdout


class AutosyncByPath(base.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['DEAI_HOME'] = cls.deai          # стенд уже ізолює; присвоєння — для охоронця test_serve
        patcher = mock.patch.dict(os.environ, {'GIT_AUTHOR_NAME': 'Lead', 'GIT_AUTHOR_EMAIL': 'lead@example.com',
                                               'GIT_COMMITTER_NAME': 'Lead', 'GIT_COMMITTER_EMAIL': 'lead@example.com'})
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.y_dir = os.path.join(cls.p_path, 'y')
        cls.bare_dir = os.path.join(cls.p_path, 'bare')
        cfg = base._read(cls.p_file)
        cfg['tasks']['y'] = {'title': 'Ігрек', 'dir': cls.y_dir, 'track': 'tool'}
        cfg['tasks']['bare'] = {'title': 'Без git', 'dir': cls.bare_dir, 'track': 'tool'}
        base._write(cls.p_file, cfg)

    def setUp(self):
        super().setUp()
        for tid, d in (('x', self.x_dir), ('y', self.y_dir)):
            shutil.rmtree(d, ignore_errors=True)
            base._task_dir(d, tid)
            st, _ = self.post('/api/iteration', {'from': 'it1', 'note': 'Друга'}, {'X-Canvas-Task': tid})   # it2 + git init + коміт
            self.assertEqual(st, 200)
        shutil.rmtree(self.bare_dir, ignore_errors=True)
        base._task_dir(self.bare_dir, 'bare')

    def dirty(self, d, it='it2', text='<p>AI</p>'):
        with open(os.path.join(d, 'iterations', it, 'index.html'), 'a', encoding='utf-8') as f:
            f.write(text)

    def status(self, d):
        return _git(d, 'status', '--porcelain', '--untracked-files=all', '--', 'iterations/')    # iterations.json після `/api/iteration` лишається брудним: не ітерація

    def subject(self, d):
        return _git(d, 'log', '-1', '--format=%s').strip()

    # ---- простір за cwd

    def test_cwd_in_the_space_commits_every_task_with_git(self):
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        self.dirty(self.bare_dir, 'it1')
        st, body = self.post('/api/autosync', {'cwd': self.p_path})        # машина «стоїть» на старому просторі: простір — за шляхом
        self.assertEqual((st, body['reason']), (200, 'no-gitlab'))
        self.assertEqual(sorted(body['ai_tasks']), ['x', 'y'])
        for tid in ('x', 'y'):
            self.assertEqual(body['ai_tasks'][tid]['its'], ['it2'])
            self.assertEqual(body['ai_tasks'][tid]['it'], 'it2')
        self.assertEqual(body['ai'], body['ai_tasks']['x'], '`ai` — результат поточної задачі простору (x)')
        for d in (self.x_dir, self.y_dir):
            self.assertEqual(self.subject(d), 'it2: зміни AI')
            self.assertIn('Deai-Actor: ai', _git(d, 'log', '-1', '--format=%b'))
            self.assertEqual(self.status(d), '')
        self.assertFalse(os.path.exists(os.path.join(self.bare_dir, '.git')), 'задача без git лишається без репо')
        self.assertFalse(os.path.exists(os.path.join(self.a_dir, '.git')), 'інші простори не зачеплено')

    def test_cwd_deeper_in_a_task_folder_finds_the_space(self):
        self.dirty(self.y_dir)
        st, body = self.post('/api/autosync', {'cwd': os.path.join(self.x_dir, 'iterations', 'it2')})
        self.assertEqual((st, sorted(body['ai_tasks'])), (200, ['y']))

    def test_only_tasks_with_something_to_commit_are_listed(self):
        self.dirty(self.y_dir)
        st, body = self.post('/api/autosync', {'cwd': self.p_path})
        self.assertEqual((st, sorted(body['ai_tasks']), body['ai']), (200, ['y'], None))     # поточна — x, там чисто

    def test_nothing_dirty_gives_an_empty_map(self):
        st, body = self.post('/api/autosync', {'cwd': self.p_path})
        self.assertEqual((st, body['ai_tasks'], body['ai']), (200, {}, None))
        self.assertEqual(self.status(self.x_dir) + self.status(self.y_dir), '')

    def test_ai_is_the_current_task_of_that_space(self):
        self.restore_bytes(self.p_file)
        cfg = base._read(self.p_file)
        cfg['current'] = 'y'
        base._write(self.p_file, cfg)
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        st, body = self.post('/api/autosync', {'cwd': self.p_path})
        self.assertEqual(body['ai'], body['ai_tasks']['y'])

    def test_a_failing_task_does_not_stop_the_others_and_the_log_is_clean(self):
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        real = serve.ai_commit

        def flaky(task):
            if task['dir'] == self.x_dir:
                raise RuntimeError('boom')
            return real(task)
        err = io.StringIO()
        with mock.patch.object(serve, 'ai_commit', flaky), mock.patch.object(sys, 'stderr', err):
            st, body = self.post('/api/autosync', {'cwd': self.p_path, 'last_assistant_message': MARK * 40, 'session_id': MARK})
        self.assertEqual(st, 200)
        self.assertEqual(sorted(body['ai_tasks']), ['y'])
        self.assertIsNone(body['ai'])                                   # поточна x — збій
        self.assertIn("autosync: ai-commit 'x'", err.getvalue())
        self.assertIn('RuntimeError', err.getvalue())
        self.assertNotIn(MARK, err.getvalue())
        self.assertEqual(self.subject(self.y_dir), 'it2: зміни AI')

    # ---- пріоритети

    def test_a_task_header_beats_cwd(self):
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        st, body = self.post('/api/autosync', {'cwd': self.p_path}, {'X-Canvas-Task': 'x'})
        self.assertEqual(st, 200)
        self.assertNotIn('ai_tasks', body, 'названа задача — режим як у 0.36.0')
        self.assertEqual(body['ai']['it'], 'it2')
        self.assertEqual(self.status(self.x_dir), '')
        self.assertIn('iterations/it2/index.html', self.status(self.y_dir), 'y не чіпали')

    def test_the_task_prefix_beats_cwd_and_a_no_space_cwd(self):
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        st, body = self.post('/t/y/api/autosync', {'cwd': self.tmp})       # cwd поза просторами, але задачу названо
        self.assertEqual(st, 200)
        self.assertNotIn('ai_tasks', body)
        self.assertEqual(body['ai']['it'], 'it2')
        self.assertEqual(self.status(self.y_dir), '')
        self.assertIn('iterations/it2/index.html', self.status(self.x_dir))

    def test_without_cwd_it_is_the_current_task_of_the_machine(self):
        spaces.switch_space(self.p_id)
        self.dirty(self.x_dir)
        self.dirty(self.y_dir)
        for payload in ({}, {'cwd': 5}, {'cwd': ''}, {'session_id': 's'}):
            with self.subTest(payload=payload):
                st, body = self.post('/api/autosync', payload)
                self.assertEqual(st, 200)
                self.assertNotIn('ai_tasks', body)
        self.assertEqual(self.status(self.x_dir), '')
        self.assertIn('iterations/it2/index.html', self.status(self.y_dir), 'поточна машини — x; y не чіпали')

    # ---- no-space, no-task

    def test_cwd_outside_every_space_is_no_space_and_nothing_runs(self):
        self.dirty(self.x_dir)
        for cwd in (self.tmp, 'relative/path', '/'):
            with self.subTest(cwd=cwd):
                st, body = self.post('/api/autosync', {'cwd': cwd})
                self.assertEqual((st, body), (200, {'ok': True, 'changed': False, 'reason': 'no-space', 'ai': None}))
        self.assertIn('iterations/it2/index.html', self.status(self.x_dir))

    def test_a_space_without_a_current_task_is_no_task(self):
        st, body = self.post('/api/autosync', {'cwd': self.e_path})
        self.assertEqual((st, body), (200, {'ok': True, 'changed': False, 'reason': 'no-task', 'ai': None, 'ai_tasks': {}}))

    # ---- ліміт тіла й приватність

    def test_the_body_cap_is_two_mebibytes(self):
        self.assertEqual(serve.AUTOSYNC_BODY_MAX, 2 * 1024 * 1024)

    def test_a_body_over_the_cap_is_413_before_reading_and_nothing_runs(self):
        self.dirty(self.x_dir)
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.putrequest('POST', '/api/autosync')
            conn.putheader('Content-Type', 'application/json')
            conn.putheader('Content-Length', str(10 * 1024 * 1024))
            conn.endheaders()                                           # тіло НЕ шлемо: відмова мусить прийти до читання
            r = conn.getresponse()
            got = json.loads(r.read().decode('utf-8'))
        finally:
            conn.close()
        self.assertEqual((r.status, got['code'], got['ok']), (413, 'body-too-large', False))
        self.assertIn('iterations/it2/index.html', self.status(self.x_dir))

    def test_a_body_within_the_cap_is_processed(self):
        self.dirty(self.x_dir)
        with mock.patch.object(serve, 'AUTOSYNC_BODY_MAX', 4096):
            st, body = self.post('/api/autosync', {'cwd': self.p_path, 'pad': 'x' * 3000})
            self.assertEqual((st, sorted(body['ai_tasks'])), (200, ['x']))
            st, got = self.post('/api/autosync', {'cwd': self.p_path, 'pad': 'x' * 5000})
            self.assertEqual((st, got['code']), (413, 'body-too-large'))

    def test_the_other_fields_of_the_body_never_reach_the_log_or_the_answer(self):
        self.dirty(self.x_dir)
        err = io.StringIO()
        payload = {'cwd': self.p_path, 'session_id': MARK + '-s', 'transcript_path': '/t/' + MARK,
                   'hook_event_name': 'Stop', 'stop_hook_active': False, 'last_assistant_message': MARK * 50}
        with mock.patch.object(sys, 'stderr', err):
            st, body = self.post('/api/autosync', payload)
        self.assertEqual(st, 200)
        self.assertNotIn(MARK, err.getvalue())
        self.assertNotIn(MARK, json.dumps(body))

    def test_a_foreign_origin_is_refused_and_nothing_runs(self):
        self.dirty(self.x_dir)
        st, body = self.post('/api/autosync', {'cwd': self.p_path}, {'Origin': 'http://evil.example'})
        self.assertEqual((st, body), (403, {'ok': False, 'error': 'foreign origin'}))
        self.assertIn('iterations/it2/index.html', self.status(self.x_dir))


if __name__ == '__main__':
    unittest.main()
