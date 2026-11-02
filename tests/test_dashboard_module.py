"""`app/modules/supabase-dashboard`: власний проєкт Supabase як сховище карток команди (роль `dashboard`, 4c-1, Task 4).

Модуль вантажиться через справжній `deai_modules.catalog()`: так тест бачить саме те, що виконає сервер (зокрема
`ctx['ModuleError']` ядра). ⛔ Жодного реального запиту: шов мережі — імʼя `_open` у глобалах модуля (ЄДИНЕ місце, де запит
іде в мережу); тест підміняє його записувачем, що віддає сценарні відповіді. Побудова запиту, заголовки й розбір відповідей — справжні.

Що доводиться:
  * маніфест (`roles`, налаштування, ключ БЕЗ `public`), `schema.sql` (RLS, жодної політики й жодного права для `anon`);
  * `check`: адреса/таблиця/ключ, відмова публічному ключу (але НЕ в ЛІГИ: `ctx['legacy']`), «нема таблиці → schema.sql»;
  * `rows`, `push` (пакети по 50, збій пакета, `None` не шлеться, різні набори ключів — різні запити), `open_comments`;
  * ⛔ жоден текст помилки не містить ключа, тіла запиту чи відповіді й не довший за 200 знаків;
  * форма запитів збігається з ЗАПИСАНОЮ в знімку 0.11.0 (`tests/fixtures/dashboard/before-4c1.json`: `team_read` і `upsert_http`),
    крім двох свідомих відмінностей — пакети по 50 замість одного рядка та тайм-аут читання 4 с замість 3 (запис — 15 с).
"""
import base64
import io
import json
import os
import re
import sys
import unittest
import urllib.error
import urllib.request
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402

MODULE_DIR = os.path.join(ROOT, 'app', 'modules', 'supabase-dashboard')
BEFORE = os.path.join(_HERE, 'fixtures', 'dashboard', 'before-4c1.json')
URL = 'https://demo.supabase.example'
KEY = 'sk-test-dashboard-0123456789'
TEAM_KEYS = ('id', 'name', 'jira', 'jira_status', 'jira_status_cat', 'open_comments', 'thumb_url', 'code_url',
             'updated_at', 'designer', 'iterations', 'pages')


def _jwt(role):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')
    return '.'.join([b64({'alg': 'HS256'}), b64({'role': role, 'iss': 'supabase-demo'}), 'c2ln'])


class Resp:
    """Відповідь, що вміє `with`, `.status` і `.read(n)`."""

    def __init__(self, status, body):
        self.status = status
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]


def http_error(status, body=b''):
    body = body if isinstance(body, bytes) else json.dumps(body).encode()
    return urllib.error.HTTPError(URL, status, 'err', {}, io.BytesIO(body))


class ModuleCase(unittest.TestCase):
    def setUp(self):
        os.environ.pop('DEAI_EXTRA_MODULES', None)
        dm.reset_caches()
        self.mod = dm.catalog()['supabase-dashboard']
        self.g = self.mod.fn('check').__globals__
        self.calls = []

    def ctx(self, **over):
        base = {'space': {'id': 'alpha', 'path': ''}, 'settings': {'url': URL, 'table': 'deai_dashboard'},
                'secrets': {'key': KEY}, 'ModuleError': dm.ModuleError}
        for k, v in over.items():
            if k == 'settings':
                base['settings'] = {**base['settings'], **v}
            elif k == 'secrets':
                base['secrets'] = v
            else:
                base[k] = v
        return base

    def net(self, script):
        """Підміна шва `_open`: `script(call_index, call) -> Resp | виняток`; кожен запит — у `self.calls`."""
        def fake(req, timeout):
            body = json.loads(req.data.decode('utf-8')) if req.data else None
            call = {'method': req.get_method(), 'url': req.full_url, 'timeout': timeout, 'body': body,
                    'headers': {k.lower(): v for k, v in req.header_items()}}
            self.calls.append(call)
            r = script(len(self.calls) - 1, call) if callable(script) else script
            if isinstance(r, BaseException):
                raise r
            return r
        p = mock.patch.dict(self.g, {'_open': fake})
        p.start()
        self.addCleanup(p.stop)

    def run_fn(self, name, ctx, *args):
        """Виклик, як його робить ядро: через `deai_modules.call` (виняток ядра, сліпа смуга секретів)."""
        return dm.call(self.mod, name, ctx, *args)

    def raises(self, name, ctx, *args):
        with self.assertRaises(dm.ModuleError) as cm:
            self.run_fn(name, ctx, *args)
        return cm.exception


