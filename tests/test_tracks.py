"""Напрямки простору (етап 4d-1, спека 2026-11-04-space-tracks-design.md).

Тут: знімок поведінки 0.14.0 (`Before4d1Shape`, Task 1) і ядро `app/tracks.py` (Task 2: `Normalize`, `TaskTrack`,
`LegacyTracks`, `LegacyParity` — паритет ЛІГИ зі знімком через `tracks`), Task 3: сервер на напрямках (`ServerLegacyParity` —
диференційні тести ЛІГИ проти знімка через справжній `serve`, `ServerTracks` — звичайний простір, `ServerHygiene`). Наступні
задачі додають класи (API), що читають той самий JSON.

4d-4a: адаптерні класи (`LegacyTracks`, `LegacyParity`, legacy-мітки) переїхали в `tests/test_liga_adapter.py` (націлені на
`liga_migrate._legacy_*`); `BinParity` і `ServerLegacyParity` ретайрені (таблиця відповідності — у звіті задачі; паритет після
міграції — `AfterMigrationParity4d4a`, Task 7).
"""
import copy
import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app')
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _APP)
sys.path.insert(0, _HERE)
import tracks  # noqa: E402  (чисте ядро; `serve` воно не імпортує)
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import liga_fixture  # noqa: E402
import make_before_4d1 as gen  # noqa: E402  (хелпери знімка: `Server`, `Vcs`, `NoNet`, `pages`, `route`; ГЕНЕРАТОР не кличемо)

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


BEFORE = os.path.join(_HERE, 'fixtures', 'tracks', 'before-4d1.json')

PROFILES = ('None', 'liga360', 'seo', 'united', 'zzz')       # відсортовано (ключ для `None` — рядок)
ROOT_PROFILES = tuple(sorted(PROFILES + ('United', '')))     # `roots`/`bin`: ще «не той регістр» і порожній рядок


class Before4d1Shape(unittest.TestCase):
    """Знімок поведінки профілю задачі 0.14.0 на місці й має ключі, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['bin', 'ds', 'meta', 'pages', 'repos', 'roots', 'route', 'tags', 'task_new'])
        self.assertEqual(self.snap['meta']['version'], '0.14.0')
        self.assertEqual(self.snap['meta']['source_commit'], 'c8c3a8b')
        self.assertEqual(self.snap['meta']['generator'], 'tests/make_before_4d1.py')

    def test_machine_independent(self):
        """⛔ Знімок не несе ні справжніх шляхів, ні імен, ні тимчасових тек: лише `~/…` відносно тимчасового HOME."""
        # ⛔ Імʼя користувача машини — з оточення, не літералом: справжнє імʼя в коді репо — та сама утічка, від якої тест береже.
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/Users/', '/home/', '/var/folders', '/private/', '/tmp/', 'before-4d1-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        # жодного часового штампа (`opened`, дат створення): лише факт наявності
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))
        self.assertEqual(self.snap['meta']['volatile_stripped'], ['opened'])

    def test_roots_shape(self):
        r = self.snap['roots']
        names = ['absolute', 'both', 'empty_value', 'nothing', 'roots_not_dict', 'roots_null', 'roots_only', 'shared_only']
        self.assertEqual(sorted(k for k in r if k != 'fallback_constant'), names)
        for name in names:
            self.assertEqual(sorted(r[name]['by_profile']), list(ROOT_PROFILES), name)
        self.assertEqual(r['fallback_constant'], '~/deai-work')
        # ключові паритети: свій корінь профілю → спільний → фолбек; невідомий і `None` — спільний (НЕ корінь `united`)
        both = {p: v['result'] for p, v in r['both']['by_profile'].items()}
        self.assertEqual(both, {'united': '~/work/united', 'seo': '~/work/seo', 'liga360': '~/work/shared',
                                'zzz': '~/work/shared', 'None': '~/work/shared',
                                'United': '~/work/shared', '': '~/work/shared'})
        self.assertEqual({v['result'] for v in r['nothing']['by_profile'].values()}, {'~/deai-work'})
        self.assertEqual(r['empty_value']['by_profile']['united']['result'], '~/work/shared')
        # `design_work_roots` не словник — відмова `AttributeError` (не мовчазний фолбек)
        self.assertEqual({v.get('raised') for v in r['roots_not_dict']['by_profile'].values()}, {'AttributeError'})
        self.assertEqual(r['absolute']['by_profile']['united']['result'], '/srv/designs/united')

    def test_repos_shape(self):
        r = self.snap['repos']
        self.assertEqual(len(r), 17)
        for name, row in r.items():
            self.assertIn('result', row, name)
            self.assertNotIn('raised', row['result'], name)       # `profile_repos()` не кидає за жодного входу
        res = {k: v['result']['result'] for k, v in r.items()}
        self.assertEqual(sorted(res['good_pairs']), ['liga360', 'seo', 'united'])
        self.assertEqual(sorted(res['bad_key_uppercase']), ['seo'])
        self.assertEqual(sorted(res['bad_repo_dash']), ['liga360'])
        self.assertEqual(res['repo_stripped'], {'united': 'ssh://git@example.com/o/r.git'})
        self.assertEqual(len(res['key_len_32_ok_33_bad']), 1)
        for name in ('not_a_dict', 'string_value', 'null_value', 'no_key', 'cfg_not_dict', 'no_file', 'not_json',
                     'repo_non_ascii'):
            self.assertEqual(res[name], {}, name)

    def test_tags_shape(self):
        r = self.snap['tags']
        self.assertEqual(len(r), 24)
        res = {k: v['result']['result'] for k, v in r.items()}
        self.assertEqual((res["no_tags_profile_'united'"], res["no_tags_profile_'liga360'"], res["no_tags_profile_'seo'"]),
                         (['United'], ['LIGA360'], ['SEO']))
        self.assertEqual(res["no_tags_profile_'zzz'"], ['zzz'])                    # невідомий профіль — як є
        self.assertEqual(res["no_tags_profile_'Bad,Comma'"], [])
        self.assertEqual(res['no_tags_profile_x*40'], [])
        self.assertEqual(res['no_tags_profile_5'], [])
        self.assertEqual(res['tags_empty_with_profile'], [])                       # `tags: []` — свідомо порожньо
        self.assertEqual(res['tags_A_with_profile'], ['A'])
        self.assertEqual(res['no_tags_no_profile'], [])

    def test_ds_shape(self):
        r = self.snap['ds']
        self.assertEqual(len(r), 13)
        res = {k: v['result'].get('result') for k, v in r.items()}
        self.assertEqual(r['5']['result'], {'raised': 'AttributeError'})             # не рядок — виняток, не порожньо
        self.assertEqual(res["'United'"], '')                                         # шаблон лише малі літери
        self.assertEqual((res["'united'"], res["'seo'"], res["'zzz'"]), ('?ds=united', '?ds=seo', '?ds=zzz'))
        for bad in ("'Bad!'", "''", 'None', "'a_b'", 'x*33', "'United'"):
            self.assertEqual(res[bad], '', bad)

    def test_task_new_shape(self):
        r = self.snap['task_new']
        self.assertEqual(sorted(r), list(PROFILES))
        for name, row in r.items():
            self.assertTrue(row['result']['ok'], name)
            self.assertTrue(row['it1_index_exists'], name)
            self.assertTrue(row['has_opened'], name)
            self.assertEqual(row['urlopen_calls'], 0, name)                        # мережі не було
            self.assertEqual(row['entry']['profile'], None if name == 'None' else name, name)
            self.assertEqual(row['entry']['dir'], row['result']['dir'], name)
        # постачальника `vcs` питають рівно тоді, коли в задачі є `gitlab` (профіль у таблиці `profile_repos`)
        self.assertEqual({k: v['vcs_provider_calls'] for k, v in r.items()},
                         {'united': 1, 'liga360': 0, 'seo': 0, 'zzz': 0, 'None': 0})
        self.assertEqual(r['united']['entry']['gitlab'], {'repo': 'ssh://git@example.com/o/r.git', 'path': 'mockup/t1'})
        self.assertEqual(r['united']['entry']['dir'], '~/work/united/t1')
        self.assertEqual(r['seo']['entry']['dir'], '~/work/seo/t1')
        for name in ('liga360', 'zzz', 'None'):
            self.assertEqual(r[name]['entry']['dir'], '~/work/shared/t1', name)
        for name in ('liga360', 'seo', 'zzz', 'None'):
            self.assertNotIn('gitlab', r[name]['entry'], name)

    def test_route_shape(self):
        rt = self.snap['route']
        self.assertEqual(sorted(rt), ['layer_on', 'task_get_no_header', 'task_get_query_id', 'task_new',
                                      'task_new_current_after', 'task_seeded', 'tasks_after_create', 'tasks_seeded',
                                      'urlopen_calls', 'vcs_provider_calls_total'])
        self.assertIs(rt['layer_on'], False)                                       # шар просторів вимкнено
        self.assertEqual(rt['urlopen_calls'], 0)
        posts = rt['task_new']
        self.assertEqual(sorted(posts), sorted(['empty_string', 'explicit_gitlab', 'liga360', 'no_profile', 'not_a_string_5',
                                                'null', 'seo', 'unknown_zzz', 'uppercase_United', 'united',
                                                'with_empty_tags', 'with_tags']))
        # без профілю, `''` і `null` — `united` (`profile or 'united'`); не рядок — 400 `bad-profile` до будь-якого запису
        for name in ('no_profile', 'empty_string', 'null'):
            self.assertEqual((posts[name]['status'], posts[name]['entry']['profile']), (200, 'united'), name)
        self.assertEqual((posts['not_a_string_5']['status'], posts['not_a_string_5']['code']), (400, 'bad-profile'))
        self.assertIsNone(posts['not_a_string_5']['entry'])
        # невідомий і «не той регістр» профіль приймається як є, тека — спільний корінь, репо нема
        for name, prof in (('unknown_zzz', 'zzz'), ('uppercase_United', 'United')):
            self.assertEqual(posts[name]['entry']['profile'], prof, name)
            self.assertNotIn('gitlab', posts[name]['entry'], name)
        # `tags: []` у запис не лягає (тоді мітка похідна), непорожні — лягають
        self.assertNotIn('tags', posts['with_empty_tags']['entry'])
        self.assertEqual(posts['with_tags']['entry']['tags'], ['A', 'B'])
        self.assertEqual(posts['explicit_gitlab']['entry']['profile'], 'zzz')
        # рядки `GET /api/tasks` після створення — у порядку id, лише `id`/`profile`/`tags`
        rows = rt['tasks_after_create']['rows']
        self.assertEqual([r['id'] for r in rows], sorted(r['id'] for r in rows))
        self.assertEqual(len(rows), 11)
        self.assertIsNone(rt['tasks_after_create']['space'])
        # готові задачі: 10 рядків у порядку файла; `/api/task` віддає `profile` і `tags`
        seeded = rt['tasks_seeded']['rows']
        self.assertEqual(len(seeded), 10)
        self.assertEqual(sorted(rt['task_seeded']), sorted(r['id'] for r in seeded))
        for row in seeded:
            one = rt['task_seeded'][row['id']]
            self.assertEqual((one['status'], one['has_profile_key']), (200, True), row['id'])
            self.assertEqual((one['profile'], one['tags']), (row['profile'], row['tags']), row['id'])
        # задачу `GET /api/task` обирає заголовок (або `current`), а `?id=` не діє — 404 (план 4d-1 писав `?id=`)
        self.assertEqual(rt['task_get_query_id']['status'], 404)
        self.assertEqual(rt['task_get_no_header']['id'], 's-united')

    def test_pages_shape(self):
        """Хвіст `inspector.js…` у розмітці `/commented`: обидва входи розмітки (локальний і модуля) дають той самий."""
        pg = self.snap['pages']
        self.assertEqual(pg['urlopen_calls'], 0)
        rows = {k: v for k, v in pg.items() if k != 'urlopen_calls'}
        self.assertEqual(len(rows), 10)
        want = {'s-united': '?ds=united', 's-notags': '?ds=united', 's-tags': '?ds=united', 's-liga360': '?ds=liga360',
                's-seo': '?ds=seo', 's-zzz': '?ds=zzz',
                # без профілю, з комою, не з малих літер — хвоста нема (тег `inspector.js` лишається)
                's-noprofile': '', 's-comma': '', 's-upper': ''}
        for tid, tail in want.items():
            for ch in ('local', 'project'):
                self.assertEqual(rows[tid][ch]['status'], 200, (tid, ch))
                self.assertEqual(rows[tid][ch]['inspector_tails'], [tail], (tid, ch))
            self.assertFalse(rows[tid]['local']['project_channel'], tid)
            self.assertTrue(rows[tid]['project']['project_channel'], tid)
        # профіль не рядок (`5`): сторінка падає (`AttributeError` у `inspector_ds_arg`), зʼєднання рветься без відповіді
        for ch in ('local', 'project'):
            self.assertEqual(rows['s-five'][ch], {'error': 'RemoteDisconnected', 'status': None})

    def test_bin_shape(self):
        b = self.snap['bin']
        self.assertEqual(sorted(b), sorted(['liga', 'no_roots', 'registry_work_root', 'registry_work_root_5',
                                            'registry_work_root_nothing', 'with_int_profile']))
        # `registry._work_root` = колишній `serve.work_root` (0.14.0), тепер `tracks.legacy_root`
        self.assertEqual({k: v['result'] for k, v in b['registry_work_root'].items()},
                         {'united': '~/work/united', 'seo': '~/work/seo', 'liga360': '~/work/shared', 'zzz': '~/work/shared',
                          'None': '~/work/shared', 'United': '~/work/shared', '': '~/work/shared'})
        self.assertEqual(b['registry_work_root_5']['result'], '~/work/shared')
        self.assertEqual(b['registry_work_root_nothing']['result'], '~/deai-work')
        plan = {m[0]: m for m in b['liga']['plan']['result']}
        # переїдуть лише `united`/`seo`-задачі зі спільного кореня; решта стоп-причин названа вголос
        self.assertEqual(sorted(plan), ['b-clash', 'b-gone', 'b-nodir', 'b-seo', 'b-united'])
        self.assertEqual(plan['b-united'][2:], ['~/work/shared/b-united', '~/work/united/b-united', None])
        self.assertEqual(plan['b-seo'][3], '~/work/seo/b-seo')
        self.assertIn('ціль уже існує', plan['b-clash'][4])
        self.assertEqual(plan['b-gone'][4], 'теки нема на диску')
        self.assertEqual(plan['b-nodir'][2:], [None, None, 'немає dir у tasks.json'])
        in_use = {r[0]: r[1:] for r in b['liga']['roots_in_use']['result']}
        self.assertEqual(in_use['seo'], ['~/work/seo', True])
        self.assertEqual(in_use['zzz'], ['~/work/shared', False])
        self.assertEqual(in_use['—'], ['~/work/shared', False])                      # задача без профілю
        self.assertEqual(b['no_roots']['roots_in_use']['result'], [['united', '~/deai-work', False]])
        # профіль-число: `roots_in_use` сортує змішані типи → `TypeError`; `plan` працює (спільний корінь)
        self.assertEqual(b['with_int_profile']['roots_in_use'], {'raised': 'TypeError'})
        self.assertIn(['b-five', 5, '~/work/shared/b-zzz', '~/work/shared/b-five', None], b['with_int_profile']['plan']['result'])


class _Home(unittest.TestCase):
    """Тимчасова домівка (`HOME`) і тека простору в ній: `root` у просторі перевіряється проти справжньої домівки, а справжню
    ми не чіпаємо. `self.home` / `self.space` — реальні шляхи (`realpath`) під ним."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = os.path.realpath(tmp.name)
        self.space = os.path.join(self.home, 'space')
        os.makedirs(self.space)
        p = mock.patch.dict(os.environ, {'HOME': self.home})
        p.start()
        self.addCleanup(p.stop)


