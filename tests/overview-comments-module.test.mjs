/**
 * «Огляд» і командний канал МОДУЛЯ (2b-2, Task 2): `moduleStore(cfg)` — сховище для відповіді
 * `/api/comment-config?ch=project`, де є `module`: файли адаптера вантажаться по порядку (кожен чекаємо), далі
 * `DeaiComments.create({...config, channel, onChange})`.
 *
 * Мапа «перевірка → запобіжник» (мутаційно):
 *   порядок і очікування  — `for … await load(src)`. Мутація «паралельно / без await» червонить A.
 *   дедуп у списку        — `new Set(cfg.client)`. Мутація «без Set» червонить B.
 *   фабрика кешується     — `factories.get(cfg.module)`. Мутація «вантажити щоразу» червонить C; «кеш за адресою, не за
 *                           модулем» (глобал `DeaiComments` чужого модуля) червонить D.
 *   канал — ядра          — `{...config, channel, onChange}` (порядок ключів). Мутація «config після channel» червонить E.
 *   відмови — з текстом   — нема фабрики / падіння `load` / падіння `create`. Мутація «мовчати» червонить F.
 *   єдиний шлях (4b-2)    — ЛІГА теж веде командний канал модулем (`supabase-comments`): у `start()` нема гілки CDN
 *                           Supabase / `CommentLayerSupabase`, відповідь без `module` — лише локальний канал. Охоронець G
 *                           (по тексту), H3 (наскрізь: ЛІГА-подібна відповідь вантажить обидва файли модуля по порядку).
 *   invalidate()          — (фінальне ревʼю 0.5.0) `cl.destroy(); cl = null` у `invalidate()`: без знищення старий шар
 *                           лишається живим і опитує старий сервіс (червонить N). `epoch` + `stale()` у `start()`: без
 *                           епохи запуск, що летів під час `invalidate()`, піднімає шар поверх нового (червонить N3);
 *                           `gen !== epoch` у `catch` `ensure()`: без нього застарілий запуск, що впав, скидає ключ нового й
 *                           шле помилку в тост (червонить N4). ⚠️ `cfgKey = null` у `invalidate()` мутацією НЕ ловиться — це
 *                           еквівалентна мутація: `cl = null`, `inflight = null` і `epoch` уже дають той самий ефект; рядок
 *                           лишено лише щоб стан не брехав («ключ, під яким піднято» — нічого не піднято).
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

import { DICT } from "../app/i18n.js";
import { moduleStore, overviewComments } from "../app/overview-comments.js";

/* Справжнє `DeaiDualStore` (класичний скрипт `window.*`) — у пісочниці, як у `tests/dual-store.test.mjs`. */
const DUAL_SRC = fs.readFileSync(new URL("../app/vendor/dual-store.js", import.meta.url), "utf8");
function loadDual() {
  const win = {};
  vm.runInNewContext(DUAL_SRC, { window: win });
  return win.DeaiDualStore;
}

const SRC = fs.readFileSync(new URL("../app/overview-comments.js", import.meta.url), "utf8");

/** Світ без DOM: `load` дописує в журнал і ставить `win.DeaiComments` після ОСТАННЬОГО файла модуля. */
function world({ files = {}, failOn = null, slow = false } = {}) {
  const win = {};
  const log = [];
  const created = [];
  const load = async (src) => {
    log.push(`start ${src}`);
    if (slow) await new Promise((r) => setTimeout(r, 5));
    if (src === failOn) throw new Error(`не завантажився ${src}`);
    const f = files[src];
    if (f) f(win, created);
    log.push(`done ${src}`);
  };
  return { win, log, created, load };
}
const factoryOf = (tag) => (win, created) => {
  win.DeaiComments = { create: (cfg) => { created.push({ tag, cfg }); return { tag, ready: Promise.resolve(), load: () => [], save() {} }; } };
};
const resp = (o = {}) => ({
  ch: "project", module: "memo-comments", client: ["/api/module-client/memo-comments/adapter.js"],
  config: { endpoint: "http://127.0.0.1:4000", pubkey: "pk" }, channel: "deai/liga/t-1", version: "3", ...o,
});

test("A: файли адаптера вантажаться ПО ПОРЯДКУ і кожен чекаємо, фабрика береться після останнього", async () => {
  const w = world({ slow: true, files: { "/m/b.js": factoryOf("b") } });
  const store = await moduleStore(resp({ module: "m1", client: ["/m/a.js", "/m/b.js"] }), { load: w.load, win: w.win, factories: new Map() });
  assert.deepEqual(w.log, ["start /m/a.js", "done /m/a.js", "start /m/b.js", "done /m/b.js"]);
  assert.equal(store.tag, "b");
});

