#!/usr/bin/env python3
"""Реестр задач: design-office (ветка `registry`) — единственный источник истины.

Локальный tasks.json — кеш. Переносимые поля (title/jira/profile/gitlab/…) приходят
из реестра; машинное (dir/live/current) остаётся локальным и наверх не уезжает.

    registry.py status          вік кешу + чи реєстр поїхав уперед + розбіжності
    registry.py pull            підтягнути реєстр у локальний tasks.json
    registry.py push [id|--all] віддати задачу(і) в реєстр

Свежесть проверяется по времени: кеш старше TTL (DC_REGISTRY_TTL_H, дефолт 6 ч)
или сдвинувшийся origin/registry → status/pull зовут обновиться.
"""
import argparse
import calendar
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#      DC_TASKS_FILE — той самий перевизначувач, що в serve.tasks_path(): інакше
# реєстр і сервер читали б РІЗНІ файли, а тест, який думає, що ізолювався,
# мовчки правив би живий конфіг (03.08.2026 саме так фікстура поїхала в прод).
TASKS_PATH = os.environ.get('DC_TASKS_FILE') or os.path.join(ROOT, 'tasks.json')
REPO = 'git@gitlab.internal.example:ORG/design-office.git'
BRANCH = 'registry'
TTL_H = float(os.environ.get('DC_REGISTRY_TTL_H') or 6)

# Переносимые поля — то, что имеет смысл на любой машине.
#      `vercel_scope` — разом із `vercel_project`: імʼя саме по собі URL не
# тримає, бо в ЧУЖОМУ акаунті `vercel link` із тим самим імʼям створює ІНШИЙ
# проєкт (і друге посилання). Пара імʼя+скоуп — це і є прив'язка задача→превʼю.
#      `track` — напрямок задачі; `profile` лишається поряд: старі колеги (0.14.0) читають зі спільного реєстру саме його
# (без нього їхня тека, репо й мітка зламались би). Нові машини читають `track`, а запис лише з `profile` береться через межу
# `_track_of_entry`; `push` нової машини дописує `track` у записи реєстру.
SHARED = ('title', 'jira', 'profile', 'track', 'gitlab', 'comment_project', 'vercel_project',
          'vercel_scope', 'figma', 'owner', 'owner_key', 'tags')
# Машинное — живёт только локально, в реестр не уезжает.
LOCAL_ONLY = ('dir', 'live')


# ---------- gitlab: спільне — ЯКИЙ проєкт, машинне — ЯК до нього достукатись ----------
#
# ⛔ fb-29092026-d64d35 (boss-interface). `gitlab` їздив у реєстр ЦІЛКОМ, разом
# із формою адреси, якою до проєкту стукається саме ця машина. 25.08.2026 звідси
# поїхало `git@10.0.0.7:…` (ручний обхід split-DNS, ще до повтору по IP у
# `serve._git`), 21.09 колега перезаписав на `https://…`. Реєстр головніший, тож
# `pull` розносив обидві форми всім, а SSH-ключ налаштований на ІМʼЯ хоста:
# fetch/push на IP падали, і ітерації 8–14 жили лише на Vercel. `status` при
# цьому радив зробити той самий шкідливий `pull`.
#
# Тепер: у реєстр іде канонічна адреса (SSH на імʼя хоста — та сама форма, що
# `serve.profile_repos()`), без `ssh_key`/`host_ip`; з реєстру береться ЯКИЙ
# проєкт і шлях, а локальна форма адреси того самого проєкту лишається.
CANON_HOST = REPO.split('@', 1)[1].split(':', 1)[0]          # gitlab.internal.example
GITLAB_MACHINE_KEYS = ('ssh_key', 'host_ip')
_SCP = re.compile(r'^[^@/\s]+@([^:/\s]+):(.+)$')                 # git@host:path
_URL = re.compile(r'^(?:ssh|https?)://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$', re.I)
_IPV4 = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')


def _repo_parts(url):
    """(хост, шлях без .git) або None — для локальних шляхів і невідомих форм.

    ⚠️ IP-літерал вважаємо НАШИМ GitLab: інших у команди немає, а IP в адресі
    зʼявляється рівно як обхід split-DNS (fb-30072026-46c4de). Інакше IP-форма
    лишалась би «іншим проєктом» і ніколи б не нормалізувалась.
    """
    m = _SCP.match(url or '') or _URL.match(url or '')
    if not m:
        return None
    host = m.group(1).lower()
    if _IPV4.match(host):
        host = CANON_HOST
    path = m.group(2).strip('/')
    if path.endswith('.git'):
        path = path[:-4]
    return host, path


def canonical_repo(url):
    """Адреса проєкту на НАШОМУ GitLab → `git@<хост>:<шлях>.git`. Чуже й локальне — як є."""
    parts = _repo_parts(url)
    if not parts or parts[0] != CANON_HOST:
        return url
    return f'git@{CANON_HOST}:{parts[1]}.git'


