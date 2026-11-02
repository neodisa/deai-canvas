"""Командний дашборд як роль `dashboard` (етап 4c-1). Тут — тести ядра; знімок 0.11.0 — еталон паритету.

Task 1: лише знімок `tests/fixtures/dashboard/before-4c1.json` (його знімає `tests/make_before_4c1.py` на коді БЕЗ змін,
і більше він не переписується) та перевірка його форми. Тести паритету наступних задач читають цей JSON, а не переганяють
генератор.
"""
import contextlib
import copy
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)
import dashboard  # noqa: E402
import deai_modules as dm  # noqa: E402
import install_config  # noqa: E402
import make_before_4c1 as mb  # noqa: E402  (шаблон світу знімка 0.11.0: простори, сервер у процесі, `scrub`/`strip`)
import sbconf  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import task_state  # noqa: E402
import test_modules as tm  # noqa: E402  (каркас `Env`: тимчасові HOME/DEAI_HOME, теку модулів-фікстур)
BEFORE = os.path.join(_HERE, 'fixtures', 'dashboard', 'before-4c1.json')
_REAL = None


def setUpModule():
    """Клас `DashboardRole` створює простори: справжній `~/.deai` стереже знімок на вході й звірка на виході
    (інваріант `test_serve.TestsCannotWriteLiveConfig`)."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)

#: Поля, що змінюються між прогонами: у знімку їх не має бути ніде (ні в тілах відповідей, ні в рядках синку).
VOLATILE = ('fetchedAt', 'rowsAt', 'changed', 'synced_at', 'updated_at', 'jira_synced_at')


def walk(obj, path=()):
    """Усі `(шлях, ключ, значення)` JSON-дерева (і вмісту списків)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path, k, v
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (i,))


