"""`app/module_trust.py`: сканер теки свого модуля, хеш, порівняння з довіреним (Task 1); записи довіри, знімки й
системне вікно (Task 2). Спека: `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`.

Кожен тест має власні `HOME` і `DEAI_HOME` (тимчасові); справжній `~/.deai` стереже `spaces_guard`. Системне вікно ОС
не показується НІКОЛИ: `subprocess.run` і `confirm` підмінені там, де до них доходить.
"""
import errno
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import types
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


def _slurp(path):
    with open(path, 'rb') as f:
        return f.read()


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
        mt.clear_declined()
        self.addCleanup(mt.clear_declined)
        # Сітка: справжнє системне вікно не показується НІКОЛИ — будь-який незаглушений шлях до підпроцесу падає голосно.
        net = mock.patch.object(mt.subprocess, 'run', side_effect=AssertionError('системне вікно в тесті'))
        net.start()
        self.addCleanup(net.stop)
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
        for bad in ('a\x01b', 'a‮b.js', 'CON', 'nul.txt', 'Com1.js', 'tail.', 'tail ', ' ',
                    'prn', 'AUX.txt', 'lpt1', 'LPT9.log', 'com0'):
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

    def test_shown_keeps_readable_names_and_escapes_the_rest(self):
        self.assertEqual(mt._shown('ж/é.txt'), 'ж/é.txt')          # не-ASCII лишається читабельним
        self.assertEqual(mt._shown('a\x01b\u202e'), 'a\\u0001b\\u202e')

    def test_files_are_ordered_by_utf8_bytes_across_directories(self):
        # Обхід у глибину віддав би 'a/x' раніше за 'a-b' й 'a.b', а за байтами шляху ('-' < '.' < '/') порядок інший.
        for rel in ('a/x', 'a.b', 'a-b', 'Z', 'é', 'ж/y'):
            _put(self.mod, rel, rel)
        sc = mt.scan(self.mod, with_data=True)
        paths = [f[0] for f in sc.files]
        self.assertEqual(paths, sorted(paths, key=lambda q: q.encode('utf-8')))
        self.assertLess(paths.index('a-b'), paths.index('a/x'))
        self.assertEqual(mt.tree_hash(list(reversed(sc.files))), sc.hash)    # хеш не залежить від порядку на вході

    def test_pycache_dir_is_skipped_whatever_is_inside(self):
        h0 = mt.scan(self.mod).hash
        _put(self.mod, '__pycache__/note.txt', 'x')                 # не `.pyc`: пропущена саме тека
        self.assertEqual(mt.scan(self.mod, with_data=True).hash, h0)

    def test_file_count_limit_is_inclusive(self):
        for i in range(mt.MAX_FILES - 2):                           # module.json і server.py вже є
            _put(self.mod, f'f/{i:03}.txt', 'x')
        self.assertEqual(len(mt.scan(self.mod, with_data=True).files), mt.MAX_FILES)
        _put(self.mod, 'f/over.txt', 'x')
        self.assertRefused('too-many-files')

    def test_size_limit_is_inclusive(self):
        os.remove(os.path.join(self.mod, 'server.py'))
        os.remove(os.path.join(self.mod, 'module.json'))
        os.truncate(_put(self.mod, 'big.bin', b''), mt.MAX_BYTES)   # розріджений файл рівно на межі
        self.assertEqual(mt.scan(self.mod).total, mt.MAX_BYTES)

    def test_refusal_is_cached_not_rewalked(self):
        _put(self.mod, 'CON', 'x')
        with mock.patch.object(mt, '_walk', wraps=mt._walk) as walk:
            for _ in range(3):
                with self.assertRaises(mt.Refused):
                    mt.scan(self.mod)
        self.assertEqual(walk.call_count, 1)

    def _no_access(self, path):
        if os.geteuid() == 0:
            self.skipTest('root обходить права')
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o700)                      # інакше `rmtree` не прибере тимчасову теку

    @unittest.skipIf(os.name == 'nt', 'права POSIX')
    def test_unreadable_dir_is_refused(self):
        _put(self.mod, 'sub/a.py', 'x')
        self._no_access(os.path.join(self.mod, 'sub'))
        e = self.assertRefused('unreadable')
        self.assertEqual(e.detail, 'sub')

    @unittest.skipIf(os.name == 'nt', 'права POSIX')
    def test_unreadable_file_is_refused(self):
        self._no_access(os.path.join(self.mod, 'server.py'))
        e = self.assertRefused('unreadable')
        self.assertEqual(e.detail, 'server.py')

    def test_missing_root_is_unreadable(self):
        self.assertRefused('unreadable', os.path.join(self.tmp, 'nope'))

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_read_refuses_a_symlink_swapped_in_after_lstat(self):
        p = os.path.join(self.mod, 'server.py')
        st = os.lstat(p)
        os.remove(p)
        os.symlink(os.path.join(self.mod, 'module.json'), p)         # `O_NOFOLLOW`: не йдемо за підміною
        with self.assertRaises(mt.Refused) as cm:
            mt._read('server.py', p, st)
        self.assertEqual(cm.exception.code, 'symlink')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO')
    def test_read_does_not_hang_on_a_fifo_swapped_in_after_lstat(self):
        p = os.path.join(self.mod, 'server.py')
        st = os.lstat(p)
        os.remove(p)
        os.mkfifo(p)
        got = []

        def run():
            try:
                mt._read('server.py', p, st)
            except mt.Refused as e:
                got.append(e.code)
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(3)
        if t.is_alive():                                            # без `O_NONBLOCK` `open` висить: розблокувати й упасти
            # Письменник сам неблоківний: коли читача ще нема, `open` дає `ENXIO` (повторюємо коротко й обмежено), а не
            # висне — тест не може зависнути назавжди навіть тоді, коли висить код.
            for _ in range(100):
                try:
                    os.close(os.open(p, os.O_WRONLY | os.O_NONBLOCK))
                    break
                except OSError as e:
                    if e.errno != errno.ENXIO:
                        raise
                    time.sleep(0.05)
            t.join(3)
            self.fail('open() FIFO завис')
        self.assertEqual(got, ['unstable'])

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


