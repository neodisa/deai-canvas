"""Статуси трекера як роль `tracker` (етап 4c-2). Тут — тести ядра й модуля; знімок 0.12.0 — еталон паритету.

Task 1: лише знімок `tests/fixtures/tracker/before-4c2.json` (його знімає `tests/make_before_4c2.py` на коді БЕЗ змін, і більше
він не переписується) та перевірка його форми. Тести паритету наступних задач читають цей JSON, а не переганяють генератор.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402
import install_config  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_modules as tm  # noqa: E402  (каркас `Env`: тимчасові HOME/DEAI_HOME, тека модулів-фікстур)
import tracker  # noqa: E402

_REAL = None


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
        self.assertEqual(dm.ROLES_CALLED, ('publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker'))
        self.assertEqual(dm.ROLES_RESERVED, ('notify',))
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
