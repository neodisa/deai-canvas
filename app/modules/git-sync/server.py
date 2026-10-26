"""Вбудований модуль `git-sync` (роль `vcs`, етап 4a): ітерації задачі ↔ будь-який git-репозиторій.

Модуль — ТРАНСПОРТ: дзеркало (локальний клон віддаленого репо), fetch, «відстає/попереду», заміна теки `<path>` вмістом,
який підготувало ядро, коміт, push без force, pull --ff-only, копіювання `<path>` назовні, адреса історії у вебі. Про
ітерації, авторство й `iterations.json` модуль не знає нічого — це ядро (`serve.py`, спека 4a, «Межа»).

Виконується ядром через `exec`: лише stdlib, без `serve`/`deai_modules`. Помилки — `ctx['ModuleError']` з кодами
`vcs-offline`/`vcs-auth`/`vcs-bad-target`/`vcs-busy`/`vcs-error` (вони в `STATUS` ядра); рукописний `ctx` без класу —
`RuntimeError` із кодом у тексті.

Ціль (`target`) дає ядро: `{repo, path, branch, task?, ssh_key?, host_ip?}`. `ssh_key`/`host_ip` цілі перемагають
налаштування модуля; порожній рядок — «не задано». Перевірка (`validate`) — до БУДЬ-ЯКОГО виклику git і без нього.

Дзеркало: `<cache_dir>/mirrors/<host>/<шлях>`; `ctx['mirror_flat']` (лише неявний постачальник простору ЛІГА) —
`<cache_dir>/<slug>` за правилом 0.7.0, щоб старі клони не перегортались. Одна операція на дзеркало: `flock` на
`<дзеркало>.lock` (між процесами — `bin/state.py` питає статус окремим процесом; модуль ще й перевантажується `exec`-ом).

Команду ssh модуль складає лише тоді, коли сам щось додає (`ssh_key`, повтор через `host_ip`): основа — `GIT_SSH_COMMAND`
оточення, інакше `ssh`. Інакше git бере ssh людини (`core.sshCommand`, `~/.ssh/config`) сам — модуль його не перекриває.
"""
import ipaddress
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlsplit

try:
    import fcntl
except ImportError:                          # Windows
    fcntl = None
    import msvcrt

#: Тайм-аути git (секунди): як у 0.7.0 — звичайна операція, клон, перевірка на «Підключенні» (каркас чекає `check` 5 с).
GIT_TIMEOUT = 120
CLONE_TIMEOUT = 180
CHECK_GIT_TIMEOUT = 4
#: Скільки `push`/`pull` чекають на зайняте дзеркало; `status` не чекає (`vcs-busy`).
LOCK_WAIT = 60
LOCK_POLL = 0.2
MAX_MSG = 300
ALLOWED_SCHEMES = ('ssh://', 'https://', 'file://')
_RESOLVER_FAIL = 'could not resolve hostname'
_AUTH_MARKS = ('permission denied', 'authentication failed', 'could not read username',
               'could not read password', 'host key verification failed')
_OFFLINE_MARKS = ('could not resolve hostname', 'could not resolve host', 'connection timed out',
                  'operation timed out', 'network is unreachable', 'no route to host', 'connection refused')
_NO_BRANCH_MARKS = ('not found in upstream', "couldn't find remote ref", 'could not find remote ref')
_SCP = re.compile(r'(?:([^@/:\s]+)@)?([^/:\s]+):(.+)')
_NAME = re.compile(r'[A-Za-z0-9._-]+')          # хост і користувач scp-адреси: жодних `; $ ( ) & | < >` (див. `_Git._ssh`)
_PASSWORD = re.compile(r'(://[^/@:\s]*):[^/@\s]*@')
_BAD_BRANCH_CHARS = set(' ~^:?*[\\')
_BAD_PATH_CHARS = set('*?[\\')


def _err(ctx, code, message=''):
    text = _mask(str(message))[:MAX_MSG]
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    return cls(code, message=text) if cls is not None else RuntimeError(f'{code}: {text}')


def _mask(text):
    """Пароль з адреси (`://user:pass@`) ніколи не йде в текст: такі адреси відхиляє `validate`, але stderr git — чужий текст."""
    return _PASSWORD.sub(r'\1:***@', text)


