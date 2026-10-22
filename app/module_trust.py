"""Свої модулі простору (етап 3c, спека `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`).

Тут — усе, що стосується ДОВІРИ, і нічого з ядра модулів: сканер теки модуля, хеш, порівняння з довіреним (Task 1);
записи `<DEAI_HOME>/trust.json`, знімки `<DEAI_HOME>/trusted/<хеш>/` і системне вікно підтвердження (Task 2). Не
імпортує ні `serve`, ні `deai_modules` (вони імпортують його); з ядра бере лише `spaces` (домівка, шар).

Правила теки (`scan`): обхід без переходу за посиланнями, глибина ≤ `MAX_DEPTH`; лише теки й звичайні файли з
`st_nlink == 1`; `.DS_Store`, теки `__pycache__` і `.git`, файли `*.pyc` пропускаються (не в хеші, не в знімку), бо їх
плодять Finder, локальний запуск і git; ≤ `MAX_FILES` файлів і ≤ `MAX_BYTES` разом — обхід обривається на першому
перевищенні, не читаючи решти; імена — `name_ok` і без двійників за регістром/NFC (`twin_key`). Перше порушення —
`Refused(code, detail)`. Кожен файл читається один раз (`O_NOFOLLOW|O_NONBLOCK`, `fstat` того ж дескриптора).

Хеш теки — sha256 рядків `"<шлях>\\0<розмір>\\0<sha256>\\n"` (UTF-8), відсортованих за UTF-8 байтами шляху.
"""
import errno
import hashlib
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from collections import namedtuple

import spaces
from atomic_io import WRITE_LOCK, atomic_write_json

