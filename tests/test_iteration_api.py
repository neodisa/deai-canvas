"""Фаза И: видалення ітерації в кошик, повернення, номер без повторів, 409 на останню, історія й коміт AI (Task 2, 4)."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

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
        self.assertTrue(body['iteration']['label_text'].startswith('Іт.2'), body['iteration'])   # тост «Повернено як…»

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

    def test_merge_pages_does_not_reuse_trashed_number(self):
        self.post('/api/iteration', {'from': 'it1', 'note': 'Третя'})          # it3
        self.post('/api/iteration-delete', {'id': 'it3'})
        st, body = self.post('/api/pages-from-iterations', {'itIds': ['it1', 'it2']})
        self.assertEqual((st, body['iteration']), (200, 'it4'))

    def test_delete_purges_old_slots(self):
        old = os.path.join(self.x_dir, '.trash', 'iterations', 'it5--20200101-100000')
        os.makedirs(os.path.join(old, 'files'))
        self.post('/api/iteration-delete', {'id': 'it2'})
        self.assertFalse(os.path.exists(old))

    def test_delete_survives_purge_failure(self):
        with mock.patch('iter_trash.purge', side_effect=ValueError('x')):
            st, body = self.post('/api/iteration-delete', {'id': 'it2'})
        self.assertEqual((st, body['ok']), (200, True))

    def test_delete_save_failure_leaves_iteration_live(self):
        with mock.patch('serve.save_meta', side_effect=OSError('disk')):
            st, body = self.post_raw('/api/iteration-delete', {'id': 'it2'})
        self.assertEqual(st, 500)
        self.assertEqual(self.ids(), ['it1', 'it2'])
        self.assertTrue(os.path.isfile(os.path.join(self.x_dir, 'iterations', 'it2', 'index.html')))
        root = os.path.join(self.x_dir, '.trash', 'iterations')
        self.assertEqual(os.listdir(root) if os.path.isdir(root) else [], [])

    def test_restore_save_failure_keeps_iteration_in_trash(self):
        _, d = self.post('/api/iteration-delete', {'id': 'it2'})
        with mock.patch('serve.save_meta', side_effect=OSError('disk')):
            st, _ = self.post_raw('/api/iteration-restore', {'trash': d['trash']})
        self.assertEqual(st, 500)
        self.assertEqual(self.ids(), ['it1'])
        self.assertFalse(os.path.exists(os.path.join(self.x_dir, 'iterations', 'it2')))
        self.assertTrue(os.path.isfile(os.path.join(self.x_dir, '.trash', 'iterations', d['trash'], 'files', 'index.html')))
        st, body = self.post('/api/iteration-restore', {'trash': d['trash']})   # повтор працює
        self.assertEqual((st, body['id']), (200, 'it2'))

    def test_restore_finish_failure_does_not_allow_a_second_restore(self):
        _, d = self.post('/api/iteration-delete', {'id': 'it2'})
        with mock.patch('iter_trash.shutil.rmtree', side_effect=OSError('boom')):
            st, body = self.post('/api/iteration-restore', {'trash': d['trash']})
        self.assertEqual((st, body['id']), (200, 'it2'))
        st, _ = self.post_raw('/api/iteration-restore', {'trash': d['trash']})
        self.assertEqual(st, 404)
        self.assertEqual(self.ids(), ['it1', 'it2'])

    def test_failed_rollback_is_reported(self):
        with mock.patch('serve.save_meta', side_effect=OSError('disk')), \
                mock.patch('iter_trash.undo_move', side_effect=OSError('stuck')), \
                mock.patch('sys.stderr'):
            st, body = self.post('/api/iteration-delete', {'id': 'it2'})
        self.assertEqual((st, body['error'], body['rolled_back']), (500, 'delete-failed', False))

    def test_successful_rollback_is_reported(self):
        with mock.patch('serve.save_meta', side_effect=OSError('disk')):
            st, body = self.post('/api/iteration-delete', {'id': 'it2'})
        self.assertEqual((st, body['rolled_back']), (500, True))


class HistoryAndAi(_Base):
    def test_history_route(self):
        self.post('/api/iteration-rename', {'id': 'it2', 'label': 'Фільтри'})
        st, body = self.jget('/api/iteration-history?id=it2')
        self.assertEqual(st, 200)
        self.assertEqual(body['id'], 'it2')
        self.assertEqual([e['kind'] for e in body['entries']][:2], ['rename', 'copy'])
        self.assertIn('pending', body)

    def test_history_route_errors(self):
        st, _ = self.jget('/api/iteration-history?id=../x')
        self.assertEqual(st, 400)
        st, body = self.jget('/api/iteration-history?id=it9')
        self.assertEqual((st, body['error']), (404, 'iteration-not-found'))

    def test_autosync_commits_ai_edits_without_gitlab(self):
        with open(os.path.join(self.x_dir, 'iterations', 'it2', 'index.html'), 'a', encoding='utf-8') as f:
            f.write('<p>AI</p>')
        st, body = self.post('/api/autosync', {})
        self.assertEqual((st, body['reason']), (200, 'no-gitlab'))
        self.assertEqual(body['ai']['it'], 'it2')
        log = _git(self.x_dir, 'log', '-1', '--format=%s%n%b')
        self.assertIn('it2: зміни AI', log)
        self.assertIn('Deai-Actor: ai', log)
        _, h = self.jget('/api/iteration-history?id=it2')
        self.assertEqual(h['entries'][0]['actor'], {'kind': 'ai', 'name': 'AI'})

    def test_autosync_clean_tree_makes_no_commit(self):
        before = _git(self.x_dir, 'rev-parse', 'HEAD')
        _, body = self.post('/api/autosync', {})
        self.assertIsNone(body['ai'])
        self.assertEqual(_git(self.x_dir, 'rev-parse', 'HEAD'), before)

    def test_ai_commit_failure_does_not_break_hook(self):
        with mock.patch.object(serve, 'ai_commit', side_effect=OSError('boom')), \
                mock.patch.object(sys, 'stderr', new=mock.MagicMock()):
            st, body = self.post('/api/autosync', {})
        self.assertEqual((st, body['reason'], body['ai']), (200, 'no-gitlab', None))

    def test_publish_subject_carries_iteration_ids(self):
        """Тема коміту публікації несе id опублікованих ітерацій (власність для історії). Драйвимо `/api/publish`
        без node: гілка `no-node` комітить так само, як і основна."""
        meta = _meta(self.x_dir)
        for i in meta['iterations']:
            i['published'] = True
        with open(os.path.join(self.x_dir, 'iterations.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f)
        subjects = []
        real = serve.git_autocommit
        with mock.patch.object(serve.deai_modules, 'provider', return_value=mock.MagicMock()), \
                mock.patch.object(serve.deai_modules, 'publish_legacy_path', return_value=True), \
                mock.patch.object(serve, '_node_bin', return_value=None), \
                mock.patch.object(serve, 'git_autocommit', side_effect=lambda d, m, *a, **k: subjects.append(m) or real(d, m, *a, **k)):
            self.post('/api/publish', {})
        pub = [m for m in subjects if m.startswith('publish:')]
        self.assertEqual(pub, ['publish: 2 iteration(s) · it1 it2'])

    # ---- фаза И, раунд виправлень: обсяг AI-коміту, чесний успіх, стійкість маршруту історії
    def edit(self, it, name='index.html', text='<p>AI</p>', mtime=None):
        path = os.path.join(self.x_dir, 'iterations', it, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(text)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def status(self):
        return _git(self.x_dir, 'status', '--porcelain', '--untracked-files=all')

    def test_only_own_iterations_are_committed_never_foreign_or_other_files(self):
        """M1: чужа ітерація й сторонній файл лишаються незакоміченими, коміт не торкається їх."""
        meta = _meta(self.x_dir)
        meta['iterations'].append({'id': 'it3', 'date': '23.11.2026 12:00', 'note': 'чужа', 'author': 'Other',
                                   'author_key': 'other@example.com'})
        with open(os.path.join(self.x_dir, 'iterations.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f)
        self.edit('it3', text='<p>foreign</p>')
        self.edit('it2')
        with open(os.path.join(self.x_dir, 'notes.txt'), 'w', encoding='utf-8') as f:
            f.write('stray')
        st, body = self.post('/api/autosync', {})
        self.assertEqual((st, body['ai']['it'], body['ai']['its']), (200, 'it2', ['it2']))
        files = _git(self.x_dir, 'show', '--name-only', '--format=', 'HEAD').split()
        self.assertEqual(files, ['iterations/it2/index.html'])
        left = self.status()
        self.assertIn('iterations/it3/index.html', left)       # чужа лишилась брудною
        self.assertIn('notes.txt', left)                       # (d) сторонній файл не потрапив у коміт
        self.assertNotIn('iterations/it2', left)

    def test_two_own_dirty_iterations_make_two_commits_freshest_last(self):
        """M4: найстарша — першим комітом, найсвіжіша — останнім; `it` називає найсвіжішу."""
        import time
        now = time.time()        # у майбутньому: файли копії ітерації мають менший mtime, ніж ці правки
        self.edit('it1', mtime=now + 1000)
        self.edit('it2', mtime=now + 2000)
        st, body = self.post('/api/autosync', {})
        self.assertEqual((body['ai']['it'], body['ai']['its']), ('it2', ['it1', 'it2']))
        subjects = _git(self.x_dir, 'log', '-2', '--format=%s').split('\n')
        self.assertEqual(subjects[:2], ['it2: зміни AI', 'it1: зміни AI'])
        self.assertEqual(_git(self.x_dir, 'rev-parse', '--short', 'HEAD').strip(), body['ai']['sha'])

    def test_ai_commit_is_never_pushed(self):
        """M6: з origin і вимкненим автосинком origin не рухається, локальний HEAD — рухається."""
        origin = os.path.join(self.deai, 'origin-bare')
        subprocess.run(['git', 'init', '-q', '--bare', origin], check=True)
        _git(self.x_dir, 'remote', 'add', 'origin', origin)
        _git(self.x_dir, 'push', '-q', '-u', 'origin', 'HEAD')
        before = _git(origin, 'rev-parse', 'HEAD')
        local = _git(self.x_dir, 'rev-parse', 'HEAD')
        self.edit('it2')
        st, body = self.post('/api/autosync', {})
        self.assertEqual((st, body['reason']), (200, 'no-gitlab'))
        self.assertNotEqual(_git(self.x_dir, 'rev-parse', 'HEAD'), local)
        self.assertEqual(_git(origin, 'rev-parse', 'HEAD'), before)

    def test_gitless_task_is_not_labelled_ai_and_gets_no_repo(self):
        shutil.rmtree(os.path.join(self.x_dir, '.git'))
        self.edit('it2')
        st, body = self.post('/api/autosync', {})
        self.assertEqual((st, body['ai']), (200, None))
        self.assertFalse(os.path.exists(os.path.join(self.x_dir, '.git')))

    def test_no_false_success_when_head_did_not_move(self):
        self.edit('it2')
        head = _git(self.x_dir, 'rev-parse', '--short', 'HEAD').strip()
        with mock.patch.object(serve, 'git_autocommit', return_value={'sha': head, 'pushed': False}):
            self.assertIsNone(serve.ai_commit({'dir': self.x_dir}))

    def test_history_route_survives_broken_meta(self):
        with open(os.path.join(self.x_dir, 'iterations.json'), 'w', encoding='utf-8') as f:
            f.write('{не json')
        st, body = self.jget('/api/iteration-history?id=it2')
        self.assertEqual((st, body['ok'], body['error'], body['degraded']), (200, False, 'meta-unreadable', True))
        self.assertEqual((body['entries'], body['pending']), ([], None))

    def test_history_route_survives_entry_without_id(self):
        meta = _meta(self.x_dir)
        meta['iterations'].insert(0, {'note': 'без id'})
        with open(os.path.join(self.x_dir, 'iterations.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f)
        st, body = self.jget('/api/iteration-history?id=it2')
        self.assertEqual((st, body['ok']), (200, True))

    def test_git_autocommit_with_paths_commits_only_them(self):
        self.edit('it2')
        with open(os.path.join(self.x_dir, 'notes.txt'), 'w', encoding='utf-8') as f:
            f.write('stray')
        _git(self.x_dir, 'add', 'notes.txt')                     # навіть ЗАСТЕЙДЖЕНЕ стороннє не входить
        serve.git_autocommit(self.x_dir, 'only it2', push=False, paths=['iterations/it2/'])
        self.assertEqual(_git(self.x_dir, 'show', '--name-only', '--format=', 'HEAD').split(), ['iterations/it2/index.html'])
        self.assertIn('A  notes.txt', self.status())


if __name__ == '__main__':
    unittest.main()