test("B: той самий файл двічі в списку вантажиться раз", async () => {
  const w = world({ files: { "/m/a.js": factoryOf("a") } });
  await moduleStore(resp({ module: "m1", client: ["/m/a.js", "/m/a.js"] }), { load: w.load, win: w.win, factories: new Map() });
  assert.deepEqual(w.log, ["start /m/a.js", "done /m/a.js"]);
});

test("C: фабрика модуля кешується — повторний вхід у «Огляд» не вантажить адаптер знову", async () => {
  const w = world({ files: { "/m/a.js": factoryOf("a") } });
  const opts = { load: w.load, win: w.win, factories: new Map() };
  await moduleStore(resp({ module: "m1", client: ["/m/a.js"] }), opts);
  await moduleStore(resp({ module: "m1", client: ["/m/a.js"] }), opts);
  assert.equal(w.log.filter((l) => l.startsWith("start")).length, 1);
  assert.equal(w.created.length, 2, "а сховище — нове щоразу");
});

test("D: два модулі по черзі: повернення до першого бере ЙОГО фабрику, а не глобал `DeaiComments` другого", async () => {
  const w = world({ files: { "/a.js": factoryOf("A"), "/b.js": factoryOf("B") } });
  const opts = { load: w.load, win: w.win, factories: new Map() };
  assert.equal((await moduleStore(resp({ module: "a", client: ["/a.js"] }), opts)).tag, "A");
  assert.equal((await moduleStore(resp({ module: "b", client: ["/b.js"] }), opts)).tag, "B");
  assert.equal((await moduleStore(resp({ module: "a", client: ["/a.js"] }), opts)).tag, "A", "глобал тепер B; кеш — за модулем");
});

test("E: у create іде {...config, channel, onChange}, а канал і гачок — ЯДРА: модуль їх не перекриє", async () => {
  const w = world({ files: { "/m/a.js": factoryOf("a") } });
  await moduleStore(resp({ module: "m1", client: ["/m/a.js"], channel: "deai/liga/t-1",
    config: { endpoint: "http://127.0.0.1:4000", channel: "evil", onChange: "x" } }),
  { load: w.load, win: w.win, factories: new Map() });
  const { cfg } = w.created[0];
  assert.equal(cfg.endpoint, "http://127.0.0.1:4000");
  assert.equal(cfg.channel, "deai/liga/t-1");
  assert.equal(typeof cfg.onChange, "function");
  assert.doesNotThrow(() => cfg.onChange([]));
});

test("E2: `config` відповіді не мутується, а відсутній `config` — не падіння", async () => {
  const w = world({ files: { "/m/a.js": factoryOf("a") } });
  const r = resp({ module: "m1", client: ["/m/a.js"] });
  const before = JSON.stringify(r);
  await moduleStore(r, { load: w.load, win: w.win, factories: new Map() });
  assert.equal(JSON.stringify(r), before);
  const w2 = world({ files: { "/m/a.js": factoryOf("a") } });
  await moduleStore({ ch: "project", module: "m2", client: ["/m/a.js"], channel: "c" }, { load: w2.load, win: w2.win, factories: new Map() });
  assert.deepEqual({ ...w2.created[0].cfg, onChange: 0 }, { channel: "c", onChange: 0 });
});

test("F: нема фабрики після завантаження — помилка словом, а не TypeError; нічого не кешується", async () => {
  const w = world({ files: {} });
  const factories = new Map();
  await assert.rejects(moduleStore(resp({ module: "m1", client: ["/m/a.js"] }), { load: w.load, win: w.win, factories }),
    (e) => e instanceof Error && e.message === DICT.uk.errCommentsAdapter, "порожній `window.DeaiComments`");
  assert.equal(factories.size, 0, "невдача не кешується: наступний вхід спробує знову");
  w.win.DeaiComments = { create: "не функція" };
  await assert.rejects(moduleStore(resp({ module: "m1", client: ["/m/a.js"] }), { load: w.load, win: w.win, factories }),
    (e) => e.message === DICT.uk.errCommentsAdapter);
});

test("F2: падіння завантаження файла і падіння create() долітають до викликача як є", async () => {
  const w = world({ failOn: "/m/b.js", files: { "/m/a.js": factoryOf("a") } });
  await assert.rejects(moduleStore(resp({ module: "m1", client: ["/m/a.js", "/m/b.js"] }),
    { load: w.load, win: w.win, factories: new Map() }), /не завантажився \/m\/b\.js/);
  const w2 = world({ files: { "/m/c.js": (win) => { win.DeaiComments = { create: () => { throw new Error("адаптер впав"); } }; } } });
  await assert.rejects(moduleStore(resp({ module: "m2", client: ["/m/c.js"] }), { load: w2.load, win: w2.win, factories: new Map() }), /адаптер впав/);
});

test("F3: ключ errCommentsAdapter є в обох словниках", () => {
  assert.equal(typeof DICT.uk.errCommentsAdapter, "string");
  assert.equal(typeof DICT.en.errCommentsAdapter, "string");
  assert.notEqual(DICT.uk.errCommentsAdapter, DICT.en.errCommentsAdapter);
});

