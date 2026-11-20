"""Рантайм без оригіналів і без запасного постачальника (етап 4d-4b): провайдер, аудит викликів. Усе на явній фікстурі ЛІГИ (`liga_fixture`):
тимчасові `HOME`/`DEAI_HOME`, вигадані значення, мережі нема. Далі в цей файл додають Task 10–11 (пароль превʼю, ланцюг ключа git, коментарі в ізоляції…)."""
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
for _p in (os.path.join(os.path.dirname(_HERE), 'app'), os.path.join(os.path.dirname(_HERE), 'bin'), os.path.join(os.path.dirname(_HERE), 'ops')):
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

    def test_an_enabled_record_that_cannot_be_served_is_an_error_for_every_role(self):
        """I2 (рішення контролера): ЯВНО ввімкнений запис вбудованого модуля, якого нема в каталозі чи який не `ok`, — `module-error` для КОЖНОЇ з шести
        ролей, а не мовчазне `None`. Без запису чи з вимкненим — `None`; чужа роль цим не зачеплена."""
        fx = lf.LigaFixture(self).env().build()
        real = deai_modules.catalog(_liga(fx))
        for role in ROLES:
            mid = lf.ROLE_RECORDS[role][0]
            broken = deai_modules.Module(mid, roles=[role], status='error', error='x', error_code='module-error')
            for name, cat in (('missing', {k: v for k, v in real.items() if k != mid}), ('broken', dict(real, **{mid: broken})),
                              ('empty', {})):
                with self.subTest(role=role, catalog=name), mock.patch.object(deai_modules, 'catalog', return_value=cat):
                    with self.assertRaises(deai_modules.ModuleError) as cm:
                        deai_modules.provider(role, _liga(fx))
                    self.assertEqual(cm.exception.code, 'module-error')
                    other = next(r for r in ROLES if r != role)
                    if name != 'empty':                                              # живий модуль іншої ролі далі веде свою
                        self.assertEqual(deai_modules.provider(other, _liga(fx)).id, lf.ROLE_RECORDS[other][0])
        for role in ROLES:                                                            # запису нема / вимкнений — як було, `None`
            mid = lf.ROLE_RECORDS[role][0]
            for kw in ({'roles': ()}, {'overrides': {role: {'enabled': False}}}):
                fx.build(**kw)
                with self.subTest(role=role, case=sorted(kw)[0]), mock.patch.object(deai_modules, 'catalog', return_value={}):
                    self.assertIsNone(deai_modules.provider(role, _liga(fx)))

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
        self.assertEqual({k: v for k, v in caps.items() if k not in ('error', 'errors')}, {r: None for r in deai_modules.ROLES_CALLED})

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
    """Аудит (Р4): `provider(<роль>)` БЕЗ простору мовчки дає `None`, коли простір запиту не зафіксовано (раніше — `Implicit`). Сканер бачить
    КОЖЕН виклик `provider(…)`/`comments_provider(…)` (рахує, а не ключує словником, тож другий виклик тієї ж ролі в тій самій функції теж
    видно) у будь-якій формі: `deai_modules.provider(…)`, голе `provider(…)` після `from deai_modules import provider`, роль не літералом
    (`provider(role)`), простір відсутній / літерал `None` / імʼя / інший вираз, позиційно чи `space=`. Точний набір пінується буквально:
    новий виклик, нова форма чи зміна кількості — свідоме рішення з правкою списку. Виклики «без простору» (`absent`) дозволені лише з потоку
    запиту (простір фіксує `task_anywhere`/`set_request_space`) чи обгорнутого `_in_space` фонового потоку; решта передає `space` явно
    (`name`: змінна простору, яку вирішив викликач)."""

    CALLEES = {'provider': 1, 'comments_provider': 0}   # імʼя -> позиція аргументу простору
    #: (файл, функція, виклик, роль, форма простору) -> кількість викликів.
    ALLOWED = {
        ('app/serve.py', 'team_resolve', 'provider', 'dashboard', 'absent'): 1,
        ('app/serve.py', 'tracker_resolve', 'provider', 'tracker', 'absent'): 1,
        ('app/serve.py', 'notify_resolve', 'provider', 'notify', 'absent'): 1,
        ('app/serve.py', 'vcs_provider', 'provider', 'vcs', 'absent'): 1,
        ('app/serve.py', 'Handler._publish', 'provider', 'publish', 'absent'): 1,
        ('app/serve.py', 'Handler._overview_sync', 'provider', 'dashboard', 'absent'): 1,
        ('app/serve.py', 'Handler._preview_password', 'provider', 'publish', 'absent'): 1,
        # Форма `name` — лише ВИГЛЯД аргументу в коді: змінна `space` може бути `None` під час роботи, і `serve.comments_provider` свідомо
        # ставить `space = None` (~3055: шар вимкнено чи простір запиту не зафіксовано → неявний простір → роль `comments` дає `None`, не збій).
        ('app/serve.py', 'comments_provider', 'provider', 'comments', 'name'): 1,
        ('app/serve.py', 'ds_tokens_view', 'provider', 'tokens', 'name'): 1,
        ('app/serve.py', 'published_target', 'provider', 'publish', 'name'): 1,
        # 0.33.0: пароль превʼю в списку просторів і в просторі задачі — простір передано явно (форма `name`)
        ('app/serve.py', '_publish_password', 'provider', 'publish', 'name'): 1,
        ('app/serve.py', 'ProjectComments.__init__', 'comments_provider', 'comments', 'name'): 1,
        ('app/serve.py', 'publish_comments', 'comments_provider', 'comments', 'name'): 1,
        ('app/serve.py', 'Handler._commented', 'comments_provider', 'comments', 'name'): 1,
        ('app/serve.py', 'Handler._comment_config', 'comments_provider', 'comments', 'name'): 1,
        ('bin/overview_push.py', '_target', 'provider', 'dashboard', 'name'): 1,
        ('bin/overview_push.py', '_statuses', 'provider', 'tracker', 'name'): 1,
        ('bin/overview_push.py', '_channel_of', 'provider', 'comments', 'name'): 1,
    }

    @classmethod
    def scan(cls, tree):
        """Список `(функція, виклик, роль, форма простору)` для КОЖНОГО виклику; роль — літерал або `<non-literal>`; форма — `absent`/`None`/
        `name`/`other`. Імпорт `from deai_modules import provider` дає `('<module>', 'import', 'provider', 'from-import')`."""
        import ast
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}

        def where(n):
            names = []
            while n in parents:
                n = parents[n]
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.append(n.name)
            return '.'.join(reversed(names)) or '<module>'
        out = []
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and any(a.name in cls.CALLEES for a in n.names):
                out.append((where(n), 'import', 'provider', 'from-import'))
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            callee = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if callee not in cls.CALLEES:
                continue
            pos = cls.CALLEES[callee]
            role_node = n.args[0] if callee == 'provider' and n.args else None
            role = ('comments' if callee == 'comments_provider' else
                    role_node.value if isinstance(role_node, ast.Constant) and isinstance(role_node.value, str) else '<non-literal>')
            sp = n.args[pos] if len(n.args) > pos else next((k.value for k in n.keywords if k.arg == 'space'), None)
            if sp is None:
                form = 'absent'
            elif isinstance(sp, ast.Constant) and sp.value is None:
                form = 'None'
            elif isinstance(sp, ast.Name):
                form = 'name'
            else:
                form = 'other'
            out.append((where(n), callee, role, form))
        return out

    @staticmethod
    def files():
        """Усі `.py` без `test_*`: `app/` РЕКУРСИВНО (`app/modules/*/*.py` теж, як у `NoOriginalsRead`), `bin/*.py`, `ops/*.py`."""
        import glob
        root = os.path.dirname(_HERE)
        walked = []
        for base, _d, fs in os.walk(os.path.join(root, 'app')):
            walked += [os.path.join(base, f) for f in fs if f.endswith('.py')]
        walked += glob.glob(os.path.join(root, 'bin', '*.py')) + glob.glob(os.path.join(root, 'ops', '*.py'))
        return sorted(p for p in walked if not os.path.basename(p).startswith('test_'))

    def test_the_scan_reaches_the_module_servers(self):
        rel = {os.path.relpath(p, os.path.dirname(_HERE)) for p in self.files()}
        self.assertTrue({r for r in rel if r.startswith(os.path.join('app', 'modules') + os.sep)}, 'app/modules/*/*.py не скановано')
        self.assertIn(os.path.join('app', 'serve.py'), rel)
        self.assertIn(os.path.join('ops', 'reseal_gate.py'), rel)

    @classmethod
    def found(cls):
        import ast
        import collections
        root = os.path.dirname(_HERE)
        out = collections.Counter()
        for p in cls.files():
            with open(p, encoding='utf-8') as f:
                for hit in cls.scan(ast.parse(f.read())):
                    out[(os.path.relpath(p, root),) + hit] += 1
        return out

    def test_only_the_audited_callers_ask_without_a_space(self):
        self.assertEqual(dict(self.found()), self.ALLOWED)

    def test_the_audit_can_fail(self):
        import ast
        s = lambda src: self.scan(ast.parse(src))  # noqa: E731
        self.assertEqual(s("def f():\n    return deai_modules.provider('tracker')\n"), [('f', 'provider', 'tracker', 'absent')])
        self.assertEqual(s("def f(sp):\n    return deai_modules.provider('tracker', sp)\n"), [('f', 'provider', 'tracker', 'name')])
        self.assertEqual(s("x = m.provider('vcs')"), [('<module>', 'provider', 'vcs', 'absent')])
        # другий виклик тієї ж ролі в тій самій функції — два записи, а не один
        self.assertEqual(len(s("def f():\n    a = m.provider('vcs')\n    b = m.provider('vcs')\n")), 2)
        # роль не літералом
        self.assertEqual(s("def f(role):\n    return m.provider(role)\n"), [('f', 'provider', '<non-literal>', 'absent')])
        # форма `from deai_modules import provider` і голий виклик
        self.assertIn(('<module>', 'import', 'provider', 'from-import'), s("from deai_modules import provider"))
        self.assertEqual(s("def f():\n    return provider('vcs')\n"), [('f', 'provider', 'vcs', 'absent')])
        # явний None, простір ключем, обгортка comments_provider
        self.assertEqual(s("def f():\n    return m.provider('vcs', None)\n"), [('f', 'provider', 'vcs', 'None')])
        self.assertEqual(s("def f():\n    return m.provider('vcs', space=None)\n"), [('f', 'provider', 'vcs', 'None')])
        self.assertEqual(s("def f():\n    return serve.comments_provider(space=None)\n"), [('f', 'comments_provider', 'comments', 'None')])
        self.assertEqual(s("def f():\n    return serve.comments_provider()\n"), [('f', 'comments_provider', 'comments', 'absent')])
        self.assertEqual(s("def f():\n    return serve.comments_provider(sp)\n"), [('f', 'comments_provider', 'comments', 'name')])
        self.assertEqual(s("def f():\n    return m.provider('vcs', a.b)\n"), [('f', 'provider', 'vcs', 'other')])


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


