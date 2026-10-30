"""Вбудований модуль `vercel-publish` (роль `publish`, `publish_target: url`): зібране превʼю задачі → ВЛАСНИЙ Vercel людини.

Лише stdlib (`urllib`, `hashlib`, `json`, …). Режим `token` (типовий): без Node, без CLI, без підпроцесів — лише REST. Режим
`cli` (4b-1, див. нижче) запускає системний `npx vercel`. Диспетчер ядра будує превʼю
(`build_preview`, за потреби з паролем-гейтом у сторінках) і кличе `publish(ctx, build_dir, task)`; модуль відправляє
теку на `api.vercel.com` і повертає адресу. Роздачі, лока й запису в `iterations.json` модуль не торкається — це ядро.

`server.py` виконується ядром через `exec` у свіжий модуль: без імпорту `serve`, `deai_modules` чи сусідніх файлів.
Із `ctx` береться лише:
  * `ctx['secrets']['token']` — токен Vercel; `ctx['settings']['team']` — команда (необовʼязково);
  * `ctx['ModuleError']` — клас помилки ядра: `call()` пропускає як є лише його, з кодом із таблиці `STATUS`
    (`vercel-auth`, `vercel-busy` → 409). Усе інше, що йде з `publish` вгору, — теж `ModuleError('module-error')` з
    чистим текстом (без `RuntimeError: `/`_NetworkError: `: ядро дописало б імʼя класу, а людина бачить цей текст у
    діалозі). Без класу в `ctx` (рукописний `ctx`) модуль кидає `RuntimeError` (із кодом у тексті для `vercel-auth`/
    `vercel-busy`) — тихої відмови нема.
Пароль превʼю (`ctx['secrets']['password']`) модуль НЕ читає: його вкладає в сторінки збірка (ядро).

Токен
  * іде ЛИШЕ в заголовок `Authorization` і ЛИШЕ на `API_BASE`, єдиним місцем — `_req`; ні в перевірку превʼю, ні в
    аргументи/оточення процесів, ні в тексти винятків (тексти Vercel, що його повторили б, вичищаються);
  * запити API не йдуть за редиректами (інакше `urllib` віддав би заголовок на чужий хост): 3xx — це помилка.

Стан задачі НЕ довіряється (`iterations.json` можна склонувати чи поділити). Проєкт зі стану береться лише коли його
імʼя — `pv-<8 цифр>` (те, що створює сам модуль), є непорожній `project_id` і `task` збігається з id ЦІЄЇ задачі
(скопійований із іншої задачі стан — «стану нема»). Навіть тоді ПЕРЕД будь-яким завантаженням проєкт шукається за `id`
(`GET /v9/projects/<project_id>`): деплоїмо в нього лише коли відповідь — 200, `id` збігається з записаним і ТОЧНЕ `name`
дорівнює записаному. Інше імʼя — проєкт «не наш» (підроблений `project_id` на чужий проєкт, чи його перейменували в
панелі): у нього НЕ деплоїмо й нічого не видаляємо, створюється новий `pv-…` з попередженням «проєкт у стані не
збігається — створено новий». Перейменування НЕ підтримується: доказ «остання публікація зі стану належить цьому
проєкту» теж лежить у стані, тож його можна підробити так само, як `project_id`. 404 — проєкт видалено, і лише якщо
записане імʼя теж вільне (`GET /v9/projects/<імʼя>` → 404) створюємо наново під ним, інакше нове імʼя.

Що робить `publish(ctx, build_dir, task)` (`task = {id, title, dir, state}`; `state` — те, що модуль повернув минулого
разу, або `{}`)
  0. збірка читається ЦІЛКОМ І ЛОКАЛЬНО до першого запиту: будь-яке символічне посилання (файл чи тека), не звичайний
     файл, понад `MAX_FILES` файлів, файл понад `MAX_FILE_BYTES`, імʼя не з UTF-8 чи порожня збірка — відмова
     (`module-error`), нічого не завантажено;
  1. проєкт: див. вище; нове імʼя — непрозоре `pv-<8 цифр>` (в адресі ні назви задачі, ні клієнта), перевірене
     `GET /v9/projects/<імʼя>` → 404, інакше (чужий проєкт із таким імʼям) інше імʼя, ≤ 3 спроби;
  2. файли: `POST /v2/files` по разу на вміст (SHA-1), 60 с на файл, ≤ `UPLOAD_TOTAL_S` усього; кожен файл — один повтор
     при збої мережі/5xx (завантаження ідемпотентне за SHA-1);
  3. `POST /v13/deployments` (`target: production`, без збірки: превʼю вже зібране);
  4. опитування `GET /v13/deployments/<id>` кожні `POLL_S` до `READY` (`ERROR`/`CANCELED`/`BLOCKED`/`DELETED` → помилка
     з текстом Vercel, понад `POLL_MAX_S` — `timeout`); до `POLL_TRANSIENT` збоїв мережі/5xx ПОСПІЛЬ терпимо;
  5. адреса: після `READY` alias може запізнитись — ще опитуємо до `ALIAS_MAX_S`, доки `aliasAssigned` не стане правдою
     чи не зʼявиться `*.vercel.app`; `aliasError` зупиняє очікування (його текст — у попередженні). Найкоротший alias на
     `.vercel.app` — продакшн-адреса проєкту; нема — адреса самої публікації + попередження (її Vercel зазвичай
     закриває захистом);
  6. перевірка `GET <адреса>` без жодних облікових даних і БЕЗ переходів: 200 — `verified`; 401/403 чи редирект на
     `vercel.com` — не `verified` + попередження про Deployment Protection; 404/5xx/без відповіді — до `VERIFY_RETRIES`
     повторів (розкатка запізнюється); усе інше — не `verified`, публікація не зупиняється;
  7. прибирання старих публікацій проєкту (тримаємо `KEEP` разом із поточною, ≤ `CLEANUP_MAX_S`) — лише коли `projectId`
     публікації збігається зі `state.project_id` (або проєкт створив САМЕ цей виклик); чужий проєкт не чіпаємо взагалі;
     видаляється лише запис, ПОЗИТИВНО впізнаний як цього проєкту (`projectId` збігається, а коли його нема — збігається
     `name`); будь-який збій — попередження, не помилка;
  8. повертає `{url, verified, warnings, state: {project, project_id, deployment, task}}`; кожне попередження — рядок без
     самотніх сурогатів і ≤ `WARN_MAX` (ядро відмовило б уже вдалу публікацію через один такий знак).
Збій ПІСЛЯ `POST /v13/deployments`, коли проєкт створив САМЕ цей виклик (перша публікація задачі, або проєкт зі стану
було видалено в панелі й створено наново в цьому ж виклику), — best-effort `DELETE /v9/projects/<id>` цього проєкту
(лише `pv-<8 цифр>`; на шляху зі станом, коли проєкт існував, — НІКОЛИ). «Створений цим викликом» — висновок із 404-проби,
а між пробою й `POST` проєкт міг створити хтось інший, тож ПЕРЕД видаленням: `id` починається з `prj_`, у проєкті
(`GET /v6/deployments?projectId=<id>&limit=5`) нема жодної публікації, крім цього виклику, і `GET /v9/projects/<id>`
дає те саме імʼя; інакше проєкт не видаляється, а текст помилки каже чому. Текст помилки завжди каже, видалено проєкт чи ні.
Усі збої `publish` з `RuntimeError`-родини (`_HttpError`, `_NetworkError`, відмови модуля) на виході стають
`ModuleError('module-error')` із текстом ≤ `ERR_MAX` без імені класу (`publish` — тонка обгортка над `_publish`).
Очікування alias після `READY` НЕОБОВʼЯЗКОВЕ: будь-який збій у ньому (мережа, 5xx, 4xx, авторизація, ліміт) лишає
останню відповідь `READY` і веде до адреси публікації з попередженням — готова публікація не стає помилкою.

Режим `cli` (`ctx['settings']['auth'] == 'cli'`, 4b-1): людина вже зайшла в Vercel на цій машині (`vercel login`), токен
не потрібен і НЕ читається. Модуль робить те саме, що ядро в гілці ЛІГИ до 0.8.0: `npx --yes vercel link --yes [--scope S]
--project P` → `deploy --prod --yes [--scope S]` (cwd = тека збірки; 120 і 300 с) → `inspect <адреса>` (120 с) і береться
НАЙКОРОТША з адрес `*.vercel.app` (вивід `deploy` + `inspect`); адресу НЕ вгадуємо. `npx` дає `ctx['find_tool']('npx')` (ядро
знає про nvm/volta/brew, яких нема в PATH застосунку); нема — `no-node`. Підпроцес запускається БЕЗ `env=`: токенів модуль у
нього не кладе (оточення процесу — як у сервера). Імʼя проєкту й скоуп перевіряються регулярками ДО запуску (аргумент не
може стати прапорцем). Перевірка превʼю — `_fetch_page` (GET без облікових даних, без переходів): `task['gated']` (ядро
вклало пароль-гейт у сторінки) — `verified` лише з маркером `authgate` у тілі; без гейта — будь-яка 200.
Коди відмов (ядро складає з них людські тексти; тут їх НЕМА — лише сирий вивід CLI в `ModuleError.full`, хвіст ≤ 4000 знаків
`stderr or stdout`): `vercel-login` (не ввійшли), `vercel-scope` (скоуп/команда недоступні), `vercel-auth` (немає доступу),
`vercel-deploy` (інше, і тайм-аут/ОС-збій запуску), `vercel-no-url` (деплой пройшов, адреси нема), `no-node`. Порядок
класифікації — той самий, що в `_deploy_hint` 0.8.0: вхід → скоуп → доступ → решта.
Прибирання старих публікацій (`_cli_cleanup`): `vercel list <проєкт> --json` (≤ `CLI_LIST_PAGES` сторінок, `--next`),
кандидати — лише `name == проєкт`; поточна (`deploy_url`) лишається завжди, разом із нею `KEEP`; решта — `vercel remove <хост>
--safe --yes` (⛔ ІМЕНІ проєкту в `remove` нема: CLI видалив би весь проєкт). Список не розібрано — не видаляємо нічого. Будь-який
збій — `cleanup_warning` (і в `warnings`), не помилка. `--scope` — лише коли скоуп відомий.

Довіра до стану в режимі `cli` залежить від ДЖЕРЕЛА (`_cli_pick`). Звичайний простір: стан із `iterations.json` (їздить через git)
недовірений — імʼя проєкту береться з нього лише коли воно `pv-<8 цифр>` (інакше новий `pv-…` і попередження), скоуп — ЛИШЕ з
налаштування `team`, ніколи зі стану. ЛІГА: ядро (`serve._publish_legacy_call`) ставить `task['legacy_state'] = True`, бо стан
складено з локальних `tasks.json`/реєстру (`vercel_project`, `vercel_scope`) — тоді приймається будь-яке безпечне імʼя (`dc-…`)
і скоуп зі стану. Звичайний диспетчер цього ключа не ставить ніколи. Збій `vercel link` (код ≠ 0) — відмова з кодом за `_cli_code` ДО
`deploy` (відхилення від 0.8.0: без привʼязки `deploy` пішов би в проєкт з імʼям теки, а прибирання чистило б задуманий проєкт).

Ядро кличе `publish` БЕЗ тайм-ауту, тож кожен запит має свій: 30 с на запит API, 60 с на файл, 20 с на перевірку.

`check(ctx)` у режимі `cli` — `npx vercel whoami` (`{"ok": true, "detail": <імʼя>}`, або `no-node` / `vercel-login`). Холодний
`npx --yes vercel` спершу завантажує CLI, тож маніфест просить для `check` 130 с (`check_timeout_s`; типові 5 с ядра обірвали б його
до вердикту), а `CLI_WHOAMI_S` = 120 с — власна межа `whoami`, щоб чесний `check-timeout` модуля передував тайм-ауту ядра.
`check(ctx)` у режимі `token` — `GET /v2/user` (+ `GET /v2/teams/<team_…>` для `teamId`; для `slug` — читальна проба доступу
`GET /v6/deployments?limit=1` у цій команді); нічого не створює й не кидає на звичайних збоях (немає токена, не
прийнято, мережі нема) — вертає `{"ok": false, "error": <код>, "detail": <причина>}`.
"""
import hashlib
import json
import os
import re
import secrets
import ssl
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = 'https://api.vercel.com'
#: Інтервал опитування публікації й загальна межа очікування `READY`, секунди (тести ставлять малі).
POLL_S = 1.5
POLL_MAX_S = 180
#: Після `READY` alias може запізнитись: скільки ще чекаємо `aliasAssigned` / `*.vercel.app`, секунди.
ALIAS_MAX_S = 30
#: Скільки збоїв мережі/5xx ПОСПІЛЬ терпимо під час опитування; повторів завантаження одного файла.
POLL_TRANSIENT = 3
UPLOAD_RETRIES = 1
#: Скільки публікацій проєкту лишаємо після прибирання (разом із поточною).
KEEP = 3
API_TIMEOUT_S = 30
UPLOAD_TIMEOUT_S = 60
PREVIEW_TIMEOUT_S = 20
#: Загальні межі, секунди: усі завантаження разом, усе прибирання.
UPLOAD_TOTAL_S = 300
CLEANUP_MAX_S = 60
#: Перевірка превʼю: скільки повторів і з яким проміжком, коли сторінка ще «не там» (404/5xx/без відповіді).
VERIFY_RETRIES = 2
VERIFY_RETRY_S = 1.5
#: Межі збірки (до першого запиту): файлів і розмір одного файла.
MAX_FILES = 5000
MAX_FILE_BYTES = 50 << 20
#: Більше цього відповіді API не читаємо (це JSON зі списком, а не файли).
MAX_BODY = 4 << 20
NAME_TRIES = 3
#: Довжина тексту Vercel у помилці й у попередженні (ядро ріже до 300 само; ми — раніше й обачніше).
MSG_MAX = 200
WARN_MAX = 300
ERR_MAX = 300
MAX_WARNINGS = 5
UA = 'deai-canvas-vercel-publish/1.0'
#: Імʼя проєкту, яке створює САМ модуль (і єдине, яке береться зі стану): `pv-<8 цифр>`, ASCII.
OWN_NAME_RE = re.compile(r'pv-[0-9]{8}', re.ASCII)
#: Імʼя хоста з відповіді API (alias, url публікації): мітки через крапку, без пробілів, `/`, `@`, `#`, `\`.
_LABEL = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
HOST_RE = re.compile(rf'(?:{_LABEL}\.)*{_LABEL}', re.ASCII)
#: Токен Vercel — друковний ASCII без пробілів: усе інше зіпсувало б заголовок (і потрапило б у текст помилки).
TOKEN_RE = re.compile(r'[\x21-\x7e]+')
REDIRECTS = (301, 302, 303, 307, 308)


