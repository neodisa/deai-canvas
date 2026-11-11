"""Відгук (0.23, T6): кільце помилок сервера й збирач діагностики. Надсилання й черга — далі в цьому ж файлі (T7).

Модуль НЕ імпортує `serve`: контекст (простір, задача, екран, мова) збирає `serve._feedback_context` і передає готовим словником.
⛔ Приватність: у діагностику не потрапляє жоден вільний текст з файлів чи задач користувача, лише id/коди; КОЖЕН рядок проходить
`redact.text` (дім → `~`, ключі/токени/e-mail приховано, query URL відрізано)."""
import collections
import json
import os
import platform
import re
import threading

import deai_modules
import redact
import updater

ERRORS_MAX = 50              # кільце сервера
CLIENT_ERRORS_MAX = 20       # кільце клієнта (береться з тіла запиту)
MSG_MAX = 300
DIAG_MAX_BYTES = 64 * 1024
SHOT_MAX_BYTES = 2 * 1024 * 1024

_RING = collections.deque(maxlen=ERRORS_MAX)
_RING_LOCK = threading.Lock()

_SEG_RE = re.compile(r'^[A-Za-z0-9_.-]{1,40}$')
_TASK_PREFIX = re.compile(r'^/t/[^/]+(?=/)')
_ID_RE = re.compile(r'^[\w-]{1,80}$')
_PAGE_RE = re.compile(r'^[\w-]+(~[0-9a-f]{8})?(@[1-9]\d{1,3})?$')
_MIG_RE = re.compile(r'^liga-4d[0-9a-z]{1,4}$')
_FILE_RE = re.compile(r'^app/[\w./-]{1,100}$')
_CODE_RE = re.compile(r'^[a-z0-9-]{1,40}$')


# --------------------------------------------------------------------------------- кільце помилок сервера

def route_of(path):
    """Маршрут БЕЗ query, без префікса `/t/<id>` і без імен: `/api/…` — перші три сегменти, решта — лише перший (`/it-assets/it1/назва/x` →
    `/it-assets`). Сегмент не з `[A-Za-z0-9_.-]` (назва кирилицею, пробіли) → `*`."""
    p = str(path or '').split('?', 1)[0].split('#', 1)[0]
    p = _TASK_PREFIX.sub('', p)
    parts = [s for s in p.split('/') if s]
    if not parts:
        return '/'
    keep = 3 if parts[0] == 'api' else 1
    segs = [s if _SEG_RE.match(s) else '*' for s in parts[:keep]]
    return '/' + '/'.join(segs)


def record_error(path, exc, code=None):
    """Записати виняток у кільце. З `code` (операційна відмова: шляхи в тексті) — лише код, БЕЗ `str(exc)`; без коду — повідомлення
    пройшло `redact.text` і обрізане до 300 символів."""
    entry = {'route': route_of(path), 'type': redact.text(type(exc).__name__, limit=80)}
    if code is not None:
        entry['code'] = redact.text(code, limit=60)
        entry['msg'] = ''
    else:
        try:
            raw = str(exc)
        except Exception:  # noqa: BLE001
            raw = ''
        entry['msg'] = redact.text(raw, limit=MSG_MAX)
    with _RING_LOCK:
        _RING.append(entry)


def server_errors():
    with _RING_LOCK:
        return [dict(e) for e in _RING]


def reset_errors():
    """Шов тестів."""
    with _RING_LOCK:
        _RING.clear()


# --------------------------------------------------------------------------------- діагностика

def _with_home_forms(roots):
    """Корені простору/задачі + їхні форми з уже згорнутим домом (`~/…`): повідомлення в кільці записано ДО того, як відомо, чий це простір,
    тож шлях у ньому вже `~/…` — без цього імʼя теки простору (назва клієнта) лишилось би в діагностиці."""
    out = []
    homes = [h for h in redact._homes() if h]
    for prefix, label in roots:
        out.append((prefix, label))
        for h in homes:
            if prefix.rstrip('/').startswith(h + '/'):
                out.append(('~' + prefix.rstrip('/')[len(h):], label))
    return out


