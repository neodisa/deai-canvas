/**
 * Піни на «Огляді» (T-45) — чиста модель: яка сторінка в піна, де він у світі,
 * коли кадр злипається в лічильник, куди летить камера.
 *
 * Мапа «перевірка → запобіжник» (мутаційно, див. Phase Recap T-45):
 *   сторінка з версії   — розбір `"3/stattia"`. Мутація «брати лише page= з url» червонить A.
 *   стан у кадрі        — `stateQ` у `cardMatches`. Мутація «прибрати» червонить B.
 *   +10/+10             — `PIN_OFFSET`. Мутація 10→0 червонить C.
 *   обріз кадру         — `ly > card.h`. Мутація «прибрати» червонить C.
 *   поріг кластера      — `<` у `clustered`. Мутація `<=` червонить D (межа).
 *   позаекранний        — `vis`, а не викидання. Мутація «фільтрувати» червонить E.
 *   стеля/підлога зуму  — `revealCam`. Мутації червонять F.
 */
import assert from "node:assert/strict";
import test from "node:test";
import {
  CLUSTER_W, PIN_OFFSET, cardMatches, cardsOfPin, layoutPins, pinTarget, pinWorld, revealCam,
} from "../app/overview-pins.js";

const pin = (id, version, url = "", extra = {}) => ({ id, status: "open", meta: { version, url }, ...extra });
const HEAD = 34;

test("A: сторінка піна — суфікс версії, неявна main, запасний page= з url", () => {
  assert.deepEqual(pinTarget(pin("a", "3/stattia")), { page: "stattia", stateQ: "" });
  assert.deepEqual(pinTarget(pin("b", "3")), { page: "main", stateQ: "" });
  // legacy-тег (`it1`) ітерації не несе — сторінка береться з url живого виду
  assert.deepEqual(pinTarget(pin("c", "it1", "http://h/commented?it=it1&page=poshuk&ch=local")),
    { page: "poshuk", stateQ: "" });
  // версія каже одне, url інше — вірити версії: її пише той самий `page_version_tag`
  assert.equal(pinTarget(pin("d", "3/stattia", "http://h/commented?it=it3&page=inshe")).page, "stattia");
  assert.equal(pinTarget(pin("e", null, "")), null, "ні версії, ні url — сторінки не вгадуємо");
  assert.equal(pinTarget(pin("f", "3", "не url")).page, "main", "битий url не валить розбір");
});

test("B: стан — хвіст url без наших параметрів, тим самим stateQuery, що в кадрі", () => {
  const t = pinTarget(pin("e", "3/poshuk", "http://h/commented?it=it3&page=poshuk&ch=local&tab=b&q=x"));
  assert.equal(t.stateQ, "&q=x&tab=b");
  assert.equal(cardMatches({ page: "poshuk", state: { tab: "b", q: "x" } }, t), true);
  assert.equal(cardMatches({ page: "poshuk", state: null }, t), false, "стан не той — кадр не той");
  assert.equal(cardMatches({ page: "poshuk", state: null }, pinTarget(pin("g", "3/poshuk"))), true);
  assert.equal(cardMatches({ page: "poshuk", state: null }, null), false);
});

test("B2: host=1 у url піна (створений у рамці режиму хоста) — той самий стан і вузол, що без нього", () => {
  const base = "http://h/commented?it=it3&page=poshuk&ch=local&tab=b";
  const plain = pinTarget(pin("h", "3/poshuk", base));
  const hosted = pinTarget(pin("i", "3/poshuk", base + "&host=1"));
  assert.deepEqual(hosted, plain);
  assert.equal(hosted.stateQ, "&tab=b");
  assert.equal(cardMatches({ page: "poshuk", state: { tab: "b" } }, hosted), true);
  assert.equal(pinTarget(pin("j", "3", "http://h/commented?it=it3&host=1")).stateQ, "", "лише host=1 — стану нема");
});

