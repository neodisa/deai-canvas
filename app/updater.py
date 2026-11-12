"""Оновлення інструмента (0.23.0): версія, remote, перевірка тегів `vX.Y.Z`, файл стану `update.json`, фоновий потік.

`check`/`status` — ЧИТАННЯ (нічого не змінюють у робочому дереві); `apply` — єдине місце, де модуль пише в дерево: `fetch` тега → перевірка
`package.json` тега → `merge --ff-only` → смоук в ізольованому дочірньому процесі → відкат. Правила, що тримають модуль безпечним:

* Тег — лише `^v\\d+\\.\\d+\\.\\d+\\Z` (без пре-релізів); усе інше з `ls-remote` ігнорується. Порівняння — за числами, не за рядками.
* `remote` (змінна `DEAI_UPDATE_REMOTE`, upstream гілки) — недовірений рядок для `git`: дозволені імʼя remote, `https://`/`ssh://`,
  `git@host:path`, абсолютний шлях (`check_remote`). Усі виклики `git` — з `-c protocol.ext.allow=never` і з `--` перед адресою.
* Відповідь API несе лише ХОСТ remote (`remote_host`), ніколи userinfo й шляхи; `reason` — короткий код, а не текст помилки `git`.
* Мережа — лише через `network_allowed`: remote-шлях файлової системи дозволений завжди; будь-який інший — коли НЕ
  (`DEAI_NO_UPDATE_CHECK=1` або `isolation.isolated()`). Інакше `state: 'disabled'`, `git` не викликається.
* Читальні виклики `git` мають `GIT_OPTIONAL_LOCKS=0`: `git status` не оновлює індекс живого дерева.
* `update.json` (0600) не пишеться, коли `isolation.writes_allowed(home)` — стан тоді лише в памʼяті процесу.
* `apply`: ціль — `latest` зі стану (не з запиту); тег перевіряється `TAG_RE` до будь-якого `git`; remote резолвиться ЗАРАЗ (не зі
  збереженого); тег фіксується на sha (`rev-parse`), версія в його `package.json` мусить збігатись із `latest`; єдиний `reset` у модулі —
  `reset --hard <old>`, лише після вдалого `merge --ff-only` і лише на 40-hex sha, перевірений регексом.
* `BOOT` — випадковий токен, що виникає при ІМПОРТІ: після `execv` модуль імпортується наново, тож клієнт бачить, що процес інший.

Імпортує лише `isolation`, `spaces`, `atomic_io` (без `serve`: цикл неможливий).
"""
import datetime
import json
import hashlib
import os
import random
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata

import isolation
import spaces
from atomic_io import atomic_write_json

PRODUCT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Тег релізу. `\Z`, а не `$`: `$` пропускає завершальний `\n`.
#: Без `\d` (він приймає нелатинські цифри) і без ведучих нулів; до 9 цифр на частину (ліміт `int` не дістати).
TAG_RE = re.compile(r'^v(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\Z')
CHECK_EVERY_S = 6 * 3600
LS_REMOTE_TIMEOUT_S = 15
FETCH_TIMEOUT_S = 60
LOCAL_GIT_TIMEOUT_S = 10
MERGE_TIMEOUT_S = 60
SMOKE_TIMEOUT_S = 30
#: Підрядки stderr (`LC_ALL=C`) `git fetch`, коли `fsckObjects` чи розпакування відкинули обʼєкти.
#: Голі `index-pack`/`unpack-objects` тут НЕ стоять: «index-pack failed» дає й обірваний переказ (це `offline`), а не лише відкинутий обʼєкт.
_FETCH_REJECTED_MARKERS = ('fsck', 'error in object', 'bad object', 'corrupt', 'invalid object')
NOTES_MAX_BYTES = 1024 * 1024        # з CHANGELOG віддаленого тега читається не більше 1 МБ
NOTES_SECTION_MAX_BYTES = 8 * 1024
NOTES_TOTAL_MAX_BYTES = 40 * 1024
NOTES_FAIL_TTL_S = 60                # після невдалого `fetch` для «Що нового» стільки секунд відповідаємо без нового `fetch`
FIRST_CHECK_DELAY_S = 5
FIRST_CHECK_JITTER_S = 25
PERIOD_JITTER = 0.1
STATES = ('ok', 'offline', 'no-git', 'error', 'disabled')
BOOT = secrets.token_hex(8)

_SHA_RE = re.compile(r'^[0-9a-f]{40}\Z')
_NAME_RE = re.compile(r'^[A-Za-z0-9][\w.-]*\Z')
_URL_RE = re.compile(r'^(?:https|ssh)://[^\s\x00-\x1f\\/-][^\s\x00-\x1f\\]*\Z')
_HOST_START_RE = re.compile(r'^[A-Za-z0-9\[]')
#: Змінні `git`, що перекривають репо/конфіг: з успадкованого оточення вилучаються.
_GIT_SCRUB = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
              'GIT_CONFIG', 'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT', 'GIT_SSH', 'GIT_EXEC_PATH', 'GIT_NAMESPACE')
_GIT_SCRUB_PREFIXES = ('GIT_CONFIG_KEY_', 'GIT_CONFIG_VALUE_')
_SCP_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.-]*:[^\s\x00-\x1f]+\Z')
_PATH_RE = re.compile(r'^/[^\x00-\x1f]*\Z')
_HOST_URL_RE = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*://(?:[^/\s]*@)?(\[[^\]]*\]|[^/:?#\s]+)')
_HOST_SCP_RE = re.compile(r'^(?:[^@/\s]+@)?([^:/\s]+):')


