"""Коментарі простору ЛІГА через модуль `supabase-comments` (етап 4b-2). Тут — тести ядра.

Task 3: адреса й ключ Supabase більше не зашиті в `serve.py`. 4d-4b: і з конфігу УСТАНОВКИ (корінь старого `tasks.json`, оточення) рантайм їх не
бере — ЛІГА веде коментарі, «Команду» й сповіщення ЯВНИМИ записами (`liga_fixture`), а читач оригіналів лишився лише в міграції.

⛔ Ізоляція: `DC_TASKS_FILE`/`DC_NO_OVERVIEW` прибираються лише там, де це ПОТРІБНО для перевірки (вони самі глушать
мережу `_team_fetch`/`notify_call`); справжній `tasks.json` недосяжний — старий файл підставлено тимчасовий через
`spaces.legacy_tasks_file`, а `urlopen` підмінено: або записувачем, або тим, що падає. Адреси й ключі — вигадані.
"""
import contextlib
import json
import os
import re
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
import liga_fixture  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import sbconf  # noqa: E402
import spaces_guard  # noqa: E402
import state  # noqa: E402
import test_comments_role as tcr  # noqa: E402  — `PagesEnv`: справжній сервер у процесі й два простори

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


def _text(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


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

    def league(self, role, url=URL, key=KEY, **override):
        """`(space, prov)` ролі `role` простору ЛІГА з ЯВНИМ записом (4d-4b: оригіналів кореня й `Implicit` нема; було
        `implicit.for_role(role)` + корінь `tasks.json`): адреса й ключ — вигадані. Простір закріплено простором запиту; `override` — частини
        запису (`enabled`, `settings`, `secrets`). ⛔ Викликати ДО `sbconf.patch_*_open`: фікстура скидає кеші модулів."""
        settings = {'url': url} if role != 'tracker' else {}
        secrets = {'key': key} if role != 'tracker' else {}
        fx = liga_fixture.LigaFixture(self, tmp=self.tmp.name).env().build(
            roles=(role,), overrides={role: dict({'settings': settings, 'secrets': secrets}, **override)})
        fx.fix_space()
        space = {'id': 'legacy', 'path': fx.space_dir, 'legacy': True, 'integrations': True}
        return space, deai_modules.provider(role, space)


class SupabaseConfigTest(_Env):
    """Читач оригіналів Supabase ЛІГИ — конфіг УСТАНОВКИ, а не константи коду: корінь старого `tasks.json`, далі оточення. З 4d-4b рантайм його
    не має (`serve.supabase_config` видалено), а копія живе в міграції (`liga_migrate._supabase_from`) — ті самі кейси тепер проти неї
    (`self.cfg()` читає старий файл; зламаний чи відсутній — порожній корінь, без винятку)."""

    def cfg(self):
        import install_config
        import liga_migrate
        try:
            root = install_config.load_legacy_tasks()
        except (OSError, ValueError, RecursionError):
            root = {}
        return liga_migrate._supabase_from(root)

    def test_reads_root_of_legacy_tasks_and_trims_slash(self):
        self.write({'supabase_url': URL + '/', 'supabase_key': KEY})
        self.assertEqual(self.cfg(), (URL, KEY))

    def test_falls_back_to_environment(self):
        self.write({'tasks': {}})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(self.cfg(), (ENV_URL, ENV_KEY))

    def test_file_wins_over_environment(self):
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(self.cfg(), (URL, KEY))

    def test_pair_comes_whole_from_one_source(self):
        # Адреса з файла й ключ з оточення не змішуються: або ціла пара з файла, або ціла з оточення.
        self.write({'supabase_url': URL})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(self.cfg(), (ENV_URL, ENV_KEY))
        # …а коли й оточення неповне — нічого.
        del os.environ['SUPABASE_URL']
        self.assertEqual(self.cfg(), (None, None))
        os.environ['SUPABASE_URL'] = ENV_URL
        del os.environ['SUPABASE_KEY']
        self.assertEqual(self.cfg(), (None, None))

    def test_only_https_and_non_blank_strings(self):
        for url, key in (('http://demo.supabase.co', KEY), ('', KEY), (5, KEY), (None, KEY),
                         (URL, '   '), (URL, ''), (URL, 5), (URL, None), ('demo.supabase.co', KEY),
                         ('https://', KEY), ('https://   ', KEY), ('https:///', KEY),
                         ('https://  /', KEY)):
            with self.subTest(url=url, key=key):
                self.write({'supabase_url': url, 'supabase_key': key})
                self.assertEqual(self.cfg(), (None, None))

    def test_documentation_placeholders_are_not_a_config(self):
        # `cp tasks.example.json tasks.json`-подібна заготовка з документації: `<ref>` — не хост, `…` — не ключ
        for url, key in (('https://<ref>.supabase.co', KEY), (URL, 'sb_publishable_…'),
                         ('https://demo.supabase.co/path', KEY), ('https://demo.supabase.co:abc', KEY),
                         ('https://demo supabase.co', KEY), ('https://user@demo.supabase.co', KEY)):
            with self.subTest(url=url, key=key):
                self.write({'supabase_url': url, 'supabase_key': key})
                self.assertEqual(self.cfg(), (None, None))

    def test_key_with_a_space_is_not_a_config(self):
        self.write({'supabase_url': URL, 'supabase_key': 'sb_publishable_ab cd'})
        self.assertEqual(self.cfg(), (None, None))

    def test_port_is_allowed(self):
        self.write({'supabase_url': 'https://demo.supabase.co:8443/', 'supabase_key': KEY})
        self.assertEqual(self.cfg(), ('https://demo.supabase.co:8443', KEY))

    def test_bad_file_pair_falls_to_a_good_environment_pair(self):
        self.write({'supabase_url': 'https://<ref>.supabase.co', 'supabase_key': KEY})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(self.cfg(), (ENV_URL, ENV_KEY))

    def test_http_in_file_does_not_fall_through_to_mixed_pair(self):
        # Негодна пара з файла відкидається ЦІЛКОМ; оточення береться теж лише цілим.
        self.write({'supabase_url': 'http://demo.supabase.co', 'supabase_key': KEY})
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(self.cfg(), (ENV_URL, ENV_KEY))

    def test_unreadable_file_means_environment_or_nothing(self):
        # нема файла
        self.assertEqual(self.cfg(), (None, None))
        os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
        self.assertEqual(self.cfg(), (ENV_URL, ENV_KEY))
        # не JSON і не обʼєкт
        for raw in ('{oops', '[]', '"x"', '5', 'null'):
            with self.subTest(raw=raw):
                self.write(None, raw=raw)
                self.assertEqual(self.cfg(), (ENV_URL, ENV_KEY))
        del os.environ['SUPABASE_KEY']
        self.write(None, raw='{oops')
        self.assertEqual(self.cfg(), (None, None))

    def test_deeply_nested_file_is_no_config_not_a_crash(self):
        # `json.load` на надто глибокій вкладеності кидає `RecursionError` (не `ValueError`): це «конфігу нема», а не обвал.
        for raw in ('[' * 100000, '{"a":' * 100000):
            with self.subTest(raw=raw[:6]):
                self.write(None, raw=raw)
                self.assertEqual(self.cfg(), (None, None))
                os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'] = ENV_URL, ENV_KEY
                self.assertEqual(self.cfg(), (ENV_URL, ENV_KEY))
                del os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY']

    def test_no_constants_left_in_serve(self):
        self.assertFalse(hasattr(serve, 'SUPABASE_URL'))
        self.assertFalse(hasattr(serve, 'SUPABASE_KEY'))

    def test_status_code_comments_unconfigured(self):
        self.assertEqual(deai_modules.STATUS['comments-unconfigured'], 409)


class TeamFetchTest(_Env):
    """`_team_fetch('legacy')`: без конфігу — чесне «не налаштовано» і жодної мережі; з конфігом — запит на адресу конфігу.
    4c-1: підпис `_team_fetch(space, prov)` і мережа ЛІГИ — шов `_open` вбудованого `supabase-dashboard` (не `urlopen`)."""

    def test_without_config_no_network(self):
        """4d-4b: «конфігу нема» — запис `supabase-dashboard` без адреси (корінь `tasks.json` запису не замінює); мережі нема, текст — модуля."""
        self.write({'supabase_url': URL, 'supabase_key': KEY})       # корінь з парою — БЕЗ запису це нічого не дає
        space, prov = self.league('dashboard', url='')
        rows, err = serve._team_fetch(space, prov)
        self.assertEqual((rows, err), ([], 'url: адресу проєкту Supabase не задано'))

    def test_with_config_requests_config_url(self):
        space, prov = self.league('dashboard')
        seen = []

        def fake(req, timeout=None):
            seen.append(req)
            return sbconf.Resp(b'[{"id": "p1", "name": "One", "secret_col": "x"}]')
        sbconf.patch_dashboard_open(self, fake)
        rows, err = serve._team_fetch(space, prov)
        self.assertIsNone(err)
        self.assertEqual([r['id'] for r in rows], ['p1'])
        self.assertEqual(rows[0]['name'], 'One')
        self.assertNotIn('secret_col', rows[0])
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].full_url.startswith(URL + '/rest/v1/overview_projects?'))
        self.assertEqual(seen[0].get_header('Apikey'), KEY)
        self.assertEqual(seen[0].get_header('Authorization'), 'Bearer ' + KEY)

    def test_isolation_still_wins_over_config(self):
        # ⛔ Закон ізоляції не змінився: `DC_TASKS_FILE` глушить мережу, навіть коли конфіг є.
        space, prov = self.league('dashboard')
        os.environ['DC_TASKS_FILE'] = self.legacy
        seen = []
        sbconf.patch_dashboard_open(self, lambda req, timeout=None: seen.append(req) or sbconf.Resp(b'[]'))
        rows, err = serve._team_fetch(space, prov)
        self.assertEqual(rows, [])
        self.assertIn('ізольованому', err)
        self.assertEqual(seen, [])


