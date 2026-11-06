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


class _Stand(unittest.TestCase):
    """Спільний стенд Task 4–5 (4d-3a); Task 4 (4d-3a): чистий розрахунок `liga_migrate.plan()` — нічого не пишемо, секрети лише в `plan['secrets']`, `report()` без
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
                if f == '.lock':                      # замок міграції (`migrations/.lock`) — не стан: його створює будь-який запуск
                    continue
                p = os.path.join(base, f)
                with open(p, 'rb') as fh:
                    out[p] = fh.read()
        return out

    def plan(self, **kw):
        return self.lm.plan(**kw)

class PlanTest(_Stand):
    """Task 4 (4d-3a): тести `plan()` на спільному стенді `_Stand`."""

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
    def _assert_parity_miss(self, p):
        """Паритету нема: напрямки не мігрують (`tracks-parity`), ролі мігрують далі, `tracks` у `space_json` не з'являється."""
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', False, 'tracks-parity'))
        self.assertNotIn('tracks', p['space_json'])
        self.assertEqual(len(p['space_json']['modules']), 3)
        self.assertEqual(sorted(p['secrets']), ['jira-tracker', 'supabase-dashboard', 'supabase-teams'])

    def test_tracks_parity_miss(self):
        """Корінь, який `normalize` відкидає (тека всередині `Library`), а адаптер зберігає, — `tracks-parity`, не обвал міграції."""
        bad = os.path.join(self.home, 'Library', 'work')
        self.config(design_work_roots={'seo': bad})
        self._assert_parity_miss(self.plan())

    def test_tracks_parity_miss_relative_shared_root(self):
        """Відносний `design_work_root`: адаптер читає його від cwd, `normalize` — від теки простору → `tracks-parity`."""
        self.config(design_work_root='relative/shared')
        self._assert_parity_miss(self.plan())

    def test_tracks_parity_miss_foreign_space_root(self):
        """Корінь напрямку лежить усередині ІНШОГО простору реєстру: у явних напрямках `serve` його скине, адаптер — ні."""
        other = os.path.join(self.tmp, 'other-space')
        os.makedirs(other)
        self._write(os.path.join(self.deai, 'spaces.json'), {'version': 1, 'current': 'legacy', 'spaces': [
            {'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': True},
            {'id': 'other', 'path': other, 'integrations': False}]})
        self.config(design_work_roots={'seo': os.path.join(other, 'work')})
        self._assert_parity_miss(self.plan())

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

    def test_tracks_unknown_values_key_outside_id_re(self):
        """(в): ключ `design_work_roots`/`profile_repos` поза `ID_RE` не стає напрямком — напрямки НЕ мігрують, ролі — так."""
        work = os.path.join(self.home, 'work')
        for extra in ({'design_work_roots': {'Foo': os.path.join(work, 'foo'), 'custom-x': os.path.join(work, 'custom')}},
                      {'profile_repos': {'Bar': self.REPO_U, 'united': self.REPO_U}}):
            with self.subTest(extra=sorted(extra)):
                self.config(**extra)
                p = self.plan()
                self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', False, 'tracks-unknown-values'))
                self.assertEqual(len(p['space_json']['modules']), 3)

    def test_skip_nothing(self):
        """Жодна роль і не напрямки: `skip-nothing`, `space_json` = None (позначку не пишемо); достатньо ролі чи напрямків — `ready`."""
        self.config(supabase=False, jira=False, design_work_root=None)       # нема облікових; ключ `design_work_root` знімаємо
        cfg = self.cfg
        cfg['tasks']['x'] = {'dir': os.path.join(self.home, 'work', 'x')}    # задача без напрямку → tracks-unknown-values
        self._write(self.tasks_path, cfg)
        p = self.plan()
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('skip-nothing', False, 'tracks-unknown-values'))
        self.assertIsNone(p['space_json'])
        self.assertEqual(p['secrets'], {})
        self.assertFalse(any(r['migrate'] for r in p['roles'].values()))
        self.assertIn('skip-nothing', self.lm.report(p))
        cfg['tasks'].pop('x')
        self._write(self.tasks_path, cfg)
        self.assertEqual(self.plan()['status'], 'ready')                     # напрямки мігрують — не skip-nothing
        self.config(supabase=False, jira=True, **{'tasks': {'x': {'dir': 'd'}}})
        p = self.plan()
        self.assertEqual((p['status'], p['tracks']), ('ready', False))       # напрямків нема, але роль tracker є

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


# ================================================================================================ Task 5: запис, відкат, старт

