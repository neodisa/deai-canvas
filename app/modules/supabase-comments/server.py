"""Вбудований модуль `supabase-comments` (роль `comments`): ВЛАСНИЙ проєкт Supabase людини як сервіс командних коментарів.

Дві половини (контракт ролі — спека 2b-2): браузерна — `adapter.js` + `supabase.min.js` (сторінки канваса, «Огляд», опубліковані
превʼю); ця — серверна: `client_config` (публічна конфігурація для сторінок), `list`/`resolve`/`reply` (агент: `inbox`) і `check`.
Лише stdlib (`urllib`, `json`, `re`, `base64`, `ssl`) і за наявності `certifi` (сховище сертифікатів для TLS; без нього — типове): без SDK, без Node, без підпроцесів. Схему таблиці `comments` (RLS, тригери, realtime) людина
один раз виконує сама з `schema.sql` (таблицю відповідей `comment_replies` — у наявному проєкті з `replies.sql`): модуль її НЕ змінює
(це потребувало б сервісного ключа, якого йому не дають).

`server.py` виконується ядром через `exec` у свіжий модуль: без імпорту `serve`, `deai_modules` чи сусідніх файлів. Із `ctx`
береться лише `ctx['settings']['url']`, `ctx['secrets']['key']` і `ctx['ModuleError']` (клас помилки ядра: `call()` пропускає
як є лише його, з кодом із таблиці `STATUS`; без класу в `ctx` — рукописний `ctx` — модуль кидає `RuntimeError`).
⚠️ `def list` ТІНИТЬ вбудовану `list` у всьому цьому файлі: тому нижче `type([])`, спискові вирази, але ніколи `list(...)`.

Адреса й ключ
  * `url` — лише `https://`, хост — DNS-імʼя (те саме правило, що в ядра для `url`-модулів: ≥ 2 міток, остання з літери, жодних
    IP і `localhost`), необовʼязковий порт, шлях лише порожній чи `/`, жодних облікових даних, параметрів і фрагмента. Власні
    домени Supabase дозволені. Усе інше — `bad-settings` (текст без самої адреси: у ній могли бути облікові дані);
  * `key` — публічний ключ (anon / publishable): друковний ASCII без пробілів (інакше зіпсував би заголовок). СЕРВІСНИЙ ключ
    (`sb_secret_…` чи JWT із `"role": "service_role"`) відхиляється: ключ модуля `public: true` потрапляє в КОЖНУ сторінку й
    превʼю, а сервісний обходить усі правила доступу — це повний доступ до бази. Ключ іде ЛИШЕ в заголовки `apikey` і
    `Authorization: Bearer` запитів до `url`, єдиним місцем — `_request`; ні в адресу, ні в тіло, ні в тексти помилок (тексти
    Supabase, що його повторили б, вичищаються), ні в журнали;
  * запити не йдуть за редиректами (`_NoRedirect`): інакше `urllib` віддав би обидва заголовки на чужий хост. 3xx — це помилка.

Тайм-аути. Ядро чекає на `check` `CHECK_TIMEOUT` = 5 с, а на `list`/`resolve` — `COMMENTS_TIMEOUT` = 10 с, і при мовчанні модуля віддає
`check-timeout` замість причини. Тому запити модуля мають ВЛАСНИЙ, коротший бюджет: `check` — `CHECK_TIMEOUT_S` = 4 с, `list`/`resolve`
— `CALL_TIMEOUT_S` = 8 с; модуль встигає віддати свій `network`/`module-error`. Це ЗАГАЛЬНИЙ бюджет ОДНОГО виклику (`check`; `list`,
`recent`, `reply`, `resolve`), а не лише строк однієї операції сокета (зʼєднання, відповідь — тайм-аут сокета, як і раніше, на операцію):
виклики з кількома послідовними запитами (коментарі, потім відповіді) ділять ОДИН дедлайн, а кожен запит іде з
`min(свій строк, що лишилося)`. Дедлайн «мʼякий»: тайм-аут `urllib` діє на кожну операцію сокета, а DNS ним не покритий, тож відповідь, що сочиться по краплі,
може трохи його перевищити. Запит до таблиці відповідей — додатковий: коли лишилося менше `REPLIES_MIN_S`, його не посилаємо
(`list` — коментарі без відповідей, `recent` — лише коментарі, `check` — `replies: None`, «не перевірено»); `reply` не пише, коли до
POST лишилося менше `REPLY_POST_MIN_S`. Інакше повільна таблиця відповідей робила б із здорового `check` ядрове `check-timeout`, а з `list` —
втрату коментарів.

Шов мережі. Запит іде в мережу в ОДНОМУ місці — `_open(req, timeout)`; тест підміняє саме його (переписує `https://<проєкт>.supabase.co` на
локальний підставний сервер), а побудова запиту, заголовки й обробка редиректів лишаються справжніми. Вимогу `https` це не
послаблює: у виробничому коді іншого входу нема.

Що робить кожна функція (REST — `<url>/rest/v1/comments`, тайм-аути — вище)
  * `client_config(ctx)` → `{'url': <канонічна адреса>, 'key': <публічний ключ>[, 'shotsBucket': <кошик скріншотів>]}`; у мережу не
    ходить. `shotsBucket` — лише коли задано налаштування `shots_bucket` (необовʼязкове; погане імʼя — `bad-settings`, у `check` теж);
  * `list(ctx, channel)` → коментарі каналу у формі CommentLayer (`rowToComment`: `html_snapshot` → `htmlSnapshot`, `born_v` →
    `bornV`…): `GET ?project_id=eq.<канал>&order=id&select=*&limit=<MAX_ROWS+1>`. Зайвий рядок понад `MAX_ROWS` лишається — ядро
    саме відкине його й ЗАЯВИТЬ про це (`truncated`), а не віддасть «повний» список мовчки;
  * `resolve(ctx, channel, id, reason, iteration=None)` → `PATCH ?id=eq.<id>&project_id=eq.<канал>&select=id` `{status: 'resolved',
    resolve_reason}` (без `resolve_reason`, коли причини нема) з `Prefer: return=representation` — за відповіддю (лише `id`)
    знаємо, скільки рядків змінено: 0 — `module-error` «коментар не знайдено», а відповідь без підтвердження — теж помилка (агент вірить відповіді й не перечитує сервіс). Повторне закриття — не помилка;
    `resolved_v` пишеться лише коли ядро передало номер ітерації (справжнє `int` ≥ 1, не `bool`), інакше не чіпається; обидва фільтри — завжди (без `id` чи каналу PATCH зачепив би
    чужі рядки, тож порожні значення відхиляються ДО запиту);
  * `check(ctx)` → `GET ?select=id&limit=1`: 200 → `ok`; 401/403 → `bad-key`; 404 чи код PostgREST `42P01`/`PGRST205` →
    `no-schema` (виконайте `schema.sql`); мережа → `network`; решта → `supabase-error`. Нічого не створює й не кидає на звичайних
    збоях (немає ключа, не прийнято, мережі нема) — вертає `{"ok": false, "error": <код>, "detail": <причина>}`.
"""
import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

