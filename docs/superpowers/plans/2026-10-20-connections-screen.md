# Етап 3a «Підключення» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** екран «Підключення» простору — UI над наявним API модулів (картки за ролями, бічна панель налаштувань і секретів, перевірка, заміна модуля в ролі, вимкнення), реліз 0.5.0.

**Architecture:** сервер отримує одну нову річ — атомарну заміну постачальника ролі (`replace` у `module-enable`). Клієнт — два нові чисті модулі (`connections-model.js` — логіка без DOM і без `t()`; `connections-view.js` — розмітка рядками) і проводка в `app.js`: сторінка `conn` наявного оверлею `#tasks-home` плюс окремий вузол бічної панелі `#cn-drawer`. Входи: дропдаун фішки простору, ⌘K, голова «Задач».

**Tech Stack:** Python 3 stdlib (`app/serve.py`, `app/deai_modules.py`, `unittest`), ванільний ES-модульний JS (`node:test`), Playwright Chromium для живого тесту.

**Спека:** `docs/superpowers/specs/2026-10-20-connections-screen-design.md` — читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

- Репо: `<repo>`. Гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
- Додавати в індекс лише свої файли поіменно. **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий файл `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` — його не чіпати й не комітити.
- Кожен прогін тестів — через охоронця памʼяті: `G=<scratchpad>/bin/guard.py`, виклик `python3 "$G" <секунд> <МБ> <команда…>`, напр. `python3 "$G" 600 3000 npm test`. Якщо файла охоронця нема — сказати контролеру, а не запускати без нього.
- Не виставляти `DEAI_HOME` у шелі. Не чіпати порти 8765 і 4317, справжні `~/.deai`, `~/deai-published`, `~/.gitconfig`. Процеси зупиняти лише за PID, ніколи `pkill`/`killall` за шаблоном.
- Жодної мережі в тестах (Vercel і Supabase не вмикати там, де їхній `check` піде в мережу).
- Конвенції коду: коментарі українською, тексти інтерфейсу лише через `t()` (обидві мови `UK` і `EN` у `app/i18n.js`), кирилиці в літералах `app/**` поза словником бути не може (`tests/i18n-literals.test.mjs`); дані в розмітку лише через `esc()` з `app/esc.js`; іконки лише відомі `ico()` з `app/icons.js`; CSS лише токенами.
- ЛІГА-golden (`tests/legacy-golden.test.mjs`) мусить лишитись зеленим БЕЗ `UPDATE_GOLDEN=1`.
- Повний набір юнітів: `npm test`. Живі тести — лише послідовно: `node --test --test-concurrency=1 tests/live/<файл>`.

## Структура файлів

| файл | відповідальність |
|---|---|
| `app/deai_modules.py` (зміна) | `_holders`, `replace` у `write_module_state` і `preflight` |
| `app/serve.py` (зміна) | `replace` у `module_write`/`_module_post`, `replaced` у відповіді |
| `app/connections-model.js` (новий) | чиста логіка екрана: групування, рядок «Зараз», картка, причина, форма, патч, конфлікт ролей, тексти кодів |
| `app/connections-view.js` (новий) | розмітка сторінки, картки й бічної панелі; `modName`, `roleTitle` |
| `app/i18n.js` (зміна) | ключі `cn*`, `spaceConn`; правка `publishErrVercelAuth` |
| `app/styles.css` (зміна) | правила `.cn-*`, `.th-head-acts` |
| `app/bar-model.js`, `app/shell-bar.js`, `app/shell-palette.js`, `app/tasks-home.js` (зміни) | входи: крихта, пункт дропдауна, пункт ⌘K, кнопка в голові «Задач» |
| `app/app.js` (зміна) | сторінка `conn` оверлею, завантаження, дії карток, бічна панель, запис, заміна, вимкнення, оновлення після змін |
| `tests/fixtures/modules-conn/memo-publish/` (новий) | тестовий модуль ролі `publish` з локальною перевіркою |
| `tests/live/connections.test.mjs` (новий) | живий сценарій |
| `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json` | документи й версія 0.5.0 |

---

### Task 1: Сервер — атомарна заміна постачальника ролі (`replace`)

**Files:**
- Modify: `app/deai_modules.py` (`_role_conflict` ≈ рядок 726, `preflight` ≈ 740, `write_module_state` ≈ 788)
- Modify: `app/serve.py` (`module_write` ≈ 4650, `Handler._module_post` ≈ 6918)
- Test: `tests/test_modules_api.py` (новий клас `Replace(World)` після класу `Enable`)
- Modify: `README.md` (рядок таблиці `POST /api/module-enable` ≈ 153)

- [ ] **Step 1: Написати падаючі тести.** Додати в `tests/test_modules_api.py` після класу `Enable` (фікстура `alt-publish` уже є в `FIXTURES`):

```python
class Replace(World):
    """`replace: true` у `module-enable`: ролі цього модуля звільняються в ТОМУ САМОМУ записі `space.json`."""

    def test_replace_takes_the_role_from_the_implicit_static_publish_in_one_write(self):
        self.modules(extra=('alt-publish',))
        writes = []
        real = spaces._write_public

        def spy(path, data):
            writes.append((path, json.loads(json.dumps(data))))
            return real(path, data)

        with mock.patch.object(spaces, '_write_public', spy):
            st, body = self.post('/api/module-enable', {'id': 'alt-publish', 'replace': True})
        self.assertEqual((st, body['ok'], body['check']), (200, True, {'ok': True}), body)
        self.assertEqual(body['replaced'], ['static-publish'])
        mods = self.sj()['modules']
        self.assertEqual(mods['static-publish'], {'enabled': False})
        self.assertEqual(mods['alt-publish'], {'enabled': True})
        sj_writes = [w for w in writes if w[0].endswith('space.json')]
        self.assertEqual(len(sj_writes), 1, 'обидві зміни — одним записом файла')
        self.assertEqual(sj_writes[0][1]['modules']['static-publish']['enabled'], False)
        self.assertEqual(sj_writes[0][1]['modules']['alt-publish']['enabled'], True)
        listing = self.listing()
        self.assertEqual((listing['static-publish']['enabled'], listing['alt-publish']['enabled']), (False, True))

    def test_replace_keeps_the_settings_of_the_replaced_module(self):
        self.modules(extra=('alt-publish',))
        st, body = self.post('/api/module-settings', {'id': 'static-publish', 'settings': {'folder': '{home}/pv'}})
        self.assertEqual(st, 200, body)
        st, body = self.post('/api/module-enable', {'id': 'alt-publish', 'replace': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.sj()['modules']['static-publish'], {'enabled': False, 'settings': {'folder': '{home}/pv'}})

    def test_replace_takes_the_role_from_an_explicit_holder_too(self):
        self.modules(extra=('alt-publish',))
        st, _ = self.post('/api/module-enable', {'space': 'on', 'id': 'alt-publish'})
        self.assertEqual(st, 200)
        st, body = self.post('/api/module-enable', {'space': 'on', 'id': 'static-publish', 'replace': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['replaced'], ['alt-publish'])
        mods = self.sj(self.on)['modules']
        self.assertEqual((mods['alt-publish']['enabled'], mods['static-publish']['enabled']), (False, True))

    def test_replace_without_a_conflict_answers_an_empty_list(self):
        self.css()
        st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '{space}/ds.css'},
                                                    'replace': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['replaced'], [])

    def test_no_replace_key_in_the_answer_without_replace(self):
        self.css()
        st, body = self.post('/api/module-enable', {'id': 'css-tokens', 'settings': {'file': '{space}/ds.css'}})
        self.assertEqual(st, 200, body)
        self.assertNotIn('replaced', body)

    def test_without_replace_the_role_is_still_taken(self):
        self.modules(extra=('alt-publish',))
        before = self.sj_bytes()
        for payload in ({'id': 'alt-publish'}, {'id': 'alt-publish', 'replace': False}):
            with self.subTest(payload=payload):
                st, body = self.post('/api/module-enable', payload)
                self.refused(st, body, 409, 'role-taken')
        self.assertEqual(self.sj_bytes(), before)

    def test_replace_must_be_a_boolean_and_nothing_is_written(self):
        self.modules(extra=('alt-publish',))
        before = self.sj_bytes()
        for bad in ('yes', 1, None, [], {}):
            with self.subTest(replace=bad):
                st, body = self.post('/api/module-enable', {'id': 'alt-publish', 'replace': bad,
                                                            'secrets': {'token': SECRET}})
                self.refused(st, body, 400, 'bad-settings')
        self.assertEqual(self.sj_bytes(), before)
        self.assertFalse(os.path.exists(self.secrets_path), 'відмова replace — ДО запису секрету')
        self.assert_never_seen(SECRET)

    def test_replace_is_ignored_by_the_other_routes(self):
        self.modules(extra=('alt-publish',))
        st, body = self.post('/api/module-settings', {'id': 'alt-publish', 'settings': {'note': 'x'}, 'replace': True})
        self.assertEqual(st, 200, body)
        self.assertNotIn('replaced', body)
        self.assertTrue(self.sj()['modules'].get('static-publish', {}).get('enabled', True) is not False,
                        'settings не вмикає і не замінює')

    def test_preflight_with_replace_does_not_refuse(self):
        self.modules(extra=('alt-publish',))
        dm.preflight(self.off, 'alt-publish', enabling=True, replace=True)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.preflight(self.off, 'alt-publish', enabling=True)
        self.assertEqual(cm.exception.code, 'role-taken')

    def test_write_module_state_reports_what_it_replaced(self):
        self.modules(extra=('alt-publish',))
        st = dm.write_module_state(self.off, 'alt-publish', enabled=True, replace=True)
        self.assertEqual(st['replaced'], ['static-publish'])
        st = dm.write_module_state(self.off, 'alt-publish', enabled=True)
        self.assertNotIn('replaced', st)
```

Пояснення до `test_replace_is_ignored_by_the_other_routes`: `module-settings` з `replace` поводиться так само, як без нього (ключ ігнорується, `replaced` у відповіді нема). Перевірити тип `None`: `{'replace': None}` — це «передано не bool» → 400 (явно переданий `null` — помилка клієнта).

- [ ] **Step 2: Запустити — мусять впасти.**

```bash
cd <repo> && python3 "$G" 300 2000 python3 -m unittest tests.test_modules_api.Replace -v
```
Очікувано: FAIL/ERROR (`replaced` нема, `preflight() got an unexpected keyword argument 'replace'`, 409 замість 200).

Якщо `python3 -m unittest tests.test_modules_api…` не знаходить модуль (пакета `tests` нема) — запускати з `-s`: `python3 -m unittest discover -s tests -p test_modules_api.py -k Replace -v`.

- [ ] **Step 3: Реалізувати в `app/deai_modules.py`.** Замінити `_role_conflict` на пару функцій:

```python
def _holders(m, cat, space, explicit):
    """Id ІНШИХ модулів `cat`, що зараз тримають хоч одну роль `m` у `explicit` (неявно ввімкнений `static-publish`
    теж), за абеткою. Не завантажені модулі ролей не тримають."""
    mine = set(m.roles)
    out = []
    for oid in sorted(cat):
        other = cat[oid]
        if oid == m.id or other.status != 'ok' or not (mine & set(other.roles)):
            continue
        if _enabled_in(other, space, explicit)[0]:
            out.append(oid)
    return out


def _role_conflict(m, cat, space, explicit):
    """Текст `role-taken` для модуля `m`, якщо хтось інший із `cat` уже тримає його роль у `explicit` (неявно
    ввімкнений `static-publish` теж); інакше `None`. Не завантажені модулі ролей не тримають."""
    for oid in _holders(m, cat, space, explicit):
        return f'{sorted(set(m.roles) & set(cat[oid].roles))[0]} is already provided by {oid}'
    return None
```

`preflight` — новий параметр:

```python
def preflight(space, module_id, enabling=False, replace=False):
```
…і в тілі `if enabling and not replace:` замість `if enabling:` (доповнити докстрінг: «з `replace` роль не перевіряється — її звільнить `write_module_state` під локом»).

`write_module_state` — новий параметр `replace=False`. Сигнатура: `def write_module_state(space, module_id, enabled=None, settings=None, replace=False):`. Доповнити докстрінг абзацом:

```
    `replace=True` (лише разом з `enabled=True`): замість `role-taken` — під тим самим локом і в ТОМУ САМОМУ записі
    файла кожен інший модуль, що тримає роль цього (`_holders`, неявний `static-publish` теж), отримує `enabled: false`
    (його налаштування лишаються). Тоді в поверненому стані є ключ `replaced` — перелік таких id (може бути порожнім).
```

Під `with spaces.WRITE_LOCK:` замінити блок перевірки ролі:

```python
        replaced = []
        if enabled is True:
            if replace:
                replaced = _holders(m, cat, space, explicit)
            else:
                why = _role_conflict(m, cat, space, explicit)
                if why:
                    raise ModuleError('role-taken', message=why)
```

…і ПЕРЕД `mods[module_id] = entry` додати:

```python
        for oid in replaced:
            prev = mods.get(oid)
            off = dict(prev) if isinstance(prev, dict) else {}
            off['enabled'] = False
            mods[oid] = off
```

…а повернення в кінці:

```python
        state = _entry_state(m, space, _normalize(mods))
        if replace and enabled is True:
            state['replaced'] = replaced
        return state
```

- [ ] **Step 4: Реалізувати в `app/serve.py`.** `module_write` — новий параметр і повернення пари:

```python
def module_write(space, mid, action, settings, secrets, replace=None):
```
Доповнити докстрінг: «`replace` — лише для `enable`: `None` (ключа в тілі не було) чи `bool`; інше — `bad-settings` ДО будь-якого запису. Повертає `(вердикт | None, replaced | None)`: `replaced` — список id, звільнених заміною, лише коли `replace is True`.»

Тіло:

```python
    if action == 'disable':
        deai_modules.write_module_state(space, mid, enabled=False)
        return None, None
    deai_modules.validate_settings(mid, settings)
    swap = action == 'enable' and replace is True
    if action == 'enable' and replace is not None and not isinstance(replace, bool):
        raise deai_modules.ModuleError('bad-settings', message='replace: expected a boolean')
    deai_modules.preflight(space, mid, enabling=(action == 'enable'), replace=swap)
    if secrets is not None:
        deai_modules.write_secrets(space['id'], mid, secrets)
    state = deai_modules.write_module_state(space, mid, enabled=True if action == 'enable' else None,
                                            settings=settings, replace=swap)
    return module_check_verdict(space, mid), (state.get('replaced') if swap else None)
```

Перевірити, як `ModuleError` кидається в цьому файлі (може бути `deai_modules.ModuleError('bad-settings', message=…)` — звірити з наявними викликами в `serve.py`; конструктор: `ModuleError(code, message=…)`).

`_module_post` — розрізнити «ключа нема» і «передано»:

```python
        mid = payload.get('id')
        replaced = None
        if action == 'check':
            verdict = module_check_verdict(sp, mid)
        else:
            verdict, replaced = module_write(sp, mid, action, payload.get('settings'), payload.get('secrets'),
                                             payload['replace'] if 'replace' in payload else None)
        out = {'ok': True, 'module': module_entry(sp, mid)}
        if action != 'disable':
            out['check'] = verdict
        if replaced is not None:
            out['replaced'] = replaced
        self._send_json(out)
```

⚠️ `payload['replace']` зі значенням `None` (у JSON `null`) мусить дати 400: тому `'replace' in payload` і передаємо значення як є, а в `module_write` перевірка `replace is not None and not isinstance(replace, bool)` для `None` НЕ спрацює. Щоб `null` теж відмовляв, передати маркер: у `_module_post` — `payload.get('replace', _NO_REPLACE)` з модульною константою `_NO_REPLACE = object()`, а в `module_write` — `replace=_NO_REPLACE` за замовчуванням і перевірка `if action == 'enable' and replace is not _NO_REPLACE and not isinstance(replace, bool)`. `swap = action == 'enable' and replace is True`. Тест `test_replace_must_be_a_boolean_and_nothing_is_written` містить `None` — він це стереже.

Оновити докстрінг `_module_post`: тіло `{space?, id, settings?, secrets?, replace?}`, відповідь `{ok, module[, check][, replaced]}`.

- [ ] **Step 5: Тести зелені.**

```bash
python3 "$G" 600 3000 python3 -m unittest discover -s tests -p 'test_modules_api.py' -v 2>&1 | tail -15
python3 "$G" 900 3000 python3 -m unittest discover -s tests -p 'test_comments_role.py' 2>&1 | tail -5
```
Очікувано: усе OK (і старі тести `role-taken`).

- [ ] **Step 6: Мутаційний доказ.** Під `python3 -B` по черзі (кожну мутацію відкотити побайтно, `git diff --stat` порожній після):
  1. у `write_module_state` прибрати цикл `for oid in replaced:` → мусить впасти `test_replace_takes_the_role_from_the_implicit_static_publish_in_one_write`;
  2. у `module_write` прибрати перевірку типу → мусить впасти `test_replace_must_be_a_boolean_and_nothing_is_written`;
  3. у `preflight` повернути `if enabling:` → мусять впасти тести з 200 на `replace`.

- [ ] **Step 7: README.** У таблиці API (рядок `POST /api/module-enable`) дописати `replace?`: `` `{space?, id, settings?, secrets?, replace?}` | enable and configure; answers `{ok, module, check[, replaced]}` — … `replace: true` takes the module's roles from their current holders in the same write (their settings stay) and lists them in `replaced` `` (зберегти решту тексту рядка).

- [ ] **Step 8: Commit.**

```bash
git add app/deai_modules.py app/serve.py tests/test_modules_api.py README.md
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(modules): replace у module-enable — атомарна заміна постачальника ролі

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Чиста модель екрана (`app/connections-model.js`)

**Files:**
- Create: `app/connections-model.js`
- Test: `tests/connections-model.test.mjs`

- [ ] **Step 1: Написати падаючі тести** `tests/connections-model.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";

import {
  ROLE_ORDER, builtinText, cardView, disableConsequences, formFields, formPatch, groupModules, initialForm,
  isDirty, missingRequired, providerLine, refusalView, roleHolders, roleIcon, roleKeys, verdictText, whyOf,
  writePayload,
} from "../app/connections-model.js";

const M = (id, o = {}) => ({ id, name: id, roles: ["publish"], enabled: false, implicit: false, status: "unchecked",
  settings: [], ...o });

