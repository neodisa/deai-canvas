"""Відгук (0.23): кільце помилок сервера й збирач діагностики (T6); конфіг, локальна черга й надсилання в Supabase (T7).

Модуль НЕ імпортує `serve`: контекст (простір, задача, екран, мова) збирає `serve._feedback_context` і передає готовим словником.
⛔ Приватність: у діагностику не потрапляє жоден вільний текст з файлів чи задач користувача, лише id/коди; КОЖЕН рядок проходить
`redact.text` (дім → `~`, ключі/токени/e-mail приховано, query URL відрізано)."""
import base64
import calendar
import collections
import errno
import hashlib
import http.client
import json
import os
import platform
import re
import stat
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import deai_modules
import isolation
import redact
import spaces
import updater
from atomic_io import atomic_write_json

ERRORS_MAX = 50              # кільце сервера
CLIENT_ERRORS_MAX = 20       # кільце клієнта (береться з тіла запиту)
MSG_MAX = 300                # повідомлення сервера (тепер: код + кадр, не текст)
CLIENT_MSG_MAX = 200         # повідомлення клієнта (вільний текст: коротше й через `redact.text(collapse=True)`)
DIAG_MAX_BYTES = 64 * 1024
SHOT_MAX_BYTES = 2 * 1024 * 1024

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_RING = collections.deque(maxlen=ERRORS_MAX)
_RING_LOCK = threading.Lock()
_SEQ = [0]                   # монотонний лічильник подій кільця: перегляд фіксує його, відправка бере лише записи з seq ≤ зафіксованого
SEQS_MAX = 200               # скільки номерів повторів тримає один дедубльований запис

_SEG_RE = re.compile(r'^[A-Za-z0-9_.-]{1,40}$')
_TASK_PREFIX = re.compile(r'^/t/[^/]+(?=/)')
_ID_RE = re.compile(r'^[\w-]{1,80}$')
_PAGE_RE = re.compile(r'^[\w-]+(~[0-9a-f]{8})?(@[1-9]\d{1,3})?$')
_MIG_RE = re.compile(r'^liga-4d[0-9a-z]{1,4}$')
_FILE_RE = re.compile(r'^app/[\w./-]{1,100}$')
_CODE_RE = re.compile(r'^[a-z0-9-]{1,40}$')


# --------------------------------------------------------------------------------- кільце помилок сервера

def route_of(path):
    """Лише ІМʼЯ маршруту, без query, префікса `/t/<id>`, id й зайвих сегментів: `/api/<name>`, інші — перший сегмент (`/it-assets/it1/назва/x`
    → `/it-assets`, `/api/task/it1/x` → `/api/task`). Сегмент не з `[A-Za-z0-9_.-]` (назва кирилицею, пробіли) → `*`."""
    p = str(path or '').split('?', 1)[0].split('#', 1)[0]
    p = _TASK_PREFIX.sub('', p)
    parts = [s for s in p.split('/') if s]
    if not parts:
        return '/'
    keep = 2 if parts[0] == 'api' else 1
    segs = [s if _SEG_RE.match(s) else '*' for s in parts[:keep]]
    return '/' + '/'.join(segs)


def _app_frame(exc):
    """`файл.py:рядок` ВНУТРІШНЬОГО кадру трасування (останній, що лежить у теці застосунку) або `''`. Лише імʼя файла: тека не потрібна."""
    last = ''
    tb = getattr(exc, '__traceback__', None)
    while tb is not None:
        try:
            fn = os.path.abspath(tb.tb_frame.f_code.co_filename)
            if fn.startswith(_APP_DIR + os.sep):
                last = '%s:%d' % (os.path.basename(fn), tb.tb_lineno)
        except Exception:  # noqa: BLE001
            pass
        tb = tb.tb_next
    return last


