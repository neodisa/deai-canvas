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
`<дзеркало>@lock` (між процесами — `bin/state.py` питає статус окремим процесом; модуль ще й перевантажується `exec`-ом).
Не `.lock`: репо `o/foo.lock` має дзеркало з таким самим імʼям, як лок-файл репо `o/foo`; `@` slug дати не може.

Оточення git: `LC_ALL=C` (класифікація помилок читає англійський текст), без `GIT_AUTHOR_*`/`GIT_COMMITTER_*` (особистість
коміту — з `meta.author`) і без змінних, що відводять git від дзеркала (`GIT_DIR`, `GIT_WORK_TREE`, …). Глобальний конфіг
людини (credential helper, `insteadOf`, ssh) не ізолюється. Дзеркало — кеш: перед кожним push/pull його дерево чиститься.

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
#: Найменший залишок бюджету (с), з яким ще варто повторювати спробу через IP: менше — повтор не встигне нічого.
MIN_RETRY = 1
MAX_MSG = 300
ALLOWED_SCHEMES = ('ssh://', 'https://', 'file://')
_RESOLVER_FAIL = 'could not resolve hostname'
#: Відмова ВХОДУ: ssh пише `Permission denied (publickey…)` чи `Permission denied, please try again`. Голе «permission
#: denied» — це права на файли дзеркала (`index.lock`, `FETCH_HEAD`), не доступ до сервера.
_AUTH_MARKS = ('permission denied (', 'permission denied, please try again', 'authentication failed',
               'could not read username', 'could not read password', 'host key verification failed',
               'returned error: 403')
_AUTH_RE = re.compile(r'permission to \S+ denied')             # GitHub: «remote: Permission to o/r.git denied to user.»
_OFFLINE_MARKS = ('could not resolve hostname', 'could not resolve host', 'connection timed out',
                  'operation timed out', 'network is unreachable', 'no route to host', 'connection refused')
_NO_BRANCH_MARKS = ('not found in upstream', "couldn't find remote ref", 'could not find remote ref')
_SCP = re.compile(r'(?:([^@/:\s]+)@)?([^/:\s]+):(.+)')
_NAME = re.compile(r'[A-Za-z0-9._-]+')          # хост і користувач scp-адреси: жодних `; $ ( ) & | < >` (див. `_Git._ssh`)
_USERINFO = re.compile(r'(://)[^/\s]*@')              # до ОСТАННЬОГО `@` перед першим `/`: `p@ss` у паролі теж
_BAD_BRANCH_CHARS = set(' ~^:?*[\\')
_BAD_PATH_CHARS = set('*?[\\')
#: Змінні оточення батька, що перекрили б модуль: особистість коміту (`meta.author`) і розташування репозиторію
#: (дзеркало). Глобальний конфіг людини (`GIT_CONFIG_GLOBAL`, `~/.gitconfig`: credential helper, `insteadOf`, ssh) НЕ чіпаємо.
_GIT_ENV_DROP = ('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_AUTHOR_DATE', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL',
                 'GIT_COMMITTER_DATE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
                 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_NAMESPACE', 'GIT_CEILING_DIRECTORIES', 'GIT_COMMON_DIR',
                 'GIT_GLOB_PATHSPECS', 'GIT_NOGLOB_PATHSPECS', 'GIT_ICASE_PATHSPECS')
_NTFS_GIT = re.compile(r'git~\d+')                  # NTFS: коротке імʼя `.git`


def _err(ctx, code, message=''):
    text = _mask(str(message))[:MAX_MSG]
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    return cls(code, message=text) if cls is not None else RuntimeError(f'{code}: {text}')