test("ролі: порядок секцій, ключі й іконки; чужа роль і __proto__ не мають ключів", () => {
  assert.deepEqual(ROLE_ORDER, ["publish", "comments", "tokens"]);
  assert.equal(roleKeys("publish").title, "cnRolePublish");
  assert.equal(roleKeys("comments").none, "cnNoneComments");
  assert.equal(roleKeys("vcs"), null);
  assert.equal(roleKeys("__proto__"), null);
  assert.equal(roleKeys("toString"), null);
  assert.equal(roleIcon("publish"), "up");
  assert.equal(roleIcon("comments"), "comment");
  assert.equal(roleIcon("tokens"), "sliders");
  assert.equal(roleIcon("vcs"), "dots");
  assert.equal(roleIcon(undefined), "dots");
  assert.equal(roleIcon("constructor"), "dots");
});

test("вбудовані тексти: чотири модулі, решта — null", () => {
  for (const id of ["static-publish", "vercel-publish", "supabase-comments", "css-tokens"]) {
    const b = builtinText(id);
    assert.ok(b && b.name && b.desc && b.fields, id);
  }
  assert.equal(builtinText("static-publish").fields.folder, "cnFieldStaticFolder");
  assert.equal(builtinText("memo-publish"), null);
  assert.equal(builtinText("__proto__"), null);
});

test("групування: відомі ролі за порядком, далі інші за абеткою, без ролі — останні; missing окремо", () => {
  const list = [
    M("t", { roles: ["tokens"] }), M("z", { roles: ["vcs"] }), M("a", { roles: ["alpha"] }),
    M("p2"), M("p1"), M("n", { roles: [] }), M("c", { roles: ["comments", "publish"] }),
    { id: "gone", name: "gone", roles: [], enabled: true, status: "missing", settings: [] },
    null, { name: "без id" },
  ];
  const { sections, missing } = groupModules(list);
  assert.deepEqual(sections.map((s) => s.role), ["publish", "comments", "tokens", "alpha", "vcs", ""]);
  assert.deepEqual(sections[0].modules.map((e) => e.id), ["p2", "p1"], "порядок усередині — як у списку сервера");
  assert.deepEqual(sections[1].modules.map((e) => e.id), ["c"], "кілька ролей — у секції першої");
  assert.deepEqual(missing.map((e) => e.id), ["gone"]);
  assert.deepEqual(groupModules(null), { sections: [], missing: [] });
});

test("рядок «Зараз»: модуль, legacy, нікого з наслідком, невідома роль, нема capabilities", () => {
  const list = [M("vercel-publish", { name: "Vercel" })];
  assert.deepEqual(providerLine("publish", { publish: "vercel-publish" }, list),
    { kind: "module", id: "vercel-publish", entry: list[0] });
  assert.deepEqual(providerLine("publish", { publish: "ghost" }, list), { kind: "module", id: "ghost", entry: null });
  assert.deepEqual(providerLine("comments", { comments: "legacy" }, list), { kind: "legacy" });
  assert.deepEqual(providerLine("tokens", { tokens: null }, list), { kind: "none", noneKey: "cnNoneTokens" });
  assert.equal(providerLine("vcs", { publish: null }, list), null, "роль, якої capabilities не знає");
  assert.equal(providerLine("error", { error: "x" }, list), null);
  assert.equal(providerLine("publish", null, list), null);
  assert.equal(providerLine("__proto__", {}, list), null);
});

test("картка: бейдж і дії для кожного стану", () => {
  assert.deepEqual(cardView(M("a", { status: "missing", enabled: true })),
    { badge: "missing", actions: ["disable"], why: true, implicit: false });
  assert.deepEqual(cardView(M("a", { enabled: false, status: "error" })),
    { badge: "off", actions: ["enable"], why: false, implicit: false });
  assert.deepEqual(cardView(M("a", { enabled: true, status: "ok" })),
    { badge: "ok", actions: ["configure", "check", "disable"], why: false, implicit: false });
  assert.deepEqual(cardView(M("a", { enabled: true, status: "unchecked", implicit: true })),
    { badge: "unchecked", actions: ["configure", "check", "disable"], why: false, implicit: true });
  assert.deepEqual(cardView(M("a", { enabled: true, status: "error" })),
    { badge: "error", actions: ["configure", "check", "disable"], why: true, implicit: false });
});

test("вердикт: відомий код, невідомий код, вільний текст, ok, обрізання до 300", () => {
  assert.deepEqual(verdictText({ ok: true, detail: "2 tokens" }), { key: "cnCheckOk", detail: "2 tokens" });
  assert.deepEqual(verdictText({ ok: false, error: "no-token", detail: "Токен не задано" }),
    { key: "cnErrNoToken", detail: "Токен не задано" });
  assert.deepEqual(verdictText({ ok: false, error: "file: not found" }), { key: "cnErrGeneric", detail: "file: not found" });
  assert.deepEqual(verdictText({ ok: false, error: "weird", detail: "why" }), { key: "cnErrGeneric", detail: "weird — why" });
  assert.deepEqual(verdictText(null), { key: "cnErrGeneric", detail: "" });
  const long = verdictText({ ok: false, error: "network", detail: "x".repeat(500) });
  assert.equal(long.key, "cnErrNetwork");
  assert.equal(long.detail.length, 300);
  assert.ok(long.detail.endsWith("…"));
  for (const code of ["bad-settings", "module-error", "check-timeout", "secrets-unreadable", "bad-manifest",
    "bad-folder", "not-writable", "no-token", "vercel-auth", "vercel-error", "bad-key", "no-schema",
    "supabase-error", "network"]) {
    assert.notEqual(verdictText({ ok: false, error: code }).key, "cnErrGeneric", code);
  }
});

test("причина: missing; error з деталлю лише свого last_check; не-error — null", () => {
  assert.deepEqual(whyOf(M("a", { status: "missing" })), { key: "cnWhyMissing", detail: "" });
  assert.deepEqual(whyOf(M("a", { status: "error", error: "bad-key", last_check: { ok: false, error: "bad-key", detail: "401" } })),
    { key: "cnErrBadKey", detail: "401" });
  assert.deepEqual(whyOf(M("a", { status: "error", error: "secrets-unreadable", last_check: { ok: true, detail: "2 tokens" } })),
    { key: "cnErrSecretsUnreadable", detail: "" }, "стара успішна перевірка не дає деталь чужій причині");
  assert.equal(whyOf(M("a", { status: "ok" })), null);
  assert.equal(whyOf(null), null);
});

test("відмова HTTP: код → ключ, timeout → formTimeout, невідома — загальна з текстом", () => {
  assert.deepEqual(refusalView({ code: "role-taken", message: "publish is already provided by x" }),
    { key: "cnRefRoleTaken", detail: "publish is already provided by x" });
  assert.deepEqual(refusalView({ code: "timeout", message: "timeout" }), { key: "formTimeout", detail: "" });
  assert.deepEqual(refusalView({ message: "boom" }), { key: "cnRefGeneric", detail: "boom" });
  for (const code of ["bad-settings", "unknown-module", "unknown-space", "space-json-unreadable", "spaces-off", "unwritable"]) {
    assert.notEqual(refusalView({ code }).key, "cnRefGeneric", code);
  }
});

test("хто тримає ролі: увімкнені (і неявний) з перетином ролей, крім самого себе й missing", () => {
  const me = M("vercel-publish");
  const list = [me, M("static-publish", { enabled: true, implicit: true }), M("off-pub", { enabled: false }),
    M("cm", { roles: ["comments"], enabled: true }), { id: "gone", roles: ["publish"], enabled: true, status: "missing" }];
  assert.deepEqual(roleHolders(me, list).map((e) => e.id), ["static-publish"]);
  assert.deepEqual(roleHolders(M("x", { roles: [] }), list), []);
  assert.deepEqual(roleHolders(me, null), []);
});

test("наслідки вимкнення: legacy для ЛІГА publish/comments, «нікого» інакше, лише для ролей, які він тримає", () => {
  const e = M("vercel-publish");
  assert.deepEqual(disableConsequences(e, { integrations: false, capabilities: { publish: "vercel-publish" } }),
    [{ role: "publish", kind: "none", noneKey: "cnNonePublish" }]);
  assert.deepEqual(disableConsequences(e, { integrations: true, capabilities: { publish: "vercel-publish" } }),
    [{ role: "publish", kind: "legacy" }]);
  assert.deepEqual(disableConsequences(e, { integrations: false, capabilities: { publish: "static-publish" } }), []);
  const tok = M("css-tokens", { roles: ["tokens"] });
  assert.deepEqual(disableConsequences(tok, { integrations: true, capabilities: { tokens: "css-tokens" } }),
    [{ role: "tokens", kind: "none", noneKey: "cnNoneTokens" }], "токенів ЛІГА не має — legacy тут нема");
  assert.deepEqual(disableConsequences(e, null), []);
});

const SETTINGS = [
  { key: "folder", type: "path", label: "Тека", required: true, value: "{home}/deai-published/{space_id}" },
  { key: "team", type: "text", label: "Команда", required: false },
  { key: "on", type: "bool", label: "Прапорець", required: false, value: true },
  { key: "mode", type: "select", label: "Режим", required: false, value: "a",
    options: [{ value: "a", label: "A" }, { value: "b" }, { label: "без значення" }] },
  { key: "token", type: "secret", label: "Токен", required: true, set: false },
  { key: "password", type: "secret", label: "Пароль", required: false, set: true },
  { key: "odd", type: "weird", label: "", required: false, value: 5 },
];

test("поля форми з settings[]", () => {
  const f = formFields({ settings: [...SETTINGS, null, { type: "text" }] });
  assert.deepEqual(f.map((x) => [x.key, x.type]), [["folder", "path"], ["team", "text"], ["on", "bool"],
    ["mode", "select"], ["token", "secret"], ["password", "secret"], ["odd", "text"]]);
  assert.equal(f[4].set, false);
  assert.equal(f[5].set, true);
  assert.equal(f[4].value, undefined, "секрет не несе значення");
  assert.deepEqual(f[3].options, [{ value: "a", label: "A" }, { value: "b", label: "b" }]);
  assert.equal(f[6].label, "odd", "порожній підпис — ключ");
  assert.equal(formFields({ settings: [{ key: "k", type: "secret", label: "K", set: null }] })[0].set, null);
});

test("початкова форма й патч: лише змінене, обрізання пробілів, очищене необовʼязкове — null", () => {
  const f = formFields({ settings: SETTINGS });
  const init = initialForm(f);
  assert.deepEqual({ ...init.values }, { folder: "{home}/deai-published/{space_id}", team: "", on: true, mode: "a", odd: "5" });
  assert.deepEqual(init.erase, []);
  const same = formPatch(f, init, { values: { ...init.values }, secrets: { token: "", password: "  " }, erase: [] });
  assert.deepEqual({ ...same.settings }, {});
  assert.deepEqual({ ...same.secrets }, {});
  assert.equal(isDirty(same), false);
  const p = formPatch(f, init, {
    values: { ...init.values, team: "  acme ", on: false, mode: "b", odd: "" },
    secrets: { token: " tk-1 \n", password: "" }, erase: ["password"],
  });
  assert.deepEqual({ ...p.settings }, { team: "acme", on: false, mode: "b", odd: null });
  assert.deepEqual({ ...p.secrets }, { token: "tk-1", password: null });
  assert.equal(isDirty(p), true);
});

test("патч: стерти можна лише заданий необовʼязковий; введене перемагає стирання", () => {
  const f = formFields({ settings: SETTINGS });
  const init = initialForm(f);
  const p = formPatch(f, init, { values: { ...init.values }, secrets: { password: "new" }, erase: ["password", "token"] });
  assert.deepEqual({ ...p.secrets }, { password: "new" });
});

test("патч: ключ __proto__ — звичайне власне поле, не прототип", () => {
  const f = formFields({ settings: [{ key: "__proto__", type: "text", label: "x", value: "a" }] });
  const init = initialForm(f);
  const p = formPatch(f, init, { values: Object.fromEntries([["__proto__", "b"]]), secrets: {}, erase: [] });
  assert.equal(Object.getPrototypeOf(p.settings), Object.prototype);
  assert.deepEqual(Object.keys(p.settings), ["__proto__"]);
  assert.equal(JSON.parse(JSON.stringify(p.settings)).__proto__, "b");
});

test("обовʼязкові: порожній шлях, незаданий і невведений секрет; заданий секрет і прапорець — ні", () => {
  const f = formFields({ settings: SETTINGS });
  const init = initialForm(f);
  assert.deepEqual(missingRequired(f, { values: { ...init.values, folder: "  " }, secrets: {}, erase: [] }), ["folder", "token"]);
  assert.deepEqual(missingRequired(f, { values: { ...init.values }, secrets: { token: "x" }, erase: [] }), []);
  const unknown = formFields({ settings: [{ key: "k", type: "secret", label: "K", required: true, set: null }] });
  assert.deepEqual(missingRequired(unknown, { values: {}, secrets: {}, erase: [] }), ["k"], "невідомо — теж треба ввести");
});

test("тіло запиту: space і id завжди, порожні патчі не йдуть, replace лише true", () => {
  assert.deepEqual(writePayload("s", "m", { settings: {}, secrets: {} }), { space: "s", id: "m" });
  assert.deepEqual(writePayload("s", "m", { settings: { a: 1 }, secrets: { b: null } }, true),
    { space: "s", id: "m", settings: { a: 1 }, secrets: { b: null }, replace: true });
  assert.deepEqual(writePayload("s", "m", null, "yes"), { space: "s", id: "m" });
});
```

- [ ] **Step 2: Запустити — мусить впасти** (модуля нема):

```bash
python3 "$G" 120 1500 node --test tests/connections-model.test.mjs
```

- [ ] **Step 3: Реалізувати** `app/connections-model.js`:

```js
/**
 * Модель екрана «Підключення» (Deai 0.5.0, етап 3a; спека
 * `docs/superpowers/specs/2026-10-20-connections-screen-design.md`). Чисті функції: ні DOM, ні fetch, ні `t()` —
 * лише ІМЕНА ключів словника (як `bar-model.js`), тож модуль тестується в node без браузера й без мови.
 *
 * Вхід — записи `GET /api/modules` (`{id, name, roles, enabled, implicit, status, settings[], last_check?, error?}`)
 * і `capabilities` простору з `/api/spaces` (`{publish, comments, tokens[, error]}`).
 *
 * ⛔ Ключі з даних (роль, id модуля, ключ налаштування) НІКОЛИ не індексують звичайний обʼєкт без перевірки власної
 * властивості: роль `__proto__` чи `constructor` інакше дістала б щось із прототипу. Тому `has()` скрізь, а мапи
 * значень будуються `Object.fromEntries` (власна властивість `__proto__` — просто поле, а не прототип).
 */

const has = (o, k) => o != null && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);
const get = (o, k) => (has(o, k) ? o[k] : undefined);

/** Ролі зі своїми текстами — у порядку секцій. Інші ролі йдуть далі за абеткою, модулі без ролі — останніми. */
export const ROLE_ORDER = ["publish", "comments", "tokens"];

const ROLE_KEYS = {
  publish: { title: "cnRolePublish", lead: "cnRolePublishLead", none: "cnNonePublish" },
  comments: { title: "cnRoleComments", lead: "cnRoleCommentsLead", none: "cnNoneComments" },
  tokens: { title: "cnRoleTokens", lead: "cnRoleTokensLead", none: "cnNoneTokens" },
};
/** Ключі словника ролі (`title`, `lead`, `none`) або `null` для ролі без своїх текстів. */
export const roleKeys = (role) => get(ROLE_KEYS, role) ?? null;

const ROLE_ICONS = { publish: "up", comments: "comment", tokens: "sliders" };
/** Іконка ролі (імʼя з `icons.js`); невідома роль — `dots`. */
export const roleIcon = (role) => get(ROLE_ICONS, role) ?? "dots";

/* Вбудовані модулі: назва, опис і підписи полів — зі словника (обидві мови). Маніфести не змінюються: їхні `name` і
   `label` — мова автора модуля, і для модулів поза цією таблицею екран показує саме їх. */
const BUILTIN_TEXT = {
  "static-publish": { name: "cnModStaticName", desc: "cnModStaticDesc",
    fields: { folder: "cnFieldStaticFolder", password: "cnFieldPreviewPassword" } },
  "vercel-publish": { name: "cnModVercelName", desc: "cnModVercelDesc",
    fields: { token: "cnFieldVercelToken", team: "cnFieldVercelTeam", password: "cnFieldPreviewPassword" } },
  "supabase-comments": { name: "cnModSupabaseName", desc: "cnModSupabaseDesc",
    fields: { url: "cnFieldSupabaseUrl", key: "cnFieldSupabaseKey" } },
  "css-tokens": { name: "cnModCssName", desc: "cnModCssDesc", fields: { file: "cnFieldCssFile" } },
};
/** Ключі словника вбудованого модуля (`name`, `desc`, `fields{ключ: ключ словника}`) або `null`. */
export const builtinText = (id) => get(BUILTIN_TEXT, id) ?? null;

/**
 * Секції сторінки: `{sections: [{role, modules}], missing}`. Модуль стоїть у секції ПЕРШОЇ ролі (кілька ролей
 * перелічує картка); `status: missing` — окремо. Порядок усередині секції — як у списку сервера (за абеткою id).
 */
export function groupModules(list) {
  const byRole = new Map();
  const missing = [];
  for (const e of Array.isArray(list) ? list : []) {
    if (!e || typeof e !== "object" || typeof e.id !== "string") continue;
    if (e.status === "missing") { missing.push(e); continue; }
    const first = Array.isArray(e.roles) && typeof e.roles[0] === "string" ? e.roles[0] : "";
    if (!byRole.has(first)) byRole.set(first, []);
    byRole.get(first).push(e);
  }
  const named = [...byRole.keys()].filter((r) => r && !ROLE_ORDER.includes(r)).sort();
  const order = [...ROLE_ORDER.filter((r) => byRole.has(r)), ...named, ...(byRole.has("") ? [""] : [])];
  return { sections: order.map((role) => ({ role, modules: byRole.get(role) })), missing };
}

/**
 * Рядок «Зараз» ролі з `capabilities` простору: `{kind: 'module', id, entry|null}`, `{kind: 'legacy'}`,
 * `{kind: 'none', noneKey}`; `null` — роль, якої `capabilities` не знає (нема що казати).
 */
export function providerLine(role, caps, list) {
  if (!caps || typeof caps !== "object" || role === "error" || !has(caps, role)) return null;
  const v = caps[role];
  if (v === "legacy") return { kind: "legacy" };
  if (typeof v !== "string" || !v) return { kind: "none", noneKey: roleKeys(role)?.none ?? null };
  const entry = (Array.isArray(list) ? list : []).find((x) => x && x.id === v) ?? null;
  return { kind: "module", id: v, entry };
}

