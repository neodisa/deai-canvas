"""Простори машини — етап 1 Deai Canvas (спека 2026-10-13-deai-spaces-design.md).

Єдиний модуль, що читає й пише реєстр `<DEAI_HOME>/spaces.json`. serve.py, CLI й
скрипти питають тут: який файл задач діє, у якому просторі задача, чи ввімкнені
інтеграції. Читання ключа `current` реєстру живе ЛИШЕ тут (охоронець
`CurrentTaskReadGuard` сканує serve.py).

Контракт помилок — повний набір винятків модуля:
  InputError(code)        (підклас ValueError) валідація в create_space/update_space: 'name-required',
                          'path-*' (див. check_new_path), 'path-unwritable',
                          'task-id-collision: <id>, …', 'space-unavailable: <файл>' (файл задач
                          якогось простору чи «усиновленої» теки є, але не читається — id в ньому
                          невидимі, тож колізій не перевірити). Код — атрибут `.code`, файл — `.path`;
                          сервер відображає відмову за ними, а не за текстом;
  KeyError(id)            невідомий простір (update_space, switch_space);
  SpacesError(code, …)    'spaces-unreadable' (реєстр не прочитати), 'spaces-unwritable'
                          (не записати), 'spaces-off' (шар вимкнено, а викликали запис);
  AmbiguousTask           той самий id задачі у двох просторах;
  NoTask                  просторів нема / у просторі нема поточної задачі;
  IntegrationsOff         зовнішній виклик у просторі без інтеграцій (підклас OSError).

Права: `spaces.json` лишається таким, яким його робить `atomic_write_json` (новий
файл — 0600), тека `<DEAI_HOME>` — 0700. `space.json` і `tasks.json`, які створює
сам модуль, — 0644: це файли простору, вони живуть поруч з роботою користувача.

Простір запиту (`_LOCAL.space`) має ТРИ стани: `None`/не заданий — «простір запиту не
зафіксовано» (інструменти ЛІГА: doctor, registry, roots, тести без ізоляції);
`''` — «запит без простору» (просторів нема); `'<id>'` — саме цей простір."""
import contextlib
import json
import os
import re
import shutil
import threading
import unicodedata

from atomic_io import WRITE_LOCK, atomic_write_json

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
VERSION = 1
SPACE_ID_RE = re.compile(r'[a-z0-9][a-z0-9-]{0,39}')
COLORS = ('space-1', 'space-2', 'space-3', 'space-4', 'space-5', 'space-6')
LEGACY_MARKERS = ('registry', 'gitlab_host_ip', 'gitlab_ssh_key')
SYSTEM_DIRS = ('/System', '/Library', '/usr', '/bin', '/sbin', '/etc', '/private',
               '/var', '/Applications')
#: Скільки найбільше читаємо з JSON-файла (реєстр, tasks.json, space.json).
MAX_JSON_BYTES = 1 << 20
#: Простір, коли шар вимкнено (лише `DC_TASKS_FILE`): поведінка як до просторів.
#: Назовні віддається ЛИШЕ копією (`dict(IMPLICIT)`), щоб ніхто не змінив константу.
IMPLICIT = {'id': 'legacy', 'path': '', 'legacy': True, 'integrations': True}


class SpacesError(Exception):
    """Реєстр не прочитати чи не записати. `code` іде в API (`spaces-unreadable`)."""
    def __init__(self, code, path, why=''):
        super().__init__(f'{code}: {path} {why}'.strip())
        self.code, self.path = code, path


class InputError(ValueError):
    """Відмова валідації `create_space`/`update_space`. Підклас `ValueError` зі ТИМ САМИМ текстом, що
    був у голого `ValueError(code)` (`str(e)` — `code` чи `code: detail`), але код — атрибут:
    сервер розбирає `e.code`/`e.path`, а не `str(e).split(':')`."""
    def __init__(self, code, detail='', path=None):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code, self.detail, self.path = code, detail, path


class NoTask(LookupError):
    """У просторі нема поточної задачі (новий, порожній, застарілий `current`)
    або просторів нема зовсім (`space is None`)."""
    def __init__(self, space=None):
        super().__init__(space or '')
        self.space = space


class AmbiguousTask(LookupError):
    """Той самий id у двох просторах — відмова, а не перший-ліпший."""


class IntegrationsOff(OSError):
    """Зовнішній виклик у просторі без інтеграцій. Підклас OSError: наявні
    `except OSError` навколо мережі деградують чесно (порожньо + помилка);
    маршрути, яким треба 409, ловлять його ПЕРЕД OSError."""


def home():
    return os.path.expanduser(os.environ.get('DEAI_HOME') or '~/.deai')


def registry_path():
    return os.path.join(home(), 'spaces.json')


