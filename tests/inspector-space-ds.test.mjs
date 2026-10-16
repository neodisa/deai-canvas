/**
 * Токени ДС ПРОСТОРУ в інспекторі (етап 2а, Task 7).
 *
 * Інспектор звіряє значення з дизайн-системою. До 2а ДС була одна — статичний
 * знімок `ds-tokens.js` за напрямком задачі (`?ds=united`). Тепер у простору є
 * свій постачальник токенів (модуль `css-tokens` читає CSS-файл), а сервер
 * віддає їх на `GET /api/ds-tokens?space=<id>`. Інспектор живе в документі
 * макета й мусить дізнатись про них САМ — по `sp` у власному URL.
 *
 * Що тут стережеться, і чому окремо від решти інспектора:
 *   · ЧИСТІ функції вибору (`spaceTokensFrom`, `pickDsRaw`) — відповідь сервера
 *     не довіряється наосліп, а профіль `space:…` береться ЛИШЕ з відповіді;
 *   · ЗАВАНТАЖУВАЧ (`loadSpaceTokens`) — фонова спроба, яка нічого не ламає:
 *     збій, тайм-аут, 404, `{profile:null}` — це всі один стан «токенів
 *     простору немає», і статичний профіль лишається як був;
 *   · ПРОВОДКА в `inspector.js` — реєстрація СИНХРОННА (жодного `await` на
 *     верхньому рівні: рамку макета канвас бере одним `load`, і модуль, що
 *     висить на мережі, прийшов би після нього), токени приходять у фоні, а
 *     перемальовка — той самий шлях, що й після кручення ручки (`_tuned`).
 *
 * Модуль `inspector.js` вантажимо В NODE зі штучними `window`/`document`/`fetch`:
 * його імпорт без DOM нічого не робить, доки не кликнуто `init`, а `import.meta`
 * несе параметри запиту, тобто саме ту дорогу, якою йде `sp` у браузері.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  dsIndex, dsVerdict, isSpaceProfile, pickDsRaw, spaceTokensFrom,
} from "../app/vendor/inspector-core.js";
import {
  collectRules, ds, dsInfo, loadSpaceTokens, setDsProfile, setDsTokens,
} from "../app/vendor/inspector-dom.js";
import { readSource, stripComments } from "./_sources.mjs";

const BODY = (o = {}) => ({
  profile: "space:s1", tokens: { "--a": ["#fff"], "--b": ["1rem", "2rem"] },
  source: "tokens.css", ...o,
});
const OK = (body) => ({ ok: true, status: 200, json: async () => body });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test.beforeEach(() => setDsProfile(null));

/* ── чисті функції ──────────────────────────────────────────────────────── */

test("isSpaceProfile: лише `space:<id>`", () => {
  assert.equal(isSpaceProfile("space:s1"), true);
  for (const p of ["united", "space", "space:", "", null, undefined, 5, "xspace:s1"]) {
    assert.equal(isSpaceProfile(p), false, String(p));
  }
});

test("spaceTokensFrom: придатна відповідь → профіль, токени, джерело", () => {
  const got = spaceTokensFrom(BODY(), "s1");
  assert.deepEqual(got, BODY());
  assert.equal(spaceTokensFrom(BODY({ source: undefined }), "s1").source, "",
    "джерело — рядок завжди: панель підставляє його в текст");
  assert.equal(spaceTokensFrom(BODY({ source: 7 }), "s1").source, "");
});

test("spaceTokensFrom: усе інше — null (= «токенів простору немає»)", () => {
  const bad = [
    null, undefined, "x", 5, [], {},
    { profile: null },                                   // постачальника нема
    { profile: null, error: "check-timeout" },           // модуль упав
    BODY({ profile: "space:other" }),                    // відповідь про ІНШИЙ простір
    BODY({ profile: "united" }),
    BODY({ tokens: {} }),                                // порожня мапа: словник без імен
    BODY({ tokens: null }),
    BODY({ tokens: [] }),
    BODY({ tokens: { "--a": "#fff" } }),                 // значення — не список
    BODY({ tokens: { "--a": [1] } }),                    // у списку не рядок
  ];
  for (const b of bad) assert.equal(spaceTokensFrom(b, "s1"), null, JSON.stringify(b));
  assert.equal(spaceTokensFrom(BODY(), ""), null);
  assert.equal(spaceTokensFrom(BODY(), undefined), null);
});