def same_project(a, b):
    """Той самий проєкт, хоч би якою формою адреси (IP / HTTPS / SSH)."""
    pa, pb = _repo_parts(a), _repo_parts(b)
    if pa is None or pb is None:
        return a == b
    return (pa[0], pa[1].lower()) == (pb[0], pb[1].lower())


def shared_gitlab(gl):
    """Що з `gitlab` задачі їде в реєстр: канонічна адреса, без машинних ключів."""
    out = {k: v for k, v in gl.items() if k not in GITLAB_MACHINE_KEYS}
    if out.get('repo'):
        out['repo'] = canonical_repo(out['repo'])
    return out


def merged_gitlab(local, reg):
    """`gitlab` після pull: реєстр каже ЯКИЙ проєкт і шлях, машина — як стукатись."""
    local = local if isinstance(local, dict) else {}
    # Машинні ключі з реєстру НЕ беремо взагалі — навіть там, де своїх немає:
    # чужий `ssh_key` дав би `ssh -i <чужий шлях> -o IdentitiesOnly=yes`, тобто
    # той самий збій, що й IP у boss-interface. Такі ключі лежать хіба в записах,
    # відданих до 1.42.0 (ревʼю 29.09.2026).
    out = {**local, **{k: v for k, v in reg.items() if k not in GITLAB_MACHINE_KEYS}}
    if reg.get('repo'):
        mine = local.get('repo')
        out['repo'] = mine if mine and same_project(mine, reg['repo']) \
            else canonical_repo(reg['repo'])
    return out


# ---------- превʼю спільної задачі — у ВЛАСНИКА ----------
#
# ⛔ fb-29092026-69e9c7 + fb-29092026-210ec1 (рішення власника 29.09.2026). Пара
# `vercel_project`+`vercel_scope` їхала реєстром як спільна правда: колега віддав
# boss-interface зі СВОЇМ проєктом у своїй команді, і перший `pull` власника
# перемкнув би його публікацію туди. Друга машина з тим самим імʼям без скоупа
# отримує `pv-XXXX-<суфікс>.vercel.app`, і кожна публікація заміняє деплой ЦІЛКОМ —
# ітерації з іншої машини зникали. Тепер: у реєстрі — прив'язка ВЛАСНИКА задачі
# (`owner_key`), змінити її може лише його машина; у решти вона машинна —
# публікують у своє превʼю, і канвас каже, що це не посилання задачі.
VERCEL_KEYS = ('vercel_project', 'vercel_scope')


def _is_owner(owner_key):
    """Чи ЦЯ машина — власник. Без власника або без особи — так (як було досі)."""
    me = _identity()[1]
    return not owner_key or not me or owner_key == me


def _pulled_value(local_task, key, reg_value, reg_entry=None):
    """Значення поля, яке ЗАЛИШИТЬ pull (None — поле не чіпати).

    `gitlab` — злите (`merged_gitlab`). Пара Vercel — власника: не-власник свою
    лишає й чужої не бере; власник бере з реєстру лише коли своєї немає (друга
    машина) — пара цілком, бо скоуп одного проєкту до імені іншого не пасує.
    """
    if key == 'gitlab' and isinstance(reg_value, dict):
        return merged_gitlab(local_task.get('gitlab'), reg_value)
    if key in VERCEL_KEYS:
        owner_key = (reg_entry or {}).get('owner_key') or local_task.get('owner_key')
        if not _is_owner(owner_key) or local_task.get('vercel_project'):
            return local_task.get(key)
    return reg_value


def clone_dir():
    return os.environ.get('DC_REGISTRY_DIR') or os.path.join(ROOT, '.mirrors', 'design-office-registry')


# ---------- Фікстура тесту не сміє стати спільним станом ----------
#
# ⛔ ІНЦИДЕНТ 15.09.2026 (розібрано 27.09.2026). `tests/test_gitlab_sync.py`
# без `DC_TASKS_FILE` записав фікстуру поверх живого `tasks.json`, і задача
# `nova` з `gitlab.repo = /var/folders/…/T/dc-syncverify-…/origin.git` поїхала
# в СПІЛЬНИЙ реєстр (7 комітів `registry: nova` у гілці `registry`), а звідти —
# на командний дашборд карткою «Нова» зі статусом `pub`. Код тесту полагоджено
# (3fc8e65), але бар'єр «підмінений конфіг = заборона писати у спільний стан»
# (`DC_TASKS_FILE`) тут би й не спрацював: конфіг НЕ був підмінений — був
# зіпсований живий. Захід, що стоїть у кожному тесті окремо, тримає рівно до
# наступного тесту, який про нього забуде. Тому він стоїть на тому кроці, що
# створює ризик: на самому пуші (і на pull/дашборді — дзеркально), і питає не
# «хто мене кличе», а «куди вказує ця задача».

