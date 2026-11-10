"""Вбудовані модулі Deai Canvas — каркас етапу 2а (спека 2026-10-14-modules-2a-design.md, ревізія 2).

Модуль = тека `app/modules/<id>/` з `module.json` (маніфест) і `server.py` (функції ролей).
Роль = інтерфейс, який кличе ядро: `publish`, `tokens`, `comments` (2b-2), `vcs` (4a: синк макетів із git);
`dashboard` (4c-1: командний дашборд — читання рядків команди й пуш карток проєктів), `tracker` (4c-2: статуси задач у трекері — `statuses(ctx, keys)`); `notify` (4c-3: сповіщення Teams — стан і перемикання тиші каналу, `mute_state(ctx)`, `mute_set(ctx, channel, muted, by)`). Зарезервованих ролей не лишилось. Один постачальник на роль у просторі.
Роль `comments` — дві половини: браузерний адаптер сховища CommentLayer (`client` у маніфесті — файли теки
модуля, їх роздає `GET /api/module-client/<id>/<файл>`; адаптер СВОГО модуля простору — зі знімка довіри,
`GET /api/module-client/<простір>/<id>/<файл>`) і серверні `client_config`/`list`/`resolve`
(`comments_client`, `channel_for`; налаштування `secret` з `"public": true` дозволено показувати сторінкам).
Тестовий шов: змінна оточення `DEAI_EXTRA_MODULES` — друга тека вбудованих модулів (`extra_dir`), якої каталог
додає до `app/modules`; `id`, що вже є серед вбудованих, програє (`shadowed`). Лише для тестів і живих перевірок:
оточення контролює людина, що запускає сервер, тож модулі звідти вважаються вбудованими.
Свої модулі простору (етап 3c): `catalog(space)` додає до вбудованих модулі з `<простір>/modules/<id>/`
(`own_modules`, `own_notes`). Довірений модуль (запис у `<DEAI_HOME>/trust.json`, знімок у `<DEAI_HOME>/trusted/<хеш>/`,
див. `module_trust`) вантажиться ЗІ ЗНІМКА, а верхній рівень його `server.py` — у потоці-демоні з тайм-аутом
`LOAD_TIMEOUT`; недовірений — лише з маніфесту (`status='untrusted'`, а з `refused` без знімка — `'error'`;
`error_code='module-untrusted'`), його код не виконується НІКОЛИ. Коди ядра для них — `CORE_STATUS` (поза `STATUS`:
модуль не може кинути їх від свого імені). Функції з id модуля (`check`, `validate_settings`, `write_secrets`…) беруть
`space`, щоб знайти свій модуль; без нього — лише вбудовані.
Роль «на папері»: свій модуль, ЯВНО ввімкнений у `space.json`, тримає свої ролі й тоді, коли тут не працює (недовірений,
збій завантаження, тека не приїхала з git): `_holders`/`_role_conflict` рахують його власником (ролі — з маніфесту й із
запису `roles` у `space.json`, їх пише вмикання свого модуля), `_provider_for` кидає `module-untrusted`/`module-error` без
запасного шляху (`_paper_failure`), а `capabilities` дає такій ролі `None` БЕЗ ключа `error`. Довіра: `trust_view`,
`grant_trust` (системне вікно ОС — останнє слово людини), `revoke_trust`; кеш знімків скидає `forget_own` (покоління `_OWN_GEN`).
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
    віддає `None` (ролей нема) НЕ читаючи ні реєстр, ні `space.json`, ні каталог. Запасного постачальника нема (4d-4b): роль без явного ввімкненого
    запису — `None`; нечитабельний `space.json` — `ModuleError('space-json-unreadable', 409)` для КОЖНОЇ ролі.
    Роль `comments` (приватність): явно ввімкнений запис, що ВІВ коментарі й загубився
    (його маніфест оголошує `comments`; або маніфест не розібрано, а id не належить вбудованому модулю іншої ролі; або
    це відсутній вбудований модуль коментарів — точне правило в `_enabled_module_is_lost`), — `module-error`
    (`COMMENTS_MODULE_BROKEN`). ВИДИМІСТЬ: тиша
    «коментарів немає» без причини була б брехнею: сторінка канваса показує примітку, `comment-config` віддає код,
    `capabilities()` у всіх цих випадках — `comments: None` + `error`; простір без жодного запису про коментарі — просто
    `None` без помилки.
  * `capabilities()` — ТОТАЛЬНА (опитування, списки просторів): ніколи не кидає, а помилку кладе в
    ключ `error` (див. функцію). Запасного постачальника нема (4d-4b): роль без явного ввімкненого запису — `None`.
  * Правила теки публікації живуть тут (`published_root`, `folder_ok`, `folder_inputs`), щоб їх ділили
    `serve.py` і модуль; код модулів НЕ імпортує ні `serve`, ні `deai_modules` (їхній список імпортів —
    явний stdlib-allowlist у тестах): правило теки й клас `ModuleError` модуль отримує в `ctx`
    (`ctx['folder_ok']`, `ctx['ModuleError']`). `ctx` модуля для `serve.py` — `module_ctx()`.
  * Межі `exec`-завантаження (модуль — не в `sys.modules`): `@dataclass` разом з `from __future__ import
    annotations` падає (`dataclasses` шукає `sys.modules[cls.__module__]`), класи з `exec`-модулів не
    піклюються (`pickle`, `multiprocessing` у режимі spawn), `importlib.reload` не працює. Модулям вистачає
    функцій і простих структур.
  * Вимкнений шар просторів (лише `DC_TASKS_FILE`) нічого не пише: `write_module_state` і
    `write_secrets` → `spaces-off`, `read_secrets` → `{}` без звернення до диска.
"""
import json
import math
import os
import re
import shutil
import stat
import threading
import time
import types
from collections import OrderedDict
from urllib.parse import quote, unquote, unquote_plus

import isolation
import module_trust
import spaces
from atomic_io import atomic_write_json

APP = os.path.dirname(os.path.abspath(__file__))

API_VERSION = 1
ROLES_CALLED = ('publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker', 'notify')
#: Зарезервованих імен ролей не лишилось (4c-3: `notify` — остання — стала викликаною). Порожній кортеж лишено, щоб
#: `ROLES_CALLED + ROLES_RESERVED` у перевірці маніфесту й `space.json` працювало без змін; невідома роль, як і раніше,
#: — `bad-manifest` (маніфест) чи ігнорується (`roles` запису `space.json`).
ROLES_RESERVED = ()
#: Функції `server.py`, які мусить мати модуль ролі (понад обовʼязковий `check`).
ROLE_FUNCTIONS = {'publish': ('publish',), 'tokens': ('tokens',), 'comments': ('client_config', 'list', 'resolve'),
                  'vcs': ('status', 'push', 'pull'), 'dashboard': ('rows', 'push'),
                  'tracker': ('statuses',), 'notify': ('mute_state', 'mute_set')}
#: Необовʼязкові функції ролі: беруться з server.py, якщо є й callable; свій модуль без них валідний.
ROLE_OPTIONAL_FUNCTIONS = {'vcs': ('validate', 'mirror_dir'), 'dashboard': ('open_comments',)}
#: Куди публікує модуль ролі `publish` (необовʼязкове поле маніфесту `publish_target`): `folder` — у локальну теку
#: (`static-publish`), `url` — на віддалений хост, де результат — адреса (`vercel-publish`). Типово `folder`.
PUBLISH_TARGETS = ('folder', 'url')
SETTING_TYPES = ('text', 'path', 'bool', 'select', 'secret')
ID_RE = re.compile(r'[a-z0-9][a-z0-9-]{0,39}')
KEY_RE = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}')
#: Скільки секунд чекаємо на `check` модуля (виклик у робочому потоці).
CHECK_TIMEOUT = 5
#: Необовʼязковий ключ маніфесту `check_timeout_s` (ціле 1..`MAX_CHECK_TIMEOUT`): модулю, чия перевірка запускає процес
#: (`vercel-publish` у режимі `cli`: `npx --yes vercel whoami`, холодне завантаження ≫ 5 с), потрібен довший тайм-аут `check`.
#: Без ключа — `CHECK_TIMEOUT`. Клієнт (`MODULE_CHECK_POST_TIMEOUT_MS`) чекає на запит не менше за цей строк.
MAX_CHECK_TIMEOUT = 150
#: Тайм-аут `list`/`resolve` модуля ролі `comments` (ходять у мережу сервісу; кличе агент, не сторінка:
#: `serve.ProjectComments._module`). Модуль мусить вкластись РАНІШЕ й відповісти своїм текстом помилки (`supabase-comments` —
#: 8 с на запит), інакше людина бачить `check-timeout` ядра замість причини.
COMMENTS_TIMEOUT = 10
#: Текст відмови `provider('comments')` у просторі з інтеграціями, де явно ввімкнений модуль коментарів не завантажився.
COMMENTS_MODULE_BROKEN = 'модуль коментарів простору не завантажився — командні коментарі вимкнено'
#: Файли браузерного адаптера (`client` у маніфесті ролі `comments`): імʼя, кількість, розмір одного файла.
CLIENT_RE = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\.js')
MAX_CLIENT_FILES = 8
MAX_CLIENT_BYTES = 512 * 1024
#: `client_config` модуля: плаский JSON-обʼєкт не більший за стільки знаків (`json.dumps`).
MAX_CLIENT_CONFIG = 4096
#: Змінна оточення з другою текою вбудованих модулів (тестовий шов, див. docstring модуля).
EXTRA_ENV = 'DEAI_EXTRA_MODULES'
MAX_SERVER_BYTES = 1 << 20
MAX_VALUE_LEN = 4096
MAX_MESSAGE = 300
MAX_FULL_MESSAGE = 1 << 16

STATUS = {'bad-manifest': 500, 'module-error': 502, 'role-taken': 409, 'unknown-module': 404,
          'bad-settings': 400, 'space-json-unreadable': 409, 'spaces-off': 409,
          'check-timeout': 504, 'secrets-unreadable': 409, 'unwritable': 500, 'bad-folder': 409,
          # модулі «публікація за адресою»: віддалений хост не прийняв токен / вперся в ліміт (текст — від модуля)
          'vercel-auth': 409, 'vercel-busy': 409,
          # модуль Vercel у режимі `cli` (4b-1): нема node/npx, не виконано вхід, не вибрано команду (scope), збій `deploy`,
          # у виводі `deploy` нема адреси (текст — від модуля; адаптер ЛІГИ в `serve.py` підміняє його своїми підказками)
          'no-node': 409, 'vercel-login': 409, 'vercel-scope': 409, 'vercel-deploy': 502, 'vercel-no-url': 502,
          # роль `vcs` (4a): мережа/DNS/тайм-аут git, відмова в доступі, погана ціль, зайняте дзеркало, решта відмов git
          'vcs-offline': 502, 'vcs-auth': 502, 'vcs-bad-target': 400, 'vcs-busy': 409, 'vcs-error': 502,
          # простір ЛІГА без адреси/ключа Supabase у конфігу установки (4b-2; `supabase_url`/`supabase_key` у tasks.json)
          'comments-unconfigured': 409,
          # закон ізоляції (4d-4b, Д6): ізольований прогін у справжньому домі спільних коментарів не читає — не «не налаштовано»
          'comments-isolated': 409,
          # роль `dashboard` (4c-1): простір ЛІГА без адреси/ключа Supabase; збій запиту модуля до сховища дашборда
          'dashboard-unconfigured': 409, 'dashboard-error': 502,
          # роль `tracker` (4c-2): простір ЛІГА без адреси Jira (`jira_base`) чи облікових; збій запиту модуля до трекера
          'tracker-unconfigured': 409, 'tracker-error': 502,
          # роль `notify` (4c-3): простір ЛІГА без адреси/ключа Supabase; збій виклику модуля сповіщень (тиша каналу Teams)
          'notify-unconfigured': 409, 'notify-error': 502}

#: Коди ЯДРА для своїх модулів і довіри (етап 3c). Окремо від `STATUS`: `_run` пропускає як є лише коди `STATUS`, тож
#: модуль не кине «module-untrusted» від свого імені.
CORE_STATUS = {'module-untrusted': 409, 'module-changed': 409, 'module-refused': 409, 'trust-needs-ui': 403,
               'trust-declined': 409, 'trust-no-confirm': 409, 'trust-busy': 409, 'trust-unreadable': 409}
#: Своїх модулів у просторі — не більше (за абеткою); решта — примітки `too-many-modules`.
MAX_OWN_MODULES = 32
#: Скільки секунд чекати верхнього рівня `server.py` знімка свого модуля.
LOAD_TIMEOUT = 5
#: Скільки знімків тримає кеш завантаження своїх модулів.
OWN_CACHE_MAX = 64
UNTRUSTED_TEXT = 'module is not trusted on this computer'


class ModuleError(Exception):
    """`code` — з таблиці `STATUS`, `status` — HTTP, `message` — текст (≤300, без секретів).
    `ModuleError('x', 409)`, `ModuleError('x', message='…')` і `ModuleError('x', '…')` — усе дозволено.
    Конструктор ріже `message` до 300 знаків; повний текст (до 64 КіБ) лишається в `_full` і віддається публічною властивістю
    `full`. Секрети з нього вирізає `call()` (`_run`: СПЕРШУ вирізати, ПОТІМ різати — секрет, що перетинає межу 300, інакше пролізав
    би обрізаним початком); без `call` (помилка ядра) `full` — сирий текст."""

    def __init__(self, code, status=None, message=''):
        if isinstance(status, str):
            status, message = (message if isinstance(message, int) else None), status
        self.code = code
        self.status = status if isinstance(status, int) else STATUS.get(code, CORE_STATUS.get(code, 500))
        self._full = str(message or '')[:MAX_FULL_MESSAGE]
        self.message = self._full[:MAX_MESSAGE]
        super().__init__(f'{code}: {self.message}' if self.message else code)

    @property
    def full(self):
        """Повний текст (≤ `MAX_FULL_MESSAGE`); `message` — його перші 300 знаків. Для виклику з `call()` секрети з нього вже
        вирізані (`_run`): повний вивід `vercel deploy` потрібен адаптерові ЛІГИ, щоб розпізнати причину за хвостом тексту."""
        return self._full


