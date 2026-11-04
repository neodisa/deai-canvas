"""Напрямки простору (етап 4d-1, спека 2026-11-04-space-tracks-design.md).

Тут: знімок поведінки 0.14.0 (`Before4d1Shape`, Task 1). Наступні задачі додають класи (ядро `app/tracks.py`, диференційні
тести проти знімка, API), що читають той самий JSON.
"""
import json
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'tracks', 'before-4d1.json')

PROFILES = ('None', 'liga360', 'seo', 'united', 'zzz')       # відсортовано (ключ для `None` — рядок)


class Before4d1Shape(unittest.TestCase):
    """Знімок поведінки профілю задачі 0.14.0 на місці й має ключі, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['ds', 'meta', 'repos', 'roots', 'route', 'tags', 'task_new'])
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
            self.assertEqual(sorted(r[name]['by_profile']), list(PROFILES), name)
        self.assertEqual(r['fallback_constant'], '~/deai-work')
        # ключові паритети: свій корінь профілю → спільний → фолбек; невідомий і `None` — спільний (НЕ корінь `united`)
        both = {p: v['result'] for p, v in r['both']['by_profile'].items()}
        self.assertEqual(both, {'united': '~/work/united', 'seo': '~/work/seo', 'liga360': '~/work/shared',
                                'zzz': '~/work/shared', 'None': '~/work/shared'})
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
        self.assertEqual(len(r), 11)
        res = {k: v['result']['result'] for k, v in r.items()}
        self.assertEqual((res["'united'"], res["'seo'"], res["'zzz'"]), ('?ds=united', '?ds=seo', '?ds=zzz'))
        for bad in ("'Bad!'", "''", 'None', "'a_b'", 'x*33'):
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


if __name__ == '__main__':
    unittest.main()