class ManifestTest(ModuleCase):
    def test_manifest(self):
        m = self.mod
        self.assertEqual((m.id, m.status, m.version), ('supabase-dashboard', 'ok', '1.0.0'))
        self.assertEqual(m.roles, ['dashboard'])
        st = {s['key']: s for s in m.settings}
        self.assertEqual(set(st), {'url', 'key', 'table'})
        self.assertEqual((st['url']['type'], st['url']['required']), ('text', True))
        self.assertEqual((st['key']['type'], st['key']['required']), ('secret', True))
        self.assertFalse(st['key'].get('public'), 'ключ дашборда непублічний: у сторінки він не потрапляє')
        self.assertEqual(st['table']['type'], 'text')
        self.assertFalse(st['table'].get('required'))
        self.assertEqual(m.client, ())

    def test_functions_of_the_role(self):
        for fn in ('check', 'rows', 'push', 'open_comments'):
            self.assertIsNotNone(self.mod.fn(fn), fn)

    def test_schema_gives_the_public_role_nothing(self):
        with open(os.path.join(MODULE_DIR, 'schema.sql'), encoding='utf-8') as f:
            sql = f.read()
        body = '\n'.join(ln for ln in sql.splitlines() if not ln.lstrip().startswith('--'))
        self.assertIn('create table if not exists public.deai_dashboard', body)
        self.assertRegex(body, r'id\s+text primary key')
        self.assertIn('enable row level security', body)
        self.assertNotRegex(body.lower(), r'create\s+policy', 'жодної політики: ні для anon, ні для кого')
        self.assertNotRegex(body.lower(), r'grant\s+[^;]*\bto\b[^;]*\banon\b', 'жодного права для anon')
        self.assertRegex(body.lower(), r'revoke\s+all\s+on\s+public\.deai_dashboard\s+from\s+anon')
        for col in TEAM_KEYS + ('status', 'figma_url', 'synced_at', 'designer_key'):
            self.assertRegex(body, rf'\b{col}\b', col)
        self.assertIn('NON-PUBLIC', sql)
        self.assertIn('DEDICATED', sql)

    def test_readme_exists_and_warns(self):
        with open(os.path.join(MODULE_DIR, 'README.md'), encoding='utf-8') as f:
            text = f.read()
        self.assertIn('non-public', text.lower())
        self.assertIn('schema.sql', text)


class TlsTest(ModuleCase):
    """Перевірений TLS: сховище certifi, коли є, інакше типовий контекст (як у `supabase-comments`)."""

    def test_the_opener_verifies_tls(self):
        import ssl
        handlers = [h for h in self.g['_opener'].handlers if isinstance(h, urllib.request.HTTPSHandler)]
        self.assertEqual(len(handlers), 1)
        ctx = handlers[0]._context
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_without_certifi_the_default_context_is_used(self):
        import ssl
        with mock.patch.dict(sys.modules, {'certifi': None}):
            ctx = self.g['_tls']()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)