#: Тайм-аут на операцію сокета для запитів до Supabase, секунди: `check` і `list`/`resolve` — РАНІШЕ за тайм-аути ядра (5 і 10 с),
#: щоб відповісти своїм вердиктом/текстом, а не `check-timeout` (див. docstring). Тести ставлять малі.
CHECK_TIMEOUT_S = 4
CALL_TIMEOUT_S = 8
#: Скільки коментарів каналу бере агент; запитуємо на один більше (див. docstring), решту відсікає й рахує ядро.
MAX_ROWS = 5000
#: Більше цього відповідь не читаємо: `list` (рядки з `html_snapshot` і знімками) і решта (один рядок чи помилка).
MAX_BODY = 64 << 20
MAX_SMALL = 8 << 20
#: Довжина тексту Supabase у помилці (ядро ріже до 300 само; ми — раніше й обачніше).
MSG_MAX = 200
UA = 'deai-canvas-supabase-comments/1.1'
TABLE_PATH = '/rest/v1/comments'
REPLIES_PATH = '/rest/v1/comment_replies'
#: Скільки відповідей каналу бере `list` (запитуємо на один більше за `MAX_ROWS * 4`, як і для коментарів), скільки — `recent`, скільки
#: `id` батьківських коментарів іде в один фільтр `in.(…)`; межі довжини тексту відповіді й автора в `reply`.
REPLIES_PER_COMMENT = 4
RECENT_REPLIES = 200
IN_CHUNK = 100
REPLY_TEXT_MAX = 4000
REPLY_AUTHOR_MAX = 100
#: Найменший залишок бюджету, з яким ще посилаємо ДОДАТКОВИЙ запит до відповідей, і з яким `reply` ще посилає POST (секунди).
REPLIES_MIN_S = 0.5
REPLY_POST_MIN_S = 2
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
#: Кошик Storage для скріншотів пінів (налаштування `shots_bucket`): правило імені кошика Supabase, лише нижній регістр.
_BUCKET_RE = re.compile(r'[a-z0-9][a-z0-9_-]{0,62}', re.ASCII)
_BAD_BUCKET = 'shots_bucket: імʼя кошика Storage — малі латинські літери, цифри, «-» і «_», до 63 знаків'
#: Кожен знак керуючого діапазону (C0, DEL, C1) з тексту сервісу прибирається.
_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')
#: Перше, що чує людина, коли вставила не той ключ: сервісний ключ у сторінках — це повний доступ до бази.
_SERVICE_KEY = 'це сервісний ключ — потрібен публічний anon/publishable'
_NO_REPLIES = 'у проєкті нема таблиці відповідей — виконайте replies.sql у SQL-редакторі проєкту'
_NO_TIME = 'таблицю відповідей не перевірено — не вистачило часу'
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
    """ЄДИНЕ місце, де запит іде в мережу (шов для тестів, див. docstring): без переходів за редиректами."""
    return _opener.open(req, timeout=timeout)


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


