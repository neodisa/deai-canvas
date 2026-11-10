"""Форма знімка вихідних рішень 0.21.0 (етап 4d-4c, Task 1): сам знімок — еталон, цей тест лише стереже його форму й машинонезалежність."""
import getpass
import json
import os
import re
import unittest

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'outbound', 'before-4d4c.json')
STANDS = ('liga', 'liga_unmigrated', 'plain', 'plain_git', 'layer_off')
SECTIONS = ('autocommit', 'autocommit_unfixed', 'registry', 'targets', 'comment_channel', 'task_new')
BODIES = ('jira', 'plain', 'gitlab', 'from')


class Before4d4cShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def test_meta_and_stands(self):
        self.assertEqual(self.snap['_meta']['code'], '0.21.0')
        self.assertEqual(sorted(k for k in self.snap if not k.startswith('_')), sorted(STANDS))

    def test_every_stand_has_every_section(self):
        for st in STANDS:
            self.assertEqual(sorted(self.snap[st]), sorted(SECTIONS), st)
            self.assertEqual(sorted(self.snap[st]['task_new']), sorted(BODIES), st)

    def test_values_that_0_21_decided_by_the_flag(self):
        s = self.snap
        self.assertIs(s['layer_off']['autocommit']['pushed'], True)          # шар вимкнено: «інтеграції ввімкнено»
        self.assertIs(s['liga']['autocommit_unfixed']['pushed'], True)       # простір не зафіксовано: так само
        self.assertIs(s['plain']['autocommit']['pushed'], False)
        self.assertEqual(s['plain']['task_new']['jira']['code'], 'no-integrations-space')
        self.assertEqual(s['liga']['task_new']['from']['code'], 'from-needs-plain-space')

    def test_machine_independent(self):
        with open(FIX, encoding='utf-8') as f:
            raw = f.read()
        for bad in (os.path.expanduser('~'), os.path.realpath(__import__('tempfile').gettempdir())):
            self.assertNotIn(bad, raw)
        u = getpass.getuser()
        if len(u) >= 4:       # коротке імʼя збігалося б із випадковими підрядками; шукаємо лише ціле слово
            self.assertIsNone(re.search(r'(?<![A-Za-z0-9_.-])' + re.escape(u) + r'(?![A-Za-z0-9_.-])', raw))