class Before4c1Shape(unittest.TestCase):
    """Знімок поведінки 0.11.0 на місці й має ключі, на які спираються тести паритету Task 2–7."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['meta', 'supabase_choice', 'sync_gate', 'sync_push', 'team_read', 'upsert_http'])
        self.assertEqual(self.snap['meta']['version'], '0.11.0')
        self.assertEqual(self.snap['meta']['source_commit'], '6e0a0a5', 'знімок знято з замороженої копії v0.11.0')

    def test_team_read_cases(self):
        cases = self.snap['team_read']
        self.assertEqual(sorted(cases), ['array_with_junk', 'fake_three_rows', 'integrations_off', 'isolation_dc_no_overview',
                                         'isolation_dc_tasks_file', 'no_config', 'non_array_response', 'supabase_error',
                                         'supabase_request', 'team_snapshot_spaces_error'])
        for name, case in cases.items():
            if name == 'team_snapshot_spaces_error':
                continue                # `team_snapshot` напряму: не тіло маршруту
            with self.subTest(case=name):
                self.assertEqual(case['status'], 200)
                self.assertEqual(sorted(case['body']), ['current', 'mine', 'space', 'team'])
                self.assertEqual(sorted(case['volatile']), ['fetchedAt', 'rowsAt'])
        fake = cases['fake_three_rows']
        self.assertEqual(len(fake['body']['team']['rows']), 3, 'свій t1, чужий x9 і рядок без id')
        self.assertEqual(fake['urlopen_calls'], 0)
        req = cases['supabase_request']['urlopen_calls']
        self.assertEqual(len(req), 1)
        self.assertEqual(req[0]['timeout'], 3)
        self.assertEqual(req[0]['headers'], {'apikey': '<key>', 'authorization': 'Bearer <key>'})
        self.assertTrue(req[0]['url'].startswith('https://demo.supabase.example/rest/v1/overview_projects?'))
        self.assertIsNone(cases['integrations_off']['body']['team'])
        self.assertEqual(cases['integrations_off']['urlopen_calls'], 0)
        iso = 'вимкнено в ізольованому прогоні (DC_TASKS_FILE / DC_NO_OVERVIEW)'
        for name in ('isolation_dc_tasks_file', 'isolation_dc_no_overview'):
            self.assertEqual(cases[name]['body']['team']['error'], iso)
            self.assertEqual(cases[name]['body']['team']['rows'], [])
            self.assertEqual(cases[name]['urlopen_calls'], 0)
        self.assertEqual(cases['non_array_response']['body']['team']['error'], 'очікувався масив рядків overview_projects')
        self.assertEqual([r['id'] for r in cases['array_with_junk']['body']['team']['rows']], ['x9'])
        self.assertEqual(cases['team_snapshot_spaces_error'], {
            'cache_untouched': True, 'error': 'реєстр просторів не читається (spaces-unreadable)', 'rows': [],
            'rows_at': None, 'urlopen_calls': 0})

    def test_upsert_http_shape(self):
        for name, ignore in (('merge_duplicates', False), ('ignore_duplicates', True)):
            with self.subTest(case=name):
                case = self.snap['upsert_http'][name]
                self.assertEqual((case['ignore'], case['returned_status']), (ignore, 201))
                (call,) = case['calls']
                self.assertEqual((call['method'], call['timeout']), ('POST', 10))
                self.assertTrue(call['url'].endswith('/rest/v1/overview_projects?on_conflict=id'))
                self.assertEqual(call['headers'], {
                    'apikey': '<key>', 'authorization': 'Bearer <key>', 'content-type': 'application/json',
                    'prefer': f'resolution={name.replace("_", "-")},return=minimal'})
                self.assertEqual(call['body'], [case['input_row']])

    def test_supabase_choice_precedence(self):
        ch = self.snap['supabase_choice']
        self.assertEqual(ch['env_url_and_key'], {'url': 'env-url', 'key': 'env-key'})
        self.assertEqual(ch['env_url_and_service_key'], {'url': 'env-url', 'key': 'env-service-key'})
        self.assertEqual(ch['env_both_keys_key_wins']['key'], 'env-key')
        self.assertEqual(ch['env_url_only_falls_back_to_config'], {'url': 'config-url', 'key': 'config-key'})
        self.assertEqual(ch['no_env_uses_config'], {'url': 'config-url', 'key': 'config-key'})
        self.assertTrue(ch['neither']['error'].startswith('Supabase не налаштовано'))

    def test_sync_push_has_inputs_and_ordered_upserts(self):
        push = self.snap['sync_push']
        self.assertEqual(sorted(push), ['input', 'jira_keys_asked', 'stdout', 'upserts'])
        calls = push['upserts']
        self.assertEqual([c['row']['id'] for c in calls], ['reg1', 't1', 't2', 't3'], 'реєстр першим, далі локальні')
        self.assertEqual([c['ignore'] for c in calls], [True, False, False, False])
        self.assertEqual(sorted(push['input']), ['fake_temp_root', 'identity', 'iterations_json', 'jira_statuses',
                                                 'open_comment_counts', 'registry', 'tasks'])

    def test_sync_gate_cases(self):
        gate = self.snap['sync_gate']
        self.assertEqual(sorted(gate), ['dc_no_overview', 'dc_tasks_file_with_integrations_on', 'integrations_off',
                                        'integrations_on_with_config', 'no_config', 'notes'])
        cases = {k: v for k, v in gate.items() if k != 'notes'}
        self.assertEqual({k: v['popen_started'] for k, v in cases.items()},
                         {'dc_no_overview': False, 'dc_tasks_file_with_integrations_on': True, 'integrations_off': False,
                          'integrations_on_with_config': True, 'no_config': False})
        for name in ('integrations_on_with_config', 'dc_tasks_file_with_integrations_on'):
            started = gate[name]
            self.assertEqual(started['argv'], ['python3', 'bin/overview_push.py', 'sync'])
            self.assertEqual((started['log_relpath'], started['log_mode']), ('.claude/pipeline-feedback/overview-sync.log', 'a'))
            self.assertEqual(started['env_supabase_key_names'], ['SUPABASE_KEY', 'SUPABASE_URL'])
        self.assertEqual(gate['integrations_on_with_config']['env_other_key_names'], ['DEAI_HOME', 'HOME', 'PATH'])
        self.assertIn('DC_TASKS_FILE', gate['dc_tasks_file_with_integrations_on']['env_other_key_names'])
        self.assertTrue(any('--space' in n for n in gate['notes']) and any('sys.executable' in n for n in gate['notes']))

    def test_no_volatile_fields_and_no_absolute_paths_or_keys(self):
        """Мінливе вирізано, ключ Supabase замінено, абсолютних шляхів (теки машини) нема."""
        for path, key, _ in walk(self.snap):
            # вхідні дані фікстур (`input`, `input_rows`) — вигадані й сталі, мінливе стосується лише ВИХОДУ коду
            if key in VOLATILE and path[-1:] != ('volatile',) and not {'input', 'input_rows'} & set(path):
                self.fail(f'мінливе поле {key} у знімку: {path}')
        blob = json.dumps(self.snap, ensure_ascii=False)
        self.assertNotIn('pk-test-1', blob, 'значення ключа має бути <key>')
        self.assertIsNone(re.search(r'/(Users|home|private|var/folders|tmp)/', blob), 'абсолютний шлях у знімку')


# ------------------------------------------------------------------------------------------ Task 2: переїзд без зміни

URL = 'https://demo.supabase.co'
KEY = 'sb_publishable_test'
ENV_URL = 'https://abcdefghijkl.supabase.co'
ENV_KEY = 'sb_publishable_test_env'


class SupabaseConfigBothNames(unittest.TestCase):
    """`install_config.supabase_config` і `serve.supabase_config` (тонка обгортка) поводяться однаково: файл раніше за
    оточення, пара цілою, заготовки відкидаються. Кейси — ті самі, що в `test_legacy_comments.SupabaseConfigTest`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.legacy = os.path.join(self.tmp.name, 'tasks.json')
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in ('DC_TASKS_FILE', 'SUPABASE_URL', 'SUPABASE_KEY'):
            os.environ.pop(name, None)
        patch = mock.patch.object(spaces, 'legacy_tasks_file', return_value=self.legacy)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, obj, raw=None):
        with open(self.legacy, 'w', encoding='utf-8') as f:
            f.write(raw if raw is not None else json.dumps(obj))

    def each(self):
        for name, fn in (('install_config', install_config.supabase_config), ('serve', serve.supabase_config)):
            with self.subTest(getter=name):
                yield fn

    def test_file_wins_over_environment_and_trims_slash(self):
        self.write({'supabase_url': URL + '/', 'supabase_key': KEY})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        for fn in self.each():
            self.assertEqual(fn(), (URL, KEY))

    def test_falls_back_to_environment(self):
        self.write({'tasks': {}})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        for fn in self.each():
            self.assertEqual(fn(), (ENV_URL, ENV_KEY))

    def test_pair_comes_whole_from_one_source(self):
        self.write({'supabase_url': URL})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        for fn in self.each():
            self.assertEqual(fn(), (ENV_URL, ENV_KEY))
        del os.environ['SUPABASE_KEY']
        for fn in self.each():
            self.assertEqual(fn(), (None, None))

    def test_placeholders_and_bad_pairs_are_not_a_config(self):
        for url, key in (('http://demo.supabase.co', KEY), ('', KEY), (5, KEY), (URL, '   '), (URL, None),
                         ('https://<ref>.supabase.co', KEY), (URL, 'sb_publishable_…'), (URL, 'sb_publishable_ab cd'),
                         ('https://demo.supabase.co/path', KEY), ('https://user@demo.supabase.co', KEY)):
            self.write({'supabase_url': url, 'supabase_key': key})
            for fn in self.each():
                self.assertEqual(fn(), (None, None), (url, key))

    def test_port_is_allowed(self):
        self.write({'supabase_url': 'https://demo.supabase.co:8443/', 'supabase_key': KEY})
        for fn in self.each():
            self.assertEqual(fn(), ('https://demo.supabase.co:8443', KEY))

    def test_unreadable_or_deep_file_means_environment_or_nothing(self):
        for fn in self.each():
            self.assertEqual(fn(), (None, None))            # файла нема
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        for raw in ('{oops', '[]', 'null', '[' * 100000, '{"a":' * 100000):
            self.write(None, raw=raw)
            for fn in self.each():
                self.assertEqual(fn(), (ENV_URL, ENV_KEY), raw[:6])

    def test_serve_is_a_thin_wrapper_and_keeps_the_legacy_names(self):
        """Підміна `serve.supabase_config` (як у тестах) діє на викликачів у `serve`; `legacy_*` лишаються імпортованими."""
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        with mock.patch.object(install_config, 'supabase_config', return_value=('https://x.example', 'k')):
            self.assertEqual(serve.supabase_config(), ('https://x.example', 'k'))
        self.assertIs(serve.legacy_tasks_path, install_config.legacy_tasks_path)
        self.assertIs(serve.load_legacy_tasks, install_config.load_legacy_tasks)
        self.assertEqual(serve.load_legacy_tasks()['supabase_key'], KEY)


