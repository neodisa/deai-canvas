import assert from "node:assert/strict";
import test from "node:test";

import { DICT } from "../app/i18n.js";
import {
  SPACE_COLORS, colorStep, currentSpace, effectiveCommentMode, freeColor, hasTeamComments, healTarget,
  isReadErrKey, needsWelcome, peekFound, peekRegistered, readErrKey, rovingIndex, shouldRefreshHome, spaceChanged, taskErrKey,
} from "../app/spaces-model.js";

/* Рішення, які приймає `app.js` у просторах (Task 7) і помилка в яких не кидає, а
   мовчки спотворює стан: який канал коментарів діє, чи змінився простір, куди вести
   при «задачі нема», який колір пропонувати. Проводку (DOM, мережа) стережуть
   `tests/spaces-wiring.test.mjs` і живі тести; тут — чисті правила. */

const has = (k) => DICT.uk[k] !== undefined && DICT.en[k] !== undefined;

/* ── канал коментарів ──────────────────────────────────────────────────── */

test("effectiveCommentMode: без інтеграцій `project` затискається в `local`, решта — як є", () => {
  assert.equal(effectiveCommentMode({ integrations: false }, "project"), "local");
  assert.equal(effectiveCommentMode({ integrations: false }, "local"), "local");
  assert.equal(effectiveCommentMode({ integrations: true }, "project"), "project");
  assert.equal(effectiveCommentMode({ integrations: true }, "local"), "local");
});

test("effectiveCommentMode: затискається ЛИШЕ `project`; інше значення (і сміття зі сховища) — як є", () => {
  assert.equal(effectiveCommentMode({ integrations: false }, "щось"), "щось");
  assert.equal(effectiveCommentMode({ integrations: false }, undefined), undefined);
});

test("effectiveCommentMode: невідомий простір каналу не відбирає (рівно `=== false`)", () => {
  for (const space of [null, undefined, {}, { integrations: undefined }, { integrations: 0 },
    { integrations: "" }, { integrations: null }]) {
    assert.equal(effectiveCommentMode(space, "project"), "project", JSON.stringify(space));
  }
});

/* ── командний канал за `capabilities.comments` (2b-2, Task 2) ──────────────────────────────────────
   Командний канал дає РОЛЬ `comments`: зашитий ЛІГА (`'legacy'`) або модуль; `null` — нікого. Прапорець
   `integrations` тепер тільки запасний (відповіді старої форми без `capabilities`). */

test("hasTeamComments: capabilities.comments — null ні, 'legacy' і id модуля так, незалежно від integrations", () => {
  const caps = (comments, integrations) => ({ integrations, capabilities: { publish: null, tokens: null, comments } });
  for (const integrations of [true, false, undefined]) {
    assert.equal(hasTeamComments(caps(null, integrations)), false, `null / ${integrations}`);
    assert.equal(hasTeamComments(caps("legacy", integrations)), true, `legacy / ${integrations}`);
    assert.equal(hasTeamComments(caps("memo-comments", integrations)), true, `module / ${integrations}`);
  }
});

test("hasTeamComments: capabilities з помилкою (space.json не читається) і порожні — каналу нема", () => {
  assert.equal(hasTeamComments({ integrations: false, capabilities: { publish: null, tokens: null, comments: null, error: "space-json-unreadable" } }), false);
  assert.equal(hasTeamComments({ integrations: true, capabilities: {} }), false, "capabilities є, а `comments` у них немає");
});

test("hasTeamComments: стара форма (без capabilities) — за `integrations`, рівно `=== false`", () => {
  assert.equal(hasTeamComments({ integrations: false }), false);
  assert.equal(hasTeamComments({ integrations: true }), true);
  for (const space of [null, undefined, {}, { integrations: undefined }, { integrations: 0 }, { integrations: "" }, { integrations: null }]) {
    assert.equal(hasTeamComments(space), true, JSON.stringify(space));
  }
});

