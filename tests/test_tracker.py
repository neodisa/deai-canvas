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