class DashboardIsServeFree(unittest.TestCase):
    """⛔ `app/dashboard.py` (і `install_config`) не тягнуть `serve`: їх читає CLI-пушер без сервера й мережі."""

    def test_importing_does_not_load_serve(self):
        code = ('import sys; sys.path.insert(0, %r); '
                'import importlib; importlib.import_module("dashboard"); importlib.import_module("install_config"); '
                'sys.exit(1 if "serve" in sys.modules else 0)') % os.path.join(ROOT, 'app')
        r = subprocess.run([sys.executable, '-B', '-I', '-c', code], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr or '`serve` потрапив у sys.modules після імпорту dashboard')


class CardsParity(unittest.TestCase):
    """На тих самих даних, що `sync_push` знімка 0.11.0, ядро дає ті самі картки (без часових полів)."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.push = json.load(f)['sync_push']

    @staticmethod
    def strip(row):
        return {k: v for k, v in row.items() if k not in VOLATILE}

    def test_cards_equal_the_recorded_upserts(self):
        inp = self.push['input']
        recorded = {c['row']['id']: (c['row'], c['ignore']) for c in self.push['upserts']}
        got = {}
        with tempfile.TemporaryDirectory() as tmp:
            for tid, it in inp['iterations_json'].items():
                os.makedirs(os.path.join(tmp, tid))
                with open(os.path.join(tmp, tid, 'iterations.json'), 'w', encoding='utf-8') as f:
                    json.dump(it, f)
            designer, designer_key = inp['identity']
            # крок 0: базові картки реєстру (фікстури реєстру відсіює `_drop_fixtures` — тут їх нема в записі)
            for pid, entry in inp['registry'].items():
                if pid == 'regfix':
                    continue
                card = dashboard.discover_card(pid, entry)
                self.assertFalse(dashboard.card_has_pii(card))
                got[pid] = (self.strip(card), True)
            for tid, task in inp['tasks'].items():
                if tid not in inp['iterations_json']:
                    continue                                   # `nova` (фікстура) і `t4` (теки нема на машині): не картки
                task = dict(task, dir=os.path.join(tmp, tid))
                st = task_state.task_state(task)
                st['open_comments'] = inp['open_comment_counts'].get(dashboard.comment_project_key(task, tid), 0)
                js = inp['jira_statuses'].get(task.get('jira') or '')
                if js and js.get('name'):
                    st['jira_status'] = js['name']
                    st['jira_status_cat'] = js.get('cat')
                card = dashboard.build_card(tid, task, st, designer, designer_key)
                if dashboard.card_has_pii(card):
                    continue                                   # `t5`: «Справа 1234567890»
                got[tid] = (self.strip(card), False)
        self.assertEqual(sorted(got), sorted(recorded))
        for tid, (row, ignore) in recorded.items():
            with self.subTest(card=tid):
                self.assertEqual(got[tid], (self.strip(row), ignore))

    def test_pii_card_is_recognised_and_absent_from_the_record(self):
        t5 = self.push['input']['tasks']['t5']
        self.assertTrue(dashboard.card_has_pii({'name': t5['title']}))
        self.assertNotIn('t5', [c['row']['id'] for c in self.push['upserts']])

    def test_map_status(self):
        ms = dashboard.map_status
        self.assertEqual(ms({'published': True, 'finalized': True}), 'done')
        self.assertEqual(ms({'published': True, 'open_comments': 2}), 'review')
        self.assertEqual(ms({'published': True}), 'pub')
        self.assertEqual(ms({}), 'work')

    def test_the_pusher_still_exports_the_old_names(self):
        import overview_push as ov
        for old, new in (('build_row', 'build_card'), ('row_has_pii', 'card_has_pii'), ('discover_row', 'discover_card'),
                         ('gitlab_web', 'gitlab_web'), ('to_iso', 'to_iso'), ('map_status', 'map_status'),
                         ('preview_source', 'preview_source'), ('comment_project_key', 'comment_project_key'),
                         ('_identity', '_identity'), ('_humanize', '_humanize'), ('_fixture_reason', '_fixture_reason')):
            self.assertIs(getattr(ov, old), getattr(dashboard, new), old)


#: Модуль ролі `dashboard`: `check` і обовʼязкові `rows`/`push`; `open_comments` — окремо (необовʼязкова).
DASH_FNS = ('def rows(ctx):\n    return []\n'
            'def push(ctx, cards, mode):\n    return {"ok": len(cards), "failed": {}}\n')
DASH_SERVER = tm.CHECK_ONLY + DASH_FNS
DASH_OPTIONAL = 'def open_comments(ctx):\n    return {"dc/t1": 2}\n'


class DashboardRole(tm.Env):
    """Роль `dashboard` у каркасі модулів (4c-1, Task 3): маніфест, постачальник, `capabilities`, коди помилок."""

    def setUp(self):
        super().setUp()
        # `Env.setUp` уже ізолює `DEAI_HOME`; присвоєння повторено тут явно, бо статичний охоронець
        # (`test_serve.TestsCannotWriteLiveConfig`) шукає його в тексті САМОГО файла, що пише простори.
        os.environ['DEAI_HOME'] = self.deai

    def error_of(self, mid):
        m = dm.catalog()[mid]
        self.assertEqual((m.status, m.error_code), ('error', 'bad-manifest'), f'{mid}: {m.error!r}')
        return m.error

    def test_the_role_is_called_and_no_longer_reserved(self):
        self.assertIn('dashboard', dm.ROLES_CALLED)
        self.assertNotIn('dashboard', dm.ROLES_RESERVED)
        self.assertEqual(dm.ROLE_FUNCTIONS['dashboard'], ('rows', 'push'))
        self.assertEqual(dm.ROLE_OPTIONAL_FUNCTIONS['dashboard'], ('open_comments',))
        self.assertIn('dashboard', dm.LEGACY_ROLES)

    def test_the_league_path_of_the_dashboard_is_not_a_fallback_after_an_error(self):
        """⛔ Зашитий шлях дашборда — спільний Supabase ЛІГИ (рядки команди, картки проєктів), тож, як `comments`, «через
        помилку» на нього не переходимо: `dashboard` НЕ в `LEGACY_ON_ERROR_ROLES`."""
        self.assertNotIn('dashboard', dm.LEGACY_ON_ERROR_ROLES)

    def test_a_dashboard_module_needs_rows_and_push(self):
        self.mk('dash-bare', roles=('dashboard',), server=tm.CHECK_ONLY)
        self.assertIn('rows', self.error_of('dash-bare'))
        for gap in ('rows', 'push'):
            self.mk(f'dash-no-{gap}', roles=('dashboard',), server=DASH_SERVER.replace(f'def {gap}(', f'def _not_{gap}('))
            self.assertIn(gap, self.error_of(f'dash-no-{gap}'), gap)
        self.mk('dash-ok', roles=('dashboard',), server=DASH_SERVER)
        self.assertEqual(dm.catalog()['dash-ok'].status, 'ok')

    def test_open_comments_is_optional_and_taken_when_present(self):
        self.mk('dash-plain', roles=('dashboard',), server=DASH_SERVER)
        self.mk('dash-full', roles=('dashboard',), server=DASH_SERVER + DASH_OPTIONAL)
        cat = dm.catalog()
        self.assertEqual((cat['dash-plain'].status, cat['dash-full'].status), ('ok', 'ok'))
        self.assertIsNone(cat['dash-plain'].fn('open_comments'))
        self.assertEqual(cat['dash-full'].fn('open_comments')({}), {'dc/t1': 2})

    def test_the_provider_of_an_integrations_space_without_a_module_is_legacy(self):
        ig = self.new_space('Integ', integrations=True)
        plain = self.new_space('Plain')
        self.assertEqual(dm.provider('dashboard', ig), 'legacy')
        self.assertEqual(dm.capabilities(ig)['dashboard'], 'legacy')
        self.assertIsNone(dm.provider('dashboard', plain))               # без інтеграцій і без модуля — нікого
        self.assertIsNone(dm.capabilities(plain)['dashboard'])

    def test_an_enabled_module_is_the_provider_in_both_kinds_of_space(self):
        self.mk('dash-ok', roles=('dashboard',), server=DASH_SERVER)
        ig = self.new_space('Integ', integrations=True)
        plain = self.new_space('Plain')
        for sp in (ig, plain):
            dm.write_module_state(sp, 'dash-ok', enabled=True)
            self.assertEqual(dm.provider('dashboard', sp).id, 'dash-ok')
            self.assertEqual(dm.capabilities(sp)['dashboard'], 'dash-ok')
        dm.write_module_state(ig, 'dash-ok', enabled=False)
        self.assertEqual(dm.capabilities(ig)['dashboard'], 'legacy')     # вимкнули: ЛІГА повертається до зашитого шляху
        dm.write_module_state(plain, 'dash-ok', enabled=False)
        self.assertIsNone(dm.capabilities(plain)['dashboard'])

    def test_a_module_error_is_none_never_legacy_and_sets_the_error(self):
        ig = self.new_space('Integ', integrations=True)
        with mock.patch.object(dm, '_provider_for', side_effect=dm.ModuleError('bad-manifest', message='x')):
            caps = dm.capabilities(ig)
        self.assertIsNone(caps['dashboard'])
        self.assertEqual(caps['error'], 'bad-manifest')
        self.assertEqual((caps['publish'], caps['vcs']), ('legacy', 'legacy'))     # а локальні ролі лишились зашитими
        dm.reset_caches()
        with mock.patch.object(dm, '_caps_key', side_effect=RuntimeError('bug')):      # запасний словник: теж не 'legacy'
            self.assertIsNone(dm.capabilities(ig)['dashboard'])

    def test_an_unreadable_space_json_in_an_integrations_space_never_yields_legacy(self):
        """⛔ Зашитий шлях `dashboard` — спільний Supabase ЛІГИ, тож, як `comments`, нечитабельний `space.json` у просторі з
        інтеграціями дає `space-json-unreadable`, а не `'legacy'` (ми не знаємо, чи людина ввімкнула там свій модуль)."""
        ig = self.new_space('Integ', integrations=True)
        with open(os.path.join(ig['path'], 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('dashboard', ig)
        self.assertEqual(cm.exception.code, 'space-json-unreadable')
        caps = dm.capabilities(ig)
        self.assertIsNone(caps['dashboard'])
        self.assertEqual(caps['error'], 'space-json-unreadable')
        self.assertEqual((caps['publish'], caps['vcs']), ('legacy', 'legacy'))     # локальні ролі шлях ЛІГИ не втрачають

    def test_the_error_codes_have_http_statuses(self):
        self.assertEqual(dm.STATUS['dashboard-unconfigured'], 409)
        self.assertEqual(dm.STATUS['dashboard-error'], 502)
        self.assertEqual(dm.ModuleError('dashboard-unconfigured').status, 409)
        self.assertEqual(dm.ModuleError('dashboard-error').status, 502)

    def test_the_builtin_dashboard_module_is_a_known_other_module(self):
        self.assertIn('supabase-dashboard', dm.KNOWN_OTHER_MODULES)
        self.assertEqual(set(dm.KNOWN_COMMENTS_MODULES) & set(dm.KNOWN_OTHER_MODULES), set())


class DropFixturesDefaultReason(unittest.TestCase):
    """`_drop_fixtures(entries, where)` без шва `reason` бере `_fixture_reason` цього модуля (Task 2 ревʼю)."""

    def test_the_default_reason_drops_a_fixture_entry_aloud(self):
        tmpdir = os.path.join(tempfile.gettempdir(), 'dc-fixture-x')
        entries = {'nova': {'title': 'Nova', 'gitlab': {'repo': os.path.join(tmpdir, 'nova.git')}},
                   'real': {'title': 'Real', 'gitlab': {'repo': 'git@git.example:org/demo-design.git'}}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kept = dashboard._drop_fixtures(entries, ' (тест)')
        self.assertEqual(list(kept), ['real'])
        self.assertIn('nova', buf.getvalue())
        self.assertIn('тимчасов', buf.getvalue())                      # причина названа вголос, а не мовчки


# ------------------------------------------------------------------------------------------ Task 5: читання «Команди»

class _Net:
    """Шов `_open` вбудованого `supabase-dashboard`: записує запити (URL, метод, заголовки з ключем → `<key>`, тайм-аут) і
    віддає `body` (або кидає `exc`). Той самий вигляд, що в записувача знімка 0.11.0 (`make_before_4c1.Recorder`)."""

    def __init__(self, body=b'[]', exc=None, key=mb.KEY):
        self.calls, self.body, self.exc, self.key = [], body, exc, key

    def __call__(self, req, timeout=None):
        headers = {k.lower(): str(v).replace(self.key, '<key>') for k, v in req.header_items()}
        self.calls.append({'url': req.full_url, 'method': req.get_method(), 'headers': headers, 'timeout': timeout})
        if self.exc:
            raise self.exc
        return sbconf.Resp(self.body)


class _Hits(list):
    """Влучання розтяжки; `allow_ports` — loopback-порти, які вона пропускає (сервер у процесі, його порт відомий після старту)."""

    def __init__(self):
        super().__init__()
        self.allow_ports = set()


def block_network(case):
    """Розтяжка (як `test_integrations_off.Tripwire`, але вужча): `urlopen` ядра й `socket.create_connection` — у запис і
    `OSError`; лише loopback на `hits.allow_ports` (сервер у процесі) проходить. Модуль ходить крізь власний opener, тож його
    справжній запит упав би саме на сокеті: тест, що забув підмінити `_open`, не вийде в мережу. Повертає список влучань."""
    hits = _Hits()
    real_cc = socket.create_connection

    def cc(address, *a, **kw):
        if address[0] in ('127.0.0.1', 'localhost') and address[1] in hits.allow_ports:
            return real_cc(address, *a, **kw)
        hits.append(('socket', '%s:%s' % address[:2]))
        raise OSError('tripwire')

    def uo(target, *a, **kw):
        hits.append(('urlopen', getattr(target, 'full_url', str(target))))
        raise OSError('tripwire')
    for owner, name, fn in ((socket, 'create_connection', cc), (urllib.request, 'urlopen', uo)):
        p = mock.patch.object(owner, name, fn)
        p.start()
        case.addCleanup(p.stop)
    return hits


class ReadParity(unittest.TestCase):
    """Диференційний: шлях ЛІГИ вкладки «Команда» через вбудований `supabase-dashboard` дає ТЕ САМЕ, що записав знімок 0.11.0
    (`before-4c1.json`, `team_read`): те саме тіло `/api/tasks-overview`, той самий URL і заголовки, той самий `team: null` без
    мережі. Мережа — шов `_open` модуля (не `urlopen`); сервер справжній, у процесі, на ефемерному порту.

    Свідомі відмінності (кожна названа в тесті, а не прихована):
      * `space.capabilities` має НОВИЙ ключ `dashboard` (знімок його не знає) — перевіряється окремо й вилучається з порівняння;
      * тайм-аут запиту 4 с (власний тайм-аут модуля), у знімку було 3 с;
      * тексти двох помилок (мережа впала, відповідь не масив) — тепер ТЕКСТ МОДУЛЯ, а не сирий виняток `urlopen`/`ValueError`."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)['team_read']
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix='read-parity-'))
        home = os.path.join(cls.tmp, 'home')
        os.makedirs(home)
        # `addClassCleanup`, а не `tearDownClass`: оточення й підміни мусять повернутись і тоді, коли `setUpClass` упав посередині
        # (інакше тимчасові `DEAI_HOME`/`HOME` лишились би в процесі й зламали б усі наступні файли набору).
        import shutil
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        cls.addClassCleanup(dm.reset_caches)
        cls.addClassCleanup(spaces.clear_request_space)
        env = mock.patch.dict(os.environ, {'HOME': home, 'DEAI_HOME': os.path.join(cls.tmp, 'deai')})
        env.start()
        cls.addClassCleanup(env.stop)
        for name in mb.CLEAN:
            os.environ.pop(name, None)
        legacy = mock.patch.object(spaces, 'legacy_tasks_file', return_value=os.path.join(cls.tmp, 'legacy', 'tasks.json'))
        legacy.start()
        cls.addClassCleanup(legacy.stop)
        dm.reset_caches()
        cls.ids = mb.setup_spaces(cls.tmp)
        cls.srv = mb.Server().__enter__()
        cls.addClassCleanup(cls.srv.__exit__, None, None, None)

    def setUp(self):
        spaces.clear_request_space()
        serve._TEAM_CACHE.clear()
        self.addCleanup(serve._TEAM_CACHE.clear)
        self.hits = block_network(self)
        self.hits.allow_ports.add(self.srv.port)
        self.net = _Net()
        sbconf.patch_dashboard_open(self, self.net)

    def overview(self, space='liga', env=None, cfg=(mb.URL, mb.KEY)):
        """`GET /api/tasks-overview?refresh=1` у просторі `space` → `{body, volatile, dashboard}` (форма запису знімка)."""
        spaces.switch_space(self.ids[space])
        with mock.patch.dict(os.environ, env or {}), mock.patch.object(serve, 'supabase_config', return_value=cfg):
            status, body = self.srv.get('/api/tasks-overview?refresh=1')
        self.assertEqual(status, 200, body)
        data = json.loads(mb.scrub(body, self.tmp))
        team = data.get('team')
        volatile = {k: (type(team.get(k)).__name__ if isinstance(team, dict) else None) for k in ('fetchedAt', 'rowsAt')}
        sp = data.get('space')
        sp.pop('id', None)
        sp.pop('path', None)
        cap = sp['capabilities'].pop('dashboard')          # новий ключ 4c-1: вилучаємо ДО копії, перевіряється окремо
        return {'status': status, 'body': mb.strip(data), 'volatile': volatile, 'dashboard': cap}

    def same_as_snapshot(self, got, name, dashboard_cap='legacy', error=None):
        """Тіло збігається із записаним. `error` — свідомо ІНШИЙ текст помилки (модуль замість сирого винятку)."""
        want = copy.deepcopy(self.snap[name])
        self.assertEqual(got['dashboard'], dashboard_cap, 'новий ключ capabilities.dashboard — рівно такий')
        if error is not None:
            self.assertEqual(got['body']['team']['error'], error)
            want['body']['team']['error'] = error
        self.assertEqual(got['body'], want['body'])
        self.assertEqual(got['volatile'], want['volatile'])

    def test_fake_seam_gives_the_recorded_body_and_never_touches_the_network(self):
        want = self.snap['fake_three_rows']
        fake = os.path.join(self.tmp, 'team-fake.json')
        with open(fake, 'w', encoding='utf-8') as f:
            json.dump(want['input_rows'], f)
        got = self.overview(env={'DC_TEAM_FAKE': fake})
        self.same_as_snapshot(got, 'fake_three_rows')
        self.assertEqual(self.net.calls, [])
        self.assertEqual(len(got['body']['team']['rows']), 3, 'шов віддає рядки як є, навіть без id (як у 0.11.0)')

    def test_real_request_has_the_recorded_url_and_headers(self):
        want = self.snap['supabase_request']
        self.net.body = json.dumps(want['input_rows']).encode('utf-8')
        got = self.overview()
        self.same_as_snapshot(got, 'supabase_request')
        (call,), (rec,) = self.net.calls, want['urlopen_calls']
        self.assertEqual((call['url'], call['method'], call['headers']), (rec['url'], rec['method'], rec['headers']))
        # свідома відмінність: тайм-аут модуля 4 с, у знімку 3 с
        self.assertEqual((rec['timeout'], call['timeout']), (3, 4))
        self.assertEqual(self.hits, [], 'жодного виходу назовні повз шов')

    def test_network_down_is_an_error_banner_with_the_modules_text(self):
        self.net.exc = OSError('мережі нема')
        got = self.overview()
        want = self.snap['supabase_error']
        self.assertEqual(want['body']['team']['error'], 'мережі нема')
        self.same_as_snapshot(got, 'supabase_error', error='Supabase недоступний (OSError)')
        self.assertEqual(len(self.net.calls), want['urlopen_calls'])

    def test_no_config_says_so_and_asks_nothing(self):
        got = self.overview(cfg=(None, None))
        self.same_as_snapshot(got, 'no_config')
        self.assertEqual(got['body']['team']['error'], 'Supabase не налаштовано')
        self.assertEqual(self.net.calls, [])

    def test_isolation_does_not_call_the_module(self):
        """⛔ `DC_TASKS_FILE`/`DC_NO_OVERVIEW` без шва: у ЛІГИ жодного виклику модуля, те саме пояснення, що в 0.11.0 — навіть
        коли конфіг валідний."""
        for name, env in (('isolation_dc_tasks_file', {'DC_TASKS_FILE': os.path.join(self.tmp, 'x-tasks.json')}),
                          ('isolation_dc_no_overview', {'DC_NO_OVERVIEW': '1'})):
            with self.subTest(case=name):
                serve._TEAM_CACHE.clear()
                self.net.calls.clear()
                got = self.overview(env=env)
                self.same_as_snapshot(got, name)
                self.assertEqual(self.net.calls, [])

    def test_a_non_array_answer_is_an_error_with_no_rows(self):
        self.net.body = b'{"message": "not an array"}'
        got = self.overview()
        self.assertEqual(self.snap['non_array_response']['body']['team']['error'], 'очікувався масив рядків overview_projects')
        self.same_as_snapshot(got, 'non_array_response',
                              error='Supabase повернув відповідь, що не є списком рядків дашборда')
        self.assertEqual(len(self.net.calls), 1)

    def test_junk_in_the_array_is_dropped_like_before(self):
        want = self.snap['array_with_junk']
        self.net.body = json.dumps([self.snap['fake_three_rows']['input_rows'][1], 5, 'x', None, ['y']]).encode('utf-8')
        self.same_as_snapshot(self.overview(), 'array_with_junk')
        self.assertEqual([r['id'] for r in want['body']['team']['rows']], ['x9'])

    def test_a_space_without_integrations_has_no_team_and_no_request(self):
        fake = os.path.join(self.tmp, 'team-fake.json')
        with open(fake, 'w', encoding='utf-8') as f:
            json.dump([{'id': 'x'}], f)
        got = self.overview(space='plain', env={'DC_TEAM_FAKE': fake})
        self.same_as_snapshot(got, 'integrations_off', dashboard_cap=None)
        self.assertIsNone(got['body']['team'])
        self.assertEqual(self.net.calls, [])

    def test_an_unreadable_registry_names_the_reason_and_leaves_the_cache_alone(self):
        want = self.snap['team_snapshot_spaces_error']
        boom = spaces.SpacesError('spaces-unreadable', '<registry>', 'тест')
        with spaces.request_space(self.ids['liga']), mock.patch.object(spaces, 'active_space', side_effect=boom), \
                mock.patch.object(serve, 'supabase_config', return_value=(mb.URL, mb.KEY)):
            rows, error, rows_at = serve.team_snapshot(refresh=True)
        self.assertEqual({'rows': rows, 'error': error, 'rows_at': rows_at, 'urlopen_calls': len(self.net.calls),
                          'cache_untouched': serve._TEAM_CACHE == {}}, want)

    def test_the_snapshot_itself_has_no_dashboard_capability(self):
        """Свідок знімка: ключа `dashboard` у записаному `capabilities` справді нема (він новий у 4c-1) — тож явне врахування
        в `same_as_snapshot` не маскує випадкового збігу."""
        for name in ('fake_three_rows', 'integrations_off'):
            self.assertNotIn('dashboard', self.snap[name]['body']['space']['capabilities'])


