"""Історія ітерації з git теки задачі (фаза И, Р8): фільтр, таблиця тем, трейлер AI, незаписані зміни."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import iter_history as ih  # noqa: E402


def git(d, *a, env=None):
    e = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'Олена Д.', 'GIT_AUTHOR_EMAIL': 'o@example.com',
         'GIT_COMMITTER_NAME': 'Олена Д.', 'GIT_COMMITTER_EMAIL': 'o@example.com', **(env or {})}
    r = subprocess.run(['git', *a], cwd=d, capture_output=True, text=True, env=e)
    return r.stdout.strip()


def write(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)


def commit(d, msg):
    git(d, 'add', '-A')
    git(d, 'commit', '-q', '-m', msg)
    return git(d, 'rev-parse', '--short', 'HEAD')


class History(unittest.TestCase):
    def setUp(self):
        # модуль сам кличе git: ізолюємо його від ~/.gitconfig так само, як помічник тестів
        env = mock.patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'})
        env.start()
        self.addCleanup(env.stop)
        self.d = tempfile.mkdtemp(prefix='ihist-')
        self.addCleanup(shutil.rmtree, self.d, True)
        git(self.d, 'init', '-q')
        write(self.d, 'iterations/it1/index.html', 'a')
        self.c1 = commit(self.d, 'iteration it1: Перша')
        write(self.d, 'iterations/it2/index.html', 'b')
        self.c2 = commit(self.d, 'iteration it2: копія it1 · Друга')
        write(self.d, 'iterations/it2/filters.css', 'c')
        write(self.d, 'iterations/it2/data.js', 'd')
        commit(self.d, 'it2: зміни AI\n\nDeai-Actor: ai')
        write(self.d, 'iterations/it1/index.html', 'a2')
        commit(self.d, 'page main: rename')                       # чіпає лише it1
        write(self.d, 'iterations.json', '{}')
        commit(self.d, 'rename iteration it2: Фільтри')            # лише iterations.json, id у темі
        write(self.d, 'iterations/it2/pages.json', '[]')
        commit(self.d, 'page filters: new in it2')
        write(self.d, 'iterations.json', '{"p":1}')
        commit(self.d, 'publish: 1 iteration(s) · it2')

    def test_entries_for_it2_newest_first(self):
        out = ih.history(self.d, {'id': 'it2', 'git': self.c2}, {'filters': 'Фільтри'})
        kinds = [e['kind'] for e in out['entries']]
        self.assertEqual(kinds, ['publish', 'page-new', 'rename', 'ai', 'copy'])
        self.assertFalse(out['degraded'])
        self.assertIsNone(out['pending'])

    def test_args_and_actor(self):
        es = {e['kind']: e for e in ih.history(self.d, {'id': 'it2', 'git': self.c2}, {'filters': 'Фільтри'})['entries']}
        self.assertEqual(es['copy']['args'], {'from': 'it1', 'note': 'Друга'})
        self.assertEqual(es['rename']['args'], {'name': 'Фільтри'})
        self.assertEqual(es['page-new']['args'], {'page': 'filters', 'name': 'Фільтри'})
        self.assertEqual(es['ai']['actor'], {'kind': 'ai', 'name': 'AI'})
        self.assertEqual(es['copy']['actor'], {'kind': 'person', 'name': 'Олена Д.'})
        self.assertEqual(sorted(es['ai']['files']), ['data.js', 'filters.css'])
        self.assertRegex(es['ai']['at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

    def test_other_iteration_commits_excluded(self):
        texts = [e['text'] for e in ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['entries']]
        self.assertNotIn('page main: rename', texts)

    def test_creation_commit_cuts_older_history(self):
        # it1 «видалили» й створили знову з тим самим номером: коміти до нового створення — не її
        write(self.d, 'iterations/it1/index.html', 'new')
        c = commit(self.d, 'iteration it1: Нова перша')
        out = ih.history(self.d, {'id': 'it1', 'git': c}, {})
        self.assertEqual([e['kind'] for e in out['entries']], ['create'])

    def test_creation_commit_cuts_by_full_sha_too(self):
        write(self.d, 'iterations/it1/index.html', 'new')
        c = commit(self.d, 'iteration it1: Нова перша')
        full = git(self.d, 'rev-parse', 'HEAD')
        out = ih.history(self.d, {'id': 'it1', 'git': full}, {})
        self.assertEqual([e['kind'] for e in out['entries']], ['create'])
        self.assertEqual(out['entries'][0]['sha'], c)

    def test_id_token_does_not_match_longer_id(self):
        write(self.d, 'iterations/it10/index.html', 'x')
        commit(self.d, 'iteration it10: Десята')
        texts = [e['text'] for e in ih.history(self.d, {'id': 'it1', 'git': self.c1}, {})['entries']]
        self.assertNotIn('iteration it10: Десята', texts)
        self.assertIn('iteration it1: Перша', texts)

    def test_id_token_requires_left_boundary(self):
        write(self.d, 'iterations/it1/q.html', 'q')
        commit(self.d, 'preit2 щось')
        texts = [e['text'] for e in ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['entries']]
        self.assertNotIn('preit2 щось', texts)

    def test_files_capped(self):
        for i in range(8):
            write(self.d, f'iterations/it2/f{i}.css', str(i))
        commit(self.d, 'it2: зміни AI\n\nDeai-Actor: ai')
        e = ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['entries'][0]
        self.assertEqual((len(e['files']), e['more']), (5, 3))

    def test_pending_lists_dirty_files(self):
        write(self.d, 'iterations/it2/new.html', 'x')
        p = ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['pending']
        self.assertEqual(p['files'], ['new.html'])
        self.assertRegex(p['at'], r'^\d{4}-\d{2}-\d{2}T')

    def test_dirty_iterations(self):
        write(self.d, 'iterations/it1/x.html', 'x')
        write(self.d, 'iterations/it2/y.html', 'y')
        self.assertEqual(ih.dirty_iterations(self.d), {'it1', 'it2'})

    def test_no_git_is_degraded_with_creation_from_meta(self):
        d = tempfile.mkdtemp(prefix='ihist-nogit-')
        self.addCleanup(shutil.rmtree, d, True)
        out = ih.history(d, {'id': 'it1', 'date': '21.11.2026 18:40', 'author': 'Олена Д.', 'note': 'Старт'}, {})
        self.assertTrue(out['degraded'])
        self.assertEqual(out['entries'][0]['kind'], 'create')
        self.assertEqual(out['entries'][0]['actor'], {'kind': 'person', 'name': 'Олена Д.'})

    def test_unknown_subject_is_other_trimmed(self):
        write(self.d, 'iterations/it2/z.html', 'z')
        commit(self.d, 'щось своє ' + 'x' * 200)
        e = ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['entries'][0]
        self.assertEqual(e['kind'], 'other')
        self.assertEqual(len(e['text']), 120)


class Ownership(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'})
        env.start()
        self.addCleanup(env.stop)
        self.d = tempfile.mkdtemp(prefix='ihist-own-')
        self.addCleanup(shutil.rmtree, self.d, True)
        git(self.d, 'init', '-q')
        for n in ('it1', 'it2', 'it3'):
            write(self.d, f'iterations/{n}/index.html', n)
        self.base = commit(self.d, 'seed')

    def hist(self, iid, names=None):
        return ih.history(self.d, {'id': iid}, names or {})

    def empty_commit(self, subject, body=''):
        git(self.d, 'commit', '-q', '--allow-empty', '-m', subject + (('\n\n' + body) if body else ''))

    def texts(self, iid):
        return [e['text'] for e in self.hist(iid)['entries']]

    def test_copy_source_not_owner(self):
        self.empty_commit('iteration it2: копія it1 · як в it3')
        self.assertNotIn('iteration it2: копія it1 · як в it3', self.texts('it1'))
        self.assertNotIn('iteration it2: копія it1 · як в it3', self.texts('it3'))
        e = self.hist('it2')['entries'][0]
        self.assertEqual((e['kind'], e['args']), ('copy', {'from': 'it1', 'note': 'як в it3'}))

    def test_merge_sources_not_owners_and_args(self):
        self.empty_commit('iteration it3: pages from it1, it2')
        self.empty_commit('iteration it3: pages from it1,it2')
        self.assertFalse([x for x in self.texts('it1') if x.startswith('iteration it3')])
        es = self.hist('it3')['entries']
        self.assertEqual([(e['kind'], e['args']) for e in es[:2]], [('merge', {'from': ['it1', 'it2']})] * 2)

    def test_free_text_not_owner(self):
        self.empty_commit('rename iteration it2: Як it1 але краще')
        self.assertNotIn('rename iteration it2: Як it1 але краще', self.texts('it1'))
        self.assertIn('rename iteration it2: Як it1 але краще', self.texts('it2'))

    def test_publish_ids_and_old_subject(self):
        self.empty_commit('publish: 2 iteration(s) · it1 it3')
        self.empty_commit('publish: 1 iteration(s)')
        self.assertIn('publish: 2 iteration(s) · it1 it3', self.texts('it3'))
        self.assertNotIn('publish: 2 iteration(s) · it1 it3', self.texts('it2'))
        self.assertNotIn('publish: 1 iteration(s)', self.texts('it1'))

    def test_delete_kind_owned(self):
        self.empty_commit('delete iteration it2')
        e = self.hist('it2')['entries'][0]
        self.assertEqual((e['kind'], e['args']), ('delete', {}))
        self.assertNotIn('delete iteration it2', self.texts('it1'))

    def test_page_and_tree_kinds(self):
        self.empty_commit('page a: new in it1')
        self.empty_commit('page a: rename')
        self.empty_commit('page a: move')
        self.empty_commit('tree: reorder')
        es = self.hist('it1', {'a': 'Альфа'})['entries']
        by = {e['text']: e for e in es}
        self.assertEqual(by['page a: new in it1']['args'], {'page': 'a', 'name': 'Альфа'})
        self.assertNotIn('page a: rename', by)      # лише за шляхом
        self.assertNotIn('tree: reorder', by)

    def test_page_name_falls_back_to_id(self):
        self.empty_commit('page zz: new in it1')
        e = self.hist('it1')['entries'][0]
        self.assertEqual(e['args'], {'page': 'zz', 'name': 'zz'})

    def test_path_touching_kinds(self):
        for subj, kind in (('page a: rename', 'page-rename'), ('page a: move', 'page-move'), ('tree: x', 'tree'),
                           ('restore iteration it1', 'restore'), ('it1: автосинк (3)', 'sync'), ('щось', 'other')):
            write(self.d, 'iterations/it1/index.html', subj)
            commit(self.d, subj)
            e = self.hist('it1')['entries'][0]
            self.assertEqual(e['kind'], kind, subj)

    def test_empty_note_markers(self):
        self.empty_commit('iteration it1: без примітки')
        self.empty_commit('iteration it2: копія it1 · без примітки')
        self.assertEqual(self.hist('it1')['entries'][0]['args'], {'note': ''})
        self.assertEqual(self.hist('it2')['entries'][0]['args'], {'from': 'it1', 'note': ''})

    def test_other_falls_back_to_token_scan(self):
        self.empty_commit('щось про it2 та it20')
        self.assertIn('щось про it2 та it20', self.texts('it2'))
        self.assertNotIn('щось про it2 та it20', self.texts('it1'))

    def test_trailer_is_a_line(self):
        self.empty_commit('it1: щось', 'Це не Deai-Actor: ai а текст')
        self.empty_commit('it1: інше', 'Deai-Actor: air')
        self.empty_commit('it1: третє', 'Deai-Actor: ai')
        es = self.hist('it1')['entries']
        self.assertEqual([e['actor']['kind'] for e in es[:3]], ['ai', 'person', 'person'])

    def test_ai_subject_without_trailer_is_ai(self):
        self.empty_commit('it1: зміни AI')
        e = self.hist('it1')['entries'][0]
        self.assertEqual((e['kind'], e['actor']), ('ai', {'kind': 'ai', 'name': 'AI'}))

    def test_synced_for_ai_autosync(self):
        self.empty_commit('it1: автосинк (2)', 'Deai-Actor: ai')
        e = self.hist('it1')['entries'][0]
        self.assertEqual((e['kind'], e['args']['synced']), ('ai', True))

    def test_status_calls_use_no_optional_locks(self):
        calls = []

        def spy(cmd, **kw):
            calls.append(cmd)
            return subprocess.run(cmd, **kw)
        ih.history(self.d, {'id': 'it1'}, {}, run=spy)
        ih.dirty_iterations(self.d, run=spy)
        self.assertTrue(calls and all('--no-optional-locks' in c for c in calls))
        self.assertTrue(all('--no-renames' in c for c in calls))
        self.assertTrue(any(':(literal)iterations/it1/' in c for c in calls))

    def test_timeout_is_degraded_and_dirty_raises_oserror(self):
        def boom(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 1)
        out = ih.history(self.d, {'id': 'it1'}, {}, run=boom)
        self.assertTrue(out['degraded'])
        with self.assertRaises(OSError):
            ih.dirty_iterations(self.d, run=boom)

    def test_rename_across_iterations_in_both_histories(self):
        os.makedirs(os.path.join(self.d, 'iterations/it2'), exist_ok=True)
        git(self.d, 'mv', 'iterations/it1/index.html', 'iterations/it2/moved.html')
        self.assertEqual(ih.dirty_iterations(self.d), {'it1', 'it2'})
        git(self.d, 'commit', '-q', '-m', 'щось переніс')
        self.assertIn('щось переніс', self.texts('it1'))
        self.assertIn('щось переніс', self.texts('it2'))

    def test_dirty_fallback_dirs_only_and_parent_repo(self):
        os.makedirs(os.path.join(self.d, 'task/iterations/it1'))
        write(self.d, 'task/iterations/.DS_Store', 'x')
        task = os.path.join(self.d, 'task')        # власного .git немає, але батьківський репо є
        self.assertEqual(ih.dirty_iterations(task), {'it1'})
        out = ih.history(task, {'id': 'it1', 'date': '21.11.2026 18:40'}, {})
        self.assertTrue(out['degraded'])
        self.assertEqual([e['kind'] for e in out['entries']], ['create'])

    def test_pending_cap_other_iterations_and_unicode(self):
        for i in range(8):
            write(self.d, f'iterations/it1/f{i}.css', 'x')
        write(self.d, 'iterations/it2/other.html', 'x')
        p = self.hist('it1')['pending']
        self.assertEqual((len(p['files']), p['more']), (5, 3))
        self.assertEqual(p['files'], sorted(p['files']))
        self.assertTrue(all('other' not in f for f in p['files']))
        write(self.d, 'iterations/it3/файл.html', 'x')
        self.assertEqual(self.hist('it3')['pending']['files'], ['файл.html'])
        commit(self.d, 'щось в it3')
        self.assertEqual(self.hist('it3')['entries'][0]['files'], ['файл.html'])

    def test_non_utf8_subject_is_not_degraded(self):
        write(self.d, 'iterations/it1/raw.css', 'x')
        git(self.d, 'add', '-A')
        tree, head = git(self.d, 'write-tree'), git(self.d, 'rev-parse', 'HEAD')
        who = b'A <a@example.com> 1700000000 +0000'
        # `commit`/`commit-tree` самі перекодовують повідомлення; сирі не-UTF-8 байти в темі дає лише ручний обʼєкт
        raw = (b'tree ' + tree.encode() + b'\nparent ' + head.encode() + b'\nauthor ' + who + b'\ncommitter ' + who
               + b'\n\nit1: \xff\xfe raw\n')
        sha = subprocess.run(['git', 'hash-object', '-t', 'commit', '-w', '--literally', '--stdin'], cwd=self.d, input=raw,
                             capture_output=True).stdout.decode().strip()
        git(self.d, 'reset', '-q', '--soft', sha)
        out = self.hist('it1')
        self.assertFalse(out['degraded'])
        self.assertIn('\ufffd', out['entries'][0]['text'])

    def test_value_error_from_git_run_is_oserror(self):
        def boom(cmd, **kw):
            raise ValueError('embedded null')
        with self.assertRaises(OSError):
            ih.dirty_iterations(self.d, run=boom)

    def test_dirty_iterations_pathspec_is_literal(self):
        """Поведінкою `:(literal)` не довести: шлях `iterations/` без метасимволів, а глоб із косою рискою в кінці git у `status` не
        матчить узагалі (перевірено вручну). Тому стережемо сам аргумент: він захищає від майбутньої зміни шляху."""
        calls = []
        real = subprocess.run
        ih.dirty_iterations(self.d, run=lambda c, **kw: calls.append(c) or real(c, **kw))
        self.assertTrue(any(':(literal)iterations/' in c for c in calls))

    def test_files_sorted(self):
        for n in ('c', 'a', 'b'):
            write(self.d, f'iterations/it1/{n}.css', n)
        commit(self.d, 'x')
        self.assertEqual(self.hist('it1')['entries'][0]['files'], ['a.css', 'b.css', 'c.css'])


if __name__ == '__main__':
    unittest.main()