test("spaceTokensFrom: токен із ПОРОЖНІМ списком значень — валідний (var(), що не розкрилась)", () => {
  const got = spaceTokensFrom(BODY({ tokens: { "--a": [] } }), "s1");
  assert.deepEqual(got.tokens, { "--a": [] });
});

test("pickDsRaw: профіль простору — ЛИШЕ з відповіді, статичні — зі знімка", () => {
  const live = { profile: "space:s1", tokens: { "--a": ["1px"] }, source: "t.css" };
  const statics = { united: { "--u": ["2px"] }, "space:s1": { "--static": ["3px"] } };
  assert.deepEqual(pickDsRaw("space:s1", live, statics), { "--a": ["1px"] });
  // відповідь про інший простір не підставляється (і статичний «двійник» — теж)
  assert.equal(pickDsRaw("space:s2", live, statics), null);
  assert.equal(pickDsRaw("space:s1", null, statics), null,
    "профіль простору без відповіді сервера не береться зі статики");
  assert.deepEqual(pickDsRaw("united", live, statics), { "--u": ["2px"] });
  assert.equal(pickDsRaw("seo", live, statics), null, "напрямку без ДС — null, а не порожній словник");
  assert.equal(pickDsRaw(null, live, statics), null);
  assert.equal(pickDsRaw("", live, statics), null);
});

test("pickDsRaw: статичний профіль — ВЛАСНА властивість, не успадкована з прототипу", () => {
  for (const p of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
    assert.equal(pickDsRaw(p, null, {}), null, p);
  }
});

/* ── dsVerdict для порожнього списку значень ───────────────────────────── */

test("dsVerdict: токен простору з ПОРОЖНІМ списком — 'token', а не 'overridden'", () => {
  const d = dsIndex("space:s1", { "--a": [], "--b": ["#fff"] });
  assert.deepEqual(dsVerdict(d, "--a", "#123456"), { state: "token", want: [] });
  // контроль: непорожній список поводиться як раніше
  assert.equal(dsVerdict(d, "--b", "#123456").state, "overridden");
  assert.equal(dsVerdict(d, "--b", "#fff").state, "token");
  assert.equal(dsVerdict(d, "--zzz", "#fff").state, "off-ds");
});

/* ── стан модуля: що відповідають ds() і dsInfo() ───────────────────────── */

test("setDsTokens: ds() і dsInfo() віддають токени простору, а не статику", () => {
  setDsProfile("united");
  assert.equal(ds().known, false, "статичного знімка в заглушці нема");      // і кеш прогріто
  setDsTokens("space:s1", { "--a": ["#fff"], "--e": [] }, "tokens.css");
  const d = ds();
  assert.equal(d.known, true, "кеш ds() скинуто: прогріте DS_NONE не залишилось");
  assert.equal(d.profile, "space:s1");
  assert.deepEqual([...d.tokens.keys()], ["--a", "--e"]);
  assert.deepEqual(d.tokens.get("--e"), []);
  assert.deepEqual(dsInfo(), { profile: "space:s1", known: true, source: "tokens.css" });
});

test("setDsProfile після токенів простору повертає статичний профіль", () => {
  setDsTokens("space:s1", { "--a": ["#fff"] }, "tokens.css");
  setDsProfile("united");
  assert.equal(ds().profile, "united");
  assert.equal(ds().known, false);
  assert.equal("source" in dsInfo(), false, "статичний профіль не несе `source`");
  assert.ok("commit" in dsInfo() && "figma" in dsInfo(), "статичні поля лишились");
});

/* ── завантажувач ───────────────────────────────────────────────────────── */

