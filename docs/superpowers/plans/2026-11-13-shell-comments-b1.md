# Реліз 0.26.0 «Коментарі в оболонці» (етап Б1) — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** джерело коментатора живе в репо Deai (`commenter/`); коментатор отримує опційний режим хоста; права панель «Коментарі» в оболонці (острівець, клавіша C, ⌘K) показує піни поточної ітерації в «Макеті» й на «Огляді», закриті — з тим, що зробив Claude.

**Architecture:** коментатор у рамці (і на полотні «Огляду») лишається рушієм пінів і форми; з `init({host})` він ховає свою ручку й панель, не слухає C/P/H і повідомляє хоста колбеками (`onReady/onChange/onSelect/onMode`), а хост кличе його публічні методи (`snapshot`, `focus`, `carry`, `editComment`, `openShot`, `togglePins` + наявні). Сервер вставляє колбеки лише в робоче місце і лише за `/commented?…&host=1`. Оболонка: чиста модель `app/comments-model.js`, чиста розмітка `app/comments-view.js`, проводка в `app/app.js` через `BAR_ACTIONS`.

**Tech Stack:** ванільний ES-модульний JS (`node:test`), esbuild 0.25.12 (лише збірка коментатора), Python 3 stdlib (`unittest`, 3.9-сумісний), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-13-shell-comments-design.md`, розділ «Б1». Парасолька: `2026-11-13-shell-redesign-design.md`. Принципи: `PRODUCT.md` (принцип 6 — коментатор окремий продукт). **ПОПРАВКИ НИЖЧЕ мають перевагу над текстом спеки й задач.**

**Рівень строгості — повний:** на кожну задачу — виконавець і ревʼюер (спершу відповідність задачі, потім якість); кожна нова перевірка доводиться мутацією (один рядок → червоніє → відновлено; у звіті — що саме мутовано); після T10 — фінальне ревʼю всієї гілки, релізний прогін, перевірка проти живого канвасу (T11, контролер).

Базова лінія на `325bd50` (= 0.25.0 + спека): записати числа з першого прогону в звіті T1 (на 0.25.0 було JS 2073 pass; Python 5080/223/170; живі 494).

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Робоче дерево: `<repo>` = `deai-canvas-dev`, гілка `feat/shell-comments`. Коміти лише так, з переліком шляхів; новий файл спершу `git add -- <шлях>`:
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<тема>

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  **Ніколи** `git add -A` / `git add .`; не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`; ніколи `--amend`, `stash`, `reset`, `checkout` інших гілок. У zsh список шляхів у змінній розгортати як `${=P}`.
- ⛔ Живий канвас працює з ІНШОГО дерева (`deai-canvas`, порт 8765). Його не чіпаємо: ні файлів, ні процесу, ні порту.
- ⛔ `~/Liga Tools/design-office` — лише ЧИТАННЯ (`git -C … show <коміт>:<шлях>`, `git -C … log`). Нічого там не змінювати, не перемикати гілок, не збирати.
- ⛔ У жоден комітований файл не пишемо справжніх імен людей, хостів, імен користувачів машини, ключів, шляхів зі scratchpad чи тимчасових тек.
- Правки наявних файлів — точкові (`Edit`); нові файли — `Write`.

**Прогони й середовище**

- JS (після кожної задачі): `node --test tests/*.test.mjs && node tests/inspector-core.test.mjs` (з T2 — ще `&& node --test commenter/test/*.test.mjs`).
- Python (T2, T5, T8, T11 — і будь-яка задача, що чіпає `.py`): кожен прогін під тимчасовим `HOME`, без `DC_TASKS_FILE`/`DEAI_HOME`, без `.pyc`:
  `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s tests -p 'test_*.py'` (і так само `-s bin`, `-s app`).
- Живі — по одному файлу, ПОСЛІДОВНО:
  `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs`.
- Чекати фоновий прогін — лише за PID (`while kill -0 $PID 2>/dev/null; do sleep 10; done`) або за рядком у лозі. ⛔ Ніколи `while pgrep -f …` (збігається сам із собою й не закінчується ніколи).
- Мережі в тестах нема; порти 8765/4317 не чіпаються; справжні `~/.deai`, `~/deai-work`, `~/deai-published`, `~/.claude/pipeline-feedback/`, `~/.gitconfig`, справжній `tasks.json` не змінюються; процеси зупиняємо лише за PID (ніколи `pkill -f`/`killall`).
- ≤ 1 виконавець одночасно. Тести, які ламає задача, правляться в ТІЙ САМІЙ задачі й згадуються у звіті одним рядком із причиною. Тест не можна «підігнати» під нову поведінку мовчки: у звіті — що він охороняв і чому охорона збереглась.
- Кириличних рядкових літералів у `app/*.js` (крім `i18n.js`) бути не може — `tests/i18n-literals.test.mjs`; тексти лише через `t()`. Іконки — лише з `app/icons.js` (`tests/icons.test.mjs`). Класи `pin`, `cp`, `cluster`, `cbadge` у `app/*.js` заборонені (`tests/principle6.test.mjs`) — у оболонці лише `cmt-*`.
- CSS — лише наявні токени (`tests/css-guards.test.mjs`).

---

## Поправки до спеки (звірено з кодом на `325bd50` і design-office `3581cd0`; мають перевагу)

1. **Режим хоста БУДУЄ і ХОВАЄ, а не «не будує».** Внутрішній код коментатора тримає посилання на ручку, панель, список (`this._fab`, `this._panel`, `this._list` …); прибрати їх — переписати пів файла. Тому з `host` корінь тіньового DOM отримує клас `hosted`, і CSS ховає `.handle`, `.panel`, `.sheetscrim`, `.sheetpeek` (`display:none !important`). `_openPanel()` у режимі хоста нічого не робить (і `body.cl-shift` не ставить).
2. **Рядок режимів лишається.** Element / Text / Multi / Area / Done / Freeze — це інструмент коментування, не хром. Острівець над ним уже піднімається (`claude-lift`, `app.js` `layerModesShown`). «Done» вимикає режим → `onMode(false)` → оболонка закриває панель.
3. **Колбеки:** `onReady()` (кінець `init`; оболонка тоді повторно вмикає режим, якщо панель відкрита — `setCommentMode` до кінця `init` ігнорується), `onChange(snapshot)` (лише після `init`; на кожен `_render`), `onSelect(id)` (клік по піну чи кластеру), `onMode(on)` (кожен `_armComment`). Виняток у колбеку хоста коментатор ковтає.
4. **Клавіші.** З `host` коментатор слухає лише СВОЄ вікно (без предків) і лише Escape (лайтбокс → форма → редагування → вихід із режиму). C і H — оболонки: її глобальний обробник і обробник на вікні рамки (вішається на кожне `load` рамки). P прибрано (панель = режим).
5. **«Поточні» = `_inScope` коментатора** (ітерація; legacy — скрізь), рівно як список його власної панелі; окремого фільтра сторінок у Б1 нема. «Іншу сторінку» й «елемента немає на екрані» картка показує з поля `where` знімка.
6. **Картка не втрачає можливостей панелі коментатора:** редагування, видалення, мініатюра скриншота (клік → лайтбокс коментатора в рамці), режим (text/multi/area), ширина (`meta.viewport`), цитата (`meta.sel`). Нові публічні методи: `snapshot()`, `focus(id)` (= клік по картці в панелі коментатора: скрол і спалах елемента, на полотні — камера до піна, без елемента — лайтбокс), `carry(id)`, `editComment(id, text)`, `openShot(id)`, `togglePins()`.
7. **Число на кнопці острівця.** Нейтральне число відкритих поточних (замінює `cbadge` ручки; клас `isl-count`). Бурштинові «нові» — Б2.
8. **`audiences` у сніпетах робочого місця лишаються як є.** Панель коментатора схована, вкладок у ній не видно; перемикач каналу в панелі оболонки кличе наявну `setAudience(ch)` (`app.js`). У Б2 аудиторії стануть чипами адресата.
9. **Колбеки в сторінці — лише за `host=1` в URL `/commented`.** Оболонка завжди додає `&host=1` до `frame.src`; без нього сторінка байт-у-байт як зараз (еталони `tests/fixtures/comments-role/` НЕ змінюються), публікація `host` не отримує ніколи. Відкрита напряму в браузері `/commented` лишається з ручкою коментатора.
10. **Штамп збірки — `commenter/build-stamp.json`**, не в `app/vendor/` (службовий файл не мусить їхати в превʼю). Штамп: `{ "src": <sha256 commenter/src>, "esbuild": "0.25.12", "out": { "comment-layer.min.js": <sha256>, "anchor.min.js": <sha256> } }` — охоронець звіряє обидві ланки (src → штамп → вендорні файли).
11. **Повідомлення з рамки:** `{ type: 'dc-comments', ev: 'ready'|'change'|'select'|'mode', snapshot?, id?, on? }`, `window.parent.postMessage(m, location.origin)`. Приймач перевіряє `ev.source === frame.contentWindow`, тип і білий список `ev`. Події рамки ігноруються в «Огляді», події полотна — в «Макеті».
12. **Безпека розмітки:** тексти користувачів (текст, автор, час, цитата, `resolveReason`) — лише через `esc()`; `src` мініатюри — лише `data:image/(png|jpeg|jpg|webp|gif);base64,…` або `http(s)://…`, інакше мініатюри нема.
13. **Сортування й пошук:** відкриті й попередні — за номером (`n`) спаданням; закриті — за `meta.resolvedAt` спаданням, далі `n`. Пошук як у коментатора: `#N` — точний номер, інакше підрядок без регістру в `#n текст автор час цитата`.
14. **Перехід на «Задачі» закриває панель** (і вимикає режим); чистий перегляд ховає `#cmt-panel` разом з `#insp-panel`.
15. **`host=1` не губиться в рамці (ревʼю T5, T7).** Коментатор у `_focusElement` переходить на `meta.url` піна; у пінів, створених до 0.26.0 чи на сторінці, відкритій напряму, там нема `host=1` — рамка підніметься без колбеків і з власною ручкою. Тому обробник `load` рамки в оболонці (той самий, що вішає C/H): якщо рамка на `/commented` і в її `location.search` нема `host=1` — `frame.contentWindow.location.replace(<та сама адреса> + '&host=1')` (без запису в історію). Живий сценарій у `comments-panel`: перехід рамки на `/commented?…` без `host=1` → повертається `ready`, ручки коментатора не видно.
16. **`host` — зарезервований параметр** (`app/flow-model.js` `RESERVED_Q`, T7). Інакше `meta.url` пінів, створених у рамці з `host=1`, дає стан `{host:'1'}` (`overview-pins.js` читає всі незарезервовані параметри як стан) — і пін на «Огляді» не знаходить свого вузла. Тест у `tests/flow-model.test.mjs` + сценарій в `overview-pins`-тесті: `meta.url` з `&host=1` дає той самий стан, що й без нього; мутація — прибрати `"host"` з набору.

---

## Структура файлів

| Файл | Що робить | Задача |
|---|---|---|
| `commenter/src/*.js`, `commenter/test/*.test.mjs`, `commenter/LICENSE`, `commenter/package.json` (нові) | джерело коментатора, перенесене з design-office `3581cd0` | T1 |
| `commenter/scripts/build.mjs`, `commenter/package-lock.json`, `commenter/build-stamp.json`, `.gitignore`, `package.json`, `app/vendor/comment-layer.min.js`, `app/vendor/anchor.min.js`, `tests/commenter-stamp.test.mjs` (новий) | збірка в `app/vendor`, штамп, охоронець | T2 |
| `app/vendor/local-adapter.js`, `tests/local-adapter.test.mjs` | новіший локальний адаптер (фікси 05.11) | T3 |
| `commenter/src/comment-layer.js` (+ збірка), `tests/live/commenter-host.test.mjs` (новий) | режим хоста | T4 |
| `app/serve.py`, `tests/test_comments_role.py`, `tests/test_publish_module.py` | `host=1` у `/commented` | T5 |
| `app/comments-model.js`, `app/comments-view.js` (нові), `app/i18n.js`, `tests/comments-model.test.mjs`, `tests/comments-view.test.mjs` (нові) | чиста модель і розмітка панелі | T6 |
| `app/island.js`, `app/index.html`, `app/styles.css`, `app/app.js`, `app/shell-palette.js`, `tests/island.test.mjs`, `tests/shell-palette.test.mjs`, `tests/live/comments-panel.test.mjs` (новий) | проводка в «Макеті» | T7 |
| `app/overview-comments.js`, `app/app.js`, `tests/overview-comments-module.test.mjs`, `tests/live/comments-panel.test.mjs`, `tests/live/overview-comments.test.mjs` | «Огляд» | T8 |
| `tests/live/*.test.mjs` | міграція решти живих тестів | T9 |
| `CHANGELOG.md`, `package.json`, `README.md`, `commenter/README.md`, `PRODUCT.md`, `docs/modules/comments.md` | реліз 0.26.0 | T10 |

