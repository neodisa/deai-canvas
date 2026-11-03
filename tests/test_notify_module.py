"""`app/modules/supabase-teams`: сповіщення Teams із проєкту Supabase (роль `notify`, 4c-3, Task 3).

Модуль вантажиться через справжній `deai_modules.catalog()`: так тест бачить саме те, що виконає сервер (зокрема
`ctx['ModuleError']` ядра). ⛔ Жодного реального запиту: шов мережі — імʼя `_open` у глобалах модуля (ЄДИНЕ місце, де запит
іде в мережу); тест підміняє його записувачем, що віддає сценарні відповіді. Побудова запиту, заголовки й розбір — справжні.

Що доводиться:
  * маніфест (`roles`, `url`, `key` БЕЗ `public`) і функції ролі;
  * форма запитів `mute_state`/`mute_set` збігається з ЗАПИСАНОЮ в знімку 0.13.0 (`tests/fixtures/notify/before-4c3.json`,
    `rpc_requests`): метод, шлях, тіло, набір заголовків, тайм-аут 8;
  * `check`: адреса, публічний ключ (не для `legacy`), нема схеми (404 / PGRST202 / 42883), вебхук без секрету, здоровʼя;
    для `legacy` `teams_notify_health` НЕ кличеться;
  * ⛔ жоден текст помилки не містить ключа й тіл відповіді й не довший за 200 знаків; редирект не виконується.
"""
import base64
import http.client
import io
import json
import os
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

BEFORE = os.path.join(_HERE, 'fixtures', 'notify', 'before-4c3.json')
URL = 'https://demo.supabase.example'
KEY = 'sk-test-0123456789'
ME = 'k:0123456789ab'
STATE = [{'project_id': 'dc/t1', 'muted_at': '2026-11-01T10:00:00', 'muted_by': 'k:ffffffffffff'}]
HEALTH_OK = [{'webhook_set': True, 'sent': 5, 'responded': 4, 'failed': 1, 'last_failed_at': None, 'last_sent_at': None}]


def jwt(role):
    """JWT без підпису: розбирається лише корисна частина (як у справжніх ключах Supabase)."""
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')
    return '.'.join((b64({'alg': 'HS256', 'typ': 'JWT'}), b64({'role': role, 'iss': 'supabase-demo'}), 'sig'))


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


def by_path(table):
    """Сценарій за назвою RPC: `{'teams_mute_state': відповідь, …}` → функція для `ModuleCase.net`."""
    def script(i, call):
        name = call['url'].rsplit('/', 1)[-1]
        return table[name]
    return script


class ModuleCase(unittest.TestCase):
    def setUp(self):
        os.environ.pop('DEAI_EXTRA_MODULES', None)
        dm.reset_caches()
        self.mod = dm.catalog()['supabase-teams']
        self.g = self.mod.fn('check').__globals__
        self.calls = []

    def ctx(self, **over):
        base = {'space': {'id': 'alpha', 'path': ''}, 'settings': {'url': URL}, 'secrets': {'key': KEY},
                'ModuleError': dm.ModuleError}
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

    def raw(self, name, ctx, *args):
        """Виклик САМОЇ функції модуля, без `deai_modules.call`: ядро теж вирізає секрети, а тут перевіряється власний `_clean`."""
        return self.mod.fn(name)(ctx, *args)

    def raises(self, name, ctx, *args):
        with self.assertRaises(dm.ModuleError) as cm:
            self.run_fn(name, ctx, *args)
        return cm.exception


class ManifestTest(ModuleCase):
    def test_manifest(self):
        m = self.mod
        self.assertEqual((m.id, m.status, m.version), ('supabase-teams', 'ok', '1.0.0'))
        self.assertEqual(m.roles, ['notify'])
        st = {s['key']: s for s in m.settings}
        self.assertEqual(set(st), {'url', 'key'})
        self.assertEqual((st['url']['type'], st['url']['required']), ('text', True))
        self.assertEqual((st['key']['type'], st['key']['required']), ('secret', True))
        self.assertFalse(st['key'].get('public'), 'ключ непублічний: у сторінки він не потрапляє')
        self.assertEqual(m.private_secret_keys(), ['key'])
        self.assertEqual(m.client, ())

    def test_functions_of_the_role(self):
        for fn in ('check', 'mute_state', 'mute_set'):
            self.assertIsNotNone(self.mod.fn(fn), fn)

    def test_the_readme_invents_no_urls(self):
        with open(os.path.join(ROOT, 'app', 'modules', 'supabase-teams', 'README.md'), encoding='utf-8') as f:
            text = f.read()
        self.assertNotIn('http://', text)
        for part in text.split('https://')[1:]:
            self.assertTrue(part.startswith(('<ref>.supabase.co', '"', '`')) or part[:1] in ' ,.)', part[:40])
        self.assertNotRegex(text, r'logic\.azure|office\.com|powerplatform')


