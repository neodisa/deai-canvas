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

test("крок 2: недовірений — радіо вимкнене, пігулка «свій», «Довірити» ПОЗА label; увімкнений — ще й причина", () => {
  const h = wizardHTML(V2([OWN("acme", ["publish"], { enabled: true })], new Set(["acme"])));
  assert.match(h, /<div class="wz-opt-row"><label class="wz-opt" for="wz-o-0-0"><input type="radio" id="wz-o-0-0" name="wz-r-0" value="acme" data-wz-pick data-role="publish" checked disabled>/);
  assert.match(h, /<span class="cn-tag cn-tag--own" title="~\/w\/modules\/acme">свій<\/span>/);
  assert.match(h, /<\/label><button type="button" class="ctl ctl--out" data-wz="trust" data-id="acme" aria-describedby="wz-on-0-0">.*Довірити<\/button><\/div>/s);
  assert.match(h, /class="wz-opt-why".*йому не довірено/s);
  const off = wizardHTML(V2([OWN("acme", ["publish"])], new Set()));
  assert.match(off, /value="acme" data-wz-pick data-role="publish" disabled>/);
  assert.doesNotMatch(off, /wz-opt-why/, "невключений недовірений — без причини: просто чекає довіри");
});

test("крок 2: «Довірити» не всередині label — клік по кнопці в label клікнув би й радіо", () => {
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
  assert.match(h, /<b id="wz-on-0-0">&lt;img src=x onerror=1&gt;<\/b>/);
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

test("крок 2: id модуля в `data-id` кнопки «Довірити» екранується — не виходить з атрибута", () => {
  const h = wizardHTML(V2([OWN('a"><b', ["publish"])], new Set()));
  assert.ok(h.includes('data-wz="trust" data-id="a&quot;&gt;&lt;b"'), "id екрановано");
  assert.ok(!h.includes('data-id="a"><b'), "розмітку не прорвано");
});

test("крок 2: «Довірити» привʼязана до НАЗВИ свого модуля (`aria-describedby`) — дві кнопки читач екрана озвучує по-різному", () => {
  const list = [OWN("acme", ["publish"], { name: "Acme Deploy" }), OWN("beta", ["comments"], { name: "Beta Notes" })];
  const h = wizardHTML(V2(list, new Set()));
  const buttons = [...h.matchAll(/<button [^>]*data-wz="trust" data-id="([^"]+)"[^>]*>/g)];
  assert.equal(buttons.length, 2);
  const seen = new Set();
  for (const [tag, id] of buttons) {
    const ref = /aria-describedby="([^"]+)"/.exec(tag)?.[1];
    assert.ok(ref, `у кнопки ${id} нема aria-describedby`);
    assert.ok(!seen.has(ref), "id описів різні");
    seen.add(ref);
    const named = new RegExp(`<[a-z]+ id="${ref}">([^<]*)</[a-z]+>`).exec(h)?.[1];
    assert.equal(named, id === "acme" ? "Acme Deploy" : "Beta Notes", `опис кнопки ${id} — назва її модуля`);
    assert.equal(h.split(`id="${ref}"`).length - 1, 1, "id у розмітці один");
  }
});

test("крок 2: id назви є лише там, де є кнопка — вбудований і refused без знімка (кнопки нема) без висячого id", () => {
  const h = wizardHTML(V2([M("vercel-publish", ["publish"]),
    OWN("acme", ["comments"], { trust: "refused", status: "error", trust_error: "too-big", error: "too-big: 6 MiB" })], new Set()));
  assert.doesNotMatch(h, /wz-on-/);
});