class CheckTest(ModuleCase):
    def test_ok(self):
        self.net(Resp(200, []))
        res = self.run_fn('check', self.ctx())
        self.assertEqual(res['ok'], True)
        self.assertEqual(len(self.calls), 1)
        c = self.calls[0]
        self.assertEqual((c['method'], c['url']), ('GET', URL + '/rest/v1/deai_dashboard?select=id&limit=1'))
        self.assertLessEqual(c['timeout'], 4)

    def test_default_table(self):
        self.net(Resp(200, []))
        ctx = self.ctx()
        ctx['settings'].pop('table')
        self.assertTrue(self.run_fn('check', ctx)['ok'])
        self.assertIn('/rest/v1/deai_dashboard?', self.calls[0]['url'])

    def test_bad_address_is_refused_before_any_request(self):
        self.net(Resp(200, []))
        for bad in ('http://demo.supabase.example', 'https://localhost', 'https://127.0.0.1', 'https://u:p@demo.supabase.example',
                    'https://demo.supabase.example/path', 'not a url', 'https://demo.supabase.example?x=1'):
            res = self.run_fn('check', self.ctx(settings={'url': bad}))
            self.assertFalse(res['ok'], bad)
            self.assertEqual(res['error'], 'module-error', bad)
            self.assertIn('https://<ref>.supabase.co', res['detail'])
        self.assertEqual(self.calls, [])

    def test_missing_url_or_key_is_a_verdict(self):
        self.net(Resp(200, []))
        res = self.run_fn('check', self.ctx(settings={'url': ''}))
        self.assertEqual((res['ok'], res['error']), (False, 'module-error'))
        res = self.run_fn('check', self.ctx(secrets={}))
        self.assertEqual((res['ok'], res['error']), (False, 'module-error'))
        self.assertEqual(self.calls, [])

    def test_public_keys_are_refused(self):
        self.net(Resp(200, []))
        for key in ('sb_publishable_abc123', _jwt('anon')):
            res = self.run_fn('check', self.ctx(secrets={'key': key}))
            self.assertEqual((res['ok'], res['error']), (False, 'module-error'), key[:14])
            self.assertIn('непублічний ключ', res['detail'])
            self.assertNotIn(key, json.dumps(res))
        self.assertEqual(self.calls, [], 'публічному ключу не віддаємо навіть запиту')

    def test_non_public_keys_pass(self):
        self.net(Resp(200, []))
        for key in ('sb_secret_abc123', _jwt('service_role'), KEY):
            self.assertTrue(self.run_fn('check', self.ctx(secrets={'key': key}))['ok'], key[:14])

    def test_liga_path_does_not_refuse_a_public_key(self):
        """ЛІГА: ключ той самий, що до 4c-1 (паритет); `check` у `ctx['legacy']` публічності не перевіряє."""
        self.net(Resp(200, []))
        ctx = self.ctx(secrets={'key': 'sb_publishable_abc123'}, settings={'table': 'overview_projects'}, legacy=True)
        res = self.run_fn('check', ctx)
        self.assertTrue(res['ok'], res)
        self.assertIn('/rest/v1/overview_projects?', self.calls[0]['url'])
        ctx = self.ctx(secrets={'key': _jwt('anon')}, legacy=True)
        self.assertTrue(self.run_fn('check', ctx)['ok'])

    def test_bad_table_name(self):
        self.net(Resp(200, []))
        for bad in ('Deai', '1table', 'a-b', 'a b', 'a' * 64, 'public.deai', 'x;drop'):
            res = self.run_fn('check', self.ctx(settings={'table': bad}))
            self.assertEqual((res['ok'], res['error']), (False, 'module-error'), bad)
        self.assertEqual(self.calls, [])
        for good in ('_t', 'deai_dashboard', 'a' * 63):
            self.assertTrue(self.run_fn('check', self.ctx(settings={'table': good}))['ok'], good)

    def test_missing_table_says_run_schema(self):
        for status, body in ((404, {'code': '42P01', 'message': 'x'}), (400, {'code': 'PGRST205', 'message': 'x'}), (404, b'')):
            self.calls.clear()
            self.net(http_error(status, body))
            res = self.run_fn('check', self.ctx())
            self.assertEqual((res['ok'], res['error']), (False, 'no-schema'), (status, body))
            self.assertIn('schema.sql', res['detail'])

    def test_service_failures_are_verdicts(self):
        self.net(http_error(401, {'message': 'Invalid API key ' + KEY}))
        res = self.run_fn('check', self.ctx())
        self.assertEqual((res['ok'], res['error']), (False, 'bad-key'))
        self.net(http_error(500, {'message': 'boom'}))
        self.assertEqual(self.run_fn('check', self.ctx())['error'], 'dashboard-error')
        self.net(OSError('connection refused'))
        res = self.run_fn('check', self.ctx())
        self.assertEqual((res['ok'], res['error']), (False, 'network'))
        self.net(Resp(200, {'not': 'a list'}))
        self.assertEqual(self.run_fn('check', self.ctx())['error'], 'dashboard-error')

    def test_a_redirect_is_an_error_not_a_hop(self):
        """Редирект не виконується (`_NoRedirect`): ключ лишається в нас, а відповідь 3xx — помилка."""
        h = [h for h in self.g['_opener'].handlers if isinstance(h, self.g['_NoRedirect'])]
        self.assertTrue(h)
        self.assertIsNone(h[0].redirect_request(None, None, 302, 'Found', {}, 'https://evil.example/'))
        self.net(http_error(302))
        res = self.run_fn('check', self.ctx())
        self.assertFalse(res['ok'])
        self.assertIn('переадресацією', res['detail'])


