"""`ops/build_site.py`: копія landing/ для Pages без README.md і з найбільшим тегом vX.Y.Z у [data-version]."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
import build_site as bs  # noqa: E402

HTML = '<footer><p class="footer-version"><a href="x" data-version>v0.39.1</a> · Beta</p></footer>'


class LatestTagTest(unittest.TestCase):
    def test_numeric_order(self):
        self.assertEqual(bs.latest_tag(['v0.9.9', 'v0.10.0', 'v0.2.0']), 'v0.10.0')

    def test_ignores_non_release_tags(self):
        self.assertEqual(bs.latest_tag(['v1.0.0-rc1', 'backup-2026', 'v2', 'v0.3.0', 'v01.0.0']), 'v0.3.0')

    def test_no_tags(self):
        self.assertIsNone(bs.latest_tag([]))


class InjectTest(unittest.TestCase):
    def test_replaces_the_version(self):
        self.assertEqual(bs.inject_version(HTML, 'v0.40.0'), HTML.replace('v0.39.1', 'v0.40.0'))

    def test_needs_exactly_one_marker(self):
        for html in ('<p>no marker</p>', HTML + HTML, '<a data-versions>v1.0.0</a>'):
            with self.subTest(html=html), self.assertRaises(ValueError):
                bs.inject_version(html, 'v0.40.0')


class BuildTest(unittest.TestCase):
    def make_src(self, d):
        src = os.path.join(d, 'landing')
        os.makedirs(os.path.join(src, 'assets'))
        for name, text in (('index.html', HTML), ('README.md', 'readme'), ('.DS_Store', 'x'), ('assets/a.webp', 'img')):
            with open(os.path.join(src, name), 'w', encoding='utf-8') as f:
                f.write(text)
        return src

    def test_copies_without_readme_and_writes_the_version(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, '_site')
            bs.build(self.make_src(d), out, 'v0.40.0')
            self.assertEqual(sorted(os.listdir(out)), ['assets', 'index.html'])
            self.assertTrue(os.path.isfile(os.path.join(out, 'assets', 'a.webp')))
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                self.assertIn('data-version>v0.40.0<', f.read())

    def test_without_a_tag_the_page_is_copied_as_is(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, '_site')
            bs.build(self.make_src(d), out, None)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                self.assertEqual(f.read(), HTML)

    def test_refuses_an_existing_out_folder(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, '_site')
            os.makedirs(out)
            with self.assertRaises(FileExistsError):
                bs.build(self.make_src(d), out, 'v0.40.0')
            self.assertEqual(os.listdir(out), [])

    def test_real_landing_has_one_marker(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, '_site')
            bs.build(os.path.join(ROOT, 'landing'), out, 'v9.9.9')
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                self.assertIn('data-version>v9.9.9<', f.read())


if __name__ == '__main__':
    unittest.main()