class _CodedError(RuntimeError):
    """Помилка з кодом, коли в `ctx` нема класу ядра (рукописний `ctx`)."""

    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code = code
        self.message = message


class _HttpError(RuntimeError):
    """Інша (не авторизація й не ліміт) відповідь Vercel: `status` — код (404 перевірки імені — не помилка)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class _NetworkError(RuntimeError):
    """Vercel недосяжний: мережа, тайм-аут, обрив."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Нікуди не йти за 3xx: відповідь лишається помилкою `HTTPError` з її `Location`."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    return urllib.request.build_opener(_NoRedirect)


def _error(ctx, code, message):
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    if isinstance(cls, type) and issubclass(cls, Exception):
        return cls(code, message=message)
    return _CodedError(code, message)


def _token(ctx):
    sec = ctx.get('secrets') if isinstance(ctx, dict) else None
    tok = sec.get('token') if isinstance(sec, dict) else None
    return tok.strip() if isinstance(tok, str) else ''


def _need_token(ctx):
    tok = _token(ctx)
    if not tok:
        raise _error(ctx, 'vercel-auth', 'Токен Vercel не задано')
    if not TOKEN_RE.fullmatch(tok):
        raise _error(ctx, 'vercel-auth', 'Токен Vercel має недопустимі символи (очікується один рядок без пробілів)')
    return tok


def _team(ctx):
    """Параметр команди для КОЖНОГО запиту: `team_…` — `teamId`, інакше `slug`; порожньо — без параметра."""
    st = ctx.get('settings') if isinstance(ctx, dict) else None
    team = st.get('team') if isinstance(st, dict) else None
    team = team.strip() if isinstance(team, str) else ''
    if not team:
        return {}
    return {'teamId': team} if team.startswith('team_') else {'slug': team}


def _utf8(text):
    """Рядок, який можна записати в UTF-8: самотній сурогат (з `\\ud800` у JSON Vercel) стає `?`. Ядро відмовило б усю
    вже вдалу публікацію через один такий знак у попередженні."""
    return text.encode('utf-8', 'replace').decode('utf-8')


def _clean(text, token, limit):
    """Рядок для тексту помилки й попередження: без переносів і зайвих пробілів, без токена, без самотніх сурогатів,
    не довше `limit`."""
    text = _utf8(' '.join(str(text).split()))
    if token:
        text = text.replace(token, '***')
    return text[:limit]