def layer_on():
    """Таблиця спеки: лише `DC_TASKS_FILE` (усі наявні тести) — шар вимкнено.
    Вимкнений шар не читає й не пише ні реєстр, ні `space.json`: інакше тест із
    самим `DC_TASKS_FILE` мігрував би у справжній `~/.deai`."""
    return not (os.environ.get('DC_TASKS_FILE') and not os.environ.get('DEAI_HOME'))


def _require_layer():
    if not layer_on():
        raise SpacesError('spaces-off', registry_path(),
                          'spaces layer is off (DC_TASKS_FILE without DEAI_HOME)')


def legacy_tasks_file():
    return os.environ.get('DC_TASKS_FILE') or os.path.join(ROOT, 'tasks.json')


def _read_json(path):
    """JSON із файла; не більше `MAX_JSON_BYTES`, надто глибока вкладеність — теж
    `ValueError`, а не `RecursionError` (його не ловлять `except (OSError, ValueError)`)."""
    with open(path, 'rb') as f:
        raw = f.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError(f'{path}: bigger than {MAX_JSON_BYTES} bytes')
    try:
        return json.loads(raw.decode('utf-8'))
    except RecursionError as e:
        raise ValueError(f'{path}: nested too deep') from e


def _empty():
    return {'version': VERSION, 'current': None, 'spaces': []}


def _virtual():
    """Реєстр вимкненого шару: один неявний простір (копія, не константа)."""
    return {'version': VERSION, 'current': IMPLICIT['id'], 'spaces': [dict(IMPLICIT)]}


def _usable_path_text(p):
    """Рядок можна віддати системним викликам як шлях: без NUL (`ValueError: embedded null`) і
    кодований як імʼя файла (`os.fsencode`: самотній сурогат — `UnicodeEncodeError` у `realpath`).
    Рукописний JSON обидва приймає, а `_real`/`os.path.realpath` на них кидає посеред відповіді."""
    if '\0' in p:
        return False
    try:
        os.fsencode(p)
    except UnicodeEncodeError:
        return False
    return True


def _validate(reg, path):
    ok = (isinstance(reg, dict) and reg.get('version') == VERSION
          and isinstance(reg.get('spaces'), list))
    if ok:
        seen = set()
        for s in reg['spaces']:
            if not (isinstance(s, dict)
                    and isinstance(s.get('id'), str) and SPACE_ID_RE.fullmatch(s['id'])
                    and isinstance(s.get('path'), str) and os.path.isabs(s['path'])
                    and _usable_path_text(s['path'])
                    and s['id'] not in seen
                    # прапорці — лише справжні bool: вимикач закривається, а не «усе, що truthy»
                    and all(isinstance(s[k], bool) for k in ('integrations', 'legacy') if k in s)):
                ok = False
                break
            seen.add(s['id'])
    if not ok:
        raise SpacesError('spaces-unreadable', path, 'bad shape or version')
    return reg


def _read_registry():
    p = registry_path()
    try:
        return _validate(_read_json(p), p)
    except FileNotFoundError:
        return _empty()
    except (OSError, ValueError) as e:
        raise SpacesError('spaces-unreadable', p, str(e)[:120]) from e


def read_registry():
    """Реєстр ЛИШЕ для читання: без міграції й без запису. Шар вимкнено — віртуальний."""
    if not layer_on():
        return _virtual()
    return _read_registry()


def _write_locked(reg):
    """Запис реєстру; викликач ТРИМАЄ `WRITE_LOCK` (він не реентерабельний)."""
    _require_layer()            # останній заслін: вимкнений шар ніколи не пише в ~/.deai
    p = registry_path()
    try:
        os.makedirs(home(), mode=0o700, exist_ok=True)
        if os.path.isfile(p):
            shutil.copy2(p, p + '.bak')
        atomic_write_json(p, reg)
    except OSError as e:
        raise SpacesError('spaces-unwritable', p, str(e)[:120]) from e


def slug(name):
    s = re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')
    return s[:40].strip('-')


def unique_id(base, taken):
    if base and SPACE_ID_RE.fullmatch(base):
        if base not in taken:
            return base
        n = 2
        while f'{base[:36]}-{n}' in taken:
            n += 1
        return f'{base[:36]}-{n}'
    n = 1
    while f'space-{n}' in taken:
        n += 1
    return f'space-{n}'


def _nfc(s):
    return unicodedata.normalize('NFC', s)


def _abs_paths(values):
    out = []
    for v in values:
        if isinstance(v, str) and v:
            v = os.path.expanduser(v)
            if os.path.isabs(v):
                out.append(os.path.normpath(v))
    return out


def _under(p, q):
    """`p` == `q` або всередині `q`. Порівняння в NFC: macOS віддає імена в NFD."""
    p, q = _nfc(p), _nfc(q)
    return p == q or p.startswith(q.rstrip(os.sep) + os.sep)


