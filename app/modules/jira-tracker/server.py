"""Вбудований модуль `jira-tracker` (роль `tracker`): статуси задач із Jira Cloud за їхніми ключами.

Ядро (`app/tracker.py`) фільтрує ключі, ділить їх на пакети по 100 і нормалізує відповідь; модуль лише ХОДИТЬ у Jira
(`statuses`) і перевіряє зʼєднання (`check`). Контракт ролі — `docs/modules/authoring.md`, розділ «The `tracker` role».
Лише Jira Cloud (Basic `email:токен`); Jira Server/Data Center (особистий токен `Bearer`) — окремий модуль пізніше.

Лише stdlib (`urllib`, `json`, `re`, `base64`, `ssl`) і за наявності `certifi`. `server.py` виконується ядром через `exec` у
свіжий модуль: без імпорту `serve`, `deai_modules` чи сусідніх файлів (хелпери адреси/TLS ТУТ ПРОДУБЛЬОВАНО з модулів Supabase,
а не імпортовано: модулі не знають один про одного). Із `ctx` береться `ctx['settings']['base'|'email']`,
`ctx['secrets']['token']`, `ctx['ModuleError']` і `ctx['timeout_s']`. Прапорець `ctx['legacy']` модуль НЕ читає: для ЛІГИ
поведінка та сама (прапорець лишається в `ctx` для однорідності з 4c-1).
⚠️ Для однорідності з модулями Supabase перевірки типу — `isinstance(x, type([]))`, а не `list`.

Адреса, пошта, токен
  * `base` — адреса сайту Jira Cloud (`https://<сайт>.atlassian.net` чи власний домен): ті самі правила, що `_host_ok` модулів
    Supabase (лише https, DNS-імʼя щонайменше з двох міток, не IP і не localhost, без шляху, параметрів і облікових даних,
    необовʼязковий порт); не за правилами — `module-error`. Запити не йдуть за редиректами (`_NoRedirect`): інакше `urllib`
    віддав би заголовок `Authorization` на чужий хост;
  * `email` — один рядок до 254 знаків із `@`, без пробілів, керівних знаків і `:` (двокрапка зламала б `email:токен`);
  * `token` — API-токен Atlassian, один рядок друкованого ASCII без пробілів. НЕПУБЛІЧНИЙ: живе в `~/.deai/secrets.json`.
    Токен (і пошта) йдуть ЛИШЕ в заголовок `Authorization: Basic …` запитів до `base` (єдине місце — `_request`); ні в адресу,
    ні в тіло, ні в тексти помилок.

Тайм-аут сокета — `ctx['timeout_s']` (бюджет, який дає ядро: 4 с для екрана «Задачі», 15 с для синку дашборда); не число чи
поза 1…30 — `DEFAULT_TIMEOUT_S` = 4. Ядро чекає довше за цей бюджет, тож людина бачить текст модуля, а не `check-timeout`.

Тексти помилок: фіксовані слова + HTTP-статус, ≤ 200 знаків. ⛔ Ні токена, ні пошти, ні тіл запиту й відповіді (повідомлення
Jira могло б повторити ключі й назви задач) у текст НЕ потрапляють; значення токена й пошти вичищається ще раз у `_clean`.

Шов мережі — `_open(req, timeout)`: ЄДИНЕ місце, де запит іде в мережу (тест підміняє саме його).

Форми запитів (знімок 0.12.0: `tests/fixtures/tracker/before-4c2.json`, `jira_request`)
  * `statuses` — `POST <base>/rest/api/3/search/jql`, тіло `{"jql": "key in (K1,K2,…)", "fields": ["status"], "maxResults": 100}`,
    заголовки `Authorization: Basic base64(email:токен)`, `Accept`/`Content-Type: application/json`. Відповідь:
    `issues[].key` → `{'name': fields.status.name, 'cat': fields.status.statusCategory.key}`; запис без ключа чи статусу
    пропущено, `issues` не масив чи нема — `{}`;
  * `check` — `GET <base>/rest/api/3/myself`: 200 — «підключено»; 401/403 — «невірний email чи токен» з кодом `tracker-auth`
    (не `module-error`: екран «Підключення» підписує його «Модуль упав під час перевірки», а тут хибний токен, не збій модуля;
    `statuses` лишає `module-error` — його текст бачить синк, а не людина).
"""
import base64
import json
import re
import urllib.error
import urllib.request

