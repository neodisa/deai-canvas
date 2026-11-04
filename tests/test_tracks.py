"""Напрямки простору (етап 4d-1, спека 2026-11-04-space-tracks-design.md).

Тут: знімок поведінки 0.14.0 (`Before4d1Shape`, Task 1) і ядро `app/tracks.py` (Task 2: `Normalize`, `TaskTrack`,
`LegacyTracks`, `LegacyParity` — паритет ЛІГИ зі знімком через `tracks`). Наступні задачі додають класи (сервер, API), що
читають той самий JSON.
"""
import copy
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app')
sys.path.insert(0, _APP)
import tracks  # noqa: E402  (чисте ядро; `serve` воно не імпортує)

_HERE = os.path.dirname(os.path.abspath(__file__))
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


class LegacyParity(_Home):
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

    @staticmethod
    def _derived(task):
        """Мітки задачі, як `serve.task_tags` 0.14.0, але правила мітки й похідна — з `tracks` (цикл `tags` лишається в `serve`
        до Task 3: тут він відтворений лише для того, щоб прогнати КОЖЕН сценарій знімка через `tracks.read_tag`)."""
        if isinstance(task, dict) and 'tags' in task:
            raw = task['tags']
            out, seen = [], set()
            for x in raw if isinstance(raw, list) else []:
                tag = tracks.read_tag(x)
                if tag and tag.casefold() not in seen:
                    seen.add(tag.casefold())
                    out.append(tag)
                    if len(out) >= 10:
                        break
            return out
        tag = tracks.label_tag([], task, legacy=True)
        return [tag] if tag else []

    def test_tags_every_scenario(self):
        self.assertEqual(len(self.snap['tags']), 24)
        for name, sc in self.snap['tags'].items():
            self.assertEqual(self._derived(sc['task']), sc['result']['result'], name)

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


if __name__ == '__main__':
    unittest.main()