def _text(p):
    """Нормалізований текстовий шлях з ОДНИМ провідним `/` (normpath лишає `//`)."""
    return os.sep + os.path.normpath(p).lstrip(os.sep)


def _real(p):
    """`realpath` (симлінки розкрито) з одним провідним `/`."""
    return os.sep + os.path.realpath(p).lstrip(os.sep)


def _acceptable(p):
    h = os.path.normpath(os.path.expanduser('~'))
    if not p or p == os.sep or _under(h, p):          # корінь, домівка чи її предок
        return False
    return not (_under(p, ROOT) or _under(ROOT, p))   # не тека інструмента й не над нею


def legacy_path(cfg):
    """`path` простору `legacy` з конфіга старого файла задач: спільний предок `dirname(dir)`
    усіх задач і коренів (`design_work_root(s)`), якщо він прийнятний; інакше сам
    `design_work_root`; останній запас — `~/deai-work/main`.

    ⚠️ Запас — ДОЧІРНЯ тека, не сама `~/deai-work`: та лежить над типовою текою нового простору
    `~/deai-work/<slug>`, і перший же «Новий простір» упирався б у `path-overlap`. Запас
    вмикається, лише коли жоден з двох варіантів вище не прийнятний (типово — старий файл без
    задач і коренів); на машині власника спільний предок є — `~/Liga`, міграція не змінилась."""
    tasks = cfg.get('tasks') if isinstance(cfg.get('tasks'), dict) else {}
    roots = cfg.get('design_work_roots') if isinstance(cfg.get('design_work_roots'), dict) else {}
    dirs = _abs_paths(t.get('dir') for t in tasks.values() if isinstance(t, dict))
    cands = [os.path.dirname(d) for d in dirs] + _abs_paths(
        [cfg.get('design_work_root'), *roots.values()])
    try:
        c = os.path.commonpath(cands) if cands else ''
    except ValueError:
        c = ''
    if _acceptable(c):
        return c
    for r in _abs_paths([cfg.get('design_work_root')]):
        if _acceptable(r):
            return r
    return os.path.join(os.path.expanduser('~'), 'deai-work', 'main')


def has_markers(cfg):
    if any(k in cfg for k in LEGACY_MARKERS):
        return True
    tasks = cfg.get('tasks') if isinstance(cfg.get('tasks'), dict) else {}
    return any(isinstance(t, dict) and t.get('gitlab') for t in tasks.values())


def load_registry():
    """Реєстр + міграція старого файла. Пише на диск ЛИШЕ щоб додати простір
    `legacy`; «нічого нема» — віртуальний порожній реєстр (блокер №1 ревʼю: checkout
    без tasks.json не сміє «закрити» міграцію для справжнього канваса).
    Шар вимкнено — віртуальний реєстр із одним неявним простором, диска не торкаємось.

    ⚠️ НІКОЛИ не викликати, тримаючи `WRITE_LOCK`: перша міграція бере його сама, а лок
    не реентерабельний — вийде дедлок. Хто пише реєстр під локом, спершу кличе
    `load_registry()` ПОЗА ним, а під локом перечитує `_read_registry()`."""
    if not layer_on():
        return _virtual()
    reg = _read_registry()
    if any(s.get('legacy') for s in reg['spaces']):
        return reg
    lf = legacy_tasks_file()
    if not os.path.isfile(lf):
        return reg
    try:
        cfg = _read_json(lf)
    except (OSError, ValueError):
        return reg              # битий старий файл не мігруємо; про нього кажуть `legacy_unreadable` і serve
    if not isinstance(cfg, dict):
        return reg
    with WRITE_LOCK:
        reg = _read_registry()  # паралельний потік міг уже мігрувати
        if any(s.get('legacy') for s in reg['spaces']):
            return reg
        path = legacy_path(cfg)
        entry = {'id': unique_id(slug(os.path.basename(path)), {s['id'] for s in reg['spaces']}),
                 'path': path, 'legacy': True, 'integrations': has_markers(cfg)}
        reg['spaces'].insert(0, entry)
        if not reg.get('current'):
            reg['current'] = entry['id']
        _write_locked(reg)
    return reg


def current_id():
    """`current` реєстру (id простору або `None`); шар вимкнено — `'legacy'`.
    ⚠️ Кличе `load_registry()`, тобто МОЖЕ мігрувати (писати на диск). Чистий читач — `read_registry()`."""
    return load_registry().get('current')


def tasks_file(sp):
    return legacy_tasks_file() if sp.get('legacy') else os.path.join(sp['path'], 'tasks.json')


def _is_implicit(sp):
    return sp.get('id') == IMPLICIT['id'] and not sp.get('path')


