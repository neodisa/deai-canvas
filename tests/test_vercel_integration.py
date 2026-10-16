"""Справжній модуль `vercel-publish` + справжній диспетчер ядра: `POST /api/publish` → `iterations.json` → `/api/task`.

Окремо модуль (`test_vercel_publish.py`: проти підставного API) і диспетчер (`test_publish_module.py`: проти
фікстурного модуля) перевірені, а ЇХНІЙ СТИК — ні: що модуль повертає, що ядро записує, що `/api/task` з цього бачить.
Тут усе справжнє: сервер канваса в процесі (`DispatchWorld`), модуль із `app/modules`, його `ctx` від ядра (клас
`ModuleError`, секрети з `secrets.json`), `build_preview` з гейтом, запис `publish_remote`. Підставне лише те, чого
в тесті бути не може, — `api.vercel.com` і сайт превʼю (`FakeVercel`, `FakeSite` з `test_vercel_publish.py`: два
сервери на `127.0.0.1:0`).

⛔ Жодного реального запиту. Дві розтяжки: ядровий `Tripwire` (`test_publish_module.py`: мережа, підпроцеси, loopback
лише на порти цього тесту) і `Tripwire` Vercel-тестів (`getaddrinfo`/`connect`: усе, крім `127.0.0.1`). `tearDown` падає,
навіть якщо модуль проковтнув відмову. Справжні `~/.deai`, `~/deai-published` і `tasks.json` стережуть охоронці
`test_publish_module.py` (`setUpModule`/`tearDownModule`).

Токен ніде, крім `secrets.json` (і заголовка `Authorization` до підставного API): жодна відповідь канваса, жоден файл під
тимчасовою домівкою; охоронець «токен ніде» сам доводиться (`test_the_token_guard_can_fail`).
"""
import json
import os
import sys
import unittest
import urllib.parse
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402
import serve  # noqa: E402
import spaces_guard  # noqa: E402
import test_publish_module as tpm  # noqa: E402  — світ диспетчера (`DispatchWorld`) і його охоронці
import test_vercel_publish as tvp  # noqa: E402  — підставні `api.vercel.com` і сайт превʼю

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()
    tpm.setUpModule()                  # і ті самі охоронці, що в тестах диспетчера: справжні `~/deai-published`, `tasks.json`


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)
    tpm.tearDownModule()

MID = 'vercel-publish'
TOKEN = 'vcp_INTEGRATION-token-0a1b2c3d4e5f'
PW1 = 'gate-pass-9876'
PW2 = 'another-pass-1'
PROJECT_RE = r'^pv-\d{8}$'


