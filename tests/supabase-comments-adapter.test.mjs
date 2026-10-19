/**
 * Адаптер вбудованого модуля `supabase-comments` (роль `comments`, 2b-2): `DeaiComments.create(cfg)` поверх
 * supabase-js — порт `CommentLayerSupabase` (форма рядків, upsert за `id` з повторами, видалення в межах каналу,
 * realtime → перечитування).
 *
 * Файл виконується в ізольованому `vm`-контексті з ПІДСТАВНИМ глобальним `supabase` (його справжня збірка — окремий
 * файл `supabase.min.js`, чужий код, приколотий хешем у `tests/test_supabase_comments.py`): жодної мережі, жодного
 * реального часу (`setTimeout` викликає зворотний виклик одразу й пише затримку). Підставний клієнт записує КОЖЕН
 * ланцюжок викликів: `from().select().eq().order()`, `upsert`, `delete().in().eq()`, `channel().on().subscribe()`,
 * `removeChannel`.
 */
import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const FILE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "modules", "supabase-comments", "adapter.js");
const SRC = fs.readFileSync(FILE, "utf8");

const URL = "https://abcdefghijkl.supabase.co";
const KEY = "eyJhbGciOiJIUzI1NiJ9.TEST-payload.TEST-signature";
const CHANNEL = "deai/space-1/task-7";

/** Рядок таблиці `comments` так, як його віддає PostgREST (snake_case + службові колонки). */
const row = (id, over = {}) => ({
  id, project_id: CHANNEL, author: "Олена", text: `текст ${id}`, status: "open", fp: { tag: "button", path: ["div[1]"] },
  html_snapshot: { text: "Купити", outerHTML: "<button>Купити</button>" }, meta: { version: "2/x", seq: 3 },
  born_v: 2, resolved_v: null, resolve_reason: null, ts: "19.10.2026 10:00", created_at: "2026-10-19T10:00:00Z", ...over,
});
/** Той самий коментар у формі CommentLayer — те, що чекає сховище. */
const pin = (id, over = {}) => ({
  id, author: "Олена", text: `текст ${id}`, status: "open", fp: { tag: "button", path: ["div[1]"] },
  htmlSnapshot: { text: "Купити", outerHTML: "<button>Купити</button>" }, meta: { version: "2/x", seq: 3 },
  bornV: 2, resolvedV: null, resolveReason: null, ts: "19.10.2026 10:00", ...over,
});
/* Об'єкти з `vm`-контексту мають СВІЙ `Object.prototype`: `deepStrictEqual` порівняв би прототипи. Звідси — копії. */
const plain = (x) => JSON.parse(JSON.stringify(x));
const settle = () => new Promise((r) => setImmediate(r));

/**
 * Світ: `opts.rows` — що віддає SELECT (масив або функція від номера запиту), `failSelect`, `failUpserts` (перші N
 * upsert-ів падають), `failDelete`. Результат: `sandbox`, `calls` (усі запити в порядку виклику), `channels`,
 * `removedChannels`, `created` (аргументи `createClient`), `delays` (затримки `setTimeout`), `warnings`, `logs`.
 */
