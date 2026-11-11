"""«Що нового» (0.23.0): `parse_changelog` (чиста функція) і `Updater.notes()` на викидних git-світах у тимчасових теках (remote — шлях
файлової системи, мережі нема). `notes()` лише `fetch` тега + `git show`: робоче дерево, індекс і HEAD не змінюються."""
import json
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import spaces_guard  # noqa: E402
import test_updater as tu  # noqa: E402
import test_updater_apply as ta  # noqa: E402
import updater  # noqa: E402

_REAL = None
SAMPLE = '# Changelog\n\n## [0.3.0] — 12.11.2026\n\nThree.\n\n### Added\n\n- c\n\n## [0.2.0] — 11.11.2026\n\nTwo.\n\n## [0.1.0] — 10.11.2026\n\nOne.\n'


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def changelog(*versions):
    return '# Changelog\n\n## [Unreleased]\n\nNext.\n\n' + ''.join(
        '## [%s] — 1%d.11.2026\n\nBody of %s.\n\n' % (v, i, v) for i, v in enumerate(versions))


class ParseChangelog(unittest.TestCase):
    def test_sections_between_current_exclusive_and_latest_inclusive(self):
        got = updater.parse_changelog(SAMPLE, after='0.1.0', upto='0.3.0')
        self.assertEqual([s['version'] for s in got], ['0.3.0', '0.2.0'])
        self.assertEqual(got[1]['date'], '11.11.2026')
        self.assertEqual(got[1]['body'], 'Two.')
        self.assertIn('### Added', got[0]['body'])

    def test_range_edges(self):
        self.assertEqual([s['version'] for s in updater.parse_changelog(SAMPLE, '0.2.0', '0.3.0')], ['0.3.0'])
        self.assertEqual([s['version'] for s in updater.parse_changelog(SAMPLE, '0.0.1', '0.2.0')], ['0.2.0', '0.1.0'])
        self.assertEqual(updater.parse_changelog(SAMPLE, '0.3.0', '0.3.0'), [])
        self.assertEqual(updater.parse_changelog(SAMPLE, 'unknown', '0.3.0'), [])

    def test_text_only_no_html_and_controls_stripped(self):
        text = '## [0.2.0] — 11.11.2026\n\n<script>alert(1)</script> a‮b​c\x00d\x1be\r\nline2\tx\n'
        body = updater.parse_changelog(text, '0.1.0', '0.2.0')[0]['body']
        self.assertIn('<script>alert(1)</script>', body)           # лишається ТЕКСТОМ (клієнт вставляє через textContent)
        self.assertEqual(body, '<script>alert(1)</script> abcde\nline2 x')

    def test_each_section_capped_and_total_capped(self):
        big = 'я' * 20000                                           # 2 байти на символ
        text = '## [0.2.0] — 11.11.2026\n\n%s\n\n' % big
        body = updater.parse_changelog(text, '0.1.0', '0.2.0')[0]['body']
        self.assertLessEqual(len(body.encode('utf-8')), updater.NOTES_SECTION_MAX_BYTES)
        self.assertGreater(len(body.encode('utf-8')), updater.NOTES_SECTION_MAX_BYTES - 4)
        many = ''.join('## [0.%d.0] — 11.11.2026\n\n%s\n\n' % (i, 'x' * 6000) for i in range(30, 1, -1))
        got = updater.parse_changelog(many, '0.1.0', '0.30.0')
        self.assertLessEqual(sum(len(s['body'].encode('utf-8')) for s in got), updater.NOTES_TOTAL_MAX_BYTES)
        self.assertLess(len(got), 28)

    def test_malformed_headings_ignored_and_close_the_previous_section(self):
        text = ('## [0.3.0] — 12.11.2026\n\nThree.\n\n## [x.y.z] — 11.11.2026\n\nBAD1\n\n## [0.2] — 11.11.2026\n\nBAD2\n\n'
                '## [0.2.0]\n\nBAD3\n\n## [0.2.0] — 31.02.2026\n\nBAD4\n\n## [01.2.0] — 11.11.2026\n\nBAD5\n\n## [0.1.5] — 10.11.2026\n\nOk.\n')
        got = updater.parse_changelog(text, '0.1.0', '0.3.0')
        self.assertEqual([s['version'] for s in got], ['0.3.0', '0.1.5'])
        self.assertEqual(got[0]['body'], 'Three.')
        self.assertNotIn('BAD', ''.join(s['body'] for s in got))

    def test_unreleased_ignored(self):
        text = '## [Unreleased]\n\nNext.\n\n## [0.2.0] — 11.11.2026\n\nTwo.\n'
        got = updater.parse_changelog(text, '0.1.0', '0.9.0')
        self.assertEqual([s['version'] for s in got], ['0.2.0'])
        self.assertEqual(got[0]['body'], 'Two.')