def space_meta(sp):
    """(назва, колір) з `space.json`; нема чи битий — назва теки й `space-1`.
    Порожній шлях (неявний простір) — `(id, space-1)` без звернення до диска."""
    if not sp.get('path'):
        return sp['id'], COLORS[0]
    name = os.path.basename(sp.get('path', '').rstrip(os.sep)) or sp['id']
    color = COLORS[0]
    try:
        m = _read_json(os.path.join(sp['path'], 'space.json'))
    except (OSError, ValueError, KeyError):
        m = None
    if isinstance(m, dict):
        if isinstance(m.get('name'), str) and m['name'].strip():
            name = m['name'].strip()[:60]
        if m.get('color') in COLORS:
            color = m['color']
    return name, color


def describe(sp):
    """Простір для API: без внутрішніх полів, з назвою й кольором. Неявний простір
    (шар вимкнено) і `None` — `None`: serve віддає `space: null`."""
    if sp is None or _is_implicit(sp):
        return None
    name, color = space_meta(sp)
    return {'id': sp['id'], 'name': name, 'color': color, 'path': sp.get('path', ''),
            'legacy': bool(sp.get('legacy')), 'integrations': bool(sp.get('integrations'))}


_LOCAL = threading.local()


def set_request_space(space_id):
    _LOCAL.space = space_id


def clear_request_space():
    _LOCAL.space = None


def request_space_id():
    """Сире значення простору запиту: `None` / `''` / `'<id>'` (див. докстрінг модуля)."""
    return getattr(_LOCAL, 'space', None)


@contextlib.contextmanager
def request_space(sid):
    """Зафіксувати простір запиту на блок і повернути попереднє значення."""
    prev = request_space_id()
    _LOCAL.space = sid
    try:
        yield
    finally:
        _LOCAL.space = prev


def active_space(reg=None):
    """Простір запиту (`threading.local`) або поточний машини; `None` — просторів нема
    (чи запит прямо сказав «без простору», `''`). Неявний — завжди КОПІЄЮ."""
    if not layer_on():
        return dict(IMPLICIT)
    req = request_space_id()
    if req == '':
        return None
    reg = reg or load_registry()
    want = req or reg.get('current')
    for sp in reg['spaces']:
        if sp['id'] == want:
            return sp
    return reg['spaces'][0] if reg['spaces'] and not req else None


def effective_space():
    """Простір запиту для ядра ролей (4d-2, шов «шар вимкнено»): шар вимкнено чи простір запиту не зафіксовано → `dict(IMPLICIT)`
    БЕЗ читання реєстру; інакше `active_space()` (може кинути `SpacesError`; `None` — простору нема). ⛔ Не плутати з
    контекстним менеджером `request_space(sid)`, що лише фіксує простір запиту."""
    if not layer_on() or request_space_id() is None:
        return dict(IMPLICIT)
    return active_space()


def active_tasks_file():
    sp = active_space()
    if sp is None:
        raise NoTask(None)
    return tasks_file(sp)


def integrations_for(sp):
    """Вимикач закривається: лише рівно `True` вмикає (не `'yes'`, не `1`)."""
    return bool(sp) and sp.get('integrations') is True


def integrations_on():
    """Чи ввімкнені зовнішні інтеграції для ЦЬОГО запиту.
    Шар вимкнено → так. Простір запиту не зафіксовано (`None`: інструменти ЛІГА) → так,
    і реєстру ми НЕ читаємо взагалі. `''` (запит без простору) → ні. `'<id>'` → прапорець
    цього простору (невідомий id → ні).

    ⚠️ Простір запиту живе в `threading.local`: потік, який запустив сервер (фоновий
    воркер, таймер, опитування), його НЕ успадковує — тож без `request_space(...)` такий
    воркер працює з УВІМКНЕНИМИ інтеграціями. Хто породжує воркери, мусить огорнути
    їхнє тіло в `with request_space(<id>)` (або `request_space('')`)."""
    if not layer_on():
        return True
    req = request_space_id()
    if req is None:
        return True
    if req == '':
        return False
    for sp in load_registry()['spaces']:
        if sp['id'] == req:
            return integrations_for(sp)
    return False


def require_integrations():
    if not integrations_on():
        raise IntegrationsOff('integrations-off')


def _space_tasks(sp):
    try:
        cfg = _read_json(tasks_file(sp))
    except (OSError, ValueError):
        return {}
    t = cfg.get('tasks') if isinstance(cfg, dict) else None
    return t if isinstance(t, dict) else {}


