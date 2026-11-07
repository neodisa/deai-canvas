import assert from "node:assert/strict";
import test from "node:test";

import { DICT } from "../app/i18n.js";
import {
  CHECK_POST_MARGIN_S, FORM_POST_TIMEOUT_MS, ID_MAX, NAME_RE, SPACE_COLORS, defaultSpacePath, isRegisteredPath, spaceColorToken, spaceErrField,
  checkPostTimeoutMs, hasNotify, hasPublish, hasTeamComments, hasVcs, isLegacyPublish, isLegacyVcs, isRemotePublish, previewTarget, publishReaction, pwView, spaceErrKey, spaceRows, spaceSlug, taskErrField, taskErrKey, taskErrShowsReason, taskFormError, taskIdFrom, validTaskId,
} from "../app/spaces-model.js";

/* Модель UI просторів — чисті функції без DOM, `t()` і мережі. Усе, що вони
   повертають як ПІДПИС, — це ІМʼЯ ключа словника (рядок), а `t()` кличе вже
   DOM-шар: той самий контракт, що в `bar-model.js`. Тому кожен ключ тут
   звіряється зі словником в ОБОХ мовах, а не лише з тим, що очікує тест. */

/* ── id задачі з назви ─────────────────────────────────────────────────── */

test("taskIdFrom: латиниця — слаг із назви, кирилиця — task-N", () => {
  assert.equal(taskIdFrom("Landing page v2", []), "landing-page-v2");
  assert.equal(taskIdFrom("Головна", []), "task-1");
  assert.equal(taskIdFrom("Головна", ["task-1"]), "task-2");
});

test("taskIdFrom: нумерація бере ПЕРШУ вільну, а не кількість зайнятих", () => {
  // «task-1» і «task-3» зайняті → вільна «task-2»; кількість (2) дала б «task-3» — колізію.
  assert.equal(taskIdFrom("Головна", ["task-1", "task-3"]), "task-2");
  assert.equal(taskIdFrom("???", ["task-1", "task-2", "task-3"]), "task-4");
});

test("taskIdFrom: слаг, що вже зайнятий, отримує -2, -3…", () => {
  assert.equal(taskIdFrom("Landing page v2", ["landing-page-v2"]), "landing-page-v2-2");
  assert.equal(taskIdFrom("Landing page v2", ["landing-page-v2", "landing-page-v2-2"]),
    "landing-page-v2-3");
});

test("taskIdFrom: зайнятість без регістру (macOS/Windows: Foo і foo — одна тека)", () => {
  assert.equal(taskIdFrom("Foo", ["FOO"]), "foo-2");
  assert.equal(taskIdFrom("Головна", ["TASK-1"]), "task-2");
});

test("taskIdFrom: довжина ≤ 60, навіть із суфіксом, і результат завжди валідний", () => {
  const long = "a".repeat(200);
  assert.ok(taskIdFrom(long, []).length <= ID_MAX);
  const taken = [taskIdFrom(long, [])];
  const next = taskIdFrom(long, taken);
  assert.ok(next.length <= ID_MAX, `довжина ${next.length}`);
  assert.notEqual(next, taken[0]);
  assert.ok(validTaskId(next));
  // слаг не кінчається дефісом після обрізання по межі
  const cut = taskIdFrom(`${"a".repeat(59)} b`, []);
  assert.ok(!cut.endsWith("-"), cut);
  for (const title of ["  Mixed CASE & symbols!! ", "ідея 42", "x", "--", "", "Café déjà vu"]) {
    assert.ok(validTaskId(taskIdFrom(title, [])), `«${title}» → невалідний id`);
  }
});

test("taskIdFrom: суфікс не лягає ПІСЛЯ дефіса, на якому обрізало слаг (нема «--2»)", () => {
  // слаг = 57 «a», дефіс, «bc…» → обрізаний до 60 = a×57 + «-bc»; під суфікс «-2» лишається 58
  // символів, і 58-й — дефіс: без зрізання краю вийшло б «a×57--2».
  const title = `${"a".repeat(57)} b${"c".repeat(10)}`;
  const first = taskIdFrom(title, []);
  assert.equal(first, `${"a".repeat(57)}-bc`);
  const second = taskIdFrom(title, [first]);
  assert.equal(second, `${"a".repeat(57)}-2`);
  assert.ok(!second.includes("--"));
  assert.ok(validTaskId(second));
  assert.ok(second.length <= ID_MAX);
});

