"""Коментарі простору ЛІГА через модуль `supabase-comments` (етап 4b-2). Тут — тести ядра.

Task 3: адреса й ключ Supabase більше не зашиті в `serve.py`: `serve.supabase_config()` бере їх з конфігу УСТАНОВКИ
(корінь старого `tasks.json`, далі оточення). Усі споживачі (`_team_fetch`, `teams_rpc`, …) ходять лише через неї.

⛔ Ізоляція: `DC_TASKS_FILE`/`DC_NO_OVERVIEW` прибираються лише там, де це ПОТРІБНО для перевірки (вони самі глушать
мережу `_team_fetch`/`teams_rpc`); справжній `tasks.json` недосяжний — старий файл підставлено тимчасовий через
`spaces.legacy_tasks_file`, а `urlopen` підмінено: або записувачем, або тим, що падає. Адреси й ключі — вигадані.
"""
import contextlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)
import deai_modules  # noqa: E402
import inbox  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402

_REAL = None
BEFORE = os.path.join(_HERE, 'fixtures', 'legacy-comments', 'before-4b2.json')

URL = 'https://demo.supabase.co'
KEY = 'sb_publishable_test'
ENV_URL = 'https://abcdefghijkl.supabase.co'
ENV_KEY = 'sb_publishable_test_env'

#: Змінні, що ізолюють прогін (самі глушать мережу) і шви тестів: у перевірках «живого» шляху їх немає.
_ISOLATION = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE')


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _boom(*a, **k):
    raise AssertionError('urlopen не мав бути викликаний')


class _Resp:
    """Мінімальна відповідь `urlopen` (контекстний менеджер з `read`)."""

    def __init__(self, body=b'[]'):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class _Env(unittest.TestCase):
    """Тимчасовий старий файл задач під `spaces.legacy_tasks_file`, оточення без `SUPABASE_*` й без ізоляційних
    змінних (вони самі глушать мережу), `urlopen` — що падає, поки тест не підмінить його власним записувачем."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.legacy = os.path.join(self.tmp.name, 'tasks.json')
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.dict(os.environ, {}, clear=False))
        for name in _ISOLATION + ('SUPABASE_URL', 'SUPABASE_KEY'):
            os.environ.pop(name, None)
        stack.enter_context(mock.patch.object(spaces, 'legacy_tasks_file', return_value=self.legacy))
        # Розтяжка: жодної мережі, поки тест не підмінив її явно.
        stack.enter_context(mock.patch.object(serve.urllib.request, 'urlopen', _boom))

    def write(self, obj, raw=None):
        with open(self.legacy, 'w', encoding='utf-8') as f:
            f.write(raw if raw is not None else json.dumps(obj))


class SupabaseConfigTest(_Env):
    """`serve.supabase_config()`: конфіг УСТАНОВКИ, а не константи коду."""

    def test_reads_root_of_legacy_tasks_and_trims_slash(self):
        self.write({'supabase_url': URL + '/', 'supabase_key': KEY})
        self.assertEqual(serve.supabase_config(), (URL, KEY))

    def test_falls_back_to_environment(self):
        self.write({'tasks': {}})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(serve.supabase_config(), (ENV_URL, ENV_KEY))

    def test_file_wins_over_environment(self):
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(serve.supabase_config(), (URL, KEY))

    def test_pair_comes_whole_from_one_source(self):
        # Адреса з файла й ключ з оточення не змішуються: або ціла пара з файла, або ціла з оточення.
        self.write({'supabase_url': URL})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(serve.supabase_config(), (ENV_URL, ENV_KEY))
        # …а коли й оточення неповне — нічого.
        del os.environ['SUPABASE_URL']
        self.assertEqual(serve.supabase_config(), (None, None))
        os.environ['SUPABASE_URL'] = ENV_URL
        del os.environ['SUPABASE_KEY']
        self.assertEqual(serve.supabase_config(), (None, None))

    def test_only_https_and_non_blank_strings(self):
        for url, key in (('http://demo.supabase.co', KEY), ('', KEY), (5, KEY), (None, KEY),
                         (URL, '   '), (URL, ''), (URL, 5), (URL, None), ('demo.supabase.co', KEY)):
            with self.subTest(url=url, key=key):
                self.write({'supabase_url': url, 'supabase_key': key})
                self.assertEqual(serve.supabase_config(), (None, None))

    def test_http_in_file_does_not_fall_through_to_mixed_pair(self):
        # Негодна пара з файла відкидається ЦІЛКОМ; оточення береться теж лише цілим.
        self.write({'supabase_url': 'http://demo.supabase.co', 'supabase_key': KEY})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(serve.supabase_config(), (ENV_URL, ENV_KEY))

    def test_unreadable_file_means_environment_or_nothing(self):
        # нема файла
        self.assertEqual(serve.supabase_config(), (None, None))
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(serve.supabase_config(), (ENV_URL, ENV_KEY))
        # не JSON і не обʼєкт
        for raw in ('{oops', '[]', '"x"', '5', 'null'):
            with self.subTest(raw=raw):
                self.write(None, raw=raw)
                self.assertEqual(serve.supabase_config(), (ENV_URL, ENV_KEY))
        del os.environ['SUPABASE_KEY']
        self.write(None, raw='{oops')
        self.assertEqual(serve.supabase_config(), (None, None))

    def test_no_constants_left_in_serve(self):
        self.assertFalse(hasattr(serve, 'SUPABASE_URL'))
        self.assertFalse(hasattr(serve, 'SUPABASE_KEY'))

    def test_status_code_comments_unconfigured(self):
        self.assertEqual(deai_modules.STATUS['comments-unconfigured'], 409)


class TeamFetchTest(_Env):
    """`_team_fetch()`: без конфігу — чесне «не налаштовано» і жодної мережі; з конфігом — запит на адресу конфігу."""

    def test_without_config_no_network(self):
        self.write({'tasks': {}})
        self.assertEqual(serve._team_fetch(), ([], 'Supabase не налаштовано'))

    def test_with_config_requests_config_url(self):
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        seen = []

        def fake(req, timeout=None, context=None):
            seen.append(req)
            return _Resp(b'[{"project_id": "p1"}]')
        with mock.patch.object(serve.urllib.request, 'urlopen', fake):
            rows, err = serve._team_fetch()
        self.assertIsNone(err)
        self.assertEqual(rows, [{'project_id': 'p1'}])
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].full_url.startswith(URL + '/rest/v1/overview_projects?'))
        self.assertEqual(seen[0].get_header('Apikey'), KEY)
        self.assertEqual(seen[0].get_header('Authorization'), 'Bearer ' + KEY)

    def test_isolation_still_wins_over_config(self):
        # ⛔ Закон ізоляції не змінився: `DC_TASKS_FILE` глушить мережу, навіть коли конфіг є.
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        os.environ['DC_TASKS_FILE'] = self.legacy
        rows, err = serve._team_fetch()
        self.assertEqual(rows, [])
        self.assertIn('ізольованому', err)


class TeamsRpcTest(_Env):
    """`teams_rpc`: без конфігу — `OSError` без мережі; з конфігом — той самий запит, що знято до зміни (0.9.0)."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(spaces, 'require_integrations', lambda *a, **k: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_without_config_raises_without_network(self):
        self.write({'tasks': {}})
        with self.assertRaises(OSError):
            serve.teams_rpc('teams_mute_state', {})

    def test_with_config_matches_baseline(self):
        with open(BEFORE, encoding='utf-8') as f:
            base = json.load(f)['teams_rpc']
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        seen = []

        def fake(req, timeout=None, context=None):
            seen.append(req)
            return _Resp(b'[]')
        with mock.patch.object(serve.urllib.request, 'urlopen', fake):
            serve.teams_rpc('teams_mute_state', {})
        self.assertEqual(len(seen), 1)
        req = seen[0]
        self.assertEqual(req.full_url, URL + base['path'])
        self.assertEqual(req.get_method(), base['method'])
        self.assertEqual(json.loads(req.data.decode('utf-8')), base['body'])
        apikey_is_config = req.get_header('Apikey') == KEY
        bearer_is_config = req.get_header('Authorization') == 'Bearer ' + KEY
        self.assertEqual((apikey_is_config, bearer_is_config),
                         (base['apikey_is_config'], base['bearer_is_config']))
        self.assertTrue(apikey_is_config and bearer_is_config)

    def test_isolation_still_blocks_with_config(self):
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        os.environ['DC_NO_OVERVIEW'] = '1'
        with self.assertRaises(OSError):
            serve.teams_rpc('teams_mute_state', {})


