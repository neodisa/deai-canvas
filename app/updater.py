"""Оновлення інструмента (0.23.0): версія, remote, перевірка тегів `vX.Y.Z`, файл стану `update.json`, фоновий потік.

Це ядро ЧИТАННЯ: нічого не змінює в робочому дереві (`apply` — окрема задача). Правила, що тримають модуль безпечним:

* Тег — лише `^v\\d+\\.\\d+\\.\\d+\\Z` (без пре-релізів); усе інше з `ls-remote` ігнорується. Порівняння — за числами, не за рядками.
* `remote` (змінна `DEAI_UPDATE_REMOTE`, upstream гілки) — недовірений рядок для `git`: дозволені імʼя remote, `https://`/`ssh://`,
  `git@host:path`, абсолютний шлях (`check_remote`). Усі виклики `git` — з `-c protocol.ext.allow=never` і з `--` перед адресою.
* Відповідь API несе лише ХОСТ remote (`remote_host`), ніколи userinfo й шляхи; `reason` — короткий код, а не текст помилки `git`.
* Мережа — лише через `network_allowed`: remote-шлях файлової системи дозволений завжди; будь-який інший — коли НЕ
  (`DEAI_NO_UPDATE_CHECK=1` або `isolation.isolated()`). Інакше `state: 'disabled'`, `git` не викликається.
* Читальні виклики `git` мають `GIT_OPTIONAL_LOCKS=0`: `git status` не оновлює індекс живого дерева.
* `update.json` (0600) не пишеться, коли `isolation.writes_allowed(home)` — стан тоді лише в памʼяті процесу.
* `BOOT` — випадковий токен, що виникає при ІМПОРТІ: після `execv` модуль імпортується наново, тож клієнт бачить, що процес інший.

Імпортує лише `isolation`, `spaces`, `atomic_io` (без `serve`: цикл неможливий).
"""
import json
import hashlib
import os
import random
import re
import secrets
import signal
import subprocess
import threading
import time

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
FIRST_CHECK_DELAY_S = 5
FIRST_CHECK_JITTER_S = 25
PERIOD_JITTER = 0.1
STATES = ('ok', 'offline', 'no-git', 'error', 'disabled')
BOOT = secrets.token_hex(8)

_NAME_RE = re.compile(r'^[A-Za-z0-9][\w.-]*\Z')
_URL_RE = re.compile(r'^(?:https|ssh)://[^\s\x00-\x1f\\/-][^\s\x00-\x1f\\]*\Z')
_HOST_START_RE = re.compile(r'^[A-Za-z0-9\[]')
#: Змінні `git`, що перекривають репо/конфіг: з успадкованого оточення вилучаються.
_GIT_SCRUB = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
              'GIT_CONFIG', 'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT')
_GIT_SCRUB_PREFIXES = ('GIT_CONFIG_KEY_', 'GIT_CONFIG_VALUE_')
_SCP_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.-]*:[^\s\x00-\x1f]+\Z')
_PATH_RE = re.compile(r'^/[^\x00-\x1f]*\Z')
_HOST_URL_RE = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*://(?:[^/\s]*@)?(\[[^\]]*\]|[^/:?#\s]+)')
_HOST_SCP_RE = re.compile(r'^(?:[^@/\s]+@)?([^:/\s]+):')


def run_git(args, cwd, timeout, env_extra=None):
    """`git` без оболонки → `(rc, stdout, stderr)`. Тайм-аут — `(124, '', 'timeout')` (уся група процесів убивається: `ssh` теж), нема
    `git` — `(127, '', 'no-git-binary')`. Оточення: без успадкованих `GIT_DIR`/`GIT_WORK_TREE`/`GIT_CONFIG*` тощо (`_GIT_SCRUB`)."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_SCRUB and not k.startswith(_GIT_SCRUB_PREFIXES)}
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GCM_INTERACTIVE'] = 'never'
    env['GIT_OPTIONAL_LOCKS'] = '0'
    if 'GIT_SSH_COMMAND' not in env:
        env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes -o ConnectTimeout=10'
    env.update(env_extra or {})
    try:
        p = subprocess.Popen(['git', '-c', 'protocol.ext.allow=never'] + list(args), cwd=cwd, env=env, text=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=(os.name != 'nt'))
    except FileNotFoundError:
        return 127, '', 'no-git-binary'
    except OSError as e:
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
            pass
        return 124, '', 'timeout'
    return p.returncode, out, err


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
            'blocked': self._blocked() if available else None,
            'remote_host': state.get('remote_host') if isinstance(state.get('remote_host'), str) else None,
            'last_update': state.get('last_update') if isinstance(state.get('last_update'), dict) else None,
            'boot': BOOT,
        }

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
