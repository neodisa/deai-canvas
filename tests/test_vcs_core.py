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
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

try:
    import fcntl
except ImportError:                          # Windows: лок модуля там інший (`msvcrt`), тест його не торкається
    fcntl = None

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402
import iter_history  # noqa: E402
from liga_fixture import LigaFixture  # noqa: E402
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

    def league_explicit(self):
        """ІЗОЛЬОВАНИЙ простір ЛІГА з явним записом `git-sync` (`compat = design-canvas`) на місці колишнього неявного постачальника
        (4d-4b): `LigaFixture` кладе реєстр, запис і секрети в тимчасовий дім, простір запиту зафіксовано. `DC_TASKS_FILE`/`DC_NO_OVERVIEW`
        лишаються (ізоляція), тож `ctx` — фіксований (закон ізоляції): налаштування запису не читаються, дзеркала плоскі в `DC_MIRRORS_DIR`."""
        fx = LigaFixture(self, tmp=self.tmp)
        fx.tasks_path = os.environ['DC_TASKS_FILE']
        fx.env(DC_TASKS_FILE=os.environ['DC_TASKS_FILE'], DC_NO_OVERVIEW='1', DC_MIRRORS_DIR=self.mirrors)
        # ключ і IP сервера в записі не потрібні (ізольований `ctx` їх не бачить; цілі їх несе саме задача)
        fx.build(roles=('vcs',), overrides={'vcs': {'settings': {'ssh_key': '', 'host_ip': ''}}})
        fx.fix_space()
        with open(fx.tasks_path, 'w', encoding='utf-8') as f:
            json.dump({'tasks': {}, 'current': None}, f)
        self.fx = fx
        return fx

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
    """Ізольований прогін у просторі ЛІГА (`DC_TASKS_FILE`): постачальник — ЯВНИЙ запис `git-sync` із `compat == "design-canvas"` (4d-4b:
    неявного `'legacy'` більше нема; запис кладе `LigaFixture`, простір запиту зафіксовано на ньому). В ізольованому прогоні `ctx` — фіксований
    (закон ізоляції), тож налаштування запису тут не читаються, як і раніше в неявного постачальника."""

    def setUp(self):
        super().setUp()
        self.league_explicit()

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
        """Поправка 9 ревʼю Task 3: `module_ctx` каркаса кладе `cache_dir` під `spaces.home()`. Ізольований шлях ЛІГИ живе на СВОЄМУ `ctx`:
        дзеркало — під `DC_MIRRORS_DIR`. 4d-4b: дім Deai у стенді існує (реєстр і запис), тож замість «домівки нема» — «кешу під домівкою нема»."""
        self.assertTrue(spaces.home().startswith(self.tmp), 'передумова: домівка — тимчасова')
        self.assertTrue(self.sync()['synced'])
        self.assertTrue(os.path.isdir(os.path.join(serve.vcs_mirror_dir(self.gl), '.git')))
        self.assertFalse(os.path.exists(os.path.join(spaces.home(), 'cache')), 'кеш зʼявився під домівкою Deai')
        self.assertEqual(sorted(os.listdir(spaces.home())), ['secrets.json', 'spaces.json'], 'у домі Deai зʼявилось щось крім стенда')

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
        self.assertIn('module catalog', str(cm.exception))
        # Рішення контролера 4d-4b (I2): порожній каталог при ЯВНО ввімкненому записі `git-sync` — ПОМИЛКА (`module-error` → `VcsError`), а не
        # мовчазне `None` (інакше здорова ЛІГА тихо втратила б `vcs`: `task-new` 400, `configured: False`); БЕЗ запису лишається `None`.
        with mock.patch.object(dm, 'catalog', return_value={}):
            with self.assertRaises(serve.VcsError) as cm:
                serve.vcs_provider()
            self.assertEqual(cm.exception.code, 'module-error')
            st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1')
            self.assertEqual((st['configured'], st['code']), (True, 'module-error'))
            with mock.patch.object(dm, 'space_modules', return_value={}):               # запису нема — ролі нема
                self.assertIsNone(serve.vcs_provider())
        with mock.patch.object(dm, 'catalog', side_effect=RuntimeError('boom')):
            st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1')
        self.assertEqual((st['configured'], st['code']), (True, 'vcs-error'))

    # ---------------------------------------------------------------- ціль
    def target(self, task, settings=None, tid='t1'):
        # 4d-4b (R4): `vcs_target(tid, task, settings)` — без `cfg`: кореня `tasks.json` у ланцюгу ключа й IP більше нема.
        return serve.vcs_target(tid, task, {'branch': 'main', 'path': 'mockup/{task}'} if settings is None else settings)

    def test_a_gitlab_task_gives_a_target_without_none_fields(self):
        t = self.target({'gitlab': {'repo': 'git@h:o/r.git', 'path': '/mockup/t1/'}})
        self.assertEqual(t, {'repo': 'git@h:o/r.git', 'path': 'mockup/t1', 'branch': 'main', 'task': 't1'})

    def test_gitlab_without_a_path_or_repo_is_a_task_that_is_not_set_up(self):
        for gl in ({'repo': 'git@h:o/r.git'}, {'path': 'mockup/t1'}, {'repo': '', 'path': 'mockup/t1'}, {}):
            with self.subTest(gl=gl):
                self.assertIsNone(self.target({'gitlab': gl}))
        self.assertIsNone(self.target({}))

    def test_the_gitlab_target_carries_the_key_and_ip_of_the_task_only(self):
        """Було `…_of_the_task_or_the_shared_ones` (ключ і IP — задачі, інакше спільні з кореня `tasks.json`). 4d-4b: спільні живуть в
        налаштуваннях запису `git-sync` (їх бере модуль), ціль їх не несе; корінь `tasks.json` не читається взагалі (негатив)."""
        self.write_root_keys('/k/shared', '10.0.0.7')
        t = self.target({'gitlab': {'repo': 'git@h:o/r.git', 'path': 'p'}})
        self.assertNotIn('ssh_key', t, 'спільний ключ — справа налаштувань модуля, а не цілі')
        self.assertNotIn('host_ip', t)
        t = self.target({'gitlab': {'repo': 'git@h:o/r.git', 'path': 'p', 'ssh_key': '/k/own', 'host_ip': '10.0.0.8'}})
        self.assertEqual((t['ssh_key'], t['host_ip']), ('/k/own', '10.0.0.8'))
        self.assertNotIn('ssh_key', serve.vcs_provider()[1]['settings'])
        self.assertNotIn('host_ip', serve.vcs_provider()[1]['settings'])

    def write_root_keys(self, key, ip):
        """Старий спільний ключ і IP у КОРЕНІ файла задач — лише щоб довести, що корінь більше не читається (негативний assert)."""
        with open(os.environ['DC_TASKS_FILE'], 'w', encoding='utf-8') as f:
            json.dump({'tasks': {}, 'current': None, 'gitlab_ssh_key': key, 'gitlab_host_ip': ip}, f)

    def test_the_gitlab_target_of_the_league_is_the_070_result_in_effective_values(self):
        """Було `…_of_the_legacy_provider_is_the_070_result_byte_for_byte` (ревʼю c191cfb, Minor 3): ціль зі старого `gitlab{}` = `gitlab_cfg` +
        відсів порожніх 0.7.0, байт у байт. 4d-4b: спільні ключ і IP — налаштування запису `git-sync`, а не корінь, тож ціль їх НЕ несе, коли
        задача не має своїх; еталон 0.7.0 (власна копія в тесті, з `cfg` = налаштування запису) порівнюється ЕФЕКТИВНИМИ значеннями
        (`ціль.поле або налаштування.поле` — так обирає модуль) і порядком решти ключів цілі."""
        def old(cfg, tid, task):                     # `gitlab_cfg` 0.7.0 + відсів порожніх, дослівно
            g = task.get('gitlab')
            if not g or not g.get('repo') or not g.get('path'):
                return None
            key = g.get('ssh_key') or cfg.get('gitlab_ssh_key')
            gl = {'repo': g['repo'], 'path': g['path'].strip('/'), 'ssh_key': os.path.expanduser(key) if key else None,
                  'branch': g.get('branch', 'main'), 'host_ip': g.get('host_ip') or cfg.get('gitlab_host_ip')}
            return {**{k: x for k, x in gl.items() if x}, 'task': tid, 'repo': str(gl['repo']).strip()}
        settings = serve._vcs_legacy_ctx()['settings']
        r, p = 'git@h:o/r.git', 'mockup/t1'
        gitlabs = ({'repo': r, 'path': '/mockup/t1/'}, {'repo': r, 'path': p, 'branch': 'dev'}, {'repo': r, 'path': p, 'ssh_key': '/k/own'},
                   {'repo': r, 'path': p, 'ssh_key': '~/k', 'host_ip': '10.0.0.8'}, {'repo': r, 'path': p, 'host_ip': '10.0.0.8'},
                   {'repo': ' ' + r + ' ', 'path': p}, {'repo': r}, {'path': p}, {'repo': '', 'path': p}, {}, {'repo': r, 'path': p, 'ssh_key': '', 'host_ip': ''})
        cfgs = ({}, {'gitlab_ssh_key': '/k/shared'}, {'gitlab_host_ip': '10.0.0.7'},
                {'gitlab_ssh_key': '~/s', 'gitlab_host_ip': '10.0.0.7'}, {'gitlab_ssh_key': '', 'gitlab_host_ip': None})
        seen = 0
        for gl in gitlabs:
            for cfg in cfgs:
                with self.subTest(gitlab=gl, shared=cfg):
                    task = {'gitlab': gl}
                    got, want = serve.vcs_target('t1', task, settings), old(cfg, 't1', task)
                    if want is None:
                        self.assertIsNone(got)
                        continue
                    seen += 1
                    rec = {'ssh_key': cfg.get('gitlab_ssh_key'), 'host_ip': cfg.get('gitlab_host_ip')}      # налаштування запису `git-sync`

                    def effective(target):
                        key, ip = target.get('ssh_key') or rec['ssh_key'], target.get('host_ip') or rec['host_ip']
                        return {'ssh_key': os.path.expanduser(key) if key else None, 'host_ip': ip or None}
                    self.assertEqual(effective(got), effective(want), 'ефективні ключ і IP змінились')
                    rest = lambda t: {k: x for k, x in t.items() if k not in ('ssh_key', 'host_ip')}  # noqa: E731
                    self.assertEqual(rest(got), rest(want))
                    self.assertEqual(json.dumps(rest(got)), json.dumps(rest(want)), 'порядок ключів цілі змінився')
        self.assertGreater(seen, 30, 'передумова: більшість рядків таблиці дає справжню ціль')

    def test_the_vcs_field_of_a_liga_task_does_not_take_the_root_key_and_ip(self):
        """Було `…_carries_the_shared_key_and_ip_too` (ревʼю Task 5 (M7), поправка 7: ключ/IP задачі, інакше спільні з кореня — і коли ціль із
        `task.vcs`). 4d-4b: корінь не читається — ціль із `task.vcs` без своїх полів ключа й IP не несе (їх бере модуль з налаштувань запису);
        `~` власного ключа розгортається, як і було."""
        self.write_root_keys('/k/shared', '10.0.0.7')
        t = self.target({'vcs': {'repo': 'git@h:o/r.git'}})
        self.assertEqual(t, {'repo': 'git@h:o/r.git', 'path': 'mockup/t1', 'branch': 'main', 'task': 't1'})
        t = self.target({'vcs': {'repo': 'git@h:o/r.git', 'ssh_key': '~/k'}})
        self.assertEqual(t['ssh_key'], os.path.expanduser('~/k'))

    def test_the_own_key_and_ip_of_a_liga_task_are_the_only_ones_in_a_vcs_target(self):
        """Було `…_beat_the_shared_ones_for_a_vcs_target`: пріоритет тепер `своє поле задачі (vcs{}, далі gitlab{}) > налаштування модуля`;
        корінь — лише негатив (див. `write_root_keys`)."""
        self.write_root_keys('/k/shared', '10.0.0.7')
        own_in_vcs = self.target({'vcs': {'repo': 'git@h:o/r.git', 'ssh_key': '/k/own', 'host_ip': '10.0.0.8'}})
        self.assertEqual((own_in_vcs['ssh_key'], own_in_vcs['host_ip']), ('/k/own', '10.0.0.8'))
        own_in_gitlab = self.target({'vcs': {'repo': 'git@h:o/r.git'}, 'gitlab': {'ssh_key': '/k/g', 'host_ip': '10.0.0.9'}})
        self.assertEqual((own_in_gitlab['ssh_key'], own_in_gitlab['host_ip']), ('/k/g', '10.0.0.9'))

    def test_a_vcs_target_of_a_liga_task_has_no_key_fields_when_nobody_sets_them(self):
        self.write_root_keys('', None)
        t = self.target({'vcs': {'repo': 'git@h:o/r.git'}})
        self.assertEqual(t, {'repo': 'git@h:o/r.git', 'task': 't1', 'path': 'mockup/t1', 'branch': 'main'})
        self.assertEqual(self.target({'vcs': {'repo': 'git@h:o/r.git'}}),
                         {'repo': 'git@h:o/r.git', 'task': 't1', 'path': 'mockup/t1', 'branch': 'main'})

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

    def test_the_local_autocommit_of_the_autosync_keeps_the_design_canvas_signature_in_liga(self):
        """Ревʼю Task 5 (M10), поправка 12: текст даних ЛІГИ лишається — і коли постачальник даний, і коли ядро знаходить його саме."""
        self.write_it1('<h1>v-local-1</h1>')
        serve.autosync('t1', self.task, self.gl)
        self.assertEqual(self.out(self.task_dir, 'log', '-1', '--format=%s'), 'it1: автосинк (design-canvas)')
        self.write_it1('<h1>v-local-2</h1>')
        serve.autosync('t1', self.task, self.gl, vcs=serve.vcs_provider())
        self.assertEqual(self.out(self.task_dir, 'log', '-1', '--format=%s'), 'it1: автосинк (design-canvas)')

    # ---------------------------------------------------------------- крок 2 без трейлера AI (спека Stop-хука, розділ 5)
    def test_the_autosync_commit_is_a_person_commit_without_the_ai_trailer(self):
        """Крок 2 комітить решту теки (і файл поза ітераціями) БЕЗ `Deai-Actor: ai`.
        Мутація: поверни `\\n\\n{iter_history.AI_TRAILER}` у тему коміту в `autosync()` — тест червоніє."""
        self.write_it1('<h1>v-plain</h1>')
        write(os.path.join(self.task_dir, 'notes.md'), 'чиясь нотатка')
        serve.autosync('t1', self.task, self.gl)
        self.assertEqual(self.out(self.task_dir, 'log', '-1', '--format=%B'), 'it1: автосинк (design-canvas)')
        self.assertIn('notes.md', self.out(self.task_dir, 'show', '--name-only', '--format=', 'HEAD').split())

    def test_the_first_commit_of_a_folder_without_git_is_not_signed_ai(self):
        """Тека без `.git`: крок 1 її не чіпає (`ai_commit` → `None`), крок 2 створює репо — і перший коміт теж не «AI»."""
        self.assertFalse(os.path.exists(os.path.join(self.task_dir, '.git')))
        self.assertIsNone(serve.ai_commit(self.task))
        serve.autosync('t1', self.task, self.gl)
        self.assertNotIn('Deai-Actor', self.out(self.task_dir, 'log', '--format=%B'))

    def test_after_the_ai_step_a_colleague_edit_is_a_person_sync_and_mine_stays_ai(self):
        """Порядок маршруту `/api/autosync`: `ai_commit` (крок 1), далі `autosync` (крок 2). В історії ітерації колеги — `sync` від
        людини (до поправки — `ai`); у своїй — коміт кроку 1 `ai`, над ним `sync` кроку 2 (тема називає `it1`) від людини."""
        serve.autosync('t1', self.task, self.gl)                      # `.git` і перша відправка
        write(os.path.join(self.task_dir, 'iterations', 'it2', 'index.html'), '<h1>чуже</h1>')
        self.save_meta({'iterations': [{'id': 'it1'},
                                       {'id': 'it2', 'author': 'Ольга', 'author_key': 'designer2@example.com'}],
                        'current': 'it1'})
        self.write_it1('<h1>v-ai</h1>')
        self.assertEqual(serve.ai_commit(self.task)['its'], ['it1'])
        r = serve.autosync('t1', self.task, self.gl)
        self.assertTrue(r.get('synced'), r)
        theirs = iter_history.history(self.task_dir, {'id': 'it2'})['entries'][0]
        self.assertEqual((theirs['kind'], theirs['actor']['kind']), ('sync', 'person'))
        mine = iter_history.history(self.task_dir, {'id': 'it1'})['entries']
        self.assertEqual([(e['kind'], e['actor']['kind']) for e in mine[:2]], [('sync', 'person'), ('ai', 'ai')])

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
        r = serve.task_new(self.cfg(), 'nova', title='Нова', gitlab={'repo': self.origin, 'path': 'mockup/nova', 'branch': 'nope'}, legacy=True)
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

    # ---------------------------------------------------------------- 4-кортеж `vcs_task`
    def test_the_full_vcs_task_tuple_goes_through_all_four_functions(self):
        """Контракт: `vcs_task` дає `(module, ctx, legacy, target)`, і маршрут передає ЦЕЙ кортеж як `vcs=` у всі старі імена.
        Розпаковка з трьох (`m, ctx, legacy = v`) падала б тут, а не на живому маршруті."""
        task = {**self.task, 'gitlab': dict(self.gl)}
        v = serve.vcs_task('t1', task)               # 4d-4b (R4): без `cfg`
        self.assertEqual((len(v), v[2]), (4, True))
        gl = v[3]
        r = serve.gitlab_sync('t1', task, gl, 'it1', vcs=v)
        self.assertTrue(r['synced'], r)
        serve._record_sync(task, 'it1', r['sha'])
        st = serve.gitlab_status(task, gl, self.meta(), 'it1', vcs=v)
        self.assertEqual((st['configured'], st['label'], st['dirty'], st['on_remote']), (True, 'GitLab', False, True))
        self.write_it1('<h1>v10</h1>')
        auto = serve.autosync('t1', task, gl, vcs=v)
        self.assertEqual((auto['ok'], auto['synced'], auto['changed']), (True, True, True), auto)
        self.peer_push({'mockup/t1/index.html': '<h1>колега</h1>'})
        pulled = serve.gitlab_pull(task, gl, vcs=v)
        self.assertEqual(pulled['iteration']['note'], 'оновлення з GitLab')

    # ---------------------------------------------------------------- ЛІГА: нова задача
    def cfg(self):
        return {'tasks': {}, 'design_work_root': os.path.join(self.tmp, 'dw'), 'gitlab': {}}

    def test_a_foreign_clone_in_legacy_forks_with_the_gitlab_note(self):
        self.sync()
        self.peer_state('<h1>чуже</h1>', 'Ольга Сидорук', 'designer2@example.com')
        r = serve.task_new(self.cfg(), 'nova', title='Нова', gitlab={'repo': self.origin, 'path': 'mockup/t1'}, legacy=True)
        self.assertTrue(r['cloned'])
        with open(os.path.join(r['dir'], 'iterations.json'), encoding='utf-8') as fh:
            its = json.load(fh)['iterations']
        self.assertEqual([i['id'] for i in its], ['it1', 'it2'])
        self.assertEqual(its[1]['note'], 'продовження макета з GitLab')
        self.assertEqual(its[0]['author'], 'Ольга Сидорук')

    def test_task_new_records_the_gitlab_mapping_and_no_vcs_field(self):
        cfg = self.cfg()
        serve.task_new(cfg, 'nova', title='Нова', gitlab={'repo': self.origin, 'path': 'mockup/nova'}, legacy=True)
        self.assertEqual(cfg['tasks']['nova']['gitlab'], {'repo': self.origin, 'path': 'mockup/nova'})
        self.assertNotIn('vcs', cfg['tasks']['nova'])

    def test_task_new_from_an_unreachable_gitlab_gives_the_starter_mockup(self):
        r = serve.task_new(self.cfg(), 'nova', title='Нова', gitlab={'repo': '/нема/такого.git', 'path': 'mockup/nova'}, legacy=True)
        self.assertFalse(r['cloned'])
        self.assertTrue(os.path.isfile(os.path.join(r['dir'], 'iterations', 'it1', 'index.html')))
        self.assertEqual(os.listdir(self.systmp), [])

    def test_task_new_with_a_vcs_target_beats_the_profile_default(self):
        """Явний `vcs.repo` перемагає `gitlab` репо напрямку (ЛІГА; раніше — за `profile`) — як у `vcs_target`."""
        self.peer_push({'mockup/nova/index.html': '<h1>з origin</h1>'})
        cfg = self.cfg()
        r = serve.task_new(cfg, 'nova', title='Нова', track='united', legacy=True, repo='ssh://git@example.com/o/r.git',
                           vcs={'repo': self.origin})
        self.assertEqual(cfg['tasks']['nova']['gitlab']['repo'], 'ssh://git@example.com/o/r.git')   # репо напрямку теж записано
        self.assertTrue(r['cloned'], 'ціль клону — репо напрямку замість явного vcs.repo')
        self.assertEqual(cfg['tasks']['nova']['vcs'], {'repo': self.origin})
        with open(os.path.join(r['dir'], 'iterations', 'it1', 'index.html'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '<h1>з origin</h1>')

    def test_task_new_with_vcs_and_a_folder_to_adopt_does_not_pull(self):
        """Поправка 1: `vcs` із `from` отримання не робить; ЛІГА-`gitlab` — як було (без `from` тут не буває)."""
        folder = os.path.join(self.tmp, 'adopt')
        write(os.path.join(folder, 'index.html'), '<h1>моя тека</h1>')
        self.peer_push({'mockup/nova/index.html': '<h1>з origin</h1>'})
        with mock.patch.object(serve, '_vcs_call', side_effect=AssertionError('отримання з `from`')):
            r = serve.task_new(self.cfg(), 'nova', title='Нова', vcs={'repo': self.origin},
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
        return serve.vcs_task('t1', self.task)

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
        self.assertEqual(serve.vcs_task('t1', task)[3]['repo'], self.origin)
        dm.write_module_state(self.sp, 'git-sync', settings={'repo': None})
        self.assertIsNone(serve.vcs_task('t1', task)[3], 'gitlab{} без інтеграцій став ціллю')

    def test_a_vcs_field_of_a_task_overrides_the_settings(self):
        other = self.make_origin('other.git')
        task = {**self.task, 'vcs': {'repo': other, 'path': 'x/{task}'}}
        self.assertEqual(serve.vcs_task('t1', task)[3],
                         {'repo': other, 'task': 't1', 'path': 'x/t1', 'branch': 'main'})

    def test_the_shared_key_of_the_root_is_not_for_a_space_without_integrations(self):
        """Ключ і IP цілі — речі простору з інтеграціями (ЛІГА): у звичайному просторі `task.vcs` їх не несе, навіть свої (4d-4b: корінь
        `tasks.json` не читається ніде, тож «спільного» тут нема й у вигляді негатива)."""
        t = serve.vcs_task('t1', {**self.task, 'vcs': {'repo': self.origin}})[3]
        self.assertEqual(t, {'repo': self.origin, 'task': 't1', 'path': 'mockup/t1', 'branch': 'main'})
        t = serve.vcs_task('t1', {**self.task, 'vcs': {'repo': self.origin, 'ssh_key': '/k/own', 'host_ip': '10.0.0.8'}})[3]
        self.assertNotIn('ssh_key', t)
        self.assertNotIn('host_ip', t)

    def test_an_explicit_git_sync_in_a_liga_space_leaves_the_shared_key_to_the_module_for_any_origin_of_the_target(self):
        """Було `…_takes_the_shared_key_for_any_origin_of_the_target` (поправка 7 до спеки: спільний ключ з кореня клався в ціль, звідки б вона
        не була). 4d-4b: спільні ключ і IP — налаштування запису; ціль їх не несе (модуль бере з налаштувань), і це так для будь-якого
        походження цілі (`task.vcs` чи налаштування модуля)."""
        self.make_space('Liga', integrations=True, ssh_key='/k/shared', host_ip='10.0.0.7')
        for what, task in (('task.vcs', {**self.task, 'vcs': {'repo': 'git@h:o/r.git'}}), ('налаштування модуля', self.task)):
            with self.subTest(target=what):
                v = serve.vcs_task('t1', task)
                self.assertNotIn('ssh_key', v[3])
                self.assertNotIn('host_ip', v[3])
                self.assertEqual((v[1]['settings']['ssh_key'], v[1]['settings']['host_ip']), ('/k/shared', '10.0.0.7'))

    def test_a_key_in_the_settings_of_the_module_is_not_overridden_by_the_target(self):
        """Було `…_beats_the_shared_one_of_the_root`: тепер спільний — і є налаштуванням запису; ціль ключа не несе, модуль бере його сам."""
        sp = self.make_space('Liga', integrations=True)
        dm.write_module_state(sp, 'git-sync', settings={'ssh_key': '/k/mine'})
        v = serve.vcs_task('t1', self.task)
        self.assertNotIn('ssh_key', v[3])
        self.assertNotIn('host_ip', v[3])
        self.assertEqual(v[1]['settings']['ssh_key'], '/k/mine')

    def test_the_key_and_ip_priority_is_one_for_every_path_of_the_target(self):
        """Ревʼю c191cfb (Minor 3). Правило ОДНЕ для всіх шляхів цілі й окремо для `ssh_key` та `host_ip`: своє поле задачі
        (`vcs{}`, далі `gitlab{}`) > налаштування модуля (цілі поля не несуть — модуль бере своє). 4d-4b: третього щабля (спільний корінь
        `tasks.json`) більше нема — корінь у стенді лежить із «чужими» значеннями лише щоб довести, що жоден шлях цілі його не бере.
        Таблиця: (налаштування запису, поля задачі, що несе ЦІЛЬ, ЕФЕКТИВНІ значення = ціль, інакше налаштування)."""
        sp = self.make_space('Liga', integrations=True)
        write(os.path.join(sp['path'], 'tasks.json'),
              json.dumps({'tasks': {}, 'gitlab_ssh_key': '/k/shared', 'gitlab_host_ip': '10.0.0.7'}))
        r = 'git@h:o/r.git'
        gl = {'repo': r, 'path': 'mockup/t1'}
        both, only_key, only_ip, none = ({'ssh_key': '/k/mine', 'host_ip': '10.1.1.1'}, {'ssh_key': '/k/mine'},
                                         {'host_ip': '10.1.1.1'}, {})
        rows = (
            ('gitlab{} + ключ у налаштуваннях → налаштування', both, {'gitlab': gl}, {}, both),
            ('vcs{} + ключ у налаштуваннях → налаштування', both, {'vcs': {'repo': r}}, {}, both),
            ('налаштування repo + ключ у налаштуваннях → налаштування', both, {}, {}, both),
            ('свій у vcs{} + налаштування → свій', both, {'vcs': {'repo': r, 'ssh_key': '/k/own', 'host_ip': '10.0.0.8'}},
             {'ssh_key': '/k/own', 'host_ip': '10.0.0.8'}, {'ssh_key': '/k/own', 'host_ip': '10.0.0.8'}),
            ('свій у gitlab{} + налаштування → свій (ціль із gitlab{})', both, {'gitlab': {**gl, 'ssh_key': '/k/g', 'host_ip': '10.0.0.9'}},
             {'ssh_key': '/k/g', 'host_ip': '10.0.0.9'}, {'ssh_key': '/k/g', 'host_ip': '10.0.0.9'}),
            ('свій у gitlab{} + налаштування → свій (ціль із vcs{})', both, {'vcs': {'repo': r}, 'gitlab': {'ssh_key': '/k/g', 'host_ip': '10.0.0.9'}},
             {'ssh_key': '/k/g', 'host_ip': '10.0.0.9'}, {'ssh_key': '/k/g', 'host_ip': '10.0.0.9'}),
            ('vcs{} свій раніше за gitlab{} свій, по полях', both, {'vcs': {'repo': r, 'ssh_key': '/k/v'}, 'gitlab': {'ssh_key': '/k/g', 'host_ip': '10.0.0.9'}},
             {'ssh_key': '/k/v', 'host_ip': '10.0.0.9'}, {'ssh_key': '/k/v', 'host_ip': '10.0.0.9'}),
            ('налаштування тримають лише своє поле: ключ', only_key, {'gitlab': gl}, {}, {'ssh_key': '/k/mine'}),
            ('налаштування тримають лише своє поле: IP', only_ip, {'vcs': {'repo': r}}, {}, {'host_ip': '10.1.1.1'}),
            ('своє поле однієї назви + налаштування іншої', only_key, {'vcs': {'repo': r, 'host_ip': '10.0.0.8'}},
             {'host_ip': '10.0.0.8'}, {'ssh_key': '/k/mine', 'host_ip': '10.0.0.8'}),
            ('без налаштувань: ніхто не каже — нічого (корінь НЕ береться) для gitlab{}', none, {'gitlab': gl}, {}, {}),
            ('без налаштувань: корінь НЕ береться для vcs{}', none, {'vcs': {'repo': r}}, {}, {}),
            ('без налаштувань: корінь НЕ береться для налаштувань repo', none, {}, {}, {}),
            ('без налаштувань: свій у vcs{}', none, {'vcs': {'repo': r, 'ssh_key': '/k/own'}}, {'ssh_key': '/k/own'}, {'ssh_key': '/k/own'}),
            ('без налаштувань: свій у gitlab{}', none, {'gitlab': {**gl, 'host_ip': '10.0.0.9'}}, {'host_ip': '10.0.0.9'}, {'host_ip': '10.0.0.9'}),
        )
        for what, settings, fields, carried, effective in rows:
            with self.subTest(what):
                dm.write_module_state(sp, 'git-sync', settings={'ssh_key': None, 'host_ip': None, 'compat': 'design-canvas', **settings})
                v = serve.vcs_task('t1', {**self.task, **fields})
                self.assertEqual({k: (v[1]['settings'].get(k) or None) for k in settings},
                                 {k: x for k, x in settings.items()}, 'передумова: налаштування модуля записались')
                t = v[3]
                self.assertEqual({k: t[k] for k in ('ssh_key', 'host_ip') if k in t}, carried)
                eff = {k: t.get(k) or v[1]['settings'].get(k) for k in ('ssh_key', 'host_ip')}      # так обирає модуль (`_pick`)
                self.assertEqual({k: x for k, x in eff.items() if x}, effective)
                self.assertNotIn('/k/shared', json.dumps(t), 'ключ кореня `tasks.json` потрапив у ціль')
                self.assertNotIn('10.0.0.7', json.dumps(t), 'IP кореня `tasks.json` потрапив у ціль')

    def test_the_local_autocommit_of_the_autosync_is_signed_deai_in_an_ordinary_space(self):
        """Ревʼю Task 5 (M10), поправка 12: «автосинк (deai)» у звичайному просторі — і з готовим постачальником, і без."""
        v = self.vt()
        self.write_it1('<h1>v-deai-1</h1>')
        serve.autosync('t1', self.task, v[3], vcs=v)
        self.assertEqual(self.out(self.task_dir, 'log', '-1', '--format=%s'), 'it1: автосинк (deai)')
        self.write_it1('<h1>v-deai-2</h1>')
        serve.autosync('t1', self.task, v[3])
        self.assertEqual(self.out(self.task_dir, 'log', '-1', '--format=%s'), 'it1: автосинк (deai)')

    def test_a_space_without_the_module_has_no_provider(self):
        self.make_space('Beta', enable=False)
        self.assertIsNone(serve.vcs_provider())
        self.assertIsNone(serve.vcs_task('t1', self.task))
        self.assertEqual(serve.gitlab_status(self.task, self.gl, self.meta(), 'it1', vcs=None), {'configured': False})

    def test_an_unreadable_space_json_is_a_vcs_error_with_the_frame_code(self):
        write(os.path.join(self.sp['path'], 'space.json'), '{')
        with self.assertRaises(serve.VcsError) as cm:
            serve.vcs_provider()
        self.assertEqual(cm.exception.code, 'space-json-unreadable')
        self.assertIsInstance(cm.exception, OSError)
        with self.assertRaises(serve.VcsError):
            serve.vcs_task('t1', self.task)

    def test_a_long_refusal_of_the_frame_is_masked_before_it_is_cut_in_the_provider(self):
        """Ревʼю c191cfb (Minor 2): обидва місця `vcs_provider`, що пакують відмову каркаса у `VcsError`, ріжуть текст до 300
        ПІСЛЯ маски: адреса з токеном, що стартує за 15 символів до межі, інакше лишала б `https://ghp_SEC` (маска без `@`
        нічого не впізнає, а конструктор `VcsError` бачить уже обрізане)."""
        head = 'space-json-unreadable: /p '
        why = 'a' * (285 - len(head)) + f'https://{TOKEN}@github.com/o/r.git'
        exc = spaces.SpacesError('space-json-unreadable', '/p', why)
        self.assertEqual(str(exc).index('https://'), 285, 'передумова: адреса стартує на 285-му символі')
        want = (head + 'a' * (285 - len(head)) + 'https://***@github.com/o/r.git')[:300]
        for site, patch in (('provider()', mock.patch.object(dm, 'provider', side_effect=exc)),
                            ('module_ctx()', mock.patch.object(dm, 'module_ctx', side_effect=exc))):
            with self.subTest(site=site), patch:
                with self.assertRaises(serve.VcsError) as cm:
                    serve.vcs_provider()
                self.assertEqual((cm.exception.code, str(cm.exception)), ('space-json-unreadable', want))
                self.assertNotIn('ghp_SE', str(cm.exception))

    def test_a_module_error_of_the_frame_is_masked_in_the_provider_too(self):
        """`ModuleError` ріже текст до 300 сам, ще в конструкторі: тут повна адреса вміщається, і маска її бере."""
        exc = dm.ModuleError('bad-settings', message=f'ctx failed for https://{TOKEN}@github.com/o/r.git')
        for site, patch in (('provider()', mock.patch.object(dm, 'provider', side_effect=exc)),
                            ('module_ctx()', mock.patch.object(dm, 'module_ctx', side_effect=exc))):
            with self.subTest(site=site), patch:
                with self.assertRaises(serve.VcsError) as cm:
                    serve.vcs_provider()
                self.assertEqual((cm.exception.code, str(cm.exception)), ('bad-settings', 'ctx failed for https://***@github.com/o/r.git'))

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

    def test_a_liga_space_with_integrations_and_no_record_has_no_provider(self):
        """Було `…_and_no_module_runs_the_legacy_provider` (простір з інтеграціями без запису вів неявний постачальник). 4d-4b: неявного нема —
        без запису `git-sync` ролі `vcs` у просторі немає (як у будь-якому)."""
        self.make_space('Liga', integrations=True, enable=False)
        self.assertIsNone(serve.vcs_provider())

    def test_a_liga_space_with_the_compat_record_runs_the_league_texts_and_flat_mirrors(self):
        """Те, що перевіряв попередник на неявному постачальнику, — на ЯВНОМУ записі (`compat = design-canvas`): тексти ЛІГИ, плоскі дзеркала в
        `DC_MIRRORS_DIR`, кешу Deai нема."""
        sp = self.make_space('Liga', integrations=True, enable=False)
        dm.write_module_state(sp, 'git-sync', enabled=True, settings={'compat': 'design-canvas'})
        m, ctx, legacy = serve.vcs_provider()
        self.assertEqual((m.id, legacy), ('git-sync', True))
        self.assertEqual((ctx['cache_dir'], ctx['mirror_flat']), (self.mirrors, True))
        self.assertEqual(ctx['space']['id'], 'liga')
        self.assertFalse(os.path.exists(os.path.join(self.deai, 'cache')), 'кеш Deai створено для ЛІГИ')

    def test_an_explicit_git_sync_without_the_liga_scheme_ignores_the_gitlab_target(self):
        """4d-4c: `gitlab{}` задачі й її ключ діють лише за схемою ЛІГИ (`vcs_outbound`); прапорець простору (`integrations=True`) без
        `compat` більше нічого не відкриває — ціль із налаштувань модуля, без ключа задачі."""
        sp = self.make_space('Liga', integrations=True)
        m, ctx, legacy = serve.vcs_provider()
        self.assertFalse(legacy)
        self.assertEqual(ctx['cache_dir'], os.path.join(self.deai, 'cache', sp['id'], 'git-sync'))
        task = {**self.task, 'gitlab': {'repo': 'git@h:o/r.git', 'path': 'mockup/t1', 'ssh_key': '/k'}}
        t = serve.vcs_task('t1', task)[3]
        self.assertEqual(t['repo'], self.origin)
        self.assertNotIn('ssh_key', t)

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

    def test_the_full_vcs_task_tuple_goes_through_all_four_functions(self):
        """Той самий контракт у звичайному просторі: цілий 4-кортеж `vcs_task` як `vcs=` для всіх старих імен."""
        v = self.vt()
        self.assertEqual((len(v), v[2]), (4, False))
        r = serve.gitlab_sync('t1', self.task, v[3], 'it1', vcs=v)
        self.assertTrue(r['synced'], r)
        serve._record_sync(self.task, 'it1', r['sha'])
        st = serve.gitlab_status(self.task, v[3], self.meta(), 'it1', vcs=v)
        self.assertEqual((st['configured'], st['label'], st['dirty'], st['on_remote']), (True, 'Git', False, True))
        self.write_it1('<h1>v10</h1>')
        auto = serve.autosync('t1', self.task, v[3], vcs=v)
        self.assertEqual((auto['ok'], auto['synced'], auto['changed']), (True, True, True), auto)
        self.peer_push({'mockup/t1/index.html': '<h1>колега</h1>'})
        pulled = serve.gitlab_pull(self.task, v[3], vcs=v)
        self.assertEqual(pulled['iteration']['note'], 'оновлення з репозиторію')

    # ---------------------------------------------------------------- нова задача
    def new(self, tid='t2', **kw):
        kw.setdefault('vcs', {'repo': self.origin})
        return serve.task_new(self.cfg, tid, title='Нова', root=self.sp['path'], **kw)

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
            r = serve.task_new(self.cfg, 't3', title='Нова', root=self.sp['path'])
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



# ======================================================================== адреса без userinfo
TOKEN = 'ghp_SECRETTOKEN123'
#: Адреси з секретом у userinfo: токен у позиції користувача, `user:pass`, пароль із `@`. Другу й третю `validate` справжнього
#: модуля відхиляє, а чужий модуль (довіра 3c) міг би прийняти, тож ядро маскує незалежно від нього.
SECRET_REPOS = {
    'token': (f'https://{TOKEN}@github.com/o/r.git', (TOKEN,)),
    'user:pass': ('https://anna:hunter2@github.com/o/r.git', ('hunter2', 'anna')),
    'password with @': ('https://anna:p@ss@github.com/o/r.git', ('p@ss', 'anna')),
}


class AddressMask(Core):
    """`remote`, `web`, тексти помилок і рядок автосинку НІКОЛИ не несуть userinfo адреси (спека: «тексти помилок і `remote`
    ніколи не несуть пароля з адреси»). Модуль — заглушка: справжній ходив би в мережу по `https://github.com`."""

    def setUp(self):
        super().setUp()
        self.league_explicit()           # 4d-4b: маршрути без явного запису не мають постачальника (було — неявний)

    def mod(self, ctx, repo, **fns):
        return (self.stub(**fns), ctx, False)

    def refuse(self, repo, code='vcs-error'):
        """Функція модуля, що відмовляє текстом із повною адресою (чужий модуль не маскує сам)."""
        def f(ctx, *a, **kw):
            raise ctx['ModuleError'](code, message=f'fetch failed: {repo}')
        return f

    def leak_free(self, obj, secrets):
        text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
        for secret in secrets:
            self.assertNotIn(secret, text)

    def test_the_mask_rule_is_the_one_of_the_module(self):
        for text, want in (('https://TOKEN@h/o/r', 'https://***@h/o/r'),
                           ('https://u:p@ss@h/o/r:mockup/t1', 'https://***@h/o/r:mockup/t1'),
                           ('ssh://git@h:2222/o/r', 'ssh://***@h:2222/o/r'),
                           ('a https://T@x/y b https://U:P@z/w', 'a https://***@x/y b https://***@z/w'),
                           ('git@github.com:o/r.git', 'git@github.com:o/r.git'),
                           ('/srv/репо.git:mockup/t1', '/srv/репо.git:mockup/t1'),
                           ('https://host/path@file', 'https://host/path@file')):
            with self.subTest(text=text):
                self.assertEqual(serve._mask_repo(text), want)
        self.assertIsNone(serve._mask_repo(None))
        self.assertEqual(serve._mask_repo(5), 5)

    def test_a_vcs_error_masks_the_address_in_its_text_and_keeps_the_code(self):
        e = serve.VcsError('vcs-offline', f'fetch failed: https://{TOKEN}@github.com/o/r.git: no route')
        self.assertEqual((e.code, str(e)), ('vcs-offline', 'fetch failed: https://***@github.com/o/r.git: no route'))
        self.assertEqual(str(serve.VcsError('vcs-busy')), 'vcs-busy')

    def test_the_sync_result_carries_a_masked_remote_when_it_is_ok_and_when_it_is_blocked(self):
        ok = {'ok': True, 'synced': True, 'changed': True, 'pushed': True, 'sha': 'abc1234'}
        for name, (repo, secrets) in SECRET_REPOS.items():
            gl = {**self.gl, 'repo': repo}
            for what, result in (('ok', ok), ('behind', {'ok': False, 'synced': False, 'blocked': 'behind', 'behind': 1}),
                                 ('diverged', {'ok': False, 'synced': False, 'blocked': 'diverged'})):
                with self.subTest(repo=name, result=what):
                    v = self.mod(serve._vcs_legacy_ctx(), repo, push=lambda ctx, t, d, m, r=result: dict(r))
                    r = serve.gitlab_sync('t1', self.task, gl, 'it1', vcs=v)
                    self.assertEqual(r['remote'], 'https://***@github.com/o/r.git:mockup/t1')
                    self.leak_free(r, secrets)

    def test_the_status_masks_what_a_foreign_module_returns_and_what_it_says_in_an_error(self):
        for name, (repo, secrets) in SECRET_REPOS.items():
            gl = {**self.gl, 'repo': repo}
            with self.subTest(repo=name):
                leaky = {'behind': 0, 'behind_path': 0, 'unpushed': 0, 'on_remote': True,
                         'web': f'{repo}/commits/main', 'label': f'Git ({repo})'}
                st = serve.gitlab_status(self.task, gl, self.meta(), 'it1',
                                         vcs=self.mod(serve._vcs_legacy_ctx(), repo, status=lambda ctx, t, r=leaky: dict(r)))
                self.assertEqual((st['configured'], st['web']), (True, 'https://***@github.com/o/r.git/commits/main'))
                self.leak_free(st, secrets)
                st = serve.gitlab_status(self.task, gl, self.meta(), 'it1',
                                         vcs=self.mod(serve._vcs_legacy_ctx(), repo, status=self.refuse(repo)))
                self.assertEqual((st['configured'], st['code']), (True, 'vcs-error'))
                self.assertIn('https://***@github.com/o/r.git', st['error'])
                self.leak_free(st, secrets)

    def test_a_refusal_of_a_foreign_module_is_masked_in_sync_pull_and_autosync(self):
        for name, (repo, secrets) in SECRET_REPOS.items():
            gl = {**self.gl, 'repo': repo}
            v = self.mod(serve._vcs_legacy_ctx(), repo, push=self.refuse(repo), pull=self.refuse(repo))
            with self.subTest(repo=name):
                for what, call in (('sync', lambda: serve.gitlab_sync('t1', self.task, gl, 'it1', vcs=v)),
                                   ('pull', lambda: serve.gitlab_pull(self.task, gl, vcs=v))):
                    with self.assertRaises(serve.VcsError, msg=what) as cm:
                        call()
                    self.leak_free(str(cm.exception), secrets)
                    self.leak_free(repr(cm.exception), secrets)
                self.write_it1(f'<h1>{name}</h1>')
                r = serve.autosync('t1', self.task, gl, vcs=v)
                self.assertEqual((r['reason'], r['code']), ('offline', 'vcs-error'))
                self.assertIn('https://***@github.com/o/r.git', r['error'])
                self.leak_free(r, secrets)

    def test_a_successful_autosync_and_pull_carry_no_secret_either(self):
        repo, secrets = SECRET_REPOS['token']
        gl = {**self.gl, 'repo': repo}

        def pull(ctx, t, d, o=None):
            write(os.path.join(d, 'index.html'), '<h1>колега</h1>')
            return {'found': True, 'last_commit': {'author': 'Peer', 'time': 1}}
        v = self.mod(serve._vcs_legacy_ctx(), repo, push=lambda ctx, t, d, m: {'ok': True, 'synced': True, 'changed': True,
                                                                                'pushed': True, 'sha': 'abc1234'}, pull=pull)
        self.write_it1('<h1>v11</h1>')
        auto = serve.autosync('t1', self.task, gl, vcs=v)
        self.assertEqual((auto['synced'], auto['remote']), (True, 'https://***@github.com/o/r.git:mockup/t1'))
        self.leak_free(auto, secrets)
        self.leak_free(serve.gitlab_pull(self.task, gl, vcs=v), secrets)

    def test_the_autosync_masks_the_address_in_a_plain_oserror_too(self):
        """Не `VcsError` (той маскує сам при створенні), а будь-який `OSError` нижче по стеку з адресою в тексті."""
        self.write_it1('<h1>v12</h1>')
        with mock.patch.object(serve, 'gitlab_sync', side_effect=OSError(f'push to https://{TOKEN}@github.com/o/r.git failed')):
            r = serve.autosync('t1', self.task, self.gl)
        self.assertEqual((r['reason'], r['error']), ('offline', 'push to https://***@github.com/o/r.git failed'))
        self.assertNotIn('code', r)
        self.leak_free(r, (TOKEN,))

    def test_the_autosync_masks_the_address_before_it_cuts_the_text(self):
        """Ревʼю c191cfb (Minor 2): `[:300]` ПІСЛЯ маски. Адреса, що стартує за 15 символів до межі, інакше лишила б у відповіді
        Stop-хука `https://ghp_SEC` без `@`."""
        self.write_it1('<h1>v13</h1>')
        text = 'a' * 285 + f'https://{TOKEN}@github.com/o/r.git'
        with mock.patch.object(serve, 'gitlab_sync', side_effect=OSError(text)):
            r = serve.autosync('t1', self.task, self.gl)
        self.assertEqual(r['reason'], 'offline')
        self.assertEqual(r['error'], ('a' * 285 + 'https://***@github.com/o/r.git')[:300])
        self.assertNotIn('ghp_SE', json.dumps(r))

    def test_a_returned_error_of_a_foreign_module_is_masked_in_status_push_and_pull(self):
        """Поправка 10: чужий модуль не кидає, а ПОВЕРТАЄ `{ok: false, error: <текст із адресою>}`: рядковий `error` результату
        `status`/`push`/`pull` ядро маскує саме на виклику (`_vcs_call`), а не лише відмови, що летять винятком."""
        repo, secrets = SECRET_REPOS['token']
        leak = f'push to {repo} denied'
        want = 'push to https://***@github.com/o/r.git denied'
        v = self.mod(serve._vcs_legacy_ctx(), repo,
                     status=lambda ctx, t: {'error': leak}, push=lambda ctx, t, d, m: {'ok': False, 'error': leak},
                     pull=lambda ctx, t, d, o=None: {'found': False, 'error': leak})
        self.assertEqual(serve._vcs_call(v, 'status', self.gl)['error'], want)
        self.assertEqual(serve._vcs_call(v, 'push', self.gl, self.tmp, {})['error'], want)
        self.assertEqual(serve._vcs_call(v, 'pull', self.gl, self.tmp)['error'], want)
        self.assertEqual(serve._vcs_call(v, 'status', self.gl, timeout=5)['error'], want)
        # не рядок і відсутній `error` лишаються як є
        w = self.mod(serve._vcs_legacy_ctx(), repo, status=lambda ctx, t: {'error': 5}, push=lambda ctx, t, d, m: {'ok': True})
        self.assertEqual(serve._vcs_call(w, 'status', self.gl), {'error': 5})
        self.assertEqual(serve._vcs_call(w, 'push', self.gl, self.tmp, {}), {'ok': True})

    def test_every_top_level_string_of_a_foreign_result_is_masked_not_only_the_error(self):
        """Ревʼю Task 5 (M9): `gitlab_sync` віддає `{**r, 'remote'}`, тож `hint`/`message` свого модуля йшли назовні як є."""
        repo, secrets = SECRET_REPOS['token']
        text = f'try {repo} again'
        want = 'try https://***@github.com/o/r.git again'
        leaky = {'hint': text, 'message': text, 'sha': 'abc1234', 'n': 5, 'ok': True, 'none': None}
        v = self.mod(serve._vcs_legacy_ctx(), repo, status=lambda ctx, t: dict(leaky),
                     push=lambda ctx, t, d, m: dict(leaky), pull=lambda ctx, t, d, o=None: dict(leaky))
        for fn, args in (('status', (self.gl,)), ('push', (self.gl, self.tmp, {})), ('pull', (self.gl, self.tmp))):
            with self.subTest(fn=fn):
                r = serve._vcs_call(v, fn, *args)
                self.assertEqual((r['hint'], r['message']), (want, want))
                self.assertEqual((r['sha'], r['n'], r['ok'], r['none']), ('abc1234', 5, True, None), 'чужі значення зачеплено')
                self.leak_free(r, secrets)

    def test_a_returned_error_of_a_foreign_module_does_not_reach_the_sync_result_nor_the_autosync(self):
        repo, secrets = SECRET_REPOS['token']
        gl = {**self.gl, 'repo': repo}
        v = self.mod(serve._vcs_legacy_ctx(), repo,
                     push=lambda ctx, t, d, m: {'ok': False, 'synced': False, 'error': f'push to {repo} denied'})
        r = serve.gitlab_sync('t1', self.task, gl, 'it1', vcs=v)
        self.assertEqual((r['ok'], r['error']), (False, 'push to https://***@github.com/o/r.git denied'))
        self.leak_free(r, secrets)
        self.write_it1('<h1>повернена помилка</h1>')
        auto = serve.autosync('t1', self.task, gl, vcs=v)
        self.assertEqual(auto['error'], 'push to https://***@github.com/o/r.git denied')
        self.leak_free(auto, secrets)

    def test_the_real_module_refuses_a_password_in_the_address_without_echoing_it(self):
        """Справжній модуль, без мережі: `validate` відхиляє `user:pass` до будь-якого git, і текст не несе адреси."""
        for name in ('user:pass', 'password with @'):
            repo, secrets = SECRET_REPOS[name]
            gl = {**self.gl, 'repo': repo}
            with self.subTest(repo=name):
                st = serve.gitlab_status(self.task, gl, self.meta(), 'it1')
                self.assertEqual((st['configured'], st['code']), (True, 'vcs-bad-target'))
                self.leak_free(st, secrets)
                with self.assertRaises(serve.VcsError) as cm:
                    serve.gitlab_sync('t1', self.task, gl, 'it1')
                self.assertEqual(cm.exception.code, 'vcs-bad-target')
                self.leak_free(str(cm.exception), secrets)
                self.write_it1(f'<h1>{name}</h1>')
                auto = serve.autosync('t1', self.task, gl)
                self.assertEqual((auto['reason'], auto['code']), ('offline', 'vcs-bad-target'))
                self.leak_free(auto, secrets)

    def handler(self, **attrs):
        """Обробник маршруту без сервера: лише те, що читають `_gitlab_*`/`_autosync`."""
        from types import SimpleNamespace
        sent = []
        task = {**self.task, 'gitlab': dict(self.gl)}
        h = SimpleNamespace(path='/api/gitlab-status?it=it1', _current_task=lambda: ('t1', task), _send_json=sent.append,
                            _task_override=None,        # `_autosync` дивиться, чи запит назвав задачу (режим «за шляхом»)
                            send_error=lambda *a: sent.append(a), _overview_sync=lambda: None, **attrs)
        h._vcs_ctx = lambda: serve.Handler._vcs_ctx(h)         # справжній метод: постачальник і ціль — як на сервері
        return h, sent

    def test_the_old_routes_mask_the_address_of_a_plain_exception_too(self):
        """Маршрути друкують `str(e)` будь-якого `OSError`, не лише `VcsError`: адреса з токеном у чужому тексті (git у стек-
        трейсі, чужий модуль) теж маскується."""
        msg = f'clone of https://{TOKEN}@github.com/o/r.git failed'
        boom = mock.patch.object(serve, 'load_tasks', return_value={})
        boom.start()
        self.addCleanup(boom.stop)
        for route, fn, args in (('_gitlab_status', 'gitlab_status', ()), ('_gitlab_sync', 'gitlab_sync', ({'it': 'it1'},)),
                                ('_autosync', 'autosync', ({},)), ('_gitlab_pull', 'gitlab_pull', ({},))):
            with self.subTest(route=route):
                h, sent = self.handler()
                with mock.patch.object(serve, fn, side_effect=OSError(msg)):
                    getattr(serve.Handler, route)(h, *args)
                self.assertEqual(len(sent), 1, sent)
                self.assertEqual(sent[0]['error'], 'clone of https://***@github.com/o/r.git failed')
                self.assertNotIn(TOKEN, json.dumps(sent))


# ======================================================================== ключ і IP з запису ЛІГИ (4d-4b)
class LeagueKeyFromTheRecord(unittest.TestCase):
    """ПОЗИТИВ до негативів «кореня нема»: ключ і IP, що міграція перенесла в запис `git-sync`, ДІЙСНО доходять до модуля. Стенд — явний запис
    ЛІГИ (`LigaFixture`, неізольований прогін) із справжнім файлом ключа в тимчасовому домі (`key_file=True`)."""

    def setUp(self):
        self.fx = LigaFixture(self).env().build(roles=('vcs',), key_file=True).fix_space()

    def test_the_key_and_ip_of_the_record_resolve_for_a_target_that_carries_none(self):
        v = serve.vcs_task('t1', {'gitlab': {'repo': 'git@h:o/r.git', 'path': 'mockup/t1'}})
        self.assertNotIn('ssh_key', v[3])
        self.assertNotIn('host_ip', v[3])
        got = serve._vcs_call(v, 'validate', v[3], timeout=5)            # справжній `validate` `git-sync`: ключ мусить існувати
        self.assertEqual((got['ssh_key'], got['host_ip']), (os.path.expanduser('~/.ssh/id_example'), '203.0.113.7'))
        self.assertTrue(os.path.isfile(got['ssh_key']) and got['ssh_key'].startswith(self.fx.home + os.sep))

    def test_the_own_key_of_the_task_still_beats_the_record(self):
        own = os.path.join(self.fx.home, 'own_key')
        write(own, 'x\n')
        v = serve.vcs_task('t1', {'gitlab': {'repo': 'git@h:o/r.git', 'path': 'mockup/t1', 'ssh_key': own}})
        self.assertEqual(serve._vcs_call(v, 'validate', v[3], timeout=5)['ssh_key'], own)


# ======================================================================== кривий результат модуля
class ModuleShape(Core):
    """Свій модуль ролі `vcs` (довіра 3c) може віддати не обʼєкт чи обʼєкт без ключів: це `VcsError('module-error')` або
    безпечне значення, але не `AttributeError`/`TypeError`/`KeyError` (маршрути ловлять лише `OSError`)."""
    BAD = (None, 'x', [], 5, True)

    def v(self, **fns):
        return (self.stub(**fns), serve._vcs_legacy_ctx(), False)

    def cfg(self):
        return {'tasks': {}, 'design_work_root': os.path.join(self.tmp, 'dw'), 'gitlab': {}}

    def test_a_status_that_is_not_an_object_is_an_error_status_with_the_frame_code(self):
        for bad in self.BAD:
            with self.subTest(result=bad):
                st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1', vcs=self.v(status=lambda ctx, t, b=bad: b))
                self.assertEqual((st['configured'], st['code']), (True, 'module-error'))
                self.assertIn('status returned', st['error'])

    def test_a_push_that_is_not_an_object_is_a_vcs_error_and_autosync_stays_quiet(self):
        before = json.dumps(self.meta().get('gitlab'), sort_keys=True)
        for bad in self.BAD:
            v = self.v(push=lambda ctx, t, d, m, b=bad: b)
            with self.subTest(result=bad):
                with self.assertRaises(serve.VcsError) as cm:
                    serve.gitlab_sync('t1', self.task, self.gl, 'it1', vcs=v)
                self.assertEqual(cm.exception.code, 'module-error')
                self.write_it1(f'<h1>{bad!r}</h1>')
                r = serve.autosync('t1', self.task, self.gl, vcs=v)
                self.assertEqual((r['reason'], r['code'], r['synced']), ('offline', 'module-error', False))
                self.assertEqual(json.dumps(self.meta().get('gitlab'), sort_keys=True), before)
        self.assertEqual(os.listdir(self.systmp), [], 'тека src лишилась після відмови')

    def test_a_pull_that_is_not_an_object_is_a_vcs_error(self):
        for bad in self.BAD:
            with self.subTest(result=bad):
                with self.assertRaises(serve.VcsError) as cm:
                    serve.gitlab_pull(self.task, self.gl, vcs=self.v(pull=lambda ctx, t, d, o=None, b=bad: b))
                self.assertEqual(cm.exception.code, 'module-error')
        self.assertEqual(os.listdir(self.systmp), [])

    def test_a_mirror_dir_that_is_not_a_string_is_a_vcs_error(self):
        v = self.v(mirror_dir=lambda ctx, t: 5)
        with self.assertRaises(serve.VcsError) as cm:
            serve.vcs_mirror_dir(self.gl, vcs=v)
        self.assertEqual(cm.exception.code, 'module-error')

    def test_a_validate_that_is_not_an_object_is_a_vcs_error(self):
        """`validate` кличе маршрут через `_vcs_call` (з короткою межею): тут форма результату стереже так само."""
        for bad in self.BAD:
            with self.subTest(result=bad):
                with self.assertRaises(serve.VcsError) as cm:
                    serve._vcs_call(self.v(validate=lambda ctx, t, b=bad: b), 'validate', self.gl, timeout=5)
                self.assertEqual(cm.exception.code, 'module-error')

    def test_a_result_that_json_cannot_carry_is_a_module_error_not_a_dropped_connection(self):
        """Свій модуль може віддати dict із `set`/`bytes`: `_send_json` кинув би `TypeError` ПОЗА `try` маршруту — обірване
        зʼєднання, а для автосинку це 5xx Stop-хуку. Тут вона стає `module-error`, як і криву форму результату."""
        calls = {'status': (), 'push': ('/tmp/src', {}), 'pull': ('/tmp/dst', {}), 'validate': ()}
        for bad in ({'ok': True, 'x': {1, 2}}, {'ok': True, 'x': b'bytes'}, {'ok': True, 'x': object()},
                    {'ok': True, 'nested': {'k': [1, {2}]}}, {'ok': True, (1, 2): 'tuple key'}):
            for fn, extra in calls.items():
                with self.subTest(fn=fn, bad=repr(bad)[:40]):
                    v = self.v(**{fn: (lambda *a, b=bad: b)})
                    with self.assertRaises(serve.VcsError) as cm:
                        serve._vcs_call(v, fn, self.gl, *extra)
                    self.assertEqual(cm.exception.code, 'module-error')
                    self.assertIn(fn, str(cm.exception))

    def test_a_serializable_result_passes_through_unchanged(self):
        r = {'ok': True, 'n': 1, 'nested': {'k': [1, None, 'x']}, 'f': 1.5}
        self.assertEqual(serve._vcs_call(self.v(status=lambda ctx, t: dict(r)), 'status', self.gl), r)

    def test_a_function_without_a_declared_shape_is_passed_through_as_it_is(self):
        """`web_url` законно віддає `None`: форму ядро вимагає лише там, де знає її (status/push/pull/validate/mirror_dir)."""
        self.assertIsNone(serve._vcs_call(self.v(web_url=lambda ctx, t: None), 'web_url', self.gl))

    def test_objects_without_the_expected_keys_do_not_crash_the_core(self):
        st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1', vcs=self.v(status=lambda ctx, t: {}))
        self.assertEqual((st['configured'], st['behind'], st['behind_path'], st['unpushed'], st['on_remote'], st['label']),
                         (True, 0, 0, 0, None, 'Git'))
        self.assertIsNone(st['web'])
        st = serve.gitlab_status(self.task, self.gl, self.meta(), 'it1',
                                 vcs=self.v(status=lambda ctx, t: {'web': 5, 'label': ['x']}))
        self.assertEqual((st['web'], st['label']), (None, 'Git'))
        r = serve.gitlab_sync('t1', self.task, self.gl, 'it1', vcs=self.v(push=lambda ctx, t, d, m: {}))
        self.assertEqual(r, {'remote': f'{self.origin}:mockup/t1'})
        r = serve.autosync('t1', self.task, self.gl, vcs=self.v(push=lambda ctx, t, d, m: {}))
        self.assertEqual((r['it'], r.get('synced')), ('it1', None))
        with self.assertRaises(OSError) as cm:
            serve.gitlab_pull(self.task, self.gl, vcs=self.v(pull=lambda ctx, t, d, o=None: {}))
        self.assertIn('not found in repo', str(cm.exception))

    # ---- last_commit
    def pulling(self, last_commit):
        def pull(ctx, t, d, o=None):
            write(os.path.join(d, 'index.html'), '<h1>з репо</h1>')
            return {'found': True, 'last_commit': last_commit}
        return self.v(pull=pull)

    def test_last_commit_helper_keeps_only_a_well_formed_value(self):
        for lc, want in ((None, {}), ('x', {}), (5, {}), (['a'], {}), ({}, {'author': '', 'time': None}),
                         ({'author': 5, 'time': 'x'}, {'author': '', 'time': None}),
                         ({'author': 'Peer', 'time': True}, {'author': 'Peer', 'time': None}),
                         ({'author': 'Peer', 'time': 1700000000}, {'author': 'Peer', 'time': 1700000000}),
                         ({'author': 'Peer', 'time': 1.5}, {'author': 'Peer', 'time': 1.5})):
            with self.subTest(last_commit=lc):
                self.assertEqual(serve._last_commit({'last_commit': lc}), want)
        self.assertEqual(serve._last_commit({}), {})

    def test_a_malformed_last_commit_is_the_same_as_a_missing_one(self):
        for lc in ('x', 5, ['a'], {'author': 5, 'time': 'x'}, {'author': 'Peer', 'time': True}):
            with self.subTest(last_commit=lc):
                self.save_meta({'iterations': [{'id': 'it1'}], 'current': 'it1'})
                r = serve.gitlab_pull(self.task, self.gl, vcs=self.pulling(lc))
                self.assertTrue(r['ok'], r)
                self.assertIsNone(r['fork'], 'без числового `time` застарілість не перевіряється')
                self.assertIsInstance(r['iteration'].get('author', ''), str)

    def test_a_well_formed_old_time_still_forks_the_own_newer_work(self):
        """Контроль до попереднього: коректний `time` старіший за мою роботу — форк, тобто перевірка застарілості жива."""
        r = serve.gitlab_pull(self.task, self.gl, vcs=self.pulling({'author': 'Peer', 'time': 1}))
        self.assertEqual((r['ok'], r['continue_from']), (True, 'it1'))
        self.assertIsNotNone(r['fork'])

    # ---- found
    def finding(self, found, files=('index.html',)):
        """`pull` свого модуля: кладе `files` у `dst` і каже `found` (будь-яке значення)."""
        def pull(ctx, t, d, o=None):
            for name in files:
                write(os.path.join(d, name), '<h1>з репо</h1>')
            return {'found': found, 'last_commit': {'author': 'Peer', 'time': 1}}
        return self.v(pull=pull)

    def test_found_must_be_exactly_true_for_a_pull_to_make_an_iteration(self):
        """Поправка 11: `{'found': 'no'}` (будь-що правдиве, крім `True`) раніше давало нову ітерацію з чужої `dst`."""
        for bad in ('no', 'false', 1, 2, [1], {'a': 1}):
            with self.subTest(found=bad):
                before = json.dumps(self.meta(), sort_keys=True)
                with self.assertRaises(OSError) as cm:
                    serve.gitlab_pull(self.task, self.gl, vcs=self.finding(bad))
                self.assertIn('not found in repo', str(cm.exception))
                self.assertEqual(json.dumps(self.meta(), sort_keys=True), before, 'зʼявилась ітерація')
        self.assertEqual(sorted(os.listdir(os.path.join(self.task_dir, 'iterations'))), ['it1'])

    def test_found_true_with_an_empty_dst_is_not_found(self):
        """Поправка 11: `found: True`, а `dst` порожня, — порожня нова ітерація. Це «не знайдено»."""
        before = json.dumps(self.meta(), sort_keys=True)
        with self.assertRaises(OSError) as cm:
            serve.gitlab_pull(self.task, self.gl, vcs=self.finding(True, files=()))
        self.assertIn('not found in repo', str(cm.exception))
        self.assertEqual(json.dumps(self.meta(), sort_keys=True), before)
        self.assertEqual(sorted(os.listdir(os.path.join(self.task_dir, 'iterations'))), ['it1'])
        self.assertEqual(os.listdir(self.systmp), [])

    def test_found_true_with_files_still_makes_the_iteration(self):
        r = serve.gitlab_pull(self.task, self.gl, vcs=self.finding(True))
        self.assertEqual((r['ok'], r['iteration']['id']), (True, 'it2'))

    def test_task_new_takes_a_found_that_is_not_true_as_a_missing_path(self):
        for i, bad in enumerate(('no', 1, [1])):
            with self.subTest(found=bad):
                with mock.patch.object(serve, 'vcs_provider', return_value=self.finding(bad)):
                    r = serve.task_new(self.cfg(), f'f{i}', title='Нова', vcs={'repo': self.origin})
                self.assertFalse(r['cloned'], 'found не True, а макет склонувався')
        with mock.patch.object(serve, 'vcs_provider', return_value=self.finding(True)):
            r = serve.task_new(self.cfg(), 'f9', title='Нова', vcs={'repo': self.origin})
        self.assertTrue(r['cloned'], 'контроль: found True із index.html клонується')

    # ---- task_new
    def test_task_new_takes_a_pull_that_is_not_an_object_as_an_unavailable_mirror(self):
        for i, bad in enumerate(self.BAD):
            with self.subTest(result=bad):
                v = self.v(pull=lambda ctx, t, d, o=None, b=bad: b)
                with mock.patch.object(serve, 'vcs_provider', return_value=v):
                    r = serve.task_new(self.cfg(), f'n{i}', title='Нова', vcs={'repo': self.origin})
                self.assertFalse(r['cloned'])
                self.assertTrue(os.path.isfile(os.path.join(r['dir'], 'iterations', 'it1', 'index.html')))
        self.assertEqual(os.listdir(self.systmp), [])

    def test_task_new_ignores_a_malformed_last_commit(self):
        with mock.patch.object(serve, 'vcs_provider', return_value=self.pulling('x')):
            r = serve.task_new(self.cfg(), 'nova', title='Нова', vcs={'repo': self.origin})
        self.assertTrue(r['cloned'])
        with open(os.path.join(r['dir'], 'iterations', 'it1', 'index.html'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '<h1>з репо</h1>')


# ======================================================================== маршрути /api/vcs-* (Task 5)
class Http(Core):
    """Маршрути на справжньому сервері в процесі. Два простори: ЛІГА (`a`: `gitlab{repo, path}`, неявний `'legacy'`) і звичайний
    (`p`: `git-sync`, ціль — із налаштувань модуля, автосинк за замовчуванням вимкнений). Простір запиту — заголовок
    `X-Canvas-Task`. Git — на локальному bare-репо, мережі нема."""
    PLAIN = True

    def setUp(self):
        super().setUp()
        self.liga = self.make_space('Liga', integrations=True, enable=False)
        # 4d-4b: ЛІГА веде ЯВНИЙ запис `git-sync` (`compat = design-canvas`, автосинк увімкнено — як у неявного постачальника), без `repo`
        dm.write_module_state(self.liga, 'git-sync', enabled=True,
                              settings={'branch': 'main', 'path': 'mockup/{task}', 'autosync': True, 'compat': 'design-canvas'})
        self.a_dir = self.mk_task('a', '<h1>a1</h1>')
        self.liga_root = os.path.join(self.tmp, 'liga-root')
        self.liga_tasks = os.path.join(self.liga['path'], 'tasks.json')
        write(self.liga_tasks, json.dumps(
            {'current': 'a', 'design_work_root': self.liga_root,
             'tasks': {'a': {'dir': self.a_dir, 'title': 'Альфа', 'profile': 'tool',
                             'gitlab': {'repo': self.origin, 'path': 'mockup/a'}}}}))
        self.plain = self.make_space('Plain')
        self.p_dir = self.mk_task('p', '<h1>p1</h1>')
        self.plain_tasks = os.path.join(self.plain['path'], 'tasks.json')
        write(self.plain_tasks, json.dumps(
            {'current': 'p', 'tasks': {'p': {'dir': self.p_dir, 'title': 'Пе', 'profile': None}}}))
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.base = f'http://127.0.0.1:{httpd.server_address[1]}'

    # ---- хелпери
    def mk_task(self, tid, html):
        d = os.path.join(self.tmp, 'tasks', tid)
        write(os.path.join(d, 'iterations', 'it1', 'index.html'), html)
        write(os.path.join(d, 'iterations.json'), json.dumps({'iterations': [{'id': 'it1'}], 'current': 'it1'}))
        return d

    def call(self, method, path, payload=None, task=None):
        """`(статус, JSON або текст)`: `send_error` віддає HTML, решта — JSON."""
        headers = {'Content-Type': 'application/json'}
        if task:
            headers['X-Canvas-Task'] = task
        data = None if payload is None else json.dumps(payload).encode()
        rq = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(rq, timeout=60) as r:
                st, body = r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            st, body = e.code, e.read().decode('utf-8')
        try:
            return st, json.loads(body)
        except ValueError:
            return st, body

    def get(self, path, task=None):
        return self.call('GET', path, None, task)

    def post(self, path, payload=None, task=None):
        return self.call('POST', path, {} if payload is None else payload, task)

    @contextlib.contextmanager
    def server_log(self):
        """Stderr сервера: він у цьому ж процесі, а `_autosync` пише traceback збою в лог. Тест його або читає, або глушить, щоб не
        засмічувати вивід прогону (для тихих причин лог лишається порожнім)."""
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            yield buf

    def heads(self):
        return self.out(self.origin, 'rev-parse', 'main')

    def log1(self):
        return self.out(self.origin, 'log', '-1', '--format=%s')

    def break_space_json(self):
        write(os.path.join(self.plain['path'], 'space.json'), '{')

    def bare_space(self, name='Bare'):
        """Простір БЕЗ ролі `vcs` і його задача `b`."""
        sp = self.make_space(name, enable=False)
        d = self.mk_task('b', '<h1>b1</h1>')
        write(os.path.join(sp['path'], 'tasks.json'),
              json.dumps({'current': 'b', 'tasks': {'b': {'dir': d, 'title': 'Бе', 'profile': None}}}))
        return sp

    # ---------------------------------------------------------------- статус
    def test_the_status_aliases_answer_the_same_json_in_both_spaces(self):
        for tid, label in (('a', 'GitLab'), ('p', 'Git')):
            with self.subTest(task=tid, stage='до відправки'):
                (so, old), (sn, new) = (self.get('/api/gitlab-status?it=it1', tid), self.get('/api/vcs-status?it=it1', tid))
                self.assertEqual((so, sn), (200, 200))
                self.assertEqual(old, new)
                self.assertEqual((new['configured'], new['label'], new['dirty'], new['on_remote'], new['remote_path']),
                                 (True, label, True, False, f'mockup/{tid}'))
            with self.subTest(task=tid, stage='після відправки'):
                st, sent = self.post('/api/vcs-push', {'it': 'it1'}, tid)
                self.assertEqual((st, sent['synced']), (200, True), sent)
                (so, old), (sn, new) = (self.get('/api/gitlab-status?it=it1', tid), self.get('/api/vcs-status?it=it1', tid))
                self.assertEqual(old, new)
                self.assertEqual((new['dirty'], new['on_remote'], new['synced_it']), (False, True, 'it1'))

    def test_the_status_of_a_space_without_the_role_is_not_configured(self):
        self.bare_space()
        for path in ('/api/gitlab-status?it=it1', '/api/vcs-status?it=it1'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path, 'b'), (200, {'configured': False}))

    def test_the_status_of_a_space_with_a_task_that_has_no_target_is_not_configured(self):
        dm.write_module_state(self.plain, 'git-sync', settings={'repo': None})
        for path in ('/api/gitlab-status?it=it1', '/api/vcs-status?it=it1'):
            self.assertEqual(self.get(path, 'p'), (200, {'configured': False}))

    def test_an_unreadable_space_json_is_a_status_without_a_config_and_with_the_code(self):
        """Поправка 5: опит статусу йде на кожному старті, тож не 409 і не `configured: true`. Форма спеки —
        `{configured: false, code}`; `gitlab_status(vcs=None)` у цьому разі віддав би `configured: true` із `error`."""
        self.break_space_json()
        for path in ('/api/gitlab-status?it=it1', '/api/vcs-status?it=it1'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path, 'p'), (200, {'configured': False, 'code': 'space-json-unreadable'}))

    def test_a_broken_catalog_in_the_liga_space_is_a_status_without_a_config_and_with_the_code(self):
        with mock.patch.object(dm, 'catalog', side_effect=RuntimeError('boom')):
            for path in ('/api/gitlab-status?it=it1', '/api/vcs-status?it=it1'):
                self.assertEqual(self.get(path, 'a'), (200, {'configured': False, 'code': 'vcs-error'}))

    def test_a_hidden_origin_is_a_status_with_an_error_and_a_code(self):
        self.hide()
        for tid in ('a', 'p'):
            for path in ('/api/gitlab-status?it=it1', '/api/vcs-status?it=it1'):
                with self.subTest(task=tid, path=path):
                    st, body = self.get(path, tid)
                    self.assertEqual((st, body['configured']), (200, True))
                    self.assertTrue(body['error'])
                    self.assertIn(body['code'], ('vcs-error', 'vcs-offline'))

    # ---------------------------------------------------------------- відправка
    def test_both_push_addresses_send_the_iteration_in_both_spaces(self):
        n = 0
        for path in ('/api/gitlab-sync', '/api/vcs-push'):
            for tid, subject, mp, d in (('a', 'design-canvas: sync mockup/a (Альфа) · it1', 'mockup/a', self.a_dir),
                                        ('p', 'deai: sync mockup/p (Пе) · it1', 'mockup/p', self.p_dir)):
                n += 1
                with self.subTest(path=path, task=tid):
                    write(os.path.join(d, 'iterations', 'it1', 'index.html'), f'<h1>правка {n}</h1>')
                    st, body = self.post(path, {'it': 'it1'}, tid)
                    self.assertEqual((st, body['ok'], body['synced'], body['changed']), (200, True, True, True), body)
                    self.assertEqual(body['remote'], f'{self.origin}:{mp}')
                    self.assertEqual(self.log1(), subject)
                    with open(os.path.join(d, 'iterations.json'), encoding='utf-8') as fh:
                        self.assertEqual(json.load(fh)['gitlab']['synced_it'], 'it1', 'відбиток не записано')

    def test_a_push_without_a_target_is_400_with_the_old_text(self):
        """Без ролі, з роллю без цілі, ЛІГА без `gitlab{}` — один і той самий 400, на ньому стоять тести й клієнт."""
        self.bare_space()
        write(os.path.join(self.liga['path'], 'tasks.json'), json.dumps(
            {'current': 'a2', 'tasks': {'a2': {'dir': self.mk_task('a2', '<h1>a2</h1>'), 'title': 'Альфа 2', 'profile': 'tool'}}}))
        for path in ('/api/gitlab-sync', '/api/vcs-push'):
            for tid, what in (('b', 'без ролі'), ('a2', 'ЛІГА без gitlab')):
                with self.subTest(path=path, what=what):
                    st, body = self.post(path, {'it': 'it1'}, tid)
                    self.assertEqual(st, 400)
                    self.assertIn('no gitlab configured', body)
        dm.write_module_state(self.plain, 'git-sync', settings={'repo': None})
        for path in ('/api/gitlab-sync', '/api/vcs-push'):
            with self.subTest(path=path, what='роль без цілі'):
                st, body = self.post(path, {'it': 'it1'}, 'p')
                self.assertEqual(st, 400)
                self.assertIn('no gitlab configured', body)
        self.assertEqual(self.out(self.origin, 'log', '--format=%s', '-1'), 'seed', 'щось відправилось')

    def test_a_push_of_a_bad_iteration_name_is_400(self):
        for tid in ('a', 'p'):
            st, body = self.post('/api/vcs-push', {'it': '../x'}, tid)
            self.assertEqual(st, 400)
            self.assertIn('bad iteration', body)

    def test_a_push_to_a_hidden_origin_is_200_not_ok_with_an_error_and_a_code(self):
        self.hide()
        for path in ('/api/gitlab-sync', '/api/vcs-push'):
            for tid in ('a', 'p'):
                with self.subTest(path=path, task=tid):
                    st, body = self.post(path, {'it': 'it1'}, tid)
                    self.assertEqual((st, body['ok']), (200, False), body)
                    self.assertTrue(body['error'])
                    self.assertIn(body['code'], ('vcs-error', 'vcs-offline'))

    def test_a_refusing_provider_is_a_failed_push_and_pull_with_the_frame_code(self):
        self.break_space_json()
        for path, payload in (('/api/gitlab-sync', {'it': 'it1'}), ('/api/vcs-push', {'it': 'it1'}),
                              ('/api/gitlab-pull', {}), ('/api/vcs-pull', {})):
            with self.subTest(path=path):
                st, body = self.post(path, payload, 'p')
                self.assertEqual((st, body['ok'], body['code']), (200, False, 'space-json-unreadable'), body)
                self.assertTrue(body['error'])

    def test_a_repo_with_spaces_in_a_liga_task_still_goes_through_the_old_routes(self):
        """Поправка 6: старі маршрути йдуть через `vcs_task`, а не `gitlab_cfg`: адреса з пробілами не дає `vcs-bad-target`."""
        write(os.path.join(self.liga['path'], 'tasks.json'), json.dumps(
            {'current': 'a', 'tasks': {'a': {'dir': self.a_dir, 'title': 'Альфа', 'profile': 'tool',
                                             'gitlab': {'repo': f'  {self.origin}\n', 'path': 'mockup/a'}}}}))
        st, body = self.get('/api/gitlab-status?it=it1', 'a')
        self.assertEqual((st, body['configured']), (200, True))
        self.assertNotIn('error', body, body)
        st, body = self.post('/api/gitlab-sync', {'it': 'it1'}, 'a')
        self.assertEqual((st, body['ok'], body['synced']), (200, True, True), body)
        self.assertEqual(body['remote'], f'{self.origin}:mockup/a')
        self.peer_push({'mockup/a/index.html': '<h1>колега</h1>'})
        st, body = self.post('/api/gitlab-pull', {}, 'a')
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(body['iteration']['note'], 'оновлення з GitLab')

    # ---------------------------------------------------------------- отримання
    def test_both_pull_addresses_bring_a_colleague_change_with_the_note_of_the_space(self):
        n = 0
        for tid, mp, note in (('a', 'mockup/a', 'оновлення з GitLab'), ('p', 'mockup/p', 'оновлення з репозиторію')):
            for path in ('/api/gitlab-pull', '/api/vcs-pull'):
                n += 1
                with self.subTest(path=path, task=tid):
                    self.peer_push({f'{mp}/index.html': f'<h1>колега {n}</h1>'})
                    st, body = self.post(path, {}, tid)
                    self.assertEqual((st, body['ok']), (200, True), body)
                    self.assertEqual(body['iteration']['note'], note)
        self.assertEqual(os.listdir(self.systmp), [])

    def test_a_pull_without_a_target_is_400_with_the_old_text(self):
        self.bare_space()
        dm.write_module_state(self.plain, 'git-sync', settings={'repo': None})
        for path in ('/api/gitlab-pull', '/api/vcs-pull'):
            for tid in ('b', 'p'):
                with self.subTest(path=path, task=tid):
                    st, body = self.post(path, {}, tid)
                    self.assertEqual(st, 400)
                    self.assertIn('no gitlab configured', body)

    def test_a_pull_from_a_hidden_origin_is_200_not_ok_with_an_error_and_a_code(self):
        self.hide()
        for path in ('/api/gitlab-pull', '/api/vcs-pull'):
            for tid in ('a', 'p'):
                with self.subTest(path=path, task=tid):
                    st, body = self.post(path, {}, tid)
                    self.assertEqual((st, body['ok']), (200, False), body)
                    self.assertIn(body['code'], ('vcs-error', 'vcs-offline'))

    # ---------------------------------------------------------------- автосинк
    NO_GITLAB = {'ok': True, 'changed': False, 'reason': 'no-gitlab'}

    def no_ai(self, resp):
        """Відповідь `/api/autosync` без `ai` (фаза И: ключ є завжди — `None` або `{it, sha}`): решту звіряємо дослівно."""
        st, body = resp
        self.assertIn('ai', body)
        return st, {k: v for k, v in body.items() if k != 'ai'}

    def test_autosync_without_a_role_or_without_a_target_is_the_quiet_no_gitlab_verbatim(self):
        self.bare_space()
        self.assertEqual(self.no_ai(self.post('/api/autosync', {}, 'b')), (200, self.NO_GITLAB))
        dm.write_module_state(self.plain, 'git-sync', settings={'repo': None})
        self.assertEqual(self.no_ai(self.post('/api/autosync', {}, 'p')), (200, self.NO_GITLAB))

    def test_autosync_switched_off_in_the_module_does_nothing_and_says_so(self):
        """`git-sync` за замовчуванням має `autosync: false`: відповідь `autosync-off`, жодного коміту ні в origin, ні в теці задачі."""
        before = self.heads()
        write(os.path.join(self.p_dir, 'iterations', 'it1', 'index.html'), '<h1>брудна</h1>')
        # Фаза И: ключ `ai` є завжди; тека без `.git` (початковий імпорт) — не AI, тож локального коміту й тут нема.
        self.assertEqual(self.post('/api/autosync', {}, 'p'), (200, {'ok': True, 'changed': False, 'reason': 'autosync-off', 'ai': None}))
        self.assertEqual(self.heads(), before, 'вимкнений автосинк відправив')
        self.assertFalse(os.path.isdir(os.path.join(self.p_dir, '.git')), 'вимкнений автосинк зробив локальний коміт')
        self.assertNotIn('mockup/p/index.html', self.out(self.origin, 'ls-tree', '-r', '--name-only', 'main'))

    def test_autosync_switched_on_sends_a_change_once(self):
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        st, body = self.post('/api/autosync', {}, 'p')
        self.assertEqual((st, body['ok'], body['changed'], body['synced'], body['it']), (200, True, True, True, 'it1'), body)
        self.assertEqual(self.log1(), 'deai: sync mockup/p (Пе) · it1')
        self.assertEqual(self.post('/api/autosync', {}, 'p'), (200, {'ok': True, 'changed': False, 'reason': 'clean', 'it': 'it1', 'ai': None}))

    def test_autosync_of_the_liga_space_is_on_as_it_was(self):
        st, body = self.post('/api/autosync', {}, 'a')
        self.assertEqual((st, body['ok'], body['changed'], body['synced']), (200, True, True, True), body)
        self.assertEqual(self.log1(), 'design-canvas: sync mockup/a (Альфа) · it1')

    def test_autosync_with_a_hidden_origin_is_offline_with_a_code_and_never_5xx(self):
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        self.hide()
        for tid in ('a', 'p'):
            with self.subTest(task=tid):
                st, body = self.post('/api/autosync', {}, tid)
                self.assertEqual(st, 200)
                self.assertEqual((body['ok'], body['reason'], body['synced'], body['changed']), (False, 'offline', False, False), body)
                self.assertIn(body['code'], ('vcs-error', 'vcs-offline'))

    def test_autosync_of_a_refusing_provider_is_the_quiet_no_gitlab_with_the_code(self):
        self.break_space_json()
        self.assertEqual(self.no_ai(self.post('/api/autosync', {}, 'p')), (200, {**self.NO_GITLAB, 'code': 'space-json-unreadable'}))
        with mock.patch.object(dm, 'catalog', side_effect=RuntimeError('boom')):
            self.assertEqual(self.no_ai(self.post('/api/autosync', {}, 'a')), (200, {**self.NO_GITLAB, 'code': 'vcs-error'}))

    # ---------------------------------------------------------------- тип `it` (ревʼю Task 5, I1)
    BAD_IT = (5, None, [], {}, True, 1.5, 'it1\n', '../x', 'a b', '')

    def test_an_iteration_that_is_not_a_clean_name_is_400_on_both_push_addresses(self):
        """`NAME_RE.match(5)` кидав TypeError, і зʼєднання рвалось без відповіді; `match` пропускав `it1\\n`. Тепер 400 `bad iteration`."""
        before = self.heads()
        for path in ('/api/gitlab-sync', '/api/vcs-push'):
            for tid in ('a', 'p'):
                for bad in self.BAD_IT:
                    with self.subTest(path=path, task=tid, it=bad):
                        st, body = self.post(path, {'it': bad}, tid)
                        self.assertEqual(st, 400)
                        self.assertIn('bad iteration', body)
                st, body = self.post(path, {}, tid)
                self.assertEqual((st, 'bad iteration' in body), (400, True), 'без it')
        self.assertEqual(self.heads(), before, 'щось відправилось')

    def test_a_status_with_a_path_instead_of_an_iteration_is_400_and_an_empty_one_still_answers(self):
        """`it` у query — завжди рядок, але йде в шлях (`_iter_dir`): `../..` хешував би чужу теку. Порожній — штатний (смуга без вибору)."""
        for path in ('/api/gitlab-status', '/api/vcs-status'):
            for tid in ('a', 'p'):
                for bad in ('..%2F..', 'it1%0A', 'a%20b', '..'):
                    with self.subTest(path=path, task=tid, it=bad):
                        st, body = self.get(f'{path}?it={bad}', tid)
                        self.assertEqual(st, 400)
                        self.assertIn('bad iteration', body)
                for good in ('it1', '', 'it-9'):
                    with self.subTest(path=path, task=tid, it=good):
                        st, body = self.get(f'{path}?it={good}', tid)
                        self.assertEqual((st, body['configured']), (200, True))
                st, body = self.get(path, tid)
                self.assertEqual((st, body['configured']), (200, True), 'без it')

    # ---------------------------------------------------------------- постачальник один раз (ревʼю Task 5, M5)
    def test_the_routes_resolve_the_provider_once_and_hand_the_triple_to_the_core(self):
        """Без `vcs=vcs[:3]` ядро резолвило б постачальника вдруге, а тести лишались би зеленими: той самий результат, лише вдвічі
        більше читань `space.json`. Шпигуни: `vcs_provider` — рівно один виклик на запит, ядро отримує готовий кортеж."""
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        real = {n: getattr(serve, n) for n in ('vcs_provider', 'gitlab_status', 'gitlab_sync', 'gitlab_pull', 'autosync')}
        seen = {'provider': 0, 'core': []}

        def provider():
            seen['provider'] += 1
            return real['vcs_provider']()

        def spy(name):
            def call(*a, **kw):
                seen['core'].append((name, kw.get('vcs')))
                return real[name](*a, **kw)
            return call
        n = 0
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(serve, 'vcs_provider', side_effect=provider))
            for name in ('gitlab_status', 'gitlab_sync', 'gitlab_pull', 'autosync'):
                stack.enter_context(mock.patch.object(serve, name, side_effect=spy(name)))
            for tid, legacy, mp, d in (('a', True, 'mockup/a', self.a_dir), ('p', False, 'mockup/p', self.p_dir)):
                for method, path, payload, names in (
                        ('GET', '/api/vcs-status?it=it1', None, ['gitlab_status']),
                        ('GET', '/api/gitlab-status?it=it1', None, ['gitlab_status']),
                        ('POST', '/api/vcs-push', {'it': 'it1'}, ['gitlab_sync']),
                        ('POST', '/api/gitlab-sync', {'it': 'it1'}, ['gitlab_sync']),
                        ('POST', '/api/vcs-pull', {}, ['gitlab_pull']),
                        ('POST', '/api/gitlab-pull', {}, ['gitlab_pull']),
                        ('POST', '/api/autosync', {}, ['autosync', 'gitlab_sync'])):
                    with self.subTest(task=tid, path=path):
                        n += 1
                        write(os.path.join(d, 'iterations', 'it1', 'index.html'), f'<h1>шпигун {n}</h1>')
                        self.peer_push({f'{mp}/index.html': f'<h1>колега {n}</h1>'})
                        seen['provider'], seen['core'] = 0, []
                        st, body = self.call(method, path, payload, tid)
                        self.assertEqual(st, 200, body)
                        self.assertEqual(seen['provider'], 1, 'постачальника резолвили вдруге')
                        self.assertEqual([c[0] for c in seen['core']], names)
                        for name, v in seen['core']:
                            self.assertIsInstance(v, tuple, f'{name} без готового постачальника')
                            self.assertEqual((len(v), v[2]), (3, legacy))

    # ---------------------------------------------------------------- автосинк ніколи не віддає 5xx (ревʼю Task 5, M8)
    def test_the_autosync_answers_200_with_a_reason_and_a_mask_for_any_failure(self):
        """Stop-хук не мусить отримувати 500: і не-`OSError` (`ValueError` з читання мети) теж 200 з `reason` і маскою.

        Ревʼю c191cfb (F1): «offline» хук мовчить, а `OSError`/`PermissionError`/`FileNotFoundError` НА РІВНІ МАРШРУТУ — це збій
        ЛОКАЛЬНИЙ (нечитабельні `iterations.json`, права на теку), а не відсутня мережа: незапушений макет тоді лежав би тихо.
        Тож `offline` — лише те, що ставить сам `autosync()` (його тут нема) і `VcsError`; решта — `error`, і хук кричить."""
        msg = f'broken iterations of https://{TOKEN}@github.com/o/r.git'
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        cases = ((ValueError(msg), 'error', None), (KeyError(msg), 'error', None), (TypeError(msg), 'error', None),
                 (OSError(msg), 'error', None), (subprocess.SubprocessError(msg), 'error', None),
                 (PermissionError(msg), 'error', None), (FileNotFoundError(msg), 'error', None),
                 (serve.VcsError('vcs-offline', msg), 'offline', 'vcs-offline'))
        for tid in ('a', 'p'):
            for exc, reason, code in cases:
                with self.subTest(task=tid, exc=type(exc).__name__):
                    with self.server_log(), mock.patch.object(serve, 'autosync', side_effect=exc):
                        st, body = self.post('/api/autosync', {}, tid)
                    self.assertEqual(st, 200, body)
                    self.assertEqual((body['ok'], body['synced'], body['changed'], body['reason']), (False, False, False, reason))
                    self.assertEqual(body.get('code'), code)
                    self.assertIn('https://***@github.com/o/r.git', body['error'])
                    self.assertNotIn(TOKEN, json.dumps(body))

    def test_a_local_failure_of_the_autosync_writes_a_masked_traceback_to_stderr(self):
        """Ревʼю c191cfb (Minor 1a): `reason: "error"` у відповіді — коротко, а ЩО зламалось, видно лише з traceback у stderr
        сервера (інакше `except Exception` ховає причину так само, як ховав би `pass`). Адреса з токеном — теж замаскована."""
        msg = f'broken iterations of https://{TOKEN}@github.com/o/r.git'
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        for tid in ('a', 'p'):
            with self.subTest(task=tid, kind='error'):
                with self.server_log() as err, mock.patch.object(serve, 'autosync', side_effect=ValueError(msg)):
                    st, body = self.post('/api/autosync', {}, tid)
                self.assertEqual((st, body['reason']), (200, 'error'), body)
                log = err.getvalue()
                self.assertIn('Traceback', log)
                self.assertIn('ValueError', log)
                self.assertIn('https://***@github.com/o/r.git', log)
                self.assertNotIn(TOKEN, log)
            with self.subTest(task=tid, kind='offline'):
                with self.server_log() as err, mock.patch.object(serve, 'autosync', side_effect=serve.VcsError('vcs-offline', msg)):
                    st, body = self.post('/api/autosync', {}, tid)
                self.assertEqual((st, body['reason']), (200, 'offline'), body)
                self.assertNotIn('Traceback', err.getvalue(), 'тиха причина лишається тихою')

    def test_the_central_states_of_the_space_are_not_swallowed_by_the_autosync(self):
        """Ревʼю c191cfb (Minor 1b): `NoTask`/`SpaceUnavailable`/`SpacesError`/`AmbiguousTask` — відповіді `_guarded` (404/503/409), як у
        кожного маршруту, а не 200 із `reason: "error"`: `SpaceUnavailable` — ще й `OSError` із `ValueError`, тож без явного `raise`
        перед `except Exception` його проковтнув би той самий рядок. `ModuleError` тут НЕ центральний: див. наступний тест."""
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        cases = ((spaces.NoTask('x'), 404, 'no-task'), (serve.SpaceUnavailable('/p/tasks.json'), 503, 'space-unavailable'),
                 (spaces.SpacesError('spaces-unreadable', '/p', 'bad'), 503, 'spaces-unreadable'),
                 (spaces.AmbiguousTask('a'), 409, 'ambiguous-task'))
        for tid in ('a', 'p'):
            for exc, status, code in cases:
                with self.subTest(task=tid, exc=type(exc).__name__):
                    with mock.patch.object(serve, 'autosync', side_effect=exc):
                        st, body = self.post('/api/autosync', {}, tid)
                    self.assertEqual((st, body['ok'], body['code']), (status, False, code), body)
                    self.assertNotIn('reason', body, 'це не відповідь автосинку')

    def test_a_module_error_at_the_route_is_a_quiet_200_offline_with_the_code_and_a_mask(self):
        """Ревʼю 7db6370 (1): `ModuleError` через `_guarded` дав би 502/504/500 без маски (`HTTPError` — і хук мовчить): порушення «хукові
        ніколи 5xx». Тож тут він — як `VcsError`: 200 `reason: "offline"` + `code`, адреса замаскована, traceback не пишемо (тиха причина)."""
        msg = f'module broke on https://{TOKEN}@github.com/o/r.git'
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        cases = (('module-error', 502), ('check-timeout', 504), ('vcs-error', 500), ('vcs-busy', None))
        for tid in ('a', 'p'):
            for code, status in cases:
                with self.subTest(task=tid, code=code):
                    exc = dm.ModuleError(code, status, msg) if status else dm.ModuleError(code, message=msg)
                    with self.server_log() as err, mock.patch.object(serve, 'autosync', side_effect=exc):
                        st, body = self.post('/api/autosync', {}, tid)
                    self.assertEqual(st, 200, body)
                    self.assertEqual((body['ok'], body['synced'], body['changed'], body['reason'], body['code']),
                                     (False, False, False, 'offline', code))
                    self.assertIn('https://***@github.com/o/r.git', body['error'])
                    self.assertNotIn(TOKEN, json.dumps(body))
                    self.assertNotIn('Traceback', err.getvalue(), 'тиха причина лишається тихою')

    def test_a_real_value_error_of_the_task_state_is_still_a_200_for_the_stop_hook(self):
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        write(os.path.join(self.p_dir, 'iterations.json'), '{')
        with self.server_log():
            st, body = self.post('/api/autosync', {}, 'p')
        self.assertEqual((st, body['ok'], body['reason']), (200, False, 'error'), body)
        self.assertTrue(body['error'])

    # ---------------------------------------------------------------- рядки свого модуля (ревʼю Task 5, M9)
    def test_a_hint_of_a_foreign_module_with_a_token_never_reaches_the_push_response_or_the_autosync(self):
        leak = {'ok': False, 'synced': False, 'error': 'denied', 'hint': f'use https://{TOKEN}@host/o/r.git', 'code': 'x'}
        mod = self.stub(push=lambda ctx, t, d, m: dict(leak))
        with mock.patch.object(serve, 'vcs_provider', side_effect=lambda: (mod, serve._vcs_legacy_ctx(), True)):
            for path in ('/api/vcs-push', '/api/gitlab-sync'):
                st, body = self.post(path, {'it': 'it1'}, 'a')
                self.assertEqual((st, body['hint']), (200, 'use https://***@host/o/r.git'))
                self.assertNotIn(TOKEN, json.dumps(body))
            st, body = self.post('/api/autosync', {}, 'a')
            self.assertEqual((st, body['hint']), (200, 'use https://***@host/o/r.git'))
            self.assertNotIn(TOKEN, json.dumps(body))

    # ---------------------------------------------------------------- підпис локального автокоміту (ревʼю Task 5, M10)
    def test_the_local_autocommit_of_the_autosync_is_signed_by_the_space(self):
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        for tid, d, tool in (('a', self.a_dir, 'design-canvas'), ('p', self.p_dir, 'deai')):
            with self.subTest(task=tid):
                st, body = self.post('/api/autosync', {}, tid)
                self.assertEqual((st, body['ok'], body['synced']), (200, True, True), body)
                # теки без `.git` AI-коміту не отримують (фаза И): підпис простору ставить автокоміт `autosync()`
                self.assertEqual(self.out(d, 'log', '-1', '--format=%s'), f'it1: автосинк ({tool})')

    # ---------------------------------------------------------------- маска адреси
    def test_a_token_in_an_exception_never_reaches_a_response_of_the_routes(self):
        """Поправка 8: усе, що маршрути друкують із винятку, — через `_mask_repo`: чужий текст із адресою теж."""
        msg = f'clone of https://{TOKEN}@github.com/o/r.git failed'
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        for tid in ('a', 'p'):
            for method, path, fn, payload in (('GET', '/api/vcs-status?it=it1', 'gitlab_status', None),
                                              ('GET', '/api/gitlab-status?it=it1', 'gitlab_status', None),
                                              ('POST', '/api/vcs-push', 'gitlab_sync', {'it': 'it1'}),
                                              ('POST', '/api/gitlab-sync', 'gitlab_sync', {'it': 'it1'}),
                                              ('POST', '/api/vcs-pull', 'gitlab_pull', {}),
                                              ('POST', '/api/gitlab-pull', 'gitlab_pull', {}),
                                              ('POST', '/api/autosync', 'autosync', {})):
                with self.subTest(task=tid, path=path):
                    with self.server_log(), mock.patch.object(serve, fn, side_effect=OSError(msg)):
                        st, body = self.call(method, path, payload, tid)
                    self.assertEqual(st, 200)
                    self.assertEqual(body['error'], 'clone of https://***@github.com/o/r.git failed')
                    self.assertNotIn(TOKEN, json.dumps(body))

    # ---------------------------------------------------------------- маска ДО обрізання (ревʼю c191cfb, Minor 2)
    @staticmethod
    def straddle(limit):
        """Текст, у якому адреса з токеном починається за 15 символів до `limit`: `https://` займає 8, тож у зріз `[:limit]` без
        маски потрапляє `https://ghp_SEC` — без `@`, маска його вже не впізнає, і початок токена йде назовні."""
        return 'a' * (limit - 15) + f'https://{TOKEN}@github.com/o/r.git'

    def test_the_address_is_masked_before_the_text_is_cut_in_every_failure_body_of_the_routes(self):
        """Порядок «спершу маска, потім обрізання» тримає кожне місце, що друкує текст винятку: `_vcs_failure` (відправка, прийом,
        автосинк) на 300 і маршрут статусу на 200."""
        dm.write_module_state(self.plain, 'git-sync', settings={'autosync': True})
        cases = (('GET', '/api/vcs-status?it=it1', 'gitlab_status', None, OSError, 200),
                 ('GET', '/api/gitlab-status?it=it1', 'gitlab_status', None, OSError, 200),
                 ('POST', '/api/vcs-push', 'gitlab_sync', {'it': 'it1'}, OSError, 300),
                 ('POST', '/api/gitlab-sync', 'gitlab_sync', {'it': 'it1'}, OSError, 300),
                 ('POST', '/api/vcs-pull', 'gitlab_pull', {}, OSError, 300),
                 ('POST', '/api/gitlab-pull', 'gitlab_pull', {}, OSError, 300),
                 ('POST', '/api/autosync', 'autosync', {}, OSError, 300),
                 ('POST', '/api/autosync', 'autosync', {}, ValueError, 300))
        for tid in ('a', 'p'):
            for method, path, fn, payload, kind, limit in cases:
                with self.subTest(task=tid, path=path, exc=kind.__name__):
                    with self.server_log(), mock.patch.object(serve, fn, side_effect=kind(self.straddle(limit))):
                        st, body = self.call(method, path, payload, tid)
                    self.assertEqual(st, 200, body)
                    self.assertEqual(body['error'], ('a' * (limit - 15) + 'https://***@github.com/o/r.git')[:limit])
                    self.assertNotIn('ghp_SE', json.dumps(body), 'початок токена пройшов крізь обрізання')

    def test_a_returned_error_of_a_foreign_module_never_reaches_the_push_response_or_the_autosync(self):
        """Поправка 10 крізь HTTP: модуль не кидає, а повертає `{ok: false, error: <адреса з токеном>}`."""
        leak = {'ok': False, 'synced': False, 'error': f'push to https://{TOKEN}@host/o/r.git denied'}
        mod = self.stub(push=lambda ctx, t, d, m: dict(leak))
        with mock.patch.object(serve, 'vcs_provider', side_effect=lambda: (mod, serve._vcs_legacy_ctx(), True)):
            st, body = self.post('/api/vcs-push', {'it': 'it1'}, 'a')
            self.assertEqual(st, 200)
            self.assertEqual(body['error'], 'push to https://***@host/o/r.git denied')
            self.assertNotIn(TOKEN, json.dumps(body))
            st, body = self.post('/api/autosync', {}, 'a')
            self.assertEqual((st, body['error']), (200, 'push to https://***@host/o/r.git denied'))
            self.assertNotIn(TOKEN, json.dumps(body))

    # ---------------------------------------------------------------- нова задача з `vcs`
    def tasks_bytes(self):
        with open(self.plain_tasks, 'rb') as fh:
            return fh.read()

    def new(self, payload, space=None):
        return self.post('/api/task-new', {'space': (space or self.plain)['id'], 'title': 'Нова', **payload})

    def nothing_written(self, before, tid):
        self.assertEqual(self.tasks_bytes(), before, 'tasks.json простору змінено')
        self.assertFalse(os.path.exists(os.path.join(self.plain['path'], tid)), 'тека задачі створена')
        self.assertEqual(os.listdir(self.systmp), [], 'лишилась тимчасова тека')

    def test_task_new_records_the_vcs_target_and_takes_the_mockup_from_the_repo(self):
        self.peer_push({'mockup/n1/index.html': '<h1>з репо</h1>'})
        st, body = self.new({'id': 'n1', 'vcs': {'repo': self.origin}})
        self.assertEqual((st, body['ok'], body['cloned'], body['space']), (200, True, True, self.plain['id']), body)
        with open(self.plain_tasks, encoding='utf-8') as fh:
            entry = json.load(fh)['tasks']['n1']
        self.assertEqual(entry['vcs'], {'repo': self.origin})
        self.assertNotIn('gitlab', entry)
        with open(os.path.join(body['dir'], 'iterations', 'it1', 'index.html'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '<h1>з репо</h1>')

    def test_task_new_trims_the_vcs_strings_and_drops_the_empty_ones(self):
        st, body = self.new({'id': 'n2', 'vcs': {'repo': f'  {self.origin}\n', 'path': ' docs/{task} ', 'branch': None}})
        self.assertEqual((st, body['ok']), (200, True), body)
        with open(self.plain_tasks, encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['tasks']['n2']['vcs'], {'repo': self.origin, 'path': 'docs/{task}'})

    def test_task_new_with_a_target_the_module_refuses_is_400_and_writes_nothing(self):
        """Поправка 4: `ext::sh` — це виконання команди, а ядро `task_new` кладе `vcs` як є, навіть коли модуль ціль
        відхилив: відмова мусить настати ДО будь-якого запису (задача, тека, `tasks.json`)."""
        before = self.tasks_bytes()
        for repo in ('ext::sh', 'ext::sh -c id', 'https://anna:hunter2@github.com/o/r.git', '--upload-pack=x', 'two words'):
            with self.subTest(repo=repo):
                st, body = self.new({'id': 'bad1', 'vcs': {'repo': repo}})
                self.assertEqual((st, body['ok'], body['code']), (400, False, 'vcs-bad-target'), body)
                self.assertNotIn('hunter2', json.dumps(body))
                self.nothing_written(before, 'bad1')

    def test_task_new_refuses_a_bad_target_before_a_folder_to_adopt_is_taken(self):
        folder = os.path.join(self.tmp, 'adopt')
        write(os.path.join(folder, 'index.html'), '<h1>моя тека</h1>')
        before = self.tasks_bytes()
        st, body = self.new({'id': 'bad2', 'from': folder, 'vcs': {'repo': 'ext::sh -c id'}})
        self.assertEqual((st, body['code']), (400, 'vcs-bad-target'), body)
        self.nothing_written(before, 'bad2')

    def test_task_new_with_a_branch_or_a_path_the_module_refuses_is_400(self):
        before = self.tasks_bytes()
        for vcs in ({'repo': self.origin, 'branch': 'a..b'}, {'repo': self.origin, 'path': '../x'}):
            with self.subTest(vcs=vcs):
                st, body = self.new({'id': 'bad3', 'vcs': vcs})
                self.assertEqual((st, body['code']), (400, 'vcs-bad-target'), body)
                self.nothing_written(before, 'bad3')

    def test_task_new_with_a_vcs_in_a_space_without_the_role_is_400_vcs_needs_role(self):
        bare = self.bare_space()
        before = self.tasks_bytes()
        with open(os.path.join(bare['path'], 'tasks.json'), 'rb') as fh:
            bare_before = fh.read()
        st, body = self.new({'id': 'n3', 'vcs': {'repo': self.origin}}, space=bare)
        self.assertEqual((st, body['ok'], body['code']), (400, False, 'vcs-needs-role'), body)
        with open(os.path.join(bare['path'], 'tasks.json'), 'rb') as fh:
            self.assertEqual(fh.read(), bare_before)
        self.assertFalse(os.path.exists(os.path.join(bare['path'], 'n3')))
        self.assertEqual(self.tasks_bytes(), before)

    def test_task_new_with_a_vcs_that_is_not_a_target_object_is_400_bad_request(self):
        before = self.tasks_bytes()
        bad = ('x', 5, True, [], [{'repo': 'r'}], {}, {'path': 'p'}, {'repo': ''}, {'repo': '   '}, {'repo': None}, {'repo': 5},
               {'repo': self.origin, 'extra': 'x'}, {'repo': self.origin, 'ssh_key': '/k'}, {'repo': self.origin, 'path': 5},
               {'repo': self.origin, 'branch': ['x']}, {'repo': self.origin, 'path': True})
        for vcs in bad:
            with self.subTest(vcs=vcs):
                st, body = self.new({'id': 'bad4', 'vcs': vcs})
                self.assertEqual((st, body['ok'], body['code']), (400, False, 'bad-request'), body)
                self.nothing_written(before, 'bad4')

    def test_task_new_without_a_vcs_or_with_a_null_one_never_asks_the_provider(self):
        with mock.patch.object(serve, 'vcs_provider', side_effect=AssertionError('постачальник без vcs')):
            st, body = self.new({'id': 'n4'})
            self.assertEqual((st, body['ok']), (200, True), body)
            st, body = self.new({'id': 'n5', 'vcs': None})
            self.assertEqual((st, body['ok']), (200, True), body)

    def test_task_new_with_a_valid_folder_to_adopt_and_a_vcs_takes_the_folder_and_records_the_target(self):
        """Ревʼю Task 5 (M6): `from` + `vcs` — 200, отримання з репо нема (людина вже назвала джерело макета), ціль записано."""
        folder = os.path.join(self.tmp, 'adopt-ok')
        write(os.path.join(folder, 'index.html'), '<h1>моя тека</h1>')
        self.peer_push({'mockup/n13/index.html': '<h1>з origin</h1>'})
        st, body = self.new({'id': 'n13', 'from': folder, 'vcs': {'repo': self.origin, 'path': 'docs/{task}'}})
        self.assertEqual((st, body['ok'], body['cloned']), (200, True, False), body)
        self.assertEqual(body['copied']['files'], 1)
        with open(self.plain_tasks, encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['tasks']['n13']['vcs'], {'repo': self.origin, 'path': 'docs/{task}'})
        with open(os.path.join(body['dir'], 'iterations', 'it1', 'index.html'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '<h1>моя тека</h1>')
        self.assertEqual(os.listdir(self.systmp), [])

    def test_task_new_with_a_refusing_provider_is_409_with_the_frame_code_and_writes_nothing(self):
        self.break_space_json()
        before = self.tasks_bytes()
        st, body = self.new({'id': 'n6', 'vcs': {'repo': self.origin}})
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'space-json-unreadable'), body)
        self.nothing_written(before, 'n6')

    def test_task_new_with_a_vcs_and_a_bad_task_id_is_the_old_bad_task_id(self):
        for tid in (5, None, '../x'):
            with self.subTest(id=tid):
                st, body = self.new({'id': tid, 'vcs': {'repo': self.origin}})
                self.assertEqual((st, body['code']), (400, 'bad-task-id'), body)

    def test_validate_gets_the_target_the_task_would_have(self):
        seen = []

        def validate(ctx, t):
            seen.append(t)
            return t
        mod = self.stub(validate=validate)
        with mock.patch.object(serve, 'vcs_provider', side_effect=lambda: (mod, serve._vcs_legacy_ctx(), False)):
            st, body = self.new({'id': 'n7', 'vcs': {'repo': self.origin, 'path': 'x/{task}'}})
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(seen[0], {'repo': self.origin, 'task': 'n7', 'path': 'x/n7', 'branch': 'main'})

    def test_validate_of_an_own_module_runs_under_the_short_limit_of_the_frame(self):
        """Поправка 3: завислий `validate` свого модуля не тримає `task-new` — відповідь із кодом тайм-ауту каркаса."""
        mod = self.stub(validate=lambda ctx, t: time.sleep(3))
        before = self.tasks_bytes()
        with mock.patch.object(serve, 'vcs_provider', side_effect=lambda: (mod, serve._vcs_legacy_ctx(), False)), \
                mock.patch.object(dm, 'CHECK_TIMEOUT', 0.3):
            t0 = time.monotonic()
            st, body = self.new({'id': 'n8', 'vcs': {'repo': self.origin}})
            took = time.monotonic() - t0
        self.assertEqual((st, body['ok'], body['code']), (504, False, 'check-timeout'), body)
        self.assertLess(took, 2.5, 'відповідь чекала на модуль')
        self.nothing_written(before, 'n8')

    def test_validate_of_an_own_module_that_refuses_or_answers_wrongly(self):
        before = self.tasks_bytes()

        def refuse(ctx, t):
            raise ctx['ModuleError']('vcs-bad-target', message='my module does not like this')
        for what, fn, status, code in (('відмова', refuse, 400, 'vcs-bad-target'),
                                       ('не обʼєкт', lambda ctx, t: 5, 502, 'module-error'),
                                       ('збій', lambda ctx, t: 1 / 0, 502, 'module-error')):
            mod = self.stub(validate=fn)
            with self.subTest(what=what):
                with mock.patch.object(serve, 'vcs_provider', side_effect=lambda m=mod: (m, serve._vcs_legacy_ctx(), False)):
                    st, body = self.new({'id': 'n9', 'vcs': {'repo': self.origin}})
                self.assertEqual((st, body['ok'], body['code']), (status, False, code), body)
                self.nothing_written(before, 'n9')

    def test_task_new_in_the_liga_space_runs_the_same_checks_and_records_the_vcs(self):
        """Постачальник простору ЛІГА — неявний `'legacy'` (той самий `git-sync`): `vcs` у `task-new` перевіряється так само."""
        with open(self.liga_tasks, 'rb') as fh:
            before = fh.read()
        st, body = self.new({'id': 'n11', 'profile': 'tool', 'vcs': {'repo': 'ext::sh'}}, space=self.liga)
        self.assertEqual((st, body['code']), (400, 'vcs-bad-target'), body)
        with open(self.liga_tasks, 'rb') as fh:
            self.assertEqual(fh.read(), before)
        self.assertFalse(os.path.exists(os.path.join(self.liga_root, 'n11')))
        self.peer_push({'mockup/n12/index.html': '<h1>з репо ЛІГИ</h1>'})
        st, body = self.new({'id': 'n12', 'profile': 'tool', 'vcs': {'repo': self.origin}}, space=self.liga)
        self.assertEqual((st, body['ok'], body['cloned']), (200, True, True), body)
        with open(self.liga_tasks, encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['tasks']['n12']['vcs'], {'repo': self.origin})

    def test_a_module_without_validate_is_not_asked(self):
        plain_mod = dm.Module('git-sync', roles=['vcs'], fns={'status': lambda c, t: {}, 'push': lambda *a: {},
                                                              'pull': lambda c, t, d, o=None: {'found': False}})
        with mock.patch.object(serve, 'vcs_provider', side_effect=lambda: (plain_mod, serve._vcs_legacy_ctx(), False)):
            st, body = self.new({'id': 'n10', 'vcs': {'repo': 'ext::sh -c id'}})
        self.assertEqual((st, body['ok']), (200, True), body)


if __name__ == '__main__':
    unittest.main()
