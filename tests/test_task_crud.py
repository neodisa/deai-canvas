"""Задачі простору, сервер (етап Д, 0.30.0, Task 2): маршрути `task-rename`, `task-delete`, `task-restore`, `task-purge`.

Фікстура — `test_spaces_serve.Fixture` (тимчасові HOME/DEAI_HOME/DC_TASKS_FILE): простір `P` має задачі `x` (тека, поточна) і
`gone` (теки нема), `E` порожній. ⛔ Справжній `~/.deai` не мусить змінитись (`spaces_guard`).
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_spaces_serve import Fixture, _read, _write, _md5  # noqa: E402  (модуль сам ставить app/ і bin/)
from test_tasks_overview import make_task, add_shot  # noqa: E402
import serve  # noqa: E402
import spaces_guard  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class TaskCrudApi(Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # `task-new` робить простір задачі поточним (запис реєстру): ізоляцію `DEAI_HOME` фіксуємо явно, як і охоронець файлів просторів
        os.environ['DEAI_HOME'] = cls.deai

    def snapshot_p(self):
        """Повернути tasks.json простору P, теку `x` і кошик у стан «до тесту»: тести видаляють, повертають, додають кадри."""
        self.restore_bytes(self.p_file)
        keep = tempfile.mkdtemp(prefix='crud-keep-')
        shutil.copytree(self.x_dir, os.path.join(keep, 'x'))

        def back():
            shutil.rmtree(os.path.join(self.p_path, '.deai-trash'), True)
            shutil.rmtree(self.x_dir, True)
            shutil.copytree(os.path.join(keep, 'x'), self.x_dir)
            shutil.rmtree(keep, True)
        self.addCleanup(back)

    # ── перейменування ──
    def test_rename_writes_only_title_in_the_task_space(self):
        self.snapshot_p()
        st, j = self.post('/api/task-rename', {'id': 'x', 'title': '  Нова назва  '})
        self.assertEqual((st, j), (200, {'ok': True, 'id': 'x', 'title': 'Нова назва'}))
        cfg = _read(self.p_file)
        self.assertEqual(cfg['tasks']['x']['title'], 'Нова назва')
        self.assertEqual(cfg['tasks']['x']['dir'], self.x_dir)        # id і тека ті самі

    def test_rename_refuses_empty_title_without_touching_disk(self):
        self.snapshot_p()
        before = _md5(self.p_file)
        for bad in ('', '   ', None, 5):
            st, j = self.post('/api/task-rename', {'id': 'x', 'title': bad})
            self.assertEqual((st, j['code']), (400, 'bad-title'), repr(bad))
        self.assertEqual(_md5(self.p_file), before)

    def test_rename_unknown_task_is_404(self):
        st, j = self.post('/api/task-rename', {'id': 'nope', 'title': 'X'})
        self.assertEqual((st, j['code']), (404, 'unknown-task'))

    def test_rename_cuts_title_to_200(self):
        self.snapshot_p()
        _st, j = self.post('/api/task-rename', {'id': 'x', 'title': 'я' * 300})
        self.assertEqual(len(j['title']), 200)

    # ── видалення ──
    def test_delete_moves_folder_and_reports_trash(self):
        self.snapshot_p()
        st, j = self.post('/api/task-delete', {'id': 'x'})
        self.assertEqual(st, 200)
        self.assertEqual(j['id'], 'x')
        self.assertEqual(j['trash']['title'], 'Ікс')
        cfg = _read(self.p_file)
        self.assertNotIn('x', cfg['tasks'])
        rec = cfg['trash']['x']
        self.assertFalse(os.path.exists(self.x_dir))
        self.assertTrue(os.path.isdir(rec['trashDir']))
        self.assertEqual(os.path.dirname(rec['trashDir']), os.path.join(self.p_path, '.deai-trash'))

    def test_delete_current_repoints_current(self):
        self.snapshot_p()
        _st, j = self.post('/api/task-delete', {'id': 'x'})
        self.assertEqual(j['current'], 'gone')                       # єдина інша задача простору
        self.assertEqual(_read(self.p_file)['current'], 'gone')

    def test_delete_failed_save_brings_folder_back(self):
        self.snapshot_p()
        with mock.patch.object(serve, 'save_tasks', side_effect=OSError('disk full')):
            st, j = self.post('/api/task-delete', {'id': 'x'})
        self.assertEqual((st, j['code']), (500, 'task-delete-failed'))
        self.assertTrue(os.path.isdir(self.x_dir))
        self.assertIn('x', _read(self.p_file)['tasks'])

    def test_delete_unknown_is_404(self):
        st, j = self.post('/api/task-delete', {'id': 'nope'})
        self.assertEqual((st, j['code']), (404, 'unknown-task'))

    # ── повернення ──
    def test_restore_round_trip(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j), (200, {'ok': True, 'id': 'x'}))
        cfg = _read(self.p_file)
        self.assertIn('x', cfg['tasks'])
        self.assertNotIn('x', cfg.get('trash', {}))
        self.assertTrue(os.path.isdir(self.x_dir))
        self.assertEqual(cfg['current'], 'gone', 'повернення поточну не міняє')

    def test_restore_refuses_when_folder_reappeared(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        os.makedirs(self.x_dir)
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (409, 'task-dir-exists'))
        self.assertIn('x', _read(self.p_file)['trash'])

    def test_restore_refuses_id_taken_in_another_space(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        if os.path.exists(self.e_file):
            self.restore_bytes(self.e_file)
        else:
            self.addCleanup(lambda: os.path.exists(self.e_file) and os.remove(self.e_file))
        _write(self.e_file, {'tasks': {'x': {'title': 'Чужий', 'dir': os.path.join(self.e_path, 'x')}}})
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (409, 'task-exists'))

    def test_restore_unknown_space_and_not_in_trash(self):
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': 'nope'})
        self.assertEqual((st, j['code']), (400, 'unknown-space'))
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (404, 'not-in-trash'))

    # ── знищення ──
    def test_purge_deletes_folder_and_keeps_tombstone(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        td = _read(self.p_file)['trash']['x']['trashDir']
        st, j = self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j), (200, {'ok': True, 'id': 'x'}))
        self.assertFalse(os.path.exists(td))
        self.assertIn('purged', _read(self.p_file)['trash']['x'])

    def test_purge_rmtree_failure_keeps_record(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        with mock.patch('task_trash.shutil.rmtree', side_effect=OSError('busy')):
            st, j = self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (500, 'task-purge-failed'))
        self.assertIn('entry', _read(self.p_file)['trash']['x'])

    def test_routes_are_registry_routes(self):
        for r in ('/api/task-rename', '/api/task-delete', '/api/task-restore', '/api/task-purge'):
            self.assertIn(r, serve.Handler._REGISTRY_ROUTES)

    # ── дозаписано за ревʼю Task 1 ──
    def test_delete_refuses_when_trash_record_with_same_id_is_live(self):
        self.snapshot_p()
        cfg = _read(self.p_file)
        cfg['trash'] = {'x': {'entry': {'title': 'Старий'}, 'dir': None, 'trashDir': None, 'at': '2026-01-01T00:00:00Z'}}
        _write(self.p_file, cfg)
        st, j = self.post('/api/task-delete', {'id': 'x'})
        self.assertEqual((st, j['code']), (409, 'task-in-trash'))
        self.assertTrue(os.path.isdir(self.x_dir))
        self.assertIn('x', _read(self.p_file)['tasks'])

    def test_rename_failed_save_is_500(self):
        self.snapshot_p()
        with mock.patch.object(serve, 'save_tasks', side_effect=OSError('disk full')):
            st, j = self.post('/api/task-rename', {'id': 'x', 'title': 'Нова'})
        self.assertEqual((st, j['code']), (500, 'task-rename-failed'))
        self.assertEqual(_read(self.p_file)['tasks']['x']['title'], 'Ікс')

    def test_purge_failed_save_is_500_and_retry_writes_tombstone(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        td = _read(self.p_file)['trash']['x']['trashDir']
        with mock.patch.object(serve, 'save_tasks', side_effect=OSError('disk full')):
            st, j = self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (500, 'task-purge-failed'))
        self.assertFalse(os.path.exists(td))
        self.assertIn('entry', _read(self.p_file)['trash']['x'])
        st, j = self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        self.assertEqual(st, 200)
        self.assertIn('purged', _read(self.p_file)['trash']['x'])

    # ── дозаписано за ревʼю Task 2 ──
    def test_restore_and_purge_with_non_string_id_are_404(self):
        for route in ('/api/task-restore', '/api/task-purge'):
            for bad in ([1], {'a': 1}, 5, None):
                st, j = self.post(route, {'id': bad, 'space': self.p_id})
                self.assertEqual((st, j['code']), (404, 'not-in-trash'), f'{route} {bad!r}')

    def test_restore_failed_save_puts_folder_back_into_trash(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        td = _read(self.p_file)['trash']['x']['trashDir']
        with mock.patch.object(serve, 'save_tasks', side_effect=OSError('disk full')):
            st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (500, 'task-restore-failed'))
        self.assertTrue(os.path.isdir(td))
        self.assertFalse(os.path.exists(self.x_dir))
        self.assertIn('entry', _read(self.p_file)['trash']['x'])

    def test_restore_ambiguous_task_is_task_exists(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        with mock.patch.object(serve.spaces, 'find_task', side_effect=serve.spaces.AmbiguousTask('x')):
            st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (409, 'task-exists'))
        self.assertIn('entry', _read(self.p_file)['trash']['x'])

    # ── кошик у екрані задач, кадр із кошика, id у кошику ──
    def test_overview_lists_trash_of_the_space(self):
        self.snapshot_p()
        serve.spaces.switch_space(self.p_id)
        self.post('/api/task-delete', {'id': 'x'})
        st, j = self.jget('/api/tasks-overview')
        self.assertEqual(st, 200)
        self.assertEqual([r['id'] for r in j['trash']], ['x'])
        row = j['trash'][0]
        self.assertEqual(row['title'], 'Ікс')
        self.assertTrue(row['at'].endswith('Z'))
        self.assertNotIn('x', [r['id'] for r in j['mine']])

    def test_overview_hides_tombstones(self):
        self.snapshot_p()
        serve.spaces.switch_space(self.p_id)
        self.post('/api/task-delete', {'id': 'x'})
        self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        _st, j = self.jget('/api/tasks-overview')
        self.assertEqual(j['trash'], [])

    def test_task_list_does_not_see_trash(self):
        self.snapshot_p()
        serve.spaces.switch_space(self.p_id)
        self.post('/api/task-delete', {'id': 'x'})
        _st, j = self.jget('/api/tasks')
        self.assertNotIn('x', [r['id'] for r in j['tasks']])

    def test_thumb_from_trash(self):
        self.snapshot_p()
        serve.spaces.switch_space(self.p_id)
        make_task(self.p_path, 'x', pages=['home'])
        add_shot({'dir': self.x_dir}, 'it1', 'home', sha='tr1')
        self.post('/api/task-delete', {'id': 'x'})
        _st, j = self.jget('/api/tasks-overview')
        url = j['trash'][0]['thumb']
        self.assertIn('trash=1', url)
        st, _body = self.get(url)
        self.assertEqual(st, 200)
        st, _body = self.get('/api/task-thumb?task=x')     # без trash=1 — живої задачі `x` нема
        self.assertEqual(st, 404)

    def test_new_task_refuses_an_id_in_trash_and_clears_a_tombstone(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        st, j = self.post('/api/task-new', {'id': 'x', 'title': 'X', 'space': self.p_id})
        self.assertEqual((st, j['code']), (400, 'task-in-trash'))
        self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        self.assertIn('x', _read(self.p_file)['trash'])          # надгробок є
        st, j = self.post('/api/task-new', {'id': 'x', 'title': 'X', 'space': self.p_id})
        self.assertEqual(st, 200, j)
        self.assertNotIn('x', _read(self.p_file).get('trash', {}))


if __name__ == '__main__':
    unittest.main()