test("taskIdFrom: діакритика знімається, цифри лишаються, заголовок без слів → task-N", () => {
  assert.equal(taskIdFrom("Café déjà vu 2", []), "cafe-deja-vu-2");
  assert.equal(taskIdFrom("2026", []), "2026");
  assert.equal(taskIdFrom("---", []), "task-1");
  assert.equal(taskIdFrom(undefined, []), "task-1");
});

/* ── правило id: ASCII `\w`, суворіше за Python ────────────────────────── */

test("validTaskId: ASCII-слова й дефіс; пробіл, порожнє, хвостовий \\n, кирилиця — ні", () => {
  assert.equal(validTaskId("ok-1"), true);
  assert.equal(validTaskId("LIGA_11584"), true);
  assert.equal(validTaskId("a b"), false);
  assert.equal(validTaskId(""), false);
  assert.equal(validTaskId("x\n"), false, "хвостовий \\n: Python-ський `$` його пропускав");
  assert.equal(validTaskId("задача"), false, "JS-`\\w` без прапорця u — лише ASCII");
  assert.equal(validTaskId("a/b"), false);
  assert.equal(validTaskId("../x"), false);
  assert.equal(validTaskId(null), false);
  assert.equal(validTaskId(5), false);
  assert.ok(NAME_RE.test("a-b_c"));
});

/* ── помилки форми «Нова задача» ───────────────────────────────────────── */

test("taskFormError: порядок і ключі словника", () => {
  assert.equal(taskFormError({ title: "", id: "x" }, []), "titleRequired");
  assert.equal(taskFormError({ title: "   ", id: "x" }, []), "titleRequired", "пробіли — не назва");
  assert.equal(taskFormError({ title: "T", id: "x" }, ["x"]), "idTaken");
  assert.equal(taskFormError({ title: "T", id: "a b" }, []), "idBad");
  assert.equal(taskFormError({ title: "T", id: "" }, []), "idBad");
  assert.equal(taskFormError({ title: "T", id: "ok" }, []), null);
  assert.equal(taskFormError({ title: "T", id: "ok" }, undefined), null, "без переліку — нічого не зайнято");
  // без регістру: на macOS «Foo» і «foo» — одна тека
  assert.equal(taskFormError({ title: "T", id: "Foo" }, ["foo"]), "idTaken");
  // назва важливіша за id: порожня назва + невалідний id → кажемо про назву
  assert.equal(taskFormError({ title: "", id: "a b" }, []), "titleRequired");
  for (const k of ["titleRequired", "idTaken", "idBad"]) {
    assert.ok(DICT.uk[k] !== undefined && DICT.en[k] !== undefined, `ключа «${k}» бракує в словнику`);
  }
});

/* ── простір: слаг, тека за замовчуванням ──────────────────────────────── */

test("spaceSlug: слаг назви; без латиниці — порожньо", () => {
  assert.equal(spaceSlug("Client X"), "client-x");
  assert.equal(spaceSlug("  A -- B  "), "a-b");
  assert.equal(spaceSlug("Особисте"), "");
  assert.equal(spaceSlug(undefined), "");
});

test("defaultSpacePath: <дім>/deai-work/<слаг>, порожній слаг → personal", () => {
  assert.equal(defaultSpacePath("Client X", "~"), "~/deai-work/client-x");
  assert.equal(defaultSpacePath("Особисте", "~"), "~/deai-work/personal");
  assert.equal(defaultSpacePath("Client X", "/Users/me/"), "/Users/me/deai-work/client-x",
    "кінцевий слеш дому не дає подвійного");
  assert.equal(defaultSpacePath("Client X", ""), "~/deai-work/client-x", "без дому — «~»");
});

