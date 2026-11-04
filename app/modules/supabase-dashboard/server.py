"""Вбудований модуль `supabase-dashboard` (роль `dashboard`): ВЛАСНИЙ проєкт Supabase людини як сховище карток команди.

Ядро (`app/dashboard.py`) вирішує, що таке картка, і веде синк; модуль лише ЗБЕРІГАЄ картки (`push`) і ВІДДАЄ рядки команди
(`rows`). Контракт ролі — `docs/modules/authoring.md`, розділ «The `dashboard` role». Схему таблиці людина один раз виконує
сама з `schema.sql`: модуль її не змінює.

Лише stdlib (`urllib`, `json`, `re`, `base64`, `ssl`) і за наявності `certifi`. `server.py` виконується ядром через `exec` у
свіжий модуль: без імпорту `serve`, `deai_modules` чи сусідніх файлів (хелпери адреси/TLS ТУТ ПРОДУБЛЬОВАНО з
`supabase-comments`, а не імпортовано: модулі не знають один про одного). Із `ctx` береться `ctx['settings']['url'|'table']`,
`ctx['secrets']['key']`, `ctx['ModuleError']` і прапорець `ctx['legacy']` (див. нижче).
⚠️ Для однорідності з `supabase-comments` перевірки типу — `isinstance(x, type([]))`, а не `list`.

Адреса, ключ, таблиця
  * `url` — ті самі правила, що в `supabase-comments` (лише https, DNS-імʼя, без шляху й облікових даних); не за правилами —
    `module-error`. Запити не йдуть за редиректами (`_NoRedirect`): інакше `urllib` віддав би заголовки з ключем на чужий хост;
  * `key` — НЕПУБЛІЧНИЙ ключ (`service_role` чи ключ окремої ролі): у картках імʼя й пошта дизайнера, а публічний ключ проєкту
    їде в кожне опубліковане превʼю. Тому `check` відмовляє публічному (`sb_publishable_…`, JWT з `"role": "anon"`). Ключ іде
    ЛИШЕ в заголовки `apikey` і `Authorization: Bearer` запитів до `url` (єдине місце — `_request`); ні в адресу, ні в тіло,
    ні в тексти помилок;
  * `table` — типово `deai_dashboard`, інакше за `[a-z_][a-z0-9_]{0,62}`.
  ⚠️ Шлях ЛІГИ (`ctx['legacy'] is True`, ctx будує ядро з конфігу установки): ключ там — той самий, що й до 4c-1, тож `check`
  публічність НЕ перевіряє (паритет з 0.11.0); `rows`/`push`/`open_comments` публічності ключа не перевіряють НІКОЛИ — вирішує
  лише `check`, а справжню межу ставить сама база (RLS).

Тексти помилок: фіксовані слова + HTTP-статус + код PostgREST (`[A-Za-z0-9]{1,10}`), ≤ 200 знаків. ⛔ Тіла запиту й відповіді
(і `message` Supabase, що могло б повторити значення картки) у текст НЕ потрапляють; значення ключа вичищається ще раз у `_clean`.

Шов мережі — `_open(req, timeout)`: ЄДИНЕ місце, де запит іде в мережу (тест підміняє саме його).

Форми запитів (знімок 0.11.0: `tests/fixtures/dashboard/before-4c1.json`, `team_read` і `upsert_http`)
  * `rows` — `GET <url>/rest/v1/<table>?select=<TEAM_KEYS>&limit=500`, тайм-аут `READ_TIMEOUT_S` = 4 (було 3);
  * `push` — `POST <url>/rest/v1/<table>?on_conflict=id`, `Prefer: resolution=merge-duplicates|ignore-duplicates,return=minimal`,
    `Content-Type: application/json`, пакетами до `BATCH` = 50 карток (було по одній), тайм-аут `PUSH_TIMEOUT_S` = 15 на пакет;
  * `open_comments` — `GET <url>/rest/v1/comments?status=eq.open&select=project_id`.
"""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request

#: Колонки рядка команди (як `TEAM_KEYS` ядра): тільки їх читає `rows`.
TEAM_KEYS = ('id', 'name', 'jira', 'jira_status', 'jira_status_cat', 'open_comments', 'thumb_url', 'code_url',
             'updated_at', 'designer', 'iterations', 'pages')
