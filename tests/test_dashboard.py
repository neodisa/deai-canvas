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
import shutil
import tempfile
import threading
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
import overview_push as ov  # noqa: E402  (тонкий CLI синку: Task 6)
import registry  # noqa: E402
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
                         ('_identity', '_identity'), ('_humanize', '_humanize')):
            self.assertIs(getattr(ov, old), getattr(dashboard, new), old)
        # Task 6: бар'єр фікстур живе в `dashboard` (кроки синку переїхали); на пушері НЕ лишено імені, яке підміна в тестах
        # мовчки не слухалась би (колись `ov._fixture_reason` був швом бар'єра)
        for gone in ('_fixture_reason', '_drop_fixtures', '_supabase', 'upsert_project', 'open_comment_counts'):
            self.assertFalse(hasattr(ov, gone), gone)


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
        self.assertIn('dashboard', dm.IMPLICIT_ROLES)

    def test_the_league_path_of_the_dashboard_is_not_a_fallback_after_an_error(self):
        """⛔ Зашитий шлях дашборда — спільний Supabase ЛІГИ (рядки команди, картки проєктів), тож, як `comments`, «через
        помилку» на нього не переходимо: `dashboard` НЕ в `IMPLICIT_ON_ERROR_ROLES`."""
        self.assertNotIn('dashboard', dm.IMPLICIT_ON_ERROR_ROLES)

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
      * тексти двох помилок (мережа впала, відповідь не масив) — тепер ТЕКСТ МОДУЛЯ, а не сирий виняток `urlopen`/`ValueError`;
      * на шляху модуля/справжньої мережі обʼєкти-рядки БЕЗ рядкового `id` тепер відкидаються (`normalize_rows`; 0.11.0 їх
        лишав), а шов `DC_TEAM_FAKE` (файл замість бази) їх, як і раніше, пропускає як є."""

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
        sp['capabilities'].pop('tracker')                  # новий ключ 4c-2 (знімок 0.11.0 його не знає): його перевіряє test_tracker
        sp['capabilities'].pop('notify')                   # новий ключ 4c-3 (знімок 0.11.0 його не знає): його перевіряє test_notify
        data.pop('tracker')                                # новий ключ тіла 4c-2 (знімок 0.11.0 його не знає): його перевіряє test_tasks_overview
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



# ------------------------------------------------------------------------------------------ Task 6: запис — синк

class _FakeDash:
    """Модуль ролі `dashboard` для тестів ядра: `deai_modules.call` бачить `status`, `id` і `fn(імʼя)`. `push` пише всі виклики
    в `sent` як `(mode, картка)`; `fns` додають чи підміняють функції (`open_comments`, `push` з відмовами)."""
    id = 'fake-dashboard'
    status = 'ok'

    def __init__(self, **fns):
        self.sent, self.calls = [], []
        self._fns = {'push': self._push, **fns}

    def _push(self, ctx, cards, mode):
        self.calls.append((mode, [c['id'] for c in cards]))
        self.sent.extend((mode, c) for c in cards)
        return {'ok': len(cards), 'failed': {}}

    def fn(self, name):
        return self._fns.get(name)


class SyncParity(unittest.TestCase):
    """Диференційний `sync_push`: `dashboard.sync` для ЛІГИ на ТИХ САМИХ заглушках, що знімок 0.11.0 (реєстр, коментарі, Jira —
    колбеки; сам запис — модуль, що пише `push`), віддає ті самі картки (з тими ж `mode`: `insert` для реєстру, `merge` для
    задач) і ті самі підсумкові рядки лога. Свідомих відмінностей запису тут дві: картки йдуть ПАКЕТАМИ (по одному виклику
    `push` на режим, а не по одному upsert на картку) і збій `push` називається вголос (раніше крок реєстру мовчав)."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.push = json.load(f)['sync_push']

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sync-parity-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(registry, '_temp_roots', return_value=[mb.FAKE_TMP])   # як у генераторі знімка: фікстури — лише FAKE_TMP
        p.start()
        self.addCleanup(p.stop)

    def world(self):
        """`(cfg, registry)` знімка: теки задач у тимчасовій теці, `iterations.json` — з входу знімка."""
        inp = self.push['input']
        for tid, it in inp['iterations_json'].items():
            mb._write(os.path.join(self.tmp, tid, 'iterations.json'), it)
        tasks = {}
        for tid, task in inp['tasks'].items():
            task = dict(task)
            if 'dir' in task:
                task['dir'] = os.path.join(self.tmp, task['dir'].replace('<dir>/', ''))
            tasks[tid] = task
        return {'tasks': tasks}, inp['registry']

    def run_sync(self, module, plain=False, **kw):
        """Один прохід на світі знімка → `(лог-рядки, ключі Jira, підсумок)`. `plain` — без колбеків реєстру й Jira."""
        cfg, reg = self.world()
        asked, lines = [], []

        def jira(keys):
            asked.append(list(keys))
            return self.push['input']['jira_statuses']
        summary = dashboard.sync(cfg, module, {'secrets': {}}, discover=None if plain else (lambda: dict(reg)),
                                 statuses=None if plain else jira, identity=tuple(self.push['input']['identity']),
                                 log=lines.append, **kw)
        return lines, asked, summary

    @staticmethod
    def strip(card):
        return {k: v for k, v in card.items() if k not in VOLATILE}

    def test_the_same_cards_in_the_same_modes_as_the_0_11_0_upserts(self):
        mod = _FakeDash(open_comments=lambda ctx: self.push['input']['open_comment_counts'])
        self.run_sync(mod)
        recorded = [('insert' if c['ignore'] else 'merge', c['row']) for c in self.push['upserts']]
        self.assertEqual([(m, self.strip(c)) for m, c in mod.sent], recorded)
        for (_, card), rec in zip(mod.sent, self.push['upserts']):
            self.assertEqual(sorted(k for k in VOLATILE if k in card), rec['volatile_present'], card['id'])
        # пакетами: один виклик на режим (реєстр — `insert`, задачі — `merge`), а не по картці
        self.assertEqual(mod.calls, [('insert', ['reg1']), ('merge', ['t1', 't2', 't3'])])

    def test_the_log_has_the_same_summary_lines(self):
        mod = _FakeDash(open_comments=lambda ctx: self.push['input']['open_comment_counts'])
        lines, asked, summary = self.run_sync(mod)
        self.assertEqual(lines, self.push['stdout'])
        self.assertEqual(sorted(k for k in asked[0] if k), sorted(k for k in self.push['jira_keys_asked'][0] if k),
                         'Jira питають про ключі ВСІХ задач файла (навіть без теки)')
        self.assertEqual((summary['discovered'], summary['synced'], summary['skipped'], summary['failed']), (1, 3, ['t4'], {}))

    def test_open_comments_move_the_status_to_review_only_when_the_module_has_them(self):
        with_fn = _FakeDash(open_comments=lambda ctx: {'dc/t1': 2})
        self.run_sync(with_fn, plain=True)
        self.assertEqual({c['id']: c['status'] for _, c in with_fn.sent}['t1'], 'review')
        without = _FakeDash()                                           # необовʼязкової функції нема → `{}`, `call` її не кличе
        self.run_sync(without, plain=True)
        self.assertEqual({c['id']: c['status'] for _, c in without.sent}['t1'], 'work')
        broken = _FakeDash(open_comments=lambda ctx: 1 / 0)             # збій → `{}`, а не падіння синку
        self.run_sync(broken, plain=True)
        self.assertEqual({c['id']: c['status'] for _, c in broken.sent}['t1'], 'work')
        junk = _FakeDash(open_comments=lambda ctx: ['dc/t1'])           # не словник → `{}`
        self.run_sync(junk, plain=True)
        self.assertEqual({c['id']: c['status'] for _, c in junk.sent}['t1'], 'work')

    def test_an_ordinary_space_has_no_registry_and_no_jira(self):
        """Колбеків нема (`discover`/`statuses` = `None`): ні `insert`, ні Jira-статусів на картках; лише `merge` задач."""
        mod = _FakeDash(open_comments=lambda ctx: {'dc/t1': 1})
        lines, asked, _ = self.run_sync(mod, plain=True)
        self.assertEqual(asked, [])
        self.assertEqual({m for m, _ in mod.sent}, {'merge'})
        self.assertEqual(mod.calls, [('merge', ['t1', 't2', 't3'])])
        self.assertTrue(all('jira_status' not in c for _, c in mod.sent))
        self.assertFalse(any('з реєстру оброблено' in ln for ln in lines))

    def test_failed_cards_are_named_aloud(self):
        def push(ctx, cards, mode):
            return {'ok': len(cards) - 1, 'failed': {'t2': 'Supabase недоступний (URLError)'}} if mode == 'merge' else \
                {'ok': 0, 'failed': {'reg1': 'відмова вставки'}}
        lines, _, summary = self.run_sync(_FakeDash(push=push))
        self.assertIn('⚠ overview: не вдалося синхронізувати «t2»: Supabase недоступний (URLError)', lines)
        self.assertIn('⚠ overview: не вдалося додати з реєстру «reg1»: відмова вставки', lines)
        self.assertIn('✅ overview: синхронізовано 2 проєктів', lines)
        self.assertEqual(summary['failed'], {'t2': 'Supabase недоступний (URLError)'})

    def test_a_dead_service_names_every_card_and_does_not_raise(self):
        def push(ctx, cards, mode):
            raise dm.ModuleError('dashboard-error', message='Supabase недоступний (timeout)')
        lines, _, summary = self.run_sync(_FakeDash(push=push))
        self.assertEqual(sorted(summary['failed']), ['t1', 't2', 't3'])
        self.assertIn('⚠ overview: не вдалося синхронізувати «t1»: Supabase недоступний (timeout)', lines)
        self.assertIn('✅ overview: синхронізовано 0 проєктів', lines)

    def test_an_answer_off_the_contract_is_a_failure_not_a_crash(self):
        _, _, summary = self.run_sync(_FakeDash(push=lambda ctx, cards, mode: 'ok'))
        self.assertEqual(sorted(summary['failed']), ['t1', 't2', 't3'])

    def test_nothing_is_pushed_when_there_are_no_cards(self):
        """Порожній список — без виклику `push` (модуль не будує порожній запит)."""
        mod = _FakeDash()
        dashboard.sync({'tasks': {}}, mod, {'secrets': {}}, identity=('Alpha', 'alpha@example.com'), log=lambda m: None)
        self.assertEqual(mod.calls, [])

    def test_the_real_module_gets_the_same_cards_over_http(self):
        """Наскрізно ЛІГА: справжній вбудований `supabase-dashboard` із `legacy_ctx` (шов `_open` — записувач): URL таблиці
        `overview_projects`, `Prefer` на режим, і ті самі картки, що у знімку, а лічильники коментарів — з `comments`."""
        bodies = []

        def net(req, timeout=None):
            body = json.loads(req.data.decode('utf-8')) if req.data else None
            bodies.append((req.get_method(), req.full_url, req.headers.get('Prefer'), body))
            return sbconf.Resp(json.dumps([{'project_id': 'dc/t1'}]).encode('utf-8') if '/comments?' in req.full_url else b'')
        hits = block_network(self)
        sbconf.patch_dashboard_open(self, net)
        cfg, reg = self.world()
        ctx = dashboard.legacy_ctx(mb.URL, mb.KEY, 'liga')
        dashboard.sync(cfg, dashboard.legacy_module(), ctx, discover=lambda: dict(reg),
                       statuses=lambda keys: self.push['input']['jira_statuses'],
                       identity=tuple(self.push['input']['identity']), log=lambda m: None)
        self.assertEqual(hits, [], 'мережа тільки через шов модуля')
        urls = {u for _, u, _, _ in bodies}
        self.assertEqual(urls, {f'{mb.URL}/rest/v1/overview_projects?on_conflict=id',
                                f'{mb.URL}/rest/v1/comments?status=eq.open&select=project_id'})
        writes = [(pref, b) for m, _, pref, b in bodies if m == 'POST']
        insert = [c for pref, b in writes if pref == 'resolution=ignore-duplicates,return=minimal' for c in b]
        merge = [c for pref, b in writes if pref == 'resolution=merge-duplicates,return=minimal' for c in b]
        recorded = {c['row']['id']: (c['ignore'], c['row']) for c in self.push['upserts']}
        self.assertEqual(sorted(c['id'] for c in insert), ['reg1'])
        self.assertEqual(sorted(c['id'] for c in merge), ['t1', 't2', 't3'])
        for card in insert + merge:
            self.assertEqual(self.strip(card), self.strip(recorded[card['id']][1]), card['id'])
        # ⛔ «None не шлемо» дійшло до дроту: жодного `null` у тілах
        self.assertNotIn(None, [v for c in insert + merge for v in c.values()])