def _parse_error(raw, token):
    """`(текст, invalidToken)` із тіла відповіді Vercel: `error.message` (чи рядок `error`, чи `message`); порожній
    текст, якщо тіла нема чи воно не JSON."""
    try:
        data = json.loads(raw.decode('utf-8', 'replace'))
    except ValueError:
        return '', False
    err = data.get('error') if isinstance(data, dict) else None
    invalid = isinstance(err, dict) and err.get('invalidToken') is True
    if isinstance(err, dict):
        msg = err.get('message')
    elif isinstance(err, str):
        msg = err
    else:
        msg = data.get('message') if isinstance(data, dict) else None
    return (_clean(msg, token, MSG_MAX) if isinstance(msg, str) else ''), invalid


def _kind(e):
    """Імʼя КЛАСУ збою для тексту «Vercel недоступний (…)»: лише імʼя, без подробиць (в них могла б бути адреса чи токен)."""
    reason = getattr(e, 'reason', None)
    return type(reason if isinstance(reason, BaseException) else e).__name__


def _transient(e):
    """Збій, що минає сам: мережа чи 5xx. Авторизація, ліміт і 4xx — ні."""
    return isinstance(e, _NetworkError) or (isinstance(e, _HttpError) and e.status >= 500)


def _req(ctx, method, path, *, query=None, body=None, raw=None, headers=None, timeout=API_TIMEOUT_S):
    """Один запит до `API_BASE`: ЄДИНЕ місце, де є `Authorization: Bearer <токен>`; параметр команди — до кожного запиту.
    JSON у `body` (або байти в `raw` із заголовками викликача); результат — розібраний JSON-обʼєкт (`{}` для порожнього).
    401/403 → `vercel-auth`, 429 → `vercel-busy` (обидва з текстом Vercel), інший HTTP → `_HttpError`, мережа →
    `_NetworkError('Vercel недоступний (<клас збою>)')`. Ні в одному тексті винятку токена нема."""
    token = _need_token(ctx)
    params = dict(query or {})
    params.update(_team(ctx))
    url = API_BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
    hdrs = {'Accept': 'application/json', 'User-Agent': UA}
    hdrs.update(headers or {})
    hdrs['Authorization'] = 'Bearer ' + token
    data = None
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        hdrs['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    status, payload = 0, b''
    try:
        try:
            with _opener().open(req, timeout=timeout) as resp:
                status, payload = resp.status, resp.read(MAX_BODY + 1)
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                payload = e.read(MAX_BODY + 1)
            finally:
                e.close()
    except Exception as e:  # noqa: BLE001 — URLError, тайм-аут, обрив, TLS, `http.client.*`: для людини це одне — «недоступний»
        raise _NetworkError(f'Vercel недоступний ({_kind(e)})') from None
    if not 200 <= status < 300:                                    # 3xx — теж помилка: за редиректами не йдемо
        msg, invalid = _parse_error(payload, token)
        if status in (401, 403):
            if status == 401 or invalid:
                text = 'Vercel не прийняв токен' + (f': {msg}' if msg else f' (HTTP {status})')
            else:
                text = f'Vercel відмовив у доступі (HTTP {status})' + (f': {msg}' if msg else '')
            raise _error(ctx, 'vercel-auth', text)
        if status == 429:
            raise _error(ctx, 'vercel-busy', msg or 'Vercel: забагато запитів, спробуйте трохи згодом')
        raise _HttpError(status, msg or f'Vercel відповів HTTP {status}')
    if len(payload) > MAX_BODY:
        raise RuntimeError('Vercel: відповідь завелика')
    if not payload.strip():
        return {}
    try:
        out = json.loads(payload.decode('utf-8'))
    except ValueError:
        raise RuntimeError('Vercel повернув відповідь не у форматі JSON') from None
    if not isinstance(out, dict):
        raise RuntimeError('Vercel повернув несподівану відповідь')
    return out


# ------------------------------------------------------------------------------------------------ збірка

def _mb(n):
    return f'{n / (1 << 20):.1f}'


def _scan(build_dir):
    """`[(відносний шлях через '/', шлях на диску, sha1, розмір)]` за відсортованими шляхами. Символічне посилання (файл чи
    тека, навіть биті), не звичайний файл, понад `MAX_FILES` файлів чи файл понад `MAX_FILE_BYTES` — `RuntimeError`: так
    само читається все, ДО першого запиту."""
    if os.path.islink(build_dir):
        raise RuntimeError('Збірка є символічним посиланням — публікацію зупинено')

    def unreadable(_e):
        raise RuntimeError('Не вдалося прочитати теку збірки — публікацію зупинено')

    out = []
    for dirpath, dirnames, filenames in os.walk(build_dir, followlinks=False, onerror=unreadable):
        dirnames.sort()
        for name in sorted(dirnames) + sorted(filenames):
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, build_dir).replace(os.sep, '/')
            try:
                rel.encode('utf-8')
            except UnicodeEncodeError:                              # імʼя не з UTF-8 (сурогати): у JSON воно б зіпсувалось
                raise RuntimeError('Імʼя файла у збірці не в UTF-8 — публікацію зупинено') from None
            try:
                st = os.lstat(p)
            except OSError:
                raise RuntimeError(f'Не вдалося прочитати {rel} — публікацію зупинено') from None
            if stat.S_ISLNK(st.st_mode):
                raise RuntimeError(f'У збірці є символічне посилання ({rel}) — публікацію зупинено')
            if name in filenames:
                if not stat.S_ISREG(st.st_mode):
                    raise RuntimeError(f'У збірці є не звичайний файл ({rel}) — публікацію зупинено')
                if len(out) >= MAX_FILES:
                    raise RuntimeError(f'У збірці понад {MAX_FILES} файлів — публікацію зупинено')
                if st.st_size > MAX_FILE_BYTES:
                    raise RuntimeError(f'Файл {rel} завеликий ({_mb(st.st_size)} МБ, межа {_mb(MAX_FILE_BYTES)} МБ) — '
                                       'публікацію зупинено')
                digest = hashlib.sha1(usedforsecurity=False)
                size = 0
                try:
                    with open(p, 'rb') as f:
                        for chunk in iter(lambda: f.read(1 << 20), b''):
                            digest.update(chunk)
                            size += len(chunk)
                except OSError:
                    raise RuntimeError(f'Не вдалося прочитати {rel} — публікацію зупинено') from None
                out.append((rel, p, digest.hexdigest(), size))
    out.sort(key=lambda t: t[0])
    if not out:
        raise RuntimeError('Збірка порожня — нічого публікувати')
    return out


