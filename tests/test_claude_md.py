"""CLAUDE.md простору (0.33.0, «Перший запуск»): стан і «Підключити» — `agents_md.claude_status|claude_ensure|claude_connect`.

Claude Code 2.1.322 не читає AGENTS.md, якщо вище по теках є будь-який CLAUDE.md; рядок `@AGENTS.md` у CLAUDE.md теки простору
це лагодить. Наявний CLAUDE.md змінюється лише «Підключити» — дописом `@AGENTS.md` і порожнього рядка НА ПОЧАТОК, решта байт у байт.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
import agents_md  # noqa: E402


class ClaudeMd(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='claude-md-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.f = os.path.join(self.dir, 'CLAUDE.md')

    def put(self, b):
        with open(self.f, 'wb') as fh:
            fh.write(b)

    def get(self):
        with open(self.f, 'rb') as fh:
            return fh.read()

    def state(self):
        return agents_md.claude_status(self.dir)['state']

    def test_status_missing_carries_the_path(self):
        self.assertEqual(agents_md.claude_status(self.dir), {'state': 'missing', 'path': self.f})

    def test_status_ok_for_an_import_line_anywhere(self):
        for line in (b'@AGENTS.md', b'  @AGENTS.md  ', b'@./AGENTS.md', b'@AGENTS.md\r', b'\t@AGENTS.md'):
            with self.subTest(line=line):
                self.put(b'# mine\n' + line + b'\nmore\n')
                self.assertEqual(self.state(), 'ok')

    def test_status_no_import_when_the_line_is_not_an_import(self):
        for text in (b'# mine\n', b'see @AGENTS.md\n', b'@AGENTS.mdx\n', b'`@AGENTS.md`\n', b''):
            with self.subTest(text=text):
                self.put(text)
                self.assertEqual(self.state(), 'no-import')

    def test_status_unreadable_for_a_folder_and_a_symlink(self):
        os.mkdir(self.f)
        self.assertEqual(self.state(), 'unreadable')
        os.rmdir(self.f)
        other = os.path.join(self.dir, 'other.md')
        with open(other, 'w') as fh:
            fh.write('@AGENTS.md\n')
        os.symlink(other, self.f)
        self.assertEqual(self.state(), 'unreadable')

    def test_ensure_creates_only_when_absent(self):
        self.assertTrue(agents_md.claude_ensure(self.dir))
        self.assertEqual(self.get(), b'@AGENTS.md\n')
        self.put(b'mine\n')
        self.assertFalse(agents_md.claude_ensure(self.dir))
        self.assertEqual(self.get(), b'mine\n')

    def test_connect_creates_a_missing_file(self):
        st = agents_md.claude_connect(self.dir)
        self.assertEqual(st, {'state': 'ok', 'path': self.f})
        self.assertEqual(self.get(), b'@AGENTS.md\n')

    def test_connect_prepends_and_keeps_every_byte_and_the_mode(self):
        mine = 'Мої правила\r\nбез кінця'.encode() + b'\xff\xfe'
        self.put(mine)
        os.chmod(self.f, 0o600)
        st = agents_md.claude_connect(self.dir)
        self.assertEqual(st['state'], 'ok')
        self.assertEqual(self.get(), b'@AGENTS.md\n\n' + mine)
        self.assertEqual(os.stat(self.f).st_mode & 0o777, 0o600)
        self.assertEqual(sorted(os.listdir(self.dir)), ['CLAUDE.md'], 'тимчасовий файл лишився')

    def test_connect_is_a_noop_when_already_imported(self):
        self.put(b'# x\n@./AGENTS.md\n')
        agents_md.claude_connect(self.dir)
        self.assertEqual(self.get(), b'# x\n@./AGENTS.md\n')

    def test_connect_refuses_a_symlink_and_leaves_the_target(self):
        other = os.path.join(self.dir, 'other.md')
        with open(other, 'wb') as fh:
            fh.write(b'theirs\n')
        os.symlink(other, self.f)
        with self.assertRaises(OSError):
            agents_md.claude_connect(self.dir)
        with open(other, 'rb') as fh:
            self.assertEqual(fh.read(), b'theirs\n')
        self.assertTrue(os.path.islink(self.f))

    def test_connect_detects_a_change_between_read_and_replace(self):
        self.put(b'mine\n')
        real = agents_md._claude_read
        calls = []

        def racing(d):
            calls.append(1)
            if len(calls) == 2:                 # друге читання — звірка перед заміною
                with open(self.f, 'ab') as fh:
                    fh.write(b'other\n')
            return real(d)

        with mock.patch.object(agents_md, '_claude_read', racing):
            with self.assertRaises(ValueError) as cm:
                agents_md.claude_connect(self.dir)
        self.assertEqual(str(cm.exception), 'changed')
        self.assertEqual(self.get(), b'mine\nother\n')
        self.assertEqual(sorted(os.listdir(self.dir)), ['CLAUDE.md'])


if __name__ == '__main__':
    unittest.main()
