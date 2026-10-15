"""Вбудований модуль `static-publish` (роль `publish`): зібране превʼю задачі → тека ПОЗА простором.

Це НЕЯВНИЙ постачальник публікації: діє в просторі без `integrations`, доки людина не вирішила інакше
(`deai_modules.IMPLICIT_MODULE`). Диспетчер ядра будує превʼю (`build_preview`) і кличе `publish`; роздачу
`/published/…` робить ядро (перевіряючи ту саму теку тими самими правилами).

`server.py` виконується ядром через `exec` у свіжий модуль: лише stdlib, без імпорту `serve`, `deai_modules`
чи сусідніх файлів. Те, що інакше довелося б імпортувати, ядро кладе в `ctx`:
  * `ctx['folder_ok'](folder) -> (ok, код)` — правила теки публікації (`deai_modules.folder_ok`, привʼязані до
    простору): модуль повторює перевірку на КОЖНІЙ публікації й у `check` (ядро вже перевірило раніше —
    це друга лінія, не заміна);
  * `ctx['ModuleError']` — клас помилки ядра: `call()` пропускає як є лише його, з кодом із таблиці `STATUS`
    (`bad-folder` → 409), а звичайний виняток став би `module-error` 502. Без класу в `ctx` (рукописний `ctx`)
    модуль кидає звичайний `RuntimeError` із тим самим кодом у тексті — тихої відмови нема.
Пароль превʼю (`ctx['secrets']`) модуль НЕ читає: його вкладає в сторінки збірка (ядро), тож у помилках
модуля його не може бути за побудовою (тест це стереже).

Що робить `publish(ctx, build_dir, task)` (`task = {id, title, dir}`)
  1. `task['id']` — `[\\w-]+` (ASCII, `fullmatch`), ≤ `MAX_ID` символів, не імʼя пристрою Windows (`CON`, `NUL`,
     `COM1`…): імʼя теки під `<folder>`, тож жодних `/`, `..`, крапок;
  2. тека `folder` — з `ctx['settings']`, абсолютна й схвалена `ctx['folder_ok']`;
  3. `<folder>/<id>/`, якщо вже є, мусить бути справжньою текою (не посиланням) із маркером `.deai-published`
     — інакше `bad-folder` і НІЧОГО не видаляється: чужу теку, на яку вказало налаштування, не затремо. На ФС без
     урахування регістру `foo` і `Foo` — одна тека: якщо точного імені `<id>` у списку теки нема, це чужа
     (`Foo`) — теж `bad-folder`;
  4. `<id>/` нема, а є марковані `.old-<id>-<rand>` (збій посеред заміни) — НАЙНОВІШУ (за mtime) повертаємо на
     місце, щоб наступний крок не видалив останню робочу версію; потім залишки `.tmp-<id>-<rand>` /
     `.old-<id>-<rand>` ЦІЄЇ задачі (рівно такі імена, справжні теки, не посилання, з маркером) прибираються;
     чужі задачі, немарковані й дивні імена не чіпаються;
  5. збірка копіюється в `.tmp-<id>-<rand>`, потім пишеться маркер (маркер — ознака завершеної копії: поки
     копіюється, `.tmp-*` залишків-кандидатів на прибирання не має);
  6. стара `<id>/` → `.old-<id>-<rand>`, нова → `<id>/`, стара → `rmtree`. Перевірка маркера не атомарна з
     перейменуванням, тож ПІСЛЯ нього перевіряється те, що саме перейменували (справжня тека з маркером): чужу,
     що стала на місце за цей проміжок, повертаємо назад (чи лишаємо під `.old-…`) і відмовляємо — видаляється
     лише те, що перевірено. Між двома перейменуваннями `<id>/` на мить нема (404 при роздачі — прийнятно).
     Збій будь-де: прибирається лише СВІЙ `.tmp-*`, стару версію повернуто на місце.
Повертає `{'path': '<folder>/<id>'}`.

⚠️ Паралельність: виклики для однієї пари (тека, задача) МУСИТЬ серіалізувати викликач (диспетчер ядра так і робить —
лок на (realpath(folder), id) без урахування регістру). Сам модуль не безпечний проти паралельних публікацій того
самого `<folder>/<id>`: його `_sweep` може прибрати ЖИВИЙ `.tmp-*` конкурента, що вже має маркер.

`check(ctx)` — без побічних ефектів (нічого не створює, не пише): тека проходить правила, а вона або її найближчий
НАЯВНИЙ предок записувані. Для звичайного поганого вводу (нема налаштування, тека не пройшла правила) не кидає,
а повертає `{"ok": false, "error": <код>, "detail": <причина>}`.
"""
import os
import re
import shutil
import stat
from secrets import token_hex

