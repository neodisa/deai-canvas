"""`app/modules/jira-tracker`: статуси задач із Jira Cloud (роль `tracker`, 4c-2, Task 3).

Модуль вантажиться через справжній `deai_modules.catalog()`: так тест бачить саме те, що виконає сервер (зокрема
`ctx['ModuleError']` ядра). ⛔ Жодного реального запиту: шов мережі — імʼя `_open` у глобалах модуля (ЄДИНЕ місце, де запит
іде в мережу); тест підміняє його записувачем, що віддає сценарні відповіді. Побудова запиту, заголовки й розбір — справжні.

Що доводиться:
  * маніфест (`roles`, налаштування, токен БЕЗ `public`) і функції ролі;
  * адреса (правила `_host_ok`), пошта, токен; `check` (200/401/403/500/мережа); `statuses` (розбір, сміття, межі `timeout_s`);
  * форма запиту збігається з ЗАПИСАНОЮ в знімку 0.12.0 (`tests/fixtures/tracker/before-4c2.json`, `jira_request`): метод, шлях,
    тіло й набір заголовків; адреса тепер із налаштувань, `Authorization` порівнюється як «Basic від email:токен»;
  * ⛔ жоден текст помилки не містить токена, пошти, тіла запиту чи відповіді й не довший за 200 знаків; редирект не виконується.
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

BEFORE = os.path.join(_HERE, 'fixtures', 'tracker', 'before-4c2.json')
BASE = 'https://demo.atlassian.example'
EMAIL = 'alpha@example.com'
TOKEN = 'tok-test-1'
ISSUES = {'issues': [
    {'key': 'DEMO-1', 'fields': {'status': {'name': 'In Review', 'statusCategory': {'key': 'indeterminate'}}}},
    {'key': 'DEMO-2', 'fields': {'status': {'name': 'Done', 'statusCategory': {'key': 'done'}}}}]}


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
    return urllib.error.HTTPError(BASE, status, 'err', {}, io.BytesIO(body))


class ModuleCase(unittest.TestCase):
    def setUp(self):
        os.environ.pop('DEAI_EXTRA_MODULES', None)
        dm.reset_caches()
        self.mod = dm.catalog()['jira-tracker']
        self.g = self.mod.fn('check').__globals__
        self.calls = []

    def ctx(self, **over):
        base = {'space': {'id': 'alpha', 'path': ''}, 'settings': {'base': BASE, 'email': EMAIL},
                'secrets': {'token': TOKEN}, 'ModuleError': dm.ModuleError}
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
        self.assertEqual((m.id, m.status, m.version), ('jira-tracker', 'ok', '1.0.0'))
        self.assertEqual(m.roles, ['tracker'])
        st = {s['key']: s for s in m.settings}
        self.assertEqual(set(st), {'base', 'email', 'token'})
        self.assertEqual((st['base']['type'], st['base']['required']), ('text', True))
        self.assertEqual((st['email']['type'], st['email']['required']), ('text', True))
        self.assertEqual((st['token']['type'], st['token']['required']), ('secret', True))
        self.assertFalse(st['token'].get('public'), 'токен непублічний: у сторінки він не потрапляє')
        self.assertEqual(m.private_secret_keys(), ['token'])
        self.assertEqual(m.client, ())

    def test_functions_of_the_role(self):
        for fn in ('check', 'statuses'):
            self.assertIsNotNone(self.mod.fn(fn), fn)

    def test_the_readme_invents_no_urls(self):
        with open(os.path.join(ROOT, 'app', 'modules', 'jira-tracker', 'README.md'), encoding='utf-8') as f:
            text = f.read()
        self.assertNotIn('http://', text)
        for part in text.split('https://')[1:]:
            self.assertTrue(part.startswith('<сайт>.atlassian.net'), part[:40])


class AddressTest(ModuleCase):
    def test_good_addresses(self):
        for base in (BASE, BASE + '/', BASE + ':8443/', BASE + ':8443', '  ' + BASE + ' ', 'HTTPS://Demo.Atlassian.Example'):
            with self.subTest(base=base):
                self.calls.clear()
                self.net(Resp(200, ISSUES))
                self.run_fn('statuses', self.ctx(settings={'base': base}), ['DEMO-1'])
                host = base.strip().split('://')[1].rstrip('/').lower()
                self.assertEqual(self.calls[-1]['url'], f'https://{host}/rest/api/3/search/jql')

    def test_bad_addresses_are_module_error_with_the_rules_text(self):
        self.net(Resp(200, ISSUES))
        for base in ('http://demo.atlassian.example', 'https://127.0.0.1', 'https://[::1]', 'https://10.0.0.1:8443',
                     'https://localhost', 'https://atlassian', 'https://demo.atlassian.example/path',
                     'https://demo.atlassian.example/?a=1', 'https://demo.atlassian.example?a=1',
                     'https://user@demo.atlassian.example', 'https://user:pw@demo.atlassian.example',
                     'https://demo.atlassian.example:0', 'https://demo.atlassian.example:70000',
                     'https://-bad.atlassian.example', 'https://demo..atlassian.example', 'https://demo.atlassian.1',
                     'demo.atlassian.example', 'ftp://demo.atlassian.example', 5, ['x'], {'a': 1}):
            with self.subTest(base=base):
                e = self.raises('statuses', self.ctx(settings={'base': base}), ['DEMO-1'])
                self.assertEqual(e.code, 'module-error')
                self.assertIn('https', e.message)
                self.assertIn('base', e.message)
                v = self.raw('check', self.ctx(settings={'base': base}))
                self.assertEqual((v['ok'], v['error']), (False, 'module-error'))
        self.assertEqual(self.calls, [], 'жодного запиту до перевірки адреси')

    def test_the_address_is_never_echoed_in_the_error(self):
        self.net(Resp(200, ISSUES))
        e = self.raises('statuses', self.ctx(settings={'base': 'https://user:pw-secret@demo.atlassian.example'}), ['DEMO-1'])
        self.assertNotIn('pw-secret', e.message)

    def test_a_missing_base_is_unconfigured(self):
        self.net(Resp(200, ISSUES))
        for st in ({'base': None}, {'base': ''}, {'base': '   '}):
            self.assertEqual(self.raises('statuses', self.ctx(settings=st), ['DEMO-1']).code, 'tracker-unconfigured')
        self.assertEqual(self.calls, [])


class CredentialsTest(ModuleCase):
    def test_bad_emails_are_refused_without_a_request(self):
        self.net(Resp(200, ISSUES))
        for email in ('alpha', 'alpha.example.com', 'a' * 250 + '@e.co', 'al pha@example.com', 'al:pha@example.com',
                      'alpha@exa\nmple.com', 5, ['a@b.c']):
            with self.subTest(email=email):
                e = self.raises('statuses', self.ctx(settings={'email': email}), ['DEMO-1'])
                self.assertEqual(e.code, 'module-error')
                self.assertIn('email', e.message)
        self.assertEqual(self.calls, [])

    def test_an_email_of_254_chars_passes(self):
        self.net(Resp(200, ISSUES))
        email = 'a' * (254 - len('@example.com')) + '@example.com'
        self.assertEqual(len(email), 254)
        self.run_fn('statuses', self.ctx(settings={'email': email}), ['DEMO-1'])
        self.assertEqual(len(self.calls), 1)

    def test_missing_email_or_token_is_unconfigured(self):
        self.net(Resp(200, ISSUES))
        self.assertEqual(self.raises('statuses', self.ctx(settings={'email': ''}), ['DEMO-1']).code, 'tracker-unconfigured')
        for sec in ({}, {'token': ''}, {'token': '  '}, {'token': None}):
            self.assertEqual(self.raises('statuses', self.ctx(secrets=sec), ['DEMO-1']).code, 'tracker-unconfigured')
        self.assertEqual(self.calls, [])

    def test_a_token_with_a_space_or_non_ascii_is_refused(self):
        self.net(Resp(200, ISSUES))
        for tok in ('tok test', 'tok\ntest', 'токен', 'tok\x00x', 5):
            e = self.raises('statuses', self.ctx(secrets={'token': tok}), ['DEMO-1'])
            self.assertEqual(e.code, 'module-error', repr(tok))
        self.assertEqual(self.calls, [])


class CheckTest(ModuleCase):
    def test_200_is_connected(self):
        self.net(Resp(200, {'accountId': 'x'}))
        self.assertEqual(self.raw('check', self.ctx()), {'ok': True, 'detail': 'підключено до Jira'})
        c = self.calls[0]
        self.assertEqual((c['method'], c['url'], c['body']), ('GET', BASE + '/rest/api/3/myself', None))
        self.assertEqual(c['timeout'], 4)

    def test_check_through_the_core(self):
        self.net(Resp(200, {}))
        self.assertTrue(self.run_fn('check', self.ctx())['ok'])

    def test_401_and_403_say_wrong_email_or_token(self):
        for status in (401, 403):
            self.net(http_error(status, {'message': 'Client must be authenticated'}))
            v = self.raw('check', self.ctx())
            self.assertEqual((v['ok'], v['error']), (False, 'module-error'))
            self.assertIn('невірний email чи токен', v['detail'])
            self.assertIn(str(status), v['detail'])

    def test_500_has_the_status(self):
        self.net(http_error(500, b'oops'))
        v = self.raw('check', self.ctx())
        self.assertEqual((v['ok'], v['error']), (False, 'tracker-error'))
        self.assertIn('HTTP 500', v['detail'])

    def test_network_failure_says_unreachable(self):
        for exc in (urllib.error.URLError(OSError('refused')), TimeoutError('t'), ConnectionResetError('r')):
            self.net(exc)
            v = self.raw('check', self.ctx())
            self.assertEqual((v['ok'], v['error']), (False, 'network'))
            self.assertIn('Jira недосяжна', v['detail'])

    def test_a_missing_setting_is_a_verdict_not_an_exception(self):
        self.net(Resp(200, {}))
        for ctx in (self.ctx(settings={'base': ''}), self.ctx(settings={'email': ''}), self.ctx(secrets={})):
            v = self.raw('check', ctx)
            self.assertEqual((v['ok'], v['error']), (False, 'module-error'))
        self.assertEqual(self.calls, [])


class StatusesTest(ModuleCase):
    def test_parses_the_answer(self):
        self.net(Resp(200, ISSUES))
        out = self.run_fn('statuses', self.ctx(), ['DEMO-1', 'DEMO-2'])
        self.assertEqual(out, {'DEMO-1': {'name': 'In Review', 'cat': 'indeterminate'},
                               'DEMO-2': {'name': 'Done', 'cat': 'done'}})

    def test_the_request(self):
        self.net(Resp(200, ISSUES))
        self.run_fn('statuses', self.ctx(), ['DEMO-1', 'DEMO-2'])
        c = self.calls[0]
        self.assertEqual((c['method'], c['url']), ('POST', BASE + '/rest/api/3/search/jql'))
        self.assertEqual(c['body'], {'jql': 'key in (DEMO-1,DEMO-2)', 'fields': ['status'], 'maxResults': 100})
        self.assertEqual(c['headers']['accept'], 'application/json')
        self.assertEqual(c['headers']['content-type'], 'application/json')
        self.assertEqual(c['headers']['authorization'], 'Basic ' + base64.b64encode(f'{EMAIL}:{TOKEN}'.encode()).decode())
        self.assertEqual(set(c['headers']), {'accept', 'authorization', 'content-type'})
        self.assertNotIn(TOKEN, c['url'])

    def test_no_keys_is_no_request(self):
        self.net(Resp(200, ISSUES))
        self.assertEqual(self.run_fn('statuses', self.ctx(), []), {})
        self.assertEqual(self.calls, [])

    def test_the_module_checks_the_keys_itself(self):
        """Ключі йдуть у JQL: навіть коли ядро помилилось, модуль не пустить сміття."""
        self.net(Resp(200, ISSUES))
        for keys in ('DEMO-1', None, ['demo-1'], ['DEMO-1) OR (x'], ['DEMO-1', 5], [None], ['DEMO-1\n'],
                     ['DEMO-%d' % i for i in range(1, 102)]):
            with self.subTest(keys=keys):
                self.assertEqual(self.raises('statuses', self.ctx(), keys).code, 'module-error')
        self.assertEqual(self.calls, [])
        self.run_fn('statuses', self.ctx(), ['DEMO-%d' % i for i in range(1, 101)])
        self.assertEqual(len(self.calls), 1, 'рівно 100 ключів — один запит')

    def test_timeout_comes_from_the_ctx_budget(self):
        self.net(Resp(200, ISSUES))
        for given, want in ((15, 15), (1, 1), (30, 30), (2.5, 2.5), (None, 4), ('15', 4), (0, 4), (0.5, 4), (31, 4), (-1, 4),
                            (True, 4), (float('nan'), 4), (float('inf'), 4), ([15], 4)):
            with self.subTest(given=given):
                self.calls.clear()
                ctx = self.ctx()
                if given is not None:
                    ctx['timeout_s'] = given
                self.run_fn('statuses', ctx, ['DEMO-1'])
                self.assertEqual(self.calls[0]['timeout'], want)

    def test_missing_or_bad_issues_is_empty(self):
        for body in ({}, {'issues': None}, {'issues': 'x'}, {'issues': {'a': 1}}, {'issues': []}, {'total': 0}):
            self.net(Resp(200, body))
            self.assertEqual(self.run_fn('statuses', self.ctx(), ['DEMO-1']), {}, body)

    def test_entries_without_a_key_or_status_are_skipped(self):
        body = {'issues': [
            {'fields': {'status': {'name': 'A'}}},
            {'key': 'DEMO-1'},
            {'key': 'DEMO-2', 'fields': None},
            {'key': 'DEMO-3', 'fields': {'status': None}},
            {'key': 'DEMO-4', 'fields': {'status': {'name': ''}}},
            {'key': 'DEMO-5', 'fields': {'status': {'name': 7}}},
            {'key': 5, 'fields': {'status': {'name': 'B'}}},
            'junk', None, 3,
            {'key': 'DEMO-6', 'fields': {'status': {'name': 'Open'}}},
            {'key': 'DEMO-7', 'fields': {'status': {'name': 'Open', 'statusCategory': {'key': 5}}}},
            {'key': 'DEMO-8', 'fields': {'status': {'name': 'Open', 'statusCategory': 'x'}}}]}
        self.net(Resp(200, body))
        keys = ['DEMO-%d' % i for i in range(1, 9)]
        self.assertEqual(self.run_fn('statuses', self.ctx(), keys),
                         {'DEMO-6': {'name': 'Open', 'cat': None}, 'DEMO-7': {'name': 'Open', 'cat': None},
                          'DEMO-8': {'name': 'Open', 'cat': None}})

    def test_garbage_answers_are_tracker_error(self):
        for payload in (b'', b'not json', b'[1,2]', b'"x"', b'null', b'\xff\xfe', b'[' * 100000):
            self.net(Resp(200, payload))
            e = self.raises('statuses', self.ctx(), ['DEMO-1'])
            self.assertEqual(e.code, 'tracker-error', payload[:8])

    def test_an_oversized_answer_is_tracker_error(self):
        self.net(Resp(200, b'x' * ((4 << 20) + 5)))
        self.assertEqual(self.raises('statuses', self.ctx(), ['DEMO-1']).code, 'tracker-error')

    def test_http_failures_carry_the_status(self):
        for status, code in ((400, 'module-error'), (401, 'module-error'), (403, 'module-error'), (404, 'module-error'),
                             (408, 'tracker-error'), (429, 'tracker-error'), (500, 'tracker-error'), (503, 'tracker-error')):
            with self.subTest(status=status):
                self.net(http_error(status, {'errorMessages': ['Issue does not exist']}))
                e = self.raises('statuses', self.ctx(), ['DEMO-1'])
                self.assertEqual(e.code, code)
                self.assertIn(f'HTTP {status}', e.message)

    def test_a_400_has_the_fixed_hint_without_the_body(self):
        self.net(http_error(400, {'errorMessages': ['Issue DEMO-1 does not exist']}))
        e = self.raises('statuses', self.ctx(), ['DEMO-1'])
        self.assertEqual((e.code, e.message), ('module-error', 'Jira відхилила запит (HTTP 400): перевірте ключі задач'))

    def test_a_huge_error_body_still_gives_the_status_text(self):
        for status, code in ((400, 'module-error'), (404, 'module-error'), (429, 'tracker-error'), (500, 'tracker-error')):
            with self.subTest(status=status):
                self.net(http_error(status, b'x' * ((4 << 20) + 5)))
                e = self.raises('statuses', self.ctx(), ['DEMO-1'])
                self.assertEqual(e.code, code)
                self.assertIn(f'HTTP {status}', e.message)
                self.assertNotIn('завелика', e.message)
                v = self.raw('check', self.ctx())
                self.assertNotIn('завелика', v['detail'])

    def test_network_failure_is_tracker_error(self):
        self.net(urllib.error.URLError(OSError('refused')))
        e = self.raises('statuses', self.ctx(), ['DEMO-1'])
        self.assertEqual(e.code, 'tracker-error')
        self.assertIn('Jira недосяжна', e.message)


class SecretsInTextsTest(ModuleCase):
    """⛔ Тексти помилок — фіксовані слова + HTTP-статус: ні токена, ні пошти, ні тіл запиту й відповіді; ≤ 200 знаків."""

    BODY = {'errorMessages': ['Issue DEMO-1 alpha@example.com tok-test-1 does not exist'], 'errors': {'jql': 'DEMO-1 !!'}}

    def texts(self):
        """Усі тексти помилок і вердиктів, які модуль віддає на збої; відповіді містять токен, пошту й ключ."""
        out = []
        for status in (400, 401, 403, 404, 302, 500, 502):
            self.net(http_error(status, self.BODY))
            out.append(self.raises('statuses', self.ctx(), ['DEMO-1']).message)
            out.append(self.raw('check', self.ctx())['detail'])
        for exc in (urllib.error.URLError(OSError(f'{TOKEN} {EMAIL}')), OSError(TOKEN), ValueError(EMAIL)):
            self.net(exc)
            out.append(self.raises('statuses', self.ctx(), ['DEMO-1']).message)
            out.append(self.raw('check', self.ctx())['detail'])
        return out

    def test_no_text_has_the_token_email_or_bodies(self):
        for text in self.texts():
            with self.subTest(text=text):
                self.assertNotIn(TOKEN, text)
                self.assertNotIn(EMAIL, text)
                self.assertNotIn('DEMO-1', text, 'у повідомленні Jira могли бути ключі й назви')
                self.assertNotIn('does not exist', text)
                self.assertLessEqual(len(text), 200)

    def test_clean_scrubs_the_token_and_email_from_the_failure_class_name(self):
        """Єдина дорога значення в текст — ім'я класу збою (`type(e).__name__`): самі функції без ядра (його `_scrub` ховав би це)."""
        evil = type(f'{TOKEN}-{EMAIL}', (OSError,), {})
        self.net(evil('boom'))
        v = self.raw('check', self.ctx())
        self.assertEqual(v['error'], 'network')
        self.assertNotIn(TOKEN, v['detail'])
        self.assertNotIn(EMAIL, v['detail'])
        self.assertIn('***', v['detail'])
        with self.assertRaises(dm.ModuleError) as cm:
            self.raw('statuses', self.ctx(), ['DEMO-1'])
        self.assertNotIn(TOKEN, cm.exception.message)
        self.assertNotIn(EMAIL, cm.exception.message)

    def test_clean_cuts_to_200_and_drops_control_characters(self):
        evil = type('x' * 400 + '\n\x01y', (OSError,), {})
        self.net(evil('boom'))
        d = self.raw('check', self.ctx())['detail']
        self.assertLessEqual(len(d), 200)
        self.assertNotRegex(d, r'[\x00-\x1f]')


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
            e = self.raises('statuses', self.ctx(), ['DEMO-1'])
        self.assertEqual(seen, [BASE + '/rest/api/3/search/jql'], 'другого запиту (на Location) нема')
        self.assertEqual(e.code, 'module-error')
        self.assertIn('HTTP 302', e.message)
        self.assertNotIn('evil.example', e.message)