class NotifyCallBaselineTest(_Env):
    """`notify_call` ЛІГИ (4c-3: заміна `teams_rpc`): без конфігу — `notify-unconfigured` без мережі; з конфігом — той самий запит,
    що знято до зміни (0.9.0), але крізь шов `_open` вбудованого `supabase-teams`; ізоляція — `OSError` без мережі."""

    def open_seam(self):
        seen = []
        sbconf.patch_open(self, lambda req, timeout=None: seen.append(req) or sbconf.Resp(b'[]'), 'supabase-teams')
        return seen

    def test_without_config_is_unconfigured_without_network(self):
        """4d-4b: «конфігу нема» — запис `supabase-teams` без адреси (корінь запису не замінює); `notify-unconfigured`, мережі нема."""
        self.write({'supabase_url': URL, 'supabase_key': KEY})
        self.league('notify', url='')
        seen = self.open_seam()
        with self.assertRaises(deai_modules.ModuleError) as cm:
            serve.notify_call('mute_state')
        self.assertEqual(cm.exception.code, 'notify-unconfigured')
        self.assertEqual(seen, [])

    def test_with_config_matches_baseline(self):
        with open(BEFORE, encoding='utf-8') as f:
            base = json.load(f)['teams_rpc']
        self.league('notify')
        seen = self.open_seam()
        serve.notify_call('mute_state')
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
        self.league('notify')
        seen = self.open_seam()
        os.environ['DC_NO_OVERVIEW'] = '1'
        with self.assertRaises(OSError):
            serve.notify_call('mute_state')
        self.assertEqual(seen, [])