test("C: світова точка — кут елемента +10/+10 під головою кадру; 0×0 і нижче обрізу — null", () => {
  const card = { x: 100, y: 200, h: 900 };            // h — висота ЗНІМКА, голова окремо
  assert.deepEqual(pinWorld(card, { x: 50, y: 60, w: 10, h: 10 }, null, HEAD),
    { x: 100 + 50 + PIN_OFFSET, y: 200 + HEAD + 60 + PIN_OFFSET });
  assert.equal(pinWorld(card, { x: 0, y: 0, w: 0, h: 0 }, null, HEAD), null, "невидимий — як у живому виді");
  assert.equal(pinWorld(card, { x: 0, y: 895, w: 5, h: 5 }, null, HEAD), null, "нижче обрізу кадру");
  // Між «висота знімка мінус голова» і «висота знімка» — пін ЩЕ на картинці.
  // План T-45 спершу рахував обріз як `card.h - head`; ця точка це ловить.
  assert.deepEqual(pinWorld(card, { x: 0, y: 870, w: 5, h: 5 }, null, HEAD),
    { x: 100 + PIN_OFFSET, y: 200 + HEAD + 880 }, "низ знімка — ще кадр");
  assert.deepEqual(pinWorld(card, { x: 0, y: 0, w: 100, h: 40 }, { fx: 0.5, fy: 0.5 }, HEAD),
    { x: 150, y: 200 + HEAD + 20 }, "частка всередині елемента (етап 2)");
  assert.equal(pinWorld(card, null, null, HEAD), null);
});

test("D: кластер, коли кадр на екрані вужчий за CLUSTER_W; межа — вже окремі піни", () => {
  const cards = [{ id: "k", page: "main", state: null, x: 0, y: 0, h: 900 }];
  const pins = [pin("a", "3"), pin("b", "3")];
  const worldOf = () => ({ x: 20, y: 60 });
  const view = { left: 0, top: 46, w: 1000, h: 700 };
  const small = layoutPins({ pins, cards, cam: { x: 0, y: 0, scale: (CLUSTER_W - 1) / 1280 }, cardW: 1280, view, worldOf });
  assert.equal(small.length, 1);
  assert.equal(small[0].cluster, true);
  assert.deepEqual(small[0].ids, ["a", "b"]);
  const edge = layoutPins({ pins, cards, cam: { x: 0, y: 0, scale: CLUSTER_W / 1280 }, cardW: 1280, view, worldOf });
  assert.equal(edge.length, 2, "рівно CLUSTER_W — уже окремі піни");
  const big = layoutPins({ pins, cards, cam: { x: 0, y: 0, scale: 0.5 }, cardW: 1280, view, worldOf });
  assert.equal(big[0].cluster, false);
  assert.deepEqual([big[0].x, big[0].y], [0 + 0 + 20 * 0.5, 46 + 0 + 60 * 0.5], "екран = view + cam + світ·масштаб");
  assert.notEqual(big[0].key, big[1].key);
});

test("E: пін поза полотном — vis:false, але в переліку лишається", () => {
  const cards = [{ id: "k", page: "main", state: null, x: 0, y: 0, h: 900 }];
  const r = layoutPins({ pins: [pin("a", "3")], cards, cam: { x: -5000, y: 0, scale: 1 }, cardW: 1280,
    view: { left: 0, top: 0, w: 800, h: 600 }, worldOf: () => ({ x: 20, y: 60 }) });
  assert.equal(r.length, 1);
  assert.equal(r[0].vis, false);
});

test("E2: пін без місця на кадрі — у лічильник «поза кадром»; поки геометрія їде — ніде; на кількох копіях — на кожній", () => {
  const cards = [{ id: "k1", page: "main", state: null, x: 0, y: 0, h: 900 },
                 { id: "k2", page: "main", state: null, x: 2000, y: 0, h: 900 },
                 { id: "k3", page: "main", state: null, x: 4000, y: 0, h: 900 },
                 { id: "k4", page: "inshe", state: null, x: 6000, y: 0, h: 900 }];
  const worldOf = (p, c) => (c.id === "k2" ? null : c.id === "k3" ? undefined : { x: c.x + 5, y: 5 });
  const r = layoutPins({ pins: [pin("a", "3")], cards, cam: { x: 0, y: 0, scale: 1 }, cardW: 1280,
    view: { left: 0, top: 0, w: 800, h: 600 }, worldOf });
  assert.deepEqual(r.map((i) => i.key), ["p:a@k1", "o:k2"], "k2 — поза кадром, k3 — ще невідомо");
  assert.equal(r[1].off, true);
  assert.deepEqual(r[1].ids, ["a"]);
  assert.deepEqual(cardsOfPin(pin("a", "3"), cards).map((c) => c.id), ["k1", "k2", "k3"]);
});