test("defaultSpacePath: ВІЛЬНА тека — зайняту реєстром пропускає (слаг, слаг-2…; кирилиця: personal, space-2…)", () => {
  const taken = (...names) => names.map((n) => `/Users/me/deai-work/${n}`);
  assert.equal(defaultSpacePath("Особисте", "~", taken()), "~/deai-work/personal", "реєстр порожній — як і було");
  assert.equal(defaultSpacePath("Особисте", "~", taken("personal")), "~/deai-work/space-2",
    "друге кириличне імʼя не лягає на теку першого");
  assert.equal(defaultSpacePath("Клієнт", "~", taken("personal", "space-2")), "~/deai-work/space-3");
  assert.equal(defaultSpacePath("Client X", "~", taken("client-x")), "~/deai-work/client-x-2");
  assert.equal(defaultSpacePath("Client X", "~", taken("client-x", "client-x-2")), "~/deai-work/client-x-3");
  assert.equal(defaultSpacePath("Client X", "~", taken("other")), "~/deai-work/client-x", "чужі імена не заважають");
});

test("defaultSpacePath: хвостові слеші й регістр у реєстрі не обманюють; реальний дім — точне порівняння", () => {
  assert.equal(defaultSpacePath("Особисте", "~", ["/Users/me/deai-work/personal/"]), "~/deai-work/space-2");
  assert.equal(defaultSpacePath("Особисте", "~", ["/Users/me/deai-work/Personal"]), "~/deai-work/space-2",
    "на macOS Personal і personal — одна тека");
  assert.equal(defaultSpacePath("Client X", "/Users/me", ["/Users/me/deai-work/client-x"]), "/Users/me/deai-work/client-x-2");
  assert.equal(defaultSpacePath("Client X", "/Users/me", ["/Users/you/deai-work/client-x"]), "/Users/me/deai-work/client-x",
    "з відомим домом чужий дім не збігається");
  assert.equal(defaultSpacePath("Особисте", "~", undefined), "~/deai-work/personal");
  assert.equal(defaultSpacePath("Особисте", "~", null), "~/deai-work/personal");
});

test("defaultSpacePath: результат ніколи не збігається з жодною зайнятою текою (перебір до вільної)", () => {
  const taken = ["personal", ...Array.from({ length: 30 }, (_, i) => `space-${i + 2}`)].map((n) => `/h/deai-work/${n}`);
  const got = defaultSpacePath("Особисте", "~", taken);
  assert.equal(got, "~/deai-work/space-32");
  assert.ok(!taken.some((u) => got.endsWith(u.slice(u.indexOf("/deai-work")))));
});

test("isRegisteredPath: збіг з реєстром без хвостового слеша й у NFC; порожнє — ні", () => {
  assert.equal(isRegisteredPath("/a/b", ["/a/b"]), true);
  assert.equal(isRegisteredPath("/a/b/", ["/a/b"]), true);
  assert.equal(isRegisteredPath("/a/b", ["/a/b/"]), true);
  assert.equal(isRegisteredPath("/a/Ke\u0301/x", ["/a/K\u00e9/x"]), true, "NFC/NFD — одна тека");
  assert.equal(isRegisteredPath("/a/b/c", ["/a/b"]), false, "вкладена — інша (перетин — справа сервера)");
  assert.equal(isRegisteredPath("/a/B", ["/a/b"]), false, "регістр, як і на сервері, не нормалізуємо");
  assert.equal(isRegisteredPath("", [""]), false);
  assert.equal(isRegisteredPath(undefined, ["/a"]), false);
  assert.equal(isRegisteredPath("/a", undefined), false);
});

test("spaceErrField: назва, тека або жодне; spaces-* і мережа — не чіпають поля", () => {
  assert.equal(spaceErrField("name-required"), "name");
  for (const c of ["path-not-absolute", "path-too-broad", "path-system", "path-tool", "path-registered",
    "path-overlap", "path-not-dir", "path-unwritable", "task-id-collision"]) assert.equal(spaceErrField(c), "path", c);
  for (const c of ["spaces-unwritable", "spaces-unreadable", "spaces-off", "unknown-space", undefined, null, ""]) {
    assert.equal(spaceErrField(c), null, String(c));
  }
});

