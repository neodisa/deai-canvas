"""Статуси трекера як роль `tracker` (етап 4c-2). Тут — тести ядра й модуля; знімок 0.12.0 — еталон паритету.

Task 1: лише знімок `tests/fixtures/tracker/before-4c2.json` (його знімає `tests/make_before_4c2.py` на коді БЕЗ змін, і більше
він не переписується) та перевірка його форми. Тести паритету наступних задач читають цей JSON, а не переганяють генератор.
"""
import contextlib
import json
import os
import re
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
import overview_push as ov  # noqa: E402
import registry  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_modules as tm  # noqa: E402  (каркас `Env`: тимчасові HOME/DEAI_HOME, тека модулів-фікстур)
import tracker  # noqa: E402

_REAL = None
#: Справжня тека вбудованих модулів: `tm.Env` підміняє `dm.builtin_dir` на тимчасову, а шлях ЛІГИ мусить бачити справжній `jira-tracker`.
_REAL_BUILTIN = dm.builtin_dir


def setUpModule():
    """Клас `TrackerRole` створює простори: справжній `~/.deai` стереже знімок на вході й звірка на виході
    (інваріант `test_serve.TestsCannotWriteLiveConfig`)."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


BEFORE = os.path.join(_HERE, 'fixtures', 'tracker', 'before-4c2.json')

#: Поля, що змінюються між прогонами: у знімку їх не має бути ніде (ні в тілі відповіді, ні в рядках синку).
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


class Before4c2Shape(unittest.TestCase):
    """Знімок поведінки 0.12.0 на місці й має ключі, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['jira_request', 'meta', 'sync_cards', 'tasks_overview'])
        self.assertEqual(self.snap['meta']['version'], '0.12.0')
        self.assertEqual(self.snap['meta']['generator'], 'tests/make_before_4c2.py')

    def test_jira_request_shape(self):
        jr = self.snap['jira_request']
        self.assertEqual(sorted(jr), ['network_error', 'no_credentials', 'request'])
        calls = jr['request']['calls']
        self.assertEqual(len(calls), 1, 'один запит на всі ключі')
        self.assertEqual(calls[0]['method'], 'POST')
        self.assertEqual(calls[0]['path'], '/rest/api/3/search/jql')
        self.assertEqual(calls[0]['headers']['authorization'], '<basic>')
        self.assertEqual(calls[0]['body']['jql'], 'key in (DEMO-1,DEMO-2)', 'унікальні ключі, порожні відкинуто')
        self.assertEqual(jr['request']['result']['DEMO-1'], {'name': 'In Review', 'cat': 'indeterminate'})
        self.assertEqual(jr['no_credentials'], {'result': {}, 'urlopen_calls': 0})
        self.assertEqual(jr['network_error']['result'], {})
        self.assertEqual(jr['network_error']['urlopen_calls'], 1, 'запит був, мережа впала')

    def test_sync_cards_shape(self):
        sc = self.snap['sync_cards']
        self.assertEqual(sorted(sc), ['input', 'log', 'pushes', 'statuses_asked', 'statuses_raises', 'summary'])
        self.assertEqual(sc['statuses_asked'], [['DEMO-1', 'DEMO-2', None, 'DEMO-9']], '0.12.0: сирий список, із None')
        self.assertEqual(len(sc['pushes']), 1)
        self.assertEqual(sc['pushes'][0]['mode'], 'merge')
        cards = {c['id']: c for c in sc['pushes'][0]['cards']}
        self.assertEqual(sorted(cards), ['t1', 't2', 't3', 't4'])
        self.assertEqual(cards['t1']['jira_status'], 'In Review')
        self.assertEqual(cards['t2']['jira_status_cat'], 'done')
        for tid in ('t3', 't4'):        # без `jira` / ключ, якого нема у відповіді: полів статусу нема
            self.assertFalse([k for k in cards[tid] if k.startswith('jira_status')], tid)
        raised = sc['statuses_raises']
        self.assertEqual(raised['statuses_asked'], sc['statuses_asked'])
        self.assertEqual(raised['log'], sc['log'], '0.12.0: збій `statuses` мовчки, жодного рядка логу')
        self.assertEqual(len(raised['pushes']), 1)
        for card in raised['pushes'][0]['cards']:
            self.assertFalse([k for k in card if k.startswith('jira_status')], card['id'])

    def test_tasks_overview_shape(self):
        to = self.snap['tasks_overview']
        self.assertEqual(to['status'], 200)
        self.assertEqual(sorted(to['body']), ['current', 'mine', 'space', 'team'])
        self.assertEqual(sorted(to['volatile']), ['fetchedAt', 'rowsAt'])
        mine = {m['id']: m for m in to['body']['mine']}
        self.assertEqual(mine['t1']['jiraStatus'], 'In Review')
        self.assertEqual((mine['t2']['jiraStatus'], mine['t2']['jiraCat']), (None, None), 'своя задача без рядка дашборда')
        self.assertEqual(to['body']['team']['rows'][0]['jiraCat'], 'indeterminate')

    def test_no_volatile_fields_or_paths(self):
        # Вихід (тіло відповіді, картки синку) без мінливого; `volatile` (лише ТИПИ вирізаних полів), `meta` (їх перелік) і
        # `input_rows` (вхідні рядки-заглушки: там `updated_at` є за задумом) не перевіряються.
        outputs = {'sync_cards': [self.snap['sync_cards']['pushes'], self.snap['sync_cards']['statuses_raises']['pushes']], 'tasks_overview': self.snap['tasks_overview']['body'],
                   'jira_request': self.snap['jira_request']}
        for path, key, _ in walk(outputs):
            with self.subTest(path=path, key=key):
                self.assertNotIn(key, VOLATILE)
        text = json.dumps(self.snap)
        for needle in ('/var/', '/tmp', '/Users/', 'before-4c2-'):
            self.assertNotIn(needle, text, 'у знімку нема абсолютних шляхів')


if __name__ == '__main__':
    unittest.main()


# ------------------------------------------------------------------------------------------ Task 2: роль і ядро

#: Модуль ролі `tracker`: `check` і обовʼязкова `statuses`.
TRACKER_SERVER = tm.CHECK_ONLY + 'def statuses(ctx, keys):\n    return {}\n'


