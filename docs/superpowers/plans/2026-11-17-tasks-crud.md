# Етап Д «Задачі» (0.30.0) — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** На екрані «Задачі» з'являються три дії: створити задачу карткою в сітці, перейменувати (на картці, з вкладки, F2) і
видалити в кошик простору з «Повернути». Серверна частина — модуль кошика й чотири маршрути.

**Architecture:**
- **Кошик** — ключ `trash` у `tasks.json` простору плюс тека `<батьківська>/.deai-trash/<id>-<штамп>`.
  - Логіка в новому модулі `app/task_trash.py`: змінює `cfg` і диск, повертає `undo`.
  - Маршрути `serve.py` пишуть файл під `TASK_CRUD_LOCK` і на збій запису кличуть `undo`.
- **Клієнт.**
  - Розмітка — чиста: `tasks-home.js` і новий `task-menu.js`.
  - Тимчасовий стан екрана (`homeEdit`) і проводка — у `app.js`.
  - Форма «Нова задача» — та сама логіка, що в діалозі: винесена в `createTask(vals, ctl)`; `ctl` дає `makeFormCtl` з `ask.js`.

**Tech Stack:** Python 3 stdlib (`serve.py`, `unittest`), vanilla ES modules, `node --test`, Playwright (живі).

**Спека:** `docs/superpowers/specs/2026-11-17-tasks-crud-design.md`. Прототип:
погоджено власником 17.11.2026. Рівень строгості — **повний**:
- після КОЖНОЇ задачі — ревʼю відповідності спеці, потім ревʼю якості;
- кожен новий охоронець доводиться мутацією, яка його валить.

**Гілка:** `feat/tasks-crud` від `main` (c8a83f1), worktree `deai-canvas-dev`.

---

## Правила для виконавців (обовʼязкові)

