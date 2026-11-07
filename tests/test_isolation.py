import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import isolation  # noqa: E402

ENVS = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TRACKER_FAKE', 'DC_TEAMS_FAKE')


class IsolationCore(unittest.TestCase):
    """Закон ізоляції й шви тестів (раніше `ImplicitCore`): `isolated`, `route`, таблиця `FAKE_ENV`, `real_home`."""

    def setUp(self):
        e = mock.patch.dict(os.environ, {})
        e.start()
        self.addCleanup(e.stop)
        for k in ENVS:
            os.environ.pop(k, None)

    def test_imports_nothing_but_os(self):
        """Чистий модуль: цикл імпорту з `spaces`/`serve`/`deai_modules` неможливий."""
        import ast
        with open(isolation.__file__.replace('.pyc', '.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(mods, {'os', 'pwd'})

    def test_fake_env_table_is_the_old_one(self):
        self.assertEqual(isolation.FAKE_ENV, {'dashboard': 'DC_TEAM_FAKE', 'tracker': 'DC_TRACKER_FAKE', 'notify': 'DC_TEAMS_FAKE'})

    def test_isolated_is_tasks_file_or_no_overview(self):
        self.assertFalse(isolation.isolated())
        for k in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
            with mock.patch.dict(os.environ, {k: '1'}):
                self.assertTrue(isolation.isolated(), k)
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': 'x'}):
            self.assertFalse(isolation.isolated())                 # шов сам по собі не робить прогін ізольованим

    def test_route_order_fake_then_isolated_then_live(self):
        self.assertEqual(isolation.route('dashboard'), ('live', None))
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '1'}):
            self.assertEqual(isolation.route('dashboard'), ('isolated', None))
            with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': '/tmp/fake.json'}):
                self.assertEqual(isolation.route('dashboard'), ('fake', '/tmp/fake.json'))   # шов раніше за ізоляцію

    def test_an_empty_seam_is_absent(self):
        """Порожнє значення шва (`DC_TEAM_FAKE=`) — як відсутнє: ні шва, ні ізоляції не вмикає."""
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': ''}):
            self.assertEqual(isolation.route('dashboard'), ('live', None))
            with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '1'}):
                self.assertEqual(isolation.route('dashboard'), ('isolated', None))

    def test_each_role_uses_its_own_seam(self):
        for role, env in isolation.FAKE_ENV.items():
            with mock.patch.dict(os.environ, {env: '/tmp/x.json'}):
                self.assertEqual(isolation.route(role), ('fake', '/tmp/x.json'), role)
                for other in set(isolation.FAKE_ENV) - {role}:
                    self.assertEqual(isolation.route(other), ('live', None), (role, other))

    def test_roles_without_a_seam_are_only_isolated_or_live(self):
        for role in ('comments', 'vcs', 'publish', 'tokens'):
            self.assertEqual(isolation.route(role), ('live', None))
            with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1', 'DC_TEAM_FAKE': '/tmp/x.json'}):
                self.assertEqual(isolation.route(role), ('isolated', None), role)

    def test_real_home_is_the_pwd_home_not_the_HOME_variable(self):
        import pwd
        real = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, '.deai')
        self.assertTrue(isolation.real_home(real))
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {'HOME': t}):          # тест підміняє HOME, але не пароль ОС
                self.assertFalse(isolation.real_home(os.path.join(t, '.deai')))
                self.assertFalse(isolation.real_home(t))
                self.assertTrue(isolation.real_home(real))

    def test_real_home_follows_symlinks(self):
        import pwd
        real = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, '.deai')
        with tempfile.TemporaryDirectory() as t:
            link = os.path.join(t, 'link')
            os.symlink(real, link)
            self.assertTrue(isolation.real_home(link))

    def test_real_home_unknown_os_home_is_real(self):
        """Безпечніший бік: не вдалось дізнатись дім ОС — вважаємо справжнім (облікових із цієї теки не беремо)."""
        with mock.patch('pwd.getpwuid', side_effect=KeyError('x')):
            self.assertTrue(isolation.real_home('/anything'))

    def test_real_home_garbage_is_real(self):
        self.assertTrue(isolation.real_home(None))

    def _fake_os_home(self, t):
        """Дім ОС (`pwd`) = тимчасова тека `t` з готовою `.deai`."""
        os.mkdir(os.path.join(t, '.deai'))
        return mock.patch('pwd.getpwuid', return_value=mock.Mock(pw_dir=t))

    def test_real_home_asks_samefile_when_realpath_differs(self):
        """I1 (ревʼю Task 10): на macOS `realpath` не є перевіркою тотожності (регістр, firmlink `/System/Volumes/Data`) — `samefile`
        ловить те, що `realpath` пропустив. Без цього Д6 відкривалась би."""
        with tempfile.TemporaryDirectory() as t, self._fake_os_home(t):
            other = os.path.join(t, 'elsewhere')
            os.mkdir(other)
            self.assertFalse(isolation.real_home(other))
            with mock.patch('os.path.samefile', return_value=True):
                self.assertTrue(isolation.real_home(other))
            with mock.patch('os.path.samefile', side_effect=OSError('gone')):
                self.assertFalse(isolation.real_home(other))        # теки нема — лишається результат `realpath`

    def test_real_home_case_variant_on_a_case_insensitive_fs(self):
        with tempfile.TemporaryDirectory() as t, self._fake_os_home(t):
            variant = os.path.join(t, '.DEAI')
            if not os.path.exists(variant):
                self.skipTest('ФС чутлива до регістру: варіанта `.DEAI` не існує')
            self.assertNotEqual(os.path.realpath(variant), os.path.realpath(os.path.join(t, '.deai')))
            self.assertTrue(isolation.real_home(variant))

    def test_real_home_without_pwd_uses_userprofile_not_home(self):
        """m5: без `pwd` (Windows) дім ОС — `USERPROFILE`, а не `HOME`, який підміняє тест; не вдалось — справжній."""
        with tempfile.TemporaryDirectory() as prof, tempfile.TemporaryDirectory() as fake_home:
            os.mkdir(os.path.join(prof, '.deai'))
            with mock.patch.dict(sys.modules, {'pwd': None}), mock.patch.dict(os.environ, {'USERPROFILE': prof, 'HOME': fake_home}):
                self.assertTrue(isolation.real_home(os.path.join(prof, '.deai')))
                self.assertFalse(isolation.real_home(os.path.join(fake_home, '.deai')))
            env = {k: v for k, v in os.environ.items() if k != 'USERPROFILE'}
            with mock.patch.dict(sys.modules, {'pwd': None}), mock.patch.dict(os.environ, env, clear=True):
                self.assertTrue(isolation.real_home(os.path.join(fake_home, '.deai')))   # дім ОС невідомий — fail-closed


if __name__ == '__main__':
    unittest.main()
