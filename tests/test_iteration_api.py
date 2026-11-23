"""Фаза И: видалення ітерації в кошик, повернення, номер без повторів, 409 на останню, історія й коміт AI (Task 2, 4)."""
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _meta(d):
    with open(os.path.join(d, 'iterations.json'), encoding='utf-8') as f:
        return json.load(f)


def _git(d, *args):
    return subprocess.run(['git', *args], cwd=d, capture_output=True, text=True).stdout


class _Base(base.Fixture):
    """Без тестів: лише стенд. Класи нижче успадковують ЙОГО, а не один одного — інакше тести бігли б двічі."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Стенд уже ізолює DEAI_HOME (тимчасова тека, повертається в його tearDownClass); присвоєння тут — для
        # охоронця test_serve, що шукає його у САМОМУ файлі (ізоляція через успадкований стенд йому невидима).
        os.environ['DEAI_HOME'] = cls.deai

    def setUp(self):
        super().setUp()
        spaces.switch_space(self.p_id)                      # простір P, поточна задача — `x`
        shutil.rmtree(self.x_dir, ignore_errors=True)
        base._task_dir(self.x_dir, 'x')
        self.post('/api/iteration', {'from': 'it1', 'note': 'Друга'})     # it2

    def ids(self):
        return [i['id'] for i in _meta(self.x_dir)['iterations']]


class IterationApi(_Base):
    def test_delete_moves_to_trash_and_returns_slot(self):
        st, body = self.post('/api/iteration-delete', {'id': 'it2'})
        self.assertEqual(st, 200)
        self.assertTrue(body['ok'] and body['deleted'] == 'it2' and body['trash'].startswith('it2--'))
        self.assertEqual(self.ids(), ['it1'])
        self.assertFalse(os.path.exists(os.path.join(self.x_dir, 'iterations', 'it2')))
        self.assertTrue(os.path.isdir(os.path.join(self.x_dir, '.trash', 'iterations', body['trash'], 'files')))

    def test_trash_is_not_committed(self):
        self.post('/api/iteration-delete', {'id': 'it2'})
        tracked = _git(self.x_dir, 'ls-files')
        self.assertNotIn('.trash/', tracked)
        with open(os.path.join(self.x_dir, '.gitignore'), encoding='utf-8') as f:
            self.assertIn('.trash/', f.read().splitlines())

    def test_restore_puts_it_back_in_order(self):
        self.post('/api/iteration', {'from': 'it1', 'note': 'Третя'})         # it3
        _, d = self.post('/api/iteration-delete', {'id': 'it2'})
        st, body = self.post('/api/iteration-restore', {'trash': d['trash']})
        self.assertEqual((st, body['ok'], body['id'], body['renamed']), (200, True, 'it2', False))
        self.assertEqual(self.ids(), ['it1', 'it2', 'it3'])
        self.assertIn('restore iteration it2', _git(self.x_dir, 'log', '-1', '--format=%s'))

    def test_new_iteration_does_not_reuse_trashed_number(self):
        self.post('/api/iteration-delete', {'id': 'it2'})
        _, body = self.post('/api/iteration', {'from': 'it1', 'note': 'Нова'})
        self.assertEqual(body['iteration']['id'], 'it3')

    def test_last_iteration_is_refused(self):
        self.post('/api/iteration-delete', {'id': 'it2'})
        st, body = self.post('/api/iteration-delete', {'id': 'it1'})
        self.assertEqual((st, body['error']), (409, 'last-iteration'))
        self.assertEqual(self.ids(), ['it1'])

    def test_restore_errors(self):
        st, _ = self.post_raw('/api/iteration-restore', {'trash': '../x'})
        self.assertEqual(st, 400)
        st, body = self.post('/api/iteration-restore', {'trash': 'it9--20261123-100000'})
        self.assertEqual((st, body['error']), (404, 'not-in-trash'))

    def test_unknown_iteration_still_404(self):
        st, _ = self.post_raw('/api/iteration-delete', {'id': 'it9'})
        self.assertEqual(st, 404)


if __name__ == '__main__':
    unittest.main()