- **Коміти.**
  - Лише `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>`.
  - Нові файли — спершу `git add -- <шлях>`.
  - Ніколи `git add -A`, `--amend`, `stash`, `reset`, `rebase`, `checkout` інших гілок.
  - Не застейджувати `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `…/2026-11-09-agents-sdk-policy-addendum.md`.
- **Заборонені місця й дії.**
  - Тести не чіпають порти 8765/4317, живе дерево `~/Liga Tools/deai-canvas`, справжні `~/.deai`, `~/deai-work`,
    `~/deai-published`, `~/.gitconfig`, справжній `tasks.json`, Teams, Supabase ЛІГИ, Jira.
  - Не ставити `DEAI_HOME`/`DC_TASKS_FILE` поза тестовими фікстурами.
  - Python — завжди `python3 -B`.
  - Без мережевих встановлень.
  - Процеси зупиняти лише за PID (ніколи `pkill`/`killall` за шаблоном, ніколи `while pgrep -f`).
  - Без `rm -rf` — тимчасові теки через `mktemp -d`.
- **Живі тести** — по одному файлу, послідовно:
  `node --test --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs`. Ніхто інший у цей час не править код.
- **Юніти.**
  - JS: `node --test tests/*.test.mjs`.
  - Python: `python3 -B -m unittest discover -s tests` (окремий модуль: `cd tests && python3 -B -m unittest test_task_trash`).
  - Також `python3 -B -m unittest discover -s bin -p 'test_*.py'`.
- **Мова.** Публічне репо: без справжніх імен, внутрішніх хостів, IP, ключів, шляхів scratchpad/tmp у файлах. Коментарі й
  тексти — українською, як у сусідньому коді.
- **UI.** Без підписів-пояснень (правило власника): лише те, що назване в спеці.

---

## Карта файлів

| Файл | Що робимо |
|---|---|
| `app/task_trash.py` (новий) | кошик: `delete`, `restore`, `purge`, `listing`, `in_trash`, `clear_tombstone`, `utcnow` |
| `app/serve.py` | `TASK_CRUD_LOCK`; маршрути `task-rename/delete/restore/purge`; `_find_task_cfg`; `trash` в `tasks-overview`; `task-thumb?trash=1`; `task_new` → `task-in-trash` + знімає надгробок |
| `bin/registry.py` | `pull` пропускає id з `trash` |
| `app/task-menu.js` (новий) | чиста розмітка меню картки |
| `app/tasks-home.js` | картка «+» / слот форми, «⋯», поле назви, питання в картці, чип і картки кошика; «Мітки» й «Нова задача» з голови — геть |
| `app/space-dialogs.js` | `taskFormHTML({inline})`; нова `taskNameFormHTML` |
| `app/spaces-model.js` | `taskFormError(..., trash)` → `idInTrash`; `task-in-trash` у `TASK_ERR_KEYS`; поле `id` |
| `app/ask.js` | `makeFormCtl(formEl)` винесено з `overlay` (поведінка та сама) |
| `app/app.js` | `homeEdit`; інлайн-форма; меню; перейменування; видалення / тост / повернення; кошик; вкладка (dblclick, F2); `BAR_ACTIONS.rentask` |
| `app/shell-palette.js` | дія «Перейменувати задачу» (F2) |
| `app/i18n.js` | нові ключі uk/en |
| `app/styles.css` | `.th-card--new/--form/--ask/--trash`, `.th-new-ic`, `.th-more`, `.th-ren`, `.th-menu`, `.cv-toast.has-act` |
| `tests/test_task_trash.py`, `tests/test_task_crud.py` (нові) | Python |
| `bin/test_registry.py` | `pull` і кошик |
| `tests/task-menu.test.mjs` (новий), `tests/tasks-home.test.mjs`, `tests/spaces-model*.test.mjs`, `tests/ask-form.test.mjs` | JS-юніти |
| `tests/live/tasks-crud.test.mjs` (новий), `tests/live/tasks-home.test.mjs` | живі |
| `CHANGELOG.md`, `package.json`, `README.md` | реліз 0.30.0 |

---

### Task 1: Модуль кошика `app/task_trash.py`

**Files:**
- Create: `app/task_trash.py`
- Test: `tests/test_task_trash.py`

- [ ] **Step 1: Написати тести (червоні)**

```python
"""Кошик задач простору (етап Д, 0.30.0): модуль без сервера — лише `cfg` і тимчасовий диск."""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))
import task_trash as tt  # noqa: E402

NOW = datetime.datetime(2026, 11, 17, 10, 15, 0, tzinfo=datetime.timezone.utc)
LATER = datetime.datetime(2026, 11, 17, 11, 0, 0, tzinfo=datetime.timezone.utc)


class TrashCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='task-trash-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, 'work')

    def mk(self, tid, files=('index.html',)):
        d = os.path.join(self.root, tid)
        os.makedirs(d)
        for f in files:
            with open(os.path.join(d, f), 'w', encoding='utf-8') as fh:
                fh.write(tid)
        return d

    def cfg(self, **tasks):
        return {'current': next(iter(tasks), None), 'tasks': {k: dict(v) for k, v in tasks.items()}}


class TrashDirFor(TrashCase):
    def test_next_to_task_folder_with_stamp(self):
        d = self.mk('a')
        self.assertEqual(tt.trash_dir_for(d, 'a', NOW), os.path.join(self.root, '.deai-trash', 'a-20261117-101500'))

    def test_taken_name_gets_suffix(self):
        d = self.mk('a')
        os.makedirs(os.path.join(self.root, '.deai-trash', 'a-20261117-101500'))
        os.makedirs(os.path.join(self.root, '.deai-trash', 'a-20261117-101500-2'))
        self.assertTrue(tt.trash_dir_for(d, 'a', NOW).endswith('a-20261117-101500-3'))


class Delete(TrashCase):
    def test_moves_folder_and_entry_in_one_cfg(self):
        d = self.mk('a')
        cfg = self.cfg(a={'title': 'A', 'dir': d, 'vercel_project': 'p'}, b={'title': 'B', 'dir': self.mk('b')})
        rec, _undo = tt.delete(cfg, 'a', NOW, order=['a', 'b'])
        self.assertNotIn('a', cfg['tasks'])
        self.assertFalse(os.path.exists(d))
        self.assertTrue(os.path.isfile(os.path.join(rec['trashDir'], 'index.html')))
        self.assertEqual(cfg['trash']['a']['entry'], {'title': 'A', 'dir': d, 'vercel_project': 'p'})
        self.assertEqual(rec['dir'], d)
        self.assertEqual(rec['at'], '2026-11-17T10:15:00Z')

    def test_current_moves_to_most_recent_other(self):
        cfg = self.cfg(a={'dir': self.mk('a')}, b={'dir': self.mk('b')}, c={'dir': self.mk('c')})
        cfg['current'] = 'b'
        tt.delete(cfg, 'b', NOW, order=['b', 'c', 'a'])
        self.assertEqual(cfg['current'], 'c')

    def test_last_task_drops_current(self):
        cfg = self.cfg(a={'dir': self.mk('a')})
        tt.delete(cfg, 'a', NOW, order=['a'])
        self.assertNotIn('current', cfg)

    def test_non_current_keeps_current(self):
        cfg = self.cfg(a={'dir': self.mk('a')}, b={'dir': self.mk('b')})
        tt.delete(cfg, 'b', NOW, order=['a', 'b'])
        self.assertEqual(cfg['current'], 'a')

    def test_missing_folder_gives_record_without_trash_dir(self):
        gone = os.path.join(self.root, 'gone')
        cfg = self.cfg(g={'dir': gone})
        rec, undo = tt.delete(cfg, 'g', NOW)
        self.assertIsNone(rec['trashDir'])
        undo()                                            # нічого не переносили — нічого й не вертає
        self.assertFalse(os.path.exists(os.path.join(self.root, '.deai-trash')))

    def test_undo_brings_folder_back(self):
        d = self.mk('a')
        cfg = self.cfg(a={'dir': d})
        rec, undo = tt.delete(cfg, 'a', NOW)
        undo()
        self.assertTrue(os.path.isfile(os.path.join(d, 'index.html')))
        self.assertFalse(os.path.exists(rec['trashDir']))

    def test_garbage_trash_value_is_replaced(self):
        cfg = self.cfg(a={'dir': self.mk('a')})
        cfg['trash'] = ['сміття']
        tt.delete(cfg, 'a', NOW)
        self.assertIn('a', cfg['trash'])


class Restore(TrashCase):
    def trashed(self):
        d = self.mk('a')
        cfg = self.cfg(a={'title': 'A', 'dir': d}, b={'dir': self.mk('b')})
        rec, _ = tt.delete(cfg, 'a', NOW, order=['a', 'b'])
        return cfg, d, rec

    def test_moves_back_and_restores_entry(self):
        cfg, d, _rec = self.trashed()
        entry, _undo = tt.restore(cfg, 'a')
        self.assertEqual(entry['title'], 'A')
        self.assertIn('a', cfg['tasks'])
        self.assertNotIn('a', cfg['trash'])
        self.assertTrue(os.path.isfile(os.path.join(d, 'index.html')))

    def test_refuses_when_original_folder_exists(self):
        cfg, d, rec = self.trashed()
        os.makedirs(d)                                    # агент записав у стару теку знову
        with self.assertRaises(tt.TrashError) as cm:
            tt.restore(cfg, 'a')
        self.assertEqual(cm.exception.code, 'task-dir-exists')
        self.assertTrue(os.path.isdir(rec['trashDir']), 'тека в кошику мусить лишитись')
        self.assertIn('a', cfg['trash'])

    def test_refuses_when_id_is_taken(self):
        cfg, _d, _rec = self.trashed()
        cfg['tasks']['a'] = {'dir': '/elsewhere'}
        with self.assertRaises(tt.TrashError) as cm:
            tt.restore(cfg, 'a')
        self.assertEqual(cm.exception.code, 'task-exists')

    def test_unknown_and_tombstone_are_not_in_trash(self):
        cfg, _d, _rec = self.trashed()
        tt.purge(cfg, 'a', LATER)
        for tid in ('a', 'nope'):
            with self.assertRaises(tt.TrashError) as cm:
                tt.restore(cfg, tid)
            self.assertEqual(cm.exception.code, 'not-in-trash')

    def test_undo_puts_folder_back_into_trash(self):
        cfg, d, rec = self.trashed()
        _entry, undo = tt.restore(cfg, 'a')
        undo()
        self.assertTrue(os.path.isdir(rec['trashDir']))
        self.assertFalse(os.path.exists(d))


class Purge(TrashCase):
    def test_removes_folder_and_leaves_tombstone(self):
        d = self.mk('a')
        cfg = self.cfg(a={'dir': d})
        rec, _ = tt.delete(cfg, 'a', NOW)
        tt.purge(cfg, 'a', LATER)
        self.assertFalse(os.path.exists(rec['trashDir']))
        self.assertEqual(cfg['trash']['a'], {'purged': '2026-11-17T11:00:00Z'})
        self.assertFalse(tt.in_trash(cfg, 'a'))

    def test_refuses_a_path_outside_the_trash(self):
        victim = self.mk('victim')
        cfg = {'tasks': {}, 'trash': {'x': {'entry': {}, 'dir': victim, 'trashDir': victim, 'at': 'x'}}}
        with self.assertRaises(tt.TrashError) as cm:
            tt.purge(cfg, 'x', LATER)
        self.assertEqual(cm.exception.code, 'task-purge-failed')
        self.assertTrue(os.path.isfile(os.path.join(victim, 'index.html')))
        self.assertIn('entry', cfg['trash']['x'])

    def test_symlink_in_trash_is_unlinked_not_followed(self):
        target = self.mk('target')
        trash = os.path.join(self.root, '.deai-trash')
        os.makedirs(trash)
        link = os.path.join(trash, 'x-20261117-101500')
        os.symlink(target, link)
        cfg = {'tasks': {}, 'trash': {'x': {'entry': {}, 'dir': None, 'trashDir': link, 'at': 'x'}}}
        tt.purge(cfg, 'x', LATER)
        self.assertFalse(os.path.lexists(link))
        self.assertTrue(os.path.isfile(os.path.join(target, 'index.html')))


class Listing(TrashCase):
    def test_newest_first_without_tombstones_and_garbage(self):
        cfg = {'tasks': {}, 'trash': {
            'old': {'entry': {'title': 'O'}, 'at': '2026-11-16T10:00:00Z'},
            'new': {'entry': {'title': 'N'}, 'at': '2026-11-17T10:00:00Z'},
            'dead': {'purged': '2026-11-17T09:00:00Z'},
            'junk': 5}}
        self.assertEqual([k for k, _ in tt.listing(cfg)], ['new', 'old'])

    def test_clear_tombstone_keeps_live_records(self):
        cfg = {'trash': {'dead': {'purged': 'x'}, 'live': {'entry': {}, 'at': 'x'}}}
        tt.clear_tombstone(cfg, 'dead')
        tt.clear_tombstone(cfg, 'live')
        self.assertEqual(list(cfg['trash']), ['live'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Запустити — червоні:** `cd tests && python3 -B -m unittest test_task_trash -v`. Очікувано:
  `ModuleNotFoundError: No module named 'task_trash'`.

- [ ] **Step 3: Написати модуль**

```python
"""Кошик задач простору (етап Д, 0.30.0): видалення без стирання, повернення, знищення.

Запис кошика живе в `tasks.json` простору (ключ `trash`). Задача й її запис у кошику міняються ОДНИМ записом файла: немає
стану, де задача є і там, і там. Тека задачі переїжджає `os.rename` у `<батьківська>/.deai-trash/<id>-<штамп>`, тобто
поруч, на тому самому диску, без копіювання: тека задачі може лежати поза текою простору (корінь напрямку,
`design_work_root`). Після «назавжди» лишається надгробок `{"purged": …}`, щоб `bin/registry.py pull` не воскресив задачу
ЛІГИ зі спільного реєстру.

Функції змінюють `cfg` і диск, але НЕ пишуть `tasks.json`: це робить маршрут (`save_tasks`). Якщо запис упав, маршрут кличе
повернуту `undo()`. Час — параметр (`now`, aware UTC), тож тести детерміновані.
"""
import datetime
import os
import shutil

TRASH_DIRNAME = '.deai-trash'


class TrashError(Exception):
    """Відмова з кодом відповіді маршруту: `not-in-trash`, `task-exists`, `task-dir-exists`, `task-restore-failed`,
    `task-purge-failed`."""

    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(now):
    return now.strftime('%Y-%m-%dT%H:%M:%SZ')


def trash_dir_for(task_dir, tid, now):
    """Вільний шлях у кошику поруч із текою задачі: `<батьківська>/.deai-trash/<id>-<РРРРММДД-ГГХХСС>[-N]`."""
    parent = os.path.dirname(os.path.normpath(task_dir))
    base = os.path.join(parent, TRASH_DIRNAME, f"{tid}-{now.strftime('%Y%m%d-%H%M%S')}")
    cand, n = base, 2
    while os.path.lexists(cand):
        cand, n = f'{base}-{n}', n + 1
    return cand


def _bucket(cfg):
    tr = cfg.get('trash')
    return tr if isinstance(tr, dict) else {}


def records(cfg):
    """Живі записи кошика `{id: запис}`: без надгробків і без сміття, яке правили руками."""
    return {k: v for k, v in _bucket(cfg).items() if isinstance(v, dict) and isinstance(v.get('entry'), dict)}


def in_trash(cfg, tid):
    return tid in records(cfg)


def listing(cfg):
    """`[(id, запис)]` кошика, найновіші першими (за `at`)."""
    return sorted(records(cfg).items(), key=lambda kv: str(kv[1].get('at') or ''), reverse=True)


def clear_tombstone(cfg, tid):
    """Нова задача з тим самим id знімає надгробок. Живого запису кошика не чіпає: його id зайнятий (`task-in-trash`)."""
    tr = _bucket(cfg)
    v = tr.get(tid)
    if isinstance(v, dict) and 'purged' in v and 'entry' not in v:
        del tr[tid]


def delete(cfg, tid, now, order=()):
    """Задача `tid` → кошик. Тека (якщо є) переїжджає; запис задачі стає `entry` запису кошика; `current`, що вказував на неї,
    переходить на першу іншу з `order` (порядок «нещодавно відкриті» маршруту), а без інших — прибирається.
    Повертає `(запис, undo)`; `undo()` вертає теку на місце (для збою запису `tasks.json`). `OSError` переносу — маршруту."""
    entry = cfg['tasks'][tid]
    d = entry.get('dir')
    src = d if isinstance(d, str) and d and os.path.isdir(d) else None
    dst = trash_dir_for(src, tid, now) if src else None
    if src:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
    rec = {'entry': entry, 'dir': d if isinstance(d, str) else None, 'trashDir': dst, 'at': _iso(now)}
    del cfg['tasks'][tid]
    if not isinstance(cfg.get('trash'), dict):
        cfg['trash'] = {}
    cfg['trash'][tid] = rec
    if cfg.get('current') == tid:
        rest = [k for k in (list(order) or list(cfg['tasks'])) if k != tid and k in cfg['tasks']]
        if rest:
            cfg['current'] = rest[0]
        else:
            cfg.pop('current', None)

    def undo():
        if src:
            os.rename(dst, src)
    return rec, undo


def restore(cfg, tid):
    """Запис кошика `tid` → назад у `tasks`. Тека вертається на ВИХІДНИЙ шлях. Він уже зайнятий (агент записав туди нову) —
    `task-dir-exists`, нічого не рухаємо. Id зайнятий у цьому файлі — `task-exists` (між просторами перевіряє маршрут).
    Повертає `(запис задачі, undo)`; `undo()` кладе теку назад у кошик."""
    rec = records(cfg).get(tid)
    if rec is None:
        raise TrashError('not-in-trash', 'task is not in the trash')
    if tid in (cfg.get('tasks') or {}):
        raise TrashError('task-exists', 'a task with this id already exists')
    src, dst = rec.get('trashDir'), rec.get('dir')
    moved = False
    if isinstance(src, str) and src and os.path.isdir(src):
        if not isinstance(dst, str) or not dst:
            raise TrashError('task-restore-failed', 'the trash record has no original folder')
        if os.path.lexists(dst):
            raise TrashError('task-dir-exists', 'the task folder already exists')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
        moved = True
    if not isinstance(cfg.get('tasks'), dict):
        cfg['tasks'] = {}
    cfg['tasks'][tid] = rec['entry']
    del cfg['trash'][tid]

    def undo():
        if moved:
            os.rename(dst, src)
    return rec['entry'], undo


def _inside_trash(path):
    """Шлях — безпосередня дитина теки `.deai-trash`. ⛔ `trashDir` у `tasks.json` правлять руками: без цієї перевірки
    «назавжди» стерло б будь-яку теку диска."""
    norm = os.path.normpath(path)
    return os.path.basename(os.path.dirname(norm)) == TRASH_DIRNAME and os.path.basename(norm) not in ('', '.', '..')


def purge(cfg, tid, now):
    """Знищити запис кошика `tid`: тека йде з диска (посилання — лише саме посилання), запис стає надгробком. Шлях поза
    `.deai-trash` — `task-purge-failed`, нічого не стерто. `OSError` стирання — маршруту; запис лишається, тож знищення
    можна повторити."""
    rec = records(cfg).get(tid)
    if rec is None:
        raise TrashError('not-in-trash', 'task is not in the trash')
    td = rec.get('trashDir')
    if isinstance(td, str) and td and os.path.lexists(td):
        if not _inside_trash(td):
            raise TrashError('task-purge-failed', 'refusing to delete a folder outside the trash')
        if os.path.islink(td):
            os.unlink(td)
        else:
            shutil.rmtree(td)
    cfg['trash'][tid] = {'purged': _iso(now)}
```

- [ ] **Step 4: Запустити — зелені:** `cd tests && python3 -B -m unittest test_task_trash -v` → `OK` (усі тести модуля).

- [ ] **Step 5: Мутації.**
  - Прибрати `if not _inside_trash(td): raise …` → `test_refuses_a_path_outside_the_trash` червоний.
  - Прибрати гілку `if os.path.islink(td)` → `test_symlink_in_trash_is_unlinked_not_followed` червоний.
  - Замінити `rest[0]` на `None`-гілку → `test_current_moves_to_most_recent_other` червоний.
  - Повернути код після кожної мутації. Ганяти `python3 -B`.

- [ ] **Step 6: Коміт** — `app/task_trash.py tests/test_task_trash.py`:
  `feat(0.30.0): кошик задач простору — модуль task_trash`.

---

### Task 2: Маршрути `task-rename`, `task-delete`, `task-restore`, `task-purge`

**Files:**
- Modify: `app/serve.py`:
  - імпорт біля `import feedback` (~рядок 36);
  - `_REGISTRY_ROUTES` (~5988);
  - `do_POST`, ланцюжок `elif` біля `/api/task-tags` (~7310);
  - `_task_tags` (~8085) стає користувачем нового помічника.
- Test: `tests/test_task_crud.py`

- [ ] **Step 1: Тести (червоні).** Фікстура — `Fixture` з `test_spaces_serve`, як у `tests/test_task_tags.py`.
  - Шапку модуля скопіювати звідти: `sys.path`, `setUpModule`/`tearDownModule` зі `spaces_guard.snapshot()` — справжній
    `~/.deai` не мусить змінитись.
  - Імпорт: `from test_spaces_serve import Fixture, _read, _write, _bytes, _md5`.
  - У фікстурі простір `P` має задачі `x` («Ікс», тека `cls.x_dir`, поточна) і `gone` (тека не існує); простір `E` — `cls.e_path`,
    `cls.e_file`.
  - Кожен тест, що міняє файли простору `P`, кличе `snapshot_p()`: він відновлює `tasks.json` (`restore_bytes` фікстури), теку
    `x` (повністю) і прибирає `.deai-trash`. Інакше класова фікстура «протікає» між тестами.

```python
class TaskCrudApi(Fixture):
    def snapshot_p(self):
        """Повернути tasks.json простору P, теку `x` і кошик у стан «до тесту»: тести видаляють, повертають, додають кадри."""
        self.restore_bytes(self.p_file)
        keep = tempfile.mkdtemp(prefix='crud-keep-')
        shutil.copytree(self.x_dir, os.path.join(keep, 'x'))

        def back():
            shutil.rmtree(os.path.join(self.p_path, '.deai-trash'), True)
            shutil.rmtree(self.x_dir, True)
            shutil.copytree(os.path.join(keep, 'x'), self.x_dir)
            shutil.rmtree(keep, True)
        self.addCleanup(back)

    # ── перейменування ──
    def test_rename_writes_only_title_in_the_task_space(self):
        self.snapshot_p()
        st, j = self.post('/api/task-rename', {'id': 'x', 'title': '  Нова назва  '})
        self.assertEqual((st, j), (200, {'ok': True, 'id': 'x', 'title': 'Нова назва'}))
        cfg = _read(self.p_file)
        self.assertEqual(cfg['tasks']['x']['title'], 'Нова назва')
        self.assertEqual(cfg['tasks']['x']['dir'], self.x_dir)        # id і тека ті самі

    def test_rename_refuses_empty_title_without_touching_disk(self):
        self.snapshot_p()
        before = _md5(self.p_file)
        for bad in ('', '   ', None, 5):
            st, j = self.post('/api/task-rename', {'id': 'x', 'title': bad})
            self.assertEqual((st, j['code']), (400, 'bad-title'), repr(bad))
        self.assertEqual(_md5(self.p_file), before)

    def test_rename_unknown_task_is_404(self):
        st, j = self.post('/api/task-rename', {'id': 'nope', 'title': 'X'})
        self.assertEqual((st, j['code']), (404, 'unknown-task'))

    def test_rename_cuts_title_to_200(self):
        self.snapshot_p()
        _st, j = self.post('/api/task-rename', {'id': 'x', 'title': 'я' * 300})
        self.assertEqual(len(j['title']), 200)

    # ── видалення ──
    def test_delete_moves_folder_and_reports_trash(self):
        self.snapshot_p()
        st, j = self.post('/api/task-delete', {'id': 'x'})
        self.assertEqual(st, 200)
        self.assertEqual(j['id'], 'x')
        self.assertEqual(j['trash']['title'], 'Ікс')
        cfg = _read(self.p_file)
        self.assertNotIn('x', cfg['tasks'])
        rec = cfg['trash']['x']
        self.assertFalse(os.path.exists(self.x_dir))
        self.assertTrue(os.path.isdir(rec['trashDir']))
        self.assertEqual(os.path.dirname(rec['trashDir']), os.path.join(self.p_path, '.deai-trash'))

    def test_delete_current_repoints_current(self):
        self.snapshot_p()
        _st, j = self.post('/api/task-delete', {'id': 'x'})
        self.assertEqual(j['current'], 'gone')                       # єдина інша задача простору
        self.assertEqual(_read(self.p_file)['current'], 'gone')

    def test_delete_failed_save_brings_folder_back(self):
        self.snapshot_p()
        with mock.patch.object(serve, 'save_tasks', side_effect=OSError('disk full')):
            st, j = self.post('/api/task-delete', {'id': 'x'})
        self.assertEqual((st, j['code']), (500, 'task-delete-failed'))
        self.assertTrue(os.path.isdir(self.x_dir))
        self.assertIn('x', _read(self.p_file)['tasks'])

    def test_delete_unknown_is_404(self):
        st, j = self.post('/api/task-delete', {'id': 'nope'})
        self.assertEqual((st, j['code']), (404, 'unknown-task'))

    # ── повернення ──
    def test_restore_round_trip(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j), (200, {'ok': True, 'id': 'x'}))
        cfg = _read(self.p_file)
        self.assertIn('x', cfg['tasks'])
        self.assertNotIn('x', cfg.get('trash', {}))
        self.assertTrue(os.path.isdir(self.x_dir))
        self.assertEqual(cfg['current'], 'gone', 'повернення поточну не міняє')

    def test_restore_refuses_when_folder_reappeared(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        os.makedirs(self.x_dir)
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (409, 'task-dir-exists'))
        self.assertIn('x', _read(self.p_file)['trash'])

    def test_restore_refuses_id_taken_in_another_space(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        self.restore_bytes(self.e_file)
        _write(self.e_file, {'tasks': {'x': {'title': 'Чужий', 'dir': os.path.join(self.e_path, 'x')}}})
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (409, 'task-exists'))

    def test_restore_unknown_space_and_not_in_trash(self):
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': 'nope'})
        self.assertEqual((st, j['code']), (400, 'unknown-space'))
        st, j = self.post('/api/task-restore', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (404, 'not-in-trash'))

    # ── знищення ──
    def test_purge_deletes_folder_and_keeps_tombstone(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        td = _read(self.p_file)['trash']['x']['trashDir']
        st, j = self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j), (200, {'ok': True, 'id': 'x'}))
        self.assertFalse(os.path.exists(td))
        self.assertIn('purged', _read(self.p_file)['trash']['x'])

    def test_purge_rmtree_failure_keeps_record(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        with mock.patch('task_trash.shutil.rmtree', side_effect=OSError('busy')):
            st, j = self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        self.assertEqual((st, j['code']), (500, 'task-purge-failed'))
        self.assertIn('entry', _read(self.p_file)['trash']['x'])

    def test_routes_are_registry_routes(self):
        for r in ('/api/task-rename', '/api/task-delete', '/api/task-restore', '/api/task-purge'):
            self.assertIn(r, serve.Handler._REGISTRY_ROUTES)
```

  Якщо `e_file` у фікстурі ще не існує на момент тесту, `restore_bytes` впаде. Тоді — `addCleanup(os.remove, self.e_file)`
  після `_write`.

- [ ] **Step 2: Червоні:** `cd tests && python3 -B -m unittest test_task_crud -v` → 404 / `bad path` на нових маршрутах.

- [ ] **Step 3: Реалізація в `serve.py`.**

  Імпорт поруч з іншими модулями `app/`:

```python
import task_trash  # кошик задач простору (етап Д, 0.30.0): видалення без стирання, повернення, знищення
```

  Замок — модульна константа поруч із `CLAUDE_LOCK`:

```python
#: Етап Д: маршрути `task-rename/delete/restore/purge` роблять «прочитати tasks.json → змінити → записати» під ЦИМ замком —
#: два видалення поспіль не перезапишуть одне одного. Решта маршрутів його не бере (наявний борг, `atomic_io.py`).
#: ⛔ Не `WRITE_LOCK`: той нереентрантний і його бере `save_tasks` усередині.
TASK_CRUD_LOCK = threading.Lock()
```

  У `_REGISTRY_ROUTES` дописати `'/api/task-rename', '/api/task-delete', '/api/task-restore', '/api/task-purge'`.

  У `do_POST` поруч із `task-tags` — кожен маршрут окремим `elif self.path ==` (сканер `bad-body` у тестах шукає саме цю форму):

```python
        elif self.path == '/api/task-rename':
            self._task_rename(payload)
        elif self.path == '/api/task-delete':
            self._task_delete(payload)
        elif self.path == '/api/task-restore':
            self._task_restore(payload)
        elif self.path == '/api/task-purge':
            self._task_purge(payload)
```

  Помічник (над `_task_tags`), і `_task_tags` переходить на нього (поведінка та сама — `tests/test_task_tags.py` стереже):

```python
    def _find_task_cfg(self, tid):
        """`cfg` простору, де лежить задача `tid`, з простором запиту, зафіксованим на ньому; `None` — відмову вже надіслано.
        Нечитабельний файл (старий чи інших просторів) — центральний 503 `space-unavailable`, а не «нема задачі»; нема — 404
        `unknown-task`; дубль id у двох просторах — центральний 409 (`AmbiguousTask` з `find_task`)."""
        sp = spaces.find_task(tid)
        if sp is None:
            raise_if_legacy_unreadable()
            broken = spaces.unreadable_task_files(spaces.read_registry())
            if broken:
                raise SpaceUnavailable(broken[0])
            self._space_error(404, 'unknown-task', 'task not found')
            return None
        spaces.set_request_space(sp['id'])
        cfg = load_tasks()
        if tid not in cfg.get('tasks', {}):         # вилучили між `find_task` і читанням
            self._space_error(404, 'unknown-task', 'task not found')
            return None
        return cfg

    def _payload_space(self, payload):
        """Простір із тіла (`space`): кошик належить простору. Нема такого — 400 `unknown-space`, `None`."""
        want = payload.get('space')
        sp = (next((s for s in spaces.read_registry()['spaces'] if s['id'] == want), None)
              if isinstance(want, str) else None)
        if sp is None:
            self._space_error(400, 'unknown-space', 'unknown space')
            return None
        spaces.set_request_space(sp['id'])
        return sp
```

  У `_task_tags` блок від `sp = spaces.find_task(tid)` до перевірки «вилучили між…» замінити на:

```python
        cfg = self._find_task_cfg(tid)
        if cfg is None:
            return
```

  Обробники (після `_task_tags`):

```python
    def _task_rename(self, payload):
        """Етап Д: нова назва задачі `{id, title}` → `{ok, id, title}`. Лише `title`: id, тека й вкладка (вона показує id)
        лишаються. Назва — `strip`, до 200 символів (як `task-new`); порожня чи не рядок — 400 `bad-title` без читання диска.
        Після запису — `_registry_push`: у ЛІГА назва — спільне поле реєстру, як мітки."""
        raw = payload.get('title')
        title = raw.strip()[:200] if isinstance(raw, str) else ''
        if not title:
            self._space_error(400, 'bad-title', 'title must be a non-empty string')
            return
        tid = payload.get('id', '')
        with TASK_CRUD_LOCK:
            cfg = self._find_task_cfg(tid)
            if cfg is None:
                return
            cfg['tasks'][tid]['title'] = title
            save_tasks(cfg)
        _registry_push(tid)
        self._send_json({'ok': True, 'id': tid, 'title': title})

    def _task_delete(self, payload):
        """Етап Д: задача → кошик простору (`task_trash.delete`): `{id}` → `{ok, id, current, trash:{id, title, at}}`.
        Тека переїжджає ДО запису `tasks.json`; збій запису вертає її (`undo`) і відповідає 500 `task-delete-failed`.
        Видалена поточна — `current` переходить на найсвіжішу іншу (його й віддаємо: екран оновлює «відкриту зараз»)."""
        tid = payload.get('id', '')
        with TASK_CRUD_LOCK:
            cfg = self._find_task_cfg(tid)
            if cfg is None:
                return
            order = [k for k, _ in tasks_by_recent(cfg)]
            try:
                rec, undo = task_trash.delete(cfg, tid, task_trash.utcnow(), order)
            except OSError as e:
                self._space_error(500, 'task-delete-failed', str(e)[:300])
                return
            try:
                save_tasks(cfg)
            except OSError as e:
                with contextlib.suppress(OSError):
                    undo()
                self._space_error(500, 'task-delete-failed', str(e)[:300])
                return
        self._send_json({'ok': True, 'id': tid, 'current': cfg.get('current'),
                         'trash': {'id': tid, 'title': rec['entry'].get('title', tid), 'at': rec['at']}})

    def _task_restore(self, payload):
        """Етап Д: запис кошика простору `space` → назад: `{id, space}` → `{ok, id}`. Id зайнятий у БУДЬ-ЯКОМУ просторі —
        409 `task-exists`; вихідна тека вже є — 409 `task-dir-exists` (нічого не рухаємо); збій запису — тека назад у
        кошик, 500 `task-restore-failed`. `current` не змінюється."""
        tid = payload.get('id', '')
        with TASK_CRUD_LOCK:
            if self._payload_space(payload) is None:
                return
            cfg = load_tasks()
            if not task_trash.in_trash(cfg, tid):
                self._space_error(404, 'not-in-trash', 'task is not in the trash')
                return
            try:
                taken = spaces.find_task(tid) is not None
            except spaces.AmbiguousTask:
                taken = True
            if taken:
                self._space_error(409, 'task-exists', 'a task with this id already exists')
                return
            try:
                _entry, undo = task_trash.restore(cfg, tid)
            except task_trash.TrashError as e:
                self._space_error(409 if e.code in ('task-dir-exists', 'task-exists') else 500, e.code, str(e))
                return
            except OSError as e:
                self._space_error(500, 'task-restore-failed', str(e)[:300])
                return
            try:
                save_tasks(cfg)
            except OSError as e:
                with contextlib.suppress(OSError):
                    undo()
                self._space_error(500, 'task-restore-failed', str(e)[:300])
                return
        self._send_json({'ok': True, 'id': tid})

    def _task_purge(self, payload):
        """Етап Д: знищити запис кошика `{id, space}` → `{ok, id}`. Тека стирається ПЕРШОЮ; збій стирання — 500
        `task-purge-failed`, запис лишається (повтор можливий). Після — надгробок (`registry.py pull` не воскресить)."""
        tid = payload.get('id', '')
        with TASK_CRUD_LOCK:
            if self._payload_space(payload) is None:
                return
            cfg = load_tasks()
            try:
                task_trash.purge(cfg, tid, task_trash.utcnow())
            except task_trash.TrashError as e:
                self._space_error(404 if e.code == 'not-in-trash' else 500, e.code, str(e))
                return
            except OSError as e:
                self._space_error(500, 'task-purge-failed', str(e)[:300])
                return
            save_tasks(cfg)
        self._send_json({'ok': True, 'id': tid})
```

  ⛔ Перевірити, що `contextlib` імпортовано (так, рядок 9) і що `_find_task_cfg`/`_payload_space` викликаються лише з
  `do_POST` під центральним `_guarded` (503/409 туди).

- [ ] **Step 4: Зелені:**
  - `cd tests && python3 -B -m unittest test_task_crud test_task_tags test_spaces_serve -v` → `OK`.
  - Повний Python: `python3 -B -m unittest discover -s tests` → `OK`. Окремо — охоронці `bad-body` і
    `TestsCannotWriteLiveConfig`.

- [ ] **Step 5: Мутації.**
  - Прибрати `undo()` у `_task_delete` → `test_delete_failed_save_brings_folder_back` червоний.
  - Прибрати перевірку `find_task` у `_task_restore` → `test_restore_refuses_id_taken_in_another_space` червоний.

- [ ] **Step 6: Коміт** — `app/serve.py tests/test_task_crud.py`:
  `feat(0.30.0): маршрути перейменування, видалення, повернення й знищення задачі`.

---

### Task 3: Кошик у відповіді екрана, кадр із кошика, `task-new` і надгробок

**Files:**
- Modify: `app/serve.py`:
  - маршрут `GET /api/tasks-overview` (~6251);
  - `_task_thumb` (~6511);
  - `task_new` (~2346);
  - новий помічник `_trash_rows` поруч із `tasks_overview`.
- Test: `tests/test_task_crud.py` (дописати), `tests/test_tasks_overview.py` (не ламати).

- [ ] **Step 1: Тести (червоні)** — у `TaskCrudApi`:

```python
    def test_overview_lists_trash_of_the_space(self):
        self.snapshot_p()
        spaces.switch_space(self.p_id)
        self.post('/api/task-delete', {'id': 'x'})
        st, j = self.jget('/api/tasks-overview')
        self.assertEqual(st, 200)
        self.assertEqual([r['id'] for r in j['trash']], ['x'])
        row = j['trash'][0]
        self.assertEqual(row['title'], 'Ікс')
        self.assertTrue(row['at'].endswith('Z'))
        self.assertNotIn('x', [r['id'] for r in j['mine']])

    def test_overview_hides_tombstones(self):
        self.snapshot_p()
        spaces.switch_space(self.p_id)
        self.post('/api/task-delete', {'id': 'x'})
        self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        _st, j = self.jget('/api/tasks-overview')
        self.assertEqual(j['trash'], [])

    def test_task_list_does_not_see_trash(self):
        self.snapshot_p()
        spaces.switch_space(self.p_id)
        self.post('/api/task-delete', {'id': 'x'})
        _st, j = self.jget('/api/tasks')
        self.assertNotIn('x', [r['id'] for r in j['tasks']])

    def test_thumb_from_trash(self):
        self.snapshot_p()
        spaces.switch_space(self.p_id)
        make_task(self.p_path, 'x', pages=['home'])          # iterations.json + pages.json у теці `x`
        add_shot({'dir': self.x_dir}, 'it1', 'home', sha='tr1')
        self.post('/api/task-delete', {'id': 'x'})
        _st, j = self.jget('/api/tasks-overview')
        url = j['trash'][0]['thumb']
        self.assertIn('trash=1', url)
        st, _body = self.get(url)
        self.assertEqual(st, 200)
        st, _body = self.get('/api/task-thumb?task=x')     # без trash=1 — задачі в tasks нема
        self.assertEqual(st, 404)

    def test_new_task_refuses_an_id_in_trash_and_clears_a_tombstone(self):
        self.snapshot_p()
        self.post('/api/task-delete', {'id': 'x'})
        st, j = self.post('/api/task-new', {'id': 'x', 'title': 'X', 'space': self.p_id})
        self.assertEqual((st, j['code']), (400, 'task-in-trash'))
        self.post('/api/task-purge', {'id': 'x', 'space': self.p_id})
        st, j = self.post('/api/task-new', {'id': 'x', 'title': 'X', 'space': self.p_id})
        self.assertEqual(st, 200, j)
        self.assertNotIn('x', _read(self.p_file).get('trash', {}))
```

  - `make_task(root, tid, its=('it1',), pages=None)` і `add_shot(task, it, key, sha=…)` — з `tests/test_tasks_overview.py`:
    `from test_tasks_overview import make_task, add_shot`.
  - Нова задача `x` у `test_new_task…` створює теку `self.x_dir`. `snapshot_p` її прибирає й вертає оригінал.
  - `spaces.switch_space(self.p_id)` — як у сусідніх тестах `test_spaces_serve`. Поточний простір фікстура скидає в `setUp`.

- [ ] **Step 2: Червоні:** `cd tests && python3 -B -m unittest test_task_crud -v` → `KeyError: 'trash'`,
  `task-in-trash` не повертається.

- [ ] **Step 3: Реалізація.**

  Помічник поруч із `tasks_overview`:

```python
def _trash_rows(cfg, sp=None):
    """Етап Д: рядки кошика простору для екрана «Задачі» — найновіші першими, без надгробків. Кадр — з ТЕКИ В КОШИКУ
    (`/api/task-thumb?…&trash=1`); мітки — як у «Моїх» (`task_tags`, похідна мітка напрямку для запису без власних)."""
    rows = []
    for tid, rec in task_trash.listing(cfg):
        entry, td = rec['entry'], rec.get('trashDir')
        found = (task_thumb_path({**entry, 'dir': td})
                 if isinstance(td, str) and td and NAME_RE.fullmatch(tid) else None)
        rows.append({'id': tid, 'title': entry.get('title', tid), 'jira': entry.get('jira'),
                     'tags': task_tags(entry, sp), 'at': rec.get('at'),
                     'thumb': (_thumb_url(tid, found[1]) + '&trash=1') if found else None})
    return rows
```

  У маршруті `/api/tasks-overview`:
  - гілка `except spaces.NoTask` відповідає з `'trash': []`;
  - в обох гілках, де збирається `out`, перед відправкою — `out['trash'] = _trash_rows(cfg)`. Звірити, як далі будується
    відповідь (`{'current': …, **out, 'space': …}`): `trash` мусить дійти до тіла.

  У `_task_thumb`:

```python
        cfg = load_tasks()
        if q.get('trash', [''])[0] == '1':
            # Етап Д: кадр задачі з кошика — з її теки В КОШИКУ. Лише записи `trash` цього простору: довільної теки так не відкрити.
            rec = task_trash.records(cfg).get(tid)
            td = rec.get('trashDir') if rec else None
            task = {**rec['entry'], 'dir': td} if isinstance(td, str) and td else None
        else:
            task = cfg.get('tasks', {}).get(tid)
```

  (замість наявного `task = load_tasks().get('tasks', {}).get(tid)`; далі як було).

  У `task_new` після перевірки `task-exists`:

```python
    if task_trash.in_trash(cfg, tid):
        # Етап Д: id зайнятий записом кошика — нова задача з ним зробила б повернення неможливим.
        raise TaskRefused('task-in-trash', 'a task with this id is in the trash')
```

  І в блоці `try` перед `save_tasks(cfg)`:

```python
        task_trash.clear_tombstone(cfg, tid)       # «назавжди» знищену задачу заводять знову — надгробок більше не потрібен
```

- [ ] **Step 4: Зелені:** `python3 -B -m unittest discover -s tests` → `OK`. Окремо `test_tasks_overview` (форма `mine` не
  змінилась).

- [ ] **Step 5: Мутація.** Прибрати `in_trash` у `task_new` → `test_new_task_refuses…` червоний; повернути.

- [ ] **Step 6: Коміт** — `app/serve.py tests/test_task_crud.py`:
  `feat(0.30.0): кошик в екрані задач, кадр із кошика, id у кошику зайнятий`.

---

### Task 4: `bin/registry.py pull` пропускає кошик

**Files:**
- Modify: `bin/registry.py` (`_cmd_pull`, цикл `for tid, e in reg.items()`)
- Test: `bin/test_registry.py` (новий клас поруч із `TestPullSkipsFixtures`)

- [ ] **Step 1: Тест (червоний)**

```python
class TestPullSkipsTrash(_RegistrySandbox):
    """Етап Д: задача, видалена на цій машині (запис кошика чи надгробок), не воскресає з реєстру."""

    def _pull(self, registry):
        from unittest import mock
        with mock.patch.object(rg, 'read_registry', lambda d: dict(registry)), \
             mock.patch.object(rg, '_work_root', lambda cfg, profile: self.tmp):
            return self._quiet(rg.cmd_pull, None)

    def test_trashed_and_purged_ids_stay_gone(self):
        import json
        with open(self.file, encoding='utf-8') as f:
            cfg = json.load(f)
        cfg['tasks'].pop('courts')
        cfg['trash'] = {'courts': {'entry': dict(COURTS), 'dir': None, 'trashDir': None, 'at': '2026-11-17T10:00:00Z'},
                        'dead': {'purged': '2026-11-17T11:00:00Z'}}
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)
        self._pull({'courts': dict(COURTS, id='courts'), 'dead': dict(COURTS, id='dead', title='Dead')})
        with open(self.file, encoding='utf-8') as f:
            after = json.load(f)
        self.assertNotIn('courts', after['tasks'])
        self.assertNotIn('dead', after['tasks'])
        self.assertIn('courts', after['trash'], 'запис кошика мусить пережити pull')
```

  Звірити з `TestPullSkipsFixtures`: як фікстура кладе `COURTS` і чи `_quiet` повертає `(rc, out, err)`; підігнати.

- [ ] **Step 2: Червоний:** `cd bin && python3 -B -m unittest test_registry.TestPullSkipsTrash -v`.

- [ ] **Step 3: Реалізація.** На початку циклу в `_cmd_pull`, перед `local = tasks.get(tid)`:

```python
    # Етап Д: видалене на ЦІЙ машині (запис кошика чи надгробок «назавжди») реєстр не воскрешає — видалення локальне,
    # колеги задачу бачать і далі.
    trash = cfg.get('trash') if isinstance(cfg.get('trash'), dict) else {}
```

  (оголосити до циклу), а в циклі:

```python
        if tid not in tasks and tid in trash:
            continue
```

  Переконатись, що точковий запис стану (`_save_registry_state`) не губить `trash`: він пише в свіжо перечитаний конфіг. Тест
  це й стереже (`assertIn('courts', after['trash'])`).

- [ ] **Step 4: Зелені:** `python3 -B -m unittest discover -s bin -p 'test_*.py'` → `OK`.

- [ ] **Step 5: Мутація.** Прибрати `continue` → тест червоний.

- [ ] **Step 6: Коміт** — `bin/registry.py bin/test_registry.py`:
  `fix(0.30.0): registry pull не воскрешає задачі з кошика`.

---

### Task 5: Чиста розмітка екрана: картка «+», «⋯», поле назви, питання, кошик; меню

**Files:**
- Create: `app/task-menu.js`, `tests/task-menu.test.mjs`
- Modify:
  - `app/tasks-home.js`;
  - `app/space-dialogs.js` (`taskFormHTML({inline})`, `taskNameFormHTML`);
  - `app/spaces-model.js` (`taskFormError`, `TASK_ERR_KEYS`, `taskErrField`);
  - `app/i18n.js`, `app/styles.css`;
  - `tests/tasks-home.test.mjs`, тести `spaces-model`.

**Вхід розмітки.** `ui.edit` — тимчасовий стан екрана з `app.js`:

```js
/* ui.edit = { newForm: bool, ren: id|null, ask: {id, kind: 'del'|'purge', claude: bool}|null, trash: bool }
   Відсутній `ui.edit` = усе вимкнено (розмітка як без етапу Д, плюс картка «+» і «⋯»). */
