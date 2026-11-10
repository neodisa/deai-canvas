"""Вимикач інтеграцій: простір без них не ходить у Supabase, Teams, GitLab, Vercel, реєстр.

Етап 1 Deai 1.0, Task 4 (спека 2026-10-13-deai-spaces-design.md, «Вимикач інтеграцій»).

Як це доводиться — РОЗТЯЖКОЮ, а не перевіркою відповіді: усе, що вміє вийти з машини
(`urllib.request.urlopen`, `socket.create_connection`, `subprocess.run/Popen` з `git push|fetch|
clone|ls-remote|pull`, `npx`, `vercel`, `overview_push.py`, `registry.py`), підмінено записувачем,
який кидає `OSError('tripwire')`. Простір без інтеграцій обовʼязаний лишити запис порожнім, а
КОНТРОЛЬ (простір з інтеграціями, той самий виклик) обовʼязаний його заповнити — інакше «нуль
записів» нічого не доводить (розтяжка могла б бути просто зламана).

Три шари:
  * `Points`  — кожна точка виходу окремою функцією (`ProjectComments.pins`/`resolve` — командні піни ЛІГИ модулем
                `supabase-comments`, `notify_call`, `team_snapshot`,
                `_registry_push`, `_overview_sync`, `git_autocommit`,
                `task_new` із дзеркалом GitLab): `with spaces.request_space('off'|'on')`;
  * `Routes`  — сервер у процесі: маршрути простору без інтеграцій (409 `integrations-off`, чи
                «нема GitLab», чи `team: null`), контроль — той самий маршрут із `X-Canvas-Task: a`;
                `task-new` у простір без інтеграцій не пушить у реєстр і не робить `git push`;
  * `Cli`     — `bin/state.py` і `bin/inbox.py`.

⛔ Ізоляція: власні тимчасові `HOME`, `DEAI_HOME`; `DC_TASKS_FILE` указує на ТИМЧАСОВИЙ старий файл
(шар просторів увімкнено, бо є `DEAI_HOME`; живий `tasks.json` недосяжний), `DC_NO_OVERVIEW`,
`DC_TEAM_FAKE`, `DC_TEAMS_FAKE` прибрані. Але `DC_TASKS_FILE` сам глушить мережу (`notify_call`,
`team_snapshot`, `_registry_push`) — тож усі перевірки, чия відмова мусить належати САМЕ вимикачу,
йдуть у `unisolated()`: змінна прибрана, старий файл підставлено через `spaces.legacy_tasks_file`.
Розтяжка вмикається РАНІШЕ за будь-яке прибирання запобіжників; справжній `~/.deai` стереже
`spaces_guard`. Порт 8765 і живі `tasks.json` не чіпаються.
"""
import contextlib
import gc
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import warnings
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liga_fixture  # noqa: E402
import sbconf  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import state  # noqa: E402
import inbox  # noqa: E402
from atomic_io import atomic_write_json  # noqa: E402

_REAL = None
#: Хост і порт Supabase ЛІГИ з вигаданого конфігу тестів (`sbconf.ENV`): першим записом розтяжки має бути саме він.
LIGA_HOST = urllib.parse.urlsplit(sbconf.SB_URL).hostname + ':443'


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


# ---------- розтяжка ----------

LOOPBACK = ('127.0.0.1', 'localhost', '::1')
#: Підкоманди `git`, що працюють ЛИШЕ з локальним репозиторієм. Усе інше (`push`, `fetch`, `clone`,
#: `pull`, `ls-remote`, `submodule`, `remote update|show|prune`, псевдоніми…) — назовні.
LOCAL_GIT = {'init', 'add', 'commit', 'rev-parse', 'log', 'status', 'checkout', 'merge',
             'cat-file', 'symbolic-ref', 'diff', 'ls-files', 'show', 'branch', 'tag', 'reset',
             'rm', 'mv'}
#: `git remote <…>`: лише те, що правлять локальний конфіг (`update`/`show`/`prune` ходять до origin).
#: `-v` сюди НЕ входить: `git remote -v update` — це `update` (прапорець `-v` лише сам: `rest == ['-v']`).
LOCAL_REMOTE = {'add', 'remove', 'rm', 'get-url', 'set-url'}
#: `git config`: лише ЧИТАННЯ — перший аргумент один із цих прапорців, далі лише позиційні (ключ, regexp).
#: Запис (`core.fsmonitor`, `core.hooksPath`, `core.editor`, `core.sshCommand`, `alias.*`) змушує
#: наступну «локальну» команду запускати чужий код, а `--global`/`-e`/`--file` ще й ходять мимо репозиторію.
GIT_CONFIG_READ = ('--get', '--get-all', '--get-regexp', '--list', '-l')
#: Глобальні опції `git` ПЕРЕД підкомандою без аргументу, які пускаємо. Решта `--опцій`
#: (`--git-dir`, `--work-tree`, `--exec-path`, `--config-env`, `--namespace`, …) і `-p/-P` міняють,
#: ЩО й ЧИМ виконує git, — «дозволена» підкоманда з ними вже не локальна (`--git-dir status push`).
GIT_GLOBAL_OK = ('--no-pager',)
#: Ключі `git -c <k=v>`, які пускаємо: підміна адреси (`url.*`) і особа коміту (`user.*`). Будь-який
#: інший (`core.sshCommand`, `core.gitProxy`, `core.fsmonitor`, `submodule.recurse`…) — запуск чужої
#: команди чи мережа в «локальній» підкоманді.
GIT_C_KEYS = ('url.', 'user.')
#: Підкоманди, де `--recurse-submodules` (і будь-який його скорочений префікс: git приймає
#: однозначні скорочення довгих опцій) витягує субмодулі.
GIT_NO_RECURSE = ('checkout', 'reset')


def _git_args(args):
    """`(підкоманда, решта)` команди `git` після глобальних опцій; `('', [])`, коли підкоманди нема
    АБО перед нею стоїть опція, якої ми не знаємо (тоді `is_allowed` каже ні). Пускаються лише
    `-C <dir>`, `-c <ключ з GIT_C_KEYS>=<значення>` і `GIT_GLOBAL_OK`."""
    i = 1
    while i < len(args):
        a = args[i]
        if a == '-C':
            if i + 1 >= len(args):
                return '', []
            i += 2
        elif a == '-c':
            if i + 1 >= len(args) or not args[i + 1].split('=', 1)[0].lower().startswith(GIT_C_KEYS):
                return '', []
            i += 2
        elif a in GIT_GLOBAL_OK:
            i += 1
        elif a.startswith('-'):
            return '', []
        else:
            return a, args[i + 1:]
    return '', []


def is_allowed(args):
    """БІЛИЙ список: що з підпроцесів справді виконується. Пропускається лише `git` з локальною
    підкомандою (`LOCAL_GIT`; `remote` без аргументів, `-v` САМ, чи `LOCAL_REMOTE` — `add` без
    жодного прапорця, бо `-f/--fetch` робить fetch; `config` лише на читання (`GIT_CONFIG_READ`);
    `stash list`; `--version`) і лише з глобальними
    опціями `-C`, `-c url.*|user.*`, `--no-pager`; `checkout/reset` — без `--recurse-submodules`.
    Усе інше — `curl`, `ssh`, `sh -c 'git push'`, `npx`, `python3 …/overview_push.py`, `zsh -lic …`,
    рядок із shell=True — записується й блокується. Чого не знаємо — не пускаємо."""
    if not isinstance(args, (list, tuple)) or not args:
        return False
    args = [os.fspath(a) if isinstance(a, os.PathLike) else a for a in args]
    if not all(isinstance(a, str) for a in args):
        return False
    if os.path.basename(args[0]) != 'git':
        return False
    if args[1:] == ['--version']:
        return True
    sub, rest = _git_args(args)
    if sub in LOCAL_GIT:
        if sub in GIT_NO_RECURSE:
            return not any('--recurse-submodules'.startswith(a.split('=', 1)[0])
                           for a in rest if a.startswith('--r'))
        return True
    if sub == 'remote':
        if not rest or rest == ['-v']:
            return True
        # `add -f|--fetch` робить fetch відразу; прапорці можуть стояти де завгодно, бути
        # скороченими (`--fet`) чи згорнутими (`-ft`) — тож для `add` пускаємо лише БЕЗ прапорців.
        return rest[0] in LOCAL_REMOTE and not (
            rest[0] == 'add' and any(a.startswith('-') for a in rest[1:]))
    if sub == 'config':
        return (bool(rest) and rest[0] in GIT_CONFIG_READ
                and not any(a.startswith('-') for a in rest[1:]))
    if sub == 'stash':
        return rest[:1] == ['list']
    return False