function world(opts = {}) {
  const w = { calls: [], channels: [], removedChannels: [], created: [], delays: [], warnings: [], logs: [], selects: 0 };
  w.opts = { rows: [], failSelect: false, failUpserts: 0, failDelete: false, ...opts };
  const reply = (v) => ({ then: (res, rej) => Promise.resolve(v).then(res, rej) });   // thenable, як у PostgREST-білдера

  const client = {
    from(table) {
      return {
        select(cols) {
          const q = { op: "select", table, cols, filters: [], order: null };
          w.calls.push(q);
          const n = w.selects++;
          const b = {
            eq(col, val) { q.filters.push(["eq", col, val]); return b; },
            order(col) { q.order = col; return b; },
            then(res, rej) {
              const rows = typeof w.opts.rows === "function" ? w.opts.rows(n) : w.opts.rows;
              const out = w.opts.failSelect
                ? { data: null, error: { message: "select boom" } }
                : { data: rows, error: null };
              return Promise.resolve(out).then(res, rej);
            },
          };
          return b;
        },
        upsert(rows, o) {
          w.calls.push({ op: "upsert", table, rows, opts: o });
          const fail = w.opts.failUpserts > 0;
          if (fail) w.opts.failUpserts -= 1;
          return reply({ data: null, error: fail ? { message: "upsert boom" } : null });
        },
        delete() {
          const q = { op: "delete", table, filters: [] };
          w.calls.push(q);
          const b = {
            in(col, vals) { q.filters.push(["in", col, vals]); return b; },
            eq(col, val) { q.filters.push(["eq", col, val]); return b; },
            then(res, rej) {
              return Promise.resolve({ error: w.opts.failDelete ? { message: "delete boom" } : null }).then(res, rej);
            },
          };
          return b;
        },
      };
    },
    channel(name) {
      const ch = { name, handlers: [], subscribed: 0 };
      ch.on = (type, filter, cb) => { ch.handlers.push({ type, filter, cb }); return ch; };
      ch.subscribe = () => { ch.subscribed += 1; return ch; };
      w.channels.push(ch);
      return ch;
    },
    removeChannel(ch) { w.removedChannels.push(ch); return Promise.resolve("ok"); },
  };

  const sandbox = {
    supabase: { createClient: (url, key) => { w.created.push([url, key]); return client; } },
    setTimeout: (fn, ms) => { w.delays.push(ms); fn(); return 1; },
    console: { warn: (...a) => w.warnings.push(a.join(" ")), log: (...a) => w.logs.push(a.join(" ")), error: (...a) => w.logs.push(a.join(" ")) },
  };
  sandbox.window = sandbox;                               // `window.DeaiComments = …` у браузері — глобальний обʼєкт
  w.before = new Set(Object.keys(sandbox));
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: FILE });
  w.sandbox = sandbox;
  w.create = (cfg = {}) => sandbox.DeaiComments.create({ url: URL, key: KEY, channel: CHANNEL, ...cfg });
  w.selectCalls = () => w.calls.filter((c) => c.op === "select");
  return w;
}

test("файл реєструє лише window.DeaiComments.create і не створює інших глобальних імен", () => {
  const w = world();
  assert.deepEqual([...Object.keys(w.sandbox)].filter((k) => !w.before.has(k)), ["DeaiComments"]);
  assert.deepEqual(Object.keys(w.sandbox.DeaiComments), ["create"]);
  assert.equal(typeof w.sandbox.DeaiComments.create, "function");
});

test("без supabase-js адаптер не мовчить: create кидає зрозумілу помилку, а не TypeError з нічого", () => {
  const w = world();
  delete w.sandbox.supabase;
  assert.throws(() => w.create(), /supabase-js/);
  w.sandbox.supabase = {};
  assert.throws(() => w.create(), /supabase-js/);
});

test("create: createClient(url, key) рівно раз, SELECT * з фільтром каналу й порядком за id; ready чекає на нього", async () => {
  const w = world({ rows: [row("b"), row("a")] });
  const s = w.create();
  assert.deepEqual(w.created, [[URL, KEY]]);
  assert.deepEqual(plain(s.load()), [], "до ready кешу ще нема");
  await s.ready;
  const sel = w.selectCalls();
  assert.equal(sel.length, 1);
  assert.deepEqual(plain(sel[0]), { op: "select", table: "comments", cols: "*", filters: [["eq", "project_id", CHANNEL]], order: "id" });
  assert.deepEqual(s.load().map((c) => c.id), ["b", "a"], "порядок — як віддав сервер (order=id робить він)");
  assert.deepEqual(Object.keys(s).sort(), ["close", "load", "ready", "remove", "save", "subscribe"]);
});