def _is_service_key(key):
    """Сервісний ключ: нове `sb_secret_…` чи JWT (три частини через `.`), чия корисна частина (base64url JSON) каже
    `"role": "service_role"`. Публічні — `sb_publishable_…` і JWT з `"role": "anon"` — проходять. Не розібране — не сервісний."""
    if key.startswith('sb_secret_'):
        return True
    parts = key.split('.')
    if len(parts) != 3:
        return False
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
    except (ValueError, RecursionError):            # `binascii.Error` і `UnicodeDecodeError` — підкласи `ValueError`
        return False
    return isinstance(claims, dict) and claims.get('role') == 'service_role'


def _need_key(ctx):
    key = _key(ctx)
    if not key:
        raise _error(ctx, 'bad-settings', 'key: публічний ключ (anon / publishable) не задано')
    if not _KEY_RE.fullmatch(key):
        raise _error(ctx, 'bad-settings', 'key: ключ має недопустимі символи (очікується один рядок без пробілів)')
    if _is_service_key(key):
        raise _error(ctx, 'bad-settings', 'key: ' + _SERVICE_KEY)
    return key


def _bucket(ctx):
    """Кошик скріншотів пінів або `''` (налаштування нема чи порожнє — скріншоти не вантажимо). Інше — `bad-settings`."""
    st = ctx.get('settings') if isinstance(ctx, dict) else None
    raw = st.get('shots_bucket') if isinstance(st, dict) else None
    if raw is None or (isinstance(raw, str) and not raw.strip(' \t\r\n')):
        return ''
    if not isinstance(raw, str) or not _BUCKET_RE.fullmatch(raw.strip(' \t\r\n')):
        raise _error(ctx, 'bad-settings', _BAD_BUCKET)
    return raw.strip(' \t\r\n')


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


