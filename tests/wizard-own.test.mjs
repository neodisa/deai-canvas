/**
 * Свої модулі простору в майстрі (Deai 0.7.0, етап 3c; спека, «Майстер (крок 2)» з поправками 2 і 10 плану):
 * `needsTrust`, НЕзмінний `initialPick`, операція `untrusted` у `writePlan`, рядок свого модуля на кроці 2 у трьох станах і
 * рядок «чекає довіри» на кроці 3; `trustFrom` контролера (ЗІБРАНО З ДЖЕРЕЛА й запущено з підставними залежностями — DOM нема).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { refusalView } from "../app/connections-model.js";
import { t } from "../app/i18n.js";
import { errOffRows, holdersByRole, initialPick, needsTrust, offRows, pickedInOrder, prunePick, writePlan } from "../app/wizard-model.js";
import { wizardHTML } from "../app/wizard-view.js";

const M = (id, roles, extra = {}) => ({ id, name: id, roles, enabled: false, status: "unchecked", settings: [], ...extra });
const OWN = (id, roles, extra = {}) => M(id, roles, { custom: true, builtin: false, trust: "untrusted", runs: false,
  record: false, status: "untrusted", source: `~/w/modules/${id}`, ...extra });

test("needsTrust: свій без робочого коду — так; свій зі знімком і вбудований — ні", () => {
  assert.equal(needsTrust(OWN("a", ["publish"])), true);
  assert.equal(needsTrust(OWN("a", ["publish"], { trust: "refused", status: "error" })), true);
  assert.equal(needsTrust(OWN("a", ["publish"], { trust: "changed", runs: true, status: "ok" })), false);
  assert.equal(needsTrust(M("vercel-publish", ["publish"])), false);
});

test("initialPick НЕ змінено: увімкнений недовірений (колега закомітив) — вибраний, тож writePlan його НЕ вимикає", () => {
  const list = [OWN("acme", ["publish"], { enabled: true }), M("vercel-publish", ["publish"])];
  const pick = initialPick(list);
  assert.deepEqual([...pick], ["acme"]);
  assert.deepEqual(offRows(list, pick), []);
  assert.deepEqual(writePlan({ list, pick, forms: new Map(), atPick: holdersByRole(list), prevList: list }), [],
    "ні disable, ні settings (картки й форми нема)");
});

test("writePlan: вибраний невключений модуль, що тепер потребує довіри, — операція untrusted, а не enable", () => {
  const was = [OWN("acme", ["publish"], { trust: "trusted", runs: true, status: "ok" })];
  const now = [OWN("acme", ["publish"])];
  assert.deepEqual(writePlan({ list: now, pick: new Set(["acme"]), forms: new Map(), atPick: holdersByRole(was), prevList: was }),
    [{ op: "untrusted", id: "acme", roles: ["publish"], stale: [] }]);
});

test("writePlan: untrusted не звільняє роль — тримач тієї ж ролі не отримує ні disable, ні заміни", () => {
  /* Вибраний «acme» (недовірений тепер) стоїть у ролі, яку тримає «vercel-publish»: заміни не буде, тож і вимикати тримача
     нема чого — відмова `untrusted` нічого не змінює в просторі. */
  const was = [OWN("acme", ["publish"], { trust: "trusted", runs: true, status: "ok" }), M("vercel-publish", ["publish"], { enabled: true })];
  const now = [OWN("acme", ["publish"]), M("vercel-publish", ["publish"], { enabled: true })];
  assert.deepEqual(writePlan({ list: now, pick: new Set(["acme"]), forms: new Map(), atPick: holdersByRole(was), prevList: was })
    .map((o) => o.op), ["untrusted"]);
});

const V2 = (list, pick, over = {}) => ({
  step: 2, created: true, busy: false, s1: { name: "S", color: "space-1", path: "~/s", folderFirst: false },
  s2: { list, failed: null, capsError: false, pick, path: "~/s" },
  s3: { cards: [], offs: [], waits: [], failed: null, loading: false },
  s4: { title: "", id: "", source: "empty", from: "", spaceName: "S", tasks: 0 }, ...over,
});

