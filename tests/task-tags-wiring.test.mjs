/**
 * Проводка міток задач у `app/app.js` (етап 4b-3, Task 4): кнопка «Мітки» на картці, діалог правки, поле в «Новій задачі»,
 * збережений стан екрана. `app.js` у Node не імпортується (DOM на верхньому рівні), тож функції виконуються із заглушками
 * (`load`, як у `tests/vcs-client.test.mjs`): перевіряється ПОВЕДІНКА тіл, а не лише рядки джерела; статично стережеться
 * лише те, що виконанням не побачиш (порядок гілок, сам запис у `localStorage`).
 *
 * Правила міток (довжина, кома, межа числа, дублікати) — на сервері (`tests/test_task_tags.py`); тут — що клієнт шле,
 * показує й не ламає навколо.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { setLang, t } from "../app/i18n.js";
import { requestErrText, taskErrField, taskErrKey } from "../app/spaces-model.js";
import { parseTags, tagsFormHTML } from "../app/space-dialogs.js";
import { effectiveTab, pruneFilters } from "../app/tasks-home.js";
import { readHomeUi } from "../app/tasks-model.js";

test.beforeEach(() => setLang("uk"));

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

function balanced(open) {
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(open, i + 1); }
  }
  throw new Error("немає закриття дужки");
}
/** Повний текст функції-декларації верхнього рівня (`[async ]function name(…) {…}`). */
function declSource(name) {
  const m = new RegExp(`\\n((?:async )?function ${name}\\()`).exec(src);
  assert.ok(m, `у app.js нема функції ${name}`);
  const start = m.index + 1;
  const open = src.indexOf("{", src.indexOf(")", start));
  return src.slice(start, open) + balanced(open);
}
const fn = (name) => { const s = declSource(name); return s.slice(s.indexOf("{")); };
function load(env, funcs) {
  const decls = funcs.map(declSource).join("\n");
  // eslint-disable-next-line no-new-func
  return new Function("env", `with (env) { ${decls}\nreturn { ${funcs.map((f) => `${f}: ${f}`).join(", ")} }; }`)(env);
}
const tick = () => new Promise((r) => setImmediate(r));

/* ── клік по «Мітки» всередині картки не відкриває задачу ─────────────────────────────────────────────────── */

/**
 * Мінімальне дерево вузлів зі справжньою семантикою `closest` (найближчий предок-або-сам, що підходить): картка
 * `data-th="open"` містить кнопку `data-th="tags"`. Селектори — ті, що кличе `wireHome` (`a`, `[data-cn]`, `[data-th]`).
 */
function node(tag, dataset, parent = null) {
  const n = { tag, dataset, parent };
  n.closest = (sel) => {
    for (let x = n; x; x = x.parent) {
      if (sel === "a" ? x.tag === "a" : sel === "[data-cn]" ? "cn" in x.dataset : sel === "[data-th]" ? "th" in x.dataset : false) return x;
    }
    return null;
  };
  return n;
}

function wireEnv(over = {}) {
  const log = { open: [], tags: [], paint: 0 };
  const env = {
    log,
    homePage: "tasks", wiz: { click: () => { throw new Error("майстер не мав би бути"); } },
    homeUi: { tab: "mine", status: "active", tags: new Set(), designers: new Set() }, homeData: { mine: [], team: null },
    effectiveTab, saveHomeUi: () => {}, paintHome: () => { log.paint += 1; }, paintHomeLower: () => {},
    homeOpenTask: (id) => log.open.push(id), editTaskTags: (id) => log.tags.push(id),
    connAction: () => { throw new Error("не картка «Підключення»"); },
    ...over,
  };
  return env;
}
function wire(env) {
  const handlers = {};
  load(env, ["wireHome"]).wireHome({ addEventListener: (type, f) => { handlers[type] = f; }, querySelector: () => null });
  return handlers;
}

