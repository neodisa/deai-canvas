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

/** Сервер у памʼяті: віддає свій список і приймає повний масив, як справжній.
 *  ⛔ Віддає СВІЖУ КОПІЮ, як справжній `fetch`: віддача `state.rows` за
 *  посиланням ховала спільні масиви між адаптером і шаром (fb 05.11.2026). */
function fakeServer(initial) {
  const state = { rows: initial.map((c) => ({ ...c })), writes: 0 };
  globalThis.fetch = async (url, opts) => {
    if (!opts || opts.method !== "POST") {
      const copy = JSON.parse(JSON.stringify(state.rows));
      return { ok: true, json: async () => ({ comments: copy }) };
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

/* ── fb 05.11.2026: піни на React-сторінці не доходили до файла ───────────────
   Шар (`comment-layer`) кладе отримані від адаптера обʼєкти у `this.comments` і
   вішає на них `c._el` — DOM-вузол якоря. На React-сторінці у вузла є
   `__reactFiber$…`, а файбер посилається назад через `stateNode`: кільце.
   Адаптер серіалізував ТІ САМІ обʼєкти, що віддав шару, — `JSON.stringify`
   падав, POST не йшов, пін жив лише в памʼяті вікна. На сторінках без React
   те саме проходило мовчки, і `_el` осідав у файлах 21 задачі. */

/** Вузол із кільцем, як у React: вузол → файбер → stateNode → вузол. */
function reactNode() {
  const el = { tagName: "SECTION" };
  el.__reactFiber$x = { stateNode: el };
  return el;
}
/** Шар коментаря в мініатюрі: тримає те, що дав адаптер, і чіпляє якорі. */
function fakeLayer(s) {
  const layer = { comments: s.load() };
  const anchor = (list) => { for (const c of list) c._el = reactNode(); };
  anchor(layer.comments);
  s.subscribe((list) => { layer.comments = list; anchor(list); });
  return layer;
}

test("пін на React-сторінці доходить до файла, а `_el` у файл не потрапляє", async () => {
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  const layer = fakeLayer(s);

  await s.save([...layer.comments, pin("new")]);

  const ids = server.rows.map((c) => c.id).sort();
  assert.deepEqual(ids, ["a", "new"], `пін не доїхав: ${ids}`);
  for (const c of server.rows) assert.equal("_el" in c, false, `_el у файлі (${c.id})`);
  /* Другий save — уже з обʼєктами, що адаптер віддав шару після запису. */
  await s.save([...layer.comments, pin("second")]);
  assert.deepEqual(server.rows.map((c) => c.id).sort(), ["a", "new", "second"]);
});

test("новий пін, дописаний прямо в масив із load(), не губиться при злитті", async () => {
  /* Шар бере `this.comments = store.load()` і дописує новий пін у той самий
     масив. Коли масив адаптера = його база, новий пін опинявся «у базі», а на
     сервері його нема → злиття вважало його видаленим іншою вкладкою. Досі
     рятувало лише те, що `_el` робив рядки різними. */
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  const list = s.load();
  list.push(pin("pushed"));

  await s.save(list);

  assert.deepEqual(server.rows.map((c) => c.id).sort(), ["a", "pushed"], "дописаний пін загубився");
});

test("remove при недоступному GET пише видалення, навіть коли в кеші якорі з кільцем", async () => {
  const server = fakeServer([pin("a"), pin("b")]);
  const s = await store(server);
  fakeLayer(s);
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, opts) => {
    if (!opts || opts.method !== "POST") throw new Error("offline");
    return realFetch(url, opts);
  };

  await s.remove(["a"]);

  assert.deepEqual(server.rows.map((c) => c.id), ["b"], "видалення не записалось");
  assert.equal("_el" in server.rows[0], false, "_el у файлі");
});

test("remove і save підряд без await: видалений пін не повертається (fb 05.11.2026, гонка)", async () => {
  /* Коментатор у `removeComment` кличе `store.remove([id])`, а одразу за ним
     `_persist()` → `store.save(list)`, не чекаючи першого. Обидва GET приходили
     ДО обох POST: `remove` писав сервер мінус id, а злиття `save` бачило пін на
     сервері, не бачило у вкладці — і лишало його як «вкладка не чіпала». Хто
     з двох POST останній, той і виграв: видалення спрацьовувало через раз. */
  const server = fakeServer([pin("a"), pin("b")]);
  const realFetch = globalThis.fetch;
  /* Мережа, як у браузері: сервер читає файл, коли ПРИЙНЯВ GET, а відповідь
     доходить за кілька мс. Тож без черги обидва GET бачать пін — дослівна
     послідовність зі звіту. (Знімок у момент ВІДПОВІДІ гонку б ховав.) */
  globalThis.fetch = async (url, opts) => {
    const res = await realFetch(url, opts);
    if (!opts || opts.method !== "POST") await new Promise((r) => setTimeout(r, 5));
    return res;
  };
  const s = await store(server);
  const left = s.load().filter((c) => c.id !== "a").map((c) => ({ ...c }));

  await Promise.all([s.remove(["a"]), s.save(left)]);
  assert.deepEqual(server.rows.map((c) => c.id), ["b"], "видалений пін повернувся злиттям save()");

  /* І в зворотному порядку: save, а за ним remove. */
  const left2 = s.load().map((c) => ({ ...c }));
  await Promise.all([s.save([...left2, pin("c")]), s.remove(["b"])]);
  assert.deepEqual(server.rows.map((c) => c.id), ["c"], "remove після save не втримався");
});

test("впалий запис не зупиняє чергу: наступний save доходить", async () => {
  const server = fakeServer([pin("a")]);
  const realFetch = globalThis.fetch;
  let failNext = true;
  globalThis.fetch = async (url, opts) => {
    if (opts && opts.method === "POST" && failNext) { failNext = false; return { ok: false, json: async () => ({}) }; }
    return realFetch(url, opts);
  };
  const s = await store(server);
  const seen = s.load().map((c) => ({ ...c }));

  await assert.rejects(s.save([...seen, pin("lost")]));
  await s.save([...seen, pin("next")]);

  assert.ok(server.rows.some((c) => c.id === "next"), "після впалого запису черга стала");
});

/* ---------- Відповіді піна (0.35) ---------- */
const reply = (id, ts, extra = {}) => ({ id, author: "Lead", text: `відповідь ${id}`, ts, ...extra });
const copyOf = (s) => s.load().map((c) => JSON.parse(JSON.stringify(c)));

test("replies переживають save/load: файл → вкладка → файл", async () => {
  const r = reply("r1", "20.11.2026 10:00", { editedTs: "20.11.2026 10:05", agent: true });
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  await s.save([{ ...copyOf(s)[0], replies: [r] }]);
  assert.deepEqual(server.rows[0].replies, [r]);
  await s.refresh();
  assert.deepEqual(copyOf(s)[0].replies, [r]);
});

test("clean: зайві поля відповіді відкинуто, agent:true лишається, agent:false — ні, спадок без id дослівно, не-обʼєкти геть", async () => {
  const legacy = { who: "claude", body: "старий формат", n: [1, { z: 2 }] };
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  await s.save([copyOf(s)[0], { ...pin("n"), replies: [
    { ...reply("r1", "20.11.2026 10:00", { agent: true }), _pending: true, junk: 1 },
    reply("r2", "20.11.2026 10:01", { agent: false }),
    legacy, "рядок", 7, null,
  ] }]);
  assert.deepEqual(server.rows[1].replies, [
    reply("r1", "20.11.2026 10:00", { agent: true }),
    reply("r2", "20.11.2026 10:01"),
    legacy,
  ]);
  assert.equal("agent" in server.rows[1].replies[1], false);
  await s.save([...copyOf(s), { ...pin("m"), replies: "не масив" }, { ...pin("e"), replies: [] }]);
  assert.equal("replies" in server.rows[2], false, "не-масив має прибрати ключ");
  assert.equal("replies" in server.rows[3], false, "порожній масив — теж");
});

test("одночасно: агент дописав A на диск, вкладка додала B — обидві, за ts", async () => {
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  const seen = copyOf(s);
  server.rows = [pin("a", { replies: [reply("A", "20.11.2026 10:00", { agent: true })] })];
  await s.save([{ ...seen[0], replies: [reply("B", "20.11.2026 11:00")] }]);
  assert.deepEqual(server.rows[0].replies.map((r) => r.id), ["A", "B"]);
  server.rows = [pin("a", { replies: [reply("A", "20.11.2026 12:00", { agent: true })] })];
  await s.refresh();
  const seen2 = copyOf(s);
  server.rows[0].replies.push(reply("C", "20.11.2026 09:00", { agent: true }));
  await s.save([{ ...seen2[0], replies: [...seen2[0].replies, reply("D", "20.11.2026 10:30")] }]);
  assert.deepEqual(server.rows[0].replies.map((r) => r.id), ["C", "D", "A"], "порядок за ts");
});

test("вкладка прибрала відповідь, яку знала, а на диску вона ще є — її нема", async () => {
  const server = fakeServer([pin("a", { replies: [reply("r1", "20.11.2026 10:00"), reply("r2", "20.11.2026 10:01")] })]);
  const s = await store(server);
  const seen = copyOf(s);
  await s.save([{ ...seen[0], replies: [seen[0].replies[1]] }]);
  assert.deepEqual(server.rows[0].replies.map((r) => r.id), ["r2"]);
  await s.save([{ ...copyOf(s)[0], replies: undefined }]);
  assert.equal("replies" in server.rows[0], false, "порожній результат — без ключа");
});

test("відповідь на диску, якої вкладка не знала, лишається, коли вкладка міняє лише текст піна", async () => {
  const server = fakeServer([pin("a")]);
  const s = await store(server);
  const seen = copyOf(s);
  server.rows = [pin("a", { replies: [reply("A", "20.11.2026 10:00", { agent: true })] })];
  await s.save([{ ...seen[0], text: "нова правка" }]);
  assert.equal(server.rows[0].text, "нова правка");
  assert.deepEqual(server.rows[0].replies.map((r) => r.id), ["A"]);
});

test("вкладка правила текст відповіді R, диск не мінявся — правка виграє", async () => {
  const server = fakeServer([pin("a", { replies: [reply("R", "20.11.2026 10:00")] })]);
  const s = await store(server);
  const seen = copyOf(s);
  const edited = { ...seen[0].replies[0], text: "виправлено", editedTs: "20.11.2026 10:30" };
  await s.save([{ ...seen[0], replies: [edited] }]);
  assert.equal(server.rows[0].replies[0].text, "виправлено");
  assert.equal(server.rows[0].replies[0].editedTs, "20.11.2026 10:30");
});

test("спадковий запис без id на диску переживає відповідь вкладки, лишаючись попереду", async () => {
  const legacy = { who: "claude", body: "від попередника" };
  const server = fakeServer([pin("a", { replies: [legacy] })]);
  const s = await store(server);
  const seen = copyOf(s);
  await s.save([{ ...seen[0], replies: [...seen[0].replies, reply("B", "20.11.2026 10:00")] }]);
  assert.deepEqual(server.rows[0].replies, [legacy, reply("B", "20.11.2026 10:00")]);
});

test("зміна лише replies викликає запис; незмінений пін лишає сирі replies сервера", async () => {
  const server = fakeServer([pin("a"), pin("b")]);
  const s = await store(server);
  const seen = copyOf(s);
  const w0 = server.writes;
  await s.save([{ ...seen[0], replies: [reply("B", "20.11.2026 10:00")] }, seen[1]]);
  assert.equal(server.writes, w0 + 1);
  assert.equal(server.rows[0].replies.length, 1);
  // Незмінений пін b: на диску сирі replies у «чужій» формі — не чіпаємо.
  const raw = [{ ts: 5, anything: true }, { id: "x", text: "t", extraField: 1 }];
  server.rows[1] = { ...server.rows[1], replies: raw };
  await s.refresh();
  const seen2 = copyOf(s);
  await s.save([{ ...seen2[0], text: "інша" }, seen2[1]]);
  assert.deepEqual(server.rows[1].replies, raw);
});

test("відповідь, видалена на диску, не воскресає, коли вкладка додає іншу (ревʼю T5)", async () => {
  const server = fakeServer([pin("a", { replies: [reply("X", "20.11.2026 10:00"), reply("Y", "20.11.2026 10:01")] })]);
  const s = await store(server);
  const seen = copyOf(s);
  server.rows = [pin("a", { replies: [reply("Y", "20.11.2026 10:01")] })];   // X видалили на диску
  await s.save([{ ...seen[0], replies: [...seen[0].replies, reply("Z", "20.11.2026 10:02")] }]);
  assert.deepEqual(server.rows[0].replies.map((r) => r.id), ["Y", "Z"]);
});

test("runtime-поля коментатора на обʼєктах із load() не доходять до POST (_goneReplies, reply._pending)", async () => {
  const server = fakeServer([pin("a", { replies: [reply("R", "20.11.2026 10:00")] })]);
  const s = await store(server);
  const live = s.load()[0];                       // коментатор мутує саме ці обʼєкти
  live._goneReplies = { r9: 1 };
  live._pending = true;
  live.replies[0]._pending = true;
  live.replies.push({ ...reply("N", "20.11.2026 10:05"), _pending: true });
  let body = null;
  const orig = globalThis.fetch;
  globalThis.fetch = async (url, opts) => { if (opts && opts.method === "POST") body = opts.body; return orig(url, opts); };
  await s.save(s.load());
  assert.ok(body, "POST не було");
  assert.equal(body.includes("_goneReplies"), false);
  assert.equal(body.includes("_pending"), false);
  assert.deepEqual(server.rows[0].replies.map((r) => r.id), ["R", "N"]);
});

/* ---- uploadShot (0.35.1): повний знімок локального піна → файл поруч із задачею ---- */
async function shotStore(opts) {
  globalThis.window = globalThis.window || {};
  await import(pathToFileURL(VENDOR).href);
  const s = globalThis.window.CommentLayerLocal(opts);
  await s.ready;
  return s;
}
function fakeShotFetch(reply) {
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    if (opts && opts.method === "POST" && String(url).includes("/api/local-shots")) {
      calls.push({ url: String(url), opts });
      return reply(calls.length);
    }
    return { ok: true, json: async () => ({ comments: [] }) };
  };
  return calls;
}
const ok = (url) => async () => ({ ok: true, json: async () => ({ ok: true, url }) });

test("uploadShot: POST {id, dataUrl} на shotsEndpoint, абсолютна адреса у відповіді", async () => {
  const calls = fakeShotFetch(ok("/api/local-shots/p1.jpg"));
  const s = await shotStore({ endpoint: "http://127.0.0.1:9/api/local-comments", shotsEndpoint: "http://127.0.0.1:9/api/local-shots" });
  const url = await s.uploadShot("p1", "data:image/jpeg;base64,/9j/AA==", { _aud: "local" });
  assert.equal(url, "http://127.0.0.1:9/api/local-shots/p1.jpg");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://127.0.0.1:9/api/local-shots");
  assert.deepEqual(JSON.parse(calls[0].opts.body), { id: "p1", dataUrl: "data:image/jpeg;base64,/9j/AA==" });
  assert.equal(calls[0].opts.headers["Content-Type"], "application/json");
});

test("uploadShot: shotsEndpoint виводиться з endpoint (хвіст /api/local-comments і query замінюються)", async () => {
  for (const [ep, want] of [
    ["http://127.0.0.1:9/api/local-comments", "http://127.0.0.1:9/api/local-shots"],
    ["http://127.0.0.1:9/api/local-comments?k=1", "http://127.0.0.1:9/api/local-shots"],
    ["http://127.0.0.1:9/t/beta/api/local-comments", "http://127.0.0.1:9/t/beta/api/local-shots"],
  ]) {
    const calls = fakeShotFetch(ok("/api/local-shots/p1.jpg"));
    const s = await shotStore({ endpoint: ep });
    await s.uploadShot("p1", "data:image/jpeg;base64,AA==");
    assert.equal(calls[0].url, want);
  }
});

test("uploadShot: збій мережі, ok:false, відповідь без url, сміття — null, без винятку", async () => {
  const replies = [
    async () => { throw new Error("offline"); },
    async () => ({ ok: false, status: 413, json: async () => ({ ok: false }) }),
    async () => ({ ok: true, json: async () => ({ ok: true }) }),
    async () => ({ ok: true, json: async () => { throw new Error("not json"); } }),
    async () => ({ ok: true, json: async () => ({ ok: true, url: 42 }) }),
  ];
  for (const r of replies) {
    fakeShotFetch(r);
    const s = await shotStore({ endpoint: "http://127.0.0.1:9/api/local-comments" });
    assert.equal(await s.uploadShot("p1", "data:image/jpeg;base64,AA=="), null);
  }
});
