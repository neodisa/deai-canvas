"""Роль `notify` (етап 4c-3, спека 2026-11-03-notify-role-design.md).

Тут: знімок поведінки 0.13.0 (`Before4c3Shape`, Task 1), роль у каркасі модулів (`NotifyRole`, Task 2) і чисте ядро
`app/notify.py` (`NotifyCore`, Task 2, з паритетом проти `serve.teams_mute_view` і знімка). Наступні задачі додають
класи модуля, маршруту й адаптера ЛІГИ, що читають той самий JSON.
"""
import json
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402
import notify  # noqa: E402
import serve  # noqa: E402  (лише для паритету `teams_mute_view`; ядро `notify` сам `serve` НЕ імпортує)
import spaces_guard  # noqa: E402
import test_modules as tm  # noqa: E402  (каркас `Env`: тимчасові HOME/DEAI_HOME, тека модулів-фікстур)

BEFORE = os.path.join(_HERE, 'fixtures', 'notify', 'before-4c3.json')
_REAL = None


def setUpModule():
    """Клас `NotifyRole` створює простори: справжній `~/.deai` стереже знімок на вході й звірка на виході
    (інваріант `test_serve.TestsCannotWriteLiveConfig`)."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


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
            self.assertEqual(c['query'], '', key)
            self.assertEqual(c['headers']['content-type'], 'application/json', key)
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
        self.assertEqual(sorted(g), ['empty_signature_empty_muted_by', 'legacy_empty_muted_by',
                                     'legacy_empty_muted_by_with_time', 'legacy_no_muted_by', 'muted_by_colleague',
                                     'muted_by_me', 'not_muted', 'other_channel_muted', 'parent_muted_subchannel',
                                     'prefix_collision_t10', 'prefix_collision_t1x'])
        for key in ('prefix_collision_t10', 'prefix_collision_t1x'):      # `dc/t10`, `dc/t1x` — не батьки `dc/t1`
            self.assertEqual(g[key]['body'], {'channel': 'dc/t1', 'muted': False}, key)
        for key in ('legacy_no_muted_by', 'legacy_empty_muted_by', 'legacy_empty_muted_by_with_time',
                    'empty_signature_empty_muted_by'):                    # порожній підпис ніколи не «мій»
            self.assertTrue(g[key]['body']['muted'], key)
            self.assertIs(g[key]['body']['mine'], False, key)
            self.assertEqual(g[key]['body']['muted_by'] if 'muted_by' in g[key]['body'] else '', '', key)
        self.assertEqual(g['empty_signature_empty_muted_by']['signature'], '')
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


# ------------------------------------------------------------------------------------------ Task 2: роль і ядро

#: Модуль ролі `notify`: `check` і обовʼязкові `mute_state`, `mute_set`.
NOTIFY_SERVER = (tm.CHECK_ONLY + 'def mute_state(ctx):\n    return []\n'
                 + 'def mute_set(ctx, channel, muted, by):\n    return bool(muted)\n')


class NotifyRole(tm.Env):
    """Роль `notify` у каркасі модулів (4c-3, Task 2): маніфест, постачальник, `capabilities`, коди помилок."""

    def setUp(self):
        super().setUp()
        # `Env.setUp` уже ізолює `DEAI_HOME`; присвоєння повторено тут явно, бо статичний охоронець
        # (`test_serve.TestsCannotWriteLiveConfig`) шукає його в тексті САМОГО файла, що пише простори.
        os.environ['DEAI_HOME'] = self.deai

    def error_of(self, mid):
        m = dm.catalog()[mid]
        self.assertEqual((m.status, m.error_code), ('error', 'bad-manifest'), f'{mid}: {m.error!r}')
        return m.error

    def test_the_role_is_called_and_nothing_is_reserved_any_more(self):
        self.assertEqual(dm.ROLES_CALLED[-1], 'notify')
        self.assertEqual(dm.ROLES_CALLED, ('publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker', 'notify'))
        self.assertEqual(dm.ROLES_RESERVED, ())
        self.assertEqual(dm.ROLE_FUNCTIONS['notify'], ('mute_state', 'mute_set'))
        self.assertIn('notify', dm.LEGACY_ROLES)
        self.assertIn('notify', dm.STRICT_LEGACY_ROLES)
        self.assertIn('supabase-teams', dm.KNOWN_OTHER_MODULES)

    def test_the_league_path_of_notify_is_not_a_fallback_after_an_error(self):
        """⛔ Зашитий шлях `notify` — спільний Supabase ЛІГИ й живий канал Teams команди: «через помилку» на нього не
        переходимо, тож `notify` НЕ в `LEGACY_ON_ERROR_ROLES`."""
        self.assertNotIn('notify', dm.LEGACY_ON_ERROR_ROLES)

    def test_a_notify_module_needs_both_functions(self):
        self.mk('ntf-bare', roles=('notify',), server=tm.CHECK_ONLY)
        self.assertIn('mute_state', self.error_of('ntf-bare'))
        for gap in ('mute_state', 'mute_set'):
            src = NOTIFY_SERVER.replace(f'def {gap}(', f'def _not_{gap}(')
            self.mk(f'ntf-no-{gap.replace("_", "-")}', roles=('notify',), server=src)
            self.assertIn(gap, self.error_of(f'ntf-no-{gap.replace("_", "-")}'), gap)
        self.mk('ntf-ok', roles=('notify',), server=NOTIFY_SERVER)
        m = dm.catalog()['ntf-ok']
        self.assertEqual((m.status, m.roles), ('ok', ['notify']))

    def test_an_unknown_role_is_still_a_bad_manifest(self):
        """Зарезервованих ролей нема (`ROLES_RESERVED == ()`), а невідома роль у маніфесті поводиться, як і раніше: модуль
        зламаний (`bad-manifest`), у тексті — імʼя ролі; у `space.json` запис із невідомою роллю губить ключ `roles`."""
        self.mk('ntf-alien', roles=('alpha',), server=tm.CHECK_ONLY)
        self.assertIn("unknown role 'alpha'", self.error_of('ntf-alien'))
        self.mk('ntf-mixed', roles=('notify', 'alpha'), server=NOTIFY_SERVER)
        self.assertIn("unknown role 'alpha'", self.error_of('ntf-mixed'))
        got = dm._normalize({'good': {'enabled': True, 'roles': ['notify']}, 'bad': {'enabled': True, 'roles': ['alpha']}})
        self.assertEqual(got['good']['roles'], ['notify'])
        self.assertNotIn('roles', got['bad'])

    def test_the_provider_of_an_integrations_space_without_a_module_is_legacy(self):
        ig = self.new_space('Integ', integrations=True)
        plain = self.new_space('Plain')
        self.assertEqual(dm.provider('notify', ig), 'legacy')
        self.assertEqual(dm.capabilities(ig)['notify'], 'legacy')
        self.assertIsNone(dm.provider('notify', plain))             # без інтеграцій і без модуля — нікого
        self.assertIsNone(dm.capabilities(plain)['notify'])

    def test_an_enabled_module_is_the_provider_in_both_kinds_of_space(self):
        self.mk('ntf-ok', roles=('notify',), server=NOTIFY_SERVER)
        ig = self.new_space('Integ', integrations=True)
        plain = self.new_space('Plain')
        for sp in (ig, plain):
            dm.write_module_state(sp, 'ntf-ok', enabled=True)
            self.assertEqual(dm.provider('notify', sp).id, 'ntf-ok')
            self.assertEqual(dm.capabilities(sp)['notify'], 'ntf-ok')
        dm.write_module_state(ig, 'ntf-ok', enabled=False)
        self.assertEqual(dm.capabilities(ig)['notify'], 'legacy')   # вимкнули: ЛІГА повертається до зашитого шляху
        dm.write_module_state(plain, 'ntf-ok', enabled=False)
        self.assertIsNone(dm.capabilities(plain)['notify'])

    def test_a_module_error_is_none_never_legacy_and_sets_the_error(self):
        ig = self.new_space('Integ', integrations=True)
        with mock.patch.object(dm, '_provider_for', side_effect=dm.ModuleError('bad-manifest', message='x')):
            caps = dm.capabilities(ig)
        self.assertIsNone(caps['notify'])
        self.assertEqual(caps['error'], 'bad-manifest')
        self.assertEqual((caps['publish'], caps['vcs']), ('legacy', 'legacy'))     # а локальні ролі лишились зашитими
        dm.reset_caches()
        with mock.patch.object(dm, '_caps_key', side_effect=RuntimeError('bug')):      # запасний словник: теж не 'legacy'
            self.assertIsNone(dm.capabilities(ig)['notify'])

    def test_an_unreadable_space_json_in_an_integrations_space_never_yields_legacy(self):
        """⛔ Як `comments`, `dashboard`, `tracker`: нечитабельний `space.json` у просторі з інтеграціями дає
        `space-json-unreadable`, а не `'legacy'` (не знаємо, чи людина ввімкнула там свій модуль сповіщень)."""
        ig = self.new_space('Integ', integrations=True)
        with open(os.path.join(ig['path'], 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('notify', ig)
        self.assertEqual(cm.exception.code, 'space-json-unreadable')
        caps = dm.capabilities(ig)
        self.assertIsNone(caps['notify'])
        self.assertEqual(caps['error'], 'space-json-unreadable')
        self.assertEqual((caps['publish'], caps['vcs']), ('legacy', 'legacy'))     # локальні ролі шлях ЛІГИ не втрачають

    def test_the_error_codes_have_http_statuses(self):
        self.assertEqual(dm.STATUS['notify-unconfigured'], 409)
        self.assertEqual(dm.STATUS['notify-error'], 502)
        self.assertEqual(dm.ModuleError('notify-unconfigured').status, 409)
        self.assertEqual(dm.ModuleError('notify-error').status, 502)


def _rows_of(case):
    """Рядки стану тиші зі знімка: `db` → список `{project_id, muted_at, muted_by?}`; `muted_at` у знімку — лише ТИП."""
    rows = []
    for pid, rec in case['db'].items():
        row = {'project_id': pid}
        row.update(rec)
        row['muted_at'] = '2026-11-01T10:00:00' if rec.get('muted_at') == 'str' else None
        rows.append(row)
    return rows


def _typed(view):
    """Вигляд каналу з типом замість значення `muted_at` — як у знімку."""
    out = dict(view)
    if 'muted_at' in out:
        out['muted_at'] = type(out['muted_at']).__name__
    return out


class NotifyCore(unittest.TestCase):
    """Ядро `app/notify.py` (4c-3, Task 2): нормалізація стану тиші, вигляд каналу, перевірка аргументів `mute_set`."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def test_constants(self):
        self.assertEqual((notify.NOTIFY_TIMEOUT, notify.MAX_MUTES, notify.CHANNEL_MAX, notify.BY_MAX),
                         (10, 1000, 200, 200))
        self.assertEqual(notify.LEGACY_MODULE, 'supabase-teams')
        self.assertEqual(notify.UNCONFIGURED, 'Supabase не налаштовано')

    def test_the_core_does_not_import_serve(self):
        """⛔ `serve` тягне сервер, мережу й увесь стан: ядро ролі його не імпортує (як `tracker.py`, `dashboard.py`)."""
        import ast
        with open(os.path.join(ROOT, 'app', 'notify.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names.update(a.name.split('.')[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                names.add((n.module or '').split('.')[0])
        self.assertNotIn('serve', names)

    # ----- normalize_mutes

    def test_normalize_keeps_only_dicts_with_a_string_project_id_of_1_to_200(self):
        ok = {'project_id': 'dc/t1', 'muted_at': '2026-11-01T10:00:00', 'muted_by': 'k:0123456789ab'}
        rows = [ok, 'x', None, 7, [], {}, {'project_id': ''}, {'project_id': 5}, {'project_id': None},
                {'project_id': 'p' * 201}, {'project_id': 'p' * 200}, {'muted_by': 'x'}]
        got = notify.normalize_mutes(rows)
        self.assertEqual([r['project_id'] for r in got], ['dc/t1', 'p' * 200])
        self.assertEqual(got[0], ok)

    def test_normalize_cleans_muted_by_and_muted_at(self):
        rows = [{'project_id': 'a', 'muted_by': 5, 'muted_at': 5},
                {'project_id': 'b', 'muted_by': 'x' * 201, 'muted_at': 't' * 41},
                {'project_id': 'c', 'muted_by': 'x' * 200, 'muted_at': 't' * 40},
                {'project_id': 'd'},
                {'project_id': 'e', 'muted_by': None, 'muted_at': None}]
        got = {r['project_id']: r for r in notify.normalize_mutes(rows)}
        self.assertEqual(got['a'], {'project_id': 'a', 'muted_at': None, 'muted_by': ''})
        self.assertEqual(got['b'], {'project_id': 'b', 'muted_at': None, 'muted_by': ''})
        self.assertEqual(got['c'], {'project_id': 'c', 'muted_at': 't' * 40, 'muted_by': 'x' * 200})
        self.assertEqual(got['d'], {'project_id': 'd', 'muted_at': None, 'muted_by': ''})
        self.assertEqual(got['e'], {'project_id': 'e', 'muted_at': None, 'muted_by': ''})

    def test_normalize_drops_unknown_keys(self):
        got = notify.normalize_mutes([{'project_id': 'a', 'secret': 'x', 'muted_by': 'k:1'}])
        self.assertEqual(got, [{'project_id': 'a', 'muted_at': None, 'muted_by': 'k:1'}])

    def test_normalize_caps_the_number_of_rows(self):
        rows = [{'project_id': f'dc/t{i}'} for i in range(notify.MAX_MUTES + 5)]
        got = notify.normalize_mutes(rows)
        self.assertEqual(len(got), notify.MAX_MUTES)
        self.assertEqual(got[0]['project_id'], 'dc/t0')
        self.assertEqual(got[-1]['project_id'], f'dc/t{notify.MAX_MUTES - 1}')
        self.assertEqual(len(notify.normalize_mutes(rows[:notify.MAX_MUTES])), notify.MAX_MUTES)

    def test_normalize_rejects_a_non_list(self):
        for bad in (None, {}, {'project_id': 'a'}, 'rows', 5, ({'project_id': 'a'},)):
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.normalize_mutes(bad)
        self.assertEqual(notify.normalize_mutes([]), [])

    # ----- mute_view

    ME, OTHER = 'k:0123456789ab', 'k:ffffffffffff'

    def row(self, pid, by='k:ffffffffffff', at='2026-11-01T10:00:00'):
        return {'project_id': pid, 'muted_at': at, 'muted_by': by}

    def test_view_of_a_channel_that_is_not_muted(self):
        self.assertEqual(notify.mute_view('dc/t1', [], self.ME), {'channel': 'dc/t1', 'muted': False})
        self.assertEqual(notify.mute_view('dc/t1', None, self.ME), {'channel': 'dc/t1', 'muted': False})
        self.assertEqual(notify.mute_view('dc/t1', [self.row('dc/other')], self.ME), {'channel': 'dc/t1', 'muted': False})

    def test_view_of_an_exact_match_and_of_a_subchannel_under_a_muted_parent(self):
        self.assertEqual(notify.mute_view('dc/t1', [self.row('dc/t1')], self.ME),
                         {'channel': 'dc/t1', 'muted': True, 'muted_by': self.OTHER, 'mine': False,
                          'muted_at': '2026-11-01T10:00:00', 'via': 'dc/t1'})
        sub = notify.mute_view('dc/t1/internal', [self.row('dc/t1')], self.ME)
        self.assertEqual((sub['channel'], sub['muted'], sub['via']), ('dc/t1/internal', True, 'dc/t1'))
        deeper = notify.mute_view('dc/t1/a/b', [self.row('dc/t1')], self.ME)
        self.assertEqual((deeper['muted'], deeper['via']), (True, 'dc/t1'))

    def test_a_muted_subchannel_does_not_mute_its_parent(self):
        self.assertEqual(notify.mute_view('dc/t1', [self.row('dc/t1/internal')], self.ME), {'channel': 'dc/t1', 'muted': False})

    def test_prefix_collisions_are_not_parents(self):
        """⛔ `dc/t10` і `dc/t1x` — НЕ батьки `dc/t1`: підканал лише за `<канал>/`, а не за голим префіксом."""
        for other in ('dc/t10', 'dc/t1x', 'dc/t1-b', 'dc/t'):
            self.assertEqual(notify.mute_view('dc/t1', [self.row(other)], self.ME), {'channel': 'dc/t1', 'muted': False}, other)
        self.assertEqual(notify.mute_view('dc/t10', [self.row('dc/t1')], self.ME)['muted'], False)

    def test_mine_only_with_a_non_empty_matching_signature(self):
        mine = notify.mute_view('dc/t1', [self.row('dc/t1', by=self.ME)], self.ME)
        self.assertIs(mine['mine'], True)
        self.assertIs(notify.mute_view('dc/t1', [self.row('dc/t1', by=self.OTHER)], self.ME)['mine'], False)
        for by in ('', None):                       # рядок без підпису (застарілий) — не мій ні за яких умов
            for me in (self.ME, ''):
                v = notify.mute_view('dc/t1', [{'project_id': 'dc/t1', 'muted_by': by}], me)
                self.assertTrue(v['muted'])
                self.assertIs(v['mine'], False, (by, me))
                self.assertEqual(v['muted_by'], '')
        v = notify.mute_view('dc/t1', [self.row('dc/t1', by=self.ME)], '')        # порожній підпис машини
        self.assertIs(v['mine'], False)

    def test_the_first_matching_row_wins(self):
        rows = [self.row('dc/other'), self.row('dc/t1', by=self.OTHER), self.row('dc/t1', by=self.ME)]
        self.assertEqual(notify.mute_view('dc/t1', rows, self.ME)['muted_by'], self.OTHER)

    def test_view_matches_the_0_13_0_snapshot_of_the_route(self):
        """Паритет зі знімком GET `/api/teams-mute` ЛІГИ на 0.13.0: той самий вигляд на всіх 11 кейсах (колізії префікса,
        підканал, рядки без `muted_by`, порожній підпис)."""
        cases = self.snap['route']['fake_get']
        self.assertEqual(len(cases), 11)
        for name, case in cases.items():
            me = case.get('signature', self.ME)
            channel = case['body']['channel']
            got = _typed(notify.mute_view(channel, _rows_of(case), me))
            self.assertEqual(got, case['body'], name)

    def test_view_equals_serve_teams_mute_view_on_the_snapshot_and_on_edge_rows(self):
        """Диференційно проти `serve.teams_mute_view` (він лишається до Task 4): ті самі відповіді на всіх кейсах знімка й на
        крайових рядках."""
        edge = [[{'project_id': 'dc/t1'}], [{'project_id': ''}], [{'project_id': None, 'muted_by': 'k:0123456789ab'}],
                [{'muted_by': 'k:0123456789ab'}], [{'project_id': 'dc/t1', 'muted_by': None}],
                [{'project_id': 'dc/t1', 'muted_by': 'k:0123456789ab', 'muted_at': None}],
                [self.row('dc/t'), self.row('dc/t1/x/y', by=self.ME)], [], None]
        pool = [(c['body']['channel'], _rows_of(c), c.get('signature', self.ME))
                for c in self.snap['route']['fake_get'].values()]
        pool += [(ch, rows, me) for rows in edge for ch in ('dc/t1', 'dc/t1/internal', 'x') for me in (self.ME, '')]
        for channel, rows, me in pool:
            with mock.patch.object(serve, 'mute_signature', return_value=me):
                want = serve.teams_mute_view(channel, rows)
            self.assertEqual(notify.mute_view(channel, rows, me), want, (channel, rows, me))

    # ----- check_set_args

    def test_set_args_accept_a_valid_call(self):
        for args in (('dc/t1', True, 'k:0123456789ab'), ('dc/t1/internal', False, ''), ('c' * 200, True, 'b' * 200)):
            self.assertIsNone(notify.check_set_args(*args), args)

    def test_set_args_reject_a_bad_channel(self):
        for bad in ('', None, 5, b'dc/t1', ['dc/t1'], 'c' * 201):
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.check_set_args(bad, True, '')

    def test_set_args_reject_a_non_bool_muted(self):
        for bad in ('yes', 'true', 1, 0, None, [], {}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.check_set_args('dc/t1', bad, '')

    def test_set_args_reject_a_bad_signature(self):
        for bad in ('b' * 201, None, 5, b'k'):
            with self.assertRaises(ValueError, msg=repr(bad)):
                notify.check_set_args('dc/t1', True, bad)


if __name__ == '__main__':
    unittest.main()