```

`data.trash` — масив рядків кошика з `/api/tasks-overview` (може бути відсутнім → `[]`).

- [ ] **Step 1: i18n (uk/en).** Ключі поруч із `thTagsEdit` (uk) і їхні пари в `EN`:

```js
  thMenuAria: (key) => `Дії задачі ${key}`,
  thMenuTitle: 'Дії · Shift+F10',
  taskRename: 'Перейменувати',
  taskTagsMenu: 'Мітки…',
  taskPreviewOpen: 'Відкрити превʼю',
  taskDelete: 'Видалити',
  taskRestore: 'Повернути',
  taskPurge: 'Видалити назавжди',
  taskDelAsk: (title) => `Видалити «${title}»?`,
  taskDelAskClaude: (title) => `Claude працює в «${title}». Видалити?`,
  taskPurgeAsk: (title) => `Видалити назавжди «${title}»?`,
  taskDeleted: (title) => `Задачу «${title}» видалено`,
  taskRestored: (title) => `«${title}» повернуто`,
  taskPurged: (title) => `«${title}» видалено назавжди`,
  taskRestoreDirExists: 'Тека задачі вже існує — повернути не можна.',
  taskRestoreIdTaken: 'Задача з таким ідентифікатором уже є.',
  thTrash: (n) => `Кошик · ${n}`,
  thDeleted: (when) => `видалено ${when}`,
  taskRenamePal: 'Перейменувати задачу',
  taskNameSave: 'Зберегти',
  idInTrash: 'Такий ідентифікатор є в кошику.',