def _mask(text):
    """Userinfo адреси (`://user:pass@`, `://TOKEN@`) ніколи не йде в текст: пароль у адресі відхиляє `validate`, але токен
    у позиції користувача він не відрізнить, а stderr git — чужий текст."""
    return _USERINFO.sub(r'\1***@', text)


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
        if not u.hostname or u.hostname.startswith('-') or (u.username or '').startswith('-'):
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
    """`p` — уже без `/` по краях. Сегменти `.`/`..`/порожні, магія pathspec, глоби, `.git` (будь-який регістр) і його
    короткі імена NTFS (`GIT~1`) — ні."""
    if not p or p.startswith(('-', ':')) or _ctl(p) or any(c in _BAD_PATH_CHARS for c in p):
        return f'{what}: not a valid folder in the repository'
    for seg in p.split('/'):
        low = seg.rstrip(' .').lower()                  # NTFS відкидає хвостові крапки й пробіли: `.git.` — це `.git`
        if seg in ('', '.', '..') or low == '.git' or _NTFS_GIT.fullmatch(low):
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
    branch = target.get('branch').strip() if not _empty(target.get('branch')) else 'main'
    path = target.get('path').strip().strip('/') if isinstance(target.get('path'), str) else ''
    why = _repo_why(repo) or _branch_why(branch) or _path_why(path)
    key, ip = _pick(target, settings, 'ssh_key'), _pick(target, settings, 'host_ip')
    if not why and key is not None:
        key = os.path.expanduser(key)
        if not (os.path.isabs(key) and os.path.isfile(key)):
            why = 'ssh_key: not an existing file (use an absolute path or ~)'
    if not why and ip is not None:
        try:
            if '%' in ip:                         # zone-id (`fe80::1%eth0`): ipaddress його приймає, `insteadOf` — ні
                raise ValueError(ip)
            ipaddress.ip_address(ip)
        except ValueError:
            why = 'host_ip: not an IP address'
    if why:
        raise _err(ctx, 'vcs-bad-target', why)
    return {'repo': repo, 'path': path, 'branch': branch, 'ssh_key': key, 'host_ip': ip}


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

    def __init__(self, ctx, t, connect_timeout=None, deadline=None):
        """`deadline` — абсолютний `time.monotonic()`, до якого мають вкластись ВСІ спроби (`check`): повтор через IP
        отримає лише залишок. Без нього кожна спроба — з повним тайм-аутом."""
        self.ctx, self.t, self.connect_timeout, self.deadline = ctx, t, connect_timeout, deadline

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
        for name in _GIT_ENV_DROP:
            env.pop(name, None)
        env['LC_ALL'] = 'C'                       # класифікація помилок читає англійський текст git
        env.pop('LANGUAGE', None)                 # пріоритетніший за LC_ALL для перекладів gettext
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

    @staticmethod
    def _sub(args):
        """Підкоманда git для тексту помилок: `commit` іде як `-c user.name=… -c user.email=… commit`, а не `-c`."""
        i = 0
        while i + 1 < len(args) and args[i] == '-c':
            i += 2
        return args[i] if i < len(args) else ''

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
            # `utf-8`, а не локаль батька (Windows — cp1251/cp1252: кирилиця авторів ламалась би); `errors='replace'`:
            # git повторює в stderr байти з імен шляхів — не-UTF-8 не мусить кидати UnicodeDecodeError.
            return subprocess.run(['git', *pre, *args], cwd=cwd, env=self._env(alias, literal),
                                  capture_output=True, encoding='utf-8', errors='replace', timeout=timeout)
        except subprocess.TimeoutExpired:
            raise _err(self.ctx, 'vcs-offline', f'git {self._sub(args)}: no answer in {timeout:g} s') from None
        except (OSError, ValueError) as e:        # немає git у PATH, зникла тека cwd, нема прав; NUL в аргументі — ValueError
            raise _err(self.ctx, 'vcs-error', f'git {self._sub(args)}: {e}') from None

    def run(self, args, cwd, timeout=GIT_TIMEOUT, literal=True):
        r = self._once(args, cwd, timeout, None, literal)
        ip = self.t.get('host_ip')
        if (r.returncode != 0 and ip and _RESOLVER_FAIL in (r.stderr or '').lower()
                and _SCP.fullmatch(self.t['repo']) and not self.t['repo'].startswith(ALLOWED_SCHEMES)
                and not os.path.isabs(self.t['repo'])):
            if self.deadline is not None:
                timeout = min(timeout, self.deadline - time.monotonic())
                if timeout < MIN_RETRY:
                    return r                      # бюджет майже вичерпано: повтору нема, віддаємо першу відмову
            return self._once(args, cwd, timeout, ip, literal)
        return r

    def code_of(self, r):
        low = (r.stderr or r.stdout or '').lower()
        if any(m in low for m in _AUTH_MARKS) or _AUTH_RE.search(low):
            return 'vcs-auth'
        if any(m in low for m in _OFFLINE_MARKS):
            return 'vcs-offline'
        if 'index.lock' in low and 'file exists' in low:      # інший git тримає лок; `Permission denied` — права
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
    """Одна операція на дзеркало, між процесами й потоками: `flock` на `<дзеркало>@lock` (окремий `open` — окремий опис
    файла, тож потоки одного процесу теж виключають один одного). `wait=0` — одна спроба. Не реентерабельний: другий
    вхід у той самий лок з того ж потоку чекає на себе. Файл — `@lock`, не `.lock`: дзеркало репо `o/foo.lock` — це тека
    з таким самим імʼям, як лок-файл репо `o/foo`; slug (`[^\\w.-]` → `-`) `@` дати не може, тож збігу нема."""

    def __init__(self, ctx, md, wait):
        self.ctx, self.path, self.wait, self.fh = ctx, md + '@lock', wait, None

    def __enter__(self):
        try:
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            self.fh = open(self.path, 'a+')
        except OSError as e:                                  # файл на місці теки кешу, нема прав
            raise _err(self.ctx, 'vcs-error', f'mirror lock: {e}') from None
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