test("taskErrField: title / id / null за ключем помилки форми задачі", () => {
  assert.equal(taskErrField("titleRequired"), "title");
  assert.equal(taskErrField("idBad"), "id");
  assert.equal(taskErrField("idTaken"), "id");
  for (const k of ["taskErrGeneric", "taskErrSpaceGone", "tasksErrSpaceUnavailable", null, undefined]) {
    assert.equal(taskErrField(k), null, String(k));
  }
});

test("коди відмов задачі з теки → ключі й поле форми", () => {
  assert.equal(taskErrKey("from-too-big"), "wzErrFromTooBig");
  assert.equal(taskErrKey("task-dir-exists"), "wzErrTaskDirExists");
  assert.equal(taskErrField("wzErrFromNoIndex"), "from");
  assert.equal(taskErrField("wzFromRequired"), "from");
  assert.equal(taskErrField("wzErrTaskDirExists"), "id");
  assert.equal(taskErrField("wzErrFromPlain"), null);
  assert.equal(taskErrField("idTaken"), "id");
});

test("кожен код відмови `from` на сервері має свій ключ; поле — лише те, що людина виправляє сама", () => {
  const map = {
    "from-not-found": ["wzErrFromNotFound", "from"],
    "from-no-index": ["wzErrFromNoIndex", "from"],
    "from-contains-space": ["wzErrFromContains", "from"],
    "from-too-big": ["wzErrFromTooBig", "from"],
    "from-needs-plain-space": ["wzErrFromPlain", null],
    "task-dir-exists": ["wzErrTaskDirExists", "id"],
  };
  for (const [code, [key, field]] of Object.entries(map)) {
    assert.equal(taskErrKey(code), key, code);
    assert.equal(taskErrField(taskErrKey(code)), field, code);
  }
  /* `bad-request` (from не рядок) і `bad-task-id` — не про поле «Тека»: перший загальний, другий — як і раніше id. */
  assert.equal(taskErrKey("bad-request"), "taskErrGeneric");
  assert.equal(taskErrKey("bad-task-id"), "idBad");
  assert.equal(taskErrKey("from-щось-нове"), "taskErrGeneric");
  assert.equal(taskErrKey(undefined), "taskErrGeneric");
});

/* ── рядки перемикача ──────────────────────────────────────────────────── */

test("spaceRows: ✓ на поточному, sub {n, path}, недоступний — muted", () => {
  const rows = spaceRows({
    current: "p",
    spaces: [
      { id: "liga", name: "ЛІГА", color: "space-1", path: "/w/liga", tasks: 12, available: true },
      { id: "p", name: "P", color: "space-2", path: "/w/p", tasks: 0, available: true },
      { id: "gone", name: "G", color: "space-3", path: "/w/gone", tasks: 0, available: false },
    ],
  });
  assert.deepEqual(rows.map((r) => r.id), ["liga", "p", "gone"], "порядок реєстру збережено");
  assert.deepEqual(rows.map((r) => r.on), [false, true, false]);
  assert.deepEqual(rows.map((r) => r.muted), [false, false, true]);
  assert.deepEqual(rows[0].sub, { n: 12, path: "/w/liga" });
  assert.equal(rows[1].name, "P");
  assert.equal(rows[1].color, "space-2");
});

test("spaceRows: поле available відсутнє — простір доступний; порожній вхід не кидає", () => {
  assert.equal(spaceRows({ current: "a", spaces: [{ id: "a", name: "A" }] })[0].muted, false);
  assert.deepEqual(spaceRows({ current: null, spaces: [] }), []);
  assert.deepEqual(spaceRows({ off: true }), []);
  assert.deepEqual(spaceRows(null), []);
  assert.deepEqual(spaceRows({ current: "a", spaces: [{ id: "a", name: "A" }] })[0].sub,
    { n: 0, path: "" });
});

/* ── колір ─────────────────────────────────────────────────────────────── */