class LigaRoutesWithoutConfigTest(tcr.PagesEnv):
    """Справжній сервер, простір ЛІГА (інтеграції), де ЯВНОГО запису `supabase-comments` НЕМА (4d-4b: оригіналів кореня й оточення рантайм не
    читає, тож «конфігу нема» = «запису нема»; було — порожній корінь `tasks.json` і код `comments-unconfigured`).

    ⛔ Сторінка без запису НЕ стирається і НЕ несе порожніх адреси й ключа: вона лишається РОБОЧОЮ — локальний шар коментарів; вкладки
    «Команда» нема, а `comment-config` каже `integrations-off` (командних коментарів ніхто не веде) без жодних значень."""

    def setUp(self):
        super().setUp()
        self.liga = self.liga_space(roles=(), sid='liga', legacy=False)       # простір ЛІГА без жодного запису ролей
        self.write_task(self.liga)
        net = mock.patch.object(serve.urllib.request, 'urlopen', _boom)
        net.start()
        self.addCleanup(net.stop)
        self.use(self.liga)

    def test_comment_config_is_409_integrations_off_without_values(self):
        st, raw = self.fetch('/api/comment-config?ch=project&it=it1')
        body = json.loads(raw)
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'integrations-off'))
        for leaked in ('sbUrl', 'sbKey', 'https://'):
            self.assertNotIn(leaked, raw)

    def test_project_page_keeps_its_content_and_stays_local(self):
        """Заміна двох старих перевірок `InjectWithoutConfigTest` (сторінка живе без конфігу; порожня адреса в сніпеті):
        сторінка локальна, а порожніх `url: ''` і спільних адрес у розмітці нема взагалі."""
        html = self.page('project')
        self.assertIn('<h1>x</h1>', html)
        self.assertIn('local-adapter.js', html)
        self.assertNotIn('__deaiCommentsCfg', html)
        self.assertNotIn('audiences:', html)
        self.assertNotIn("url: ''", html)
        for shared in self.SHARED + (sbconf.SB_URL, sbconf.SB_KEY):
            self.assertNotIn(shared, html, shared)