---

### Task 1: Джерело коментатора в `commenter/` (перенесення як є)

**Files:**
- Create: `commenter/src/comment-layer.js`, `commenter/src/anchor.js`, `commenter/src/anchor-global.js`, `commenter/src/audiences.js`, `commenter/src/context-bundle.js`
- Create: `commenter/scripts/build.mjs` (як є; адаптація — T2)
- Create: `commenter/test/<лише юніт-тести без мережі й Supabase>.test.mjs`
- Create: `commenter/LICENSE`, `commenter/package.json`

- [ ] **Step 1: Базова лінія.** `node --test tests/*.test.mjs 2>&1 | tail -5` і `node tests/inspector-core.test.mjs | tail -2` — числа у звіт.

- [ ] **Step 2: Звірити джерело.** Має бути саме цей коміт і чисте дерево коментатора:

```bash
DO="$HOME/Liga Tools/design-office"
git -C "$DO" rev-parse --short fix/local-pins-react      # очікується 3581cd0
git -C "$DO" ls-tree --name-only 3581cd0 comment-layer/src/ comment-layer/test/ comment-layer/scripts/
```

Якщо гілка вказує не на `3581cd0` — СТОП, звіт `NEEDS_CONTEXT`.

- [ ] **Step 3: Вивантажити ЗАКОМІЧЕНИЙ вміст** (не робоче дерево) у `commenter/`:

```bash
mkdir -p commenter/src commenter/scripts commenter/test
for f in comment-layer.js anchor.js anchor-global.js audiences.js context-bundle.js; do
  git -C "$DO" show "3581cd0:comment-layer/src/$f" > "commenter/src/$f"; done
git -C "$DO" show 3581cd0:comment-layer/scripts/build.mjs > commenter/scripts/build.mjs
git -C "$DO" show 3581cd0:comment-layer/LICENSE > commenter/LICENSE
```

`supabase-adapter.js` НЕ переїжджає (у Deai свій адаптер модуля `supabase-comments`). Переконатися, що точки входу його не імпортують: `grep -n "^import" commenter/src/*.js` — жодного `supabase-adapter`.

- [ ] **Step 4: Юніт-тести.** Для кожного файла з `git -C "$DO" ls-tree --name-only 3581cd0 comment-layer/test/` вирішити: переносимо, якщо він НЕ імпортує `supabase-adapter`/`@supabase`, НЕ ходить у мережу й НЕ потребує браузера. Очікувано переїжджають: `anchor-geo`, `audiences`, `backup`, `compose-top`, `context-bundle`, `offscreen-context`, `style-literal`, `typing-origin`, `viewport-tag`; лишаються в design-office: `supabase-mappers`, `supabase-traffic`, `supabase-e2e`. Вивантажити вибрані тим самим `git show` у `commenter/test/`. Тест, що читає `dist/…`, позначити у звіті — шлях виправить T2.

- [ ] **Step 5: `commenter/package.json`** (новий, мінімальний; `"type": "module"` — тести імпортують `../src/*.js` як ES-модулі):

```json
{
  "name": "deai-commenter",
  "private": true,
  "version": "1.3.0",
  "description": "Коментатор Deai Canvas: піни на макеті. Перенесено з comment-layer (design-office @3581cd0).",
  "type": "module",
  "license": "MIT",
  "scripts": {
    "build": "node scripts/build.mjs",
    "test": "node --test test/*.test.mjs"
  },
  "devDependencies": {
    "esbuild": "0.25.12"
  }
}
```

- [ ] **Step 6: Прогнати тести коментатора:** `node --test commenter/test/*.test.mjs` — усі PASS (крім тих, що читають `dist/` — їх перелічити у звіті з причиною; T2 їх полагодить).

- [ ] **Step 7: Чистота.** Сканування забороненого списку по теці:

```bash
F="$HOME/Liga Tools/design-office-transition/scripts/deai-forbidden.txt"
grep -rIl -F -f <(grep -v '^\s*#' "$F" | grep -v '^\s*$') commenter/ || echo "0 збігів"
```

Очікується `0 збігів`. Будь-який збіг — СТОП, звіт `BLOCKED` із назвою файла (не змісту збігу).

- [ ] **Step 8: Коміт** (нові файли спершу `git add -- …`):

```bash
P="commenter/src commenter/scripts/build.mjs commenter/test commenter/LICENSE commenter/package.json"
git add -- ${=P}
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.26.0): джерело коментатора переїжджає в Deai (commenter/, з comment-layer @3581cd0)

Як є: src (без supabase-adapter — у Deai свій адаптер модуля), юніт-тести без
мережі, ліцензія. Збірка в app/vendor — наступним комітом.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ${=P}
```

---

### Task 2: Збірка в `app/vendor`, штамп і охоронець

**Files:**
- Modify: `commenter/scripts/build.mjs`
- Create: `commenter/package-lock.json` (через `npm install`), `commenter/build-stamp.json` (пише збірка), `tests/commenter-stamp.test.mjs`
- Modify: `.gitignore` (+ `commenter/node_modules/`), `package.json` (скрипт `test`), `app/vendor/comment-layer.min.js`, `app/vendor/anchor.min.js` (пише збірка)
- Modify (за потреби): `commenter/test/*.test.mjs`, що читали `dist/`

- [ ] **Step 1: Встановити esbuild точно 0.25.12:** `cd commenter && npm install --save-exact --save-dev esbuild@0.25.12 && cd ..`. Додати в `.gitignore` рядок `commenter/node_modules/`. Перевірити: `git status --short commenter` не показує `node_modules`.

- [ ] **Step 2: Написати охоронця, що падає** — `tests/commenter-stamp.test.mjs`:

```js
/**
 * Вендорні бандли коментатора (`app/vendor/comment-layer.min.js`, `app/vendor/anchor.min.js`) зібрано з ПОТОЧНОГО
 * `commenter/src` (Deai 0.26.0). Ланцюжок із двох ланок: хеш `src/` == `build-stamp.json#src` і хеш кожного вендорного
 * файла == `build-stamp.json#out[файл]`. Правка в `src/` без збірки червонить першу ланку; ручна правка бандла — другу.
 * Хеш `src/` рахує ТА САМА функція, що й збірка (`srcHash` з `commenter/scripts/build.mjs`): двох реалізацій бути не мусить.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { srcHash } from "../commenter/scripts/build.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const STAMP = JSON.parse(readFileSync(path.join(ROOT, "commenter", "build-stamp.json"), "utf8"));
const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");

test("штамп збірки відповідає поточному commenter/src", () => {
  assert.equal(STAMP.src, srcHash(path.join(ROOT, "commenter")), "src змінено без `npm run build` у commenter/");
  assert.equal(STAMP.esbuild, "0.25.12");
});

test("вендорні бандли — рівно ті, що записала збірка", () => {
  assert.deepEqual(Object.keys(STAMP.out).sort(), ["anchor.min.js", "comment-layer.min.js"]);
  for (const [name, want] of Object.entries(STAMP.out)) {
    assert.equal(sha(path.join(ROOT, "app", "vendor", name)), want, `app/vendor/${name} не зі збірки`);
  }
});
```

Запустити: `node --test tests/commenter-stamp.test.mjs` → FAIL (`build-stamp.json` ще нема).

- [ ] **Step 3: Адаптувати `commenter/scripts/build.mjs`.** `srcHash` і `srcFiles` лишаються як є. Блок запуску (`if (import.meta.url === invokedAs) { … }`) замінити на:

```js
if (import.meta.url === invokedAs) {
  const bin = path.join(ROOT, "node_modules", ".bin", "esbuild");
  /* Вихід — прямо у вендор Deai: окремої `dist/` нема, щоб не було двох копій бандла, одна з яких застаріє.
     `supabase-adapter` не збираємо: у Deai свій адаптер модуля `supabase-comments`. */
  const VENDOR = path.join(ROOT, "..", "app", "vendor");
  const ENTRIES = [["comment-layer.js", "comment-layer.min.js"], ["anchor-global.js", "anchor.min.js"]];
  const out = {};
  for (const [entry, file] of ENTRIES) {
    const dest = path.join(VENDOR, file);
    execFileSync(bin, [path.join("src", entry), "--bundle", "--format=iife", "--minify", `--outfile=${dest}`],
                 { cwd: ROOT, stdio: "inherit" });
    out[file] = createHash("sha256").update(readFileSync(dest)).digest("hex");
  }
  writeFileSync(path.join(ROOT, "build-stamp.json"),
    `${JSON.stringify({ src: srcHash(), esbuild: esbuildVersion(), out }, null, 2)}\n`);
  console.log("app/vendor зібрано, штамп записано");
}
```

Прибрати з файла згадки `doctor.py`/`design-canvas` у коментарях, що стали неправдою (хеш більше ніхто в Python не дублює) — одним реченням: «рахується лише тут; охоронець — `tests/commenter-stamp.test.mjs`». Невикористаний імпорт `statSync` лишається (його бере `srcFiles`).

- [ ] **Step 4: Зібрати:** `cd commenter && npm run build && cd ..`. Перевірити `git diff --stat app/vendor` — змінився `comment-layer.min.js` (було `a5c6efc`, тепер `3581cd0`); `anchor.min.js` очікувано без змін. Повторна збірка — `git diff --exit-code app/vendor commenter/build-stamp.json` після другого `npm run build` чистий (детермінізм).

- [ ] **Step 5: Охоронець зелений:** `node --test tests/commenter-stamp.test.mjs` → PASS.

- [ ] **Step 6: Мутації охоронця** (кожну — відновити й переконатися, що знову зелено):
  1. дописати коментар `// x` у кінець `commenter/src/audiences.js` → перший тест FAIL;
  2. дописати байт у кінець `app/vendor/anchor.min.js` → другий тест FAIL.

- [ ] **Step 7: Тести коментатора в загальному прогоні.** У кореневому `package.json` скрипт `test` починається з `node --test tests/*.test.mjs && node --test commenter/test/*.test.mjs && …` (решта без змін). Тести коментатора, що читали `dist/…`, перевести на `../../app/vendor/…`. `node --test commenter/test/*.test.mjs` → усі PASS.

- [ ] **Step 8: Повний прогін із новим бандлом** (поведінка коментатора змінилась фіксами 05.11): JS; Python (3 discover); живі ПОСЛІДОВНО: `comments`, `overview-comments`, `offscreen-pin`, `pin-where`, `comment-audience`, `shell-typing`, `claude-status`, `external-change`. Усе має пройти. Червоне — не правити тест, а звітувати `DONE_WITH_CONCERNS` із виводом.

- [ ] **Step 9: Коміт:**

```bash
P="commenter/scripts/build.mjs commenter/package.json commenter/package-lock.json commenter/build-stamp.json .gitignore package.json app/vendor/comment-layer.min.js app/vendor/anchor.min.js tests/commenter-stamp.test.mjs commenter/test"
git add -- commenter/package-lock.json commenter/build-stamp.json tests/commenter-stamp.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "build(0.26.0): коментатор збирається з commenter/src прямо в app/vendor, штамп і охоронець

Вендорний бандл тепер із 3581cd0 (фікси 05.11: піни на React-сторінках, видалений
пін не повертається). Охоронець звіряє src → штамп → вендорні файли.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ${=P}
```

---

### Task 3: Новіший локальний адаптер

**Files:**
- Modify: `app/vendor/local-adapter.js`
- Modify: `tests/local-adapter.test.mjs`

- [ ] **Step 1: Звірити різницю:** `DO="$HOME/Liga Tools/design-office"; NEW=$(mktemp); git -C "$DO" show 3581cd0:design-canvas/app/vendor/local-adapter.js > "$NEW"; diff app/vendor/local-adapter.js "$NEW"`. Очікується: лише ДОДАНО знімок `snap()` (кільце `_el`) і чергу записів `serial()`; жодного видаленого рядка поведінки. Інакше — СТОП, `NEEDS_CONTEXT`.