test("spaceColorToken: лише space-1…6, решта (і ін'єкція в style) — space-1", () => {
  assert.deepEqual(SPACE_COLORS, ["space-1", "space-2", "space-3", "space-4", "space-5", "space-6"]);
  for (const c of SPACE_COLORS) assert.equal(spaceColorToken(c), c);
  for (const bad of ["space-7", "space-0", "red", "space-2;position:fixed", "", null, undefined, "space-2\n"]) {
    assert.equal(spaceColorToken(bad), "space-1", String(bad));
  }
});

/* ── коди помилок сервера → ключі словника ─────────────────────────────── */

test("spaceErrKey: кожен код `space-new` має свій ключ, невідомий — загальний", () => {
  const map = {
    "path-not-absolute": "spaceErrNotAbsolute",
    "path-too-broad": "spaceErrTooBroad",
    "path-system": "spaceErrSystem",
    "path-tool": "spaceErrTool",
    "path-registered": "spaceErrRegistered",
    "path-overlap": "spaceErrOverlap",
    "path-not-dir": "spaceErrNotDir",
    "path-unwritable": "spaceErrUnwritable",
    "task-id-collision": "spaceErrCollision",
    "name-required": "spaceErrName",
  };
  for (const [code, key] of Object.entries(map)) {
    assert.equal(spaceErrKey(code), key, code);
    assert.ok(DICT.uk[key] !== undefined && DICT.en[key] !== undefined, `«${key}» бракує в словнику`);
  }
  assert.equal(spaceErrKey("spaces-unwritable"), "spaceErrGeneric");
  assert.equal(spaceErrKey("щось нове"), "spaceErrGeneric");
  assert.equal(spaceErrKey(undefined), "spaceErrGeneric");
  assert.equal(spaceErrKey(null), "spaceErrGeneric");
  assert.ok(DICT.uk.spaceErrGeneric !== undefined && DICT.en.spaceErrGeneric !== undefined);
});

test("spaceErrKey: `timeout` (запит діалогу обірвано за стелею часу) → formTimeout, а не загальна; поле не зачеплено", () => {
  assert.equal(spaceErrKey("timeout"), "formTimeout");
  assert.ok(DICT.uk.formTimeout !== undefined && DICT.en.formTimeout !== undefined, "formTimeout бракує в словнику");
  assert.equal(spaceErrField("timeout"), null, "таймаут не вина жодного поля: ні aria-invalid, ні фокуса");
});

test("FORM_POST_TIMEOUT_MS: скінченна стеля 5–60 с — довша лишала б людину під підкладкою, коротша обривала б живий запит", () => {
  assert.ok(Number.isFinite(FORM_POST_TIMEOUT_MS), "стелі нема");
  assert.ok(FORM_POST_TIMEOUT_MS >= 5000 && FORM_POST_TIMEOUT_MS <= 60000, String(FORM_POST_TIMEOUT_MS));
});

test("checkPostTimeoutMs: стеля запиту `check` — `check_timeout_s` модуля + запас; без ключа (чи сміття) — стеля форми, як було", () => {
  assert.equal(checkPostTimeoutMs({ id: "vercel-publish", check_timeout_s: 130 }), (130 + CHECK_POST_MARGIN_S) * 1000);
  assert.ok(checkPostTimeoutMs({ check_timeout_s: 130 }) > 130000, "стеля клієнта мусить бути довшою за тайм-аут ядра");
  assert.equal(checkPostTimeoutMs({ check_timeout_s: 150 }), 165000);
  for (const e of [{ id: "git-sync" }, {}, null, undefined, { check_timeout_s: 0 }, { check_timeout_s: -5 }, { check_timeout_s: "130" },
    { check_timeout_s: 1.5 }, { check_timeout_s: null }]) {
    assert.equal(checkPostTimeoutMs(e), FORM_POST_TIMEOUT_MS, JSON.stringify(e));
  }
  assert.equal(checkPostTimeoutMs({ check_timeout_s: 1 }), FORM_POST_TIMEOUT_MS, "короткий `check` не МЕНШИЙ за стелю форми");
});

test("spaceErrKey: код, що збігається з іменем з прототипу, — загальна помилка, не «функція»", () => {
  for (const code of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
    assert.equal(spaceErrKey(code), "spaceErrGeneric", code);
  }
});