test("крок 2: недовірений — радіо вимкнене, пігулка «свій», «Довіритись…» ПОЗА label; увімкнений — ще й причина", () => {
  const h = wizardHTML(V2([OWN("acme", ["publish"], { enabled: true })], new Set(["acme"])));
  assert.match(h, /<div class="wz-opt-row"><label class="wz-opt" for="wz-o-0-0"><input type="radio" id="wz-o-0-0" name="wz-r-0" value="acme" data-wz-pick data-role="publish" checked disabled>/);
  assert.match(h, /<span class="cn-tag cn-tag--own" title="~\/w\/modules\/acme">свій<\/span>/);
  assert.match(h, /<\/label><button type="button" class="ctl ctl--out" data-wz="trust" data-id="acme">.*Довіритись…<\/button><\/div>/s);
  assert.match(h, /class="wz-opt-why".*йому не довірено/s);
  const off = wizardHTML(V2([OWN("acme", ["publish"])], new Set()));
  assert.match(off, /value="acme" data-wz-pick data-role="publish" disabled>/);
  assert.doesNotMatch(off, /wz-opt-why/, "невключений недовірений — без причини: просто чекає довіри");
});

test("крок 2: «Довіритись…» не всередині label — клік по кнопці в label клікнув би й радіо", () => {
  const h = wizardHTML(V2([OWN("acme", ["publish"])], new Set()));
  const label = /<label class="wz-opt"[\s\S]*?<\/label>/.exec(h)?.[0] ?? "";
  assert.ok(label.length > 0);
  assert.doesNotMatch(label, /data-wz="trust"/, "кнопка потрапила в label");
  assert.equal((h.match(/data-wz="trust"/g) || []).length, 1);
});

test("крок 2: refused без знімка — радіо вимкнене й причина, кнопки нема; changed — вибирається з рядком «є зміни»", () => {
  /* Лише перевірка розмітки: на практиці `refused` без знімка має `roles: []` (ролі «на папері» беруться зі знімка чи
     маніфесту, що читається), тож такий рядок у секції ролі майже не трапляється — але якщо запис прийде, `optionHTML` мусить
     намалювати його правильно. */
  const r = wizardHTML(V2([OWN("acme", ["publish"], { trust: "refused", status: "error", trust_error: "too-big", error: "too-big: 6 MiB" })], new Set()));
  assert.match(r, /value="acme" data-wz-pick data-role="publish" disabled>/);
  assert.match(r, /class="wz-opt-why".*Тека завелика/s);
  assert.doesNotMatch(r, /data-wz="trust"|wz-opt-row/);
  const c = wizardHTML(V2([OWN("acme", ["publish"], { trust: "changed", runs: true, status: "ok" })], new Set()));
  assert.match(c, /value="acme" data-wz-pick data-role="publish">/, "радіо доступне");
  assert.match(c, /<span class="wz-opt-trust">.*У теці є зміни/s);
  assert.doesNotMatch(c, /data-wz="trust"|wz-opt-row/, "зі знімком вибирається й так — кнопки нема");
});

test("крок 2: refused зі знімком (працює попередня версія) — радіо доступне, рядок про нову версію, кнопки нема", () => {
  const h = wizardHTML(V2([OWN("acme", ["publish"], { trust: "refused", runs: true, status: "ok", trust_error: "symlink" })], new Set()));
  assert.match(h, /value="acme" data-wz-pick data-role="publish">/);
  assert.match(h, /<span class="wz-opt-trust">.*Нову версію теки не можна довірити/s);
  assert.doesNotMatch(h, /data-wz="trust"/);
});

test("крок 2: вбудований модуль — як було (без пігулки «свій», без рядка довіри, без кнопки)", () => {
  const h = wizardHTML(V2([M("vercel-publish", ["publish"])], new Set()));
  assert.doesNotMatch(h, /cn-tag--own|wz-opt-trust|data-wz="trust"|wz-opt-row/);
  assert.match(h, /<label class="wz-opt" for="wz-o-0-0"><input type="radio" id="wz-o-0-0" name="wz-r-0" value="vercel-publish" data-wz-pick data-role="publish">/);
});

test("крок 2: назва свого модуля з диска екранується, у пігулці — шлях теки", () => {
  const h = wizardHTML(V2([OWN("acme", ["publish"], { name: "<img src=x onerror=1>", source: "~/a\"><b>" })], new Set()));
  assert.doesNotMatch(h, /<img/);
  assert.match(h, /<b>&lt;img src=x onerror=1&gt;<\/b>/);
  assert.match(h, /title="~\/a&quot;&gt;&lt;b&gt;"/, "шлях у підказці пігулки не виходить з атрибута");
});

