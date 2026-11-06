"""Міграція простору ЛІГА в явні `tracks` і модулі (етап 4d-3a, 0.17.0; спека `docs/superpowers/specs/2026-11-05-liga-migration-a-design.md`).

Тут — ЧИСТИЙ розрахунок `plan()` і безпечний для друку `report(plan)`: `plan()` нічого не пише на диск. Запис (`run`), відкат
(`restore`), `status` і старт сервера (`startup`) — нижче, після `report()`. Модуль не імпортує `serve` (лише `spaces`,
`deai_modules`, `tracks`, `install_config`, `implicit`).

4d-3b (0.18.0): модуль — ВПОРЯДКОВАНИЙ СПИСОК кроків (`Step`, `ALL_STEPS`/`STEPS`): свій бекап, позначка й відкат на крок; `plan/run/
restore/status` без аргументу `step` — крок 4d-3a; `run_all()`/`startup()`/CLI ідуть по `STEPS` (`abort-*` зупиняє наступні, `skip-*` — ні);
відкат LIFO (`refuse-later-applied`); `last.json` — верхній рівень як у 4d-3a + `step`, і мапа `steps`. Нижче документація 4d-3a.

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
import implicit
import install_config
import spaces
import tracks as tracks_core
from atomic_io import TMP_SUFFIX, atomic_write_json

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
              'skip-space-json-unreadable', 'skip-registry-unreadable', 'skip-tasks-unreadable', 'skip-nothing', 'skip-busy')
ABORT_CODES = ('abort-provider', 'abort-internal', 'abort-lock')
_REASONS = {
    'skip-layer-off': 'шар просторів вимкнено: міграція не біжить',
    'skip-no-liga': 'у реєстрі нема простору ЛІГА',
    'skip-done': 'міграцію вже виконано (позначка в space.json)',
    'skip-held': 'міграцію вимкнено вручну (held у space.json)',
    'skip-no-path': 'теки простору ЛІГА не існує',
    'skip-path-in-git': 'тека простору лежить у робочому дереві git: space.json не має потрапити в чужий коміт',
    'skip-space-json-unreadable': 'space.json простору ЛІГА не читається',
    'skip-registry-unreadable': 'реєстр просторів не читається',
    'skip-tasks-unreadable': 'старий tasks.json не читається: конфіг ЛІГИ невідомий',
    'skip-nothing': 'нічого мігрувати (нема ні ролей, ні напрямків): позначку не пишемо, наступний старт перевірить знову',
    'skip-busy': 'міграція вже виконується іншим процесом (замок migrations/.lock зайнятий)',
    'abort-provider': 'ядро не вирішує мігровану роль на розрахованому space.json: міграція нічого не пише',
    'abort-internal': 'непередбачена помилка розрахунку: міграція нічого не пише',
    'abort-lock': 'міжпроцесний замок недоступний (flock не працює на цій файловій системі): міграція нічого не пише, щоб не йти без замка',
}


class _Stop(Exception):
    def __init__(self, status, **extra):
        super().__init__(status)
        self.status = status
        self.extra = extra


def _result(status, space_id=None, **kw):
    out = {'status': status, 'reason': _REASONS.get(status, ''), 'space_id': space_id, 'roles': {}, 'tracks': False,
           'tracks_reason': None, 'space_json': None, 'secrets': {}, 'space_path': None}
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


def _foreign_dropped(root, others):
    """Так само, як `serve._drop_foreign_roots`: корінь, що перетинається з ІНШИМ простором реєстру, у явних напрямках стає
    `None` (в адаптері ЛІГИ він лишився б). `others` — реєстр без запису ЛІГИ."""
    try:
        _ok, why = spaces.check_new_path(root, others, [])
    except (OSError, ValueError):
        return True
    return why is not None


def _compute_tracks(cfg, path, others):
    """Явні напрямки з адаптера + перевірка паритету → `(список для space.json, нормалізований, дефолт)` чи `None` (паритету нема)."""
    items, default, _fallback = tracks_core.legacy_tracks(cfg)
    raw = [{'id': t['id'], 'label': t['label'], 'root': t['root'], 'repo': t['repo'], 'ds': t['ds']} for t in items]
    norm = tracks_core.normalize(raw, path)
    norm = [{**t, 'root': None} if t['root'] is not None and _foreign_dropped(t['root'], others) else t for t in norm]
    if tracks_core.default_id(norm, default) != default:
        return None
    for a in items:
        n = tracks_core.find(norm, a['id'])
        if (n is None or n['root'] != os.path.normpath(a['root']) or n['repo'] != a['repo'] or n['ds'] != a['ds']
                or n['label'] != tracks_core.label_tag([], {'track': a['id']}, legacy=True)):
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
        if isinstance(t, dict) and tracks_core.of_task(t) not in ids:
            return True
    default = tracks_core.find(norm, 'united')
    return default is None or default['root'] != os.path.normpath(tracks_core.legacy_root(cfg, None))


def _has_userinfo(url):
    """Адреса з `userinfo` (`user:pass@хост`): такий рядок не мігрує — облікові лежали б у `space.json` відкритим текстом."""
    try:
        return '@' in urlsplit(url).netloc
    except ValueError:
        return True


def _role_entries(cfg, present):
    """`{role: (module, ознака_пропуску | None, запис space.json | None, секрети | None)}` за вже прочитаним `cfg`; облікові — ті
    самі функції `install_config`, що в сервері (`supabase_from`/`jira_from`): джерела й порядок не продубльовано."""
    sb_url, sb_key = install_config.supabase_from(cfg)
    base, email, token = install_config.jira_from(cfg)
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
    `comments` → `supabase-comments`: адреса й ключ — `install_config.supabase_from` (ті самі джерела, що `serve._comments_legacy_ctx`);
    кошик — `install_config.LEGACY_SHOTS_BUCKET`. `vcs` → `git-sync`: налаштування ті самі, що в `serve._vcs_legacy_ctx` (тест зіставляє).
    ⛔ `ssh_key`/`host_ip`/`repo` НЕ копіюємо: ключ і IP дає корінь (`_vcs_ssh`), репо — ціль задачі; секретів у `git-sync` нема."""
    sb_url, sb_key = install_config.supabase_from(cfg)
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

    roles = (step.entries or _role_entries)(cfg, set(mods))      # ролі кроку (4d-3a — `_role_entries`; пошук за імʼям на виклик: точка підміни)
    new_mods, secrets = dict(mods), {}
    for role, (mid, skip, entry, secret) in roles.items():
        if skip is None:
            new_mods[mid] = entry
            if secret:                                      # `git-sync` (4d-3b) секретів не має: порожнього запису в secrets.json нема
                secrets[mid] = secret
    out_roles = {r: {'module': m, 'migrate': skip is None, 'reason': skip} for r, (m, skip, _e, _s) in roles.items()}

    do_tracks, tracks_reason, new_tracks = False, None, None
    if not step.tracks:                                     # напрямки мігрує лише 4d-3a
        pass
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

    if not do_tracks and not any(skip is None for (_m, skip, _e, _s) in roles.values()):
        raise _Stop('skip-nothing', space_id=sid, roles=out_roles, tracks_reason=tracks_reason)

    # Перевірка В ПАМʼЯТІ: ядро вирішує кожну мігровану роль саме цим модулем на розрахованому `space.json` (нічого не пишемо).
    explicit = deai_modules._normalize(new_mods)
    space = {'id': sid, 'path': path, 'legacy': True, 'integrations': liga.get('integrations') is True}
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
    if step.tracks:                                         # позначка 4d-3b — без `tracks`
        marks[step.mark]['tracks'] = do_tracks
    space_json['migrations'] = marks
    return _result('ready', space_id=sid, space_path=path, roles=out_roles, tracks=do_tracks, tracks_reason=tracks_reason,
                   space_json=space_json, secrets=secrets)


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
Step = namedtuple('Step', 'mark roles tracks suffix stamp_re entries', defaults=(None,))
STEP_A = Step(MARK, ROLE_MODULES, True, BACKUP_SUFFIX, STAMP_RE)
#: Другий крок (4d-3b, 0.18.0): `comments` і `vcs` ЛІГИ — явні модулі; без напрямків (`tracks=False`), свій бекап і позначка без `tracks`.
STEP_B = Step('liga-4d3b', ROLE_MODULES_B, False, '-liga-4d3b', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3b(?:-[0-9]{1,3})?'), _entries_b)
#: Усі відомі кроки в порядку застосування (відкат — у зворотному: LIFO) і ті, що біжать на старті/в CLI.
ALL_STEPS = (STEP_A, STEP_B)
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
BENIGN = ('done', 'skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-held', 'skip-nothing')
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
           'tracks': bool(p.get('tracks')), 'tracks_reason': p.get('tracks_reason')}
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
    мігрує лише на старті, до відкриття порту)."""
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


def _commit_space(space_path, p, stamp, step=None):
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
        if step.tracks and p['tracks'] and cur.get('tracks') is None:
            new['tracks'], new['default_track'] = planned['tracks'], planned['default_track']
        marks[step.mark] = dict(planned['migrations'][step.mark], at=time.strftime('%Y-%m-%dT%H:%M:%S'), backup=stamp)
        new['migrations'] = marks
        _write_space(sp, new)
    return 'done'


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
            st = _commit_space(space_path, p, stamp, step)
        except (OSError, ValueError, deai_modules.ModuleError):
            info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
            _write_last(info, step)
            return 'abort-write', info
        info = _info(p, status=st, reason=_RUN_REASONS.get(st) or _REASONS.get(st, ''), backup=stamp)
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
    міграції не губляться). `hold=True` дописує `migrations.liga-4d3a.held` — наступний старт не мігрує. Невідоме/підроблене імʼя —
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
    """Бекап (імʼя) першого з ПІЗНІШИХ за `step` кроків, що застосований у `space.json` (`migrations[mark]` є і не `held`), чи `None`.
    Застосований без імені бекапу (позначку хтось дописав руками) — `''`: відмова все одно (імені просто нема). `space.json`,
    що не читається, пізніших кроків не показує (відкат його й так замінює)."""
    try:
        mig = deai_modules._load_space_json(sp).get('migrations')
    except deai_modules.ModuleError:
        return None
    if not isinstance(mig, dict):
        return None
    for s in ALL_STEPS[ALL_STEPS.index(step) + 1:]:
        mark = mig.get(s.mark)
        if mark is not None and not (isinstance(mark, dict) and mark.get('held') is True):
            return (mark.get('backup') if isinstance(mark, dict) else None) or ''
    return None


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
    # Спершу space.json: збій між двома записами лишає простір НЕмігрованим (секрети без запису нешкідливі), а не навпаки.
    with spaces.WRITE_LOCK:
        if 'space.json' in files:
            _atomic_bytes(sp, read('space.json'), files['space.json']['mode'] & 0o777)
        elif os.path.lexists(sp):
            os.remove(sp)
    with spaces.WRITE_LOCK:
        secrets_p = deai_modules._secrets_path()
        cur = deai_modules._load_secrets()
        raw = read('secrets.json') if 'secrets.json' in files else None
        bk = json.loads(raw.decode('utf-8')) if raw is not None else {}
        if not isinstance(bk, dict):
            raise ValueError('secrets backup: not an object')
        cur_rest = {k: v for k, v in cur.items() if k != sid}
        bk_rest = {k: v for k, v in bk.items() if k != sid}
        if raw is not None and cur_rest == bk_rest:
            _atomic_bytes(secrets_p, raw, 0o600)             # чужого не змінилось — побайтно
        else:
            new = dict(cur_rest)                             # лише запис ЛІГИ — з бекапу; чужі секрети лишаються
            if sid in bk:
                new[sid] = bk[sid]
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
    _write_last(info, step)
    return 'restored', info


# ---------------------------------------------------------------------------------------------------------------- статус

def status(home=None):
    """Стан для людини (словник без значень секретів): запис ЛІГИ, позначка, останній звіт, бекапи. Ключі 4d-3a без змін (`mark` —
    позначка кроку 4d-3a), плюс `steps`: `{позначка: {'mark': позначка кроку | None, 'backups': усі бекапи}}` для кожного кроку `STEPS`."""
    out = {'liga': False, 'space_id': None, 'mark': None, 'last': None, 'backups': [], 'error': None, 'steps': {}}
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
                marks[key] = ({k: mark[k] for k in ('at', 'roles', 'tracks', 'backup', 'held') if k in mark}
                              if isinstance(mark, dict) else None)
            out['mark'] = marks.get(_step(None).mark)
        except deai_modules.ModuleError:
            out['error'] = 'skip-space-json-unreadable'
    out['last'] = _read_last() or None
    out['backups'] = _list_backups()
    out['steps'] = {key: {'mark': m, 'backups': list(out['backups'])} for key, m in marks.items()}
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
                lines.append('  позначка: вимкнено вручну (held)')
            else:
                lines.append('  позначка: %s, ролі: %s, напрямки: %s, бекап: %s' % (
                    m.get('at'), ', '.join(m.get('roles') or []) or '-', 'так' if m.get('tracks') else 'ні', m.get('backup')))
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
    return '\n'.join(lines)


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


def startup():
    """Виклик із `serve.main` ДО `make_server`. Ізольований прогін (`implicit.isolated()`) не мігрує, крім шва
    `DC_MIGRATE_LIGA=1` ЛИШЕ з тимчасовим `DEAI_HOME` (справжній `~/.deai` — гучна відмова). Не кидає ніколи: виняток — у stderr
    (імʼя типу, без значень) і в `last.json`. Повертає статус чи `None`. Кроки `STEPS` — по порядку (`run_all`): `abort-*` і `skip-busy`
    зупиняють наступні на цьому старті; `held` раннього кроку теж тримає наступні (їхній `plan` — `skip-held`); решта `skip-*`
    (`skip-nothing`/`skip-done`/…) наступних не блокує. Повертає статус ПЕРШОГО кроку, що не `skip-*` (найважливіше), інакше — першого кроку."""
    done, hints = [], set()
    try:
        if implicit.isolated():
            if os.environ.get('DC_MIGRATE_LIGA') != '1':
                return None
            if _real_home():
                print('liga-4d3a: DC_MIGRATE_LIGA=1 разом зі справжнім DEAI_HOME (~/.deai): відмова, міграцію не запущено', file=sys.stderr)
                return 'refuse-real-home'

        def announce(mark, st, info):
            done.append(st)
            if st != 'skip-layer-off' and not st.startswith('skip-no') and st != 'skip-done':
                print('%s: %s — %s' % (mark, st, info.get('reason') or ''), file=sys.stderr)
                if info.get('hint') and info['hint'] not in hints:           # однакова підказка (тека в git) — раз на старт
                    hints.add(info['hint'])
                    print('  ' + info['hint'], file=sys.stderr)
                # ⛔ Часткова міграція мовчить найгірше: позначку записано, а роль (напр. трекер без облікових у оточенні, коли
                # старт — з Dock/PWA) лишилась неявною й не повториться. Рядок: роль і КОД причини, без значень.
                skipped = info.get('skipped')
                if isinstance(skipped, dict) and skipped:
                    print('  не мігровано: ' + ', '.join('%s (%s)' % (r, c) for r, c in sorted(skipped.items())), file=sys.stderr)
        run_all(None, on_result=announce)
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