def _host_port(target):
    url = getattr(target, 'full_url', None) or str(target)
    u = urllib.parse.urlparse(url)
    return u.hostname, u.port


class Tripwire:
    """Усе, що виходить з машини, — у запис і `OSError('tripwire')`. Пропускається лише loopback на
    порти ЦЬОГО тесту (`allow_ports`: сервер у процесі, його заповнює `World.setUpClass`) — будь-який
    інший loopback-порт (8765 справжнього канваса!) теж «вихід» — і підпроцеси з білого списку
    (`is_allowed`). `hits` — список `(вид, подробиці)`."""

    def __init__(self):
        self.hits = []
        self.allow_ports = set()
        real_urlopen, real_cc = urllib.request.urlopen, socket.create_connection
        real_run, real_popen = subprocess.run, subprocess.Popen

        def urlopen(target, *a, **kw):
            host, port = _host_port(target)
            if host in LOOPBACK and port in self.allow_ports:
                return real_urlopen(target, *a, **kw)
            method = target.get_method() if hasattr(target, 'get_method') else 'GET'
            self.hits.append(('urlopen', f'{method} {getattr(target, "full_url", target)}'))
            raise OSError('tripwire')

        def create_connection(address, *a, **kw):
            if address[0] in LOOPBACK and address[1] in self.allow_ports:
                return real_cc(address, *a, **kw)
            self.hits.append(('socket', f'{address[0]}:{address[1]}'))
            raise OSError('tripwire')

        def shown(args):
            return args if isinstance(args, str) else ' '.join(map(str, args))

        def run(args, *a, **kw):
            if not is_allowed(args):
                self.hits.append(('run', shown(args)))
                raise OSError('tripwire')
            return real_run(args, *a, **kw)

        def popen(args, *a, **kw):
            if not is_allowed(args):
                self.hits.append(('popen', shown(args)))
                raise OSError('tripwire')
            return real_popen(args, *a, **kw)

        self._stack = contextlib.ExitStack()
        for owner, name, repl in ((urllib.request, 'urlopen', urlopen),
                                  (socket, 'create_connection', create_connection),
                                  (subprocess, 'run', run), (subprocess, 'Popen', popen)):
            self._stack.enter_context(mock.patch.object(owner, name, repl))

    def stop(self):
        self._stack.close()

    def of(self, kind):
        return [d for k, d in self.hits if k == kind]


#: Те, що МУСИТЬ бути заблоковано й записано (кожне — окремий шлях назовні, якого розтяжка-«чорний
#: список» не бачила: `-C`, `remote update|show`, `submodule`, обгортка `sh -c`, не-git).
ESCAPES = (
    ['git', 'push', '-q'], ['git', 'fetch', '--quiet', 'origin', 'main'],
    ['git', 'clone', 'x', 'y'], ['git', 'ls-remote', 'origin'], ['git', 'pull', '--ff-only'],
    ['git', '-c', 'url.git@1.2.3.4:.insteadOf=git@h:', 'push', 'origin'],
    ['git', '-C', '/x', 'push'], ['git', '-C', '/x', '-c', 'k=v', 'fetch'],
    ['git', 'remote', 'update'], ['git', 'remote', 'show', 'origin'], ['git', 'remote', 'prune', 'origin'],
    ['git', 'submodule', 'update'], ['git', 'stash', 'pop'], ['git', 'bundle', 'create'],
    ['sh', '-c', 'git push'], ['curl', 'https://example.invalid/'],
    ['ssh', '-o', 'BatchMode=yes', 'example.invalid', 'true'],
    ['/opt/homebrew/bin/npx', '--yes', 'vercel', 'deploy'],
    ['python3', '/x/bin/overview_push.py', 'sync'], ['python3', '/x/bin/registry.py', 'push'],
    ['zsh', '-lic', 'command -v npx'], 'git push', [],
    # Другий обхід (ре-ревʼю Task 4): «дозволена» підкоманда, що несе мережу в прапорцях/опціях.
    ['git', 'remote', 'add', '-f', 'o', 'u'], ['git', 'remote', 'add', '--fetch', 'o', 'u'],
    ['git', 'remote', 'add', 'o', 'u', '-f'], ['git', 'remote', 'add', '--fet', 'o', 'u'],
    ['git', 'remote', 'add', '-ft', 'main', 'o', 'u'],
    ['git', 'remote', '-v', 'update'], ['git', 'remote', '-v', 'show', 'origin'],
    ['git', '-c', 'core.sshCommand=ssh', 'commit'], ['git', '-c', 'core.sshCommand=x', '-C', '/x', 'status'],
    ['git', '-c', 'user.name=a', '-c', 'core.fsmonitor=x', 'status'], ['git', '-c', 'k=v', 'status'],
    ['git', '-c', 'core.gitProxy=x', 'log'], ['git', '-c'], ['git', '-c', 'user.name=a'],
    ['git', '--git-dir', 'status', 'push'], ['git', '--git-dir=/x', 'status'],
    ['git', '--work-tree=/x', 'status'], ['git', '--exec-path=/x', 'status'],
    ['git', '--config-env=core.sshCommand=X', 'status'], ['git', '--no-pager', '--git-dir', 'status'],
    ['git', '-p', 'status'], ['git', '-P', 'status'], ['git', '--namespace=x', 'status'],
    ['git', 'checkout', '--recurse-submodules'], ['git', 'checkout', '--recurse-submodules', 'main'],
    ['git', 'checkout', '--recurse-submodule', 'main'], ['git', 'checkout', '--rec', 'main'],
    ['git', '-C', '/x', 'checkout', '-b', 'n', '--recurse-submodules=on-demand'],
    ['git', 'reset', '--hard', '--recurse-submodules'],
    # `git config` ПИШЕ конфіг, який потім виконує git: `core.fsmonitor`/`core.hooksPath`/`core.editor`/
    # `core.sshCommand` → наступний `status`/`commit` запускає чужу команду. Дозволено лише читання.
    ['git', 'config', 'core.fsmonitor', 'cmd'], ['git', 'config', 'core.hooksPath', '/x'],
    ['git', 'config', 'core.editor', 'x'], ['git', 'config', 'core.sshCommand', 'x'],
    ['git', 'config', '--global', 'core.fsmonitor', 'x'], ['git', 'config', '--global', '--get', 'k'],
    ['git', 'config', '--local', 'core.editor', 'x'], ['git', 'config', '-e'], ['git', 'config', '--edit'],
    ['git', 'config', '--add', 'core.fsmonitor', 'x'], ['git', 'config', '--replace-all', 'k', 'v'],
    ['git', 'config', '--unset', 'k'], ['git', 'config', '--unset-all', 'k'],
    ['git', 'config', '--remove-section', 'core'], ['git', 'config', '--rename-section', 'a', 'b'],
    ['git', 'config', 'user.name'], ['git', 'config', 'alias.p', '!git push'], ['git', 'config'],
    ['git', 'config', '--get', '--add', 'k', 'v'], ['git', 'config', '--list', '-e'],
    ['git', 'config', '--ge', 'k'], ['git', '-C', '/x', 'config', 'core.fsmonitor', 'cmd'],
    ['git', '-c', 'user.name=n', 'config', '--file', '/x', 'k', 'v'],
)