#: Маркер «цю теку створив Deai Canvas, її можна замінити». Без нього наявну теку не чіпаємо ніколи.
MARKER = '.deai-published'
MARKER_TEXT = 'Створено Deai Canvas: публікація превʼю. Цю теку можна замінювати при повторній публікації.\n'
#: Ідентифікатор задачі = імʼя теки: лише слово-символи й дефіс, ASCII (юнікодні цифри/літери не потрібні).
ID_RE = re.compile(r'[\w-]+', re.ASCII)
#: Довжина id: `.tmp-<id>-<hex8>` лишається далеко під 255 байтами імені.
MAX_ID = 128
#: Імена пристроїв Windows: теку з таким імʼям там не створити (регістр байдужий; ID_RE вже не пускає крапку/суфікс).
_RESERVED = re.compile(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', re.IGNORECASE | re.ASCII)
_TRIES = 16


def _error(ctx, code, message):
    """Виняток для ядра: його `ModuleError` (з `ctx`), а без нього — звичайний `RuntimeError` з кодом у тексті."""
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    if isinstance(cls, type) and issubclass(cls, Exception):
        return cls(code, message=message)
    return RuntimeError(f'{code}: {message}')


def _task_id(ctx, task):
    tid = task.get('id') if isinstance(task, dict) else None
    if not isinstance(tid, str) or not ID_RE.fullmatch(tid):
        raise _error(ctx, 'module-error', 'task id: expected [A-Za-z0-9_-]+')
    if len(tid) > MAX_ID:
        raise _error(ctx, 'module-error', f'task id: longer than {MAX_ID} characters')
    if _RESERVED.fullmatch(tid):
        raise _error(ctx, 'module-error', f'task id: {tid!r} is a reserved device name on Windows')
    return tid


def _folder(ctx):
    """`(тека, None)` або `(None, (код для check, причина))`. Відмовляємо, а не пускаємо: немає правила в `ctx`,
    воно кинуло чи віддало не `(True, …)` — теж відмова."""
    settings = ctx.get('settings') if isinstance(ctx, dict) else None
    folder = settings.get('folder') if isinstance(settings, dict) else None
    if not isinstance(folder, str) or not folder.strip():
        return None, ('no-folder', 'folder: not set')
    if not os.path.isabs(folder):
        return None, ('bad-folder', 'path-not-absolute')
    rule = ctx.get('folder_ok')
    if not callable(rule):
        return None, ('bad-folder', 'no folder rule in ctx')
    try:
        ok, why = rule(folder)
    except Exception:  # noqa: BLE001 — збій правила = відмова
        return None, ('bad-folder', 'path-invalid')
    if ok is not True:
        return None, ('bad-folder', why if isinstance(why, str) and why else 'path-invalid')
    return folder, None


def _marked(d):
    """У теці `d` є маркер — ЗВИЧАЙНИЙ файл (посилання на чужий файл маркером не вважаємо)."""
    try:
        return stat.S_ISREG(os.lstat(os.path.join(d, MARKER)).st_mode)
    except OSError:
        return False


def _check_dest(ctx, dest):
    """Тека задачі: нема — гаразд; є — лише справжня тека із маркером, інакше `bad-folder` (нічого не видаляємо)."""
    if not os.path.lexists(dest):
        return
    try:
        names = os.listdir(os.path.dirname(dest))
    except OSError:
        names = []
    if os.path.basename(dest) not in names:             # ФС без урахування регістру: знайшлася теку з ІНШИМ регістром імені
        raise _error(ctx, 'bad-folder', f'{dest}: a folder with a different letter case already exists here '
                                        '(another task), not touching it')
    if os.path.islink(dest) or not os.path.isdir(dest):
        raise _error(ctx, 'bad-folder', f'{dest}: is a symlink or not a folder, not touching it')
    if not _marked(dest):
        raise _error(ctx, 'bad-folder', f'{dest}: exists and has no {MARKER} marker, '
                                        'so it was not published by Deai Canvas; not touching it')


def _leftovers(folder, tid):
    """Шляхи залишків ЦІЄЇ задачі після збою: `.tmp-<id>-<hex8>` / `.old-<id>-<hex8>` — справжні теки (не
    посилання) з маркером. Імʼя однозначне: `<id>` — усе між префіксом і останнім `-<hex8>`, тож залишок
    задачі `a-12345678` не сплутається із залишком задачі `a`."""
    pat = re.compile(r'\.(?:tmp|old)-' + re.escape(tid) + r'-[0-9a-f]{8}')
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for name in names:
        p = os.path.join(folder, name)
        if pat.fullmatch(name) and not os.path.islink(p) and os.path.isdir(p) and _marked(p):
            out.append(p)
    return out


def _sweep(folder, tid):
    for p in _leftovers(folder, tid):
        shutil.rmtree(p, ignore_errors=True)


def _restore(folder, tid, dest):
    """Збій посеред заміни (`<id>/` уже стала `.old-…`, а нова ще не стала на місце) лишає задачу без теки. Тоді
    НАЙНОВІШУ марковану `.old-<id>-*` (за mtime теки, тобто за часом її публікації; за рівності — за імʼям)
    повертаємо на місце: інакше `_sweep` видалив би останню робочу версію."""
    if os.path.lexists(dest):
        return
    try:
        olds = [p for p in _leftovers(folder, tid) if os.path.basename(p).startswith('.old-')]
        if olds:
            os.rename(max(olds, key=lambda p: (os.lstat(p).st_mtime_ns, p)), dest)
    except OSError:
        pass


def _fresh(ctx, folder, kind, tid):
    """Вільне імʼя `.<kind>-<id>-<hex8>` у `folder`: наявне чужим не перезаписуємо й не видаляємо."""
    for _ in range(_TRIES):
        p = os.path.join(folder, f'.{kind}-{tid}-{token_hex(4)}')
        if not os.path.lexists(p):
            return p
    raise _error(ctx, 'module-error', f'no free .{kind}- name in {folder}')


def publish(ctx, build_dir, task):
    tid = _task_id(ctx, task)
    folder, bad = _folder(ctx)
    if bad:
        raise _error(ctx, 'bad-folder', bad[1])
    if not isinstance(build_dir, str) or not os.path.isdir(build_dir):
        raise _error(ctx, 'module-error', 'build: not a folder')
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as e:
        raise _error(ctx, 'bad-folder', f'{folder}: cannot be created ({type(e).__name__})') from None
    dest = os.path.join(folder, tid)
    _check_dest(ctx, dest)
    _restore(folder, tid, dest)
    _sweep(folder, tid)
    tmp = _fresh(ctx, folder, 'tmp', tid)
    old = None
    try:
        shutil.copytree(build_dir, tmp)
        with open(os.path.join(tmp, MARKER), 'w', encoding='utf-8') as f:
            f.write(MARKER_TEXT)
        _check_dest(ctx, dest)                          # ще раз: поки копіювали, теку могли підмінити
        if os.path.lexists(dest):
            old = _fresh(ctx, folder, 'old', tid)
            os.rename(dest, old)
            if os.path.islink(old) or not os.path.isdir(old) or not _marked(old):
                # Між `_check_dest` і `rename` на місце `<id>` стало ЧУЖЕ: видаляти можна лише перевірене.
                foreign, old = old, None
                where = foreign
                if not os.path.lexists(dest):
                    try:
                        os.rename(foreign, dest)
                        where = dest
                    except OSError:
                        pass
                raise _error(ctx, 'bad-folder', f'{dest}: changed during publish, not touching it (left as {where})')
        os.rename(tmp, dest)
    except BaseException:
        if old is not None and not os.path.lexists(dest):
            try:
                os.rename(old, dest)                    # стару версію — на місце
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)          # лише СВІЙ .tmp-*
        raise
    if old is not None:
        shutil.rmtree(old, ignore_errors=True)          # не вдалось — залишок із маркером, прибереться наступного разу
    return {'path': dest}


def check(ctx):
    folder, bad = _folder(ctx)
    if bad:
        return {'ok': False, 'error': bad[0], 'detail': bad[1]}
    p = folder
    while not os.path.lexists(p):                       # найближчий НАЯВНИЙ предок; нічого не створюємо
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    if not os.path.isdir(p):
        return {'ok': False, 'error': 'bad-folder', 'detail': 'path-not-dir'}
    if not os.access(p, os.W_OK | os.X_OK):
        return {'ok': False, 'error': 'not-writable', 'detail': p}
    return {'ok': True, 'detail': folder}
