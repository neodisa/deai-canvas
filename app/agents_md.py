"""AGENTS.md простору (етап Е, 0.31.0): блок з шаблону Deai між маркерами + «Ваше» навколо нього.

Блок НЕ залежить від компʼютера (тека простору спільна через git): жодних абсолютних шляхів, імені користувача й імені
простору; єдина підстановка шаблону — `{version}` у маркері begin. Шляхи установки віддає лише відповідь API (`paths`).
Текст користувача (до й після блоку) зберігається байт-у-байт: читання/запис без перекладу рядків, `surrogateescape`.
Нечитний файл (права, тека замість файла, симлінк) — `OSError` із `status`/`write`; запис ще раз звіряє файл перед заміною (`ValueError('changed')`).
Файл із НОВІШОЇ версії Deai ніколи не «понижується» (`write` → `ValueError('newer')`). Запис атомарний.
"""
import os
import re
import tempfile

NAME = 'AGENTS.md'
BEGIN_RE = re.compile(r'^<!-- deai:begin v(?P<v>[0-9.]+)[^\n]*-->\r?$', re.M)
END = '<!-- deai:end -->'
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'agents.md')
_VER_RE = re.compile(r'^[0-9]+(\.[0-9]+)*$')
_ENC = {'encoding': 'utf-8', 'errors': 'surrogateescape', 'newline': ''}


def version_tuple(v):
    """`'0.31.0'` → `(0, 31, 0)`; не semver (`'unknown'`, `None`, `'1..2'`) → `None`."""
    if not isinstance(v, str) or not _VER_RE.match(v):
        return None
    return tuple(int(x) for x in v.split('.'))


def render_block(*, version):
    """Блок із маркерами, закінчується `\\n`. Версія не числова → `ValueError('version')` (маркер не розібрався б назад)."""
    if version_tuple(version) is None:
        raise ValueError('version')
    with open(TEMPLATE, encoding='utf-8', newline='') as f:
        text = f.read()
    return text.replace('{version}', version)


def _parts(text):
    """`(before, block, after, file_version)`; блоку нема (або begin без end) → `(text, None, '', None)`."""
    m = BEGIN_RE.search(text)
    if m:
        e = text.find(END, m.end())
        if e >= 0:
            nl = text.find('\n', e)
            stop = len(text) if nl < 0 else nl + 1
            return text[:m.start()], text[m.start():stop], text[stop:], m.group('v')
    return text, None, '', None


def split(text):
    """`(block | None, own, file_version | None)`: `own` — увесь текст поза блоком (до + після)."""
    before, block, after, fv = _parts(text)
    return block, before + after, fv


def _body(block):
    """Блок без рядка begin й без `\\r` (порівняння не залежить від перекладу рядків)."""
    return block.replace('\r\n', '\n').split('\n', 1)[1] if block else ''


def _path(space_dir):
    return os.path.join(space_dir, NAME)


def _read(space_dir):
    """Текст файла чи `None` (файла нема). Симлінк і не-звичайний файл — `OSError` (як і будь-яка інша відмова читання):
    такий AGENTS.md ми не читаємо й не замінюємо (заміна розірвала б симлінк)."""
    p = _path(space_dir)
    if os.path.islink(p) or (os.path.exists(p) and not os.path.isfile(p)):
        raise OSError(f'{NAME}: not a regular file')
    try:
        with open(p, **_ENC) as f:
            return f.read()
    except FileNotFoundError:
        return None


def status(space_dir, *, version):
    text = _read(space_dir)
    out = {'path': _path(space_dir), 'exists': text is not None, 'hasBlock': False, 'outdated': False,
           'newer': False, 'version': version, 'fileVersion': None, 'block': None, 'own': '', 'text': ''}
    if text is None:
        return out
    block, own, fv = split(text)
    out.update(hasBlock=block is not None, fileVersion=fv, block=block, own=own, text=text)
    cur, ft = version_tuple(version), version_tuple(fv)
    if block is not None and cur is not None and ft is not None:
        if ft > cur:
            out['newer'] = True
        elif ft < cur:
            out['outdated'] = _body(block) != _body(render_block(version=version))
    return out


