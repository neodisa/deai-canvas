"""Вбудований модуль `supabase-comments` (роль `comments`): ВЛАСНИЙ проєкт Supabase людини як сервіс командних коментарів.

Дві половини (контракт ролі — спека 2b-2): браузерна — `adapter.js` + `supabase.min.js` (сторінки канваса, «Огляд», опубліковані
превʼю); ця — серверна: `client_config` (публічна конфігурація для сторінок), `list`/`resolve` (агент: `inbox`) і `check`.
Лише stdlib (`urllib`, `json`, `re`): без SDK, без Node, без підпроцесів. Схему таблиці `comments` (RLS, тригери, realtime) людина
один раз виконує сама з `schema.sql`: модуль її НЕ змінює (це потребувало б сервісного ключа, якого йому не дають).

`server.py` виконується ядром через `exec` у свіжий модуль: без імпорту `serve`, `deai_modules` чи сусідніх файлів. Із `ctx`
береться лише `ctx['settings']['url']`, `ctx['secrets']['key']` і `ctx['ModuleError']` (клас помилки ядра: `call()` пропускає
як є лише його, з кодом із таблиці `STATUS`; без класу в `ctx` — рукописний `ctx` — модуль кидає `RuntimeError`).
⚠️ `def list` ТІНИТЬ вбудовану `list` у всьому цьому файлі: тому нижче `type([])`, спискові вирази, але ніколи `list(...)`.

Адреса й ключ
  * `url` — лише `https://`, хост — DNS-імʼя (те саме правило, що в ядра для `url`-модулів: ≥ 2 міток, остання з літери, жодних
    IP і `localhost`), необовʼязковий порт, шлях лише порожній чи `/`, жодних облікових даних, параметрів і фрагмента. Власні
    домени Supabase дозволені. Усе інше — `bad-settings` (текст без самої адреси: у ній могли бути облікові дані);
  * `key` — публічний ключ (anon / publishable): друковний ASCII без пробілів (інакше зіпсував би заголовок). Він іде ЛИШЕ в
    заголовки `apikey` і `Authorization: Bearer` запитів до `url`, єдиним місцем — `_request`; ні в адресу, ні в тіло, ні в
    тексти помилок (тексти Supabase, що його повторили б, вичищаються), ні в журнали;
  * запити не йдуть за редиректами (`_NoRedirect`): інакше `urllib` віддав би обидва заголовки на чужий хост. 3xx — це помилка.

Шов мережі. Запит іде в мережу в ОДНОМУ місці — `_open(req)`; тест підміняє саме його (переписує `https://<проєкт>.supabase.co` на
локальний підставний сервер), а побудова запиту, заголовки й обробка редиректів лишаються справжніми. Вимогу `https` це не
послаблює: у виробничому коді іншого входу нема.

Що робить кожна функція (REST — `<url>/rest/v1/comments`, тайм-аут `TIMEOUT_S` на запит)
  * `client_config(ctx)` → `{'url': <канонічна адреса>, 'key': <публічний ключ>}`; у мережу не ходить;
  * `list(ctx, channel)` → коментарі каналу у формі CommentLayer (`rowToComment`: `html_snapshot` → `htmlSnapshot`, `born_v` →
    `bornV`…): `GET ?project_id=eq.<канал>&order=id&select=*&limit=<MAX_ROWS+1>`. Зайвий рядок понад `MAX_ROWS` лишається — ядро
    саме відкине його й ЗАЯВИТЬ про це (`truncated`), а не віддасть «повний» список мовчки;
  * `resolve(ctx, channel, id, reason)` → `PATCH ?id=eq.<id>&project_id=eq.<канал>` `{status: 'resolved', resolve_reason}` з
    `Prefer: return=representation` — за відповіддю знаємо, скільки рядків змінено: 0 — `module-error` «коментар не знайдено», а
    відповідь без підтвердження — теж помилка (агент вірить відповіді й не перечитує сервіс). Повторне закриття — не помилка;
    `resolved_v` не чіпається (номера ітерації в контракті ролі нема); обидва фільтри — завжди (без `id` чи каналу PATCH зачепив би
    чужі рядки, тож порожні значення відхиляються ДО запиту);
  * `check(ctx)` → `GET ?select=id&limit=1`: 200 → `ok`; 401/403 → `bad-key`; 404 чи код PostgREST `42P01`/`PGRST205` →
    `no-schema` (виконайте `schema.sql`); мережа → `network`; решта → `supabase-error`. Нічого не створює й не кидає на звичайних
    збоях (немає ключа, не прийнято, мережі нема) — вертає `{"ok": false, "error": <код>, "detail": <причина>}`.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

#: Тайм-аут одного запиту до Supabase, секунди (шов `_open` читає його щоразу: тести ставлять малий).
TIMEOUT_S = 10
#: Скільки коментарів каналу бере агент; запитуємо на один більше (див. docstring), решту відсікає й рахує ядро.
MAX_ROWS = 5000
#: Більше цього відповідь не читаємо: `list` (рядки з `html_snapshot` і знімками) і решта (один рядок чи помилка).
MAX_BODY = 64 << 20
MAX_SMALL = 8 << 20
#: Довжина тексту Supabase у помилці (ядро ріже до 300 само; ми — раніше й обачніше).
MSG_MAX = 200
UA = 'deai-canvas-supabase-comments/1.0'
TABLE_PATH = '/rest/v1/comments'
#: Коди PostgREST «таблиці нема»: `42P01` (relation does not exist), `PGRST205` (нема в кеші схеми).
NO_SCHEMA_CODES = ('42P01', 'PGRST205')
#: Адреса проєкту ЦІЛКОМ: `https://<хост>[:порт][/]` — жодного іншого символу (облікових даних, `?`, `#`, `\`, пробілів, не-ASCII).
_URL_RE = re.compile(r'https://([A-Za-z0-9.-]+)(?::([0-9]{1,5}))?/?', re.ASCII | re.IGNORECASE)
#: Мітка DNS: літери/цифри/дефіс, не з дефіса й не на дефіс, ≤ 63; імена не-ASCII — лише punycode (`xn--…`).
_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.ASCII)
#: Остання мітка (TLD) починається з літери: цифрова (`1` у `127.0.0.1`, `0x7f`) — це IP, а не імʼя.
_TLD_START = re.compile(r'[a-z]', re.ASCII)
#: Публічний ключ — друковний ASCII без пробілів: усе інше зіпсувало б заголовок (і потрапило б у текст помилки).
_KEY_RE = re.compile(r'[\x21-\x7e]+')
#: Кожен знак керуючого діапазону (C0, DEL, C1) з тексту сервісу прибирається.
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')
_BAD_URL = ('url: потрібна адреса проєкту Supabase виду https://<ref>.supabase.co — лише https, імʼя хоста (не IP і не localhost), '
            'без шляху, параметрів і облікових даних')


class _CodedError(RuntimeError):
    """Помилка з кодом, коли в `ctx` нема класу ядра (рукописний `ctx`)."""

    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code = code
        self.message = message


class _ResponseError(RuntimeError):
    """Збій ВІДПОВІДІ сервісу (а не налаштувань): `list`/`resolve` перетворюють його на `module-error`, `check` — на вердикт."""


class _NetworkError(_ResponseError):
    """Supabase недосяжний: мережа, тайм-аут, обрив, TLS."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Нікуди не йти за 3xx: відповідь лишається помилкою `HTTPError`, а заголовки з ключем — у нас."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _open(req):
    """ЄДИНЕ місце, де запит іде в мережу (шов для тестів, див. docstring): без переходів за редиректами."""
    return _opener.open(req, timeout=TIMEOUT_S)