def _upload(ctx, path, sha, size):
    """`POST /v2/files`: вміст файла за SHA-1; один повтор при збої мережі/5xx (за SHA-1 завантаження ідемпотентне).
    Читаємо знову й звіряємо з тим, що порахували: файл, що змінився між підрахунком і завантаженням, не відправляємо
    під чужим хешем."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        raise RuntimeError('Не вдалося прочитати файл збірки — публікацію зупинено') from None
    if len(data) != size or hashlib.sha1(data, usedforsecurity=False).hexdigest() != sha:
        raise RuntimeError('Файл збірки змінився під час публікації — спробуйте ще раз')
    for attempt in range(UPLOAD_RETRIES + 1):
        try:
            _req(ctx, 'POST', '/v2/files', raw=data, timeout=UPLOAD_TIMEOUT_S,
                 headers={'Content-Type': 'application/octet-stream', 'x-vercel-digest': sha,
                          'Content-Length': str(len(data))})
            return
        except (_NetworkError, _HttpError) as e:
            if attempt >= UPLOAD_RETRIES or not _transient(e):
                raise


# -------------------------------------------------------------------------------------------- проєкт, стан

def _state_str(state, key):
    v = state.get(key) if isinstance(state, dict) else None
    return v if isinstance(v, str) and v else None


def _own_state(state, task_id):
    """`(імʼя, project_id)` зі стану — лише коли це справді те, що створює модуль для ЦІЄЇ задачі: `pv-<8 цифр>`,
    непорожній id і `task` = id задачі. Усе інше (чужа назва зі склонованого `iterations.json`, стан без id, стан
    іншої задачі…) — «стану нема»."""
    name, pid, tid = _state_str(state, 'project'), _state_str(state, 'project_id'), _state_str(state, 'task')
    if name and OWN_NAME_RE.fullmatch(name) and pid and len(pid) <= 200 and tid == task_id:      # `tid` — не порожній рядок чи None
        return name, pid
    return None, None


def _pick_project(ctx, state, task_id):
    """`(імʼя, projectId | None, створено_цим_викликом, попередження | None)`. Стан не довіряється. Проєкт зі стану
    шукається за `id` (`GET /v9/projects/<project_id>`) ДО будь-якого завантаження: 200 — деплоїмо в нього, лише коли
    `id` збігається з записаним і ТОЧНЕ `name` дорівнює записаному (інше імʼя — чужий проєкт чи перейменований, тож
    «не наш»: нове `pv-<8 цифр>` із попередженням, у чужий — жодного `POST`/`DELETE`); 404 — видалено: наново під
    записаним імʼям, лише якщо й воно вільне (404). Усе інше — нове `pv-<8 цифр>`, перевірене `GET /v9/projects/<імʼя>`
    → 404 (200 — чужий проєкт)."""
    name, pid = _own_state(state, task_id)
    note = None
    if name:
        got = None
        try:
            got = _req(ctx, 'GET', '/v9/projects/' + urllib.parse.quote(pid, safe=''))
        except _HttpError as e:
            if e.status != 404:
                raise
        if got is None:                                            # id такого проєкту нема: видалено в панелі
            try:
                _req(ctx, 'GET', '/v9/projects/' + urllib.parse.quote(name, safe=''))
            except _HttpError as e:
                if e.status != 404:
                    raise
                return name, None, True, None                      # імʼя вільне: створюємо наново під ним
        elif got.get('id') == pid and got.get('name') == name:
            return name, pid, False, None
        note = ('Проєкт у стані не збігається з проєктом у Vercel — створено новий проєкт; '
                'адреса може відрізнятись від попередньої.')
    for _ in range(NAME_TRIES):
        name = f'pv-{secrets.randbelow(10 ** 8):08d}'
        try:
            _req(ctx, 'GET', '/v9/projects/' + urllib.parse.quote(name, safe=''))
        except _HttpError as e:
            if e.status == 404:
                return name, None, True, note
            raise
    raise RuntimeError(f'Не вдалося підібрати вільне імʼя проєкту у Vercel ({NAME_TRIES} спроби)')


# ----------------------------------------------------------------------------------------- очікування, адреса

def _get_dep(ctx, dep_id, streak):
    """`GET /v13/deployments/<id>`. Збій мережі/5xx терпимо — до `POLL_TRANSIENT` ПОСПІЛЬ (`streak[0]`; успіх
    скидає): тоді `None`. Решта (4xx, авторизація, ліміт) і перевищення — виняток."""
    try:
        d = _req(ctx, 'GET', '/v13/deployments/' + urllib.parse.quote(dep_id, safe=''))
    except (_NetworkError, _HttpError) as e:
        if not _transient(e):
            raise
        streak[0] += 1
        if streak[0] > POLL_TRANSIENT:
            raise
        return None
    streak[0] = 0
    return d


def _terminal_text(ctx, st, d):
    why = d.get('errorMessage') if isinstance(d.get('errorMessage'), str) else ''
    why = _clean(why or (d.get('errorCode') if isinstance(d.get('errorCode'), str) else ''), _token(ctx), MSG_MAX)
    if st == 'BLOCKED':
        return 'Vercel заблокував публікацію (BLOCKED)' + (f': {why}' if why else '')
    if st == 'DELETED':
        return 'Публікацію видалено у Vercel до завершення (DELETED)' + (f': {why}' if why else '')
    return 'Vercel: ' + (why or f'публікація завершилась станом {st}')


def _wait_ready(ctx, dep_id, streak):
    """Опитування до `READY`: повертає останню відповідь `GET /v13/deployments/<id>`."""
    deadline = time.monotonic() + POLL_MAX_S
    while True:
        d = _get_dep(ctx, dep_id, streak)
        if d is not None:
            st = d.get('readyState') if isinstance(d.get('readyState'), str) else d.get('status')
            if st == 'READY':
                return d
            if st in ('ERROR', 'CANCELED', 'BLOCKED', 'DELETED'):
                raise RuntimeError(_terminal_text(ctx, st, d))
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Vercel не завершив публікацію за {POLL_MAX_S} с (timeout)')
        time.sleep(POLL_S)


def _host(value):
    """Імʼя хоста з відповіді API (`https://` відкидаємо) або `None`: без шляху, облікових даних, пробілів."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v.startswith('https://'):
        v = v[len('https://'):]
    return v if len(v) <= 253 and HOST_RE.fullmatch(v) else None


def _vercel_app_aliases(dep):
    """Усі `*.vercel.app` серед `alias` публікації (імена хостів, що пройшли `HOST_RE`)."""
    aliases = dep.get('alias')
    out = []
    for a in (aliases if isinstance(aliases, list) else []):
        h = _host(a)
        if h and h.endswith('.vercel.app'):
            out.append(h)
    return out


def _alias_error(ctx, dep):
    """Текст `aliasError` (обʼєкт із `message` чи рядок) або `None`."""
    err = dep.get('aliasError')
    msg = err.get('message') if isinstance(err, dict) else err
    if isinstance(msg, str) and msg.strip():
        return _clean(msg, _token(ctx), 120)
    return None


def _wait_alias(ctx, dep_id, ready, streak):
    """Після `READY` alias може запізнитись. Опитуємо далі кожні `POLL_S` до `ALIAS_MAX_S`, доки: зʼявився `*.vercel.app`,
    або `aliasAssigned` став правдою (призначено, але `.vercel.app` нема — далі чекати нема чого), або Vercel
    повідомив `aliasError`. Повертає `(остання відповідь, текст aliasError | None)`. НІКОЛИ не кидає: це очікування
    необовʼязкове, а публікація вже `READY` (її збій у цьому місці — не збій публікації)."""
    deadline = time.monotonic() + ALIAS_MAX_S
    try:
        while True:
            if _vercel_app_aliases(ready):
                return ready, None
            err = _alias_error(ctx, ready)
            if err:
                return ready, err
            if ready.get('aliasAssigned'):
                return ready, None
            if time.monotonic() >= deadline:
                return ready, None
            time.sleep(POLL_S)
            nxt = _get_dep(ctx, dep_id, streak)
            if nxt is not None and nxt.get('readyState') == 'READY':
                ready = nxt
    except Exception:  # noqa: BLE001 — очікування alias НЕОБОВʼЯЗКОВЕ: публікація вже READY, тож що б не сталось (мережа,
        return ready, None                    # 5xx, 4xx, авторизація, ліміт), лишаємо останню READY і падаємо на адресу публікації


def _main_url(ready, created):
    """`(адреса, є_постійна_адреса)`: найкоротший `alias` на `.vercel.app`; нема — адреса самої публікації."""
    cands = _vercel_app_aliases(ready)
    if cands:
        return 'https://' + min(cands, key=lambda h: (len(h), h)), True
    h = _host(ready.get('url')) or _host(created.get('url'))
    if not h:
        raise RuntimeError('Vercel не повернув адресу публікації')
    return 'https://' + h, False


# ------------------------------------------------------------------------------------------------ перевірка

def _fetch_preview(url):
    """`(статус | None, Location)`: GET без жодних облікових даних і без переходів за редиректами, 20 с.
    Лише `http(s)`; будь-який збій — `(None, '')`."""
    try:
        if urllib.parse.urlsplit(url).scheme not in ('http', 'https'):
            return None, ''
        req = urllib.request.Request(url, method='GET', headers={'User-Agent': UA, 'Accept': 'text/html,*/*'})
        with _opener().open(req, timeout=PREVIEW_TIMEOUT_S) as resp:
            return resp.status, ''
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.headers.get('Location') or ''
        finally:
            e.close()
    except Exception:  # noqa: BLE001 — перевірка лише інформує: що б не сталось, публікацію вона не зупиняє
        return None, ''


def _is_vercel_login(location):
    try:
        host = (urllib.parse.urlsplit(location).hostname or '').lower()
    except ValueError:
        return False
    return host == 'vercel.com' or host.endswith('.vercel.com')


def _not_there_yet(status):
    """Сторінка ще не розкотилась: без відповіді, 404 чи 5xx. Захист, редиректи й 200 — остаточні."""
    return status is None or status == 404 or status >= 500


#: Попередження про Deployment Protection — спільне для обох режимів (`_verify` і `_publish_cli`); `{project}` — імʼя проєкту.
_PROTECTION_TEXT = ('Превʼю закрите захистом Vercel (Deployment Protection): без входу в акаунт Vercel воно не відкриється. '
                    'Вимкнути: Vercel → проєкт {project} → Settings → Deployment Protection → Vercel Authentication → Disabled.')