test("loadSpaceTokens: успіх → setDsTokens, ПОТІМ onTokens; fetch із сигналом і закодованим id", async () => {
  setDsProfile("united");
  ds();                                          // прогріти кеш
  const calls = [];
  const seen = [];
  const res = await loadSpaceTokens("s 1", {
    fetchFn: async (url, opts) => { calls.push({ url, opts }); return OK(BODY({ profile: "space:s 1" })); },
    onTokens: () => seen.push(dsInfo().profile),
  });
  assert.equal(res, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/ds-tokens?space=s%201");
  assert.ok(calls[0].opts.signal instanceof AbortSignal);
  assert.deepEqual(seen, ["space:s 1"], "перемальовку просять, коли токени вже ЛЕЖАТЬ у модулі");
  assert.equal(ds().known, true);
});

test("loadSpaceTokens: куди ходити — як сказав викликач", async () => {
  let got = null;
  await loadSpaceTokens("s1", {
    url: "http://h:1/api/ds-tokens?space=s1",
    fetchFn: async (url) => { got = url; return OK({ profile: null }); },
  });
  assert.equal(got, "http://h:1/api/ds-tokens?space=s1");
});

test("loadSpaceTokens: збій, 404, 503, {profile:null}, крива відповідь — те саме «токенів немає»", async () => {
  const cases = {
    "мережа": async () => { throw new TypeError("Failed to fetch"); },
    "тайм-аут (AbortError)": async () => { throw new DOMException("t", "AbortError"); },
    "404": async () => ({ ok: false, status: 404, json: async () => ({ ok: false }) }),
    "503": async () => ({ ok: false, status: 503, json: async () => ({}) }),
    // відмова з тілом, схожим на успіх: статус — перший, а не додатковий довід
    "500 із придатним тілом": async () => ({ ok: false, status: 500, json: async () => BODY() }),
    "profile:null": async () => OK({ profile: null }),
    "profile:null + error": async () => OK({ profile: null, error: "check-timeout" }),
    "не JSON": async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError("x"); } }),
    "порожня мапа": async () => OK(BODY({ tokens: {} })),
    "чужий простір": async () => OK(BODY({ profile: "space:zzz" })),
    "порожня відповідь": async () => undefined,
  };
  for (const [name, fetchFn] of Object.entries(cases)) {
    setDsProfile("united");
    ds();
    let asked = 0;
    const res = await loadSpaceTokens("s1", { fetchFn, onTokens: () => { asked += 1; } });
    assert.equal(res, false, name);
    assert.equal(asked, 0, `${name}: перемальовувати нема чого`);
    assert.equal(ds().profile, "united", `${name}: статичний профіль лишився`);
    assert.equal(ds().known, false, name);
  }
});

test("loadSpaceTokens: без профілю напрямку збій лишає DS_NONE (профіль null)", async () => {
  setDsProfile(null);
  const res = await loadSpaceTokens("s1", { fetchFn: async () => ({ ok: false, status: 404 }) });
  assert.equal(res, false);
  assert.equal(ds().known, false);
  assert.equal(ds().profile, null);
});

test("loadSpaceTokens: повільний сервер — сигнал спрацьовує, обіцянка не висить і не падає", async () => {
  // Чесний `fetch` відхиляється на `signal.abort`; штучний робить те саме.
  const fetchFn = (url, { signal }) => new Promise((_, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason));
  });
  const t0 = Date.now();
  /* Таймер `AbortSignal.timeout` у Node не тримає цикл подій (unref): без
     власного живого таймера процес вийшов би, не діждавшись обіцянки. */
  const keep = setInterval(() => {}, 10);
  let res;
  try {
    res = await loadSpaceTokens("s1", { fetchFn, timeoutMs: 30 });
  } finally {
    clearInterval(keep);
  }
  assert.equal(res, false);
  assert.ok(Date.now() - t0 < 1500, "тайм-аут справді короткий");
});

test("loadSpaceTokens: власний тайм-аут — довший за серверний (5 с), щоб вердикт сервера дійшов", async () => {
  let ms = null;
  const realTimeout = AbortSignal.timeout;
  AbortSignal.timeout = (n) => { ms = n; return realTimeout.call(AbortSignal, n); };
  try {
    await loadSpaceTokens("s1", { fetchFn: async () => OK({ profile: null }) });
  } finally {
    AbortSignal.timeout = realTimeout;
  }
  assert.equal(ms, 7000);
});

test("loadSpaceTokens: падіння onTokens не вилітає назовні — токени вже застосовані", async () => {
  const res = await loadSpaceTokens("s1", {
    fetchFn: async () => OK(BODY()),
    onTokens: () => { throw new Error("перемальовка впала на чужому макеті"); },
  });
  assert.equal(res, true);
  assert.equal(ds().profile, "space:s1");
});

/* ── inspector.js: проводка ─────────────────────────────────────────────── */

function stubDom() {
  const saved = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch };
  globalThis.window = globalThis;
  globalThis.document = { readyState: "loading", addEventListener() {} };
  return () => {
    for (const [k, v] of Object.entries(saved)) {
      if (v === undefined) delete globalThis[k]; else globalThis[k] = v;
    }
    delete globalThis.CanvasInspector;
  };
}

/** `import()` із таймаутом: модуль із `await` на верхньому рівні, що висить на
 *  мережі, не повернув би керування ніколи — тест мусить упасти, а не зависнути. */