class LegacyPagesTest(tcr.PagesEnv):
    """Сторінки ЛІГИ після 4b-2: `/commented?ch=project`, `/api/comment-config`, превʼю — через вбудований
    `supabase-comments` (`comments_route`). Диференційно проти знімка 0.9.0 (`before-4b2.json`): канал, версія, прапорці
    аудиторій/інспектора ті самі; змінюється лише ШЛЯХ (модуль замість зашитого Supabase). Задачі: `t1`
    (`comment_project: proj/alpha`, поточна) і `t2` (без нього, ітерація `it1` опублікована)."""

    def setUp(self):
        super().setUp()
        # Простори пишуться в тимчасовий `DEAI_HOME`, а не у справжній `~/.deai`: `Env.setUp` уже виставив його, тут він
        # підтверджений явно (так вимагає охоронець `test_serve.TestsCannotWriteLiveConfig`); оточення відновлює `Env.tearDown`.
        os.environ['DEAI_HOME'] = self.deai
        self.before = json.load(open(BEFORE, encoding='utf-8'))
        self.use(self.liga)
        sp = self.liga
        tasks = {}
        for tid, extra in (('t1', {'comment_project': 'proj/alpha'}), ('t2', {})):
            self.write_task(sp, tid)                    # теки й `iterations.json`; `tasks.json` перепишемо нижче
            tasks[tid] = {'title': tid, 'dir': os.path.join(sp['path'], tid), 'profile': 'tool', **extra}
        tcr._write(os.path.join(sp['path'], 'tasks.json'),
                   json.dumps({'design_work_root': sp['path'], 'current': 't1', 'tasks': tasks}))
        tcr._write(os.path.join(tasks['t2']['dir'], 'iterations.json'), json.dumps(
            {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'start', 'published': True}],
             'publish_url': None}))
        self.t2 = tasks['t2']

    @staticmethod
    def facts(html):
        """Ті самі «факти сторінки», що знімок `before-4b2.json` брав зі старого сніпета."""
        m = re.search(r'version: ("(?:[^"\\]|\\.)*")', html)
        return {'version': json.loads(m.group(1)),
                'audiences': 'audiences:' in html, 'inspector': '/inspector.js' in html}

    def decide(self, **kw):
        """`serve.publish_comments` для простору ЛІГА: простір ЗАКРІПЛЕНО простором запиту, як це робить обробник (без закріплення
        постачальника нема — 4d-4b: явний запис діє лише в закріпленому просторі)."""
        with spaces.request_space(self.liga['id']):
            return serve.publish_comments(self.liga, self.t2, 't2', **kw)

    def build(self, comments):
        task, its = self.t2, [{'id': 'it1', 'published': True}]
        return serve.build_preview(task, 't2', its, comments=comments, gate_pw='1100', build='legacy')

    # ---- /commented?ch=project ---------------------------------------------------------------------------------------

    def test_the_work_page_is_the_module_page_with_the_recorded_channel_and_flags(self):
        html = self.page('project')
        cfg = self.cfg_of(html)
        want = self.before['page_work']
        self.assertEqual(cfg['channel'], want['channel'])
        self.assertEqual((cfg['url'], cfg['key'], cfg['shotsBucket']), (sbconf.SB_URL, sbconf.SB_KEY, 'overview-thumbs'))
        f = self.facts(html)
        self.assertEqual((f['audiences'], f['inspector']), (want['audiences'], want['inspector']))
        self.assertEqual(f['version'], serve.pm.page_version_tag('it1', {'id': serve.pm.IMPLICIT_ID}))
        for src in ('/api/module-client/supabase-comments/supabase.min.js', '/api/module-client/supabase-comments/adapter.js'):
            self.assertEqual(html.count(f'src="{src}"'), 1, src)
        self.assertLess(html.index('supabase.min.js'), html.index('adapter.js'), 'бібліотека — ДО адаптера')
        for gone in ('cdn.jsdelivr.net/npm/@supabase', 'supabase-adapter.min.js', 'CommentLayerSupabase', 'sbUrl'):
            self.assertNotIn(gone, html, gone)

    def test_the_work_page_of_a_task_without_comment_project_uses_the_dc_channel(self):
        tcr._write(os.path.join(self.liga['path'], 'tasks.json'), json.dumps(
            {'design_work_root': self.liga['path'], 'current': 't2',
             'tasks': {'t2': {'title': 't2', 'dir': self.t2['dir'], 'profile': 'tool'}}}))
        self.assertEqual(self.cfg_of(self.page('project'))['channel'], self.before['channels']['t2'])

    def test_the_snippet_facts_are_the_recorded_ones_for_both_kinds_of_page(self):
        """Функція-проти-знімка: ті самі аргументи, що знімав `record_before.py` (`version`, `inspector`, `audiences`)."""
        def snippet(**kw):
            return serve.inject_module_comment_layer('<html><body></body></html>', '/app/vendor', [], {'channel': 'c'}, **kw)
        work = self.facts(snippet(version='1/main', inspector=True, audiences=True))
        pub = self.facts(snippet(version='2/kartka'))
        for got, key in ((work, 'page_work'), (pub, 'page_publish')):
            want = self.before[key]
            self.assertEqual(got, {'version': want['version'], 'audiences': want['audiences'],
                                   'inspector': want['inspector']}, key)

    # ---- превʼю -----------------------------------------------------------------------------------------------------

    def test_the_preview_carries_exactly_the_layer_and_the_module_adapter_files(self):
        comments, warn = self.decide()
        self.assertIsNone(warn)
        pub = self.build(comments)['dir']
        self.assertEqual(sorted(os.listdir(os.path.join(pub, 'comment-layer'))),
                         ['adapter.js', 'comment-layer.min.js', 'supabase.min.js'])
        html = _text(os.path.join(pub, 'it1', 'index.html'))
        cfg = self.cfg_of(html)
        self.assertEqual(cfg['channel'], self.before['page_publish']['channel'])
        self.assertEqual(cfg['shotsBucket'], 'overview-thumbs')
        f = self.facts(html)
        # 0.32.0: інспектора РОБОЧОГО МІСЦЯ в публікації як не було, так нема; але сторінка превʼю везе власний оверлей лише для
        # перегляду з відносним шляхом (`shell/vendor/`), тож `'/inspector.js' in html` істинне саме через нього
        self.assertEqual(f['audiences'], self.before['page_publish']['audiences'])
        self.assertNotIn('/app/vendor/inspector.js', html)
        self.assertEqual(html.count('src="../shell/vendor/inspector.js'), 1)
        self.assertEqual(f['version'], serve.pm.page_version_tag('it1', {'id': serve.pm.IMPLICIT_ID}))
        for name in ('supabase.min.js', 'adapter.js', 'comment-layer.min.js'):
            self.assertEqual(html.count(f'src="../comment-layer/{name}"'), 1, name)
        for gone in ('cdn.jsdelivr.net/npm/@supabase', 'supabase-adapter.min.js', 'CommentLayerSupabase', '/api/module-client/'):
            self.assertNotIn(gone, html, gone)
        man = json.loads(_text(os.path.join(pub, 'manifest.json')))
        self.assertEqual(man['build'], 'legacy')

    def test_publish_comments_for_the_league(self):
        comments, warn = self.decide()
        self.assertIsNone(warn)
        self.assertEqual((comments['module'].id, comments['channel']), ('supabase-comments', 'dc/t2'))
        self.assertEqual(set(comments['config']), {'url', 'key', 'shotsBucket'})
        self.assertEqual(self.decide(module_publish=True), (False, None))

    def test_publish_comments_without_a_record_is_none_and_the_build_carries_nothing(self):
        """Було: без конфігу кореня — `(False, 'comments-unconfigured')`. 4d-4b: «нема конфігу» = «нема запису» — постачальника ролі нема,
        превʼю без коментарів і без попередження (як і в будь-якому просторі, де коментарі не підключено)."""
        self.liga = self.liga_space(roles=(), sid='liga', legacy=False)
        self.assertEqual(self.decide(), (False, None))
        pub = self.build(False)['dir']
        self.assertFalse(os.path.exists(os.path.join(pub, 'comment-layer')))
        self.assertNotIn('CommentLayer', _text(os.path.join(pub, 'it1', 'index.html')))

    def _assert_publish_has_no_comment_layer(self):
        self.assertEqual(self.decide(), (False, None))
        pub = self.build(False)['dir']
        self.assertFalse(os.path.exists(os.path.join(pub, 'comment-layer')))
        self.assertNotIn('CommentLayer', _text(os.path.join(pub, 'it1', 'index.html')))

    def test_a_migrated_liga_whose_comments_record_is_disabled_publishes_without_the_layer(self):
        """r15-4: ЛІГА після міграції з ВИМКНЕНИМ записом `supabase-comments` (решта п'ять ролей живі) — превʼю без шару коментарів і без
        попередження: рішення за записом, а не за тим, що в пари Supabase була адреса."""
        self.assertIsNotNone(self.decide()[0], 'контроль: із увімкненим записом шар є')
        self.liga = self.liga_space(overrides={'comments': {'enabled': False}})
        self._assert_publish_has_no_comment_layer()

    def test_a_migrated_liga_whose_comments_record_is_removed_publishes_without_the_layer(self):
        """r15-4: те саме, коли запис `supabase-comments` ВИДАЛЕНО з `space.json` (решта п'ять ролей лишаються)."""
        self.assertIsNotNone(self.decide()[0], 'контроль: із записом шар є')
        self.liga = self.liga_space(roles=tuple(r for r in liga_fixture.ALL_ROLES if r != 'comments'))
        self._assert_publish_has_no_comment_layer()

    def test_build_preview_true_is_a_value_error_before_the_disk_is_touched(self):
        pub = os.path.join(self.t2['dir'], 'publish')
        os.makedirs(pub)
        keep = os.path.join(pub, 'keep.txt')
        tcr._write(keep, 'попередня збірка')
        with self.assertRaises(ValueError):
            self.build(True)
        self.assertEqual(os.listdir(pub), ['keep.txt'])
        self.assertEqual(_text(keep), 'попередня збірка')

    # ---- /api/comment-config ----------------------------------------------------------------------------------------

    def test_comment_config_is_the_module_shape(self):
        st, body = self.config('project')
        self.assertEqual(st, 200)
        self.assertEqual(set(body), {'ch', 'module', 'client', 'config', 'channel', 'version'})
        self.assertEqual((body['ch'], body['module']), ('project', 'supabase-comments'))
        self.assertEqual(body['client'], ['/api/module-client/supabase-comments/supabase.min.js',
                                          '/api/module-client/supabase-comments/adapter.js'])
        self.assertEqual(body['config'], {'url': sbconf.SB_URL, 'key': sbconf.SB_KEY, 'shotsBucket': 'overview-thumbs'})
        self.assertEqual(body['channel'], self.before['channels']['t1'])
        for gone in ('sbUrl', 'sbKey', 'project'):
            self.assertNotIn(gone, body)

    # ---- старий шлях зник -------------------------------------------------------------------------------------------

    def test_the_old_comment_path_is_gone(self):
        for name in ('COMMENT_SNIPPET', 'inject_comment_layer', 'INTERNAL_TINT'):
            self.assertFalse(hasattr(serve, name), name)
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'app', 'vendor', 'supabase-adapter.min.js')))
        self.assertTrue(os.path.isfile(os.path.join(_HERE, 'fixtures', 'legacy-comments', 'supabase-adapter.min.js')))
        with open(os.path.join(ROOT, 'app', 'index.html'), encoding='utf-8') as fh:
            self.assertNotIn('supabase-adapter', fh.read())


