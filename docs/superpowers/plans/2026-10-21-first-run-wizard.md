# Етап 3b «Майстер нового простору» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** майстер із чотирьох кроків (Простір → Модулі → Налаштування → Перша задача) замість діалогу «Новий простір»; задача з наявної теки на сервері; реліз 0.6.0.

**Architecture:** сервер отримує одну нову річ — поле `from` у `POST /api/task-new` (копія теки з `index.html` у першу ітерацію, з перевірками до будь-якого запису). Клієнт — три нові модулі: `wizard-model.js` (чиста логіка: секції за ролями, вибір, план записів, свіжість), `wizard-view.js` (розмітка рядками; поля модулів і результат — спільні з бічною панеллю 3a) і `wizard.js` (контролер із залежностями зверху, без імпорту `app.js`). `app.js` лише вмикає третю сторінку оверлею `#tasks-home` (`homePage === 'wiz'`) і веде туди входи.

**Tech Stack:** Python 3 stdlib (`app/serve.py`, `unittest`), ванільний ES-модульний JS (`node:test`), Playwright Chromium для живого тесту.

**Спека:** `docs/superpowers/specs/2026-10-21-first-run-wizard-design.md` — читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

- Репо: `<repo>`. Гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
- Додавати в індекс лише свої файли поіменно. **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий файл `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` — його не чіпати й не комітити.
- Кожен прогін тестів — через охоронця памʼяті: `python3 "$G" <секунд> <МБ> <команда…>` (шлях `$G` дає контролер), напр. `python3 "$G" 600 3000 npm test`. Якщо охоронця нема — сказати контролеру, а не запускати без нього.
- Не виставляти `DEAI_HOME` у шелі. Не чіпати порти 8765 і 4317, справжні `~/.deai`, `~/deai-published`, `~/.gitconfig`. Процеси зупиняти лише за PID, ніколи `pkill`/`killall` за шаблоном.
- Жодної мережі в тестах (Vercel і Supabase не вмикати там, де їхній `check` піде в мережу).
- Конвенції коду: коментарі українською; тексти інтерфейсу лише через `t()` (обидві мови `UK` і `EN` у `app/i18n.js`); кирилиці в літералах `app/**` поза словником бути не може (`tests/i18n-literals.test.mjs`); дані в розмітку лише через `esc()` з `app/esc.js`; іконки лише відомі `ico()` з `app/icons.js`; CSS лише токенами.
- ЛІГА-golden (`tests/legacy-golden.test.mjs`) мусить лишатись зеленим БЕЗ `UPDATE_GOLDEN=1`.
- Повний набір юнітів: `npm test`. Живі тести — лише послідовно: `node --test --test-concurrency=1 tests/live/<файл>`.
- Номери рядків у плані — орієнтир («≈»): шукати за назвою функції.

## Структура файлів

| файл | відповідальність |
|---|---|
| `app/serve.py` (зміна) | `adopt_scan`, `adopt_copy`, `AdoptRefused`, ліміти; `src` у `task_new`; `_adopt_source` і `from` у `Handler._task_new` |
| `app/wizard-model.js` (новий) | секції за ролями, вибір (`pickModule`/`pickNone`), рядки «Без модуля», план записів, свіжість, крок назад, назва з теки |
| `app/spaces-model.js` (зміна) | коди відмов `from-*` і `task-dir-exists` → ключі й поле форми |
| `app/connections-view.js` (зміна) | експорт `fieldHTML` (з префіксом id), `resultHTML`, `badgeHTML`, `rolesLine` |
| `app/space-dialogs.js` (зміна) | друга кнопка привітання; опції `pathTouched`/`idTouched` у `wire*`; режим `new` діалогу прибрано (Task 7) |
| `app/wizard-view.js` (новий) | розмітка чотирьох кроків |
| `app/i18n.js` (зміна) | ключі `wz*`, `welcomeOpen` |
| `app/styles.css` (зміна) | правила `.wz*` |
| `app/bar-model.js`, `app/shell-bar.js`, `app/shell-palette.js` (зміни) | крихта `crumb-wiz`, без фішки й «назад»; ⌘K без дій простору на `wiz` |
| `app/wizard.js` (новий) | контролер майстра |
| `app/app.js` (зміна) | сторінка `wiz` оверлею, входи, `openWizard`, `wizOpenTask`; прибрано `openSpaceNew` |
| `tests/test_task_from.py` (новий) | сервер: `from` |
| `tests/wizard-model.test.mjs`, `tests/wizard-view.test.mjs`, `tests/wizard-css.test.mjs`, `tests/wizard-wiring.test.mjs` (нові) | юніти |
| `tests/live/wizard.test.mjs` (новий) | живий сценарій |
| `tests/live/spaces.test.mjs`, `tests/live/spaces-flows.test.mjs` (зміни) | діалог «Новий простір» → крок 1 майстра |
| `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json` | документи й версія 0.6.0 |

---

### Task 1: Сервер — задача з наявної теки (`from` у `task-new`)

**Files:**
- Modify: `app/serve.py` (константи й функції — перед `def task_new` ≈ рядок 1816 (`class TaskRefused`); `task_new` ≈ 1824; `Handler._task_new` ≈ 6735)
- Create: `tests/test_task_from.py`
- Modify: `README.md` (таблиця API, рядок `POST /api/task-new`)

- [ ] **Step 1: Написати падаючі тести.** Створити `tests/test_task_from.py`:

```python
"""`POST /api/task-new` з `from` — задача з наявної теки (Deai 0.6.0, етап 3b; спека
`docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`, «Сервер: задача з наявної теки»).

Сервер і простори — фікстура `test_spaces_serve.Fixture`: старий простір з інтеграціями (`legacy_id`), `P` без
інтеграцій (`p_id`, `p_path`, задача `x`), порожній `E`. ⛔ Ізоляція та сама: тимчасові `HOME`/`DEAI_HOME`; справжній
`~/.deai` стереже `spaces_guard`.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_spaces_serve import Fixture, _read  # noqa: E402  (модуль сам ставить app/ і bin/ у sys.path)
import serve  # noqa: E402
import spaces_guard  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class TaskFrom(Fixture):
    """Тека-джерело — у тимчасовій теці класу; задача лягає в `P`."""

    def setUp(self):
        super().setUp()
        for p in (os.path.join(self.deai, 'spaces.json'), self.legacy_file, self.p_file):
            self.restore_bytes(p)
        self.src = tempfile.mkdtemp(prefix='adopt-src-', dir=self.tmp)
        self.addCleanup(shutil.rmtree, self.src, True)

    def made(self, tid):
        """Тека задачі, яку може лишити `task-new` (стирає cleanup)."""
        p = os.path.join(self.p_path, tid)
        self.addCleanup(shutil.rmtree, p, True)
        return p

    def put(self, rel, data=b'x'):
        p = os.path.join(self.src, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)
        return p

    def full_source(self):
        """Макет зі сміттям навколо: що копіюється, а що ні — див. `test_copies_the_folder_without_junk_and_links`."""
        self.put('index.html', b'<!doctype html><h1>Adopted</h1>')
        self.put('page.css', b'h1{color:red}')
        self.put('img/a.png', b'\x89PNG')
        self.put('sub/keep.py', b'1')                 # .py у ПІДТЕЦІ — не службове (асиметрія `_is_tool_junk`)
        self.put('.git/config', b'[core]')
        self.put('node_modules/x/i.js', b'1')
        self.put('sub/.DS_Store', b'junk')
        self.put('build.py', b'print(1)')             # службове в корені
        self.put('.canvas-state.json', b'{}')         # чужий підпис публікації
        outside = os.path.join(self.tmp, 'outside-secret.txt')
        with open(outside, 'w', encoding='utf-8') as f:
            f.write('outside')
        os.symlink(outside, os.path.join(self.src, 'link.txt'))
        os.symlink(self.tmp, os.path.join(self.src, 'linkdir'))

    def it1_files(self, tid):
        root = os.path.join(self.p_path, tid, 'iterations', 'it1')
        out = set()
        for dp, dns, fns in os.walk(root):
            for f in fns:
                out.add(os.path.relpath(os.path.join(dp, f), root))
        return out

    def test_copies_the_folder_without_junk_and_links(self):
        self.full_source()
        tdir = self.made('ad1')
        st, body = self.post('/api/task-new', {'id': 'ad1', 'title': 'Ad', 'space': self.p_id, 'from': self.src})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.it1_files('ad1'), {'index.html', 'page.css', os.path.join('img', 'a.png'),
                                                 os.path.join('sub', 'keep.py')})
        sizes = sum(len(x) for x in (b'<!doctype html><h1>Adopted</h1>', b'h1{color:red}', b'\x89PNG', b'1'))
        self.assertEqual(body['copied'], {'files': 4, 'bytes': sizes, 'skipped_links': 2})
        self.assertEqual((body['space'], body['dir']), (self.p_id, tdir))
        with open(os.path.join(tdir, 'iterations', 'it1', 'index.html'), encoding='utf-8') as f:
            self.assertIn('Adopted', f.read(), 'стартовий макет замість теки-джерела')
        self.assertIn('ad1', _read(self.p_file)['tasks'])
        its = json.load(open(os.path.join(tdir, 'iterations.json'), encoding='utf-8'))['iterations']
        self.assertEqual([x['id'] for x in its], ['it1'])
        self.assertTrue(os.path.isfile(os.path.join(self.src, 'build.py')), 'джерело змінилось')

    def test_tilde_is_expanded(self):
        home_src = os.path.join(self.home, 'mock-tilde')
        os.makedirs(home_src, exist_ok=True)
        self.addCleanup(shutil.rmtree, home_src, True)
        with open(os.path.join(home_src, 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<h1>T</h1>')
        self.made('ad2')
        st, body = self.post('/api/task-new', {'id': 'ad2', 'space': self.p_id, 'from': '~/mock-tilde'})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.it1_files('ad2'), {'index.html'})

    def refused(self, payload, status, code):
        st, body = self.post('/api/task-new', payload)
        self.assertEqual((st, body.get('ok'), body.get('code')), (status, False, code), body)
        return body

    def assert_nothing(self, tid):
        self.assertFalse(os.path.lexists(os.path.join(self.p_path, tid)), 'тека задачі зʼявилась')
        self.assertNotIn(tid, _read(self.p_file)['tasks'])

    def test_only_a_space_without_integrations(self):
        self.put('index.html')
        before = _read(self.legacy_file)
        self.refused({'id': 'ad3', 'space': self.legacy_id, 'from': self.src}, 400, 'from-needs-plain-space')
        self.assertEqual(_read(self.legacy_file), before)
        self.refused({'id': 'ad3', 'space': self.p_id, 'from': self.src, 'gitlab': {'repo': 'r', 'path': 'p'}},
                     400, 'from-needs-plain-space')
        self.assert_nothing('ad3')

    def test_bad_from_values(self):
        for bad in (5, '', '   ', None):
            with self.subTest(bad=bad):
                if bad is None:
                    continue                          # `from: null` — поля нема (див. наступний тест)
                self.refused({'id': 'ad4', 'space': self.p_id, 'from': bad}, 400, 'bad-request')
        self.assert_nothing('ad4')

    def test_from_null_means_no_from(self):
        self.made('ad4n')
        st, body = self.post('/api/task-new', {'id': 'ad4n', 'space': self.p_id, 'from': None})
        self.assertEqual(st, 200, body)
        self.assertNotIn('copied', body)

    def test_not_a_folder_or_no_index(self):
        self.refused({'id': 'ad5', 'space': self.p_id, 'from': os.path.join(self.src, 'nope')}, 400, 'from-not-found')
        f = self.put('file.txt')
        self.refused({'id': 'ad5', 'space': self.p_id, 'from': f}, 400, 'from-not-found')
        self.refused({'id': 'ad5', 'space': self.p_id, 'from': self.src}, 400, 'from-no-index')
        target = self.put('real.html')
        os.symlink(target, os.path.join(self.src, 'index.html'))
        self.refused({'id': 'ad5', 'space': self.p_id, 'from': self.src}, 400, 'from-no-index')
        self.assert_nothing('ad5')

    def test_the_folder_must_not_contain_the_task_folder(self):
        with open(os.path.join(self.p_path, 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<h1>space root</h1>')
        self.addCleanup(os.remove, os.path.join(self.p_path, 'index.html'))
        self.refused({'id': 'ad6', 'space': self.p_id, 'from': self.p_path}, 400, 'from-contains-space')
        parent = os.path.dirname(self.p_path)
        with open(os.path.join(parent, 'index.html'), 'w', encoding='utf-8') as f:
            f.write('<h1>parent</h1>')
        self.addCleanup(os.remove, os.path.join(parent, 'index.html'))
        self.refused({'id': 'ad6', 'space': self.p_id, 'from': parent}, 400, 'from-contains-space')
        self.assert_nothing('ad6')

    def test_the_task_folder_must_not_exist_yet(self):
        self.put('index.html')
        existing = self.made('ad7')
        os.makedirs(existing)
        with open(os.path.join(existing, 'mine.txt'), 'w', encoding='utf-8') as f:
            f.write('чужий файл')
        self.refused({'id': 'ad7', 'space': self.p_id, 'from': self.src}, 409, 'task-dir-exists')
        self.assertEqual(os.listdir(existing), ['mine.txt'], 'чужу теку зачеплено')
        self.assertNotIn('ad7', _read(self.p_file)['tasks'])

    def test_too_big_by_files_and_by_bytes(self):
        self.put('index.html', b'12345')
        self.put('a.css', b'12345')
        self.put('b.css', b'12345')
        with mock.patch.object(serve, 'ADOPT_MAX_FILES', 2):
            body = self.refused({'id': 'ad8', 'space': self.p_id, 'from': self.src}, 413, 'from-too-big')
        self.assertEqual(body['files'], 3)
        with mock.patch.object(serve, 'ADOPT_MAX_BYTES', 9):
            body = self.refused({'id': 'ad8', 'space': self.p_id, 'from': self.src}, 413, 'from-too-big')
        self.assertGreater(body['bytes'], 9)
        self.assert_nothing('ad8')

    def test_a_bad_task_id_is_refused_before_any_scan(self):
        self.put('index.html')
        with mock.patch.object(serve, 'adopt_scan', side_effect=AssertionError('обхід до перевірки id')):
            self.refused({'id': 'bad id', 'space': self.p_id, 'from': self.src}, 400, 'bad-task-id')

    def test_a_failure_mid_copy_leaves_nothing(self):
        self.put('index.html')
        self.put('a.css')
        self.put('b.css')
        real = shutil.copy2
        calls = []

        def flaky(s, d, *a, **k):
            calls.append(s)
            if len(calls) == 2:
                raise OSError('disk full')
            return real(s, d, *a, **k)

        self.made('ad9')
        with mock.patch.object(serve.shutil, 'copy2', flaky):
            st, body = self.post('/api/task-new', {'id': 'ad9', 'space': self.p_id, 'from': self.src})
        self.assertEqual((st, body['code']), (500, 'task-create-failed'), body)
        self.assert_nothing('ad9')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Переконатись, що тести падають.**
  Run: `python3 "$G" 300 2000 python3 -m unittest tests.test_task_from -v` (з кореня репо; якщо `tests` не пакет — `cd tests && python3 -m unittest test_task_from -v`).
  Expected: FAIL — `from` ігнорується (200 там, де чекаємо відмову), `copied` нема, `serve.ADOPT_MAX_FILES` нема.

- [ ] **Step 3: Константи, обхід і копія.** У `app/serve.py` перед `class TaskRefused` (≈ рядок 1816) додати:

```python
# ---------- Задача з наявної теки (етап 3b, спека 2026-10-21-first-run-wizard-design.md) ----------

#: Стеля теки-джерела: випадково вибрана домашня тека чи корінь проєкту не мусить скопіювати півдиска. Константи
#: модуля — тест їх зменшує (`mock.patch.object`).
ADOPT_MAX_FILES = 2000
ADOPT_MAX_BYTES = 200 * 1024 * 1024
#: На БУДЬ-ЯКОМУ рівні теки-джерела не копіюються: історія git, залежності, сміття Finder.
_ADOPT_SKIP_ANY = frozenset({'.git', 'node_modules', '.DS_Store'})


class AdoptRefused(Exception):
    """Відмова прийняти теку-джерело: `code`, HTTP-`status` і додаткові поля тіла відповіді (`extra`)."""

    def __init__(self, code, status, message, **extra):
        super().__init__(message)
        self.code, self.status, self.extra = code, status, extra


def adopt_scan(src):
    """Обхід теки-джерела ДО будь-якого запису: `(файли, байти, пропущені посилання)`, де файли — відносні шляхи, які
    скопіює `adopt_copy`. Не копіюються ніколи: символьні посилання (файли й теки — копія лягла б вмістом поза
    текою-джерелом), `_ADOPT_SKIP_ANY` на будь-якому рівні, службове інструмента в корені (`_is_tool_junk`) і стан
    публікації `STATE_FILE` у корені (підпис чужої публікації в новій задачі збрехав би). Сокети й fifo — не файли.
    Більше `ADOPT_MAX_FILES` файлів чи `ADOPT_MAX_BYTES` байтів — `AdoptRefused('from-too-big', 413)` одразу, не
    дочитуючи (з числами на момент зупинки)."""
    files, total, links = [], 0, 0
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        rel = os.path.relpath(dirpath, src)
        top = rel == os.curdir
        keep = []
        for d in sorted(dirnames):
            if os.path.islink(os.path.join(dirpath, d)):
                links += 1
            elif d not in _ADOPT_SKIP_ANY and not (top and _is_tool_junk(d)):
                keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            p = os.path.join(dirpath, f)
            if os.path.islink(p):
                links += 1
                continue
            if f in _ADOPT_SKIP_ANY or (top and (_is_tool_junk(f) or f == STATE_FILE)):
                continue
            if not os.path.isfile(p):
                continue
            files.append(f if top else os.path.join(rel, f))
            total += os.path.getsize(p)
            if len(files) > ADOPT_MAX_FILES or total > ADOPT_MAX_BYTES:
                raise AdoptRefused('from-too-big', 413,
                                   f'the folder is too big for a mockup: over {ADOPT_MAX_FILES} files '
                                   f'or {ADOPT_MAX_BYTES // (1024 * 1024)} MB',
                                   files=len(files), bytes=total)
    return files, total, links


def adopt_copy(src, dst, files):
    """Копія переліку `adopt_scan` у `dst`. Файл, що між обходом і копією став посиланням, пропускається."""
    os.makedirs(dst, exist_ok=True)
    for rel in files:
        s = os.path.join(src, rel)
        if os.path.islink(s):
            continue
        d = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
```

- [ ] **Step 4: `src` у `task_new`.** Сигнатура: `def task_new(cfg, tid, title='', jira='', profile='united', gitlab=None, root=None, src=None, src_files=()):`. У докстрінг додати абзац:

```
    `src` — тека-джерело (`from` маршруту, вже перевірена `_adopt_source`), `src_files` — її перелік з `adopt_scan`: тоді
    перша ітерація — копія теки, а не стартовий `index.html`. Збій копії прибирає теку задачі (її створила саме ця
    спроба: маршрут відмовляє, коли тека вже існує) і летить далі як `OSError` (маршрут: 500 `task-create-failed`).
```

  Гілку `if not cloned:` (≈ рядок 1876) замінити на:

```python
    if not cloned:
        if src is not None:
            try:
                adopt_copy(src, it1, src_files)
            except OSError:
                shutil.rmtree(tdir, ignore_errors=True)
                raise
        else:
            os.makedirs(it1, exist_ok=True)
            with open(os.path.join(it1, 'index.html'), 'w', encoding='utf-8') as f:
                shown = html_escape(str(title or tid))
                f.write('<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8">'
                        f'<title>{shown}</title></head><body>'
                        f'<h1>{shown}</h1>'
                        '<p>Нова ітерація — почни проєктувати.</p></body></html>')
```

  Повідомлення автокоміту: `git_autocommit(tdir, f'task {tid}: bootstrap ({"clone from gitlab" if cloned else "from folder" if src is not None else "new"})')`.

- [ ] **Step 5: Перевірки маршруту.** У `class Handler` поруч із `_task_new` додати метод:

```python
    def _adopt_source(self, sp, tid, src, payload):
        """Перевірки `from` ДО будь-якого запису (спека 3b, «Сервер: задача з наявної теки»): `(тека, файли, байти,
        посилання)` або `None` — відмову вже надіслано. Порядок несучий: простір і тип поля — раніше за id (поле не
        для цього простору — відмова без огляду решти), id — раніше за диск (`adopt_scan` не ходить по теці заради
        задачі, якої однаково не буде)."""
        if spaces.integrations_for(sp) or payload.get('gitlab'):
            self._space_error(400, 'from-needs-plain-space', 'from is only for a space without integrations')
            return None
        if not isinstance(src, str) or not src.strip():
            self._space_error(400, 'bad-request', 'from must be a non-empty string')
            return None
        if not isinstance(tid, str) or not NAME_RE.fullmatch(tid):
            self._space_error(400, 'bad-task-id', 'bad task id')
            return None
        real = os.path.realpath(os.path.expanduser(src.strip()))
        if not os.path.isdir(real):
            self._space_error(400, 'from-not-found', 'no such folder')
            return None
        idx = os.path.join(real, 'index.html')
        if os.path.islink(idx) or not os.path.isfile(idx):
            self._space_error(400, 'from-no-index', 'the folder has no index.html')
            return None
        tdir = os.path.join(sp['path'], tid)
        if os.path.commonpath([real, os.path.realpath(tdir)]) == real:
            self._space_error(400, 'from-contains-space', 'the folder contains the task folder itself')
            return None
        if os.path.lexists(tdir):
            self._space_error(409, 'task-dir-exists', 'the task folder already exists in the space')
            return None
        try:
            files, total, links = adopt_scan(real)
        except AdoptRefused as e:
            self._space_error(e.status, e.code, str(e), **e.extra)
            return None
        except OSError as e:
            self._space_error(400, 'from-not-found', f'the folder is not readable: {type(e).__name__}')
            return None
        return real, files, total, links
