# «Видалені» — перелік видалених ітерацій. План реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Внизу дропдауна ітерації — розділ «Видалені» з кошика задачі. Кожен рядок показує, скільки лишилось, і має
кнопку «Повернути»; той самий розділ відкриває пункт ⌘K.

**Architecture:**
- **Сервер:** чиста функція `iter_trash.list_slots` читає `.trash/iterations/`; `GET /api/task` віддає її як
  `iteration_trash`.
- **Клієнт:**
  - `bar-model.js` передає записи в модель крошки ітерації;
  - `shell-bar.js` малює розділ і рахує «скільки лишилось» (`trashLeft`);
  - `app.js` тримає прапорець розгортання `iterGone` і кличе наявний `restoreIteration`.
- Нових маршрутів немає.

**Tech Stack:** Python stdlib (`app/serve.py`, `app/iter_trash.py`, `unittest`); vanilla ES modules (`node --test`);
Playwright для живого тесту.

Спека: `docs/superpowers/specs/2026-11-23-iteration-trash-list-design.md` (погоджений прототип — варіант А).

---

## Спільні правила (для кожного виконавця)

- **Де працюємо.** Worktree `deai-canvas-dev`, гілка `feat/iteration-trash-list`. Іншу гілку не перемикати.
- **Коміт** — лише шляхами:
  ```
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<subject>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <paths>
  ```
  Нові файли — спершу `git add -- <path>`.