def _no_branch(r):
    """Відмова «такої гілки на origin нема» (а не «origin недоступний»)."""
    low = (r.stderr or r.stdout or '').lower()
    return any(m in low for m in _NO_BRANCH_MARKS)


def _has_ref(g, cwd, ref):
    return g.run(['rev-parse', '--verify', '--quiet', ref], cwd).returncode == 0


def _ensure(g, md):
    """Дзеркало цілі: клон за потреби (у тимчасову теку поруч + `rename`: перерваний клон не лишає напівдзеркала),
    `origin` = адреса цілі, свіжий fetch. ⛔ Відмову fetch не ковтаємо: без свіжого origin «відстає» бреше нулем.
    Гілки на origin ще нема — не відмова: перший push її створить (лише на порожньому репо, див. `_checkout`)."""
    b = g.t['branch']
    if not os.path.isdir(os.path.join(md, '.git')):
        if os.path.lexists(md):
            raise _err(g.ctx, 'vcs-error', f'mirror folder exists but is not a git clone: {os.path.basename(md)}')
        parent = os.path.dirname(md)
        try:
            os.makedirs(parent, mode=0o700, exist_ok=True)
            tmp = tempfile.mkdtemp(prefix='.clone-', dir=parent)
        except OSError as e:
            raise _err(g.ctx, 'vcs-error', f'mirror: cannot make a folder for the clone: {e}') from None
        try:
            r = g.run(['clone', '--quiet', '--branch', b, '--', g.t['repo'], tmp], parent, CLONE_TIMEOUT)
            if r.returncode == 0:
                # `--branch <тег>` теж вдається (detached HEAD), але гілки `<b>` у клоні нема: працювати так тихо не можна.
                if not _has_ref(g, tmp, f'refs/heads/{b}'):
                    raise _err(g.ctx, 'vcs-error', f'clone failed: {b} is not a branch on the remote (a tag?)')
            elif _no_branch(r):
                # Порожній репо клон `--branch` не бере. Клонуємо без гілки; порожній (HEAD не народжений) — лишаємо
                # й ставимо HEAD на цільову гілку; непорожній із іншою типовою — відмова `clone failed`, як у 0.7.0.
                shutil.rmtree(tmp, ignore_errors=True)
                os.makedirs(tmp, mode=0o700)
                r2 = g.run(['clone', '--quiet', '--', g.t['repo'], tmp], parent, CLONE_TIMEOUT)
                if r2.returncode == 0 and not _has_ref(g, tmp, 'HEAD'):
                    g.must(['symbolic-ref', 'HEAD', f'refs/heads/{b}'], tmp, 'symbolic-ref')
                    r = r2
            if r.returncode != 0:
                raise g.fail('clone', r)
            try:
                os.rename(tmp, md)
            except OSError as e:
                raise _err(g.ctx, 'vcs-error', f'mirror: cannot put the clone in place: {e}') from None
        finally:
            if os.path.isdir(tmp):
                shutil.rmtree(tmp, ignore_errors=True)
        return
    _align_remote(g, md)
    r = g.run(['fetch', '--quiet', 'origin', b], md)
    if r.returncode != 0 and not _no_branch(r):
        raise g.fail('fetch', r)


