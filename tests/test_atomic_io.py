"""`atomic_io.atomic_write_json`: опційна довговічність (`fsync=True`) і `fsync_path`; усі решта викликачів — без fsync."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
import atomic_io  # noqa: E402


class AtomicFsync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, 'x.json')

    def test_default_never_syncs(self):
        with mock.patch.object(atomic_io, 'fsync_path') as fp, mock.patch.object(atomic_io.os, 'fsync') as fs:
            atomic_io.atomic_write_json(self.path, {'a': 1})
        fp.assert_not_called()
        fs.assert_not_called()
        with open(self.path) as f:
            self.assertEqual(json.load(f), {'a': 1})

    def test_opt_in_syncs_file_and_directory(self):
        with mock.patch.object(atomic_io, 'fsync_path') as fp:
            atomic_io.atomic_write_json(self.path, {'a': 2}, fsync=True)
        paths = [c.args[0] for c in fp.call_args_list]
        self.assertEqual(paths, [os.path.realpath(self.path), os.path.realpath(self.tmp)])
        with open(self.path) as f:
            self.assertEqual(json.load(f), {'a': 2})

    def test_fsync_failure_after_rename_keeps_the_file_and_raises_unconfirmed(self):
        """Збій `fsync` ПІСЛЯ `os.replace`: файл уже на місці (не «обрізаний і не записаний»), виняток — окремий підклас `OSError`."""
        with mock.patch.object(atomic_io, 'fsync_path', side_effect=OSError('no fsync')):
            with self.assertRaises(atomic_io.DurabilityUnconfirmed) as cm:
                atomic_io.atomic_write_json(self.path, {'a': 3}, fsync=True)
        self.assertIsInstance(cm.exception, OSError)
        with open(self.path) as f:
            self.assertEqual(json.load(f), {'a': 3})
        self.assertEqual([n for n in os.listdir(self.tmp) if n.endswith(atomic_io.TMP_SUFFIX)], [])

    def test_failure_before_the_rename_is_still_a_plain_error(self):
        with mock.patch.object(atomic_io.os, 'replace', side_effect=OSError('boom')):
            with self.assertRaises(OSError) as cm:
                atomic_io.atomic_write_json(self.path, {'a': 4}, fsync=True)
        self.assertNotIsInstance(cm.exception, atomic_io.DurabilityUnconfirmed)
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(os.listdir(self.tmp), [])

    def test_fsync_path_flushes_a_file_and_a_directory(self):
        open(self.path, 'w').close()
        with mock.patch.object(atomic_io, '_fcntl', None), mock.patch.object(atomic_io.os, 'fsync') as fs:
            atomic_io.fsync_path(self.path)
            atomic_io.fsync_path(self.tmp)
        self.assertEqual(fs.call_count, 2)

    def test_fsync_path_prefers_full_fsync_when_available(self):
        open(self.path, 'w').close()
        fcntl = mock.Mock(F_FULLFSYNC=51)
        with mock.patch.object(atomic_io, '_fcntl', fcntl), mock.patch.object(atomic_io.os, 'fsync') as fs:
            atomic_io.fsync_path(self.path)
        fcntl.fcntl.assert_called_once()
        fs.assert_not_called()


if __name__ == '__main__':
    unittest.main()