```

  EN:

```js
  thMenuAria: (key) => `Actions for ${key}`,
  thMenuTitle: 'Actions · Shift+F10',
  taskRename: 'Rename',
  taskTagsMenu: 'Tags…',
  taskPreviewOpen: 'Open preview',
  taskDelete: 'Delete',
  taskRestore: 'Restore',
  taskPurge: 'Delete forever',
  taskDelAsk: (title) => `Delete “${title}”?`,
  taskDelAskClaude: (title) => `Claude is working in “${title}”. Delete?`,
  taskPurgeAsk: (title) => `Delete “${title}” forever?`,
  taskDeleted: (title) => `Task “${title}” deleted`,
  taskRestored: (title) => `“${title}” restored`,
  taskPurged: (title) => `“${title}” deleted forever`,
  taskRestoreDirExists: 'The task folder already exists — cannot restore.',
  taskRestoreIdTaken: 'A task with this identifier already exists.',
  thTrash: (n) => `Trash · ${n}`,
  thDeleted: (when) => `deleted ${when}`,
  taskRenamePal: 'Rename task',
  taskNameSave: 'Save',
  idInTrash: 'This identifier is in the trash.',
```

  `spaceEmptyAgent`:
  - uk: `(name) => \`Створи першу або попроси агента: «створи задачу в просторі ${name}».\``;
  - en: `(name) => \`Create the first one or ask the agent: “create a task in the space ${name}”.\``.

  Якщо `taskNameSave` дублює наявний ключ «Зберегти» — взяти наявний, новий не заводити.

- [ ] **Step 2: Тести меню (червоні) — `tests/task-menu.test.mjs`**

```js
import assert from "node:assert/strict";
import test from "node:test";
import { setLang } from "../app/i18n.js";
import { taskMenuHTML, taskMenuItems } from "../app/task-menu.js";

setLang("uk");

test("меню «Моїх»: перейменувати, мітки, (превʼю), видалити — у цьому порядку; превʼю лише з http(s)", () => {
  const ths = (x) => taskMenuItems(x).filter((i) => i !== "sep").map((i) => i.th);
  assert.deepEqual(ths({ id: "a", published: null }), ["rename", "tags", "delete"]);
  assert.deepEqual(ths({ id: "a", published: "https://p.example/a" }), ["rename", "tags", "preview", "delete"]);
  assert.deepEqual(ths({ id: "a", published: "javascript:alert(1)" }), ["rename", "tags", "delete"]);
});

test("меню кошика: повернути, видалити назавжди", () => {
  assert.deepEqual(taskMenuItems({ id: "a" }, { trash: true }).filter((i) => i !== "sep").map((i) => i.th),
    ["restore", "purge"]);
});

test("розмітка: role=menu, пункти menuitem з data-th і data-id, клавіші, небезпечний пункт, id екрановано", () => {
  const h = taskMenuHTML({ id: 'x"><b>', published: "https://p.example/x" });
  assert.match(h, /^<div id="th-menu" class="cv-ctx th-menu" role="menu"/);
  assert.equal((h.match(/role="menuitem"/g) || []).length, 4);
  assert.match(h, /data-th="rename"[^>]*>.*F2/s);
  assert.match(h, /class="danger"[^>]*data-th="delete"|data-th="delete"[^>]*class="danger"/);
  assert.match(h, /<a [^>]*data-th="preview"[^>]*href="https:\/\/p\.example\/x"[^>]*target="_blank"/);
  assert.ok(!h.includes('"><b>'), "id мусить бути екранований");
});
```

- [ ] **Step 3: `app/task-menu.js`**

```js
/**
 * Меню картки задачі (етап Д, 0.30.0): «⋯» на кадрі, правий клік, Shift+F10. Чиста розмітка; відкриття, позиція
 * (`positionCtxMenu`), клавіші й дії — `app.js`. Пункти — `[data-th][data-id]`: клік ловить той самий обробник екрана
 * (`wireHome`), що й решту `data-th`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { safeUrl } from "./tasks-home.js";

/** Пункти меню: обʼєкти `{th, icon, key, kbd?, danger?, href?}` і `"sep"` (роздільник). */
export function taskMenuItems(x, { trash = false } = {}) {
  if (trash) {
    return [{ th: "restore", icon: "refresh", key: "taskRestore" }, "sep",
      { th: "purge", icon: "trash", key: "taskPurge", danger: true }];
  }
  const out = [{ th: "rename", icon: "pencil", key: "taskRename", kbd: "F2" },
    { th: "tags", icon: "sliders", key: "taskTagsMenu" }];
  const u = safeUrl(x.published);
  if (u) out.push({ th: "preview", icon: "ext", key: "taskPreviewOpen", href: u });
  out.push("sep", { th: "delete", icon: "trash", key: "taskDelete", kbd: "⌫", danger: true });
  return out;
}

export function taskMenuHTML(x, opts = {}) {
  const id = esc(x.id);
  const items = taskMenuItems(x, opts).map((i) => {
    if (i === "sep") return '<hr role="separator">';
    const kbd = i.kbd ? `<kbd>${esc(i.kbd)}</kbd>` : "";
    const cls = i.danger ? ' class="danger"' : "";
    const body = `${ico(i.icon, 15)}<span>${esc(t(i.key))}</span>${kbd}`;
    return i.href
      ? `<a role="menuitem" tabindex="-1"${cls} data-th="${i.th}" data-id="${id}" href="${esc(i.href)}" target="_blank" rel="noopener">${body}</a>`
      : `<button type="button" role="menuitem" tabindex="-1"${cls} data-th="${i.th}" data-id="${id}">${body}</button>`;
  }).join("");
  return `<div id="th-menu" class="cv-ctx th-menu" role="menu" aria-label="${esc(t("thMenuAria", x.id))}">${items}</div>`;
}
```

  ⛔ Порядок атрибутів у тесті розмітки — під реалізацію вище (`class` перед `data-th`). Регекс у тесті приймає обидва.