test("G: старого шляху ЛІГИ (CDN Supabase, CommentLayerSupabase) нема: командний канал — лише модулем, ключ коментатора локальний (Б2)", () => {
  const start = SRC.slice(SRC.indexOf("async function start(key)"), SRC.indexOf("const fail = (e)"));
  assert.match(start, /const local = window\.CommentLayerLocal\(\{ endpoint: cfg\.endpoint \}\);/, "локальна частина — завжди");
  assert.match(start, /try \{ team = await moduleStore\(await cfgOf\("project"\)\); \}\n\s*catch \(e\) \{ why = /, "командне — модулем ролі, збій → teamDown");
  assert.match(start, /projectId: cfg\.project,/, "ключ коментатора — локальний (Б2)");
  for (const gone of ["SB_JS", "CommentLayerSupabase", "supabase-js", "sbUrl", "sbKey", "cdn.jsdelivr.net"]) {
    assert.equal(SRC.includes(gone), false, `${gone} у overview-comments.js`);
  }
});

test("F4: адаптер, що не зареєстрував фабрику, не підхоплює залишок попереднього модуля", async () => {
  const w = world({ files: { "/a.js": factoryOf("A") } });
  const opts = { load: w.load, win: w.win, factories: new Map() };
  await moduleStore(resp({ module: "a", client: ["/a.js"] }), opts);
  await assert.rejects(moduleStore(resp({ module: "b", client: ["/b.js"] }), opts), (e) => e.message === DICT.uk.errCommentsAdapter,
    "глобал лишився від A — але B його не ставив");
  assert.equal(opts.factories.has("b"), false);
});

/* ── H: start() наскрізь, з підставним браузером (document/fetch/CommentLayer) ──────────────────────── */

/** Підставний браузер на `globalThis`; повертає журнали й `restore()`. `scripts[src]` — що робить завантаження файла. */
function browser({ resp: response, scripts = {} }) {
  const saved = {};
  const names = ["window", "document", "fetch", "addEventListener", "CommentLayer", "CommentLayerLocal", "DeaiComments", "DeaiDualStore"];
  for (const n of names) saved[n] = Object.getOwnPropertyDescriptor(globalThis, n);
  const out = { appended: [], created: [], inits: [], fetched: [], errors: [], destroyed: 0 };
  globalThis.window = globalThis;
  globalThis.addEventListener = () => {};
  delete globalThis.DeaiComments;
  globalThis.document = {
    createElement: () => ({}),
    head: { appendChild: (el) => {
      out.appended.push(el.src);
      queueMicrotask(() => { (scripts[el.src] || (() => el.onerror()))(el); });
    } },
  };
  // `response` — тіло (200) або функція `(url) => відповідь fetch` для сценаріїв із помилками й різними каналами
  globalThis.fetch = async (url) => {
    out.fetched.push(url);
    if (typeof response === "function") return response(url);
    // Б2: локальна конфігурація — окремий запит; тіло `response` — відповідь КОМАНДНОГО каналу (`ch=project`)
    return { ok: true, json: async () => (url.includes("ch=local") ? LOCAL_CFG : response) };
  };
  globalThis.DeaiDualStore = loadDual();
  globalThis.CommentLayerLocal = () => ({ ready: Promise.resolve(), load: () => [], save() {} });
  globalThis.CommentLayer = { create: () => ({
    init: (o) => { out.inits.push(o); return { destroy() { out.destroyed += 1; }, store: o.storage }; },
  }) };
  out.restore = () => {
    for (const n of names) {
      if (saved[n]) Object.defineProperty(globalThis, n, saved[n]); else delete globalThis[n];
    }
  };
  return out;
}
const envFor = (b, channel = "dual") => ({
  canvasEl: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 100 }) },
  picked: () => "it1", channel: () => channel, audiences: () => [],
  fail: (e) => b.errors.push(e && e.message),
});
const settle = () => new Promise((r) => setTimeout(r, 30));

test("H: «Огляд» із відповіддю модуля вантажить адаптер із головки, create() і CommentLayer — з каналом ядра", async () => {
  const R = resp({ module: "m-h", client: ["/api/module-client/m-h/adapter.js"] });
  const b = browser({ resp: R, scripts: { "/api/module-client/m-h/adapter.js": (el) => {
    globalThis.DeaiComments = { create: (cfg) => { b.created.push(cfg); return { ready: Promise.resolve(), load: () => [], save() {}, subscribe() {}, close() {} }; } };
    el.onload();
  } } });
  try {
    const oc = overviewComments(envFor(b));
    oc.enter();
    await settle();
    assert.deepEqual(b.errors, []);
    assert.deepEqual(b.fetched, ["/api/comment-config?ch=local&it=it1", "/api/comment-config?ch=project&it=it1"]);
    assert.deepEqual(b.appended, ["/api/module-client/m-h/adapter.js"], "жодного CDN Supabase");
    assert.equal(b.created.length, 1);
    assert.equal(b.created[0].endpoint, "http://127.0.0.1:4000");
    assert.equal(b.created[0].channel, "deai/liga/t-1");
    assert.equal(b.inits.length, 1);
    assert.equal(b.inits[0].projectId, LOCAL_CFG.project, "ключ коментатора — локальний; канал модуля йде лише в адаптер");
    assert.equal(b.inits[0].local, false);
    assert.equal(b.inits[0].version, "3");
    assert.equal(typeof b.inits[0].storage.load, "function");
  } finally { b.restore(); }
});