def sanitize_client_errors(raw, roots=()):
    """Кільце клієнта з тіла запиту → не більше 20 найновіших `{msg, file, line}`; недовірене: не-словники відкинуто, `msg` ≤ 300 і через
    `redact.text`, `file` лише `app/…`, `line` — невідʼємне ціле."""
    if not isinstance(raw, list):
        return []
    out = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        f = e.get('file')
        f = redact.text(f, limit=120) if isinstance(f, str) else ''
        line = e.get('line')
        if isinstance(line, bool) or not isinstance(line, int) or not 0 <= line <= 10 ** 7:
            line = None
        out.append({'msg': redact.text(e.get('msg'), roots=roots, limit=MSG_MAX), 'file': f if _FILE_RE.match(f) and '..' not in f else '', 'line': line})
    return out[-CLIENT_ERRORS_MAX:]


def _id(v, rx=_ID_RE):
    return redact.text(v, limit=80) if isinstance(v, str) and rx.match(v) else None


def _space_part(sp):
    """`{kind, roles, migration}`: ролі — лише id ВБУДОВАНИХ модулів (свій модуль → `own`), без налаштувань і шляхів; міграція —
    лише ключі `liga-4d…`. Тотальна."""
    if not isinstance(sp, dict) or not sp:
        return None
    try:
        builtin = deai_modules._builtin_ids()
    except Exception:  # noqa: BLE001
        builtin = set()
    roles = {}
    try:
        caps = deai_modules.capabilities(sp)
    except Exception:  # noqa: BLE001
        caps = {}
    for role in deai_modules.ROLES_CALLED:
        mid = caps.get(role)
        roles[role] = None if not mid else (redact.text(mid, limit=40) if mid in builtin else 'own')
    migration = {}
    try:
        marks = deai_modules._load_space_json(sp).get('migrations')
        if isinstance(marks, dict):
            migration = {k: 'applied' for k in sorted(marks) if isinstance(k, str) and _MIG_RE.match(k)}
    except Exception:  # noqa: BLE001
        pass
    return {'kind': 'legacy' if sp.get('legacy') else 'regular', 'roles': roles, 'migration': migration}


def build_diag(ctx, client_errors=None):
    """Діагностика, що піде з відгуком (і яку показує «Що буде надіслано»). `ctx` — готовий словник від `serve`:
    `{space, task_id, iteration, page, screen, lang, version, roots}`. Серверна частина перераховується тут, клієнтська проходить
    санітизацію. ≥ 64 КБ → кільця відкидаються першими. Тотальна: зламаний простір/задача — поля `None`."""
    ctx = ctx if isinstance(ctx, dict) else {}
    roots = _with_home_forms([(p, l) for p, l in (ctx.get('roots') or ()) if isinstance(p, str) and p])
    version = ctx.get('version')
    if not isinstance(version, str):
        version = updater.current_version(updater.PRODUCT_ROOT)
    task = None
    if ctx.get('task_id') is not None:
        task = {'id': _id(ctx.get('task_id')), 'iteration': _id(ctx.get('iteration')),
                'page': _id(ctx.get('page'), _PAGE_RE), 'screen': _id(ctx.get('screen'))}
    lang = ctx.get('lang')
    server = server_errors()
    for e in server:                      # повторно, з коренями простору: ідемпотентно
        e['msg'] = redact.text(e.get('msg'), roots=roots, limit=MSG_MAX)
    diag = {
        'version': redact.text(version, limit=40),
        'os': {'system': redact.text(platform.system(), limit=40), 'release': redact.text(platform.release(), limit=60),
               'python': redact.text(platform.python_version(), limit=20)},
        'lang': lang if lang in ('uk', 'en') else None,
        'space': _space_part(ctx.get('space')),
        'task': task,
        'errors': {'server': server, 'client': sanitize_client_errors(client_errors, roots)},
    }
    if len(json.dumps(diag, ensure_ascii=False).encode('utf-8')) > DIAG_MAX_BYTES:
        diag['errors'] = {'server': [], 'client': [], 'dropped': True}
    return diag


def shot_info(path):
    """`{available, bytes?, skipped?}` для файла кадру (`None` — кадру нема). Понад 2 МБ — `skipped: 'too-big'`, не усічення."""
    if not path:
        return {'available': False}
    try:
        n = os.path.getsize(path)
    except OSError:
        return {'available': False}
    if n > SHOT_MAX_BYTES:
        return {'available': False, 'bytes': n, 'skipped': 'too-big'}
    return {'available': True, 'bytes': n}