class RowsTest(ModuleCase):
    def test_request_shape(self):
        data = [{'id': 't1', 'name': 'Demo'}]
        self.net(Resp(200, data))
        self.assertEqual(self.run_fn('rows', self.ctx()), data)
        c = self.calls[0]
        self.assertEqual(c['method'], 'GET')
        self.assertEqual(c['url'], URL + '/rest/v1/deai_dashboard?select=' + ','.join(TEAM_KEYS) + '&limit=500')
        self.assertEqual(c['headers'], {'apikey': KEY, 'authorization': 'Bearer ' + KEY})
        self.assertLessEqual(c['timeout'], 4)

    def test_table_setting_is_used(self):
        self.net(Resp(200, []))
        self.run_fn('rows', self.ctx(settings={'table': 'team_cards'}))
        self.assertIn('/rest/v1/team_cards?select=', self.calls[0]['url'])

    def test_not_a_list_is_module_error(self):
        for body in ({'rows': []}, 'text', 7, None):
            self.net(Resp(200, body))
            e = self.raises('rows', self.ctx())
            self.assertEqual((e.code, e.status), ('module-error', 502), body)

    def test_service_errors_carry_the_dashboard_error_code(self):
        self.net(http_error(401, {'code': 'PGRST301', 'message': 'JWT secret ' + KEY}))
        e = self.raises('rows', self.ctx())
        self.assertEqual((e.code, e.status), ('dashboard-error', 502))
        self.assertIn('401', e.message)
        self.net(http_error(404, {'code': '42P01', 'message': 'relation does not exist'}))
        self.assertIn('schema.sql', self.raises('rows', self.ctx()).message)
        self.net(OSError('boom'))
        e = self.raises('rows', self.ctx())
        self.assertEqual(e.code, 'dashboard-error')
        self.assertIn('недоступний', e.message)

    def test_unconfigured_and_bad_settings(self):
        self.net(Resp(200, []))
        self.assertEqual(self.raises('rows', self.ctx(secrets={})).code, 'dashboard-unconfigured')
        self.assertEqual(self.raises('rows', self.ctx(settings={'url': ''})).code, 'dashboard-unconfigured')
        self.assertEqual(self.raises('rows', self.ctx(settings={'url': 'http://x.example'})).code, 'module-error')
        self.assertEqual(self.raises('rows', self.ctx(settings={'table': 'A-b'})).code, 'module-error')
        self.assertEqual(self.raises('rows', self.ctx(secrets={'key': 'a b'})).code, 'module-error')
        self.assertEqual(self.calls, [])

    def test_a_public_key_is_not_judged_by_rows(self):
        """Публічність ключа вирішує лише `check`; `rows` її не перевіряє (межу ставить RLS бази)."""
        self.net(Resp(200, []))
        self.assertEqual(self.run_fn('rows', self.ctx(secrets={'key': 'sb_publishable_abc123'})), [])