- **Заборонено:**
  - `git add -A`, `reset`, `rebase`, `--amend`, голий `git stash`;
  - додавати в індекс `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і
    `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`;
  - `pkill`/`killall` за шаблоном; `rm -rf` (тимчасові теки — `mktemp -d`).
- **Тести не чіпають:**
  - порти 8765/4317;
  - живу теку `~/Liga Tools/deai-canvas`;
  - справжні `~/.deai`, `~/deai-published`, `~/deai-work`, `~/.gitconfig`;
  - мережу.
- **Python** завжди `python3 -B`.
- **Команди тестів:**
  - Python: `python3 -B -m unittest discover -s tests -p "test_*.py"`.
  - Node: `node --test tests/*.test.mjs`.
  - Живі — один файл під спільним замком і з тимчасовим HOME:
    ```
    until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; H=$(mktemp -d); HOME="$H" node --test --import ./tests/live/_env.mjs tests/live/<file>; rc=$?; rmdir /private/tmp/deai-live.lock; exit $rc
    ```
    `rmdir` — лише після власного вдалого `mkdir`. Під час живого прогону код не правити.
- **Підписи в інтерфейсі.** Жодних, яких нема в спеці.

---

### Task 1: Сервер — `list_slots` і `iteration_trash` у `/api/task`

**Files:**
- Modify: `app/iter_trash.py` (нова функція після `purge`)
- Modify: `app/serve.py` (новий хелпер після `task_api_iterations`, ~рядок 2928; поле у `/api/task`, ~рядок 6732)
- Test: `tests/test_iter_trash.py` (новий клас `ListSlots`)
- Test: `tests/test_iteration_api.py` (новий клас `TrashList(_Base)`)

- [ ] **Step 1: Failing tests for `list_slots`** — append to `tests/test_iter_trash.py`:

```python
class ListSlots(unittest.TestCase):
    """Перелік кошика для інтерфейсу («Видалені»): найсвіжіше першим, нічого не пише, пропускає сміття й прострочене."""

    def setUp(self):
        self.d = _task(['it1', 'it2', 'it3', 'it4'])
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_newest_first_with_times(self):
        a = tr.move_to_trash(self.d, {'id': 'it2', 'note': 'Друга'}, T0)
        b = tr.move_to_trash(self.d, {'id': 'it3'}, T0 + datetime.timedelta(hours=2))
        got = tr.list_slots(self.d, T0 + datetime.timedelta(hours=3))
        self.assertEqual([x['trash'] for x in got], [b, a])
        self.assertEqual(got[1]['entry'], {'id': 'it2', 'note': 'Друга'})
        self.assertEqual((got[1]['deleted_at'], got[1]['expires_at']), ('2026-11-23T10:00:00Z', '2026-11-30T10:00:00Z'))

    def test_same_second_suffix_is_newer(self):
        a = tr.move_to_trash(self.d, {'id': 'it2'}, T0)
        os.makedirs(os.path.join(self.d, 'iterations', 'it2'))
        b = tr.move_to_trash(self.d, {'id': 'it2'}, T0)
        self.assertEqual([x['trash'] for x in tr.list_slots(self.d, T0)], [b, a])

    def test_skips_junk_and_expired(self):
        ok = tr.move_to_trash(self.d, {'id': 'it2'}, T0)
        root = os.path.join(self.d, '.trash', 'iterations')
        os.makedirs(os.path.join(root, 'not a slot'))                             # чуже імʼя
        os.makedirs(os.path.join(root, 'it5--20261123-090000'))                   # без entry.json (залишок restore_finish)
        os.makedirs(os.path.join(root, 'it6--20261123-090000'))
        with open(os.path.join(root, 'it6--20261123-090000', 'entry.json'), 'w', encoding='utf-8') as f:
            f.write('{не json')                                                  # битий
        os.makedirs(os.path.join(root, 'it7--20261123-090000'))
        with open(os.path.join(root, 'it7--20261123-090000', 'entry.json'), 'w', encoding='utf-8') as f:
            json.dump(['entry'], f)                                               # не тієї форми
        os.makedirs(os.path.join(root, 'it8--20261123-090000'))
        with open(os.path.join(root, 'it8--20261123-090000', 'entry.json'), 'w', encoding='utf-8') as f:
            json.dump({'entry': {'id': '..'}}, f)                                 # небезпечний id
        tr.move_to_trash(self.d, {'id': 'it3'}, T0 - datetime.timedelta(days=8))  # прострочений
        self.assertEqual([x['trash'] for x in tr.list_slots(self.d, T0)], [ok])

    def test_seven_day_boundary_matches_purge(self):
        s = tr.move_to_trash(self.d, {'id': 'it2'}, T0)
        edge = T0 + datetime.timedelta(days=tr.KEEP_DAYS)
        self.assertEqual([x['trash'] for x in tr.list_slots(self.d, edge)], [s])   # рівно 7 діб — ще є (як у purge)
        self.assertEqual(tr.list_slots(self.d, edge + datetime.timedelta(seconds=1)), [])

    def test_no_trash_is_empty_and_listing_writes_nothing(self):
        self.assertEqual(tr.list_slots(self.d, T0), [])
        self.assertFalse(os.path.exists(os.path.join(self.d, '.trash')))
        tr.move_to_trash(self.d, {'id': 'it2'}, T0 - datetime.timedelta(days=9))
        before = sorted(os.listdir(os.path.join(self.d, '.trash', 'iterations')))
        tr.list_slots(self.d, T0)
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, '.trash', 'iterations'))), before)  # не прибирає
```

- [ ] **Step 2: Run them — expect FAIL** (`AttributeError: module 'iter_trash' has no attribute 'list_slots'`):

`python3 -B -m unittest tests.test_iter_trash.ListSlots -v`

- [ ] **Step 3: Implement `list_slots`** — in `app/iter_trash.py` right after `purge`:

```python
def list_slots(task_dir, now, keep_days=KEEP_DAYS):
    """Перелік кошика для інтерфейсу («Видалені»): `[{trash, entry, deleted_at, expires_at}]`, найсвіжіше першим. НЕ пише й не
    прибирає (це `purge` при видаленні). Вік — за датою в імені слота, тим самим правилом, що в `purge` (рівно `keep_days` —
    ще в кошику), тож перелік і прибирання не розходяться. Пропускає чужі імена, слоти без читабельного `entry.json` (залишок
    після `restore_finish`), запис не тієї форми, небезпечний `id` і прострочені слоти. Нема кошика — `[]`."""
    root = trash_root(task_dir)
    try:
        names = os.listdir(root)
    except OSError:
        return []
    edge = now - datetime.timedelta(days=keep_days)
    found = []
    for name in names:
        s = SLOT_RE.fullmatch(name)
        if not s:
            continue
        try:
            at = datetime.datetime.strptime(s.group(2), '%Y%m%d-%H%M%S').replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if at < edge:
            continue
        try:
            with open(os.path.join(root, name, 'entry.json'), encoding='utf-8') as f:
                entry = json.load(f)['entry']
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not isinstance(entry, dict) or not _safe_id(entry.get('id')):
            continue
        found.append((at, name, dict(entry)))
    found.sort(key=lambda x: (x[0], x[1]), reverse=True)        # той самий час — суфікс `-N` новіший
    fmt = '%Y-%m-%dT%H:%M:%SZ'
    return [{'trash': name, 'entry': entry, 'deleted_at': at.strftime(fmt),
             'expires_at': (at + datetime.timedelta(days=keep_days)).strftime(fmt)}
            for at, name, entry in found]
```

- [ ] **Step 4: Run — expect PASS:** `python3 -B -m unittest tests.test_iter_trash -v`

- [ ] **Step 5: Failing API tests** — append to `tests/test_iteration_api.py`:

```python
class TrashList(_Base):
    """`/api/task` несе кошик (`iteration_trash`) для розділу «Видалені»: зʼявляється після видалення, зникає після повернення."""

    def test_task_carries_trash_after_delete_and_drops_it_after_restore(self):
        st, task = self.jget('/api/task')
        self.assertEqual((st, task['iteration_trash']), (200, []))
        _, d = self.post('/api/iteration-delete', {'id': 'it2'})
        _, task = self.jget('/api/task')
        self.assertEqual(len(task['iteration_trash']), 1)
        row = task['iteration_trash'][0]
        self.assertEqual((row['trash'], row['id']), (d['trash'], 'it2'))
        self.assertTrue(row['label_text'].startswith('Іт.2'), row)
        self.assertRegex(row['deleted_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertRegex(row['expires_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertEqual(set(row), {'trash', 'id', 'label_text', 'deleted_at', 'expires_at'})
        self.post('/api/iteration-restore', {'trash': d['trash']})
        _, task = self.jget('/api/task')
        self.assertEqual(task['iteration_trash'], [])

    def test_broken_trash_never_breaks_the_task_screen(self):
        with mock.patch('iter_trash.list_slots', side_effect=OSError('x')):
            st, task = self.jget('/api/task')
        self.assertEqual((st, task['iteration_trash']), (200, []))
```

- [ ] **Step 6: Run — expect FAIL** (`KeyError: 'iteration_trash'`):

`python3 -B -m unittest tests.test_iteration_api.TrashList -v`

- [ ] **Step 7: Implement.** In `app/serve.py`, right after `task_api_iterations` (~line 2928):

```python
def task_iteration_trash(task):
    """Кошик ітерацій для `/api/task` (`iteration_trash`, розділ «Видалені»): найсвіжіше першим, з тим самим `label_text`, що в
    переліку. Будь-який збій читання → `[]`: екран задачі не сміє впасти через кошик."""
    try:
        return [{'trash': x['trash'], 'id': x['entry']['id'], 'label_text': iteration_label(x['entry']),
                 'deleted_at': x['deleted_at'], 'expires_at': x['expires_at']}
                for x in iter_trash.list_slots(task['dir'], iter_trash.utcnow())]
    except Exception:
        return []
```

In the `/api/task` handler (`out = {...}`, ~line 6732), right after `'iterations': task_api_iterations(meta),` add:

```python
                   # Кошик ітерацій (розділ «Видалені» дропдауна): `render()` перечитує задачу після видалення й
                   # повернення, тож окремого маршруту не треба.
                   'iteration_trash': task_iteration_trash(task),
```

- [ ] **Step 8: Run — expect PASS:**

`python3 -B -m unittest tests.test_iter_trash tests.test_iteration_api -v`

Then the whole Python suite: `python3 -B -m unittest discover -s tests -p "test_*.py"` → `OK`.

- [ ] **Step 9: Commit**

```
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(trash-list): list_slots + iteration_trash у /api/task" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/iter_trash.py app/serve.py tests/test_iter_trash.py tests/test_iteration_api.py
```

---

### Task 2: Клієнт — розділ «Видалені», ⌘K, i18n, стилі

**Files:**
- Modify: `app/i18n.js` (UK біля `iterRestoreFailed` ~рядок 372 і `iterHistoryPal` ~175; EN — ті самі місця ~1870 і ~1712)
- Modify: `app/bar-model.js` (~рядок 195, запис `zone1` з `id: "iter"`)
- Modify: `app/shell-bar.js`:
  - `trashLeft` і розмітка розділу — перед `crumbIter`;
  - `crumbIter` — ~рядок 211;
  - виклик крошки — ~рядок 476.
- Modify: `app/shell-palette.js` (група `gIter`, ~рядок 307; опис стану, ~рядок 90)
- Modify: `app/app.js`:
  - `let iterGone` — біля `iterUi`, ~231;
  - `paintBar` — ~1292;
  - `barState` — ~1078;
  - делегація кліку смуги — ~3823;
  - `BAR_ACTIONS` — біля `histcur`, ~3190;
  - `paletteState` — ~9769.
- Modify: `app/styles.css` (після правила `.dd--itmenu`, ~рядок 1061)
- Test: `tests/shell-bar.test.mjs`, `tests/shell-palette.test.mjs`

- [ ] **Step 1: Failing tests** — append to `tests/shell-bar.test.mjs` (`trashLeft` додай в імпорт із `../app/shell-bar.js` поруч із
  `initials`):

```js
/* «Видалені» (патч після 0.36.0): розділ кошика внизу переліку ітерацій. */
const TR = [
  { trash: "it5--20261123-124000", label: "Іт.5", note: "Темна тема", deletedAt: "2026-11-23T12:40:00Z", expiresAt: "2026-11-30T12:40:00Z" },
  { trash: "it3--20261116-150000", label: "Іт.3", note: "", deletedAt: "2026-11-16T15:00:00Z", expiresAt: "2026-11-23T15:00:00Z" },
];
const NOW = Date.parse("2026-11-23T12:40:00Z");