test("effectiveCommentMode: простір без інтеграцій, але з модулем коментарів, лишає `project`", () => {
  const mod = { integrations: false, capabilities: { publish: "static-publish", tokens: null, comments: "memo-comments" } };
  assert.equal(effectiveCommentMode(mod, "project"), "project");
  assert.equal(effectiveCommentMode(mod, "local"), "local");
});

test("effectiveCommentMode: простір з інтеграціями, але без постачальника коментарів, затискає `project`", () => {
  const none = { integrations: true, capabilities: { publish: "legacy", tokens: null, comments: null } };
  assert.equal(effectiveCommentMode(none, "project"), "local");
  assert.equal(effectiveCommentMode({ ...none, capabilities: { ...none.capabilities, comments: "legacy" } }, "project"), "project");
});

/* ── зміна простору ────────────────────────────────────────────────────── */

test("spaceChanged: різні id — змінився; null/undefined — одне й те саме", () => {
  assert.equal(spaceChanged("a", "b"), true);
  assert.equal(spaceChanged("a", "a"), false);
  assert.equal(spaceChanged(null, undefined), false, "шар вимкнено: перемикання задачі не скидає простір");
  assert.equal(spaceChanged(undefined, null), false);
  assert.equal(spaceChanged("a", null), true);
  assert.equal(spaceChanged(null, "a"), true);
});

test("currentSpace: поточний рядок реєстру; висячий current, порожньо, off, null — null", () => {
  const info = { current: "p", spaces: [{ id: "a", name: "A" }, { id: "p", name: "P" }] };
  assert.equal(currentSpace(info).name, "P");
  assert.equal(currentSpace({ ...info, current: "ghost" }), null);
  assert.equal(currentSpace({ current: null, spaces: [] }), null);
  assert.equal(currentSpace({ off: true, current: null, spaces: [] }), null);
  assert.equal(currentSpace(null), null);
  assert.equal(currentSpace({ current: "p" }), null, "нема масиву — не кидає");
});

/* ── висячий current і привітання ──────────────────────────────────────── */

test("healTarget: висячий current → перший ДОСТУПНИЙ; усе недоступне → перший", () => {
  const sp = (id, available) => ({ id, available });
  assert.equal(healTarget({ current: "ghost", spaces: [sp("a", false), sp("b", true), sp("c", true)] }), "b");
  assert.equal(healTarget({ current: "ghost", spaces: [sp("a", false), sp("b", false)] }), "a");
  assert.equal(healTarget({ current: null, spaces: [sp("a", true)] }), "a", "current: null теж висить");
  assert.equal(healTarget({ current: "ghost", spaces: [{ id: "a" }] }), "a", "available нема — доступний");
});

test("healTarget: лікувати нічого — current на місці, просторів нема, шар вимкнено, нема відповіді", () => {
  assert.equal(healTarget({ current: "a", spaces: [{ id: "a" }, { id: "b" }] }), null);
  assert.equal(healTarget({ current: null, spaces: [] }), null);
  assert.equal(healTarget({ off: true, current: null, spaces: [] }), null);
  assert.equal(healTarget({ off: true, current: "x", spaces: [{ id: "a" }] }), null, "off сильніший за все");
  assert.equal(healTarget(null), null);
  assert.equal(healTarget({ current: "ghost" }), null, "нема масиву");
});

test("needsWelcome: просторів нема й шар увімкнено; невідомість і off — не привітання", () => {
  assert.equal(needsWelcome({ current: null, spaces: [] }), true);
  assert.equal(needsWelcome({ current: null, spaces: [{ id: "a" }] }), false);
  assert.equal(needsWelcome({ off: true, current: null, spaces: [] }), false, "шар вимкнено — просторів «нема», але привітання не для того");
  assert.equal(needsWelcome(null), false, "ще не питали / реєстр не читається");
  assert.equal(needsWelcome({ current: null }), false);
});