class CoreIntegration(tpm.DispatchWorld):
    """Простір `off` (поточний, задача `tx`, без інтеграцій): `static-publish` вимкнено, `vercel-publish` увімкнено."""

    def setUp(self):
        super().setUp()
        # Ізоляція від справжнього `~/.deai` — у `DispatchWorld.setUp`; тут вона ще й названа явно (охоронець `test_serve.py`
        # шукає присвоєння `DEAI_HOME` у КОЖНОМУ файлі, що пише простори) і перевіряється: домівка — під тимчасовою текою.
        env = mock.patch.dict(os.environ, {'DEAI_HOME': self.deai})
        env.start()
        self.addCleanup(env.stop)
        self.assertTrue(os.path.realpath(os.environ['DEAI_HOME']).startswith(os.path.realpath(self.tmp)))
        dm.write_module_state(self.off, 'static-publish', enabled=False)
        dm.write_module_state(self.off, MID, enabled=True)
        dm.write_secrets('off', MID, {'token': TOKEN})
        dm.reset_caches()
        self.module = dm.catalog()[MID]
        self.assertEqual((self.module.status, self.module.error), ('ok', None))
        self.vapi = tvp.FakeVercel(token=TOKEN)
        self.addCleanup(self.vapi.stop)
        self.site = tvp.FakeSite()
        self.addCleanup(self.site.stop)
        self.trip.allow_ports.update({self.vapi.port, self.site.port})          # ядровий `Tripwire`: лише ці два порти
        self.vtrip = tvp.Tripwire()                                              # і розтяжка Vercel-тестів: лише 127.0.0.1
        self.vtrip.start()
        self.addCleanup(self.vtrip.stop)
        proxies = mock.patch('urllib.request.getproxies', return_value={})
        proxies.start()
        self.addCleanup(proxies.stop)
        g = self.module.fn('publish').__globals__
        real_fetch = g['_fetch_preview']
        self.preview_urls = []

        def mapped(url, *a, **k):                                                # шов перевірки превʼю: https-адреса → підставний сайт
            self.preview_urls.append(url)
            return real_fetch(f'http://127.0.0.1:{self.site.port}{urllib.parse.urlsplit(url).path or "/"}', *a, **k)
        over = mock.patch.dict(g, {'API_BASE': self.vapi.base, 'POLL_S': 0.001, 'POLL_MAX_S': 10, 'ALIAS_MAX_S': 1,
                                   'VERIFY_RETRY_S': 0.001, '_fetch_preview': mapped, 'time': tvp._TimeGuard()})
        over.start()
        self.addCleanup(over.stop)
        self.responses = []                                                      # КОЖНА відповідь канваса, текстом

    def tearDown(self):
        # `unittest` кличе `tearDown` ДО cleanup-ів: розтяжки ще стоять
        self.assertEqual(self.vtrip.violations, [], 'модуль спробував вийти за межі 127.0.0.1')
        self.assertEqual(self.token_leaks(), [])
        self.assert_quiet()
        super().tearDown()

    # ---- помічники
    def call(self, method, path, payload=None):
        st, body = self._call(method, path, payload)
        self.responses.append(json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body)
        return st, body

    def publish(self):
        return self.call('POST', '/api/publish', {})

    def task(self):
        st, body = self.call('GET', '/api/task')
        self.assertEqual(st, 200, body)
        return body

    def gate(self):
        t = self.task()
        return {k: t[k] for k in ('publish_gate', 'publish_gate_stale', 'publish_share_url') if k in t}

    def set_password(self, value):
        dm.write_secrets('off', MID, {'password': value})                       # None — прибрати

    def token_leaks(self):
        """Де токен лишився: у відповідях канваса й у файлах під тимчасовою домівкою, КРІМ `secrets.json`."""
        leaks = [('response', i) for i, text in enumerate(self.responses) if TOKEN in text]
        for root, _dirs, files in os.walk(self.tmp):
            for name in files:
                if name == 'secrets.json':
                    continue
                path = os.path.join(root, name)
                try:
                    with open(path, 'rb') as f:
                        if TOKEN.encode() in f.read():
                            leaks.append(('file', os.path.relpath(path, self.tmp)))
                except OSError:
                    pass
        return leaks

    def uploaded(self):
        return [r['body'] for r in self.vapi.reqs('POST', '/v2/files')]

    def deployment_bodies(self):
        return self.vapi.bodies('/v13/deployments')

    # ---- перша публікація й повторна
    def test_the_first_publish_records_the_state_and_the_second_one_reuses_the_project(self):
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual((body['url'], body['verified']), (tvp.SITE_URL, True))
        self.assertNotIn('warnings', body)                                        # ядро віддає `warnings` лише непорожні
        self.assertEqual(self.preview_urls, [tvp.SITE_URL])
        meta = self.meta()
        self.assertEqual((meta['publish_url'], meta['publish_verified']), (tvp.SITE_URL, True))
        remote = meta['publish_remote']
        self.assertEqual((remote['module'], remote['url'], remote['gated']), (MID, tvp.SITE_URL, False))
        state = remote['state']
        self.assertEqual(set(state), {'project', 'project_id', 'deployment', 'task'})
        self.assertRegex(state['project'], PROJECT_RE)
        self.assertEqual((state['project_id'], state['deployment'], state['task']), ('prj_mine', 'dpl_cur', 'tx'))
        (first,) = self.deployment_bodies()
        self.assertEqual((first['name'], first['project'], first['target']), (state['project'], state['project'], 'production'))
        self.assertEqual(len(self.vapi.projects), 1)

        # друга публікація: те саме `state` іде в модуль, проєкт знаходиться за id і лишається ОДИН; старі публікації прибрано
        self.vapi.requests.clear()
        self.vapi.dep_id = 'dpl_two'
        self.vapi.listing = tvp.entries(6, current='dpl_two', name=state['project'])
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertEqual(self.vapi.reqs('GET', '/v9/projects')[0]['path'], '/v9/projects/prj_mine')
        (second,) = self.deployment_bodies()
        self.assertEqual(second['name'], state['project'])
        self.assertEqual(len(self.vapi.projects), 1, 'друга публікація створила ще один проєкт')
        self.assertEqual(sorted(r['path'].rsplit('/', 1)[1] for r in self.vapi.reqs('DELETE')), ['o3', 'o4', 'o5'])
        self.assertEqual(self.vapi.reqs('DELETE', '/v9/projects/'), [])           # проєкт ніколи не видаляється
        state2 = self.meta()['publish_remote']['state']
        self.assertEqual(state2, {'project': state['project'], 'project_id': 'prj_mine', 'deployment': 'dpl_two', 'task': 'tx'})
        self.assertEqual(self.task()['publish_url'], tvp.SITE_URL)

    # ---- /api/task: гейт, застаріння, посилання для колег
    def test_the_gate_table_through_api_task(self):
        """Таблиця ревʼюера: без пароля → пароль ЗАДАЛИ після публікації → публікація з паролем → пароль ЗМІНИЛИ → ЗНЯЛИ."""
        url = tvp.SITE_URL
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.gate(), {'publish_gate': False, 'publish_share_url': url},
                         'без пароля: превʼю публічне, посилання — сама адреса')
        self.assertFalse(any(b'authgate' in body for body in self.uploaded()), 'без пароля гейта в сторінках нема')

        self.set_password(PW1)                                                    # пароль задали ПІСЛЯ публікації
        self.assertEqual(self.gate(), {'publish_gate': False, 'publish_gate_stale': True, 'publish_share_url': url},
                         'опубліковане лишилось публічним, а пароль уже є: застереження «публічне» + «перепублікуйте», без #k=')

        self.vapi.requests.clear()
        self.vapi.dep_id = 'dpl_gated'
        self.assertEqual(self.publish()[0], 200)                                  # публікація з паролем
        self.assertTrue(any(b'authgate' in body for body in self.uploaded()), 'гейт у сторінках, які пішли на Vercel')
        remote = self.meta()['publish_remote']
        self.assertEqual((remote['gated'], remote['gate_hash']), (True, serve._gate_hash(PW1)))
        self.assertNotIn(PW1, json.dumps(remote), 'пароль у мета не пишеться, лише відбиток')
        self.assertEqual(self.gate(), {'publish_gate': True, 'publish_share_url': f'{url}#k={urllib.parse.quote(PW1, safe="")}'},
                         'з паролем і без змін: посилання для колег із #k=')

        self.set_password(PW2)                                                    # пароль ЗМІНИЛИ
        self.assertEqual(self.gate(), {'publish_gate': True, 'publish_gate_stale': True, 'publish_share_url': url},
                         'опубліковане зі старим паролем: застаріло, посилання без #k= (новий пароль до нього не підходить)')

        self.set_password(None)                                                   # пароль ЗНЯЛИ
        self.assertEqual(self.gate(), {'publish_gate': True, 'publish_gate_stale': True, 'publish_share_url': url},
                         'опубліковане з паролем, а пароля вже нема: застаріло')
        self.assertEqual(len(self.vapi.projects), 1)
        self.assertEqual(self.token_leaks(), [])

    def test_republishing_after_the_password_change_makes_the_share_link_current(self):
        self.assertEqual(self.publish()[0], 200)
        self.set_password(PW1)
        self.assertEqual(self.publish()[0], 200)
        self.set_password(PW2)
        self.assertTrue(self.gate().get('publish_gate_stale'))
        self.assertEqual(self.publish()[0], 200)
        self.assertEqual(self.gate(), {'publish_gate': True, 'publish_share_url': f'{tvp.SITE_URL}#k={PW2}'})

    # ---- збій першої публікації
    def test_a_failed_first_publish_is_a_clean_module_error_and_records_nothing(self):
        self.vapi.states = ['BUILDING', 'ERROR']
        self.vapi.error_message = f'Build failed: saw {TOKEN} in the log'          # Vercel повторив би токен у тексті
        st, body = self.publish()
        self.assertEqual((st, body.get('ok'), body.get('code')), (502, False, 'module-error'), body)
        text = body['error']
        self.assertLessEqual(len(text), 300)
        self.assertNotIn(TOKEN, text)
        for cls in ('RuntimeError', '_HttpError', '_NetworkError', 'ModuleError'):
            self.assertNotIn(cls, text)                                           # без імені класу в діалозі
        self.assertTrue(text.startswith('Vercel: Build failed: saw'), text)
        self.assertRegex(text, r'[^\s.]\. Створений проєкт pv-\d{8} видалено\.$')   # крапка перед приміткою
        self.assertEqual(self.vapi.projects, {}, 'створений цим викликом проєкт мав бути видалений')
        meta = self.meta()
        self.assertNotIn('publish_remote', meta)
        self.assertIsNone(meta['publish_url'])
        self.assertEqual(self.gate(), {'publish_gate': False})
        self.assertEqual(self.site.requests, [])

    def test_a_rejected_token_is_vercel_auth_409_through_the_core(self):
        self.vapi.token = 'vcp_some-other-token'                                  # підставний API токен не приймає
        st, body = self.publish()
        self.assertEqual((st, body.get('code')), (409, 'vercel-auth'), body)
        self.assertIn('Vercel не прийняв токен', body['error'])
        self.assertNotIn('publish_remote', self.meta())
        self.assertEqual(self.vapi.reqs('POST'), [])

    # ---- підроблений стан
    def test_a_forged_publish_remote_state_never_reaches_a_foreign_project_through_the_core(self):
        """`iterations.json` склонували чи підробили: чужий `project_id`, «доказова» публікація чужого проєкту, `task` цієї
        задачі. Модуль не деплоїть у чужий проєкт і не видаляє там нічого — і так само через справжній диспетчер."""
        victim = 'acme-production-site'
        self.vapi.projects.clear()
        self.vapi.projects[victim] = 'prj_victim'
        self.vapi.known_deployments['dpl_victim_old'] = 'prj_victim'
        self.vapi.listing = tvp.entries(8, pid='prj_victim', name=victim)
        self.vapi.project_id = 'prj_new'
        self.seed_meta(publish_url=tvp.SITE_URL, publish_remote={
            'module': MID, 'url': tvp.SITE_URL, 'gated': False, 'published_at': '2026-10-16T10:00:00Z',
            'state': {'project': 'pv-12345678', 'project_id': 'prj_victim', 'deployment': 'dpl_victim_old', 'task': 'tx'}})
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        (dep,) = self.deployment_bodies()
        self.assertRegex(dep['name'], PROJECT_RE)
        self.assertEqual(self.vapi.projects[victim], 'prj_victim')
        self.assertEqual(self.vapi.projects[dep['name']], 'prj_new')
        self.assertEqual(self.vapi.reqs('DELETE'), [], 'жодного DELETE: ні публікацій, ні проєктів')
        self.assertEqual(self.vapi.reqs('GET', '/v13/deployments/dpl_victim_old'), [])
        for r in self.vapi.reqs('POST'):
            self.assertNotIn(victim.encode(), tvp.Base.blob(r))
            self.assertNotIn(b'prj_victim', tvp.Base.blob(r))
        self.assertTrue(any('не збігається' in w for w in body.get('warnings', [])), body)
        remote = self.meta()['publish_remote']
        self.assertEqual((remote['state']['project'], remote['state']['project_id']), (dep['name'], 'prj_new'))

    def seed_meta(self, **fields):
        path = os.path.join(self.tx_dir, 'iterations.json')
        meta = self.meta()
        meta.update(fields)
        tpm._write_json(path, meta)

    # ---- самотній сурогат у тексті Vercel
    def test_a_lone_surrogate_in_a_vercel_text_does_not_make_the_core_refuse_a_successful_publish(self):
        self.vapi.alias_error = {'message': 'alias \ud800 failed'}                 # `\ud800` у JSON відповіді
        st, body = self.publish()
        self.assertEqual(st, 200, body)
        self.assertTrue(body['warnings'])
        for w in body['warnings']:
            w.encode('utf-8')                                                     # лягає в UTF-8 (інакше `iterations.json` зламався б)
        self.assertTrue(any('alias ? failed' in w for w in body['warnings']), body['warnings'])
        self.assertEqual(self.meta()['publish_remote']['state']['task'], 'tx')

    # ---- токен
    def test_the_token_is_nowhere_but_secrets_json(self):
        self.assertEqual(self.publish()[0], 200)
        self.set_password(PW1)
        self.assertEqual(self.publish()[0], 200)
        self.task()
        self.call('GET', '/api/modules')
        self.vapi.states = ['ERROR']
        self.vapi.error_message = f'echo {TOKEN}'
        self.vapi.dep_id = 'dpl_bad'
        self.publish()
        self.call('POST', '/api/module-check', {'id': MID})
        self.assertGreater(len(self.responses), 5)
        self.assertEqual(self.token_leaks(), [])
        for r in self.vapi.requests:
            self.assertEqual(r['headers'].get('authorization'), 'Bearer ' + TOKEN)
            self.assertNotIn(TOKEN.encode(), tvp.Base.blob(r, skip_auth=True), (r['method'], r['path']))
        with open(os.path.join(self.deai, 'secrets.json'), encoding='utf-8') as f:
            self.assertIn(TOKEN, f.read(), 'секрет має лежати саме тут — інакше перевірка нічого не доводить')

    def test_the_token_guard_can_fail(self):
        """Охоронець, який не може впасти, нічого не вартий: підкинутий токен він бачить і у відповіді, і у файлі."""
        self.assertEqual(self.token_leaks(), [])
        self.responses.append('{"error": "oops %s"}' % TOKEN)
        planted = os.path.join(self.tmp, 'planted.txt')
        with open(planted, 'w', encoding='utf-8') as f:
            f.write('x ' + TOKEN)
        self.assertEqual(sorted(k for k, _ in self.token_leaks()), ['file', 'response'])
        os.remove(planted)
        self.responses.clear()
        self.assertEqual(self.token_leaks(), [])


if __name__ == '__main__':
    unittest.main()
