import assert from "node:assert/strict";
import test from "node:test";
import { EMPTY_LOC, formatLocation, parseLocation } from "../app/location-model.js";
import { bootFollowsServer, createNav, findKeyOf, isMacPlatform, navKeyDir } from "../app/nav.js";

const L = (o) => ({ ...EMPTY_LOC, ...o });
const H = (o) => formatLocation(L(o));
const tick = () => new Promise((r) => setTimeout(r, 15));

/** Фальшиве вікно: `replaceState` міняє hash БЕЗ події (як браузер), присвоєння `location.hash` стріляє `hashchange`. */
function fakeWin(hash = "") {
  let cur = hash;
  const listeners = [];
  const writes = [];
  let pushes = 0;
  const win = {
    location: {
      pathname: "/app/", search: "",
      get hash() { return cur; },
      set hash(v) { cur = v.startsWith("#") ? v : `#${v}`; listeners.forEach((f) => f()); },
    },
    history: {
      state: null,
      replaceState(s, _t, u) { win.history.state = s; const k = u.indexOf("#"); cur = k < 0 ? "" : u.slice(k); writes.push(cur); },
      pushState() { pushes += 1; },
    },
    addEventListener(type, fn) { if (type === "hashchange") listeners.push(fn); },
  };
  return { win, writes, pushes: () => pushes };
}
const memStore = () => ({ mem: null, get() { return this.mem; }, set(v) { this.mem = v; } });

function setup({ hash = "", goTo, store = null, cap } = {}) {
  const w = fakeWin(hash);
  const cur = { loc: L({ t: "a", it: "it1", p: "x" }) };
  const calls = [];
  const nav = createNav({
    win: w.win, store, cap, getLoc: () => cur.loc,
    /* Справжній `goTo` ставить стан місця, куди повів, — інакше `sync()` після переходу переписав би запис «поточним». */
    goTo: goTo ?? (async (loc) => { calls.push(loc); cur.loc = loc; return true; }),
  });
  /** Перехід, як його робить дія: жетон на мутації стану, `sync()` від `render()`, жетон закрито. */
  const go = (loc) => { const tk = nav.open(); cur.loc = loc; nav.sync(); nav.close(tk); };
  return { ...w, nav, cur, calls, go };
}

test("старт: sync без жетона лише записує адресу (replace), стек з одного запису, ← → вимкнені, pushState нема", () => {
  const s = setup();
  s.nav.sync();
  assert.equal(s.win.location.hash, H({ t: "a", it: "it1", p: "x" }));
  assert.equal(s.nav.canBack(), false);
  assert.equal(s.nav.canFwd(), false);
  assert.equal(s.pushes(), 0);
});

test("перехід із жетоном додає запис; адреса йде за ним; pushState не викликано", () => {
  const s = setup();
  s.nav.sync();
  s.go(L({ t: "a", it: "it1", p: "y" }));
  assert.equal(s.nav.canBack(), true);
  assert.equal(s.win.location.hash, H({ t: "a", it: "it1", p: "y" }));
  assert.equal(s.pushes(), 0);
});

test("жетон записує РІВНО ОДИН запис: другий sync під тим самим жетоном лише оновлює його", () => {
  const s = setup();
  s.nav.sync();
  const tk = s.nav.open();
  s.cur.loc = L({ t: "a", p: "y" }); s.nav.sync();
  s.cur.loc = L({ t: "a", p: "z" }); s.nav.sync();
  s.nav.close(tk);
  assert.deepEqual(s.nav.entries(), [H({ t: "a", it: "it1", p: "x" }), H({ t: "a", p: "z" })]);
});

test("без жетона sync міняє поточний запис, а не додає", () => {
  const s = setup();
  s.nav.sync();
  s.cur.loc = L({ t: "a", p: "auto" });
  s.nav.sync();
  assert.equal(s.nav.entries().length, 1);
  assert.equal(s.nav.entries()[0], H({ t: "a", p: "auto" }));
});

test("жетон, закритий без sync (ранній вихід), не витікає: пізніший sync лише оновлює запис", () => {
  const s = setup();
  s.nav.sync();
  const tk = s.nav.open();
  s.nav.close(tk);
  s.cur.loc = L({ t: "a", p: "late" });
  s.nav.sync();
  assert.equal(s.nav.entries().length, 1);
});