class PushTest(ModuleCase):
    @staticmethod
    def cards(n, **extra):
        return [{'id': f't{i}', 'name': f'Demo {i}', 'iterations': i, **extra} for i in range(n)]

    def test_batches_of_fifty(self):
        self.net(Resp(201, b''))
        res = self.run_fn('push', self.ctx(), self.cards(120), 'merge')
        self.assertEqual(res, {'ok': 120, 'failed': {}})
        self.assertEqual([len(c['body']) for c in self.calls], [50, 50, 20])
        self.assertEqual([c['body'][0]['id'] for c in self.calls], ['t0', 't50', 't100'])

    def test_request_shape_merge_and_insert(self):
        self.net(Resp(201, b''))
        self.run_fn('push', self.ctx(), self.cards(1), 'merge')
        self.run_fn('push', self.ctx(), self.cards(1), 'insert')
        merge, insert = self.calls
        for c in (merge, insert):
            self.assertEqual((c['method'], c['url']), ('POST', URL + '/rest/v1/deai_dashboard?on_conflict=id'))
            self.assertEqual(c['headers']['content-type'], 'application/json')
            self.assertEqual(c['headers']['apikey'], KEY)
            self.assertEqual(c['headers']['authorization'], 'Bearer ' + KEY)
            self.assertEqual(c['timeout'], 15)
        self.assertEqual(merge['headers']['prefer'], 'resolution=merge-duplicates,return=minimal')
        self.assertEqual(insert['headers']['prefer'], 'resolution=ignore-duplicates,return=minimal')

    def test_a_failed_batch_marks_only_its_ids(self):
        def script(i, call):
            return http_error(400, {'code': '22P02', 'message': 'bad ' + json.dumps(call['body'])}) if i == 1 else Resp(201, b'')
        self.net(script)
        res = self.run_fn('push', self.ctx(), self.cards(120), 'merge')
        self.assertEqual(res['ok'], 70)
        self.assertEqual(sorted(res['failed']), sorted(f't{i}' for i in range(50, 100)))
        for text in res['failed'].values():
            self.assertIn('400', text)
            self.assertIn('22P02', text)
            self.assertLessEqual(len(text), 200)
            self.assertNotIn('Demo', text, 'тіло запиту в тексті помилки недопустиме')

    def test_none_values_are_not_sent(self):
        self.net(Resp(201, b''))
        cards = [{'id': 't1', 'name': 'Demo', 'jira_status': None, 'pages': None, 'iterations': 0}]
        self.run_fn('push', self.ctx(), cards, 'merge')
        self.assertEqual(self.calls[0]['body'], [{'id': 't1', 'name': 'Demo', 'iterations': 0}])
        self.assertEqual(cards[0]['jira_status'], None, 'вхідну картку не псуємо')

    def test_cards_with_different_key_sets_go_separately(self):
        """PostgREST заповнив би відсутній ключ `null`ом, а `merge-duplicates` затер би наявне: різні набори — різні запити."""
        self.net(Resp(201, b''))
        cards = [{'id': 'a', 'name': 'A', 'jira_status': 'Done'}, {'id': 'b', 'name': 'B'},
                 {'id': 'c', 'name': 'C', 'jira_status': 'To Do'}, {'id': 'd', 'name': 'D', 'x': None}]
        res = self.run_fn('push', self.ctx(), cards, 'merge')
        self.assertEqual(res, {'ok': 4, 'failed': {}})
        sets = [{frozenset(r) for r in c['body']} for c in self.calls]
        self.assertTrue(all(len(s) == 1 for s in sets), 'у запиті один набір ключів')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([[r['id'] for r in c['body']] for c in self.calls], [['a', 'c'], ['b', 'd']])

    def test_bad_mode_and_bad_cards(self):
        self.net(Resp(201, b''))
        for mode in ('replace', '', None, 'MERGE'):
            self.assertEqual(self.raises('push', self.ctx(), self.cards(1), mode).code, 'module-error', mode)
        self.assertEqual(self.raises('push', self.ctx(), {'id': 't1'}, 'merge').code, 'module-error')
        self.assertEqual(self.calls, [])
        res = self.run_fn('push', self.ctx(), [{'name': 'no id'}, 'x', {'id': 't1'}], 'merge')
        self.assertEqual(res['ok'], 1)
        self.assertEqual(sorted(res['failed']), ['#0', '#1'])
        self.assertEqual(self.run_fn('push', self.ctx(), [], 'merge'), {'ok': 0, 'failed': {}})
        self.assertEqual(len(self.calls), 1)

    def test_service_unreachable_at_once_is_a_dashboard_error(self):
        self.net(OSError('refused'))
        e = self.raises('push', self.ctx(), self.cards(120), 'merge')
        self.assertEqual((e.code, e.status), ('dashboard-error', 502))
        self.assertEqual(len(self.calls), 1, 'решту пакетів не мучимо')

    def test_service_lost_midway_fails_the_rest(self):
        self.net(lambda i, call: Resp(201, b'') if i == 0 else OSError('reset'))
        res = self.run_fn('push', self.ctx(), self.cards(120), 'merge')
        self.assertEqual(res['ok'], 50)
        self.assertEqual(sorted(res['failed']), sorted(f't{i}' for i in range(50, 120)))
        self.assertEqual(len(self.calls), 2, 'після обриву решта пакетів не шлеться')

    def test_missing_table_and_bad_key_are_failures_of_the_cards(self):
        self.net(http_error(404, {'code': '42P01', 'message': 'x'}))
        res = self.run_fn('push', self.ctx(), self.cards(2), 'insert')
        self.assertEqual(res['ok'], 0)
        self.assertEqual(sorted(res['failed']), ['t0', 't1'])
        self.assertIn('schema.sql', res['failed']['t0'])
        self.net(http_error(401, b'{}'))
        self.assertIn('401', self.run_fn('push', self.ctx(), self.cards(1), 'merge')['failed']['t0'])