NORMAL_ROWS_SERVER = tm.CHECK_ONLY + (
    'import json, os\n'
    'def rows(ctx):\n'
    '    p = os.path.join(os.environ["DASH_TEST_DIR"], ctx["space"]["id"] + ".json")\n'
    '    try:\n'
    '        with open(p, encoding="utf-8") as f:\n'
    '            return json.load(f)\n'
    '    except OSError:\n'
    '        raise ctx["ModuleError"]("dashboard-error", message="down " + ctx["space"]["id"])\n'
    'def push(ctx, cards, mode):\n    return {"ok": 0, "failed": {}}\n')


class ReadPath(tm.Env):
    """Вкладка «Команда» звичайного простору й загальні закони читання: відбір рядків, кеш НА ПРОСТІР, збій модуля, тайм-аут,
    рішення «вкладка є/нема». Модуль-фікстура `dash` читає рядки з `$DASH_TEST_DIR/<id простору>.json`."""

    def setUp(self):
        super().setUp()
        os.environ['DEAI_HOME'] = self.deai          # як у `DashboardRole`: охоронець просторів шукає присвоєння в тексті файла
        # ⛔ НЕ `mock.patch.dict(os.environ)` на весь тест: його `stop` (після `Env.tearDown`) відновив би оточення ЗНІМКА, зробленого
        # вже після `Env.setUp` (з тимчасовими `DEAI_HOME`/`DC_TASKS_FILE`), — і вони просочились би в усі наступні файли тестів.
        os.environ['DASH_TEST_DIR'] = os.path.join(self.tmp, 'rows')
        self.addCleanup(os.environ.pop, 'DASH_TEST_DIR', None)
        os.makedirs(os.environ['DASH_TEST_DIR'])
        serve._TEAM_CACHE.clear()
        self.addCleanup(serve._TEAM_CACHE.clear)
        self.hits = block_network(self)
        self.mk('dash', roles=('dashboard',), server=NORMAL_ROWS_SERVER)

    def set_rows(self, sp, rows):
        with open(os.path.join(os.environ['DASH_TEST_DIR'], sp['id'] + '.json'), 'w', encoding='utf-8') as f:
            json.dump(rows, f)

    def drop_rows(self, sp):
        os.remove(os.path.join(os.environ['DASH_TEST_DIR'], sp['id'] + '.json'))

    def plain(self, name='Plain', module='dash'):
        sp = self.new_space(name)
        if module:
            dm.write_module_state(sp, module, enabled=True)
        return sp

    def snapshot(self, sp, **kw):
        with spaces.request_space(sp['id']):
            return serve.team_snapshot(**kw)

    def seed_tasks(self, sp):
        """`tasks.json` простору з однією задачею (без неї маршрут віддає «просторів нема» і `team: null`)."""
        d = os.path.join(sp['path'], 't1')
        mb._write(os.path.join(d, 'iterations.json'), {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00', 'published': False}],
                                                       'publish_url': None})
        mb._write(os.path.join(sp['path'], 'tasks.json'), {'design_work_root': sp['path'], 'current': 't1', 'tasks': {
            't1': {'title': 'Demo', 'dir': d, 'profile': 'tool', 'opened': '2026-11-01T10:00:00Z'}}})

    def http_overview(self, sp):
        self.seed_tasks(sp)
        spaces.switch_space(sp['id'])
        with mb.Server() as srv:
            self.hits.allow_ports.add(srv.port)             # loopback сервера цього тесту — єдиний дозволений вихід
            status, body = srv.get('/api/tasks-overview?refresh=1')
        self.assertEqual(status, 200, body)
        return json.loads(body)

    # ---- відбір рядків ----

    def test_rows_keep_only_team_keys_and_rows_with_an_id(self):
        sp = self.plain()
        self.set_rows(sp, [{'id': 'a', 'name': 'A', 'open_comments': 2, 'secret_col': 'S3CRET'},
                           {'id': 'b', 'name': 'B', 'designer': 'Alpha'}, {'name': 'no id'}, {'id': 7}, 'x', None])
        # ізоляція й шов ЛІГИ звичайного простору не стосуються: файл `DC_TEAM_FAKE` рядків не підмінює
        fake = os.path.join(self.tmp, 'fake.json')
        mb._write(fake, [{'id': 'from-fake'}])
        with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1', 'DC_TEAM_FAKE': fake}):
            rows, err, rows_at = self.snapshot(sp, refresh=True)
        self.assertIsNone(err)
        self.assertEqual([r['id'] for r in rows], ['a', 'b'])
        for r in rows:
            self.assertEqual(set(r), set(dashboard.TEAM_KEYS))
        self.assertEqual((rows[0]['open_comments'], rows[0]['name']), (2, 'A'))
        self.assertNotIn('S3CRET', json.dumps(rows))
        self.assertIsNotNone(rows_at)
        self.assertEqual(self.hits, [])

    def test_the_route_shows_those_rows_and_the_tab_only_with_a_provider(self):
        bare = self.plain('Bare', module=None)
        self.assertIsNone(self.http_overview(bare)['team'], 'нема постачальника — вкладки нема')
        sp = self.plain('Plain')
        self.set_rows(sp, [{'id': 'a', 'name': 'A', 'secret_col': 'S3CRET'}, {'name': 'no id'}])
        data = self.http_overview(sp)
        self.assertEqual([r['id'] for r in data['team']['rows']], ['a'])
        self.assertIsNone(data['team']['error'])
        self.assertNotIn('S3CRET', json.dumps(data))
        self.assertEqual(data['space']['capabilities']['dashboard'], 'dash')

    def test_a_provider_that_cannot_be_decided_shows_an_error_not_a_hidden_tab(self):
        """Зламаний власний модуль / нечитабельний `space.json` — `ModuleError` рішення ролі: вкладка ЛИШАЄТЬСЯ, плашка називає
        причину (а не `team: null`, що мовчки сховав би вкладку)."""
        ig = self.new_space('Integ', integrations=True)
        with open(self.space_json(ig), 'w', encoding='utf-8') as f:
            f.write('{broken')
        data = self.http_overview(ig)
        team = data['team']
        self.assertIsNotNone(team, 'вкладка не зникає')
        self.assertEqual(team['rows'], [])
        self.assertTrue(team['error'] and len(team['error']) <= 200)
        self.assertIsNone(team['rowsAt'])
        self.assertEqual([m['id'] for m in data['mine']], ['t1'], '«Мої» живуть')
        self.assertEqual(serve._TEAM_CACHE, {}, 'відмову рішення не кешуємо')

    # ---- збій модуля ----

    def test_a_module_failure_keeps_the_last_good_rows_and_says_why(self):
        sp = self.plain()
        self.set_rows(sp, [{'id': 'a', 'name': 'A'}])
        rows, err, at = self.snapshot(sp, now=1000.0)
        self.assertEqual(([r['id'] for r in rows], err, at), (['a'], None, 1000.0))
        self.drop_rows(sp)
        rows, err, at = self.snapshot(sp, now=1000.0 + serve.TEAM_TTL + 1)
        self.assertEqual([r['id'] for r in rows], ['a'], 'останні вдалі рядки')
        self.assertEqual(err, 'down ' + sp['id'])
        self.assertEqual(at, 1000.0, '`rowsAt` — час останнього успіху')
        self.assertLessEqual(len(err), 200)

    def test_a_slow_module_gets_the_cores_timeout_text(self):
        slow = self.mk('slow', roles=('dashboard',), server=tm.CHECK_ONLY + (
            'import time\ndef rows(ctx):\n    time.sleep(3)\n    return []\ndef push(ctx, cards, mode):\n    return {"ok": 0, "failed": {}}\n'))
        sp = self.plain('Slow', module='slow')
        with mock.patch.object(dashboard, 'READ_TIMEOUT', 0.3):
            t0 = time.monotonic()
            rows, err, at = self.snapshot(sp, refresh=True)
        self.assertLess(time.monotonic() - t0, 2.5, 'ядро не чекає на модуль довше за свій тайм-аут')
        self.assertEqual((rows, at), ([], None))
        self.assertIn('no answer', err)
        self.assertLessEqual(len(err), 200)

    def test_the_cores_timeout_is_longer_than_the_modules_own(self):
        """Ядро чекає ТРОХИ довше за модуль: модуль встигає відповісти СВОЇМ текстом, а не голим `check-timeout`."""
        import runpy
        mod = runpy.run_path(os.path.join(ROOT, 'app', 'modules', 'supabase-dashboard', 'server.py'))
        self.assertGreater(dashboard.READ_TIMEOUT, mod['READ_TIMEOUT_S'])
        self.assertEqual(dashboard.TEAM_KEYS, mod['TEAM_KEYS'], 'ключі рядка команди — одні й ті самі в ядрі й модулі')

    # ---- кеш на простір ----

    def test_the_cache_is_per_space_and_refresh_only_touches_its_own(self):
        a, b = self.plain('Alpha'), self.plain('Bravo')
        self.set_rows(a, [{'id': 'a1', 'name': 'A1'}])
        self.set_rows(b, [{'id': 'b1', 'name': 'B1'}])
        self.assertEqual([r['id'] for r in self.snapshot(a, now=1000.0)[0]], ['a1'])
        self.assertEqual([r['id'] for r in self.snapshot(b, now=1000.0)[0]], ['b1'])
        self.drop_rows(a)                                            # простір A «упав»
        self.set_rows(b, [{'id': 'b2', 'name': 'B2'}])
        rows_a, err_a, _ = self.snapshot(a, now=1001.0, refresh=True)
        self.assertEqual(([r['id'] for r in rows_a], bool(err_a)), (['a1'], True), 'A: останні вдалі рядки й помилка')
        rows_b, err_b, _ = self.snapshot(b, now=1002.0)               # у вікні TTL, без refresh
        self.assertEqual(([r['id'] for r in rows_b], err_b), (['b1'], None), 'збій A не став станом B; refresh A не зачепив B')
        rows_b, _, _ = self.snapshot(b, now=1002.0, refresh=True)
        self.assertEqual([r['id'] for r in rows_b], ['b2'])
        self.assertEqual(sorted(serve._TEAM_CACHE), sorted([a['id'], b['id']]))

    def test_a_new_provider_does_not_inherit_the_old_providers_rows(self):
        sp = self.plain()
        self.set_rows(sp, [{'id': 'old', 'name': 'Old'}])
        self.assertEqual([r['id'] for r in self.snapshot(sp, now=1000.0)[0]], ['old'])
        self.mk('dash2', roles=('dashboard',), server=tm.CHECK_ONLY + (
            'def rows(ctx):\n    raise ctx["ModuleError"]("dashboard-error", message="new is down")\n'
            'def push(ctx, cards, mode):\n    return {"ok": 0, "failed": {}}\n'))
        dm.write_module_state(sp, 'dash', enabled=False)
        dm.write_module_state(sp, 'dash2', enabled=True)
        rows, err, at = self.snapshot(sp, now=1001.0)                 # у вікні TTL, але постачальник інший
        self.assertEqual((rows, err, at), ([], 'new is down', None))


