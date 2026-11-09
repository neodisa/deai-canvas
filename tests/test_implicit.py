"""Неявний постачальник, шов шару, закон ізоляції (етап 4d-2, 0.16.0).

Тут: знімок поведінки 0.15.0 (`Before4d2Shape`, Task 1); ядро `app/implicit.py`, шов `effective_space()`, закон ізоляції й
охоронець літерала додаються наступними задачами. Спека `docs/superpowers/specs/2026-11-05-implicit-provider-seam-design.md`.
"""
import ast
import glob
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import install_config  # noqa: E402
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


# ⛔ Клас `ImplicitCore` (11 тестів) ретировано в 4d-4b: `app/implicit.py` видалено, ядро ізоляції — `app/isolation.py`. Відповідність:
#   `test_roles_order`, `test_singleton_and_immutable`, `test_table`, `test_module_ids_match_real_code`, `test_unknown_role` -> R6 (`Implicit`
#     нема; таблиця швів — `test_isolation.IsolationCore.test_fake_env_table_is_the_old_one`, ролі — `liga_migrate.LIGA_ROLES`);
#   `test_isolated_truth_table` -> `test_isolation.IsolationCore.test_isolated_is_tasks_file_or_no_overview`;
#   `test_route_fake_wins_even_isolated`, `test_route_isolated_and_live` -> `test_isolation.IsolationCore.test_route_order_fake_then_isolated_then_live`;
#   `test_route_empty_fake_is_absent` -> `test_isolation.IsolationCore.test_an_empty_seam_is_absent`;
#   `test_route_not_shared_is_live_when_isolated` -> R6 (параметр `shared` завжди був `True`; ролі без шва —
#     `test_isolation.IsolationCore.test_roles_without_a_seam_are_only_isolated_or_live`);
#   `test_no_serve_import` -> `test_isolation.IsolationCore.test_imports_nothing_but_os`.


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

    def _assert_no_roles_without_reads(self):
        reads = self._counters()
        for role in self.dm.ROLES_CALLED:
            self.assertIsNone(self.dm.provider(role), role)       # було `Implicit` для шести ролей ЛІГИ; 4d-4b: ролей нема
        self.assertIsNone(self.dm.provider('tokens'))
        for m in reads:
            m.assert_not_called()

    def test_layer_off_has_no_roles_without_reads(self):
        """Було `…_is_implicit_without_reads` (шість ролей віддавали `Implicit`); тепер `None`, і так само БЕЗ читань реєстру/`space.json`/каталогу."""
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp.name, 'tasks.json')
        self.assertFalse(spaces.layer_on())
        self._assert_no_roles_without_reads()

    def test_unfixed_request_space_has_no_roles_without_reads(self):
        os.environ['DEAI_HOME'] = os.path.join(self.tmp.name, 'deai')
        self.assertTrue(spaces.layer_on())
        self.assertIsNone(spaces.request_space_id())
        self._assert_no_roles_without_reads()

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
            self.assertIsNone(self.dm._provider_for(role, dict(spaces.IMPLICIT)), role)     # було `Implicit` для ролей ЛІГИ
        for m in reads:
            m.assert_not_called()

    def test_provider_for_plain_space_without_integrations_has_no_provider(self):
        sp = {'id': 'plain', 'path': os.path.join(self.tmp.name, 'plain')}
        os.makedirs(sp['path'])
        for role in self.dm.ROLES_CALLED:
            p = self.dm._provider_for(role, sp)
            if role == 'publish':
                self.assertEqual(p.id, 'static-publish')           # єдиний типовий модуль простору без запису
            else:
                self.assertIsNone(p, role)

    # Ретировано (4d-4b): `test_provider_for_integrations_space_returns_implicit` -> ІНВЕРТОВАНО в
    # `test_originals_gone.ProviderWithoutImplicit.test_a_liga_role_without_a_record_is_none`; `test_role_constants_renamed` -> R6
    # (`test_originals_gone.ProviderWithoutImplicit.test_the_core_has_no_fallback_names`: `IMPLICIT_*` констант нема).

    def test_api_value(self):
        dm = self.dm
        self.assertIsNone(dm.api_value(None))
        mod = dm.Module.__new__(dm.Module)
        mod.id = 'acme'
        self.assertEqual(dm.api_value(mod), 'acme')
        for bad in ('legacy', 'acme', 0, {}, object()):            # рядок `'legacy'` — теж `TypeError`: неявного випадку нема
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
            # 4d-4b: знімок 0.15.0 — еталон, а не вимога: неявні `'legacy'` стали `None` (запасного постачальника нема); решта — без змін
            expected = {r: (None if v == 'legacy' else v) for r, v in want[name]['caps'].items()}
            if expected.get('error') not in (None, 'space-json-unreadable'):
                # r15-1: збій НЕ простору тепер іменний за роллю (`errors`) — додатковий ключ, значення ролей і `error` ті самі
                expected['errors'] = {r: expected['error'] for r in self.dm.ROLES_CALLED}
            self.assertEqual(got[name]['caps'], expected, name)
            for role, v in got[name]['caps'].items():
                self.assertTrue(v is None or isinstance(v, str), (name, role))           # `str`/`None`
        self.assertEqual(want['liga']['caps']['publish'], 'legacy')                        # знімок справді несе `'legacy'`
        self.assertTrue(all(v is None for v in got['liga']['caps'].values()), 'ЛІГА без явних записів — жодної ролі')