class Module:
    """Вбудований модуль із каталогу. `status`: `'ok'` — вантажиться й відповідає маніфесту,
    `'error'` — ні (`error` — текст, `error_code` — `bad-manifest` чи `module-error`). Модуль із
    помилкою лишається в каталозі, але нічого не віддає (`fn()` → `None`) і постачальником не є.
    `publish_target` — `'folder'` (типово) чи `'url'` (див. `PUBLISH_TARGETS`): що повертає й куди пише модуль
    ролі `publish`. `client` — кортеж імен файлів браузерного адаптера (лише роль `comments`, див. `_check_client`),
    у порядку вантаження. `fn(імʼя)` — функція `server.py` (`'check'`, `'publish'`, `'client_config'`…) або `None`: необовʼязкові
    функції ролі (`ROLE_OPTIONAL_FUNCTIONS`: `validate`, `mirror_dir` у `vcs`) модуль міг не мати, і тоді `fn()` дає `None`,
    а модуль лишається справним.

    Свій модуль простору (`origin='space'`) без робочого знімка — `status='untrusted'` чи `'error'` (`refused`) з
    `error_code='module-untrusted'`: функцій нема, ролі й налаштування — з маніфесту теки."""
    __slots__ = ('id', 'name', 'version', 'api', 'roles', 'settings', 'publish_target', 'client', 'status', 'error',
                 'error_code', 'dir', '_fns', 'origin', 'trust', 'record', 'source', 'trust_error', 'check_timeout_s')

    def __init__(self, mid, *, name=None, version='', api=None, roles=(), settings=(), status='ok',
                 error=None, error_code=None, dir='', fns=None, publish_target='folder', client=(),
                 origin='builtin', trust=None, record=False, source='', trust_error=None, check_timeout_s=None):
        self.id = mid
        self.name = name if isinstance(name, str) and name.strip() else mid
        self.version = version if isinstance(version, str) else ''
        self.api = api
        self.roles = list(roles)
        self.settings = [dict(s) for s in settings]
        self.publish_target = publish_target if publish_target in PUBLISH_TARGETS else 'folder'
        # `None` — ключа в маніфесті нема: `check` бере `CHECK_TIMEOUT` у момент виклику (тести його підміняють)
        self.check_timeout_s = check_timeout_s if type(check_timeout_s) is int else None
        self.client = tuple(client)
        self.status = status
        self.error = error
        self.error_code = error_code
        self.dir = dir
        self._fns = dict(fns or {}) if status == 'ok' else {}
        self.origin = origin            # 'builtin' | 'space' (свій модуль простору, етап 3c)
        self.trust = trust              # свій: 'untrusted' | 'trusted' | 'changed' | 'refused'; вбудований — None
        self.record = bool(record)      # свій: чи є запис довіри (у `untrusted` з пошкодженим знімком — є)
        self.source = source            # свій: тека в просторі, з `~`
        self.trust_error = trust_error  # свій: причина `untrusted`/`refused` (код)

    def fn(self, name):
        return self._fns.get(name)

    def secret_keys(self):
        return [s['key'] for s in self.settings if s['type'] == 'secret']

    def private_secret_keys(self):
        """Секрети БЕЗ `"public": true`: їх значення не сміє потрапити в сторінки (`comments_client`)."""
        return [s['key'] for s in self.settings if s['type'] == 'secret' and not s.get('public')]

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
        _OWN_CACHE.clear()
        _OWN_LOCKS.clear()
    with _STATE_LOCK:
        _LAST_CHECK.clear()
        _CAPS.clear()
        _FOLDER_INPUTS.clear()
    module_trust.reset_cache()


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


def extra_dir():
    """Друга тека вбудованих модулів зі змінної оточення `DEAI_EXTRA_MODULES` (тестовий шов: живі перевірки й тести
    кладуть сюди модулі-фікстури) — нормалізований абсолютний шлях або `None`, коли змінної нема чи вона порожня.
    Читається щоразу, а не при імпорті: тест міняє оточення без перезапуску."""
    raw = os.environ.get(EXTRA_ENV)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return os.path.normpath(os.path.abspath(raw))


def _list_dirs(base):
    """[(імʼя, шлях)] підтек `base` за абеткою, без прихованих і `__pycache__`; теки нема — порожньо."""
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    out = []
    for n in names:
        if n.startswith('.') or n == '__pycache__':
            continue
        d = os.path.join(base, n)
        if os.path.isdir(d):
            out.append((n, d))
    return out


def _scan():
    """`(теки, [(імʼя, шлях)], [(імʼя, шлях)])`: теки джерел (`builtin_dir()` і, якщо задана й інша, `extra_dir()`),
    модулі каталогу за абеткою й ті модулі зайвої теки, чий `id` уже є серед вбудованих (вони програють:
    `shadowed`). Підтеки — без прихованих і `__pycache__`."""
    base = os.path.normpath(builtin_dir())
    items = _list_dirs(base)
    bases, lost = (base,), []
    extra = extra_dir()
    if extra is not None and extra != base:
        bases = (base, extra)
        taken = {n for n, _ in items}
        for n, d in _list_dirs(extra):
            (lost if n in taken else items).append((n, d))
        items.sort(key=lambda it: it[0])
    return bases, items, lost


def shadowed():
    """`{id: Module}` модулів з `DEAI_EXTRA_MODULES`, чий `id` уже має вбудований модуль: вбудований виграє (його не
    підмінити через оточення), а такий модуль лишається ТУТ — зі `status='error'` і причиною; його `server.py` не
    виконується. Каталог (`catalog()`) їх не містить."""
    out = {}
    for n, d in _scan()[2]:
        out[n] = Module(n, status='error', error_code='bad-manifest', dir=d,
                        error=f'id {n!r} is taken by a built-in module; the one in {EXTRA_ENV} is ignored')
    return out


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
    if 'public' in s:                                   # лише `secret`: значення живе в `secrets.json`, але може йти в сторінки
        if t != 'secret':
            return None, f'{key}: public is only for secret settings'
        if not isinstance(s['public'], bool):
            return None, f'{key}: public must be a boolean'
        if s['public']:
            out['public'] = True                        # `false` — те саме, що без прапорця: не зберігаємо
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


def _check_client(man, roles, d):
    """`client` маніфесту: `(кортеж імен, None)` або `(None, причина)`. Обовʼязковий для ролі `comments`, заборонений без
    неї; 1–`MAX_CLIENT_FILES` унікальних імен за `CLIENT_RE`, кожне — звичайний файл теки `d` (`lstat`: ні посилання,
    ні жорсткого посилання, ні FIFO) не більший за `MAX_CLIENT_BYTES`. Імен у тексті причини — лише ті, що пройшли
    `CLIENT_RE`."""
    has_role = 'comments' in roles
    if 'client' not in man:
        return ((), None) if not has_role else (None, 'client: required for the comments role')
    if not has_role:
        return None, 'client: only for the comments role'
    raw = man['client']
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CLIENT_FILES:
        return None, f'client: must be a list of 1 to {MAX_CLIENT_FILES} file names'
    names = []
    on_disk = None
    for i, n in enumerate(raw):
        if not isinstance(n, str) or not CLIENT_RE.fullmatch(n):
            return None, f'client[{i}]: must match [A-Za-z0-9_][A-Za-z0-9_.-]{{0,63}}\\.js'
        if n in names:
            return None, f'client[{i}]: {n} is listed twice'
        if on_disk is None:
            try:
                on_disk = set(os.listdir(d))
            except OSError:
                return None, 'client: the module folder is not readable'
        try:
            if n not in on_disk:                        # імʼя — РІВНО як на диску: ФС без урахування регістру
                raise OSError                           # віддала б `adapter.js` на запит `ADAPTER.js`, а дубль за регістром
            st = os.lstat(os.path.join(d, n))           # пройшов би перевірку «двічі»
        except OSError:
            return None, f'client[{i}]: {n} is not a file of the module'
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return None, f'client[{i}]: {n} must be a regular file (no symlink, no hard link)'
        if st.st_size > MAX_CLIENT_BYTES:
            return None, f'client[{i}]: {n} is bigger than {MAX_CLIENT_BYTES} bytes'
        names.append(n)
    return tuple(names), None


def _check_manifest(man, folder, d):
    """(метадані, None) або (None, причина) — перевірка маніфесту (і файлів `client` у теці `d`) без виконання
    `server.py`."""
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
    target = man.get('publish_target', 'folder')
    if not isinstance(target, str) or target not in PUBLISH_TARGETS:
        return None, f'publish_target: must be one of {", ".join(PUBLISH_TARGETS)}'
    cts = man.get('check_timeout_s')
    if 'check_timeout_s' in man and (type(cts) is not int or not 1 <= cts <= MAX_CHECK_TIMEOUT):
        return None, f'check_timeout_s: must be an integer 1..{MAX_CHECK_TIMEOUT}'
    raw = man.get('settings', [])
    if not isinstance(raw, list):
        return None, 'settings: must be a list'
    settings, seen = [], set()
    for i, s in enumerate(raw):
        norm, why = _check_setting(s, seen)
        if why:
            return None, f'settings[{i}]: {why}'
        settings.append(norm)
    roles = list(dict.fromkeys(roles))
    client, why = _check_client(man, roles, d)
    if why:
        return None, why
    return {'name': name, 'version': version, 'roles': roles,
            'settings': settings, 'publish_target': target, 'client': client,
            'check_timeout_s': cts if 'check_timeout_s' in man else None}, None


def _failed(folder, d, code, text, man=None, meta=None):
    base = dict(status='error', error=str(text)[:MAX_MESSAGE], error_code=code, dir=d)
    if meta:
        return Module(folder, name=meta['name'], version=meta['version'], api=API_VERSION,
                      roles=meta['roles'], settings=meta['settings'],
                      publish_target=meta['publish_target'], check_timeout_s=meta['check_timeout_s'],
                      **base)           # `client` не передаємо: помилковий модуль нічого не віддає
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
    meta, why = _check_manifest(man, folder, d)
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
    for need in ('check', *(fn for r in meta['roles'] for fn in ROLE_FUNCTIONS.get(r, ()))):
        f = ns.__dict__.get(need)
        if not callable(f):
            return _failed(folder, d, 'bad-manifest', f'server.py: no callable {need}()', meta=meta)
        fns[need] = f
    for opt in dict.fromkeys(fn for r in meta['roles'] for fn in ROLE_OPTIONAL_FUNCTIONS.get(r, ())):
        f = ns.__dict__.get(opt)
        if callable(f):                                 # необовʼязкова: немає чи не функція — не помилка, `fn()` дасть `None`
            fns[opt] = f
    return Module(folder, name=meta['name'], version=meta['version'], api=API_VERSION,
                  roles=meta['roles'], settings=meta['settings'], publish_target=meta['publish_target'],
                  check_timeout_s=meta['check_timeout_s'], client=meta['client'], status='ok', dir=d, fns=fns)


def _client_sig(d):
    """Відбиток файлів `*.js` теки модуля (`lstat`: підміна файла посиланням чи жорстким посиланням — інший відбиток).
    Кеш і ключ `capabilities` мусять бачити файли адаптера, бо від них залежить, чи модуль справний."""
    out = []
    try:
        with os.scandir(d) as it:
            for e in it:
                if e.name.endswith('.js'):
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    out.append((e.name, st.st_mode, st.st_nlink, st.st_mtime_ns, st.st_size, st.st_ino))
    except OSError:
        return None
    return tuple(sorted(out))


def _load_dir(d, folder):
    sig = (_sig(os.path.join(d, 'module.json')), _sig(os.path.join(d, 'server.py')), _client_sig(d))
    with _LOAD_LOCK:
        hit = _CACHE.get(d)
        if hit is not None and hit[0] == sig:
            return hit[1]
        mod = _build(d, folder)
        _CACHE[d] = (sig, mod)
        return mod


# ------------------------------------------------------------------------------- свої модулі простору (3c)

#: Кеш знімків своїх модулів: `{(тека знімка, id): (відбиток, Module)}` у порядку використання; лок — на ту саму пару.
#: Ключ несе й `id`: той самий знімок під двома іменами (запис довіри, що вказує на чужий хеш) не віддає одного модуля обом.
_OWN_CACHE = OrderedDict()
_OWN_LOCKS = {}
#: Покоління кешу знімків: `forget_own` піднімає його, а `_load_own` кладе результат у кеш, лише якщо за час завантаження
#: покоління не змінилось (інакше збійне завантаження, що ще в польоті, дописало б себе ПІСЛЯ повторної довіри).
_OWN_GEN = 0