test("needsWelcome: старий tasks.json є, але не читається (legacy_error) — це не чиста машина, привітання нема", () => {
  const err = { path: "/x/tasks.json", code: "space-unavailable" };
  assert.equal(needsWelcome({ current: null, spaces: [], legacy_error: err }), false,
    "порожній список + зіпсований файл із задачами людини → смуга помилки, а не «створи перший простір»");
  assert.equal(needsWelcome({ current: null, spaces: [] }), true, "без legacy_error — як було");
  assert.equal(needsWelcome({ current: null, spaces: [], legacy_error: null }), true, "порожнє значення не рахується");
  assert.equal(needsWelcome({ off: true, current: null, spaces: [], legacy_error: err }), false);
  assert.equal(needsWelcome({ current: "a", spaces: [{ id: "a" }], legacy_error: err }), false);
});

/* ── причини помилок ───────────────────────────────────────────────────── */

test("readErrKey: коди читання задачі → ключі смуги; невідомий — null; ключі є в обох словниках", () => {
  assert.equal(readErrKey("space-unavailable"), "tasksErrSpaceUnavailable");
  assert.equal(readErrKey("spaces-unreadable"), "tasksErrSpaces");
  for (const bad of ["no-task", "constructor", "__proto__", "", undefined, null]) {
    assert.equal(readErrKey(bad), null, String(bad));
  }
  assert.ok(has("tasksErrSpaceUnavailable") && has("tasksErrSpaces"));
});

test("isReadErrKey: лише ключі «простір не читається»; решта причин смуги (порт, null) — ні", () => {
  assert.equal(isReadErrKey("tasksErrSpaceUnavailable"), true);
  assert.equal(isReadErrKey("tasksErrSpaces"), true);
  for (const k of ["tasksErrPort", "taskErrGeneric", "", null, undefined, "constructor"]) {
    assert.equal(isReadErrKey(k), false, String(k));
  }
  /* Узгодженість з readErrKey: кожен ключ, що її повертає, — «читання простору». */
  for (const code of ["space-unavailable", "spaces-unreadable"]) assert.equal(isReadErrKey(readErrKey(code)), true, code);
});

test("taskErrKey: коди task-new → ключі; невідомий (і мережа) — загальний; ключі є в словниках", () => {
  const map = {
    "task-exists": "idTaken",
    "bad-task-id": "idBad",
    "no-space": "taskErrSpaceGone",
    "unknown-space": "taskErrSpaceGone",
    "space-unavailable": "tasksErrSpaceUnavailable",
    timeout: "formTimeout",
  };
  for (const [code, key] of Object.entries(map)) {
    assert.equal(taskErrKey(code), key, code);
    assert.ok(has(key), `«${key}» бракує в словнику`);
  }
  for (const other of ["gitlab-needs-integrations", "bad-request", "constructor", undefined, null]) {
    assert.equal(taskErrKey(other), "taskErrGeneric", String(other));
  }
  assert.ok(has("taskErrGeneric"));
});

/* ── колір нового простору ─────────────────────────────────────────────── */

test("freeColor: перший невикористаний; усе зайнято — по колу від кількості", () => {
  assert.equal(freeColor([]), "space-1");
  assert.equal(freeColor(undefined), "space-1");
  assert.equal(freeColor([{ color: "space-1" }]), "space-2");
  assert.equal(freeColor([{ color: "space-2" }]), "space-1", "перший вільний, а не наступний за останнім");
  assert.equal(freeColor([{ color: "space-1" }, { color: "space-3" }]), "space-2");
  const all = SPACE_COLORS.map((color) => ({ color }));
  assert.equal(freeColor(all), "space-1");
  assert.equal(freeColor([...all, { color: "space-1" }]), "space-2", "сьомий простір — другий колір");
});

test("freeColor: невідомі кольори в реєстрі за зайняті не рахуються", () => {
  assert.equal(freeColor([{ color: "red" }, { color: undefined }, null]), "space-1");
});

/* ── клавіатура ────────────────────────────────────────────────────────── */