class TripwireItself(unittest.TestCase):
    """Охоронець, який не може впасти, нічого не вартий: розтяжка сама доводиться."""

    def setUp(self):
        self.trip = Tripwire()
        self.addCleanup(self.trip.stop)
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='integrations-tripwire-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_whitelist_lets_only_local_git_through(self):
        for argv in (['git', 'commit', '-q', '-m', 'pull and push later'],
                     ['git', 'remote'], ['git', 'remote', '-v'], ['git', 'remote', 'add', 'origin', 'x'],
                     ['git', 'remote', 'get-url', 'origin'], ['git', 'init', '-q'],
                     ['git', 'rev-parse', 'HEAD'], ['git', 'stash', 'list'], ['git', '--version'],
                     ['git', '-C', '/x', 'rev-parse', '--git-dir'],
                     ['git', '-c', 'user.name=k', 'config', '--get', 'remote.origin.url'],
                     ['/usr/bin/git', 'log', '--oneline'],
                     # що вузька розтяжка НЕ блокує зайвого: форми, якими справді ходить код
                     ['git', '--no-pager', 'log', '--reverse'], ['git', 'remote', 'add', 'origin', '/x'],
                     ['git', '-C', '/x', '-c', 'user.name=n', '-c', 'user.email=e', 'commit', '-q', '-m', 'm'],
                     ['git', '-c', 'url.git@1.2.3.4:.insteadOf=git@h:', 'status'],
                     ['git', '-c', 'USER.name=n', 'commit'],
                     ['git', 'config', '--get', 'k'], ['git', 'config', '--get-all', 'k'],
                     ['git', 'config', '--get-regexp', '^remote'], ['git', 'config', '--list'],
                     ['git', 'config', '-l'], ['git', '-C', '/x', 'config', '--get', 'remote.origin.url'],
                     ['git', 'checkout', 'main'], ['git', 'checkout', '-b', 'n'],
                     ['git', 'checkout', '-q', '--', 'a.txt'], ['git', 'reset', '--hard', 'HEAD~1']):
            self.assertTrue(is_allowed(argv), argv)
        for argv in ESCAPES:
            self.assertFalse(is_allowed(argv), argv)

    def safe_env(self):
        """Середовище для ESCAPES: розтяжка, що ЗЛАМАЛАСЬ (або мутована), пропустила б команду
        по-справжньому — тож вона не бачить ні справжньої домівки (`git config --global …` писав би в
        `~/.gitconfig`), ні редактора (`config -e`), ні ssh/проксі, ні запитів пароля."""
        return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': self.tmp,
                'GIT_CONFIG_GLOBAL': os.path.join(self.tmp, 'gitconfig'), 'GIT_CONFIG_NOSYSTEM': '1',
                'GIT_EDITOR': 'true', 'EDITOR': 'true', 'VISUAL': 'true', 'GIT_TERMINAL_PROMPT': '0',
                'GIT_ASKPASS': 'true', 'SSH_ASKPASS': 'true', 'GIT_SSH_COMMAND': 'false',
                'GIT_PROXY_COMMAND': 'false'}

    def test_every_escape_is_recorded_and_blocked_by_run_and_popen(self):
        env = self.safe_env()
        for argv in ESCAPES:
            for call in (subprocess.run, subprocess.Popen):
                with self.subTest(argv=argv, call=call.__name__):
                    n = len(self.trip.hits)
                    with self.assertRaises(OSError):
                        call(argv, cwd=self.tmp, env=env)
                    self.assertEqual(len(self.trip.hits), n + 1)
        self.assertEqual(len(self.trip.hits), len(ESCAPES) * 2)

    def test_local_git_really_runs(self):
        """Білий список не «блокує все»: локальні команди виконуються по-справжньому (`-C` теж)."""
        d = os.path.join(self.tmp, 'repo')
        os.makedirs(d)
        subprocess.run(['git', '-C', d, 'init', '-q'], check=True)
        subprocess.run(['git', '-C', d, 'remote', 'add', 'origin', '/nonexistent'], check=True)
        out = subprocess.run(['git', '-C', d, 'remote'], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), 'origin')
        self.assertEqual(subprocess.run(['git', '--version'], capture_output=True).returncode, 0)
        p = subprocess.Popen(['git', '-C', d, 'stash', 'list'], stdout=subprocess.PIPE)
        self.assertEqual(p.wait(), 0)
        p.stdout.close()
        self.assertEqual(self.trip.hits, [])

    def test_records_and_blocks_every_network_channel(self):
        with self.assertRaises(OSError):
            urllib.request.urlopen('https://example.invalid/x')
        with self.assertRaises(OSError):
            urllib.request.urlopen(urllib.request.Request('https://example.invalid/y', method='PATCH'))
        with self.assertRaises(OSError):
            socket.create_connection(('example.invalid', 443))
        self.assertEqual([k for k, _ in self.trip.hits], ['urlopen', 'urlopen', 'socket'])
        self.assertIn('PATCH https://example.invalid/y', self.trip.of('urlopen'))

    def test_loopback_passes_only_on_the_allowed_ports(self):
        srv, other = socket.socket(), socket.socket()
        for s_ in (srv, other):
            s_.bind(('127.0.0.1', 0))
            s_.listen(2)
            self.addCleanup(s_.close)
        port, other_port = srv.getsockname()[1], other.getsockname()[1]
        gone = socket.socket()                      # закритий порт: «справжній канвас на іншому порту»
        gone.bind(('127.0.0.1', 0))
        gone_port = gone.getsockname()[1]
        gone.close()
        # порт не дозволено — це «вихід»: запис і відмова (таймаут — щоб мутація «пускати весь loopback»
        # не повисла на сервері, який мовчить)
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=1)
        with self.assertRaises(OSError):
            urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1)
        with self.assertRaises(OSError):
            urllib.request.urlopen(f'http://localhost:{gone_port}/api/task', timeout=1)
        self.assertEqual(self.trip.hits, [('socket', f'127.0.0.1:{port}'),
                                          ('urlopen', f'GET http://127.0.0.1:{port}/'),
                                          ('urlopen', f'GET http://localhost:{gone_port}/api/task')])
        self.trip.hits.clear()
        self.trip.allow_ports.add(port)
        socket.create_connection(('127.0.0.1', port)).close()
        self.assertEqual(self.trip.hits, [])
        with self.assertRaises(OSError):                      # дозволено ОДИН порт, не весь loopback
            socket.create_connection(('127.0.0.1', other_port), timeout=1)
        self.assertEqual(self.trip.hits, [('socket', f'127.0.0.1:{other_port}')])

    def test_is_removed_on_stop(self):
        self.trip.stop()
        self.assertEqual(urllib.request.urlopen.__module__, 'urllib.request')
        self.assertEqual(subprocess.run.__module__, 'subprocess')
        self.assertEqual(subprocess.Popen.__module__, 'subprocess')
        self.assertEqual(socket.create_connection.__module__, 'socket')


# ---------- спільне ----------

_ENV = ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE',
        'SUPABASE_URL', 'SUPABASE_KEY', 'DC_MIRRORS_DIR', 'DC_IDENTITY_NAME', 'DC_IDENTITY_EMAIL', 'GIT_AUTHOR_NAME',
        'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL')


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False)


def _read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def _isolate_env(case, tmp, legacy_file, class_level=False):
    """Власні `HOME`/`DEAI_HOME`, `DC_TASKS_FILE` = тимчасовий старий файл, особа для git-комітів.
    Повертає `(home, deai)`; відновлення оточення — у cleanup."""
    add = case.addClassCleanup if class_level else case.addCleanup
    saved = {k: os.environ.get(k) for k in _ENV}

    def restore():
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    add(restore)
    home, deai = os.path.join(tmp, 'home'), os.path.join(tmp, 'deai')
    # лог `_overview_sync` пишеться ДО `Popen`: без теки `open()` упав би й до розтяжки
    os.makedirs(os.path.join(home, '.claude', 'pipeline-feedback'))
    for k in ('DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE'):
        os.environ.pop(k, None)
    os.environ['DC_TASKS_FILE'] = legacy_file
    os.environ.update({
        'HOME': home, 'DEAI_HOME': deai, 'DC_MIRRORS_DIR': os.path.join(tmp, 'mirrors'),
        'DC_IDENTITY_NAME': 'Lead', 'DC_IDENTITY_EMAIL': 'lead@example.com',
        'GIT_AUTHOR_NAME': 'Lead', 'GIT_AUTHOR_EMAIL': 'lead@example.com',
        'GIT_COMMITTER_NAME': 'Lead', 'GIT_COMMITTER_EMAIL': 'lead@example.com'})
    return home, deai