- [ ] **Step 4: `tasks-home.js` — тести (червоні), дописати в `tests/tasks-home.test.mjs`**

```js
const EDIT0 = { newForm: false, ren: null, ask: null, trash: false };
const ui0 = (o = {}) => ({ tab: "mine", q: "", sort: "recent", status: "all", tags: new Set(), designers: new Set(), now: NOW, edit: EDIT0, ...o });
const SPACE = { name: "Studio", capabilities: { dashboard: null } };
const dataStudio = (o = {}) => ({ current: "edr", mine: [A, B], team: null, space: SPACE, trash: [], ...o });

test("Д: картка «+» першою в сітці простору без дашборда; голова без «Нова задача»", () => {
  const h = homeHTML(ui0(), dataStudio());
  const grid = h.slice(h.indexOf('id="th-grid"'));
  assert.match(grid, /^id="th-grid"[^>]*><button class="th-card th-card--new" data-th="newtask"/);
  const head = h.slice(0, h.indexOf('class="th-tabs"'));
  assert.ok(!head.includes('data-th="newtask"'), "у голові «Нова задача» більше нема");
});

test("Д: у ЛІГА (є дашборд) картки «+» нема; на «Команді» теж", () => {
  const liga = { ...dataStudio(), space: { name: "ЛІГА", capabilities: { dashboard: "legacy" } }, team: { rows: [] } };
  assert.ok(!homeGridHTML(ui0(), liga).includes("th-card--new"));
});

test("Д: форма відкрита — слот форми на місці картки «+»", () => {
  const g = homeGridHTML(ui0({ edit: { ...EDIT0, newForm: true } }), dataStudio());
  assert.match(g, /<div class="th-card th-card--form" id="th-new-slot"><\/div>/);
  assert.ok(!g.includes("th-card--new"));
});

test("Д: «⋯» на кадрі кожної картки «Моїх», кнопки «Мітки» на картці нема", () => {
  const c = cardHTML(A, ui0(), "edr");
  assert.match(c, /<div class="th-thumb">.*<button class="th-more" data-th="menu" data-id="edr" aria-haspopup="menu" aria-expanded="false"/s);
  assert.ok(!c.includes('data-th="tags"'));
});

test("Д: перейменування — поле #th-ren зі значенням назви замість .th-ttl", () => {
  const c = cardHTML(A, ui0({ edit: { ...EDIT0, ren: "edr" } }), "edr");
  assert.match(c, /<input id="th-ren" class="th-ren"[^>]*value="LIGA-7019 · Очікування/);
  assert.ok(!c.includes('class="th-ttl"'));
});

test("Д: питання в картці — замість бейджів, без «⋯», картка не відкривається; Claude — інше питання", () => {
  const c = cardHTML(A, ui0({ edit: { ...EDIT0, ask: { id: "edr", kind: "del", claude: false } } }), "edr");
  assert.match(c, /class="th-card th-card--cur th-card--ask"/);
  assert.ok(!c.includes('data-th="open"') && !c.includes("th-more"));
  assert.match(c, /class="cfm"/);
  assert.match(c, /data-th="askno" data-id="edr"/);
  assert.match(c, /data-th="askyes" data-id="edr"/);
  const cc = cardHTML(A, ui0({ edit: { ...EDIT0, ask: { id: "edr", kind: "del", claude: true } } }), "edr");
  assert.match(cc, /Claude працює/);
});

test("Д: чип «Кошик · N» лише з непорожнім кошиком; вигляд кошика — картки --trash, «Повернути», без «+» і міток", () => {
  const T = { id: "old", title: "Стара", jira: null, tags: ["core"], at: "2026-11-17T09:00:00Z", thumb: null };
  assert.ok(!homeGridHTML(ui0(), dataStudio()).includes('data-th="trash"'));
  const g = homeGridHTML(ui0(), dataStudio({ trash: [T] }));
  assert.match(g, /<button class="th-chip" data-th="trash" aria-pressed="false">.*Кошик · 1/s);
  const v = homeGridHTML(ui0({ edit: { ...EDIT0, trash: true } }), dataStudio({ trash: [T] }));
  assert.match(v, /th-card th-card--trash/);
  assert.match(v, /data-th="restore" data-id="old"/);
  assert.ok(!v.includes("th-card--new"));
  assert.ok(!v.includes('data-th="tag"'));
  assert.match(v, /Показано 1 з 1/);
});

test("Д: усе з даних у кошику екрановано", () => {
  const T = { id: "x", title: "<img src=x onerror=1>", jira: null, tags: ["<b>"], at: "2026-11-17T09:00:00Z", thumb: "javascript:1" };
  const v = homeGridHTML(ui0({ edit: { ...EDIT0, trash: true } }), dataStudio({ trash: [T] }));
  assert.ok(!v.includes("<img src=x") && !v.includes("<b>") && !v.includes("javascript:"));
});
```

  Наявні тести, що шукали `data-th="tags"` на картці чи `newtask` у голові, — оновити під нову розмітку. Вони перевіряли
  наявність, тепер мусять перевіряти відсутність. Зміст переписати, а не видаляти мовчки.

- [ ] **Step 5: Реалізація `tasks-home.js`.**
  - **`actionHTML`** для «Моїх» лишає ЛИШЕ посилання превʼю: кнопку «Мітки» прибрати, вона тепер у меню.
  - **`cardHTML`** (для «Моїх», `!team`):
    - у `.th-thumb` після кадру — «⋯»;
    - `ui.edit?.ren === x.id` дає поле замість `.th-ttl`;
    - `ui.edit?.ask?.id === x.id` дає `confirmHTML` замість `.th-badges`, клас `th-card--ask`, `role="group"`, без
      `data-th="open"` і без «⋯».

```js
import { confirmHTML } from "./inline-confirm.js";
// …
  const edit = ui.edit || {};
  const asking = !team && edit.ask && edit.ask.id === x.id ? edit.ask : null;
  const more = team || asking ? ""
    : `<button class="th-more" data-th="menu" data-id="${esc(x.id)}" aria-haspopup="menu" aria-expanded="false"`
      + ` aria-label="${esc(t("thMenuAria", taskKey(x)))}" title="${esc(t("thMenuTitle"))}">${ico("dots")}</button>`;
  const ttl = !team && edit.ren === x.id
    ? `<input id="th-ren" class="th-ren" type="text" value="${esc(cleanTitle(x))}" aria-label="${esc(t("newTaskTitle"))}"`
      + ` autocomplete="off" spellcheck="false">`
    : `<div class="th-ttl">${mark(cleanTitle(x), q)}</div>`;
  const tail = asking
    ? confirmHTML({
      title: asking.claude ? t("taskDelAskClaude", cleanTitle(x)) : t("taskDelAsk", cleanTitle(x)),
      no: t("askCancel"), yes: t("taskDelete"),
      noAttrs: `data-th="askno" data-id="${esc(x.id)}"`, yesAttrs: `data-th="askyes" data-id="${esc(x.id)}"`,
    })
    : `<div class="th-badges">${status}${comments}${gone}${actionHTML(x, team)}</div>`;
```

    Клас картки: `th-card` + `th-card--cur?` + `th-card--miss?` + `th-card--ask?`. Роль: `asking ? "group" : (actionable ?
    "button" : "group")`. `data-th="open"` — лише `actionable && !asking`.

    ⛔ `.th-ttl` для поля перейменування бере `cleanTitle(x)` без `mark()` (у `value` розмітка не йде) і екранований `esc`.
  - **Картка кошика** — нова експортована `trashCardHTML(x, ui)`:

```js
/** Етап Д: картка задачі з кошика. Кадр знебарвлений (CSS), «видалено <коли>», «Повернути», «⋯» → меню кошика. */
export function trashCardHTML(x, ui) {
  const edit = ui.edit || {};
  const asking = edit.ask && edit.ask.id === x.id && edit.ask.kind === "purge";
  const src = safeThumb(x.thumb);
  const thumb = src ? `<img class="th-img" src="${esc(src)}" alt="" loading="lazy" draggable="false">`
    : `<div class="th-none">${ico("camera")}${esc(t("thNoShot"))}</div>`;
  const ms = Date.parse(x.at);
  const when = Number.isFinite(ms) ? (() => { const r = relTime(ms, ui.now); return t(r.key, r.n); })() : "";
  const meta = [esc((x.tags || []).join(", ")), when ? esc(t("thDeleted", when)) : ""].filter(Boolean).join(" · ");
  const more = asking ? "" : `<button class="th-more" data-th="menu" data-id="${esc(x.id)}" data-trash="1" aria-haspopup="menu"`
    + ` aria-expanded="false" aria-label="${esc(t("thMenuAria", x.id))}" title="${esc(t("thMenuTitle"))}">${ico("dots")}</button>`;
  const tail = asking
    ? confirmHTML({ title: t("taskPurgeAsk", x.title || x.id), no: t("askCancel"), yes: t("taskPurge"),
      noAttrs: `data-th="askno" data-id="${esc(x.id)}"`, yesAttrs: `data-th="askyes" data-id="${esc(x.id)}"` })
    : `<div class="th-badges"><button class="th-lnk" data-th="restore" data-id="${esc(x.id)}">${ico("refresh")}${esc(t("taskRestore"))}</button></div>`;
  return `<div class="th-card th-card--trash${asking ? " th-card--ask" : ""}" tabindex="0" role="group" data-id="${esc(x.id)}" data-trash="1">`
    + `<div class="th-thumb">${thumb}${more}</div><div class="th-cbody">`
    + `<div class="th-krow"><span class="th-key">${esc(x.id)}</span></div>`
    + `<div class="th-ttl">${esc(x.title || x.id)}</div><div class="th-meta">${meta}</div>${tail}</div></div>`;
}
```

  - **Картка «+» / слот** — новий експорт:

```js
/** Етап Д: «Нова задача» — перша клітинка сітки. Форма відкрита — порожній слот: живу `<form>` у нього вставляє `app.js`
 *  (поля переживають перемальовку сітки — набраного не губимо). */
export function newTaskCardHTML(ui) {
  return ui.edit?.newForm
    ? '<div class="th-card th-card--form" id="th-new-slot"></div>'
    : `<button class="th-card th-card--new" data-th="newtask" aria-label="${esc(t("newTask"))}">`
      + `<span class="th-new-ic">${ico("plus", 20)}</span><span>${esc(t("newTask"))}</span></button>`;
}
```

  - **`homeGridHTML`.**
    - Вигляд кошика `inTrash = !team && !!ui.edit?.trash && (data.trash || []).length > 0`.
    - Список — `data.trash` (картки `trashCardHTML`), інакше як було.
    - Перед картками «Моїх» — `newTaskCardHTML(ui)`, коли `!team && noDashboard(data) && !inTrash`.
    - Порожній простір без дашборда: сітка з карткою «+» і ПІД сіткою `th-empty--space` з `spaceEmpty` /
      `spaceEmptyAgent` (без кнопки). `.th-empty` у сітці лишається для звичайної порожньої видачі.
  - **`chipsHTML`.**
    - Статусні чипи `aria-pressed` — `false`, коли `inTrash`.
    - Чипи міток/дизайнерів — сховані, коли `inTrash`.
    - Після них — чип кошика, коли `(data.trash || []).length`:

```js
  const trashN = team ? 0 : (data.trash || []).length;
  const trashChip = trashN ? `<span class="th-gap"></span><button class="th-chip${inTrash ? " th-chip--on" : ""}" data-th="trash"`
    + ` aria-pressed="${inTrash}">${ico("trash")}${esc(t("thTrash", trashN))}</button>` : "";
```

    - Лічильник у вигляді кошика — `thShown(n, n)`.
  - **`homeHTML`:** голова — завжди `h1` для простору з дашбордом. Для простору без дашборда — `th-head` лише з `connBtn()`
    (без `newTaskBtn()`). Функцію `newTaskBtn` прибрати, якщо більше ніде не вживається.

- [ ] **Step 6: `space-dialogs.js`.**
  - `taskFormHTML({ …, inline = false })`. Inline дає `<form class="cv-form th-nf" data-form="task" novalidate
    aria-label="${esc(t("newTask"))}">` без `role="dialog"`, `aria-modal` і `<h2>`; поля, слот помилки й `buttons("taskCreate")`
    ті самі.
  - Нова функція:

```js
/** Етап Д: поповер «Перейменувати задачу» під вкладкою: одне поле `#tn-title` (`name="title"`), слот помилки, «Скасувати · Зберегти». */
export function taskNameFormHTML({ title = "" } = {}) {
  return `<form class="cv-form" data-form="taskname" novalidate role="dialog" aria-label="${esc(t("taskRenamePal"))}">
    <div class="cv-field">
      <label for="tn-title">${esc(t("newTaskTitle"))}</label>
      <input id="tn-title" name="title" type="text" value="${esc(title)}" maxlength="200" autocomplete="off"
        spellcheck="false" aria-describedby="${ERR_ID}" data-autofocus>
    </div>
    ${errorSlot("")}
    ${buttons("taskNameSave")}
  </form>`;
}
```

  Гачки — у шапку модуля (список «Стабільні гачки»): `form[data-form="taskname"]`, `#tn-title`.

- [ ] **Step 7: `spaces-model.js`.**
  - `taskFormError({title, id}, taken = [], trash = [])`: після `idTaken` — `if (lowerSet(trash).has(id.toLowerCase()))
    return "idInTrash";`.
  - `TASK_ERR_KEYS`: `["task-in-trash", "idInTrash"]`.
  - `taskErrField`: `idInTrash` → `"id"`.
  - Тест у наявному файлі тестів `spaces-model` (знайти `grep -l taskFormError tests/*.mjs`): `idInTrash` для id з кошика;
    `taskErrKey("task-in-trash") === "idInTrash"`; поле `id`.

- [ ] **Step 8: CSS (`styles.css`, після блока `.th-*`).** Значення — з прототипу, кольори лише токенами:

```css
/* Етап Д (0.30.0): картка «Нова задача» — перша клітинка сітки; форма на її місці. */
.th-card--new{border-style:dashed;border-color:var(--line2);background:none;color:var(--mid);align-items:center;
  justify-content:center;gap:8px;min-height:220px;font:inherit}
.th-card--new:hover{border-color:var(--mid);color:var(--hi);background:color-mix(in srgb,var(--s2) 50%,transparent)}
.th-new-ic{display:grid;place-items:center;width:40px;height:40px;border-radius:50%;background:var(--s3)}
.th-card--new:hover .th-new-ic{background:var(--s4)}
.th-card--form{cursor:default;border-color:var(--sel)}
.th-card--form:hover{transform:none;border-color:var(--sel)}
.th-nf{display:flex;flex-direction:column;gap:10px;padding:14px 12px 12px;flex:1}
.th-nf .cv-field{display:flex;flex-direction:column;gap:4px}
.th-nf label{font-size:12px;color:var(--dim)}
.th-nf input{height:var(--h-ctl);padding:0 10px;border:1px solid var(--line2);border-radius:var(--r-sm);background:var(--s1);
  color:var(--hi);font:inherit;outline:0;min-width:0}
.th-nf input:focus{border-color:var(--sel)}
.th-nf input[aria-invalid="true"]{border-color:var(--bad)}
.th-nf #tf-id{font-family:var(--mono);font-size:12px}
.th-nf .cv-form-err{margin:0;font-size:12px;color:var(--bad)}
.th-nf .cv-ask-row{display:flex;justify-content:flex-end;gap:8px;margin-top:auto}
.th-nf .cv-ask-row button{height:var(--h-ctl);padding:0 14px;border-radius:var(--r-sm);border:1px solid var(--line2);
  background:var(--s3);color:var(--hi);font:inherit;cursor:pointer}
.th-nf .cv-ask-row button[data-a="ok"]{background:var(--sel);border-color:var(--sel);color:var(--on-sel);font-weight:500}
/* «⋯» на кадрі: під мишею, у фокусі картки й поки меню відкрите; на сенсорних — завжди. */
.th-more{position:absolute;top:8px;right:8px;display:grid;place-items:center;width:var(--h-sm);height:var(--h-sm);border:0;
  border-radius:var(--r-sm);background:color-mix(in srgb,var(--s0) 86%,transparent);color:var(--hi);cursor:pointer;opacity:0;
  transition:opacity var(--dur) var(--ease)}
.th-card:hover .th-more,.th-card:focus-within .th-more,.th-more[aria-expanded="true"]{opacity:1}
.th-more:hover{background:var(--s0)}
.th-more:focus-visible{outline:2px solid var(--sel);outline-offset:1px}
@media (hover:none){.th-more{opacity:1}}
.th-ren{width:100%;height:var(--h-sm);margin:-3px 0;padding:0 6px;border:1px solid var(--sel);border-radius:var(--r-sm);
  background:var(--s1);color:var(--hi);font:inherit;font-weight:500;outline:0}
.th-card--ask{cursor:default;border-color:color-mix(in srgb,var(--bad) 55%,var(--line))}
.th-card--ask:hover{transform:none}
.th-card--ask .cfm{margin-top:auto}
.th-card--trash .th-img,.th-card--trash .th-none{filter:grayscale(1) brightness(.55)}
.th-card--trash{cursor:default}
.th-card--trash .th-ttl{color:var(--mid)}
.th-chip .ico{width:13px;height:13px}
.th-menu kbd{margin-left:auto;font:11px var(--ui, inherit);color:var(--dim)}
.th-menu button,.th-menu a{display:flex;align-items:center;gap:9px;text-decoration:none}
.th-menu .ico{color:var(--mid)}
.th-menu .danger,.th-menu .danger .ico{color:var(--bad)}
.th-menu hr{border:0;border-top:1px solid var(--line);margin:4px 2px}
.th-empty--below{grid-column:1/-1}
```

  Звірити з `tests/css-guards.test.mjs` і `tests/dialogs-css.test.mjs`. Кожен клас мусить мати повний літерал у JS (так у
  розмітці вище), висоти — лише токени. Якщо `--ui` не токен у `styles.css`, взяти наявний шрифтовий токен.

- [ ] **Step 9: Зелені:** `node --test tests/*.test.mjs` → усі `pass`, включно з `i18n-keys`, `i18n-literals`, `css-guards`,
  `js-parses`. Python не зачеплено.

- [ ] **Step 10: Коміт.** Файли: `app/task-menu.js app/tasks-home.js app/space-dialogs.js app/spaces-model.js app/i18n.js
  app/styles.css tests/task-menu.test.mjs tests/tasks-home.test.mjs` і змінені тести `spaces-model`. Повідомлення:
  `feat(0.30.0): розмітка дій задачі — картка «+», меню, перейменування, питання, кошик`.

  ⚠ Після цієї задачі екран у живому браузері ще не проведений: «Мітки» з картки зникли, а меню відкривається лише з
  Task 7. Живі `tasks-home` (мітки 3/5) червоні до Task 7 — очікувано. Записати в звіт.

---

### Task 6: Інлайн-форма «Нова задача» (проводка)

**Files:**
- Modify: `app/ask.js` (винести `makeFormCtl`), `app/app.js` (`newTaskDialog` → `createTask` + інлайн-картка, клавіші)
- Test: `tests/ask-form.test.mjs` (дописати), `tests/live/tasks-crud.test.mjs` (новий), `tests/live/tasks-home.test.mjs`
  («мітки 4»)

- [ ] **Step 1: `ask.js` — `makeFormCtl(formEl)`.** Обʼєкт `ctl` з `overlay` (рядки ~293–321: `form`, `error`, `focus`, `busy`)
  винести в експортовану функцію без зміни поведінки; `overlay` кличе її. Юніт у `tests/ask-form.test.mjs` (на фейковому
  DOM, як сусідні тести файла; якщо файл працює з `linkedom`/власним стабом — тим самим):
  - `error("x")` показує слот;
  - `error("")` ховає слот і знімає `aria-invalid`;
  - `focus("title")` ставить `aria-invalid`;
  - `busy(true)` вимикає `button[data-a="ok"]` і ставить `aria-busy`.

- [ ] **Step 2: `app.js` — `createTask(vals, ctl, ctx)`.** Тіло `onSubmit` з `newTaskDialog` винести в
  `async function createTask(vals, ctl, { sp, withRepo, taken, trashIds })`, що повертає текст помилки чи `undefined`,
  дослівно, з двома змінами:
  - перевірка — `taskFormError(vals, await taken, trashIds)`;
  - карта помилок сервера вже знає `task-in-trash`, бо це зробив Task 5.

  `newTaskDialog` лишається: його кличуть майстер і ⌘K, якщо такі виклики є (знайти `grep -n "newTaskDialog(" app/*.js`). Він
  кличе `createTask`. Якщо викликів поза екраном нема — `newTaskDialog` прибрати й записати це у звіт.

- [ ] **Step 3: Стан екрана й інлайн-форма.** Поруч з `homeUi`:

```js
/* Етап Д: тимчасовий стан екрана «Задачі» — НЕ зберігається (`homeUi` пишеться в localStorage, це — ні). Скидається
   на вході на екран і на зміні простору. `newForm`: відкрита форма «Нова задача» (жива `<form>` — `newFormEl`);
   `ren`: id задачі, назву якої правлять на картці; `ask`: питання в картці `{id, kind, claude}`; `trash`: вигляд кошика. */
let homeEdit = { newForm: false, ren: null, ask: null, trash: false };
let newFormEl = null;
let newFormCtx = null;
const resetHomeEdit = () => { homeEdit = { newForm: false, ren: null, ask: null, trash: false }; newFormEl = null; newFormCtx = null; };
```

  - `homeView()` додає `edit: homeEdit`.
  - `enterHome` і місця, що скидають простір (`resetSpaceState`), кличуть `resetHomeEdit()`.

  Монтування після кожної перемальовки (кінець `paintHome` і `paintHomeLower`, усередині `keepFocus`-колбека):

```js
/** Жива форма «Нова задача» — у свій слот після перемальовки сітки: поля й набране переживають `innerHTML` сітки. */
function mountNewForm() {
  const slot = document.getElementById('th-new-slot');
  if (slot && newFormEl && newFormEl.parentNode !== slot) slot.appendChild(newFormEl);
}
```

  Відкриття і закриття:

```js
async function openNewTaskCard() {
  const sp = spaceNow();
  if (!sp || homeEdit.newForm) return;
  const withRepo = hasVcs(sp) && !isLegacyVcs(sp);
  const taken = formApi('/api/tasks?all=1').then((r) => (r.tasks || []).map((x) => x.id)).catch(() => []);
  const trashIds = (homeData?.trash || []).map((x) => x.id);
  const tpl = document.createElement('template');
  tpl.innerHTML = taskFormHTML({ inline: true, tags: true, ...(withRepo ? { repo: {} } : {}) }).trim();
  newFormEl = tpl.content.firstChild;
  newFormCtx = { sp, withRepo, taken, trashIds };
  wireTaskForm(newFormEl, { taken: taken.then((ids) => [...ids, ...trashIds]) });
  const ctl = makeFormCtl(newFormEl);
  let busy = false;
  newFormEl.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (busy) return;
    busy = true; ctl.busy(true); ctl.error('');
    try {
      const msg = await createTask(formValues([...newFormEl.elements]), ctl, newFormCtx);
      if (msg) ctl.error(msg); else resetHomeEdit();
    } finally { busy = false; if (newFormEl) ctl.busy(false); }
  });
  newFormEl.addEventListener('click', (ev) => { if (ev.target.closest('[data-a="cancel"]') && !busy) closeNewTaskCard(); });
  homeEdit = { ...homeEdit, newForm: true, ask: null, ren: null };
  paintHomeLower();
  newFormEl.querySelector('#tf-title')?.focus({ preventScroll: false });
  /* Підказка репо (як у діалозі) — коли приїде. */
}

function closeNewTaskCard() {
  resetHomeEdit();   // newForm:false, ren/ask теж скинуто — їх під час форми нема
  paintHomeLower();
  homeNode()?.querySelector('[data-th="newtask"]')?.focus({ preventScroll: true });
}
```

  Підказку репо (`repoHint`) перенести з `newTaskDialog` у спільний помічник і викликати і там, і тут. `formValues` —
  імпорт з `ask.js` (експорт уже є). Під час відправки `createTask` лишає задачу поточною й кличе `leaveHome()` (як було);
  `resetHomeEdit()` після успіху — щоб наступний вхід на екран почався без форми.

  Відкриття картки «+» мусить вести сюди: у `wireHome` — `case 'newtask': openNewTaskCard(); break;`.

- [ ] **Step 4: Клавіші.** У обробнику клавіш екрана (≈4214):
  - Esc у формі, коли не `busy`, — `closeNewTaskCard()`. Перевіряти до гілки `typing` і повертатись. Esc під час клону
    нічого не робить: `aria-busy` на формі.
  - Enter у пошуку відкриває першу картку з `data-th === 'open'` (`homeCards().find(…)`), а не просто першу.
  - Enter і Пробіл на картці `data-th="newtask"` — `openNewTaskCard()`. Зараз гілка `Enter` робить `preventDefault` для всіх
    `.th-card` і нативний клік кнопки не стався б.
  - `homeCards()` повертає й `.th-card--new`, тож стрілки ходять по ній.

- [ ] **Step 5: Живі тести — новий `tests/live/tasks-crud.test.mjs`.**
  - Простір без дашборда — через `startServer(..., { spaces: … })` чи `_spaces-kit.mjs`, як у `tests/live/spaces*.test.mjs`
    («звичайний простір»).
  - Власний `PORT_BASE` (вільний діапазон: `grep -h "PORT_BASE = " tests/live/*.mjs`, взяти незайнятий; `live-ports` це
    стереже).
  - Тести:

```js
test("нова задача карткою: клік → форма на місці, id за назвою, Enter створює й відкриває; tasks.json має задачу", async (t) => { … });
test("нова задача карткою: Esc і «Скасувати» вертають картку «+» з фокусом; набране в формі переживає клік по чипу статусу", async (t) => { … });
test("нова задача карткою: id із кошика — помилка під полем id, запиту нема", async (t) => { … });   // кошик: заздалегідь видалити задачу через API
test("клавіатура: стрілки ходять і по картці «+», Enter на ній відкриває форму; Enter у пошуку відкриває першу ЗАДАЧУ", async (t) => { … });
```

  Кожен тест — повністю: дані фікстури, кроки, перевірки DOM, `tasks.json` і мережі (`page.on('request')` для «запиту нема»).
  Зразок проводки — `tests/live/tasks-home.test.mjs` («мітки 4»).

  `tests/live/tasks-home.test.mjs` «мітки 4»: картка `[data-th="newtask"]` тепер у сітці, а форма — інлайн
  (`form[data-form="task"]` у `#th-grid`, а не в `.cv-ask`). Селектори підігнати, суть тесту не міняти.

