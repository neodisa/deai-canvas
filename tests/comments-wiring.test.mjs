/**
 * Проводка «Коментарі + команда» (0.27.0, Б2) у `app/app.js`, яку юніти моделей не бачать (`app.js` не імпортується в
 * Node). Чисті правила — `comment-news.js`, `comments-model.js`, `comments-view.js`; тут — що `app.js` ними користується
 * саме так, як задумано. Поведінку наживо (клік → картка, тост, число) покриває `tests/live/comments-panel.test.mjs`
 * і сценарії адресата (T12).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

function fn(name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `у app.js нема функції ${name}`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(open, i + 1); }
  }
  throw new Error(`не збалансовані дужки ${name}`);
}
/** Рядок дії `BAR_ACTIONS` за ключем. */
const act = (key) => {
  const m = new RegExp(`^  ${key}: .*$`, "m").exec(src);
  assert.ok(m, `у BAR_ACTIONS нема ${key}`);
  return m[0];
};

test("cmtfilter: лише значення з FILTERS, вибір памʼятається в dc-cmt-filter", () => {
  const a = act("cmtfilter");
  assert.match(a, /if \(!FILTERS\.includes\(f\)\) return;/, "довільне значення не мусить потрапити ні в стан, ні в localStorage");
  assert.match(a, /localStorage\.setItem\('dc-cmt-filter', f\)/);
  assert.ok(a.indexOf("FILTERS.includes") < a.indexOf("cmtFilter = f"));
  assert.match(src, /localStorage\.getItem\('dc-cmt-filter'\); return FILTERS\.includes\(v\) \? v : 'all'/, "збережене сміття читається як «all»");
});

test("cmtassign / cmtunassign ставлять і знімають доручення Claude через setMeta", () => {
  assert.match(act("cmtassign"), /setMeta\?\.\(id, \{ assignee: 'claude' \}\)/);
  assert.match(act("cmtunassign"), /setMeta\?\.\(id, \{ assignee: null \}\)/);
});

test("readTeamDown: лише непорожній РЯДОК із store.teamDown, решта — null (поведінка)", () => {
  const body = fn("readTeamDown");
  // eslint-disable-next-line no-new-func
  const readTeamDown = new Function(`function readTeamDown(L) ${body}\nreturn readTeamDown;`)();
  assert.equal(readTeamDown({ store: { teamDown: "module-error" } }), "module-error");
  for (const bad of [{ store: { teamDown: 1 } }, { store: { teamDown: true } }, { store: { teamDown: {} } }, { store: { teamDown: "" } },
    { store: { teamDown: null } }, { store: {} }, {}, null, undefined]) {
    assert.equal(readTeamDown(bad), null, JSON.stringify(bad));
  }
  const thrower = { get store() { throw new Error("чужий документ"); } };
  assert.equal(readTeamDown(thrower), null, "доступ до чужої рамки не мусить кидати");
});

