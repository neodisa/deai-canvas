"""CLI структури сторінок — єдиний спосіб, яким Claude міняє pages.json."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(BIN), 'app'))
import pages_model as pm  # noqa: E402
CLI = os.path.join(BIN, 'pages.py')


def run(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, '-B', CLI, *args], capture_output=True,
                          text=True, cwd=cwd, env=env)


class PagesCli(unittest.TestCase):
    def setUp(self):
        self.task = tempfile.mkdtemp(prefix='pcli-')
        self.addCleanup(shutil.rmtree, self.task, True)
        self.it = os.path.join(self.task, 'iterations', 'it1')
        os.makedirs(os.path.join(self.it, 'p'))
        with open(os.path.join(self.it, 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': [{'id': 'p', 'name': 'Картка', 'kind': 'page', 'children': [
                {'id': 'w', 'name': 'Віджет', 'kind': 'folder', 'isGroup': True}]}]}, fh)

    def pages(self):
        with open(os.path.join(self.it, 'pages.json'), encoding='utf-8') as fh:
            return json.load(fh)['pages']

    def cli(self, cmd, *args):
        return run(cmd, '--task-dir', self.task, '--it', 'it1', *args)

    def set_tree(self, pages):
        with open(os.path.join(self.it, 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': pages}, fh)

    def test_add_state_into_widget_folder_keeps_the_rest(self):
        r = run('add', '--task-dir', self.task, '--it', 'it1', '--kind', 'state',
                '--into', 'w', '--name', 'Помилка')
        self.assertEqual(r.returncode, 0, r.stderr)
        new_id = json.loads(r.stdout)['id']
        w = self.pages()[0]['children'][0]
        self.assertEqual([c['id'] for c in w['children']], [new_id])
        self.assertTrue(os.path.isfile(os.path.join(self.it, new_id, 'index.html')))

    def test_rule_violation_exits_nonzero_with_code_and_changes_nothing(self):
        before = self.pages()
        r = run('add', '--task-dir', self.task, '--it', 'it1', '--kind', 'state', '--name', 'X')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('state-outside-page', r.stderr)
        self.assertEqual(self.pages(), before)

    def test_list_prints_tree_with_ids_and_kinds(self):
        r = run('list', '--task-dir', self.task, '--it', 'it1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('p  [page]  Картка', r.stdout)
        self.assertIn('  w  [folder]  Віджет', r.stdout)

    def test_move_and_kind(self):
        run('add', '--task-dir', self.task, '--it', 'it1', '--kind', 'state', '--into', 'p', '--name', 'S')
        sid = self.pages()[0]['children'][1]['id']
        r = run('move', '--task-dir', self.task, '--it', 'it1', '--id', sid, '--into', 'w')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.pages()[0]['children'][0]['children'][0]['id'], sid)
        r = run('kind', '--task-dir', self.task, '--it', 'it1', '--id', sid, '--kind', 'page')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {'id': sid, 'kind': 'page'})
        node = self.pages()[0]['children'][0]['children'][0]
        self.assertEqual((node['id'], node['kind']), (sid, 'page'))

    def test_add_after_puts_the_node_right_after_the_sibling(self):
        """`--after` ставить новий вузол одразу ПІСЛЯ сусіда, а не в кінець батька."""
        self.set_tree([{'id': 'a', 'name': 'A', 'kind': 'page'},
                       {'id': 'b', 'name': 'B', 'kind': 'page'},
                       {'id': 'c', 'name': 'C', 'kind': 'page'}])
        r = self.cli('add', '--kind', 'page', '--name', 'Нова', '--after', 'a')
        self.assertEqual(r.returncode, 0, r.stderr)
        nid = json.loads(r.stdout)['id']
        self.assertEqual([p['id'] for p in self.pages()], ['a', nid, 'b', 'c'])
        self.assertTrue(os.path.isfile(os.path.join(self.it, nid, 'index.html')))

    def test_add_folder_after_a_nested_sibling_lands_in_its_parent(self):
        r = self.cli('add', '--kind', 'folder', '--name', 'Нова тека', '--after', 'w')
        self.assertEqual(r.returncode, 0, r.stderr)
        fid = json.loads(r.stdout)['id']
        self.assertEqual([c['id'] for c in self.pages()[0]['children']], ['w', fid])
        self.assertFalse(os.path.exists(os.path.join(self.it, fid)))   # тека без каталогу

    def test_move_after_counts_position_without_the_moved_node(self):
        """Індекс `op_move` — серед дітей ПІСЛЯ виймання. Перенос уперед у межах
        одного батька (a → після c) з індексом «до виймання» ставив би a перед c."""
        self.set_tree([{'id': 'a', 'name': 'A', 'kind': 'page'},
                       {'id': 'b', 'name': 'B', 'kind': 'page'},
                       {'id': 'c', 'name': 'C', 'kind': 'page'},
                       {'id': 'd', 'name': 'D', 'kind': 'page'}])
        r = self.cli('move', '--id', 'a', '--after', 'c')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p['id'] for p in self.pages()], ['b', 'c', 'a', 'd'])

    def test_move_after_itself_is_refused(self):
        before = self.pages()
        r = self.cli('move', '--id', 'p', '--after', 'p')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error bad-position', r.stderr)
        self.assertEqual(self.pages(), before)

    def test_move_with_unknown_after_is_not_found_and_changes_nothing(self):
        before = self.pages()
        r = self.cli('move', '--id', 'w', '--after', 'nope')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error not-found', r.stderr)
        self.assertEqual(self.pages(), before)

    def test_rename_changes_only_the_name(self):
        r = self.cli('rename', '--id', 'w', '--name', '  Новий  ')
        self.assertEqual(r.returncode, 0, r.stderr)
        w = self.pages()[0]['children'][0]
        self.assertEqual((w['name'], w['kind']), ('Новий', 'folder'))

    def test_rename_unknown_id_fails_with_code(self):
        r = self.cli('rename', '--id', 'nope', '--name', 'X')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error not-found', r.stderr)

    def test_missing_iteration_fails_with_code_not_a_traceback(self):
        r = run('list', '--task-dir', self.task, '--it', 'it99')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error ', r.stderr)
        self.assertNotIn('Traceback', r.stderr)

    def test_corrupt_pages_json_is_refused_and_left_untouched(self):
        path = os.path.join(self.it, 'pages.json')
        with open(path, 'w') as fh:
            fh.write('{не json')
        r = self.cli('add', '--kind', 'page', '--name', 'X')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error corrupt', r.stderr)
        with open(path) as fh:
            self.assertEqual(fh.read(), '{не json')

    # ---- рев'ю A5 ----
    def test_move_needs_exactly_one_target(self):
        """Без цілі `move` мовчки кидав вузол у кінець кореня; тепер — явний вибір."""
        self.set_tree([{'id': 'a', 'name': 'A', 'kind': 'page', 'children': [
                           {'id': 'k', 'name': 'K', 'kind': 'page'}]},
                       {'id': 'b', 'name': 'B', 'kind': 'page'}])
        before = self.pages()
        for args in ((), ('--into', 'b', '--after', 'a'), ('--root', '--into', 'b'),
                     ('--root', '--after', 'a')):
            with self.subTest(args=args):
                r = self.cli('move', '--id', 'k', *args)
                self.assertEqual(r.returncode, 2)
                self.assertIn('error bad-position', r.stderr)
                self.assertEqual(self.pages(), before)

    def test_move_root_puts_the_node_at_the_end_of_the_root_and_reports_it(self):
        self.set_tree([{'id': 'a', 'name': 'A', 'kind': 'page', 'children': [
                           {'id': 'k', 'name': 'K', 'kind': 'page'}]},
                       {'id': 'b', 'name': 'B', 'kind': 'page'}])
        r = self.cli('move', '--id', 'k', '--root')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout),
                         {'id': 'k', 'parent': None, 'index': 2, 'changed': True})
        self.assertEqual([p['id'] for p in self.pages()], ['a', 'b', 'k'])

    def test_move_reports_changed_false_when_nothing_moves(self):
        self.set_tree([{'id': 'a', 'name': 'A', 'kind': 'page'},
                       {'id': 'b', 'name': 'B', 'kind': 'page'}])
        r = self.cli('move', '--id', 'b', '--after', 'a')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout),
                         {'id': 'b', 'parent': None, 'index': 1, 'changed': False})
        self.assertFalse(os.path.exists(os.path.join(self.it, 'pages.json.bak')))

    def test_move_into_own_descendant_is_cycle(self):
        before = self.pages()
        r = self.cli('move', '--id', 'p', '--into', 'w')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error cycle', r.stderr)
        self.assertEqual(self.pages(), before)

    def test_add_into_with_after_of_another_parent_is_bad_position(self):
        before = self.pages()
        r = self.cli('add', '--kind', 'page', '--name', 'X', '--into', 'w', '--after', 'p')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error bad-position', r.stderr)
        self.assertEqual(self.pages(), before)

    def test_add_into_with_after_of_the_same_parent_is_fine(self):
        r = self.cli('add', '--kind', 'folder', '--name', 'F', '--into', 'p', '--after', 'w')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_add_after_writes_once_so_bak_is_the_state_before(self):
        """Два записи лишали в .bak проміжний стан (вузол у кінці батька)."""
        self.set_tree([{'id': 'a', 'name': 'A', 'kind': 'page'},
                       {'id': 'b', 'name': 'B', 'kind': 'page'}])
        path = os.path.join(self.it, 'pages.json')
        with open(path, 'rb') as fh:
            before = fh.read()
        r = self.cli('add', '--kind', 'page', '--name', 'N', '--after', 'a')
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(path + '.bak', 'rb') as fh:
            self.assertEqual(fh.read(), before)

    def test_rename_and_kind_print_json(self):
        r = self.cli('rename', '--id', 'w', '--name', ' Нове ')
        self.assertEqual(json.loads(r.stdout), {'id': 'w', 'name': 'Нове'})
        r = self.cli('kind', '--id', 'p', '--kind', 'page')
        self.assertEqual(json.loads(r.stdout), {'id': 'p', 'kind': 'page'})

    def test_list_on_corrupt_pages_json_is_corrupt(self):
        with open(os.path.join(self.it, 'pages.json'), 'w') as fh:
            fh.write('{не json')
        r = self.cli('list')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error corrupt', r.stderr)

    def test_bad_iteration_name_is_refused_before_touching_disk(self):
        for it in ('..', '../x', 'a/b', '.', ''):
            with self.subTest(it=it):
                r = run('list', '--task-dir', self.task, '--it', it)
                self.assertEqual(r.returncode, 2)
                self.assertIn('error bad-iteration', r.stderr)

    def test_os_error_is_error_io_not_a_traceback(self):
        os.chmod(os.path.join(self.it, 'pages.json'), 0o000)
        self.addCleanup(os.chmod, os.path.join(self.it, 'pages.json'), 0o644)
        if os.access(os.path.join(self.it, 'pages.json'), os.R_OK):
            self.skipTest('root читає й без прав')
        r = self.cli('list')
        self.assertEqual(r.returncode, 2)
        self.assertIn('error io', r.stderr)
        self.assertNotIn('Traceback', r.stderr)

    def test_missing_required_flags_exit_2_with_argparse_message(self):
        r = run('add', '--task-dir', self.task, '--it', 'it1')
        self.assertEqual(r.returncode, 2)
        self.assertIn('required', r.stderr)

    # ---- лок покриває ВЕСЬ цикл читання-зміни-запису ----
    def _race(self, *args):
        """Тримаємо лок у тесті, стартуємо CLI, дописуємо вузол у pages.json,
        відпускаємо. Якщо CLI читав дерево до лока — наш вузол пропаде."""
        with pm.pages_lock(self.it):
            proc = subprocess.Popen([sys.executable, '-B', CLI, *args,
                                     '--task-dir', self.task, '--it', 'it1'],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(0.6)           # CLI має дійти до очікування лока
            pages = self.pages()
            pages.append({'id': 'late', 'name': 'Пізній', 'kind': 'page'})
            self.set_tree(pages)
        out, err = proc.communicate(timeout=20)
        self.assertEqual(proc.returncode, 0, err)
        return [p['id'] for p in self.pages()]

    def test_add_reads_the_tree_under_the_lock(self):
        ids = self._race('add', '--kind', 'page', '--name', 'Нова')
        self.assertIn('late', ids)
        self.assertEqual(len(ids), 3)

    def test_rename_reads_the_tree_under_the_lock(self):
        ids = self._race('rename', '--id', 'p', '--name', 'Інше')
        self.assertIn('late', ids)

    def test_a_held_lock_past_the_timeout_is_busy(self):
        env = dict(os.environ, DC_PAGES_LOCK_TIMEOUT='0.2')
        before = self.pages()
        t0 = time.monotonic()
        with pm.pages_lock(self.it):
            r = run('add', '--task-dir', self.task, '--it', 'it1', '--kind', 'page',
                    '--name', 'X', env=env)
        # справжній таймаут — 10 с: без перевірки часу env міг би ігноруватися
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual(r.returncode, 2)
        self.assertIn('error busy', r.stderr)
        self.assertEqual(self.pages(), before)


if __name__ == '__main__':
    unittest.main()