def league_records(space_dir, deai, sid):
    """ЯВНІ записи ролей простору ЛІГА (4d-4b; було — вигаданий конфіг у корені `tasks.json`, `sbconf.write_root`): точки виходу ЛІГИ живі й
    під розтяжкою лише тут. Адреса й ключ Supabase — вигадані (`sbconf`), решта — з `liga_fixture`."""
    over = {role: {'settings': {'url': sbconf.SB_URL}, 'secrets': {'key': sbconf.SB_KEY}} for role in ('comments', 'dashboard', 'notify')}
    over['vcs'] = {'settings': {'ssh_key': '', 'host_ip': ''}}        # у старому корені ключа SSH не було: ціль іде типовим ключем, а не неіснуючим файлом
    return liga_fixture.write_records(space_dir, deai, sid, liga_fixture.ALL_ROLES, over)


def isolate_team_cache(case):
    """Модульний кеш дашборда (`serve._TEAM_CACHE`, 4c-1: словник `{id простору: запис}`, спільний на ПРОЦЕС): скинути на час
    тесту й повернути як було. Без цього тест, що кликав `team_snapshot`, лишав би запис `{rows: [], error:
    'tripwire', at: now}` усім наступним тестам процесу (вони читали б чужу «помилку мережі»)."""
    saved = {k: dict(v) for k, v in serve._TEAM_CACHE.items()}
    serve._TEAM_CACHE.clear()

    def back():
        serve._TEAM_CACHE.clear()
        serve._TEAM_CACHE.update(saved)
    case.addCleanup(back)


@contextlib.contextmanager
def unisolated(legacy_file):
    """Бойовий шлях зовнішніх функцій: `DC_TASKS_FILE` прибрано (він глушить `notify_call`,
    `team_snapshot`, `_registry_push` САМ — і без цього відмову міг би дати він, а не вимикач),
    старий файл простору підставлено через `spaces.legacy_tasks_file`. Усе — під розтяжкою."""
    saved = os.environ.pop('DC_TASKS_FILE', None)
    try:
        with mock.patch.object(spaces, 'legacy_tasks_file', return_value=legacy_file):
            yield
    finally:
        if saved is not None:
            os.environ['DC_TASKS_FILE'] = saved


def _git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo_with_remote(path):
    """Тека-репозиторій з `origin`: лише тоді `git push` у `git_autocommit` взагалі можливий."""
    os.makedirs(path, exist_ok=True)
    _git(path, 'init', '-q')
    _git(path, 'remote', 'add', 'origin', '/nonexistent')
    _write(os.path.join(path, 'a.txt'), 'x')
    return path


def _commits(path):
    return len(_git(path, 'log', '--oneline').stdout.splitlines())


class TeamCacheIsolation(unittest.TestCase):
    def test_helper_resets_for_the_test_and_restores_after(self):
        before = {'sp-1': {'at': 7.0, 'rows': [{'id': 'before'}], 'error': None, 'rowsAt': 7.0, 'who': 'legacy'}}
        outer = {k: dict(v) for k, v in serve._TEAM_CACHE.items()}

        def restore():
            serve._TEAM_CACHE.clear()
            serve._TEAM_CACHE.update(outer)
        self.addCleanup(restore)
        serve._TEAM_CACHE.clear()
        serve._TEAM_CACHE.update(before)
        probe = unittest.TestCase()
        isolate_team_cache(probe)
        self.assertEqual(serve._TEAM_CACHE, {})
        serve._TEAM_CACHE['sp-1'] = {'at': 9.0, 'rows': [], 'error': 'tripwire', 'rowsAt': None, 'who': 'legacy'}  # як лишив би `team_snapshot`
        probe.doCleanups()
        self.assertEqual(serve._TEAM_CACHE, before)


# ---------- кожна точка виходу окремою функцією ----------