class _WriteStand(_Stand):
    """Стенд запису: перехоплення stdout/stderr, пошук значень секретів у ВСІХ виходах, CLI `bin/migrate_liga.py`."""

    def setUp(self):
        super().setUp()
        import io
        import contextlib
        self.io, self.contextlib = io, contextlib
        self.secret_values = (self.SB_KEY, self.JIRA_TOKEN)
        self.cap = []                                  # усе, що надруковано (stdout+stderr) за час тесту

    def cli(self, *argv):
        import importlib.util
        spec = importlib.util.spec_from_file_location('liga_migrate_cli', os.path.join(os.path.dirname(_HERE), 'bin', 'migrate_liga.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out, err = self.io.StringIO(), self.io.StringIO()
        with self.contextlib.redirect_stdout(out), self.contextlib.redirect_stderr(err):
            code = mod.main(list(argv))
        self.cap.extend([out.getvalue(), err.getvalue()])
        return code, out.getvalue(), err.getvalue()

    def quiet(self, fn, *a, **kw):
        err = self.io.StringIO()
        with self.contextlib.redirect_stderr(err):
            r = fn(*a, **kw)
        self.cap.append(err.getvalue())
        return r, err.getvalue()

    def read(self, *parts):
        with open(os.path.join(*parts), 'rb') as f:
            return f.read()

    def read_json(self, *parts):
        return json.loads(self.read(*parts).decode('utf-8'))

    def space_path(self):
        return os.path.join(self.space_dir, 'space.json')

    def secrets_path(self):
        return os.path.join(self.deai, 'secrets.json')

    def backups(self):
        d = os.path.join(self.deai, 'backups')
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def sha(self, data):
        import hashlib
        return hashlib.sha256(data).hexdigest()

    def assert_no_secrets(self, *texts):
        for text in texts:
            for v in self.secret_values:
                self.assertNotIn(v, text)

    def assert_no_secrets_in_logs(self):
        """⛔ Значень секретів нема ні в `last.json`, ні в маніфестах бекапів, ні в `space.json`, ні в усьому надрукованому."""
        for base, _d, files in os.walk(self.deai):
            for f in files:
                if f in ('last.json', 'manifest.json'):
                    self.assert_no_secrets(self.read(base, f).decode('utf-8'))
        if os.path.exists(self.space_path()):
            self.assert_no_secrets(self.read(self.space_path()).decode('utf-8'))
        self.assert_no_secrets(*self.cap)

    def tree_without_logs(self):
        t = self.snapshot_tree()
        return {k: v for k, v in t.items() if os.sep + 'migrations' + os.sep not in k}


class RunTest(_WriteStand):
    """Task 5 (4d-3a): `run()` — бекап, секрети, ОДИН запис `space.json` з позначкою, `last.json`; усе в тимчасовому DEAI_HOME."""

    ORIG_SPACE = b'{"name": "Liga",\n  "color": "#112233",\n  "x": {"k": [1,  2]}}\n'

    def seed_space(self):
        self._write(self.space_path(), self.ORIG_SPACE.decode('utf-8'))
        os.chmod(self.space_path(), 0o644)
        self._write(self.secrets_path(), json.dumps({'other': {'m': {'k': 'other_value_alpha'}}}))
        os.chmod(self.secrets_path(), 0o644)

    def test_backup_content_modes_manifest(self):
        self.seed_space()
        old_tasks, old_reg = self.read(self.tasks_path), self.read(self.deai, 'spaces.json')
        old_space, old_secrets = self.read(self.space_path()), self.read(self.secrets_path())
        self.assertEqual(self.lm.run(), 'done')
        names = self.backups()
        self.assertEqual(len(names), 1)
        self.assertRegex(names[0], self.lm.STAMP_RE.pattern)
        b = os.path.join(self.deai, 'backups', names[0])
        self.assertEqual(os.stat(b).st_mode & 0o777, 0o700)
        self.assertEqual(sorted(os.listdir(b)), ['manifest.json', 'secrets.json', 'space.json', 'spaces.json', 'tasks.json'])
        for fname, orig in (('tasks.json', old_tasks), ('spaces.json', old_reg), ('space.json', old_space), ('secrets.json', old_secrets)):
            self.assertEqual(self.read(b, fname), orig, fname)
            self.assertEqual(os.stat(os.path.join(b, fname)).st_mode & 0o777, 0o600, fname)
        m = self.read_json(b, 'manifest.json')
        self.assertEqual(m['version'], self.lm._tool_version())
        self.assertEqual(m['space_id'], 'legacy')
        self.assertEqual(sorted(m['files']), ['secrets.json', 'space.json', 'spaces.json', 'tasks.json'])
        for fname, meta in m['files'].items():
            self.assertEqual(meta['sha256'], self.sha(self.read(b, fname)), fname)
        self.assertEqual(m['files']['space.json']['source'], self.space_path())
        self.assertEqual(m['files']['space.json']['mode'], 0o644)
        self.assertEqual(os.stat(self.secrets_path()).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.deai).st_mode & 0o777, 0o700)
        self.assert_no_secrets_in_logs()

    def test_backup_without_space_and_secrets(self):
        self.assertEqual(self.lm.run(), 'done')
        b = os.path.join(self.deai, 'backups', self.backups()[0])
        self.assertEqual(sorted(os.listdir(b)), ['manifest.json', 'spaces.json', 'tasks.json'])
        self.assertEqual(sorted(self.read_json(b, 'manifest.json')['files']), ['spaces.json', 'tasks.json'])

    def test_backup_stamp_suffix_when_dir_exists(self):
        with self.mock.patch.object(self.lm.time, 'strftime', lambda fmt: '20261106-120000' if 'T' not in fmt else '2026-11-06T12:00:00'):
            os.makedirs(os.path.join(self.deai, 'backups', '20261106-120000-liga-4d3a'), mode=0o700)
            self.assertEqual(self.lm.run(), 'done')
        self.assertEqual(self.backups(), ['20261106-120000-liga-4d3a', '20261106-120000-liga-4d3a-2'])
        self.assertEqual(self.read_json(self.space_path())['migrations']['liga-4d3a']['backup'], '20261106-120000-liga-4d3a-2')

    def test_mark_merge_and_secrets(self):
        self.seed_space()
        self.assertEqual(self.lm.run(), 'done')
        sj = self.read_json(self.space_path())
        self.assertEqual((sj['name'], sj['color'], sj['x']), ('Liga', '#112233', {'k': [1, 2]}))
        self.assertEqual(sorted(sj['modules']), ['jira-tracker', 'supabase-dashboard', 'supabase-teams'])
        self.assertIn('custom-x', [t['id'] for t in sj['tracks']])
        self.assertEqual(sj['default_track'], 'united')
        mark = sj['migrations']['liga-4d3a']
        self.assertEqual(sorted(mark), ['at', 'backup', 'roles', 'tracks'])
        self.assertRegex(mark['at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$')
        self.assertEqual(mark['backup'], self.backups()[0])
        self.assertEqual(mark['roles'], ['tracker', 'dashboard', 'notify'])
        self.assertTrue(mark['tracks'])
        sec = self.read_json(self.secrets_path())
        self.assertEqual(sec['legacy'], {'jira-tracker': {'token': self.JIRA_TOKEN}, 'supabase-dashboard': {'key': self.SB_KEY},
                                         'supabase-teams': {'key': self.SB_KEY}})
        self.assertEqual(sec['other'], {'m': {'k': 'other_value_alpha'}})
        self.assertEqual(os.stat(self.space_path()).st_mode & 0o777, 0o644)

    def test_new_space_json_is_public_mode(self):
        self.assertEqual(self.lm.run(), 'done')
        self.assertEqual(os.stat(self.space_path()).st_mode & 0o777, 0o644)

    def test_last_json_has_no_secret_values(self):
        self.assertEqual(self.lm.run(), 'done')
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['status'], last['space_id'], last['roles'], last['tracks']), ('done', 'legacy', ['tracker', 'dashboard', 'notify'], True))
        self.assertEqual(last['secrets'], {'jira-tracker': ['token'], 'supabase-dashboard': ['key'], 'supabase-teams': ['key']})
        self.assertEqual(last['backup'], self.backups()[0])
        self.assert_no_secrets_in_logs()

    def test_second_run_is_skip_done_and_writes_nothing(self):
        self.assertEqual(self.lm.run(), 'done')
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(), 'skip-done')
        self.assertEqual(self.snapshot_tree(), before)

    def test_non_ready_statuses_write_nothing(self):
        """Усе, крім `ready`: статус назад, диск не змінено ні на байт (включно з `last.json`)."""
        self.registry(entry=False)
        self.assertEqual(self.lm.run(), 'skip-no-liga')
        self.registry()
        self.space_json({'migrations': {'liga-4d3a': {'held': True}}})
        self.assertEqual(self.lm.run(), 'skip-held')
        self.space_json('not json')
        self.assertEqual(self.lm.run(), 'skip-space-json-unreadable')
        self.assertEqual(self.backups(), [])
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'migrations', 'last.json')))
        self.assertFalse(os.path.exists(self.secrets_path()))
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'migrations')))     # ⛔ ні теки, ні `.lock`: дім не-ЛІГА лишається чистим

    def test_skip_nothing_writes_nothing(self):
        """⛔ `skip-nothing`: ні бекапу, ні позначки, ні `last.json`; наступний запуск перевірить знову."""
        self.config(supabase=False, jira=False, design_work_root=None)
        cfg = self.cfg
        cfg['tasks']['x'] = {'dir': os.path.join(self.home, 'work', 'x')}
        self._write(self.tasks_path, cfg)
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(), 'skip-nothing')
        self.assertEqual(self.snapshot_tree(), before)
        self.assertEqual(self.backups(), [])
        self.assertFalse(os.path.exists(self.space_path()))

    def test_abort_provider_writes_only_log(self):
        before = self.tree_without_logs()
        with self.mock.patch.object(self.dm, '_provider_for', lambda *a, **k: None):
            self.assertEqual(self.lm.run(), 'abort-provider')
        self.assertEqual(self.tree_without_logs(), before)
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['status'], 'abort-provider')

    def test_backup_failure_writes_nothing(self):
        self.seed_space()
        with open(os.path.join(self.deai, 'backups'), 'w') as f:      # на місці теки бекапів — файл: тека не створюється
            f.write('x')
        before = self.tree_without_logs()
        self.assertEqual(self.lm.run(), 'abort-backup')
        self.assertEqual(self.tree_without_logs(), before)
        self.assertEqual(self.read(self.space_path()), self.ORIG_SPACE)
        self.assertEqual(self.read_json(self.secrets_path()), {'other': {'m': {'k': 'other_value_alpha'}}})
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['status'], 'abort-backup')

    def test_backup_copy_failure_removes_partial_dir_and_writes_nothing(self):
        self.seed_space()
        before = self.tree_without_logs()
        with self.mock.patch.object(self.lm.shutil, 'copyfile', side_effect=OSError('disk')):
            self.assertEqual(self.lm.run(), 'abort-backup')
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.tree_without_logs(), before)

    def test_failure_between_secrets_and_space_then_recovery(self):
        self.seed_space()
        with self.mock.patch.object(self.lm, '_write_space', side_effect=OSError('boom')):
            self.assertEqual(self.lm.run(), 'abort-write')
        self.assertEqual(self.read(self.space_path()), self.ORIG_SPACE)              # space.json не змінено
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['jira-tracker'], {'token': self.JIRA_TOKEN})   # секрети вже є
        self.assertNotIn('migrations', self.read_json(self.space_path()))
        self.assertEqual(self.lm.plan()['status'], 'ready')                          # позначки нема → наступний запуск починає заново
        self.assertEqual(self.lm.run(), 'done')
        sj = self.read_json(self.space_path())
        self.assertIn('liga-4d3a', sj['migrations'])
        self.assertEqual(sorted(sj['modules']), ['jira-tracker', 'supabase-dashboard', 'supabase-teams'])
        self.assertEqual(self.lm.run(), 'skip-done')
        self.assert_no_secrets_in_logs()

    def test_failure_in_secrets_leaves_space_untouched_then_recovers(self):
        self.seed_space()
        err = self.dm.ModuleError('unwritable', message='secrets.json: OSError')
        with self.mock.patch.object(self.dm, 'write_secrets', side_effect=err):
            self.assertEqual(self.lm.run(), 'abort-secrets')
        self.assertEqual(self.read(self.space_path()), self.ORIG_SPACE)
        self.assertEqual(self.lm.run(), 'done')

    def test_secrets_written_before_space_json(self):
        """Порядок: секрети ДО `space.json` (запис `space.json` бачить секрети вже на диску)."""
        seen = []
        real = self.lm._write_space

        def spy(path, data):
            seen.append(os.path.exists(self.secrets_path()) and 'legacy' in self.read_json(self.secrets_path()))
            return real(path, data)
        with self.mock.patch.object(self.lm, '_write_space', spy):
            self.assertEqual(self.lm.run(), 'done')
        self.assertEqual(seen, [True])

    def test_concurrent_edit_between_plan_and_write_is_kept(self):
        """Правка `space.json` ПІСЛЯ `plan()` (тут — під час запису секретів) не губиться: запис зливається з поточним диском."""
        self.seed_space()
        real = self.dm.write_secrets
        done = []

        def racing(*a, **kw):
            r = real(*a, **kw)
            if not done:
                done.append(1)
                cur = self.read_json(self.space_path())
                cur['foreign'] = {'keep': 7}
                cur['modules'] = {'custom-mod': {'enabled': False}}
                self._write(self.space_path(), cur)
            return r
        with self.mock.patch.object(self.dm, 'write_secrets', racing):
            self.assertEqual(self.lm.run(), 'done')
        sj = self.read_json(self.space_path())
        self.assertEqual(sj['foreign'], {'keep': 7})
        self.assertEqual(sj['modules']['custom-mod'], {'enabled': False})
        self.assertEqual(sj['name'], 'Liga')
        for mid in ('jira-tracker', 'supabase-dashboard', 'supabase-teams'):
            self.assertIn(mid, sj['modules'])
        self.assertIn('liga-4d3a', sj['migrations'])

    def test_mark_added_concurrently_wins(self):
        real = self.dm.write_secrets

        def racing(*a, **kw):
            r = real(*a, **kw)
            self._write(self.space_path(), {'migrations': {'liga-4d3a': {'held': True}}})
            return r
        with self.mock.patch.object(self.dm, 'write_secrets', racing):
            self.assertEqual(self.lm.run(), 'skip-done')
        self.assertEqual(self.read_json(self.space_path()), {'migrations': {'liga-4d3a': {'held': True}}})

    def test_home_must_match_deai_home(self):
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(home=os.path.join(self.tmp, 'elsewhere')), 'abort-internal')
        self.assertEqual(self.snapshot_tree(), before)
        self.assertEqual(self.lm.run(home=self.deai), 'done')

    def test_run_never_raises(self):
        with self.mock.patch.object(self.lm, '_backup', side_effect=RuntimeError(self.SB_KEY)):
            self.assertEqual(self.lm.run(), 'abort-internal')
        self.assert_no_secrets_in_logs()

    def test_skip_path_in_git_persists_reason_under_separate_key(self):
        """Постійний пропуск: код і підказка лишаються в `last.json` (ключ `skip`), справжній звіт не затирається; `status` їх показує."""
        self.lm._write_last({'status': 'done', 'reason': 'real report'})
        os.makedirs(os.path.join(self.space_dir, '.git'))
        before = self.tree_without_logs()
        self.assertEqual(self.lm.run(), 'skip-path-in-git')
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['status'], last['reason']), ('done', 'real report'))          # справжній звіт на місці
        self.assertEqual(last['skip']['status'], 'skip-path-in-git')
        self.assertIn('git', last['skip']['hint'])
        self.assertEqual(self.tree_without_logs(), before)                                   # крім last.json — нічого
        self.assertEqual(self.lm.run(), 'skip-path-in-git')                                  # повтор не churn-ить файл
        code, out, _ = self.cli('status')
        self.assertIn('skip-path-in-git', out)
        self.assertIn('що робити', out)
        code, out, _ = self.cli('run')
        self.assertEqual(code, 1)
        self.assertIn('що робити', out)
        os.rmdir(os.path.join(self.space_dir, '.git'))                                       # вийшло з git → мігрує, ключ skip зникає
        self.assertEqual(self.lm.run(), 'done')
        self.assertNotIn('skip', self.read_json(self.deai, 'migrations', 'last.json'))

    def test_abort_changed_when_registry_path_moves_between_plan_and_write(self):
        other = os.path.join(self.tmp, 'other-space')
        os.makedirs(other)
        entry = {'id': 'legacy', 'path': other, 'legacy': True, 'integrations': True}
        before = self.tree_without_logs()
        with self.mock.patch.object(self.lm, '_liga_entry', lambda home: entry):
            self.assertEqual(self.lm.run(), 'abort-changed')
        self.assertEqual(self.tree_without_logs(), before)                       # ні бекапу, ні секретів, ні space.json
        self.assertEqual(os.listdir(other), [])
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['status'], 'abort-changed')

    def test_plan_returns_path_used(self):
        self.assertEqual(self.lm.plan()['space_path'], self.space_dir)

    def test_lock_busy_by_other_process_skips_without_writing(self):
        import fcntl
        os.makedirs(os.path.join(self.deai, 'migrations'), mode=0o700)
        fd = os.open(os.path.join(self.deai, 'migrations', '.lock'), os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(), 'skip-busy')
        self.assertEqual(self.lm.restore('20260101-000000-liga-4d3a'), 'skip-busy')
        self.assertEqual(self.snapshot_tree(), before)
        st, _err = self.quiet(self.lm.startup)
        self.assertEqual(st, 'skip-busy')                                          # старт не чекає
        self.assertEqual(os.stat(os.path.join(self.deai, 'migrations', '.lock')).st_mode & 0o777, 0o600)

    def test_flock_other_errors_are_abort_lock_not_busy(self):
        """⛔ «Зайнято» — лише EWOULDBLOCK/EAGAIN; `ENOLCK` (файлова система без flock) — видимий `abort-lock`, нічого не записано."""
        import errno
        for code in (errno.EWOULDBLOCK, errno.EAGAIN):                             # справжня зайнятість — як і раніше skip-busy
            with self.mock.patch('fcntl.flock', side_effect=OSError(code, 'busy')):
                self.assertEqual(self.lm.run(), 'skip-busy')
        self.assertEqual(self.backups(), [])
        with self.mock.patch('fcntl.flock', side_effect=OSError(errno.ENOLCK, 'no locks')):
            st, _err = self.quiet(self.lm.startup)
            self.assertEqual(st, 'abort-lock')
            self.assertEqual(self.lm.run(), 'abort-lock')
            self.assertEqual(self.lm.restore('20260101-000000-liga-4d3a'), 'abort-lock')
        self.assertEqual(self.backups(), [])
        self.assertFalse(os.path.exists(self.space_path()))
        self.assertFalse(os.path.exists(self.secrets_path()))
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual(last['status'], 'abort-lock')
        self.assertIn('abort-lock', self.lm.status_text(self.lm.status()))
        self.assertEqual(self.lm.run(), 'done')                                    # лише flock відновився — міграція доходить до кінця

    def test_ready_creates_lock_dir_but_non_ready_does_not(self):
        self.registry(entry=False)
        self.assertEqual(self.lm.run(), 'skip-no-liga')
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'migrations')))
        self.registry()
        self.assertEqual(self.lm.run(), 'done')
        self.assertTrue(os.path.exists(os.path.join(self.deai, 'migrations', '.lock')))

    def test_nested_run_during_write_is_busy_and_secrets_written_once(self):
        real = self.dm.write_secrets
        calls, inner = [], []

        def spy(sid, mid, patch, *a, **kw):
            calls.append(mid)
            if not inner:
                inner.append(self.lm.run())                                        # «другий процес» посеред першого
            return real(sid, mid, patch, *a, **kw)
        with self.mock.patch.object(self.dm, 'write_secrets', spy):
            self.assertEqual(self.lm.run(), 'done')
        self.assertEqual(inner, ['skip-busy'])
        self.assertEqual(sorted(calls), ['jira-tracker', 'supabase-dashboard', 'supabase-teams'])     # рівно раз
        self.assertEqual(len(self.backups()), 1)

    def test_two_threads_one_done_secrets_once(self):
        import threading
        real = self.dm.write_secrets
        calls, res = [], []
        gate = threading.Event()

        def slow(sid, mid, patch, *a, **kw):
            calls.append(mid)
            gate.wait(2)
            return real(sid, mid, patch, *a, **kw)
        with self.mock.patch.object(self.dm, 'write_secrets', slow):
            t1 = threading.Thread(target=lambda: res.append(self.lm.run()))
            t1.start()
            while not calls:
                pass
            res.append(self.lm.run())                                              # перший тримає замок, поки gate закритий
            gate.set()
            t1.join(10)
        self.assertEqual(sorted(res), ['done', 'skip-busy'])
        self.assertEqual(sorted(calls), ['jira-tracker', 'supabase-dashboard', 'supabase-teams'])
        self.assertEqual(len(self.backups()), 1)

    def test_mark_found_inside_lock_before_any_secret(self):
        """`plan()` рахується під замком: позначка, що зʼявилась ДО запуску, не дає записати жодного секрету."""
        self._write(self.space_path(), {'migrations': {'liga-4d3a': {'at': 'x'}}})
        with self.mock.patch.object(self.dm, 'write_secrets', side_effect=AssertionError('secret written')):
            self.assertEqual(self.lm.run(), 'skip-done')
        self.assertFalse(os.path.exists(self.secrets_path()))

    def test_backup_source_changed_mid_copy_aborts(self):
        self.seed_space()
        real = self.lm.shutil.copyfile

        def mutating(src, dst, *a, **kw):
            r = real(src, dst, *a, **kw)
            if os.path.basename(src) == 'space.json':
                with open(src, 'ab') as f:
                    f.write(b' ')
            return r
        before = self.tree_without_logs()
        with self.mock.patch.object(self.lm.shutil, 'copyfile', mutating):
            self.assertEqual(self.lm.run(), 'abort-backup')
        with open(self.space_path(), 'wb') as f:
            f.write(self.ORIG_SPACE)
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.tree_without_logs(), before)

    def test_backup_copy_corrupted_aborts(self):
        real = self.lm.shutil.copyfile

        def corrupting(src, dst, *a, **kw):
            r = real(src, dst, *a, **kw)
            with open(dst, 'ab') as f:
                f.write(b' ')
            return r
        with self.mock.patch.object(self.lm.shutil, 'copyfile', corrupting):
            self.assertEqual(self.lm.run(), 'abort-backup')
        self.assertEqual(self.backups(), [])
        self.assertFalse(os.path.exists(self.secrets_path()))

    def test_backup_source_vanishes_mid_backup_aborts(self):
        real = self.lm.shutil.copyfile

        def vanishing(src, dst, *a, **kw):
            r = real(src, dst, *a, **kw)
            if os.path.basename(src) == 'spaces.json':
                os.rename(src, src + '.gone')
            return r
        with self.mock.patch.object(self.lm.shutil, 'copyfile', vanishing):
            self.assertEqual(self.lm.run(), 'abort-backup')
        os.rename(os.path.join(self.deai, 'spaces.json.gone'), os.path.join(self.deai, 'spaces.json'))
        self.assertEqual(self.backups(), [])
        self.assertFalse(os.path.exists(self.secrets_path()))

    def test_backup_required_source_missing_aborts(self):
        """`tasks.json`/`spaces.json` обовʼязкові: їхня відсутність у момент бекапу — збій, а не мовчазний пропуск."""
        for name in ('legacy-tasks.json', 'spaces.json'):
            with self.mock.patch.object(self.lm.os.path, 'isfile', lambda p, n=name: False if os.path.basename(p) == n else os.path.exists(p)):
                with self.assertRaises(OSError):
                    self.lm._backup(self.deai, 'legacy', self.space_dir)
            self.assertEqual(self.backups(), [])

    def test_status_lists_only_backups_with_manifest(self):
        self.assertEqual(self.lm.run(), 'done')
        good = self.backups()[0]
        junk = os.path.join(self.deai, 'backups', '20260101-000000-liga-4d3a')
        os.makedirs(junk)                                                          # недописана тека без маніфесту
        self.assertEqual(self.lm.status()['backups'], [good])
        self.assertNotIn('20260101-000000-liga-4d3a', self.cli('status')[1])

    def test_tracks_empty_list_is_present(self):
        self.space_json({'tracks': [], 'default_track': 'zzz'})
        p = self.lm.plan()
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', False, 'tracks-present'))
        self.assertEqual(self.lm.run(), 'done')
        sj = self.read_json(self.space_path())
        self.assertEqual((sj['tracks'], sj['default_track']), ([], 'zzz'))

    def test_userinfo_urls_are_not_migrated(self):
        """Зараз форму адреси стереже `install_config` (userinfo не проходить регулярку); `bad-url` — другий рубіж у самій міграції."""
        ic = self.lm.install_config
        with self.mock.patch.object(ic, 'jira_from', lambda cfg: ('https://user:pass@jira.example.com', self.JIRA_EMAIL, self.JIRA_TOKEN)):
            p = self.lm.plan()
        self.assertEqual((p['roles']['tracker']['migrate'], p['roles']['tracker']['reason']), (False, 'bad-url'))
        self.assertNotIn('jira-tracker', p['secrets'])
        self.assertNotIn('pass', repr(p['space_json']))
        self.assertNotIn('pass', self.lm.report(p))
        self.assertTrue(p['roles']['dashboard']['migrate'])
        with self.mock.patch.object(ic, 'supabase_from', lambda cfg: ('https://k:v@sb.example.com', self.SB_KEY)):
            p = self.lm.plan()
        for role in ('dashboard', 'notify'):
            self.assertEqual((p['roles'][role]['migrate'], p['roles'][role]['reason']), (False, 'bad-url'))
            self.assertNotIn(self.lm.ROLE_MODULES[1 if role == 'dashboard' else 2][1], p['secrets'])
        self.assertTrue(p['roles']['tracker']['migrate'])

    # --- CLI
    def test_cli_status_dry_run_run(self):
        code, out, _ = self.cli('status')
        self.assertEqual(code, 0)
        self.assertIn('позначки нема', out)
        code, out, _ = self.cli('dry-run')
        self.assertEqual(code, 0)
        self.assertIn('ready', out)
        self.assertEqual(out.strip(), self.lm.report(self.lm.plan()).strip())
        self.assertEqual(self.backups(), [])                                          # dry-run нічого не пише
        self.assertFalse(os.path.exists(self.space_path()))
        code, out, _ = self.cli('run')
        self.assertEqual(code, 0)
        self.assertIn('done', out)
        code, out, _ = self.cli('run')
        self.assertEqual((code, 'skip-done' in out), (0, True))
        code, out, _ = self.cli('status')
        self.assertIn('позначка:', out)
        self.assertIn(self.backups()[0], out)
        self.assert_no_secrets_in_logs()

    def test_cli_exit_codes(self):
        self.registry(entry=False)
        self.assertEqual(self.cli('run')[0], 0)                                        # нема простору ЛІГА — не помилка
        self.registry()
        os.makedirs(os.path.join(self.space_dir, '.git'))
        self.assertEqual(self.cli('run')[0], 1)                                        # тека в git — потрібна увага
        os.rmdir(os.path.join(self.space_dir, '.git'))
        with self.mock.patch.object(self.dm, '_provider_for', lambda *a, **k: None):
            self.assertEqual(self.cli('dry-run')[0], 1)
        self.assertEqual(self.cli('restore', '../nope')[0], 1)
        self.assert_no_secrets_in_logs()