def _error(ctx, code, message):
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    if isinstance(cls, type) and issubclass(cls, Exception):
        return cls(code, message=message)
    return _CodedError(code, message)


def _host_ok(host):
    """DNS-імʼя з ДВОХ і більше міток, остання з літери, ≤ 253 знаків: тому не проходять IP у будь-якій формі
    (`127.0.0.1`, `2130706433`, `0x7f.1`) і одномітковий `localhost`."""
    labels = host.split('.')
    return (len(host) <= 253 and len(labels) >= 2 and all(_LABEL.fullmatch(x) for x in labels)
            and _TLD_START.match(labels[-1]) is not None)


def _base(ctx):
    """Канонічна адреса проєкту (`https://<хост>[:порт]`, без `/` в кінці) або `bad-settings`."""
    st = ctx.get('settings') if isinstance(ctx, dict) else None
    raw = st.get('url') if isinstance(st, dict) else None
    if not isinstance(raw, str):
        raise _error(ctx, 'bad-settings', _BAD_URL)
    m = _URL_RE.fullmatch(raw.strip(' \t\r\n'))
    if m is None:
        raise _error(ctx, 'bad-settings', _BAD_URL)
    host, port = m.group(1).lower(), m.group(2)
    if not _host_ok(host) or (port is not None and not 1 <= int(port) <= 65535):
        raise _error(ctx, 'bad-settings', _BAD_URL)
    return 'https://' + host + (f':{int(port)}' if port is not None else '')


