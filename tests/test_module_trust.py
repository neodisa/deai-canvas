"""`app/module_trust.py`: сканер теки свого модуля, хеш, порівняння з довіреним (Task 1); записи довіри, знімки й
системне вікно (Task 2). Спека: `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`.

Кожен тест має власні `HOME` і `DEAI_HOME` (тимчасові); справжній `~/.deai` стереже `spaces_guard`. Системне вікно ОС
не показується НІКОЛИ: `subprocess.run` і `confirm` підмінені там, де до них доходить.
"""
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import module_trust as mt  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _put(root, rel, data=b'x'):
    p = os.path.join(root, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))
    return p


def _case_insensitive(d):
    probe = os.path.join(d, 'CaseProbe')
    open(probe, 'w').close()
    try:
        return os.path.exists(os.path.join(d, 'caseprobe'))
    finally:
        os.remove(probe)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='mt-'))
        self.addCleanup(self._cleanup)
        self.home = os.path.join(self.tmp, 'home')
        self.deai = os.path.join(self.home, '.deai-test')
        os.makedirs(self.home)
        env = mock.patch.dict(os.environ, {'HOME': self.home, 'DEAI_HOME': self.deai})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DEAI_TRUST_CONFIRM', None)
        mt.reset_cache()
        self.addCleanup(mt.reset_cache)
        if hasattr(mt, 'clear_declined'):              # зʼявляється в Task 2
            mt.clear_declined()
            self.addCleanup(mt.clear_declined)
        self.mod = os.path.join(self.tmp, 'space', 'modules', 'netlify')
        _put(self.mod, 'module.json', json.dumps({'api': 1, 'id': 'netlify', 'roles': ['publish']}))
        _put(self.mod, 'server.py', 'def check(ctx):\n    return {"ok": True}\n')

    def _cleanup(self):
        for dp, dns, fns in os.walk(self.tmp):        # знімки — 0500/0400: повернути запис перед видаленням
            os.chmod(dp, 0o700)
        shutil.rmtree(self.tmp, ignore_errors=True)


