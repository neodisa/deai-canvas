"""Вбудований модуль `supabase-teams` (роль `notify`): сповіщення Teams про нові коментарі з ВЛАСНОГО проєкту Supabase людини.

Саму доставку (новий пін → картка в Teams через вебхук із Vault, журнал, тиша) робить БАЗА: `schema.sql`, який людина один
раз виконує в SQL-редакторі проєкту. Модуль лише ходить у RPC цієї схеми: читає стан тиші (`mute_state`), перемикає тишу
каналу (`mute_set`) і чесно відповідає, чи все налаштовано (`check`). Контракт ролі — `docs/modules/authoring.md`, розділ
«The `notify` role»; логіку (нормалізація стану, вигляд каналу, перевірка аргументів) веде ядро `app/notify.py`.

Лише stdlib (`urllib`, `json`, `re`, `base64`, `ssl`) і за наявності `certifi`. `server.py` виконується ядром через `exec` у
свіжий модуль: без імпорту `serve`, `deai_modules` чи сусідніх файлів (хелпери адреси/TLS ТУТ ПРОДУБЛЬОВАНО з
`supabase-dashboard`, а не імпортовано: модулі не знають один про одного). Із `ctx` береться `ctx['settings']['url']`,
`ctx['secrets']['key']`, `ctx['ModuleError']` і прапорець `ctx['legacy']` (див. нижче).
⚠️ Для однорідності з `supabase-dashboard` перевірки типу — `isinstance(x, type([]))`, а не `list`.

Адреса й ключ
  * `url` — ті самі правила, що в `supabase-comments` (лише https, DNS-імʼя, без шляху й облікових даних); не за правилами —
    `module-error`. Запити не йдуть за редиректами (`_NoRedirect`): інакше `urllib` віддав би заголовки з ключем на чужий хост;
  * `key` — НЕПУБЛІЧНИЙ ключ (`service_role` чи ключ окремої ролі): RPC тиші в схемі модуля віддані лише `service_role`, а
    публічний ключ їде в кожне опубліковане превʼю. Тому `check` відмовляє публічному (`sb_publishable_…`, JWT з
    `"role": "anon"`). Ключ іде ЛИШЕ в заголовки `apikey` і `Authorization: Bearer` запитів до `url` (єдине місце —
    `_request`); ні в адресу, ні в тіло, ні в тексти помилок.
  ⚠️ Шлях ЛІГИ (`ctx['legacy'] is True`, ctx будує ядро з конфігу установки): база ЛІГИ — стара схема comment-layer, де RPC
  тиші віддані ключу сторінки (публічному), а `teams_notify_health` НЕМАЄ. Тож для `legacy` `check` публічність ключа НЕ
  перевіряє і `teams_notify_health` НЕ кличе (паритет з 0.13.0); `mute_state`/`mute_set` публічності не перевіряють НІКОЛИ —
  вирішує лише `check`, а справжню межу ставить сама база (`grant`).

Тексти помилок: фіксовані слова + HTTP-статус + код PostgREST (`[A-Za-z0-9]{1,10}`), ≤ 200 знаків. ⛔ Тіла запиту й відповіді
(і `message` Supabase) у текст НЕ потрапляють; значення ключа вичищається ще раз у `_clean`.

Шов мережі — `_open(req, timeout)`: ЄДИНЕ місце, де запит іде в мережу (тест підміняє саме його).

Форми запитів (знімок 0.13.0: `tests/fixtures/notify/before-4c3.json`, `rpc_requests`)
  * `mute_state` — `POST <url>/rest/v1/rpc/teams_mute_state` `{}`;
  * `mute_set` — `POST <url>/rest/v1/rpc/teams_mute_set` `{"p_project", "p_muted", "p_by"}`;
  * заголовки рівно `apikey`, `Authorization: Bearer <ключ>`, `Content-Type: application/json`; тайм-аут `TIMEOUT_S` = 8;
  * `check` додає `POST …/rpc/teams_notify_health` `{"window_hours": 6}` (не для `legacy`).
"""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request