test("той самий стан під жетоном — запису нема", () => {
  const s = setup();
  s.nav.sync();
  s.go(s.cur.loc);
  assert.equal(s.nav.entries().length, 1);
});

test("Назад / Вперед: goTo з розібраним записом; індекс і кнопки йдуть слідом", async () => {
  const s = setup();
  s.nav.sync();
  s.go(L({ t: "a", p: "y" }));
  s.go(L({ t: "a", p: "z" }));
  assert.equal(await s.nav.back(), true);
  assert.equal(s.calls.at(-1).p, "y");
  assert.equal(s.nav.canFwd(), true);
  assert.equal(s.win.location.hash, H({ t: "a", p: "y" }));
  assert.equal(await s.nav.forward(), true);
  assert.equal(s.nav.canFwd(), false);
  assert.equal(s.win.location.hash, H({ t: "a", p: "z" }));
});

test("під час goTo sync стримано: проміжні місця не доходять до адреси, наприкінці — фінальне", async () => {
  const w = fakeWin();
  const cur = { loc: L({ t: "a", p: "x" }) };
  const transient = H({ t: "a", p: "TRANSIENT", h: "tasks" });
  const nav = createNav({
    win: w.win, getLoc: () => cur.loc,
    /* Як справжній `goTo`: `enterHome`/`wiz.requestExit` по дорозі дають `sync()` із проміжним місцем. */
    goTo: async (loc) => { cur.loc = L({ t: "a", p: "TRANSIENT", h: "tasks" }); nav.sync(); await tick(); cur.loc = loc; nav.sync(); return true; },
  });
  nav.sync();
  const tk = nav.open(); cur.loc = L({ t: "a", p: "y" }); nav.sync(); nav.close(tk);
  assert.equal(await nav.back(), true);
  assert.ok(!w.writes.includes(transient), "проміжне місце не записано");
  assert.equal(w.win.location.hash, H({ t: "a", p: "x" }));
});

test("відмова goTo: індекс і записи лишаються, кнопки ті самі", async () => {
  const s = setup({ goTo: async () => false });
  s.nav.sync();
  s.go(L({ t: "a", p: "y" }));
  assert.equal(await s.nav.back(), false);
  assert.equal(s.nav.canBack(), true);
  assert.equal(s.nav.canFwd(), false);
  assert.equal(s.nav.entries().length, 2);
});

test("'gone': мертвий запис викидається, йдемо до сусіднього", async () => {
  const dead = H({ t: "dead" });
  const s = setup({ goTo: async (loc) => (loc.t === "dead" ? "gone" : true) });
  s.nav.sync();
  s.go(L({ t: "dead" }));
  s.go(L({ t: "a", p: "z" }));
  assert.equal(await s.nav.back(), true);
  assert.ok(!s.nav.entries().includes(dead), "мертвий запис викинуто");
  assert.equal(s.nav.index(), 0);
});

test("новий перехід після Назад відтинає «вперед»", async () => {
  const s = setup();
  s.nav.sync();
  s.go(L({ t: "a", p: "y" }));
  s.go(L({ t: "a", p: "z" }));
  await s.nav.back();
  assert.equal(s.nav.canFwd(), true);
  s.go(L({ t: "a", p: "n" }));
  assert.equal(s.nav.canFwd(), false);
  assert.equal(s.nav.entries().length, 3);
});

test("стеля: старіші записи відпадають, Назад усе ще працює", async () => {
  const s = setup({ cap: 3 });
  s.nav.sync();
  for (const p of ["1", "2", "3", "4", "5"]) s.go(L({ t: "a", p }));
  assert.equal(s.nav.entries().length, 3);
  assert.equal(await s.nav.back(), true);
});

test("sessionStorage: стек переживає перезавантаження; глибоке посилання додається новим записом; сміття ігнорується", () => {
  const store = memStore();
  const a = setup({ store });
  a.nav.sync();
  a.go(L({ t: "a", p: "y" }));
  const same = setup({ store, hash: H({ t: "a", p: "y" }) });
  assert.equal(same.nav.canBack(), true, "після ⌘R Назад доступна");
  assert.equal(same.nav.entries().length, 2);
  const deep = setup({ store, hash: H({ t: "other", p: "q" }) });
  assert.equal(deep.nav.entries().length, 3, "глибоке посилання — новий запис");
  assert.equal(deep.nav.canBack(), true);
  const bad = memStore(); bad.mem = "{garbage";
  assert.equal(setup({ store: bad, hash: H({ t: "k" }) }).nav.entries().length, 1);
});

