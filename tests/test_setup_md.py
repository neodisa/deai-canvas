"""`SETUP.md` (0.33.0) — інструкція для агента: кожен маршрут `/api/…` існує в `serve.py`, кожен файл репо, на який вона
посилається, існує; правила про секрети й системне ПЗ на місці."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


class SetupMd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(REPO, 'SETUP.md'), encoding='utf-8') as f:
            cls.md = f.read()
        with open(os.path.join(REPO, 'app', 'serve.py'), encoding='utf-8') as f:
            cls.serve = f.read()

    def test_every_api_route_exists(self):
        paths = sorted(set(re.findall(r'/api/[a-z][a-z-]*', self.md)))
        for p in ('/api/setup', '/api/space-new', '/api/modules', '/api/module-enable', '/api/module-settings',
                  '/api/module-check', '/api/demo-task', '/api/claude-status'):
            self.assertIn(p, paths)
        for p in paths:
            with self.subTest(path=p):
                self.assertIn(f"'{p}'", self.serve)

    def test_every_repo_path_exists(self):
        found = sorted(set(re.findall(r'<deai>/([A-Za-z0-9_./-]+[A-Za-z0-9_])', self.md)))
        self.assertIn('ops/canvas-app/install.sh', found)
        self.assertIn('start.command', found)
        for rel in found:
            with self.subTest(path=rel):
                self.assertTrue(os.path.exists(os.path.join(REPO, rel)), rel)

    def test_rules_and_clone_url(self):
        self.assertIn('git clone https://github.com/neodisa/deai-canvas.git ~/deai-canvas', self.md)
        self.assertIn('`secrets`', self.md)
        self.assertIn('sudo', self.md)
        self.assertIn('npx playwright install chromium', self.md)
        self.assertNotRegex(self.md, r'[а-яіїєґА-ЯІЇЄҐ]', 'SETUP.md — англійською (агент відповідає людині її мовою)')


if __name__ == '__main__':
    unittest.main()
