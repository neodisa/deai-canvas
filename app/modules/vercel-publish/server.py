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

Що робить `publish(ctx, build_dir, task)` (`task = {id, title, dir, state}`; `state` — те, що модуль повернув минулого
разу, або `{}`)
  0. збірка читається ЦІЛКОМ І ЛОКАЛЬНО до першого запиту: будь-яке символічне посилання (файл чи тека) чи не звичайний
     файл — `RuntimeError`, нічого не завантажено; порожня збірка теж;
  1. проєкт: із `state.project` (+ `state.project_id`) або НОВЕ непрозоре імʼя `pv-<8 цифр>` (в адресі ні назви
     задачі, ні клієнта), перевірене `GET /v9/projects/<імʼя>` — мусить дати 404, інакше (чужий проєкт із таким
     імʼям) інше імʼя, ≤ 3 спроби;
  2. файли: `POST /v2/files` по разу на вміст (SHA-1), 60 с на файл;
  3. `POST /v13/deployments` (`target: production`, без збірки: превʼю вже зібране);
  4. опитування `GET /v13/deployments/<id>` кожні `POLL_S` до `READY` (`ERROR`/`CANCELED` → помилка з текстом Vercel,
     понад `POLL_MAX_S` — `timeout`);
  5. адреса: найкоротший `alias` на `.vercel.app` (продакшн-адреса проєкту); нема — адреса самої публікації + попередження
     (її Vercel зазвичай закриває захистом);
  6. перевірка `GET <адреса>` без жодних облікових даних і БЕЗ переходів: 200 — `verified`; 401/403 чи редирект на
     `vercel.com` — не `verified` + попередження про Deployment Protection; усе інше — не `verified`, публікація
     не зупиняється;
  7. прибирання старих публікацій проєкту (тримаємо `KEEP` разом із поточною) — лише коли `projectId` публікації збігається
     зі `state.project_id` (або проєкт створив САМЕ цей виклик); чужий проєкт не чіпаємо взагалі; будь-який збій —
     попередження, не помилка;
  8. повертає `{url, verified, warnings, state: {project, project_id, deployment}}`.

Ядро кличе `publish` БЕЗ тайм-ауту, тож кожен запит має свій: 30 с на запит API, 60 с на файл, 20 с на перевірку.

`check(ctx)` — `GET /v2/user` (+ `GET /v2/teams/<team>`, коли команду задано); нічого не створює й не кидає на звичайних
збоях (немає токена, не прийнято, мережі нема) — вертає `{"ok": false, "error": <код>, "detail": <причина>}`.
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
#: Скільки публікацій проєкту лишаємо після прибирання (разом із поточною).
KEEP = 3
API_TIMEOUT_S = 30
UPLOAD_TIMEOUT_S = 60
PREVIEW_TIMEOUT_S = 20
#: Більше цього відповіді API не читаємо (це JSON зі списком, а не файли).
MAX_BODY = 4 << 20
NAME_TRIES = 3
#: Довжина тексту Vercel у помилці й у попередженні (ядро ріже до 300 само; ми — раніше й обачніше).
MSG_MAX = 200
WARN_MAX = 300
MAX_WARNINGS = 5
UA = 'deai-canvas-vercel-publish/1.0'
#: Імʼя проєкту Vercel: нижній регістр, цифри, `.`, `_`, `-`; ≤ 100.
PROJECT_RE = re.compile(r'[a-z0-9][a-z0-9._-]{0,99}', re.ASCII)
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


def _vercel_message(raw, token):
    """`error.message` (чи `message`) із тіла відповіді Vercel; порожній рядок, якщо тіла нема чи воно не JSON."""
    try:
        data = json.loads(raw.decode('utf-8', 'replace'))
    except ValueError:
        return ''
    err = data.get('error') if isinstance(data, dict) else None
    if isinstance(err, dict):
        msg = err.get('message')
    elif isinstance(err, str):
        msg = err
    else:
        msg = data.get('message') if isinstance(data, dict) else None
    return _clean(msg, token, MSG_MAX) if isinstance(msg, str) else ''