test("rowToComment: рівно 11 полів CommentLayer; project_id і created_at лишаються в базі; null → null", async () => {
  const w = world({ rows: [row("a"), row("b", { html_snapshot: null, meta: null, resolved_v: 5, resolve_reason: "готово", status: "resolved" })] });
  const s = w.create();
  await s.ready;
  const [a, b] = plain(s.load());
  assert.deepEqual(a, pin("a"));
  assert.deepEqual(Object.keys(a).sort(), ["author", "bornV", "fp", "htmlSnapshot", "id", "meta", "resolveReason", "resolvedV", "status", "text", "ts"]);
  assert.deepEqual(b, pin("b", { htmlSnapshot: null, meta: null, resolvedV: 5, resolveReason: "готово", status: "resolved" }));
});

test("fetchAll: порожня відповідь дає порожній кеш; помилка запиту лишає попередній кеш і попереджає без ключа", async () => {
  const w = world({ rows: null });
  const s = w.create();
  await s.ready;
  assert.deepEqual(plain(s.load()), [], "data: null → порожньо");
  const w2 = world({ rows: [row("a")] });
  const s2 = w2.create();
  await s2.ready;
  w2.opts.failSelect = true;
  w2.channels[0].handlers[0].cb();
  await settle();
  assert.deepEqual(s2.load().map((c) => c.id), ["a"], "збій не стирає кеш");
  assert.ok(w2.warnings.some((m) => m.includes("select boom")));
  for (const m of [...w2.warnings, ...w2.logs]) assert.ok(!m.includes(KEY), "ключ у консолі");
});

test("save: upsert з onConflict:id, рядки у формі commentToRow із project_id = канал; кеш оновлюється", async () => {
  const w = world();
  const s = w.create();
  await s.ready;
  const full = pin("a", { resolvedV: 4, resolveReason: "ok", status: "resolved" });
  const bare = pin("b", { htmlSnapshot: undefined, meta: undefined, resolvedV: 0, resolveReason: "", ts: "", bornV: 7 });
  await s.save([full, bare]);
  const up = w.calls.filter((c) => c.op === "upsert");
  assert.equal(up.length, 1);
  assert.deepEqual(plain(up[0].opts), { onConflict: "id" });
  assert.equal(up[0].table, "comments");
  assert.deepEqual(plain(up[0].rows), [
    { id: "a", project_id: CHANNEL, author: "Олена", text: "текст a", status: "resolved", fp: full.fp, html_snapshot: full.htmlSnapshot,
      meta: full.meta, born_v: 2, resolved_v: 4, resolve_reason: "ok", ts: "19.10.2026 10:00" },
    { id: "b", project_id: CHANNEL, author: "Олена", text: "текст b", status: "open", fp: bare.fp, html_snapshot: null,
      meta: null, born_v: 7, resolved_v: null, resolve_reason: null, ts: null },
  ]);
  assert.deepEqual(s.load().map((c) => c.id), ["a", "b"]);
});

test("save: канал береться з cfg, а не з коментаря (чужий project_id у вхідних даних ігнорується)", async () => {
  const w = world();
  const s = w.create({ channel: "deai/other/task" });
  await s.ready;
  await s.save([{ ...pin("a"), project_id: "deai/victim/task" }]);
  assert.equal(w.calls.find((c) => c.op === "upsert").rows[0].project_id, "deai/other/task");
});

test("save: два збої підряд — третя спроба вдала; затримки 300 і 600 мс; не кидає", async () => {
  const w = world({ failUpserts: 2 });
  const s = w.create();
  await s.ready;
  await s.save([pin("a")]);
  assert.equal(w.calls.filter((c) => c.op === "upsert").length, 3);
  assert.deepEqual(w.delays, [300, 600]);
  assert.deepEqual(s.load().map((c) => c.id), ["a"]);
});

