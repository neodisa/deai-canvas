"""«Перший запуск» (0.33.0): CLAUDE.md через API — `GET|POST /api/agents-md` (`claude`), новий простір і «Створити» AGENTS.md."""
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
sys.path.insert(0, HERE)
import serve  # noqa: E402,F401
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _get(p):
    with open(p, 'rb') as f:
        return f.read()


def _put(p, b):
    with open(p, 'wb') as f:
        f.write(b)


class ClaudeRoutes(base.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['DEAI_NO_UPDATE_CHECK'] = '1'
        cls.addClassCleanup(os.environ.pop, 'DEAI_NO_UPDATE_CHECK', None)

    def setUp(self):
        super().setUp()
        self.agents = os.path.join(self.p_path, 'AGENTS.md')
        self.claude = os.path.join(self.p_path, 'CLAUDE.md')
        self.addCleanup(self._clear)
        self._clear()

    def _clear(self):
        for p in (self.agents, self.claude):
            if os.path.isdir(p) and not os.path.islink(p):
                os.rmdir(p)
            elif os.path.lexists(p):
                os.remove(p)

    def test_get_reports_claude_and_writes_nothing(self):
        st, body = self.jget(f'/api/agents-md?space={self.p_id}')
        self.assertEqual(st, 200)
        self.assertEqual(body['claude'], {'state': 'missing', 'path': self.claude})
        self.assertFalse(os.path.lexists(self.claude))

    def test_create_agents_md_also_creates_claude_md(self):
        st, body = self.post('/api/agents-md', {'space': self.p_id})
        self.assertEqual((st, body['exists'], body['claude']['state']), (200, True, 'ok'))
        self.assertEqual(_get(self.claude), b'@AGENTS.md\n')

    def test_create_keeps_an_existing_claude_md_untouched(self):
        _put(self.claude, b'# team rules\n')
        st, body = self.post('/api/agents-md', {'space': self.p_id})
        self.assertEqual((st, body['claude']['state']), (200, 'no-import'))
        self.assertEqual(_get(self.claude), b'# team rules\n')

    def test_update_does_not_create_claude_md(self):
        self.post('/api/agents-md', {'space': self.p_id})
        os.remove(self.claude)
        st, body = self.post('/api/agents-md', {'space': self.p_id})      # оновлення наявного AGENTS.md
        self.assertEqual((st, body['claude']['state']), (200, 'missing'))
        self.assertFalse(os.path.lexists(self.claude))

    def test_post_claude_true_prepends_the_import(self):
        _put(self.claude, b'# team rules\n')
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['claude']['state']), (200, 'ok'))
        self.assertEqual(_get(self.claude), b'@AGENTS.md\n\n# team rules\n')
        self.assertFalse(os.path.lexists(self.agents), '«Підключити» не створює AGENTS.md')

    def test_post_claude_true_creates_a_missing_file(self):
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['claude']['state']), (200, 'ok'))
        self.assertEqual(_get(self.claude), b'@AGENTS.md\n')

    def test_post_claude_true_on_a_folder_gives_503_unreadable(self):
        os.mkdir(self.claude)
        st, body = self.post('/api/agents-md', {'space': self.p_id, 'claude': True})
        self.assertEqual((st, body['code']), (503, 'unreadable'))
        self.assertTrue(os.path.isdir(self.claude))

    def test_new_space_gets_claude_md(self):
        path = os.path.join(self.home, 'deai-work', 'claude-new')
        self.addCleanup(shutil.rmtree, path, True)
        st, body = self.post('/api/space-new', {'name': 'Claude New', 'color': 'space-4', 'path': path})
        self.assertEqual(st, 200, body)
        self.assertEqual(_get(os.path.join(path, 'CLAUDE.md')), b'@AGENTS.md\n')
        self.assertTrue(os.path.isfile(os.path.join(path, 'AGENTS.md')))


if __name__ == '__main__':
    unittest.main()