- [ ] **Step 2: Тести, що падають.** Знайти тести цих фіксів у design-office: `git -C "$DO" show --stat 7290cca 3581cd0 | grep -i test`. Перенести їхні сценарії в `tests/local-adapter.test.mjs` (у стилі файла, `node:test`). Мінімум два сценарії:
  1. `save()` списку, де в піна є кільцеве посилання (`c._el = { self: null }; c._el.self = c._el` чи DOM-подібне кільце) — запис іде, кільце не серіалізується;
  2. `remove([id])` і одразу `save(list)` без очікування — видалений пін не повертається на сервері (фейковий `fetch` фіксує порядок GET/POST).
  Запустити — обидва FAIL на старому адаптері.

- [ ] **Step 3: Замінити файл** вмістом із `3581cd0`. Тести — PASS.

- [ ] **Step 4: Мутація:** у новому файлі замінити тіло `serial(job)` на `return job();` → сценарій 2 FAIL. Відновити.

- [ ] **Step 5: Прогін:** JS; живі ПОСЛІДОВНО `comments`, `overview-comments`, `pin-where`.

- [ ] **Step 6: Коміт** `fix(0.26.0): локальний адаптер — знімок без кільця _el і записи по черзі (з design-office 3581cd0)` — шляхи `app/vendor/local-adapter.js tests/local-adapter.test.mjs`.

---

### Task 4: Режим хоста в коментаторі

**Files:**
- Modify: `commenter/src/comment-layer.js`
- Modify (збірка): `app/vendor/comment-layer.min.js`, `commenter/build-stamp.json`
- Create: `tests/live/commenter-host.test.mjs`

- [ ] **Step 1: Живий тест, що падає** — `tests/live/commenter-host.test.mjs`. Сервер Deai не потрібен: сторінка з `page.setContent`, бандл — `page.addScriptTag({ content })`. Дати файлу власну смугу портів не треба (порти не відкриваються); `tests/live-ports.test.mjs` перевірити — якщо він вимагає `PORT_BASE` у кожному файлі, додати невикористану унікальну базу з коментарем.

```js
/**
 * Режим хоста коментатора (Deai 0.26.0): з `init({host})` ручка й панель коментатора сховані, C/P/H він не слухає,
 * про все повідомляє колбеками, а хост керує ним методами. Без `host` — як до 0.26.0. Сервер не потрібен: голий бандл
 * `app/vendor/comment-layer.min.js` на сторінці з `setContent`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BUNDLE = readFileSync(path.join(ROOT, "app", "vendor", "comment-layer.min.js"), "utf8");
const PAGE = '<!doctype html><html><body style="margin:40px"><main><h1 id="t">Заголовок</h1>'
  + '<p id="p">Абзац для коментаря</p></main></body></html>';

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** `seed` — коментарі, що вже лежать у сховищі; `withHost` — чи передати `host`. */
async function boot({ withHost, seed = [], version = "2" }) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(({ withHost, seed, version }) => {
    window.__ev = [];
    const mem = seed.slice();
    const store = { load: () => mem.slice(), save: (l) => { mem.length = 0; mem.push(...l); } };
    window.__mem = mem;
    const host = withHost ? {
      onReady: () => window.__ev.push(["ready"]),
      onChange: (s) => window.__ev.push(["change", s]),
      onSelect: (id) => window.__ev.push(["select", id]),
      onMode: (on) => window.__ev.push(["mode", on]),
    } : undefined;
    window.CommentLayer.init({ projectId: "t", storage: store, version, user: { name: "Тест" }, host });
  }, { withHost, seed, version });
  return page;
}
const root = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(s);
  return el ? getComputedStyle(el).display : null;
}, sel);
const lastSnap = (page) => page.evaluate(() => [...window.__ev].reverse().find((e) => e[0] === "change")?.[1]);
async function addComment(page, text) {
  await page.click("#p");
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await page.evaluate((t) => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .save").click());
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text);
}

test("без host: ручку видно, клавіша C вмикає режим (поведінка до 0.26.0)", async () => {
  const page = await boot({ withHost: false });
  assert.notEqual(await root(page, ".handle"), "none");
  await page.keyboard.press("c");
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".modes.show")), true);
  await page.close();
});

test("з host: ручка й панель сховані, C не діє, ready і change приходять", async () => {
  const page = await boot({ withHost: true });
  assert.equal(await root(page, ".handle"), "none");
  assert.equal(await root(page, ".panel"), "none");
  const kinds = await page.evaluate(() => window.__ev.map((e) => e[0]));
  assert.deepEqual(kinds.slice(0, 2), ["ready", "change"]);
  const s = await lastSnap(page);
  assert.equal(s.version, "2");
  assert.equal(s.iteration, "2");
  assert.deepEqual(s.comments, []);
  await page.keyboard.press("c");
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".modes.show")), false);
  assert.equal(await page.evaluate(() => document.body.classList.contains("cl-shift")), false);
  await page.close();
});

test("з host: режим через API, пін через форму, знімок без fp/htmlSnapshot, select і Escape", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  assert.deepEqual(await page.evaluate(() => window.__ev.filter((e) => e[0] === "mode").map((e) => e[1])), [true]);
  assert.notEqual(await root(page, ".modes.show"), null);
  await addComment(page, "Зробити ширшим");
  const s = await lastSnap(page);
  assert.equal(s.comments.length, 1);
  const c = s.comments[0];
  assert.equal(c.n, 1);
  assert.equal(c.scope, "current");
  assert.equal(c.where, "here");
  assert.equal(c.text, "Зробити ширшим");
  assert.equal("fp" in c, false);
  assert.equal("htmlSnapshot" in c, false);
  assert.equal("_el" in c, false);
  await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".pin").click());
  assert.deepEqual(await page.evaluate(() => window.__ev.filter((e) => e[0] === "select").map((e) => e[1])), [c.id]);
  assert.equal(await root(page, ".panel"), "none");
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => window.__ev.filter((e) => e[0] === "mode").at(-1)[1]), false);
  await page.close();
});

test("з host: editComment, resolve/reopen, togglePins, openShot", async () => {
  const shot = "data:image/png;base64,iVBORw0KGgo=";
  const page = await boot({ withHost: true, seed: [
    { id: "a1", author: "Тест", text: "старий", status: "open", meta: { seq: 1, iteration: "2", version: "2", shot }, ts: "13.11.2026 10:00" },
  ] });
  assert.equal(await page.evaluate(() => window.CommentLayer.editComment("a1", "  новий  ")), true);
  assert.equal((await lastSnap(page)).comments[0].text, "новий");
  assert.equal(await page.evaluate(() => window.CommentLayer.editComment("a1", "   ")), false);
  await page.evaluate(() => window.CommentLayer.resolveComment("a1"));
  assert.equal((await lastSnap(page)).comments[0].status, "resolved");
  await page.evaluate(() => window.CommentLayer.reopenComment("a1"));
  assert.equal((await lastSnap(page)).comments[0].status, "open");
  assert.equal(await page.evaluate(() => window.CommentLayer.togglePins()), true);
  assert.equal((await lastSnap(page)).pinsHidden, true);
  await page.evaluate(() => window.CommentLayer.openShot("a1"));
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".cllb img")), true);
  await page.close();
});

test("з host: пін попередньої ітерації — scope earlier, carry переносить копією в поточну", async () => {
  const page = await boot({ withHost: true, version: "3", seed: [
    { id: "o1", author: "Тест", text: "з другої", status: "open", meta: { seq: 4, iteration: "2", version: "2" }, ts: "12.11.2026 09:00" },
  ] });
  const before = (await lastSnap(page)).comments;
  assert.deepEqual(before.map((c) => [c.id, c.scope, c.iter]), [["o1", "earlier", "2"]]);
  await page.evaluate(() => window.CommentLayer.carry("o1"));
  const after = (await lastSnap(page)).comments;
  assert.equal(after.length, 2);
  assert.equal(after.find((c) => c.id !== "o1").scope, "current");
  assert.equal(after.find((c) => c.id === "o1").scope, "earlier");
  await page.close();
});
```

Запустити: FAIL (ручка видно з `host`, подій нема, методів нема).

- [ ] **Step 2: Реалізація в `commenter/src/comment-layer.js`** (лише додавання гілок; шлях без `host` не змінюється):

  a. `init`: після рядка `this.appLocal = !!opts.local;` —
  ```js
      /* Режим хоста (Deai 0.26.0): ручку й власну панель тримає ОБОЛОНКА; коментатор малює піни, форму й рядок режимів
         і повідомляє хоста колбеками (`onReady`/`onChange`/`onSelect`/`onMode`). Без `host` — поведінка як до 0.26.0. */
      this._hostOpts = opts.host && typeof opts.host === 'object' ? opts.host : null;
  ```
  b. `init`: після `this._inited = true;` —
  ```js
      this._emit('onReady');
      this._emit('onChange', this.snapshot());
  ```
  c. `_buildUI`: у `root.className` додати `+ (this._hostOpts ? ' hosted' : '')`.
  d. `STYLE` (у кінець рядка стилів): `.root.hosted .handle,.root.hosted .panel,.root.hosted .sheetscrim,.root.hosted .sheetpeek{display:none !important}`.
  e. Клавіші: замість безумовного обходу предків —
  ```js
      const keyTargets = [window];
      /* Хост сам тримає C/H на своєму вікні й на вікні рамки: предків коментатор не чіпає. */
      if (!this._hostOpts) {
        try {
          let w = window;
          while (w !== w.parent) { w = w.parent; void w.document.documentElement; keyTargets.push(w); }
        } catch (err) { /* cross-origin ancestor — can't listen there, ignore */ }
      }
  ```
  і в `_keyHandler` одразу ПІСЛЯ блоку `if (e.key === 'Escape') { … }`: `if (this._hostOpts) return;   // C/P/H — клавіші хоста`.
  f. `_openPanel()`: першим рядком `if (this._hostOpts) return;   // панель — оболонки`.
  g. `_focusCard(id)`: першим рядком `if (this._hostOpts) { this._emit('onSelect', id); return; }`; `_focusCards(ids)`: першим рядком `if (this._hostOpts) { if (ids && ids.length) this._emit('onSelect', ids[0]); return; }`.
  h. `_armComment(on)`: останнім рядком `this._emit('onMode', !!on);`.
  i. `_render()`: останнім рядком (після `this._placePins();`) `if (this._inited) this._emit('onChange', this.snapshot());`.
  j. Нові методи — поруч із `getComments()`:
  ```js
    /* ---- API хоста (Deai 0.26.0) ---- */
    _emit(name, arg) {
      const h = this._hostOpts;
      if (!h || typeof h[name] !== 'function') return;
      try { h[name](arg); } catch (e) { /* хост не сміє зламати коментатор */ }
    },
    /** Знімок для панелі хоста: копії без `_el`/`_pending`/`fp`/`htmlSnapshot` + `n` (номер піна), `scope`
     *  (`current` — ця ітерація чи legacy, `earlier` — інша відома ітерація, `other` — решта), `where` (`here` /
     *  `elsewhere` — інша сторінка / `offscreen` — елемента нема на екрані), `iter` (ітерація піна), `pending`. */
    snapshot() {
      const route = location.pathname + location.hash;
      const where = (c) => {
        if (!this.anchors && c.meta && c.meta.route && c.meta.route !== route) return 'elsewhere';
        if (!this.anchors && c.status === 'open' && this._offscreen(c)) return 'offscreen';
        return 'here';
      };
      const scope = (c) => (this._inScope(c) ? 'current' : (this._pinIter(c) != null ? 'earlier' : 'other'));
      return {
        version: this.appVersion, iteration: this._curIter(), pinsHidden: !!this._pinsHidden,
        comments: this.comments.map((c) => {
          const { _el, _pending, fp, htmlSnapshot, ...rest } = c;
          return Object.assign(JSON.parse(JSON.stringify(rest)),
            { n: this._seqOf(c), scope: scope(c), where: where(c), iter: this._pinIter(c), pending: !!_pending });
        }),
      };
    },
    /** Те саме, що клік по картці в панелі коментатора: скрол і спалах елемента (полотно — камера до піна). */
    focus(id) { if (this._inited && this.comments.some((x) => x.id === id)) this._focusElement(id); },
    carry(id) { if (this._inited) this._carryToCurrent(id); },
    editComment(id, text) {
      const v = String(text == null ? '' : text).trim();
      const c = this.comments.find((x) => x.id === id);
      if (!c || !v) return false;
      c.text = v; c._pending = true;
      this._persist(); this._render();
      return true;
    },
    openShot(id) {
      const c = this.comments.find((x) => x.id === id);
      const src = c && c.meta && (c.meta.shot || c.meta.shotUrl);
      if (src) this._openLightbox(src);
    },
    togglePins() { this._togglePins(); this._render(); return !!this._pinsHidden; },
  ```