class AddressTest(ModuleCase):
    def test_good_addresses(self):
        for url in (URL, URL + '/', URL + ':8443/', URL + ':8443', '  ' + URL + ' ', 'HTTPS://Demo.Supabase.Example'):
            with self.subTest(url=url):
                self.calls.clear()
                self.net(Resp(200, STATE))
                self.run_fn('mute_state', self.ctx(settings={'url': url}))
                host = url.strip().split('://')[1].rstrip('/').lower()
                self.assertEqual(self.calls[-1]['url'], f'https://{host}/rest/v1/rpc/teams_mute_state')

    def test_bad_addresses_are_module_error_with_the_rules_text(self):
        self.net(Resp(200, STATE))
        for url in ('http://demo.supabase.example', 'https://127.0.0.1', 'https://[::1]', 'https://10.0.0.1:8443',
                    'https://localhost', 'https://supabase', 'https://demo.supabase.example/path',
                    'https://demo.supabase.example/?a=1', 'https://demo.supabase.example?a=1',
                    'https://user@demo.supabase.example', 'https://user:pw@demo.supabase.example',
                    'https://demo.supabase.example:0', 'https://demo.supabase.example:70000',
                    'https://-bad.supabase.example', 'https://demo..supabase.example', 'https://demo.supabase.1',
                    'demo.supabase.example', 'ftp://demo.supabase.example', 5, ['x'], {'a': 1}):
            with self.subTest(url=url):
                e = self.raises('mute_state', self.ctx(settings={'url': url}))
                self.assertEqual(e.code, 'module-error')
                self.assertIn('https', e.message)
                self.assertIn('url', e.message)
                v = self.raw('check', self.ctx(settings={'url': url}))
                self.assertEqual((v['ok'], v['error']), (False, 'module-error'))
        self.assertEqual(self.calls, [], 'жодного запиту до перевірки адреси')

    def test_the_address_is_never_echoed_in_the_error(self):
        self.net(Resp(200, STATE))
        e = self.raises('mute_state', self.ctx(settings={'url': 'https://user:pw-secret@demo.supabase.example'}))
        self.assertNotIn('pw-secret', e.message)

    def test_a_missing_url_or_key_is_unconfigured(self):
        self.net(Resp(200, STATE))
        for st in ({'url': None}, {'url': ''}, {'url': '   '}):
            self.assertEqual(self.raises('mute_state', self.ctx(settings=st)).code, 'notify-unconfigured')
        for sec in ({}, {'key': ''}, {'key': '  '}, {'key': None}):
            self.assertEqual(self.raises('mute_state', self.ctx(secrets=sec)).code, 'notify-unconfigured')
        self.assertEqual(self.calls, [])

    def test_a_key_with_a_space_or_non_ascii_is_refused(self):
        self.net(Resp(200, STATE))
        for key in ('sk test', 'sk\ntest', 'ключ', 'sk\x00x'):
            self.assertEqual(self.raises('mute_state', self.ctx(secrets={'key': key})).code, 'module-error', repr(key))
        self.assertEqual(self.raises('mute_state', self.ctx(secrets={'key': 5})).code, 'notify-unconfigured')   # не рядок = нема ключа
        self.assertEqual(self.calls, [])