class UnreadableSecretsConsumers(unittest.TestCase):
    """t11-I1: файл секретів ІСНУЄ, але не читається — кожен споживач пароля превʼю відмовляє вголос (fail-closed), а не падає в `1100`.
    Справжній `Handler` на тимчасовому домі (як `test_spaces_serve`), задача в просторі ЛІГИ із записом `vercel-publish`; мережі нема."""

    def setUp(self):
        import json
        import threading
        self.fx = lf.LigaFixture(self).env(DC_NO_OVERVIEW='1', DC_IDENTITY_NAME='Lead', DC_IDENTITY_EMAIL='lead@example.com')
        tdir = os.path.join(self.fx.tmp, 'work', 'a')
        os.makedirs(os.path.join(tdir, 'iterations', 'it1'))
        with open(os.path.join(tdir, 'iterations.json'), 'w', encoding='utf-8') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'n', 'published': True}], 'publish_url': None}, f)
        with open(os.path.join(tdir, 'iterations', 'it1', 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<!DOCTYPE html><html><body>x</body></html>')
        self.tdir = tdir
        self.fx.build(tasks={'a': {'title': 'A', 'dir': tdir, 'track': 'tool'}}, root_extra={'current': 'a'})
        with open(deai_modules._secrets_path(), 'w', encoding='utf-8') as f:
            f.write('{not json')
        deai_modules.reset_caches()
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        self.httpd = serve.make_server(0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.base = 'http://127.0.0.1:%d' % self.httpd.server_address[1]

    def call(self, path, payload=None):
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(self.base + path, method='GET' if payload is None else 'POST',
                                     data=None if payload is None else json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode('utf-8'))

    @staticmethod
    def raw(path):
        with open(path, 'rb') as f:
            return f.read()

    def test_api_task_degrades_with_the_error_and_no_default(self):
        st, body = self.call('/api/task')
        self.assertEqual(st, 200, body)
        self.assertEqual(body['preview_password_error'], 'secrets-unreadable')
        self.assertIsNone(body['preview_password'])
        self.assertEqual(body['preview_gate']['state'], 'none')
        self.assertNotIn(serve.DEFAULT_PREVIEW_PW, str(body['preview_password']))

    def test_publish_is_refused_before_the_build(self):
        st, body = self.call('/api/publish', {'build_only': True})
        self.assertEqual((st, body['code'], body['error']), (409, 'secrets-unreadable', serve.SECRETS_UNREADABLE_TEXT), body)
        self.assertFalse(os.path.exists(os.path.join(self.tdir, 'publish')))

    def test_clearing_the_password_is_refused_and_the_task_file_is_untouched(self):
        before = self.raw(self.fx.tasks_path)
        st, body = self.call('/api/preview-password', {'password': ''})
        self.assertEqual((st, body['code']), (409, 'secrets-unreadable'), body)
        self.assertEqual(self.raw(self.fx.tasks_path), before)

    def test_setting_a_nonempty_password_does_not_need_the_secrets(self):
        """m4: свій пароль задачі секретів не питає — запис проходить, навіть коли файл секретів зіпсовано."""
        import json
        st, body = self.call('/api/preview-password', {'password': 'abcd'})
        self.assertEqual((st, body.get('preview_password')), (200, 'abcd'), body)
        with open(self.fx.tasks_path, encoding='utf-8') as f:
            self.assertEqual(json.load(f)['tasks']['a']['preview_password'], 'abcd')
        # fp-2: усе, що людина бачить ПІСЛЯ, теж живе без секретів (файл секретів і далі зіпсовано).
        st, body = self.call('/api/task')                                    # знімок задачі: пароль задачі, помилки нема
        self.assertEqual(st, 200, body)
        self.assertEqual((body['preview_password'], body['preview_password_custom']), ('abcd', True))
        self.assertNotIn('preview_password_error', body)
        st, body = self.call('/api/publish', {'build_only': True})           # збірка: гейт із паролем задачі, а не типовий 1100
        self.assertEqual((st, body.get('ok')), (200, True), body)
        with open(os.path.join(self.tdir, 'publish', 'index.html'), encoding='utf-8') as f:
            wrapper = f.read()
        self.assertIn('abcd', wrapper)
        self.assertNotIn(serve.DEFAULT_PREVIEW_PW, wrapper)
        before = self.raw(self.fx.tasks_path)
        st, body = self.call('/api/preview-password', {'password': ''})      # зняти власний — пароль упав би в 1100: відмова, файл не змінено
        self.assertEqual((st, body['code']), (409, 'secrets-unreadable'), body)
        self.assertEqual(self.raw(self.fx.tasks_path), before)

    def test_secrets_breaking_between_the_probe_and_the_save_is_a_clean_refusal(self):
        """fp-1: зняття власного пароля — пробна перевірка секретів ПРОЙШЛА, а друге читання (після зміни задачі) їх уже не бачить: відповідь — чиста
        409 `secrets-unreadable` (не 500), а `tasks.json` НЕ змінено (результат рахуємо ДО запису)."""
        import json
        with open(self.fx.tasks_path, encoding='utf-8') as f:
            cfg = json.load(f)
        cfg['tasks']['a']['preview_password'] = 'oldpw'
        with open(self.fx.tasks_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)
        before = self.raw(self.fx.tasks_path)
        boom = deai_modules.ModuleError('secrets-unreadable', message='x')
        with mock.patch.object(deai_modules, 'publish_password', side_effect=[None, boom]) as pp:
            st, body = self.call('/api/preview-password', {'password': ''})
        self.assertEqual(pp.call_count, 2)
        self.assertEqual((st, body.get('code'), body.get('error')), (409, 'secrets-unreadable', serve.SECRETS_UNREADABLE_TEXT), body)
        self.assertEqual(self.raw(self.fx.tasks_path), before)

    def test_reseal_gate_skips_the_task_and_keeps_its_wrapper(self):
        import contextlib
        import io
        import json
        import reseal_gate
        pub = os.path.join(self.tdir, 'publish')
        os.makedirs(pub)
        with open(os.path.join(pub, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump({'build': 'legacy', 'shell': serve.PREVIEW_SHELL_VERSION}, f)
        idx = os.path.join(pub, 'index.html')
        with open(idx, 'w', encoding='utf-8') as f:
            f.write('<html>old wrapper</html>')
        before = self.raw(idx)
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['reseal_gate.py', '--build', 'a']), contextlib.redirect_stdout(out):
            reseal_gate.main()
        self.assertIn('секрети простору не читаються', out.getvalue())
        self.assertEqual(self.raw(idx), before)


class PublishIsAlwaysPinned(unittest.TestCase):
    """fp-3: `_publish` береться за простір лише коли запит ним зафіксовано; без нього `publish_password(None)` дав би `None` і гейт упав би в `1100`.
    Справжній `Handler`, простір ЛІГА з секретом `password` запису `vercel-publish` (шар увімкнено): КОЖНА форма запиту (без назви задачі, заголовок
    `X-Canvas-Task`, префікс `/t/<id>/`) мусить фіксуватися, а гейт збірки — нести секрет запису, а не типовий пароль."""
    SECRET = 'sec-from-record-7'

    def setUp(self):
        import json
        import threading
        self.fx = lf.LigaFixture(self).env(DC_NO_OVERVIEW='1', DC_IDENTITY_NAME='Lead', DC_IDENTITY_EMAIL='lead@example.com')
        tdir = os.path.join(self.fx.tmp, 'work', 'a')
        os.makedirs(os.path.join(tdir, 'iterations', 'it1'))
        with open(os.path.join(tdir, 'iterations.json'), 'w', encoding='utf-8') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'n', 'published': True}], 'publish_url': None}, f)
        with open(os.path.join(tdir, 'iterations', 'it1', 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<!DOCTYPE html><html><body>x</body></html>')
        self.tdir = tdir
        self.fx.build(tasks={'a': {'title': 'A', 'dir': tdir, 'track': 'tool'}}, root_extra={'current': 'a'},
                      overrides={'publish': {'secrets': {'password': self.SECRET}}})
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        self.httpd = serve.make_server(0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.base = 'http://127.0.0.1:%d' % self.httpd.server_address[1]

    def _publish(self, path, headers=None):
        import json
        import urllib.request
        req = urllib.request.Request(self.base + path, method='POST', data=json.dumps({'build_only': True}).encode(),
                                     headers=dict({'Content-Type': 'application/json'}, **(headers or {})))
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode('utf-8'))

    def test_every_request_shape_is_pinned_and_the_gate_uses_the_record_secret(self):
        orig = deai_modules.publish_password
        seen = []

        def spy(space):
            seen.append((space, spaces.request_space_id()))
            return orig(space)
        shapes = (('/api/publish', None), ('/api/publish', {'X-Canvas-Task': 'a'}), ('/t/a/api/publish', None))
        for path, headers in shapes:
            del seen[:]
            with mock.patch.object(deai_modules, 'publish_password', side_effect=spy):
                st, body = self._publish(path, headers)
            self.assertEqual((st, body.get('ok')), (200, True), (path, body))
            self.assertTrue(seen, path)
            for space, pin in seen:
                self.assertIsNotNone(pin, path)                      # запит зафіксовано…
                self.assertIsInstance(space, dict, path)             # …тож `_publish` бере простір, а не `None`
                self.assertEqual(space.get('id'), 'legacy', path)
            with open(os.path.join(self.tdir, 'publish', 'index.html'), encoding='utf-8') as f:
                wrapper = f.read()
            self.assertIn(self.SECRET, wrapper, path)
            self.assertNotIn(serve.DEFAULT_PREVIEW_PW, wrapper, path)


class RegistrySshKeyRecord(unittest.TestCase):
    """m1: `git-sync` з `enabled: false` — ключ не береться; `sys.path` доповнюється один раз."""

    def test_a_disabled_git_sync_record_gives_the_default(self):
        import registry
        lf.LigaFixture(self).env().build(overrides={'vcs': {'enabled': False, 'settings': {'ssh_key': '/other/key'}}})
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))

    def test_sys_path_is_not_grown_by_repeated_calls(self):
        import registry
        lf.LigaFixture(self).env().build()
        registry._ssh_key()
        n = len(sys.path)
        registry._ssh_key()
        registry._ssh_key()
        self.assertEqual(len(sys.path), n)