class Notes(ta.Base):
    def setUp(self):
        super().setUp()
        for k in ('DEAI_NO_UPDATE_CHECK', 'DEAI_UPDATE_REMOTE'):
            os.environ.pop(k, None)

    def ready_notes(self, version='0.2.0', text=None, **kw):
        files = {'CHANGELOG.md': text if text is not None else changelog(version, '0.1.0')}
        return self.ready(version, release={'files': files}, **kw)

    def fresh_notes(self):
        """Свіжий світ на кожен збій: попередній реліз/кеш не заважає."""
        import tempfile
        try:
            os.remove(os.path.join(self.home, 'update.json'))
        except OSError:
            pass
        self.remote, self.work = ta.make_app_world(tempfile.mkdtemp(dir=self.tmp))
        return self.ready_notes()

    @staticmethod
    def read(path):
        with open(path, encoding='utf-8') as f:
            return f.read()

    def state(self):
        with open(os.path.join(self.home, 'update.json'), encoding='utf-8') as f:
            return json.load(f)

    def test_reads_the_remote_tag_changelog_and_caches_it(self):
        u = self.ready_notes()
        out = u.notes()
        self.assertEqual((out['ok'], out['version']), (True, '0.2.0'))
        self.assertEqual([s['version'] for s in out['sections']], ['0.2.0'])
        self.assertEqual(out['sections'][0]['body'], 'Body of 0.2.0.')
        self.assertNotIn('reason', out)
        self.assertEqual(self.state()['notes']['version'], '0.2.0')
        self.assertEqual(self.state()['latest'], '0.2.0')

    def test_never_touches_tree_index_or_head(self):
        u = self.ready_notes()
        pkg = os.path.join(self.work, 'package.json')
        with open(pkg, 'a') as f:                                   # правка користувача в відстежуваному файлі
            f.write('\n')
        calls, run = self.counting()
        u.run = run
        before = (ta.head(self.work), tu.git(['status', '--porcelain'], self.work), self.read(pkg))
        self.assertEqual(u.notes()['sections'][0]['version'], '0.2.0')
        after = (ta.head(self.work), tu.git(['status', '--porcelain'], self.work), self.read(pkg))
        self.assertEqual(before, after)
        verbs = [c[0] for c in calls]
        for bad in ('merge', 'reset', 'checkout', 'stash', 'rebase', 'pull', 'clean', 'restore', 'switch'):
            self.assertNotIn(bad, verbs)
        self.assertIn('fetch', verbs)
        self.assertFalse(os.path.exists(os.path.join(self.work, 'CHANGELOG.md')))

    def test_target_is_validated_before_git_and_show_uses_the_resolved_sha(self):
        u = self.ready_notes()
        calls, run = self.counting()
        u.run = run
        st = u._load()
        for hostile in ('0.2.0 --upload-pack=x', '-1.0.0', '0.2.0\n', 'v0.2.0', '0.2', '../x', 5):
            u._save({**st, 'latest': hostile})
            del calls[:]
            self.assertEqual(u.notes(), {'ok': True, 'sections': [], 'reason': 'no-update'}, repr(hostile))
            self.assertEqual(calls, [], repr(hostile))
        u._save(st)
        self.assertEqual(u.notes()['version'], '0.2.0')
        shows = [r for r in self.raw if r[0] == 'show']
        self.assertEqual(len(shows), 0)                              # `show` іде повз `self.run` (обмежене читання), див. нижче
        tag_sha = tu.git(['rev-parse', 'v0.2.0^{commit}'], self.work).strip()
        seen = []
        real = updater.git_head

        def spy(args, *a, **k):
            seen.append(list(args))
            return real(args, *a, **k)
        u._save({k: v for k, v in st.items() if k != 'notes'})
        with mock.patch.object(updater, 'git_head', spy):
            u.notes()
        self.assertEqual(seen, [['show', tag_sha + ':CHANGELOG.md']])
        self.assertRegex(seen[0][1], r'^[0-9a-f]{40}:CHANGELOG\.md$')

    def test_second_call_serves_the_cache_without_git_or_remote(self):
        u = self.ready_notes()
        first = u.notes()
        import shutil
        shutil.rmtree(self.remote)
        calls, run = self.counting()
        u.run = run
        with mock.patch.object(updater, 'git_head', side_effect=AssertionError('cache expected')):
            again = u.notes()
        self.assertEqual(again, first)
        self.assertEqual(calls, [])

    def test_cache_is_for_this_latest_and_current_only(self):
        u = self.ready_notes()
        u.notes()
        ta.release(self.work, '0.3.0', files={'CHANGELOG.md': changelog('0.3.0', '0.2.0', '0.1.0')})
        u.check()
        out = u.notes()
        self.assertEqual((out['version'], [s['version'] for s in out['sections']]), ('0.3.0', ['0.3.0', '0.2.0']))

    def test_tampered_cache_is_ignored_and_refetched(self):
        u = self.ready_notes()
        st = u._load()
        u._save({**st, 'notes': {'version': '0.2.0', 'after': '0.1.0', 'sections': [{'version': 5, 'date': None, 'body': []}]}})
        out = u.notes()
        self.assertEqual(out['sections'][0]['body'], 'Body of 0.2.0.')

    def test_offline_without_cache_is_a_reason_not_an_error(self):
        u = self.ready_notes()
        import shutil
        shutil.rmtree(self.remote)
        out = u.notes()
        self.assertEqual(out, {'ok': True, 'sections': [], 'reason': 'offline', 'version': '0.2.0'})
        self.assertNotIn('notes', u._load())                         # відмова не кешується

    def test_fetch_failures_map_to_codes_without_leaking_git_text(self):
        for stderr, reason in (('fatal: index-pack failed', 'offline'), ('fatal: fsck error in packed object', 'fetch-rejected'),
                               ("fatal: couldn't find remote ref refs/tags/v0.2.0", 'tag-missing'),
                               ('! [rejected] v0.2.0 -> v0.2.0 (would clobber existing tag)', 'tag-conflict')):
            u = self.fresh_notes()
            real = updater.run_git
            u.run = lambda args, cwd, timeout, env_extra=None, s=stderr: (
                (128, '', s + ' ' + self.remote) if ta.V(args)[0] == 'fetch' else real(args, cwd, timeout, env_extra))
            out = u.notes()
            self.assertEqual(out['reason'], reason, stderr)
            self.assertEqual(out['sections'], [])
            self.assertNotIn(self.remote, json.dumps(out))

    def test_no_git_and_no_update(self):
        d = os.path.join(self.tmp, 'plain')
        os.makedirs(d)
        tu.write_pkg(d, '0.1.0')
        u = self.upd(d)
        u._save({'latest': '0.2.0'})
        self.assertEqual(u.notes(), {'ok': True, 'sections': [], 'reason': 'no-git', 'version': '0.2.0'})
        u = self.upd(self.work)
        u._save({})
        self.assertEqual(u.notes()['reason'], 'no-update')

    def test_disabled_without_cache_never_calls_network_git(self):
        u = self.ready_notes()
        calls, run = self.counting()
        u.run = run
        with mock.patch.dict(os.environ, {'DEAI_UPDATE_REMOTE': 'https://git.example/o/r.git', 'DEAI_NO_UPDATE_CHECK': '1'}):
            out = u.notes()
        self.assertEqual(out, {'ok': True, 'sections': [], 'reason': 'disabled', 'version': '0.2.0'})
        self.assertNotIn('fetch', [c[0] for c in calls])
        self.assertNotIn('ls-remote', [c[0] for c in calls])
        self.assertNotIn('git.example', json.dumps(out))

    def test_changelog_over_1mb_is_read_only_up_to_1mb(self):
        filler = ('x' * 99 + '\n') * 12000                          # ~1,2 МБ у розділі 0.3.0, а розділ 0.2.0 — за межею 1 МБ
        text = '## [0.3.0] — 12.11.2026\n\n%s\n## [0.2.0] — 11.11.2026\n\nBEYOND\n' % filler
        self.assertGreater(len(text), updater.NOTES_MAX_BYTES)
        u = self.ready_notes('0.3.0', text=text)
        out = u.notes()
        self.assertEqual([s['version'] for s in out['sections']], ['0.3.0'])
        self.assertLessEqual(len(out['sections'][0]['body'].encode()), updater.NOTES_SECTION_MAX_BYTES)

    def test_git_head_never_returns_more_than_the_limit(self):
        blob = os.path.join(self.work, 'big.txt')
        with open(blob, 'w') as f:
            f.write('y' * (3 * 1024 * 1024))
        tu.git(['add', '--', 'big.txt'], self.work)
        tu.git(['commit', '-m', 'big'], self.work)
        sha = ta.head(self.work)
        rc, data = updater.git_head(['show', sha + ':big.txt'], self.work, 1024 * 1024, 30)
        self.assertEqual((rc, len(data)), (0, 1024 * 1024))
        rc, data = updater.git_head(['show', sha + ':package.json'], self.work, 1024 * 1024, 30)
        self.assertEqual(rc, 0)
        self.assertTrue(data.startswith(b'{'))
        rc, data = updater.git_head(['show', sha + ':nope'], self.work, 1024 * 1024, 30)
        self.assertNotEqual(rc, 0)

    def test_missing_changelog_is_a_reason_and_not_cached(self):
        u = self.ready()                                             # реліз без CHANGELOG.md
        out = u.notes()
        self.assertEqual((out['sections'], out['reason']), ([], 'no-changelog'))
        self.assertNotIn('notes', u._load())

    def test_response_has_no_paths_or_remote(self):
        u = self.ready_notes()
        raw = json.dumps(u.notes())
        for needle in (self.tmp, self.remote, self.work):
            self.assertNotIn(needle, raw)

    def test_notes_never_raises(self):
        u = self.ready_notes()
        u.run = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom'))
        self.assertEqual(u.notes()['reason'], 'error')


if __name__ == '__main__':
    unittest.main()