test("крок 2: «Замість» — лише модулю, який можна вибрати: недовіреному (його не вибрати) не показується, довіреному — так", () => {
  const holder = M("vercel-publish", ["publish"], { enabled: true });
  const untrusted = wizardHTML(V2([OWN("acme", ["publish"]), holder], new Set(["vercel-publish"])));
  const own = /<div class="wz-opt-row">[\s\S]*?<\/div>/.exec(untrusted)?.[0] ?? "";
  assert.ok(own.includes('value="acme"'));
  assert.doesNotMatch(own, /wz-opt-instead/, "недовірений не замінить тримача — «Замість» йому не потрібне");
  const trusted = wizardHTML(V2([OWN("acme", ["publish"], { trust: "trusted", runs: true, status: "ok" }), holder], new Set(["vercel-publish"])));
  assert.match(trusted, /value="acme"[^>]*>[\s\S]*?wz-opt-instead/, "довірений, що замінить тримача, — «Замість»");
});

test("крок 2 зайнятий: «Довіритись…» теж вимкнена", () => {
  assert.match(wizardHTML(V2([OWN("acme", ["publish"])], new Set(), { busy: "save" })), /data-wz="trust" data-id="acme" disabled>/);
});

test("крок 3: рядок «чекає довіри» замість картки; без карток — не «нічого не підключаємо»", () => {
  const e = OWN("acme", ["publish"], { enabled: true, name: "<b>Acme</b>" });
  const h = wizardHTML(V2([e], new Set(["acme"]), { step: 3,
    s3: { cards: [], offs: [], waits: [{ entry: e, result: null }], failed: null, loading: false } }));
  assert.match(h, /<ul class="wz-waits"><li class="wz-wait" data-id="acme" tabindex="-1">/);
  assert.match(h, /Публікація: «&lt;b&gt;Acme&lt;\/b&gt;» чекає довіри/);
  assert.doesNotMatch(h, /Нічого не підключаємо|wz-card/);
});

test("крок 3: відмова `untrusted` показується в рядку «чекає довіри» (role=alert), а решта карток — поруч", () => {
  const e = OWN("acme", ["publish"], { enabled: true });
  const card = { entry: M("css-tokens", ["tokens"], { enabled: true, status: "ok" }), fields: [], values: {}, erase: [], errors: {}, result: null };
  const h = wizardHTML(V2([e, card.entry], new Set(["acme", "css-tokens"]), { step: 3,
    s3: { cards: [card], offs: [], waits: [{ entry: e, result: { kind: "refused", key: "cnRefUntrusted", detail: "" } }], failed: null, loading: false } }));
  assert.match(h, /<li class="wz-wait" data-id="acme"[^>]*>.*<div class="cn-res cn-res--err" role="alert">.*Модуль не довірено на цьому компʼютері/s);
  assert.match(h, /wz-card/);
  assert.ok(h.indexOf("wz-waits") < h.indexOf("wz-card"), "рядки очікування — над картками");
});

test("крок 3: стан без `waits` (старий вигляд s3) — як було", () => {
  const h = wizardHTML(V2([], new Set(), { step: 3, s3: { cards: [], offs: [], failed: null, loading: false } }));
  assert.match(h, /Нічого не підключаємо/);
  assert.doesNotMatch(h, /wz-waits/);
});

/* ── `trustFrom` контролера: зібрано з джерела ────────────────────────────────────────────────────────── */

const W = readFileSync(new URL("../app/wizard.js", import.meta.url), "utf8");
function fnSrc(name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(W);
  assert.ok(m, `функції ${name} нема`);
  const open = W.indexOf("{", W.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < W.length; i += 1) {
    if (W[i] === "{") depth += 1;
    else if (W[i] === "}") { depth -= 1; if (depth === 0) return W.slice(m.index, i + 1); }
  }
  throw new Error(`немає закриття для ${name}`);
}

