"""Міграція простору ЛІГА в явні `tracks` і модулі (етап 4d-3a, 0.17.0; спека `docs/superpowers/specs/2026-11-05-liga-migration-a-design.md`).

Тут — ЧИСТИЙ розрахунок `plan()` і безпечний для друку `report(plan)`: нічого не пишемо на диск (запис, бекап, позначка, відкат —
наступна задача). Модуль не імпортує `serve` (лише `spaces`, `deai_modules`, `tracks`, `install_config`).

`plan(home=None)` → словник:
    status        'ready' | 'skip-*' | 'abort-*' (коди — `SKIP_CODES`, `ABORT_CODES`). 'skip-nothing' — жодна роль і не напрямки не
                  мігрують: `space_json` = None, позначка НЕ пишеться (наступний старт перевірить знову)
    reason        короткий український опис БЕЗ значень секретів і адрес
    space_id      id запису ЛІГИ в реєстрі або `None`
    roles         {'tracker'|'dashboard'|'notify': {'module': id, 'migrate': bool, 'reason': None | код}}; для skip/abort — `{}`
    tracks        bool: чи мігрують напрямки; `tracks_reason` — код, коли ні: `tracks-present`, `tracks-parity` (розраховане не
                  збігається з адаптером), `tracks-unknown-values`. Роль від цього не залежить: ролі мігрують далі
    space_json    НОВИЙ вміст `space.json` (повний, з наявним злитим) або `None`; позначка `migrations['liga-4d3a']` тут має лише
                  `roles` і `tracks` — `at` і `backup` дописує запис (Task 5)
    secrets       {module_id: {ключ: "<значення>"}} — ⛔ значення секретів потрібні ЗАПИСУ; назовні (журнал, звіт) — лише `report()`

⛔ Секрети живуть лише в `plan['secrets']`. `report()` друкує імена ключів, не значення; `plan` не друкувати цілком.
"""
import os

import deai_modules
import install_config
import spaces
import tracks as tracks_core

MARK = 'liga-4d3a'
#: Роль → вбудований модуль, у порядку запису.
ROLE_MODULES = (('tracker', 'jira-tracker'), ('dashboard', 'supabase-dashboard'), ('notify', 'supabase-teams'))
DASHBOARD_TABLE = 'overview_projects'
COMPAT = 'comment-layer'
SKIP_CODES = ('skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-held', 'skip-no-path', 'skip-path-in-git',
              'skip-space-json-unreadable', 'skip-registry-unreadable', 'skip-tasks-unreadable', 'skip-nothing')
ABORT_CODES = ('abort-provider', 'abort-internal')
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
    'abort-provider': 'ядро не вирішує мігровану роль на розрахованому space.json: міграція нічого не пише',
    'abort-internal': 'непередбачена помилка розрахунку: міграція нічого не пише',
}


class _Stop(Exception):
    def __init__(self, status, **extra):
        super().__init__(status)
        self.status = status
        self.extra = extra


def _result(status, space_id=None, **kw):
    out = {'status': status, 'reason': _REASONS.get(status, ''), 'space_id': space_id, 'roles': {}, 'tracks': False,
           'tracks_reason': None, 'space_json': None, 'secrets': {}}
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
    out = {}
    for role, mid in ROLE_MODULES:
        have, why, settings, secret = spec[role]
        if mid in present:
            out[role] = (mid, 'module-present', None, None)
        elif not have:
            out[role] = (mid, why, None, None)
        else:
            out[role] = (mid, None, {'enabled': True, 'shared_state': True, 'settings': settings}, secret)
    return out


def plan(home=None):
    """Чистий розрахунок міграції ЛІГИ; див. докстрінг модуля. Нічого не пише; не кидає (збій — `abort-internal`)."""
    try:
        return _plan(home)
    except _Stop as s:
        return _result(s.status, **s.extra)
    except Exception:  # noqa: BLE001 — розрахунок не валить старт: код замість винятку (без тексту винятку: там можуть бути значення)
        return _result('abort-internal')


def _plan(home):
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
    mark = mig.get(MARK) if isinstance(mig, dict) else None
    if mark is not None:
        raise _Stop('skip-held' if isinstance(mark, dict) and mark.get('held') is True else 'skip-done', space_id=sid)
    if _in_git(path):
        raise _Stop('skip-path-in-git', space_id=sid)
    try:
        cfg = install_config.load_legacy_tasks()
    except (OSError, ValueError, RecursionError):
        raise _Stop('skip-tasks-unreadable', space_id=sid) from None
    if not isinstance(cfg, dict):
        raise _Stop('skip-tasks-unreadable', space_id=sid)

    roles = _role_entries(cfg, set(mods))
    new_mods, secrets = dict(mods), {}
    for role, (mid, skip, entry, secret) in roles.items():
        if skip is None:
            new_mods[mid] = entry
            secrets[mid] = secret
    out_roles = {r: {'module': m, 'migrate': skip is None, 'reason': skip} for r, (m, skip, _e, _s) in roles.items()}

    do_tracks, tracks_reason, new_tracks = False, None, None
    if data.get('tracks'):
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
    marks[MARK] = {'roles': [r for r, (_m, skip, _e, _s) in roles.items() if skip is None], 'tracks': do_tracks}
    space_json['migrations'] = marks
    return _result('ready', space_id=sid, roles=out_roles, tracks=do_tracks, tracks_reason=tracks_reason,
                   space_json=space_json, secrets=secrets)


def report(p):
    """Текст для людини й журналу: статус, код, ролі, напрямки, ІМЕНА секретних ключів. ⛔ Жодних значень секретів чи адрес."""
    lines = ['liga-4d3a: ' + str(p.get('status')), '  ' + str(p.get('reason') or '')]
    if p.get('space_id'):
        lines.append('  space: ' + str(p['space_id']))
    for role, r in (p.get('roles') or {}).items():
        lines.append('  %s (%s): %s' % (role, r['module'], 'migrate' if r['migrate'] else 'skip: ' + str(r['reason'])))
    if p.get('status') == 'ready':
        lines.append('  tracks: ' + ('migrate' if p.get('tracks') else 'skip: ' + str(p.get('tracks_reason'))))
        for mid, sec in (p.get('secrets') or {}).items():
            lines.append('  secrets %s: %s' % (mid, ', '.join(sorted(sec)) or '-'))
    return '\n'.join(lines)