def write(space_dir, *, version):
    """Створити/оновити AGENTS.md; повертає `status` після запису. Файл новішої версії → `ValueError('newer')`, файл цілий."""
    st = status(space_dir, version=version)
    if st['newer']:
        raise ValueError('newer')
    new = render_block(version=version)
    if not st['exists']:
        text = new
    else:
        old = st['text']
        before, block, after, _ = _parts(old)
        text = before + new + after if block is not None else new + '\n' + old
    path = _path(space_dir)
    old = st['text'] if st['exists'] else None
    if st['exists'] and text == old:
        return st
    mode = None
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        pass
    tmp = tempfile.NamedTemporaryFile('w', dir=space_dir, prefix='.AGENTS.', suffix='.tmp', delete=False, **_ENC)
    try:
        with tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp.name, 0o644 if mode is None else mode)
        if _read(space_dir) != old:      # файл змінили між читанням і заміною: чужу правку не губимо
            raise ValueError('changed')
        os.replace(tmp.name, path)
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise
    return status(space_dir, version=version)


# ----------------------------------------------------------------------------------- CLAUDE.md (0.33.0)
# Claude Code (перевірено 20.11.2026 на 2.1.322) не читає AGENTS.md, коли вище по теках є будь-який CLAUDE.md; CLAUDE.md у теці
# простору з рядком `@AGENTS.md` це лагодить. Наявний CLAUDE.md змінює ЛИШЕ `claude_connect` (кнопка «Підключити» = згода людини).

CLAUDE_NAME = 'CLAUDE.md'
_IMPORT_RE = re.compile(r'^[ \t]*@(?:\./)?AGENTS\.md[ \t]*\r?$', re.M)
_IMPORT_LINE = '@AGENTS.md\n'


def _claude_path(space_dir):
    return os.path.join(space_dir, CLAUDE_NAME)


def _claude_read(space_dir):
    """Текст CLAUDE.md чи `None` (файла нема). Симлінк, не-звичайний файл, відмова читання — `OSError` (як `_read`)."""
    p = _claude_path(space_dir)
    if os.path.islink(p) or (os.path.lexists(p) and not os.path.isfile(p)):
        raise OSError(f'{CLAUDE_NAME}: not a regular file')
    try:
        with open(p, **_ENC) as f:
            return f.read()
    except FileNotFoundError:
        return None


def claude_status(space_dir):
    """`{state, path}`: `ok` (є рядок `@AGENTS.md` чи `@./AGENTS.md`), `missing`, `no-import`, `unreadable`. Не кидає."""
    p = _claude_path(space_dir)
    try:
        text = _claude_read(space_dir)
    except (OSError, ValueError):
        return {'state': 'unreadable', 'path': p}
    if text is None:
        return {'state': 'missing', 'path': p}
    return {'state': 'ok' if _IMPORT_RE.search(text) else 'no-import', 'path': p}


def claude_ensure(space_dir):
    """Новий простір і «Створити» AGENTS.md: CLAUDE.md з `@AGENTS.md` ЛИШЕ коли його нема (`O_EXCL`); наявний не чіпаємо.
    `True` — створено."""
    try:
        with open(_claude_path(space_dir), 'x', **_ENC) as f:
            f.write(_IMPORT_LINE)
        return True
    except FileExistsError:
        return False


def claude_connect(space_dir):
    """«Підключити»: нема файла — створити з `@AGENTS.md`; є без імпорту — дописати `@AGENTS.md` і порожній рядок НА ПОЧАТОК
    (решта байт у байт, права ті самі, запис атомарний); уже підключено — нічого. Нечитний — `OSError`; файл змінили між читанням
    і заміною — `ValueError('changed')`. Повертає `claude_status` після запису."""
    text = _claude_read(space_dir)
    if text is None:
        if not claude_ensure(space_dir):
            raise ValueError('changed')          # файл зʼявився між читанням і створенням
        return claude_status(space_dir)
    if _IMPORT_RE.search(text):
        return claude_status(space_dir)
    path = _claude_path(space_dir)
    mode = os.stat(path).st_mode & 0o777
    tmp = tempfile.NamedTemporaryFile('w', dir=space_dir, prefix='.CLAUDE.', suffix='.tmp', delete=False, **_ENC)
    try:
        with tmp:
            tmp.write(_IMPORT_LINE + '\n' + text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp.name, mode)
        if _claude_read(space_dir) != text:      # чужу правку не губимо
            raise ValueError('changed')
        os.replace(tmp.name, path)
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise
    return claude_status(space_dir)