test("rovingIndex: ↓/↑ ходять без обертання, Home/End — крайні", () => {
  assert.equal(rovingIndex(0, 4, "ArrowDown"), 1);
  assert.equal(rovingIndex(3, 4, "ArrowDown"), 3, "з кінця нікуди");
  assert.equal(rovingIndex(2, 4, "ArrowUp"), 1);
  assert.equal(rovingIndex(0, 4, "ArrowUp"), 0, "з початку нікуди");
  assert.equal(rovingIndex(2, 4, "Home"), 0);
  assert.equal(rovingIndex(1, 4, "End"), 3);
});

test("rovingIndex: з -1 (фокус поза списком) ↓ — перший, ↑ — останній; чужа клавіша й порожній список — null", () => {
  assert.equal(rovingIndex(-1, 4, "ArrowDown"), 0);
  assert.equal(rovingIndex(-1, 4, "ArrowUp"), 3);
  assert.equal(rovingIndex(undefined, 4, "ArrowDown"), 0, "не число — як -1");
  for (const key of ["Enter", "a", "Tab", "Escape", " ", "ArrowLeft"]) {
    assert.equal(rovingIndex(1, 4, key), null, key);
  }
  assert.equal(rovingIndex(0, 0, "ArrowDown"), null);
  assert.equal(rovingIndex(0, 0, "Home"), null);
});

test("colorStep: група кружків — коло; стрілки вбік і вниз/вгору; чужа клавіша — null", () => {
  assert.equal(colorStep("space-1", "ArrowRight"), "space-2");
  assert.equal(colorStep("space-1", "ArrowDown"), "space-2");
  assert.equal(colorStep("space-2", "ArrowLeft"), "space-1");
  assert.equal(colorStep("space-2", "ArrowUp"), "space-1");
  assert.equal(colorStep("space-6", "ArrowRight"), "space-1", "з кінця — на початок");
  assert.equal(colorStep("space-1", "ArrowLeft"), "space-6", "з початку — у кінець");
  assert.equal(colorStep("nope", "ArrowRight"), "space-2", "невідомий — як перший");
  for (const key of ["Home", "End", "Enter", " ", "Tab", "a"]) assert.equal(colorStep("space-3", key), null, key);
});

/* ── відповідь peek ────────────────────────────────────────────────────── */

test("peekFound: тека з space.json → {name, color-токен, tasks}; решта — null", () => {
  assert.deepEqual(peekFound({ path: "/p", exists: true, name: "Клієнт", color: "space-4", tasks: 3 }),
    { name: "Клієнт", color: "space-4", tasks: 3 });
  assert.deepEqual(peekFound({ exists: true, name: "A" }), { name: "A", color: "space-1", tasks: 0 },
    "нема кольору й задач — типові");
  assert.equal(peekFound({ exists: true, name: "A", color: "red;position:fixed" }).color, "space-1",
    "колір з файла проходить токен: піде в style");
  for (const none of [null, undefined, {}, { exists: true }, { exists: true, name: "" },
    { exists: true, name: "  " }, { exists: false, error: "path-not-absolute" },
    { exists: true, name: "A", error: "x" }, { name: 5 }]) {
    assert.equal(peekFound(none), null, JSON.stringify(none));
  }
});

test("peekFound: тека, що вже в реєстрі, — НЕ «знайдений простір» (навіть із space.json і назвою)", () => {
  const res = { path: "/Users/me/deai-work/personal", exists: true, name: "Особисте", color: "space-2", tasks: 4 };
  assert.equal(peekFound(res, ["/Users/me/deai-work/personal"]), null);
  assert.equal(peekFound(res, ["/Users/me/deai-work/personal/"]), null, "хвостовий слеш реєстру не обманює");
  assert.deepEqual(peekFound(res, ["/Users/me/deai-work/other"]),
    { name: "Особисте", color: "space-2", tasks: 4 }, "інша зареєстрована тека не заважає");
  assert.deepEqual(peekFound(res), { name: "Особисте", color: "space-2", tasks: 4 }, "без реєстру — як раніше");
});