/** Картка: бейдж (`missing|off|ok|unchecked|error`), дії (`enable|configure|check|disable`), чи показувати причину. */
export function cardView(e) {
  if (e?.status === "missing") return { badge: "missing", actions: ["disable"], why: true, implicit: false };
  if (!e?.enabled) return { badge: "off", actions: ["enable"], why: false, implicit: false };
  const badge = e.status === "ok" ? "ok" : e.status === "error" ? "error" : "unchecked";
  return { badge, actions: ["configure", "check", "disable"], why: badge === "error", implicit: e.implicit === true };
}

/** Найдовша деталь у розмітці: текст модуля чи сервера може бути будь-якої довжини. */
export const DETAIL_MAX = 300;
const clip = (s) => (typeof s === "string" && s ? (s.length > DETAIL_MAX ? `${s.slice(0, DETAIL_MAX - 1)}…` : s) : "");

const CHECK_KEYS = new Map([
  ["bad-settings", "cnErrBadSettings"], ["module-error", "cnErrModuleError"], ["check-timeout", "cnErrTimeout"],
  ["secrets-unreadable", "cnErrSecretsUnreadable"], ["bad-manifest", "cnErrBadManifest"],
  ["bad-folder", "cnErrBadFolder"], ["not-writable", "cnErrNotWritable"],
  ["no-token", "cnErrNoToken"], ["vercel-auth", "cnErrVercelAuth"], ["vercel-error", "cnErrVercelError"],
  ["bad-key", "cnErrBadKey"], ["no-schema", "cnErrNoSchema"], ["supabase-error", "cnErrSupabaseError"],
  ["network", "cnErrNetwork"],
]);

/**
 * Вердикт перевірки (`{ok, error?, detail?}`) → `{key, detail}`. Невідомий код і вільний текст модуля
 * (`css-tokens`: «file: not found») — загальний текст, а сам текст іде деталлю: інакше людина не дізналась би причини.
 */
export function verdictText(v) {
  if (!v || typeof v !== "object") return { key: "cnErrGeneric", detail: "" };
  if (v.ok === true) return { key: "cnCheckOk", detail: clip(v.detail) };
  const code = typeof v.error === "string" ? v.error : "";
  const key = CHECK_KEYS.get(code);
  if (key) return { key, detail: clip(v.detail) };
  const detail = [code, typeof v.detail === "string" ? v.detail : ""].filter(Boolean).join(" — ");
  return { key: "cnErrGeneric", detail: clip(detail) };
}

/**
 * Причина на картці: `missing` — свій текст; `error` — текст коду і деталь ЛИШЕ з того `last_check`, що й дав цю
 * помилку (стара успішна перевірка не пояснює `secrets-unreadable`); інакше `null`.
 */
export function whyOf(e) {
  if (!e) return null;
  if (e.status === "missing") return { key: "cnWhyMissing", detail: "" };
  if (e.status !== "error") return null;
  const lc = e.last_check;
  const detail = lc && lc.ok === false && lc.error === e.error ? lc.detail : undefined;
  return verdictText({ ok: false, error: e.error, detail });
}

const REFUSAL_KEYS = new Map([
  ["role-taken", "cnRefRoleTaken"], ["bad-settings", "cnRefBadSettings"], ["unknown-module", "cnRefUnknownModule"],
  ["unknown-space", "cnRefUnknownSpace"], ["space-json-unreadable", "cnRefSpaceJson"], ["spaces-off", "cnRefSpacesOff"],
  ["unwritable", "cnRefUnwritable"],
]);

/** Відмова HTTP (`api()` кидає `Error` з `code`): `{key, detail}`; `timeout` (`formApi`) — наявний `formTimeout`. */
export function refusalView(err) {
  const code = typeof err?.code === "string" ? err.code : "";
  if (code === "timeout") return { key: "formTimeout", detail: "" };
  return { key: REFUSAL_KEYS.get(code) ?? "cnRefGeneric", detail: clip(typeof err?.message === "string" ? err.message : "") };
}

/** Хто, КРІМ `e`, зараз тримає хоч одну з його ролей: увімкнені (зокрема неявно) і не `missing`. */
export function roleHolders(e, list) {
  const mine = new Set(Array.isArray(e?.roles) ? e.roles : []);
  if (!mine.size) return [];
  return (Array.isArray(list) ? list : []).filter((o) => o && o.id !== e.id && o.enabled === true
    && o.status !== "missing" && Array.isArray(o.roles) && o.roles.some((r) => mine.has(r)));
}

/**
 * Що станеться з ролями, які `e` зараз ВИКОНУЄ (`capabilities[role] === e.id`), якщо його вимкнути:
 * `[{role, kind: 'legacy'}]` — простір з інтеграціями (ЛІГА) повернеться до вбудованої публікації чи коментарів;
 * `[{role, kind: 'none', noneKey}]` — роль лишиться без модуля.
 */
export function disableConsequences(e, space) {
  const caps = space?.capabilities;
  if (!e || !caps || typeof caps !== "object") return [];
  const out = [];
  for (const role of Array.isArray(e.roles) ? e.roles : []) {
    if (role === "error" || !has(caps, role) || caps[role] !== e.id) continue;
    if (space.integrations === true && (role === "publish" || role === "comments")) out.push({ role, kind: "legacy" });
    else out.push({ role, kind: "none", noneKey: roleKeys(role)?.none ?? null });
  }
  return out;
}

const TYPES = new Set(["text", "path", "bool", "select", "secret"]);

/** Поля форми з `settings[]` запису. Невідомий тип — `text`; секрет несе лише `set` (`true|false|null`). */
export function formFields(e) {
  const out = [];
  for (const s of Array.isArray(e?.settings) ? e.settings : []) {
    if (!s || typeof s.key !== "string" || !s.key) continue;
    const type = TYPES.has(s.type) ? s.type : "text";
    const f = { key: s.key, type, label: typeof s.label === "string" && s.label ? s.label : s.key, required: s.required === true };
    if (type === "secret") f.set = s.set === true ? true : (s.set === false ? false : null);
    else f.value = s.value;
    if (type === "select") {
      f.options = (Array.isArray(s.options) ? s.options : []).filter((o) => o && typeof o.value === "string")
        .map((o) => ({ value: o.value, label: typeof o.label === "string" && o.label ? o.label : o.value }));
    }
    out.push(f);
  }
  return out;
}

/** Початкові значення форми (секретів нема ніколи): `{values, secrets: {}, erase: []}`. */
export function initialForm(fields) {
  const values = [];
  for (const f of fields) {
    if (f.type === "secret") continue;
    values.push([f.key, f.type === "bool" ? f.value === true : (f.value == null ? "" : String(f.value))]);
  }
  return { values: Object.fromEntries(values), secrets: {}, erase: [] };
}

const trim = (v) => (typeof v === "string" ? v.trim() : v);

/**
 * Патч запиту: `{settings, secrets}` лише зі зміненого. Текст і шлях обрізаються (вставка з буфера несе пробіли й
 * перенос рядка); очищене поле — `null` (ключ знімається, діє типове маніфесту). Секрет: введене — нове значення;
 * позначене до стирання — `null`, але лише заданий необовʼязковий; введене перемагає стирання.
 */
export function formPatch(fields, init, cur) {
  const settings = [];
  const secrets = [];
  const erase = new Set(Array.isArray(cur?.erase) ? cur.erase : []);
  for (const f of fields) {
    if (f.type === "secret") {
      const typed = trim(get(cur?.secrets, f.key));
      if (typeof typed === "string" && typed) secrets.push([f.key, typed]);
      else if (erase.has(f.key) && f.set === true && !f.required) secrets.push([f.key, null]);
      continue;
    }
    if (f.type === "bool") {
      const a = get(init?.values, f.key) === true;
      const b = get(cur?.values, f.key) === true;
      if (a !== b) settings.push([f.key, b]);
      continue;
    }
    const a = trim(String(get(init?.values, f.key) ?? ""));
    const b = trim(String(get(cur?.values, f.key) ?? ""));
    if (a !== b) settings.push([f.key, b === "" ? null : b]);
  }
  return { settings: Object.fromEntries(settings), secrets: Object.fromEntries(secrets) };
}

export const isDirty = (p) => Object.keys(p?.settings ?? {}).length > 0 || Object.keys(p?.secrets ?? {}).length > 0;

/** Ключі обовʼязкових полів без значення: порожній текст/шлях/список; секрет не заданий (чи невідомо) і не введений. */
export function missingRequired(fields, cur) {
  return fields.filter((f) => {
    if (!f.required || f.type === "bool") return false;
    if (f.type === "secret") {
      const typed = trim(get(cur?.secrets, f.key));
      return f.set !== true && !(typeof typed === "string" && typed);
    }
    return trim(String(get(cur?.values, f.key) ?? "")) === "";
  }).map((f) => f.key);
}

/** Тіло `module-enable|settings`: `space` і `id` завжди (запис іде туди, що людина бачить); порожні патчі не йдуть. */
export function writePayload(space, id, patch, replace = false) {
  const out = { space, id };
  if (Object.keys(patch?.settings ?? {}).length) out.settings = patch.settings;
  if (Object.keys(patch?.secrets ?? {}).length) out.secrets = patch.secrets;
  if (replace === true) out.replace = true;
  return out;
}
```

- [ ] **Step 4: Тести зелені.** `python3 "$G" 120 1500 node --test tests/connections-model.test.mjs` → усі pass.

- [ ] **Step 5: Мутації** (під охоронцем, кожну відкотити): прибрати `has()` у `roleKeys` (→ `ROLE_KEYS[role] ?? null`) — мусить червоніти тест ролей (`__proto__`); прибрати `.trim()` у `formPatch` — тест патча; прибрати умову `lc.error === e.error` у `whyOf` — тест причини.

- [ ] **Step 6: Commit.**

```bash
git add app/connections-model.js tests/connections-model.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(connections): чиста модель екрана «Підключення»

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Тексти й розмітка (`app/i18n.js`, `app/connections-view.js`)

**Files:**
- Modify: `app/i18n.js` (ключі в `UK` і `EN`; правка `publishErrVercelAuth` і коментаря біля нього ≈ 379)
- Create: `app/connections-view.js`
- Test: `tests/connections-view.test.mjs`

- [ ] **Step 1: Ключі словника.** Додати в `UK` (поряд із ключами просторів, після `spaceEdit`) і тими самими ключами в `EN`:

| ключ | UK | EN |
|---|---|---|
| `cnTitle` | `'Підключення'` | `'Connections'` |
| `cnOpen` | `'Підключення…'` | `'Connections…'` |
| `spaceConn` | `(name) => \`Підключення простору «${name}»\`` | `(name) => \`Connections of the space “${name}”\`` |
| `cnTitleIn` | `(name) => \`Підключення · ${name}\`` | `(name) => \`Connections · ${name}\`` |
| `cnLead` | `'Модулі цього простору: куди публікувати, де жити коментарям команди, звідки брати токени. Без жодного модуля канвас працює.'` | `'Modules of this space: where to publish, where team comments live, where tokens come from. The canvas works without any module.'` |
| `cnLeadWhere` | `(path) => \`Налаштування — у ${path}/space.json, секрети — окремо, у сховищі Deai на цьому компʼютері.\`` | `(path) => \`Settings live in ${path}/space.json; secrets are kept apart, in the Deai store on this computer.\`` |
| `cnLoading` | `'Вантажу модулі…'` | `'Loading modules…'` |
| `cnErrLoad` | `'Не вдалося прочитати модулі простору.'` | `'Could not read the modules of this space.'` |
| `cnErrSpaceJson` | `(path) => \`Файл space.json цього простору не читається — виправте чи видаліть його в ${path}; до того модулі не змінити.\`` | ``(path) => `This space's space.json cannot be read — fix or delete it in ${path}; modules cannot change until then.` `` |
| `cnRolePublish` | `'Публікація'` | `'Publishing'` |
| `cnRolePublishLead` | `'Куди канвас викладає превʼю задачі.'` | `'Where the canvas puts the preview of a task.'` |
| `cnRoleComments` | `'Командні коментарі'` | `'Team comments'` |
| `cnRoleCommentsLead` | `'Де живуть коментарі команди до макетів.'` | `"Where the team's comments on mockups live."` |
| `cnRoleTokens` | `'Токени дизайн-системи'` | `'Design-system tokens'` |
| `cnRoleTokensLead` | `'Звідки інспектор бере токени для звірки.'` | `'Where the inspector takes tokens to compare against.'` |
| `cnRoleOther` | `'Інше'` | `'Other'` |
| `cnNonePublish` | `'кнопки публікації в смузі нема'` | `'there is no publish button in the bar'` |
| `cnNoneComments` | `'коментарі лише локальні — для вас і агента'` | `'comments are local only — for you and the agent'` |
| `cnNoneTokens` | `'інспектор звіряє без токенів простору'` | `"the inspector compares without the space's tokens"` |
| `cnNow` | `(name) => \`Зараз: ${name}\`` | `(name) => \`Now: ${name}\`` |
| `cnNowNone` | `(why) => \`Зараз: нікого — ${why}\`` | `(why) => \`Now: nobody — ${why}\`` |
| `cnNowNobody` | `'Зараз: нікого'` | `'Now: nobody'` |
| `cnNowLegacy` | `'Зараз: вбудована інтеграція ЛІГА (модуль у цій ролі її перекриє)'` | `'Now: the built-in LIGA integration (a module in this role overrides it)'` |
| `cnMissingSec` | `'Не встановлені на цьому компʼютері'` | `'Not installed on this computer'` |
| `cnWhyMissing` | `'Модуль увімкнено в space.json, але на цьому компʼютері його нема.'` | `'The module is on in space.json, but this computer does not have it.'` |
| `cnBadgeOk` | `'Підключено'` | `'Connected'` |
| `cnBadgeError` | `'Помилка'` | `'Error'` |
| `cnBadgeUnchecked` | `'Не перевірено'` | `'Not checked'` |
| `cnBadgeOff` | `'Вимкнено'` | `'Off'` |
| `cnBadgeMissing` | `'Не встановлено'` | `'Not installed'` |
| `cnImplicit` | `'типово'` | `'default'` |
| `cnEnable` | `'Підключити'` | `'Connect'` |
| `cnConfigure` | `'Налаштувати'` | `'Configure'` |
| `cnCheck` | `'Перевірити'` | `'Check'` |
| `cnChecking` | `'Перевіряю…'` | `'Checking…'` |
| `cnDisable` | `'Вимкнути'` | `'Turn off'` |
| `cnAgentTitle` | `'Через агента.'` | `'Through the agent.'` |
| `cnAgentText` | `'Те саме агент робить через API канваса:'` | `'The agent does the same through the canvas API:'` |
| `cnModStaticName` | `'Публікація в теку'` | `'Publish to a folder'` |
| `cnModStaticDesc` | `'Збирає превʼю в теку на цьому компʼютері. Нічого не йде в мережу.'` | `'Builds the preview into a folder on this computer. Nothing leaves the machine.'` |
| `cnModVercelName` | `'Vercel'` | `'Vercel'` |
| `cnModVercelDesc` | `'Викладає превʼю на ваш акаунт Vercel і дає посилання, яким можна поділитись.'` | `'Deploys the preview to your Vercel account and gives a link you can share.'` |
| `cnModSupabaseName` | `'Supabase'` | `'Supabase'` |
| `cnModSupabaseDesc` | `'Коментарі команди у вашому проєкті Supabase, з оновленням наживо.'` | `'Team comments in your own Supabase project, updated live.'` |
| `cnModCssName` | `'Токени з CSS'` | `'Tokens from CSS'` |
| `cnModCssDesc` | `'Читає CSS-змінні з файла вашої дизайн-системи.'` | `'Reads CSS custom properties from your design-system file.'` |
| `cnFieldStaticFolder` | `'Тека для превʼю'` | `'Folder for previews'` |
| `cnFieldPreviewPassword` | `'Пароль превʼю (необовʼязково)'` | `'Preview password (optional)'` |
| `cnFieldVercelToken` | `'Токен Vercel'` | `'Vercel token'` |
| `cnFieldVercelTeam` | `'Команда Vercel (slug або team_…; порожньо — особистий акаунт)'` | `'Vercel team (slug or team_…; empty — personal account)'` |
| `cnFieldSupabaseUrl` | `'Адреса проєкту (https://<ref>.supabase.co)'` | `'Project URL (https://<ref>.supabase.co)'` |
| `cnFieldSupabaseKey` | `'Публічний ключ (anon / publishable)'` | `'Public key (anon / publishable)'` |
| `cnFieldCssFile` | `'CSS-файл із токенами дизайн-системи'` | `'CSS file with the design-system tokens'` |
| `cnClose` | `'Закрити'` | `'Close'` |
| `cnSave` | `'Зберегти'` | `'Save'` |
| `cnBusy` | `'Зберігаю й перевіряю…'` | `'Saving and checking…'` |
| `cnNoSettings` | `'Налаштувань немає.'` | `'No settings.'` |
| `cnPathHint` | `'{home} — домашня тека, {space} — тека простору, {space_id} — id простору.'` | `'{home} is your home folder, {space} the space folder, {space_id} the space id.'` |
| `cnSecretSet` | `'задано'` | `'set'` |
| `cnSecretUnset` | `'не задано'` | `'not set'` |
| `cnSecretUnknown` | `'невідомо — сховище секретів не читається'` | `'unknown — the secret store cannot be read'` |
| `cnSecretWhere` | `'Зберігається поза текою простору, у сховищі Deai.'` | `'Kept outside the space folder, in the Deai store.'` |
| `cnSecretKeep` | `'Нове значення (порожньо — не міняти)'` | `'New value (empty — keep)'` |
| `cnSecretEnter` | `'Введіть значення'` | `'Enter the value'` |
| `cnErase` | `'Стерти'` | `'Erase'` |
| `cnEraseUndo` | `'Не стирати'` | `'Keep'` |
| `cnEraseMarked` | `'буде стерто при збереженні'` | `'will be erased on save'` |
| `cnFieldRequired` | `'Обовʼязкове поле.'` | `'Required.'` |
| `cnCheckSavedFirst` | `'Спершу збережіть зміни — перевірка йде по збереженому.'` | `'Save first — the check runs on what is saved.'` |
| `cnSavedButFailed` | `'Збережено, але перевірка не пройшла.'` | `'Saved, but the check failed.'` |
| `cnCheckOk` | `'Працює.'` | `'Works.'` |
| `cnToastEnabled` | `(name) => \`Підключено: ${name}\`` | `(name) => \`Connected: ${name}\`` |
| `cnToastSaved` | `(name) => \`Збережено: ${name}\`` | `(name) => \`Saved: ${name}\`` |
| `cnDiscardAsk` | `'Відкинути незбережені зміни?'` | `'Discard the unsaved changes?'` |
| `cnDiscard` | `'Відкинути'` | `'Discard'` |
| `cnReplaceAsk` | `(role, holders, name) => \`${role} зараз виконує «${holders}». Підключити «${name}» замість нього? «${holders}» вимкнеться, його налаштування лишаться.\`` | `(role, holders, name) => \`${role} is now done by “${holders}”. Connect “${name}” instead? “${holders}” will be turned off; its settings stay.\`` |
| `cnReplace` | `'Замінити'` | `'Replace'` |
| `cnDisableAsk` | `(name) => \`Вимкнути «${name}»? Налаштування й секрети лишаться — підключити можна знову.\`` | `(name) => \`Turn off “${name}”? Its settings and secrets stay — you can connect it again.\`` |
| `cnDisableNone` | `(role, why) => \`Після цього роль «${role}» лишиться без модуля: ${why}.\`` | `(role, why) => \`After this, “${role}” has no module: ${why}.\`` |
| `cnDisableLegacy` | `(role) => \`Роль «${role}» знову виконуватиме вбудована інтеграція ЛІГА.\`` | `(role) => \`The built-in LIGA integration takes “${role}” back.\`` |
| `cnErrBadSettings` | `'Налаштування неповні чи неправильні.'` | `'The settings are incomplete or wrong.'` |
| `cnErrModuleError` | `'Модуль упав під час перевірки.'` | `'The module crashed during the check.'` |
| `cnErrTimeout` | `'Перевірка не вклалась у відведений час.'` | `'The check ran out of time.'` |
| `cnErrSecretsUnreadable` | `'Не вдалося прочитати сховище секретів Deai.'` | `'The Deai secret store cannot be read.'` |
| `cnErrBadManifest` | `'Модуль пошкоджений: його опис module.json не читається.'` | `'The module is damaged: its module.json cannot be read.'` |
| `cnErrBadFolder` | `'Тека не годиться для превʼю.'` | `'This folder cannot hold previews.'` |
| `cnErrNotWritable` | `'У теку не можна писати.'` | `'The folder is not writable.'` |
| `cnErrNoToken` | `'Токен Vercel не задано.'` | `'The Vercel token is not set.'` |
| `cnErrVercelAuth` | `'Vercel відмовив у доступі — перевірте токен і команду.'` | `'Vercel denied access — check the token and the team.'` |
| `cnErrVercelError` | `'Vercel відповів помилкою.'` | `'Vercel answered with an error.'` |
| `cnErrBadKey` | `'Ключ Supabase не підходить чи не задано.'` | `'The Supabase key is wrong or not set.'` |
| `cnErrNoSchema` | `'У проєкті Supabase нема таблиці comments — виконайте schema.sql.'` | `'The Supabase project has no comments table — run schema.sql.'` |
| `cnErrSupabaseError` | `'Supabase відповів помилкою.'` | `'Supabase answered with an error.'` |
| `cnErrNetwork` | `'Сервіс недосяжний — перевірте адресу й мережу.'` | `'The service cannot be reached — check the address and the network.'` |
| `cnErrGeneric` | `'Перевірка не пройшла.'` | `'The check failed.'` |
| `cnRefRoleTaken` | `'Роль уже зайнята іншим модулем — оновіть сторінку й спробуйте ще.'` | `'Another module already holds this role — reload the page and try again.'` |
| `cnRefBadSettings` | `'Сервер не прийняв налаштування.'` | `'The server rejected the settings.'` |
| `cnRefUnknownModule` | `'Такого модуля вже нема.'` | `'This module no longer exists.'` |
| `cnRefUnknownSpace` | `'Такого простору вже нема.'` | `'This space no longer exists.'` |
| `cnRefSpaceJson` | `'Файл space.json простору не читається.'` | `"The space's space.json cannot be read."` |
| `cnRefSpacesOff` | `'Простори вимкнено на цьому компʼютері.'` | `'Spaces are off on this computer.'` |
| `cnRefUnwritable` | `'Не вдалося записати space.json простору.'` | `"Could not write the space's space.json."` |
| `cnRefGeneric` | `'Не вдалося зберегти.'` | `'Could not save.'` |

