# Фаза И «Задачі й ітерації» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** назва задачі замість ідентифікатора, «задача / ітерація» в смузі, перелік ітерацій з «⋯» (перейменування в рядку, дублювання, видалення в кошик з «Повернути»), панель «Історія змін» ітерації з git теки задачі та окремі коміти правок AI.

**Architecture:** сервер отримує два чисті модулі — `app/iter_trash.py` (кошик ітерацій) і `app/iter_history.py` (git log → записи) — та три маршрути (`iteration-delete` м'який, `iteration-restore`, `GET iteration-history`) плюс локальний коміт AI в `/api/autosync`. Клієнт лишається на чистих функціях розмітки (`tabs-view.js`, `tasks-home.js`, `task-menu.js`, `shell-bar.js`, новий `iter-history-view.js`) і проводці в `app.js`; стан переліку ітерацій — один обʼєкт `iterUi`.

**Tech Stack:** vanilla JS ES modules, Python stdlib (`http.server`, `subprocess` git), `node --test`, `python3 -B -m unittest`, Playwright live tests.

**Спека:** `docs/superpowers/specs/2026-11-23-tasks-iterations-design.md` (разом із розділом «Поправки при плануванні»).

---

## Спільні правила (для КОЖНОЇ задачі)

- Робоча тека — worktree `deai-canvas-dev`, гілка `feat/tasks-iterations`. Інші гілки не перемикати, `git add -A` / `reset` / `stash` без унікальної мітки / `--amend` — заборонено.
- Коміт лише так (нові файли спершу `git add -- <шляхи>`):
  `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<тема>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>`
- Тести: `node --test tests/*.test.mjs`; Python — `python3 -B -m unittest discover -s tests -p "test_*.py"` (голий `unittest` у цьому репо знаходить 0 тестів; повний набір ~19 хв); новий файл тестів на `Fixture` мусить сам писати `os.environ['DEAI_HOME'] = …` (охоронець `test_serve.TestsCannotWriteLiveConfig` шукає це присвоєння у файлі); живі — ОДИН файл за раз під спільним замком, з тимчасовим HOME:
  `until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs; rmdir /private/tmp/deai-live.lock`
  (`rmdir` лише після СВОГО успішного `mkdir`; живі — не паралельно з Python-набором; під час живого прогону код не правити).
- Ніколи: порти 8765/4317, жива тека `deai-canvas`, справжні `~/.deai`, `~/deai-published`, `~/deai-work`, `~/.gitconfig`, `tasks.json`, мережа, `pkill`/`killall` за шаблоном, `while pgrep -f`, `rm -rf` (лише `mktemp -d`). Завжди `python3 -B`.
- Публічне репо: жодних справжніх імен, внутрішніх хостів, ключів, абсолютних локальних шляхів у коді/доках; тестові адреси — вигадані.
- Без підписів-пояснень в інтерфейсі (правило власника): лише вміст, назви дій і тексти помилок.
- i18n: кожен новий ключ — в ОБИДВА словники `app/i18n.js` (uk і en); `tests/i18n-keys.test.mjs` стереже паритет.

## Карта файлів

| Файл | Що |
|---|---|
| `app/iter_trash.py` (новий) | кошик ітерацій: перенесення, повернення, прибирання, вільний номер, впорядкована вставка |
| `app/iter_history.py` (новий) | git log теки задачі → записи історії ітерації; брудні ітерації; трейлер AI |
| `app/serve.py` | `TASK_IGNORE` + `.trash/`; `_new_iteration`, `_iteration_delete` (кошик, 409), `_iteration_restore` (новий), `GET /api/iteration-history` (новий), `ai_commit` + `_autosync`, тема коміту публікації з id ітерацій |
| `app/tabs-model.js`, `app/tabs-view.js` | вкладка = назва; підказка з ключем Jira |
| `app/tasks-home.js`, `app/task-menu.js` | картка без ключа (крім збігу пошуку); aria з назвою; меню без «Видалити» в смузі |
| `app/bar-model.js` | порядок зони 1: задача, потім ітерація |
| `app/shell-bar.js` | `crumbTask` (кнопка + дропдаун задачі), `crumbIter` з рядками «⋯», полем, питанням і меню рядка |
| `app/iter-history-view.js` (новий) | розмітка панелі «Історія» |
| `app/app.js` | `iterUi`, дії `itmenu/itren/itdel/itdelno/itdelyes/itdup/ithist/itmodact/newit/histcur/tren/ttags`, `createIteration`, `deleteIteration`, `restoreIteration`, панель `#hist-panel`, `histSync`, меню задачі в смузі; видалити `iterDelAsk`, `delitask`, мертвий `pillMenu` |
| `app/shell-palette.js` | команда ⌘K «Історія ітерації» |
| `app/index.html` | `<div id="hist-panel" class="insp hist" hidden>` |
| `app/styles.css` | `.it-row`, `.it-more`, `.it-who`, `.it-ren`, `.it-cfm`, `.dd--itmenu`, `.hist-*`, `body.with-hist`, `.th-krow` мін. висота, кнопка-крошка задачі |
| `app/i18n.js` | нові/змінені тексти |
| тести | `tests/test_iter_trash.py`, `tests/test_iter_history.py`, `tests/test_iteration_api.py` (нові); `tests/iter-history-view.test.mjs` (новий); правки `tests/shell-bar.test.mjs`, `tests/tabs-view.test.mjs`, `tests/tabs-model.test.mjs`, `tests/tasks-home.test.mjs`, `tests/task-menu.test.mjs`, `tests/bar-model.test.mjs`, `tests/shell-palette.test.mjs`; живі `tests/live/iterations-list.test.mjs` (новий) і правки `tests/live/{tabs,shell-bar,canvas}.test.mjs` |

---

### Task 1: `app/iter_trash.py` — кошик ітерацій (повний рівень)

**Files:**
- Create: `app/iter_trash.py`
- Test: `tests/test_iter_trash.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Кошик ітерацій (фаза И, Р6): перенесення без стирання, повернення, прибирання через 7 днів, номер без повторів."""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import iter_trash as tr  # noqa: E402

T0 = datetime.datetime(2026, 11, 23, 10, 0, 0, tzinfo=datetime.timezone.utc)


def _task(ids):
    d = tempfile.mkdtemp(prefix='itrash-')
    for i in ids:
        os.makedirs(os.path.join(d, 'iterations', i))
        with open(os.path.join(d, 'iterations', i, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(f'<h1>{i}</h1>')
    return d


class MoveAndRestore(unittest.TestCase):
    def setUp(self):
        self.d = _task(['it1', 'it2', 'it3'])
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_move_keeps_files_and_entry(self):
        slot = tr.move_to_trash(self.d, {'id': 'it2', 'note': 'Друга'}, T0)
        self.assertEqual(slot, 'it2--20261123-100000')
        self.assertFalse(os.path.exists(os.path.join(self.d, 'iterations', 'it2')))
        base = os.path.join(self.d, '.trash', 'iterations', slot)
        self.assertTrue(os.path.isfile(os.path.join(base, 'files', 'index.html')))
        with open(os.path.join(base, 'entry.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['entry'], {'id': 'it2', 'note': 'Друга'})

    def test_same_second_gets_suffix(self):
        a = tr.move_to_trash(self.d, {'id': 'it2'}, T0)
        os.makedirs(os.path.join(self.d, 'iterations', 'it2'))
        b = tr.move_to_trash(self.d, {'id': 'it2'}, T0)
        self.assertEqual((a, b), ('it2--20261123-100000', 'it2--20261123-100000-2'))

    def test_restore_puts_back_same_id(self):
        slot = tr.move_to_trash(self.d, {'id': 'it2', 'note': 'Друга', 'git': 'abc1234'}, T0)
        entry, renamed = tr.restore(self.d, slot, ['it1', 'it3'])
        self.assertEqual((entry['id'], renamed, entry['git']), ('it2', False, 'abc1234'))
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'iterations', 'it2', 'index.html')))
        self.assertFalse(os.path.exists(os.path.join(self.d, '.trash', 'iterations', slot)))

    def test_restore_collision_takes_next_free_id_and_drops_git(self):
        slot = tr.move_to_trash(self.d, {'id': 'it2', 'git': 'abc1234'}, T0)
        os.makedirs(os.path.join(self.d, 'iterations', 'it2'))       # хтось уже зайняв it2
        entry, renamed = tr.restore(self.d, slot, ['it1', 'it2', 'it3'])
        self.assertEqual((entry['id'], renamed), ('it4', True))
        self.assertNotIn('git', entry)
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'iterations', 'it4', 'index.html')))

    def test_restore_unknown_slot(self):
        with self.assertRaises(tr.IterTrashError) as c:
            tr.restore(self.d, 'it9--20261123-100000', ['it1'])
        self.assertEqual(c.exception.code, 'not-in-trash')
        for bad in ('../x', 'it2', 'it2--x', '', 5, None):
            with self.assertRaises(tr.IterTrashError) as c:
                tr.restore(self.d, bad, ['it1'])
            self.assertEqual(c.exception.code, 'bad-slot')

    def test_bad_id_refused(self):
        for bad in ('', '..', 'a/b', 'it 1', None):
            with self.assertRaises(tr.IterTrashError):
                tr.move_to_trash(self.d, {'id': bad}, T0)


class NextIdAndPurge(unittest.TestCase):
    def setUp(self):
        self.d = _task(['it1', 'it2', 'it3'])
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_next_id_counts_trash(self):
        tr.move_to_trash(self.d, {'id': 'it3'}, T0)
        self.assertEqual(tr.next_id(self.d, ['it1', 'it2']), 'it4')

    def test_next_id_counts_stray_folders(self):
        os.makedirs(os.path.join(self.d, 'iterations', 'it7'))
        self.assertEqual(tr.next_id(self.d, ['it1']), 'it8')

    def test_purge_removes_only_older_than_keep(self):
        old = tr.move_to_trash(self.d, {'id': 'it1'}, T0 - datetime.timedelta(days=8))
        fresh = tr.move_to_trash(self.d, {'id': 'it2'}, T0 - datetime.timedelta(days=6))
        self.assertEqual(tr.purge(self.d, T0), [old])
        root = os.path.join(self.d, '.trash', 'iterations')
        self.assertEqual(os.listdir(root), [fresh])

    def test_purge_without_trash_is_noop(self):
        self.assertEqual(tr.purge(self.d, T0), [])


class InsertOrdered(unittest.TestCase):
    def test_inserts_by_number(self):
        its = [{'id': 'it1'}, {'id': 'it3'}, {'id': 'it5'}]
        tr.insert_ordered(its, {'id': 'it4'})
        self.assertEqual([i['id'] for i in its], ['it1', 'it3', 'it4', 'it5'])

    def test_non_numeric_goes_last(self):
        its = [{'id': 'it1'}]
        tr.insert_ordered(its, {'id': 'draft'})
        self.assertEqual([i['id'] for i in its], ['it1', 'draft'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -B -m unittest tests.test_iter_trash -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'iter_trash'`.

- [ ] **Step 3: Implement `app/iter_trash.py`**

```python
"""Кошик ітерацій задачі (фаза И, Р6): видалення без стирання, повернення, прибирання через 7 днів.

Тека `iterations/<id>` переїжджає `os.rename` у `<тека задачі>/.trash/iterations/<id>--<РРРРММДД-ГГХХСС>[-N]/files`, поруч —
`entry.json` (запис ітерації з `iterations.json` і час видалення). Той самий диск — без копіювання.

Функції змінюють диск, але НЕ пишуть `iterations.json`: це робить маршрут (`save_meta`). Час — параметр (`now`, aware UTC),
тож тести детерміновані. `.trash/` стоїть у `TASK_IGNORE` (git), а `copy_mockup`/`_mockup_files` пропускають теки з крапкою.
"""
import datetime
import json
import os
import re
import shutil

TRASH_REL = os.path.join('.trash', 'iterations')
KEEP_DAYS = 7
ID_RE = re.compile(r'^[\w-]{1,64}$')
NUM_RE = re.compile(r'^it(\d+)$')
SLOT_RE = re.compile(r'^([\w-]{1,64})--(\d{8}-\d{6})(?:-\d+)?$')


class IterTrashError(Exception):
    """Відмова з кодом: `bad-id`, `bad-slot`, `not-in-trash`."""

    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def trash_root(task_dir):
    return os.path.join(task_dir, TRASH_REL)


def _safe_id(iid):
    return isinstance(iid, str) and iid not in ('.', '..') and ID_RE.fullmatch(iid) is not None


def move_to_trash(task_dir, entry, now):
    """Перенести теку ітерації й її запис у кошик. Повертає імʼя слота (`it2--20261123-100000`)."""
    iid = entry.get('id') if isinstance(entry, dict) else None
    if not _safe_id(iid):
        raise IterTrashError('bad-id', 'the iteration id is not a safe folder name')
    root = trash_root(task_dir)
    os.makedirs(root, exist_ok=True)
    base = f'{iid}--{now.strftime("%Y%m%d-%H%M%S")}'
    slot, n = base, 1
    while os.path.exists(os.path.join(root, slot)):
        n += 1
        slot = f'{base}-{n}'
    dst = os.path.join(root, slot)
    os.makedirs(dst)
    src = os.path.join(task_dir, 'iterations', iid)
    if os.path.isdir(src):
        os.rename(src, os.path.join(dst, 'files'))
    with open(os.path.join(dst, 'entry.json'), 'w', encoding='utf-8') as f:
        json.dump({'entry': entry, 'deleted_at': now.strftime('%Y-%m-%dT%H:%M:%SZ')}, f, ensure_ascii=False)
    return slot


def next_id(task_dir, ids):
    """Наступний вільний `itN`: максимум по записах, кошику й теках `iterations/` (номер видаленої не повторюється)."""
    nums = [int(m.group(1)) for i in ids if isinstance(i, str) and (m := NUM_RE.match(i))]
    root = trash_root(task_dir)
    if os.path.isdir(root):
        for name in os.listdir(root):
            s = SLOT_RE.match(name)
            if s and (m := NUM_RE.match(s.group(1))):
                nums.append(int(m.group(1)))
    it_dir = os.path.join(task_dir, 'iterations')
    if os.path.isdir(it_dir):
        for name in os.listdir(it_dir):
            if m := NUM_RE.match(name):
                nums.append(int(m.group(1)))
    return f'it{max(nums, default=0) + 1}'


def restore(task_dir, slot, taken_ids):
    """Повернути ітерацію зі слота. `(entry, renamed)`; id зайнятий → наступний вільний номер, `git` прибирається
    (історія новоїʼ теки починається з повернення, а не з коміту створення старої)."""
    if not isinstance(slot, str) or not SLOT_RE.fullmatch(slot):
        raise IterTrashError('bad-slot', 'not a trash slot name')
    base = os.path.join(trash_root(task_dir), slot)
    meta_p = os.path.join(base, 'entry.json')
    if not os.path.isfile(meta_p):
        raise IterTrashError('not-in-trash', 'nothing to restore')
    with open(meta_p, encoding='utf-8') as f:
        entry = dict(json.load(f)['entry'])
    iid, renamed = entry['id'], False
    if iid in taken_ids or os.path.exists(os.path.join(task_dir, 'iterations', iid)):
        iid = next_id(task_dir, list(taken_ids) + [entry['id']])
        entry['id'] = iid
        entry.pop('git', None)
        renamed = True
    target = os.path.join(task_dir, 'iterations', iid)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    files = os.path.join(base, 'files')
    if os.path.isdir(files):
        os.rename(files, target)
    else:
        os.makedirs(target)
    shutil.rmtree(base)
    return entry, renamed


def purge(task_dir, now, keep_days=KEEP_DAYS):
    """Стерти слоти, старші за `keep_days`. Повертає їхні імена (відсортовані)."""
    root = trash_root(task_dir)
    if not os.path.isdir(root):
        return []
    edge = now - datetime.timedelta(days=keep_days)
    gone = []
    for name in sorted(os.listdir(root)):
        s = SLOT_RE.match(name)
        if not s:
            continue
        at = datetime.datetime.strptime(s.group(2), '%Y%m%d-%H%M%S').replace(tzinfo=datetime.timezone.utc)
        if at < edge:
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)
            gone.append(name)
    return gone


def insert_ordered(its, entry):
    """Вставити запис за номером (`it4` між `it3` і `it5`); не-`itN` — у кінець. Змінює `its` на місці."""
    m = NUM_RE.match(entry.get('id', ''))
    if not m:
        its.append(entry)
        return
    n = int(m.group(1))
    for i, x in enumerate(its):
        k = NUM_RE.match(x.get('id', ''))
        if k and int(k.group(1)) > n:
            its.insert(i, entry)
            return
    its.append(entry)
```

- [ ] **Step 4: Run tests**

Run: `python3 -B -m unittest tests.test_iter_trash -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -- app/iter_trash.py tests/test_iter_trash.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(И): iter_trash — кошик ітерацій: перенесення, повернення, 7 днів, номер без повторів" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/iter_trash.py tests/test_iter_trash.py
```

---

### Task 2: маршрути видалення/повернення, номер нової ітерації, `.trash/` у `TASK_IGNORE` (повний рівень)

**Files:**
- Modify: `app/serve.py` — `TASK_IGNORE` (~рядок 157), `import iter_trash` (поруч з `import task_trash`), `_new_iteration`, `_iteration_delete`, новий `_iteration_restore`, POST-диспетчер (`elif self.path == '/api/iteration-delete'`)
- Test: `tests/test_iteration_api.py` (новий)

- [ ] **Step 1: Write the failing tests**

Стенд — `test_spaces_serve.Fixture` (сервер у процесі, тимчасові HOME/DEAI_HOME, простір `P` із задачею `x`, у якої одна ітерація `it1`). Перед кожним тестом тека задачі `x` відтворюється з нуля.

```python
"""Фаза И: видалення ітерації в кошик, повернення, номер без повторів, 409 на останню, історія й коміт AI (Task 2, 4)."""
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
sys.path.insert(0, HERE)
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _meta(d):
    with open(os.path.join(d, 'iterations.json'), encoding='utf-8') as f:
        return json.load(f)


def _git(d, *args):
    return subprocess.run(['git', *args], cwd=d, capture_output=True, text=True).stdout


class _Base(base.Fixture):
    """Без тестів: лише стенд. Класи нижче успадковують ЙОГО, а не один одного — інакше тести бігли б двічі."""

    def setUp(self):
        super().setUp()
        spaces.switch_space(self.p_id)                      # простір P, поточна задача — `x`
        shutil.rmtree(self.x_dir, ignore_errors=True)
        base._task_dir(self.x_dir, 'x')
        self.post('/api/iteration', {'from': 'it1', 'note': 'Друга'})     # it2

    def ids(self):
        return [i['id'] for i in _meta(self.x_dir)['iterations']]


class IterationApi(_Base):
    def test_delete_moves_to_trash_and_returns_slot(self):
        st, body = self.post('/api/iteration-delete', {'id': 'it2'})
        self.assertEqual(st, 200)
        self.assertTrue(body['ok'] and body['deleted'] == 'it2' and body['trash'].startswith('it2--'))
        self.assertEqual(self.ids(), ['it1'])
        self.assertFalse(os.path.exists(os.path.join(self.x_dir, 'iterations', 'it2')))
        self.assertTrue(os.path.isdir(os.path.join(self.x_dir, '.trash', 'iterations', body['trash'], 'files')))

    def test_trash_is_not_committed(self):
        self.post('/api/iteration-delete', {'id': 'it2'})
        tracked = _git(self.x_dir, 'ls-files')
        self.assertNotIn('.trash/', tracked)
        with open(os.path.join(self.x_dir, '.gitignore'), encoding='utf-8') as f:
            self.assertIn('.trash/', f.read().splitlines())

    def test_restore_puts_it_back_in_order(self):
        self.post('/api/iteration', {'from': 'it1', 'note': 'Третя'})         # it3
        _, d = self.post('/api/iteration-delete', {'id': 'it2'})
        st, body = self.post('/api/iteration-restore', {'trash': d['trash']})
        self.assertEqual((st, body['ok'], body['id'], body['renamed']), (200, True, 'it2', False))
        self.assertEqual(self.ids(), ['it1', 'it2', 'it3'])
        self.assertIn('restore iteration it2', _git(self.x_dir, 'log', '-1', '--format=%s'))

    def test_new_iteration_does_not_reuse_trashed_number(self):
        self.post('/api/iteration-delete', {'id': 'it2'})
        _, body = self.post('/api/iteration', {'from': 'it1', 'note': 'Нова'})
        self.assertEqual(body['iteration']['id'], 'it3')

    def test_last_iteration_is_refused(self):
        self.post('/api/iteration-delete', {'id': 'it2'})
        st, body = self.post('/api/iteration-delete', {'id': 'it1'})
        self.assertEqual((st, body['error']), (409, 'last-iteration'))
        self.assertEqual(self.ids(), ['it1'])

    def test_restore_errors(self):
        st, _ = self.post_raw('/api/iteration-restore', {'trash': '../x'})
        self.assertEqual(st, 400)
        st, body = self.post('/api/iteration-restore', {'trash': 'it9--20261123-100000'})
        self.assertEqual((st, body['error']), (404, 'not-in-trash'))

    def test_unknown_iteration_still_404(self):
        st, _ = self.post_raw('/api/iteration-delete', {'id': 'it9'})
        self.assertEqual(st, 404)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -B -m unittest tests.test_iteration_api -v`
Expected: FAIL — `KeyError: 'trash'` / 404 на `/api/iteration-restore` / `.trash/` відсутній у `.gitignore`.

- [ ] **Step 3: Implement in `app/serve.py`**

3a. `TASK_IGNORE` — додати `.trash/` (кінець кортежу):

```python
TASK_IGNORE = ('publish/', '*.bak', '*.tmp', '.DS_Store', 'comments-for-ai*',
               '.vercel/', '.dc-tuner.json', '.dc-local-comments.json',
               '.pages.lock', '.trash/')
```

3b. Імпорт поруч з `import task_trash` (знайти `grep -n "^import task_trash" app/serve.py`):

```python
import iter_trash  # кошик ітерацій задачі (фаза И)
```

3c. `_new_iteration` — номер через кошик. Замінити два рядки

```python
        nums = [int(m.group(1)) for i in its if (m := re.match(r'^it(\d+)$', i['id']))]
        new_id = f'it{max(nums, default=0) + 1}'
```

на

```python
        # Фаза И: номер видаленої (у кошику) не повторюємо — інакше історія нової `itN` змішалась би зі старою.
        new_id = iter_trash.next_id(task['dir'], [i['id'] for i in its])
```

3d. `_iteration_delete` — повністю замінити тіло:

```python
    def _iteration_delete(self, payload):
        """Видалити ітерацію: тека й запис — у кошик задачі (`iter_trash`, 7 днів), відповідь несе слот для «Повернути».
        Останню ітерацію не видаляємо (409): задача без ітерацій лишилась би без макета."""
        tid, task = self._current_task()
        iid = payload.get('id', '')
        if not isinstance(iid, str) or not NAME_RE.fullmatch(iid):
            self.send_error(400, 'bad id')
            return
        meta = load_meta(task)
        its = meta.get('iterations', [])
        entry = next((i for i in its if i['id'] == iid), None)
        if entry is None:
            self.send_error(404, 'iteration not found')
            return
        if len(its) <= 1:
            self._send_json({'ok': False, 'error': 'last-iteration'}, status=409)
            return
        now = iter_trash.utcnow()
        try:
            slot = iter_trash.move_to_trash(task['dir'], entry, now)
        except (OSError, iter_trash.IterTrashError) as e:
            self._send_json({'ok': False, 'error': 'trash-failed', 'message': str(e)}, status=500)
            return
        meta['iterations'] = [i for i in its if i['id'] != iid]
        save_meta(task, meta)
        try:
            iter_trash.purge(task['dir'], now)
        except OSError:
            pass                       # прибирання — не умова видалення
        git_autocommit(task['dir'], f'delete iteration {iid}')
        self._send_json({'ok': True, 'deleted': iid, 'trash': slot})
```

3e. Новий обробник одразу після `_iteration_delete`:

```python
    def _iteration_restore(self, payload):
        """`POST /api/iteration-restore {trash}` — повернути ітерацію з кошика. Зайнятий id → наступний вільний номер."""
        tid, task = self._current_task()
        slot = payload.get('trash')
        if not isinstance(slot, str) or not iter_trash.SLOT_RE.fullmatch(slot):
            self.send_error(400, 'bad trash slot')
            return
        meta = load_meta(task)
        its = meta.setdefault('iterations', [])
        try:
            entry, renamed = iter_trash.restore(task['dir'], slot, [i['id'] for i in its])
        except iter_trash.IterTrashError as e:
            self._send_json({'ok': False, 'error': e.code}, status=404 if e.code == 'not-in-trash' else 400)
            return
        except OSError as e:
            self._send_json({'ok': False, 'error': 'restore-failed', 'message': str(e)}, status=500)
            return
        iter_trash.insert_ordered(its, entry)
        save_meta(task, meta)
        git_autocommit(task['dir'], f'restore iteration {entry["id"]}')
        self._send_json({'ok': True, 'id': entry['id'], 'renamed': renamed, 'iteration': entry})
```

3f. POST-диспетчер — одразу після гілки `iteration-delete`:

```python
        elif self.path == '/api/iteration-restore':
            self._iteration_restore(payload)
```

- [ ] **Step 4: Run tests**

Run: `python3 -B -m unittest tests.test_iteration_api tests.test_iter_trash -v`
Expected: PASS.
Run: `python3 -B -m unittest tests.test_serve -v 2>&1 | tail -5`
Expected: OK (`test_7_delete_iteration` лишається зеленим: тека зникла з `iterations/`, `it9` → 404).

- [ ] **Step 5: Commit**

```bash
git add -- tests/test_iteration_api.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(И): видалення ітерації в кошик, /api/iteration-restore, 409 на останню, номер без повторів, .trash/ поза git" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/serve.py tests/test_iteration_api.py
```

---

### Task 3: `app/iter_history.py` — історія ітерації з git (повний рівень)

**Files:**
- Create: `app/iter_history.py`
- Test: `tests/test_iter_history.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Історія ітерації з git теки задачі (фаза И, Р8): фільтр, таблиця тем, трейлер AI, незаписані зміни."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import iter_history as ih  # noqa: E402


def git(d, *a, env=None):
    e = {**os.environ, 'GIT_AUTHOR_NAME': 'Олена Д.', 'GIT_AUTHOR_EMAIL': 'o@example.com',
         'GIT_COMMITTER_NAME': 'Олена Д.', 'GIT_COMMITTER_EMAIL': 'o@example.com', **(env or {})}
    r = subprocess.run(['git', *a], cwd=d, capture_output=True, text=True, env=e)
    return r.stdout.strip()


def write(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)


def commit(d, msg):
    git(d, 'add', '-A')
    git(d, 'commit', '-q', '-m', msg)
    return git(d, 'rev-parse', '--short', 'HEAD')


class History(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='ihist-')
        self.addCleanup(shutil.rmtree, self.d, True)
        git(self.d, 'init', '-q')
        write(self.d, 'iterations/it1/index.html', 'a')
        self.c1 = commit(self.d, 'iteration it1: Перша')
        write(self.d, 'iterations/it2/index.html', 'b')
        self.c2 = commit(self.d, 'iteration it2: копія it1 · Друга')
        write(self.d, 'iterations/it2/filters.css', 'c')
        write(self.d, 'iterations/it2/data.js', 'd')
        commit(self.d, 'it2: зміни AI\n\nDeai-Actor: ai')
        write(self.d, 'iterations/it1/index.html', 'a2')
        commit(self.d, 'page main: rename')                       # чіпає лише it1
        write(self.d, 'iterations.json', '{}')
        commit(self.d, 'rename iteration it2: Фільтри')            # лише iterations.json, id у темі
        write(self.d, 'iterations/it2/pages.json', '[]')
        commit(self.d, 'page filters: new in it2')
        write(self.d, 'iterations.json', '{"p":1}')
        commit(self.d, 'publish: 1 iteration(s) · it2')

    def test_entries_for_it2_newest_first(self):
        out = ih.history(self.d, {'id': 'it2', 'git': self.c2}, {'filters': 'Фільтри'})
        kinds = [e['kind'] for e in out['entries']]
        self.assertEqual(kinds, ['publish', 'page-new', 'rename', 'ai', 'copy'])
        self.assertFalse(out['degraded'])
        self.assertIsNone(out['pending'])

    def test_args_and_actor(self):
        es = {e['kind']: e for e in ih.history(self.d, {'id': 'it2', 'git': self.c2}, {'filters': 'Фільтри'})['entries']}
        self.assertEqual(es['copy']['args'], {'from': 'it1', 'note': 'Друга'})
        self.assertEqual(es['rename']['args'], {'name': 'Фільтри'})
        self.assertEqual(es['page-new']['args'], {'page': 'filters', 'name': 'Фільтри'})
        self.assertEqual(es['ai']['actor'], {'kind': 'ai', 'name': 'AI'})
        self.assertEqual(es['copy']['actor'], {'kind': 'person', 'name': 'Олена Д.'})
        self.assertEqual(sorted(es['ai']['files']), ['data.js', 'filters.css'])
        self.assertRegex(es['ai']['at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

    def test_other_iteration_commits_excluded(self):
        texts = [e['text'] for e in ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['entries']]
        self.assertNotIn('page main: rename', texts)

    def test_creation_commit_cuts_older_history(self):
        # it1 «видалили» й створили знову з тим самим номером: коміти до нового створення — не її
        write(self.d, 'iterations/it1/index.html', 'new')
        c = commit(self.d, 'iteration it1: Нова перша')
        out = ih.history(self.d, {'id': 'it1', 'git': c}, {})
        self.assertEqual([e['kind'] for e in out['entries']], ['create'])

    def test_files_capped(self):
        for i in range(8):
            write(self.d, f'iterations/it2/f{i}.css', str(i))
        commit(self.d, 'it2: зміни AI\n\nDeai-Actor: ai')
        e = ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['entries'][0]
        self.assertEqual((len(e['files']), e['more']), (5, 3))

    def test_pending_lists_dirty_files(self):
        write(self.d, 'iterations/it2/new.html', 'x')
        p = ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['pending']
        self.assertEqual(p['files'], ['new.html'])
        self.assertRegex(p['at'], r'^\d{4}-\d{2}-\d{2}T')

    def test_dirty_iterations(self):
        write(self.d, 'iterations/it1/x.html', 'x')
        write(self.d, 'iterations/it2/y.html', 'y')
        self.assertEqual(ih.dirty_iterations(self.d), {'it1', 'it2'})

    def test_no_git_is_degraded_with_creation_from_meta(self):
        d = tempfile.mkdtemp(prefix='ihist-nogit-')
        self.addCleanup(shutil.rmtree, d, True)
        out = ih.history(d, {'id': 'it1', 'date': '21.11.2026 18:40', 'author': 'Олена Д.', 'note': 'Старт'}, {})
        self.assertTrue(out['degraded'])
        self.assertEqual(out['entries'][0]['kind'], 'create')
        self.assertEqual(out['entries'][0]['actor'], {'kind': 'person', 'name': 'Олена Д.'})

    def test_unknown_subject_is_other_trimmed(self):
        write(self.d, 'iterations/it2/z.html', 'z')
        commit(self.d, 'щось своє ' + 'x' * 200)
        e = ih.history(self.d, {'id': 'it2', 'git': self.c2}, {})['entries'][0]
        self.assertEqual(e['kind'], 'other')
        self.assertEqual(len(e['text']), 120)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -B -m unittest tests.test_iter_history -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'iter_history'`.

- [ ] **Step 3: Implement `app/iter_history.py`**

```python
"""Історія змін ітерації (фаза И, Р8) з git теки задачі: `git log` → записи панелі «Історія».

Нової бази немає: канвас уже комітить кожну дію (`git_autocommit`). Ітерації належить коміт, що чіпає `iterations/<id>/`, або той,
у темі якого стоїть її id. Коміти, старші за коміт створення (`entry['git']`), відкидаються — історія не змішується з давно
видаленою ітерацією, що мала той самий номер. Тексти записів складає клієнт за `kind` (i18n); `text` — тема як є (≤120).
"""
import datetime
import os
import re
import subprocess

LOG_LIMIT = 300
FILES_MAX = 5
TEXT_MAX = 120
AI_TRAILER = 'Deai-Actor: ai'
_RS, _FS = '\x1e', '\x1f'

_RULES = (
    (re.compile(r'^iteration (?P<it>[\w-]+): копія (?P<from>[\w-]+) · (?P<note>.*)$'), 'copy'),
    (re.compile(r'^iteration (?P<it>[\w-]+): pages from (?P<list>.*)$'), 'merge'),
    (re.compile(r'^iteration (?P<it>[\w-]+): (?P<note>.*)$'), 'create'),
    (re.compile(r'^rename iteration (?P<it>[\w-]+): (?P<name>.*)$'), 'rename'),
    (re.compile(r'^restore iteration (?P<it>[\w-]+)$'), 'restore'),
    (re.compile(r'^page (?P<page>\S+): new in (?P<it>[\w-]+)$'), 'page-new'),
    (re.compile(r'^page (?P<page>\S+): rename$'), 'page-rename'),
    (re.compile(r'^page (?P<page>\S+): move$'), 'page-move'),
    (re.compile(r'^tree: (?P<what>.*)$'), 'tree'),
    (re.compile(r'^publish: '), 'publish'),
    (re.compile(r'^(?P<it>[\w-]+): зміни AI$'), 'ai'),
    (re.compile(r'^(?P<it>[\w-]+): автосинк'), 'sync'),
)


def _git(task_dir, args, run):
    r = run(['git', *args], cwd=task_dir, capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise OSError(r.stderr.strip() or f'git {args[0]} failed')
    return r.stdout


def _mentions(subject, iid):
    return re.search(rf'(?<![\w-]){re.escape(iid)}(?![\w-])', subject) is not None


def _classify(subject, body, page_names):
    kind, args = 'other', {}
    for rx, k in _RULES:
        m = rx.match(subject)
        if not m:
            continue
        kind, g = k, m.groupdict()
        if k == 'copy':
            args = {'from': g['from'], 'note': '' if g['note'] == 'без примітки' else g['note']}
        elif k == 'create':
            args = {'note': '' if g['note'] == 'без примітки' else g['note']}
        elif k == 'merge':
            args = {'from': [x for x in g['list'].split(',') if x]}
        elif k == 'rename':
            args = {'name': g['name']}
        elif k.startswith('page-'):
            args = {'page': g['page'], 'name': page_names.get(g['page']) or g['page']}
        break
    ai = AI_TRAILER in (body or '')
    if ai:
        args = {**args, 'synced': kind == 'sync'}
        kind = 'ai'
    return kind, args, ai


def _to_local_iso(date_text):
    """`ДД.ММ.РРРР ГГ:ХХ` з `iterations.json` → ISO з поясом машини; не розібрали — порожньо."""
    try:
        dt = datetime.datetime.strptime(date_text, '%d.%m.%Y %H:%M')
    except (TypeError, ValueError):
        return ''
    return dt.astimezone().isoformat(timespec='seconds')


def _created_from_meta(entry):
    return {'sha': '', 'at': _to_local_iso(entry.get('date')),
            'actor': {'kind': 'person', 'name': str(entry.get('author') or '')},
            'kind': 'create', 'args': {'note': str(entry.get('note') or '')}, 'text': '', 'files': [], 'more': 0}


def dirty_iterations(task_dir, run=subprocess.run):
    """Ідентифікатори ітерацій із незакоміченими змінами. Без `.git` — усі теки `iterations/`."""
    if not os.path.isdir(os.path.join(task_dir, '.git')):
        it_dir = os.path.join(task_dir, 'iterations')
        return set(os.listdir(it_dir)) if os.path.isdir(it_dir) else set()
    out = _git(task_dir, ['status', '--porcelain', '-z', '--untracked-files=all', '--', 'iterations/'], run)
    ids = set()
    for rec in out.split('\0'):
        path = rec[3:] if len(rec) > 3 else ''
        parts = path.split('/')
        if len(parts) >= 3 and parts[0] == 'iterations':
            ids.add(parts[1])
    return ids


def _pending(task_dir, iid, run):
    prefix = f'iterations/{iid}/'
    out = _git(task_dir, ['status', '--porcelain', '-z', '--untracked-files=all', '--', prefix], run)
    files, newest = [], 0.0
    for rec in out.split('\0'):
        path = rec[3:] if len(rec) > 3 else ''
        if not path.startswith(prefix):
            continue
        files.append(path[len(prefix):])
        try:
            newest = max(newest, os.path.getmtime(os.path.join(task_dir, path)))
        except OSError:
            pass
    if not files:
        return None
    at = datetime.datetime.fromtimestamp(newest).astimezone().isoformat(timespec='seconds') if newest else ''
    return {'files': sorted(files)[:FILES_MAX], 'more': max(0, len(files) - FILES_MAX), 'at': at}


def history(task_dir, entry, page_names=None, *, limit=LOG_LIMIT, run=subprocess.run):
    """`{'entries': [...], 'pending': {...}|None, 'degraded': bool}` для ітерації `entry` (запис з `iterations.json`)."""
    iid = entry['id']
    page_names = page_names or {}
    if not os.path.isdir(os.path.join(task_dir, '.git')):
        return {'entries': [_created_from_meta(entry)], 'pending': None, 'degraded': True}
    try:
        raw = _git(task_dir, ['log', f'-n{int(limit)}', '--name-only',
                              f'--format={_RS}%h{_FS}%an{_FS}%aI{_FS}%s{_FS}%b{_FS}'], run)
        pending = _pending(task_dir, iid, run)
    except (OSError, subprocess.SubprocessError):
        return {'entries': [_created_from_meta(entry)], 'pending': None, 'degraded': True}
    created = str(entry.get('git') or '')
    prefix = f'iterations/{iid}/'
    entries = []
    for chunk in raw.split(_RS):
        if not chunk.strip():
            continue
        parts = chunk.split(_FS)
        if len(parts) < 6:
            continue
        sha, author, at, subject, body, rest = parts[:6]
        files_all = [ln for ln in rest.strip().splitlines() if ln]
        mine = [f[len(prefix):] for f in files_all if f.startswith(prefix)]
        if mine or _mentions(subject, iid):
            kind, args, ai = _classify(subject, body, page_names)
            entries.append({'sha': sha, 'at': at, 'actor': {'kind': 'ai', 'name': 'AI'} if ai else {'kind': 'person', 'name': author},
                            'kind': kind, 'args': args, 'text': subject[:TEXT_MAX],
                            'files': sorted(mine)[:FILES_MAX], 'more': max(0, len(mine) - FILES_MAX)})
        if created and (sha.startswith(created) or created.startswith(sha)):
            break
    if not entries:
        entries = [_created_from_meta(entry)]
    return {'entries': entries, 'pending': pending, 'degraded': False}
```

- [ ] **Step 4: Run tests**

Run: `python3 -B -m unittest tests.test_iter_history -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -- app/iter_history.py tests/test_iter_history.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(И): iter_history — історія ітерації з git: фільтр за шляхом/id/створенням, таблиця тем, трейлер AI, незаписані" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/iter_history.py tests/test_iter_history.py
```

---

### Task 4: `GET /api/iteration-history`, коміт AI в `/api/autosync`, тема коміту публікації (повний рівень)

**Files:**
- Modify: `app/serve.py` — `import iter_history`; GET-гілка поруч з `/api/iteration-pages`; нова функція `ai_commit(task)` поруч з `autosync()`; `_autosync`; два виклики `git_autocommit(task['dir'], f'publish: …')`; виклик `git_autocommit` усередині `autosync()` (трейлер)
- Test: `tests/test_iteration_api.py` (дописати клас)

- [ ] **Step 1: Write the failing tests** — дописати в кінець `tests/test_iteration_api.py` (перед `if __name__`):

```python
class HistoryAndAi(_Base):
    def test_history_route(self):
        self.post('/api/iteration-rename', {'id': 'it2', 'label': 'Фільтри'})
        st, body = self.jget('/api/iteration-history?id=it2')
        self.assertEqual(st, 200)
        self.assertEqual(body['id'], 'it2')
        self.assertEqual([e['kind'] for e in body['entries']][:2], ['rename', 'copy'])
        self.assertIn('pending', body)

    def test_history_route_errors(self):
        st, _ = self.jget('/api/iteration-history?id=../x')
        self.assertEqual(st, 400)
        st, body = self.jget('/api/iteration-history?id=it9')
        self.assertEqual((st, body['error']), (404, 'iteration-not-found'))

    def test_autosync_commits_ai_edits_without_gitlab(self):
        with open(os.path.join(self.x_dir, 'iterations', 'it2', 'index.html'), 'a', encoding='utf-8') as f:
            f.write('<p>AI</p>')
        st, body = self.post('/api/autosync', {})
        self.assertEqual((st, body['reason']), (200, 'no-gitlab'))
        self.assertEqual(body['ai']['it'], 'it2')
        log = _git(self.x_dir, 'log', '-1', '--format=%s%n%b')
        self.assertIn('it2: зміни AI', log)
        self.assertIn('Deai-Actor: ai', log)
        _, h = self.jget('/api/iteration-history?id=it2')
        self.assertEqual(h['entries'][0]['actor'], {'kind': 'ai', 'name': 'AI'})

    def test_autosync_clean_tree_makes_no_commit(self):
        before = _git(self.x_dir, 'rev-parse', 'HEAD')
        _, body = self.post('/api/autosync', {})
        self.assertIsNone(body['ai'])
        self.assertEqual(_git(self.x_dir, 'rev-parse', 'HEAD'), before)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -B -m unittest tests.test_iteration_api.HistoryAndAi -v`
Expected: FAIL — 404/HTML на `/api/iteration-history`, `KeyError: 'ai'`.

- [ ] **Step 3: Implement**

3a. Імпорт поруч з `import iter_trash`:

```python
import iter_history  # історія ітерації з git теки задачі (фаза И)
```

3b. GET — ПЕРЕД гілкою `if self.path.startswith('/api/iteration-pages'):`:

```python
        if self.path.startswith('/api/iteration-history'):
            q = parse_qs(urlparse(self.path).query)
            it = self._iteration_or_400(q.get('id', [''])[0])
            if it is None:
                return
            _, task = self._current_task()
            entry = next((i for i in load_meta(task).get('iterations', []) if i['id'] == it), None)
            if entry is None:
                self._send_json({'ok': False, 'error': 'iteration-not-found'}, status=404)
                return
            try:
                names = {p['page'].get('id'): p['page'].get('name') or p['page'].get('id')
                         for p in pm.flatten(pm.read_pages(_iter_dir(task, it)))}
            except (pm.TreeError, OSError, ValueError):
                names = {}
            self._send_json({'ok': True, 'id': it, **iter_history.history(task['dir'], entry, names)})
            return
```

3c. Нова функція одразу ПЕРЕД `def autosync(tid, task, gl, vcs=None):`:

```python
def ai_commit(task):
    """Правки AI окремим комітом (фаза И, Р9). Кличе `/api/autosync` (Stop-хук після кожної відповіді Claude): найсвіжіша
    СВОЯ брудна ітерація → `itN: зміни AI` з трейлером `Deai-Actor: ai`. Без пушу: пуш — справа автосинку GitLab нижче.
    Чужі ітерації не комітимо під своїм підписом (той самий принцип, що в `autosync`). Чисто → `None`."""
    meta = load_meta(task)
    _, my_key = machine_identity()
    by_id = {x['id']: x for x in meta.get('iterations', [])}
    dirty = [i for i in iter_history.dirty_iterations(task['dir'])
             if i in by_id and iteration_is_mine(by_id[i], my_key) and os.path.isdir(_iter_dir(task, i))]
    if not dirty:
        return None
    it = max(dirty, key=lambda i: _dir_mtime(_iter_dir(task, i)))
    g = git_autocommit(task['dir'], f'{it}: зміни AI\n\n{iter_history.AI_TRAILER}', push=False)
    return {'it': it, 'sha': g['sha']}
```

3d. `_autosync` — на початку тіла (після `tid, task, vcs, err = self._vcs_ctx()`) і в кожній відповіді. Оновити й докстрінг: рядок «`autosync` вимкнений у модулі — … ні відправки, ні локального автокоміту» замінити на «… ні відправки; локальний коміт правок AI (`ai_commit`, фаза И) робиться завжди».

```python
        tid, task, vcs, err = self._vcs_ctx()
        try:
            ai = ai_commit(task) if task is not None else None
        except (OSError, ValueError, subprocess.SubprocessError):
            sys.stderr.write(traceback.format_exc())   # локальний збій коміту AI не валить хук: історія просто без цього запису
            ai = None
        if err is not None or vcs is None or vcs[3] is None:
            out = {'ok': True, 'changed': False, 'reason': 'no-gitlab', 'ai': ai}
            self._send_json({**out, 'code': err.code} if err is not None else out)
            return
        if not (vcs[1].get('settings') or {}).get('autosync'):
            self._send_json({'ok': True, 'changed': False, 'reason': 'autosync-off', 'ai': ai})
            return
```

і далі: у гілці винятку — `self._send_json({**_vcs_failure(e), 'synced': False, 'changed': False, 'reason': 'offline' if offline else 'error', 'ai': ai})`; у кінці — `self._send_json({**r, 'ai': ai})`.

3e. У `autosync()` коміт автосинку теж несе трейлер (правки після відповіді Claude):

```python
    local = git_autocommit(task['dir'], f'{it}: автосинк ({"deai" if v is not None and not v[2] else "design-canvas"})\n\n{iter_history.AI_TRAILER}')
```

3f. Обидва коміти публікації (`grep -n "publish: {len(its)} iteration(s)" app/serve.py`) — додати id, щоб історія ітерації бачила публікацію:

```python
        git_autocommit(task['dir'], f'publish: {len(its)} iteration(s) · {" ".join(str(i.get("id", "")) for i in its)}')
```

(`its` в обох місцях — список ЗАПИСІВ опублікованих ітерацій, `serve.py` ~9286: `[i for i in meta['iterations'] if i.get('published')]`.)

- [ ] **Step 4: Run tests**

Run: `python3 -B -m unittest tests.test_iteration_api tests.test_iter_history tests.test_iter_trash -v`
Expected: PASS.
Run: `python3 -B -m unittest tests.test_serve tests.test_gitlab_sync tests.test_git_sync_module 2>&1 | tail -4`
Expected: OK (якщо тест перевіряє точну тему `publish:` чи `автосинк` — оновити очікування свідомо, тема тепер довша).

- [ ] **Step 5: Commit**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(И): GET /api/iteration-history, коміт правок AI у /api/autosync з трейлером, id ітерацій у темі публікації" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/serve.py tests/test_iteration_api.py
```

---

### Task 5: назва замість ідентифікатора — вкладки, картка, меню задачі (середній рівень)

**Files:**
- Modify: `app/tabs-model.js` (`tabsModel` — `title` через `cleanTitle`, `jira`), `app/tabs-view.js` (`tabHTML`), `app/tasks-home.js` (рядок `.th-krow`, aria), `app/task-menu.js` (`inBar`, aria), `app/i18n.js` (`tabTitle`, `tabClose`, `thMenuAria`, `thSearchMine`), `app/styles.css` (`.th-krow{min-height:16px}`)
- Test: `tests/tabs-view.test.mjs`, `tests/tabs-model.test.mjs`, `tests/tasks-home.test.mjs`, `tests/task-menu.test.mjs`

- [ ] **Step 1: Write/adjust failing tests**

`tests/tabs-view.test.mjs` — додати:

```js
test("фаза И: вкладка показує назву, а не ідентифікатор; підказка — назва · ключ Jira", () => {
  setLang("uk");
  const h = tabsHTML({ logoOn: false, gearOn: false, update: null, items: [
    { id: "landing-week", title: "Лендінг тижня", jira: null, active: true },
    { id: "LIGA-10001", title: "Фільтр компаній у медіа", jira: "LIGA-10001", active: false },
  ] });
  assert.match(h, /<span class="tab-id">Лендінг тижня<\/span>/);
  assert.doesNotMatch(h, /<span class="tab-id">landing-week<\/span>/);
  assert.match(h, /title="Фільтр компаній у медіа · LIGA-10001"/);
  assert.match(h, /title="Лендінг тижня"/);
  assert.match(h, /aria-label="Закрити вкладку Лендінг тижня"/);
});
```

`tests/tabs-model.test.mjs` — додати:

```js
test("фаза И: модель вкладки несе чисту назву (без префікса ключа) і ключ Jira", () => {
  const m = tabsModel({ tabs: [{ id: "LIGA-10001", title: "LIGA-10001 · Фільтр", jira: "LIGA-10001", space: null, color: null },
    { id: "x", title: "", jira: null, space: null, color: null }], activeId: "x" });
  assert.equal(m.items[0].title, "Фільтр");
  assert.equal(m.items[0].jira, "LIGA-10001");
  assert.equal(m.items[1].title, "x");
});
```

`tests/tasks-home.test.mjs` — рядки, що чекали `<span class="th-key">LIGA-7019</span>` і `<span class="th-key">boss-interface</span>` без пошуку, перевернути: ключа на картці НЕМАЄ; і новий тест — ключ видно, коли пошук збігся лише з ним (взяти той самий виклик рендера картки, що в сусідніх тестах файла, з `q: "7019"`):

```js
assert.doesNotMatch(h, /class="th-key"/);                       // без пошуку ключа немає
// з пошуком за ключем: q = "7019" (назва цього не містить)
assert.match(hq, /<span class="th-key"><mark>7019<\/mark>|<span class="th-key">LIGA-<mark>7019<\/mark><\/span>/);
```

`tests/task-menu.test.mjs` — додати:

```js
test("фаза И: меню в смузі (inBar) без «Видалити», aria — назва задачі", () => {
  setLang("uk");
  const x = { id: "landing-week", title: "Лендінг тижня", jira: "", published: "https://example.com/p" };
  const items = taskMenuItems(x, { inBar: true });
  assert.ok(!items.some((i) => i !== "sep" && i.th === "delete"));
  assert.notEqual(items[items.length - 1], "sep");
  assert.match(taskMenuHTML(x), /aria-label="Дії задачі Лендінг тижня"/);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/tabs-view.test.mjs tests/tabs-model.test.mjs tests/tasks-home.test.mjs tests/task-menu.test.mjs`
Expected: FAIL у нових/перевернутих перевірках.

- [ ] **Step 3: Implement**

`app/tabs-model.js` — імпорт і `items`:

```js
import { cleanTitle } from "./tasks-model.js";
// …у tabsModel(): 
    items: tabs.map((t) => ({
      id: t.id, title: cleanTitle(t), jira: t.jira || null, color: t.color,
      active: !homeOpen && t.id === activeId,
      claude: stateOf(t),
      news: news && Number(news[t.id]) > 0 ? Number(news[t.id]) : 0,
    })),
```

(якщо `tasks-model.js` імпортує щось із `tabs-model.js` — розірвати цикл, перенісши `cleanTitle` не треба: перевірити `grep -n "^import" app/tasks-model.js`.)

`app/tabs-view.js` — `tabHTML`:

```js
  /* Фаза И (Р1): вкладка — це назва задачі. Ідентифікатор — внутрішня річ; ключ Jira — лише в підказці. Клас `tab-id`
     лишається (на ньому стилі й живі тести), вміст — назва. */
  const name = x.title || x.id;
  const tip = esc(t("tabTitle", name, x.jira || ""));
  return `<div class="tab${x.active ? " tab--on" : ""}">`
    + `<button class="tab-main" data-act="tab" data-val="${esc(x.id)}" title="${tip}"${cur(x.active)}>`
    + `${dot}<span class="tab-id">${esc(name)}</span>${claude}${news}</button>`
    + `<button class="tab-x" data-act="tabclose" data-val="${esc(x.id)}" aria-label="${esc(t("tabClose", name))}">`
    + `${ico("x", 12)}</button></div>`;
```

`app/i18n.js` — uk:

```js
  tabTitle: (title, key) => (key ? `${title} · ${key}` : title),
  tabClose: (name) => `Закрити вкладку ${name}`,
  thMenuAria: (name) => `Дії задачі ${name}`,
  thSearchMine: 'Назва, номер, статус…',
```

en:

```js
  tabTitle: (title, key) => (key ? `${title} · ${key}` : title),
  tabClose: (name) => `Close tab ${name}`,
  thMenuAria: (name) => `Actions for ${name}`,
  thSearchMine: 'Title, number, status…',
```

(інші місця, що кличуть `tabTitle(id, title)` — `grep -n "tabTitle" app/*.js` — перевести на `(назва, ключ)`.)

`app/tasks-home.js` — у рендері картки замінити рядок `.th-krow` і aria:

```js
  /* Фаза И (Р1): ідентифікатора на картці немає. Ключ видно лише тоді, коли пошук збігся саме з ним, а не з назвою, —
     інакше незрозуміло, чому картка в результатах. Рядок `.th-krow` стоїть завжди (мін. висота): назви карток на одній лінії. */
  const ql = (q || "").trim().toLowerCase();
  const keyHit = !!ql && !cleanTitle(x).toLowerCase().includes(ql) && taskKey(x).toLowerCase().includes(ql);
  const krow = `${keyHit ? `<span class="th-key">${mark(taskKey(x), q)}</span>` : ""}`
    + `${isCur ? `<span class="th-curb">${keyHit ? "· " : ""}${esc(t("thCurrent"))}</span>` : ""}`;
```

і в шаблоні `<div class="th-krow">${krow}</div>`; `aria-label` групи — `${esc(cleanTitle(x))}`; aria кнопки «⋯» — `t("thMenuAria", cleanTitle(x))`.

`app/task-menu.js`:

```js
import { cleanTitle } from "./tasks-model.js";

/** Пункти меню: … `inBar` — меню крошки задачі в смузі (фаза И, Р2): без «Видалити» (етап Д, Р4 — лише з екрана «Задачі»). */
export function taskMenuItems(x, { trash = false, actions = [], inBar = false } = {}) {
  // …без змін до module actions…
  if (!inBar) out.push("sep", { th: "delete", icon: "trash", key: "taskDelete", kbd: "⌫", danger: true });
  return out;
}
// у taskMenuHTML:
  return `<div id="th-menu" class="cv-ctx th-menu" role="menu" aria-label="${esc(t("thMenuAria", opts.trash ? (x.title || x.id) : cleanTitle(x)))}">${items}</div>`;
```

(`taskKey` в імпорті лишити, лише якщо ще використовується.)

`app/styles.css` — після `.th-krow{…}`:

```css
/* Фаза И: рядок над назвою картки стоїть завжди (часто порожній) — назви сусідніх карток на одній лінії. */
.th-krow{min-height:16px}
```

- [ ] **Step 4: Run tests**

Run: `node --test tests/*.test.mjs 2>&1 | tail -8`
Expected: усі PASS. Тести, що досі чекають id у вкладці/картці (`tests/tabs-view.test.mjs`, `tests/tasks-home.test.mjs`, `tests/i18n*.test.mjs`) — оновити свідомо під Р1, не обходити.

- [ ] **Step 5: Commit**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(И): назва задачі замість ідентифікатора — вкладки, картки, меню; ключ лише в підказці й при збігу пошуку" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/tabs-model.js app/tabs-view.js app/tasks-home.js app/task-menu.js app/i18n.js app/styles.css tests/tabs-view.test.mjs tests/tabs-model.test.mjs tests/tasks-home.test.mjs tests/task-menu.test.mjs
```

---

### Task 6: смуга «задача / ітерація» і дропдаун задачі (середній рівень)

**Files:**
- Modify: `app/bar-model.js` (зона 1: `title` першою), `app/shell-bar.js` (`crumbTask` замість `crumbTitle`, роздільник, `barHTML`), `app/app.js` (`barState`: `taskActs`, `taskPreview`; дії `tren`, `ttags`, `tmodact`; `editTaskTags` бере рядок і з `curTaskList`), `app/i18n.js`, `app/styles.css`
- Test: `tests/shell-bar.test.mjs`, `tests/bar-model.test.mjs`

- [ ] **Step 1: Write/adjust failing tests** (`tests/shell-bar.test.mjs`)

Тест «назва — після крошки ітерації … не контрол» (рядки ~40–46) замінити на:

```js
test("фаза И (Р2): спершу задача, потім «/», потім ітерація; задача — кнопка з дропдауном", () => {
  setLang("uk");
  const h = html({ taskTitle: 'Картка "клієнта"' });
  const iTask = h.indexOf('data-dd="task"'), iSep = h.indexOf('class="crumb-sep"'), iIter = h.indexOf('data-dd="iter"');
  assert.ok(iTask > 0 && iTask < iSep && iSep < iIter, "задача / ітерація");
  assert.match(h, /<button class="ctl crumb crumb--title" data-dd="task" aria-haspopup="true" aria-expanded="false" title="Картка &quot;клієнта&quot;">/);
  assert.ok(h.indexOf("crumb--title") < h.indexOf('class="zone zone-2"'));
});

test("фаза И (Р2): дропдаун задачі — Перейменувати, Мітки, превʼю, дії модулів; без «Видалити»", () => {
  setLang("uk");
  const st = { ...S({ taskTitle: "Лендінг" }), openDd: "task", taskPreview: "https://example.com/p",
    taskActs: [{ key: "notes/ping", label: "Пінг" }] };
  const h = barHTML(barModel(st), st);
  for (const a of ['data-act="tren"', 'data-act="ttags"', 'data-act="tprev"', 'data-act="tmodact" data-val="notes/ping"']) assert.match(h, new RegExp(a));
  assert.doesNotMatch(h, /data-act="tdel"|taskDelete/);
});

test("фаза И (Р2): без ітерації — лише задача, без роздільника", () => {
  const h = html({ hasIteration: false, taskTitle: "Т" });
  assert.match(h, /data-dd="task"/);
  assert.doesNotMatch(h, /crumb-sep/);
});
```

Тести, що чекали `crumb--flat crumb--title`/«не контрол» (зокрема рядок ~59 «на екрані Задачі назва зайва», ~136) — лишити змістовно: на «Задачах» крошки задачі нема; в макеті є.

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/shell-bar.test.mjs tests/bar-model.test.mjs`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app/bar-model.js` — у гілці макета: спершу `title`, потім `iter`:

```js
  const zone1 = [];
  /* Фаза И (Р2): «задача / ітерація» — задача першою (порядок власника 23.11.2026). */
  zone1.push({ id: "title", tier: 0, label: s.taskTitle || s.taskId || "" });
  if (s.hasIteration) {
    zone1.push({ /* …той самий обʼєкт iter, без змін… */ });
  }
```

(видалити старий `zone1.push({ id: "title", … })` після блоку ітерації.)

`app/shell-bar.js` — `crumbTitle` замінити на:

```js
/* Фаза И (Р2): задача — ПЕРША крошка й кнопка. Дропдаун — ті самі пункти, що «⋯» картки, крім «Видалити» (етап Д, Р4).
   Клас `crumb--title` лишається: на ньому правило ширини `#bar .crumb.crumb--title` і живі тести. */
function crumbTask(model, openDd, state) {
  const c = model.zone1.find((x) => x.id === "title");
  if (!c) return "";
  const open = openDd === "task";
  const acts = Array.isArray(state?.taskActs) ? state.taskActs : [];
  const prev = typeof state?.taskPreview === "string" && /^https?:\/\//i.test(state.taskPreview) ? state.taskPreview : "";
  const dd = open ? `<div class="dd dd--task">
    ${ddItem({ act: "tren", icon: "pencil", title: t("taskRename"), marks: '<kbd>F2</kbd>' })}
    ${ddItem({ act: "ttags", icon: "sliders", title: t("taskTagsMenu") })}
    ${prev ? ddItem({ act: "tprev", val: prev, icon: "ext", title: t("taskPreviewOpen") }) : ""}
    ${acts.length ? `<div class="dd-sep"></div>${acts.map((a) => ddItem({ act: "tmodact", val: a.key, icon: "puzzle", title: a.label })).join("")}` : ""}
  </div>` : "";
  return `<div class="ddhost crumb-h crumb--task">`
    + `<button class="ctl crumb crumb--title" data-dd="task" aria-haspopup="true" aria-expanded="${open}" title="${esc(c.label)}">`
    + `${ico("task")}<span class="txt">${esc(c.label)}</span>${ico("chevdown", 14, "ico caret")}</button>${dd}</div>`;
}
```

У `barHTML` гілка макета:

```js
  const iter = crumbIter(model, openDd, state?.iterUi ?? null, Array.isArray(state?.modActs) ? state.modActs : []);
  const zone1 = home
    ? `${spaceChip(model, state, openDd)}${homeCrumbs(model)}`
    : `<div class="crumbs">${crumbTask(model, openDd, state)}${iter ? `<span class="crumb-sep" aria-hidden="true">/</span>${iter}` : ""}</div>`;
```

(`crumbIter` отримує новий третій параметр у Task 7; тут — лише передати `state?.iterUi ?? null` замість `!!state?.iterDelAsk`. До Task 7 `crumbIter` ігнорує обʼєкт так само, як ігнорував би `false`.)

`app/app.js` — у `barState()` поруч із `modActs`:

```js
    taskActs: actionItems(modExtNow(), 'task'),
    /* Превʼю задачі для пункту дропдауна задачі (фаза И): той самий адресат, що в «Опублікувати». */
    taskPreview: previewTarget(curTask, spaceNow())?.url || '',
```

У `BAR_ACTIONS`:

```js
  /* Дропдаун крошки задачі (фаза И, Р2). */
  tren: () => renameTaskFromTab(currentTaskId),
  ttags: () => editTaskTags(currentTaskId),
  tprev: (url) => { if (/^https?:\/\//i.test(url || '')) window.open(url, '_blank', 'noopener'); },
  tmodact: (key) => runModuleAction(key, 'task', currentTaskId, null),
```

`editTaskTags(id)` — рядок задачі брати й поза екраном «Задачі»:

```js
  const row = (homeData?.mine || []).find((y) => y.id === id) || (curTaskList || []).find((y) => y.id === id);
```

(перевірити, що рядки `curTaskList` несуть `tags` — `/api/tasks`, `serve.py` ~2364; `focusBack` для смуги — крошка задачі: `bar.querySelector('[data-dd="task"]')`, коли картки нема.)

`app/i18n.js` — ключ `taskRename` (uk «Перейменувати», en «Rename»), якщо такого ще нема (`grep -n "taskRename\b" app/i18n.js`); `taskTagsMenu`/`taskPreviewOpen` уже є.

`app/styles.css` — крошка-кнопка задачі світла (як у прототипі) і роздільник:

```css
/* Фаза И (Р2): задача — кнопка першою в смузі; назва яскрава, як у прототипі. */
#bar button.crumb--title .txt{color:var(--hi)}
#bar .crumbs>.crumb-sep{padding:0 2px}
```

- [ ] **Step 4: Run tests**

Run: `node --test tests/*.test.mjs 2>&1 | tail -8`
Expected: PASS (оновити свідомо тести порядку крошок у `tests/bar-model.test.mjs`).

- [ ] **Step 5: Commit**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(И): смуга «задача / ітерація», дропдаун задачі (перейменувати, мітки, превʼю, дії модулів)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/bar-model.js app/shell-bar.js app/app.js app/i18n.js app/styles.css tests/shell-bar.test.mjs tests/bar-model.test.mjs
```

---

### Task 7: перелік ітерацій з «⋯», поле, питання, кошик (середній рівень)

**Files:**
- Modify: `app/shell-bar.js` (`crumbIter`, нові `iterRow`, `iterMenu`, `initials`), `app/app.js` (стан `iterUi`, дії, клавіші, `createIteration`, `deleteIteration`, `restoreIteration`, позиція меню рядка; прибрати `iterDelAsk`, `delitask`, `pillMenu`), `app/i18n.js`, `app/styles.css`
- Test: `tests/shell-bar.test.mjs`

- [ ] **Step 1: Write/adjust failing tests** (`tests/shell-bar.test.mjs`)

Тести «пункт видалення — delitask» (~859) і «dupit < modact < delitask» (~890) замінити на:

```js
const IT = (o = {}) => S({ iterList: [
  { id: "it1", label: "Іт.1", note: "Чернетка", pub: false, onGl: false, author: "Олена Д.", mine: true },
  { id: "it2", label: "Іт.2", note: "Фільтри", pub: true, onGl: true, author: "Марта К.", mine: false, origin: { it: "it2" } },
  { id: "it3", label: "Іт.3", note: "Правки", pub: false, onGl: false, author: "Олена Д.", mine: true },
], iterId: "it3", openDd: "iter", ...o });
const itHtml = (o) => { const s = IT(o); return barHTML(barModel(s), s); };

test("фаза И (Р3): рядок — «Іт.N · назва», без підпису автора; чужа — кружок ініціалів з підказкою", () => {
  setLang("uk");
  const h = itHtml();
  assert.match(h, /<span class="dd-t">Іт\.3 · Правки<\/span>/);
  assert.doesNotMatch(h, /dd-sub">· Олена/);
  assert.match(h, /<span class="it-who" title="Марта К\. · в автора це Іт\.2 — ітерація колеги[^"]*">МК<\/span>/);
  assert.equal((h.match(/class="it-more"/g) || []).length, 3);
});

test("фаза И (Р3): під переліком лише «Нова ітерація»", () => {
  const h = itHtml();
  assert.match(h, /data-act="newit"/);
  for (const a of ["renit", "dupit", "delitask", "modact"]) assert.doesNotMatch(h, new RegExp(`data-act="${a}"`));
});

test("фаза И (Р4): меню рядка — праворуч, пункти й дії модулів над ЦІЄЮ ітерацією; єдина — «Видалити» вимкнене", () => {
  setLang("uk");
  const h = itHtml({ iterUi: { menu: "it2", ren: null, del: null }, modActs: [{ key: "notes/ping", label: "Пінг" }] });
  assert.match(h, /<div class="dd dd--itmenu" role="menu" data-for="it2">/);
  for (const a of ['data-act="itren" data-val="it2"', 'data-act="itdup" data-val="it2"', 'data-act="ithist" data-val="it2"',
    'data-act="itmodact" data-val="it2::notes/ping"', 'data-act="itdel" data-val="it2"']) assert.match(h, new RegExp(a));
  const one = barHTML(barModel(S({ iterList: [{ id: "it1", label: "Іт.1", note: "", mine: true }], iterId: "it1", openDd: "iter",
    iterUi: { menu: "it1", ren: null, del: null } })), S({ openDd: "iter", iterUi: { menu: "it1", ren: null, del: null } }));
  assert.match(one, /data-act="itdel" data-val="it1"[^>]*disabled/);
});

test("фаза И (Р5, Р6): поле перейменування й питання видалення стоять на місці рядка", () => {
  setLang("uk");
  const r = itHtml({ iterUi: { menu: null, ren: "it3", del: null } });
  assert.match(r, /<input id="it-ren-in" class="it-ren-in" type="text" maxlength="40" value="Правки" data-val="it3"/);
  const d = itHtml({ iterUi: { menu: null, ren: null, del: "it1" } });
  assert.match(d, /Видалити Іт\.1 · Чернетка\?/);
  assert.match(d, /data-act="itdelyes" data-val="it1"/);
  assert.match(d, /data-act="itdelno"/);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/shell-bar.test.mjs`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app/shell-bar.js` — новий `crumbIter` (повністю замінює старий; `confirmHTML` уже імпортовано):

```js
/** Ініціали для кружка чужої ітерації: перші літери двох перших слів. */
export function initials(name) {
  const w = String(name || "").trim().split(/\s+/).filter(Boolean);
  return w.slice(0, 2).map((x) => x[0].toUpperCase()).join("") || "?";
}

/* Фаза И (Р3–Р6). `ui` — `{menu, ren, del}` (id ітерації або null) зі стану смуги; `null` — нічого не розкрито. */
function iterRow(x, ui) {
  const title = x.note ? `${x.label} · ${x.note}` : x.label;
  if (ui?.ren === x.id) {
    return `<div class="it-ren">${ico("iter")}<b>${esc(x.label)} ·</b>`
      + `<input id="it-ren-in" class="it-ren-in" type="text" maxlength="40" value="${esc(x.note)}" data-val="${esc(x.id)}"`
      + ` aria-label="${esc(t("iterRenameAria", x.label))}" autocomplete="off" spellcheck="false"></div>`;
  }
  if (ui?.del === x.id) {
    return `<div class="it-cfm">${confirmHTML({ title: t("cfmDelIter", title), yes: t("menuDeleteYes"), no: t("cfmNo"),
      yesAttrs: `data-act="itdelyes" data-val="${esc(x.id)}"`, noAttrs: 'data-act="itdelno"' })}</div>`;
  }
  const tip = [x.origin ? t("iterOriginTitle", x.author, String(x.origin.it || "").replace(/^it/, "")) : x.author, t("iterForeign")]
    .filter(Boolean).join(" — ");
  const who = x.mine ? "" : `<span class="it-who" title="${esc(tip)}">${esc(initials(x.author))}</span>`;
  const marks = `${x.pub ? `<span class="dot dot--ok" title="${esc(t("markPreview"))}"></span>` : ""}${x.onGl ? ico("cloud", 13, "ico") : ""}`;
  return `<div class="it-row" data-it="${esc(x.id)}">`
    + `<button class="dd-item${x.on ? " dd-item--on" : ""}${x.mine ? "" : " dd-item--foreign"}" data-act="iter" data-val="${esc(x.id)}">`
    + `${ico("iter")}<span class="dd-body"><span class="dd-t">${esc(title)}</span></span><span class="dd-marks">${marks}${who}</span></button>`
    + `<button class="it-more" data-act="itmenu" data-val="${esc(x.id)}" aria-haspopup="menu" aria-expanded="${ui?.menu === x.id}"`
    + ` aria-label="${esc(t("iterMenuAria", title))}" title="${esc(t("iterMenuTitle"))}">${ico("dots")}</button></div>`;
}

function iterMenu(x, count, modActs) {
  const id = esc(x.id);
  return `<div class="dd dd--itmenu" role="menu" data-for="${id}">
    ${ddItem({ act: "itren", val: x.id, icon: "pencil", title: t("iterRename"), marks: "<kbd>F2</kbd>" })}
    ${ddItem({ act: "itdup", val: x.id, icon: "copy", title: t("dupIteration") })}
    ${ddItem({ act: "ithist", val: x.id, icon: "refresh", title: t("iterHistory") })}
    ${modActs.length ? `<div class="dd-sep"></div>${modActs.map((a) => ddItem({ act: "itmodact", val: `${x.id}::${a.key}`, icon: "puzzle", title: a.label })).join("")}` : ""}
    <div class="dd-sep"></div>
    ${ddItem({ act: "itdel", val: x.id, icon: "trash", title: t("iterDelete"), danger: true, why: count <= 1 ? t("iterDelOnly") : "" })}
  </div>`;
}

function crumbIter(model, openDd, ui = null, modActs = []) {
  const it = model.zone1.find((x) => x.id === "iter");
  if (!it) return "";
  const open = openDd === "iter";
  const items = it.items || [];
  const marks = `<span class="crumb-marks">
    ${it.pub ? `<span class="dot dot--ok" title="${esc(t("markPreview"))}"></span>` : ""}
    ${it.onGl ? ico("cloud", 13, "ico") : ""}</span>`;
  const menuFor = ui?.menu ? items.find((x) => x.id === ui.menu) : null;
  const dd = open ? `<div class="dd dd--iters">
    ${items.map((x) => iterRow(x, ui)).join("")}${items.length ? '<div class="dd-sep"></div>' : ""}
    ${ddItem({ act: "newit", icon: "plus", title: t("newIteration"), sub: t("newIterationSub") })}
  </div>${menuFor ? iterMenu(menuFor, items.length, modActs) : ""}` : "";
  const foreign = it.mine ? "" : " crumb--foreign";
  const foreignTitle = it.mine ? "" : ` title="${esc([
    it.origin ? t("iterOriginTitle", it.author || "", String(it.origin.it || "").replace(/^it/, "")) : "",
    t("iterForeign"),
  ].filter(Boolean).join(" — "))}"`;
  return `<div class="ddhost crumb-h crumb--iter">
    <button class="ctl crumb crumb--iter${foreign}" data-dd="iter"${foreignTitle}
      aria-expanded="${open}" aria-haspopup="true">
      ${ico("iter")}<span class="txt txt--fix">${esc(it.label)}</span>
      <span class="txt txt--soft">· ${esc(it.note)}</span>${marks}
      ${ico("chevdown", 14, "ico caret")}</button>
    ${dd}
  </div>`;
}
```

(`ddItem` з `why` уже ставить `disabled`; щоб тест бачив `data-act="itdel" data-val="it1"… disabled` в одному тегу — `ddItem` так і робить.)

`app/i18n.js` — uk / en:

```js
  iterRename: 'Перейменувати',            // en: 'Rename'
  iterDelete: 'Видалити',                 // en: 'Delete'
  iterHistory: 'Історія змін',            // en: 'Change history'
  iterDelOnly: 'єдина ітерація',          // en: 'the only iteration'
  iterMenuAria: (l) => `Дії з ітерацією ${l}`,   // en: (l) => `Actions for ${l}`
  iterMenuTitle: 'Дії з ітерацією',       // en: 'Iteration actions'
  iterRenameAria: (l) => `Назва ${l}`,    // en: (l) => `Name of ${l}`
  iterDeleted: (l) => `${l} — видалено`,  // en: (l) => `${l} deleted`
  iterRestore: 'Повернути',               // en: 'Restore'
  iterRestoredAs: (l) => `Повернуто як ${l}`,    // en: (l) => `Restored as ${l}`
  iterRestoreFailed: (l) => `Не вдалося повернути ${l}`, // en: (l) => `Couldn’t restore ${l}`
  newIterationSub: 'копія обраної',       // en: 'a copy of the selected one'
```

`app/styles.css` (поруч із `.dd-item--foreign`):

```css
/* ── Фаза И: перелік ітерацій з «⋯» ── */
.dd--iters{width:330px;max-width:330px}
.it-row{position:relative}
.it-row>.dd-item{padding-right:40px}
.dd-marks{display:inline-flex;align-items:center;gap:6px;flex:none}
.it-more{position:absolute;right:5px;top:50%;transform:translateY(-50%);width:var(--h-sm);height:var(--h-sm);
  border:0;background:none;border-radius:var(--r-sm);color:var(--mid);display:grid;place-items:center;opacity:0;cursor:pointer}
.it-row:hover .it-more,.it-row:focus-within .it-more,.it-row:has(.dd-item--on) .it-more,.it-more[aria-expanded=true]{opacity:1}
.it-more:hover,.it-more[aria-expanded=true]{background:var(--s4);color:var(--hi)}
.it-more:focus-visible{outline:2px solid var(--sel);outline-offset:-2px}
.it-who{flex:none;width:20px;height:20px;border-radius:50%;display:grid;place-items:center;
  font-size:10px;font-weight:600;background:var(--s4);color:var(--hi)}
.it-ren{display:flex;align-items:center;gap:8px;padding:4px 6px 4px 10px;min-height:var(--h-ctl);
  border-radius:var(--r-sm);background:var(--s3)}
.it-ren .ico{flex:none;color:var(--mid)}
.it-ren b{flex:none;font-weight:600;color:var(--hi);font-size:13px}
.it-ren-in{flex:1;min-width:0;height:var(--h-sm);padding:0 8px;border:1px solid var(--line2);border-radius:var(--r-sm);
  background:var(--s0);color:var(--hi);font:inherit;font-size:13px;outline:none}
.it-ren-in:focus{border-color:var(--sel)}
.it-cfm{padding:2px 0}
/* Меню рядка — fixed, позицію ставить `app.js` (праворуч від переліку на висоті рядка). */
.dd--itmenu{position:fixed;top:0;left:0;min-width:210px;max-width:280px}
```

`app/app.js`:

1. Стан (замість `let iterDelAsk = false;`):

```js
/* Перелік ітерацій (фаза И): відкрите меню рядка, рядок-поле, рядок-питання — id ітерації або null. Живе лише у відкритому
   дропдауні ітерації: закриття дропдауна скидає все (`paintBar`). */
let iterUi = { menu: null, ren: null, del: null };
const IT_NONE = { menu: null, ren: null, del: null };
```

2. `barState()`: `openDd, iterUi,` замість `openDd, iterDelAsk,`.

3. `paintBar()`: замість `if (openDd !== 'iter') iterDelAsk = false;` —

```js
  if (openDd !== 'iter') iterUi = IT_NONE;
```

і в кінці `paintBar()` (після вставки розмітки) — позиція меню рядка:

```js
  const itm = bar.querySelector('.dd--itmenu');
  if (itm) {
    const row = bar.querySelector(`.it-row[data-it="${CSS.escape(itm.dataset.for)}"]`);
    const list = bar.querySelector('.dd--iters');
    if (row && list) positionCtxMenu(itm, { x: list.getBoundingClientRect().right + 6, y: row.getBoundingClientRect().top - 5 });
  }
```

4. Делегація кліку смуги — замість рядка з `delitask` вставити:

```js
  /* Фаза И: дії, що лишають дропдаун ітерації ВІДКРИТИМ (меню рядка, поле, питання, нова/копія, видалення). */
  if (act === 'itmenu') { iterUi = { ...IT_NONE, menu: iterUi.menu === el.dataset.val ? null : el.dataset.val }; paintBar(); bar.querySelector('.dd--itmenu .dd-item')?.focus(); return; }
  if (act === 'itren') { iterUi = { ...IT_NONE, ren: el.dataset.val }; paintBar(); focusItRen(); return; }
  if (act === 'itdel') { iterUi = { ...IT_NONE, del: el.dataset.val }; paintBar(); bar.querySelector('.it-cfm .cfm-no')?.focus(); return; }
  if (act === 'itdelno') { iterUi = IT_NONE; paintBar(); return; }
  if (act === 'itdelyes') { deleteIteration(el.dataset.val); return; }
  if (act === 'newit') { createIteration(picked); return; }
  if (act === 'itdup') { createIteration(el.dataset.val); return; }
```

5. `BAR_ACTIONS` — прибрати `newit: dupIteration`; лишити `dupit: dupIteration`, `renit`, `delit` (їх кличе ⌘K); додати:

```js
  /* Меню рядка ітерації (фаза И, Р4): історія та дії модулів над ЦІЄЮ ітерацією (`id::ключ`). */
  ithist: (id) => openHistory(id),
  itmodact: (v) => { const i = String(v).indexOf('::'); if (i > 0) runModuleAction(v.slice(i + 2), 'iteration', currentTaskId, v.slice(0, i)); },
```

(`modact` у `BAR_ACTIONS` прибрати, якщо його більше ніхто не кличе: `grep -n "'modact'\|\"modact\"\|act === 'modact'" app/*.js` — палітра має свій шлях.) `openHistory` зʼявиться в Task 8; до того — заглушки немає: Task 7 комітить `ithist`, лише разом із Task 8, АБО тимчасово `ithist: () => {}` і тест цього не перевіряє. Обрати перше: якщо Task 8 іде одразу після, `ithist` додати в Task 8.

6. Нові функції поруч із `dupIteration`:

```js
/** «Нова ітерація» / «Дублювати» в переліку (фаза И): копія `from`, поле назви одразу відкрите (примітка — назва джерела). */
async function createIteration(from) {
  const src = (curTask?.iterations || []).find((x) => x.id === from);
  const note = (src?.label_text || '').replace(new RegExp(`^Іт\\.${itNum(from)}\\s*(?:·\\s*)?`), '');
  try {
    const r = await post('/api/iteration', { from, note });
    picked = r.iteration.id;
    openDd = 'iter';
    iterUi = { ...IT_NONE, ren: r.iteration.id };
    await refreshGitlab(); await render();
    focusItRen();
  } catch (e) { tellError(t('errTDupIter'), e.message); }
}

function focusItRen() {
  const inp = bar.querySelector('#it-ren-in');
  if (inp) { inp.focus({ preventScroll: true }); inp.select(); }
}

let itRenSaving = false;
/** Зберегти поле перейменування: назва ітерації (`label`, ≤40), порожнє — прибрати `label`. */
async function saveItRen(inp) {
  if (itRenSaving || !inp) return;
  const id = inp.dataset.val;
  const it = (curTask?.iterations || []).find((x) => x.id === id);
  const next = inp.value.trim();
  iterUi = IT_NONE;
  const was = (it?.label_text || '').replace(new RegExp(`^Іт\\.${itNum(id)}\\s*(?:·\\s*)?`), '');
  if (!it || next === was) { paintBar(); return; }
  itRenSaving = true;
  try { await post('/api/iteration-rename', { id, label: next }); await render(); }
  catch (e) { paintBar(); tellError(t('errTRenameIter'), e.message); }
  finally { itRenSaving = false; }
}

/** Видалити ітерацію з переліку: кошик на сервері, «Повернути» в тості 8 с. */
async function deleteIteration(id) {
  const it = (curTask?.iterations || []).find((x) => x.id === id);
  const label = it?.label_text || id;
  iterUi = IT_NONE;
  try {
    const r = await post('/api/iteration-delete', { id });
    if (picked === id) picked = null;
    if (histOpen?.id === id) closeHistory();
    await render();
    toast(t('iterDeleted', label), { ms: 8000, action: { label: t('iterRestore'), run: () => restoreIteration(r.trash, label) } });
  } catch (e) { paintBar(); tellError(t('errTDeleteIter'), e.message); }
}

async function restoreIteration(slot, label) {
  try {
    const r = await post('/api/iteration-restore', { trash: slot });
    picked = r.id;
    await render();
    if (r.renamed) toast(t('iterRestoredAs', r.iteration?.label_text || `Іт.${itNum(r.id)}`));
  } catch (e) { toast(t('iterRestoreFailed', label)); }
}
```

(`histOpen`/`closeHistory` — Task 8; якщо Task 7 комітиться раніше, рядок `if (histOpen?.id === id) closeHistory();` додати в Task 8.) Перевірити сигнатуру `toast(msg, { action, ms })` — параметр `ms` уже є; `render()` — повертає проміс (якщо ні — прибрати `await`).

7. Клавіші й втрата фокуса поля — делеговано на `bar`:

```js
bar.addEventListener('keydown', (ev) => {
  const inp = ev.target.closest?.('#it-ren-in');
  if (inp) {
    if (ev.key === 'Enter') { ev.preventDefault(); saveItRen(inp); }
    else if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); iterUi = IT_NONE; paintBar(); bar.querySelector('.it-row .dd-item--on')?.focus(); }
    return;
  }
  const row = ev.target.closest?.('.it-row');
  if (!row) return;
  if (ev.key === 'F2') { ev.preventDefault(); iterUi = { ...IT_NONE, ren: row.dataset.it }; paintBar(); focusItRen(); }
  else if (ev.key === 'F10' && ev.shiftKey) { ev.preventDefault(); iterUi = { ...IT_NONE, menu: row.dataset.it }; paintBar(); bar.querySelector('.dd--itmenu .dd-item')?.focus(); }
});
bar.addEventListener('focusout', (ev) => { if (ev.target.id === 'it-ren-in') saveItRen(ev.target); });
bar.addEventListener('contextmenu', (ev) => {
  const row = ev.target.closest?.('.it-row');
  if (!row) return;
  ev.preventDefault();
  iterUi = { ...IT_NONE, menu: row.dataset.it };
  paintBar();
  bar.querySelector('.dd--itmenu .dd-item')?.focus();
});
```

(якщо глобальний обробник Esc закриває дропдаун раніше — `stopPropagation` у полі цього не допускає; перевірити порядок слухачів: `grep -n "'Escape'" app/app.js`.)

8. Прибрати: `iterDelAsk` (усі згадки), гілку `if (act === 'delitask')`, мертвий `pillMenu` (`grep -n "pillMenu" app/app.js` — лише коментарі-згадки лишити ні, оновити на «перелік ітерацій»).

- [ ] **Step 4: Run tests**

Run: `node --test tests/*.test.mjs 2>&1 | tail -8`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(И): перелік ітерацій — «⋯» рядка праворуч, поле назви, питання видалення, кошик з «Повернути», ініціали чужої" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/shell-bar.js app/app.js app/i18n.js app/styles.css tests/shell-bar.test.mjs
```

---

### Task 8: панель «Історія змін» (середній рівень)

**Files:**
- Create: `app/iter-history-view.js`
- Modify: `app/index.html` (`#hist-panel`), `app/app.js` (`histOpen`, `openHistory`, `closeHistory`, `histSync` у `paintBar`, делегація панелі, `ithist`/`histcur` у `BAR_ACTIONS`, закриття при видаленні), `app/shell-palette.js` (команда), `app/i18n.js`, `app/styles.css`
- Test: `tests/iter-history-view.test.mjs` (новий), `tests/shell-palette.test.mjs`

- [ ] **Step 1: Write the failing tests** (`tests/iter-history-view.test.mjs`)

```js
import assert from "node:assert/strict";
import test from "node:test";
import { histHTML, dayKey } from "../app/iter-history-view.js";
import { setLang } from "../app/i18n.js";

const NOW = new Date("2026-11-23T15:00:00");
const E = (o) => ({ sha: "a", at: "2026-11-23T14:32:00", actor: { kind: "person", name: "Олена Д." }, kind: "other",
  args: {}, text: "", files: [], more: 0, ...o });

test("групи днів: Сьогодні, Вчора, ДД.ММ.РРРР", () => {
  setLang("uk");
  assert.equal(dayKey("2026-11-23T09:00:00", NOW), "Сьогодні");
  assert.equal(dayKey("2026-11-22T23:59:00", NOW), "Вчора");
  assert.equal(dayKey("2026-11-20T10:00:00", NOW), "20.11.2026");
});

test("шапка, записи, AI фіолетовий, файли з «ще N», час ГГ:ХХ", () => {
  setLang("uk");
  const h = histHTML({ label: "Іт.5", entries: [
    E({ kind: "ai", actor: { kind: "ai", name: "AI" }, args: { synced: false }, files: ["a.html", "b.css"], more: 2 }),
    E({ at: "2026-11-21T18:40:00", kind: "copy", args: { from: "it4", note: "Мобільна" } }),
  ], pending: null }, { now: NOW });
  assert.match(h, /<span class="panel-title">Історія · Іт\.5<\/span>/);
  assert.match(h, /data-act="histclose"/);
  assert.match(h, /<span class="hist-av hist-av--ai">AI<\/span>/);
  assert.match(h, /Макет змінено/);
  assert.match(h, /a\.html · b\.css · ще 2/);
  assert.match(h, /<span class="hist-time">14:32<\/span>/);
  assert.match(h, /Створено як копію Іт\.4 · Мобільна/);
  assert.match(h, /<span class="hist-av">ОД<\/span>/);
  assert.ok(h.indexOf("Сьогодні") < h.indexOf("21.11.2026"));
});

test("незаписані зміни — першими, без автора", () => {
  setLang("uk");
  const h = histHTML({ label: "Іт.5", entries: [E({ kind: "publish" })], pending: { files: ["x.html"], more: 0, at: "2026-11-23T14:50:00" } }, { now: NOW });
  assert.ok(h.indexOf("Незаписані зміни") < h.indexOf("Опубліковано"));
  assert.match(h, /hist-e--pending/);
});

test("невідома тема — як є; недоступна історія — один рядок; текст екранується", () => {
  setLang("uk");
  const h = histHTML({ label: "Іт.1", entries: [E({ kind: "other", text: "<b>x</b>" })], pending: null, degraded: true }, { now: NOW });
  assert.match(h, /&lt;b&gt;x&lt;\/b&gt;/);
  assert.match(h, /Історія недоступна/);
});
```

Плюс у `tests/shell-palette.test.mjs`: є ітерація → є команда `{ id: "ithist", act: "histcur" }`; немає ітерації → немає.

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/iter-history-view.test.mjs tests/shell-palette.test.mjs`
Expected: FAIL — модуля немає.

- [ ] **Step 3: Implement**

`app/iter-history-view.js`:

```js
/**
 * Панель «Історія змін» ітерації (фаза И, Р7). Чиста розмітка з відповіді `GET /api/iteration-history`; проводка — `app.js`.
 * Записи від новіших, групи днів «Сьогодні» / «Вчора» / ДД.ММ.РРРР. Тексти — за `kind` (i18n), `text` — запасний для `other`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { initials } from "./shell-bar.js";

const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

/** Підпис дня запису відносно `now` (локальний час машини). */
export function dayKey(at, now = new Date()) {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "";
  if (ymd(d) === ymd(now)) return t("today");
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (ymd(d) === ymd(y)) return t("yesterday");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

const hhmm = (at) => { const d = new Date(at); return Number.isNaN(d.getTime()) ? "" : `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const itTag = (id) => t("iterTag", String(id || "").replace(/^it/, ""));

function what(e) {
  const a = e.args || {};
  switch (e.kind) {
    case "create": return a.note ? `${t("histCreate")} · ${a.note}` : t("histCreate");
    case "copy": return t("histCopy", itTag(a.from), a.note || "");
    case "merge": return t("histMerge", (a.from || []).map(itTag).join(", "));
    case "rename": return t("histRename", a.name || "");
    case "restore": return t("histRestore");
    case "delete": return t("histDelete");
    case "page-new": return t("histPageNew", a.name || a.page || "");
    case "page-rename": return t("histPageRename", a.name || a.page || "");
    case "page-move": return t("histPageMove", a.name || a.page || "");
    case "tree": return t("histTree");
    case "publish": return t("histPublish");
    case "ai": return a.synced ? `${t("histAi")} · ${t("histSynced")}` : t("histAi");
    case "sync": return t("histSync");
    default: return e.text || "";
  }
}

const filesLine = (files, more) => {
  const list = [...(files || []), ...(more > 0 ? [t("histMore", more)] : [])];
  return list.length ? `<div class="hist-files">${esc(list.join(" · "))}</div>` : "";
};

function entryHTML(e) {
  const ai = e.actor?.kind === "ai";
  const name = ai ? "AI" : (e.actor?.name || "");
  return `<div class="hist-e"><span class="hist-av${ai ? " hist-av--ai" : ""}">${esc(ai ? "AI" : initials(name))}</span>`
    + `<div class="hist-b"><div class="hist-t">${esc(what(e))}</div>${name ? `<div class="hist-m">${esc(name)}</div>` : ""}`
    + `${filesLine(e.files, e.more)}</div><span class="hist-time">${esc(hhmm(e.at))}</span></div>`;
}

export function histHTML({ label, entries = [], pending = null, degraded = false }, { now = new Date() } = {}) {
  const groups = [];
  for (const e of entries) {
    const k = dayKey(e.at, now);
    const g = groups[groups.length - 1];
    if (g && g.k === k) g.items.push(e); else groups.push({ k, items: [e] });
  }
  const pend = pending ? `<div class="hist-e hist-e--pending"><span class="hist-av">•</span>`
    + `<div class="hist-b"><div class="hist-t">${esc(t("histPending"))}</div>${filesLine(pending.files, pending.more)}</div>`
    + `<span class="hist-time">${esc(hhmm(pending.at))}</span></div>` : "";
  return `<div class="insp-top cmt-top">${ico("refresh", 16)}<span class="panel-title">${esc(t("histTitle", label))}</span>`
    + `<button type="button" class="icob" data-act="histclose" aria-label="${esc(t("histClose"))}" title="${esc(t("histClose"))}">${ico("x")}</button></div>`
    + `<div class="insp-body hist-body">${degraded ? `<p class="hist-deg">${esc(t("histDegraded"))}</p>` : ""}${pend}`
    + groups.map((g) => `<div class="hist-day">${esc(g.k)}</div>${g.items.map(entryHTML).join("")}`).join("")
    + `</div>`;
}
```

(якщо `shell-bar.js` імпортує щось важке, що тягне DOM, — винести `initials` в `app/esc.js`-подібний маленький модуль `app/initials.js` і імпортувати звідти в обох місцях.)

`app/i18n.js` — uk / en:

```js
  histTitle: (l) => `Історія · ${l}`,               // en: (l) => `History · ${l}`
  histClose: 'Закрити історію',                     // en: 'Close history'
  histPending: 'Незаписані зміни',                  // en: 'Unsaved changes'
  histDegraded: 'Історія недоступна',               // en: 'History is unavailable'
  histCreate: 'Створено',                           // en: 'Created'
  histCopy: (tag, note) => `Створено як копію ${tag}${note ? ` · ${note}` : ''}`,   // en: `Created as a copy of ${tag}…`
  histMerge: (list) => `Зібрано зі сторінок ітерацій ${list}`,  // en: `Built from pages of ${list}`
  histRename: (n) => (n ? `Перейменовано на «${n}»` : 'Назву прибрано'),  // en: (n) => (n ? `Renamed to “${n}”` : 'Name removed')
  histRestore: 'Повернуто з кошика',                // en: 'Restored from trash'
  histDelete: 'Переміщено в кошик',                // en: 'Moved to trash'
  histPageNew: (n) => `Додано сторінку «${n}»`,      // en: `Page “${n}” added`
  histPageRename: (n) => `Сторінку «${n}» перейменовано`,  // en: `Page “${n}” renamed`
  histPageMove: (n) => `Сторінку «${n}» переміщено`, // en: `Page “${n}” moved`
  histTree: 'Змінено дерево сторінок',              // en: 'Page tree changed'
  histPublish: 'Опубліковано в превʼю',             // en: 'Published to preview'
  histAi: 'Макет змінено',                          // en: 'Mockup changed'
  histSynced: 'у GitLab',                           // en: 'in GitLab'
  histSync: 'Синхронізовано з GitLab',              // en: 'Synced with GitLab'
  histMore: (n) => `ще ${n}`,                        // en: (n) => `${n} more`
  iterHistoryPal: 'Історія ітерації',               // en: 'Iteration history'
```

(`today`/`yesterday`/`iterTag` — перевірити, що ключі є: `grep -n "today:\|yesterday:\|iterTag:" app/i18n.js`; немає — додати «Сьогодні»/«Вчора», en «Today»/«Yesterday».)

`app/index.html` — після `#mod-panel`:

```html
<div id="hist-panel" class="insp hist" hidden aria-label="Історія ітерації"></div>
```

`app/styles.css`:

```css
/* ── Фаза И: панель «Історія змін» — четверта права панель (ширина `--insp-w`, як у решти) ── */
body.with-hist .cv-stage,body.with-hist .cv-canvas{width:calc(100% - var(--insp-w))}
body.with-panel.with-hist .cv-canvas{width:calc(100% - var(--panel-w) - var(--insp-w))}
body.with-panel.panel-collapsed.with-hist .cv-canvas{width:calc(100% - var(--panel-rail-w) - var(--insp-w))}
.hist-day{padding:14px 4px 6px;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim)}
.hist-day:first-child,.hist-deg+.hist-day,.hist-e--pending+.hist-day{padding-top:2px}
.hist-e{display:grid;grid-template-columns:22px minmax(0,1fr) auto;gap:10px;align-items:start;padding:8px 6px;border-radius:var(--r-sm)}
.hist-e:hover{background:var(--s3)}
.hist-e--pending .hist-t{color:var(--open)}
.hist-av{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:10px;font-weight:600;
  background:var(--s4);color:var(--hi)}
.hist-av--ai{background:var(--local-pin);color:#fff}
.hist-b{min-width:0}
.hist-t{font-size:13px;line-height:1.35;color:var(--hi);overflow-wrap:anywhere}
.hist-m{margin-top:2px;font-size:12px;color:var(--dim)}
.hist-files{margin-top:4px;font:11.5px/1.45 var(--mono);color:var(--dim);overflow-wrap:anywhere}
.hist-time{font-size:12px;color:var(--dim);font-variant-numeric:tabular-nums;padding-top:1px}
.hist-deg{margin:0 0 8px;font-size:12px;color:var(--dim)}
```

(перевірити правило `body.with-mod` у `styles.css` ~784–788 і повторити рівно ті селектори, що є там; `css-guards`/`css-tokens` тести можуть вимагати токенів замість `#fff` — тоді взяти `var(--on-sel)` чи наявний токен білого на `--local-pin`: `grep -n "local-pin" app/styles.css`.)

`app/app.js`:

```js
import { histHTML } from "./iter-history-view.js";
const histEl = document.getElementById('hist-panel');
/* Історія ітерації (фаза И, Р7): `{id, seq}` відкритої або null. Права панель одна — історія поступається іншим (`histSync`). */
let histOpen = null;
let histSeq = 0;

async function openHistory(id) {
  if (!id || homeOpen || mode === 'canvas') return;
  if (cmtOpen) setCommentsOpen(false);
  closeModTool();
  const api = inspectorApi();
  if (api?.on) api.set(false);
  const seq = ++histSeq;
  histOpen = { id, seq };
  const label = (curTask?.iterations || []).find((x) => x.id === id)?.label_text || id;
  histEl.innerHTML = histHTML({ label, entries: [], pending: null });
  histEl.hidden = false;
  document.body.classList.add('with-hist');
  paintBar();
  try {
    const r = await api(`/api/iteration-history?id=${encodeURIComponent(id)}`);
    if (histOpen?.seq !== seq) return;                    // за час запиту відкрили іншу чи закрили
    histEl.innerHTML = histHTML({ label, entries: r.entries || [], pending: r.pending || null, degraded: !!r.degraded });
  } catch (e) {
    if (histOpen?.seq !== seq) return;
    histEl.innerHTML = histHTML({ label, entries: [], pending: null, degraded: true });
  }
}

function closeHistory() {
  if (!histOpen) return;
  histOpen = null;
  histEl.hidden = true;
  histEl.innerHTML = '';
  document.body.classList.remove('with-hist');
}

/** Права панель одна: історія закривається, коли відкрилась інша панель, «Задачі», «Огляд» чи ітерація зникла. */
function histSync() {
  if (!histOpen) return;
  const gone = !(curTask?.iterations || []).some((x) => x.id === histOpen.id);
  if (homeOpen || mode === 'canvas' || cmtOpen || modOpen || inspectorApi()?.on || gone) closeHistory();
}

histEl.addEventListener('click', (ev) => {
  if (ev.target.closest('[data-act="histclose"]')) { closeHistory(); paintBar(); }
});
```

(`api(path)` — наявний GET-хелпер `app.js` (~766), кидає `Error` з `status`/`code` на не-2xx; `histSync()` викликати в `paintBar()` поруч із `modSync()`; у `deleteIteration` з Task 7 — рядок `if (histOpen?.id === id) closeHistory();`; у перемикачі задачі (функція, що забуває стан задачі — «Забути ВСЕ, що належить ОДНІЙ задачі») — `closeHistory()`.)

`BAR_ACTIONS`:

```js
  ithist: (id) => openHistory(id),
  /* ⌘K «Історія ітерації» — для поточної (`picked`, інакше найновішої). */
  histcur: () => openHistory(picked || (curTask?.iterations || []).at(-1)?.id),
```

`app/shell-palette.js` — після `renit`/`dupit` (група `gIter`):

```js
    out.push({ id: "ithist", group: "gIter", labelKey: "iterHistoryPal", icon: "refresh", act: "histcur" });
```

- [ ] **Step 4: Run tests**

Run: `node --test tests/*.test.mjs 2>&1 | tail -8`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -- app/iter-history-view.js tests/iter-history-view.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(И): панель «Історія змін» ітерації — групи днів, AI окремо, незаписані зміни; ⌘K «Історія ітерації»" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/iter-history-view.js app/index.html app/app.js app/shell-palette.js app/i18n.js app/styles.css tests/iter-history-view.test.mjs tests/shell-palette.test.mjs
```

---

### Task 9: живі тести (середній рівень)

**Files:**
- Create: `tests/live/iterations-list.test.mjs`
- Modify: `tests/live/tabs.test.mjs`, `tests/live/shell-bar.test.mjs` (рядок з `delitask`), `tests/live/canvas.test.mjs` (рядки 3081–3113: `newit` + діалог, `renit` у дропдауні), `tests/live/_port.mjs` (нова смуга портів для нового файла, напр. 35000 — перевірити вільну)

- [ ] **Step 1: Write the live test** `tests/live/iterations-list.test.mjs` (за зразком `tests/live/tabs.test.mjs`: `startServer`, `taskFixture`, `chromium`; сервер — тимчасовий, вигадані дані):

```js
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 35000;

async function boot(t) {
  const { dir } = taskFixture({ html: () => "<!doctype html><h1>Фікстура</h1>" });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, title: "Лендінг тижня" });
  t.after(() => child.kill());
  const post = (p, b) => fetch(url + p, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(b) }).then((r) => r.json());
  await post("/api/iteration", { from: "it1", note: "Друга" });
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-dd="iter"]');
  return { page, url, post };
}

const rows = (page) => page.$$eval("#bar .dd--iters .dd-t", (els) => els.map((e) => e.textContent.trim()));

test("смуга: задача перша, вкладка — назва", async (t) => {
  const { page } = await boot(t);
  const order = await page.evaluate(() => {
    const a = document.querySelector('#bar [data-dd="task"]'), b = document.querySelector('#bar [data-dd="iter"]');
    return !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  assert.ok(order, "задача / ітерація");
  assert.equal((await page.textContent('#tabs .tab--on .tab-id')).trim(), "Лендінг тижня");
});

test("перейменування в рядку: F2/меню → Enter зберігає; Esc скасовує", async (t) => {
  const { page } = await boot(t);
  await page.click('#bar [data-dd="iter"]');
  await page.hover('#bar .it-row[data-it="it2"]');
  await page.click('#bar .it-more[data-val="it2"]');
  await page.click('#bar .dd--itmenu [data-act="itren"]');
  await page.fill("#it-ren-in", "Фільтри");
  await page.press("#it-ren-in", "Enter");
  await page.waitForFunction(() => [...document.querySelectorAll("#bar .dd--iters .dd-t")].some((e) => /Іт\.2 · Фільтри/.test(e.textContent)));
  assert.ok((await rows(page)).includes("Іт.2 · Фільтри"));
});

test("«Нова ітерація» → новий рядок одразу з полем назви", async (t) => {
  const { page } = await boot(t);
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar [data-act="newit"]');
  await page.waitForSelector("#it-ren-in");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "it-ren-in");
});

test("видалення: питання в рядку → тост «Повернути» → ітерація повертається", async (t) => {
  const { page, url } = await boot(t);
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar .it-more[data-val="it1"]');
  await page.click('#bar .dd--itmenu [data-act="itdel"]');
  await page.click('#bar .it-cfm [data-act="itdelyes"]');
  await page.waitForSelector('#cv-toast.show [data-act="undo"]');
  let ids = (await (await fetch(`${url}/api/task`)).json()).iterations.map((x) => x.id);
  assert.deepEqual(ids, ["it2"]);
  await page.click('#cv-toast [data-act="undo"]');
  await page.waitForFunction(async (u) => (await (await fetch(`${u}/api/task`)).json()).iterations.length === 2, url);
  ids = (await (await fetch(`${url}/api/task`)).json()).iterations.map((x) => x.id);
  assert.deepEqual(ids, ["it1", "it2"]);
});

test("історія: меню рядка → панель з записами; ⌘K-команда відкриває для поточної", async (t) => {
  const { page } = await boot(t);
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar .it-more[data-val="it2"]');
  await page.click('#bar .dd--itmenu [data-act="ithist"]');
  await page.waitForSelector("#hist-panel:not([hidden]) .hist-e");
  assert.match(await page.textContent("#hist-panel .panel-title"), /Історія · Іт\.2/);
  assert.match(await page.textContent("#hist-panel"), /Створено як копію Іт\.1/);
  await page.click('#hist-panel [data-act="histclose"]');
  assert.ok(await page.$eval("#hist-panel", (e) => e.hidden));
});

test("дропдаун задачі: без «Видалити»", async (t) => {
  const { page } = await boot(t);
  await page.click('#bar [data-dd="task"]');
  await page.waitForSelector('#bar .dd--task [data-act="tren"]');
  assert.equal(await page.$$eval('#bar .dd--task [data-act*="del"]', (els) => els.length), 0);
});
```

- [ ] **Step 2: Оновити наявні живі** — `tabs.test.mjs` (вкладка показує назву: перевірки тексту вкладки — за назвою, `data-val` лишається id), `shell-bar.test.mjs` (замість `delitask` — `.it-more` → `itdel` → `itdelyes`), `canvas.test.mjs` 3081–3113 (`newit` більше не питає примітку діалогом: поле `#it-ren-in`; `renit` у дропдауні → меню рядка `itren`).

- [ ] **Step 3: Run each live file under the lock (one at a time)**

Run (по черзі): `iterations-list`, `tabs`, `shell-bar`, `canvas`, `tasks-home`, `spaces`, `wizard`, `vercel`, `connections`, `git-sync`, `spaces-flows`, `space-tools`, `bar-narrow` — кожен:
`until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/<f>.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; echo rc=$rc`
Expected: rc=0 для кожного.

- [ ] **Step 4: Commit**

```bash
git add -- tests/live/iterations-list.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(И): живі — перелік ітерацій, кошик з «Повернути», історія, задача / ітерація; оновлено tabs/shell-bar/canvas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/live/iterations-list.test.mjs tests/live/tabs.test.mjs tests/live/shell-bar.test.mjs tests/live/canvas.test.mjs tests/live/_port.mjs
```

---

### Task 10: фінальне ревʼю й реліз (контролер)

- [ ] Фінальний ревʼюер (Sonnet, англійською) — весь диф `main..feat/tasks-iterations` проти спеки; окремо: втрата даних у кошику (rename/rmtree порядок, частковий збій), гонки `iterUi`/`render`, XSS у підписах (назви, автори, файли), паритет i18n.
- [ ] Перевірка вигляду проти прототипу (скриншоти смуги, переліку з меню, поля, питання, тосту, панелі історії) — власнику.
- [ ] `git merge main` (без rebase) → версія — наступна вільна мінорна на момент злиття → `package.json` + CHANGELOG.
- [ ] Релізний прогін: node + Python + усі живі файли під замком → охоронець забороненого списку → ff-злиття в живу теку → тег з ідентичністю neodisa → рестарт канваса за PID → `/api/update`.
- [ ] Перевірка проти живого канвасу (лише перегляд): перелік і історія на справжній задачі.
- [ ] Пуш — лише після «да» власника.