def _request(ctx, method, query, *, timeout, body=None, prefer=None, limit=MAX_SMALL, table=TABLE_PATH):
    """Один запит до `<url><table>` (типово `/rest/v1/comments`, відповіді — `REPLIES_PATH`): ЄДИНЕ місце, де є `apikey` і `Authorization: Bearer <ключ>`. Повертає
    `(статус, тіло-байти)` для будь-якої відповіді (4xx/5xx/3xx теж — рішення про них ухвалює викликач); `timeout` — секунди на
    операцію сокета. Мережа, тайм-аут, обрив — `_NetworkError('Supabase недоступний (<клас збою>)')`; відповідь більша за
    `limit` — `_ResponseError`. Ключа в текстах нема."""
    base = _base(ctx)
    key = _need_key(ctx)
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key, 'Accept': 'application/json', 'User-Agent': UA}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if prefer:
        headers['Prefer'] = prefer
    req = urllib.request.Request(base + table + ('?' + query if query else ''), data=data, method=method, headers=headers)
    status, payload = 0, b''
    try:
        try:
            with _open(req, timeout) as resp:
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


def _classify(status, payload, key, replies=False):
    """Невдала відповідь (`status` не 2xx) → `(рубрика, текст)`; рубрики: `no-schema`, `bad-key`, `supabase-error`. Код PostgREST «таблиці
    нема» важить більше за статус (старіші версії віддають його не з 404). `replies=True` — запит до `comment_replies`: тексти
    називають таблицю відповідей і `replies.sql`, а не `comments` і `schema.sql`."""
    code, msg = _code_and_message(payload, key)
    if code in NO_SCHEMA_CODES or status == 404:
        if replies:
            return 'no-schema', _NO_REPLIES
        return 'no-schema', 'у проєкті нема таблиці comments — виконайте schema.sql у SQL-редакторі проєкту'
    if status in (401, 403):
        text = ('Supabase не прийняв ключ' if status == 401 else 'Supabase відмовив у доступі')
        text += f' (HTTP {status})' + (f': {msg}' if msg else '')
        where = 'comment_replies (replies.sql)' if replies else 'comments (schema.sql)'
        return 'bad-key', text + ('' if status == 401 else f' — перевірте ключ і права на таблицю {where}')
    if 300 <= status < 400:
        return 'supabase-error', f'Supabase відповів переадресацією (HTTP {status}): за нею не йдемо — перевірте адресу проєкту'
    return 'supabase-error', f'Supabase відповів HTTP {status}' + (f': {msg}' if msg else '')


def _fail(ctx, status, payload, replies=False):
    """Помилка модуля за невдалою відповіддю: `module-error` (код ядра) з текстом `_classify` (`replies` — див. там)."""
    _, text = _classify(status, payload, _key(ctx), replies)
    return _error(ctx, 'module-error', text)


def _deadline(total):
    """Дедлайн виклику модуля: `total` секунд від зараз (монотонний годинник). Див. «Тайм-аути» у docstring файла."""
    return time.monotonic() + total


def _left(deadline):
    return deadline - time.monotonic()


def _timeout(deadline, per_op):
    """Тайм-аут запиту: свій строк, але не більше, ніж лишилося до дедлайну виклику (і не менше крихітного додатного)."""
    return max(0.05, min(per_op, _left(deadline)))


def _row_to_comment(r):
    """Рядок таблиці → коментар CommentLayer (як `rowToComment` у `adapter.js`); не обʼєкт — як є: ядро саме порахує його зіпсованим."""
    if not isinstance(r, dict):
        return r
    return {'id': r.get('id'), 'author': r.get('author'), 'text': r.get('text'), 'status': r.get('status'), 'fp': r.get('fp'),
            'htmlSnapshot': r.get('html_snapshot') or None, 'meta': r.get('meta') or None,
            'bornV': r.get('born_v'), 'resolvedV': r.get('resolved_v'), 'resolveReason': r.get('resolve_reason'), 'ts': r.get('ts')}


def _need_text(ctx, value, what):
    """Непорожній рядок, який можна закодувати в UTF-8: самотній сурогат (`\\ud800`, непрочитний байт аргументу CLI) у фільтрі не
    закодувати, і відмова — наша, з фіксованим текстом, а не виняток `urllib.parse.quote` із символом усередині."""
    if not isinstance(value, str) or not value:
        raise _error(ctx, 'module-error', f'{what} не задано')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise _error(ctx, 'module-error', f'{what}: недопустимі символи (самотній сурогат)') from None
    return value


