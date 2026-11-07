"""Адаптер ЛІГИ ПІСЛЯ 4d-4a: його копія живе ЛИШЕ в `app/liga_migrate.py` (приватні `_legacy_*`), рантайм її не знає
(охоронець `NoTracksAdapter`, `tests/test_no_adapter.py`). Тут — перенесені з `tests/test_tracks.py` класи адаптера
(`LegacyTracks`, `LegacyParity`, legacy-мітки `TaskTrack`), націлені на `liga_migrate._legacy_*`; кожен тест лишився, змінився
лише обʼєкт. Знімок поведінки 0.14.0 — `tests/fixtures/tracks/before-4d1.json`.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import liga_migrate as lm  # noqa: E402
import spaces_guard  # noqa: E402
import tracks  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


BEFORE = os.path.join(_HERE, 'fixtures', 'tracks', 'before-4d1.json')


class _Home(unittest.TestCase):
    """Тимчасова домівка (`HOME`): `~` у кореневих шляхах розгортається проти неї, справжню ми не чіпаємо."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = os.path.realpath(tmp.name)
        p = mock.patch.dict(os.environ, {'HOME': self.home})
        p.start()
        self.addCleanup(p.stop)


class LegacyLabelAndOfTask(unittest.TestCase):
    """Було в `TaskTrack` (`label_tag(legacy=True)`, `_LEGACY_LABELS`, читання `profile`) — тепер `_legacy_label`/`_legacy_of_task`."""

    def test_label_legacy_uses_table_then_value(self):
        self.assertEqual(lm._legacy_label(lm._legacy_of_task({'profile': 'united'})), 'United')
        self.assertEqual(lm._legacy_label(lm._legacy_of_task({'profile': 'liga360'})), 'LIGA360')
        self.assertEqual(lm._legacy_label(lm._legacy_of_task({'track': 'seo'})), 'SEO')
        self.assertEqual(lm._legacy_label(lm._legacy_of_task({'profile': 'zzz'})), 'zzz')
        self.assertEqual(lm._legacy_label(lm._legacy_of_task({'profile': 'Seo'})), 'Seo')
        self.assertIsNone(lm._legacy_label(lm._legacy_of_task({'profile': 'Bad,Comma'})))
        self.assertIsNone(lm._legacy_label(lm._legacy_of_task({})))

    def test_label_legacy_ignores_tracks_labels(self):
        # адаптер ЛІГИ: значення — вільний рядок; підпис — таблиця адаптера, а не `label` з переданого переліку
        t = [{'id': 'united', 'label': 'Інший', 'root': None, 'repo': '', 'ds': ''}]
        self.assertEqual(lm._legacy_label('united'), 'United')
        self.assertEqual(tracks.label_tag(t, {'track': 'united'}), 'Інший')

    def test_legacy_labels_table(self):
        self.assertEqual(lm._LEGACY_LABELS, {'united': 'United', 'liga360': 'LIGA360', 'seo': 'SEO'})

    def test_of_task_prefers_track(self):
        self.assertEqual(lm._legacy_of_task({'track': 'web', 'profile': 'seo'}), 'web')

    def test_of_task_falls_back_to_profile(self):
        self.assertEqual(lm._legacy_of_task({'profile': 'seo'}), 'seo')
        self.assertEqual(lm._legacy_of_task({'track': None, 'profile': 'seo'}), 'seo')
        self.assertEqual(lm._legacy_of_task({'track': '', 'profile': 'seo'}), 'seo')
        self.assertEqual(lm._legacy_of_task({'track': 5, 'profile': 'seo'}), 'seo')

    def test_of_task_returns_the_stored_string_as_is(self):
        for v in ('United', 'Bad,Comma', 'x' * 40, '  seo  ', ' ', 'a\tb'):
            self.assertEqual(lm._legacy_of_task({'profile': v}), v, repr(v))
            self.assertEqual(lm._legacy_of_task({'track': v}), v, repr(v))

    def test_of_task_non_string_or_empty_is_none(self):
        for task in ({}, {'profile': ''}, {'profile': None}, {'profile': 5}, {'profile': ['united']}, {'track': 5},
                     {'track': ''}, {'track': '', 'profile': ''}, {'track': {}, 'profile': 5}):
            self.assertIsNone(lm._legacy_of_task(task), repr(task))

    def test_of_task_not_a_dict_is_none(self):
        for task in (None, ['united'], 'united', 5):
            self.assertIsNone(lm._legacy_of_task(task), repr(task))