class TrackerRole(tm.Env):
    """Роль `tracker` у каркасі модулів (4c-2, Task 2): маніфест, постачальник, `capabilities`, коди помилок."""

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
        self.assertEqual(dm.ROLES_CALLED, ('publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker', 'notify'))
        self.assertEqual(dm.ROLES_RESERVED, ())
        self.assertEqual(dm.ROLE_FUNCTIONS['tracker'], ('statuses',))
        self.assertIn('tracker', dm.LEGACY_ROLES)
        self.assertIn('tracker', dm.STRICT_LEGACY_ROLES)
        self.assertIn('jira-tracker', dm.KNOWN_OTHER_MODULES)

    def test_the_league_path_of_the_tracker_is_not_a_fallback_after_an_error(self):
        """⛔ Зашитий шлях трекера — сайт Jira ЛІГИ з обліковими людини, тож «через помилку» на нього не переходимо:
        `tracker` НЕ в `LEGACY_ON_ERROR_ROLES`."""
        self.assertNotIn('tracker', dm.LEGACY_ON_ERROR_ROLES)

    def test_a_tracker_module_needs_statuses(self):
        self.mk('trk-bare', roles=('tracker',), server=tm.CHECK_ONLY)
        self.assertIn('statuses', self.error_of('trk-bare'))
        self.mk('trk-ok', roles=('tracker',), server=TRACKER_SERVER)
        self.assertEqual(dm.catalog()['trk-ok'].status, 'ok')

    def test_the_provider_of_an_integrations_space_without_a_module_is_legacy(self):
        ig = self.new_space('Integ', integrations=True)
        plain = self.new_space('Plain')
        self.assertEqual(dm.provider('tracker', ig), 'legacy')
        self.assertEqual(dm.capabilities(ig)['tracker'], 'legacy')
        self.assertIsNone(dm.provider('tracker', plain))             # без інтеграцій і без модуля — нікого
        self.assertIsNone(dm.capabilities(plain)['tracker'])

    def test_an_enabled_module_is_the_provider_in_both_kinds_of_space(self):
        self.mk('trk-ok', roles=('tracker',), server=TRACKER_SERVER)
        ig = self.new_space('Integ', integrations=True)
        plain = self.new_space('Plain')
        for sp in (ig, plain):
            dm.write_module_state(sp, 'trk-ok', enabled=True)
            self.assertEqual(dm.provider('tracker', sp).id, 'trk-ok')
            self.assertEqual(dm.capabilities(sp)['tracker'], 'trk-ok')
        dm.write_module_state(ig, 'trk-ok', enabled=False)
        self.assertEqual(dm.capabilities(ig)['tracker'], 'legacy')   # вимкнули: ЛІГА повертається до зашитого шляху
        dm.write_module_state(plain, 'trk-ok', enabled=False)
        self.assertIsNone(dm.capabilities(plain)['tracker'])

    def test_a_module_error_is_none_never_legacy_and_sets_the_error(self):
        ig = self.new_space('Integ', integrations=True)
        with mock.patch.object(dm, '_provider_for', side_effect=dm.ModuleError('bad-manifest', message='x')):
            caps = dm.capabilities(ig)
        self.assertIsNone(caps['tracker'])
        self.assertEqual(caps['error'], 'bad-manifest')
        self.assertEqual((caps['publish'], caps['vcs']), ('legacy', 'legacy'))     # а локальні ролі лишились зашитими
        dm.reset_caches()
        with mock.patch.object(dm, '_caps_key', side_effect=RuntimeError('bug')):      # запасний словник: теж не 'legacy'
            self.assertIsNone(dm.capabilities(ig)['tracker'])

    def test_an_unreadable_space_json_in_an_integrations_space_never_yields_legacy(self):
        """⛔ Як `comments` і `dashboard`: нечитабельний `space.json` у просторі з інтеграціями дає `space-json-unreadable`,
        а не `'legacy'` (не знаємо, чи людина ввімкнула там свій трекер)."""
        ig = self.new_space('Integ', integrations=True)
        with open(os.path.join(ig['path'], 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('tracker', ig)
        self.assertEqual(cm.exception.code, 'space-json-unreadable')
        caps = dm.capabilities(ig)
        self.assertIsNone(caps['tracker'])
        self.assertEqual(caps['error'], 'space-json-unreadable')
        self.assertEqual((caps['publish'], caps['vcs']), ('legacy', 'legacy'))     # локальні ролі шлях ЛІГИ не втрачають

    def test_the_error_codes_have_http_statuses(self):
        self.assertEqual(dm.STATUS['tracker-unconfigured'], 409)
        self.assertEqual(dm.STATUS['tracker-error'], 502)
        self.assertEqual(dm.ModuleError('tracker-unconfigured').status, 409)
        self.assertEqual(dm.ModuleError('tracker-error').status, 502)


def _stat(name='In Review', cat='indeterminate'):
    return {'name': name, 'cat': cat}


class TrackerCore(unittest.TestCase):
    """`app/tracker.py`: фільтр ключів, нормалізація відповіді, пакети по 100, збій пакета."""

    def test_constants(self):
        self.assertEqual((tracker.BATCH, tracker.NAME_MAX), (100, 80))
        self.assertEqual((tracker.READ_TIMEOUT, tracker.READ_SOCKET_S), (6, 4))
        self.assertEqual((tracker.SYNC_TIMEOUT, tracker.SYNC_SOCKET_S), (30, 15))
        self.assertEqual(tracker.CATS, ('new', 'indeterminate', 'done'))
        self.assertEqual(tracker.LEGACY_MODULE, 'jira-tracker')
        self.assertTrue(tracker.UNCONFIGURED.startswith('Jira не налаштовано'))
        self.assertIn('jira_base', tracker.UNCONFIGURED)

    def test_key_re_accepts_only_whole_well_formed_keys(self):
        for ok in ('DEMO-1', 'AB_2-10', 'A-1', 'X9-9999999999', 'A' * 32 + '-7'):
            self.assertTrue(tracker.KEY_RE.fullmatch(ok), ok)
        for bad in ('demo-1', 'DEMO-0', 'DEMO-01', '-1', 'DEMO 1', 'DEMO-1) OR (x', 'DEMO-1\n', ' DEMO-1', 'DEMO-', 'DEMO',
                    'A' * 33 + '-1', '1DEMO-1', 'DEMO-12345678901', 'ДЕМО-1', '', 'DEMO-1; DROP'):
            self.assertIsNone(tracker.KEY_RE.fullmatch(bad), bad)

    def test_keys_of_is_unique_valid_and_in_file_order(self):
        tasks = {'a': {'jira': 'DEMO-2'}, 'b': {'jira': 'DEMO-1'}, 'c': {'jira': 'DEMO-2'}, 'd': {'jira': 'bad'},
                 'e': {}, 'f': {'jira': ['DEMO-3']}}
        self.assertEqual(tracker.keys_of(tasks), ['DEMO-2', 'DEMO-1'])
        self.assertEqual(tracker.keys_of({}), [])
        self.assertEqual(tracker.keys_of(None), [])
        self.assertEqual(tracker.keys_of({'a': 'not a task', 'b': None, 'c': {'jira': 'DEMO-5'}}), ['DEMO-5'])

    def test_normalize_keeps_only_asked_keys(self):
        data = {'DEMO-1': _stat(), 'DEMO-2': _stat('Done', 'done'), 'OTHER-9': _stat()}
        self.assertEqual(tracker.normalize(data, ['DEMO-1', 'DEMO-3']), {'DEMO-1': _stat()})
        self.assertEqual(tracker.normalize({}, ['DEMO-1']), {})

    def test_normalize_cuts_the_name_and_drops_bad_names(self):
        data = {'DEMO-1': {'name': 'x' * 200, 'cat': 'new'}}
        self.assertEqual(tracker.normalize(data, ['DEMO-1'])['DEMO-1']['name'], 'x' * 80)
        for bad in ('', '   ', None, 5, ['a'], 'In\x00Review', 'In\nReview', 'In\x7fReview', 'a\u2028b', 'a\u202eb', 'a\u200bb'):
            self.assertEqual(tracker.normalize({'DEMO-1': {'name': bad, 'cat': 'new'}}, ['DEMO-1']), {}, repr(bad))
        self.assertEqual(tracker.normalize({'DEMO-1': 'In Review', 'DEMO-2': None, 'DEMO-3': ['x']},
                                           ['DEMO-1', 'DEMO-2', 'DEMO-3']), {})

    def test_normalize_unknown_category_is_none(self):
        for cat, want in (('new', 'new'), ('indeterminate', 'indeterminate'), ('done', 'done'), ('NEW', None),
                          ('open', None), ('', None), (None, None), (7, None), (['done'], None)):
            got = tracker.normalize({'DEMO-1': {'name': 'S', 'cat': cat}}, ['DEMO-1'])['DEMO-1']['cat']
            self.assertEqual(got, want, repr(cat))
        self.assertIsNone(tracker.normalize({'DEMO-1': {'name': 'S'}}, ['DEMO-1'])['DEMO-1']['cat'])

    def test_normalize_rejects_a_non_dict(self):
        for bad in (None, [], 'x', 5, [('DEMO-1', _stat())]):
            with self.assertRaises(ValueError):
                tracker.normalize(bad, ['DEMO-1'])

    def fake(self, calls, answer=None):
        def call(module, fn, ctx, chunk, timeout=None):
            calls.append((module, fn, dict(ctx), list(chunk), timeout))
            return answer(chunk) if answer else {k: _stat() for k in chunk}
        return call

    def test_statuses_drops_junk_before_the_call(self):
        calls = []
        out = tracker.statuses('M', {'space': {}}, ['DEMO-1', 'bad', 'DEMO-1', None, 'DEMO-2) OR (x', 'DEMO-2', 5],
                               timeout=6, socket_s=4, call=self.fake(calls))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][3], ['DEMO-1', 'DEMO-2'], 'сміття й повтори не доходять до модуля')
        self.assertEqual(sorted(out), ['DEMO-1', 'DEMO-2'])

    def test_statuses_splits_into_batches_of_100(self):
        calls = []
        keys = [f'DEMO-{i}' for i in range(1, 251)]
        out = tracker.statuses('M', {}, keys, timeout=6, socket_s=4, call=self.fake(calls))
        self.assertEqual([len(c[3]) for c in calls], [100, 100, 50])
        self.assertEqual([k for c in calls for k in c[3]], keys)
        self.assertEqual(sorted(out), sorted(keys))

    def test_statuses_gives_the_module_its_socket_budget_and_the_core_its_wait(self):
        calls = []
        ctx = {'space': {'id': 's1'}, 'settings': {'a': 1}}
        tracker.statuses('MOD', ctx, [f'DEMO-{i}' for i in range(1, 151)], timeout=6, socket_s=4, call=self.fake(calls))
        self.assertEqual(len(calls), 2)
        for module, fn, ctx2, chunk, timeout in calls:
            self.assertEqual((module, fn, timeout), ('MOD', 'statuses', 6))
            self.assertEqual(ctx2['timeout_s'], 4)
            self.assertEqual(ctx2['space'], {'id': 's1'})
        self.assertEqual(ctx, {'space': {'id': 's1'}, 'settings': {'a': 1}}, 'вихідний ctx не змінено')
        self.assertNotIn('timeout_s', ctx)

    def test_statuses_without_a_valid_key_makes_no_call(self):
        calls = []
        for keys in ([], ['bad', None, 3], ['demo-1']):
            self.assertEqual(tracker.statuses('M', {}, keys, timeout=6, socket_s=4, call=self.fake(calls)), {})
        self.assertEqual(calls, [])

    def test_a_failed_batch_raises_to_the_caller(self):
        calls = []

        def answer(chunk):
            if len(calls) == 2:
                raise dm.ModuleError('tracker-error', message='Jira is down')
            return {k: _stat() for k in chunk}
        keys = [f'DEMO-{i}' for i in range(1, 251)]
        with self.assertRaises(dm.ModuleError) as cm:
            tracker.statuses('M', {}, keys, timeout=6, socket_s=4, call=self.fake(calls, answer))
        self.assertEqual(cm.exception.code, 'tracker-error')
        self.assertEqual(len(calls), 2, 'після збою решту пакетів не питаємо')

    def test_a_non_dict_answer_is_a_tracker_error(self):
        with self.assertRaises(dm.ModuleError) as cm:
            tracker.statuses('M', {}, ['DEMO-1'], timeout=6, socket_s=4, call=lambda *a, **k: ['DEMO-1'])
        self.assertEqual(cm.exception.code, 'tracker-error')

    def test_the_answer_is_normalized(self):
        def call(module, fn, ctx, chunk, timeout=None):
            return {'DEMO-1': {'name': 'x' * 200, 'cat': 'weird'}, 'OTHER-1': _stat(), 'DEMO-2': {'name': '', 'cat': 'new'}}
        out = tracker.statuses('M', {}, ['DEMO-1', 'DEMO-2'], timeout=6, socket_s=4, call=call)
        self.assertEqual(out, {'DEMO-1': {'name': 'x' * 80, 'cat': None}})

    def test_the_default_call_is_the_core_call(self):
        with mock.patch.object(dm, 'call', return_value={'DEMO-1': _stat()}) as c:
            out = tracker.statuses('M', {'a': 1}, ['DEMO-1'], timeout=6, socket_s=4)
        self.assertEqual(out, {'DEMO-1': _stat()})
        c.assert_called_once_with('M', 'statuses', {'a': 1, 'timeout_s': 4}, ['DEMO-1'], timeout=6)

    def test_the_core_does_not_import_serve(self):
        with open(os.path.join(ROOT, 'app', 'tracker.py'), encoding='utf-8') as f:
            src = f.read()
        self.assertNotRegex(src, r'(?m)^\s*(import serve|from serve )')


