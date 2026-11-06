"""Міграція ЛІГИ в явні `tracks` і модулі (етап 4d-3a, 0.17.0).

Тут: знімок поведінки 0.16.0 (`Before4d3aShape`, Task 1); `compat`, `shared_state`, розрахунок і запис міграції, паритет додаються
наступними задачами. Спека `docs/superpowers/specs/2026-11-05-liga-migration-a-design.md`.
"""
import json
import os
import re
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d3a.json')

ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs')
LEGACY_ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tracker', 'vcs')
MODULES = ('jira-tracker', 'supabase-dashboard', 'supabase-teams')

for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import spaces_guard  # noqa: E402

_REAL = None


def setUpModule():
    """⛔ Справжній реєстр `~/.deai` стереже `spaces_guard` (тести цього файлу пишуть `space.json` — лише у власних теках)."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class Before4d3aShape(unittest.TestCase):
    """Знімок 0.16.0 на місці й має ключі, типи та кількості сценаріїв, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['api', 'caps', 'check', 'connections', 'ctx', 'meta', 'non_loopback_attempts', 'tracks'])
        self.assertEqual(self.snap['meta']['version'], '0.16.0')
        self.assertEqual(self.snap['meta']['source_commit'], 'bf9bb5b')
        self.assertEqual(self.snap['meta']['generator'], 'tests/make_before_4d3a.py')
        self.assertEqual(self.snap['non_loopback_attempts'], 0)

    def test_machine_independent(self):
        """⛔ Знімок не несе ні справжніх шляхів, ні імен, ні тимчасових тек, ні секретів: лише `~/…`/`<tmp>`; значення — вигадані."""
        # ⛔ Імʼя користувача машини — з оточення, не літералом: справжнє імʼя в коді репо — та сама утічка, від якої тест береже.
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/Users/', '/home/', '/var/folders', '/private/', '/tmp/', 'before-4d3a-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        for secret in ('sb_test_key_alpha', 'sb_env_key_alpha', 'jira_env_token_alpha', 'jira_file_token_alpha'):
            self.assertNotIn(secret, self.raw, 'секрет у знімку: значення мусить бути <secret:ДОВЖИНА>')
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))          # жодного часового штампа
        self.assertEqual(self.snap['meta']['volatile_stripped'], [])

    def test_caps_liga_is_implicit_everywhere(self):
        c = self.snap['caps']
        self.assertEqual(c['space'], {'id': 'legacy', 'integrations': True, 'legacy': True, 'path': '<tmp>/liga-space'})
        self.assertEqual(sorted(c['caps']), list(ROLES))
        self.assertEqual({r: c['caps'][r] for r in LEGACY_ROLES}, {r: 'legacy' for r in LEGACY_ROLES})
        self.assertIsNone(c['caps']['tokens'])

    def test_tracks_adapter(self):
        t = self.snap['tracks']
        self.assertTrue(t['adapter'])
        self.assertEqual(t['default_track'], 'united')
        self.assertEqual(t['ids'], ['united', 'liga360', 'seo', 'custom-x'])
        self.assertEqual([x['id'] for x in t['tracks']], t['ids'])
        for x in t['tracks']:
            self.assertEqual(sorted(x), ['ds', 'id', 'label', 'repo', 'root'])
            self.assertEqual(x['ds'], x['id'])
            self.assertEqual(t['track_root'][x['id']], x['root'])
            self.assertEqual(t['track_repo'][x['id']], x['repo'])
        self.assertEqual(t['track_root']['united'], '~/work/united')
        self.assertEqual(t['track_root']['custom-x'], '~/work/custom')
        self.assertEqual(t['track_root']['seo'], '~/work/shared', 'напрямок без власного кореня — спільний')
        self.assertEqual(set(t['track_root_unknown'].values()), {'~/work/shared'}, 'невідоме значення — спільний корінь, не дефолтного')
        self.assertEqual(sorted(t['track_root_unknown']), sorted(["'United'", "'zzz'", "''", 'None', '7']))
        self.assertEqual(t['track_repo']['zzz'], '')

    def test_ctx_of_implicit_providers(self):
        c = self.snap['ctx']
        self.assertEqual(sorted(c), ['jira_env_beats_files', 'jira_from_env', 'jira_from_files', 'supabase_from_env', 'unconfigured'])
        expect = {'dashboard': ('supabase-dashboard', 'rows', {'table': 'overview_projects', 'url': 'https://sb.example.com'}, 'key'),
                  'tracker': ('jira-tracker', 'statuses', {'base': 'https://jira.example.com', 'email': 'alpha@example.com'}, 'token'),
                  'notify': ('supabase-teams', 'mute_state', {'url': 'https://sb.example.com'}, 'key')}
        for role, (mid, fn, settings, skey) in expect.items():
            row = c['jira_from_env'][role]
            self.assertEqual(row['provider'], 'Implicit')
            self.assertEqual(len(row['calls']), 1)
            call = row['calls'][0]
            self.assertEqual((call['module'], call['fn']), (mid, fn))
            self.assertEqual(call['ctx']['settings'], settings)
            self.assertTrue(call['ctx']['legacy'], 'ЛІГА: ctx несе legacy: True (його читає лише перевірка публічного ключа)')
            self.assertEqual(call['ctx']['space'], {'id': 'legacy', 'path': ''})
            self.assertEqual(list(call['ctx']['secrets']), [skey])
            self.assertRegex(call['ctx']['secrets'][skey], r'^<secret:\d+>$')
        # Jira з файлів pipeline-feedback: пошта з файла; оточення раніше за файли
        self.assertEqual(c['jira_from_files']['tracker']['calls'][0]['ctx']['settings']['email'], 'file@example.com')
        self.assertEqual(c['jira_env_beats_files']['tracker']['calls'][0]['ctx']['settings']['email'], 'alpha@example.com')
        # Supabase з оточення, коли в корені пари нема; Jira без облікових — без виклику модуля
        self.assertEqual(c['supabase_from_env']['dashboard']['calls'][0]['ctx']['settings']['url'], 'https://sb-env.example.com')
        self.assertEqual(c['supabase_from_env']['tracker']['calls'], [])
        # конфігу нема: жодного виклику, чесні відмови
        for role in ('dashboard', 'tracker', 'notify'):
            self.assertEqual(c['unconfigured'][role]['calls'], [], role)
        self.assertEqual(c['unconfigured']['notify']['flow_outcome']['code'], 'notify-unconfigured')

    def test_check_verdicts(self):
        k = self.snap['check']
        self.assertEqual(sorted(k), ['core_check', 'jira-tracker', 'public_key', 'supabase-dashboard', 'supabase-teams'])
        for mid in MODULES:
            self.assertTrue(k[mid]['ok']['outcome']['result']['ok'], mid)
            self.assertEqual(k[mid]['network']['outcome']['result']['error'], 'network', mid)
            self.assertEqual(len(k[mid]['ok']['requests']), 1, mid)
        self.assertEqual(k['supabase-dashboard']['denied']['outcome']['result']['error'], 'bad-key')
        self.assertEqual(k['supabase-teams']['denied']['outcome']['result']['error'], 'bad-key')
        self.assertEqual(k['jira-tracker']['denied']['outcome']['result']['error'], 'tracker-auth')
        # прапорець legacy: публічний ключ у ЛІГИ проходить, без прапорця — `public-key` без запиту в мережу
        for mid in ('supabase-dashboard', 'supabase-teams'):
            for variant in ('', 'jwt_anon_'):
                self.assertTrue(k['public_key'][mid][variant + 'legacy_true']['outcome']['result']['ok'], mid)
                absent = k['public_key'][mid][variant + 'legacy_absent']
                self.assertEqual(absent['outcome']['result']['error'], 'public-key', mid)
                self.assertEqual(absent['requests'], [], mid)
        # кнопка «Перевірити» ядра на ЛІГІ без space.json: налаштувань нема — `bad-settings`, мережі нема
        for mid in MODULES:
            self.assertEqual(k['core_check'][mid]['outcome']['code'], 'bad-settings', mid)
            self.assertEqual(k['core_check'][mid]['requests'], [], mid)

    def test_api(self):
        a = self.snap['api']
        self.assertTrue(a['layer_on'])
        self.assertEqual((a['vcs_provider_calls'], a['urlopen_calls']), (0, 0))
        rows = a['spaces']['rows']
        self.assertEqual([r['id'] for r in rows], ['legacy'])
        self.assertEqual({r: rows[0]['capabilities'][r] for r in LEGACY_ROLES}, {r: 'legacy' for r in LEGACY_ROLES})
        self.assertEqual(rows[0]['default_track'], 'united')
        self.assertEqual([t['id'] for t in rows[0]['tracks']], ['united', 'liga360', 'seo', 'custom-x'])
        self.assertEqual(a['modules']['status'], 200)
        self.assertEqual([m['id'] for m in a['modules']['list']],
                         ['css-tokens', 'git-sync', 'jira-tracker', 'static-publish', 'supabase-comments', 'supabase-dashboard',
                          'supabase-teams', 'vercel-publish'])
        self.assertFalse(any(m['enabled'] or m['implicit'] for m in a['modules']['list']), 'у ЛІГИ жоден модуль не ввімкнений явно')
        t = a['tasks']
        self.assertEqual((t['a-1']['track'], t['a-1']['tags'], t['a-1']['jira']), ('seo', ['SEO'], 'DEMO-1'))
        self.assertEqual((t['a-2']['track'], t['a-2']['tags'], t['a-2']['profile']), ('united', ['United'], 'united'))
        for tid in t:
            self.assertEqual(t[tid]['status'], 200)
            self.assertEqual(t[tid]['space']['id'], 'legacy')
            self.assertEqual(t[tid]['space']['capabilities'], rows[0]['capabilities'])

    def test_connections(self):
        now = self.snap['connections']['now']
        self.assertEqual(now['role_order'], ['publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify', 'tokens'])
        for role in LEGACY_ROLES:
            self.assertEqual(now['roles'][role]['provider']['kind'], 'legacy', role)
        self.assertEqual(now['roles']['tokens']['provider']['kind'], 'none')
        self.assertEqual([s['role'] for s in now['sections']], now['role_order'])
        self.assertEqual(now['duplicate_cards'], [])
        for mid in MODULES:
            self.assertEqual(now['cards'][mid]['view']['badge'], 'off', mid)
        # гіпотетичний стан після міграції: ті самі три картки, провайдер — модуль, дубля нема
        h = self.snap['connections']['hypothetical_explicit']
        self.assertEqual({r: h['capabilities'][r] for r in ('tracker', 'dashboard', 'notify')},
                         {'tracker': 'jira-tracker', 'dashboard': 'supabase-dashboard', 'notify': 'supabase-teams'})
        self.assertEqual(h['screen']['duplicate_cards'], [])
        self.assertEqual(h['screen']['sections'], now['sections'], 'набір карток не змінюється — лише рядок «Зараз» і стан')
        self.assertEqual(h['screen']['roles']['tracker']['provider']['kind'], 'module')
        for mid in MODULES:
            self.assertEqual(h['screen']['cards'][mid]['view']['badge'], 'unchecked', mid)