test("save: після трьох збоїв — відмова з текстом сервісу (без ключа), рівно 3 спроби й без марного очікування після останньої, кеш оптимістичний", async () => {
  const w = world({ failUpserts: 99 });
  const s = w.create();
  await s.ready;
  await assert.rejects(s.save([pin("a")]), (e) => e.name === "Error" && /supabase save failed: upsert boom/.test(e.message) && !e.message.includes(KEY));
  assert.equal(w.calls.filter((c) => c.op === "upsert").length, 3);
  assert.deepEqual(w.delays, [300, 600], "після останньої невдалої спроби чекати нема чого");
  assert.deepEqual(s.load().map((c) => c.id), ["a"], "локальний кеш не губить запис, який SDK ще повторить сам");
  assert.ok(w.warnings.some((m) => m.includes("upsert boom")));
  for (const m of [...w.warnings, ...w.logs]) assert.ok(!m.includes(KEY), "ключ у консолі");
});

test("remove: delete().in('id', ids).eq('project_id', канал) — ОБИДВА фільтри; кеш чиститься", async () => {
  const w = world({ rows: [row("a"), row("b"), row("c")] });
  const s = w.create();
  await s.ready;
  await s.remove(["a", "c"]);
  const del = w.calls.filter((c) => c.op === "delete");
  assert.equal(del.length, 1);
  assert.deepEqual(plain(del[0]), { op: "delete", table: "comments", filters: [["in", "id", ["a", "c"]], ["eq", "project_id", CHANNEL]] });
  assert.deepEqual(s.load().map((c) => c.id), ["b"]);
});

test("remove: порожній список не робить запиту; помилка видалення — попередження, а не відмова", async () => {
  const w = world({ rows: [row("a")], failDelete: true });
  const s = w.create();
  await s.ready;
  await s.remove([]);
  await s.remove(undefined);
  assert.equal(w.calls.filter((c) => c.op === "delete").length, 0);
  await s.remove(["a"]);                                           // не кидає
  assert.equal(w.calls.filter((c) => c.op === "delete").length, 1);
  assert.ok(w.warnings.some((m) => m.includes("delete boom")));
  assert.deepEqual(s.load().map((c) => c.id), [], "як у CommentLayerSupabase: кеш чиститься і при збої");
});

test("realtime: канал cl-<канал>, postgres_changes на comments БЕЗ фільтра project_id, subscribe рівно раз", async () => {
  const w = world();
  const s = w.create();
  await s.ready;
  assert.equal(w.channels.length, 1);
  const ch = w.channels[0];
  assert.equal(ch.name, "cl-" + CHANNEL);
  assert.equal(ch.subscribed, 1);
  assert.equal(ch.handlers.length, 1);
  assert.equal(ch.handlers[0].type, "postgres_changes");
  /* Фільтра project_id тут нема навмисно: події DELETE несуть лише PK, і фільтр мовчки губив би видалення. Канал
     звужує перечитування (`fetchAll` з фільтром каналу), а не підписка. */
  assert.deepEqual(plain(ch.handlers[0].filter), { event: "*", schema: "public", table: "comments" });
});

test("подія realtime → перечитування каналу → onChange з cfg і підписники отримують новий масив", async () => {
  let n = 0;
  const w = world({ rows: () => (n++ === 0 ? [row("a")] : [row("a"), row("b")]) });
  const seenCfg = [];
  const seenSub = [];
  const s = w.create({ onChange: (c) => seenCfg.push(c.map((x) => x.id)) });
  s.subscribe((c) => seenSub.push(c.map((x) => x.id)));
  await s.ready;
  assert.deepEqual(seenCfg, [["a"]], "перше завантаження теж повідомляє");
  assert.deepEqual(seenSub, [["a"]]);
  w.channels[0].handlers[0].cb({ eventType: "INSERT" });
  await settle();
  assert.equal(w.selectCalls().length, 2);
  assert.deepEqual(w.selectCalls()[1].filters, [["eq", "project_id", CHANNEL]], "перечитування — у межах каналу");
  assert.deepEqual(seenCfg.at(-1), ["a", "b"]);
  assert.deepEqual(seenSub.at(-1), ["a", "b"]);
  assert.deepEqual(s.load().map((c) => c.id), ["a", "b"]);
});