JIRA = 'https://demo.atlassian.example'


class JiraConfig(unittest.TestCase):
    """`install_config.jira_config()`: адреса з `tasks.json` установки, облікові — оточення раніше за файли. Тимчасові
    HOME і старий файл задач: справжні `~/.claude/pipeline-feedback/` і `tasks.json` не читаються."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, 'home')
        self.legacy = os.path.join(self.tmp.name, 'tasks.json')
        os.makedirs(os.path.join(self.home, '.claude', 'pipeline-feedback'))
        env = mock.patch.dict(os.environ, {'HOME': self.home}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in ('DC_TASKS_FILE', 'JIRA_EMAIL', 'JIRA_TOKEN'):
            os.environ.pop(name, None)
        patch = mock.patch.object(spaces, 'legacy_tasks_file', return_value=self.legacy)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, obj, raw=None):
        with open(self.legacy, 'w', encoding='utf-8') as f:
            f.write(raw if raw is not None else json.dumps(obj))

    def cred_file(self, name, text):
        with open(os.path.join(self.home, '.claude', 'pipeline-feedback', name), 'w', encoding='utf-8') as f:
            f.write(text)

    def test_base_and_credentials_from_environment(self):
        self.write({'jira_base': JIRA + '/'})
        os.environ['JIRA_EMAIL'], os.environ['JIRA_TOKEN'] = 'alpha@example.com', 'tok-test-1'
        self.assertEqual(install_config.jira_config(), (JIRA, 'alpha@example.com', 'tok-test-1'))

    def test_credentials_from_files_when_there_is_no_environment(self):
        self.write({'jira_base': JIRA})
        self.cred_file('jira-email', 'alpha@example.com\n')
        self.cred_file('jira-token', ' tok-test-1 \n')
        self.assertEqual(install_config.jira_config(), (JIRA, 'alpha@example.com', 'tok-test-1'))

    def test_environment_wins_over_files(self):
        self.write({'jira_base': JIRA})
        self.cred_file('jira-email', 'file@example.com')
        self.cred_file('jira-token', 'tok-file')
        os.environ['JIRA_EMAIL'], os.environ['JIRA_TOKEN'] = 'env@example.com', 'tok-env'
        self.assertEqual(install_config.jira_config(), (JIRA, 'env@example.com', 'tok-env'))

    def test_email_and_token_are_read_independently(self):
        """Як `_jira_creds` до 4c-2: кожне значення — з оточення, інакше з файла; джерела можуть бути різні."""
        self.write({'jira_base': JIRA})
        self.cred_file('jira-email', 'file@example.com')
        self.cred_file('jira-token', 'tok-file')
        os.environ['JIRA_EMAIL'] = 'env@example.com'                 # токена в оточенні нема
        self.assertEqual(install_config.jira_config(), (JIRA, 'env@example.com', 'tok-file'))
        os.environ.pop('JIRA_EMAIL')
        os.environ['JIRA_TOKEN'] = 'tok-env'                         # а тепер навпаки
        self.assertEqual(install_config.jira_config(), (JIRA, 'file@example.com', 'tok-env'))
        os.remove(os.path.join(self.home, '.claude', 'pipeline-feedback', 'jira-email'))
        self.assertEqual(install_config.jira_config(), (None, None, None), 'пошти нема ніде')

    def test_an_empty_or_bad_environment_value_falls_through_to_the_file(self):
        self.write({'jira_base': JIRA})
        self.cred_file('jira-email', 'file@example.com')
        self.cred_file('jira-token', 'tok-file')
        os.environ['JIRA_TOKEN'] = 'tok-env'
        for bad in ('', '   ', ' \n ', 'a\nb@example.com', 'a\tb@example.com'):
            os.environ['JIRA_EMAIL'] = bad
            self.assertEqual(install_config.jira_config(), (JIRA, 'file@example.com', 'tok-env'), repr(bad))
        os.environ['JIRA_EMAIL'] = 'env@example.com'
        for bad in ('', '   ', 'tok env'):
            os.environ['JIRA_TOKEN'] = bad
            self.assertEqual(install_config.jira_config(), (JIRA, 'env@example.com', 'tok-file'), repr(bad))

    def test_no_credentials_is_no_config(self):
        self.write({'jira_base': JIRA})
        self.assertEqual(install_config.jira_config(), (None, None, None))
        self.cred_file('jira-email', 'alpha@example.com')
        self.assertEqual(install_config.jira_config(), (None, None, None), 'є пошта, токена нема')
        self.cred_file('jira-token', '  \n')
        self.assertEqual(install_config.jira_config(), (None, None, None), 'порожній токен')

    def test_no_base_or_a_bad_base_is_no_config(self):
        os.environ['JIRA_EMAIL'], os.environ['JIRA_TOKEN'] = 'alpha@example.com', 'tok-test-1'
        self.write({'tasks': {}})
        self.assertEqual(install_config.jira_config(), (None, None, None))
        for base in ('http://demo.atlassian.example', '', 5, None, 'https://demo.atlassian.example/path',
                     'https://user@demo.atlassian.example', 'https://<сайт>.atlassian.net', 'https://<site>.atlassian.net',
                     'demo.atlassian.example', 'https://demo atlassian.example'):
            self.write({'jira_base': base})
            self.assertEqual(install_config.jira_config(), (None, None, None), repr(base))

    def test_a_token_with_a_space_is_no_config(self):
        self.write({'jira_base': JIRA})
        os.environ['JIRA_EMAIL'], os.environ['JIRA_TOKEN'] = 'alpha@example.com', 'tok test'
        self.assertEqual(install_config.jira_config(), (None, None, None))

    def test_a_port_is_allowed_and_the_slash_trimmed(self):
        self.write({'jira_base': 'https://demo.atlassian.example:8443/'})
        os.environ['JIRA_EMAIL'], os.environ['JIRA_TOKEN'] = 'alpha@example.com', 'tok-test-1'
        self.assertEqual(install_config.jira_config()[0], 'https://demo.atlassian.example:8443')

    def test_a_broken_or_missing_tasks_file_is_no_config_without_an_exception(self):
        os.environ['JIRA_EMAIL'], os.environ['JIRA_TOKEN'] = 'alpha@example.com', 'tok-test-1'
        self.assertEqual(install_config.jira_config(), (None, None, None))          # файла нема
        for raw in ('{oops', '[]', 'null', '[' * 100000, '{"a":' * 100000):
            self.write(None, raw=raw)
            self.assertEqual(install_config.jira_config(), (None, None, None), raw[:6])

    def test_the_real_home_is_never_read(self):
        """Файли облікових шукаються під `HOME` тесту, а не в справжньому домашньому каталозі."""
        self.write({'jira_base': JIRA})
        real = os.path.expanduser('~')
        self.assertTrue(real.startswith(self.home), real)
        self.assertEqual(install_config.jira_config(), (None, None, None))


class LegacyAdapter(unittest.TestCase):
    """`tracker.legacy_ctx` і `tracker.legacy_module` — адаптер ЛІГИ (неявний постачальник): `ctx` будує ядро з конфігу
    установки, а не з простору (⛔ не `module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`)."""

    def setUp(self):
        os.environ.pop('DEAI_EXTRA_MODULES', None)
        dm.reset_caches()

    def test_legacy_ctx_is_built_from_the_install_config_not_from_the_frame(self):
        ctx = tracker.legacy_ctx('https://demo.atlassian.example', 'alpha@example.com', 'tok-test-1', space_id='s')
        self.assertEqual(ctx['settings'], {'base': 'https://demo.atlassian.example', 'email': 'alpha@example.com'})
        self.assertEqual(ctx['secrets'], {'token': 'tok-test-1'})
        self.assertEqual(ctx['space'], {'id': 's', 'path': ''})
        self.assertIs(ctx['legacy'], True)
        self.assertIs(ctx['ModuleError'], dm.ModuleError)
        self.assertEqual(tracker.legacy_ctx('https://x.example', 'a@b.c', 't')['space']['id'], '')

    def test_legacy_ctx_never_reads_the_spaces_layer(self):
        """⛔ Урок 4c-1: `module_ctx()` при вимкненому шарі читав би справжній `~/.deai` — адаптер до нього не торкається."""
        with mock.patch.object(dm, 'module_ctx', side_effect=AssertionError('module_ctx')), \
                mock.patch.object(dm, 'read_secrets', side_effect=AssertionError('read_secrets')), \
                mock.patch.object(spaces, 'home', side_effect=AssertionError('spaces.home')):
            tracker.legacy_ctx('https://demo.atlassian.example', 'alpha@example.com', 'tok-test-1')

    def test_legacy_ctx_without_a_config_is_tracker_unconfigured(self):
        for args in ((None, None, None), (None, 'alpha@example.com', 'tok-test-1')):
            with self.assertRaises(dm.ModuleError) as cm:
                tracker.legacy_ctx(*args)
            self.assertEqual((cm.exception.code, cm.exception.status), ('tracker-unconfigured', 409))
            self.assertEqual(cm.exception.message, tracker.UNCONFIGURED)

    def test_legacy_module_is_the_builtin_jira_tracker(self):
        m = tracker.legacy_module()
        self.assertEqual((m.id, m.status, m.roles), ('jira-tracker', 'ok', ['tracker']))
        for fn in ('check', 'statuses'):
            self.assertTrue(callable(m.fn(fn)), fn)

    def test_legacy_module_not_loaded_is_module_error(self):
        broken = mock.Mock(status='broken')
        for cat in ({}, {'jira-tracker': broken}):
            with mock.patch.object(dm, 'catalog', return_value=cat):
                with self.assertRaises(dm.ModuleError) as cm:
                    tracker.legacy_module()
                self.assertEqual(cm.exception.code, 'module-error')
        with mock.patch.object(dm, 'catalog', side_effect=RuntimeError('boom')):
            with self.assertRaises(dm.ModuleError) as cm:
                tracker.legacy_module()
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertNotIn('boom', cm.exception.message)

    def test_end_to_end_the_module_with_the_legacy_ctx(self):
        """Справжній вбудований модуль із `legacy_ctx` (шов `_open` — записувач): адреса, пошта й токен ідуть з конфігу."""
        m = tracker.legacy_module()
        seen = []

        def fake(req, timeout):
            seen.append((req.full_url, timeout, dict(req.header_items())))

            class R:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self, n=-1):
                    return json.dumps({'issues': [{'key': 'DEMO-1', 'fields': {'status': {
                        'name': 'Done', 'statusCategory': {'key': 'done'}}}}]}).encode()
            return R()
        ctx = tracker.legacy_ctx('https://demo.atlassian.example', 'alpha@example.com', 'tok-test-1', space_id='liga')
        with mock.patch.dict(m.fn('check').__globals__, {'_open': fake}):
            out = tracker.statuses(m, ctx, ['DEMO-1'], timeout=tracker.READ_TIMEOUT, socket_s=tracker.READ_SOCKET_S)
        self.assertEqual(out, {'DEMO-1': {'name': 'Done', 'cat': 'done'}})
        self.assertEqual([(u, t) for u, t, _ in seen], [('https://demo.atlassian.example/rest/api/3/search/jql', 4)])


# ------------------------------------------------------------------------------- Task 4: синк дашборда через `tracker`

#: Вигадані облікові Jira ЛІГИ (`install_config.jira_config` у тестах підмінено на них: справжніх файлів і оточення не читаємо).
JIRA_CFG = (JIRA, 'alpha@example.com', 'tok-test-1')
#: Запис реєстру ЛІГИ (як `spaces` віддає для простору з `legacy`).
LEAGUE = {'id': 'liga', 'path': '', 'legacy': True, 'integrations': True}
#: Вигадана «тека-фікстура» в `registry._temp_roots`: тимчасові теки тестів не мають вважатись фікстурами (як у генераторі знімка).
FAKE_TMP = '/deai-fixture-tmp'


class _StubResp:
    """Відповідь-заглушка шва `_open` модуля `jira-tracker`: контекстний менеджер із `status` і `read`."""

    def __init__(self, body):
        self._body = json.dumps(body).encode('utf-8')
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        return self._body


def _strip(card):
    return {k: v for k, v in card.items() if k not in VOLATILE}


#: Фейковий трекер: пише в `log_file` ключі й бюджет сокета кожного виклику, віддає `{ключ: {name, cat}}`; `fail` — текст помилки.
FAKE_TRACKER = (tm.CHECK_ONLY + """
import json
def statuses(ctx, keys):
    with open(ctx['settings']['log_file'], 'a', encoding='utf-8') as fh:
        fh.write(json.dumps({'keys': keys, 'timeout_s': ctx.get('timeout_s')}) + '\\n')
    if ctx['settings'].get('fail'):
        raise ctx['ModuleError']('tracker-error', message=ctx['settings']['fail'])
    return {k: {'name': 'Fake ' + k, 'cat': 'done'} for k in keys}
