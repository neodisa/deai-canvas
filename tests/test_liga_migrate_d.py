"""Міграція ЛІГИ, четвертий крок — напрямки остаточно явні (етап 4d-4a, 0.20.0).

Тут: знімок поведінки 0.19.0 (`Before4d4aShape`, Task 1); крок `liga-4d4a` — розрахунок, запис, відкат LIFO на чотири кроки, старт
і CLI (Task 2–3); паритет після міграції (`AfterMigrationParity4d4a`, Task 7). Спека
`docs/superpowers/specs/2026-11-07-liga-tracks-final-design.md`.
"""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4a.json')

for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import spaces_guard  # noqa: E402
from make_before_4d4a import POSTS, STANDS, UNKNOWN_ONLY_IN_NOTES, VALUES  # noqa: E402  (сценарії — ті самі, що в генераторі)
from test_liga_migrate import _WriteStand  # noqa: E402  (стенд запису 4d-3a: тимчасові HOME/DEAI_HOME, CLI, пошук секретів)

_REAL = None


def setUpModule():
    """⛔ Справжній реєстр `~/.deai` стереже `spaces_guard`."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


SECTIONS_LIGA = ['api', 'ds', 'labels', 'registry', 'repos', 'roots', 'roots_cli', 'task_new', 'view']
SECTIONS_PLAIN = ['api', 'ds', 'labels', 'repos', 'roots', 'task_new', 'view']


class Before4d4aShape(unittest.TestCase):
    """Знімок 0.19.0 на місці й має ключі, типи та кількості сценаріїв, на які спираються тести паритету."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_and_meta(self):
        self.assertEqual(sorted(self.snap), ['meta', 'non_loopback_attempts', 'stands'])
        self.assertEqual(sorted(self.snap['stands']), sorted(STANDS))
        self.assertEqual(self.snap['meta'], {'version': '0.19.0', 'source_commit': '80dc34a',
                                             'generator': 'tests/make_before_4d4a.py', 'volatile_stripped': []})
        self.assertEqual(self.snap['non_loopback_attempts'], 0)

    def test_machine_independent(self):
        """⛔ Ні справжніх шляхів, ні імені користувача, ні тимчасових тек, ні штампів часу: лише `~/…`/`<tmp>`."""
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/' + 'Users/', '/home/', '/var/' + 'folders', '/' + 'private/', '/tmp/', 'before-4d4a-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))

    def test_sections_and_scenarios_are_exact(self):
        want_values = sorted(repr(v) for v in VALUES)
        for name, st in self.snap['stands'].items():
            self.assertEqual(sorted(st), SECTIONS_PLAIN if name == 'plain' else SECTIONS_LIGA, name)
            self.assertEqual(sorted(st['task_new']), sorted(k for k, _ in POSTS), name)
            self.assertEqual(sorted(st['roots']), sorted(want_values + (["'app'", "'web'"] if name == 'plain' else [])), name)
            tasks = ['a-%d' % i for i in range(1, 9)] + (['a-9'] if name == 'notes' else [])
            tasks = [t for t in tasks if not (name != 'notes' and t in UNKNOWN_ONLY_IN_NOTES)]
            self.assertEqual(sorted(st['labels']), tasks, name)

    def test_the_stands_witness_the_adapter(self):
        """Знімок ловить саме те, що зникне: адаптерні мітки старого запису, `profile` у відповіді API, корені адаптера."""
        s = self.snap['stands']
        self.assertEqual(s['parity']['labels']['a-2'], ['United'], 'запис лише з `profile` дає мітку адаптера')
        self.assertEqual(s['parity']['roots']["'united'"], '~/work/shared')
        for name in ('parity', 'notes', 'explicit'):
            for tid, row in s[name]['api']['task'].items():
                self.assertIn('profile', row['keys'], (name, tid))
        self.assertEqual(s['notes']['roots']["'seo'"], '~/.hidden/seo')
        self.assertEqual(s['notes']['roots']["'liga360'"], 'rel/l360')
        self.assertEqual(s['notes']['roots']["'united'"], '~/work/united', 'власний корінь united ≠ спільного')
        self.assertEqual(s['plain']['labels']['a-2'], ['united'])
        self.assertEqual(s['parity']['task_new']['track_upper']['status'], 200, 'ЛІГА 0.19 приймає будь-який рядок напрямку')
        self.assertEqual(s['plain']['task_new']['track_zzz']['code'], 'unknown-track')
