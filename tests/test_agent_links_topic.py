"""Тема `tasks` довідки агента описує формат адреси `/app/#…` і не розходиться з `app/location-model.js`."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


class LinksSection(unittest.TestCase):
    def test_section_lives_in_the_tasks_topic_and_the_index_line_is_unchanged(self):
        text = read('docs', 'agents', 'tasks.md')
        lines = text.split('\n')
        self.assertEqual(lines[0], '# Tasks')
        self.assertEqual(lines[1], 'Tasks of a space: list, create, switch, rename, tags, trash.')
        self.assertIn('\n## Links\n', text)

    def test_documents_every_key_of_the_location_model(self):
        model = read('app', 'location-model.js')
        keys = re.search(r'LOC_KEYS\s*=\s*\[([^\]]*)\]', model).group(1)
        names = re.findall(r'"([a-z]+)"', keys) + ['m', 'v', 'h']
        section = read('docs', 'agents', 'tasks.md').split('\n## Links\n', 1)[1]
        for k in names:
            self.assertRegex(section, r'`%s=' % re.escape(k), f'key {k}= not documented in the Links section')

    def test_shows_the_address_shape(self):
        section = read('docs', 'agents', 'tasks.md').split('\n## Links\n', 1)[1]
        self.assertIn('/app/#', section)
        self.assertIn('encodeURIComponent', section)


if __name__ == '__main__':
    unittest.main()
