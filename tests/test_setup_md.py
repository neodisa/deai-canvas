"""`SETUP.md` (0.33.0) — інструкція для агента: кожен маршрут `/api/…` існує в `serve.py`, кожен файл репо, на який вона
посилається, існує; правила про секрети й системне ПЗ на місці."""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import spaces_guard  # noqa: E402


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class SetupMd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Тест лише читає файли, але в ньому названо маршрути просторів: охоронець `test_serve` вимагає явний `DEAI_HOME`.
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {'DEAI_HOME': tmp.name})
        patcher.start()
        cls.addClassCleanup(patcher.stop)
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

    def test_vercel_enable_replaces_the_default_publish_module_with_real_keys(self):
        # 0.33.0: кожен новий простір уже має `static-publish` з роллю `publish` → без `replace` буде 409 `role-taken`
        line = next(l for l in self.md.splitlines() if '"id": "vercel-publish"' in l)
        self.assertIn('"replace": true', line)
        with open(os.path.join(REPO, 'app', 'modules', 'vercel-publish', 'module.json'), encoding='utf-8') as f:
            keys = {x['key']: x['type'] for x in json.load(f)['settings']}
        self.assertEqual(keys['token'], 'secret')
        self.assertEqual(keys['password'], 'secret')
        self.assertIn('"secrets"', line)

    def test_demo_task_is_retry_safe(self):
        line = next(l for l in self.md.splitlines() if 'POST /api/demo-task' in l)
        self.assertIn('"reuse": true', line)

    def test_api_address_follows_the_prompt(self):
        self.assertIn('http://127.0.0.1:8765', self.md)
        self.assertRegex(self.md, r'address (named )?in the prompt|prompt names')

    def test_readme_has_both_install_prompts_and_no_legacy_quick_start(self):
        with open(os.path.join(REPO, 'README.md'), encoding='utf-8') as f:
            readme = f.read()
        self.assertIn('Install Deai Canvas: clone https://github.com/neodisa/deai-canvas.git into ~/deai-canvas and follow '
                      '~/deai-canvas/SETUP.md.', readme)
        self.assertIn('Встанови Deai Canvas: склонуй https://github.com/neodisa/deai-canvas.git у ~/deai-canvas і зроби все за '
                      '~/deai-canvas/SETUP.md.', readme)
        self.assertNotIn('cp tasks.example.json tasks.json', readme)
        self.assertIn('@AGENTS.md', readme)


if __name__ == '__main__':
    unittest.main()