- [ ] **Step 3: Зібрати:** `cd commenter && npm run build && cd ..`; `node --test tests/commenter-stamp.test.mjs` → PASS.

- [ ] **Step 4: Тест зелений:** `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/commenter-host.test.mjs` → PASS. Якщо `user: { name }` не приймається (`getUser` у `comment-layer.js`) — у тесті передати так, як очікує `getUser`, і написати це у звіті.

- [ ] **Step 5: Мутації** (кожна → червоний тест → відновити → зібрати знову):
  1. прибрати `if (this._hostOpts) return;   // C/P/H …` → тест 2 FAIL (C вмикає режим);
  2. прибрати правило `.root.hosted …` зі `STYLE` → тест 2 FAIL (ручку видно);
  3. у `_focusCard` прибрати гілку хоста → тест 3 FAIL (select не приходить);
  4. у `snapshot()` не вирізати `htmlSnapshot` → тест 3 FAIL.

- [ ] **Step 6: Регресія без `host`:** JS + `node --test commenter/test/*.test.mjs`; живі ПОСЛІДОВНО `comments`, `overview-comments`, `offscreen-pin`, `pin-where`, `comment-audience`, `shell-typing`, `claude-status` — усе зелене БЕЗ змін у них (ніхто ще не передає `host`).

- [ ] **Step 7: Коміт** `feat(0.26.0): режим хоста в коментаторі — сховані ручка й панель, колбеки, API для оболонки` — шляхи `commenter/src/comment-layer.js app/vendor/comment-layer.min.js commenter/build-stamp.json tests/live/commenter-host.test.mjs` (+ `tests/live-ports.test.mjs`, якщо правився).

---

### Task 5: `host=1` у `/commented`

**Files:**
- Modify: `app/serve.py` (поруч з `AUDIENCES_TMPL`/`audiences_arg`, `LOCAL_COMMENT_SNIPPET`, `inject_local_comment_layer`, `MODULE_COMMENT_SNIPPET`, `inject_module_comment_layer`, `_commented`)
- Modify: `tests/test_comments_role.py`, `tests/test_publish_module.py`

- [ ] **Step 1: Тести, що падають.** У `tests/test_comments_role.py`:
  - у `SnippetUnitTest`: `serve.host_arg(False) == ''`; `serve.host_arg(True)` містить `host: (function`, `'dc-comments'`, `location.origin`; `inject_local_comment_layer(…)` без `host` НЕ містить `dc-comments`, з `host=True` — містить рівно один раз; те саме для `inject_module_comment_layer`;
  - у класі сторінок (`PagesEnv`, поруч із `LegacyPagesTest`): сторінка `/commented?it=…&ch=local&host=1` і `…&ch=project&host=1` (ЛІГА) містять `dc-comments`; ті самі без `host=1` — НЕ містять (і еталони `page-*.html` не змінюються — наявні тести еталонів мусять лишитись зеленими без перезйомки).
  У `tests/test_publish_module.py` — у тест, що читає опубліковану сторінку з коментарями (знайти за `comment-layer.min.js` у тілі), додати `assertNotIn('dc-comments', html)` і `assertNotIn('host:', html)`.
  Запустити — FAIL (`host_arg` нема).

- [ ] **Step 2: Реалізація в `app/serve.py`:**

```python
# Режим хоста коментатора (Deai 0.26.0) — аргументом `init`, за ПРАПОРЦЕМ на виклику, як `audiences`.
#
# Панель коментарів переїхала в оболонку: коментатор у рамці ховає ручку й свою панель і повідомляє оболонку
# посилками (`postMessage` у батьківське вікно того самого походження), а оболонка керує ним методами
# `window.CommentLayer.*`. Чому лише за `host=1` в URL: оболонка ЗАВЖДИ його додає, а сторінка без нього (відкрита
# напряму, старі еталони `tests/fixtures/comments-role/`, публікація) — байт у байт як до 0.26.0. Публікація `host`
# не отримує НІКОЛИ: у превʼю колег нема оболонки, і схована ручка лишила б їх без коментарів.
# Чому `location.origin`, а не `'*'`: батько — оболонка цього ж сервера; чужому вікну посилка не потрібна.
HOST_ARG = """,
        host: (function () {
          var send = function (m) { m.type = 'dc-comments'; window.parent.postMessage(m, location.origin); };
          return {
            onReady: function () { send({ ev: 'ready' }); },
            onChange: function (s) { send({ ev: 'change', snapshot: s }); },
            onSelect: function (id) { send({ ev: 'select', id: id }); },
            onMode: function (on) { send({ ev: 'mode', on: !!on }); }
          };
        })()"""


def host_arg(on):
    """Аргумент `host` для `init` (колбеки-посилки в оболонку) або порожній рядок. `HOST_ARG` — готовий JS, без
    плейсхолдерів: у шаблон сніпета він іде ЗНАЧЕННЯМ `format`, тож фігурні дужки в ньому не екрануються."""
    return HOST_ARG if on else ''
```

  - `LOCAL_COMMENT_SNIPPET`: `local: true{audiences} }});` → `local: true{audiences}{host} }});`.
  - `MODULE_COMMENT_SNIPPET`: `version: {version_js}{audiences} }});` → `version: {version_js}{audiences}{host} }});`.
  - `inject_local_comment_layer(..., space=None, host=False)` → у `format(...)` додати `host=host_arg(host)`; так само `inject_module_comment_layer(..., space=None, host=False)`. Докстрінги — одне речення про `host`.
  - `_commented`: `host = q.get('host', ['0'])[0] == '1'` поруч із `bare`; обидва виклики інʼєкції отримують `host=host`. `build_preview`/публікацію НЕ чіпати.

- [ ] **Step 3: Зелено:** `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest tests.test_comments_role tests.test_publish_module` → PASS; `GoldenPinTest` зелений без змін `PINNED`.

- [ ] **Step 4: Мутації:**
  1. у `_commented` передати `host=True` безумовно → тест «без `host=1` — нема `dc-comments`» FAIL;
  2. у `build_preview` (виклик `inject_module_comment_layer`) тимчасово додати `host=True` → тест публікації FAIL.

- [ ] **Step 5: Повний Python** (3 discover) + JS. Живі: `comments` (сторінка без `host=1` — як була).

- [ ] **Step 6: Коміт** `feat(0.26.0): /commented?host=1 дає коментатору колбеки оболонки; публікація й еталони без змін` — шляхи `app/serve.py tests/test_comments_role.py tests/test_publish_module.py`.

---

### Task 6: Модель і розмітка панелі (чисті модулі)

**Files:**
- Create: `app/comments-model.js`, `app/comments-view.js`, `tests/comments-model.test.mjs`, `tests/comments-view.test.mjs`
- Modify: `app/i18n.js` (обидва словники)

- [ ] **Step 1: Ключі i18n** — у `uk` і `en`, поруч із `fbIsland` (тексти точно ці):

| ключ | uk | en |
|---|---|---|
| `cmtTitle` | `'Коментарі'` | `'Comments'` |
| `cmtKey` | `'Коментарі · C'` | `'Comments · C'` |
| `cmtIsland` | `(n) => n ? \`Коментарі, відкритих: ${n}\` : 'Коментарі'` | `(n) => n ? \`Comments, ${n} open\` : 'Comments'` |
| `cmtClose` | `'Закрити панель'` | `'Close panel'` |
| `cmtSearch` | `'Пошук — текст, автор, #5'` | `'Search — text, author, #5'` |
| `cmtChannel` | `'Кому'` | `'Audience'` |
| `cmtChLocal` | `'Claude'` | `'Claude'` |
| `cmtChTeam` | `'Команда'` | `'Team'` |
| `cmtPinsHide` | `'Сховати піни · H'` | `'Hide pins · H'` |
| `cmtPinsShow` | `'Показати піни · H'` | `'Show pins · H'` |
| `cmtOpen` | `'Відкриті'` | `'Open'` |
| `cmtEarlier` | `'З попередніх ітерацій'` | `'From earlier iterations'` |
| `cmtClosed` | `'Закриті'` | `'Closed'` |
| `cmtEmpty` | `'Коментарів ще немає. Натисніть на макет, щоб залишити.'` | `'No comments yet. Click the layout to leave one.'` |
| `cmtNoMatch` | `'Нічого не знайдено.'` | `'Nothing found.'` |
| `cmtLoading` | `'Коментатор завантажується…'` | `'Loading comments…'` |
| `cmtDown` | `(why) => \`Коментарі недоступні: ${why}\`` | `(why) => \`Comments unavailable: ${why}\`` |
| `cmtShow` | `'Показати'` | `'Show'` |
| `cmtResolve` | `'Закрити'` | `'Resolve'` |
| `cmtReopen` | `'Повернути'` | `'Reopen'` |
| `cmtEdit` | `'Редагувати'` | `'Edit'` |
| `cmtDelete` | `'Видалити'` | `'Delete'` |
| `cmtSave` | `'Зберегти'` | `'Save'` |
| `cmtCancel` | `'Скасувати'` | `'Cancel'` |
| `cmtCarry` | `(n) => \`Перенести в Іт.${n}\`` | `(n) => \`Move to It.${n}\`` |
| `cmtIter` | `(n) => \`Іт.${n}\`` | `(n) => \`It.${n}\`` |
| `cmtDone` | `(n) => \`Зроблено · Іт.${n}\`` | `(n) => \`Done · It.${n}\`` |
| `cmtClosedPlain` | `'Закрито'` | `'Resolved'` |
| `cmtElsewhere` | `'На іншій сторінці'` | `'On another page'` |
| `cmtOffscreen` | `'Елемента зараз немає на екрані'` | `'The element is not on screen now'` |
| `cmtShot` | `'Знімок у момент коментаря'` | `'Snapshot at comment time'` |
| `cmtNoTime` | `'час невідомий'` | `'time unknown'` |
| `cmtModeText` | `'текст'` | `'text'` |
| `cmtModeArea` | `'область'` | `'area'` |
| `cmtModeMulti` | `(n) => \`елементів: ${n}\`` | `(n) => \`${n} elements\`` |

- [ ] **Step 2: Тести моделі, що падають** — `tests/comments-model.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";

import { commentSections, matchQuery, openCount, shotSrc } from "../app/comments-model.js";

const C = (o) => ({ id: o.id, n: o.n, text: o.text || "", author: o.author || "Ліна", ts: o.ts || "",
  status: o.status || "open", scope: o.scope || "current", where: "here", meta: o.meta || {} });
const SNAP = { version: "3", iteration: "3", comments: [
  C({ id: "a", n: 1, text: "Кнопка ширша" }),
  C({ id: "b", n: 3, text: "Відступ зверху", author: "Олег" }),
  C({ id: "c", n: 2, text: "Старе", scope: "earlier" }),
  C({ id: "d", n: 4, text: "Готово раніше", status: "resolved", meta: { resolvedAt: 100 } }),
  C({ id: "e", n: 5, text: "Готово пізніше", status: "resolved", meta: { resolvedAt: 200 } }),
  C({ id: "f", n: 6, text: "Чужа ітерація закрита", status: "resolved", scope: "earlier" }),
  C({ id: "g", n: 7, text: "Інше", scope: "other" }),
] };

test("розділи: відкриті й попередні — новіші вгорі, закриті — за часом закриття", () => {
  const s = commentSections(SNAP);
  assert.deepEqual(s.open.map((c) => c.id), ["b", "a"]);
  assert.deepEqual(s.earlier.map((c) => c.id), ["c"]);
  assert.deepEqual(s.closed.map((c) => c.id), ["e", "d"]);
});

test("пошук: #N — точний номер, інакше підрядок без регістру по номеру, тексту, автору, часу, цитаті", () => {
  assert.deepEqual(commentSections(SNAP, { query: "#3" }).open.map((c) => c.id), ["b"]);
  assert.deepEqual(commentSections(SNAP, { query: "#30" }).open, []);
  assert.deepEqual(commentSections(SNAP, { query: "олег" }).open.map((c) => c.id), ["b"]);
  assert.equal(matchQuery(C({ n: 9, meta: { sel: "Купити зараз" } }), "купити"), true);
  assert.equal(matchQuery(C({ n: 9 }), "   "), true);
});

test("лічильник — відкриті поточні, без пошуку; порожній знімок — нуль", () => {
  assert.equal(openCount(SNAP), 2);
  assert.equal(openCount(null), 0);
  assert.equal(openCount({ comments: "зламано" }), 0);
});

test("мініатюра — лише data:image і http(s)", () => {
  assert.equal(shotSrc({ meta: { shot: "data:image/png;base64,AAA" } }), "data:image/png;base64,AAA");
  assert.equal(shotSrc({ meta: { shotUrl: "https://x.example/s.png" } }), "https://x.example/s.png");
  assert.equal(shotSrc({ meta: { shot: "javascript:alert(1)" } }), null);
  assert.equal(shotSrc({ meta: { shot: "data:text/html;base64,AAA" } }), null);
  assert.equal(shotSrc({}), null);
});
```

