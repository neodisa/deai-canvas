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
  1. `task['id']` — `[\\w-]+` (ASCII, `fullmatch`): імʼя теки під `<folder>`, тож жодних `/`, `..`, крапок;
  2. тека `folder` — з `ctx['settings']`, абсолютна й схвалена `ctx['folder_ok']`;
  3. `<folder>/<id>/`, якщо вже є, мусить бути справжньою текою (не посиланням) із маркером `.deai-published`
     — інакше `bad-folder` і НІЧОГО не видаляється: чужу теку, на яку вказало налаштування, не затремо;
  4. залишки `.tmp-<id>-<rand>` / `.old-<id>-<rand>` ЦІЄЇ задачі (рівно такі імена, справжні теки, не посилання,
     з маркером) прибираються; чужі задачі, немарковані й дивні імена не чіпаються;
  5. збірка копіюється в `.tmp-<id>-<rand>`, потім пишеться маркер (маркер — ознака завершеної копії: поки
     копіюється, `.tmp-*` залишків-кандидатів на прибирання не має);
  6. стара `<id>/` → `.old-<id>-<rand>`, нова → `<id>/`, стара → `rmtree`. Між двома перейменуваннями
     `<id>/` на мить нема (404 при роздачі — прийнятно). Збій будь-де: прибирається лише СВІЙ `.tmp-*`, стару
     версію повернуто на місце.
Повертає `{'path': '<folder>/<id>'}`.

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
_TRIES = 16


def _error(ctx, code, message):
    """Виняток для ядра: його `ModuleError` (з `ctx`), а без нього — звичайний `RuntimeError` з кодом у тексті."""
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    if isinstance(cls, type) and issubclass(cls, Exception):
        return cls(code, message=message)
    return RuntimeError(f'{code}: {message}')


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
    if os.path.islink(dest) or not os.path.isdir(dest):
        raise _error(ctx, 'bad-folder', f'{dest}: is a symlink or not a folder, not touching it')
    if not _marked(dest):
        raise _error(ctx, 'bad-folder', f'{dest}: exists and has no {MARKER} marker, '
                                        'so it was not published by Deai Canvas; not touching it')


def _sweep(folder, tid):
    """Прибрати залишки ЦІЄЇ задачі після збою: `.tmp-<id>-<hex8>` / `.old-<id>-<hex8>` — справжні теки (не
    посилання) з маркером. Імʼя однозначне: `<id>` — усе між префіксом і останнім `-<hex8>`, тож залишок
    задачі `a-12345678` не сплутається із залишком задачі `a`."""
    pat = re.compile(r'\.(?:tmp|old)-' + re.escape(tid) + r'-[0-9a-f]{8}')
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        p = os.path.join(folder, name)
        if pat.fullmatch(name) and not os.path.islink(p) and os.path.isdir(p) and _marked(p):
            shutil.rmtree(p, ignore_errors=True)


def _fresh(ctx, folder, kind, tid):
    """Вільне імʼя `.<kind>-<id>-<hex8>` у `folder`: наявне чужим не перезаписуємо й не видаляємо."""
    for _ in range(_TRIES):
        p = os.path.join(folder, f'.{kind}-{tid}-{token_hex(4)}')
        if not os.path.lexists(p):
            return p
    raise _error(ctx, 'module-error', f'no free .{kind}- name in {folder}')


def publish(ctx, build_dir, task):
    tid = task.get('id') if isinstance(task, dict) else None
    if not isinstance(tid, str) or not ID_RE.fullmatch(tid):
        raise _error(ctx, 'module-error', 'task id: expected [A-Za-z0-9_-]+')
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
