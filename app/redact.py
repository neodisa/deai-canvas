"""Редагування рядків діагностики (0.23, T1): одна реалізація фільтра для тексту помилок, діагностики й повідомлень кілець.

Чиста функція без залежностей від ядра: лише `os`, `re`, `pwd` (як `isolation.real_home`); `serve`/`spaces` не імпортуємо.
Порядок кроків несучий (див. `text`) і результат ідемпотентний: `text(text(x)) == text(x)`."""
import os
import re

try:
    import pwd
except ImportError:  # Windows
    pwd = None

HIDDEN = '‹приховано›'
EMAIL = '‹e-mail›'

#: те саме правило, що `serve._USERINFO`: до ОСТАННЬОГО `@` перед першим `/`.
_USERINFO = re.compile(r'(://)[^/\s]*@')
_QUERY = re.compile(r'(https?://\S*?|/api/\S*?)\?[^\s\'")]*')
_PREFIXED = re.compile(
    r'eyJ[\w-]{8,}\.[\w-]{8,}(?:\.[\w-]*)?'
    r'|(?:sk-|sb_(?:publishable|secret)_|ghp_|gho_|glpat-|xox[bap]-)[\w-]{12,}')
_GENERIC = re.compile(r'(?<![\w/.-])[A-Za-z0-9_+=-]{32,}(?![\w/.-])')
_MAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')


def userinfo(value):
    """`https://TOKEN@host/o/r` → `https://***@host/o/r`."""
    return _USERINFO.sub(r'\1***@', value)


def _generic(m):
    s = m.group(0)
    if any(c.isdigit() for c in s) and any(c.isalpha() for c in s):
        return HIDDEN
    return s


def _homes():
    out = []
    try:
        out.append(os.path.expanduser('~'))
    except Exception:
        pass
    if pwd is not None:
        try:
            out.append(pwd.getpwuid(os.getuid()).pw_dir)
        except Exception:
            pass
    uniq = []
    for h in out:
        h = (h or '').rstrip('/')
        if h and h not in uniq:
            uniq.append(h)
    return sorted(uniq, key=len, reverse=True)


def _swap(value, prefix, label):
    # межа за `os.path`: після збігу — `/` або кінець, не продовження імені
    return re.sub(r'(?<![\w.-])' + re.escape(prefix) + r'(?![\w.-])', lambda m: label, value)


def text(value, roots=(), limit=300):
    """Рядок без шляхів дому/коренів, ключів, e-mail і query. Не-рядок → `str()`, `None` → `''`."""
    if value is None:
        return ''
    if not isinstance(value, str):
        value = str(value)
    for prefix, label in sorted(roots or (), key=lambda r: len(r[0]), reverse=True):
        if prefix:
            value = _swap(value, prefix.rstrip('/'), label)
    for home in _homes():
        value = _swap(value, home, '~')
    value = userinfo(value)
    value = _QUERY.sub(r'\1', value)
    value = _PREFIXED.sub(HIDDEN, value)
    value = _GENERIC.sub(_generic, value)
    value = _MAIL.sub(EMAIL, value)
    if limit is not None and len(value) > limit:
        value = value[:limit]
        if value and '\ud800' <= value[-1] <= '\udbff':
            value = value[:-1]
    return value
