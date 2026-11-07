"""Рантайм без оригіналів і без запасного постачальника (етап 4d-4b): провайдер, аудит викликів. Усе на явній фікстурі ЛІГИ (`liga_fixture`):
тимчасові `HOME`/`DEAI_HOME`, вигадані значення, мережі нема. Далі в цей файл додають Task 10–11 (пароль превʼю, ланцюг ключа git, коментарі в ізоляції…)."""
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
for _p in (os.path.join(os.path.dirname(_HERE), 'app'), os.path.join(os.path.dirname(_HERE), 'bin')):
    sys.path.insert(0, _p)
import liga_fixture as lf  # noqa: E402
import deai_modules  # noqa: E402
import isolation  # noqa: E402
import spaces  # noqa: E402
import serve  # noqa: E402

ROLES = ('publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify')


def _liga(fx):
    return {'id': 'legacy', 'path': fx.space_dir, 'legacy': True, 'integrations': True}


class ProviderWithoutImplicit(unittest.TestCase):
    """Роль ЛІГИ без явного ввімкненого запису — `None`; запасного постачальника нема."""

    def test_the_core_has_no_fallback_names(self):
        for name in ('Implicit', 'IMPLICIT_ROLES', 'IMPLICIT_ON_ERROR_ROLES', 'STRICT_IMPLICIT_ROLES'):
            self.assertFalse(hasattr(deai_modules, name), name)
        with self.assertRaises(TypeError):
            deai_modules.api_value('legacy')

    def test_all_six_explicit_records_are_modules(self):
        fx = lf.LigaFixture(self).env().build()
        got = {r: deai_modules.provider(r, _liga(fx)).id for r in ROLES}
        self.assertEqual(got, {r: lf.ROLE_RECORDS[r][0] for r in ROLES})

    def test_a_liga_role_without_a_record_is_none(self):
        fx = lf.LigaFixture(self).env().build(roles=())
        for r in ROLES:
            self.assertIsNone(deai_modules.provider(r, _liga(fx)), r)

    def test_a_disabled_record_is_none(self):
        fx = lf.LigaFixture(self).env().build(overrides={'tracker': {'enabled': False}})
        self.assertIsNone(deai_modules.provider('tracker', _liga(fx)))
        self.assertEqual(deai_modules.provider('notify', _liga(fx)).id, 'supabase-teams')

    def test_an_unpinned_request_space_has_no_roles(self):
        """Простір запиту не зафіксовано → неявний простір → жодної ролі (раніше `Implicit` для шести)."""
        lf.LigaFixture(self).env().build()
        with spaces.request_space(None):
            for r in ROLES + ('tokens',):
                self.assertIsNone(deai_modules.provider(r), r)

    def test_layer_off_has_no_roles(self):
        """Шар вимкнено (`DC_TASKS_FILE` без `DEAI_HOME`): неявний простір, ролей нема, секретів нема."""
        lf.LigaFixture(self).env()
        os.environ.pop('DEAI_HOME')
        os.environ['DC_TASKS_FILE'] = '/nonexistent/tasks.json'
        for r in ROLES:
            self.assertIsNone(deai_modules.provider(r), r)
        self.assertEqual(deai_modules.read_secrets('legacy', 'supabase-comments'), {})

    def test_unreadable_space_json_is_an_error_for_every_role(self):
        """Було лише для чотирьох ролей (`STRICT_IMPLICIT_ROLES`); тепер — для всіх шести, як у звичайних просторах."""
        fx = lf.LigaFixture(self).env().build()
        with open(os.path.join(fx.space_dir, 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        deai_modules.reset_caches()
        for r in ROLES:
            with self.assertRaises(deai_modules.ModuleError, msg=r) as cm:
                deai_modules.provider(r, _liga(fx))
            self.assertEqual(cm.exception.code, 'space-json-unreadable', r)

    def test_capabilities_error_path_gives_none_not_legacy(self):
        fx = lf.LigaFixture(self).env().build()
        with open(os.path.join(fx.space_dir, 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        deai_modules.reset_caches()
        caps = deai_modules.capabilities(_liga(fx))
        self.assertEqual((caps['publish'], caps['vcs'], caps['error']), (None, None, 'space-json-unreadable'))
        self.assertNotIn('legacy', caps.values())

    def test_capabilities_total_failure_gives_none_not_legacy(self):
        """Тотальний збій відбитків: раніше `publish`/`vcs` лишались `'legacy'` у просторі з `integrations`."""
        fx = lf.LigaFixture(self).env().build()
        deai_modules.reset_caches()
        with mock.patch.object(deai_modules, 'own_sig', side_effect=RuntimeError('boom')):
            caps = deai_modules.capabilities(_liga(fx))
        self.assertEqual(caps['error'], 'module-error')
        self.assertEqual({k: v for k, v in caps.items() if k != 'error'}, {r: None for r in deai_modules.ROLES_CALLED})

    def test_publish_legacy_path_and_comment_scheme_read_only_the_module(self):
        fx = lf.LigaFixture(self).env().build()
        sp = _liga(fx)
        self.assertTrue(deai_modules.publish_legacy_path(deai_modules.provider('publish', sp), sp))
        self.assertTrue(deai_modules.comment_scheme_legacy(sp, deai_modules.provider('comments', sp)))
        self.assertFalse(deai_modules.publish_legacy_path(None, sp))
        self.assertFalse(deai_modules.comment_scheme_legacy(sp, None))


class PublishPassword(unittest.TestCase):
    """`deai_modules.publish_password(space)`: секрет `password` вбудованого `vercel-publish` у режимі `compat == design-canvas`; решта — `None`."""

    def test_secret_of_the_explicit_record(self):
        fx = lf.LigaFixture(self).env().build()
        self.assertEqual(deai_modules.publish_password(_liga(fx)), lf.PASSWORD)

    def test_no_record_or_module_mode_or_bad_space_is_none(self):
        fx = lf.LigaFixture(self).env().build(roles=())
        self.assertIsNone(deai_modules.publish_password(_liga(fx)))
        fx.build(overrides={'publish': {'settings': {'compat': ''}}})
        self.assertIsNone(deai_modules.publish_password(_liga(fx)))
        for bad in (None, {}, 'x'):
            self.assertIsNone(deai_modules.publish_password(bad))

    def test_isolated_run_in_the_real_home_is_none(self):
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        self.assertEqual(deai_modules.publish_password(_liga(fx)), lf.PASSWORD)
        with mock.patch.object(isolation, 'real_home', lambda home: True):
            self.assertIsNone(deai_modules.publish_password(_liga(fx)))


class ProviderCallersPinTheSpace(unittest.TestCase):
    """Аудит (Р4): `provider(<роль>)` БЕЗ простору мовчки дає `None`, коли простір запиту не зафіксовано (раніше — `Implicit`). Дозволені лише ті
    виклики, що йдуть із потоку запиту (простір фіксує `task_anywhere`/`set_request_space`) чи обгорнутого `_in_space` фонового потоку; новий
    однопараметровий виклик — свідоме рішення з правкою цього списку. Решта викликів (`bin/*`, `serve.comments_provider`) передають `space` явно."""

    ALLOWED = {('app/serve.py', 'team_resolve'): 'dashboard', ('app/serve.py', 'tracker_resolve'): 'tracker',
               ('app/serve.py', 'notify_resolve'): 'notify', ('app/serve.py', 'vcs_provider'): 'vcs',
               ('app/serve.py', '_publish'): 'publish', ('app/serve.py', '_overview_sync'): 'dashboard',
               ('app/serve.py', '_preview_password'): 'publish'}

    @staticmethod
    def scan(tree):
        """`{імʼя функції: роль}` для викликів `<щось>.provider('<роль>')` з ОДНИМ позиційним аргументом (простір не передано)."""
        import ast
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        out = {}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'provider' and len(n.args) == 1
                    and not n.keywords and isinstance(n.args[0], ast.Constant)):
                f = n
                while f in parents:
                    f = parents[f]
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        break
                out[getattr(f, 'name', '<module>')] = n.args[0].value
        return out

    @classmethod
    def found(cls):
        import ast
        import glob
        root = os.path.dirname(_HERE)
        out = {}
        for p in sorted(glob.glob(os.path.join(root, 'app', '*.py')) + glob.glob(os.path.join(root, 'bin', '*.py')) + glob.glob(os.path.join(root, 'ops', '*.py'))):
            if os.path.basename(p).startswith('test_'):
                continue
            with open(p, encoding='utf-8') as f:
                for fn, role in cls.scan(ast.parse(f.read())).items():
                    out[(os.path.relpath(p, root), fn)] = role
        return out

    def test_only_the_audited_callers_ask_without_a_space(self):
        self.assertEqual(self.found(), self.ALLOWED)

    def test_the_audit_can_fail(self):
        import ast
        self.assertEqual(self.scan(ast.parse("def f():\n    return deai_modules.provider('tracker')\n")), {'f': 'tracker'})
        self.assertEqual(self.scan(ast.parse("def f(sp):\n    return deai_modules.provider('tracker', sp)\n")), {})
        self.assertEqual(self.scan(ast.parse("x = m.provider('vcs')")), {'<module>': 'vcs'})


class PreviewPasswordFromTheRecord(unittest.TestCase):
    """Пароль превʼю: задача > секрет `password` запису `vercel-publish` (режим `design-canvas`) > `1100`. Корінь `tasks.json` не читається."""

    def test_task_then_secret_then_default(self):
        fx = lf.LigaFixture(self).env().build()
        sp = _liga(fx)
        self.assertEqual(serve.preview_password({'preview_password': 'task-pw'}, sp), 'task-pw')
        self.assertEqual(serve.preview_password({}, sp), lf.PASSWORD)
        fx.build(roles=tuple(r for r in lf.ALL_ROLES if r != 'publish'))
        self.assertEqual(serve.preview_password({}, sp), serve.DEFAULT_PREVIEW_PW)
        self.assertEqual(serve.preview_password(None, None), serve.DEFAULT_PREVIEW_PW)

    def test_the_root_password_is_ignored(self):
        fx = lf.LigaFixture(self).env().build(root_extra={'preview_password': 'root-pw'})
        self.assertEqual(serve.preview_password({}, _liga(fx)), lf.PASSWORD)
        fx.build(roles=(), root_extra={'preview_password': 'root-pw'})
        self.assertEqual(serve.preview_password({}, _liga(fx)), serve.DEFAULT_PREVIEW_PW)

    def test_module_mode_does_not_use_the_legacy_secret_here(self):
        """`compat` порожній: пароль у режимі модуля читає сам `publish_with_module`; `/api/task` дає типовий (так було й до 4d-4b для режиму модуля)."""
        fx = lf.LigaFixture(self).env().build(overrides={'publish': {'settings': {'compat': ''}}})
        self.assertIsNone(deai_modules.publish_password(_liga(fx)))

    def test_isolated_run_in_a_temp_home_uses_the_fixture_secret(self):
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        self.assertEqual(serve.preview_password({}, _liga(fx)), lf.PASSWORD)

    def test_isolated_run_in_the_real_home_never_reads_the_shared_secret(self):
        """Д6: ізольований прогін у СПРАВЖНЬОМУ домі — `1100`, секрет не береться (закон ізоляції)."""
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        with mock.patch.object(isolation, 'real_home', lambda home: True):
            self.assertEqual(serve.preview_password({}, _liga(fx)), serve.DEFAULT_PREVIEW_PW)

    def test_the_old_signature_is_gone(self):
        fx = lf.LigaFixture(self).env().build()
        with self.assertRaises(TypeError):
            serve.preview_password({'preview_password': 'x'}, {}, _liga(fx))

    def test_unreadable_secrets_fail_closed_not_to_1100(self):
        """t9-1: файл секретів ІСНУЄ, але не читається — помилка, а не мовчазний спільний `1100` (відкрите превʼю замість закритого)."""
        fx = lf.LigaFixture(self).env().build()
        with open(deai_modules._secrets_path(), 'w', encoding='utf-8') as f:
            f.write('{not json')
        for call in (lambda: deai_modules.publish_password(_liga(fx)),
                     lambda: serve.preview_password({}, _liga(fx))):
            with self.assertRaises(deai_modules.ModuleError) as cm:
                call()
            self.assertEqual(cm.exception.code, 'secrets-unreadable')
        self.assertEqual(serve.preview_password({'preview_password': 'task-pw'}, _liga(fx)), 'task-pw')   # пароль задачі секретів не питає

    def test_absent_secrets_file_or_key_is_the_default(self):
        fx = lf.LigaFixture(self).env().build()
        os.remove(deai_modules._secrets_path())
        self.assertIsNone(deai_modules.publish_password(_liga(fx)))
        self.assertEqual(serve.preview_password({}, _liga(fx)), serve.DEFAULT_PREVIEW_PW)


class GitChainWithoutTheRoot(unittest.TestCase):
    """Ключ і IP git: своє поле задачі > налаштування запису `git-sync`. Кореня `tasks.json` у ланцюгу нема."""

    def test_the_target_carries_only_the_tasks_own_fields(self):
        lf.LigaFixture(self).env().build(root_extra={'gitlab_ssh_key': '/root/key', 'gitlab_host_ip': '198.51.100.1'})
        settings = {'branch': 'main', 'path': 'mockup/{task}'}
        with spaces.request_space('legacy'):
            t = serve.vcs_target('a-1', {'gitlab': {'repo': 'git@example.com:o/r.git', 'path': 'mockup/a-1'}}, settings)
            self.assertNotIn('ssh_key', t)
            self.assertNotIn('host_ip', t)
            own = serve.vcs_target('a-1', {'gitlab': {'repo': 'git@example.com:o/r.git', 'path': 'mockup/a-1', 'ssh_key': '/own/key',
                                                       'host_ip': '198.51.100.9'}}, settings)
            self.assertEqual((own['ssh_key'], own['host_ip']), ('/own/key', '198.51.100.9'))
            v = serve.vcs_target('a-1', {'vcs': {'repo': 'git@example.com:o/r.git'}}, settings)
            self.assertNotIn('ssh_key', v)

    def test_gitlab_cfg_has_no_root(self):
        lf.LigaFixture(self).env().build(root_extra={'gitlab_ssh_key': '/root/key'})
        got = serve.gitlab_cfg({'gitlab': {'repo': 'r', 'path': 'p'}})
        self.assertIsNone(got['ssh_key'])
        self.assertIsNone(got['host_ip'])
        self.assertEqual(serve.gitlab_cfg({'gitlab': {'repo': 'r', 'path': 'p', 'ssh_key': '~/k'}})['ssh_key'], os.path.expanduser('~/k'))
        with self.assertRaises(TypeError):
            serve.gitlab_cfg({}, {'gitlab': {}})                      # старий підпис `gitlab_cfg(cfg, task)`

    def test_the_effective_values_come_from_the_record(self):
        """Ефективні ключ і IP для git (ціль, інакше налаштування запису) — ті самі, що давав корінь до міграції (паритет)."""
        lf.LigaFixture(self).env().build()
        with spaces.request_space('legacy'):
            _mod, ctx, _legacy = serve.vcs_provider()
        self.assertEqual((ctx['settings']['ssh_key'], ctx['settings']['host_ip']), (lf.SSH_KEY, lf.HOST_IP))


class RegistrySshKey(unittest.TestCase):
    def test_key_from_the_record_else_default_never_the_root(self):
        import registry
        fx = lf.LigaFixture(self).env().build(root_extra={'gitlab_ssh_key': '/root/key'})
        self.assertEqual(registry._ssh_key(), os.path.expanduser(lf.SSH_KEY))
        fx.build(overrides={'vcs': {'settings': {'ssh_key': '/other/key'}}})
        self.assertEqual(registry._ssh_key(), '/other/key')
        fx.build(overrides={'vcs': {'settings': {'ssh_key': ''}}}, root_extra={'gitlab_ssh_key': '/root/key'})
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))
        fx.build(roles=())
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))

    def test_layer_off_or_unreadable_registry_is_the_default(self):
        import registry
        fx = lf.LigaFixture(self).env().build()
        with open(os.path.join(fx.deai, 'spaces.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))
        os.environ.pop('DEAI_HOME')
        os.environ['DC_TASKS_FILE'] = '/nonexistent/tasks.json'
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))