def _align_remote(g, md):
    """`origin` дзеркала = адреса цілі (fb-29092026-d64d35: дзеркало, склоноване з обхідною IP-адресою, тримало її в
    origin тижнями). ЗАПИСАНЕ значення, а не `remote get-url`: той розгортає `url.*.insteadOf`."""
    r = g.run(['config', '--get', 'remote.origin.url'], md)
    have = (r.stdout or '').strip() if r.returncode == 0 else ''
    if have == g.t['repo']:
        return
    g.must(['remote', 'set-url', 'origin', g.t['repo']], md, 'remote set-url')
    print(_mask(f'дзеркало {os.path.basename(md)}: origin {have or "—"} → {g.t["repo"]} (за ціллю синку)'),
          file=sys.stderr)


def _reset(g, md):
    """Робоче дерево й індекс дзеркала = HEAD, чужого непідтвердженого немає (незапушені КОМІТИ не страждають).
    Нема жодного коміту (порожній репо, перший push) — HEAD не народжений: чиститься лише індекс."""
    if _has_ref(g, md, 'HEAD'):
        g.must(['reset', '--hard', '-q', 'HEAD'], md, 'reset')
    else:
        g.must(['read-tree', '--empty'], md, 'reset')
    g.must(['clean', '-fdq'], md, 'clean')


def _checkout(g, md):
    """Чисте дерево на цільовій гілці. Чистка йде ДО `checkout`: той відмовився б перезаписати чужі зміни. Дзеркало —
    кеш інструмента: брудне дерево після збою (коміт відмовлено, копіювання урвалось) віддавалось би `pull` як «робота
    колеги», а `push` комітив би сторонній індекс."""
    b = g.t['branch']
    _reset(g, md)
    if _has_ref(g, md, f'refs/heads/{b}'):
        g.must(['checkout', '-q', b, '--'], md, f'checkout {b}', keep=200)
    elif _has_ref(g, md, f'refs/remotes/origin/{b}'):
        g.must(['checkout', '-q', '-b', b, '--track', f'origin/{b}'], md, f'checkout {b}', keep=200)
    else:
        # Гілки нема ні тут, ні на origin. Нову з нуля заводимо лише в справді ПОРОЖНЬОМУ репо; інакше друкарська
        # помилка (чи тег) дала б на origin кореневий коміт із усім індексом `main`.
        r = g.run(['ls-remote', '--heads', 'origin'], md)
        if r.returncode != 0:
            raise g.fail('ls-remote', r)
        if (r.stdout or '').strip():
            raise _err(g.ctx, 'vcs-error', f'branch {b} not found on the remote')
        g.must(['symbolic-ref', 'HEAD', f'refs/heads/{b}'], md, 'symbolic-ref')
        # Нова гілка з нуля мусить початись з порожнього індексу: `symbolic-ref` його не чіпає, і дерево попередньої гілки
        # (дзеркало ще пам'ятає origin до того, як той спорожнів) потрапило б у перший коміт.
        _reset(g, md)


def _count(g, md, rng, path=None):
    """Кількість комітів у діапазоні (`path` звужує до однієї теки). Нема гілки, щоб рахувати, — 0."""
    r = g.run(['rev-list', '--count', rng] + (['--', path] if path else []), md)
    out = (r.stdout or '').strip()
    return int(out) if r.returncode == 0 and out.isdigit() else 0


def _on_remote(g, md):
    """Три стани: True / False / None («гілки на origin нема — питання без відповіді»). Не зливати None у False."""
    b, p = g.t['branch'], g.t['path']
    if g.run(['cat-file', '-e', f'origin/{b}:{p}'], md).returncode == 0:
        return True
    if not _has_ref(g, md, f'refs/remotes/origin/{b}'):
        return None
    return False


def _unpushed(g, md):
    """Локальні коміти, яких нема на origin. Гілки на origin ще нема (порожній репо, перший push відмовлено) — усі
    коміти локальної гілки: інакше «немає що відправляти» ховало б коміт, що так і не доїхав."""
    b = g.t['branch']
    if _has_ref(g, md, f'refs/remotes/origin/{b}'):
        return _count(g, md, f'origin/{b}..{b}')
    return _count(g, md, f'refs/heads/{b}') if _has_ref(g, md, f'refs/heads/{b}') else 0