class CompatSetting(unittest.TestCase):
    """Task 2 (4d-3a): налаштування `compat` модулів `supabase-dashboard`/`supabase-teams` замість прапорця `ctx['legacy']`.

    ⛔ `check` на неявному шляху ЛІГИ (`legacy_ctx`) лишається побайтно тим, що в знімку 0.16.0 (секції `check`): порівняння
    через будівники ТОГО Ж генератора (`tests/make_before_4d3a.py`), без мережі (шов `_open` підмінено, сокети під розтяжкою)."""

    MODS = ('supabase-dashboard', 'supabase-teams')

    @classmethod
    def setUpClass(cls):
        import sys
        for p in (os.path.join(os.path.dirname(_HERE), 'app'), os.path.join(os.path.dirname(_HERE), 'bin'), _HERE):
            if p not in sys.path:
                sys.path.insert(0, p)
        import make_before_4d3a as gen
        cls.gen = gen
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)['check']

    def setUp(self):
        import tempfile
        from unittest import mock
        gen = self.gen
        self._tmp = tempfile.TemporaryDirectory(prefix='compat-')
        self.addCleanup(self._tmp.cleanup)
        home = os.path.join(os.path.normpath(self._tmp.name), 'home')
        os.makedirs(home)
        patch = mock.patch.dict(os.environ, {'HOME': home})
        patch.start()
        self.addCleanup(patch.stop)
        for name in gen.CLEAN:
            os.environ.pop(name, None)
        wire = gen.SocketTripwire()
        wire.__enter__()
        self.addCleanup(lambda: wire.__exit__(None, None, None))
        self.wire = wire
        self.rig = gen.Rig(os.path.normpath(self._tmp.name), 'cs')
        self.rig.config()
        self.rig.registry()

    def _ctxs(self):
        import dashboard
        import install_config
        import notify
        url, key = install_config.supabase_config()
        return {'supabase-dashboard': dashboard.legacy_ctx(url, key, space_id=self.gen.SPACE_ID),
                'supabase-teams': notify.legacy_ctx(url, key, space_id=self.gen.SPACE_ID)}

    def _run(self, mid, ctx, scenario='ok'):
        return json.loads(json.dumps(self.gen.scrub(self.gen._run_check(mid, ctx, scenario), self.rig.home)))

    @staticmethod
    def _with(ctx, key=None, compat=None, legacy=None):
        """Копія ctx: ключ; `compat` (`None` — прибрати налаштування); `legacy` (`None` — прибрати прапорець)."""
        c = dict(ctx)
        c['settings'] = {k: v for k, v in ctx['settings'].items() if k != 'compat'}
        if compat is not None:
            c['settings']['compat'] = compat
        c.pop('legacy', None)
        if legacy is not None:
            c['legacy'] = legacy
        if key is not None:
            c['secrets'] = {'key': key}
        return c

    def test_legacy_ctx_carries_compat(self):
        with self.rig.activate():
            for mid, ctx in self._ctxs().items():
                self.assertEqual(ctx['settings']['compat'], 'comment-layer', mid)
                self.assertIs(ctx['legacy'], True, 'прапорець лишено для чужих модулів')

    def test_implicit_path_verdicts_equal_snapshot(self):
        """Вердикти `check` на `legacy_ctx` (ok/denied/network і публічні ключі) — побайтно секція `check` знімка."""
        with self.rig.activate():
            ctxs = self._ctxs()
            for mid in self.MODS:
                for sc in ('ok', 'denied', 'network'):
                    self.assertEqual(self._run(mid, ctxs[mid], sc), self.snap[mid][sc], (mid, sc))
                pub = self.snap['public_key'][mid]
                c = dict(ctxs[mid], secrets={'key': 'sb_publishable_alpha'})      # compat — саме з `legacy_ctx`, не дописаний тестом
                self.assertEqual(self._run(mid, c), pub['legacy_true'], mid)
                jwt = self.gen._jwt_anon()
                c = dict(ctxs[mid], secrets={'key': jwt})
                self.assertEqual(self._run(mid, c), pub['jwt_anon_legacy_true'], mid)

    def test_without_compat_public_key_refused_even_with_legacy_flag(self):
        """Без `compat` (нема/`""`) прапорець `ctx['legacy'] = True` нічого не змінює: публічний ключ → `public-key`, мережі нема."""
        with self.rig.activate():
            ctxs = self._ctxs()
            for mid in self.MODS:
                for compat in (None, ''):
                    for key in ('sb_publishable_alpha', self.gen._jwt_anon()):
                        c = self._with(ctxs[mid], key=key, compat=compat, legacy=True)
                        out = self._run(mid, c)
                        self.assertEqual(out['outcome']['result']['error'], 'public-key', (mid, compat))
                        self.assertEqual(out['requests'], [])
                ref = self._with(ctxs[mid], key='sb_publishable_alpha', compat=None)
                self.assertEqual(self._run(mid, self._with(ctxs[mid], key='sb_publishable_alpha', compat=None, legacy=True)),
                                 self._run(mid, ref), 'прапорець legacy не змінює нічого')
                self.assertEqual(self._run(mid, ref), self.snap['public_key'][mid]['legacy_absent'], mid)

    def test_teams_compat_skips_health_and_uses_legacy_texts(self):
        """`supabase-teams` + `compat`: лише `teams_mute_state` (без `teams_notify_health`); без нього — обидва виклики."""
        with self.rig.activate():
            ctx = self._ctxs()['supabase-teams']
            on = self._run('supabase-teams', ctx)
            self.assertEqual([r[1].rsplit('/', 1)[-1] for r in on['requests']], ['teams_mute_state'])
            off = self._run('supabase-teams', self._with(ctx, compat=None, legacy=True, key='sb_secret_alpha'))
            self.assertEqual([r[1].rsplit('/', 1)[-1] for r in off['requests']][:2], ['teams_mute_state', 'teams_notify_health'])
            self.assertEqual(self._run('supabase-teams', ctx, 'denied'), self.snap['supabase-teams']['denied'])

    def test_manifests_declare_compat_as_select(self):
        """Формат `select` — як у наявних модулях (`options: [{value, label}]`); невідоме значення — `bad-settings` наявним механізмом."""
        import deai_modules as dm
        dm.reset_caches()
        for mid in self.MODS:
            mod = dm.catalog()[mid]
            s = {x['key']: x for x in mod.settings}['compat']
            self.assertEqual(s['type'], 'select')
            self.assertFalse(s['required'])
            self.assertEqual(s.get('default'), '')
            self.assertEqual([o['value'] for o in s['options']], ['', 'comment-layer'])
            self.assertEqual(dm.resolve_settings({'id': 'x', 'path': ''}, mod, {'url': 'https://sb.example.com', 'compat': 'comment-layer'})['compat'],
                             'comment-layer')
            self.assertEqual(dm.resolve_settings({'id': 'x', 'path': ''}, mod, {'url': 'https://sb.example.com'})['compat'], '')
            for bad in ('legacy', 'Comment-Layer', 'comment-layer ', 1, True):
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.resolve_settings({'id': 'x', 'path': ''}, mod, {'url': 'https://sb.example.com', 'compat': bad})
                self.assertEqual(cm.exception.code, 'bad-settings', repr(bad))

    def test_builtin_modules_do_not_read_legacy_flag(self):
        """⛔ Охоронець: у `app/modules/*/server.py` нема читання `ctx.get('legacy')` / `ctx['legacy']` (AST: коментарі й докстрінги,
        що згадують прапорець, не рахуються). Прапорець лишено чужим модулям, вбудовані вирішують `settings.compat`."""
        import ast
        import glob
        files = sorted(glob.glob(os.path.join(os.path.dirname(_HERE), 'app', 'modules', '*', 'server.py')))
        self.assertGreaterEqual(len(files), 6)
        hits = []
        for path in files:
            with open(path, encoding='utf-8') as f:
                tree = ast.parse(f.read(), path)
            for n in ast.walk(tree):
                if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == 'legacy':
                    hits.append((path, n.lineno))
                elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get'
                      and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'legacy'):
                    hits.append((path, n.lineno))
        self.assertEqual(hits, [])


