"""Вбудовані модулі Deai Canvas — каркас етапу 2а (спека 2026-10-14-modules-2a-design.md, ревізія 2).

Модуль = тека `app/modules/<id>/` з `module.json` (маніфест) і `server.py` (функції ролей).
Роль = інтерфейс, який кличе ядро: `publish`, `tokens`; `comments`, `vcs`, `tracker`,
`dashboard`, `notify` — зарезервовані (ядро їх не кличе). Один постачальник на роль у просторі.
Файл названо `deai_modules.py`, а не `modules.py`: `bin/` стоїть у `sys.path` попереду, і імпорт
був би неоднозначним.

Що де живе:
  * налаштування й вмикання — `<тека простору>/space.json`, ключ `modules`:
    `{"<id>": {"enabled": bool, "settings": {…символьні…}}}`. Шляхи зберігаються СИМВОЛЬНО
    (`{home}`, `{space}`, `{space_id}`) і підставляються лише під час читання (`resolve_settings`);
  * секрети (тип `secret`) — `<DEAI_HOME>/secrets.json`, `{"<space-id>": {"<module-id>": {"<key>":
    "<value>"}}}`, 0600 (тека 0700). Значення секретів НІКОЛИ не потрапляють у `space.json`, у стан
    (`effective_state`), у `resolve_settings`, у тексти помилок і результатів `check`.

Контракт помилок — `ModuleError(code, status=None, message='')`; код і HTTP-статус:
  bad-manifest 500 · module-error 502 · role-taken 409 · unknown-module 404 · bad-settings 400 ·
  space-json-unreadable 409 · spaces-off 409 · check-timeout 504 · bad-folder 409 (його кидає модуль
  публікації, див. нижче) · і два додаткові, яких вимагає чесна поведінка: secrets-unreadable 409 (є
  `secrets.json`, але не читається — НЕ вважати його порожнім: це мовчки зняло б пароль превʼю) та
  unwritable 500 (не записати `space.json` чи `secrets.json`). Другий аргумент-рядок розуміється як `message`.
  `ModuleError`, яку кидає САМ модуль із кодом із цієї таблиці, `call()` пропускає як є (текст очищено від
  секретів, ≤300; статус — з таблиці); невідомий код стає `module-error`.

Правила, які тримають решту коду чесним:
  * Завантаження — `exec(compile(…))` у свіжий `types.ModuleType('deai_mod_<id>')`: без `importlib`,
    без `__pycache__`, не в `sys.modules`. Кеш за (шлях, mtime_ns, розмір, inode) обох файлів.
    Маніфест, що не пройшов перевірку, НЕ виконує `server.py` взагалі.
  * `WRITE_LOCK` (той самий, що в `spaces`) не реентерабельний: під ним ніколи не кличемо
    `catalog()` (виконання коду модулів), `load_registry()` чи будь-що, що бере лок. Каталог
    беремо ДО локу, а під ним перечитуємо стан із диска й перевіряємо на ньому `role-taken`.
  * Будь-який виклик функції модуля — `call()`: `BaseException` (окрім `KeyboardInterrupt`) →
    `module-error` без значень секретів, ≤300 символів; виняток-першоджерело не чіпляється до
    нового (`__cause__`/`__context__` порожні), щоб секрет не виїхав у traceback.
  * Шлях ЛІГА недоторканий: `provider()` для простору запиту, що не зафіксований (чи шар вимкнено),
    віддає `'legacy'`/`None` НЕ читаючи ні реєстр, ні `space.json`, ні каталог; простір з `integrations`
    без жодного явно ввімкненого модуля — те саме, ДО каталогу (зламаний вбудований модуль чи
    пошкоджений `space.json` не зачепить зашитий шлях). У просторі БЕЗ інтеграцій `provider()` мусить
    знати явні рішення, тож нечитабельний `space.json` — `ModuleError('space-json-unreadable', 409)`.
  * `capabilities()` — ТОТАЛЬНА (опитування, списки просторів): ніколи не кидає, а помилку кладе в
    ключ `error` (див. функцію).
  * Правила теки публікації живуть тут (`published_root`, `folder_ok`, `folder_inputs`), щоб їх ділили
    `serve.py` і модуль; код модулів НЕ імпортує `serve` (а `import deai_modules` — можна). `ctx` модуля для
    `serve.py` — `module_ctx()`.
  * Межі `exec`-завантаження (модуль — не в `sys.modules`): `@dataclass` разом з `from __future__ import
    annotations` падає (`dataclasses` шукає `sys.modules[cls.__module__]`), класи з `exec`-модулів не
    піклюються (`pickle`, `multiprocessing` у режимі spawn), `importlib.reload` не працює. Модулям вистачає
    функцій і простих структур.
  * Вимкнений шар просторів (лише `DC_TASKS_FILE`) нічого не пише: `write_module_state` і
    `write_secrets` → `spaces-off`, `read_secrets` → `{}` без звернення до диска.
"""
import json
import os
import re
import threading
import time
import types
from urllib.parse import quote

import spaces
from atomic_io import atomic_write_json

APP = os.path.dirname(os.path.abspath(__file__))

API_VERSION = 1
ROLES_CALLED = ('publish', 'tokens')
ROLES_RESERVED = ('comments', 'vcs', 'tracker', 'dashboard', 'notify')
SETTING_TYPES = ('text', 'path', 'bool', 'select', 'secret')
ID_RE = re.compile(r'[a-z0-9][a-z0-9-]{0,39}')
KEY_RE = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}')
#: Єдиний модуль із неявним типовим станом: діє в просторі без `integrations`, доки людина не
#: вирішила інакше (`modules["static-publish"]` у `space.json`).
IMPLICIT_MODULE = 'static-publish'
#: Скільки секунд чекаємо на `check` модуля (виклик у робочому потоці).
CHECK_TIMEOUT = 5
MAX_SERVER_BYTES = 1 << 20
MAX_VALUE_LEN = 4096
MAX_MESSAGE = 300
MAX_FULL_MESSAGE = 1 << 16

STATUS = {'bad-manifest': 500, 'module-error': 502, 'role-taken': 409, 'unknown-module': 404,
          'bad-settings': 400, 'space-json-unreadable': 409, 'spaces-off': 409,
          'check-timeout': 504, 'secrets-unreadable': 409, 'unwritable': 500, 'bad-folder': 409}