- [ ] **Step 3: `app/comments-model.js`:**

```js
/**
 * Модель панелі коментарів оболонки (Deai 0.26.0, етап Б1). Чиста: ні DOM, ні мережі. Вхід — знімок коментатора
 * (`CommentLayer.snapshot()`: копії коментарів із `n`, `scope`, `where`, `iter`). Що «поточне», вирішує КОМЕНТАТОР
 * (`scope`), а не ця модель — друга реалізація того самого знання розійшлась би мовчки (принцип 6 `PRODUCT.md`).
 */
const SHOT_RE = /^(data:image\/(png|jpe?g|webp|gif);base64,|https?:\/\/)/i;

const list = (snapshot) => (snapshot && Array.isArray(snapshot.comments) ? snapshot.comments : []);
const byNewest = (a, b) => (Number(b.n) || 0) - (Number(a.n) || 0);
const closedAt = (c) => Number((c.meta && c.meta.resolvedAt) || c.resolvedAt || 0) || 0;

/** Пошук як у панелі коментатора: `#N` — точний номер; інакше підрядок без регістру в «#n текст автор час цитата». */
export function matchQuery(c, query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return true;
  const num = /^#(\d+)$/.exec(q);
  if (num) return Number(c.n) === Number(num[1]);
  const sel = (c.meta && c.meta.sel) || "";
  return `#${c.n} ${c.text || ""} ${c.author || ""} ${c.ts || ""} ${sel}`.toLowerCase().includes(q);
}

/** `{open, earlier, closed}`: відкриті поточні, відкриті попередніх ітерацій, закриті поточні. */
export function commentSections(snapshot, { query = "" } = {}) {
  const hit = (c) => matchQuery(c, query);
  const all = list(snapshot);
  return {
    open: all.filter((c) => c.status === "open" && c.scope === "current" && hit(c)).sort(byNewest),
    earlier: all.filter((c) => c.status === "open" && c.scope === "earlier" && hit(c)).sort(byNewest),
    closed: all.filter((c) => c.status === "resolved" && c.scope === "current" && hit(c))
      .sort((a, b) => (closedAt(b) - closedAt(a)) || byNewest(a, b)),
  };
}

/** Відкриті поточні — число на кнопці острівця. */
export function openCount(snapshot) {
  return list(snapshot).filter((c) => c.status === "open" && c.scope === "current").length;
}

/** `src` мініатюри або `null`: лише растрові `data:image/…;base64,` і `http(s)://` (не `javascript:`, не `data:text/html`). */
export function shotSrc(c) {
  const s = c && c.meta && (c.meta.shot || c.meta.shotUrl);
  return typeof s === "string" && SHOT_RE.test(s) ? s : null;
}
```

Тести моделі — PASS.

- [ ] **Step 4: Тести розмітки, що падають** — `tests/comments-view.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";

import { commentsPanelHTML } from "../app/comments-view.js";
import { setLang } from "../app/i18n.js";

setLang("uk");
const C = (o) => ({ id: o.id, n: o.n, text: o.text || "т", author: o.author || "Ліна", ts: "13.11.2026 10:00",
  status: o.status || "open", scope: o.scope || "current", where: o.where || "here", iter: o.iter || "3",
  resolvedV: o.resolvedV ?? null, resolveReason: o.resolveReason ?? null, meta: o.meta || {} });
const base = (over = {}) => ({ snapshot: { version: "3", iteration: "3", comments: [] }, query: "", selectedId: null,
  editingId: null, expanded: { earlier: false, closed: false }, channel: "local", team: false, down: null, ...over });

test("порожньо — запрошення; немає знімка — завантаження; є відмова — її текст", () => {
  assert.match(commentsPanelHTML(base()), /Коментарів ще немає/);
  assert.match(commentsPanelHTML(base({ snapshot: null })), /Коментатор завантажується/);
  assert.match(commentsPanelHTML(base({ snapshot: null, down: "адаптер не завантажився" })), /Коментарі недоступні: адаптер не завантажився/);
});

test("тексти людей екрануються, шкідлива мініатюра не малюється", () => {
  const html = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [
    C({ id: "x", n: 1, text: "<img src=x onerror=alert(1)>", author: "<b>я</b>", meta: { shot: "javascript:alert(1)", sel: "<i>" } }),
  ] } }));
  assert.equal(html.includes("<img src=x"), false);
  assert.equal(html.includes("<b>я</b>"), false);
  assert.equal(html.includes("javascript:"), false);
  assert.match(html, /&lt;img src=x/);
});

test("картка відкритого: номер, автор, дії Показати/Редагувати/Закрити/Видалити; виділена — клас", () => {
  const html = commentsPanelHTML(base({ selectedId: "a", snapshot: { iteration: "3", comments: [C({ id: "a", n: 2 })] } }));
  assert.match(html, /class="cmt-card cmt-card--sel"[^>]*data-cid="a"/);
  for (const act of ["cmtshow", "cmtedit", "cmtres", "cmtdel"]) assert.match(html, new RegExp(`data-act="${act}" data-val="a"`));
  assert.match(html, /<span class="cmt-n">2<\/span>/);
});

test("редагування — textarea з текстом і Зберегти/Скасувати", () => {
  const html = commentsPanelHTML(base({ editingId: "a", snapshot: { iteration: "3", comments: [C({ id: "a", n: 1, text: "було" })] } }));
  assert.match(html, /<textarea class="cmt-edit"[^>]*>було<\/textarea>/);
  assert.match(html, /data-act="cmteditsave" data-val="a"/);
});

test("закрита картка: «Зроблено · Іт.N» і що зробив Claude; без resolvedV — «Закрито»", () => {
  const comments = [C({ id: "d", n: 1, status: "resolved", resolvedV: 2, resolveReason: "Зробив кнопку ширшою" }),
                    C({ id: "e", n: 2, status: "resolved" })];
  const html = commentsPanelHTML(base({ expanded: { earlier: false, closed: true }, snapshot: { iteration: "3", comments } }));
  assert.match(html, /Зроблено · Іт\.2/);
  assert.match(html, /Зробив кнопку ширшою/);
  assert.match(html, /Закрито/);
  assert.match(html, /data-act="cmtreopen" data-val="d"/);
});

test("попередні й закриті згорнуті: заголовок із числом, карток нема до розгортання", () => {
  const comments = [C({ id: "o", n: 1, scope: "earlier", iter: "2" }), C({ id: "z", n: 2, status: "resolved" })];
  const folded = commentsPanelHTML(base({ snapshot: { iteration: "3", comments } }));
  assert.match(folded, /data-act="cmtsec" data-val="earlier" aria-expanded="false"/);
  assert.match(folded, /З попередніх ітерацій \(1\)/);
  assert.equal(folded.includes('data-cid="o"'), false);
  const open = commentsPanelHTML(base({ expanded: { earlier: true, closed: false }, snapshot: { iteration: "3", comments } }));
  assert.match(open, /data-act="cmtcarry" data-val="o"[^>]*>Перенести в Іт\.3/);
  assert.match(open, /Іт\.2/);
});

test("перемикач каналу — лише коли є командний модуль; активний — aria-pressed", () => {
  assert.equal(commentsPanelHTML(base()).includes('data-act="cmtch"'), false);
  const html = commentsPanelHTML(base({ team: true, channel: "project" }));
  assert.match(html, /data-act="cmtch" data-val="local" aria-pressed="false"/);
  assert.match(html, /data-act="cmtch" data-val="project" aria-pressed="true"/);
});

test("інша сторінка й елемент поза екраном — підписані", () => {
  const html = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [
    C({ id: "a", n: 1, where: "elsewhere" }), C({ id: "b", n: 2, where: "offscreen" })] } }));
  assert.match(html, /На іншій сторінці/);
  assert.match(html, /Елемента зараз немає на екрані/);
});

test("пошук без збігів — «Нічого не знайдено.»; поле пошуку несе запит", () => {
  const html = commentsPanelHTML(base({ query: "\"><x", snapshot: { iteration: "3", comments: [C({ id: "a", n: 1 })] } }));
  assert.match(html, /Нічого не знайдено/);
  assert.match(html, /id="cmt-q"[^>]*value="&quot;&gt;&lt;x"/);
});
```

- [ ] **Step 5: `app/comments-view.js`:**

```js
/**
 * Розмітка правої панелі «Коментарі» (Deai 0.26.0, етап Б1). Чиста: рядок HTML зі стану; дії — `data-act` для
 * `BAR_ACTIONS` (делегація з `#cmt-panel` в `app.js`). Класи — лише `cmt-*`: `pin`/`cp`/`cbadge` належать коментатору
 * (`tests/principle6.test.mjs`). Тексти людей — лише через `esc()`; мініатюра — лише з `shotSrc`.
 */
import { commentSections, openCount, shotSrc } from "./comments-model.js";
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

const btn = (act, val, label, icon) => `<button type="button" class="cmt-act" data-act="${act}" data-val="${esc(val)}"`
  + ` aria-label="${esc(label)}" title="${esc(label)}">${icon ? ico(icon) : esc(label)}</button>`;

function modeTag(m) {
  if (!m || !m.mode || m.mode === "element") return "";
  const txt = m.mode === "multi" ? t("cmtModeMulti", m.count || 0) : m.mode === "area" ? t("cmtModeArea") : t("cmtModeText");
  return `<span class="cmt-tag">${esc(txt)}</span>`;
}

function cardHTML(c, st, kind) {
  const m = c.meta || {};
  const sel = c.id === st.selectedId ? " cmt-card--sel" : "";
  const closed = c.status === "resolved" ? " cmt-card--closed" : "";
  const head = `<header class="cmt-head"><span class="cmt-n">${esc(c.n)}</span><span class="cmt-who">${esc(c.author || "")}</span>`
    + `${modeTag(m)}<span class="cmt-when">${esc(c.ts || t("cmtNoTime"))}</span></header>`;
  const body = c.id === st.editingId
    ? `<textarea class="cmt-edit" data-val="${esc(c.id)}" aria-label="${esc(t("cmtEdit"))}">${esc(c.text || "")}</textarea>`
      + `<div class="cmt-acts">${btn("cmteditsave", c.id, t("cmtSave"))}${btn("cmteditcancel", c.id, t("cmtCancel"))}</div>`
    : `<p class="cmt-text">${esc(c.text || "")}</p>`;
  const quote = m.sel ? `<p class="cmt-sel">“${esc(String(m.sel).slice(0, 120))}”</p>` : "";
  const vp = m.viewport && m.viewport.w ? `<p class="cmt-vp">${esc(`${m.viewport.w}×${m.viewport.h || "?"}`)}</p>` : "";
  const where = c.where === "elsewhere" ? `<p class="cmt-note">${esc(t("cmtElsewhere"))}</p>`
    : c.where === "offscreen" ? `<p class="cmt-note">${esc(t("cmtOffscreen"))}</p>` : "";
  const src = shotSrc(c);
  const shot = src ? `<button type="button" class="cmt-shot" data-act="cmtshot" data-val="${esc(c.id)}" aria-label="${esc(t("cmtShot"))}">`
    + `<img src="${esc(src)}" alt="${esc(t("cmtShot"))}"></button>` : "";
  const done = c.status === "resolved"
    ? `<p class="cmt-done">${esc(c.resolvedV != null ? t("cmtDone", c.resolvedV) : t("cmtClosedPlain"))}</p>`
      + (c.resolveReason ? `<p class="cmt-reason">${esc(c.resolveReason)}</p>` : "")
    : "";
  const iter = kind === "earlier" && c.iter != null ? `<p class="cmt-iter">${esc(t("cmtIter", c.iter))}</p>` : "";
  let acts = "";
  if (c.id !== st.editingId) {
    if (kind === "open") acts = btn("cmtshow", c.id, t("cmtShow")) + btn("cmtedit", c.id, t("cmtEdit"), "pencil")
      + btn("cmtres", c.id, t("cmtResolve"), "check") + btn("cmtdel", c.id, t("cmtDelete"), "trash");
    else if (kind === "earlier") acts = btn("cmtcarry", c.id, t("cmtCarry", st.snapshot.iteration))
      + btn("cmtdel", c.id, t("cmtDelete"), "trash");
    else acts = btn("cmtreopen", c.id, t("cmtReopen"), "refresh") + btn("cmtdel", c.id, t("cmtDelete"), "trash");
    acts = `<div class="cmt-acts">${acts}</div>`;
  }
  return `<article class="cmt-card${sel}${closed}" data-cid="${esc(c.id)}">${head}${iter}${body}${quote}${vp}${where}${shot}${done}${acts}</article>`;
}

