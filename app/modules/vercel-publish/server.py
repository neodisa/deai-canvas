"""Вбудований модуль `vercel-publish` (роль `publish`, `publish_target: url`): зібране превʼю задачі → ВЛАСНИЙ Vercel людини.

Лише stdlib (`urllib`, `hashlib`, `json`, …): без Node, без CLI, без підпроцесів. Диспетчер ядра будує превʼю
(`build_preview`, за потреби з паролем-гейтом у сторінках) і кличе `publish(ctx, build_dir, task)`; модуль відправляє
теку на `api.vercel.com` і повертає адресу. Роздачі, лока й запису в `iterations.json` модуль не торкається — це ядро.

`server.py` виконується ядром через `exec` у свіжий модуль: без імпорту `serve`, `deai_modules` чи сусідніх файлів.
Із `ctx` береться лише:
  * `ctx['secrets']['token']` — токен Vercel; `ctx['settings']['team']` — команда (необовʼязково);
  * `ctx['ModuleError']` — клас помилки ядра: `call()` пропускає як є лише його, з кодом із таблиці `STATUS`
    (`vercel-auth`, `vercel-busy` → 409). Без класу в `ctx` (рукописний `ctx`) модуль кидає `RuntimeError` із тим самим
    кодом у тексті — тихої відмови нема.
Пароль превʼю (`ctx['secrets']['password']`) модуль НЕ читає: його вкладає в сторінки збірка (ядро).

Токен
  * іде ЛИШЕ в заголовок `Authorization` і ЛИШЕ на `API_BASE`, єдиним місцем — `_req`; ні в перевірку превʼю, ні в
    аргументи/оточення процесів, ні в тексти винятків (тексти Vercel, що його повторили б, вичищаються);
  * запити API не йдуть за редиректами (інакше `urllib` віддав би заголовок на чужий хост): 3xx — це помилка.

Стан задачі НЕ довіряється (`iterations.json` можна склонувати чи поділити). Проєкт зі стану береться лише коли його
імʼя — `pv-<8 цифр>` (те, що створює сам модуль), є непорожній `project_id` і `task` збігається з id ЦІЄЇ задачі
(скопійований із іншої задачі стан — «стану нема»). Навіть тоді ПЕРЕД будь-яким завантаженням проєкт шукається за `id`
(`GET /v9/projects/<project_id>`, тож перейменування в панелі його не губить): 200 — деплоїмо в нього під його ПОТОЧНИМ
імʼям (якщо воно відрізняється від записаного, спершу перевіряємо, що записана в стані остання публікація справді
належить цьому проєкту, інакше — «не наш»); 404 — проєкт видалено, і лише якщо записане імʼя теж вільне
(`GET /v9/projects/<імʼя>` → 404) створюємо наново під ним, інакше нове імʼя. У стані завжди лежить ПЕРВИННЕ імʼя
`pv-<8 цифр>`, а не перейменоване.

Що робить `publish(ctx, build_dir, task)` (`task = {id, title, dir, state}`; `state` — те, що модуль повернув минулого
разу, або `{}`)
  0. збірка читається ЦІЛКОМ І ЛОКАЛЬНО до першого запиту: будь-яке символічне посилання (файл чи тека), не звичайний
     файл, понад `MAX_FILES` файлів, файл понад `MAX_FILE_BYTES`, імʼя не з UTF-8 чи порожня збірка — `RuntimeError`,
     нічого не завантажено;
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
  8. повертає `{url, verified, warnings, state: {project, project_id, deployment, task}}`.
Збій ПІСЛЯ `POST /v13/deployments`, коли проєкт створив САМЕ цей виклик (перша публікація задачі, або проєкт зі стану
було видалено в панелі й створено наново в цьому ж виклику), — best-effort `DELETE /v9/projects/<id>` цього проєкту
(лише `pv-<8 цифр>`; на шляху зі станом, коли проєкт існував, — НІКОЛИ). «Створений цим викликом» — висновок із 404-проби,
а між пробою й `POST` проєкт міг створити хтось інший, тож ПЕРЕД видаленням: `id` починається з `prj_`, у проєкті
(`GET /v6/deployments?projectId=<id>&limit=5`) нема жодної публікації, крім цього виклику, і `GET /v9/projects/<id>`
дає те саме імʼя; інакше проєкт не видаляється, а текст помилки каже чому. Текст помилки завжди каже, видалено проєкт чи ні.
Очікування alias після `READY` НЕОБОВʼЯЗКОВЕ: будь-який збій у ньому (мережа, 5xx, 4xx, авторизація, ліміт) лишає
останню відповідь `READY` і веде до адреси публікації з попередженням — готова публікація не стає помилкою.

Ядро кличе `publish` БЕЗ тайм-ауту, тож кожен запит має свій: 30 с на запит API, 60 с на файл, 20 с на перевірку.

`check(ctx)` — `GET /v2/user` (+ `GET /v2/teams/<team_…>` для `teamId`; для `slug` — читальна проба доступу
`GET /v6/deployments?limit=1` у цій команді); нічого не створює й не кидає на звичайних збоях (немає токена, не
прийнято, мережі нема) — вертає `{"ok": false, "error": <код>, "detail": <причина>}`.
"""
import hashlib
import json
import os
import re
import secrets
import stat
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
#: Поточне імʼя проєкту, повернуте Vercel (його можна перейменувати в панелі): звичайні символи імен проєктів Vercel.
REAL_NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', re.ASCII)
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


