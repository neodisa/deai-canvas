"""`serve.claude_view` — статус Клода на канвасі, що НЕ бреше (замовлення 02.09.2026).

Несуча вимога власника: «щоб він не обрехав, коли цього не відбувається». Прапорець
`working: true/false` бреше саме тоді, коли зняття не відбулось (Клод упав, сесію
закрили). Тому статус тримається на серцебитті, що СПЛИВАЄ: «працює» — лише поки
останній удар свіжий. Охоронець — удар перестав приходити, і статус згас САМ.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import serve  # noqa: E402

T0 = 1_000_000.0


def rec(status='in_progress', task='demo', at=T0, **kw):
    return {'task': task, 'phase': 'design', 'status': status, 'note': '', 'session': 's', 'at': at, **kw}


class ClaudeView(unittest.TestCase):
    def test_fresh_beat_is_working(self):
        v = serve.claude_view({'s': rec()}, T0 + 20, 'demo')
        self.assertEqual((v['state'], v['age_s']), ('working', 20))

    def test_working_expires_by_itself_when_beats_stop(self):
        """Головний охоронець: Клод упав посеред роботи — ніхто не зняв прапорець."""
        ttl = serve.CLAUDE_TTL['in_progress']
        self.assertEqual(serve.claude_view({'s': rec()}, T0 + ttl - 1, 'demo')['state'], 'working')
        self.assertIsNone(serve.claude_view({'s': rec()}, T0 + ttl + 1, 'demo')['state'])

    def test_waiting_lives_longer_but_also_expires(self):
        ttl = serve.CLAUDE_TTL['waiting']
        self.assertGreater(ttl, serve.CLAUDE_TTL['in_progress'])
        self.assertEqual(serve.claude_view({'s': rec('waiting')}, T0 + ttl - 1, 'demo')['state'], 'waiting')
        self.assertIsNone(serve.claude_view({'s': rec('waiting')}, T0 + ttl + 1, 'demo')['state'])

    def test_other_task_is_not_shown(self):
        self.assertIsNone(serve.claude_view({'s': rec(task='інша')}, T0 + 1, 'demo')['state'])

    def test_freshest_session_of_this_task_wins(self):
        recs = {'a': rec('waiting', at=T0), 'b': rec('in_progress', at=T0 + 30)}
        self.assertEqual(serve.claude_view(recs, T0 + 31, 'demo')['state'], 'working')

    def test_blocked_and_done_are_named(self):
        self.assertEqual(serve.claude_view({'s': rec('blocked')}, T0 + 1, 'demo')['state'], 'blocked')
        self.assertEqual(serve.claude_view({'s': rec('done')}, T0 + 1, 'demo')['state'], 'done')

    def test_beat_by_jira_key_is_shown(self):
        """Знахідка 12.10.2026: мод шле ключ задачі `jira ?? id`, модель за інструкцією
        скіла — тікет Jira, а сервер звіряв лише з id. У 23 з 32 задач (jira ≠ id)
        статус не світився НІКОЛИ — «хибне нічого»."""
        v = serve.claude_view({'s': rec(task='LIGA-1')}, T0 + 1, 'demo', aliases=('LIGA-1',))
        self.assertEqual(v['state'], 'working')

    def test_foreign_jira_key_is_not_shown(self):
        v = serve.claude_view({'s': rec(task='LIGA-2')}, T0 + 1, 'demo', aliases=('LIGA-1',))
        self.assertIsNone(v['state'])

    def test_empty_alias_matches_nothing(self):
        """Задача без Jira: порожній псевдонім не сміє збігтися з ударом без ключа."""
        v = serve.claude_view({'s': rec(task='')}, T0 + 1, 'demo', aliases=(None, ''))
        self.assertIsNone(v['state'])

    def test_non_string_alias_is_ignored(self):
        """Ревʼю 12.10.2026: `jira` у tasks.json правлять руками; список у ньому валив
        `GET /api/claude-status` (TypeError: unhashable), а опит б'є кожні 5 с."""
        v = serve.claude_view({'s': rec()}, T0 + 1, 'demo', aliases=(['LIGA-1'], 7))
        self.assertEqual(v['state'], 'working')


if __name__ == '__main__':
    unittest.main()