function foldHTML(key, title, items, st, kind) {
  if (!items.length) return "";
  const open = !!(st.expanded && st.expanded[key]);
  return `<section class="cmt-sec cmt-sec--fold"><button type="button" class="cmt-fold" data-act="cmtsec" data-val="${key}"`
    + ` aria-expanded="${open}">${ico(open ? "chevdown" : "chevright")}${esc(`${title} (${items.length})`)}</button>`
    + (open ? items.map((c) => cardHTML(c, st, kind)).join("") : "") + "</section>";
}

/** st: {snapshot, query, selectedId, editingId, expanded:{earlier,closed}, channel:'local'|'project', team, down} */
export function commentsPanelHTML(st) {
  const total = openCount(st.snapshot);
  const seg = st.team
    ? `<div class="cmt-ch" role="group" aria-label="${esc(t("cmtChannel"))}">`
      + ["local", "project"].map((ch) => `<button type="button" data-act="cmtch" data-val="${ch}" aria-pressed="${st.channel === ch}">`
        + `${esc(t(ch === "local" ? "cmtChLocal" : "cmtChTeam"))}</button>`).join("") + "</div>"
    : "";
  const hidden = !!(st.snapshot && st.snapshot.pinsHidden);
  const pins = `<button type="button" class="icon-btn" data-act="cmtpins" aria-pressed="${hidden}"`
    + ` aria-label="${esc(t(hidden ? "cmtPinsShow" : "cmtPinsHide"))}" title="${esc(t(hidden ? "cmtPinsShow" : "cmtPinsHide"))}">${ico("eye")}</button>`;
  const top = `<div class="insp-top cmt-top"><span class="panel-title">${esc(t("cmtTitle"))}</span>`
    + `<span class="cmt-total">${total}</span>${seg}${pins}`
    + `<button type="button" class="icon-btn" data-act="comments" aria-label="${esc(t("cmtClose"))}" title="${esc(t("cmtClose"))}">${ico("x")}</button></div>`;
  const search = `<div class="cmt-search"><input type="search" id="cmt-q" value="${esc(st.query || "")}"`
    + ` placeholder="${esc(t("cmtSearch"))}" aria-label="${esc(t("cmtSearch"))}"></div>`;
  let body;
  if (!st.snapshot) {
    body = st.down ? `<p class="cmt-down" role="alert">${esc(t("cmtDown", st.down))}</p>` : `<p class="insp-hint">${esc(t("cmtLoading"))}</p>`;
  } else {
    const s = commentSections(st.snapshot, { query: st.query });
    const none = !s.open.length && !s.earlier.length && !s.closed.length;
    const empty = none ? `<p class="insp-hint">${esc(t(st.query ? "cmtNoMatch" : "cmtEmpty"))}</p>` : "";
    const open = `<section class="cmt-sec" aria-label="${esc(t("cmtOpen"))}"><h3 class="cmt-h">${esc(t("cmtOpen"))}`
      + ` <span>${s.open.length}</span></h3>${s.open.map((c) => cardHTML(c, st, "open")).join("")}</section>`;
    body = empty + open + foldHTML("earlier", t("cmtEarlier"), s.earlier, st, "earlier")
      + foldHTML("closed", t("cmtClosed"), s.closed, st, "closed");
  }
  return `${top}${search}<div class="insp-body cmt-body">${body}</div>`;
}
```

Іконки `pencil`, `check`, `refresh`, `trash`, `eye`, `x`, `chevdown`, `chevright` уже є в `app/icons.js`. `esc` — з `app/esc.js` (екранує `& < > "` — годиться і для тексту, і для атрибутів у подвійних лапках). Тести розмітки — PASS.

- [ ] **Step 6: Мутації:** у `cardHTML` прибрати `esc(` навколо `c.text` → тест екранування FAIL; у `shotSrc` замінити регексп на `/./` → тест мініатюри FAIL; у `foldHTML` малювати картки завжди → тест згортання FAIL.

- [ ] **Step 7: Прогін:** JS повністю (`i18n-keys`, `i18n-literals`, `icons`, `principle6` — зелені).

- [ ] **Step 8: Коміт** `feat(0.26.0): модель і розмітка панелі коментарів (чисті модулі)` — шляхи `app/comments-model.js app/comments-view.js app/i18n.js tests/comments-model.test.mjs tests/comments-view.test.mjs`.

---

### Task 7: Проводка в «Макеті»

**Files:**
- Modify: `app/island.js`, `tests/island.test.mjs`
- Modify: `app/index.html` (+ `#cmt-panel`), `app/styles.css`
- Modify: `app/app.js`, `app/shell-palette.js`, `tests/shell-palette.test.mjs`
- Create: `tests/live/comments-panel.test.mjs`

- [ ] **Step 1: Острівець — тест, що падає** (`tests/island.test.mjs`, дописати):

```js
test("кнопка «Коментарі» — у задачі в обох видах, перед інспектором; число відкритих", () => {
  const lay = islandToolsHTML({ screen: "task", mode: "layout", commentsOn: true, commentsCount: 3 });
  assert.match(lay, /data-act="comments" aria-pressed="true"/);
  assert.ok(lay.indexOf('data-act="comments"') < lay.indexOf('data-act="inspector"'));
  assert.match(lay, /<span class="isl-count" aria-hidden="true">3<\/span>/);
  const ov = islandToolsHTML({ screen: "task", mode: "overview", commentsCount: 0 });
  assert.match(ov, /data-act="comments" aria-pressed="false"/);
  assert.equal(ov.includes("isl-count"), false);
  assert.equal(ov.includes('data-act="inspector"'), false);
  assert.equal(islandToolsHTML({ screen: "home" }).includes('data-act="comments"'), false);
  assert.match(islandToolsHTML({ screen: "task", mode: "layout", commentsCount: 120 }), />99\+</);
});
```

- [ ] **Step 2: `app/island.js`** — сигнатура `islandToolsHTML({ screen = "task", mode = "layout", inspectorOn = false, commentsOn = false, commentsCount = 0 } = {})`; тіло:

```js
  const parts = [];
  if (screen === "task") {
    const n = commentsCount > 0
      ? `<span class="isl-count" aria-hidden="true">${commentsCount > 99 ? "99+" : commentsCount}</span>` : "";
    parts.push(`<button class="isl-btn${commentsOn ? " isl-btn--on" : ""}" data-act="comments" aria-pressed="${commentsOn}"`
      + ` aria-label="${esc(t("cmtIsland", commentsCount))}" title="${esc(t("cmtKey"))}">${ico("comment")}${n}</button>`);
    if (mode === "layout") {
      parts.push(`<button class="isl-btn${inspectorOn ? " isl-btn--on" : ""}" data-act="inspector" aria-pressed="${inspectorOn}"`
        + ` aria-label="${esc(t("inspector"))}" title="${esc(t("inspectorKey"))}">${ico("inspect")}</button>`);
    }
    parts.push('<span class="isl-sep" aria-hidden="true"></span>');
  }
  const fb = esc(t("fbIsland"));
  parts.push(`<button class="isl-btn" data-act="feedback" aria-label="${fb}" title="${fb}">${ico("bug")}</button>`);
  return parts.join("");
```

Докстрінг файла: «Кнопка коментарів — етап Б» → «Коментарі (обидва види) | інспектор (лише «Макет») | баг/ідея». Старі тести острівця, що чекали `isl-sep` лише в «Макеті», виправити в цій задачі (причина — у звіт). Тести острівця — PASS.

- [ ] **Step 3: Вузол і стилі.** `app/index.html`: після `<div id="insp-panel" class="insp" hidden></div>` — `<div id="cmt-panel" class="insp cmt" hidden aria-label="Коментарі"></div>` (атрибут перекладає `app.js` при старті й зміні мови: `cmtEl.setAttribute('aria-label', t('cmtTitle'))`). `app/styles.css`:
  - до правила `html.cv-clean #tabs,…,html.cv-clean #insp-panel,…` додати `html.cv-clean #cmt-panel`;
  - поруч із `body.with-insp …` (рядки 705–711) — ті самі три правила для `with-cmt`:
    ```css
    body.with-cmt .cv-stage,body.with-cmt .cv-canvas,body.with-cmt .cv-hud{width:calc(100% - var(--insp-w))}
    body.with-panel.with-cmt .cv-stage,
    body.with-panel.with-cmt .cv-canvas,
    body.with-panel.with-cmt .cv-hud{width:calc(100% - var(--panel-w) - var(--insp-w))}
    body.with-panel.panel-collapsed.with-cmt .cv-stage,
    body.with-panel.panel-collapsed.with-cmt .cv-canvas,
    body.with-panel.panel-collapsed.with-cmt .cv-hud{width:calc(100% - var(--panel-rail-w) - var(--insp-w))}
    ```
  - стилі `.cmt-*` після блоку `.insp-*`: картка (`.cmt-card` — фон `var(--s3)` чи найближчий наявний токен поверхні, рамка `var(--line)`, радіус як у `.insp-*`), `.cmt-card--sel` (рамка акцентним токеном, яким підсвічено активну вкладку в `.tabs`), `.cmt-card--closed` (приглушений текст `var(--dim)`), `.cmt-n` (кружок з номером), `.cmt-acts` (ряд кнопок), `.cmt-shot img{max-width:100%;max-height:120px}`, `.cmt-search input{width:100%}`, `.cmt-ch` (сегмент як `.seg` у смузі, якщо такий є — ті самі правила через спільний селектор), `.isl-count` (маленьке число справа вгорі кнопки острівця, нейтральний токен). Лише наявні токени (`css-guards`).