test("H1: host оболонки (0.26.0) долітає в init коментатора тим самим обʼєктом; без host — поля нема", async () => {
  const R = resp({ module: "m-h", client: ["/api/module-client/m-h/adapter.js"] });
  const mk = (b) => ({ "/api/module-client/m-h/adapter.js": (el) => {
    globalThis.DeaiComments = { create: () => ({ ready: Promise.resolve(), load: () => [], save() {}, subscribe() {}, close() {} }) };
    el.onload();
  } });
  const b = browser({ resp: R, scripts: mk() });
  try {
    const host = { onReady() {}, onChange() {}, onSelect() {}, onMode() {} };
    const oc = overviewComments({ ...envFor(b), host });
    oc.enter();
    await settle();
    assert.deepEqual(b.errors, []);
    assert.equal(b.inits.length, 1);
    assert.equal(b.inits[0].host, host, "init отримує host оболонки як є");
    oc.leave();
    oc.invalidate();
    const oc2 = overviewComments(envFor(b));
    oc2.enter();
    await settle();
    assert.equal(b.inits.at(-1).host, undefined, "без env.host — undefined (поведінка до 0.26.0)");
  } finally { b.restore(); }
});

test("H2: локальна конфігурація відмовила — без винятку назовні: помилка в fail(), шар не піднято, наступний вхід пробує знову", async () => {
  const b = browser({ resp: () => ({ ok: false, status: 502, json: async () => ({ code: "module-error" }) }) });
  try {
    const oc = overviewComments(envFor(b));
    oc.enter();
    await settle();
    assert.deepEqual(b.errors, [DICT.uk.errCommentConfig(502, "module-error")]);
    assert.equal(b.inits.length, 0, "без локального сховища коментатор не піднімається");
    oc.rebuild();
    await settle();
    assert.equal(b.fetched.length, 2, "невдачу не закешовано — повторна спроба");
  } finally { b.restore(); }
});

test("H3: ЛІГА (4b-2) — відповідь `supabase-comments` вантажить обидва файли модуля по порядку, без CDN Supabase", async () => {
  const urls = ["/api/module-client/supabase-comments/supabase.min.js", "/api/module-client/supabase-comments/adapter.js"];
  const R = resp({ module: "supabase-comments", client: urls, config: { url: "https://x.supabase.co", key: "k", shotsBucket: "overview-thumbs" }, channel: "dc/t" });
  const b = browser({ resp: R, scripts: {
    [urls[0]]: (el) => { globalThis.supabase = {}; el.onload(); },
    [urls[1]]: (el) => {
      globalThis.DeaiComments = { create: (cfg) => { b.created.push(cfg); return { ready: Promise.resolve(), load: () => [], save() {} }; } };
      el.onload();
    },
  } });
  try {
    overviewComments(envFor(b)).enter();
    await settle();
    assert.deepEqual(b.errors, []);
    assert.deepEqual(b.appended, urls, "бібліотека — ДО адаптера, жодного CDN");
    assert.equal(b.created.length, 1);
    assert.equal(b.created[0].url, "https://x.supabase.co");
    assert.equal(b.created[0].shotsBucket, "overview-thumbs");
    assert.equal(b.created[0].channel, "dc/t");
    assert.equal(b.inits[0].projectId, LOCAL_CFG.project, "ключ коментатора — локальний; канал ЛІГИ — лише в адаптері");
    assert.equal(b.inits[0].storage.teamDown, null);
  } finally { delete globalThis.supabase; b.restore(); }
});

test("I: нескидаємий глобал (`var` у скрипті адаптера) не кидає TypeError: скидання — присвоєнням, фабрики немає → помилка словом", async () => {
  const win = {};
  Object.defineProperty(win, "DeaiComments", { value: { create: () => ({ stale: true }) }, writable: true, configurable: false });
  const w = world({ files: {} });
  await assert.rejects(moduleStore(resp({ module: "m-i", client: ["/m/a.js"] }), { load: w.load, win, factories: new Map() }),
    (e) => e instanceof Error && !(e instanceof TypeError) && e.message === DICT.uk.errCommentsAdapter,
    "залишок попереднього модуля не підхоплено, а `delete` не кинув");
  assert.equal(win.DeaiComments, undefined, "глобал скинуто до завантаження");
});