class ResealGateRegistryEdges(unittest.TestCase):
    """m2: `liga_space()` без ключа `spaces` не падає; `rebuild_index` із нечитабельними секретами пропускає, а не падає."""

    def test_liga_space_survives_a_registry_without_spaces(self):
        import reseal_gate
        for reg in ({'version': 1}, {'spaces': None}):
            with mock.patch.object(spaces, 'read_registry', lambda reg=reg: reg):
                self.assertIsNone(reseal_gate.liga_space())

    def test_rebuild_index_with_unreadable_secrets_is_skipped(self):
        import json
        import reseal_gate
        fx = lf.LigaFixture(self).env().build()
        tdir = os.path.join(fx.tmp, 'work', 'a')
        pub = os.path.join(tdir, 'publish')
        os.makedirs(pub)
        with open(os.path.join(pub, 'index.html'), 'w', encoding='utf-8') as f:
            f.write('old')
        with open(os.path.join(tdir, 'iterations.json'), 'w', encoding='utf-8') as f:
            json.dump({'iterations': [{'id': 'it1', 'published': True}]}, f)
        with open(deai_modules._secrets_path(), 'w', encoding='utf-8') as f:
            f.write('{not json')
        deai_modules.reset_caches()
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):                 # попередження — друк у stdout; ловимо, щоб не шуміло і було перевірено
            res = reseal_gate.rebuild_index('a', {'dir': tdir})
        self.assertIsNone(res)
        self.assertIn('секрети простору не читаються', out.getvalue())
        self.assertIn('a:', out.getvalue())
        with open(os.path.join(pub, 'index.html'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'old')


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
        self.assertEqual(caps['errors'], {'vcs': 'module-error'}, 'r15-1: помилка названа за роллю')


class CapabilityErrorsArePerRole(unittest.TestCase):
    """r15-1: `capabilities.error` читав клієнт як «space.json не читається» для БУДЬ-ЯКОГО коду й ховав усі картки. Тепер
    простір-рівневе — лише `space-json-unreadable` (без `errors`), а збій модуля однієї ролі названий в `errors[роль]`."""

    def setUp(self):
        self.fx = lf.LigaFixture(self).env().build()
        deai_modules.reset_caches()
        self.addCleanup(deai_modules.reset_caches)

    def test_unreadable_space_json_is_space_level_without_a_role_map(self):
        with open(os.path.join(self.fx.space_dir, 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        caps = deai_modules.capabilities(_liga(self.fx))
        self.assertEqual(caps['error'], 'space-json-unreadable')
        self.assertNotIn('errors', caps)

    def test_a_module_lost_by_one_role_names_that_role_only(self):
        real = deai_modules._provider_for

        def lost(role, space, *rest):
            if role == 'vcs':
                raise deai_modules.ModuleError('module-error', message='git-sync не завантажився')
            return real(role, space, *rest)
        with mock.patch.object(deai_modules, '_provider_for', lost):
            caps = deai_modules.capabilities(_liga(self.fx))
        self.assertEqual(caps['errors'], {'vcs': 'module-error'})
        self.assertIsNone(caps['vcs'])
        for role in ('publish', 'comments', 'dashboard', 'tracker', 'notify'):
            self.assertIsNotNone(caps[role], role)

    def test_space_level_error_wins_over_an_earlier_module_error(self):
        real = deai_modules._provider_for

        def mixed(role, space, *rest):
            if role == 'publish':
                raise deai_modules.ModuleError('module-error', message='раніше за порядком')
            if role == 'comments':
                raise deai_modules.ModuleError(deai_modules.SPACE_LEVEL_ERROR, message='space.json')
            return real(role, space, *rest)
        with mock.patch.object(deai_modules, '_provider_for', mixed):
            caps = deai_modules.capabilities(_liga(self.fx))
        self.assertEqual(caps['error'], deai_modules.SPACE_LEVEL_ERROR)
        self.assertEqual(caps['errors']['publish'], 'module-error')

    def test_the_cache_does_not_share_the_errors_dict(self):
        real = deai_modules._provider_for

        def lost(role, space, *rest):
            if role == 'vcs':
                raise deai_modules.ModuleError('module-error', message='x')
            return real(role, space, *rest)
        with mock.patch.object(deai_modules, '_provider_for', lost):
            first = deai_modules.capabilities(_liga(self.fx))
            first['errors']['vcs'] = 'tampered'
            second = deai_modules.capabilities(_liga(self.fx))
            second['errors']['x'] = 1
            third = deai_modules.capabilities(_liga(self.fx))
        self.assertEqual(third['errors'], {'vcs': 'module-error'})

    def test_a_total_failure_names_every_role(self):
        with mock.patch.object(deai_modules, 'own_sig', side_effect=RuntimeError('boom')):
            caps = deai_modules.capabilities(_liga(self.fx))
        self.assertEqual(caps['errors'], {r: 'module-error' for r in deai_modules.ROLES_CALLED})


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
        self.assertNotIn('«Налаштування»', cm.exception.message)
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
            self.assertIn('«Налаштування»', text)
            for bad in ('tasks.json', 'jira_base', 'JIRA_EMAIL', 'JIRA_TOKEN', 'supabase_url'):
                self.assertNotIn(bad, text)


if __name__ == '__main__':
    unittest.main()
