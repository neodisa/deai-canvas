"""Неявний постачальник, шов шару, закон ізоляції (етап 4d-2, 0.16.0).

Тут: знімок поведінки 0.15.0 (`Before4d2Shape`, Task 1); ядро `app/implicit.py`, шов `request_space()`, закон ізоляції й
охоронець літерала додаються наступними задачами. Спека `docs/superpowers/specs/2026-11-05-implicit-provider-seam-design.md`.
"""
import json
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'implicit', 'before-4d2.json')

ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs')       # `deai_modules.ROLES_CALLED`, відсортовано
LEGACY_ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tracker', 'vcs')          # `deai_modules.LEGACY_ROLES`
ENVS = ('a_seam', 'b_dc_tasks_file', 'c_dc_no_overview')


class Before4d2Shape(unittest.TestCase):
    """Знімок 0.15.0 на місці й має ключі, типи та кількості сценаріїв, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['api', 'build', 'caps', 'install', 'isolation', 'meta', 'provider'])
        self.assertEqual(self.snap['meta']['version'], '0.15.0')
        self.assertEqual(self.snap['meta']['source_commit'], '6e68250')
        self.assertEqual(self.snap['meta']['generator'], 'tests/make_before_4d2.py')

    def test_machine_independent(self):
        """⛔ Знімок не несе ні справжніх шляхів, ні імен, ні тимчасових тек: лише `~/…`/`<tmp>`; значення — вигадані."""
        # ⛔ Імʼя користувача машини — з оточення, не літералом: справжнє імʼя в коді репо — та сама утічка, від якої тест береже.
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/Users/', '/home/', '/var/folders', '/private/', '/tmp/', 'before-4d2-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))          # жодного часового штампа
        self.assertEqual(self.snap['meta']['volatile_stripped'], [])

    def test_caps_shape(self):
        c = self.snap['caps']
        self.assertEqual(sorted(c), ['fingerprint_failure_liga', 'fingerprint_failure_plain', 'liga',
                                     'liga_unreadable_space_json', 'plain_no_modules', 'plain_own_module_untrusted',
                                     'plain_static_publish', 'plain_unreadable_space_json'])
        for name, row in c.items():
            self.assertEqual(sorted(row), ['caps', 'space'], name)
            self.assertTrue(set(ROLES) <= set(row['caps']), name)
            self.assertLessEqual(set(row['caps']) - set(ROLES), {'error'}, name)
            for role in ROLES:
                self.assertIsInstance(row['caps'][role], (str, type(None)), (name, role))
        # ключові паритети: ЛІГА — `'legacy'` у шести ролях, у `tokens` — ніхто; звичайний — неявний `static-publish`
        liga = c['liga']['caps']
        self.assertEqual({r: liga[r] for r in LEGACY_ROLES}, {r: 'legacy' for r in LEGACY_ROLES})
        self.assertIsNone(liga['tokens'])
        self.assertNotIn('error', liga)
        self.assertEqual(c['plain_no_modules']['caps']['publish'], 'static-publish')
        self.assertEqual({v for k, v in c['plain_no_modules']['caps'].items() if k != 'publish'}, {None})
        self.assertEqual(c['plain_static_publish']['caps']['publish'], 'static-publish')
        # нечитабельний `space.json`: ЛІГА лишає `'legacy'` лише в `publish`/`vcs`; решта — `None` + код помилки
        bad = c['liga_unreadable_space_json']['caps']
        self.assertEqual((bad['publish'], bad['vcs'], bad['error']), ('legacy', 'legacy', 'space-json-unreadable'))
        self.assertEqual({bad[r] for r in ('comments', 'dashboard', 'notify', 'tracker')}, {None})
        self.assertEqual(c['plain_unreadable_space_json']['caps']['error'], 'space-json-unreadable')
        self.assertIsNone(c['plain_unreadable_space_json']['caps']['publish'])
        # свій недовірений модуль «на папері»: `publish` — `None`, без `error` (стан ролі, а не простору)
        own = c['plain_own_module_untrusted']['caps']
        self.assertIsNone(own['publish'])
        self.assertNotIn('error', own)
        # збій відбитків: тотальна запасна форма з `error: module-error`; `'legacy'` лише в `publish`/`vcs` ЛІГИ
        fp = c['fingerprint_failure_liga']['caps']
        self.assertEqual((fp['publish'], fp['vcs'], fp['error']), ('legacy', 'legacy', 'module-error'))
        self.assertEqual({fp[r] for r in ('comments', 'dashboard', 'notify', 'tracker', 'tokens')}, {None})
        fpp = c['fingerprint_failure_plain']['caps']
        self.assertEqual({fpp[r] for r in ROLES}, {None})
        self.assertEqual(fpp['error'], 'module-error')

    def test_provider_shape(self):
        p = self.snap['provider']
        self.assertEqual(sorted(p), ['layer_off', 'layer_on_request_not_fixed'])
        self.assertFalse(p['layer_off']['layer_on'])
        self.assertTrue(p['layer_on_request_not_fixed']['layer_on'])
        for mode, row in p.items():
            self.assertEqual(sorted(row['roles']), sorted(ROLES + ('git-sync', 'zzz')), mode)
            for role, r in row['roles'].items():
                self.assertEqual(sorted(r), ['catalog_reads', 'registry_reads', 'space_json_reads', 'value'], (mode, role))
                self.assertEqual(r['value'], 'legacy' if role in LEGACY_ROLES else None, (mode, role))
                # ⛔ без простору запиту рішення не читає ні реєстр, ні `space.json`, ні каталог
                self.assertEqual((r['registry_reads'], r['space_json_reads'], r['catalog_reads']), (0, 0, 0), (mode, role))

    def test_api_shape(self):
        a = self.snap['api']
        self.assertEqual(sorted(a), ['layer_off', 'liga_in_registry'])
        for mode, row in a.items():
            self.assertEqual(sorted(row), ['layer_on', 'space_route', 'spaces', 'task', 'urlopen_calls', 'vcs_provider_calls'], mode)
            self.assertEqual((row['urlopen_calls'], row['vcs_provider_calls']), (0, 0), mode)
            self.assertEqual((row['space_route']['status'], row['space_route']['body_is_json']), (404, False), mode)
            self.assertEqual(row['task']['status'], 200, mode)
            self.assertEqual(sorted(row['task']['preview_gate']), ['inner_stale', 'pages', 'stale', 'state', 'ungated'], mode)
            self.assertFalse(row['task']['has_publish_gate'], mode)
        liga = a['liga_in_registry']
        self.assertTrue(liga['layer_on'])
        self.assertEqual(len(liga['spaces']['rows']), 1)
        row = liga['spaces']['rows'][0]
        self.assertEqual((row['integrations'], row['legacy']), (True, True))
        self.assertEqual({row['capabilities'][r] for r in LEGACY_ROLES}, {'legacy'})      # публічний контракт: `'legacy'` назовні
        self.assertEqual(liga['task']['space']['capabilities'], row['capabilities'])
        off = a['layer_off']
        self.assertFalse(off['layer_on'])
        self.assertEqual((off['spaces']['off'], off['spaces']['rows']), (True, []))
        self.assertIsNone(off['task']['space'])

    def test_isolation_shape(self):
        i = self.snap['isolation']
        self.assertEqual(sorted(i), ['dashboard', 'note', 'notify', 'sync', 'tracker'])
        # (а) шов дає результат; (б) і (в) — модуль НЕ кличеться, мережі нема
        for role in ('dashboard', 'tracker', 'notify'):
            self.assertEqual(sorted(i[role]), list(ENVS), role)
        for env in ENVS:
            for fn in ('team_fetch', 'team_rows'):
                r = i['dashboard'][env][fn]
                self.assertEqual((r['module_calls'], r['urlopen_calls']), (0, 0), (env, fn))
            for fn in ('mute_state', 'mute_set'):
                r = i['notify'][env][fn]
                self.assertEqual((r['module_calls'], r['urlopen_calls']), (0, 0), (env, fn))
            t = i['tracker'][env]
            self.assertEqual((t['module_calls'], t['tracker_statuses_calls'], t['urlopen_calls']), (0, 0, 0), env)
        # дашборд: (а) — рядки шва без помилки; (б)/(в) — порожньо + текст ізоляції
        self.assertEqual(i['dashboard']['a_seam']['team_fetch']['outcome']['result'][1], None)
        self.assertEqual(len(i['dashboard']['a_seam']['team_fetch']['outcome']['result'][0]), 1)
        for env in ENVS[1:]:
            rows, err = i['dashboard'][env]['team_fetch']['outcome']['result']
            self.assertEqual(rows, [])
            self.assertIn('DC_TASKS_FILE', err)
        # трекер: (а) — статуси шва; (б)/(в) — `None` («трекера нема»), помилки нема
        self.assertEqual(i['tracker']['a_seam']['outcome']['result'][0], {'DEMO-1': {'cat': 'indeterminate', 'name': 'In progress'}})
        for env in ENVS[1:]:
            self.assertIsNone(i['tracker'][env]['outcome']['result'])
        # нотифай: (а) — шов пише у свій файл; (б)/(в) — `OSError` з фіксованим текстом
        self.assertEqual(i['notify']['a_seam']['mute_set']['outcome'], {'result': True})
        self.assertEqual(i['notify']['a_seam']['seam_file_after_set'], ['demo-channel'])
        for env in ENVS[1:]:
            for fn in ('mute_state', 'mute_set'):
                self.assertEqual(i['notify'][env][fn]['outcome']['raised'], 'OSError', (env, fn))
        # синк: стартує лише без ізоляції й з конфігом установки
        s = i['sync']
        self.assertEqual(sorted(s), ['a_seam', 'a_seam_no_install_config', 'b_dc_tasks_file', 'c_dc_no_overview'])
        self.assertEqual(s['a_seam']['launched'], [['legacy-key', True, ['--legacy']]])
        for name in ('a_seam_no_install_config', 'b_dc_tasks_file', 'c_dc_no_overview'):
            self.assertEqual(s[name]['launched'], [], name)
        for name, row in s.items():
            self.assertEqual(row['outcome'], {'result': None}, name)
            self.assertEqual(row.get('popen_calls', 0), 0, name)

    def test_install_shape(self):
        n = self.snap['install']
        names = sorted('%s/%s/%s' % (r, e, f) for r in ('root_with_pair', 'root_without_pair') for e in ('env_set', 'env_unset')
                       for f in ('files_present', 'files_absent'))
        self.assertEqual(sorted(n), names)
        for name, row in n.items():
            self.assertEqual(sorted(row), ['jira_config', 'supabase_config'], name)
            self.assertEqual((len(row['supabase_config']), len(row['jira_config'])), (2, 3), name)
        # вигадані значення і лише вони
        for name, row in n.items():
            for v in row['supabase_config'] + row['jira_config']:
                self.assertTrue(v is None or v.endswith('.example.com') or '@' in v or v.startswith(('sb_', 'jira_')), (name, v))
        # зафіксована ПОТОЧНА (0.15.0) поведінка: ізольований прогін бачить облікові машини — Task 5 це закриє
        self.assertEqual(n['root_without_pair/env_set/files_absent']['supabase_config'], ['https://sb-env.example.com', 'sb_env_key'])
        self.assertEqual(n['root_with_pair/env_unset/files_present']['jira_config'],
                         ['https://jira.example.com', 'file@example.com', 'jira_file_token'])
        self.assertEqual(n['root_without_pair/env_unset/files_present']['jira_config'], [None, None, None])
        self.assertEqual(n['root_without_pair/env_unset/files_absent']['supabase_config'], [None, None])

    def test_build_shape(self):
        b = self.snap['build']
        self.assertEqual(b['BUILD_KINDS'], ['legacy', 'module'])
        self.assertEqual((b['legacy_with_league_comments']['manifest_build'], b['legacy_no_comments']['manifest_build'],
                          b['module_no_comments']['manifest_build']), ('legacy', 'legacy', 'module'))
        for name in ('legacy_with_league_comments', 'legacy_no_comments', 'module_no_comments'):
            self.assertTrue(b[name]['build_is_last_key'], name)
            self.assertEqual(b[name]['manifest_keys'], ['build', 'frames', 'iters', 'outline', 'pages', 'task', 'widths'], name)
        self.assertTrue(b['legacy_with_league_comments']['has_comment_layer_dir'])
        self.assertFalse(b['legacy_no_comments']['has_comment_layer_dir'])
        self.assertEqual(b['league_comments'], {'is_dict': True, 'keys': ['channel', 'config', 'module'],
                                                'module': 'supabase-comments', 'warn': None})
        self.assertFalse(b['publish_manifest_without_mark']['has_build_key'])
        bad = {k: v for k, v in b.items() if k.startswith('bad_build_')}
        self.assertEqual(len(bad), 4)
        self.assertEqual({v['raised'] for v in bad.values()}, {'ValueError'})
        self.assertEqual(b['urlopen_calls'], 0)


if __name__ == '__main__':
    unittest.main()