class Points(unittest.TestCase):
    """Реєстр із двома просторами: `on` (інтеграції) і `off`. Функція кличеться ПІД простором
    запиту — `with spaces.request_space(…)`: так її кличуть і сервер, і CLI, і фонові потоки."""

    def setUp(self):
        self.trip = Tripwire()                   # ПЕРШИМ: далі прибираються env-запобіжники
        self.addCleanup(self.trip.stop)
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='integrations-points-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # старого файла нема (інакше `load_registry` домігрував би простір `legacy`)
        self.legacy = os.path.join(self.tmp, 'no-legacy', 'tasks.json')
        self.home, self.deai = _isolate_env(self, self.tmp, self.legacy)
        self.on_path = os.path.join(self.home, 'deai-work', 'on')
        self.off_path = os.path.join(self.home, 'deai-work', 'off')
        for p in (self.on_path, self.off_path):
            _write(os.path.join(p, 'tasks.json'), {'design_work_root': p, 'tasks': {}})
        os.makedirs(self.deai, mode=0o700)
        atomic_write_json(os.path.join(self.deai, 'spaces.json'), {
            'version': 1, 'current': 'off', 'spaces': [
                {'id': 'on', 'path': self.on_path, 'legacy': False, 'integrations': True},
                {'id': 'off', 'path': self.off_path, 'legacy': False, 'integrations': False}]})
        league_records(self.on_path, self.deai, 'on')       # простір з інтеграціями = ЛІГА: явні записи ролей
        isolate_team_cache(self)       # чужий прогін не має підсунути «свіжі» рядки (і не лишати свої)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)

    def enter_unisolated(self):
        cm = unisolated(self.legacy)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)

    def project_comments(self):
        """`ProjectComments` простору запиту — так його будують CLI й маршрут `/comments`."""
        return serve.ProjectComments(spaces.active_space())

    def test_project_pins_through_the_league_module(self):
        """Колишній `test_supabase_pins`: з 4b-2 піни ЛІГИ читає модуль `supabase-comments` (його запит іде не крізь
        `urlopen`, а крізь `socket.create_connection` власного opener-а — тож розтяжка бачить `socket`)."""
        with spaces.request_space('off'):
            with self.assertRaises(spaces.IntegrationsOff):
                self.project_comments().pins({}, 'x')
        self.assertEqual(self.trip.hits, [])
        with spaces.request_space('on'):
            with self.assertRaises(serve.deai_modules.ModuleError) as cm:        # не `IntegrationsOff` і не «пусто»
                self.project_comments().pins({}, 'x')
        self.assertNotIsInstance(cm.exception, spaces.IntegrationsOff)
        self.assertEqual(self.trip.of('socket'), [LIGA_HOST], 'питали Supabase ЛІГИ (конфіг установки), і лише його')
        self.assertEqual(self.trip.of('urlopen'), [])

    def test_notify_call(self):
        """4c-3: `notify_call` замість `teams_rpc`. Простір без інтеграцій і без модуля — `OSError` («сповіщень нема») ДО мережі;
        ЛІГА ходить у Supabase ЛІГИ вбудованим `supabase-teams` (через `socket`, а не `urlopen`)."""
        self.enter_unisolated()
        with spaces.request_space('off'):
            with self.assertRaises(OSError) as off:
                serve.notify_call('mute_state')
        self.assertEqual(str(off.exception), 'сповіщень Teams у просторі нема', 'не ізоляція, а відсутність постачальника')
        self.assertEqual(self.trip.hits, [])
        with spaces.request_space('on'):
            with self.assertRaises(serve.deai_modules.ModuleError) as cm:        # не `OSError` і не «пусто»
                serve.notify_call('mute_state')
        self.assertNotIsInstance(cm.exception, OSError)
        self.assertEqual(self.trip.of('socket'), [LIGA_HOST], 'питали Supabase ЛІГИ (конфіг установки), і лише його')
        self.assertEqual(self.trip.of('urlopen'), [])

    def test_team_snapshot(self):
        self.enter_unisolated()
        with spaces.request_space('off'):
            rows, err, rows_at = serve.team_snapshot(refresh=True)
        self.assertEqual((rows, rows_at), ([], None))
        self.assertTrue(err and isinstance(err, str))      # форма та сама, що в гілки ізоляції
        self.assertEqual(self.trip.hits, [])
        self.assertEqual(serve._TEAM_CACHE, {}, 'відмова потрапила в кеш дашборда')
        with spaces.request_space('on'):
            serve.team_snapshot(refresh=True)
        # 4c-1: читання ЛІГИ йде модулем `supabase-dashboard` (його власний opener), тож розтяжка ловить його на сокеті, а не на `urlopen`
        self.assertEqual(self.trip.of('urlopen'), [])
        self.assertEqual(self.trip.of('socket'), [LIGA_HOST], 'питали Supabase ЛІГИ (конфіг установки), і лише його')

    def test_team_snapshot_says_why_when_the_registry_is_unreadable(self):
        """Реєстр просторів, що не читається, — не «простір без інтеграцій»: причина названа окремо,
        а кеш не чіпається. Ні те, ні те не пускає запит назовні."""
        self.enter_unisolated()
        # 4c-1: постачальника ролі вирішує `deai_modules.provider` (читає реєстр через `spaces.active_space`), не `integrations_on`
        with spaces.request_space('on'), mock.patch.object(
                spaces, 'active_space', side_effect=spaces.SpacesError('spaces-unreadable', 'p')):
            rows, err, rows_at = serve.team_snapshot(refresh=True)
        self.assertEqual((rows, rows_at), ([], None))
        self.assertIn('не читається', err)
        self.assertNotIn('без інтеграцій', err)
        self.assertEqual(self.trip.hits, [])
        self.assertEqual(serve._TEAM_CACHE, {})

    def test_registry_push(self):
        self.enter_unisolated()
        fake = mock.MagicMock()
        with mock.patch.dict('sys.modules', {'registry': fake}):
            with spaces.request_space('off'):
                self.assertIs(serve._registry_push('x'), False)
            fake.push_tasks.assert_not_called()
            with spaces.request_space('on'):
                self.assertIs(serve._registry_push('x'), False)      # 4d-4c: реєстр лише для `legacy: true` (`registry_allowed`)
                fake.push_tasks.assert_not_called()
                with mock.patch.object(serve, 'registry_allowed', return_value=True):
                    serve._registry_push('x')
            fake.push_tasks.assert_called_once_with(['x'])

    def test_overview_sync(self):
        # 4c-1 (Task 6): гейт `_overview_sync` для ЛІГИ дивиться й на `DC_TASKS_FILE` (ізольований прогін не пише у спільний
        # Supabase), тож «бойовий» шлях — без нього (`enter_unisolated`, як у сусідніх точках виходу); лог — шов `OVERVIEW_LOG`
        # у тимчасовій домівці, стан «один синк на простір» — чистий.
        self.enter_unisolated()
        for patcher in (mock.patch.object(serve, 'OVERVIEW_LOG',
                                          os.path.join(self.home, '.claude', 'pipeline-feedback', 'overview-sync.log')),
                        mock.patch.dict(serve._SYNC_RUNS, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        with spaces.request_space('off'):
            serve.Handler._overview_sync(object())
        self.assertEqual(self.trip.hits, [])
        with spaces.request_space('on'), warnings.catch_warnings(record=True) as caught:
            # Тут `Popen` — розтяжка, і вона падає: відкритий лог `_overview_sync` закриває сам
            # (раніше цей тест глушив ResourceWarning — клас «ковтає збій і лишає дескриптор»).
            warnings.simplefilter('always', ResourceWarning)
            serve.Handler._overview_sync(object())
            gc.collect()
        self.assertEqual([str(w.message) for w in caught if issubclass(w.category, ResourceWarning)], [])
        self.assertEqual(len(self.trip.of('popen')), 1)
        self.assertIn('overview_push.py', self.trip.of('popen')[0])

    def test_git_autocommit_does_not_push_without_integrations(self):
        repo = _repo_with_remote(os.path.join(self.tmp, 'off-repo'))
        with spaces.request_space('off'):
            r = serve.git_autocommit(repo, 'm')
        self.assertIsNotNone(r['sha'], 'локальний коміт мусить вийти й без інтеграцій')
        self.assertIs(r['pushed'], False)
        self.assertEqual(_commits(repo), 1)
        self.assertEqual(self.trip.hits, [])

    def test_git_autocommit_pushes_with_integrations(self):
        repo = _repo_with_remote(os.path.join(self.tmp, 'on-repo'))
        with spaces.request_space('on'):
            serve.git_autocommit(repo, 'm')
        self.assertEqual(len(self.trip.of('run')), 1)
        self.assertTrue(self.trip.of('run')[0].startswith('git push'))
        # явний `push=False` сильніший за простір
        repo2 = _repo_with_remote(os.path.join(self.tmp, 'on-repo-2'))
        self.trip.hits.clear()
        with spaces.request_space('on'):
            serve.git_autocommit(repo2, 'm', push=False)
        self.assertEqual(self.trip.hits, [])

    def test_git_autocommit_asks_the_space_only_when_there_is_a_remote(self):
        """Лінива перевірка: автокоміт без `origin` (кожна нова задача, кожна правка сторінки) не
        читає реєстр і не може впасти на `SpacesError`."""
        bare = os.path.join(self.tmp, 'no-remote')
        os.makedirs(bare)
        _write(os.path.join(bare, 'a.txt'), 'x')
        with spaces.request_space('on'), \
                mock.patch.object(serve.deai_modules, 'vcs_outbound', side_effect=AssertionError('запитано')):
            r = serve.git_autocommit(bare, 'm')
        self.assertIsNotNone(r['sha'])

    def test_git_autocommit_does_not_push_when_the_registry_is_unreadable(self):
        """Коміт уже вийшов; реєстр зіпсувався посеред запиту — пушити «навмання» не можна, а
        500 після вдалого коміту — гірше за пропущений пуш."""
        repo = _repo_with_remote(os.path.join(self.tmp, 'broken-registry'))
        with spaces.request_space('on'), mock.patch.object(
                spaces, 'effective_space', side_effect=spaces.SpacesError('spaces-unreadable', 'p')):
            r = serve.git_autocommit(repo, 'm')
        self.assertIsNotNone(r['sha'])
        self.assertIs(r['pushed'], False)
        self.assertEqual(self.trip.hits, [])

    def test_origin_is_checked_before_the_kill_switch(self):
        """Чужа сторінка не мусить дізнаватись навіть про вимикач: Origin — ПЕРШИЙ, 403, а не 409.
        (Центральний `do_POST` перевіряє Origin раніше, тож через HTTP порядок усередині обробника не
        видно — звідси заглушка з тим мінімумом, що має зовнішня заглушка Handler.)"""
        class Stub:
            headers = {'Origin': 'https://evil.example'}

            def __init__(self):
                self.sent = []

            def _send_json(self, obj, status=200):
                self.sent.append((status, obj))
        for name, payload in (('_preview_password', {'password': 'abcd'}), ('_teams_mute', {})):
            with self.subTest(handler=name), spaces.request_space('off'):
                stub = Stub()
                getattr(serve.Handler, name)(stub, payload)
                self.assertEqual([st for st, _ in stub.sent], [403], stub.sent)
        self.assertEqual(self.trip.hits, [])

    def test_project_pin_resolve_through_the_league_module(self):
        """Колишній `test_patch_project_pin`: закриття піна ЛІГИ — `resolve` модуля, і простір без інтеграцій його не
        кличе (`spaces.require_integrations()` у `ProjectComments._module`)."""
        with spaces.request_space('off'):
            with self.assertRaises(spaces.IntegrationsOff):
                self.project_comments().resolve({}, 'x', 'c0ffee01', 'r', iteration=1)
        self.assertEqual(self.trip.hits, [])
        with spaces.request_space('on'):
            with self.assertRaises(serve.deai_modules.ModuleError) as cm:
                self.project_comments().resolve({}, 'x', 'c0ffee01', 'r', iteration=1)
        self.assertNotIsInstance(cm.exception, spaces.IntegrationsOff)
        self.assertEqual(self.trip.of('socket'), [LIGA_HOST], 'питали Supabase ЛІГИ (конфіг установки), і лише його')
        self.assertEqual(self.trip.of('urlopen'), [])

    def test_task_new_with_gitlab_clones_the_mirror_in_the_liga_space(self):
        """Було `…does_not_touch_the_gitlab_mirror` (друга замкова перевірка `require_integrations` у `task_new`). 4d-4c: замок
        прибрано — `gitlab` для простору без схеми ЛІГИ відхиляє маршрут (400 `gitlab-needs-vcs-scheme`, `test_spaces_serve.TaskNew`);
        лишилась позитивна половина: у просторі, що ходить назовні, `task_new` справді клонує дзеркало."""
        gl = {'repo': 'git@gitlab.example.test:g/r.git', 'path': 'mockup/g1'}
        with spaces.request_space('on'), mock.patch.dict('sys.modules', {'registry': mock.MagicMock()}):
            serve.task_new(serve.load_tasks(), 'g1', gitlab=gl, root=self.on_path)
        self.assertEqual(len(self.trip.of('run')), 1)       # `git clone` дзеркала
        self.assertTrue(self.trip.of('run')[0].startswith('git clone'))


# ---------- сервер у процесі ----------

class World(unittest.TestCase):
    """Сервер у процесі й два простори: старий (`a`, інтеграції: маркер `registry`) та `P` (`x`,
    БЕЗ інтеграцій), поточний — `P`. Обидві задачі мають GitLab-маппінг у файлі: «нема GitLab»
    у `P` — наслідок вимикача, а не відсутності налаштувань."""

    @classmethod
    def setUpClass(cls):
        cls.trip = Tripwire()                    # ПЕРШИМ
        cls.addClassCleanup(cls.trip.stop)
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix='integrations-routes-'))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        cls.legacy_file = os.path.join(cls.tmp, 'legacy', 'tasks.json')
        cls.home, cls.deai = _isolate_env(cls, cls.tmp, cls.legacy_file, class_level=True)
        spaces.clear_request_space()

        work = os.path.join(cls.tmp, 'work')
        cls.a_dir = os.path.join(work, 'a')
        cls._task_dir(cls.a_dir, 'a', published=False)
        _write(cls.legacy_file, {'current': 'a', 'design_work_root': work, 'registry': {},
                                 'tasks': {'a': {'title': 'Альфа', 'dir': cls.a_dir, 'profile': 'tool',
                                                 'gitlab': {'repo': 'git@gitlab.example.test:g/a.git',
                                                            'path': 'mockup/a'}}}})
        cls.p_path = os.path.join(cls.home, 'deai-work', 'p')
        cls.p_id = spaces.create_space('P', 'space-2', cls.p_path)
        cls.legacy_id = next(s['id'] for s in spaces.read_registry()['spaces'] if s.get('legacy'))
        league_records(next(s['path'] for s in spaces.read_registry()['spaces'] if s['id'] == cls.legacy_id), cls.deai, cls.legacy_id)
        cls.x_dir = os.path.join(cls.p_path, 'x')
        # ітерація ПОЗНАЧЕНА до публікації: без вимикача `/api/publish` пішов би збирати й деплоїти
        cls._task_dir(cls.x_dir, 'x', published=True)
        cls.p_file = os.path.join(cls.p_path, 'tasks.json')
        _write(cls.p_file, {'design_work_root': cls.p_path, 'current': 'x', 'tasks': {
            'x': {'title': 'Ікс', 'dir': cls.x_dir, 'profile': None,
                  'gitlab': {'repo': 'git@gitlab.example.test:g/x.git', 'path': 'mockup/x'}}}})
        flags = {s['id']: s.get('integrations') for s in spaces.read_registry()['spaces']}
        assert flags == {cls.legacy_id: True, cls.p_id: False}, flags

        cls.httpd = serve.make_server(0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.httpd.server_close)
        cls.addClassCleanup(cls.httpd.shutdown)
        cls.base = f'http://127.0.0.1:{cls.port}'
        cls.trip.allow_ports.add(cls.port)     # лише порт ЦЬОГО сервера: решта loopback — «вихід»

    @staticmethod
    def _task_dir(path, marker, published):
        _write(os.path.join(path, 'iterations.json'),
               {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'start',
                                'published': published}], 'publish_url': None})
        _write(os.path.join(path, 'iterations', 'it1', 'index.html'),
               f'<!DOCTYPE html><html><body><h1>{marker}</h1></body></html>')

    def setUp(self):
        # Бойовий шлях зовнішніх функцій (див. `unisolated`): сервер у процесі читає оточення на
        # кожен запит, тож прибрана змінна діє й на нього.
        cm = unisolated(self.legacy_file)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        isolate_team_cache(self)                 # `tasks-overview` кличе `team_snapshot` і кешує
        spaces.clear_request_space()
        spaces.switch_space(self.p_id)           # поточний простір — БЕЗ інтеграцій
        self.trip.hits.clear()

    def tearDown(self):
        spaces.clear_request_space()

    # ---------- HTTP ----------

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8')

    def jget(self, path, headers=None):
        st, body = self.get(path, headers)
        return st, json.loads(body)

    def post(self, path, payload, headers=None):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(), method='POST',
            headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8')

    def jpost(self, path, payload, headers=None):
        st, body = self.post(path, payload, headers)
        return st, json.loads(body)

    def restore_bytes(self, path):
        before = _bytes(path)

        def back():
            with open(path, 'wb') as f:
                f.write(before)
        self.addCleanup(back)

    def assert_off(self, st, body):
        self.assertEqual(st, 409, body)
        self.assertEqual((body['ok'], body['code']), (False, 'integrations-off'))
        self.assertTrue(body['error'])

    def assert_not_off(self, st, body):
        self.assertNotEqual(st, 409, body)
        self.assertNotEqual(body.get('code') if isinstance(body, dict) else None, 'integrations-off')