test("J: відмова comment-config — у тості код із JSON-тіла (i18n), а не лише «502»; нерозбірне тіло — статус; чужі символи — ні", async () => {
  const fail = (body, status = 502) => ({ ok: false, status, json: async () => { if (body === "not-json") throw new SyntaxError("x"); return body; } });
  const cases = [
    [fail({ ok: false, code: "module-error", error: "приватний текст відповіді" }), DICT.uk.errCommentConfig(502, "module-error")],
    [fail({ ok: false, code: "bad-settings" }, 400), DICT.uk.errCommentConfig(400, "bad-settings")],
    [fail("not-json", 500), DICT.uk.errCommentConfig(500, null)],
    [fail({ code: "<img src=x onerror=1>" }, 409), DICT.uk.errCommentConfig(409, null)],
    [fail({ code: 7 }, 409), DICT.uk.errCommentConfig(409, null)],
  ];
  for (const [res, want] of cases) {
    const b = browser({ resp: () => res });
    try {
      overviewComments(envFor(b)).enter();
      await settle();
      assert.deepEqual(b.errors, [want]);
      assert.equal(b.inits.length, 0);
    } finally { b.restore(); }
  }
  assert.match(DICT.uk.errCommentConfig(502, "module-error"), /502.*module-error/);
  assert.match(DICT.en.errCommentConfig(502, "module-error"), /502.*module-error/);
  assert.doesNotMatch(DICT.uk.errCommentConfig(500, null), /null/);
});

test("K: застарілий запуск (канал перемкнули, поки адаптер готувався) закриває своє сховище й не піднімає другий шар", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const closes = [];
  const R = resp({ module: "m-k", client: ["/api/module-client/m-k/adapter.js"] });
  const LOCAL = { ch: "local", project: "x/local", version: "1", endpoint: "/api/local-comments" };
  const b = browser({
    resp: (url) => ({ ok: true, json: async () => (url.includes("ch=project") ? R : LOCAL) }),
    scripts: { "/api/module-client/m-k/adapter.js": (el) => {
      globalThis.DeaiComments = { create: () => ({ ready: gate, load: () => [], save() {}, close: () => closes.push("closed") }) };
      el.onload();
    } },
  });
  let channel = "dual";
  try {
    const oc = overviewComments({ ...envFor(b), channel: () => channel });
    oc.enter();
    await settle();                       // адаптер завантажено, create() викликано, ready тримається
    assert.equal(b.inits.length, 0);
    channel = "local";
    oc.rebuild();
    await settle();                       // локальний запуск піднявся
    assert.equal(b.inits.length, 1);
    assert.equal(b.inits[0].local, true);
    release();
    await settle();                       // застарілий запуск дочекався ready
    assert.deepEqual(closes, ["closed"], "сховище застарілого запуску закрито (інакше опитування/realtime тече)");
    assert.equal(b.inits.length, 1, "другого інстансу коментатора нема");
    assert.deepEqual(b.errors, []);
  } finally { b.restore(); }
});

test("L: сховище без load/save — помилка словом, створене сховище закрито, фабрика лишається в кеші", async () => {
  const closes = [];
  const bad = {
    noSave: () => ({ ready: Promise.resolve(), load: () => [], close: () => closes.push("noSave") }),
    noLoad: () => ({ ready: Promise.resolve(), save() {}, close: () => closes.push("noLoad") }),
    notFunctions: () => ({ load: 1, save: "x", close: () => closes.push("notFunctions") }),
    nothing: () => null,
    closeThrows: () => ({ close: () => { closes.push("closeThrows"); throw new Error("close впав"); } }),
  };
  for (const [name, make] of Object.entries(bad)) {
    const w = world({ files: { "/m/a.js": (win) => { win.DeaiComments = { create: make }; } } });
    const factories = new Map();
    await assert.rejects(moduleStore(resp({ module: "m-l", client: ["/m/a.js"] }), { load: w.load, win: w.win, factories }),
      (e) => e instanceof Error && !(e instanceof TypeError) && e.message === DICT.uk.errCommentsStore, name);
    assert.equal(factories.has("m-l"), true, `${name}: фабрика справна — кеш лишається, повторний вхід не вантажить файли знову`);
  }
  assert.deepEqual(closes, ["noSave", "noLoad", "notFunctions", "closeThrows"], "кожне створене сховище закрито (`null` — нема що)");
});

test("L2: справжнє сховище (load і save) проходить; `ready`, `close` і решта — необовʼязкові", async () => {
  const w = world({ files: { "/m/a.js": (win) => { win.DeaiComments = { create: () => ({ load: () => [], save() {} }) }; } } });
  const store = await moduleStore(resp({ module: "m-l2", client: ["/m/a.js"] }), { load: w.load, win: w.win, factories: new Map() });
  assert.equal(typeof store.load, "function");
});