test("E3: лічильник на дрібному зумі — лише піни з місцем на кадрі; решта — «поза кадром» (рішення 29.09)", () => {
  const cards = [{ id: "k", page: "main", state: null, x: 0, y: 0, h: 900 }];
  const pins = [pin("a", "3"), pin("b", "3"), pin("gone", "3")];
  const worldOf = (p) => (p.id === "gone" ? null : { x: 20, y: 60 });
  const r = layoutPins({ pins, cards, cam: { x: 0, y: 0, scale: 0.05 }, cardW: 1280,
    view: { left: 0, top: 0, w: 1000, h: 700 }, worldOf });
  const cl = r.find((i) => i.cluster), off = r.find((i) => i.off);
  assert.deepEqual(cl.ids, ["a", "b"], "лічильник рахує піни без місця");
  assert.deepEqual(off.ids, ["gone"]);
});

test("F: переліт — точка в центр, масштаб не менший за 0.5 і не більший за 1", () => {
  const c = revealCam({ x: 1000, y: 2000 }, { scale: 0.1 }, { w: 800, h: 600 });
  assert.equal(c.scale, 0.5);
  assert.equal(c.x, 400 - 1000 * 0.5);
  assert.equal(c.y, 300 - 2000 * 0.5);
  assert.equal(revealCam({ x: 0, y: 0 }, { scale: 0.8 }, { w: 800, h: 600 }).scale, 0.8, "свій масштаб, якщо вже великий");
  assert.equal(revealCam({ x: 0, y: 0 }, { scale: 2 }, { w: 800, h: 600 }).scale, 1, "кадр знято 1:1 — вище нема сенсу");
});

/* ── Етап 2 T-45: наведення й ціль нового коментаря ─────────────────────────
   Мапа запобіжників: голова кадру не ціль — `ly < 0` у `cardAt` (мутація
   «прибрати» червонить G); найглибший — `path.length` у `hitElement` (мутація
   «найменша площа першою» червонить H); hid/pe — фільтр (мутація червонить H);
   частка кліку й тег версії — `targetFor` (червонить I). */
import { cardAt, hitElement, targetFor } from "../app/overview-pins.js";

test("G: кадр під точкою — лише ТІЛО кадру, голова (підпис, «Відкрити») не ціль", () => {
  const cards = [{ id: "a", x: 0, y: 0, h: 900 }, { id: "b", x: 1480, y: 0, h: 500 }];
  assert.equal(cardAt(cards, 100, 10, 1280, HEAD), null, "голова кадру");
  assert.equal(cardAt(cards, 100, HEAD + 5, 1280, HEAD).card.id, "a");
  assert.deepEqual(cardAt(cards, 1500, HEAD + 20, 1280, HEAD), { card: cards[1], lx: 20, ly: 20 });
  assert.equal(cardAt(cards, 1500, HEAD + 501, 1280, HEAD), null, "нижче знімка");
  assert.equal(cardAt(cards, 1300, HEAD + 5, 1280, HEAD), null, "у зазорі між кадрами");
});

test("H: елемент під точкою — найглибший; невидимий, прозорий для миші й 0×0 — ні", () => {
  const E = (path, x, y, w, h, extra = {}) => ({ tag: "div", path, x, y, w, h, ...extra });
  const els = [
    E(["div[0]"], 0, 0, 1000, 1000),
    E(["div[0]", "section[0]"], 0, 0, 500, 500),
    E(["div[0]", "section[0]", "p[0]"], 10, 10, 400, 40),
    E(["div[0]", "i[0]"], 0, 0, 5, 5),                          // дрібніший, але мілкіший
    E(["div[0]", "section[0]", "p[0]", "b[0]"], 10, 10, 0, 0),  // 0×0
    E(["div[0]", "section[0]", "p[0]", "u[0]"], 10, 10, 80, 20, { hid: 1 }),
    E(["div[0]", "section[0]", "p[0]", "s[0]"], 10, 10, 80, 20, { pe: 0 }),
    // мілкий, але крихітний — накриває точку поверх глибокого абзацу; «найменша
    // площа першою» взяла б його замість абзацу
    E(["em[0]"], 15, 15, 10, 10),
  ];
  assert.equal(hitElement(els, 20, 20), 2, "найглибший видимий");
  assert.equal(hitElement(els, 2, 2), 3, "у тієї ж глибини — менша площа");
  assert.equal(hitElement(els, 700, 700), 0);
  assert.equal(hitElement(els, 2000, 2000), -1);
});