def valid_tasks_cfg(cfg):
    """Чи файл задач має форму, з якою працює код: обʼєкт, де `tasks` — або нема, або обʼєкт
    з обʼєктів-задач. Усе інше (`[]`, `{"tasks": []}`, `{"tasks": {"x": 5}}`) роняло б обробники
    `AttributeError`-ом посеред відповіді, тож `serve.load_tasks()` і перевірки унікальності id
    рахують такий файл НЕДОСТУПНИМ, а не порожнім."""
    if not isinstance(cfg, dict):
        return False
    tasks = cfg.get('tasks', {})
    return isinstance(tasks, dict) and all(isinstance(t, dict) for t in tasks.values())


def _task_file_broken(path):
    """Файл задач ІСНУЄ, але не читається чи має не ту форму (`valid_tasks_cfg`). Нема файла —
    не «битий» (checkout без старого файла, простір без `tasks.json`: це `available: false`)."""
    if not os.path.isfile(path):
        return False
    try:
        return not valid_tasks_cfg(_read_json(path))
    except (OSError, ValueError):
        return True


def legacy_unreadable(reg=None):
    """Шлях старого файла задач, коли він ІСНУЄ, але не читається (обрізаний JSON, не обʼєкт,
    понад `MAX_JSON_BYTES`, нема прав), а простору `legacy` у реєстрі `reg` ще нема — міграція
    такого файла не відбулась. Інакше `None` (шар вимкнено, файла нема, він читається, простір
    уже мігровано: тоді нечитабельність — справа `load_tasks()`).

    «Не читається» — як у `_task_file_broken`: не прочитати, не обʼєкт чи погана форма `tasks`.
    `load_registry` не мігрує перші два; обʼєкт із поганою формою `tasks` мігрує, і після цього
    простір `legacy` у реєстрі є — функція мовчить, а відмову дає `load_tasks()` (503).

    Навіщо окремо: без цього машина з порожнім `DEAI_HOME` і зіпсованим `tasks.json` виглядає як
    чиста — «просторів нема», привітання, 404 `no-task`, — хоча в файлі лежать усі задачі людини.
    Рукописний `tasks.json` дизайнери правлять самі (ONBOARDING), тож це не екзотика. Полагодили
    файл — наступне читання мігрує як звичайно, пам'ятати нічого не треба.

    `reg` — реєстр, який уже в руках (довідка `listing()`, `unreadable_task_files`); без нього
    береться `read_registry()` (БЕЗ міграції і без запису: цей виклик не змінює диск)."""
    if not layer_on():
        return None
    if reg is None:
        reg = read_registry()
    if any(s.get('legacy') for s in reg['spaces']):
        return None
    lf = legacy_tasks_file()
    return lf if _task_file_broken(lf) else None


def unreadable_task_files(reg):
    """Файли задач просторів `reg`, які є, але не читаються (`_task_file_broken`), у порядку реєстру,
    плюс старий файл, який не мігровано через його нечитабельність (`legacy_unreadable`).
    `_space_tasks` такі файли мовчки вважає порожніми — для ПОШУКУ це правильно (одна біда не
    ховає решту), для СТВОРЕННЯ id — ні: id, що лежить у нечитабельному файлі, невидимий для
    перевірки унікальності."""
    out = [tf for tf in (tasks_file(sp) for sp in reg['spaces']) if _task_file_broken(tf)]
    legacy = legacy_unreadable(reg)
    return [*out, legacy] if legacy else out


def task_count(sp):
    return len(_space_tasks(sp))


def space_current_task(sid):
    """`current` із `tasks.json` простору `sid`, якщо така задача там є; інакше `None`
    (нема файла, битий, нема ключа, невідомий простір).
    ⚠️ Шукає простір через `load_registry()`, тобто МОЖЕ мігрувати (писати на диск).
    Чистий читач, який не пише нічого, бере `read_registry()` і сам шукає простір."""
    sp = next((s for s in load_registry()['spaces'] if s['id'] == sid), None)
    if sp is None:
        return None
    try:
        cfg = _read_json(tasks_file(sp))
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict) or not isinstance(cfg.get('tasks'), dict):
        return None
    cur = cfg.get('current')
    return cur if isinstance(cur, str) and cur in cfg['tasks'] else None