#: Тайм-аут сокета (на операцію): ядро чекає 10 с (`notify.NOTIFY_TIMEOUT`), тож модуль відповідає СВОЇМ текстом помилки раніше.
TIMEOUT_S = 8
#: Вікно (годин) для `teams_notify_health` у `check`.
HEALTH_HOURS = 6
MAX_BODY = 1 << 20
MSG_MAX = 200
#: Коди PostgREST «функції нема»: `PGRST202` (нема в кеші схеми), `42883` (undefined_function).
NO_FUNCTION_CODES = ('PGRST202', '42883')
CHANNEL_MAX = BY_MAX = 200
_CODE_RE = re.compile(r'[A-Za-z0-9]{1,10}', re.ASCII)
_URL_RE = re.compile(r'https://([A-Za-z0-9.-]+)(?::([0-9]{1,5}))?/?', re.ASCII | re.IGNORECASE)
_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.ASCII)
_TLD_START = re.compile(r'[a-z]', re.ASCII)
#: Ключ — друковний ASCII без пробілів: усе інше зіпсувало б заголовок (і потрапило б у текст помилки).
_KEY_RE = re.compile(r'[\x21-\x7e]+')
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')
_BAD_URL = ('url: потрібна адреса проєкту Supabase виду https://<ref>.supabase.co — лише https, імʼя хоста (не IP і не localhost), '
            'без шляху, параметрів і облікових даних')
_PUBLIC_KEY = ('key: потрібен непублічний ключ (service_role чи ключ окремої ролі): тишу Teams перемикає лише він, а публічний '
               'anon/publishable їде в кожне превʼю')
_NO_SCHEMA = 'у проєкті нема функцій сповіщень Teams — запустіть schema.sql у SQL-редакторі проєкту'
_NO_WEBHOOK = 'у Vault нема секрету teams_webhook_url — картки в Teams не підуть'


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
    """Канонічна адреса проєкту (`https://<хост>[:порт]`, без `/` в кінці). Нема адреси — `notify-unconfigured`, погана —
    `module-error` (текст без самої адреси: у ній могли бути облікові дані)."""
    raw = _setting(ctx, 'url')
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise _error(ctx, 'notify-unconfigured', 'url: адресу проєкту Supabase не задано')
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
        raise _error(ctx, 'notify-unconfigured', 'key: ключ не задано')
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


def _clean(text, key, limit=MSG_MAX):
    """Текст для повідомлення: без керівних знаків і переносів, без ключа, без самотніх сурогатів, не довше `limit`."""
    text = ' '.join(_CONTROL.sub(' ', str(text)).split()).encode('utf-8', 'replace').decode('utf-8')
    if key:
        text = text.replace(key, '***')
    return text[:limit]


def _rpc(ctx, name, body):
    """Один виклик `POST <url>/rest/v1/rpc/<name>`: ЄДИНЕ місце, де є `apikey` і `Authorization: Bearer <ключ>`. Повертає
    `(статус, тіло-байти)` для будь-якої відповіді (4xx/5xx/3xx теж — рішення ухвалює викликач). Мережа, тайм-аут, обрив —
    `_NetworkError('Supabase недоступний (<клас збою>)')`; відповідь більша за `MAX_BODY` — `notify-error`. Заголовки — рівно
    ті, що в знімку 0.13.0 (`apikey`, `Authorization`, `Content-Type`)."""
    base = _base(ctx)
    key = _need_key(ctx)
    req = urllib.request.Request(f'{base}/rest/v1/rpc/{name}', data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'apikey': key, 'Authorization': 'Bearer ' + key,
                                          'Content-Type': 'application/json'})
    status, payload = 0, b''
    try:
        try:
            with _open(req, TIMEOUT_S) as resp:
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
        raise _error(ctx, 'notify-error', 'відповідь Supabase завелика')
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


def _no_function(status, payload):
    return status == 404 or _pg_code(payload) in NO_FUNCTION_CODES


def _problem(status, payload, key):
    """Текст невдалої відповіді (`status` не 2xx): лише фіксовані слова, HTTP-статус і код PostgREST."""
    if _no_function(status, payload):
        return _NO_SCHEMA
    code = _pg_code(payload)
    if status == 401:
        text = 'Supabase не прийняв ключ (HTTP 401)'
    elif status == 403:
        text = 'Supabase відмовив у доступі (HTTP 403) — перевірте ключ: тишу Teams перемикає лише непублічний'
    elif 300 <= status < 400:
        text = f'Supabase відповів переадресацією (HTTP {status}): за нею не йдемо — перевірте адресу проєкту'
    else:
        text = f'Supabase відповів HTTP {status}'
    return _clean(text + (f' [{code}]' if code else ''), key)


def _fail(ctx, status, payload):
    """`notify-error` за невдалою відповіддю сервісу."""
    return _error(ctx, 'notify-error', _problem(status, payload, _key(ctx)))


def _unreachable(ctx, e):
    return _error(ctx, 'notify-error', _clean(e, _key(ctx)))