#: Ядро чекає на `rows` трохи довше (`dashboard.READ_TIMEOUT` = 6 с): власний тайм-аут (на операцію сокета) коротший, щоб відповісти своїм текстом, а не `check-timeout`.
READ_TIMEOUT_S = 4
#: Пакет `push`; ядро дає на весь виклик 60 с.
PUSH_TIMEOUT_S = 15
OPEN_TIMEOUT_S = 10
BATCH = 50
MAX_ROWS = 500
DEFAULT_TABLE = 'deai_dashboard'
#: Таблиця коментарів `supabase-comments` у тому ж проєкті (лише читання лічильників).
COMMENTS_TABLE = 'comments'
_TABLE_RE = re.compile(r'[a-z_][a-z0-9_]{0,62}', re.ASCII)
MAX_BODY = 16 << 20
MSG_MAX = 200
#: Коди PostgREST «таблиці нема»: `42P01` (relation does not exist), `PGRST205` (нема в кеші схеми).
NO_SCHEMA_CODES = ('42P01', 'PGRST205')
_CODE_RE = re.compile(r'[A-Za-z0-9]{1,10}', re.ASCII)
_URL_RE = re.compile(r'https://([A-Za-z0-9.-]+)(?::([0-9]{1,5}))?/?', re.ASCII | re.IGNORECASE)
_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.ASCII)
_TLD_START = re.compile(r'[a-z]', re.ASCII)
#: Ключ — друковний ASCII без пробілів: усе інше зіпсувало б заголовок (і потрапило б у текст помилки).
_KEY_RE = re.compile(r'[\x21-\x7e]+')
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')
_BAD_URL = ('url: потрібна адреса проєкту Supabase виду https://<ref>.supabase.co — лише https, імʼя хоста (не IP і не localhost), '
            'без шляху, параметрів і облікових даних')
_BAD_TABLE = 'table: імʼя таблиці — малі латинські літери, цифри й «_», не з цифри, до 63 знаків'
_PUBLIC_KEY = 'key: потрібен непублічний ключ (service_role чи ключ окремої ролі): публічний anon/publishable їде в кожне превʼю'
_NO_SCHEMA = 'у проєкті нема таблиці дашборда — запустіть schema.sql у SQL-редакторі проєкту'


class _CodedError(RuntimeError):
    """Помилка з кодом, коли в `ctx` нема класу ядра (рукописний `ctx`)."""

    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code = code
        self.message = message


class _NetworkError(RuntimeError):
    """Supabase недосяжний: мережа, тайм-аут, обрив, TLS (текст — без ключа й тіл)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Нікуди не йти за 3xx: відповідь лишається помилкою `HTTPError`, а заголовки з ключем — у нас."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _tls():
    """Перевірений TLS: сховище certifi, коли пакет є (Python з python.org на macOS не бачить системного), інакше типове."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 — нема certifi чи зіпсований: типовий контекст
        return ssl.create_default_context()


_opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_tls()))


def _open(req, timeout):
    """ЄДИНЕ місце, де запит іде в мережу (шов для тестів): без переходів за редиректами."""
    return _opener.open(req, timeout=timeout)


def _error(ctx, code, message):
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    if isinstance(cls, type) and issubclass(cls, Exception):
        return cls(code, message=message)
    return _CodedError(code, message)


def _host_ok(host):
    """DNS-імʼя з ДВОХ і більше міток, остання з літери, ≤ 253 знаків: тому не проходять IP у будь-якій формі і `localhost`."""
    labels = host.split('.')
    return (len(host) <= 253 and len(labels) >= 2 and all(_LABEL.fullmatch(x) for x in labels)
            and _TLD_START.match(labels[-1]) is not None)


def _setting(ctx, name):
    st = ctx.get('settings') if isinstance(ctx, dict) else None
    return st.get(name) if isinstance(st, dict) else None


def _base(ctx):
    """Канонічна адреса проєкту (`https://<хост>[:порт]`, без `/` в кінці). Нема адреси — `dashboard-unconfigured`, погана —
    `module-error` (текст без самої адреси: у ній могли бути облікові дані)."""
    raw = _setting(ctx, 'url')
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise _error(ctx, 'dashboard-unconfigured', 'url: адресу проєкту Supabase не задано')
    if not isinstance(raw, str):
        raise _error(ctx, 'module-error', _BAD_URL)
    m = _URL_RE.fullmatch(raw.strip(' \t\r\n'))
    if m is None:
        raise _error(ctx, 'module-error', _BAD_URL)
    host, port = m.group(1).lower(), m.group(2)
    if not _host_ok(host) or (port is not None and not 1 <= int(port) <= 65535):
        raise _error(ctx, 'module-error', _BAD_URL)
    return 'https://' + host + (f':{int(port)}' if port is not None else '')


