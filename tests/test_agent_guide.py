"""Гайд агента завжди актуальний (23.11.2026): теми `docs/agents/*.md` і `app/modules/<id>/agent.md`, індекс блоку, мітка
`guide`, живий `GET /api/agent-guide`, автооновлення блоків при старті. Усе — у тимчасових теках; справжні `~/.deai` не чіпаються."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
sys.path.insert(0, HERE)
import agents_md  # noqa: E402
import spaces_guard  # noqa: E402


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def _wb(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _rb(path):
    with open(path, 'rb') as f:
        return f.read()


class Topics(unittest.TestCase):
    """Теми, індекс і мітка на підставлених теках (`DOCS`, `MODULES`, `TEMPLATE`)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='agent-guide-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.docs = os.path.join(self.tmp, 'docs')
        self.mods = os.path.join(self.tmp, 'modules')
        self.tpl = os.path.join(self.tmp, 'agents.md')
        _w(os.path.join(self.docs, 'pages.md'), '# Pages\nPages of an iteration.\n\nbody\n')
        _w(os.path.join(self.docs, 'comments.md'), '# Comments\nPins and replies.\n')
        _w(os.path.join(self.docs, '_internal.txt'), '/api/x — y\n')
        _w(os.path.join(self.docs, '_draft.md'), '# Draft\nnot a topic\n')
        _w(os.path.join(self.mods, 'zeta', 'agent.md'), '# Zeta\nA module.\n')
        os.makedirs(os.path.join(self.mods, 'alpha'))          # модуль без agent.md — не тема
        _w(self.tpl, '<!-- deai:begin v{version} · x -->\n# T (guide {guide})\ncurl have={guide}\n{index}\n<!-- deai:end -->\n')
        for name, val in (('DOCS', self.docs), ('MODULES', self.mods), ('TEMPLATE', self.tpl)):
            p = mock.patch.object(agents_md, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_topics_are_docs_then_modules_in_order(self):
        self.assertEqual([n for n, _ in agents_md.topics()], ['comments', 'pages', 'module-zeta'])

    def test_topic_text_and_unknown_names(self):
        self.assertEqual(agents_md.topic_text('pages'), '# Pages\nPages of an iteration.\n\nbody\n')
        self.assertEqual(agents_md.topic_text('module-zeta'), '# Zeta\nA module.\n')
        for bad in ('nope', '../pages', 'pages.md', '_draft', '_internal', 'module-alpha', '', None, 5):
            with self.subTest(bad=bad):
                self.assertIsNone(agents_md.topic_text(bad))

    def test_index_has_a_line_per_topic(self):
        self.assertEqual(agents_md.index_lines(),
                         '- `comments` — Pins and replies.\n- `pages` — Pages of an iteration.\n- `module-zeta` — A module.')

    def test_no_docs_folder_gives_no_topics(self):
        with mock.patch.object(agents_md, 'DOCS', os.path.join(self.tmp, 'none')), \
                mock.patch.object(agents_md, 'MODULES', os.path.join(self.tmp, 'none')):
            self.assertEqual(agents_md.topics(), [])
            self.assertEqual(agents_md.index_lines(), '')

    def test_the_label_is_the_hash_of_the_text_in_both_places(self):
        b = agents_md.render_block(version='1.2.0')
        g = agents_md.guide_of(b)
        self.assertRegex(g, r'^[0-9a-f]{8}$')
        self.assertIn(f'# T (guide {g})', b)
        self.assertIn(f'have={g}', b)
        for left in ('{guide}', '{index}', '{version}'):
            self.assertNotIn(left, b)
        self.assertEqual(g, agents_md.guide_hash(b.replace(g, '')))

    def test_a_version_bump_keeps_the_label(self):
        self.assertEqual(agents_md.guide_of(agents_md.render_block(version='1.2.0')),
                         agents_md.guide_of(agents_md.render_block(version='1.3.0')))

    def test_a_topic_change_changes_the_label(self):
        before = agents_md.guide_of(agents_md.render_block(version='1.2.0'))
        _w(os.path.join(self.docs, 'pages.md'), '# Pages\nPages, folders and groups.\n')
        self.assertNotEqual(before, agents_md.guide_of(agents_md.render_block(version='1.2.0')))

    def test_a_new_topic_makes_an_older_file_outdated(self):
        d = tempfile.mkdtemp(prefix='agent-guide-space-')
        self.addCleanup(shutil.rmtree, d, True)
        _w(os.path.join(d, 'AGENTS.md'), agents_md.render_block(version='1.2.0'))
        self.assertFalse(agents_md.status(d, version='1.3.0')['outdated'])   # той самий текст — не застарів
        _w(os.path.join(self.docs, 'flow.md'), '# Flow\nScreens and arrows.\n')
        self.assertTrue(agents_md.status(d, version='1.3.0')['outdated'])

    def test_topic_summary_handles_crlf_and_short_text(self):
        self.assertEqual(agents_md.topic_summary('# A\r\nsummary\r\nbody\r\n'), 'summary')
        self.assertEqual(agents_md.topic_summary('# only'), '')

    def test_topics_sort_by_name_not_file_name(self):
        _w(os.path.join(self.docs, 'a.md'), '# A\nfirst\n')
        _w(os.path.join(self.docs, 'a-b.md'), '# AB\nsecond\n')
        self.assertEqual([n for n, _ in agents_md.topics()], ['a', 'a-b', 'comments', 'pages', 'module-zeta'])

    def test_the_module_prefix_is_reserved_for_modules(self):
        _w(os.path.join(self.docs, 'module-zeta.md'), '# Fake\nfake\n')
        self.assertEqual([n for n, _ in agents_md.topics()].count('module-zeta'), 1)
        self.assertEqual(agents_md.topic_text('module-zeta'), '# Zeta\nA module.\n')

    def test_a_name_with_a_newline_is_not_a_topic(self):
        _w(os.path.join(self.docs, 'bad\n.md'), '# Bad\nx\n')
        self.assertNotIn('bad\n', [n for n, _ in agents_md.topics()])

    def test_invalid_utf8_in_a_topic_does_not_break_the_block(self):
        d = tempfile.mkdtemp(prefix='agent-guide-space-')
        self.addCleanup(shutil.rmtree, d, True)
        _w(os.path.join(d, 'AGENTS.md'), agents_md.render_block(version='1.2.0'))
        _wb(os.path.join(self.docs, 'pages.md'), b'# Pages\nbad \xff byte\n')
        self.assertRegex(agents_md.guide_of(agents_md.render_block(version='1.2.0')), r'^[0-9a-f]{8}$')
        agents_md.status(d, version='1.3.0')

    def test_guide_of_without_a_label(self):
        for text in (None, '', '# no label\n', '(guide XYZ)'):
            with self.subTest(text=text):
                self.assertIsNone(agents_md.guide_of(text))


if __name__ == '__main__':
    unittest.main()