def _empty(v):
    return not isinstance(v, str) or not v.strip()


def _ctl(s):
    return any(ord(c) < 32 or c == '\x7f' for c in s)


def _slug(s):
    return re.sub(r'[^\w.-]+', '-', s).strip('-')


def _split_repo(repo):
    """(host, шлях) адреси. Локальний шлях і `file://` — хост `local`; `ssh://` з портом — `host:port`."""
    if repo.startswith(ALLOWED_SCHEMES):
        u = urlsplit(repo)
        if u.scheme == 'file':
            return 'local', u.path
        return (u.hostname or '') + (f':{u.port}' if u.port else ''), u.path
    m = _SCP.fullmatch(repo)
    if m and not os.path.isabs(repo):
        return m.group(2), m.group(3)
    return 'local', repo


def _repo_why(repo):
    if _empty(repo) or repo != repo.strip() or _ctl(repo) or any(c.isspace() for c in repo):
        return 'repo: empty or contains spaces or control characters'
    if repo.startswith('-'):
        return 'repo: must not start with "-"'
    if '::' in repo:
        return 'repo: transport helpers (ext::, fd::) are not allowed'
    if repo.startswith(ALLOWED_SCHEMES):
        try:
            u = urlsplit(repo)
            u.port                              # поганий порт кидає ValueError — це й є перевірка
        except ValueError:
            return 'repo: bad address'
        if u.scheme == 'file':
            return None if u.netloc in ('', 'localhost') and u.path.startswith('/') else \
                'repo: file:// needs an absolute local path'
        if not u.hostname or u.hostname.startswith('-'):
            return 'repo: bad host'
        if u.password is not None:
            return 'repo: a password in the address is not accepted — keep credentials in git (credential helper)'
        return None
    if '://' in repo:
        return 'repo: only ssh://, https:// and file:// addresses'
    if os.path.isabs(repo):
        return None
    m = _SCP.fullmatch(repo)
    if (m and _NAME.fullmatch(m.group(2)) and not m.group(2).startswith('-')
            and (m.group(1) is None or _NAME.fullmatch(m.group(1))) and not m.group(3).startswith('-')):
        return None
    return 'repo: use ssh://, https://, file://, user@host:path or an absolute local path'


def _branch_why(b):
    """Правила `git check-ref-format` для `refs/heads/<b>` — у Python, без git (`--branch` розгортає `@{-N}`)."""
    if _empty(b) or b.startswith('-') or b == '@' or _ctl(b) or any(c in _BAD_BRANCH_CHARS for c in b):
        return 'branch: not a valid branch name'
    if '..' in b or '@{' in b or '//' in b or b.startswith('/') or b.endswith(('/', '.')):
        return 'branch: not a valid branch name'
    if any(c.startswith('.') or c.endswith('.lock') for c in b.split('/')):
        return 'branch: not a valid branch name'
    return None


def _path_why(p, what='path'):
    """`p` — уже без `/` по краях. Сегменти `.`/`..`/порожні, магія pathspec, глоби й `.git` (будь-який регістр) — ні."""
    if not p or p.startswith(('-', ':')) or _ctl(p) or any(c in _BAD_PATH_CHARS for c in p):
        return f'{what}: not a valid folder in the repository'
    if any(seg in ('', '.', '..') or seg.lower() == '.git' for seg in p.split('/')):
        return f'{what}: not a valid folder in the repository'
    return None


def _pick(target, settings, key):
    v = target.get(key)
    if _empty(v):
        v = settings.get(key)
    return None if _empty(v) else v.strip()