class LegacyTracks(_Home):
    """Адаптер ЛІГИ `_legacy_tracks(cfg)` (спека §2, §6): перелік, `root`, `repo`, `label`, `ds`, дефолт, `fallback_root`."""

    def test_constants(self):
        self.assertEqual(tracks.ID_RE.pattern, '[a-z0-9-]{1,32}')
        self.assertEqual(lm._FALLBACK_ROOT, '~/deai-work')

    def test_nothing_gives_three_tracks_and_default_united(self):
        tr, d, fb = lm._legacy_tracks({})
        self.assertEqual([t['id'] for t in tr], ['united', 'liga360', 'seo'])
        self.assertEqual(d, 'united')
        self.assertEqual(fb, os.path.join(self.home, 'deai-work'))
        self.assertEqual([t['label'] for t in tr], ['United', 'LIGA360', 'SEO'])
        self.assertEqual([t['ds'] for t in tr], ['united', 'liga360', 'seo'])
        self.assertEqual({t['root'] for t in tr}, {fb})
        self.assertEqual({t['repo'] for t in tr}, {''})

    def test_result_shape(self):
        tr, d, fb = lm._legacy_tracks({})
        self.assertEqual(list(tr[0]), ['id', 'label', 'root', 'repo', 'ds'])

    def test_ids_order_and_no_duplicates(self):
        cfg = {'design_work_roots': {'seo': '~/a', 'zeta': '~/b', 'alpha': '~/c'},
               'profile_repos': {'alpha': 'git@e:s/w', 'beta': 'git@e:s/w', 'united': 'git@e:s/w'}}
        tr, _, _ = lm._legacy_tracks(cfg)
        self.assertEqual([t['id'] for t in tr], ['united', 'liga360', 'seo', 'zeta', 'alpha', 'beta'])

    def test_ids_only_by_id_re(self):
        cfg = {'design_work_roots': {'United': '~/a', 'a_b': '~/b', '': '~/c', 'x' * 33: '~/d', 'ok': '~/e', 5: '~/f'},
               'profile_repos': {'Bad!': 'git@e:s/w', 'fine-1': 'git@e:s/w'}}
        tr, _, _ = lm._legacy_tracks(cfg)
        self.assertEqual([t['id'] for t in tr], ['united', 'liga360', 'seo', 'ok', 'fine-1'])

    def test_root_own_then_shared_then_fallback(self):
        cfg = {'design_work_root': '~/work/shared', 'design_work_roots': {'united': '~/work/united', 'seo': ''}}
        tr, _, fb = lm._legacy_tracks(cfg)
        by = {t['id']: t['root'] for t in tr}
        self.assertEqual(by, {'united': os.path.join(self.home, 'work/united'), 'liga360': os.path.join(self.home, 'work/shared'),
                              'seo': os.path.join(self.home, 'work/shared')})
        self.assertEqual(fb, os.path.join(self.home, 'work/shared'))

    def test_root_is_expanded_not_tilde(self):
        tr, _, fb = lm._legacy_tracks({'design_work_root': '~/x', 'design_work_roots': {'seo': '/srv/seo'}})
        self.assertFalse(any(t['root'].startswith('~') for t in tr) or fb.startswith('~'))
        self.assertEqual({t['id']: t['root'] for t in tr}['seo'], '/srv/seo')

    def test_repo_from_profile_repos_only_if_valid_and_stripped(self):
        cfg = {'profile_repos': {'united': '  ssh://git@example.com/o/r.git  ', 'seo': '-x', 'liga360': 'a b', 'extra': 'git@e:s/w'}}
        tr, _, _ = lm._legacy_tracks(cfg)
        self.assertEqual({t['id']: t['repo'] for t in tr},
                         {'united': 'ssh://git@example.com/o/r.git', 'liga360': '', 'seo': '', 'extra': 'git@e:s/w'})

    def test_label_table_or_id(self):
        tr, _, _ = lm._legacy_tracks({'design_work_roots': {'zzz': '~/z'}})
        self.assertEqual({t['id']: t['label'] for t in tr}, {'united': 'United', 'liga360': 'LIGA360', 'seo': 'SEO', 'zzz': 'zzz'})

    def test_ds_is_the_id(self):
        tr, _, _ = lm._legacy_tracks({'design_work_roots': {'zzz': '~/z'}})
        self.assertTrue(all(t['ds'] == t['id'] for t in tr))

    def test_does_not_raise_on_bad_cfg(self):
        deep = cur = {}
        for _ in range(500):
            cur['x'] = {}
            cur = cur['x']
        for cfg in (None, [], ['design_work_root'], 'x', 5, {'design_work_roots': 5}, {'design_work_roots': ['united']},
                    {'design_work_roots': None}, {'profile_repos': 'united'}, {'profile_repos': ['united']},
                    {'profile_repos': None}, {'design_work_root': 5}, {'design_work_root': ['x']}, {'design_work_root': ''},
                    {'design_work_roots': {'united': 5, 'seo': ['x'], 'liga360': None}}, deep,
                    {'profile_repos': {'united': 5, 'seo': None, 'zzz': ['x']}}):
            tr, d, fb = lm._legacy_tracks(cfg)
            self.assertEqual([t['id'] for t in tr][:3], ['united', 'liga360', 'seo'], repr(cfg)[:60])
            self.assertEqual(d, 'united')
            self.assertEqual(fb, os.path.join(self.home, 'deai-work'), repr(cfg)[:60])

    def test_non_string_roots_fall_back_to_the_next_link(self):
        """Відмінність від 0.14.0 (там `TypeError` у `expanduser`): не рядок — як відсутнє, діє наступна ланка ланцюга."""
        shared, deai = os.path.join(self.home, 'work/shared'), os.path.join(self.home, 'deai-work')
        for bad in (5, ['x'], {'a': 1}, True, 1.5):
            cfg = {'design_work_root': '~/work/shared', 'design_work_roots': {'united': bad, 'seo': '~/work/seo'}}
            self.assertEqual(lm._legacy_root(cfg, 'united'), shared, repr(bad))          # власний не рядок → спільний
            self.assertEqual(lm._legacy_root(cfg, 'seo'), os.path.join(self.home, 'work/seo'))
            tr, _, fb = lm._legacy_tracks(cfg)
            self.assertEqual((tracks.find(tr, 'united')['root'], fb), (shared, shared), repr(bad))
            cfg = {'design_work_root': bad, 'design_work_roots': {'united': 5, 'seo': '~/work/seo'}}
            self.assertEqual(lm._legacy_root(cfg, 'united'), deai, repr(bad))             # і власний, і спільний не рядки
            self.assertEqual(lm._legacy_root(cfg, 'zzz'), deai, repr(bad))
            self.assertEqual(lm._legacy_root(cfg, 'seo'), os.path.join(self.home, 'work/seo'))
            self.assertEqual(lm._legacy_tracks(cfg)[2], deai, repr(bad))

    def test_design_work_roots_not_a_dict_is_shared_root(self):
        """Свідома відмінність від 0.14.0 (спека §6.4): там `AttributeError` (500), тут — спільний корінь."""
        cfg = {'design_work_root': '~/work/shared', 'design_work_roots': ['united']}
        tr, _, fb = lm._legacy_tracks(cfg)
        shared = os.path.join(self.home, 'work/shared')
        self.assertEqual(fb, shared)
        self.assertEqual({t['root'] for t in tr}, {shared})
        for p in ('united', 'seo', None, ''):
            self.assertEqual(lm._legacy_root(cfg, p), shared)

    def test_fallback_root_is_shared_not_the_default_tracks_root(self):
        """Спека §6.1: напрямок без власного кореня → `fallback_root`, а НЕ корінь дефолтного `united`."""
        cfg = {'design_work_root': '~/work/shared', 'design_work_roots': {'united': '~/work/united'}}
        tr, d, fb = lm._legacy_tracks(cfg)
        self.assertEqual(d, 'united')
        self.assertNotEqual(fb, tracks.find(tr, 'united')['root'])
        self.assertEqual(fb, os.path.join(self.home, 'work/shared'))

    def test_legacy_root_non_identifier_key_is_still_honoured(self):
        # `work_root` 0.14.0 брав `roots.get(profile)` для БУДЬ-ЯКОГО рядка, зокрема не за `ID_RE`: адаптер зберігає це
        cfg = {'design_work_root': '~/s', 'design_work_roots': {'United': '~/big'}}
        self.assertEqual(lm._legacy_root(cfg, 'United'), os.path.join(self.home, 'big'))
        self.assertEqual(lm._legacy_root(cfg, 'united'), os.path.join(self.home, 's'))
        self.assertNotIn('United', [t['id'] for t in lm._legacy_tracks(cfg)[0]])

    def test_a_liga_root_never_goes_through_find(self):
        """Було в `ServerLegacyParity`: `_legacy_tracks` перелічує лише id за `ID_RE`, а 0.14.0 шанував власний корінь будь-якого
        ключа (`'United'` теж): шлях через `find` його не бачив би."""
        cfg = {'design_work_roots': {'United': '~/work/up', 'x y': '~/work/sp'}, 'design_work_root': '~/work/shared'}
        self.assertIsNone(tracks.find(lm._legacy_tracks(cfg)[0], 'United'))
        self.assertEqual(lm._legacy_root(cfg, 'United'), os.path.expanduser('~/work/up'))
        self.assertEqual(lm._legacy_root(cfg, 'x y'), os.path.expanduser('~/work/sp'))
        self.assertEqual(lm._legacy_root(cfg, 'liga360'), os.path.expanduser('~/work/shared'))

    def test_legacy_root_odd_values(self):
        cfg = {'design_work_root': '~/s', 'design_work_roots': {'united': '~/u'}}
        s = os.path.join(self.home, 's')
        for v in (None, 5, ['united'], {}, b'united', '', 'zzz'):
            self.assertEqual(lm._legacy_root(cfg, v), s, repr(v))

    def test_legacy_repos_not_a_dict_and_bad_cfg(self):
        for cfg in (None, [], 'x', {}, {'profile_repos': None}, {'profile_repos': ['united']}, {'profile_repos': 'united'}):
            self.assertEqual(lm._legacy_repos(cfg), {}, repr(cfg))


