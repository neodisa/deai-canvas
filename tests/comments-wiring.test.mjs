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
  assert.match(act("cmtfilter"), /cmtfilter: \(f\) => setCmtFilter\(f\),/, "дія ділить шлях із тостом новин");
  const a = fn("setCmtFilter");
  assert.match(a, /if \(!FILTERS\.includes\(f\)\) return;/, "довільне значення не мусить потрапити ні в стан, ні в localStorage");
  assert.match(a, /localStorage\.setItem\('dc-cmt-filter', f\)/);
  assert.ok(a.indexOf("FILTERS.includes") < a.indexOf("cmtFilter = f"));
  assert.match(src, /localStorage\.getItem\('dc-cmt-filter'\); return FILTERS\.includes\(v\) \? v : 'local'/, "немає чи сміття — вкладка «Для AI» (рішення власника 16.11.2026)");
});

test("тост новин: «Показати» з вкладки «Для AI» веде на «Команду» через спільний шлях; з «Команда»/«Усі» вкладку не чіпає", () => {
  const body = fn("newsToast");
  assert.match(body, /if \(cmtFilter === 'local'\) setCmtFilter\('project'\);/);
  assert.ok(body.indexOf("setCmtFilter('project')") < body.indexOf("setCommentsOpen(true)"), "вкладку міняємо до відкриття панелі");
  /* поведінка: виконуємо `run` із підставленими залежностями */
  const run = (filter) => {
    const calls = [];
    const notice = (id, text, actions) => { calls.push(["notice"]); notice.run = actions[0].run; };
    const mk = new Function("notice", "t", "dropNotice", "setCommentsOpen", "paintComments", "cmtLayer", "setCmtFilter", "state",
      `let cmtFilter = state.f; let cmtSel = null; function newsToast(came) ${body}\nnewsToast([{ id: "x", author: "a" }]); return () => { state.f = cmtFilter; };`);
    const state = { f: filter };
    mk(notice, (k) => k, () => {}, () => calls.push(["open"]), () => {}, () => null, (f) => calls.push(["filter", f]), state);
    notice.run();
    return calls.filter((c) => c[0] !== "notice");
  };
  assert.deepEqual(run("local"), [["filter", "project"], ["open"]]);
  assert.deepEqual(run("all"), [["open"]]);
  assert.deepEqual(run("project"), [["open"]]);
});

test("«Огляд»: аудиторія «AI» має підказку під чипом, як і «Команді»", () => {
  assert.match(src, /\{ id: 'local', label: t\('audChipLocal'\), icon: 'bot', color: LOCAL_PIN_COLOR, private: true \}/);
  assert.match(src, /\{ id: 'project', label: t\('audChipTeam'\), icon: 'team', note: t\('audChipTeamNote'\) \}/);
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
  assert.match(body, /const seen = cmtSeenSet\(news\);/, "перший погляд — усе наявне бачене (база в cmtSeenSet)");
  assert.match(fn("cmtSeenSet"), /main = baseline\(news\);/);
});

