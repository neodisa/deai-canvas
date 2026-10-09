/**
 * Адаптер локального сховища коментарів: запис НЕ сміє відкочувати те, чого
 * вкладка не бачила.
 *
 * ЩО ЛАМАЛОСЬ (фідбек 08.09.2026). Шар тримає весь список пінів у памʼяті і при
 * будь-якій дії POSTить його ЦІЛКОМ, а `/api/local-comments` замінює файл
 * повністю. Тому: Клод закрив 9 пінів (API підтвердив), дизайнер додав
 * наступний пін зі сторінки, відкритої ДО цього, — і всі 9 знову стали
 * відкритими. Тобто правило «закривай пін одразу, як зробив» технічно не
 * працювало, поки сторінка відкрита.
 *
 * ЯК ПОЛАГОДЖЕНО. Трьохстороннє злиття В АДАПТЕРІ, без жодного нового поля в
 * даних: базою слугує те, що вкладка ЗНАЛА (її попередній кеш), тому видно
 * різницю між «клієнт змінив пін» і «клієнт про пін просто не в курсі».
 * Перше виграє, друге лишається серверним. Ні `updated_at`, ні ревізій у пінах
 * немає — і вигадувати їх не довелось.
 *
 * ⛔ Чому саме тут, а не в ендпоінті: сервер із повного масиву не може
 * відрізнити «клієнт видалив пін» від «клієнт його не бачив», а адаптер може —
 * він і є тим, хто тримає базу. Плюс `comment-layer` лишається окремим
 * продуктом: `local-adapter.js` НАШ, бандл шару не чіпаємо.
 */
import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const VENDOR = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
                            "..", "app", "vendor", "local-adapter.js");

/** Сервер у памʼяті: віддає свій список і приймає повний масив, як справжній. */
function fakeServer(initial) {
  const state = { rows: initial.map((c) => ({ ...c })), writes: 0 };
  globalThis.fetch = async (url, opts) => {
    if (!opts || opts.method !== "POST") {
      return { ok: true, json: async () => ({ comments: state.rows }) };
    }
    state.writes += 1;
    state.rows = JSON.parse(opts.body).comments;
    return { ok: true, json: async () => ({ ok: true }) };
  };
  return state;
}

const pin = (id, extra = {}) => ({
  id, author: "Lead", text: `пін ${id}`, status: "open", fp: {},
  htmlSnapshot: null, meta: null, bornV: "1", resolvedV: null,
  resolveReason: null, ts: "08.09.2026 10:00", ...extra,
});

async function store(server) {
  globalThis.window = globalThis.window || {};
  await import(pathToFileURL(VENDOR).href);
  const s = globalThis.window.CommentLayerLocal({ endpoint: "/api/local-comments" });
  await s.ready;
  return s;
}

test("закритий на сервері пін не воскресає від запису вкладки", async () => {
  /* Дослівний сценарій фідбеку: вкладка відкрилась, коли всі піни були
     відкриті; далі Клод закрив два; далі дизайнер додав третій. */
  const server = fakeServer([pin("a"), pin("b")]);
  const s = await store(server);
  const seenByTab = s.load().map((c) => ({ ...c }));

  server.rows = [pin("a", { status: "resolved" }), pin("b", { status: "resolved" })];

  await s.save([...seenByTab, pin("c")]);

  const byId = Object.fromEntries(server.rows.map((c) => [c.id, c]));
  assert.equal(byId.a.status, "resolved", "пін a воскрес");
  assert.equal(byId.b.status, "resolved", "пін b воскрес");
  assert.ok(byId.c, "новий пін дизайнера не доїхав");
});

test("зміна, яку зробила сама вкладка, виграє над серверною версією", async () => {
  /* Зворотний бік: злиття не сміє знерухомити вкладку. Без цієї половини
     найпростіша «правка» — завжди лишати серверний стан — виглядала б як
     успіх, а закрити пін із коментатора стало б неможливо. */
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  const mine = s.load().map((c) => ({ ...c }));
  mine[0].status = "resolved";
  mine[0].resolveReason = "зробив";

  await s.save(mine);

  assert.equal(server.rows[0].status, "resolved", "закриття з вкладки не доїхало");
});