def client_config(ctx):
    """ПУБЛІЧНА конфігурація для сторінок: канонічна адреса проєкту, публічний ключ і (коли задано) кошик скріншотів
    `shotsBucket` — адаптер тоді вміє `uploadShot`. У мережу не ходить."""
    cfg = {'url': _base(ctx), 'key': _need_key(ctx)}
    bucket = _bucket(ctx)
    if bucket:
        cfg['shotsBucket'] = bucket
    return cfg


def _replies_rows(ctx, query, limit, deadline):
    """Рядки таблиці `comment_replies` за запитом або `None` на БУДЬ-ЯКИЙ збій (нема таблиці, HTTP, мережа, завелика чи не-списокова
    відповідь) і коли до `deadline` лишилося менше `REPLIES_MIN_S` (тоді запит і не йде): відповіді додаткові, викликач без них
    обходиться й ніколи не кидає через них."""
    if _left(deadline) < REPLIES_MIN_S:
        return None
    try:
        status, payload = _request(ctx, 'GET', query, timeout=_timeout(deadline, CALL_TIMEOUT_S), limit=limit, table=REPLIES_PATH)
    except Exception:  # noqa: BLE001 — `_ResponseError`, мережа: див. docstring
        return None
    if not 200 <= status < 300:
        return None
    rows = _json(payload)
    return rows if isinstance(rows, type([])) else None


def list(ctx, channel):  # noqa: A001 — імʼя функції ролі
    channel = _need_text(ctx, channel, 'канал коментарів')
    dl = _deadline(CALL_TIMEOUT_S)
    query = f'project_id=eq.{_quote(channel)}&order=id&select=*&limit={MAX_ROWS + 1}'
    try:
        status, payload = _request(ctx, 'GET', query, timeout=_timeout(dl, CALL_TIMEOUT_S), limit=MAX_BODY)
    except _ResponseError as e:
        raise _error(ctx, 'module-error', _clean(e, _key(ctx))) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload)
    rows = _json(payload)
    if not isinstance(rows, type([])):
        raise _error(ctx, 'module-error', 'Supabase повернув відповідь, що не є списком коментарів')
    comments = [_row_to_comment(r) for r in rows]
    # Відповіді — ДОДАТОК: збій їх читання (нема таблиці, HTTP-помилка, мережа, завелика відповідь) не відбирає в агента коментарі.
    # Порядок стабільний: `created_at`, за рівних — `id` (так само читає адаптер). Лишилося мало часу — без відповідей.
    replies = _replies_rows(ctx, f'project_id=eq.{_quote(channel)}&order=created_at.asc,id.asc'
                                 f'&select=id,comment_id,author,text,ts,edited_ts,agent&limit={MAX_ROWS * REPLIES_PER_COMMENT + 1}',
                            MAX_BODY, dl)
    if replies:
        by_id = {c['id']: c for c in comments if isinstance(c, dict) and isinstance(c.get('id'), str)}
        for r in replies:
            parent = by_id.get(r.get('comment_id')) if isinstance(r, dict) else None
            if parent is None:                              # сирота (коментар видалили старим клієнтом): не показуємо
                continue
            item = {'id': r.get('id'), 'author': r.get('author'), 'text': r.get('text'), 'ts': r.get('ts')}
            if r.get('edited_ts') is not None:
                item['editedTs'] = r.get('edited_ts')
            if r.get('agent') is True:
                item['agent'] = True
            parent.setdefault('replies', []).append(item)
    return comments


RECENT_ROWS = 200        # «нових» на вкладці більше не покажемо; найновіші — за `created_at`
# `recent` віддає не більше 200 найновіших відкритих рядків, тож число на вкладці може трохи завищуватись; основа «побаченого» для
# вкладки охоплює лише відкриті — це прийнятно.