DEFAULT_TIMEOUT_S = 4
MAX_TIMEOUT_S = 30
MAX_RESULTS = 100
MAX_BODY = 4 << 20
MSG_MAX = 200
#: Ключ задачі (як `tracker.KEY_RE` ядра): модуль перевіряє ще раз, бо ключі йдуть у JQL, а не тільки в ядро.
_ISSUE_KEY = re.compile(r'[A-Z][A-Z0-9_]{0,31}-[1-9][0-9]{0,9}', re.ASCII)
_URL_RE = re.compile(r'https://([A-Za-z0-9.-]+)(?::([0-9]{1,5}))?/?', re.ASCII | re.IGNORECASE)
_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.ASCII)
_TLD_START = re.compile(r'[a-z]', re.ASCII)
#: Токен — друковний ASCII без пробілів: усе інше зіпсувало б заголовок (і потрапило б у текст помилки).
_TOKEN_RE = re.compile(r'[\x21-\x7e]+')
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')
_BAD_BASE = ('base: потрібна адреса сайту Jira Cloud виду https://<сайт>.atlassian.net — лише https, імʼя хоста (не IP і не '
             'localhost), без шляху, параметрів і облікових даних')
_BAD_EMAIL = 'email: потрібна пошта облікового запису Atlassian (до 254 знаків, із «@», без пробілів і «:»)'
_BAD_TOKEN = 'token: токен має недопустимі символи (очікується один рядок без пробілів)'
_BAD_KEYS = 'keys: очікується список ключів задач виду DEMO-1 (до 100)'
_BAD_SHAPE = 'Jira повернула відповідь не тієї форми'


class _CodedError(RuntimeError):
    """Помилка з кодом, коли в `ctx` нема класу ядра (рукописний `ctx`)."""

    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code = code
        self.message = message


class _NetworkError(RuntimeError):
    """Jira недосяжна: мережа, тайм-аут, обрив, TLS (текст — без токена й тіл)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Нікуди не йти за 3xx: відповідь лишається помилкою `HTTPError`, а заголовок з токеном — у нас."""

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
    """Канонічна адреса сайту (`https://<хост>[:порт]`, без `/` в кінці). Нема адреси — `tracker-unconfigured`, погана —
    `module-error` (текст без самої адреси: у ній могли бути облікові дані)."""
    raw = _setting(ctx, 'base')
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise _error(ctx, 'tracker-unconfigured', 'base: адресу сайту Jira не задано')
    if not isinstance(raw, str):
        raise _error(ctx, 'module-error', _BAD_BASE)
    m = _URL_RE.fullmatch(raw.strip(' \t\r\n'))
    if m is None:
        raise _error(ctx, 'module-error', _BAD_BASE)
    host, port = m.group(1).lower(), m.group(2)
    if not _host_ok(host) or (port is not None and not 1 <= int(port) <= 65535):
        raise _error(ctx, 'module-error', _BAD_BASE)
    return 'https://' + host + (f':{int(port)}' if port is not None else '')


def _email(ctx):
    """Пошта або `''`, коли її нема (чи тип не той)."""
    raw = _setting(ctx, 'email')
    return raw.strip(' \t\r\n') if isinstance(raw, str) else ''


def _need_email(ctx):
    """Пошта для запиту: непорожня, ≤ 254, з `@`, без пробілів, керівних знаків і `:`. Нема — `tracker-unconfigured`."""
    email = _email(ctx)
    if not email and not isinstance(_setting(ctx, 'email'), (str, type(None))):
        raise _error(ctx, 'module-error', _BAD_EMAIL)
    if not email:
        raise _error(ctx, 'tracker-unconfigured', 'email: пошту не задано')
    if len(email) > 254 or '@' not in email or ':' in email or _CONTROL.search(email) or any(c.isspace() for c in email):
        raise _error(ctx, 'module-error', _BAD_EMAIL)
    return email