test("крок 2 зайнятий: «Довірити» теж вимкнена", () => {
  assert.match(wizardHTML(V2([OWN("acme", ["publish"])], new Set(), { busy: "save" })), /data-wz="trust" data-id="acme" aria-describedby="wz-on-0-0" disabled>/);
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

/** `trustFrom` з підставним станом майстра; `log` пише виклики в порядку. `box` — єдиний вузол, що скролиться (як `#tasks-home`):
    підставний `loadStep2` обнуляє його `scrollTop` — так робить браузер, коли «Завантажую…» коротша за список. */
function trustEnv({ wz, lost = true, radio = null, open = async () => true, onLoad = null, scroll = 0, noNode = false } = {}) {
  const log = [];
  const focusOf = (what) => ({ focus: (o) => log.push(["focus", what, o]) });
  const state = { wz };
  const found = { radio: radio ? focusOf("radio") : null, button: focusOf("button") };
  const box = { scrollTop: scroll, querySelector: (sel) => { log.push(["query", sel]); return sel.startsWith("input[") ? found.radio : (sel.startsWith("[data-wz=") ? found.button : null); } };
  const deps = {
    openTrust: async (e, spaceId) => { log.push(["openTrust", e.id, spaceId]); return open(); },
    node: () => (noNode ? null : box),
    toast: (m) => log.push(["toast", m]),
  };
  let api;
  const loadStep2 = async () => { log.push(["loadStep2"]); box.scrollTop = 0; await onLoad?.(api); };
  const focusLost = () => lost;
  const CSS = { escape: (s) => `<${s}>` };
  const code = `let wz = state.wz;\n${fnSrc("trustFrom")}\nreturn { trustFrom, drop: () => { wz = null; }, swap: (v) => { wz = v; } };`;
  api = new Function("state", "deps", "loadStep2", "focusLost", "CSS", "t", code)(state, deps, loadStep2, focusLost, CSS, t);
  return { ...api, log, deps, box };
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

test("trustFrom: скрол сторінки повертається після перечитування — «Завантажую…» коротша за список, браузер притиснув його до нуля", async () => {
  const env = trustEnv({ wz: WZ(), scroll: 600 });
  await env.trustFrom("acme");
  assert.equal(env.box.scrollTop, 600);
  const declined = trustEnv({ wz: WZ(), open: async () => false, scroll: 420 });
  await declined.trustFrom("acme");
  assert.equal(declined.box.scrollTop, 420, "довіри не дали — список усе одно перемальовано, скрол усе одно повертаємо");
});

test("trustFrom: майстер закрито, поки йшло перечитування, — скрол не чіпаємо (вузол уже не наш)", async () => {
  const env = trustEnv({ wz: WZ(), scroll: 600, onLoad: (api) => api.drop() });
  await env.trustFrom("acme");
  assert.equal(env.box.scrollTop, 0);
});

test("trustFrom: крок змінився, поки йшло перечитування, — скрол кроку 2 на новому кроці не відновлюємо", async () => {
  const wz = WZ();
  const env = trustEnv({ wz, scroll: 600, onLoad: () => { wz.step = 3; } });
  await env.trustFrom("acme");
  assert.equal(env.box.scrollTop, 0);
});

test("trustFrom: вузла сторінки нема — без падіння, список усе одно перечитано", async () => {
  const env = trustEnv({ wz: WZ(), scroll: 600, noNode: true });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.map((x) => x[0]), ["openTrust", "loadStep2"]);
});

test("trustFrom: подвійний клік — діалог відкривається один раз; після завершення наступний клік знову працює", async () => {
  const env = trustEnv({ wz: WZ() });
  const first = env.trustFrom("acme");
  const second = env.trustFrom("acme");
  await Promise.all([first, second]);
  assert.equal(env.log.filter((x) => x[0] === "openTrust").length, 1, "другий клік, поки діалог уже відкривався, ігнорується");
  assert.equal(env.log.filter((x) => x[0] === "loadStep2").length, 1, "і зайвого перечитування списку нема");
  await env.trustFrom("acme");
  assert.equal(env.log.filter((x) => x[0] === "openTrust").length, 2, "прапорець знято: людина може відкрити діалог знову");
});

test("trustFrom: прапорець «зайнято» знімається на КОЖНОМУ виході, ранньому теж — «Довірити» не мертвіє", async () => {
  const again = async (what, env, wz) => {
    await env.trustFrom("acme");
    wz.step = 2;
    await env.trustFrom("acme");
    assert.equal(env.log.filter((x) => x[0] === "openTrust").length, 2, `${what}: другий клік не спрацював — прапорець завис`);
  };
  const a = WZ();
  await again("фокус не втрачено", trustEnv({ wz: a, lost: false }), a);
  const b = WZ();
  await again("крок змінився, поки висів діалог", trustEnv({ wz: b, open: async () => { b.step = 3; return true; } }), b);
  const c = WZ();
  await again("крок змінився, поки йшло перечитування", trustEnv({ wz: c, onLoad: () => { c.step = 3; } }), c);
});

test("trustFrom: прапорець «зайнято» висить на обʼєкті майстра — майстер, відкритий наново поки діалог висить, не успадковує його", async () => {
  const release = [];
  const env = trustEnv({ wz: WZ(), open: () => new Promise((r) => { release.push(r); }) });
  const first = env.trustFrom("acme");
  env.swap(WZ());
  const second = env.trustFrom("acme");
  assert.equal(env.log.filter((x) => x[0] === "openTrust").length, 2, "новий майстер — свій прапорець");
  release.forEach((r) => r(true));
  await Promise.all([first, second]);
});

test("trustFrom: openTrust відмовив — тост із причиною, список усе одно перечитується, без необроблених відмов", async () => {
  const env = trustEnv({ wz: WZ(), open: async () => { throw new Error("boom"); }, scroll: 300 });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.filter((x) => x[0] === "toast"), [["toast", t("errFailed", "boom")]]);
  assert.match(t("errFailed", "boom"), /boom/);
  assert.deepEqual(env.log.map((x) => x[0]).filter((k) => k === "loadStep2"), ["loadStep2"]);
  assert.equal(env.box.scrollTop, 300);
  const again = trustEnv({ wz: WZ(), open: async () => { throw new Error("boom"); } });
  await again.trustFrom("acme");
  await again.trustFrom("acme");
  assert.equal(again.log.filter((x) => x[0] === "openTrust").length, 2, "після збою прапорець знято");
});

test("trustFrom: openTrust відмовив, а майстер тим часом закрито, — тост є, список не чіпаємо", async () => {
  const env = trustEnv({ wz: WZ(), open: async () => { env.drop(); throw new Error("boom"); } });
  await env.trustFrom("acme");
  assert.deepEqual(env.log.map((x) => x[0]), ["openTrust", "toast"]);
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