def listing():
    """Усі простори для `GET /api/spaces`: `{'current', 'spaces': [describe + tasks + available]}`.

    `tasks` — скільки задач у файлі простору (нема/битий — 0), `available` — чи файл задач
    лежить на диску (`legacy` без старого файла цього checkout-а — `False`; читається
    він чи ні, каже `/api/task`: 503 `space-unavailable`). Реєстр береться ОДИН раз, тож
    `current` і список — з одного знімка.

    `legacy_error: {path, code}` — ЛИШЕ коли старий файл задач є, але не читається, і простору
    `legacy` у реєстрі нема (`legacy_unreadable`): без нього порожній список читався б як чиста
    машина. Ключа нема, коли все гаразд.

    Шар вимкнено → `{'current': None, 'spaces': [], 'off': True}`: неявний простір — не простір
    для UI (`describe` його ховає), а без `off` порожній список читався б як «просторів нема»
    і UI показав би привітання замість задач.

    ⚠️ Може мігрувати (через `load_registry()`): ніколи не кликати під `WRITE_LOCK`."""
    if not layer_on():
        return {'current': None, 'spaces': [], 'off': True}
    reg = load_registry()
    out = {'current': reg.get('current'),
           'spaces': [{**describe(sp), 'tasks': task_count(sp),
                       'available': os.path.isfile(tasks_file(sp))}
                      for sp in reg['spaces']]}
    bad = legacy_unreadable(reg)
    if bad:
        # Старий файл є, але не читається, і простору з нього нема: `spaces: []` тут НЕ «чиста
        # машина». UI за цим ключем показує смугу помилки, а не привітання (`needsWelcome`).
        out['legacy_error'] = {'path': bad, 'code': 'space-unavailable'}
    return out


def find_task(tid):
    """Простір, де є задача `tid`; `None` — ніде. Дубль → `AmbiguousTask`."""
    if not isinstance(tid, str):
        return None
    if not layer_on():
        return dict(IMPLICIT) if tid in _space_tasks(IMPLICIT) else None
    reg = load_registry()
    hits = task_ids_by_space(reg).get(tid, [])
    if len(hits) > 1:
        raise AmbiguousTask(tid)
    return next(sp for sp in reg['spaces'] if sp['id'] == hits[0]) if hits else None


def task_ids_by_space(reg):
    """`{id задачі: [id просторів реєстру `reg`, де вона є]}` у порядку реєстру. Читає ТАК САМО, як
    `find_task` (той самий `_space_tasks`: файл, що не читається, — порожній; такі файли показує
    `unreadable_task_files`). Список довшим за один елемент — дубль між просторами. Чистий читач:
    нічого не мігрує й не пише, тож годиться для доктора."""
    out = {}
    for sp in reg['spaces']:
        for tid in _space_tasks(sp):
            out.setdefault(tid, []).append(sp['id'])
    return out


def other_spaces_have_tasks(exclude=None):
    """Чи є задачі в просторах, КРІМ `exclude` (id простору або `None`). Шар вимкнено — `False`
    (там один неявний простір, «інших» нема); реєстр не прочитати — теж `False` (підказка CLI
    не мусить кидати). Чистий читач: нічого не мігрує й не пише."""
    if not layer_on():
        return False
    try:
        reg = read_registry()
    except SpacesError:
        return False
    return any(sp['id'] != exclude and task_count(sp) for sp in reg['spaces'])


def no_task_message(e):
    """Текст для CLI (`bin/state.py`, `bin/inbox.py`) на `NoTask`. У поточному просторі задач нема,
    а в інших є — «створи простір» тут би брехало (простір є, і задачі є): кажемо про `--task` і
    перемикання. Задач нема ніде — як було. `e.space` — простір запиту (`None` — просторів нема)."""
    if e.space and other_spaces_have_tasks(e.space):
        return ('у поточному просторі задач нема; є в інших — вкажи `--task <id>` '
                'або перемкнись на простір із задачами (канвас: ⌘K)')
    return 'задач немає — створи простір і задачу в канвасі'


def all_task_dirs(reg):
    out = []
    for sp in reg['spaces']:
        out += _abs_paths(t.get('dir') for t in _space_tasks(sp).values() if isinstance(t, dict))
    return out


def _home_system(p, h):
    """Усередині домівки: `Library` (будь-який регістр) чи прихована тека."""
    if not _under(p, h) or _nfc(p) == _nfc(h):
        return False
    first = os.path.relpath(_nfc(p), _nfc(h)).split(os.sep)[0]   # NFC: macOS віддає NFD
    return first.lower() == 'library' or first.startswith('.')


def _same_dir(a, b):
    """`a` і `b` — одна тека на диску. `os.path.samefile`, коли обидві є: файлова система сама знає, що
    `…/CASEa` і `…/caseA` на macOS (APFS без урахування регістру) — одна тека, чого текстове порівняння
    не бачить. Нема котроїсь (чи `OSError`) — `False`: тоді вирішує текстове порівняння викликача."""
    try:
        return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)
    except OSError:
        return False


def _fs_under(p, q):
    """`p` == `q` або всередині `q` — за ФАЙЛОВОЮ системою: хтось із предків `p` (їх теки, що вже є на
    диску) — та сама тека, що `q`. Підтека, якої ще нема (`…/CASEA/sub`), так знаходить зареєстровану
    `…/caseA`, а `_under` бачив би лише різні рядки."""
    if not os.path.exists(q):
        return False
    a = p
    while True:
        if _same_dir(a, q):
            return True
        parent = os.path.dirname(a)
        if parent == a:
            return False
        a = parent