# Системні тимчасові корені. `/var/folders` — macOS (`$TMPDIR` живе там),
# `/private/…` — те саме після realpath (`/tmp` і `/var` на macOS — симлінки).
_TEMP_ROOTS = ('/tmp', '/private/tmp', '/var/folders', '/private/var/folders')


def _temp_roots():
    """Тимчасові корені цієї машини — нормалізовані й після realpath.

    `tempfile.gettempdir()` додаємо, бо `$TMPDIR` у CI чи на чужій машині буває
    де завгодно. Але не беремо його, якщо він `/` або містить домашню теку:
    `TMPDIR=$HOME` зробив би «фікстурою» кожну справжню задачу, і реєстр
    мовчки перестав би приймати будь-що.
    """
    roots = list(_TEMP_ROOTS)
    try:
        t = tempfile.gettempdir()
    except Exception:  # noqa: BLE001 — нема tmp: лишаємо зашиті корені
        t = None
    if t:
        home = os.path.realpath(os.path.expanduser('~'))
        rt = os.path.realpath(t)
        if rt != os.sep and not _under(home, rt):
            roots.append(t)
    out = []
    for r in roots:
        for form in (os.path.normpath(r), os.path.realpath(r)):
            if form not in out:
                out.append(form)
    return out


def _under(path, root):
    """Чи лежить `path` у `root` — по МЕЖІ компонента, не підрядком.

    Підрядок дав би `/tmpfoo/x` ⊂ `/tmp` і `/var/folders-archive` ⊂
    `/var/folders` — тобто відмову пушити справжню задачу.
    """
    root = root.rstrip(os.sep) or os.sep
    return path == root or path.startswith(root if root == os.sep else root + os.sep)