test("subscribe: не функція ігнорується; підписник, що кидає, не валить решту", async () => {
  const w = world({ rows: [row("a")] });
  const s = w.create();
  s.subscribe(null);
  s.subscribe("x");
  const got = [];
  s.subscribe(() => { throw new Error("boom"); });
  s.subscribe((c) => got.push(c.length));
  await s.ready;
  assert.deepEqual(got, [1]);
});

test("перечитування не плутається у порядку: пізня відповідь на старіший запит не затирає свіжішу", async () => {
  const waits = [];
  const w = world();
  /* Власний підставний клієнт: SELECT-и вирішуємо вручну в потрібному порядку. */
  const pending = [];
  w.sandbox.supabase.createClient = () => ({
    from: () => ({ select: () => { const b = { eq: () => b, order: () => b, then: (res, rej) => new Promise((r) => pending.push(r)).then(res, rej) }; return b; } }),
    channel: () => { const ch = { on: (t, f, cb) => { waits.push(cb); return ch; }, subscribe: () => ch }; return ch; },
    removeChannel: () => Promise.resolve(),
  });
  const s = w.create();
  waits[0]();                                                         // другий SELECT, поки перший ще в дорозі
  await settle();
  assert.equal(pending.length, 2);
  pending[1]({ data: [row("fresh")], error: null });
  await settle();
  assert.deepEqual(s.load().map((c) => c.id), ["fresh"]);
  pending[0]({ data: [row("stale")], error: null });
  await settle();
  assert.deepEqual(s.load().map((c) => c.id), ["fresh"], "стара відповідь відкинута");
});

test("close: removeChannel(канал) рівно раз, підписники відпущені, пізня подія нічого не перечитує й не повідомляє; повторний close — нічого", async () => {
  const w = world({ rows: [row("a")] });
  const seen = [];
  const s = w.create({ onChange: (c) => seen.push(c.length) });
  s.subscribe((c) => seen.push(c.length));
  await s.ready;
  const before = seen.length;
  s.close();
  assert.deepEqual(w.removedChannels, [w.channels[0]]);
  w.channels[0].handlers[0].cb();
  await settle();
  assert.equal(w.selectCalls().length, 1, "після close перечитувань нема");
  assert.equal(seen.length, before, "після close повідомлень нема");
  s.close();
  assert.equal(w.removedChannels.length, 1, "повторний close не знімає канал удруге");
});

test("close під час польоту SELECT: відповідь, що прийшла після нього, нікого не повідомляє", async () => {
  const w = world();
  const pending = [];
  w.sandbox.supabase.createClient = () => ({
    from: () => ({ select: () => { const b = { eq: () => b, order: () => b, then: (res, rej) => new Promise((r) => pending.push(r)).then(res, rej) }; return b; } }),
    channel: () => { const ch = { on: () => ch, subscribe: () => ch }; return ch; },
    removeChannel: () => Promise.resolve(),
  });
  const seen = [];
  const s = w.create({ onChange: (c) => seen.push(c.length) });
  await settle();
  assert.equal(pending.length, 1);
  s.close();
  pending[0]({ data: [row("a")], error: null });
  await settle();
  assert.deepEqual(seen, []);
});

test("ключ іде лише в createClient: адаптер його ніде не друкує й не зберігає в глобальних іменах", async () => {
  const w = world({ rows: [row("a")], failUpserts: 99, failDelete: true });
  const s = w.create();
  await s.ready;
  await s.save([pin("a")]).catch(() => {});
  await s.remove(["a"]);
  s.close();
  for (const m of [...w.warnings, ...w.logs]) assert.ok(!m.includes(KEY), m);
  assert.ok(!SRC.includes("localStorage") && !SRC.includes("document.cookie"), "адаптер не пише ключ у сховище браузера");
  assert.ok(!/\bfetch\s*\(/.test(SRC) && !/XMLHttpRequest/.test(SRC), "мережею ходить лише supabase-js");
});