class _LayerOff(_Home):
    """Шар просторів ВИМКНЕНО (лише `DC_TASKS_FILE`, без `DEAI_HOME`) — світ, у якому знято знімок: простір неявний і ЛІГА.
    Усе в тимчасовій домівці; справжній `~/.deai` стереже `spaces_guard` модуля."""

    def setUp(self):
        super().setUp()
        env = {'DC_TASKS_FILE': os.path.join(self.home, 'tasks.json'), 'DC_NO_OVERVIEW': '1'}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('DEAI_HOME', None)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)


class Normalize(_Home):
    """`tracks.normalize(raw, space_path)`: кожне правило спеки §1 — свій тест."""

    def norm(self, *recs):
        return tracks.normalize(list(recs), self.space)

    def test_not_a_list_is_empty(self):
        for raw in (None, {}, {'id': 'web'}, 'web', 5, True):
            self.assertEqual(tracks.normalize(raw, self.space), [], repr(raw))

    def test_roots_false_skips_the_root_check_and_touches_no_disk(self):
        """`roots=False` (листинг просторів): `root` завжди `None` без жодного `check_new_path`; решта полів — як із перевіркою."""
        recs = [{'id': 'web', 'label': 'Web', 'root': 'web-dir', 'repo': 'git@example.com:studio/web.git', 'ds': 'united'},
                {'id': 'mobile', 'root': '/'}]
        with mock.patch.object(spaces, 'check_new_path', side_effect=AssertionError('диск чіпати не можна')):
            got = tracks.normalize(recs, self.space, roots=False)
        full = tracks.normalize(recs, self.space)
        self.assertEqual([t['root'] for t in got], [None, None])
        self.assertIsNotNone(full[0]['root'], 'контроль: з перевіркою корінь `web-dir` проходить')
        self.assertEqual([{**t, 'root': None} for t in full], got)

    def test_record_not_a_dict_is_dropped(self):
        got = self.norm('web', 5, None, ['id'], {'id': 'ok'})
        self.assertEqual([t['id'] for t in got], ['ok'])

    def test_bad_id_is_dropped(self):
        bad = ('', 'Web', 'a_b', 'a b', 'a.b', 'a' * 33, 'вeb', 5, None, ['a'], 'a\n')
        got = tracks.normalize([{'id': b} for b in bad] + [{'id': 'a' * 32}, {'id': 'x-1'}], self.space)
        self.assertEqual([t['id'] for t in got], ['a' * 32, 'x-1'])

    def test_missing_id_is_dropped(self):
        self.assertEqual(self.norm({'label': 'X'}), [])

    def test_duplicate_id_first_wins(self):
        got = self.norm({'id': 'web', 'label': 'First'}, {'id': 'mobile'}, {'id': 'web', 'label': 'Second'})
        self.assertEqual([(t['id'], t['label']) for t in got], [('web', 'First'), ('mobile', 'mobile')])

    def test_bad_first_record_does_not_reserve_id(self):
        # запис з поганим `id` не резервує нічого: наступний із «виправленим» id проходить
        got = self.norm({'id': 'Web'}, {'id': 'web'})
        self.assertEqual([t['id'] for t in got], ['web'])

    def test_label_rules(self):
        good = {'Web': 'Web', '  a   b  ': 'a b', 'x' * 32: 'x' * 32}
        bad = ['x' * 33, 'a,b', 'a\tb', 'a\nb', 'a\u202eb', 'a\u200bb', 'a\ufeffb', 'a\x7fb', '', '   ', 5, None, ['x'], {}]
        for raw, want in good.items():
            self.assertEqual(self.norm({'id': 'w', 'label': raw})[0]['label'], want, repr(raw))
        for raw in bad:
            self.assertEqual(self.norm({'id': 'w', 'label': raw})[0]['label'], 'w', repr(raw))
        self.assertEqual(self.norm({'id': 'w'})[0]['label'], 'w')

    def test_root_absolute_inside_home(self):
        r = os.path.join(self.home, 'work', 'web')
        self.assertEqual(self.norm({'id': 'a', 'root': r})[0]['root'], r)

    def test_root_tilde_expands(self):
        got = self.norm({'id': 'a', 'root': '~/work/web'}, {'id': 'b', 'root': '~/work/../w2'})
        self.assertEqual([t['root'] for t in got], [os.path.join(self.home, 'work', 'web'), os.path.join(self.home, 'w2')])

    def test_root_relative_to_space_path(self):
        got = self.norm({'id': 'a', 'root': 'mobile'}, {'id': 'b', 'root': 'x/../y'}, {'id': 'c', 'root': './z/'})
        self.assertEqual([t['root'] for t in got], [os.path.join(self.space, p) for p in ('mobile', 'y', 'z')])

    def test_root_relative_without_space_path_is_none(self):
        self.assertIsNone(tracks.normalize([{'id': 'a', 'root': 'mobile'}], '')[0]['root'])
        self.assertIsNone(tracks.normalize([{'id': 'a', 'root': 'mobile'}], None)[0]['root'])
        self.assertIsNone(tracks.normalize([{'id': 'a', 'root': 'mobile'}], 'rel/space')[0]['root'])

    def test_root_missing_or_bad_type_is_none(self):
        for raw in ('', '   ', 5, None, ['x'], {}, True, 'a\x00b', 'a\nb'):
            got = self.norm({'id': 'a', 'root': raw})
            self.assertEqual(len(got), 1, repr(raw))                       # запис лишається, поле — відсутнє
            self.assertIsNone(got[0]['root'], repr(raw))
        self.assertIsNone(self.norm({'id': 'a'})[0]['root'])

    def test_root_system_dir_is_none(self):
        for r in ('/System', '/System/x', '/Library', '/Library/Caches/x', '/usr', '/usr/local/share', '/bin', '/sbin',
                  '/etc', '/etc/x', '/private', '/private/tmp/x', '/var', '/var/folders/x', '/Applications', '/Applications/X.app',
                  '/'):
            got = self.norm({'id': 'a', 'root': r, 'repo': 'g@e:s/w'})
            self.assertEqual((got[0]['id'], got[0]['root'], got[0]['repo']), ('a', None, 'g@e:s/w'), r)    # запис живий

    def test_root_home_system_dirs_are_none(self):
        """І2: правило `spaces` для шляху простору (`check_new_path`): у домівці `Library` (будь-який регістр) і приховані теки."""
        for r in ('~/.ssh', '~/.ssh/keys', '~/.config', '~/.hidden/x', '~/Library', '~/Library/x', '~/library/x', '~/LIBRARY',
                  os.path.join(self.home, '.ssh'), os.path.join(self.home, 'Library', 'Caches')):
            got = self.norm({'id': 'a', 'root': r, 'repo': 'g@e:s/w'})
            self.assertEqual((got[0]['id'], got[0]['root'], got[0]['repo']), ('a', None, 'g@e:s/w'), r)
        # звичайна тека в домівці й тека з крапкою ГЛИБШЕ — дозволені (як для простору)
        self.assertEqual(self.norm({'id': 'a', 'root': '~/work/.cache'})[0]['root'], os.path.join(self.home, 'work', '.cache'))

    def test_root_home_itself_and_its_ancestors_are_none(self):
        parent = os.path.dirname(self.home)
        for r in ('~', '~/', self.home, parent, '/', os.path.join(self.home, 'x', '..')):
            self.assertIsNone(self.norm({'id': 'a', 'root': r})[0]['root'], r)

    def test_root_symlink_to_home_hidden_dir_is_none(self):
        os.mkdir(os.path.join(self.home, '.secret'))
        os.symlink(os.path.join(self.home, '.secret'), os.path.join(self.home, 'pub'))
        self.assertIsNone(self.norm({'id': 'a', 'root': '~/pub'})[0]['root'])

    def test_root_length_cap(self):
        self.assertEqual(tracks.ROOT_MAX, 1024)
        ok = 'a/' * 511 + 'aa'                                            # рівно 1024 знаки
        long = 'a/' * 512 + 'aa'                                           # 1026
        self.assertEqual((len(ok), len(long)), (1024, 1026))
        self.assertEqual(self.norm({'id': 'a', 'root': ok})[0]['root'], os.path.join(self.space, ok))
        got = self.norm({'id': 'a', 'root': long, 'label': 'L'})
        self.assertEqual((got[0]['id'], got[0]['label'], got[0]['root']), ('a', 'L', None))     # запис живий, поле відсутнє
        self.assertIsNone(self.norm({'id': 'a', 'root': '/' + 'x' * 1030})[0]['root'])

    def test_root_not_a_system_dir_by_prefix_only(self):
        # `/usrlocal` — не підтека `/usr`: порівняння за межею компонента
        self.assertEqual(self.norm({'id': 'a', 'root': '/usrlocal/x'})[0]['root'], '/usrlocal/x')

    def test_root_relative_escape_into_system_is_none(self):
        # ⛔ нормалізація ДО перевірки: `../` з простору не обходить відсів
        self.assertIsNone(self.norm({'id': 'a', 'root': '../' * 40 + 'usr/bin'})[0]['root'])

    def test_root_symlink_into_system_is_none(self):
        link = os.path.join(self.home, 'sneaky')
        os.symlink('/usr', link)
        self.assertIsNone(self.norm({'id': 'a', 'root': link})[0]['root'])
        self.assertIsNone(self.norm({'id': 'a', 'root': 'x', 'repo': ''}, {'id': 'b', 'root': '~/sneaky/sub'})[1]['root'])

    def test_repo_rules(self):
        ok = {'git@example.com:studio/web.git': 'git@example.com:studio/web.git',
              '  ssh://git@example.com/o/r.git  ': 'ssh://git@example.com/o/r.git'}
        bad = ['-x', '--upload-pack=x', '', '   ', 'git@example.com:s/a b.git', 'git@example.com:s/\u0432.git', 5, None, ['x'], {}]
        for raw, want in ok.items():
            self.assertEqual(self.norm({'id': 'a', 'repo': raw})[0]['repo'], want, raw)
        for raw in bad:
            self.assertEqual(self.norm({'id': 'a', 'repo': raw})[0]['repo'], '', repr(raw))
        self.assertEqual(self.norm({'id': 'a'})[0]['repo'], '')

    def test_ds_rules(self):
        self.assertEqual(self.norm({'id': 'a', 'ds': 'united'})[0]['ds'], 'united')
        self.assertEqual(self.norm({'id': 'a', 'ds': 'a' * 32})[0]['ds'], 'a' * 32)
        for raw in ('', 'United', 'a_b', ' united', 'a' * 33, 5, None, ['x']):
            self.assertEqual(self.norm({'id': 'a', 'ds': raw})[0]['ds'], '', repr(raw))
        self.assertEqual(self.norm({'id': 'a'})[0]['ds'], '')

    def test_at_most_max_tracks_first_ones(self):
        self.assertEqual(tracks.MAX_TRACKS, 20)
        got = tracks.normalize([{'id': 'a%d' % i} for i in range(35)], self.space)
        self.assertEqual([t['id'] for t in got], ['a%d' % i for i in range(20)])

    def test_bad_records_do_not_eat_the_limit(self):
        raw = [5] * 30 + [{'id': 'a%d' % i} for i in range(25)]
        got = tracks.normalize(raw, self.space)
        self.assertEqual(len(got), 20)
        self.assertEqual(got[0]['id'], 'a0')

    def test_result_shape(self):
        got = self.norm({'id': 'web', 'label': 'Web', 'root': '~/work/web', 'repo': 'git@example.com:studio/web.git', 'ds': 'united'})
        self.assertEqual(got, [{'id': 'web', 'label': 'Web', 'root': os.path.join(self.home, 'work', 'web'),
                                'repo': 'git@example.com:studio/web.git', 'ds': 'united'}])
        self.assertEqual(list(got[0]), ['id', 'label', 'root', 'repo', 'ds'])

    def test_extra_keys_are_ignored(self):
        self.assertEqual(sorted(self.norm({'id': 'a', 'secret': 'x', 'default': True})[0]), ['ds', 'id', 'label', 'repo', 'root'])

    def test_never_raises_on_hostile_json(self):
        deep = cur = []
        for _ in range(100000):
            nxt = []
            cur.append(nxt)
            cur = nxt
        selfref = {}
        selfref['id'] = selfref
        selfref['label'] = selfref
        loop = []
        loop.append(loop)
        hostile = [deep, selfref, loop, [deep] * 10, {'id': 'a', 'label': deep, 'root': deep, 'repo': deep, 'ds': deep},
                   {'id': 'b', 'label': 'x' * 2000000, 'root': 'y' * 2000000, 'repo': 'z' * 2000000}, float('nan'), -1e308]
        got = tracks.normalize(hostile, self.space)
        self.assertEqual([t['id'] for t in got], ['a', 'b'])
        self.assertEqual(tracks.normalize(deep, self.space), [])
        for raw in (loop, selfref, float('inf'), b'bytes', object()):
            self.assertIsInstance(tracks.normalize(raw, self.space), list)

    def test_does_not_mutate_input(self):
        raw = [{'id': 'a', 'root': 'x', 'label': ' L '}, {'id': 'a'}]
        before = copy.deepcopy(raw)
        tracks.normalize(raw, self.space)
        self.assertEqual(raw, before)