def _key(ctx):
    """Ключ або `''`, коли його нема (чи тип не той)."""
    sec = ctx.get('secrets') if isinstance(ctx, dict) else None
    key = sec.get('key') if isinstance(sec, dict) else None
    return key.strip(' \t\r\n') if isinstance(key, str) else ''


def _need_key(ctx):
    """Ключ для запиту: непорожній, один рядок друковного ASCII. ⛔ Публічність тут НЕ перевіряється (див. docstring: це робить
    лише `check`, і не в ЛІГИ)."""
    key = _key(ctx)
    if not key:
        raise _error(ctx, 'dashboard-unconfigured', 'key: ключ не задано')
    if not _KEY_RE.fullmatch(key):
        raise _error(ctx, 'module-error', 'key: ключ має недопустимі символи (очікується один рядок без пробілів)')
    return key


def _is_public_key(key):
    """Публічний ключ: нове `sb_publishable_…` чи JWT (три частини через `.`), чия корисна частина (base64url JSON) каже
    `"role": "anon"`. Не розібране — не публічний (`check` не вигадує відмов)."""
    if key.startswith('sb_publishable_'):
        return True
    parts = key.split('.')
    if len(parts) != 3:
        return False
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
    except (ValueError, RecursionError):            # `binascii.Error` і `UnicodeDecodeError` — підкласи `ValueError`
        return False
    return isinstance(claims, dict) and claims.get('role') == 'anon'


def _table(ctx):
    """Таблиця дашборда: налаштування `table` чи `DEFAULT_TABLE`; не за правилом — `module-error`."""
    raw = _setting(ctx, 'table')
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DEFAULT_TABLE
    if not isinstance(raw, str) or not _TABLE_RE.fullmatch(raw.strip(' \t\r\n')):
        raise _error(ctx, 'module-error', _BAD_TABLE)
    return raw.strip(' \t\r\n')


def _clean(text, key, limit=MSG_MAX):
    """Текст для повідомлення: без керівних знаків і переносів, без ключа, без самотніх сурогатів, не довше `limit`."""
    text = ' '.join(_CONTROL.sub(' ', str(text)).split()).encode('utf-8', 'replace').decode('utf-8')
    if key:
        text = text.replace(key, '***')
    return text[:limit]


def _request(ctx, method, table, query, *, timeout, body=None, prefer=None):
    """Один запит до `<url>/rest/v1/<table>`: ЄДИНЕ місце, де є `apikey` і `Authorization: Bearer <ключ>`. Повертає
    `(статус, тіло-байти)` для будь-якої відповіді (4xx/5xx/3xx теж — рішення ухвалює викликач). Мережа, тайм-аут, обрив —
    `_NetworkError('Supabase недоступний (<клас збою>)')`; відповідь більша за `MAX_BODY` — `dashboard-error`. Заголовки — рівно
    ті, що в знімку 0.11.0 (`apikey`, `Authorization`, для запису `Content-Type`, `Prefer`)."""
    base = _base(ctx)
    key = _need_key(ctx)
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key}
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if prefer:
        headers['Prefer'] = prefer
    req = urllib.request.Request(f'{base}/rest/v1/{table}' + ('?' + query if query else ''), data=data, method=method,
                                 headers=headers)
    status, payload = 0, b''
    try:
        try:
            with _open(req, timeout) as resp:
                status, payload = resp.status, resp.read(MAX_BODY + 1)
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                payload = e.read(MAX_BODY + 1)
            finally:
                e.close()
    except Exception as e:  # noqa: BLE001 — URLError, тайм-аут, обрив, TLS, `http.client.*`: для людини це одне — «недоступний»
        reason = getattr(e, 'reason', None)
        raise _NetworkError('Supabase недоступний (' + type(reason if isinstance(reason, BaseException) else e).__name__
                            + ')') from None
    if len(payload) > MAX_BODY:
        raise _error(ctx, 'dashboard-error', 'відповідь Supabase завелика')
    return status, payload