Стиль лапок — як у сусідніх рядках файла (переважно одинарні; рядок з апострофом — подвійні).

`publishErrVercelAuth` (UK ≈ 391, EN ≈ 1170): «(через API чи агента)» → «(меню простору → «Підключення»)» / «(through the API or the agent)» → «(space menu → Connections)». Коментар ≈ 379: «Керувати модулем у 0.3.0 можна лише через API чи агента (екран «Підключення» — етап 3), тож тексти не обіцяють кнопки.» → «Модулем керують на екрані «Підключення» (меню простору, 0.5.0) або через API чи агента.»

> **Поправки після ревʼю Task 2 (коміт `43d6c64`) — обовʼязкові для цієї задачі:**
> - модель тепер експортує `canErase(f)`; поле `f.blank` у `select`; `providerLine` може дати `{kind: "error"}`; нові коди `vercel-busy` → `cnErrVercelBusy`, `no-folder` → `cnErrBadFolder`;
> - словник: додати `cnErrVercelBusy` (UK `'Vercel тимчасово відмовляє (ліміт запитів) — спробуйте за хвилину.'`, EN `'Vercel is temporarily refusing requests (rate limit) — try again in a minute.'`) і `cnNowError` (UK `'Зараз: невідомо — space.json не читається'`, EN `'Now: unknown — space.json cannot be read'`);
> - у `connections-view.js`: імпортувати `canErase` і замість `const canErase = f.set === true && !f.required;` брати `const erasable = canErase(f);`; список: порожня опція рендериться, коли `f.blank` (а не `!f.required`), і вибрана, коли значення форми `""`; `nowHTML` для `kind: "error"` — `t("cnNowError")`;
> - дописати в тест розмітки: обовʼязковий `select` зі значенням з опцій — без порожньої опції; обовʼязковий без значення — з порожньою вибраною; необовʼязковий — завжди з порожньою; `providerLine` error → «Зараз: невідомо».

- [ ] **Step 2: Падаючі тести розмітки** `tests/connections-view.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";

import { setLang } from "../app/i18n.js";
import { cardHTML, connPageHTML, drawerHTML, modName, roleTitle } from "../app/connections-view.js";
import { formFields, initialForm } from "../app/connections-model.js";

const SP = { id: "studio", name: "Studio", path: "/u/work/studio", integrations: false,
  capabilities: { publish: "static-publish", comments: null, tokens: null } };
const LIST = [
  { id: "css-tokens", name: "Токени з CSS", roles: ["tokens"], enabled: false, implicit: false, status: "unchecked",
    settings: [{ key: "file", type: "path", label: "CSS-файл із токенами дизайн-системи", required: true }] },
  { id: "static-publish", name: "Публікація в теку", roles: ["publish"], enabled: true, implicit: true, status: "unchecked",
    settings: [{ key: "folder", type: "path", label: "Тека", required: true, value: "{home}/deai-published/{space_id}" },
      { key: "password", type: "secret", label: "Пароль", required: false, set: true }] },
  { id: "supabase-comments", name: "Supabase", roles: ["comments"], enabled: false, implicit: false, status: "unchecked", settings: [] },
  { id: "vercel-publish", name: "Vercel", roles: ["publish"], enabled: false, implicit: false, status: "unchecked", settings: [] },
];
const view = (o = {}) => ({ space: SP, list: LIST, failed: null, busy: new Map(), ...o });

test.beforeEach(() => setLang("uk"));

test("сторінка: заголовок, тека, секції в порядку ролей, рядок «Зараз», агент з id простору", () => {
  const h = connPageHTML(view());
  assert.match(h, /Підключення · Studio/);
  assert.match(h, /\/u\/work\/studio\/space\.json/);
  const order = ["Публікація", "Командні коментарі", "Токени дизайн-системи"].map((s) => h.indexOf(`>${s}<`));
  assert.ok(order.every((i) => i > 0) && order[0] < order[1] && order[1] < order[2], String(order));
  assert.match(h, /Зараз: Публікація в теку/);
  assert.match(h, /Зараз: нікого — коментарі лише локальні/);
  assert.match(h, /\/api\/modules\?space=studio/);
  assert.doesNotMatch(h, /Не встановлені/, "секції missing нема, коли таких модулів нема");
});

test("сторінка: legacy, missing-секція, завантаження, помилка списку й нечитабельний space.json", () => {
  const liga = { ...SP, integrations: true, capabilities: { publish: "legacy", comments: "legacy", tokens: null } };
  const missing = { id: "gone", name: "gone", roles: [], enabled: true, status: "missing", settings: [] };
  const h = connPageHTML(view({ space: liga, list: [...LIST, missing] }));
  assert.match(h, /вбудована інтеграція ЛІГА/);
  assert.match(h, /Не встановлені на цьому компʼютері/);
  assert.match(h, /data-cn="disable" data-id="gone"/);
  assert.match(connPageHTML(view({ list: null })), /Вантажу модулі…/);
  const failed = connPageHTML(view({ list: null, failed: { code: null, message: "<b>boom</b>" } }));
  assert.match(failed, /Не вдалося прочитати модулі простору/);
  assert.match(failed, /data-cn="retry"/);
  assert.doesNotMatch(failed, /<b>boom/);
  const sj = connPageHTML(view({ list: null, failed: { code: "space-json-unreadable", message: "x" } }));
  assert.match(sj, /space\.json цього простору не читається/);
  assert.doesNotMatch(connPageHTML(view({ space: { ...SP, capabilities: { error: "space-json-unreadable" } } })), /cn-card/,
    "capabilities.error — картки не малюються");
});

test("картка: бейдж, «типово», дії з data-cn і data-id, опис вбудованого, причина помилки", () => {
  const sp = cardHTML(LIST[1], new Map());
  assert.match(sp, /Публікація в теку/);
  assert.match(sp, /cn-badge--unchecked/);
  assert.match(sp, />типово</);
  for (const a of ["configure", "check", "disable"]) assert.match(sp, new RegExp(`data-cn="${a}" data-id="static-publish"`));
  assert.match(sp, /Збирає превʼю в теку/);
  const err = cardHTML({ ...LIST[3], enabled: true, status: "error", error: "no-token",
    last_check: { ok: false, error: "no-token", detail: "Токен Vercel не задано" } }, new Map());
  assert.match(err, /cn-badge--error/);
  assert.match(err, /Токен Vercel не задано\./);
  const busy = cardHTML({ ...LIST[1] }, new Map([["static-publish", "check"]]));
  assert.match(busy, /Перевіряю…/);
  assert.match(busy, /disabled/);
});

test("картка: ворожі назва, id і деталь — лише текстом", () => {
  const evil = { id: 'x"><img src=x onerror=1>', name: "<b>n</b>", roles: ["<script>"], enabled: true, status: "error",
    error: "<i>e</i>", last_check: { ok: false, error: "<i>e</i>", detail: "<svg onload=1>" }, settings: [] };
  const h = cardHTML(evil, new Map());
  assert.doesNotMatch(h, /<img|<b>n|<script>|<i>e|<svg/);
  assert.match(h, /&lt;b&gt;n&lt;\/b&gt;/);
});

test("назви й підписи вбудованих — мовою інтерфейсу; чужі — з маніфесту", () => {
  setLang("en");
  assert.equal(modName(LIST[1]), "Publish to a folder");
  assert.equal(roleTitle("publish"), "Publishing");
  assert.equal(roleTitle("vcs"), "vcs");
  assert.equal(roleTitle(""), "Other");
  assert.equal(modName({ id: "memo-publish", name: "Memo (тест)" }), "Memo (тест)");
});

test("панель: поля за типами, секрет без значення, стерти лише заданий необовʼязковий, підказка шляху", () => {
  const e = { id: "vault", name: "Vault", roles: ["publish"], enabled: true, status: "ok", settings: [
    { key: "folder", type: "path", label: "Тека", required: true, value: '{home}/"x"' },
    { key: "on", type: "bool", label: "Прапор", required: false, value: true },
    { key: "mode", type: "select", label: "Режим", required: false, value: "b", options: [{ value: "a", label: "A" }, { value: "b", label: "<B>" }] },
    { key: "token", type: "secret", label: "Токен", required: true, set: true },
    { key: "pw", type: "secret", label: "Пароль", required: false, set: true },
    { key: "nope", type: "secret", label: "Ні", required: false, set: null },
  ] };
  const fields = formFields(e);
  const h = drawerHTML({ entry: e, mode: "edit", fields, form: initialForm(fields), busy: false, result: null, errors: {}, spaceName: "Studio" });
  assert.match(h, /value="\{home\}\/&quot;x&quot;"/);
  assert.match(h, /type="checkbox"[^>]*checked/);
  assert.match(h, /<option value="b" selected>&lt;B&gt;<\/option>/);
  const pw = [...h.matchAll(/<input[^>]*type="password"[^>]*>/g)].map((m) => m[0]);
  assert.equal(pw.length, 3);
  for (const i of pw) {
    assert.doesNotMatch(i, /\svalue=/, "секрет ніколи не потрапляє в розмітку");
    assert.match(i, /autocomplete="new-password"/);
  }
  assert.equal((h.match(/data-cn-dr="erase"/g) || []).length, 1, "стерти — лише заданий необовʼязковий (pw)");
  assert.match(h, /data-cn-dr="erase" data-key="pw"/);
  assert.match(h, /невідомо — сховище секретів не читається/);
  assert.match(h, /\{home\} — домашня тека/);
  assert.match(h, /data-cn-dr="check"/, "у режимі правки є «Перевірити»");
  assert.match(h, /data-cn-dr="submit"[^>]*>Зберегти</);
});

test("панель: режим підключення, помилки полів, результат і зайнятість", () => {
  const e = LIST[0];
  const fields = formFields(e);
  const base = { entry: e, mode: "enable", fields, form: initialForm(fields), busy: false, result: null, errors: {}, spaceName: "Studio" };
  const h = drawerHTML(base);
  assert.doesNotMatch(h, /data-cn-dr="check"/);
  assert.match(h, /data-cn-dr="submit"[^>]*>Підключити</);
  assert.match(drawerHTML({ ...base, errors: { file: "cnFieldRequired" } }), /aria-invalid="true"[\s\S]*Обовʼязкове поле\./);
  assert.match(drawerHTML({ ...base, result: { kind: "failed", key: "cnErrBadSettings", detail: "file: required" } }),
    /Збережено, але перевірка не пройшла\.[\s\S]*Налаштування неповні[\s\S]*file: required/);
  assert.match(drawerHTML({ ...base, result: { kind: "ok", key: "cnCheckOk", detail: "2 tokens" } }), /cn-res--ok[\s\S]*Працює\./);
  const busy = drawerHTML({ ...base, busy: true });
  assert.match(busy, /Зберігаю й перевіряю…/);
  assert.match(busy, /data-cn-field="file"[^>]*disabled/);
  const evil = drawerHTML({ ...base, entry: { ...e, name: "<b>", id: "<i>" }, spaceName: "<s>" });
  assert.doesNotMatch(evil, /<b>|<i>|<s>/);
});
```

- [ ] **Step 3: Запустити — мусить впасти** (модуля нема): `python3 "$G" 120 1500 node --test tests/connections-view.test.mjs`.

- [ ] **Step 4: Реалізувати** `app/connections-view.js`:

```js
/**
 * Розмітка екрана «Підключення» (Deai 0.5.0, етап 3a). Чисті будівельники рядків — як `tasks-home.js`: ні DOM, ні
 * fetch. Логіка (що показати) — у `connections-model.js`; тут лише «стан → HTML» і слова (`t()`).
 *
 *   connPageHTML(v)  v = {space, list, failed, busy}
 *                     space  — запис `/api/spaces` поточного простору ({id, name, path, integrations, capabilities});
 *                     list   — записи `GET /api/modules` або `null` (вантажиться);
 *                     failed — `{code, message}`, коли список не прочитався;
 *                     busy   — Map id → 'check'|'disable': дія в польоті.
 *   drawerHTML(d)    d = {entry, mode: 'enable'|'edit', fields, form, busy, result, errors, spaceName}.
 *
 * Гачки для `app.js`: `data-cn="<дія>" data-id="<модуль>"` на картках і в помилці сторінки, `data-cn-dr="<дія>"` у
 * панелі, `data-cn-field="<ключ>" data-type="<тип>"` на полях.
 *
 * ⛔ Усе з даних (назви, підписи, опції, тека, `error`, `detail`, id) — лише через `esc()`. ⛔ Значення секрету НІКОЛИ
 * не потрапляє в розмітку: поле пароля завжди порожнє.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import {
  builtinText, cardView, groupModules, providerLine, roleIcon, roleKeys, whyOf,
} from "./connections-model.js";

/** Назва модуля: вбудований — мовою інтерфейсу, інший — `name` маніфесту як є. */
export const modName = (e) => {
  const k = builtinText(e?.id)?.name;
  return k ? t(k) : String(e?.name || e?.id || "");
};

/** Назва ролі: своя — зі словника; чужа — сам id; порожня — «Інше». */
export const roleTitle = (role) => {
  const k = roleKeys(role);
  return k ? t(k.title) : (role ? String(role) : t("cnRoleOther"));
};

const fieldLabel = (e, f) => {
  const fields = builtinText(e?.id)?.fields;
  const k = fields && Object.prototype.hasOwnProperty.call(fields, f.key) ? fields[f.key] : null;
  return k ? t(k) : f.label;
};

const rolesLine = (e) => (Array.isArray(e?.roles) ? e.roles : []).map(roleTitle).join(" · ");

const BADGES = {
  ok: ["cnBadgeOk", "check"], error: ["cnBadgeError", "warn"], unchecked: ["cnBadgeUnchecked", null],
  off: ["cnBadgeOff", null], missing: ["cnBadgeMissing", "warn"],
};
const badgeHTML = (kind) => {
  const [key, icon] = BADGES[kind];
  return `<span class="cn-badge cn-badge--${kind}">${icon ? ico(icon, 13) : ""}${esc(t(key))}</span>`;
};

const ACTIONS = {
  enable: ["cnEnable", "plus", "ctl ctl--out"],
  configure: ["cnConfigure", "pencil", "ctl ctl--out"],
  check: ["cnCheck", "refresh", "ctl"],
  disable: ["cnDisable", null, "ctl"],
};

const detailHTML = (d) => (d ? `<span class="cn-why-detail">${esc(d)}</span>` : "");

function whyHTML(e) {
  const w = whyOf(e);
  if (!w) return "";
  return `<div class="cn-why">${ico("warn", 13)}<span>${esc(t(w.key))}${detailHTML(w.detail)}</span></div>`;
}

/** Картка модуля. `busy` — Map id → дія в польоті: її кнопки вимкнені, «Перевірити» каже «Перевіряю…». */
export function cardHTML(e, busy) {
  const v = cardView(e);
  const b = busy?.get?.(e.id) ?? null;
  const desc = builtinText(e.id)?.desc;
  const roles = rolesLine(e);
  const acts = v.actions.map((a) => {
    const [key, icon, cls] = ACTIONS[a];
    const label = a === "check" && b === "check" ? t("cnChecking") : t(key);
    return `<button class="${cls}" data-cn="${a}" data-id="${esc(e.id)}"${b ? " disabled" : ""}>`
      + `${icon ? ico(icon) : ""}${esc(label)}</button>`;
  }).join("");
  return `<div class="cn-card" data-id="${esc(e.id)}">
    <div class="cn-card-top"><span class="cn-ic">${ico(roleIcon(e.roles?.[0]))}</span>
      <div class="cn-card-name"><b>${esc(modName(e))}</b>${roles ? `<span class="cn-card-role">${esc(roles)}</span>` : ""}</div>
      ${v.implicit ? `<span class="cn-tag">${esc(t("cnImplicit"))}</span>` : ""}${badgeHTML(v.badge)}</div>
    ${desc ? `<p class="cn-card-desc">${esc(t(desc))}</p>` : ""}
    ${v.why ? whyHTML(e) : ""}
    <div class="cn-card-acts">${acts}</div></div>`;
}

function nowHTML(role, v) {
  const p = providerLine(role, v.space?.capabilities, v.list);
  if (!p) return "";
  const txt = p.kind === "legacy" ? t("cnNowLegacy")
    : p.kind === "none" ? (p.noneKey ? t("cnNowNone", t(p.noneKey)) : t("cnNowNobody"))
      : t("cnNow", p.entry ? modName(p.entry) : p.id);
  return `<span class="cn-now">${esc(txt)}</span>`;
}

function sectionHTML(s, i, v) {
  const keys = roleKeys(s.role);
  return `<section class="cn-sec" aria-labelledby="cn-sec-${i}">
    <div class="cn-sec-head"><h2 class="cn-sec-h" id="cn-sec-${i}">${esc(roleTitle(s.role))}</h2>${nowHTML(s.role, v)}</div>
    ${keys ? `<p class="cn-sec-lead">${esc(t(keys.lead))}</p>` : ""}
    <div class="cn-grid">${s.modules.map((e) => cardHTML(e, v.busy)).join("")}</div></section>`;
}

const agentHTML = (sp) => `<div class="cn-agent">${ico("task")}<div><b>${esc(t("cnAgentTitle"))}</b> ${esc(t("cnAgentText"))}
    <code class="cn-code">GET /api/modules?space=${esc(encodeURIComponent(sp.id))}</code>
    <code class="cn-code">POST /api/module-enable {space: "${esc(sp.id)}", id, settings, secrets, replace}</code>
    <code class="cn-code">POST /api/module-settings · /api/module-check · /api/module-disable</code></div></div>`;

/** Сторінка «Підключення». Простору нема — порожньо (входів тоді нема, `app.js` сюди не пускає). */
export function connPageHTML(v) {
  const sp = v?.space;
  if (!sp) return "";
  const head = `<h1 class="th-h" id="cn-title">${esc(t("cnTitleIn", sp.name))}</h1>
    <p class="cn-lead">${esc(t("cnLead"))} ${esc(t("cnLeadWhere", sp.path || ""))}</p>`;
  const wrap = (inner) => `<div class="th-in cn-in">${head}${inner}</div>`;
  const sjBad = !!sp.capabilities?.error || v.failed?.code === "space-json-unreadable";
  if (sjBad || v.failed) {
    const msg = sjBad ? t("cnErrSpaceJson", sp.path || "") : t("cnErrLoad");
    const det = !sjBad && v.failed?.message ? detailHTML(String(v.failed.message).slice(0, 300)) : "";
    return wrap(`<div class="cn-err" role="alert">${ico("warn")}<span>${esc(msg)}${det}</span>`
      + `<button class="ctl ctl--out" data-cn="retry">${ico("refresh")}${esc(t("retry"))}</button></div>`);
  }
  if (!Array.isArray(v.list)) return wrap(`<p class="cn-loading">${esc(t("cnLoading"))}</p>`);
  const { sections, missing } = groupModules(v.list);
  const miss = missing.length
    ? `<section class="cn-sec" aria-labelledby="cn-sec-miss"><div class="cn-sec-head"><h2 class="cn-sec-h" id="cn-sec-miss">`
      + `${esc(t("cnMissingSec"))}</h2></div><div class="cn-grid">${missing.map((e) => cardHTML(e, v.busy)).join("")}</div></section>`
    : "";
  return wrap(`${sections.map((s, i) => sectionHTML(s, i, v)).join("")}${miss}${agentHTML(sp)}`);
}

const SECRET_STATE = { true: "cnSecretSet", false: "cnSecretUnset", null: "cnSecretUnknown" };

function fieldHTML(e, f, i, d) {
  const id = `cn-f-${i}`;
  const err = d.errors?.[f.key];
  const inv = err ? ` aria-invalid="true" aria-describedby="${id}-err"` : "";
  const dis = d.busy ? " disabled" : "";
  const data = `data-cn-field="${esc(f.key)}" data-type="${f.type}"`;
  const req = f.required ? ' <span class="cn-req" aria-hidden="true">*</span>' : "";
  const label = `${esc(fieldLabel(e, f))}${req}`;
  const errHTML = err ? `<p class="cn-field-err" id="${id}-err">${esc(t(err))}</p>` : "";
  const val = Object.prototype.hasOwnProperty.call(d.form?.values ?? {}, f.key) ? d.form.values[f.key] : "";
  if (f.type === "bool") {
    return `<div class="cn-field"><label class="cn-check"><input type="checkbox" id="${id}" ${data}`
      + `${val === true ? " checked" : ""}${dis}> ${label}</label>${errHTML}</div>`;
  }
  let ctl;
  if (f.type === "select") {
    const opts = (f.required ? "" : `<option value=""${val === "" ? " selected" : ""}>—</option>`)
      + f.options.map((o) => `<option value="${esc(o.value)}"${o.value === val ? " selected" : ""}>${esc(o.label)}</option>`).join("");
    ctl = `<select class="cn-inp" id="${id}" ${data}${inv}${dis}>${opts}</select>`;
  } else if (f.type === "secret") {
    const erase = Array.isArray(d.form?.erase) && d.form.erase.includes(f.key);
    const canErase = f.set === true && !f.required;
    ctl = `<div class="cn-secret-row"><input class="cn-inp" type="password" id="${id}" ${data}`
      + ` autocomplete="new-password" spellcheck="false"`
      + ` placeholder="${esc(t(f.set === true ? "cnSecretKeep" : "cnSecretEnter"))}"${inv}${dis}>`
      + `${canErase ? `<button type="button" class="ctl" data-cn-dr="erase" data-key="${esc(f.key)}" aria-pressed="${erase}"${dis}>`
        + `${esc(t(erase ? "cnEraseUndo" : "cnErase"))}</button>` : ""}</div>`
      + `<p class="cn-secret">${ico("lock", 13)}<span>${esc(t(SECRET_STATE[String(f.set)]))} · ${esc(t("cnSecretWhere"))}</span></p>`
      + (canErase ? `<p class="cn-hint" data-cn-erase-note="${esc(f.key)}"${erase ? "" : " hidden"}>${esc(t("cnEraseMarked"))}</p>` : "");
  } else {
    ctl = `<input class="cn-inp" type="text" id="${id}" ${data} value="${esc(val)}" spellcheck="false" autocomplete="off"${inv}${dis}>`
      + (f.type === "path" ? `<p class="cn-hint">${esc(t("cnPathHint"))}</p>` : "");
  }
  return `<div class="cn-field"><label class="cn-lbl" for="${id}">${label}</label>${ctl}${errHTML}</div>`;
}

function resultHTML(r) {
  if (!r) return "";
  if (r.kind === "ok") {
    return `<div class="cn-res cn-res--ok" role="status">${ico("check", 13)}<span>${esc(t(r.key))}${detailHTML(r.detail)}</span></div>`;
  }
  const head = r.kind === "failed" ? `<b>${esc(t("cnSavedButFailed"))}</b> ` : "";
  return `<div class="cn-res cn-res--err" role="alert">${ico("warn", 13)}<span>${head}${esc(t(r.key))}${detailHTML(r.detail)}</span></div>`;
}

/**
 * Бічна панель. `result.kind`: `ok` (зелений), `failed` (збережено, але перевірка не пройшла), `check-failed`
 * (кнопка «Перевірити» в панелі сказала «ні»), `refused` (HTTP-відмова — нічого не збережено).
 */
export function drawerHTML(d) {
  const e = d.entry;
  const desc = builtinText(e?.id)?.desc;
  const body = d.fields.length ? d.fields.map((f, i) => fieldHTML(e, f, i, d)).join("")
    : `<p class="cn-dr-none">${esc(t("cnNoSettings"))}</p>`;
  const primary = d.busy ? t("cnBusy") : t(d.mode === "enable" ? "cnEnable" : "cnSave");
  return `<form class="cn-dr-form" novalidate>
    <div class="cn-dr-head"><span class="cn-ic">${ico(roleIcon(e?.roles?.[0]))}</span>
      <div class="cn-dr-name"><b id="cn-dr-title">${esc(modName(e))}</b>`
    + `<span class="cn-card-role">${esc([rolesLine(e), d.spaceName].filter(Boolean).join(" · "))}</span></div>
      <button type="button" class="ctl ctl--icon" data-cn-dr="close" aria-label="${esc(t("cnClose"))}" title="${esc(t("cnClose"))}">${ico("x")}</button></div>
    <div class="cn-dr-body">${desc ? `<p class="cn-card-desc">${esc(t(desc))}</p>` : ""}${body}${resultHTML(d.result)}</div>
    <div class="cn-dr-foot">${d.mode === "edit"
      ? `<button type="button" class="ctl ctl--out" data-cn-dr="check"${d.busy ? " disabled" : ""}>${ico("refresh")}${esc(t("cnCheck"))}</button>` : ""}
      <span class="cn-grow"></span>
      <button type="submit" class="ctl ctl--pri" data-cn-dr="submit"${d.busy ? " disabled" : ""}>${esc(primary)}</button></div></form>`;
}
```

⚠️ Перевірити `ico()` сигнатуру `ico(name, size, cls)` і що іконки `up`, `comment`, `sliders`, `dots`, `check`, `warn`, `plus`, `pencil`, `refresh`, `lock`, `x`, `task` є в `ICONS` (`app/icons.js`) — так, усі є. Якщо тест `tests/icons.test.mjs` статично збирає `ico("…")` — новий файл він підхопить сам.

- [ ] **Step 5: Тести зелені** — `connections-view`, `i18n` (паритет ключів), `i18n-keys`, `i18n-literals`, `icons`, `esc`:

```bash
python3 "$G" 300 2000 node --test tests/connections-view.test.mjs tests/i18n.test.mjs tests/i18n-keys.test.mjs tests/i18n-literals.test.mjs tests/icons.test.mjs tests/esc.test.mjs tests/js-parses.test.mjs
```
Якщо `tests/esc.test.mjs` чи `js-parses` вимагають реєстрації нового файла (перелік модулів) — додати `connections-view.js`/`connections-model.js` туди за зразком сусідів.

- [ ] **Step 6: Commit.**

```bash
git add app/i18n.js app/connections-view.js tests/connections-view.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(connections): тексти й розмітка екрана «Підключення»

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
(плюс файли тестів-охоронців, якщо їх довелось доповнити — поіменно).

---

### Task 4: Стилі (`app/styles.css`) і охоронець класів

**Files:**
- Modify: `app/styles.css` (новий блок у кінці розділу екрана «Задачі», після правил `.th-*`)
- Test: `tests/connections-css.test.mjs` (новий)

- [ ] **Step 1: Падаючий тест** `tests/connections-css.test.mjs`:

```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
const rule = (selector) => {
  const e = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = new RegExp(`(?:^|[}\\s])${e}\\s*\\{([^{}]*)\\}`).exec(css);
  return m ? m[1] : null;
};

test("кожен клас розмітки «Підключення» має правило в styles.css", () => {
  const src = read("connections-view.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  const classes = new Set();
  for (const m of src.matchAll(/class="([^"]+)"/g)) {
    for (const c of m[1].replace(/\$\{[^}]*\}/g, " ").split(/\s+/)) if (/^cn-/.test(c)) classes.add(c);
  }
  for (const k of ["ok", "error", "missing"]) classes.add(`cn-badge--${k}`);
  assert.ok(classes.size >= 25, `знайдено лише ${classes.size} класів — регексп зламано: ${[...classes]}`);
  const missing = [...classes].filter((c) => !new RegExp(`\\.${c}(?![\\w-])`).test(css));
  assert.deepEqual(missing, [], `класи без правила: ${missing.join(", ")}`);
});

test("кнопка «Підключення» в голові «Задач»: ряд дій має правило", () => {
  assert.match(rule(".th-head-acts") ?? "", /display:flex/);
});

test("бічна панель: 420px, над оверлеєм і під смугою, схована атрибутом і поза оверлеєм", () => {
  const d = rule(".cn-drawer");
  assert.ok(d, "правила .cn-drawer немає");
  assert.match(d, /position:fixed/);
  assert.match(d, /width:420px/);
  assert.match(d, /z-index:var\(--z-widget\)/);
  assert.match(rule(".cn-drawer[hidden]") ?? "", /display:none/);
  assert.match(rule("body:not(.home-open) .cn-drawer") ?? "", /display:none/);
  assert.match(css, /@media\s*\(max-width:\s*720px\)\s*\{[^{}]*\.cn-drawer\s*\{[^{}]*width:100%/);
});

test("кольори правил .cn-* — лише токени (тінь може мати rgba)", () => {
  const bad = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/\.cn-/.test(m[1])) continue;
    const body = m[2].replace(/box-shadow:[^;]*;?/g, "");
    if (/#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i.test(body)) bad.push(m[1].trim());
  }
  assert.deepEqual(bad, [], `літерали кольорів у: ${bad.join(", ")}`);
});
```

- [ ] **Step 2: Запустити — мусить впасти.** `python3 "$G" 120 1500 node --test tests/connections-css.test.mjs`

- [ ] **Step 3: Додати стилі** в `app/styles.css` після правил `.th-*` (знайти блок екрана «Задачі», ≈ рядки 1449–1544):

```css
/* ── екран «Підключення» (етап 3a): сторінка `conn` оверлею `#tasks-home` і бічна панель `#cn-drawer` ── */
.th-head-acts{display:flex;align-items:center;gap:8px}
.cn-in{max-width:1120px}
.cn-lead{margin:0;max-width:760px;color:var(--dim);font-size:13px;line-height:1.5}
.cn-loading{margin:24px 0;color:var(--dim)}
.cn-err{display:flex;align-items:center;gap:10px;margin:18px 0;padding:10px 12px;border:1px solid var(--line2);
  border-radius:var(--r);background:var(--s2);color:var(--hi)}
.cn-err .ico{color:var(--bad);flex:none}
.cn-err .ctl{margin-left:auto;flex:none}
.cn-sec{margin:26px 0 0}
.cn-sec-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.cn-sec-h{margin:0;font-size:15px;font-weight:600;color:var(--hi)}
.cn-now{font-size:12.5px;color:var(--dim)}
.cn-sec-lead{margin:4px 0 12px;font-size:12.5px;color:var(--dim)}
.cn-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-top:12px}
.cn-sec-lead + .cn-grid{margin-top:0}
.cn-card{display:flex;flex-direction:column;gap:10px;padding:14px;border:1px solid var(--line);border-radius:var(--r-lg);background:var(--s2)}
.cn-card-top{display:flex;align-items:flex-start;gap:12px}
.cn-ic{display:flex;align-items:center;justify-content:center;width:32px;height:32px;flex:none;border-radius:var(--r);
  background:var(--s3);color:var(--mid)}
.cn-card-name{display:flex;flex-direction:column;gap:2px;flex:1;min-width:0}
.cn-card-name b{font-weight:600;color:var(--hi);overflow-wrap:anywhere}
.cn-card-role{font-size:12px;color:var(--dim);overflow-wrap:anywhere}
.cn-tag{flex:none;padding:1px 7px;border:1px solid var(--line2);border-radius:999px;font-size:11px;color:var(--dim)}
.cn-badge{display:inline-flex;align-items:center;gap:5px;flex:none;padding:2px 8px;border-radius:999px;
  background:var(--s3);color:var(--dim);font-size:12px;white-space:nowrap}
.cn-badge--ok{color:var(--ok)}
.cn-badge--error,.cn-badge--missing{color:var(--hi)}
.cn-badge--error .ico,.cn-badge--missing .ico{color:var(--bad)}
.cn-card-desc{margin:0;font-size:12.5px;line-height:1.45;color:var(--mid)}
.cn-why{display:flex;align-items:flex-start;gap:8px;padding:7px 9px;border:1px solid var(--line2);border-radius:var(--r-sm);
  background:var(--s1);color:var(--hi);font-size:12px;line-height:1.4}
.cn-why .ico{flex:none;margin-top:1px;color:var(--bad)}
.cn-why-detail{display:block;margin-top:2px;color:var(--dim);overflow-wrap:anywhere}
.cn-card-acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto}
.cn-agent{display:flex;gap:10px;margin-top:30px;padding:14px 16px;border:1px dashed var(--line2);border-radius:var(--r-lg);
  background:var(--s1);color:var(--mid);font-size:12.5px;line-height:1.5}
.cn-agent .ico{flex:none;margin-top:2px}
.cn-code{display:inline-block;margin:6px 6px 0 0;padding:2px 6px;border-radius:var(--r-sm);background:var(--s3);color:var(--hi);
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;overflow-wrap:anywhere}
.cn-drawer{position:fixed;top:var(--h-bar);right:0;bottom:0;width:420px;max-width:100%;z-index:var(--z-widget);
  display:flex;flex-direction:column;background:var(--s1);border-left:1px solid var(--line2);box-shadow:-18px 0 44px rgba(0,0,0,.35)}
