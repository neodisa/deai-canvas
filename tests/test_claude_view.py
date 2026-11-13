"""`serve.claude_view` — статус Клода на канвасі, що НЕ бреше (замовлення 02.09.2026).

Несуча вимога власника: «щоб він не обрехав, коли цього не відбувається». Прапорець
`working: true/false` бреше саме тоді, коли зняття не відбулось (Клод упав, сесію
закрили). Тому статус тримається на серцебитті, що СПЛИВАЄ: «працює» — лише поки
останній удар свіжий. Охоронець — удар перестав приходити, і статус згас САМ.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from unittest import mock

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


class ClaudeViewsAll(unittest.TestCase):
    """`claude_views` — статуси ВСІХ задач для вкладок (0.25.0): той самий TTL і та сама мапа станів, що в `claude_view`."""

    def test_freshest_beat_per_task_key(self):
        beats = {
            's1': {'task': 'A', 'status': 'in_progress', 'at': 100},
            's2': {'task': 'A', 'status': 'waiting', 'at': 105},
            's3': {'task': 'LIGA-9', 'status': 'in_progress', 'at': 104},
        }
        out = serve.claude_views(beats, 106)
        self.assertEqual(set(out), {'A', 'LIGA-9'})
        self.assertEqual(out['A']['state'], serve.claude_view(beats, 106, 'A')['state'])
        self.assertEqual(out['A']['state'], 'waiting')
        self.assertEqual(out['A']['age_s'], 1)

    def test_expired_beats_are_absent(self):
        beats = {'s1': {'task': 'A', 'status': 'in_progress', 'at': 0}}
        now = serve.CLAUDE_TTL['in_progress'] + 1
        self.assertEqual(serve.claude_views(beats, now), {})

    def test_garbage_task_keys_are_skipped(self):
        beats = {'s1': {'task': ['x'], 'status': 'in_progress', 'at': 1},
                 's2': {'task': '', 'status': 'in_progress', 'at': 1}}
        self.assertEqual(serve.claude_views(beats, 1), {})

    def test_only_state_and_age_leave_the_server(self):
        beats = {'s1': {'task': 'A', 'status': 'in_progress', 'at': 1, 'note': 'секрет', 'phase': 'x'}}
        self.assertEqual(set(serve.claude_views(beats, 1)['A']), {'state', 'age_s'})


class ClaudeStatusesRoute(unittest.TestCase):
    """`GET /api/claude-statuses` — машинний маршрут: працює без задачі й просторів."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-cst-')
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        env = {'HOME': os.path.join(cls.tmp, 'home'), 'DEAI_HOME': os.path.join(cls.tmp, 'deai'),
               'DC_TASKS_FILE': os.path.join(cls.tmp, 'tasks.json'), 'DC_NO_OVERVIEW': '1',
               'DEAI_NO_UPDATE_CHECK': '1'}
        os.makedirs(env['HOME'])
        p = mock.patch.dict(os.environ, env)
        p.start()
        cls.addClassCleanup(p.stop)
        cls.httpd = serve.make_server(0)
        cls.base = 'http://127.0.0.1:%d' % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.httpd.shutdown)

    def get(self):
        with urllib.request.urlopen(self.base + '/api/claude-statuses') as r:
            return r.status, json.loads(r.read().decode())

    def test_is_machine_route(self):
        self.assertIn('/api/claude-statuses', serve.Handler._MACHINE_ROUTES)

    def test_empty_without_beats(self):
        with mock.patch.dict(serve.CLAUDE_BEATS, {}, clear=True):
            self.assertEqual(self.get(), (200, {'tasks': {}}))

    def test_returns_fresh_beats(self):
        import time
        beats = {'s1': {'task': 'A', 'status': 'in_progress', 'at': time.time(), 'note': 'секрет'}}
        with mock.patch.dict(serve.CLAUDE_BEATS, beats, clear=True):
            st, body = self.get()
        self.assertEqual(st, 200)
        self.assertEqual(set(body['tasks']), {'A'})
        self.assertEqual(set(body['tasks']['A']), {'state', 'age_s'})
        self.assertEqual(body['tasks']['A']['state'], 'working')


if __name__ == '__main__':
    unittest.main()