/** `trustFrom` з підставним станом майстра; `log` пише виклики в порядку. */
function trustEnv({ wz, lost = true, radio = null, open = async () => true, onLoad = null } = {}) {
  const log = [];
  const focusOf = (what) => ({ focus: (o) => log.push(["focus", what, o]) });
  const state = { wz };
  const found = { radio: radio ? focusOf("radio") : null, button: focusOf("button") };
  const deps = {
    openTrust: async (e, spaceId) => { log.push(["openTrust", e.id, spaceId]); return open(); },
    node: () => ({ querySelector: (sel) => { log.push(["query", sel]); return sel.startsWith("input[") ? found.radio : (sel.startsWith("[data-wz=") ? found.button : null); } }),
  };
  let api;
  const loadStep2 = async () => { log.push(["loadStep2"]); await onLoad?.(api); };
  const focusLost = () => lost;
  const CSS = { escape: (s) => `<${s}>` };
  const code = `let wz = state.wz;\n${fnSrc("trustFrom")}\nreturn { trustFrom, drop: () => { wz = null; }, swap: (v) => { wz = v; } };`;
  api = new Function("state", "deps", "loadStep2", "focusLost", "CSS", code)(state, deps, loadStep2, focusLost, CSS);
  return { ...api, log, deps };
}
const WZ = (over = {}) => ({ step: 2, busy: false, spaceId: "alpha", list: [OWN("acme", ["publish"]), M("vercel-publish", ["publish"])], ...over });

test("trustFrom: діалог для простору МАЙСТРА, далі loadStep2, далі фокус на кнопку (радіо ще вимкнене)", async () => {
  const env = trustEnv({ wz: WZ() });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.map((x) => x[0]), ["openTrust", "loadStep2", "query", "query", "focus"]);
  assert.deepEqual(env.log[0], ["openTrust", "acme", "alpha"]);
  assert.deepEqual(env.log[2], ["query", 'input[data-wz-pick][value="<acme>"]:not([disabled])']);
  assert.deepEqual(env.log[3], ["query", '[data-wz="trust"][data-id="<acme>"]'], "id йде через CSS.escape");
  assert.deepEqual(env.log[4], ["focus", "button", { preventScroll: true }]);
});

test("trustFrom: довіру дали — фокус на радіо модуля (воно вже доступне), а не на кнопку", async () => {
  const env = trustEnv({ wz: WZ(), radio: true });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.filter((x) => x[0] === "focus"), [["focus", "radio", { preventScroll: true }]]);
});

test("trustFrom: фокус не втрачено (людина вже кудись перейшла) — не чіпаємо", async () => {
  const env = trustEnv({ wz: WZ(), lost: false, radio: true });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.map((x) => x[0]), ["openTrust", "loadStep2"]);
});

test("trustFrom: список перечитується ЗАВЖДИ після діалогу — і коли довіри не дали (false): колега міг змінити теку", async () => {
  const env = trustEnv({ wz: WZ(), open: async () => false });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.slice(0, 2).map((x) => x[0]), ["openTrust", "loadStep2"]);
});

test("trustFrom: майстер закрили чи підмінили, поки висів діалог, — список не чіпаємо", async () => {
  const closed = trustEnv({ wz: WZ(), open: async () => { closed.drop(); return true; } });
  await closed.trustFrom("acme");
  assert.deepEqual(closed.log.map((x) => x[0]), ["openTrust"], "майстер закрито — нічого не перечитуємо й не фокусуємо");
  const swapped = trustEnv({ wz: WZ(), open: async () => { swapped.swap(WZ()); return true; } });
  await swapped.trustFrom("acme");
  assert.deepEqual(swapped.log.map((x) => x[0]), ["openTrust"], "відкрито новий майстер — старий не торкаємо");
});

test("trustFrom: крок змінився, поки висів діалог (інший крок) — список кроку 2 не перечитуємо", async () => {
  const wz = WZ();
  const env = trustEnv({ wz, open: async () => { wz.step = 3; return true; } });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.map((x) => x[0]), ["openTrust"]);
});

test("trustFrom: закрили майстер, поки йшло перечитування, — фокус не ставимо", async () => {
  const env = trustEnv({ wz: WZ(), radio: true, onLoad: (api) => api.drop() });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.map((x) => x[0]), ["openTrust", "loadStep2"], "wz !== mine — ні запитів вузла, ні фокуса");
});

test("trustFrom: зайнятий майстер, не крок 2, нема майстра чи модуля зі списку — діалогу не відкриваємо", async () => {
  for (const [what, wz] of [["зайнятий", WZ({ busy: "save" })], ["крок 3", WZ({ step: 3 })], ["нема майстра", null],
    ["список не прочитано", WZ({ list: null })], ["нема модуля", WZ({ list: [M("x", ["publish"])] })]]) {
    const env = trustEnv({ wz });
    await env.trustFrom("acme");
    assert.deepEqual(env.log, [], what);
  }
});

/* ── `loadStep3` і `runOp` контролера (зібрано з джерела): що з вибраними, яких тут не виконати ───────────────────────── */