class RestoreTest(_WriteStand):
    """Task 5 (4d-3a): `restore()` — побайтно, з перевіркою sha256, без чужих файлів, відмова на підроблене імʼя."""

    ORIG_SPACE = b'{"name": "Liga",\n  "x": [1,  2]}\n'
    ORIG_SECRETS = b'{"other": {"m": {"k": "other_value_alpha"}},\n "z": 1}\n'

    def migrate(self, seed=True):
        if seed:
            self._write(self.space_path(), self.ORIG_SPACE.decode('utf-8'))
            os.chmod(self.space_path(), 0o640)
            self._write(self.secrets_path(), self.ORIG_SECRETS.decode('utf-8'))
            os.chmod(self.secrets_path(), 0o600)
        self.assertEqual(self.lm.run(), 'done')
        return self.backups()[-1]

    def test_restore_byte_for_byte(self):
        stamp = self.migrate()
        tasks, reg = self.read(self.tasks_path), self.read(self.deai, 'spaces.json')
        self.assertNotEqual(self.read(self.space_path()), self.ORIG_SPACE)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        self.assertEqual(self.read(self.space_path()), self.ORIG_SPACE)
        self.assertEqual(self.read(self.secrets_path()), self.ORIG_SECRETS)
        self.assertEqual(os.stat(self.space_path()).st_mode & 0o777, 0o640)
        self.assertEqual(os.stat(self.secrets_path()).st_mode & 0o777, 0o600)
        self.assertEqual((self.read(self.tasks_path), self.read(self.deai, 'spaces.json')), (tasks, reg))   # їх міграція не міняла
        self.assertEqual(self.lm.plan()['status'], 'ready')                          # позначки нема → мігрує знову
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['status'], 'restored')
        self.assert_no_secrets_in_logs()

    def test_restore_hold(self):
        stamp = self.migrate()
        self.assertEqual(self.lm.restore(stamp, hold=True), 'restored')
        sj = self.read_json(self.space_path())
        self.assertEqual(sj, {'name': 'Liga', 'x': [1, 2], 'migrations': {'liga-4d3a': {'held': True}}})
        self.assertEqual(self.read(self.secrets_path()), self.ORIG_SECRETS)
        self.assertEqual(self.lm.plan()['status'], 'skip-held')
        self.assertEqual(self.lm.run(), 'skip-held')

    def test_restore_when_backup_had_no_space_json(self):
        stamp = self.migrate(seed=False)
        self.assertTrue(os.path.exists(self.space_path()))
        self.assertEqual(self.lm.restore(stamp), 'restored')
        self.assertFalse(os.path.exists(self.space_path()))
        self.assertFalse(os.path.exists(self.secrets_path()))                       # секретів у бекапі теж не було
        self.assertEqual(self.lm.plan()['status'], 'ready')

    def test_restore_hold_when_backup_had_no_space_json(self):
        stamp = self.migrate(seed=False)
        self.assertEqual(self.lm.restore(stamp, hold=True), 'restored')
        self.assertEqual(self.read_json(self.space_path()), {'migrations': {'liga-4d3a': {'held': True}}})

    def test_restore_without_secrets_in_backup_keeps_foreign_secrets(self):
        stamp = self.migrate(seed=False)
        cur = self.read_json(self.secrets_path())
        cur['other-space'] = {'m': {'k': 'later_value_alpha'}}
        self._write(self.secrets_path(), cur)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        self.assertEqual(self.read_json(self.secrets_path()), {'other-space': {'m': {'k': 'later_value_alpha'}}})

    def test_refuses_bad_stamps(self):
        stamp = self.migrate()
        before = self.snapshot_tree()
        os.symlink(os.path.join(self.deai, 'backups', stamp), os.path.join(self.deai, 'backups', '20260101-000000-liga-4d3a'))
        before = self.snapshot_tree()
        for bad in (None, '', 5, '../' + stamp, stamp + '/..', os.path.join(self.deai, 'backups', stamp), stamp + '\n', 'nope',
                    stamp.replace('liga-4d3a', 'other'), '20990101-000000-liga-4d3a', '20260101-000000-liga-4d3a', '.', '..'):
            self.assertEqual(self.lm.restore(bad), 'refuse-stamp', repr(bad))
            self.assertEqual(self.lm.restore(bad, hold=True), 'refuse-stamp', repr(bad))
        self.assertEqual(self.snapshot_tree(), before)                              # символічний лінк на справжній бекап — теж відмова

    def test_refuses_tampered_backup_files_before_any_write(self):
        stamp = self.migrate()
        b = os.path.join(self.deai, 'backups', stamp)
        migrated = self.read(self.space_path())
        with open(os.path.join(b, 'secrets.json'), 'ab') as f:                      # підробка САМЕ секретів: space.json бекапу цілий
            f.write(b' ')
        self.assertEqual(self.lm.restore(stamp), 'refuse-tampered')
        self.assertEqual(self.read(self.space_path()), migrated)                    # нічого не відновлено — навіть цілий space.json
        with open(os.path.join(b, 'secrets.json'), 'wb') as f:
            f.write(self.ORIG_SECRETS)
        with open(os.path.join(b, 'space.json'), 'wb') as f:
            f.write(b'{"name": "Evil"}')
        self.assertEqual(self.lm.restore(stamp, hold=True), 'refuse-tampered')
        self.assertEqual(self.read(self.space_path()), migrated)

    def test_refuses_tampered_manifest(self):
        stamp = self.migrate()
        b = os.path.join(self.deai, 'backups', stamp)
        m = self.read_json(b, 'manifest.json')
        migrated = self.read(self.space_path())
        for mutate in (lambda x: x['files']['space.json'].update(sha256='0' * 64),
                       lambda x: x['files'].update({'../evil.json': {'sha256': 'a', 'mode': 420}}),
                       lambda x: x.pop('files'),
                       lambda x: x.update(migration='other')):
            bad = json.loads(json.dumps(m))
            mutate(bad)
            with open(os.path.join(b, 'manifest.json'), 'w') as f:
                json.dump(bad, f)
            self.assertEqual(self.lm.restore(stamp), 'refuse-tampered')
            self.assertEqual(self.read(self.space_path()), migrated)
        with open(os.path.join(b, 'manifest.json'), 'w') as f:
            f.write('not json')
        self.assertEqual(self.lm.restore(stamp), 'refuse-tampered')

    def test_manifest_paths_are_never_trusted(self):
        """Куди писати, береться з реєстру, а не з маніфесту: підроблений `space_path` нікуди не веде."""
        stamp = self.migrate()
        b = os.path.join(self.deai, 'backups', stamp)
        m = self.read_json(b, 'manifest.json')
        evil = os.path.join(self.tmp, 'evil')
        os.makedirs(evil)
        m['space_path'] = evil
        m['files']['space.json']['source'] = os.path.join(evil, 'space.json')
        with open(os.path.join(b, 'manifest.json'), 'w') as f:
            json.dump(m, f)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        self.assertEqual(os.listdir(evil), [])
        self.assertEqual(self.read(self.space_path()), self.ORIG_SPACE)

    def test_refuses_when_space_differs_or_missing(self):
        stamp = self.migrate()
        migrated = self.read(self.space_path())
        self.registry(entry=False)
        self.assertEqual(self.lm.restore(stamp), 'refuse-no-liga')
        self.registry()
        reg = self.read_json(self.deai, 'spaces.json')
        reg['spaces'][0]['id'] = 'other'
        reg['current'] = 'other'
        self._write(os.path.join(self.deai, 'spaces.json'), reg)
        self.assertEqual(self.lm.restore(stamp), 'refuse-no-liga')
        self.assertEqual(self.read(self.space_path()), migrated)

    def test_restore_keeps_foreign_secrets_added_after_migration(self):
        """⛔ Відкат чіпає лише запис ЛІГИ: секрет іншого простору/модуля, доданий ПІСЛЯ міграції, виживає."""
        stamp = self.migrate()
        cur = self.read_json(self.secrets_path())
        cur['other-space'] = {'m': {'k': 'later_value_alpha'}}
        cur['other']['m2'] = {'k': 'later_value_beta'}
        self._write(self.secrets_path(), cur)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        after = self.read_json(self.secrets_path())
        self.assertEqual(after['other-space'], {'m': {'k': 'later_value_alpha'}})
        self.assertEqual(after['other'], {'m': {'k': 'other_value_alpha'}, 'm2': {'k': 'later_value_beta'}})
        self.assertNotIn('legacy', after)                                          # у бекапі запису ЛІГИ не було
        self.assertEqual(os.stat(self.secrets_path()).st_mode & 0o777, 0o600)

    def test_restore_restores_liga_secrets_entry_from_backup(self):
        self._write(self.secrets_path(), {'legacy': {'jira-tracker': {'token': 'old_token_alpha'}}, 'other': {'m': {'k': 'v'}}})
        stamp = self.migrate(seed=False)
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['jira-tracker'], {'token': self.JIRA_TOKEN})
        cur = self.read_json(self.secrets_path())
        cur['later'] = {'m': {'k': 'later_value_alpha'}}
        self._write(self.secrets_path(), cur)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        after = self.read_json(self.secrets_path())
        self.assertEqual(after['legacy'], {'jira-tracker': {'token': 'old_token_alpha'}})
        self.assertEqual((after['other'], after['later']), ({'m': {'k': 'v'}}, {'m': {'k': 'later_value_alpha'}}))

    def test_pre_restore_safety_copy_holds_later_edits(self):
        """⛔ Правки ПІСЛЯ міграції не зникають мовчки: поточні `space.json` і ліговий шматок секретів — у `…-pre-restore`."""
        stamp = self.migrate()
        edited = self.read_json(self.space_path())
        edited['edited_later'] = {'keep': 1}
        self._write(self.space_path(), edited)
        edited_bytes = self.read(self.space_path())
        sec = self.read_json(self.secrets_path())
        sec['legacy']['jira-tracker']['token'] = 'edited_later_token_alpha'
        self._write(self.secrets_path(), sec)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        self.assertEqual(self.read(self.space_path()), self.ORIG_SPACE)
        names = [n for n in os.listdir(os.path.join(self.deai, 'backups')) if n.endswith('-pre-restore')]
        self.assertEqual(names, [stamp + '-pre-restore'])
        self.assertIsNone(self.lm.STAMP_RE.fullmatch(names[0]))                    # це не бекап міграції
        b = os.path.join(self.deai, 'backups', names[0])
        self.assertEqual(os.stat(b).st_mode & 0o777, 0o700)
        self.assertEqual(self.read(b, 'space.json'), edited_bytes)
        self.assertEqual(self.read_json(b, 'secrets-liga.json')['legacy']['jira-tracker'], {'token': 'edited_later_token_alpha'})
        for f in os.listdir(b):
            self.assertEqual(os.stat(os.path.join(b, f)).st_mode & 0o777, 0o600, f)
        m = self.read_json(b, 'manifest.json')
        for fname, meta in m['files'].items():
            self.assertEqual(meta['sha256'], self.sha(self.read(b, fname)), fname)
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['safety_copy'], names[0])
        self.assertEqual(self.lm.status()['backups'], [stamp])                     # pre-restore у списку бекапів міграції нема
        self.assertEqual(self.lm.restore(stamp + '-pre-restore'), 'refuse-stamp')  # і відкотитись із нього не можна
        self.assertEqual(self.lm.restore(stamp), 'restored')                       # другий відкат — нова копія з суфіксом
        self.assertEqual(sorted(n for n in os.listdir(os.path.join(self.deai, 'backups')) if 'pre-restore' in n),
                         [stamp + '-pre-restore', stamp + '-pre-restore-2'])

    def test_safety_copy_failure_restores_nothing(self):
        stamp = self.migrate()
        migrated = self.read(self.space_path())
        with self.mock.patch.object(self.lm, '_write_pre_restore', side_effect=OSError('disk')):
            self.assertEqual(self.lm.restore(stamp), 'abort-restore')
        self.assertEqual(self.read(self.space_path()), migrated)

    def test_cli_restore_mentions_safety_copy(self):
        stamp = self.migrate()
        code, out, _ = self.cli('restore', stamp)
        self.assertEqual(code, 0)
        self.assertIn('pre-restore', out)
        self.assertIn('запобіжна', out)

    def test_cli_restore(self):
        stamp = self.migrate()
        code, out, _ = self.cli('restore', stamp, '--hold')
        self.assertEqual(code, 0)
        self.assertIn('restored', out)
        self.assertEqual(self.read_json(self.space_path())['migrations'], {'liga-4d3a': {'held': True}})
        code, out, _ = self.cli('status')
        self.assertIn('held', out)
        self.assertEqual(self.cli('restore', 'bad')[0], 1)
        self.assert_no_secrets_in_logs()