def _req(ctx, method, path, *, query=None, body=None, raw=None, headers=None, timeout=API_TIMEOUT_S):
    """Один запит до `API_BASE`: ЄДИНЕ місце, де є `Authorization: Bearer <токен>`; параметр команди — до кожного запиту.
    JSON у `body` (або байти в `raw` із заголовками викликача); результат — розібраний JSON-обʼєкт (`{}` для порожнього).
    401/403 → `vercel-auth`, 429 → `vercel-busy` (обидва з текстом Vercel), інший HTTP → `_HttpError`, мережа →
    `_NetworkError('Vercel недоступний')`. Ні в одному тексті винятку токена нема."""
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
    except Exception:  # noqa: BLE001 — URLError, тайм-аут, обрив, TLS, `http.client.*`: для людини це одне — «недоступний»
        raise _NetworkError('Vercel недоступний') from None
    if not 200 <= status < 300:                                    # 3xx — теж помилка: за редиректами не йдемо
        msg = _vercel_message(payload, token)
        if status in (401, 403):
            raise _error(ctx, 'vercel-auth', 'Vercel не прийняв токен' + (f': {msg}' if msg else f' (HTTP {status})'))
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

def _scan(build_dir):
    """`[(відносний шлях через '/', шлях на диску, sha1, розмір)]` за відсортованими шляхами. Символічне посилання (файл чи
    тека, навіть биті) і не звичайний файл — `RuntimeError`: так само читається все, ДО першого запиту."""
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
                mode = os.lstat(p).st_mode
            except OSError:
                raise RuntimeError(f'Не вдалося прочитати {rel} — публікацію зупинено') from None
            if stat.S_ISLNK(mode):
                raise RuntimeError(f'У збірці є символічне посилання ({rel}) — публікацію зупинено')
            if name in filenames:
                if not stat.S_ISREG(mode):
                    raise RuntimeError(f'У збірці є не звичайний файл ({rel}) — публікацію зупинено')
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
    """`POST /v2/files`: вміст файла за SHA-1. Читаємо знову й звіряємо з тим, що порахували: файл, що змінився між
    підрахунком і завантаженням, не відправляємо під чужим хешем."""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        raise RuntimeError('Не вдалося прочитати файл збірки — публікацію зупинено') from None
    if len(data) != size or hashlib.sha1(data, usedforsecurity=False).hexdigest() != sha:
        raise RuntimeError('Файл збірки змінився під час публікації — спробуйте ще раз')
    _req(ctx, 'POST', '/v2/files', raw=data, timeout=UPLOAD_TIMEOUT_S,
         headers={'Content-Type': 'application/octet-stream', 'x-vercel-digest': sha, 'Content-Length': str(len(data))})


# -------------------------------------------------------------------------------------------- проєкт, стан

def _state_str(state, key):
    v = state.get(key) if isinstance(state, dict) else None
    return v if isinstance(v, str) and v else None


def _pick_project(ctx, state):
    """`(імʼя, projectId зі стану | None, створено_цим_викликом)`. Стан задачі — лише справжнє імʼя проєкту; інакше нове
    `pv-<8 цифр>`, перевірене `GET /v9/projects/<імʼя>` → 404 (200 — чужий проєкт: беремо інше імʼя)."""
    name = _state_str(state, 'project')
    if name and PROJECT_RE.fullmatch(name):
        pid = _state_str(state, 'project_id')
        return name, (pid if pid and len(pid) <= 200 else None), False
    for _ in range(NAME_TRIES):
        name = f'pv-{secrets.randbelow(10 ** 8):08d}'
        try:
            _req(ctx, 'GET', '/v9/projects/' + urllib.parse.quote(name, safe=''))
        except _HttpError as e:
            if e.status == 404:
                return name, None, True
            raise
    raise RuntimeError(f'Не вдалося підібрати вільне імʼя проєкту у Vercel ({NAME_TRIES} спроби)')


# ----------------------------------------------------------------------------------------- очікування, адреса

def _wait_ready(ctx, dep_id):
    """Опитування до `READY`: повертає останню відповідь `GET /v13/deployments/<id>`."""
    deadline = time.monotonic() + POLL_MAX_S
    while True:
        d = _req(ctx, 'GET', '/v13/deployments/' + urllib.parse.quote(dep_id, safe=''))
        st = d.get('readyState') if isinstance(d.get('readyState'), str) else d.get('status')
        if st == 'READY':
            return d
        if st in ('ERROR', 'CANCELED'):
            why = d.get('errorMessage') if isinstance(d.get('errorMessage'), str) else ''
            why = why or (d.get('errorCode') if isinstance(d.get('errorCode'), str) else '')
            raise RuntimeError('Vercel: ' + (_clean(why, _token(ctx), MSG_MAX) or f'публікація завершилась станом {st}'))
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