test("«Видалені»: порожній кошик — розділу нема зовсім (ні роздільника, ні підпису)", () => {
  const a = itHtml({});
  const b = itHtml({ iterTrash: [] });
  assert.equal(a, b);
  assert.doesNotMatch(b, /it-gone|itgone/);
});

test("«Видалені»: заголовок під «Новою ітерацією», з числом; згорнутий — без рядків", () => {
  setLang("uk");
  const h = itHtml({ iterTrash: TR, now: NOW });
  assert.match(h, /<button class="dd-item it-gone-h" data-act="itgone" aria-expanded="false">/);
  assert.match(h, /<span class="dd-t">Видалені<\/span>/);
  assert.match(h, /<span class="dd-marks">2<svg/);
  assert.ok(h.indexOf('data-act="newit"') < h.indexOf('data-act="itgone"'), "розділ не під «Новою ітерацією»");
  assert.doesNotMatch(h, /class="it-gone"|data-act="itback"/);
});

test("«Видалені»: розгорнутий — рядки найсвіжіше першим, скільки лишилось, «Повернути» на слот", () => {
  setLang("uk");
  const h = itHtml({ iterTrash: TR, iterGone: true, now: NOW });
  assert.match(h, /aria-expanded="true"/);
  const backs = [...h.matchAll(/data-act="itback" data-val="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(backs, ["it5--20261123-124000", "it3--20261116-150000"]);
  assert.match(h, /<span class="it-gone-t">Іт\.5 · Темна тема<\/span>/);
  assert.match(h, /<span class="it-gone-t">Іт\.3<\/span>/);
  assert.match(h, /<span class="it-gone-s">ще 7 дн\.<\/span>/);
  assert.match(h, /<span class="it-gone-s it-gone-s--soon">ще 2 год\.<\/span>/);
  assert.match(h, /title="Іт\.5 · Темна тема — видалено \d\d\.\d\d\.2026 о \d\d:\d\d"/);
  assert.match(h, /aria-label="Повернути Іт\.5 · Темна тема">Повернути<\/button>/);
});

test("«Видалені»: закритий дропдаун розділу не малює; назва екранується", () => {
  assert.doesNotMatch(itHtml({ iterTrash: TR, iterGone: true, openDd: null }), /it-gone/);
  const h = itHtml({ iterTrash: [{ ...TR[0], note: 'A"<b>' }], iterGone: true, now: NOW });
  assert.doesNotMatch(h, /<b>/);
  assert.match(h, /A&quot;&lt;b&gt;/);
});

test("trashLeft: дні округлено, години вниз, менше години / минуле / зіпсоване — попередження", () => {
  setLang("uk");
  const at = "2026-11-30T12:00:00Z";
  const H = 3600e3;
  const end = Date.parse(at);
  assert.deepEqual(trashLeft(at, end - 7 * 24 * H), { text: "ще 7 дн.", soon: false });
  assert.deepEqual(trashLeft(at, end - 36.5 * H), { text: "ще 2 дн.", soon: false });
  assert.deepEqual(trashLeft(at, end - 24 * H), { text: "ще 1 дн.", soon: false });
  assert.deepEqual(trashLeft(at, end - 23.9 * H), { text: "ще 23 год.", soon: true });
  assert.deepEqual(trashLeft(at, end - H), { text: "ще 1 год.", soon: true });
  assert.deepEqual(trashLeft(at, end - 59 * 60e3), { text: "менше години", soon: true });
  assert.deepEqual(trashLeft(at, end + H), { text: "менше години", soon: true });
  assert.deepEqual(trashLeft("зіпсовано", end), { text: "менше години", soon: true });
  setLang("en");
  assert.deepEqual(trashLeft(at, end - 24 * H), { text: "1 day left", soon: false });
  assert.deepEqual(trashLeft(at, end - 3 * 24 * H), { text: "3 days left", soon: false });
  setLang("uk");
});
```

Append to `tests/shell-palette.test.mjs`:

```js
test("⌘K «Видалені ітерації»: лише коли кошик не порожній, у групі ітерації; не на екрані «Задачі»", () => {
  const find = (o) => paletteActions(S(o)).find((a) => a.id === "ittrash");
  assert.equal(find({}), undefined);
  assert.equal(find({ iterTrashCount: 0 }), undefined);
  const a = find({ iterTrashCount: 2 });
  assert.deepEqual({ act: a.act, group: a.group, labelKey: a.labelKey, icon: a.icon },
    { act: "ittrash", group: "gIter", labelKey: "iterTrashPal", icon: "trash" });
  assert.equal(find({ iterTrashCount: 2, homeOpen: true }), undefined);
});
```

- [ ] **Step 2: Run — expect FAIL:** `node --test tests/shell-bar.test.mjs tests/shell-palette.test.mjs` (`trashLeft` не
  експортовано; `ittrash` нема).

- [ ] **Step 3: i18n.** In `app/i18n.js`.

UK, right after `iterRestoreFailed`:

```js
  iterTrash: 'Видалені',
  iterRestoreAria: (l) => `Повернути ${l}`,
  trashLeftDays: (n) => `ще ${n} дн.`,
  trashLeftHours: (n) => `ще ${n} год.`,
  trashLeftUnderHour: 'менше години',
  trashDeletedAt: (l, d, tm) => `${l} — видалено ${d} о ${tm}`,
```

UK, right after `iterHistoryPal`: `iterTrashPal: 'Видалені ітерації',`

EN, right after `iterRestoreFailed`:

```js
  iterTrash: 'Deleted',
  iterRestoreAria: (l) => `Restore ${l}`,
  trashLeftDays: (n) => `${n} ${n === 1 ? 'day' : 'days'} left`,
  trashLeftHours: (n) => `${n} h left`,
  trashLeftUnderHour: 'under an hour',
  trashDeletedAt: (l, d, tm) => `${l} — deleted ${d} at ${tm}`,
```

EN, right after `iterHistoryPal`: `iterTrashPal: 'Deleted iterations',`

- [ ] **Step 4: Model.** In `app/bar-model.js`, inside the `zone1.push({ id: "iter", … })` object, after the `items: …`
  property, add:

```js
      /* Кошик (розділ «Видалені», патч після 0.36.0): найсвіжіше першим, як віддав сервер; підпис — тими самими полями, що й
         рядок переліку (`label` мовою глядача + `note`). */
      trash: (s.iterTrash || []).map((x) => ({
        trash: x.trash, label: x.label, note: x.note || "", deletedAt: x.deletedAt || "", expiresAt: x.expiresAt || "",
      })),
```

- [ ] **Step 5: Markup.** In `app/shell-bar.js`, insert before `function crumbIter`:

```js
/* «Видалені» (патч після 0.36.0): скільки лишилось до автоочищення кошика — від `expiresAt` до `nowMs`. Чиста (тести без DOM).
   ≥ доби — дні, округлені до найближчих (свіжовидалена — «ще 7 дн.»); < доби — години вниз; < години, минуле чи зіпсоване —
   «менше години». `soon` — колір попередження. */
export function trashLeft(expiresAt, nowMs = Date.now()) {
  const ms = Date.parse(expiresAt) - nowMs;
  const H = 3600e3;
  const D = 24 * H;
  if (!(ms >= H)) return { text: t("trashLeftUnderHour"), soon: true };
  if (ms < D) return { text: t("trashLeftHours", Math.floor(ms / H)), soon: true };
  return { text: t("trashLeftDays", Math.round(ms / D)), soon: false };
}

const pad2 = (n) => String(n).padStart(2, "0");
/** Локальні дата й час видалення для підказки рядка (`DD.MM.YYYY`, `HH:MM`); зіпсоване — `null`. */
function deletedWhen(at) {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return null;
  return [`${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`, `${pad2(d.getHours())}:${pad2(d.getMinutes())}`];
}

function goneRow(x, nowMs) {
  const title = x.note ? `${x.label} · ${x.note}` : x.label;
  const when = deletedWhen(x.deletedAt);
  const tip = when ? t("trashDeletedAt", title, when[0], when[1]) : title;
  const left = trashLeft(x.expiresAt, nowMs);
  return `<div class="it-gone" title="${esc(tip)}">${ico("iter")}`
    + `<span class="it-gone-b"><span class="it-gone-t">${esc(title)}</span>`
    + `<span class="it-gone-s${left.soon ? " it-gone-s--soon" : ""}">${esc(left.text)}</span></span>`
    + `<button type="button" class="it-back" data-act="itback" data-val="${esc(x.trash)}"`
    + ` aria-label="${esc(t("iterRestoreAria", title))}">${esc(t("iterRestore"))}</button></div>`;
}

/* Розділ стоїть найнижче (під «Новою ітерацією»): дія рідкісна. Порожній кошик — рядок порожній, щоб розмітка дропдауна без кошика
   лишилась байт-у-байт такою, як була. */
function goneSection(trash, gone, nowMs) {
  if (!trash.length) return "";
  return `<div class="dd-sep"></div>`
    + `<button class="dd-item it-gone-h" data-act="itgone" aria-expanded="${gone}">${ico("trash")}`
    + `<span class="dd-body"><span class="dd-t">${esc(t("iterTrash"))}</span></span>`
    + `<span class="dd-marks">${trash.length}${ico("chevright", 14, "ico caret")}</span></button>`
    + (gone ? `<div class="it-gone-list">${trash.map((x) => goneRow(x, nowMs)).join("")}</div>` : "");
}
```

Change the signature of `crumbIter` to
`function crumbIter(model, openDd, ui = null, modActs = [], overview = false, gone = false, nowMs = Date.now())`. In its
`dd` template, append `${goneSection(it.trash || [], gone, nowMs)}` directly after the `newit` `ddItem(...)` call, with
nothing in between, so the closing becomes:

```js
    ${ddItem({ act: "newit", icon: "plus", title: t("newIteration") })}${goneSection(it.trash || [], gone, nowMs)}
  </div>${menuFor ? iterMenu(menuFor, items.length, modActs, overview) : ""}` : "";
```

At the call site (~line 476), pass the two new arguments:

```js
  const iter = home ? "" : crumbIter(model, openDd, state?.iterUi ?? null, Array.isArray(state?.modActs) ? state.modActs : [],
    state?.mode === "overview", state?.iterGone === true, typeof state?.now === "number" ? state.now : Date.now());
```

- [ ] **Step 6: Palette.** In `app/shell-palette.js`, inside `if (hasIteration) { … }` of the `gIter` block, after the
  `ithist` line:

```js
    /* «Видалені» (патч після 0.36.0): лише коли кошик не порожній — порожнього кошика палітра не обіцяє. */
    if (s.iterTrashCount > 0) out.push({ id: "ittrash", group: "gIter", labelKey: "iterTrashPal", icon: "trash", act: "ittrash" });
```

In the state doc comment near `hasIteration: boolean` (~line 90), add the line
` *   iterTrashCount: number — скільки ітерацій у кошику задачі (пункт «Видалені ітерації»)`.

- [ ] **Step 7: Wiring in `app/app.js`.**

7a. Next to `let iterUi = …` (~line 231):

```js
/* Розділ «Видалені» дропдауна ітерації розгорнутий? Окремо від `iterUi`: меню «⋯», поле назви й питання про видалення його не
   згортають. Живе лише поки дропдаун ітерації відкритий — скидає `paintBar`. */
let iterGone = false;
```

7b. In `paintBar`, replace
`if (openDd !== 'iter') iterUi = IT_NONE;   // …`
with:

```js
  if (openDd !== 'iter') { iterUi = IT_NONE; iterGone = false; }   // меню рядка, поле назви, питання й розділ «Видалені» живуть лише у відкритому дропдауні ітерації
```

7c. In `barState()`, extract the note-stripping into a helper, declared once above `barState` (next to `itNum`, ~line 974):

```js
/** Примітка ітерації без префікса «Іт.N · » з `label_text` сервера (номер малює клієнт мовою глядача). */
const itNoteOf = (x) => (x.label_text || '').replace(new RegExp(`^Іт\\.${itNum(x.id)}\\s*(?:·\\s*)?`), '');
```

Then use it in `iterList` (`note: itNoteOf(x),` instead of the inline `replace`). After the `iterList: …` property add:

```js
    /* Кошик (розділ «Видалені»): ті самі поля, що й рядок переліку, плюс слот і час. */
    iterTrash: (curTask?.iteration_trash || []).map((x) => ({
      trash: x.trash, label: t('iterTag', itNum(x.id)), note: itNoteOf(x),
      deletedAt: x.deleted_at || '', expiresAt: x.expires_at || '',
    })),
    iterGone,
```

7d. In the bar click delegation, right after the `itdup` line
(`if (act === 'itdup') { createIteration(el.dataset.val); return; }`):

```js
  /* «Видалені»: розгорнути/згорнути, дропдаун лишається відкритим. */
  if (act === 'itgone') { iterGone = !iterGone; paintBar(); bar.querySelector('.it-gone-h')?.focus({ preventScroll: true }); return; }
```

7e. In `BAR_ACTIONS`, right after `histcur: …`:

```js
  /* «Видалені» (патч після 0.36.0): «Повернути» з переліку — той самий шлях, що й з тосту (ітерація стає обраною; новий номер —
     тост). Дропдаун уже закрила загальна делегація кліку. */
  itback: (slot) => {
    const x = (curTask?.iteration_trash || []).find((y) => y.trash === slot);
    restoreIteration(slot, x?.label_text || slot, currentTaskId);
  },
  /* ⌘K «Видалені ітерації»: дропдаун ітерації з розгорнутим розділом. */
  ittrash: () => {
    if (!(curTask?.iteration_trash || []).length) return;
    openDd = 'iter';
    iterGone = true;
    paintBar();
    bar.querySelector('.it-gone-h')?.focus({ preventScroll: true });
  },
```

7f. In `paletteState()` (~line 9769), next to `iterCount: …`:

```js
    iterTrashCount: (curTask?.iteration_trash || []).length,
```

- [ ] **Step 8: Styles.** In `app/styles.css`, right after the `.dd--itmenu{…}` rule:

```css
/* «Видалені» (патч після 0.36.0): розділ кошика внизу переліку ітерацій. Шеврон праворуч; розгорнутий — донизу. */
.it-gone-h .dd-t{color:var(--mid)}
.it-gone-h .dd-marks{color:var(--dim);font-size:12px;font-variant-numeric:tabular-nums}
.it-gone-h .caret{transition:transform .12s}
.it-gone-h[aria-expanded=true] .caret{transform:rotate(90deg)}
.it-gone-list{padding-left:8px}
.it-gone{display:grid;grid-template-columns:16px minmax(0,1fr) auto;gap:9px;align-items:center;
  padding:6px 6px 6px 10px;border-radius:var(--r-sm);min-height:var(--h-ctl)}
.it-gone:hover{background:var(--s3)}
.it-gone>.ico{color:var(--dim)}
.it-gone-b{display:flex;flex-direction:column;min-width:0}
.it-gone-t{font-size:13px;color:var(--mid);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.it-gone-s{font-size:12px;color:var(--dim);margin-top:1px;font-variant-numeric:tabular-nums}
.it-gone-s--soon{color:var(--open)}
.it-back{height:var(--h-sm);padding:0 10px;border:1px solid var(--line2);border-radius:var(--r-sm);background:none;
  color:var(--hi);font:inherit;font-size:12.5px;cursor:pointer;white-space:nowrap}
.it-back:hover{background:var(--s4)}
.it-back:focus-visible{outline:2px solid var(--sel);outline-offset:1px}
@media (prefers-reduced-motion:reduce){.it-gone-h .caret{transition:none}}
```

- [ ] **Step 9: Run — expect PASS:** `node --test tests/*.test.mjs` (усі, не лише нові: охоронці CSS/i18n/палітри теж у цьому
  наборі). Then `python3 -B -m unittest discover -s tests -p "test_*.py"` → `OK`. If a guard test fails, fix the cause
  (e.g. a missing EN key), do not weaken the guard.

- [ ] **Step 10: Commit**

```
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(trash-list): розділ «Видалені» в дропдауні ітерації + ⌘K" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/i18n.js app/bar-model.js app/shell-bar.js app/shell-palette.js app/app.js app/styles.css tests/shell-bar.test.mjs tests/shell-palette.test.mjs
```

---

### Task 3: Живий тест і гайд агента

**Files:**
- Modify: `tests/live/iterations-list.test.mjs` (новий тест після тесту «видалення: «Видалити» вимкнене…», ~рядок 188)
- Modify: `app/templates/agents.md` (розділ «Tasks and iterations», після блоку з `iteration-restore`, ~рядок 47)

- [ ] **Step 1: Live test** — insert after the test `"видалення: «Видалити» вимкнене, коли лишилась одна ітерація"`:

```js
test("«Видалені»: після видалення розділ з числом; «Повернути» повертає й обирає; порожній кошик — розділу нема", async (t) => {
  const { page, ids } = await boot(t, { count: 3 });
  await openList(page);
  assert.equal(await page.locator("#bar .it-gone-h").count(), 0, "розділ при порожньому кошику");
  await openRowMenu(page, "it2");
  await page.click('#bar .dd--itmenu [data-act="itdel"]');
  await page.click('#bar .it-cfm [data-act="itdelyes"]');
  await page.waitForFunction(async () => (await (await fetch("/api/task")).json()).iteration_trash.length === 1);
  if (!(await page.locator("#bar .dd--iters").count())) await openList(page);
  await page.waitForSelector("#bar .it-gone-h");
  assert.match(await page.textContent("#bar .it-gone-h"), /Видалені\s*1/);
  await page.click("#bar .it-gone-h");
  await page.waitForSelector('#bar .it-gone [data-act="itback"]');
  assert.ok(await page.locator("#bar .dd--iters").count(), "розгортання закрило дропдаун");
  assert.match(await page.textContent("#bar .it-gone-t"), /^Іт\.2/);
  assert.match(await page.textContent("#bar .it-gone-s"), /ще 7 дн\./);
  await shot(page, "10-trash.png");
  const req = page.waitForRequest((r) => r.url().endsWith("/api/iteration-restore"));
  await page.click('#bar .it-gone [data-act="itback"]');
  assert.ok((await req).headers()["x-canvas-task"], "«Повернути» з переліку без X-Canvas-Task");
  await page.waitForFunction(async () => (await (await fetch("/api/task")).json()).iterations.length === 3);
  assert.deepEqual(await ids(), ["it1", "it2", "it3"], "ітерація повернулась не на своє місце");
  await page.waitForFunction(() => /Іт\.2/.test(document.querySelector('#bar [data-dd="iter"]')?.textContent || ""));
  await openList(page);
  assert.equal(await page.locator("#bar .it-gone-h").count(), 0, "розділ лишився після повернення єдиної видаленої");
});
```

- [ ] **Step 2: Run it under the lock** (only this file):

```
until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; H=$(mktemp -d); HOME="$H" node --test --import ./tests/live/_env.mjs tests/live/iterations-list.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; exit $rc
```

Expected: усі тести файлу `pass`. Тест падає — знайди причину в коді Task 2 (не послаблюй тест) і прожени ще раз.

- [ ] **Step 3: Agent guide.** In `app/templates/agents.md`, «Tasks and iterations»:
  - Replace the bullet starting `- Deleting an iteration moves it to the task's trash for 7 days` with the text below.
  - Keep the existing two `POST` lines and the `header:` line as they are, and add the `GET /api/task` line after them.

```
- Deleting an iteration moves it to the task's trash for 7 days (`.trash/`, outside git); the answer carries the slot to
  restore it. The only iteration of a task cannot be deleted. The trash, newest first, comes with the task, and the
  designer sees it as «Видалені» at the bottom of the iteration list.
```

Line to add after the `header: X-Canvas-Task: <task-id>` line, with the same indentation:

```
      GET  http://127.0.0.1:8765/api/task → "iteration_trash": [{"trash": "<slot>", "id": "itN", "label_text": "…", "deleted_at": "…Z", "expires_at": "…Z"}]
```

Then run `python3 -B -m unittest tests.test_agents_md -v` → `OK`.

- [ ] **Step 4: Commit**

```
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(trash-list): живе проведення «Видалені»; гайд агента — iteration_trash" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/live/iterations-list.test.mjs app/templates/agents.md
```

---

## Після задач (контролер)

- Один ревʼюер на всю гілку (середній рівень).
- CHANGELOG і версія — на релізі: наступна вільна мінорна/патч-версія на момент злиття. Сесія гайда агента випускає
  0.37.0; розділ 0.36.0 не переписуємо.
- Релізний прогін, ff у живий `main`, тег, перезапуск канваса з чистим env, `push` — лише за «да» власника.