test("L3: ключ errCommentsStore є в обох словниках", () => {
  assert.equal(typeof DICT.uk.errCommentsStore, "string");
  assert.equal(typeof DICT.en.errCommentsStore, "string");
  assert.notEqual(DICT.uk.errCommentsStore, DICT.en.errCommentsStore);
});

test("M: `ready` командного відхилився — сховище закрито (інакше опитування/сокет тече), причина долітає в teamDown як є, «Огляд» живий", async () => {
  for (const closeThrows of [false, true]) {
    const closes = [];
    const R = resp({ module: `m-m${closeThrows}`, client: [`/api/module-client/m-m${closeThrows}/adapter.js`] });
    const b = browser({ resp: R, scripts: { [`/api/module-client/m-m${closeThrows}/adapter.js`]: (el) => {
      globalThis.DeaiComments = { create: () => ({
        ready: Promise.reject(new Error("сервіс не відповів")), load: () => [], save() {},
        close: () => { closes.push("closed"); if (closeThrows) throw new Error("close впав"); },
      }) };
      el.onload();
    } } });
    try {
      overviewComments(envFor(b)).enter();
      await settle();
      assert.deepEqual(closes, ["closed"], `closeThrows=${closeThrows}`);
      assert.deepEqual(b.errors, [], "Б2: падіння командного не валить «Огляд»");
      assert.equal(b.inits.length, 1, "шар піднявся на локальних");
      assert.equal(b.inits[0].storage.teamDown, "сервіс не відповів", "причина — відхилення `ready`, а не збій закриття");
    } finally { b.restore(); }
  }
});

test("M2: сховище без `close` і з відхиленим `ready` — та сама причина, без TypeError", async () => {
  const R = resp({ module: "m-m2", client: ["/api/module-client/m-m2/adapter.js"] });
  const b = browser({ resp: R, scripts: { "/api/module-client/m-m2/adapter.js": (el) => {
    globalThis.DeaiComments = { create: () => ({ ready: Promise.reject(new Error("впало")), load: () => [], save() {} }) };
    el.onload();
  } } });
  try {
    overviewComments(envFor(b)).enter();
    await settle();
    assert.deepEqual(b.errors, []);
    assert.equal(b.inits[0].storage.teamDown, "впало");
  } finally { b.restore(); }
});

test("M3: `ready` ЛОКАЛЬНОГО сховища відхилився — це вже падіння «Огляду»: обидва сховища закрито, причина — у fail()", async () => {
  const closes = [];
  const R = resp({ module: "m-m3", client: ["/api/module-client/m-m3/adapter.js"] });
  const b = browser({ resp: R, scripts: { "/api/module-client/m-m3/adapter.js": (el) => {
    globalThis.DeaiComments = { create: () => ({ ready: Promise.resolve(), load: () => [], save() {}, close: () => closes.push("team") }) };
    el.onload();
  } } });
  globalThis.CommentLayerLocal = () => ({ ready: Promise.reject(new Error("локальний не відповів")), load: () => [], save() {}, close: () => closes.push("local") });
  try {
    overviewComments(envFor(b)).enter();
    await settle();
    assert.deepEqual(b.errors, ["локальний не відповів"]);
    assert.equal(b.inits.length, 0);
    assert.deepEqual([...closes].sort(), ["local", "team"], "комбіноване закриває обидва");
  } finally { b.restore(); }
});

/* ── N: invalidate() — «Огляд» після зміни модуля коментарів (фінальне ревʼю 0.5.0) ─────────────────────── */

/** Світ двох сервісів (`mod` — id модуля: кеш фабрик `FACTORIES` спільний на файл, тож кожному тесту свій id): `state.which`
 *  каже, чия адреса зараз у відповіді comment-config; адаптер модуля реєструє фабрику, що
 *  складає кожне створене сховище в `made` (з адресою) і пише його закриття в `closes`. `gates[endpoint]` — що тримає
 *  `ready` цього сховища (запуск «у дорозі»). */
function twoServices(mod, { gates = {} } = {}) {
  const state = { which: "http://a", made: [], closes: [] };
  const b = browser({
    resp: () => ({ ok: true, json: async () => resp({ module: mod, client: [`/api/module-client/${mod}/adapter.js`], config: { endpoint: state.which } }) }),
    scripts: { [`/api/module-client/${mod}/adapter.js`]: (el) => {
      globalThis.DeaiComments = { create: (cfg) => {
        state.made.push(cfg.endpoint);
        return { endpoint: cfg.endpoint, ready: gates[cfg.endpoint] ?? Promise.resolve(), load: () => [{ id: cfg.endpoint }], save() {}, close: () => state.closes.push(cfg.endpoint) };
      } };
      el.onload();
    } },
  });
  return { b, state };
}