def _behind_top(g, md):
    """Хто й коли зробив верхній коміт origin — щоб не гадати, хто нас обігнав. Без мережі."""
    r = g.run(['log', '-1', '--format=%an%x1f%ad%x1f%s', '--date=format:%d.%m.%Y %H:%M', f'origin/{g.t["branch"]}'], md)
    if r.returncode != 0 or '\x1f' not in r.stdout:
        return {}
    author, date, subject = (r.stdout.rstrip('\n').split('\x1f') + ['', '', ''])[:3]       # не strip: `\x1f` — пробіл
    return {'author': author, 'date': date, 'subject': subject[:120]}


def _web_parts(t):
    """(хост без порту, хост для вебу, шлях проєкту без `.git`). Порт `ssh://` — не порт вебу; порт `https://` — той самий."""
    host, rpath = _split_repo(t['repo'])
    proj = rpath.strip('/')
    if proj.endswith('.git'):
        proj = proj[:-4]
    bare = host.split(':')[0].lower()
    return bare, (host.lower() if t['repo'].startswith('https://') else bare), proj


def label_of(t):
    host = _web_parts(t)[0]
    return 'GitHub' if host == 'github.com' else 'GitLab' if 'gitlab' in host else 'Git'


def web_url(t):
    """Історія комітів `<path>` у вебі: GitHub і GitLab (хост містить `gitlab`); інше — `None`."""
    host, netloc, proj = _web_parts(t)
    if host in ('', 'local') or not proj:
        return None
    tail = quote(f'{t["branch"]}/{t["path"]}', safe='/')
    proj = quote(proj, safe='/')
    if host == 'github.com':
        return f'https://{netloc}/{proj}/commits/{tail}'
    if 'gitlab' in host:
        return f'https://{netloc}/{proj}/-/commits/{tail}'
    return None


def _inside(ctx, md, p):
    """`<md>/<p>`, якщо шлях веде туди, куди написано: жоден відрізок не симлінк. У чужому репо `mockup` може бути
    симлінком на `/` чи на `.git` дзеркала, а `isdir`/`copytree`/`rmtree` пішли б за ним — повз дзеркало або в його `.git`."""
    root = os.path.realpath(md)
    want = os.path.normcase(os.path.join(root, *p.split('/')))
    if os.path.normcase(os.path.realpath(os.path.join(md, p))) != want:
        raise _err(ctx, 'vcs-error', 'path leaves the mirror or goes through a symlink in the repository')
    return os.path.join(md, p)


def status(ctx, target):
    """Стан дзеркала цілі після свіжого fetch. «Відстає» по ВСЬОМУ репо (`behind`) і по теці задачі (`behind_path`) —
    різні новини: перше наздоганяється само, друге блокує push. Не чекає на зайняте дзеркало (`vcs-busy`)."""
    t = validate(ctx, target)
    g, md = _Git(ctx, t), _mirror(ctx, t)
    with _Lock(ctx, md, wait=0):
        _ensure(g, md)
        b = t['branch']
        return {'behind': _count(g, md, f'{b}..origin/{b}'),
                'behind_path': _count(g, md, f'{b}..origin/{b}', t['path']),
                'unpushed': _unpushed(g, md),
                'on_remote': _on_remote(g, md), 'web': web_url(t), 'label': label_of(t)}


def _pushed(g, r, changed, catchup=False):
    ok = r.returncode == 0
    out = {'ok': ok, 'synced': ok, 'changed': changed, 'pushed': ok,
           'error': None if ok else _mask(r.stderr or r.stdout or '')[-300:]}      # маска ДО обрізання: різ ховає `://`
    if catchup:
        out['catchup'] = True
    if not ok:
        out['code'] = g.code_of(r)
    return out


def _skip_links(d, names):
    """Симлінки (файли й теки) не їдуть ні в репо, ні з репо: у спільному репо лінк виніс би локальні шляхи, а
    розіменування — вміст поза текою макета; з чужого репо він вів би куди завгодно на цій машині."""
    return [n for n in names if os.path.islink(os.path.join(d, n))]


