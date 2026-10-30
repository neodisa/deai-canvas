"""`app/modules/vercel-publish`, режим `cli` (4b-1): публікація через СИСТЕМНИЙ Vercel CLI (`npx --yes vercel …`).

Модуль вантажиться через справжній `deai_modules.catalog()`, а світ тесту — той самий, що в `tests/test_vercel_publish.py`
(`tvp.Base`: тимчасові `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`, `spaces_guard`, `Tripwire`, що пропускає лише `127.0.0.1`).
Нового тут два шви:
  * ФАЛЬШИВИЙ `npx` (`tests/fake_npx.py`) — справжній виконуваний файл у тимчасовій теці: журнал argv/cwd, відповіді за
    підкомандою. Жодного справжнього `vercel`/`npx vercel` і жодної мережі;
  * `_fetch_page` у глобалах модуля — перевірка превʼю (адреса `https://….vercel.app` — це мережа, тож її підміняє тест;
    сама функція перевіряється окремо проти локального сервера).
Модуль повертає КОДИ (`vercel-login`…) із сирим текстом у `ModuleError.full`; людських текстів ЛІГИ тут нема й бути не
мусить — вони в ядрі.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import types
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402
import fake_npx  # noqa: E402
import spaces_guard  # noqa: E402
import serve  # noqa: E402  — лише `_checked_url_result`: ті самі правила перевірки відповіді, що в ядра
import test_vercel_publish as tvp  # noqa: E402  — світ тесту (`Base`) і підставні сервери; його тести сюди не потрапляють

MID = tvp.MID
TOKEN = 'vcp_SECRET-x'
D = 'https://pv-12345678-abc.vercel.app'
A = 'https://pv-12345678.vercel.app'
PAGE_OK = (200, '', '<div id="authgate">')
_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class _SubSpy:
    """Підміна `subprocess` у глобалах модуля: пише кожен виклик `run` (argv + kwargs) і віддає справжній `subprocess.run`,
    а `handler(argv, kw)` може підмінити відповідь чи кинути виняток. Решта — як у справжнього `subprocess`."""
    SubprocessError = subprocess.SubprocessError
    TimeoutExpired = subprocess.TimeoutExpired
    CompletedProcess = subprocess.CompletedProcess

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler

    def run(self, argv, **kw):
        self.calls.append((list(argv), kw))
        if self.handler is not None:
            res = self.handler(list(argv), kw)
            if res is not None:
                return res
        return subprocess.run(argv, **kw)


class CliBase(tvp.Base):
    def setUp(self):
        super().setUp()
        # Ізоляція від справжнього `~/.deai` — у `tvp.Base.setUp`; тут вона ще й названа явно (охоронець `test_serve.py` шукає
        # присвоєння `DEAI_HOME` у КОЖНОМУ файлі, що пише простори) і перевіряється: домівка — під тимчасовою текою.
        os.environ['DEAI_HOME'] = self.deai
        self.assertTrue(self.deai.startswith(self.tmp + os.sep))
        self.fx = os.path.join(self.tmp, 'fx')
        self.npx_path = None
        self.pages = []

    # ---- фікстури
    def scenario(self, sc):
        """Скласти фальшивий `npx` зі сценарієм; повертає шлях до нього."""
        self.npx_path = fake_npx.make(self.fx, sc)
        return self.npx_path

    def cli_ctx(self, team=None, token=None, npx=True, auth='cli'):
        """Справжній `ctx` ядра (`module_ctx`) простору з `auth: cli`; `find_tool` — на фальшивий `npx` (або `None`)."""
        settings = {'auth': auth}
        if team is not None:
            settings['team'] = team
        dm.write_module_state(self.sp, MID, settings=settings)
        if token is not None:
            dm.write_secrets(self.sp['id'], MID, {'token': token})
        ctx = dm.module_ctx(self.sp, MID)
        path = self.npx_path if npx else None
        ctx['find_tool'] = lambda name: path if name == 'npx' else None
        return ctx

    def calls(self):
        return fake_npx.calls(self.fx)

    def argvs(self):
        return [c['argv'] for c in self.calls()]

    def run_cli(self, ctx=None, state=None, tid='t1', gated=True, page=PAGE_OK, core=False, spy=None, **ctx_kw):
        """Публікація. `core=True` — через `dm.call` (як диспетчер); інакше — функція модуля напряму."""
        ctx = ctx if ctx is not None else self.cli_ctx(**ctx_kw)
        task = {'id': tid, 'title': 'T', 'dir': self.hp('t', tid), 'gated': gated,
                'state': {'project': 'pv-12345678', 'task': tid} if state is None else state}
        g = self.fn('publish').__globals__

        def fetch(url):
            self.pages.append(url)
            return page(url) if callable(page) else page
        over = {'_fetch_page': fetch}
        if spy is not None:
            over['subprocess'] = spy
        with mock.patch.dict(g, over):
            if core:
                return dm.call(self.m, 'publish', ctx, self.build, task)
            return self.fn('publish')(ctx, self.build, task)

    def fails(self, **kw):
        try:
            self.run_cli(**kw)
        except BaseException as e:  # noqa: BLE001
            return e
        self.fail('очікували виняток')

    def ok_sc(self, **over):
        """Типовий успішний сценарій: `deploy` друкує D, `inspect` — A, `link` пише org."""
        sc = {'link': {'code': 0, 'org': 'team_x'}, 'deploy': {'code': 0, 'stdout': D + '\n'},
              'inspect': {'code': 0, 'stdout': A + '\n'},
              'list': {'code': 0, 'stdout': json.dumps({'deployments': []})}}      # порожній список: нічого прибирати
        sc.update(over)
        return self.scenario(sc)


# ---------------------------------------------------------------------------------------- 1: успіх і форма результату

class Success(CliBase):
    def test_1_success_with_the_gate(self):
        self.ok_sc(**{'list': {'code': 0, 'stdout': json.dumps({'deployments': []})}})
        res = self.run_cli()
        self.assertEqual(res, {'url': A, 'deploy_url': D, 'verified': True, 'verify': None, 'warnings': [],
                               'cleanup_warning': None,
                               'state': {'project': 'pv-12345678', 'scope': 'team_x', 'task': 't1'}})
        self.assertEqual(self.argvs(), [
            ['--yes', 'vercel', 'link', '--yes', '--project', 'pv-12345678'],
            ['--yes', 'vercel', 'deploy', '--prod', '--yes'],
            ['--yes', 'vercel', 'inspect', D],
            ['--yes', 'vercel', 'list', 'pv-12345678', '--json']])   # рівно в такому порядку; `list` — прибирання (Task 3), порожній список
        real = os.path.realpath(self.build)
        self.assertEqual({c['cwd'] for c in self.calls()}, {real})   # cwd — тека збірки
        self.assertEqual(self.pages, [A])                            # перевірялась найкоротша адреса

    def test_the_result_passes_the_core_shape_check(self):
        """Ядро (`serve._checked_url_result`) приймає відповідь режиму `cli`: зайві ключі (`deploy_url`, `verify`,
        `cleanup_warning`) воно не читає, а `state` — пласкі рядки (без `None`)."""
        self.ok_sc()
        res = self.run_cli(core=True)
        url, state, verified, warnings = serve._checked_url_result(res)
        self.assertEqual((url, verified, warnings), (A, True, []))
        self.assertEqual(state, {'project': 'pv-12345678', 'scope': 'team_x', 'task': 't1'})
        # і без скоупу: ключа `scope` у стані нема (а не `None`)
        shutil.rmtree(os.path.join(self.build, '.vercel'))             # від першого запуску лишився `project.json`
        self.ok_sc(link={'code': 0})
        res = self.run_cli(core=True)
        url, state, verified, warnings = serve._checked_url_result(res)
        self.assertEqual(state, {'project': 'pv-12345678', 'task': 't1'})

    def test_state_scope_is_not_replaced_by_the_link_file(self):
        self.ok_sc(link={'code': 0, 'org': 'team_other'})
        res = self.run_cli(state={'project': 'pv-12345678', 'task': 't1', 'scope': 'team_a'})
        self.assertEqual(res['state']['scope'], 'team_a')

    def test_the_link_file_without_a_safe_org_gives_no_scope(self):
        self.ok_sc(link={'code': 0, 'org': '--yes'})
        self.assertNotIn('scope', self.run_cli()['state'])

    def test_timeouts_cwd_and_capture_of_each_command(self):
        self.ok_sc()
        spy = _SubSpy()
        self.run_cli(spy=spy)
        kinds = [(a[3], kw.get('timeout')) for a, kw in spy.calls]
        self.assertEqual(kinds, [('link', 120), ('deploy', 300), ('inspect', 120), ('list', 60)])
        for argv, kw in spy.calls:
            self.assertEqual(argv[0], self.npx_path)
            self.assertEqual(kw.get('cwd'), self.build)
            self.assertIs(kw.get('capture_output'), True)
            self.assertIs(kw.get('text'), True)
            self.assertEqual((kw.get('encoding'), kw.get('errors')), ('utf-8', 'replace'))   # не кодування локалі (Windows)

    def test_non_utf8_cli_output_does_not_break_the_publish(self):
        """Сміття не в UTF-8 у виводі CLI заміняється, а не кидає `UnicodeDecodeError` повз `ModuleError`."""
        self.ok_sc(deploy={'code': 0, 'stdout': D + '\n', 'stdout_hex': 'fffe80'}, inspect={'code': 0, 'stdout': A + '\n'})
        self.assertEqual(self.run_cli()['url'], A)
        self.ok_sc(deploy={'code': 1, 'stdout_hex': 'fffe80', 'stderr': 'Error: Forbidden'})
        e = self.fails()
        self.assertEqual((type(e), e.code), (dm.ModuleError, 'vercel-auth'))

    def test_a_null_byte_in_the_build_path_is_a_deploy_failure_not_a_stray_error(self):
        self.ok_sc()
        g = self.fn('publish').__globals__
        ctx = self.cli_ctx()
        task = {'id': 't1', 'gated': True, 'state': {'project': 'pv-12345678', 'task': 't1'}}
        spy = _SubSpy(lambda argv, kw: (_ for _ in ()).throw(ValueError('embedded null byte')))
        with mock.patch.dict(g, {'subprocess': spy, '_fetch_page': lambda u: PAGE_OK}):
            with self.assertRaises(dm.ModuleError) as cm:
                self.fn('publish')(ctx, self.build, task)
        self.assertEqual(cm.exception.code, 'vercel-deploy')

    def test_default_mode_is_token(self):
        ctx = dm.module_ctx(self.sp, MID)
        self.assertEqual(ctx['settings'].get('auth'), 'token')
        g = self.fn('publish').__globals__
        self.assertEqual(g['_auth'](ctx), 'token')
        self.assertEqual(g['_auth']({'settings': {'auth': 'garbage'}}), 'token')
        self.assertEqual(g['_auth']({}), 'token')
        self.assertEqual(g['_auth']({'settings': {'auth': 'cli'}}), 'cli')

    def test_token_mode_still_wants_a_token_and_never_runs_npx(self):
        self.ok_sc()
        e = self.fails(ctx=self.cli_ctx(auth='token'))
        self.assertIsInstance(e, dm.ModuleError)
        self.assertEqual(e.code, 'vercel-auth')
        self.assertEqual(self.calls(), [])


# ------------------------------------------------------------------------------------------ 2–7: імʼя, скоуп, npx

class NameAndScope(CliBase):
    def test_2_scope_from_state_goes_to_link_and_deploy_but_not_to_inspect(self):
        self.ok_sc()
        res = self.run_cli(state={'project': 'pv-12345678', 'task': 't1', 'scope': 'team_a'}, team='acme')
        self.assertEqual(self.argvs(), [
            ['--yes', 'vercel', 'link', '--yes', '--scope', 'team_a', '--project', 'pv-12345678'],
            ['--yes', 'vercel', 'deploy', '--prod', '--yes', '--scope', 'team_a'],
            ['--yes', 'vercel', 'inspect', D],
            ['--yes', 'vercel', 'list', 'pv-12345678', '--json', '--scope', 'team_a']])
        self.assertEqual(res['state']['scope'], 'team_a')            # налаштування `team` ігнорується, коли є стан

    def test_3_scope_from_settings(self):
        self.ok_sc()
        res = self.run_cli(state={}, team='acme')
        link, deploy, _inspect, _list = self.argvs()
        self.assertEqual(link[:6], ['--yes', 'vercel', 'link', '--yes', '--scope', 'acme'])
        self.assertEqual(deploy, ['--yes', 'vercel', 'deploy', '--prod', '--yes', '--scope', 'acme'])
        self.assertEqual(res['state']['scope'], 'acme')

    def test_4_a_state_of_another_task_is_no_state(self):
        self.ok_sc()
        res = self.run_cli(state={'project': 'pv-99999999', 'task': 't2', 'scope': 'team_a'})
        proj = res['state']['project']
        self.assertRegex(proj, r'^pv-\d{8}$')
        self.assertNotEqual(proj, 'pv-99999999')
        link, deploy, _inspect, _list = self.argvs()
        self.assertEqual(link, ['--yes', 'vercel', 'link', '--yes', '--project', proj])   # і скоуп чужої задачі — теж не наш
        self.assertEqual(deploy, ['--yes', 'vercel', 'deploy', '--prod', '--yes'])
        self.assertEqual(res['state']['task'], 't1')

    def test_4b_no_state_at_all_mints_an_opaque_name(self):
        self.ok_sc()
        res = self.run_cli(state={})
        self.assertRegex(res['state']['project'], r'^pv-\d{8}$')

    def test_5_a_name_that_is_not_pv_is_accepted(self):
        self.ok_sc()
        res = self.run_cli(state={'project': 'dc-x', 'task': 't1'})
        self.assertEqual(res['state']['project'], 'dc-x')
        self.assertEqual(self.argvs()[0], ['--yes', 'vercel', 'link', '--yes', '--project', 'dc-x'])

    def test_6_unsafe_name_or_scope_is_refused_before_any_run(self):
        self.ok_sc()
        bad = ['--yes', 'a b', 'A' * 101, 'a' * 101, 'pv;rm', '-x', '', 'PV-1']
        for value in bad:
            with self.subTest(project=value):
                e = self.fails(state={'project': value, 'task': 't1'})
                self.assertIsInstance(e, dm.ModuleError)
                self.assertEqual(e.code, 'module-error')
                self.assertEqual(self.calls(), [])
        for value in ['--yes', 'a b', 'A' * 101, 'pv;rm', '-x']:
            with self.subTest(scope_in_state=value):
                e = self.fails(state={'project': 'pv-12345678', 'task': 't1', 'scope': value})
                self.assertEqual((type(e), e.code), (dm.ModuleError, 'module-error'))
                self.assertEqual(self.calls(), [])
            with self.subTest(team=value):
                e = self.fails(state={}, team=value)
                self.assertEqual((type(e), e.code), (dm.ModuleError, 'module-error'))
                self.assertEqual(self.calls(), [])

    def test_6b_a_non_string_state_value_is_refused_too(self):
        self.ok_sc()
        for st in ({'project': 5, 'task': 't1'}, {'project': ['pv-12345678'], 'task': 't1'},
                   {'project': 'pv-12345678', 'task': 't1', 'scope': 7}):
            with self.subTest(state=st):
                e = self.fails(state=st)
                self.assertEqual((type(e), e.code), (dm.ModuleError, 'module-error'))
                self.assertEqual(self.calls(), [])

    def test_7_no_npx(self):
        self.ok_sc()
        e = self.fails(npx=False)
        self.assertIsInstance(e, dm.ModuleError)
        self.assertEqual(e.code, 'no-node')
        self.assertEqual(self.calls(), [])
        self.assertEqual(e.status, 409)

    def test_7b_a_find_tool_that_answers_something_odd_is_no_node(self):
        self.ok_sc()
        ctx = self.cli_ctx()
        for odd in (None, '', 5, ['npx']):
            ctx['find_tool'] = lambda name, odd=odd: odd
            with self.subTest(odd=odd):
                e = self.fails(ctx=ctx)
                self.assertEqual((type(e), e.code), (dm.ModuleError, 'no-node'))
        ctx.pop('find_tool')
        self.assertEqual(self.fails(ctx=ctx).code, 'no-node')

    def test_7c_the_unsafe_name_wins_over_no_npx(self):
        """Порядок: імʼя/скоуп перевіряються ДО пошуку `npx` (відмова про небезпечне значення не залежить від Node)."""
        self.ok_sc()
        e = self.fails(state={'project': '--yes', 'task': 't1'}, npx=False)
        self.assertEqual(e.code, 'module-error')

    def test_without_the_core_class_a_plain_error_still_surfaces(self):
        self.ok_sc()
        ctx = self.cli_ctx(npx=False)
        ctx.pop('ModuleError')
        e = self.fails(ctx=ctx)
        self.assertIsInstance(e, RuntimeError)
        self.assertIn('no-node', str(e))


# -------------------------------------------------------------------------------------------- 8–10: відмови deploy

class DeployFailures(CliBase):
    LOGIN = "Error: No existing credentials found. Please run `vercel login`"
    SCOPE = "Error: You don't have access to the team 'x'"
    AUTH = 'Error: Forbidden'

    def fail_with(self, stderr='', stdout='', code=1, core=False):
        self.ok_sc(deploy={'code': code, 'stdout': stdout, 'stderr': stderr})
        return self.fails(core=core)

    def test_8_classification(self):
        for text, code in ((self.LOGIN, 'vercel-login'), (self.SCOPE, 'vercel-scope'), (self.AUTH, 'vercel-auth'),
                           ('Error: something else broke', 'vercel-deploy'), ('', 'vercel-deploy')):
            with self.subTest(code=code, text=text[:30]):
                e = self.fail_with(stderr=text)
                self.assertIsInstance(e, dm.ModuleError)
                self.assertEqual(e.code, code)
                self.assertEqual(e.full, text)                       # сирий текст — як є

    def test_8b_full_is_the_last_4000_chars_of_stderr_or_stdout(self):
        long = 'x' * 5000 + 'TAIL-' + self.AUTH
        e = self.fail_with(stderr=long)
        self.assertEqual(e.full, long[-4000:])
        self.assertTrue(e.full.endswith(self.AUTH))
        self.assertLessEqual(len(e.message), 300)                    # `message` — лише перші 300
        self.assertEqual(e.code, 'vercel-auth')
        e = self.fail_with(stdout='only stdout: ' + self.LOGIN)      # `stderr or stdout`: stderr порожній → stdout
        self.assertEqual((e.code, e.full), ('vercel-login', 'only stdout: ' + self.LOGIN))
        e = self.fail_with(stderr='err side: Error: Forbidden', stdout='out side: vercel login')   # stderr має перевагу
        self.assertEqual((e.code, e.full), ('vercel-auth', 'err side: Error: Forbidden'))

    def test_8c_the_order_login_then_scope_then_access(self):
        both_scope_and_access = "Forbidden: you don't have access to the team 'x'"
        self.assertEqual(self.fail_with(stderr=both_scope_and_access).code, 'vercel-scope')   # скоуп — ПЕРЕД доступом
        login_and_scope = 'Please run `vercel login` and pass --scope'
        self.assertEqual(self.fail_with(stderr=login_and_scope).code, 'vercel-login')          # вхід — ПЕРЕД скоупом

    def test_8d_every_documented_pattern_maps_to_its_code(self):
        table = {
            'vercel-login': ['not authenticated', 'credentials', 'please log in', 'vercel login', 'no existing credentials'],
            'vercel-scope': ['--scope', 'scope not found', 'no such team', 'not a member of',
                             "don't have access to the team", 'team not found'],
            'vercel-auth': ['forbidden', 'not authorized', 'access denied', 'do not have permission'],
        }
        for code, pats in table.items():
            for pat in pats:
                with self.subTest(pat=pat):
                    self.assertEqual(self.fail_with(stderr=f'Error: {pat.upper()} …').code, code)   # регістр неважливий

    def test_8e_through_the_core_the_codes_and_statuses_are_those_of_the_table(self):
        e = self.fail_with(stderr=self.LOGIN, core=True)
        self.assertEqual((e.code, e.status), ('vercel-login', 409))
        self.assertIn('vercel login', e.full)
        e = self.fail_with(stderr=self.SCOPE, core=True)
        self.assertEqual((e.code, e.status), ('vercel-scope', 409))
        e = self.fail_with(stderr='boom', core=True)
        self.assertEqual((e.code, e.status), ('vercel-deploy', 502))

    def test_8f_no_human_text_of_liga_in_the_module_output(self):
        """Тексти ЛІГИ (`npx vercel login`, `tasks.json`, «Андрія», пароль) — в ядрі: модуль віддає лише сирий вивід."""
        e = self.fail_with(stderr=self.LOGIN)
        for human in ('tasks.json', 'Андр', '1100', 'натисни', 'терміналі'):
            self.assertNotIn(human, e.full + e.message)

    def test_9_no_address_in_the_output(self):
        self.ok_sc(deploy={'code': 0, 'stdout': 'Done. Production deployed.\n'})
        e = self.fails()
        self.assertEqual((type(e), e.code), (dm.ModuleError, 'vercel-no-url'))
        self.assertEqual(e.status, 502)
        self.assertEqual(self.pages, [])                             # перевіряти нічого
        self.assertEqual(len(self.calls()), 2)                       # `inspect` не кличеться без адреси

    def test_9b_a_foreign_host_is_not_an_address(self):
        self.ok_sc(deploy={'code': 0, 'stdout': 'see https://example.com/x and http://pv-1.vercel.app (no TLS)\n'})
        self.assertEqual(self.fails().code, 'vercel-no-url')

    def test_10_a_timeout_of_deploy(self):
        self.ok_sc()
        exc = subprocess.TimeoutExpired(['npx', 'vercel', 'deploy'], 300)

        def handler(argv, kw):
            if argv[3] == 'deploy':
                raise exc
            return None
        e = self.fails(spy=_SubSpy(handler))
        self.assertEqual((type(e), e.code), (dm.ModuleError, 'vercel-deploy'))
        self.assertEqual(e.full, str(exc))

    def test_10b_a_timeout_of_link_is_also_a_deploy_failure(self):
        self.ok_sc()
        exc = subprocess.TimeoutExpired(['npx', 'vercel', 'link'], 120)

        def handler(argv, kw):
            if argv[3] == 'link':
                raise exc
            return None
        e = self.fails(spy=_SubSpy(handler))
        self.assertEqual((e.code, e.full), ('vercel-deploy', str(exc)))

    def test_10c_an_os_error_while_starting_is_a_deploy_failure(self):
        self.ok_sc()

        def handler(argv, kw):
            raise FileNotFoundError(2, 'No such file or directory', 'npx')
        e = self.fails(spy=_SubSpy(handler))
        self.assertEqual((e.code, e.full), ('vercel-deploy', str(FileNotFoundError(2, 'No such file or directory', 'npx'))))

    def test_a_failed_link_alone_does_not_stop_the_deploy(self):
        """Як у 0.8.0: код `link` не перевіряється (відмову скоупу скаже `deploy`)."""
        self.ok_sc(link={'code': 1, 'stderr': 'link complained'})
        self.assertEqual(self.run_cli()['url'], A)
        self.assertEqual(len(self.calls()), 4)                       # link, deploy, inspect, list


# ------------------------------------------------------------------------------------------------ 3: прибирання

P = 'pv-12345678'
CUR = 'pv-12345678-abc.vercel.app'                                  # хост `deploy_url` (D) — у списку `vercel list` без схеми


def host(i):
    return f'pv-12345678-h{i}.vercel.app'


def entry(h, created, name=P):
    return {'url': h, 'name': name, 'state': 'READY', 'target': 'production', 'createdAt': created}


def page(entries, nxt=None):
    return {'code': 0, 'stdout': json.dumps({'contextName': 'team', 'deployments': entries,
                                              'pagination': {'count': len(entries), 'next': nxt, 'prev': 0}})}


class Cleanup(CliBase):
    def removes(self):
        return [a for a in self.argvs() if a[2] == 'remove']

    def lists(self):
        return [a for a in self.argvs() if a[2] == 'list']

    def go(self, entries=None, **over):
        sc = dict(over)
        if entries is not None and 'list' not in sc:
            sc['list'] = page(entries)
        self.ok_sc(**sc)
        return self.run_cli()

    def test_1_the_two_oldest_of_five_are_removed(self):
        res = self.go([entry(CUR, 5), entry(host(4), 4), entry(host(3), 3), entry(host(2), 2), entry(host(1), 1)])
        self.assertIsNone(res['cleanup_warning'])
        self.assertEqual(res['warnings'], [])
        rm = self.removes()
        self.assertEqual(sorted(rm), sorted([['--yes', 'vercel', 'remove', host(1), '--safe', '--yes'],
                                             ['--yes', 'vercel', 'remove', host(2), '--safe', '--yes']]))
        self.assertEqual(self.lists(), [['--yes', 'vercel', 'list', P, '--json']])
        self.assertEqual({c['cwd'] for c in self.calls()}, {os.path.realpath(self.build)})

    def test_2_a_current_deployment_that_is_not_the_newest_is_always_kept(self):
        self.go([entry(host(5), 5), entry(host(4), 4), entry(host(3), 3), entry(CUR, 2), entry(host(1), 1)])
        self.assertEqual(sorted(a[3] for a in self.removes()), sorted([host(3), host(1)]))   # лишились CUR + 5 + 4
        self.assertNotIn(CUR, [a[3] for a in self.removes()])

    def test_2b_the_current_one_is_kept_even_when_it_is_the_oldest(self):
        self.go([entry(host(5), 5), entry(host(4), 4), entry(host(3), 3), entry(CUR, 0)])
        self.assertEqual([a[3] for a in self.removes()], [host(3)])

    def test_2c_few_deployments_nothing_is_removed(self):
        self.go([entry(CUR, 3), entry(host(2), 2), entry(host(1), 1)])
        self.assertEqual(self.removes(), [])
        self.go([entry(host(2), 2), entry(host(1), 1)])             # поточної в списку ще нема (відстав) — теж нічого
        self.assertEqual(self.removes(), [])

    def test_3_other_projects_are_never_removed(self):
        ents = [entry(CUR, 9)] + [entry(host(i), i) for i in (8, 7, 6)]
        ents += [entry('other-0.vercel.app', 0, name='other'), entry('foreign-1.vercel.app', 1, name='foreign'),
                 {'name': 'other', 'state': 'READY'}]               # чужий запис без `url`/`createdAt` — ігнорується, а не «незнайома форма»
        res = self.go(ents)
        self.assertIsNone(res['cleanup_warning'])
        self.assertEqual([a[3] for a in self.removes()], [host(6)])
        self.assertFalse([a for a in self.removes() if 'other' in a[3] or 'foreign' in a[3]])

    def test_4_the_project_name_is_never_an_argument_of_remove(self):
        """⛔ `vercel remove <імʼя проєкту>` видаляє ВЕСЬ проєкт."""
        ents = [entry(CUR, 9)] + [entry(host(i), i) for i in range(1, 7)]
        for proj in (P, 'dc-x'):
            with self.subTest(project=proj):
                ents_p = [dict(e, name=proj) for e in ents]
                self.ok_sc(list=page(ents_p))
                self.run_cli(state={'project': proj, 'task': 't1'})
                rm = self.removes()
                self.assertTrue(rm)
                for a in rm:
                    self.assertNotIn(proj, a[3:])
                    self.assertRegex(a[3], r'^[a-z0-9.-]+\.vercel\.app$')
        # навіть запис, чий «хост» збігається з імʼям проєкту, — незнайома форма, а не `remove <проєкт>`
        self.ok_sc(list=page([entry(CUR, 9), entry(P, 1)] + [entry(host(i), i) for i in range(2, 6)]))
        res = self.run_cli()
        self.assertEqual(self.removes(), [])
        self.assertIn('Старі публікації не прибрано', res['cleanup_warning'])

    def test_5_an_unparsable_list_removes_nothing(self):
        good = [entry(CUR, 9)] + [entry(host(i), i) for i in range(1, 7)]
        bad = {
            'exit 1': {'code': 1, 'stderr': 'Error: boom'},
            'not json': {'code': 0, 'stdout': 'not json at all'},
            'empty': {'code': 0, 'stdout': ''},
            'list instead of object': {'code': 0, 'stdout': '[]'},
            'deployments not a list': {'code': 0, 'stdout': json.dumps({'deployments': 'x'})},
            'deployments object': {'code': 0, 'stdout': json.dumps({'deployments': {}})},
            'no url': page(good + [{'name': P, 'createdAt': 5}]),
            'no createdAt': page(good + [{'name': P, 'url': host(9)}]),
            'createdAt string': page(good + [dict(entry(host(9), 1), createdAt='5')]),
            'createdAt bool': page(good + [dict(entry(host(9), 1), createdAt=True)]),
            'weird host': page(good + [entry('bad host/x', 1)]),
            'url not a string': page(good + [dict(entry(host(9), 1), url=5)]),
        }
        for why, sc in bad.items():
            with self.subTest(why=why):
                self.ok_sc(list=sc)
                res = self.run_cli()
                self.assertEqual(self.removes(), [])
                self.assertIsInstance(res['cleanup_warning'], str)
                self.assertTrue(res['cleanup_warning'].startswith('Старі публікації не прибрано'))
                self.assertEqual((res['url'], res['verified']), (A, True))     # публікація вдалась

    def test_5b_a_list_that_cannot_start_or_times_out_removes_nothing(self):
        self.ok_sc(list=page([entry(CUR, 9)] + [entry(host(i), i) for i in range(1, 7)]))
        for exc in (subprocess.TimeoutExpired(['x'], 60), FileNotFoundError('npx'), ValueError('embedded null byte')):
            with self.subTest(exc=type(exc).__name__):
                def handler(argv, kw, exc=exc):
                    if argv[3] == 'list':
                        raise exc
                    return None
                spy = _SubSpy(handler)
                res = self.run_cli(spy=spy)
                self.assertEqual([c for c in spy.calls if c[0][3] == 'remove'], [])
                self.assertTrue(res['cleanup_warning'].startswith('Старі публікації не прибрано'))

    def test_5c_an_unexpected_failure_in_cleanup_never_fails_the_publish(self):
        self.ok_sc()
        g = self.fn('publish').__globals__

        def boom(*a, **k):
            raise KeyError('x')
        with mock.patch.dict(g, {'_cli_cleanup': boom}):
            res = self.run_cli()
        self.assertEqual(res['url'], A)
        self.assertTrue(res['cleanup_warning'].startswith('Старі публікації не прибрано'))
        self.assertIn(res['cleanup_warning'], res['warnings'])

    def test_6_a_failed_remove_does_not_stop_the_next_one(self):
        res = self.go([entry(CUR, 5), entry(host(4), 4), entry(host(3), 3), entry(host(2), 2), entry(host(1), 1)],
                      remove=[{'code': 1, 'stderr': 'Error: nope'}, {'code': 0}])
        self.assertEqual(len(self.removes()), 2)                   # другий все одно пробується
        self.assertIn('не вдалося 1 з 2', res['cleanup_warning'])
        self.assertEqual(res['url'], A)
        self.go([entry(CUR, 5), entry(host(4), 4), entry(host(3), 3), entry(host(2), 2), entry(host(1), 1)],
                remove={'code': 1})
        res = self.run_cli()
        self.assertIn('не вдалося 2 з 2', res['cleanup_warning'])

    def test_6b_a_remove_that_cannot_run_counts_as_failed(self):
        self.ok_sc(list=page([entry(CUR, 5), entry(host(4), 4), entry(host(3), 3), entry(host(2), 2), entry(host(1), 1)]))

        def handler(argv, kw):
            if argv[3] == 'remove':
                raise subprocess.TimeoutExpired(argv, 60)
            return None
        spy = _SubSpy(handler)
        res = self.run_cli(spy=spy)
        self.assertEqual(len([c for c in spy.calls if c[0][3] == 'remove']), 2)
        self.assertIn('не вдалося 2 з 2', res['cleanup_warning'])
        self.assertEqual([kw.get('timeout') for argv, kw in spy.calls if argv[3] in ('list', 'remove')], [60, 60, 60])

    def test_7_pagination(self):
        p1 = page([entry(CUR, 9), entry(host(8), 8), entry(host(7), 7)], nxt=123)
        p2 = page([entry(host(2), 2), entry(host(1), 1)], nxt=None)
        self.ok_sc(list=[p1, p2])
        res = self.run_cli()
        ls = self.lists()
        self.assertEqual(ls, [['--yes', 'vercel', 'list', P, '--json'], ['--yes', 'vercel', 'list', P, '--json', '--next', '123']])
        self.assertEqual(sorted(a[3] for a in self.removes()), sorted([host(1), host(2)]))
        self.assertIsNone(res['cleanup_warning'])

    def test_7b_at_most_five_pages_and_repeats_are_not_removed_twice(self):
        self.ok_sc(list=page([entry(CUR, 9), entry(host(8), 8), entry(host(7), 7), entry(host(6), 6), entry(host(5), 5)],
                             nxt=7))                                # остання відповідь повторюється: нескінченна пагінація
        res = self.run_cli()
        self.assertEqual(len(self.lists()), 5)                      # `CLI_LIST_PAGES`
        rm = [a[3] for a in self.removes()]
        self.assertEqual(sorted(rm), sorted(set(rm)))               # дублі сторінок — той самий запис
        self.assertEqual(sorted(rm), sorted([host(6), host(5)]))
        self.assertIsNone(res['cleanup_warning'])

    def test_7c_a_bad_next_stops_paging(self):
        for nxt in (0, -1, 'x', None, True, 1.5):
            with self.subTest(nxt=nxt):
                self.ok_sc(list=page([entry(CUR, 9)], nxt=nxt))
                self.run_cli()
                self.assertEqual(len(self.lists()), 1)

    def test_8_scope_goes_to_list_and_remove_only_when_known(self):
        ents = [entry(CUR, 5), entry(host(4), 4), entry(host(3), 3), entry(host(2), 2), entry(host(1), 1)]
        self.ok_sc(list=page(ents))
        self.run_cli(state={'project': P, 'task': 't1', 'scope': 'team_a'})
        self.assertEqual(self.lists(), [['--yes', 'vercel', 'list', P, '--json', '--scope', 'team_a']])
        self.assertEqual(len(self.removes()), 2)
        for a in self.removes():
            self.assertEqual(a[4:], ['--safe', '--yes', '--scope', 'team_a'])
        self.ok_sc(list=page(ents))
        self.run_cli(state={'project': P, 'task': 't1'})            # скоупа нема (а `link` дописав `orgId` у стан — це не скоуп запуску)
        self.assertEqual(self.lists(), [['--yes', 'vercel', 'list', P, '--json']])
        for a in self.removes():
            self.assertNotIn('--scope', a)
        self.ok_sc(list=page(ents))
        self.run_cli(state={}, team='acme')                         # скоуп із налаштування
        self.assertIn('--scope', self.lists()[0])

    def test_9_the_time_limit_stops_the_removals(self):
        ents = [entry(CUR, 5), entry(host(4), 4), entry(host(3), 3), entry(host(2), 2), entry(host(1), 1)]

        def clock(ticks_before_expiry):
            n = [0]

            def monotonic():
                n[0] += 1
                return 0 if n[0] <= ticks_before_expiry else 10 ** 6
            return types.SimpleNamespace(monotonic=monotonic, sleep=lambda s: None)
        g = self.fn('publish').__globals__
        # 1-й виклик — `deadline`, 2-й — перед сторінкою списку, 3-й і далі — перед кожним `remove`
        for ticks, removed, failed in ((2, 0, 2), (3, 1, 1)):
            with self.subTest(removed=removed):
                self.ok_sc(list=page(ents))
                with mock.patch.dict(g, {'time': clock(ticks)}):
                    res = self.run_cli()
                self.assertEqual(len(self.removes()), removed)
                self.assertIn(f'не вдалося {failed} з 2', res['cleanup_warning'])
                self.assertIn('ліміт часу', res['cleanup_warning'])
        self.ok_sc(list=page(ents))
        with mock.patch.dict(g, {'time': clock(1)}):                # вичерпано ще до читання списку
            res = self.run_cli()
        self.assertEqual(self.removes(), [])
        self.assertTrue(res['cleanup_warning'].startswith('Старі публікації не прибрано'))

    def test_10_the_warning_is_also_in_warnings(self):
        res = self.go(None, list={'code': 1})
        self.assertIn(res['cleanup_warning'], res['warnings'])
        self.assertLessEqual(len(res['cleanup_warning']), 300)
        res = self.go([entry(CUR, 1)])
        self.assertIsNone(res['cleanup_warning'])
        self.assertEqual(res['warnings'], [])
        core = self.run_cli(core=True)
        serve._checked_url_result(core)                             # форма, яку приймає ядро, і з попередженням

    def test_10b_the_cleanup_warning_comes_after_the_verify_warning(self):
        self.ok_sc(list={'code': 1})
        res = self.run_cli(page=(404, '', ''))
        self.assertEqual(len(res['warnings']), 2)
        self.assertIn('HTTP 404', res['warnings'][0])
        self.assertEqual(res['warnings'][1], res['cleanup_warning'])

    def test_11_scheme_prefixed_and_mixed_case_hosts_are_normalised(self):
        """Список дає голий хост, `deploy_url` — `https://хост`; порівнюємо хости (регістр не важливий)."""
        ents = [entry('https://' + CUR.upper(), 9), entry(host(8), 8), entry(host(7), 7), entry('https://' + host(6), 6)]
        self.go(ents)
        self.assertEqual([a[3] for a in self.removes()], [host(6)])            # поточна не видалена навіть за іншого запису хоста

    def test_12_cleanup_does_not_run_when_the_publish_failed(self):
        self.ok_sc(deploy={'code': 1, 'stderr': 'Error: Forbidden'})
        self.fails()
        self.assertEqual(self.lists(), [])
        self.ok_sc(deploy={'code': 0, 'stdout': 'nothing'})
        self.fails()
        self.assertEqual(self.lists(), [])


# ------------------------------------------------------------------------------------ 11–12: перевірка превʼю, гейт

class Verification(CliBase):
    def test_11_gate_marker_decides_when_the_page_is_gated(self):
        self.ok_sc()
        res = self.run_cli(gated=False, page=(200, '', '<html>'))
        self.assertEqual((res['verified'], res['verify'], res['warnings']), (True, None, []))
        res = self.run_cli(gated=True, page=(200, '', '<html>'))
        self.assertEqual(res['verified'], False)
        self.assertEqual(res['verify'], {'reason': 'на URL відповідає не наш макет (немає гейта)'})
        self.assertEqual(len(res['warnings']), 1)
        self.assertIn('немає гейта', res['warnings'][0])
        res = self.run_cli(gated=True, page=PAGE_OK)
        self.assertEqual((res['verified'], res['verify']), (True, None))
        res = self.run_cli(gated=False, page=PAGE_OK)               # з маркером, але без гейта — теж добре
        self.assertEqual(res['verified'], True)

    def test_11b_gated_missing_means_not_gated(self):
        self.ok_sc()
        ctx = self.cli_ctx()
        task = {'id': 't1', 'state': {'project': 'pv-12345678', 'task': 't1'}}          # без ключа `gated`
        g = self.fn('publish').__globals__
        with mock.patch.dict(g, {'_fetch_page': lambda url: (200, '', '<html>')}):
            res = self.fn('publish')(ctx, self.build, task)
        self.assertTrue(res['verified'])

    def test_12_vercel_protection(self):
        self.ok_sc()
        res = self.run_cli(page=(302, 'https://vercel.com/sso-api?url=x', ''))
        self.assertEqual(res['verified'], False)
        self.assertEqual(res['verify'], {'reason': 'vercel_protection'})
        g = self.fn('publish').__globals__
        token_text = g['_verify']  # той самий текст, що в режимі `token`: звіряємо з його функцією
        with mock.patch.dict(g, {'_fetch_preview': lambda url: (401, '')}):
            token_warning = token_text(A, 'pv-12345678')[1]
        self.assertEqual(res['warnings'], [token_warning])
        self.assertIn('pv-12345678', res['warnings'][0])
        self.assertIn('Deployment Protection', res['warnings'][0])

    def test_12b_other_answers(self):
        self.ok_sc()
        cases = [((302, 'https://example.com/login', ''), 'HTTP 302'), ((404, '', ''), 'HTTP 404'),
                 ((500, '', ''), 'HTTP 500'), ((None, '', ''), 'адреса не відповіла'),
                 ((301, 'https://vercel.com/login', ''), 'HTTP 301')]      # `vercel.com/sso` — саме SSO; звичайний вхід — ні
        for page, reason in cases:
            with self.subTest(page=page):
                res = self.run_cli(page=page)
                self.assertEqual((res['verified'], res['verify']), (False, {'reason': reason}))
                self.assertEqual(len(res['warnings']), 1)
                self.assertIn(reason, res['warnings'][0])
                self.assertEqual(res['url'], A)                          # публікація не зупиняється

    def test_12d_an_unreachable_page_reports_the_exception_text(self):
        """Як `_check_published` 0.8.0 (`str(e)[:200]`): причина недосяжності (сертифікат, DNS…), а не фіксований рядок."""
        self.ok_sc()
        why = '<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>'
        res = self.run_cli(page=(None, '', why))
        self.assertEqual((res['verified'], res['verify']), (False, {'reason': why}))
        self.assertIn(why, res['warnings'][0])
        res = self.run_cli(page=(None, '', '   '))                   # порожній текст — запасний рядок
        self.assertEqual(res['verify'], {'reason': 'адреса не відповіла'})

    def test_12d2_an_error_text_with_the_gate_marker_is_not_a_verification(self):
        self.ok_sc()
        for gated in (True, False):
            res = self.run_cli(gated=gated, page=(None, '', '<urlopen error authgate unreachable>'))
            self.assertEqual((res['verified'], res['verify']), (False, {'reason': '<urlopen error authgate unreachable>'}))

    def test_12e_any_2xx_goes_through_the_body_check(self):
        """0.8.0 читало тіло за будь-якого успішного відкриття: 204/206 з маркером гейта — теж `verified`."""
        self.ok_sc()
        for code in (200, 201, 204, 206, 299):
            with self.subTest(code=code):
                res = self.run_cli(gated=True, page=(code, '', '<div id="authgate">'))
                self.assertEqual((res['verified'], res['verify']), (True, None))
                res = self.run_cli(gated=True, page=(code, '', '<html>'))
                self.assertEqual(res['verify'], {'reason': 'на URL відповідає не наш макет (немає гейта)'})
        for code in (199, 300, 304):
            with self.subTest(code=code):
                res = self.run_cli(gated=False, page=(code, '', '<div id="authgate">'))
                self.assertEqual(res['verify'], {'reason': f'HTTP {code}'})

    def test_12c_no_retries_of_the_page_check(self):
        """Як у 0.8.0 (`_check_published`): одна спроба, без повторів і без сну."""
        self.ok_sc()
        self.run_cli(page=(404, '', ''))
        self.assertEqual(len(self.pages), 1)

    def test_a_check_that_blows_up_would_not_hide_the_deploy(self):
        """`_fetch_page` сам не кидає (збій → `(None, '', '')`), тож публікація з ним завжди завершується відповіддю."""
        self.ok_sc()
        res = self.run_cli(page=(None, '', ''))
        self.assertEqual(res['verify'], {'reason': 'адреса не відповіла'})


# --------------------------------------------------------------------------------------------- 13: найкоротша адреса

class ShortestAddress(CliBase):
    def test_13_shortest_of_deploy_and_inspect(self):
        self.ok_sc(deploy={'code': 0, 'stdout': D + '\n' + A + '\n'}, inspect={'code': 0, 'stdout': ''})
        res = self.run_cli()
        self.assertEqual((res['url'], res['deploy_url']), (A, A))    # `deploy_url` — ОСТАННЯ адреса виводу `deploy`
        self.assertEqual(self.pages, [A])
        self.ok_sc(deploy={'code': 0, 'stdout': A + '\n' + D + '\n'}, inspect={'code': 0, 'stdout': ''})
        res = self.run_cli()
        self.assertEqual((res['url'], res['deploy_url']), (A, D))

    def test_13b_inspect_adds_a_shorter_alias(self):
        self.ok_sc(deploy={'code': 0, 'stdout': D + '\n'}, inspect={'code': 0, 'stdout': 'Aliases\n  ' + A + '\n'})
        self.assertEqual(self.run_cli()['url'], A)

    def test_13c_inspect_failure_keeps_the_deploy_addresses(self):
        self.ok_sc(deploy={'code': 0, 'stdout': D + '\n' + A + '\n'}, inspect={'code': 1, 'stderr': 'boom'})
        self.assertEqual(self.run_cli()['url'], A)
        self.ok_sc(deploy={'code': 0, 'stdout': D + '\n'}, inspect={'code': 1, 'stderr': 'boom'})
        self.assertEqual(self.run_cli()['url'], D)                   # `dep_url` не виключається: часто він і є найкоротшим

    def test_13d_inspect_that_cannot_start_keeps_the_deploy_addresses(self):
        self.ok_sc(deploy={'code': 0, 'stdout': D + '\n'})

        def handler(argv, kw):
            if argv[3] == 'inspect':
                raise subprocess.TimeoutExpired(argv, 120)
            return None
        self.assertEqual(self.run_cli(spy=_SubSpy(handler))['url'], D)

    def test_13e_addresses_in_stderr_count_and_duplicates_collapse(self):
        self.ok_sc(deploy={'code': 0, 'stdout': D + '\n', 'stderr': 'Production: ' + D + ' [3s]\n' + A + '\n'},
                   inspect={'code': 0, 'stdout': ''})
        res = self.run_cli()
        self.assertEqual((res['url'], res['deploy_url']), (A, A))

    def test_13f_the_address_is_never_guessed_from_the_project_name(self):
        """⚠️ Історія 30.07.2026: `https://<проєкт>.vercel.app` не вгадуємо — лише те, що надрукував Vercel."""
        self.ok_sc(deploy={'code': 0, 'stdout': 'https://totally-other-name-9.vercel.app\n'}, inspect={'code': 0, 'stdout': ''})
        res = self.run_cli(state={'project': 'pv-12345678', 'task': 't1'})
        self.assertEqual(res['url'], 'https://totally-other-name-9.vercel.app')


# -------------------------------------------------------------------------------------------------- 14: жодного токена

class NoTokenLeaks(CliBase):
    def test_14_no_token_in_argv_and_no_env_is_passed(self):
        self.ok_sc()
        ctx = self.cli_ctx(token=TOKEN, team='acme')
        self.assertEqual(ctx['secrets'].get('token'), TOKEN)         # токен у `ctx` справді є
        spy = _SubSpy()
        g = self.fn('publish').__globals__
        boom = mock.Mock(side_effect=AssertionError('REST API у режимі cli'))
        with mock.patch.dict(g, {'_req': boom}):
            res = self.run_cli(ctx=ctx, spy=spy)
        self.assertEqual(res['url'], A)
        boom.assert_not_called()
        self.assertEqual(len(spy.calls), 4)
        for argv, kw in spy.calls:
            self.assertNotIn('env', kw)
            self.assertFalse([a for a in argv if TOKEN in a])
        self.assertFalse([a for a in self.argvs() for x in a if TOKEN in x])
        self.assertNotIn(TOKEN, json.dumps(res))
        self.assertEqual(self.api.requests, [])                      # і до підставного API нічого не йшло

    def test_14b_check_does_not_pass_env_either(self):
        self.scenario({'whoami': {'code': 0, 'stdout': 'someone\n'}})
        ctx = self.cli_ctx(token=TOKEN)
        spy = _SubSpy()
        g = self.fn('check').__globals__
        with mock.patch.dict(g, {'subprocess': spy}):
            self.fn('check')(ctx)
        self.assertEqual(len(spy.calls), 1)
        self.assertNotIn('env', spy.calls[0][1])
        self.assertFalse([a for a in spy.calls[0][0] if TOKEN in a])


# ------------------------------------------------------------------------------------------------------- 15: check

class CheckCli(CliBase):
    def check(self, ctx=None, spy=None, **kw):
        ctx = ctx if ctx is not None else self.cli_ctx(**kw)
        g = self.fn('check').__globals__
        with mock.patch.dict(g, {'subprocess': spy} if spy is not None else {}):
            return self.fn('check')(ctx)

    def test_15_whoami_ok(self):
        self.scenario({'whoami': {'code': 0, 'stdout': 'someone\n'}})
        self.assertEqual(self.check(), {'ok': True, 'detail': 'someone'})
        self.assertEqual(self.argvs(), [['--yes', 'vercel', 'whoami']])

    def test_15b_whoami_picks_the_last_line_and_trims(self):
        self.scenario({'whoami': {'code': 0, 'stdout': 'Vercel CLI 99.9\n  someone  \n'}})
        self.assertEqual(self.check(), {'ok': True, 'detail': 'someone'})
        self.scenario({'whoami': {'code': 0, 'stdout': ''}})
        self.assertEqual(self.check(), {'ok': True, 'detail': ''})

    def test_15c_not_logged_in(self):
        self.scenario({'whoami': {'code': 1, 'stderr': 'Error: No existing credentials found. Please run `vercel login`'}})
        res = self.check()
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-login'))
        self.assertIn('vercel login', res['detail'])

    def test_15d_no_npx(self):
        self.scenario({})
        res = self.check(npx=False)
        self.assertEqual((res['ok'], res['error']), (False, 'no-node'))
        self.assertEqual(self.calls(), [])

    def test_15e_team_goes_to_whoami_when_safe(self):
        self.scenario({'whoami': {'code': 0, 'stdout': 'someone\n'}})
        self.check(team='acme')
        self.assertEqual(self.argvs()[-1], ['--yes', 'vercel', 'whoami', '--scope', 'acme'])
        self.check(team='--yes')                                     # небезпечне — просто без скоупа
        self.assertEqual(self.argvs()[-1], ['--yes', 'vercel', 'whoami'])

    def test_15f_a_timeout_is_check_timeout_and_never_raises(self):
        self.scenario({'whoami': {'code': 0, 'stdout': 'x'}})

        def handler(argv, kw):
            raise subprocess.TimeoutExpired(argv, 120)
        res = self.check(spy=_SubSpy(handler))
        self.assertEqual((res['ok'], res['error']), (False, 'check-timeout'))
        self.assertIn('120', res['detail'])

    def test_15h_a_failure_to_start_is_no_node_and_a_nonzero_exit_stays_login(self):
        self.scenario({'whoami': {'code': 1, 'stderr': 'Error: not logged in'}})

        def handler(argv, kw):
            raise FileNotFoundError(2, 'No such file or directory', 'npx')
        res = self.check(spy=_SubSpy(handler))
        self.assertEqual((res['ok'], res['error']), (False, 'no-node'))
        self.assertIn('No such file', res['detail'])

        def odd(argv, kw):
            raise ValueError('embedded null byte')
        res = self.check(spy=_SubSpy(odd))                           # check не кидає й на дивному збої запуску
        self.assertEqual((res['ok'], res['error']), (False, 'no-node'))
        res = self.check()                                           # справжній фальшивий npx: код 1 → вхід
        self.assertEqual((res['ok'], res['error']), (False, 'vercel-login'))

    def test_15g_whoami_timeout_is_120_seconds_and_cwd_is_not_set(self):
        self.scenario({'whoami': {'code': 0, 'stdout': 'x\n'}})
        spy = _SubSpy()
        self.check(spy=spy)
        (argv, kw), = spy.calls
        self.assertEqual(kw.get('timeout'), 120)                     # холодний `npx --yes vercel` спершу завантажує CLI
        self.assertIsNone(kw.get('cwd'))

    def test_15i_check_survives_a_non_utf8_answer(self):
        self.scenario({'whoami': {'code': 0, 'stdout': 'someone\n', 'stdout_hex': 'fffe'}})
        res = self.check()
        self.assertEqual(res['ok'], True)                            # байти замінено, `UnicodeDecodeError` нема

    def test_16_token_mode_check_is_unchanged(self):
        self.scenario({})
        res = self.check(auth='token')
        self.assertEqual((res['ok'], res['error']), (False, 'no-token'))
        self.assertEqual(self.calls(), [])


# ---------------------------------------------------------------------------------- справжній `_fetch_page` проти сервера

class FetchPage(CliBase):
    def serve(self, respond):
        srv = tvp._Server(respond)
        self.addCleanup(srv.stop)
        return srv

    def fetch(self, url):
        return self.fn('publish').__globals__['_fetch_page'](url)

    def test_200_returns_the_body(self):
        srv = self.serve(lambda rec: (200, '<div id="authgate">x</div>', {}))
        status, loc, body = self.fetch(f'http://127.0.0.1:{srv.port}/')
        self.assertEqual((status, loc), (200, ''))
        self.assertIn('authgate', body)
        rec, = srv.requests
        self.assertNotIn('authorization', rec['headers'])            # жодних облікових даних
        self.assertTrue(rec['headers']['user-agent'].startswith('deai-canvas-vercel-publish'))

    def test_the_body_is_capped(self):
        srv = self.serve(lambda rec: (200, 'a' * 100000, {}))
        status, _loc, body = self.fetch(f'http://127.0.0.1:{srv.port}/')
        self.assertEqual((status, len(body)), (200, 60000))

    def test_redirects_are_not_followed(self):
        srv = self.serve(lambda rec: (302, '', {'Location': 'https://vercel.com/sso-api?x=1'}))
        self.assertEqual(self.fetch(f'http://127.0.0.1:{srv.port}/'), (302, 'https://vercel.com/sso-api?x=1', ''))
        self.assertEqual(len(srv.requests), 1)

    def test_http_errors_give_status_without_body(self):
        srv = self.serve(lambda rec: (404, 'nope', {}))
        self.assertEqual(self.fetch(f'http://127.0.0.1:{srv.port}/'), (404, '', ''))

    def test_failures_give_none(self):
        srv = self.serve(lambda rec: (200, 'x', {}))
        port = srv.port
        srv.stop()
        status, loc, why = self.fetch(f'http://127.0.0.1:{port}/')      # третій елемент — текст винятку (причина)
        self.assertEqual((status, loc), (None, ''))
        self.assertTrue(why.strip() and len(why) <= 200, why)
        self.assertEqual(self.fetch('file:///etc/passwd'), (None, '', ''))
        self.assertEqual(self.fetch('ftp://127.0.0.1/x'), (None, '', ''))
        self.assertEqual(self.fetch('not a url'), (None, '', ''))
        self.assertEqual(self.trip.violations, [])


# ------------------------------------------------------------------------------------------------- вигляд коду

class SourceShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(tvp.SERVER, encoding='utf-8') as f:
            cls.tree = ast.parse(f.read())

    def test_subprocess_is_called_in_one_place_and_never_with_env(self):
        runs = [n for n in ast.walk(self.tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess']
        self.assertEqual([n.func.attr for n in runs], ['run'])                    # єдиний запуск — у `_vc`
        self.assertEqual([k.arg for k in runs[0].keywords], ['cwd', 'capture_output', 'text', 'encoding', 'errors', 'timeout'])
        (fn,) = [n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == '_vc']
        self.assertIn(runs[0], list(ast.walk(fn)))

    def test_nothing_is_imported_from_subprocess(self):
        """`from subprocess import Popen` обійшов би перевірку єдиного місця запуску вище."""
        self.assertEqual([n.module for n in ast.walk(self.tree) if isinstance(n, ast.ImportFrom) and n.module
                          and n.module.split('.')[0] == 'subprocess'], [])

    def test_the_page_check_does_not_touch_the_token(self):
        (fn,) = [n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == '_fetch_page']
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | {a.arg for a in fn.args.args}
        consts = {c.value for c in ast.walk(fn) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        self.assertFalse({'ctx', 'token', 'secrets', '_token', '_req'} & names)
        self.assertFalse([c for c in consts if 'bearer' in c.lower() or 'authorization' in c.lower()])

    def test_the_cli_branch_is_chosen_before_the_token_is_demanded(self):
        (fn,) = [n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == '_publish']
        line = {n.func.id: n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertLess(line['_publish_cli'], line['_need_token'])


if __name__ == '__main__':
    unittest.main()