test("пін, створений на сервері після відкриття вкладки, не зникає", async () => {
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  const seen = s.load().map((c) => ({ ...c }));

  server.rows = [pin("a"), pin("z")];        // зʼявився поки вкладка жила
  await s.save([...seen, pin("c")]);

  const ids = server.rows.map((c) => c.id).sort();
  assert.deepEqual(ids, ["a", "c", "z"], `пін із сервера загубився: ${ids}`);
});

test("видалення лишається видаленням — злиття не воскрешає прибране", async () => {
  /* `remove` — це ЯВНИЙ намір вкладки, на відміну від «пін просто відсутній у
     моєму знімку». Саме цю різницю сервер із повного масиву й не бачив. */
  const server = fakeServer([pin("a"), pin("b")]);
  const s = await store(server);

  await s.remove(["a"]);

  assert.deepEqual(server.rows.map((c) => c.id), ["b"]);
});

test("пін, видалений на сервері ІНШОЮ вкладкою, не воскресає від запису цієї (ревʼю T-45, D2)", async () => {
  /* «Огляд» і живий вид — дві вкладки одного каналу. Живий вид видалив пін; «Огляд»
     його ще тримає в знімку й зберігає свій новий. Було: усе, чого нема на
     сервері, вважалось «новим піном вкладки» — видалений повертався. Тепер нове —
     лише те, чого не було і в БАЗІ вкладки. */
  const server = fakeServer([pin("a"), pin("victim")]);
  const s = await store(server);
  const seenByTab = s.load().map((c) => ({ ...c }));
  server.rows = [pin("a")];                       // інша вкладка видалила victim
  await s.save([...seenByTab, pin("fresh")]);
  const ids = server.rows.map((c) => c.id).sort();
  assert.deepEqual(ids, ["a", "fresh"], `видалений пін воскрес: ${ids}`);
});

test("видалений деінде, але ЗМІНЕНИЙ цією вкладкою — правка вкладки не губиться", async () => {
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  const edited = s.load().map((c) => ({ ...c, text: "уточнив" }));
  server.rows = [];
  await s.save(edited);
  assert.deepEqual(server.rows.map((c) => c.text), ["уточнив"]);
});

test("refresh перечитує сервер і сповіщає підписників", async () => {
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  let got = null;
  s.subscribe((list) => { got = list.map((c) => c.id); });
  server.rows = [pin("a"), pin("from-live-view")];
  await s.refresh();
  assert.deepEqual(got, ["a", "from-live-view"]);
  assert.deepEqual(s.load().map((c) => c.id), ["a", "from-live-view"]);
});

test("файл у «чужій» формі (без resolvedV, інший порядок ключів) — ні воскресіння, ні відкату закриття", async () => {
  /* Повторне ревʼю T-45: злиття порівнювало сиру базу з `clean()`-знімком, і для
     файла, який записав не цей адаптер, кожен пін здавався «зміненим вкладкою». */
  const raw = (id, extra = {}) => ({ status: "open", id, text: `пін ${id}`, author: "Lead", fp: {}, ...extra });
  const server = fakeServer([raw("a"), raw("victim"), raw("closed")]);
  const s = await store(server);
  const seen = s.load().map((c) => ({ ...c }));
  server.rows = [raw("a"), raw("closed", { status: "resolved" })];   // victim видалили, closed закрив Клод
  await s.save([...seen, pin("fresh")]);
  const byId = Object.fromEntries(server.rows.map((c) => [c.id, c]));
  assert.deepEqual(Object.keys(byId).sort(), ["a", "closed", "fresh"], "видалений воскрес");
  assert.equal(byId.closed.status, "resolved", "закриття Клодом відкотилось");
});

