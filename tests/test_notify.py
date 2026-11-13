"""Роль `notify` (етап 4c-3, спека 2026-11-03-notify-role-design.md).

Тут: знімок поведінки 0.13.0 (`Before4c3Shape`, Task 1), роль у каркасі модулів (`NotifyRole`, Task 2), чисте ядро
`app/notify.py` (`NotifyCore`, Task 2, з паритетом проти `serve.teams_mute_view` і знімка) і адаптер ЛІГИ
(`LegacyAdapter`, Task 3) і сервер (`ServerPath`, Task 4: `notify_call` замість `teams_rpc`, маршрут `/api/teams-mute` за
роллю). Наступні задачі додають класи, що читають той самий JSON.
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
import liga_fixture  # noqa: E402
import make_before_4c3 as mb  # noqa: E402  (лише помічники знімка: сервер у процесі, простори, записувач; ЗАПУСКУ генератора нема)
import notify  # noqa: E402
import serve  # noqa: E402  (сервер Task 4; ядро `notify` сам `serve` НЕ імпортує)
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
        self.assertIn('supabase-teams', dm.KNOWN_OTHER_MODULES)
        # 4d-4b: `IMPLICIT_ROLES`/`STRICT_IMPLICIT_ROLES`/`IMPLICIT_ON_ERROR_ROLES` зникли разом із запасним постачальником
        # (`test_originals_gone.ProviderWithoutImplicit.test_the_core_has_no_fallback_names`).
        for gone in ('IMPLICIT_ROLES', 'STRICT_IMPLICIT_ROLES', 'IMPLICIT_ON_ERROR_ROLES'):
            self.assertFalse(hasattr(dm, gone), gone)

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

    def test_a_space_without_a_notify_record_has_no_provider_with_or_without_integrations(self):
        """4d-4b (було `…_is_legacy`): запасного шляху нема — простір з інтеграціями без запису `notify` теж без нікого."""
        ig = self.new_space('Integ', integrations=True)
        plain = self.new_space('Plain')
        for sp in (ig, plain):
            self.assertIsNone(dm.provider('notify', sp))
            self.assertIsNone(dm.capabilities(sp)['notify'])

    def test_an_enabled_module_is_the_provider_in_both_kinds_of_space(self):
        self.mk('ntf-ok', roles=('notify',), server=NOTIFY_SERVER)
        ig = self.new_space('Integ', integrations=True)
        plain = self.new_space('Plain')
        for sp in (ig, plain):
            dm.write_module_state(sp, 'ntf-ok', enabled=True)
            self.assertEqual(dm.provider('notify', sp).id, 'ntf-ok')
            self.assertEqual(dm.capabilities(sp)['notify'], 'ntf-ok')
        dm.write_module_state(ig, 'ntf-ok', enabled=False)
        self.assertIsNone(dm.capabilities(ig)['notify'])            # вимкнули: запасного шляху нема (4d-4b) — нікого
        dm.write_module_state(plain, 'ntf-ok', enabled=False)
        self.assertIsNone(dm.capabilities(plain)['notify'])

    def test_a_module_error_is_none_never_legacy_and_sets_the_error(self):
        ig = self.new_space('Integ', integrations=True)
        with mock.patch.object(dm, '_provider_for', side_effect=dm.ModuleError('bad-manifest', message='x')):
            caps = dm.capabilities(ig)
        self.assertIsNone(caps['notify'])
        self.assertEqual(caps['error'], 'bad-manifest')
        self.assertEqual((caps['publish'], caps['vcs']), (None, None))     # 4d-4b: підміна кидає для КОЖНОЇ ролі, зашитих нема
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
        self.assertEqual((caps['publish'], caps['vcs']), (None, None))     # 4d-4b: нечитабельний `space.json` — помилка КОЖНОЇ ролі

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


def _reference_mute_view(channel, rows, me):
    """`serve.teams_mute_view` 0.13.0 дослівно (підпис машини — аргументом замість `mute_signature()`)."""
    for r in rows or []:
        pid = r.get('project_id') or ''
        if pid and (channel == pid or channel.startswith(pid + '/')):
            by = r.get('muted_by') or ''
            return {'channel': channel, 'muted': True, 'muted_by': by,
                    'mine': bool(by) and by == me,
                    'muted_at': r.get('muted_at'), 'via': pid}
    return {'channel': channel, 'muted': False}


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
        self.assertEqual(notify.UNCONFIGURED, 'Supabase не налаштовано: додайте адресу й ключ на екрані «Налаштування»')   # R5 (4d-4b)

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

    def test_view_equals_the_0_13_0_reference_on_the_snapshot_and_on_edge_rows(self):
        """Диференційно проти ДОСЛІВНОЇ копії `serve.teams_mute_view` 0.13.0 (`_reference_mute_view`; з функції в `serve` Task 4
        її прибрав): ті самі відповіді на всіх кейсах знімка й на крайових рядках."""
        edge = [[{'project_id': 'dc/t1'}], [{'project_id': ''}], [{'project_id': None, 'muted_by': 'k:0123456789ab'}],
                [{'muted_by': 'k:0123456789ab'}], [{'project_id': 'dc/t1', 'muted_by': None}],
                [{'project_id': 'dc/t1', 'muted_by': 'k:0123456789ab', 'muted_at': None}],
                [self.row('dc/t'), self.row('dc/t1/x/y', by=self.ME)], [], None]
        pool = [(c['body']['channel'], _rows_of(c), c.get('signature', self.ME))
                for c in self.snap['route']['fake_get'].values()]
        pool += [(ch, rows, me) for rows in edge for ch in ('dc/t1', 'dc/t1/internal', 'x') for me in (self.ME, '')]
        for channel, rows, me in pool:
            want = _reference_mute_view(channel, rows, me)
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


# ------------------------------------------------------------------------------------------ Task 3: адаптер ЛІГИ

class LeagueNotifyRecord(tm.Env):
    """4d-4b (було `LegacyAdapter`): `notify.legacy_ctx`/`legacy_module` — адаптер неявного постачальника — видалено. Сповіщення ЛІГИ — звичайний
    запис `supabase-teams` (`compat: comment-layer`) із секретом `key`: `ctx` будує ядро (`module_ctx`) з ЗАПИСУ, корінь `tasks.json` не читається."""

    def setUp(self):
        super().setUp()
        os.environ['DEAI_HOME'] = self.deai          # статичний охоронець `test_serve.TestsCannotWriteLiveConfig` шукає присвоєння в файлі
        self.addCleanup(dm.reset_caches)
        patch = mock.patch.object(dm, 'builtin_dir', tm._REAL_BUILTIN_DIR)
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()

    def test_ctx_is_built_from_the_record_and_the_secret(self):
        """Замінює `test_legacy_ctx_is_built_from_the_install_config_not_from_the_frame` і `test_legacy_module_is_the_builtin_supabase_teams`."""
        sp = self.liga_space(roles=('notify',))
        m = dm.provider('notify', sp)
        self.assertEqual((m.id, m.status, m.roles), ('supabase-teams', 'ok', ['notify']))
        for fn in ('check', 'mute_state', 'mute_set'):
            self.assertTrue(callable(m.fn(fn)), fn)
        ctx = dm.module_ctx(sp, m)
        self.assertEqual(ctx['settings'], {'url': liga_fixture.SB_URL, 'compat': 'comment-layer'})
        self.assertEqual(ctx['secrets'], {'key': liga_fixture.SB_KEY})
        self.assertEqual(ctx['space']['id'], 'legacy')
        self.assertIs(ctx['ModuleError'], dm.ModuleError)

    def test_the_root_and_the_environment_are_never_read(self):
        """Замінює `test_legacy_ctx_never_reads_the_spaces_layer` (урок 4c-1) під 4d-4b: ні корінь, ні `SUPABASE_*` облікових не дають."""
        import install_config
        sp = self.liga_space(roles=('notify',))
        tm._write(self.legacy, {'supabase_url': 'https://root.example.com', 'supabase_key': 'root-key'})
        with mock.patch.dict(os.environ, {'SUPABASE_URL': 'https://env.example.com', 'SUPABASE_KEY': 'env-key'}), \
                mock.patch.object(install_config, 'load_legacy_tasks', side_effect=AssertionError('корінь не читаємо')):
            ctx = dm.module_ctx(sp, dm.provider('notify', sp))
        self.assertEqual((ctx['settings']['url'], ctx['secrets']['key']), (liga_fixture.SB_URL, liga_fixture.SB_KEY))

    def test_without_a_record_or_with_a_disabled_one_there_is_no_provider(self):
        """Замінює `test_legacy_ctx_without_a_config_is_notify_unconfigured` і `test_legacy_module_not_loaded_is_module_error`: нема запису
        (або він вимкнений) — постачальника нема (`None`)."""
        sp = self.liga_space(roles=('tracker',))
        self.assertIsNone(dm.provider('notify', sp))
        sp = self.liga_space(roles=('notify',), overrides={'notify': {'enabled': False}})
        self.assertIsNone(dm.provider('notify', sp))
        self.assertIsNone(dm.capabilities(sp)['notify'])

    def test_end_to_end_the_module_with_the_record_ctx(self):
        """Замінює `test_end_to_end_the_module_with_the_legacy_ctx`: справжній вбудований модуль із `ctx` запису (шов `_open` — записувач):
        адреса й ключ ідуть із запису, запит — той самий, що `teams_rpc` 0.13.0 (знімок), `check` не кличе `teams_notify_health`."""
        sp = self.liga_space(roles=('notify',), overrides={'notify': {'settings': {'url': 'https://demo.supabase.example'},
                                                                        'secrets': {'key': 'sk-test-1'}}})
        m = dm.provider('notify', sp)
        seen = []

        class R:
            status = 200

            def __init__(self, body):
                self._b = json.dumps(body).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n=-1):
                return self._b

        def fake(req, timeout):
            seen.append((req.full_url, timeout, {k.lower(): v for k, v in req.header_items()}, req.data))
            return R(True if req.full_url.endswith('teams_mute_set') else [])

        ctx = dm.module_ctx(sp, m)
        with mock.patch.dict(m.fn('check').__globals__, {'_open': fake}):
            self.assertEqual(dm.call(m, 'mute_state', ctx), [])
            self.assertIs(dm.call(m, 'mute_set', ctx, 'dc/t1', True, 'k:0123456789ab'), True)
            self.assertTrue(dm.call(m, 'check', ctx)['ok'])
        self.assertEqual([u.rsplit('/', 1)[-1] for u, *_ in seen],
                         ['teams_mute_state', 'teams_mute_set', 'teams_mute_state'])
        for url, timeout, headers, _ in seen:
            self.assertTrue(url.startswith('https://demo.supabase.example/rest/v1/rpc/'))
            self.assertEqual(timeout, 8)
            self.assertEqual(headers['apikey'], 'sk-test-1')
            self.assertEqual(headers['authorization'], 'Bearer sk-test-1')
        self.assertEqual(json.loads(seen[1][3]), {'p_project': 'dc/t1', 'p_muted': True, 'p_by': 'k:0123456789ab'})


# ------------------------------------------------------------------------------------------ Task 4: сервер

#: Модуль-фікстура `notify` для маршруту: кожен виклик пишеться в `CALLS`, поведінку задають глобали модуля (`MODE`, `STATE`,
#: `SET_ANSWER`) — тест міняє їх через `fn.__globals__` модуля, який справді викликає сервер.
RECORDING_NOTIFY = tm.CHECK_ONLY + """
CALLS = []
MODE = 'ok'
STATE = []
SET_ANSWER = 'echo'


