"""Охоронець «мережі в тестах нема» (0.23.0): живі сервери фікстури не ходять у remote оновлень і не мають адреси відгуку."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, 'live', 'fixture.mjs')
REQUIRED = ('DEAI_NO_UPDATE_CHECK', 'DEAI_FEEDBACK_URL', 'DEAI_FEEDBACK_KEY')


class FixtureEnv(unittest.TestCase):
    def test_live_fixture_env_blocks_update_check_and_feedback(self):
        """`env:` дочірнього сервера фікстури задає всі три змінні (`DEAI_NO_UPDATE_CHECK` — `"1"`, адреса й ключ відгуку — порожні)."""
        with open(FIXTURE, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'\benv:\s*\{(.*?)\n\s*\.\.\.env,', src, re.S)
        self.assertIsNotNone(m, 'не знайшли обʼєкт env у spawn() фікстури')
        body = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S)      # коментарі не рахуються
        for key in REQUIRED:
            self.assertRegex(body, r'\b%s:\s*"' % key, key)
        self.assertRegex(body, r'\bDEAI_NO_UPDATE_CHECK:\s*"1"')
        self.assertRegex(body, r'\bDEAI_FEEDBACK_URL:\s*""')
        self.assertRegex(body, r'\bDEAI_FEEDBACK_KEY:\s*""')


ROOT = os.path.dirname(HERE)
# Маркери «відгук вимкнено»: файл, що запускає сервер (`serve_main` або підпроцес `serve.py`), мусить містити один із них.
MARKERS = ("serve.feedback, 'start_background'", 'DEAI_FEEDBACK_URL')
LAUNCH_RE = re.compile(r'serve_main\b|(?:Popen|subprocess\.(?:run|call|check_\w+))\([^)]*serve\.py')


def python_tests():
    out = []
    for d in (HERE, os.path.join(ROOT, 'bin'), os.path.join(ROOT, 'app')):
        if os.path.isdir(d):
            out += [os.path.join(d, n) for n in sorted(os.listdir(d)) if n.startswith('test_') and n.endswith('.py')]
    return out


def unguarded(paths):
    bad = []
    for p in paths:
        if os.path.abspath(p) == os.path.abspath(__file__):
            continue
        with open(p, encoding='utf-8') as f:
            src = f.read()
        if LAUNCH_RE.search(src) and not any(m in src for m in MARKERS):
            bad.append(os.path.relpath(p, ROOT))
    return bad


class TestsNeverReachRealCollector(unittest.TestCase):
    """Приймач відгуків постачається в `app/feedback.json`: юніт, що запускає сервер (`serve_main`, `serve.py` у підпроцесі), без вимкнення
    відгуку запустив би `feedback.start_background()` проти справжнього приймача."""

    def test_every_server_launching_test_switches_feedback_off(self):
        self.assertEqual(unguarded(python_tests()), [])

    def test_the_scan_sees_the_known_launchers(self):
        """Охоронець, що нічого не сканує, не падає: відомі файли мають бути в полі зору."""
        names = set()
        for p in python_tests():
            with open(p, encoding='utf-8') as f:
                if LAUNCH_RE.search(f.read()):
                    names.add(os.path.basename(p))
        self.assertLessEqual({'test_static_publish_explicit.py', 'test_liga_migrate.py'}, names)

    def test_the_scan_flags_a_file_without_the_marker(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'test_x.py')
            with open(p, 'w') as f:
                f.write('serve.serve_main(0)\n')
            self.assertEqual(unguarded([p]), [os.path.relpath(p, ROOT)])
            with open(p, 'w') as f:
                f.write("serve.serve_main(0)  # mock.patch.object(serve.feedback, 'start_background')\n")
            self.assertEqual(unguarded([p]), [])


if __name__ == '__main__':
    unittest.main()