/* ── створення задачі з ціллю синку (етап 4a, Task 7) ─────────────────────────────────────────────── */

test("vcs-bad-target / vcs-needs-role: свої ключі; поле «Репозиторій» підсвічується лише адресою", () => {
  assert.equal(taskErrKey("vcs-bad-target"), "taskErrVcsTarget");
  assert.equal(taskErrKey("vcs-needs-role"), "taskErrVcsRole");
  assert.equal(taskErrField("taskErrVcsTarget"), "repo", "помилка про адресу — на полі repo");
  assert.equal(taskErrField("taskErrVcsRole"), null, "про відсутню роль — не про поле");
  for (const k of ["taskErrVcsTarget", "taskErrVcsRole"]) {
    assert.ok(DICT.uk[k] !== undefined && DICT.en[k] !== undefined, `«${k}» бракує в словнику`);
  }
});

test("коди постачальника ролі vcs (409): space.json і недовірений модуль — готові тексти, поле не підсвічується", () => {
  assert.equal(taskErrKey("space-json-unreadable"), "cnRefSpaceJson");
  assert.equal(taskErrKey("module-untrusted"), "cnRefUntrusted");
  for (const c of ["space-json-unreadable", "module-untrusted"]) assert.equal(taskErrField(taskErrKey(c)), null, c);
});

test("taskErrShowsReason: check-timeout / module-error / vcs-error — завжди причина сервера; будь-який НЕЗМАПЛЕНИЙ код — коли тіло несло vcs", () => {
  for (const c of ["check-timeout", "module-error", "vcs-error"]) {
    assert.equal(taskErrShowsReason(c), true, c);
    assert.equal(taskErrShowsReason(c, true), true, c);
    assert.equal(taskErrKey(c), "taskErrGeneric", `${c}: власного ключа нема — причина йде в errFailed`);
    assert.equal(taskErrField(taskErrKey(c)), null, `${c}: поле не підсвічується`);
  }
  /* M2 ревʼю Task 7: коди каркаса й постачальника без ключа (`bad-settings`, `secrets-unreadable`, `bad-manifest`…) падали у
     «Спробуй ще раз», а повтор марний. З `vcs` у тілі їхня причина — єдине корисне, що є. */
  for (const c of ["bad-settings", "secrets-unreadable", "bad-manifest", "module-changed", "module-refused", "task-create-failed", "constructor", "__proto__", "", undefined, null, 5]) {
    assert.equal(taskErrShowsReason(c, true), true, `vcs у тілі: ${String(c)}`);
    assert.equal(taskErrShowsReason(c), false, `без vcs у тілі поведінка стара: ${String(c)}`);
    assert.equal(taskErrShowsReason(c, false), false);
  }
  /* Змаплені коди мають свій текст — причину сервера не підміняють, навіть із vcs у тілі. */
  for (const c of ["vcs-bad-target", "vcs-needs-role", "task-exists", "bad-task-id", "timeout", "space-json-unreadable", "module-untrusted", "unknown-space"]) {
    assert.equal(taskErrShowsReason(c, true), false, String(c));
    assert.equal(taskErrShowsReason(c), false, String(c));
  }
});

/* ── роль notify (4c-3): пункт Teams і опит тиші — за capabilities.notify ───────────────── */

test("hasNotify: ключ capabilities.notify вирішує (модуль чи 'legacy'), а без ключа — integrations, як hasVcs", () => {
  assert.equal(hasNotify({ integrations: false, capabilities: { notify: "supabase-teams" } }), true, "модуль у просторі без інтеграцій");
  assert.equal(hasNotify({ integrations: true, capabilities: { notify: "legacy" } }), true, "зашитий шлях ЛІГА");
  assert.equal(hasNotify({ integrations: true, capabilities: { notify: null } }), false, "роль вимкнено — Teams нема, хоч інтеграції є");
  assert.equal(hasNotify({ integrations: true, capabilities: { publish: "legacy" } }), true, "ключа нема + інтеграції (сервер ще без ролі)");
  assert.equal(hasNotify({ integrations: false, capabilities: { publish: "static-publish" } }), false, "ключа нема + без інтеграцій");
  assert.equal(hasNotify({ id: "p", integrations: true }), true, "стара форма: рівно за integrations");
  assert.equal(hasNotify({ id: "p", integrations: false }), false);
  assert.equal(hasNotify({ id: "p" }), true, "невідомість Teams не краде: лише рівно `=== false`");
  assert.equal(hasNotify(null), true, "hasNotify(null) — true, як hasVcs(null): шар вимкнено");
  assert.equal(hasNotify(undefined), true);
  assert.equal(hasNotify({ capabilities: "x", integrations: false }), false, "caps не обʼєкт — як без ключа");
});