def _main_url(ready, created):
    """`(адреса, є_постійна_адреса)`: найкоротший `alias` на `.vercel.app`; нема — адреса самої публікації."""
    cands = []
    aliases = ready.get('alias')
    for a in (aliases if isinstance(aliases, list) else []):
        h = _host(a)
        if h and h.endswith('.vercel.app'):
            cands.append(h)
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


def _verify(url, project):
    """`(verified, попередження | None)` за відповіддю сторінки превʼю."""
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

def _cleanup(ctx, project_id, current_id):
    """Прибирання старих публікацій проєкту: тримаємо `KEEP` разом із поточною. Повертає попередження або `None`; будь-який збій —
    попередження (публікація вже відбулась). Чіпає лише записи цього проєкту з датою й ідентифікатором."""
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
            if it.get('projectId') not in (None, project_id):        # запис чужого проєкту — не наш
                continue
            if isinstance(created, bool) or not isinstance(created, (int, float)) or created - created != 0:
                continue                                              # не число, bool, NaN чи ±inf (`x - x != 0`)
            rest.append((created, uid))
        rest.sort(reverse=True)
        doomed = rest[max(KEEP - 1, 0):]                              # поточна лишається завжди, тож «інших» KEEP − 1
        failed = 0
        for i, (_created, uid) in enumerate(doomed):
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


# -------------------------------------------------------------------------------------------------- роль

def publish(ctx, build_dir, task):
    _need_token(ctx)
    state = task.get('state') if isinstance(task, dict) else None
    if not isinstance(build_dir, str) or not os.path.isdir(build_dir):
        raise RuntimeError('Збірка превʼю не є текою')
    files = _scan(build_dir)                                        # ДО будь-якого запиту
    project, state_pid, created_here = _pick_project(ctx, state)
    sent = set()
    for _rel, path, sha, size in files:
        if sha not in sent:
            _upload(ctx, path, sha, size)
            sent.add(sha)
    dep = _req(ctx, 'POST', '/v13/deployments', body={
        'name': project, 'project': project, 'target': 'production',
        'files': [{'file': rel, 'sha': sha, 'size': size} for rel, _p, sha, size in files],
        'projectSettings': {'framework': None}})
    dep_id = dep.get('id')
    if not isinstance(dep_id, str) or not dep_id:
        raise RuntimeError('Vercel не повернув ідентифікатор публікації')
    ready = _wait_ready(ctx, dep_id)
    pid = ready.get('projectId') if isinstance(ready.get('projectId'), str) and ready.get('projectId') else dep.get('projectId')
    pid = pid if isinstance(pid, str) and pid else None
    url, has_alias = _main_url(ready, dep)
    warnings = []
    if not has_alias:
        warnings.append('Vercel не призначив постійної адреси проєкту — взято адресу окремої публікації; Vercel зазвичай '
                        'закриває її захистом (Deployment Protection), тож колеги можуть не відкрити.')
    verified, why = _verify(url, project)
    if why:
        warnings.append(why)
    # прибирання — лише в проєкті, який створив цей модуль для цієї задачі: його projectId записаний у стані й збігається
    ours = pid is not None and (created_here or (state_pid is not None and pid == state_pid))
    if ours:
        w = _cleanup(ctx, pid, dep_id)
        if w:
            warnings.append(w)
    elif state_pid is not None and pid != state_pid:
        warnings.append('Проєкт у Vercel не збігається з тим, що записано для цієї задачі: старі публікації не прибиралися.')
    # чужий projectId не «усиновлюємо»: запис у стані лишається тим, що створили ми
    rec_pid = state_pid if state_pid is not None else pid
    return {'url': url, 'verified': verified,
            'warnings': [w[:WARN_MAX] for w in warnings[:MAX_WARNINGS]],
            'state': {'project': project, 'project_id': rec_pid, 'deployment': dep_id}}


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
        if team:
            value = next(iter(team.values()))
            t = _req(ctx, 'GET', '/v2/teams/' + urllib.parse.quote(value, safe=''))
            label = t.get('name') or t.get('slug') or value
            detail += ' · команда ' + _clean(label, tok, 80)
        return {'ok': True, 'detail': detail}
    except _NetworkError:
        return {'ok': False, 'error': 'network', 'detail': 'Vercel недоступний'}
    except Exception as e:  # noqa: BLE001
        code = getattr(e, 'code', None)
        text = _clean(getattr(e, 'message', None) or str(e), tok, MSG_MAX)
        if code in ('vercel-auth', 'vercel-busy'):
            return {'ok': False, 'error': code, 'detail': text}
        if isinstance(e, RuntimeError):
            return {'ok': False, 'error': 'vercel-error', 'detail': text}
        raise
