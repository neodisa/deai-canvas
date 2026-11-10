"""Паритет 4d-4c: вихідні рішення 0.22 дорівнюють знімку 0.21, крім переліку `EXPECT_DIFF` (кожен елемент — свідома відмінність спеки)."""
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import make_before_4d4c as mk  # noqa: E402
import spaces_guard  # noqa: E402

FIX = os.path.join(_HERE, 'fixtures', 'outbound', 'before-4d4c.json')
_REAL = None
ABSENT = object()  # листка в «після» нема (ключ зник зі словника)


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


#: `шлях (стенд.розділ[.тіло]) → {листок: очікуване значення «після»}`. Лише ці піддерева можуть відрізнятись; решта — рівна знімку.
EXPECT_DIFF = {
    # шар вимкнено й незафіксований простір — автопуш закрито (Поправка 2, свідома відмінність 5)
    'layer_off.autocommit': {'pushed': False},
    'liga.autocommit_unfixed': {'pushed': False},
    'liga_unmigrated.autocommit_unfixed': {'pushed': False},
    'plain.autocommit_unfixed': {'pushed': False},
    'plain_git.autocommit_unfixed': {'pushed': False},
    'layer_off.autocommit_unfixed': {'pushed': False},
    # немігрована ЛІГА: записів нема → закрито
    'liga_unmigrated.autocommit': {'pushed': False},
    'liga_unmigrated.registry': {'called': False, 'result': False},
    # ціль `gitlab` зникає, а `vcs`-ціль втрачає `ssh_key`: `_vcs_ssh` віддає ключ лише за `vcs_outbound` (T3, Поправка 2)
    'liga_unmigrated.targets': {'gitlab': None, 'vcs.ssh_key': ABSENT},
    'layer_off.targets': {'gitlab': None, 'vcs.ssh_key': ABSENT},
    # `comment_channel` — лише з постачальника ролі `comments` (Поправка 10): у цих стендах його нема
    'liga_unmigrated.comment_channel': {'comment_channel': None},
    'layer_off.comment_channel': {'comment_channel': None},
    # Поправка 10 (T3): звичайний простір із ввімкненим модулем коментарів тепер отримує `comment_channel` — знімок 0.21 такого стенду
    # не має (`plain` без модуля коментарів), тож рядка в EXPECT_DIFF нема; факт закріплений прямо: `tests/test_outbound.py`
    # `test_a_plain_space_with_a_comments_module_gets_a_channel`.
    # task-new
    'plain.task_new.jira': {'status': 200, 'code': None, 'space': 'plain', 'created': True},        # було 409 no-integrations-space
    'plain_git.task_new.jira': {'status': 200, 'code': None, 'space': 'plain', 'created': True},
    'plain.task_new.gitlab': {'status': 400, 'code': 'gitlab-needs-vcs-scheme'},                    # було 409 (Поправка 8, R-B)
    'plain_git.task_new.gitlab': {'status': 400, 'code': 'gitlab-needs-vcs-scheme'},
    'liga.task_new.from': {'status': 200, 'code': None, 'space': 'legacy', 'created': True},        # було 400 from-needs-plain-space
    'liga_unmigrated.task_new.from': {'status': 200, 'code': None, 'space': 'legacy', 'created': True},
    'liga_unmigrated.task_new.gitlab': {'status': 400, 'code': 'gitlab-needs-vcs-scheme', 'created': False},
    'layer_off.task_new.from': {'status': 200, 'code': None, 'created': True},
    'layer_off.task_new.gitlab': {'status': 400, 'code': 'gitlab-needs-vcs-scheme', 'created': False},
}


def _get(d, path):
    for k in path.split('.'):
        if not isinstance(d, dict) or k not in d:
            return ABSENT
        d = d[k]
    return d


def _leaves(prefix, node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            _leaves(prefix + (k,), v, out)
    else:
        out['.'.join(prefix)] = node


class ParityAfter4d4c(unittest.TestCase):
    def test_after_equals_before_except_the_listed(self):
        with open(FIX, encoding='utf-8') as f:
            before = json.load(f)
        with tempfile.TemporaryDirectory(prefix='after-4d4c-') as tmp:
            after = mk.collect(tmp)
        b, a = {}, {}
        _leaves((), {k: v for k, v in before.items() if not k.startswith('_')}, b)
        _leaves((), after, a)
        allowed = tuple(p + '.' for p in EXPECT_DIFF)
        changed = sorted(k for k in set(b) | set(a) if b.get(k, '<нема>') != a.get(k, '<нема>'))
        stray = [k for k in changed if not any((k + '.').startswith(p) for p in allowed)]
        self.assertEqual(stray, [], 'вимірювана відмінність поза EXPECT_DIFF — ЗУПИНИТИСЬ і доповісти, перелік мовчки не розширювати')
        for path, want in EXPECT_DIFF.items():
            for leaf, val in want.items():
                self.assertEqual(_get(after, path + '.' + leaf), val, '%s.%s' % (path, leaf))