class OverviewSyncTest(_Env):
    """`Handler._overview_sync`: без конфігу установки фонового пуша нема (ні лога, ні `Popen`); з конфігом — дитина стартує з
    `--space <id>` і БЕЗ конфігу в оточенні (4c-1, Task 6: вона читає `install_config` сама; раніше пара їхала в `env`)."""

    def setUp(self):
        super().setUp()
        home = os.path.join(self.tmp.name, 'home')
        os.makedirs(os.path.join(home, '.claude', 'pipeline-feedback'))
        self.old_log = os.path.join(home, '.claude', 'pipeline-feedback', 'overview-sync.log')
        env = mock.patch.dict(os.environ, {'HOME': home})
        env.start()
        self.addCleanup(env.stop)
        out = mock.patch.object(serve, '_vcs_outbound_here', return_value=True)
        out.start()
        self.addCleanup(out.stop)
        # лог синку (4d-4c) — `<DEAI_HOME>/logs/dashboard-sync.log` тимчасового `DEAI_HOME`; і чистий стан «один синк на простір»
        self.log = serve._overview_log_path()
        patcher = mock.patch.dict(serve._SYNC_RUNS, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_without_a_dashboard_record_no_popen_and_no_log(self):
        """Було: «без конфігу установки» (порожній корінь). 4d-4b: рішення — запис ролі `dashboard` простору; у просторі ЛІГА без нього
        (є лише запис коментарів) постачальника нема — ні лога, ні `Popen`."""
        self.league('comments')
        with mock.patch.object(serve.subprocess, 'Popen') as popen:
            serve.Handler._overview_sync(None)
        popen.assert_not_called()
        self.assertFalse(os.path.exists(self.log))

    def test_with_a_dashboard_record_child_starts_for_the_league_and_gets_no_config(self):
        """Простір ЛІГА закріплено простором запиту (явний запис діє лише так): дитина стартує з `--space <id>` (ключ синку — той самий id), БЕЗ конфігу.
        Було: запит без закріплення брав запис реєстру з `legacy` чи `--legacy` — з 4d-4b провайдера без закріпленого простору нема, тож гілка
        недосяжна звідси (її лишає `_overview_target` для інструментів без обробника)."""
        self.league('dashboard')
        script = os.path.join(ROOT, 'bin', 'overview_push.py')
        with mock.patch.object(serve.subprocess, 'Popen') as popen:
            serve._SYNC_RUNS.clear()
            serve.Handler._overview_sync(None)
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], [sys.executable, script, 'sync', '--space', 'legacy'])
        self.assertNotIn('env', popen.call_args.kwargs, 'конфіг дитині не передається: вона читає install_config')
        self.assertTrue(os.path.exists(self.log), 'лог — `<DEAI_HOME>/logs/dashboard-sync.log`')
        self.assertFalse(os.path.exists(self.old_log), 'старий лог ЛІГИ в pipeline-feedback сервер не пише')

    def test_the_isolated_run_does_not_start_a_child_for_the_shared_league_record(self):
        """Закон ізоляції: `shared_state`-запис ЛІГИ + ізольований прогін (`DC_TASKS_FILE`) — синку нема (пишемо у спільний Supabase)."""
        self.league('dashboard')
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp.name, 'iso.json')}), \
                mock.patch.object(serve.subprocess, 'Popen') as popen:
            serve.Handler._overview_sync(None)
        popen.assert_not_called()