class OneRoleFailsAlone(unittest.TestCase):
    def test_a_type_error_from_api_value_fails_only_that_role(self):
        """t9-4: чужий постачальник однієї ролі (не `Module`/`None`) не обвалює решту п'ять."""
        fx = lf.LigaFixture(self).env().build()
        sp = _liga(fx)
        real = deai_modules.api_value
        deai_modules._CAPS.clear()
        self.addCleanup(deai_modules._CAPS.clear)

        def picky(p):
            if getattr(p, 'id', None) == deai_modules.VCS_MODULE:
                raise TypeError('boom')
            return real(p)
        with mock.patch.object(deai_modules, 'api_value', picky):
            caps = deai_modules.capabilities(sp)
        self.assertIsNone(caps['vcs'])
        self.assertEqual(caps['error'], 'module-error')
        for role in ('publish', 'comments', 'dashboard', 'tracker', 'notify'):
            self.assertIsNotNone(caps[role], role)


class CommentsInIsolation(unittest.TestCase):
    """Д6: ізольований прогін читає облікові коментарів із запису лише в ТИМЧАСОВОМУ домі; у справжньому — `comments-isolated`."""

    def route(self, fx):
        sp = _liga(fx)
        with spaces.request_space('legacy'):
            prov, _err = serve.comments_provider(sp)
            return serve.comments_route(sp, prov)

    def test_temp_home_gives_the_fixture_context(self):
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        _mod, ctx, _ch = self.route(fx)
        self.assertEqual((ctx['settings']['url'], ctx['secrets']['key']), (lf.SB_URL, lf.SB_KEY))

    def test_real_home_is_refused(self):
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        with mock.patch.object(isolation, 'real_home', lambda home: True):
            with self.assertRaises(deai_modules.ModuleError) as cm:
                self.route(fx)
        self.assertEqual(cm.exception.code, 'comments-isolated')           # m3: окремий код, не «не налаштовано»
        self.assertNotIn('«Підключення»', cm.exception.message)
        self.assertEqual(deai_modules.STATUS['comments-isolated'], 409)

    def test_a_custom_shared_module_is_not_refused_by_the_isolation_law(self):
        """m8 (Д6: закон — для ВБУДОВАНОГО `shared_state`-запису): свій модуль (`origin != 'builtin'`) у справжньому домі не відмовляє."""
        import copy
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        sp = _liga(fx)
        with spaces.request_space('legacy'):
            prov, _err = serve.comments_provider(sp)
            custom = copy.copy(prov)
            custom.origin = 'space'
            self.assertTrue(serve._shared_module(sp, custom))
            self.assertFalse(serve._builtin_shared(sp, custom))
            with mock.patch.object(isolation, 'real_home', lambda home: True), \
                    mock.patch.object(deai_modules, 'module_ctx', lambda s, p: {'marker': 'ctx'}):
                mod, ctx, _ch = serve.comments_route(sp, custom)
                self.assertEqual(ctx, {'marker': 'ctx'})
                with self.assertRaises(deai_modules.ModuleError):      # той самий запис, вбудований — відмова
                    serve.comments_route(sp, prov)

    def test_non_isolated_uses_the_record_in_any_home(self):
        fx = lf.LigaFixture(self).env().build()
        with mock.patch.object(isolation, 'real_home', lambda home: True):
            _mod, ctx, _ch = self.route(fx)
        self.assertEqual(ctx['settings']['url'], lf.SB_URL)

    def test_a_missing_record_is_unconfigured_not_the_root(self):
        fx = lf.LigaFixture(self).env().build(roles=(), root_extra={'supabase_url': lf.SB_URL, 'supabase_key': lf.SB_KEY})
        sp = _liga(fx)
        with spaces.request_space('legacy'):
            prov, _err = serve.comments_provider(sp)
        self.assertIsNone(prov)