def _token(ctx):
    """Токен або `''`, коли його нема (чи тип не той)."""
    sec = ctx.get('secrets') if isinstance(ctx, dict) else None
    tok = sec.get('token') if isinstance(sec, dict) else None
    return tok.strip(' \t\r\n') if isinstance(tok, str) else ''


def _need_token(ctx):
    tok = _token(ctx)
    sec = ctx.get('secrets') if isinstance(ctx, dict) else None
    if not tok and isinstance(sec, dict) and not isinstance(sec.get('token'), (str, type(None))):
        raise _error(ctx, 'module-error', _BAD_TOKEN)
    if not tok:
        raise _error(ctx, 'tracker-unconfigured', 'token: токен не задано')
    if not _TOKEN_RE.fullmatch(tok):
        raise _error(ctx, 'module-error', _BAD_TOKEN)
    return tok


def _timeout(ctx):
    """Бюджет сокета: `ctx['timeout_s']`, коли це число в межах 1…`MAX_TIMEOUT_S`, інакше `DEFAULT_TIMEOUT_S`. `bool` — не число."""
    v = ctx.get('timeout_s') if isinstance(ctx, dict) else None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 1 <= v <= MAX_TIMEOUT_S:
        return DEFAULT_TIMEOUT_S
    return v


def _clean(text, *secrets, limit=MSG_MAX):
    """Текст для повідомлення: без керівних знаків і переносів, без значень `secrets` (токен, пошта), без самотніх сурогатів,
    не довше `limit`."""
    text = ' '.join(_CONTROL.sub(' ', str(text)).split()).encode('utf-8', 'replace').decode('utf-8')
    for s in secrets:
        if s:
            text = text.replace(s, '***')
    return text[:limit]


def _request(ctx, method, path, *, body=None):
    """Один запит до `<base><path>`: ЄДИНЕ місце, де є `Authorization: Basic base64(email:токен)`. Повертає
    `(статус, тіло-байти)` для будь-якої відповіді (4xx/5xx/3xx теж — рішення ухвалює викликач). Мережа, тайм-аут, обрив —
    `_NetworkError('Jira недосяжна (<клас збою>)')`; відповідь більша за `MAX_BODY` — `tracker-error`. Заголовки — рівно ті, що в
    знімку 0.12.0 (`Authorization`, `Accept`, `Content-Type`)."""
    base = _base(ctx)
    email = _need_email(ctx)
    token = _need_token(ctx)
    auth = base64.b64encode(f'{email}:{token}'.encode('utf-8')).decode('ascii')
    headers = {'Authorization': 'Basic ' + auth, 'Accept': 'application/json', 'Content-Type': 'application/json'}
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    status, payload = 0, b''
    try:
        try:
            with _open(req, _timeout(ctx)) as resp:
                status, payload = resp.status, resp.read(MAX_BODY + 1)
        except urllib.error.HTTPError as e:
            # ⛔ Тіло помилки НЕ читаємо: текст — лише статус, а завелике тіло 4xx не мусить обернути «HTTP 4xx» на «відповідь завелика».
            status = e.code
            e.close()
    except Exception as e:  # noqa: BLE001 — URLError, тайм-аут, обрив, TLS, `http.client.*`: для людини це одне — «недосяжна»
        reason = getattr(e, 'reason', None)
        raise _NetworkError('Jira недосяжна (' + type(reason if isinstance(reason, BaseException) else e).__name__
                            + ')') from None
    if len(payload) > MAX_BODY:
        raise _error(ctx, 'tracker-error', 'відповідь Jira завелика')
    return status, payload


def _json(payload):
    """Розібраний JSON або `None` (порожнє тіло, не JSON, не UTF-8, надто глибоке вкладення)."""
    try:
        return json.loads(payload.decode('utf-8'))
    except (ValueError, RecursionError):
        return None