def mute_state(ctx):
    try:
        status, payload = _rpc(ctx, 'teams_mute_state', {})
    except _NetworkError as e:
        raise _unreachable(ctx, e) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload)
    data = _json(payload)
    if not isinstance(data, type([])):
        raise _error(ctx, 'notify-error', 'Supabase повернув відповідь, що не є списком замовчаних каналів')
    return data


def mute_set(ctx, channel, muted, by):
    if not isinstance(channel, str) or not 1 <= len(channel) <= CHANNEL_MAX:
        raise _error(ctx, 'module-error', f'mute_set: channel — рядок від 1 до {CHANNEL_MAX} знаків')
    if type(muted) is not bool:
        raise _error(ctx, 'module-error', 'mute_set: muted — true або false')
    if not isinstance(by, str) or len(by) > BY_MAX:
        raise _error(ctx, 'module-error', f'mute_set: by — рядок до {BY_MAX} знаків')
    try:
        status, payload = _rpc(ctx, 'teams_mute_set', {'p_project': channel, 'p_muted': muted, 'p_by': by})
    except _NetworkError as e:
        raise _unreachable(ctx, e) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload)
    data = _json(payload)
    if type(data) is not bool:
        raise _error(ctx, 'notify-error', 'Supabase повернув відповідь, що не є станом тиші (true/false)')
    return data


def _verdict(error, detail, key=''):
    return {'ok': False, 'error': error, 'detail': _clean(detail, key)}


def _count(value):
    """Лічильник зі здоровʼя: ціле число (не `bool`), інакше `None`."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def check(ctx):
    """Вердикт `{"ok": bool, "error"?, "detail"?}` (контракт ядра): налаштування (адреса, ключ — для не-ЛІГИ ще й публічність)
    → `module-error`; потім `teams_mute_state` (нема схеми → `no-schema`); для не-ЛІГИ далі `teams_notify_health`
    (нема секрету вебхука → `notify-no-webhook`, інакше ok із деталлю «доставок за 6 год: N, невдалих: M»). Збоїв не кидає."""
    key = _key(ctx)
    try:
        _base(ctx)
        _need_key(ctx)
    except Exception as e:  # noqa: BLE001 — налаштування не годяться: вердикт, а не виняток
        return _verdict('module-error', getattr(e, 'message', None) or e, key)
    legacy = bool(ctx.get('legacy'))
    if not legacy and _is_public_key(key):
        return _verdict('module-error', _PUBLIC_KEY)
    try:
        status, payload = _rpc(ctx, 'teams_mute_state', {})
        if 200 <= status < 300 and not isinstance(_json(payload), type([])):
            return _verdict('notify-error', f'Supabase відповів HTTP {status}, але не списком замовчаних каналів')
        if not 200 <= status < 300:
            return _bad(status, payload, key)
        if legacy:                                  # у базі ЛІГИ `teams_notify_health` нема: лише стан тиші
            return {'ok': True, 'detail': 'тиша Teams доступна'}
        status, payload = _rpc(ctx, 'teams_notify_health', {'window_hours': HEALTH_HOURS})
    except _NetworkError as e:
        return _verdict('network', e, key)
    except Exception as e:  # noqa: BLE001 — завелика відповідь: вердикт, а не виняток
        return _verdict('notify-error', getattr(e, 'message', None) or e, key)
    if not 200 <= status < 300:
        return _bad(status, payload, key)
    data = _json(payload)
    row = data[0] if isinstance(data, type([])) and len(data) == 1 else data
    if not isinstance(row, dict) or type(row.get('webhook_set')) is not bool:
        return _verdict('notify-error', 'Supabase повернув здоровʼя доставки не тієї форми')
    if not row['webhook_set']:
        return _verdict('notify-no-webhook', _NO_WEBHOOK)
    sent, failed = _count(row.get('sent')), _count(row.get('failed'))
    if sent is None or failed is None:
        return _verdict('notify-error', 'Supabase повернув здоровʼя доставки не тієї форми')
    return {'ok': True, 'detail': f'доставок за {HEALTH_HOURS} год: {sent}, невдалих: {failed}'}


def _bad(status, payload, key):
    """Вердикт за невдалою відповіддю: нема схеми → `no-schema`, ключ не прийнято → `bad-key`, решта — `notify-error`."""
    if _no_function(status, payload):
        return _verdict('no-schema', _NO_SCHEMA)
    return _verdict('bad-key' if status in (401, 403) else 'notify-error', _problem(status, payload, key), key)
