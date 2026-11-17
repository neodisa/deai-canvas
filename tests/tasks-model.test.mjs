import assert from "node:assert/strict";
import test from "node:test";

import { DICT } from "../app/i18n.js";
import {
  HOME_STATUSES, SORTS, cleanTitle, filterTasks, isDone, matches, readHomeUi, relTime, retitle, sortTasks, statusCounts, tagKey, taskKey,
} from "../app/tasks-model.js";

/* Дані — зліпок форми з /api/tasks-overview: `mine[i]` має `opened`/`changed`
   (секунди), `profile` і `tags`, `team.rows[i]` — `updated` (ISO) і `designer`. Назви
   справжні за формою: частина дублює ключ Jira, частина (boss-interface) — без. */
const T = (o) => ({
  id: "x", jira: null, title: "x", profile: null, tags: [], opened: null, changed: null,
  jiraStatus: null, jiraCat: null, ...o,
});

const A = T({ id: "edr", jira: "LIGA-7019", title: "LIGA-7019 · Очікування оновлення даних із ЄДР",
  profile: "liga360", tags: ["LIGA360"], opened: "2026-09-10T10:00:00Z", changed: 1790000000, jiraStatus: "В роботі", jiraCat: "indeterminate" });
const B = T({ id: "sanc", jira: "LIGA-7015", title: "LIGA-7015: Санкції Бізнес-груп",
  profile: "united", tags: ["United"], opened: "2026-09-20T10:00:00Z", changed: 1790500000, jiraStatus: "Готово", jiraCat: "done" });
const C = T({ id: "boss-interface", jira: null, title: "boss-interface",
  profile: "united", tags: ["United"], opened: "2026-08-01T10:00:00Z", changed: null, jiraStatus: null, jiraCat: null });
const D = T({ id: "seo-blog", jira: "LIGA-9", title: "Блог для SEO", profile: "seo", tags: ["SEO"],
  opened: null, changed: 1780000000, jiraStatus: "To Do", jiraCat: "new" });

/* ── cleanTitle / taskKey ─────────────────────────────────────────────── */

test("cleanTitle: прибирає «<jira> · » з голови назви", () => {
  assert.equal(cleanTitle(A), "Очікування оновлення даних із ЄДР");
});

test("cleanTitle: усі п'ять роздільників і регістр ключа не мають значення", () => {
  for (const sep of [" · ", ": ", " — ", " – ", " - "]) {
    assert.equal(cleanTitle({ id: "i", jira: "LIGA-1", title: `liga-1${sep}Назва` }), "Назва", `роздільник «${sep}»`);
  }
});

test("cleanTitle: без Jira назва лишається як є, навіть якщо схожа на ключ", () => {
  assert.equal(cleanTitle(C), "boss-interface");
  assert.equal(cleanTitle({ id: "i", jira: null, title: "LIGA-5 · Назва" }), "LIGA-5 · Назва");
});

test("cleanTitle: порожня назва → id; назва = лише ключ не стає порожньою", () => {
  assert.equal(cleanTitle({ id: "only-id", jira: null, title: "" }), "only-id");
  assert.equal(cleanTitle({ id: "i", jira: "LIGA-7", title: "LIGA-7" }), "LIGA-7");
  assert.equal(cleanTitle({ id: "i", jira: "LIGA-7", title: "LIGA-7 · " }), "LIGA-7 · ");
});

test("cleanTitle: ключ, що лише починає чужий ключ, не різається", () => {
  assert.equal(cleanTitle({ id: "i", jira: "LIGA-11", title: "LIGA-115 · Інше" }), "LIGA-115 · Інше");
});

test("cleanTitle: спецсимволи ключа екрануються, а не читаються як регексп", () => {
  assert.equal(cleanTitle({ id: "i", jira: "A+B(1)", title: "A+B(1) · Назва" }), "Назва");
  assert.equal(cleanTitle({ id: "i", jira: "A.B", title: "AxB · Назва" }), "AxB · Назва");
});

test("taskKey: jira, інакше id", () => {
  assert.equal(taskKey(A), "LIGA-7019");
  assert.equal(taskKey(C), "boss-interface");
});

/* ── matches ──────────────────────────────────────────────────────────── */

test("matches: порожній запит пропускає все", () => {
  assert.equal(matches(A, ""), true);
  assert.equal(matches(A, "   "), true);
  assert.equal(matches(A, undefined), true);
});