class DashboardHelpers(unittest.TestCase):
    """`dashboard.legacy_ctx` і `dashboard.normalize_rows` — чисті функції ядра."""

    def test_legacy_ctx_is_built_from_the_install_config_not_from_the_frame(self):
        ctx = dashboard.legacy_ctx('https://demo.supabase.example', 'sk-test-1', 'liga')
        self.assertEqual(ctx['settings'], {'url': 'https://demo.supabase.example', 'table': 'overview_projects'})
        self.assertEqual(ctx['secrets'], {'key': 'sk-test-1'})
        self.assertEqual(ctx['space'], {'id': 'liga', 'path': ''})
        self.assertIs(ctx['legacy'], True, 'модуль не відмовляє публічному ключу ЛІГИ')
        self.assertIs(ctx['ModuleError'], dm.ModuleError)
        self.assertEqual(dashboard.legacy_ctx('https://x.example', 'k')['space']['id'], '')

    def test_legacy_ctx_without_a_config_is_dashboard_unconfigured(self):
        with self.assertRaises(dm.ModuleError) as cm:
            dashboard.legacy_ctx(None, None)
        self.assertEqual((cm.exception.code, cm.exception.status, cm.exception.message), ('dashboard-unconfigured', 409,
                                                                                         'Supabase не налаштовано'))

    def test_normalize_rows(self):
        n = dashboard.normalize_rows
        out = n([{'id': 'a', 'name': 'A', 'secret_col': 1}, {'name': 'x'}, {'id': 3}, 'r', None, {'id': 'b'}])
        self.assertEqual([r['id'] for r in out], ['a', 'b'])
        self.assertTrue(all(set(r) == set(dashboard.TEAM_KEYS) for r in out))
        self.assertEqual(out[1]['name'], None)
        self.assertEqual(len(n([{'id': f'r{i}'} for i in range(dashboard.MAX_ROWS + 50)])), dashboard.MAX_ROWS)
        for bad in ({'id': 'a'}, 'x', None, 5):
            with self.assertRaises(ValueError):
                n(bad)


if __name__ == '__main__':
    unittest.main()
