"""Командний дашборд як роль `dashboard` (етап 4c-1). Тут — тести ядра; знімок 0.11.0 — еталон паритету.

Task 1: лише знімок `tests/fixtures/dashboard/before-4c1.json` (його знімає `tests/make_before_4c1.py` на коді БЕЗ змін,
і більше він не переписується) та перевірка його форми. Тести паритету наступних задач читають цей JSON, а не переганяють
генератор.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)
import dashboard  # noqa: E402
import deai_modules as dm  # noqa: E402
import install_config  # noqa: E402
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


if __name__ == '__main__':
    unittest.main()