class CacheTest(Base):
    def test_fingerprint_of_a_missing_root_is_none(self):
        self.assertIsNone(mt.fingerprint(os.path.join(self.tmp, 'nope')))

    def test_cache_sees_a_nested_edit(self):
        p = _put(self.mod, 'lib/h.py', 'one')
        h0 = mt.scan(self.mod).hash
        _put(self.mod, 'lib/h.py', 'two')                           # той самий розмір: видно лише в записі `lib/h.py`
        st = os.stat(p)                                             # явний зсув: на ФС із грубими мітками (ext4 до 6.13, NTFS,
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5 * 10 ** 9))   # HFS+) правка в ту ж секунду мала б той самий mtime
        self.assertNotEqual(mt.scan(self.mod).hash, h0)

    def test_fingerprint_reacts_to_each_lstat_field(self):
        target = os.path.join(self.mod, 'server.py')
        real = os.lstat
        st = real(target)

        def fp_with(**over):
            def fake(p):
                s = real(p)
                if p != target:
                    return s
                d = {k: getattr(s, k) for k in ('st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_ino', 'st_nlink')}
                d.update(over)
                return types.SimpleNamespace(**d)
            with mock.patch.object(os, 'lstat', fake):
                return mt.fingerprint(self.mod)
        base = fp_with()
        self.assertEqual(fp_with(), base)
        for field, val in (('st_mode', st.st_mode ^ 0o100), ('st_size', st.st_size + 1), ('st_mtime_ns', st.st_mtime_ns + 1),
                           ('st_ctime_ns', st.st_ctime_ns + 1), ('st_ino', st.st_ino + 1), ('st_nlink', st.st_nlink + 1)):
            with self.subTest(field=field):
                self.assertNotEqual(fp_with(**{field: val}), base)

    def test_same_size_edit_with_restored_mtime_is_still_seen(self):
        p = os.path.join(self.mod, 'server.py')
        st = os.stat(p)
        h0, fp0 = mt.scan(self.mod).hash, mt.fingerprint(self.mod)
        # `ctime` userland не підробить, а на ФС із грубими мітками (ext4 до 6.13, NTFS, HFS+) правка в ту ж мить, що й
        # створення, лишила б його тим самим. Тож правимо, доки `ctime` справді зрушить (≤ ~4 с); не зрушив — ФС надто груба,
        # і тест чесно пропускається, а не флейкає.
        for _ in range(40):
            with open(p, 'r+b') as f:
                f.write(b'Z')                                       # перший байт; розмір той самий
            os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))        # `mtime` повернуто
            if os.stat(p).st_ctime_ns != st.st_ctime_ns:
                break
            time.sleep(0.1)
        else:
            self.skipTest('ФС із грубими мітками часу: ctime не зрушив')
        self.assertEqual(os.stat(p).st_mtime_ns, st.st_mtime_ns)
        self.assertEqual(os.stat(p).st_size, st.st_size)
        self.assertNotEqual(mt.fingerprint(self.mod), fp0)
        self.assertNotEqual(mt.scan(self.mod).hash, h0)

    def test_fingerprint_cut_off_never_hides_a_change(self):
        for i in range(mt.FP_MAX + 100):                            # `.pyc` у скан не йдуть, а відбиток вичерпують
            _put(self.mod, f'a/{i:04}.pyc', b'')
        _put(self.mod, 'z/real.py', 'one')
        h0 = mt.scan(self.mod).hash
        _put(self.mod, 'z/real.py', 'two')
        self.assertNotEqual(mt.scan(self.mod).hash, h0)             # кеш промахнувся, а не віддав застарілий хеш
        fp = mt.fingerprint(self.mod)
        self.assertEqual(sum(1 for e in fp if e[0] == 'truncated'), 1)           # токен один, не на кожному рівні
        self.assertNotEqual(fp, mt.fingerprint(self.mod))

    def test_fingerprint_does_not_enter_skipped_dirs(self):
        # `.git` (чи `__pycache__`) може мати тисячі файлів і змінюватись щохвилини: відбиток не мусить ні обриватись на
        # `FP_MAX`, ні реагувати на їхній вміст — інакше кеш `scan` ніколи не влучав би для модуля в git-теці.
        for i in range(mt.FP_MAX + 100):
            _put(self.mod, f'.git/objects/{i:04}', b'')
        _put(self.mod, '__pycache__/m.cpython-313.opt-1.pyc', b'one')
        fp = mt.fingerprint(self.mod)
        self.assertEqual([e for e in fp if e[0] == 'truncated'], [])
        self.assertEqual(mt.fingerprint(self.mod), fp)
        mt.scan(self.mod)
        with mock.patch.object(mt, '_walk', side_effect=AssertionError('промах кешу')):
            mt.scan(self.mod)                                        # хіт кешу, обхід не потрібен
        _put(self.mod, '.git/objects/0007', b'edited in place')      # правка існуючого файла всередині пропущеної теки
        _put(self.mod, '__pycache__/m.cpython-313.opt-1.pyc', b'two')
        self.assertEqual(mt.fingerprint(self.mod), fp)

    def test_cache_is_bounded_and_evicts_the_oldest(self):
        roots = []
        for i in range(5):
            r = os.path.join(self.tmp, 'many', f'm{i}')
            _put(r, 'module.json', '{}')
            roots.append(r)
        with mock.patch.object(mt, 'CACHE_MAX', 3):
            for r in roots:
                mt.scan(r)
        self.assertEqual(list(mt._CACHE), roots[2:])                # найстарі витіснено, найновіші лишились

    def test_forget_drops_one_root_and_reset_drops_all(self):
        other = os.path.join(self.tmp, 'other-mod')
        _put(other, 'module.json', '{}')
        mt.scan(self.mod)
        mt.scan(other)
        mt.forget(self.mod)
        with mock.patch.object(mt, '_walk', wraps=mt._walk) as walk:
            mt.scan(other)
            self.assertEqual(walk.call_count, 0)                    # інша тека лишилась у кеші
            mt.scan(self.mod)
            self.assertEqual(walk.call_count, 1)
        mt.reset_cache()
        with mock.patch.object(mt, '_walk', wraps=mt._walk) as walk:
            mt.scan(other)
            self.assertEqual(walk.call_count, 1)


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

    def test_diff_survives_a_lone_surrogate_in_a_record_path(self):
        # Запис із зіпсованого `trust.json` може нести самотній сурогат: сортування `removed` не повинно падати.
        files, removed = mt.diff(mt.scan(self.mod).files, [{'path': 'a\ud800', 'size': 1, 'sha256': 'x'}])
        self.assertEqual(removed, [{'path': 'a\ud800', 'size': 1}])

    def test_tilde_only_on_a_path_boundary(self):
        self.assertEqual(mt.tilde(os.path.join(self.home, 'w', 'm')), os.path.join('~', 'w', 'm'))
        self.assertEqual(mt.tilde(self.home + '2/m'), self.home + '2/m')
        self.assertEqual(mt.tilde('/elsewhere/m'), '/elsewhere/m')


