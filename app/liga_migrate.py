"""Міграція простору ЛІГА в явні `tracks` і модулі (етап 4d-3a, 0.17.0; спека `docs/superpowers/specs/2026-11-05-liga-migration-a-design.md`).

Тут — ЧИСТИЙ розрахунок `plan()` і безпечний для друку `report(plan)`: `plan()` нічого не пише на диск. Запис (`run`), відкат
(`restore`), `status` і старт сервера (`startup`) — нижче, після `report()`. Модуль не імпортує `serve` (лише `spaces`,
`deai_modules`, `tracks`, `install_config`, `isolation`).

4d-3b (0.18.0): модуль — ВПОРЯДКОВАНИЙ СПИСОК кроків (`Step`, `ALL_STEPS`/`STEPS`): свій бекап, позначка й відкат на крок; `plan/run/
restore/status` без аргументу `step` — крок 4d-3a; `run_all()`/`startup()`/CLI ідуть по `STEPS` (`abort-*` зупиняє наступні, `skip-*` — ні);
відкат LIFO (`refuse-later-applied`); `last.json` — верхній рівень як у 4d-3a + `step`, і мапа `steps`. Нижче документація 4d-3a.
4d-3c (0.19.0): кроків ТРИ (`liga-4d3a`, `liga-4d3b`, `liga-4d3c`); відкат і підказки — від найпізнішого застосованого до раннього.

`plan(home=None)` → словник:
    status        'ready' | 'skip-*' | 'abort-*' (коди — `SKIP_CODES`, `ABORT_CODES`). 'skip-nothing' — жодна роль і не напрямки не
                  мігрують: `space_json` = None, позначка НЕ пишеться (наступний старт перевірить знову)
    reason        короткий український опис БЕЗ значень секретів і адрес
    space_id      id запису ЛІГИ в реєстрі або `None`; `space_path` — тека, з якої `plan()` рахував (запис іде ТУДИ Ж)
    roles         {'tracker'|'dashboard'|'notify': {'module': id, 'migrate': bool, 'reason': None | код}}; для skip/abort — `{}`
    tracks        bool: чи мігрують напрямки; `tracks_reason` — код, коли ні: `tracks-present`, `tracks-parity` (розраховане не
                  збігається з адаптером), `tracks-unknown-values`. Роль від цього не залежить: ролі мігрують далі
    space_json    НОВИЙ вміст `space.json` (повний, з наявним злитим) або `None`; позначка `migrations['liga-4d3a']` тут має лише
                  `roles` і `tracks` — `at` і `backup` дописує запис (Task 5)
    secrets       {module_id: {ключ: "<значення>"}} — ⛔ значення секретів потрібні ЗАПИСУ; назовні (журнал, звіт) — лише `report()`

⛔ Секрети живуть лише в `plan['secrets']`. `report()` друкує імена ключів, не значення; `plan` не друкувати цілком.
"""
import contextlib
import errno
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import namedtuple
from urllib.parse import urlsplit

import deai_modules
import install_config
import isolation
import spaces
import tracks as tracks_core
from atomic_io import TMP_SUFFIX, DurabilityUnconfirmed, atomic_write_json, fsync_path

try:
    import fcntl
except ImportError:                 # Windows: міжпроцесного замка нема (одна копія канваса на дім — межа спеки)
    fcntl = None

MARK = 'liga-4d3a'
#: Роль → вбудований модуль, у порядку запису.
ROLE_MODULES = (('tracker', 'jira-tracker'), ('dashboard', 'supabase-dashboard'), ('notify', 'supabase-teams'))
DASHBOARD_TABLE = 'overview_projects'
COMPAT = 'comment-layer'
SKIP_CODES = ('skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-held', 'skip-no-path', 'skip-path-in-git',
              'skip-space-json-unreadable', 'skip-registry-unreadable', 'skip-tasks-unreadable', 'skip-nothing', 'skip-busy', 'skip-integrations-off')
ABORT_CODES = ('abort-provider', 'abort-internal', 'abort-lock', 'abort-tracks', 'abort-records', 'abort-originals', 'abort-verify')
_REASONS = {
    'skip-layer-off': 'шар просторів вимкнено: міграція не біжить',
    'skip-no-liga': 'у реєстрі нема простору ЛІГА',
    'skip-done': 'міграцію вже виконано (позначка в space.json)',
    'skip-held': 'міграцію вимкнено вручну (held у space.json)',
    'skip-integrations-off': 'інтеграції простору ЛІГА вимкнено — мігрувати нічого (ролі й так вимкнені)',
    'skip-no-path': 'теки простору ЛІГА не існує',
    'skip-path-in-git': 'тека простору лежить у робочому дереві git: space.json не має потрапити в чужий коміт',
    'skip-space-json-unreadable': 'space.json простору ЛІГА не читається',
    'skip-registry-unreadable': 'реєстр просторів не читається',
    'skip-tasks-unreadable': 'старий tasks.json не читається: конфіг ЛІГИ невідомий',
    'skip-nothing': 'нічого мігрувати (нема ні ролей, ні напрямків, ні записів задач): позначку не пишемо, наступний старт перевірить знову',
    'publisher-present': 'публікацію вже веде інший модуль простору: крок його не перебиває',
    'skip-busy': 'міграція вже виконується іншим процесом (замок migrations/.lock зайнятий)',
    'abort-provider': 'ядро не вирішує мігровану роль на розрахованому space.json: міграція нічого не пише',
    'abort-internal': 'непередбачена помилка розрахунку: міграція нічого не пише',
    'abort-tracks': 'розраховані напрямки не збігаються з адаптером за id чи дефолтом: міграція нічого не пише',
    'abort-records': 'tasks.json не записано: space.json не змінено, наступний запуск почне заново',
    'abort-originals': 'tasks.json ЛІГИ не записано: копії вже лежать у записах, нічого не видалено — наступний запуск почне заново',
    'abort-verify': 'скопійоване значення не збіглося з планом після запису: нічого не видалено з tasks.json',
    'abort-lock': 'міжпроцесний замок недоступний (flock не працює на цій файловій системі): міграція нічого не пише, щоб не йти без замка',
}


class _Stop(Exception):
    def __init__(self, status, **extra):
        super().__init__(status)
        self.status = status
        self.extra = extra


def _result(status, space_id=None, **kw):
    out = {'status': status, 'reason': _REASONS.get(status, ''), 'space_id': space_id, 'roles': {}, 'tracks': False,
           'tracks_reason': None, 'space_json': None, 'secrets': {}, 'space_path': None, 'records': [], 'notes': []}
    out.update(kw)
    return out


def _registry(home):
    """Реєстр просторів (читання без міграції й запису). `home` — тека `DEAI_HOME`; не задана — `spaces.home()`."""
    path = os.path.join(os.path.expanduser(home), 'spaces.json') if home else spaces.registry_path()
    try:
        return spaces._validate(spaces._read_json(path), path)
    except FileNotFoundError:
        return {'spaces': []}
    except (OSError, ValueError, spaces.SpacesError):
        raise _Stop('skip-registry-unreadable') from None


def _in_git(path):
    """`.git` (файл чи тека) у теці чи будь-якому її предку — лише файлові перевірки, git не запускається (ні за текстом шляху,
    ні за `realpath`: симлінк у робоче дерево теж дерево)."""
    for start in {os.path.abspath(path), os.path.realpath(path)}:
        d = start
        while True:
            if os.path.lexists(os.path.join(d, '.git')):
                return True
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return False


#: Адаптер ЛІГИ (4d-4a: ЛИШЕ тут, для міграції): останній рубіж кореня, перелік id, дефолт і підписи.
_FALLBACK_ROOT = '~/deai-work'
_LEGACY_IDS = ('united', 'liga360', 'seo')
_LEGACY_DEFAULT = 'united'
_LEGACY_LABELS = {'united': 'United', 'liga360': 'LIGA360', 'seo': 'SEO'}


def _legacy_of_task(task):
    """Старе читання напрямку задачі: `track`, інакше `profile` (лише міграція: `tracks.of_task` читає один `track`)."""
    if not isinstance(task, dict):
        return None
    for key in ('track', 'profile'):
        v = task.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _legacy_label(value):
    return tracks_core.read_tag(_LEGACY_LABELS.get(value, value))


# ── адаптер ЛІГИ: корінь старого `tasks.json` → напрямки ──────────────────────────────────────────────────────────────

def _legacy_roots_of(cfg):
    """`design_work_roots` ЛІГИ. ⛔ Не словник → `{}` (0.14.0 тут падав `AttributeError`; свідома відмінність спеки §6.4: спільний
    корінь замість обвалу)."""
    raw = cfg.get('design_work_roots') if isinstance(cfg, dict) else None
    return raw if isinstance(raw, dict) else {}


def _legacy_fallback(cfg):
    shared = cfg.get('design_work_root') if isinstance(cfg, dict) else None
    return os.path.expanduser(shared if isinstance(shared, str) and shared else _FALLBACK_ROOT)


def _legacy_root(cfg, value):
    """Корінь робочих тек ДЛЯ ЦЬОГО НАПРЯМКУ ЛІГИ (раніше `serve.work_root(cfg, profile)`), з розгорнутим `~`.

    Вимога користувача 31.08.2026: три напрямки — три теки і три репозиторії. Порядок: свій корінь напрямку →
    спільний `design_work_root` → історичний фолбек. ⛔ Напрямок без власного кореня НЕ вигадується (і не береться з
    дефолтного): краще чесно покласти в спільний корінь і сказати про це (`bin/roots.py`), ніж створити теку за вигаданим
    шляхом. `value` — що завгодно (`'United'`, `''`, число, `None`): невідоме — спільний корінь. Не кидає на поганому `cfg`.

    Свідома відмінність від 0.14.0: НЕ рядок у власному корені напрямку чи в `design_work_root` (число, список) раніше
    давав `TypeError` у `expanduser` (500); тепер таке значення вважається відсутнім і діє наступна ланка ланцюга
    (власний → спільний → `~/deai-work`)."""
    own = _legacy_roots_of(cfg).get(value) if isinstance(value, str) else None
    if isinstance(own, str) and own:
        return os.path.expanduser(own)
    return _legacy_fallback(cfg)


def _legacy_repos(cfg):
    """Таблиця «напрямок → репозиторій макетів» ЛІГИ з кореня `tasks.json` (раніше `serve.profile_repos` без читання файла).
    Ключ — за `ID_RE`, репо — `repo_ok` (обрізане); погані пари відкидаються, `cfg` не словник / ключа нема / не словник —
    `{}`. ⛔ Структура в усіх напрямків одна — `mockup/<task-id>`, тому напрямки розходяться лише репозиторієм, а не логікою
    (урок колишньої константи `PROFILE_REPOS`). Значень — ні в текстах, ні в журналах."""
    raw = cfg.get('profile_repos') if isinstance(cfg, dict) else None
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        r = tracks_core.repo_ok(v)
        if r and tracks_core._is_id(k):
            out[k] = r
    return out


def _legacy_tracks(cfg):
    """Неявні напрямки ЛІГИ → `(tracks, default_id, fallback_root)`.

    Перелік id: `united`, `liga360`, `seo`, далі ключі `design_work_roots` і `profile_repos` (лише за `ID_RE`, у такому
    порядку, без дублів). `root` — `_legacy_root` (свій → спільний → `~/deai-work`, розгорнутий); `repo` — з `_legacy_repos`
    або `''`; `label` — `_LEGACY_LABELS` або `id`; `ds` = `id` (вендорний інспектор сам каже «ДС нема» для невідомого);
    дефолт — `united`. `fallback_root` — корінь для будь-якого значення поза переліком (`'United'`, невідомий, `None`):
    не корінь дефолтного напрямку (спека §6.1). Перелік не обмежений `MAX_TRACKS`: адаптер дзеркалить довільний конфіг, а
    репо 21-го ключа 0.14.0 теж віддавав. Не кидає на поганому `cfg`."""
    ids = list(_LEGACY_IDS)
    seen = set(ids)
    raw_repos = cfg.get('profile_repos') if isinstance(cfg, dict) else None
    for src in (_legacy_roots_of(cfg), raw_repos if isinstance(raw_repos, dict) else {}):
        for k in src:
            if tracks_core._is_id(k) and k not in seen:
                seen.add(k)
                ids.append(k)
    repos = _legacy_repos(cfg)
    tracks = [{'id': i, 'label': _LEGACY_LABELS.get(i, i), 'root': _legacy_root(cfg, i),
               'repo': repos.get(i, ''), 'ds': i} for i in ids]
    return tracks, _LEGACY_DEFAULT, _legacy_fallback(cfg)


def _foreign_dropped(root, others):
    """Так само, як `serve._drop_foreign_roots`: корінь, що перетинається з ІНШИМ простором реєстру, у явних напрямках стає
    `None` (в адаптері ЛІГИ він лишився б). `others` — реєстр без запису ЛІГИ."""
    try:
        _ok, why = spaces.check_new_path(root, others, [])
    except (OSError, ValueError):
        return True
    return why is not None


def _adapter_tracks(cfg, path, others):
    """Явні напрямки з адаптера БЕЗ воріт паритету → `(список для space.json, нормалізований, дефолт, нотатки-про-корені)`.
    `нотатки-про-корені` — `root-dropped:<id>` (корінь відкинув `normalize` чи перетин з іншим простором) і `root-rebased:<id>`
    (відносний корінь став відносним до теки простору)."""
    items, default, _fallback = _legacy_tracks(cfg)
    raw = [{'id': t['id'], 'label': t['label'], 'root': t['root'], 'repo': t['repo'], 'ds': t['ds']} for t in items]
    norm = tracks_core.normalize(raw, path)
    norm = [{**t, 'root': None} if t['root'] is not None and _foreign_dropped(t['root'], others) else t for t in norm]
    notes = []
    for a in items:
        n = tracks_core.find(norm, a['id'])
        if n is not None and n['root'] != os.path.normpath(a['root']):
            notes.append(('root-dropped:' if n['root'] is None else 'root-rebased:') + a['id'])
    return raw, norm, default, notes


def _compute_tracks(cfg, path, others):
    """4d-3a: явні напрямки + ВОРОТА паритету → `(список для space.json, нормалізований, дефолт)` чи `None` (паритету нема)."""
    raw, norm, default, _notes_roots = _adapter_tracks(cfg, path, others)
    items = _legacy_tracks(cfg)[0]
    if tracks_core.default_id(norm, default) != default:
        return None
    for a in items:
        n = tracks_core.find(norm, a['id'])
        if (n is None or n['root'] != os.path.normpath(a['root']) or n['repo'] != a['repo'] or n['ds'] != a['ds']
                or n['label'] != _legacy_label(a['id'])):
            return None
    return raw, norm, default


def _unknown_values(cfg, ids, norm):
    """Поправка контролера після Task 1: чи веде явний `tracks` невідоме значення напрямку інакше, ніж адаптер.
    (а) у старому `tasks.json` є задача, чий `track`/`profile` (`tracks.of_task`) не рядок із переліку мігрованих id
    (включно з `None`, `''`, іншим регістром); (б) корінь дефолтного напрямку ≠ спільному кореню адаптера
    (`legacy_root(cfg, None)`): тоді нова задача з невідомим значенням лягла б в інше місце; (в) ключ `design_work_roots` чи
    `profile_repos` поза `ID_RE` (напр. `Foo` зі своїм коренем чи репо): він не стає напрямком, тож задачі з ним втратили б свій корінь."""
    for key in ('design_work_roots', 'profile_repos'):
        raw = cfg.get(key) if isinstance(cfg, dict) else None
        if isinstance(raw, dict) and any(not tracks_core._is_id(k) for k in raw):
            return True
    tasks = cfg.get('tasks') if isinstance(cfg, dict) else None
    for t in (tasks.values() if isinstance(tasks, dict) else ()):
        if isinstance(t, dict) and _legacy_of_task(t) not in ids:
            return True
    default = tracks_core.find(norm, 'united')
    return default is None or default['root'] != os.path.normpath(_legacy_root(cfg, None))