class ModuleError(Exception):
    """`code` — з таблиці `STATUS`, `status` — HTTP, `message` — текст (≤300, без секретів).
    `ModuleError('x', 409)`, `ModuleError('x', message='…')` і `ModuleError('x', '…')` — усе дозволено.
    Повний текст (до 64 КіБ) лишається в `_full`: `_run` вирізає секрети з НЬОГО й лише потім ріже до 300 —
    секрет, що перетинає межу, інакше пролізав би обрізаним початком."""

    def __init__(self, code, status=None, message=''):
        if isinstance(status, str):
            status, message = (message if isinstance(message, int) else None), status
        self.code = code
        self.status = status if isinstance(status, int) else STATUS.get(code, 500)
        self._full = str(message or '')[:MAX_FULL_MESSAGE]
        self.message = self._full[:MAX_MESSAGE]
        super().__init__(f'{code}: {self.message}' if self.message else code)


class Module:
    """Вбудований модуль із каталогу. `status`: `'ok'` — вантажиться й відповідає маніфесту,
    `'error'` — ні (`error` — текст, `error_code` — `bad-manifest` чи `module-error`). Модуль із
    помилкою лишається в каталозі, але нічого не віддає (`fn()` → `None`) і постачальником не є.
    `fn(role | 'check')` — функція `server.py` або `None`."""
    __slots__ = ('id', 'name', 'version', 'api', 'roles', 'settings', 'status', 'error', 'error_code',
                 'dir', '_fns')

    def __init__(self, mid, *, name=None, version='', api=None, roles=(), settings=(), status='ok',
                 error=None, error_code=None, dir='', fns=None):
        self.id = mid
        self.name = name if isinstance(name, str) and name.strip() else mid
        self.version = version if isinstance(version, str) else ''
        self.api = api
        self.roles = list(roles)
        self.settings = [dict(s) for s in settings]
        self.status = status
        self.error = error
        self.error_code = error_code
        self.dir = dir
        self._fns = dict(fns or {}) if status == 'ok' else {}

    def fn(self, name):
        return self._fns.get(name)

    def secret_keys(self):
        return [s['key'] for s in self.settings if s['type'] == 'secret']

    def __repr__(self):
        return f'<Module {self.id} {self.status}>'


# ----------------------------------------------------------------------------------- каталог

def builtin_dir():
    """Тека вбудованих модулів `<app>/modules` (у тестах патчиться)."""
    return os.path.join(APP, 'modules')


#: Кеш завантажених модулів: `{тека: (відбиток файлів, Module)}`. Відбиток — (mtime_ns, розмір, inode)
#: `module.json` і `server.py`; inode ловить заміну файла перейменуванням із тим самим mtime і розміром.
_CACHE = {}
_LOAD_LOCK = threading.RLock()        # власний лок вантаження (НЕ `WRITE_LOCK`); RLock — модуль може кликати `catalog()`
_STATE_LOCK = threading.Lock()
#: Останній результат `check` на пару (id простору, id модуля) — для `GET /api/modules`.
_LAST_CHECK = {}
#: `capabilities`: `{id простору: (ключ, результат)}`.
_CAPS = {}
#: Вхідні дані `folder_ok` (реєстр + теки задач) на `FOLDER_INPUTS_TTL` секунд: `{'v': (ключ, момент, значення)}`.
_FOLDER_INPUTS = {}
FOLDER_INPUTS_TTL = 2


def reset_caches():
    """Скинути всі кеші процесу (тести; відновлення після підміни `builtin_dir`)."""
    with _LOAD_LOCK:
        _CACHE.clear()
    with _STATE_LOCK:
        _LAST_CHECK.clear()
        _CAPS.clear()
        _FOLDER_INPUTS.clear()