- [ ] **Step 6: Прогони.**
  - `node --test tests/*.test.mjs` → pass.
  - По одному: `tests/live/tasks-crud.test.mjs`, `tests/live/tasks-home.test.mjs` (очікувано червоні лише «мітки 3/5»),
    `tests/live/spaces*.test.mjs`, `tests/live/wizard*.test.mjs` — зелені, бо гачки форми ті самі.

- [ ] **Step 7: Мутація.** Прибрати `mountNewForm()` з `paintHomeLower` → тест «набране переживає клік по чипу» червоний.

- [ ] **Step 8: Коміт.** Файли: `app/ask.js app/app.js tests/ask-form.test.mjs tests/live/tasks-crud.test.mjs
  tests/live/tasks-home.test.mjs`. Повідомлення: `feat(0.30.0): «Нова задача» — форма на місці картки в сітці`.

---

### Task 7: Меню картки, «Мітки» з меню, перейменування на картці

**Files:**
- Modify: `app/app.js`
- Test: `tests/live/tasks-crud.test.mjs` (дописати), `tests/live/tasks-home.test.mjs` (мітки 3/5 → через меню)

- [ ] **Step 1: Меню.**

```js
/** Меню картки (етап Д). `at` — `{x, y}` (правий клік) або `null` (під «⋯»). Вузол — у `#tasks-home`: його кліки ловить
 *  `wireHome` (`data-th`). Перемальовка екрана меню прибирає (воно не в розмітці стану) — кнопка `aria-expanded` тоді хибна сама. */
function openTaskMenu(id, { trash = false, at = null } = {}) {
  closeTaskMenu(false);
  const home = homeNode();
  const x = trash ? (homeData?.trash || []).find((y) => y.id === id) : (homeData?.mine || []).find((y) => y.id === id);
  if (!home || !x) return;
  const tpl = document.createElement('template');
  tpl.innerHTML = taskMenuHTML(x, { trash }).trim();
  const m = tpl.content.firstChild;
  m.style.position = 'fixed';
  home.appendChild(m);
  const btn = home.querySelector(`.th-more[data-id="${CSS.escape(id)}"]`);
  const r = btn?.getBoundingClientRect();
  positionCtxMenu(m, at ?? { x: r ? r.right - m.offsetWidth : 0, y: r ? r.bottom + 4 : 0 });
  btn?.setAttribute('aria-expanded', 'true');
  m.dataset.for = id;
  m.querySelector('[role="menuitem"]')?.focus({ preventScroll: true });
}

function closeTaskMenu(refocus = true) {
  const m = document.getElementById('th-menu');
  if (!m) return;
  const id = m.dataset.for;
  m.remove();
  const btn = homeNode()?.querySelector(`.th-more[data-id="${CSS.escape(id)}"]`);
  btn?.setAttribute('aria-expanded', 'false');
  if (refocus) btn?.focus({ preventScroll: true });
}
```

  Проводка:
  - **`wireHome`, клік.**
    - `case 'menu'`: тогл. Відкрите для цієї ж картки — закрити, інакше `openTaskMenu(id, { trash: b.dataset.trash === '1' })`.
    - Будь-який клік по пункту меню спершу закриває меню (`closeTaskMenu(false)`), потім дія.
    - Клік поза меню (і поза «⋯») закриває його без повернення фокуса: на початку обробника кліку, до `closest('[data-th]')`.
  - **`contextmenu` на `#tasks-home`.** На `.th-card[data-id]` (не `--ask`, не `--new`): `preventDefault()` і
    `openTaskMenu(id, { trash: card.dataset.trash === '1', at: { x: ev.clientX, y: ev.clientY } })`.
  - **Клавіші в обробнику екрана.**
    - Меню відкрите: ↑/↓ ходять по `[role=menuitem]` по колу, Esc → `closeTaskMenu()`, Tab закриває.
    - На картці: `Shift+F10` і `ContextMenu` відкривають меню під «⋯». ⛔ Перевірка `ev.metaKey || ev.ctrlKey || ev.altKey` вище
      Shift пропускає — переконатись, що гілка стоїть після неї правильно.
    - Esc на екрані з відкритим меню не мусить робити інших дій екрана.

- [ ] **Step 2: Дії меню в `wireHome`.**
  - `case 'tags': editTaskTags(b.dataset.id)`. Фокус після діалогу вертається на «⋯» картки: у `editTaskTags.focusBack` →
    `.th-more[data-id=…]`.
  - `case 'preview'` — посилання; `wireHome` уже пропускає `a`: перед `if (ev.target.closest('a')) return;` закрити меню.
  - `case 'rename': startRenameCard(id)`.

- [ ] **Step 3: Перейменування на картці.**

```js
function startRenameCard(id) {
  if (!(homeData?.mine || []).some((y) => y.id === id)) return;
  homeEdit = { ...homeEdit, ren: id, ask: null };
  paintHomeLower();
  const inp = document.getElementById('th-ren');
  inp?.focus({ preventScroll: true }); inp?.select();
}

let renSaving = false;
async function commitRenameCard(save) {
  const id = homeEdit.ren;
  if (!id || renSaving) return;
  const inp = document.getElementById('th-ren');
  const row = (homeData?.mine || []).find((y) => y.id === id);
  const next = (inp?.value ?? '').trim();
  homeEdit = { ...homeEdit, ren: null };
  const focusCard = () => homeNode()?.querySelector(`.th-card[data-id="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
  if (!save || !row || !next || next === cleanTitle(row)) { paintHomeLower(); focusCard(); return; }
  renSaving = true;
  try {
    const r = await postForm('/api/task-rename', { id, title: next });
    applyTaskTitle(id, r.title);
  } catch (e) { toast(t('errFailed', requestErrText(e))); }
  finally { renSaving = false; }
  paintHomeLower(); focusCard();
}

/** Нова назва — всюди, де її показують: рядок екрана, запис вкладки (підказка), поточна задача. */
function applyTaskTitle(id, title) {
  if (homeReady()) homeData = { ...homeData, mine: homeData.mine.map((y) => (y.id === id ? { ...y, title } : y)) };
  if (tabs.some((x) => x.id === id)) { tabs = tabs.map((x) => (x.id === id ? { ...x, title } : x)); saveTabs(); paintTabs(); }
  if (curTask && currentTaskId === id) curTask = { ...curTask, title };
}
```

  `curTask` — відповідь `/api/task` (поля `id`, `jira`, `title`, `space`; app.js:1220), тож оновлюємо його `title` на місці.

  Проводка:
  - **Клавіші.** Enter у `#th-ren` → `commitRenameCard(true)`; Esc → `commitRenameCard(false)`. Обидві — до гілки `typing`
    обробника, з `preventDefault`.
  - **Втрата фокуса.** `focusout` на `#tasks-home`: ціль `#th-ren` і `homeEdit.ren` → `setTimeout(() => commitRenameCard(true))`.
    Подвійного запису не буде: `ren` скидається першим рядком.
  - **F2** на сфокусованій `.th-card[data-th="open"]` (не кошик) → `startRenameCard(id)`.
  - **Клік поза полем** під час перейменування комітить, але НЕ відкриває картку. Порядок: на початку обробника кліку
    `if (homeEdit.ren && !ev.target.closest('#th-ren')) { commitRenameCard(true); return; }`.

- [ ] **Step 4: Живі тести (дописати в `tasks-crud`):**

```js
test("меню: «⋯» відкриває з фокусом на першому пункті; ↓/↑ по колу; Esc закриває й вертає фокус на «⋯»; клік повз — закриває", …);
test("меню: правий клік по картці — меню в точці кліку; Shift+F10 на картці — меню під «⋯»", …);
test("меню → «Мітки…» відкриває діалог міток (задача НЕ відкривається); Esc — фокус на «⋯» картки", …);
test("перейменування на картці: F2 → поле з виділеною назвою; Enter → tasks.json title, id і тека ті самі, підказка вкладки нова", …);
test("перейменування на картці: Esc — без запиту; порожнє — без запиту; втрата фокуса — зберігає", …);
```

  `tests/live/tasks-home.test.mjs` «мітки 3», «мітки 5»: замість кнопки на картці — «⋯» → «Мітки…» (клавіатурою — Shift+F10 →
  ↓ → Enter). Перевірки результату ті самі.

- [ ] **Step 5: Прогони.** JS-юніти; живі `tasks-crud`, `tasks-home` (тепер усі зелені), `tabs`.

- [ ] **Step 6: Мутація.** Прибрати `return` після коміту при кліку поза полем → живий тест «втрата фокуса» чи новий
  «клік по іншій картці під час перейменування не відкриває її» червоний. Додати цей тест, якщо мутація вижила.

- [ ] **Step 7: Коміт.** Файли: `app/app.js tests/live/tasks-crud.test.mjs tests/live/tasks-home.test.mjs`. Повідомлення:
  `feat(0.30.0): меню картки задачі й перейменування на місці`.

---

### Task 8: Видалення з питанням у картці, тост «Повернути»

**Files:**
- Modify: `app/app.js` (`toast` з дією, видалення, повернення)
- Test: `tests/live/tasks-crud.test.mjs`

- [ ] **Step 1: Тост із дією.** `toast(msg, { action, ms } = {})`:
  - без `action` — як зараз;
  - з `action` (`{label, run}`) — текст у `span.msg`, кнопка `button[data-act="undo"]`, клас `has-act`, `ms` (типово 8000);
  - клік по кнопці кличе `run()` і ховає тост.

  CSS:

```css
/* Етап Д: тост із дією («Повернути»): клікабельний, текст і кнопка в ряд. Без дії — як був (pointer-events:none). */
.cv-toast.has-act{display:flex;align-items:center;gap:12px;padding:8px 8px 8px 16px}
.cv-toast.has-act.show{pointer-events:auto}
.cv-toast .msg{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cv-toast [data-act="undo"]{flex:none;height:var(--h-sm);padding:0 10px;border-radius:var(--r-sm);border:1px solid var(--line2);
  background:var(--s3);color:var(--hi);font:inherit;font-weight:500;cursor:pointer}
.cv-toast [data-act="undo"]:hover{background:var(--s4)}
```

  Наступний `toast()` без дії замінює тост із дією: кнопка зникає, «Повернути» втрачається. Це прийнятно і так само у
  прототипі.

- [ ] **Step 2: Питання.**

```js
/** Стан Claude «працює» для задачі (id чи Jira-ключ) з останнього опиту вкладок (`claudeAll`); нема даних — ні. */
const claudeWorkingOn = (row) => {
  const v = claudeAll && (claudeAll[row.id] || (row.jira && claudeAll[row.jira]));
  return !!v && v.state === 'working';
};

function askDeleteCard(id, kind = 'del') {
  const row = kind === 'purge' ? (homeData?.trash || []).find((y) => y.id === id) : (homeData?.mine || []).find((y) => y.id === id);
  if (!row) return;
  closeTaskMenu(false);
  homeEdit = { ...homeEdit, ask: { id, kind, claude: kind === 'del' && claudeWorkingOn(row) }, ren: null };
  paintHomeLower();
  homeNode()?.querySelector(`.th-card[data-id="${CSS.escape(id)}"] .cfm-no`)?.focus({ preventScroll: true });
}

function cancelAsk() {
  const id = homeEdit.ask?.id;
  homeEdit = { ...homeEdit, ask: null };
  paintHomeLower();
  if (id) homeNode()?.querySelector(`.th-card[data-id="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
}
```

  `claudeAll` — `{ключ: {state}}` з `/api/claude-statuses`, ключ — id чи Jira-ключ, `state` ∈ `working|waiting|blocked|done`
  (той самий пошук, що `tabsModel.stateOf`, app/tabs-model.js:82).

  Проводка:
  - `wireHome`: `delete` → `askDeleteCard(id)`; `askno` → `cancelAsk()`; `askyes` →
    `homeEdit.ask.kind === 'purge' ? purgeFromTrash(id) : deleteTask(id)`.
  - Клавіші на `.th-card[data-th="open"]`: `Delete` чи `Backspace` → `askDeleteCard(id)`. Esc, коли `homeEdit.ask`, →
    `cancelAsk()`.
  - Клік поза карткою з питанням → `cancelAsk()` без інших дій. Порядок: на початку обробника кліку, як для `ren`.

- [ ] **Step 3: Видалення й повернення.**

```js
async function deleteTask(id) {
  const row = (homeData?.mine || []).find((y) => y.id === id);
  if (!row) return;
  const spaceId = homeData?.space?.id ?? spaceNow()?.id ?? null;
  homeEdit = { ...homeEdit, ask: null };
  let r;
  try { r = await postForm('/api/task-delete', { id }); }
  catch (e) { paintHomeLower(); toast(t('errFailed', requestErrText(e))); return; }
  const at = tabs.findIndex((x) => x.id === id);
  const tabRec = at >= 0 ? tabs[at] : null;
  if (tabRec) { tabs = tabs.filter((x) => x.id !== id); saveTabs(); }
  if (id === currentTaskId) {
    await resetPerTaskState();
    currentTaskId = r.current ?? null;
    taskSwitchGen += 1;
  }
  homeData = { ...homeData, current: r.current ?? null, mine: homeData.mine.filter((y) => y.id !== id),
    trash: [{ id, title: cleanTitle(row), jira: row.jira ?? null, tags: row.tags || [], at: r.trash?.at ?? null, thumb: null },
      ...(homeData.trash || [])] };
  paintTabs(); paintHome();
  (homeCards().find((c) => c.dataset.th === 'open') ?? homeNode()?.querySelector('[data-th="newtask"]'))?.focus({ preventScroll: true });
  toast(t('taskDeleted', cleanTitle(row)), { action: { label: t('taskRestore'), run: () => restoreTask(id, { spaceId, tabRec, at, title: cleanTitle(row) }) } });
  loadHome();      // свіжі дані (кадр кошика, current)
}