MAX_FILES = 200
MAX_BYTES = 5 * 1024 * 1024
MAX_DEPTH = 8
#: Скільки записів дерева бере `fingerprint` — з запасом над `MAX_FILES` (пропущені `*.pyc` теж записи).
FP_MAX = 2000
SKIP_FILES = frozenset({'.DS_Store'})
SKIP_DIRS = frozenset({'__pycache__', '.git'})
SKIP_SUFFIXES = ('.pyc',)
_WIN_RESERVED = frozenset({'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(10)), *(f'lpt{i}' for i in range(10))})
_REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
_OPEN_FLAGS = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)

#: Причини відмови сканера (`Refused.code`). `bad-manifest` ставить ядро (`deai_modules`), не сканер.
REFUSAL_CODES = ('symlink', 'hardlink', 'special-file', 'too-many-files', 'too-big', 'too-deep', 'bad-name',
                 'unreadable', 'unstable', 'bad-manifest')


class Refused(Exception):
    """Теку не можна довірити: `code` — з `REFUSAL_CODES`, `detail` — відносний шлях і пояснення (≤300, лише ASCII-
    безпечне для показу: імена з керівними символами екрануються)."""

    def __init__(self, code, detail=''):
        self.code = code
        self.detail = str(detail)[:300]
        super().__init__(f'{code}: {self.detail}' if self.detail else code)


#: Результат сканування: `hash` теки; `files` — кортеж `(шлях, розмір, sha256)` за UTF-8 байтами шляху; `total` — байтів
#: разом; `manifest` — байти `module.json` (чи `None`); `data` — `{шлях: байти}` лише з `with_data=True`, інакше `None`.
Scan = namedtuple('Scan', 'hash files total manifest data')


def name_ok(name):
    """Імʼя файла чи теки придатне: кодується в UTF-8, без символів категорій `Cc`/`Cf`/`Zl`/`Zp` (керівні, двонапрямні —
    U+202E підробив би перелік файлів у діалозі), не зарезервоване у Windows (`CON`, `nul.txt`…), без крапки чи пробілу
    в кінці, не `.`/`..`."""
    if not isinstance(name, str) or not name or name in ('.', '..'):
        return False
    try:
        name.encode('utf-8')
    except UnicodeEncodeError:
        return False
    if any(unicodedata.category(c) in ('Cc', 'Cf', 'Zl', 'Zp') for c in name):
        return False
    if name[-1] in '. ':
        return False
    return name.split('.', 1)[0].lower() not in _WIN_RESERVED


def twin_key(name):
    """Ключ двійників: два імені однієї теки з однаковим ключем на нечутливій до регістру чи нормалізації ФС — один
    файл, і знімок розійшовся б із хешем."""
    return unicodedata.normalize('NFC', name).casefold()


def _shown(rel):
    """Шлях для тексту відмови: керівні, двонапрямні й одинокі сурогати (імʼя з не-UTF-8 байтами, `surrogateescape`) —
    `\\uXXXX`, решта як є. Сурогат не кодується в UTF-8: `_send_json` має запасний `ensure_ascii`, але інші приймачі
    (запис JSON з `ensure_ascii=False` у файли, `argv` підпроцесу, лог) на ньому падають."""
    return ''.join(c if unicodedata.category(c) not in ('Cc', 'Cf', 'Zl', 'Zp', 'Cs') else f'\\u{ord(c):04x}'
                   for c in rel)


def _lstat(p, rel):
    try:
        return os.lstat(p)
    except OSError:
        raise Refused('unreadable', _shown(rel) or '.') from None


def _is_link(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & _REPARSE)


#: Для ядра (`deai_modules`: сама тека `modules/` простору): посилання — і точка повторного розбору Windows теж.
is_link = _is_link


def _walk(root):
    """`[(відносний шлях, абсолютний шлях, lstat)]` файлів теки `root` за UTF-8 байтами шляху — з усіма перевірками
    структури й меж, БЕЗ читання вмісту. Перше порушення — `Refused`."""
    st = _lstat(root, '')
    if _is_link(st):
        raise Refused('symlink', '.')
    if not stat.S_ISDIR(st.st_mode):
        raise Refused('special-file', '.')
    out = []
    total = 0

    def rec(d, rel, depth):
        nonlocal total
        try:
            names = sorted(os.listdir(d))
        except OSError:
            raise Refused('unreadable', _shown(rel) or '.') from None
        seen = {}
        for n in names:
            r = f'{rel}/{n}' if rel else n
            if not name_ok(n):
                raise Refused('bad-name', _shown(r))
            k = twin_key(n)
            if k in seen:
                raise Refused('bad-name', f'{_shown(r)} and {_shown(seen[k])} differ only by case or Unicode form')
            seen[k] = r
            p = os.path.join(d, n)
            s = _lstat(p, r)
            if _is_link(s):
                raise Refused('symlink', _shown(r))
            if stat.S_ISDIR(s.st_mode):
                if n in SKIP_DIRS:
                    continue
                if depth + 1 > MAX_DEPTH:
                    raise Refused('too-deep', _shown(r))
                rec(p, r, depth + 1)
                continue
            if not stat.S_ISREG(s.st_mode):
                raise Refused('special-file', _shown(r))
            if n in SKIP_FILES or n.endswith(SKIP_SUFFIXES):
                continue
            if s.st_nlink != 1:
                raise Refused('hardlink', _shown(r))
            out.append((r, p, s))
            total += s.st_size
            if len(out) > MAX_FILES:
                raise Refused('too-many-files', f'more than {MAX_FILES} files')
            if total > MAX_BYTES:
                raise Refused('too-big', f'more than {MAX_BYTES // (1024 * 1024)} MiB')

    rec(root, '', 0)
    out.sort(key=lambda e: e[0].encode('utf-8'))
    return out


def _read(rel, p, st):
    """Байти файла `p` (lstat `st`), прочитані РАЗ: `O_NOFOLLOW|O_NONBLOCK` (посилання чи FIFO, підкладені між `lstat` і
    `open`, не пройдуть і не підвісять потік), `fstat` того ж дескриптора — звичайний файл, `nlink == 1`, ті самі
    `dev`/`ino`; прочитано рівно `st_size` байтів. Інакше — `Refused`."""
    try:
        fd = os.open(p, _OPEN_FLAGS)
    except OSError as e:
        raise Refused('symlink' if e.errno == errno.ELOOP else 'unreadable', _shown(rel)) from None
    try:
        fs = os.fstat(fd)
        if (not stat.S_ISREG(fs.st_mode) or fs.st_nlink != 1
                or (fs.st_dev, fs.st_ino) != (st.st_dev, st.st_ino)):
            raise Refused('unstable', _shown(rel))
        chunks, n = [], 0
        while True:
            b = os.read(fd, 1 << 16)
            if not b:
                break
            n += len(b)
            if n > st.st_size:
                raise Refused('unstable', _shown(rel))
            chunks.append(b)
        if n != st.st_size:
            raise Refused('unstable', _shown(rel))
        return b''.join(chunks)
    finally:
        os.close(fd)


def tree_hash(files):
    """Хеш теки з `(шлях, розмір, sha256)` — канонічна форма зі спеки."""
    h = hashlib.sha256()
    for path, size, sha in sorted(files, key=lambda f: f[0].encode('utf-8')):
        h.update(f'{path}\0{size}\0{sha}\n'.encode('utf-8'))
    return h.hexdigest()


def _scan(root, with_data):
    files, data, total, manifest = [], ({} if with_data else None), 0, None
    for rel, p, st in _walk(root):
        raw = _read(rel, p, st)
        files.append((rel, len(raw), hashlib.sha256(raw).hexdigest()))
        total += len(raw)
        if rel == 'module.json':
            manifest = raw
        if with_data:
            data[rel] = raw
    files = tuple(files)
    return Scan(tree_hash(files), files, total, manifest, data)


def fingerprint(root):
    """Дешевий відбиток дерева `root` — лише `lstat` (тип, розмір, `mtime_ns`, `ctime_ns`, `ino`, `nlink`), без читання;
    `None`, коли самого `root` нема. Не більше `FP_MAX` записів, тека не глибше `MAX_DEPTH`, за посиланнями не ходить;
    обірваний на `FP_MAX` відбиток несе одноразовий токен і ніколи не збігається з попереднім (зміна за межею не
    ховається за кешем). Кеш `scan` і ключі кешів ядра порівнюють саме його."""
    out = []
    cut = []                                          # обрив стався (токен у відбиток — лише раз)

    def rec(d, rel, depth):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            out.append((rel, 'unreadable'))
            return
        for n in names:
            if len(out) > FP_MAX:
                if not cut:
                    cut.append(1)
                    out.append(('truncated', os.urandom(8)))
                return
            p = os.path.join(d, n)
            r = f'{rel}/{n}' if rel else n
            try:
                s = os.lstat(p)
            except OSError:
                out.append((r, 'gone'))
                continue
            out.append((r, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino, s.st_nlink))
            if stat.S_ISDIR(s.st_mode) and not _is_link(s) and n not in SKIP_DIRS and depth < MAX_DEPTH:
                rec(p, r, depth + 1)

    try:
        s = os.lstat(root)
    except OSError:
        return None
    out.append(('.', s.st_mode, s.st_ino))
    if stat.S_ISDIR(s.st_mode) and not _is_link(s):
        rec(root, '', 0)
    return tuple(out)


#: Кеш `scan`: `{корінь: (відбиток, Scan | Refused)}` (без байтів файлів — `data` не кешується). Межа `CACHE_MAX`.
_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_MAX = 256


def reset_cache():
    """Скинути кеші модуля (тести; після запису довіри)."""
    with _CACHE_LOCK:
        _CACHE.clear()
        _REC_CACHE.clear()


def forget(root):
    """Прибрати з кешу `scan` одну теку (знімок щойно записано чи замінено)."""
    with _CACHE_LOCK:
        _CACHE.pop(os.path.normpath(os.path.abspath(root)), None)


def scan(root, with_data=False):
    """`Scan` теки `root` або `Refused`. Без `with_data` — з кешем за `fingerprint` (відбиток береться ДО читання: зміна
    під час сканування дасть промах наступного разу, а не застарілий хіт). `with_data=True` (довіра, знімок) — завжди
    свіже читання, з байтами."""
    root = os.path.normpath(os.path.abspath(root))
    if with_data:
        return _scan(root, True)
    fp = fingerprint(root)
    with _CACHE_LOCK:
        hit = _CACHE.get(root)
    if hit is not None and fp is not None and hit[0] == fp:
        res = hit[1]
    else:
        try:
            res = _scan(root, False)
        except Refused as e:
            res = e
        if fp is not None:
            with _CACHE_LOCK:
                _CACHE[root] = (fp, res)
                while len(_CACHE) > CACHE_MAX:
                    _CACHE.pop(next(iter(_CACHE)))
    if isinstance(res, Refused):
        raise Refused(res.code, res.detail)
    return res


def diff(files, record_files):
    """Тека проти запису довіри: `(files, removed)`. `files` — `[{path, size, change}]` у порядку `files`, `change` —
    `same`/`changed`/`new` (за sha256 файла; без запису — усі `new`); `removed` — `[{path, size}]` файлів запису, яких у
    теці нема (за UTF-8 байтами шляху)."""
    was = {}
    for f in record_files or ():
        if isinstance(f, dict) and isinstance(f.get('path'), str):
            was[f['path']] = f
    out = []
    for path, size, sha in files:
        old = was.get(path)
        out.append({'path': path, 'size': size,
                    'change': 'new' if old is None else ('same' if old.get('sha256') == sha else 'changed')})
    have = {f[0] for f in files}
    removed = [{'path': p, 'size': f['size'] if isinstance(f.get('size'), int) else 0}
               for p, f in sorted(was.items(), key=lambda kv: kv[0].encode('utf-8', 'surrogatepass')) if p not in have]
    return out, removed


def tilde(p):
    """`p` з `~` замість домашньої теки — лише на межі компонента (`/Users/x2` не стає `~2`)."""
    home = os.path.expanduser('~').rstrip(os.sep)
    if home and (p == home or p.startswith(home + os.sep)):
        return '~' + p[len(home):]
    return p


# ------------------------------------------------------------------------------------- записи довіри

HASH_RE = re.compile(r'[0-9a-f]{64}')
#: Залишки `.tmp-*`/`.old-*` у `trusted/`, старші за стільки секунд, прибирає `sweep`.
STALE_S = 3600

#: Кеш `load_records`: `{'v': (відбиток файла, записи)}`.
_REC_CACHE = {}


class TrustUnreadable(Exception):
    """`trust.json` є, але не читається чи не тієї форми: довіра НЕ вважається порожньою, і файл не переписується
    (інакше мовчки зникли б інші довіри)."""


class SnapshotGone(Exception):
    """Знімка, на який мав би вказати запис, уже нема (паралельне «Забрати довіру» відсунуло його)."""


def trust_file():
    return os.path.join(spaces.home(), 'trust.json')


def trusted_root():
    return os.path.join(spaces.home(), 'trusted')


def snapshot_dir(h):
    return os.path.join(trusted_root(), h)


def key_for(space_path, mid):
    """Ключ запису довіри — `realpath(<простір>/modules/<id>)`; рахується й для теки, якої вже нема."""
    return os.path.realpath(os.path.join(space_path, 'modules', mid))


def _secure(path, mode):
    if os.name != 'nt':
        os.chmod(path, mode)


def _sig(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def records_sig():
    """Відбиток `trust.json` для ключів кешів ядра; шар вимкнено — `None`."""
    return _sig(trust_file()) if spaces.layer_on() else None


def _valid_record(r):
    return (isinstance(r, dict) and isinstance(r.get('id'), str) and isinstance(r.get('hash'), str)
            and bool(HASH_RE.fullmatch(r['hash'])) and isinstance(r.get('files'), list))


def _read_file():
    """Вміст `trust.json` як `{'version': 1, 'modules': {…}}`; файла нема — порожній; не читається чи не та форма —
    `TrustUnreadable`."""
    try:
        data = spaces._read_json(trust_file())
    except FileNotFoundError:
        return {'version': 1, 'modules': {}}
    except (OSError, ValueError):
        raise TrustUnreadable('trust.json is unreadable') from None
    if not isinstance(data, dict) or not isinstance(data.get('modules', {}), dict):
        raise TrustUnreadable('trust.json: "modules" is not an object')
    data = dict(data)
    data['modules'] = dict(data.get('modules', {}))
    data.setdefault('version', 1)
    return data


def load_records():
    """`{ключ: запис}` з `trust.json` (лише записи правильної форми). Файла нема чи шар просторів вимкнено — `{}` без
    звернення до диска; не читається — `TrustUnreadable`. Кеш за відбитком файла; віддає новий словник, але самі записи
    спільні з кешем — викликачі їх не змінюють."""
    if not spaces.layer_on():
        return {}
    sig = _sig(trust_file())
    with _CACHE_LOCK:
        hit = _REC_CACHE.get('v')
    if hit is not None and sig is not None and hit[0] == sig:
        return dict(hit[1])
    recs = {k: v for k, v in _read_file()['modules'].items() if isinstance(k, str) and _valid_record(v)}
    if sig is not None:
        with _CACHE_LOCK:
            _REC_CACHE['v'] = (sig, recs)
    return dict(recs)


def _require_layer():
    if not spaces.layer_on():
        raise RuntimeError('spaces layer is off: trust is not written')


def _write_file(data):
    home, path = spaces.home(), trust_file()
    os.makedirs(home, mode=0o700, exist_ok=True)
    _secure(home, 0o700)
    if os.path.exists(path):
        _secure(path, 0o600)                         # ДО запису: атомарна заміна переносить режим цілі
    atomic_write_json(path, data)
    _secure(path, 0o600)
    with _CACHE_LOCK:
        _REC_CACHE.clear()


def put_record(key, rec):
    """Записати довіру `rec` під ключем `key`: під `WRITE_LOCK` лише читання-зміна-запис файла (атомарно, 0600). Форма
    запису — як у `load_records` (інакше `ValueError`: `rec['hash']` іде в шлях знімка, а запис не тієї форми однаково
    не завантажився б). Знімок `rec['hash']` мусить існувати — перевірка під тим самим локом, інакше `SnapshotGone`.
    ⚠️ Знімок пишуть ДО (`ensure_snapshot`), кеші ядра скидають ПІСЛЯ — і те, і те поза локом."""
    _require_layer()
    if not _valid_record(rec):
        raise ValueError('put_record: malformed record')
    with WRITE_LOCK:
        data = _read_file()
        if not _real_dir(snapshot_dir(rec['hash'])):
            raise SnapshotGone(rec['hash'])
        data['modules'][key] = rec
        _write_file(data)


def drop_record(key):
    """Прибрати довіру `key`; `True`, якщо запис був. Знімок, на який більше не посилається жоден запис, відсувається в
    `.old-*` ПІД тим самим локом (паралельна довіра того ж хешу побачить його відсутність і відмовить), видаляється —
    після локу. Запис файла не вдався — знімок повертається на місце (best effort) і виняток іде далі: довіра лишилась."""
    _require_layer()
    aside = None
    with WRITE_LOCK:
        data = _read_file()
        rec = data['modules'].pop(key, None)
        if rec is None:
            return False
        h = rec.get('hash') if isinstance(rec, dict) else None
        still = any(isinstance(r, dict) and r.get('hash') == h for r in data['modules'].values())
        if isinstance(h, str) and HASH_RE.fullmatch(h) and not still and _real_dir(snapshot_dir(h)):
            aside = _aside(snapshot_dir(h))
        try:
            _write_file(data)
        except BaseException:
            if aside:
                try:
                    os.rename(aside, snapshot_dir(h))
                except OSError:
                    pass                              # поруч уже новий знімок того ж хешу — `.old-*` прибере `sweep`
            raise
    if aside:
        _rmtree(aside)
    sweep()
    return True


# ------------------------------------------------------------------------------------------- знімки

def _real_dir(p):
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode) and not _is_link(st)


def _aside(d):
    """Атомарно перейменувати теку `d` в `.old-<випадкове>` поруч; новий шлях."""
    dst = os.path.join(os.path.dirname(d), f'.old-{secrets.token_hex(8)}')
    os.rename(d, dst)
    forget(d)
    return dst


def _rmtree(p):
    """Видалити теку знімка: спершу повернути теки на запис (знімок — 0500/0400)."""
    for dp, _dns, _fns in os.walk(p):
        try:
            _secure(dp, 0o700)
        except OSError:
            pass
    shutil.rmtree(p, ignore_errors=True)


def sweep(now=None):
    """Прибрати в `trusted/` теки `.tmp-*`/`.old-*`, старші за `STALE_S` (залишки обірваних записів і видалень)."""
    root = trusted_root()
    now = time.time() if now is None else now
    try:
        names = os.listdir(root)
    except OSError:
        return
    for n in names:
        if not (n.startswith('.tmp-') or n.startswith('.old-')):
            continue
        p = os.path.join(root, n)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if now - st.st_mtime > STALE_S and stat.S_ISDIR(st.st_mode) and not _is_link(st):
            _rmtree(p)


def verify_snapshot(h):
    """Знімок `h` цілий: справжня тека `trusted/<h>` (не посилання) і її хеш (сканер з кешем відбитка) дорівнює `h`."""
    if not (isinstance(h, str) and HASH_RE.fullmatch(h)):
        return False
    d = snapshot_dir(h)
    if not _real_dir(d):
        return False
    try:
        return scan(d).hash == h
    except Refused:
        return False


def ensure_snapshot(sc):
    """Знімок рівно байтів `sc` (з `scan(…, with_data=True)`) у `trusted/<sc.hash>/`: файли 0400, теки 0500. Цілий знімок
    із цим хешем лишається; пошкоджений — відсувається й пишеться наново. Пишеться в `.tmp-*` і перейменовується (та
    сама тека-батько — атомарно). Повертає теку знімка."""
    if sc.data is None:
        raise ValueError('ensure_snapshot: scan(…, with_data=True) is required')
    if not HASH_RE.fullmatch(str(sc.hash)):           # хеш іде в шлях знімка (і в `_aside` + `_rmtree`): лише 64 hex
        raise ValueError('ensure_snapshot: malformed hash')
    _require_layer()
    sweep()
    root = trusted_root()
    os.makedirs(root, mode=0o700, exist_ok=True)
    _secure(spaces.home(), 0o700)
    _secure(root, 0o700)
    final = snapshot_dir(sc.hash)
    if _real_dir(final):
        if verify_snapshot(sc.hash):
            return final
        _rmtree(_aside(final))
    elif os.path.lexists(final):
        os.unlink(final)                              # посилання чи файл на місці знімка
    tmp = tempfile.mkdtemp(prefix='.tmp-', dir=root)
    try:
        for rel, raw in sc.data.items():
            p = os.path.join(tmp, *rel.split('/'))
            os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
                         | getattr(os, 'O_BINARY', 0), 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(raw)
        for dp, _dns, fns in os.walk(tmp, topdown=False):
            for n in fns:
                _secure(os.path.join(dp, n), 0o400)
            _secure(dp, 0o500)
        try:
            os.rename(tmp, final)
        except OSError:
            if not verify_snapshot(sc.hash):          # паралельний запис того ж хешу встиг першим — тоді ок
                raise
            _rmtree(tmp)
        tmp = None
    finally:
        if tmp:
            _rmtree(tmp)
    forget(final)
    return final


# ------------------------------------------------------------------------------------ системне вікно

CONFIRM_TIMEOUT = 120
DECLINE_COOLDOWN = 30
SEAM_ENV = 'DEAI_TRUST_CONFIRM'

#: Тексти рідного вікна. Мова — з `lang` запиту довіри; невідома — `uk`.
CONFIRM_TEXT = {
    'uk': {'title': 'Deai Canvas', 'yes': 'Довіряю', 'no': 'Скасувати',
           'ask': 'Довіритись модулю «{name}» ({id}, відбиток {hash})?\n\n'
                  'Його код виконуватиметься на цьому компʼютері з вашими правами.\n\nТека: {path}'},
    'en': {'title': 'Deai Canvas', 'yes': 'Trust', 'no': 'Cancel',
           'ask': 'Trust the module “{name}” ({id}, fingerprint {hash})?\n\n'
                  'Its code will run on this computer with your permissions.\n\nFolder: {path}'},
}

_OSA = '''on run argv
  set msg to item 1 of argv
  set ttl to item 2 of argv
  set yesB to item 3 of argv
  set noB to item 4 of argv
  tell me to activate
  try
    set r to display dialog msg with title ttl buttons {noB, yesB} default button noB cancel button noB with icon caution giving up after 120
  on error number -128
    return "no"
  end try
  if gave up of r then return "no"
  if button returned of r is yesB then return "yes"
  return "no"
end run'''

_PS = ("Add-Type -AssemblyName System.Windows.Forms; "
       "$r = [System.Windows.Forms.MessageBox]::Show($env:DEAI_CONFIRM_MSG, $env:DEAI_CONFIRM_TITLE, 'YesNo', 'Warning', 'Button2'); "
       "if ($r -eq 'Yes') { 'yes' } else { 'no' }")


def _clean(s, n=80, middle=False):
    """Рядок для системного вікна: без `Cc`/`Cf`/`Cs`/`Zl`/`Zp`, не довший за `n` (з «…»). `Cs` — самотній сурогат
    (`"\\ud800"` з `module.json`): у `argv` підпроцесу він дав би `UnicodeEncodeError` замість вікна. Зайве зрізається
    з кінця, а з `middle` — із СЕРЕДИНИ (голова, «…», хвіст): у шляху важливий саме кінець — тека модуля."""
    s = ''.join(c for c in str(s) if unicodedata.category(c) not in ('Cc', 'Cf', 'Cs', 'Zl', 'Zp'))
    if len(s) <= n:
        return s
    if middle:
        head = (n - 1) // 3
        return s[:head] + '…' + s[len(s) - (n - 1 - head):]
    return s[:n - 1] + '…'


def confirm_texts(lang, name, mid, h, path):
    """`(заголовок, текст, «так», «ні»)` вікна довіри мовою `lang` (`uk`/`en`, інакше `uk`)."""
    tx = (CONFIRM_TEXT.get(lang) if isinstance(lang, str) else None) or CONFIRM_TEXT['uk']
    msg = tx['ask'].format(name=_clean(name), id=_clean(mid), hash=str(h)[:12], path=_clean(path, middle=True))
    return tx['title'], msg, tx['yes'], tx['no']


def confirm_command(platform, title, msg, yes, no, which=shutil.which, env=None):
    """`(argv, додаткове оточення)` рідного вікна для `platform` (`sys.platform`) або `None` — нема чим показати. Текст
    іде АРГУМЕНТОМ (macOS, Linux) чи ЗМІННОЮ ОТОЧЕННЯ (Windows) — ніколи не підставляється в код скрипта."""
    env = os.environ if env is None else env
    if platform == 'darwin':
        return ['osascript', '-e', _OSA, msg, title, yes, no], {}
    if platform.startswith('win'):
        return (['powershell', '-NoProfile', '-NonInteractive', '-Command', _PS],
                {'DEAI_CONFIRM_MSG': msg, 'DEAI_CONFIRM_TITLE': title})
    if not (env.get('DISPLAY') or env.get('WAYLAND_DISPLAY')):
        return None
    if which('zenity'):
        return ['zenity', '--question', '--no-markup', '--title', title, '--text', msg,
                '--ok-label', yes, '--cancel-label', no, f'--timeout={CONFIRM_TIMEOUT}'], {}
    if which('kdialog'):
        return ['kdialog', '--title', title, '--yes-label', yes, '--no-label', no, '--warningyesno', msg], {}
    return None


def _interpret(argv0, proc):
    """Відповідь вікна з завершеного процесу: `yes`/`no`/`unavailable`."""
    if argv0 in ('osascript', 'powershell'):
        if proc.returncode != 0:
            return 'unavailable'
        return 'yes' if (proc.stdout or '').strip().lower() == 'yes' else 'no'
    if proc.returncode == 0:
        return 'yes'
    if proc.returncode in (1, 5):                     # zenity: 1 — «ні», 5 — тайм-аут; kdialog: 1 — «ні»
        return 'no'
    return 'unavailable'


def _real_default_home():
    """Справжній типовий `~/.deai` — з бази користувачів (POSIX), а не з `$HOME`, який тест чи оточення могли підмінити."""
    try:
        import pwd
        base = pwd.getpwuid(os.getuid()).pw_dir
    except (ImportError, KeyError):
        base = os.path.expanduser('~')
    return os.path.realpath(os.path.join(base, '.deai'))


def seam_value(env=None):
    """Тестовий шов `DEAI_TRUST_CONFIRM` (`yes`/`no`/`unavailable`) або `None`. Діє ЛИШЕ коли `DEAI_HOME` задано й це не
    справжній типовий `~/.deai`: на робочій машині змінна, що випадково лишилась, нічого не робить."""
    env = os.environ if env is None else env
    v = env.get(SEAM_ENV)
    home = env.get('DEAI_HOME')
    if v not in ('yes', 'no', 'unavailable') or not home:
        return None
    here, default = os.path.realpath(os.path.expanduser(home)), _real_default_home()
    if here == default or spaces._same_dir(here, default):      # тека на диску та сама (APFS: інший регістр, NFD)
        return None
    return v


def confirm(title, msg, yes, no):
    """Рідне вікно ОС → `'yes'`/`'no'`/`'unavailable'`. Блокує потік до відповіді; тайм-аут — `'no'`."""
    seam = seam_value()
    if seam is not None:
        return seam
    cmd = confirm_command(sys.platform, title, msg, yes, no)
    if cmd is None:
        return 'unavailable'
    argv, extra = cmd
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=CONFIRM_TIMEOUT + 10,
                              env={**os.environ, **extra}, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 'no'
    except OSError:
        return 'unavailable'
    return _interpret(argv[0], proc)


_ASK_LOCK = threading.Lock()
_DECLINED = {}


def clear_declined():
    """Забути відмови (тести)."""
    _DECLINED.clear()


def ask(key, h, texts, now=time.monotonic):
    """Системне підтвердження довіри `(key, h)`: `'yes'`/`'no'`/`'unavailable'`, `'busy'` (уже відкрите інше вікно) чи
    `'declined'` (той самий `(key, h)` відхилено менш як `DECLINE_COOLDOWN` с тому — вікна не показуємо). Поза локами
    ядра: блокує лише свій потік."""
    t = _DECLINED.get((key, h))
    if t is not None and now() - t < DECLINE_COOLDOWN:
        return 'declined'
    if not _ASK_LOCK.acquire(blocking=False):
        return 'busy'
    try:
        r = confirm(*texts)
    finally:
        _ASK_LOCK.release()
    if r == 'no':
        _DECLINED[(key, h)] = now()
    return r