test("I: ціль нового коментаря — відбиток із геометрії, частка кліку, сторінка у версії й url", () => {
  const card = { id: "poshuk", page: "poshuk", state: { tab: "b" }, x: 1000, y: 200, h: 900 };
  const e = { tag: "button", stableId: "testid:go", path: ["div[0]", "button[0]"], text: "знайти",
              textHash: "t", structHash: "s", styleHash: "y", x: 100, y: 50, w: 200, h: 40 };
  const cam = { x: 10, y: 20, scale: 0.5 }, view = { left: 0, top: 46, w: 1200, h: 800 };
  const t = targetFor({ card, e, lx: 150, ly: 60, cam, view, head: HEAD, it: "it4", iterNum: "4",
                        channel: "local", canvasW: 1280, origin: "http://h" });
  assert.deepEqual(t.fp, { tag: "button", stableId: "testid:go", text: "знайти", textHash: "t",
                           structHash: "s", styleHash: "y", path: ["div[0]", "button[0]"] });
  assert.deepEqual(t.anchor, { fx: 0.25, fy: 0.25 });
  assert.deepEqual(t.rect, { left: 0 + 10 + 1100 * 0.5, top: 46 + 20 + (200 + HEAD + 50) * 0.5, width: 100, height: 20 });
  assert.equal(t.meta.version, "4/poshuk");
  assert.equal(t.meta.url, "http://h/commented?it=it4&page=poshuk&ch=local&tab=b");
  assert.equal(t.meta.route, "/commented");
  assert.deepEqual(t.meta.viewport, { w: 1280, h: 900 });
  assert.equal(t.meta.via, "overview");
  // неявна сторінка — чисте число, як `page_version_tag`
  assert.equal(targetFor({ card: { ...card, page: "main", state: null }, e, lx: 150, ly: 60, cam, view, head: HEAD,
    it: "it4", iterNum: "4", channel: "project", canvasW: 1280, origin: "http://h" }).meta.version, "4");
  // пін нового коментаря сідає в точку кліку: та сама формула, що в pinWorld
  assert.deepEqual(pinWorld(card, e, t.anchor, HEAD), { x: 1000 + 150, y: 200 + HEAD + 60 });
});

/* ── Відгук (етап 3 T-45): розбір адреси піна — раз на ПІН, а не на кадр ────
   Замір на bf360 (264 піни, 24 кадри): `pinTarget` + `URL` — ~3.4с власного
   часу JS за панораму, тобто ~8мс на кадр понад полотно без пінів; кадр 120 Гц
   падав до 60. Причина — розбір url кожного піна для КОЖНОГО кадру на КОЖЕН
   кадр камери. Охоронець рахує `new URL`: мутація «прибрати кеш» червонить J. */
test("J: layoutPins на кадрах камери розбирає адресу кожного піна не більше одного разу", () => {
  const Real = globalThis.URL;
  let made = 0;
  globalThis.URL = class extends Real { constructor(...a) { super(...a); made += 1; } };
  try {
    const cards = Array.from({ length: 6 }, (_, i) => ({ id: `p${i}`, page: `p${i}`, state: null, x: i * 1500, y: 0, h: 900 }));
    const pins = Array.from({ length: 30 }, (_, i) => pin(`c${i}`, `6/p${i % 6}`, `http://h/commented?it=it6&page=p${i % 6}&ch=local`));
    const args = { pins, cards, cam: { x: 0, y: 0, scale: 0.5 }, cardW: 1280, view: { left: 0, top: 0, w: 1400, h: 800 }, worldOf: () => ({ x: 1, y: 1 }) };
    for (let f = 0; f < 10; f += 1) layoutPins(args);
    assert.ok(made <= pins.length, `на 10 кадрів камери розібрано ${made} адрес на ${pins.length} пінів`);
    assert.equal(layoutPins(args).length, pins.length, "кеш не сміє губити піни");
  } finally { globalThis.URL = Real; }
});

test("E4: на дрібному зумі кадр, де ВСІ піни поза кадром, — без порожнього лічильника (повторне ревʼю, NEW-5)", () => {
  const cards = [{ id: "k", page: "main", state: null, x: 0, y: 0, h: 900 }];
  const r = layoutPins({ pins: [pin("gone", "3")], cards, cam: { x: 0, y: 0, scale: 0.05 }, cardW: 1280,
    view: { left: 0, top: 0, w: 1000, h: 700 }, worldOf: () => null });
  assert.deepEqual(r.map((i) => i.key), ["o:k"], "зʼявився лічильник без пінів");
});
