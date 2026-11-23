"""Stop-хук Claude Code простору (23.11.2026): «Підключити» ставить у `hooks.Stop` файла `<простір>/.claude/settings.local.json`
ОДНУ нашу групу, яка після кожної відповіді Claude шле канвасу JSON сесії на `POST /api/autosync` (сервер бере з нього лише `cwd`).

Лише ця машина: локальний файл налаштувань теки простору, не командний `.claude/settings.json` і не глобальний `~/.claude`.
Наш хук відрізняє від чужих мітка `# deai-autosync` наприкінці команди — інших ознак нема. Хук завжди тихий: без виводу, `|| true`,
канвас вимкнено → нічого. Windows на справжній машині не перевірено (команда — синтаксис sh).

Запис — злиття, а не перезапис: чужі хуки й ключі лишаються; наші групи (точніше, наші записи в групах) прибираємо й ставимо одну
свіжу, тож повторне «Підключити» не дублює. Нечитне (лише для читання, симлінк, не-звичайний файл чи тека `.claude`, не UTF-8, не JSON, верхній
рівень не обʼєкт, `hooks` не обʼєкт, `hooks.Stop` не список) не чіпаємо взагалі: стан `unreadable`, `connect`/`disconnect` → `OSError`.
Запис атомарний (тимчасовий файл у `.claude/`, `fsync`, права як у наявного, новий — за umask); перед заміною файл читається ще раз,
і зміна (чужа правка, файл, що зʼявився) — `ValueError('changed')`. Форматування файла може змінитись (відступ 2 пробіли), числа — нормалізуватись (`1E5` → `100000.0`).
"""
import json
import os
import uuid

HOOK_MARK = '# deai-autosync'
FILE = '.claude/settings.local.json'
EXCLUDE_LINE = '/' + FILE
#: Шов тестів: на Windows стану `elsewhere` нема (там файл завжди поруч із `.claude/settings.json`).
_WINDOWS = os.name == 'nt'


def _home():
    """Домашня тека (шов тестів): її `.git` і все вище — не «інший репозиторій»."""
    return os.path.expanduser('~')


def command(port):
    """Команда хука для порту канваса. `port` не число → `ValueError` (у shell-рядок потрапляє лише ціле)."""
    if isinstance(port, bool):
        raise ValueError('port')
    return ("curl -s --noproxy '*' --max-time 5 -o /dev/null -X POST -H 'Content-Type: application/json' --data-binary @- "
            f"http://127.0.0.1:{int(port)}/api/autosync || true {HOOK_MARK}")


def _dir(space_dir):
    return os.path.join(space_dir, os.path.dirname(FILE))


def _path(space_dir):
    return os.path.join(space_dir, *FILE.split('/'))