def _verify(url, project):
    """`(verified, попередження | None)` за відповіддю сторінки превʼю; «ще не там» — до `VERIFY_RETRIES` повторів."""
    status, location = _fetch_preview(url)
    retries = 0
    while _not_there_yet(status) and retries < VERIFY_RETRIES:
        retries += 1
        time.sleep(VERIFY_RETRY_S)
        status, location = _fetch_preview(url)
    if status == 200:
        return True, None
    if status in (401, 403) or (status in REDIRECTS and _is_vercel_login(location)):
        return False, _PROTECTION_TEXT.format(project=project)
    if status is None:
        return False, 'Не вдалося перевірити, що превʼю відкривається без входу (адреса не відповіла). Відкрийте її в браузері.'
    return False, f'Не вдалося підтвердити, що превʼю відкривається без входу (відповідь HTTP {status}). Відкрийте адресу в браузері.'


# ---------------------------------------------------------------------------------------------- прибирання

def _ours(item, project_id, project):
    """ПОЗИТИВНО впізнати запис списку як публікацію цього проєкту: `projectId` збігається, а коли його нема —
    збігається `name`. Усе інше (чужий `projectId`, нема ні того, ні того) — не наше, не чіпаємо."""
    pid = item.get('projectId')
    if pid is not None:
        return pid == project_id
    return item.get('name') == project


def _cleanup(ctx, project_id, project, current_id):
    """Прибирання старих публікацій проєкту: тримаємо `KEEP` разом із поточною, не довше `CLEANUP_MAX_S`. Повертає
    попередження або `None`; будь-який збій — попередження (публікація вже відбулась). Чіпає лише записи, ПОЗИТИВНО
    впізнані як цього проєкту (`_ours`), з датою й ідентифікатором."""
    deadline = time.monotonic() + CLEANUP_MAX_S
    try:
        data = _req(ctx, 'GET', '/v6/deployments',
                    query={'projectId': project_id, 'target': 'production', 'limit': 20})
        items = data.get('deployments')
        if not isinstance(items, list):
            raise RuntimeError('unexpected list')
        rest = []
        for it in items:
            if not isinstance(it, dict):
                continue
            uid = it.get('uid') if isinstance(it.get('uid'), str) and it.get('uid') else it.get('id')
            created = it.get('created')
            if not isinstance(uid, str) or not uid or uid == current_id:
                continue
            if not _ours(it, project_id, project):
                continue
            if isinstance(created, bool) or not isinstance(created, (int, float)) or created - created != 0:
                continue                                              # не число, bool, NaN чи ±inf (`x - x != 0`)
            rest.append((created, uid))
        rest.sort(reverse=True)
        doomed = rest[max(KEEP - 1, 0):]                              # поточна лишається завжди, тож «інших» KEEP − 1
        failed = 0
        for i, (_created, uid) in enumerate(doomed):
            if time.monotonic() >= deadline:
                return f'Прибирання старих публікацій у Vercel перервано за часом ({CLEANUP_MAX_S} с) — частина лишилась.'
            try:
                _req(ctx, 'DELETE', '/v13/deployments/' + urllib.parse.quote(uid, safe=''))
            except Exception as e:  # noqa: BLE001 — один збій не зупиняє решти, але авторизація й ліміт — зупиняють
                failed += 1
                if getattr(e, 'code', None) in ('vercel-auth', 'vercel-busy'):
                    failed += len(doomed) - i - 1                     # решту навіть не пробували
                    break
        if failed:
            return f'Не вдалося видалити {failed} із {len(doomed)} старих публікацій у Vercel — вони лишились.'
        return None
    except Exception:  # noqa: BLE001 — список не отримано чи розібрано: це попередження, не помилка
        return 'Не вдалося прибрати старі публікації у Vercel — вони лишились.'


# ------------------------------------------------------------------------------------------------ сироти

def _drop_created_project(ctx, project, project_id, dep_id):
    """Best-effort `DELETE /v9/projects/<id>` проєкту, який (як ми вважаємо) створив ЦЕЙ виклик, коли публікація в ньому не
    вдалась. «Створив цей виклик» — висновок із 404-проби імені, а між пробою й `POST` проєкт міг створити хтось інший
    (особливо на шляху «видалено в панелі → створено наново», де імʼя спільне для всіх клонів стану). Тому ПЕРЕД
    видаленням: `id` починається з `prj_`; у проєкті (`GET /v6/deployments?projectId=<id>&limit=5`) нема жодної публікації,
    крім цього виклику (порожній список — гаразд); `GET /v9/projects/<id>` дає те саме імʼя. Інакше — НЕ видаляємо й кажемо
    чому. Повертає речення для тексту помилки."""
    skip = f'Проєкт {project} не видалено: '
    if not project_id.startswith('prj_'):
        return skip + 'не вдалося перевірити, що він створений цим викликом — перевірте його у Vercel.'
    try:
        lst = _req(ctx, 'GET', '/v6/deployments', query={'projectId': project_id, 'limit': 5})
        items = lst.get('deployments')
        if not isinstance(items, list):
            raise RuntimeError('unexpected list')
        for it in items:
            uid = (it.get('uid') or it.get('id')) if isinstance(it, dict) else None
            if not isinstance(uid, str) or not uid:
                raise RuntimeError('unreadable list item')               # запис, якого не прочитати, — не «наш»: не видаляємо
            if uid != dep_id:
                return skip + 'у ньому є інші публікації — перевірте його у Vercel.'
        got = _req(ctx, 'GET', '/v9/projects/' + urllib.parse.quote(project_id, safe=''))
        if got.get('name') != project:
            return skip + 'під цим ідентифікатором у Vercel інший проєкт.'
    except Exception:  # noqa: BLE001 — не вдалось перевірити: краще лишити проєкт, ніж видалити чужий
        return skip + 'не вдалося перевірити, що в ньому нема чужих публікацій — перевірте його у Vercel.'
    try:
        _req(ctx, 'DELETE', '/v9/projects/' + urllib.parse.quote(project_id, safe=''))
        return f'Створений проєкт {project} видалено.'
    except Exception:  # noqa: BLE001 — найкращі зусилля: причину помилки публікації це не змінює
        return f'Не вдалося видалити створений проєкт {project} — видаліть його у Vercel вручну.'


def _with_note(ctx, e, note):
    """Той самий збій з приміткою в кінці. Код збережено; безкодовий збій стає `module-error` ядра (а не `RuntimeError`:
    ядро додало б до тексту `RuntimeError: ` і відрізало б примітку на 300 знаках). Основний текст стискається так,
    щоб примітка вмістилась у `ERR_MAX` цілою, і завершується крапкою перед нею («… станом ERROR. Створений проєкт … видалено.»)."""
    msg = getattr(e, 'message', None)
    base = msg if isinstance(msg, str) else str(e)
    base = _clean(base, _token(ctx), max(ERR_MAX - len(note) - 2, 0))     # 2 — крапка й пробіл перед приміткою
    if base and base[-1] not in '.!?…':
        base += '.'
    code = getattr(e, 'code', None)
    return _error(ctx, code if isinstance(code, str) else 'module-error', f'{base} {note}' if base else note)


def _module_error(ctx, e):
    """Звичайний збій `publish` (HTTP, мережа, збірка, очікування…) → `ModuleError('module-error')` ядра з чистим текстом
    (≤ `ERR_MAX`, без токена й без імені класу). Збій із кодом (`vercel-auth`, `vercel-busy`, помилка ядра з приміткою)
    чи без класу помилки в `ctx` (рукописний `ctx`) лишається як є."""
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    if not (isinstance(cls, type) and issubclass(cls, Exception)):
        return e
    if isinstance(e, (_CodedError, cls)):
        return e
    msg = getattr(e, 'message', None)
    return cls('module-error', message=_clean(msg if isinstance(msg, str) else str(e), _token(ctx), ERR_MAX))


# ------------------------------------------------------------------------------------- режим cli (системний Vercel CLI)

#: `whoami` — 120 с: холодний `npx --yes vercel` спершу завантажує сам CLI.
CLI_LINK_S, CLI_DEPLOY_S, CLI_INSPECT_S, CLI_WHOAMI_S = 120, 300, 120, 120
#: Прибирання: `vercel list` (до `CLI_LIST_PAGES` сторінок) і `vercel remove` — по 60 с на виклик, усе разом у `CLEANUP_MAX_S`.
CLI_LIST_S, CLI_REMOVE_S, CLI_LIST_PAGES = 60, 60, 5
#: Скільки знаків хвоста виводу CLI лишається в `ModuleError.full` (ядро/адаптер розпізнає причину за хвостом).
CLI_RAW_MAX = 4000
#: Імʼя проєкту й скоуп ідуть у argv: перший знак — літера/цифра, щоб значення не стало прапорцем (`--yes`).
CLI_PROJECT_RE = re.compile(r'[a-z0-9][a-z0-9._-]{0,99}', re.ASCII)
CLI_SCOPE_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', re.ASCII)
_CLI_URL_RE = re.compile(r'https://[a-z0-9.-]+\.vercel\.app')
#: Причина «на адресі не наш макет»: рядок `_check_published` ядра 0.8.0.
NO_GATE_REASON = 'на URL відповідає не наш макет (немає гейта)'