class ScanTest(Base):
    def test_counts_files_and_reads_manifest(self):
        sc = mt.scan(self.mod)
        self.assertEqual([f[0] for f in sc.files], ['module.json', 'server.py'])
        self.assertEqual(sc.total, sum(f[1] for f in sc.files))
        self.assertEqual(json.loads(sc.manifest)['id'], 'netlify')
        self.assertIsNone(sc.data)
        self.assertRegex(sc.hash, r'^[0-9a-f]{64}$')

    def test_hash_is_the_documented_canonical_form(self):
        sc = mt.scan(self.mod)
        h = hashlib.sha256()
        for path, size, sha in sorted(sc.files, key=lambda f: f[0].encode('utf-8')):
            h.update(f'{path}\0{size}\0{sha}\n'.encode('utf-8'))
        self.assertEqual(sc.hash, h.hexdigest())

    def test_hash_reacts_to_content_rename_and_new_file(self):
        h0 = mt.scan(self.mod).hash
        _put(self.mod, 'server.py', 'def check(ctx):\n    return {"ok": False}\n')
        h1 = mt.scan(self.mod, with_data=True).hash
        self.assertNotEqual(h0, h1)
        os.rename(os.path.join(self.mod, 'server.py'), os.path.join(self.mod, 'main.py'))
        h2 = mt.scan(self.mod, with_data=True).hash
        self.assertNotEqual(h1, h2)
        _put(self.mod, 'extra.txt', 'x')
        self.assertNotEqual(h2, mt.scan(self.mod, with_data=True).hash)

    def test_skips_finder_python_and_git_litter(self):
        h0 = mt.scan(self.mod).hash
        _put(self.mod, '.DS_Store', b'\0\1')
        _put(self.mod, '__pycache__/server.cpython-313.pyc', b'pyc')
        _put(self.mod, 'lib/helper.pyc', b'pyc')
        _put(self.mod, '.git/HEAD', 'ref: refs/heads/main')
        sc = mt.scan(self.mod, with_data=True)
        self.assertEqual(sc.hash, h0)
        self.assertEqual(sorted(sc.data), ['module.json', 'server.py'])

    def test_other_hidden_files_count(self):
        h0 = mt.scan(self.mod).hash
        _put(self.mod, '.env', 'X=1')
        sc = mt.scan(self.mod, with_data=True)
        self.assertIn('.env', [f[0] for f in sc.files])
        self.assertNotEqual(sc.hash, h0)

    def assertRefused(self, code, root=None):
        with self.assertRaises(mt.Refused) as cm:
            mt.scan(root or self.mod, with_data=True)
        self.assertEqual(cm.exception.code, code, cm.exception.detail)
        return cm.exception

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_refuses_symlinked_file_dir_and_root(self):
        os.symlink(os.path.join(self.mod, 'server.py'), os.path.join(self.mod, 'alias.py'))
        self.assertIn('alias.py', self.assertRefused('symlink').detail)
        os.remove(os.path.join(self.mod, 'alias.py'))
        os.symlink(self.tmp, os.path.join(self.mod, 'up'))
        self.assertRefused('symlink')
        os.remove(os.path.join(self.mod, 'up'))
        link = os.path.join(self.tmp, 'link-mod')
        os.symlink(self.mod, link)
        self.assertRefused('symlink', link)

    @unittest.skipIf(os.name == 'nt', 'жорсткі посилання')
    def test_refuses_hardlink(self):
        os.link(os.path.join(self.mod, 'server.py'), os.path.join(self.tmp, 'outside.py'))
        self.assertRefused('hardlink')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO')
    def test_refuses_fifo(self):
        os.mkfifo(os.path.join(self.mod, 'pipe'))
        self.assertRefused('special-file')

    def test_too_many_files_refused_before_reading_anything(self):
        for i in range(mt.MAX_FILES):
            _put(self.mod, f'f/{i:03}.txt', 'x')
        with mock.patch.object(mt, '_read', side_effect=AssertionError('читання до відмови')):
            self.assertRefused('too-many-files')

    def test_too_big_refused_before_reading_anything(self):
        p = _put(self.mod, 'big.bin', b'')
        with open(p, 'r+b') as f:
            f.truncate(mt.MAX_BYTES + 1)              # розріджений файл: швидко й без 5 МіБ на диску
        with mock.patch.object(mt, '_read', side_effect=AssertionError('читання до відмови')):
            self.assertRefused('too-big')

    def test_depth_limit(self):
        _put(self.mod, '/'.join(['d'] * mt.MAX_DEPTH) + '/ok.txt', 'x')
        mt.scan(self.mod, with_data=True)
        _put(self.mod, '/'.join(['e'] * (mt.MAX_DEPTH + 1)) + '/deep.txt', 'x')
        self.assertRefused('too-deep')

    def test_name_rules(self):
        for bad in ('a\x01b', 'a‮b.js', 'CON', 'nul.txt', 'Com1.js', 'tail.', 'tail ', ' '):
            self.assertFalse(mt.name_ok(bad), repr(bad))
        for good in ('server.py', '.env', 'README', 'ж.txt', 'con-rules.md', 'a b.txt'):
            self.assertTrue(mt.name_ok(good), repr(good))

    def test_bad_name_on_disk_is_refused_and_detail_is_escaped(self):
        _put(self.mod, 'a‮b.js', 'x')
        e = self.assertRefused('bad-name')
        self.assertNotIn('‮', e.detail)

    def test_case_and_nfc_twins_key(self):
        self.assertEqual(mt.twin_key('Server.PY'), mt.twin_key('server.py'))
        self.assertEqual(mt.twin_key('é.js'), mt.twin_key('é.js'))

    def test_case_twins_on_disk(self):
        if _case_insensitive(self.mod):
            self.skipTest('ФС нечутлива до регістру: двійників не створити')
        _put(self.mod, 'A.js', 'x')
        _put(self.mod, 'a.js', 'y')
        self.assertRefused('bad-name')

    def test_twin_names_in_one_listing_on_any_fs(self):
        # Переносний свідок двійників: на APFS/NTFS (нечутливих до регістру) двох файлів не створити, тож «другий» імітуємо
        # переліком теки; його `lstat` — справжній файл `server.py`.
        real_listdir, real_lstat = os.listdir, mt._lstat
        with mock.patch.object(os, 'listdir', lambda d: real_listdir(d) + (['SERVER.PY'] if d == self.mod else [])), \
                mock.patch.object(mt, '_lstat', lambda p, rel: real_lstat(os.path.join(self.mod, 'server.py'), rel)
                                  if rel == 'SERVER.PY' else real_lstat(p, rel)):
            e = self.assertRefused('bad-name')
        self.assertIn('SERVER.PY', e.detail)
        self.assertIn('server.py', e.detail)

    def test_surrogate_in_a_name_is_escaped_so_detail_encodes(self):
        # Імʼя з не-UTF-8 байтами на ФС, що таке дозволяє (Linux), приходить з `listdir` одиноким сурогатом.
        real_listdir = os.listdir
        with mock.patch.object(os, 'listdir', lambda d: real_listdir(d) + (['a\udcffb'] if d == self.mod else [])):
            e = self.assertRefused('bad-name')
        e.detail.encode('utf-8')                        # не падає: сурогата в тексті відмови нема
        self.assertIn('a\\udcffb', e.detail)

    def test_unstable_file(self):
        p = os.path.join(self.mod, 'server.py')
        st = os.lstat(p)
        with open(p, 'ab') as f:
            f.write(b'# grew')
        with self.assertRaises(mt.Refused) as cm:
            mt._read('server.py', p, st)
        self.assertEqual(cm.exception.code, 'unstable')

    def test_unstable_file_shrunk_swapped_linked_or_growing(self):
        # Кожна з перевірок `_read` окремо: файл усох, підмінений іншим (той самий розмір, інший inode), отримав жорстке
        # посилання, ріс би без меж. Відмови 'unstable' — не 'unreadable': змінилось те, що вже бачив `lstat`.
        p = os.path.join(self.mod, 'server.py')
        st = os.lstat(p)
        other = _put(self.tmp, 'other.py', b'y' * st.st_size)
        with self.assertRaises(mt.Refused) as cm:
            mt._read('server.py', p, os.lstat(other))
        self.assertEqual(cm.exception.code, 'unstable')
        os.link(p, os.path.join(self.tmp, 'late-alias.py'))
        with self.assertRaises(mt.Refused) as cm:
            mt._read('server.py', p, st)
        self.assertEqual(cm.exception.code, 'unstable')
        os.remove(os.path.join(self.tmp, 'late-alias.py'))
        calls = []

        def endless(fd, n):
            calls.append(n)
            return b'x' * n if len(calls) < 50 else b''
        with mock.patch.object(os, 'read', endless):
            with self.assertRaises(mt.Refused) as cm:
                mt._read('server.py', p, st)
        self.assertEqual(cm.exception.code, 'unstable')
        self.assertLessEqual(len(calls), 2)               # обірвано одразу, не дочитано до кінця
        with open(p, 'r+b') as f:
            f.truncate(3)
        with self.assertRaises(mt.Refused) as cm:
            mt._read('server.py', p, st)
        self.assertEqual(cm.exception.code, 'unstable')

    def test_root_must_be_a_directory(self):
        self.assertRefused('special-file', os.path.join(self.mod, 'server.py'))

    def test_cache_skips_reading_until_the_tree_changes(self):
        first = mt.scan(self.mod)
        with mock.patch.object(mt, '_read', side_effect=AssertionError('перечитав без змін')):
            self.assertEqual(mt.scan(self.mod), first)
        p = os.path.join(self.mod, 'server.py')
        st = os.stat(p)
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5 * 10 ** 9))
        with mock.patch.object(mt, '_read', side_effect=AssertionError('read')):
            with self.assertRaises(AssertionError):
                mt.scan(self.mod)

    def test_cached_refusal_is_raised_again(self):
        _put(self.mod, 'CON', 'x')
        for _ in range(2):
            with self.assertRaises(mt.Refused):
                mt.scan(self.mod)

    def test_with_data_bypasses_cache_and_carries_bytes(self):
        mt.scan(self.mod)
        with mock.patch.object(mt, '_read', wraps=mt._read) as rd:
            sc = mt.scan(self.mod, with_data=True)
        self.assertEqual(rd.call_count, 2)
        with open(os.path.join(self.mod, 'server.py'), 'rb') as f:
            self.assertEqual(sc.data['server.py'], f.read())


class DiffTest(Base):
    def test_diff_against_record(self):
        sc = mt.scan(self.mod)
        rec = [{'path': 'module.json', 'size': 1, 'sha256': sc.files[0][2]},
               {'path': 'server.py', 'size': 1, 'sha256': '0' * 64},
               {'path': 'old.js', 'size': 300, 'sha256': '1' * 64}]
        files, removed = mt.diff(sc.files, rec)
        self.assertEqual([(f['path'], f['change']) for f in files], [('module.json', 'same'), ('server.py', 'changed')])
        self.assertEqual(removed, [{'path': 'old.js', 'size': 300}])

    def test_diff_without_record_is_all_new(self):
        files, removed = mt.diff(mt.scan(self.mod).files, None)
        self.assertEqual({f['change'] for f in files}, {'new'})
        self.assertEqual(removed, [])

    def test_tilde_only_on_a_path_boundary(self):
        self.assertEqual(mt.tilde(os.path.join(self.home, 'w', 'm')), os.path.join('~', 'w', 'm'))
        self.assertEqual(mt.tilde(self.home + '2/m'), self.home + '2/m')
        self.assertEqual(mt.tilde('/elsewhere/m'), '/elsewhere/m')


if __name__ == '__main__':
    unittest.main()