async function importInspector(query) {
  const p = import(`../app/vendor/inspector.js?${query}`);
  const hung = Symbol("hung");
  const r = await Promise.race([p, sleep(2000).then(() => hung)]);
  assert.notEqual(r, hung, "inspector.js не завершив вантаження, поки fetch висить: await на верхньому рівні");
  return globalThis.CanvasInspector;
}

test("inspector.js: sp у URL → фоновий fetch; реєстрація не чекає; токени → ds() + перемальовка піна", async () => {
  const restore = stubDom();
  try {
    const calls = [];
    let release;
    const pending = new Promise((r) => { release = r; });
    globalThis.fetch = (url, opts) => { calls.push({ url: String(url), opts }); return pending; };
    const I = await importInspector("ds=united&sp=s1");

    assert.ok(I && typeof I.init === "function", "window.CanvasInspector зареєстровано, поки fetch ще висить");
    assert.equal(calls.length, 1, "рівно один фоновий запит");
    assert.match(calls[0].url, /\/api\/ds-tokens\?space=s1$/);
    assert.ok(calls[0].opts.signal instanceof AbortSignal);
    assert.equal(dsInfo().profile, "united", "до відповіді діє статичний напрямок із ?ds=");

    const painted = [];
    I._tuned = () => painted.push("tuned");
    I.pinned = { isConnected: true };
    release(OK(BODY()));
    await sleep(30);

    assert.deepEqual(dsInfo(), { profile: "space:s1", known: true, source: "tokens.css" });
    assert.deepEqual(painted, ["tuned"], "запінений елемент перемальовано рівно раз, наявним шляхом");
  } finally {
    restore();
  }
});

test("inspector.js: sp у URL кодується — інакше `&` в id розбив би запит", async () => {
  const restore = stubDom();
  try {
    const calls = [];
    globalThis.fetch = async (url) => { calls.push(String(url)); return OK({ profile: null }); };
    await importInspector("sp=a%20b%26c%2Fd");          // id: «a b&c/d»
    assert.equal(calls.length, 1);
    assert.match(calls[0], /\/api\/ds-tokens\?space=a%20b%26c%2Fd$/,
      "без encodeURIComponent `&` став би другим параметром, а `/` — шляхом");
    assert.equal(new URL(calls[0]).searchParams.get("space"), "a b&c/d", "сервер прочитає той самий id");
    assert.equal([...new URL(calls[0]).searchParams.keys()].length, 1);
  } finally {
    restore();
  }
});

test("inspector.js: нема піна — токени застосовано, перемальовувати нічого", async () => {
  const restore = stubDom();
  try {
    globalThis.fetch = async () => OK(BODY({ profile: "space:s2" }));
    const I = await importInspector("sp=s2");          // без ?ds=: статичного профілю нема
    let painted = 0;
    I._tuned = () => { painted += 1; };
    await sleep(30);
    assert.equal(dsInfo().profile, "space:s2");
    assert.equal(painted, 0);
    I._dsArrived();                                      // і прямий виклик без піна не кидає
    assert.equal(painted, 0);
  } finally {
    restore();
  }
});

test("inspector.js: збої fetch не лишають ні винятку, ні нового профілю", async () => {
  for (const [n, fetchFn] of [
    ["мережа", async () => { throw new TypeError("Failed to fetch"); }],
    ["404", async () => ({ ok: false, status: 404, json: async () => ({}) })],
    ["profile:null", async () => OK({ profile: null })],
  ]) {
    const restore = stubDom();
    try {
      globalThis.fetch = fetchFn;
      setDsProfile(null);
      const I = await importInspector(`ds=united&sp=f${n.length}`);
      let painted = 0;
      I._tuned = () => { painted += 1; };
      I.pinned = { isConnected: true };
      await sleep(30);
      assert.equal(dsInfo().profile, "united", n);
      assert.equal(painted, 0, n);
    } finally {
      restore();
    }
  }
});

test("inspector.js: без sp у URL — жодного запиту (стара розмітка, публікація, голий макет)", async () => {
  for (const q of ["ds=united", "", "sp="]) {
    const restore = stubDom();
    try {
      let n = 0;
      globalThis.fetch = async () => { n += 1; return OK(BODY()); };
      await importInspector(q ? `${q}&z=${Math.random()}` : `z=${Math.random()}`);
      await sleep(10);
      assert.equal(n, 0, `query «${q}»`);
    } finally {
      restore();
    }
  }
});