class TaskTrack(unittest.TestCase):
    """`default_id`, `of_task`, `find`, `label_tag`: правила спеки §1, §6.2."""

    WEB = {'id': 'web', 'label': 'Web', 'root': None, 'repo': '', 'ds': ''}
    MOB = {'id': 'mobile', 'label': 'Мобільний', 'root': None, 'repo': '', 'ds': ''}
    TRACKS = [WEB, MOB]

    def test_default_id_from_list(self):
        self.assertEqual(tracks.default_id(self.TRACKS, 'mobile'), 'mobile')

    def test_default_id_unknown_falls_to_first(self):
        for raw in ('zzz', '', None, 5, ['web'], 'Web'):
            self.assertEqual(tracks.default_id(self.TRACKS, raw), 'web', repr(raw))

    def test_default_id_empty_is_none(self):
        self.assertIsNone(tracks.default_id([], 'web'))
        self.assertIsNone(tracks.default_id([], None))

    def test_of_task_prefers_track(self):
        self.assertEqual(tracks.of_task({'track': 'web', 'profile': 'seo'}), 'web')

    def test_of_task_ignores_profile(self):
        # 4d-4a: було `falls_back_to_profile` — `profile` у записах більше не читається (читає лише міграція та три межі)
        self.assertIsNone(tracks.of_task({'profile': 'seo'}))
        self.assertIsNone(tracks.of_task({'track': None, 'profile': 'seo'}))
        self.assertIsNone(tracks.of_task({'track': '', 'profile': 'seo'}))
        self.assertIsNone(tracks.of_task({'track': 5, 'profile': 'seo'}))

    def test_of_task_returns_the_stored_string_as_is(self):
        # без звірки з `ID_RE`: значення `track` вільне (`'United'`, з комою, довгий, з пробілами)
        for v in ('United', 'Bad,Comma', 'x' * 40, '  seo  ', ' ', 'a\tb'):
            self.assertEqual(tracks.of_task({'track': v}), v, repr(v))
            self.assertIsNone(tracks.of_task({'profile': v}), repr(v))       # було: `profile` віддавався як є

    def test_of_task_non_string_or_empty_is_none(self):
        for task in ({}, {'profile': ''}, {'profile': None}, {'profile': 5}, {'profile': ['united']}, {'track': 5},
                     {'track': ''}, {'track': '', 'profile': ''}, {'track': {}, 'profile': 5}):
            self.assertIsNone(tracks.of_task(task), repr(task))

    def test_of_task_not_a_dict_is_none(self):
        for task in (None, ['united'], 'united', 5):
            self.assertIsNone(tracks.of_task(task), repr(task))

    def test_find(self):
        self.assertIs(tracks.find(self.TRACKS, 'mobile'), self.MOB)
        self.assertIsNone(tracks.find(self.TRACKS, 'zzz'))
        self.assertIsNone(tracks.find(self.TRACKS, None))
        self.assertIsNone(tracks.find(self.TRACKS, 5))
        self.assertIsNone(tracks.find([], 'web'))

    def test_label_tag_known_track_uses_label(self):
        self.assertEqual(tracks.label_tag(self.TRACKS, {'track': 'mobile'}), 'Мобільний')
        self.assertIsNone(tracks.label_tag(self.TRACKS, {'profile': 'web'}))           # було 'Web': `profile` не читається

    def test_label_tag_unknown_id_is_the_id_itself(self):
        self.assertEqual(tracks.label_tag(self.TRACKS, {'track': 'zzz'}), 'zzz')
        self.assertEqual(tracks.label_tag([], {'track': 'zzz'}), 'zzz')

    def test_label_tag_unknown_id_passes_tag_rules(self):
        for v in ('Bad,Comma', 'x' * 40, 'a\tb', ' '):
            self.assertIsNone(tracks.label_tag(self.TRACKS, {'track': v}), repr(v))
        self.assertEqual(tracks.label_tag(self.TRACKS, {'track': '  a   b  '}), 'a b')

    def test_label_tag_no_track_is_none(self):
        for task in ({}, None, {'track': 5}, {'profile': ''}, ['web']):
            self.assertIsNone(tracks.label_tag(self.TRACKS, task), repr(task))

    def test_read_tag_rules(self):
        self.assertEqual(tracks.read_tag('  a   b '), 'a b')
        self.assertEqual(tracks.read_tag('x' * 32), 'x' * 32)
        for bad in ('x' * 33, '', '  ', 'a,b', 'a\nb', 'a\u202eb', 5, None, ['x']):
            self.assertIsNone(tracks.read_tag(bad), repr(bad))

    def test_repo_ok_rules(self):
        self.assertEqual(tracks.repo_ok('  git@example.com:s/w.git '), 'git@example.com:s/w.git')
        for bad in ('-x', '', ' ', 'a b', 'г', 5, None):
            self.assertEqual(tracks.repo_ok(bad), '', repr(bad))


class SourceHygiene(unittest.TestCase):
    """І1: у коді ядра немає «сирих» невидимих знаків (їх не видно в ревʼю; керівні клас ПРАВИЛА мітки записаний `\\uXXXX`)."""

    BAD = re.compile('[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff'
                     '\x00-\x08\x0b-\x1f\x7f-\x9f]')

    def test_tracks_source_has_no_raw_invisible_or_control_chars(self):
        with open(os.path.join(_APP, 'tracks.py'), encoding='utf-8') as f:
            src = f.read()
        found = [(src.count('\n', 0, m.start()) + 1, hex(ord(m.group()))) for m in self.BAD.finditer(src)]
        self.assertEqual(found, [])

    def test_tag_bad_pattern_is_written_escaped(self):
        with open(os.path.join(_APP, 'tracks.py'), encoding='utf-8') as f:
            line = [ln for ln in f if ln.startswith('TAG_BAD = ')][0]
        self.assertIn('\\u200b-\\u200f', line)
        self.assertTrue(tracks.TAG_BAD.search('a\u202eb') and tracks.TAG_BAD.search('a,b') and tracks.TAG_BAD.search('a\x85b'))



# ======================================================================== Task 3: сервер на напрямках

class _Plain(unittest.TestCase):
    """Шар просторів УВІМКНЕНО в тимчасовому `DEAI_HOME`: звичайний простір `Alpha` без інтеграцій (і, за потреби, простір
    ЛІГИ з прапорцем `integrations`). Репо — лише вигадані адреси; мережі нема (`GIT_SSH_COMMAND=false`, `DC_NO_OVERVIEW`)."""

    REPO = 'git@example.com:studio/web.git'
    OTHER = 'ssh://git@example.com/o/r.git'

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='srv-tracks-')
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)
        self.home = os.path.join(self.tmp, 'home')
        self.tool = os.path.join(self.home, 'tools', 'dc')
        os.makedirs(self.tool)
        self.deai = os.path.join(self.home, 'stuff', 'deai')
        self.legacy_file = os.path.join(self.tmp, 'legacy', 'tasks.json')
        p = mock.patch.dict(os.environ, {
            'HOME': self.home, 'DEAI_HOME': self.deai, 'DC_TASKS_FILE': self.legacy_file, 'DC_NO_OVERVIEW': '1',
            'DC_MIRRORS_DIR': os.path.join(self.tmp, 'mirrors'), 'DC_IDENTITY_NAME': 'Alpha',
            'DC_IDENTITY_EMAIL': 'alpha@example.com', 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_SSH_COMMAND': 'false', 'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@t',
            'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@t'})        # ⛔ літерал: його читає статичний охоронець
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(spaces, 'ROOT', self.tool)                      # тека інструмента — не в тимчасовій домівці
        q.start()
        self.addCleanup(q.stop)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        self.sp = self.make_space('Alpha')
        self.use(self.sp)

    def make_space(self, name, integrations=False):
        sid = spaces.create_space(name, 'space-1', os.path.join(self.home, 'work', name.lower()))
        if integrations:
            reg_file = os.path.join(self.deai, 'spaces.json')
            with open(reg_file, encoding='utf-8') as f:
                reg = json.load(f)
            for entry in reg['spaces']:
                if entry['id'] == sid:
                    entry['integrations'] = True
            with open(reg_file, 'w', encoding='utf-8') as f:
                json.dump(reg, f)
        return next(e for e in spaces.read_registry()['spaces'] if e['id'] == sid)

    def use(self, sp):
        spaces.set_request_space(sp['id'])

    def space_json(self, sp, **fields):
        """Дописати поля в `space.json` простору (`raw` — сирий текст замість JSON)."""
        path = os.path.join(sp['path'], 'space.json')
        raw = fields.pop('raw', None)
        if raw is not None:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(raw)
            return
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        data.update(fields)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def two_tracks(self, sp=None, **extra):
        sp = sp or self.sp
        self.space_json(sp, tracks=[{'id': 'web', 'label': 'Web', 'root': 'web-dir', 'repo': self.REPO, 'ds': 'united'},
                                    {'id': 'mobile'}], default_track='web', **extra)

    def legacy_cfg(self, **extra):
        cfg = {**gen._liga_cfg({'united': self.OTHER, 'seo': self.REPO}), **extra}
        gen._write(self.legacy_file, cfg)
        return cfg