def validate(ctx, target):
    """Нормалізована ціль `{repo, path, branch, ssh_key, host_ip}` або `vcs-bad-target`. Жодного виклику git."""
    if not isinstance(target, dict):
        raise _err(ctx, 'vcs-bad-target', 'target must be an object')
    settings = (ctx.get('settings') if isinstance(ctx, dict) else None) or {}
    repo = target.get('repo')
    branch = target.get('branch') if not _empty(target.get('branch')) else 'main'
    path = target.get('path').strip().strip('/') if isinstance(target.get('path'), str) else ''
    why = _repo_why(repo) or _branch_why(branch) or _path_why(path)
    key, ip = _pick(target, settings, 'ssh_key'), _pick(target, settings, 'host_ip')
    if not why and key is not None:
        key = os.path.expanduser(key)
        if not (os.path.isabs(key) and os.path.isfile(key)):
            why = 'ssh_key: not an existing file (use an absolute path or ~)'
    if not why and ip is not None:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            why = 'host_ip: not an IP address'
    if why:
        raise _err(ctx, 'vcs-bad-target', why)
    return {'repo': repo, 'path': path, 'branch': branch.strip(), 'ssh_key': key, 'host_ip': ip}


def _mirror(ctx, t):
    base = ctx.get('cache_dir') if isinstance(ctx, dict) else None
    if _empty(base):
        raise _err(ctx, 'vcs-error', 'no cache_dir in ctx')
    if ctx.get('mirror_flat'):
        parts = [_slug(t['repo'].split(':')[-1])]             # правило `_mirror_dir` 0.7.0: старі клони ЛІГИ
    else:
        host, rpath = _split_repo(t['repo'])
        parts = ['mirrors', _slug(host), _slug(rpath)]
    if any(p in ('', '.', '..') for p in parts):
        raise _err(ctx, 'vcs-bad-target', 'repo: cannot name a mirror folder for this address')
    return os.path.join(base, *parts)


def mirror_dir(ctx, target):
    """Тека дзеркала цілі (діагностика й тести ядра). Нічого не створює."""
    return _mirror(ctx, validate(ctx, target))


class _Git:
    """git для однієї цілі: оточення, ssh, ОДИН повтор через `host_ip` на збої резолвера, тайм-аут → `vcs-offline`."""

    def __init__(self, ctx, t, connect_timeout=None):
        self.ctx, self.t, self.connect_timeout = ctx, t, connect_timeout

    def _ssh(self, alias):
        key = self.t.get('ssh_key')
        if not key and not alias:
            return None
        parts = [os.environ.get('GIT_SSH_COMMAND') or 'ssh', '-o BatchMode=yes']
        if self.connect_timeout:
            parts.append(f'-o ConnectTimeout={int(self.connect_timeout)}')
        if key:
            parts += [f'-i {shlex.quote(key)}', '-o IdentitiesOnly=yes', '-o StrictHostKeyChecking=accept-new']
        if alias:
            # Ключ хоста має збігтися з тим, що вже в known_hosts — інакше повтор упреться в перевірку ключа.
            parts.append(f'-o HostKeyAlias={shlex.quote(alias)}')     # git виконує GIT_SSH_COMMAND через shell
        return ' '.join(parts)

    def _env(self, alias=None, literal=True):
        env = dict(os.environ)
        env['GIT_TERMINAL_PROMPT'] = '0'
        env['GIT_ALLOW_PROTOCOL'] = 'ssh:https:file'
        if literal:
            env['GIT_LITERAL_PATHSPECS'] = '1'
        else:
            env.pop('GIT_LITERAL_PATHSPECS', None)
        ssh = self._ssh(alias)
        if ssh:
            env['GIT_SSH_COMMAND'] = ssh
        return env

    def _once(self, args, cwd, timeout, ip, literal):
        pre, alias = [], None
        if ip:
            m = _SCP.fullmatch(self.t['repo'])
            user = f'{m.group(1)}@' if m.group(1) else ''
            addr = f'[{ip}]' if ':' in ip else ip
            # `url.…insteadOf`, а не правка аргументу: у fetch/push адреса — `origin`, не в рядку команди.
            pre = ['-c', f'url.{user}{addr}:.insteadOf={user}{m.group(2)}:']
            alias = m.group(2)
        try:
            return subprocess.run(['git', *pre, *args], cwd=cwd, env=self._env(alias, literal),
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise _err(self.ctx, 'vcs-offline', f'git {args[0]}: no answer in {timeout} s') from None

    def run(self, args, cwd, timeout=GIT_TIMEOUT, literal=True):
        r = self._once(args, cwd, timeout, None, literal)
        ip = self.t.get('host_ip')
        if (r.returncode != 0 and ip and _RESOLVER_FAIL in (r.stderr or '').lower()
                and _SCP.fullmatch(self.t['repo']) and not self.t['repo'].startswith(ALLOWED_SCHEMES)
                and not os.path.isabs(self.t['repo'])):
            return self._once(args, cwd, timeout, ip, literal)
        return r

    def code_of(self, r):
        low = (r.stderr or r.stdout or '').lower()
        if any(m in low for m in _AUTH_MARKS):
            return 'vcs-auth'
        if any(m in low for m in _OFFLINE_MARKS):
            return 'vcs-offline'
        if 'index.lock' in low:
            return 'vcs-busy'
        return 'vcs-error'

    def fail(self, what, r, tail='', keep=300):
        """Відмова git → `ModuleError`. Пароль маскується ДО обрізання (різ посередині адреси не лишає його шматка),
        а обрізається ПОЧАТОК stderr: головне git пише останнім рядком, а підказка `tail` лишається цілою."""
        head = f'{what} failed: '
        err = _mask(r.stderr or r.stdout or '')
        room = max(0, min(keep, MAX_MSG - len(head) - len(tail)))
        return _err(self.ctx, self.code_of(r), head + (err[-room:] if room else '') + tail)

    def must(self, args, cwd, what, timeout=GIT_TIMEOUT, keep=300):
        r = self.run(args, cwd, timeout)
        if r.returncode != 0:
            raise self.fail(what, r, keep=keep)
        return r


def _try_lock(fh):
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)