def _commit_tree(g, ctx, md, src, dst, p, ident, message):
    """Копія `src` у `<path>` → add → коміт. True — коміт зроблено, False — змін нема. Збій на БУДЬ-ЯКОМУ кроці лишає
    дерево чистим (`_reset`) і кидає виняток далі: напівскопійована тека чи індекс без коміту потрапили б у наступний pull
    як «робота колеги»."""
    try:
        try:
            if os.path.isdir(dst):
                shutil.rmtree(dst)                       # щоб видалені в `src` файли пішли й з репо
            shutil.copytree(src, dst, symlinks=True, ignore=_skip_links)
        except OSError as e:                             # файл замість теки, нема прав, зникло посеред копіювання
            raise _err(ctx, 'vcs-error', f'push: cannot replace {p}: {e}') from None
        g.run(['add', '-A', '--', p], md)                # збій add видно далі: зміни лишаться неіндексованими
        st = g.run(['status', '--porcelain', '--', p], md)
        if st.returncode != 0:                           # порожній вивід при відмові читався б як «змін нема»
            raise g.fail('status', st)
        if not st.stdout.strip():
            return False
        c = g.run(['-c', f'user.name={ident[0]}', '-c', f'user.email={ident[1]}', 'commit', '-q', '-m', message], md)
        if c.returncode != 0:
            raise g.fail('commit', c)
        return True
    except BaseException:
        try:
            _reset(g, md)
        except Exception:  # noqa: BLE001 — перший збій важливіший; наступна операція почистить сама (`_checkout`)
            pass
        raise


def push(ctx, target, src, meta):
    """Вміст `src` стає `<path>` (заміна теки, з dot-файлами) → коміт → push без force. Форми результату — як
    `gitlab_sync` 0.7.0 без `remote` (його додає ядро). Блокує лише тека задачі (`behind_path`): решту, що пішла
    вперед, наздоганяє `merge --ff-only` (інакше push відбивався б як non-fast-forward назавжди)."""
    t = validate(ctx, target)
    if not isinstance(src, str) or not os.path.isdir(src):
        raise _err(ctx, 'vcs-error', 'push: src is not a folder')
    meta = meta if isinstance(meta, dict) else {}
    author = meta.get('author') if isinstance(meta.get('author'), dict) else {}
    raw = [str(author.get('name') or ''), str(author.get('email') or '')]
    message = str(meta.get('message') or 'deai: sync')
    # NUL в аргументі git — `ValueError` ще до запуску, інші керівні символи псують коміт: відмовляємо ДО будь-якого git.
    if _ctl(raw[0]) or _ctl(raw[1]) or _ctl(message.replace('\n', '').replace('\t', '').replace('\r', '')):
        raise _err(ctx, 'vcs-error', 'push: meta (message, author) contains control characters')
    ident = (raw[0].strip() or 'Deai Canvas', raw[1].strip() or 'deai@localhost')
    g, md = _Git(ctx, t), _mirror(ctx, t)
    b, p = t['branch'], t['path']
    with _Lock(ctx, md, wait=LOCK_WAIT):
        _ensure(g, md)
        _checkout(g, md)
        behind = _count(g, md, f'{b}..origin/{b}')
        if behind > 0:
            behind_path = _count(g, md, f'{b}..origin/{b}', p)
            if behind_path > 0:
                return {'ok': False, 'synced': False, 'blocked': 'behind', 'behind': behind,
                        'behind_path': behind_path, 'behind_top': _behind_top(g, md)}
            ff = g.run(['merge', '--ff-only', '--quiet', f'origin/{b}'], md)
            if ff.returncode != 0:
                return {'ok': False, 'synced': False, 'blocked': 'diverged', 'behind': behind,
                        'ahead': _count(g, md, f'origin/{b}..{b}'), 'behind_top': _behind_top(g, md),
                        'error': _mask(ff.stderr or ff.stdout or '')[-200:]}
        dst = _inside(ctx, md, p)                        # ПІСЛЯ merge: він міг привезти симлінк
        if not _commit_tree(g, ctx, md, src, dst, p, ident, message):
            # Не змінилось — ще НЕ «лежить на origin»: попередній коміт міг не доїхати (bgSanctions, 12 днів «✓»).
            # Гілки на origin нема зовсім (порожній репо) — теж не «synced»: пробуємо push і чесно звітуємо про результат.
            if _count(g, md, f'origin/{b}..{b}') == 0 and _has_ref(g, md, f'refs/remotes/origin/{b}'):
                return {'ok': True, 'synced': True, 'changed': False, 'pushed': False}
            return _pushed(g, g.run(['push', '--quiet', 'origin', b], md), changed=False, catchup=True)
        out = _pushed(g, g.run(['push', '--quiet', 'origin', b], md), changed=True)
        out['sha'] = (g.run(['rev-parse', '--short', 'HEAD'], md).stdout or '').strip()
        return out