class RolesParity(unittest.TestCase):
    """4d-2 Task 4: `serve.py` і `bin/` ідуть через `isinstance(prov, Implicit)` + `implicit.route`; поведінка 0.15.0 — та сама.
    Сценарії ті самі, що в `make_before_4d2.py` (його будівники викликаються з `Implicit` замість рядка `'legacy'`)."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.snap = json.load(f)

    def _run(self, builder, prov=None, **kw):
        import make_before_4d2 as gen
        with tempfile.TemporaryDirectory(prefix='roles-4d2-') as tmp:
            tmp = os.path.normpath(tmp)
            home = os.path.join(tmp, 'home')
            os.makedirs(home)
            with mock.patch.dict(os.environ, {'HOME': home}):
                for name in gen.CLEAN:
                    os.environ.pop(name, None)
                fn = getattr(gen, builder)
                return fn(tmp, **kw) if prov is None else fn(tmp, prov, **kw)

    def league(self, role):
        """`(space, prov)` ролі `role` простору ЛІГА з ЯВНИМ записом (4d-4b, R3; було `implicit.for_role(role)`). Простір закріплено простором запиту."""
        import deai_modules as dm
        import liga_fixture
        fx = liga_fixture.LigaFixture(self).env().build(roles=(role,))
        fx.fix_space()
        space = {'id': 'legacy', 'path': fx.space_dir, 'legacy': True, 'integrations': True}
        return space, dm.provider(role, space)

    # Ретировано (4d-4b): `test_isolation_matches_snapshot_through_new_code_paths` і `test_cache_who_matches_snapshot` — вони гонили
    # генератор знімка 0.15.0 (`make_before_4d2`) з `Implicit` і читачами оригіналів, яких нема. Замінено: ізоляція дашборда/сповіщень/
    # трекера — `test_dashboard.test_isolation_does_not_call_the_module`, `test_notify.test_the_league_route_in_an_isolated_run_never_reaches_the_network`,
    # `test_tasks_overview.test_isolation_without_the_seam_means_no_tracker_and_no_work`; ключ `who` кешів (`'legacy'` через `api_value`)
    # більше не існує — його значення тепер id явного модуля (покриває `test_originals_gone.ProviderWithoutImplicit`).

    def test_tracker_empty_keys_isolated_is_none_not_empty_dict(self):
        """⛔ Порядок `_tracker_fetch` для `shared_state`-запису: шов → ізоляція → `if not keys`. Ізольований прогін без ключів — `None`
        («трекера нема»), а не `({}, None)`; (знімок має непорожні ключі, тож цього не бачить). Постачальник — явний запис `jira-tracker`."""
        import serve
        space, prov = self.league('tracker')
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(tempfile.gettempdir(), 'x-tasks.json')}):
            os.environ.pop('DC_TRACKER_FAKE', None)
            self.assertIsNone(serve._tracker_fetch(space, prov, []))
            self.assertIsNone(serve._tracker_fetch(space, prov, ['DEMO-1']))

    def test_notify_isolated_never_calls_module(self):
        import serve
        import deai_modules as dm
        space, prov = self.league('notify')
        with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1'}), mock.patch.object(dm, 'call', side_effect=AssertionError('модуль')):
            os.environ.pop('DC_TEAMS_FAKE', None)
            with self.assertRaises(OSError):
                serve.notify_call('mute_state', resolved=(space, prov))

    def test_api_matches_snapshot_in_both_modes(self):
        """`/api/spaces` і `/api/task` (`capabilities`, `preview_gate`, `publish_gate`) — як 0.15.0, КРІМ простору ЛІГА в реєстрі:
        там неявні `'legacy'` стали `null` (запасного постачальника нема, 4d-4b; значення знімка — еталон 0.15, а не вимога)."""
        def no_fallback(obj):
            if isinstance(obj, dict):
                return {k: ({r: (None if v == 'legacy' else v) for r, v in val.items()} if k == 'capabilities' and isinstance(val, dict)
                            else no_fallback(val)) for k, val in obj.items()}
            if isinstance(obj, list):
                return [no_fallback(x) for x in obj]
            return obj
        got = self._run('api')
        want = dict(self.snap['api'], liga_in_registry=no_fallback(self.snap['api']['liga_in_registry']))
        self.assertEqual(got, want)


class PublishModule(unittest.TestCase):
    """4d-2 Task 4: `deai_modules.publish_module(space)` — тотальний помічник «публікує модуль»; рішення = `capabilities(space)['publish']`."""

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
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        on = [mock.patch.object(spaces, 'layer_on', return_value=True), mock.patch.object(spaces, 'request_space_id', return_value='x')]
        for m in on:
            m.start()
            self.addCleanup(m.stop)

    def _space(self, name, **extra):
        path = os.path.join(self.tmp.name, name)
        os.makedirs(path)
        return {'id': name, 'path': path, **extra}

    def test_plain_space_returns_module_equal_to_capabilities(self):
        sp = self._space('plain')
        mod = self.dm.publish_module(sp)
        self.assertIsInstance(mod, self.dm.Module)
        self.assertEqual(mod.id, self.dm.capabilities(sp)['publish'])
        import serve
        self.assertEqual(serve.task_preview_gate({}, None, sp), serve.MODULE_GATE_STATE)

    def test_no_provider_and_failures_are_none(self):
        liga = self._space('liga', integrations=True)
        self.assertIsNone(self.dm.capabilities(liga)['publish'])   # було 'legacy' (неявний постачальник); запасного нема (4d-4b)
        self.assertIsNone(self.dm.publish_module(liga))            # просторові з інтеграціями без запису публікація не дісталась
        for bad in (None, {}, 'x', 0):
            self.assertIsNone(self.dm.publish_module(bad))
        with mock.patch.object(self.dm, '_caps_key', side_effect=RuntimeError('збій відбитків')):
            self.assertIsNone(self.dm.publish_module(self._space('plain2')))
        broken = self._space('broken')
        with open(os.path.join(broken['path'], 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{не json')
        self.assertIsNone(self.dm.publish_module(broken))
        self.assertIsNone(self.dm.capabilities(broken)['publish'])

    def test_same_cache_as_capabilities(self):
        """Другий виклик `publish_module` після `capabilities` не перераховує ролі (той самий кеш)."""
        sp = self._space('plain3')
        self.dm.capabilities(sp)
        with mock.patch.object(self.dm, '_provider_for', side_effect=AssertionError('перерахунок')):
            self.assertIsNotNone(self.dm.publish_module(sp))

    def test_unfixed_request_space_or_layer_off_is_none(self):
        sp = self._space('plain4')
        with mock.patch.object(spaces, 'request_space_id', return_value=None):
            self.assertIsNone(self.dm.publish_module(sp))
        with mock.patch.object(spaces, 'layer_on', return_value=False):
            self.assertIsNone(self.dm.publish_module(sp))


class NoLegacyLiteral(unittest.TestCase):
    """4d-2 Task 6: у коді ядра (`app/**/*.py`, `bin/*.py`, без `test_*.py`) жодне порівняння (`Compare`: `==`, `!=`, `in`, `not in`,
    `is`, `is not`) не має сторони — рядка `'legacy'` (у т. ч. у кортежі/списку/множині). Суворий AST замість регекса Task 4:
    ловить будь-який відступ рядка, а не лише рядки з `==`. `sp.get('legacy')` і словникові ключі — `Call`/`Constant`, не `Compare`.

    ⛔ Дозволені місця — лише `ALLOWED`: пари `(файл відносно кореня, функція чи 'module')` з причиною. Зараз `ALLOWED` порожній:
    `IMPLICIT`/`_is_implicit` у `spaces.py` порівнюють з `IMPLICIT['id']`, а не з літералом, `BUILD_KINDS` і `--legacy` порівнянь
    не мають, тож винятки не потрібні.

    `ops/` поза охороною навмисно: `ops/reseal_gate.py` порівнює зовсім інший `kind` (не значення постачальника)."""

    ALLOWED = {}        # {(файл, функція): причина}

    @staticmethod
    def _is_legacy(node):
        if isinstance(node, ast.Constant):
            return node.value == 'legacy'
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return any(NoLegacyLiteral._is_legacy(e) for e in node.elts)
        return False

    @classmethod
    def offenders(cls, source, name='<src>'):
        """Список `(файл, функція, рядок)` порівнянь з `'legacy'` у тексті `source` (поза `ALLOWED`)."""
        found = []

        def walk(node, fn):
            for ch in ast.iter_child_nodes(node):
                cur = ch.name if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
                if isinstance(ch, ast.Compare) and any(cls._is_legacy(x) for x in [ch.left] + ch.comparators) \
                        and (name, cur) not in cls.ALLOWED:
                    found.append((name, cur, ch.lineno))
                walk(ch, cur)
        walk(ast.parse(source), 'module')
        return found

    def test_no_legacy_literal_comparisons_in_core(self):
        root = os.path.dirname(_HERE)
        files = [p for pat in ('app/**/*.py', 'bin/*.py') for p in glob.glob(os.path.join(root, pat), recursive=True)
                 if not os.path.basename(p).startswith('test_')]
        self.assertGreater(len(files), 20)          # охоронець не мовчить через порожній glob
        bad = []
        for path in sorted(files):
            with open(path, encoding='utf-8') as f:
                bad += self.offenders(f.read(), os.path.relpath(path, root))
        self.assertEqual(bad, [])

    def test_detector_catches_every_form(self):
        for src in ("x == 'legacy'", "'legacy' == x", "x != 'legacy'", "x in ('legacy', 'a')", "x not in ['a', 'legacy']",
                    "x in {'legacy'}", "x is 'legacy'", "x is not 'legacy'", "def f(p):\n    return p.kind == 'legacy'"):
            with self.subTest(src=src):
                self.assertEqual(len(self.offenders(src)), 1)
        for src in ("x.get('legacy')", "d = {'legacy': 1}", "x == 'legacyx'", "x in ('a', 'b')"):
            with self.subTest(src=src):
                self.assertEqual(self.offenders(src), [])

    # `test_implicit_is_not_the_public_string` ретировано (4d-4b, R6): `Implicit` видалено, порівнювати нема з чим; що неявного постачальника
    # нема ні під якою назвою, стереже `test_originals_gone.ProviderWithoutImplicit.test_the_core_has_no_fallback_names`.


class LigaLikePin(unittest.TestCase):
    """4d-2 Task 6: `serve._liga_like` = `spaces.integrations_for`; неявний простір (шар вимкнено) мусить лишатись «ЛІГОЮ»."""

    def test_implicit_space_is_liga_like(self):
        import serve
        self.assertIs(spaces.IMPLICIT['integrations'], True)
        self.assertTrue(serve._liga_like(dict(spaces.IMPLICIT)))
        self.assertFalse(serve._liga_like(None))
        self.assertFalse(serve._liga_like({'id': 'x', 'path': '/p'}))


# ⛔ Клас `IsolatedInstallConfig` (12 тестів) ретировано в 4d-4b: читачі оригіналів (`install_config.supabase_config`/`jira_config`/
# `service_key_config`) видалено, тож ізоляція їх уже нічого не відрізає. Відповідність (нічого не губимо):
#   * `…supabase_isolated_ignores_env_when_root_has_no_pair`, `…supabase_isolated_takes_the_root_pair_not_the_env`,
#     `…jira_isolated_without_root_credentials_is_none_whatever_env_and_files`, `…jira_isolated_takes_the_full_triple_from_the_root_only`,
#     `…service_key_isolated_is_none_whatever_env_and_root`, `…service_key_outside_isolation_is_the_0_15_0_pair`,
#     `…outside_isolation_matches_the_0_15_0_snapshot`  -> замінено `test_originals_gone.CommentsInIsolation`,
#     `PreviewPasswordFromTheRecord`, `DashboardSyncWithoutLegacy` і охоронцем `NoOriginalsRead` (R6: поведінки нема);
#   * `…no_import_cycle` -> замінено `test_isolation.IsolationCore.test_imports_nothing_but_os`;
#   * ВІДКЛАДЕНО на хвилю 3 (Task 14, `tests/test_liga_migrate.py`, клас `OriginalsReadersCopy`; мене там чіпати не можна): форма пари
#     (`…supabase_root_pair_form_is_checked`), вимога обох полів Jira (`…jira_root_credentials_need_both_and_the_same_form_as_env`),
#     «поза ізоляцією корінь ігнорується, працюють оточення й файли» (`…outside_isolation_the_root_credentials_are_ignored…`) і «ізоляція
#     відрізає рівно оточення й файли знімка» (`…isolation_cuts_exactly_the_env_and_files_sources_of_the_snapshot`) — проти копій
#     міграції `liga_migrate._supabase_from`/`_jira_from`. Тимчасово без покриття.

if __name__ == '__main__':
    unittest.main()