class ServerTracks(_Plain):
    """`space_tracks`, `track_root`, `track_repo`, `task_ds`, `task_tags` і `task_new` у звичайному просторі й у просторі ЛІГИ."""

    # ---- space_tracks
    def test_an_ordinary_space_reads_its_space_json(self):
        self.two_tracks()
        tr, default = serve.space_tracks(self.sp)
        self.assertEqual(default, 'web')
        self.assertEqual([t['id'] for t in tr], ['web', 'mobile'])
        self.assertEqual(tr[0], {'id': 'web', 'label': 'Web', 'root': os.path.join(self.sp['path'], 'web-dir'),
                                 'repo': self.REPO, 'ds': 'united'})
        self.assertEqual(tr[1], {'id': 'mobile', 'label': 'mobile', 'root': None, 'repo': '', 'ds': ''})
        self.space_json(self.sp, default_track='mobile')
        self.assertEqual(serve.space_tracks(self.sp)[1], 'mobile')
        self.space_json(self.sp, default_track='zzz')                          # не з переліку — перший
        self.assertEqual(serve.space_tracks(self.sp)[1], 'web')

    def test_no_tracks_a_broken_file_or_a_non_list_is_nothing_for_an_ordinary_space(self):
        self.assertEqual(serve.space_tracks(self.sp), ([], None))              # `space.json` є, ключа `tracks` нема
        for raw in ('{не json', '[1]', '5', '{"tracks": 5}', '{"tracks": {"id": "web"}}', '{"tracks": []}'):
            with self.subTest(raw=raw):
                self.space_json(self.sp, raw=raw)
                self.assertEqual(serve.space_tracks(self.sp), ([], None))
        os.remove(os.path.join(self.sp['path'], 'space.json'))
        self.assertEqual(serve.space_tracks(self.sp), ([], None))
        self.assertEqual(serve.space_tracks(None), ([], None))

    # 4d-4a: ЛІГА читає ЛИШЕ свій `space.json`, як і будь-який простір. Було чотири тести адаптера (`…without_tracks_uses_the_adapter`,
    # `…does_not_get_the_adapter`, `layer_off_is_the_adapter`, `…broken_legacy_file_gives_the_bare_adapter`): їхня копія в
    # `tests/test_liga_adapter.py`, а тут — три тести про відсутність адаптера (спека, відмінність 1: «нема напрямків»).
    def test_a_liga_space_without_tracks_has_none_even_with_a_legacy_file(self):
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg()                                                      # корінь старого файла з коренями й репо — не читається
        self.assertEqual(serve.space_tracks(liga), ([], None))
        for raw in ('{не json', '[1]', '{"tracks": 5}', '{"name": "x"}'):      # ключа нема / не список / файл битий — напрямків нема
            with self.subTest(raw=raw):
                self.space_json(liga, raw=raw)
                self.assertEqual(serve.space_tracks(liga), ([], None))
        gen._write(self.legacy_file, '{not json')                              # зіпсований старий файл нічого не міняє
        self.assertEqual(serve.space_tracks(liga), ([], None))
        os.remove(self.legacy_file)
        self.assertEqual(serve.space_tracks(liga), ([], None))

    def test_a_liga_space_reads_its_own_tracks_and_an_empty_list_stays_empty(self):
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg()
        self.space_json(liga, tracks=[{'id': 'web'}], default_track='web')
        tr, default = serve.space_tracks(liga)
        self.assertEqual(([t['id'] for t in tr], default), (['web'], 'web'))
        self.space_json(liga, tracks=[])                                       # було: порожній перелік ЛІГИ вмикав адаптер (ревʼю 4d-1)
        self.assertEqual(serve.space_tracks(liga), ([], None))

    def test_layer_off_has_no_tracks(self):
        self.legacy_cfg()
        with mock.patch.dict(os.environ):
            os.environ.pop('DEAI_HOME')
            self.assertFalse(spaces.layer_on())
            self.assertEqual(serve.space_tracks(spaces.active_space()), ([], None))

    # ---- корінь напрямку в чужому просторі
    def test_a_root_in_another_space_is_dropped(self):
        beta = self.make_space('Beta')
        self.use(self.sp)
        outside = os.path.join(self.home, 'work', 'elsewhere')
        self.space_json(self.sp, tracks=[
            {'id': 'same', 'root': beta['path']},
            {'id': 'inside', 'root': os.path.join(beta['path'], 'sub')},
            {'id': 'own', 'root': 'own-sub'},
            {'id': 'ownself', 'root': self.sp['path']},
            {'id': 'out', 'root': outside}])
        got = {t['id']: t['root'] for t in serve.space_tracks(self.sp)[0]}
        self.assertEqual(got, {'same': None, 'inside': None, 'own': os.path.join(self.sp['path'], 'own-sub'),
                               'ownself': self.sp['path'], 'out': outside})
        # корінь, що пропав, — шлях простору (`track_root`), а не чужий
        self.assertEqual(serve.track_root(self.sp, 'same'), self.sp['path'])
        self.assertEqual(serve.track_root(self.sp, 'inside'), self.sp['path'])

    def test_the_overlap_check_does_not_touch_the_stored_tracks_of_the_other_space(self):
        """Простір Beta лежить у реєстрі, його напрямки читаються зі СВОГО `space.json` (кореня Alpha вони не стосуються)."""
        beta = self.make_space('Beta')
        self.space_json(beta, tracks=[{'id': 'b', 'root': os.path.join(self.sp['path'], 'sub')}])
        self.assertEqual(serve.space_tracks(beta)[0][0]['root'], None)         # корінь у Alpha — чужий для Beta
        self.two_tracks()
        self.assertEqual(serve.space_tracks(self.sp)[0][0]['root'], os.path.join(self.sp['path'], 'web-dir'))

    # ---- track_root / track_repo / task_ds
    def test_track_root_of_an_ordinary_space(self):
        self.two_tracks()
        web = os.path.join(self.sp['path'], 'web-dir')
        self.assertEqual(serve.track_root(self.sp, 'web'), web)
        self.assertEqual(serve.track_root(self.sp, 'mobile'), self.sp['path'])      # напрямок без `root` — шлях простору
        self.assertEqual(serve.track_root(self.sp, 'zzz'), web)                     # невідомий — `root` дефолтного
        self.assertEqual(serve.track_root(self.sp, None), web)
        self.space_json(self.sp, tracks=[])
        for tid in ('web', None):
            self.assertEqual(serve.track_root(self.sp, tid), self.sp['path'])       # напрямків нема — шлях простору

    def test_track_root_of_a_liga_space_is_the_same_as_of_any_space(self):
        # 4d-4a: було `…of_a_liga_space` — корінь із `design_work_roots` старого файла через адаптер; тепер ЛІГА — як усі: корінь
        # напрямку з її `space.json`, інакше шлях простору (спільний корінь старого файла більше не береться: відмінність спеки)
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg(design_work_roots={'united': '~/w/u', 'seo': '~/w/s'}, design_work_root='~/w/shared')
        for tid in ('united', 'seo', 'liga360', 'zzz', 'United', None):
            self.assertEqual(serve.track_root(liga, tid), liga['path'], tid)
        self.space_json(liga, tracks=[])
        self.assertEqual(serve.track_root(liga, 'web'), liga['path'])
        self.space_json(liga, tracks=[{'id': 'web', 'root': os.path.join(liga['path'], 'web')}])
        self.assertEqual(serve.track_root(liga, 'web'), os.path.join(liga['path'], 'web'))
        self.assertEqual(serve.track_root(liga, 'zzz'), os.path.join(liga['path'], 'web'))   # невідомий — дефолтний

    def test_track_root_without_a_space_is_none(self):
        self.assertIsNone(serve.track_root(None, 'web'))                           # викликач бере `default_task_root(cfg)`
        with mock.patch.dict(os.environ):
            os.environ.pop('DEAI_HOME')
            self.assertIsNone(serve.track_root(spaces.active_space(), 'united'))   # шар вимкнено: неявний простір без шляху

    def test_default_task_root(self):
        self.assertEqual(serve.default_task_root({'design_work_root': '~/w/shared'}), os.path.expanduser('~/w/shared'))
        for cfg in ({}, None, {'design_work_root': ''}, {'design_work_root': 5}, []):
            self.assertEqual(serve.default_task_root(cfg), os.path.expanduser('~/deai-work'), repr(cfg))

    def test_track_repo(self):
        self.two_tracks()
        self.assertEqual(serve.track_repo(self.sp, 'web'), self.REPO)
        for tid in ('mobile', 'zzz', None, 5):
            self.assertEqual(serve.track_repo(self.sp, tid), '', tid)         # невідомий НЕ береться з дефолтного
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg()                                                      # `profile_repos` старого файла більше не читається
        self.assertEqual((serve.track_repo(liga, 'united'), serve.track_repo(liga, 'seo')), ('', ''))
        self.space_json(liga, tracks=[{'id': 'united', 'repo': self.OTHER}, {'id': 'seo', 'repo': self.REPO}, {'id': 'liga360'}])
        self.assertEqual((serve.track_repo(liga, 'united'), serve.track_repo(liga, 'seo'), serve.track_repo(liga, 'liga360')),
                         (self.OTHER, self.REPO, ''))

    def test_task_ds_and_the_inspector_tail(self):
        self.two_tracks()
        sid = self.sp['id']
        for task, ds, tail in (({'track': 'web'}, 'united', f'?ds=united&sp={sid}'),
                               ({'profile': 'web'}, '', f'?sp={sid}'),                      # 4d-4a: було `united` — `profile` не читається
                               ({'track': 'mobile'}, '', f'?sp={sid}'),                     # `ds: ''` — лише `?sp=`
                               ({'track': 'zzz'}, 'zzz', f'?ds=zzz&sp={sid}'),             # напрямку нема — значення як є, як 0.14.0
                               ({}, '', f'?sp={sid}'), ({'track': 5}, '', f'?sp={sid}')):
            with self.subTest(task=task):
                self.assertEqual(serve.task_ds(task, self.sp), ds)
                self.assertEqual(serve.inspector_ds_arg(serve.task_ds(task, self.sp), self.sp), tail)
        self.assertEqual(serve.task_ds(None, self.sp), '')
        # збережений `track` без напрямку, що його називає, діє як у 0.14.0 (еталон `page-none-project.html`); було те саме для
        # `profile` — тепер запис лише з `profile` дає `''` (відмінність спеки 4: міграція дописує `track` ЛІГІ)
        self.assertEqual(serve.task_ds({'track': 'united'}, self.sp), 'united')
        self.assertEqual(serve.task_ds({'profile': 'united'}, self.sp), '')
        self.space_json(self.sp, tracks=[])
        self.assertEqual(serve.task_ds({'track': 'tool'}, self.sp), 'tool')
        self.assertEqual(serve.task_ds({'profile': 'tool'}, self.sp), '')

    def test_the_inspector_argument_is_the_ds_not_the_track(self):
        self.space_json(self.sp, tracks=[{'id': 'web', 'ds': 'liga360'}, {'id': 'plain'}])
        self.assertEqual(serve.task_ds({'track': 'web'}, self.sp), 'liga360')   # ДС напрямку, а не його id
        self.assertEqual(serve.task_ds({'track': 'plain'}, self.sp), '')
        self.assertEqual(next(iter(inspect.signature(serve.inspector_ds_arg).parameters)), 'ds')

    # ---- мітки
    def test_task_tags_of_an_ordinary_space_come_from_the_track_label(self):
        self.two_tracks()
        for task, want in (({'track': 'web'}, ['Web']), ({'profile': 'web'}, []), ({'track': 'mobile'}, ['mobile']),   # `profile` — 4d-4a: без мітки
                           ({'track': 'zzz'}, ['zzz']), ({'track': 'a,b'}, []), ({'track': 'web', 'tags': ['X']}, ['X']),
                           ({'track': 'web', 'tags': []}, []), ({}, []), ({'track': 5}, [])):
            with self.subTest(task=task):
                self.assertEqual(serve.task_tags(task, self.sp), want)
        # без `sp` — простір запиту
        self.assertEqual(serve.task_tags({'track': 'web'}), ['Web'])
        # `track` ЛІГИ в звичайному просторі НЕ перекладається таблицею адаптера
        self.assertEqual(serve.task_tags({'track': 'united'}, self.sp), ['united'])

    def test_task_tags_of_a_liga_space_come_from_its_own_tracks_not_from_the_adapter_table(self):
        # 4d-4a: було `…use_the_adapter_labels` (United/LIGA360/SEO з таблиці адаптера за `profile`). Тепер — підписи з `space.json`
        # простору, а де напрямків нема — значення `track` як є (нижній регістр: відмінність спеки, ЛІГА без напрямків)
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg()
        for prof, want in (('united', ['united']), ('liga360', ['liga360']), ('seo', ['seo']), ('zzz', ['zzz'])):
            self.assertEqual(serve.task_tags({'track': prof}, liga), want, prof)
            self.assertEqual(serve.task_tags({'profile': prof}, liga), [], prof)           # лише `profile` — без мітки
        self.space_json(liga, tracks=[{'id': 'united', 'label': 'United'}, {'id': 'seo', 'label': 'SEO'}])
        self.assertEqual([serve.task_tags({'track': t}, liga) for t in ('united', 'seo', 'zzz')], [['United'], ['SEO'], ['zzz']])
        self.space_json(liga, tracks=[{'id': 'united', 'label': 'Alpha team'}])            # власні напрямки — їхні підписи
        self.assertEqual(serve.task_tags({'track': 'united'}, liga), ['Alpha team'])

    # ---- task_new у звичайному просторі
    def fake_vcs(self, provider=True):
        """Підміна постачальника ролі `vcs`: повертає список викликів функцій ролі (`pull` з ціллю)."""
        calls = []

        def call(v, fn, *args, **kw):
            calls.append((fn, args))
            return {'found': False}
        prov = (object(), {'settings': {}}, False) if provider else None
        for patch in (mock.patch.object(serve, 'vcs_provider', return_value=prov),
                      mock.patch.object(serve, '_vcs_call', side_effect=call)):
            patch.start()
            self.addCleanup(patch.stop)
        return calls

    def new(self, tid, track, **kw):
        cfg = serve.load_tasks()
        res = serve.task_new(cfg, tid, title='Alpha', track=track, root=serve.track_root(self.sp, track),
                             repo=serve.track_repo(self.sp, track), **kw)
        return res, serve.load_tasks()['tasks'][tid]

    def test_a_task_in_a_track_lands_under_its_root_with_track_and_the_repo_as_vcs(self):
        self.two_tracks()
        calls = self.fake_vcs()
        res, entry = self.new('w1', 'web')
        self.assertEqual(res['dir'], os.path.join(self.sp['path'], 'web-dir', 'w1'))
        self.assertEqual((entry['track'], entry['dir']), ('web', res['dir']))
        self.assertIn('profile', entry)
        self.assertIsNone(entry['profile'])                                    # формат запису звичайного простору не міняється
        self.assertEqual(entry['vcs'], {'repo': self.REPO})
        self.assertNotIn('gitlab', entry)
        pulls = [a for fn, a in calls if fn == 'pull']
        self.assertEqual(len(pulls), 1)
        self.assertEqual((pulls[0][0]['repo'], pulls[0][0]['task']), (self.REPO, 'w1'))      # бутстрап кличе `pull` з репо напрямку

    def test_a_track_without_a_repo_gives_no_vcs_and_never_asks_the_provider(self):
        self.two_tracks()
        with mock.patch.object(serve, 'vcs_provider', side_effect=AssertionError('постачальник без репо')):
            res, entry = self.new('m1', 'mobile')
        self.assertEqual(res['dir'], os.path.join(self.sp['path'], 'm1'))
        self.assertEqual((entry['track'], entry['profile']), ('mobile', None))
        self.assertNotIn('vcs', entry)

    def test_an_explicit_vcs_beats_the_repo_of_the_track(self):
        self.two_tracks()
        calls = self.fake_vcs()
        _, entry = self.new('w2', 'web', vcs={'repo': self.OTHER})
        self.assertEqual(entry['vcs'], {'repo': self.OTHER})
        self.assertEqual([a[0]['repo'] for fn, a in calls if fn == 'pull'], [self.OTHER])

    def test_without_a_vcs_provider_the_repo_of_the_track_is_not_applied(self):
        self.two_tracks()
        calls = self.fake_vcs(provider=False)
        _, entry = self.new('w3', 'web')
        self.assertNotIn('vcs', entry)
        self.assertEqual(calls, [])
        self.assertEqual(entry['track'], 'web')

    def test_a_refusing_vcs_provider_does_not_block_the_task(self):
        self.two_tracks()
        with mock.patch.object(serve, 'vcs_provider', side_effect=serve.VcsError('vcs-error', 'нема модуля')):
            res, entry = self.new('w4', 'web')
        self.assertTrue(res['ok'])
        self.assertNotIn('vcs', entry)

    def test_a_task_without_a_track_is_as_before(self):
        self.two_tracks()
        cfg = serve.load_tasks()
        res = serve.task_new(cfg, 'p1', title='Alpha', root=self.sp['path'])
        entry = serve.load_tasks()['tasks']['p1']
        self.assertEqual((res['dir'], entry['profile']), (os.path.join(self.sp['path'], 'p1'), None))
        self.assertNotIn('track', entry)
        self.assertNotIn('vcs', entry)

    def test_a_liga_task_writes_profile_and_track_and_gets_the_gitlab_mapping_from_the_repo(self):
        liga = self.make_space('Liga', integrations=True)
        self.use(liga)
        self.space_json(liga, tracks=[{'id': 'web', 'repo': self.REPO}, {'id': 'plain'}], default_track='web')
        self.fake_vcs(provider=False)
        cfg = serve.load_tasks()
        serve.task_new(cfg, 'g1', title='Alpha', track='web', legacy=True, root=serve.track_root(liga, 'web'),
                       repo=serve.track_repo(liga, 'web'))
        entry = serve.load_tasks()['tasks']['g1']
        self.assertEqual((entry['profile'], entry['track']), ('web', 'web'))
        self.assertEqual(entry['gitlab'], {'repo': self.REPO, 'path': 'mockup/g1'})
        self.assertNotIn('vcs', entry)
        cfg = serve.load_tasks()
        serve.task_new(cfg, 'g2', title='Alpha', track='plain', legacy=True, root=serve.track_root(liga, 'plain'),
                       repo=serve.track_repo(liga, 'plain'))
        self.assertNotIn('gitlab', serve.load_tasks()['tasks']['g2'])
        cfg = serve.load_tasks()                                               # явний `gitlab` перемагає репо напрямку
        own = {'repo': self.OTHER, 'path': 'mockup/x'}
        serve.task_new(cfg, 'g3', title='Alpha', track='web', legacy=True, gitlab=own, root=serve.track_root(liga, 'web'),
                       repo=serve.track_repo(liga, 'web'))
        self.assertEqual(serve.load_tasks()['tasks']['g3']['gitlab'], own)