def _sig(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _short(e):
    try:
        return f'{type(e).__name__}: {e}'[:200]
    except BaseException:  # noqa: BLE001 — `str(e)` теж може кинути
        return type(e).__name__


def _exc_text(e):
    try:
        msg = str(e)
    except BaseException:  # noqa: BLE001
        msg = ''
    return f'{type(e).__name__}: {msg}' if msg else type(e).__name__


def _scan():
    """(тека, [(імʼя, шлях)]) — підтеки `builtin_dir()` за абеткою, без прихованих і `__pycache__`."""
    base = os.path.normpath(builtin_dir())
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return base, []
    out = []
    for n in names:
        if n.startswith('.') or n == '__pycache__':
            continue
        d = os.path.join(base, n)
        if os.path.isdir(d):
            out.append((n, d))
    return base, out


def _encodable(v):
    """Рядок можна записати в UTF-8 файл: самотній сурогат (`\\ud800` із JSON-екрана) — ні, і падав би на записі."""
    try:
        v.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def _value_ok(s, v):
    """Значення `v` придатне для налаштування `s` (без підстановок). Секрет — ніколи."""
    t = s['type']
    if t == 'bool':
        return isinstance(v, bool)
    if t == 'secret' or not isinstance(v, str) or len(v) > MAX_VALUE_LEN or not _encodable(v):
        return False
    if t == 'path':
        return bool(v.strip()) and spaces._usable_path_text(v)
    if t == 'select':
        return v in {o['value'] for o in s['options']}
    return True


def _check_setting(s, seen):
    """(нормалізоване налаштування, None) або (None, причина)."""
    if not isinstance(s, dict):
        return None, 'must be an object'
    key = s.get('key')
    if not isinstance(key, str) or not KEY_RE.fullmatch(key):
        return None, 'key: must match [A-Za-z][A-Za-z0-9_-]{0,63}'
    if key in seen:
        return None, f'duplicate key {key!r}'
    t = s.get('type')
    if not isinstance(t, str) or t not in SETTING_TYPES:
        return None, f'{key}: type must be one of {", ".join(SETTING_TYPES)}'
    label = s.get('label', key)
    if not isinstance(label, str):
        return None, f'{key}: label must be a string'
    required = s.get('required', False)
    if not isinstance(required, bool):
        return None, f'{key}: required must be a boolean'
    out = {'key': key, 'type': t, 'label': label, 'required': required}
    if t == 'select':
        opts = s.get('options')
        if not isinstance(opts, list) or not opts or not all(
                isinstance(o, dict) and isinstance(o.get('value'), str) and isinstance(o.get('label'), str)
                for o in opts):
            return None, f'{key}: select needs options: [{{"value", "label"}}, …] (non-empty)'
        out['options'] = [{'value': o['value'], 'label': o['label']} for o in opts]
    if s.get('default') is not None:
        if t == 'secret':
            return None, f'{key}: a secret cannot have a default'
        if not _value_ok(out, s['default']):
            return None, f'{key}: default does not fit type {t}'
        out['default'] = s['default']
    seen.add(key)
    return out, None


def _check_manifest(man, folder):
    """(метадані, None) або (None, причина) — перевірка маніфесту без виконання `server.py`."""
    if not isinstance(man, dict):
        return None, 'module.json: not an object'
    api = man.get('api')
    if type(api) is not int or api != API_VERSION:
        return None, f'api: must be {API_VERSION}'
    mid = man.get('id')
    if not isinstance(mid, str) or not ID_RE.fullmatch(mid):
        return None, 'id: must match [a-z0-9][a-z0-9-]{0,39}'
    if mid != folder:
        return None, f'id: {mid!r} differs from the folder name {folder!r}'
    name = man.get('name', mid)
    if not isinstance(name, str) or not name.strip():
        return None, 'name: must be a non-empty string'
    version = man.get('version', '')
    if not isinstance(version, str):
        return None, 'version: must be a string'
    roles = man.get('roles')
    if not isinstance(roles, list):
        return None, 'roles: must be a list'
    for r in roles:
        if not isinstance(r, str) or r not in ROLES_CALLED + ROLES_RESERVED:
            return None, f'roles: unknown role {str(r)[:40]!r}'
    raw = man.get('settings', [])
    if not isinstance(raw, list):
        return None, 'settings: must be a list'
    settings, seen = [], set()
    for i, s in enumerate(raw):
        norm, why = _check_setting(s, seen)
        if why:
            return None, f'settings[{i}]: {why}'
        settings.append(norm)
    return {'name': name, 'version': version, 'roles': list(dict.fromkeys(roles)),
            'settings': settings}, None


def _failed(folder, d, code, text, man=None, meta=None):
    base = dict(status='error', error=str(text)[:MAX_MESSAGE], error_code=code, dir=d)
    if meta:
        return Module(folder, name=meta['name'], version=meta['version'], api=API_VERSION,
                      roles=meta['roles'], settings=meta['settings'], **base)
    man = man if isinstance(man, dict) else {}
    api = man.get('api')
    return Module(folder, name=man.get('name'), version=man.get('version', ''),
                  api=api if type(api) is int else None, **base)


def _build(d, folder):
    mj, sv = os.path.join(d, 'module.json'), os.path.join(d, 'server.py')
    try:
        man = spaces._read_json(mj)
    except FileNotFoundError:
        return _failed(folder, d, 'bad-manifest', 'module.json: not found')
    except (OSError, ValueError) as e:
        return _failed(folder, d, 'bad-manifest', f'module.json: {_short(e)}')
    meta, why = _check_manifest(man, folder)
    if why:
        return _failed(folder, d, 'bad-manifest', why, man=man)
    try:
        with open(sv, 'rb') as f:
            raw = f.read(MAX_SERVER_BYTES + 1)
    except FileNotFoundError:
        return _failed(folder, d, 'bad-manifest', 'server.py: not found', meta=meta)
    except OSError as e:
        return _failed(folder, d, 'module-error', f'server.py: {_short(e)}', meta=meta)
    if len(raw) > MAX_SERVER_BYTES:
        return _failed(folder, d, 'module-error', f'server.py: bigger than {MAX_SERVER_BYTES} bytes', meta=meta)
    ns = types.ModuleType(f'deai_mod_{folder}')
    ns.__file__ = sv
    try:
        exec(compile(raw, sv, 'exec', dont_inherit=True), ns.__dict__)    # без importlib і без __pycache__
    except KeyboardInterrupt:
        raise
    except BaseException as e:  # noqa: BLE001 — SyntaxError, SystemExit у верхньому рівні, ImportError…
        return _failed(folder, d, 'module-error', _exc_text(e), meta=meta)
    fns = {}
    for need in ('check', *(r for r in meta['roles'] if r in ROLES_CALLED)):
        f = ns.__dict__.get(need)
        if not callable(f):
            return _failed(folder, d, 'bad-manifest', f'server.py: no callable {need}()', meta=meta)
        fns[need] = f
    return Module(folder, name=meta['name'], version=meta['version'], api=API_VERSION,
                  roles=meta['roles'], settings=meta['settings'], status='ok', dir=d, fns=fns)


def _load_dir(d, folder):
    sig = (_sig(os.path.join(d, 'module.json')), _sig(os.path.join(d, 'server.py')))
    with _LOAD_LOCK:
        hit = _CACHE.get(d)
        if hit is not None and hit[0] == sig:
            return hit[1]
        mod = _build(d, folder)
        _CACHE[d] = (sig, mod)
        return mod


def catalog():
    """`{id: Module}` вбудованих модулів (за абеткою). Модулі з помилкою — тут, зі `status='error'`.
    ⚠️ Виконує код модулів (першого разу чи після зміни файлів) — НЕ кликати під `WRITE_LOCK`."""
    base, items = _scan()
    out = {name: _load_dir(d, name) for name, d in items}
    live = {d for _, d in items}
    with _LOAD_LOCK:
        for k in [k for k in _CACHE if os.path.dirname(k) == base and k not in live]:
            del _CACHE[k]
    return out


def _catalog_sig():
    base, items = _scan()
    return (base, tuple((n, _sig(os.path.join(d, 'module.json')), _sig(os.path.join(d, 'server.py')))
                        for n, d in items))


# ------------------------------------------------------------------------------- простір і space.json

def _space_id(space):
    return str((space or {}).get('id') or '')


def _space_path(space):
    p = (space or {}).get('path')
    return p if isinstance(p, str) else ''


def _space_json_path(space):
    p = _space_path(space)
    return os.path.join(p, 'space.json') if p else None


def _load_space_json(path):
    """Вміст `space.json` як обʼєкт; файла нема — `{}`; не читається / не обʼєкт — 409."""
    try:
        data = spaces._read_json(path)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise ModuleError('space-json-unreadable', message=f'space.json: {_short(e)}') from None
    if not isinstance(data, dict):
        raise ModuleError('space-json-unreadable', message='space.json: not an object')
    return data


def _raw_modules(data):
    mods = data.get('modules')
    if mods is None:
        return {}
    if not isinstance(mods, dict):
        raise ModuleError('space-json-unreadable', message='space.json: "modules" is not an object')
    return mods


def _normalize(mods):
    out = {}
    for mid, e in mods.items():
        if not isinstance(e, dict):
            continue
        st = e.get('settings')
        out[mid] = {'enabled': e.get('enabled') is True, 'settings': dict(st) if isinstance(st, dict) else {}}
    return out


def space_modules(space):
    """`{id: {"enabled": bool, "settings": {…символьні…}}}` — явні рішення з `space.json` простору.
    Простір без теки/файла — `{}`; файл, що не читається, — `ModuleError('space-json-unreadable', 409)`."""
    path = _space_json_path(space)
    if path is None:
        return {}
    return _normalize(_raw_modules(_load_space_json(path)))


def _implicit_on(mid, space, explicit):
    return (mid == IMPLICIT_MODULE and mid not in explicit and bool(space)
            and not spaces.integrations_for(space))


def _enabled_in(m, space, explicit):
    """(увімкнено, неявно) для модуля `m` за явними рішеннями `explicit` і неявним типовим."""
    e = explicit.get(m.id)
    if e is not None:
        return e['enabled'], False
    if _implicit_on(m.id, space, explicit):
        return True, True
    return False, False


def _entry_state(m, space, explicit):
    en, implicit = _enabled_in(m, space, explicit)
    stored = explicit.get(m.id, {}).get('settings', {})
    settings = {}
    for s in m.settings:
        if s['type'] == 'secret':
            continue                                    # секрет не живе в налаштуваннях і не світиться
        if stored.get(s['key']) is not None:
            settings[s['key']] = stored[s['key']]
        elif 'default' in s:
            settings[s['key']] = s['default']
    return {'enabled': en, 'implicit': implicit, 'settings': settings}


def effective_state(space):
    """Для кожного модуля каталогу: `{enabled, implicit, settings}` (налаштування символьні, із
    типовими значеннями маніфесту, без секретів). `implicit` — увімкнений неявним типовим
    (`static-publish` у просторі без інтеграцій, поки нема явного рішення).
    ⚠️ Виконує код модулів (каталог) і може кинути `space-json-unreadable`."""
    if not space:
        return {}
    explicit = space_modules(space)
    return {mid: _entry_state(m, space, explicit) for mid, m in catalog().items()}


# ----------------------------------------------------------------------------------- налаштування

def _bad(msg):
    return ModuleError('bad-settings', message=msg)


def _check_value(s, v):
    if not _value_ok(s, v):
        raise _bad(f'{s["key"]}: expected {s["type"]}')


_PLACEHOLDER = re.compile(r'\{(home|space|space_id)\}')


def _subst_path(s, v, space):
    sp = _space_path(space)
    if '{space}' in v and not sp:
        raise _bad(f'{s["key"]}: {{space}} needs a space folder')
    vals = {'home': os.path.expanduser('~'), 'space': sp, 'space_id': _space_id(space)}
    p = os.path.expanduser(_PLACEHOLDER.sub(lambda m: vals[m.group(1)], v))   # один прохід
    if not os.path.isabs(p):
        if not sp:
            raise _bad(f'{s["key"]}: a relative path needs a space folder')
        p = os.path.join(sp, p)
    return os.path.normpath(p)


def resolve_settings(space, module, symbolic):
    """Символьні налаштування → робочі значення для `ctx['settings']`. Підстановки `{home}`
    (домівка користувача), `{space}` (тека простору), `{space_id}`; `~`; відносний `path` — від теки
    простору. Типи перевіряються (`bad-settings`); значення береться з `symbolic`, інакше з типового;
    обовʼязкове без значення — `bad-settings`, необовʼязкове — просто нема в результаті. Секрети й
    невідомі ключі в результат не потрапляють."""
    symbolic = symbolic if isinstance(symbolic, dict) else {}
    out = {}
    for s in module.settings:
        if s['type'] == 'secret':
            continue
        v = symbolic.get(s['key'])
        if v is None:
            v = s.get('default')
        if v is None:
            if s['required']:
                raise _bad(f'{s["key"]}: required')
            continue
        _check_value(s, v)
        out[s['key']] = _subst_path(s, v, space) if s['type'] == 'path' else v
    return out


def _validate_patch(m, settings):
    if settings is None:
        return {}
    if not isinstance(settings, dict):
        raise _bad('settings: expected an object')
    by_key = {s['key']: s for s in m.settings}
    for k, v in settings.items():
        s = by_key.get(k)
        if s is None:
            raise _bad(f'{str(k)[:40]!r}: unknown setting of {m.id}')
        if s['type'] == 'secret':
            raise _bad(f'{k}: a secret is written through the secrets, not the settings')
        if v is not None:
            _check_value(s, v)
    return dict(settings)


def _need_module(module_id):
    m = catalog().get(module_id) if isinstance(module_id, str) else None
    if m is None:
        raise ModuleError('unknown-module', message=str(module_id)[:60])
    return m


def _require_writable(space):
    if not spaces.layer_on() or not _space_path(space):
        raise ModuleError('spaces-off', message='spaces layer is off or the space has no folder')


def write_module_state(space, module_id, enabled=None, settings=None):
    """Змінити вмикання й/чи налаштування модуля в `space.json` простору. Читання-зміна-запис
    ПІД `WRITE_LOCK`; каталог — ДО локу; `role-taken` — на свіжо прочитаному стані під локом (неявно
    ввімкнений `static-publish` теж займає роль `publish`); невідомі ключі файла й запису модуля
    зберігаються; `settings` — патч (`None` значення знімає ключ); секрет у ньому — `bad-settings`.
    Новий запис модуля бере `enabled` із поточного ефективного стану, тож запис налаштувань не
    перемикає неявно ввімкнений `static-publish`. Повертає новий стан модуля."""
    _require_writable(space)
    if enabled is not None and not isinstance(enabled, bool):
        raise _bad('enabled: expected a boolean')
    cat = catalog()                                     # ДО локу: виконує код модулів
    m = cat.get(module_id) if isinstance(module_id, str) else None
    if m is None:
        raise ModuleError('unknown-module', message=str(module_id)[:60])
    patch = _validate_patch(m, settings)
    path = _space_json_path(space)
    with spaces.WRITE_LOCK:
        data = _load_space_json(path)
        mods = dict(_raw_modules(data))
        explicit = _normalize(mods)
        cur, _ = _enabled_in(m, space, explicit)
        if enabled is None and not patch:
            return _entry_state(m, space, explicit)
        if enabled is True:
            mine = set(m.roles)
            for oid in sorted(cat):
                other = cat[oid]
                shared = mine & set(other.roles)
                if oid == m.id or other.status != 'ok' or not shared:
                    continue
                if _enabled_in(other, space, explicit)[0]:
                    raise ModuleError('role-taken', message=f'{sorted(shared)[0]} is already provided by {oid}')
        old = mods.get(module_id)
        entry = dict(old) if isinstance(old, dict) else {}
        entry['enabled'] = enabled if enabled is not None else cur
        if patch:
            st = entry.get('settings')
            st = dict(st) if isinstance(st, dict) else {}
            for k, v in patch.items():
                if v is None:
                    st.pop(k, None)
                else:
                    st[k] = v
            entry['settings'] = st
        mods[module_id] = entry
        data['modules'] = mods
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            spaces._write_public(path, data)
        except (OSError, ValueError) as e:        # ValueError: UnicodeEncodeError, NUL у шляху
            raise ModuleError('unwritable', message=f'space.json: {type(e).__name__}') from None
        return _entry_state(m, space, _normalize(mods))


# ------------------------------------------------------------------------------- тека публікації

def published_root(space, module):
    """Вирішене налаштування `folder` модуля `module` (`Module` чи його id) у просторі `space` — абсолютний
    шлях після підстановок (`{home}`, `{space}`, `{space_id}`, `~`) або `None`, коли в модуля нема
    налаштування `folder`. Може кинути `bad-settings` / `space-json-unreadable` / `unknown-module`.
    Саму теку це НЕ перевіряє — для того `folder_ok`."""
    m = module if isinstance(module, Module) else _need_module(module)
    explicit = space_modules(space)
    return resolve_settings(space, m, _entry_state(m, space, explicit)['settings']).get('folder')


def _now():
    return time.monotonic()


def folder_inputs():
    """`(реєстр, теки задач)` для `folder_ok` або `None`, коли реєстр чи ФАЙЛ ЗАДАЧ ЯКОГОСЬ простору не
    читається (`spaces.unreadable_task_files`: `all_task_dirs` читає такий файл як порожній, а в ньому могли
    лежати теки задач, — тож перевірку «пускаємо» робити не можна). Результат кешується на
    `FOLDER_INPUTS_TTL` с (`folder_ok` кличуть на кожен роздаваний файл); відмову не кешуємо. Кеш прив'язаний до
    `DEAI_HOME`, файла старих задач і стану шару. Повернуті обʼєкти не змінювати."""
    reg_path, legacy_path = spaces.registry_path(), spaces.legacy_tasks_file()
    # Відбитки обох файлів у ключі: щойно створений простір чи змінений старий файл задач не чекають кінця TTL.
    key = (spaces.layer_on(), reg_path, legacy_path, _sig(reg_path), _sig(legacy_path))
    now = _now()
    with _STATE_LOCK:
        hit = _FOLDER_INPUTS.get('v')
    if hit is not None and hit[0] == key and 0 <= now - hit[1] < FOLDER_INPUTS_TTL:
        return hit[2]
    try:
        reg = spaces.read_registry()
        if spaces.unreadable_task_files(reg):
            return None
        val = (reg, spaces.all_task_dirs(reg))
    except (spaces.SpacesError, OSError, ValueError):
        return None
    with _STATE_LOCK:
        _FOLDER_INPUTS['v'] = (key, now, val)
    return val


def _home_walk(p):
    """За ФАЙЛОВОЮ системою (samefile, без урахування регістру): `(True, перша_складова)`, коли `p` лежить у
    домівці `~` (`перша_складова` — шлях на рівень під домівкою, `None`, якщо `p` — сама домівка);
    `(False, None)` — коли ні."""
    home = os.path.expanduser('~')
    a, child = p, None
    while True:
        if spaces._same_dir(a, home):
            return True, child
        parent = os.path.dirname(a)
        if parent == a:
            return False, None
        a, child = parent, a


def _fs_rules(pt):
    """Правила, яких текстове порівняння `spaces.check_new_path` не бачить на ФС без урахування регістру
    (`<ДОМІВКА великими>`, `<ДОМІВКА великими>/.ssh`, `<тека інструмента великими>`): код причини або `None`."""
    home = os.path.expanduser('~')
    if spaces._fs_under(home, pt):
        return 'path-too-broad'                         # сама домівка чи її предок в іншому написанні
    if spaces._fs_under(pt, spaces.ROOT) or spaces._fs_under(spaces.ROOT, pt):
        return 'path-tool'
    inside, child = _home_walk(pt)
    if inside:
        if child and (os.path.basename(child).startswith('.')
                      or spaces._same_dir(child, os.path.join(os.path.expanduser('~'), 'Library'))):
            return 'path-system'                        # `~/Library` і будь-яка прихована тека домівки
        return None
    sysdirs = {*spaces.SYSTEM_DIRS, *(os.path.realpath(d) for d in spaces.SYSTEM_DIRS)}
    if any(spaces._fs_under(pt, d) for d in sysdirs):
        return 'path-system'
    return None


def folder_ok(space, folder, *, reg=None, task_dirs=None):
    """Чи можна публікувати в теку `folder` (відносна — від теки простору): `(True, None)` або
    `(False, код)`. Кличуть при КОЖНІЙ публікації й роздачі, не лише при вмиканні.

    Правила — `spaces.check_new_path` над усіма просторами реєстру й теками всіх задач
    (`path-not-absolute`; `path-too-broad` — домівка й її предки; `path-system`; `path-tool` — тека
    інструмента; `path-not-dir`; `path-registered`/`path-overlap` — дорівнює, всередині чи НАД текою простору
    чи задачі; порівняння за `realpath`, у NFC й — для збігу з просторами та теками задач — за файловою
    системою) плюс:
      * `path-deai-home` — дорівнює, ВСЕРЕДИНІ чи НАД `DEAI_HOME` (`spaces.home()`): за текстом, за
        `realpath` обох (висяче посилання на `DEAI_HOME` теж), у NFC й за файловою системою;
      * за файловою системою (`samefile`, бо на macOS регістр не різнить теки, а текст його бачить): `path-tool`
        — тека інструмента, її підтека чи предок; `path-system` — `~/Library`, будь-яка прихована тека
        домівки чи системна тека (`/Applications`, `/System`…) в іншому написанні. Теку в домівці від
        системних тек FS-перевірка відрізняє так само, як текст (тимчасова домівка macOS живе під `/var`).
    Відмовляємо, а не пускаємо: реєстр чи файл задач будь-якого простору не читається —
    `(False, 'spaces-unreadable')` (`all_task_dirs` читав би його як порожній); збій перевірки шляху —
    `(False, 'path-invalid')`. Простори без `path` (неявний, шар вимкнено) у порівнянні не беруть участі,
    а теки задач старого файла беруться.

    `reg`/`task_dirs` — готові вхідні дані (з `folder_inputs()`): обидва задані — читання з диска нема;
    інакше бракуюче береться з диска (реєстр — свіжий, файли задач перевіряються на читабельність), а без обох
    — з `folder_inputs()` (кеш `FOLDER_INPUTS_TTL` с). Простір створено/додано щойно — у межах TTL
    перевірка може його ще не знати."""
    if not isinstance(folder, str) or not folder.strip() or not spaces._usable_path_text(folder):
        return False, 'path-not-absolute'
    p = os.path.expanduser(folder)
    if not os.path.isabs(p):
        sp = _space_path(space)
        if not sp:
            return False, 'path-not-absolute'
        p = os.path.join(sp, p)
    try:
        if reg is None and task_dirs is None:
            inputs = folder_inputs()
            if inputs is None:
                return False, 'spaces-unreadable'
            reg, task_dirs = inputs
        elif reg is None or task_dirs is None:
            if reg is None:
                reg = spaces.read_registry()
            if spaces.unreadable_task_files(reg):
                return False, 'spaces-unreadable'
            if task_dirs is None:
                task_dirs = spaces.all_task_dirs(reg)
    except spaces.SpacesError:
        return False, 'spaces-unreadable'
    try:
        pt, why = spaces.check_new_path(
            p, {'spaces': [sp for sp in reg['spaces'] if sp.get('path')]}, task_dirs)
        if why:
            return False, why
        pr = spaces._real(p)
        why = _fs_rules(pt) or _fs_rules(pr)            # `pr` — куди веде посилання (`~/lnk -> /APPLICATIONS`)
        if why:
            return False, why
        deai = os.path.abspath(spaces.home())
        for a, b in ((pt, spaces._text(deai)), (pr, spaces._real(deai))):
            if spaces._under(a, b) or spaces._under(b, a):
                return False, 'path-deai-home'
        if spaces._fs_under(pt, deai) or spaces._fs_under(deai, pt):
            return False, 'path-deai-home'
    except (OSError, ValueError):
        return False, 'path-invalid'
    return True, None


# ---------------------------------------------------------------------------------------- секрети

def _secrets_path():
    return os.path.join(spaces.home(), 'secrets.json')


def _secure(path, mode):
    """Явний `chmod` (на Windows права не виставляються — no-op, записано в «Межах» спеки)."""
    if os.name != 'nt':
        os.chmod(path, mode)


def _load_secrets():
    try:
        data = spaces._read_json(_secrets_path())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise ModuleError('secrets-unreadable', message=f'secrets.json: {type(e).__name__}') from None
    if not isinstance(data, dict):
        raise ModuleError('secrets-unreadable', message='secrets.json: not an object')
    return data


def _bucket(data, space_id, module_id):
    a = data.get(space_id)
    b = a.get(module_id) if isinstance(a, dict) else None
    return {k: v for k, v in b.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(b, dict) else {}


def read_secrets(space_id, module_id):
    """Секрети ОДНОГО модуля простору: `{key: value}`. Файла чи ключа нема (чи шар вимкнено) —
    `{}`. Файл є, але не читається — `secrets-unreadable` (не «порожньо»: інакше пароль мовчки зникає)."""
    if not spaces.layer_on():
        return {}
    return _bucket(_load_secrets(), space_id, module_id)


def write_secrets(space_id, module_id, patch):
    """Патч секретів модуля: ключ відсутній — лишити, `None` — видалити, рядок — записати. Ключі
    мусять бути оголошені в маніфесті як `secret`. Під `WRITE_LOCK`, атомарно, потім `chmod 0600` на
    файл і `0700` на теку. Шар вимкнено — `spaces-off` (справжній `~/.deai` не чіпаємо).
    Повертає імена ключів, що тепер задані (значень не віддає)."""
    if not spaces.layer_on():
        raise ModuleError('spaces-off', message='spaces layer is off')
    if not isinstance(space_id, str) or not space_id or not _encodable(space_id):
        raise _bad('space: expected an id')
    m = _need_module(module_id)                         # ДО локу
    if not isinstance(patch, dict):
        raise _bad('secrets: expected an object')
    allowed = set(m.secret_keys())
    for k, v in patch.items():
        if k not in allowed:
            raise _bad(f'{str(k)[:40]!r}: not a secret of {m.id}')
        if v is not None and not (isinstance(v, str) and len(v) <= MAX_VALUE_LEN and _encodable(v)):
            raise _bad(f'{k}: expected a string or null')
    with spaces.WRITE_LOCK:
        data = _load_secrets()
        spc = data.get(space_id)
        spc = dict(spc) if isinstance(spc, dict) else {}
        cur = spc.get(module_id)
        cur = dict(cur) if isinstance(cur, dict) else {}
        changed = False
        for k, v in patch.items():
            if v is None:
                if k in cur:
                    del cur[k]
                    changed = True
            elif cur.get(k) != v:
                cur[k] = v
                changed = True
        if changed:
            if cur:
                spc[module_id] = cur
            else:
                spc.pop(module_id, None)
            if spc:
                data[space_id] = spc
            else:
                data.pop(space_id, None)
            home, path = spaces.home(), _secrets_path()
            try:
                os.makedirs(home, mode=0o700, exist_ok=True)
                _secure(home, 0o700)
                if os.path.exists(path):
                    _secure(path, 0o600)                # ДО запису: атомарна заміна переносить режим цілі
                atomic_write_json(path, data)
                _secure(path, 0o600)
                _secure(home, 0o700)
            except (OSError, ValueError) as e:          # ValueError: UnicodeEncodeError (сурогат, що вже лежить у файлі)
                raise ModuleError('unwritable', message=f'secrets.json: {type(e).__name__}') from None
        else:
            try:                                        # нічого не змінилось, але права підтягуємо в будь-якому разі
                if os.path.exists(_secrets_path()):
                    _secure(_secrets_path(), 0o600)
                    _secure(spaces.home(), 0o700)
            except OSError as e:
                raise ModuleError('unwritable', message=f'secrets.json: {type(e).__name__}') from None
        return sorted(k for k, v in cur.items() if isinstance(v, str))


# ---------------------------------------------------------------------------------------- виклик

def _scrub(text, secrets):
    """Вирізати значення секретів (і їхні repr/JSON/URL-форми) з `text`; довші — першими."""
    vals = set()
    if isinstance(secrets, dict):
        for v in secrets.values():
            if isinstance(v, str) and v:
                vals |= {v, repr(v)[1:-1], json.dumps(v)[1:-1], json.dumps(v, ensure_ascii=False)[1:-1],
                         quote(v, safe='', errors='surrogatepass')}
    for v in sorted(vals, key=len, reverse=True):
        if v:
            text = text.replace(v, '***')
    return text


def _run(f, ctx, args, secrets):
    """(True, результат) або (False, (код, текст)). `ModuleError` модуля з кодом, відомим ядру (`STATUS`),
    проходить як є — лише з вирізаними секретами й ≤300 символів (його код читає API: `bad-folder`…);
    усе інше (невідомий код, `SystemExit`, `ValueError`…) — `module-error`."""
    try:
        return True, f(ctx, *args)
    except KeyboardInterrupt:
        raise
    except ModuleError as e:
        if e.code in STATUS:
            return False, (e.code, _scrub(e._full, secrets)[:MAX_MESSAGE])
        text = f'ModuleError: {e.code}: {e._full}' if e._full else f'ModuleError: {e.code}'
        return False, ('module-error', _scrub(text, secrets)[:MAX_MESSAGE])
    except BaseException as e:  # noqa: BLE001 — SystemExit, GeneratorExit… теж `module-error`
        return False, ('module-error', _scrub(_exc_text(e), secrets)[:MAX_MESSAGE])   # СПЕРШУ вирізати, ПОТІМ різати


def _resolve_fn(module, fn):
    if callable(fn):
        return fn, getattr(fn, '__name__', 'fn')
    if module.status != 'ok':
        raise ModuleError(module.error_code or 'module-error', message=module.error or 'module is not loaded')
    f = module.fn(fn)
    if f is None:
        raise ModuleError('module-error', message=f'module {module.id} has no function {str(fn)[:40]!r}')
    return f, str(fn)


def call(module, fn, ctx, *args, timeout=None):
    """Викликати функцію модуля (`fn` — роль, `'check'` чи сама функція) як `f(ctx, *args)`.
    Результат — як є; будь-який `BaseException` (окрім `KeyboardInterrupt`) → `ModuleError('module-error')`
    з текстом ≤300 символів без значень `ctx['secrets']` і без прикріпленого першоджерела. Виняток:
    `ModuleError` модуля з кодом із `STATUS` (`bad-folder`, `role-taken`…) проходить як є (код і статус
    — з таблиці, текст очищений); невідомий код — `module-error`.
    `timeout` (секунди) — виклик у робочому потоці (він успадковує простір запиту); не вклались —
    `check-timeout` (потік-сирота доживає свій час: `daemon`, його результат викидається)."""
    f, name = _resolve_fn(module, fn)
    secrets = ctx.get('secrets') if isinstance(ctx, dict) else None
    if timeout is None:
        ok, val = _run(f, ctx, args, secrets)
    else:
        box = []
        sid = spaces.request_space_id()

        def work():
            try:
                with spaces.request_space(sid):
                    box.append(_run(f, ctx, args, secrets))
            except BaseException as e:  # noqa: BLE001 — `KeyboardInterrupt` з модуля (його `_run` не ловить)
                box.append((False, ('module-error', type(e).__name__)))
        t = threading.Thread(target=work, name=f'deai-module-{module.id}-{name}', daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive() or not box:
            raise ModuleError('check-timeout', message=f'{module.id}.{name}: no answer in {timeout} s')
        ok, val = box[0]
    if not ok:
        raise ModuleError(val[0], message=val[1])           # поза `except`: без __context__ з секретом
    return val


def _ctx(space, m):
    explicit = space_modules(space)
    settings = resolve_settings(space, m, _entry_state(m, space, explicit)['settings'])
    # секрети читаємо лише в модуля, що їх оголосив: зіпсований `secrets.json` не ламає css-tokens
    secrets = read_secrets(_space_id(space), m.id) if m.secret_keys() else {}
    return {'space': {'id': _space_id(space), 'path': _space_path(space)},
            'settings': settings, 'secrets': secrets}


def module_ctx(space, module):
    """`ctx` для функцій модуля — `{"space": {id, path}, "settings": {…підставлені…}, "secrets": {…лише
    його оголошені…}}`; `module` — `Module` чи id. Саме це отримує `check`; для `serve.py` (`/api/ds-tokens`,
    диспетчер публікації). Може кинути `unknown-module`, `bad-settings`, `space-json-unreadable`,
    `secrets-unreadable`. Статус модуля не перевіряє (це робить `call`)."""
    m = module if isinstance(module, Module) else _need_module(module)
    return _ctx(space, m)


def _remember(space, module_id, res):
    with _STATE_LOCK:
        _LAST_CHECK[(_space_id(space), module_id)] = dict(res)


def last_check(space_id, module_id):
    """Останній результат `check` (копія) або `None`, якщо ще не перевіряли."""
    with _STATE_LOCK:
        res = _LAST_CHECK.get((space_id, module_id))
    return dict(res) if res is not None else None


def check(space, module_id):
    """Результат `check` модуля — `{"ok": bool, "error"?: str, "detail"?: str}` (рядки без секретів,
    ≤300), з `ctx` (налаштування підставлені, секрети ЦЬОГО модуля), тайм-аут `CHECK_TIMEOUT`.
    Останній результат запамʼятовується в `_LAST_CHECK` (для `GET /api/modules`). `ok: false` від
    модуля — звичайний результат; а `module-error`, `check-timeout`, `bad-settings` (обовʼязкове
    налаштування не задане / не те значення) — винятки, і перед викидом вони теж запамʼятовуються як
    `{"ok": false, "error": <код>, "detail": <текст>}`. Для модуля, якого нема чи який не завантажився, і
    для `space-json-unreadable`/`secrets-unreadable` — винятки без запису."""
    m = _need_module(module_id)
    if m.status != 'ok':
        raise ModuleError(m.error_code or 'module-error', message=m.error or '')
    try:
        ctx = _ctx(space, m)
    except ModuleError as e:
        if e.code == 'bad-settings':
            _remember(space, module_id, {'ok': False, 'error': e.code, 'detail': e.message})
        raise
    try:
        res = call(m, 'check', ctx, timeout=CHECK_TIMEOUT)
        if not isinstance(res, dict) or not isinstance(res.get('ok'), bool):
            raise ModuleError('module-error', message='check returned a result without a boolean "ok"')
        out = {'ok': res['ok']}
        for k in ('error', 'detail'):
            if res.get(k) is not None:
                out[k] = _scrub(str(res[k]), ctx['secrets'])[:MAX_MESSAGE]
    except ModuleError as e:
        _remember(space, module_id, {'ok': False, 'error': e.code, 'detail': e.message})
        raise
    _remember(space, module_id, out)
    return dict(out)


# ------------------------------------------------------------------------------ постачальник ролі

def _provider_for(role, space):
    """Модуль, `'legacy'` (лише `publish`) чи `None` — для вже відомого простору `space`.
    Простір з `integrations` і без жодного явно ввімкненого модуля — `'legacy'`/`None` ДО каталогу.
    Без інтеграцій потрібні явні рішення, тож нечитабельний `space.json` — `space-json-unreadable`."""
    integrations = spaces.integrations_for(space)
    if integrations:
        try:
            explicit = space_modules(space)
        except ModuleError:
            explicit = {}                                   # пошкоджений файл не ламає шлях ЛІГА
        if not any(e['enabled'] for e in explicit.values()):
            return 'legacy' if role == 'publish' else None
    else:
        explicit = space_modules(space)
    cat = catalog()
    winners = []
    for mid in sorted(cat):
        m = cat[mid]
        if m.status != 'ok' or role not in m.roles:
            continue
        en, implicit = _enabled_in(m, space, explicit)
        if en:
            winners.append((implicit, mid, m))
    if winners:
        winners.sort(key=lambda w: (w[0], w[1]))        # явно ввімкнений — перед неявним
        return winners[0][2]
    if role == 'publish' and integrations:
        return 'legacy'
    return None


def provider(role, space=None):
    """Хто виконує роль у просторі: `Module`, `'legacy'` (зашитий шлях ЛІГА; лише для `publish`) чи `None`.

    `space` — запис реєстру; не заданий → простір запиту (`spaces.active_space()`). Шар вимкнено чи
    простір запиту НЕ зафіксовано (`request_space_id() is None`: інструменти ЛІГА, воркери, тести без
    ізоляції) → `'legacy'` для `publish`, `None` для інших ролей — БЕЗ читання реєстру, `space.json` і
    каталогу (як `spaces.integrations_on()`). Явно переданий `space` вирішується сам по собі, незалежно
    від стану запиту. Явно чи неявно ввімкнений `ok`-модуль із роллю перемагає; інакше простір з
    `integrations` і роль `publish` → `'legacy'`; інакше `None`.
    ⚠️ НІКОЛИ не кликати під `spaces.WRITE_LOCK`: для простору запиту це `spaces.active_space()`, а той може
    мігрувати реєстр (бере лок), а `catalog()` виконує код модулів. Може кинути `spaces.SpacesError` (реєстр
    не прочитати) і `ModuleError('space-json-unreadable')` (простір без інтеграцій, `space.json` є, але не
    читається) — для списків і опитування є `capabilities()`, яка не кидає."""
    if space is None:
        if not spaces.layer_on() or spaces.request_space_id() is None:
            return 'legacy' if role == 'publish' else None
        space = spaces.active_space()
        if space is None:
            return None
    return _provider_for(role, space)


def _caps_key(space):
    jp = _space_json_path(space)
    return (_space_id(space), spaces.integrations_for(space), _space_path(space),
            _sig(jp) if jp else None, _catalog_sig())


def capabilities(space):
    """`{"publish": id | 'legacy' | None, "tokens": id | None}` для простору `space` (запис реєстру).
    ТОТАЛЬНА: не кидає ніколи. Якщо вирішити роль не вдалось (`ModuleError`, типово нечитабельний
    `space.json`), віддає `{"publish": None, "tokens": None, "error": <код>}` (`publish` — `'legacy'`, коли
    у просторі є інтеграції); без помилки ключа `error` нема. Кеш за (простір, прапорець
    `integrations`, відбиток `space.json`, відбитки `module.json` і `server.py` кожного вбудованого
    модуля); повертає копію. `None`, порожнє чи не-словник замість простору — нічого не вміє."""
    if not isinstance(space, dict) or not space:
        return {'publish': None, 'tokens': None}
    try:
        key = _caps_key(space)                          # ДО обчислення: зміна під час нього — промах, не застарілий хіт
        sid = _space_id(space)
        with _STATE_LOCK:
            hit = _CAPS.get(sid)
        if hit is not None and hit[0] == key:
            return dict(hit[1])
        try:
            caps = {}
            for role in ROLES_CALLED:
                p = _provider_for(role, space)
                caps[role] = p.id if isinstance(p, Module) else p
        except ModuleError as e:
            caps = {'publish': 'legacy' if spaces.integrations_for(space) else None, 'tokens': None,
                    'error': e.code}
        with _STATE_LOCK:
            _CAPS[sid] = (key, dict(caps))
        return dict(caps)
    except Exception:  # noqa: BLE001 — тотальність: збій відбитків/каталогу не ламає опитування
        return {'publish': 'legacy' if space.get('integrations') is True else None, 'tokens': None,
                'error': 'module-error'}