test("клік по кнопці «Мітки» на картці відкриває діалог міток, а НЕ задачу; клік по самій картці відкриває задачу", () => {
  const env = wireEnv();
  const { click } = wire(env);
  const grid = node("div", {});
  const card = node("div", { th: "open", id: "t1" }, grid);
  const btn = node("button", { th: "tags", id: "t1" }, card);
  const icon = node("span", {}, btn);                       // клік по іконці/тексту всередині кнопки
  click({ target: btn });
  click({ target: icon });
  assert.deepEqual(env.log.tags, ["t1", "t1"], "діалог міток");
  assert.deepEqual(env.log.open, [], "задача не відкрилась");
  click({ target: node("div", {}, card) });                 // клік по тілу картки
  assert.deepEqual(env.log.open, ["t1"], "картка, як і раніше, відкриває задачу");
  assert.deepEqual(env.log.tags, ["t1", "t1"]);
});

test("кнопка «Мітки» на картці ЧУЖОЇ задачі команди й посилання «Превʼю» діалогу не відкривають", () => {
  const env = wireEnv();
  const { click } = wire(env);
  const link = node("a", {}, node("div", { th: "open", id: "t1" }));
  click({ target: link });
  assert.deepEqual([env.log.open, env.log.tags], [[], []], "посилання — своя навігація");
});