test("відкриття панелі посуває маркер «бачив» ОДРАЗУ й складає розділ «нових»", () => {
  const body = fn("setCommentsOpen");
  assert.match(body, /fresh\.forEach\(\(c\) => cmtFresh\.add\(c\.id\)\);/);
  assert.match(body, /if \(fresh\.length\) cmtMarkSeen\(fresh\.map\(\(c\) => c\.id\)\);/);
  assert.match(body, /const seen = cmtSnap && Array\.isArray\(cmtSnap\.comments\) \? cmtSeenSet\(news\) : new Set\(\);/, "та сама база, що в cmtNewsUpdate: без маркера старе не стає «Новим»");
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
  assert.match(fn("cmtSeenSet"), /if \(!cmtTeamDown && !noTeamComments\(\)\) \{ main = baseline\(news\); saveSeen\(key, main\); \}/,
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
  const make = (store, homeOpen = false) => new Function("cmtLayer", "homeOpen", `${line[0]}\nreturn cmtRefreshLocal;`)(() => ({ store }), homeOpen);
  const calls = [];
  make({ refreshLocal() { calls.push(["local", this]); } , refresh() { calls.push(["full"]); } })();
  assert.deepEqual(calls.map((c) => c[0]), ["local"], "комбіноване: лише локальні");
  const plain = { refresh() { calls.push(["plain", this]); } };
  make(plain)();
  assert.equal(calls[1][0], "plain", "локальний адаптер без refreshLocal: кличе refresh");
  assert.equal(calls[1][1], plain, "this = сховище");
  assert.doesNotThrow(() => make(undefined)());
  // Під екраном «Задачі» макет схований — тиша (вихід з екрана однаково перезавантажує рамку).
  make({ refreshLocal() { calls.push(["home"]); }, refresh() { calls.push(["home-full"]); } }, true)();
  assert.equal(calls.length, 2, "під «Задачами» focus не кличе сховище");
});

/* --- Числа на вкладках (Б2, Task 10) --- */
function pollHarness({ tabs, current = "T0", space = "s1", visible = true, replies = {}, seenStore = {}, clock = { t: 1e6 }, onApi } ) {
  const calls = []; const saved = [];
  /* Фальшивий годинник таймерів: tick(ms) проганяє заплановане (debounce примусових опитів). */
  const timers = new Map(); let tid = 0;
  const fake = { setTimeout: (cb, ms) => { timers.set(++tid, { cb, at: clock.t + ms }); return tid; }, clearTimeout: (id) => { timers.delete(id); } };
  const tick = async (ms) => {
    clock.t += ms;
    for (const [id, t] of [...timers]) if (t.at <= clock.t) { timers.delete(id); t.cb(); }
    await new Promise((r) => setTimeout(r, 5));
  };
  const spaceBox = { id: space };
  const env = {
    Date: { now: () => clock.t },
    setTimeout: fake.setTimeout, clearTimeout: fake.clearTimeout,
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
  const f = new Function(...names, "TABS_KEY", "writeTabs", "localStorage", "let newsBusy = false, newsAgain = false, newsSetKey = null, newsLastAt = 0, newsSoonTimer = null;\nconst NEWS_SOON_MS = 1500;\n"
    + `async function pollTabNews(force = false) ${body}\nfunction saveTabs() ${sbody}\nfunction pollTabNewsSoon() ${fn("pollTabNewsSoon")}\n`
    + "return { run: pollTabNews, save: saveTabs, soon: pollTabNewsSoon, news: () => tabNews };")(...names.map((n) => env[n]), "k", () => "", { setItem() {} });
  return { f, calls, saved, seenStore, clock, spaceBox, tick };
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
  await h.tick(1600);
  assert.equal(h.calls.length, 1, "три saveTabs без зміни складу — один запит на вкладку");
  tabs.push({ id: "T2", space: "s1" });
  h.f.save();
  await h.tick(1600);
  assert.equal(h.calls.length, 3, "новий склад — новий опит одразу, хоч і 30 с не минуло (T1 + T1,T2)");
});
test("опит: 5 примусових за секунду — один раунд після вікна, по запиту на іншу вкладку", async () => {
  const h = pollHarness({ tabs: [{ id: "T0", space: "s1" }, { id: "T1", space: "s1" }, { id: "T2", space: "s1" }],
    replies: { T1: { supported: true, items: items3 }, T2: { supported: true, items: items3 } }, seenStore: { "s1:T1": new Set(["a"]), "s1:T2": new Set(["a"]) } });
  for (let i = 0; i < 5; i++) { h.f.soon(); await h.tick(200); }
  assert.equal(h.calls.length, 0, "у межах вікна (хвостовий debounce) запитів нема");
  await h.tick(1600);
  assert.equal(h.calls.length, 2, "один раунд: по одному запиту на T1 і T2");
  await h.tick(5000);
  assert.equal(h.calls.length, 2, "більше нічого не викликано");
});
test("опит: примусовий під час зайнятого раунду — один додатковий після нього, а не купа", async () => {
  const h = pollHarness({ tabs: [{ id: "T0", space: "s1" }, { id: "T1", space: "s1" }],
    replies: { T1: { supported: true, items: items3 } }, seenStore: { "s1:T1": new Set(["a"]) } });
  const first = h.f.run(true);           // раунд ще йде (await api)
  h.f.soon(); h.f.soon(); h.f.soon();
  await first;
  await h.tick(1600);
  assert.equal(h.calls.length, 2, "перший раунд + один повтор від злитих примусових");
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
  assert.match(fn("saveTabs"), /pollTabNewsSoon\(\)/);
  assert.match(fn("paintTabs"), /pollTabNewsSoon\(\)/, "зміна активної задачі/простору — примусовий опит");
  assert.match(fn("paintTabs"), /\(x\.space \?\? null\) === spNow/, "числа лише вкладок поточного простору");
  assert.match(src, /window\.addEventListener\('focus', \(\) => \{ pollTabNews\(\); \}\);/);
  assert.match(src, /setInterval\(pollTabNews, NEWS_EVERY_MS\)/);
});

test("кошик у картці (етап В): cmtdel питає, cmtdelyes видаляє з confirmed, cmtdelno знімає; Esc і клік повз знімають питання", () => {
  assert.match(act("cmtdel"), /cmtDelAsk = id; paintComments\(\);/);
  assert.equal(/removeComment/.test(act("cmtdel")), false, "кошик сам нічого не видаляє");
  assert.match(act("cmtdelyes"), /if \(cmtDelAsk !== id\) return;/);
  assert.match(act("cmtdelyes"), /removeComment\(id, \{ confirmed: true \}\)/);
  assert.match(act("cmtdelno"), /cmtdelno: \(\) => closeDelAsk\(true\),/);
  assert.match(src, /function closeDelAsk\(refocus\) \{\s*const id = cmtDelAsk;\s*cmtDelAsk = null;\s*paintComments\(\);\s*if \(refocus && id\) cmtEl\.querySelector\(`\[data-act="cmtdel"\]\[data-val="\$\{CSS\.escape\(id\)\}"\]`\)\?\.focus\(\);/, "після «Скасувати»/Esc фокус — на кошику тієї картки");
  assert.match(src, /window\.addEventListener\('blur', \(\) => setTimeout\(\(\) => \{\s*if \(cmtDelAsk && document\.activeElement\?\.tagName === 'IFRAME'\) \{ cmtDelAsk = null; paintComments\(\); \}/, "клік у макет знімає питання");
  assert.match(src, /act\.closest\('\.cmt-acts--cfm'\)/, "перемальовка панелі повертає фокус на кнопку питання");
  assert.match(src, /if \(cmtFree && cmtOpen && cmtDelAsk && ev\.key === 'Escape'\) \{ ev\.preventDefault\(\); closeDelAsk\(true\); return; \}/);
  assert.match(src, /if \(cmtDelAsk && !ev\.target\.closest\?\.\('\.cmt-acts--cfm'\)\) \{ cmtDelAsk = null; paintComments\(\); \}/);
  assert.match(src, /editingId: cmtEditing, delAsk: cmtDelAsk,/);
});

/* --- Відповіді в картці (0.34, Task 7b) --- */
test("відповіді: усі 10 дій у BAR_ACTIONS (кожна в окремому рядку), виклики шару — у try", () => {
  for (const k of ["cmtthread", "cmtreply", "cmtreplysend", "cmtreplycancel", "cmtredit", "cmtreditsave", "cmtreditcancel", "cmtrdel", "cmtrdelyes", "cmtrdelno"]) act(k);
  assert.match(act("cmtreplysend"), /cmtreplysend: \(id\) => \{$/);
  for (const [k, call] of [["cmtreplysend", "reply\\("], ["cmtreditsave", "editReply\\("], ["cmtrdelyes", "removeReply\\("]]) {
    const m = new RegExp(`^  ${k}: [\\s\\S]*?\\n  \\},$`, "m").exec(src);
    assert.ok(m, k);
    assert.match(m[0], new RegExp(`try \\{[^\\n]*${call}[^\\n]*\\} catch \\(e\\) \\{\\}`), `${k}: виклик шару в try`);
  }
});

test("readRepliesDown: лише непорожній РЯДОК із store.repliesDown, решта й чужий документ — null; усередині try", () => {
  const body = fn("readRepliesDown");
  assert.match(body, /try \{/);
  const readRepliesDown = new Function(`function readRepliesDown(L) ${body}\nreturn readRepliesDown;`)();
  assert.equal(readRepliesDown({ store: { repliesDown: "no-replies-schema" } }), "no-replies-schema");
  for (const bad of [{ store: { repliesDown: 1 } }, { store: { repliesDown: "" } }, { store: {} }, null, undefined]) assert.equal(readRepliesDown(bad), null);
  assert.equal(readRepliesDown({ get store() { throw new Error("чужий документ"); } }), null);
});

/** repliesOff + права + смуга з підставленими залежностями. */
function repliesKit({ team = true, down = null, supports = true, teamDown = null, me = "Я", snap, ready = true }) {
  const L = { store: { repliesDown: down, supportsReplies: (a) => (a === "local" ? true : supports) } };
  const lines = ["parentOfReply", "repliesWritable", "isOwnReply", "canDeleteReply"].map((n) => new RegExp(`^const ${n} = .*$`, "m").exec(src)[0]).join("\n");
  const whole = (n) => { const i = src.indexOf(`function ${n}(`); return src.slice(i, src.indexOf("{", i)) + fn(n); };
  const code = `function storeIsReady() { return ready; }\n${["readRepliesDown", "readSupportsReplies", "repliesOff", "repliesBanner"].map(whole).join("\n")}\n${lines}\nreturn { repliesOff, repliesBanner: () => repliesBanner(cmtLayer()), isOwnReply, canDeleteReply };`;
  return new Function("t", "audOf", "cmtLayer", "noTeamComments", "cmtTeamDown", "cmtSnap", "myName", "ready", code)(
    (k) => k, (c) => (c && c._aud === "project" ? "project" : "local"), () => L, () => !team, teamDown, snap, () => me, ready);
}
const cm = (id, aud, replies) => ({ id, _aud: aud, status: "open", replies });
const R = { mine: { id: "r1", author: "Я", text: "x" }, other: { id: "r2", author: "Хтось", text: "y" }, agent: { id: "r3", author: "Я", agent: true, text: "z" } };

test("repliesOff: локальний — null; командний — непорожній рядок при repliesDown чи supportsReplies('project') === false; інакше null", () => {
  const snap = { comments: [] };
  const loc = cm("l", "local", []), tm = cm("t", "project", []);
  assert.equal(repliesKit({ down: "no-replies-schema", snap }).repliesOff(loc), null, "локальний завжди можна");
  assert.equal(repliesKit({ snap }).repliesOff(tm), null);
  assert.equal(repliesKit({ down: "no-replies-schema", snap }).repliesOff(tm), "cmtRepliesOff");
  assert.equal(repliesKit({ supports: false, snap }).repliesOff(tm), "cmtRepliesOff", "модуль без відповідей: адаптер мовчки відкине — ховаємо поле");
});

test("смуга відповідей: no-replies-schema / інша причина / модуль без підтримки; нема команди чи вона впала — без смуги", () => {
  const snap = { comments: [] };
  assert.equal(repliesKit({ down: "no-replies-schema", snap }).repliesBanner(), "cmtRepliesNoSchema");
  assert.equal(repliesKit({ down: "rls denied", snap }).repliesBanner(), "rls denied");
  assert.equal(repliesKit({ supports: false, snap }).repliesBanner(), "cmtRepliesNoModule");
  assert.equal(repliesKit({ snap }).repliesBanner(), null);
  assert.equal(repliesKit({ team: false, supports: false, snap }).repliesBanner(), null, "команди нема");
  assert.equal(repliesKit({ teamDown: "x", supports: false, snap }).repliesBanner(), null, "команда впала — є смуга teamDown");
});

test("права на відповіді: змінити — лише свою людську; видалити — будь-яку; при repliesOff батька обидві кнопки зникають", () => {
  const tm = cm("t", "project", [R.mine, R.other, R.agent]), loc = cm("l", "local", [{ ...R.mine, id: "r9" }]);
  const snap = { comments: [tm, loc] };
  const ok = repliesKit({ snap });
  assert.deepEqual([R.mine, R.other, R.agent].map(ok.isOwnReply), [true, false, false], "змінити — лише свою, не агента");
  assert.deepEqual([R.mine, R.other, R.agent].map(ok.canDeleteReply), [true, true, true]);
  const off = repliesKit({ down: "no-replies-schema", snap });
  assert.deepEqual([R.mine, R.other, R.agent].map(off.isOwnReply), [false, false, false], "чужа відповідь під вимкненими відповідями не редагується");
  assert.deepEqual([R.mine, R.other, R.agent].map(off.canDeleteReply), [false, false, false], "видалення б «вдалось» і не дійшло до сервера");
  assert.equal(off.isOwnReply({ ...R.mine, id: "r9" }), true, "локальний коментар лишається редагованим");
  assert.equal(off.canDeleteReply({ id: "r9" }), true);
  assert.equal(repliesKit({ me: "", snap }).isOwnReply(R.mine), false, "без імені «своїх» нема");
});

test("новини з відповідями: cmtNewsUpdate і setCommentsOpen беруть newsItems, не teamOf; «бачив» ведуть і відповіді (вони в newsItems)", () => {
  assert.match(fn("cmtNewsUpdate"), /const news = newsItems\(all\);/);
  assert.match(fn("setCommentsOpen"), /newsItems\(cmtSnap\?\.comments\)/);
  assert.doesNotMatch(src, /teamOf\(/);
  assert.match(fn("cmtNewsUpdate"), /cmtPrevIds = snapIds\(all\);/, "id відповідей у попередньому знімку: стара відповідь не «зʼявляється» щоразу");
  assert.match(fn("newsToast"), /replyNewsToast\(came\[came\.length - 1\]\)/);
  assert.match(fn("replyNewsToast"), /t\('cmtReplyToast', r\.author \|\| '—', par \? par\.n : '—'\)/);
  assert.match(fn("replyNewsToast"), /cmtThreads\.add\(r\.parent\)/);
  assert.match(fn("replyNewsToast"), /cmtQuery = '';/, "пошук міг сховати батька (live 31)");
  assert.match(fn("replyNewsToast"), /par && par\.scope === 'earlier'\) cmtExpanded\.earlier = true;/, "батько в «З попередніх ітерацій» (у «Нове» картка видима й так — це запас)");
  assert.match(src, /cmtEl\.addEventListener\('focusin'[\s\S]*?classList\.add\('cmt-rbox--on'\);[\s\S]*?\}\);/, "focusin ставить клас без перемальовки");
  assert.doesNotMatch(/cmtEl\.addEventListener\('focusin'[\s\S]*?\n\}\);/.exec(src)[0], /paintComments/, "перемальовка у focusin губить каретку");
  const fi = /cmtEl\.addEventListener\('focusin'[\s\S]*?\n\}\);/.exec(src)[0];
  assert.match(fi, /if \(cmtRestoringFocus\) return;/, "фокус, повернутий перемальовкою, не мусить знову розгортати поле (Esc)");
  assert.match(src, /cmtRestoringFocus = true;[^\n]*\n\s*try \{ el\?\.focus\(\); \} finally \{ cmtRestoringFocus = false; \}/, "прапор довкола focus() у paintComments");
  assert.match(fi, /for \(const b of cmtEl\.querySelectorAll\('\.cmt-rbox--on'\)\) if \(b !== box\) b\.classList\.remove\('cmt-rbox--on'\);/, "розгорнутий рядок — один");
});

test("«не підтримує відповідей» — невідомо, поки store.ready не виконано: ні смуги, ні прихованого поля (поведінка справжніх storeIsReady/readSupportsReplies)", async () => {
  const code = `const cmtStoreReady = new WeakMap(); let paints = 0; const paintComments = () => { paints += 1; };
    function storeIsReady${/function storeIsReady(\([^)]*\))/.exec(src)[1]} ${fn("storeIsReady")}
    function readSupportsReplies${/function readSupportsReplies(\([^)]*\))/.exec(src)[1]} ${fn("readSupportsReplies")}
    return { read: readSupportsReplies, paints: () => paints };`;
  const kit = new Function(code)();
  let done; const store = { ready: new Promise((r) => { done = r; }), supportsReplies: () => false };
  const L = { store };
  assert.equal(kit.read(L), null, "до готовності — невідомо, а не «false»");
  assert.equal(kit.read(L), null);
  done();
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(kit.read(L), false, "після готовності — справжня відповідь");
  assert.equal(kit.paints(), 1, "готовність перемальовує панель");
  const rejected = { ready: Promise.reject(new Error("x")), supportsReplies: () => true };
  kit.read({ store: rejected });
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(kit.read({ store: rejected }), true, "відмова ready — теж «готово» (падіння команди має свою смугу)");
  assert.equal(kit.read({ store: {} }), null, "не комбіноване сховище — невідомо");
});

test("права перевіряються й у діях, а не лише в розмітці: cmtreply, cmtredit, cmtrdel, cmtrdelyes", () => {
  assert.match(act("cmtredit"), /if \(!isOwnReply\(replyOf\(\.\.\.splitReplyKey\(key\)\)\)\) return;/);
  assert.match(act("cmtrdel"), /if \(!canDeleteReply\(replyOf\(\.\.\.splitReplyKey\(key\)\)\)\) return;/);
  const m = /^  cmtreply: [\s\S]*?\n  \},$/m.exec(src)[0];
  assert.match(m, /c\.status !== 'open' \|\| repliesOff\(c\) != null\) return;/);
  const y = /^  cmtrdelyes: [\s\S]*?\n  \},$/m.exec(src)[0];
  assert.match(y, /if \(!canDeleteReply\(replyOf\(cid, rid\)\)\) \{ paintComments\(\); return; \}/);
  assert.ok(y.indexOf("canDeleteReply") < y.indexOf("removeReply"), "право — до виклику шару");
});

test("маркер відповідей без команди: окремий ключ dc-seen-r, база й запис ТІЛЬКИ відповідей, isNew бачить обʼєднання (поведінка cmtSeenSet/cmtMarkSeen)", () => {
  const store = new Map();
  const code = `${["loadSeen", "saveSeen", "cmtSeenSet", "cmtMarkSeen"].map((n) => `function ${n}${/function \w+(\([^)]*\))/.exec(src.slice(src.indexOf(`function ${n}(`)))[1]} ${fn(n)}`).join("\n")}
    ${/^const cmtReplySeenKey = .*$/m.exec(src)[0]}
    ${/^const cmtSeenKey = .*$/m.exec(src)[0]}
    return { cmtSeenSet, cmtMarkSeen };`;
  const mk = (team) => new Function("localStorage", "readSeen", "writeSeen", "baseline", "markSeen", "seenKey", "spaceNow", "currentTaskId", "cmtTeamDown", "noTeamComments", code)(
    { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    (raw) => (raw ? new Set(JSON.parse(raw)) : null), (set) => JSON.stringify([...set]),
    (items) => new Set(items.map((c) => c.id)), (seen, ids) => new Set([...(seen || []), ...ids]),
    (sp, t) => `dc-seen:${sp || "-"}:${t}`, () => ({ id: "s" }), "T1", team ? null : "down", () => !team);
  const old = { id: "r-old", parent: "c1" }, comm = { id: "c-col" };
  /* без команди: головний маркер НЕ пишеться, маркер відповідей — з базою лише відповідей */
  const k = mk(false);
  const seen = k.cmtSeenSet([comm, old]);
  assert.equal(store.has("dc-seen:s:T1"), false, "головний маркер записано без команди — залив би «Нове» при поверненні команди");
  assert.deepEqual([...JSON.parse(store.get("dc-seen-r:s:T1"))], ["r-old"], "база маркера відповідей — лише відповіді");
  assert.equal(seen.has("r-old"), true);
  /* нова відповідь — не в обʼєднанні (тобто isNew), доки її не позначили */
  assert.equal(k.cmtSeenSet([comm, old, { id: "r-new", parent: "c1" }]).has("r-new"), false);
  k.cmtMarkSeen(["r-new"]);
  assert.equal(store.has("dc-seen:s:T1"), false, "markSeen без команди не створює головного маркера");
  assert.equal(k.cmtSeenSet([old]).has("r-new"), true, "позначена відповідь — бачена");
  /* команда жива: як було — база всього в головному маркері */
  store.clear();
  mk(true).cmtSeenSet([comm, old]);
  assert.deepEqual([...JSON.parse(store.get("dc-seen:s:T1"))].sort(), ["c-col", "r-old"]);
});
