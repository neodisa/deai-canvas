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


if __name__ == '__main__':
    unittest.main()