test("hashchange: goTo із розібраним місцем і запис у стек; власні записи адреси goTo не кличуть", async () => {
  const s = setup();
  s.nav.sync();
  s.go(L({ t: "a", p: "y" }));
  assert.equal(s.calls.length, 0, "власний replaceState hashchange не дає");
  s.win.location.hash = H({ t: "b", it: "it2", p: "w" });
  await tick();
  assert.equal(s.calls.length, 1);
  assert.equal(s.calls[0].t, "b");
  assert.equal(s.nav.entries().length, 3);
  assert.equal(s.nav.canBack(), true);
});

test("hashchange під час goTo ставиться в чергу й виконується після осідання (не губиться)", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const calls = [];
  const w = fakeWin();
  const cur = { loc: L({ t: "a", p: "x" }) };
  const nav = createNav({
    win: w.win, getLoc: () => cur.loc,
    goTo: async (loc) => { calls.push(loc.p); if (loc.p === "x") await gate; cur.loc = loc; return true; },
  });
  nav.sync();
  const tk = nav.open(); cur.loc = L({ t: "a", p: "y" }); nav.sync(); nav.close(tk);
  const back = nav.back();                                  // goTo(x) висить на `gate`
  await tick();
  w.win.location.hash = H({ t: "a", p: "typed" });          // людина вписала адресу під час переходу
  release();
  await back; await tick();
  assert.deepEqual(calls, ["x", "typed"], "вписана адреса виконана ПІСЛЯ переходу, а не загублена");
});

test("hashchange на порожній hash: адреса повертається до поточного запису, goTo не кличеться", async () => {
  const s = setup();
  s.nav.sync();
  const before = s.win.location.hash;
  s.win.location.hash = "";
  await tick();
  assert.equal(s.win.location.hash, before);
  assert.equal(s.calls.length, 0);
});

test("жетон, не закритий до Назад, не записує нічого під час Назад/Вперед", async () => {
  const s = setup();
  s.nav.sync();
  s.go(L({ t: "a", p: "y" }));
  s.nav.open();                                             // «забутий» жетон
  await s.nav.back();
  s.cur.loc = L({ t: "a", p: "after" });
  s.nav.sync();
  assert.equal(s.nav.canFwd(), true, "жетон скинуто на початку step(): запису не додано, «Вперед» не обрізано");
  assert.equal(s.nav.entries().length, 2);
});

test("goTo, що відмовив (збій мережі), не викидає запис стека", async () => {
  const s = setup({ goTo: async () => false });
  s.nav.sync();
  s.go(L({ t: "a", p: "y" }));
  await s.nav.back();
  assert.equal(s.nav.entries().length, 2);
  assert.equal(s.nav.canBack(), true);
});

test("hashchange, що goTo відмовив: адреса вертається до поточного запису", async () => {
  const s = setup({ goTo: async () => false });
  s.nav.sync();
  const before = s.win.location.hash;
  s.win.location.hash = H({ t: "zzz" });
  await tick();
  assert.equal(s.win.location.hash, before);
  assert.equal(s.nav.entries().length, 1);
});

test("сторонній sync із тим самим місцем не спалює жетон: потім зміна місця під тим самим жетоном — РІВНО ОДИН запис", () => {
  const s = setup();
  s.nav.sync();
  const tk = s.nav.open();
  s.nav.sync();                                   // сторонній render() до мутації стану: місце те саме
  s.cur.loc = L({ t: "a", p: "real" });           // справжня дія змінила стан
  s.nav.sync();
  s.nav.close(tk);
  assert.deepEqual(s.nav.entries(), [H({ t: "a", it: "it1", p: "x" }), H({ t: "a", p: "real" })]);
  assert.equal(s.nav.canBack(), true);
});

