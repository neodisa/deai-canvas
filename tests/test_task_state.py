"""`app/task_state.py`: легкий стан задачі, спільний для пушера (bin/overview_push.py)
і сервера (екран «Задачі»). Функція ніколи не кидає виняток — тека може бути
знесена, `iterations.json` — зіпсований руками, `pages.json` — відсутній.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
from task_state import task_state  # noqa: E402


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False)


class TaskState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='task-state-')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_counts_openable_pages_of_last_iteration(self):
        d = os.path.join(self.tmp, 'task')
        _write(os.path.join(d, 'iterations.json'), {
            'iterations': [{'id': 'it1', 'date': '01.10.2026'},
                           {'id': 'it2', 'date': '02.10.2026'}],
            'publish_url': 'https://example.test/p',
            'gitlab': {'synced_at': '2026-10-02T10:00:00+03:00'},
        })
        # старіша ітерація: 1 сторінка — лічильник її НЕ має брати (береться остання)
        _write(os.path.join(d, 'iterations', 'it1', 'pages.json'),
               {'pages': [{'id': 'old', 'name': 'Стара', 'kind': 'page'}]})
        # остання: home (сторінка) + s1 (її стан) + тека grp (НЕ рахується) + inner
        # (сторінка в теці) + about (сторінка) → 4 відкриваних, теку не рахуємо
        _write(os.path.join(d, 'iterations', 'it2', 'pages.json'), {'pages': [
            {'id': 'home', 'name': 'Головна', 'kind': 'page',
             'children': [{'id': 's1', 'name': 'Стан', 'kind': 'state'}]},
            {'id': 'grp', 'name': 'Тека', 'kind': 'folder', 'isGroup': True,
             'children': [{'id': 'inner', 'name': 'Вкладена', 'kind': 'page'}]},
            {'id': 'about', 'name': 'Про нас', 'kind': 'page'},
        ]})

        st = task_state({'dir': d, 'figma': 'https://figma.test/x'})

        self.assertEqual(st['iterations'], 2)
        self.assertEqual(st['pages'], 4)
        self.assertIs(st['published'], True)
        self.assertEqual(st['code_url'], 'https://example.test/p')
        self.assertEqual(st['last_iter'], 'it2')
        self.assertIs(st['dir_exists'], True)
        self.assertEqual(st['figma'], 'https://figma.test/x')
        self.assertEqual(st['backup_at'], '2026-10-02T10:00:00+03:00')

    def test_missing_dir_gives_zeros_and_never_raises(self):
        st = task_state({'dir': os.path.join(self.tmp, 'нема-такої-теки')})
        self.assertIs(st['dir_exists'], False)
        self.assertEqual(st['iterations'], 0)
        self.assertEqual(st['pages'], 0)
        self.assertIs(st['published'], False)
        self.assertIsNone(st['code_url'])
        self.assertIsNone(st['last_iter'])

    def test_task_without_dir_does_not_read_cwd(self):
        """Порожній/відсутній `dir` не має читати `iterations.json` з cwd процесу:
        `os.path.join('', 'iterations.json')` — це файл у поточній теці, і сервер
        показав би чужу задачу як «порожню» задачу без теки."""
        trap = os.path.join(self.tmp, 'cwd')
        _write(os.path.join(trap, 'iterations.json'), {
            'iterations': [{'id': 'it1'}, {'id': 'it2'}, {'id': 'it3'}],
            'publish_url': 'https://example.test/trap',
        })
        was = os.getcwd()
        self.addCleanup(os.chdir, was)
        os.chdir(trap)
        for task in ({}, {'dir': ''}, {'dir': None}):
            with self.subTest(task=task):
                st = task_state(task)
                self.assertIs(st['dir_exists'], False)
                self.assertEqual(st['iterations'], 0)
                self.assertEqual(st['pages'], 0)
                self.assertIs(st['published'], False)
                self.assertIsNone(st['code_url'])
                self.assertIsNone(st['last_iter'])

    def test_broken_iterations_json_gives_zeros_and_never_raises(self):
        d = os.path.join(self.tmp, 'task')
        _write(os.path.join(d, 'iterations.json'), '{ це не JSON')
        st = task_state({'dir': d})
        self.assertIs(st['dir_exists'], True)       # тека є, зіпсований лише файл
        self.assertEqual(st['iterations'], 0)
        self.assertEqual(st['pages'], 0)
        self.assertIs(st['published'], False)
        self.assertIsNone(st['code_url'])
        self.assertIsNone(st['last_iter'])

    def test_valid_json_of_wrong_shape_never_raises(self):
        """Сервер кличе task_state на КОЖЕН запит екрана «Задачі»: виняток тут —
        це 500 на весь екран. Валідний JSON не тієї форми (правили руками)
        мусить дати нулі, а не AttributeError."""
        shapes = {
            'корінь — список': ('[]', 0),
            'корінь — null': ('null', 0),
            'iterations — рядок': ('{"iterations": "x"}', 0),
            'iterations — обʼєкт': ('{"iterations": {"id": "it1"}}', 0),
            'iterations — не обʼєкти': ('{"iterations": [1, 2]}', 0),
            'частина ітерацій — не обʼєкти': ('{"iterations": [1, {"id": "it2"}, null]}', 2),
            'gitlab — рядок': ('{"iterations": [{"id": "it1"}], "gitlab": "x"}', 1),
        }
        for name, (raw, want_iters) in shapes.items():
            with self.subTest(name):
                d = os.path.join(self.tmp, 'task')
                _write(os.path.join(d, 'iterations.json'), raw)
                st = task_state({'dir': d})
                self.assertIs(st['dir_exists'], True)
                self.assertEqual(st['iterations'], want_iters)
                self.assertEqual(st['pages'], 0)
                self.assertIs(st['published'], False)
                self.assertIsNone(st['code_url'])
                self.assertIsNone(st['backup_at'])

    def test_malformed_task_never_raises(self):
        """Запис у tasks.json теж могли зіпсувати: `dir` не рядок, задача не обʼєкт."""
        for task in ({'dir': 5}, {'dir': ['a']}, None, 'x'):
            with self.subTest(task=task):
                st = task_state(task)
                self.assertIs(st['dir_exists'], False)
                self.assertEqual(st['iterations'], 0)

    def test_last_iteration_without_id_does_not_raise(self):
        """Пушер не має падати на ітерації без `id` (iter_count її переживає)."""
        d = os.path.join(self.tmp, 'task')
        _write(os.path.join(d, 'iterations.json'), {'iterations': [{'note': 'без id'}]})
        st = task_state({'dir': d})
        self.assertEqual(st['iterations'], 1)       # фолбек iter_count — довжина списку
        self.assertIsNone(st['last_iter'])


if __name__ == '__main__':
    unittest.main()
