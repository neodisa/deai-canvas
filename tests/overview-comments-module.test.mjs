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
 *   ЛІГА не зачеплено     — відповідь БЕЗ `module` у `start()` ходить у CDN Supabase. Охоронець G (по тексту).
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { DICT } from "../app/i18n.js";
import { moduleStore, overviewComments } from "../app/overview-comments.js";

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

test("G: відповідь без `module` лишається зашитим ЛІГА — CDN Supabase й CommentLayerSupabase, як було", () => {
  const start = SRC.slice(SRC.indexOf("async function start(key)"), SRC.indexOf("const fail = (e)"));
  assert.match(start, /if \(cfg\.module\) \{\n(?:\s*\/\/[^\n]*\n)?\s*store = await moduleStore\(cfg\);\n\s*\} else if \(cfg\.ch === "project"\) \{/);
  assert.match(start, /if \(!window\.supabase\) await loadScript\(SB_JS\);\n\s+store = window\.CommentLayerSupabase\(\{ url: cfg\.sbUrl, anonKey: cfg\.sbKey, projectId: cfg\.project \}\);/);
  assert.match(start, /window\.CommentLayerLocal\(\{ endpoint: cfg\.endpoint \}\)/);
  assert.match(start, /projectId: cfg\.module \? cfg\.channel : cfg\.project,/, "канал модуля — ключ коментатора");
  assert.match(SRC, /const SB_JS = "https:\/\/cdn\.jsdelivr\.net\/npm\/@supabase\/supabase-js@2";/);
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
  const names = ["window", "document", "fetch", "addEventListener", "CommentLayer", "CommentLayerLocal", "DeaiComments"];
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
    return typeof response === "function" ? response(url) : { ok: true, json: async () => response };
  };
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
const envFor = (b, channel = "project") => ({
  canvasEl: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 100 }) },
  picked: () => "it1", channel: () => channel, audiences: () => [], onAudience() {},
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
    assert.deepEqual(b.fetched, ["/api/comment-config?ch=project&it=it1"]);
    assert.deepEqual(b.appended, ["/api/module-client/m-h/adapter.js"], "жодного CDN Supabase");
    assert.equal(b.created.length, 1);
    assert.equal(b.created[0].endpoint, "http://127.0.0.1:4000");
    assert.equal(b.created[0].channel, "deai/liga/t-1");
    assert.equal(b.inits.length, 1);
    assert.equal(b.inits[0].projectId, "deai/liga/t-1", "ключ коментатора — канал модуля");
    assert.equal(b.inits[0].local, false);
    assert.equal(b.inits[0].version, "3");
    assert.equal(typeof b.inits[0].storage.load, "function");
  } finally { b.restore(); }
});

test("H2: адаптер не завантажився — без винятку назовні: помилка в fail(), шар не піднято, наступний вхід пробує знову", async () => {
  const R = resp({ module: "m-h2", client: ["/api/module-client/m-h2/adapter.js"] });
  const b = browser({ resp: R });             // scripts порожні → onerror
  try {
    const oc = overviewComments(envFor(b));
    oc.enter();
    await settle();
    assert.equal(b.errors.length, 1);
    assert.match(b.errors[0], /\/api\/module-client\/m-h2\/adapter\.js/);
    assert.equal(b.inits.length, 0, "без сховища коментатор не піднімається");
    oc.rebuild();
    await settle();
    assert.equal(b.appended.length, 2, "невдачу не закешовано — повторна спроба");
  } finally { b.restore(); }
});

test("H3: ЛІГА — відповідь без `module` не торкається адаптерів модуля (CDN Supabase, як було)", async () => {
  const R = { ch: "project", project: "dc/t", version: "1", sbUrl: "https://x.supabase.co", sbKey: "k" };
  const b = browser({ resp: R, scripts: { "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2": (el) => {
    globalThis.supabase = {};
    globalThis.CommentLayerSupabase = (o) => { b.created.push(o); return { ready: Promise.resolve() }; };
    el.onload();
  } } });
  try {
    overviewComments(envFor(b)).enter();
    await settle();
    assert.deepEqual(b.errors, []);
    assert.deepEqual(b.appended, ["https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"]);
    assert.deepEqual(b.created, [{ url: "https://x.supabase.co", anonKey: "k", projectId: "dc/t" }]);
    assert.equal(b.inits[0].projectId, "dc/t");
  } finally { delete globalThis.supabase; delete globalThis.CommentLayerSupabase; b.restore(); }
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
  let channel = "project";
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

test("M: `ready` відхилився — сховище закрито ДО відмови (інакше опитування/сокет тече), причина долітає в fail() як є", async () => {
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
      assert.deepEqual(b.errors, ["сервіс не відповів"], "причина — відхилення `ready`, а не збій закриття");
      assert.equal(b.inits.length, 0, "без готового сховища коментатор не піднімається");
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
    assert.deepEqual(b.errors, ["впало"]);
  } finally { b.restore(); }
});