def _json(payload):
    """Розібраний JSON або `None` (порожнє тіло, не JSON, не UTF-8, надто глибоке вкладення)."""
    try:
        return json.loads(payload.decode('utf-8'))
    except (ValueError, RecursionError):
        return None


def _pg_code(payload):
    """Код PostgREST з тіла помилки (`''`, коли нема чи форма не та). ⛔ `message` не читаємо: воно могло б повторити значення з
    тіла запиту; код — короткий токен `[A-Za-z0-9]{1,10}`."""
    data = _json(payload)
    code = data.get('code') if isinstance(data, dict) else None
    return code if isinstance(code, str) and _CODE_RE.fullmatch(code) else ''


def _no_schema(status, payload):
    return _pg_code(payload) in NO_SCHEMA_CODES or status == 404


def _problem(status, payload, key):
    """Текст невдалої відповіді (`status` не 2xx): лише фіксовані слова, HTTP-статус і код PostgREST."""
    if _no_schema(status, payload):
        return _NO_SCHEMA
    code = _pg_code(payload)
    if status == 401:
        text = 'Supabase не прийняв ключ (HTTP 401)'
    elif status == 403:
        text = 'Supabase відмовив у доступі (HTTP 403) — перевірте ключ і права на таблицю'
    elif 300 <= status < 400:
        text = f'Supabase відповів переадресацією (HTTP {status}): за нею не йдемо — перевірте адресу проєкту'
    else:
        text = f'Supabase відповів HTTP {status}'
    return _clean(text + (f' [{code}]' if code else ''), key)


def _fail(ctx, status, payload):
    """`dashboard-error` за невдалою відповіддю сервісу."""
    return _error(ctx, 'dashboard-error', _problem(status, payload, _key(ctx)))


def _unreachable(ctx, e):
    return _error(ctx, 'dashboard-error', _clean(e, _key(ctx)))


def rows(ctx):
    table = _table(ctx)
    query = 'select=' + ','.join(TEAM_KEYS) + f'&limit={MAX_ROWS}'
    try:
        status, payload = _request(ctx, 'GET', table, query, timeout=READ_TIMEOUT_S)
    except _NetworkError as e:
        raise _unreachable(ctx, e) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload)
    data = _json(payload)
    if not isinstance(data, type([])):
        raise _error(ctx, 'module-error', 'Supabase повернув відповідь, що не є списком рядків дашборда')
    return data[:MAX_ROWS]


def _prepare(cards):
    """`(готові, збійні)`: готові — `[(id, картка без None-ключів)]`, збійні — `{ключ: текст}` для того, що не картка.
    ⛔ `None` не шлемо: у `merge-duplicates` він ЗАТИРАЄ наявне значення (ядро теж не шле, але модуль не покладається на це).
    ⛔ `id` у виклику УНІКАЛЬНІ: дві картки з одним `id` в одному `POST` PostgreSQL відхиляє цілим запитом (`ON CONFLICT DO UPDATE
    command cannot affect row a second time`, 21000) — і всі до 50 карток пакета потрапили б у `failed` через чужий дубль. Тому
    лишається ОСТАННЯ картка з цим `id` (пізніша — свіжіший стан), на місці ПЕРШОЇ появи `id`; раніші дублі — не збій: їх
    витіснено, у `ok` вони не рахуються (`ok` — кількість унікальних карток)."""
    ready, bad = {}, {}
    for i, c in enumerate(cards):
        cid = c.get('id') if isinstance(c, dict) else None
        if not isinstance(cid, str) or not cid:
            bad[f'#{i}'] = 'картка без id'
            continue
        ready[cid] = {k: v for k, v in c.items() if v is not None}      # `dict` лишає порядок першої появи, значення — останнє
    return list(ready.items()), bad


def _batches(ready):
    """Пакети до `BATCH` карток З ОДНАКОВИМ НАБОРОМ КЛЮЧІВ. ⚠️ PostgREST у масиві з різними наборами ключів заповнює відсутні
    `null`ом, а `merge-duplicates` тоді ЗАТЕРЛО б наявні значення (саме тому не шлемо `None`): тож картки без, скажімо,
    `jira_status` не можна класти в один запит із тими, що його мають. Порядок — за першою появою набору й карток."""
    groups = {}
    for cid, card in ready:
        groups.setdefault(frozenset(card), []).append((cid, card))
    out = []
    for items in groups.values():
        for i in range(0, len(items), BATCH):
            out.append(items[i:i + BATCH])
    return out