test("matches: слова з різних місць назви, без регістру", () => {
  assert.equal(matches(B, "санк біз"), true);
  assert.equal(matches(B, "САНК біз"), true);
  assert.equal(matches(B, "санк євро"), false);
});

test("matches: за номером і за повним ключем", () => {
  assert.equal(matches(A, "7019"), true);
  assert.equal(matches(A, "LIGA-7019"), true);
  assert.equal(matches(A, "liga-7019"), true);
  assert.equal(matches(B, "7019"), false);
});

test("matches: шукає в id, статусі Jira й дизайнері", () => {
  assert.equal(matches(C, "boss"), true);
  assert.equal(matches(A, "в роботі"), true);
  assert.equal(matches({ ...A, designer: "Ольга К." }, "ольга"), true);
  assert.equal(matches(A, "ольга"), false);
});

/* ── isDone / statusCounts ────────────────────────────────────────────── */

test("isDone: лише jiraCat=done; без статусу задача активна", () => {
  assert.equal(isDone(B), true);
  assert.equal(isDone(A), false);
  assert.equal(isDone(D), false);
  assert.equal(isDone(C), false);
});

test("statusCounts: активні/виконані/всі", () => {
  assert.deepEqual(statusCounts([A, B, C, D], ""), { active: 3, done: 1, all: 4 });
});

test("statusCounts: рахує лише те, що пройшло запит", () => {
  assert.deepEqual(statusCounts([A, B, C, D], "liga"), { active: 2, done: 1, all: 3 });
  assert.deepEqual(statusCounts([A, B, C, D], "санк"), { active: 0, done: 1, all: 1 });
  assert.deepEqual(statusCounts([], ""), { active: 0, done: 0, all: 0 });
});

/* ── filterTasks ──────────────────────────────────────────────────────── */

const ids = (l) => l.map((x) => x.id);
const NONE = { q: "", status: "all", tags: new Set(), designers: new Set() };

test("filterTasks: порожні фільтри — усе, порядок збережено", () => {
  assert.deepEqual(ids(filterTasks([A, B, C, D], NONE)), ["edr", "sanc", "boss-interface", "seo-blog"]);
});

test("filterTasks: статус active / done", () => {
  assert.deepEqual(ids(filterTasks([A, B, C, D], { ...NONE, status: "active" })), ["edr", "boss-interface", "seo-blog"]);
  assert.deepEqual(ids(filterTasks([A, B, C, D], { ...NONE, status: "done" })), ["sanc"]);
});

test("filterTasks: мітки — АБО між вибраними, регістр і крайні пробіли не важать, задача без міток ховається", () => {
  assert.deepEqual(ids(filterTasks([A, B, C, D], { ...NONE, tags: new Set(["united"]) })), ["sanc", "boss-interface"]);
  assert.deepEqual(ids(filterTasks([A, B, C, D], { ...NONE, tags: new Set(["united", "seo"]) })), ["sanc", "boss-interface", "seo-blog"],
    "АБО: задача з будь-якою вибраною міткою");
  const noTags = { id: "n", title: "n" };
  assert.deepEqual(ids(filterTasks([A, noTags, { ...A, id: "e", tags: [] }], { ...NONE, tags: new Set(["liga360"]) })), ["edr"],
    "свідома відмінність від профільного фільтра: задача без міток при вибраній мітці ховається");
  assert.deepEqual(ids(filterTasks([{ ...A, tags: ["  Alpha "] }], { ...NONE, tags: new Set(["alpha"]) })), ["edr"]);
});

test("filterTasks: порожній Set міток — не фільтр (задачі без міток лишаються)", () => {
  assert.deepEqual(ids(filterTasks([A, { id: "n", title: "n" }], NONE)), ["edr", "n"]);
  assert.deepEqual(ids(filterTasks([A, { id: "n", title: "n" }], { q: "", status: "all", designers: new Set() })), ["edr", "n"], "ключа tags нема");
});

test("tagKey: без регістру й крайніх пробілів; не рядок і порожнє — порожній ключ", () => {
  assert.equal(tagKey("  Alpha "), "alpha");
  assert.equal(tagKey("United"), tagKey("united"));
  assert.equal(tagKey("a b"), "a b", "внутрішні пробіли — справа сервера, ключ їх не чіпає");
  for (const x of [null, undefined, "", "   "]) assert.equal(tagKey(x), "");
  assert.equal(tagKey(5), "5");
});