test("peekRegistered: слово сервера (`registered: true`) — перше; без нього — порівняння з реєстром; помилка peek — ні", () => {
  /* Сервер бачить те, чого клієнт не бачить: варіант регістру на macOS (APFS) — той самий каталог. */
  assert.equal(peekRegistered({ path: "/Users/me/deai-work/CASEa", exists: true, registered: true }, []), true,
    "сервер каже «зареєстрована», реєстру в клієнта нема/інший шлях");
  assert.equal(peekRegistered({ path: "/Users/me/deai-work/CASEa", exists: true, registered: true }, ["/Users/me/deai-work/caseA"]), true);
  /* Ключа нема — запасне порівняння клієнта (як було). */
  assert.equal(peekRegistered({ path: "/p", exists: true }, ["/p/"]), true);
  assert.equal(peekRegistered({ path: "/p", exists: true }, ["/other"]), false);
  assert.equal(peekRegistered({ path: "/p", exists: true }), false);
  /* Лише `true` — слово сервера; усе інше (false, рядок, 1) не є «зареєстрована». */
  for (const v of [false, "true", 1, null]) assert.equal(peekRegistered({ path: "/p", registered: v }, []), false, String(v));
  /* Помилка peek (`error`) — не зареєстрована, навіть коли реєстр збігається чи сервер сказав `registered`. */
  assert.equal(peekRegistered({ path: "/p", exists: false, error: "path-not-absolute" }, ["/p"]), false);
  assert.equal(peekRegistered({ path: "/p", error: "x", registered: true }, []), false);
  assert.equal(peekRegistered(null, ["/p"]), false);
  assert.equal(peekRegistered(undefined), false);
});

test("peekFound: `registered: true` від сервера теж виключає «знайдений простір» — навіть коли реєстр клієнта порожній", () => {
  const res = { path: "/Users/me/deai-work/CASEa", exists: true, name: "A", color: "space-2", tasks: 1, registered: true };
  assert.equal(peekFound(res, []), null, "регістр теки клієнт не бачить, сервер сказав");
  assert.equal(peekFound(res), null);
  const { registered, ...plain } = res;
  assert.deepEqual(peekFound(plain, []), { name: "A", color: "space-2", tasks: 1 }, "без слова сервера — знайдений, як раніше");
});

test("shouldRefreshHome: поки летить примусовий повтор (`forced`) — не перебиваємо його", () => {
  const base = { open: true, visible: true, last: 0, now: 10_000 };
  assert.equal(shouldRefreshHome(base), true);
  assert.equal(shouldRefreshHome({ ...base, forced: true }), false);
  assert.equal(shouldRefreshHome({ ...base, forced: false }), true);
});

test("shouldRefreshHome: лише коли екран відкритий і вікно видиме; парну подію focus+visibilitychange гасить `gap`", () => {
  const base = { open: true, visible: true, last: 0, now: 10_000 };
  assert.equal(shouldRefreshHome(base), true);
  assert.equal(shouldRefreshHome({ ...base, open: false }), false, "екран закрито — нема що освіжати");
  assert.equal(shouldRefreshHome({ ...base, visible: false }), false, "вікно приховане — не будимо мережу");
  assert.equal(shouldRefreshHome({ ...base, last: 9_500 }), false, "друга подія пари в межах gap");
  assert.equal(shouldRefreshHome({ ...base, last: 9_100 }), true, "gap минув");
  assert.equal(shouldRefreshHome({ ...base, last: 9_800, gap: 100 }), true, "gap налаштовується");
  assert.equal(shouldRefreshHome({}), false);
  assert.equal(shouldRefreshHome(), false);
});

test("словник: підказка про зареєстровану теку є в обох мовах", () => {
  assert.ok(has("spaceRegistered"));
  assert.match(DICT.uk.spaceRegistered, /вже додано/);
  assert.match(DICT.en.spaceRegistered, /already been added/);
});