- [ ] **Step 4: Проводка в `app/app.js`** (усе через `t()`, без кириличних літералів):
  - імпорти: `import { commentsPanelHTML } from './comments-view.js';` і `import { openCount } from './comments-model.js';`;
  - стан поруч з `inspEl`: `const cmtEl = document.getElementById('cmt-panel');` і
    ```js
    /* Панель «Коментарі» (0.26.0). Відкрита панель = увімкнений режим коментування (як у Figma). Знімок — від
       коментатора поточного виду (рамка в «Макеті», полотно в «Огляді»); сховища панель не читає (спека Б-Р4). */
    let cmtOpen = false, cmtSnap = null, cmtSel = null, cmtQuery = '', cmtEditing = null, frameCmtReady = false;
    const cmtExpanded = { earlier: false, closed: false };
    const CMT_EVENTS = new Set(['ready', 'change', 'select', 'mode']);
    ```
  - функції:
    ```js
    /** Живий коментатор поточного виду або `null` (ще вантажиться / виду нема). */
    function cmtLayer() {
      if (mode === 'canvas') return ovc.layer || null;
      if (!frameCmtReady) return null;
      try { return frame.contentWindow?.CommentLayer || null; } catch (e) { return null; }
    }
    /** Текст банера `__clDown` у рамці (коментатор не піднявся) — у панель, щоб людина бачила причину. */
    function cmtDown() {
      if (mode === 'canvas') return null;
      try { return frame.contentDocument?.getElementById('cl-down')?.textContent || null; } catch (e) { return null; }
    }
    function paintComments() {
      const html = cmtOpen && !homeOpen ? commentsPanelHTML({ snapshot: cmtSnap, query: cmtQuery, selectedId: cmtSel,
        editingId: cmtEditing, expanded: cmtExpanded, channel: effMode(), team: !noTeamComments(),
        down: cmtSnap ? null : cmtDown() }) : '';
      /* Фокус і каретку поля пошуку / редагування — назад після перезапису (той самий прийом, що в `paintInsp`). */
      const act = document.activeElement;
      const keep = act && cmtEl.contains(act) && (act.id === 'cmt-q' || act.classList.contains('cmt-edit'))
        ? { sel: act.id === 'cmt-q' ? '#cmt-q' : '.cmt-edit', range: [act.selectionStart, act.selectionEnd] } : null;
      const top = cmtEl.querySelector('.cmt-body')?.scrollTop || 0;
      cmtEl.hidden = !html;
      document.body.classList.toggle('with-cmt', !!html);
      cmtEl.innerHTML = html;
      const body = cmtEl.querySelector('.cmt-body');
      if (body && top) body.scrollTop = top;
      if (keep) { const el = cmtEl.querySelector(keep.sel); el?.focus(); try { el?.setSelectionRange(...keep.range); } catch (e) {} }
      if (cmtSel) cmtEl.querySelector(`[data-cid="${CSS.escape(cmtSel)}"]`)?.scrollIntoView({ block: 'nearest' });
      paintIsland();
    }
    function setCommentsOpen(on) {
      on = !!on;
      if (on) { const api = inspectorApi(); if (api?.on) { api.set(false); paintBar(); } }
      cmtOpen = on;
      if (!on) { cmtSel = null; cmtEditing = null; }
      const L = cmtLayer();
      if (L && !!L.commentMode !== on) L.setCommentMode(on);
      paintComments();
    }
    /** Подія коментатора: `src` — 'frame' чи 'canvas'; чужий вид — ігнор (поправка 11). */
    function onCommentsEvent(src, m) {
      if ((src === 'canvas') !== (mode === 'canvas')) return;
      if (m.ev === 'ready') {
        if (src === 'frame') frameCmtReady = true;
        const L = cmtLayer();
        if (L) { cmtSnap = L.snapshot(); if (cmtOpen) L.setCommentMode(true); }
        paintComments();
      } else if (m.ev === 'change') {
        if (m.snapshot && Array.isArray(m.snapshot.comments)) { cmtSnap = m.snapshot; paintComments(); }
      } else if (m.ev === 'select') {
        cmtSel = typeof m.id === 'string' ? m.id : null;
        if (!cmtOpen) setCommentsOpen(true); else paintComments();
      } else if (m.ev === 'mode') {
        if (!m.on && cmtOpen) { cmtOpen = false; cmtSel = null; cmtEditing = null; paintComments(); }
        else if (m.on && !cmtOpen) { cmtOpen = true; paintComments(); }
      }
    }
    ```
  - приймач посилок (поруч із приймачем `dc-audience`, з тим самим коментарем-попередженням про джерело):
    ```js
    window.addEventListener('message', (ev) => {
      if (ev.source !== frame.contentWindow) return;
      const m = ev.data;
      if (!m || m.type !== 'dc-comments' || !CMT_EVENTS.has(m.ev)) return;
      onCommentsEvent('frame', m);
    });
    ```
  - `frame.src`: у обох гілках присвоєння (`render`, ~`app.js:6354`) додати `&host=1` (після `ch=…`, ПЕРЕД `stateQuery(...)` — хвіст стану мусить лишитись останнім). Безпосередньо ПЕРЕД присвоєнням: `frameCmtReady = false; if (mode !== 'canvas') cmtSnap = null;`.
  - клавіші на вікні рамки — на кожне `load`:
    ```js
    /* C і H — клавіші оболонки (поправка 4): коментатор у режимі хоста їх не слухає, тож ловимо й тоді, коли фокус у макеті. */
    function frameCmtKey(ev) {
      if (ev.metaKey || ev.ctrlKey || ev.altKey || ev.shiftKey) return;
      const tg = ev.target;
      if (tg && (['INPUT', 'TEXTAREA', 'SELECT'].includes(tg.tagName) || tg.isContentEditable)) return;
      const k = (ev.key || '').toLowerCase();
      if (k === 'c' || ev.code === 'KeyC') { ev.preventDefault(); ev.stopPropagation(); BAR_ACTIONS.comments(); }
      else if ((k === 'h' || ev.code === 'KeyH') && cmtOpen) { ev.preventDefault(); ev.stopPropagation(); BAR_ACTIONS.cmtpins(); }
    }
    frame.addEventListener('load', () => { try { frame.contentWindow.addEventListener('keydown', frameCmtKey, true); } catch (e) { /* чужий документ */ } });
    ```
  - глобальний обробник клавіш (`document.addEventListener('keydown', …)` ~`app.js:7634`): ПІСЛЯ рядка `if (homeOpen) return;` —
    ```js
    if (!meta && !ev.altKey && !ev.shiftKey && (ev.key.toLowerCase() === 'c' || ev.code === 'KeyC')) {
      ev.preventDefault(); BAR_ACTIONS.comments(); return;
    }
    if (cmtOpen && !meta && !ev.altKey && !ev.shiftKey && (ev.key.toLowerCase() === 'h' || ev.code === 'KeyH')) {
      ev.preventDefault(); BAR_ACTIONS.cmtpins(); return;
    }
    if (cmtOpen && ev.key === 'Escape') { setCommentsOpen(false); return; }
    ```
    (`typing` вище вже повертає для полів вводу — C у пошуку панелі друкується.)
  - `BAR_ACTIONS` (поруч з `inspector`):
    ```js
    comments: () => { if (!homeOpen) setCommentsOpen(!cmtOpen); },
    cmtshow: (id) => { cmtSel = id; cmtLayer()?.focus(id); paintComments(); },
    cmtres: (id) => { cmtLayer()?.resolveComment(id); },
    cmtreopen: (id) => { cmtLayer()?.reopenComment(id); },
    cmtdel: (id) => { cmtLayer()?.removeComment(id); },
    cmtedit: (id) => { cmtEditing = id; paintComments(); cmtEl.querySelector('.cmt-edit')?.focus(); },
    cmteditsave: (id) => { const ta = cmtEl.querySelector('.cmt-edit'); if (cmtLayer()?.editComment(id, ta?.value)) cmtEditing = null; paintComments(); },
    cmteditcancel: () => { cmtEditing = null; paintComments(); },
    cmtcarry: (id) => { cmtLayer()?.carry(id); },
    cmtshot: (id) => { cmtLayer()?.openShot(id); },
    cmtsec: (k) => { if (k in cmtExpanded) { cmtExpanded[k] = !cmtExpanded[k]; paintComments(); } },
    cmtch: (ch) => { setAudience(ch); },
    cmtpins: () => { cmtLayer()?.togglePins(); },
    ```
    `inspector`: перед `api.set(!api.on)` — `if (!api.on && cmtOpen) setCommentsOpen(false);`.
  - делегація з `#cmt-panel` (як з `#insp-panel`, `app.js:6056`): `click` → `[data-act]` (пропуск `INPUT`/`TEXTAREA`) → `BAR_ACTIONS[act]?.(val, el, ev)`; `input` на `#cmt-q` → `cmtQuery = ev.target.value; paintComments();`; `keydown` у `.cmt-edit`: `⌘/Ctrl+Enter` → `cmteditsave`, `Escape` → `cmteditcancel` (+ `stopPropagation`, щоб глобальний Esc не закрив панель).
  - `paintIsland()`: передати `commentsOn: cmtOpen, commentsCount: openCount(cmtSnap)`.
  - `enterHome(...)`: на початку `if (cmtOpen) setCommentsOpen(false);`.
  - зміна мови (там, де перекладаються `islandEl`/`#canvas-hint`): `cmtEl.setAttribute('aria-label', t('cmtTitle')); paintComments();`.
- [ ] **Step 5: Палітра й довідка клавіш** (`app/shell-palette.js`): у гілці задачі (поруч з `inspector`, ~рядок 280; для ОБОХ видів) — `out.push({ id: "comments", group: "gView", labelKey: "cmtTitle", icon: "comment", kbd: "C", act: "comments" });`. У довідку клавіш — `C` (коментарі) і `H` (сховати піни, коли панель відкрита) поруч з `I`. Оновити реєстр «підказка → обробник» у `tests/shell-palette.test.mjs` (обробник `C`/`H` — `app.js`). Тести палітри — PASS.

- [ ] **Step 6: Живий тест «Макета»** — `tests/live/comments-panel.test.mjs` (нова смуга портів — перевірити `tests/live-ports.test.mjs`). Каркас сервера й задачі — як у `tests/live/tabs.test.mjs` (`startServer` з `fixture.mjs`, тимчасова домівка). Засів локальних пінів — так, як це роблять наявні живі тести (`offscreen-pin`/`pin-where`: файл `.dc-local-comments.json` у теці задачі, ключ `<задача>/local`; формат звірити з обробником `/api/local-comments` у `serve.py`). Сценарії (кожен — окремий `test`, послідовно, одна сторінка):
  1. в острівці є `[data-act="comments"]` (`aria-pressed="false"`); `frame.src` містить `host=1`; у рамці `.handle` має `display:none`;
  2. клік по кнопці → `#cmt-panel` видимий, `aria-pressed="true"`, `body.with-cmt`, у рамці `.modes.show`;
  3. клік по елементу макета → форма в рамці; текст; «Comment» → у `#cmt-panel` картка з `.cmt-n` = `1` і цим текстом; на кнопці острівця `.isl-count` = `1`;
  4. «Закрити» на картці → розділ «Закриті (1)», `.isl-count` нема; розгорнути → «Повернути» → знову відкрита;
  5. «Редагувати» → `textarea.cmt-edit` → новий текст → «Зберегти» → картка з новим текстом, і файл `.dc-local-comments.json` містить новий текст;
  6. клік по піну в рамці → `.cmt-card--sel` на цій картці;
  7. пошук `#1` → одна картка; `нема-такого` → «Нічого не знайдено.»;
  8. фокус в оболонці (клік по `#bar`), `c` → панель закрита й `.modes.show` нема; клік по макету (режим вимкнено — фокус у рамці), `c` → панель відкрита (обробник на вікні рамки);
  9. кнопка інспектора → панель коментарів закрита; знову `c` → інспектор вимкнено (`inspectorApi().on === false`), панель відкрита;
  10. засіяний закритий пін `{status:'resolved', resolvedV: 1, resolveReason: 'Зробив кнопку ширшою', meta:{iteration:'1', version:'1', seq: 7}}` на ітерації 1 → «Закриті» показують «Зроблено · Іт.1» і «Зробив кнопку ширшою»;
  11. засіяний відкритий пін ітерації 1 при відкритій ітерації 2 → «З попередніх ітерацій (1)» → «Перенести в Іт.2» → у «Відкритих» зʼявилась копія;
  12. підроблена посилка від САМОЇ оболонки (`window.postMessage({type:'dc-comments', ev:'change', snapshot:{iteration:'2', comments:[{id:'f', n:99, text:'фейк', status:'open', scope:'current'}]}}, '*')`) → картки «фейк» нема.

- [ ] **Step 7: Зелено й мутації.** Живий тест — PASS. Мутації: (1) прибрати перевірку `ev.source !== frame.contentWindow` → сценарій 12 FAIL; (2) прибрати `&host=1` з `frame.src` → сценарій 1 FAIL; (3) прибрати `frameCmtKey`-підписку → сценарій 8 FAIL; (4) у `setCommentsOpen` не вимикати інспектор → сценарій 9 FAIL.

- [ ] **Step 8: Прогін:** JS; живі ПОСЛІДОВНО `comments-panel`, `tabs`, `inspector-panel`, `shell-palette`, `claude-status`. Тести, що впали через переїзд ручки в рамці (сторінка тепер із `host=1`), — НЕ в цій задачі: перелічити у звіті, їх мігрує T9 (і `overview-comments` — T8).

- [ ] **Step 9: Коміт** `feat(0.26.0): панель «Коментарі» в оболонці (Макет) — острівець, C/H, ⌘K, картки, закриті з тим, що зробив Claude` — шляхи `app/island.js app/index.html app/styles.css app/app.js app/shell-palette.js tests/island.test.mjs tests/shell-palette.test.mjs tests/live/comments-panel.test.mjs` (+ `tests/live-ports.test.mjs`, якщо правився).