test("збережений стек довший за стелю: глибоке посилання обрізає найстаріші, індекс на новому записі", () => {
  const store = memStore();
  store.mem = JSON.stringify({ entries: ["#t=1", "#t=2", "#t=3", "#t=4", "#t=5"], index: 4 });
  const s = setup({ store, cap: 3, hash: "#t=deep" });
  assert.equal(s.nav.entries().length, 3);
  assert.equal(s.nav.index(), 2);
  assert.equal(s.nav.entries().at(-1), "#t=deep");
  assert.deepEqual(s.nav.entries().slice(0, 2), ["#t=4", "#t=5"]);
});

test("усі записи в напрямку мертві: Назад викидає їх, повертає false, індекс 0, стек лише з поточного", async () => {
  const w = fakeWin();
  const cur = { loc: L({ t: "dead", p: "0" }) };
  let alive = true;
  const nav = createNav({
    win: w.win, getLoc: () => cur.loc,
    goTo: async (loc) => { if (!alive && loc.t === "dead") return "gone"; cur.loc = loc; return true; },
  });
  nav.sync();
  for (const p of ["1", "2"]) { const tk = nav.open(); cur.loc = L({ t: "dead", p }); nav.sync(); nav.close(tk); }
  const tk = nav.open(); cur.loc = L({ t: "a", p: "z" }); nav.sync(); nav.close(tk);
  alive = false;
  assert.equal(await nav.back(), false);
  assert.deepEqual(nav.entries(), [H({ t: "a", p: "z" })]);
  assert.equal(nav.index(), 0);
  assert.equal(nav.canBack(), false);
});

test("усі записи «вперед» мертві: false, мертві викинуто, індекс не зсунуто, canFwd вимкнено", async () => {
  const w = fakeWin();
  const cur = { loc: L({ t: "a", p: "x" }) };
  let alive = true;
  const nav = createNav({
    win: w.win, getLoc: () => cur.loc,
    goTo: async (loc) => { if (!alive && loc.t === "dead") return "gone"; cur.loc = loc; return true; },
  });
  nav.sync();
  for (const p of ["1", "2"]) { const tk = nav.open(); cur.loc = L({ t: "dead", p }); nav.sync(); nav.close(tk); }
  await nav.back(); await nav.back();
  assert.equal(nav.index(), 0);
  alive = false;
  assert.equal(await nav.forward(), false);
  assert.deepEqual(nav.entries(), [H({ t: "a", p: "x" })]);
  assert.equal(nav.index(), 0);
  assert.equal(nav.canFwd(), false);
});

test("bootFollowsServer: посилання перемикає, reload/back_forward з іншою задачею йдуть за сервером, та сама задача — повне місце", () => {
  assert.equal(bootFollowsServer("navigate", L({ t: "b" }), "a"), false, "посилання: явний намір");
  assert.equal(bootFollowsServer("reload", L({ t: "b" }), "a"), true);
  assert.equal(bootFollowsServer("back_forward", L({ t: "b" }), "a"), true);
  assert.equal(bootFollowsServer("reload", L({ t: "a" }), "a"), false, "та сама задача — повне місце");
  assert.equal(bootFollowsServer("reload", L({ it: "it1" }), "a"), false, "без t нічого перемикати");
  assert.equal(bootFollowsServer("reload", L({ t: "x" }), null), true);   // сервер без поточної задачі: reload відкидає `t` — безпечно й навмисно
});

test("navKeyDir: платформний модифікатор — на Mac лише ⌘, інакше лише Ctrl; Shift/Alt/композиція й інші клавіші — 0", async () => {
  const k = (o) => ({ code: "BracketLeft", key: "[", ...o });
  assert.equal(navKeyDir(k({ metaKey: true }), true), -1);
  assert.equal(navKeyDir(k({ ctrlKey: true }), true), 0, "Ctrl+[ на Mac — не наше");
  assert.equal(navKeyDir(k({ ctrlKey: true }), false), -1);
  assert.equal(navKeyDir(k({ metaKey: true }), false), 0, "⌘[ на Windows — не наше");
  assert.equal(navKeyDir({ code: "BracketRight", key: "]", metaKey: true }, true), 1);
  assert.equal(navKeyDir({ code: "KeyХ", key: "х", metaKey: true }, true), 0);
  assert.equal(navKeyDir(k({ metaKey: true, shiftKey: true }), true), 0);
  assert.equal(navKeyDir(k({ metaKey: true, isComposing: true }), true), 0);
  assert.equal(navKeyDir({ code: "BracketLeft", key: "х", metaKey: true }, true), -1, "укр. розкладка: за `code`");
  assert.equal(navKeyDir({ code: "BracketRight", key: "ъ", metaKey: true }, true), 1, "нелатинська розкладка: за `code`");
  assert.equal(navKeyDir({ code: "BracketLeft", key: "/", metaKey: true }, true), 0, "Dvorak: фізична `[` видає `/` — не крадемо ⌘/");
  assert.equal(navKeyDir({ code: "Slash", key: "[", metaKey: true }, true), -1, "Dvorak: `[` стоїть деінде — за `key`");
  assert.equal(navKeyDir({ code: "BracketRight", key: "=", ctrlKey: true }, false), 0, "Dvorak: фізична `]` видає `=`");
});