def mute_state(ctx):
    CALLS.append(('mute_state',))
    if MODE == 'fail':
        raise ctx['ModuleError']('notify-error', message='service is down')
    return STATE


def mute_set(ctx, channel, muted, by):
    CALLS.append(('mute_set', channel, muted, by))
    if MODE == 'fail':
        raise ctx['ModuleError']('notify-error', message='service is down')
    return muted if SET_ANSWER == 'echo' else SET_ANSWER
"""


class _OpenResp:
    """Відповідь шва `_open` модуля: контекстний менеджер зі `status` і `read`."""
    status = 200

    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *limit):
        return self._body


class _OpenRec(mb.Recorder):
    """Записувач `mb.Recorder` для шва `_open(req, timeout)` модуля (знімок писав `urlopen(req, timeout, context)`)."""

    answers = {}              # `{імʼя RPC: тіло}` — окрема відповідь на конкретний RPC (типово — `body`)

    def __call__(self, req, timeout=None, **kw):
        super().__call__(req, timeout=timeout)
        return _OpenResp(self.answers.get(req.full_url.rsplit('/', 1)[-1], self.body))


def _db_of(case):
    """Файл шва `DC_TEAMS_FAKE` зі знімка: `{канал: {muted_at, muted_by?}}`; у знімку `muted_at` — лише ТИП."""
    return {pid: {**rec, 'muted_at': '2026-11-01T10:00:00' if rec.get('muted_at') == 'str' else None}
            for pid, rec in case['db'].items()}


class ServerPath(tm.Env):
    """Task 4: `serve.notify_resolve()` + `serve.notify_call()` замість `teams_rpc`, маршрут `/api/teams-mute` — за
    постачальником ролі `notify`. ЛІГА (шов `DC_TEAMS_FAKE` і шлях через вбудований модуль із підміненим `_open`) — диференційно
    проти знімка 0.13.0; звичайний простір — через фейковий модуль. Мережі нема: `_open` завжди підмінений записувачем."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def setUp(self):
        # знімок оточення ДО `Env.setUp`: його скасування (після `tearDown`) повертає початкові значення
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        super().setUp()
        os.environ['DEAI_HOME'] = self.deai          # статичний охоронець шукає присвоєння в тексті самого файла
        for k in mb.CLEAN:
            if k != 'DEAI_HOME':
                os.environ.pop(k, None)               # як у генераторі знімка: чисте оточення (ізоляція — лише на час випадку)
        os.environ.pop('SUPABASE_URL', None)
        os.environ.pop('SUPABASE_KEY', None)
        self.ids = mb.setup_spaces(self.tmp)         # `liga` (інтеграції; задачі t1, t2) і `plain` (без; задача p1)
        self.league_record()
        self.fake = os.path.join(self.tmp, 'teams-fake.json')
        self.sig = mock.patch.object(serve, 'mute_signature', lambda: mb.MINE)
        self.sig.start()
        self.addCleanup(self.sig.stop)

    # ---- допоміжне
    def real_builtins(self):
        """Шлях ЛІГИ: справжній `supabase-teams` з `app/modules` (а не тека фікстур `Env`)."""
        patch = mock.patch.object(dm, 'builtin_dir', tm._REAL_BUILTIN_DIR)
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()

    def league_record(self, roles=('notify',), **notify_override):
        """Явний запис `supabase-teams` у просторі `liga` (4d-4b: запасного шляху й оригіналів кореня нема): адреса й ключ — вигадані
        (`mb.URL`/`mb.KEY`), секрет — у `secrets.json` дому тесту; `roles=()` — без запису (ЛІГА без сповіщень)."""
        liga_fixture.write_records(self.rec(self.ids['liga'])['path'], self.deai, self.ids['liga'], roles,
                                   {'notify': dict({'settings': {'url': mb.URL}, 'secrets': {'key': mb.KEY}}, **notify_override)})
        dm.reset_caches()

    def pin_league(self):
        """Закріпити простір `liga` простором запиту ПОТОЧНОГО потоку (як це робить обробник): без цього `notify_call` напряму бачить неявний
        простір (ролей нема)."""
        import spaces
        spaces.set_request_space(self.ids['liga'])
        self.addCleanup(spaces.clear_request_space)

    def open_seam(self, rec):
        """Шов `_open` вбудованого `supabase-teams`: усе, що модуль шле в мережу, йде в записувач."""
        patch = mock.patch.dict(dm.catalog()['supabase-teams'].fn('check').__globals__, {'_open': rec})
        patch.start()
        self.addCleanup(patch.stop)

    def srv(self):
        s = mb.Server().__enter__()
        self.addCleanup(s.__exit__, None, None, None)
        return s

    def get(self, srv, task):
        st, body = srv.req('GET', '/api/teams-mute', task)
        return st, mb.stamp_type(body)

    def post(self, srv, task, payload, origin='local'):
        st, body = srv.req('POST', '/api/teams-mute', task, payload, origin)
        return st, mb.stamp_type(body)

    def db_now(self):
        try:
            with open(self.fake, encoding='utf-8') as f:
                return mb.stamp_type(json.load(f))
        except (OSError, ValueError):
            return None

    def fake_module_space(self):
        """Звичайний простір без інтеграцій + свій (тут вбудований у `Env`) модуль `notify`, ЯВНО ввімкнений у ньому. Повертає
        глобали модуля: `CALLS` (виклики), `MODE`, `STATE`, `SET_ANSWER` — їх міняє тест."""
        self.mk('ntf-fake', roles=('notify',), server=RECORDING_NOTIFY)
        sp = self.rec(self.ids['plain'])
        dm.write_module_state(sp, 'ntf-fake', enabled=True)
        return dm.provider('notify', sp).fn('mute_state').__globals__

    # ---- відсутність старого API
    def test_teams_rpc_and_teams_mute_view_are_gone_and_the_signature_stays(self):
        self.assertFalse(hasattr(serve, 'teams_rpc'))
        self.assertFalse(hasattr(serve, 'teams_mute_view'))
        self.assertTrue(callable(serve.notify_resolve))
        self.assertTrue(callable(serve.notify_call))
        with mock.patch.dict(os.environ, {'DC_IDENTITY_NAME': 'Alpha', 'DC_IDENTITY_EMAIL': 'alpha@example.com'}):
            self.sig.stop()
            try:
                self.assertEqual(serve.mute_signature(), self.snap['route']['signature_real'])
            finally:
                self.sig.start()

    # ---- ЛІГА: шов DC_TEAMS_FAKE — маршрут = знімок 0.13.0
    def test_the_league_fake_seam_gets_are_the_0_13_0_snapshot(self):
        self.real_builtins()
        srv = self.srv()
        os.environ['DC_TEAMS_FAKE'] = self.fake
        for key, case in self.snap['route']['fake_get'].items():
            with self.subTest(case=key):
                mb._write(self.fake, _db_of(case))
                with mock.patch.object(serve, 'mute_signature', lambda: case.get('signature', mb.MINE)):
                    st, body = self.get(srv, case['task'])
                self.assertEqual((st, body), (case['status'], case['body']))

    def test_the_league_fake_seam_posts_are_the_0_13_0_snapshot(self):
        self.real_builtins()
        srv = self.srv()
        os.environ['DC_TEAMS_FAKE'] = self.fake
        want = self.snap['route']['fake_post']
        mb._write(self.fake, {})
        steps = (('mute', 't1', {'muted': True}, 'local'), ('unmute', 't1', {'muted': False}, 'local'),
                 ('mute_subchannel', 't2', {'muted': True}, 'local'))
        for key, task, payload, origin in steps:
            st, body = self.post(srv, task, payload, origin)
            self.assertEqual((st, body, self.db_now()), (want[key]['status'], want[key]['body'], want[key]['db_after']), key)
        mb._write(self.fake, {})
        for key, payload, origin in (('bad_muted', {'muted': 'yes'}, 'local'),
                                     ('foreign_origin', {'muted': True}, 'https://evil.example'),
                                     ('no_origin_header', {'muted': True}, None)):
            st, body = self.post(srv, 't1', payload, origin)
            self.assertEqual((st, body, self.db_now()), (want[key]['status'], want[key]['body'], want[key]['db_after']), key)

    # ---- ЛІГА без шва: запити модуля = запити teams_rpc 0.13.0
    def test_the_league_rpc_requests_are_the_0_13_0_requests(self):
        self.real_builtins()
        self.pin_league()
        rr = self.snap['rpc_requests']
        cases = (('state', ('mute_state',), rr['state']['stub_response']),
                 ('set', ('mute_set', 'dc/t1', True, mb.MINE), True),
                 ('unset', ('mute_set', 'dc/t1', False, mb.MINE), False))
        for key, args, stub in cases:
            with self.subTest(case=key):
                rec = _OpenRec(json.dumps(stub).encode('utf-8'))
                self.open_seam(rec)
                result = serve.notify_call(*args)
                self.assertEqual(result, stub)
                self.assertEqual(len(rec.calls), 1)
                got, want = rec.calls[0], rr[key]['calls'][0]
                for field in ('method', 'path', 'query', 'body', 'timeout', 'host_is_demo', 'headers'):
                    self.assertEqual(got[field], want[field], field)

    def test_the_league_refusals_are_the_0_13_0_refusals(self):
        """Ізоляція — той самий `OSError` з тим самим текстом і без мережі; решта відмов — свідомо інші типи (`ModuleError`)."""
        self.real_builtins()
        self.pin_league()
        rr = self.snap['rpc_requests']
        for key, env in (('isolated_tasks_file', {'DC_TASKS_FILE': os.path.join(self.tmp, 'x-tasks.json')}),
                         ('isolated_no_overview', {'DC_NO_OVERVIEW': '1'})):
            rec = _OpenRec(b'[]')
            self.open_seam(rec)
            with mock.patch.dict(os.environ, env), self.assertRaises(OSError) as cm:
                serve.notify_call('mute_state')
            self.assertEqual((type(cm.exception).__name__, str(cm.exception), len(rec.calls)),
                             ('OSError', rr[key]['message'], 0), key)

    def test_the_league_record_without_an_address_is_notify_unconfigured(self):
        """4d-4b (було `…without_a_config_is_notify_unconfigured_with_the_old_text`): «нема конфігу» тепер — запис без адреси (оригіналів
        кореня нема). Код той самий, мережі нема; ТЕКСТ — модуля (знімок 0.13.0 мав «Supabase не налаштовано», R5)."""
        self.real_builtins()
        self.pin_league()
        self.league_record(settings={'url': ''})
        rec = _OpenRec(b'[]')
        self.open_seam(rec)
        with self.assertRaises(dm.ModuleError) as cm:
            serve.notify_call('mute_state')
        self.assertEqual((cm.exception.code, len(rec.calls)), ('notify-unconfigured', 0))
        self.assertNotEqual(cm.exception.message, self.snap['rpc_requests']['no_supabase']['message'])

    def test_the_league_without_a_notify_record_has_no_provider(self):
        """4d-4b: ЛІГА без запису `supabase-teams` — сповіщень нема (`OSError`, мережі нема), а не `notify-unconfigured`: оригінали кореня
        (адреса й ключ у `tasks.json`/оточенні) запису не замінюють."""
        self.real_builtins()
        self.pin_league()
        self.league_record(roles=())
        mb._write(self.legacy, {'supabase_url': mb.URL, 'supabase_key': mb.KEY})
        rec = _OpenRec(b'[]')
        self.open_seam(rec)
        with mock.patch.dict(os.environ, {'SUPABASE_URL': mb.URL, 'SUPABASE_KEY': mb.KEY}), self.assertRaises(OSError):
            serve.notify_call('mute_state')
        self.assertEqual(rec.calls, [])

    def test_a_network_failure_is_a_notify_error_not_a_bare_oserror(self):
        self.real_builtins()
        self.pin_league()
        rec = _OpenRec(exc=OSError('мережі нема'))
        self.open_seam(rec)
        with self.assertRaises(dm.ModuleError) as cm:
            serve.notify_call('mute_state')
        self.assertEqual((cm.exception.code, len(rec.calls)), ('notify-error', 1))

    def test_without_a_provider_notify_call_never_reaches_the_network(self):
        """Простір без інтеграцій і без модуля: `OSError` (як було з `IntegrationsOff`), жодного запиту."""
        self.real_builtins()
        rec = _OpenRec(b'[]')
        self.open_seam(rec)
        import spaces
        with spaces.request_space(self.ids['plain']), self.assertRaises(OSError):
            serve.notify_call('mute_state')
        self.assertEqual(rec.calls, [])

    # ---- ЛІГА: маршрут без шва
    def test_the_league_route_through_the_module_matches_the_snapshot_requests(self):
        self.real_builtins()
        srv = self.srv()
        real = self.snap['route']['real_path']
        rec = _OpenRec(json.dumps(mb.STATE_ROWS).encode('utf-8'))
        rec.answers = {'teams_mute_set': b'true'}          # знімок віддавав список і на `mute_set` (його не читали); модуль читає `bool`
        self.open_seam(rec)
        st, body = self.get(srv, 't1')
        self.assertEqual((st, body), (real['get']['status'], real['get']['body']))
        self.assertEqual([c['path'] for c in rec.calls], [c['path'] for c in real['get']['rpc_calls']])
        rec.calls.clear()
        st, body = self.post(srv, 't1', {'muted': True})
        self.assertEqual((st, body), (real['post_mute']['status'], real['post_mute']['body']))
        got = [(c['path'], c['body']) for c in rec.calls]
        self.assertEqual(got, [(c['path'], c['body']) for c in real['post_mute']['rpc_calls']])

    def assert_no_secrets(self, text):
        """Текст помилки для екрана не несе ні ключа, ні адреси Supabase."""
        for needle in (mb.KEY, mb.URL, 'demo.supabase.example'):
            self.assertNotIn(needle, str(text))

    def test_the_league_route_on_a_network_failure_keeps_the_0_13_0_shape(self):
        """GET — 200 `{channel, error}` (без `muted`), POST — 502 `{ok: false, channel, error}`: форма та сама, текст — модуля."""
        self.real_builtins()
        srv = self.srv()
        self.open_seam(_OpenRec(exc=OSError('мережі нема')))
        real = self.snap['route']['real_path']
        st, body = self.get(srv, 't1')
        self.assertEqual((st, sorted(body)), (200, sorted(real['get_network_error']['body'])))
        self.assertEqual(body['channel'], 'dc/t1')
        self.assertTrue(body['error'])
        self.assert_no_secrets(body['error'])
        st, body = self.post(srv, 't1', {'muted': True})
        self.assertEqual((st, sorted(body)), (502, sorted(real['post_network_error']['body'])))
        self.assertIs(body['ok'], False)
        self.assert_no_secrets(body['error'])

    def test_the_league_route_in_an_isolated_run_never_reaches_the_network(self):
        self.real_builtins()
        srv = self.srv()
        for key, env in (('tasks_file', {'DC_TASKS_FILE': os.path.join(self.tmp, 'x-tasks.json')}),
                         ('no_overview', {'DC_NO_OVERVIEW': '1'})):
            want = self.snap['route']['isolated'][key]
            rec = _OpenRec(json.dumps(mb.STATE_ROWS).encode('utf-8'))
            self.open_seam(rec)
            with mock.patch.dict(os.environ, env):
                got_get, got_post = self.get(srv, 't1'), self.post(srv, 't1', {'muted': True})
            self.assertEqual(got_get, (want['get']['status'], want['get']['body']), key)
            self.assertEqual(got_post, (want['post']['status'], want['post']['body']), key)
            self.assertEqual(rec.calls, [], key)

    # ---- простір без постачальника: 409 notify-off
    def test_a_space_without_a_provider_answers_409_notify_off(self):
        self.real_builtins()
        srv = self.srv()
        os.environ['DC_TEAMS_FAKE'] = self.fake            # шов діє лише для 'legacy': тут його мають ігнорувати
        mb._write(self.fake, {'dc/p1': {'muted_at': None, 'muted_by': mb.COLLEAGUE}})
        rec = _OpenRec(b'[]')
        self.open_seam(rec)
        off = {'ok': False, 'code': 'notify-off', 'error': 'сповіщень Teams у просторі нема'}
        before = self.db_now()
        self.assertEqual(self.get(srv, 'p1'), (409, off))
        self.assertEqual(self.post(srv, 'p1', {'muted': True}), (409, off))
        self.assertEqual(self.post(srv, 'p1', {'muted': 'yes'}), (409, off), 'шлюз — раніше за перевірку muted, як було')
        self.assertEqual(self.post(srv, 'p1', {'muted': True}, 'https://evil.example'), (403, {'ok': False, 'error': 'foreign origin'}))
        self.assertEqual((self.db_now(), rec.calls), (before, []))

    def test_the_old_integrations_off_code_is_replaced_not_duplicated(self):
        self.real_builtins()
        srv = self.srv()
        st, body = self.get(srv, 'p1')
        self.assertEqual(st, 409)
        self.assertNotEqual(body['code'], 'integrations-off')

    # ---- звичайний простір із модулем
    def test_a_plain_space_with_a_module_works_through_the_module(self):
        g = self.fake_module_space()
        srv = self.srv()
        os.environ['DC_TEAMS_FAKE'] = self.fake            # ⛔ шов лише для 'legacy': з модулем його не читають і не пишуть
        mb._write(self.fake, {'dc/p1': {'muted_at': None, 'muted_by': mb.COLLEAGUE}})
        before = self.db_now()
        g['STATE'] = [{'project_id': 'dc/p1', 'muted_at': '2026-11-01T10:00:00', 'muted_by': mb.MINE, 'extra': 1}]
        st, body = self.get(srv, 'p1')
        self.assertEqual((st, body), (200, {'channel': 'dc/p1', 'muted': True, 'muted_by': mb.MINE, 'mine': True,
                                            'muted_at': 'str', 'via': 'dc/p1'}))
        g['STATE'] = []
        st, body = self.post(srv, 'p1', {'muted': True})
        self.assertEqual((st, body), (200, {'ok': True, 'channel': 'dc/p1', 'muted': False}), 'вигляд — зі стану ПІСЛЯ перемикання')
        self.assertEqual(g['CALLS'], [('mute_state',), ('mute_set', 'dc/p1', True, mb.MINE), ('mute_state',)])
        self.assertEqual(self.db_now(), before)

    def test_a_module_failure_is_get_error_and_post_502(self):
        g = self.fake_module_space()
        srv = self.srv()
        g['MODE'] = 'fail'
        st, body = self.get(srv, 'p1')
        self.assertEqual((st, body), (200, {'channel': 'dc/p1', 'error': 'service is down'}))
        st, body = self.post(srv, 'p1', {'muted': True})
        self.assertEqual((st, body), (502, {'ok': False, 'channel': 'dc/p1', 'error': 'service is down'}))

    def test_a_bad_muted_is_400_before_the_module_is_called(self):
        g = self.fake_module_space()
        srv = self.srv()
        for bad in ('yes', 1, 0, None, 'true', [True]):
            st, body = self.post(srv, 'p1', {'muted': bad})
            self.assertEqual((st, body), (400, {'ok': False, 'error': 'muted must be boolean'}), repr(bad))
        st, body = self.post(srv, 'p1', {})
        self.assertEqual(st, 400)
        self.assertEqual(g['CALLS'], [], 'модуль не бачить поганих аргументів')

    def test_a_bad_channel_is_400_before_the_module_is_called(self):
        """`check_set_args` стереже й канал (`comment_project` задачі довший за 200 знаків): 400, модуль не бачить."""
        g = self.fake_module_space()
        tasks_file = os.path.join(self.home, 'work', 'plain', 'tasks.json')
        with open(tasks_file, encoding='utf-8') as f:
            cfg = json.load(f)
        cfg['tasks']['p1']['comment_project'] = 'c' * 201
        mb._write(tasks_file, cfg)
        srv = self.srv()
        st, body = self.post(srv, 'p1', {'muted': True})
        self.assertEqual((st, body['ok']), (400, False))
        self.assertIn('channel', body['error'])
        self.assertEqual(g['CALLS'], [])

    def test_a_foreign_origin_is_403_before_everything(self):
        g = self.fake_module_space()
        srv = self.srv()
        for task in ('p1', 't1'):                          # і зі своїм модулем, і в ЛІГИ
            st, body = self.post(srv, task, {'muted': 'yes'}, 'https://evil.example')
            self.assertEqual((st, body), (403, {'ok': False, 'error': 'foreign origin'}), task)
        self.assertEqual(g['CALLS'], [])

    def test_a_non_bool_mute_set_answer_is_a_module_error(self):
        """Carry-over (a): відповідь `mute_set`, що не `bool` (в т.ч. `1` — `True == 1`), — `notify-error`, а не «успіх»."""
        g = self.fake_module_space()
        srv = self.srv()
        for answer in (1, 0, 'true', None, {'muted': True}, [True]):
            g['SET_ANSWER'] = answer
            st, body = self.post(srv, 'p1', {'muted': True})
            self.assertEqual((st, body['ok'], body['channel']), (502, False, 'dc/p1'), repr(answer))
            self.assertTrue(body['error'], repr(answer))

    def test_a_non_list_mute_state_answer_is_a_module_error(self):
        """Carry-over (a): відповідь `mute_state`, що не список, — `notify-error` (GET `{channel, error}`, POST 502 на
        другому кроці): «не знаю» ніколи не стає «нічого не замовчано»."""
        g = self.fake_module_space()
        srv = self.srv()
        for answer in ({}, {'project_id': 'dc/p1'}, 'x', None, 0):
            g['STATE'] = answer
            st, body = self.get(srv, 'p1')
            self.assertEqual((st, sorted(body)), (200, ['channel', 'error']), repr(answer))
            self.assertNotIn('muted', body)
            st, body = self.post(srv, 'p1', {'muted': True})
            self.assertEqual((st, body['ok']), (502, False), repr(answer))

    def test_notify_call_checks_the_set_arguments_before_the_module(self):
        """Пояс і шлейки: сам `notify_call` теж не пропускає поганий `muted`/канал/підпис до модуля (`ValueError`)."""
        g = self.fake_module_space()
        import spaces
        with spaces.request_space(self.ids['plain']):
            for args in (('dc/p1', 'yes', ''), ('dc/p1', 1, ''), ('', True, ''), ('dc/p1', True, 'x' * 201)):
                with self.assertRaises(ValueError, msg=repr(args)):
                    serve.notify_call('mute_set', *args)
        self.assertEqual(g['CALLS'], [])

    def test_a_broken_own_module_is_an_error_not_notify_off(self):
        """⛔ Свій модуль «на папері», що не працює, — НЕ «сповіщень нема»: GET/POST називають причину (як вкладка «Команда»)."""
        self.fake_module_space()
        srv = self.srv()
        with mock.patch.object(serve, 'notify_resolve', side_effect=dm.ModuleError('module-untrusted', message='not trusted')):
            st, body = self.get(srv, 'p1')
            self.assertEqual((st, body), (200, {'channel': 'dc/p1', 'error': 'not trusted'}))
            st, body = self.post(srv, 'p1', {'muted': True})
            self.assertEqual((st, body), (502, {'ok': False, 'channel': 'dc/p1', 'error': 'not trusted'}))


if __name__ == '__main__':
    unittest.main()
