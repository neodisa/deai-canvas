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
import stat
import threading
import unicodedata
from collections import namedtuple

import spaces

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
    `\\uXXXX`, решта як є: інакше `detail` не кодується в UTF-8 і відповідь API впала б."""
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
    """Дешевий відбиток дерева `root` — лише `lstat` (тип, розмір, `mtime_ns`, `ino`, `nlink`), без читання; `None`,
    коли самого `root` нема. Не більше `FP_MAX` записів, тека не глибше `MAX_DEPTH`, за посиланнями не ходить.
    Кеш `scan` і ключі кешів ядра порівнюють саме його."""
    out = []

    def rec(d, rel, depth):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            out.append((rel, 'unreadable'))
            return
        for n in names:
            if len(out) > FP_MAX:
                return
            p = os.path.join(d, n)
            r = f'{rel}/{n}' if rel else n
            try:
                s = os.lstat(p)
            except OSError:
                out.append((r, 'gone'))
                continue
            out.append((r, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ino, s.st_nlink))
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
               for p, f in sorted(was.items(), key=lambda kv: kv[0].encode('utf-8')) if p not in have]
    return out, removed


def tilde(p):
    """`p` з `~` замість домашньої теки — лише на межі компонента (`/Users/x2` не стає `~2`)."""
    home = os.path.expanduser('~').rstrip(os.sep)
    if home and (p == home or p.startswith(home + os.sep)):
        return '~' + p[len(home):]
    return p


_REC_CACHE = {}      # Task 2: кеш записів `trust.json`
