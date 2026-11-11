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
#: ІПН/ЄДРПОУ/картка/телефон: 8+ цифр підряд (рядки `:123`, версії `0.23.0` і дати `2026-11-11` лишаються: там цифри короткими групами).
_DIGITS = re.compile(r'(?<!\d)\d{8,}(?!\d)')
_CARD = re.compile(r'(?<!\d)\d{4}(?:[ -]\d{4}){3,4}(?!\d)')
_IBAN = re.compile(r'(?<![A-Za-z0-9])[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?![A-Za-z0-9])')
_IBAN_SPACED = re.compile(r'(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?: [A-Z0-9]{4}){3,7}(?: [A-Z0-9]{1,3})?(?![A-Za-z0-9])')
_LABELLED = re.compile(
    r'(?i)((?:api[-_]?key|token|secret|password|passwd|authorization)["\']?\s*[:=]\s*)'
    r'(?:(?:bearer|basic)\s+)?(?:‹приховано›|"[^"]*"|\'[^\']*\'|\S+)')
#: чужі домівки (не наш користувач): після правила власного дому
_OTHER_HOME_WIN = re.compile(r'(?<![\w.:-])[A-Za-z]:[\\/]Users[\\/][^\\/\s]+')
_OTHER_HOME_POSIX = re.compile(r'(?<![\w.:~-])/(?:Users|home)/[^/\s]+')

# --- абсолютні шляхи → `…/<імʼя>` (`paths`) ---
_P_QUOTED = re.compile(r'([\'"])((?:/|~[\\/]|[A-Za-z]:[\\/]|\\\\)[^\'"\n]*)\1')
_P_URL = re.compile(r'(https?://[^/\s\'"<>|?#]+)((?:/[^/\s\'"<>|?#]*)+)')
_P_FILEURL = re.compile(r'file://[^\s\'"<>|]*')
_P_ENCODED = re.compile(r'(?:[\w.~-]|%[0-9A-Fa-f]{2})*%(?:2[Ff]|5[Cc])(?:[\w.~-]|%[0-9A-Fa-f]{2})*')
_P_UNC = re.compile(r'\\\\[^\s\\\'"]+(?:\\[^\s\\\'"]*)+')
_P_WIN = re.compile(r'(?<![\w])[A-Za-z]:[\\/][^\s\'"<>|]*')
_P_HOME = re.compile(r'(?<![\w])~[\\/][^\s\'"<>|]*')
_P_POSIX = re.compile(r'(?<![\w:/.<>~%…-])/[^\s\'"<>|]+')
_P_LAST = re.compile(r'[^/\\]*$')
_P_ENC_LAST = re.compile(r'(?:[\w.~-]|%(?!2[Ff]|5[Cc])[0-9A-Fa-f]{2})*$')


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
        for v in (h, (h or '').replace('\\', '/')):       # Windows: і `C:\Users\me`, і `C:/Users/me`
            v = (v or '').rstrip('/\\')
            if v and v not in uniq:
                uniq.append(v)
    return sorted(uniq, key=len, reverse=True)


def _swap(value, prefix, label):
    # межа за `os.path`: після збігу — `/` або кінець, не продовження імені
    return re.sub(r'(?<![\w.:-])' + re.escape(prefix) + r'(?![\w.-])', lambda m: label, value)


def _tail(m):
    return '…/' + _P_LAST.search(m.group(0)).group(0)


def _tail_quoted(m):
    return m.group(1) + '…/' + _P_LAST.search(m.group(2)).group(0) + m.group(1)


_LOOPBACK = re.compile(r'^https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$', re.I)
_EXT = re.compile(r'\.([A-Za-z0-9]{1,5})$')


def _tail_url(m):
    """Зовнішній `https://h/a/b/42` → `https://h/…/42` (схема, хост, останній сегмент). Локальний (loopback або шлях з `/t/…`):
    `http://localhost:8765/t/acme/it1/x.png` → `http://localhost:8765/…/*.png`: імена файлів канваса несуть імена клієнтів, тож лишається
    лише розширення (нема розширення → `…`)."""
    segs = [x for x in m.group(2).split('/') if x]
    if _LOOPBACK.match(m.group(1)) or (segs and segs[0] == 't'):
        ext = _EXT.search(segs[-1]) if segs and segs[-1] != '…' else None
        return m.group(1) + '/…/' + ('*.' + ext.group(1).lower() if ext else '…')
    if len(segs) <= 1 and '…' not in m.group(2):
        return m.group(0)
    return m.group(1) + '/…/' + (segs[-1] if segs else '')


def _tail_encoded(m):
    return '…/' + re.split(r'%(?:2[Ff]|5[Cc])', m.group(0))[-1]


def paths(value):
    """Кожен абсолютний шлях (POSIX `/…`, `~/…`, `C:\\…`/`C:/…`, UNC, `file://…`, URL-кодований `%2F`) → `…/<останній сегмент>`: імена
    тек (клієнт, користувач, простір) не їдуть із машини. `http(s)://хост/…/<останній сегмент>` для локальних і зовнішніх адрес (query/hash відрізає `text`). Шлях у лапках (з пробілами) береться цілим. Мітки `<space>/…` не чіпає. Ідемпотентна."""
    value = _P_URL.sub(_tail_url, value)
    value = _P_QUOTED.sub(_tail_quoted, value)
    value = _P_FILEURL.sub(_tail, value)
    value = _P_ENCODED.sub(_tail_encoded, value)
    value = _P_WIN.sub(_tail, value)             # ДО UNC: `C:\\Users\\x` (подвійне екранування) не має лишити `C:`
    value = _P_UNC.sub(_tail, value)
    value = _P_HOME.sub(_tail, value)
    return _P_POSIX.sub(_tail, value)


def text(value, roots=(), limit=300, collapse=False):
    """Рядок без шляхів дому/коренів, ключів, номерів, e-mail і query. Не-рядок → `str()`, `None` → `''`. `collapse=True` — ще й КОЖЕН
    абсолютний шлях згорнуто до `…/<імʼя>` (`paths`): для повідомлень помилок, де шлях може бути з чужого простору."""
    if value is None:
        return ''
    if not isinstance(value, str):
        value = str(value)
    for prefix, label in sorted(roots or (), key=lambda r: len(r[0]), reverse=True):
        if prefix:
            value = _swap(value, prefix.rstrip('/'), label)
    for home in _homes():
        value = _swap(value, home, '~')
    if collapse:
        value = paths(value)
    value = _OTHER_HOME_WIN.sub('~', value)
    value = _OTHER_HOME_POSIX.sub('~', value)
    value = userinfo(value)
    value = _QUERY.sub(r'\1', value)
    value = _LABELLED.sub(lambda m: m.group(1) + HIDDEN, value)
    value = _PREFIXED.sub(HIDDEN, value)
    value = _GENERIC.sub(_generic, value)
    value = _IBAN.sub(HIDDEN, value)
    value = _IBAN_SPACED.sub(HIDDEN, value)
    value = _CARD.sub(HIDDEN, value)
    value = _DIGITS.sub(HIDDEN, value)
    value = _MAIL.sub(EMAIL, value)
    if limit is not None and len(value) > limit:
        value = value[:limit]
        if value and '\ud800' <= value[-1] <= '\udbff':
            value = value[:-1]
    return value