def _is_registered(pt, pr, reg):
    """Тека (текст `pt`, `realpath` `pr`) вже є шляхом простору реєстру: збіг тексту чи `realpath` у NFC
    АБО та сама тека за файловою системою (`_same_dir`). Простори без `path` (неявний) пропускаються."""
    for sp in reg['spaces']:
        if not sp.get('path'):
            continue
        if any(_nfc(a) == _nfc(b) for a, b in ((pt, _text(sp['path'])), (pr, _real(sp['path'])))):
            return True
        if _same_dir(pt, sp['path']):
            return True
    return False


def check_new_path(path, reg, task_dirs):
    """(нормалізований текстовий шлях, None) або (None, код причини).

    Порівняння — за `realpath` (симлінк у домівці на `~/.ssh` не обхід) і в NFC, а для збігу й
    перекриття з наявними просторами та текою задач — ще й ФАЙЛОВОЮ системою (`samefile`, предки):
    варіант регістру зареєстрованої теки на macOS — та сама тека (`path-registered`; його підтека чи
    її предок — `path-overlap`), а текст бачив би «іншу». Теки на диску нема — лишається текст.
    Правила домівки йдуть РАНІШЕ за системні теки (тимчасова домівка macOS живе
    під `/var/folders/…`). Коди: path-not-absolute, path-too-broad, path-system,
    path-tool, path-not-dir, path-registered, path-overlap."""
    raw = str(path or '').strip()
    if not raw or not _usable_path_text(raw):
        return None, 'path-not-absolute'
    p = os.path.expanduser(raw)
    if not os.path.isabs(p):
        return None, 'path-not-absolute'
    pt, pr = _text(p), _real(p)
    h = os.path.expanduser('~')
    ht, hr = _text(h), _real(h)
    if os.sep in (pt, pr) or _under(ht, pt) or _under(hr, pr):
        return None, 'path-too-broad'
    in_home = _under(pr, hr)
    if _home_system(pt, ht) or _home_system(pr, hr):
        return None, 'path-system'
    if not in_home:
        sysdirs = {*SYSTEM_DIRS, *(os.path.realpath(d) for d in SYSTEM_DIRS)}
        probes = (pr,) if _under(pt, ht) else (pt, pr)
        if any(_under(x, d) for x in probes for d in sysdirs):
            return None, 'path-system'
    tool = (_text(ROOT), _real(ROOT))
    if any(_under(x, r) or _under(r, x) for x in (pt, pr) for r in tool):
        return None, 'path-tool'
    if os.path.exists(pr) and not os.path.isdir(pr):
        return None, 'path-not-dir'
    for sp in reg['spaces']:
        if _is_registered(pt, pr, {'spaces': [sp]}):
            return None, 'path-registered'
        for a, b in ((pt, _text(sp['path'])), (pr, _real(sp['path']))):
            if _under(a, b) or _under(b, a):
                return None, 'path-overlap'
        if sp.get('path') and (_fs_under(pt, sp['path']) or _fs_under(sp['path'], pt)):
            return None, 'path-overlap'
    for d in task_dirs:
        for a, b in ((pt, _text(d)), (pr, _real(d))):
            if _under(a, b) or _under(b, a):
                return None, 'path-overlap'
        if _fs_under(pt, d) or _fs_under(d, pt):
            return None, 'path-overlap'
    return pt, None


def peek(path):
    """Що лежить у теці майбутнього простору (для діалогу). Лише читання;
    відносний чи порожній шлях — без звернення до диска.

    `registered: true` — тека вже шлях простору реєстру (тим самим порівнянням, що `path-registered`
    у `check_new_path`: текст/`realpath`/NFC і та сама тека за файловою системою, тобто й варіант
    регістру на macOS): діалог не має видавати її за «знайдений» простір, а `space-new` на неї відмовить.
    Ключа нема, коли теки в реєстрі нема, а також коли реєстр не прочитати чи порівняння
    спіткнулося об шлях (`peek` не кидає: «чи зареєстрована» тоді невідомо) або шар вимкнено (є лише неявний простір без шляху)."""
    raw = str(path or '')
    p = os.path.expanduser(raw)
    if not raw.strip() or not _usable_path_text(raw) or not os.path.isabs(p):
        return {'path': raw, 'exists': False, 'error': 'path-not-absolute'}
    p = _text(p)
    out = {'path': p, 'exists': os.path.isdir(p)}
    try:
        if _is_registered(p, _real(p), read_registry()):
            out['registered'] = True
    except (SpacesError, ValueError, OSError):
        # `SpacesError` — реєстр не прочитати; `ValueError`/`OSError` (зокрема `UnicodeEncodeError`) —
        # шлях, на якому спотикається `realpath`/`stat`. `peek` не кидає: «чи зареєстрована» невідомо.
        pass
    if os.path.isfile(os.path.join(p, 'space.json')):
        out['name'], out['color'] = space_meta({'id': '', 'path': p})
    if os.path.isfile(os.path.join(p, 'tasks.json')):
        out['tasks'] = task_count({'path': p})
    return out