/** Збирає функції `names` з wizard.js; `env` — залежності замикання (імена — як у файлі). */
function buildFns(names, env) {
  const keys = Object.keys(env);
  const code = `${names.map(fnSrc).join("\n")}\nreturn { ${names.join(", ")} };`;
  return new Function(...keys, code)(...keys.map((k) => env[k]));
}
const cardFrom = (entry) => ({ entry, fields: [], init: { values: {} }, values: {}, erase: [], errors: {}, result: null });

function step3Env({ list, pick }) {
  const log = [];
  const mine = { seq: 0, spaceId: "alpha", list: [], pick: new Set(pick), cards: [], offs: [], waits: [], s3failed: null, s3loading: false };
  const env = {
    wz: mine,
    deps: { api: async () => ({ modules: list }), toast: (m) => log.push(["toast", m]) },
    paint: () => log.push(["paint"]), go: (n) => log.push(["go", n]), afterRetry: () => {}, spaceGone: () => log.push(["spaceGone"]),
    prunePick, pickedInOrder, needsTrust, offRows, errOffRows, refusalView, t, cardFrom,
    mine,
  };
  const { loadStep3 } = buildFns(["loadStep3"], env);
  return { loadStep3, mine, log };
}

test("loadStep3: увімкнений колегою недовірений — без картки, рядком «чекає довіри»; решта карток лишається; крок не відкочується", async () => {
  const own = OWN("acme", ["publish"], { enabled: true });
  const css = M("css-tokens", ["tokens"], { enabled: true, status: "ok" });
  const e = step3Env({ list: [own, css], pick: ["acme", "css-tokens"] });
  await e.loadStep3();
  assert.deepEqual(e.mine.cards.map((c) => c.entry.id), ["css-tokens"]);
  assert.deepEqual(e.mine.waits.map((w) => [w.entry.id, w.result]), [["acme", null]]);
  assert.equal(e.mine.s3loading, false);
  assert.ok(!e.log.some((x) => x[0] === "go" || x[0] === "toast"));
});

test("loadStep3: вибраний невключений, що тепер потребує довіри (забрали між кроками), — тост cnRefUntrusted і назад на крок 2, без карток", async () => {
  const e = step3Env({ list: [OWN("acme", ["publish"])], pick: ["acme"] });
  await e.loadStep3();
  assert.deepEqual(e.log.filter((x) => x[0] !== "paint"), [["toast", t("cnRefUntrusted")], ["go", 2]]);
  assert.deepEqual(e.mine.cards, []);
  assert.deepEqual(e.mine.waits, []);
  assert.equal(e.mine.s3loading, false, "завантаження знято, інакше крок 3 висів би «Завантажую…»");
});

test("loadStep3: довірений свій модуль (зі знімком) — звичайна картка, не «чекає довіри»", async () => {
  const e = step3Env({ list: [OWN("acme", ["publish"], { trust: "changed", runs: true, status: "ok", enabled: true })], pick: ["acme"] });
  await e.loadStep3();
  assert.deepEqual(e.mine.cards.map((c) => c.entry.id), ["acme"]);
  assert.deepEqual(e.mine.waits, []);
});

test("runOp, untrusted: запиту нема (deps.post не кликано), відмова cnRefUntrusted лягає в рядок «чекає довіри», решта рядків не чіпається", async () => {
  const posts = [];
  const mine = { cards: [], offs: [], waits: [{ entry: OWN("acme", ["publish"]), result: null }, { entry: OWN("other", ["comments"]), result: null }] };
  let paints = 0;
  const { runOp } = buildFns(["runOp"], {
    deps: { post: async (...a) => { posts.push(a); return {}; } },
    paint: () => { paints += 1; }, refusalView, holdersByRole, modName: (e) => e.name,
    clearSecrets: () => {}, cardFrom, writePayload: () => ({}), formPatch: () => ({}), verdictText: () => ({}),
  });
  const res = await runOp(mine, { op: "untrusted", id: "acme", roles: ["publish"], stale: [] }, [], new Map(), { written: new Set(), replaced: new Set(), touched: new Set() });
  assert.deepEqual(posts, [], "відмова без запиту");
  assert.deepEqual(res, { kind: "refused", key: "cnRefUntrusted", detail: "" });
  assert.deepEqual(mine.waits[0].result, res);
  assert.equal(mine.waits[1].result, null);
  assert.equal(paints, 1);
});