test("matches: пошук знаходить і за міткою (без регістру, частина слова)", () => {
  assert.equal(matches({ ...C, tags: ["Beta"] }, "bet"), true);
  assert.equal(matches({ ...C, tags: ["Beta"] }, "BETA"), true);
  assert.equal(matches({ ...C, tags: ["Beta"] }, "alpha"), false);
  assert.equal(matches({ ...C, tags: ["Beta", "Дизайн"] }, "дизайн beta"), true, "слова з різних місць, як у решти полів");
  assert.equal(matches({ id: "n", title: "n" }, "bet"), false, "ключа tags нема — не кидає");
});

/* ── readHomeUi: збережений стан екрана ───────────────────────────────── */

test("readHomeUi: новий стан — мітки як ключі; старий `profiles` читається як мітки (нижній регістр)", () => {
  assert.deepEqual([...readHomeUi({ tags: ["alpha"] }).tags], ["alpha"]);
  assert.deepEqual([...readHomeUi({ tags: [" Alpha ", "BETA", "alpha"] }).tags], ["alpha", "beta"], "ключі через tagKey, без дублів");
  assert.deepEqual([...readHomeUi({ profiles: ["united", "SEO"] }).tags], ["united", "seo"], "стан 0.10.0: чип «United» лишається вибраним");
  assert.deepEqual([...readHomeUi({ tags: ["alpha"], profiles: ["united"] }).tags], ["alpha"], "новий ключ сильніший за старий");
  assert.deepEqual([...readHomeUi({ tags: [], profiles: ["united"] }).tags], [], "порожній новий ключ — свідомо знятий фільтр");
});

test("readHomeUi: сміття — порожньо й типове, не кидає; решта полів — як було в app.js", () => {
  const base = { tab: "mine", q: "", sort: "recent", status: "active" };
  for (const raw of [null, undefined, "x", 5, [], true, {}, { tags: "alpha" }, { tags: [1, null, {}, "", "  "] }, { profiles: { a: 1 } }]) {
    const ui = readHomeUi(raw);
    assert.deepEqual([ui.tags.size, ui.designers.size], [0, 0], JSON.stringify(raw));
    assert.deepEqual({ tab: ui.tab, q: ui.q, sort: ui.sort, status: ui.status }, base, JSON.stringify(raw));
  }
  const ui = readHomeUi({ tab: "team", sort: "title", status: "done", designers: ["Ольга", 5], profiles: [3, "x"] });
  assert.deepEqual([ui.tab, ui.sort, ui.status], ["team", "title", "done"]);
  assert.deepEqual([...ui.designers], ["Ольга"]);
  assert.deepEqual([...ui.tags], ["x"]);
  assert.deepEqual([readHomeUi({ tab: "x", sort: "nope", status: "nope" }).tab, readHomeUi({ sort: "nope" }).sort,
    readHomeUi({ status: "nope" }).status], ["mine", "recent", "active"], "невідоме значення — типове");
});

test("filterTasks: дизайнери — лише для елементів, що мають designer", () => {
  const r1 = { ...A, designer: "Ольга" };
  const r2 = { ...B, designer: "Андрій" };
  assert.deepEqual(ids(filterTasks([r1, r2, C], { ...NONE, designers: new Set(["Андрій"]) })), ["sanc", "boss-interface"]);
});

test("filterTasks: усі умови діють разом", () => {
  const f = { q: "liga", status: "active", tags: new Set(["liga360", "seo"]), designers: new Set() };
  assert.deepEqual(ids(filterTasks([A, B, C, D], f)), ["edr", "seo-blog"]);
  assert.deepEqual(ids(filterTasks([A, B, C, D], { ...f, q: "блог" })), ["seo-blog"]);
});

test("filterTasks: не мутує вхід і повертає новий масив", () => {
  const list = [A, B];
  const out = filterTasks(list, NONE);
  assert.notEqual(out, list);
  assert.deepEqual(list, [A, B]);
});

/* ── sortTasks ────────────────────────────────────────────────────────── */

test("SORTS: перелік і порядок", () => {
  assert.deepEqual(SORTS, ["recent", "changed", "jira", "title", "status"]);
});