def _unlock(fh):
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    else:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


class _Lock:
    """Одна операція на дзеркало, між процесами й потоками: `flock` на `<дзеркало>.lock` (окремий `open` — окремий опис
    файла, тож потоки одного процесу теж виключають один одного). `wait=0` — одна спроба."""

    def __init__(self, ctx, md, wait):
        self.ctx, self.path, self.wait, self.fh = ctx, md + '.lock', wait, None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        self.fh = open(self.path, 'a+')
        deadline = time.monotonic() + self.wait
        while True:
            try:
                _try_lock(self.fh)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    self.fh.close()
                    raise _err(self.ctx, 'vcs-busy', 'the mirror is busy with another operation') from None
                time.sleep(LOCK_POLL)

    def __exit__(self, *exc):
        try:
            _unlock(self.fh)
        finally:
            self.fh.close()
        return False


def check(ctx):
    """Для «Підключення»: є типовий `repo` → `ls-remote` з межею `CHECK_GIT_TIMEOUT` (каркас чекає 5 с). Звичайні відмови —
    `{"ok": false, "error": <код>, "detail": …}`, не виняток."""
    s = (ctx.get('settings') if isinstance(ctx, dict) else None) or {}
    if _empty(s.get('repo')):
        return {'ok': True, 'detail': 'the repository is set per task'}
    try:
        t = validate(ctx, {'repo': s['repo'].strip(), 'branch': s.get('branch'),
                           'path': str(s.get('path') or 'mockup/{task}').replace('{task}', 'task')})
    except Exception as e:  # noqa: BLE001 — клас помилки приходить з ctx
        return {'ok': False, 'error': 'vcs-bad-target', 'detail': getattr(e, 'message', None) or str(e)}
    g = _Git(ctx, t, connect_timeout=3)
    try:
        r = g.run(['ls-remote', '--heads', '--', t['repo'], t['branch']], tempfile.gettempdir(), CHECK_GIT_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — `vcs-offline` від тайм-ауту
        return {'ok': False, 'error': getattr(e, 'code', 'vcs-offline'), 'detail': getattr(e, 'message', None) or str(e)}
    if r.returncode != 0:
        e = g.fail('ls-remote', r)
        return {'ok': False, 'error': getattr(e, 'code', 'vcs-error'), 'detail': getattr(e, 'message', None) or str(e)}
    if (r.stdout or '').strip():
        return {'ok': True, 'detail': f'branch {t["branch"]} found'}
    return {'ok': True, 'detail': f'branch {t["branch"]} is not on the remote yet — the first send creates it'}