def _nonempty_str(v):
    return isinstance(v, str) and bool(v)


def _notes(cfg, ids, norm, root_notes):
    """Нотатки четвертого кроку (коди без шляхів і значень; id напрямків — можна), у порядку: корені, `unknown-values`,
    `default-root-differs`, `non-id-keys`. `unknown-values` — задача зі значенням напрямку (`_legacy_of_task`), якого нема в
    переліку (задачі БЕЗ значення нотатки не дають: мітка й ДС у них і так порожні)."""
    notes = list(root_notes)
    tasks = cfg.get('tasks') if isinstance(cfg, dict) else None
    if any(isinstance(t, dict) and _legacy_of_task(t) is not None and _legacy_of_task(t) not in ids
           for t in (tasks.values() if isinstance(tasks, dict) else ())):
        notes.append('unknown-values')
    default = tracks_core.find(norm, 'united')
    if default is None or default['root'] != os.path.normpath(_legacy_root(cfg, None)):
        notes.append('default-root-differs')
    for key in ('design_work_roots', 'profile_repos'):
        raw = cfg.get(key) if isinstance(cfg, dict) else None
        if isinstance(raw, dict) and any(not tracks_core._is_id(k) for k in raw):
            notes.append('non-id-keys')
            break
    return notes


def _records_to_fix(cfg):
    """Ідентифікатори задач ЛІГИ, у яких `track` — не непорожній рядок, а `profile` — непорожній: їм крок пише `track = profile`
    (старий запис до 0.15.0 мав лише `profile`; після 4d-4a `tracks.of_task` читає один `track`)."""
    tasks = cfg.get('tasks') if isinstance(cfg, dict) else None
    return sorted(tid for tid, t in (tasks.items() if isinstance(tasks, dict) else ())
                  if isinstance(t, dict) and not _nonempty_str(t.get('track')) and _nonempty_str(t.get('profile')))


def _has_userinfo(url):
    """Адреса з `userinfo` (`user:pass@хост`): такий рядок не мігрує — облікові лежали б у `space.json` відкритим текстом."""
    try:
        return '@' in urlsplit(url).netloc
    except ValueError:
        return True


