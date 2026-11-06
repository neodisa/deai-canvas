"""Міграція простору ЛІГА в явні `tracks` і модулі (етап 4d-3a, 0.17.0; спека `docs/superpowers/specs/2026-11-05-liga-migration-a-design.md`).

Тут — ЧИСТИЙ розрахунок `plan()` і безпечний для друку `report(plan)`: `plan()` нічого не пише на диск. Запис (`run`), відкат
(`restore`), `status` і старт сервера (`startup`) — нижче, після `report()`. Модуль не імпортує `serve` (лише `spaces`,
`deai_modules`, `tracks`, `install_config`, `implicit`).

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
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time

import deai_modules
import implicit
import install_config
import spaces
import tracks as tracks_core
from atomic_io import TMP_SUFFIX, atomic_write_json

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


# ================================================================================================ запис, відкат, старт (Task 5)
#
# ⛔ Замки: `spaces.WRITE_LOCK` — звичайний `Lock`, не вкладений. Його тримаємо ЛИШЕ на один запис (`write_secrets` бере його сам,
# `_commit_space`/`_restore_file`/`_write_last` — окремо). Під ним НІКОЛИ не кличемо `plan()`, `load_registry`, `catalog`, `provider`.

BACKUP_SUFFIX = '-liga-4d3a'
#: Строгий вигляд імені бекапу (`<YYYYMMDD-HHMMSS>-liga-4d3a[-N]`): жодних шляхів, крапок і розділювачів.
STAMP_RE = re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3a(?:-[0-9]{1,3})?')
BACKUP_FILES = ('tasks.json', 'space.json', 'secrets.json', 'spaces.json')
#: Статуси, після яких CLI не вважає запуск помилкою (нічого не зламано; «done» — міграцію виконано).
BENIGN = ('done', 'skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-held', 'skip-nothing')
_RUN_REASONS = {
    'done': 'міграцію виконано',
    'abort-backup': 'бекап не створено: міграція нічого не записала',
    'abort-secrets': 'секрети не записано: space.json не змінено, наступний запуск почне заново',
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


def _info(p, **extra):
    """Безпечний підсумок для `last.json` і друку: коди, імена ролей, без значень секретів і адрес."""
    out = {'status': p.get('status'), 'reason': p.get('reason') or '', 'space_id': p.get('space_id'),
           'roles': [r for r, v in (p.get('roles') or {}).items() if v.get('migrate')],
           'skipped': {r: v.get('reason') for r, v in (p.get('roles') or {}).items() if not v.get('migrate')},
           'tracks': bool(p.get('tracks')), 'tracks_reason': p.get('tracks_reason')}
    out.update(extra)
    return out


def _write_last(info):
    """`<DEAI_HOME>/migrations/last.json` — журнал останньої дії (без значень секретів). Найкращі зусилля: не кидає."""
    try:
        d = os.path.join(spaces.home(), 'migrations')
        with spaces.WRITE_LOCK:
            os.makedirs(d, mode=0o700, exist_ok=True)
            atomic_write_json(os.path.join(d, 'last.json'), dict(info, at=time.strftime('%Y-%m-%dT%H:%M:%S')))
        return True
    except (OSError, ValueError):
        return False


def _liga_entry(home):
    reg = _registry(home)
    liga = next((s for s in reg['spaces'] if s.get('legacy') is True), None)
    if liga is None:
        raise _Stop('skip-no-liga')
    return liga


def _backup(base, space_id, space_path):
    """Датований бекап; повертає імʼя теки. Збій — виняток (викликач робить `abort-backup`); недописану теку прибираємо.
    Усі файли бекапу 0600, тека 0700: у `tasks.json` лежать облікові."""
    root = os.path.join(base, 'backups')
    os.makedirs(root, mode=0o700, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S') + BACKUP_SUFFIX
    name, n = stamp, 1
    while True:
        try:
            os.mkdir(os.path.join(root, name), 0o700)
            break
        except FileExistsError:
            n += 1
            name = '%s-%d' % (stamp, n)
    d = os.path.join(root, name)
    try:
        os.chmod(d, 0o700)
        sources = {'tasks.json': install_config.legacy_tasks_path(), 'space.json': os.path.join(space_path, 'space.json'),
                   'secrets.json': deai_modules._secrets_path(), 'spaces.json': spaces.registry_path()}
        files = {}
        for fname, src in sources.items():
            if not os.path.isfile(src):
                continue
            dst = os.path.join(d, fname)
            shutil.copyfile(src, dst)
            os.chmod(dst, 0o600)
            files[fname] = {'source': src, 'sha256': _sha256(dst), 'mode': os.stat(src).st_mode & 0o777}
        manifest = {'tool': 'deai-canvas', 'version': _tool_version(), 'migration': MARK, 'space_id': space_id,
                    'space_path': space_path, 'files': files}
        mp = os.path.join(d, 'manifest.json')
        with open(mp, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.chmod(mp, 0o600)
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return name


def _commit_space(space_path, p, stamp):
    """ОДИН атомарний запис `space.json`: злиття з ПОТОЧНИМ вмістом диска (перечитуємо під замком, відразу перед записом): чужі
    ключі й правки, зроблені після `plan()`, не губляться. Модуль, що зʼявився тим часом, не перезаписуємо. Позначка вже є — `skip-done`."""
    sp = os.path.join(space_path, 'space.json')
    with spaces.WRITE_LOCK:
        cur = deai_modules._load_space_json(sp)
        mods = dict(deai_modules._raw_modules(cur))
        marks = cur.get('migrations')
        marks = dict(marks) if isinstance(marks, dict) else {}
        if MARK in marks:
            return 'skip-done'
        planned = p['space_json']
        for role, r in p['roles'].items():
            if r['migrate'] and r['module'] not in mods:
                mods[r['module']] = planned['modules'][r['module']]
        new = dict(cur)
        new['modules'] = mods
        if p['tracks'] and not cur.get('tracks'):
            new['tracks'], new['default_track'] = planned['tracks'], planned['default_track']
        marks[MARK] = dict(planned['migrations'][MARK], at=time.strftime('%Y-%m-%dT%H:%M:%S'), backup=stamp)
        new['migrations'] = marks
        _write_space(sp, new)
    return 'done'


def _run(home):
    """`(статус, підсумок)`; кожен виняток — код, без тексту винятку (там можуть бути значення)."""
    if home and os.path.realpath(os.path.expanduser(home)) != os.path.realpath(spaces.home()):
        return 'abort-internal', {'status': 'abort-internal', 'reason': 'home не збігається з DEAI_HOME: запис пішов би в іншу теку'}
    p = plan(home)
    st = p['status']
    if st != 'ready':
        info = _info(p)
        if st.startswith('abort-'):
            _write_last(info)                                # лише журнал: стан не чіпаємо; skip-* журнал не затирає
        return st, info
    try:
        liga = _liga_entry(home)
        try:
            stamp = _backup(spaces.home(), p['space_id'], liga['path'])
        except (OSError, ValueError):
            info = _info(p, status='abort-backup', reason=_RUN_REASONS['abort-backup'])
            _write_last(info)
            return 'abort-backup', info
        try:
            for mid, patch in p['secrets'].items():
                deai_modules.write_secrets(p['space_id'], mid, patch)
        except deai_modules.ModuleError as e:
            info = _info(p, status='abort-secrets', reason=_RUN_REASONS['abort-secrets'], backup=stamp, error=getattr(e, 'code', 'secrets'))
            _write_last(info)
            return 'abort-secrets', info
        try:
            st = _commit_space(liga['path'], p, stamp)
        except (OSError, ValueError, deai_modules.ModuleError):
            info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
            _write_last(info)
            return 'abort-write', info
        info = _info(p, status=st, reason=_RUN_REASONS.get(st) or _REASONS.get(st, ''), backup=stamp)
        if st == 'done':
            info['secrets'] = {m: sorted(s) for m, s in p['secrets'].items()}      # лише імена ключів
            _write_last(info)
        return st, info
    except _Stop as s:
        return s.status, {'status': s.status, 'reason': _REASONS.get(s.status, '')}
    except Exception as e:  # noqa: BLE001
        info = _info(p, status='abort-internal', reason=_REASONS['abort-internal'], error=type(e).__name__)
        _write_last(info)
        return 'abort-internal', info


def run(home=None):
    """Міграція ЛІГИ: `plan()` → бекап → секрети → ОДИН запис `space.json` (з позначкою) → `last.json`. Повертає статус
    (`done`, `skip-*`, `abort-*`); будь-що, крім `ready` у `plan()`, нічого не пише (лише `abort-*` лишають рядок у `last.json`).
    Збій між секретами й `space.json` лишає нешкідливі секрети без позначки: наступний запуск починає з нуля."""
    return _run(home)[0]


# ---------------------------------------------------------------------------------------------------------------- відкат

def _backup_dir(stamp):
    """Тека бекапу за ЗАВАЖНО строгим імʼям; не символічне посилання, лежить прямо в `<DEAI_HOME>/backups`."""
    if not isinstance(stamp, str) or not STAMP_RE.fullmatch(stamp):
        return None
    root = os.path.join(spaces.home(), 'backups')
    d = os.path.join(root, stamp)
    if os.path.islink(d) or not os.path.isdir(d) or os.path.dirname(os.path.realpath(d)) != os.path.realpath(root):
        return None
    return d


def _load_manifest(d):
    """Маніфест бекапу, перевірений на форму й sha256 КОЖНОГО файла; будь-яка розбіжність — `None` (нічого не відновлюємо)."""
    try:
        with open(os.path.join(d, 'manifest.json'), encoding='utf-8') as f:
            m = json.load(f)
        files = m['files']
        if m.get('migration') != MARK or not isinstance(files, dict) or not isinstance(m.get('space_id'), str):
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
    """Відкат: `space.json` ЛІГИ і `secrets.json` повертаються побайтно з бекапу (sha256 з маніфесту звіряється ДО будь-якого
    запису). Бекап без `space.json` — мігрований `space.json` прибираємо. Старий `tasks.json` і `spaces.json` не чіпаємо.
    `hold=True` дописує `migrations.liga-4d3a.held` — наступний старт не мігрує. Невідоме/підроблене імʼя — відмова
    (`refuse-stamp`/`refuse-tampered`/`refuse-no-liga`), нічого не пишемо. Повертає статус (`restored` чи відмова/`abort-restore`)."""
    try:
        if home and os.path.realpath(os.path.expanduser(home)) != os.path.realpath(spaces.home()):
            return 'abort-internal'
        d = _backup_dir(stamp)
        if d is None:
            return 'refuse-stamp'
        m = _load_manifest(d)
        if m is None:
            return 'refuse-tampered'
        try:
            liga = _liga_entry(home)
        except _Stop:
            return 'refuse-no-liga'
        if liga['id'] != m['space_id']:
            return 'refuse-no-liga'
        files = m['files']
        sp = os.path.join(liga['path'], 'space.json')

        def read(fname):
            with open(os.path.join(d, fname), 'rb') as f:
                return f.read()
        # Спершу space.json: збій між двома записами лишає простір НЕмігрованим (секрети без запису нешкідливі), а не навпаки.
        with spaces.WRITE_LOCK:
            if 'space.json' in files:
                _atomic_bytes(sp, read('space.json'), files['space.json']['mode'] & 0o777)
            elif os.path.lexists(sp):
                os.remove(sp)
        with spaces.WRITE_LOCK:
            secrets_p = deai_modules._secrets_path()
            if 'secrets.json' in files:
                _atomic_bytes(secrets_p, read('secrets.json'), 0o600)
            elif os.path.lexists(secrets_p):                 # бекап без секретів: знімаємо лише записане для ЛІГИ, чужі лишаємо
                cur = deai_modules._load_secrets()
                cur.pop(m['space_id'], None)
                if cur:
                    atomic_write_json(secrets_p, cur)
                    os.chmod(secrets_p, 0o600)
                else:
                    os.remove(secrets_p)
        if hold:
            with spaces.WRITE_LOCK:
                cur = deai_modules._load_space_json(sp)
                marks = cur.get('migrations')
                marks = dict(marks) if isinstance(marks, dict) else {}
                marks[MARK] = {'held': True}
                new = dict(cur)
                new['migrations'] = marks
                _write_space(sp, new)
        _write_last({'status': 'restored', 'reason': 'простір ЛІГА повернено з бекапу', 'space_id': m['space_id'], 'backup': stamp,
                     'held': bool(hold)})
        return 'restored'
    except Exception:  # noqa: BLE001 — без тексту винятку
        return 'abort-restore'


# ---------------------------------------------------------------------------------------------------------------- статус

def status(home=None):
    """Стан для людини (словник без значень секретів): запис ЛІГИ, позначка, останній звіт, бекапи."""
    out = {'liga': False, 'space_id': None, 'mark': None, 'last': None, 'backups': [], 'error': None}
    try:
        liga = _liga_entry(home)
    except _Stop as s:
        out['error'] = s.status
        liga = None
    if liga:
        out['liga'], out['space_id'] = True, liga['id']
        try:
            data = deai_modules._load_space_json(os.path.join(liga['path'], 'space.json'))
            mig = data.get('migrations')
            mark = mig.get(MARK) if isinstance(mig, dict) else None
            out['mark'] = {k: mark[k] for k in ('at', 'roles', 'tracks', 'backup', 'held') if k in mark} if isinstance(mark, dict) else None
        except deai_modules.ModuleError:
            out['error'] = 'skip-space-json-unreadable'
    try:
        with open(os.path.join(spaces.home(), 'migrations', 'last.json'), encoding='utf-8') as f:
            last = json.load(f)
        out['last'] = last if isinstance(last, dict) else None
    except (OSError, ValueError):
        pass
    try:
        out['backups'] = sorted(n for n in os.listdir(os.path.join(spaces.home(), 'backups')) if STAMP_RE.fullmatch(n))
    except OSError:
        pass
    return out


def status_text(st):
    """Український текст `status()`. ⛔ Без значень секретів."""
    lines = ['Міграція ЛІГИ (liga-4d3a)']
    if not st['liga']:
        lines.append('  простору ЛІГА в реєстрі нема' + (' (%s)' % st['error'] if st.get('error') else ''))
    else:
        lines.append('  простір: ' + str(st['space_id']))
        m = st['mark']
        if m is None:
            lines.append('  позначки нема: міграція ще не виконана (або відкочена)')
        elif m.get('held'):
            lines.append('  позначка: вимкнено вручну (held)')
        else:
            lines.append('  позначка: %s, ролі: %s, напрямки: %s, бекап: %s' % (
                m.get('at'), ', '.join(m.get('roles') or []) or '-', 'так' if m.get('tracks') else 'ні', m.get('backup')))
    last = st.get('last')
    if last:
        lines.append('  останній звіт: %s (%s)' % (last.get('status'), last.get('at')))
    lines.append('  бекапи: ' + (', '.join(st['backups']) or 'нема'))
    return '\n'.join(lines)


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
    (імʼя типу, без значень) і в `last.json`. Повертає статус чи `None`."""
    try:
        if implicit.isolated():
            if os.environ.get('DC_MIGRATE_LIGA') != '1':
                return None
            if _real_home():
                print('liga-4d3a: DC_MIGRATE_LIGA=1 разом зі справжнім DEAI_HOME (~/.deai): відмова, міграцію не запущено', file=sys.stderr)
                return 'refuse-real-home'
        st, info = _run(None)
        if st != 'skip-layer-off' and not st.startswith('skip-no') and st != 'skip-done':
            print('liga-4d3a: %s — %s' % (st, info.get('reason') or ''), file=sys.stderr)
        return st
    except Exception as e:  # noqa: BLE001
        try:
            print('liga-4d3a: abort-internal — %s' % type(e).__name__, file=sys.stderr)
            _write_last({'status': 'abort-internal', 'reason': _REASONS['abort-internal'], 'error': type(e).__name__})
        except Exception:  # noqa: BLE001
            pass
        return 'abort-internal'