test("переякорення вкладкою не відкриває закритий на сервері пін (fb-30092026-423d00)", async () => {
  /* Дослівний механізм записки: Клод закрив пін з диска; коментатор у вкладці
     після правки макета переякорив УСІ свої відкриті піни (новий `fp`), і пін
     став «зміненим вкладкою» — тоді виграв її стан цілком, зі статусом open. */
  const server = fakeServer([pin("a"), pin("b")]);
  const s = await store(server);
  const seen = s.load().map((c) => ({ ...c }));

  server.rows = [
    pin("a", { status: "resolved", resolvedV: "3", resolveReason: "зроблено",
               meta: { resolvedAt: 111 } }),
    pin("b"),
  ];
  const reanchored = seen.map((c) => ({ ...c, fp: { tag: "div", path: ["main[0]"] } }));
  await s.save([...reanchored, pin("c")]);

  const byId = Object.fromEntries(server.rows.map((c) => [c.id, c]));
  assert.equal(byId.a.status, "resolved", "закриття з диска відкотилось");
  assert.equal(byId.a.resolveReason, "зроблено");
  assert.equal(byId.a.meta.resolvedAt, 111, "мітка закриття загубилась");
  assert.deepEqual(byId.a.fp, { tag: "div", path: ["main[0]"] }, "переякорення вкладки загубилось");
  assert.ok(byId.c, "новий пін не доїхав");
});

test("поле meta зливається по ключах: знімок із сервера не затирається переякоренням", async () => {
  const server = fakeServer([pin("a", { meta: { seq: 4 } })]);
  const s = await store(server);
  const seen = s.load().map((c) => ({ ...c }));
  server.rows = [pin("a", { meta: { seq: 4, shotUrl: "https://x/shot.jpg" } })];
  await s.save(seen.map((c) => ({ ...c, fp: { tag: "p" }, meta: { ...c.meta, sel: "нове" } })));
  const a = server.rows[0];
  assert.equal(a.meta.shotUrl, "https://x/shot.jpg", "серверний ключ meta затерто");
  assert.equal(a.meta.sel, "нове", "ключ meta, змінений вкладкою, загубився");
});

test("повторне відкриття у вкладці їде групою: статус, причина, мітка закриття", async () => {
  /* Зворотний бік групи полів: вкладка відкрила закритий пін — разом зі статусом
     мусять зникнути причина й мітка, інакше вийде «відкритий пін із причиною». */
  const closed = pin("a", { status: "resolved", resolvedV: "2", resolveReason: "ok",
                            meta: { resolvedAt: 5 } });
  const server = fakeServer([closed]);
  const s = await store(server);
  const mine = s.load().map((c) => {
    const meta = { ...c.meta }; delete meta.resolvedAt;
    return { ...c, status: "open", resolvedV: null, resolveReason: null, meta };
  });
  await s.save(mine);
  const a = server.rows[0];
  assert.equal(a.status, "open");
  assert.equal(a.resolveReason, null);
  assert.equal("resolvedAt" in (a.meta || {}), false, "мітка закриття лишилась на відкритому піні");
});

test("два save() внахлест не відкривають закритий на диску пін (ревʼю 1.47, D2)", async () => {
  /* Коментатор може дати серію save() поспіль (MutationObserver), і другий стартує,
     поки летить запис першого. Його GET приходить ПІСЛЯ запису першого, тобто база
     вже «закрито», а список вкладки — ще «відкрито»: злиття проти СВІЖОЇ бази
     прочитало б це як «вкладка відкрила пін». База — та, яку вкладка знала, коли
     ПОРОДИЛА список. */
  const server = fakeServer([pin("a")]);
  const realFetch = globalThis.fetch;
  let gets = 0;
  globalThis.fetch = async (url, opts) => {
    if (!opts || opts.method !== "POST") {
      gets += 1;
      if (gets === 3) await new Promise((r) => setTimeout(r, 50));   // GET другого save — повільний
    }
    return realFetch(url, opts);
  };
  const s = await store(server);
  const seen = s.load().map((c) => ({ ...c }));
  server.rows = [pin("a", { status: "resolved", resolvedV: "3", resolveReason: "ok", meta: { resolvedAt: 9 } })];
  await Promise.all([
    s.save(seen.map((c) => ({ ...c, fp: { tag: "p" } }))),
    s.save(seen.map((c) => ({ ...c, fp: { tag: "q" } }))),
  ]);
  assert.equal(server.rows[0].status, "resolved", "закриття відкотилось двома save() внахлест");
});