class Routes(World):
    A = {'X-Canvas-Task': 'a'}               # контроль: той самий маршрут у просторі з інтеграціями

    def test_comments_are_refused_before_supabase(self):
        self.assert_off(*self.jget('/comments?it=it1'))
        self.assertEqual(self.trip.hits, [])
        st, body = self.jget('/comments?it=it1', self.A)
        self.assertEqual((st, body['comments']), (200, []))
        self.assertTrue(body['error'], 'контроль: запит мусив дійти до розтяжки')
        self.assertEqual(self.trip.of('socket'), [LIGA_HOST], 'модуль ходить крізь `socket.create_connection` у Supabase ЛІГИ')

    def test_comment_config_project_is_refused_local_is_not(self):
        self.assert_off(*self.jget('/api/comment-config?ch=project&it=it1'))
        st, body = self.jget('/api/comment-config?ch=local&it=it1')
        self.assertEqual((st, body['ch']), (200, 'local'))
        self.assertNotIn('sbUrl', body)
        self.assertEqual(self.trip.hits, [])
        st, body = self.jget('/api/comment-config?ch=project&it=it1', self.A)
        self.assertEqual((st, body['ch']), (200, 'project'))
        self.assertEqual(body['module'], 'supabase-comments')        # 4b-2: ЛІГА — вбудований модуль (було: `sbUrl` у тілі)
        self.assertEqual(body['config']['url'], sbconf.SB_URL)

    def test_commented_project_is_downgraded_to_local_without_audience_tabs(self):
        st, html = self.get('/commented?it=it1&ch=project')
        self.assertEqual(st, 200)
        self.assertNotIn('supabase', html.lower())
        self.assertNotIn('audiences:', html, 'без інтеграцій вкладок аудиторій нема зовсім')
        self.assertIn('local-comments', html)
        self.assertEqual(self.trip.hits, [])
        # і чистий локальний режим без вкладок «Клод/Команда»
        st, html = self.get('/commented?it=it1&ch=local')
        self.assertEqual(st, 200)
        self.assertNotIn('audiences:', html)
        self.assertIn('local-comments', html)
        # контроль: поточний простір — з інтеграціями
        spaces.switch_space(self.legacy_id)
        st, html = self.get('/commented?it=it1&ch=project')
        self.assertEqual(st, 200)
        self.assertIn('supabase', html.lower())
        self.assertIn('audiences:', html)
        st, html = self.get('/commented?it=it1&ch=local')
        self.assertIn('audiences:', html)

    def test_teams_mute_is_refused_both_ways(self):
        """4c-3: відмова — `notify-off` (немає постачальника ролі), а не `integrations-off`; решта — як була."""
        for st, body in (self.jget('/api/teams-mute'), self.jpost('/api/teams-mute', {}),
                         self.jpost('/api/teams-mute', {'muted': True})):
            self.assertEqual(st, 409, body)
            self.assertEqual((body['ok'], body['code']), (False, 'notify-off'))
            self.assertTrue(body['error'])
        self.assertEqual(self.trip.hits, [])
        self.assert_not_off(*self.jget('/api/teams-mute', self.A))
        self.assert_not_off(*self.jpost('/api/teams-mute', {'muted': True}, self.A))
        # Origin стоїть ПЕРЕД вимикачем: чужа сторінка не дізнається навіть про нього
        st, body = self.jpost('/api/teams-mute', {}, {'Origin': 'https://evil.example'})
        self.assertEqual(st, 403)

    def test_publish_works_locally_without_integrations_and_preview_password_is_still_refused(self):
        # Етап 2а: у просторі без інтеграцій публікує неявний модуль `static-publish` — ЛОКАЛЬНО (тека поза
        # простором, жодної мережі, жодного Vercel/дашборда); раніше тут була 409 `integrations-off`. Пароль
        # превʼю — гейт ЛІГА-превʼю, а в модуля публікації свій (секрет), тож цей маршрут лишається закритим.
        self.restore_bytes(self.p_file)
        self.restore_bytes(os.path.join(self.x_dir, 'iterations.json'))
        self.addCleanup(shutil.rmtree, os.path.join(self.x_dir, 'publish'), True)
        self.addCleanup(shutil.rmtree, os.path.join(self.home, 'deai-published'), True)
        before = _bytes(self.p_file)
        st, body = self.jpost('/api/publish', {})
        self.assertEqual(st, 200, body)
        want = os.path.join(self.home, 'deai-published', self.p_id, 'x')
        self.assertEqual(body['local'], {'path': want, 'url': f'/published/{self.p_id}/x/'})
        self.assertTrue(os.path.isfile(os.path.join(want, 'index.html')))
        self.assertEqual(_read(os.path.join(self.x_dir, 'iterations.json'))['publish_local']['path'], want)
        self.assertEqual(self.trip.hits, [], 'публікація модулем вийшла назовні')
        self.assert_off(*self.jpost('/api/preview-password', {'password': 'abcd'}))
        self.assertEqual(self.trip.hits, [])
        self.assertEqual(_bytes(self.p_file), before, 'пароль превʼю записано в простір без інтеграцій')
        # без позначених ітерацій — те саме 400, що й у ЛІГА, і збірки нема
        _write(os.path.join(self.x_dir, 'iterations.json'),
               {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'start', 'published': False}],
                'publish_url': None})
        shutil.rmtree(os.path.join(self.x_dir, 'publish'), True)
        st, body = self.post('/api/publish', {})
        self.assertEqual(st, 400, body)
        self.assertFalse(os.path.exists(os.path.join(self.x_dir, 'publish')), 'збірка publish/ почалась до відмови')
        self.assertEqual(self.trip.hits, [])
        # контроль: у просторі з інтеграціями публікація доходить далі (тут — до «нема що
        # публікувати», бо ітерація `a` не позначена), а пароль записується
        self.restore_bytes(self.legacy_file)
        st, body = self.post('/api/publish', {}, self.A)
        self.assertEqual(st, 400, body)
        st, body = self.jpost('/api/preview-password', {'password': 'abcd'}, self.A)
        self.assertEqual(st, 200, body)
        self.assertEqual(_read(self.legacy_file)['tasks']['a']['preview_password'], 'abcd')

    def test_gitlab_routes_answer_as_for_a_task_without_gitlab(self):
        # `x` має маппінг GitLab у файлі, і все ж: статус — «не налаштовано» (UI опитує його на
        # кожному старті, тож не 409), синк і підтягування — те саме 400, що для задачі без GitLab
        self.assertEqual(self.jget('/api/gitlab-status?it=it1'), (200, {'configured': False}))
        st, body = self.post('/api/gitlab-sync', {'it': 'it1'})
        self.assertEqual(st, 400)
        self.assertIn('no gitlab configured', body)
        st, body = self.post('/api/gitlab-pull', {})
        self.assertEqual(st, 400)
        self.assertIn('no gitlab configured', body)
        self.assertEqual(self.jpost('/api/autosync', {}),
                         (200, {'ok': True, 'changed': False, 'reason': 'no-gitlab'}))
        self.assertEqual(self.trip.hits, [])
        # контроль: ті самі маршрути в просторі з інтеграціями б'ють у git (розтяжка ловить)
        st, body = self.jget('/api/gitlab-status?it=it1', self.A)
        self.assertEqual((st, body['configured']), (200, True))
        self.assertTrue(body['error'])
        self.assertTrue(self.trip.of('run')[-1].startswith('git clone'))
        self.trip.hits.clear()
        st, body = self.jpost('/api/gitlab-sync', {'it': 'it1'}, self.A)
        self.assertEqual((st, body['ok']), (200, False))
        self.assertTrue(self.trip.of('run'))
        self.trip.hits.clear()
        st, body = self.jpost('/api/gitlab-pull', {}, self.A)
        self.assertEqual((st, body['ok']), (200, False))
        self.assertTrue(self.trip.of('run'))
        self.trip.hits.clear()
        self.restore_bytes(self.legacy_file)
        st, body = self.jpost('/api/autosync', {}, self.A)
        self.assertNotEqual(body.get('reason'), 'no-gitlab', body)

    def test_tasks_overview_has_no_team_and_makes_no_request(self):
        st, body = self.jget('/api/tasks-overview?refresh=1')
        self.assertEqual(st, 200)
        self.assertIsNone(body['team'])
        self.assertEqual([m['id'] for m in body['mine']], ['x'])
        self.assertEqual(body['space']['id'], self.p_id)
        self.assertEqual(self.trip.hits, [])
        # контроль: у просторі з інтеграціями `team` є й запит іде (розтяжка його ловить)
        st, body = self.jget('/api/tasks-overview?refresh=1', self.A)
        self.assertEqual(st, 200)
        self.assertIsInstance(body['team'], dict)
        self.assertTrue(body['team']['error'])
        # 4c-1: рядки ЛІГИ читає модуль `supabase-dashboard` — його запит видно на сокеті, а не на `urlopen`
        self.assertEqual(self.trip.of('socket'), [LIGA_HOST])
        self.assertEqual(self.trip.of('urlopen'), [])

    def test_the_world_isolates_the_dashboard_cache_between_tests(self):
        """`tasks-overview` кличе `team_snapshot`, а той кешує — і кеш спільний на процес. Повторний
        вхід у `World.setUp` посеред тесту = межа між двома тестами: кеш, залишений попереднім,
        скинутий (а після тесту повернеться як було)."""
        serve._TEAM_CACHE['x'] = {'rows': [], 'error': 'tripwire', 'at': 9.0, 'rowsAt': None, 'who': 'legacy'}  # як лишив би попередній тест
        World.setUp(self)
        self.assertEqual(serve._TEAM_CACHE, {})

    def test_unreadable_registry_is_503_and_nothing_leaves(self):
        """Вікно «відкрито при битому реєстрі» закрите в Task 2: API-запит без простору не
        виконується. Тут лише свідок із розтяжкою."""
        reg = os.path.join(self.deai, 'spaces.json')
        self.restore_bytes(reg)
        _write(reg, '{')
        for path in ('/comments?it=it1', '/api/comment-config?ch=project&it=it1',
                     '/api/tasks-overview', '/api/teams-mute'):
            with self.subTest(path=path):
                st, body = self.jget(path)
                self.assertEqual(st, 503, body)
                self.assertEqual(body['code'], 'spaces-unreadable')
        st, body = self.jpost('/api/publish', {})
        self.assertEqual((st, body['code']), (503, 'spaces-unreadable'))
        self.assertEqual(self.trip.hits, [])

    def test_task_new_into_a_space_without_integrations_neither_registers_nor_pushes(self):
        fake = mock.MagicMock()
        fake.push_tasks.return_value = mock.MagicMock(refused={})
        self.restore_bytes(self.p_file)
        self.restore_bytes(self.legacy_file)
        # `origin` у теці ЗАДАЧІ: інакше `git push` у `git_autocommit` не зустрівся б і так
        n1 = _repo_with_remote(os.path.join(self.p_path, 'n1'))
        with mock.patch.dict('sys.modules', {'registry': fake}):
            st, body = self.jpost('/api/task-new', {'id': 'n1', 'title': 'Н', 'space': self.p_id})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['id'], body['registered']), ('n1', False))
        fake.push_tasks.assert_not_called()
        self.assertEqual(self.trip.hits, [])
        self.assertGreaterEqual(_commits(n1), 1, 'локальний коміт мусив вийти')
        # контроль: те саме в просторі з інтеграціями — реєстр і `git push` дістають виклик
        n2 = _repo_with_remote(os.path.join(self.tmp, 'work', 'n2'))
        fake2 = mock.MagicMock()
        fake2.push_tasks.return_value = mock.MagicMock(refused={})
        with mock.patch.dict('sys.modules', {'registry': fake2}):
            st, body = self.jpost('/api/task-new', {'id': 'n2', 'title': 'Н2', 'space': self.legacy_id,
                                                    'profile': 'tool'})
        self.assertEqual(st, 200, body)
        self.assertIs(body['registered'], True)
        fake2.push_tasks.assert_called_once_with(['n2'])
        self.assertTrue([c for c in self.trip.of('run') if c.startswith('git push')])
        self.assertGreaterEqual(_commits(n2), 1)


