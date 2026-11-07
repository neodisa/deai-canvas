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
        return {'id': 'legacy', 'path': fx.space_dir, 'legacy': True, 'integrations': True}

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

    def test_overrides_disable_one_role(self):
        fx = liga_fixture.LigaFixture(self).env().build(overrides={'tracker': {'enabled': False}})
        st = {s['role']: s for s in liga_migrate.roles_state()}
        self.assertEqual((st['tracker']['on'], st['tracker']['reason']), (False, 'disabled'))
        self.assertTrue(st['notify']['on'])


if __name__ == '__main__':
    unittest.main()
