"""Три корені по напрямках (вимога 31.08.2026) — розкладка і переїзд.

Тести ганяють справжню файлову систему у тимчасовій теці: переїзд — це рух
реальних тек, і мок тут перевіряв би не те.

4d-4a: корені — з ЯВНИХ напрямків простору (`space.json` → `serve._TrackView`, параметр `view` у `plan`/`roots_in_use`/
`cmd_migrate`), а не з `design_work_roots` старого файла; напрямок задачі — лише `track`. ⛔ `HOME` тимчасовий: `roots`
без кореня пише в `default_task_root(cfg)` = `~/deai-work`, і тест без підміни створив би теки у справжній домівці.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spaces_guard  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class Roots(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='dc-roots-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = mock.patch.dict(os.environ, {'HOME': self.tmp, 'DC_TASKS_FILE': os.path.join(self.tmp, 'tasks.json')})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DEAI_HOME', None)
        import roots
        import serve
        import tracks
        self.tracks, self.roots, self.serve = tracks, roots, serve
        self.space = os.path.join(self.tmp, 'space')
        os.makedirs(self.space)

    def _view(self, tracks_list=None, default=None):
        """Вигляд напрямків простору ЛІГИ: `space.json` у теці простору (корені — абсолютні, у тимчасовій теці)."""
        data = {} if tracks_list is None else {'tracks': tracks_list}
        if default:
            data['default_track'] = default
        with open(os.path.join(self.space, 'space.json'), 'w', encoding='utf-8') as fh:
            json.dump(data, fh)
        return self.serve._TrackView({'id': 'liga', 'name': 'Liga', 'legacy': True, 'path': self.space})

    def _seo_view(self):
        return self._view([{'id': 'united', 'root': os.path.join(self.tmp, 'united')},
                           {'id': 'seo', 'root': os.path.join(self.tmp, 'seo')}], default='united')

    def _cfg(self, tasks, single=None):
        cfg = {'current': next(iter(tasks), ''), 'tasks': tasks}
        if single is not None:
            cfg['design_work_root'] = single
        with open(os.environ['DC_TASKS_FILE'], 'w', encoding='utf-8') as fh:
            json.dump(cfg, fh, ensure_ascii=False)
        return cfg

    # ---- корінь напрямку (було `tracks.legacy_root` з `design_work_roots`; тепер `roots._root_of` над явними напрямками) ----
    def test_track_root_wins_over_the_default_and_the_shared_one(self):
        cfg = self._cfg({}, single='/r/shared')
        self.assertEqual(self.roots._root_of(cfg, self._seo_view(), 'seo'), os.path.join(self.tmp, 'seo'))

    def test_track_without_own_root_is_the_space_folder_not_invented(self):
        """Свого кореня нема — тека простору, а не вигаданий шлях за назвою."""
        cfg = self._cfg({}, single='/r/shared')
        view = self._view([{'id': 'united', 'root': os.path.join(self.tmp, 'united')}, {'id': 'liga360'}], default='united')
        self.assertEqual(self.roots._root_of(cfg, view, 'liga360'), self.space)
        self.assertEqual(self.roots._root_of(cfg, view, 'zzz'), os.path.join(self.tmp, 'united'), 'невідомий — корінь дефолтного')

    def test_no_space_or_no_tracks_falls_to_the_shared_root_then_to_deai_work(self):
        cfg = self._cfg({}, single='/r/shared')
        nospace = self.serve._TrackView(None)
        self.assertEqual(self.roots._root_of(cfg, nospace, 'seo'), '/r/shared')
        self.assertEqual(self.roots._root_of(self._cfg({}), nospace, 'seo'), os.path.join(self.tmp, 'deai-work'))
        self.assertEqual(self.roots._root_of(cfg, self._view([]), 'seo'), self.space, 'напрямків нема — тека простору')

    def test_tilde_is_expanded(self):
        cfg = self._cfg({}, single='~/x/shared')
        self.assertEqual(self.roots._root_of(cfg, self.serve._TrackView(None), 'seo'), os.path.join(self.tmp, 'x', 'shared'))

    # ---- план переїзду ----
    def test_task_in_foreign_root_is_planned_to_move(self):
        """Той самий випадок із фідбеку: SEO-задача лежить у теці United."""
        cfg = self._cfg({'blog': {'track': 'seo', 'dir': os.path.join(self.tmp, 'united', 'blog')}})
        os.makedirs(cfg['tasks']['blog']['dir'])
        (tid, track, cur, want, stop), = self.roots.plan(cfg, self._seo_view())
        self.assertEqual((tid, track, stop), ('blog', 'seo', None))
        self.assertEqual(want, os.path.join(self.tmp, 'seo', 'blog'))

    def test_task_already_home_is_not_planned(self):
        home = os.path.join(self.tmp, 'seo', 'blog')
        os.makedirs(home)
        cfg = self._cfg({'blog': {'track': 'seo', 'dir': home}})
        self.assertEqual(self.roots.plan(cfg, self._seo_view()), [])

    def test_existing_target_stops_the_move_loudly(self):
        """Ціль зайнята — це стоп із причиною, а не мовчазний пропуск і не
        затирання чужої теки."""
        cur = os.path.join(self.tmp, 'united', 'blog')
        os.makedirs(cur)
        os.makedirs(os.path.join(self.tmp, 'seo', 'blog'))
        cfg = self._cfg({'blog': {'track': 'seo', 'dir': cur}})
        self.assertIn('ціль уже існує', self.roots.plan(cfg, self._seo_view())[0][4])

    def test_missing_dir_is_reported_not_skipped(self):
        cfg = self._cfg({'blog': {'track': 'seo', 'dir': os.path.join(self.tmp, 'нема')}})
        self.assertIn('теки нема', self.roots.plan(cfg, self._seo_view())[0][4])

    # ---- сам переїзд ----
    def test_dry_run_moves_nothing(self):
        cur = os.path.join(self.tmp, 'united', 'blog')
        os.makedirs(cur)
        cfg = self._cfg({'blog': {'track': 'seo', 'dir': cur}})
        self.roots.cmd_migrate(cfg, apply=False, view=self._seo_view())
        self.assertTrue(os.path.isdir(cur), 'сухий прогін не має рухати теки')

    def test_apply_moves_folder_and_rewrites_dir(self):
        cur = os.path.join(self.tmp, 'united', 'blog')
        os.makedirs(os.path.join(cur, 'iterations', 'it1'))
        with open(os.path.join(cur, 'iterations', 'it1', 'index.html'), 'w') as fh:
            fh.write('<h1>макет</h1>')
        cfg = self._cfg({'blog': {'track': 'seo', 'dir': cur}})
        self.roots.cmd_migrate(cfg, apply=True, view=self._seo_view())

        want = os.path.join(self.tmp, 'seo', 'blog')
        self.assertFalse(os.path.exists(cur))
        self.assertTrue(os.path.isfile(os.path.join(want, 'iterations', 'it1', 'index.html')),
                        'макет мусить переїхати цілим')
        with open(os.environ['DC_TASKS_FILE'], encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['tasks']['blog']['dir'], want)

    def test_apply_does_not_touch_a_task_of_the_root_owner_track(self):
        """Сусідня задача свого напрямку лишається на місці — переїзд адресний."""
        united = os.path.join(self.tmp, 'united')
        os.makedirs(os.path.join(united, 'widget'))
        os.makedirs(os.path.join(united, 'blog'))
        cfg = self._cfg({'widget': {'track': 'united', 'dir': os.path.join(united, 'widget')},
                         'blog': {'track': 'seo', 'dir': os.path.join(united, 'blog')}})
        self.roots.cmd_migrate(cfg, apply=True, view=self._seo_view())
        self.assertTrue(os.path.isdir(os.path.join(united, 'widget')))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, 'seo', 'blog')))

    # ---- 4d-4a: напрямок задачі — лише `track` (`tracks.of_task`); було «`track`, інакше `profile`» (4d-1) ----
    def _seo_cfg(self, task):
        os.makedirs(os.path.join(self.tmp, 'united', 'blog'))
        task = {'dir': os.path.join(self.tmp, 'united', 'blog'), **task}
        return self._cfg({'blog': task}, single=os.path.join(self.tmp, 'united'))

    def test_plan_reads_only_track(self):
        """Було `…reads_track_profile_and_track_wins`: задача лише з `profile` (запис до 0.15.0) переїжджала в `seo`. Тепер лише з
        `track`: `track` переїжджає, `profile` — без напрямку (міграція ЛІГИ дописує `track`, реєстр — на межі пулу), тож лягла
        б у корінь дефолтного напрямку, де вона вже лежить, — у плані її нема."""
        view = self._seo_view()
        for name, keys, shown in (('track only', {'track': 'seo'}, 'seo'),
                                  ('both, track wins', {'track': 'seo', 'profile': 'united'}, 'seo')):
            with self.subTest(name):
                shutil.rmtree(os.path.join(self.tmp, 'united'), ignore_errors=True)
                (tid, track, cur, want, stop), = self.roots.plan(self._seo_cfg(keys), view)
                self.assertEqual((tid, track, stop), ('blog', shown, None))
                self.assertEqual(want, os.path.join(self.tmp, 'seo', 'blog'))
        shutil.rmtree(os.path.join(self.tmp, 'united'), ignore_errors=True)
        (tid, track, cur, want, stop), = self.roots.plan(self._seo_cfg({'profile': 'seo'}), view)
        self.assertEqual((tid, track, want, stop), ('blog', None, None, 'напрямок невідомий'), 'лише `profile` — не напрямок')

    def test_unknown_or_missing_track_is_never_moved(self):
        """⛔ Стенд «notes» (ревʼю Task 4): після кроку D кожен явний напрямок має корінь, тож задачі без `track` чи з невідомим
        `track`, що лежать у спільному корені, `migrate --apply` стягнув би в корінь `united`. Тепер вони в плані лише як
        «напрямок невідомий» і лишаються на місці."""
        shared = os.path.join(self.tmp, 'shared')
        tasks = {}
        for tid, keys in (('a-4', {}), ('a-6', {'track': 'zzz'}), ('a-8', {'profile': 'seo'}), ('a-9', {'track': None})):
            d = os.path.join(shared, tid)
            os.makedirs(d)
            tasks[tid] = {'dir': d, **keys}
        cfg = self._cfg(tasks, single=shared)
        view = self._seo_view()
        plan = self.roots.plan(cfg, view)
        self.assertEqual([(m[0], m[3], m[4]) for m in plan], [(t, None, 'напрямок невідомий') for t in sorted(tasks)])
        self.roots.cmd_migrate(cfg, apply=True, view=view)
        for tid in tasks:
            self.assertTrue(os.path.isdir(os.path.join(shared, tid)), tid)
            self.assertFalse(os.path.exists(os.path.join(self.tmp, 'united', tid)), tid)
        with open(os.environ['DC_TASKS_FILE'], encoding='utf-8') as fh:
            self.assertEqual({k: v['dir'] for k, v in json.load(fh)['tasks'].items()}, {k: v['dir'] for k, v in tasks.items()})

    def test_known_track_without_own_root_is_never_moved(self):
        """⛔ Ревʼю Task 7: напрямок відомий, але корінь не заданий (після кроку D корінь, що його адаптер брав зі спільного, відкинуто →
        `None`). `_root_of` дав би теку простору, і `migrate --apply` стягнув би задачу зі спільної теки в простір. Як з невідомим
        напрямком: лише називаємо, не чіпаємо."""
        shared = os.path.join(self.tmp, 'shared')
        d = os.path.join(shared, 'blog')
        os.makedirs(d)
        view = self._view([{'id': 'united', 'root': os.path.join(self.tmp, 'united')}, {'id': 'seo'}], default='united')
        cfg = self._cfg({'blog': {'dir': d, 'track': 'seo'}}, single=shared)
        self.assertEqual(self.roots.plan(cfg, view), [('blog', 'seo', d, None, 'корінь напрямку не задано')])
        self.roots.cmd_migrate(cfg, apply=True, view=view)
        self.assertTrue(os.path.isdir(d))
        self.assertFalse(os.path.exists(os.path.join(self.space, 'blog')))

    def test_track_only_task_is_not_sent_to_the_default_root(self):
        """⛔ Задачу `seo` лише з `track` не мають вважати «на місці» в United (корінь дефолтного напрямку)."""
        cfg = self._seo_cfg({'track': 'seo'})
        self.assertEqual(len(self.roots.plan(cfg, self._seo_view())), 1)

    def test_apply_moves_a_track_only_task(self):
        cfg = self._seo_cfg({'track': 'seo'})
        self.roots.cmd_migrate(cfg, apply=True, view=self._seo_view())
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, 'seo', 'blog')))

    def test_roots_in_use_lists_track_and_survives_a_numeric_profile(self):
        """Напрямки кореня — з `of_task` і з явних напрямків простору; число в `profile` (0.14.0: `TypeError` у `sorted`) — «без
        напрямку», не обвал. «Свій» — напрямок має `root`; без нього — тека простору."""
        view = self._view([{'id': 'seo', 'root': os.path.join(self.tmp, 'seo')}, {'id': 'plain'}], default='seo')
        cfg = self._cfg({'a': {'track': 'seo'}, 'b': {'profile': 'liga360'}, 'c': {'profile': 5}}, single='/r/shared')
        self.assertEqual(self.roots.roots_in_use(cfg, view),
                         [('plain', self.space, False), ('seo', os.path.join(self.tmp, 'seo'), True),
                          ('—', os.path.join(self.tmp, 'seo'), False)])

    def test_the_default_view_is_the_active_space_and_without_one_the_shared_root(self):
        """`plan(cfg)` без `view` бере активний простір; шар вимкнено (`DC_TASKS_FILE` без `DEAI_HOME`) — неявний простір без
        напрямків: усі корені — спільний `design_work_root` (раніше тут діяв адаптер зі своїми трьома коренями)."""
        cfg = self._cfg({'blog': {'track': 'seo', 'dir': os.path.join(self.tmp, 'elsewhere', 'blog')}},
                        single=os.path.join(self.tmp, 'shared'))
        os.makedirs(cfg['tasks']['blog']['dir'])
        (tid, track, cur, want, stop), = self.roots.plan(cfg)           # без напрямків усі напрямки невідомі: не чіпаємо
        self.assertEqual((tid, track, want, stop), ('blog', 'seo', None, 'напрямок невідомий'))
        self.assertEqual(self.roots.roots_in_use(cfg), [('seo', os.path.join(self.tmp, 'shared'), False)])

    def test_main_uses_the_space_view_end_to_end(self):
        """`main(['status'])` над шаром вимкненим: без напрямків усе лягає в спільний корінь, нічого не падає."""
        import io
        from contextlib import redirect_stdout
        self._cfg({'blog': {'track': 'seo', 'dir': os.path.join(self.tmp, 'united', 'blog')}}, single=os.path.join(self.tmp, 'shared'))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(self.roots.main(['status']), 0)
        self.assertIn(os.path.join(self.tmp, 'shared'), out.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'deai-work')), 'тека у домівці не створюється')


if __name__ == '__main__':
    unittest.main()