""")
#: Фейковий дашборд: дописує кожен `push` рядком JSON у `log_file` (за ним тест бачить, ЩО поїхало).
FAKE_DASH = (tm.CHECK_ONLY + """
import json
def rows(ctx):
    return []
def push(ctx, cards, mode):
    with open(ctx['settings']['log_file'], 'a', encoding='utf-8') as fh:
        fh.write(json.dumps({'mode': mode, 'cards': cards}) + '\\n')
    return {'ok': len(cards), 'failed': {}}
""")
_LOG_SETTING = [{'key': 'log_file', 'type': 'text', 'label': 'Log file (test)', 'required': True}]
_FAIL_SETTING = [{'key': 'fail', 'type': 'text', 'label': 'Fail with this text (test)'}]


class SyncStatuses(tm.Env):
    """Синк дашборда бере статуси в постачальника ролі `tracker` ЦЬОГО простору (4c-2, Task 4): ЛІГА — вбудований `jira-tracker`
    з адресою з `jira_base`, звичайний простір — свій модуль; нема постачальника чи конфігу — кроку нема. Збій трекера — рядок
    у лозі (до 4c-2 Jira мовчала). Усе без мережі: шов `_open` модуля / `call`-запис / фейкові модулі."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def setUp(self):
        super().setUp()
        os.environ['DEAI_HOME'] = self.deai          # як у `TrackerRole`: статичний охоронець шукає присвоєння в самому файлі
        patch = mock.patch.object(registry, '_temp_roots', return_value=[FAKE_TMP])
        patch.start()
        self.addCleanup(patch.stop)

    def real_builtins(self):
        """Шлях ЛІГИ: справжній `jira-tracker` з `app/modules` (а не тека фікстур `Env`)."""
        self.addCleanup(dm.reset_caches)
        patch = mock.patch.object(dm, 'builtin_dir', _REAL_BUILTIN)
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()

    def world(self):
        """`cfg` знімка: теки задач у тимчасовій теці, `iterations.json` — як у генераторі знімка."""
        tasks = {}
        for tid, task in self.snap['sync_cards']['input']['tasks'].items():
            tdir = os.path.join(self.tmp, 'work', tid)
            tm._write(os.path.join(tdir, 'iterations.json'),
                      {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00', 'published': False}], 'publish_url': None})
            tasks[tid] = dict(task, dir=tdir)
        return {'current': 't1', 'tasks': tasks}

    def run_league(self, open_fn=None, jira_config=JIRA_CFG):
        """`cmd_sync` ЛІГИ: простір `LEAGUE`, дашборд — запис `call` (`push`), реєстр — порожній, Jira — шов `_open`. Повертає
        `(лог, [{'mode', 'cards'}], [запити до Jira])`."""
        self.real_builtins()
        reqs, lines, pushes = [], [], []
        stub = self.snap['jira_request']['request']['stub_response']

        def fake_open(req, timeout):
            reqs.append({'method': req.get_method(), 'url': req.full_url, 'body': json.loads(req.data.decode('utf-8')),
                         'headers': {k.lower(): v for k, v in req.header_items()}, 'timeout': timeout})
            return _StubResp(stub)

        def call(module, name, ctx, *args, **kw):
            assert name == 'push', name
            cards, mode = args
            pushes.append({'mode': mode, 'cards': [_strip(c) for c in cards]})
            return {'ok': len(cards), 'failed': {}}
        cfg = self.world()
        mod = tracker.legacy_module()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(ov, '_space', lambda sid: LEAGUE))
            st.enter_context(mock.patch.object(ov, '_target', lambda sp: (object(), {}, True)))
            st.enter_context(mock.patch.object(ov, '_tasks_of', lambda sp: cfg))
            st.enter_context(mock.patch.object(ov, 'discover_projects', lambda c: {}))
            st.enter_context(mock.patch.object(dashboard, '_identity', lambda: ('Alpha', 'alpha@example.com')))
            st.enter_context(mock.patch.object(install_config, 'jira_config', lambda: jira_config))
            st.enter_context(mock.patch.dict(mod.fn('check').__globals__, {'_open': open_fn or fake_open}))
            ov.cmd_sync(call=call, log=lines.append)
        return lines, pushes, reqs

    # ---- паритет ЛІГИ зі знімком 0.12.0
    def test_the_league_cards_and_modes_are_the_0_12_0_snapshot(self):
        lines, pushes, reqs = self.run_league()
        want = self.snap['sync_cards']
        self.assertEqual(pushes, want['pushes'])                 # ті самі картки (з `jira_status*` на t1/t2) і той самий `merge`
        self.assertEqual(lines, want['log'])
        self.assertEqual(len(reqs), 1)

    def test_the_league_request_is_the_0_12_0_request_but_to_jira_base(self):
        """Запит модуля = запит знімка (метод, шлях, тіло, заголовки, сокет 15 с); адреса — з `jira_base`, а не з коду."""
        _, _, reqs = self.run_league()
        want = self.snap['jira_request']['request']['calls'][0]
        got = reqs[0]
        self.assertEqual((got['method'], got['url']), (want['method'], JIRA + want['path']))
        self.assertEqual(got['body']['fields'], want['body']['fields'])
        self.assertEqual(got['body']['maxResults'], want['body']['maxResults'])
        # ключі — валідні ключі задач файла (знімок питав лише DEMO-1/DEMO-2; тут sync питає про всі задачі, у т.ч. DEMO-9)
        self.assertEqual(got['body']['jql'], 'key in (DEMO-1,DEMO-2,DEMO-9)')
        self.assertEqual((got['headers']['accept'], got['headers']['content-type']),
                         (want['headers']['accept'], want['headers']['content-type']))
        self.assertTrue(got['headers']['authorization'].startswith('Basic '))
        self.assertEqual(got['timeout'], want['timeout'])        # 15 с — `SYNC_SOCKET_S`

    def test_a_failing_tracker_differs_from_0_12_0_only_by_the_log_line(self):
        """Збій Jira: картки БЕЗ `jira_status` (наявні статуси не затираються, а не `None`) — як у знімку; єдина свідома
        відмінність — рядок у лозі (раніше збій мовчав)."""
        def down(req, timeout):
            raise OSError('connection refused: tok-test-1')
        lines, pushes, _ = self.run_league(open_fn=down)
        want = self.snap['sync_cards']['statuses_raises']
        self.assertEqual(pushes, want['pushes'])
        self.assertTrue(all('jira_status' not in c for p in pushes for c in p['cards']))
        self.assertEqual(lines, ['⚠ overview: статуси трекера недоступні: Jira недосяжна (OSError)'] + want['log'])
        self.assertNotIn('tok-test-1', ' '.join(lines))

    def test_the_league_without_jira_base_has_no_statuses_and_no_network(self):
        """Конфігу Jira нема (`jira_base` у `tasks.json` не задано): крок пропущено, мережі й виклику модуля нема, синк іде далі."""
        def boom(req, timeout):
            raise AssertionError('мережа: Jira без конфігу не питається')
        lines, pushes, reqs = self.run_league(open_fn=boom, jira_config=(None, None, None))
        self.assertEqual(reqs, [])
        self.assertEqual(lines, self.snap['sync_cards']['log'])      # жодного рядка про Jira: «не налаштовано» — не збій
        cards = [c for p in pushes for c in p['cards']]
        self.assertEqual(len(cards), 4)
        self.assertTrue(all('jira_status' not in c for c in cards))

    def test_the_real_install_config_without_jira_base_is_the_same(self):
        """Те саме на справжньому `install_config.jira_config` (тимчасові HOME і `tasks.json` без `jira_base`)."""
        self.real_builtins()
        tm._write(self.legacy, {'tasks': {}})
        with mock.patch.object(tracker, 'statuses', side_effect=AssertionError('виклик трекера')):
            cb = ov._statuses(LEAGUE)
        self.assertIsNone(cb)

    # ---- звичайний простір
    def regular_space(self, with_tracker=True, fail=None):
        """Простір без інтеграцій із фейковим дашбордом і (за потреби) фейковим трекером; `(запис, лог дашборда, лог трекера)`."""
        sp = self.new_space('Plain')
        dash_log, trk_log = self.hp('dash.log'), self.hp('trk.log')
        self.mk('fake-dash', roles=('dashboard',), server=FAKE_DASH, settings=_LOG_SETTING)
        dm.write_module_state(sp, 'fake-dash', enabled=True, settings={'log_file': dash_log})
        if with_tracker:
            self.mk('fake-trk', roles=('tracker',), server=FAKE_TRACKER, settings=_LOG_SETTING + _FAIL_SETTING)
            dm.write_module_state(sp, 'fake-trk', enabled=True,
                                  settings=dict({'log_file': trk_log}, **({'fail': fail} if fail else {})))
        return sp, dash_log, trk_log

    def run_regular(self, sp):
        lines = []
        cfg = self.world()
        with mock.patch.object(ov, '_tasks_of', lambda s: cfg), \
                mock.patch.object(dashboard, '_identity', lambda: ('Alpha', 'alpha@example.com')):
            ov.cmd_sync(sp['id'], log=lines.append)
        return lines

    @staticmethod
    def jsonl(path):
        try:
            with open(path, encoding='utf-8') as f:
                return [json.loads(ln) for ln in f if ln.strip()]
        except OSError:
            return []

    def test_a_regular_space_gets_jira_status_from_its_tracker_module(self):
        sp, dash_log, trk_log = self.regular_space()
        lines = self.run_regular(sp)
        cards = {c['id']: c for p in self.jsonl(dash_log) for c in p['cards']}
        self.assertEqual(sorted(cards), ['t1', 't2', 't3', 't4'])
        self.assertEqual((cards['t1']['jira_status'], cards['t1']['jira_status_cat']), ('Fake DEMO-1', 'done'))
        self.assertEqual(cards['t4']['jira_status'], 'Fake DEMO-9')
        self.assertNotIn('jira_status', cards['t3'])                    # задача без ключа
        # ядро шле лише валідні ключі (без `None` задачі без `jira`) і дає модулю сокет синку (15 с)
        self.assertEqual(self.jsonl(trk_log), [{'keys': ['DEMO-1', 'DEMO-2', 'DEMO-9'], 'timeout_s': tracker.SYNC_SOCKET_S}])
        self.assertEqual(lines, ['✅ overview: синхронізовано 4 проєктів'])

    def test_a_regular_space_tracker_failure_is_a_log_line_not_silence(self):
        sp, dash_log, _ = self.regular_space(fail='Jira відповіла HTTP 503')
        lines = self.run_regular(sp)
        self.assertEqual(lines[0], '⚠ overview: статуси трекера недоступні: Jira відповіла HTTP 503')
        cards = [c for p in self.jsonl(dash_log) for c in p['cards']]
        self.assertEqual(len(cards), 4)
        self.assertTrue(all('jira_status' not in c for c in cards))      # статуси не затираються: поля нема, а не `None`

    def test_a_space_without_a_tracker_module_has_no_statuses_and_no_call(self):
        sp, dash_log, trk_log = self.regular_space(with_tracker=False)
        seen = []
        real = dashboard.sync
        with mock.patch.object(dashboard, 'sync', lambda *a, **kw: seen.append(kw['statuses']) or real(*a, **kw)), \
                mock.patch.object(tracker, 'statuses', side_effect=AssertionError('виклик трекера')):
            lines = self.run_regular(sp)
        self.assertEqual(seen, [None])
        self.assertEqual(self.jsonl(trk_log), [])
        self.assertEqual(lines, ['✅ overview: синхронізовано 4 проєктів'])
        self.assertTrue(all('jira_status' not in c for p in self.jsonl(dash_log) for c in p['cards']))

    # ---- хелпер `_statuses`
    def test_the_callback_uses_the_sync_budgets(self):
        sp, _, _ = self.regular_space()
        prov = dm.provider('tracker', sp)
        with mock.patch.object(tracker, 'statuses', return_value={}) as st:
            cb = ov._statuses(sp)
            cb(['DEMO-1'])
        (module, ctx, keys), kw = st.call_args
        self.assertEqual((module.id, keys), (prov.id, ['DEMO-1']))
        self.assertEqual((kw['timeout'], kw['socket_s']), (tracker.SYNC_TIMEOUT, tracker.SYNC_SOCKET_S))

    def test_a_role_that_cannot_be_resolved_is_none_with_a_log_line(self):
        """Простір з зламаним `space.json`/нечитаним реєстром: колбека нема, синк іде далі, а причина — у лозі (не мовчки)."""
        lines = []
        for exc in (dm.ModuleError('space-json-unreadable', message='space.json: broken'),
                    dm.ModuleError('module-error', message='x' * 500),
                    spaces.SpacesError('spaces-unreadable', '/nowhere/spaces.json'),
                    RuntimeError('несподіваний збій: tok-test-1')):         # будь-що інше — теж не валить синк
            with mock.patch.object(dm, 'provider', side_effect=exc):
                self.assertIsNone(ov._statuses({'id': 'p', 'path': '/nowhere'}, log=lines.append))
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(ln.startswith('⚠ overview: статуси трекера недоступні: ') for ln in lines), lines)
        self.assertLessEqual(max(len(ln) for ln in lines), len('⚠ overview: статуси трекера недоступні: ') + 200)
        # ⛔ чужий виняток — лише назва класу (його `str` не чищений від секретів)
        self.assertEqual(lines[3], '⚠ overview: статуси трекера недоступні: RuntimeError')
        self.assertNotIn('tok-test-1', ' '.join(lines))

    def test_cmd_sync_passes_the_callback_for_any_space(self):
        """`statuses=_statuses(sp, log)` — і для ЛІГИ, і для звичайного простору (раніше — лише `legacy`)."""
        for legacy in (True, False):
            seen = []
            sentinel = object()
            with mock.patch.object(ov, '_space', lambda sid: {'id': 's', 'legacy': legacy}), \
                    mock.patch.object(ov, '_target', lambda sp: (object(), {}, legacy)), \
                    mock.patch.object(ov, '_tasks_of', lambda sp: {'tasks': {}}), \
                    mock.patch.object(ov, 'discover_projects', lambda c: {}), \
                    mock.patch.object(ov, '_statuses', lambda sp, log=print: sentinel), \
                    mock.patch.object(dashboard, 'sync', lambda *a, **kw: seen.append(kw['statuses'])):
                ov.cmd_sync()
            self.assertEqual(seen, [sentinel], f'legacy={legacy}')

    # ---- крок 2 `dashboard.sync` напряму
    def sync_with(self, statuses):
        lines = []
        cfg = self.world()
        dashboard.sync(cfg, object(), {}, statuses=statuses, identity=('Alpha', 'alpha@example.com'), log=lines.append,
                       call=lambda module, name, ctx, *a, **kw: {'ok': len(a[0]), 'failed': {}})
        return lines

    def test_the_failure_line_text_is_the_module_error_message_else_the_class_name_up_to_200(self):
        head = '⚠ overview: статуси трекера недоступні: '
        cases = ((dm.ModuleError('tracker-error', message='Jira відповіла HTTP 502'), 'Jira відповіла HTTP 502'),
                 (dm.ModuleError('tracker-error', message='m' * 300), 'm' * 200),
                 (dm.ModuleError('tracker-error'), 'ModuleError'),            # порожнє повідомлення — назва класу
                 (RuntimeError('boom tok-test-1'), 'RuntimeError'),            # ⛔ чужий виняток: без `str(e)` (не чищений)
                 (RuntimeError(), 'RuntimeError'))
        for exc, text in cases:
            def statuses(keys, exc=exc):
                raise exc
            lines = self.sync_with(statuses)
            self.assertEqual(lines[0], head + text, repr(exc))
            self.assertEqual(lines[-1], '✅ overview: синхронізовано 4 проєктів')


class NoJiraCodeInThePusher(unittest.TestCase):
    """Jira з `bin/overview_push.py` пішла в модуль `jira-tracker`: нічого з цього там більше не лишилось."""

    def test_the_removed_names_are_gone(self):
        with open(os.path.join(ROOT, 'bin', 'overview_push.py'), encoding='utf-8') as f:
            text = f.read()
        for gone in ('_JIRA_BASE', 'jira_statuses', '_jira_creds', 'urllib.request', '_ssl_context'):
            self.assertFalse(gone in text, gone)           # не `assertNotIn`: той друкує весь файл при падінні
        self.assertIsNone(re.search(r'^\s*import\s+(?:[\w, ]*\b)?(?:base64|urllib)\b', text, re.M))
        for name in ('_JIRA_BASE', '_jira_creds', 'jira_statuses', '_ssl_context'):
            self.assertFalse(hasattr(ov, name), name)