/* ── роль publish (4d-3c): «ЛІГА» живе в `compat.publish`, а `capabilities.publish` — id модуля ──────────── */

const MIG = { id: "liga", integrations: true, capabilities: { publish: "vercel-publish" }, compat: { publish: "design-canvas" } };
const PLAIN = { id: "p", integrations: true, capabilities: { publish: "vercel-publish" } };

test("isLegacyPublish: compat.publish === design-canvas — ЛІГА, хоч capabilities.publish — id модуля", () => {
  assert.equal(isLegacyPublish(MIG), true);
  assert.equal(isLegacyPublish(PLAIN), false, "звичайний vercel-publish без compat — модуль-шлях");
  assert.equal(isLegacyPublish({ capabilities: { publish: "legacy" } }), true);
  assert.equal(isLegacyPublish({ integrations: true }), true, "стара відповідь без capabilities — за integrations");
  assert.equal(isLegacyPublish({ integrations: false }), false);
  assert.equal(isLegacyPublish({ capabilities: { publish: "vercel-publish" }, compat: { publish: "other" } }), false, "інше значення — не ЛІГА");
  assert.equal(isLegacyPublish({ capabilities: { publish: "static-publish" }, compat: { vcs: "design-canvas" } }), false, "compat чужої ролі");
});

test("мігрований запис ЛІГА читається гілкою ЛІГА скрізь: isRemotePublish, previewTarget, publishReaction, pwView", () => {
  const task = { id: "T", publish_url: "https://pv-12345678.vercel.app", preview_password: "1100", preview_password_custom: false,
    publish_remote: { module: "vercel-publish", url: "https://pv-12345678.vercel.app" } };
  assert.equal(isRemotePublish(task, MIG), false, "слід модуля не береться за публікацію модуля: це ЛІГА");
  assert.equal(isRemotePublish(task, PLAIN), true, "контроль: без compat той самий слід — модуль");
  assert.deepEqual(previewTarget(task, MIG), { kind: "external", url: "https://pv-12345678.vercel.app", at: null });
  assert.deepEqual(publishReaction({ url: "https://pv-12345678.vercel.app" }, MIG, true), { kind: "legacy", show: "render" });
  assert.deepEqual(publishReaction({ url: "https://pv-12345678.vercel.app" }, MIG, false), { kind: "legacy", show: "toast", key: "publishToastDone" });
  assert.equal(publishReaction({ url: "https://pv-12345678.vercel.app" }, PLAIN, true).kind, "remote");
  assert.equal(pwView(task, MIG).pw, "1100", "пароль превʼю ЛІГА показано");
  assert.equal(pwView(task, PLAIN).pw, "", "контроль: у модуль-шляху пароль ЛІГА не показуємо");
});

test("4d-4b: capabilities без запасного постачальника (збій → null, не 'legacy') читаються як «ролі нема», а не падають", () => {
  const sp = { id: "legacy", integrations: true, capabilities: { publish: null, comments: null, vcs: null, dashboard: null, tracker: null, notify: null, error: "space-json-unreadable" } };
  assert.equal(hasPublish(sp), false);
  assert.equal(hasVcs(sp), false);
  assert.equal(hasNotify(sp), false);
  assert.equal(hasTeamComments(sp), false);
  assert.equal(isLegacyVcs(sp), false);
  assert.equal(isLegacyPublish(sp), false);
  assert.equal(isRemotePublish({ publish_url: "https://pv-12345678.vercel.app" }, sp), false);
});