def _local_path(value):
    """Локальний абсолютний шлях із `dir` / `gitlab.repo`, або None.

    `git@host:group/repo.git`, `https://…`, `ssh://…` — віддалені адреси, у
    них немає що перевіряти. `file:///…` і `~/…` — локальні.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if v.startswith('file://'):
        v = unquote(urlparse(v).path)
    v = os.path.expanduser(v)
    return v if os.path.isabs(v) else None


def fixture_path_reason(task):
    """Причина (рядок), якщо задача вказує в тимчасову теку, інакше None.

    ОДНЕ джерело правди для всіх, хто віддає задачу в спільний стан: пуш у
    реєстр, pull у кеш, синк дашборда, доктор. Дивимось на `dir` (машинне поле
    локальної задачі) і `gitlab.repo` (їде в реєстр — саме ним `nova` і
    протекла). Справжня робота дизайнера в `/tmp` чи `/var/folders` не живе:
    звідти її стирає сама система.
    """
    if not isinstance(task, dict):
        return None
    gl = task.get('gitlab')
    fields = [('dir', task.get('dir')),
              ('gitlab.repo', gl.get('repo') if isinstance(gl, dict) else None)]
    roots = _temp_roots()
    for field, value in fields:
        p = _local_path(value)
        if not p:
            continue
        for form in (os.path.normpath(p), os.path.realpath(p)):
            for root in roots:
                if _under(form, root):
                    return (f'{field} = {value} лежить у тимчасовій теці {root} — '
                            f'це фікстура тесту, а не робота дизайнера')
    return None


def _ssh_key(cfg):
    key = cfg.get('gitlab_ssh_key') or '~/.ssh/gitlab_ed25519'
    return os.path.expanduser(key)


def _git(args, cwd, cfg, check=True, timeout=120):
    env = dict(os.environ,
               GIT_SSH_COMMAND=f'ssh -i {_ssh_key(cfg)} -o StrictHostKeyChecking=no')
    r = subprocess.run(['git', *args], cwd=cwd, env=env, text=True,
                       capture_output=True, timeout=timeout)
    if check and r.returncode != 0:
        raise OSError(f"git {' '.join(args)} → {(r.stderr or r.stdout)[-400:]}")
    return r


def load_tasks():
    with open(TASKS_PATH, encoding='utf-8') as f:
        return json.load(f)


def save_tasks(cfg):
    tmp = TASKS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, TASKS_PATH)


def _save_registry_state(task_updates, registry):
    """Записати підсумок синхронізації, НЕ затираючи паралельних правок.

    ⛔ НАВІЩО. `cmd_pull`/`push_tasks` читають `tasks.json` на початку, далі
    роблять мережеву роботу (clone/reset/push — секунди), і наприкінці клали на
    місце СВІЙ знімок конфіга. Усе, що змінилось за цей час, зникало мовчки —
    зокрема `current`, тобто щойно зроблене перемикання задачі відкочувалось.
    Симптом при цьому вказує не туди: `/api/iteration-pages` віддає порожньо,
    `/it-assets/<it>/…` дає 404, і виглядає як зламана ітерація.

    Тому пишемо ТОЧКОВО: перечитуємо файл і накладаємо лише ті поля, які
    синхронізація справді визначає (перенесені з реєстру + `registry`). Усе
    інше — `current`, задача, заведена паралельно, машинні поля — лишається
    таким, яким його лишив той, хто писав останнім.
    """
    fresh = load_tasks()
    tasks = fresh.setdefault('tasks', {})
    for tid, fields in task_updates.items():
        tasks.setdefault(tid, {}).update(fields)
    fresh['registry'] = registry
    save_tasks(fresh)


def ensure_clone(cfg, fetch=True):
    """Локальный клон ветки registry. Бросает OSError, если недоступно (нет VPN)."""
    d = clone_dir()
    if not os.path.isdir(os.path.join(d, '.git')):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        _git(['clone', '--quiet', '--branch', BRANCH, '--single-branch', REPO, d],
             os.path.dirname(d), cfg, timeout=180)
    elif fetch:
        _git(['fetch', '--quiet', 'origin', BRANCH], d, cfg)
    return d


def remote_head(cfg):
    """SHA головы origin/registry без клона. None, если недоступно."""
    try:
        r = _git(['ls-remote', REPO, f'refs/heads/{BRANCH}'], ROOT, cfg, timeout=30)
    except Exception:  # noqa: BLE001 — нет сети/VPN/ключа: трактуем как offline
        return None
    line = (r.stdout or '').split('\n')[0].strip()
    return line.split('\t')[0] if line else None


def read_registry(d):
    """{id: entry} из registry/tasks/*.json рабочей копии."""
    tdir = os.path.join(d, 'registry', 'tasks')
    out = {}
    if not os.path.isdir(tdir):
        return out
    for name in sorted(os.listdir(tdir)):
        if not name.endswith('.json'):
            continue
        with open(os.path.join(tdir, name), encoding='utf-8') as f:
            e = json.load(f)
        tid = e.get('id') or name[:-5]
        out[tid] = e
    return out


def _identity():
    """Кто работает на этой машине — из git config. Нужно, чтобы в общем списке
    было видно, кто задачу завёл (то же, чем overview подписывает карточки)."""
    # Ті самі перекривачі, що в `serve.machine_identity`: інакше машина без
    # git-конфіга для сервера «не-власник», а для реєстру «власник» (ревʼю 29.09).
    env_name, env_key = os.environ.get('DC_IDENTITY_NAME'), os.environ.get('DC_IDENTITY_EMAIL')
    if env_name is not None or env_key is not None:
        return (env_name or '').strip() or None, (env_key or '').strip() or None

    def cfg(key):
        try:
            r = subprocess.run(['git', 'config', '--get', key], text=True,
                               capture_output=True, timeout=5)
            return (r.stdout or '').strip() or None
        except Exception:  # noqa: BLE001
            return None
    return cfg('user.name'), cfg('user.email')


def entry_from_task(tid, task, keep_owner=None):
    """Локальная задача → запись реестра (только переносимое).

    `keep_owner` — владелец из уже существующей записи: правка чужой задачи не
    переписывает авторство на себя.
    """
    e = {'schema': 1, 'id': tid}
    for k in SHARED:
        if task.get(k):
            e[k] = shared_gitlab(task[k]) if k == 'gitlab' and isinstance(task[k], dict) \
                else task[k]
    # ⛔ Порожній СПИСОК міток — теж значення («людина прибрала всі»): без ключа інша машина лишила б свої старі мітки (pull
    # зливає лише `if k in e`), а свіжа показала б похідну мітку профілю. Старі клієнти ключ ігнорують.
    if isinstance(task.get('tags'), list):
        e['tags'] = task['tags']
    if keep_owner:
        e['owner'], e['owner_key'] = keep_owner
    elif not e.get('owner'):
        name, email = _identity()
        if name:
            e['owner'] = name
        if email:
            e['owner_key'] = email
    e['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    return e


def sync_age_h(cfg):
    """Сколько часов назад pull'или реестр. None — никогда."""
    at = (cfg.get('registry') or {}).get('synced_at')
    if not at:
        return None
    try:  # метка в UTC → timegm, а не mktime (mktime трактует как локальное время)
        t = calendar.timegm(time.strptime(at, '%Y-%m-%dT%H:%M:%SZ'))
    except ValueError:
        return None
    return max(0.0, (time.time() - t) / 3600)


def staleness(cfg, check_remote=True):
    """Свежесть кеша: {'state': fresh|stale|never|behind|offline, 'age_h', 'hint'}.

    `behind` — реестр уехал вперёд (origin/registry ≠ зафиксированный head): это
    важнее возраста, потому что значит «коллега что-то зарегистрировал».
    """
    age = sync_age_h(cfg)
    local_head = (cfg.get('registry') or {}).get('head')
    if check_remote:
        rh = remote_head(cfg)
        if rh is None:
            return {'state': 'offline', 'age_h': age,
                    'hint': 'реєстр недоступний (VPN?) — працюю з локальним кешем'}
        if local_head and rh != local_head:
            return {'state': 'behind', 'age_h': age,
                    'hint': 'реєстр поїхав уперед — `registry.py pull`'}
    if age is None:
        return {'state': 'never', 'age_h': None,
                'hint': 'реєстр ще не підтягували — `registry.py pull`'}
    if age > TTL_H:
        return {'state': 'stale', 'age_h': age,
                'hint': f'кеш старіший за {TTL_H:g} год — `registry.py pull`'}
    return {'state': 'fresh', 'age_h': age, 'hint': ''}


def _track_of_entry(e):
    """Напрямок запису спільного реєстру (МЕЖА): `track`, коли непорожній рядок, інакше `profile` (колеги на старому
    інструменті шлють лише `profile`). Одна з трьох меж, де `profile` ще читається (поряд із `task-new` і `_liga_flow`)."""
    if not isinstance(e, dict):
        return None
    for key in ('track', 'profile'):
        v = e.get(key)
        if isinstance(v, str) and v:
            return v
    return None


_WORK_ROOT_WARNED = False


def _liga_view():
    """Вигляд напрямків простору ЛІГИ реєстру (`serve._TrackView`) — будується ОДИН раз на `pull`. Реєстр просторів, що не
    читається (`SpacesError`), НЕ валить `pull` на півдорозі (ще до збереження стану): вигляд порожній (корінь — спільний), а
    причину кажемо вголос один раз."""
    global _WORK_ROOT_WARNED
    sys.path.insert(0, os.path.join(ROOT, 'app'))
    import serve
    import spaces
    try:
        sp = next((s for s in spaces.read_registry()['spaces'] if s.get('legacy') is True), None)
    except spaces.SpacesError as err:
        sp = None
        if not _WORK_ROOT_WARNED:
            _WORK_ROOT_WARNED = True
            print(f'   ⚠ реєстр просторів не прочитати ({err.code}) — теки нових задач беруться зі спільного кореня',
                  file=sys.stderr)
    return serve._TrackView(sp)


#: Кеш вигляду на час ОДНОГО `pull` (`None` поза ним): реєстр просторів і `space.json` читаються раз, а не на кожну задачу.
_PULL_VIEW = None


def _work_root(cfg, task):
    """Корінь теки задачі через ЯВНІ напрямки простору ЛІГИ (`serve.track_root`); простору/напрямків нема → спільний корінь
    `serve.default_task_root(cfg)`. Підпис без `view` свідомо: тести підміняють `_work_root(cfg, task)`."""
    sys.path.insert(0, os.path.join(ROOT, 'app'))
    import serve
    return serve.track_root(_pull_view(), _track_of_entry(task)) or serve.default_task_root(cfg)


def _pull_view():
    """Вигляд напрямків для `_work_root`: у межах `pull` — один на весь виклик (комірка `_PULL_VIEW` будується ліниво, перше звернення),
    поза ним — свіжий на кожен виклик."""
    if _PULL_VIEW is None:
        return _liga_view()
    if not _PULL_VIEW:
        _PULL_VIEW.append(_liga_view())
    return _PULL_VIEW[0]


def split_fixtures(entries):
    """(чисті, сміття) — записи, що вказують у тимчасову теку, окремо з причиною.

    Для тих, хто ЧИТАЄ спільний стан (pull, status, синк дашборда, доктор):
    сміття, яке вже протекло в реєстр, не має розповзатись далі — ні в кеш
    колеги, ні на дашборд, — і мусить бути назване вголос, а не відкинуте мовчки.
    """
    clean, junk = {}, {}
    for tid, e in entries.items():
        why = fixture_path_reason(e)
        if why:
            junk[tid] = why
        else:
            clean[tid] = e
    return clean, junk


def _say_junk(junk, stream=None):
    for tid, why in junk.items():
        print(f'   ⛔ у реєстрі сміття-фікстура: {tid} — {why}. У кеш не кладу; '
              f'прибери з гілки registry (registry/tasks/{tid}.json)',
              file=stream or sys.stderr)


def cmd_pull(_a):
    """`pull` реєстру. Вигляд напрямків (`_PULL_VIEW`) живе рівно на час виклику: `finally` скидає його й після винятку (інакше наступний
    виклик у тому ж процесі — тест, `push` після невдалого `pull` — читав би застарілий вигляд)."""
    global _PULL_VIEW
    _PULL_VIEW = []                           # вигляд напрямків ЛІГИ — ліниво й раз на `pull` (див. `_pull_view`)
    try:
        return _cmd_pull(_a)
    finally:
        _PULL_VIEW = None


def _cmd_pull(_a):
    # Модульного шляху до app/ тут нема (лише лінивий у `_work_root`), а `spaces` потрібен
    # одразу: реєстр командний, і задача колеги не мусить ліпитись у старий файл, якщо її id
    # уже живе в ІНШОМУ просторі цієї машини.
    sys.path.insert(0, os.path.join(ROOT, 'app'))
    import spaces
    # Перевірка між просторами має сенс лише коли pull оновлює САМЕ старий файл (простір
    # `legacy`) при увімкненому шарі. Інший `TASKS_PATH` (тести підміняють його на тимчасовий)
    # — це не простір, і лізти заради нього в справжній `~/.deai` (читати й, чого доброго,
    # мігрувати) не можна.
    cross_check = (spaces.layer_on()
                   and os.path.abspath(TASKS_PATH) == os.path.abspath(spaces.legacy_tasks_file()))
    cfg = load_tasks()
    d = ensure_clone(cfg)
    _git(['reset', '--hard', f'origin/{BRANCH}'], d, cfg)
    # ⛔ Сміття-фікстуру з реєстру в кеш НЕ кладемо: з кешу її підхопили б і
    # синк дашборда, і наступний `push --all` цієї машини (див. push_tasks).
    reg, junk = split_fixtures(read_registry(d))
    tasks = cfg.setdefault('tasks', {})

    added, updated = [], []
    # Що САМЕ ця синхронізація визначає — по полях. Записуємо потім точково, на
    # свіжо перечитаний конфіг: див. `_save_registry_state`.
    writes = {}
    for tid, e in reg.items():
        local = tasks.get(tid)
        if local is None:
            if cross_check:
                try:
                    other = spaces.find_task(tid)
                except spaces.AmbiguousTask:
                    other = {'legacy': False}
                except spaces.SpacesError as err:
                    # Реєстр просторів не прочитати: pull ЛІГА через це не блокуємо, але вголос.
                    print(f'   ⚠ реєстр просторів не прочитати ({err.code}) — перевірку id між '
                          f'просторами пропущено', file=sys.stderr)
                    cross_check = False
                    other = None
                if other is not None and not other.get('legacy'):
                    print(f'   ⚠ {tid}: такий id уже є в іншому просторі — пропущено',
                          file=sys.stderr)
                    continue
            local = tasks[tid] = {}
            added.append(tid)
        else:
            # что реально поменяется в переносимых полях
            if any(local.get(k) != _pulled_value(local, k, e[k], e) for k in SHARED if k in e):
                updated.append(tid)
        mine = writes.setdefault(tid, {})
        # ⛔ Знімок ДО циклу: пара Vercel вирішується цілком. Із живим `local`
        # записаний щойно `vercel_project` робив `vercel_scope` «своїм» (None) —
        # друга машина власника брала пару НАПОЛОВИНУ й публікувала без --scope
        # (ревʼю 29.09.2026).
        before = dict(local)
        for k in SHARED:                      # реестр — источник истины
            if k in e:
                v = _pulled_value(before, k, e[k], e)
                if v is None:
                    continue                  # поле машинне й локально відсутнє
                local[k] = v
                mine[k] = v
        # МЕЖА track/profile: запис реєстру старої машини має лише `profile`, а рантайм читає тільки `track` — без цього
        # такий запис у кеші не мав би напрямку (ні мітки, ні `?ds=`, ні кореня). `track` із реєстру (SHARED вище) не чіпаємо.
        # Запис БЕЗ власного `track` написала стара машина: її `profile` — істина, тож локальний `track` ЗАМІНЮЄМО (а не лише дописуємо до
        # порожнього: інакше `track` зі старішого `pull` пережив би зміну напрямку колегою). Запис із власним `track` — його вже скопійовано.
        t = _track_of_entry(e)
        if t and not (isinstance(e.get('track'), str) and e['track']):
            local['track'] = t
            mine['track'] = t
        # dir выводим локально, из реестра не берём: он машинный. Корень — за
        # напрямком задачі (`track`, інакше `profile`), інакше задача чужого напрямку
        # лягла б у чужу теку (вимога 31.08.2026: три напрямки — три теки).
        if not local.get('dir'):
            root = _work_root(cfg, local)
            if root:
                local['dir'] = os.path.join(root, tid)
                mine['dir'] = local['dir']

    # Сміття (у реєстрі чи лише в кеші) — не «є локально, віддай push»: пуш його
    # однаково відмовить, а порада штовхала б людину пушити фікстуру.
    local_junk = {t: w for t, w in ((t, fixture_path_reason(tasks[t])) for t in tasks)
                  if w and t not in junk}
    only_local = [t for t in tasks if t not in reg and t not in junk and t not in local_junk]
    head = _git(['rev-parse', 'HEAD'], d, cfg).stdout.strip()
    _save_registry_state(writes, {'synced_at': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                             time.gmtime()),
                                  'head': head})

    print(f'✅ реєстр підтягнуто: {len(reg)} задач (head {head[:8]})')
    if added:
        print(f'   + нових у кеші: {", ".join(added)}')
    if updated:
        print(f'   ~ оновлено полів: {", ".join(updated)}')
    _say_junk(junk)
    for t, why in local_junk.items():
        print(f'   ⛔ у кеші фікстура: {t} — {why}. Прибери «{t}» з tasks.json',
              file=sys.stderr)
    if only_local:
        print(f'   ⚠️ є локально, немає в реєстрі: {", ".join(only_local)}'
              f' — віддай `registry.py push <id>`')
    return 0


class PushResult(list):
    """Що віддано в реєстр — СПИСОК, як і до 27.09.2026 (`if not changed`,
    `", ".join(changed)` у викликачів працюють як були), плюс `refused`:
    {id: причина} — задачі, які свідомо НЕ поїхали, бо вказують у тимчасову
    теку (`fixture_path_reason`).

    Окремим полем, а не мовчки відкинутими: викликач мусить знати, що задачу
    НЕ зареєстровано (`serve.task_new` віддає це в `registered`), а людина —
    бачити, чому. Словник замість списку зламав би `if not changed` тихо:
    непорожній словник — завжди істина.
    """

    def __init__(self, pushed=(), refused=None):
        super().__init__(pushed)
        self.refused = dict(refused or {})


def _say_refused(refused):
    """Гучний рядок у stderr про кожну відмову: ЩО не поїхало, ЧОМУ і що робити."""
    for tid, why in refused.items():
        print(f'⛔ реєстр: НЕ віддаю «{tid}» — {why}. Спільний реєстр бачить уся '
              f'команда, а звідти задача їде кожному в кеш і на дашборд. Прибери '
              f'«{tid}» з tasks.json; якщо вона вже в реєстрі — і з гілки registry '
              f'(registry/tasks/{tid}.json)', file=sys.stderr)


def push_tasks(ids):
    """Отдать задачи в реестр. ids=None → все локальные. Возвращает `PushResult`:
    список отданных + `.refused` (фікстури, які НЕ віддано, з причиною).

    Ядро без argparse — чтобы вызывать и из CLI, и из serve.task_new при бутстрапе.

    ⛔ Задача, що вказує в тимчасову теку, у реєстр НЕ їде — ні з CLI, ні з
    serve, ні з `--all` колеги, в чий кеш вона вже встигла приїхати (див.
    `fixture_path_reason`, інцидент `nova` 15.09.2026). Відмова стоїть ТУТ, на
    самому пуші, а не в кожному тесті: тест, який забув ізолюватись, більше не
    може зробити свою фікстуру спільним станом. Решта задач пушиться як завжди.
    """
    cfg = load_tasks()
    tasks = cfg.get('tasks', {})
    if ids is None:
        ids = list(tasks)
    missing = [t for t in ids if t not in tasks]
    if missing:
        raise KeyError(f'немає таких задач локально: {", ".join(missing)}')

    refused = {}
    for tid in ids:
        why = fixture_path_reason(tasks[tid])
        if why:
            refused[tid] = why
    _say_refused(refused)
    ids = [t for t in ids if t not in refused]
    if not ids:
        return PushResult([], refused)        # клон навіть не чіпаємо

    d = ensure_clone(cfg)
    _git(['reset', '--hard', f'origin/{BRANCH}'], d, cfg)  # pull-first: не пушим поверх чужого
    tdir = os.path.join(d, 'registry', 'tasks')
    os.makedirs(tdir, exist_ok=True)

    changed = []
    for tid in ids:
        p = os.path.join(tdir, f'{tid}.json')
        old = None
        if os.path.isfile(p):
            with open(p, encoding='utf-8') as f:
                old = json.load(f)
        keep = (old.get('owner'), old.get('owner_key')) if old and old.get('owner') else None
        e = entry_from_task(tid, tasks[tid], keep_owner=keep)
        # Прив'язку превʼю в реєстрі міняє лише власник (див. VERCEL_KEYS).
        if old and not _is_owner(old.get('owner_key')):
            for k in VERCEL_KEYS:
                if k in old:
                    e[k] = old[k]
                else:
                    e.pop(k, None)
        if old and {k: old.get(k) for k in SHARED} == {k: e.get(k) for k in SHARED}:
            continue                          # без содержательных изменений — не шумим коммитом
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(e, f, ensure_ascii=False, indent=2)
            f.write('\n')
        # свести кеш с тем, что отдали (иначе status сразу покажет ложный дрейф
        # по полям, которые проставил сам push — например owner)
        for k in SHARED:
            if k in e:
                tasks[tid][k] = e[k]
        changed.append(tid)

    if not changed:
        return PushResult([], refused)

    _git(['add', 'registry/tasks'], d, cfg)
    msg = (f'registry: {changed[0]}' if len(changed) == 1
           else f'registry: {len(changed)} задач ({", ".join(changed)})')
    _git(['-c', 'commit.gpgsign=false', 'commit', '-q', '-m', msg], d, cfg)
    _git(['push', 'origin', BRANCH], d, cfg)
    head = _git(['rev-parse', 'HEAD'], d, cfg).stdout.strip()
    # Пуш нічого не приносить у локальні задачі — лише позначку синхронізації.
    _save_registry_state({}, {'synced_at': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                         time.gmtime()),
                              'head': head})
    return PushResult(changed, refused)


def cmd_push(a):
    """`push <id>` фікстури → код 1: попросили рівно її, і рівно її не віддали.
    `push --all` → код 0, якщо решта поїхала: фікстура в кеші колеги — не
    провал його пуша, а сміття, про яке `push_tasks` щойно сказав у stderr."""
    try:
        changed = push_tasks(None if a.all else [a.id])
    except KeyError as e:
        sys.exit(str(e.args[0]))
    refused = getattr(changed, 'refused', {})
    if changed:
        print(f'✅ у реєстр віддано: {", ".join(changed)}')
    elif not refused:
        print('✅ реєстр уже актуальний — нічого пушити')
    if refused:
        print(f'⛔ НЕ віддано (фікстури тестів): {", ".join(refused)} — див. stderr')
    return 1 if refused and not a.all else 0


def cmd_status(_a):
    cfg = load_tasks()
    st = staleness(cfg)
    age = st['age_h']
    age_s = 'ніколи' if age is None else (f'{age*60:.0f} хв тому' if age < 1 else f'{age:.1f} год тому')
    icon = {'fresh': '✅', 'stale': '⚠️', 'never': '⚠️', 'behind': '⬇️', 'offline': '⚠️'}[st['state']]
    print(f'{icon} реєстр: синк {age_s}' + (f' — {st["hint"]}' if st['hint'] else ''))

    tasks = cfg.get('tasks', {})
    try:
        reg = read_registry(ensure_clone(cfg))
    except OSError as e:
        print(f'   (реєстр недоступний: {e})')
        return 0

    # Сміття-фікстуру називаємо окремо: інакше `only_reg` порадив би `pull`,
    # який її свідомо не принесе, а `only_local` — `push`, який її відмовить.
    reg, junk = split_fixtures(reg)
    _say_junk(junk, sys.stdout)
    local_junk = [t for t in tasks if t not in junk and fixture_path_reason(tasks[t])]
    for t in local_junk:
        print(f'   ⛔ у кеші фікстура: {t} — {fixture_path_reason(tasks[t])}. '
              f'Прибери «{t}» з tasks.json')
    only_local = [t for t in tasks if t not in reg and t not in junk and t not in local_junk]
    only_reg = [t for t in reg if t not in tasks]
    drift = [t for t in reg if t in tasks
             and any(tasks[t].get(k) != _pulled_value(tasks[t], k, reg[t][k], reg[t])
                     for k in SHARED if k in reg[t])]
    print(f'   задач: у реєстрі {len(reg)}, локально {len(tasks)}')
    by_track, by_owner = {}, {}
    for e in reg.values():
        k = _track_of_entry(e) or '?'
        by_track[k] = by_track.get(k, 0) + 1
        by_owner[e.get('owner') or '—'] = by_owner.get(e.get('owner') or '—', 0) + 1
    print('   напрямки: ' + ', '.join(f'{k} {v}' for k, v in sorted(by_track.items())))
    print('   хто завів: ' + ', '.join(f'{k} {v}' for k, v in sorted(by_owner.items())))
    if only_reg:
        print(f'   ⬇️ є в реєстрі, немає локально: {", ".join(only_reg)} — `pull`')
    if only_local:
        print(f'   ⬆️ є локально, немає в реєстрі: {", ".join(only_local)} — `push`')
    if drift:
        print(f'   ± розійшлися поля: {", ".join(drift)} — `pull` (реєстр головніший)')
    # Власник бачить, що в реєстрі ЧУЖА прив'язка превʼю (boss-interface, 21.09):
    # pull її не візьме, тож лікується лише його push.
    foreign_bind = [t for t in reg if t in tasks and _is_owner(reg[t].get('owner_key'))
                    and tasks[t].get('vercel_project') and reg[t].get('vercel_project')
                    and any(tasks[t].get(k) != reg[t].get(k) for k in VERCEL_KEYS)]
    for t in foreign_bind:
        print(f'   ⚠️ {t}: у реєстрі не твоя прив\'язка превʼю ({reg[t].get("vercel_project")}), '
              f'а задача твоя — `registry.py push {t}`')
    if not (only_reg or only_local or drift or junk or local_junk or foreign_bind):
        print('   розбіжностей немає')
    return 0


def main():
    ap = argparse.ArgumentParser(description='реєстр задач: design-office/registry')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status', help='вік кешу + розбіжності').set_defaults(fn=cmd_status)
    sub.add_parser('pull', help='підтягнути реєстр у tasks.json').set_defaults(fn=cmd_pull)
    pp = sub.add_parser('push', help='віддати задачу в реєстр')
    pp.add_argument('id', nargs='?')
    pp.add_argument('--all', action='store_true')
    pp.set_defaults(fn=cmd_push)
    a = ap.parse_args()
    try:
        return a.fn(a)
    except OSError as e:
        sys.exit(f'⚠️ реєстр недоступний: {e}')


if __name__ == '__main__':
    sys.exit(main() or 0)