def _write_public(path, data):
    """JSON-файл простору: новий — 0644 (`atomic_write_json` лишив би 0600)."""
    fresh = not os.path.exists(path)
    atomic_write_json(path, data)
    if fresh:
        os.chmod(path, 0o644)


def create_space(name, color, path):
    """Створити простір: тека, `space.json`, `tasks.json`, запис у реєстрі, `current`.
    Перевірка шляху, колізій id й запис реєстру — ПІД одним `WRITE_LOCK` (два паралельні
    запити з одним шляхом не створять два простори). Помилки див. докстрінг модуля."""
    _require_layer()
    name = str(name or '').strip()[:60]
    if not name:
        raise InputError('name-required')
    if color not in COLORS:
        color = COLORS[0]
    load_registry()             # міграція старого файла — ПОЗА локом (вона бере його сама)
    with WRITE_LOCK:
        reg = _read_registry()
        p, why = check_new_path(path, reg, all_task_dirs(reg))
        if why:
            raise InputError(why)
        # Файл, що є, але не читається, не «порожній»: id в ньому (чужому чи «усиновленому»)
        # невидимі, а колізію не побачити — тож відмова з назвою файла, а не дубль у реєстрі.
        broken = unreadable_task_files({'spaces': [*reg['spaces'], {'id': '', 'path': p}]})
        if broken:
            raise InputError('space-unavailable', broken[0], path=broken[0])
        adopt = _space_tasks({'path': p})
        taken = {t for sp in reg['spaces'] for t in _space_tasks(sp)}
        clash = sorted(set(adopt) & taken)
        if clash:
            raise InputError('task-id-collision', ', '.join(clash))
        try:
            os.makedirs(p, exist_ok=True)
            if not os.path.exists(os.path.join(p, 'space.json')):
                _write_public(os.path.join(p, 'space.json'), {'name': name, 'color': color})
            if not os.path.exists(os.path.join(p, 'tasks.json')):
                _write_public(os.path.join(p, 'tasks.json'), {'design_work_root': p, 'tasks': {}})
        except (OSError, ValueError) as e:
            raise InputError('path-unwritable') from e
        sid = unique_id(slug(name), {s['id'] for s in reg['spaces']})
        reg['spaces'].append({'id': sid, 'path': p, 'legacy': False, 'integrations': False})
        reg['current'] = sid
        _write_locked(reg)
    return sid


def _space(reg, sid):
    for sp in reg['spaces']:
        if sp['id'] == sid:
            return sp
    raise KeyError(sid)


def update_space(sid, name=None, color=None):
    """Змінити назву/колір у `space.json` простору; решту ключів файла зберігає.
    Повертає `{'name', 'color'}`. Порожня назва — `InputError('name-required')`."""
    _require_layer()
    if name is not None and not str(name).strip():
        raise InputError('name-required')
    sp = _space(load_registry(), sid)   # ПОЗА локом: load_registry може мігрувати
    path = os.path.join(sp['path'], 'space.json')
    with WRITE_LOCK:
        try:
            old = _read_json(path)
        except (OSError, ValueError):
            old = None
        out = dict(old) if isinstance(old, dict) else {}
        cur_name, cur_color = space_meta(sp)
        out['name'] = str(name).strip()[:60] if name is not None else cur_name
        out['color'] = color if color in COLORS else cur_color
        try:
            # Тека простору може ще не існувати: застарілий простір із запасним
            # шляхом (`~/deai-work/main`) створюється міграцією запису, не теки.
            os.makedirs(sp['path'], exist_ok=True)
            _write_public(path, out)
        except OSError as e:
            raise InputError('path-unwritable') from e
    return {'name': out['name'], 'color': out['color']}


def switch_space(sid):
    """Зробити простір поточним. Шар вимкнено — НАВМИСНИЙ no-op (і для невідомого id):
    поточного простору там нема, є лише неявний."""
    if not layer_on():
        return
    with WRITE_LOCK:
        reg = _read_registry()
        _space(reg, sid)
        if reg.get('current') != sid:
            reg['current'] = sid
            _write_locked(reg)


def default_new_task_space():
    """Простір для `task-new` без `space`: перший запис із `legacy: true` (простір ЛІГА), інакше поточний."""
    if not layer_on():
        return dict(IMPLICIT)
    reg = load_registry()
    for sp in reg['spaces']:
        if sp.get('legacy') is True:
            return sp
    return active_space(reg)