def _communicate(argv, cwd, env, timeout):
    """Процес без оболонки в окремій групі → `(rc, stdout, stderr)`. Тайм-аут — `(124, '', 'timeout')` (вбивається вся група: `ssh`, нащадки),
    нема виконуваного — `(127, '', 'no-git-binary')`. Недекодований вивід не кидає (`errors='replace'`)."""
    try:
        p = subprocess.Popen(argv, cwd=cwd, env=env, text=True, errors='replace',
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=(os.name != 'nt'))
    except FileNotFoundError:
        return 127, '', 'no-git-binary'
    except (OSError, ValueError, TypeError) as e:        # ValueError: NUL у аргументі
        return 126, '', type(e).__name__
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            if hasattr(os, 'killpg'):
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
        except (OSError, ProcessLookupError):
            pass
        try:
            p.communicate(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                p.wait(timeout=1)
            except Exception:  # noqa: BLE001
                pass
            for pipe in (getattr(p, 'stdout', None), getattr(p, 'stderr', None)):
                try:
                    pipe.close()
                except Exception:  # noqa: BLE001
                    pass
        return 124, '', 'timeout'
    return p.returncode, out, err


#: Підкоманди, що ходять у мережу: лише для них читається локальний `core.sshCommand` клону.
_NETWORK_SUBCOMMANDS = ('ls-remote', 'fetch', 'clone', 'pull', 'push')


def _subcommand(args):
    """Перша підкоманда `git` у `args` (повз `-c <k=v>` і прапорці) або `None`."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == '-c':
            i += 2
            continue
        if a.startswith('-'):
            i += 1
            continue
        return a
    return None


def _base_env():
    """Успадковане оточення без змінних, що перекривають репо/конфіг `git` (`_GIT_SCRUB`)."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_SCRUB and not k.startswith(_GIT_SCRUB_PREFIXES)}


def _local_ssh_command(cwd):
    """`core.sshCommand` ЛИШЕ з власного `.git/config` клону (`--local`: глобальний, системний і `include` не читаються; `GIT_CONFIG*` вичищені
    через `_base_env`) або `None`. Багаторядкове/з NUL значення відкидається (у лог іде лише код `ssh-command-rejected`, не значення).
    Це не розширює довіру: клон і так виконує код зі свого `.git` (hooks)."""
    if not cwd:
        return None
    env = _base_env()
    env['GIT_OPTIONAL_LOCKS'] = '0'
    env['GIT_TERMINAL_PROMPT'] = '0'
    rc, out, _ = _communicate(['git', '-c', 'protocol.ext.allow=never', 'config', '--local', '--get', 'core.sshCommand'],
                              cwd, env, LOCAL_GIT_TIMEOUT_S)
    val = out.strip() if rc == 0 and isinstance(out, str) else ''
    if not val:
        return None
    if '\n' in val or '\x00' in val:
        try:
            sys.stderr.write('updater: ssh-command-rejected\n')
        except Exception:  # noqa: BLE001
            pass
        return None
    return val


def _git_env(env_extra=None, cwd=None, network=False):
    """Оточення `git`: без успадкованих `GIT_DIR`/`GIT_WORK_TREE`/`GIT_CONFIG*` тощо (`_GIT_SCRUB`), без запитів, без оновлення індексу.
    Для мережевих викликів у клоні зберігає його власний `core.sshCommand`, додаючи `BatchMode`/`ConnectTimeout` (явний `GIT_SSH_COMMAND`
    в оточенні головніший)."""
    env = _base_env()
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GCM_INTERACTIVE'] = 'never'
    env['GIT_OPTIONAL_LOCKS'] = '0'
    if 'GIT_SSH_COMMAND' not in env:
        local = _local_ssh_command(cwd) if (network and cwd) else None
        env['GIT_SSH_COMMAND'] = ((local + ' -o BatchMode=yes -o ConnectTimeout=10') if local
                                  else 'ssh -o BatchMode=yes -o ConnectTimeout=10')
    env.update(env_extra or {})
    return env


def run_git(args, cwd, timeout, env_extra=None):
    """`git` без оболонки → `(rc, stdout, stderr)`. Тайм-аут — `(124, '', 'timeout')` (уся група процесів убивається: `ssh` теж), нема
    `git` — `(127, '', 'no-git-binary')`. Оточення: без успадкованих `GIT_DIR`/`GIT_WORK_TREE`/`GIT_CONFIG*` тощо (`_GIT_SCRUB`)."""
    env = _git_env(env_extra, cwd=cwd, network=_subcommand(list(args)) in _NETWORK_SUBCOMMANDS)
    return _communicate(['git', '-c', 'protocol.ext.allow=never'] + list(args), cwd, env, timeout)


def git_head(args, cwd, limit, timeout, env_extra=None):
    """`git` → `(rc, bytes)`: читає з stdout НЕ БІЛЬШЕ `limit` байтів (пам'ять обмежена, на відміну від `communicate`) і вбиває процес, коли вивід
    більший. Обрізання за лімітом — `rc == 0`; тайм-аут — `124`; нема `git` — `127`. stderr відкидається."""
    try:
        p = subprocess.Popen(['git', '-c', 'protocol.ext.allow=never'] + list(args), cwd=cwd, env=_git_env(env_extra, cwd=cwd, network=_subcommand(list(args)) in _NETWORK_SUBCOMMANDS),
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             start_new_session=(os.name != 'nt'))
    except FileNotFoundError:
        return 127, b''
    except (OSError, ValueError, TypeError):
        return 126, b''
    timed_out = []

    def kill():
        timed_out.append(1)
        try:
            if hasattr(os, 'killpg'):
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
        except (OSError, ProcessLookupError):
            pass

    timer = threading.Timer(timeout, kill)
    timer.daemon = True
    timer.start()
    try:
        data = p.stdout.read(limit)
    finally:
        timer.cancel()
        if p.poll() is None:
            try:
                if hasattr(os, 'killpg'):
                    os.killpg(p.pid, signal.SIGKILL)
                else:
                    p.kill()
            except (OSError, ProcessLookupError):
                pass
        try:
            p.stdout.close()
        except OSError:
            pass
        try:
            p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
    if timed_out:
        return 124, b''
    if len(data) >= limit:
        return 0, data
    return p.returncode, data


def parse_tag(tag):
    """`'v1.2.3'` → `(1, 2, 3)`; усе інше (пре-реліз, `v1.2`, пробіли, `-…`, `\\n` у кінці) → `None`."""
    if not isinstance(tag, str):
        return None
    m = TAG_RE.match(tag)
    return tuple(int(g) for g in m.groups()) if m else None


def version_tuple(version):
    """`'0.10.1'` → `(0, 10, 1)`; не semver (`'unknown'`) → `None`."""
    return parse_tag('v' + version) if isinstance(version, str) else None


def latest_tag(ls_remote_out):
    """Найбільший тег `vX.Y.Z` у виводі `git ls-remote --tags` (`<sha>\\trefs/tags/<тег>`) → `'X.Y.Z'`, без тегів — `None`."""
    best = None
    for line in (ls_remote_out or '').splitlines():
        _, _, ref = line.partition('\t')
        if not ref.startswith('refs/tags/'):
            continue
        t = parse_tag(ref[len('refs/tags/'):])
        if t and (best is None or t > best):
            best = t
    return '.'.join(str(n) for n in best) if best else None


def current_version(root):
    """Версія з `package.json` кореня (єдине джерело); не читається — `'unknown'` (як `liga_migrate._tool_version`)."""
    try:
        with open(os.path.join(root, 'package.json'), encoding='utf-8') as f:
            return str(json.load(f).get('version') or 'unknown')
    except (OSError, ValueError, AttributeError):
        return 'unknown'


def check_remote(remote):
    """Чи `remote` безпечно віддавати `git`: імʼя remote, `https://`/`ssh://`, `git@host:path` або абсолютний шлях."""
    if not isinstance(remote, str):
        return False
    if _URL_RE.match(remote):
        authority = remote.split('://', 1)[1].split('/', 1)[0]
        return bool(_HOST_START_RE.match(authority.rsplit('@', 1)[-1]))      # `ssh://u@-oProxyCommand=x/` — не хост
    return bool(_NAME_RE.match(remote) or _SCP_RE.match(remote) or _PATH_RE.match(remote))


def remote_host(remote):
    """Лише хост адреси (для людини): `https://TOKEN@git.example/o/r.git` і `git@git.example:o/r.git` → `git.example`; абсолютний
    шлях → `'local'`; решта → `None`. Userinfo й шлях не віддаються ніколи."""
    if not isinstance(remote, str):
        return None
    if remote.startswith('/'):
        return 'local'
    m = _HOST_URL_RE.match(remote) or _HOST_SCP_RE.match(remote)
    return m.group(1) if m else None


def is_local_path(remote):
    return isinstance(remote, str) and remote.startswith('/')


def network_allowed(remote):
    """Мережу можна чіпати лише так: remote — шлях файлової системи (мережі нема) АБО не вимкнено оточенням і прогін не ізольований."""
    if is_local_path(remote):
        return True
    return not (os.environ.get('DEAI_NO_UPDATE_CHECK') == '1' or isolation.isolated())


def remote_for(root, run=run_git):
    """`(імʼя_чи_адреса, url, помилка)`: `DEAI_UPDATE_REMOTE` > upstream поточної гілки > `origin`. Імʼя розгортається в url
    (`git remote get-url`); помилка — код: `bad-remote` / `no-remote` / `no-git-binary`."""
    cand = (os.environ.get('DEAI_UPDATE_REMOTE') or '').strip()
    if not cand:
        rc, out, _ = run(['symbolic-ref', '--short', '-q', 'HEAD'], root, LOCAL_GIT_TIMEOUT_S)
        if rc == 127:
            return None, None, 'no-git-binary'
        branch = out.strip() if rc == 0 and out.strip() else 'main'
        rc, out, _ = run(['config', '--get', 'branch.%s.remote' % branch], root, LOCAL_GIT_TIMEOUT_S)
        cand = out.strip() if rc == 0 else ''
        if cand in ('', '.'):
            cand = 'origin'
    if not check_remote(cand):
        return None, None, 'bad-remote'
    if not _NAME_RE.match(cand):
        return cand, cand, None
    rc, out, _ = run(['remote', 'get-url', '--', cand], root, LOCAL_GIT_TIMEOUT_S)
    if rc == 127:
        return cand, None, 'no-git-binary'
    url = out.strip() if rc == 0 else ''
    if not url:
        return cand, None, 'no-remote'
    if not check_remote(url) or _NAME_RE.match(url):
        return cand, None, 'bad-remote'
    return cand, url, None


_CL_HEAD_RE = re.compile(r'^## \[([0-9][0-9.]*)\] [\u2014\u2013-] ([0-9]{2})\.([0-9]{2})\.([0-9]{4})[ \t]*\Z')


def _plain(text):
    """Лише текст: `\\r\\n`→`\\n`, табуляція → пробіл, решта керуючих/форматних символів (Unicode Cc/Cf) геть; `\\n` лишається."""
    text = text.encode('utf-8', 'replace').decode('utf-8')                 # самотні сурогати (`\ud800` з ручної правки кешу) → `?`, а не виняток
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    return ''.join(c for c in text if c == '\n' or unicodedata.category(c) not in ('Cc', 'Cf'))


def _cap_bytes(text, limit):
    raw = text.encode('utf-8')
    return text if len(raw) <= limit else raw[:limit].decode('utf-8', 'ignore')


def parse_changelog(text, after, upto):
    """Розділи `## [X.Y.Z] — DD.MM.YYYY` у проміжку `(after, upto]` → `[{version, date, body}]` (порядок файла). Лише текст (HTML лишається
    текстом); тіло розділу ≤ 8 КБ, усього ≤ 40 КБ; керуючі символи вирізано. Хибні заголовки (`## [0.2]`, без дати), `Unreleased` розділів не
    відкривають, але ЗАКРИВАЮТЬ попередній (їхній вміст не прилипає до сусіда)."""
    lo, hi = version_tuple(after), version_tuple(upto)
    if not (lo and hi and isinstance(text, str)):
        return []
    sections, cur, total = [], None, 0
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')

    def close():
        nonlocal cur, total
        if cur is None:
            return
        body = _cap_bytes(_plain('\n'.join(cur['lines'])).strip(), NOTES_SECTION_MAX_BYTES)
        room = NOTES_TOTAL_MAX_BYTES - total
        if room > 0:
            body = _cap_bytes(body, room).rstrip()
            total += len(body.encode('utf-8'))
            sections.append({'version': cur['version'], 'date': cur['date'], 'body': body})
        cur = None

    for line in lines:
        if line.startswith('## '):
            close()
            m = _CL_HEAD_RE.match(line)
            vt = version_tuple(m.group(1)) if m else None
            if m and vt and lo < vt <= hi:
                try:
                    datetime.date(int(m.group(4)), int(m.group(3)), int(m.group(2)))
                except ValueError:
                    continue
                cur = {'version': m.group(1), 'date': '%s.%s.%s' % (m.group(2), m.group(3), m.group(4)), 'lines': []}
        elif cur is not None:
            cur['lines'].append(line)
    close()
    return sections


class Updater:
    """Стан оновлення одного кореня: `check()` ходить у remote (за `network_allowed`), `status()` — відповідь `GET /api/update`."""

    def __init__(self, root, run=run_git, home=spaces.home, busy=lambda: None, clock=time.time):
        self.root = root
        self.run = run
        self.home = home
        self.busy = busy
        self.clock = clock
        self._lock = threading.RLock()           # короткий: лише читання/запис стану, НІКОЛИ не поверх git
        self._checking = threading.Lock()        # «перевірка триває»: друга `check()` не ставиться в чергу
        self._apply_lock = threading.Lock()      # «застосування триває»: друге `apply()` — `409 busy`
        self._fetch_lock = threading.Lock()      # один `fetch` тега за раз (`apply` і `notes` не б'ються за `refs/tags/vX`)
        self._mem = {}

    # --- файл стану ---

    def state_path(self):
        return os.path.join(self.home(), 'update.json')

    def _load(self):
        with self._lock:
            if not isolation.writes_allowed(self.home()):
                return dict(self._mem)
            try:
                with open(self.state_path(), encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                return {}
            return data if isinstance(data, dict) else {}

    def _save(self, state):
        with self._lock:
            self._mem = dict(state)
            if not isolation.writes_allowed(self.home()):
                return False
            try:
                os.makedirs(self.home(), mode=0o700, exist_ok=True)
                atomic_write_json(self.state_path(), state)
            except OSError:
                return False
            return True

    # --- перевірка ---

    def check(self):
        """Спитати remote про теги й записати результат. Не кидає: будь-яка несподіванка — `state: 'error'`. Мережа/`git` — ПОЗА замком
        стану (`GET /api/update` не чекає); друга `check()` під час першої повертає поточний стан одразу."""
        if not self._checking.acquire(blocking=False):
            return self._load()
        try:
            try:
                result = self._probe()
            except Exception:  # noqa: BLE001 — фонова перевірка не вмирає, а повідомляє
                result = {'state': 'error', 'reason': 'internal'}
            with self._lock:
                state = self._load()
                state['checked_at'] = int(self.clock())
                state['state'] = result['state']
                state['reason'] = result.get('reason')
                # `latest` переживає лише `offline` ТОГО Ж remote; інакше він застарів (інша адреса чи перевірка не відбулась).
                if result['state'] == 'ok':
                    state['latest'] = result.get('latest')
                elif not (result['state'] == 'offline' and result.get('remote_id') and state.get('remote_id') == result['remote_id']):
                    state.pop('latest', None)
                for k in ('remote_host', 'remote_id'):
                    if result.get(k):
                        state[k] = result[k]
                    else:
                        state.pop(k, None)
                self._save(state)
                return state
        finally:
            self._checking.release()

    def _probe(self):
        if not os.path.exists(os.path.join(self.root, '.git')):
            return {'state': 'no-git', 'reason': 'not-a-clone'}
        _, url, err = remote_for(self.root, self.run)
        if err:
            return {'state': 'no-git' if err == 'no-git-binary' else 'error', 'reason': err}
        host = remote_host(url)
        rid = hashlib.sha256(url.encode('utf-8', 'replace')).hexdigest()[:16]      # впізнати зміну remote, не зберігаючи адресу
        if not network_allowed(url):
            return {'state': 'disabled', 'reason': 'check-disabled', 'remote_host': host, 'remote_id': rid}
        rc, out, _ = self.run(['ls-remote', '--tags', '--refs', '--', url], self.root, LS_REMOTE_TIMEOUT_S)
        if rc == 127:
            return {'state': 'no-git', 'reason': 'no-git-binary'}
        if rc != 0:
            return {'state': 'offline', 'reason': 'timeout' if rc == 124 else 'unreachable', 'remote_host': host, 'remote_id': rid}
        return {'state': 'ok', 'reason': None, 'latest': latest_tag(out), 'remote_host': host, 'remote_id': rid}

    # --- відповідь ---

    def status(self):
        state = self._load()
        current = current_version(self.root)
        latest = state.get('latest') if isinstance(state.get('latest'), str) else None
        lt, ct = version_tuple(latest), version_tuple(current)
        available = bool(lt and ct and lt > ct)
        return {
            'current': current,
            'latest': latest,
            'available': available,
            'checked_at': state.get('checked_at'),
            'state': state.get('state') if state.get('state') in STATES else None,
            'reason': state.get('reason') if isinstance(state.get('reason'), str) else None,
            'blocked': self._safe_blocked() if available else None,
            'remote_host': state.get('remote_host') if isinstance(state.get('remote_host'), str) else None,
            'last_update': state.get('last_update') if isinstance(state.get('last_update'), dict) else None,
            'boot': BOOT,
            'restart_failed': state.get('restart_failed') == BOOT,
        }

    def _safe_blocked(self):
        """`_blocked` без винятків: `GET /api/update` не дає 500 за жодного збою `git` — відповідь `not-git` (клоном не вважаємо)."""
        try:
            return self._blocked()
        except Exception:  # noqa: BLE001
            return 'not-git'

    def _blocked(self):
        """Код причини, чому оновлення зараз не можна застосувати (`None` — можна). Лише читальні виклики `git`."""
        if not os.path.exists(os.path.join(self.root, '.git')):
            return 'not-git'
        rc, out, _ = self.run(['rev-parse', '--git-dir', '--git-common-dir'], self.root, LOCAL_GIT_TIMEOUT_S)
        if rc == 127:
            return 'not-git'
        lines = out.split('\n') if rc == 0 else []
        if len(lines) >= 2 and lines[0] and lines[1] and (
                os.path.realpath(os.path.join(self.root, lines[0])) != os.path.realpath(os.path.join(self.root, lines[1]))):
            return 'worktree'
        rc, _, _ = self.run(['symbolic-ref', '-q', 'HEAD'], self.root, LOCAL_GIT_TIMEOUT_S)
        if rc != 0:
            return 'detached'
        rc, out, _ = self.run(['status', '--porcelain', '--untracked-files=no'], self.root, LOCAL_GIT_TIMEOUT_S)
        if rc != 0:
            return 'not-git'                                   # статус не прочитався — клоном не вважаємо
        if out.strip():
            return 'dirty'
        try:
            if self.busy():
                return 'busy'
        except Exception:  # noqa: BLE001 — зламаний датчик не блокує показ
            pass
        return None

    # --- застосування ---

    @staticmethod
    def _fail(status, code, **extra):
        return status, {'ok': False, 'code': code, **extra}

    def apply(self):
        """Застосувати `latest` зі стану → `(http_status, body)`. Не кидає. НІЧОГО не приймає ззовні (ні версії, ні шляху, ні remote).
        Рестарт НЕ планує: `serve` робить це ПІСЛЯ відправки відповіді. Кожна відмова — код, робоче дерево при цьому не змінене (крім
        `rolled-back`, де воно повернуте на старий HEAD)."""
        try:
            if (isolation.isolated() and not os.environ.get('DEAI_UPDATE_TEST_APPLY')
                    and os.path.realpath(self.root) == os.path.realpath(PRODUCT_ROOT)):
                return self._fail(409, 'isolated')       # ізольований прогін не міняє справжній код
            if not self._apply_lock.acquire(blocking=False):
                return self._fail(409, 'busy')
            try:
                return self._apply_locked()
            finally:
                self._apply_lock.release()
        except Exception:  # noqa: BLE001
            return self._fail(500, 'error')

    def _apply_locked(self):
        state = self._load()
        latest = state.get('latest') if isinstance(state.get('latest'), str) else None
        current = current_version(self.root)
        lt, ct = (parse_tag('v' + latest) if latest else None), version_tuple(current)
        if not (lt and ct and lt > ct):
            return self._fail(409, 'nothing-to-update')
        tag = 'v' + latest                                # TAG_RE (parse_tag вище) пройдено ДО будь-якого `git`
        blocked = self._blocked()
        if blocked:
            return self._fail(409, blocked)
        _, url, err = remote_for(self.root, self.run)      # адреса — ЗАРАЗ, не зі збереженого
        if err:
            return self._fail(409, 'not-git' if err == 'no-git-binary' else err)
        if not network_allowed(url):
            return self._fail(409, 'disabled')
        rc, out, _ = self.run(['rev-parse', '--verify', 'HEAD'], self.root, LOCAL_GIT_TIMEOUT_S)
        old = out.strip() if rc == 0 else ''
        if not _SHA_RE.match(old):
            return self._fail(500, 'error')
        failure = self._fetch_tag(url, tag)
        if failure:
            return self._fail(*failure)
        rc, out, _ = self.run(['rev-parse', '--verify', '%s^{commit}' % tag], self.root, LOCAL_GIT_TIMEOUT_S)
        target = out.strip() if rc == 0 else ''
        if not _SHA_RE.match(target):
            return self._fail(500, 'error')                # далі працюємо з sha, а не з рухомим іменем
        rc, out, _ = self.run(['cat-file', 'blob', '%s:package.json' % target], self.root, LOCAL_GIT_TIMEOUT_S)
        try:
            tagged = str(json.loads(out).get('version')) if rc == 0 else None
        except (ValueError, AttributeError):
            tagged = None
        if tagged != latest:
            return self._fail(409, 'tag-mismatch')
        rc, _, _ = self.run(['merge-base', '--is-ancestor', old, target], self.root, LOCAL_GIT_TIMEOUT_S)
        if rc == 1:
            return self._fail(409, 'diverged', hint='merge-hint')
        if rc != 0:
            return self._fail(500, 'error')
        rc, out, _ = self.run(['status', '--porcelain', '--untracked-files=no'], self.root, LOCAL_GIT_TIMEOUT_S)
        if rc != 0:
            return self._fail(500, 'error')
        if out.strip():                                    # правка зʼявилась за час fetch: merge не робимо, reset не робимо
            return self._fail(409, 'dirty')
        rc, _, _ = self.run(['-c', 'gc.auto=0', 'merge', '--ff-only', target], self.root, MERGE_TIMEOUT_S)
        if rc != 0:
            return self._after_failed_merge(old, target, rc)
        try:
            smoke_ok = smoke_check(self.root)
        except Exception:  # noqa: BLE001
            smoke_ok = False
        if not smoke_ok:
            return self._rollback(old)
        try:                                               # оновлення вже вдалось: збій запису стану не скасовує ні 202, ні рестарт
            with self._lock:
                state = self._load()
                state.pop('restart_failed', None)
                state['last_update'] = {'from': current, 'to': latest, 'at': int(self.clock())}
                self._save(state)
        except Exception:  # noqa: BLE001
            pass
        return 202, {'ok': True, 'to': latest, 'restart': 'manual' if _is_windows() else 'auto'}


    def _fetch_tag(self, url, tag, blocking=True):
        """ЄДИНИЙ `fetch` тега (`apply` і `notes`): лише обʼєкти й `refs/tags/<tag>`, робоче дерево, індекс і HEAD не чіпаються. `None` — вдало;
        інакше `(http_status, code)`. `tag` уже пройшов `TAG_RE`; `fsckObjects` відкидає зіпсовані обʼєкти; `LC_ALL=C` — стабільний stderr."""
        refspec = 'refs/tags/%s:refs/tags/%s' % (tag, tag)
        if not self._fetch_lock.acquire(blocking=blocking):
            return 503, 'busy'                            # лише для `notes`: його GET не стає в чергу за чужим `fetch`
        try:
            rc, _, err_text = self.run(['-c', 'transfer.fsckObjects=true', '-c', 'fetch.fsckObjects=true', '-c', 'gc.auto=0',
                                        'fetch', '--no-tags', '--no-recurse-submodules', '--', url, refspec],
                                       self.root, FETCH_TIMEOUT_S, {'LC_ALL': 'C'})
        finally:
            self._fetch_lock.release()
        if rc == 0:
            return None
        if rc == 127:
            return 409, 'not-git'
        low = (err_text or '').lower()
        if 'clobber' in low:
            return 409, 'tag-conflict'
        if "couldn't find remote ref" in low:
            return 409, 'tag-missing'
        if any(m in low for m in _FETCH_REJECTED_MARKERS):
            return 409, 'fetch-rejected'                  # fsck/пошкоджений обʼєкт: це не «нема мережі»
        return 503, 'offline'

    # --- «Що нового» ---

    @staticmethod
    def _notes_empty(reason, version=None):
        out = {'ok': True, 'sections': [], 'reason': reason}
        if version:
            out['version'] = version
        return out

    def notes(self):
        """`GET /api/update-notes` → `{ok, version, sections: [{version, date, body}], reason?}`. Не кидає. Розділи `(current, latest]` беруться з
        CHANGELOG ВІДДАЛЕНОГО тега (локальний ще не має нової версії): `fetch` тега, `git show <sha>:CHANGELOG.md` (≤ 1 МБ), кеш у `update.json`.
        Дерево/індекс/HEAD не чіпаються. У відповіді лише коди й текст — без адрес і шляхів."""
        try:
            return self._notes()
        except Exception:  # noqa: BLE001
            return self._notes_empty('error')

    def _cached_notes(self, state, latest, current):
        c = state.get('notes')
        if not (isinstance(c, dict) and c.get('version') == latest and c.get('after') == current
                and c.get('remote_id') == state.get('remote_id') and isinstance(c.get('sections'), list)):
            return None
        out = []
        for s in c['sections']:
            if not (isinstance(s, dict) and all(isinstance(s.get(k), str) for k in ('version', 'date', 'body'))):
                return None
            out.append({'version': s['version'], 'date': s['date'], 'body': _cap_bytes(_plain(s['body']), NOTES_SECTION_MAX_BYTES)})
        return out

    def _notes_failed(self, reason, latest):
        """Невдача ПІСЛЯ спроби мережі (`fetch`, далі `rev-parse`/`cat-file`): запамʼятовуємо її на `NOTES_FAIL_TTL_S`, щоб кожен `GET /api/update-notes`
        не повторював `fetch`. `busy` (чужий `fetch` іде) не кешуємо — це не відповідь про тег, а чергу."""
        if reason != 'busy':
            with self._lock:
                state = self._load()
                state['notes_fail'] = {'version': latest, 'remote_id': state.get('remote_id'), 'reason': reason, 'at': int(self.clock())}
                self._save(state)
        return self._notes_empty(reason, latest)

    def _notes(self):
        state = self._load()
        latest = state.get('latest') if isinstance(state.get('latest'), str) else None
        current = current_version(self.root)
        lt, ct = (parse_tag('v' + latest) if latest else None), version_tuple(current)      # TAG_RE ДО будь-якого `git`
        if not (lt and ct and lt > ct):
            return self._notes_empty('no-update')
        cached = self._cached_notes(state, latest, current)
        if cached is not None:
            return {'ok': True, 'version': latest, 'sections': cached}
        fail = state.get('notes_fail')
        if (isinstance(fail, dict) and fail.get('version') == latest and fail.get('remote_id') == state.get('remote_id')
                and isinstance(fail.get('reason'), str) and isinstance(fail.get('at'), (int, float))
                and 0 <= self.clock() - fail['at'] < NOTES_FAIL_TTL_S):
            return self._notes_empty(fail['reason'], latest)       # негативний кеш: GET не б'є в мережу частіше за раз на хвилину
        if not os.path.exists(os.path.join(self.root, '.git')):
            return self._notes_empty('no-git', latest)
        _, url, err = remote_for(self.root, self.run)
        if err:
            return self._notes_empty('no-git' if err == 'no-git-binary' else err, latest)
        if not network_allowed(url):
            return self._notes_empty('disabled', latest)
        tag = 'v' + latest
        failure = self._fetch_tag(url, tag, blocking=False)
        if failure:
            return self._notes_failed('no-git' if failure[1] == 'not-git' else failure[1], latest)
        rc, out, _ = self.run(['rev-parse', '--verify', '%s^{commit}' % tag], self.root, LOCAL_GIT_TIMEOUT_S)
        target = out.strip() if rc == 0 else ''
        if not _SHA_RE.match(target):
            return self._notes_failed('error', latest)      # далі — sha, а не рухоме імʼя
        rc, data = git_head(['cat-file', 'blob', '%s:CHANGELOG.md' % target], self.root, NOTES_MAX_BYTES, LOCAL_GIT_TIMEOUT_S)
        if rc == 127:
            return self._notes_failed('no-git', latest)
        if rc != 0:
            return self._notes_failed('no-changelog', latest)
        sections = parse_changelog(data.decode('utf-8', 'replace'), current, latest)
        with self._lock:
            state = self._load()
            state['notes'] = {'version': latest, 'after': current, 'remote_id': state.get('remote_id'), 'sections': sections}
            state.pop('notes_fail', None)
            self._save(state)
        return {'ok': True, 'version': latest, 'sections': sections}

    def _rollback(self, old):
        """ЄДИНЕ місце з `reset` у модулі: `reset --hard <old>` (`old` — 40-hex, перевірений раніше). Лише після `merge`, що чіпав дерево."""
        rc, _, _ = self.run(['-c', 'gc.auto=0', 'reset', '--hard', old], self.root, MERGE_TIMEOUT_S)
        return self._fail(500, 'rolled-back' if rc == 0 else 'rollback-failed')

    def _after_failed_merge(self, old, target, merge_rc):
        """`merge` не вдався (зокрема вбитий за тайм-аутом): правди про дерево не знаємо, тож перечитуємо. HEAD == old й дерево чисте →
        справді нічого не змінилось (`merge-failed`); HEAD == target, або HEAD == old із брудним деревом І rc == 124 (вбили ми) → відкат до `old`; HEAD == old і інший rc → `merge-failed` (ff-only атомарний,
        брудне дерево — правки користувача, їх не скидаємо); HEAD будь-який
        інший — хтось рухав гілку, НЕ чіпаємо (`error`). `index.lock` не видаляємо."""
        rc, out, _ = self.run(['rev-parse', '--verify', 'HEAD'], self.root, LOCAL_GIT_TIMEOUT_S)
        head = out.strip() if rc == 0 else ''
        rc, out, _ = self.run(['status', '--porcelain', '--untracked-files=no'], self.root, LOCAL_GIT_TIMEOUT_S)
        clean = rc == 0 and not (out or '').strip()
        dirty = rc == 0 and not clean
        if head == old and clean:
            return self._fail(500, 'merge-failed')
        if head == target or (head == old and dirty and merge_rc == 124):    # 124 — ми самі вбили merge; інакше ff-only атомарний
            return self._rollback(old)
        if head == old:
            return self._fail(500, 'merge-failed')          # дерево брудне через правку користувача: НЕ скидаємо
        return self._fail(500, 'error')

    def mark_restart_failed(self):
        """Перезапуск після оновлення не вдався: прапорець (привʼязаний до ЦЬОГО процесу — після ручного перезапуску він застарів сам)."""
        try:
            with self._lock:
                state = self._load()
                state['restart_failed'] = BOOT
                self._save(state)
        except Exception:  # noqa: BLE001
            pass


#: Смоук нового коду в ДОЧІРНЬОМУ процесі (`python -B -I`: ні `.pyc`, ні `sys.path` старого процесу): усі `app/*.py` і `bin/*.py` компілюються
#: (синтаксис), потім `import serve` (зламаний імпорт). `py_compile` не годиться: пише `.pyc` навіть при `-B`.
_SMOKE_CODE = r"""
import os, sys
root = sys.argv[1]
for sub in ('app', 'bin'):
    d = os.path.join(root, sub)
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            if name.endswith('.py'):
                p = os.path.join(d, name)
                with open(p, 'rb') as f:
                    compile(f.read(), p, 'exec')
sys.path.insert(0, os.path.join(root, 'app'))
import serve
"""


def smoke_check(root):
    """`True`, коли код у `root` компілюється й `serve` імпортується. Оточення дитини — вичищене й ізольоване: тимчасові `HOME`,
    `DEAI_HOME`, `DC_TASKS_FILE`, `DEAI_NO_UPDATE_CHECK=1`; тимчасові теки видаляються після."""
    tmp = tempfile.mkdtemp(prefix='deai-smoke-')
    try:
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'SYSTEMROOT') if k in os.environ}
        env.update({'HOME': home, 'USERPROFILE': home, 'TMPDIR': tmp, 'DEAI_HOME': os.path.join(tmp, 'deai'),
                    'DC_TASKS_FILE': os.path.join(tmp, 'tasks.json'), 'DEAI_NO_UPDATE_CHECK': '1',
                    'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'})
        rc, _, _ = _communicate([sys.executable, '-B', '-I', '-c', _SMOKE_CODE, root], root, env, SMOKE_TIMEOUT_S)
        return rc == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- перезапуск ---