class OverviewSyncTest(_Env):
    """`Handler._overview_sync`: без конфігу установки фонового пуша нема (ні лога, ні `Popen`); з конфігом — дитина
    отримує пару в оточенні."""

    def setUp(self):
        super().setUp()
        home = os.path.join(self.tmp.name, 'home')
        os.makedirs(os.path.join(home, '.claude', 'pipeline-feedback'))
        env = mock.patch.dict(os.environ, {'HOME': home})
        env.start()
        self.addCleanup(env.stop)
        out = mock.patch.object(serve, '_outbound_ok', return_value=True)
        out.start()
        self.addCleanup(out.stop)

    def test_without_config_no_popen_and_no_log(self):
        self.write({'tasks': {}})
        with mock.patch.object(serve.subprocess, 'Popen') as popen:
            serve.Handler._overview_sync(None)
        popen.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(
            self.tmp.name, 'home', '.claude', 'pipeline-feedback', 'overview-sync.log')))

    def test_with_config_child_gets_the_pair(self):
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        with mock.patch.object(serve.subprocess, 'Popen') as popen:
            serve.Handler._overview_sync(None)
        popen.assert_called_once()
        env = popen.call_args.kwargs['env']
        self.assertEqual((env['SUPABASE_URL'], env['SUPABASE_KEY']), (URL, KEY))


class InboxWithoutConfigTest(_Env):
    """`bin/inbox.py`: закриття піна старим шляхом і його dry-run без конфігу установки — чесно, без мережі й без значень."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(spaces, 'require_integrations', lambda *a, **k: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_patch_project_pin_without_config_raises_without_network(self):
        self.write({'tasks': {}})
        with self.assertRaises(OSError) as ctx:
            inbox.patch_project_pin('c0ffee01-aaaa', 2, 'причина')
        self.assertIn('не налаштовано', str(ctx.exception))

    def test_patch_project_pin_with_config_patches_config_url(self):
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        seen = []

        def fake(req, timeout=None, context=None):
            seen.append(req)
            return _Resp(b'')
        _Resp.status = 204
        with mock.patch.object(inbox.urllib.request, 'urlopen', fake):
            inbox.patch_project_pin('c0ffee01-aaaa', 2, 'причина')
        self.assertEqual(seen[0].full_url, f'{URL}/rest/v1/comments?id=eq.c0ffee01-aaaa')
        self.assertEqual(seen[0].get_method(), 'PATCH')
        self.assertEqual(seen[0].get_header('Apikey'), KEY)


if __name__ == '__main__':
    unittest.main()