test("«нові»: при відкритій панелі тост не показується; число острівця й дерева скидаються", () => {
  const body = fn("cmtNewsUpdate");
  const open = body.indexOf("if (cmtOpen) {");
  assert.ok(open > 0);
  const branch = body.slice(open, body.indexOf("\n  }\n", open));
  assert.match(branch, /return;/, "гілка відкритої панелі виходить до тосту");
  assert.doesNotMatch(branch, /newsToast/);
  assert.match(branch, /cmtNewsN = 0; cmtNewsPages = \{\};/);
  assert.ok(body.indexOf("newsToast(came)") > open + branch.length, "тост — лише після гілки відкритої панелі");
  assert.match(body, /const came = arrived\(cmtPrevIds, fresh\);/, "лише те, що зʼявилось у знімку ПІД ЧАС сесії");
  assert.match(body, /if \(!seen\) \{ seen = baseline\(team\);/, "перший погляд — усе наявне бачене");
});

test("відкриття панелі посуває маркер «бачив» ОДРАЗУ й складає розділ «нових»", () => {
  const body = fn("setCommentsOpen");
  assert.match(body, /fresh\.forEach\(\(c\) => cmtFresh\.add\(c\.id\)\);/);
  assert.match(body, /saveSeen\(key, markSeen\(seen, fresh\.map\(\(c\) => c\.id\)\)\)/);
  assert.match(body, /dropNotice\('cmt-news'\);/);
  assert.match(body, /if \(!on\) \{[^}]*cmtFresh\.clear\(\);/, "закриття чистить «нові» цього відкриття");
  assert.match(body, /cmtRefreshLocal\(\);/, "свіжість локальних піни на відкритті");
});

test("панель, острівець і дерево отримують дані «нових»; «Огляд» — комбінований із памʼяттю адресата", () => {
  assert.match(fn("paintComments"), /filter: cmtFilter, dual: !noTeamComments\(\), teamDown: cmtTeamDown,\s+fresh: cmtFresh/);
  assert.match(fn("paintIsland"), /commentsNew: cmtNewsN/);
  assert.match(src, /news: cmtNewsPages\[p\.id\] \|\| 0,/);
  assert.match(src, /defaultAudience: \(\) => \{ try \{ return localStorage\.getItem\(CMT_AUD_KEY\); \} catch \(e\) \{ return null; \} \},/);
  assert.match(src, /onAudiencePick: \(id\) => \{ try \{ localStorage\.setItem\(CMT_AUD_KEY, id\); \} catch \(e\) \{\} \},/);
});

test("знімок коментатора веде «нові»: ready, change і перемикання виду кличуть cmtNewsUpdate", () => {
  const ev = fn("onCommentsEvent");
  assert.equal((ev.match(/cmtNewsUpdate\(\)/g) || []).length, 2, "ready і change");
  assert.match(fn("cmtViewSwitch"), /cmtNewsUpdate\(\);\s+paintComments\(\);/);
  assert.match(fn("cmtViewSwitch"), /cmtFresh\.clear\(\); cmtPrevIds = null;/);
  assert.match(fn("dropFrameCmt"), /cmtSnap = null; cmtTeamDown = null;/);
});

test("усі читання й записи localStorage у проводці коментарів — у try/catch", () => {
  for (const name of ["loadSeen", "saveSeen", "readTeamDown", "cmtRefreshLocal"]) {
    const m = new RegExp(`(?:function ${name}\\(|const ${name} = )[^\\n]*`).exec(src);
    assert.ok(m, name);
    assert.match(m[0], /try \{/, name);
  }
  assert.match(src, /const myName = \(\) => \{ try \{ return localStorage\.getItem\('comment-layer:user'\)/);
});

test("ревʼю T9: маркер «бачив» не пишеться, поки командного нема (впало чи не заведене)", () => {
  const body = fn("cmtNewsUpdate");
  assert.match(body, /if \(!seen\) \{ seen = baseline\(team\); if \(!cmtTeamDown && !noTeamComments\(\)\) saveSeen\(key, seen\); \}/,
    "базова лінія зі знімка без команди порожня: усі колеги стали б «новими» при поверненні команди");
});

test("ревʼю T9: тост «нових» не переживає зміну задачі, виду чи рамки", () => {
  assert.match(fn("cmtNewsUpdate"), /cmtNewsTask = currentTaskId; cmtFresh\.clear\(\); cmtPrevIds = null; dropNotice\('cmt-news'\);/);
  assert.match(fn("cmtViewSwitch"), /cmtFresh\.clear\(\); cmtPrevIds = null; dropNotice\('cmt-news'\);/);
  assert.match(fn("dropFrameCmt"), /cmtFresh\.clear\(\); cmtPrevIds = null; dropNotice\('cmt-news'\);/);
});

test("ревʼю T9: оновлення на focus працює й без команди — refreshLocal, інакше refresh (поведінка)", () => {
  const line = /^const cmtRefreshLocal = .*$/m.exec(src);
  assert.ok(line, "нема cmtRefreshLocal");
  const make = (store) => new Function("cmtLayer", `${line[0]}\nreturn cmtRefreshLocal;`)(() => ({ store }));
  const calls = [];
  make({ refreshLocal() { calls.push(["local", this]); } , refresh() { calls.push(["full"]); } })();
  assert.deepEqual(calls.map((c) => c[0]), ["local"], "комбіноване: лише локальні");
  const plain = { refresh() { calls.push(["plain", this]); } };
  make(plain)();
  assert.equal(calls[1][0], "plain", "локальний адаптер без refreshLocal: кличе refresh");
  assert.equal(calls[1][1], plain, "this = сховище");
  assert.doesNotThrow(() => make(undefined)());
});

/* --- Числа на вкладках (Б2, Task 10) --- */
function pollHarness({ tabs, current = "T0", space = "s1", visible = true, replies = {}, seenStore = {}, clock = { t: 1e6 }, onApi } ) {
  const calls = []; const saved = [];
  const spaceBox = { id: space };
  const env = {
    Date: { now: () => clock.t },
    document: { visibilityState: visible ? "visible" : "hidden" },
    tabs, currentTaskId: current,
    spaceNow: () => ({ id: spaceBox.id }),
    api: async (p) => { calls.push(p); if (onApi) onApi(spaceBox); const r = replies[decodeURIComponent(p.split("task=")[1])]; if (r instanceof Error) throw r; return r; },
    seenKey: (s, t) => `${s}:${t}`,
    loadSeen: (k) => seenStore[k] ?? null,
    saveSeen: (k, v) => { saved.push(k); seenStore[k] = v; },
    baseline: (items) => new Set(items.map((c) => c.id)),
    countNew: (items, seen) => items.filter((c) => !seen.has(c.id)).length,
    myName: () => "me",
    paintTabs: () => {},
    tabNews: {},
  };
  const body = fn("pollTabNews");
  const names = Object.keys(env);
  // eslint-disable-next-line no-new-func
  const sbody = fn("saveTabs");
  const f = new Function(...names, "TABS_KEY", "writeTabs", "localStorage", "let newsBusy = false, newsAgain = false, newsSetKey = null, newsLastAt = 0;\n"
    + `async function pollTabNews(force = false) ${body}\nfunction saveTabs() ${sbody}\n`
    + "return { run: pollTabNews, save: saveTabs, news: () => tabNews };")(...names.map((n) => env[n]), "k", () => "", { setItem() {} });
  return { f, calls, saved, seenStore, clock, spaceBox };
}
const items3 = [{ id: "a" }, { id: "b" }];
test("pollTabNews: активна вкладка і вкладки інших просторів не опитуються", async () => {
  const h = pollHarness({ tabs: [{ id: "T0", space: "s1" }, { id: "T1", space: "s1" }, { id: "T2", space: "s2" }, { id: "T3" }],
    replies: { T1: { supported: true, items: items3 } }, seenStore: { "s1:T1": new Set(["a"]) } });
  await h.f.run();
  assert.deepEqual(h.calls, ["/api/comment-news?task=T1"]);
  assert.deepEqual(h.f.news(), { T1: 1 });
});
test("pollTabNews: рахує нові інших вкладок, пише маркер лише з supported:true; збій/unsupported — ні числа, ні маркера", async () => {
  const h = pollHarness({ tabs: [{ id: "T1", space: "s1" }, { id: "T2", space: "s1" }, { id: "T3", space: "s1" }, { id: "T4", space: "s1" }],
    replies: { T1: { supported: true, items: items3 }, T2: { supported: false, items: [] }, T3: new Error("down"), T4: { supported: true, items: "x" } },
    seenStore: { "s1:T1": new Set(["a"]) } });
  await h.f.run();
  assert.deepEqual(h.f.news(), { T1: 1 });
  assert.deepEqual(h.saved, [], "маркер уже був у T1; решта не мусить його отримати");
  const h2 = pollHarness({ tabs: [{ id: "T1", space: "s1" }, { id: "T2", space: "s1" }],
    replies: { T1: { supported: true, items: items3 }, T2: { supported: false, items: [] } } });
  await h2.f.run();
  assert.deepEqual(h2.saved, ["s1:T1"], "перша відповідь supported:true — основа без числа; unsupported — без запису");
  assert.deepEqual(h2.f.news(), {});
});
test("pollTabNews: supported:true з error (команда впала) — ні числа, ні маркера (інакше після одужання усе «нове»)", async () => {
  const h = pollHarness({ tabs: [{ id: "T1", space: "s1" }], replies: { T1: { supported: true, items: [], error: "x" } } });
  await h.f.run();
  assert.deepEqual(h.f.news(), {});
  assert.deepEqual(h.saved, []);
});
test("опит: незмінний склад вкладок — один опит; зміна складу — опит і в межах 30 с", async () => {
  const tabs = [{ id: "T1", space: "s1" }];
  const h = pollHarness({ tabs, replies: { T1: { supported: true, items: items3 } }, seenStore: { "s1:T1": new Set(["a"]) } });
  h.f.save(); h.f.save(); h.f.save();
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(h.calls.length, 1, "три saveTabs без зміни складу — один запит на вкладку");
  tabs.push({ id: "T2", space: "s1" });
  h.f.save();
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(h.calls.length, 3, "новий склад — новий опит одразу, хоч і 30 с не минуло (T1 + T1,T2)");
});
test("опит: без force — не частіше разу на 30 с", async () => {
  const h = pollHarness({ tabs: [{ id: "T1", space: "s1" }], replies: { T1: { supported: true, items: items3 } }, seenStore: { "s1:T1": new Set(["a"]) } });
  await h.f.run();
  h.clock.t += 29000; await h.f.run();
  assert.equal(h.calls.length, 1, "focus/таймер у межах 30 с — без запитів");
  h.clock.t += 2000; await h.f.run();
  assert.equal(h.calls.length, 2, "після 30 с — опитує");
  await h.f.run(true);
  assert.equal(h.calls.length, 3, "force ігнорує поріг");
});
test("опит: простір перемкнули посеред опиту — старі числа не малюються", async () => {
  const h = pollHarness({ tabs: [{ id: "T1", space: "s1" }], replies: { T1: { supported: true, items: items3 } }, seenStore: { "s1:T1": new Set(["a"]) },
    onApi: (box) => { box.id = "s2"; } });
  await h.f.run();
  assert.deepEqual(h.f.news(), {}, "sp зняли на старті, на кінці простір інший — присвоєння немає");
});
test("pollTabNews: приховане вікно — жодного запиту", async () => {
  const h = pollHarness({ tabs: [{ id: "T1", space: "s1" }], visible: false, replies: { T1: { supported: true, items: items3 } } });
  await h.f.run();
  assert.deepEqual(h.calls, []);
});
test("проводка: paintTabs передає news і гасить число активної; saveTabs і focus опитують", () => {
  assert.match(fn("paintTabs"), /news: newsHere/);
  assert.match(fn("paintTabs"), /delete tabNews\[currentTaskId\]/);
  assert.match(fn("saveTabs"), /pollTabNews\(true\)/);
  assert.match(fn("paintTabs"), /pollTabNews\(true\)/, "зміна активної задачі/простору — примусовий опит");
  assert.match(fn("paintTabs"), /\(x\.space \?\? null\) === spNow/, "числа лише вкладок поточного простору");
  assert.match(src, /window\.addEventListener\('focus', \(\) => \{ pollTabNews\(\); \}\);/);
  assert.match(src, /setInterval\(pollTabNews, NEWS_EVERY_MS\)/);
});