class RecordsTest(Base):
    def rec(self, h='a' * 64, mid='netlify'):
        return {'id': mid, 'name': 'Netlify', 'version': '1', 'roles': ['publish'], 'hash': h,
                'files': [{'path': 'server.py', 'size': 1, 'sha256': 'b' * 64}], 'trusted_at': '2026-10-22T00:00:00Z'}

    def snap(self, h='a' * 64):
        os.makedirs(mt.snapshot_dir(h))

    def write_raw(self, body):
        os.makedirs(self.deai, exist_ok=True)
        with open(mt.trust_file(), 'w') as f:
            f.write(body if isinstance(body, str) else json.dumps(body))

    def test_no_file_is_empty(self):
        self.assertEqual(mt.load_records(), {})

    def test_layer_off_reads_nothing(self):
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            os.environ.pop('DEAI_HOME')
            with mock.patch.object(spaces, '_read_json', side_effect=AssertionError('читав при вимкненому шарі')):
                self.assertEqual(mt.load_records(), {})
            with self.assertRaises(RuntimeError):
                mt.put_record('/k', self.rec())
            with self.assertRaises(RuntimeError):
                mt.drop_record('/k')

    def test_put_and_load(self):
        self.snap()
        mt.put_record('/k', self.rec())
        self.assertEqual(mt.load_records()['/k']['hash'], 'a' * 64)
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(os.stat(mt.trust_file()).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(self.deai).st_mode), 0o700)

    def test_put_keeps_the_other_records_and_the_version(self):
        self.snap()
        self.snap('c' * 64)
        mt.put_record('/k1', self.rec())
        mt.put_record('/k2', self.rec('c' * 64, 'other'))
        with open(mt.trust_file()) as f:
            data = json.load(f)
        self.assertEqual(data['version'], 1)
        self.assertEqual(sorted(data['modules']), ['/k1', '/k2'])
        self.assertEqual(sorted(mt.load_records()), ['/k1', '/k2'])

    def test_put_refuses_without_snapshot(self):
        with self.assertRaises(mt.SnapshotGone):
            mt.put_record('/k', self.rec())
        self.assertFalse(os.path.exists(mt.trust_file()))

    def test_put_refuses_a_malformed_record(self):
        # `hash` іде в шлях знімка: без перевірки форми `../x` вказав би на будь-яку теку поруч із `trusted/`.
        os.makedirs(os.path.join(self.deai, 'x'))
        self.snap()
        r = self.rec()
        for bad in ({**r, 'hash': '../x'}, {**r, 'hash': 'A' * 64}, {**r, 'hash': 7}, {**r, 'files': 'no'},
                    {**r, 'id': 3}, 'text', None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    mt.put_record('/k', bad)
        self.assertFalse(os.path.exists(mt.trust_file()))

    def test_unreadable_file_is_an_error_and_is_not_overwritten(self):
        os.makedirs(self.deai)
        with open(mt.trust_file(), 'w') as f:
            f.write('{not json')
        before = _slurp(mt.trust_file())
        with self.assertRaises(mt.TrustUnreadable):
            mt.load_records()
        self.snap()
        with self.assertRaises(mt.TrustUnreadable):
            mt.put_record('/k', self.rec())
        with self.assertRaises(mt.TrustUnreadable):
            mt.drop_record('/k')
        self.assertEqual(_slurp(mt.trust_file()), before)

    def test_a_file_that_is_a_directory_or_not_utf8_is_unreadable(self):
        os.makedirs(os.path.join(self.deai, 'trust.json'))
        with self.assertRaises(mt.TrustUnreadable):
            mt.load_records()
        os.rmdir(mt.trust_file())
        with open(mt.trust_file(), 'wb') as f:
            f.write(b'{"modules": {"\xff": 1}}')
        with self.assertRaises(mt.TrustUnreadable):
            mt.load_records()

    def test_a_file_of_the_wrong_shape_is_unreadable_but_an_empty_object_is_fine(self):
        for body in ('[]', '"x"', '{"modules": []}', '{"modules": 3}'):
            with self.subTest(body=body):
                self.write_raw(body)
                with self.assertRaises(mt.TrustUnreadable):
                    mt.load_records()
        self.write_raw('{}')
        self.assertEqual(mt.load_records(), {})

    def test_load_keeps_only_well_formed_records(self):
        good = self.rec()
        self.write_raw({'version': 1, 'modules': {
            '/ok': good,
            '/nohash': {**good, 'hash': 'zz'},
            '/shorthash': {**good, 'hash': 'a' * 63},
            '/upperhash': {**good, 'hash': 'A' * 64},
            '/nofiles': {k: v for k, v in good.items() if k != 'files'},
            '/noid': {**good, 'id': 5},
            '/str': 'x',
            '/list': []}})
        self.assertEqual(list(mt.load_records()), ['/ok'])

    def test_load_is_cached_by_the_file_signature(self):
        self.snap()
        mt.put_record('/k', self.rec())
        first = mt.load_records()
        with mock.patch.object(mt, '_read_file', side_effect=AssertionError('перечитав без змін')):
            self.assertEqual(mt.load_records(), first)
            got = mt.load_records()
            got['/zzz'] = 1                                       # віддається новий словник: кеш не псується
            self.assertNotIn('/zzz', mt.load_records())
        data = json.loads(_slurp(mt.trust_file()))                # інший писар переписав файл — відбиток інший
        data['modules']['/k']['name'] = 'A much longer name than before'
        with open(mt.trust_file(), 'w') as f:
            json.dump(data, f)
        self.assertEqual(mt.load_records()['/k']['name'], 'A much longer name than before')

    def test_a_write_drops_the_cache_even_if_the_signature_did_not_move(self):
        self.snap()
        self.snap('c' * 64)
        with mock.patch.object(mt, '_sig', return_value=(1, 2, 3)):
            mt.put_record('/k1', self.rec())
            self.assertEqual(sorted(mt.load_records()), ['/k1'])  # кеш наповнено
            mt.put_record('/k2', self.rec('c' * 64))
            self.assertEqual(sorted(mt.load_records()), ['/k1', '/k2'])

    def test_records_sig_follows_the_file_and_the_layer(self):
        self.assertIsNone(mt.records_sig())                       # файла нема
        self.snap()
        mt.put_record('/k', self.rec())
        s1 = mt.records_sig()
        self.assertIsNotNone(s1)
        self.snap('c' * 64)
        mt.put_record('/k2', self.rec('c' * 64))
        self.assertNotEqual(mt.records_sig(), s1)
        other = os.path.join(self.home, '.deai')                  # тека «справжньої» домівки при вимкненому шарі
        os.makedirs(other)
        with open(os.path.join(other, 'trust.json'), 'w') as f:
            f.write('{}')
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            os.environ.pop('DEAI_HOME')
            self.assertTrue(os.path.exists(mt.trust_file()))
            self.assertIsNone(mt.records_sig())

    @unittest.skipIf(os.name == 'nt', 'права POSIX')
    def test_an_existing_file_is_secured_before_the_atomic_replace_and_after_it(self):
        self.snap()
        mt.put_record('/k', self.rec())
        os.chmod(mt.trust_file(), 0o644)
        seen, real = [], mt.atomic_write_json

        def spy(path, data, *a, **k):
            seen.append(stat.S_IMODE(os.stat(path).st_mode))     # ДО заміни: атомарна заміна переносить режим цілі
            real(path, data, *a, **k)
            os.chmod(path, 0o644)                                 # а раптом писар лишив ширші права
        with mock.patch.object(mt, 'atomic_write_json', spy):
            mt.put_record('/k2', self.rec())
        self.assertEqual(seen, [0o600])
        self.assertEqual(stat.S_IMODE(os.stat(mt.trust_file()).st_mode), 0o600)

    def test_key_for_is_the_real_path_even_for_a_missing_dir(self):
        real = os.path.join(self.tmp, 'space')
        link = os.path.join(self.tmp, 'link-space')
        os.symlink(real, link)
        self.assertEqual(mt.key_for(link, 'netlify'), os.path.join(real, 'modules', 'netlify'))
        self.assertEqual(mt.key_for(link, 'nope'), os.path.join(real, 'modules', 'nope'))   # теки нема — ключ є

    def test_drop_removes_record_and_only_unreferenced_snapshot(self):
        self.snap('a' * 64)
        mt.put_record('/k1', self.rec('a' * 64))
        mt.put_record('/k2', self.rec('a' * 64))
        self.assertTrue(mt.drop_record('/k1'))
        self.assertTrue(os.path.isdir(mt.snapshot_dir('a' * 64)), 'на знімок ще посилається /k2')
        self.assertTrue(mt.drop_record('/k2'))
        self.assertFalse(os.path.exists(mt.snapshot_dir('a' * 64)))
        self.assertFalse(mt.drop_record('/k2'))
        self.assertEqual(mt.load_records(), {})

    def test_drop_leaves_no_aside_leftover_and_no_other_snapshot_touched(self):
        self.snap('a' * 64)
        self.snap('c' * 64)
        mt.put_record('/k1', self.rec('a' * 64))
        mt.put_record('/k2', self.rec('c' * 64))
        mt.drop_record('/k1')
        self.assertEqual(sorted(os.listdir(mt.trusted_root())), ['c' * 64])

    def test_drop_sweeps_old_leftovers(self):
        self.snap()
        mt.put_record('/k', self.rec())
        old = os.path.join(mt.trusted_root(), '.tmp-dead')
        os.makedirs(os.path.join(old, 'x'))
        past = time.time() - mt.STALE_S - 10
        os.utime(old, (past, past))
        mt.drop_record('/k')
        self.assertFalse(os.path.exists(old))

    def test_drop_does_not_follow_a_hash_that_is_not_a_hash(self):
        # `trust.json` писали не лише ми: `hash` на кшталт `../x` не мусить відсунути й видалити чужу теку поруч із `trusted/`.
        os.makedirs(mt.trusted_root())
        victim = os.path.join(self.deai, 'x')
        os.makedirs(victim)
        self.write_raw({'version': 1, 'modules': {'/k': {**self.rec(), 'hash': '../x'}}})
        self.assertTrue(mt.drop_record('/k'))
        self.assertTrue(os.path.isdir(victim))
        self.assertEqual(json.loads(_slurp(mt.trust_file()))['modules'], {})

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_put_refuses_a_snapshot_that_is_a_link(self):
        decoy = os.path.join(self.tmp, 'decoy')                     # посилання на теку «зі знімком» — чужа, змінна тека
        os.makedirs(decoy)
        os.makedirs(mt.trusted_root())
        os.symlink(decoy, mt.snapshot_dir('a' * 64))
        with self.assertRaises(mt.SnapshotGone):
            mt.put_record('/k', self.rec())
        self.assertFalse(os.path.exists(mt.trust_file()))

    def test_a_hash_with_a_valid_prefix_and_a_path_tail_is_refused(self):
        # `HASH_RE.match` пропустив би `<64 hex>/../x` — а це шлях до `trusted/x`.
        bad = 'a' * 64 + '/../x'
        os.makedirs(mt.snapshot_dir('a' * 64))
        os.makedirs(os.path.join(mt.trusted_root(), 'x'))
        with self.assertRaises(ValueError):
            mt.put_record('/k', self.rec(bad))
        self.assertFalse(os.path.exists(mt.trust_file()))
        self.write_raw({'version': 1, 'modules': {'/k': {**self.rec(), 'hash': bad}}})    # рукописний файл теж не шкодить
        self.assertTrue(mt.drop_record('/k'))
        self.assertTrue(os.path.isdir(os.path.join(mt.trusted_root(), 'x')))

    def test_drop_works_when_the_snapshot_is_already_gone(self):
        self.snap()
        mt.put_record('/k', self.rec())
        os.rmdir(mt.snapshot_dir('a' * 64))
        self.assertTrue(mt.drop_record('/k'))                      # «Забрати довіру» знімає запис і без знімка
        self.assertEqual(mt.load_records(), {})

    def test_put_and_drop_wait_for_the_write_lock(self):
        # Детерміновано: лок тримаємо ми — писар у потоці мусить чекати, а не писати поруч із чужим читанням-зміною-записом.
        self.snap()
        mt.put_record('/k', self.rec())
        calls = {'put': lambda: mt.put_record('/k2', self.rec()), 'drop': lambda: mt.drop_record('/k')}
        for name, call in calls.items():
            with self.subTest(name):
                th = threading.Thread(target=call, daemon=True)
                mt.WRITE_LOCK.acquire()
                try:
                    th.start()
                    th.join(0.3)
                    waiting = th.is_alive()
                finally:
                    mt.WRITE_LOCK.release()
                th.join(5)
                self.assertTrue(waiting, f'{name} не чекав лока')
                self.assertFalse(th.is_alive())

    def test_the_snapshot_is_set_aside_under_the_write_lock(self):
        self.snap()
        mt.put_record('/k', self.rec())
        real, seen = mt._aside, []

        def spy(d):
            seen.append(mt.WRITE_LOCK.locked())
            return real(d)
        with mock.patch.object(mt, '_aside', spy):
            mt.drop_record('/k')
        self.assertEqual(seen, [True])

    def test_a_failed_write_puts_the_snapshot_back_and_keeps_the_record(self):
        sc = mt.scan(self.mod, with_data=True)
        mt.ensure_snapshot(sc)
        mt.put_record('/k', self.rec(sc.hash))
        with mock.patch.object(mt, 'atomic_write_json', side_effect=OSError(errno.EIO, 'disk')):
            with self.assertRaises(OSError):
                mt.drop_record('/k')
        self.assertIn('/k', mt.load_records())                      # довіра лишилась…
        self.assertTrue(mt.verify_snapshot(sc.hash))                # …і знімок на місці, цілий
        self.assertEqual([n for n in os.listdir(mt.trusted_root()) if n.startswith('.old-')], [])

    def test_concurrent_puts_do_not_lose_records(self):
        self.snap()
        real, errs = mt._read_file, []

        def slow():
            data = real()
            time.sleep(0.05)                                       # розширює вікно між читанням і записом
            return data

        def put(i):
            try:
                mt.put_record(f'/k{i}', self.rec())
            except Exception as e:                                 # noqa: BLE001 — зібрати й показати в провалі
                errs.append(e)
        with mock.patch.object(mt, '_read_file', slow):
            ths = [threading.Thread(target=put, args=(i,)) for i in range(5)]
            for t in ths:
                t.start()
            for t in ths:
                t.join(10)
        self.assertEqual(errs, [])
        self.assertEqual(sorted(mt.load_records()), [f'/k{i}' for i in range(5)])


class SnapshotTest(Base):
    def test_snapshot_holds_the_scanned_bytes_read_only(self):
        sc = mt.scan(self.mod, with_data=True)
        _put(self.mod, 'server.py', 'changed after the scan')
        d = mt.ensure_snapshot(sc)
        self.assertEqual(d, mt.snapshot_dir(sc.hash))
        self.assertEqual(_slurp(os.path.join(d, 'server.py')), sc.data['server.py'])
        self.assertTrue(mt.verify_snapshot(sc.hash))
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o500)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, 'server.py')).st_mode), 0o400)

    def test_nested_files_are_written_with_read_only_dirs(self):
        _put(self.mod, 'lib/deep/h.py', 'x = 1')
        sc = mt.scan(self.mod, with_data=True)
        d = mt.ensure_snapshot(sc)
        self.assertEqual(_slurp(os.path.join(d, 'lib', 'deep', 'h.py')), b'x = 1')
        self.assertTrue(mt.verify_snapshot(sc.hash))
        if os.name != 'nt':
            for sub in ('lib', os.path.join('lib', 'deep')):
                self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, sub)).st_mode), 0o500)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, 'lib', 'deep', 'h.py')).st_mode), 0o400)
            self.assertEqual(stat.S_IMODE(os.stat(mt.trusted_root()).st_mode), 0o700)

    def test_intact_snapshot_is_kept(self):
        sc = mt.scan(self.mod, with_data=True)
        d = mt.ensure_snapshot(sc)
        ino = os.stat(d).st_ino
        mt.ensure_snapshot(mt.scan(self.mod, with_data=True))
        self.assertEqual(os.stat(d).st_ino, ino)

    def test_damaged_snapshot_is_detected_and_repaired(self):
        sc = mt.scan(self.mod, with_data=True)
        d = mt.ensure_snapshot(sc)
        os.chmod(d, 0o700)
        p = os.path.join(d, 'server.py')
        os.chmod(p, 0o600)
        with open(p, 'w') as f:
            f.write('tampered')
        mt.forget(d)
        self.assertFalse(mt.verify_snapshot(sc.hash))
        mt.ensure_snapshot(sc)
        self.assertTrue(mt.verify_snapshot(sc.hash))
        self.assertEqual(_slurp(os.path.join(mt.snapshot_dir(sc.hash), 'server.py')), sc.data['server.py'])

    def test_requires_bytes(self):
        with self.assertRaises(ValueError):
            mt.ensure_snapshot(mt.scan(self.mod))

    def test_layer_off_writes_no_snapshot(self):
        sc = mt.scan(self.mod, with_data=True)
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            os.environ.pop('DEAI_HOME')
            with self.assertRaises(RuntimeError):
                mt.ensure_snapshot(sc)
            self.assertFalse(os.path.exists(mt.trusted_root()))

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_link_in_the_snapshot_place_is_never_accepted_and_is_replaced(self):
        # Підсунуте посилання на теку з ТИМИ САМИМИ байтами пройшло б хеш-перевірку, але лишилось би чужим (змінним).
        sc = mt.scan(self.mod, with_data=True)
        decoy = os.path.join(self.tmp, 'decoy')
        for rel, raw in sc.data.items():
            _put(decoy, rel, raw)
        os.makedirs(mt.trusted_root())
        os.symlink(decoy, mt.snapshot_dir(sc.hash))
        self.assertFalse(mt.verify_snapshot(sc.hash))
        d = mt.ensure_snapshot(sc)
        self.assertFalse(os.path.islink(d))
        self.assertTrue(mt.verify_snapshot(sc.hash))
        self.assertTrue(os.path.exists(os.path.join(decoy, 'server.py')))     # чужу теку не чіпали

    def test_verify_rejects_a_bad_hash_before_touching_the_disk(self):
        for bad in ('../x', 'A' * 64, 'a' * 63, None, 5):
            self.assertFalse(mt.verify_snapshot(bad), repr(bad))

    def test_a_failed_write_leaves_no_tmp_dir(self):
        sc = mt.scan(self.mod, with_data=True)
        with mock.patch.object(mt.os, 'rename', side_effect=OSError(errno.EXDEV, 'x')):
            with self.assertRaises(OSError):
                mt.ensure_snapshot(sc)
        self.assertEqual(os.listdir(mt.trusted_root()), [])

    def test_a_parallel_writer_of_the_same_hash_is_not_an_error(self):
        sc = mt.scan(self.mod, with_data=True)

        def racing(src, dst):                                       # паралельний запис встиг першим: у `dst` цілий знімок
            shutil.copytree(src, dst)
            raise OSError(errno.ENOTEMPTY, 'exists')
        with mock.patch.object(mt.os, 'rename', racing):
            d = mt.ensure_snapshot(sc)
        self.assertEqual(d, mt.snapshot_dir(sc.hash))
        self.assertTrue(mt.verify_snapshot(sc.hash))
        self.assertEqual([n for n in os.listdir(mt.trusted_root()) if n.startswith('.tmp-')], [])

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_planted_link_inside_a_snapshot_makes_it_not_intact(self):
        sc = mt.scan(self.mod, with_data=True)
        d = mt.ensure_snapshot(sc)
        os.chmod(d, 0o700)
        os.symlink(os.path.join(self.tmp, 'elsewhere'), os.path.join(d, 'planted'))
        mt.forget(d)
        self.assertFalse(mt.verify_snapshot(sc.hash))                # сканер відмовляє на посиланні: знімок не цілий

    def test_ensure_tightens_wider_dirs_and_forgets_a_stale_cache_entry(self):
        sc = mt.scan(self.mod, with_data=True)
        os.makedirs(mt.trusted_root())
        if os.name != 'nt':
            os.chmod(self.deai, 0o755)
            os.chmod(mt.trusted_root(), 0o755)
        key = os.path.normpath(os.path.abspath(mt.snapshot_dir(sc.hash)))
        mt._CACHE[key] = ('stale', None)                             # застарілий результат скану цього шляху
        mt.ensure_snapshot(sc)
        self.assertNotIn(key, mt._CACHE)
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(os.stat(self.deai).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(mt.trusted_root()).st_mode), 0o700)

    def test_aside_moves_the_dir_and_forgets_the_old_path(self):
        sc = mt.scan(self.mod, with_data=True)
        d = mt.ensure_snapshot(sc)
        mt.scan(d)
        key = os.path.normpath(os.path.abspath(d))
        self.assertIn(key, mt._CACHE)
        aside = mt._aside(d)
        self.assertNotIn(key, mt._CACHE)
        self.assertFalse(os.path.exists(d))
        self.assertTrue(os.path.basename(aside).startswith('.old-'))
        self.assertEqual(os.path.dirname(aside), os.path.dirname(d))
        mt._rmtree(aside)
        self.assertFalse(os.path.exists(aside))

    def test_ensure_sweeps_old_leftovers(self):
        sc = mt.scan(self.mod, with_data=True)
        old = os.path.join(mt.trusted_root(), '.old-dead')
        os.makedirs(os.path.join(old, 'x'))
        past = time.time() - mt.STALE_S - 10
        os.utime(old, (past, past))
        mt.ensure_snapshot(sc)
        self.assertFalse(os.path.exists(old))

    def test_a_snapshot_never_writes_into_a_file_that_is_already_there(self):
        # Платформонезалежно: у «щойно створеній» теці вже лежить файл (жорстке посилання на чужий) — без `O_EXCL` запис
        # пішов би крізь нього в чужий файл (а на ФС без урахування регістру так само зіткнулись би `a.py` і `A.py`).
        sc = mt.Scan('f' * 64, (), 0, None, {'a.py': b'1'})
        outside = _put(self.tmp, 'outside.txt', b'outside')
        planted = os.path.join(mt.trusted_root(), '.tmp-planted')
        os.makedirs(planted)
        os.link(outside, os.path.join(planted, 'a.py'))
        with mock.patch.object(mt.tempfile, 'mkdtemp', return_value=planted):
            with self.assertRaises(FileExistsError):
                mt.ensure_snapshot(sc)
        self.assertEqual(_slurp(outside), b'outside')
        self.assertFalse(os.path.exists(mt.snapshot_dir('f' * 64)))

    def test_ensure_refuses_a_hash_that_is_not_a_hash(self):
        # Хеш іде в шлях знімка, а `ensure_snapshot` уміє відсунути й видалити теку на цьому шляху: з реального `scan` такий
        # хеш недосяжний, але рукотворний `Scan` не мусить зачепити чужу теку.
        victims = [os.path.join(self.deai, 'victim'), os.path.join(mt.trusted_root(), 'victim')]
        os.makedirs(mt.snapshot_dir('a' * 64))
        for v in victims:
            os.makedirs(v, exist_ok=True)
        for bad in ('../victim', 'a' * 64 + '/../victim', 'A' * 64, '', None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    mt.ensure_snapshot(mt.Scan(bad, (), 0, None, {'a.py': b'1'}))
                for v in victims:
                    self.assertTrue(os.path.isdir(v), v)

    def test_sweep_removes_only_old_leftovers(self):
        root = mt.trusted_root()
        old, fresh = os.path.join(root, '.tmp-old'), os.path.join(root, '.old-fresh')
        for d in (old, fresh):
            os.makedirs(os.path.join(d, 'x'))
        past = time.time() - mt.STALE_S - 10
        os.utime(old, (past, past))
        mt.sweep()
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(fresh))

    def test_sweep_never_touches_a_snapshot_or_an_old_file(self):
        root = mt.trusted_root()
        h = 'a' * 64
        keep_dir, keep_file = os.path.join(root, h), os.path.join(root, 'notes.txt')
        os.makedirs(keep_dir)
        open(keep_file, 'w').close()
        past = time.time() - 10 * mt.STALE_S
        for p in (keep_dir, keep_file):
            os.utime(p, (past, past))
        mt.sweep()
        self.assertTrue(os.path.isdir(keep_dir))
        self.assertTrue(os.path.exists(keep_file))

    def test_sweep_removes_read_only_leftovers_and_survives_a_missing_root(self):
        mt.sweep()                                                  # `trusted/` ще нема
        sc = mt.scan(self.mod, with_data=True)
        d = mt.ensure_snapshot(sc)
        left = os.path.join(mt.trusted_root(), '.old-dead')
        os.rename(d, left)                                          # 0500/0400, як після `_aside`
        past = time.time() - mt.STALE_S - 10
        os.utime(left, (past, past))
        mt.sweep()
        self.assertFalse(os.path.exists(left))


