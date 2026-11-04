"""Напрямки простору (етап 4d-1, спека 2026-11-04-space-tracks-design.md).

Тут: знімок поведінки 0.14.0 (`Before4d1Shape`, Task 1) і ядро `app/tracks.py` (Task 2: `Normalize`, `TaskTrack`,
`LegacyTracks`, `LegacyParity` — паритет ЛІГИ зі знімком через `tracks`), Task 3: сервер на напрямках (`ServerLegacyParity` —
диференційні тести ЛІГИ проти знімка через справжній `serve`, `ServerTracks` — звичайний простір, `ServerHygiene`). Наступні
задачі додають класи (API), що читають той самий JSON.
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
        # `registry._work_root` = `serve.work_root`
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

    def test_of_task_falls_back_to_profile(self):
        self.assertEqual(tracks.of_task({'profile': 'seo'}), 'seo')
        self.assertEqual(tracks.of_task({'track': None, 'profile': 'seo'}), 'seo')
        self.assertEqual(tracks.of_task({'track': '', 'profile': 'seo'}), 'seo')
        self.assertEqual(tracks.of_task({'track': 5, 'profile': 'seo'}), 'seo')

    def test_of_task_returns_the_stored_string_as_is(self):
        # без звірки з `ID_RE`: ЛІГА приймає будь-який рядок (`'United'`, з комою, довгий, з пробілами)
        for v in ('United', 'Bad,Comma', 'x' * 40, '  seo  ', ' ', 'a\tb'):
            self.assertEqual(tracks.of_task({'profile': v}), v, repr(v))
            self.assertEqual(tracks.of_task({'track': v}), v, repr(v))

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
        self.assertEqual(tracks.label_tag(self.TRACKS, {'profile': 'web'}), 'Web')

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

    def test_label_tag_legacy_uses_table_then_value(self):
        self.assertEqual(tracks.label_tag([], {'profile': 'united'}, legacy=True), 'United')
        self.assertEqual(tracks.label_tag([], {'profile': 'liga360'}, legacy=True), 'LIGA360')
        self.assertEqual(tracks.label_tag([], {'track': 'seo'}, legacy=True), 'SEO')
        self.assertEqual(tracks.label_tag([], {'profile': 'zzz'}, legacy=True), 'zzz')
        self.assertEqual(tracks.label_tag([], {'profile': 'Seo'}, legacy=True), 'Seo')
        self.assertIsNone(tracks.label_tag([], {'profile': 'Bad,Comma'}, legacy=True))
        self.assertIsNone(tracks.label_tag([], {}, legacy=True))

    def test_label_tag_legacy_ignores_tracks_labels(self):
        # адаптер ЛІГИ: значення — вільний рядок; підпис — таблиця адаптера, а не `label` з переданого переліку
        t = [{'id': 'united', 'label': 'Інший', 'root': None, 'repo': '', 'ds': ''}]
        self.assertEqual(tracks.label_tag(t, {'profile': 'united'}, legacy=True), 'United')
        self.assertEqual(tracks.label_tag(t, {'profile': 'united'}), 'Інший')

    def test_legacy_labels_table(self):
        self.assertEqual(tracks._LEGACY_LABELS, {'united': 'United', 'liga360': 'LIGA360', 'seo': 'SEO'})

    def test_read_tag_rules(self):
        self.assertEqual(tracks.read_tag('  a   b '), 'a b')
        self.assertEqual(tracks.read_tag('x' * 32), 'x' * 32)
        for bad in ('x' * 33, '', '  ', 'a,b', 'a\nb', 'a\u202eb', 5, None, ['x']):
            self.assertIsNone(tracks.read_tag(bad), repr(bad))

    def test_repo_ok_rules(self):
        self.assertEqual(tracks.repo_ok('  git@example.com:s/w.git '), 'git@example.com:s/w.git')
        for bad in ('-x', '', ' ', 'a b', 'г', 5, None):
            self.assertEqual(tracks.repo_ok(bad), '', repr(bad))


class LegacyTracks(_Home):
    """Адаптер ЛІГИ `legacy_tracks(cfg)` (спека §2, §6): перелік, `root`, `repo`, `label`, `ds`, дефолт, `fallback_root`."""

    def test_constants(self):
        self.assertEqual(tracks.ID_RE.pattern, '[a-z0-9-]{1,32}')
        self.assertEqual(tracks.FALLBACK_ROOT, '~/deai-work')

    def test_nothing_gives_three_tracks_and_default_united(self):
        tr, d, fb = tracks.legacy_tracks({})
        self.assertEqual([t['id'] for t in tr], ['united', 'liga360', 'seo'])
        self.assertEqual(d, 'united')
        self.assertEqual(fb, os.path.join(self.home, 'deai-work'))
        self.assertEqual([t['label'] for t in tr], ['United', 'LIGA360', 'SEO'])
        self.assertEqual([t['ds'] for t in tr], ['united', 'liga360', 'seo'])
        self.assertEqual({t['root'] for t in tr}, {fb})
        self.assertEqual({t['repo'] for t in tr}, {''})

    def test_result_shape(self):
        tr, d, fb = tracks.legacy_tracks({})
        self.assertEqual(list(tr[0]), ['id', 'label', 'root', 'repo', 'ds'])

    def test_ids_order_and_no_duplicates(self):
        cfg = {'design_work_roots': {'seo': '~/a', 'zeta': '~/b', 'alpha': '~/c'},
               'profile_repos': {'alpha': 'git@e:s/w', 'beta': 'git@e:s/w', 'united': 'git@e:s/w'}}
        tr, _, _ = tracks.legacy_tracks(cfg)
        self.assertEqual([t['id'] for t in tr], ['united', 'liga360', 'seo', 'zeta', 'alpha', 'beta'])

    def test_ids_only_by_id_re(self):
        cfg = {'design_work_roots': {'United': '~/a', 'a_b': '~/b', '': '~/c', 'x' * 33: '~/d', 'ok': '~/e', 5: '~/f'},
               'profile_repos': {'Bad!': 'git@e:s/w', 'fine-1': 'git@e:s/w'}}
        tr, _, _ = tracks.legacy_tracks(cfg)
        self.assertEqual([t['id'] for t in tr], ['united', 'liga360', 'seo', 'ok', 'fine-1'])

    def test_root_own_then_shared_then_fallback(self):
        cfg = {'design_work_root': '~/work/shared', 'design_work_roots': {'united': '~/work/united', 'seo': ''}}
        tr, _, fb = tracks.legacy_tracks(cfg)
        by = {t['id']: t['root'] for t in tr}
        self.assertEqual(by, {'united': os.path.join(self.home, 'work/united'), 'liga360': os.path.join(self.home, 'work/shared'),
                              'seo': os.path.join(self.home, 'work/shared')})
        self.assertEqual(fb, os.path.join(self.home, 'work/shared'))

    def test_root_is_expanded_not_tilde(self):
        tr, _, fb = tracks.legacy_tracks({'design_work_root': '~/x', 'design_work_roots': {'seo': '/srv/seo'}})
        self.assertFalse(any(t['root'].startswith('~') for t in tr) or fb.startswith('~'))
        self.assertEqual({t['id']: t['root'] for t in tr}['seo'], '/srv/seo')

    def test_repo_from_profile_repos_only_if_valid_and_stripped(self):
        cfg = {'profile_repos': {'united': '  ssh://git@example.com/o/r.git  ', 'seo': '-x', 'liga360': 'a b', 'extra': 'git@e:s/w'}}
        tr, _, _ = tracks.legacy_tracks(cfg)
        self.assertEqual({t['id']: t['repo'] for t in tr},
                         {'united': 'ssh://git@example.com/o/r.git', 'liga360': '', 'seo': '', 'extra': 'git@e:s/w'})

    def test_label_table_or_id(self):
        tr, _, _ = tracks.legacy_tracks({'design_work_roots': {'zzz': '~/z'}})
        self.assertEqual({t['id']: t['label'] for t in tr}, {'united': 'United', 'liga360': 'LIGA360', 'seo': 'SEO', 'zzz': 'zzz'})

    def test_ds_is_the_id(self):
        tr, _, _ = tracks.legacy_tracks({'design_work_roots': {'zzz': '~/z'}})
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
            tr, d, fb = tracks.legacy_tracks(cfg)
            self.assertEqual([t['id'] for t in tr][:3], ['united', 'liga360', 'seo'], repr(cfg)[:60])
            self.assertEqual(d, 'united')
            self.assertEqual(fb, os.path.join(self.home, 'deai-work'), repr(cfg)[:60])

    def test_non_string_roots_fall_back_to_the_next_link(self):
        """Відмінність від 0.14.0 (там `TypeError` у `expanduser`): не рядок — як відсутнє, діє наступна ланка ланцюга."""
        shared, deai = os.path.join(self.home, 'work/shared'), os.path.join(self.home, 'deai-work')
        for bad in (5, ['x'], {'a': 1}, True, 1.5):
            cfg = {'design_work_root': '~/work/shared', 'design_work_roots': {'united': bad, 'seo': '~/work/seo'}}
            self.assertEqual(tracks.legacy_root(cfg, 'united'), shared, repr(bad))          # власний не рядок → спільний
            self.assertEqual(tracks.legacy_root(cfg, 'seo'), os.path.join(self.home, 'work/seo'))
            tr, _, fb = tracks.legacy_tracks(cfg)
            self.assertEqual((tracks.find(tr, 'united')['root'], fb), (shared, shared), repr(bad))
            cfg = {'design_work_root': bad, 'design_work_roots': {'united': 5, 'seo': '~/work/seo'}}
            self.assertEqual(tracks.legacy_root(cfg, 'united'), deai, repr(bad))             # і власний, і спільний не рядки
            self.assertEqual(tracks.legacy_root(cfg, 'zzz'), deai, repr(bad))
            self.assertEqual(tracks.legacy_root(cfg, 'seo'), os.path.join(self.home, 'work/seo'))
            self.assertEqual(tracks.legacy_tracks(cfg)[2], deai, repr(bad))

    def test_design_work_roots_not_a_dict_is_shared_root(self):
        """Свідома відмінність від 0.14.0 (спека §6.4): там `AttributeError` (500), тут — спільний корінь."""
        cfg = {'design_work_root': '~/work/shared', 'design_work_roots': ['united']}
        tr, _, fb = tracks.legacy_tracks(cfg)
        shared = os.path.join(self.home, 'work/shared')
        self.assertEqual(fb, shared)
        self.assertEqual({t['root'] for t in tr}, {shared})
        for p in ('united', 'seo', None, ''):
            self.assertEqual(tracks.legacy_root(cfg, p), shared)

    def test_fallback_root_is_shared_not_the_default_tracks_root(self):
        """Спека §6.1: напрямок без власного кореня → `fallback_root`, а НЕ корінь дефолтного `united`."""
        cfg = {'design_work_root': '~/work/shared', 'design_work_roots': {'united': '~/work/united'}}
        tr, d, fb = tracks.legacy_tracks(cfg)
        self.assertEqual(d, 'united')
        self.assertNotEqual(fb, tracks.find(tr, 'united')['root'])
        self.assertEqual(fb, os.path.join(self.home, 'work/shared'))

    def test_legacy_root_non_identifier_key_is_still_honoured(self):
        # `work_root` 0.14.0 брав `roots.get(profile)` для БУДЬ-ЯКОГО рядка, зокрема не за `ID_RE`: адаптер зберігає це
        cfg = {'design_work_root': '~/s', 'design_work_roots': {'United': '~/big'}}
        self.assertEqual(tracks.legacy_root(cfg, 'United'), os.path.join(self.home, 'big'))
        self.assertEqual(tracks.legacy_root(cfg, 'united'), os.path.join(self.home, 's'))
        self.assertNotIn('United', [t['id'] for t in tracks.legacy_tracks(cfg)[0]])

    def test_legacy_root_odd_values(self):
        cfg = {'design_work_root': '~/s', 'design_work_roots': {'united': '~/u'}}
        s = os.path.join(self.home, 's')
        for v in (None, 5, ['united'], {}, b'united', '', 'zzz'):
            self.assertEqual(tracks.legacy_root(cfg, v), s, repr(v))

    def test_legacy_repos_not_a_dict_and_bad_cfg(self):
        for cfg in (None, [], 'x', {}, {'profile_repos': None}, {'profile_repos': ['united']}, {'profile_repos': 'united'}):
            self.assertEqual(tracks.legacy_repos(cfg), {}, repr(cfg))


class LegacyParity(_LayerOff):
    """⛔ Паритет ЛІГИ зі знімком 0.14.0: кожен сценарій `roots` / `repos` / `tags` через `tracks`."""

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
                self.assertEqual(tracks.legacy_root(sc['cfg'], prof), self._expect_path(row['result']), (name, key))
                n += 1
        self.assertGreaterEqual(n, 40)

    def test_roots_through_legacy_tracks(self):
        """Те саме через перелік адаптера: напрямок з переліку → його `root`, будь-що інше → `fallback_root`."""
        for name, sc in self.snap['roots'].items():
            if name == 'fallback_constant':
                continue
            tr, _, fb = tracks.legacy_tracks(sc['cfg'])
            for key, row in sc['by_profile'].items():
                if 'raised' in row:
                    continue
                t = tracks.find(tr, None if key == 'None' else key)
                got = t['root'] if t else fb
                self.assertEqual(got, self._expect_path(row['result']), (name, key))

    def test_roots_fallback_constant(self):
        self.assertEqual(tracks.FALLBACK_ROOT, self.snap['roots']['fallback_constant'])

    def test_roots_not_a_dict_deliberate_difference(self):
        """0.14.0: `AttributeError` для КОЖНОГО профілю. Тепер (спека §6.4) — спільний корінь, без винятку."""
        sc = self.snap['roots']['roots_not_dict']
        self.assertEqual({r.get('raised') for r in sc['by_profile'].values()}, {'AttributeError'})
        shared = self._expect_path(sc['cfg']['design_work_root'])
        for key in sc['by_profile']:
            self.assertEqual(tracks.legacy_root(sc['cfg'], None if key == 'None' else key), shared, key)
        tr, _, fb = tracks.legacy_tracks(sc['cfg'])
        self.assertEqual(fb, shared)
        self.assertEqual({t['root'] for t in tr}, {shared})

    def test_roots_edge_values_are_covered(self):
        """Крайні значення знімка не загубилися: `'United'`, `''`, `None`, невідомий, свій/спільний/порожній корінь."""
        both = self.snap['roots']['both']['by_profile']
        self.assertTrue({'United', '', 'None', 'zzz', 'united', 'seo', 'liga360'} <= set(both))
        cfg = self.snap['roots']['both']['cfg']
        shared = self._expect_path(cfg['design_work_root'])
        for p in ('United', '', None, 'zzz', 'liga360'):
            self.assertEqual(tracks.legacy_root(cfg, p), shared, repr(p))
        self.assertEqual(tracks.legacy_root(cfg, 'united'), self._expect_path(cfg['design_work_roots']['united']))
        empty = self.snap['roots']['empty_value']['cfg']                 # `united: ''` → спільний, не фолбек
        self.assertEqual(tracks.legacy_root(empty, 'united'), self._expect_path(empty['design_work_root']))

    def test_repos_through_legacy_repos_and_tracks(self):
        n = 0
        for name, sc in self.snap['repos'].items():
            want = sc['result']['result']
            cfg = sc.get('cfg')                                            # `no_file` / `not_json` — конфігу нема
            self.assertEqual(tracks.legacy_repos(cfg), want, name)
            tr, _, _ = tracks.legacy_tracks(cfg)
            self.assertEqual({t['id']: t['repo'] for t in tr if t['repo']}, want, name)
            n += 1
        self.assertEqual(n, 17)

    def test_repos_for_every_listed_id(self):
        sc = self.snap['repos']['good_pairs']
        tr, _, _ = tracks.legacy_tracks(sc['cfg'])
        for t in tr:
            self.assertEqual(t['repo'], sc['result']['result'].get(t['id'], ''), t['id'])

    def test_tags_every_scenario(self):
        """⛔ Кожен сценарій `tags` знімка — через СПРАВЖНІЙ `serve.task_tags` (раніше тут був свій цикл, що лише імітував
        його): шар вимкнено, простір ЛІГИ неявний — те саме, що віддавав 0.14.0."""
        self.assertEqual(len(self.snap['tags']), 24)
        sp = spaces.active_space()
        for name, sc in self.snap['tags'].items():
            self.assertEqual(serve.task_tags(sc['task'], sp), sc['result']['result'], name)
            self.assertEqual(serve.task_tags(sc['task']), sc['result']['result'], name)       # без `sp` — простір запиту

    def test_tags_derived_without_tags_key_only_through_label_tag(self):
        """Сценарії без ключа `tags` (11 + крайні): рівно `label_tag(legacy=True)`, тобто `_LEGACY_LABELS` + правила мітки."""
        n = 0
        for name, sc in self.snap['tags'].items():
            task = sc['task']
            if isinstance(task, dict) and 'tags' in task:
                continue
            tag = tracks.label_tag([], task, legacy=True)
            self.assertEqual([tag] if tag else [], sc['result']['result'], name)
            n += 1
        self.assertGreaterEqual(n, 16)

    def test_tags_edge_profiles(self):
        t = self.snap['tags']
        self.assertEqual(t["no_tags_profile_'zzz'"]['result']['result'], ['zzz'])
        self.assertEqual(tracks.label_tag([], {'profile': 'zzz'}, legacy=True), 'zzz')
        self.assertIsNone(tracks.label_tag([], {'profile': 5}, legacy=True))                 # числовий профіль
        self.assertIsNone(tracks.label_tag([], {'profile': ''}, legacy=True))
        self.assertIsNone(tracks.label_tag([], {'profile': 'x' * 40}, legacy=True))


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

class ServerLegacyParity(_LayerOff):
    """⛔ ДИФЕРЕНЦІЙНІ тести: ЛІГА (неявний простір, шар вимкнено) через СПРАВЖНІЙ `serve` дає те, що знімок 0.14.0, — тека,
    репо, мітки, `?ds=`, рядки маршруту, `bin/`. Єдині відмінності — свідомі й названі окремими тестами (`track` у записі,
    числовий профіль у сторінці, `design_work_roots` не словник)."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def setUp(self):
        super().setUp()
        for name in gen.CLEAN:
            if name not in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
                os.environ.pop(name, None)
        self.sp = spaces.active_space()

    def _tmp(self):
        d = tempfile.TemporaryDirectory(prefix='srv-tracks-')
        self.addCleanup(d.cleanup)
        return os.path.realpath(d.name)

    def test_the_implicit_space_gets_the_adapter_tracks(self):
        cfg = gen._liga_cfg(gen.REPOS)
        gen._write(os.environ['DC_TASKS_FILE'], cfg)
        self.assertIsNone(spaces.describe(self.sp))                         # неявний простір — шар вимкнено
        tr, default = serve.space_tracks(self.sp)
        self.assertEqual((tr, default), tracks.legacy_tracks(cfg)[:2])
        self.assertEqual((default, [t['id'] for t in tr]), ('united', ['united', 'liga360', 'seo']))

    def test_roots_through_track_root_and_the_thin_wrapper(self):
        n = 0
        for name, sc in self.snap['roots'].items():
            if name == 'fallback_constant':
                continue
            for key, row in sc['by_profile'].items():
                if 'raised' in row:
                    continue
                prof = None if key == 'None' else key
                want = os.path.expanduser(row['result'])
                self.assertEqual(serve.track_root(self.sp, sc['cfg'], prof), want, (name, key))
                self.assertEqual(serve.work_root(sc['cfg'], prof), want, (name, key))
                n += 1
        self.assertGreaterEqual(n, 40)

    def test_a_liga_root_never_goes_through_find(self):
        """⛔ `legacy_tracks` перелічує лише id за `ID_RE`, а 0.14.0 шанував власний корінь будь-якого ключа (`'United'` теж):
        шлях через `find` його не бачив би."""
        cfg = {'design_work_roots': {'United': '~/work/up', 'x y': '~/work/sp'}, 'design_work_root': '~/work/shared'}
        self.assertIsNone(tracks.find(tracks.legacy_tracks(cfg)[0], 'United'))
        self.assertEqual(serve.track_root(self.sp, cfg, 'United'), os.path.expanduser('~/work/up'))
        self.assertEqual(serve.track_root(self.sp, cfg, 'x y'), os.path.expanduser('~/work/sp'))
        self.assertEqual(serve.track_root(self.sp, cfg, 'liga360'), os.path.expanduser('~/work/shared'))

    def test_roots_not_a_dict_is_the_shared_root_not_a_500(self):
        """Свідома відмінність (спека §6.4): 0.14.0 давав `AttributeError`; тепер спільний корінь."""
        sc = self.snap['roots']['roots_not_dict']
        shared = os.path.expanduser(sc['cfg']['design_work_root'])
        for key in sc['by_profile']:
            prof = None if key == 'None' else key
            self.assertEqual(serve.track_root(self.sp, sc['cfg'], prof), shared, key)
            self.assertEqual(serve.work_root(sc['cfg'], prof), shared, key)

    def test_repos_through_profile_repos_and_track_repo(self):
        path = os.environ['DC_TASKS_FILE']
        n = 0
        for name, sc in self.snap['repos'].items():
            want = sc['result']['result']
            if name == 'no_file':
                if os.path.exists(path):
                    os.remove(path)
            elif name == 'not_json':
                gen._write(path, '{not json')
            else:
                gen._write(path, sc['cfg'])
            self.assertEqual(serve.profile_repos(), want, name)
            for tid in ('united', 'liga360', 'seo', 'zzz', 'ok', 'ok-1', 'a' * 32):
                self.assertEqual(serve.track_repo(self.sp, tid), want.get(tid, ''), (name, tid))
            self.assertEqual(serve.track_repo(self.sp, None), '', name)
            self.assertEqual(serve.track_repo(self.sp, 5), '', name)
            n += 1
        self.assertEqual(n, 17)

    def test_task_new_matches_the_snapshot_and_adds_track(self):
        tmp = self._tmp()
        for i, prof in enumerate(gen.PROFILES):
            with self.subTest(profile=prof):
                home = os.path.join(tmp, 'tn%d' % i, 'home')
                os.makedirs(home)
                path = os.path.join(home, 'tasks.json')
                gen._write(path, gen._liga_cfg({'united': gen.REPOS['united']}))
                vcs, net = gen.Vcs(), gen.NoNet()
                with mock.patch.dict(os.environ, {'HOME': home, 'DC_TASKS_FILE': path}), \
                        mock.patch.object(serve, 'vcs_provider', vcs), mock.patch.object(serve.urllib.request, 'urlopen', net):
                    cfg = serve.load_tasks()
                    sp = spaces.active_space()
                    res = serve.task_new(cfg, 't1', track=prof, legacy=True, root=serve.track_root(sp, cfg, prof),
                                         repo=serve.track_repo(sp, prof))
                    saved = serve.load_tasks()
                want = self.snap['task_new'][str(prof)]
                view = gen._entry_view(saved['tasks']['t1'], home)
                entry, keys = dict(view['entry']), list(view['keys'])
                track = entry.pop('track', '<нема>')
                if 'track' in keys:
                    keys.remove('track')
                self.assertEqual(entry, want['entry'])                       # `dir`, `gitlab`, `title`, `jira`, `profile` — як було
                self.assertEqual(sorted(keys), want['keys'])
                self.assertEqual(track, '<нема>' if prof is None else prof)  # новий ключ: те саме значення; `None` — не пишеться
                self.assertEqual(entry['profile'], prof)                     # `profile` лишається (колеги на 0.14.0 читають його)
                self.assertEqual({**{k: v for k, v in res.items() if k != 'dir'}, 'dir': gen.rel(res['dir'], home)},
                                 want['result'])
                self.assertEqual((saved['current'], view['has_opened']), (want['current'], want['has_opened']))
                self.assertTrue(os.path.isfile(os.path.join(res['dir'], 'iterations', 'it1', 'index.html')))
                self.assertEqual((vcs.calls, net.calls), (want['vcs_provider_calls'], 0))

    def test_ds_matches_the_snapshot(self):
        n = 0
        for name, row in self.snap['ds'].items():
            prof, want = row['profile'], row['result']
            if 'raised' in want:                                              # не рядок: сам `inspector_ds_arg` не змінений
                with self.assertRaises(AttributeError):
                    serve.inspector_ds_arg(prof, None)
                continue
            self.assertEqual(serve.inspector_ds_arg(prof, None), want['result'], name)
            self.assertEqual(serve.inspector_ds_arg(serve.task_ds({'profile': prof}, self.sp), None), want['result'], name)
            self.assertEqual(serve.inspector_ds_arg(serve.task_ds({'track': prof}, self.sp), None), want['result'], name)
            n += 1
        self.assertEqual(n, 12)

    def test_pages_match_the_snapshot_through_a_real_server(self):
        """Хвіст `inspector.js…` у розмітці `/commented` для всіх готових задач — через справжній сервер у процесі (як знімав
        генератор). Лише `s-five` (профіль-число) відрізняється свідомо: 0.14.0 рвав зʼєднання, тепер чиста сторінка без `?ds=`."""
        out = gen.pages(self._tmp())
        want = self.snap['pages']
        self.assertEqual(sorted(out), sorted(want))
        for key in want:
            if key == 's-five':
                continue
            self.assertEqual(out[key], want[key], key)
        for ch in ('local', 'project'):
            self.assertEqual(want['s-five'][ch], {'error': 'RemoteDisconnected', 'status': None})
            self.assertEqual((out['s-five'][ch]['status'], out['s-five'][ch]['inspector_tails']), (200, ['']), ch)
        self.assertEqual(out['urlopen_calls'], 0)

    def test_route_matches_the_snapshot_modulo_the_track_key(self):
        out = gen.route(self._tmp())
        want = self.snap['route']
        n = 0
        for name, row in out['task_new'].items():
            entry = row.get('entry')
            if entry is None:
                continue
            self.assertEqual(entry.pop('track'), entry['profile'], name)      # `track` дзеркалить `profile`
            row['keys'].remove('track')
            n += 1
        self.assertEqual(n, 11)                                               # 12 сценаріїв без `bad-profile` (5)
        self.assertEqual(out, want)

    def test_bin_tools_keep_working_through_the_wrapper(self):
        self.assertEqual(gen.bin_tools(self._tmp()), self.snap['bin'])


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

    def test_a_liga_space_without_tracks_uses_the_adapter(self):
        liga = self.make_space('Liga', integrations=True)
        cfg = self.legacy_cfg()
        self.assertEqual(serve.space_tracks(liga), tracks.legacy_tracks(cfg)[:2])
        for raw in ('{не json', '[1]', '{"tracks": 5}', '{"name": "x"}'):      # ключа нема / не список / файл битий — адаптер
            with self.subTest(raw=raw):
                self.space_json(liga, raw=raw)
                self.assertEqual(serve.space_tracks(liga), tracks.legacy_tracks(cfg)[:2])

    def test_a_liga_space_with_tracks_in_its_space_json_does_not_get_the_adapter(self):
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg()
        self.space_json(liga, tracks=[{'id': 'web'}], default_track='web')
        tr, default = serve.space_tracks(liga)
        self.assertEqual(([t['id'] for t in tr], default), (['web'], 'web'))
        self.space_json(liga, tracks=[])                                       # явний порожній перелік теж вимикає адаптер
        self.assertEqual(serve.space_tracks(liga), ([], None))

    def test_layer_off_is_the_adapter(self):
        cfg = self.legacy_cfg()
        with mock.patch.dict(os.environ):
            os.environ.pop('DEAI_HOME')
            self.assertFalse(spaces.layer_on())
            self.assertEqual(serve.space_tracks(spaces.active_space()), tracks.legacy_tracks(cfg)[:2])

    def test_a_missing_or_broken_legacy_file_gives_the_bare_adapter(self):
        liga = self.make_space('Liga', integrations=True)
        want = tracks.legacy_tracks({})[:2]
        self.assertEqual(serve.space_tracks(liga), want)                       # файла нема
        gen._write(self.legacy_file, '{not json')
        self.assertEqual(serve.space_tracks(liga), want)

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
        cfg = serve.load_tasks()
        self.assertEqual(serve.track_root(self.sp, cfg, 'same'), self.sp['path'])
        self.assertEqual(serve.track_root(self.sp, cfg, 'inside'), self.sp['path'])

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
        cfg = serve.load_tasks()
        web = os.path.join(self.sp['path'], 'web-dir')
        self.assertEqual(serve.track_root(self.sp, cfg, 'web'), web)
        self.assertEqual(serve.track_root(self.sp, cfg, 'mobile'), self.sp['path'])      # напрямок без `root` — шлях простору
        self.assertEqual(serve.track_root(self.sp, cfg, 'zzz'), web)                     # невідомий — `root` дефолтного
        self.assertEqual(serve.track_root(self.sp, cfg, None), web)
        self.space_json(self.sp, tracks=[])
        for tid in ('web', None):
            self.assertEqual(serve.track_root(self.sp, cfg, tid), self.sp['path'])       # напрямків нема — шлях простору

    def test_track_root_of_a_liga_space(self):
        liga = self.make_space('Liga', integrations=True)
        cfg = self.legacy_cfg(design_work_roots={'united': '~/w/u', 'seo': '~/w/s'}, design_work_root='~/w/shared')
        for tid in ('united', 'seo', 'liga360', 'zzz', 'United', None):
            self.assertEqual(serve.track_root(liga, cfg, tid), tracks.legacy_root(cfg, tid), tid)
        self.space_json(liga, tracks=[])                                       # власні напрямки є, але порожні — спільний корінь
        self.assertEqual(serve.track_root(liga, cfg, 'web'), tracks.legacy_root(cfg, None))
        self.space_json(liga, tracks=[{'id': 'web', 'root': os.path.join(liga['path'], 'web')}])
        self.assertEqual(serve.track_root(liga, cfg, 'web'), os.path.join(liga['path'], 'web'))
        self.assertEqual(serve.track_root(liga, cfg, 'zzz'), os.path.join(liga['path'], 'web'))   # невідомий — дефолтний

    def test_track_repo(self):
        self.two_tracks()
        self.assertEqual(serve.track_repo(self.sp, 'web'), self.REPO)
        for tid in ('mobile', 'zzz', None, 5):
            self.assertEqual(serve.track_repo(self.sp, tid), '', tid)         # невідомий НЕ береться з дефолтного
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg()
        self.assertEqual((serve.track_repo(liga, 'united'), serve.track_repo(liga, 'seo'), serve.track_repo(liga, 'liga360')),
                         (self.OTHER, self.REPO, ''))

    def test_task_ds_and_the_inspector_tail(self):
        self.two_tracks()
        sid = self.sp['id']
        for task, ds, tail in (({'track': 'web'}, 'united', f'?ds=united&sp={sid}'),
                               ({'profile': 'web'}, 'united', f'?ds=united&sp={sid}'),     # синонім
                               ({'track': 'mobile'}, '', f'?sp={sid}'),                     # `ds: ''` — лише `?sp=`
                               ({'track': 'zzz'}, 'zzz', f'?ds=zzz&sp={sid}'),             # напрямку нема — значення як є, як 0.14.0
                               ({}, '', f'?sp={sid}'), ({'track': 5}, '', f'?sp={sid}')):
            with self.subTest(task=task):
                self.assertEqual(serve.task_ds(task, self.sp), ds)
                self.assertEqual(serve.inspector_ds_arg(serve.task_ds(task, self.sp), self.sp), tail)
        self.assertEqual(serve.task_ds(None, self.sp), '')
        # збережений `profile` без напрямку, що його називає, діє як у 0.14.0 (еталон `page-none-project.html`)
        self.assertEqual(serve.task_ds({'profile': 'united'}, self.sp), 'united')
        self.space_json(self.sp, tracks=[])
        self.assertEqual(serve.task_ds({'profile': 'tool'}, self.sp), 'tool')

    def test_the_inspector_argument_is_the_ds_not_the_track(self):
        self.space_json(self.sp, tracks=[{'id': 'web', 'ds': 'liga360'}, {'id': 'plain'}])
        self.assertEqual(serve.task_ds({'track': 'web'}, self.sp), 'liga360')   # ДС напрямку, а не його id
        self.assertEqual(serve.task_ds({'track': 'plain'}, self.sp), '')
        self.assertEqual(next(iter(inspect.signature(serve.inspector_ds_arg).parameters)), 'ds')

    # ---- мітки
    def test_task_tags_of_an_ordinary_space_come_from_the_track_label(self):
        self.two_tracks()
        for task, want in (({'track': 'web'}, ['Web']), ({'profile': 'web'}, ['Web']), ({'track': 'mobile'}, ['mobile']),
                           ({'track': 'zzz'}, ['zzz']), ({'track': 'a,b'}, []), ({'track': 'web', 'tags': ['X']}, ['X']),
                           ({'track': 'web', 'tags': []}, []), ({}, []), ({'track': 5}, [])):
            with self.subTest(task=task):
                self.assertEqual(serve.task_tags(task, self.sp), want)
        # без `sp` — простір запиту
        self.assertEqual(serve.task_tags({'track': 'web'}), ['Web'])
        # профіль ЛІГИ в звичайному просторі НЕ перекладається таблицею адаптера
        self.assertEqual(serve.task_tags({'profile': 'united'}, self.sp), ['united'])

    def test_task_tags_of_a_liga_space_use_the_adapter_labels(self):
        liga = self.make_space('Liga', integrations=True)
        self.legacy_cfg()
        for prof, want in (('united', ['United']), ('liga360', ['LIGA360']), ('seo', ['SEO']), ('zzz', ['zzz'])):
            self.assertEqual(serve.task_tags({'profile': prof}, liga), want, prof)
        self.space_json(liga, tracks=[{'id': 'united', 'label': 'Alpha team'}])            # власні напрямки — їхні підписи
        self.assertEqual(serve.task_tags({'profile': 'united'}, liga), ['Alpha team'])

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
        res = serve.task_new(cfg, tid, title='Alpha', track=track, root=serve.track_root(self.sp, cfg, track),
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
        serve.task_new(cfg, 'g1', title='Alpha', track='web', legacy=True, root=serve.track_root(liga, cfg, 'web'),
                       repo=serve.track_repo(liga, 'web'))
        entry = serve.load_tasks()['tasks']['g1']
        self.assertEqual((entry['profile'], entry['track']), ('web', 'web'))
        self.assertEqual(entry['gitlab'], {'repo': self.REPO, 'path': 'mockup/g1'})
        self.assertNotIn('vcs', entry)
        cfg = serve.load_tasks()
        serve.task_new(cfg, 'g2', title='Alpha', track='plain', legacy=True, root=serve.track_root(liga, cfg, 'plain'),
                       repo=serve.track_repo(liga, 'plain'))
        self.assertNotIn('gitlab', serve.load_tasks()['tasks']['g2'])
        cfg = serve.load_tasks()                                               # явний `gitlab` перемагає репо напрямку
        own = {'repo': self.OTHER, 'path': 'mockup/x'}
        serve.task_new(cfg, 'g3', title='Alpha', track='web', legacy=True, gitlab=own, root=serve.track_root(liga, cfg, 'web'),
                       repo=serve.track_repo(liga, 'web'))
        self.assertEqual(serve.load_tasks()['tasks']['g3']['gitlab'], own)


class ServerTrackView(_Plain):
    """Напрямки простору рахуються ОДИН раз на відповідь і щодо ПРАВИЛЬНОГО простору (ревʼю Task 3): `?all=1`, вартість
    циклу по задачах, ліниве питання простору, реєстр, що не читається, `task_ds` без простору."""

    def write_tasks(self, sp, tasks):
        with open(os.path.join(sp['path'], 'tasks.json'), 'w', encoding='utf-8') as f:
            json.dump({'tasks': tasks, 'current': next(iter(tasks))}, f)

    def two_spaces(self):
        """Alpha — звичайний, напрямок `web` з підписом `Web`; Liga — з `integrations`, без `tracks` (адаптер: `United`)."""
        self.two_tracks()
        liga = self.make_space('Liga', integrations=True)
        self.write_tasks(self.sp, {'a1': {'track': 'web', 'dir': os.path.join(self.tmp, 'a1')}})
        self.write_tasks(liga, {'l1': {'profile': 'united', 'dir': os.path.join(self.tmp, 'l1')}})
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
        cfg = {'tasks': {'l1': {'profile': 'united'}}}
        self.assertEqual(serve._task_rows(cfg, liga)[0]['tags'], ['United'])
        self.assertEqual(serve._task_rows(cfg)[0]['tags'], ['united'])      # без `sp` — простір запиту (звичайний)

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
                mock.patch.object(serve, '_own_tracks', wraps=serve._own_tracks) as own, \
                mock.patch.object(serve, '_legacy_cfg', wraps=serve._legacy_cfg) as leg:
            tags = call(cfg, space)
        return (chk.call_count, own.call_count, leg.call_count), tags

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
                self.assertEqual((few[0] > 0, few[1]), (True, 1))            # напрямки порахували, `space.json` прочитали раз
                self.assertEqual((tags_few, tags_many), ([['Web']] * 3, [['Web']] * 30))
        few, _ = self.cost(3, liga, by_rows, profile='united')               # адаптер: навіть напрямків не будуємо
        many, tags = self.cost(30, liga, by_rows, profile='united')
        self.assertEqual((few, many), ((0, 1, 0), (0, 1, 0)))
        self.assertEqual(tags, [['United']] * 30)

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
                self.assertEqual(serve.track_root(self.sp, {}, 'web'), self.sp['path'])
        os.remove(reg)                                                       # реєстру нема зовсім — це не відмова
        self.assertEqual(serve.space_tracks(self.sp)[0][0]['root'], keep)
        with open(reg, 'wb') as f:
            f.write(good)

    # ---- m3: простору нема — значення як було
    def test_task_ds_without_a_space_is_the_raw_value(self):
        spaces.set_request_space('')                                        # запит «без простору»
        self.assertIsNone(spaces.active_space())
        self.assertEqual(serve.task_ds({'profile': 'tool'}, None), 'tool')
        self.assertEqual(serve.task_ds({'track': 'tool'}), 'tool')
        self.assertEqual(serve.task_ds({}, None), '')
        self.assertEqual(serve.task_ds({'track': 5}, None), '')


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

    def test_the_two_wrappers_are_thin_and_marked(self):
        for fn in (serve.work_root, serve.profile_repos):
            self.assertIn('до 4d-4', fn.__doc__)
        cfg = {'design_work_roots': {'x': '~/w/x'}, 'design_work_root': '~/w/s', 'profile_repos': {'x': 'git@example.com:s/w.git'}}
        self.assertEqual(serve.work_root(cfg, 'x'), tracks.legacy_root(cfg, 'x'))
        self.assertEqual(serve.work_root(cfg, 'y'), tracks.legacy_root(cfg, 'y'))

    def test_the_tag_rules_are_the_ones_of_tracks(self):
        self.assertNotIn('re.compile(', self.src[self.src.index('TAGS_MAX = 10'):self.src.index('class TagsError')])
        self.assertEqual(serve.normalize_tags([' a   b ']), [tracks.clean_tag('a   b')])
        for bad in ('a,b', 'a‮b', 'x' * (tracks.TAG_MAX_LEN + 1)):
            with self.assertRaises(serve.TagsError):
                serve.normalize_tags([bad])


if __name__ == '__main__':
    unittest.main()
