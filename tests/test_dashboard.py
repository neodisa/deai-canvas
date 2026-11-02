"""Командний дашборд як роль `dashboard` (етап 4c-1). Тут — тести ядра; знімок 0.11.0 — еталон паритету.

Task 1: лише знімок `tests/fixtures/dashboard/before-4c1.json` (його знімає `tests/make_before_4c1.py` на коді БЕЗ змін,
і більше він не переписується) та перевірка його форми. Тести паритету наступних задач читають цей JSON, а не переганяють
генератор.
"""
import json
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'dashboard', 'before-4c1.json')

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


if __name__ == '__main__':
    unittest.main()
