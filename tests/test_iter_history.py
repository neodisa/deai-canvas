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


if __name__ == '__main__':
    unittest.main()