def _key(ctx):
    """Публічний ключ або `''`, коли його нема (чи тип не той)."""
    sec = ctx.get('secrets') if isinstance(ctx, dict) else None
    key = sec.get('key') if isinstance(sec, dict) else None
    return key.strip(' \t\r\n') if isinstance(key, str) else ''


def _need_key(ctx):
    key = _key(ctx)
    if not key:
        raise _error(ctx, 'bad-settings', 'key: публічний ключ (anon / publishable) не задано')
    if not _KEY_RE.fullmatch(key):
        raise _error(ctx, 'bad-settings', 'key: ключ має недопустимі символи (очікується один рядок без пробілів)')
    return key


def _quote(text):
    """Значення фільтра PostgREST: усе, крім `[A-Za-z0-9_.~-]`, — `%XX` у UTF-8 (`/` у каналі, `&`, `#`, `+`, пробіл, `,`…)."""
    return urllib.parse.quote(text, safe='')


def _utf8(text):
    """Рядок, який можна записати в UTF-8: самотній сурогат стає `?`."""
    return text.encode('utf-8', 'replace').decode('utf-8')


def _clean(text, key, limit=MSG_MAX):
    """Текст сервісу для повідомлення: без керівних знаків і переносів, без ключа, без самотніх сурогатів, не довше `limit`."""
    text = _utf8(' '.join(_CONTROL.sub(' ', str(text)).split()))
    if key:
        text = text.replace(key, '***')
    return text[:limit]


def _request(ctx, method, query, *, body=None, prefer=None, limit=MAX_SMALL):
    """Один запит до `<url>/rest/v1/comments`: ЄДИНЕ місце, де є `apikey` і `Authorization: Bearer <ключ>`. Повертає
    `(статус, тіло-байти)` для будь-якої відповіді (4xx/5xx/3xx теж — рішення про них ухвалює викликач); мережа, тайм-аут, обрив —
    `_NetworkError('Supabase недоступний (<клас збою>)')`; відповідь більша за `limit` — `_ResponseError`. Ключа в текстах нема."""
    base = _base(ctx)
    key = _need_key(ctx)
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key, 'Accept': 'application/json', 'User-Agent': UA}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if prefer:
        headers['Prefer'] = prefer
    req = urllib.request.Request(base + TABLE_PATH + ('?' + query if query else ''), data=data, method=method, headers=headers)
    status, payload = 0, b''
    try:
        try:
            with _open(req) as resp:
                status, payload = resp.status, resp.read(limit + 1)
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                payload = e.read(limit + 1)
            finally:
                e.close()
    except Exception as e:  # noqa: BLE001 — URLError, тайм-аут, обрив, TLS, `http.client.*`: для людини це одне — «недоступний»
        reason = getattr(e, 'reason', None)
        raise _NetworkError('Supabase недоступний (' + type(reason if isinstance(reason, BaseException) else e).__name__ + ')') from None
    if len(payload) > limit:
        raise _ResponseError('відповідь Supabase завелика')
    return status, payload


def _json(payload):
    """Розібраний JSON або `None` (порожнє тіло, не JSON, не UTF-8, надто глибоке вкладення)."""
    try:
        return json.loads(payload.decode('utf-8'))
    except (ValueError, RecursionError):
        return None


def _code_and_message(payload, key):
    """`(код PostgREST | '', повідомлення сервісу для людини | '')` з тіла помилки."""
    data = _json(payload)
    if not isinstance(data, dict):
        return '', ''
    code, msg = data.get('code'), data.get('message')
    return (code if isinstance(code, str) else ''), (_clean(msg, key) if isinstance(msg, str) else '')


def _classify(status, payload, key):
    """Невдала відповідь (`status` не 2xx) → `(рубрика, текст)`; рубрики: `no-schema`, `bad-key`, `supabase-error`. Код PostgREST «таблиці
    нема» важить більше за статус (старіші версії віддають його не з 404)."""
    code, msg = _code_and_message(payload, key)
    if code in NO_SCHEMA_CODES or status == 404:
        return 'no-schema', 'у проєкті нема таблиці comments — виконайте schema.sql у SQL-редакторі проєкту'
    if status in (401, 403):
        text = ('Supabase не прийняв ключ' if status == 401 else 'Supabase відмовив у доступі')
        text += f' (HTTP {status})' + (f': {msg}' if msg else '')
        return 'bad-key', text + ('' if status == 401 else ' — перевірте ключ і права на таблицю comments (schema.sql)')
    if 300 <= status < 400:
        return 'supabase-error', f'Supabase відповів переадресацією (HTTP {status}): за нею не йдемо — перевірте адресу проєкту'
    return 'supabase-error', f'Supabase відповів HTTP {status}' + (f': {msg}' if msg else '')