class SnapshotParityTest(ModuleCase):
    """Запит модуля = запит знімка 0.12.0 (`jira_request`): метод, шлях, тіло, набір заголовків. Адреса — з налаштувань."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)['jira_request']['request']

    def test_the_request_equals_the_snapshot(self):
        want = self.snap['calls'][0]
        self.net(Resp(200, self.snap['stub_response']))
        out = self.run_fn('statuses', self.ctx(timeout_s=want['timeout']), ['DEMO-1', 'DEMO-2'])
        c = self.calls[0]
        self.assertEqual(c['method'], want['method'])
        self.assertEqual(c['url'], BASE + want['path'] + (('?' + want['query']) if want['query'] else ''))
        self.assertEqual(c['body'], want['body'])
        headers = dict(c['headers'])
        self.assertEqual(want['headers']['authorization'], '<basic>')
        self.assertTrue(want['authorization_is_basic_of_credentials'])
        self.assertEqual(headers['authorization'], 'Basic ' + base64.b64encode(f'{EMAIL}:{TOKEN}'.encode()).decode())
        headers['authorization'] = '<basic>'                      # значення не зберігається ніде: лише «є Basic від email:токена»
        self.assertEqual(headers, want['headers'])
        self.assertEqual(c['timeout'], want['timeout'])
        self.assertEqual(out, self.snap['result'])

    def test_the_snapshot_input_after_the_core_filter_is_the_modules_input(self):
        """Знімок слав у Jira рівно унікальні непорожні ключі: те, що лишається після фільтра ядра, дає той самий JQL."""
        import tracker
        keys = tracker.keys_of({str(i): {'jira': k} for i, k in enumerate(self.snap['input_keys'])})
        self.assertEqual(keys, ['DEMO-1', 'DEMO-2'])
        self.net(Resp(200, self.snap['stub_response']))
        self.run_fn('statuses', self.ctx(), keys)
        self.assertEqual(self.calls[0]['body'], self.snap['calls'][0]['body'])


if __name__ == '__main__':
    unittest.main()