class TextSafetyTest(ModuleCase):
    """⛔ Жоден текст помилки не містить ключа, тіла запиту чи відповіді й не довший за 200 знаків."""
    BODY = 'SECRET-BODY-MARKER'

    def scenarios(self):
        echo = {'code': 'XX000', 'message': f'{self.BODY} {KEY} {"z" * 400}', 'details': self.BODY, 'hint': KEY}
        yield 'rows-401', lambda: http_error(401, echo), 'rows', ()
        yield 'rows-500', lambda: http_error(500, echo), 'rows', ()
        yield 'rows-404', lambda: http_error(404, echo), 'rows', ()
        yield 'rows-302', lambda: http_error(302, echo), 'rows', ()
        yield 'rows-net', lambda: OSError(f'{KEY} {self.BODY}'), 'rows', ()
        yield 'rows-shape', lambda: Resp(200, {'x': self.BODY + KEY}), 'rows', ()
        yield 'open-500', lambda: http_error(500, echo), 'open_comments', ()
        yield 'open-net', lambda: OSError(f'{KEY}'), 'open_comments', ()
        yield 'push-net', lambda: OSError(f'{KEY} {self.BODY}'), 'push', ([{'id': 't1', 'name': self.BODY}], 'merge')

    def test_exceptions_are_clean(self):
        for name, make, fn, args in self.scenarios():
            with self.subTest(name):
                self.calls.clear()
                self.net(make())
                e = self.raises(fn, self.ctx(), *args)
                for text in (e.message, e.full, str(e)):
                    self.assertNotIn(KEY, text)
                    self.assertNotIn(self.BODY, text)
                    self.assertLessEqual(len(e.message), 200)

    def test_verdicts_and_failed_texts_are_clean(self):
        echo = {'code': 'XX000', 'message': f'{self.BODY} {KEY}', 'details': self.BODY}
        for make in (lambda: http_error(401, echo), lambda: http_error(404, echo), lambda: http_error(500, echo),
                     lambda: OSError(f'{KEY} {self.BODY}'), lambda: Resp(200, {'x': self.BODY + KEY})):
            self.net(make())
            res = self.run_fn('check', self.ctx())
            self.assertNotIn(KEY, json.dumps(res))
            self.assertNotIn(self.BODY, json.dumps(res))
            self.assertLessEqual(len(res['detail']), 200)
        self.net(http_error(500, echo))
        res = self.run_fn('push', self.ctx(), [{'id': 't1', 'name': self.BODY}], 'merge')
        self.assertNotIn(KEY, json.dumps(res))
        self.assertNotIn(self.BODY, json.dumps(res))
        self.assertLessEqual(len(res['failed']['t1']), 200)

    def test_settings_errors_never_echo_the_key_or_the_address(self):
        self.net(Resp(200, []))
        ctx = self.ctx(settings={'url': 'https://user:hunter2@demo.supabase.example'})
        res = self.run_fn('check', ctx)
        self.assertNotIn('hunter2', json.dumps(res))
        e = self.raises('rows', ctx)
        self.assertNotIn('hunter2', e.message)
        bad_key = self.ctx(secrets={'key': KEY + ' tail'})
        e = self.raises('rows', bad_key)
        self.assertNotIn(KEY, e.message)

    def test_clean_removes_the_key_even_if_it_gets_in(self):
        clean = self.g['_clean']
        self.assertNotIn(KEY, clean(f'a {KEY} b', KEY))
        self.assertLessEqual(len(clean('x' * 1000, KEY)), 200)


