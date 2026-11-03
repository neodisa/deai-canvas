"""Статуси трекера як роль `tracker` (етап 4c-2). Тут — тести ядра й модуля; знімок 0.12.0 — еталон паритету.

Task 1: лише знімок `tests/fixtures/tracker/before-4c2.json` (його знімає `tests/make_before_4c2.py` на коді БЕЗ змін, і більше
він не переписується) та перевірка його форми. Тести паритету наступних задач читають цей JSON, а не переганяють генератор.
"""
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
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
        call = jr['request']['calls']
        self.assertEqual(len(call), 1, 'один запит на всі ключі')
        self.assertEqual(call[0]['method'], 'POST')
        self.assertEqual(call[0]['path'], '/rest/api/3/search/jql')
        self.assertEqual(call[0]['headers']['authorization'], '<basic>')
        self.assertEqual(call[0]['body']['jql'], 'key in (DEMO-1,DEMO-2)', 'унікальні ключі, порожні відкинуто')
        self.assertEqual(jr['request']['result']['DEMO-1'], {'name': 'In Review', 'cat': 'indeterminate'})
        self.assertEqual(jr['no_credentials'], {'result': {}, 'urlopen_calls': 0})
        self.assertEqual(jr['network_error']['result'], {})

    def test_sync_cards_shape(self):
        sc = self.snap['sync_cards']
        self.assertEqual(sorted(sc), ['input', 'log', 'pushes', 'statuses_asked', 'summary'])
        self.assertEqual(sc['statuses_asked'], [['DEMO-1', 'DEMO-2']])
        self.assertEqual(len(sc['pushes']), 1)
        self.assertEqual(sc['pushes'][0]['mode'], 'merge')
        cards = {c['id']: c for c in sc['pushes'][0]['cards']}
        self.assertEqual(cards['t1']['jira_status'], 'In Review')
        self.assertEqual(cards['t2']['jira_status_cat'], 'done')

    def test_tasks_overview_shape(self):
        to = self.snap['tasks_overview']
        self.assertEqual(to['status'], 200)
        self.assertEqual(sorted(to['body']), ['current', 'mine', 'space', 'team'])
        self.assertEqual(sorted(to['volatile']), ['fetchedAt', 'rowsAt'])
        self.assertEqual(to['body']['mine'][0]['jiraStatus'], 'In Review')
        self.assertEqual(to['body']['team']['rows'][0]['jiraCat'], 'indeterminate')

    def test_no_volatile_fields_or_paths(self):
        # Вихід (тіло відповіді, картки синку) без мінливого; `volatile` (лише ТИПИ вирізаних полів), `meta` (їх перелік) і
        # `input_rows` (вхідні рядки-заглушки: там `updated_at` є за задумом) не перевіряються.
        outputs = {'sync_cards': self.snap['sync_cards']['pushes'], 'tasks_overview': self.snap['tasks_overview']['body'],
                   'jira_request': self.snap['jira_request']}
        for path, key, _ in walk(outputs):
            with self.subTest(path=path, key=key):
                self.assertNotIn(key, VOLATILE)
        text = json.dumps(self.snap)
        for needle in ('/var/', '/tmp', '/Users/', 'before-4c2-'):
            self.assertNotIn(needle, text, 'у знімку нема абсолютних шляхів')


if __name__ == '__main__':
    unittest.main()