def push(ctx, cards, mode):
    if mode not in ('merge', 'insert'):
        raise _error(ctx, 'module-error', "push: mode — 'merge' або 'insert'")
    if not isinstance(cards, type([])):
        raise _error(ctx, 'module-error', 'push: cards — список карток')
    table = _table(ctx)
    prefer = ('resolution=merge-duplicates' if mode == 'merge' else 'resolution=ignore-duplicates') + ',return=minimal'
    ready, failed = _prepare(cards)
    ok, down, reached = 0, None, False
    for batch in _batches(ready):
        ids = [cid for cid, _ in batch]
        if down is not None:                     # сервіс не відповів — решту пакетів не мучимо (15 с на кожен)
            failed.update({cid: down for cid in ids})
            continue
        try:
            status, payload = _request(ctx, 'POST', table, 'on_conflict=id', timeout=PUSH_TIMEOUT_S,
                                       body=[card for _, card in batch], prefer=prefer)
        except _NetworkError as e:
            if not reached:
                raise _unreachable(ctx, e) from None      # жодної відповіді сервісу: збій виклику, а не окремих карток
            down = _clean(e, _key(ctx))
            failed.update({cid: down for cid in ids})
            continue
        reached = True
        if 200 <= status < 300:
            ok += len(batch)
        else:
            text = _problem(status, payload, _key(ctx))
            failed.update({cid: text for cid in ids})
    return {'ok': ok, 'failed': failed}


def open_comments(ctx):
    try:
        status, payload = _request(ctx, 'GET', COMMENTS_TABLE, 'status=eq.open&select=project_id', timeout=OPEN_TIMEOUT_S)
    except _NetworkError as e:
        raise _unreachable(ctx, e) from None
    if not 200 <= status < 300:
        if _no_schema(status, payload):
            return {}                            # таблиці коментарів нема (інший модуль чи інший проєкт) — лічильників нема
        raise _fail(ctx, status, payload)
    data = _json(payload)
    if not isinstance(data, type([])):
        raise _error(ctx, 'module-error', 'Supabase повернув відповідь, що не є списком коментарів')
    counts = {}
    for r in data:
        ch = r.get('project_id') if isinstance(r, dict) else None
        if isinstance(ch, str) and ch:
            counts[ch] = counts.get(ch, 0) + 1
    return counts


def _verdict(error, detail, key=''):
    return {'ok': False, 'error': error, 'detail': _clean(detail, key)}


def check(ctx):
    """Вердикт `{"ok": bool, "error"?, "detail"?}` (контракт ядра): налаштування (адреса, таблиця, ключ) → `module-error`; для
    не-ЛІГИ публічний ключ → `public-key`; потім `GET <table>?select=id&limit=1` за `READ_TIMEOUT_S`. Збоїв не кидає."""
    key = _key(ctx)
    try:
        _base(ctx)
        _table(ctx)
        _need_key(ctx)
    except Exception as e:  # noqa: BLE001 — налаштування не годяться: вердикт, а не виняток
        return _verdict('module-error', getattr(e, 'message', None) or e, key)
    if not ctx.get('legacy') and _is_public_key(key):
        return _verdict('public-key', _PUBLIC_KEY)    # ⛔ не `module-error`: той клієнт підписує «Модуль упав», а ключ — вина налаштування
    try:
        status, payload = _request(ctx, 'GET', _table(ctx), 'select=id&limit=1', timeout=READ_TIMEOUT_S)
    except _NetworkError as e:
        return _verdict('network', e, key)
    except Exception as e:  # noqa: BLE001 — завелика відповідь: вердикт, а не виняток
        return _verdict('dashboard-error', getattr(e, 'message', None) or e, key)
    if 200 <= status < 300:
        if isinstance(_json(payload), type([])):
            return {'ok': True, 'detail': 'таблиця дашборда доступна'}
        return _verdict('dashboard-error', f'Supabase відповів HTTP {status}, але не списком рядків таблиці дашборда')
    if _no_schema(status, payload):
        return _verdict('no-schema', _NO_SCHEMA)
    return _verdict('bad-key' if status in (401, 403) else 'dashboard-error', _problem(status, payload, key), key)