class ConfirmTest(Base):
    TEXTS = ('Deai Canvas', 'Trust «x"; do shell script "touch /tmp/pwn" --»?', 'Довіряю', 'Скасувати')

    def test_darwin_text_goes_as_arguments_not_into_the_script(self):
        argv, extra = mt.confirm_command('darwin', *self.TEXTS)
        self.assertEqual(argv[:2], ['osascript', '-e'])
        self.assertNotIn('pwn', argv[2])
        self.assertEqual(argv[3:], [self.TEXTS[1], self.TEXTS[0], self.TEXTS[2], self.TEXTS[3]])
        self.assertEqual(extra, {})

    def test_windows_text_goes_through_the_environment(self):
        argv, extra = mt.confirm_command('win32', *self.TEXTS)
        self.assertEqual(argv[0], 'powershell')
        self.assertNotIn('pwn', ' '.join(argv))
        self.assertEqual(extra['DEAI_CONFIRM_MSG'], self.TEXTS[1])
        self.assertEqual(extra['DEAI_CONFIRM_TITLE'], self.TEXTS[0])

    def test_linux_needs_a_display_and_a_tool(self):
        self.assertIsNone(mt.confirm_command('linux', *self.TEXTS, which=lambda n: '/usr/bin/' + n, env={}))
        argv, _ = mt.confirm_command('linux', *self.TEXTS, which=lambda n: '/usr/bin/zenity' if n == 'zenity' else None,
                                     env={'DISPLAY': ':0'})
        self.assertEqual(argv[0], 'zenity')
        self.assertIn(self.TEXTS[1], argv)
        argv, _ = mt.confirm_command('linux', *self.TEXTS, which=lambda n: '/usr/bin/kdialog' if n == 'kdialog' else None,
                                     env={'WAYLAND_DISPLAY': 'w'})
        self.assertEqual(argv[0], 'kdialog')
        self.assertIn(self.TEXTS[1], argv)
        self.assertIsNone(mt.confirm_command('linux', *self.TEXTS, which=lambda n: None, env={'DISPLAY': ':0'}))

    def test_linux_prefers_zenity_when_both_exist(self):
        argv, _ = mt.confirm_command('linux', *self.TEXTS, which=lambda n: '/usr/bin/' + n, env={'DISPLAY': ':0'})
        self.assertEqual(argv[0], 'zenity')
        self.assertIn(f'--timeout={mt.CONFIRM_TIMEOUT}', argv)

    def test_zenity_shows_the_text_literally(self):
        argv, _ = mt.confirm_command('linux', *self.TEXTS, which=lambda n: '/usr/bin/' + n, env={'DISPLAY': ':0'})
        self.assertIn('--no-markup', argv)

    def test_the_default_answer_is_no_on_macos_and_windows(self):
        self.assertIn('default button noB', mt._OSA)
        self.assertIn('cancel button noB', mt._OSA)
        self.assertIn("'Button2'", mt._PS)

    def test_the_macos_script_times_out_with_the_constant(self):
        self.assertIn(f'giving up after {mt.CONFIRM_TIMEOUT}', mt._OSA)

    def test_interpret(self):
        P = lambda rc, out='': mock.Mock(returncode=rc, stdout=out)  # noqa: E731
        self.assertEqual(mt._interpret('osascript', P(0, 'yes\n')), 'yes')
        self.assertEqual(mt._interpret('osascript', P(0, 'no\n')), 'no')
        self.assertEqual(mt._interpret('osascript', P(0, '')), 'no')
        self.assertEqual(mt._interpret('osascript', P(1, '')), 'unavailable')
        self.assertEqual(mt._interpret('osascript', P(1, 'yes')), 'unavailable')
        self.assertEqual(mt._interpret('powershell', P(0, 'yes\r\n')), 'yes')
        self.assertEqual(mt._interpret('powershell', P(1, 'yes')), 'unavailable')
        self.assertEqual(mt._interpret('zenity', P(0)), 'yes')
        self.assertEqual(mt._interpret('zenity', P(1)), 'no')
        self.assertEqual(mt._interpret('zenity', P(5)), 'no')
        self.assertEqual(mt._interpret('zenity', P(255)), 'unavailable')
        self.assertEqual(mt._interpret('kdialog', P(1)), 'no')
        self.assertEqual(mt._interpret('kdialog', P(0)), 'yes')

    def test_texts_are_cleaned_and_clipped(self):
        title, msg, yes, no = mt.confirm_texts('uk', 'N‮a\ud800me' + 'x' * 200, 'netlify', 'f' * 64, '/p\x07ath')
        self.assertNotIn('‮', msg)
        self.assertNotIn('\ud800', msg)
        msg.encode('utf-8')                                     # пройде в argv
        self.assertNotIn('\x07', msg)
        self.assertIn('/path', msg)
        self.assertIn('ffffffffffff', msg)
        self.assertNotIn('f' * 13, msg)
        self.assertIn('Name' + 'x' * 75 + '…', msg)             # імʼя обрізане до 80 знаків (79 + «…»)
        self.assertNotIn('x' * 76, msg)
        self.assertEqual(set(mt.CONFIRM_TEXT), {'uk', 'en'})
        self.assertEqual(mt.confirm_texts('zz', 'n', 'i', 'f' * 64, '/p'), mt.confirm_texts('uk', 'n', 'i', 'f' * 64, '/p'))
        self.assertEqual((title, yes, no), ('Deai Canvas', 'Довіряю', 'Скасувати'))
        en = mt.confirm_texts('en', 'n', 'i', 'f' * 64, '/p')
        self.assertEqual((en[2], en[3]), ('Trust', 'Cancel'))

    def test_a_lang_that_is_not_a_string_falls_back_to_uk(self):
        want = mt.confirm_texts('uk', 'n', 'i', 'f' * 64, '/p')
        for lang in ([], {}, None, 5, b'en'):
            self.assertEqual(mt.confirm_texts(lang, 'n', 'i', 'f' * 64, '/p'), want, repr(lang))

    def test_line_and_paragraph_separators_are_cleaned(self):
        msg = mt.confirm_texts('uk', 'a\u2028b\u2029c', 'i', 'f' * 64, '/p')[1]
        self.assertNotIn('\u2028', msg)
        self.assertNotIn('\u2029', msg)
        self.assertIn('abc', msg)

    def test_the_module_id_is_cleaned_too(self):
        msg = mt.confirm_texts('uk', 'n', 'i\u202ed\x07', 'f' * 64, '/p')[1]
        self.assertNotIn('\u202e', msg)
        self.assertNotIn('\x07', msg)
        self.assertIn('(id,', msg)                                  # `i` + `d` зійшлись після очищення

    def test_a_long_path_is_clipped_in_the_middle_so_the_module_dir_stays_visible(self):
        path = '/h/' + 'd' * 200 + '/space/modules/netlify'
        msg = mt.confirm_texts('uk', 'n', 'i', 'f' * 64, path)[1]
        self.assertIn('/space/modules/netlify', msg)               # кінець шляху — сама тека модуля
        self.assertIn('/h/ddd', msg)                                # голова теж
        self.assertIn('…', msg)
        self.assertNotIn('d' * 55, msg)
        s = 'abcdefghij' * 20
        self.assertEqual(mt._clean(s, n=10, middle=True), 'abc…efghij')       # 3 + «…» + 6 = 10
        self.assertEqual(mt._clean(s, n=10), 'abcdefghi…')                    # без `middle` — з кінця
        self.assertEqual(mt._clean('short', n=10, middle=True), 'short')

    def test_seam_needs_a_non_default_deai_home(self):
        with mock.patch.dict(os.environ, {mt.SEAM_ENV: 'yes'}):
            self.assertEqual(mt.seam_value(), 'yes')
            with mock.patch.object(mt, '_real_default_home', lambda: os.path.realpath(self.deai)):
                self.assertIsNone(mt.seam_value())
            os.environ.pop('DEAI_HOME')
            self.assertIsNone(mt.seam_value())
        with mock.patch.dict(os.environ, {mt.SEAM_ENV: 'maybe'}):
            self.assertIsNone(mt.seam_value())

    def test_seam_is_off_for_the_default_home_spelled_with_a_tilde(self):
        default = os.path.join(self.home, '.deai')                  # теки ще нема: рішає лише текст шляху
        with mock.patch.object(mt, '_real_default_home', lambda: os.path.realpath(default)), \
                mock.patch.dict(os.environ, {mt.SEAM_ENV: 'yes', 'DEAI_HOME': '~/.deai', 'HOME': self.home}):
            self.assertIsNone(mt.seam_value())

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_seam_is_off_for_a_link_to_a_default_home_that_does_not_exist_yet(self):
        default = os.path.join(self.tmp, 'default-deai')            # перший запуск: типової теки ще нема — лише `realpath`
        link = os.path.join(self.tmp, 'link')
        os.symlink(default, link)
        with mock.patch.object(mt, '_real_default_home', lambda: os.path.realpath(default)), \
                mock.patch.dict(os.environ, {mt.SEAM_ENV: 'yes', 'DEAI_HOME': link}):
            self.assertIsNone(mt.seam_value())

    def test_seam_is_off_for_the_default_home_in_another_letter_case(self):
        default = os.path.join(self.tmp, 'Default-Deai')
        os.makedirs(default)
        other = os.path.join(self.tmp, 'default-deai')
        if not os.path.exists(other):
            self.skipTest('ФС чутлива до регістру: ту саму теку іншим написанням не відкрити')
        with mock.patch.object(mt, '_real_default_home', lambda: os.path.realpath(default)), \
                mock.patch.dict(os.environ, {mt.SEAM_ENV: 'yes', 'DEAI_HOME': other}):
            self.assertNotEqual(os.path.realpath(other), os.path.realpath(default))   # рядки різні, тека — та сама
            self.assertIsNone(mt.seam_value())

    @unittest.skipIf(os.name == 'nt', 'pwd і посилання')
    def test_the_default_home_is_resolved_through_a_linked_user_home(self):
        user = os.path.join(self.tmp, 'user')
        os.makedirs(user)
        link = os.path.join(self.tmp, 'user-link')
        os.symlink(user, link)
        with mock.patch('pwd.getpwuid', return_value=types.SimpleNamespace(pw_dir=link)):
            self.assertEqual(mt._real_default_home(), os.path.join(user, '.deai'))
            with mock.patch.dict(os.environ, {mt.SEAM_ENV: 'yes', 'DEAI_HOME': os.path.join(user, '.deai')}):
                self.assertIsNone(mt.seam_value())

    def test_the_default_home_comes_from_the_user_database_not_from_HOME(self):
        # HOME підмінено на тимчасову (так роблять усі тести): `DEAI_HOME` під нею — НЕ справжній `~/.deai`, шов діє.
        own = os.path.join(self.home, '.deai')
        self.assertNotEqual(mt._real_default_home(), os.path.realpath(own))
        with mock.patch.dict(os.environ, {mt.SEAM_ENV: 'yes', 'DEAI_HOME': own}):
            self.assertEqual(mt.seam_value(), 'yes')

    def test_confirm_uses_the_seam_and_never_a_window(self):
        for v in ('yes', 'no', 'unavailable'):
            with mock.patch.dict(os.environ, {mt.SEAM_ENV: v}), \
                    mock.patch.object(mt.subprocess, 'run', side_effect=AssertionError('вікно в тесті')):
                self.assertEqual(mt.confirm(*self.TEXTS), v)

    def test_confirm_runs_the_command_and_maps_failures(self):
        os.environ.pop(mt.SEAM_ENV, None)
        with mock.patch.object(mt, 'confirm_command', return_value=(['osascript', '-e', 's'], {})), \
                mock.patch.object(mt.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='yes')):
            self.assertEqual(mt.confirm(*self.TEXTS), 'yes')
        with mock.patch.object(mt, 'confirm_command', return_value=(['osascript'], {})), \
                mock.patch.object(mt.subprocess, 'run', side_effect=mt.subprocess.TimeoutExpired('osascript', 1)):
            self.assertEqual(mt.confirm(*self.TEXTS), 'no')
        with mock.patch.object(mt, 'confirm_command', return_value=(['osascript'], {})), \
                mock.patch.object(mt.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(mt.confirm(*self.TEXTS), 'unavailable')
        with mock.patch.object(mt, 'confirm_command', return_value=None):
            self.assertEqual(mt.confirm(*self.TEXTS), 'unavailable')

    def test_confirm_hands_the_extra_environment_a_timeout_and_no_stdin_to_the_process(self):
        os.environ.pop(mt.SEAM_ENV, None)
        with mock.patch.object(mt, 'confirm_command', return_value=(['powershell'], {'DEAI_CONFIRM_MSG': 'm'})), \
                mock.patch.object(mt.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='no')) as run:
            self.assertEqual(mt.confirm(*self.TEXTS), 'no')
        kw = run.call_args.kwargs
        self.assertEqual(kw['env']['DEAI_CONFIRM_MSG'], 'm')
        self.assertEqual(kw['env']['HOME'], self.home)              # решта оточення збережена
        self.assertEqual(kw['timeout'], mt.CONFIRM_TIMEOUT + 10)
        self.assertIs(kw['stdin'], mt.subprocess.DEVNULL)

    def test_ask_one_window_at_a_time(self):
        gate, inside = threading.Event(), threading.Event()

        def slow(*a):
            inside.set()
            gate.wait(5)
            return 'yes'
        with mock.patch.object(mt, 'confirm', slow):
            box = []
            th = threading.Thread(target=lambda: box.append(mt.ask('/k', 'h', self.TEXTS)))
            th.start()
            inside.wait(5)
            self.assertEqual(mt.ask('/k2', 'h2', self.TEXTS), 'busy')
            gate.set()
            th.join(5)
        self.assertEqual(box, ['yes'])

    def test_ask_releases_the_window_slot_even_if_the_window_fails(self):
        with mock.patch.object(mt, 'confirm', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                mt.ask('/k', 'h', self.TEXTS)
        with mock.patch.object(mt, 'confirm', return_value='yes'):
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS), 'yes')

    def test_ask_cools_down_after_a_decline(self):
        clock = [100.0]
        with mock.patch.object(mt, 'confirm', return_value='no') as c:
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: clock[0]), 'no')
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: clock[0] + 5), 'declined')
            self.assertEqual(c.call_count, 1)
            self.assertEqual(mt.ask('/k', 'other', self.TEXTS, now=lambda: clock[0] + 5), 'no')
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: clock[0] + mt.DECLINE_COOLDOWN + 1), 'no')

    def test_only_a_decline_starts_the_cooldown_and_clear_forgets_it(self):
        with mock.patch.object(mt, 'confirm', return_value='yes') as c:
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: 1.0), 'yes')
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: 2.0), 'yes')
            self.assertEqual(c.call_count, 2)
        with mock.patch.object(mt, 'confirm', return_value='unavailable') as c:
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: 3.0), 'unavailable')
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: 4.0), 'unavailable')
            self.assertEqual(c.call_count, 2)
        with mock.patch.object(mt, 'confirm', return_value='no') as c:
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: 5.0), 'no')
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: 6.0), 'declined')
            mt.clear_declined()
            self.assertEqual(mt.ask('/k', 'h', self.TEXTS, now=lambda: 6.0), 'no')
            self.assertEqual(c.call_count, 2)


if __name__ == '__main__':
    unittest.main()
