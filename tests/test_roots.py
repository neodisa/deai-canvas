"""Три корені по напрямках (вимога 31.08.2026) — розкладка і переїзд.

Тести ганяють справжню файлову систему у тимчасовій теці: переїзд — це рух
реальних тек, і мок тут перевіряв би не те.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))


class Roots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='dc-roots-')
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp, 'tasks.json')
        import serve
        import roots
        self.serve, self.roots = serve, roots

    def tearDown(self):
        os.environ.pop('DC_TASKS_FILE', None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cfg(self, tasks, roots=None, single=None):
        cfg = {'current': next(iter(tasks), ''), 'tasks': tasks}
        if roots is not None:
            cfg['design_work_roots'] = roots
        if single is not None:
            cfg['design_work_root'] = single
        with open(os.environ['DC_TASKS_FILE'], 'w', encoding='utf-8') as fh:
            json.dump(cfg, fh, ensure_ascii=False)
        return cfg

    # ---- work_root ----
    def test_profile_root_wins_over_shared(self):
        cfg = self._cfg({}, roots={'seo': '/r/seo'}, single='/r/united')
        self.assertEqual(self.serve.work_root(cfg, 'seo'), '/r/seo')

    def test_profile_without_own_root_falls_back_not_invents(self):
        """Свого кореня нема — беремо спільний, а не вигадуємо шлях за назвою."""
        cfg = self._cfg({}, roots={'seo': '/r/seo'}, single='/r/united')
        self.assertEqual(self.serve.work_root(cfg, 'liga360'), '/r/united')

    def test_tilde_is_expanded(self):
        cfg = self._cfg({}, roots={'seo': '~/x/seo'})
        self.assertTrue(self.serve.work_root(cfg, 'seo').startswith(os.path.expanduser('~')))

    # ---- план переїзду ----
    def test_task_in_foreign_root_is_planned_to_move(self):
        """Той самий випадок із фідбеку: SEO-задача лежить у теці United."""
        cfg = self._cfg({'blog': {'profile': 'seo', 'dir': os.path.join(self.tmp, 'united', 'blog')}},
                        roots={'seo': os.path.join(self.tmp, 'seo')})
        os.makedirs(cfg['tasks']['blog']['dir'])
        (tid, profile, cur, want, stop), = self.roots.plan(cfg)
        self.assertEqual((tid, profile, stop), ('blog', 'seo', None))
        self.assertEqual(want, os.path.join(self.tmp, 'seo', 'blog'))

    def test_task_already_home_is_not_planned(self):
        home = os.path.join(self.tmp, 'seo', 'blog')
        os.makedirs(home)
        cfg = self._cfg({'blog': {'profile': 'seo', 'dir': home}},
                        roots={'seo': os.path.join(self.tmp, 'seo')})
        self.assertEqual(self.roots.plan(cfg), [])

    def test_existing_target_stops_the_move_loudly(self):
        """Ціль зайнята — це стоп із причиною, а не мовчазний пропуск і не
        затирання чужої теки."""
        cur = os.path.join(self.tmp, 'united', 'blog')
        os.makedirs(cur)
        os.makedirs(os.path.join(self.tmp, 'seo', 'blog'))
        cfg = self._cfg({'blog': {'profile': 'seo', 'dir': cur}},
                        roots={'seo': os.path.join(self.tmp, 'seo')})
        self.assertIn('ціль уже існує', self.roots.plan(cfg)[0][4])

    def test_missing_dir_is_reported_not_skipped(self):
        cfg = self._cfg({'blog': {'profile': 'seo', 'dir': os.path.join(self.tmp, 'нема')}},
                        roots={'seo': os.path.join(self.tmp, 'seo')})
        self.assertIn('теки нема', self.roots.plan(cfg)[0][4])

    # ---- сам переїзд ----
    def test_dry_run_moves_nothing(self):
        cur = os.path.join(self.tmp, 'united', 'blog')
        os.makedirs(cur)
        cfg = self._cfg({'blog': {'profile': 'seo', 'dir': cur}},
                        roots={'seo': os.path.join(self.tmp, 'seo')})
        self.roots.cmd_migrate(cfg, apply=False)
        self.assertTrue(os.path.isdir(cur), 'сухий прогін не має рухати теки')

    def test_apply_moves_folder_and_rewrites_dir(self):
        cur = os.path.join(self.tmp, 'united', 'blog')
        os.makedirs(os.path.join(cur, 'iterations', 'it1'))
        with open(os.path.join(cur, 'iterations', 'it1', 'index.html'), 'w') as fh:
            fh.write('<h1>макет</h1>')
        cfg = self._cfg({'blog': {'profile': 'seo', 'dir': cur}},
                        roots={'seo': os.path.join(self.tmp, 'seo')})
        self.roots.cmd_migrate(cfg, apply=True)

        want = os.path.join(self.tmp, 'seo', 'blog')
        self.assertFalse(os.path.exists(cur))
        self.assertTrue(os.path.isfile(os.path.join(want, 'iterations', 'it1', 'index.html')),
                        'макет мусить переїхати цілим')
        with open(os.environ['DC_TASKS_FILE'], encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['tasks']['blog']['dir'], want)

    def test_apply_does_not_touch_a_task_of_the_root_owner_profile(self):
        """Сусідня задача свого напрямку лишається на місці — переїзд адресний."""
        united = os.path.join(self.tmp, 'united')
        os.makedirs(os.path.join(united, 'widget'))
        os.makedirs(os.path.join(united, 'blog'))
        cfg = self._cfg({'widget': {'profile': 'united', 'dir': os.path.join(united, 'widget')},
                         'blog': {'profile': 'seo', 'dir': os.path.join(united, 'blog')}},
                        roots={'seo': os.path.join(self.tmp, 'seo'),
                               'united': united})
        self.roots.cmd_migrate(cfg, apply=True)
        self.assertTrue(os.path.isdir(os.path.join(united, 'widget')))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, 'seo', 'blog')))


if __name__ == '__main__':
    unittest.main()