#: ⛔ Читачі ОРИГІНАЛІВ кореня `tasks.json`/оточення/`pipeline-feedback` — ЄДИНІ копії на весь код (4d-4b: з `install_config` вони видалені).
#: Міграція ще читає оригінали на першому старті старої установки (кроки A–C), далі їх тримає лише вона. Тіла — байт у байт ті, що були
#: в `install_config.supabase_from`/`jira_from`; ізоляція — `isolation.isolated()`.
def _supabase_from(cfg):
    """`(url, key)` за вже прочитаним коренем старого `tasks.json` (`cfg`; не словник — як порожній). Джерела по черзі: корінь файла
    (`supabase_url`, `supabase_key`), далі змінні оточення `SUPABASE_URL`/`SUPABASE_KEY`; пара береться ЦІЛОЮ з одного джерела.
    Адреса — ПОВНІСТЮ `https://<хост>[:порт][/]` (без `/` в кінці в результаті), ключ — друковний ASCII без пробілів.
    ⛔ В ізольованому прогоні (`isolation.isolated()`) оточення не читаємо: джерело ОДНЕ — корінь файла."""
    cfg = cfg if isinstance(cfg, dict) else {}
    sources = [(cfg.get('supabase_url'), cfg.get('supabase_key'))]
    if not isolation.isolated():                       # ⛔ в ізольованому прогоні оточення не читаємо (див. докстрінг)
        sources.append((os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY')))
    for url, key in sources:
        if not (isinstance(url, str) and isinstance(key, str)):
            continue
        url, key = url.strip(), key.strip()
        # адреса — повністю `https://<хост>[:порт][/]`; ключ — друковний ASCII без пробілів (див. докстрінг)
        if install_config._SUPABASE_URL_RE.fullmatch(url) and install_config._SUPABASE_KEY_RE.fullmatch(key):
            return url.rstrip('/'), key
    return None, None


def _jira_from(cfg):
    """`(base, email, token)` за вже прочитаним коренем старого `tasks.json` (`cfg`). Адреса — `jira_base` кореня (форма — як
    в `_supabase_from`, без `/` в кінці). Облікові — пара `JIRA_EMAIL`/`JIRA_TOKEN` з оточення, а коли її нема — файли
    `<HOME>/.claude/pipeline-feedback/jira-email|jira-token`; пошта й токен читаються НЕЗАЛЕЖНО (оточення раніше за файл; порожнє чи
    негодне — далі). ⛔ В ізольованому прогоні (`isolation.isolated()`) — ЛИШЕ корінь: `jira_email`, `jira_token`; `JIRA_*` і
    `pipeline-feedback` НЕ читаються. Значень — ні в текстах, ні в журналах."""
    base = cfg.get('jira_base') if isinstance(cfg, dict) else None
    if not isinstance(base, str):
        return None, None, None
    base = base.strip()
    if not install_config._SUPABASE_URL_RE.fullmatch(base):           # та сама форма адреси, що в `_supabase_from`
        return None, None, None

    def from_file(name):
        try:
            with open(os.path.expanduser('~/.claude/pipeline-feedback/' + name), encoding='utf-8') as f:
                return f.read()
        except (OSError, ValueError):
            return None

    def pick(env, name, key, valid):
        if isolation.isolated():                        # ⛔ лише корінь файла задач (ключ `jira_email`/`jira_token`)
            raw = cfg.get(key)
            return raw.strip() if isinstance(raw, str) and valid(raw.strip()) else None
        for raw in (os.environ.get(env), from_file(name)):          # оточення раніше за файл; порожнє/негодне — далі
            if isinstance(raw, str) and valid(raw.strip()):
                return raw.strip()
        return None
    email = pick('JIRA_EMAIL', 'jira-email', 'jira_email', lambda v: bool(v) and v.isprintable())
    token = pick('JIRA_TOKEN', 'jira-token', 'jira_token', lambda v: install_config._SUPABASE_KEY_RE.fullmatch(v) is not None)
    return (base.rstrip('/'), email, token) if (email and token) else (None, None, None)


def _role_entries(cfg, present):
    """`{role: (module, ознака_пропуску | None, запис space.json | None, секрети | None)}` за вже прочитаним `cfg`; облікові — приватні
    читачі оригіналів цього модуля (`_supabase_from`/`_jira_from`): джерела й порядок ті самі, що були в рантаймі до 4d-4b."""
    sb_url, sb_key = _supabase_from(cfg)
    base, email, token = _jira_from(cfg)
    spec = {
        'tracker': ((base and email and token), 'no-jira', {'base': base, 'email': email}, {'token': token}),
        'dashboard': ((sb_url and sb_key), 'no-supabase', {'url': sb_url, 'table': DASHBOARD_TABLE, 'compat': COMPAT}, {'key': sb_key}),
        'notify': ((sb_url and sb_key), 'no-supabase', {'url': sb_url, 'compat': COMPAT}, {'key': sb_key}),
    }
    urls = {'tracker': base, 'dashboard': sb_url, 'notify': sb_url}
    out = {}
    for role, mid in ROLE_MODULES:
        have, why, settings, secret = spec[role]
        if mid in present:
            out[role] = (mid, 'module-present', None, None)
        elif not have:
            out[role] = (mid, why, None, None)
        elif _has_userinfo(urls[role]):                      # `user:pass@хост` в адресі: облікові в адресу не мігрують
            out[role] = (mid, 'bad-url', None, None)
        else:
            out[role] = (mid, None, {'enabled': True, 'shared_state': True, 'settings': settings}, secret)
    return out


#: 4d-3b: ролі другого кроку → вбудований модуль, у порядку запису (напрямки крок не мігрує).
ROLE_MODULES_B = (('comments', 'supabase-comments'), ('vcs', 'git-sync'))
#: Ключ `compat` запису `git-sync`: тексти «design-canvas»/«GitLab» (див. `serve.vcs_legacy_texts`). Для коментарів — `COMPAT`.
VCS_COMPAT = 'design-canvas'


def _entries_b(cfg, present):
    """Роль → `(module, ознака_пропуску | None, запис space.json | None, секрети | None)` кроку 4d-3b (форма `_role_entries`).
    `comments` → `supabase-comments`: адреса й ключ — `_supabase_from` (читач оригіналів міграції);
    кошик — `install_config.LEGACY_SHOTS_BUCKET`. `vcs` → `git-sync`: налаштування ті самі, що були в неявного шляху 0.7.0 (гілка `main`, `mockup/{task}`, автосинк).
    ⛔ `ssh_key`/`host_ip`/`repo` НЕ копіюємо тут: ключ і IP до 4d-4b давав корінь, їх переносить крок Е; репо — ціль задачі; секретів у `git-sync` нема."""
    sb_url, sb_key = _supabase_from(cfg)
    out = {}
    for role, mid in ROLE_MODULES_B:
        if mid in present:
            out[role] = (mid, 'module-present', None, None)
        elif role == 'comments':
            if not (sb_url and sb_key):
                out[role] = (mid, 'no-supabase', None, None)
            elif _has_userinfo(sb_url):                      # `user:pass@хост` в адресі: облікові в адресу не мігрують
                out[role] = (mid, 'bad-url', None, None)
            else:
                out[role] = (mid, None, {'enabled': True, 'shared_state': True,
                                         'settings': {'url': sb_url, 'shots_bucket': install_config.LEGACY_SHOTS_BUCKET, 'compat': COMPAT}},
                             {'key': sb_key})
        else:
            out[role] = (mid, None, {'enabled': True, 'shared_state': True,
                                     'settings': {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True, 'compat': VCS_COMPAT}}, None)
    return out


#: 4d-3c: роль третього кроку → вбудований модуль (напрямки крок не мігрує, секретів нема).
ROLE_MODULES_C = (('publish', 'vercel-publish'),)
#: Ключ `compat` запису `vercel-publish`: шлях ЛІГИ (`deai_modules.publish_legacy_path`); тест зіставляє з `COMPAT_DESIGN_CANVAS`.
PUBLISH_COMPAT = 'design-canvas'


def _entries_c(cfg, present):
    """Роль → `(module, ознака_пропуску | None, запис space.json | None, секрети | None)` кроку 4d-3c (форма `_entries_b`).
    `publish` → `vercel-publish` з `compat: design-canvas`: публікація, пароль превʼю, `pv-…` і URL — ті самі, що в неявному шляху.
    ⛔ Секретів нема (`token`/`password` не пишемо: `auth: cli`, пароль превʼю дає задача/корінь, а не `secrets.json`); `cfg` не потрібен.
    `publisher-present` тут НЕ проставляється: функція не знає простору — це робить `_plan` одним блоком (Поправка 4 плану)."""
    if 'vercel-publish' in present:
        return {'publish': ('vercel-publish', 'module-present', None, None)}
    return {'publish': ('vercel-publish', None, {'enabled': True, 'shared_state': True,
                                                 'settings': {'auth': 'cli', 'team': '', 'compat': PUBLISH_COMPAT}}, None)}


def _publisher_present(space, mods):
    """Чи роль `publish` на ПОТОЧНОМУ `space.json` (`mods` — сирі модулі) уже веде модуль (`Module`) — не `vercel-publish`
    (той — `module-present`), а ІНШИЙ явно ввімкнений (напр. `static-publish`): два явні модулі публікації розв'язуються за id
    (`static-publish` < `vercel-publish`), тож без цього коду крок дав би вічний `abort-provider`. Лише `ModuleError` (зламаний СВІЙ
    модуль) — «не присутній»: далі той самий виклик на розрахованому `space.json` теж кине → `abort-provider`. ⛔ Інший виняток
    (напр. `OSError` при скануванні каталогу) НЕ ковтаємо: «не присутній» перезаписав би робочий СВІЙ видавець, чий id сортується
    після `vercel-publish`; виняток іде до `plan()` → `abort-internal`, нічого не пишемо."""
    try:
        prov = deai_modules._provider_for('publish', space, explicit_override=deai_modules._normalize(mods))
        return isinstance(prov, deai_modules.Module)
    except deai_modules.ModuleError:
        return False


#: 4d-4b: вісім «оригіналів» кореня `tasks.json` ЛІГИ і де лежить їхня копія. `kind`: `s` — налаштування запису, `k` — секрет запису.
#: `copy` — крок Е сам кладе значення в запис, коли там порожньо (4d-3 це свідомо не копіював). Рядки — ТІ САМІ, що були в читачів рантайму
#: (рантайм їх більше не читає: `install_config.{supabase,jira}_*`, `serve.preview_password`, `_vcs_ssh` видалено чи переписано); міграція — єдине місце, що знає ці рядки назавжди.
SB_MODULES = ('supabase-dashboard', 'supabase-teams', 'supabase-comments')
ORIGINALS = (
    ('supabase_url', SB_MODULES, 's', 'url', False),
    ('supabase_key', SB_MODULES, 'k', 'key', False),
    ('jira_base', ('jira-tracker',), 's', 'base', False),
    ('jira_email', ('jira-tracker',), 's', 'email', False),
    ('jira_token', ('jira-tracker',), 'k', 'token', False),
    ('gitlab_ssh_key', ('git-sync',), 's', 'ssh_key', True),
    ('gitlab_host_ip', ('git-sync',), 's', 'host_ip', True),
    ('preview_password', ('vercel-publish',), 'k', 'password', True),
)
ORIGINAL_KEYS = tuple(o[0] for o in ORIGINALS)
#: Ключі, наявність яких у корені робить файл «файлом ЛІГИ» для `_has_markers` (реєстр без запису ЛІГИ відновлюється з нуля).
_MARKER_KEYS = ('gitlab_host_ip', 'gitlab_ssh_key')
#: Усі маркери кореня: `registry` + ключі вище (задачі з `gitlab` — окремо, у `_has_markers`).
_LEGACY_MARKERS = ('registry',) + _MARKER_KEYS


def _has_markers(cfg):
    """Корінь старого `tasks.json` має ознаки «файла ЛІГИ» (переїхало з `spaces`: прапорець `integrations` там більше не пишеться)."""
    if any(k in cfg for k in _LEGACY_MARKERS):
        return True
    tasks = cfg.get('tasks') if isinstance(cfg.get('tasks'), dict) else {}
    return any(isinstance(t, dict) and t.get('gitlab') for t in tasks.values())


def _fits(v):
    """Значення можна покласти в запис (`write_secrets`/налаштування `text`): рядок ≤ `MAX_VALUE_LEN`, кодується в UTF-8."""
    return isinstance(v, str) and len(v) <= deai_modules.MAX_VALUE_LEN and deai_modules._encodable(v)


def _effective(key, raw):
    """Значення, яке віддав би ВИДАЛЕНИЙ читач (після його `strip`/`rstrip('/')`/форми), або `None` — «непридатне» (`unfit`)."""
    if key in ('supabase_url', 'jira_base'):
        s = raw.strip() if isinstance(raw, str) else ''
        ok = install_config._SUPABASE_URL_RE.fullmatch(s) and not _has_userinfo(s)
        return s.rstrip('/') if ok else None
    if key in ('supabase_key', 'jira_token'):
        s = raw.strip() if isinstance(raw, str) else ''
        return s if install_config._SUPABASE_KEY_RE.fullmatch(s) else None
    if key == 'jira_email':
        s = raw.strip() if isinstance(raw, str) else ''
        return s if s and s.isprintable() else None
    if key == 'preview_password':
        if isinstance(raw, bool) or (isinstance(raw, (int, float)) and not raw):
            return None                                      # `True` — не пароль; `0`/`0.0`/`False` старий читач вважав ВІДСУТНІМ (→ 1100): непридатне
        v = str(raw) if isinstance(raw, (int, float)) else raw
        return v if isinstance(v, str) and v.strip() and _fits(v) else None
    return raw if isinstance(raw, str) and raw.strip() and _fits(raw) else None        # gitlab_ssh_key / gitlab_host_ip: як є


def _holder_ready(norm, mid, key):
    """Запис `mid` готовий тримати оригінал: є, `enabled`, `shared_state`; для `preview_password` — ще й `compat == design-canvas`
    (інакше секрет `password` має інший зміст: модуль-режим, а не пароль превʼю ЛІГИ)."""
    e = norm.get(mid)
    if not (isinstance(e, dict) and e.get('enabled') is True and e.get('shared_state') is True):
        return None
    if key == 'preview_password' and (e.get('settings') or {}).get('compat') != PUBLISH_COMPAT:
        return None
    return e


def _held(norm, secrets, sid, mid, kind, field):
    e = norm.get(mid) or {}
    if kind == 'k':
        return deai_modules._bucket(secrets, sid, mid).get(field)
    v = (e.get('settings') or {}).get(field)
    return v if isinstance(v, str) and v else None


def _decide_originals(cfg, norm, secrets, sid, had_markers=None):
    """ЧИСТИЙ розрахунок кроку Е (нічого не читає з диска): `{'copy_settings': {mid: {поле: значення}}, 'copy_secrets': {mid: {поле:
    значення}}, 'remove': [ключі], 'kept': [ключі], 'notes': [коди]}`. Правила (спека §1.1): нема в корені — мовчки; непридатне —
    `unfit:<ключ>`; тримача нема — `no-record:<модуль>`; значення відмінне — `differs:<ключ>` (КРІМ `preview_password`: секрет, відмінний від
    кореня, ПЕРЕЗАПИСУЄТЬСЯ коренем — рішення власника 09.11.2026, `replaced:preview_password`, старе значення — у бекапі кроку); порожнє й копіюємо — у план копії; збіг — у список видалення. Пара Supabase — лише разом: не всі три
    тримачі — `partial:supabase`, жоден із двох не видаляється. ⛔ Значень у виході НЕМАЄ нікуди, крім `copy_*` (їх пише запис)."""
    out = {'copy_settings': {}, 'copy_secrets': {}, 'copied': [], 'remove': [], 'kept': [], 'notes': []}
    notes = out['notes']

    def note(code):
        if code not in notes:
            notes.append(code)

    sb_blocked = False
    present = [o for o in ORIGINALS if cfg.get(o[0]) is not None]
    if any(o[0] in ('supabase_url', 'supabase_key') for o in present):
        missing = [m for m in SB_MODULES if not _holder_ready(norm, m, 'supabase_url')]
        if missing:
            sb_blocked = True
            note('partial:supabase')
            for m in missing:
                note('no-record:' + m)
    for key, mods_, kind, field, copyable in present:
        eff = _effective(key, cfg[key])
        if eff is None:
            note('unfit:' + key)
            out['kept'].append(key)
            continue
        if key in ('supabase_url', 'supabase_key') and sb_blocked:      # мертва оборона: той самий предикат, що й перевірка тримачів нижче
            out['kept'].append(key)
            continue
        holders = [m for m in mods_ if _holder_ready(norm, m, key)]
        if len(holders) != len(mods_):
            for m in mods_:
                if m not in holders:
                    note('no-record:' + m)
            out['kept'].append(key)
            continue
        equal = True
        for m in mods_:
            cur = _held(norm, secrets, sid, m, kind, field)
            if cur == eff:
                continue
            if cur in (None, '') and copyable:                  # порожньо — копіюємо
                out['copy_secrets' if kind == 'k' else 'copy_settings'].setdefault(m, {})[field] = eff
                out['copied'].append(key)
            elif key == 'preview_password':                     # рішення власника 09.11.2026: КОРІНЬ перемагає (люди бачать той самий пароль);
                out['copy_secrets'].setdefault(m, {})[field] = eff   # старий секрет — у датованому бекапі, у підсумку лише `replaced:<ключ>`
                out['copied'].append(key)
                note('replaced:' + key)
            else:           # решта відмінних значень запису (`ssh_key`, `jira_token`, …) НІКОЛИ не перезаписуємо: `differs:<ключ>`
                note('differs:' + key)
                equal = False
        if equal:
            out['remove'].append(key)
        else:
            out['kept'].append(key)
    # Охоронець маркера: без `registry`/задач з `gitlab` реєстр, відновлений з нуля, створив би запис ЛІГИ без ознак інтеграцій.
    if had_markers is None:
        had_markers = _has_markers(cfg)
    if had_markers:
        left = {k: v for k, v in cfg.items() if k not in out['remove']}
        if not _has_markers(left):
            for k in _MARKER_KEYS:
                if k in out['remove']:
                    out['remove'].remove(k)
                    out['kept'].append(k)
                    note('marker-kept:' + k)
                    break
    return out


def _originals_state(path, data, cfg):
    """`(norm, secrets)` для `_decide_originals`: явні записи `space.json` ЛІГИ (`data`) і весь `secrets.json`."""
    mods = deai_modules._raw_modules(data)
    return deai_modules._normalize(mods), deai_modules._load_secrets()


def _plan_originals(reg, liga, sid, path, data, mods, mig, cfg, step):
    """`plan()` кроку Е (див. `_decide_originals`): ворота вже пройдено в `_plan`."""
    norm, secrets = _originals_state(path, data, cfg)
    d = _decide_originals(cfg, norm, secrets, sid)
    if not (d['copy_settings'] or d['copy_secrets'] or d['remove'] or d['notes']):
        raise _Stop('skip-nothing', space_id=sid)
    new_mods = {k: (dict(v) if isinstance(v, dict) else v) for k, v in mods.items()}
    for mid, patch in d['copy_settings'].items():
        rec = dict(new_mods[mid])
        st = dict(rec.get('settings') or {})
        st.update(patch)
        rec['settings'] = st
        new_mods[mid] = rec
    # Перевірка В ПАМʼЯТІ: запис із новими налаштуваннями лишається тим самим постачальником (ролі кроку Е нема — міняти нічого не вільно).
    space = {'id': sid, 'path': path, 'legacy': True}
    for role in deai_modules.ROLES_CALLED:
        got = []
        for m in (mods, new_mods):
            try:
                prov = deai_modules._provider_for(role, space, explicit_override=deai_modules._normalize(m))
            except deai_modules.ModuleError:
                prov = None
            got.append((getattr(prov, 'id', None), isinstance(prov, deai_modules.Module)))
        if got[0] != got[1]:
            raise _Stop('abort-provider', space_id=sid)
    space_json = dict(data)
    space_json['modules'] = new_mods
    marks = dict(mig) if isinstance(mig, dict) else {}
    marks[step.mark] = {'roles': [], 'copied': sorted(d['copied']), 'removed': sorted(d['remove']), 'kept': sorted(d['kept']),
                        'notes': list(d['notes'])}
    space_json['migrations'] = marks
    return _result('ready', space_id=sid, space_path=path, space_json=space_json, notes=list(d['notes']), originals=d)


def plan(home=None, step=None):
    """Чистий розрахунок міграції ЛІГИ; див. докстрінг модуля. Нічого не пише; не кидає (збій — `abort-internal`).
    `step` — крок (`Step`, його позначка чи `None` = 4d-3a): 4d-3b узагальнює модуль до впорядкованого списку кроків."""
    try:
        return _plan(home, _step(step))
    except _Stop as s:
        return _result(s.status, **s.extra)
    except Exception:  # noqa: BLE001 — розрахунок не валить старт: код замість винятку (без тексту винятку: там можуть бути значення)
        return _result('abort-internal')


def _plan(home, step):
    if not spaces.layer_on():
        raise _Stop('skip-layer-off')
    reg = _registry(home)
    liga = next((s for s in reg['spaces'] if s.get('legacy') is True), None)
    if liga is None:
        raise _Stop('skip-no-liga')
    sid, path = liga['id'], liga['path']
    # ⛔ Без інтеграцій (`integrations` не `True`) ролі ЛІГИ в 0.17 вимкнені (немає неявних постачальників): явні записи їх увімкнули б —
    # злам паритету. Для КОЖНОГО кроку: нічого не пишемо (ні позначки, ні `migrations/`).
    if not _liga_integrations(liga):
        raise _Stop('skip-integrations-off', space_id=sid)
    if not os.path.isdir(path):
        raise _Stop('skip-no-path', space_id=sid)
    try:
        data = deai_modules._load_space_json(os.path.join(path, 'space.json'))
        mods = dict(deai_modules._raw_modules(data))
    except deai_modules.ModuleError:
        raise _Stop('skip-space-json-unreadable', space_id=sid) from None
    mig = data.get('migrations')
    mark = mig.get(step.mark) if isinstance(mig, dict) else None
    if mark is not None:
        raise _Stop('skip-held' if isinstance(mark, dict) and mark.get('held') is True else 'skip-done', space_id=sid)
    # ⛔ УТРИМАНИЙ (`held: true`) ранній крок тримає всі наступні: інакше `restore <b>` + `restore <a> --hold` лишив би b живим на
    # наступному старті. Лише `held`: done/skip-nothing/інші пропуски раннього кроку наступний не блокують.
    for earlier in ALL_STEPS[:ALL_STEPS.index(step)]:
        em = mig.get(earlier.mark) if isinstance(mig, dict) else None
        if isinstance(em, dict) and em.get('held') is True:
            # свій текст: власне «вимкнено вручну» цей крок не казав — його тримає ранній (мінор ревʼю Task 5)
            raise _Stop('skip-held', space_id=sid, reason='утримано разом із %s (ранній крок вимкнено вручну: held у space.json)' % earlier.mark)
    if _in_git(path):
        raise _Stop('skip-path-in-git', space_id=sid)
    try:
        cfg = install_config.load_legacy_tasks()
    except (OSError, ValueError, RecursionError):
        raise _Stop('skip-tasks-unreadable', space_id=sid) from None
    if not isinstance(cfg, dict):
        raise _Stop('skip-tasks-unreadable', space_id=sid)
    if step.originals:                                       # 4d-4b: оригінали кореня (копія й видалення), ролей нема
        return _plan_originals(reg, liga, sid, path, data, mods, mig, cfg, step)

    roles = (step.entries or _role_entries)(cfg, set(mods))      # ролі кроку (4d-3a — `_role_entries`; пошук за імʼям на виклик: точка підміни)
    # 4d-3c (Поправка 4 плану): `_entries_c` не знає простору, тож «публікацію вже веде інший модуль» проставляємо тут, одним блоком,
    # ДО підрахунку `new_mods`/`skip-nothing`/`abort-provider`. `space` — ТАК САМО, як у перевірці `abort-provider` нижче.
    if step is STEP_C and roles['publish'][1] is None:
        if _publisher_present({'id': sid, 'path': path, 'legacy': True}, mods):
            roles['publish'] = (roles['publish'][0], 'publisher-present', None, None)
    new_mods, secrets = dict(mods), {}
    for role, (mid, skip, entry, secret) in roles.items():
        if skip is None:
            new_mods[mid] = entry
            if secret:                                      # `git-sync` (4d-3b) секретів не має: порожнього запису в secrets.json нема
                secrets[mid] = secret
    out_roles = {r: {'module': m, 'migrate': skip is None, 'reason': skip} for r, (m, skip, _e, _s) in roles.items()}

    do_tracks, tracks_reason, new_tracks, notes = False, None, None, []
    records = _records_to_fix(cfg) if step.ungated else []
    if not step.tracks:                                     # напрямки мігрують лише 4d-3a і 4d-4a
        pass
    elif step.ungated:                                      # 4d-4a: рівно тоді, коли ЗАРАЗ діє адаптер (та сама функція, що в рантаймі)
        if not tracks_core.adapter_applies(data.get('tracks'), path):
            tracks_reason = 'tracks-present'
        else:
            others = {'spaces': [s for s in reg['spaces'] if s.get('id') != sid]}
            raw, norm, default, root_notes = _adapter_tracks(cfg, path, others)
            chk = tracks_core.normalize(raw, path, roots=False)          # перевірка В ПАМʼЯТІ: ті самі id і дефолт, що адаптер
            if [x['id'] for x in chk] != [x['id'] for x in raw] or tracks_core.default_id(chk, default) != default:
                raise _Stop('abort-tracks', space_id=sid)
            do_tracks, new_tracks = True, (raw, default)
            notes = _notes(cfg, {x['id'] for x in raw}, norm, root_notes)
    elif data.get('tracks') is not None:                    # навіть `[]`: власник свідомо обрав «жодного напрямку»
        tracks_reason = 'tracks-present'
    else:
        others = {'spaces': [s for s in reg['spaces'] if s.get('id') != sid]}
        computed = _compute_tracks(cfg, path, others)
        if computed is None:
            tracks_reason = 'tracks-parity'                     # напрямки не мігрують, ролі — так
        else:
            raw, norm, default = computed
            if _unknown_values(cfg, {t['id'] for t in raw}, norm):
                tracks_reason = 'tracks-unknown-values'
            else:
                do_tracks, new_tracks = True, (raw, default)

    if not do_tracks and not records and not any(skip is None for (_m, skip, _e, _s) in roles.values()):
        raise _Stop('skip-nothing', space_id=sid, roles=out_roles, tracks_reason=tracks_reason)

    # Перевірка В ПАМʼЯТІ: ядро вирішує кожну мігровану роль саме цим модулем на розрахованому `space.json` (нічого не пишемо).
    explicit = deai_modules._normalize(new_mods)
    space = {'id': sid, 'path': path, 'legacy': True}
    for role, (mid, skip, _e, _s) in roles.items():
        if skip is not None:
            continue
        try:
            prov = deai_modules._provider_for(role, space, explicit_override=explicit)
        except Exception:  # noqa: BLE001
            prov = None
        if getattr(prov, 'id', None) != mid or not isinstance(prov, deai_modules.Module):
            raise _Stop('abort-provider', space_id=sid, roles=out_roles)

    space_json = dict(data)
    space_json['modules'] = new_mods
    if do_tracks:
        space_json['tracks'], space_json['default_track'] = new_tracks
    marks = dict(mig) if isinstance(mig, dict) else {}
    marks[step.mark] = {'roles': [r for r, (_m, skip, _e, _s) in roles.items() if skip is None]}
    if step.tracks:                                         # позначка 4d-3b/3c — без `tracks`
        marks[step.mark]['tracks'] = do_tracks
    if step.ungated:
        marks[step.mark]['records'], marks[step.mark]['notes'] = len(records), notes
    space_json['migrations'] = marks
    return _result('ready', space_id=sid, space_path=path, roles=out_roles, tracks=do_tracks, tracks_reason=tracks_reason,
                   space_json=space_json, secrets=secrets, records=records, notes=notes)


def report(p, step=None):
    """Текст для людини й журналу: статус, код, ролі, напрямки, ІМЕНА секретних ключів. ⛔ Жодних значень секретів чи адрес.
    `step` — крок, чия позначка відкриває звіт (`None` = 4d-3a)."""
    lines = [_step(step).mark + ': ' + str(p.get('status')), '  ' + str(p.get('reason') or '')]
    if p.get('space_id'):
        lines.append('  space: ' + str(p['space_id']))
    for role, r in (p.get('roles') or {}).items():
        lines.append('  %s (%s): %s' % (role, r['module'], 'migrate' if r['migrate'] else 'skip: ' + str(r['reason'])))
    if p.get('status') == 'ready':
        if _step(step).tracks:
            lines.append('  tracks: ' + ('migrate' if p.get('tracks') else 'skip: ' + str(p.get('tracks_reason'))))
        if _step(step).ungated:
            lines.append('  records: %d; notes: %s' % (len(p.get('records') or []), ', '.join(p.get('notes') or []) or '-'))
        if _step(step).originals:                            # 4d-4b: імена ключів кореня, без значень
            o = p.get('originals') or {}
            lines.append('  copy: %s; remove: %s; kept: %s; notes: %s' % tuple(
                ', '.join(o.get(k) or []) or '-' for k in ('copied', 'remove', 'kept', 'notes')))
        for mid, sec in (p.get('secrets') or {}).items():
            lines.append('  secrets %s: %s' % (mid, ', '.join(sorted(sec)) or '-'))
    return '\n'.join(lines)


# ================================================================================================ запис, відкат, старт (Task 5)
#
# ⛔ Замки: `spaces.WRITE_LOCK` — звичайний `Lock`, не вкладений. Його тримаємо ЛИШЕ на один запис (`write_secrets` бере його сам,
# `_commit_space`/`_restore_file`/`_write_last` — окремо). Під ним НІКОЛИ не кличемо `plan()`, `load_registry`, `catalog`, `provider`.

BACKUP_SUFFIX = '-liga-4d3a'
#: Строгий вигляд імені бекапу (`<YYYYMMDD-HHMMSS>-liga-4d3a[-N]`): жодних шляхів, крапок і розділювачів.
STAMP_RE = re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3a(?:-[0-9]{1,3})?')

#: Крок міграції (4d-3b: впорядкований список): `mark` — ключ у `space.json['migrations']` І значення `migration` у маніфесті бекапу;
#: `roles` — `((роль, модуль), …)` у порядку запису; `tracks` — чи мігрує напрямки (лише 4d-3a); `suffix` — хвіст імені бекапу;
#: `stamp_re` — строге імʼя бекапу (імʼя однозначно каже, чий це крок); `entries(cfg, present)` — розрахунок ролей кроку
#: (`None` = `_role_entries`, 4d-3a; `_entries_b` додає Task 6). `hold` кроку — це `{held: True}` у ЙОГО позначці.
Step = namedtuple('Step', 'mark roles tracks suffix stamp_re entries ungated originals', defaults=(None, False, False))
STEP_A = Step(MARK, ROLE_MODULES, True, BACKUP_SUFFIX, STAMP_RE)
#: Другий крок (4d-3b, 0.18.0): `comments` і `vcs` ЛІГИ — явні модулі; без напрямків (`tracks=False`), свій бекап і позначка без `tracks`.
STEP_B = Step('liga-4d3b', ROLE_MODULES_B, False, '-liga-4d3b', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3b(?:-[0-9]{1,3})?'), _entries_b)
#: Усі відомі кроки в порядку застосування (відкат — у зворотному: LIFO) і ті, що біжать на старті/в CLI.
#: Третій крок (4d-3c, 0.19.0): `publish` ЛІГИ — явний `vercel-publish` з `compat`; без напрямків і секретів, свій бекап і позначка.
STEP_C = Step('liga-4d3c', ROLE_MODULES_C, False, '-liga-4d3c', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3c(?:-[0-9]{1,3})?'), _entries_c)
#: Четвертий крок (4d-4a, 0.20.0): напрямки ЛІГИ — остаточно явні (БЕЗ воріт паритету, розбіжності — нотатки позначки) і записи задач
#: (`track = profile`). Ролей нема; `ungated=True` — крок без воріт паритету й з записом `tasks.json`.
STEP_D = Step('liga-4d4a', (), True, '-liga-4d4a', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d4a(?:-[0-9]{1,3})?'), lambda cfg, present: {}, True)
#: П'ятий крок (4d-4b, 0.21.0): останні оригінали кореня `tasks.json` ЛІГИ — копія в записи (`gitlab_*`, `preview_password`) і видалення
#: з кореня за рівністю. Ролей нема; `originals=True` — гілка «оригінали» в `_plan`/`_run_locked`/`_restore_locked`.
STEP_E = Step('liga-4d4b', (), False, '-liga-4d4b', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d4b(?:-[0-9]{1,3})?'), lambda cfg, present: {}, False, True)
ALL_STEPS = (STEP_A, STEP_B, STEP_C, STEP_D, STEP_E)
#: Те, що біжить на старті й в CLI (4d-4b, Task 7: запис, відкат і вивід кроку Е вже є — п'ять кроків).
STEPS = ALL_STEPS


def _step(x):
    """`None` → перший крок (4d-3a); рядок-позначка → крок; `Step` → він сам. Невідома позначка — `ValueError` (`plan` лишає це
    `abort-internal`: непередбачена помилка розрахунку, без тексту винятку)."""
    if x is None:
        return ALL_STEPS[0]
    if isinstance(x, Step):
        return x
    for s in ALL_STEPS:
        if s.mark == x:
            return s
    raise ValueError('unknown step')


def step_of_stamp(stamp):
    """Крок, чий строгий `stamp_re` повністю збігається з імʼям бекапу, чи `None` (не імʼя бекапу міграції: `…-pre-restore`,
    шляхи, не рядок). Шукаємо серед УСІХ відомих кроків: імʼя однозначно каже, чий це бекап."""
    if not isinstance(stamp, str):
        return None
    return next((s for s in ALL_STEPS if s.stamp_re.fullmatch(stamp)), None)
BACKUP_FILES = ('tasks.json', 'space.json', 'secrets.json', 'spaces.json')
#: Статуси, після яких CLI не вважає запуск помилкою (нічого не зламано; «done» — міграцію виконано).
BENIGN = ('done', 'skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-held', 'skip-nothing', 'skip-integrations-off')
_RUN_REASONS = {
    'done': 'міграцію виконано',
    'abort-backup': 'бекап не створено: міграція нічого не записала',
    'abort-secrets': 'секрети не записано: space.json не змінено, наступний запуск почне заново',
    'abort-changed': 'запис ЛІГИ в реєстрі змінився між розрахунком і записом: міграція нічого не записала, наступний запуск почне заново',
    'abort-write': 'space.json не записано (секрети вже є — нешкідливо): наступний запуск почне заново',
}


def _tool_version():
    """Версія інструмента з `package.json` кореня репо (для маніфесту бекапу); не читається — `unknown`."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'package.json'), encoding='utf-8') as f:
            return str(json.load(f).get('version') or 'unknown')
    except (OSError, ValueError, AttributeError):
        return 'unknown'


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _atomic_bytes(path, data, mode):
    """Атомарний запис БАЙТІВ (відкат побайтно: `atomic_write_json` перепакував би JSON). Тимчасовий файл — власний, у тій самій теці."""
    path = os.path.realpath(path)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or '.', prefix=os.path.basename(path) + '.', suffix=TMP_SUFFIX)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _write_space(path, data):
    """Єдиний запис `space.json` міграції й відкату `--hold` (точка підміни для тестів «збій між секретами й space.json»)."""
    spaces._write_public(path, data)


_HINTS = {
    'skip-path-in-git': 'Перенесіть теку простору ЛІГА поза робоче дерево git (space.json не має потрапити в чужий коміт) і запустіть '
                        'міграцію знову: python3 bin/migrate_liga.py run. Поки тека в git, міграція на кожному старті пропускається.',
}


def _info(p, **extra):
    """Безпечний підсумок для `last.json` і друку: коди, імена ролей, без значень секретів і адрес."""
    out = {'status': p.get('status'), 'reason': p.get('reason') or '', 'space_id': p.get('space_id'),
           'roles': [r for r, v in (p.get('roles') or {}).items() if v.get('migrate')],
           'skipped': {r: v.get('reason') for r, v in (p.get('roles') or {}).items() if not v.get('migrate')},
           'tracks': bool(p.get('tracks')), 'tracks_reason': p.get('tracks_reason'),
           'records': len(p.get('records') or []), 'notes': list(p.get('notes') or [])}
    if p.get('status') in _HINTS:
        out['hint'] = _HINTS[p['status']]
    out.update(extra)
    return out


def _last_path():
    return os.path.join(spaces.home(), 'migrations', 'last.json')


def _read_last():
    try:
        with open(_last_path(), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_last(info, step=None):
    """`<DEAI_HOME>/migrations/last.json` — журнал останньої дії (без значень секретів). Найкращі зусилля: не кидає. Справжній звіт
    замінює файл цілком (разом зі старим ключем `skip`: пропуск уже неактуальний).
    ⛔ Форма (4d-3b, рішення 3): верхній рівень — звіт останньої дії, як у 4d-3a, плюс `step` (позначка кроку); `steps` — мапа
    `{позначка: звіт}` ВСІХ кроків, що вже писали. Мапу читаємо з наявного файла під ТИМ САМИМ замком і зберігаємо: звіт 4d-3b
    не стирає звіт 4d-3a. `step=None` (збій поза кроком) — `step` не пишемо, мапа лишається як була."""
    try:
        d = os.path.join(spaces.home(), 'migrations')
        with spaces.WRITE_LOCK:
            os.makedirs(d, mode=0o700, exist_ok=True)
            doc = dict(info, at=time.strftime('%Y-%m-%dT%H:%M:%S'))
            prev = _read_last().get('steps')
            steps = dict(prev) if isinstance(prev, dict) else {}
            if step is not None:
                doc['step'] = _step(step).mark
                steps[doc['step']] = dict(doc)
            if steps:
                doc['steps'] = steps
            atomic_write_json(os.path.join(d, 'last.json'), doc)
        return True
    except (OSError, ValueError):
        return False


def _write_skip(info):
    """Ключ `skip` у `last.json` для ПОСТІЙНОГО пропуску (тека простору в git): справжній звіт у файлі не затираємо. Той самий код
    двічі поспіль — без перезапису. Найкращі зусилля."""
    try:
        cur = _read_last()
        if (cur.get('skip') or {}).get('status') == info.get('status'):
            return False
        cur['skip'] = {'status': info.get('status'), 'reason': info.get('reason'), 'hint': info.get('hint'),
                       'at': time.strftime('%Y-%m-%dT%H:%M:%S')}
        d = os.path.join(spaces.home(), 'migrations')
        with spaces.WRITE_LOCK:
            os.makedirs(d, mode=0o700, exist_ok=True)
            atomic_write_json(os.path.join(d, 'last.json'), cur)
        return True
    except (OSError, ValueError):
        return False


@contextlib.contextmanager
def _exclusive():
    """Міжпроцесний замок `<DEAI_HOME>/migrations/.lock` (0600, `flock` БЕЗ очікування) на ВЕСЬ `run`/`restore`: дає `'ok'`, якщо
    взяли, `'busy'`, якщо зайнято іншим процесом (старт сервера ніколи не чекає), `'error'`, якщо `flock` відмовив з ІНШОЇ причини.
    ⛔ «Зайнято» — ЛИШЕ `EWOULDBLOCK`/`EAGAIN`: будь-яка інша `OSError` (напр. `ENOLCK` на файловій системі без flock) не має
    мовчки скіпати міграцію на кожному старті. Безпечніше й видиме: `'error'` → `abort-lock` у `last.json`/статусі, нічого не
    пишемо (йти без міжпроцесного замка не ризикуємо; `WRITE_LOCK` стереже лише потоки одного процесу). ⚠️ Замок стереже міграцію від другої міграції/відкату; з правками
    з екрана канваса він не знайомий: `run` із CLI, поки канвас того ж дому працює, може розійтись із правками UI (сам канвас
    мігрує лише на старті, після відкриття порту й до першого запиту)."""
    d = os.path.join(spaces.home(), 'migrations')
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(d, '.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                yield 'busy' if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN) else 'error'
                return
        yield 'ok'
    finally:
        os.close(fd)


def _mkdir_unique(root, base):
    """Нова тека `root/base` (0700); існує — `base-2`, `base-3`…; повертає імʼя."""
    name, n = base, 1
    while True:
        try:
            os.mkdir(os.path.join(root, name), 0o700)
            os.chmod(os.path.join(root, name), 0o700)
            return name
        except FileExistsError:
            n += 1
            name = '%s-%d' % (base, n)


def _list_backups():
    """Імена бекапів міграції УСІХ кроків: строге імʼя (`step_of_stamp`) І `manifest.json` усередині (недописана тека не рахується)."""
    root = os.path.join(spaces.home(), 'backups')
    try:
        return sorted(n for n in os.listdir(root) if step_of_stamp(n) is not None and os.path.isfile(os.path.join(root, n, 'manifest.json')))
    except OSError:
        return []


def _liga_entry(home):
    reg = _registry(home)
    liga = next((s for s in reg['spaces'] if s.get('legacy') is True), None)
    if liga is None:
        raise _Stop('skip-no-liga')
    return liga


def _backup(base, space_id, space_path, step=None):
    """Датований бекап кроку `step` (суфікс імені й `migration` маніфесту — з нього); повертає імʼя теки. Збій — виняток (викликач робить `abort-backup`); недописану теку прибираємо.
    Усі файли бекапу 0600, тека 0700: у `tasks.json` лежать облікові. Кожен файл: sha256 ДЖЕРЕЛА до копії, sha256 копії після, і
    джерело ще раз — зміна чи зникнення посеред бекапу = збій. `tasks.json` і `spaces.json` обовʼязкові (їхня відсутність — збій,
    не мовчазний пропуск); `space.json` і `secrets.json` — лише якщо є."""
    step = _step(step)
    root = os.path.join(base, 'backups')
    os.makedirs(root, mode=0o700, exist_ok=True)
    name = _mkdir_unique(root, time.strftime('%Y%m%d-%H%M%S') + step.suffix)
    d = os.path.join(root, name)
    try:
        sources = {'tasks.json': (install_config.legacy_tasks_path(), True), 'space.json': (os.path.join(space_path, 'space.json'), False),
                   'secrets.json': (deai_modules._secrets_path(), False), 'spaces.json': (spaces.registry_path(), True)}
        files = {}
        for fname, (src, required) in sources.items():
            if not os.path.isfile(src):
                if required:
                    raise OSError('source missing: ' + fname)
                continue
            before = _sha256(src)
            dst = os.path.join(d, fname)
            shutil.copyfile(src, dst)
            os.chmod(dst, 0o600)
            if _sha256(dst) != before or _sha256(src) != before:
                raise OSError('source changed during backup: ' + fname)
            files[fname] = {'source': src, 'sha256': before, 'mode': os.stat(src).st_mode & 0o777}
        manifest = {'tool': 'deai-canvas', 'version': _tool_version(), 'migration': step.mark, 'space_id': space_id,
                    'space_path': space_path, 'files': files}
        mp = os.path.join(d, 'manifest.json')
        with open(mp, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.chmod(mp, 0o600)
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return name


def _commit_space(space_path, p, stamp, step=None, records=None, mark_patch=None):
    """ОДИН атомарний запис `space.json`: злиття з ПОТОЧНИМ вмістом диска (перечитуємо під замком, відразу перед записом): чужі
    ключі й правки, зроблені після `plan()`, не губляться. Модуль, що зʼявився тим часом, не перезаписуємо. Позначка вже є — `skip-done`."""
    step = _step(step)
    sp = os.path.join(space_path, 'space.json')
    with spaces.WRITE_LOCK:
        cur = deai_modules._load_space_json(sp)
        mods = dict(deai_modules._raw_modules(cur))
        marks = cur.get('migrations')
        marks = dict(marks) if isinstance(marks, dict) else {}
        if step.mark in marks:
            return 'skip-done'
        planned = p['space_json']
        for role, r in p['roles'].items():
            if r['migrate'] and r['module'] not in mods:
                mods[r['module']] = planned['modules'][r['module']]
        new = dict(cur)
        new['modules'] = mods
        wrote = False
        if step.tracks and p['tracks'] and (tracks_core.adapter_applies(cur.get('tracks'), space_path) if step.ungated else cur.get('tracks') is None):
            new['tracks'], new['default_track'] = planned['tracks'], planned['default_track']
            wrote = True
        marks[step.mark] = dict(planned['migrations'][step.mark], at=time.strftime('%Y-%m-%dT%H:%M:%S'), backup=stamp, **(mark_patch or {}))
        if step.ungated:                                    # 4d-4a: позначка каже, що крок записав НАСПРАВДІ (власні напрямки, що зʼявились, не затираємо)
            marks[step.mark]['tracks'], marks[step.mark]['records'] = wrote, records
        new['migrations'] = marks
        _write_space(sp, new)
    return 'done'


#: Скільки разів `_commit_records` перечитує файл задач, якщо його змінив інший процес між читанням і записом.
_RECORDS_ATTEMPTS = 3


def _file_sig(path):
    """`(mtime_ns, size)` файла — дешевий знак «файл не змінювали» між читанням і записом."""
    st = os.stat(path)
    return st.st_mtime_ns, st.st_size


def _records_writable(path):
    """Чи можна записати `tasks.json` (тека — для тимчасового файла й `.bak`, сам файл і наявний `tasks.json.bak` — якщо є); перевіряємо
    ДО бекапу кроку: `.bak` без прав на запис зламав би `copy2` уже ПІСЛЯ бекапу простору."""
    return (os.access(os.path.dirname(path) or '.', os.W_OK) and (not os.path.exists(path) or os.access(path, os.W_OK))
            and (not os.path.exists(path + '.bak') or os.access(path + '.bak', os.W_OK)))


def _bak_copy(path):
    """`tasks.json.bak` — копія кореня, де можуть лежати облікові: права 0600 (збій `chmod` на не-POSIX ігноруємо)."""
    shutil.copy2(path, path + '.bak')
    try:
        os.chmod(path + '.bak', 0o600)
    except OSError:
        pass


def _commit_records(p, step):
    """4d-4a: `track = profile` у записах задач ЛІГИ (файл задач ЛІГИ — `install_config.legacy_tasks_path()`, той самий, що читав
    `plan`). Файл ПЕРЕЧИТУЄМО під `WRITE_LOCK` відразу перед записом (задача, додана після `plan()`, теж виправляється; чужі правки не
    губляться), `.bak` — як `serve.save_tasks`. Повертає кількість записаних записів; не кидає лише коли писати нічого. Крок
    без `ungated` чи без записів — `0` без дотику до диска."""
    if not step.ungated or not p.get('records'):
        return 0
    path = install_config.legacy_tasks_path()
    with spaces.WRITE_LOCK:                                  # ⛔ замок — лише ВНУТРІШНІЙ: інший ПРОЦЕС (сервер, CLI) його не бачить
        for _attempt in range(_RECORDS_ATTEMPTS):
            before = _file_sig(path)                         # (mtime_ns, size) ДО читання: зміна після нього помітна
            cfg = install_config.load_legacy_tasks()
            todo = _records_to_fix(cfg)
            if not todo:
                return 0
            for tid in todo:
                cfg['tasks'][tid]['track'] = cfg['tasks'][tid]['profile']
            _bak_copy(path)
            if _file_sig(path) == before:                    # ще раз ПЕРЕД записом: файл не чіпали — пишемо
                atomic_write_json(path, cfg)
                return len(todo)
        raise OSError('tasks file keeps changing')           # постійна гонка: не пишемо поверх чужого, наступний старт повторить


def _secrets_writable():
    """Чи можна писати `secrets.json` (тека дому — для тимчасового файла, сам файл — якщо є): перевірка ДО бекапу (як `_records_writable`)."""
    p, home = deai_modules._secrets_path(), spaces.home()
    return (not os.path.exists(home) or os.access(home, os.W_OK)) and (not os.path.exists(p) or os.access(p, os.W_OK))


def _space_writable(space_path):
    """Чи можна писати `space.json` простору (тека — для тимчасового файла, сам файл — якщо є): перевірка ДО бекапу (як `_records_writable`)."""
    sp = os.path.join(space_path, 'space.json')
    return os.access(space_path, os.W_OK) and (not os.path.exists(sp) or os.access(sp, os.W_OK))


def _durable_before_delete(space_path, stamp):
    """Крок Е ВИДАЛЯЄ з кореня: до того копії (`secrets.json`, `space.json`) і файли бекапу мусять бути на пластині, інакше збій живлення
    лишив би корінь без ключів, а копію — порожньою. Скидає файли й теки; збій — виняток (викликач: `abort-write`, нічого не видалено)."""
    bdir = os.path.join(spaces.home(), 'backups', stamp)
    paths = [deai_modules._secrets_path(), os.path.join(space_path, 'space.json')]
    paths += [os.path.join(bdir, n) for n in sorted(os.listdir(bdir))]
    for p in paths:
        if os.path.isfile(p):
            fsync_path(p)
    for p in (bdir, os.path.dirname(bdir), space_path, os.path.dirname(deai_modules._secrets_path())):
        fsync_path(p)


def _merge_settings(space_path, patches):
    """Копії налаштувань у ПОТОЧНИЙ `space.json` під `WRITE_LOCK`: перечитуємо, кладемо лише відсутні/порожні ключі запису, що ще є; чужі
    правки (і запис, що зник) не чіпаємо — розбіжність побачить перевірка `abort-verify`."""
    if not patches:
        return
    sp = os.path.join(space_path, 'space.json')
    with spaces.WRITE_LOCK:
        cur = deai_modules._load_space_json(sp)
        mods = dict(deai_modules._raw_modules(cur))
        changed = False
        for mid, patch in patches.items():
            rec = mods.get(mid)
            if not isinstance(rec, dict):
                continue
            st = rec.get('settings')
            st = dict(st) if isinstance(st, dict) else {}
            for k, v in patch.items():
                if not (isinstance(st.get(k), str) and st[k]):
                    st[k] = v
                    changed = True
            mods[mid] = dict(rec, settings=st)
        if changed:
            new = dict(cur)
            new['modules'] = mods
            _write_space(sp, new)


def _verify_copies(sid, space_path, d):
    """Після запису копій: перечитане з диска (без локу) дорівнює плану. Інакше `abort-verify` — нічого не видалено."""
    secrets = deai_modules._load_secrets()
    data = deai_modules._load_space_json(os.path.join(space_path, 'space.json'))
    norm = deai_modules._normalize(deai_modules._raw_modules(data))
    for mid, patch in d['copy_secrets'].items():
        for k, v in patch.items():
            if deai_modules._bucket(secrets, sid, mid).get(k) != v:
                return False
    for mid, patch in d['copy_settings'].items():
        for k, v in patch.items():
            if (norm.get(mid, {}).get('settings') or {}).get(k) != v:
                return False
    return True


def _commit_originals(sid, space_path, planned_remove, unconfirmed=None):
    """Видаляє з кореня `tasks.json` ЛІГИ ключі зі списку, чия рівність з копією ПІДТВЕРДЖЕНА щойно перечитаним диском. Під `WRITE_LOCK`:
    `_file_sig` → читання → повторне звіряння (людина могла змінити налаштування між копією й видаленням) → `.bak` → `_file_sig` →
    `atomic_write_json`. Ключі видаляються ПО ОДНОМУ з щойно прочитаного файла: записи задач і чужі ключі — як є. Повертає
    список видалених; постійна гонка — `OSError`.
    ⛔ Ключ, що в свіжому рішенні ще потребує КОПІЇ (`fresh['copied']`: людина стерла налаштування між перевіркою й видаленням), не
    видаляється: корінь тоді — єдина копія значення.
    `fsync` ПІСЛЯ rename не вдався (`DurabilityUnconfirmed`): корінь УЖЕ переписано — це не збій; у список `unconfirmed` (якщо передано)
    кладеться `True`, а викликач звітує «записано, довговічність не підтверджено»."""
    path = install_config.legacy_tasks_path()
    sp = os.path.join(space_path, 'space.json')
    with spaces.WRITE_LOCK:
        for _attempt in range(_RECORDS_ATTEMPTS):
            before = _file_sig(path)
            cfg = install_config.load_legacy_tasks()
            norm, secrets = _originals_state(space_path, deai_modules._load_space_json(sp), cfg)
            fresh = _decide_originals(cfg, norm, secrets, sid)
            todo = [k for k in planned_remove if k in fresh['remove'] and k not in fresh['copied'] and k in cfg]
            if not todo:
                return []
            for k in todo:
                del cfg[k]
            _bak_copy(path)
            if _file_sig(path) == before:
                try:
                    atomic_write_json(path, cfg, fsync=True)     # єдиний видаляючий запис кроку Е: довговічно (не `_commit_records`)
                except DurabilityUnconfirmed:                    # файл уже записано: звітуємо, не відкочуємо й не падаємо
                    if unconfirmed is not None:
                        unconfirmed.append(True)
                return todo
        raise OSError('tasks file keeps changing')


def _run_originals(home, step, p, space_path):
    """Запис кроку Е (спека §1.4): precheck → бекап → секрети → налаштування `space.json` → перевірка прочитанням → видалення з кореня →
    позначка (остання). Повертає `(статус, підсумок)`; кожен збій — код, без значень."""
    d = p['originals']
    if (p['originals']['remove'] or d['copy_settings'] or d['copy_secrets']) and not _records_writable(install_config.legacy_tasks_path()):
        info = _info(p, status='abort-originals', reason=_REASONS['abort-originals'])
        _write_last(info, step)
        return 'abort-originals', info
    if d['copy_secrets'] and not _secrets_writable():
        info = _info(p, status='abort-secrets', reason=_RUN_REASONS['abort-secrets'])
        _write_last(info, step)
        return 'abort-secrets', info
    if not _space_writable(space_path):                      # `space.json` не запишемо: інакше копії/позначка зламались б ПІСЛЯ бекапу
        info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'])
        _write_last(info, step)
        return 'abort-write', info
    try:
        stamp = _backup(spaces.home(), p['space_id'], space_path, step)
    except (OSError, ValueError):
        info = _info(p, status='abort-backup', reason=_RUN_REASONS['abort-backup'])
        _write_last(info, step)
        return 'abort-backup', info
    sid = p['space_id']
    try:
        for mid, patch in d['copy_secrets'].items():
            deai_modules.write_secrets(sid, mid, patch)
    except deai_modules.ModuleError as e:
        info = _info(p, status='abort-secrets', reason=_RUN_REASONS['abort-secrets'], backup=stamp, error=getattr(e, 'code', 'secrets'))
        _write_last(info, step)
        return 'abort-secrets', info
    try:
        _merge_settings(space_path, d['copy_settings'])
        ok = _verify_copies(sid, space_path, d)
    except (OSError, ValueError, deai_modules.ModuleError):
        info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
        _write_last(info, step)
        return 'abort-write', info
    if not ok:
        info = _info(p, status='abort-verify', reason=_REASONS['abort-verify'], backup=stamp)
        _write_last(info, step)
        return 'abort-verify', info
    try:
        _durable_before_delete(space_path, stamp)           # копії й бекап — на пластину ДО видалення з кореня
    except (OSError, ValueError):
        info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
        _write_last(info, step)
        return 'abort-write', info
    unconfirmed = []
    try:
        removed = _commit_originals(sid, space_path, d['remove'], unconfirmed)
    except (OSError, ValueError, RecursionError, KeyError, TypeError, deai_modules.ModuleError):
        info = _info(p, status='abort-originals', reason=_REASONS['abort-originals'], backup=stamp)
        _write_last(info, step)
        return 'abort-originals', info
    kept = sorted(set(p['space_json']['migrations'][step.mark]['kept']) | (set(d['remove']) - set(removed)))
    try:
        st = _commit_space(space_path, p, stamp, step, None, mark_patch={'removed': sorted(removed), 'kept': kept})
    except (OSError, ValueError, deai_modules.ModuleError):
        info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
        _write_last(info, step)
        return 'abort-write', info
    info = _info(p, status=st, reason=_RUN_REASONS.get(st) or _REASONS.get(st, ''), backup=stamp)
    info.update(copied=sorted(d['copied']), removed=sorted(removed), kept=kept)
    if unconfirmed:
        info['durability_unconfirmed'] = True
    if st == 'done':
        _write_last(info, step)
    return st, info


def _run(home, step=None):
    """`(статус, підсумок)` кроку `step` (`None` = 4d-3a); кожен виняток — код, без тексту винятку (там можуть бути значення). Увесь
    біг — під міжпроцесним замком (`skip-busy`, якщо зайнято); `plan()` рахується ВСЕРЕДИНІ замка, тож позначку/`held`, що зʼявились
    раніше, бачимо ДО запису секретів."""
    step = _step(step)
    if home and os.path.realpath(os.path.expanduser(home)) != os.path.realpath(spaces.home()):
        return 'abort-internal', {'status': 'abort-internal', 'reason': 'home не збігається з DEAI_HOME: запис пішов би в іншу теку'}
    p0 = plan(home, step)                                    # ⛔ дешевий розрахунок ПОЗА замком: нема що робити — диск не чіпаємо
    if p0['status'] != 'ready':                              # (ні `migrations/`, ні `.lock` у домі звичайного не-ЛІГА користувача)
        return _not_ready(p0, step)
    try:
        with _exclusive() as got:
            if got == 'busy':
                return 'skip-busy', {'status': 'skip-busy', 'reason': _REASONS['skip-busy']}
            if got != 'ok':
                info = {'status': 'abort-lock', 'reason': _REASONS['abort-lock']}
                _write_last(info, step)                      # видимо в last.json і status; не мовчки
                return 'abort-lock', info
            return _run_locked(home, step)
    except OSError as e:
        return 'abort-internal', {'status': 'abort-internal', 'reason': _REASONS['abort-internal'], 'error': type(e).__name__}


def _not_ready(p, step=None):
    """Результат не-`ready` розрахунку: `(статус, підсумок)`; на диск — лише журнал `abort-*` та постійний `skip-path-in-git`."""
    st = p['status']
    info = _info(p)
    if st.startswith('abort-'):
        _write_last(info, step)                              # лише журнал: стан не чіпаємо; skip-* журнал не затирає
    elif st == 'skip-path-in-git':
        _write_skip(info)                                    # постійний пропуск: окремий ключ, справжній звіт лишається
    return st, info


def _run_locked(home, step=None):
    step = _step(step)
    p = plan(home, step)                                     # повторно ВСЕРЕДИНІ замка: позначка/`held` могли зʼявитись, поки чекали
    st = p['status']
    if st != 'ready':
        return _not_ready(p, step)
    try:
        liga = _liga_entry(home)
        if os.path.realpath(liga['path']) != os.path.realpath(p['space_path']) or liga['id'] != p['space_id']:
            info = _info(p, status='abort-changed', reason=_RUN_REASONS['abort-changed'])
            _write_last(info, step)
            return 'abort-changed', info
        space_path = p['space_path']                         # пишемо ТУДИ Ж, звідки рахували
        if step.originals:
            return _run_originals(home, step, p, space_path)
        if step.ungated and p.get('records') and not _records_writable(install_config.legacy_tasks_path()):
            # ⛔ постійний збій запису (лише читання): бекап не робимо — кожен старт інакше лишав би по теці бекапу
            info = _info(p, status='abort-records', reason=_REASONS['abort-records'], records=0, records_planned=len(p['records']))
            _write_last(info, step)
            return 'abort-records', info
        try:
            stamp = _backup(spaces.home(), p['space_id'], space_path, step)
        except (OSError, ValueError):
            info = _info(p, status='abort-backup', reason=_RUN_REASONS['abort-backup'])
            _write_last(info, step)
            return 'abort-backup', info
        try:
            for mid, patch in p['secrets'].items():
                deai_modules.write_secrets(p['space_id'], mid, patch)
        except deai_modules.ModuleError as e:
            info = _info(p, status='abort-secrets', reason=_RUN_REASONS['abort-secrets'], backup=stamp, error=getattr(e, 'code', 'secrets'))
            _write_last(info, step)
            return 'abort-secrets', info
        try:
            n_records = _commit_records(p, step)
        except (OSError, ValueError, RecursionError, KeyError, TypeError):
            info = _info(p, status='abort-records', reason=_REASONS['abort-records'], backup=stamp,
                         records=0, records_planned=len(p['records']))      # `records` — скільки ЗАПИСАНО (атомарний запис: нуль)
            _write_last(info, step)
            return 'abort-records', info
        try:
            st = _commit_space(space_path, p, stamp, step, n_records if step.ungated else None)
        except (OSError, ValueError, deai_modules.ModuleError):
            info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
            if step.ungated:                                 # `records` — скільки ЗАПИСАНО вже (нешкідливо), не скільки планувалось
                info['records'], info['records_planned'] = n_records, len(p['records'])
            _write_last(info, step)
            return 'abort-write', info
        info = _info(p, status=st, reason=_RUN_REASONS.get(st) or _REASONS.get(st, ''), backup=stamp)
        if step.ungated:
            info['records'] = n_records
        if st == 'done':
            info['secrets'] = {m: sorted(s) for m, s in p['secrets'].items()}      # лише імена ключів
            _write_last(info, step)
        return st, info
    except _Stop as s:
        return s.status, {'status': s.status, 'reason': _REASONS.get(s.status, '')}
    except Exception as e:  # noqa: BLE001
        info = _info(p, status='abort-internal', reason=_REASONS['abort-internal'], error=type(e).__name__)
        _write_last(info, step)
        return 'abort-internal', info


def run(home=None, step=None):
    """Міграція ЛІГИ (крок `step`, `None` = 4d-3a): `plan()` → бекап → секрети → ОДИН запис `space.json` (з позначкою) → `last.json`.
    Повертає статус (`done`, `skip-*`, `abort-*`); будь-що, крім `ready` у `plan()`, нічого не пише (лише `abort-*` лишають рядок у
    `last.json`). Збій між секретами й `space.json` лишає нешкідливі секрети без позначки: наступний запуск починає з нуля."""
    return _run(home, step)[0]


def run_all(home=None, on_result=None):
    """Усі кроки `STEPS` по порядку: `[(позначка, статус, підсумок)]`. `abort-*` і `skip-busy` кроку зупиняють НАСТУПНІ (стан сумнівний /
    інший процес посеред кроку); решта `skip-*` (`skip-nothing`/`skip-done`) — ні, а `held` раннього кроку тримає наступні в `plan`. План наступного кроку рахується ПІСЛЯ запису попереднього (читає актуальний
    `space.json`). `on_result(mark, status, info)` — після кожного кроку (старт друкує рядок, поки наступний ще не пішов)."""
    out = []
    for step in STEPS:
        st, info = _run(home, step)
        out.append((step.mark, st, info))
        if on_result is not None:
            on_result(step.mark, st, info)
        if st.startswith('abort-') or st == 'skip-busy':      # зайнято іншим процесом: він може бути посеред кроку — наступні не рушаємо
            break
    return out


# ---------------------------------------------------------------------------------------------------------------- відкат

def _backup_dir(stamp):
    """Тека бекапу за ЗАВАЖНО строгим імʼям; не символічне посилання, лежить прямо в `<DEAI_HOME>/backups`."""
    if step_of_stamp(stamp) is None:                         # строге імʼя ЯКОГОСЬ кроку (не `-pre-restore`, не шлях)
        return None
    root = os.path.join(spaces.home(), 'backups')
    d = os.path.join(root, stamp)
    if os.path.islink(d) or not os.path.isdir(d) or os.path.dirname(os.path.realpath(d)) != os.path.realpath(root):
        return None
    return d


def _load_manifest(d, step=None):
    """Маніфест бекапу, перевірений на форму, на ТОЙ САМИЙ крок (`migration` = позначка кроку, чиє імʼя має тека) і sha256 КОЖНОГО
    файла; будь-яка розбіжність — `None` (нічого не відновлюємо)."""
    step = _step(step)
    try:
        with open(os.path.join(d, 'manifest.json'), encoding='utf-8') as f:
            m = json.load(f)
        files = m['files']
        if m.get('migration') != step.mark or not isinstance(files, dict) or not isinstance(m.get('space_id'), str):
            return None
        for fname, meta in files.items():
            if fname not in BACKUP_FILES or not isinstance(meta, dict):
                return None
            fp = os.path.join(d, fname)
            if os.path.islink(fp) or not os.path.isfile(fp) or _sha256(fp) != meta.get('sha256'):
                return None
            if not isinstance(meta.get('mode'), int):
                return None
        return m
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def restore(stamp, hold=False, home=None):
    """Відкат; повертає статус (див. `_restore`)."""
    return _restore(stamp, hold, home)[0]


def _pre_restore_copy(sid, sp):
    """⛔ Запобіжна копія ПОТОЧНОГО `space.json` ЛІГИ і ЛІГОВОЇ частини секретів (`secrets-liga.json`) у
    `backups/<бекап>-pre-restore[-N]/` (0700/0600, `manifest.json` із sha256): правки після міграції не зникають мовчки. Імʼя НЕ
    підходить під `STAMP_RE` — це не бекап міграції, відкотитись із нього не можна. Збій — виняток: відкат нічого не пише."""
    cur = deai_modules._load_secrets()
    part = cur.get(sid)
    root = os.path.join(spaces.home(), 'backups')
    os.makedirs(root, mode=0o700, exist_ok=True)
    return root, part


def _write_pre_restore(stamp, sid, sp, part):
    root = os.path.join(spaces.home(), 'backups')
    name = _mkdir_unique(root, stamp + '-pre-restore')
    d = os.path.join(root, name)
    try:
        files = {}
        if os.path.isfile(sp):
            dst = os.path.join(d, 'space.json')
            shutil.copyfile(sp, dst)
            os.chmod(dst, 0o600)
            files['space.json'] = {'source': sp, 'sha256': _sha256(dst)}
        if part is not None:
            dst = os.path.join(d, 'secrets-liga.json')
            with open(dst, 'w', encoding='utf-8') as f:
                json.dump({sid: part}, f, ensure_ascii=False, indent=2)
            os.chmod(dst, 0o600)
            files['secrets-liga.json'] = {'sha256': _sha256(dst)}
        mp = os.path.join(d, 'manifest.json')
        with open(mp, 'w', encoding='utf-8') as f:
            json.dump({'tool': 'deai-canvas', 'version': _tool_version(), 'kind': 'pre-restore', 'of': stamp, 'space_id': sid,
                       'files': files}, f, ensure_ascii=False, indent=2)
        os.chmod(mp, 0o600)
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return name


def _restore(stamp, hold=False, home=None):
    """Відкат: `space.json` ЛІГИ і ЛІГОВА частина `secrets.json` повертаються з бекапу (sha256 з маніфесту звіряється ДО будь-якого
    запису). Бекап без `space.json` — мігрований `space.json` прибираємо; без секретів — прибираємо запис ЛІГИ. Чужі записи
    `secrets.json` (інші простори/модулі, додані після міграції) ЗАВЖДИ лишаються; файл повертається побайтно, коли чужого
    вмісту не змінилось, інакше записується злиттям. Старий `tasks.json` і `spaces.json` не чіпаємо.
    ⛔ ПЕРЕД записом поточний `space.json` і ліговий шматок секретів кладуться в `backups/<бекап>-pre-restore/` (правки після
    міграції не губляться). Крок Е спершу домерджує корінь: якщо він відмовив чи збоїв (`refuse-tasks-unreadable`, `abort-restore`), НІЧОГО не
    записано, а запобіжну копію прибрано (осиротілої теки нема). `hold=True` дописує `migrations.<позначка кроку цього бекапу>.held` (лише його; ранній `held` тримає й наступні) — наступний старт не мігрує. Невідоме/підроблене імʼя —
    відмова (`refuse-stamp`/`refuse-tampered`/`refuse-no-liga`), нічого не пишемо. Увесь відкат — під міжпроцесним замком
    (`skip-busy`). Повертає `(статус, підсумок)`: статус `restored`, відмова, `skip-busy` чи `abort-restore`."""
    try:
        if home and os.path.realpath(os.path.expanduser(home)) != os.path.realpath(spaces.home()):
            return 'abort-internal', {}
        if not spaces.layer_on():
            return 'skip-layer-off', {}
        with _exclusive() as got:
            if got == 'busy':
                return 'skip-busy', {}
            if got != 'ok':
                return 'abort-lock', {}
            return _restore_locked(stamp, hold, home)
    except Exception:  # noqa: BLE001 — без тексту винятку
        return 'abort-restore', {}


def _applied_later(sp, step):
    """Бекап (імʼя) ОСТАННЬОГО з ПІЗНІШИХ за `step` кроків, що застосований у `space.json` (`migrations[mark]` є і не `held`), чи `None`
    (4d-3c: для `restore <a>` при застосованих b і c це бекап c — відкочувати треба спершу його, а не b, якого вже не відкотиш).
    Застосований без імені бекапу (позначку хтось дописав руками) — `''`: відмова все одно (імені просто нема). `space.json`,
    що не читається, пізніших кроків не показує (відкат його й так замінює)."""
    try:
        mig = deai_modules._load_space_json(sp).get('migrations')
    except deai_modules.ModuleError:
        return None
    if not isinstance(mig, dict):
        return None
    for s in reversed(ALL_STEPS[ALL_STEPS.index(step) + 1:]):
        mark = mig.get(s.mark)
        if mark is not None and not (isinstance(mark, dict) and mark.get('held') is True):
            return (mark.get('backup') if isinstance(mark, dict) else None) or ''
    return None


def _restore_root(sp, d):
    """Відкат кроку Е (4d-4b): ДОМЕРДЖ видалених ключів у ЖИВИЙ `tasks.json` ЛІГИ (НЕ перезапис файла: там уже нові задачі й правки людини).
    Перелік — з позначки `removed` ПОТОЧНОГО `space.json` (читаємо ДО його заміни); позначка нечитана чи без `removed` — усі `ORIGINAL_KEYS`
    бекапного `tasks.json`. Значення — з бекапу. Додається ЛИШЕ ключ, якого в живому корені нема; свій ключ людини лишається (`kept-live`).
    Під `WRITE_LOCK`: `_file_sig` → читання → `.bak` → `_file_sig` → `atomic_write_json`; ретраї `_RECORDS_ATTEMPTS`, постійна гонка — `OSError`.
    Живий файл не читається чи ЙОГО НЕМА — `_Stop('refuse-tasks-unreadable')` (нічого не записано). Повертає `(повернуто, kept_live, flags)`: списки
    імен ключів і `flags` = `{'root_fallback': перелік узято з усіх ORIGINAL_KEYS (позначка нечитана/без `removed`/`held`),
    'root_durability_unconfirmed': fsync після rename не вдався, файл записано}`.
    ⚠️ `tasks.json.bak` при цьому ПЕРЕЗАПИСУЄТЬСЯ станом ПЕРЕД відкатом (стан до кроку Е лишається в `backups/<бекап>`)."""
    keys = None
    try:
        mark = (deai_modules._load_space_json(sp).get('migrations') or {}).get(STEP_E.mark)
        removed = mark.get('removed') if isinstance(mark, dict) else None
        if isinstance(removed, list) and all(isinstance(k, str) for k in removed):
            keys = [k for k in removed if k in ORIGINAL_KEYS]
    except (deai_modules.ModuleError, AttributeError):
        keys = None
    with open(os.path.join(d, 'tasks.json'), encoding='utf-8') as f:
        old = json.load(f)
    if not isinstance(old, dict):
        raise ValueError('tasks backup: not an object')
    flags = {'root_fallback': keys is None, 'root_durability_unconfirmed': False}
    keys = [k for k in (ORIGINAL_KEYS if keys is None else keys) if k in old]
    path = install_config.legacy_tasks_path()
    with spaces.WRITE_LOCK:
        for _attempt in range(_RECORDS_ATTEMPTS):
            try:
                before = _file_sig(path)
                cfg = install_config.load_legacy_tasks()
            except (OSError, ValueError):
                raise _Stop('refuse-tasks-unreadable')
            if not isinstance(cfg, dict):
                raise _Stop('refuse-tasks-unreadable')
            add = [k for k in keys if k not in cfg]
            kept = sorted(k for k in keys if k in cfg)
            if not add:
                return [], kept, flags
            for k in add:
                cfg[k] = old[k]
            _bak_copy(path)
            if _file_sig(path) == before:
                try:
                    atomic_write_json(path, cfg, fsync=True)
                except DurabilityUnconfirmed:                    # файл уже записано: звітуємо, не абортуємо
                    flags['root_durability_unconfirmed'] = True
                return sorted(add), kept, flags
        raise OSError('tasks file keeps changing')


def _replaced_password(sid, d, files):
    """Відкат кроку Е: чи крок ЗАМІНИВ секрет `password` запису `vercel-publish` коренем `preview_password` (рішення власника 09.11.2026). Лише з БЕКАПУ:
    `(значення з кореня, старий секрет)` — коли обидва є і різні, інакше `None`. Бекап, що не читається, — виняток (відкат нічого не пише)."""
    if 'secrets.json' not in files:
        return None
    with open(os.path.join(d, 'tasks.json'), encoding='utf-8') as f:
        old_root = json.load(f)
    with open(os.path.join(d, 'secrets.json'), encoding='utf-8') as f:
        old_secrets = json.load(f)
    if not isinstance(old_root, dict) or not isinstance(old_secrets, dict) or 'preview_password' not in old_root:
        return None
    eff = _effective('preview_password', old_root['preview_password'])
    was = deai_modules._bucket(old_secrets, sid, 'vercel-publish').get('password')
    return (eff, was) if eff and was and eff != was else None


def _restore_locked(stamp, hold, home):
    d = _backup_dir(stamp)
    if d is None:
        return 'refuse-stamp', {}
    step = step_of_stamp(stamp)                              # імʼя бекапу каже, чий це крок
    m = _load_manifest(d, step)
    if m is None:
        return 'refuse-tampered', {}
    try:
        liga = _liga_entry(home)
    except _Stop:
        return 'refuse-no-liga', {}
    sid = m['space_id']
    if liga['id'] != sid:
        return 'refuse-no-liga', {}
    files = m['files']
    sp = os.path.join(liga['path'], 'space.json')
    # ⛔ LIFO (4d-3b): повернення `space.json` «до цього кроку» мовчки затерло б модулі, позначку й секрет ПІЗНІШОГО кроку, лишивши
    # осиротілий бекап. Пізніший крок застосований (позначка є, без `held`) — відмова ДО запобіжної копії й будь-якого запису.
    later = _applied_later(sp, step)
    if later is not None:
        return 'refuse-later-applied', {'rollback_first': later}

    def read(fname):
        with open(os.path.join(d, fname), 'rb') as f:
            return f.read()
    try:
        _root, part = _pre_restore_copy(sid, sp)
        safety = _write_pre_restore(stamp, sid, sp, part)
    except Exception:  # noqa: BLE001 — запобіжної копії нема: нічого не відкочуємо
        return 'abort-restore', {}
    root_restored = kept_live = None
    root_flags = {}
    replaced = None
    if step.originals:                                       # 4d-4b: корінь ПЕРШИМ — збій далі лишає простір мігрованим І з поверненими ключами
        try:
            replaced = _replaced_password(sid, d, files)     # читання бекапу ДО будь-якого запису
            root_restored, kept_live, root_flags = _restore_root(sp, d)
        except BaseException as s:
            # m4: до цього місця нічого, крім запобіжної копії, не записано — відмова/збій не лишає осиротілої `-pre-restore`.
            shutil.rmtree(os.path.join(spaces.home(), 'backups', safety), ignore_errors=True)
            if isinstance(s, _Stop):
                return s.status, {}
            raise
    # Спершу space.json: збій між двома записами лишає простір НЕмігрованим (секрети без запису нешкідливі), а не навпаки.
    with spaces.WRITE_LOCK:
        if 'space.json' in files:
            _atomic_bytes(sp, read('space.json'), files['space.json']['mode'] & 0o777)
        elif os.path.lexists(sp):
            os.remove(sp)
    kept_live_secrets = []
    with spaces.WRITE_LOCK:
        secrets_p = deai_modules._secrets_path()
        cur = deai_modules._load_secrets()
        raw = read('secrets.json') if 'secrets.json' in files else None
        bk = json.loads(raw.decode('utf-8')) if raw is not None else {}
        if not isinstance(bk, dict):
            raise ValueError('secrets backup: not an object')
        cur_rest = {k: v for k, v in cur.items() if k != sid}
        bk_rest = {k: v for k, v in bk.items() if k != sid}
        keep_pw = None                                       # секрет, який людина змінила ПІСЛЯ кроку (≠ корінь, ≠ старий): не затираємо (`kept_live_secrets`)
        if replaced is not None:
            live = deai_modules._bucket(cur, sid, 'vercel-publish').get('password')
            if live and live not in replaced:
                keep_pw = live
                kept_live_secrets.append('preview_password')
        if raw is not None and cur_rest == bk_rest and keep_pw is None:
            _atomic_bytes(secrets_p, raw, 0o600)             # чужого не змінилось — побайтно
        else:
            new = dict(cur_rest)                             # лише запис ЛІГИ — з бекапу; чужі секрети лишаються
            if sid in bk:
                new[sid] = bk[sid]
            if keep_pw is not None:
                part = dict(new.get(sid) if isinstance(new.get(sid), dict) else {})
                part['vercel-publish'] = dict(part.get('vercel-publish') if isinstance(part.get('vercel-publish'), dict) else {}, password=keep_pw)
                new[sid] = part
            if new:
                atomic_write_json(secrets_p, new)
                os.chmod(secrets_p, 0o600)
            elif os.path.lexists(secrets_p):
                os.remove(secrets_p)
    if hold:
        with spaces.WRITE_LOCK:
            cur = deai_modules._load_space_json(sp)
            marks = cur.get('migrations')
            marks = dict(marks) if isinstance(marks, dict) else {}
            marks[step.mark] = {'held': True}                # ⛔ лише позначка ЦЬОГО кроку: решту `--hold` не чіпає
            new = dict(cur)
            new['migrations'] = marks
            _write_space(sp, new)
    info = {'status': 'restored', 'reason': 'простір ЛІГА повернено з бекапу', 'space_id': sid, 'backup': stamp,
            'held': bool(hold), 'safety_copy': safety}
    if step.originals:
        info.update(root_restored=root_restored, kept_live=kept_live, kept_live_secrets=kept_live_secrets, **root_flags)
    _write_last(info, step)
    return 'restored', info


# ---------------------------------------------------------------------------------------------------------------- ролі ЛІГИ (4d-4b)

#: Шість ролей ЛІГИ: `(роль, вбудований модуль, крок-власник)`. Запасного постачальника нема (4d-4b): роль працює лише через ЯВНИЙ запис.
LIGA_ROLES = (('publish', 'vercel-publish', STEP_C), ('comments', 'supabase-comments', STEP_B), ('vcs', 'git-sync', STEP_B),
              ('dashboard', 'supabase-dashboard', STEP_A), ('tracker', 'jira-tracker', STEP_A), ('notify', 'supabase-teams', STEP_A))
_ENTRY_FIX = 'додайте адресу й облікові на екрані «Налаштування» (змінні оточення й pipeline-feedback більше не читаються)'
_RUN_FIX = 'python3 bin/migrate_liga.py run'
#: Код причини → що робити. Рядки без шляхів і значень (друкуються на КОЖНОМУ старті, поки роль вимкнена).
_ROLE_FIX = {
    'disabled': 'увімкніть запис на екрані «Налаштування»',
    'no-jira': _ENTRY_FIX, 'no-supabase': _ENTRY_FIX, 'bad-url': _ENTRY_FIX, 'not-migrated': _ENTRY_FIX,
    'publisher-present': 'публікацію веде інший модуль простору — так і було',
    'module-present': 'модуль ролі вже є в просторі — так і було',
    'skip-path-in-git': 'перенесіть теку простору ЛІГА поза робоче дерево git, далі: ' + _RUN_FIX,      # коротко: повна підказка друкується в рядку кроку раз
    'skip-tasks-unreadable': 'виправте старий tasks.json і запустіть: ' + _RUN_FIX,
    'skip-space-json-unreadable': 'виправте space.json простору ЛІГА і запустіть: ' + _RUN_FIX,
    'skip-registry-unreadable': 'виправте реєстр просторів (spaces.json) і запустіть: ' + _RUN_FIX,
    'skip-no-path': 'теки простору ЛІГА не існує: відновіть її чи змініть шлях у реєстрі, далі: ' + _RUN_FIX,
    'skip-busy': 'повторіть старт: міграцію зараз виконує інший процес',
    'module-error': 'модуль не завантажився: перевірте його на екрані «Налаштування»',
    'module-untrusted': 'довіртесь модулю на екрані «Налаштування»',
    'bad-settings': 'виправте налаштування запису на екрані «Налаштування»',
    'secrets-unreadable': 'secrets.json не читається: виправте файл у домі Deai',
    'space-json-unreadable': 'space.json не читається: виправте файл простору ЛІГА',
    'no-record': 'запустіть: ' + _RUN_FIX,
    'record-removed': 'запис видалено після міграції: додайте його на екрані «Налаштування» чи поверніть простір з бекапу (bin/migrate_liga.py restore <бекап>)',
}


def _held_mark(mig, owner):
    """Позначка першого кроку до `owner` включно, що утримано (`{held: true}`), чи `None`: `held` раннього кроку тримає й пізніші (спека §1)."""
    if not isinstance(mig, dict):
        return None
    for step in ALL_STEPS:
        m = mig.get(step.mark)
        if isinstance(m, dict) and m.get('held') is True:
            return step.mark
        if step is owner:
            break
    return None


def _reason_from_reports(role, owner, mig, last, home=None):
    """Код причини, чому в просторі нема ЗАПИСУ `role` (за порядком спеки §4.1): `held` (власника чи раннього кроку) → `skipped` кроку-власника
    (звіт `last.json` цього кроку) → позначка кроку (застосований без ролі — `not-migrated`; роль у `roles` позначки, а запису нема —
    `record-removed`) → статус ЧИСТОГО `plan(step=owner)` (`skip-path-in-git`, `skip-tasks-unreadable`, `abort-*`…: `last.json` постійних
    пропусків не зберігає, тож читати його тут — мертва гілка) → `no-record`."""
    mark = mig.get(owner.mark) if isinstance(mig, dict) else None
    rep = ((last or {}).get('steps') or {}).get(owner.mark) if isinstance(last, dict) else None
    rep = rep if isinstance(rep, dict) else {}
    skipped = rep.get('skipped') if isinstance(rep.get('skipped'), dict) else {}
    if _held_mark(mig, owner):                                # `held` власника АБО раннього кроку (ранній тримає пізніші)
        return 'skip-held'
    if role in skipped and skipped[role]:
        return skipped[role]
    if isinstance(mark, dict):                                # крок застосований, а запису нема: роль пропущено (код не збережено) чи запис видалено
        return 'not-migrated' if role not in (mark.get('roles') or []) else 'record-removed'
    st = plan(home, owner).get('status')                      # чистий розрахунок: нічого не пише
    if isinstance(st, str) and (st.startswith('skip-') or st.startswith('abort-')) and st not in (
            'skip-done', 'skip-nothing', 'skip-layer-off', 'skip-no-liga', 'skip-integrations-off', 'skip-held', 'abort-internal'):
        return st
    return 'no-record'


def roles_state(home=None):
    """Стан шести ролей ЛІГИ для старту й `status`: `[{role, module, on, reason, fix}]` (порядок `LIGA_ROLES`) або `[]`, коли шару нема / простору
    ЛІГА нема. ЧИСТА: без мережі й без коду модуля (`module_ctx` лише збирає налаштування й секрет). `on` — `_provider_for` дає ЯВНИЙ
    `Module` цієї ролі і `module_ctx` будується. Причина — перша застосовна: `disabled` (запис вимкнено) → причина кроку (`no-jira`,
    `no-supabase`, `bad-url`, `skip-held`, `skip-path-in-git`, `abort-*`…) → `module-error`/`module-untrusted`/`bad-settings` (запис є, не
    працює) → `no-record`. `integrations` ЛІГИ вимкнено — усі ролі `on: False`, `reason: 'integrations-off'`, `fix: ''` (так було й у 0.20)."""
    try:
        if not spaces.layer_on():
            return []
        liga = _liga_entry(home)
    except _Stop:
        return []
    if not _liga_integrations(liga):
        return [{'role': r, 'module': m, 'on': False, 'reason': 'integrations-off', 'fix': ''} for r, m, _s in LIGA_ROLES]
    space = {'id': liga['id'], 'path': liga['path'], 'legacy': True}
    try:
        data = deai_modules._load_space_json(os.path.join(liga['path'], 'space.json'))
        mods = deai_modules._raw_modules(data)
        norm = deai_modules._normalize(mods)
        mig = data.get('migrations')
    except deai_modules.ModuleError:
        return [{'role': r, 'module': m, 'on': False, 'reason': 'space-json-unreadable', 'fix': _ROLE_FIX['space-json-unreadable']}
                for r, m, _s in LIGA_ROLES]
    last = _read_last()
    out = []
    for role, mid, owner in LIGA_ROLES:
        reason = None
        try:
            prov = deai_modules._provider_for(role, space)
            if isinstance(prov, deai_modules.Module):         # m5: ЯВНИЙ модуль ролі — свій чи ІНШИЙ (`static-publish`…): роль працює, з його id
                deai_modules.module_ctx(space, prov)
                out.append({'role': role, 'module': prov.id, 'on': True, 'reason': None if prov.id == mid else 'served-by:%s' % prov.id, 'fix': ''})
                continue
        except deai_modules.ModuleError as e:
            reason = e.code if e.code in _ROLE_FIX else 'module-error'
        if reason is None:
            e_ = norm.get(mid)
            if e_ is not None and e_.get('enabled') is not True:
                reason = 'disabled'
            elif e_ is None:
                reason = _reason_from_reports(role, owner, mig, last, home)
            else:
                reason = 'module-error'
        if reason == 'skip-held':
            fix = 'python3 bin/migrate_liga.py unhold %s, далі: %s' % (_held_mark(mig, owner) or owner.mark, _RUN_FIX)
        elif reason.startswith('abort-'):
            fix = 'дивіться python3 bin/migrate_liga.py status (рядок кроку %s) і усуньте причину, далі: %s' % (owner.mark, _RUN_FIX)
        elif reason == 'not-migrated' and role in ('vcs', 'comments'):
            fix = 'запустіть %s (або увімкніть модуль на екрані «Налаштування»)' % _RUN_FIX
        else:
            fix = _ROLE_FIX.get(reason, _RUN_FIX)
        out.append({'role': role, 'module': mid, 'on': False, 'reason': reason, 'fix': fix})
    return out


def roles_lines(states):
    """Рядки старту про вимкнені ролі: `ролі ЛІГИ вимкнено: <роль> (<модуль>) — <код>; виправити: <команда>` по рядку на роль. Усі ролі
    ввімкнено чи `integrations` вимкнено (так було й у 0.20) — порожньо."""
    return ['ролі ЛІГИ вимкнено: %s (%s) — %s; виправити: %s' % (s['role'], s['module'], s['reason'], s['fix'])
            for s in states if not s['on'] and s['reason'] != 'integrations-off']


#: Рядок після кроку Е: де тепер лежать облікові (спека §6, ризик «єдина копія»). `tasks.json.bak` — теж копія (0600), поки його не перезапише наступний запис.
ORIGINALS_REMOVED_LINE = 'оригінали видалено з tasks.json; копії — secrets.json, backups/ у домі Deai і tasks.json.bak (права 0600)'

#: Рядок, коли корінь ЛІГИ ще має `preview_password`, а запис `vercel-publish` секрету `password` не має: Deai корінь не читає, тож закритий
#: превʼю тихо став би спільним `1100`. Лише імʼя ключа.
UNREAD_PREVIEW_PASSWORD_LINE = ('preview_password у корені tasks.json Deai не читає, а запис vercel-publish пароля не має — превʼю візьме спільний '
                                'пароль за замовчуванням; виправити: %s (крок утримано (held) — спершу unhold; або задайте секрет password '
                                'запису vercel-publish)' % _RUN_FIX)
#: Рядок, коли корінь має `preview_password`, а секрет `password` запису — ІНШИЙ (напр. після `restore` чи ручної зміни): діє запис.
DIFFERING_PREVIEW_PASSWORD_LINE = ('preview_password у корені tasks.json розходиться із секретом password запису vercel-publish; діє запис '
                                   '(корінь Deai не читає) — приберіть ключ із кореня або, щоб переміг корінь, %s' % _RUN_FIX)


def unread_preview_password_line(home=None):
    """Коли корінь `tasks.json` ЛІГИ має непорожній `preview_password`, якого немає в секреті `password` запису `vercel-publish` (крок Е не
    виконано чи не спожив ключ): `UNREAD_PREVIEW_PASSWORD_LINE`, якщо секрету немає (превʼю впаде на спільний), або
    `DIFFERING_PREVIEW_PASSWORD_LINE`, якщо секрет інший (діє запис); інакше `None`. Чиста; не кидає (нечитане — `None`). Значення не повертає."""
    try:
        if not spaces.layer_on():
            return None
        liga = _liga_entry(home)
        raw = install_config.load_legacy_tasks().get('preview_password')
        eff = _effective('preview_password', raw)
        if eff is None:
            return None
        held = deai_modules._bucket(deai_modules._load_secrets(), liga['id'], 'vercel-publish').get('password')
        if held == eff:
            return None
        return DIFFERING_PREVIEW_PASSWORD_LINE if held else UNREAD_PREVIEW_PASSWORD_LINE
    except (_Stop, OSError, ValueError, AttributeError, deai_modules.ModuleError):
        return None


def originals_summary(info):
    """Підсумок кроку Е для старту й CLI: `скопійовано: …; видалено: …; лишилось: …; нотатки: …` (імена ключів і коди, без значень)."""
    parts = []
    for key, label in (('copied', 'скопійовано'), ('removed', 'видалено'), ('kept', 'лишилось')):
        if info.get(key):
            parts.append('%s: %s' % (label, ', '.join(info[key])))
    if info.get('notes'):
        parts.append('нотатки: ' + ', '.join(info['notes']))
    if info.get('durability_unconfirmed'):
        parts.append('записано, довговічність не підтверджено (fsync)')
    return '; '.join(parts) or 'нічого не змінено'


def unhold(mark, home=None):
    """Знімає `{held: true}` кроку `mark` (ключ позначки, `liga-4d4a`…) у `space.json` ЛІГИ: наступний старт знову виконає крок. Лише позначку,
    що є РІВНО `{held: true}` (позначка застосованого кроку — відмова `refuse-not-held`); невідомий ключ — `refuse-mark`. Під міжпроцесним
    замком і `WRITE_LOCK`. Повертає статус: `unheld`, `refuse-mark`, `refuse-not-held`, `refuse-no-liga`, `skip-busy`, `skip-layer-off`, `abort-unhold`."""
    try:
        if home and os.path.realpath(os.path.expanduser(home)) != os.path.realpath(spaces.home()):     # як `_run`: запис пішов би в іншу теку
            return 'abort-internal'
        step = next((s for s in ALL_STEPS if s.mark == mark), None)
        if step is None:
            return 'refuse-mark'
        if not spaces.layer_on():
            return 'skip-layer-off'
        with _exclusive() as got:
            if got == 'busy':
                return 'skip-busy'
            if got != 'ok':
                return 'abort-lock'
            try:
                liga = _liga_entry(home)
            except _Stop:
                return 'refuse-no-liga'
            sp = os.path.join(liga['path'], 'space.json')
            with spaces.WRITE_LOCK:
                cur = deai_modules._load_space_json(sp)
                marks = cur.get('migrations')
                if not (isinstance(marks, dict) and marks.get(step.mark) == {'held': True}):
                    return 'refuse-not-held'
                new = dict(cur)
                new['migrations'] = {k: v for k, v in marks.items() if k != step.mark}
                _write_space(sp, new)
            return 'unheld'
    except Exception:  # noqa: BLE001 — без тексту винятку
        return 'abort-unhold'


# ---------------------------------------------------------------------------------------------------------------- статус

def status(home=None):
    """Стан для людини (словник без значень секретів): запис ЛІГИ, позначка, останній звіт, бекапи. Ключі 4d-3a без змін (`mark` —
    позначка кроку 4d-3a), плюс `steps`: `{позначка: {'mark': позначка кроку | None, 'backups': усі бекапи}}` для кожного кроку `STEPS`."""
    out = {'liga': False, 'space_id': None, 'mark': None, 'last': None, 'backups': [], 'error': None, 'steps': {}, 'roles': []}
    try:
        liga = _liga_entry(home)
    except _Stop as s:
        out['error'] = s.status
        liga = None
    marks = {s.mark: None for s in STEPS}
    if liga:
        out['liga'], out['space_id'] = True, liga['id']
        try:
            data = deai_modules._load_space_json(os.path.join(liga['path'], 'space.json'))
            mig = data.get('migrations')
            for key in marks:
                mark = mig.get(key) if isinstance(mig, dict) else None
                marks[key] = ({k: mark[k] for k in ('at', 'roles', 'tracks', 'records', 'notes', 'backup', 'held', 'copied', 'removed', 'kept') if k in mark}
                              if isinstance(mark, dict) else None)
            out['mark'] = marks.get(_step(None).mark)
        except deai_modules.ModuleError:
            out['error'] = 'skip-space-json-unreadable'
    out['last'] = _read_last() or None
    out['backups'] = _list_backups()
    out['steps'] = {key: {'mark': m, 'backups': list(out['backups'])} for key, m in marks.items()}
    try:
        out['roles'] = roles_state(home)
    except Exception:  # noqa: BLE001 — `status` не падає через стан ролей
        out['roles'] = []
    out['unread_preview_password'] = unread_preview_password_line(home) if liga else None      # рядок (лише імʼя ключа) або None
    return out


def status_text(st):
    """Український текст `status()`: секція на крок `STEPS` (з одним кроком — рівно текст 4d-3a). ⛔ Без значень секретів."""
    last = st.get('last')
    steps = st.get('steps') or {_step(None).mark: {'mark': st.get('mark')}}
    multi = len(steps) > 1
    lines = []
    for key, info in steps.items():
        lines.append('Міграція ЛІГИ (%s)' % key)
        if not st['liga']:
            lines.append('  простору ЛІГА в реєстрі нема' + (' (%s)' % st['error'] if st.get('error') else ''))
        else:
            lines.append('  простір: ' + str(st['space_id']))
            m = info.get('mark')
            if m is None:
                lines.append('  позначки нема: міграція ще не виконана (або відкочена)')
            elif m.get('held'):
                lines.append('  позначка: вимкнено вручну (held); зняти: python3 bin/migrate_liga.py unhold %s' % key)
            else:
                tr = (', напрямки: ' + ('так' if m.get('tracks') else 'ні')) if _step(key).tracks else ''     # рядок напрямків — лише кроку з напрямками
                if _step(key).ungated:                                       # 4d-4a: записи й нотатки (лише коди, без шляхів і значень)
                    tr += ', записи: %s, нотатки: %s' % (m.get('records', 0), ', '.join(m.get('notes') or []) or '-')
                if _step(key).originals:                                     # 4d-4b: ключі кореня (імена, без значень)
                    tr += ', ' + originals_summary(m)
                lines.append('  позначка: %s, ролі: %s%s, бекап: %s' % (
                    m.get('at'), ', '.join(m.get('roles') or []) or '-', tr, m.get('backup')))
        rep = ((last or {}).get('steps') or {}).get(key) if multi and isinstance(last, dict) else last   # звіт ЦЬОГО кроку
        if isinstance(rep, dict):
            if rep.get('status'):
                lines.append('  останній звіт: %s (%s)' % (rep.get('status'), rep.get('at')))
            unmig = rep.get('skipped')
            if isinstance(unmig, dict) and unmig:
                lines.append('  не мігровано: ' + ', '.join('%s (%s)' % (r, c) for r, c in sorted(unmig.items())))
        if not multi:
            lines.extend(_skip_lines(last))
    if multi:
        lines.extend(_skip_lines(last))
    lines.append('  бекапи: ' + (', '.join(st['backups']) or 'нема'))
    if st.get('unread_preview_password'):                            # 4d-4b: лише імʼя ключа
        lines.append('  ' + st['unread_preview_password'])
    roles = st.get('roles') or []
    if roles:                                                        # 4d-4b: усі шість ролей ЛІГИ — `так`/`ні (<код>)`
        lines.append('Ролі ЛІГИ')
        if all(r['reason'] == 'integrations-off' for r in roles):
            lines.append('  інтеграції вимкнено — так і було')
        else:
            lines.extend('  %s (%s): %s' % (r['role'], r['module'], ('так (інший модуль)' if str(r['reason']).startswith('served-by:') else 'так')
                                              if r['on'] else 'ні (%s)' % r['reason']) for r in roles)
    return '\n'.join(lines)


#: Рядок для старту й CLI, коли напрямки ЛІГИ НЕ мігровано (крок 4d-4a пропущено чи не вдався): що бачитиме людина.
TRACKS_NOT_MIGRATED = 'напрямки ЛІГИ не мігровані — нові задачі лягають у теку простору'

#: Статуси кроку 4d-4a, після яких про «напрямки не мігровані» мовчимо: нічого не зламано, або кроку тут нема, або він уже виконаний.
TRACKS_QUIET = ('done', 'skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-nothing', 'skip-integrations-off', 'skip-busy')


def tracks_not_migrated(status):
    """Чи казати людині «напрямки ЛІГИ не мігровані» після цього статусу кроку 4d-4a (held, пропуски, `abort-*`)."""
    return status not in TRACKS_QUIET


def summary_line(info):
    """Підсумок кроку 4d-4a для старту й CLI: `напрямки: записано|вже явні; записи: N; нотатки: a, b` (нотатки — коди без шляхів)."""
    if info.get('tracks'):
        head = 'записано'
    else:
        head = 'вже явні' if info.get('tracks_reason') == 'tracks-present' else 'не змінено (%s)' % (info.get('tracks_reason') or '-')
    parts = ['напрямки: ' + head]
    if info.get('records'):
        parts.append('записи: %d' % info['records'])
    if info.get('notes'):
        parts.append('нотатки: ' + ', '.join(info['notes']))
    return '; '.join(parts)


def _skip_lines(last):
    """Рядки ПОСТІЙНОГО пропуску (`skip` у `last.json`, напр. тека простору в git) — одні на всі кроки."""
    lines = []
    if last:
        skip = last.get('skip')
        if isinstance(skip, dict):
            lines.append('  пропущено: %s — %s' % (skip.get('status'), skip.get('reason')))
            if skip.get('hint'):
                lines.append('  що робити: ' + str(skip['hint']))
    return lines


# ---------------------------------------------------------------------------------------------------------------- старт сервера

def _real_home():
    """Чи `spaces.home()` — справжній `~/.deai` (за `realpath`; і за теками з пароля ОС, і за `$HOME`)."""
    cur = os.path.realpath(spaces.home())
    cands = {os.path.realpath(os.path.expanduser('~/.deai'))}
    try:
        import pwd
        cands.add(os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, '.deai')))
    except (ImportError, KeyError, OSError):
        pass
    return cur in cands


def _liga_integrations(liga):
    """Чи простір `legacy: true` — ЛІГА (інтеграції ввімкнені): явний `bool` ключа `integrations` виграє (історичні записи 0.21), а коли
    ключа нема — за маркерами кореня старого `tasks.json` (`_has_markers`). Будь-яка помилка читання — `True` (безпечний бік: не чіпаємо).
    Єдине місце в коді, що читає ключ `integrations`."""
    v = liga.get('integrations')
    if isinstance(v, bool):
        return v
    try:
        cfg = spaces._read_json(spaces.legacy_tasks_file())
        return bool(isinstance(cfg, dict) and _has_markers(cfg))
    except Exception:  # noqa: BLE001 — будь-який збій = «ЛІГА»
        return True


def liga_space(sp):
    """`True` для запису `legacy: true`, що є ЛІГОЮ (див. `_liga_integrations`); для решти — `False`. Збій — `True` для `legacy`-запису."""
    try:
        return sp.get('legacy') is True and _liga_integrations(sp)
    except Exception:  # noqa: BLE001
        return isinstance(sp, dict) and sp.get('legacy') is True


def startup():
    """Виклик із `serve.serve_main` ПІСЛЯ `make_server` (порт уже зайнято), до `serve_forever`. Ізольований прогін (`isolation.isolated()`) не мігрує, крім шва
    `DC_MIGRATE_LIGA=1` ЛИШЕ з тимчасовим `DEAI_HOME` (справжній `~/.deai` — гучна відмова). Не кидає ніколи: виняток — у stderr
    (імʼя типу, без значень) і в `last.json`. Повертає статус чи `None`. Кроки `STEPS` — по порядку (`run_all`): `abort-*` і `skip-busy`
    зупиняють наступні на цьому старті; `held` раннього кроку теж тримає наступні (їхній `plan` — `skip-held`); решта `skip-*`
    (`skip-nothing`/`skip-done`/…) наступних не блокує. Повертає статус ПЕРШОГО кроку, що не `skip-*` (найважливіше), інакше — першого кроку."""
    done, hints, hints_tracks = [], set(), []
    try:
        if isolation.isolated():
            if os.environ.get('DC_MIGRATE_LIGA') != '1':
                return None
            if _real_home():
                print('міграція ЛІГИ: DC_MIGRATE_LIGA=1 разом зі справжнім DEAI_HOME (~/.deai): відмова, міграцію не запущено', file=sys.stderr)
                return 'refuse-real-home'

        stamps_done = []                                                     # бекапи кроків, виконаних на цьому старті (у порядку a, b, c)
        repeats = {}                                                         # (статус, причина) постійного пропуску → позначки кроків-повторів

        def announce(mark, st, info):
            done.append(st)
            if mark == STEP_D.mark and tracks_not_migrated(st):             # 4d-4a: що буде з напрямками, коли крок не виконано
                hints_tracks.append(TRACKS_NOT_MIGRATED)
            if st not in ('skip-layer-off', 'skip-done', 'skip-integrations-off') and not st.startswith('skip-no'):
                if st.startswith('skip-'):                                   # M1: той самий постійний пропуск на кількох кроках — один рядок
                    key = (st, info.get('reason') or '')
                    if key in repeats:
                        repeats[key].append(mark)
                        return
                    repeats[key] = []
                print('%s: %s — %s' % (mark, st, info.get('reason') or ''), file=sys.stderr)
                if info.get('hint') and info['hint'] not in hints:           # однакова підказка (тека в git) — раз на старт
                    hints.add(info['hint'])
                    print('  ' + info['hint'], file=sys.stderr)
                # ⛔ Часткова міграція мовчить найгірше: позначку записано, а роль (напр. трекер без облікових у оточенні, коли
                # старт — з Dock/PWA) лишилась неявною й не повториться. Рядок: роль і КОД причини, без значень.
                stamp = info.get('backup')
                if st == 'done' and step_of_stamp(stamp):                    # лише імʼя бекапу (без шляху до дому)
                    stamps_done.append(stamp)
                    print('  бекап: %s' % stamp, file=sys.stderr)
                if mark == STEP_D.mark and st == 'done':                     # 4d-4a: що людина бачитиме (нотатки)
                    print('  ' + summary_line(info), file=sys.stderr)
                if mark == STEP_E.mark and st == 'done':                     # 4d-4b: що скопійовано/видалено/лишилось (імена ключів) і де єдина копія
                    print('  ' + originals_summary(info), file=sys.stderr)
                    if info.get('removed'):
                        print('  ' + ORIGINALS_REMOVED_LINE, file=sys.stderr)
                skipped = info.get('skipped')
                if isinstance(skipped, dict) and skipped:
                    print('  не мігровано: ' + ', '.join('%s (%s)' % (r, c) for r, c in sorted(skipped.items())), file=sys.stderr)
        try:
            run_all(None, on_result=announce)
        finally:
            for (rst, _reason), marks in repeats.items():
                if marks:
                    print('  те саме для: %s (%s)' % (', '.join(marks), rst), file=sys.stderr)
            for line in hints_tracks:                                       # після рядка статусу кроку (він друкується в `announce`)
                print('  ' + line, file=sys.stderr)
            # ⛔ LIFO: підказка відкату — ОДНА, для найпізнішого виконаного кроку (відкат раннього при застосованому пізнішому — відмова).
            if stamps_done:
                print('  відкат: bin/migrate_liga.py restore %s --hold' % stamps_done[-1], file=sys.stderr)
                if len(stamps_done) > 1:
                    print('  раніші кроки (%s) — лише після відкату пізніших, у зворотному порядку' % ', '.join(stamps_done[:-1]), file=sys.stderr)
        if not isolation.isolated():                                         # 4d-4b: кожна вимкнена роль — рядком, причина й команда виправлення
            try:                                                             # I3: звіт про ролі не має перетворити вдалу міграцію на `abort-internal`
                for line in roles_lines(roles_state()):
                    print(line, file=sys.stderr)
                pw_line = unread_preview_password_line()
                if pw_line:
                    print(pw_line, file=sys.stderr)
            except Exception as e:  # noqa: BLE001 — лише імʼя типу
                print('ролі ЛІГИ: стан не визначено (%s)' % type(e).__name__, file=sys.stderr)
        # abort не маскуємо пізнішим успіхом: перший `abort-*`, інакше перший не-`skip-*`, інакше перший
        return (next((s for s in done if s.startswith('abort-')), None) or next((s for s in done if not s.startswith('skip-')), None)
                or (done[0] if done else None))
    except Exception as e:  # noqa: BLE001
        try:
            mark = (STEPS[min(len(done), len(STEPS) - 1)] if STEPS else _step(None)).mark     # крок, що не дійшов до звіту
            print('%s: abort-internal — %s' % (mark, type(e).__name__), file=sys.stderr)
            _write_last({'status': 'abort-internal', 'reason': _REASONS['abort-internal'], 'error': type(e).__name__})
        except Exception:  # noqa: BLE001
            pass
        return 'abort-internal'