# ---------- CLI ----------

def _run(fn, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = fn(argv)
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class Cli(World):
    """`bin/state.py` і `bin/inbox.py` у просторі без інтеграцій. `server` тут не потрібен, але
    задачі й реєстр ті самі, що в маршрутів."""

    def setUp(self):
        super().setUp()
        self.staleness = mock.Mock(return_value={'state': 'fresh', 'age_h': 0.5, 'hint': ''})
        for owner, name, repl in ((state.registry, 'staleness', self.staleness),
                                  # інакше питав би живий канвас на 8765
                                  (state, 'find_canvas_port', lambda *a, **k: 8766)):
            p = mock.patch.object(owner, name, repl)
            p.start()
            self.addCleanup(p.stop)

    def test_state_in_a_space_without_integrations_prints_no_registry_and_asks_nothing(self):
        rc, out, err = _run(state.main, ['--task', 'x'])
        self.assertEqual(rc, 0, err)
        self.assertIn('«Ікс» (x)', out)
        self.assertNotIn('Реєстр', out)
        self.staleness.assert_not_called()
        # `x` має маппінг GitLab у файлі, але інтеграцій нема — як для задачі без GitLab
        self.assertIn('GitLab: не налаштований для задачі', out)
        # командних коментарів у такому просторі нема — «нема», а не «+ 0 проєктних» (нуль читався б
        # як «питали, і тихо»)
        self.assertIn('локальних (мені), проєктних нема', out)
        self.assertNotRegex(out, r'\+ \d+ проєктних')
        self.assertEqual(self.trip.hits, [])

    def test_state_control_in_a_space_with_integrations(self):
        rc, out, err = _run(state.main, ['--task', 'a'])
        self.assertEqual(rc, 0, err)
        self.assertIn('Реєстр: ✅', out)
        # 4b-2: Supabase ЛІГИ, що не відповів (тут — розтяжка), — «не дістати (<код>)», а не тихий «+ 0 проєктних»
        self.assertIn('проєктні: не дістати (module-error)', out)
        self.assertNotIn('проєктних нема', out)
        self.staleness.assert_called_once()
        self.assertNotIn('GitLab: не налаштований', out)
        self.assertTrue([c for c in self.trip.of('run') if c.startswith('git clone')],
                        'контроль: статус GitLab мусив дійти до розтяжки')
        self.assertEqual(self.trip.of('socket')[:1], [LIGA_HOST], 'контроль: проєктні піни мусили дійти до розтяжки')

    def test_state_team_comments_in_a_space_without_integrations_is_none_without_a_request(self):
        """Колишній `_open_pins`: у просторі БЕЗ інтеграцій лічильник проєктних — «нема» і без жодного запиту."""
        with spaces.request_space(self.legacy_id):           # контроль: простір з інтеграціями питає (і не дістає)
            self.assertEqual(state._team_comments({}, 'a'), (0, ', проєктні: не дістати (module-error)'))
        self.assertTrue(self.trip.of('socket'))
        self.trip.hits.clear()
        with spaces.request_space(self.p_id):
            self.assertEqual(state._team_comments({}, 'x'), (0, ', проєктних нема'))
            self.assertEqual(state._registry_line({'tasks': {}}), '')
        self.assertEqual(self.trip.hits, [])
        self.staleness.assert_not_called()

    def test_inbox_says_there_are_no_team_comments_in_this_space(self):
        rc, out, err = _run(inbox.main, ['--task', 'x'])
        self.assertEqual(rc, 0, err)
        self.assertIn('командних коментарів у цьому просторі нема', out)
        self.assertNotIn('не дістати', out)
        self.assertEqual(self.trip.hits, [])
        # контроль: у просторі з інтеграціями проєктні піни питаються (і недоступні)
        rc, out, err = _run(inbox.main, ['--task', 'a'])
        self.assertEqual(rc, 0, err)
        self.assertNotIn('командних коментарів у цьому просторі нема', out)
        self.assertIn('не дістати', out)
        self.assertTrue(self.trip.of('socket'))

    def test_inbox_resolve_searches_only_local_pins_without_integrations(self):
        """Проєктних пінів у просторі без інтеграцій нема: пошук лишається локальним, і відповідь —
        чесне «не знайдено», а не «проєкт недоступний (integrations-off)». Закрити проєктний пін
        звідси неможливо ще й тому, що `ProjectComments.resolve` закритий сам (див. `Points`)."""
        rc, out, err = _run(inbox.main, ['--task', 'x', 'resolve', 'abcdef12', '--reason', 'r'])
        self.assertEqual(rc, 1)
        self.assertIn('не знайдено серед пінів поточної задачі', out)
        self.assertNotIn('integrations-off', out)
        self.assertEqual(self.trip.hits, [])
        # контроль: у просторі з інтеграціями проєкт питається, і його недоступність — не «не знайдено»
        rc, out, err = _run(inbox.main, ['--task', 'a', 'resolve', 'abcdef12', '--reason', 'r'])
        self.assertEqual(rc, 1)
        self.assertIn('проєкт недоступний', out)
        self.assertTrue(self.trip.of('socket'))


if __name__ == '__main__':
    unittest.main()
