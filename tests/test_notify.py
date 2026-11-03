"""Роль `notify` (етап 4c-3, спека 2026-11-03-notify-role-design.md).

Наразі тут лише знімок поведінки 0.13.0 (`Before4c3Shape`, Task 1): наступні задачі додають класи ядра `app/notify.py`,
маршруту й диференційних перевірок паритету ЛІГИ, що читають той самий JSON.
"""
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'notify', 'before-4c3.json')


class Before4c3Shape(unittest.TestCase):
    """Знімок поведінки 0.13.0 на місці й має ключі, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['menu', 'meta', 'route', 'rpc_requests'])
        self.assertEqual(self.snap['meta']['version'], '0.13.0')
        self.assertEqual(self.snap['meta']['source_commit'], '0267024')
        self.assertEqual(self.snap['meta']['generator'], 'tests/make_before_4c3.py')

    def test_rpc_requests_shape(self):
        rr = self.snap['rpc_requests']
        self.assertEqual(sorted(rr), ['integrations_off', 'isolated_no_overview', 'isolated_tasks_file', 'network_error',
                                      'no_supabase', 'set', 'state', 'unset'])
        for key, fn in (('state', 'teams_mute_state'), ('set', 'teams_mute_set'), ('unset', 'teams_mute_set')):
            calls = rr[key]['calls']
            self.assertEqual(len(calls), 1, key)
            c = calls[0]
            self.assertEqual((c['method'], c['path'], c['timeout'], c['ssl_context']),
                             ('POST', '/rest/v1/rpc/' + fn, 8, True), key)
            self.assertTrue(c['host_is_demo'], key)
            # ⛔ значення ключа в знімку нема — лише мітка
            self.assertEqual(c['headers']['apikey'], '<key>')
            self.assertEqual(c['headers']['authorization'], 'Bearer <key>')
        self.assertEqual(rr['state']['calls'][0]['body'], {})
        self.assertEqual(rr['set']['calls'][0]['body'],
                         {'p_project': 'dc/t1', 'p_muted': True, 'p_by': 'k:0123456789ab'})
        self.assertIs(rr['unset']['calls'][0]['body']['p_muted'], False)
        self.assertEqual(rr['state']['result'][0]['project_id'], 'dc/t1')
        self.assertIs(rr['set']['result'], True)
        # відмови: усі — `OSError`, ізоляція й «без інтеграцій» не доходять до мережі
        for key in ('integrations_off', 'isolated_no_overview', 'isolated_tasks_file', 'no_supabase'):
            self.assertTrue(rr[key]['is_oserror'], key)
            self.assertEqual(rr[key]['urlopen_calls'], 0, key)
        self.assertEqual(rr['integrations_off']['raised'], 'IntegrationsOff')
        self.assertIn('ізольований конфіг', rr['isolated_tasks_file']['message'])
        self.assertEqual(rr['isolated_tasks_file']['message'], rr['isolated_no_overview']['message'])
        self.assertEqual(rr['network_error']['urlopen_calls'], 1, 'запит був, мережа впала')

    def test_route_shape(self):
        rt = self.snap['route']
        self.assertEqual(sorted(rt), ['fake_get', 'fake_post', 'integrations_off', 'isolated', 'real_path',
                                      'signature_real'])
        self.assertRegex(rt['signature_real'], r'^k:[0-9a-f]{12}$')
        g = rt['fake_get']
        self.assertEqual(sorted(g), ['muted_by_colleague', 'muted_by_me', 'not_muted', 'other_channel_muted',
                                     'parent_muted_subchannel'])
        self.assertEqual(g['not_muted']['body'], {'channel': 'dc/t1', 'muted': False})
        self.assertEqual(g['other_channel_muted']['body'], {'channel': 'dc/t1', 'muted': False},
                         'чужий канал тишу не покриває')
        self.assertTrue(g['muted_by_me']['body']['muted'])
        self.assertTrue(g['muted_by_me']['body']['mine'])
        self.assertFalse(g['muted_by_colleague']['body']['mine'])
        sub = g['parent_muted_subchannel']['body']
        self.assertEqual((sub['channel'], sub['via'], sub['muted']), ('dc/t1/internal', 'dc/t1', True),
                         'тиша батьківського каналу покриває підканал')
        # POST: записи в базу лише від прийнятих запитів
        p = rt['fake_post']
        self.assertEqual(p['mute']['status'], 200)
        self.assertEqual(p['mute']['body']['muted_by'], 'k:0123456789ab')
        self.assertEqual(sorted(p['mute']['db_after']), ['dc/t1'])
        self.assertEqual(p['unmute']['db_after'], {})
        self.assertEqual((p['bad_muted']['status'], p['bad_muted']['db_after']), (400, {}))
        self.assertEqual((p['foreign_origin']['status'], p['foreign_origin']['db_after']), (403, {}))
        # простір без інтеграцій: 409 `integrations-off`, мережі й бази не торкається
        off = rt['integrations_off']
        for key in ('get', 'post_mute', 'post_bad_muted'):
            self.assertEqual(off[key]['status'], 409, key)
            self.assertEqual(off[key]['body']['code'], 'integrations-off', key)
        self.assertEqual(off['post_foreign_origin']['status'], 403, 'Origin дивиться раніше за простір')
        self.assertEqual(off['urlopen_calls'], 0)
        self.assertEqual(sorted(off['db_after']), ['dc/p1'], 'база простору без інтеграцій не змінилась')
        # ізоляція: GET «не знаю» (200 + error), POST 502; мережі нема
        for key in ('tasks_file', 'no_overview'):
            iso = rt['isolated'][key]
            self.assertEqual((iso['get']['status'], iso['post']['status']), (200, 502), key)
            self.assertIn('error', iso['get']['body'])
            self.assertNotIn('muted', iso['get']['body'])
            self.assertEqual(iso['urlopen_calls'], 0, key)
        # справжній шлях RPC (без шва): стан запитується, збій мережі дає `error`, а не «увімкнено»
        real = rt['real_path']
        self.assertEqual([c['path'] for c in real['get']['rpc_calls']], ['/rest/v1/rpc/teams_mute_state'])
        self.assertTrue(real['get']['body']['muted'])
        self.assertEqual(real['get_network_error']['body'], {'channel': 'dc/t1', 'error': 'мережі нема'})
        self.assertEqual(real['post_network_error']['status'], 502)

    def test_menu_shape(self):
        res = self.snap['menu']['result']
        self.assertEqual(sorted(res), sorted(self.snap['menu']['input']))
        base = ['togglepub', 'openpreview', 'copylink']
        self.assertEqual(res['liga_on']['items'], base + ['teamsnotify', 'pubpw'])
        # без інтеграцій пункта Teams нема, навіть якщо дані про тишу є; без постачальника публікації нема й кнопки
        self.assertEqual(res['plain_no_teams_data']['items'], base)
        self.assertEqual(res['plain_with_teams_data']['items'], base)
        self.assertIsNone(res['plain_with_teams_data']['teamsnotify'])
        self.assertIsNone(res['plain_no_publish']['items'])
        self.assertEqual(res['module_with_integrations']['items'], base + ['teamsnotify'], 'пароля ЛІГИ у модуля нема')
        # стани перемикача ЛІГИ: завантаження й збій — вимкнений пункт із причиною, а не «увімкнено»
        self.assertTrue(res['liga_loading']['teamsnotify']['disabled'])
        self.assertEqual(res['liga_loading']['teamsnotify']['whyKey'], 'whyTeamsLoading')
        self.assertEqual(res['liga_error']['teamsnotify']['whyKey'], 'whyTeamsUnknown')
        self.assertTrue(res['liga_on']['teamsnotify']['on'])
        self.assertFalse(res['liga_muted_by_me']['teamsnotify']['on'])
        self.assertEqual(res['liga_muted_by_me']['teamsnotify']['subKey'], 'teamsMutedByMe')
        self.assertEqual(res['liga_muted_by_colleague']['teamsnotify']['subKey'], 'teamsMutedSub')
        # стара форма відповіді: рішення за `integrations` (рівно `=== false`)
        self.assertIsNone(res['old_shape_false']['items'])
        self.assertIn('teamsnotify', res['old_shape_true']['items'])
        self.assertIn('teamsnotify', res['no_space']['items'])

    def test_no_secrets_or_local_paths(self):
        """Репо знеособлене: у знімку лише вигадані значення — без ключів, хостів і шляхів машини."""
        with open(BEFORE, encoding='utf-8') as f:
            raw = f.read()
        for needle in ('pk-test-1', '/Users/', '/private/', 'before-4c3-', 'alpha@example.com'):
            self.assertNotIn(needle, raw, needle)


if __name__ == '__main__':
    unittest.main()
