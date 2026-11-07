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


if __name__ == '__main__':
    unittest.main()