```

  У `_task_new` одразу ПІСЛЯ блоку `if taken: … return` (≈ рядок 6790) і ДО `if spaces.integrations_for(sp):` додати:

```python
        # Задача з наявної теки (етап 3b). `from: null` — поля нема (як і без нього).
        adopt = None
        if payload.get('from') is not None:
            adopt = self._adopt_source(sp, tid, payload.get('from'), payload)
            if adopt is None:
                return
```

  Виклик `task_new(...)` доповнити: `src=adopt[0] if adopt else None, src_files=adopt[1] if adopt else ()`. Відповідь: `out = {**r, 'space': _space_id(sp), 'space_switched': switched}`; `if adopt: out['copied'] = {'files': len(adopt[1]), 'bytes': adopt[2], 'skipped_links': adopt[3]}`; `self._send_json(out)`. У докстрінг `_task_new` додати речення про `from` (посилання на `_adopt_source`).

- [ ] **Step 6: Тести зелені.** Run: `python3 "$G" 300 2000 python3 -m unittest tests.test_task_from -v` → PASS (11 тестів). Потім увесь Python: `python3 "$G" 900 3000 python3 -m unittest discover -s tests` → зелено (сусідні `test_spaces_serve.TaskNew` без змін).

- [ ] **Step 7: README.** Рядок таблиці API `POST /api/task-new` доповнити: «`from` — тека з `index.html`, яку сервер копіює в першу ітерацію (лише простір без інтеграцій; посилання, `.git`, `node_modules` не копіюються; ≤ 2000 файлів і 200 МБ); відповідь тоді несе `copied: {files, bytes, skipped_links}`».

- [ ] **Step 8: Commit.**
```bash
git add app/serve.py tests/test_task_from.py README.md
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(task-new): задача з наявної теки — from з перевірками до запису

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Чиста модель майстра (`app/wizard-model.js`) і коди відмов задачі

**Files:**
- Create: `app/wizard-model.js`
- Create: `tests/wizard-model.test.mjs`
- Modify: `app/spaces-model.js` (`TASK_ERR_KEYS` ≈ рядок 306, `taskErrField` ≈ 320)
- Modify: `tests/spaces-model.test.mjs` (додати тест)

- [ ] **Step 1: Падаючі тести моделі.** Створити `tests/wizard-model.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import {
  WZ_STEPS, allOk, holdersByRole, initialPick, offRows, pickModule, pickNone, pickedFor, pickedInOrder, prevStep,
  staleRoles, titleFromFolder, wizardSections, writePlan,
} from "../app/wizard-model.js";

const M = (id, roles, extra = {}) => ({ id, name: id, roles, enabled: false, status: "unchecked", settings: [], ...extra });
const LIST = [
  M("css-tokens", ["tokens"]),
  M("static-publish", ["publish"], { enabled: true, implicit: true, status: "ok" }),
  M("supabase-comments", ["comments"]),
  M("vercel-publish", ["publish"]),
];
const ids = (s) => [...s].sort();

test("кроки: чотири, у порядку спеки", () => {
  assert.deepEqual(WZ_STEPS, ["space", "modules", "settings", "task"]);
});

test("секції: ROLE_ORDER, далі інші за абеткою; модуль кількох ролей — у кожній; missing і биті записи — ні", () => {
  const list = [...LIST, M("multi", ["zeta", "publish"]), M("gone", ["publish"], { status: "missing" }),
    null, { id: 5 }, M("alpha", ["alpha"])];
  const s = wizardSections(list);
  assert.deepEqual(s.map((x) => x.role), ["publish", "comments", "tokens", "alpha", "zeta"]);
  assert.deepEqual(s[0].modules.map((e) => e.id), ["static-publish", "vercel-publish", "multi"]);
  assert.deepEqual(s.find((x) => x.role === "zeta").modules.map((e) => e.id), ["multi"]);
  assert.ok(!s.flatMap((x) => x.modules).some((e) => e.id === "gone"));
});

test("роль __proto__ — звичайна роль (Map), не прототип", () => {
  const s = wizardSections([M("x", ["__proto__"])]);
  assert.deepEqual(s.map((x) => x.role), ["__proto__"]);
  assert.deepEqual(holdersByRole([M("x", ["__proto__"], { enabled: true })]).get("__proto__"), ["x"]);
});

test("початковий вибір — поточні тримачі (зокрема неявний static-publish), не missing і не вимкнені", () => {
  assert.deepEqual(ids(initialPick(LIST)), ["static-publish"]);
  const list = [...LIST, M("gone", ["comments"], { enabled: true, status: "missing" })];
  assert.deepEqual(ids(initialPick(list)), ["static-publish"]);
});

test("тримачі за ролями: відсортовані id увімкнених", () => {
  const list = [...LIST, M("alt", ["publish"], { enabled: true })];
  assert.deepEqual(holdersByRole(list).get("publish"), ["alt", "static-publish"]);
  assert.equal(holdersByRole(list).get("tokens"), undefined);
});

test("вибрати модуль прибирає інших тримачів його ролей; невідомий id — без змін", () => {
  const p = pickModule(new Set(["static-publish"]), LIST, "vercel-publish");
  assert.deepEqual(ids(p), ["vercel-publish"]);
  assert.deepEqual(ids(pickModule(p, LIST, "css-tokens")), ["css-tokens", "vercel-publish"]);
  assert.deepEqual(ids(pickModule(p, LIST, "nope")), ["vercel-publish"]);
});

test("модуль кількох ролей: вибір прибирає тримачів УСІХ його ролей; «Без модуля» в одній ролі прибирає його цілком", () => {
  const list = [...LIST, M("multi", ["publish", "comments"])];
  let p = pickModule(new Set(["static-publish", "supabase-comments", "css-tokens"]), list, "multi");
  assert.deepEqual(ids(p), ["css-tokens", "multi"]);
  assert.equal(pickedFor(p, list, "comments"), "multi");
  p = pickNone(p, list, "comments");
  assert.deepEqual(ids(p), ["css-tokens"]);
  assert.equal(pickedFor(p, list, "publish"), null);
});

test("вибрані в порядку секцій, кожен раз", () => {
  const list = [...LIST, M("multi", ["tokens", "publish"])];
  const p = new Set(["css-tokens", "multi", "supabase-comments"].filter((x) => x !== "css-tokens"));
  assert.deepEqual(pickedInOrder(list, p).map((e) => e.id), ["multi", "supabase-comments"]);
});

test("рядки «Без модуля»: роль без вибраного, яку хтось тримає", () => {
  assert.deepEqual(offRows(LIST, new Set()).map((o) => [o.role, o.holder.id]), [["publish", "static-publish"]]);
  assert.deepEqual(offRows(LIST, new Set(["vercel-publish"])), []);
});

const form = (fields, init, cur) => ({ fields, init: { values: init, secrets: {}, erase: [] }, cur: { values: cur, secrets: {}, erase: [] } });
const F = [{ key: "folder", type: "path", required: false, value: "a" }];

test("план: enable з невключеного, settings лише змінений, disable тримача «Без модуля»", () => {
  const atPick = holdersByRole(LIST);
  const pick = new Set(["vercel-publish", "css-tokens"]);
  const forms = new Map([["css-tokens", form(F, { folder: "a" }, { folder: "a" })]]);
  const ops = writePlan({ list: LIST, pick, forms, atPick });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "vercel-publish"], ["enable", "css-tokens"]],
    "static-publish вимкне заміна (replace), окремого disable нема");
  assert.ok(ops.every((o) => o.stale.length === 0));
});

test("план: увімкнений без змін — нічого; змінений — settings", () => {
  const atPick = holdersByRole(LIST);
  const pick = new Set(["static-publish"]);
  assert.deepEqual(writePlan({ list: LIST, pick, forms: new Map([["static-publish", form(F, { folder: "a" }, { folder: " a " })]]), atPick }), []);
  const ops = writePlan({ list: LIST, pick, forms: new Map([["static-publish", form(F, { folder: "a" }, { folder: "b" })]]), atPick });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["settings", "static-publish"]]);
});

test("план: «Без модуля» для публікації — disable static-publish", () => {
  const ops = writePlan({ list: LIST, pick: new Set(), forms: new Map(), atPick: holdersByRole(LIST) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["disable", "static-publish"]]);
});

test("план: тримач кількох ролей іде з заміною в ІНШІЙ ролі — окремого disable нема", () => {
  const list = [M("multi", ["publish", "comments"], { enabled: true }), M("memo", ["publish"]), M("c2", ["comments"])];
  const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: holdersByRole(list) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "memo"]]);
});

test("план: вибраний, якого нема у свіжому списку, — gone", () => {
  const ops = writePlan({ list: LIST, pick: new Set(["static-publish", "ghost"]), forms: new Map(), atPick: holdersByRole(LIST) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["gone", "ghost"]]);
});

test("свіжість: тримачі ролі змінились після кроку 2 — stale у enable і в disable", () => {
  const atPick = holdersByRole(LIST);
  const now = LIST.map((e) => (e.id === "static-publish" ? { ...e, enabled: false } : e)).concat(M("agent", ["publish"], { enabled: true }));
  const ops = writePlan({ list: now, pick: new Set(["vercel-publish"]), forms: new Map(), atPick });
  assert.deepEqual(ops.map((o) => [o.op, o.id, o.stale]), [["enable", "vercel-publish", ["publish"]]]);
  const off = writePlan({ list: now, pick: new Set(), forms: new Map(), atPick });
  assert.deepEqual(off.map((o) => [o.op, o.id, o.stale]), [["disable", "agent", ["publish"]]]);
  assert.deepEqual(staleRoles(["publish", "tokens"], atPick, holdersByRole(now)), ["publish"]);
});

test("результати: усе ok — далі; будь-що інше — ні; порожньо — так", () => {
  assert.equal(allOk([{ kind: "ok" }, { kind: "ok" }]), true);
  assert.equal(allOk([{ kind: "ok" }, { kind: "failed" }]), false);
  assert.equal(allOk([]), true);
});

test("назад: 2→1, 3→2, 4→3, 4→2 коли крок 3 пропущено, 1→1", () => {
  assert.deepEqual([prevStep(2), prevStep(3), prevStep(4), prevStep(4, true), prevStep(1)], [1, 2, 3, 2, 1]);
});

test("назва з теки: останній сегмент без хвостового слеша; «~» і порожнє — ''", () => {
  assert.equal(titleFromFolder("~/work/landing/"), "landing");
  assert.equal(titleFromFolder("/a/b\\c"), "c");
  assert.equal(titleFromFolder("~"), "");
  assert.equal(titleFromFolder("  "), "");
  assert.equal(titleFromFolder(null), "");
});
```

- [ ] **Step 2: Переконатись, що падають.** Run: `python3 "$G" 120 1500 node --test tests/wizard-model.test.mjs` → FAIL (модуля нема).

- [ ] **Step 3: Реалізація.** Створити `app/wizard-model.js`:

```js
/**
 * Модель майстра нового простору (Deai 0.6.0, етап 3b; спека
 * `docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`). Чисті функції: ні DOM, ні fetch, ні `t()` — як
 * `connections-model.js`, на якій вона стоїть. Вхід — записи `GET /api/modules` (`{id, roles, enabled, implicit,
 * status, settings[]}`).
 *
 * Вибір кроку 2 — МНОЖИНА id модулів (`pick`), радіокнопки лише її показують: модуль кількох ролей стоїть у секції
 * кожної своєї ролі, і вибрати його = прибрати з `pick` усіх, хто ділить із ним хоч одну роль.
 *
 * ⛔ Ролі — ДАНІ (з маніфестів): мапи ролей — лише `Map` (роль `__proto__` — звичайний ключ, а не прототип).
 */
import { ROLE_ORDER, formPatch, isDirty } from "./connections-model.js";

/** Кроки майстра — у порядку спеки; номер кроку = індекс + 1. */
export const WZ_STEPS = ["space", "modules", "settings", "task"];

const list0 = (list) => (Array.isArray(list) ? list : []);
const rolesOf = (e) => [...new Set(Array.isArray(e?.roles) ? e.roles.filter((r) => typeof r === "string" && r) : [])];
/* Запис, з яким майстер працює: обʼєкт з id і не `missing` (тим місце в «Підключенні»). */
const valid = (e) => !!e && typeof e === "object" && typeof e.id === "string" && !!e.id && e.status !== "missing";
/* Тримає роль: увімкнений (зокрема неявно). Зламаний (`status: error`) теж тримає — як `roleHolders` у 3a. */
const holds = (e) => valid(e) && e.enabled === true;
const entryOf = (list, id) => list0(list).find((e) => valid(e) && e.id === id) ?? null;

/** Секції кроку 2: `[{role, modules}]` — ролі `ROLE_ORDER`, далі інші за абеткою; модуль кількох ролей — у КОЖНІЙ. */
export function wizardSections(list) {
  const byRole = new Map();
  for (const e of list0(list)) {
    if (!valid(e)) continue;
    for (const r of rolesOf(e)) {
      if (!byRole.has(r)) byRole.set(r, []);
      byRole.get(r).push(e);
    }
  }
  const named = [...byRole.keys()].filter((r) => !ROLE_ORDER.includes(r)).sort();
  return [...ROLE_ORDER.filter((r) => byRole.has(r)), ...named].map((role) => ({ role, modules: byRole.get(role) }));
}

/** Хто зараз тримає кожну роль: `Map<роль, id[]>`, id відсортовані. Знімок кроку 2 — основа «свіжості». */
export function holdersByRole(list) {
  const out = new Map();
  for (const e of list0(list)) {
    if (!holds(e)) continue;
    for (const r of rolesOf(e)) {
      if (!out.has(r)) out.set(r, []);
      out.get(r).push(e.id);
    }
  }
  for (const v of out.values()) v.sort();
  return out;
}

/** Початковий вибір: усі, хто зараз тримає хоч одну роль. */
export const initialPick = (list) => new Set(list0(list).filter((e) => holds(e) && rolesOf(e).length).map((e) => e.id));

/** Вибрати модуль: прибрати з вибору кожен інший, що ділить із ним роль (і ті, кого вже нема в списку). */
export function pickModule(pick, list, id) {
  const e = entryOf(list, id);
  if (!e) return new Set(pick);
  const mine = new Set(rolesOf(e));
  const out = new Set([...pick].filter((x) => {
    const o = entryOf(list, x);
    return !!o && !rolesOf(o).some((r) => mine.has(r) && x !== id);
  }));
  out.add(id);
  return out;
}

/** «Без модуля» в ролі: прибрати з вибору всіх, хто її тримає. */
export const pickNone = (pick, list, role) =>
  new Set([...pick].filter((x) => { const o = entryOf(list, x); return !!o && !rolesOf(o).includes(role); }));

/** Вибраний постачальник ролі (перший за порядком списку) або `null` — «Без модуля». */
export const pickedFor = (pick, list, role) =>
  list0(list).find((e) => valid(e) && pick.has(e.id) && rolesOf(e).includes(role))?.id ?? null;

/** Вибрані модулі в порядку секцій; модуль кількох ролей — один раз, на першій. */
export function pickedInOrder(list, pick) {
  const seen = new Set();
  const out = [];
  for (const s of wizardSections(list)) {
    for (const e of s.modules) {
      if (pick.has(e.id) && !seen.has(e.id)) { seen.add(e.id); out.push(e); }
    }
  }
  return out;
}

/** Рядки «Без модуля» кроку 3: ролі без вибраного постачальника, які хтось тримає, → `[{role, holder}]`. */
export function offRows(list, pick) {
  const out = [];
  for (const s of wizardSections(list)) {
    if (pickedFor(pick, list, s.role)) continue;
    for (const e of s.modules) if (holds(e)) out.push({ role: s.role, holder: e });
  }
  return out;
}

const sameIds = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

/** Ролі, тримачі яких зараз (`fresh`) не ті, що бачив крок 2 (`atPick`): запис у такій ролі не шлемо. */
export const staleRoles = (roles, atPick, fresh) =>
  roles.filter((r) => !sameIds(atPick?.get?.(r) ?? [], fresh?.get?.(r) ?? []));

/**
 * План записів кроку 3 зі СВІЖОГО списку: `[{op, id, roles, stale}]`, у порядку:
 *   gone     — вибраний, якого вже нема у списку (писати нема що; картка скаже чому);
 *   enable   — вибраний, ще не ввімкнений (контролер шле `replace: true` — згода дана вибором на кроці 2);
 *   settings — вибраний, увімкнений, форма змінена (`formPatch` → `isDirty`); без форми чи без змін — нічого;
 *   disable  — тримач ролі з «Без модуля», якого не вимикає жоден `enable`: заміна вимикає тримачів УСІХ ролей нового
 *              модуля, тож тримач кількох ролей міг піти разом із заміною в іншій ролі.
 * `forms` — `Map<id, {fields, init, cur}>`; `atPick` — `holdersByRole` списку, який бачила людина на кроці 2.
 * `stale` — ролі запису, тримачі яких змінились після кроку 2 (для `settings` не рахується: роль не міняється).
 */
export function writePlan({ list, pick, forms, atPick }) {
  const fresh = holdersByRole(list);
  const ops = [];
  for (const id of pick) if (!entryOf(list, id)) ops.push({ op: "gone", id, roles: [], stale: [] });
  const freed = new Set();
  for (const e of pickedInOrder(list, pick)) {
    const roles = rolesOf(e);
    if (e.enabled !== true) {
      const stale = staleRoles(roles, atPick, fresh);
      if (!stale.length) roles.forEach((r) => freed.add(r));
      ops.push({ op: "enable", id: e.id, roles, stale });
      continue;
    }
    const f = forms?.get?.(e.id);
    if (f && isDirty(formPatch(f.fields, f.init, f.cur))) ops.push({ op: "settings", id: e.id, roles, stale: [] });
  }
  const off = new Set();
  for (const { role, holder } of offRows(list, pick)) {
    if (off.has(holder.id) || rolesOf(holder).some((r) => freed.has(r))) continue;
    off.add(holder.id);
    ops.push({ op: "disable", id: holder.id, roles: [role], stale: staleRoles([role], atPick, fresh) });
  }
  return ops;
}

/** Чи всі результати проходу — успіх (запис прийнято й перевірка `ok`, або вимкнено). Порожньо — так. */
export const allOk = (results) => results.every((r) => r?.kind === "ok");

/** Крок «Назад»: 2→1, 3→2, 4→3; 4→2, коли крок 3 пропущено (модулі не прочитались). */
export const prevStep = (step, skipped3 = false) => (step === 4 && skipped3 ? 2 : Math.max(1, step - 1));

/** Назва задачі з теки-джерела: останній сегмент шляху без хвостових слешів; «~» і порожнє — ''. */
export function titleFromFolder(p) {
  const s = String(p ?? "").trim().replace(/[\\/]+$/, "");
  const base = s.split(/[\\/]/).pop() ?? "";
  return base === "~" ? "" : base;
}
```

  ⚠️ Звірити з тестом «свіжість»: `enable` зі `stale` НЕ звільняє ролі (`freed`), тож `disable` тієї ролі не губиться. Якщо тест `план: «Без модуля» для публікації` червоний — перевірити, що `offRows` бере `holds` зі СВІЖОГО списку.

- [ ] **Step 4: Коди відмов задачі.** У `app/spaces-model.js` до `TASK_ERR_KEYS` додати:

```js
  ["from-not-found", "wzErrFromNotFound"],
  ["from-no-index", "wzErrFromNoIndex"],
  ["from-contains-space", "wzErrFromContains"],
  ["from-too-big", "wzErrFromTooBig"],
  ["from-needs-plain-space", "wzErrFromPlain"],
  ["task-dir-exists", "wzErrTaskDirExists"],
```

  і замінити `taskErrField`:

```js
/** Поле форми задачі, про яке ключ помилки (`taskFormError`/`taskErrKey`): `title`, `id`, `from` (тека майстра) або `null`. */
const FROM_KEYS = new Set(["wzFromRequired", "wzErrFromNotFound", "wzErrFromNoIndex", "wzErrFromContains", "wzErrFromTooBig"]);
export const taskErrField = (key) => (key === "titleRequired" ? "title"
  : (key === "idBad" || key === "idTaken" || key === "wzErrTaskDirExists") ? "id"
    : FROM_KEYS.has(key) ? "from" : null);
```

  (`wzErrFromPlain` — не про поле: простір без інтеграцій людина в майстрі не вибирає.) Ключі словника зʼявляться в Task 3; до того `t()` їх не кличе ніхто.

  У `tests/spaces-model.test.mjs` додати:

```js
test("коди відмов задачі з теки → ключі й поле форми", () => {
  assert.equal(taskErrKey("from-too-big"), "wzErrFromTooBig");
  assert.equal(taskErrKey("task-dir-exists"), "wzErrTaskDirExists");
  assert.equal(taskErrField("wzErrFromNoIndex"), "from");
  assert.equal(taskErrField("wzFromRequired"), "from");
  assert.equal(taskErrField("wzErrTaskDirExists"), "id");
  assert.equal(taskErrField("wzErrFromPlain"), null);
  assert.equal(taskErrField("idTaken"), "id");
});
```
  (імпорт `taskErrKey`, `taskErrField` додати в шапку файла, якщо їх там нема.)

- [ ] **Step 5: Тести зелені.** Run: `python3 "$G" 120 1500 node --test tests/wizard-model.test.mjs tests/spaces-model.test.mjs` → PASS.

- [ ] **Step 6: Commit.**
```bash
git add app/wizard-model.js tests/wizard-model.test.mjs app/spaces-model.js tests/spaces-model.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(wizard): чиста модель майстра — секції за ролями, вибір, план записів, свіжість

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: Тексти, спільні поля й розмітка майстра (`app/i18n.js`, `app/connections-view.js`, `app/space-dialogs.js`, `app/wizard-view.js`)

**Files:**
- Modify: `app/i18n.js` (UK — поруч із блоком `cn*` ≈ рядок 860; EN — поруч із EN-блоком `cn*` ≈ 1630)
- Modify: `app/connections-view.js` (`fieldHTML` ≈ 175, `resultHTML` ≈ 228, `BADGES`/`badgeHTML` ≈ 58–70, `rolesLine` ≈ 56)
- Modify: `app/space-dialogs.js` (`welcomeHTML`, `wireSpaceDialog`, `wireTaskForm`)
- Create: `app/wizard-view.js`
- Create: `tests/wizard-view.test.mjs`
- Modify: `tests/space-dialogs.test.mjs`, `tests/connections-view.test.mjs`

- [ ] **Step 1: Словник.** У `UK` додати блок (коментар `/* Майстер нового простору (етап 3b) */`):

```js
  wzCrumb: 'Новий простір',
  wzSteps: 'Кроки майстра',
  wzStep1: 'Простір',
  wzStep2: 'Модулі',
  wzStep3: 'Налаштування',
  wzStep4: 'Перша задача',
  wzStepOf: (n, all, name) => `Крок ${n} з ${all} · ${name}`,
  wzS1Title: 'Новий простір',
  wzS1TitleEdit: 'Простір',
  wzS1Lead: 'Простір — це тека на диску. Її можна покласти в git і ділити з командою: секрети туди не потрапляють.',
  wzS1FolderHint: 'Тут житимуть задачі й space.json. Тека, що вже є простором (наприклад, зі спільного git), теж підійде — канвас підхопить її задачі й модулі.',
  wzS1FolderLocked: 'Теку створеного простору не змінити: на ній стоять його задачі.',
  wzNext: 'Далі',
  wzBack: 'Назад',
  wzCancel: 'Скасувати',
  wzClose: 'Закрити майстер',
  wzCreating: 'Створюю…',
  wzSaving: 'Зберігаю…',
  wzS2Title: 'Що підключити',
  wzS2Lead: 'Усе необовʼязкове: без модулів канвас працює повністю. Підключити чи змінити можна будь-коли в «Підключенні».',
  wzNone: 'Без модуля',
  wzInstead: (names) => `замість «${names}»`,
  wzS3Title: 'Налаштування',
  wzS3Lead: 'Заповніть поля — канвас збереже їх і одразу перевірить доступ.',
  wzS3Nothing: 'Нічого не підключаємо — і це нормально.',
  wzBadgeWill: 'Буде підключено',
  wzOffRow: (role, name, then) => `${role}: «${name}» вимкнеться — ${then}.`,
  wzOffRowPlain: (role, name) => `${role}: «${name}» вимкнеться.`,
  wzOffDone: 'Вимкнено.',
  wzStale: 'Поки ви вибирали, роль змінилась — поверніться на крок «Модулі».',
  wzSaveNext: 'Зберегти й далі',
  wzS4Title: 'Перша задача',
  wzS4Lead: 'Задача — одна фіча чи екран: у ній ітерації, сторінки, коментарі.',
  wzS4LeadHas: (n) => `Задач у просторі вже: ${n} — можна одразу перейти до них.`,
  wzSource: 'Звідки макет',
  wzSourceEmpty: 'Порожня сторінка',
  wzSourceFolder: 'Наявна тека з макетом',
  wzFromLabel: 'Тека з index.html',
  wzFromHint: 'Канвас скопіює теку в першу ітерацію; оригінал не зміниться. index.html стане першою сторінкою.',
  wzFromRequired: 'Вкажіть теку з макетом.',
  wzCreateOpen: 'Створити й відкрити',
  wzSkip: 'Пропустити',
  wzToTasks: 'До задач',
  wzAgentTitle: 'Хай зробить агент.',
  wzAgentText: 'Скажіть агенту в терміналі — він заведе задачу тим самим API:',
  wzAgentPhrase: (name) => `створи задачу «екран оплати» у просторі «${name}»`,
  wzCopy: 'Скопіювати',
  wzCopied: 'Скопійовано.',
  wzCopyFailed: 'Не вдалося скопіювати — виділіть фразу вручну.',
  wzErrFromNotFound: 'Такої теки нема або вона не читається. Шлях — повний (можна з ~).',
  wzErrFromNoIndex: 'У теці нема index.html.',
  wzErrFromContains: 'Ця тека містить сам простір — виберіть теку макета всередині нього.',
  wzErrFromTooBig: 'Тека завелика для макета (понад 2000 файлів чи 200 МБ) — виберіть теку самого макета.',
  wzErrFromPlain: 'Копіювати теку можна лише в простір без інтеграцій.',
  wzErrTaskDirExists: 'У просторі вже є тека з таким ідентифікатором — змініть його.',
  wzSkippedLinks: (n) => `Символьні посилання не скопійовано: ${n}.`,
  wzReady: (name) => `Простір «${name}» готовий. Підключення — у меню простору.`,
  wzSpaceGone: 'Простору майстра більше нема.',
  welcomeOpen: 'Відкрити наявну теку простору',
```

  У `EN` — ті самі ключі:

```js
  wzCrumb: 'New space',
  wzSteps: 'Wizard steps',
  wzStep1: 'Space',
  wzStep2: 'Modules',
  wzStep3: 'Settings',
  wzStep4: 'First task',
  wzStepOf: (n, all, name) => `Step ${n} of ${all} · ${name}`,
  wzS1Title: 'New space',
  wzS1TitleEdit: 'Space',
  wzS1Lead: 'A space is a folder on disk. You can put it in git and share it with your team: secrets never go there.',
  wzS1FolderHint: 'Tasks and space.json will live here. A folder that already is a space (say, from a shared git repo) works too — the canvas picks up its tasks and modules.',
  wzS1FolderLocked: "A created space's folder cannot change: its tasks live there.",
  wzNext: 'Next',
  wzBack: 'Back',
  wzCancel: 'Cancel',
  wzClose: 'Close the wizard',
  wzCreating: 'Creating…',
  wzSaving: 'Saving…',
  wzS2Title: 'What to connect',
  wzS2Lead: 'All optional: the canvas works fully without modules. You can connect or change them any time in Connections.',
  wzNone: 'No module',
  wzInstead: (names) => `instead of “${names}”`,
  wzS3Title: 'Settings',
  wzS3Lead: 'Fill in the fields — the canvas saves them and checks the access right away.',
  wzS3Nothing: 'Nothing to connect — and that is fine.',
  wzBadgeWill: 'Will be connected',
  wzOffRow: (role, name, then) => `${role}: “${name}” turns off — ${then}.`,
  wzOffRowPlain: (role, name) => `${role}: “${name}” turns off.`,
  wzOffDone: 'Turned off.',
  wzStale: 'The role changed while you were choosing — go back to the Modules step.',
  wzSaveNext: 'Save and continue',
  wzS4Title: 'First task',
  wzS4Lead: 'A task is one feature or screen: it holds iterations, pages and comments.',
  wzS4LeadHas: (n) => `Tasks already in this space: ${n} — you can go straight to them.`,
  wzSource: 'Where the mockup comes from',
  wzSourceEmpty: 'A blank page',
  wzSourceFolder: 'An existing mockup folder',
  wzFromLabel: 'Folder with index.html',
  wzFromHint: 'The canvas copies the folder into the first iteration; the original stays untouched. index.html becomes the first page.',
  wzFromRequired: 'Enter the mockup folder.',
  wzCreateOpen: 'Create and open',
  wzSkip: 'Skip',
  wzToTasks: 'Go to tasks',
  wzAgentTitle: 'Let the agent do it.',
  wzAgentText: 'Tell the agent in the terminal — it creates the task through the same API:',
  wzAgentPhrase: (name) => `create a task “payment screen” in the space “${name}”`,
  wzCopy: 'Copy',
  wzCopied: 'Copied.',
  wzCopyFailed: 'Could not copy — select the phrase by hand.',
  wzErrFromNotFound: 'No such folder, or it cannot be read. Use a full path (~ is fine).',
  wzErrFromNoIndex: 'The folder has no index.html.',
  wzErrFromContains: 'This folder contains the space itself — pick the mockup folder inside it.',
  wzErrFromTooBig: 'The folder is too big for a mockup (over 2000 files or 200 MB) — pick the mockup folder itself.',
  wzErrFromPlain: 'A folder can be copied only into a space without integrations.',
  wzErrTaskDirExists: 'The space already has a folder with this ID — change it.',
  wzSkippedLinks: (n) => `Symbolic links not copied: ${n}.`,
  wzReady: (name) => `The space “${name}” is ready. Connections are in the space menu.`,
  wzSpaceGone: "The wizard's space is gone.",
  welcomeOpen: 'Open an existing space folder',