# Рядки Supabase, які віддає «сервер» у тестах агента (ті самі, що записані в `before-4b2.json` на 0.9.0).
ROWS = [
    {'id': 'c1', 'text': 'Збільшити відступ', 'status': 'open', 'author': 'A', 'ts': '30.10.2026 10:00',
     'meta': {'version': '1/main', 'shotUrl': 'https://demo.supabase.co/x.jpg'}, 'born_v': 1, 'fp': {'tag': 'div'},
     'html_snapshot': {'text': 'x'}, 'resolved_v': None, 'resolve_reason': None},
    {'id': 'c2', 'text': 'Готово', 'status': 'resolved', 'author': 'B', 'ts': '30.10.2026 11:00',
     'meta': None, 'born_v': 1, 'fp': None, 'html_snapshot': None, 'resolved_v': 2, 'resolve_reason': 'зроблено'},
]
#: Поля піна, які 0.9.0 віддавав агентові (`supabase_pins`): новий шлях (модуль + `agent_pins`) мусить мати всі.
PIN_FIELDS = ('id', 'text', 'status', 'author', 'ts', 'meta', 'born_v', 'fp', 'html_snapshot', 'resolved_v',
              'resolve_reason')


class LegacyAgentTest(_Env):
    """Task 4: агент (`ProjectComments`, `inbox`, `state`) веде командні коментарі ЛІГИ вбудованим `supabase-comments`.

    Конфіг — ЯВНИЙ запис `supabase-comments` простору ЛІГА (`self.league('comments')`, 4d-4b; було — фікстура старого `tasks.json`); мережа —
    лише шов `_open` модуля (`sbconf.patch_open`), `urlopen` — розтяжка (`_boom`). Усе порівнюється зі знімком 0.9.0 (`before-4b2.json`)."""

    TASK = {'comment_project': 'proj/alpha'}

    def setUp(self):
        super().setUp()
        with open(BEFORE, encoding='utf-8') as f:
            self.base = json.load(f)
        self.seen = []
        self.rows = ROWS
        self.space, self.prov = self.league('comments')          # ДО `patch_open`: фікстура скидає кеші модулів
        sbconf.patch_open(self, self.fake_open)

    def pc(self):
        return serve.ProjectComments(self.space)

    def no_record(self):
        """Простір ЛІГА без запису коментарів (є лише запис дашборда): ролі `comments` ніхто не веде. Заміна «без конфігу кореня»."""
        space, _ = self.league('dashboard')
        sbconf.patch_open(self, self.fake_open)
        return space

    def fake_open(self, req, timeout=None):
        self.seen.append({'method': req.get_method(), 'url': req.full_url, 'timeout': timeout,
                          'body': json.loads(req.data) if req.data else None,
                          'headers': {k.lower(): v for k, v in req.header_items()}})
        if req.get_method() == 'GET':
            return sbconf.Resp(json.dumps(self.rows).encode('utf-8'))
        return sbconf.Resp(json.dumps([{'id': re.search(r'[?&]id=eq\.([^&]+)', req.full_url).group(1)}]).encode('utf-8'))

    # --- ctx і маршрут ---
    def test_ctx_comes_from_the_league_record(self):
        """Було: `serve._comments_legacy_ctx()` читав конфіг УСТАНОВКИ (корінь `tasks.json`); з 4d-4b ctx дає `module_ctx` з ЗАПИСУ простору
        (адреса — налаштування, ключ — секрет); читача оригіналів нема."""
        self.assertFalse(hasattr(serve, '_comments_legacy_ctx'))
        _, ctx, _ = serve.comments_route(self.space, self.prov)
        self.assertEqual(ctx['settings']['url'], URL)
        self.assertEqual(ctx['secrets'], {'key': KEY})
        self.assertIs(ctx['ModuleError'], deai_modules.ModuleError)
        self.assertEqual((serve.COMMENTS_MODULE, serve.LEGACY_SHOTS_BUCKET), ('supabase-comments', 'overview-thumbs'))

    def test_route_for_the_league_is_the_builtin_module_with_the_league_channel(self):
        m, ctx, channel = serve.comments_route(self.space, self.prov)
        self.assertEqual((m.id, m.status, m.origin), ('supabase-comments', 'ok', 'builtin'))
        self.assertEqual(ctx['settings']['url'], URL)
        ch = self.base['channels']
        self.assertEqual(channel({'comment_project': 'proj/alpha'}, 't1'), ch['t1'])
        self.assertEqual(channel({'comment_project': 'proj/alpha'}, 't1', internal=True), ch['t1_internal'])
        self.assertEqual(channel({}, 't2'), ch['t2'])
        self.assertEqual(channel({}, 't2', internal=True), ch['t2_internal'])

    def test_route_refuses_without_a_loaded_builtin_module_or_a_provider(self):
        # Було: пропажа вбудованого модуля з каталогу (`catalog` → `{}`/збій) — каталог ЛІГА більше не опитує (постачальник уже вирішений);
        # лишився збій `module_ctx` (`secrets-unreadable`, `bad-settings`…) — маршрут не ковтає його й не показує ключа.
        with mock.patch.object(deai_modules, 'module_ctx', side_effect=deai_modules.ModuleError('module-error', message='comments: ctx')):
            with self.assertRaises(deai_modules.ModuleError) as cm:
                serve.comments_route(self.space, self.prov)
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertNotIn(KEY, str(cm.exception))
        for prov in (None, 'nope', 5):
            with self.subTest(prov=prov), self.assertRaises(deai_modules.ModuleError):
                serve.comments_route(None, prov)

    def test_route_for_a_space_module_uses_the_frame_ctx_and_the_space_channel(self):
        mod = deai_modules.catalog()['supabase-comments']
        space = {'id': 'sp1', 'path': self.tmp.name}
        with mock.patch.object(deai_modules, 'module_ctx', return_value={'frame': True}) as mctx:
            m, ctx, channel = serve.comments_route(space, mod)
        mctx.assert_called_once_with(space, mod)
        self.assertEqual((m, ctx), (mod, {'frame': True}))
        self.assertEqual(channel({'comment_project': 'proj/alpha'}, 't1'), 'deai/sp1/t1')     # канал простору, не ЛІГИ
        self.assertEqual(channel({}, 't1', internal=True), 'deai/sp1/t1/internal')

    # --- диференційні: 0.9.0 ↔ модуль ---
    def test_pins_match_the_recorded_0_9_0_pins_field_by_field(self):
        pins = self.pc().pins(self.TASK, 't1')
        self.assertEqual([p['id'] for p in pins], [p['id'] for p in self.base['pins']])
        for got, want in zip(pins, self.base['pins']):
            for field in PIN_FIELDS:
                with self.subTest(pin=want['id'], field=field):
                    if want[field] is None and field == 'meta':
                        # Свідома відмінність «санітарна обробка»: `null` у jsonb-колонці `meta` стає `{}` (читач `inbox`
                        # бере `meta or {}`), а в обʼєктних полях бувають ЗАЙВІ ключі (`outerHTML: ''`). Відсутнього — ні.
                        self.assertIn(got[field], (None, {}))
                    elif isinstance(want[field], dict):
                        self.assertEqual({k: got[field].get(k) for k in want[field]}, want[field])
                    else:
                        self.assertEqual(got[field], want[field])
        # `list` (0.34) після коментарів читає ще й `comment_replies`: звіряємо запит до `comments`
        [req] = [r for r in self.seen if '/rest/v1/comment_replies' not in r['url']]
        self.assertEqual(req['method'], 'GET')
        self.assertEqual(re.search(r'project_id=eq\.([^&]+)', req['url']).group(1), self.base['pins_query_channel'])
        self.assertTrue(req['url'].startswith(URL + '/rest/v1/comments?'))
        self.assertEqual(req['headers']['apikey'], KEY)
        self.assertEqual(req['headers']['authorization'], 'Bearer ' + KEY)

    def test_resolve_body_contains_the_recorded_0_9_0_body_and_filters_by_id_and_channel(self):
        self.pc().resolve(self.TASK, 't1', 'c1', 'виправлено', iteration=3)
        [req] = self.seen
        want = self.base['resolve']
        self.assertEqual(req['method'], 'PATCH')
        for key, value in want['body'].items():
            with self.subTest(key=key):
                self.assertEqual(req['body'].get(key), value)
        self.assertEqual(re.search(r'[?&]id=eq\.([^&]+)', req['url']).group(1), want['id_filter'])
        # свідома відмінність: пін чужого каналу не закриється
        self.assertEqual(re.search(r'project_id=eq\.([^&]+)', req['url']).group(1), self.base['pins_query_channel'])
        self.assertIs(type(req['body']['resolved_v']), int)

    def test_the_agent_object_for_the_league(self):
        pc = self.pc()
        # було `kind == 'implicit'` (неявний постачальник); тепер ЛІГА — явний запис, тож `module`, а підпис «Supabase» дає схема comment-layer
        self.assertEqual((pc.kind, pc.label, pc.takes_iteration), ('module', 'Supabase', True))
        self.assertEqual(pc.channel(self.TASK, 't1'), 'proj/alpha')
        self.assertEqual(pc.channel({}, 't2', internal=True), 'dc/t2/internal')

    def test_a_space_module_takes_the_iteration_only_when_it_is_the_builtin_supabase_one(self):
        builtin = deai_modules.catalog()['supabase-comments']
        pc = serve.ProjectComments(None)
        pc.prov = builtin
        self.assertIs(pc.kind, 'module')
        self.assertIs(pc.takes_iteration, True)
        own = mock.Mock(spec=deai_modules.Module)
        own.id, own.origin = 'supabase-comments', 'space'               # свій модуль з тим самим id — не вбудований
        pc.prov = own
        self.assertIs(pc.takes_iteration, False)
        other = mock.Mock(spec=deai_modules.Module)
        other.id, other.origin = 'memo-comments', 'builtin'
        pc.prov = other
        self.assertIs(pc.takes_iteration, False)

    def test_a_space_module_gets_four_arguments_only(self):
        """Власний модуль простору міг оголосити `resolve(ctx, channel, id, reason)`: номер ітерації йому не передається."""
        got = []
        own = mock.Mock(spec=deai_modules.Module)
        own.id, own.origin = 'own-comments', 'space'
        pc = self.pc()                                  # простір закріплено: без нього `Module` не мав би запису простору (4d-4b)
        pc.prov = own
        with mock.patch.object(serve, 'comments_route', return_value=(own, {}, lambda t, i, internal=False: 'ch')), \
                mock.patch.object(deai_modules, 'call', lambda mod, fn, ctx, ch, *args, timeout=None: got.append((fn, args))):
            pc.resolve({}, 't1', 'c1', 'готово', iteration=4)
        self.assertEqual(got, [('resolve', ('c1', 'готово'))])

    # --- відмови ---
    def test_without_a_record_pins_and_resolve_are_integrations_off_without_network(self):
        """Було: без конфігу кореня — `comments-unconfigured` (`ModuleError`). 4d-4b: «нема конфігу» = «нема запису ролі»: `IntegrationsOff`
        (`OSError`, `kind == 'off'`: ролі нікого не ведуть), а мережа мовчить."""
        pc = serve.ProjectComments(self.no_record())
        self.assertEqual((pc.kind, pc.label), ('off', 'не підключено'))
        with self.assertRaises(spaces.RoleOff):
            pc.pins(self.TASK, 't1')
        with self.assertRaises(spaces.RoleOff):
            pc.resolve(self.TASK, 't1', 'c1', 'r', iteration=1)
        self.assertEqual(self.seen, [])

    def test_a_disabled_record_gives_nobody_and_no_module_call(self):
        """Було: перевірка інтеграцій (`spaces.require_integrations`) ПЕРЕД викликом модуля. З 4d-4b рішення — наявність УВІМКНЕНОГО запису:
        вимкнений запис — ролі ніхто не веде (`IntegrationsOff`), мережі нема; контроль — увімкнений той самий виклик іде в модуль."""
        off_space, _ = self.league('comments', enabled=False)
        sbconf.patch_open(self, self.fake_open)
        pc = serve.ProjectComments(off_space)
        with self.assertRaises(spaces.RoleOff):
            pc.pins(self.TASK, 't1')
        with self.assertRaises(spaces.RoleOff):
            pc.resolve(self.TASK, 't1', 'c1', 'r', iteration=1)
        self.assertEqual(self.seen, [])
        on_space, _ = self.league('comments')
        sbconf.patch_open(self, self.fake_open)
        self.assertEqual(len(serve.ProjectComments(on_space).pins(self.TASK, 't1')), 2, 'контроль: з увімкненим записом виклик іде в модуль')

    def test_old_league_path_is_gone(self):
        self.assertFalse(hasattr(serve, 'supabase_pins'))
        self.assertFalse(hasattr(inbox, 'patch_project_pin'))
        self.assertFalse(hasattr(inbox, 'project_body'))
        self.assertFalse(hasattr(state, '_open_pins'))
        self.assertFalse(hasattr(inbox, 'supabase_pins'))
        self.assertFalse(hasattr(state, 'supabase_pins'))

    def test_comments_client_takes_a_ready_ctx_and_does_not_build_its_own(self):
        """`comments_client(…, ctx=…)`: публічна конфігурація браузерного адаптера — з ГОТОВОГО `ctx` ЛІГИ (без `space.json` і
        `secrets.json`: `_ctx` не кличеться); публічний ключ і кошик скріншотів у ній є."""
        mod = self.prov
        _, ctx, _ = serve.comments_route(self.space, self.prov)
        with mock.patch.object(deai_modules, '_ctx', side_effect=AssertionError('_ctx при готовому ctx')):
            cfg = deai_modules.comments_client(None, mod, ctx=ctx)
        self.assertEqual(cfg, {'url': URL, 'key': KEY, 'shotsBucket': 'overview-thumbs'})

    # --- state ---
    def setUpState(self, space=None):
        """`state._team_comments` будує `ProjectComments(spaces.active_space())`: простір ЛІГА — явний запис, закріплений простором запиту
        (`league()`), тож активним простором тут лишається він (чи `space`, підставлений тестом)."""
        active = mock.patch.object(spaces, 'active_space', return_value=space or self.space)
        active.start()
        self.addCleanup(active.stop)

    def test_state_counts_open_league_pins_through_the_module(self):
        self.setUpState()
        self.rows = [{**ROWS[0], 'meta': {**ROWS[0]['meta'], 'assignee': 'claude'}}, ROWS[1]]    # доручений Claude (Б2.3)
        self.assertEqual(state._team_comments(self.TASK, 't1'), (1, ' + 1 проєктних (доручено Claude)'))

    def test_state_says_cannot_reach_instead_of_a_silent_zero(self):
        self.setUpState()
        self.rows = {'not': 'a list'}
        n, tail = state._team_comments(self.TASK, 't1')
        self.assertEqual((n, tail), (0, ', проєктні: не дістати (module-error)'))

    def test_state_without_a_record_says_none_and_asks_nobody(self):
        """Заміна двох перевірок: «Supabase не налаштовано» (порожній корінь) і «без інтеграцій» (`require_integrations`) — тепер обидві це
        «запису ролі нема»: `проєктних нема`, жодного запиту."""
        self.setUpState(self.no_record())
        self.assertEqual(state._team_comments(self.TASK, 't1'), (0, ', проєктних нема'))
        self.assertEqual(self.seen, [])

    def test_the_league_resolve_refuses_an_unsafe_pin_id_before_any_request(self):
        """Білий список `id` піна діє й для ЛІГИ (як для модуля простору): чужий `id` іде в адресу PATCH."""
        pc = self.pc()
        for bad in ('a/b?x', 'x&project_id=neq.y', '', None, 5, 'a b'):
            with self.subTest(bad=bad), self.assertRaises(deai_modules.ModuleError) as cm:
                pc.resolve(self.TASK, 't1', bad, 'r', iteration=1)
            self.assertEqual(cm.exception.code, 'module-error')
        self.assertEqual(self.seen, [])

if __name__ == '__main__':
    unittest.main()
