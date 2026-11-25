"""`ops/release_notes.py`: секція CHANGELOG для тега `vX.Y.Z` — текст GitHub Release."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
import release_notes as rn  # noqa: E402

CL = """# Changelog

Intro.

## [0.40.0] — 01.12.2026

Headline paragraph.

### Додано
- Thing one.

## [0.39.1] — 25.11.2026

Older.
"""
PKG = json.dumps({'name': 'deai-canvas', 'version': '0.40.0'})


class SectionTest(unittest.TestCase):
    def test_takes_only_its_section(self):
        body = rn.section(CL, '0.40.0')
        self.assertTrue(body.startswith('Headline paragraph.'))
        self.assertIn('- Thing one.', body)
        self.assertNotIn('Older.', body)
        self.assertNotIn('## [', body)

    def test_last_section_runs_to_the_end(self):
        self.assertEqual(rn.section(CL, '0.39.1'), 'Older.')

    def test_missing_section(self):
        with self.assertRaises(rn.NotesError):
            rn.section(CL, '0.41.0')

    def test_version_prefix_does_not_match(self):
        with self.assertRaises(rn.NotesError):
            rn.section(CL, '0.39')

    def test_empty_section(self):
        with self.assertRaises(rn.NotesError):
            rn.section('## [1.0.0] — 01.01.2027\n\n## [0.9.0] — 01.12.2026\nx\n', '1.0.0')


class NotesTest(unittest.TestCase):
    def test_section_then_footer(self):
        out = rn.notes('v0.40.0', CL, PKG)
        self.assertTrue(out.startswith('Headline paragraph.'))
        self.assertIn(rn.FOOTER.strip(), out)
        self.assertLess(out.index('- Thing one.'), out.index(rn.FOOTER.strip()))

    def test_tag_must_be_a_release_tag(self):
        for tag in ('0.40.0', 'v0.40', 'v0.40.0-rc1', 'v01.2.3', 'v0.40.0\n', 'release'):
            with self.subTest(tag=tag), self.assertRaises(rn.NotesError):
                rn.notes(tag, CL, PKG)

    def test_package_version_must_match(self):
        with self.assertRaises(rn.NotesError):
            rn.notes('v0.40.0', CL, json.dumps({'version': '0.39.1'}))

    def test_package_must_be_json_object(self):
        for bad in ('nope', '[]'):
            with self.subTest(bad=bad), self.assertRaises(rn.NotesError):
                rn.notes('v0.40.0', CL, bad)


class CliTest(unittest.TestCase):
    def run_cli(self, *args, cwd):
        script = os.path.join(ROOT, 'ops', 'release_notes.py')
        return subprocess.run([sys.executable, '-B', script, *args], cwd=cwd, capture_output=True, text=True)

    def write_repo(self, d):
        with open(os.path.join(d, 'CHANGELOG.md'), 'w', encoding='utf-8') as f:
            f.write(CL)
        with open(os.path.join(d, 'package.json'), 'w', encoding='utf-8') as f:
            f.write(PKG)

    def test_prints_notes(self):
        with tempfile.TemporaryDirectory() as d:
            self.write_repo(d)
            r = self.run_cli('v0.40.0', cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('- Thing one.', r.stdout)

    def test_fails_with_a_reason(self):
        with tempfile.TemporaryDirectory() as d:
            self.write_repo(d)
            r = self.run_cli('v9.9.9', cwd=d)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, '')
        self.assertIn('release_notes:', r.stderr)


class RepoTest(unittest.TestCase):
    def test_current_version_has_a_section(self):
        with open(os.path.join(ROOT, 'package.json'), encoding='utf-8') as f:
            version = json.load(f)['version']
        with open(os.path.join(ROOT, 'CHANGELOG.md'), encoding='utf-8') as f:
            self.assertTrue(rn.section(f.read(), version))


if __name__ == '__main__':
    unittest.main()