class DashboardSyncWithoutLegacy(unittest.TestCase):
    def test_no_dashboard_record_means_no_provider_even_with_the_service_key(self):
        import overview_push
        fx = lf.LigaFixture(self).env(SUPABASE_URL=lf.SB_URL, SUPABASE_SERVICE_KEY='service-key-alpha').build(roles=())
        self.assertEqual(overview_push._target(_liga(fx)), (None, None, False))
        self.assertFalse(hasattr(overview_push, '_legacy_config'))

    def test_discover_without_a_dashboard_record_names_the_missing_provider(self):
        """m6: ЛІГА без запису дашборда — «нема постачальника», а не «лише для простору ЛІГА» (той самий текст, що в `cmd_sync`)."""
        import overview_push
        fx = lf.LigaFixture(self).env().build(roles=())
        with self.assertRaises(overview_push.CliError) as cm:
            self._discover(overview_push, fx)
        self.assertIn('нема постачальника командного дашборда', str(cm.exception))
        self.assertNotIn('лише для простору ЛІГА', str(cm.exception))

    @staticmethod
    def _discover(overview_push, fx):
        with mock.patch.object(overview_push, '_space', lambda sid=None: _liga(fx)):
            return overview_push.cmd_discover(log=lambda *a: None)

    def test_with_the_record_the_module_ctx_is_used(self):
        import overview_push
        fx = lf.LigaFixture(self).env().build()
        mod, ctx, legacy = overview_push._target(_liga(fx))
        self.assertEqual((mod.id, ctx['settings']['url'], legacy), ('supabase-dashboard', lf.SB_URL, True))


class TextsNameTheConnectionsScreen(unittest.TestCase):
    def test_no_text_sends_the_person_to_tasks_json(self):
        import dashboard
        import notify
        import tracker
        for text in (serve.COMMENTS_UNCONFIGURED, dashboard.UNCONFIGURED, notify.UNCONFIGURED, tracker.UNCONFIGURED):
            self.assertIn('«Підключення»', text)
            for bad in ('tasks.json', 'jira_base', 'JIRA_EMAIL', 'JIRA_TOKEN', 'supabase_url'):
                self.assertNotIn(bad, text)


if __name__ == '__main__':
    unittest.main()