def _clone(m, **kw):
    """Новий `Module` з полями `m` і змінами `kw`: обʼєкт свого модуля — свій на кожен виклик (два простори з однаковими
    байтами ділять теку знімка, але не обʼєкт), а рішення про довіру не живе в кеші."""
    c = Module.__new__(Module)
    for s in Module.__slots__:
        setattr(c, s, getattr(m, s))
    c.roles = list(m.roles)
    c.settings = [dict(s) for s in m.settings]
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def untrusted_own(m):
    """Свій модуль без робочого знімка (недовірений чи `refused` без довіри): код не виконується, вмикати не можна."""
    return getattr(m, 'origin', 'builtin') == 'space' and m.error_code == 'module-untrusted'


def _builtin_ids():
    """Id модулів із тек вбудованих (`app/modules`, `DEAI_EXTRA_MODULES`, і ті, що програли як `shadowed`)."""
    _, items, lost = _scan()
    return {n for n, _ in items} | {n for n, _ in lost}


def _manifest_from_bytes(raw, folder, d):
    """`(метадані, None)` чи `(None, причина)` — маніфест свого модуля з УЖЕ прочитаних сканером байтів (не повторним
    читанням з диска), з тим самим захистом, що `spaces._read_json` (розмір, глибина), і `_check_manifest`."""
    if raw is None:
        return None, 'module.json: not found'
    if len(raw) > spaces.MAX_JSON_BYTES:
        return None, f'module.json: bigger than {spaces.MAX_JSON_BYTES} bytes'
    try:
        man = json.loads(raw.decode('utf-8'))
    except RecursionError:
        return None, 'module.json: nested too deep'
    except ValueError as e:                                   # UnicodeDecodeError — теж ValueError
        return None, f'module.json: {_short(e)}'
    return _check_manifest(man, folder, d)


def _meta_kw(meta):
    if not meta:
        return {}
    return dict(name=meta['name'], version=meta['version'], api=API_VERSION, roles=meta['roles'],
                settings=meta['settings'], publish_target=meta['publish_target'],
                check_timeout_s=meta['check_timeout_s'])


def _own_base(space):
    p = _space_path(space)
    return os.path.join(p, 'modules') if p and spaces.layer_on() else None


def _own_listing(space):
    """`([(id, тека)], примітки)` своїх модулів простору: лише `lstat`/`listdir`, без читання файлів модулів. Модуль —
    підтека з імʼям за `ID_RE`, у якій є `module.json`; решта ігнорується. Примітки — `id-taken`, `too-many-modules`,
    `modules-link`, `modules-unreadable`."""
    base = _own_base(space)
    if base is None:
        return [], []
    try:
        st = os.lstat(base)
    except FileNotFoundError:
        return [], []
    except OSError:
        return [], [{'folder': 'modules', 'code': 'modules-unreadable'}]
    if module_trust.is_link(st) or not stat.S_ISDIR(st.st_mode):
        return [], [{'folder': 'modules', 'code': 'modules-link'}]
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return [], [{'folder': 'modules', 'code': 'modules-unreadable'}]
    taken = _builtin_ids()
    out, notes = [], []
    for n in names:
        d = os.path.join(base, n)
        if not ID_RE.fullmatch(n) or not os.path.lexists(os.path.join(d, 'module.json')):
            continue
        if n in taken:
            notes.append({'folder': f'modules/{n}', 'code': 'id-taken'})
        elif len(out) >= MAX_OWN_MODULES:
            notes.append({'folder': f'modules/{n}', 'code': 'too-many-modules'})
        else:
            out.append((n, d))
    return out, notes


def own_notes(space):
    """Примітки своїх модулів простору (`[{folder, code}]`) для `GET /api/modules`; нічого не виконує й не хешує."""
    return _own_listing(space)[1]


def own_modules(space):
    """`{id: Module}` своїх модулів простору — новий обʼєкт на кожен виклик. Довірений — зі знімка (`_load_own`); без
    робочого знімка — без виконання, з маніфестом теки (якщо він розбирається). ⚠️ Може виконати код знімка — НЕ під
    `WRITE_LOCK`."""
    cands, _ = _own_listing(space)
    if not cands:
        return {}
    try:
        records, rec_err = module_trust.load_records(), None
    except module_trust.TrustUnreadable:
        records, rec_err = {}, 'trust-unreadable'
    return {mid: _own_module(space, mid, d, records, rec_err) for mid, d in cands}


def _own_module(space, mid, d, records, rec_err):
    try:
        sc, refused = module_trust.scan(d), None
    except module_trust.Refused as e:
        sc, refused = None, e
    meta = None
    if sc is not None:
        meta, why = _manifest_from_bytes(sc.manifest, mid, d)
        if why:
            refused = module_trust.Refused('bad-manifest', why)
    # Тека модуля — посилання (`Refused('symlink', '.')`): `key_for` бере `realpath`, і аліас `modules/aaa -> acme` (чи посилання
    # на довірений модуль іншого простору) ділив би запис довіри з теку-ціллю. Такий аліас — `refused` без запису.
    alias = refused is not None and refused.code == 'symlink' and refused.detail == '.'
    rec = None if (rec_err or alias) else records.get(module_trust.key_for(_space_path(space), mid))
    base = dict(origin='space', source=module_trust.tilde(d), record=rec is not None)
    if rec is not None and module_trust.verify_snapshot(rec['hash']):
        m = _load_own(module_trust.snapshot_dir(rec['hash']), mid)
        trust = 'refused' if refused else ('trusted' if sc.hash == rec['hash'] else 'changed')
        return _clone(m, trust=trust, trust_error=refused.code if refused else None, **base)
    if refused:
        text = f'{refused.code}: {refused.detail}' if refused.detail else refused.code
        return Module(mid, status='error', error=text[:MAX_MESSAGE], error_code='module-untrusted', dir=d,
                      trust='refused', trust_error=refused.code, **_meta_kw(meta), **base)
    why = rec_err or ('snapshot-damaged' if rec is not None else None)
    return Module(mid, status='untrusted', error=UNTRUSTED_TEXT, error_code='module-untrusted', dir=d,
                  trust='untrusted', trust_error=why, **_meta_kw(meta), **base)


def _snapshot_meta(d, mid):
    """Метадані маніфесту знімка `d` (як віддає `_check_manifest`) чи `None`, коли знімок не сканується чи маніфест не проходить. Лише
    читання (скан з кешем відбитка), не виконання: потрібні `_failed(meta=…)`, щоб модуль, який не завантажився, ніс свої
    ролі, налаштування й версію (інакше він «не тримав би» роль, а в `space.json` лягло б `roles: []`)."""
    try:
        sc = module_trust.scan(d)
    except module_trust.Refused:
        return None
    return _manifest_from_bytes(sc.manifest, mid, d)[0]


def _load_own(d, mid):
    """`Module` знімка `d` (id — `mid`). Верхній рівень `server.py` виконується в потоці-демоні з тайм-аутом
    `LOAD_TIMEOUT` і ПОЗА `_LOAD_LOCK` (лок — на пару (тека знімка, id), щоб не будувати двічі): зависання свого модуля не
    блокує ні каталог інших просторів, ні вбудовані модулі. Не встиг чи кинув виняток — `module-error` («load timed out» чи
    текст винятку), але з маніфестом знімка (`_snapshot_meta`, прочитаний ДО старту потоку); результат кешується за відбитком
    теки (потік-сирота доживає свій час), але лише коли `forget_own` не спрацював за час завантаження (`_OWN_GEN`) — інакше
    результат повертається викликачу, а в кеш не потрапляє."""
    key = (d, mid)
    fp = module_trust.fingerprint(d)
    with _LOAD_LOCK:
        hit = _OWN_CACHE.get(key)
        if hit is not None and hit[0] == fp:
            _OWN_CACHE.move_to_end(key)                     # за порядком використання: останнім витісняється те, чим користуються
            return hit[1]
        lock = _OWN_LOCKS.setdefault(key, threading.Lock())
        gen = _OWN_GEN
    with lock:
        with _LOAD_LOCK:
            hit = _OWN_CACHE.get(key)
            if hit is not None and hit[0] == fp:
                _OWN_CACHE.move_to_end(key)
                return hit[1]
        meta = _snapshot_meta(d, mid)
        box = []
        sid = spaces.request_space_id()

        def work():
            try:
                with spaces.request_space(sid):
                    box.append(_build(d, mid))
            except BaseException as e:  # noqa: BLE001 — і `KeyboardInterrupt` модуля не валить сервер
                box.append(_failed(mid, d, 'module-error', _exc_text(e), meta=meta))
        t = threading.Thread(target=work, name=f'deai-own-load-{mid}', daemon=True)
        t.start()
        t.join(LOAD_TIMEOUT)
        mod = box[0] if box else _failed(mid, d, 'module-error', f'load timed out after {LOAD_TIMEOUT} s', meta=meta)
        with _LOAD_LOCK:
            if _OWN_GEN == gen:                             # `forget_own` посеред завантаження: цей результат — не в кеш
                _OWN_CACHE[key] = (fp, mod)
                _OWN_CACHE.move_to_end(key)
                while len(_OWN_CACHE) > OWN_CACHE_MAX:
                    old, _ = _OWN_CACHE.popitem(last=False)
                    _OWN_LOCKS.pop(old, None)
        return mod


def forget_own(h):
    """Забути закешоване завантаження знімка `h` (хеш) під БУДЬ-ЯКИМ id: повторна довіра ті самі байти — та сама тека знімка,
    а закешований збій (тайм-аут, виняток) інакше пережив би її аж до перезапуску. Решту знімків не чіпає. Під `_LOAD_LOCK`.
    Піднімає `_OWN_GEN`: завантаження, що вже в польоті, не допише свій результат у кеш після цього виклику."""
    global _OWN_GEN
    d = module_trust.snapshot_dir(h)
    with _LOAD_LOCK:
        _OWN_GEN += 1
        for k in [k for k in _OWN_CACHE if k[0] == d]:
            del _OWN_CACHE[k]
        for k in [k for k in _OWN_LOCKS if k[0] == d]:
            del _OWN_LOCKS[k]


def catalog(space=None):
    """`{id: Module}` за абеткою: вбудовані (`app/modules` і, якщо задана, тека `DEAI_EXTRA_MODULES`; `id` вбудованого
    виграє — програш у `shadowed()`) і — коли передано простір — його свої модулі (`own_modules`: свіжі обʼєкти, довіра
    рахується щоразу). Модулі з помилкою — тут, зі `status='error'`; недовірені свої — зі `status='untrusted'`.
    ⚠️ Виконує код модулів (першого разу чи після зміни файлів) — НЕ кликати під `WRITE_LOCK`."""
    _, items, _ = _scan()
    out = {name: _load_dir(d, name) for name, d in items}
    live = {d for _, d in items}
    with _LOAD_LOCK:
        for k in [k for k in _CACHE if k not in live]:      # теки, яких уже нема (чи оточення більше не називає); знімки — у `_OWN_CACHE`
            del _CACHE[k]
    if space:
        out.update(own_modules(space))
        out = dict(sorted(out.items()))
    return out


def _catalog_sig():
    bases, items, _ = _scan()
    return (bases, tuple((n, d, _sig(os.path.join(d, 'module.json')), _sig(os.path.join(d, 'server.py')),
                          _client_sig(d)) for n, d in items))


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
        roles = e.get('roles')                     # пише вмикання СВОГО модуля (`write_module_state`); вбудовані — без
        if (isinstance(roles, list) and roles
                and all(isinstance(r, str) and r in ROLES_CALLED + ROLES_RESERVED for r in roles)):
            out[mid]['roles'] = list(dict.fromkeys(roles))
        if isinstance(e.get('shared_state'), bool):  # 4d-3a: запис СПІЛЬНОГО стану ЛІГИ (пише міграція); не-bool ігнорується
            out[mid]['shared_state'] = e['shared_state']
    return out


def shared_state(space, module_id):
    """Чи явний запис модуля в `space.json` позначено `shared_state: true` (4d-3a): спільний стан ЛІГИ, що підлягає закону ізоляції
    (`isolation.isolated`) так само, як неявний шлях. ⛔ Тотальна: нема запису, не-`bool`, збій читання — `False`, не виняток
    (відмова читання не має вмикати спільний шлях і не має ламати екран)."""
    try:
        return space_modules(space).get(module_id, {}).get('shared_state') is True
    except Exception:  # noqa: BLE001 — будь-який збій = «не спільний»
        return False


def space_modules(space):
    """`{id: {"enabled": bool, "settings": {…символьні…}}}` — явні рішення з `space.json` простору.
    Простір без теки/файла — `{}`; файл, що не читається, — `ModuleError('space-json-unreadable', 409)`."""
    path = _space_json_path(space)
    if path is None:
        return {}
    return _normalize(_raw_modules(_load_space_json(path)))


