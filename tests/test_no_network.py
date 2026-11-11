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


if __name__ == '__main__':
    unittest.main()