def _read_raw(space_dir):
    """Байти файла налаштувань чи `None` (файла нема). Симлінк чи не-тека `.claude`, симлінк чи не-звичайний файл, відмова
    читання — `OSError`: такий файл ми не читаємо й не замінюємо (заміна розірвала б симлінк)."""
    d = _dir(space_dir)
    if os.path.islink(d) or (os.path.lexists(d) and not os.path.isdir(d)):
        raise OSError('.claude: not a directory')
    p = _path(space_dir)
    if os.path.islink(p) or (os.path.lexists(p) and not os.path.isfile(p)):
        raise OSError('settings.local.json: not a regular file')
    if os.path.exists(p) and not (os.stat(p).st_mode & 0o200):
        raise OSError('settings.local.json: read-only')      # людина закрила файл від запису: не замінюємо його через теку
    try:
        with open(p, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        return None


def _dump(doc):
    """Байти файла для `doc`: відступ 2, без `\\u`-екранування, з кінцевим переводом рядка. Те, що не серіалізується без втрат
    (самотній сурогат, `inf`/`NaN`), — `OSError`: такий файл ми не пишемо."""
    try:
        return (json.dumps(doc, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, RecursionError):      # UnicodeEncodeError — теж ValueError
        raise OSError('settings.local.json: cannot be rewritten losslessly') from None


def _no_const(name):
    raise ValueError(name)


def _no_dupes(pairs):
    """Повтор ключа обʼєкта (на будь-якому рівні) загубився б при перезаписі — такий файл не чіпаємо."""
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('duplicate key')
        out[k] = v
    return out


def _parse(raw):
    """Обʼєкт налаштувань з байтів (`None` → `{}`); усе, з чим ми не вміємо зливати чи що не перезаписати без втрат, — `OSError`."""
    if raw is None:
        return {}
    try:
        doc = json.loads(raw.decode('utf-8'), parse_constant=_no_const, object_pairs_hook=_no_dupes)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise OSError('settings.local.json: not JSON') from None
    if not isinstance(doc, dict):
        raise OSError('settings.local.json: not an object')
    if 'hooks' in doc:
        hooks = doc['hooks']
        if not isinstance(hooks, dict):
            raise OSError('settings.local.json: hooks is not an object')
        if 'Stop' in hooks and not isinstance(hooks['Stop'], list):
            raise OSError('settings.local.json: hooks.Stop is not a list')
    _dump(doc)      # не перезаписується без втрат (`1e999`, самотній сурогат) → нечитне вже тут
    return doc


def _is_ours(h):
    return isinstance(h, dict) and isinstance(h.get('command'), str) and h['command'].rstrip().endswith(HOOK_MARK)


def _our_hooks(doc):
    out = []
    for g in (doc.get('hooks') or {}).get('Stop') or []:
        if isinstance(g, dict) and isinstance(g.get('hooks'), list):
            out += [h for h in g['hooks'] if _is_ours(h)]
    return out


def _strip(doc, prune):
    """Прибрати наші записи з `hooks.Stop` (на місці). Група, що спорожніла через нас, зникає; чужі записи тієї самої групи
    лишаються. `prune` — ще й прибрати порожні `Stop` і `hooks`, що спорожніли через нас. Повертає `(doc, скільки прибрано)`."""
    hooks = doc.get('hooks')
    if not isinstance(hooks, dict) or not isinstance(hooks.get('Stop'), list):
        return doc, 0
    kept, removed = [], 0
    for g in hooks['Stop']:
        if isinstance(g, dict) and isinstance(g.get('hooks'), list) and any(_is_ours(h) for h in g['hooks']):
            rest = [h for h in g['hooks'] if not _is_ours(h)]
            removed += len(g['hooks']) - len(rest)
            if rest:
                kept.append({**g, 'hooks': rest})
            continue
        kept.append(g)
    if removed == 0:
        return doc, 0
    if kept or not prune:
        hooks['Stop'] = kept
    else:
        del hooks['Stop']
        if not hooks:
            del doc['hooks']
    return doc, removed


def _add(doc, port):
    doc.setdefault('hooks', {}).setdefault('Stop', []).append(
        {'hooks': [{'type': 'command', 'timeout': 10, 'command': command(port)}]})


def _elsewhere(space_dir):
    """Тека простору всередині ІНШОГО git-репозиторію: `.git` є в предку, а не в самій теці (`.git` — тека чи файл). Домашня тека
    й усе вище не рахуються. Claude Code тоді читає `settings.local.json` з кореня того репозиторію, а туди ми не пишемо."""
    if _WINDOWS:
        return False
    cur = os.path.realpath(space_dir)
    home = os.path.realpath(_home())
    if cur == home or os.path.lexists(os.path.join(cur, '.git')):
        return False
    cur = os.path.dirname(cur)
    while True:
        if cur == home:
            return False
        if os.path.lexists(os.path.join(cur, '.git')):
            return True
        up = os.path.dirname(cur)
        if up == cur:
            return False
        cur = up


def status(space_dir, port):
    """`{state, path}`; ніколи не кидає. `elsewhere` (хук тут не діє) — раніше за решту; далі `unreadable`, `missing` (нашого хука
    нема), `stale` (є, але команда інша для `port` чи записів більше одного), `ok`."""
    p = _path(space_dir)
    try:
        if _elsewhere(space_dir):
            return {'state': 'elsewhere', 'path': p}
        ours = _our_hooks(_parse(_read_raw(space_dir)))
        if not ours:
            state = 'missing'
        elif len(ours) == 1 and ours[0].get('command') == command(port):
            state = 'ok'
        else:
            state = 'stale'
        return {'state': state, 'path': p}
    except Exception:  # noqa: BLE001 — статус для UI не кидає: що б не сталось, це «не читається»
        return {'state': 'unreadable', 'path': p}


def _write(space_dir, doc, before):
    """Атомарний запис `doc`; `before` — байти, які ми читали (`None` — файла не було). Інакше `ValueError('changed')`."""
    data = _dump(doc)      # раніше за `makedirs`: відмова не лишає порожнього `.claude/`
    d = _dir(space_dir)
    os.makedirs(d, exist_ok=True)
    path = _path(space_dir)
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        mode = None
    tmp = os.path.join(d, f'.settings.local.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)     # права нового файла — за umask
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        if _read_raw(space_dir) != before:      # файл змінили між читанням і заміною: чужу правку не губимо
            raise ValueError('changed')
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _exclude(space_dir):
    """Локально сховати наш файл від git: `.git/info/exclude` (спільний `.gitignore` не чіпаємо). Раз; лише коли `.git` — тека
    (файл `.git` — worktree чи submodule — не чіпаємо). Best-effort: збій тут не провалює «Підключити»."""
    g = os.path.join(space_dir, '.git')
    if os.path.islink(g) or not os.path.isdir(g):
        return
    p = os.path.join(g, 'info', 'exclude')
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            with open(p, encoding='utf-8', errors='surrogateescape', newline='') as f:
                old = f.read()
        except FileNotFoundError:
            old = ''
        if EXCLUDE_LINE in [ln.strip() for ln in old.splitlines()]:
            return
        with open(p, 'a', encoding='utf-8', errors='surrogateescape', newline='') as f:
            f.write(('' if not old or old.endswith('\n') else '\n') + EXCLUDE_LINE + '\n')
    except OSError:
        pass


def connect(space_dir, port):
    """«Підключити»: поставити (чи оновити) наш хук. Повертає `status` після запису. `elsewhere` — нічого не пишемо; `ok` — запису нема;
    нечитне — `OSError`; зміна під час запису — `ValueError('changed')`. Файл, який створили МИ, ховаємо в `.git/info/exclude`."""
    st = status(space_dir, port)
    if st['state'] == 'elsewhere' or st['state'] == 'ok':
        return st
    if st['state'] == 'unreadable':
        raise OSError('unreadable')
    raw = _read_raw(space_dir)
    doc, _ = _strip(_parse(raw), prune=False)
    _add(doc, port)
    _write(space_dir, doc, raw)
    if raw is None:
        _exclude(space_dir)
    return status(space_dir, port)


def disconnect(space_dir, port):
    """«Відключити»: прибрати наші записи; порожні `Stop` і `hooks`, що спорожніли через нас, — теж; файл, що став `{}`, видаляємо
    (тека `.claude/` лишається). Нічого нашого нема — нічого не пишемо. Нечитне — `OSError`; зміна — `ValueError('changed')`."""
    raw = _read_raw(space_dir)
    doc, removed = _strip(_parse(raw), prune=True)
    if removed:
        if doc:
            _write(space_dir, doc, raw)
        else:
            if _read_raw(space_dir) != raw:
                raise ValueError('changed')
            os.remove(_path(space_dir))
    return status(space_dir, port)