class SnapshotParityTest(ModuleCase):
    """Запити модуля = запити `teams_rpc` 0.13.0 зі знімка: метод, шлях, тіло, НАБІР заголовків, тайм-аут. Адреса — з налаштувань."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)['rpc_requests']

    def assert_same_request(self, want, got):
        self.assertEqual(got['method'], want['method'])
        self.assertEqual(got['url'], URL + want['path'] + (('?' + want['query']) if want['query'] else ''))
        self.assertEqual(got['body'], want['body'])
        self.assertEqual(got['timeout'], want['timeout'])
        headers = dict(got['headers'])
        self.assertEqual(headers['apikey'], KEY)
        self.assertEqual(headers['authorization'], 'Bearer ' + KEY)
        self.assertEqual(want['headers']['apikey'], '<key>')                # у знімку значення ключа нема — лише мітка
        headers['apikey'], headers['authorization'] = '<key>', 'Bearer <key>'
        self.assertEqual(headers, want['headers'])

    def test_mute_state_request_and_result(self):
        snap = self.snap['state']
        self.net(Resp(200, snap['stub_response']))
        out = self.run_fn('mute_state', self.ctx())
        self.assertEqual(len(self.calls), 1)
        self.assert_same_request(snap['calls'][0], self.calls[0])
        self.assertEqual(out, snap['result'])

    def test_mute_set_request_and_result_for_both_directions(self):
        for key, muted in (('set', True), ('unset', False)):
            with self.subTest(key=key):
                self.calls.clear()
                snap = self.snap[key]
                self.net(Resp(200, muted))
                out = self.run_fn('mute_set', self.ctx(), 'dc/t1', muted, ME)
                self.assertEqual(len(self.calls), 1)
                self.assert_same_request(snap['calls'][0], self.calls[0])
                self.assertIs(out, snap['result'])

    def test_the_header_set_is_exactly_three(self):
        self.net(Resp(200, []))
        self.run_fn('mute_state', self.ctx())
        self.assertEqual(set(self.calls[0]['headers']), {'apikey', 'authorization', 'content-type'})
        self.assertNotIn(KEY, self.calls[0]['url'])


class MuteStateTest(ModuleCase):
    def test_returns_the_rows_as_they_came(self):
        self.net(Resp(200, STATE + ['junk']))
        self.assertEqual(self.run_fn('mute_state', self.ctx()), STATE + ['junk'])   # чистить ядро (`notify.normalize_mutes`)

    def test_an_empty_list(self):
        self.net(Resp(200, []))
        self.assertEqual(self.run_fn('mute_state', self.ctx()), [])

    def test_a_non_list_answer_is_notify_error(self):
        for body in ({'a': 1}, 'x', None, 5, True, b'', b'not json', b'\xff\xfe', b'[' * 100000):
            self.net(Resp(200, body))
            self.assertEqual(self.raises('mute_state', self.ctx()).code, 'notify-error', body)

    def test_http_failures_carry_the_status_and_the_postgrest_code(self):
        for status in (400, 401, 403, 500, 502):
            self.net(http_error(status, {'code': 'XX000', 'message': 'secret body'}))
            e = self.raises('mute_state', self.ctx())
            self.assertEqual(e.code, 'notify-error')
            self.assertIn(f'HTTP {status}', e.message)
            self.assertIn('[XX000]', e.message)
            self.assertNotIn('secret body', e.message)

    def test_a_missing_function_says_run_the_schema(self):
        for err in (http_error(404, {}), http_error(400, {'code': 'PGRST202'}), http_error(400, {'code': '42883'})):
            self.net(err)
            e = self.raises('mute_state', self.ctx())
            self.assertEqual(e.code, 'notify-error')
            self.assertIn('schema.sql', e.message)

    def test_network_failure_is_notify_error(self):
        self.net(urllib.error.URLError(OSError('refused')))
        e = self.raises('mute_state', self.ctx())
        self.assertEqual(e.code, 'notify-error')
        self.assertIn('Supabase недоступний', e.message)


class MuteSetTest(ModuleCase):
    def test_arguments_are_checked_before_any_request(self):
        self.net(Resp(200, True))
        for args in (('', True, ME), (None, True, ME), (5, True, ME), ('c' * 201, True, ME), ('dc/t1', 'yes', ME),
                     ('dc/t1', 1, ME), ('dc/t1', None, ME), ('dc/t1', True, 'b' * 201), ('dc/t1', True, None),
                     ('dc/t1', True, 5)):
            with self.subTest(args=args):
                self.assertEqual(self.raises('mute_set', self.ctx(), *args).code, 'module-error')
        self.assertEqual(self.calls, [])
        self.run_fn('mute_set', self.ctx(), 'c' * 200, True, '')
        self.assertEqual(len(self.calls), 1, 'порожній підпис і канал у 200 знаків дозволені')

    def test_a_non_bool_answer_is_notify_error(self):
        for body in ([], {'a': 1}, 'true', None, 1, b'', b'nope'):
            self.net(Resp(200, body))
            self.assertEqual(self.raises('mute_set', self.ctx(), 'dc/t1', True, ME).code, 'notify-error', body)

    def test_the_answer_is_the_new_state(self):
        self.net(Resp(200, False))
        self.assertIs(self.run_fn('mute_set', self.ctx(), 'dc/t1', False, ME), False)

    def test_http_failures_and_network(self):
        self.net(http_error(403, {'code': '42501'}))
        e = self.raises('mute_set', self.ctx(), 'dc/t1', True, ME)
        self.assertEqual(e.code, 'notify-error')
        self.assertIn('HTTP 403', e.message)
        self.net(urllib.error.URLError(OSError('refused')))
        self.assertIn('Supabase недоступний', self.raises('mute_set', self.ctx(), 'dc/t1', True, ME).message)


class CheckTest(ModuleCase):
    GOOD = {'teams_mute_state': Resp(200, []), 'teams_notify_health': Resp(200, HEALTH_OK)}

    def test_ok_says_the_delivery_numbers(self):
        self.net(by_path(self.GOOD))
        v = self.raw('check', self.ctx())
        self.assertEqual(v, {'ok': True, 'detail': 'доставок за 6 год: 5, невдалих: 1'})
        self.assertEqual([c['url'].rsplit('/', 1)[-1] for c in self.calls], ['teams_mute_state', 'teams_notify_health'])
        self.assertEqual(self.calls[1]['body'], {'window_hours': 6})
        self.assertEqual({c['timeout'] for c in self.calls}, {8})

    def test_check_through_the_core(self):
        self.net(by_path(self.GOOD))
        self.assertTrue(self.run_fn('check', self.ctx())['ok'])

    def test_health_may_come_as_a_single_object(self):
        self.net(by_path({**self.GOOD, 'teams_notify_health': Resp(200, HEALTH_OK[0])}))
        self.assertTrue(self.raw('check', self.ctx())['ok'])

    def test_a_missing_webhook_secret_is_its_own_verdict(self):
        row = {**HEALTH_OK[0], 'webhook_set': False}
        self.net(by_path({**self.GOOD, 'teams_notify_health': Resp(200, [row])}))
        v = self.raw('check', self.ctx())
        self.assertEqual((v['ok'], v['error']), (False, 'notify-no-webhook'))
        self.assertIn('teams_webhook_url', v['detail'])
        self.assertEqual(self.run_fn('check', self.ctx())['error'], 'notify-no-webhook', 'каркас віддає код як є')

    def test_a_missing_schema_says_run_schema_sql(self):
        for status, body in ((404, {}), (404, {'code': 'PGRST202'}), (400, {'code': 'PGRST202'}), (400, {'code': '42883'})):
            for broken in ('teams_mute_state', 'teams_notify_health'):
                with self.subTest(status=status, body=body, broken=broken):
                    # ⚠️ Свіжа помилка на кожен прогін: `HTTPError` читається один раз і закривається.
                    self.net(by_path({**self.GOOD, broken: http_error(status, body)}))
                    v = self.raw('check', self.ctx())
                    self.assertEqual((v['ok'], v['error']), (False, 'no-schema'))
                    self.assertIn('schema.sql', v['detail'])

    def test_a_bad_key_and_other_statuses(self):
        for status, code in ((401, 'bad-key'), (403, 'bad-key'), (500, 'notify-error'), (400, 'notify-error')):
            with self.subTest(status=status):
                self.net(by_path({**self.GOOD, 'teams_mute_state': http_error(status, {})}))
                v = self.raw('check', self.ctx())
                self.assertEqual((v['ok'], v['error']), (False, code))
                self.assertIn(f'HTTP {status}', v['detail'])

    def test_network_failure_says_network(self):
        for exc in (urllib.error.URLError(OSError('refused')), TimeoutError('t'), ConnectionResetError('r')):
            self.net(exc)
            v = self.raw('check', self.ctx())
            self.assertEqual((v['ok'], v['error']), (False, 'network'))

    def test_garbage_answers_are_notify_error(self):
        for first in (Resp(200, {'a': 1}), Resp(200, b'not json'), Resp(200, b'')):
            self.net(by_path({**self.GOOD, 'teams_mute_state': first}))
            self.assertEqual(self.raw('check', self.ctx())['error'], 'notify-error')
        for health in ([], [HEALTH_OK[0], HEALTH_OK[0]], {'webhook_set': 'yes'}, [{'sent': 1, 'failed': 0}], b'junk',
                       [{**HEALTH_OK[0], 'sent': 'many'}], [{**HEALTH_OK[0], 'failed': True}]):
            self.net(by_path({**self.GOOD, 'teams_notify_health': Resp(200, health)}))
            self.assertEqual(self.raw('check', self.ctx())['error'], 'notify-error', health)

    def test_an_oversized_answer_is_a_verdict_not_an_exception(self):
        self.net(by_path({**self.GOOD, 'teams_mute_state': Resp(200, b'x' * ((1 << 20) + 5))}))
        v = self.raw('check', self.ctx())
        self.assertEqual((v['ok'], v['error']), (False, 'notify-error'))
        self.assertIn('завелика', v['detail'])

    def test_a_missing_setting_is_a_verdict_not_an_exception(self):
        self.net(Resp(200, []))
        for ctx in (self.ctx(settings={'url': ''}), self.ctx(secrets={}), self.ctx(secrets={'key': 'ключ'})):
            v = self.raw('check', ctx)
            self.assertEqual((v['ok'], v['error']), (False, 'module-error'))
        self.assertEqual(self.calls, [])


class PublicKeyTest(ModuleCase):
    GOOD = CheckTest.GOOD

    def test_a_public_key_is_refused_without_a_request(self):
        self.net(by_path(self.GOOD))
        for key in ('sb_publishable_abc123', jwt('anon')):
            with self.subTest(key=key[:20]):
                v = self.raw('check', self.ctx(secrets={'key': key}))
                self.assertEqual((v['ok'], v['error']), (False, 'module-error'))
                self.assertIn('непублічний ключ', v['detail'])
                self.assertNotIn(key, v['detail'])
        self.assertEqual(self.calls, [])

    def test_a_non_public_key_passes(self):
        self.net(by_path(self.GOOD))
        for key in ('sb_secret_abc123', jwt('service_role'), 'sk-test-1', 'a.b.c', 'a.' + 'e30' + '.c'):
            with self.subTest(key=key[:20]):
                self.assertTrue(self.raw('check', self.ctx(secrets={'key': key}))['ok'])

    def test_the_league_path_skips_the_public_key_check(self):
        """⛔ ЛІГА: ключ там — публічний ключ сторінки (паритет з 0.13.0), тож `legacy` публічності не перевіряє."""
        self.net(by_path(self.GOOD))
        for key in ('sb_publishable_abc123', jwt('anon')):
            self.calls.clear()
            self.assertTrue(self.raw('check', self.ctx(secrets={'key': key}, legacy=True))['ok'], key[:20])
            self.assertEqual(len(self.calls), 1)

    def test_mute_calls_never_check_the_key_publicity(self):
        """Вирішує лише `check`; справжню межу ставить сама база (`grant`)."""
        self.net(Resp(200, []))
        self.run_fn('mute_state', self.ctx(secrets={'key': jwt('anon')}))
        self.assertEqual(len(self.calls), 1)


class LegacyCheckTest(ModuleCase):
    def test_the_league_check_does_not_call_the_health_function(self):
        """⛔ У базі ЛІГИ `teams_notify_health` нема: `check` лише читає стан тиші."""
        self.net(by_path({'teams_mute_state': Resp(200, STATE)}))        # будь-який інший RPC зламав би `KeyError`
        v = self.raw('check', self.ctx(legacy=True))
        self.assertEqual(v, {'ok': True, 'detail': 'тиша Teams доступна'})
        self.assertEqual([c['url'].rsplit('/', 1)[-1] for c in self.calls], ['teams_mute_state'])

    def test_the_league_check_still_reports_failures(self):
        self.net(by_path({'teams_mute_state': http_error(404, {'code': 'PGRST202'})}))
        self.assertEqual(self.raw('check', self.ctx(legacy=True))['error'], 'no-schema')
        self.net(by_path({'teams_mute_state': http_error(401, {})}))
        self.assertEqual(self.raw('check', self.ctx(legacy=True))['error'], 'bad-key')


class NoRedirectTest(ModuleCase):
    """⛔ Редирект не виконується: інакше `urllib` віддав би `Authorization` на чужий хост."""

    def test_the_opener_has_no_redirect_handler(self):
        redirect = self.g['_NoRedirect']
        self.assertTrue(issubclass(redirect, urllib.request.HTTPRedirectHandler))
        self.assertIsNone(redirect().redirect_request(None, None, 302, 'Found', {}, 'https://evil.example/'))
        self.assertTrue(any(isinstance(h, redirect) for h in self.g['_opener'].handlers))

    def test_a_302_is_an_error_and_no_second_request_is_made(self):
        # Справжні обробники opener-а модуля, лише HTTPS-рівень підмінено: 302 → `HTTPError` (за `Location` не йдемо). Без
        # `_NoRedirect` у `_opener` стандартний обробник пішов би на `evil.example` — і `seen` мав би другий запис.
        seen = []

        class FakeHTTPS(urllib.request.HTTPSHandler):
            def https_open(self, req):
                seen.append(req.full_url)
                hdrs = http.client.HTTPMessage()
                hdrs['Location'] = 'https://evil.example/x'          # саме `HTTPMessage`: словник не знайшов би `location` без регістру
                resp = urllib.response.addinfourl(io.BytesIO(b''), hdrs, req.full_url, 302)
                resp.msg = 'Found'
                return resp
        real = [h for h in self.g['_opener'].handlers if not isinstance(h, urllib.request.HTTPSHandler)]
        fake = urllib.request.build_opener(*real, FakeHTTPS())
        with mock.patch.dict(self.g, {'_opener': fake}):
            e = self.raises('mute_state', self.ctx())
        self.assertEqual(seen, [URL + '/rest/v1/rpc/teams_mute_state'], 'другого запиту (на Location) нема')
        self.assertEqual(e.code, 'notify-error')
        self.assertIn('HTTP 302', e.message)
        self.assertNotIn('evil.example', e.message)


class OversizeTest(ModuleCase):
    def test_an_oversized_answer_is_notify_error(self):
        self.net(Resp(200, b'x' * ((1 << 20) + 5)))
        e = self.raises('mute_state', self.ctx())
        self.assertEqual(e.code, 'notify-error')
        self.assertIn('завелика', e.message)

    def test_an_answer_at_the_limit_is_read(self):
        row = json.dumps([{'project_id': 'p'}]).encode()
        pad = b' ' * ((1 << 20) - len(row))
        self.net(Resp(200, row + pad))
        self.assertEqual(self.run_fn('mute_state', self.ctx()), [{'project_id': 'p'}])

    def test_a_huge_error_body_still_gives_the_status_text(self):
        self.net(http_error(500, b'x' * ((1 << 20) + 5)))
        e = self.raises('mute_state', self.ctx())
        self.assertEqual(e.code, 'notify-error')
        self.assertIn('завелика', e.message)


class SecretsInTextsTest(ModuleCase):
    """⛔ Тексти помилок — фіксовані слова + HTTP-статус + код PostgREST: ні ключа, ні тіл запиту й відповіді; ≤ 200 знаків."""

    BODY = {'code': 'XX000', 'message': f'insert dc/t1 {KEY} secret-body', 'details': 'secret-detail'}

    def texts(self):
        out = []
        for status in (400, 401, 403, 404, 302, 500, 502):
            self.net(http_error(status, self.BODY))
            out.append(self.raises('mute_state', self.ctx()).message)
            out.append(self.raises('mute_set', self.ctx(), 'dc/t1', True, ME).message)
            out.append(self.raw('check', self.ctx())['detail'])
        for exc in (urllib.error.URLError(OSError(f'{KEY} {URL}')), OSError(KEY), ValueError(KEY)):
            self.net(exc)
            out.append(self.raises('mute_state', self.ctx()).message)
            out.append(self.raw('check', self.ctx())['detail'])
        return out

    def test_no_text_has_the_key_or_bodies(self):
        for text in self.texts():
            with self.subTest(text=text):
                self.assertNotIn(KEY, text)
                self.assertNotIn('secret-body', text)
                self.assertNotIn('secret-detail', text)
                self.assertNotIn('insert dc/t1', text)
                self.assertLessEqual(len(text), 200)

    def test_clean_scrubs_the_key_from_the_failure_class_name(self):
        """Єдина дорога значення в текст — імʼя класу збою: самі функції без ядра (його `_scrub` ховав би це)."""
        evil = type(f'{KEY}-x', (OSError,), {})
        self.net(evil('boom'))
        v = self.raw('check', self.ctx())
        self.assertEqual(v['error'], 'network')
        self.assertNotIn(KEY, v['detail'])
        self.assertIn('***', v['detail'])
        with self.assertRaises(dm.ModuleError) as cm:
            self.raw('mute_state', self.ctx())
        self.assertNotIn(KEY, cm.exception.message)

    def test_clean_cuts_to_200_and_drops_control_characters(self):
        evil = type('x' * 400 + '\n\x01y', (OSError,), {})
        self.net(evil('boom'))
        d = self.raw('check', self.ctx())['detail']
        self.assertLessEqual(len(d), 200)
        self.assertNotRegex(d, r'[\x00-\x1f]')


if __name__ == '__main__':
    unittest.main()
