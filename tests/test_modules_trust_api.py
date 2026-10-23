"""HTTP своїх модулів і довіри (етап 3c, Task 5): поля свого модуля й `notes` у `GET /api/modules`, `GET/POST
/api/module-trust`, `POST /api/module-untrust`, адреса адаптера з простором, `module-settings` недовіреного без `check`.

Світ — `World` з `test_modules_api` (сервер у процесі, ізольовані `HOME`/`DEAI_HOME`, жодної мережі). Системне вікно —
шов `DEAI_TRUST_CONFIRM` (діє, бо `DEAI_HOME` тимчасовий) чи підмінений `module_trust.ask`.
"""
import json
import os
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import serve  # noqa: E402
import deai_modules as dm  # noqa: E402
import module_trust as mt  # noqa: E402
from test_modules_api import World, _write, ROOT  # noqa: E402
from test_modules_own import _unlock  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


SERVER = '''def check(ctx):
    return {"ok": True, "detail": "own"}


def publish(ctx, build_dir, task):
    return {"folder": build_dir}


def client_config(ctx):
    return {"hello": "world"}


def list(ctx, channel):
    return []


def resolve(ctx, channel, pin_id, resolved):
    return {"ok": True}
'''


class TrustApi(World):
    def setUp(self):
        super().setUp()
        # Власне присвоєння (`World` уже поставив те саме через `patch.dict` і сам його поверне): охоронець `test_serve`
        # (`SPACE_WRITERS` → `_assigns_deai_home`) розбирає джерело САМЕ цього файла
        os.environ['DEAI_HOME'] = self.deai
        self.addCleanup(_unlock, self.tmp)           # LIFO: раніше за `rmtree` світу — інакше знімки 0500 лишились би
        # Сітка: справжнє системне вікно в тесті недосяжне. Шов `DEAI_TRUST_CONFIRM` відповідає в `confirm` РАНІШЕ за
        # `confirm_command`, тож тестам зі швом чи підміненим `ask` вона не заважає, а `subprocess` решти коду не чіпає
        net = mock.patch.object(mt, 'confirm_command', side_effect=AssertionError('системне вікно в тесті'))
        net.start()
        self.addCleanup(net.stop)
        self.modules()
        mt.clear_declined()
        os.environ[mt.SEAM_ENV] = 'yes'
        self.addCleanup(os.environ.pop, mt.SEAM_ENV, None)
        self.browser = {'Origin': self.base, 'Sec-Fetch-Site': 'same-origin'}

    def own(self, mid='acme', roles=('publish',), client=None, space=None, server=SERVER):
        d = os.path.join((space or self.off)['path'], 'modules', mid)
        man = {'api': 1, 'id': mid, 'name': mid.title(), 'version': '1.0.0', 'roles': list(roles),
               'settings': [{'key': 'token', 'type': 'secret', 'label': 'Token'}]}
        if client:
            man['client'] = client
            for n in client:
                _write(os.path.join(d, n), f'/* {n} v1 */')
        _write(os.path.join(d, 'module.json'), json.dumps(man))
        _write(os.path.join(d, 'server.py'), server)
        return d

    def view(self, mid='acme', space='off'):
        st, body = self.get(f'/api/module-trust?space={space}&id={mid}')
        self.assertEqual(st, 200, body)
        return body['trust']

    def grant(self, mid='acme', space='off', headers=None):
        return self.post('/api/module-trust', {'space': space, 'id': mid, 'hash': self.view(mid, space)['hash']},
                         headers=self.browser if headers is None else headers)

    def test_listing_fields_and_builtins_unchanged(self):
        self.own()
        lst = self.listing()
        e = lst['acme']
        self.assertEqual((e['builtin'], e['custom'], e['trust'], e['record'], e['status'], e['runs']),
                         (False, True, 'untrusted', False, 'untrusted', False))
        self.assertEqual(e['source'], os.path.join('~', 'deai-work', 'off', 'modules', 'acme'))
        self.assertNotIn('custom', lst['css-tokens'])
        self.assertNotIn('trust', lst['css-tokens'])

    def test_listing_of_every_own_state(self):
        """Форма запису свого модуля для клієнта (Tasks 6–8): `trust`, `record`, `runs`, `status`, `trust_error` лише коли є."""
        d = self.own()
        keys = ('trust', 'record', 'runs', 'status', 'trust_error')
        got = lambda mid='acme': {k: self.entry(mid).get(k) for k in keys}      # noqa: E731
        self.assertEqual(got(), dict(trust='untrusted', record=False, runs=False, status='untrusted', trust_error=None))
        self.assertEqual(self.entry('acme')['error'], dm.UNTRUSTED_TEXT)
        self.assertNotIn('trust_error', self.entry('acme'))
        self.grant()
        self.assertEqual(got(), dict(trust='trusted', record=True, runs=True, status='unchecked', trust_error=None))
        self.assertNotIn('error', self.entry('acme'))
        _write(os.path.join(d, 'more.js'), '//')                                # теку змінили після довіри: працює знімок
        self.assertEqual(got(), dict(trust='changed', record=True, runs=True, status='unchecked', trust_error=None))
        _write(os.path.join(d, 'NUL'), 'x')                                     # тека тепер не сканується, знімок цілий
        self.assertEqual(got(), dict(trust='refused', record=True, runs=True, status='unchecked', trust_error='bad-name'))
        bad = self.own('bad')
        _write(os.path.join(bad, 'NUL'), 'x')                                   # без знімка: нічого не виконується
        self.assertEqual(got('bad'), dict(trust='refused', record=False, runs=False, status='error', trust_error='bad-name'))
        _write(mt.trust_file(), '{oops')                                        # файл довіри не читається
        self.assertEqual(got('acme'), dict(trust='refused', record=False, runs=False, status='error', trust_error='bad-name'))
        os.remove(os.path.join(d, 'NUL'))
        self.assertEqual(got('acme'), dict(trust='untrusted', record=False, runs=False, status='untrusted',
                                           trust_error='trust-unreadable'))

    def test_a_trusted_module_that_fails_to_load_still_runs_here_with_an_error_status(self):
        """`runs` — є цілий знімок і його код тут виконується; збій завантаження цього коду — у `status`, а не `runs: false`."""
        self.own(server='raise RuntimeError("boom at load")\n')
        self.grant()
        e = self.entry('acme')
        self.assertEqual((e['trust'], e['record'], e['runs'], e['status']), ('trusted', True, True, 'error'))
        self.assertIn('boom at load', e['error'])
        self.assertNotIn('trust_error', e)

    def test_notes_only_when_present(self):
        st, body = self.get('/api/modules')
        self.assertEqual(sorted(body), ['modules'])
        self.own('css-tokens')
        st, body = self.get('/api/modules')
        self.assertEqual(body['notes'], [{'folder': 'modules/css-tokens', 'code': 'id-taken'}])

    def test_trust_needs_browser_headers(self):
        self.own()
        for headers in ({}, {'Origin': self.base}, {'Sec-Fetch-Site': 'same-origin'}):
            st, body = self.grant(headers=headers)
            self.refused(st, body, 403, 'trust-needs-ui')
        st, body = self.grant(headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'same-origin'})
        self.assertEqual((st, body.get('error')), (403, 'foreign origin'))
        self.assertEqual(mt.load_records(), {})

    def test_only_same_origin_fetch_metadata_passes(self):
        """`Sec-Fetch-Site` — рівно `same-origin`: `same-site`, `cross-site`, `none` (навігація користувача) і порожнє — ні."""
        self.own()
        for site in ('same-site', 'cross-site', 'none', ''):
            st, body = self.grant(headers={'Origin': self.base, 'Sec-Fetch-Site': site})
            self.refused(st, body, 403, 'trust-needs-ui')
        self.assertEqual(mt.load_records(), {})

    def test_a_null_origin_and_a_referer_do_not_replace_the_origin(self):
        self.own()
        st, body = self.grant(headers={'Origin': 'null', 'Sec-Fetch-Site': 'same-origin'})
        self.assertEqual((st, body), (403, {'ok': False, 'error': 'foreign origin'}))
        st, body = self.grant(headers={'Referer': self.base + '/', 'Sec-Fetch-Site': 'same-origin'})
        self.refused(st, body, 403, 'trust-needs-ui')
        self.assertEqual(mt.load_records(), {})

    def test_forged_browser_headers_still_meet_the_system_window(self):
        """Заголовки — фільтр, не межа: підроблені (як у скрипта сторінки макета) доходять до вікна, і «ні» людини
        лишає все як було."""
        self.own()
        with mock.patch.object(mt, 'ask', return_value='no') as ask:
            st, body = self.grant(headers={'Origin': self.base, 'Sec-Fetch-Site': 'same-origin'})
        self.refused(st, body, 409, 'trust-declined')
        self.assertIs(ask.called, True)
        self.assertEqual(mt.load_records(), {})

    def test_trust_flow(self):
        self.own()
        st, body = self.grant()
        self.assertEqual((st, body['ok'], body['module']['trust'], body['module']['runs']), (200, True, 'trusted', True), body)
        st, body = self.post('/api/module-enable', {'id': 'acme', 'secrets': {'token': 'tok'}, 'replace': True})
        self.assertEqual((st, body['check']['ok']), (200, True), body)

    def test_trust_refusals(self):
        d = self.own()
        st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': '0' * 64}, headers=self.browser)
        self.refused(st, body, 409, 'module-changed')
        st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'css-tokens', 'hash': '0' * 64},
                             headers=self.browser)
        self.refused(st, body, 404, 'unknown-module')
        h = self.view()['hash']
        _write(os.path.join(d, 'NUL'), 'x')
        st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': h}, headers=self.browser)
        self.refused(st, body, 409, 'module-refused')

    def test_odd_lang_falls_back_to_uk_and_never_breaks_the_request(self):
        self.own()
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='no') as ask:
            for lang in ([], {}, 7, 'zz'):
                st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': h, 'lang': lang},
                                     headers=self.browser)
                self.refused(st, body, 409, 'trust-declined')
                self.assertEqual(ask.call_args[0][2][2], mt.CONFIRM_TEXT['uk']['yes'], lang)

    def test_a_known_lang_reaches_the_window(self):
        self.own()
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='no') as ask:
            for lang in ('en', 'uk'):
                st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': h, 'lang': lang},
                                     headers=self.browser)
                self.refused(st, body, 409, 'trust-declined')
                self.assertEqual(ask.call_args[0][2][2], mt.CONFIRM_TEXT[lang]['yes'], lang)

    def test_trust_is_per_space(self):
        """Той самий id у двох просторах — два модулі з окремими записами: довіра в `off` не робить довіреним `on`."""
        self.own()
        self.own(space=self.on)
        self.grant('acme', 'off')
        self.assertEqual((self.entry('acme', 'off')['trust'], self.entry('acme', 'on')['trust']), ('trusted', 'untrusted'))
        v = self.view('acme', 'on')
        self.assertEqual((v['state'], v['record']), ('untrusted', False))
        self.assertTrue(v['path'].endswith(os.path.join('deai-work', 'on', 'modules', 'acme')), v['path'])
        on_source = os.path.join('~', 'deai-work', 'on', 'modules', 'acme')
        st, body = self.grant('acme', 'on')
        self.assertEqual((st, body['module']['trust'], body['module']['source']), (200, 'trusted', on_source), body)
        self.assertEqual(len(mt.load_records()), 2, 'два простори — два записи')
        st, body = self.post('/api/module-untrust', {'space': 'on', 'id': 'acme'})
        self.assertEqual((st, body['module']['trust'], body['module']['source']), (200, 'untrusted', on_source), body)
        self.assertEqual(self.entry('acme', 'off')['trust'], 'trusted', 'зняття в `on` не торкнулось `off`')
        st, body = self.post('/api/module-untrust', {'space': 'off', 'id': 'acme'})
        self.assertEqual((st, body['module']['trust']), (200, 'untrusted'), body)

    def test_system_window_answers(self):
        self.own()
        os.environ[mt.SEAM_ENV] = 'no'
        st, body = self.grant()
        self.refused(st, body, 409, 'trust-declined')
        with mock.patch.object(mt, 'confirm', side_effect=AssertionError('вікно знову')):
            os.environ[mt.SEAM_ENV] = 'yes'
            st, body = self.grant()
        self.refused(st, body, 409, 'trust-declined')
        mt.clear_declined()
        os.environ[mt.SEAM_ENV] = 'unavailable'
        st, body = self.grant()
        self.refused(st, body, 409, 'trust-no-confirm')
        os.environ[mt.SEAM_ENV] = 'yes'
        mt._ASK_LOCK.acquire()
        try:
            st, body = self.grant()
        finally:
            mt._ASK_LOCK.release()
        self.refused(st, body, 409, 'trust-busy')

    def test_untrust_keeps_space_json_and_works_without_the_folder(self):
        d = self.own()
        self.grant()
        self.post('/api/module-enable', {'id': 'acme', 'replace': True})
        before = self.sj_bytes()
        st, body = self.post('/api/module-untrust', {'space': 'off', 'id': 'acme'})
        self.assertEqual((st, body['ok'], body['module']['trust']), (200, True, 'untrusted'), body)
        self.assertEqual(self.sj_bytes(), before)
        self.grant()
        shutil.rmtree(d)
        st, body = self.post('/api/module-untrust', {'space': 'off', 'id': 'acme'})
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(mt.load_records(), {})

    def test_untrusted_settings_without_check_and_refused_check_and_enable(self):
        self.own()
        st, body = self.post('/api/module-settings', {'id': 'acme', 'secrets': {'token': 'tok'}})
        self.assertEqual(st, 200, body)
        self.assertNotIn('check', body)
        st, body = self.post('/api/module-check', {'id': 'acme'})
        self.refused(st, body, 409, 'module-untrusted')
        before = self.sj_bytes()
        st, body = self.post('/api/module-enable', {'id': 'acme', 'replace': True})
        self.refused(st, body, 409, 'module-untrusted')
        self.assertEqual(self.sj_bytes(), before)

    def test_adapter_is_served_from_the_snapshot_by_space(self):
        d = self.own('talk', roles=('comments',), client=['adapter.js'])
        st, raw = self.get('/api/module-client/off/talk/adapter.js')
        self.assertEqual(st, 404, 'недовірений адаптер роздано')
        self.grant('talk')
        _write(os.path.join(d, 'adapter.js'), '/* adapter.js v2 */')
        st, raw = self.get('/api/module-client/off/talk/adapter.js')
        self.assertEqual((st, raw), (200, '/* adapter.js v1 */'))
        self.assertEqual(self.get('/api/module-client/talk/adapter.js')[0], 404, 'свій модуль — лише з простором')
        self.assertEqual(self.get('/api/module-client/on/talk/adapter.js')[0], 404, 'чужий простір')
        self.assertEqual(self.get('/api/module-client/off/css-tokens/x.js')[0], 404)
        mod = dm.catalog(self.off)['talk']
        self.assertEqual(serve.module_client_urls(mod, self.off), ['/api/module-client/off/talk/adapter.js'])

    def test_a_builtin_adapter_has_one_address_and_not_a_space_one(self):
        """Адреса з простором — лише для СВОГО модуля: вбудований адаптер не відкривається й під нею (друга адреса того ж файла)."""
        shutil.copytree(os.path.join(ROOT, 'app', 'modules', 'supabase-comments'),
                        os.path.join(self.tmp, 'modules', 'supabase-comments'),
                        ignore=shutil.ignore_patterns('__pycache__'))
        dm.reset_caches()
        self.assertEqual(self.get('/api/module-client/supabase-comments/adapter.js')[0], 200)
        self.assertEqual(self.get('/api/module-client/off/supabase-comments/adapter.js')[0], 404)
        self.assertEqual(self.get('/api/module-client/on/supabase-comments/adapter.js')[0], 404)
        self.assertEqual(self.get('/api/module-client/ghost/supabase-comments/adapter.js')[0], 404, 'невідомий простір')

    def test_adapter_addresses_that_are_not_well_formed_are_404(self):
        d = self.own('talk', roles=('comments',), client=['adapter.js'])
        self.grant('talk')
        ok = '/api/module-client/off/talk/adapter.js'
        self.assertEqual(self.get(ok)[0], 200)
        for path in ('/api/module-client/off/talk/adapter.js/x', '/api/module-client/off//adapter.js',
                     '/api/module-client//talk/adapter.js', '/api/module-client/OFF/talk/adapter.js',
                     '/api/module-client/%2e%2e/talk/adapter.js', '/api/module-client/off/talk/%2e%2e%2fserver.py',
                     '/api/module-client/off/talk/server.py', '/api/module-client/off/talk/.adapter.js',
                     '/api/module-client/off/talk/adapter.js%00', '/api/module-client/off%2ftalk/adapter.js',
                     '/api/module-client/off/talk/adapter%ff.js', '/api/module-client/ghost/talk/adapter.js',
                     '/api/module-client/' + 'a' * 60 + '/talk/adapter.js'):
            self.assertEqual(self.get(path)[0], 404, path)
        self.assertEqual(self.get(ok + '?v=1')[0], 200, 'query адресу не міняє')
        # не `comments` і не оголошений файл — теж 404: ролі й список `client` беруться з знімка, а не з вигадки URL
        self.own('pubonly', roles=('publish',))
        self.grant('pubonly')
        self.assertEqual(self.get('/api/module-client/off/pubonly/adapter.js')[0], 404)
        self.assertTrue(os.path.isdir(d))

    def test_publish_share_sees_an_own_url_module(self):
        d = self.own('vpub', roles=('publish',))
        with open(os.path.join(d, 'module.json'), encoding='utf-8') as fh:
            man = json.load(fh)
        man['publish_target'] = 'url'
        man['settings'].append({'key': 'password', 'type': 'secret', 'label': 'Password'})
        _write(os.path.join(d, 'module.json'), json.dumps(man))
        self.grant('vpub')
        self.post('/api/module-enable', {'id': 'vpub', 'replace': True, 'secrets': {'password': 'pw'}})
        spaces.set_request_space('off')
        self.addCleanup(spaces.clear_request_space)
        out = serve.task_publish_share(self.off, {})
        self.assertIs(out.get('publish_gate'), True, out)

    def test_the_trust_routes_are_registry_routes(self):
        """Як решта маршрутів модулів: простір — параметр `space`, заголовок задачі не діє, префікс `/t/<id>/` — 400."""
        self.own()
        self.grant()
        for r in ('/api/module-trust', '/api/module-untrust'):
            self.assertIn(r, serve.Handler._REGISTRY_ROUTES)
        ghost = {'X-Canvas-Task': 'ghost'}
        st, body = self.get('/api/module-trust?space=off&id=acme', ghost)
        self.assertEqual((st, body['ok']), (200, True), body)
        st, body = self.post('/api/module-untrust', {'space': 'off', 'id': 'acme'}, ghost)
        self.assertEqual((st, body['ok']), (200, True), body)
        for st, body in (self.get('/t/tx/api/module-trust?space=off&id=acme'),
                         self.post('/t/tx/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': '0' * 64}, self.browser),
                         self.post('/t/tx/api/module-untrust', {'space': 'off', 'id': 'acme'})):
            self.assertEqual(st, 400)
            self.assertIn('реєстр задач не привʼязаний', body['error'])
        self.assertEqual(mt.load_records(), {}, 'відмова префікса нічого не змінила')

    def test_the_trust_reads_carry_no_cors_header(self):
        self.own()
        for path in ('/api/module-trust?space=off&id=acme', '/api/module-trust?space=ghost&id=acme',
                     '/api/modules?space=off'):
            st, headers = self.headers_of('GET', path)
            self.assertIn(st, (200, 404))
            self.assertNotIn('access-control-allow-origin', headers, path)

    def test_trust_route_failures_use_the_one_error_shape(self):
        self.own()
        st, body = self.get('/api/module-trust?space=ghost&id=acme')
        self.refused(st, body, 404, 'unknown-space')
        st, body = self.get('/api/module-trust?space=off&id=nope')
        self.refused(st, body, 404, 'unknown-module')
        st, body = self.get('/api/module-trust?space=off')
        self.refused(st, body, 404, 'unknown-module')
        st, body = self.post('/api/module-trust', {'space': 'ghost', 'id': 'acme', 'hash': '0' * 64}, self.browser)
        self.refused(st, body, 404, 'unknown-space')
        st, body = self.post('/api/module-untrust', {'space': 'ghost', 'id': 'acme'})
        self.refused(st, body, 404, 'unknown-space')
        for bad in (None, 5, ['acme'], '../acme', 'ACME'):
            st, body = self.post('/api/module-untrust', {'space': 'off', 'id': bad})
            self.refused(st, body, 404, 'unknown-module')
        st, body = self.post('/api/module-untrust', {'space': 'off', 'id': 'ghost'})
        self.assertEqual((st, body), (200, {'ok': True, 'module': None}))            # коректний id без запису — не помилка
        for bad in (None, 5, [], {}, 'zz', 'a' * 63):
            st, body = self.post('/api/module-trust', {'space': 'off', 'id': 'acme', 'hash': bad}, self.browser)
            self.refused(st, body, 400, 'bad-settings')

    def test_comment_config_and_page_name_the_own_adapter_with_the_space(self):
        """Обидва місця, де сервер називає адреси адаптера (`/api/comment-config` для «Огляду» і `/commented` для рамки),
        дають СВОЄМУ модулю адресу з простором — інакше сторінка просила б `/api/module-client//talk/adapter.js`."""
        self.own('talk', roles=('comments',), client=['adapter.js'])
        self.grant('talk')
        st, body = self.post('/api/module-enable', {'id': 'talk', 'replace': True})
        self.assertEqual((st, body['check']['ok']), (200, True), body)
        d = os.path.join(self.off['path'], 'tx')
        _write(os.path.join(d, 'iterations.json'), json.dumps(
            {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'start', 'published': False}],
             'publish_url': None}))
        _write(os.path.join(d, 'iterations', 'it1', 'index.html'), '<!DOCTYPE html><html><head></head><body>x</body></html>')
        url = '/api/module-client/off/talk/adapter.js'
        st, body = self.get('/api/comment-config?ch=project&it=it1')
        self.assertEqual((st, body.get('client')), (200, [url]), body)
        st, html = self.get('/commented?it=it1&ch=project')
        self.assertEqual(st, 200, html[:300])
        self.assertIn(url, html)
        self.assertNotIn('/api/module-client//', html)
        self.assertEqual(self.get(url)[0], 200, 'адреса, яку називає сервер, відчиняється')

    def test_a_cold_adapter_request_loads_the_module_in_its_own_space(self):
        """`module-client` стоїть ДО `_take_task`: простору запиту нема, але холодне завантаження довіреного знімка
        виконує верхній рівень `server.py` саме в просторі модуля (мітка — що той побачив)."""
        mark = os.path.join(self.tmp, 'seen-space.log')
        server = SERVER + ('\nimport spaces\nwith open(%r, "a") as _f:\n'
                           '    _f.write(str(spaces.request_space_id()) + "\\n")\n' % mark)
        self.own('talk', roles=('comments',), client=['adapter.js'], server=server)
        self.grant('talk')
        dm.reset_caches()
        if os.path.exists(mark):
            os.remove(mark)
        self.assertEqual(self.get('/api/module-client/off/talk/adapter.js'), (200, '/* adapter.js v1 */'))
        with open(mark, encoding='utf-8') as fh:
            self.assertEqual(fh.read().split(), ['off'], 'завантажено рівно раз і в просторі модуля')

    def test_seam_warning(self):
        line = serve.trust_seam_warning()
        self.assertIn('DEAI_TRUST_CONFIRM=yes', line or '')
        os.environ[mt.SEAM_ENV] = 'no'
        self.assertIn('DEAI_TRUST_CONFIRM=no', serve.trust_seam_warning() or '')
        os.environ[mt.SEAM_ENV] = 'maybe'                   # не значення шва: нічого не діє — і попередження нема
        self.assertIsNone(serve.trust_seam_warning())
        os.environ.pop(mt.SEAM_ENV)
        self.assertIsNone(serve.trust_seam_warning())


if __name__ == '__main__':
    unittest.main()