def _auth(ctx):
    """Режим входу: `'cli'` лише коли налаштування `auth` так і каже; усе інше (нема, сміття) — `'token'`."""
    st = ctx.get('settings') if isinstance(ctx, dict) else None
    return 'cli' if isinstance(st, dict) and st.get('auth') == 'cli' else 'token'


def _cli_npx(ctx):
    find = ctx.get('find_tool') if isinstance(ctx, dict) else None
    p = find('npx') if callable(find) else None
    if not (isinstance(p, str) and p):
        raise _error(ctx, 'no-node', 'Не знайдено npx (Node.js): режим «Системний Vercel CLI» запускає `npx vercel`.')
    return p


def _vc(npx, args, cwd, timeout):
    """`npx --yes vercel <args>` у `cwd`. Оточення — те, що в процесу: БЕЗ `env=` (токенів модуль у підпроцес не кладе).
    Вивід читається як UTF-8 із заміною (`text=True` сам бере кодування локалі — на Windows це не UTF-8, і `UnicodeDecodeError`
    вилетів би з модуля поза `ModuleError`)."""
    return subprocess.run([npx, '--yes', 'vercel', *args], cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


def _cli_urls(stdout, stderr):
    """Справжні адреси `*.vercel.app` з виводу CLI (без дублів, порядок збережено).
    ⚠️ Адресу НЕ вгадуємо: раніше стояло `https://<проєкт>.vercel.app` — і `dc-<задача>` у зоні vercel.app виявилось
    зайнятим ЧУЖИМ проєктом, тож дизайнеру видавалось посилання на сторонній сайт (30.07.2026). Імʼя проєкту в акаунті і
    хост у vercel.app — різні простори імен."""
    seen, out = set(), []
    for u in _CLI_URL_RE.findall((stdout or '') + '\n' + (stderr or '')):
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _cli_code(raw):
    """Код відмови `deploy` за виводом CLI. Порядок і шаблони — `_deploy_hint` ядра 0.8.0: вхід → скоуп → доступ → решта.
    ⛔ Скоуп перевіряється ПЕРЕД загальним «немає доступу»: тексти перетинаються, а причина тут конкретніша.
    Не впізнали патерн — `vercel-deploy` (причину не вигадуємо: сирий текст іде в `ModuleError.full`)."""
    e = (raw or '').lower()
    if any(k in e for k in ('not authenticated', 'credentials', 'please log in', 'vercel login', 'no existing credentials')):
        return 'vercel-login'
    if any(k in e for k in ('--scope', 'scope not found', 'no such team', 'not a member of',
                            "don't have access to the team", 'team not found')):
        return 'vercel-scope'
    if any(k in e for k in ('forbidden', 'not authorized', 'access denied', 'do not have permission')):
        return 'vercel-auth'
    return 'vercel-deploy'


def _cli_alias(npx, dep_url, cwd, extra=()):
    """Стабільна публічна адреса: НАЙКОРОТША з адрес виводу `deploy` і `vercel inspect` (див. `_stable_alias` 0.8.0).
    Перевірено на живому деплої: короткий `<проєкт>.vercel.app` віддає макет (200), а довгий, з іменем акаунта, — 302 на SSO
    команди; `dep_url` виключати НЕ можна: часто він і є цим коротким. Збій `inspect` — не помилка (лишаються адреси `deploy`).
    Вертає `(адреса, усі відомі адреси цієї публікації)`: другий елемент — для прибирання (поточну публікацію виключають за
    УСІМА її адресами: `deploy` міг надрукувати короткий alias, а в `vercel list` вона стоїть під довгим хостом)."""
    cands = list(extra) + [dep_url]
    try:
        r = _vc(npx, ['inspect', dep_url], cwd, CLI_INSPECT_S)
        cands += _cli_urls(r.stdout, r.stderr)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return min(cands, key=len), cands


def _ssl_ctx():
    """certifi, якщо він є (python.org на macOS не бачить системних сертифікатів), інакше типовий контекст."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch_page(url):
    """`(статус | None, Location, тіло ≤ 60000 знаків)`: GET без жодних облікових даних і без переходів за редиректами, 20 с.
    Збій звʼязку — `(None, '', <текст винятку ≤ 200>)`: третій елемент тоді — ПРИЧИНА, а не тіло (як `str(e)[:200]` у
    `_check_published` 0.8.0: `CERTIFICATE_VERIFY_FAILED`, DNS…); непідтримана схема — `(None, '', '')`.
    Шов тестів, як `_fetch_preview` (той тіла не читає)."""
    try:
        if urllib.parse.urlsplit(url).scheme not in ('http', 'https'):
            return None, '', ''
        op = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_ssl_ctx()))
        req = urllib.request.Request(url, method='GET', headers={'User-Agent': UA, 'Accept': 'text/html,*/*'})
        with op.open(req, timeout=PREVIEW_TIMEOUT_S) as resp:
            return resp.status, '', resp.read(60000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.headers.get('Location') or '', ''
        finally:
            e.close()
    except Exception as e:  # noqa: BLE001 — перевірка лише інформує: що б не сталось, публікацію вона не зупиняє
        return None, '', _utf8(' '.join(str(e).split()))[:200]


def _cli_verify(url, gated):
    """`None` — підтверджено; інакше `{'reason': …}`. З гейтом (`task['gated']`) — лише маркер `authgate` у тілі (як ЛІГА
    0.8.0: чужий сайт на тій самій адресі не пройде); без гейта — будь-яка 200. Захист Vercel — `vercel_protection`."""
    status, location, body = _fetch_page(url)
    if isinstance(status, int) and 200 <= status < 300:                 # 0.8.0 читало тіло за будь-якого успішного відкриття
        return None if (not gated or 'authgate' in body) else {'reason': NO_GATE_REASON}
    if status in REDIRECTS and 'vercel.com/sso' in location:
        return {'reason': 'vercel_protection'}
    if status is None:                                                  # третій елемент — текст винятку (причина недосяжності)
        return {'reason': body.strip() if isinstance(body, str) and body.strip() else 'адреса не відповіла'}
    return {'reason': f'HTTP {status}'}


def _cli_link_scope(build_dir):
    """`orgId` із `<збірка>/.vercel/project.json`, який записав `vercel link` (див. `_remember_vercel_scope` 0.8.0): без
    нього наступна публікація з ЧУЖОГО акаунта створила б ДРУГИЙ проєкт з тим самим імʼям. Нема файла чи поля — `None`."""
    try:
        with open(os.path.join(build_dir, '.vercel', 'project.json'), encoding='utf-8') as f:
            org = (json.load(f) or {}).get('orgId')
    except (OSError, ValueError, AttributeError):
        return None
    return org if isinstance(org, str) and CLI_SCOPE_RE.fullmatch(org) else None


def _cli_pick(ctx, state, task_id, legacy=False):
    """`(проєкт, скоуп | None, попередження | None)`. Стан береться лише для ЦІЄЇ задачі (`state.task`): склонований стан —
    «стану нема». Нове імʼя — `pv-<8 цифр>`.
    ⛔ Довіра до стану залежить від ДЖЕРЕЛА (`legacy` = `task['legacy_state'] is True`; ставить лише адаптер ЛІГИ ядра):
      * звичайний простір (`legacy=False`) — стан із `iterations.json` (`publish_remote.state`), а той їздить через git, тож
        недовірений. Імʼя береться зі стану лише коли воно `pv-<8 цифр>` (те, що створює сам модуль); інше (`dc-…`, імʼя
        чужого проєкту людини) — новий `pv-…` і ПОПЕРЕДЖЕННЯ (як у режимі `token`): інакше склонований стан змусив би
        `vercel link --yes` привʼязати чужий проєкт, а `_cli_cleanup` — видалити його старі публікації. Скоуп — ЛИШЕ з
        налаштування `team` (чужий скоуп зі стану на машині людини не мусить стати `--scope`);
      * ЛІГА (`legacy=True`) — стан складає ядро з локальних `tasks.json`/реєстру (`vercel_project`, `vercel_scope`): імʼя
        приймається будь-яке безпечне (`dc-…`), скоуп — зі стану, інакше з `team`.
    Небезпечне значення, що лишилось, — відмова ДО будь-якого запуску."""
    st = state if isinstance(state, dict) else {}
    mine = st.get('task') == task_id
    project = st.get('project') if mine and st.get('project') is not None else None
    note = None
    if project is not None and not legacy and not (isinstance(project, str) and OWN_NAME_RE.fullmatch(project)):
        project = None
        note = ('Імʼя проєкту в стані задачі недійсне — створено новий проєкт; адреса може відрізнятись від попередньої.')
    if project is None:
        project = 'pv-' + ''.join(secrets.choice('0123456789') for _ in range(8))
    settings = ctx.get('settings') if isinstance(ctx, dict) else None
    team = settings.get('team') if isinstance(settings, dict) else None
    scope = (st.get('scope') if mine and legacy else None) or (team.strip() if isinstance(team, str) else '') or None
    if not isinstance(project, str) or not CLI_PROJECT_RE.fullmatch(project):
        raise RuntimeError('Імʼя проєкту Vercel для цієї задачі недійсне — публікацію не запущено')
    if scope is not None and (not isinstance(scope, str) or not CLI_SCOPE_RE.fullmatch(scope)):
        raise RuntimeError('Команда Vercel (scope) недійсна — публікацію не запущено')
    return project, scope, note


def _cli_cleanup(npx, project, scope, current_urls, cwd):
    """Прибрати старі публікації проєкту `project`, лишивши `KEEP` разом із поточною (`current_urls` — УСІ адреси поточної
    публікації: вивід `deploy`, вивід `inspect`, обрана адреса).
    Вертає `None` або текст попередження; НІКОЛИ не кидає (збій прибирання не робить вдалу публікацію помилкою).
    ⛔ `vercel remove` отримує ЛИШЕ адреси публікацій (хост `….vercel.app`): з імʼям проєкту CLI видаляє ВЕСЬ проєкт.
    `--safe` — CLI сам пропускає публікації з активним alias. Чіпаємо лише записи з `name == project` (спільний акаунт:
    чужі проєкти в списку не наші). Не вдалось розібрати список (код ≠ 0, не JSON, незнайома форма, запис без адреси чи
    `createdAt`) — НЕ видаляємо нічого: без повного розуміння списку не знаємо, що є «старе». Поточна публікація лишається
    завжди (список міг відстати чи хтось опублікував паралельно). Порівнюємо ХОСТИ: список дає голий хост, `deploy_url` —
    `https://хост`; поточна виключається за ВСІМА своїми адресами. Видаляється лише хост, що закінчується на `.vercel.app`:
    однозначна назва без домену чи чужий домен у `remove` могли б означати ПРОЄКТ — такий запис = «незнайома форма», нічого
    не видаляємо. У `KEEP` рахуються ВСІ публікації проєкту незалежно від стану й цілі (ERROR, CANCELED, превʼю): так простіше
    й обережніше (свідомо). Межа часу — `CLEANUP_MAX_S` на все, жорстка: таймаут кожного виклику стискається до залишку."""
    deadline = time.monotonic() + CLEANUP_MAX_S
    sc = ['--scope', scope] if scope else []
    curs = {h for h in (_host(u) for u in current_urls) if h is not None}
    if not curs:
        return 'Старі публікації не прибрано: не вдалося розібрати адресу поточної публікації.'
    items, nxt = {}, None                                           # хост → `createdAt` (повтор на сусідній сторінці — той самий запис)
    for _ in range(CLI_LIST_PAGES):
        now = time.monotonic()
        if now >= deadline:
            return 'Старі публікації не прибрано: вичерпано ліміт часу на читання списку.'
        try:
            r = _vc(npx, ['list', project, '--json', *sc, *(['--next', str(nxt)] if nxt else [])], cwd,
                    min(CLI_LIST_S, max(1, deadline - now)))
            data = json.loads(r.stdout) if r.returncode == 0 else None
        except (OSError, ValueError, subprocess.SubprocessError):
            data = None
        deps = data.get('deployments') if isinstance(data, dict) else None
        if not isinstance(deps, list):
            return 'Старі публікації не прибрано: Vercel CLI не віддав список публікацій.'
        for d in deps:
            if not isinstance(d, dict) or d.get('name') != project:
                continue
            host, created = _host(d.get('url')), d.get('createdAt')
            if (host is None or host == project or not host.endswith('.vercel.app')
                    or isinstance(created, bool) or not isinstance(created, (int, float))):
                return 'Старі публікації не прибрано: список публікацій має незнайому форму.'
            items[host] = created
        pg = data.get('pagination') if isinstance(data.get('pagination'), dict) else {}
        nxt = pg.get('next')
        if isinstance(nxt, bool) or not isinstance(nxt, int) or nxt <= 0:
            break
    old = [h for _t, h in sorted(((t, h) for h, t in items.items()), reverse=True) if h not in curs]
    doomed = old[KEEP - 1:]                                         # поточна + `KEEP - 1` найновіших решти
    failed, timed_out = 0, False
    for h in doomed:
        now = time.monotonic()
        if now >= deadline:
            failed, timed_out = failed + 1, True
            continue
        try:
            r = _vc(npx, ['remove', h, '--safe', '--yes', *sc], cwd, min(CLI_REMOVE_S, max(1, deadline - now)))
            failed += r.returncode != 0
        except (OSError, ValueError, subprocess.SubprocessError):
            failed += 1
    if not failed:
        return None
    return (f'Старі публікації прибрано не всі: не вдалося {failed} з {len(doomed)}'
            + (' (вичерпано ліміт часу).' if timed_out else '.'))


def _publish_cli(ctx, build_dir, task):
    """Публікація через системний Vercel CLI; див. докстрінг модуля. Прибирання старих публікацій — `_cli_cleanup`."""
    if not isinstance(build_dir, str) or not os.path.isdir(build_dir):
        raise RuntimeError('Збірка превʼю не є текою')
    task = task if isinstance(task, dict) else {}
    task_id = task.get('id') if isinstance(task.get('id'), str) else ''
    # `legacy_state` ставить лише адаптер ЛІГИ ядра (`serve._publish_legacy_call`): її стан — з локального tasks.json
    project, scope, note = _cli_pick(ctx, task.get('state'), task_id, legacy=task.get('legacy_state') is True)   # ДО будь-якого запуску
    npx = _cli_npx(ctx)
    # `--scope` — якщо привʼязка відома. Без нього `link` у чужому акаунті СТВОРИВ БИ проєкт із тим самим імʼям, і задача
    # отримала б друге посилання; зі скоупом vercel відмовляє вголос (`vercel-scope`).
    sc = ['--scope', scope] if scope else []
    try:
        link = _vc(npx, ['link', '--yes', *sc, '--project', project], build_dir, CLI_LINK_S)
        if link.returncode == 0:                                        # збій `link` — нижче, ДО `deploy`
            out = _vc(npx, ['deploy', '--prod', '--yes', *sc], build_dir, CLI_DEPLOY_S)
    except (OSError, ValueError, subprocess.SubprocessError) as e:      # ValueError — напр. NUL у шляху теки
        raise _error(ctx, 'vercel-deploy', str(e)) from None
    # ⛔ Збій `link` зупиняє ВСЕ (відхилення від 0.8.0, де його код не читали): без привʼязки `deploy` пішов би в проєкт з
    # імʼям ТЕКИ, а прибирання потім чистило б задуманий проєкт без його поточної публікації. Код — той самий `_cli_code`.
    if link.returncode != 0:
        raw = link.stderr or link.stdout or ''
        raise _error(ctx, _cli_code(raw), raw[-CLI_RAW_MAX:])
    if out.returncode != 0:
        raw = out.stderr or out.stdout or ''
        raise _error(ctx, _cli_code(raw), raw[-CLI_RAW_MAX:])
    urls = _cli_urls(out.stdout, out.stderr)
    if not urls:
        raise _error(ctx, 'vercel-no-url', 'Vercel не надрукував адреси публікації')
    url, known = _cli_alias(npx, urls[-1], build_dir, extra=urls)
    verify = _cli_verify(url, bool(task.get('gated')))
    warnings = [note] if note else []
    if verify is not None:
        warnings.append(_PROTECTION_TEXT.format(project=project) if verify['reason'] == 'vercel_protection'
                        else f'Не вдалося підтвердити превʼю: {verify["reason"]}')
    try:
        cleanup_warning = _cli_cleanup(npx, project, scope, [*known, url], build_dir)   # ПІСЛЯ перевірки
    except Exception:  # noqa: BLE001 — прибирання НЕОБОВʼЯЗКОВЕ: публікація вже вдалась, що б не трапилось
        cleanup_warning = 'Старі публікації не прибрано: неочікуваний збій прибирання.'
    if cleanup_warning:
        warnings.append(cleanup_warning)
    state = {'project': project, 'task': task_id}
    got = scope or _cli_link_scope(build_dir)
    if got:                                                         # `scope` без значення в стан не кладемо: лише рядки й числа
        state['scope'] = got
    return {'url': url, 'deploy_url': urls[-1], 'verified': verify is None, 'verify': verify,
            'warnings': [_utf8(w)[:WARN_MAX] for w in warnings[:MAX_WARNINGS]],
            'cleanup_warning': _utf8(cleanup_warning)[:WARN_MAX] if cleanup_warning else None, 'state': state}


def _check_cli(ctx):
    """`check` режиму `cli`: `npx vercel whoami` (зайшли в Vercel на цій машині?). Нічого не створює й не кидає."""
    find = ctx.get('find_tool') if isinstance(ctx, dict) else None
    npx = find('npx') if callable(find) else None
    if not (isinstance(npx, str) and npx):
        return {'ok': False, 'error': 'no-node', 'detail': 'npx (Node.js) не знайдено'}
    settings = ctx.get('settings') if isinstance(ctx, dict) and isinstance(ctx.get('settings'), dict) else {}
    team = settings.get('team')
    team = team.strip() if isinstance(team, str) else ''
    try:
        r = _vc(npx, ['whoami', *(['--scope', team] if CLI_SCOPE_RE.fullmatch(team) else [])], None, CLI_WHOAMI_S)
    except subprocess.TimeoutExpired as e:                               # ПЕРЕД SubprocessError: це його підклас
        return {'ok': False, 'error': 'check-timeout', 'detail': _utf8(str(e))[:200]}
    except (OSError, ValueError, subprocess.SubprocessError) as e:      # npx не запускається — це «нема Node», а не «не ввійшли»
        return {'ok': False, 'error': 'no-node', 'detail': _utf8(str(e))[:200]}
    if r.returncode != 0:
        return {'ok': False, 'error': 'vercel-login', 'detail': _utf8(' '.join((r.stderr or r.stdout or '').split())[-200:])}
    lines = (r.stdout or '').strip().splitlines()
    return {'ok': True, 'detail': _utf8(lines[-1].strip() if lines else '')[:100]}


# -------------------------------------------------------------------------------------------------- роль

def _finish(ctx, project, state_pid, created_here, dep, warnings):
    """Усе після `POST /v13/deployments`: очікування, alias, перевірка, прибирання. Повертає `(url, verified, rec_pid)`."""
    dep_id = dep['id']
    streak = [0]
    ready = _wait_ready(ctx, dep_id, streak)
    ready, alias_err = _wait_alias(ctx, dep_id, ready, streak)
    pid = ready.get('projectId') if isinstance(ready.get('projectId'), str) and ready.get('projectId') else dep.get('projectId')
    pid = pid if isinstance(pid, str) and pid else None
    if pid is None:                                                 # Vercel не віддав projectId: беремо його за імʼям, щоб стан не загубився
        try:
            gid = _req(ctx, 'GET', '/v9/projects/' + urllib.parse.quote(project, safe='')).get('id')
            pid = gid if isinstance(gid, str) and gid else None
        except Exception:  # noqa: BLE001 — без id публікація лишається успішною (стан просто без id)
            pid = None
    url, has_alias = _main_url(ready, dep)
    if not has_alias:
        if alias_err:
            warnings.append(f'Vercel не зміг призначити постійну адресу проєкту ({alias_err}) — взято адресу окремої '
                            'публікації; Vercel зазвичай закриває її захистом (Deployment Protection).')
        else:
            warnings.append('Vercel не призначив постійної адреси проєкту — взято адресу окремої публікації; Vercel зазвичай '
                            'закриває її захистом (Deployment Protection), тож колеги можуть не відкрити.')
    verified, why = _verify(url, project)
    if why:
        warnings.append(why)
    # прибирання — лише в проєкті, який створив цей модуль для цієї задачі: його projectId записаний у стані й збігається
    ours = pid is not None and (created_here or (state_pid is not None and pid == state_pid))
    if ours:
        w = _cleanup(ctx, pid, project, dep_id)
        if w:
            warnings.append(w)
    elif state_pid is not None and pid != state_pid:
        warnings.append('Проєкт у Vercel не збігається з тим, що записано для цієї задачі: старі публікації не прибиралися.')
    # чужий projectId не «усиновлюємо»: запис у стані лишається тим, що створили ми
    return url, verified, (state_pid if state_pid is not None else pid)


def _publish(ctx, build_dir, task):
    if _auth(ctx) == 'cli':
        return _publish_cli(ctx, build_dir, task)                   # ДО `_need_token`: у режимі `cli` токена нема
    _need_token(ctx)
    state = task.get('state') if isinstance(task, dict) else None
    if not isinstance(build_dir, str) or not os.path.isdir(build_dir):
        raise RuntimeError('Збірка превʼю не є текою')
    files = _scan(build_dir)                                        # ДО будь-якого запиту
    task_id = task.get('id') if isinstance(task, dict) and isinstance(task.get('id'), str) else ''
    project, state_pid, created_here, note = _pick_project(ctx, state, task_id)
    warnings = [note] if note else []
    sent = set()
    deadline = time.monotonic() + UPLOAD_TOTAL_S
    for _rel, path, sha, size in files:
        if sha in sent:
            continue
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Завантаження файлів триває понад {UPLOAD_TOTAL_S} с (timeout)')
        _upload(ctx, path, sha, size)
        sent.add(sha)
    dep = _req(ctx, 'POST', '/v13/deployments', body={
        'name': project, 'project': project, 'target': 'production',
        'files': [{'file': rel, 'sha': sha, 'size': size} for rel, _p, sha, size in files],
        'projectSettings': {'framework': None}})
    dep_id = dep.get('id')
    if not isinstance(dep_id, str) or not dep_id:
        raise RuntimeError('Vercel не повернув ідентифікатор публікації')
    try:
        url, verified, rec_pid = _finish(ctx, project, state_pid, created_here, dep, warnings)
    except Exception as e:  # noqa: BLE001 — збій після створення публікації: проєкт, створений ЦИМ викликом, не лишаємо сиротою
        created_id = dep.get('projectId')
        if created_here and OWN_NAME_RE.fullmatch(project) and isinstance(created_id, str) and created_id:
            raise _with_note(ctx, e, _drop_created_project(ctx, project, created_id, dep_id)) from None
        raise
    # усі попередження — рядки без самотніх сурогатів (інакше ядро відмовить уже вдалу публікацію), ≤ `WARN_MAX`
    return {'url': url, 'verified': verified,
            'warnings': [_utf8(w)[:WARN_MAX] for w in warnings[:MAX_WARNINGS]],
            'state': {'project': project, 'project_id': rec_pid, 'deployment': dep_id, 'task': task_id}}


def publish(ctx, build_dir, task):
    """Роль `publish`: див. докстрінг модуля. Усі звичайні збої йдуть вгору як `ModuleError('module-error')` з чистим текстом."""
    try:
        return _publish(ctx, build_dir, task)
    except RuntimeError as e:      # `_HttpError`, `_NetworkError` і звичайні відмови модуля; код ядра чи `_CodedError` — як є
        out = _module_error(ctx, e)
        if out is e:
            raise
        raise out from None


def check(ctx):
    if _auth(ctx) == 'cli':
        return _check_cli(ctx)
    tok = _token(ctx)
    if not tok:
        return {'ok': False, 'error': 'no-token', 'detail': 'Токен Vercel не задано'}
    try:
        who = _req(ctx, 'GET', '/v2/user')
        user = who.get('user') if isinstance(who.get('user'), dict) else {}
        handle = user.get('username') or user.get('name')
        detail = _clean(handle, tok, 80) if isinstance(handle, str) and handle.strip() else 'акаунт Vercel'
        team = _team(ctx)
        if 'teamId' in team:
            t = _req(ctx, 'GET', '/v2/teams/' + urllib.parse.quote(team['teamId'], safe=''))
            label = t.get('name') or t.get('slug') or team['teamId']
            detail += ' · команда ' + _clean(label, tok, 80)
        elif 'slug' in team:
            # `GET /v2/teams/<slug>` приймає id, а не slug: доступ до команди перевіряємо читальним запитом У ЇЇ ОБСЯЗІ
            _req(ctx, 'GET', '/v6/deployments', query={'limit': 1})
            detail += ' · команда ' + _clean(team['slug'], tok, 80)
        return {'ok': True, 'detail': detail}
    except _NetworkError as e:
        return {'ok': False, 'error': 'network', 'detail': str(e)}
    except Exception as e:  # noqa: BLE001
        code = getattr(e, 'code', None)
        text = _clean(getattr(e, 'message', None) or str(e), tok, MSG_MAX)
        if code in ('vercel-auth', 'vercel-busy'):
            return {'ok': False, 'error': code, 'detail': text}
        if isinstance(e, RuntimeError):
            return {'ok': False, 'error': 'vercel-error', 'detail': text}
        raise