def _enabled_in(m, space, explicit):
    """(увімкнено, неявно) за явними рішеннями `explicit`. Неявного типового нема (4d-4c): `implicit` — завжди `False` (ключ API до 1.0)."""
    e = explicit.get(m.id)
    return (e['enabled'], False) if e is not None else (False, False)


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
    типовими значеннями маніфесту, без секретів). `implicit` — завжди `False`: неявного типового нема (4d-4c),
    `static-publish` — явний запис `space.json`.
    ⚠️ Виконує код модулів (каталог) і може кинути `space-json-unreadable`."""
    if not space:
        return {}
    explicit = space_modules(space)
    return {mid: _entry_state(m, space, explicit) for mid, m in catalog(space).items()}


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


def _need_module(module_id, space=None):
    m = catalog(space).get(module_id) if isinstance(module_id, str) else None
    if m is None:
        raise ModuleError('unknown-module', message=str(module_id)[:60])
    return m


def validate_settings(module_id, settings, space=None):
    """Перевірка патча налаштувань БЕЗ запису: `unknown-module` / `bad-settings` (ті самі, що кине
    `write_module_state`). Для API, що пише секрети РАНІШЕ за `space.json`: відмова налаштувань мусить
    настати до запису секрету, інакше клієнт із 400 у руках мав би вже змінений пароль. Нічого не пише, лок
    не бере (каталог виконує код модулів). `space` — запис простору, щоб знайти СВІЙ модуль; без нього — лише вбудовані."""
    return _validate_patch(_need_module(module_id, space), settings)


def _require_writable(space):
    if not spaces.layer_on() or not _space_path(space):
        raise ModuleError('spaces-off', message='spaces layer is off or the space has no folder')


def _holds(o, space, explicit):
    """Чи тримає модуль `o` свої ролі: завантажений і ввімкнений (зокрема неявно) — так; СВІЙ модуль, ЯВНО ввімкнений
    у `space.json`, — так навіть коли тут не працює («на папері»: роль за ним, доки людина її не віддасть — інакше пізніша
    довіра дала б двох постачальників). Вбудований, що не завантажився, — ні, як і було."""
    if o.status == 'ok':
        return _enabled_in(o, space, explicit)[0]
    return o.origin == 'space' and explicit.get(o.id, {}).get('enabled') is True


def _roles_of(oid, cat, explicit):
    """Ролі модуля `oid`: з маніфесту (каталог); лише коли маніфест ролей не дав — для СВОГО модуля чи теки, якої в каталозі
    нема, — із запису `space.json` (їх пише вмикання свого модуля). Маніфест зламаний (ролей у каталозі нема) чи тека не
    приїхала з git — роль усе одно за ним «на папері», а не вільна для другого постачальника. Живий маніфест запис
    перекриває: нова довірена версія, що роль прибрала, не лишає її застарілому запису (так само `_paper_failure`)."""
    o = cat.get(oid)
    out = set(o.roles) if o is not None else set()
    if o is None or (o.origin == 'space' and not out):
        out |= set(explicit.get(oid, {}).get('roles', ()))
    return out


def _holders(m, cat, space, explicit):
    """Id ІНШИХ модулів, що зараз тримають хоч одну роль `m`, за абеткою: з каталогу — за `_holds` (неявно ввімкнений
    `static-publish` теж; СВІЙ явно ввімкнений — і «на папері»); явно ввімкнений запис `space.json`, чиєї теки в каталозі
    нема, — теж (ролі з запису, `_roles_of`). Вбудовані модулі, що не завантажились, ролей не тримають."""
    mine = set(m.roles)
    out = []
    for oid in sorted(set(cat) | set(explicit)):
        if oid == m.id or not (mine & _roles_of(oid, cat, explicit)):
            continue
        o = cat.get(oid)
        if _holds(o, space, explicit) if o is not None else explicit[oid]['enabled'] is True:
            out.append(oid)
    return out


def _role_conflict(m, cat, space, explicit):
    """Текст `role-taken` для модуля `m`, якщо хтось інший уже тримає його роль (`_holders`); інакше `None`. Роль у
    тексті — з тих самих ролей власника (`_roles_of`): тека, якої в каталозі нема, чи зламаний маніфест не дають `KeyError`."""
    for oid in _holders(m, cat, space, explicit):
        return f'{sorted(set(m.roles) & _roles_of(oid, cat, explicit))[0]} is already provided by {oid}'
    return None


def _check_replace_target(m):
    """`replace` лише НА модуль, що завантажився. Модуль із дійсним манифестом, але зламаним `server.py`, лишається в
    каталозі з УСІМА своїми ролями (`_failed(meta=…)`), тож заміна на нього вимкнула б робочого постачальника, а нового не
    дала б (`provider()` → `None`) — простір без постачальника ролі, чого спека не допускає. Код відмови —
    `error_code` модуля (`module-error` чи `bad-manifest`), як і в його `check`. Без `replace` вмикати такий модуль можна
    (як і було): вільну роль він займе, а `check` скаже, чому не працює."""
    if m.status != 'ok':
        raise ModuleError(m.error_code or 'module-error',
                          message=f'cannot replace with a module that did not load: {str(m.error or "")[:200]}')


def preflight(space, module_id, enabling=False, replace=False):
    """Читання БЕЗ запису і без локу: чи можна взагалі писати стан модуля. `unknown-module` (нема в каталозі),
    `space-json-unreadable` (`space_modules`) і — лише для вмикання — `role-taken`; з `replace` роль не
    перевіряється — її звільнить `write_module_state` під локом, — але ціль мусить бути завантаженим модулем
    (`_check_replace_target`). Для API, що пише секрет
    РАНІШЕ за `space.json` (спека): усе, що видно ДО запису, мусить відмовити ДО нього, інакше клієнт із 409 у руках
    мав би вже новий живий пароль. Це best-effort: авторитетні перевірки лишаються в `write_module_state` під
    локом, а те, що вони побачать іншим (гонка з паралельною правкою між пре-перевіркою й локом) чи не зможуть
    записати (`unwritable`), відмовить уже ПІСЛЯ секрету — спека це приймає (сирітський секрет нешкідливий).
    ⚠️ Виконує код модулів (каталог) — НЕ кликати під `WRITE_LOCK`."""
    cat = catalog(space)
    m = cat.get(module_id) if isinstance(module_id, str) else None
    if m is None:
        raise ModuleError('unknown-module', message=str(module_id)[:60])
    if enabling and untrusted_own(m):
        raise ModuleError('module-untrusted', message=f'{m.id}: {UNTRUSTED_TEXT}')
    explicit = space_modules(space)
    if enabling and replace:
        _check_replace_target(m)
    elif enabling:
        why = _role_conflict(m, cat, space, explicit)
        if why:
            raise ModuleError('role-taken', message=why)


def _disable_missing(space, module_id):
    """Вимкнути модуль, ЯВНО записаний у `space.json`, але відсутній у каталозі (`status: missing`): без цього запис
    лишався б увімкненим назавжди (`write_module_state` не знає модуля). Лише `enabled: false` — налаштування й решта
    запису живуть (повернеться модуль — повернуться й вони); ролей модуль не має, тож `role-taken` тут нема. id,
    якого в файлі нема чи чий запис не обʼєкт, — `unknown-module`, як і було. Під `WRITE_LOCK`; каталог уже
    прочитано (код модулів під локом не виконується). Повертає `{enabled: False, implicit: False, settings: <збережені>}`."""
    path = _space_json_path(space)
    with spaces.WRITE_LOCK:
        data = _load_space_json(path)
        mods = dict(_raw_modules(data))
        old = mods.get(module_id)
        if not isinstance(old, dict):
            raise ModuleError('unknown-module', message=module_id[:60])
        st = old.get('settings')
        state = {'enabled': False, 'implicit': False, 'settings': dict(st) if isinstance(st, dict) else {}}
        if old.get('enabled') is False:
            return state                                # вже вимкнений: файл не переписуємо
        entry = dict(old)
        entry['enabled'] = False
        mods[module_id] = entry
        data['modules'] = mods
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            spaces._write_public(path, data)
        except (OSError, ValueError) as e:
            raise ModuleError('unwritable', message=f'space.json: {type(e).__name__}') from None
        return state


def write_module_state(space, module_id, enabled=None, settings=None, replace=False):
    """Змінити вмикання й/чи налаштування модуля в `space.json` простору. Читання-зміна-запис
    ПІД `WRITE_LOCK`; каталог — ДО локу; `role-taken` — на свіжо прочитаному стані під локом (неявно
    ввімкнений `static-publish` теж займає роль `publish`); невідомі ключі файла й запису модуля
    зберігаються; `settings` — патч (`None` значення знімає ключ); секрет у ньому — `bad-settings`.
    Новий запис модуля бере `enabled` із поточного ефективного стану, тож запис налаштувань не
    перемикає неявно ввімкнений `static-publish`. Повертає новий стан модуля.

    `replace=True` (лише разом з `enabled=True`): замість `role-taken` — під тим самим локом і в ТОМУ САМОМУ записі
    файла кожен інший модуль, що тримає роль цього (`_holders`, неявний `static-publish` теж), отримує `enabled: false`
    (його налаштування лишаються). Тоді в поверненому стані є ключ `replaced` — перелік таких id (може бути порожнім).
    Ціль `replace` мусить бути завантаженим модулем (`status: ok`), інакше відмова `error_code` модуля й нічого не пишеться.

    Єдиний виняток для модуля, якого НЕМАЄ в каталозі (`missing`): `enabled=False` без налаштувань вимикає його
    запис у файлі, якщо той там є (`_disable_missing`); решта — `unknown-module`."""
    _require_writable(space)
    if enabled is not None and not isinstance(enabled, bool):
        raise _bad('enabled: expected a boolean')
    cat = catalog(space)                                # ДО локу: виконує код модулів
    m = cat.get(module_id) if isinstance(module_id, str) else None
    if m is None:
        if enabled is False and (settings is None or settings == {}) and isinstance(module_id, str):
            return _disable_missing(space, module_id)
        raise ModuleError('unknown-module', message=str(module_id)[:60])
    patch = _validate_patch(m, settings)
    if enabled is True and untrusted_own(m):
        raise ModuleError('module-untrusted', message=f'{m.id}: {UNTRUSTED_TEXT}')
    path = _space_json_path(space)
    with spaces.WRITE_LOCK:
        data = _load_space_json(path)
        mods = dict(_raw_modules(data))
        explicit = _normalize(mods)
        cur, _ = _enabled_in(m, space, explicit)
        if enabled is None and not patch:
            return _entry_state(m, space, explicit)
        replaced = []
        if enabled is True:
            if replace:
                _check_replace_target(m)                  # `m` — з каталогу ДО локу: той самий, що бачила пре-перевірка
                replaced = _holders(m, cat, space, explicit)
            else:
                why = _role_conflict(m, cat, space, explicit)
                if why:
                    raise ModuleError('role-taken', message=why)
        old = mods.get(module_id)
        entry = dict(old) if isinstance(old, dict) else {}
        entry['enabled'] = enabled if enabled is not None else cur
        if enabled is True and m.origin == 'space':
            entry['roles'] = list(m.roles)      # ролі свого модуля — у `space.json`: без теки (не приїхала з git) роль
                                                # однаково знає, що її веде він (`_paper_failure`)
        if patch:
            st = entry.get('settings')
            st = dict(st) if isinstance(st, dict) else {}
            for k, v in patch.items():
                if v is None:
                    st.pop(k, None)
                else:
                    st[k] = v
            entry['settings'] = st
        for oid in replaced:                      # колишні постачальники ролі — вимкнені тим самим записом
            prev = mods.get(oid)
            off = dict(prev) if isinstance(prev, dict) else {}
            off['enabled'] = False                # налаштування й решта запису лишаються
            mods[oid] = off
        mods[module_id] = entry
        data['modules'] = mods
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            spaces._write_public(path, data)
        except (OSError, ValueError) as e:        # ValueError: UnicodeEncodeError, NUL у шляху
            raise ModuleError('unwritable', message=f'space.json: {type(e).__name__}') from None
        state = _entry_state(m, space, _normalize(mods))
        if replace and enabled is True:
            state['replaced'] = replaced
        return state


# ------------------------------------------------------------------------------- тека публікації

def published_root(space, module):
    """Вирішене налаштування `folder` модуля `module` (`Module` чи його id) у просторі `space` — абсолютний
    шлях після підстановок (`{home}`, `{space}`, `{space_id}`, `~`) або `None`, коли в модуля нема
    налаштування `folder`. Може кинути `bad-settings` / `space-json-unreadable` / `unknown-module`.
    Саму теку це НЕ перевіряє — для того `folder_ok`."""
    m = module if isinstance(module, Module) else _need_module(module, space)
    explicit = space_modules(space)
    return resolve_settings(space, m, _entry_state(m, space, explicit)['settings']).get('folder')


def _now():
    return time.monotonic()


def folder_inputs():
    """`(реєстр, теки задач)` для `folder_ok` або `None`, коли реєстр чи ФАЙЛ ЗАДАЧ ЯКОГОСЬ простору не
    читається (`spaces.unreadable_task_files`: `all_task_dirs` читає такий файл як порожній, а в ньому могли
    лежати теки задач, — тож перевірку «пускаємо» робити не можна). Результат кешується на
    `FOLDER_INPUTS_TTL` с (`folder_ok` кличуть на кожен роздаваний файл); відмову не кешуємо. Кеш прив'язаний до
    `DEAI_HOME`, файла старих задач, стану шару й відбитків (`_sig`) реєстру та файла старих задач: щойно
    створений простір чи змінений файл задач не чекають кінця TTL. Повернуті обʼєкти не змінювати."""
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
      * за файловою системою (`samefile`, бо на macOS регістр не різнить теки, а текст його бачить):
        `path-too-broad` — сама домівка чи її предок в іншому написанні (`~` великими літерами); `path-tool`
        — тека інструмента, її підтека чи предок; `path-system` — `~/Library`, будь-яка прихована тека
        домівки чи системна тека (`/Applications`, `/System`…) в іншому написанні. Ті самі правила — і до
        `realpath`: посилання `~/lnk -> /APPLICATIONS` не обхід. Теку в домівці від системних тек
        FS-перевірка відрізняє так само, як текст (тимчасова домівка macOS живе під `/var`).
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


def write_secrets(space_id, module_id, patch, space=None):
    """Патч секретів модуля: ключ відсутній — лишити, `None` — видалити, рядок — записати. Ключі
    мусять бути оголошені в маніфесті як `secret`. Під `WRITE_LOCK`, атомарно, потім `chmod 0600` на
    файл і `0700` на теку. Шар вимкнено — `spaces-off` (справжній `~/.deai` не чіпаємо).
    `space` — запис простору, щоб знайти СВІЙ модуль; без нього — лише вбудовані.
    Повертає імена ключів, що тепер задані (значень не віддає)."""
    if not spaces.layer_on():
        raise ModuleError('spaces-off', message='spaces layer is off')
    if not isinstance(space_id, str) or not space_id or not _encodable(space_id):
        raise _bad('space: expected an id')
    m = _need_module(module_id, space)                  # ДО локу
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

def _secret_forms(secrets):
    """Усі вигляди значень секретів (`{ключ: значення}`): сире, `repr`, JSON (екрановане й ні), URL. Порожнє значення —
    нема що ховати. Рядки, а не копії словника: їх шукають у чужому тексті (`_scrub`, `comments_client`)."""
    vals = set()
    if isinstance(secrets, dict):
        for v in secrets.values():
            if isinstance(v, str) and v:
                vals |= {v, repr(v)[1:-1], json.dumps(v)[1:-1], json.dumps(v, ensure_ascii=False)[1:-1],
                         quote(v, safe='', errors='surrogatepass')}
    return {f for f in vals if f}


def _scrub(text, secrets):
    """Вирізати значення секретів (і їхні repr/JSON/URL-форми) з `text`; довші — першими."""
    vals = _secret_forms(secrets)
    for v in sorted(vals, key=len, reverse=True):
        if v:
            text = text.replace(v, '***')
    return text


def _scrub_full(text, secrets):
    """`_scrub` для повного тексту помилки. ⛔ Конструктор `ModuleError` уже обрізав його до `MAX_FULL_MESSAGE`: секрет, що
    перетинає цю межу, лишився б хвостом-префіксом (його ціле значення `_scrub` не знайде). Тож якщо текст обрізано — відкидаємо
    з кінця стільки знаків, скільки найдовша форма секрету (сира, repr, JSON, URL): префікс довший за це бути не може."""
    out = _scrub(text, secrets)
    if len(text) >= MAX_FULL_MESSAGE:
        forms = _secret_forms(secrets)
        if forms:
            out = out[:max(0, len(out) - max(len(f) for f in forms))]
    return out


def _run(f, ctx, args, secrets):
    """(True, результат) або (False, (код, текст)). `ModuleError` модуля з кодом, відомим ядру (`STATUS`),
    проходить як є (його код читає API: `bad-folder`…) — з вирізаними секретами; текст тут НЕ обрізається до 300:
    повний — у `ModuleError.full`, а перші 300 знаків — у `message` (їх ріже конструктор у `call`);
    усе інше (невідомий код, `SystemExit`, `ValueError`…) — `module-error`."""
    try:
        return True, f(ctx, *args)
    except KeyboardInterrupt:
        raise
    except ModuleError as e:
        if e.code in STATUS:
            # ⛔ БЕЗ `[:MAX_MESSAGE]`: повний (вичищений) текст іде в `call()`, а `message` обріже вже конструктор `ModuleError`
            return False, (e.code, _scrub_full(e._full, secrets))
        text = f'ModuleError: {e.code}: {e._full}' if e._full else f'ModuleError: {e.code}'
        return False, ('module-error', _scrub(text, secrets)[:MAX_MESSAGE])
    except BaseException as e:  # noqa: BLE001 — SystemExit, GeneratorExit… теж `module-error`
        return False, ('module-error', _scrub(_exc_text(e), secrets)[:MAX_MESSAGE])   # СПЕРШУ вирізати, ПОТІМ різати


#: Шукач інструментів машини для модулів (`ctx['find_tool']`): ядро реєструє свій (`serve._node_bin` знає про nvm/volta/brew,
#: яких нема в PATH GUI-застосунку); без реєстрації — `shutil.which`. Лише ці імена: модуль не отримує загального
#: «знайди мені будь-яку програму». Шукач кличеться ліниво, лише коли модуль просить інструмент (login-shell повільний).
TOOL_NAMES = ('npx', 'node')
_TOOL_FINDER = [None]


def set_tool_finder(fn):
    """Зареєструвати шукач `fn(name) -> шлях | None` (`None` — назад до `shutil.which`)."""
    _TOOL_FINDER[0] = fn


def _find_tool(name):
    if name not in TOOL_NAMES:
        return None
    fn = _TOOL_FINDER[0] or shutil.which
    try:
        p = fn(name)
    except Exception:  # noqa: BLE001 — шукач не валить виклик модуля: «не знайдено»
        return None
    return p if isinstance(p, str) and p else None


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


def _folder_rule(space):
    """`ctx['folder_ok']`: правила теки публікації (`folder_ok`), привʼязані до простору `space`, — `f(folder) ->
    (True, None) | (False, код)`. Модуль публікації не імпортує ні `serve`, ні це ядро, тож перевіряє теку
    ще раз (на кожній публікації й у `check`) саме цим викликом."""
    def folder_ok_here(folder):
        return folder_ok(space, folder)
    return folder_ok_here


def _cache_dir(space, m):
    """`ctx['cache_dir']` — `<DEAI_HOME>/cache/<простір>/<модуль>`, ЛИШЕ шлях (нічого не створює). Сегменти не можуть вивести шлях з
    кешу: id простору береться, лише коли це `str` за `spaces.SPACE_ID_RE`, інакше `_` (чужа форма запису без/з дивним id — так само,
    як і без `id`; справжній id `_` мати не може). Id модуля з каталогу вже перевірено маніфестом (`ID_RE`, збіг із текою), тож
    інший — помилка ядра (`module-error`), а не спільне відро `_` для різних модулів: їхні кеші змішалися б."""
    if not isinstance(m.id, str) or not ID_RE.fullmatch(m.id):
        raise ModuleError('module-error', message='module id is not a valid folder name')
    raw = space.get('id') if isinstance(space, dict) else None
    sid = raw if isinstance(raw, str) and spaces.SPACE_ID_RE.fullmatch(raw) else '_'
    return os.path.join(spaces.home(), 'cache', sid, m.id)


def _ctx(space, m):
    cache_dir = _cache_dir(space, m)
    explicit = space_modules(space)
    settings = resolve_settings(space, m, _entry_state(m, space, explicit)['settings'])
    # секрети читаємо лише в модуля, що їх оголосив: зіпсований `secrets.json` не ламає css-tokens
    secrets = read_secrets(_space_id(space), m.id) if m.secret_keys() else {}
    # `folder_ok` і `ModuleError` — не дані, а засоби: модуль їх не імпортує (див. docstring модуля), а `call()`
    # пропускає як є лише `ModuleError` ядра, тож свою помилку з кодом (`bad-folder`) модуль кидає цим класом.
    # `ctx` нікуди не серіалізується: у `call`/`check` з нього береться лише `secrets`.
    # `cache_dir` — лише ШЛЯХ (`_cache_dir`; 4a: дзеркала `git-sync`). Теку створює модуль (`makedirs` 0700): `_ctx` будується для
    # кожного `check`, і створення тут падало б на незаписуваному `DEAI_HOME`.
    # `find_tool` — функція, а не готовий шлях: `_node_bin` ядра може запускати login-shell, тож шукаємо лише коли модуль попросить.
    return {'space': {'id': _space_id(space), 'path': _space_path(space)},
            'settings': settings, 'secrets': secrets,
            'folder_ok': _folder_rule(space), 'ModuleError': ModuleError,
            'cache_dir': cache_dir, 'find_tool': _find_tool}


def module_ctx(space, module):
    """`ctx` для функцій модуля — `{"space": {id, path}, "settings": {…підставлені…}, "secrets": {…лише
    його оголошені…}, "folder_ok": f(folder) -> (ok, код), "ModuleError": клас, "cache_dir": шлях, "find_tool": f}`; `module` — `Module`
    чи id. Перші три — дані, `folder_ok` і `ModuleError` — засоби ядра для модуля, що не імпортує ядро (`static-publish`),
    `find_tool` — функція `f('npx'|'node') -> шлях | None` (4b-1; будь-яке інше імʼя → `None`),
    `cache_dir` — шлях теки кешу модуля в просторі (теки ядро НЕ створює: це робить модуль; `_` замість id простору, коли той не
    за `spaces.SPACE_ID_RE`; `module-error`, коли id модуля не за `ID_RE`).
    Саме це отримує `check`; для `serve.py` (`/api/ds-tokens`, диспетчер публікації). Може кинути
    `unknown-module`, `bad-settings`, `space-json-unreadable`, `secrets-unreadable`, `module-error` (id обʼєкта-модуля не за
    `ID_RE`: з нього складається `cache_dir`). Статус модуля не
    перевіряє (це робить `call`)."""
    m = module if isinstance(module, Module) else _need_module(module, space)
    return _ctx(space, m)


def _remember(space, module_id, res):
    with _STATE_LOCK:
        _LAST_CHECK[(_space_id(space), module_id)] = dict(res)


def last_check(space_id, module_id):
    """Останній результат `check` (копія) або `None`, якщо ще не перевіряли."""
    with _STATE_LOCK:
        res = _LAST_CHECK.get((space_id, module_id))
    return dict(res) if res is not None else None


def forget_check(space_id, module_id):
    """Забути останній `check` модуля в просторі й кеш `capabilities` простору (довіра змінила код, що виконуватиметься)."""
    with _STATE_LOCK:
        _LAST_CHECK.pop((space_id, module_id), None)
        _CAPS.pop(space_id, None)


def check(space, module_id):
    """Результат `check` модуля — `{"ok": bool, "error"?: str, "detail"?: str}` (рядки без секретів,
    ≤300), з `ctx` (налаштування підставлені, секрети ЦЬОГО модуля), тайм-аут — `check_timeout_s` маніфесту, інакше
    `CHECK_TIMEOUT`.
    Останній результат запамʼятовується в `_LAST_CHECK` (для `GET /api/modules`). `ok: false` від
    модуля — звичайний результат; а `module-error`, `check-timeout`, `bad-settings` (обовʼязкове
    налаштування не задане / не те значення) — винятки, і перед викидом вони теж запамʼятовуються як
    `{"ok": false, "error": <код>, "detail": <текст>}`. Для модуля, якого нема чи який не завантажився, і
    для `space-json-unreadable`/`secrets-unreadable` — винятки без запису."""
    m = _need_module(module_id, space)
    if m.status != 'ok':
        raise ModuleError(m.error_code or 'module-error', message=m.error or '')
    try:
        ctx = _ctx(space, m)
    except ModuleError as e:
        if e.code == 'bad-settings':
            _remember(space, module_id, {'ok': False, 'error': e.code, 'detail': e.message})
        raise
    try:
        res = call(m, 'check', ctx, timeout=m.check_timeout_s or CHECK_TIMEOUT)
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

#: Вбудовані модулі, що ведуть коментарі (роль `comments`), і вбудовані модулі інших ролей. Нащо вони тут: запис у
#: `space.json`, якого немає в каталозі чи чий маніфест не розібрано, сам про свої ролі нічого не скаже, а відрізнити
#: «загубився модуль коментарів» від «лежить застарілий запис якогось іншого модуля» потрібно (див.
#: `_enabled_module_is_lost`). Новий вбудований модуль — у котрийсь із двох списків (інваріант у `test_comments_role.py`).
KNOWN_COMMENTS_MODULES = frozenset({'supabase-comments'})
# ⚠️ Явно ввімкнений, але зламаний ВБУДОВАНИЙ `supabase-dashboard` у просторі з інтеграціями веде роль на папері (`_paper_failure`);
# рольова перевірка загубленого модуля для `dashboard` — відкладена.
KNOWN_OTHER_MODULES = frozenset({'css-tokens', 'git-sync', 'static-publish', 'vercel-publish',
                                'supabase-dashboard', 'jira-tracker', 'supabase-teams'})


def _enabled_module_is_lost(cat, explicit):
    """Чи є в `space.json` ЯВНО ввімкнений запис модуля, що вів коментарі, але ним бути не може. Правило (запис `mid`,
    `m = cat.get(mid)`; вимкнені записи й справні модулі — не в рахунок):

      * `m` є, не завантажився й його маніфест ОГОЛОШУЄ `comments` (`'comments' in m.roles`) — так;
      * `m` є, не завантажився, а ролі невідомі (`roles` порожні: маніфест не розібрано чи не пройшов перевірку), — так,
        КРІМ id вбудованого модуля іншої ролі (`KNOWN_OTHER_MODULES`: зламаний `css-tokens` коментарів не вів); для СВОГО
        модуля ролі тоді беруться із запису `space.json` (їх пише вмикання): запис без `comments` коментарів не веде;
      * `m` немає в каталозі, — так лише для id вбудованого модуля коментарів (`KNOWN_COMMENTS_MODULES`); решта —
        застарілий запис (модуль прибрали, теку джерел більше не названо), і він шлях ЛІГА не вимикає;
      * модуль завантажився без ролі `comments` (і зламаний модуль чужої ролі з розібраним маніфестом) — ні.

    Тобто мовчки не губиться те, що справді могло вести коментарі, а чужий пил у `space.json` — не привід лишити
    ЛІГА без її коментарів."""
    for mid, e in explicit.items():
        if not e['enabled']:
            continue
        m = cat.get(mid)
        if m is None:
            if mid in KNOWN_COMMENTS_MODULES:
                return True
            continue
        if m.status == 'ok':
            continue
        roles = m.roles or (e.get('roles', []) if m.origin == 'space' else [])   # свій модуль із зламаним маніфестом — ролі із запису
        if 'comments' in roles or (not roles and mid not in KNOWN_OTHER_MODULES):
            return True
    return False


def _paper_failure(role, cat, explicit):
    """`ModuleError` для ролі `role`, яку «на папері» веде явно ввімкнений СВІЙ модуль, що тут не працює, — або `None`.
    Модуль у каталозі, свій і не `ok` → `module-untrusted` (недовірений) чи `module-error`; модуля в каталозі нема, а
    запис `space.json` несе `roles` із цією роллю (їх пише вмикання свого модуля) → `module-error` (тека не приїхала чи
    зникла). Позначка `paper` каже `capabilities`, що роль — `None`, а не помилка простору."""
    for mid in sorted(explicit):
        e = explicit[mid]
        if not e['enabled']:
            continue
        m = cat.get(mid)
        if m is not None:
            if m.origin != 'space' or m.status == 'ok' or role not in (m.roles or e.get('roles', [])):
                continue
            code = 'module-untrusted' if m.error_code == 'module-untrusted' else 'module-error'
            err = ModuleError(code, message=f'{mid}: {m.error or UNTRUSTED_TEXT}')
        elif role in e.get('roles', ()):
            err = ModuleError('module-error', message=f'{mid}: the module folder is missing')
        else:
            continue
        err.paper = True
        return err
    return None


def _provider_for(role, space, get_cat=None, explicit_override=None):
    """Модуль чи `None` — для вже відомого простору `space`. Запасного постачальника нема (4d-4b): роль без явно ввімкненого запису — `None`.
    Неявний простір — `None` ДО каталогу. Нечитабельний `space.json` — `space-json-unreadable` для КОЖНОЇ ролі.

    СВІЙ модуль, ЯВНО ввімкнений у `space.json` і не робочий тут (недовірений, `refused`, збій завантаження, теки нема), веде
    свої ролі «на папері» (`_paper_failure`): `module-untrusted`/`module-error` для БУДЬ-ЯКОЇ такої ролі й у будь-якому
    просторі, ДО пошуку переможця — ні неявного `static-publish`. Помилка несе позначку `paper`.
    `get_cat` — ледача вибірка каталогу (`capabilities` ділить її між ролями); без неї — `catalog(space)`.
    `explicit_override` — готові явні рішення (форма `space_modules`: `{id: {enabled, settings, …}}`) ЗАМІСТЬ читання `space.json` з
    диска: так міграція ЛІГИ (`liga_migrate.plan`, 4d-3a) перевіряє розрахований `space.json` В ПАМʼЯТІ, нічого не пишучи. Лише
    для цього; звичайні виклики його не передають.

    ВИНЯТОК для `comments` (див. docstring модуля, «приватність» і «видимість»): явно ввімкнений модуль коментарів, що не
    завантажився (`_enabled_module_is_lost`), — `module-error` у БУДЬ-ЯКОМУ просторі, а не тиша: `None` лишив би людину без
    командних коментарів і без жодної причини. Простір без жодного запису про коментарі лишається `None`."""
    if spaces._is_implicit(space):
        # ⛔ Неявний простір (шар вимкнено чи простір запиту не зафіксовано) — «стан не справжній»: ролей у ньому нема (4d-4b), БЕЗ
        # `space_modules` і каталогу (його порожній `path` інакше читався б як «поточна тека процесу»).
        return None
    explicit = space_modules(space) if explicit_override is None else explicit_override   # `space-json-unreadable` — для КОЖНОЇ ролі
    cat = get_cat() if get_cat is not None else catalog(space)
    paper = _paper_failure(role, cat, explicit)
    if paper is not None:
        raise paper                                     # свій модуль веде роль на папері: ні неявного `static-publish`
    winners = []
    for mid in sorted(cat):
        m = cat[mid]
        if m.status != 'ok' or role not in m.roles:
            continue
        en, by_default = _enabled_in(m, space, explicit)
        if en:
            winners.append((by_default, mid, m))
    if winners:
        winners.sort(key=lambda w: (w[0], w[1]))        # явно ввімкнений — перед неявним
        return winners[0][2]
    if role == 'comments' and _enabled_module_is_lost(cat, explicit):
        raise ModuleError('module-error', message=COMMENTS_MODULE_BROKEN)
    if _builtin_role_is_lost(role, cat, explicit):
        raise ModuleError('module-error', message=BUILTIN_MODULE_BROKEN % _BUILTIN_ROLE_MODULE[role])
    return None


#: Вбудований модуль кожної ролі ЛІГИ (запис `space.json` з тим самим id веде роль). Рішення контролера 4d-4b: ЯВНО ввімкнений запис, який обслужити
#: нічим (модуля нема в каталозі чи він не `ok`), — ПОМИЛКА для будь-якої ролі, а не мовчазне `None` (інакше здорова ЛІГА тихо втратила б, напр.,
#: `vcs`: до 4d-4b це був «not loaded»). `comments` має ще й свій, ширший розбір (`_enabled_module_is_lost`).
_BUILTIN_ROLE_MODULE = {'publish': 'vercel-publish', 'comments': 'supabase-comments', 'vcs': 'git-sync',
                        'dashboard': 'supabase-dashboard', 'tracker': 'jira-tracker', 'notify': 'supabase-teams'}
BUILTIN_MODULE_BROKEN = 'модуль %s простору не завантажився — роль вимкнено'


def _builtin_role_is_lost(role, cat, explicit):
    """Чи ЯВНО ввімкнений запис вбудованого модуля ролі `role` не можна обслужити: модуля нема в каталозі або він не `ok`."""
    mid = _BUILTIN_ROLE_MODULE.get(role)
    e = explicit.get(mid) if mid else None
    if not isinstance(e, dict) or not e.get('enabled'):
        return False
    m = cat.get(mid)
    return m is None or m.status != 'ok'


def provider(role, space=None):
    """Хто виконує роль у просторі: `Module` чи `None` (запасного постачальника нема, 4d-4b). Неявний типовий модуль є лише в `publish` (`static-publish`).

    `space` — запис реєстру; не заданий → простір запиту з шва `spaces.effective_space()`: шар вимкнено чи простір запиту НЕ
    зафіксовано (`request_space_id() is None`: інструменти ЛІГА, воркери, тести без ізоляції) → неявний простір, а в ньому
    ролей нема (`None`) — БЕЗ читання реєстру, `space.json` і каталогу;
    простору нема (`None`) → `None`. Явно переданий `space` вирішується сам по собі, незалежно
    від стану запиту. Явно чи неявно ввімкнений `ok`-модуль із роллю перемагає; інакше `None`. Каталог — з СВОЇМИ модулями простору
    (`catalog(space)`): явно ввімкнений свій модуль, що тут не працює, веде роль «на папері» — `ModuleError`
    (`module-untrusted`/`module-error`), без запасного шляху (`_paper_failure`).
    ⚠️ НІКОЛИ не кликати під `spaces.WRITE_LOCK`: для простору запиту це `spaces.active_space()`, а той може
    мігрувати реєстр (бере лок), а `catalog()` виконує код модулів. Може кинути `spaces.SpacesError` (реєстр
    не прочитати) і `ModuleError('space-json-unreadable')` (простір без інтеграцій, `space.json` є, але не
    читається) — для списків і опитування є `capabilities()`, яка не кидає."""
    if space is None:
        space = spaces.effective_space()
        if space is None:
            return None
    return _provider_for(role, space)


def api_value(p):
    """Єдина точка відображення постачальника НАЗОВНІ: `Module` → його id, `None` → `None`. Усе інше (зокрема голий рядок) — `TypeError`:
    тихе «пропустити як є» розмило б межу між внутрішнім постачальником і зовнішнім літералом (запасного `Implicit` більше нема, 4d-4b)."""
    if p is None:
        return None
    if isinstance(p, Module):
        return p.id
    raise TypeError(f'постачальник ролі: очікувано Module чи None, отримано {type(p).__name__}')


def own_sig(space):
    """Відбиток своїх модулів простору для ключів кешів: `fingerprint` кожної підтеки `modules/`, відбиток `trust.json` і
    `fingerprint` знімків, на які вказують записи довіри ЦЬОГО простору (за `key_for`): пошкоджений знімок змінює стан
    модуля (`snapshot-damaged`), і `capabilities` мусить це побачити. Лише `lstat`/`listdir`: нічого не виконує й не хешує
    (шлях ЛІГА лишається «до каталогу»); нечитабельний `trust.json` — знімків нема."""
    base = _own_base(space)
    if base is None:
        return None
    try:
        names = sorted(os.listdir(base))[:MAX_OWN_MODULES * 4]
    except OSError:
        names = []
    try:
        records = module_trust.load_records()
    except module_trust.TrustUnreadable:
        records = {}
    snaps = []
    for n in names:
        rec = records.get(module_trust.key_for(_space_path(space), n))
        if rec is not None:
            snaps.append((n, rec['hash'], module_trust.fingerprint(module_trust.snapshot_dir(rec['hash']))))
    return (tuple((n, module_trust.fingerprint(os.path.join(base, n))) for n in names), module_trust.records_sig(),
            tuple(snaps))


def _caps_key(space):
    jp = _space_json_path(space)
    return (_space_id(space), _space_path(space),
            _sig(jp) if jp else None, _catalog_sig(), own_sig(space))


def capabilities(space):
    """`{"publish": id | None, "tokens": id | None, "comments": id | None, "vcs": id | None, "dashboard": id | None,
    "tracker": id | None, "notify": id | None}` для простору `space` (запис реєстру): id модуля, що веде роль, або `None` — ролі
    ніхто не веде. Запасного значення `'legacy'` більше нема (4d-4b): ЛІГА — звичайний простір із явними записами. ТОТАЛЬНА: не кидає
    ніколи. Якщо вирішити роль не вдалось (`ModuleError`, типово нечитабельний `space.json`), та роль — `None`, а в результаті є
    ключ `error` з кодом: кожна роль вирішується окремо, решта віддають своє. Без помилки ключа `error` нема. Просторовий збій — лише
    `error == 'space-json-unreadable'`; будь-який інший код — збій модуля, названий ще й за роллю в `errors` (`{роль: код}`; ключа нема,
    коли всі збої просторові). Роль, яку «на папері» веде свій модуль, що тут не працює (`_paper_failure`), — `None`
    без ключа `error`: це стан ролі, а не простору (екран «Підключення» показує `error` як нечитабельний `space.json` і
    ховає картки — разом із «Довіритись…»). Кеш за (простір, відбиток `space.json`, теки джерел модулів (`DEAI_EXTRA_MODULES` теж), відбитки `module.json`,
    `server.py` і файлів `*.js` адаптера кожного модуля, відбиток своїх модулів і `trust.json`, `own_sig`); повертає копію. `None`, порожнє чи не-словник замість простору — нічого не вміє."""
    return _capabilities_full(space)[0]


#: Єдиний код `capabilities.error`, що означає ПРОСТІР-рівневий збій («space.json не читається»: клієнт ховає всі картки модулів).
#: Решта кодів — збій модуля КОЖНОЇ/однієї ролі: вони ще й іменні в `capabilities.errors` (роль → код), картки лишаються.
SPACE_LEVEL_ERROR = 'space-json-unreadable'


def _copy_caps(caps):
    """Копія `caps` з власним `errors` (поверхнева копія ділила б вкладений словник між кешем і викликачами)."""
    out = dict(caps)
    if isinstance(out.get('errors'), dict):
        out['errors'] = dict(out['errors'])
    return out


def _capabilities_full(space):
    """`(caps, raw)`: `caps` — те, що віддає `capabilities` (значення назовні, через `api_value`), `raw` — ті самі рішення ролей
    як `Module`/`None` (лише для `publish_module`: рішення «публікує модуль» береться з ТОГО Ж проходу й ТОГО Ж кешу,
    що й `capabilities`, а не вгадується з рядка). Тотальна, як `capabilities`; при збої відбитків `raw` порожній."""
    if not isinstance(space, dict) or not space:
        return {role: None for role in ROLES_CALLED}, {}
    try:
        key = _caps_key(space)                          # ДО обчислення: зміна під час нього — промах, не застарілий хіт
        sid = _space_id(space)
        with _STATE_LOCK:
            hit = _CAPS.get(sid)
        if hit is not None and hit[0] == key:
            return _copy_caps(hit[1]), dict(hit[2])
        box = {}

        def get_cat():
            if 'c' not in box:
                box['c'] = catalog(space)
            return box['c']
        caps, raw, error, errors = {}, {}, None, {}
        for role in ROLES_CALLED:
            try:
                p = _provider_for(role, space, get_cat)
                caps[role] = api_value(p)
                raw[role] = p
            except ModuleError as e:
                if getattr(e, 'paper', False):
                    caps[role] = None       # роль «на папері» за своїм модулем, що тут не працює: не `'legacy'` і НЕ
                    continue                # `error` — клієнт читає `error` як «space.json не читається» й сховав би картки
                error = error or e.code
                errors[role] = e.code
                caps[role] = None
            except TypeError:
                # `api_value` не впізнав постачальника цієї ролі (свій баг, не стан простору): падає ЛИШЕ ця роль, решта п'ять живі.
                error = error or 'module-error'
                errors[role] = 'module-error'
                caps[role] = None
        if SPACE_LEVEL_ERROR in errors.values():
            error = SPACE_LEVEL_ERROR           # простір-рівневий стан не ховається за порядком ролей («перший код виграє»)
        if error:
            caps['error'] = error
            if any(code != SPACE_LEVEL_ERROR for code in errors.values()):
                caps['errors'] = errors     # r15-1: збій ролі названий за роллю; клієнт ховає картки лише за `SPACE_LEVEL_ERROR`
        with _STATE_LOCK:
            _CAPS[sid] = (key, _copy_caps(caps), dict(raw))
        return _copy_caps(caps), raw
    except Exception:  # noqa: BLE001 — тотальність: збій відбитків/каталогу не ламає опитування
        caps = {role: None for role in ROLES_CALLED}
        caps['error'] = 'module-error'
        caps['errors'] = {role: 'module-error' for role in ROLES_CALLED}
        return caps, {}


def publish_module(space):
    """Модуль, що ПУБЛІКУЄ в просторі запиту `space` (роль `publish`), або `None`. ТОТАЛЬНА: не кидає ніколи; шлях ЛІГИ (`publish_legacy_path`: вбудований `vercel-publish` із `compat == "design-canvas"`), `None`, `ModuleError`, збій
    відбитків — `None` (обидва споживачі, `task_preview_gate` і `task_publish_share`, тому не міняються: для них публікація
    ЛІГИ — не «модуль»). Рішення те саме, що `capabilities(space)['publish']`, і з ТИМ САМИМ кешем
    (`_capabilities_full`): `capabilities` зберігає поруч сирих постачальників, а назовні віддає `api_value`.
    Шар вимкнено чи простір запиту не зафіксовано — модулів нема (`None`) без читання реєстру й каталогу, як і в 0.15.0: у
    такому запиті `spaces.active_space()` міг би показати «поточний» простір реєстру, який запит не обирав."""
    try:
        if not (space and spaces.layer_on() and spaces.request_space_id() is not None):
            return None
        p = _capabilities_full(space)[1].get('publish')
        return p if isinstance(p, Module) and not publish_legacy_path(p, space) else None
    except Exception:  # noqa: BLE001 — тотальність
        return None


#: Вбудований модуль публікації в Vercel (4b-1): його запис із `compat == "design-canvas"` — публікація ЛІГИ (4d-3c).
PUBLISH_MODULE = 'vercel-publish'


def publish_legacy_path(prov, space=None):
    """ЄДИНА умова «публікація йде шляхом ЛІГИ» (проєкти `pv-…` і скоуп із `tasks.json`, пароль превʼю задачі/секрету/`1100`, гілка
    `Handler._publish` для ЛІГИ): вбудований `Module` `vercel-publish` із `compat == "design-canvas"` у `space.json`
    простору `space` (`None` — `spaces.active_space()`). ТОТАЛЬНА: будь-який збій — `False`, не виняток. Очікує постачальника, якого
    віддав `provider()` (статус/«ввімкнено» там уже відфільтровано): сама їх не перевіряє.

    ⛔ ЛІГА — запис реєстру, а не тип постачальника (урок 4d-3a/4d-3b): після міграції постачальник — звичайний `Module`, і
    рішення читається лише звідси. Лише вбудований І саме цей id: свій модуль простору міг би оголосити власне `compat` з іншим
    змістом, а `compat` інших модулів (`supabase-comments`, `git-sync`…) — про інші ролі."""
    try:
        return bool(isinstance(prov, Module) and getattr(prov, 'origin', 'builtin') == 'builtin' and prov.id == PUBLISH_MODULE
                    and compat_of(space or spaces.active_space(), PUBLISH_MODULE) == COMPAT_DESIGN_CANVAS)
    except Exception:  # noqa: BLE001 — тотальність: збій читання не ламає рішення про шлях публікації
        return False


def publish_password(space):
    """Пароль превʼю ЛІГИ з СЕКРЕТУ `password` явного `vercel-publish` (4d-4b: корінь `tasks.json` більше не читається) або `None` — тоді
    пароль веде задача чи типовий `1100` (`serve.preview_password`). Умова — та сама `publish_legacy_path(prov, space)`, що веде гілку
    ЛІГИ публікації: вбудований `vercel-publish` із `compat == "design-canvas"`; модуль-режим (`compat` порожній) цього секрета читає
    САМ (`publish_with_module`), тож тут `None`. ⛔ Закон ізоляції (Д6): ізольований прогін у СПРАВЖНЬОМУ домі
    (`isolation.real_home`) — `None` (спільний секрет не беремо); у тимчасовому домі тесту — секрет фікстури.

    ⛔ ЄДИНИЙ виняток із тотальності — `ModuleError('secrets-unreadable')`: файл секретів ІСНУЄ, але не читається. Тоді пароль не можна
    мовчки замінити спільним `1100` (відкрите превʼю замість закритого), тож помилка йде до виклику, а публікація відмовляє.
    Нема файла чи ключа — `None`. Решта збоїв — `None`."""
    try:
        if not isinstance(space, dict) or not space or spaces._is_implicit(space) or not spaces.layer_on():
            return None
        if isolation.isolated() and isolation.real_home(spaces.home()):
            return None
        prov = _capabilities_full(space)[1].get('publish')
        if not publish_legacy_path(prov, space):
            return None
        sid = _space_id(space)
    except Exception:  # noqa: BLE001 — тотальність: збій визначення шляху не ламає `/api/task`
        return None
    try:
        return read_secrets(sid, PUBLISH_MODULE).get('password') or None
    except ModuleError as e:
        if e.code == 'secrets-unreadable':
            raise                                  # fail-CLOSED: не підміняти закритий пароль відкритим типовим
        return None
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------------------ роль `comments` (2b-2)

#: Текст відмови, коли `client_config` показує значення НЕпублічного секрету: фіксований, без жодних значень.
CLIENT_CONFIG_LEAK = 'client_config contains the value of a secret that is not marked public'
_FLAT_TYPES = (str, int, float, bool, type(None))


def _config_refused(why):
    return ModuleError('module-error', message=f'client_config: {why}')


def _text_views(t):
    """Текст і його розкодовані `%XX`/`+` вигляди: секрет, перекодований як `quote` (з `/` у safe), `quote_plus` чи
    `urlencode`, знаходиться тут же, де й сирий."""
    return {t, unquote(t), unquote_plus(t)}


def _check_client_config(cfg, guarded):
    """Перевірка відповіді `client_config` (`cfg` — уже ЗНІМОК модульного обʼєкта, див. `comments_client`): плаский
    JSON-обʼєкт ≤ `MAX_CLIENT_CONFIG` (`json.dumps`) зі `str`/`int`/`float`/`bool`/`None`; жодне значення з `guarded`
    (секрети без `"public": true`) не міститься в КЛЮЧАХ чи значеннях конфігу: підрядок будь-якої довжини ≥ 1 у сирому
    вигляді, у `repr`/JSON-екрануванні, URL-кодуванні, а також після `unquote`/`unquote_plus` тексту (числа — як текст).
    Усі тексти відмов фіксовані: ні значень секретів, ні вмісту конфігу, ні його ключів.

    ⚠️ Це охоронець від ВИПАДКОВОГО витоку (модуль поклав секрет у конфіг, склав із ним адресу). Навмисно сховану форму
    (нижній регістр, base64, шматки, розбиті між полями) він не бачить — це не межа довіри: модулі вбудовані."""
    try:
        _check_client_config_shape(cfg, guarded)
    except (ValueError, OverflowError):                 # `UnicodeError` — підклас `ValueError`; напр. int із >4300 цифр
        raise _config_refused('is not serializable') from None


def _check_client_config_shape(cfg, guarded):
    """Тіло `_check_client_config`: відмови `ModuleError` — свої, а будь-який `ValueError`/`UnicodeError`/
    `OverflowError`, якого ніхто не передбачив, перехоплює обгортка."""
    if not isinstance(cfg, dict):
        raise _config_refused('must be an object')
    for k, v in cfg.items():
        if not isinstance(k, str):
            raise _config_refused('keys must be strings')
        if type(v) not in _FLAT_TYPES:
            raise _config_refused('values must be strings, numbers, booleans or null')
        if type(v) is float and not math.isfinite(v):
            raise _config_refused('numbers must be finite')
        if not _encodable(k) or (type(v) is str and not _encodable(v)):
            raise _config_refused('strings must be valid text (no lone surrogates)')     # інакше ламає відповідь сторінки
    if len(json.dumps(cfg)) > MAX_CLIENT_CONFIG:
        raise _config_refused(f'bigger than {MAX_CLIENT_CONFIG} bytes')
    forms = _secret_forms(guarded)
    if not forms:
        return
    texts = [*cfg, *(v if isinstance(v, str) else str(v) for v in cfg.values() if v is not None and type(v) is not bool)]
    if any(f in view for t in texts for view in _text_views(t) for f in forms):
        raise ModuleError('module-error', message=CLIENT_CONFIG_LEAK)


def comments_client(space, prov, ctx=None):
    """Публічна конфігурація браузерного адаптера модуля `prov` (ролі `comments`) для сторінок простору `space`:
    `client_config(ctx)` модуля (тайм-аут `CHECK_TIMEOUT`), перевірена `_check_client_config` — це те, що ядро вставляє в
    сторінки як `{...конфіг, channel}`. Секрет з `"public": true` показувати можна, решта — ні (`module-error` із
    фіксованим текстом); «решта» — це `Module.private_secret_keys()` і будь-який ключ `secrets.json`, якого нема в
    маніфесті. Модульний обʼєкт СПЕРШУ копіюється, перевіряється й віддається саме копія: те, що перевірено, і є тим,
    що піде в сторінки (модуль міг тримати посилання на свій словник чи підсунути підклас `dict`). Може кинути
    `bad-settings`, `space-json-unreadable`, `secrets-unreadable`, `check-timeout`, `module-error`.
    `ctx` — необовʼязковий ГОТОВИЙ `ctx` постачальника (4b-2: простір ЛІГА будує його з конфігу установки —
    `serve._comments_legacy_ctx`, — бо `space.json` і `secrets.json` у ньому нема); `None` — `_ctx(space, prov)`, як раніше.
    Перевірка на витік секретів лишається тією самою: вона бере секрети з ЦЬОГО `ctx`.
    ⚠️ Виконує код модуля: НЕ кликати під `spaces.WRITE_LOCK`."""
    if not isinstance(prov, Module) or prov.status != 'ok' or 'comments' not in prov.roles:
        raise ModuleError('module-error', message='comments_client: the provider is not a loaded comments module')
    ctx = _ctx(space, prov) if ctx is None else ctx
    cfg = call(prov, 'client_config', ctx, timeout=CHECK_TIMEOUT)
    if isinstance(cfg, dict):
        try:
            cfg = dict(cfg)
        except Exception:  # noqa: BLE001 — підклас `dict` із власним `keys()`/`__getitem__`, що кидає
            raise _config_refused('must be a plain object') from None
    private, declared = set(prov.private_secret_keys()), set(prov.secret_keys())
    guarded = {k: v for k, v in ctx['secrets'].items() if k in private or k not in declared}
    _check_client_config(cfg, guarded)
    return cfg


def channel_for(space, tid, internal=False):
    """Канал коментарів задачі `tid` простору `space`: `deai/<id простору>/<tid>` (внутрішній — `…/internal`). Ядро
    будує канал само й віддає модулю готовим: той самий id задачі в двох просторах не ділить коментарі. Id простору — за
    `spaces.SPACE_ID_RE`, id задачі — непорожній рядок без `/` і керівних символів: інакше `a`+`b/t` і `a/b`+`t` дали б
    один канал."""
    sid = _space_id(space) if isinstance(space, dict) else ''
    if (not spaces.SPACE_ID_RE.fullmatch(sid) or not isinstance(tid, str) or not tid
            or any(c == '/' or ord(c) < 32 or ord(c) == 127 for c in tid)):
        raise ModuleError('module-error', message='channel: a valid space id and a task id (no "/" or control characters) are required')
    return f'deai/{sid}/{tid}' + ('/internal' if internal else '')


#: Вбудований модуль командних коментарів і значення його налаштування `compat` (4d-3b): схема каналів ЛІГИ (`comment_project`
#: або `dc/<задача>`) — історія пінів, тиша Teams і лічильники дашборда прив'язані до цього каналу.
COMMENTS_MODULE = 'supabase-comments'
COMPAT_COMMENT_LAYER = 'comment-layer'


def compat_of(space, module_id):
    """Сире налаштування `compat` запису `module_id` у `space.json` простору (лише `str`, інакше `""`). ТОТАЛЬНА: нема запису,
    не-`str`, нечитабельний `space.json`, нема теки простору — `""`, не виняток. Каталог не читаємо (Поправка 2): рівність
    перевіряється лише з двома дозволеними значеннями, а недозволене `resolve_settings` усе одно відкидає (`bad-settings`)."""
    try:
        v = space_modules(space).get(module_id, {}).get('settings', {}).get('compat')
        return v if isinstance(v, str) else ''
    except Exception:  # noqa: BLE001 — тотальність: збій читання не ламає рішення про канал
        return ''


#: Вбудований модуль синку з git і значення його налаштування `compat` (4d-3b): плоскі дзеркала й тексти 0.7.0 («design-canvas», «GitLab»).
VCS_MODULE = 'git-sync'
COMPAT_DESIGN_CANVAS = 'design-canvas'
#: Ролі, чий явний вбудований модуль має `compat`, що видно клієнту: `{роль: id модуля}`.
COMPAT_ROLES = (('comments', COMMENTS_MODULE), ('vcs', VCS_MODULE), ('publish', PUBLISH_MODULE))
#: Єдине дозволене непорожнє значення `compat` ролі (клієнту віддаємо лише його; сире з `space.json` — ні).
COMPAT_ALLOWED = {'comments': COMPAT_COMMENT_LAYER, 'vcs': COMPAT_DESIGN_CANVAS, 'publish': COMPAT_DESIGN_CANVAS}


def vcs_outbound(space):
    """Чи може простір ходити назовні гітом за схемою ЛІГИ (4d-4c): простір має ВВІМКНЕНИЙ вбудований запис `git-sync` із
    `compat == "design-canvas"` — той самий факт, який клієнт читає як `isLegacyVcs`. Замінює прапорець `integrations`: автопуш,
    пуш у реєстр команди, `ssh_key`/`host_ip` цілі й `gitlab`-маппінг нової задачі питають лише це.
    ТОТАЛЬНА: нема простору, неявний простір, шар вимкнено, `ModuleError`, нечитабельний `space.json`, збій відбитків — `False`
    (закрито, не виняток). Кеш — той самий `_capabilities_full` (ключ `_caps_key` містить відбиток `space.json`)."""
    try:
        if not isinstance(space, dict) or not space or spaces._is_implicit(space) or not spaces.layer_on():
            return False
        p = _capabilities_full(space)[1].get('vcs')
        return (isinstance(p, Module) and getattr(p, 'origin', 'builtin') == 'builtin' and p.id == VCS_MODULE
                and compat_of(space, VCS_MODULE) == COMPAT_DESIGN_CANVAS)
    except Exception:  # noqa: BLE001 — тотальність
        return False


def compat_view(space, caps):
    """Ключ `compat` обʼєкта простору: `{роль: значення}` лише для ролей, які веде ЯВНИЙ вбудований модуль (`caps[роль]` — його id)
    з непорожнім `compat` у `space.json`. Порожній словник — ключа в обʼєкті простору нема (Поправка 4). ТОТАЛЬНА: не кидає
    (`compat_of` сама тотальна; не-словник `caps` — `{}`). Клієнт читає звідси «ЛІГА за налаштуванням» (`isLegacyVcs`)."""
    out = {}
    if not isinstance(caps, dict):
        return out
    try:
        raw = _capabilities_full(space)[1]          # кеш того ж проходу, що й `capabilities`: каталог знову не обходимо
    except Exception:  # noqa: BLE001 — тотальність
        return out
    for role, mid in COMPAT_ROLES:
        if caps.get(role) != mid:
            continue
        # Захист у глибину: сирий постачальник — саме ВБУДОВАНИЙ `Module` цього id. Свій модуль із тим самим id каркас
        # відхиляє (`id-taken`), але ключ `compat` для клієнта не мусить на це покладатися (як і предикати текстів/каналу).
        p = raw.get(role)
        if not (isinstance(p, Module) and getattr(p, 'origin', 'builtin') == 'builtin' and p.id == mid):
            continue
        v = compat_of(space, mid)
        if v and v == COMPAT_ALLOWED.get(role):
            out[role] = v
    return out


def legacy_comment_channel(task, tid, internal=False):
    """Схема каналу ЛІГИ: `comment_project` задачі або `dc/<tid>` (+ `/internal`). ЄДИНА копія формули: `serve.comment_channel` і
    `dashboard.comment_project_key` — тонкі обгортки."""
    return (task.get('comment_project') or f'dc/{tid}') + ('/internal' if internal else '')


def comment_scheme_legacy(space, prov):
    """ЄДИНА умова «коментарі ведуться за схемою comment-layer»: вбудований `Module` `supabase-comments` із
    `compat == "comment-layer"`. ⛔ Лише вбудований І саме цей id (Поправка 3): свій модуль простору міг оголосити власне `compat`
    з іншим змістом, а `supabase-dashboard`/`supabase-teams` мають СВОЄ `compat` (`comment-layer` — публічний ключ сторінки)."""
    return (isinstance(prov, Module) and getattr(prov, 'origin', 'builtin') == 'builtin' and prov.id == COMMENTS_MODULE
            and compat_of(space, prov.id) == COMPAT_COMMENT_LAYER)


def comment_channel_of(space, prov, task, tid, internal=False, legacy=None):
    """Канал коментарів задачі `tid` для вже вирішеного постачальника `prov`: схема comment-layer (`comment_scheme_legacy`) —
    `legacy_comment_channel`, інакше `channel_for` (`deai/<простір>/<задача>`, може кинути `ModuleError`). УСІ місця каналу ходять
    через цю функцію. `legacy` — вже прийняте рішення `comment_scheme_legacy(space, prov)` (синк рахує його ОДИН раз на прохід, а не
    читає `space.json` на кожну задачу); `None` — порахувати тут."""
    if comment_scheme_legacy(space, prov) if legacy is None else legacy:
        return legacy_comment_channel(task, tid, internal)
    return channel_for(space, tid, internal)


def comments_prov_cached(space):
    """Постачальник ролі `comments` простору `space` з кешу `_capabilities_full` (той самий прохід, що `capabilities`, а не новий
    обхід каталогу на кожен запит), як `publish_module`. ТОТАЛЬНА: шар вимкнено, простір запиту не зафіксовано, збій рішення —
    `None`; НЕ кидає. `Module` чи `None`."""
    try:
        if not (space and spaces.layer_on() and spaces.request_space_id() is not None):
            return None
        return _capabilities_full(space)[1].get('comments')
    except Exception:  # noqa: BLE001 — тотальність
        return None


# ------------------------------------------------------------------------------ довіра своїм модулям (3c)

def _own_or_404(space, mid):
    """Тека свого модуля `mid` простору або `unknown-module` (нема серед своїх; вбудований id — теж)."""
    if not isinstance(mid, str) or not ID_RE.fullmatch(mid):
        raise ModuleError('unknown-module', message=str(mid)[:60])
    cands = dict(_own_listing(space)[0])
    if mid not in cands:
        raise ModuleError('unknown-module', message=f'{mid}: not an own module of this space')
    return cands[mid]


def _is_alias(space, mid):
    """Тека модуля — посилання (аліас): `key_for` бере `realpath`, тож її ключ — ключ ЦІЛІ, тобто чужий запис довіри. Те саме,
    коли посилання — сама `modules` (`B/modules -> A/modules`): `lstat(modules/<id>)` проміжного посилання не бачить, а ключ
    уже вказує в теку чужого простору. Сам простір за посиланням (`~/work -> /Volumes/…`) аліасом не є: його `realpath`
    однаковий для всіх ключів."""
    sp = _space_path(space)
    if os.path.normcase(os.path.realpath(os.path.join(sp, 'modules'))) != os.path.normcase(
            os.path.join(os.path.realpath(sp), 'modules')):
        return True                     # сама `modules` — посилання: ключ вказав би в теку чужого простору
    try:
        return module_trust.is_link(os.lstat(os.path.join(sp, 'modules', mid)))
    except OSError:                     # теки нема — запис за шляхом, «Забрати довіру» зниклої теки працює
        return False


def _trust_setting(s):
    v = {'key': s['key'], 'type': s['type'], 'label': s['label']}
    if s['type'] == 'secret':
        v['public'] = bool(s.get('public'))
    return v


def trust_view(space, mid):
    """Дані діалогу довіри (`GET /api/module-trust`): тека сканується (з кешем відбитка) і порівнюється із записом
    довіри; назва, версія, ролі й налаштування — з маніфесту ТЕКИ (нової версії). Код теки не виконує: для вже довіреного
    модуля вантажиться хіба ЙОГО знімок (`_own_module` лише для `mid` — знімки решти модулів простору не чіпаємо).
    `state` і `refused` — ЛИШЕ зі скану самого діалогу (каталог міг скануватись раніше, і тека встигла змінитись):
    `refused` — з `refused` і без `hash`/`files`; чисте сканування — `trusted`/`changed` за записом і хешем, `untrusted` без
    запису чи коли знімок із записом не працює (пошкоджений)."""
    src = _own_or_404(space, mid)
    try:
        records, rec_err = module_trust.load_records(), None
    except module_trust.TrustUnreadable:
        records, rec_err = {}, 'trust-unreadable'
    m = _own_module(space, mid, src, records, rec_err)
    rec = records.get(module_trust.key_for(_space_path(space), mid)) if m.record else None   # аліас і так без `record`
    out = {'id': mid, 'name': m.name, 'version': m.version, 'roles': list(m.roles), 'settings': [],
           'path': module_trust.tilde(src), 'record': rec is not None}
    try:
        sc = module_trust.scan(src)
    except module_trust.Refused as e:
        out.update(state='refused', refused={'code': e.code, 'detail': e.detail})
        return out
    meta, why = _manifest_from_bytes(sc.manifest, mid, src)
    if why:
        out.update(state='refused', refused={'code': 'bad-manifest', 'detail': why[:MAX_MESSAGE]})
        return out
    if rec is None or m.trust == 'untrusted' or not module_trust.verify_snapshot(rec['hash']):
        state = 'untrusted'                 # знімок не цілий — код із нього не виконується, хоч би що бачив скан каталогу
    else:
        state = 'trusted' if sc.hash == rec['hash'] else 'changed'
    files, removed = module_trust.diff(sc.files, rec['files'] if rec else None)
    out.update(state=state, name=meta['name'], version=meta['version'], roles=list(meta['roles']),
               settings=[_trust_setting(s) for s in meta['settings']], hash=sc.hash, files=files, removed=removed,
               total={'files': len(sc.files), 'bytes': sc.total})
    return out


def grant_trust(space, mid, want_hash, lang='uk'):
    """Довіра своєму модулю `mid` — рівно версії з хешем `want_hash`, яку бачила людина. Порядок (спека, «API»):
    сканування з байтами → `module-refused` / `module-changed` → «другий постачальник» (`role-taken`) → СИСТЕМНЕ ВІКНО
    поза локами (`trust-declined` / `trust-no-confirm` / `trust-busy`) → знімок із просканованих байтів → запис під
    `WRITE_LOCK` (`module-changed`, коли знімок встигли відсунути) → скидання `_LAST_CHECK` і `capabilities`.
    ⚠️ Блокує потік до відповіді людини (до `module_trust.CONFIRM_TIMEOUT` с); НЕ кликати під `WRITE_LOCK`."""
    _require_writable(space)
    src = _own_or_404(space, mid)
    if not isinstance(want_hash, str) or not module_trust.HASH_RE.fullmatch(want_hash):
        raise _bad('hash: expected the 64-character fingerprint shown in the dialog')
    key = module_trust.key_for(_space_path(space), mid)
    try:
        module_trust.load_records()
    except module_trust.TrustUnreadable:
        raise ModuleError('trust-unreadable', message='trust.json is unreadable') from None
    try:
        sc = module_trust.scan(src, with_data=True)
    except module_trust.Refused as e:
        raise ModuleError('module-refused', message=f'{e.code}: {e.detail}'[:MAX_MESSAGE]) from None
    meta, why = _manifest_from_bytes(sc.manifest, mid, src)
    if why:
        raise ModuleError('module-refused', message=f'bad-manifest: {why}'[:MAX_MESSAGE])
    if sc.hash != want_hash:
        raise ModuleError('module-changed', message='the module folder changed after the dialog was opened')
    explicit = space_modules(space)
    if explicit.get(mid, {}).get('enabled') is True:
        probe = types.SimpleNamespace(id=mid, roles=list(meta['roles']))      # ролі НОВОЇ версії теки
        why = _role_conflict(probe, catalog(space), space, explicit)
        if why:
            raise ModuleError('role-taken', message=why)
    texts = module_trust.confirm_texts(lang, meta['name'], mid, sc.hash, module_trust.tilde(src))
    answer = module_trust.ask(key, sc.hash, texts)
    if answer != 'yes':
        code = {'busy': 'trust-busy', 'unavailable': 'trust-no-confirm'}.get(answer, 'trust-declined')
        raise ModuleError(code, message=f'system confirmation: {answer}')
    try:
        module_trust.ensure_snapshot(sc)
        module_trust.put_record(key, {
            'id': mid, 'name': meta['name'], 'version': meta['version'], 'roles': list(meta['roles']),
            'hash': sc.hash, 'files': [{'path': p, 'size': n, 'sha256': h} for p, n, h in sc.files],
            'trusted_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    except module_trust.SnapshotGone:
        raise ModuleError('module-changed', message='the snapshot was removed meanwhile — try again') from None
    except module_trust.TrustUnreadable:
        raise ModuleError('trust-unreadable', message='trust.json is unreadable') from None
    except OSError as e:
        raise ModuleError('unwritable', message=f'trust: {type(e).__name__}') from None
    forget_check(_space_id(space), mid)
    forget_own(sc.hash)                     # завантаження знімка (і закешований збій, як-от тайм-аут) — наново


def revoke_trust(space, mid):
    """Забрати довіру свого модуля `mid` (ключ — за шляхом, тож і для теки, якої вже нема). `space.json` не чіпає;
    `True`, якщо запис був. `trust-unreadable` — файл довіри не читається (не переписуємо)."""
    _require_writable(space)
    if not isinstance(mid, str) or not ID_RE.fullmatch(mid):
        raise ModuleError('unknown-module', message=str(mid)[:60])
    if _is_alias(space, mid):
        return False                    # у аліаса свого запису нема; ключ збігся б із ключем цілі — чужу довіру не чіпаємо
    try:
        removed = module_trust.drop_record(module_trust.key_for(_space_path(space), mid))
    except module_trust.TrustUnreadable:
        raise ModuleError('trust-unreadable', message='trust.json is unreadable') from None
    except OSError as e:
        raise ModuleError('unwritable', message=f'trust: {type(e).__name__}') from None
    forget_check(_space_id(space), mid)
    return removed
