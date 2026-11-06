"""Міграція ЛІГИ в явні `tracks` і модулі (етап 4d-3a, 0.17.0).

Тут: знімок поведінки 0.16.0 (`Before4d3aShape`, Task 1); `compat`, `shared_state`, розрахунок і запис міграції, паритет додаються
наступними задачами. Спека `docs/superpowers/specs/2026-11-05-liga-migration-a-design.md`.
"""
import json
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d3a.json')

ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs')
LEGACY_ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tracker', 'vcs')
MODULES = ('jira-tracker', 'supabase-dashboard', 'supabase-teams')


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


if __name__ == '__main__':
    unittest.main()