async function restoreTask(id, { spaceId, tabRec = null, at = -1, title = id } = {}) {
  try { await postForm('/api/task-restore', { id, space: spaceId }); }
  catch (e) {
    const key = e.code === 'task-dir-exists' ? 'taskRestoreDirExists' : e.code === 'task-exists' ? 'taskRestoreIdTaken' : null;
    toast(key ? t(key) : t('errFailed', requestErrText(e)));
    return;
  }
  if (tabRec && !tabs.some((x) => x.id === id)) {
    tabs = [...tabs.slice(0, Math.max(0, at)), tabRec, ...tabs.slice(Math.max(0, at))];
    saveTabs(); paintTabs();
  }
  if (homeReady() && (homeData.trash || []).length <= 1) homeEdit = { ...homeEdit, trash: false };
  await loadHome();
  homeNode()?.querySelector(`.th-card[data-id="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
  if (!tabRec) toast(t('taskRestored', title));
}
```

  ⛔ Звірити:
  - `resetPerTaskState` / `taskSwitchGen` / `currentTaskId` — та сама послідовність, що в успіху `createTask`.
  - `loadHome()` повертає проміс; з відкритим екраном він перемальовує екран.
  - Простір після видалення поточної не змінюється, тож `resetSpaceState` не потрібен.
  - Вихід з екрана без поточної задачі (`currentTaskId === null`) іде наявним шляхом `showNoTask`. Перевірити живим тестом
    «видалено єдину задачу → логотип/вихід → екран "нема задачі"», якщо такий шлях досяжний: вкладок нема, тож вийти можна
    лише через вкладку; інакше тест не потрібен.

- [ ] **Step 4: Живі тести:**

```js
test("видалення: Delete на картці → питання в картці з фокусом на «Скасувати»; Esc — питання зникає, нічого не видалено", …);
test("видалення неактивної: «Видалити» → картки нема, її вкладка закрита, тека в .deai-trash, tasks.json.trash має запис; тост із «Повернути»", …);
test("«Повернути» з тосту: задача, тека й вкладка на своїх місцях; поточна не змінилась", …);
test("видалення ПОТОЧНОЇ: «відкрита зараз» переходить на ту, що назвав сервер; екран лишається відкритим", …);
test("питання «Claude працює»: удар /api/claude-status in_progress для задачі → питання інше", …);   // POST з origin застосунку через page.evaluate(fetch)
test("видалення не вдалось (сервер 500 через заблоковану теку): картка лишається, тост із причиною", …);   // напр. chmod теки-батька 0o555 у фікстурі, відновити в t.after
```

- [ ] **Step 5: Прогони.** JS-юніти; живі `tasks-crud`, `tasks-home`, `tabs`.

- [ ] **Step 6: Мутація.** Прибрати повернення вкладки в `restoreTask` → тест «Повернути з тосту» червоний.

- [ ] **Step 7: Коміт** — `app/app.js app/styles.css tests/live/tasks-crud.test.mjs`:
  `feat(0.30.0): видалення задачі з питанням у картці й «Повернути» в тості`.

---

### Task 9: Вигляд кошика: повернути, видалити назавжди

**Files:**
- Modify: `app/app.js`
- Test: `tests/live/tasks-crud.test.mjs`

- [ ] **Step 1: Проводка.** У `wireHome`:
  - **`case 'trash'`.** `homeEdit = { ...homeEdit, trash: !homeEdit.trash, newForm: false, ask: null, ren: null };
    newFormEl = null; paintHomeLower();`. Відкриту форму «+» закриваємо: її в кошику нема.
  - **`case 'status'`.** Додатково `homeEdit = { ...homeEdit, trash: false }` перед перемальовкою.
  - **`case 'restore'`.**
    `restoreTask(id, { spaceId: homeData?.space?.id, title: (homeData.trash||[]).find(y=>y.id===id)?.title ?? id })`.
  - **`case 'purge'`.** `askDeleteCard(id, 'purge')`.
  - **`purgeFromTrash`:**

```js
async function purgeFromTrash(id) {
  const row = (homeData?.trash || []).find((y) => y.id === id);
  homeEdit = { ...homeEdit, ask: null };
  try { await postForm('/api/task-purge', { id, space: homeData?.space?.id }); }
  catch (e) { paintHomeLower(); toast(t('errFailed', requestErrText(e))); return; }
  homeData = { ...homeData, trash: (homeData.trash || []).filter((y) => y.id !== id) };
  if (!homeData.trash.length) homeEdit = { ...homeEdit, trash: false };
  paintHomeLower();
  (homeNode()?.querySelector('.th-card--trash') ?? homeNode()?.querySelector('[data-th="trash"]') ?? homeNode()?.querySelector('#th-q'))
    ?.focus({ preventScroll: true });
  toast(t('taskPurged', row?.title ?? id));
}
```

  - Клавіші на `.th-card--trash`: `Shift+F10` → меню кошика; Delete на ній нічого не робить, бо «назавжди» лише з меню. Enter
    не відкриває.
  - `pruneFilters` і `homeUi` вигляду кошика не бачать (його нема в `homeUi`).

- [ ] **Step 2: Живі тести:**

```js
test("кошик: чип «Кошик · N» зʼявляється після видалення; вигляд — знебарвлені картки, «Повернути», без «+» і міток", …);
test("кошик → «Повернути»: задача в «Моїх», тека на місці; порожній кошик — вигляд вимкнено, чипа нема", …);
test("кошик → меню → «Видалити назавжди»: питання в картці; «Видалити назавжди» → теки нема, tasks.json.trash[id] = {purged}", …);
test("кошик: клік по статусному чипу виходить із вигляду кошика", …);
```

- [ ] **Step 3: Прогони.** JS-юніти; живі `tasks-crud`, `tasks-home`.

- [ ] **Step 4: Мутація.** Прибрати `if (!homeData.trash.length) homeEdit = …` → тест «порожній кошик — вигляд вимкнено» червоний.

- [ ] **Step 5: Коміт** — `app/app.js tests/live/tasks-crud.test.mjs`:
  `feat(0.30.0): вигляд кошика — повернути й видалити назавжди`.

---

### Task 10: Перейменування з вкладки, F2 у макеті, ⌘K

**Files:**
- Modify: `app/app.js` (обробник рядка вкладок, клавіші макета, `BAR_ACTIONS.rentask`), `app/shell-palette.js`
- Test: `tests/shell-palette.test.mjs` (або відповідний юніт палітри), `tests/live/tasks-crud.test.mjs`

- [ ] **Step 1: Поповер.**

```js
/** Етап Д: «Перейменувати задачу» — поповер `askForm` під вкладкою задачі `id` (нема вкладки — модально). */
async function renameTaskFromTab(id) {
  if (!id) return;
  const tab = tabs.find((x) => x.id === id);
  const title = tab?.title ?? (currentTaskId === id ? curTask?.title : '') ?? '';
  const anchor = () => tabsEl.querySelector(`.tab-main[data-val="${CSS.escape(id)}"]`);
  await askForm(() => taskNameFormHTML({ title }), {
    anchor: anchor(), place: 'below',
    focusBack: anchor,
    onSubmit: async (vals, ctl) => {
      const next = String(vals.title ?? '').trim();
      if (!next) { ctl.focus('title'); return t('titleRequired'); }
      if (next === title) return undefined;
      try { const r = await postForm('/api/task-rename', { id, title: next }); applyTaskTitle(id, r.title); }
      catch (e) { return t('errFailed', requestErrText(e)); }
      if (homeOpen) paintHomeLower();
      return undefined;
    },
  });
}
```

- [ ] **Step 2: Подвійний клік по вкладці.** На `tabsEl`:

```js
/* Етап Д: двічі по вкладці — перейменувати. ⛔ Перший клік по НЕактивній вкладці перемикає задачу, і `paintTabs` переписує
   рядок: ціль `dblclick` уже відʼєднана від документа — беремо вкладку з точки кліку. */
tabsEl.addEventListener('dblclick', (ev) => {
  const el = (ev.target.isConnected ? ev.target : document.elementFromPoint(ev.clientX, ev.clientY))?.closest?.('.tab-main');
  if (!el) return;
  ev.preventDefault();
  renameTaskFromTab(el.dataset.val);
});
```

  ⛔ Звірити, що `.tab-main` несе id у `data-val`, як у `tabs-view.js`.

- [ ] **Step 3: F2 у макеті.** У глобальному обробнику клавіш макета (там, де `I`/`C` острівця): `F2` без модифікаторів, не в
  полі вводу, не `homeOpen`, без `askUp()` і палітри → `renameTaskFromTab(currentTaskId)`. Обробник клавіш екрана «Задачі» вже
  забирає F2 на картці (Task 7), тож ці гілки не перетинаються.

- [ ] **Step 4: ⌘K.** У `paletteActions` (група `gGo`, після `go-tasks`), коли відкрита задача (`s.task`/відповідне поле
  стану палітри — звірити):

```js
    out.push({ id: "rentask", group: "gGo", labelKey: "taskRenamePal", icon: "pencil", kbd: "F2", act: "rentask" });
```

  `BAR_ACTIONS.rentask = () => renameTaskFromTab(currentTaskId);`. Юніт палітри: дія є з задачею, нема без задачі.

- [ ] **Step 5: Живі тести:**

```js
test("двічі по НЕактивній вкладці: задача перемкнулась і відкрився поповер під вкладкою; Enter → назва в tasks.json і підказці", …);
test("двічі по активній вкладці → поповер; Esc — без запиту, фокус на вкладці", …);
test("F2 у макеті → поповер під активною вкладкою; порожня назва — помилка під полем", …);
test("⌘K «Перейменувати задачу» → той самий поповер", …);
```

- [ ] **Step 6: Прогони.** JS-юніти; живі `tasks-crud`, `tabs`, `shell-palette`.

- [ ] **Step 7: Мутація.** Замінити ціль на `ev.target.closest('.tab-main')` без `elementFromPoint` → тест «двічі по НЕактивній»
  червоний. Якщо вижила — тест не відтворює перемальовку; посилити (дочекатись `aria-current` нової вкладки між кліками
  неможливо — `dblclick` Playwright атомарний; тоді перевірити, що поповер відкрився саме для клікнутої задачі).

- [ ] **Step 8: Коміт.** Файли: `app/app.js app/shell-palette.js tests/live/tasks-crud.test.mjs` і юніт палітри. Повідомлення:
  `feat(0.30.0): перейменування задачі з вкладки, F2 і ⌘K`.

---

### Task 11: Документи й версія

**Files:** `CHANGELOG.md`, `package.json`, `README.md`

- [ ] **Step 1: CHANGELOG.** Розділ `## [0.30.0] — 17.11.2026` (дату звірити в день релізу): англійський вступ одним реченням,
  як у [0.29.0], далі «Додано / Змінено». Пункти:
  - картка «Нова задача» в сітці;
  - меню картки (Перейменувати F2, Мітки…, Відкрити превʼю, Видалити ⌫);
  - перейменування на картці, з вкладки, F2, ⌘K;
  - видалення з питанням у картці й «Повернути»;
  - кошик простору (повернути, видалити назавжди);
  - сервер: `task-rename/delete/restore/purge`, `tasks-overview.trash`, `task-thumb?trash=1`, `task-new` → `task-in-trash`;
  - `registry.py pull` не воскрешає видалене;
  - «Мітки» переїхали в меню, «Нова задача» з голови прибрано.
- [ ] **Step 2: `package.json`** — `"version": "0.30.0"`.
- [ ] **Step 3: README.** У списку можливостей (розділ про задачі) — один рядок про створення, перейменування й кошик;
  статус — «Version 0.30.0 (дата)». Без скріншотів (окремий борг README).
- [ ] **Step 4: Охоронець забороненого списку:**

```bash
DEAI_FORBIDDEN_LIST="$HOME/Liga Tools/design-office-transition/scripts/deai-forbidden.txt" DEAI_REQUIRE_FORBIDDEN_LIST=1 python3 -B -m unittest tests.test_no_internal_addresses
```

  Результат: `OK`.
- [ ] **Step 5: Коміт** — `CHANGELOG.md package.json README.md`: `docs(0.30.0): CHANGELOG, версія, README`.

---

### Task 12 (контролер): фінальне ревʼю, релізний прогін, перевірка проти живого

- [ ] **Фінальне ревʼю.** Ревʼюер (Sonnet) читає весь диф гілки проти спеки. Знахідки — окремими комітами виконавця.
- [ ] **Релізний прогін.**
  - Юніти: JS, commenter, Python (`tests`, `bin`, `app`).
  - Усі живі — по файлу, послідовно.
  - Охоронець забороненого списку.
  - `git log --format='%an %ae %cn %ce' main..HEAD` — лише `neodisa`.
- [ ] **Злиття.** `main` ff → гілка (якщо `main` пішов уперед — `git -c user.name=neodisa -c user.email=… rebase`, охоронець
  наново). Тег `v0.30.0` (neodisa). Перезапуск канвасу 8765 за PID.
- [ ] **Перевірка проти живого.**
  - Лише в просторі без дашборда, на задачі, створеній карткою саме для перевірки: створити → перейменувати на картці → двічі
    по вкладці → видалити → «Повернути» → видалити → кошик → «Видалити назавжди».
  - Задач ЛІГИ не чіпати.
  - Після перевірки в `tasks.json` того простору лишається лише надгробок тестової задачі.
- [ ] **Push** — лише з окремого «так» власника.
