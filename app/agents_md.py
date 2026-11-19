"""AGENTS.md простору (етап Е, 0.31.0): блок з шаблону Deai між маркерами + «Ваше» навколо нього.

Блок НЕ залежить від компʼютера (тека простору спільна через git): жодних абсолютних шляхів, імені користувача й імені
простору; єдина підстановка шаблону — `{version}` у маркері begin. Шляхи установки віддає лише відповідь API (`paths`).
Текст користувача (до й після блоку) зберігається байт-у-байт: читання/запис без перекладу рядків, `surrogateescape`.
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
    try:
        with open(_path(space_dir), **_ENC) as f:
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
        old = _read(space_dir)
        before, block, after, _ = _parts(old)
        text = before + new + after if block is not None else new + '\n' + old
    path = _path(space_dir)
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
        os.replace(tmp.name, path)
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise
    return status(space_dir, version=version)