test("wireHome: гілки tag/designer і reset — по новому ключу (чипи міток, скидання), старого `profile` нема", () => {
  const body = fn("wireHome");
  assert.match(body, /case 'tag': case 'designer': \{\n\s+const set = b\.dataset\.th === 'tag' \? homeUi\.tags : homeUi\.designers;/);
  assert.match(body, /case 'tags': editTaskTags\(b\.dataset\.id\); break;/);
  assert.match(body, /homeUi\.q = ''; homeUi\.status = 'all'; homeUi\.tags\.clear\(\); homeUi\.designers\.clear\(\);/);
  assert.doesNotMatch(body, /profile/i);
});

test("клік по чипу мітки перемикає ключ у homeUi.tags і перемальовує нижню частину", () => {
  const env = wireEnv();
  let lower = 0;
  env.paintHomeLower = () => { lower += 1; };
  const { click } = wire(env);
  const chip = node("button", { th: "tag", v: "alpha" });
  click({ target: chip });
  assert.deepEqual([...env.homeUi.tags], ["alpha"]);
  click({ target: chip });
  assert.deepEqual([...env.homeUi.tags], []);
  assert.equal(lower, 2);
});

/* ── діалог правки міток ──────────────────────────────────────────────────────────────────────────────────── */

function tagsEnv(over = {}) {
  const log = { form: [], toast: [], focus: [], paint: 0, saved: 0, ask: 0 };
  const env = {
    log,
    homeData: { current: "t1", mine: [{ id: "t1", tags: ["alpha", "Beta"] }, { id: "t2", tags: ["alpha"] }, { id: "t3", tags: [] }], team: null },
    homeUi: { tags: new Set(), designers: new Set() },
    homeOpen: true,
    homeReady: () => Array.isArray(env.homeData && env.homeData.mine),
    homeNode: () => ({ querySelector: (s) => { log.focusBack = s; return null; } }),
    CSS: { escape: (x) => x },
    askForm: async (build, opts) => { log.ask += 1; env.html = build(); env.opts = opts; },
    postForm: async (p, b) => { log.form.push([p, b]); return env.reply; },
    reply: { ok: true, tags: ["gamma"] },
    saveHomeUi: () => { log.saved += 1; },
    paintHome: () => { log.paint += 1; },
    toast: (m) => log.toast.push(m),
    tagsFormHTML, parseTags, pruneFilters, requestErrText, taskErrKey, t,
    ...over,
  };
  return env;
}
const open = async (id, over) => {
  const env = tagsEnv(over);
  await load(env, ["editTaskTags"]).editTaskTags(id);
  const ctl = { form: {}, focus: (n) => env.log.focus.push(n) };
  return { env, ctl, submit: (tags) => env.opts.onSubmit({ tags }, ctl) };
};

test("діалог міток: поле заповнене поточними мітками рядка «Моїх» (через «, »), екранується; без рядка — діалог не відкривається", async () => {
  const { env } = await open("t1");
  assert.match(env.html, /id="tg-tags" name="tags" type="text" value="alpha, Beta"/);
  assert.equal((await open("t3")).env.html.includes('value=""'), true, "задача без міток — порожнє поле");
  const evil = await open("t1", { homeData: { mine: [{ id: "t1", tags: ['"><img src=x>'] }] } });
  assert.doesNotMatch(evil.env.html, /<img/);
  const none = await open("nope");
  assert.equal(none.env.log.ask, 0, "нема рядка — нема діалогу");
  const gone = await open("t1", { homeData: null });
  assert.equal(gone.env.log.ask, 0, "дані екрана ще не прийшли — не кидає й не відкриває");
});

test("діалог міток: збереження шле {id, tags} на /api/task-tags, оновлює лише рядок цієї задачі й перемальовує екран", async () => {
  const { env, submit } = await open("t1");
  const before = env.homeData.mine[1];
  const r = await submit("gamma, , delta");
  assert.equal(r, undefined, "успіх — діалог закривається");
  assert.deepEqual(env.log.form, [["/api/task-tags", { id: "t1", tags: ["gamma", "delta"] }]]);
  assert.deepEqual(env.homeData.mine.map((x) => [x.id, x.tags]), [["t1", ["gamma"]], ["t2", ["alpha"]], ["t3", []]],
    "мітки з ВІДПОВІДІ сервера (він міг нормалізувати), чужі рядки не чіпані");
  assert.equal(env.homeData.mine[1], before, "інший рядок — той самий обʼєкт");
  assert.equal(env.log.paint, 1);
  assert.equal(env.homeData.current, "t1", "решта відповіді екрана цілa");
});

test("діалог міток: прибрали останню мітку, за якою стояв фільтр, — фільтр знімається й записується (екран не лишається порожнім невидимо)", async () => {
  const { env, submit } = await open("t1", { homeUi: { tags: new Set(["beta", "alpha"]), designers: new Set() },
    homeData: { mine: [{ id: "t1", tags: ["alpha", "Beta"] }, { id: "t2", tags: ["alpha"] }] }, reply: { ok: true, tags: ["alpha"] } });
  await submit("alpha");
  assert.deepEqual([...env.homeUi.tags], ["alpha"], "beta більше нема в жодної задачі");
  assert.equal(env.log.saved, 1, "стан екрана записано");
  assert.equal(env.log.paint, 1);
  const quiet = await open("t2", { homeUi: { tags: new Set(["alpha"]), designers: new Set() } });
  await quiet.submit("alpha");
  assert.equal(quiet.env.log.saved, 0, "фільтр цілий — нічого не пишемо");
});

test("діалог міток: bad-tags — текст під полем «Мітки», діалог лишається, дані екрана не чіпані; інша відмова — тост і закриття", async () => {
  const bad = await open("t1", { postForm: async () => { throw Object.assign(new Error("a tag is 1..32"), { code: "bad-tags", status: 400 }); } });
  const text = await bad.submit("a,b");
  assert.equal(text, t("tagsBad"), "рядок → діалог лишається відкритим");
  assert.deepEqual(bad.env.log.focus, ["tags"], "фокус і aria-invalid — на полі");
  assert.deepEqual([bad.env.log.paint, bad.env.log.toast], [0, []]);
  assert.deepEqual(bad.env.homeData.mine[0].tags, ["alpha", "Beta"]);
  for (const [code, status] of [["unknown-task", 404], ["ambiguous-task", 409], [undefined, undefined], ["timeout", undefined]]) {
    const r = await open("t1", { postForm: async () => { throw Object.assign(new Error("boom"), { code, status }); } });
    assert.equal(await r.submit("a"), undefined, `${code}: діалог закривається`);
    assert.deepEqual(r.env.log.toast, [t("errFailed", "boom")], `${code}: тост`);
    assert.deepEqual([r.env.log.focus, r.env.log.paint], [[], 0]);
  }
});

test("діалог міток: екран перечитали, поки запит летів, — правимо поточні дані, а не старий знімок; даних нема — не кидає", async () => {
  const { env, submit } = await open("t1");
  env.postForm = async () => { env.homeData = { mine: [{ id: "t1", tags: ["old"] }, { id: "t9", tags: [] }], team: null }; return { ok: true, tags: ["x"] }; };
  await submit("x");
  assert.deepEqual(env.homeData.mine.map((r) => [r.id, r.tags]), [["t1", ["x"]], ["t9", []]]);
  const gone = await open("t1");
  gone.env.postForm = async () => { gone.env.homeData = null; return { ok: true, tags: ["x"] }; };
  await assert.doesNotReject(() => gone.submit("x"));
  assert.equal(gone.env.log.paint, 0);
  const odd = await open("t1", { reply: { ok: true } });
  assert.equal(await odd.submit("x"), undefined, "відповідь без tags — дані лишаються як були");
  assert.deepEqual(odd.env.homeData.mine[0].tags, ["alpha", "Beta"]);
});

test("діалог міток: фокус після закриття — на кнопку «Мітки» ТІЄЇ Ж картки (вона перемальована)", async () => {
  const { env } = await open("t1");
  env.opts.focusBack();
  assert.equal(env.log.focusBack, '[data-th="tags"][data-id="t1"]');
});

/* ── поле «Мітки» в «Новій задачі»: код відмови → текст і поле ─────────────────────────────────────────────── */

test("bad-tags: код → ключ tagsBad → поле tags (під полем, а не загальний текст)", () => {
  assert.equal(taskErrKey("bad-tags"), "tagsBad");
  assert.equal(taskErrField("tagsBad"), "tags");
  assert.equal(taskErrField("idBad"), "id", "наявні відповідності не зсунулись");
  assert.equal(taskErrField("taskErrVcsTarget"), "repo");
  assert.equal(taskErrKey("nonsense"), "taskErrGeneric");
});

/* ── збережений стан екрана: запис і читання ──────────────────────────────────────────────────────────────── */

test("homeUi: читання через readHomeUi (у try), запис — ключ tags без profiles", () => {
  const ui = fn("saveHomeUi");
  assert.match(ui, /tags: \[\.\.\.homeUi\.tags\], designers: \[\.\.\.homeUi\.designers\]/);
  assert.doesNotMatch(ui, /profiles/);
  assert.match(src, /try \{ return readHomeUi\(JSON\.parse\(localStorage\.getItem\(HOME_KEY\) \|\| 'null'\)\); \} catch \(e\) \{ return readHomeUi\(null\); \}/);
  assert.doesNotMatch(src, /homeUi\.profiles|\.profiles\.clear|data-th="profile"|case 'profile'/);
});

test("збережений стан: старий запис 0.10.0 (profiles) і новий (tags) читаються в ті самі ключі; запис→читання кругом тримає мітки", () => {
  const old = JSON.stringify({ tab: "mine", sort: "recent", status: "all", profiles: ["united", "SEO"], designers: [] });
  assert.deepEqual([...readHomeUi(JSON.parse(old)).tags], ["united", "seo"]);
  const saved = JSON.stringify({ tab: "mine", sort: "title", status: "done", tags: ["alpha", "beta"], designers: ["Ольга"] });
  const back = readHomeUi(JSON.parse(saved));
  assert.deepEqual([[...back.tags], [...back.designers], back.sort, back.status], [["alpha", "beta"], ["Ольга"], "title", "done"]);
});

/* ── «Нова задача»: тіло запиту і проводка ────────────────────────────────────────────────────────────────── */

test("«Нова задача»: поле «Мітки» є в обох формах (з «Репозиторієм» і без), а tags у тілі — лише непорожні", () => {
  assert.match(fn("openNewTaskCard"), /taskFormHTML\(\{ inline: true, tags: true, \.\.\.\(withRepo \? \{ repo: \{\} \} : \{\}\) \}\)/);
  const body = fn("createTask");
  assert.match(body, /const tags = parseTags\(vals\.tags\);/);
  assert.match(body, /\.\.\.\(tags\.length \? \{ tags \} : \{\}\)/);
});