.cn-drawer[hidden]{display:none}
body:not(.home-open) .cn-drawer{display:none}
@media (max-width:720px){.cn-drawer{width:100%;border-left:0}}
.cn-dr-form{display:flex;flex-direction:column;flex:1;min-height:0}
.cn-dr-head{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--line)}
.cn-dr-name{display:flex;flex-direction:column;gap:2px;flex:1;min-width:0}
.cn-dr-name b{font-weight:600;color:var(--hi);overflow-wrap:anywhere}
.cn-dr-body{display:flex;flex-direction:column;gap:14px;flex:1;min-height:0;overflow:auto;padding:16px}
.cn-dr-none{margin:0;color:var(--dim)}
.cn-dr-foot{display:flex;align-items:center;gap:8px;padding:12px 16px;border-top:1px solid var(--line)}
.cn-grow{flex:1}
.cn-field{display:flex;flex-direction:column;gap:6px}
.cn-lbl{font-size:12px;color:var(--mid)}
.cn-req{color:var(--open)}
.cn-inp{box-sizing:border-box;width:100%;height:var(--h-ctl);padding:0 10px;border:1px solid var(--line2);border-radius:var(--r);
  background:var(--s2);color:var(--hi);font:inherit}
.cn-inp:focus-visible{outline:2px solid var(--sel);outline-offset:1px}
.cn-inp[aria-invalid="true"]{border-color:var(--bad)}
.cn-inp:disabled{opacity:.6}
.cn-secret-row{display:flex;gap:6px}
.cn-secret-row .ctl{flex:none}
.cn-secret{display:flex;align-items:center;gap:6px;margin:0;font-size:12px;color:var(--dim)}
.cn-secret .ico{flex:none}
.cn-hint{margin:0;font-size:11.5px;line-height:1.4;color:var(--dim)}
.cn-field-err{margin:0;font-size:12px;color:var(--bad)}
.cn-check{display:flex;align-items:center;gap:8px;color:var(--hi);font-size:13px}
.cn-res{display:flex;align-items:flex-start;gap:8px;padding:8px 10px;border-radius:var(--r-sm);background:var(--s2);
  color:var(--hi);font-size:12.5px;line-height:1.45}
.cn-res .ico{flex:none;margin-top:2px}
.cn-res--ok .ico{color:var(--ok)}
.cn-res--err .ico{color:var(--bad)}
```

- [ ] **Step 4: Тести зелені** — новий і всі CSS-охоронці:

```bash
python3 "$G" 300 2000 node --test tests/connections-css.test.mjs tests/css-guards.test.mjs tests/spaces-css.test.mjs
```
Якщо `css-guards` скаржиться (напр. на кейфрейми, висоти, `--lo` як колір тексту) — виправити правило, не тест.

- [ ] **Step 5: Commit.**

```bash
git add app/styles.css tests/connections-css.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(connections): стилі екрана «Підключення» і охоронець класів

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Входи в чистих модулях (смуга, дропдаун, ⌘K, голова «Задач»)

**Files:**
- Modify: `app/bar-model.js` (гілка `if (s.homeOpen)` ≈ 179)
- Modify: `app/shell-bar.js` (`ddSpaces` ≈ 82, `homeCrumbs` ≈ 560, `barHTML` ≈ 572)
- Modify: `app/shell-palette.js` (`spaceActions` ≈ 169)
- Modify: `app/tasks-home.js` (`newTaskBtn` ≈ 127, `homeHTML` ≈ 302)
- Test: `tests/bar-model.test.mjs`, `tests/shell-bar.test.mjs`, `tests/shell-palette.test.mjs`, `tests/tasks-home.test.mjs` (додати тести)

- [ ] **Step 1: Падаючі тести.** Перед написанням подивитись, як у кожному файлі будують стан (`S(...)`, `html(...)`, `SP()`, `SPACES`, `SPS` — допоміжні функції файлів) і писати в тому ж стилі. Додати:

`tests/bar-model.test.mjs`:
```js
test("екран «Підключення»: крихта `crumb-conn` замість `crumb-tasks`, решта складу та сама", () => {
  const conn = barModel({ ...base, homeOpen: true, homePage: "conn", taskId: "t1" });
  const tasks = barModel({ ...base, homeOpen: true, taskId: "t1" });
  assert.deepEqual(conn.zone1.map((x) => x.id), tasks.zone1.map((x) => (x.id === "crumb-tasks" ? "crumb-conn" : x.id)));
  assert.equal(conn.zone1.find((x) => x.id === "crumb-conn").labelKey, "cnTitle");
  assert.deepEqual([conn.zone2, conn.zone3], [[], []]);
});
```
(`base` — мінімальний стан задачі на початку файла.)

`tests/shell-bar.test.mjs`:
```js
test("дропдаун просторів: «Підключення…» після «Назва й колір…»", () => {
  const h = html({ space: SP(), spaces: SPACES, openDd: "space" });
  assert.match(h, /data-act="spaceedit"[\s\S]*?<\/button>\s*<button[^>]*data-act="conn"[\s\S]*?Підключення…/);
});

test("смуга на сторінці «Підключення»: плоска крихта «Підключення», «назад до задачі» лишається", () => {
  const h = html({ space: SP(), homeOpen: true, homePage: "conn", taskId: "t1" });
  assert.match(h, /crumb crumb--flat[\s\S]*?Підключення</);
  assert.doesNotMatch(h, /<span class="txt">Задачі</);
  assert.match(h, /data-act="back"/);
});
```

`tests/shell-palette.test.mjs`:
```js
test("простори: «Підключення простору «A»» для поточного; нема на самій сторінці й без поточного", () => {
  const acts = paletteActions(S({ spaces: SPS, spaceId: "a" }));
  const c = acts.find((a) => a.id === "space-conn");
  assert.deepEqual({ ...c, icon: undefined }, { id: "space-conn", group: "gGo", labelKey: "spaceConn", labelArgs: ["A"],
    icon: undefined, act: "conn" });
  assert.ok(ico(c.icon));
  assert.ok(paletteActions(S({ homeOpen: true, spaces: SPS, spaceId: "a" })).some((a) => a.id === "space-conn"),
    "на «Задачах» пункт є");
  assert.ok(!paletteActions(S({ homeOpen: true, homePage: "conn", spaces: SPS, spaceId: "a" })).some((a) => a.id === "space-conn"),
    "на самій сторінці — дія, що нічого не робить");
  assert.ok(!paletteActions(S({ spaces: SPS })).some((a) => a.id === "space-conn"), "поточний невідомий — нема");
  assert.ok(!paletteActions(S({ spaces: SPS, spaceId: "zzz" })).some((a) => a.id === "space-conn"), "поточного нема в переліку");
});
```
(Імена `S`, `SPS` з наявних тестів просторів у файлі ≈ 720–780; простір `a` має назву `A` — звірити з `SPS`.)

`tests/tasks-home.test.mjs`:
```js
test("голова простору без інтеграцій: «Підключення» поряд із «Нова задача»; простір ЛІГА — без змін", () => {
  const off = homeHTML(UI(), D_OFF());
  assert.match(off, /<div class="th-head-acts"><button class="ctl ctl--out" data-th="conn">[\s\S]*?Підключення<\/button><button class="ctl ctl--pri" data-th="newtask">/);
  const liga = homeHTML(UI(), { ...DATA, space: { name: "Liga", integrations: true } });
  assert.doesNotMatch(liga, /data-th="conn"/);
});
```
(`UI`, `D_OFF`, `DATA` — помічники файла: `D_OFF` — простір без інтеграцій, `DATA` — дані ЛІГА.)

- [ ] **Step 2: Запустити — мусять впасти.**

```bash
python3 "$G" 300 2000 node --test tests/bar-model.test.mjs tests/shell-bar.test.mjs tests/shell-palette.test.mjs tests/tasks-home.test.mjs
```

- [ ] **Step 3: Реалізувати.**

`app/bar-model.js`, гілка `if (s.homeOpen)`:
```js
  if (s.homeOpen) {
    /* Сторінка «Підключення» (етап 3a) — той самий оверлей, той самий склад смуги; міняється лише плоска крихта
       («де я»): `crumb-conn` замість `crumb-tasks`. */
    const crumb = s.homePage === "conn"
      ? { id: "crumb-conn", tier: 0, labelKey: "cnTitle" }
      : { id: "crumb-tasks", tier: 0, labelKey: "tasks" };
    const zone1 = [home, palette, ...spaceChip, crumb];
    if (s.taskId) zone1.push({ id: "back", tier: 0, label: s.taskId });
    return { zone1, zone2: [], zone3: [], error: tasksError(s) };
  }
```

`app/shell-bar.js` — `ddSpaces`, після рядка `spaceedit`:
```js
    ${ddItem({ act: "spaceedit", icon: "pencil", title: t("spaceEdit") })}
    ${ddItem({ act: "conn", icon: "sliders", title: t("cnOpen") })}</div>`;