def _ignore_list(ctx, opts):
    """`opts.ignore` — список підтек `<path>`, що не вважаються роботою. Перевіряється тими ж правилами, що й шлях."""
    ign = opts.get('ignore') if isinstance(opts, dict) else None
    if ign is None:
        return []
    if not isinstance(ign, (list, tuple)):
        raise _err(ctx, 'vcs-bad-target', 'ignore: must be a list of folders')
    out = []
    for x in ign:
        x = x.strip('/') if isinstance(x, str) else ''
        why = _path_why(x, 'ignore')
        if why:
            raise _err(ctx, 'vcs-bad-target', why)
        out.append(x)
    return out


def pull(ctx, target, dst, opts=None):
    """Свіжий `<path>` з origin → порожня `dst`. `last_commit`: `author` — останній коміт `<path>`; `time` — останній
    коміт `<path>` ПОЗА підтеками `opts.ignore` (кадри перезнімаються самі — це не робота), `None`, якщо такого нема.
    Нема `<path>` (чи самої гілки на порожньому origin) — `{found: False}`, не помилка."""
    t = validate(ctx, target)
    ignore = _ignore_list(ctx, opts)
    if not isinstance(dst, str) or not os.path.isdir(dst) or os.listdir(dst):
        raise _err(ctx, 'vcs-error', 'pull: dst must be an empty folder')
    g, md = _Git(ctx, t), _mirror(ctx, t)
    b, p = t['branch'], t['path']
    with _Lock(ctx, md, wait=LOCK_WAIT):
        _ensure(g, md)
        _checkout(g, md)
        if not _has_ref(g, md, f'refs/remotes/origin/{b}'):
            return {'found': False, 'last_commit': None}          # порожній origin: гілки ще нема
        # ⛔ Не ковтати: при розходженні --ff-only падає, і в ітерацію поїхало б ЗАСТАРІЛЕ дзеркало з чужим підписом.
        pl = g.run(['pull', '--ff-only', '--quiet', 'origin', b], md)
        if pl.returncode != 0:
            ahead = _count(g, md, f'origin/{b}..{b}')
            hint = (f' Дзеркало має {ahead} локальний(х) коміт(ів) поверх origin — розходження треба розвести вручну.'
                    if ahead else '')
            raise g.fail('pull --ff-only', pl, tail='.' + hint, keep=200)
        src = _inside(ctx, md, p)
        if not os.path.isdir(src):
            return {'found': False, 'last_commit': None}
        try:
            shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True, ignore=_skip_links)
        except OSError as e:
            raise _err(ctx, 'vcs-error', f'pull: cannot copy {p}: {e}') from None
        a = g.run(['log', '-1', '--format=%an', '--', p], md)
        excl = [f':(exclude){p}/{x}' for x in ignore]
        # Магія `:(exclude)` — лише тут і лише з нашим префіксом: `p` і `ignore` перевірені (`_path_why`).
        tm = g.run(['log', '-1', '--format=%ct', '--', p, *excl], md, literal=False)
        try:
            when = int((tm.stdout or '').strip())
        except ValueError:
            when = None
        return {'found': True,
                'last_commit': {'author': (a.stdout or '').strip() if a.returncode == 0 else '', 'time': when}}


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
    g = _Git(ctx, t, connect_timeout=3, deadline=time.monotonic() + CHECK_GIT_TIMEOUT)
    try:
        # Повне імʼя гілки: шаблон `ls-remote` зіставляється з ХВОСТОМ імені, тож `main` знайшов би й `feature/main`.
        r = g.run(['ls-remote', '--heads', '--', t['repo'], 'refs/heads/' + t['branch']], tempfile.gettempdir(),
                  CHECK_GIT_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — `vcs-offline` від тайм-ауту
        return {'ok': False, 'error': getattr(e, 'code', 'vcs-offline'), 'detail': getattr(e, 'message', None) or str(e)}
    if r.returncode != 0:
        e = g.fail('ls-remote', r)
        return {'ok': False, 'error': getattr(e, 'code', 'vcs-error'), 'detail': getattr(e, 'message', None) or str(e)}
    if (r.stdout or '').strip():
        return {'ok': True, 'detail': f'branch {t["branch"]} found'}
    return {'ok': True, 'detail': f'branch {t["branch"]} is not on the remote yet — the first send creates it'}