def recent(ctx, channel):
    """Відкриті коментарі каналу для лічильника «нових» (Deai 0.27.0, роль `comments`, необовʼязкова): лише `id, ts, author,
    status, version` — БЕЗ знімків HTML, скріншотів і `fp` (урок квоти трафіку 21.10.2026: опит вкладок іде раз на 90 с).

    Далі (0.34) — відповіді на ВІДКРИТІ коментарі, найновіші першими, не більше 200: `{id, ts, author, status: 'open', version,
    parent}`, де `parent` — id коментаря, `version` — з нього. Тексту й знімків тут нема: це лише лічильник. Підсумок — коментарі
    (≤ 200), потім відповіді (≤ 200). Збій у частині відповідей (нема таблиці, помилка, мережа, брак часу в спільному бюджеті виклику) —
    віддаємо самі коментарі.

    Вікно відповідей — «200 НАЙНОВІШИХ відповідей каналу», як вікно коментарів — «200 найновіших коментарів»: воно береться ДО відбору
    за відкритим батьком. Нова відповідь завжди серед найновіших, тож її можна пропустити лише коли після неї до закритих
    коментарів прийшло понад 200 новіших відповідей. Це прийнятно (число — лише підказка на вкладці)."""
    channel = _need_text(ctx, channel, 'канал коментарів')
    dl = _deadline(CALL_TIMEOUT_S)
    query = (f'project_id=eq.{_quote(channel)}&status=eq.open'
             f'&select=id,ts,author,status,version:meta->>version&order=created_at.desc&limit={RECENT_ROWS}')
    try:
        status, payload = _request(ctx, 'GET', query, timeout=_timeout(dl, CALL_TIMEOUT_S), limit=MAX_SMALL)
    except _ResponseError as e:
        raise _error(ctx, 'module-error', _clean(e, _key(ctx))) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload)
    rows = _json(payload)
    if not isinstance(rows, type([])):
        raise _error(ctx, 'module-error', 'Supabase повернув відповідь, що не є списком коментарів')
    items = [{'id': r.get('id'), 'ts': r.get('ts'), 'author': r.get('author'), 'status': r.get('status'),
              'version': r.get('version')} for r in rows if isinstance(r, dict)]
    try:
        return items + _recent_replies(ctx, channel, dl)
    except Exception:  # noqa: BLE001 — відповіді додаткові: будь-який збій їхньої частини лишає самі коментарі
        return items


def _in_list(ids):
    """Значення фільтра `in.(…)`: кожен `id` у подвійних лапках (кома, дужки, лапка в `id` не ламають список; `\\` і `"` екрануються
    `\\`), а кожне значення ще й `%XX`-кодується (`_quote`) — структурні `(`, `,`, `)` лишаються буквальними."""
    return 'in.(' + ','.join(_quote('"' + i.replace('\\', '\\\\').replace('"', '\\"') + '"') for i in ids) + ')'


def _recent_replies(ctx, channel, dl):
    rows = _replies_rows(ctx, f'project_id=eq.{_quote(channel)}&select=id,comment_id,author,ts&order=created_at.desc,id.desc'
                              f'&limit={RECENT_REPLIES}', MAX_SMALL, dl)
    rows = [r for r in (rows or []) if isinstance(r, dict) and isinstance(r.get('comment_id'), str) and r.get('comment_id')]
    parents = {}
    ids = [i for i in dict.fromkeys(r['comment_id'] for r in rows)]
    for n in range(0, len(ids), IN_CHUNK):
        if _left(dl) < REPLIES_MIN_S:
            return []                                       # бюджет вичерпано посеред батьків: лише коментарі
        status, payload = _request(ctx, 'GET', f'id={_in_list(ids[n:n + IN_CHUNK])}&project_id=eq.{_quote(channel)}&status=eq.open'
                                               '&select=id,version:meta->>version', timeout=_timeout(dl, CALL_TIMEOUT_S), limit=MAX_SMALL)
        got = _json(payload) if 200 <= status < 300 else None
        if not isinstance(got, type([])):
            return []                                       # частина батьків невідома: не вгадуємо — лише коментарі
        for p in got:
            if isinstance(p, dict) and isinstance(p.get('id'), str):
                parents[p['id']] = p.get('version')
    return [{'id': r.get('id'), 'ts': r.get('ts'), 'author': r.get('author'), 'status': 'open',
             'version': parents[r['comment_id']], 'parent': r['comment_id']} for r in rows if r['comment_id'] in parents]