class StartupTest(_WriteStand):
    """Task 5 (4d-3a): `startup()` — матриця ізоляції/шва/справжнього дому; виняток не валить старт."""

    def alt_home(self):
        """Тимчасовий DEAI_HOME, що НЕ є `~/.deai` (у стенді HOME підмінено, тож `self.deai` і є «справжнім»)."""
        alt = os.path.join(self.tmp, 'alt-deai')
        os.makedirs(alt)
        with open(os.path.join(self.deai, 'spaces.json'), 'rb') as f, open(os.path.join(alt, 'spaces.json'), 'wb') as g:
            g.write(f.read())
        return alt

    def test_production_runs(self):
        st, err = self.quiet(self.lm.startup)
        self.assertEqual(st, 'done')
        self.assertIn('liga-4d3a: done', err)
        self.assertEqual(self.quiet(self.lm.startup)[0], 'skip-done')
        self.assert_no_secrets_in_logs()

    def test_isolated_does_not_run(self):
        for env in ({'DC_NO_OVERVIEW': '1'}, {'DC_TASKS_FILE': self.tasks_path}, {'DC_TASKS_FILE': self.tasks_path, 'DC_NO_OVERVIEW': '1'}):
            with self.mock.patch.dict(os.environ, env):
                before = self.snapshot_tree()
                st, err = self.quiet(self.lm.startup)
                self.assertIsNone(st, env)
                self.assertEqual(err, '')
                self.assertEqual(self.snapshot_tree(), before, env)

    def test_isolated_with_seam_and_temp_home_runs(self):
        alt = self.alt_home()
        with self.mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1', 'DC_MIGRATE_LIGA': '1', 'DEAI_HOME': alt}):
            st, _err = self.quiet(self.lm.startup)
        self.assertEqual(st, 'done')
        self.assertEqual(len(os.listdir(os.path.join(alt, 'backups'))), 1)
        self.assertTrue(os.path.exists(os.path.join(alt, 'secrets.json')))
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'secrets.json')))         # "справжній" дім не чіпано
        self.assert_no_secrets(*self.cap)

    def test_seam_value_must_be_exactly_one(self):
        alt = self.alt_home()
        for val in ('0', '', 'true', 'yes'):
            with self.mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1', 'DC_MIGRATE_LIGA': val, 'DEAI_HOME': alt}):
                self.assertIsNone(self.quiet(self.lm.startup)[0], val)
        self.assertFalse(os.path.exists(os.path.join(alt, 'backups')))

    def test_seam_with_real_home_is_refused_loudly(self):
        before = self.snapshot_tree()
        for env_home in (self.deai, None, '~/.deai'):
            env = {'DC_NO_OVERVIEW': '1', 'DC_MIGRATE_LIGA': '1'}
            with self.mock.patch.dict(os.environ, env):
                if env_home is None:
                    os.environ.pop('DEAI_HOME', None)
                else:
                    os.environ['DEAI_HOME'] = env_home
                st, err = self.quiet(self.lm.startup)
            self.assertEqual(st, 'refuse-real-home', env_home)
            self.assertIn('DC_MIGRATE_LIGA', err)
            self.assertIn('відмова', err)
        self.assertEqual(self.snapshot_tree(), before)

    def test_seam_with_symlink_to_real_home_is_refused(self):
        link = os.path.join(self.tmp, 'link-deai')
        os.symlink(self.deai, link)
        with self.mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1', 'DC_MIGRATE_LIGA': '1', 'DEAI_HOME': link}):
            self.assertEqual(self.quiet(self.lm.startup)[0], 'refuse-real-home')
        self.assertEqual(self.backups(), [])

    def test_exception_does_not_break_startup(self):
        with self.mock.patch.object(self.lm, '_run', side_effect=RuntimeError(self.SB_KEY)):
            st, err = self.quiet(self.lm.startup)
        self.assertEqual(st, 'abort-internal')
        self.assertIn('RuntimeError', err)
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual((last['status'], last['error']), ('abort-internal', 'RuntimeError'))
        self.assert_no_secrets_in_logs()

    def test_exception_with_unwritable_log_does_not_break_startup(self):
        with self.mock.patch.object(self.lm, '_run', side_effect=RuntimeError('x')), \
                self.mock.patch.object(self.lm, '_write_last', side_effect=OSError('y')):
            self.assertEqual(self.quiet(self.lm.startup)[0], 'abort-internal')

    def test_home_only_overridden_deai_home_unset_production_runs(self):
        """Лише `HOME` підмінено, `DEAI_HOME` не заданий: дім — `<HOME>/.deai`; не ізольований прогін мігрує саме туди."""
        os.environ.pop('DEAI_HOME', None)
        st, _err = self.quiet(self.lm.startup)
        self.assertEqual(st, 'done')
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(self.deai, os.path.join(self.home, '.deai'))

    def test_serve_main_calls_startup_before_make_server(self):
        with open(os.path.join(os.path.dirname(_HERE), 'app', 'serve.py'), encoding='utf-8') as f:
            src = f.read()
        tail = src[src.index("if __name__ == '__main__':"):]
        self.assertIn('liga_migrate.startup()', tail)
        self.assertLess(tail.index('liga_migrate.startup()'), tail.index('make_server(port).serve_forever()'))


if __name__ == '__main__':
    unittest.main()