```
`homeCrumbs`:
```js
function homeCrumbs(model) {
  const back = model.zone1.find((x) => x.id === "back");
  const conn = model.zone1.some((x) => x.id === "crumb-conn");
  const crumb = `<span class="crumb crumb--flat">${ico(conn ? "sliders" : "grid")}`
    + `<span class="txt">${esc(t(conn ? "cnTitle" : "tasks"))}</span></span>`;
  …решта без змін
```
`barHTML`: `const home = model.zone1.some((x) => x.id === "crumb-tasks" || x.id === "crumb-conn");`

`app/shell-palette.js` — `spaceActions`, перед `out.push({ id: "space-new", … })`:
```js
  /* «Підключення» поточного простору (етап 3a). Не на самій сторінці (дія, що нічого не робить) і лише коли поточний
     є в переліку: без простору нема чого підключати. `space-conn` не перетинається з `space-go-<id>`. */
  const me = cur != null && s.homePage !== "conn" ? s.spaces.find((x) => x.id === cur) : null;
  if (me) out.push({ id: "space-conn", group: "gGo", labelKey: "spaceConn", labelArgs: [me.name], icon: "sliders", act: "conn" });
```
Доповнити шапковий коментар `spaceActions` одним реченням про `space-conn`.

`app/tasks-home.js`:
```js
/** «Підключення» (етап 3a): у голові простору без інтеграцій, поряд із «Нова задача» (`data-th="conn"`). */
const connBtn = () => `<button class="ctl ctl--out" data-th="conn">${ico("sliders")}${esc(t("cnTitle"))}</button>`;
```
і в `homeHTML`:
```js
  const head = noIntegrations(data)
    ? `<div class="th-head">${h1}<div class="th-head-acts">${connBtn()}${newTaskBtn()}</div></div>` : h1;
```
Оновити коментар над рядком («Кнопки «Підключення» й «Нова задача» живуть у голові лише…»).

- [ ] **Step 4: Тести зелені + golden ЛІГА без перезйомки:**

```bash
python3 "$G" 600 3000 node --test tests/bar-model.test.mjs tests/shell-bar.test.mjs tests/shell-palette.test.mjs tests/tasks-home.test.mjs tests/legacy-golden.test.mjs tests/spaces-css.test.mjs tests/i18n-keys.test.mjs
```
Якщо впав наявний тест через нову обгортку `.th-head-acts` (точна розмітка голови) — оновити ЛИШЕ очікування розмітки голови простору без інтеграцій; тест ЛІГА-голови мусить лишитись як є. `legacy-golden` впасти не сміє — якщо падає, знайти причину в коді, а не перезнімати.

- [ ] **Step 5: Commit.**

```bash
git add app/bar-model.js app/shell-bar.js app/shell-palette.js app/tasks-home.js tests/bar-model.test.mjs tests/shell-bar.test.mjs tests/shell-palette.test.mjs tests/tasks-home.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(connections): входи — крихта, пункт дропдауна, ⌘K, кнопка в голові «Задач»

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `app.js` — сторінка `conn`, список, дії карток, оновлення після змін

**Files:**
- Modify: `app/app.js`
- Test: `tests/connections-wiring.test.mjs` (новий; текстові пінни, як `tests/spaces-wiring.test.mjs`)

- [ ] **Step 1: Падаючі пінни** `tests/connections-wiring.test.mjs` (Task 6 — перша половина; Task 7 допише свою):

```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

/** Тіло функції `name` (від `{` після сигнатури до парної `}`). */
function fn(name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `функції ${name} нема`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(open, i + 1); }
  }
  throw new Error(`немає закриття для ${name}`);
}

test("дії смуги: conn веде на сторінку, логотип — завжди на «Задачі»", () => {
  assert.match(src, /\n  conn: \(\) => enterConnections\(\),/);
  assert.match(src, /\n  home: \(\) => enterHome\(\{ page: 'tasks' \}\),/);
  assert.match(fn("wireHome"), /case 'conn': enterConnections\(\); break;/);
});

test("enterHome тримає відкриту сторінку (перемикання простору й запис модулів лишають «Підключення»)", () => {
  const b = fn("enterHome");
  assert.match(b, /page \?\? \(was \? homePage : 'tasks'\)/);
  assert.match(b, /if \(homePage === 'conn'\)[\s\S]*?loadConn\(\{ spaces \}\)/);
  assert.match(b, /if \(next !== 'conn'\) closeCnDrawer\(\{ focus: false \}\)/);
});

test("barState і paletteState несуть homePage", () => {
  assert.match(src, /homePage: homeOpen \? homePage : null,/);
  assert.match(src, /homePage: st\.homePage,/);
});

test("клавіші сторінки «Задачі» на «Підключенні» не діють", () => {
  assert.match(src, /if \(!homeOpen \|\| ev\.isComposing \|\| paletteOverlay \|\| document\.querySelector\('\.cv-ask-scrim'\)\) return;\n  if \(homePage === 'conn'\) return;/);
});

test("перечитування при поверненні у вікно: на «Підключенні» — loadConn", () => {
  assert.match(fn("refreshHomeOnReturn"), /homePage === 'conn' \? loadConn\(\) : loadHome\(\)/);
});

test("запити сторінки несуть явний space (агент міг перемкнути активний простір)", () => {
  assert.match(fn("loadConn"), /api\(`\/api\/modules\?space=\$\{encodeURIComponent\(sp\.id\)\}`\)/);
  assert.match(fn("connCheck"), /postForm\('\/api\/module-check', \{ space: connState\.spaceId, id: e\.id \}\)/);
  assert.match(fn("connDisable"), /postForm\('\/api\/module-disable', \{ space: connState\.spaceId, id: e\.id \}\)/);
});

test("після вимкнення — afterModulesChange (= afterSpaceChange: смуга, рамка, інспектор)", () => {
  assert.match(fn("connDisable"), /await afterModulesChange\(\);/);
  assert.match(fn("afterModulesChange"), /await afterSpaceChange\(\);/);
});

test("фокус після перемальовки повертається і на кнопки карток (data-cn + data-id)", () => {
  assert.match(fn("focusKey"), /a\.dataset\.cn/);
});
```

- [ ] **Step 2: Запустити — мусить впасти.** `python3 "$G" 120 1500 node --test tests/connections-wiring.test.mjs`

- [ ] **Step 3: Реалізувати в `app/app.js`.**

3.1 Імпорти (біля інших):
```js
import { connPageHTML, drawerHTML, modName, roleTitle } from './connections-view.js';
import {
  disableConsequences, formFields, formPatch, initialForm, isDirty, missingRequired, refusalView, roleHolders,
  verdictText, writePayload,
} from './connections-model.js';
```
(`drawerHTML`, `formFields` й решта знадобляться в Task 7 — імпортувати зараз, щоб Task 7 не правив імпорт; якщо лінтер/тест скаржиться на невикористаний імпорт — перенести в Task 7.)

3.2 Після `let homeOpen = false;` (≈174):
```js
/* Сторінка оверлею `#tasks-home`: `tasks` (список задач / привітання) чи `conn` («Підключення», етап 3a). Один
   оверлей на всі екрани поза задачею: вхід, вихід, чистий перегляд і палітра в стані `homeOpen` — спільні. */
let homePage = 'tasks';
/* Стан сторінки «Підключення»: простір, чий список показано (знімок на момент запиту — кожен запис іде САМЕ туди),
   записи `GET /api/modules` (`null` — вантажиться), збій читання і дії в польоті (id → 'check'|'disable'). `seq`
   відкидає відповіді, що прийшли після виходу зі сторінки чи після новішого запиту. */
const connState = { spaceId: null, list: null, failed: null, busy: new Map(), seq: 0 };
/* Свіжий вхід на сторінку: після першого списку фокус — на першу кнопку першої картки. */
let connFocusPending = false;
/* Бічна панель «Підключення» (Task 7): `null` — закрита. Оголошено ТУТ, серед стану модуля, а не біля функцій панелі:
   `enterHome` (його кличе вже перший `render()`) читає її через `closeCnDrawer`, і `let` нижче за місцем виклику дав би
   TDZ-помилку на старті. */
let cnDrawer = null;   // {id, entry, mode: 'enable'|'edit', fields, init, form, busy, result, errors, spaceId, opener}
```

3.3 `barState()` — після `homeOpen,`: `homePage: homeOpen ? homePage : null,`. `paletteState()` — після `homeOpen: st.homeOpen,`: `homePage: st.homePage,`.

3.4 `BAR_ACTIONS`: `home: () => enterHome({ page: 'tasks' }),` (коментар доповнити: «логотип з «Підключення» теж веде на «Задачі»») і після `spaceedit`:
```js
  /* «Підключення» поточного простору (етап 3a): пункт дропдауна фішки, ⌘K і кнопка в голові «Задач». */
  conn: () => enterConnections(),
```

3.5 `focusKey(a)` — перед `if (a.dataset.th)`:
```js
  if (a.dataset.cn) {
    return `[data-cn="${a.dataset.cn}"]${a.dataset.id != null ? `[data-id="${CSS.escape(a.dataset.id)}"]` : ''}`;
  }
```

3.6 `paintHome()` — рядок `keepFocus(...)`:
```js
  keepFocus(el, () => {
    el.innerHTML = needsWelcome(spacesResp) ? welcomeHTML()
      : homePage === 'conn' ? connPageHTML(connView()) : homeHTML(homeView(), homeData);
  });
```

3.7 `enterHome` — нова сигнатура й гілка:
```js
function enterHome({ spaces = true, page } = {}) {
  const was = homeOpen;
  /* Сторінка: явна (`home` — «Задачі», `conn` — «Підключення»), інакше відкрита лишається відкритою (перемикання
     простору й запис модулів кличуть `enterHome` через `afterSpaceChange`, і людина лишається там, де була). */
  const next = page ?? (was ? homePage : 'tasks');
  if (next !== 'conn') closeCnDrawer({ focus: false });
  const fresh = !was || next !== homePage;
  homePage = next;
  if (cleanView) toggleClean(false);
  homeComposing = false; homePaintPending = false;
  homeOpen = true;
  openDd = null;
  document.body.classList.add('home-open');
  if (!was) homeUi.q = '';
  const el = ensureHome();
  el.hidden = false;
  paintBar();
  if (homePage === 'conn') {
    if (fresh) { connState.list = null; connState.failed = null; connFocusPending = true; }
    paintHome();
    loadConn({ spaces });
    return;
  }
  …далі БЕЗ змін (homeData, paintHome, фокус на #th-q / spacenew, loadHome)…
}
```
(Зберегти наявні коментарі функції; лише вставити нові рядки.)

3.8 `leaveHome()` — першим рядком тіла: `closeCnDrawer({ focus: false });`.

3.9 `refreshHomeOnReturn()` — останній рядок `loadHome();` → `if (homePage === 'conn') loadConn(); else loadHome();` — і щоб пін зловив, записати одним виразом: `homePage === 'conn' ? loadConn() : loadHome();`.

3.10 Клавіатурний обробник екрана (`document.addEventListener('keydown', …)` з `if (!homeOpen || ev.isComposing || …) return;` ≈ 2494): ОДРАЗУ наступним рядком (без коментаря між ними — на суміжність дивиться пін) `  if (homePage === 'conn') return;   // «Підключення»: клавіші списку задач не діють; Esc панелі — свій обробник`.

3.11 `wireHome(el)` — на початку обробника `click` (після рядка з `a`):
```js
    const c = ev.target.closest('[data-cn]');
    if (c) { connAction(c.dataset.cn, c.dataset.id); return; }
```
і в `switch`: `case 'conn': enterConnections(); break;`.

3.12 Нові функції — блоком одразу після `wireHome` (коментар-шапка розділу «── сторінка «Підключення» (етап 3a) ──»):
```js
const connOpen = () => homeOpen && homePage === 'conn';
const connView = () => ({ space: currentSpace(spacesResp), list: connState.list, failed: connState.failed, busy: connState.busy });

/** Вхід на «Підключення» поточного простору. Без простору входів нема (шар вимкнено, привітання). */
function enterConnections() {
  if (!currentSpace(spacesResp)) return;
  enterHome({ page: 'conn' });
}

/**
 * Список модулів поточного простору. `spaces: false` — перелік просторів щойно перечитано (`afterSpaceChange`).
 * Простору не стало (вилучили руками чи агентом) — на «Задачі»: там і лікування висячого `current`, і привітання.
 * Інший простір, ніж показаний (перемкнули фішкою чи агент), — спершу «вантажу», а не чужі картки під новою назвою.
 */
async function loadConn({ spaces = true } = {}) {
  const seq = ++connState.seq;
  if (spaces) {
    await loadSpaces();
    if (seq !== connState.seq || !connOpen()) return;
    paintBar();
  }
  const sp = currentSpace(spacesResp);
  if (!sp) { enterHome({ page: 'tasks' }); return; }
  if (sp.id !== connState.spaceId) {
    connState.spaceId = sp.id; connState.list = null; connState.failed = null; connState.busy.clear();
    paintHome();
  }
  try {
    const r = await api(`/api/modules?space=${encodeURIComponent(sp.id)}`);
    if (seq !== connState.seq || !connOpen()) return;
    connState.list = Array.isArray(r?.modules) ? r.modules : [];
    connState.failed = null;
  } catch (e) {
    if (seq !== connState.seq || !connOpen()) return;
    connState.failed = { code: e?.code ?? null, message: String(e?.message || e) };
  }
  paintHome();
  if (connFocusPending) {
    connFocusPending = false;
    homeNode()?.querySelector('.cn-card [data-cn], [data-cn="retry"]')?.focus({ preventScroll: true });
  }
}

/** Клік по кнопці картки чи помилки сторінки (`data-cn`). Дія над модулем, що вже в польоті, — ігнор. */
function connAction(act, id) {
  if (act === 'retry') { loadConn(); return; }
  const e = (connState.list || []).find((x) => x.id === id);
  if (!e || connState.busy.has(id)) return;
  if (act === 'enable') openCnDrawer(e, 'enable');
  else if (act === 'configure') openCnDrawer(e, 'edit');
  else if (act === 'check') connCheck(e);
  else if (act === 'disable') connDisable(e);
}

/** «Перевірити» на картці: вердикт міняє лише `status` модуля — перечитуємо сторінку. */
async function connCheck(e) {
  connState.busy.set(e.id, 'check'); paintHome();
  try { await postForm('/api/module-check', { space: connState.spaceId, id: e.id }); }
  catch (err) { const r = refusalView(err); tell([t(r.key), r.detail].filter(Boolean).join('\n\n')); }
  finally { connState.busy.delete(e.id); }
  await loadConn();
}

/** «Вимкнути»: питання з наслідками для ролей, які модуль зараз виконує; далі — як після будь-якої зміни модулів. */
async function connDisable(e) {
  const sp = currentSpace(spacesResp);
  const lines = disableConsequences(e, sp).map((c) => (c.kind === 'legacy'
    ? t('cnDisableLegacy', roleTitle(c.role))
    : t('cnDisableNone', roleTitle(c.role), c.noneKey ? t(c.noneKey) : '')));
  if (!(await askYesNo([t('cnDisableAsk', modName(e)), ...lines].join('\n\n'), { yes: t('cnDisable'), danger: true }))) return;
  connState.busy.set(e.id, 'disable'); paintHome();
  try { await postForm('/api/module-disable', { space: connState.spaceId, id: e.id }); }
  catch (err) {
    connState.busy.delete(e.id); paintHome();
    const r = refusalView(err); tell([t(r.key), r.detail].filter(Boolean).join('\n\n'));
    return;
  }
  connState.busy.delete(e.id);
  await afterModulesChange();
}

/**
 * Модулі змінились (вмикання, налаштування, вимкнення). Постачальник ролі й його налаштування — частина простору:
 * смуга (кнопки публікації), рамка (адаптер коментарів вбудовується в сторінку при віддачі) й інспектор (токени)
 * мусять побачити нове. Тому той самий шлях, що й зміна простору; сторінка лишається «Підключенням», бо `enterHome`
 * (його кличе `afterSpaceChange`) тримає відкриту сторінку. Пер-задачне (пакет тюнера) перечитується з диска.
 */
async function afterModulesChange() {
  await afterSpaceChange();
}
```

3.13 Заглушки для Task 7, щоб файл парсився й пінни Task 6 проходили: `closeCnDrawer` і `openCnDrawer` з'являться в Task 7; у Task 6 додати мінімальні версії (Task 7 їх ЗАМІНИТЬ повністю):
```js
/* Бічна панель — Task 7. */
function closeCnDrawer() {}
function openCnDrawer() {}
```

`askYesNo` і `tell` уже імпортовані з `./ask.js` — перевірити імпорт.

- [ ] **Step 4: Тести зелені** — пінни, наявні пінни просторів, усі юніти:

```bash
python3 "$G" 300 2000 node --test tests/connections-wiring.test.mjs tests/spaces-wiring.test.mjs tests/js-parses.test.mjs
python3 "$G" 900 4000 npm test 2>&1 | tail -20
```
Під час повного прогону файли не правити.

- [ ] **Step 5: Commit.**

```bash
git add app/app.js tests/connections-wiring.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(connections): сторінка «Підключення» в оверлеї — список, перевірка, вимкнення

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `app.js` — бічна панель: підключення, налаштування, заміна, секрети

**Files:**
- Modify: `app/app.js` (замінити заглушки Task 6 на справжні функції; Esc-обробник; `switchLang`)
- Test: `tests/connections-wiring.test.mjs` (дописати)

> **Поправки після ревʼю Task 3 — обовʼязкові для цієї задачі:**
> - `cnDrawer.busy` — не `true`, а `'save'` (запис у `cnSubmit`) чи `'check'` (`cnDrawerCheck`): розмітка каже «Зберігаю й перевіряю…» лише для `'save'`, а для `'check'` — «Перевіряю…» на кнопці «Перевірити». Скрізь, де план пише `mine.busy = true`, — відповідне значення; `busy = false` лишається.
> - кнопка «Стерти» має СТАЛИЙ підпис (стан — лише `aria-pressed` і видима примітка `data-cn-erase-note`): `toggleCnErase` НЕ міняє `textContent`, лише `aria-pressed` і `hidden` примітки, далі `syncCnDrawer()`.
> - (після фікса Task 3, `46b1613`) примітка «буде стерто…» має `id` (`cn-f-<i>-erase`) і входить в `aria-describedby` поля пароля ЛИШЕ коли секрет позначено до стирання: `toggleCnErase` мусить ще й додати/прибрати цей id в `aria-describedby` відповідного `[data-cn-field="<key>"]` (інші id у атрибуті — `-state`, `-err` — лишаються). Пін на це — у `tests/connections-wiring.test.mjs`.
> - `drawerHTML` читає `d.busy` як `'save' | 'check' | false`; кнопка закриття не вимикається — закриття під час запиту гасить сам `requestCloseCnDrawer` (`if (!cnDrawer || cnDrawer.busy) return;`).

- [ ] **Step 1: Падаючі пінни** — дописати в `tests/connections-wiring.test.mjs`:

```js
test("панель: запис іде в простір, відкритий у панелі; заміна — з replace після підтвердження", () => {
  const b = fn("cnSubmit");
  assert.match(b, /missingRequired\(cnDrawer\.fields, cur\)/);
  assert.match(b, /roleHolders\(cnDrawer\.entry, connState\.list\)/);
  assert.match(b, /t\('cnReplaceAsk', /);
  assert.match(b, /askYesNo\(q, \{ yes: t\('cnReplace'\) \}\)/);
  assert.match(b, /writePayload\(mine\.spaceId, mine\.id, patch, replace\)/);
  assert.match(b, /postForm\(mine\.mode === 'enable' \? '\/api\/module-enable' : '\/api\/module-settings', body\)/);
  assert.match(b, /await afterModulesChange\(\);/);
});

test("панель: секрети НЕ лишаються у формі після відповіді — у стані лише значення без секретів", () => {
  const b = fn("cnSubmit");
  assert.match(b, /mine\.form = \{ values: cur\.values, secrets: \{\}, erase: cur\.erase \};/);
});

test("панель: перевірка в панелі — module-check простору панелі", () => {
  assert.match(fn("cnDrawerCheck"), /postForm\('\/api\/module-check', \{ space: mine\.spaceId, id: mine\.id \}\)/);
});

test("панель: Esc — запит закриття (з питанням при незбереженому), не під діалогом і не під палітрою", () => {
  assert.match(src, /ev\.key === 'Escape' && cnDrawer && !paletteOverlay && !document\.querySelector\('\.cv-ask-scrim'\)/);
  assert.match(fn("requestCloseCnDrawer"), /askYesNo\(t\('cnDiscardAsk'\)/);
});

test("мова: відкрита панель перемальовується разом з екраном", () => {
  assert.match(fn("switchLang"), /if \(cnDrawer && !cnDrawer\.busy\) \{ cnDrawer\.form = \{ \.\.\.readCnForm\(cnDrawerNode\(\)\), secrets: \{\} \}; paintCnDrawer\(\); \}/);
});
```

- [ ] **Step 2: Запустити — мусять впасти.** `python3 "$G" 120 1500 node --test tests/connections-wiring.test.mjs`

- [ ] **Step 3: Реалізувати.** Видалити заглушки `closeCnDrawer`/`openCnDrawer` з Task 6 і додати після блоку Task 6:

```js
/* ── бічна панель «Підключення» (`#cn-drawer`) ───────────────────────────────────────────────────────────
   Окремий вузол поза `#tasks-home`: перемальовка сторінки (перечитування списку, «Перевіряю…» на картці) не
   сміє стирати введене в полях. Поки панель відкрита, значення полів живуть у DOM; `cnDrawer.form` — знімок для
   перемальовки самої панелі (зайнятість, результат, мова). ⛔ Секрет у знімку не тримаємо й у розмітку не пишемо:
   після будь-якої відповіді сервера поля паролів порожні. Стан `cnDrawer` оголошено вгорі файла (Task 6). */

function cnDrawerNode() {
  let el = document.getElementById('cn-drawer');
  if (el) return el;
  el = document.createElement('aside');
  el.id = 'cn-drawer';
  el.className = 'cn-drawer';
  el.hidden = true;
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-labelledby', 'cn-dr-title');
  document.body.appendChild(el);
  wireCnDrawer(el);
  return el;
}

/** Поточні значення панелі з DOM: `{values, secrets, erase}` (мапи — `Object.fromEntries`: ключ `__proto__` — поле). */
function readCnForm(el) {
  const values = [];
  const secrets = [];
  for (const n of el.querySelectorAll('[data-cn-field]')) {
    const k = n.dataset.cnField;
    if (n.dataset.type === 'secret') secrets.push([k, n.value]);
    else if (n.dataset.type === 'bool') values.push([k, n.checked]);
    else values.push([k, n.value]);
  }
  const erase = [...el.querySelectorAll('[data-cn-dr="erase"][aria-pressed="true"]')].map((b) => b.dataset.key);
  return { values: Object.fromEntries(values), secrets: Object.fromEntries(secrets), erase };
}

function paintCnDrawer() {
  const el = cnDrawerNode();
  if (!cnDrawer) { el.hidden = true; el.innerHTML = ''; return; }
  const sp = currentSpace(spacesResp);
  el.innerHTML = drawerHTML({ ...cnDrawer, spaceName: sp && sp.id === cnDrawer.spaceId ? sp.name : cnDrawer.spaceId });
  el.hidden = false;
  syncCnDrawer();
}

/** Кнопки за станом форми: «Зберегти» вимкнена без змін (у правці), «Перевірити» — зі змінами (перевіряє збережене). */
function syncCnDrawer() {
  if (!cnDrawer) return;
  const el = cnDrawerNode();
  const dirty = isDirty(formPatch(cnDrawer.fields, cnDrawer.init, readCnForm(el)));
  const submit = el.querySelector('[data-cn-dr="submit"]');
  if (submit) submit.disabled = cnDrawer.busy || (cnDrawer.mode === 'edit' && !dirty);
  const check = el.querySelector('[data-cn-dr="check"]');
  if (check) { check.disabled = cnDrawer.busy || dirty; check.title = dirty ? t('cnCheckSavedFirst') : ''; }
}

function openCnDrawer(e, mode) {
  const fields = formFields(e);
  const init = initialForm(fields);
  cnDrawer = { id: e.id, entry: e, mode, fields, init, form: init, busy: false, result: null, errors: {},
    spaceId: connState.spaceId, opener: { act: mode === 'enable' ? 'enable' : 'configure', id: e.id } };
  paintCnDrawer();
  const el = cnDrawerNode();
  (el.querySelector('[data-cn-field]') ?? el.querySelector('[data-cn-dr="submit"]'))?.focus({ preventScroll: true });
}

/** Закрити без питань. Фокус — на кнопку картки, що відкрила панель (після запису дія могла змінитись: «Підключити» →
 *  «Налаштувати», тому запасний варіант — будь-яка кнопка тієї ж картки). */
function closeCnDrawer({ focus = true } = {}) {
  if (!cnDrawer) return;
  const op = cnDrawer.opener;
  cnDrawer = null;
  paintCnDrawer();
  if (!focus || !op) return;
  const home = homeNode();
  const id = CSS.escape(op.id);
  (home?.querySelector(`[data-cn="${op.act}"][data-id="${id}"]`) ?? home?.querySelector(`[data-cn][data-id="${id}"]`))
    ?.focus({ preventScroll: true });
}

/** Хрестик і Esc: з незбереженими змінами — спершу питання. Під час запиту панель не закривається. */
async function requestCloseCnDrawer() {
  if (!cnDrawer || cnDrawer.busy) return;
  const mine = cnDrawer;
  const dirty = isDirty(formPatch(mine.fields, mine.init, readCnForm(cnDrawerNode())));
  if (dirty && !(await askYesNo(t('cnDiscardAsk'), { yes: t('cnDiscard'), danger: true }))) return;
  if (cnDrawer === mine) closeCnDrawer();
}

/** «Стерти» секрет — без перемальовки (інакше зникли б інші введені секрети): кнопка, примітка, стан кнопок. */
function toggleCnErase(btn) {
  const on = btn.getAttribute('aria-pressed') !== 'true';
  btn.setAttribute('aria-pressed', String(on));
  btn.textContent = t(on ? 'cnEraseUndo' : 'cnErase');
  const note = cnDrawerNode().querySelector(`[data-cn-erase-note="${CSS.escape(btn.dataset.key)}"]`);
  if (note) note.hidden = !on;
  syncCnDrawer();
}

/**
 * «Підключити» / «Зберегти». Обовʼязкові — до запиту. Підключення модуля, чиї ролі хтось тримає (зокрема неявний
 * `static-publish`), — спершу питання «Замінити?», далі `replace: true` (сервер міняє постачальника одним записом).
 * Запис іде в простір, відкритий у панелі (`spaceId`), а не в активний зараз. Вердикт `ok` — панель закривається,
 * тост; `ok: false` — стан УЖЕ записано (так працює API), панель лишається з причиною й переходить у режим правки;
 * HTTP-відмова — нічого не збережено, причина в панелі.
 */
async function cnSubmit() {
  if (!cnDrawer || cnDrawer.busy) return;
  const el = cnDrawerNode();
  const cur = readCnForm(el);
  const miss = missingRequired(cnDrawer.fields, cur);
  if (miss.length) {
    cnDrawer.form = { values: cur.values, secrets: {}, erase: cur.erase };
    cnDrawer.errors = Object.fromEntries(miss.map((k) => [k, 'cnFieldRequired']));
    cnDrawer.result = null;
    paintCnDrawer();
    cnDrawerNode().querySelector('[aria-invalid="true"]')?.focus({ preventScroll: true });
    return;
  }
  const patch = formPatch(cnDrawer.fields, cnDrawer.init, cur);
  if (cnDrawer.mode === 'edit' && !isDirty(patch)) return;
  const mine = cnDrawer;
  let replace = false;
  if (mine.mode === 'enable') {
    const holders = roleHolders(cnDrawer.entry, connState.list);
    if (holders.length) {
      const shared = (mine.entry.roles || []).filter((r) => holders.some((h) => (h.roles || []).includes(r)));
      const q = t('cnReplaceAsk', roleTitle(shared[0]), holders.map(modName).join(', '), modName(mine.entry));
      if (!(await askYesNo(q, { yes: t('cnReplace') }))) return;
      if (cnDrawer !== mine) return;
      replace = true;
    }
  }
  const body = writePayload(mine.spaceId, mine.id, patch, replace);
  mine.form = { values: cur.values, secrets: {}, erase: cur.erase };
  mine.errors = {}; mine.result = null; mine.busy = true;
  paintCnDrawer();
  let r;
  try {
    r = await postForm(mine.mode === 'enable' ? '/api/module-enable' : '/api/module-settings', body);
  } catch (err) {
    if (cnDrawer !== mine) return;
    mine.busy = false; mine.result = { kind: 'refused', ...refusalView(err) };
    paintCnDrawer();
    return;
  }
  const name = modName(mine.entry);
  if (r?.check?.ok === true) {
    if (cnDrawer === mine) closeCnDrawer();
    toast(t(mine.mode === 'enable' ? 'cnToastEnabled' : 'cnToastSaved', name));
  } else if (cnDrawer === mine) {
    const entry = r?.module ?? mine.entry;
    const fields = formFields(entry);
    const init = initialForm(fields);
    cnDrawer = { ...mine, entry, mode: 'edit', fields, init, form: init, busy: false,
      result: { kind: 'failed', ...verdictText(r?.check) }, opener: { act: 'configure', id: mine.id } };
    paintCnDrawer();
  }
  await afterModulesChange();
}

/** «Перевірити» в панелі — по збереженому (зі змінами кнопка вимкнена): вердикт у панелі, сторінка перечитується. */
async function cnDrawerCheck() {
  if (!cnDrawer || cnDrawer.busy) return;
  const mine = cnDrawer;
  mine.form = { ...readCnForm(cnDrawerNode()), secrets: {} };
  mine.busy = true; mine.result = null;
  paintCnDrawer();
  try {
    const r = await postForm('/api/module-check', { space: mine.spaceId, id: mine.id });
    if (cnDrawer !== mine) return;
    mine.result = { kind: r?.check?.ok === true ? 'ok' : 'check-failed', ...verdictText(r?.check) };
  } catch (err) {
    if (cnDrawer !== mine) return;
    mine.result = { kind: 'refused', ...refusalView(err) };
  } finally {
    mine.busy = false;
  }
  if (cnDrawer === mine) paintCnDrawer();
  loadConn();
}

function wireCnDrawer(el) {
  el.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-cn-dr]');
    if (!b || b.disabled) return;
    const a = b.dataset.cnDr;
    if (a === 'close') requestCloseCnDrawer();
    else if (a === 'check') cnDrawerCheck();
    else if (a === 'erase') toggleCnErase(b);
  });
  el.addEventListener('submit', (ev) => { ev.preventDefault(); cnSubmit(); });
  el.addEventListener('input', () => syncCnDrawer());
  el.addEventListener('change', () => syncCnDrawer());
}

/* Esc панелі: лише коли над нею нема діалогу питання й палітри (Esc тих — їхній). */
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && cnDrawer && !paletteOverlay && !document.querySelector('.cv-ask-scrim')) {
    ev.preventDefault();
    requestCloseCnDrawer();
  }
});
```

`switchLang(v)` — після `if (homeOpen) paintHome();`:
```js
  /* Відкрита бічна панель «Підключення» — теж окремий вузол. Введені секрети при цьому зникають (у розмітку вони не
     пишуться ніколи) — свідома ціна. */
  if (cnDrawer && !cnDrawer.busy) { cnDrawer.form = { ...readCnForm(cnDrawerNode()), secrets: {} }; paintCnDrawer(); }