def resolve(ctx, channel, id, reason, iteration=None):  # noqa: A002 — імена аргументів ролі
    channel = _need_text(ctx, channel, 'канал коментарів')
    id = _need_text(ctx, id, 'id коментаря')
    body = {'status': 'resolved'}
    if isinstance(reason, str) and reason:
        body['resolve_reason'] = _utf8(reason)          # текст, а не ідентифікатор: непрочитний знак стає `?`, закриття не губиться
    if type(iteration) is int and iteration >= 1:     # `bool` — підклас `int`: `True` не номер ітерації
        body['resolved_v'] = iteration
    query = f'id=eq.{_quote(id)}&project_id=eq.{_quote(channel)}&select=id'      # у відповіді лише `id`: рахуємо змінені рядки
    try:
        status, payload = _request(ctx, 'PATCH', query, timeout=CALL_TIMEOUT_S, body=body, prefer='return=representation')   # один запит: його строк і є бюджет виклику
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


def reply(ctx, channel, id, text, author):  # noqa: A002 — імена аргументів ролі
    """Відповідь агента на ВІДКРИТИЙ коментар: `POST comment_replies` (`agent: true`). Повертає `{'id': <id відповіді>}`. Необовʼязкова
    для ядра (`ROLE_OPTIONAL_FUNCTIONS` про неї ще не знає — це справа агента), тож модуль валідний і без неї в ядрі.

    Умови й межі:
      * текст МОВЧКИ обрізається до 4000 знаків (після `strip()`), автор — до 100;
      * гонка із закриттям: коментар перевіряється GET-ом, а POST іде окремо — відповідь може лягти на коментар, який щойно закрили;
        це прийнятно;
      * спільний дедлайн виклику (`CALL_TIMEOUT_S`) ділять GET і POST: коли до POST лишилося менше `REPLY_POST_MIN_S`, він НЕ
        посилається — `module-error` «відповідь не надіслано» (код `network` у ядра для виклику нема, `module-error` — його статус 502);
      * POST, що вичерпав тайм-аут на боці клієнта, МІГ усе ж вставити рядок (відповіді ми не дочекались): це прийнятно, повтор дасть
        другу відповідь з іншим id."""
    channel = _need_text(ctx, channel, 'канал коментарів')
    id = _need_text(ctx, id, 'id коментаря')
    if not isinstance(text, str) or not text.strip():
        raise _error(ctx, 'module-error', 'текст відповіді не задано')
    if not isinstance(author, str) or not author.strip():
        raise _error(ctx, 'module-error', 'автора відповіді не задано')
    text = _utf8(text.strip())[:REPLY_TEXT_MAX]
    author = _utf8(author.strip())[:REPLY_AUTHOR_MAX]
    dl = _deadline(CALL_TIMEOUT_S)
    try:
        status, payload = _request(ctx, 'GET', f'id=eq.{_quote(id)}&project_id=eq.{_quote(channel)}&select=id,status',
                                   timeout=_timeout(dl, CALL_TIMEOUT_S))
    except _ResponseError as e:
        raise _error(ctx, 'module-error', _clean(e, _key(ctx))) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload)
    found = _json(payload)
    if not isinstance(found, type([])):
        raise _error(ctx, 'module-error', 'Supabase повернув відповідь, що не є списком коментарів')
    if not found or not isinstance(found[0], dict):
        raise _error(ctx, 'module-error', 'коментар не знайдено')
    if found[0].get('status') != 'open':
        raise _error(ctx, 'module-error', 'коментар закрито — відповідати можна лише на відкритий')
    if _left(dl) < REPLY_POST_MIN_S:
        raise _error(ctx, 'module-error', 'Supabase відповів надто повільно — відповідь не надіслано, спробуйте ще раз')
    rid = str(uuid.uuid4())
    body = {'id': rid, 'comment_id': id, 'project_id': channel, 'author': author, 'text': text,
            'ts': time.strftime('%d.%m.%Y %H:%M'), 'agent': True}
    try:
        status, payload = _request(ctx, 'POST', 'select=id', timeout=_timeout(dl, CALL_TIMEOUT_S), body=body, prefer='return=representation',
                                   table=REPLIES_PATH)
    except _ResponseError as e:
        raise _error(ctx, 'module-error', _clean(e, _key(ctx))) from None
    if not 200 <= status < 300:
        raise _fail(ctx, status, payload, replies=True)        # нема таблиці → `_NO_REPLIES`; 403 → права на comment_replies
    saved = _json(payload)
    if not isinstance(saved, type([])) or not saved:
        raise _error(ctx, 'module-error', 'Supabase не підтвердив запис відповіді (відповідь без створеного рядка)')
    return {'id': rid}