def record_error(path, exc, code=None):
    """Записати виняток у кільце. ⛔ Текст винятку НІКОЛИ не зберігається (там шляхи, імена файлів, фрагменти даних): лише ТИП і внутрішній
    кадр `файл.py:рядок`; для `OSError` — ще імʼя errno (`ENOENT`), без імені файла. З `code` (операційна відмова) — лише код."""
    entry = {'route': route_of(path), 'type': redact.text(type(exc).__name__, limit=80)}
    if code is not None:
        entry['code'] = redact.text(code, limit=60)
        entry['msg'] = ''
    else:
        parts = []
        try:
            if isinstance(exc, OSError) and isinstance(exc.errno, int):
                parts.append(errno.errorcode.get(exc.errno, ''))
            frame = _app_frame(exc)
            if frame:
                parts.append('at ' + frame)
        except Exception:  # noqa: BLE001
            pass
        entry['msg'] = redact.text(' '.join(p for p in parts if p), limit=MSG_MAX, collapse=True)
    with _RING_LOCK:
        _SEQ[0] += 1
        seq = _SEQ[0]
        last = _RING[-1] if _RING else None
        if last is not None and all(last.get(k) == entry.get(k) for k in ('route', 'type', 'msg', 'code')):
            last['count'] += 1                  # той самий збій поспіль (опитуваний маршрут): один запис із лічильником
            last['seqs'].append(seq)
            if len(last['seqs']) > SEQS_MAX:
                del last['seqs'][0]
                last['dropped'] += 1
        else:
            entry.update(count=1, seqs=[seq], dropped=0)
            _RING.append(entry)


def ring_seq():
    """Найбільший номер події кільця на цю мить (0 — порожнє)."""
    with _RING_LOCK:
        return _SEQ[0]


def server_errors(max_seq=None):
    """Знімок кільця для діагностики: `{route, type, msg, [code], count}`. `max_seq` — лише події з номером ≤ max_seq (те, що людина бачила
    в перегляді): запис, що зʼявився пізніше, відкидається, а лічильник повторів урізається до тих, що були до цього номера."""
    out = []
    with _RING_LOCK:
        for e in _RING:
            seqs = e['seqs']
            n = e['count'] if max_seq is None else e['dropped'] + sum(1 for q in seqs if q <= max_seq)
            if n == 0:
                continue                        # весь запис новіший за перегляд
            d = {k: v for k, v in e.items() if k not in ('seqs', 'dropped', 'count')}
            d['count'] = n
            out.append(d)
    return out


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
    """Кільце клієнта з тіла запиту → не більше 20 найновіших `{msg, file, line}`; недовірене: не-словники відкинуто, `msg` ≤ 200 і через
    `redact.text(collapse=True)` (шляхи → `…/імʼя`), `file` лише `app/…`, `line` — невідʼємне ціле."""
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
        out.append({'msg': redact.text(e.get('msg'), roots=roots, limit=CLIENT_MSG_MAX, collapse=True), 'file': f if _FILE_RE.match(f) and '..' not in f else '', 'line': line})
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


def build_diag(ctx, client_errors=None, max_seq=None):
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
    server = server_errors(max_seq)
    for e in server:                      # повторно, з коренями простору: ідемпотентно
        e['msg'] = redact.text(e.get('msg'), roots=roots, limit=MSG_MAX, collapse=True)
        for k in ('route', 'type', 'code'):
            if k in e:
                e[k] = redact.text(e[k], limit=80)
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