_RESTART_SNAPSHOT = None


def _is_windows():
    return os.name == 'nt'


def snapshot_restart():
    """Знімок «як мене запустили» (викликати ПЕРШИМ у `serve_main`, до будь-якого `chdir`): `{cwd, argv}`. `orig_argv` (3.10+) зберігає
    прапорці інтерпретатора; нижче — `sys.argv`."""
    global _RESTART_SNAPSHOT
    rest = list(sys.orig_argv[1:]) if getattr(sys, 'orig_argv', None) else list(sys.argv)
    _RESTART_SNAPSHOT = {'cwd': os.getcwd(), 'argv': [sys.executable] + rest}
    return _RESTART_SNAPSHOT


def exec_restart(snapshot=None, execv=os.execv):
    """Замінити процес собою ж (той самий PID, те саме оточення). `False` (і нічого не викликано), коли: ізольований прогін без шва
    `DEAI_UPDATE_TEST_APPLY`; Windows (`execv` там не замінює процес — перезапуск вручну); знімка нема. Успіх не повертається."""
    if isolation.isolated() and not os.environ.get('DEAI_UPDATE_TEST_APPLY'):
        return False
    if _is_windows():
        return False
    snap = snapshot or _RESTART_SNAPSHOT
    if not snap or not snap.get('argv') or not isinstance(snap.get('cwd'), str):
        return False
    here = None
    try:
        here = os.getcwd()
        os.chdir(snap['cwd'])
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:  # noqa: BLE001
                pass
        execv(snap['argv'][0], snap['argv'])
    except OSError:
        if here:
            try:
                os.chdir(here)
            except OSError:
                pass
    return False


def start_background(upd, stop=None, first_delay=FIRST_CHECK_DELAY_S, every=CHECK_EVERY_S, rand=random.random):
    """Daemon-потік: перша перевірка через `first_delay` с (не блокує старт), далі кожні `every` с. З `DEAI_NO_UPDATE_CHECK=1` потік не
    стартує (`None`), але `check()` лишається доступною вручну. Зупинка — `t.stop_event.set()`. Розкид (`rand` — шов тестів): перша перевірка
    `first_delay` + 0…25 с, період `every` ±10 %: сотні копій не б'ють у remote одночасно."""
    if os.environ.get('DEAI_NO_UPDATE_CHECK') == '1':
        return None
    stop = stop or threading.Event()

    def loop():
        if stop.wait(first_delay + rand() * FIRST_CHECK_JITTER_S):
            return
        while True:
            try:
                upd.check()
            except Exception:  # noqa: BLE001
                pass
            if stop.wait(every * (1 - PERIOD_JITTER + 2 * PERIOD_JITTER * rand())):
                return

    t = threading.Thread(target=loop, name='deai-update-check', daemon=True)
    t.stop_event = stop
    t.start()
    return t