class CliShape(unittest.TestCase):
    """`bin/overview_push.py`: тонкий CLI. Без сервера, без реєстру машини (`spaces.load_registry` підмінено), без мережі."""

    REG = {'current': 'liga', 'spaces': [{'id': 'liga', 'path': '', 'legacy': True, 'integrations': True},
                                         {'id': 'p', 'path': '/nowhere/p', 'legacy': False, 'integrations': False},
                                         # справжній простір «Legacy»: `SPACE_ID_RE` пропускає id `legacy`, зарезервованих нема
                                         {'id': 'legacy', 'path': '/nowhere/legacy', 'legacy': False, 'integrations': False}]}

    def setUp(self):
        self.picked, self.synced, self.status_calls, self.status_cb = [], [], [], lambda keys: {}

        def target(sp):
            self.picked.append(sp['id'])
            return _FakeDash(), {'secrets': {}}, sp.get('legacy', False)
        for patcher in (mock.patch.object(spaces, 'load_registry', return_value=self.REG),
                        mock.patch.object(ov, '_target', target),
                        mock.patch.object(ov, '_tasks_of', lambda sp: {'tasks': {}}),
                        # 4c-2: статуси — від постачальника `tracker` (справжній читав би конфіг установки й модулі машини)
                        mock.patch.object(ov, '_statuses', self.statuses_for),
                        mock.patch.object(dashboard, 'sync', lambda *a, **kw: self.synced.append(kw)),
                        mock.patch.object(ov, 'discover_projects', lambda cfg: {})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def statuses_for(self, sp, log=print):
        self.status_calls.append(sp['id'])
        return self.status_cb

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ov.main(list(argv))
        return code, out.getvalue()

    def test_sync_without_space_is_the_league_space(self):
        self.assertEqual(self.main('sync')[0], 0)
        self.assertEqual(self.main()[0], 0, 'без підкоманди — теж синк ЛІГИ: так кликав зовнішній планувальник')
        self.assertEqual(self.picked, ['liga', 'liga'])

    def test_sync_with_space_is_that_space(self):
        self.assertEqual(self.main('sync', '--space', 'p')[0], 0)
        self.assertEqual(self.picked, ['p'])
        # звичайний простір: колбека реєстру нема; статуси — від постачальника `tracker` (тут заглушка), а не прапорця ЛІГИ
        self.assertIsNone(self.synced[0]['discover'])
        self.assertIs(self.synced[0]['statuses'], self.status_cb)
        self.assertEqual(self.status_calls, ['p'])

    def test_the_league_space_gets_the_registry_and_status_callbacks(self):
        self.main('sync')
        self.assertIsNotNone(self.synced[0]['discover'])
        self.assertIs(self.synced[0]['statuses'], self.status_cb)
        self.assertEqual(self.status_calls, ['liga'])

    def test_the_legacy_flag_is_the_league_space_and_the_id_legacy_is_a_real_space(self):
        """⛔ Псевдоніма-id нема: `--space legacy` — це справжній простір з id `legacy`, а ЛІГА — окремий прапорець `--legacy`
        (його не може мати жоден id). Інакше простір «Legacy» збігся б із ЛІГОЮ."""
        self.assertEqual(self.main('sync', '--legacy')[0], 0)
        self.assertEqual(self.main('sync', '--space', 'legacy')[0], 0)
        self.assertEqual(self.picked, ['liga', 'legacy'])

    def test_space_and_legacy_flags_exclude_each_other(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            ov.main(['sync', '--space', 'p', '--legacy'])
        self.assertEqual(cm.exception.code, 2)

    def test_an_unknown_space_is_exit_code_2_and_a_text(self):
        code, out = self.main('sync', '--space', 'nope')
        self.assertEqual(code, 2)
        self.assertIn('невідомий простір «nope»', out)
        self.assertEqual(self.picked, [], 'до постачальника не доходить')

    def test_discover_is_only_for_the_league(self):
        self.assertEqual(self.main('discover')[0], 0)                  # простір ЛІГА (`legacy: True`)
        with mock.patch.object(ov, '_space', return_value=self.REG['spaces'][1]):
            code, out = self.main('discover')
        self.assertEqual(code, 2)
        self.assertIn('лише для простору ЛІГА', out)

    def test_a_bad_command_is_exit_code_2(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            ov.main(['bogus'])
        self.assertEqual(cm.exception.code, 2)

    def test_the_pusher_does_not_import_the_server(self):
        """⛔ `from serve import …` зникло: його тягнув `_supabase()`, а сервер — це мережа й увесь стан."""
        with open(os.path.join(ROOT, 'bin', 'overview_push.py'), encoding='utf-8') as f:
            text = f.read()
        self.assertIsNone(re.search(r'^\s*(?:from\s+serve\b|import\s+serve\b)', text, re.M))
        self.assertNotIn('_serve()', text)


class CliTarget(unittest.TestCase):
    """Конфіг ЛІГИ для CLI: файл установки раніше за оточення; `SUPABASE_SERVICE_KEY` — лише запасний ключ ЛІГИ, і лише з
    `SUPABASE_URL` (спека §5). `provider` і модуль — заглушки: перевіряється саме побудова `ctx`."""

    SP = {'id': 'liga', 'path': '', 'legacy': True, 'integrations': True}

    def setUp(self):
        for patcher in (mock.patch.object(dm, 'provider', return_value='legacy'),
                        mock.patch.object(dashboard, 'legacy_module', return_value=_FakeDash()),
                        mock.patch.dict(os.environ, {}), mock.patch.object(spaces, 'legacy_tasks_file', return_value='/nowhere/tasks.json')):
            patcher.start()
            self.addCleanup(patcher.stop)
        for k in ('SUPABASE_URL', 'SUPABASE_KEY', 'SUPABASE_SERVICE_KEY', 'DC_TASKS_FILE'):
            os.environ.pop(k, None)

    def ctx(self):
        module, ctx, legacy = ov._target(self.SP)
        self.assertTrue(legacy)
        return ctx

    def test_the_installation_file_wins_over_the_service_key(self):
        os.environ.update(SUPABASE_URL='https://env.supabase.example', SUPABASE_SERVICE_KEY='sk-test-service')
        with mock.patch.object(install_config, 'load_legacy_tasks',
                               return_value={'supabase_url': 'https://demo.supabase.example', 'supabase_key': 'sk-test-file'}):
            ctx = self.ctx()
        self.assertEqual((ctx['settings']['url'], ctx['secrets']['key']), ('https://demo.supabase.example', 'sk-test-file'))

    def test_no_file_the_service_key_pair_from_the_environment(self):
        os.environ.update(SUPABASE_URL='https://env.supabase.example', SUPABASE_SERVICE_KEY='sk-test-service')
        with mock.patch.object(install_config, 'load_legacy_tasks', side_effect=FileNotFoundError):
            ctx = self.ctx()
        self.assertEqual((ctx['settings']['url'], ctx['secrets']['key']), ('https://env.supabase.example', 'sk-test-service'))
        self.assertEqual(ctx['space']['id'], 'liga')

    def test_the_service_key_alone_is_not_a_config(self):
        os.environ.update(SUPABASE_SERVICE_KEY='sk-test-service')
        with mock.patch.object(install_config, 'load_legacy_tasks', side_effect=FileNotFoundError), \
                self.assertRaises(ov.CliError) as cm:
            ov._target(self.SP)
        self.assertIn('не налаштовано', cm.exception.args[0])
        self.assertNotIn('sk-test-service', cm.exception.args[0])

    def test_a_malformed_service_pair_is_not_a_config_either(self):
        os.environ.update(SUPABASE_URL='http://insecure.example', SUPABASE_SERVICE_KEY='sk-test-service')
        with mock.patch.object(install_config, 'load_legacy_tasks', side_effect=FileNotFoundError), \
                self.assertRaises(ov.CliError):
            ov._target(self.SP)

    def test_an_ordinary_provider_gets_the_module_ctx_and_no_callbacks(self):
        mod = _FakeDash()
        with mock.patch.object(dm, 'provider', return_value=mod), \
                mock.patch.object(dm, 'module_ctx', return_value={'settings': {}, 'secrets': {}}) as mctx:
            module, ctx, legacy = ov._target({'id': 'p', 'path': '/x', 'legacy': False, 'integrations': False})
        self.assertEqual((module, legacy), (mod, False))
        mctx.assert_called_once()

    def test_no_provider_is_no_module(self):
        with mock.patch.object(dm, 'provider', return_value=None):
            self.assertEqual(ov._target(self.SP), (None, None, False))


#: Серверний модуль-фікстура ролі `dashboard` без жодного ефекту (нам потрібен лише факт постачальника).
GATE_SERVER = tm.CHECK_ONLY + DASH_FNS


class _Popen:
    """Заглушка `subprocess.Popen` для гейтів і одиночного запуску: пише `(argv, kwargs, шлях лога, режим)`; `poll()` — `None`,
    поки `finish()` не викликано (дитина «жива»), `wait()` чекає на це. Жодного справжнього процесу. `hold_next` — наступна
    дитина тримає `wait()` ще й після `finish()`, поки не відкрито `wait_gate` (щоб відтворити гонку спостерігача)."""

    def __init__(self):
        self.started, self.children = [], []
        self.lock = threading.Lock()
        self.hold_next = False

    def __call__(self, argv, **kw):
        out = kw.get('stdout')
        with self.lock:
            self.started.append({'argv': list(argv), 'kwargs': sorted(kw), 'log': getattr(out, 'name', None),
                                 'mode': getattr(out, 'mode', None), 'stderr': kw.get('stderr'), 'stdout_closed_at_start': out.closed})
            child = _Child(hold=self.hold_next)
            self.hold_next = False
            self.children.append(child)
        return child

    def finish_all(self):
        with self.lock:
            kids = list(self.children)
        for k in kids:
            k.wait_gate.set()
            k.finish()


class _Child:
    def __init__(self, hold=False):
        self.done = threading.Event()
        self.wait_gate = threading.Event()
        self.terminated = False
        if not hold:
            self.wait_gate.set()

    def finish(self):
        self.done.set()

    def terminate(self):
        self.terminated = True
        self.finish()

    def kill(self):
        self.terminate()

    def poll(self):
        return 0 if self.done.is_set() else None

    def wait(self, timeout=None):
        self.done.wait(15)
        self.wait_gate.wait(15)
        return 0


def wait_until(test, cond, what, seconds=5.0):
    """Опитування умови з тайм-аутом (потік-спостерігач — фоновий): без `sleep` навмання."""
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return
        time.sleep(0.005)
    test.fail(f'не діждались: {what}')


class _SyncEnv(tm.Env):
    """Світ запуску синку: тимчасові `HOME`/`DEAI_HOME`, простір ЛІГА (інтеграції, постачальник `'legacy'`), звичайний простір,
    що має модуль дашборда, і звичайний без нього. `Popen` — заглушка; лог ЛІГИ — шов `serve.OVERVIEW_LOG` у тимчасовій теці
    (ТА `HOME` тимчасова: навіть якщо шов зламати, справжній `~/.claude/pipeline-feedback/` не торкнеться)."""

    def setUp(self):
        super().setUp()
        # `DC_TASKS_FILE`/`SUPABASE_*` повертає сам `tm.Env.tearDown`; а `DC_NO_OVERVIEW`/`DC_TEAM_FAKE` (їх ставлять сусідні набори)
        # — тут, інакше зняті навічно
        for name in ('DC_NO_OVERVIEW', 'DC_TEAM_FAKE'):
            if name in os.environ:
                self.addCleanup(os.environ.__setitem__, name, os.environ[name])
        for name in ('DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TASKS_FILE', 'SUPABASE_URL', 'SUPABASE_KEY'):
            os.environ.pop(name, None)
        self.pf = os.path.join(self.home, '.claude', 'pipeline-feedback')
        os.makedirs(self.pf)
        # шов ≠ шлях від `HOME` (`~/.claude/pipeline-feedback/…`): інакше зашитий літерал дав би ТОЙ САМИЙ файл і підміна шва лишилась би недоведеною
        os.makedirs(os.path.join(self.tmp, 'seam'))
        self.log = os.path.join(self.tmp, 'seam', 'overview-sync.log')
        self.popen = _Popen()
        self.addCleanup(self.stop_runner)
        for patcher in (mock.patch.object(serve.subprocess, 'Popen', self.popen), mock.patch.object(serve, 'OVERVIEW_LOG', self.log),
                        mock.patch.object(serve, 'supabase_config', return_value=(mb.URL, mb.KEY)),
                        mock.patch.dict(serve._SYNC_RUNS, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.mk('dash', roles=('dashboard',), server=GATE_SERVER)
        self.liga = self.new_space('Liga', integrations=True)
        self.plain = self.new_space('Plain')
        self.modp = self.new_space('Modp')
        dm.write_module_state(self.modp, 'dash', enabled=True)

    def stop_runner(self):
        """Дітей заглушки відпускаємо й чекаємо спостерігачів ДО того, як `Popen` повернеться справжнім (cleanup йде в зворотному
        порядку: цей — перший, патчі знімаються після)."""
        self.popen.finish_all()
        for t in [t for t in threading.enumerate() if t.name.startswith('overview-sync-')]:
            t.join(5)

    def trigger(self, sp):
        with spaces.request_space(sp['id']):
            serve.Handler._overview_sync(None)


class GateParity(_SyncEnv):
    """Диференційний `sync_gate`: ті самі рішення «стартувати чи ні», що записав знімок 0.11.0, — і названі свідомі відмінності
    (`argv` дитини: `sys.executable` і `--space`; конфіг не їде в оточенні; `DC_TASKS_FILE` глушить ЛІГУ)."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.gate = json.load(f)['sync_gate']

    def decide(self, sp, env=None, cfg=(mb.URL, mb.KEY)):
        """Чи стартувала дитина (і чи відкрито лог) для простору `sp` за оточення `env` і конфігу ЛІГИ `cfg`."""
        with mock.patch.dict(os.environ, env or {}), mock.patch.object(serve, 'supabase_config', return_value=cfg):
            self.trigger(sp)
        return {'popen_started': bool(self.popen.started), 'log_created': os.path.exists(self.log)}

    def test_the_decisions_match_the_snapshot(self):
        cases = {'integrations_on_with_config': (self.liga, None, (mb.URL, mb.KEY)),
                 'integrations_off': (self.plain, None, (mb.URL, mb.KEY)),
                 'no_config': (self.liga, None, (None, None)),
                 'dc_no_overview': (self.liga, {'DC_NO_OVERVIEW': '1'}, (mb.URL, mb.KEY))}
        for name, (sp, env, cfg) in cases.items():
            with self.subTest(case=name):
                self.setUp_again()
                got = self.decide(sp, env, cfg)
                want = {k: self.gate[name][k] for k in ('popen_started', 'log_created')}
                self.assertEqual(got, want)

    def setUp_again(self):
        """Чистий стан між випадками однієї перевірки: заглушка `Popen`, лог, DC_NO_OVERVIEW, стан «один на простір»."""
        self.popen.started.clear()
        self.popen.children.clear()
        serve._SYNC_RUNS.clear()
        os.environ.pop('DC_NO_OVERVIEW', None)
        if os.path.exists(self.log):
            os.remove(self.log)

    def test_dc_tasks_file_now_silences_the_league_a_deliberate_difference(self):
        """ЄДИНА зміна рішення проти знімка: 0.11.0 стартував дитину й за `DC_TASKS_FILE` (дірка: закон ізоляції стояв лише на
        читанні). Тепер ізольований прогін не пише у спільний Supabase ЛІГИ й з процесу."""
        self.assertTrue(self.gate['dc_tasks_file_with_integrations_on']['popen_started'], 'знімок: 0.11.0 стартував')
        got = self.decide(self.liga, {'DC_TASKS_FILE': os.path.join(self.tmp, 'x-tasks.json')})
        self.assertEqual(got, {'popen_started': False, 'log_created': False})

    def test_the_child_command_matches_the_snapshot_apart_from_the_named_differences(self):
        self.assertTrue(self.decide(self.liga)['popen_started'])
        (st,) = self.popen.started
        snap = self.gate['integrations_on_with_config']
        # argv: 4c-1 змінює навмисно — `sys.executable` (було літеральне python3) і явний `--space <id>`
        self.assertEqual(snap['argv'], ['python3', 'bin/overview_push.py', 'sync'])
        self.assertEqual(st['argv'], [sys.executable, os.path.join(ROOT, 'bin', 'overview_push.py'), 'sync', '--space',
                                      self.liga['id']])
        # оточення: 0.11.0 передавало `env` із парою SUPABASE_*; тепер — НІЧОГО (дитина читає `install_config` сама)
        self.assertEqual(snap['kwargs'], ['env', 'stderr', 'stdout'])
        self.assertEqual(st['kwargs'], ['stderr', 'stdout'])
        # решта — як було: лог ЛІГИ, режим `a`, stderr → stdout, і файл лога відкритий до `Popen`
        self.assertEqual((snap['log_mode'], snap['stderr_is_stdout']), ('a', True))
        self.assertEqual((st['mode'], st['stderr'], st['log']), ('a', subprocess.STDOUT, self.log))
        self.assertFalse(st['stdout_closed_at_start'])

    def test_an_ordinary_space_with_a_dashboard_module_starts_without_integrations(self):
        self.assertFalse(spaces.integrations_for(self.modp))
        self.assertTrue(self.decide(self.modp)['popen_started'])
        self.assertEqual(self.popen.started[0]['argv'][-2:], ['--space', self.modp['id']])

    def test_a_space_without_a_provider_is_silent(self):
        self.assertEqual(self.decide(self.plain), {'popen_started': False, 'log_created': False})
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'logs')), 'тиша — без лога навіть для звичайного простору')

    def test_dc_no_overview_is_silent_for_any_provider(self):
        for sp in (self.liga, self.modp):
            with self.subTest(space=sp['id']):
                self.setUp_again()
                self.assertFalse(self.decide(sp, {'DC_NO_OVERVIEW': '1'})['popen_started'])

    def test_dc_tasks_file_does_not_silence_an_ordinary_provider(self):
        """Закон ізоляції для `DC_TASKS_FILE` — про ШЛЯХ ЛІГИ (спільний Supabase); звичайний простір пише у свій модуль."""
        self.assertTrue(self.decide(self.modp, {'DC_TASKS_FILE': os.path.join(self.tmp, 'x-tasks.json')})['popen_started'])

    def test_a_failing_decision_is_silence_not_a_crash(self):
        for exc in (spaces.SpacesError('spaces-unreadable', '<registry>', 'тест'),
                    dm.ModuleError('space-json-unreadable', message='тест')):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(dm, 'provider', side_effect=exc):
                self.assertEqual(self.decide(self.liga), {'popen_started': False, 'log_created': False})


class SyncRunner(_SyncEnv):
    """Один синк на простір: поки дитина жива, повторний тригер лише ставить позначку «ще раз», і після її завершення стартує
    РІВНО ОДИН повтор (а не по одному на тригер); тригер іншого простору — паралельно. Логи: ЛІГА — шов `OVERVIEW_LOG`, інші —
    `<DEAI_HOME>/logs/dashboard-sync.log` (тека 0o700)."""

    def test_a_second_trigger_while_the_child_lives_does_not_start_another(self):
        self.trigger(self.liga)
        self.assertEqual(len(self.popen.started), 1)
        self.trigger(self.liga)
        self.assertEqual(len(self.popen.started), 1, 'друга дитина тієї ж пари простір+час не стартує')
        self.assertTrue(serve._SYNC_RUNS[self.liga['id']]['pending'], 'але позначка «ще раз» стоїть')

    def test_after_the_child_ends_exactly_one_rerun_not_one_per_trigger(self):
        self.trigger(self.liga)
        for _ in range(5):
            self.trigger(self.liga)                                    # п'ять запитів за час одного синку
        self.assertEqual(len(self.popen.started), 1)
        self.popen.children[0].finish()
        wait_until(self, lambda: len(self.popen.started) == 2, 'повтор після завершення')
        time.sleep(0.1)
        self.assertEqual(len(self.popen.started), 2, 'рівно ОДИН повтор, а не п\'ять')
        self.assertFalse(serve._SYNC_RUNS[self.liga['id']]['pending'], 'позначка зірвана: повтор уже йде')
        # повтор завершився, нових запитів не було → тиша й чистий стан
        self.popen.children[1].finish()
        wait_until(self, lambda: self.liga['id'] not in serve._SYNC_RUNS, 'стан простору прибрано')
        self.assertEqual(len(self.popen.started), 2)

    def test_a_trigger_after_the_child_ended_starts_a_fresh_one(self):
        self.trigger(self.liga)
        self.popen.children[0].finish()
        wait_until(self, lambda: self.liga['id'] not in serve._SYNC_RUNS, 'стан простору прибрано')
        self.trigger(self.liga)
        self.assertEqual(len(self.popen.started), 2)

    def test_another_space_starts_in_parallel(self):
        self.trigger(self.liga)
        self.trigger(self.modp)
        self.assertEqual(len(self.popen.started), 2, 'тригер іншого простору не чекає чужого синку')
        self.assertEqual({st['argv'][-1] for st in self.popen.started}, {self.liga['id'], self.modp['id']})
        self.assertFalse(serve._SYNC_RUNS[self.liga['id']]['pending'])

    def test_a_failed_start_leaves_no_state_behind(self):
        with mock.patch.object(serve.subprocess, 'Popen', side_effect=OSError('no python')):
            self.trigger(self.liga)
        self.assertEqual(serve._SYNC_RUNS, {})
        self.trigger(self.liga)                                        # наступний тригер стартує як звичайно
        self.assertEqual(len(self.popen.started), 1)

    def test_the_league_log_is_the_seam(self):
        self.trigger(self.liga)
        self.assertEqual(self.popen.started[0]['log'], self.log)
        self.assertNotEqual(os.path.dirname(self.log), self.pf)        # шов ≠ шлях від HOME: літерал у коді був би видний
        self.assertTrue(self.popen.started[0]['log'].startswith(self.tmp + os.sep), 'лог — під тимчасовою текою тесту')

    def test_another_space_logs_under_deai_home_in_a_private_dir(self):
        old = os.umask(0)                                              # щедра маска: `makedirs(mode=)` без `chmod` дала б 0o777
        self.addCleanup(os.umask, old)
        self.trigger(self.modp)
        d = os.path.join(self.deai, 'logs')
        self.assertEqual(self.popen.started[0]['log'], os.path.join(d, 'dashboard-sync.log'))
        self.assertEqual(os.stat(d).st_mode & 0o777, 0o700)
        self.assertFalse(os.path.exists(self.log), 'лог ЛІГИ чужий простір не пише')

    def test_an_existing_loose_log_dir_is_tightened(self):
        d = os.path.join(self.deai, 'logs')
        os.makedirs(d, mode=0o755)
        os.chmod(d, 0o755)
        self.trigger(self.modp)
        self.assertEqual(os.stat(d).st_mode & 0o777, 0o700)
        self.assertEqual(len(self.popen.started), 1)

    def test_the_log_dir_that_cannot_be_made_is_swallowed(self):
        with mock.patch.object(serve.os, 'makedirs', side_effect=OSError('read-only')):
            self.trigger(self.modp)                                    # не кидає
        self.assertEqual(self.popen.started, [])
        self.assertEqual(serve._SYNC_RUNS, {})

    # ---- ЛІГА й простір з id `legacy`: окремі ключі; один ключ на простір ЛІГИ ----------------------------------------

    def mark_league(self, sp):
        """Запис `sp` у реєстрі стає простором ЛІГА (`legacy: True`)."""
        with open(self.reg_file, encoding='utf-8') as f:
            reg = json.load(f)
        for x in reg['spaces']:
            if x['id'] == sp['id']:
                x['legacy'] = True
        mb._write(self.reg_file, reg)

    def test_a_real_space_with_the_id_legacy_is_not_the_league(self):
        """⛔ `SPACE_ID_RE` пропускає `legacy`: простір «Legacy» не мусить збігатись із ЛІГОЮ ні в argv, ні в ключі `_SYNC_RUNS`."""
        self.mark_league(self.liga)
        real = self.new_space('Legacy', integrations=True)
        self.assertEqual(real['id'], 'legacy')
        self.trigger(real)
        self.trigger(self.liga)
        self.assertEqual([st['argv'][-2:] for st in self.popen.started],
                         [['--space', 'legacy'], ['--space', self.liga['id']]], 'кожен синк веде СВІЙ простір')
        self.assertEqual(sorted(serve._SYNC_RUNS), sorted(['legacy', self.liga['id']]))

    def test_unfixed_and_fixed_league_triggers_are_one_run(self):
        """Синк ЛІГИ без фіксованого простору запиту має ТОЙ САМИЙ ключ, що тригер, фіксований на її записі: дві синки однієї
        ЛІГИ не біжать разом."""
        self.mark_league(self.liga)
        self.trigger(self.liga)
        with spaces.request_space(None):
            serve.Handler._overview_sync(None)
            serve.Handler._overview_sync(None)
        self.assertEqual(len(self.popen.started), 1)
        self.assertEqual(list(serve._SYNC_RUNS), [self.liga['id']])
        self.assertTrue(serve._SYNC_RUNS[self.liga['id']]['pending'])

    def test_unfixed_league_without_a_registry_entry_uses_the_flag_and_a_key_no_space_can_have(self):
        with spaces.request_space(None):
            serve.Handler._overview_sync(None)
        self.assertEqual(self.popen.started[0]['argv'][-1:], ['--legacy'])
        self.assertEqual(list(serve._SYNC_RUNS), [serve.LEAGUE_KEY])
        self.assertIsNone(spaces.SPACE_ID_RE.fullmatch(serve.LEAGUE_KEY))

    # ---- спостерігач і чужий запис -------------------------------------------------------------------------------------

    def test_a_stale_watcher_leaves_the_live_runs_entry_alone(self):
        """Дитина 1 скінчилась, але її спостерігач ще не взяв лок; новий тригер стартує дитину 2. Спостерігач 1 прокидається:
        запис уже чужий (`popen is not p`) — він виходить, НЕ видаляючи запис живої дитини 2. Інакше третій тригер стартував би
        другий синк поруч із живим."""
        self.popen.hold_next = True                                    # `wait()` дитини 1 не повертається, поки не відкриємо шлюз
        self.trigger(self.liga)
        c1 = self.popen.children[0]
        c1.finish()                                                    # `poll()` уже не `None`, а спостерігач ще чекає
        self.trigger(self.liga)
        self.assertEqual(len(self.popen.started), 2)
        c1.wait_gate.set()                                             # спостерігач 1 прокидається й бачить чужий запис
        name = f'overview-sync-{self.liga["id"]}'
        alive = lambda: len([t for t in threading.enumerate() if t.name == name and t.is_alive()])  # noqa: E731
        wait_until(self, lambda: alive() == 1, 'спостерігач 1 вийшов, спостерігач 2 чекає свою дитину')
        self.assertIn(self.liga['id'], serve._SYNC_RUNS, 'запис живої дитини 2 стертий застарілим спостерігачем')
        self.trigger(self.liga)
        self.assertEqual(len(self.popen.started), 2, 'третій тригер не стартує другий синк поруч із живим')
        self.assertTrue(serve._SYNC_RUNS[self.liga['id']]['pending'])

    # ---- дедлайн дитини ------------------------------------------------------------------------------------------------

    def test_a_hung_child_is_terminated_by_its_handle_after_the_deadline(self):
        now = [1000.0]
        with mock.patch.object(serve, '_SYNC_CLOCK', lambda: now[0]):
            self.trigger(self.liga)
            now[0] += serve.SYNC_DEADLINE_S - 1
            self.trigger(self.liga)                                    # ще в межах дедлайну: лише позначка
            self.assertFalse(self.popen.children[0].terminated)
            self.assertEqual(len(self.popen.started), 1)
            now[0] += 2                                                # дедлайн минув, дитина жива
            self.trigger(self.liga)
        self.assertTrue(self.popen.children[0].terminated, 'завислу дитину перервано за її дескриптором')
        self.assertEqual(len(self.popen.started), 2, 'і стартовано свіжу')
        self.assertFalse(serve._SYNC_RUNS[self.liga['id']]['pending'])
        with open(self.log, encoding='utf-8') as f:
            notes = [ln for ln in f.read().splitlines() if 'завис' in ln]
        self.assertEqual(len(notes), 1, 'рівно один рядок у лозі')
        self.assertIn(str(serve.SYNC_DEADLINE_S), notes[0])

    def test_a_child_that_ended_before_the_deadline_is_not_terminated(self):
        now = [1000.0]
        with mock.patch.object(serve, '_SYNC_CLOCK', lambda: now[0]):
            self.trigger(self.liga)
            self.popen.children[0].wait_gate.set()
            self.popen.children[0].done.set()
            now[0] += serve.SYNC_DEADLINE_S * 3
            self.trigger(self.liga)                                    # дитина вже мертва: звичайний новий старт, без `terminate`
        self.assertFalse(self.popen.children[0].terminated)
        self.assertEqual(len(self.popen.started), 2)

    # ---- права файла лога ---------------------------------------------------------------------------------------------

    def test_the_non_league_log_file_is_private(self):
        old = os.umask(0)                                              # щедра маска: новий файл мав би 0o666
        self.addCleanup(os.umask, old)
        self.trigger(self.modp)
        path = os.path.join(self.deai, 'logs', 'dashboard-sync.log')
        self.assertEqual(self.popen.started[0]['log'], path)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_an_existing_loose_log_file_is_tightened(self):
        d = os.path.join(self.deai, 'logs')
        os.makedirs(d, mode=0o700)
        path = os.path.join(d, 'dashboard-sync.log')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('старий рядок\n')
        os.chmod(path, 0o644)
        self.trigger(self.modp)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