test("N: invalidate() забуває інстанс — наступний вхід читає comment-config заново і піднімає шар на НОВОМУ сервісі", async () => {
  const { b, state } = twoServices("m-n");
  try {
    const oc = overviewComments(envFor(b));
    oc.enter();
    await settle();
    assert.deepEqual(state.made, ["http://a"]);
    assert.equal(b.inits.length, 1);
    /* Свідок: БЕЗ invalidate() перебудова полотна нового сервісу не бачить — ключ «ітерація|канал» той самий. Саме це
       й було вадою: людина міняє адресу на екрані «Підключення», а нові піни йшли б у старий сервіс до перезавантаження. */
    state.which = "http://b";
    oc.rebuild();
    await settle();
    assert.equal(b.fetched.length, 2, "свідок: ключ той самий — ensure() нічого не перечитує");
    assert.deepEqual(state.made, ["http://a"]);

    oc.invalidate();
    assert.equal(b.destroyed, 1, "старий шар знищено (а з ним закрито й сховище: опитування старого сервісу зупиняється)");
    assert.equal(oc.layer, null, "інстанса нема до наступного входу");
    oc.rebuild();
    await settle();
    assert.equal(b.fetched.length, 4, "comment-config (обидва) прочитано заново");
    assert.deepEqual(state.made, ["http://a", "http://b"], "нове сховище — на новій адресі");
    assert.equal(b.inits.length, 2);
    assert.deepEqual([...b.inits[1].storage.load()].map((c) => c.id), ["http://b"], "живий шар сидить на новому сховищі");
    assert.equal(b.appended.length, 1, "фабрика модуля в кеші: файли адаптера вдруге не вантажаться");
    assert.deepEqual(b.errors, []);
  } finally { b.restore(); }
});

test("N2: invalidate() у «Огляді», що вже не на екрані, теж працює: наступний enter() піднімає шар заново; порожній invalidate() не падає", async () => {
  const { b, state } = twoServices("m-n2");
  try {
    const oc = overviewComments(envFor(b));
    assert.doesNotThrow(() => oc.invalidate(), "до першого входу інстанса нема — нема що знищувати");
    oc.enter();
    await settle();
    oc.leave();
    state.which = "http://b";
    oc.invalidate();
    oc.enter();
    await settle();
    assert.deepEqual(state.made, ["http://a", "http://b"]);
    assert.equal(b.inits.length, 2);
    assert.equal(b.destroyed, 1);
  } finally { b.restore(); }
});

test("N3: запуск, що летів ПІД ЧАС invalidate(), не підніме застарілий шар поверх нового (той самий ключ, інша «епоха»)", async () => {
  let release;
  const gateA = new Promise((r) => { release = r; });
  const { b, state } = twoServices("m-n3", { gates: { "http://a": gateA } });
  try {
    const oc = overviewComments(envFor(b));
    oc.enter();
    await settle();                       // адаптер завантажено, create(a) викликано, ready тримається
    assert.deepEqual(state.made, ["http://a"]);
    assert.equal(b.inits.length, 0);
    state.which = "http://b";
    oc.invalidate();                      // модулі змінились, поки старий запуск ще чекає свого сховища
    oc.rebuild();                         // той самий ключ «ітерація|канал» — а запуск уже ІНШИЙ
    await settle();
    assert.equal(b.inits.length, 1, "новий шар піднявся на B");
    release();
    await settle();                       // застарілий запуск дочекався ready
    assert.deepEqual(state.closes, ["http://a"], "сховище застарілого запуску закрито");
    assert.equal(b.inits.length, 1, "застарілий запуск не підняв другий шар (і не затер новий)");
    assert.deepEqual([...b.inits[0].storage.load()].map((c) => c.id), ["http://b"], "живий шар сидить на НОВОМУ сховищі");
    assert.deepEqual(b.errors, []);
  } finally { b.restore(); }
});

test("N4: застарілий запуск, що ВПАВ після invalidate(), мовчить і не скидає ключ нового запуску (інакше новий шар перечитується вдруге, а помилка йде в тост)", async () => {
  let reject;
  const gateA = new Promise((_, no) => { reject = no; });
  const { b, state } = twoServices("m-n4", { gates: { "http://a": gateA } });
  try {
    const oc = overviewComments(envFor(b));
    oc.enter();
    await settle();                       // create(a) викликано, ready тримається
    state.which = "http://b";
    oc.invalidate();
    oc.rebuild();
    await settle();
    assert.equal(b.inits.length, 1, "новий шар піднявся на B");
    const fetched = b.fetched.length;
    reject(new Error("старий сервіс не відповів"));
    await settle();                       // застарілий запуск упав
    assert.deepEqual(b.errors, [], "падіння застарілого запуску — не наша справа: тосту нема");
    assert.deepEqual(state.closes, ["http://a"], "його сховище закрито");
    oc.rebuild();
    await settle();
    assert.equal(b.fetched.length, fetched, "ключ нового запуску цілий: ensure() нічого не перечитує");
    assert.equal(b.inits.length, 1, "другого шару нема");
  } finally { b.restore(); }
});