def diag_hash(diag):
    """sha256 (hex) канонічного JSON діагностики — відбиток того, що саме людина бачила в «Що буде надіслано»."""
    raw = json.dumps(diag, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8', 'replace')).hexdigest()


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


# ================================================================================ T7: конфіг, черга, надсилання

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SHIPPED_CONFIG = os.path.join(APP_DIR, 'feedback.json')
TIMEOUT_S = 10
RESPONSE_MAX = 64 * 1024
BODY_MAX = 256 * 1024                 # ліміт тіла `POST /api/feedback`
TEXT_MIN, TEXT_MAX, CONTACT_MAX = 10, 10000, 200
MAX_ATTEMPTS = 20
MAX_AGE_S = 30 * 24 * 3600
FIRST_FLUSH_DELAY_S = 10
FLUSH_EVERY_S = 3600
DIR_MODE = 0o700
FILE_MODE = 0o600
KINDS = ('bug', 'idea')
_ID_FILE_RE = re.compile(r'^[0-9a-f-]{36}$')
_SHOT_NAME_RE = re.compile(r'^[0-9a-f-]{36}\.(webp|png)$')
#: Колонки таблиці `feedback`, що їх анонімна роль має право вставляти (`ops/feedback-collector.sql`); `created_at` — НІКОЛИ (час ставить база).
ROW_COLUMNS = ('id', 'kind', 'text', 'contact', 'version', 'os', 'diag', 'shot_path')


class Transient(Exception):
    """Збій, який варто повторити (мережа, 5xx, 429). Текст — лише код: без адреси й ключа."""


class Permanent(Exception):
    """Приймач відмовив назавжди (4xx). Текст — лише код."""


# --------------------------------------------------------------------------------- конфіг

def _read_json_dict(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def key_ok(key):
    """Ключ схожий на ПУБЛІКОВАНИЙ (anon): непорожній, без пробілів/керуючих, не `sb_secret_…` і не JWT з роллю `service_role`."""
    if not isinstance(key, str) or not key or len(key) > 1000 or re.search(r'\s|[\x00-\x1f]', key):
        return False
    if key.startswith('sb_secret_'):
        return False
    if key.startswith('eyJ'):
        try:
            seg = key.split('.')[1]
            payload = json.loads(base64.urlsafe_b64decode(seg + '=' * (-len(seg) % 4)))
            if isinstance(payload, dict) and payload.get('role') == 'service_role':
                return False
        except (IndexError, ValueError):
            pass
    return True


def net_allowed(url):
    """Нормалізована адреса приймача (без `/` в кінці) або `None`. Лише `https://host[/path]` без userinfo/query/fragment;
    `http://127.0.0.1|localhost|[::1]` — лише коли `isolation.isolated()` (фейковий приймач живих тестів)."""
    if not isinstance(url, str) or not url or len(url) > 300 or re.search(r'\s|[\x00-\x1f]', url):
        return None
    try:
        u = urllib.parse.urlsplit(url)
        host = u.hostname
        port = u.port
    except ValueError:
        return None
    if not host or u.username is not None or u.password is not None or u.query or u.fragment or '@' in u.netloc:
        return None
    loopback = host in ('127.0.0.1', 'localhost', '::1')
    if u.scheme == 'https':
        pass
    elif u.scheme == 'http' and loopback and isolation.isolated():
        pass
    else:
        return None
    if port is not None and not 0 < port < 65536:
        return None
    return url.rstrip('/')


def is_loopback(url):
    try:
        return urllib.parse.urlsplit(url).hostname in ('127.0.0.1', 'localhost', '::1')
    except ValueError:
        return False


def config(env=None, home=None):
    """`{url, key}` приймача або `None` (лише локальна черга). Ланцюг: `DEAI_FEEDBACK_URL`/`DEAI_FEEDBACK_KEY` > `<DEAI_HOME>/config.json`
    (`{"feedback": {"url", "key"}}`, лише читаємо) > `app/feedback.json`. ⛔ Пара — ЦІЛІСНА з одного джерела (ключ одного проєкту не
    їде на адресу іншого); перше джерело, що щось задає, вирішує: невалідне — `None` (а не мовчазний перехід до нижчого).
    ⛔ НІКОЛИ не береться з налаштувань модулів простору (коментарі, дашборд, Teams ЛІГИ).
    Явно присутній, але порожній `DEAI_FEEDBACK_URL` — ВИМИКАЧ: приймач вимкнено, без `config.json` і `app/feedback.json` (так тести й
    живі фікстури гарантовано не б'ють у приймач, що постачається з застосунком). Порожній лише `DEAI_FEEDBACK_KEY` за відсутньої адреси
    лишається «не задано» (ланцюг іде далі)."""
    env = os.environ if env is None else env
    if 'DEAI_FEEDBACK_URL' in env and not str(env.get('DEAI_FEEDBACK_URL') or '').strip():
        return None
    try:
        home = home if home is not None else spaces.home()
    except Exception:  # noqa: BLE001
        home = None
    sources = [(env.get('DEAI_FEEDBACK_URL'), env.get('DEAI_FEEDBACK_KEY'))]
    if home:
        fb = _read_json_dict(os.path.join(home, 'config.json')).get('feedback')
        fb = fb if isinstance(fb, dict) else {}
        sources.append((fb.get('url'), fb.get('key')))
    fb = _read_json_dict(SHIPPED_CONFIG)
    sources.append((fb.get('url'), fb.get('key')))
    for url, key in sources:
        if (isinstance(url, str) and url.strip()) or (isinstance(key, str) and key.strip()):
            good = net_allowed(url.strip() if isinstance(url, str) else None)
            if good and key_ok(key):
                return {'url': good, 'key': key}
            return None
    return None


# --------------------------------------------------------------------------------- перевірка запиту

def scrub_text(s):
    """Самотні сурогати → `?`, NUL геть: такий рядок не кодується в UTF-8 і Postgres його не приймає."""
    return s.encode('utf-8', 'replace').decode('utf-8').replace('\x00', '')


def scrub_obj(o):
    if isinstance(o, str):
        return scrub_text(o)
    if isinstance(o, dict):
        return {(scrub_text(k) if isinstance(k, str) else k): scrub_obj(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [scrub_obj(v) for v in o]
    return o


def validate(payload):
    """`(чисте, None)` або `(None, (код, текст))`. `kind` ∈ bug/idea; `text` ≥ 10 (після trim) і ≤ 10 000; `contact` ≤ 200; прапорці — bool."""
    kind = payload.get('kind')
    if kind not in KINDS:
        return None, ('bad-kind', 'kind must be bug or idea')
    text = payload.get('text')
    if not isinstance(text, str):
        return None, ('text-too-short', 'text is required')
    text = scrub_text(text)
    if len(text.strip()) < TEXT_MIN:
        return None, ('text-too-short', 'text is too short')
    if len(text) > TEXT_MAX:
        return None, ('text-too-long', 'text is too long')
    contact = payload.get('contact')
    if contact is not None and not isinstance(contact, str):
        return None, ('bad-contact', 'contact must be a string')
    contact = scrub_text(contact or '').strip()
    if len(contact) > CONTACT_MAX:
        return None, ('contact-too-long', 'contact is too long')
    flags = {}
    for name, default in (('include_diag', True), ('include_shot', False)):
        v = payload.get(name, default)
        if not isinstance(v, bool):
            return None, ('bad-flag', '%s must be a boolean' % name)
        flags[name] = v
    return {'kind': kind, 'text': text.strip(), 'contact': contact or None, **flags}, None


def _image_kind(data):
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    return None


def _utc_now(now):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))


def _age(rec, now):
    try:
        return now - calendar.timegm(time.strptime(rec.get('created_at'), '%Y-%m-%dT%H:%M:%SZ'))
    except (TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------------- черга

class Outbox:
    """Локальна черга відгуків `<DEAI_HOME>/feedback/{outbox,sent,failed}/<id>.json` (теки 0700, файли 0600). Запис — ДО мережі.
    Коли писати файли машини не можна (`isolation.writes_allowed`: ізольований прогін зі справжнім `~/.deai`) — лише памʼять процесу.
    `<id>.<webp|png>` поруч із записом — байти скриншота для повтору."""

    def __init__(self, home_fn=spaces.home):
        self.home_fn = home_fn
        self._lock = threading.RLock()          # короткий: структура черги
        self._busy = set()                      # id записів, що зараз відправляються: кожен іде в мережу рівно раз (і фон, і запит)
        self._sent_ok = set()                   # успіх фіксується ПЕРШИМ: навіть якщо перенос у `sent/` не вдався, запис «надіслано»
        self._mem = {'outbox': {}, 'sent': {}, 'failed': {}}
        self._mem_shots = {}

    # --- сховище ---
    def _home(self):
        return self.home_fn()

    def _on_disk(self):
        return isolation.writes_allowed(self._home())

    def _dir(self, bucket):
        return os.path.join(self._home(), 'feedback', bucket)

    def _ensure(self):
        base = os.path.join(self._home(), 'feedback')
        os.makedirs(base, exist_ok=True)
        for d in (base, self._dir('outbox'), self._dir('sent'), self._dir('failed')):
            os.makedirs(d, exist_ok=True)
            os.chmod(d, DIR_MODE)

    def _write_json(self, bucket, rec):
        path = os.path.join(self._dir(bucket), rec['id'] + '.json')
        atomic_write_json(path, rec)
        os.chmod(path, FILE_MODE)

    def add(self, rec, shot=None):
        """Записати відгук у `outbox`. `shot` — `(байти, 'webp'|'png')` або `None`. Повертає `True`, коли запис лягає на ДИСК
        (`False` — лише памʼять: диск недоступний чи заборонений законом ізоляції). Рядки очищені від самотніх сурогатів і NUL: кодування
        ніколи не кидає. Не вдався запис JSON — файл скриншота, що вже лежить, прибирається (сирота без запису)."""
        rec = scrub_obj(rec)
        with self._lock:
            if self._on_disk():
                shot_file = None
                try:
                    self._ensure()
                    if shot:
                        fd, tmp = tempfile.mkstemp(dir=self._dir('outbox'), suffix='.tmp')
                        try:
                            with os.fdopen(fd, 'wb') as f:
                                f.write(shot[0])
                            os.chmod(tmp, FILE_MODE)
                            shot_file = os.path.join(self._dir('outbox'), rec['id'] + '.' + shot[1])
                            os.replace(tmp, shot_file)
                        except BaseException:
                            try:
                                os.remove(tmp)
                            except OSError:
                                pass
                            raise
                    self._write_json('outbox', rec)
                    return True
                except (OSError, ValueError, TypeError):
                    if shot_file:
                        try:
                            os.remove(shot_file)
                        except OSError:
                            pass
            self._mem['outbox'][rec['id']] = dict(rec)
            if shot:
                self._mem_shots[rec['id']] = shot
            return False

    def pending(self):
        """Записи `outbox` від найстарішого. Нечитабельні файли пропускаються (не губляться й не валять)."""
        with self._lock:
            out = []
            if self._on_disk():
                try:
                    names = sorted(os.listdir(self._dir('outbox')))
                except OSError:
                    names = []
                for n in names:
                    if n.endswith('.json') and _ID_FILE_RE.match(n[:-5]):
                        rec = _read_json_dict(os.path.join(self._dir('outbox'), n))
                        if rec.get('id') == n[:-5]:
                            out.append(rec)
            out.extend(dict(r) for r in self._mem['outbox'].values())
            out = [r for r in out if r.get('id') not in self._sent_ok]
            return sorted(out, key=lambda r: str(r.get('created_at')))

    def _shot_path(self, rid):
        for ext in ('webp', 'png'):
            p = os.path.join(self._dir('outbox'), rid + '.' + ext)
            if os.path.isfile(p):
                return p, ext
        return None, None

    def shot_of(self, rid):
        with self._lock:
            if rid in self._mem_shots:
                return self._mem_shots[rid]
            if self._on_disk():
                p, ext = self._shot_path(rid)
                if p:
                    try:
                        with open(p, 'rb') as f:
                            return f.read(), ext
                    except OSError:
                        return None
            return None

    def _drop_shot(self, rid):
        self._mem_shots.pop(rid, None)
        if self._on_disk():
            p, _ = self._shot_path(rid)
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass

    def update(self, rec):
        rec = scrub_obj(rec)
        with self._lock:
            if rec['id'] in self._mem['outbox']:
                self._mem['outbox'][rec['id']] = dict(rec)
                return
            if self._on_disk():
                try:
                    self._write_json('outbox', rec)
                except (OSError, ValueError, TypeError):
                    pass

    def move(self, rec, bucket):
        """`outbox` → `sent`/`failed`: файл переноситься, НЕ видаляється; байти скриншота після `sent` вже не потрібні."""
        rec = scrub_obj(rec)
        with self._lock:
            if rec['id'] in self._mem['outbox']:
                self._mem[bucket][rec['id']] = dict(self._mem['outbox'].pop(rec['id']), **rec)
                if bucket == 'sent':
                    self._mem_shots.pop(rec['id'], None)
                return
            if self._on_disk():
                try:
                    self._write_json(bucket, rec)
                    os.remove(os.path.join(self._dir('outbox'), rec['id'] + '.json'))
                    if bucket == 'sent':
                        self._drop_shot(rec['id'])
                except (OSError, ValueError, TypeError):
                    pass

    def state_of(self, rid):
        """`'sent'` | `'failed'` | `'outbox'` | `None`."""
        with self._lock:
            if rid in self._sent_ok:
                return 'sent'
            for b in ('sent', 'failed', 'outbox'):
                if rid in self._mem[b]:
                    return b
                if self._on_disk() and os.path.isfile(os.path.join(self._dir(b), rid + '.json')):
                    return b
            return None

    # --- відправка ---
    def _claim(self, rid):
        """Забрати запис на відправку: `False` — його вже шле інший потік або він уже не в `outbox` (хтось устиг раніше)."""
        with self._lock:
            if rid in self._busy or self.state_of(rid) != 'outbox':
                return False
            self._busy.add(rid)
            return True

    def _release(self, rid):
        with self._lock:
            self._busy.discard(rid)

    def flush(self, sender, first=None, now=time.time, only=None):
        """Один прохід: `only` — лише цей запис (запит НЕ чекає на чергу: хвіст дочищає фоновий потік); інакше `first` (щойно доданий)
        першим, далі решта від найстарішої. Збій мережі (`Transient`) зупиняє прохід і НЕ рахується в спроби (мережа лежить — не провина
        запису); лише `Permanent` (4xx, нечитабельний запис) додає спробу, 20 спроб — `failed/`. Дожиття — лише за віком (30 днів).
        Будь-який інший виняток на записі = `Permanent`: один поганий запис не блокує чергу. Повертає множину id, надісланих цим проходом."""
        sent = set()
        recs = self.pending()
        if only is not None:
            recs = [r for r in recs if r.get('id') == only]
        else:
            recs.sort(key=lambda r: 0 if r.get('id') == first else 1)       # стабільно: далі порядок за віком
        for rec in recs:
            rid = rec.get('id')
            if not self._claim(rid):
                continue
            try:
                if _age(rec, now()) > MAX_AGE_S or int(rec.get('attempts') or 0) >= MAX_ATTEMPTS:
                    self.move(dict(rec, failed_reason='expired'), 'failed')
                    continue
                if sender is None:
                    break
                try:
                    self._deliver(sender, rec)
                except Transient as e:
                    self.update(dict(rec, last_error=str(e)))
                    break
                except Permanent as e:
                    self.update(dict(rec, attempts=int(rec.get('attempts') or 0) + 1, last_error=str(e)))
                    continue
                except Exception:  # noqa: BLE001 — кодування, неочікуване: цей запис не повинен заблокувати решту
                    self.update(dict(rec, attempts=int(rec.get('attempts') or 0) + 1, last_error='error'))
                    continue
                with self._lock:
                    self._sent_ok.add(rid)                                  # успіх — ПЕРШИМ, до будь-якого файлового кроку
                sent.add(rid)
                try:
                    self.move(dict(rec, sent_at=_utc_now(now())), 'sent')
                except Exception:  # noqa: BLE001
                    pass
            finally:
                self._release(rid)
        return sent

    def _deliver(self, sender, rec):
        row = {k: rec.get(k) for k in ROW_COLUMNS}
        shot = self.shot_of(rec['id'])
        row['shot_path'] = None
        if shot and _SHOT_NAME_RE.match('%s.%s' % (rec['id'], shot[1])):
            try:
                sender.send_shot('%s.%s' % (rec['id'], shot[1]), shot[0], 'image/' + shot[1])
                row['shot_path'] = '%s.%s' % (rec['id'], shot[1])
            except Permanent:
                row['shot_path'] = None             # приймач скриншот відхилив назавжди: рядок усе одно їде, без нього
        sender.send_row(row)


OUTBOX = Outbox()


def reset_outbox():
    """Шов тестів: свіжа черга (память процесу очищено)."""
    global OUTBOX
    OUTBOX = Outbox()
    return OUTBOX


# --------------------------------------------------------------------------------- Supabase

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _default_opener(url):
    handlers = [_NoRedirect()]
    if is_loopback(url):
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers).open


class SupabaseSender:
    """Єдине місце, де є `apikey`/`Authorization`. Запит — insert-only (анонімна роль не має `select`): `Prefer: return=minimal`,
    `id` — uuid клієнта, `409` — «вже є». Тексти винятків — лише коди (`http-503`, `network`): адреси й ключа в них нема."""

    def __init__(self, url, key, opener=None):
        self.url, self._key = url, key
        self.opener = opener or _default_opener(url)

    def __repr__(self):
        return 'SupabaseSender()'

    def _post(self, path, body, headers):
        h = {'apikey': self._key, 'Authorization': 'Bearer ' + self._key}
        h.update(headers)
        req = urllib.request.Request(self.url + path, data=body, headers=h, method='POST')
        try:
            resp = self.opener(req, timeout=TIMEOUT_S)
            try:
                status = getattr(resp, 'status', None) or resp.getcode()
                data = resp.read(RESPONSE_MAX)
            finally:
                try:
                    resp.close()
                except Exception:  # noqa: BLE001
                    pass
            return status, data
        except urllib.error.HTTPError as e:
            try:
                data = e.read(RESPONSE_MAX)
            except Exception:  # noqa: BLE001
                data = b''
            return e.code, data
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
            raise Transient('network') from None

    @staticmethod
    def _classify(status, dup_ok=False):
        if 200 <= status < 300 or status == 409 or dup_ok:
            return
        if status in (408, 425, 429) or status >= 500:
            raise Transient('http-%d' % status)
        if 300 <= status < 400:
            raise Permanent('redirect')
        raise Permanent('http-%d' % status)

    def send_row(self, row):
        body = json.dumps(scrub_obj({k: row.get(k) for k in ROW_COLUMNS}), ensure_ascii=False).encode('utf-8', 'replace')
        status, _ = self._post('/rest/v1/feedback', body, {'Content-Type': 'application/json', 'Prefer': 'return=minimal'})
        self._classify(status)

    def send_shot(self, name, data, mime):
        status, body = self._post('/storage/v1/object/feedback-shots/' + name, data, {'Content-Type': mime, 'x-upsert': 'false'})
        self._classify(status, dup_ok=(status == 400 and b'Duplicate' in body))


# --------------------------------------------------------------------------------- вхід

def submit(clean, diag, shot=None, sender=None, now=time.time):
    """Прийняти відгук: ЗАПИС у чергу — до мережі; далі одна спроба для ЦЬОГО запису (решту черги дочищає фоновий потік: запит ніколи не чекає на хвіст). `clean` — результат
    `validate`; `diag` — вже зібрана діагностика (`{}`, коли людина зняла галочку); `shot` — `(байти, ext)` або `None`.
    Повертає `{id, state: 'sent'|'queued', reason?}`; `reason` ∈ `no-collector` | `network-blocked` | `offline` | `rejected` | `memory-only`."""
    rid = str(uuid.uuid4())
    rec = {'id': rid, 'created_at': _utc_now(now()), 'kind': clean['kind'], 'text': clean['text'], 'contact': clean['contact'],
           'version': redact.text((diag or {}).get('version') or updater.current_version(updater.PRODUCT_ROOT), limit=40),
           'os': redact.text('%s %s' % (platform.system(), platform.release()), limit=80) + ' / Python ' + platform.python_version(),
           'diag': diag if clean.get('include_diag', True) else {}, 'shot_path': None, 'attempts': 0, 'last_error': ''}
    if shot and _image_kind(shot[0]) == shot[1] and len(shot[0]) <= SHOT_MAX_BYTES:
        rec['shot_path'] = '%s.%s' % (rid, shot[1])
    else:
        shot = None
    on_disk = OUTBOX.add(rec, shot)
    cfg = config()
    reason = None
    if cfg is None:
        reason = 'no-collector'
    elif not isolation.isolated() or is_loopback(cfg['url']):
        sender = sender or SupabaseSender(cfg['url'], cfg['key'])
        OUTBOX.flush(sender, only=rid, now=now)         # лише СВІЙ запис: хвіст черги — справа фонового потоку
        st = OUTBOX.state_of(rid)
        if st == 'sent':
            return {'id': rid, 'state': 'sent'}
        last = next((r for r in OUTBOX.pending() if r.get('id') == rid), {})
        reason = 'rejected' if str(last.get('last_error', '')).startswith('http-4') else 'offline'
    else:
        reason = 'network-blocked'
    return {'id': rid, 'state': 'queued', 'reason': reason, **({'memory_only': True} if not on_disk else {})}


def flush_pending(now=time.time):
    """Дочистити чергу (фоновий потік і ручний виклик): без конфігу чи в ізольованому прогоні з не-loopback адресою нічого не робить."""
    cfg = config()
    if cfg is None or (isolation.isolated() and not is_loopback(cfg['url'])):
        return 0
    return len(OUTBOX.flush(SupabaseSender(cfg['url'], cfg['key']), now=now))


def start_background(first_delay=FIRST_FLUSH_DELAY_S, every=FLUSH_EVERY_S, stop=None):
    """Daemon-потік дочищення черги: перша спроба через `first_delay` с, далі щогодини. Не стартує (`None`) з `DEAI_NO_UPDATE_CHECK=1`, у
    ізольованому прогоні й коли приймача не налаштовано."""
    if os.environ.get('DEAI_NO_UPDATE_CHECK') == '1' or isolation.isolated() or config() is None:
        return None
    stop = stop or threading.Event()

    def loop():
        if stop.wait(first_delay):
            return
        while True:
            try:
                flush_pending()
            except Exception:  # noqa: BLE001
                pass
            if stop.wait(every):
                return

    t = threading.Thread(target=loop, name='deai-feedback-flush', daemon=True)
    t.stop_event = stop
    t.start()
    return t
