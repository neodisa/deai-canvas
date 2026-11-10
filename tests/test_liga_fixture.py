import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liga_fixture  # noqa: E402
import deai_modules  # noqa: E402
import liga_migrate  # noqa: E402


def _roles(space):
    return {r: (lambda p: p.id if isinstance(p, deai_modules.Module) else p)(deai_modules._provider_for(r, space)) for r in liga_fixture.ALL_ROLES}


class LigaFixtureBothWays(unittest.TestCase):
    """Обидва способи фікстури дають ОДНАКОВИХ постачальників і однакові ефективні налаштування/секрети; корінь без облікових."""

    def space(self, fx):
        return {'id': 'legacy', 'path': fx.space_dir, 'legacy': True}

    def test_build_makes_all_six_roles_explicit(self):
        fx = liga_fixture.LigaFixture(self).env().build()
        self.assertEqual(_roles(self.space(fx)), {r: liga_fixture.ROLE_RECORDS[r][0] for r in liga_fixture.ALL_ROLES})
        self.assertTrue(all(s['on'] for s in liga_migrate.roles_state()))
        with open(fx.tasks_path, encoding='utf-8') as f:
            root = json.load(f)
        self.assertEqual(sorted(root), ['registry', 'tasks'])

    def test_migrate_gives_the_same_roles_and_a_clean_root(self):
        fx = liga_fixture.LigaFixture(self).env()
        res = fx.migrate()
        self.assertEqual([r[1] for r in res], ['done', 'done', 'done', 'skip-nothing', 'done'], res)       # 4d-4a: у тестовому корені нема записів задач
        self.assertEqual(_roles(self.space(fx)), {r: liga_fixture.ROLE_RECORDS[r][0] for r in liga_fixture.ALL_ROLES})
        with open(fx.tasks_path, encoding='utf-8') as f:
            root = json.load(f)
        self.assertEqual(sorted(root), ['registry', 'tasks'])
        # `deai_modules.publish_password` з'явиться в Task 9–11; поки що перевіряємо сам секрет запису (його й читатиме функція)
        self.assertEqual(deai_modules._bucket(deai_modules._load_secrets(), 'legacy', 'vercel-publish').get('password'), liga_fixture.PASSWORD)
        self.assertTrue(all(s['on'] for s in liga_migrate.roles_state()))

    def test_key_file_option_creates_the_key_of_the_record_inside_the_temp_home_only_on_request(self):
        """Типово ключа нема (`SSH_KEY` веде в неіснуючий файл — поведінка наявних стендів); `key_file=True` кладе справжній файл у тимчасовий дім."""
        liga_fixture.LigaFixture(self).env().build(roles=('vcs',))
        self.assertFalse(os.path.exists(os.path.expanduser(liga_fixture.SSH_KEY)))
        fx2 = liga_fixture.LigaFixture(self).env().build(roles=('vcs',), key_file=True)
        key = os.path.expanduser(liga_fixture.SSH_KEY)
        self.assertTrue(os.path.isfile(key))
        self.assertTrue(key.startswith(fx2.home + os.sep), 'ключ мусить лежати в тимчасовому домі')

    def test_overrides_disable_one_role(self):
        fx = liga_fixture.LigaFixture(self).env().build(overrides={'tracker': {'enabled': False}})
        st = {s['role']: s for s in liga_migrate.roles_state()}
        self.assertEqual((st['tracker']['on'], st['tracker']['reason']), (False, 'disabled'))
        self.assertTrue(st['notify']['on'])


class WriteRecordsStandalone(unittest.TestCase):
    """`write_records` для стендів, що самі створюють реєстр: записи в `space.json` і секрети в бакеті `sid`; `fix_space` фіксує простір запиту."""

    def test_records_and_secrets_bucket(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            mods = liga_fixture.write_records(os.path.join(d, 'sp'), os.path.join(d, 'deai'), 'sid-7', roles=('tracker', 'vcs'), name='N')
            self.assertEqual(sorted(mods), ['git-sync', 'jira-tracker'])
            with open(os.path.join(d, 'sp', 'space.json'), encoding='utf-8') as f:
                sj = json.load(f)
            self.assertEqual((sj['name'], sorted(sj['modules'])), ('N', ['git-sync', 'jira-tracker']))
            with open(os.path.join(d, 'deai', 'secrets.json'), encoding='utf-8') as f:
                self.assertEqual(json.load(f), {'sid-7': {'jira-tracker': {'token': liga_fixture.JIRA_TOKEN}}})
            self.assertEqual(os.stat(os.path.join(d, 'deai', 'secrets.json')).st_mode & 0o777, 0o600)

    def test_fix_space_pins_the_request_space_and_cleans_up(self):
        import spaces

        class T(unittest.TestCase):
            def runTest(self):
                liga_fixture.LigaFixture(self).fix_space()
                self.seen = spaces.request_space_id()
        t = T()
        res = unittest.TestResult()
        t.run(res)
        self.assertEqual((t.seen, spaces.request_space_id()), ('legacy', None))


if __name__ == '__main__':
    unittest.main()