test("isMacPlatform: userAgentData → platform → userAgent; перший непорожній вирішує; без navigator — не Mac", () => {
  assert.equal(isMacPlatform({ platform: "MacIntel" }), true);
  assert.equal(isMacPlatform({ platform: "Win32" }), false);
  assert.equal(isMacPlatform({ platform: "", userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" }), true, "порожня platform → userAgent");
  assert.equal(isMacPlatform({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" }), true);
  assert.equal(isMacPlatform({ userAgentData: { platform: "macOS" }, platform: "Win32" }), true, "userAgentData першим");
  assert.equal(isMacPlatform({ userAgentData: { platform: "Windows" }, platform: "MacIntel" }), false);
  assert.equal(isMacPlatform({ userAgentData: { platform: "" }, platform: "", userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64)" }), false);
  assert.equal(isMacPlatform({}), false);
  assert.equal(isMacPlatform(null), false);
  assert.equal(isMacPlatform({ get platform() { throw new Error("x"); } }), false);
});

test("проводка 0.40 (мінори T5): створення задачі й демо йдуть під `navigating`; майстер — ні; goTo → settings віддає факт відкриття; ⌘[ ⌘] з `.catch`", async () => {
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");
  assert.match(src, /await navigating\(\(\) => leaveHome\(\)\);/, "створення задачі з форми");
  assert.match(src, /await navigating\(\(\) => \(homeOpen \? leaveHome\(\) : render\(\)\)\)/, "демо-задача (існуюча)");
  assert.match(src, /r\.existed \? switchTask\(r\.id\) : navigating\(\(\) => wizOpenTask\(r\)\)/, "демо-задача (щойно створена) — свій запис");
  assert.match(src, /openTask: \(made\) => wizOpenTask\(made\),/, "майстер кличе wizOpenTask напряму (replace-only)");
  const body = src.slice(src.indexOf("async function wizOpenTask("), src.indexOf("async function openSpaceEdit("));
  assert.ok(body.includes("await leaveHome();"), "wizOpenTask виходить із «Задач»");
  assert.ok(!/navigating\(/.test(body.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "")), "wizOpenTask сам не відкриває жетон");
  assert.match(src, /const NAV_MAC = isMacPlatform\(\);/, "платформа — з одного хелпера");
  assert.match(src, /await enterConnections\(\); return homeOpen && homePage === 'conn';/, "settings: відмова, якщо не відкрилось");
  assert.match(src, /\(d < 0 \? nav\.back\(\) : nav\.forward\(\)\)\.catch\(\(\) => \{\}\)/);
  assert.match(src, /const live = \(\) => gen === goGen && tgen === taskSwitchGen && stillWanted\(\);/);
});

test("findKeyOf: матриця платформ — ⌘F/⌘G/⇧⌘G на Mac, Ctrl деінде; чужий модифікатор, Alt, композиція, ⇧F — null", () => {
  const e = (o) => ({ code: "", key: "", metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, isComposing: false, ...o });
  const F = { code: "KeyF", key: "f" };
  const G = { code: "KeyG", key: "g" };
  for (const [mac, own, other] of [[true, "metaKey", "ctrlKey"], [false, "ctrlKey", "metaKey"]]) {
    assert.equal(findKeyOf(e({ ...F, [own]: true }), mac), "find");
    assert.equal(findKeyOf(e({ ...G, [own]: true }), mac), "next");
    assert.equal(findKeyOf(e({ ...G, key: "G", [own]: true, shiftKey: true }), mac), "prev");
    assert.equal(findKeyOf(e({ ...F, [other]: true }), mac), null, `чужий модифікатор (mac=${mac})`);
    assert.equal(findKeyOf(e({ ...G, [other]: true }), mac), null);
    assert.equal(findKeyOf(e({ ...F, [own]: true, [other]: true }), mac), null, "обидва модифікатори — не наше");
    assert.equal(findKeyOf(e({ ...F, [own]: true, altKey: true }), mac), null);
    assert.equal(findKeyOf(e({ ...F, [own]: true, isComposing: true }), mac), null);
    assert.equal(findKeyOf(e({ ...F, [own]: true, shiftKey: true }), mac), null, "⇧⌘F — не наше");
    assert.equal(findKeyOf(e({ code: "KeyH", key: "h", [own]: true }), mac), null);
    assert.equal(findKeyOf(e({ ...F }), mac), null, "без модифікатора");
  }
  assert.equal(findKeyOf(e({ code: "KeyF", key: "а", metaKey: true }), true), "find", "укр. розкладка: за `code`");
  assert.equal(findKeyOf(e({ code: "KeyG", key: "п", metaKey: true }), true), "next");
  assert.equal(findKeyOf(e({ code: "KeyY", key: "f", metaKey: true }), true), "find", "розкладка, де `f` не на KeyF: за `key`");
  assert.equal(findKeyOf(e({ code: "KeyG", key: "G", ctrlKey: true, shiftKey: true }), false), "prev");
  /* Dvorak/Colemak: фізична F видає `u`/`e` — це ⌘U/⌘E, а не пошук; фізична G там — `i`/`g`. */
  assert.equal(findKeyOf(e({ code: "KeyF", key: "u", metaKey: true }), true), null, "Dvorak: фізична F = ⌘U");
  assert.equal(findKeyOf(e({ code: "KeyF", key: "e", metaKey: true }), true), null, "Colemak: фізична F = ⌘E");
  assert.equal(findKeyOf(e({ code: "KeyG", key: "i", ctrlKey: true }), false), null, "Dvorak: фізична G = Ctrl+I");
  assert.equal(findKeyOf(e({ code: "KeyU", key: "f", metaKey: true }), true), "find", "Dvorak: ⌘F стоїть на KeyU");
  assert.equal(findKeyOf(e({ code: "KeyI", key: "g", metaKey: true }), true), "next");
  assert.equal(findKeyOf(e({ code: "KeyF", key: "Dead", metaKey: true }), true), "find", "мертва клавіша — не ASCII: за `code`");
  assert.equal(findKeyOf(e({ code: "KeyF", key: "", metaKey: true }), true), "find", "порожній `key`: за `code`");
});

test("проводка 0.40 (T7): navKeys бере пошук із findKeyOf; ⌘G без плашки не перехоплюється; один захоплювач у рамці; findGuard після nav.sync", async () => {
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");
  const body = src.slice(src.indexOf("function navKeys(ev) {"), src.indexOf("function frameNavKey("));
  assert.match(body, /const fk = findKeyOf\(ev, NAV_MAC\);/);
  assert.match(body, /if \(!find\.isOpen\(\)\) return false;/, "⌘G без плашки лишається «згрупувати»");
  assert.doesNotMatch(body, /metaKey|ctrlKey/, "платформне правило — лише в nav.js");
  assert.equal(src.split("addEventListener('keydown', frameNavKey, true)").length - 1, 1, "захоплювач рамки ставиться з одного місця");
  assert.match(src, /if \(find\.isOpen\(\)\) find\.rerun\(\);/);
  assert.equal(src.split("findGuard();").length - 1, 2, "render() і enterHome");
  assert.equal(src.split(/nav\.sync\(\);\s*(?:\/\/[^\n]*\n\s*)?findGuard\(\);/).length - 1, 2, "findGuard — одразу після nav.sync у render() і enterHome");
  const fnk = src.slice(src.indexOf("function frameNavKey("), src.indexOf("function frameNavKey(") + 400);
  assert.match(fnk, /ev\.key === 'Escape'[^\n]*find\.isOpen\(\)/, "Esc у рамці закриває лише ВІДКРИТУ плашку");
});