class ServerTrackView(_Plain):
    """Напрямки простору рахуються ОДИН раз на відповідь і щодо ПРАВИЛЬНОГО простору (ревʼю Task 3): `?all=1`, вартість
    циклу по задачах, ліниве питання простору, реєстр, що не читається, `task_ds` без простору."""

    def write_tasks(self, sp, tasks):
        with open(os.path.join(sp['path'], 'tasks.json'), 'w', encoding='utf-8') as f:
            json.dump({'tasks': tasks, 'current': next(iter(tasks))}, f)

    def two_spaces(self):
        """Alpha — звичайний, напрямок `web` з підписом `Web`; Liga — з `integrations` і ЯВНИМ напрямком `united` з підписом `United`
        (4d-4a: було — без `tracks`, підпис давав адаптер, задача мала лише `profile`)."""
        self.two_tracks()
        liga = self.make_space('Liga', integrations=True)
        self.space_json(liga, tracks=[{'id': 'united', 'label': 'United'}], default_track='united')
        self.write_tasks(self.sp, {'a1': {'track': 'web', 'dir': os.path.join(self.tmp, 'a1')}})
        self.write_tasks(liga, {'l1': {'track': 'united', 'dir': os.path.join(self.tmp, 'l1')}})
        return liga

    # ---- C1: `?all=1` — підписи щодо простору КОЖНОЇ задачі, а не того, хто кличе
    def test_all_spaces_rows_label_each_task_by_its_own_space_from_either_side(self):
        liga = self.two_spaces()
        for caller in (self.sp, liga):
            with self.subTest(caller=caller['id']):
                self.use(caller)
                rows = {r['id']: r for r in serve._all_space_task_rows()}
                self.assertEqual(rows['l1']['tags'], ['United'])            # з боку звичайного простору теж не `united`
                self.assertEqual(rows['a1']['tags'], ['Web'])               # з боку ЛІГИ теж не `web`
                self.assertEqual((rows['l1']['space'], rows['a1']['space']), (liga['id'], self.sp['id']))
                self.assertEqual(spaces.request_space_id(), caller['id'])   # простір того, хто кличе, повернуто

    def test_task_rows_take_the_space_explicitly(self):
        liga = self.two_spaces()
        self.use(self.sp)
        cfg = {'tasks': {'l1': {'track': 'united'}}}
        self.assertEqual(serve._task_rows(cfg, liga)[0]['tags'], ['United'])
        self.assertEqual(serve._task_rows(cfg)[0]['tags'], ['united'])      # без `sp` — простір запиту (звичайний)

    # ---- (ревʼю Task 3) `?all=1`: `try` лише над читанням і сортуванням, а не над складанням рядків
    def test_all_spaces_do_not_swallow_a_bug_in_the_label_computation(self):
        self.two_spaces()
        self.use(self.sp)
        for exc in (AttributeError('вада в мітці'), TypeError('вада в мітці')):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(serve, 'task_tags', side_effect=exc), \
                    self.assertRaises(type(exc)):
                serve._all_space_task_rows()                  # справжня вада не викидає ЦІЛИЙ простір зі списку мовчки

    def test_all_spaces_still_skip_a_space_whose_file_cannot_be_read_or_sorted(self):
        self.two_spaces()
        self.use(self.sp)
        real = serve.tasks_by_recent

        def sort(cfg):
            if 'a1' in cfg.get('tasks', {}):
                raise TypeError('порівняти не вдалось')
            return real(cfg)
        with mock.patch.object(serve, 'tasks_by_recent', sort):
            self.assertEqual([r['id'] for r in serve._all_space_task_rows()], ['l1'])      # Alpha пропущено, решта — на місці
        with open(os.path.join(self.sp['path'], 'tasks.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        self.assertEqual([r['id'] for r in serve._all_space_task_rows()], ['l1'])           # нечитабельний файл — теж

    def test_skipped_spaces_are_reported_next_to_the_rows(self):
        """0.40: клієнт мусить відрізнити «задачі нема» від «простір не прочитали» — пропущені id віддаються окремо."""
        self.two_spaces()
        self.use(self.sp)
        rows, skipped = serve._all_space_task_rows_ex()
        self.assertEqual(skipped, [])
        self.assertEqual(sorted(r['id'] for r in rows), ['a1', 'l1'])
        with open(os.path.join(self.sp['path'], 'tasks.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        rows, skipped = serve._all_space_task_rows_ex()
        self.assertEqual([r['id'] for r in rows], ['l1'])
        self.assertEqual(skipped, [self.sp['id']])
        self.assertEqual([r['id'] for r in serve._all_space_task_rows()], ['l1'])   # старий вигляд — лише рядки

    def test_a_liga_space_with_an_empty_or_all_bad_own_list_no_longer_uses_the_adapter(self):
        """4d-4a: було `…still_uses_the_adapter` (ревʼю 4d-1: `tracks: []` у ЛІГИ вмикав адаптер, щоб не спорожнити все). Адаптера
        нема, тож порожній чи зіпсований власний список ЛІГИ — як у будь-якому просторі: напрямків нема, мітка — значення `track`
        як є, корінь — шлях простору, репо немає."""
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg(design_work_roots={'united': os.path.join(self.home, 'u-root')})
        for own in ([], [5, None], [{'id': 'BAD ID'}], [{'id': 'x y'}, 'web']):
            with self.subTest(own=own):
                self.space_json(liga, tracks=own, default_track='zzz')
                self.assertEqual(serve.space_tracks(liga), ([], None))
                self.assertEqual(serve.task_tags({'track': 'united'}, liga), ['united'])
                self.assertEqual(serve.track_root(liga, 'united'), liga['path'])
                self.assertEqual(serve.track_repo(liga, 'seo'), '')
        self.space_json(liga, tracks=[{'id': 'web', 'label': 'Alpha team'}], default_track='web')      # непорожній — власний
        self.assertEqual([t['id'] for t in serve.space_tracks(liga)[0]], ['web'])
        self.assertEqual(serve.space_tracks(self.sp), ([], None))                                        # звичайний — як було

    # ---- I1: простір питається лише тоді, коли похідна мітка справді потрібна
    def test_the_request_space_is_not_asked_when_no_derived_tag_is_needed(self):
        self.use(self.sp)
        cfg = {'tasks': {'a': {'tags': ['X'], 'track': 'web', 'dir': self.tmp}, 'b': {'dir': self.tmp},
                         'c': {'profile': 5, 'dir': self.tmp}}}
        with mock.patch.object(serve, '_request_space', side_effect=AssertionError('простір без потреби')), \
                mock.patch.object(spaces, 'active_space', side_effect=AssertionError('реєстр без потреби')):
            self.assertEqual([r['tags'] for r in serve._task_rows(cfg)], [['X'], [], []])
            out = serve.tasks_overview(cfg, ([], None))
        self.assertEqual([m['tags'] for m in out['mine']], [['X'], [], []])

    # ---- I2: вартість не росте з кількістю задач
    def cost(self, n, space, call, **fields):
        cfg = {'tasks': {f't{i}': {**(fields or {'track': 'web'}), 'dir': os.path.join(self.tmp, f't{i}')} for i in range(n)}}
        with mock.patch.object(spaces, 'check_new_path', wraps=spaces.check_new_path) as chk, \
                mock.patch.object(serve, '_own_tracks', wraps=serve._own_tracks) as own:
            tags = call(cfg, space)
        return (chk.call_count, own.call_count), tags

    def test_the_cost_of_labels_does_not_grow_with_the_number_of_tasks(self):
        liga = self.two_spaces()
        self.use(self.sp)
        by_rows = lambda cfg, sp: [r['tags'] for r in serve._task_rows(cfg, sp)]                   # noqa: E731
        by_overview = lambda cfg, sp: [m['tags'] for m in serve.tasks_overview(cfg, ([], None))['mine']]   # noqa: E731
        for name, call in (('_task_rows', by_rows), ('tasks_overview', by_overview)):
            with self.subTest(call=name):
                few, tags_few = self.cost(3, self.sp, call)
                many, tags_many = self.cost(30, self.sp, call)
                self.assertEqual(few, many)                                  # не росте з N
                self.assertEqual((few[0], few[1]), (0, 1))                   # `space.json` прочитали раз, коренів не перевіряли (ревʼю 4d-1)
                self.assertEqual((tags_few, tags_many), ([['Web']] * 3, [['Web']] * 30))
        few, _ = self.cost(3, liga, by_rows, track='united')                 # ЛІГА теж явна (4d-4a): те саме `(0, 1)`, без адаптера
        many, tags = self.cost(30, liga, by_rows, track='united')
        self.assertEqual((few, many), ((0, 1), (0, 1)))
        self.assertEqual(tags, [['United']] * 30)

    def test_labels_and_ds_never_check_roots(self):
        """⛔ Ревʼю 4d-1: `task_tags`/`task_ds` потрібні лише `id`/`label`/`ds`, тож корені (`realpath` + реєстр) не перевіряються —
        ні на одну задачу, ні на цикл; `track_root`/`space_tracks` перевіряють (контроль нижче)."""
        liga = self.two_spaces()
        self.space_json(liga, tracks=[{'id': 'web', 'label': 'W', 'root': 'web-dir', 'ds': 'united'}])
        for sp in (self.sp, liga):
            view = serve._TrackView(sp)
            with mock.patch.object(spaces, 'check_new_path', side_effect=AssertionError('корінь без потреби')), \
                    mock.patch.object(spaces, 'read_registry', side_effect=AssertionError('реєстр без потреби')):
                self.assertEqual(serve.task_tags({'track': 'web'}, view), ['Web' if sp is self.sp else 'W'])
                self.assertEqual(serve.task_ds({'track': 'web'}, view), 'united')
                self.assertEqual(serve.task_tags({'track': 'web'}, sp), ['Web' if sp is self.sp else 'W'])
        with mock.patch.object(spaces, 'check_new_path', wraps=spaces.check_new_path) as chk:
            self.assertEqual(serve.track_root(self.sp, 'web'), os.path.join(self.sp['path'], 'web-dir'))
        self.assertGreaterEqual(chk.call_count, 1)

    def test_all_spaces_build_the_view_once_per_space(self):
        self.two_spaces()
        self.use(self.sp)
        with mock.patch.object(serve, '_own_tracks', wraps=serve._own_tracks) as own:
            rows = serve._all_space_task_rows()
        self.assertEqual((len(rows), own.call_count), (2, 2))               # по одному читанню `space.json` на простір

    # ---- m1: реєстр, що не читається, — корені відкидаються (закрито), а не обвал
    def test_a_broken_registry_drops_the_roots_and_a_missing_one_does_not(self):
        self.two_tracks()
        reg = os.path.join(self.deai, 'spaces.json')
        keep = os.path.join(self.sp['path'], 'web-dir')
        self.assertEqual(serve.space_tracks(self.sp)[0][0]['root'], keep)
        with open(reg, 'rb') as f:
            good = f.read()
        for raw in (b'{broken', b'[]', b'5', b'', b'{"version": 1, "spaces": "x"}', b'{"version": 2, "spaces": []}',
                    b'{"version": 1, "spaces": [5]}'):
            with self.subTest(raw=raw):
                with open(reg, 'wb') as f:
                    f.write(raw)
                tr, default = serve.space_tracks(self.sp)
                self.assertEqual((default, [t['root'] for t in tr]), ('web', [None, None]))
                self.assertEqual(serve.track_root(self.sp, 'web'), self.sp['path'])
        os.remove(reg)                                                      # реєстру нема зовсім — це не відмова
        self.assertEqual(serve.space_tracks(self.sp)[0][0]['root'], keep)
        with open(reg, 'wb') as f:
            f.write(good)

    # ---- m3: простору нема — значення як було
    def test_task_ds_without_a_space_is_the_raw_value(self):
        spaces.set_request_space('')                                        # запит «без простору»
        self.assertIsNone(spaces.active_space())
        self.assertEqual(serve.task_ds({'track': 'tool'}, None), 'tool')
        self.assertEqual(serve.task_ds({'profile': 'tool'}, None), '')          # 4d-4a: було 'tool' — `profile` не читається
        self.assertEqual(serve.task_ds({'track': 'tool'}), 'tool')
        self.assertEqual(serve.task_ds({}, None), '')
        self.assertEqual(serve.task_ds({'track': 5}, None), '')


# ======================================================================== Task 4: API

def _tree(path):
    """Знімок теки: відносні шляхи всього, що в ній лежить (теки й файли) — «нічого не створено» перевіряється порівнянням."""
    out = []
    for dirpath, dirs, files in os.walk(path):
        out += [os.path.relpath(os.path.join(dirpath, n), path) for n in dirs + files]
    return sorted(out)


def _raw(path):
    try:
        with open(path, 'rb') as f:
            return f.read()
    except OSError:
        return None


class ApiTracks(_Plain):
    """HTTP-API напрямків (Task 4): `task-new`, `/api/tasks`, `/api/task`, `/api/spaces` — крізь справжній сервер у процесі."""

    def setUp(self):
        super().setUp()
        self.srv = gen.Server().__enter__()
        self.addCleanup(self.srv.__exit__, None, None, None)
        for patch in (mock.patch.object(serve, 'vcs_provider', gen.Vcs()),             # без `vcs`-ролі, без git
                      mock.patch.object(serve.urllib.request, 'urlopen', gen.NoNet())):
            patch.start()
            self.addCleanup(patch.stop)

    def post(self, body, sp=None):
        sp = sp or self.sp
        return self.srv.req('POST', '/api/task-new', {'space': sp['id'], **body})

    def entry(self, sp, tid):
        with open(os.path.join(sp['path'], 'tasks.json'), encoding='utf-8') as f:
            return json.load(f)['tasks'].get(tid)

    def snapshot(self, sp):
        return _tree(sp['path']), _raw(os.path.join(sp['path'], 'tasks.json'))

    def liga(self):
        """Простір ЛІГИ з ЯВНИМИ напрямками в `space.json` (4d-4a: було — адаптер з кореня старого `tasks.json`, ключі якого тут
        дублювались у `tasks.json` простору). Ті самі id, підписи, репо; корені — відносні (у теці простору: `~/work/…` старого файла
        лежав би в чужому «legacy»-просторі й відкидався б)."""
        liga = self.make_space('Liga', integrations=True)
        self.space_json(liga, tracks=[{'id': 'united', 'label': 'United', 'root': 'united-dir', 'repo': self.OTHER, 'ds': 'united'},
                                      {'id': 'liga360', 'label': 'LIGA360', 'ds': 'liga360'},
                                      {'id': 'seo', 'label': 'SEO', 'root': 'seo-dir', 'repo': self.REPO, 'ds': 'seo'}],
                        default_track='united',
                        # 4d-4c: «ЛІГА» (`gitlab`-маппінг, `profile` у записі) — це явний запис `git-sync` зі схемою `design-canvas`, а не прапорець
                        modules={'git-sync': {'enabled': True, 'shared_state': True,
                                              'settings': dict(liga_fixture.ROLE_RECORDS['vcs'][1])}})
        return liga

    # ---- звичайний простір: напрямок у тілі
    def test_track_places_the_task_in_the_track(self):
        self.two_tracks()
        st, body = self.post({'id': 'w1', 'track': 'web'})
        self.assertEqual((st, body.get('ok')), (200, True), body)
        e = self.entry(self.sp, 'w1')
        self.assertEqual((e['track'], e['profile']), ('web', None))
        self.assertEqual(e['dir'], os.path.join(self.sp['path'], 'web-dir', 'w1'))
        st, _ = self.post({'id': 'm1', 'track': 'mobile'})
        self.assertEqual(st, 200)
        self.assertEqual(self.entry(self.sp, 'm1')['dir'], os.path.join(self.sp['path'], 'm1'))      # без `root` — шлях простору

    def test_profile_is_a_synonym_of_track(self):
        self.two_tracks()
        st, body = self.post({'id': 's1', 'profile': 'web'})
        self.assertEqual((st, body.get('ok')), (200, True), body)
        e = self.entry(self.sp, 's1')
        self.assertEqual((e['track'], e['dir']), ('web', os.path.join(self.sp['path'], 'web-dir', 's1')))
        self.assertEqual(self.post({'id': 's2', 'track': 'web', 'profile': 'web'})[0], 200)            # обидва однакові — ок
        self.assertEqual(self.entry(self.sp, 's2')['track'], 'web')
        self.assertEqual(self.post({'id': 's3', 'track': None, 'profile': 'mobile'})[0], 200)          # `null` — поля нема
        self.assertEqual(self.entry(self.sp, 's3')['track'], 'mobile')
        self.assertEqual(self.post({'id': 's4', 'track': '', 'profile': 'mobile'})[0], 200)
        self.assertEqual(self.entry(self.sp, 's4')['track'], 'mobile')

    def test_no_field_takes_the_default_track(self):
        self.two_tracks()
        for tid, extra in (('d1', {}), ('d2', {'track': None}), ('d3', {'track': ''}), ('d4', {'profile': None})):
            self.assertEqual(self.post({'id': tid, **extra})[0], 200, tid)
            e = self.entry(self.sp, tid)
            self.assertEqual((e['track'], e['dir']), ('web', os.path.join(self.sp['path'], 'web-dir', tid)), tid)

    def test_a_space_without_tracks_keeps_todays_behaviour(self):
        st, _ = self.post({'id': 'p1'})
        self.assertEqual(st, 200)
        e = self.entry(self.sp, 'p1')
        self.assertEqual((e['dir'], e['profile']), (os.path.join(self.sp['path'], 'p1'), None))
        self.assertNotIn('track', e)

    def test_conflict_and_bad_values_are_refused_before_any_write(self):
        self.two_tracks()
        before = self.snapshot(self.sp)
        cases = (({'track': 'web', 'profile': 'mobile'}, 'bad-track'), ({'track': 5}, 'bad-track'),
                 ({'track': ['web']}, 'bad-track'), ({'track': 'Bad!'}, 'bad-track'), ({'track': 'Web'}, 'bad-track'),
                 ({'track': 'x' * 33}, 'bad-track'),
                 ({'profile': 5}, 'bad-profile'), ({'track': 'web', 'profile': 5}, 'bad-profile'))
        for extra, code in cases:
            st, body = self.post({'id': 'x1', **extra})
            self.assertEqual((st, body.get('code')), (400, code), extra)
            self.assertEqual(self.snapshot(self.sp), before, extra)

    def test_an_unknown_track_is_refused_before_any_write(self):
        self.two_tracks()
        before = self.snapshot(self.sp)
        for extra in ({'track': 'nope'}, {'track': 'nope', 'profile': 'nope'}, {'track': 'nope', 'profile': 'Bad!'}):
            st, body = self.post({'id': 'u1', **extra})
            self.assertEqual((st, body.get('code')), (400, 'unknown-track'), extra)       # `profile`, що не напрямок, не рятує
            self.assertEqual(self.snapshot(self.sp), before, extra)                # ні теки, ні `tasks.json`
            self.assertFalse(os.path.exists(os.path.join(self.sp['path'], 'web-dir')), extra)

    def test_no_tracks_configured_and_a_track_in_the_body_is_unknown(self):
        before = self.snapshot(self.sp)
        st, body = self.post({'id': 'u2', 'track': 'x'})
        self.assertEqual((st, body.get('code')), (400, 'unknown-track'))
        self.assertEqual(self.snapshot(self.sp), before)

    def test_the_order_of_checks(self):
        self.two_tracks()
        # `unknown-track` — до решти перевірок тіла: поганий id задачі, `vcs` без ролі, `gitlab` у просторі без інтеграцій
        for body in ({'id': 'bad id', 'track': 'nope'}, {'id': 'o1', 'track': 'nope', 'vcs': {'repo': self.REPO}},
                     {'id': 'o2', 'track': 'nope', 'gitlab': {'repo': self.REPO}}):
            st, resp = self.post(body)
            self.assertEqual((st, resp.get('code')), (400, 'unknown-track'), body)
        # `bad-track` / `bad-profile` — до `bad-tags` і до `unknown-track`
        st, resp = self.post({'id': 'o3', 'track': 5, 'tags': ['a,b']})
        self.assertEqual((st, resp.get('code')), (400, 'bad-track'))
        st, resp = self.post({'id': 'o4', 'profile': 5, 'track': 'nope'})
        self.assertEqual((st, resp.get('code')), (400, 'bad-profile'))
        st, resp = self.post({'id': 'o5', 'track': 'mobile', 'profile': 'web'})
        self.assertEqual((st, resp.get('code')), (400, 'bad-track'))                # конфлікт, а не `unknown-track`
        # решта — як була: ПОГАНІ мітки й далі 400 `bad-tags`, а дублікат id — 400 `task-exists`
        self.assertEqual(self.post({'id': 'o6', 'track': 'web', 'tags': ['a,b']})[1].get('code'), 'bad-tags')
        self.assertEqual(self.post({'id': 'o7', 'track': 'web'})[0], 200)
        self.assertEqual(self.post({'id': 'o7', 'track': 'web'})[1].get('code'), 'task-exists')

    # ---- `profile` — застарілий ключ: у звичайному просторі, що не є напрямком, він ІГНОРУЄТЬСЯ, як у 0.14.0
    def test_a_profile_that_is_not_a_track_is_ignored_in_a_space_with_tracks(self):
        self.two_tracks()
        for i, profile in enumerate(('nope', 'united', 'United', 'tool', 'Bad!', 'x' * 40, 'mobile-extra', ' web')):
            tid = f'i{i}'
            st, body = self.post({'id': tid, 'profile': profile})
            self.assertEqual((st, body.get('ok')), (200, True), (profile, body))
            e = self.entry(self.sp, tid)
            self.assertEqual((e['track'], e['profile']), ('web', None), profile)           # у напрямок за замовчуванням, `profile` — null
            self.assertEqual(e['dir'], os.path.join(self.sp['path'], 'web-dir', tid), profile)

    def test_a_profile_is_ignored_in_a_space_without_tracks_exactly_as_in_0_14_0(self):
        for i, profile in enumerate(('united', 'tool', 'United', 'Bad!', 'x' * 40)):
            tid = f'z{i}'
            st, body = self.post({'id': tid, 'profile': profile})
            self.assertEqual((st, body.get('ok')), (200, True), (profile, body))
            e = self.entry(self.sp, tid)
            self.assertEqual((e['dir'], e['profile']), (os.path.join(self.sp['path'], tid), None), profile)
            self.assertNotIn('track', e)
        self.assertEqual(self.post({'id': 'z9', 'profile': 5})[1].get('code'), 'bad-profile')   # не рядок — як було

    def test_the_conflict_is_only_about_a_profile_that_would_be_used(self):
        self.two_tracks()
        before = self.snapshot(self.sp)
        for body in ({'track': 'mobile', 'profile': 'web'}, {'track': 'web', 'profile': 'mobile'},
                     {'track': 'nope', 'profile': 'web'}):                     # профіль — напрямок простору і різний: конфлікт
            st, resp = self.post({'id': 'k1', **body})
            self.assertEqual((st, resp.get('code')), (400, 'bad-track'), body)
            self.assertEqual(self.snapshot(self.sp), before, body)
        # профіль, що був би проігнорований, рішення не міняє: вирішує один `track`
        for i, profile in enumerate(('nope', 'United', 'united', 'Bad!')):
            tid = f'k{i + 2}'
            st, resp = self.post({'id': tid, 'track': 'mobile', 'profile': profile})
            self.assertEqual((st, resp.get('ok')), (200, True), (profile, resp))
            e = self.entry(self.sp, tid)
            self.assertEqual((e['track'], e['profile']), ('mobile', None), profile)
        st, resp = self.post({'id': 'k9', 'track': 'nope', 'profile': 'united'})            # `track` суворий і тут
        self.assertEqual((st, resp.get('code')), (400, 'unknown-track'))
        self.assertEqual(self.post({'id': 'k10', 'track': 'web', 'profile': 'web'})[0], 200)   # однакові — ок

    def test_in_a_space_without_tracks_a_strict_track_beats_an_ignored_profile(self):
        before = self.snapshot(self.sp)
        for body in ({'track': 'x', 'profile': 'united'}, {'track': 'united', 'profile': 'united'}):
            st, resp = self.post({'id': 'k11', **body})
            self.assertEqual((st, resp.get('code')), (400, 'unknown-track'), body)
            self.assertEqual(self.snapshot(self.sp), before, body)

    def test_a_foreign_origin_is_refused_first(self):
        import http.client
        self.two_tracks()
        before = self.snapshot(self.sp)
        conn = http.client.HTTPConnection('127.0.0.1', self.srv.port, timeout=15)
        try:
            conn.request('POST', '/api/task-new', body=json.dumps({'id': 'f1', 'track': 5, 'profile': 'nope'}).encode(),
                         headers={'Origin': 'http://evil.example', 'Content-Type': 'application/json'})
            self.assertEqual(conn.getresponse().status, 403)
        finally:
            conn.close()
        self.assertEqual(self.snapshot(self.sp), before)

    # ---- простір ЛІГИ: суворо, як усі (4d-4a, відмінність спеки 1)
    def test_a_liga_space_takes_a_known_track_and_writes_profile_and_track(self):
        # було `…takes_any_string…`: `profile: 'United'` → запис `United`, `track: 'zzz'` → запис `zzz`. Тепер `profile`, що не є
        # напрямком, ігнорується (задача — у напрямок за замовчуванням), а `track` суворий (див. наступний тест)
        liga = self.liga()
        for tid, extra, want in (('l1', {'profile': 'seo'}, 'seo'), ('l2', {'track': 'seo'}, 'seo'),
                                 ('l3', {'profile': 'United'}, 'united'), ('l4', {'profile': 'zzz'}, 'united'),
                                 ('l6', {'track': 'seo', 'profile': 'seo'}, 'seo'), ('l7', {'track': 'seo', 'profile': ''}, 'seo')):
            st, body = self.post({'id': tid, **extra}, liga)
            self.assertEqual((st, body.get('ok')), (200, True), (tid, body))
            e = self.entry(liga, tid)
            self.assertEqual((e['profile'], e['track']), (want, want), tid)            # `profile` у записі лишається (колеги на 0.14–0.19)
        self.assertEqual(self.entry(liga, 'l1')['dir'], os.path.join(liga['path'], 'seo-dir', 'l1'))
        # ⛔ не `.replace('l1', 'l2')` по всьому шляху: випадкове імʼя тимчасової теки (`srv-tracks-l1…`) інколи містить `l1` — тест мигав у повному прогоні
        self.assertEqual(self.entry(liga, 'l2')['dir'], os.path.join(liga['path'], 'seo-dir', 'l2'))
        self.assertEqual(self.entry(liga, 'l1')['gitlab']['repo'], self.REPO)

    def test_a_liga_space_refuses_an_unknown_or_malformed_track(self):
        liga = self.liga()
        before = self.snapshot(liga)
        for extra, code in (({'track': 'zzz'}, 'unknown-track'), ({'track': 'United'}, 'bad-track'),
                            ({'track': 'Bad!'}, 'bad-track'), ({'track': 'zzz', 'profile': ''}, 'unknown-track')):
            st, body = self.post({'id': 'lu', **extra}, liga)
            self.assertEqual((st, body.get('code')), (400, code), extra)
            self.assertEqual(self.snapshot(liga), before, extra)

    def test_a_liga_space_defaults_to_united(self):
        liga = self.liga()
        for tid, extra in (('d1', {}), ('d2', {'track': None}), ('d3', {'track': ''}), ('d4', {'profile': ''}),
                           ('d5', {'profile': None, 'track': None})):
            self.assertEqual(self.post({'id': tid, **extra}, liga)[0], 200, tid)
            e = self.entry(liga, tid)
            self.assertEqual((e['profile'], e['track']), ('united', 'united'), tid)

    def test_a_liga_space_refuses_a_non_string_or_a_conflict(self):
        liga = self.liga()
        before = self.snapshot(liga)
        for extra, code in (({'track': 5}, 'bad-track'), ({'track': {}}, 'bad-track'),
                            ({'track': 'seo', 'profile': 'united'}, 'bad-track'), ({'profile': 5}, 'bad-profile')):
            st, body = self.post({'id': 'lx', **extra}, liga)
            self.assertEqual((st, body.get('code')), (400, code), extra)
            self.assertEqual(self.snapshot(liga), before, extra)

    def test_a_liga_space_with_its_own_tracks_now_says_unknown_track(self):
        # було `…still_never_says_unknown_track`: `track: 'anything'` писався як є — тепер 400 (відмінність спеки 1)
        liga = self.make_space('Liga', integrations=True)
        self.space_json(liga, tracks=[{'id': 'web'}], default_track='web')
        before = self.snapshot(liga)
        st, body = self.post({'id': 'n1', 'track': 'anything'}, liga)
        self.assertEqual((st, body.get('code')), (400, 'unknown-track'), body)
        self.assertEqual(self.snapshot(liga), before)
        self.assertEqual(self.post({'id': 'n2'}, liga)[0], 200)
        self.assertEqual(self.entry(liga, 'n2')['track'], 'web')

    def test_a_liga_space_without_tracks_writes_no_track_and_lands_in_the_space(self):
        # відмінність спеки 4: немігрована ЛІГА — без напрямків, нова задача лягає в теку простору; будь-який `track` — unknown-track
        liga = self.make_space('Liga', integrations=True)
        self.assertEqual(self.post({'id': 'm1', 'track': 'seo'}, liga)[1].get('code'), 'unknown-track')
        st, body = self.post({'id': 'm2', 'profile': 'seo'}, liga)                         # `profile`, що не напрямок, ігнорується
        self.assertEqual((st, body.get('ok')), (200, True), body)
        self.assertEqual(self.entry(liga, 'm2')['dir'], os.path.join(liga['path'], 'm2'))
        self.assertIsNone(self.entry(liga, 'm2').get('track'))

    # ---- GET /api/tasks, GET /api/task
    def seed(self, sp, specs):
        tasks = {}
        for tid, extra in specs:
            d = os.path.join(self.tmp, 'seed', tid)
            os.makedirs(d)
            with open(os.path.join(d, 'iterations.json'), 'w', encoding='utf-8') as f:
                json.dump({'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00'}], 'publish_url': None}, f)
            tasks[tid] = {'dir': d, 'title': 'Seed ' + tid, 'jira': '', **extra}
        with open(os.path.join(sp['path'], 'tasks.json'), 'w', encoding='utf-8') as f:
            json.dump({'tasks': tasks, 'current': specs[0][0]}, f)
        spaces.switch_space(sp['id'])

    SPECS = (('a-track', {'track': 'web'}), ('a-profile', {'profile': 'mobile'}), ('a-both', {'track': 'web', 'profile': 'x'}),
             ('a-none', {}), ('a-five', {'track': 5, 'profile': 'mobile'}), ('a-empty', {'track': '', 'profile': 'web'}))
    # 4d-4a: `profile` з API прибрано, а `track` читається лише з `track` (було: `a-profile` → 'mobile', `a-five`/`a-empty` теж)
    WANT = {'a-track': 'web', 'a-profile': None, 'a-both': 'web', 'a-none': None, 'a-five': None, 'a-empty': None}

    def test_tasks_and_task_carry_track_and_no_profile(self):
        self.two_tracks()
        self.seed(self.sp, self.SPECS)
        st, body = self.srv.req('GET', '/api/tasks')
        self.assertEqual(st, 200, body)
        rows = {r['id']: r for r in body['tasks']}
        self.assertEqual(sorted(rows), sorted(self.WANT))
        for tid, track in self.WANT.items():
            self.assertIn('track', rows[tid])
            self.assertNotIn('profile', rows[tid], tid)
            self.assertEqual(rows[tid]['track'], track, tid)
            st, one = self.srv.req('GET', '/api/task', task=tid)                       # задачу вибирає заголовок, не `?id=`
            self.assertEqual(st, 200, one)
            self.assertNotIn('profile', one, tid)
            self.assertEqual(one['track'], track, tid)
        st, body = self.srv.req('GET', '/api/tasks?all=1')
        self.assertEqual({r['id']: r['track'] for r in body['tasks']}, self.WANT)

    # ---- GET /api/spaces
    def test_spaces_listing_names_the_tracks_but_not_their_roots_or_repos(self):
        self.two_tracks()
        plain = self.make_space('Plain')
        liga = self.liga()
        self.legacy_cfg()                                     # корінь старого файла з репо — теж у тілі не зустрічається
        st, raw = self.srv.req('GET', '/api/spaces', raw_text=True)
        self.assertEqual(st, 200)
        listed = {s['id']: s for s in json.loads(raw)['spaces']}
        a = listed[self.sp['id']]
        self.assertEqual(a['tracks'], [{'id': 'web', 'label': 'Web'}, {'id': 'mobile', 'label': 'mobile'}])
        self.assertEqual(a['default_track'], 'web')
        self.assertEqual(listed[liga['id']]['tracks'], [{'id': 'united', 'label': 'United'}, {'id': 'liga360', 'label': 'LIGA360'},
                                                        {'id': 'seo', 'label': 'SEO'}])
        self.assertEqual(listed[liga['id']]['default_track'], 'united')
        self.assertEqual((listed[plain['id']]['tracks'], listed[plain['id']]['default_track']), ([], None))
        for e in listed.values():
            self.assertTrue(all(sorted(t) == ['id', 'label'] for t in e['tracks']), e['tracks'])
        # ні корені напрямків, ні репо (у `space.json` і в кореневому `tasks.json` ЛІГИ) у тілі не зустрічаються
        for secret in ('web-dir', self.REPO, self.OTHER, 'git@example.com', 'ssh://git@example.com', '"root"', '"repo"',
                       os.path.join(self.home, 'work', 'seo'), os.path.join(self.home, 'work', 'united')):
            self.assertNotIn(secret, raw, secret)

    def test_spaces_listing_builds_the_tracks_once_per_space(self):
        self.two_tracks()
        self.make_space('Plain')
        self.liga()
        with mock.patch.object(serve, '_own_tracks', wraps=serve._own_tracks) as own:
            out = serve.spaces_listing()
        self.assertGreaterEqual(len(out['spaces']), 3)                              # Alpha, Plain, Liga (+ можливий «legacy»)
        self.assertEqual(own.call_count, len(out['spaces']))                        # по одному читанню `space.json` на простір
        self.assertFalse(hasattr(serve, '_legacy_cfg'))                             # 4d-4a: кореня старого файла рантайм не читає

    def test_spaces_listing_checks_no_roots_at_all(self):
        """⛔ Ревʼю Task 4: листинг віддає лише `id` і `label`, а корінь на відімкненому чи повільному томі міг би підвісити
        `GET /api/spaces` — тож ні `check_new_path` (диск, `realpath`), ні зайвий `read_registry()` на простір, ні
        `_drop_foreign_roots` у листингу не кличуться; результат (id, підписи, дефолт) — той самий, що з перевірками."""
        self.two_tracks()
        self.make_space('Plain')
        self.liga()
        with mock.patch.object(spaces, 'check_new_path', wraps=spaces.check_new_path) as check, \
                mock.patch.object(spaces, 'read_registry', wraps=spaces.read_registry) as reg, \
                mock.patch.object(serve, '_drop_foreign_roots', wraps=serve._drop_foreign_roots) as drop:
            out = serve.spaces_listing()
            reads_with_tracks = reg.call_count
        self.assertEqual(check.call_count, 0, 'корені напрямків не перевіряються')
        self.assertEqual(drop.call_count, 0)
        listed = {e['id']: e for e in out['spaces']}
        a = listed[self.sp['id']]
        self.assertEqual(a['tracks'], [{'id': 'web', 'label': 'Web'}, {'id': 'mobile', 'label': 'mobile'}])
        self.assertEqual(a['default_track'], 'web')
        # читань реєстру стільки ж, скільки без жодного напрямку: простори не додають своїх
        self.space_json(self.sp, tracks=[])
        with mock.patch.object(spaces, 'read_registry', wraps=spaces.read_registry) as reg:
            serve.spaces_listing()
        self.assertEqual(reads_with_tracks, reg.call_count)

    def test_a_track_view_with_roots_still_checks_them(self):
        """Контроль до тесту вище: звичайний `_TrackView` (без `roots=False`) перевірки робить — інакше «не кличуться» нічого не доводило б."""
        self.two_tracks()
        with mock.patch.object(spaces, 'check_new_path', wraps=spaces.check_new_path) as check:
            view = serve._TrackView(self.sp)
            self.assertEqual([t['id'] for t in view.tracks], ['web', 'mobile'])
        self.assertGreaterEqual(check.call_count, 1)
        self.assertIsNotNone(view.tracks[0]['root'])

    def test_the_layer_off_listing_is_unchanged(self):
        with mock.patch.dict(os.environ):
            os.environ.pop('DEAI_HOME', None)
            self.assertEqual(serve.spaces_listing(), {'current': None, 'spaces': [], 'off': True})


class ApiTracksImplicitSpace(_LayerOff):
    """Шар вимкнено (неявний простір ЛІГИ): нові сценарії маршруту порівнюються з тими, що вже знято, — `track` ≡ `profile`."""

    def setUp(self):
        super().setUp()
        for name in gen.CLEAN:
            if name not in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
                os.environ.pop(name, None)
        gen._write(os.environ['DC_TASKS_FILE'], gen._liga_cfg(gen.REPOS))
        for patch in (mock.patch.object(serve, 'vcs_provider', gen.Vcs()),
                      mock.patch.object(serve.urllib.request, 'urlopen', gen.NoNet())):
            patch.start()
            self.addCleanup(patch.stop)
        self.srv = gen.Server().__enter__()
        self.addCleanup(self.srv.__exit__, None, None, None)

    def tasks(self):
        return serve.load_tasks()['tasks']

    # 4d-4a: у режимі «шар вимкнено» напрямків нема (адаптер зник): три тести про `track ≡ profile` переписано під це.
    def test_a_profile_is_ignored_and_nothing_is_written_as_a_track(self):
        # було `…track_is_the_same_as_profile`: `profile: 'seo'` і `track: 'seo'` давали ідентичні записи з `track == profile`
        for name, body in (('seo', {'profile': 'seo'}), ('united', {'profile': 'united'}), ('zzz', {'profile': 'zzz'}),
                           ('upper', {'profile': 'United'}), ('none', {}), ('empty', {'profile': ''}), ('null', {'profile': None})):
            st, resp = self.srv.req('POST', '/api/task-new', {'id': 'p-' + name, 'title': 'T', **body})
            self.assertEqual(st, 200, (name, resp))
            e = self.tasks()['p-' + name]
            self.assertIsNone(e.get('track'), name)
            self.assertIsNone(e.get('profile'), name)
            self.assertNotIn('gitlab', e, name)                                     # `profile_repos` старого файла не читається
            self.assertEqual(os.path.dirname(e['dir']), os.path.expanduser('~/work/shared'), name)   # `design_work_root` файла

    def test_conflict_and_any_track_are_refused_before_any_write(self):
        # було `…and_unknown_is_never_refused`: `track: 'never-heard'` писався як є — тепер `unknown-track` (відмінність спеки 1/4)
        before = _raw(os.environ['DC_TASKS_FILE'])
        for extra, code in (({'track': 'seo', 'profile': 'united'}, 'unknown-track'), ({'track': 5}, 'bad-track'),
                            ({'profile': 5}, 'bad-profile'), ({'track': 'never-heard'}, 'unknown-track'),
                            ({'track': 'United'}, 'bad-track')):
            st, body = self.srv.req('POST', '/api/task-new', {'id': 'c1', **extra})
            self.assertEqual((st, body.get('code')), (400, code), extra)
            self.assertEqual(_raw(os.environ['DC_TASKS_FILE']), before, extra)

    def test_tasks_rows_carry_track_and_the_label_is_the_value(self):
        for name in ('r1', 'r2'):
            os.makedirs(os.path.join(self.home, name))
        cfg = serve.load_tasks()
        cfg['tasks']['r1'] = {'dir': os.path.join(self.home, 'r1'), 'title': 'R', 'track': 'seo'}
        cfg['tasks']['r2'] = {'dir': os.path.join(self.home, 'r2'), 'title': 'R', 'profile': 'seo'}
        gen._write(os.environ['DC_TASKS_FILE'], cfg)
        st, body = self.srv.req('GET', '/api/tasks')
        rows = {r['id']: r for r in body['tasks']}
        self.assertEqual((rows['r1']['track'], rows['r1']['tags']), ('seo', ['seo']))       # було ['SEO']: підпис адаптера зник
        self.assertEqual((rows['r2']['track'], rows['r2']['tags']), (None, []))              # лише `profile` — без мітки
        self.assertNotIn('profile', rows['r1'])
        st, one = self.srv.req('GET', '/api/task', task='r1')
        self.assertEqual(one['track'], 'seo')
        self.assertNotIn('profile', one)


class OfTaskTrackOnly(_Plain):
    """4d-4a (спека §3): `of_task` читає ЛИШЕ `track`; `profile` у записах не читається ні ядром, ні API, ні мітками, ні `?ds=`.
    Мутація «`of_task` знову падає на `profile`» червоніє тут (і в `TaskTrack`)."""

    def test_of_task_never_reads_profile(self):
        self.assertIsNone(tracks.of_task({'profile': 'united'}))
        self.assertEqual(tracks.of_task({'track': 'seo', 'profile': 'united'}), 'seo')
        self.assertIsNone(tracks.of_task({'track': '', 'profile': 'united'}))     # порожній `track` НЕ відкриває `profile`
        self.assertIsNone(tracks.of_task({'track': 5, 'profile': 'united'}))

    def test_label_tag_has_no_legacy_parameter(self):
        self.assertEqual(list(inspect.signature(tracks.label_tag).parameters), ['tracks', 'task'])
        self.assertIsNone(tracks.label_tag([], {'profile': 'united'}))

    def test_the_api_has_no_profile_key_but_has_track(self):
        self.two_tracks()
        d = os.path.join(self.tmp, 'ot', 'a-2')
        os.makedirs(d)
        with open(os.path.join(self.sp['path'], 'tasks.json'), 'w', encoding='utf-8') as f:
            json.dump({'tasks': {'a-1': {'dir': d, 'title': 'T', 'track': 'web', 'profile': 'web'},
                                 'a-2': {'dir': d, 'title': 'T', 'profile': 'web'}}, 'current': 'a-1'}, f)
        spaces.switch_space(self.sp['id'])
        srv = gen.Server().__enter__()
        self.addCleanup(srv.__exit__, None, None, None)
        st, body = srv.req('GET', '/api/tasks')
        rows = {r['id']: r for r in body['tasks']}
        self.assertEqual((st, sorted(rows)), (200, ['a-1', 'a-2']))
        for tid, want in (('a-1', 'web'), ('a-2', None)):
            self.assertIn('track', rows[tid])
            self.assertNotIn('profile', rows[tid], tid)
            self.assertEqual(rows[tid]['track'], want, tid)
            st, one = srv.req('GET', '/api/task', task=tid)
            self.assertEqual(st, 200, one)
            self.assertNotIn('profile', one, tid)
            self.assertEqual(one['track'], want, tid)

    def test_a_profile_only_record_has_no_label_and_no_ds_in_an_ordinary_space(self):
        self.two_tracks()
        plain = {'profile': 'web'}                                                 # виміряно на прототипі: стенд `plain`, `a-2`
        self.assertEqual(serve.task_tags(plain, self.sp), [])
        self.assertEqual(serve.task_ds(plain, self.sp), '')
        self.assertEqual(serve.task_tags({'track': 'web', 'profile': 'zzz'}, self.sp), ['Web'])
        self.assertEqual(serve.task_ds({'track': 'web', 'profile': 'zzz'}, self.sp), 'united')


class ServerHygiene(unittest.TestCase):
    """Ядро сервера не знає імен напрямків ЛІГИ; прибране справді прибране; обгортки названі й підписані."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(_APP, 'serve.py'), encoding='utf-8') as f:
            cls.src = f.read()

    def test_serve_py_does_not_know_the_liga_track_names(self):
        """І коментарі теж: імена `united`/`liga360`/`seo` живуть лише в `tracks.py` (адаптер)."""
        self.assertEqual([m.group() for m in re.finditer(r'united|liga360|seo', self.src, re.I)], [])

    def test_the_removed_names_are_gone(self):
        for name in ('_LEGACY_PROFILE_TAGS', '_PROFILE_KEY', '_REPO_OK', '_TAG_BAD', '_clean_tag', '_read_tag', 'TAG_MAX_LEN',
                     'FALLBACK_WORK_ROOT'):
            self.assertFalse(hasattr(serve, name), name)

    def test_work_root_and_the_adapter_wrappers_are_gone(self):
        """`work_root` прибрано в 4d-1 (`bin/` перейшов на `tracks`); 4d-4a прибрав і `profile_repos`, `_legacy_cfg` (було:
        `…the_one_wrapper_is_thin_and_marked` — `profile_repos` лишалась обгорткою «до 4d-4»)."""
        self.assertFalse(hasattr(serve, 'work_root'))
        self.assertFalse(hasattr(serve, 'profile_repos'))
        self.assertFalse(hasattr(serve, '_legacy_cfg'))
        for name in ('roots.py', 'registry.py', 'state.py'):          # `bin/` не дублює логіку коренів і не бере її з `serve`
            with open(os.path.join(os.path.dirname(_APP), 'bin', name), encoding='utf-8') as f:
                text = f.read()
            self.assertNotIn('serve.work_root', text, name)
            self.assertNotIn('import load_tasks, save_tasks, work_root', text, name)
            self.assertNotRegex(text, r"get\('profile'\)", name)

    def test_the_tag_rules_are_the_ones_of_tracks(self):
        self.assertNotIn('re.compile(', self.src[self.src.index('TAGS_MAX = 10'):self.src.index('class TagsError')])
        self.assertEqual(serve.normalize_tags([' a   b ']), [tracks.clean_tag('a   b')])
        for bad in ('a,b', 'a‮b', 'x' * (tracks.TAG_MAX_LEN + 1)):
            with self.assertRaises(serve.TagsError):
                serve.normalize_tags([bad])


if __name__ == '__main__':
    unittest.main()