```

  Охоронець (поправка після ревʼю Task 2): у `tests/spaces-state.test.mjs` тест «taskErrKey: коди task-new → ключі; … ключі є в словниках» (≈ рядок 183) доповнити новими кодами: `from-not-found` → `wzErrFromNotFound`, `from-no-index` → `wzErrFromNoIndex`, `from-contains-space` → `wzErrFromContains`, `from-too-big` → `wzErrFromTooBig`, `from-needs-plain-space` → `wzErrFromPlain`, `task-dir-exists` → `wzErrTaskDirExists` — тоді він сам перевірить, що ключі є в обох мовах.

- [ ] **Step 2: Спільні частини панелі 3a — експорт.** У `app/connections-view.js`:
  - `const rolesLine = …` → `export const rolesLine = …`;
  - `const badgeHTML = (kind) => {` → `export const badgeHTML = (kind) => {`;
  - `function fieldHTML(e, f, i, d) {` → `export function fieldHTML(e, f, i, d, prefix = "cn-f") {` і перший рядок тіла `const id = \`${prefix}-${i}\`;`. У коментар над функцією додати: «`prefix` — голова id полів: панель 3a — `cn-f` (типово), майстер — `wz-f-<картка>` (кілька карток на сторінці, id не мусять збігатися).»;
  - `function resultHTML(r) {` → `export function resultHTML(r) {`;
  - у шапку файла (перелік експортів) дописати `fieldHTML`, `resultHTML`, `badgeHTML`, `rolesLine` — «спільні з майстром 3b».
  У `tests/connections-view.test.mjs` додати:

```js
test("поле з префіксом майстра: id і похідні id (-state, -err) з префіксом; типово — cn-f", () => {
  const e = { id: "memo", settings: [] };
  const f = { key: "token", type: "secret", label: "Token", required: false, set: true };
  const h = fieldHTML(e, f, 2, { errors: { token: "cnFieldRequired" }, form: { values: {}, erase: [] }, busy: false }, "wz-f-1");
  assert.match(h, /id="wz-f-1-2"/);
  assert.match(h, /id="wz-f-1-2-state"/);
  assert.match(h, /id="wz-f-1-2-err"/);
  assert.doesNotMatch(h, /cn-f-/);
  assert.match(fieldHTML(e, f, 0, { errors: {}, form: { values: {}, erase: [] }, busy: false }), /id="cn-f-0"/);
});
```
  (додати `fieldHTML` в імпорт файла.)

- [ ] **Step 3: Привітання й опції проводки.** У `app/space-dialogs.js`:
  - `welcomeHTML()` — у `.th-welcome-act` після кнопки «Створити простір» додати другу:
    `<button class="ctl ctl--out" data-th="spaceopen">${ico("folder")}${esc(t("welcomeOpen"))}</button>`.
    У шапці файла до гачків привітання дописати `[data-th="spaceopen"]`.
  - `wireSpaceDialog(form, { mode = "new", peek, debounceMs = 300, taken = [], pathTouched: touched0 = false } = {})`; рядок `let pathTouched = false;` → `let pathTouched = touched0 === true;`. У докстрінг: «`pathTouched` — теку вже правили руками до цієї проводки (майстер перемальовує крок і проводить форму заново: без цього тека знову пішла б за назвою)».
  - `wireTaskForm(form, { taken = [], idTouched: touched0 } = {})`; рядок `let idTouched = id.value !== "";` → `let idTouched = typeof touched0 === "boolean" ? touched0 : id.value !== "";`. У докстрінг: «`idTouched` — id правили руками до цієї проводки (перемальовка майстра); без нього — як було: непорожній id вважається правленим».
  У `tests/space-dialogs.test.mjs`:
  - тест «привітання» доповнити: `assert.match(h, /<button class="ctl ctl--out" data-th="spaceopen">/);` і `assert.match(h, /Відкрити наявну теку простору/);`
  - додати два тести (заглушки `spaceForm`/`taskForm` уже є в файлі):

```js
test("`new` з `pathTouched: true`: тека за назвою не йде (перемальовка майстра не скидає ручну правку)", async () => {
  const d = spaceForm({ name: "", path: "~/mine/x" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({}), debounceMs: 1, pathTouched: true });
  d.nameI.value = "Client";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/mine/x");
  await tick(20);
});

test("форма задачі з `idTouched: false`: непорожній id (автопідстановка до перемальовки) і далі йде за назвою", () => {
  const d = taskForm("alpha");
  wireTaskForm(d.form, { taken: [], idTouched: false });
  d.title.value = "Beta";
  d.title.fire("input");
  assert.equal(d.idI.value, "beta");
});
```

- [ ] **Step 4: Падаючі тести розмітки майстра.** Створити `tests/wizard-view.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import { getLang, setLang } from "../app/i18n.js";
import { wizardHTML } from "../app/wizard-view.js";

const CYR = /[а-яіїєґА-ЯІЇЄҐ]/;
const M = (id, roles, extra = {}) => ({ id, name: id, roles, enabled: false, status: "unchecked", settings: [], ...extra });
const LIST = [
  M("static-publish", ["publish"], { enabled: true, implicit: true, status: "ok",
    settings: [{ key: "folder", type: "path", value: "{space}/publish" }] }),
  M("vercel-publish", ["publish"]),
  M("css-tokens", ["tokens"]),
];
const V = (over = {}) => ({
  step: 1, created: false, busy: false,
  s1: { name: "Клієнт", color: "space-3", path: "~/deai-work/klient", folderFirst: false },
  s2: { list: LIST, failed: null, capsError: false, pick: new Set(["static-publish"]), path: "/p" },
  s3: { cards: [], offs: [], failed: null, loading: false },
  s4: { title: "", id: "", source: "empty", from: "", spaceName: "Клієнт", tasks: 0 },
  ...over,
});

test("смужка кроків: ol з чотирьох, aria-current лише на поточному, рядок «Крок N з 4»", () => {
  const h = wizardHTML(V({ step: 2 }));
  assert.match(h, /<div class="th-in wz" data-step="2">/);
  assert.match(h, /<ol class="wz-steps" aria-label="Кроки майстра">/);
  assert.equal((h.match(/<li class="wz-step/g) ?? []).length, 4);
  assert.equal((h.match(/aria-current="step"/g) ?? []).length, 1);
  assert.match(h, /wz-step--done[\s\S]*wz-step--cur[\s\S]*wz-step--todo/);
  assert.match(h, /Крок 2 з 4 · Модулі/);
  assert.match(h, /<h1 class="th-h wz-h" id="wz-h" tabindex="-1">Що підключити<\/h1>/);
});

test("крок 1 (новий): гачки форми простору, кружки, підказки теки, «Скасувати», «Далі»", () => {
  const h = wizardHTML(V());
  assert.match(h, /<form class="wz-form" data-wz-step="1" data-form="space" data-mode="new" novalidate>/);
  assert.match(h, /<input class="cn-inp" id="sp-name" name="name" type="text" value="Клієнт"/);
  assert.match(h, /<input class="cn-inp" id="sp-path" name="path" type="text" value="~\/deai-work\/klient"/);
  assert.match(h, /<input type="hidden" name="color" value="space-3">/);
  assert.equal((h.match(/class="cv-color" role="radio"/g) ?? []).length, 6);
  assert.match(h, /id="sp-found" role="status" hidden/);
  assert.match(h, /id="sp-registered" role="status" hidden/);
  assert.match(h, /<p class="wz-err" id="wz-err" role="alert" hidden><\/p>/);
  assert.match(h, /data-a="cancel"/);
  assert.match(h, /<button type="submit" class="ctl ctl--pri" data-a="ok">Далі/);
  assert.doesNotMatch(h, /data-wz="back"/);
});

test("крок 1 після створення: режим правки — тека лише для читання з поясненням, замість «Скасувати» — «Закрити майстер»", () => {
  const h = wizardHTML(V({ created: true }));
  assert.match(h, /data-mode="edit"/);
  assert.match(h, /id="sp-path"[^>]*readonly/);
  assert.match(h, /Теку створеного простору не змінити/);
  assert.doesNotMatch(h, /data-a="cancel"/);
  assert.match(h, /data-wz="close"/);
  assert.match(h, />Простір<\/h1>/);
});

test("крок 1 зайнятий: aria-busy, кнопки вимкнені, «Створюю…»", () => {
  const h = wizardHTML(V({ busy: "save" }));
  assert.match(h, /data-form="space" data-mode="new" novalidate aria-busy="true">/);
  assert.match(h, /data-a="ok" disabled>Створюю…/);
  assert.match(h, /data-a="cancel" disabled/);
});

test("крок 2: секції-fieldset з legend, радіо на модуль + «Без модуля», вибране з pick, «типово», «замість»", () => {
  const h = wizardHTML(V({ step: 2 }));
  assert.match(h, /<fieldset class="wz-sec"><legend class="cn-sec-h">Публікація<\/legend>/);
  assert.match(h, /<input type="radio" id="wz-o-0-0" name="wz-r-0" value="static-publish" data-wz-pick data-role="publish" checked>/);
  assert.match(h, /<input type="radio" id="wz-o-0-1" name="wz-r-0" value="vercel-publish" data-wz-pick data-role="publish">/);
  assert.match(h, /<input type="radio" id="wz-o-0-none" name="wz-r-0" value="" data-wz-pick data-role="publish">/);
  assert.match(h, /<input type="radio" id="wz-o-1-none" name="wz-r-1" value="" data-wz-pick data-role="tokens" checked>/);
  assert.match(h, /типово/);
  assert.match(h, /замість «Публікація в теку»/, "Vercel замінить поточного постачальника");
  assert.match(h, /data-wz="back"/);
  assert.match(h, /data-wz="close"/);
});

test("крок 2: вантажиться — «Далі» вимкнена; не прочиталось — помилка з «Спробувати ще», «Далі» доступна", () => {
  assert.match(wizardHTML(V({ step: 2, s2: { list: null, failed: null, capsError: false, pick: new Set(), path: "" } })),
    /data-a="ok" disabled>/);
  const h = wizardHTML(V({ step: 2, s2: { list: null, failed: { code: "x", message: "boom <b>" }, capsError: false, pick: new Set(), path: "" } }));
  assert.match(h, /data-wz="retry"/);
  assert.match(h, /boom &lt;b&gt;/);
  assert.match(h, /data-a="ok">Далі/);
});

test("крок 3: картка з полями (id з префіксом картки), бейдж «Буде підключено», рядок «Без модуля», секрет порожній", () => {
  const vercel = M("vercel-publish", ["publish"], { settings: [{ key: "token", type: "secret", label: "T", set: true }] });
  const card = { entry: vercel, fields: [{ key: "token", type: "secret", label: "T", required: false, set: true }],
    values: {}, erase: [], errors: {}, result: null };
  const h = wizardHTML(V({ step: 3, s3: { cards: [card], offs: [{ role: "tokens", holder: M("css-tokens", ["tokens"], { enabled: true }), result: null }], failed: null, loading: false } }));
  assert.match(h, /<section class="cn-card wz-card" data-id="vercel-publish"/);
  assert.match(h, /id="wz-f-0-0"/);
  assert.match(h, /Буде підключено/);
  assert.match(h, /<li class="wz-off" data-id="css-tokens">/);
  assert.match(h, /вимкнеться — інспектор звіряє без токенів простору\./);
  assert.match(h, /type="password" id="wz-f-0-0"(?![^>]*value=)/);
  assert.match(h, /data-a="ok">Зберегти й далі/);
});

test("крок 3: нічого — текст «і це нормально»; зайнятий — fieldset вимкнено", () => {
  assert.match(wizardHTML(V({ step: 3 })), /Нічого не підключаємо — і це нормально\./);
  const card = { entry: M("css-tokens", ["tokens"]), fields: [], values: {}, erase: [], errors: {}, result: { kind: "ok", key: "cnCheckOk", detail: "" } };
  const h = wizardHTML(V({ step: 3, busy: "save", s3: { cards: [card], offs: [], failed: null, loading: false } }));
  assert.match(h, /<fieldset class="wz-cards" disabled>/);
  assert.match(h, /cn-res cn-res--ok/);
});

test("крок 4: поля задачі, радіо «Звідки макет», поле теки сховане до вибору, агент із фразою, «Пропустити»", () => {
  const h = wizardHTML(V({ step: 4 }));
  assert.match(h, /<form class="wz-form wz-task" data-wz-step="4" data-form="task" novalidate>/);
  assert.match(h, /id="tf-title" name="title"/);
  assert.match(h, /id="tf-id" name="id"/);
  assert.match(h, /<input type="radio" name="wz-src" value="empty" checked>/);
  assert.match(h, /<div class="cn-field" id="wz-from-f" hidden>/);
  assert.match(h, /<code class="cn-code" id="wz-phrase">створи задачу «екран оплати» у просторі «Клієнт»<\/code>/);
  assert.match(h, /data-wz="copy"/);
  assert.match(h, /data-wz="skip"[^>]*>Пропустити/);
  const f = wizardHTML(V({ step: 4, s4: { title: "", id: "", source: "folder", from: "~/m", spaceName: "X", tasks: 3 } }));
  assert.match(f, /<div class="cn-field" id="wz-from-f">/);
  assert.match(f, /value="~\/m"/);
  assert.match(f, /Задач у просторі вже: 3/);
  assert.match(f, /data-wz="skip"[^>]*>До задач/);
});

test("усе з даних екранується", () => {
  const evil = "<img src=x onerror=1>";
  const h = [
    wizardHTML(V({ s1: { name: evil, color: "space-1\" onclick=\"x", path: evil, folderFirst: false } })),
    wizardHTML(V({ step: 2, s2: { list: [M(evil, [evil])], failed: null, capsError: false, pick: new Set([evil]), path: "" } })),
    wizardHTML(V({ step: 4, s4: { title: evil, id: evil, source: "folder", from: evil, spaceName: evil, tasks: 0 } })),
  ].join("");
  assert.doesNotMatch(h, /<img/);
  assert.doesNotMatch(h, /onclick="x/);
});

test("англійська: жодної кирилиці в розмітці кожного кроку з латинськими даними", () => {
  const before = getLang();
  setLang("en");
  try {
    for (const step of [1, 2, 3, 4]) {
      const h = wizardHTML(V({ step, s1: { name: "X", color: "space-1", path: "~/x", folderFirst: false }, s4: { title: "", id: "", source: "empty", from: "", spaceName: "X", tasks: 0 } }));
      assert.doesNotMatch(h, CYR, `крок ${step}`);
    }
  } finally { setLang(before); }
});
```

- [ ] **Step 5: Переконатись, що падають.** Run: `python3 "$G" 120 1500 node --test tests/wizard-view.test.mjs tests/space-dialogs.test.mjs tests/connections-view.test.mjs` → FAIL (нема `wizard-view.js`, нових кнопок/опцій).

- [ ] **Step 6: Реалізація розмітки.** Створити `app/wizard-view.js`:

```js
/**
 * Розмітка майстра нового простору (Deai 0.6.0, етап 3b; спека
 * `docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`). Чисті будівельники рядків — ні DOM, ні fetch.
 * Логіка — `wizard-model.js`; поля модулів, бейдж і результат запису — СПІЛЬНІ з бічною панеллю 3a
 * (`connections-view.js`), щоб майстер і «Підключення» не розійшлись.
 *
 *   wizardHTML(v)   v = {step: 1..4, created, busy: false|'save', s1, s2, s3, s4}
 *     s1 = {name, color, path, folderFirst}
 *     s2 = {list|null, failed|null, capsError, pick: Set, path}
 *     s3 = {cards: [{entry, fields, values, erase, errors, result}], offs: [{role, holder, result}], failed|null, loading}
 *     s4 = {title, id, source: 'empty'|'folder', from, spaceName, tasks}
 *
 * Гачки (контракт для `wizard.js` і живих тестів): корінь `.wz[data-step]`; заголовок `#wz-h` (tabindex=-1); форма кроку
 * `form[data-wz-step]` (крок 1 — ще й `data-form="space" data-mode="new|edit"`, крок 4 — `data-form="task"`); головна
 * кнопка `[data-a="ok"]` (type=submit); «Скасувати» `[data-a="cancel"]`; інші кнопки `[data-wz="back|close|skip|copy|retry"]`;
 * радіо кроку 2 `input[data-wz-pick][data-role]` (value — id модуля, порожнє — «Без модуля»), id `wz-o-<секція>-<варіант|none>`;
 * картка кроку 3 `.wz-card[data-id]` з полями 3a (`data-cn-field`, id `wz-f-<картка>-<поле>`); рядок «Без модуля»
 * `.wz-off[data-id]`; крок 4 — `#tf-title`, `#tf-id`, `input[name="wz-src"]`, `#wz-from`; слот помилки `#wz-err`.
 * Ідентифікатори кроку 1 (`#sp-name`, `#sp-path`, `#sp-found`, `#sp-registered`, `.cv-colors`, `input[name=color]`) — ті,
 * що чекає `wireSpaceDialog`; кроку 4 (`#tf-title`, `#tf-id`) — ті, що чекає `wireTaskForm`.
 *
 * ⛔ Усе з даних — лише через `esc()`; колір — лише через `spaceColorToken`. Секрет у розмітку не потрапляє ніколи (поле
 * пароля малює `fieldHTML` 3a — завжди порожнім).
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { DETAIL_MAX, builtinText, cardView, roleHolders, roleIcon, roleKeys, whyOf } from "./connections-model.js";
import { badgeHTML, fieldHTML, modName, resultHTML, roleTitle, rolesLine } from "./connections-view.js";
import { SPACE_COLORS, spaceColorToken } from "./spaces-model.js";
import { pickedFor, wizardSections } from "./wizard-model.js";

const STEP_KEYS = ["wzStep1", "wzStep2", "wzStep3", "wzStep4"];

/** Смужка кроків: для ока — смужки, для читача екрана — назви (`.wz-step-name` візуально прихована). */
function stepsHTML(step) {
  const items = STEP_KEYS.map((k, i) => {
    const n = i + 1;
    const st = n < step ? "done" : n === step ? "cur" : "todo";
    return `<li class="wz-step wz-step--${st}"${n === step ? ' aria-current="step"' : ""}>`
      + `<span class="wz-step-bar" aria-hidden="true"></span><span class="wz-step-name">${esc(t(k))}</span></li>`;
  }).join("");
  return `<ol class="wz-steps" aria-label="${esc(t("wzSteps"))}">${items}</ol>`
    + `<p class="wz-of">${esc(t("wzStepOf", step, STEP_KEYS.length, t(STEP_KEYS[step - 1])))}</p>`;
}

const head = (titleKey, lead) => `<h1 class="th-h wz-h" id="wz-h" tabindex="-1">${esc(t(titleKey))}</h1>`
  + `<p class="wz-lead">${esc(lead)}</p>`;
const errSlot = `<p class="wz-err" id="wz-err" role="alert" hidden></p>`;
const foot = (left, right) => `<div class="wz-foot">${left}<span class="cn-grow"></span>${right}</div>`;
const btn = (attrs, label, { cls = "ctl ctl--out", icon = "", dis = false } = {}) =>
  `<button type="button" class="${cls}" ${attrs}${dis ? " disabled" : ""}>${icon ? ico(icon) : ""}${esc(label)}</button>`;
const ok = (label, dis) => `<button type="submit" class="ctl ctl--pri" data-a="ok"${dis ? " disabled" : ""}>${esc(label)}</button>`;
const backBtn = (dis) => btn('data-wz="back"', t("wzBack"), { icon: "chevleft", dis });
const closeBtn = (dis) => btn('data-wz="close"', t("wzClose"), { cls: "ctl ctl--ghost", dis });
const detail = (s) => (s ? `<span class="cn-why-detail">${esc(String(s).slice(0, DETAIL_MAX))}</span>` : "");

/* ── крок 1 · Простір ─────────────────────────────────────────────────────────────────────────────── */

function colorsHTML(colorIn, dis) {
  const color = spaceColorToken(colorIn);
  const items = SPACE_COLORS.map((c, i) => `<button type="button" class="cv-color" role="radio" data-val="${c}"`
    + ` aria-checked="${c === color}" tabindex="${c === color ? 0 : -1}" aria-label="${esc(t("spaceColorName", i + 1))}"`
    + ` style="background:var(--${c})"${dis ? " disabled" : ""}>${ico("check", 14)}</button>`).join("");
  return `<div class="cv-colors wz-colors" role="radiogroup" aria-labelledby="sp-color-l">${items}</div>`
    + `<input type="hidden" name="color" value="${color}">`;
}

function step1HTML(v) {
  const s = v.s1;
  const edit = !!v.created;
  const busy = !!v.busy;
  const dis = busy ? " disabled" : "";
  const folder = edit
    ? `<input class="cn-inp" id="sp-path" name="path" type="text" value="${esc(s.path)}" readonly aria-describedby="wz-s1-hint">
      <p class="cn-hint" id="wz-s1-hint">${esc(t("wzS1FolderLocked"))}</p>`
    : `<input class="cn-inp" id="sp-path" name="path" type="text" value="${esc(s.path)}" autocomplete="off" spellcheck="false"
        aria-describedby="sp-found sp-registered wz-s1-hint wz-err"${dis}>
      <p class="cn-hint" id="sp-found" role="status" hidden></p>
      <p class="cn-hint" id="sp-registered" role="status" hidden></p>
      <p class="cn-hint" id="wz-s1-hint">${esc(t("wzS1FolderHint"))}</p>`;
  const label = busy ? t(edit ? "wzSaving" : "wzCreating") : t("wzNext");
  const left = edit ? closeBtn(busy) : btn('data-a="cancel"', t("wzCancel"), { cls: "ctl ctl--ghost", dis: busy });
  return `${head(edit ? "wzS1TitleEdit" : "wzS1Title", t("wzS1Lead"))}
    <form class="wz-form" data-wz-step="1" data-form="space" data-mode="${edit ? "edit" : "new"}" novalidate${busy ? ' aria-busy="true"' : ""}>
      <div class="cn-field"><label class="cn-lbl" for="sp-name">${esc(t("spaceName"))}</label>
        <input class="cn-inp" id="sp-name" name="name" type="text" value="${esc(s.name)}" maxlength="60" autocomplete="off"
          spellcheck="false" placeholder="${esc(t("spaceNamePh"))}" aria-describedby="wz-err"${dis}></div>
      <div class="cn-field"><span class="cn-lbl" id="sp-color-l">${esc(t("spaceColor"))}</span>${colorsHTML(s.color, busy)}</div>
      <div class="cn-field"><label class="cn-lbl" for="sp-path">${esc(t("spaceFolder"))}</label>${folder}</div>
      ${errSlot}
      ${foot(left, ok(label, busy))}
    </form>`;
}

/* ── крок 2 · Модулі ─────────────────────────────────────────────────────────────────────────────── */

function optionHTML(e, i, j, role, s, dis) {
  const id = `wz-o-${i}-${j}`;
  const on = pickedFor(s.pick, s.list, role) === e.id;
  const desc = builtinText(e.id)?.desc;
  /* «Замість кого»: поточні тримачі ролей цього модуля (зі списку сервера), коли сам він ще не ввімкнений. */
  const instead = e.enabled === true ? [] : roleHolders(e, s.list);
  const why = e.status === "error" ? whyOf(e) : null;
  return `<label class="wz-opt" for="${id}"><input type="radio" id="${id}" name="wz-r-${i}" value="${esc(e.id)}"`
    + ` data-wz-pick data-role="${esc(role)}"${on ? " checked" : ""}${dis}>`
    + `<span class="wz-opt-body"><span class="wz-opt-top"><b>${esc(modName(e))}</b>`
    + `${e.implicit === true ? `<span class="cn-tag">${esc(t("cnImplicit"))}</span>` : ""}</span>`
    + `${desc ? `<span class="wz-opt-desc">${esc(t(desc))}</span>` : ""}`
    + `${instead.length ? `<span class="wz-opt-instead">${esc(t("wzInstead", instead.map(modName).join(", ")))}</span>` : ""}`
    + `${why ? `<span class="wz-opt-why">${ico("warn", 13)}<span>${esc(t(why.key))}${detail(why.detail)}</span></span>` : ""}`
    + `</span></label>`;
}

function noneHTML(i, role, s, dis) {
  const id = `wz-o-${i}-none`;
  const on = !pickedFor(s.pick, s.list, role);
  const k = roleKeys(role)?.none;
  return `<label class="wz-opt wz-opt--none" for="${id}"><input type="radio" id="${id}" name="wz-r-${i}" value=""`
    + ` data-wz-pick data-role="${esc(role)}"${on ? " checked" : ""}${dis}>`
    + `<span class="wz-opt-body"><span class="wz-opt-top"><b>${esc(t("wzNone"))}</b></span>`
    + `${k ? `<span class="wz-opt-desc">${esc(t(k))}</span>` : ""}</span></label>`;
}

function step2HTML(v) {
  const s = v.s2;
  const busy = !!v.busy;
  const dis = busy ? " disabled" : "";
  let body;
  let loading = false;
  if (s.capsError) {
    body = `<div class="cn-err" role="alert">${ico("warn")}<span>${esc(t("cnErrSpaceJson", s.path || ""))}</span></div>`;
  } else if (s.failed) {
    body = `<div class="cn-err" role="alert">${ico("warn")}<span>${esc(t("cnErrLoad"))}${detail(s.failed.message)}</span>`
      + `${btn('data-wz="retry"', t("retry"), { icon: "refresh" })}</div>`;
  } else if (!Array.isArray(s.list)) {
    loading = true;
    body = `<p class="cn-loading" role="status">${esc(t("cnLoading"))}</p>`;
  } else {
    body = wizardSections(s.list).map((sec, i) => {
      const k = roleKeys(sec.role)?.lead;
      return `<fieldset class="wz-sec"><legend class="cn-sec-h">${esc(roleTitle(sec.role))}</legend>`
        + `${k ? `<p class="cn-sec-lead">${esc(t(k))}</p>` : ""}<div class="wz-opts">`
        + sec.modules.map((e, j) => optionHTML(e, i, j, sec.role, s, dis)).join("")
        + noneHTML(i, sec.role, s, dis) + `</div></fieldset>`;
    }).join("");
  }
  return `${head("wzS2Title", t("wzS2Lead"))}
    <form class="wz-form" data-wz-step="2" novalidate>${body}
      ${foot(`${backBtn(busy)}${closeBtn(busy)}`, ok(t("wzNext"), busy || loading))}</form>`;
}

/* ── крок 3 · Налаштування ───────────────────────────────────────────────────────────────────────── */

function cardHTML(c, i, busy) {
  const e = c.entry;
  const badge = e.enabled === true ? badgeHTML(cardView(e).badge)
    : `<span class="cn-badge">${esc(t("wzBadgeWill"))}</span>`;
  const desc = builtinText(e.id)?.desc;
  const roles = rolesLine(e);
  const d = { errors: c.errors ?? {}, form: { values: c.values ?? {}, erase: c.erase ?? [] }, busy };
  const fields = (c.fields ?? []).map((f, j) => fieldHTML(e, f, j, d, `wz-f-${i}`)).join("");
  return `<section class="cn-card wz-card" data-id="${esc(e.id)}" aria-labelledby="wz-c-${i}">
    <div class="cn-card-top"><span class="cn-ic">${ico(roleIcon(e.roles?.[0]))}</span>
      <div class="cn-card-name"><b id="wz-c-${i}">${esc(modName(e))}</b>${roles ? `<span class="cn-card-role">${esc(roles)}</span>` : ""}</div>
      ${badge}</div>
    ${desc ? `<p class="cn-card-desc">${esc(t(desc))}</p>` : ""}
    ${fields}<div class="wz-res" data-wz-res="${esc(e.id)}">${resultHTML(c.result)}</div></section>`;
}

function offHTML(o) {
  const k = roleKeys(o.role)?.none;
  const text = k ? t("wzOffRow", roleTitle(o.role), modName(o.holder), t(k))
    : t("wzOffRowPlain", roleTitle(o.role), modName(o.holder));
  return `<li class="wz-off" data-id="${esc(o.holder.id)}">${ico("x", 13)}<span>${esc(text)}</span>${resultHTML(o.result)}</li>`;
}

function step3HTML(v) {
  const s = v.s3;
  const busy = !!v.busy;
  let body;
  if (s.loading) body = `<p class="cn-loading" role="status">${esc(t("cnLoading"))}</p>`;
  else if (s.failed) body = `<div class="cn-err" role="alert">${ico("warn")}<span>${esc(t("cnErrLoad"))}${detail(s.failed.message)}</span></div>`;
  else {
    const offs = s.offs.length ? `<ul class="wz-offs">${s.offs.map(offHTML).join("")}</ul>` : "";
    const cards = s.cards.length
      ? `<fieldset class="wz-cards"${busy ? " disabled" : ""}>${s.cards.map((c, i) => cardHTML(c, i, busy)).join("")}</fieldset>`
      : (offs ? "" : `<p class="cn-dr-none">${esc(t("wzS3Nothing"))}</p>`);
    body = offs + cards;
  }
  return `${head("wzS3Title", t("wzS3Lead"))}
    <form class="wz-form" data-wz-step="3" novalidate>${body}
      ${foot(`${backBtn(busy)}${closeBtn(busy)}`, ok(busy ? t("wzSaving") : t("wzSaveNext"), busy || s.loading))}</form>`;
}

/* ── крок 4 · Перша задача ───────────────────────────────────────────────────────────────────────── */

function step4HTML(v) {
  const s = v.s4;
  const busy = !!v.busy;
  const dis = busy ? " disabled" : "";
  const folder = s.source === "folder";
  const lead = s.tasks > 0 ? t("wzS4LeadHas", s.tasks) : t("wzS4Lead");
  const radio = (val, key) => `<label class="cn-check"><input type="radio" name="wz-src" value="${val}"`
    + `${(val === "folder") === folder ? " checked" : ""}${dis}> ${esc(t(key))}</label>`;
  const form = `<form class="wz-form wz-task" data-wz-step="4" data-form="task" novalidate${busy ? ' aria-busy="true"' : ""}>
      <div class="cn-field"><label class="cn-lbl" for="tf-title">${esc(t("newTaskTitle"))}</label>
        <input class="cn-inp" id="tf-title" name="title" type="text" value="${esc(s.title)}" autocomplete="off"
          placeholder="${esc(t("newTaskTitlePh"))}" aria-describedby="wz-err"${dis}></div>
      <div class="cn-field"><label class="cn-lbl" for="tf-id">${esc(t("newTaskId"))}</label>
        <input class="cn-inp" id="tf-id" name="id" type="text" value="${esc(s.id)}" autocomplete="off" spellcheck="false"
          aria-describedby="wz-err"${dis}></div>
      <fieldset class="wz-src"><legend class="cn-lbl">${esc(t("wzSource"))}</legend>
        ${radio("empty", "wzSourceEmpty")}${radio("folder", "wzSourceFolder")}</fieldset>
      <div class="cn-field" id="wz-from-f"${folder ? "" : " hidden"}><label class="cn-lbl" for="wz-from">${esc(t("wzFromLabel"))}</label>
        <input class="cn-inp" id="wz-from" name="from" type="text" value="${esc(s.from)}" autocomplete="off" spellcheck="false"
          placeholder="~/" aria-describedby="wz-from-hint wz-err"${dis}>
        <p class="cn-hint" id="wz-from-hint">${esc(t("wzFromHint"))}</p></div>
      ${errSlot}
      <div class="wz-acts">${ok(busy ? t("wzCreating") : t("wzCreateOpen"), busy)}</div></form>`;
  const agent = `<aside class="cn-agent wz-agent">${ico("task")}<div><b>${esc(t("wzAgentTitle"))}</b> ${esc(t("wzAgentText"))}
      <code class="cn-code" id="wz-phrase">${esc(t("wzAgentPhrase", s.spaceName))}</code>
      <div class="wz-acts">${btn('data-wz="copy"', t("wzCopy"), { icon: "copy" })}</div></div></aside>`;
  return `${head("wzS4Title", lead)}<div class="wz-two">${form}${agent}</div>
    ${foot(backBtn(busy), btn('data-wz="skip"', t(s.tasks > 0 ? "wzToTasks" : "wzSkip"), { cls: "ctl ctl--ghost", dis: busy }))}`;
}

/** Уся сторінка майстра для `#tasks-home`. */
export function wizardHTML(v) {
  const body = [step1HTML, step2HTML, step3HTML, step4HTML][v.step - 1](v);
  return `<div class="th-in wz" data-step="${v.step}">${stepsHTML(v.step)}${body}</div>`;
}
```

  ⚠️ Перевірити ключі, які розмітка бере з 3a й просторів: `spaceName`, `spaceNamePh`, `spaceColor`, `spaceFolder`, `spaceColorName`, `newTaskTitle`, `newTaskTitlePh`, `newTaskId`, `cnErrSpaceJson`, `cnErrLoad`, `cnLoading`, `cnImplicit`, `retry` — усі вже є в словнику (якщо ні — тест падає на `t()`: виправити ключ, а не додавати дубль).

- [ ] **Step 7: Тести зелені.** Run: `python3 "$G" 300 2000 node --test tests/wizard-view.test.mjs tests/space-dialogs.test.mjs tests/connections-view.test.mjs tests/i18n-keys.test.mjs tests/i18n-literals.test.mjs tests/i18n.test.mjs` → PASS. Регексп тесту, що не збігся через порядок атрибутів, правити В ТЕСТІ лише тоді, коли розмітка відповідає спеці; гачки зі шапки `wizard-view.js` — контракт, їх не міняти.

- [ ] **Step 8: Commit.**
```bash
git add app/i18n.js app/connections-view.js app/space-dialogs.js app/wizard-view.js tests/wizard-view.test.mjs tests/space-dialogs.test.mjs tests/connections-view.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(wizard): тексти й розмітка чотирьох кроків; поля модулів спільні з панеллю 3a

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Стилі майстра (`app/styles.css`) і охоронець класів

**Files:**
- Modify: `app/styles.css` (після блоку «Підключення», перед правилами логотипа й палітри ≈ рядок 1640)
- Create: `tests/wizard-css.test.mjs`

- [ ] **Step 1: Падаючий охоронець.** Створити `tests/wizard-css.test.mjs`:

```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
const norm = (s) => s.trim().replace(/\s*([>+~])\s*/g, " $1 ").replace(/\s+/g, " ");
const RULES = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ sels: m[1].split(",").map(norm), body: m[2] }));
const rule = (selector) => RULES.find((r) => r.sels.includes(norm(selector)))?.body ?? null;
const subjectOf = (sel) => sel.split(/\s*[>+~]\s*|\s+/).pop();
const isSubject = (cls) => RULES.some((r) => r.sels.some((s) => new RegExp(`\\.${cls}(?![\\w-])`).test(subjectOf(s))));

test("кожен клас `wz-*` розмітки майстра має правило, де він — суб'єкт", () => {
  const src = read("wizard-view.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  const classes = new Set();
  for (const m of src.matchAll(/class="([^"]+)"/g)) {
    for (const c of m[1].replace(/\$\{[^}]*\}/g, " ").split(/\s+/)) if (/^wz-/.test(c) && !c.endsWith("-")) classes.add(c);
  }
  for (const k of ["done", "cur", "todo"]) classes.add(`wz-step--${k}`);
  assert.ok(classes.size >= 18, `знайдено лише ${classes.size} класів — регексп зламано: ${[...classes]}`);
  const missing = [...classes].filter((c) => !isSubject(c));
  assert.deepEqual(missing, [], `класи без власного правила: ${missing.join(", ")}`);
});

test("кружки кольору на темній сторінці мають власні правила (світлі правила діалогу — лише в `.cv-ask`)", () => {
  assert.match(rule(".wz .cv-color") ?? "", /width:28px/);
  assert.match(rule('.wz .cv-color[aria-checked=true] .ico') ?? "", /display:block/);
});

test("вибраний варіант підсвічений (:has(:checked)) і має видимий фокус", () => {
  assert.ok(rule(".wz-opt:has(input:checked)"), "нема підсвітки вибраного варіанта");
  assert.ok(rule(".wz-opt:has(input:focus-visible)"), "нема кільця фокуса на картці-мітці");
});

test("назви кроків візуально приховані, але лишаються для читача екрана (не display:none)", () => {
  const b = rule(".wz-step-name") ?? "";
  assert.match(b, /position:absolute/);
  assert.doesNotMatch(b, /display:none/);
});

test("вузьке вікно: колонка на всю ширину з полями 16px, дві колонки кроку 4 — одна", () => {
  assert.match(css, /@media \(max-width:719px\)\{[^}]*\.wz\{[^}]*padding:[^}]*16px/);
  assert.match(css, /@media \(max-width:719px\)\{[\s\S]*?\.wz-two\{[^}]*grid-template-columns:1fr/);
});

test("майстер — частина `#tasks-home`: чистий перегляд ховає його разом з оверлеєм (окремого правила не треба)", () => {
  assert.match(css, /html\.cv-clean #tasks-home/);
});
```

- [ ] **Step 2: Переконатись, що падає.** Run: `python3 "$G" 60 1000 node --test tests/wizard-css.test.mjs` → FAIL.

- [ ] **Step 3: Правила.** Додати в `app/styles.css` після блоку `.cn-res…`:

```css
/* ── майстер нового простору (етап 3b): сторінка `wiz` оверлею `#tasks-home` ──────────────────────────────────────────
   Класи `wz-`; поля, картки, бейджі й результат — спільні з «Підключенням» (`cn-*`). Охоронець — `tests/wizard-css.test.mjs`.
   Кружки кольору: правила діалогу (`.cv-ask .cv-color`) світлі й прив'язані до `.cv-ask`, тож тут — свої, на темному тлі. */
.wz{max-width:760px}
.wz-steps{display:flex;gap:6px;margin:0 0 10px;padding:0;list-style:none}
.wz-step{flex:1;min-width:0}
.wz-step-bar{display:block;height:4px;border-radius:2px;background:var(--s3)}
.wz-step--done .wz-step-bar{background:var(--logo)}
.wz-step--cur .wz-step-bar{background:var(--sel)}
.wz-step--todo .wz-step-bar{background:var(--s3)}
.wz-step-name{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.wz-of{margin:0 0 18px;font-size:12px;color:var(--dim)}
.wz-h{outline:none}
.wz-h:focus-visible{outline:2px solid var(--sel);outline-offset:4px;border-radius:var(--r-sm)}
.wz-lead{margin:-6px 0 22px;max-width:640px;color:var(--mid);font-size:13.5px;line-height:1.55}
.wz-form{display:flex;flex-direction:column;gap:16px;margin:0}
.wz-colors{display:flex;gap:8px;flex-wrap:wrap}
.wz .cv-color{width:28px;height:28px;padding:0;border:1px solid var(--line2);border-radius:var(--r);
  display:inline-flex;align-items:center;justify-content:center;cursor:pointer}
.wz .cv-color .ico{display:none;color:var(--g900)}
.wz .cv-color[aria-checked=true]{box-shadow:0 0 0 2px var(--s1),0 0 0 4px var(--hi)}
.wz .cv-color[aria-checked=true] .ico{display:block}
.wz .cv-color:focus-visible{outline:2px solid var(--sel);outline-offset:3px}
.wz-err{margin:0;padding:8px 10px;border:1px solid var(--line2);border-radius:var(--r-sm);background:var(--s2);
  color:var(--hi);font-size:12.5px;line-height:1.45}
.wz-err[hidden]{display:none}
.wz-foot{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:10px;padding-top:14px;border-top:1px solid var(--line)}
.wz-sec{margin:0;padding:0;border:0;min-width:0}
.wz-sec + .wz-sec{margin-top:18px}
.wz-sec legend{padding:0}
.wz-opts{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(220px,100%),1fr));gap:10px;margin-top:8px}
.wz-opt{display:flex;align-items:flex-start;gap:10px;padding:12px;border:1px solid var(--line);border-radius:var(--r-lg);
  background:var(--s2);cursor:pointer}
.wz-opt input{flex:none;margin:2px 0 0;accent-color:var(--sel)}
.wz-opt:has(input:checked){border-color:var(--sel);background:var(--s3)}
.wz-opt:has(input:focus-visible){outline:2px solid var(--sel);outline-offset:2px}
.wz-opt:has(input:disabled){cursor:default;opacity:.6}
.wz-opt--none{border-style:dashed}
.wz-opt-body{display:flex;flex-direction:column;gap:4px;min-width:0}
.wz-opt-top{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.wz-opt-top b{font-weight:600;color:var(--hi);overflow-wrap:anywhere}
.wz-opt-desc{font-size:12.5px;line-height:1.45;color:var(--mid)}
.wz-opt-instead{font-size:12px;color:var(--dim)}
.wz-opt-why{display:flex;gap:6px;font-size:12px;color:var(--hi)}
.wz-opt-why .ico{flex:none;margin-top:1px;color:var(--bad)}
.wz-offs{display:flex;flex-direction:column;gap:8px;margin:0;padding:0;list-style:none}
.wz-off{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 10px;border:1px dashed var(--line2);
  border-radius:var(--r);color:var(--mid);font-size:12.5px}
.wz-off .ico{flex:none}
.wz-off .cn-res{flex-basis:100%}
.wz-cards{display:flex;flex-direction:column;gap:12px;margin:0;padding:0;border:0;min-width:0}
.wz-card{gap:12px}
.wz-res:empty{display:none}
.wz-two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.8fr);gap:18px;align-items:start}
.wz-task{padding:14px;border:1px solid var(--line);border-radius:var(--r-lg);background:var(--s2)}
.wz-src{display:flex;flex-direction:column;gap:6px;margin:0;padding:0;border:0}
.wz-src legend{padding:0;margin-bottom:6px}
.wz-acts{display:flex;flex-wrap:wrap;gap:8px}
.wz-agent{margin-top:0}
@media (max-width:719px){.wz{padding:16px 16px 48px}.wz-two{grid-template-columns:1fr}}
```

  ⚠️ `.th-in` дає `padding:22px 28px 60px`; `@media` перебиває його для `.wz` (та сама специфічність, правило пізніше). Якщо в `styles.css` нема токена `--g900` чи `--logo` — узяти той, що є (`grep -- '--logo' app/styles.css`), не вводити літерал.

- [ ] **Step 4: Тести зелені.** Run: `python3 "$G" 120 1500 node --test tests/wizard-css.test.mjs tests/css-guards.test.mjs tests/connections-css.test.mjs` → PASS. `css-guards` стереже сітку висот і контраст: якщо він червоніє на новому правилі — підкоригувати правило (а не охоронця).

- [ ] **Step 5: Commit.**
```bash
git add app/styles.css tests/wizard-css.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "style(wizard): каркас майстра, варіанти модулів, кружки кольору на темному

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Смуга й ⌘K на сторінці майстра (`bar-model.js`, `shell-bar.js`, `shell-palette.js`)

**Files:**
- Modify: `app/bar-model.js` (≈ рядки 159–192: `home`, гілка `s.homeOpen`)
- Modify: `app/shell-bar.js` (`homeCrumbs` ≈ 565, `barHTML` ≈ 582)
- Modify: `app/shell-palette.js` (`spaceActions` ≈ 172)
- Test: `tests/bar-model.test.mjs`, `tests/shell-bar.test.mjs`, `tests/shell-palette.test.mjs`

- [ ] **Step 1: Падаючі тести.** У `tests/bar-model.test.mjs` поруч із тестом «екран «Підключення»» додати (стан будувати тим самим помічником, яким будує сусідній тест для `homeOpen`):

```js
test("майстер: логотип, палітра й крихта `crumb-wiz` — без фішки простору й без «назад до задачі»", () => {
  const m = barModel({ ...HOME_STATE, homePage: "wiz", space: { name: "Studio", color: "space-2" }, taskId: "t1" });
  assert.deepEqual(m.zone1.map((x) => x.id), ["home", "palette", "crumb-wiz"]);
  assert.equal(m.zone1.find((x) => x.id === "crumb-wiz").labelKey, "wzCrumb");
  assert.equal(m.zone1.find((x) => x.id === "home").on, false, "логотип на майстрі не «поточна сторінка»");
  assert.deepEqual([m.zone2, m.zone3], [[], []]);
});
```
  (`barModel` і `HOME_STATE` — назви з цього файла: якщо сусідні тести звуть їх інакше, взяти їхні; суть — стан `homeOpen: true` плюс `homePage: "wiz"`.)

  У `tests/shell-bar.test.mjs`:

```js
test("крихта майстра: іконка plus і «Новий простір», жодної фішки простору й кнопки «назад»", () => {
  const model = { zone1: [{ id: "home", tier: 0, on: false }, { id: "palette", tier: 0 }, { id: "crumb-wiz", tier: 0, labelKey: "wzCrumb" }], zone2: [], zone3: [] };
  const h = barHTML(model, {});
  assert.match(h, /<span class="crumb crumb--flat">[\s\S]*?#i-plus[\s\S]*?<span class="txt">Новий простір<\/span>/);
  assert.doesNotMatch(h, /data-act="back"/);
  assert.doesNotMatch(h, /space-chip/);
});
```
  (як `ico()` малює `<use href="#i-plus">` — звірити з сусіднім тестом крихти «Підключення» і повторити його форму перевірки іконки.)

  У `tests/shell-palette.test.mjs`:

```js
test("на сторінці майстра ⌘K не пропонує дій простору: ні перемикання, ні «Підключення», ні «Новий простір»", () => {
  const acts = paletteActions({ spaces: [{ id: "a", name: "A" }, { id: "b", name: "B" }], spaceId: "a", homeOpen: true, homePage: "wiz" });
  assert.ok(!acts.some((a) => a.id.startsWith("space-")), acts.map((a) => a.id).join(","));
  const tasks = paletteActions({ spaces: [{ id: "a", name: "A" }, { id: "b", name: "B" }], spaceId: "a", homeOpen: true, homePage: "tasks" });
  assert.ok(tasks.some((a) => a.id === "space-new") && tasks.some((a) => a.id === "space-go-b"), "свідок: на «Задачах» дії є");
});
```

- [ ] **Step 2: Переконатись, що падають.** Run: `python3 "$G" 120 1500 node --test tests/bar-model.test.mjs tests/shell-bar.test.mjs tests/shell-palette.test.mjs` → FAIL.

- [ ] **Step 3: Реалізація.**
  `app/bar-model.js`:
  - `const home = { id: "home", tier: 0, on: !!s.homeOpen && s.homePage !== "conn" && s.homePage !== "wiz" };` і коментар над ним доповнити: «…і на майстрі (`wiz`) теж: там поточну сторінку називає крихта «Новий простір»».
  - На початку гілки `if (s.homeOpen) {`:

```js
    /* Майстер нового простору (етап 3b) — та сама сторінка оверлею, але без фішки простору й без «назад до задачі»:
       майстер привʼязаний до СВОГО простору (перемикач посеред кроків лише плутав би), а вихід із нього — свої кнопки
       й логотип (`BAR_ACTIONS.home` питає про незбережене). */
    if (s.homePage === "wiz") {
      return { zone1: [home, palette, { id: "crumb-wiz", tier: 0, labelKey: "wzCrumb" }], zone2: [], zone3: [], error: tasksError(s) };
    }
```
  `app/shell-bar.js` у `homeCrumbs`:

```js
  const wiz = model.zone1.some((x) => x.id === "crumb-wiz");
  const conn = model.zone1.some((x) => x.id === "crumb-conn");
  const [icon, key] = wiz ? ["plus", "wzCrumb"] : conn ? ["sliders", "cnTitle"] : ["grid", "tasks"];
  const crumb = `<span class="crumb crumb--flat">${ico(icon)}<span class="txt">${esc(t(key))}</span></span>`;
```
  і в `barHTML`: `const home = model.zone1.some((x) => x.id === "crumb-tasks" || x.id === "crumb-conn" || x.id === "crumb-wiz");`. Коментар над `homeCrumbs` доповнити реченням про `crumb-wiz`.
  `app/shell-palette.js` у `spaceActions` першим рядком після перевірки масиву:

```js
  /* Майстер нового простору (етап 3b): дії простору тут не пропонуються — перемкнути простір посеред кроків означало б
     лишити майстер над чужим простором, а «Новий простір» на ньому нічого не робить. */
  if (s.homePage === "wiz") return [];
```

- [ ] **Step 4: Тести зелені.** Run: `python3 "$G" 300 2000 node --test tests/bar-model.test.mjs tests/shell-bar.test.mjs tests/shell-palette.test.mjs tests/principle6.test.mjs` → PASS.

- [ ] **Step 5: Commit.**
```bash
git add app/bar-model.js app/shell-bar.js app/shell-palette.js tests/bar-model.test.mjs tests/shell-bar.test.mjs tests/shell-palette.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(wizard): смуга й ⌘K на сторінці майстра — крихта, без фішки й дій простору

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: Контролер майстра (`app/wizard.js`)

**Files:**
- Create: `app/wizard.js`
- Create: `tests/wizard-wiring.test.mjs` (частина про `wizard.js`; частину про `app.js` допише Task 7)

Контролер не імпортує `app.js`: усе, що належить оболонці, приходить залежностями (`createWizard(deps)`), як у `overview-comments.js`. Браузерної перевірки до Task 7 нема (сторінку ще ніхто не відкриває) — тут лише статичні піни й `node --check`; поведінку доводить живий тест Task 8.

- [ ] **Step 1: Падаючі піни.** Створити `tests/wizard-wiring.test.mjs`:

```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const noComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<![:'"`])\/\/[^\n]*/g, "");
/** Тіло функції `name` у джерелі `src` (від `{` після сигнатури до парної `}`). */
function fn(src, name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `функції ${name} нема`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return noComments(src.slice(open, i + 1)); }
  }
  throw new Error(`немає закриття для ${name}`);
}
const W = read("wizard.js");