```

⚠️ Перевірити: (а) `paletteOverlay` оголошено ДО цього обробника (модульна змінна — так, але звернення в обробнику відбувається під час події, тож порядок оголошення байдужий, поки це `let` модуля); (б) в `ask.js` діалог `.cv-ask-scrim` сам обробляє Esc — наш обробник його пропускає; (в) клавіатурний обробник екрана «Задачі» на `conn` повертається одразу (Task 6) — подвійної реакції нема.

- [ ] **Step 4: Ручна перевірка в браузері** (Playwright-скрипт у скретчпаді або живий тест Task 8 пізніше). Тут — юніти й пінни:

```bash
python3 "$G" 300 2000 node --test tests/connections-wiring.test.mjs tests/js-parses.test.mjs tests/i18n-keys.test.mjs
python3 "$G" 900 4000 npm test 2>&1 | tail -20
```

- [ ] **Step 5: Мутації** (кожну відкотити): прибрати `replace = true;` → пін `writePayload(..., replace)` лишиться зеленим, тому ЦЮ мутацію доводить живий тест Task 8 (записати в звіт задачі «доводиться в Task 8»); прибрати `secrets: {}` у `mine.form` → червоніє пін секретів.

- [ ] **Step 6: Commit.**

```bash
git add app/app.js tests/connections-wiring.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(connections): бічна панель — підключення, налаштування, заміна в ролі, секрети

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Живий тест і тестовий модуль `memo-publish`

**Files:**
- Create: `tests/fixtures/modules-conn/memo-publish/module.json`, `tests/fixtures/modules-conn/memo-publish/server.py`
- Create: `tests/live/connections.test.mjs`

- [ ] **Step 1: Модуль-фікстура.** `tests/fixtures/modules-conn/memo-publish/module.json`:

```json
{"api": 1, "id": "memo-publish", "name": "Memo publish (test)", "version": "1.0.0",
 "roles": ["publish"],
 "settings": [
   {"key": "note", "type": "text", "label": "Note (test)", "required": true},
   {"key": "token", "type": "secret", "label": "Token (test)"}
 ]}
```

`tests/fixtures/modules-conn/memo-publish/server.py`:
```python
"""Тестовий модуль ролі `publish` для живого тесту екрана «Підключення»: перевірка ЛОКАЛЬНА (жодної мережі),
секрет у відповідь не потрапляє. Публікувати живий тест не публікує — `publish` лише відмовляє."""


def check(ctx):
    note = ctx['settings'].get('note', '')
    if note == 'fail':
        return {'ok': False, 'error': 'memo-says-no', 'detail': 'note is fail'}
    return {'ok': True, 'detail': 'memo ok'}


def publish(ctx, built, *args, **kwargs):
    raise ctx['ModuleError']('module-error', message='memo-publish does not publish')
```

Звірити з `tests/fixtures/modules/memo-comments/server.py` і з тим, як ядро передає `ModuleError` у `ctx` (`ctx['ModuleError']` — так у фікстурі `bad-folder` у `tests/test_modules_api.py`). Імʼя `client` не потрібне (роль `publish`).

- [ ] **Step 2: Живий тест** `tests/live/connections.test.mjs` (стиль, прилади й ізоляція — як у `tests/live/modules.test.mjs`; `PORT_BASE = 13400` — вільна смуга, перевірити `tests/live-ports.test.mjs`):

```js
/**
 * Екран «Підключення» (Deai 0.5.0, етап 3a) — живе проведення: справжній сервер в ізольованій «машині» (тимчасові
 * `HOME`/`DEAI_HOME`), справжній Chromium. Модуль-фікстура `memo-publish` (`tests/fixtures/modules-conn`, через
 * тестовий шов `DEAI_EXTRA_MODULES`) — роль `publish` з ЛОКАЛЬНОЮ перевіркою: заміна постачальника перевіряється без
 * жодної мережі. Vercel і Supabase тут НЕ вмикаються — їхній `check` ходить у мережу з процесу сервера.
 *
 * Мапа «сценарій → запобіжник» (прибери — подивись, чи червоніє):
 *   1 (вхід і картки)   — пункт `conn` у `ddSpaces`, `BAR_ACTIONS.conn`, сторінка `conn` у `paintHome`.
 *   2 (підключення)     — `cnSubmit` → `module-enable` з `space`; вердикт ok → бейдж «Підключено».
 *   3 (заміна)          — `roleHolders` + питання + `replace: true`; сервер `_holders` під локом.
 *   4 (секрет)          — поле пароля без `value`, `secrets: {}` у знімку форми; `set: true` у списку.
 *   5 (вимкнення, Esc)  — `connDisable` + `afterModulesChange`; Esc-обробник панелі.
 */
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 13400;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "modules-conn");
const SECRET = "live-S3cret-Жовтень-7";
const MOCKUP = "<!doctype html><html><body><h1>Макет</h1></body></html>";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

const isLocal = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["127.0.0.1", "localhost"].includes(x.hostname);
};

async function boot(t) {
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE,
    env: { DEAI_EXTRA_MODULES: MODULES_DIR },
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }],
  });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const outside = [];
  const bodies = [];
  context.on("request", (r) => { if (!isLocal(r.url())) outside.push(r.url()); });
  context.on("response", async (r) => {
    if (r.url().includes("/api/")) { try { bodies.push(await r.text()); } catch {} }
  });
  await context.route((u) => !isLocal(u.href), (route) => route.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await page.waitForSelector("#bar .space-chip", { timeout: 15000 });
  return { ...server, page, outside, bodies, errors, spacePath: server.spaces[0].path };
}

const badge = (page, id) => page.locator(`.cn-card[data-id="${id}"] .cn-badge`).getAttribute("class");
const waitBadge = (page, id, kind) => page.waitForSelector(`.cn-card[data-id="${id}"] .cn-badge--${kind}`, { timeout: 15000 });
const spaceJson = (p) => JSON.parse(readFileSync(path.join(p, "space.json"), "utf8"));

async function openConnections(page) {
  await page.click('#bar [data-dd="space"]');
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.cn-card[data-id="static-publish"]', { timeout: 15000 });
}

test("вхід із дропдауна, секції за ролями, неявний static-publish «типово», крихта «Підключення»", async (t) => {
  const { page, outside, errors } = await boot(t);
  await openConnections(page);
  const titles = await page.locator(".cn-sec-h").allTextContents();
  assert.deepEqual(titles.slice(0, 3), ["Публікація", "Командні коментарі", "Токени дизайн-системи"]);
  assert.match(await page.locator('.cn-card[data-id="static-publish"]').textContent(), /типово/);
  assert.match(await badge(page, "css-tokens"), /cn-badge--off/);
  assert.match(await page.locator("#bar .crumb--flat").textContent(), /Підключення/);
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.cn ?? null) !== null, true, "фокус на кнопці картки");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("css-tokens: «Підключити» з файлом простору → «Підключено»; обовʼязкове порожнє — помилка без запиту", async (t) => {
  const { page, spacePath, errors } = await boot(t);
  writeFileSync(path.join(spacePath, "ds.css"), ":root{--c-a:#123456;--gap:4px}");
  await openConnections(page);
  await page.click('[data-cn="enable"][data-id="css-tokens"]');
  await page.waitForSelector("#cn-drawer:not([hidden]) [data-cn-field=\"file\"]");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector('#cn-drawer [aria-invalid="true"]');
  assert.equal(spaceJson(spacePath).modules, undefined, "порожнє обовʼязкове — запиту не було");
  await page.fill('#cn-drawer [data-cn-field="file"]', "{space}/ds.css");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "css-tokens", "ok");
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "ok — панель закрилась");
  assert.deepEqual(spaceJson(spacePath).modules["css-tokens"], { enabled: true, settings: { file: "{space}/ds.css" } });
  assert.deepEqual(errors, []);
});

test("заміна публікації: питання → replace → static-publish вимкнено, memo-publish підключено; секрет ніде не світиться", async (t) => {
  const { page, url, spacePath, bodies, outside, errors } = await boot(t);
  await openConnections(page);
  await page.click('[data-cn="enable"][data-id="memo-publish"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "hello");
  await page.fill('#cn-drawer [data-cn-field="token"]', SECRET);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /Публікація в теку/);
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await waitBadge(page, "memo-publish", "ok");
  await waitBadge(page, "static-publish", "off");
  const mods = spaceJson(spacePath).modules;
  assert.equal(mods["static-publish"].enabled, false);
  assert.equal(mods["memo-publish"].enabled, true);
  assert.match(await page.locator(".cn-sec").first().textContent(), /Зараз: Memo publish \(test\)/);
  const list = await (await fetch(`${url}/api/modules?space=studio`)).json();
  const tok = list.modules.find((m) => m.id === "memo-publish").settings.find((s) => s.key === "token");
  assert.deepEqual(tok, { key: "token", type: "secret", label: "Token (test)", required: false, set: true });
  assert.ok(!(await page.content()).includes(SECRET), "секрет у DOM після збереження");
  assert.ok(!bodies.some((b) => b.includes(SECRET)), "секрет у відповіді API");
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
});

test("відмова від заміни лишає все як було; вимкнення через питання; Esc закриває панель", async (t) => {
  const { page, spacePath, errors } = await boot(t);
  await openConnections(page);
  await page.click('[data-cn="enable"][data-id="memo-publish"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "x");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(spaceJson(spacePath).modules, undefined, "скасування — нічого не записано");
  assert.equal(await page.locator("#cn-drawer").isVisible(), true, "панель лишилась");
  await page.keyboard.press("Escape");                       // незбережене → питання
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  await page.click('[data-cn="disable"][data-id="static-publish"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /кнопки публікації в смузі нема/);
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await waitBadge(page, "static-publish", "off");
  assert.equal(spaceJson(spacePath).modules["static-publish"].enabled, false);
  assert.match(await page.locator(".cn-sec").first().textContent(), /Зараз: нікого/);
  assert.deepEqual(errors, []);
});

test("перевірка, що каже «ні»: панель лишається з «Збережено, але перевірка не пройшла» і причиною", async (t) => {
  const { page, errors } = await boot(t);
  await openConnections(page);
  await page.click('[data-cn="enable"][data-id="memo-publish"]');
  await page.fill('#cn-drawer [data-cn-field="note"]', "fail");
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.click('.cv-ask-scrim button[data-a="ok"]');
  await page.waitForSelector("#cn-drawer .cn-res--err");
  const txt = await page.locator("#cn-drawer .cn-res--err").textContent();
  assert.match(txt, /Збережено, але перевірка не пройшла/);
  assert.match(txt, /memo-says-no — note is fail/);
  assert.match(await page.locator('#cn-drawer [data-cn-dr="submit"]').textContent(), /Зберегти/, "далі — режим правки");
  await waitBadge(page, "memo-publish", "error");
  assert.deepEqual(errors, []);
});

guardRealDeai();
```

Звірити з `fixture.mjs`: чи `startServer` повертає `spaces[0].path` (так — `iso.spaces`), чи `taskFixture` повертає `{dir}`; чи `env` зливається поверх ізоляції (так — `...env` останнім). Якщо `#bar [data-dd="space"]` відкриває дропдаун інакше — подивитись `tests/live/spaces.test.mjs`.

- [ ] **Step 3: Прогнати послідовно** (лише цей файл; інші живі — не паралельно):

```bash
python3 "$G" 600 4000 node --test --test-concurrency=1 tests/live/connections.test.mjs
python3 "$G" 120 1500 node --test tests/live-ports.test.mjs
```
Очікувано: усі pass. Якщо падає через проводку — виправляти `app/*`, не послаблювати тест.

- [ ] **Step 4: Мутації живого тесту** (кожну відкотити побайтно): (1) у `cnSubmit` прибрати `replace = true;` → червоніє «заміна публікації» (409 → `refused`); (2) у `drawerHTML` додати `value="${esc(...)}"` у поле пароля — не застосовно (значення не в стані), натомість у `cnSubmit` прибрати `secrets: {}` зі знімка й у `drawerHTML` тимчасово писати `value` секрету — червоніє перевірка «секрет у DOM»; (3) у `ddSpaces` прибрати пункт `conn` → червоніють усі.

- [ ] **Step 5: Commit.**

```bash
git add tests/fixtures/modules-conn/memo-publish/module.json tests/fixtures/modules-conn/memo-publish/server.py tests/live/connections.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(connections): живий сценарій екрана «Підключення» і модуль-фікстура memo-publish

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Документи й версія 0.5.0

**Files:**
- Modify: `package.json` (`"version": "0.5.0"`; `package-lock.json` — поле версії кореня, якщо є)
- Modify: `CHANGELOG.md` (новий розділ `## [0.5.0] — DD.MM.YYYY` зверху, англійською, у стилі 0.4.0)
- Modify: `README.md` (розділ про модулі: перший спосіб — екран «Connections»; `curl` лишається як шлях агента)
- Modify: `docs/design/spaces-and-modules.md` (розділ «Onboarding»: що зроблено в 3a, що лишилось 3b/3c)

- [ ] **Step 1:** `package.json` → `0.5.0`. Перевірити, чи є тест/скрипт, що звіряє версію з CHANGELOG (`grep -rn "0.4.0" tests bin app | head`) — оновити разом.
- [ ] **Step 2:** `CHANGELOG.md` — розділ `[0.5.0]` з датою релізу (DD.MM.YYYY): Added — Connections screen (entry points, cards by role, drawer with secrets, check, replace, turn off), `replace`/`replaced` in `module-enable`; Changed — publish error text points to the screen; Tests — unit/live. Посилання на спеку.
- [ ] **Step 3:** `README.md` і `docs/design/spaces-and-modules.md` — як вище; жодних реальних імен, ключів, хостів.
- [ ] **Step 4:** Повний набір юнітів:

```bash
python3 "$G" 1200 4000 npm test 2>&1 | tail -20
```
- [ ] **Step 5: Commit.**

```bash
git add package.json CHANGELOG.md README.md docs/design/spaces-and-modules.md
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "docs: 0.5.0 — екран «Підключення» (етап 3a)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
(плюс `package-lock.json`, якщо змінено.)

---

## Після задач (контролер)

1. Фінальне ревʼю всієї гілки від `6359f8e` (спека) до HEAD — у `git archive`-експорті, модель sonnet.
2. Повний `npm test` і живі тести, яких торкнулась зміна, ПОСЛІДОВНО: `connections`, `spaces`, `spaces-flows`, `modules`, `shell-bar`, `shell-palette`, `tasks-home`, `vercel` (`node --test --test-concurrency=1 …`).
3. Тег `v0.5.0` (`git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com tag -a v0.5.0 -m "…"`), push явно: `git push origin <sha>:refs/heads/main`, `git push origin refs/tags/v0.5.0`. Перед push — перевірка на внутрішні рядки (імена, ключі трекера, хости) у нових комітах.