def _fail(ctx, status, payload):
    """Помилка модуля за невдалою відповіддю: `module-error` (код ядра) з текстом `_classify`."""
    _, text = _classify(status, payload, _key(ctx))
    return _error(ctx, 'module-error', text)


def _row_to_comment(r):
    """Рядок таблиці → коментар CommentLayer (як `rowToComment` у `adapter.js`); не обʼєкт — як є: ядро саме порахує його зіпсованим."""
    if not isinstance(r, dict):
        return r
    return {'id': r.get('id'), 'author': r.get('author'), 'text': r.get('text'), 'status': r.get('status'), 'fp': r.get('fp'),
            'htmlSnapshot': r.get('html_snapshot') or None, 'meta': r.get('meta') or None,
            'bornV': r.get('born_v'), 'resolvedV': r.get('resolved_v'), 'resolveReason': r.get('resolve_reason'), 'ts': r.get('ts')}


def _need_text(ctx, value, what):
    if not isinstance(value, str) or not value:
        raise _error(ctx, 'module-error', f'{what} не задано')
    return value


def client_config(ctx):
    """ПУБЛІЧНА конфігурація для сторінок: канонічна адреса проєкту й публічний ключ. У мережу не ходить."""
    return {'url': _base(ctx), 'key': _need_key(ctx)}


def list(ctx, channel):  # noqa: A001 — імʼя функції ролі
    channel = _need_text(ctx, channel, 'канал коментарів')
    query = f'project_id=eq.{_quote(channel)}&order=id&select=*&limit={MAX_ROWS + 1}'
    try:
        status, payload = _request(ctx, 'GET', query, limit=MAX_BODY)
    except _ResponseError as e:
        raise _error(ctx, 'module-error', _clean(e, _key(ctx))) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload)
    rows = _json(payload)
    if not isinstance(rows, type([])):
        raise _error(ctx, 'module-error', 'Supabase повернув відповідь, що не є списком коментарів')
    return [_row_to_comment(r) for r in rows]


def resolve(ctx, channel, id, reason):  # noqa: A002 — імена аргументів ролі
    channel = _need_text(ctx, channel, 'канал коментарів')
    id = _need_text(ctx, id, 'id коментаря')
    body = {'status': 'resolved', 'resolve_reason': reason if isinstance(reason, str) and reason else None}
    query = f'id=eq.{_quote(id)}&project_id=eq.{_quote(channel)}'
    try:
        status, payload = _request(ctx, 'PATCH', query, body=body, prefer='return=representation')
    except _ResponseError as e:
        raise _error(ctx, 'module-error', _clean(e, _key(ctx))) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload)
    changed = _json(payload)
    if not isinstance(changed, type([])):
        raise _error(ctx, 'module-error', 'Supabase не підтвердив закриття коментаря (відповідь без списку змінених рядків)')
    if not changed:
        raise _error(ctx, 'module-error', 'коментар не знайдено')
    return None


def check(ctx):
    try:
        _base(ctx)
    except Exception as e:  # noqa: BLE001 — `bad-settings` (чи `RuntimeError` без класу ядра): вердикт, а не виняток
        return {'ok': False, 'error': 'bad-settings', 'detail': _clean(getattr(e, 'message', None) or e, '')}
    if not _key(ctx):
        return {'ok': False, 'error': 'bad-key', 'detail': 'Публічний ключ (anon / publishable) не задано'}
    try:
        status, payload = _request(ctx, 'GET', 'select=id&limit=1')
    except _NetworkError as e:
        return {'ok': False, 'error': 'network', 'detail': str(e)}
    except Exception as e:  # noqa: BLE001 — зіпсований ключ (`bad-settings`), завелика відповідь: вердикт, а не виняток
        code = getattr(e, 'code', None)
        return {'ok': False, 'error': 'bad-key' if code == 'bad-settings' else 'supabase-error',
                'detail': _clean(getattr(e, 'message', None) or e, _key(ctx))}
    if status == 200:
        if isinstance(_json(payload), type([])):
            return {'ok': True, 'detail': 'таблиця comments доступна'}
        return {'ok': False, 'error': 'supabase-error', 'detail': 'Supabase відповів HTTP 200, але не списком рядків таблиці comments'}
    kind, text = _classify(status, payload, _key(ctx))
    if kind == 'no-schema':
        return {'ok': False, 'error': 'no-schema', 'detail': 'виконайте schema.sql у SQL-редакторі проєкту'}
    return {'ok': False, 'error': kind, 'detail': text}