test("контролер не імпортує app.js (усе — залежностями)", () => {
  assert.doesNotMatch(W, /from ["']\.\/app\.js["']/);
});

test("кожен запит кроків 2–4 несе простір майстра (`space: mine.spaceId` / `space=`), а не «поточний»", () => {
  assert.match(fn(W, "loadStep2"), /\/api\/modules\?space=\$\{encodeURIComponent\(mine\.spaceId\)\}/);
  assert.match(fn(W, "loadStep3"), /\/api\/modules\?space=\$\{encodeURIComponent\(mine\.spaceId\)\}/);
  assert.match(fn(W, "submit3"), /\/api\/modules\?space=\$\{encodeURIComponent\(mine\.spaceId\)\}/);
  assert.match(fn(W, "runOp"), /writePayload\(mine\.spaceId, op\.id,/);
  assert.match(fn(W, "runOp"), /\{ space: mine\.spaceId, id: op\.id \}/);
  assert.match(fn(W, "submit4"), /space: mine\.spaceId/);
});

test("заміна в ролі — `replace` лише для enable; stale-запис не шлеться", () => {
  const b = fn(W, "runOp");
  assert.match(b, /op\.op === "enable"\)/);
  assert.match(b, /if \(op\.stale\.length\)/);
  assert.ok(b.indexOf("op.stale.length") < b.indexOf("deps.post("), "перевірка свіжості — до запиту");
});

test("план записів знає список кроку 2 (зниклий вибір не вимикає постачальника); вибір чиститься від зниклих", () => {
  assert.match(fn(W, "submit3"), /prevList: mine\.list2/);
  assert.match(fn(W, "loadStep2"), /mine\.list2 = mine\.list/);
  assert.match(fn(W, "loadStep2"), /filter\(\(id\) => mine\.list\.some/);
});

test("обовʼязкові поля — до будь-якого запиту кроку 3", () => {
  const b = fn(W, "submit3");
  assert.ok(b.indexOf("missingRequired(") < b.indexOf("deps.api("), "missingRequired після запиту");
});

test("секрети: перемальовка бере їх у локальну мапу й вертає ВЛАСТИВІСТЮ .value; після відповіді — порожньо", () => {
  assert.match(fn(W, "paint"), /for \(const \[id, v\] of keep\.secrets\)/);
  assert.match(fn(W, "paint"), /\.value = v/);
  assert.doesNotMatch(fn(W, "paint"), /setAttribute\(["']value/);
  assert.match(fn(W, "runOp"), /clearSecrets\(op\.id\)/);
  assert.doesNotMatch(W, /wz\.[a-z0-9]*\.secrets\s*=/i, "секрети в стані майстра");
});

test("після будь-якого успішного запису модулів — легкий шлях оболонки (afterModulesChange), а не перемикання простору", () => {
  const b = fn(W, "submit3");
  assert.match(b, /await deps\.afterModulesChange\(\)/);
  assert.doesNotMatch(b, /afterSpaceCreated/);
});

test("вихід із незбереженим кроком 3 питає; Esc сторінку не закриває (обробника клавіш нема)", () => {
  assert.match(fn(W, "requestExit"), /if \(dirty\(\) && !\(await askDiscard\(\)\)\) return;/);
  assert.match(fn(W, "back"), /dirty\(\) && !\(await askDiscard\(\)\)/);
  assert.doesNotMatch(W, /keydown/);
});

test("простір створено — оболонка дізнається навіть тоді, коли майстер тим часом закрили", () => {
  const b = fn(W, "submit1");
  assert.ok(b.indexOf("await deps.afterSpaceCreated()") < b.indexOf("if (wz !== mine) return;\n    go(2)"),
    "перевірка «майстер ще той» — ПІСЛЯ повідомлення оболонки");
});
```

  ⚠️ Останній тест шукає точний рядок `if (wz !== mine) return;\n    go(2)` — якщо форматування коду інше, підправити ТЕСТ так, щоб він перевіряв порядок «`afterSpaceCreated` раніше за останній `if (wz !== mine) return;` перед `go(2)`».

- [ ] **Step 2: Переконатись, що падають.** Run: `python3 "$G" 60 1000 node --test tests/wizard-wiring.test.mjs` → FAIL (файла нема).

- [ ] **Step 3: Реалізація.** Створити `app/wizard.js`:

```js
/**
 * Майстер нового простору (Deai 0.6.0, етап 3b; спека `docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`) —
 * стан, запити й події третьої сторінки оверлею `#tasks-home` (`homePage === 'wiz'`). Розмітку дає `wizard-view.js`,
 * рішення — `wizard-model.js`; тут лише проводка. Усе, що знає оболонка (запити, перехід між просторами, вихід з
 * оверлею, питання), приходить залежностями `createWizard(deps)` — модуль не імпортує `app.js`:
 *
 *   node()               вузол `#tasks-home`;
 *   api(path)            GET → JSON (кидає `Error` з `code`);   post(path, body) — POST зі стелею часу (`postForm`);
 *   askYesNo(q, opts)    питання;   toast(msg)   тост;   spaces()   остання відповідь `/api/spaces`;
 *   peek(path)           `/api/space-peek`;   takenPaths()   шляхи просторів;   takenTaskIds()   Promise<id[]> усіх задач;
 *   afterSpaceCreated()  простір створено й зроблено поточним (оболонка: `afterSpaceChange`);
 *   afterSpaceEdited(id, saved)   назва/колір змінились (`applySpaceMeta`);
 *   afterModulesChange() легкий шлях 3a після запису модулів;
 *   openTask(made)       задачу створено — відкрити її (вихід з оверлею);
 *   exit({back})         `back: false` — на «Задачі» (там і привітання, коли просторів нема); `back: true` («Скасувати» до
 *                        створення) — туди, звідки майстер відкрили (полотно задачі чи сторінка оверлею);
 *   copy(text)           у буфер обміну.
 *
 * Простір майстра — `wz.spaceId` (після кроку 1): КОЖЕН запит кроків 2–4 несе його явно, бо агент міг перемкнути
 * активний простір паралельно. Відповідь `unknown-space` — майстер закривається (`spaceGone`).
 *
 * Перемальовка (`paint`) — повна: на зміні кроку, після перемикання мови, після кожного запису кроку 3. Набране в
 * полях вона не губить: `capture` забирає значення в стан (секрети — у ЛОКАЛЬНУ мапу), `restore` вертає. Зайнятість і
 * помилки кроків 1 і 4 НЕ перемальовують сторінку (`setBusy`, `showError` правлять вузли на місці): проводка
 * `wireSpaceDialog`/`wireTaskForm` тримає стан (тека правлена руками, id правлений руками), і повторна проводка його б
 * скинула (для перемальовки — опції `pathTouched`/`idTouched`).
 *
 * ⛔ Секрети: значення живуть лише у `.value` полів пароля (DOM) і в локальній змінній на час одного виклику. У стан
 * майстра, у розмітку чи в журнал не потрапляють. Після відповіді сервера на запис картки її поля паролів порожні.
 */
import { t } from "./i18n.js";
import {
  formFields, formPatch, initialForm, isDirty, missingRequired, refusalView, verdictText, writePayload,
} from "./connections-model.js";
import { modName } from "./connections-view.js";
import { wireSpaceDialog, wireTaskForm } from "./space-dialogs.js";
import {
  defaultSpacePath, freeColor, needsWelcome, spaceColorToken, spaceErrField, spaceErrKey, taskErrField, taskErrKey,
  taskFormError,
} from "./spaces-model.js";
import {
  allOk, errOffRows, holdersByRole, initialPick, offRows, pickModule, pickNone, pickedInOrder, prevStep, titleFromFolder, writePlan,
} from "./wizard-model.js";
import { wizardHTML } from "./wizard-view.js";

/** Поточні значення полів модуля в межах `root` (картка): `{values, secrets, erase}` — як `readCnForm` панелі 3a. */
function readFields(root) {
  const values = [];
  const secrets = [];
  for (const n of root.querySelectorAll("[data-cn-field]")) {
    const k = n.dataset.cnField;
    if (n.dataset.type === "secret") secrets.push([k, n.value]);
    else if (n.dataset.type === "bool") values.push([k, n.checked]);
    else values.push([k, n.value]);
  }
  const erase = [...root.querySelectorAll('[data-cn-dr="erase"][aria-pressed="true"]')].map((b) => b.dataset.key);
  return { values: Object.fromEntries(values), secrets: Object.fromEntries(secrets), erase };
}

/** «Стерти» секрет у картці — без перемальовки (як `toggleCnErase` панелі 3a, але в межах картки). */
function toggleErase(btn) {
  const root = btn.closest(".wz-card");
  if (!root) return;
  const on = btn.getAttribute("aria-pressed") !== "true";
  btn.setAttribute("aria-pressed", String(on));
  const key = btn.dataset.key;
  const note = root.querySelector(`[data-cn-erase-note="${CSS.escape(key)}"]`);
  if (note) note.hidden = !on;
  const field = root.querySelector(`[data-cn-field="${CSS.escape(key)}"]`);
  if (field && note?.id) {
    const ids = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter((x) => x && x !== note.id);
    if (on) ids.splice(ids.findIndex((x) => x.endsWith("-state")) + 1, 0, note.id);
    if (ids.length) field.setAttribute("aria-describedby", ids.join(" "));
    else field.removeAttribute("aria-describedby");
  }
}

export function createWizard(deps) {
  let wz = null;

  const spaceRec = () => (Array.isArray(deps.spaces()?.spaces) ? deps.spaces().spaces : []).find((x) => x.id === wz?.spaceId) ?? null;
  const painted = (el) => Number(el?.querySelector(".wz")?.dataset.step) || 0;
  const askDiscard = () => deps.askYesNo(t("cnDiscardAsk"), { yes: t("cnDiscard"), danger: true });

  /** Відкрити на кроці 1. `folderFirst` — «Відкрити наявну теку простору»: порожня назва, фокус у теці. */
  function open({ folderFirst = false } = {}) {
    const info = deps.spaces();
    const name = needsWelcome(info) && !folderFirst ? t("personalName") : "";
    wz = {
      step: 1, spaceId: null, created: false, busy: false, skipped3: false, seq: 0,
      s1: { name, color: freeColor(info?.spaces), path: folderFirst ? "" : defaultSpacePath(name, "~", deps.takenPaths()),
        pathTouched: folderFirst, folderFirst },
      list: null, failed: null, pick: null, atPick: new Map(),
      cards: [], offs: [], s3failed: null, s3loading: false,
      s4: { title: "", id: "", idTouched: false, source: "empty", from: "", autoTitle: "" },
      taskIds: null,
    };
  }

  function view() {
    const sp = spaceRec();
    return {
      step: wz.step, created: wz.created, busy: wz.busy,
      s1: wz.s1,
      s2: { list: wz.list, failed: wz.failed, pick: wz.pick ?? new Set(), capsError: !!sp?.capabilities?.error, path: sp?.path ?? "" },
      s3: { cards: wz.cards, offs: wz.offs, failed: wz.s3failed, loading: wz.s3loading },
      s4: { ...wz.s4, spaceName: sp?.name ?? wz.s1.name, tasks: Number(sp?.tasks) || 0 },
    };
  }

  /** Значення намальованого кроку — у стан; секрети — у повернену мапу «id поля → значення». */
  function capture(el) {
    const secrets = new Map();
    const a = document.activeElement;
    const focusId = a && el.contains(a) && a.id ? a.id : null;
    const step = painted(el);
    const q = (s) => el.querySelector(s);
    if (step === 1) {
      wz.s1.name = q("#sp-name")?.value ?? wz.s1.name;
      if (!wz.created) wz.s1.path = q("#sp-path")?.value ?? wz.s1.path;
      wz.s1.color = q('input[name="color"]')?.value ?? wz.s1.color;
    } else if (step === 3) {
      for (const card of wz.cards) {
        const root = q(`.wz-card[data-id="${CSS.escape(card.entry.id)}"]`);
        if (!root) continue;
        const cur = readFields(root);
        card.values = cur.values;
        card.erase = cur.erase;
        for (const n of root.querySelectorAll('[data-cn-field][data-type="secret"]')) if (n.value) secrets.set(n.id, n.value);
      }
    } else if (step === 4) {
      wz.s4.title = q("#tf-title")?.value ?? wz.s4.title;
      wz.s4.id = q("#tf-id")?.value ?? wz.s4.id;
      wz.s4.from = q("#wz-from")?.value ?? wz.s4.from;
      wz.s4.source = q('input[name="wz-src"]:checked')?.value ?? wz.s4.source;
    }
    return { secrets, focusId };
  }

  function wire(el) {
    if (wz.step === 1) {
      const form = el.querySelector('form[data-wz-step="1"]');
      if (form) {
        wireSpaceDialog(form, { mode: wz.created ? "edit" : "new", peek: deps.peek, taken: deps.takenPaths,
          pathTouched: wz.s1.pathTouched });
      }
    } else if (wz.step === 4) {
      const form = el.querySelector('form[data-wz-step="4"]');
      if (form) {
        wz.taskIds ??= deps.takenTaskIds();
        wireTaskForm(form, { taken: wz.taskIds, idTouched: wz.s4.idTouched });
      }
    }
  }

  /** Повна перемальовка сторінки з тим, що людина вже набрала (секрети — лише властивістю `.value`). */
  function paint() {
    const el = deps.node();
    if (!el || !wz) return;
    const keep = capture(el);
    const top = el.scrollTop;
    el.innerHTML = wizardHTML(view());
    el.scrollTop = top;
    for (const [id, v] of keep.secrets) {
      const n = el.querySelector(`#${CSS.escape(id)}`);
      if (n) n.value = v;
    }
    wire(el);
    if (keep.focusId) el.querySelector(`#${CSS.escape(keep.focusId)}`)?.focus({ preventScroll: true });
  }

  function focusStep() {
    const el = deps.node();
    if (!el || !wz) return;
    if (wz.step === 1 && !wz.created) {
      el.querySelector(wz.s1.folderFirst ? "#sp-path" : "#sp-name")?.focus({ preventScroll: true });
      return;
    }
    el.querySelector("#wz-h")?.focus({ preventScroll: true });
  }

  function go(step) {
    if (!wz) return;
    wz.step = step;
    if (step === 4) wz.taskIds = null;     // свіжий перелік зайнятих id на кожен вхід
    paint();
    focusStep();
    if (step === 2) loadStep2();
    else if (step === 3) loadStep3();
  }

  function exit(msg, back = false) {
    wz = null;
    if (msg) deps.toast(msg);
    deps.exit({ back });
  }
  function spaceGone() { exit(t("wzSpaceGone")); }

  /* ── зайнятість і помилки кроків 1 і 4: на місці, без перемальовки ─────────────────────────────────── */

  function setBusy(form, on, key) {
    wz.busy = on ? "save" : false;
    if (on) form.setAttribute("aria-busy", "true");
    else form.removeAttribute("aria-busy");
    const root = deps.node();
    for (const n of root.querySelectorAll(".wz input, .wz button")) {
      if (n.type === "hidden") continue;
      if (on) { if (!n.disabled) { n.disabled = true; n.dataset.wzBusy = "1"; } }
      else if (n.dataset.wzBusy) { n.disabled = false; delete n.dataset.wzBusy; }
    }
    const okBtn = form.querySelector('[data-a="ok"]');
    if (okBtn) {
      if (on) { okBtn.dataset.wzLabel = okBtn.textContent; okBtn.textContent = t(key); }
      else if (okBtn.dataset.wzLabel != null) { okBtn.textContent = okBtn.dataset.wzLabel; delete okBtn.dataset.wzLabel; }
    }
  }

  /** Текст помилки в `#wz-err`; поле (`name`) — `aria-invalid` і фокус. Правка поля знімає позначку (`input`). */
  function showError(form, key, field) {
    const slot = form.querySelector("#wz-err");
    if (slot) { slot.textContent = t(key); slot.hidden = false; }
    for (const n of form.querySelectorAll('[aria-invalid="true"]')) n.removeAttribute("aria-invalid");
    const n = field ? form.querySelector(`[name="${field}"]`) : null;
    if (n) { n.setAttribute("aria-invalid", "true"); n.focus({ preventScroll: true }); }
  }

  /* ── крок 1 · Простір ─────────────────────────────────────────────────────────────────────────────── */

  async function submit1() {
    const el = deps.node();
    const form = el.querySelector('form[data-wz-step="1"]');
    const mine = wz;
    capture(el);
    const name = mine.s1.name.trim();
    if (!name) { showError(form, "spaceErrName", "name"); return; }
    if (mine.created) {
      const cur = spaceRec();
      if (cur && cur.name === name && cur.color === spaceColorToken(mine.s1.color)) { go(2); return; }
      setBusy(form, true, "wzSaving");
      let saved;
      try { saved = await deps.post("/api/space-update", { id: mine.spaceId, name, color: mine.s1.color }); }
      catch (e) {
        if (wz !== mine) return;
        setBusy(form, false);
        if (e?.code === "unknown-space") { spaceGone(); return; }
        showError(form, spaceErrKey(e?.code), spaceErrField(e?.code));
        return;
      }
      if (wz !== mine) return;
      mine.busy = false;
      deps.afterSpaceEdited(mine.spaceId, saved);
      go(2);
      return;
    }
    setBusy(form, true, "wzCreating");
    let r;
    try { r = await deps.post("/api/space-new", { name, color: mine.s1.color, path: mine.s1.path.trim() }); }
    catch (e) {
      if (wz !== mine) return;
      setBusy(form, false);
      showError(form, spaceErrKey(e?.code), spaceErrField(e?.code));
      return;
    }
    /* Простір УЖЕ створено й зроблено поточним (так робить сервер) — оболонка мусить дізнатись навіть тоді, коли
       майстер тим часом закрили (⌘K): інакше смуга й сервер розійшлися б. */
    mine.spaceId = r.id;
    mine.created = true;
    mine.busy = false;
    try { await deps.afterSpaceCreated(); } catch (e) { deps.toast(t("errFailed", e?.message ?? "")); }
    if (wz !== mine) return;
    go(2);
  }

  /* ── крок 2 · Модулі ─────────────────────────────────────────────────────────────────────────────── */

  async function loadStep2() {
    const mine = wz;
    const seq = ++mine.seq;
    mine.list = null;
    mine.failed = null;
    paint();
    try {
      const r = await deps.api(`/api/modules?space=${encodeURIComponent(mine.spaceId)}`);
      if (wz !== mine || seq !== mine.seq) return;
      mine.list = Array.isArray(r?.modules) ? r.modules : [];
      mine.list2 = mine.list;
      /* Вибір, що пережив «Назад», чистимо від модулів, яких уже нема: радіо показали б «Без модуля», а план — ні. */
      mine.pick = mine.pick ? new Set([...mine.pick].filter((id) => mine.list.some((e) => e?.id === id))) : initialPick(mine.list);
      mine.atPick = holdersByRole(mine.list);
    } catch (e) {
      if (wz !== mine || seq !== mine.seq) return;
      if (e?.code === "unknown-space") { spaceGone(); return; }
      mine.failed = { code: e?.code ?? null, message: String(e?.message || e) };
    }
    paint();
  }

  function submit2() {
    const skip = !Array.isArray(wz.list) || !!wz.failed || !!spaceRec()?.capabilities?.error;
    wz.skipped3 = skip;
    go(skip ? 4 : 3);
  }

  /* ── крок 3 · Налаштування ───────────────────────────────────────────────────────────────────────── */

  const cardFrom = (entry) => {
    const fields = formFields(entry);
    const init = initialForm(fields);
    return { entry, fields, init, values: init.values, erase: [], errors: {}, result: null };
  };

  async function loadStep3() {
    const mine = wz;
    const seq = ++mine.seq;
    mine.cards = []; mine.offs = []; mine.s3failed = null; mine.s3loading = true;
    paint();
    let list;
    try { list = (await deps.api(`/api/modules?space=${encodeURIComponent(mine.spaceId)}`))?.modules; }
    catch (e) {
      if (wz !== mine || seq !== mine.seq) return;
      if (e?.code === "unknown-space") { spaceGone(); return; }
      mine.s3failed = { code: e?.code ?? null, message: String(e?.message || e) };
      mine.s3loading = false;
      paint();
      return;
    }
    if (wz !== mine || seq !== mine.seq) return;
    mine.list = Array.isArray(list) ? list : [];
    mine.cards = pickedInOrder(mine.list, mine.pick).map(cardFrom);
    /* «Без модуля» + тримачі з помилкою, яких `replace` не вимикає (сервер їх не рахує тримачами) — майстер вимкне їх сам. */
    mine.offs = [...offRows(mine.list, mine.pick), ...errOffRows(mine.list, mine.pick)].map((o) => ({ ...o, result: null }));
    mine.s3loading = false;
    paint();
  }

  /** Поля паролів картки — порожні (сервер відповів на її запис). */
  function clearSecrets(id) {
    const root = deps.node()?.querySelector(`.wz-card[data-id="${CSS.escape(id)}"]`);
    for (const n of root?.querySelectorAll('[data-type="secret"]') ?? []) n.value = "";
  }

  /** Чи є на кроці 3 незбережене (змінене поле чи введений секрет). */
  function dirty() {
    if (!wz || wz.step !== 3) return false;
    const el = deps.node();
    if (painted(el) !== 3) return false;
    return wz.cards.some((c) => {
      const root = el.querySelector(`.wz-card[data-id="${CSS.escape(c.entry.id)}"]`);
      return !!root && isDirty(formPatch(c.fields, c.init, readFields(root)));
    });
  }

  async function runOp(mine, op, fresh, forms) {
    const card = mine.cards.find((c) => c.entry.id === op.id) ?? null;
    let result;
    if (op.op === "gone") {
      result = { kind: "refused", ...refusalView({ code: "unknown-module" }) };
    } else if (op.stale.length) {
      const now = holdersByRole(fresh);
      const names = op.stale.flatMap((r) => now.get(r) ?? [])
        .map((id) => modName(fresh.find((e) => e.id === id) ?? { id }));
      result = { kind: "refused", key: "wzStale", detail: [...new Set(names)].join(", ") };
    } else {
      const path = op.op === "enable" ? "/api/module-enable" : op.op === "settings" ? "/api/module-settings" : "/api/module-disable";
      const f = forms.get(op.id);
      const body = op.op === "disable" ? { space: mine.spaceId, id: op.id }
        : writePayload(mine.spaceId, op.id, formPatch(f.fields, f.init, f.cur), op.op === "enable");
      try {
        const r = await deps.post(path, body);
        if (op.op === "disable") result = { kind: "ok", key: "wzOffDone", detail: "" };
        else {
          result = { kind: r?.check?.ok === true ? "ok" : "failed", ...verdictText(r?.check) };
          /* Новий базис картки: збережене вже не «зміна», і стан секрету («задано») — з відповіді. */
          if (card && r?.module) Object.assign(card, cardFrom(r.module));
        }
      } catch (e) {
        if (e?.code === "unknown-space") return { kind: "gone-space" };
        result = { kind: "refused", ...refusalView(e) };
      }
      clearSecrets(op.id);
    }
    if (card) card.result = result;
    for (const o of mine.offs) if (o.holder.id === op.id) o.result = result;
    paint();
    return result;
  }

  async function submit3() {
    const el = deps.node();
    const mine = wz;
    const keep = capture(el);
    /* Поточні значення картки для моделі: секрети — з локальної мапи (за id поля `wz-f-<картка>-<поле>`). */
    const curOf = (c, i) => ({
      values: c.values, erase: c.erase,
      secrets: Object.fromEntries(c.fields.map((f, j) => [f, j]).filter(([f]) => f.type === "secret")
        .map(([f, j]) => [f.key, keep.secrets.get(`wz-f-${i}-${j}`) ?? ""])),
    });
    let bad = false;
    mine.cards.forEach((c, i) => {
      const miss = missingRequired(c.fields, curOf(c, i));
      c.errors = Object.fromEntries(miss.map((k) => [k, "cnFieldRequired"]));
      if (miss.length) bad = true;
    });
    if (bad) {
      paint();
      deps.node()?.querySelector('.wz [aria-invalid="true"]')?.focus({ preventScroll: true });
      return;
    }
    const forms = new Map(mine.cards.map((c, i) => [c.entry.id, { fields: c.fields, init: c.init, cur: curOf(c, i) }]));
    mine.busy = "save";
    paint();
    let fresh;
    try { fresh = (await deps.api(`/api/modules?space=${encodeURIComponent(mine.spaceId)}`))?.modules ?? []; }
    catch (e) {
      if (wz !== mine) return;
      if (e?.code === "unknown-space") { spaceGone(); return; }
      mine.busy = false;
      mine.s3failed = { code: e?.code ?? null, message: String(e?.message || e) };
      paint();
      return;
    }
    if (wz !== mine) return;
    const ops = writePlan({ list: fresh, pick: mine.pick, forms, atPick: mine.atPick, prevList: mine.list2 });
    const results = [];
    let changed = false;
    for (const op of ops) {
      if (wz !== mine) break;
      const res = await runOp(mine, op, fresh, forms);
      if (res.kind === "gone-space") { mine.busy = false; spaceGone(); return; }
      results.push(res);
      if (res.kind === "ok" || res.kind === "failed") changed = true;
    }
    mine.busy = false;
    if (changed) { try { await deps.afterModulesChange(); } catch (e) { /* екран оновиться при наступному вході */ } }
    if (wz !== mine) return;
    if (allOk(results)) { go(4); return; }
    paint();
    deps.node()?.querySelector(".wz-card .cn-res--err, .wz-off .cn-res--err")?.closest(".wz-card, .wz-off")
      ?.querySelector("input, select, button")?.focus({ preventScroll: true });
  }

  /* ── крок 4 · Перша задача ───────────────────────────────────────────────────────────────────────── */

  async function submit4() {
    const el = deps.node();
    const form = el.querySelector('form[data-wz-step="4"]');
    const mine = wz;
    capture(el);
    const vals = { title: mine.s4.title, id: mine.s4.id };
    const key = taskFormError(vals, await Promise.resolve(mine.taskIds ?? []).catch(() => []));
    if (wz !== mine) return;
    if (key) { showError(form, key, taskErrField(key)); return; }
    const folder = mine.s4.source === "folder";
    const from = mine.s4.from.trim();
    if (folder && !from) { showError(form, "wzFromRequired", "from"); return; }
    setBusy(form, true, "wzCreating");
    let made;
    try {
      made = await deps.post("/api/task-new", { id: vals.id, title: vals.title.trim(), space: mine.spaceId, ...(folder ? { from } : {}) });
    } catch (e) {
      if (wz !== mine) return;
      setBusy(form, false);
      if (e?.code === "unknown-space") { spaceGone(); return; }
      const k = taskErrKey(e?.code);
      showError(form, k, taskErrField(k));
      return;
    }
    const links = Number(made?.copied?.skipped_links) || 0;
    wz = null;
    if (links) deps.toast(t("wzSkippedLinks", links));
    try { await deps.openTask(made); } catch (e) { deps.toast(t("errFailed", e?.message ?? "")); }
  }

  async function copyPhrase() {
    const text = deps.node()?.querySelector("#wz-phrase")?.textContent ?? "";
    try { await deps.copy(text); deps.toast(t("wzCopied")); } catch (e) { deps.toast(t("wzCopyFailed")); }
  }

  /* ── навігація й вихід ───────────────────────────────────────────────────────────────────────────── */

  async function back() {
    if (!wz || wz.busy) return;
    if (wz.step === 3 && dirty() && !(await askDiscard())) return;
    if (!wz) return;
    go(prevStep(wz.step, wz.skipped3));
  }

  /** «Закрити майстер», «Пропустити», логотип: незбережене кроку 3 — питання; створений простір — тост «готовий». */
  async function requestExit() {
    if (!wz || wz.busy) return;
    if (dirty() && !(await askDiscard())) return;
    const mine = wz;
    if (!mine) return;
    exit(mine.created ? t("wzReady", spaceRec()?.name ?? mine.s1.name) : null);
  }

  /** «Скасувати» до створення: простору ще нема — назад, звідки прийшли. */
  function cancel() {
    if (!wz || wz.busy || wz.created) return;
    exit(null, true);
  }

  /* ── події сторінки (делегує `wireHome` у `app.js`) ──────────────────────────────────────────────── */

  function click(ev) {
    if (!wz) return;
    const b = ev.target.closest('[data-wz], [data-a="cancel"], [data-cn-dr="erase"]');
    if (!b || b.disabled) return;
    if (b.dataset.cnDr === "erase") { toggleErase(b); return; }
    if (b.dataset.a === "cancel") { cancel(); return; }
    const a = b.dataset.wz;
    if (a === "back") back();
    else if (a === "close" || a === "skip") requestExit();
    else if (a === "retry") loadStep2();
    else if (a === "copy") copyPhrase();
  }

  function submit(ev) {
    ev.preventDefault();
    if (!wz || wz.busy) return;
    const step = Number(ev.target?.dataset?.wzStep);
    if (step !== wz.step) return;
    if (step === 1) submit1();
    else if (step === 2) submit2();
    else if (step === 3) submit3();
    else if (step === 4) submit4();
  }

  /** `input` і `change` сторінки: позначки «правлено руками», вибір модуля, джерело макета, назва з теки. */
  function input(ev) {
    if (!wz) return;
    const n = ev.target;
    if (n.getAttribute?.("aria-invalid") === "true") n.removeAttribute("aria-invalid");
    if (ev.type === "input") {
      if (n.id === "sp-path") wz.s1.pathTouched = true;
      else if (n.id === "tf-id") wz.s4.idTouched = n.value !== "";
      else if (n.id === "wz-from") {
        const title = deps.node()?.querySelector("#tf-title");
        if (title && (!title.value.trim() || title.value === wz.s4.autoTitle)) {
          const v = titleFromFolder(n.value);
          title.value = v;
          wz.s4.autoTitle = v;
          title.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }
      return;
    }
    if (n.dataset?.wzPick != null && n.checked) {
      wz.pick = n.value ? pickModule(wz.pick ?? new Set(), wz.list, n.value) : pickNone(wz.pick ?? new Set(), wz.list, n.dataset.role);
      paint();
    } else if (n.name === "wz-src" && n.checked) {
      wz.s4.source = n.value;
      const box = deps.node()?.querySelector("#wz-from-f");
      if (box) box.hidden = n.value !== "folder";
      if (n.value === "folder") deps.node()?.querySelector("#wz-from")?.focus({ preventScroll: true });
    }
  }

  return {
    open, paint, focusStep, requestExit, click, submit, input, dirty,
    reset() { wz = null; },
    active: () => !!wz,
  };
}
```

  ⚠️ Звірити з розміткою Task 3: id `wz-f-<i>-<j>` у `curOf` — той самий префікс, що `cardHTML` передає у `fieldHTML` (`wz-f-${i}`); `#wz-from-f`, `#wz-phrase`, `[data-wz-res]` — як у `wizard-view.js`. Якщо `formFields` поверне поля в іншому порядку, ніж у розмітці, — ні: обидва ходять по `c.fields` тим самим `map`.

- [ ] **Step 4: Перевірка синтаксису й пінів.** Run: `node --check app/wizard.js && python3 "$G" 120 1500 node --test tests/wizard-wiring.test.mjs tests/js-parses.test.mjs tests/i18n-literals.test.mjs` → PASS.

- [ ] **Step 5: Commit.**
```bash
git add app/wizard.js tests/wizard-wiring.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(wizard): контролер майстра — кроки, запис модулів зі свіжістю, задача з теки

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `app.js` — сторінка `wiz`, входи, прибрати діалог «Новий простір»

**Files:**
- Modify: `app/app.js` (імпорти ≈ рядок 15–45; `homePage` ≈ 182; `openSpaceNew` ≈ 1339 — прибрати; `BAR_ACTIONS.spacenew`/`home` ≈ 1597; `paintHome` ≈ 2307; `enterHome` ≈ 2384; `leaveHome` ≈ 2427; `refreshHomeOnReturn` ≈ 2461; `wireHome` ≈ 2500; клавіатура ≈ 3101)
- Modify: `app/space-dialogs.js` (прибрати режим `new` у `spaceDialogHTML`)
- Modify: `tests/space-dialogs.test.mjs`, `tests/connections-wiring.test.mjs`, `tests/spaces-wiring.test.mjs` (піни, що описували старий шлях)
- Modify: `tests/wizard-wiring.test.mjs` (частина про `app.js`)

- [ ] **Step 1: Падаючі піни `app.js`.** Дописати в `tests/wizard-wiring.test.mjs`:

```js
const A = read("app.js");

test("входи: дропдаун/⌘K і привітання ведуть у майстер, «Відкрити наявну теку» — з фокусом у теці", () => {
  assert.match(A, /\n  spacenew: \(\) => openWizard\(\),/);
  assert.match(fn(A, "wireHome"), /case 'spacenew': openWizard\(\); break;/);
  assert.match(fn(A, "wireHome"), /case 'spaceopen': openWizard\(\{ folderFirst: true \}\); break;/);
  assert.doesNotMatch(A, /function openSpaceNew\(/, "старий діалог «Новий простір» лишився");
  assert.match(fn(A, "openWizard"), /wiz\.open\(\{ folderFirst \}\);\s*enterHome\(\{ page: 'wiz' \}\);\s*wiz\.focusStep\(\);/);
});

test("сторінка wiz: paintHome малює майстер раніше за привітання; enterHome не тягне список задач; вихід — reset", () => {
  const p = fn(A, "paintHome");
  assert.ok(p.indexOf("homePage === 'wiz'") > -1 && p.indexOf("homePage === 'wiz'") < p.indexOf("needsWelcome("),
    "майстер мусить малюватись і тоді, коли просторів ще нема (перший запуск)");
  const e = fn(A, "enterHome");
  assert.match(e, /if \(next !== 'wiz'\) wiz\.reset\(\);/);
  assert.match(e, /if \(homePage === 'wiz'\) \{\s*homeSeq \+= 1;\s*paintHome\(\);\s*return;\s*\}/);
  assert.match(fn(A, "leaveHome"), /wiz\.reset\(\);/);
});

test("логотип на майстрі — вихід через майстер (питає про незбережене)", () => {
  assert.match(A, /\n  home: async \(\) => \{ if \(homeOpen && homePage === 'wiz'\) \{ await wiz\.requestExit\(\); return; \} if \(cnDrawer && !\(await dismissCnDrawer\(\)\)\) return; enterHome\(\{ page: 'tasks' \}\); \},/);
});

test("події сторінки майстра йдуть у контролер раніше за обробники «Задач»", () => {
  const w = fn(A, "wireHome");
  assert.match(w, /if \(homePage === 'wiz'\) \{ wiz\.click\(ev\); return; \}/);
  assert.match(w, /addEventListener\('submit', \(ev\) => \{ if \(homePage === 'wiz'\) wiz\.submit\(ev\); \}\)/);
  assert.match(w, /if \(homePage === 'wiz'\) \{ wiz\.input\(ev\); return; \}/);
});

test("клавіші «Задач» діють лише на «Задачах»; повернення у вікно майстра не перечитує", () => {
  assert.match(A, /if \(homePage !== 'tasks'\) return;\s+\/\/ «Підключення» й майстер/);
  assert.match(fn(A, "refreshHomeOnReturn"), /if \(homePage === 'wiz'\) return;/);
});

test("залежності контролера: запис модулів — легкий шлях 3a, простір — afterSpaceChange, задача — wizOpenTask", () => {
  assert.match(A, /afterModulesChange: \(\) => afterModulesChange\(\),/);
  assert.match(A, /afterSpaceCreated: \(\) => afterSpaceChange\(\),/);
  assert.match(A, /openTask: \(made\) => wizOpenTask\(made\),/);
  assert.match(A, /exit: \(\{ back = false \} = \{\}\) => \(back \? wizBack\(\) : enterHome\(\{ page: 'tasks' \}\)\),/);
});
```

- [ ] **Step 2: Переконатись, що падають.** Run: `python3 "$G" 60 1000 node --test tests/wizard-wiring.test.mjs` → FAIL на нових тестах.

- [ ] **Step 3: Інтеграція в `app/app.js`.**
  1. Імпорт: `import { createWizard } from './wizard.js';` (поруч з імпортом `space-dialogs.js`). З імпорту `space-dialogs.js` прибрати `spaceDialogHTML`, якщо після кроку 5 він потрібен лише `openSpaceEdit` — ні, `openSpaceEdit` його кличе: лишити.
  2. Коментар `let homePage = 'tasks';` → «`'tasks'` — «Задачі», `'conn'` — «Підключення» (3a), `'wiz'` — майстер нового простору (3b)».
  3. Прибрати функцію `openSpaceNew` цілком (і коментар над нею). `spaceDialogFocusBack` лишається (його бере `openSpaceEdit`).
  4. Після `spaceDialogFocusBack` додати:

```js
/* ── майстер нового простору (етап 3b) ─────────────────────────────────────────────────────────────────────
   Третя сторінка оверлею `#tasks-home` (`homePage === 'wiz'`). Стан і проводку тримає `wizard.js`; тут — лише входи
   й залежності. «Новий простір…» (дропдаун, ⌘K) і привітання ведуть сюди; діалог простору лишився для «Назва й колір…». */
const wiz = createWizard({
  node: () => ensureHome(),
  api: (p) => api(p),
  post: (p, body) => postForm(p, body),
  askYesNo,
  toast,
  spaces: () => spacesResp,
  peek: (p) => api(`/api/space-peek?path=${encodeURIComponent(p)}`),
  takenPaths: () => (spacesResp?.spaces ?? []).map((x) => x.path),
  takenTaskIds: () => formApi('/api/tasks?all=1').then((r) => (r.tasks || []).map((x) => x.id)).catch(() => []),
  afterSpaceCreated: () => afterSpaceChange(),
  afterSpaceEdited: (id, saved) => applySpaceMeta(id, saved),
  afterModulesChange: () => afterModulesChange(),
  openTask: (made) => wizOpenTask(made),
  exit: ({ back = false } = {}) => (back ? wizBack() : enterHome({ page: 'tasks' })),
  copy: (s) => navigator.clipboard.writeText(s),
});

/* Звідки майстер відкрили: `null` — полотно задачі (оверлей був закритий), інакше сторінка оверлею. Потрібно лише
   «Скасувати» до створення: простору нема, і людина вертається туди, де була. */
let wizFrom = null;

/** Відкрити майстер на кроці 1. Шар просторів вимкнено — входу нема (як і «Новий простір…» у дропдауні). */
function openWizard({ folderFirst = false } = {}) {
  if (spacesResp?.off) return;
  wizFrom = homeOpen ? homePage : null;
  wiz.open({ folderFirst });
  enterHome({ page: 'wiz' });
  wiz.focusStep();
}

/**
 * «Скасувати» до створення — туди, звідки прийшли: на полотно задачі (коли вона є) чи на сторінку оверлею; фокус — на
 * фішку простору, як після колишнього діалогу. На першому запуску фішки нема — фокус ставить `enterHome` (кнопка привітання).
 */
async function wizBack() {
  if (wizFrom === null && currentTaskId) await leaveHome();
  else enterHome({ page: wizFrom === 'conn' ? 'conn' : 'tasks' });
  chipEl()?.focus({ preventScroll: true });
}

/**
 * Задачу з кроку 4 створено (`task-new` уже зробив її простір і її поточними) — відкрити, як «Нова задача» на «Задачах»:
 * простір відповіді порівнюємо з відомим (`spaceChanged`), пер-задачний стан попередньої — чужий.
 */
async function wizOpenTask(made) {
  if (spaceChanged(spaceNow()?.id, made.space)) await resetSpaceState();
  else await resetPerTaskState();
  homeData = null;
  currentTaskId = made.id; taskSwitchGen += 1;
  await refreshGitlab();
  await leaveHome();
}
```
  ⚠️ `createWizard` кличеться під час завантаження модуля, а `spacesResp`, `api`, `postForm` тощо — оголошені вище чи функції-оголошення (підіймаються). Якщо `spacesResp` оголошено `let` НИЖЧЕ цього місця — це не помилка: залежності читають його лише в момент виклику (замикання), а не при створенні.
  5. `BAR_ACTIONS`: `spacenew: () => openSpaceNew(),` → `spacenew: () => openWizard(),`; `home:` → рівно

```js
  home: async () => { if (homeOpen && homePage === 'wiz') { await wiz.requestExit(); return; } if (cnDrawer && !(await dismissCnDrawer())) return; enterHome({ page: 'tasks' }); },
```
  6. `paintHome`: одразу після `homePaintPending = false;`:

```js
  /* Майстер (етап 3b) — раніше за привітання: на першому запуску просторів ще нема, а майстер уже відкритий. */
  if (homePage === 'wiz') { wiz.paint(); return; }
```
  7. `enterHome`: поруч із `if (next !== 'conn') closeCnDrawer({ focus: false });` додати `if (next !== 'wiz') wiz.reset();` (коментар: «Пішли з майстра будь-яким шляхом (⌘K, агент) — його стан більше не потрібен: простір, якщо створено, уже є»). Після `paintBar();` і ПЕРЕД `if (homePage === 'conn') {`:

```js
  if (homePage === 'wiz') {
    /* Майстер малює себе сам (`wiz.paint` через `paintHome`); фокус ставить `openWizard`/крок. Запізніле `loadHome` не
       сміє перемалювати сторінку. */
    homeSeq += 1;
    paintHome();
    return;
  }
```
  8. `leaveHome`: першим рядком тіла — `wiz.reset();`.
  9. `refreshHomeOnReturn`: перед рядком `homePage === 'conn' ? loadConn() : loadHome();` — `if (homePage === 'wiz') return;   // майстер тримає свої дані сам`.
  10. `wireHome`:
     - у слухачі `click` першим рядком після перевірки `a`: `if (homePage === 'wiz') { wiz.click(ev); return; }`;
     - `case 'spacenew': openSpaceNew(); break;` → `case 'spacenew': openWizard(); break;` і нижче `case 'spaceopen': openWizard({ folderFirst: true }); break;`;
     - у слухачі `input` першим рядком: `if (homePage === 'wiz') { wiz.input(ev); return; }`;
     - у слухачі `change` першим рядком: `if (homePage === 'wiz') { wiz.input(ev); return; }`;
     - новий слухач: `el.addEventListener('submit', (ev) => { if (homePage === 'wiz') wiz.submit(ev); });`.
  11. Клавіатура (≈ рядок 3102): `if (homePage === 'conn') return;   // «Підключення»…` → `if (homePage !== 'tasks') return;   // «Підключення» й майстер: клавіші списку задач не діють; Esc панелі — свій обробник`.
  12. Решта згадок `openSpaceNew` у файлі (коментарі, `focusKey`, `spaceDialogFocusBack`) — переписати на майстер або прибрати; `grep -n "openSpaceNew" app/app.js` мусить бути порожнім.

- [ ] **Step 4: Режим `new` діалогу простору прибрати.** У `app/space-dialogs.js`, `spaceDialogHTML`: параметр `mode` лишається (`edit` — єдиний, що малюється з оболонки), але гілка `isNew` зникає: без поля теки, без `spaceNewLead`, заголовок `spaceEditTitle`, кнопка `spaceSave`; `found`/`path` — прибрати з сигнатури. Шапку файла оновити: «Діалог простору — лише «Назва й колір…»; новий простір створює майстер (`wizard.js`), який бере звідси `wireSpaceDialog` і `wireTaskForm`». `wireSpaceDialog` і `wireTaskForm` НЕ чіпати (їх кличе майстер). У `tests/space-dialogs.test.mjs` тести розмітки `spaceDialogHTML({ mode: "new" … })` («гачки Task 8», «знайдений простір», «слот підказки `sp-registered`», «кожне поле посилається на слот помилки») переписати на `edit` там, де перевірка ще має сенс (кружки, слот помилки, екранування), а суто «нові» (тека, `sp-found`, `sp-registered`) — прибрати: їх тепер стереже `tests/wizard-view.test.mjs` (крок 1). Тести `wireSpaceDialog` з `mode: "new"` на заглушках (`spaceForm`) лишаються як є.

- [ ] **Step 5: Старі піни.** `tests/connections-wiring.test.mjs`:
  - обидва регекспи `home:` (тести «дії смуги» і «логотип і «назад до задачі»») → новий рядок з кроку 3.5;
  - тест «клавіші сторінки «Задачі» на «Підключенні» не діють» → `/if \(!homeOpen \|\| ev\.isComposing \|\| paletteOverlay \|\| document\.querySelector\('\.cv-ask-scrim'\)\) return;\n  if \(homePage !== 'tasks'\) return;/`.
  `tests/spaces-wiring.test.mjs` — кожен пін на `openSpaceNew`/`spacenew: () => openSpaceNew()` перевести на `openWizard` (суть піна — «вхід веде у створення простору» — та сама). Інших змін у цих файлах не робити.

- [ ] **Step 6: Повний набір юнітів.** Run: `python3 "$G" 900 3000 npm test` → зелено (зокрема `legacy-golden` без `UPDATE_GOLDEN`).

- [ ] **Step 7: Димова перевірка в браузері (руками, без коміту тестів).** Підняти ізольований сервер так само, як `tests/live/fixture.mjs` (`startServer(null, { portBase: 13500, spaces: [] })` у короткому скрипті в `<scratchpad>`), відкрити `/app/` у Playwright і пройти: привітання → «Створити простір» → крок 1 → «Далі» → крок 2 (є секції) → «Далі» → крок 3 → «Зберегти й далі» → крок 4 → «Пропустити» → «Задачі · Особисте». Помилки консолі — нуль. Сервер зупинити за PID. Знахідки — виправити до коміту.

- [ ] **Step 8: Commit.**
```bash
git add app/app.js app/space-dialogs.js tests/wizard-wiring.test.mjs tests/space-dialogs.test.mjs tests/connections-wiring.test.mjs tests/spaces-wiring.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(wizard): сторінка wiz оверлею, входи з привітання, дропдауна й ⌘K; діалог «Новий простір» прибрано

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: Живий тест майстра й перехід старих живих тестів на майстер

**Files:**
- Create: `tests/live/wizard.test.mjs`
- Modify: `tests/live/spaces.test.mjs` (сценарії 3, 4, 6), `tests/live/spaces-flows.test.mjs` (T4, T5, T6, T6b, T6c, T7, T7b, T11b)

- [ ] **Step 1: Живий тест.** Створити `tests/live/wizard.test.mjs`. Прилади `isLocal`, `watchLeaks`, `plantLeak`, `leaks` — скопіювати дослівно з `tests/live/connections.test.mjs` (зі своїм `SECRET`). Каркас:

```js
/**
 * Майстер нового простору (Deai 0.6.0, етап 3b) — живе проведення: справжній сервер в ізольованій «машині» (тимчасові
 * `HOME`/`DEAI_HOME`), справжній Chromium. Модулі-фікстури `memo-publish`/`memo-publish2` (`tests/fixtures/modules-conn`,
 * шов `DEAI_EXTRA_MODULES`) — роль `publish` з ЛОКАЛЬНОЮ перевіркою: жодної мережі. Vercel і Supabase не вмикаються.
 *
 * Юніти (`tests/wizard-*.test.mjs`) і сервер (`tests/test_task_from.py`) доводять ланки окремо; тут — те, що живе лише в
 * браузері: входи, перехід кроків і фокус, запис модулів зі «свіжістю», секрет лише у властивості поля, задача з теки
 * до рамки макета.
 *
 * Мапа «сценарій → запобіжник» (заповнити мутаційно на Step 3, як у `connections.test.mjs`).
 */
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, postJson, sleep, spacesApi, stop, text, waitText } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 13500;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "modules-conn");
const SECRET = "wiz-S3cret-Листопад-9";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* isLocal, watchLeaks, plantLeak, leaks — з connections.test.mjs */

/** Сервер (+ простори, коли дано) і сторінка; лічильники запитів і тіл відповідей API; нічого назовні. */
async function boot(t, { spaces = [] } = {}) {
  const server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_EXTRA_MODULES: MODULES_DIR }, spaces });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const outside = [];
  const requests = [];
  const posts = [];
  const bodies = [];
  context.on("request", (r) => {
    requests.push(r.url());
    if (r.method() === "POST") posts.push({ url: r.url(), body: r.postData() ?? "" });
    if (!isLocal(r.url())) outside.push(r.url());
  });
  context.on("response", async (r) => {
    if (r.url().includes("/api/")) { try { bodies.push(await r.text()); } catch { /* перервана */ } }
  });
  await context.route((u) => !isLocal(u.href), (route) => route.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await page.waitForSelector(spaces.length ? "#bar .space-chip" : "#tasks-home .th-welcome", { timeout: 15000 });
  await watchLeaks(page);
  await plantLeak(page);
  return { ...server, page, outside, requests, posts, bodies, errors };
}

const step = (page, n) => page.waitForSelector(`#tasks-home .wz[data-step="${n}"]`, { timeout: 15000 });
const next = (page) => page.click('#tasks-home .wz [data-a="ok"]');
const activeId = (page) => page.evaluate(() => document.activeElement?.id ?? null);
const spaceJson = (p) => JSON.parse(readFileSync(path.join(p, "space.json"), "utf8"));
const postsTo = (posts, p) => posts.filter((x) => new URL(x.url).pathname === p);

/** «Новий простір…» з дропдауна фішки (дочекатись рядків — перший показ малюється зі старою відповіддю). */
async function openFromMenu(page, rows = 1) {
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction((n) => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === n, rows);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await step(page, 1);
}

/** Перший запуск: привітання → «Створити простір» → «Далі» → крок 2 з картками. */
async function firstSpace(page) {
  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await step(page, 1);
  await next(page);
  await step(page, 2);
  await page.waitForSelector('input[data-wz-pick][value="memo-publish"]');
}
```

  Сценарії (кожен — окремий `test`; тексти — українською, як у сусідніх файлах):

  **W1 перший запуск, заміна постачальника, секрет, задача.** Привітання → «Створити простір»: `#sp-name` = «Особисте», `#sp-path` = `~/deai-work/personal`, фокус на `sp-name`, крихта `#bar .crumb--flat` — «Новий простір», фішки нема → «Далі» → крок 2: фокус на `wz-h`; у реєстрі рівно один простір (`spacesApi`); вибрано `static-publish`; мітка варіанта `memo-publish` містить «замість «Публікація в теку»» → `page.check('input[data-wz-pick][value="memo-publish"]')`, `static-publish` більше не вибрано → «Далі» → крок 3: картка `memo-publish` з бейджем «Буде підключено». Ввести `SECRET` у `[data-cn-field="token"]`, «Зберегти й далі» з порожнім `note` → помилка під полем (`.cn-field-err`), нових POST нема, секрет ЛИШИВСЯ у властивості поля (`inputValue`). Заповнити `note` = `ok` → «Зберегти й далі» → крок 4. Перевірити: `space.json` — `memo-publish.enabled === true`, `static-publish.enabled === false`; `secrets.json` (`<deaiHome>/secrets.json`) — `[<id простору>]["memo-publish"].token === SECRET`; рівно один `POST /api/module-enable`, його тіло — `replace: true` і `space: <id простору>`. Крок 4: «Onboarding» → `#tf-id` = `onboarding` → «Створити й відкрити» → оверлей закрито (`!body.home-open`), `/api/tasks` → `current: "onboarding"`, `#bar .space-name` — «Особисте». Секрет ніде: `page.content()`, `leaks(page)` порожньо, адреси запитів, тіла відповідей; свідок — секрет є в тілі одного POST. `outside` і `errors` порожні.

  **W2 меню → «Client» → задача з наявної теки.** `boot` із простором `Studio` (задача `t1` з `taskFixture`). `openFromMenu`: назва порожня; «Client» → тека `~/deai-work/client` → «Далі» → крок 2 → «Далі» → крок 3 (картка `static-publish`) → «Зберегти й далі» БЕЗ змін → крок 4, і жодного POST на `/api/module-enable|settings|disable`. Тека-джерело в `server.home`: `mock-landing/index.html` з `<h1 id="mark">LANDING</h1>`, `mock-landing/img/a.svg`, символьне посилання `mock-landing/link.txt` → файл поза текою. «Наявна тека з макетом» → поле `#wz-from` видиме і з фокусом → `~/mock-landing` → `#tf-title` = `mock-landing`, `#tf-id` = `mock-landing` → «Створити й відкрити». Тост `#cv-toast` — «Символьні посилання не скопійовано: 1»; на диску `<home>/deai-work/client/mock-landing/iterations/it1/{index.html,img/a.svg}` є, `link.txt` нема; рамка макета показує `#mark` = `LANDING` (рамку читати так само, як сценарій 8 `connections.test.mjs`); `spacesApi(...).current === "client"`.

  **W3 крок 1: відмова, зайнятість, «Скасувати».** `boot` зі `Studio`. Меню → назва «Dup», тека `<шлях Studio>/inner` → «Далі» → `#wz-err` видимий і містить «перетинається», `#sp-path[aria-invalid=true]`, фокус на `sp-path`; правка теки знімає `aria-invalid`; просторів досі 1. «Скасувати» → назад на полотно задачі `t1` (оверлей закрито), фокус на `#bar .space-chip`; просторів 1. Зайнятість: `page.route("**/api/space-new", …sleep(1200)…continue)` → меню → «Slow» → «Далі» → форма `aria-busy="true"`, `[data-a="cancel"]` і `[data-a="ok"]` вимкнені, Esc нічого не робить → крок 2; `POST /api/space-new` рівно один; `current === "slow"`.

  **W4 назад на крок 1, перейменування, «Закрити майстер».** Перший запуск → крок 2 → «Назад» → крок 1 у режимі `edit`, `#sp-path` `readOnly` → «Далі» без змін — жодного `POST /api/space-update` → крок 2 → «Назад» → назва «Моє» → «Далі» → рівно один `POST /api/space-update`, у реєстрі «Моє» → «Закрити майстер» → «Задачі · Моє», тост «Простір «Моє» готовий».

  **W5 незбережене на кроці 3.** Перший запуск → вибрати `memo-publish` → крок 3 → `note` = «draft» → Esc — лишаємось на кроці 3 → логотип (`#bar [data-act="home"]`) → питання (`.cv-ask-scrim`) → «Скасувати» → крок 3, `note` = «draft» → «Закрити майстер» → питання → «Відкинути» (`button[data-a="ok"]`) → «Задачі · Особисте»; у `space.json` нема `memo-publish`.

  **W6 свіжість і незалежність записів.** Перший запуск; у теку простору покласти `ds.css` (`:root{--c-a:#123456}`). Крок 2: вибрати `memo-publish` і `css-tokens` → крок 3: `note` = «ok», `css-tokens` `[data-cn-field="file"]` = `{space}/ds.css`. «Агент» напряму: `postJson(url, "/api/module-enable", {space, id: "memo-publish2", settings: {note: "agent"}, replace: true})` → 200. «Зберегти й далі» → картка `memo-publish` — `.cn-res--err` з «роль змінилась» і «Memo publish 2 (test)»; картка `css-tokens` — `.cn-res--ok`; лишаємось на кроці 3. `space.json`: `css-tokens.enabled === true`, `memo-publish` відсутній, `memo-publish2.enabled === true` (майстер не затер вибір агента); жодного `POST /api/module-enable` з `id: "memo-publish"`.

  **W7 наявна тека простору з привітання.** Перший запуск; у `server.home` тека `shared-space` з `ds.css`, `space.json` `{name: "Shared", color: "space-4", modules: {"css-tokens": {enabled: true, settings: {file: "{space}/ds.css"}}}}` і `tasks.json` з однією задачею `s1` (тека з `taskFixture`). «Відкрити наявну теку простору» → фокус на `sp-path` → `~/shared-space` → підказка `#sp-found` видима, `#sp-name` = «Shared» і `readOnly` → «Далі» → крок 2: `css-tokens` вибрано → «Далі» → крок 3 (картка `css-tokens`) → «Зберегти й далі» → крок 4: лід «Задач у просторі вже: 1», кнопка «До задач» → «Задачі · Shared», картка `s1`.

  Наприкінці файла — `guardRealDeai();`.

- [ ] **Step 2: Прогін.** Run: `python3 "$G" 900 3000 node --test --test-concurrency=1 tests/live/wizard.test.mjs` → 7/7 (+ охоронець). Падіння розбирати по коду (`superpowers:systematic-debugging`): спершу — чи розмітка/контролер відповідають спеці; тест правити лише тоді, коли помилявся сам тест.

- [ ] **Step 3: Мутаційна мапа.** Для кожного сценарію прибрати один запобіжник у коді, прогнати файл, вернути побайтно (`git stash`/`git diff` порожній після повернення) і записати в шапку файла, які сценарії червоніють:
  - `replace` у `runOp` (`op.op === "enable"` → `false`) — W1 (409 `role-taken`);
  - перевірка `op.stale.length` у `runOp` — W6;
  - `missingRequired` у `submit3` — W1;
  - `keep.secrets` у `paint` (не вертати `.value`) — W1 (секрет зник після помилки);
  - `clearSecrets` у `runOp` — W1 (секрет у полі після відповіді: `page.content()` його не бачить, тож додати перевірку `inputValue === ""` після кроку 3, якщо мутація виживає);
  - `adopt_scan` пропуск посилань (серверний) — W2;
  - `wizBack` (`leaveHome` → `enterHome`) — W3;
  - `askDiscard` у `requestExit` — W5;
  - `pathTouched` у `wire` — W3/W4 (якщо виживає — це чесно записати як «стереже юніт `space-dialogs`»).
  Мутація, що вижила всюди, — або дописати перевірку в сценарій, або записати, хто її стереже (юніт, сервер-тест).

- [ ] **Step 4: Старі живі тести — на майстер.** Спільний прилад у кожному з двох файлів:

```js
/** Крок 1 майстра відправлено — дочекатись кроку 2 й закрити майстер (тестам потрібен лише простір). */
async function closeWizard(page) {
  await page.waitForSelector('#tasks-home .wz[data-step="2"]', { timeout: 15000 });
  await page.click('#tasks-home .wz [data-wz="close"]');
}
```
  `tests/live/spaces.test.mjs`:
  - **3**: після `click(... [data-a="ok"])` — `await closeWizard(page)`; решта перевірок як є (форма простору зникла — крок 2 її не має).
  - **4**: так само; назва сценарію — «…→ «Далі» → «Закрити майстер» → «Задачі · Особисте»».
  - **6**: слот помилки — `#wz-err` замість `[data-form-error]` (роль `alert` та сама); «Скасувати» — та сама кнопка `[data-a="cancel"]`.
  `tests/live/spaces-flows.test.mjs`:
  - **T4**, **T5**: після кожного `ok`, що створює простір, — `closeWizard`.
  - **T6** → «зайнята форма майстра»: `aria-busy="true"`, «Скасувати» і «Далі» вимкнені, Esc нічого не робить, `POST /api/space-new` рівно один, перехід — крок 2, `current === "client"`. Перевірки «⌘K не відкрився поверх форми» прибрати: майстер — сторінка, не модальний діалог (палітра над нею дозволена; рішення спеки 3b).
  - **T6b**: `#wz-err` замість `[data-form-error]`; точний колір `rgb(194, 54, 46)` (світлий діалог) замінити на «рамка поля з помилкою відрізняється і від своєї звичайної, і від сусіднього поля» (на темній сторінці рамка — `--bad`).
  - **T6c**: стеля 20 с та сама (`postForm`); текст — у `#wz-err`; форма знову вільна; повтор → крок 2.
  - **T7 (i)**: «Новий простір…» клавіатурою → крок 1 → «Скасувати» → полотно задачі, фокус на фішці (`chipFocused`). **(iii)** — замість «Нового простору» відкрити «Назва й колір…» (`spaceedit`): охоронець «діалог не краде фокус у рамки» стосується діалогу, що лишився.
  - **T7b**: привітання → майстер → `focus` вікна (майстер НЕ перемальовується: `refreshHomeOnReturn` його пропускає — свідок «відчепленого відкривача» прибрати) → «Скасувати» → привітання, фокус на `[data-th="spacenew"]`.
  - **T11b**: після `ok` → `closeWizard` → «Задачі · Особисте»; `POST /api/space-new` рівно 1; стелі `GET /api/spaces` і `GET /api/tasks-overview` перевиміряти й записати з поясненням (крок 2 — `GET /api/modules`; «Закрити майстер» — `enterHome` → `loadHome`).
  Номери портів цих файлів не міняти.

- [ ] **Step 5: Прогін затронутих живих тестів послідовно.** Run (по одному):
  `python3 "$G" 900 3000 node --test --test-concurrency=1 tests/live/spaces.test.mjs`,
  `… tests/live/spaces-flows.test.mjs`, `… tests/live/connections.test.mjs`, `… tests/live/tasks-home.test.mjs`,
  `… tests/live/shell-bar.test.mjs`, `… tests/live/shell-palette.test.mjs` → зелені. Плюс `node --test tests/live-ports.test.mjs`.

- [ ] **Step 6: Commit.**
```bash
git add tests/live/wizard.test.mjs tests/live/spaces.test.mjs tests/live/spaces-flows.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(wizard): живий сценарій майстра; старі тести діалогу «Новий простір» — на майстер

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Документи й версія 0.6.0

**Files:**
- Modify: `package.json` (`"version": "0.6.0"`)
- Modify: `CHANGELOG.md` (новий розділ `[0.6.0] — 21.10.2026` над `[0.5.0]`)
- Modify: `README.md` (етап 3b ✅; майстер у розділі про простори; `from` у таблиці API — уже з Task 1)
- Modify: `docs/design/spaces-and-modules.md` (Onboarding: майстер збудовано; Stages: 3b ✅; Status: «Stage 3b — first-run wizard (0.6.0, 21.10.2026)»)

- [ ] **Step 1: CHANGELOG** (англійською, як попередні розділи):

```markdown
## [0.6.0] — 21.10.2026

Stage 3b: the new-space wizard.

### Added
- **New-space wizard** — four steps instead of the "New space" dialog: Space → Modules → Settings → First task. The
  first run (no spaces) and "New space…" (space menu, ⌘K) open the same wizard. The space is created on step 1 with
  the real API, so closing the wizard at any step leaves a working space; the rest can be finished in Connections.
- **Modules step**: one choice per role (a module, or "No module" with what that means); a module that replaces the
  current provider says so ("instead of …"). **Settings step**: the same fields as the Connections side panel,
  secrets included (never rendered, cleared after each server response); one pass writes everything (replacing a
  provider atomically), checks each module and stops on the step when anything failed. If an agent changed a role
  while the person was choosing, that module is not written and its card says why.
- **First task**: a blank page, **an existing mockup folder** (copied into the first iteration), or a phrase to give
  the agent; or skip.
- **`from` in `POST /api/task-new`** — copies a folder with `index.html` into the task's first iteration, only in a
  space without integrations. Symbolic links, `.git` and `node_modules` are never copied; at most 2000 files and
  200 MB; the folder must not contain the task folder; the response carries `copied: {files, bytes, skipped_links}`.
- The welcome screen gets a second button, "Open an existing space folder".

### Changed
- The "New space" dialog is gone; the space dialog stays for "Name and colour…".

### Not in this release
- Picking folders with the system dialog; resuming an unfinished wizard after a restart; a space's own modules and
  the trust dialog (3c, 0.7.0); starting an agent from the wizard.
```

- [ ] **Step 2: README і дизайн-документ.** README: у дорожній карті `3b` — ✅ (0.6.0), `3c` — «next»; у розділі про простори — абзац про майстер (кроки, вхід, «Відкрити наявну теку простору»). `docs/design/spaces-and-modules.md`: у «Onboarding» замінити курсив «*Stage 3b, 0.6.0 — not built yet…*» на «*Built in stage 3b (0.6.0)* — see *Status → Stage 3b*»; у «Stages» — `✅ **3b** (0.6.0)`; у «Status» — підрозділ «Stage 3b — new-space wizard (0.6.0, 21.10.2026)» на 5–8 рядків (що зроблено, `from`, що поза релізом). Рядок угорі про поточний етап — «Next: 3c (a space's own modules, 0.7.0)».

- [ ] **Step 3: Повний прогін.** Run: `python3 "$G" 900 3000 npm test` → зелено; `git diff --stat` — лише документи й `package.json`.

- [ ] **Step 4: Commit.**
```bash
git add package.json CHANGELOG.md README.md docs/design/spaces-and-modules.md
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "docs: 0.6.0 — майстер нового простору (етап 3b)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Після задач (контролер)

1. Фінальне ревʼю всього діапазону (рецензент на `git archive`-експорті, Playwright-проби: перший запуск, меню, задача з теки, свіжість, вихід з незбереженим, мова посеред кроку 3, вузьке вікно 375 px).
2. Повний набір: `npm test` на Python 3.13 і системному 3.9; усі затронуті живі тести послідовно; `legacy-golden` без `UPDATE_GOLDEN`.
3. Перед пушем — скан діапазону на локальні шляхи, імена й ключі (як для 0.5.0); знайдене — лише з дозволу власника й з бекапом-бандлом.
4. Тег `v0.6.0` (теґер — `neodisa`), пуш явно: `git push origin <sha>:refs/heads/main` і `git push origin refs/tags/v0.6.0`.
5. Памʼять: запис у `project-deai-opensource.md` і рядок індексу.