test("sortTasks recent: opened спадно, null в кінці", () => {
  assert.deepEqual(ids(sortTasks([C, D, A, B], "recent")), ["sanc", "edr", "boss-interface", "seo-blog"]);
});

test("sortTasks recent: opened порівнюється як час, а не як рядок (різні зсуви)", () => {
  const early = T({ id: "early", opened: "2026-09-10T10:00:00+05:00" }); // 05:00Z, рядок «більший»
  const late = T({ id: "late", opened: "2026-09-10T08:00:00Z" });
  const junk = T({ id: "junk", opened: "не дата" });
  assert.deepEqual(ids(sortTasks([early, junk, late], "recent")), ["late", "early", "junk"]);
});

test("sortTasks changed: секунди й ISO-updated в одній шкалі, null в кінці", () => {
  const row = T({ id: "row", updated: new Date(1795000000 * 1000).toISOString() });
  assert.deepEqual(ids(sortTasks([C, D, A, B, row], "changed")), ["row", "sanc", "edr", "seo-blog", "boss-interface"]);
});

test("sortTasks jira: числова частина спадно (9 < 7015), без ключа в кінці", () => {
  assert.deepEqual(ids(sortTasks([D, C, A, B], "jira")), ["edr", "sanc", "seo-blog", "boss-interface"]);
});

test("sortTasks title: за очищеною назвою, українська колація", () => {
  const list = [
    T({ id: "z", jira: null, title: "Яблуко" }),
    T({ id: "g", jira: null, title: "Гаманець" }),
    T({ id: "i", jira: null, title: "Іграшка" }),
    T({ id: "e", jira: "LIGA-1", title: "LIGA-1 · Єдине вікно" }),
  ];
  // в українському алфавіті: Г, Є, І, Я
  assert.deepEqual(ids(sortTasks(list, "title")), ["g", "e", "i", "z"]);
  assert.deepEqual(ids(sortTasks([B, A], "title")), ["edr", "sanc"]);
});

test("sortTasks status: new < indeterminate < done < без статусу", () => {
  assert.deepEqual(ids(sortTasks([C, B, A, D], "status")), ["seo-blog", "edr", "sanc", "boss-interface"]);
});

test("sortTasks: невідомий ключ — як recent", () => {
  assert.deepEqual(ids(sortTasks([C, A, B], "нема")), ids(sortTasks([C, A, B], "recent")));
  assert.deepEqual(ids(sortTasks([C, A, B], undefined)), ["sanc", "edr", "boss-interface"]);
});

test("sortTasks: стабільний — рівні ключі лишаються у вхідному порядку", () => {
  const eq = ["a", "b", "c", "d"].map((id) => T({ id, jira: "LIGA-5", title: "Однакова", opened: "2026-01-01", jiraCat: "done", changed: 100 }));
  for (const k of SORTS) assert.deepEqual(ids(sortTasks(eq, k)), ["a", "b", "c", "d"], k);
  const nulls = ["a", "b", "c"].map((id) => T({ id }));
  for (const k of SORTS) assert.deepEqual(ids(sortTasks(nulls, k)), ["a", "b", "c"], `null · ${k}`);
});

test("sortTasks: не мутує вхід і повертає новий масив", () => {
  const list = [C, D, A, B];
  const before = structuredClone(list);
  for (const k of SORTS) {
    const out = sortTasks(list, k);
    assert.notEqual(out, list, k);
    assert.deepEqual(list, before, `вхід змінився після ${k}`);
  }
});

/* ── relTime ──────────────────────────────────────────────────────────── */

const NOW = Date.UTC(2026, 9, 9, 12, 0, 0);
const MIN = 60_000, HOUR = 60 * MIN, DAY = 24 * HOUR;
const ago = (ms) => relTime(NOW - ms, NOW);

test("relTime: до двох хвилин — «щойно»", () => {
  assert.deepEqual(ago(0), { key: "relJustNow", n: 0 });
  assert.deepEqual(ago(MIN + 59_000), { key: "relJustNow", n: 0 });
});

test("relTime: майбутній час (розбіжність годинників) — теж «щойно»", () => {
  assert.deepEqual(relTime(NOW + 5 * MIN, NOW), { key: "relJustNow", n: 0 });
});

test("relTime: хвилини — від 2 до 59", () => {
  assert.deepEqual(ago(2 * MIN), { key: "relMin", n: 2 });
  assert.deepEqual(ago(59 * MIN + 59_000), { key: "relMin", n: 59 });
});