/* ── Б2 (0.27.0), T7: «Огляд» на комбінованому сховищі ───────────────────────────────────────────────── */

const LOCAL_CFG = { ch: "local", project: "deai/liga/it1/local", version: "3", endpoint: "/api/local-comments" };
const AUDS = [{ id: "local", color: "#7C6CF0", private: true }, { id: "project" }];
const dualEnv = (b, channel) => ({ ...envFor(b, channel), audiences: () => AUDS });
const adapterOk = (b, urlOf, extra = {}) => ({ [urlOf]: (el) => {
  globalThis.DeaiComments = { create: (cfg) => { b.created.push(cfg); return { ready: Promise.resolve(), load: () => [], save() {}, subscribe() {}, close() {}, ...extra }; } };
  el.onload();
} });

test("T7-1: channel 'dual' — два запити comment-config (local, project); сховище комбіноване з teamDown === null; projectId — з локальної відповіді", async () => {
  const R = resp({ module: "m-t7a", client: ["/api/module-client/m-t7a/adapter.js"], channel: "deai/liga/t-1" });
  const b = browser({ resp: (url) => ({ ok: true, json: async () => (url.includes("ch=project") ? R : LOCAL_CFG) }) });
  const scripts = adapterOk(b, "/api/module-client/m-t7a/adapter.js");
  globalThis.document.head.appendChild = (el) => { b.appended.push(el.src); queueMicrotask(() => scripts[el.src](el)); };
  try {
    overviewComments(dualEnv(b, "dual")).enter();
    await settle();
    assert.deepEqual(b.errors, []);
    assert.deepEqual(b.fetched, ["/api/comment-config?ch=local&it=it1", "/api/comment-config?ch=project&it=it1"]);
    assert.equal(b.inits.length, 1);
    const o = b.inits[0];
    assert.equal(o.storage.teamDown, null, "командне піднялось");
    assert.equal(o.projectId, "deai/liga/it1/local", "ключ коментатора — локальний");
    assert.equal(o.local, false);
    assert.deepEqual(o.audiences, AUDS);
    assert.equal(b.created.length, 1, "адаптер модуля створено для командної частини");
    assert.equal(b.created[0].channel, "deai/liga/t-1");
    assert.equal(o.onAudience, undefined, "перемикання каналу зникло з контракту");
  } finally { b.restore(); }
});

test("T7-2: командний конфіг відмовив (409) — «Огляд» піднято на локальних, teamDown = причина, env.fail мовчить", async () => {
  const b = browser({ resp: (url) => (url.includes("ch=project")
    ? { ok: false, status: 409, json: async () => ({ error: "no-provider" }) }
    : { ok: true, json: async () => LOCAL_CFG }) });
  try {
    overviewComments(dualEnv(b, "dual")).enter();
    await settle();
    assert.deepEqual(b.errors, [], "падіння командного не валить «Огляд»");
    assert.equal(b.inits.length, 1);
    assert.equal(typeof b.inits[0].storage.teamDown, "string");
    assert.ok(b.inits[0].storage.teamDown.length > 0);
    assert.equal(b.inits[0].local, false);
  } finally { b.restore(); }
});

test("T7-2b: адаптер командного не завантажився — теж лише teamDown, шар піднявся", async () => {
  const R = resp({ module: "m-t7b", client: ["/api/module-client/m-t7b/adapter.js"], channel: "c" });
  const b = browser({ resp: (url) => ({ ok: true, json: async () => (url.includes("ch=project") ? R : LOCAL_CFG) }) });   // scripts порожні → onerror
  try {
    overviewComments(dualEnv(b, "dual")).enter();
    await settle();
    assert.deepEqual(b.errors, []);
    assert.equal(b.inits.length, 1);
    assert.match(b.inits[0].storage.teamDown, /m-t7b\/adapter\.js/);
  } finally { b.restore(); }
});

test("T7-3: channel 'local' — один запит ch=local, сховище локальне, local: true, аудиторій нема", async () => {
  const b = browser({ resp: LOCAL_CFG });
  const mine = { ready: Promise.resolve(), load: () => [], save() {} };
  globalThis.CommentLayerLocal = (o) => { b.localOpts = o; return mine; };
  try {
    overviewComments(dualEnv(b, "local")).enter();
    await settle();
    assert.deepEqual(b.errors, []);
    assert.deepEqual(b.fetched, ["/api/comment-config?ch=local&it=it1"]);
    assert.equal(b.localOpts.endpoint, "/api/local-comments");
    assert.equal(b.inits[0].storage, mine, "саме локальне сховище, без обгортки");
    assert.equal(b.inits[0].local, true);
    assert.deepEqual(b.inits[0].audiences, []);
  } finally { b.restore(); }
});