---

### Task 8: «Огляд»

**Files:**
- Modify: `app/overview-comments.js`, `app/app.js`, `tests/overview-comments-module.test.mjs`
- Modify: `tests/live/comments-panel.test.mjs`, `tests/live/overview-comments.test.mjs`

- [ ] **Step 1: Юніт, що падає** (`tests/overview-comments-module.test.mjs`): `start()` передає в `CommentLayer.create().init(...)` поле `host`, яке дорівнює `env.host` (підробити `window.CommentLayer` так, як файл уже робить для інших полів `init`). FAIL.

- [ ] **Step 2: `app/overview-comments.js`:** в `init({...})` додати `host: env.host || undefined,` з коментарем «колбеки панелі оболонки (0.26.0); ручку й панель полотна тримає оболонка». Докстрінг модуля: «коментатор малює все своє — піни, прев'ю, панель, вкладки» → «піни й форму; панель — оболонки (0.26.0)». Юніт — PASS.

- [ ] **Step 3: `app/app.js`:**
  - у виклику `overviewComments({...})` (`app.js:5046`) додати
    ```js
      host: {
        onReady: () => onCommentsEvent('canvas', { ev: 'ready' }),
        onChange: (snapshot) => onCommentsEvent('canvas', { ev: 'change', snapshot }),
        onSelect: (id) => onCommentsEvent('canvas', { ev: 'select', id }),
        onMode: (on) => onCommentsEvent('canvas', { ev: 'mode', on: !!on }),
      },
    ```
    (функції оголошені як `function` — підняті, порядок не важить; якщо `onCommentsEvent` стоїть у модулі нижче як `const` — перенести оголошення вище або обгорнути).
  - перемикання виду в `render` (гілки `mode === 'canvas'` / інакше, ~`app.js:6340`): ПЕРЕД `ovc.enter()` — вимкнути режим коментатора рамки (`try { frame.contentWindow?.CommentLayer?.setCommentMode?.(false); } catch (e) {}`), `cmtSnap = ovc.layer ? ovc.layer.snapshot() : null`, і якщо `cmtOpen` та `ovc.layer` є — `ovc.layer.setCommentMode(true)` (якщо шару ще нема — його `onReady` зробить це сам). У гілці «Макет» після `ovc.leave()` — `cmtSnap = cmtLayer() ? cmtLayer().snapshot() : null`, і якщо `cmtOpen` — `cmtLayer()?.setCommentMode(true)`. Потім `paintComments()`.
  - канвасний коментатор раніше сам ловив C на вікні оболонки (`anchors.active()`); тепер C — глобальний обробник з T7, він діє і на «Огляді» (`cmtLayer()` повертає `ovc.layer`).

- [ ] **Step 4: Живий — дописати в `tests/live/comments-panel.test.mjs`** сценарій «Огляд»: перейти в «Огляд» (дія `view`/`⌥M` — як у наявних тестах «Огляду»; знімки кадрів — як `_t45-fixture.mjs`) → з відкритою панеллю видно ті самі картки; «Показати» на картці → камера рушила (`cvx`/`cvy` змінились, як перевіряє `overview-comments.test.mjs`); `c` закриває й відкриває панель на «Огляді»; клік по кадру в режимі коментування → форма → новий пін → нова картка. Назад у «Макет» → панель показує знімок рамки.

- [ ] **Step 5: Міграція `tests/live/overview-comments.test.mjs`** (23 місця з тіньовим DOM коментатора полотна). Правило: що тест ОХОРОНЯВ — лишається, змінюється лише ДЕ дивимось:
  - `.panel` / `.panel.show` полотна → `#cmt-panel:not([hidden])`;
  - картки `.cp`/`#c<id> .who` → `#cmt-panel [data-cid="<id>"] .cmt-who`;
  - `.cbadge` → `#isl-tools [data-act="comments"] .isl-count` (порожньо = нема вузла);
  - очікування `.handle` полотна — лишаються (ручка будується, лише схована — поправка 1);
  - відкриття панелі кліком по ручці → `BAR_ACTIONS` через кнопку острівця;
  - піни `.pin`, `.pin.off`, композер `.compose` — без змін (їх і далі малює коментатор).
  У звіті — таблиця «рядок → що охороняв → куди переїхав».

- [ ] **Step 6: Мутації:** прибрати `host:` з `init` в `overview-comments.js` → сценарій «Огляд» FAIL (панель коментатора полотна видно / картки в оболонці нема); прибрати фільтр виду в `onCommentsEvent` (перший рядок) → сценарій «назад у Макет» FAIL (картки полотна в «Макеті»). Відновити.

- [ ] **Step 7: Прогін:** JS; живі ПОСЛІДОВНО `comments-panel`, `overview-comments`, `canvas`, `overview-viewports`, `autoshoot`.

- [ ] **Step 8: Коміт** `feat(0.26.0): панель коментарів на «Огляді» — той самий вигляд, піни полотна в оболонці` — шляхи `app/overview-comments.js app/app.js tests/overview-comments-module.test.mjs tests/live/comments-panel.test.mjs tests/live/overview-comments.test.mjs`.

---

### Task 9: Міграція решти живих тестів

**Files:**
- Modify: `tests/live/comments.test.mjs`, `tests/live/comment-audience.test.mjs`, `tests/live/shell-typing.test.mjs`, `tests/live/claude-status.test.mjs`, `tests/live/offscreen-pin.test.mjs`, `tests/live/pin-where.test.mjs` і будь-який інший, що впав у T7/T8 через переїзд ручки (перелік — зі звітів T7/T8 і з повного прогону в Step 1)

- [ ] **Step 1: Повний живий прогін ПОСЛІДОВНО** (`node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/*.test.mjs` під тимчасовим `HOME`, у фоні, чекати за PID; лог — у scratch-теку середовища). Зібрати список падінь.

- [ ] **Step 2: Мігрувати кожен файл** за правилом T8 Step 5 (охорона та сама, змінюється лише місце погляду). Підказки по відомих:
  - `comments.test.mjs`: картки й панель полотна (рядки ~320–330, ~428) → `#cmt-panel`; композер `.compose .save` у рамці — без змін;
  - `comment-audience.test.mjs`: вкладки аудиторій у панелі коментатора (`.aud.active`) → сегмент `#cmt-panel [data-act="cmtch"][aria-pressed="true"]`; перемикання — клік по сегменту; перевірка `frame.src` (`ch=`) і `localStorage` `dc-comment-mode` — лишаються;
  - `shell-typing.test.mjs`: зміст тесту — «набір тексту не вмикає коментування». Тепер C — клавіша оболонки: набір `c` у полі оболонки й у полі макета НЕ відкриває `#cmt-panel` і НЕ дає `.arming` у рамці;
  - `claude-status.test.mjs`: увімкнення режиму кліком по `.handle` → кнопка острівця `[data-act="comments"]`; перевірки `.modes`/`claude-lift` — без змін;
  - `offscreen-pin.test.mjs`: картка-привид `#cghost-1` у панелі коментатора → картка в `#cmt-panel` з підписом «Елемента зараз немає на екрані»; лайтбокс `.cllb img` — і далі в рамці (клік по `.cmt-shot`);
  - `pin-where.test.mjs`: звірити; правити лише якщо падає.

- [ ] **Step 3: Повний живий прогін знову** — 0 падінь. Число тестів = (базова лінія 494) + нові файли (`commenter-host`, `comments-panel`) − 0 (жоден старий тест не видаляється; видалення — лише з поясненням у звіті й погодженням контролера).

- [ ] **Step 4: Коміт** `test(0.26.0): живі тести коментатора дивляться в панель оболонки` — шляхи змінених файлів `tests/live/…`. У звіті — таблиця «файл: що охороняв → куди переїхала перевірка».

---

### Task 10: Документація й версія

**Files:**
- Modify: `CHANGELOG.md`, `package.json` (`"version": "0.26.0"`), `README.md`, `PRODUCT.md`, `docs/modules/comments.md` (якщо описує ручку/панель коментатора)
- Create: `commenter/README.md`

- [ ] **Step 1: `CHANGELOG.md`** — розділ `## [0.26.0] — 13.11.2026` (формат попередніх розділів), українською, коротко:
  - **Додано:** панель «Коментарі» праворуч в оболонці (острівець, клавіша C, ⌘K): відкриті, з попередніх ітерацій (перенести), закриті — із «Зроблено · Іт.N» і поясненням Claude; пошук; H — сховати піни; число відкритих на кнопці острівця; те саме на «Огляді».
  - **Змінено:** ручка й власна панель коментатора в робочому місці сховані (він малює піни й форму); перемикач «Claude / Команда» — у шапці панелі; P більше нічого не робить; джерело коментатора — у репо (`commenter/`), збірка `cd commenter && npm ci && npm run build`.
  - **Виправлено** (прийшло з джерелом): піни не губляться на React-сторінках; видалений локальний пін не повертається.
  - **Не змінено:** опубліковані превʼю й `/commented` без `host=1`.
- [ ] **Step 2: `package.json`** → `0.26.0`. **`README.md`** — розділ про коментарі: де панель, клавіші C/H, як зібрати коментатор. **`commenter/README.md`** — що це, звідки (comment-layer @3581cd0, 13.11.2026), режим хоста (`host`: колбеки й методи), збірка й штамп, охоронець `tests/commenter-stamp.test.mjs`, «копія в design-office живе окремо, Deai — головне джерело для Deai».
- [ ] **Step 3: `PRODUCT.md`** принцип 6: додати одне речення — «з 0.26.0 панель коментарів — оболонки; коментатор у режимі хоста малює лише піни, форму й рядок режимів і повідомляє оболонку подіями». `docs/modules/comments.md` — лише якщо там описано ручку/панель коментатора: та сама поправка.
- [ ] **Step 4: Прогін:** JS (`node --test tests/*.test.mjs && node --test commenter/test/*.test.mjs && node tests/inspector-core.test.mjs`).
- [ ] **Step 5: Коміт** `docs(0.26.0): CHANGELOG 0.26.0, версія, README, commenter/README, принцип 6` — шляхи перелічених файлів (`commenter/README.md` спершу `git add`).

---

### Task 11: Фінальне ревʼю, релізний прогін, перевірка проти живого (контролер)

- [ ] **Step 1: Фінальне ревʼю** (один ревʼюер, Sonnet, англійський бриф) усієї гілки `main..feat/shell-comments` проти спеки (Б1 + поправки цього плану): безпека посилок і розмітки, шлях без `host` байт-у-байт, публікація без `host`, охоронці доведені мутаціями. Ревʼюер працює з копією-архівом гілки, не з деревом. Знахідки → виправлення окремими комітами → повторне ревʼю.
- [ ] **Step 2: Релізний прогін:** JS (усі три набори), Python (3 discover, тимчасовий `HOME`), живі — усі ПОСЛІДОВНО. Детермінізм збірки: `cd commenter && npm ci && npm run build && cd .. && git diff --exit-code app/vendor commenter/build-stamp.json`. Охоронець забороненого списку (`DEAI_FORBIDDEN_LIST=<design-office-transition/scripts/deai-forbidden.txt> DEAI_REQUIRE_FORBIDDEN_LIST=1`) — зелений.
- [ ] **Step 3: Локальний реліз:** злиття в `main` (fast-forward), анотований тег `v0.26.0` (автор neodisa). Живий канвас 8765 — перезапуск на 0.26.0 (зупинка за PID, `start.command >/dev/null 2>&1`, слухач — `lsof -iTCP:8765 -sTCP:LISTEN`).
- [ ] **Step 4: Перевірка проти живого:** справжня задача ЛІГИ — C/острівець відкривають панель; поставити, відредагувати, закрити й повернути ЛОКАЛЬНИЙ пін; `bin/inbox.py` бачить відкритий; «Огляд» показує той самий список; командний канал ЛІГИ — лише ЧИТАННЯ (жодного запису в спільний Supabase); прибрати тестовий пін. Знахідки — фікси з живим тестом і мутацією.
- [ ] **Step 5: Пуш — лише з дозволу власника** (пуш на GitHub = пігулка оновлення всій команді): перевірити `git remote get-url origin`, пушити `main` і тег `v0.26.0`; ніколи — `backup-pre-rewrite-4d1` і `fix/supabase-egress`.