test("relTime: години — від 60 хв до 23 год", () => {
  assert.deepEqual(ago(60 * MIN), { key: "relHour", n: 1 });
  assert.deepEqual(ago(23 * HOUR + 59 * MIN), { key: "relHour", n: 23 });
});

test("relTime: 24–47 год — «вчора»", () => {
  assert.deepEqual(ago(24 * HOUR), { key: "relYesterday", n: 0 });
  assert.deepEqual(ago(47 * HOUR), { key: "relYesterday", n: 0 });
});

test("relTime: дні — від 2 до 6", () => {
  assert.deepEqual(ago(48 * HOUR), { key: "relDays", n: 2 });
  assert.deepEqual(ago(6 * DAY), { key: "relDays", n: 6 });
  assert.deepEqual(ago(7 * DAY - MIN), { key: "relDays", n: 6 });
});

test("relTime: тижні — від 7 до 34 діб", () => {
  assert.deepEqual(ago(7 * DAY), { key: "relWeeks", n: 1 });
  assert.deepEqual(ago(14 * DAY), { key: "relWeeks", n: 2 });
  assert.deepEqual(ago(34 * DAY), { key: "relWeeks", n: 4 });
});

test("relTime: від 35 діб — дата (n = самі мілісекунди)", () => {
  assert.deepEqual(ago(35 * DAY), { key: "relDate", n: NOW - 35 * DAY });
});

test("relTime: нескінченний nowMs → Date.now(), а не relDate", () => {
  const minuteAgo = Date.now() - MIN;
  for (const now of [NaN, undefined, Infinity]) assert.deepEqual(relTime(minuteAgo, now), { key: "relJustNow", n: 0 }, String(now));
  assert.equal(relTime(Date.now() - 5 * MIN, undefined).key, "relMin");
});

test("relTime: немає часу — relUnknown", () => {
  for (const v of [null, undefined, NaN]) assert.deepEqual(relTime(v, NOW), { key: "relUnknown", n: 0 });
});

test("relTime: кожен ключ, який вона віддає, є в обох словниках", () => {
  const keys = new Set([ago(0), ago(5 * MIN), ago(3 * HOUR), ago(30 * HOUR), ago(3 * DAY), ago(10 * DAY), ago(60 * DAY), relTime(null, NOW)].map((r) => r.key));
  assert.equal(keys.size, 8);
  for (const k of keys) for (const lang of ["uk", "en"]) assert.notEqual(DICT[lang][k], undefined, `${lang}: ${k}`);
});

test("HOME_STATUSES — єдиний перелік статусів екрана: active, done, all", () => {
  assert.deepEqual(HOME_STATUSES, ["active", "done", "all"]);
});

/* ── retitle ──────────────────────────────────────────────────────────── */

test("retitle: ключ Jira з голови збереженої назви вертається перед новим текстом", () => {
  assert.equal(retitle({ id: "a", jira: "LIGA-5", title: "LIGA-5 · Foo" }, "Bar"), "LIGA-5 · Bar");
});

test("retitle: без префікса в назві — просто новий текст (обрізаний)", () => {
  assert.equal(retitle({ id: "a", jira: "LIGA-5", title: "Foo" }, "  Bar "), "Bar");
  assert.equal(retitle({ id: "a", title: "LIGA-5 · Foo" }, "Bar"), "Bar", "без jira префікс — частина назви");
});

test("retitle: інший роздільник із SEP береться той самий, що був", () => {
  assert.equal(retitle({ id: "a", jira: "LIGA-5", title: "liga-5: Foo" }, "Bar"), "liga-5: Bar");
  assert.equal(retitle({ id: "a", jira: "LIGA-5", title: "LIGA-5 — Foo" }, "Bar"), "LIGA-5 — Bar");
});

test("retitle: назва = один ключ (cleanTitle її не ріже) — просто новий текст", () => {
  assert.equal(retitle({ id: "a", jira: "LIGA-5", title: "LIGA-5" }, "Bar"), "Bar");
});

test("retitle ∘ cleanTitle: показане після перейменування — саме набраний текст", () => {
  const t0 = { id: "a", jira: "LIGA-5", title: "LIGA-5 · Foo" };
  assert.equal(cleanTitle({ ...t0, title: retitle(t0, "Bar") }), "Bar");
});
