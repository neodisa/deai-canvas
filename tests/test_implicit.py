"""Неявний постачальник, шов шару, закон ізоляції (етап 4d-2, 0.16.0).

Тут: знімок поведінки 0.15.0 (`Before4d2Shape`, Task 1); ядро `app/implicit.py`, шов `effective_space()`, закон ізоляції й
охоронець літерала додаються наступними задачами. Спека `docs/superpowers/specs/2026-11-05-implicit-provider-seam-design.md`.
"""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import implicit  # noqa: E402
import spaces  # noqa: E402
import dashboard  # noqa: E402
import tracker  # noqa: E402
import notify  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'implicit', 'before-4d2.json')

ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs')       # `deai_modules.ROLES_CALLED`, відсортовано
LEGACY_ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tracker', 'vcs')          # `deai_modules.IMPLICIT_ROLES`
ENVS = ('a_seam', 'b_dc_tasks_file', 'c_dc_no_overview')


class Before4d2Shape(unittest.TestCase):
    """Знімок 0.15.0 на місці й має ключі, типи та кількості сценаріїв, на які спираються тести паритету наступних задач."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_sections(self):
        self.assertEqual(sorted(self.snap), ['api', 'build', 'cache_who', 'caps', 'install', 'isolation', 'meta', 'non_loopback_attempts', 'provider'])
        self.assertEqual(self.snap['meta']['version'], '0.15.0')
        self.assertEqual(self.snap['meta']['source_commit'], '6e68250')
        self.assertEqual(self.snap['meta']['generator'], 'tests/make_before_4d2.py')

    def test_machine_independent(self):
        """⛔ Знімок не несе ні справжніх шляхів, ні імен, ні тимчасових тек: лише `~/…`/`<tmp>`; значення — вигадані."""
        # ⛔ Імʼя користувача машини — з оточення, не літералом: справжнє імʼя в коді репо — та сама утічка, від якої тест береже.
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/Users/', '/home/', '/var/folders', '/private/', '/tmp/', 'before-4d2-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))          # жодного часового штампа
        self.assertEqual(self.snap['meta']['volatile_stripped'], [])

    def test_caps_shape(self):
        c = self.snap['caps']
        self.assertEqual(sorted(c), ['fingerprint_failure_liga', 'fingerprint_failure_plain', 'liga',
                                     'liga_unreadable_space_json', 'plain_no_modules', 'plain_own_module_untrusted',
                                     'plain_static_publish', 'plain_unreadable_space_json'])
        for name, row in c.items():
            self.assertEqual(sorted(row), ['caps', 'space'], name)
            self.assertTrue(set(ROLES) <= set(row['caps']), name)
            self.assertLessEqual(set(row['caps']) - set(ROLES), {'error'}, name)
            for role in ROLES:
                self.assertIsInstance(row['caps'][role], (str, type(None)), (name, role))
        # ключові паритети: ЛІГА — `'legacy'` у шести ролях, у `tokens` — ніхто; звичайний — неявний `static-publish`
        liga = c['liga']['caps']
        self.assertEqual({r: liga[r] for r in LEGACY_ROLES}, {r: 'legacy' for r in LEGACY_ROLES})
        self.assertIsNone(liga['tokens'])
        self.assertNotIn('error', liga)
        self.assertEqual(c['plain_no_modules']['caps']['publish'], 'static-publish')
        self.assertEqual({v for k, v in c['plain_no_modules']['caps'].items() if k != 'publish'}, {None})
        self.assertEqual(c['plain_static_publish']['caps']['publish'], 'static-publish')
        # нечитабельний `space.json`: ЛІГА лишає `'legacy'` лише в `publish`/`vcs`; решта — `None` + код помилки
        bad = c['liga_unreadable_space_json']['caps']
        self.assertEqual((bad['publish'], bad['vcs'], bad['error']), ('legacy', 'legacy', 'space-json-unreadable'))
        self.assertEqual({bad[r] for r in ('comments', 'dashboard', 'notify', 'tracker')}, {None})
        self.assertEqual(c['plain_unreadable_space_json']['caps']['error'], 'space-json-unreadable')
        self.assertIsNone(c['plain_unreadable_space_json']['caps']['publish'])
        # свій недовірений модуль «на папері»: `publish` — `None`, без `error` (стан ролі, а не простору)
        own = c['plain_own_module_untrusted']['caps']
        self.assertIsNone(own['publish'])
        self.assertNotIn('error', own)
        # збій відбитків: тотальна запасна форма з `error: module-error`; `'legacy'` лише в `publish`/`vcs` ЛІГИ
        fp = c['fingerprint_failure_liga']['caps']
        self.assertEqual((fp['publish'], fp['vcs'], fp['error']), ('legacy', 'legacy', 'module-error'))
        self.assertEqual({fp[r] for r in ('comments', 'dashboard', 'notify', 'tracker', 'tokens')}, {None})
        fpp = c['fingerprint_failure_plain']['caps']
        self.assertEqual({fpp[r] for r in ROLES}, {None})
        self.assertEqual(fpp['error'], 'module-error')

    def test_provider_shape(self):
        p = self.snap['provider']
        self.assertEqual(sorted(p), ['layer_off', 'layer_on_request_not_fixed'])
        self.assertFalse(p['layer_off']['layer_on'])
        self.assertTrue(p['layer_on_request_not_fixed']['layer_on'])
        for mode, row in p.items():
            self.assertEqual(sorted(row['roles']), sorted(ROLES + ('git-sync', 'zzz')), mode)
            for role, r in row['roles'].items():
                self.assertEqual(sorted(r), ['catalog_reads', 'registry_reads', 'space_json_reads', 'value'], (mode, role))
                self.assertEqual(r['value'], 'legacy' if role in LEGACY_ROLES else None, (mode, role))
                # ⛔ без простору запиту рішення не читає ні реєстр, ні `space.json`, ні каталог
                self.assertEqual((r['registry_reads'], r['space_json_reads'], r['catalog_reads']), (0, 0, 0), (mode, role))

    def test_api_shape(self):
        a = self.snap['api']
        self.assertEqual(sorted(a), ['layer_off', 'liga_in_registry'])
        for mode, row in a.items():
            self.assertEqual(sorted(row), ['layer_on', 'space_route', 'spaces', 'task', 'urlopen_calls', 'vcs_provider_calls'], mode)
            self.assertEqual((row['urlopen_calls'], row['vcs_provider_calls']), (0, 0), mode)
            self.assertEqual((row['space_route']['status'], row['space_route']['body_is_json']), (404, False), mode)
            self.assertEqual(row['task']['status'], 200, mode)
            self.assertEqual(sorted(row['task']['preview_gate']), ['inner_stale', 'pages', 'stale', 'state', 'ungated'], mode)
            self.assertFalse(row['task']['has_publish_gate'], mode)
        liga = a['liga_in_registry']
        self.assertTrue(liga['layer_on'])
        self.assertEqual(len(liga['spaces']['rows']), 1)
        row = liga['spaces']['rows'][0]
        self.assertEqual((row['integrations'], row['legacy']), (True, True))
        self.assertEqual({row['capabilities'][r] for r in LEGACY_ROLES}, {'legacy'})      # публічний контракт: `'legacy'` назовні
        self.assertEqual(liga['task']['space']['capabilities'], row['capabilities'])
        off = a['layer_off']
        self.assertFalse(off['layer_on'])
        self.assertEqual((off['spaces']['off'], off['spaces']['rows']), (True, []))
        self.assertIsNone(off['task']['space'])

    def test_isolation_shape(self):
        i = self.snap['isolation']
        self.assertEqual(sorted(i), ['dashboard', 'note', 'notify', 'sync', 'tracker'])
        # (а) шов дає результат; (б) і (в) — модуль НЕ кличеться, мережі нема
        for role in ('dashboard', 'tracker', 'notify'):
            self.assertEqual(sorted(i[role]), list(ENVS), role)
        for env in ENVS:
            for fn in ('team_fetch', 'team_rows'):
                r = i['dashboard'][env][fn]
                self.assertEqual((r['module_calls'], r['urlopen_calls']), (0, 0), (env, fn))
            for fn in ('mute_state', 'mute_set'):
                r = i['notify'][env][fn]
                self.assertEqual((r['module_calls'], r['urlopen_calls']), (0, 0), (env, fn))
            t = i['tracker'][env]
            self.assertEqual((t['module_calls'], t['tracker_statuses_calls'], t['urlopen_calls']), (0, 0, 0), env)
        # дашборд: (а) — рядки шва без помилки; (б)/(в) — порожньо + текст ізоляції
        self.assertEqual(i['dashboard']['a_seam']['team_fetch']['outcome']['result'][1], None)
        self.assertEqual(len(i['dashboard']['a_seam']['team_fetch']['outcome']['result'][0]), 1)
        for env in ENVS[1:]:
            rows, err = i['dashboard'][env]['team_fetch']['outcome']['result']
            self.assertEqual(rows, [])
            self.assertIn('DC_TASKS_FILE', err)
        # трекер: (а) — статуси шва; (б)/(в) — `None` («трекера нема»), помилки нема
        self.assertEqual(i['tracker']['a_seam']['outcome']['result'][0], {'DEMO-1': {'cat': 'indeterminate', 'name': 'In progress'}})
        for env in ENVS[1:]:
            self.assertIsNone(i['tracker'][env]['outcome']['result'])
        # нотифай: (а) — шов пише у свій файл; (б)/(в) — `OSError` з фіксованим текстом
        self.assertEqual(i['notify']['a_seam']['mute_set']['outcome'], {'result': True})
        self.assertEqual(i['notify']['a_seam']['seam_file_after_set'], ['demo-channel'])
        for env in ENVS[1:]:
            for fn in ('mute_state', 'mute_set'):
                self.assertEqual(i['notify'][env][fn]['outcome']['raised'], 'OSError', (env, fn))
        # синк: стартує лише без ізоляції й з конфігом установки
        s = i['sync']
        self.assertEqual(sorted(s), ['a_seam', 'a_seam_no_install_config', 'b_dc_tasks_file', 'c_dc_no_overview'])
        self.assertEqual(s['a_seam']['launched'], [['legacy-key', True, ['--legacy']]])
        for name in ('a_seam_no_install_config', 'b_dc_tasks_file', 'c_dc_no_overview'):
            self.assertEqual(s[name]['launched'], [], name)
        for name, row in s.items():
            self.assertEqual(row['outcome'], {'result': None}, name)
            self.assertEqual(row.get('popen_calls', 0), 0, name)

    def test_install_shape(self):
        n = self.snap['install']
        names = sorted('%s/%s/%s' % (r, e, f) for r in ('root_with_pair', 'root_without_pair') for e in ('env_set', 'env_unset')
                       for f in ('files_present', 'files_absent'))
        self.assertEqual(sorted(n), names)
        for name, row in n.items():
            self.assertEqual(sorted(row), ['jira_config', 'supabase_config'], name)
            self.assertEqual((len(row['supabase_config']), len(row['jira_config'])), (2, 3), name)
        # вигадані значення і лише вони
        for name, row in n.items():
            for v in row['supabase_config'] + row['jira_config']:
                self.assertTrue(v is None or v.endswith('.example.com') or '@' in v or v.startswith(('sb_', 'jira_')), (name, v))
        # зафіксована ПОТОЧНА (0.15.0) поведінка: ізольований прогін бачить облікові машини — Task 5 це закриє
        self.assertEqual(n['root_without_pair/env_set/files_absent']['supabase_config'], ['https://sb-env.example.com', 'sb_env_key'])
        self.assertEqual(n['root_with_pair/env_unset/files_present']['jira_config'],
                         ['https://jira.example.com', 'file@example.com', 'jira_file_token'])
        self.assertEqual(n['root_without_pair/env_unset/files_present']['jira_config'], [None, None, None])
        self.assertEqual(n['root_without_pair/env_unset/files_absent']['supabase_config'], [None, None])

    def test_cache_who_and_tripwire(self):
        # ключ кешу — id простору запиту (`''` — без простору), `who` — `'legacy'`: Task 4 змінить його на `api_value(prov)`
        self.assertEqual(self.snap['cache_who'], {'team': {'': 'legacy'}, 'tracker': {'': 'legacy'}})
        self.assertEqual(self.snap['non_loopback_attempts'], 0)      # розтяжка сокетів: жодного виходу за loopback

    def test_build_shape(self):
        b = self.snap['build']
        self.assertEqual(b['BUILD_KINDS'], ['legacy', 'module'])
        self.assertEqual((b['legacy_with_league_comments']['manifest_build'], b['legacy_no_comments']['manifest_build'],
                          b['module_no_comments']['manifest_build']), ('legacy', 'legacy', 'module'))
        for name in ('legacy_with_league_comments', 'legacy_no_comments', 'module_no_comments'):
            self.assertTrue(b[name]['build_is_last_key'], name)
            self.assertEqual(b[name]['manifest_keys'], ['build', 'frames', 'iters', 'outline', 'pages', 'task', 'widths'], name)
        self.assertTrue(b['legacy_with_league_comments']['has_comment_layer_dir'])
        self.assertFalse(b['legacy_no_comments']['has_comment_layer_dir'])
        self.assertEqual(b['league_comments'], {'is_dict': True, 'keys': ['channel', 'config', 'module'],
                                                'module': 'supabase-comments', 'warn': None})
        self.assertFalse(b['publish_manifest_without_mark']['has_build_key'])
        bad = {k: v for k, v in b.items() if k.startswith('bad_build_')}
        self.assertEqual(len(bad), 4)
        self.assertEqual({v['raised'] for v in bad.values()}, {'ValueError'})
        self.assertEqual(b['urlopen_calls'], 0)


_ROLES = ('publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify')
_ENV = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TRACKER_FAKE', 'DC_TEAMS_FAKE', 'DEAI_HOME')


def _clean_env():
    """Оточення без змінних ізоляції/фейків: тест ставить лише те, що перевіряє."""
    return mock.patch.dict(os.environ, {}, clear=False)


class ImplicitCore(unittest.TestCase):
    def setUp(self):
        p = _clean_env()
        p.start()
        self.addCleanup(p.stop)
        for k in _ENV:
            os.environ.pop(k, None)

    def test_roles_order(self):
        self.assertEqual(implicit.IMPLICIT_ROLES, _ROLES)

    def test_singleton_and_immutable(self):
        for r in _ROLES:
            p = implicit.for_role(r)
            self.assertIs(p, implicit.for_role(r))
            self.assertEqual(p.role, r)
            with self.assertRaises(AttributeError):
                p.module_id = 'x'
            with self.assertRaises(AttributeError):
                p.extra = 1

    def test_table(self):
        want = {
            'publish': ('vercel-publish', True, None),
            'comments': ('supabase-comments', True, None),
            'vcs': ('git-sync', True, None),
            'dashboard': ('supabase-dashboard', True, 'DC_TEAM_FAKE'),
            'tracker': ('jira-tracker', True, 'DC_TRACKER_FAKE'),
            'notify': ('supabase-teams', True, 'DC_TEAMS_FAKE'),
        }
        for r, (mid, shared, fake) in want.items():
            p = implicit.for_role(r)
            self.assertEqual((p.module_id, p.shared, p.fake_env), (mid, shared, fake), r)

    def test_module_ids_match_real_code(self):
        """Таблиця не розходиться з тим, що реально беруть гілки 0.15.0."""
        import serve
        self.assertEqual(implicit.for_role('publish').module_id, serve.PUBLISH_LEGACY_MODULE)
        self.assertEqual(implicit.for_role('comments').module_id, serve.COMMENTS_MODULE)
        self.assertEqual(implicit.for_role('vcs').module_id, serve.VCS_MODULE)
        self.assertEqual(implicit.for_role('dashboard').module_id, dashboard.LEGACY_MODULE)
        self.assertEqual(implicit.for_role('tracker').module_id, tracker.LEGACY_MODULE)
        self.assertEqual(implicit.for_role('notify').module_id, notify.LEGACY_MODULE)

    def test_unknown_role(self):
        with self.assertRaises(KeyError):
            implicit.for_role('tokens')

    def test_isolated_truth_table(self):
        for tf in (None, '', '/x/tasks.json'):
            for no in (None, '', '1'):
                with mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop('DC_TASKS_FILE', None)
                    os.environ.pop('DC_NO_OVERVIEW', None)
                    if tf is not None:
                        os.environ['DC_TASKS_FILE'] = tf
                    if no is not None:
                        os.environ['DC_NO_OVERVIEW'] = no
                    self.assertEqual(implicit.isolated(), bool(tf) or bool(no), (tf, no))

    def test_route_fake_wins_even_isolated(self):
        p = implicit.for_role('dashboard')
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': '/tmp/fake.json', 'DC_TASKS_FILE': '/x/t.json'}):
            self.assertEqual(implicit.route(p), ('fake', '/tmp/fake.json'))

    def test_route_empty_fake_is_absent(self):
        p = implicit.for_role('dashboard')
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': '', 'DC_NO_OVERVIEW': '1'}):
            self.assertEqual(implicit.route(p), ('isolated', None))

    def test_route_isolated_and_live(self):
        for r in _ROLES:
            p = implicit.for_role(r)
            self.assertEqual(implicit.route(p), ('live', None), r)
            with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '/x/t.json'}):
                self.assertEqual(implicit.route(p), ('isolated', None), r)
            with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1'}):
                self.assertEqual(implicit.route(p), ('isolated', None), r)

    def test_route_not_shared_is_live_when_isolated(self):
        p = implicit.Implicit('x', 'm', False, None)
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '/x/t.json'}):
            self.assertEqual(implicit.route(p), ('live', None))

    def test_no_serve_import(self):
        with open(implicit.__file__, encoding='utf-8') as f:
            src = f.read()
        self.assertNotIn('import serve', src)
        self.assertNotIn('deai_modules', src)


class EffectiveSpace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = _clean_env()
        p.start()
        self.addCleanup(p.stop)
        for k in _ENV:
            os.environ.pop(k, None)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)

    def _no_registry(self):
        m = mock.patch.object(spaces, 'load_registry', side_effect=AssertionError('registry read'))
        calls = m.start()
        self.addCleanup(m.stop)
        return calls

    def test_layer_off_returns_copy_without_registry(self):
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp.name, 'tasks.json')
        lr = self._no_registry()
        self.assertFalse(spaces.layer_on())
        sp = spaces.effective_space()
        self.assertEqual(sp, spaces.IMPLICIT)
        self.assertIsNot(sp, spaces.IMPLICIT)
        sp['integrations'] = False
        self.assertIs(spaces.IMPLICIT['integrations'], True)
        lr.assert_not_called()

    def test_layer_off_with_fixed_space_still_implicit(self):
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp.name, 'tasks.json')
        self._no_registry()
        with spaces.request_space('whatever'):
            self.assertEqual(spaces.effective_space(), spaces.IMPLICIT)

    def test_layer_on_unfixed_returns_copy_without_registry(self):
        os.environ['DEAI_HOME'] = os.path.join(self.tmp.name, 'deai')
        lr = self._no_registry()
        self.assertTrue(spaces.layer_on())
        self.assertIsNone(spaces.request_space_id())
        sp = spaces.effective_space()
        self.assertEqual(sp, spaces.IMPLICIT)
        self.assertIsNot(sp, spaces.IMPLICIT)
        sp['id'] = 'changed'
        self.assertEqual(spaces.IMPLICIT['id'], 'legacy')
        lr.assert_not_called()

    def test_layer_on_fixed_is_active_space(self):
        os.environ['DEAI_HOME'] = os.path.join(self.tmp.name, 'deai')
        with spaces.request_space(''):
            self.assertIsNone(spaces.effective_space())
            self.assertIsNone(spaces.active_space())
        sentinel = {'id': 'alpha', 'path': self.tmp.name}
        with mock.patch.object(spaces, 'active_space', return_value=sentinel):
            with spaces.request_space('alpha'):
                self.assertIs(spaces.effective_space(), sentinel)


class ProviderImplicit(unittest.TestCase):
    """4d-2 Task 3: `deai_modules` віддає `Implicit` замість рядка `'legacy'`; назовні лишається `'legacy'` (`api_value`)."""

    def setUp(self):
        import deai_modules as dm
        self.dm = dm
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = _clean_env()
        p.start()
        self.addCleanup(p.stop)
        for k in _ENV:
            os.environ.pop(k, None)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)

    def _counters(self):
        """Лічильники читань реєстру, `space.json` і каталогу (обгортки `wraps`: поведінку не міняють)."""
        out = []
        for obj, name in ((spaces, 'load_registry'), (self.dm, 'space_modules'), (self.dm, 'catalog')):
            m = mock.patch.object(obj, name, wraps=getattr(obj, name))
            out.append(m.start())
            self.addCleanup(m.stop)
        return out

    def _assert_implicit_roles(self):
        reads = self._counters()
        for role in self.dm.ROLES_CALLED:
            p = self.dm.provider(role)
            if role in implicit.IMPLICIT_ROLES:
                self.assertIsInstance(p, implicit.Implicit, role)
                self.assertIs(p, implicit.for_role(role), role)
            else:
                self.assertIsNone(p, role)
        self.assertIsNone(self.dm.provider('tokens'))
        for m in reads:
            m.assert_not_called()

    def test_layer_off_is_implicit_without_reads(self):
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp.name, 'tasks.json')
        self.assertFalse(spaces.layer_on())
        self._assert_implicit_roles()

    def test_unfixed_request_space_is_implicit_without_reads(self):
        os.environ['DEAI_HOME'] = os.path.join(self.tmp.name, 'deai')
        self.assertTrue(spaces.layer_on())
        self.assertIsNone(spaces.request_space_id())
        self._assert_implicit_roles()

    def test_provider_none_when_no_space(self):
        os.environ['DEAI_HOME'] = os.path.join(self.tmp.name, 'deai')
        with mock.patch.object(spaces, 'effective_space', return_value=None):
            for role in self.dm.ROLES_CALLED:
                self.assertIsNone(self.dm.provider(role), role)
        with spaces.request_space(''):                      # запит прямо каже «без простору»
            self.assertIsNone(self.dm.provider('publish'))

    def test_provider_uses_effective_space_seam(self):
        """`provider(role)` без простору бере його ТІЛЬКИ з шва `spaces.effective_space()`."""
        sentinel = {'id': 'seam-probe', 'path': ''}
        with mock.patch.object(spaces, 'effective_space', return_value=sentinel) as eff, \
                mock.patch.object(self.dm, '_provider_for', return_value='probe') as pf:
            self.assertEqual(self.dm.provider('publish'), 'probe')
        eff.assert_called_once_with()
        pf.assert_called_once_with('publish', sentinel)

    def test_explicit_space_does_not_use_seam(self):
        with mock.patch.object(spaces, 'effective_space', side_effect=AssertionError('seam')), \
                mock.patch.object(self.dm, '_provider_for', return_value='probe') as pf:
            self.assertEqual(self.dm.provider('publish', {'id': 'x', 'path': self.tmp.name}), 'probe')
        pf.assert_called_once()

    def test_provider_for_implicit_space_does_not_read_space_json_in_cwd(self):
        """⛔ `_provider_for(role, dict(spaces.IMPLICIT))` не кличе `space_modules`: `space.json` у ПОТОЧНІЙ теці процесу
        (порожній шлях неявного простору — не «поточна тека») не читається, навіть зіпсований."""
        work = os.path.join(self.tmp.name, 'cwd')
        os.makedirs(work)
        with open(os.path.join(work, 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{не json')
        reads = self._counters()
        old = os.getcwd()
        os.chdir(work)
        self.addCleanup(os.chdir, old)
        for role in self.dm.ROLES_CALLED:
            p = self.dm._provider_for(role, dict(spaces.IMPLICIT))
            if role in implicit.IMPLICIT_ROLES:
                self.assertIs(p, implicit.for_role(role), role)
            else:
                self.assertIsNone(p, role)
        for m in reads:
            m.assert_not_called()

    def test_provider_for_plain_space_without_integrations_has_no_implicit(self):
        sp = {'id': 'plain', 'path': os.path.join(self.tmp.name, 'plain')}
        os.makedirs(sp['path'])
        for role in implicit.IMPLICIT_ROLES:
            self.assertNotIsInstance(self.dm._provider_for(role, sp), implicit.Implicit, role)

    def test_provider_for_integrations_space_returns_implicit(self):
        sp = {'id': 'liga2', 'path': os.path.join(self.tmp.name, 'liga2'), 'integrations': True}
        os.makedirs(sp['path'])
        for role in implicit.IMPLICIT_ROLES:
            self.assertIs(self.dm._provider_for(role, sp), implicit.for_role(role), role)
        self.assertIsNone(self.dm._provider_for('tokens', sp))

    def test_role_constants_renamed(self):
        dm = self.dm
        self.assertIs(dm.IMPLICIT_ROLES, implicit.IMPLICIT_ROLES)
        self.assertEqual(dm.IMPLICIT_ON_ERROR_ROLES, ('publish', 'vcs'))
        self.assertEqual(dm.STRICT_IMPLICIT_ROLES, ('comments', 'dashboard', 'tracker', 'notify'))
        for gone in ('LEGACY_ROLES', 'LEGACY_ON_ERROR_ROLES', 'STRICT_LEGACY_ROLES'):
            self.assertFalse(hasattr(dm, gone), gone)

    def test_api_value(self):
        dm = self.dm
        self.assertEqual(dm.API_IMPLICIT, 'legacy')
        for role in implicit.IMPLICIT_ROLES:
            self.assertEqual(dm.api_value(implicit.for_role(role)), 'legacy')
        self.assertIsNone(dm.api_value(None))
        mod = dm.Module.__new__(dm.Module)
        mod.id = 'acme'
        self.assertEqual(dm.api_value(mod), 'acme')
        for bad in ('legacy', 'acme', 0, {}, object()):
            with self.assertRaises(TypeError):
                dm.api_value(bad)

    def test_capabilities_match_before_4d2_snapshot(self):
        """`capabilities()` після переходу на `Implicit` дає ті самі значення, що 0.15.0 (знімок `caps`): публічний контракт."""
        import make_before_4d2 as gen
        with open(BEFORE, encoding='utf-8') as f:
            want = json.load(f)['caps']
        with tempfile.TemporaryDirectory(prefix='caps-4d2-') as tmp:
            tmp = os.path.normpath(tmp)
            home = os.path.join(tmp, 'home')
            os.makedirs(home)
            with mock.patch.dict(os.environ, {'HOME': home}):
                for name in gen.CLEAN:
                    os.environ.pop(name, None)
                got = gen.caps(tmp)
        self.assertEqual(sorted(got), sorted(want))
        for name in want:
            self.assertEqual(got[name]['caps'], want[name]['caps'], name)
            for role, v in got[name]['caps'].items():
                self.assertIs(type(v), type(want[name]['caps'][role]), (name, role))     # `str`/`None`, не `Implicit`
        self.assertEqual(want['liga']['caps']['publish'], 'legacy')                        # знімок справді несе `'legacy'`


if __name__ == '__main__':
    unittest.main()