def _check_replies(ctx, dl):
    """Таблиця коментарів справна → `ok` лишається `True` ЩО Б не сталося з відповідями; `replies` каже, чи вони доступні:
    `True` / `False` / `None` (не перевірено: до `dl` лишилося менше `REPLIES_MIN_S`, запит не йшов)."""
    base = 'таблиця comments доступна'
    if _left(dl) < REPLIES_MIN_S:
        return {'ok': True, 'replies': None, 'detail': base + '; ' + _NO_TIME}
    try:
        status, payload = _request(ctx, 'GET', 'select=id&limit=1', timeout=_timeout(dl, CHECK_TIMEOUT_S), table=REPLIES_PATH)
    except _NetworkError as e:
        why = str(e)
    except Exception as e:  # noqa: BLE001 — завелика відповідь, зіпсований ключ: текст, а не виняток
        why = _clean(getattr(e, 'message', None) or e, _key(ctx))
    else:
        if status == 200:
            if isinstance(_json(payload), type([])):
                return {'ok': True, 'replies': True, 'detail': 'таблиці comments і comment_replies доступні'}
            why = 'Supabase відповів HTTP 200, але не списком рядків'
        else:
            kind, why = _classify(status, payload, _key(ctx), replies=True)
            if kind == 'no-schema':
                return {'ok': True, 'replies': False,
                        'detail': base + '; для відповідей виконайте replies.sql у SQL-редакторі проєкту'}
    return {'ok': True, 'replies': False, 'detail': base + '; таблиця відповідей не відповіла: ' + why}


def check(ctx):
    try:
        _base(ctx)
    except Exception as e:  # noqa: BLE001 — `bad-settings` (чи `RuntimeError` без класу ядра): вердикт, а не виняток
        return {'ok': False, 'error': 'bad-settings', 'detail': _clean(getattr(e, 'message', None) or e, '')}
    try:
        _bucket(ctx)
    except Exception as e:  # noqa: BLE001 — `bad-settings`: вердикт, а не виняток
        return {'ok': False, 'error': 'bad-settings', 'detail': _clean(getattr(e, 'message', None) or e, '')}
    if not _key(ctx):
        return {'ok': False, 'error': 'bad-key', 'detail': 'Публічний ключ (anon / publishable) не задано'}
    dl = _deadline(CHECK_TIMEOUT_S)
    try:
        status, payload = _request(ctx, 'GET', 'select=id&limit=1', timeout=_timeout(dl, CHECK_TIMEOUT_S))
    except _NetworkError as e:
        return {'ok': False, 'error': 'network', 'detail': str(e)}
    except Exception as e:  # noqa: BLE001 — зіпсований ключ (`bad-settings`), завелика відповідь: вердикт, а не виняток
        code = getattr(e, 'code', None)
        return {'ok': False, 'error': 'bad-key' if code == 'bad-settings' else 'supabase-error',
                'detail': _clean(getattr(e, 'message', None) or e, _key(ctx))}
    if status == 200:
        if isinstance(_json(payload), type([])):
            return _check_replies(ctx, dl)
        return {'ok': False, 'error': 'supabase-error', 'detail': 'Supabase відповів HTTP 200, але не списком рядків таблиці comments'}
    kind, text = _classify(status, payload, _key(ctx))
    if kind == 'no-schema':
        return {'ok': False, 'error': 'no-schema', 'detail': 'виконайте schema.sql у SQL-редакторі проєкту'}
    return {'ok': False, 'error': kind, 'detail': text}
