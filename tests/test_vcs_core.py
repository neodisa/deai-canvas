"""Ядро синкає через роль `vcs` (етап 4a, Task 4): ціль, постачальник, неявний `'legacy'`, старі імена, `task_new`.

Транспорт git живе в модулі `git-sync` (`tests/test_git_sync_module.py`); тут перевіряється те, що лишилось у ядрі:
ЩО відправити й ЯК прийняти (чистий макет, `.canvas-state.json`, авторство, форки, тексти даних), як ядро знаходить
постачальника й будує ціль, і що відмови модуля доходять до маршрутів як `VcsError(OSError)` із `code`.

Git — СПРАВЖНІЙ, на локальних bare-репо (без мережі: `GIT_SSH_COMMAND=false`). Кожен тест має власні `HOME`, `DEAI_HOME`,
`DC_TASKS_FILE`, `DC_MIRRORS_DIR` і особу машини; глобальний git-конфіг людини не читається (`GIT_CONFIG_GLOBAL`).
Справжній `~/.deai` стереже `spaces_guard` (тести створюють простори).

Два світи, як у ядрі: `Legacy` — шар просторів вимкнено (лише `DC_TASKS_FILE`), `'legacy'`-постачальник ЛІГИ; `Plain` —
звичайний простір без інтеграцій із підключеним `git-sync`.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

try:
    import fcntl
except ImportError:                          # Windows: лок модуля там інший (`msvcrt`), тест його не торкається
    fcntl = None

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402

_ENV = ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE', 'DC_MIRRORS_DIR', 'DC_IDENTITY_NAME', 'DC_IDENTITY_EMAIL', 'DC_NO_OVERVIEW',
        'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_NOSYSTEM', 'GIT_SSH_COMMAND', 'GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL',
        'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL')
_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def sh(args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, encoding='utf-8', env=env)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


class Core(unittest.TestCase):
    """Спільне: ізольоване оточення, origin + «колега», задача з `it1`. `PLAIN` — шар просторів увімкнено."""
    PLAIN = False

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='vcs-core-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        saved = {k: os.environ.get(k) for k in _ENV}

        def restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(restore)
        self.home = os.path.join(self.tmp, 'home')
        os.makedirs(self.home)
        os.environ['HOME'] = self.home
        os.environ['GIT_CONFIG_GLOBAL'] = os.devnull
        os.environ['GIT_CONFIG_NOSYSTEM'] = '1'
        os.environ['GIT_SSH_COMMAND'] = 'false'                       # жодної мережі: ssh-адреса впаде одразу
        for k, v in (('NAME', 'T'), ('EMAIL', 't@t')):
            os.environ['GIT_AUTHOR_' + k] = os.environ['GIT_COMMITTER_' + k] = v
        os.environ['DC_NO_OVERVIEW'] = '1'
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        self.mirrors = os.path.join(self.tmp, 'mirrors')
        os.environ['DC_MIRRORS_DIR'] = self.mirrors
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp, 'legacy', 'tasks.json')
        if not self.PLAIN:           # у світі просторів старий файл не створюємо: його міграція змінила б реєстр
            write(os.environ['DC_TASKS_FILE'], json.dumps({'tasks': {}, 'current': None}))
        # Системна тека тимчасових файлів — власна: «після виклику не лишилось `deai-vcs-*`» міряється точно.
        self.systmp = os.path.join(self.tmp, 'systmp')
        os.makedirs(self.systmp)
        p = mock.patch.object(tempfile, 'tempdir', self.systmp)
        p.start()
        self.addCleanup(p.stop)
        if self.PLAIN:
            # DEAI_HOME — у домівці (як у test_modules): інакше тимчасова тека macOS дала б `path-system` раніше
            self.deai = os.path.join(self.home, 'stuff', 'deai')
            os.environ['DEAI_HOME'] = self.deai
            self.tool = os.path.join(self.home, 'tools', 'dc')
            os.makedirs(self.tool)
            q = mock.patch.object(spaces, 'ROOT', self.tool)
            q.start()
            self.addCleanup(q.stop)
        else:
            os.environ.pop('DEAI_HOME', None)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)

        self.origin = self.make_origin()
        self.task_dir = os.path.join(self.tmp, 'task')
        self.it1 = os.path.join(self.task_dir, 'iterations', 'it1')
        write(os.path.join(self.it1, 'index.html'), '<h1>v1</h1>')
        self.save_meta({'iterations': [{'id': 'it1'}], 'current': 'it1'})
        self.task = {'dir': self.task_dir, 'title': 'Тест'}
        self.gl = {'repo': self.origin, 'path': 'mockup/t1', 'branch': 'main', 'ssh_key': None}

    # ---- хелпери ----
    def make_origin(self, name='origin.git'):
        origin = os.path.join(self.tmp, name)
        os.makedirs(origin)
        sh(['git', 'init', '--bare', '-q', '-b', 'main', '.'], origin)
        peer = os.path.join(self.tmp, 'peer-' + name)
        os.makedirs(peer)
        sh(['git', 'init', '-q', '-b', 'main', '.'], peer)
        sh(['git', 'config', 'user.email', 'peer@test'], peer)
        sh(['git', 'config', 'user.name', 'Peer'], peer)
        write(os.path.join(peer, 'README.md'), 'seed\n')
        sh(['git', 'add', '-A'], peer)
        sh(['git', 'commit', '-qm', 'seed'], peer)
        sh(['git', 'remote', 'add', 'origin', origin], peer)
        r = sh(['git', 'push', '-q', 'origin', 'main'], peer)
        self.assertEqual(r.returncode, 0, r.stderr)
        if name == 'origin.git':
            self.peer = peer
        return origin

    def meta_path(self):
        return os.path.join(self.task_dir, 'iterations.json')

    def save_meta(self, meta):
        write(self.meta_path(), json.dumps(meta, ensure_ascii=False))

    def meta(self):
        with open(self.meta_path(), encoding='utf-8') as fh:
            return json.load(fh)

    def sync(self, it='it1', record=True, **kw):
        r = serve.gitlab_sync('t1', self.task, self.gl, it, **kw)
        if record and r.get('synced'):
            serve._record_sync(self.task, it, r.get('sha'))
        return r

    def peer_push(self, files, msg='колега правив макет', who='Peer', email='peer@test', when=None, peer=None):
        """Коміт «колеги» поверх актуального origin: `files` — {шлях: текст}; `when` — unix-час (дата коміту й автора)."""
        peer = peer or self.peer
        sh(['git', 'pull', '-q', '--ff-only', 'origin', 'main'], peer)
        for rel, text in files.items():
            write(os.path.join(peer, rel), text)
        sh(['git', 'add', '-A'], peer)
        env = dict(os.environ)
        if when is not None:
            stamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(when))
            env['GIT_AUTHOR_DATE'] = env['GIT_COMMITTER_DATE'] = stamp
        c = sh(['git', '-c', f'user.name={who}', '-c', f'user.email={email}', 'commit', '-qm', msg], peer, env)
        self.assertEqual(c.returncode, 0, c.stderr)
        p = sh(['git', 'push', '-q', 'origin', 'main'], peer)
        self.assertEqual(p.returncode, 0, f'peer push failed: {p.stderr}')

    def peer_state(self, html, author, key, source_it='it3', path='mockup/t1', **kw):
        """Коміт колеги РАЗОМ із `.canvas-state.json`: так виглядає справжня передача."""
        self.peer_push({f'{path}/index.html': html,
                        f'{path}/.canvas-state.json': json.dumps(
                            {'task': 't1', 'source_it': source_it, 'author': author, 'author_key': key,
                             'published': False})}, who=author, email=key, **kw)

    def out(self, cwd, *args):
        r = sh(['git', *args], cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def age(self, d, days):
        old = time.time() - days * 24 * 3600
        for root, _, names in os.walk(d):
            for n in names:
                os.utime(os.path.join(root, n), (old, old))

    def hide(self, origin=None):
        """Сховати origin: з нього не дістатись (офлайн). Повертає функцію, що вертає його назад."""
        origin = origin or self.origin
        os.rename(origin, origin + '-hidden')
        self.addCleanup(lambda: os.path.exists(origin + '-hidden') and os.rename(origin + '-hidden', origin))
        return lambda: os.rename(origin + '-hidden', origin)

    def stub(self, **fns):
        base = {'status': lambda ctx, t: {'behind': 0, 'behind_path': 0, 'unpushed': 0, 'on_remote': True,
                                          'web': 'https://module.example/x', 'label': 'GitHub'},
                'push': lambda ctx, t, s, m: {'ok': True}, 'pull': lambda ctx, t, d, o=None: {'found': False}}
        base.update(fns)
        return dm.Module('git-sync', roles=['vcs'], fns=base)

    def multipage(self):
        write(os.path.join(self.it1, 'pages.json'), json.dumps({'pages': [
            {'id': 'p', 'name': 'Картка', 'kind': 'page'}, {'id': 'q', 'name': 'Особа', 'kind': 'page'}]}))
        for d in ('p', 'q'):
            write(os.path.join(self.it1, d, 'index.html'), '<h1>x</h1>')

    def write_it1(self, html):
        write(os.path.join(self.it1, 'index.html'), html)

    # ---- простір (Plain) ----
    def make_space(self, name='Alpha', integrations=False, enable=True, **settings):
        sid = spaces.create_space(name, 'space-1', os.path.join(self.home, 'work', name.lower()))
        if integrations:
            reg_file = os.path.join(self.deai, 'spaces.json')
            with open(reg_file, encoding='utf-8') as fh:
                reg = json.load(fh)
            for s in reg['spaces']:
                if s['id'] == sid:
                    s['integrations'] = True
            with open(reg_file, 'w', encoding='utf-8') as fh:
                json.dump(reg, fh)
        sp = next(s for s in spaces.read_registry()['spaces'] if s['id'] == sid)
        if enable:
            dm.write_module_state(sp, 'git-sync', enabled=True, settings={'repo': self.origin, **settings})
        spaces.set_request_space(sid)
        return sp


class Legacy(Core):
    """Шар просторів вимкнено (лише `DC_TASKS_FILE`): постачальник — неявний `'legacy'`, простір ЛІГА."""

    # ---------------------------------------------------------------- постачальник
    def test_the_provider_is_git_sync_run_with_the_legacy_ctx(self):
        m, ctx, legacy = serve.vcs_provider()
        self.assertEqual((m.id, m.status, m.origin), ('git-sync', 'ok', 'builtin'))
        self.assertIs(legacy, True)
        self.assertEqual(ctx['cache_dir'], self.mirrors)
        self.assertIs(ctx['mirror_flat'], True)
        self.assertEqual(ctx['settings'], {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True})
        self.assertEqual(ctx['secrets'], {})
        self.assertIs(ctx['ModuleError'], dm.ModuleError)
        self.assertEqual(ctx['folder_ok']('/x'), (False, 'bad-folder'))

    def test_without_the_env_the_mirrors_live_in_dot_mirrors_of_the_tool(self):
        os.environ.pop('DC_MIRRORS_DIR')
        self.assertEqual(serve.vcs_provider()[1]['cache_dir'], os.path.join(serve.ROOT, '.mirrors'))

    def test_the_mirror_dir_is_the_070_slug_under_the_mirrors_env(self):
        """`/abs/x/origin.git` → `abs-x-origin.git` (без першого `-`); scp-форма — частина після двокрапки."""
        t = {'path': 'mockup/t1', 'branch': 'main'}
        self.assertEqual(serve.vcs_mirror_dir({**t, 'repo': '/abs/x/origin.git'}),
                         os.path.join(self.mirrors, 'abs-x-origin.git'))
        self.assertEqual(serve.vcs_mirror_dir({**t, 'repo': 'git@gitlab.internal.example:ORG/r.git'}),
                         os.path.join(self.mirrors, 'ORG-r.git'))
        self.assertEqual(serve.vcs_mirror_dir(self.gl),
                         os.path.join(self.mirrors, re.sub(r'[^\w.-]+', '-', self.origin).strip('-')))

    def test_the_legacy_ctx_never_points_at_the_deai_home_cache(self):
        """Поправка 9 ревʼю Task 3: `module_ctx` каркаса кладе `cache_dir` під `spaces.home()`, а при вимкненому шарі це
        справжній `~/.deai`. Неявний постачальник живе на СВОЄМУ `ctx`: дзеркало — під `DC_MIRRORS_DIR`."""
        self.assertTrue(spaces.home().startswith(self.tmp), 'передумова: домівка — тимчасова')
        self.assertTrue(self.sync()['synced'])
        self.assertTrue(os.path.isdir(os.path.join(serve.vcs_mirror_dir(self.gl), '.git')))
        self.assertFalse(os.path.exists(os.path.join(spaces.home(), 'cache')), 'кеш зʼявився під домівкою Deai')
        self.assertFalse(os.path.exists(spaces.home()), 'шар вимкнено, а домівка Deai створена')

    def test_the_ctx_of_legacy_is_not_built_by_module_ctx(self):
        with mock.patch.object(dm, 'module_ctx', side_effect=AssertionError('legacy не йде через module_ctx')):
            serve.vcs_provider()
            self.assertTrue(self.sync()['synced'])

    def test_a_broken_catalog_is_a_vcs_error_not_a_crash(self):
        with mock.patch.object(dm, 'catalog', side_effect=RuntimeError('boom')):
            with self.assertRaises(serve.VcsError) as cm:
                serve.vcs_provider()
        self.assertEqual(cm.exception.code, 'vcs-error')
        self.assertIsInstance(cm.exception, OSError)
        with mock.patch.object(dm, 'catalog', return_value={}):
            with self.assertRaises(serve.VcsError) as cm:
                serve.vcs_provider()
        self.assertIn('not loaded', str(cm.exception))
        with mock.patch.object(dm, 'catalog', side_effect=RuntimeError('boom')):
            st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1')
        self.assertEqual((st['configured'], st['code']), (True, 'vcs-error'))

    # ---------------------------------------------------------------- ціль
    def target(self, task, settings=None, cfg=None, tid='t1'):
        return serve.vcs_target(cfg if cfg is not None else {}, tid, task,
                                {'branch': 'main', 'path': 'mockup/{task}'} if settings is None else settings)

    def test_a_gitlab_task_gives_a_target_without_none_fields(self):
        t = self.target({'gitlab': {'repo': 'git@h:o/r.git', 'path': '/mockup/t1/'}})
        self.assertEqual(t, {'repo': 'git@h:o/r.git', 'path': 'mockup/t1', 'branch': 'main', 'task': 't1'})

    def test_gitlab_without_a_path_or_repo_is_a_task_that_is_not_set_up(self):
        for gl in ({'repo': 'git@h:o/r.git'}, {'path': 'mockup/t1'}, {'repo': '', 'path': 'mockup/t1'}, {}):
            with self.subTest(gl=gl):
                self.assertIsNone(self.target({'gitlab': gl}))
        self.assertIsNone(self.target({}))

    def test_the_gitlab_target_carries_the_key_and_ip_of_the_task_or_the_shared_ones(self):
        """Як `gitlab_cfg` 0.7.0: ключ і IP — задачі, інакше спільні з кореня `tasks.json`; `ctx` `'legacy'` їх не має."""
        cfg = {'gitlab_ssh_key': '/k/shared', 'gitlab_host_ip': '10.0.0.7'}
        t = self.target({'gitlab': {'repo': 'git@h:o/r.git', 'path': 'p'}}, cfg=cfg)
        self.assertEqual((t['ssh_key'], t['host_ip']), ('/k/shared', '10.0.0.7'))
        t = self.target({'gitlab': {'repo': 'git@h:o/r.git', 'path': 'p', 'ssh_key': '/k/own', 'host_ip': '10.0.0.8'}}, cfg=cfg)
        self.assertEqual((t['ssh_key'], t['host_ip']), ('/k/own', '10.0.0.8'))
        self.assertNotIn('ssh_key', serve.vcs_provider()[1]['settings'])
        self.assertNotIn('host_ip', serve.vcs_provider()[1]['settings'])

    def test_the_vcs_field_of_the_task_beats_gitlab(self):
        t = self.target({'vcs': {'repo': '/x/new.git', 'path': 'docs/{task}', 'branch': 'dev'},
                         'gitlab': {'repo': 'git@h:o/r.git', 'path': 'mockup/t1'}})
        self.assertEqual(t, {'repo': '/x/new.git', 'path': 'docs/t1', 'branch': 'dev', 'task': 't1'})

    def test_an_empty_vcs_repo_is_not_set_and_falls_through(self):
        for v in ({'repo': ''}, {'repo': '   '}, {'repo': None}, {'path': 'x'}, 'x', 5, []):
            with self.subTest(v=v):
                t = self.target({'vcs': v, 'gitlab': {'repo': 'git@h:o/r.git', 'path': 'mockup/t1'}})
                self.assertEqual(t['repo'], 'git@h:o/r.git')

    def test_the_repo_is_trimmed_before_it_reaches_the_module(self):
        """`validate` відкидає `repo != repo.strip()`: ядро кладе в ціль обрізане."""
        self.assertEqual(self.target({'vcs': {'repo': '  /x/o.git\n'}})['repo'], '/x/o.git')
        self.assertEqual(self.target({'gitlab': {'repo': ' git@h:o/r.git ', 'path': 'p'}})['repo'], 'git@h:o/r.git')
        self.assertEqual(self.target({}, {'repo': ' /x/o.git ', 'path': 'p'})['repo'], '/x/o.git')

    def test_the_settings_of_the_module_are_the_last_resort(self):
        s = {'repo': '/x/o.git', 'branch': 'dev', 'path': '/{task}/'}
        self.assertEqual(self.target({}, s), {'repo': '/x/o.git', 'path': 't1', 'branch': 'dev', 'task': 't1'})
        # поле задачі перемагає налаштування по-полях: непорожнє `path` — своє, порожнє — з налаштувань
        t = self.target({'vcs': {'repo': '/x/n.git', 'path': ''}}, s)
        self.assertEqual((t['repo'], t['path'], t['branch']), ('/x/n.git', 't1', 'dev'))
        self.assertIsNone(self.target({}, {'path': 'mockup/{task}'}), 'нема repo ні в задачі, ні в модулі')
        self.assertIsNone(self.target({}, {'repo': '  ', 'path': 'p'}))

    def test_the_default_path_and_branch(self):
        t = self.target({'vcs': {'repo': '/x/o.git'}}, {})
        self.assertEqual((t['path'], t['branch']), ('mockup/t1', 'main'))

    # ---------------------------------------------------------------- статус
    def test_the_status_after_the_first_sync_is_labelled_gitlab_with_the_old_web_rule(self):
        self.assertTrue(self.sync()['synced'])
        st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1')
        self.assertEqual(st['label'], 'GitLab', 'ЛІГА: підпис «GitLab», хоч модуль для локального репо каже «Git»')
        self.assertIsNone(st['web'], 'локальне репо — посилання нема, як у 0.7.0')
        self.assertEqual(st['web'], serve.gitlab_web(self.gl))
        self.assertEqual((st['configured'], st['behind'], st['behind_path'], st['unpushed'], st['on_remote'],
                          st['dirty'], st['remote_path']), (True, 0, 0, 0, True, False, 'mockup/t1'))
        self.assertEqual((st['synced_it'], st['gitlab_it']), ('it1', 'it1'))
        self.assertTrue(st['synced_at'])

    def test_the_web_and_label_of_legacy_follow_the_old_rule_even_for_ssh_hosts(self):
        gl = {'repo': 'git@h:o/r.git', 'path': 'mockup/t1', 'branch': 'main'}
        ctx = serve._vcs_legacy_ctx()
        st = serve.gitlab_status(self.task, gl, self.meta(), 'it1', vcs=(self.stub(), ctx, True))
        self.assertEqual(st['web'], serve.gitlab_web(gl))
        self.assertEqual(st['web'], 'https://h/o/r/-/commits/main/mockup/t1')
        self.assertEqual(st['label'], 'GitLab')

    def test_a_module_provider_keeps_its_own_web_and_label(self):
        gl = {'repo': 'git@h:o/r.git', 'path': 'mockup/t1', 'branch': 'main'}
        st = serve.gitlab_status(self.task, gl, self.meta(), 'it1', vcs=(self.stub(), serve._vcs_legacy_ctx(), False))
        self.assertEqual((st['web'], st['label']), ('https://module.example/x', 'GitHub'))
        st = serve.gitlab_status(self.task, gl, self.meta(), 'it1',
                                 vcs=(self.stub(status=lambda c, t: {}), serve._vcs_legacy_ctx(), False))
        self.assertEqual((st['web'], st['label'], st['behind'], st['on_remote']), (None, 'Git', 0, None))

    def test_a_module_refusal_reaches_the_status_as_an_error_with_a_code(self):
        def deny(ctx, t):
            raise ctx['ModuleError']('vcs-auth', message='access denied for the key')
        st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1',
                                 vcs=(self.stub(status=deny), serve._vcs_legacy_ctx(), True))
        self.assertEqual(st, {'configured': True, 'error': 'access denied for the key', 'code': 'vcs-auth'})

        def crash(ctx, t):
            raise RuntimeError('boom')
        st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1',
                                 vcs=(self.stub(status=crash), serve._vcs_legacy_ctx(), True))
        self.assertEqual((st['configured'], st['code']), (True, 'module-error'))

    def test_a_hidden_origin_is_an_error_status(self):
        self.sync()
        self.hide()
        st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1')
        self.assertTrue(st['configured'])
        self.assertIn('fetch failed', st['error'])
        self.assertIn(st['code'], ('vcs-error', 'vcs-offline'))

    # ---------------------------------------------------------------- відправлення
    def test_the_commit_subject_is_the_design_canvas_one(self):
        self.assertTrue(self.sync()['synced'])
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%s'), 'design-canvas: sync mockup/t1 (Тест) · it1')
        body = self.out(self.origin, 'log', '-1', '--format=%b')
        self.assertRegex(body, r'^Ітерація: it1 · Хеш: [0-9a-f]{12} · \d\d\.\d\d\.\d{4} \d\d:\d\d$')

    def test_the_commit_carries_the_machine_identity(self):
        self.sync()
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%an <%ae>'), 'Lead <lead@example.com>')

    def test_without_an_identity_the_commit_is_signed_by_the_constant(self):
        """Git без `user.email` не комітить: константа лише підписує коміт і НІКОЛИ не потрапляє в дані ітерації."""
        os.environ['DC_IDENTITY_NAME'] = ''
        os.environ['DC_IDENTITY_EMAIL'] = ''
        self.assertTrue(self.sync()['synced'])
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%an <%ae>'),
                         'Designer One <designer.one@example.com>')
        sh(['git', 'pull', '-q', '--ff-only', 'origin', 'main'], self.peer)
        with open(os.path.join(self.peer, 'mockup/t1', '.canvas-state.json'), encoding='utf-8') as fh:
            state = json.load(fh)
        self.assertEqual((state['author'], state['author_key']), ('', ''), 'константа не сміє потрапити в заяву автора')

    def test_commit_identity_still_answers_what_it_answered(self):
        """`_commit_identity` розщеплено на `_commit_author`, відповідь та сама (на неї стоїть test_serve)."""
        self.assertEqual(serve._commit_author(), {'name': 'Lead', 'email': 'lead@example.com'})
        self.assertEqual(serve._commit_identity(), ['-c', 'user.name=Lead', '-c', 'user.email=lead@example.com'])
        os.environ['DC_IDENTITY_NAME'] = os.environ['DC_IDENTITY_EMAIL'] = ''
        self.assertEqual(serve._commit_identity(), ['-c', 'user.name=Designer One',
                                                    '-c', 'user.email=designer.one@example.com'])

    def test_a_control_character_in_the_title_does_not_block_the_send(self):
        """Модуль відхиляє керівні символи в `meta` до git; ядро чистить їх саме, тож заголовок із ESC не блокує синк."""
        self.task['title'] = 'Червоний\x1b[31m заголовок\x00'
        r = self.sync()
        self.assertTrue(r['synced'], r)
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%s'),
                         'design-canvas: sync mockup/t1 (Червоний[31m заголовок) · it1')

    def test_control_characters_in_the_identity_do_not_block_the_send_and_are_all_removed(self):
        os.environ['DC_IDENTITY_NAME'] = 'Оль\x1bга\nSigned'
        os.environ['DC_IDENTITY_EMAIL'] = 'o\tl@example.com\x7f'
        r = self.sync()
        self.assertTrue(r['synced'], r)
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%an|%ae'), 'ОльгаSigned|ol@example.com')

    def test_an_identity_made_only_of_control_characters_falls_back_to_the_constant(self):
        """Після чистки імʼя чи пошта можуть стати порожніми: тоді — константа підпису, а не відмова модуля."""
        os.environ['DC_IDENTITY_NAME'] = '\x1b\x07'
        os.environ['DC_IDENTITY_EMAIL'] = '\n\t'
        r = self.sync()
        self.assertTrue(r['synced'], r)
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%an <%ae>'),
                         'Designer One <designer.one@example.com>')

    def test_a_note_keeps_its_line_breaks_and_loses_the_other_control_characters(self):
        self.save_meta({'iterations': [{'id': 'it1', 'note': 'один\r\nдва\tтри\x07'}]})
        r = self.sync()
        self.assertTrue(r['synced'], r)
        body = self.out(self.origin, 'log', '-1', '--format=%B')
        self.assertIn('Що змінено: один\n', body)
        self.assertIn('два\tтри', body)
        self.assertNotIn('\x07', body)

    def mirror_file(self, rel):
        with open(os.path.join(serve.vcs_mirror_dir(self.gl), 'mockup/t1', rel), encoding='utf-8') as fh:
            return fh.read()

    def test_the_readme_of_a_multipage_mockup_names_design_canvas(self):
        self.multipage()
        self.assertTrue(self.sync()['synced'])
        readme = self.mirror_file('README.md')
        self.assertIn('Мультисторінковий макет (design-canvas, задача `t1`). Не редагувати тут напряму.', readme)
        self.assertIn('| `p/` | Картка |', readme)

    def test_the_state_file_is_written_and_the_clean_mockup_is_what_goes(self):
        write(os.path.join(self.it1, 'notes.py'), '# службове')
        write(os.path.join(self.it1, 'a.tmp'), 'x')
        write(os.path.join(self.it1, 'sub', 'b.tmp'), 'x')
        write(os.path.join(self.it1, 'sub', 'keep.txt'), 'x')
        self.assertTrue(self.sync()['synced'])
        files = sorted(self.out(self.origin, 'ls-tree', '-r', '--name-only', 'main').split())
        self.assertEqual(files, ['README.md', 'mockup/t1/.canvas-state.json', 'mockup/t1/index.html',
                                 'mockup/t1/sub/keep.txt'])
        state = json.loads(self.mirror_file('.canvas-state.json'))
        self.assertEqual((state['task'], state['source_it'], state['author'], state['author_key']),
                         ('t1', 'it1', 'Lead', 'lead@example.com'))

    def test_the_result_carries_the_remote_and_the_forms_of_070(self):
        r = self.sync()
        self.assertEqual({k: r[k] for k in ('ok', 'synced', 'changed', 'pushed', 'remote')},
                         {'ok': True, 'synced': True, 'changed': True, 'pushed': True,
                          'remote': f'{self.origin}:mockup/t1'})
        self.assertRegex(r['sha'], r'^[0-9a-f]{7,}$')
        again = self.sync(record=False)         # без `sha` (нічого не змінилось) відбиток не пишеться
        self.assertEqual(again, {'ok': True, 'synced': True, 'changed': False, 'pushed': False,
                                 'remote': f'{self.origin}:mockup/t1'})
        self.peer_push({'mockup/t1/index.html': '<h1>чуже</h1>'})
        self.write_it1('<h1>v2</h1>')
        blocked = self.sync()
        self.assertEqual((blocked['blocked'], blocked['synced'], blocked['remote']), ('behind', False, f'{self.origin}:mockup/t1'))

    def test_a_missing_iteration_and_a_foreign_one_are_refused_before_the_provider_and_the_network(self):
        with mock.patch.object(serve, 'vcs_provider', side_effect=AssertionError('постачальник до перевірок')):
            with self.assertRaises(OSError) as cm:
                serve.gitlab_sync('t1', self.task, self.gl, 'it9')
            self.assertEqual(str(cm.exception), 'iteration not found')
            self.save_meta({'iterations': [{'id': 'it1', 'author': 'Ольга', 'author_key': 'o@example.com'}]})
            r = serve.gitlab_sync('t1', self.task, self.gl, 'it1')
        self.assertEqual((r['ok'], r['blocked'], r['author']), (False, 'foreign', 'Ольга'))

    def test_a_refusal_of_the_module_is_a_vcs_error_with_a_code(self):
        self.sync()
        self.hide()
        with self.assertRaises(serve.VcsError) as cm:
            serve.gitlab_sync('t1', self.task, self.gl, 'it1')
        e = cm.exception
        self.assertIsInstance(e, OSError)
        self.assertIn(e.code, ('vcs-error', 'vcs-offline'))
        self.assertIn('fetch failed', str(e))

    def test_a_missing_provider_is_a_vcs_error(self):
        with mock.patch.object(serve, 'vcs_provider', return_value=None):
            with self.assertRaises(serve.VcsError) as cm:
                serve.gitlab_sync('t1', self.task, self.gl, 'it1')
            self.assertEqual(cm.exception.code, 'vcs-error')
            with self.assertRaises(serve.VcsError):
                serve.gitlab_pull(self.task, self.gl)
            self.assertEqual(serve.gitlab_status(self.task, self.gl, self.meta(), 'it1'), {'configured': False})

    def test_the_temp_src_lives_outside_the_task_folder_and_is_removed(self):
        before = sorted(os.listdir(self.task_dir))
        seen = []
        real = serve._vcs_call

        def spy(vcs, fn, *args, **kw):
            if fn == 'push':
                seen.append(args[1])
                self.assertTrue(os.path.isfile(os.path.join(args[1], 'index.html')), 'src порожня в момент відправки')
            return real(vcs, fn, *args, **kw)
        with mock.patch.object(serve, '_vcs_call', spy):
            self.sync(record=False)
        (src,) = seen
        self.assertTrue(os.path.realpath(src).startswith(self.systmp + os.sep), src)
        self.assertFalse(os.path.realpath(src).startswith(os.path.realpath(self.task_dir) + os.sep))
        self.assertTrue(os.path.basename(os.path.dirname(src)).startswith('deai-vcs-'), src)
        self.assertEqual(os.listdir(self.systmp), [], 'тимчасова теки не прибрана')
        self.assertEqual(sorted(os.listdir(self.task_dir)), before, 'у теці задачі зʼявилось зайве')

    def test_the_temp_src_is_removed_after_a_failure_too(self):
        self.sync()
        self.hide()
        with self.assertRaises(OSError):
            serve.gitlab_sync('t1', self.task, self.gl, 'it1')
        self.assertEqual(os.listdir(self.systmp), [])

    # ---------------------------------------------------------------- отримання
    def test_the_pull_note_names_gitlab_and_no_person(self):
        self.sync()
        self.peer_push({'mockup/t1/index.html': '<h1>чуже</h1>'})
        r = serve.gitlab_pull(self.task, self.gl)
        self.assertEqual(r['iteration']['note'], 'оновлення з GitLab')
        self.assertTrue(r['iteration']['from_gitlab'])

    def test_a_pull_of_a_missing_path_is_the_old_message(self):
        with self.assertRaises(OSError) as cm:
            serve.gitlab_pull(self.task, {**self.gl, 'path': 'mockup/never'})
        self.assertEqual(str(cm.exception), 'path mockup/never not found in repo')

    def test_the_temp_dir_of_a_pull_is_removed(self):
        self.sync()
        self.peer_push({'mockup/t1/index.html': '<h1>чуже</h1>'})
        serve.gitlab_pull(self.task, self.gl)
        self.assertEqual(os.listdir(self.systmp), [])
        with self.assertRaises(OSError):
            serve.gitlab_pull(self.task, {**self.gl, 'path': 'mockup/never'})
        self.assertEqual(os.listdir(self.systmp), [])

    def test_a_pull_after_a_refusal_of_the_module_is_a_vcs_error(self):
        self.sync()
        self.hide()
        with self.assertRaises(serve.VcsError):
            serve.gitlab_pull(self.task, self.gl)

    def test_the_older_own_note_names_gitlab(self):
        self.sync()
        self.peer_state('<h1>з другої машини</h1>', 'Lead', 'lead@example.com', when=time.time() - 3 * 86400)
        self.write_it1('<h1>моє сьогодні</h1>')
        r = serve.gitlab_pull(self.task, self.gl)
        self.assertEqual(r['fork']['note'], 'продовження моєї роботи — з GitLab приїхала старша версія')

    # ---------------------------------------------------------------- автосинк
    def test_the_autosync_of_a_refusal_is_offline_with_the_code(self):
        self.sync()
        self.write_it1('<h1>v4</h1>')
        self.hide()
        r = serve.autosync('t1', self.task, self.gl)
        self.assertEqual((r['reason'], r['ok'], r['synced'], r['changed']), ('offline', False, False, False))
        self.assertIn(r['code'], ('vcs-error', 'vcs-offline'))
        self.assertIn('fetch failed', r['error'])

    def test_the_autosync_of_a_plain_oserror_has_no_code(self):
        self.write_it1('<h1>v5</h1>')
        with mock.patch.object(serve, 'gitlab_sync', side_effect=OSError('нема мережі')):
            r = serve.autosync('t1', self.task, self.gl)
        self.assertEqual((r['reason'], r['error']), ('offline', 'нема мережі'))
        self.assertNotIn('code', r)

    def test_the_autosync_passes_the_given_provider_to_the_sync(self):
        self.write_it1('<h1>v6</h1>')
        v = (self.stub(), serve._vcs_legacy_ctx(), False)
        with mock.patch.object(serve, 'gitlab_sync', return_value={'ok': True, 'synced': False}) as gs:
            serve.autosync('t1', self.task, self.gl, vcs=v)
        self.assertIs(gs.call_args.kwargs['vcs'], v)

    # ---------------------------------------------------------------- нові відмови модуля (ревʼю Task 1–2)
    def test_a_missing_branch_of_a_non_empty_origin_is_a_target_error_not_a_missing_path(self):
        """Поправка 5: гілки нема на НЕпорожньому origin — це `vcs-error` (помилка цілі), а не `path … not found in repo`
        (його ядро кидає лише коли `found: false`) і не тиха нова гілка в спільному репо."""
        gl = {**self.gl, 'branch': 'nope'}
        for what, call in (('pull', lambda: serve.gitlab_pull(self.task, gl)),
                           ('push', lambda: serve.gitlab_sync('t1', self.task, gl, 'it1'))):
            with self.subTest(what):
                with self.assertRaises(serve.VcsError) as cm:
                    call()
                self.assertEqual(cm.exception.code, 'vcs-error')
                self.assertIn('nope', str(cm.exception))
                self.assertNotIn('not found in repo', str(cm.exception))
        st = serve.gitlab_status(self.task, gl, self.meta(), 'it1')
        self.assertEqual((st['configured'], st['code']), (True, 'vcs-error'))
        self.assertEqual(sh(['git', 'for-each-ref', '--format=%(refname:short)', 'refs/heads'], self.origin).stdout.split(), ['main'],
                         'у спільному репо зʼявилась гілка')

    def test_a_missing_branch_gives_the_starter_mockup_for_a_new_task(self):
        r = serve.task_new(self.cfg(), 'nova', title='Нова', gitlab={'repo': self.origin, 'path': 'mockup/nova', 'branch': 'nope'})
        self.assertFalse(r['cloned'])
        self.assertTrue(os.path.isfile(os.path.join(r['dir'], 'iterations', 'it1', 'index.html')))

    def hold_the_mirror(self):
        """Інша операція тримає дзеркало: `flock` на `<дзеркало>@lock` (так тримає його сам модуль)."""
        self.assertTrue(self.sync(record=False)['synced'])          # дзеркало й тека лок-файла зʼявились
        fh = open(serve.vcs_mirror_dir(self.gl) + '@lock', 'a+')
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        self.addCleanup(fh.close)

    @unittest.skipUnless(fcntl, 'flock')
    def test_the_status_does_not_wait_for_a_busy_mirror(self):
        """Поправка 6: `status` не чекає лока — `vcs-busy` одразу, станом із `code`; опит смуги не висить за відправкою."""
        self.hold_the_mirror()
        t0 = time.monotonic()
        st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1')
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual((st['configured'], st['code']), (True, 'vcs-busy'))

    @unittest.skipUnless(fcntl, 'flock')
    def test_the_autosync_keeps_a_busy_mirror_quiet(self):
        """Поправка 6: `push` чекає `LOCK_WAIT`, а не вічно; зайняте дзеркало для автосинку — тихий `offline` з `code`
        (Stop-хук не кричить на кожній відповіді, відбиток лишається старим)."""
        self.hold_the_mirror()
        self.write_it1('<h1>v8</h1>')
        before = json.dumps(self.meta().get('gitlab'), sort_keys=True)
        push = serve.vcs_provider()[0].fn('push')
        with mock.patch.dict(push.__globals__, {'LOCK_WAIT': 0.3}):
            r = serve.autosync('t1', self.task, self.gl)
        self.assertEqual((r['reason'], r['code'], r['synced']), ('offline', 'vcs-busy', False))
        self.assertEqual(json.dumps(self.meta().get('gitlab'), sort_keys=True), before)

    # ---------------------------------------------------------------- ЛІГА: нова задача
    def cfg(self):
        return {'tasks': {}, 'design_work_root': os.path.join(self.tmp, 'dw'), 'gitlab': {}}

    def test_a_foreign_clone_in_legacy_forks_with_the_gitlab_note(self):
        self.sync()
        self.peer_state('<h1>чуже</h1>', 'Ольга Сидорук', 'designer2@example.com')
        r = serve.task_new(self.cfg(), 'nova', title='Нова', gitlab={'repo': self.origin, 'path': 'mockup/t1'})
        self.assertTrue(r['cloned'])
        with open(os.path.join(r['dir'], 'iterations.json'), encoding='utf-8') as fh:
            its = json.load(fh)['iterations']
        self.assertEqual([i['id'] for i in its], ['it1', 'it2'])
        self.assertEqual(its[1]['note'], 'продовження макета з GitLab')
        self.assertEqual(its[0]['author'], 'Ольга Сидорук')

    def test_task_new_records_the_gitlab_mapping_and_no_vcs_field(self):
        cfg = self.cfg()
        serve.task_new(cfg, 'nova', title='Нова', gitlab={'repo': self.origin, 'path': 'mockup/nova'})
        self.assertEqual(cfg['tasks']['nova']['gitlab'], {'repo': self.origin, 'path': 'mockup/nova'})
        self.assertNotIn('vcs', cfg['tasks']['nova'])

    def test_task_new_from_an_unreachable_gitlab_gives_the_starter_mockup(self):
        r = serve.task_new(self.cfg(), 'nova', title='Нова', gitlab={'repo': '/нема/такого.git', 'path': 'mockup/nova'})
        self.assertFalse(r['cloned'])
        self.assertTrue(os.path.isfile(os.path.join(r['dir'], 'iterations', 'it1', 'index.html')))
        self.assertEqual(os.listdir(self.systmp), [])

    def test_task_new_with_a_vcs_target_beats_the_profile_default(self):
        """Явний `vcs.repo` перемагає профільний `gitlab` (той, що ставиться за `profile`) — як у `vcs_target`."""
        self.peer_push({'mockup/nova/index.html': '<h1>з origin</h1>'})
        cfg = self.cfg()
        r = serve.task_new(cfg, 'nova', title='Нова', profile='united', vcs={'repo': self.origin})
        self.assertTrue(r['cloned'], 'ціль клону — профільне репо замість явного vcs.repo')
        self.assertEqual(cfg['tasks']['nova']['vcs'], {'repo': self.origin})
        with open(os.path.join(r['dir'], 'iterations', 'it1', 'index.html'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '<h1>з origin</h1>')

    def test_task_new_with_vcs_and_a_folder_to_adopt_does_not_pull(self):
        """Поправка 1: `vcs` із `from` отримання не робить; ЛІГА-`gitlab` — як було (без `from` тут не буває)."""
        folder = os.path.join(self.tmp, 'adopt')
        write(os.path.join(folder, 'index.html'), '<h1>моя тека</h1>')
        self.peer_push({'mockup/nova/index.html': '<h1>з origin</h1>'})
        with mock.patch.object(serve, '_vcs_call', side_effect=AssertionError('отримання з `from`')):
            r = serve.task_new(self.cfg(), 'nova', title='Нова', profile=None, vcs={'repo': self.origin},
                               adopt_src=folder, adopt_files=['index.html'])
        self.assertFalse(r['cloned'])
        self.assertEqual(r['adopted']['files'], 1)
        with open(os.path.join(r['dir'], 'iterations', 'it1', 'index.html'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '<h1>моя тека</h1>')


class Plain(Core):
    """Звичайний простір без інтеграцій, `git-sync` підключено, репо — локальний bare."""
    PLAIN = True

    def setUp(self):
        super().setUp()
        self.sp = self.make_space()
        self.cfg = serve.load_tasks()

    def vt(self):
        """`vcs_task` для задачі `t1`: `(module, ctx, legacy, target)`."""
        return serve.vcs_task(self.cfg, 't1', self.task)

    # ---------------------------------------------------------------- постачальник і ціль
    def test_the_provider_is_the_module_of_the_space_with_a_cache_under_the_deai_home(self):
        m, ctx, legacy = serve.vcs_provider()
        self.assertEqual((m.id, legacy), ('git-sync', False))
        self.assertEqual(ctx['cache_dir'], os.path.join(self.deai, 'cache', self.sp['id'], 'git-sync'))
        self.assertNotIn('mirror_flat', ctx)
        self.assertEqual(ctx['settings']['repo'], self.origin)
        self.assertIs(ctx['settings']['autosync'], False)

    def test_the_target_comes_from_the_settings_of_the_module(self):
        v = self.vt()
        self.assertEqual(v[3], {'repo': self.origin, 'task': 't1', 'path': 'mockup/t1', 'branch': 'main'})
        dm.write_module_state(self.sp, 'git-sync', settings={'path': 'docs/{task}', 'branch': 'dev'})
        self.assertEqual(self.vt()[3], {'repo': self.origin, 'task': 't1', 'path': 'docs/t1', 'branch': 'dev'})

    def test_a_gitlab_field_of_a_task_is_ignored_without_integrations(self):
        """Ключ `gitlab{}` у задачі діє лише в просторі з інтеграціями: тут цілі з нього не буде, лише з налаштувань."""
        task = {**self.task, 'gitlab': {'repo': 'git@h:o/r.git', 'path': 'mockup/x'}}
        self.assertEqual(serve.vcs_task(self.cfg, 't1', task)[3]['repo'], self.origin)
        dm.write_module_state(self.sp, 'git-sync', settings={'repo': None})
        self.assertIsNone(serve.vcs_task(self.cfg, 't1', task)[3], 'gitlab{} без інтеграцій став ціллю')

    def test_a_vcs_field_of_a_task_overrides_the_settings(self):
        other = self.make_origin('other.git')
        task = {**self.task, 'vcs': {'repo': other, 'path': 'x/{task}'}}
        self.assertEqual(serve.vcs_task(self.cfg, 't1', task)[3],
                         {'repo': other, 'task': 't1', 'path': 'x/t1', 'branch': 'main'})

    def test_a_space_without_the_module_has_no_provider(self):
        self.make_space('Beta', enable=False)
        self.assertIsNone(serve.vcs_provider())
        self.assertIsNone(serve.vcs_task(self.cfg, 't1', self.task))
        self.assertEqual(serve.gitlab_status(self.task, self.gl, self.meta(), 'it1', vcs=None), {'configured': False})

    def test_an_unreadable_space_json_is_a_vcs_error_with_the_frame_code(self):
        write(os.path.join(self.sp['path'], 'space.json'), '{')
        with self.assertRaises(serve.VcsError) as cm:
            serve.vcs_provider()
        self.assertEqual(cm.exception.code, 'space-json-unreadable')
        self.assertIsInstance(cm.exception, OSError)
        with self.assertRaises(serve.VcsError):
            serve.vcs_task(self.cfg, 't1', self.task)

    def test_a_module_that_cannot_build_its_ctx_is_a_vcs_error(self):
        with mock.patch.object(dm, 'module_ctx', side_effect=dm.ModuleError('bad-settings', message='x')):
            with self.assertRaises(serve.VcsError) as cm:
                serve.vcs_provider()
        self.assertEqual(cm.exception.code, 'bad-settings')

    def test_mirror_dir_is_known_to_the_module_and_may_be_unknown_for_an_own_one(self):
        md = serve.vcs_mirror_dir(self.vt()[3])
        self.assertTrue(md.startswith(os.path.join(self.deai, 'cache', self.sp['id'], 'git-sync', 'mirrors') + os.sep), md)
        no_dir = dm.Module('own-vcs', roles=['vcs'], fns={'status': lambda c, t: {}, 'push': lambda *a: {},
                                                          'pull': lambda *a: {}})
        self.assertIsNone(serve.vcs_mirror_dir(self.gl, vcs=(no_dir, {}, False)),
                          'без mirror_dir шлях дзеркала невідомий і не показується')

    def test_a_legacy_space_with_integrations_and_no_module_runs_the_legacy_provider(self):
        self.make_space('Liga', integrations=True, enable=False)
        m, ctx, legacy = serve.vcs_provider()
        self.assertEqual((m.id, legacy), ('git-sync', True))
        self.assertEqual((ctx['cache_dir'], ctx['mirror_flat']), (self.mirrors, True))
        self.assertEqual(ctx['space']['id'], 'liga')
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'cache')), 'кеш Deai створено для ЛІГИ')

    def test_an_explicit_git_sync_in_a_liga_space_wins_over_legacy_and_uses_the_gitlab_target(self):
        sp = self.make_space('Liga', integrations=True)
        m, ctx, legacy = serve.vcs_provider()
        self.assertFalse(legacy)
        self.assertEqual(ctx['cache_dir'], os.path.join(self.deai, 'cache', sp['id'], 'git-sync'))
        task = {**self.task, 'gitlab': {'repo': 'git@h:o/r.git', 'path': 'mockup/t1', 'ssh_key': '/k'}}
        t = serve.vcs_task(self.cfg, 't1', task)[3]
        self.assertEqual((t['repo'], t['ssh_key']), ('git@h:o/r.git', '/k'))

    # ---------------------------------------------------------------- повний цикл
    def test_the_full_cycle(self):
        r = self.sync(vcs=self.vt()[:3])
        self.assertTrue(r['synced'] and r['changed'], r)
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%s'), 'deai: sync mockup/t1 (Тест) · it1')
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%an'), 'Lead')
        st = serve.gitlab_status(self.task, self.vt()[3], self.meta(), 'it1', vcs=self.vt()[:3])
        self.assertEqual((st['label'], st['web']), ('Git', None))
        self.assertEqual((st['configured'], st['dirty'], st['on_remote'], st['behind']), (True, False, True, 0))
        # колега
        self.peer_push({'mockup/t1/index.html': '<h1>колега</h1>'})
        r = serve.gitlab_pull(self.task, self.vt()[3])
        self.assertEqual(r['iteration']['note'], 'оновлення з репозиторію')
        self.assertNotIn('GitLab', json.dumps(r, ensure_ascii=False))
        # чужий автор → форк
        self.peer_state('<h1>Ольжине</h1>', 'Ольга Сидорук', 'designer2@example.com')
        r = serve.gitlab_pull(self.task, self.vt()[3])
        self.assertEqual((r['iteration']['author'], r['fork']['note']),
                         ('Ольга Сидорук', 'продовження після оновлення з репозиторію'))
        self.assertEqual(os.listdir(self.systmp), [])

    def test_the_provider_is_found_by_the_functions_themselves(self):
        self.assertTrue(self.sync()['synced'])
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%s'), 'deai: sync mockup/t1 (Тест) · it1')
        st = serve.gitlab_status(self.task, self.vt()[3], self.meta(), 'it1')
        self.assertEqual((st['configured'], st['label']), (True, 'Git'))

    def test_the_mirror_lives_under_the_deai_cache_and_not_in_the_mirrors_env(self):
        self.sync()
        self.assertTrue(os.path.isdir(os.path.join(serve.vcs_mirror_dir(self.vt()[3]), '.git')))
        self.assertFalse(os.path.exists(self.mirrors))

    def test_the_readme_names_the_tool_not_design_canvas(self):
        self.multipage()
        self.assertTrue(self.sync()['synced'])
        sh(['git', 'pull', '-q', '--ff-only', 'origin', 'main'], self.peer)
        with open(os.path.join(self.peer, 'mockup/t1/README.md'), encoding='utf-8') as fh:
            readme = fh.read()
        self.assertIn('(Deai Canvas, задача `t1`)', readme)
        self.assertNotIn('design-canvas', readme)

    def test_the_older_own_note_names_the_repository(self):
        self.sync()
        self.peer_state('<h1>з другої машини</h1>', 'Lead', 'lead@example.com', when=time.time() - 3 * 86400)
        self.write_it1('<h1>моє сьогодні</h1>')
        r = serve.gitlab_pull(self.task, self.vt()[3])
        self.assertEqual(r['fork']['note'], 'продовження моєї роботи — з репозиторію приїхала старша версія')

    def test_a_control_character_in_the_title_does_not_block_the_send(self):
        self.task['title'] = 'Червоний\x1b заголовок'
        self.assertTrue(self.sync()['synced'])
        self.assertEqual(self.out(self.origin, 'log', '-1', '--format=%s'), 'deai: sync mockup/t1 (Червоний заголовок) · it1')

    def test_a_refusal_of_the_module_carries_the_code_through_the_old_names(self):
        self.sync()
        self.hide()
        with self.assertRaises(serve.VcsError) as cm:
            serve.gitlab_sync('t1', self.task, self.vt()[3], 'it1')
        self.assertIn(cm.exception.code, ('vcs-error', 'vcs-offline'))
        self.write_it1('<h1>v7</h1>')                      # без правки автосинк вийшов би «clean» ще до мережі
        r = serve.autosync('t1', self.task, self.vt()[3])
        self.assertEqual((r['reason'], r['code'] in ('vcs-error', 'vcs-offline')), ('offline', True))

    def test_a_repo_with_spaces_in_the_settings_still_syncs(self):
        """`validate` модуля відкидає `repo != repo.strip()`: обрізане ядром у цілі, тож пробіл із форми не блокує синк."""
        dm.write_module_state(self.sp, 'git-sync', settings={'repo': f'  {self.origin} '})
        target = self.vt()[3]
        self.assertEqual(target['repo'], self.origin)
        r = serve.gitlab_sync('t1', self.task, target, 'it1')
        self.assertTrue(r['synced'], r)

    # ---------------------------------------------------------------- нова задача
    def new(self, tid='t2', **kw):
        kw.setdefault('vcs', {'repo': self.origin})
        return serve.task_new(self.cfg, tid, title='Нова', profile=None, root=self.sp['path'], **kw)

    def test_task_new_takes_the_mockup_from_the_repo(self):
        self.peer_state('<h1>з репо</h1>', 'Ольга Сидорук', 'designer2@example.com', path='mockup/t2')
        r = self.new()
        self.assertTrue(r['cloned'])
        self.assertEqual(self.cfg['tasks']['t2']['vcs'], {'repo': self.origin})
        self.assertNotIn('gitlab', self.cfg['tasks']['t2'])
        with open(os.path.join(r['dir'], 'iterations', 'it1', 'index.html'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '<h1>з репо</h1>')
        with open(os.path.join(r['dir'], 'iterations.json'), encoding='utf-8') as fh:
            its = json.load(fh)['iterations']
        self.assertEqual((its[0]['author'], [i['id'] for i in its]), ('Ольга Сидорук', ['it1', 'it2']))
        self.assertEqual(its[1]['note'], 'продовження макета з репозиторію')
        self.assertEqual(os.listdir(self.systmp), [])

    def test_task_new_trims_the_repo_before_it_reaches_the_module(self):
        self.peer_push({'mockup/t2/index.html': '<h1>з репо</h1>'})
        r = self.new(vcs={'repo': f' {self.origin}\n'})
        self.assertTrue(r['cloned'], 'репо з пробілами дійшло до validate необрізаним')

    def test_task_new_without_an_index_html_in_the_repo_gives_the_starter(self):
        self.peer_push({'mockup/t2/readme.txt': 'без index'})
        r = self.new()
        self.assertFalse(r['cloned'])
        with open(os.path.join(r['dir'], 'iterations', 'it1', 'index.html'), encoding='utf-8') as fh:
            self.assertIn('Нова', fh.read())
        self.assertEqual(self.cfg['tasks']['t2']['vcs'], {'repo': self.origin}, 'vcs пишеться і без клону')

    def test_task_new_with_an_unreachable_origin_gives_the_starter_without_an_error(self):
        self.hide()
        r = self.new()
        self.assertFalse(r['cloned'])
        self.assertTrue(os.path.isfile(os.path.join(r['dir'], 'iterations', 'it1', 'index.html')))
        self.assertEqual(os.listdir(self.systmp), [])

    def test_task_new_with_a_bad_repo_is_the_starter_too(self):
        r = self.new(vcs={'repo': 'ext::sh -c id'})
        self.assertFalse(r['cloned'])

    def test_task_new_without_vcs_never_asks_the_provider(self):
        with mock.patch.object(serve, 'vcs_provider', side_effect=AssertionError('постачальник без vcs')):
            r = serve.task_new(self.cfg, 't3', title='Нова', profile=None, root=self.sp['path'])
        self.assertFalse(r['cloned'])
        self.assertNotIn('vcs', self.cfg['tasks']['t3'])

    def test_task_new_with_vcs_and_a_folder_to_adopt_does_not_pull_and_records_vcs(self):
        folder = os.path.join(self.tmp, 'adopt')
        write(os.path.join(folder, 'index.html'), '<h1>моя тека</h1>')
        self.peer_push({'mockup/t2/index.html': '<h1>з origin</h1>'})
        with mock.patch.object(serve, '_vcs_call', side_effect=AssertionError('отримання з `from`')):
            r = self.new(adopt_src=folder, adopt_files=['index.html'])
        self.assertFalse(r['cloned'])
        self.assertEqual(self.cfg['tasks']['t2']['vcs'], {'repo': self.origin})

    def test_a_gitlab_mapping_is_still_refused_without_integrations(self):
        with self.assertRaises(spaces.IntegrationsOff):
            serve.task_new(self.cfg, 't4', gitlab={'repo': self.origin, 'path': 'mockup/t4'}, profile=None,
                           root=self.sp['path'])
        self.assertFalse(os.path.exists(os.path.join(self.sp['path'], 't4')))


if __name__ == '__main__':
    unittest.main()