/** Документ-«пустушка» для `collectRules`: правила розрізняються за ІМЕНЕМ конструктора. */
class CSSStyleRule {
  constructor(sel) { this.selectorText = sel; this.style = {}; this.cssRules = []; }
}
const fakeDoc = (...sels) => ({
  defaultView: {}, styleSheets: [{ cssRules: sels.map((s) => new CSSStyleRule(s)) }],
});

test("inspector.js: `_dsArrived` скидає кеш правил документа — і з пінем, і без", async () => {
  const restore = stubDom();
  try {
    globalThis.fetch = async () => OK({ profile: null });
    const I = await importInspector(`z=${Math.random()}`);
    I._tuned = () => {};
    for (const pinned of [null, { isConnected: true }]) {
      I.pinned = pinned;
      const doc = fakeDoc("a");
      assert.equal(collectRules(doc).rules.length, 1);
      doc.styleSheets[0].cssRules.push(new CSSStyleRule("b"));
      assert.equal(collectRules(doc).rules.length, 1, "контроль: кеш діє, доки його не скинули");
      I._dsArrived();
      assert.equal(collectRules(doc).rules.length, 2, "invalidate(): макет прочитано наново");
    }
  } finally {
    restore();
  }
});

test("inspector.js: `_dsArrived` — той самий шлях перемальовки, що й після ручки тюнера", async () => {
  const restore = stubDom();
  try {
    globalThis.fetch = async () => OK({ profile: null });
    const I = await importInspector(`z=${Math.random()}`);
    const log = [];
    I._tuned = () => log.push("tuned");
    I.pinned = null;
    I._dsArrived();
    assert.deepEqual(log, []);
    I.pinned = { isConnected: true };
    I._dsArrived();
    assert.deepEqual(log, ["tuned"]);
  } finally {
    restore();
  }
});

/* ── сирець inspector.js ────────────────────────────────────────────────── */

test("inspector.js: жодного top-level await, і реєстрація — ДО фонового запиту", () => {
  const raw = readSource("vendor/inspector.js");
  const src = stripComments(raw);
  // 1) модуль без `import` і `import.meta` розбирається як тіло НЕасинхронної функції:
  //    `await x` поза `async` — SyntaxError. Ловить і відступні форми (`try { await … }`).
  const body = src
    .replace(/^import[\s\S]*?;\s*$/gm, "")
    .replace(/import\.meta\.url/g, "'file:///x.js'");
  assert.doesNotThrow(() => new Function(body), "inspector.js має синтаксичну помилку або top-level await");
  // 2) форма `await(…)` у функції-не-async розбирається як ВИКЛИК — ловимо окремо, по нульовому відступу
  assert.doesNotMatch(src, /^[^\s/*].*\bawait\b/m, "рядок верхнього рівня з await");
  assert.doesNotMatch(src, /^await\b/m);
  // 3) порядок: реєстрація модуля, і лише потім фоновий запит
  const reg = src.indexOf("window.CanvasInspector = Inspector");
  const load = src.indexOf("loadSpaceTokens(");
  assert.ok(reg > 0 && load > reg, "loadSpaceTokens стартує ПІСЛЯ реєстрації window.CanvasInspector");
  assert.match(src, /searchParams\.get\(['"]sp['"]\)/, "sp береться з URL власного модуля");
});

test("дорога `source` до пакета тюнера: dsInfo() → report() → app.js setDs", () => {
  /* Звіт про ДС їде до пакета без перепакування: `report()` віддає `dsInfo`
     цілком, а `app.js` кладе його в `setDs`. Якщо хтось почне збирати `dsInfo`
     поіменно (як інші поля звіту), `source` загубиться тихо — пакет скаже
     `space:<id>`, а з якого файла ДС, читач не дізнається. */
  const insp = stripComments(readSource("vendor/inspector.js"));
  assert.match(insp, /dsInfo:\s*rep\.dsInfo/, "report() віддає dsInfo цілком");
  const app = stripComments(readSource("app.js"));
  assert.match(app, /setDs\(tuneState,\s*rep\.dsInfo\)/, "app.js віддає dsInfo цілком у setDs");
});

test("самоперевірка охоронця: top-level await він справді б упіймав", () => {
  const bad = "const a = 1;\ntry {\n  await fetch('/x');\n} catch (e) {}\n";
  assert.throws(() => new Function(bad));
  const ok = "async function f() { await 1; }\nf();\n";
  assert.doesNotThrow(() => new Function(ok));
});
