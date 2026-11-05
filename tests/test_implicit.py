"""`app/implicit.py` (ядро неявного постачальника, 4d-2) і шов `spaces.effective_space()`.

Усе в тимчасових теках; справжні `~/.deai` і `tasks.json` не чіпаються, мережі нема."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import implicit  # noqa: E402
import spaces  # noqa: E402
import dashboard  # noqa: E402
import tracker  # noqa: E402
import notify  # noqa: E402

_ROLES = ('publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify')
_ENV = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TRACKER_FAKE', 'DC_TEAMS_FAKE', 'DEAI_HOME')


def _clean_env():
    """Оточення без змінних ізоляції/фейків: тест ставить лише те, що перевіряє."""
    return mock.patch.dict(os.environ, {}, clear=False)


class ImplicitCore(unittest.TestCase):
    def setUp(self):
        p = _clean_env()
        p.start()
        self.addCleanup(p.stop)
        for k in _ENV:
            os.environ.pop(k, None)

    def test_roles_order(self):
        self.assertEqual(implicit.IMPLICIT_ROLES, _ROLES)

    def test_singleton_and_immutable(self):
        for r in _ROLES:
            p = implicit.for_role(r)
            self.assertIs(p, implicit.for_role(r))
            self.assertEqual(p.role, r)
            with self.assertRaises(AttributeError):
                p.module_id = 'x'
            with self.assertRaises(AttributeError):
                p.extra = 1

    def test_table(self):
        want = {
            'publish': ('vercel-publish', True, None),
            'comments': ('supabase-comments', True, None),
            'vcs': ('git-sync', True, None),
            'dashboard': ('supabase-dashboard', True, 'DC_TEAM_FAKE'),
            'tracker': ('jira-tracker', True, 'DC_TRACKER_FAKE'),
            'notify': ('supabase-teams', True, 'DC_TEAMS_FAKE'),
        }
        for r, (mid, shared, fake) in want.items():
            p = implicit.for_role(r)
            self.assertEqual((p.module_id, p.shared, p.fake_env), (mid, shared, fake), r)

    def test_module_ids_match_real_code(self):
        """Таблиця не розходиться з тим, що реально беруть гілки 0.15.0."""
        import serve
        self.assertEqual(implicit.for_role('publish').module_id, serve.PUBLISH_LEGACY_MODULE)
        self.assertEqual(implicit.for_role('comments').module_id, serve.COMMENTS_MODULE)
        self.assertEqual(implicit.for_role('vcs').module_id, serve.VCS_MODULE)
        self.assertEqual(implicit.for_role('dashboard').module_id, dashboard.LEGACY_MODULE)
        self.assertEqual(implicit.for_role('tracker').module_id, tracker.LEGACY_MODULE)
        self.assertEqual(implicit.for_role('notify').module_id, notify.LEGACY_MODULE)

    def test_unknown_role(self):
        with self.assertRaises(KeyError):
            implicit.for_role('tokens')

    def test_isolated_truth_table(self):
        for tf in (None, '', '/x/tasks.json'):
            for no in (None, '', '1'):
                with mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop('DC_TASKS_FILE', None)
                    os.environ.pop('DC_NO_OVERVIEW', None)
                    if tf is not None:
                        os.environ['DC_TASKS_FILE'] = tf
                    if no is not None:
                        os.environ['DC_NO_OVERVIEW'] = no
                    self.assertEqual(implicit.isolated(), bool(tf) or bool(no), (tf, no))

    def test_route_fake_wins_even_isolated(self):
        p = implicit.for_role('dashboard')
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': '/tmp/fake.json', 'DC_TASKS_FILE': '/x/t.json'}):
            self.assertEqual(implicit.route(p), ('fake', '/tmp/fake.json'))

    def test_route_empty_fake_is_absent(self):
        p = implicit.for_role('dashboard')
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': '', 'DC_NO_OVERVIEW': '1'}):
            self.assertEqual(implicit.route(p), ('isolated', None))

    def test_route_isolated_and_live(self):
        for r in _ROLES:
            p = implicit.for_role(r)
            self.assertEqual(implicit.route(p), ('live', None), r)
            with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '/x/t.json'}):
                self.assertEqual(implicit.route(p), ('isolated', None), r)
            with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1'}):
                self.assertEqual(implicit.route(p), ('isolated', None), r)

    def test_route_not_shared_is_live_when_isolated(self):
        p = implicit.Implicit('x', 'm', False, None)
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '/x/t.json'}):
            self.assertEqual(implicit.route(p), ('live', None))

    def test_no_serve_import(self):
        with open(implicit.__file__, encoding='utf-8') as f:
            src = f.read()
        self.assertNotIn('import serve', src)
        self.assertNotIn('deai_modules', src)


class EffectiveSpace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = _clean_env()
        p.start()
        self.addCleanup(p.stop)
        for k in _ENV:
            os.environ.pop(k, None)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)

    def _no_registry(self):
        m = mock.patch.object(spaces, 'load_registry', side_effect=AssertionError('registry read'))
        calls = m.start()
        self.addCleanup(m.stop)
        return calls

    def test_layer_off_returns_copy_without_registry(self):
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp.name, 'tasks.json')
        lr = self._no_registry()
        self.assertFalse(spaces.layer_on())
        sp = spaces.effective_space()
        self.assertEqual(sp, spaces.IMPLICIT)
        self.assertIsNot(sp, spaces.IMPLICIT)
        sp['integrations'] = False
        self.assertIs(spaces.IMPLICIT['integrations'], True)
        lr.assert_not_called()

    def test_layer_off_with_fixed_space_still_implicit(self):
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp.name, 'tasks.json')
        self._no_registry()
        with spaces.request_space('whatever'):
            self.assertEqual(spaces.effective_space(), spaces.IMPLICIT)

    def test_layer_on_unfixed_returns_copy_without_registry(self):
        os.environ['DEAI_HOME'] = os.path.join(self.tmp.name, 'deai')
        lr = self._no_registry()
        self.assertTrue(spaces.layer_on())
        self.assertIsNone(spaces.request_space_id())
        sp = spaces.effective_space()
        self.assertEqual(sp, spaces.IMPLICIT)
        self.assertIsNot(sp, spaces.IMPLICIT)
        sp['id'] = 'changed'
        self.assertEqual(spaces.IMPLICIT['id'], 'legacy')
        lr.assert_not_called()

    def test_layer_on_fixed_is_active_space(self):
        os.environ['DEAI_HOME'] = os.path.join(self.tmp.name, 'deai')
        with spaces.request_space(''):
            self.assertIsNone(spaces.effective_space())
            self.assertIsNone(spaces.active_space())
        sentinel = {'id': 'alpha', 'path': self.tmp.name}
        with mock.patch.object(spaces, 'active_space', return_value=sentinel):
            with spaces.request_space('alpha'):
                self.assertIs(spaces.effective_space(), sentinel)


if __name__ == '__main__':
    unittest.main()