def _clean(text, token, limit):
    """Рядок для тексту помилки: без переносів і зайвих пробілів, без токена, не довше `limit`."""
    text = ' '.join(str(text).split())
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


def _renamed_is_ours(ctx, project_id, state):
    """Проєкт із записаним `project_id` має інше імʼя, ніж записано (перейменовано в панелі — чи `project_id` підроблено на
    чужий проєкт). Доводимо, що він наш: записана в стані остання публікація існує й належить саме цьому проєкту."""
    dep = _state_str(state, 'deployment')
    if not dep:
        return False
    try:
        d = _req(ctx, 'GET', '/v13/deployments/' + urllib.parse.quote(dep, safe=''))
    except Exception:  # noqa: BLE001 — не вдалось довести: вважаємо чужим
        return False
    return d.get('projectId') == project_id


def _pick_project(ctx, state, task_id):
    """`(імʼя_для_Vercel, імʼя_для_стану, projectId | None, створено_цим_викликом, попередження | None)`.
    Стан не довіряється. Проєкт зі стану шукається за `id` (`GET /v9/projects/<project_id>`) ДО будь-якого завантаження:
    200 — деплоїмо в нього під його поточним імʼям (перейменований — лише якщо `_renamed_is_ours`); 404 — видалено:
    наново під записаним імʼям, лише якщо й воно вільне (404). Усе інше — нове `pv-<8 цифр>`, перевірене
    `GET /v9/projects/<імʼя>` → 404 (200 — чужий проєкт). У стан завжди йде ПЕРВИННЕ імʼя `pv-<8 цифр>`."""
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
                return name, name, None, True, None                # імʼя вільне: створюємо наново під ним
        else:
            real = got.get('name')
            if got.get('id') == pid and isinstance(real, str) and REAL_NAME_RE.fullmatch(real) and (
                    real == name or _renamed_is_ours(ctx, pid, state)):
                return real, name, pid, False, None
        note = ('Проєкт цієї задачі у Vercel змінився (інший ідентифікатор) — створено новий проєкт; '
                'адреса може відрізнятись від попередньої.')
    for _ in range(NAME_TRIES):
        name = f'pv-{secrets.randbelow(10 ** 8):08d}'
        try:
            _req(ctx, 'GET', '/v9/projects/' + urllib.parse.quote(name, safe=''))
        except _HttpError as e:
            if e.status == 404:
                return name, name, None, True, note
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
        return False, ('Превʼю закрите захистом Vercel (Deployment Protection): без входу в акаунт Vercel воно не відкриється. '
                       f'Вимкнути: Vercel → проєкт {project} → Settings → Deployment Protection → Vercel Authentication → Disabled.')
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
    щоб примітка вмістилась у `ERR_MAX` цілою."""
    msg = getattr(e, 'message', None)
    base = msg if isinstance(msg, str) else str(e)
    text = _clean(base, _token(ctx), max(ERR_MAX - len(note) - 1, 0)) + ' ' + note
    code = getattr(e, 'code', None)
    return _error(ctx, code if isinstance(code, str) else 'module-error', text)


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


def publish(ctx, build_dir, task):
    _need_token(ctx)
    state = task.get('state') if isinstance(task, dict) else None
    if not isinstance(build_dir, str) or not os.path.isdir(build_dir):
        raise RuntimeError('Збірка превʼю не є текою')
    files = _scan(build_dir)                                        # ДО будь-якого запиту
    task_id = task.get('id') if isinstance(task, dict) and isinstance(task.get('id'), str) else ''
    project, state_name, state_pid, created_here, note = _pick_project(ctx, state, task_id)
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
    return {'url': url, 'verified': verified,
            'warnings': [w[:WARN_MAX] for w in warnings[:MAX_WARNINGS]],
            'state': {'project': state_name, 'project_id': rec_pid, 'deployment': dep_id, 'task': task_id}}


def check(ctx):
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