def _problem(status, secrets=()):
    """`(код, текст)` невдалої відповіді (`status` не 2xx): лише фіксовані слова й HTTP-статус. ⛔ Тіло відповіді не читаємо:
    повідомлення Jira могло б повторити ключі й назви задач. 4xx/3xx — людині виправляти (`module-error`); 5xx, 408 і 429 —
    збій сервісу чи тимчасове (`tracker-error`)."""
    if status in (401, 403):
        code, text = 'module-error', f'невірний email чи токен (HTTP {status})'
    elif 300 <= status < 400:
        code, text = 'module-error', f'Jira відповіла переадресацією (HTTP {status}): за нею не йдемо — перевірте адресу сайту'
    elif status == 400:
        code, text = 'module-error', 'Jira відхилила запит (HTTP 400): перевірте ключі задач'
    elif status in (408, 429):                      # тимчасове (таймаут, ліміт запитів): людині нічого виправляти — повтор згодом
        code, text = 'tracker-error', f'Jira відповіла HTTP {status}'
    elif 400 <= status < 500:
        code, text = 'module-error', f'Jira відповіла HTTP {status}'
    else:
        code, text = 'tracker-error', f'Jira відповіла HTTP {status}'
    return code, _clean(text, *secrets)


def _secrets(ctx):
    return _token(ctx), _email(ctx)


def statuses(ctx, keys):
    if not isinstance(keys, type([])) or len(keys) > MAX_RESULTS or not all(
            isinstance(k, str) and _ISSUE_KEY.fullmatch(k) for k in keys):
        raise _error(ctx, 'module-error', _BAD_KEYS)
    if not keys:
        return {}
    body = {'jql': 'key in (' + ','.join(keys) + ')', 'fields': ['status'], 'maxResults': MAX_RESULTS}
    try:
        status, payload = _request(ctx, 'POST', '/rest/api/3/search/jql', body=body)
    except _NetworkError as e:
        raise _error(ctx, 'tracker-error', _clean(e, *_secrets(ctx))) from None
    if not 200 <= status < 300:
        code, text = _problem(status, _secrets(ctx))
        raise _error(ctx, code, text)
    data = _json(payload)
    if not isinstance(data, dict):
        raise _error(ctx, 'tracker-error', _BAD_SHAPE)
    issues = data.get('issues')
    out = {}
    for it in issues if isinstance(issues, type([])) else ():
        key = it.get('key') if isinstance(it, dict) else None
        fields = it.get('fields') if isinstance(it, dict) else None
        st = fields.get('status') if isinstance(fields, dict) else None
        name = st.get('name') if isinstance(st, dict) else None
        if not isinstance(key, str) or not key or not isinstance(name, str) or not name:
            continue
        cat = st.get('statusCategory')
        cat = cat.get('key') if isinstance(cat, dict) else None
        out[key] = {'name': name, 'cat': cat if isinstance(cat, str) else None}
    return out


def _verdict(error, detail, *secrets):
    return {'ok': False, 'error': error, 'detail': _clean(detail, *secrets)}


def check(ctx):
    """Вердикт `{"ok": bool, "error"?, "detail"?}` (контракт ядра): налаштування (адреса, пошта, токен) → `module-error`;
    потім `GET <base>/rest/api/3/myself`. Збоїв не кидає."""
    secrets = _secrets(ctx)
    try:
        _base(ctx)
        _need_email(ctx)
        _need_token(ctx)
    except Exception as e:  # noqa: BLE001 — налаштування не годяться: вердикт, а не виняток
        return _verdict('module-error', getattr(e, 'message', None) or e, *secrets)
    try:
        status, payload = _request(ctx, 'GET', '/rest/api/3/myself')
    except _NetworkError as e:
        return _verdict('network', e, *secrets)
    except Exception as e:  # noqa: BLE001 — завелика відповідь: вердикт, а не виняток
        return _verdict('tracker-error', getattr(e, 'message', None) or e, *secrets)
    if 200 <= status < 300:
        return {'ok': True, 'detail': 'підключено до Jira'}
    code, text = _problem(status, secrets)
    # ⛔ Хибні облікові дані — свій код: інакше «Підключення» напише «Модуль упав під час перевірки» (див. docstring).
    return _verdict('tracker-auth' if status in (401, 403) else code, text, *secrets)