class SharedStateIsolation(unittest.TestCase):
    """Task 3 (4d-3a): явний запис модуля з `shared_state: true` — спільний стан ЛІГИ, закон ізоляції той самий, що в `Implicit`:
    шов ролі → точна ізольована відповідь БЕЗ виклику модуля → живий виклик модулем із `module_ctx` (не легасі-збирачем).
    Запис без `shared_state` (чи з не-`bool`) — як сьогодні: жодного шва, модуль кличеться навіть під ізоляцією."""

    ROLES = {'dashboard': ('supabase-dashboard', 'DC_TEAM_FAKE'), 'tracker': ('jira-tracker', 'DC_TRACKER_FAKE'),
             'notify': ('supabase-teams', 'DC_TEAMS_FAKE')}

    @classmethod
    def setUpClass(cls):
        import sys
        for p in (os.path.join(os.path.dirname(_HERE), 'app'), os.path.join(os.path.dirname(_HERE), 'bin')):
            if p not in sys.path:
                sys.path.insert(0, p)

    def setUp(self):
        import tempfile
        from unittest import mock
        import deai_modules as dm
        self.dm = dm
        self._tmp = tempfile.TemporaryDirectory(prefix='shared-state-')
        self.addCleanup(self._tmp.cleanup)
        self.tmp = os.path.normpath(self._tmp.name)
        self.space = {'id': 'liga-x', 'path': os.path.join(self.tmp, 'space'), 'integrations': True}
        os.makedirs(self.space['path'])
        patch = mock.patch.dict(os.environ, {'HOME': os.path.join(self.tmp, 'home'), 'DEAI_HOME': os.path.join(self.tmp, 'deai')})
        patch.start()
        self.addCleanup(patch.stop)
        for name in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TRACKER_FAKE', 'DC_TEAMS_FAKE'):
            os.environ.pop(name, None)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)

    def _write(self, mid, **extra):
        rec = {'enabled': True, 'settings': {}}
        rec.update(extra)
        with open(os.path.join(self.space['path'], 'space.json'), 'w', encoding='utf-8') as f:
            json.dump({'modules': {mid: rec}}, f)

    def _mod(self, role):
        return self.dm.catalog()[self.ROLES[role][0]]

    def _fake_file(self, content):
        path = os.path.join(self.tmp, 'fake.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f)
        return path

    def _call(self, role):
        """Виклик ядра ролі напряму; `(результат, кількість викликів модуля, ctx)` — модуль і `module_ctx` підмінено."""
        import dashboard
        import notify
        import serve
        import tracker
        from unittest import mock
        mod = self._mod(role)
        ctx = {'marker': 'module-ctx'}
        with mock.patch.object(self.dm, 'module_ctx', return_value=ctx) as mc:
            if role == 'dashboard':
                with mock.patch.object(dashboard, 'rows', return_value=[{'id': 'live'}]) as m:
                    res = serve._team_fetch(self.space, mod)
            elif role == 'tracker':
                with mock.patch.object(tracker, 'statuses', return_value={'K-1': {'name': 'live', 'cat': 'x'}}) as m:
                    res = serve._tracker_fetch(self.space, mod, ['K-1'])
            else:
                with mock.patch.object(self.dm, 'call', return_value=[]) as m:
                    try:
                        res = serve.notify_call('mute_state', resolved=(self.space, mod))
                    except OSError as e:
                        res = ('OSError', str(e))
        return res, m.call_count, mc.call_count

    def _fake_value(self, role):
        return {'dashboard': [{'id': 'seam'}], 'tracker': {'K-1': {'name': 'S', 'cat': 'new'}}, 'notify': {}}[role]

    def test_shared_state_helper(self):
        mid = 'supabase-dashboard'
        self.assertFalse(self.dm.shared_state(self.space, mid))                       # файла нема
        self._write(mid)
        self.assertFalse(self.dm.shared_state(self.space, mid))                       # прапорця нема
        self._write(mid, shared_state=True)
        self.assertTrue(self.dm.shared_state(self.space, mid))
        self.assertFalse(self.dm.shared_state(self.space, 'jira-tracker'))            # іншого запису нема
        self._write(mid, shared_state=False)
        self.assertFalse(self.dm.shared_state(self.space, mid))
        for bad in ('true', 1, 'yes', [], {}, None):                                  # не-bool — як False, не виняток
            self._write(mid, shared_state=bad)
            self.assertFalse(self.dm.shared_state(self.space, mid), repr(bad))
        with open(os.path.join(self.space['path'], 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        self.assertFalse(self.dm.shared_state(self.space, mid))                       # збій читання — False
        self.assertFalse(self.dm.shared_state(None, mid))

    def test_normalize_keeps_bool_only(self):
        self._write('jira-tracker', shared_state=True)
        self.assertIs(self.dm.space_modules(self.space)['jira-tracker']['shared_state'], True)
        self._write('jira-tracker', shared_state='true')
        self.assertNotIn('shared_state', self.dm.space_modules(self.space)['jira-tracker'])

    def test_seam_wins_for_shared_module(self):
        for role, (mid, env) in self.ROLES.items():
            self._write(mid, shared_state=True)
            with self.subTest(role=role):
                from unittest import mock
                with mock.patch.dict(os.environ, {env: self._fake_file({} if role == 'notify' else
                                                                       ([{'id': 'seam'}] if role == 'dashboard' else {'K-1': {'name': 'S', 'cat': 'new'}})),
                                                  'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
                    res, called, ctxs = self._call(role)
                self.assertEqual((called, ctxs), (0, 0))
                if role == 'dashboard':
                    self.assertEqual(res, ([{'id': 'seam'}], None))
                elif role == 'tracker':
                    self.assertEqual(res[1], None)
                    self.assertEqual(res[0]['K-1']['name'], 'S')
                else:
                    self.assertEqual(res, [])

    def test_isolated_answers_exact_and_module_not_called(self):
        import serve
        want = {'dashboard': ([], serve.TEAM_ISOLATED), 'tracker': None,
                'notify': ('OSError', 'ізольований конфіг: спільний стан Teams не чіпаємо')}
        for role, (mid, env) in self.ROLES.items():
            self._write(mid, shared_state=True)
            for iso in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
                with self.subTest(role=role, iso=iso):
                    from unittest import mock
                    with mock.patch.dict(os.environ, {iso: os.path.join(self.tmp, 't.json') if iso == 'DC_TASKS_FILE' else '1'}):
                        res, called, ctxs = self._call(role)
                    self.assertEqual(res, want[role])
                    self.assertEqual((called, ctxs), (0, 0), 'модуль не кличеться і ctx не збирається')

    def test_tracker_order_isolated_before_empty_keys(self):
        """⛔ Порядок `tracker`: шов → ізоляція → `if not keys`: ізольований прогін без ключів — `None`, поза ізоляцією — `({}, None)`."""
        import serve
        from unittest import mock
        self._write('jira-tracker', shared_state=True)
        mod = self._mod('tracker')
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            self.assertIsNone(serve._tracker_fetch(self.space, mod, []))
        self.assertEqual(serve._tracker_fetch(self.space, mod, []), ({}, None))

    def test_live_uses_module_with_module_ctx(self):
        import dashboard
        import tracker
        for role, (mid, env) in self.ROLES.items():
            self._write(mid, shared_state=True)
            with self.subTest(role=role):
                res, called, ctxs = self._call(role)
                self.assertEqual((called, ctxs), (1, 1), 'один виклик модуля, один module_ctx')
                if role == 'dashboard':
                    self.assertEqual(res, ([{'id': 'live'}], None))
                elif role == 'tracker':
                    self.assertEqual(res[0]['K-1']['name'], 'live')

    def test_live_never_uses_legacy_builders(self):
        import dashboard
        import notify
        import serve
        import tracker
        from unittest import mock
        for role, (mid, env) in self.ROLES.items():
            self._write(mid, shared_state=True)
            with self.subTest(role=role), mock.patch.object(dashboard, 'legacy_ctx', side_effect=AssertionError('legacy')), \
                    mock.patch.object(tracker, 'legacy_ctx', side_effect=AssertionError('legacy')), \
                    mock.patch.object(notify, 'legacy_ctx', side_effect=AssertionError('legacy')), \
                    mock.patch.object(serve, 'supabase_config', side_effect=AssertionError('cfg')), \
                    mock.patch.object(serve, 'jira_config', side_effect=AssertionError('cfg')):
                res, called, _ = self._call(role)
                self.assertEqual(called, 1)

    def test_without_shared_state_behaves_as_today(self):
        """Той самий запис БЕЗ `shared_state` (і з не-`bool`): шов ігнорується, модуль кличеться навіть під ізоляцією."""
        from unittest import mock
        for role, (mid, env) in self.ROLES.items():
            for extra in ({}, {'shared_state': False}, {'shared_state': 'true'}, {'shared_state': 1}):
                self._write(mid, **extra)
                with self.subTest(role=role, extra=extra), mock.patch.dict(
                        os.environ, {env: self._fake_file({}), 'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
                    _, called, ctxs = self._call(role)
                    self.assertEqual((called, ctxs), (1, 1))

    def _sync(self, prov):
        import serve
        from unittest import mock
        with mock.patch.object(self.dm, 'provider', return_value=prov), \
                mock.patch.object(serve.spaces, 'active_space', return_value=self.space), \
                mock.patch.object(serve, '_overview_target', return_value=('liga-x', ['--space', 'liga-x'])), \
                mock.patch.object(serve, '_overview_launch') as launch:
            serve.Handler._overview_sync(None)
        return launch

    def test_sync_shared_not_spawned_under_isolation(self):
        from unittest import mock
        mod = self._mod('dashboard')
        self._write(mod.id, shared_state=True)
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
            self._sync(mod).assert_not_called()
        with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1'}):
            self._sync(mod).assert_not_called()
        self._sync(mod).assert_called_once()                                          # поза ізоляцією — стартує

    def test_sync_without_shared_state_unchanged(self):
        from unittest import mock
        mod = self._mod('dashboard')
        for extra in ({}, {'shared_state': 'true'}):
            self._write(mod.id, **extra)
            with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(self.tmp, 't.json')}):
                self._sync(mod).assert_called_once()                                  # як сьогодні: модуль без прапорця синкає

    def test_connections_write_keeps_shared_state(self):
        """Екран «Підключення» правит налаштування й `enabled` через `write_module_state`: `shared_state` переживає обидві правки."""
        mid = 'supabase-dashboard'
        self._write(mid, shared_state=True, settings={'url': 'https://sb.example.com'})
        self.dm.write_module_state(self.space, mid, settings={'url': 'https://sb2.example.com'})
        self.assertTrue(self.dm.shared_state(self.space, mid))
        self.dm.write_module_state(self.space, mid, enabled=False)
        self.assertTrue(self.dm.shared_state(self.space, mid))
        self.dm.write_module_state(self.space, mid, enabled=True)
        self.assertTrue(self.dm.shared_state(self.space, mid))
        rec = self.dm.space_modules(self.space)[mid]
        self.assertEqual((rec['enabled'], rec['settings']['url']), (True, 'https://sb2.example.com'))


class PlanTest(unittest.TestCase):
    """Task 4 (4d-3a): чистий розрахунок `liga_migrate.plan()` — нічого не пишемо, секрети лише в `plan['secrets']`, `report()` без
    значень. Стенд: тимчасові HOME/DEAI_HOME, реєстр із записом ЛІГИ, старий `tasks.json` у тимчасовій теці (підміна
    `spaces.legacy_tasks_file`), вигадані значення."""

    SB_URL, SB_KEY = 'https://sb.example.com', 'sb_plan_key_alpha'
    JIRA_BASE, JIRA_EMAIL, JIRA_TOKEN = 'https://jira.example.com', 'alpha@example.com', 'jira_plan_token_alpha'
    REPO_U, REPO_S = 'git@example.com:studio/web.git', 'ssh://git@example.com/o/r.git'
    CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'DC_TRACKER_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
             'SUPABASE_SERVICE_KEY', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DEAI_EXTRA_MODULES')

    @classmethod
    def setUpClass(cls):
        for p in (os.path.join(os.path.dirname(_HERE), 'app'),):
            if p not in sys.path:
                sys.path.insert(0, p)

    def setUp(self):
        import tempfile
        from unittest import mock
        import deai_modules as dm
        import liga_migrate
        import spaces
        self.dm, self.lm, self.spaces, self.mock = dm, liga_migrate, spaces, mock
        self._tmp = tempfile.TemporaryDirectory(prefix='liga-plan-')
        self.addCleanup(self._tmp.cleanup)
        self.tmp = os.path.realpath(self._tmp.name)
        self.home = os.path.join(self.tmp, 'home')
        self.deai = os.path.join(self.home, '.deai')
        self.space_dir = os.path.join(self.tmp, 'liga-space')
        self.tasks_path = os.path.join(self.tmp, 'legacy-tasks.json')
        for d in (self.home, self.deai, self.space_dir):
            os.makedirs(d)
        env = mock.patch.dict(os.environ, {'HOME': self.home, 'DEAI_HOME': self.deai})
        env.start()
        self.addCleanup(env.stop)
        for name in self.CLEAN:
            os.environ.pop(name, None)
        lf = mock.patch.object(spaces, 'legacy_tasks_file', lambda: self.tasks_path)
        lf.start()
        self.addCleanup(lf.stop)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        self.registry()
        self.config()

    # --- стенд
    def _write(self, path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(obj if isinstance(obj, str) else json.dumps(obj))

    def registry(self, entry=True, path=None):
        spaces_list = [{'id': 'legacy', 'path': path or self.space_dir, 'legacy': True, 'integrations': True}] if entry else []
        self._write(os.path.join(self.deai, 'spaces.json'), {'version': 1, 'current': 'legacy' if entry else None, 'spaces': spaces_list})

    def space_json(self, obj):
        self._write(os.path.join(self.space_dir, 'space.json'), obj)

    def config(self, supabase=True, jira=True, **extra):
        work = os.path.join(self.home, 'work')
        cfg = {'design_work_root': os.path.join(work, 'shared'),
               'design_work_roots': {'custom-x': os.path.join(work, 'custom')},
               'profile_repos': {'united': self.REPO_U, 'seo': self.REPO_S},
               'tasks': {'a-1': {'dir': os.path.join(work, 'a-1'), 'title': 'Alpha', 'track': 'seo'},
                         'a-2': {'dir': os.path.join(work, 'a-2'), 'title': 'Beta', 'profile': 'united'}}}
        if supabase:
            cfg.update(supabase_url=self.SB_URL, supabase_key=self.SB_KEY)
        if jira:
            cfg.update(jira_base=self.JIRA_BASE)
            os.environ['JIRA_EMAIL'], os.environ['JIRA_TOKEN'] = self.JIRA_EMAIL, self.JIRA_TOKEN
        else:
            os.environ.pop('JIRA_EMAIL', None)
            os.environ.pop('JIRA_TOKEN', None)
        cfg.update(extra)
        self.cfg = cfg
        self._write(self.tasks_path, cfg)
        return cfg

    def snapshot_tree(self):
        out = {}
        for base, _dirs, files in os.walk(self.tmp):
            for f in files:
                p = os.path.join(base, f)
                with open(p, 'rb') as fh:
                    out[p] = fh.read()
        return out

    def plan(self, **kw):
        return self.lm.plan(**kw)

    # --- пропуски
    def test_skip_layer_off(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': self.tasks_path}):
            os.environ.pop('DEAI_HOME')
            p = self.plan()
        self.assertEqual(p['status'], 'skip-layer-off')
        self.assertIsNone(p['space_json'])

    def test_skip_no_liga(self):
        self.registry(entry=False)
        self.assertEqual(self.plan()['status'], 'skip-no-liga')

    def test_skip_done(self):
        self.space_json({'migrations': {'liga-4d3a': {'at': 'x', 'roles': [], 'tracks': False}}})
        self.assertEqual(self.plan()['status'], 'skip-done')

    def test_skip_held(self):
        self.space_json({'migrations': {'liga-4d3a': {'held': True}}})
        self.assertEqual(self.plan()['status'], 'skip-held')

    def test_skip_no_path(self):
        self.registry(path=os.path.join(self.tmp, 'nowhere'))
        self.assertEqual(self.plan()['status'], 'skip-no-path')

    def test_skip_path_in_git(self):
        os.makedirs(os.path.join(self.space_dir, '.git'))                      # `.git` — тека у самій теці простору
        self.assertEqual(self.plan()['status'], 'skip-path-in-git')

    def test_skip_path_in_git_ancestor_file(self):
        outer = os.path.join(self.tmp, 'checkout')
        inner = os.path.join(outer, 'sub', 'liga')
        os.makedirs(inner)
        self._write(os.path.join(outer, '.git'), 'gitdir: elsewhere')           # `.git` — ФАЙЛ (worktree) у предку
        self.registry(path=inner)
        self.assertEqual(self.plan()['status'], 'skip-path-in-git')

    def test_skip_space_json_unreadable(self):
        self.space_json('{broken')
        self.assertEqual(self.plan()['status'], 'skip-space-json-unreadable')
        self.space_json({'modules': []})                                        # `modules` не обʼєкт — теж нечитабельний
        self.assertEqual(self.plan()['status'], 'skip-space-json-unreadable')

    def test_skip_tasks_unreadable_and_registry_unreadable(self):
        self._write(self.tasks_path, '{broken')
        self.assertEqual(self.plan()['status'], 'skip-tasks-unreadable')
        self.config()
        self._write(os.path.join(self.deai, 'spaces.json'), '{broken')
        self.assertEqual(self.plan()['status'], 'skip-registry-unreadable')

    # --- повний розрахунок
    def test_full_plan(self):
        before = self.snapshot_tree()
        p = self.plan()
        self.assertEqual(self.snapshot_tree(), before)                          # ⛔ нічого не записано
        self.assertEqual(p['status'], 'ready')
        self.assertEqual(p['space_id'], 'legacy')
        self.assertEqual({r: v['migrate'] for r, v in p['roles'].items()}, {'tracker': True, 'dashboard': True, 'notify': True})
        self.assertTrue(p['tracks'])
        sj = p['space_json']
        self.assertEqual(sj['modules'], {
            'jira-tracker': {'enabled': True, 'shared_state': True, 'settings': {'base': self.JIRA_BASE, 'email': self.JIRA_EMAIL}},
            'supabase-dashboard': {'enabled': True, 'shared_state': True,
                                   'settings': {'url': self.SB_URL, 'table': 'overview_projects', 'compat': 'comment-layer'}},
            'supabase-teams': {'enabled': True, 'shared_state': True, 'settings': {'url': self.SB_URL, 'compat': 'comment-layer'}}})
        self.assertEqual(p['secrets'], {'jira-tracker': {'token': self.JIRA_TOKEN}, 'supabase-dashboard': {'key': self.SB_KEY},
                                        'supabase-teams': {'key': self.SB_KEY}})
        shared = os.path.join(self.home, 'work', 'shared')
        self.assertEqual(sj['default_track'], 'united')
        self.assertEqual([(t['id'], t['label'], t['root'], t['repo'], t['ds']) for t in sj['tracks']], [
            ('united', 'United', shared, self.REPO_U, 'united'), ('liga360', 'LIGA360', shared, '', 'liga360'),
            ('seo', 'SEO', shared, self.REPO_S, 'seo'),
            ('custom-x', 'custom-x', os.path.join(self.home, 'work', 'custom'), '', 'custom-x')])      # нестандартний ключ
        self.assertEqual(sj['migrations'], {'liga-4d3a': {'roles': ['tracker', 'dashboard', 'notify'], 'tracks': True}})

    def test_existing_space_json_keys_kept(self):
        self.space_json({'name': 'Liga', 'color': '#123456', 'foreign': {'k': 1},
                         'migrations': {'other': {'at': 'x'}}, 'modules': {'static-publish': {'enabled': False}}})
        sj = self.plan()['space_json']
        self.assertEqual((sj['name'], sj['color'], sj['foreign']), ('Liga', '#123456', {'k': 1}))
        self.assertEqual(sj['migrations']['other'], {'at': 'x'})
        self.assertEqual(sj['modules']['static-publish'], {'enabled': False})
        self.assertIn('jira-tracker', sj['modules'])

    def test_home_argument(self):
        self.assertEqual(self.plan(home=self.deai)['status'], 'ready')
        self.assertEqual(self.plan(home=os.path.join(self.tmp, 'empty-home'))['status'], 'skip-no-liga')

    def test_no_supabase_only_tracker(self):
        self.config(supabase=False)
        p = self.plan()
        self.assertEqual(p['status'], 'ready')
        self.assertEqual(sorted(p['space_json']['modules']), ['jira-tracker'])
        self.assertEqual([p['roles'][r]['reason'] for r in ('dashboard', 'notify')], ['no-supabase'] * 2)
        self.assertEqual(sorted(p['secrets']), ['jira-tracker'])

    def test_no_jira_no_tracker(self):
        self.config(jira=False)
        p = self.plan()
        self.assertEqual(sorted(p['space_json']['modules']), ['supabase-dashboard', 'supabase-teams'])
        self.assertEqual(p['roles']['tracker'], {'module': 'jira-tracker', 'migrate': False, 'reason': 'no-jira'})
        self.assertNotIn('jira-tracker', p['secrets'])

    def test_module_already_present_role_not_migrated(self):
        self.space_json({'modules': {'supabase-dashboard': {'enabled': False, 'settings': {'url': 'https://own.example.com'}}}})
        p = self.plan()
        self.assertEqual(p['roles']['dashboard'], {'module': 'supabase-dashboard', 'migrate': False, 'reason': 'module-present'})
        self.assertEqual(p['space_json']['modules']['supabase-dashboard'], {'enabled': False, 'settings': {'url': 'https://own.example.com'}})
        self.assertNotIn('supabase-dashboard', p['secrets'])
        self.assertEqual(p['space_json']['migrations']['liga-4d3a']['roles'], ['tracker', 'notify'])

    def test_non_empty_tracks_not_touched(self):
        own = [{'id': 'mine', 'label': 'Mine'}]
        self.space_json({'tracks': own, 'default_track': 'mine'})
        p = self.plan()
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', False, 'tracks-present'))
        self.assertEqual((p['space_json']['tracks'], p['space_json']['default_track']), (own, 'mine'))
        self.assertFalse(p['space_json']['migrations']['liga-4d3a']['tracks'])
        self.assertEqual(len(p['space_json']['modules']), 3)                      # ролі мігрують далі

    # --- паритет напрямків
    def test_tracks_parity_abort(self):
        """Корінь, який `normalize` відкидає (тека всередині `Library`), а адаптер зберігає, — міграція цілком не пише нічого."""
        bad = os.path.join(self.home, 'Library', 'work')
        self.config(design_work_roots={'seo': bad})
        p = self.plan()
        self.assertEqual(p['status'], 'abort-tracks-parity')
        self.assertIsNone(p['space_json'])
        self.assertEqual(p['secrets'], {})

    def test_tracks_parity_abort_foreign_space_root(self):
        """Корінь напрямку лежить усередині ІНШОГО простору реєстру: у явних напрямках `serve` його скине, адаптер — ні."""
        other = os.path.join(self.tmp, 'other-space')
        os.makedirs(other)
        self._write(os.path.join(self.deai, 'spaces.json'), {'version': 1, 'current': 'legacy', 'spaces': [
            {'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': True},
            {'id': 'other', 'path': other, 'integrations': False}]})
        self.config(design_work_roots={'seo': os.path.join(other, 'work')})
        self.assertEqual(self.plan()['status'], 'abort-tracks-parity')

    # --- поправка контролера: невідомі значення напрямку
    def test_tracks_unknown_values_task_condition(self):
        """(а): задача з `track`/`profile` не з переліку мігрованих id (інший регістр, порожнє, нема) — напрямки НЕ мігрують."""
        for tid, task in (('x1', {'track': 'Seo'}), ('x2', {'profile': 'zzz'}), ('x3', {'title': 'без напрямку'}),
                          ('x4', {'track': ''}), ('x5', {'track': None, 'profile': None}), ('x6', {'track': 5})):
            with self.subTest(task=task):
                cfg = self.config()
                cfg['tasks'][tid] = dict(task, dir=os.path.join(self.home, 'work', tid))
                self._write(self.tasks_path, cfg)
                p = self.plan()
                self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', False, 'tracks-unknown-values'))
                self.assertNotIn('tracks', p['space_json'])
                self.assertEqual(len(p['space_json']['modules']), 3)              # ролі мігрують далі
                self.assertFalse(p['space_json']['migrations']['liga-4d3a']['tracks'])

    def test_tracks_unknown_values_default_root_condition(self):
        """(б): корінь дефолтного `united` ≠ спільному кореню адаптера — нова задача з невідомим значенням лягла б в інше місце."""
        self.config(design_work_roots={'united': os.path.join(self.home, 'work', 'united'), 'custom-x': os.path.join(self.home, 'work', 'custom')})
        p = self.plan()
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', False, 'tracks-unknown-values'))
        self.assertEqual(len(p['space_json']['modules']), 3)

    def test_tracks_migrate_when_default_root_equals_shared(self):
        shared = os.path.join(self.home, 'work', 'shared')
        self.config(design_work_roots={'united': shared, 'custom-x': os.path.join(self.home, 'work', 'custom')})
        p = self.plan()
        self.assertTrue(p['tracks'])
        self.assertIsNone(p['tracks_reason'])

    # --- провайдер
    def test_provider_check_runs_in_memory_and_aborts(self):
        before = self.snapshot_tree()
        seen = []
        real = self.dm._provider_for

        def spy(role, space, get_cat=None, explicit_override=None):
            seen.append((role, explicit_override is not None))
            return real(role, space, get_cat, explicit_override)
        with self.mock.patch.object(self.dm, '_provider_for', spy):
            p = self.plan()
        self.assertEqual(p['status'], 'ready')
        self.assertEqual(seen, [('tracker', True), ('dashboard', True), ('notify', True)])      # у памʼяті, кожна мігрована роль
        self.assertEqual(self.snapshot_tree(), before)
        with self.mock.patch.object(self.dm, '_provider_for', return_value=None):
            p = self.plan()
        self.assertEqual(p['status'], 'abort-provider')
        self.assertIsNone(p['space_json'])
        self.assertEqual(p['secrets'], {})
        with self.mock.patch.object(self.dm, '_provider_for', lambda *a, **k: self.dm.catalog()['supabase-teams']):
            self.assertEqual(self.plan()['status'], 'abort-provider')                           # інший модуль, ніж розрахований

    # --- облікові
    def test_credentials_same_sources_as_install_config(self):
        """Jira: пошта й токен незалежно (оточення → файл); Supabase — ціла пара з одного джерела. Ті самі функції, що в сервері."""
        import install_config
        fb = os.path.join(self.home, '.claude', 'pipeline-feedback')
        self._write(os.path.join(fb, 'jira-token'), 'jira_file_token_alpha\n')
        os.environ.pop('JIRA_TOKEN')                                           # пошта — з оточення, токен — з файла
        p = self.plan()
        self.assertEqual(p['space_json']['modules']['jira-tracker']['settings']['email'], self.JIRA_EMAIL)
        self.assertEqual(p['secrets']['jira-tracker'], {'token': 'jira_file_token_alpha'})
        self.assertEqual((p['space_json']['modules']['jira-tracker']['settings']['base'], p['space_json']['modules']['jira-tracker']['settings']['email'],
                          p['secrets']['jira-tracker']['token']), install_config.jira_config())
        # Supabase: у корені лише адреса, ключ в оточенні — пара НЕ змішується; без пари з жодного джерела ролей нема
        self.config(supabase=False, supabase_url=self.SB_URL)
        os.environ['SUPABASE_KEY'] = 'sb_env_key_alpha'
        self.assertEqual(self.plan()['roles']['dashboard']['reason'], 'no-supabase')
        os.environ['SUPABASE_URL'] = 'https://sb-env.example.com'
        p = self.plan()
        self.assertEqual((p['space_json']['modules']['supabase-teams']['settings']['url'], p['secrets']['supabase-teams']['key']),
                         ('https://sb-env.example.com', 'sb_env_key_alpha'))
        self.assertEqual((p['space_json']['modules']['supabase-teams']['settings']['url'], p['secrets']['supabase-teams']['key']),
                         install_config.supabase_config())

    # --- звіт
    def test_report_has_no_secret_values(self):
        for p in (self.plan(),):
            text = self.lm.report(p)
            for secret in (self.SB_KEY, self.JIRA_TOKEN, self.SB_URL, self.JIRA_BASE, self.JIRA_EMAIL):
                self.assertNotIn(secret, text)
            self.assertIn('ready', text)
            self.assertIn('token', text)                                       # імена ключів — так
            self.assertIn('supabase-dashboard', text)
        self.registry(entry=False)
        self.assertIn('skip-no-liga', self.lm.report(self.plan()))

    def test_plan_never_raises(self):
        with self.mock.patch.object(self.lm, '_compute_tracks', side_effect=RuntimeError('sb_plan_key_alpha')):
            p = self.plan()
        self.assertEqual(p['status'], 'abort-internal')
        self.assertNotIn('sb_plan_key_alpha', repr(p))


if __name__ == '__main__':
    unittest.main()