class LegacyParity(_Home):
    """⛔ Паритет адаптера зі знімком 0.14.0: кожен сценарій `roots` / `repos` / `tags` через `liga_migrate._legacy_*`."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def _expect_path(self, snap_value):
        """Знімок тримає шляхи як `~/…` відносно тимчасового HOME (або абсолютні): повертаємо справжній з тим самим HOME."""
        return os.path.expanduser(snap_value)

    def test_roots_through_legacy_root(self):
        n = 0
        for name, sc in self.snap['roots'].items():
            if name == 'fallback_constant':
                continue
            for key, row in sc['by_profile'].items():
                prof = None if key == 'None' else key
                if 'raised' in row:
                    continue                                            # свідома відмінність: окремий тест нижче
                self.assertEqual(lm._legacy_root(sc['cfg'], prof), self._expect_path(row['result']), (name, key))
                n += 1
        self.assertGreaterEqual(n, 40)

    def test_roots_through_legacy_tracks(self):
        """Те саме через перелік адаптера: напрямок з переліку → його `root`, будь-що інше → `fallback_root`."""
        for name, sc in self.snap['roots'].items():
            if name == 'fallback_constant':
                continue
            tr, _, fb = lm._legacy_tracks(sc['cfg'])
            for key, row in sc['by_profile'].items():
                if 'raised' in row:
                    continue
                t = tracks.find(tr, None if key == 'None' else key)
                got = t['root'] if t else fb
                self.assertEqual(got, self._expect_path(row['result']), (name, key))

    def test_roots_fallback_constant(self):
        self.assertEqual(lm._FALLBACK_ROOT, self.snap['roots']['fallback_constant'])

    def test_roots_not_a_dict_deliberate_difference(self):
        """0.14.0: `AttributeError` для КОЖНОГО профілю. Тепер (спека §6.4) — спільний корінь, без винятку."""
        sc = self.snap['roots']['roots_not_dict']
        self.assertEqual({r.get('raised') for r in sc['by_profile'].values()}, {'AttributeError'})
        shared = self._expect_path(sc['cfg']['design_work_root'])
        for key in sc['by_profile']:
            self.assertEqual(lm._legacy_root(sc['cfg'], None if key == 'None' else key), shared, key)
        tr, _, fb = lm._legacy_tracks(sc['cfg'])
        self.assertEqual(fb, shared)
        self.assertEqual({t['root'] for t in tr}, {shared})

    def test_roots_edge_values_are_covered(self):
        """Крайні значення знімка не загубилися: `'United'`, `''`, `None`, невідомий, свій/спільний/порожній корінь."""
        both = self.snap['roots']['both']['by_profile']
        self.assertTrue({'United', '', 'None', 'zzz', 'united', 'seo', 'liga360'} <= set(both))
        cfg = self.snap['roots']['both']['cfg']
        shared = self._expect_path(cfg['design_work_root'])
        for p in ('United', '', None, 'zzz', 'liga360'):
            self.assertEqual(lm._legacy_root(cfg, p), shared, repr(p))
        self.assertEqual(lm._legacy_root(cfg, 'united'), self._expect_path(cfg['design_work_roots']['united']))
        empty = self.snap['roots']['empty_value']['cfg']                 # `united: ''` → спільний, не фолбек
        self.assertEqual(lm._legacy_root(empty, 'united'), self._expect_path(empty['design_work_root']))

    def test_repos_through_legacy_repos_and_tracks(self):
        n = 0
        for name, sc in self.snap['repos'].items():
            want = sc['result']['result']
            cfg = sc.get('cfg')                                            # `no_file` / `not_json` — конфігу нема
            self.assertEqual(lm._legacy_repos(cfg), want, name)
            tr, _, _ = lm._legacy_tracks(cfg)
            self.assertEqual({t['id']: t['repo'] for t in tr if t['repo']}, want, name)
            n += 1
        self.assertEqual(n, 17)

    def test_repos_for_every_listed_id(self):
        sc = self.snap['repos']['good_pairs']
        tr, _, _ = lm._legacy_tracks(sc['cfg'])
        for t in tr:
            self.assertEqual(t['repo'], sc['result']['result'].get(t['id'], ''), t['id'])

    def test_tags_derived_without_tags_key_only_through_the_label_table(self):
        """Сценарії `tags` знімка без ключа `tags` (11 + крайні): рівно `_legacy_label(_legacy_of_task(task))`, тобто
        `_LEGACY_LABELS` + правила мітки. (Колишній тест через справжній `serve.task_tags` більше не має предмета: рантайм
        адаптера не знає — див. таблицю відповідності у звіті 4d-4a.)"""
        self.assertEqual(len(self.snap['tags']), 24)
        n = 0
        for name, sc in self.snap['tags'].items():
            task = sc['task']
            if isinstance(task, dict) and 'tags' in task:
                continue
            tag = lm._legacy_label(lm._legacy_of_task(task))
            self.assertEqual([tag] if tag else [], sc['result']['result'], name)
            n += 1
        self.assertGreaterEqual(n, 16)

    def test_tags_edge_profiles(self):
        t = self.snap['tags']
        self.assertEqual(t["no_tags_profile_'zzz'"]['result']['result'], ['zzz'])
        self.assertEqual(lm._legacy_label(lm._legacy_of_task({'profile': 'zzz'})), 'zzz')
        self.assertIsNone(lm._legacy_label(lm._legacy_of_task({'profile': 5})))                 # числовий профіль
        self.assertIsNone(lm._legacy_label(lm._legacy_of_task({'profile': ''})))
        self.assertIsNone(lm._legacy_label(lm._legacy_of_task({'profile': 'x' * 40})))


if __name__ == '__main__':
    unittest.main()