class OpenCommentsTest(ModuleCase):
    def test_counts_per_channel(self):
        rows = [{'project_id': 'deai/alpha/t1'}] * 3 + [{'project_id': 'deai/alpha/t2'}, {'project_id': None}, {}, 'x']
        self.net(Resp(200, rows))
        self.assertEqual(self.run_fn('open_comments', self.ctx()), {'deai/alpha/t1': 3, 'deai/alpha/t2': 1})
        c = self.calls[0]
        self.assertEqual((c['method'], c['url']), ('GET', URL + '/rest/v1/comments?status=eq.open&select=project_id'))
        self.assertEqual(c['headers'], {'apikey': KEY, 'authorization': 'Bearer ' + KEY})

    def test_no_comments_table_gives_nothing(self):
        for status, body in ((404, {'code': '42P01'}), (400, {'code': 'PGRST205'}), (404, b'')):
            self.net(http_error(status, body))
            self.assertEqual(self.run_fn('open_comments', self.ctx()), {})

    def test_other_failures_are_dashboard_errors(self):
        self.net(http_error(500, b'{}'))
        self.assertEqual(self.raises('open_comments', self.ctx()).code, 'dashboard-error')
        self.net(Resp(200, {'a': 1}))
        self.assertEqual(self.raises('open_comments', self.ctx()).code, 'module-error')


class RecordedShapeTest(ModuleCase):
    """Форма запитів модуля = ЗАПИСАНА в знімку 0.11.0 (читання — `team_read.supabase_request`, запис — `upsert_http`)."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.rec = json.load(f)

    @staticmethod
    def with_key(headers):
        return {k.lower(): v.replace('<key>', KEY) for k, v in headers.items()}

    def test_read_matches_the_recorded_get(self):
        rec = self.rec['team_read']['supabase_request']['urlopen_calls']
        self.assertEqual(len(rec), 1)
        rec = rec[0]
        self.net(Resp(200, []))
        self.run_fn('rows', self.ctx(settings={'table': 'overview_projects'}, legacy=True))
        c = self.calls[0]
        self.assertEqual((c['method'], c['url']), (rec['method'], rec['url']))
        self.assertEqual(c['headers'], self.with_key(rec['headers']))
        self.assertEqual((rec['timeout'], c['timeout']), (3, 4), 'свідома відмінність: тайм-аут читання 4 с (було 3)')

    def test_write_matches_the_recorded_upserts(self):
        for name, mode in (('merge_duplicates', 'merge'), ('ignore_duplicates', 'insert')):
            rec = self.rec['upsert_http'][name]['calls'][0]
            self.calls.clear()
            self.net(Resp(201, b''))
            res = self.run_fn('push', self.ctx(settings={'table': 'overview_projects'}, legacy=True),
                              [self.rec['upsert_http'][name]['input_row']], mode)
            self.assertEqual(res, {'ok': 1, 'failed': {}})
            c = self.calls[0]
            self.assertEqual((c['method'], c['url']), (rec['method'], rec['url']), name)
            self.assertEqual(c['headers'], self.with_key(rec['headers']), name)
            self.assertEqual(c['body'], rec['body'], 'пакет з однієї картки = тіло запису 0.11.0')
            self.assertEqual((rec['timeout'], c['timeout']), (10, 15), 'тайм-аут запису: 15 с на пакет (було 10)')

    def test_the_url_of_the_fixture_is_the_one_we_build(self):
        """Знімок записано на вигаданій адресі: запит модуля збігається з ним і по хосту, не лише по шляху."""
        self.assertTrue(self.rec['upsert_http']['merge_duplicates']['calls'][0]['url'].startswith(URL))


class ThroughTheCoreTest(ModuleCase):
    def test_core_status_of_the_codes(self):
        self.assertEqual(dm.STATUS['dashboard-error'], 502)
        self.assertEqual(dm.STATUS['dashboard-unconfigured'], 409)

    def test_check_through_the_core_contract(self):
        """Вердикт — словник з булевим `ok` (інакше ядро скаже «check returned a result without a boolean ok»)."""
        self.net(Resp(200, []))
        for ctx in (self.ctx(), self.ctx(settings={'url': 'http://x.example'}), self.ctx(secrets={'key': 'sb_publishable_1'})):
            res = self.run_fn('check', ctx)
            self.assertIsInstance(res, dict)
            self.assertIsInstance(res['ok'], bool)

    def test_source_has_no_forbidden_imports(self):
        with open(os.path.join(MODULE_DIR, 'server.py'), encoding='utf-8') as f:
            src = f.read()
        self.assertNotRegex(src, r'(?m)^\s*(import|from)\s+(serve|deai_modules|supabase_comments)\b')
        self.assertEqual(len(re.findall(r'_opener\.open\(', src)), 1, 'запит іде в мережу в одному місці')


if __name__ == '__main__':
    unittest.main()
