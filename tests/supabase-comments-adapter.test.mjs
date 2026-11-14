/**
 * Адаптер вбудованого модуля `supabase-comments` (роль `comments`, 2b-2): `DeaiComments.create(cfg)` поверх
 * supabase-js — порт `CommentLayerSupabase` (форма рядків, upsert за `id` з повторами, видалення в межах каналу,
 * realtime → перечитування).
 *
 * Файл виконується в ізольованому `vm`-контексті з ПІДСТАВНИМ глобальним `supabase` (його справжня збірка — окремий
 * файл `supabase.min.js`, чужий код, приколотий хешем у `tests/test_supabase_comments.py`; з нею адаптер ганяє
 * `tests/supabase-comments-bundle.test.mjs`): жодної мережі, жодного реального часу. Таймери — черга: `w.runTimers()`
 * виконує те, що чекає (повтори запису, згладжування realtime), `drive(w, promise)` крутить їх, доки проміс не завершиться.
 * Підставний клієнт записує КОЖЕН ланцюжок викликів: `from().select().eq().order()`, `upsert`, `delete().in().eq()`,
 * `channel().on().subscribe()`, `removeChannel`, `realtime.disconnect`.
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
const AUTH_OFF = { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } };

/**
 * Світ. Параметри: `rows` — що віддає SELECT (масив або функція від номера запиту); `failSelect` (відповідь із помилкою),
 * `rejectSelect` (запит ВІДХИЛЯЄТЬСЯ), `manualSelect` (SELECT-и чекають: `w.pendingSelects[i]({data, error})`), `failUpserts`
 * (перші N upsert-ів падають), `failDelete`, `removeChannel` (`"ok"` | `"reject"` | `"throw"`), `disconnect` (`"ok"` | `"throw"`),
 * `upload` (відповідь підставного `fetch` на завантаження скріншота: `"ok"` | `"fail"` | `"reject"`).
 * Результат: `sandbox`, `calls`, `channels`, `removedChannels`, `disconnects`, `created`, `delays` (затримки всіх таймерів),
 * `timers`, `warnings`, `logs`.
 */
function world(opts = {}) {
  const w = {
    calls: [], fetches: [], channels: [], removedChannels: [], disconnects: 0, created: [], delays: [], warnings: [], logs: [], selects: 0,
    timers: [], nextTimer: 1, pendingSelects: [],
  };
  w.opts = { rows: [], failSelect: false, rejectSelect: false, manualSelect: false, failUpserts: 0, failDelete: false,
    removeChannel: "ok", disconnect: "ok", upload: "ok", ...opts };
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
              if (w.opts.manualSelect) return new Promise((r) => w.pendingSelects.push(r)).then(res, rej);
              if (w.opts.rejectSelect) return Promise.reject(new Error("select rejected")).then(res, rej);
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
    removeChannel(ch) {
      w.removedChannels.push(ch);
      if (w.opts.removeChannel === "throw") throw new Error("removeChannel threw");
      if (w.opts.removeChannel === "reject") return Promise.reject(new Error("removeChannel rejected"));
      return Promise.resolve("ok");
    },
    realtime: {
      disconnect() {
        w.disconnects += 1;
        if (w.opts.disconnect === "throw") throw new Error("disconnect threw");
        return Promise.resolve("ok");
      },
    },
  };

  const sandbox = {
    /* Підставний `fetch`: `data:`-адреса → відповідь із `blob()`, решта (завантаження в Storage) — за `opts.upload`. */
    fetch: (url, init) => {
      w.fetches.push({ url, init });
      if (typeof url === "string" && url.startsWith("data:")) return Promise.resolve({ ok: true, status: 200, blob: () => Promise.resolve({ blob: url }) });
      if (w.opts.upload === "reject") return Promise.reject(new Error("upload rejected"));
      return Promise.resolve({ ok: w.opts.upload === "ok", status: w.opts.upload === "ok" ? 200 : 403 });
    },
    supabase: { createClient: (url, key, o) => { w.created.push([url, key, o]); return client; } },
    setTimeout: (fn, ms) => { const t = { id: w.nextTimer++, fn, ms, live: true }; w.timers.push(t); w.delays.push(ms); return t.id; },
    clearTimeout: (id) => { const t = w.timers.find((x) => x.id === id); if (t) t.live = false; },
    console: { warn: (...a) => w.warnings.push(a.join(" ")), log: (...a) => w.logs.push(a.join(" ")), error: (...a) => w.logs.push(a.join(" ")) },
  };
  sandbox.window = sandbox;                               // `window.DeaiComments = …` у браузері — глобальний обʼєкт
  w.before = new Set(Object.keys(sandbox));
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: FILE });
  w.sandbox = sandbox;
  w.create = (cfg = {}) => sandbox.DeaiComments.create({ url: URL, key: KEY, channel: CHANNEL, ...cfg });
  w.selectCalls = () => w.calls.filter((c) => c.op === "select");
  w.pending = () => w.timers.filter((t) => t.live);
  /** Виконати таймери, що чекають ЗАРАЗ (за зростанням затримки); нові, додані ними, — вже наступного разу. */
  w.runTimers = () => {
    const batch = w.pending().sort((a, b) => a.ms - b.ms);
    for (const t of batch) if (t.live) { t.live = false; t.fn(); }
    return batch.length;
  };
  return w;
}

/** Крутити мікрозадачі й таймери світу, доки `p` не завершиться (успіхом чи відмовою); повертає `p`. */
async function drive(w, p) {
  let done = false;
  p.then(() => { done = true; }, () => { done = true; });
  for (let i = 0; i < 100 && !done; i += 1) { await settle(); w.runTimers(); }
  await settle();
  return p;
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

test("create без каналу — зрозуміла помилка ДО будь-якого клієнта й запиту (канал — непорожній рядок)", () => {
  const w = world();
  for (const bad of [undefined, null, "", 5, ["a"], {}, true]) {
    assert.throws(() => w.sandbox.DeaiComments.create({ url: URL, key: KEY, channel: bad }), /channel/, String(bad));
  }
  assert.throws(() => w.sandbox.DeaiComments.create(undefined), /channel/);
  assert.throws(() => w.sandbox.DeaiComments.create(null), /channel/);
  assert.deepEqual(w.created, [], "клієнт не створювався");
  assert.deepEqual(w.calls, []);
});

test("create: createClient(url, key, без автентифікації користувача) рівно раз; SELECT * з фільтром каналу й порядком за id", async () => {
  const w = world({ rows: [row("b"), row("a")] });
  const s = w.create();
  assert.equal(w.created.length, 1);
  assert.deepEqual(plain(w.created[0]), [URL, KEY, AUTH_OFF],
    "без persistSession/autoRefreshToken/detectSessionInUrl кожен create() лишав би інтервал токена, BroadcastChannel і слухачів вікна");
  assert.deepEqual(plain(s.load()), [], "до ready кешу ще нема");
  await s.ready;
  const sel = w.selectCalls();
  assert.equal(sel.length, 1);
  assert.deepEqual(plain(sel[0]), { op: "select", table: "comments", cols: "*", filters: [["eq", "project_id", CHANNEL]], order: "id" });
  assert.deepEqual(s.load().map((c) => c.id), ["b", "a"], "порядок — як віддав сервер (order=id робить він)");
  assert.deepEqual(Object.keys(s).sort(), ["close", "load", "ready", "refresh", "remove", "save", "subscribe"]);
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
  await s2.refresh();
  assert.deepEqual(s2.load().map((c) => c.id), ["a"], "збій не стирає кеш");
  assert.ok(w2.warnings.some((m) => m.includes("select boom")));
  for (const m of [...w2.warnings, ...w2.logs]) assert.ok(!m.includes(KEY), "ключ у консолі");
});

test("ready і refresh ніколи не відхиляються: запит, що кинув, — попередження, кеш цілий", async () => {
  const w = world({ rejectSelect: true });
  const s = w.create();
  await s.ready;                                                       // не кидає (інакше — необроблена відмова в сторінці)
  await s.refresh();
  assert.deepEqual(plain(s.load()), []);
  assert.ok(w.warnings.filter((m) => m.includes("select rejected")).length >= 2);
});

test("refresh: примусове перечитування каналу; після close — нічого не питає й нічого не повідомляє", async () => {
  let n = 0;
  const w = world({ rows: () => (n++ === 0 ? [row("a")] : [row("a"), row("b")]) });
  const seen = [];
  const s = w.create({ onChange: (c) => seen.push(c.map((x) => x.id)) });
  await s.ready;
  const p = s.refresh();
  assert.equal(typeof p.then, "function");
  await p;
  assert.deepEqual(s.load().map((c) => c.id), ["a", "b"]);
  assert.deepEqual(w.selectCalls().at(-1).filters, [["eq", "project_id", CHANNEL]]);
  assert.deepEqual(seen.at(-1), ["a", "b"]);
  s.close();
  await s.refresh();
  assert.equal(w.selectCalls().length, 2, "після close перечитувань нема");
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
  await drive(w, s.save([pin("a")]));
  assert.equal(w.calls.filter((c) => c.op === "upsert").length, 3);
  assert.deepEqual(w.delays, [300, 600]);
  assert.deepEqual(s.load().map((c) => c.id), ["a"]);
});

test("save: після трьох збоїв — відмова з текстом сервісу (без ключа), рівно 3 спроби й без марного очікування після останньої, кеш оптимістичний", async () => {
  const w = world({ failUpserts: 99 });
  const s = w.create();
  await s.ready;
  await assert.rejects(drive(w, s.save([pin("a")])), (e) => e.name === "Error" && /supabase save failed: upsert boom/.test(e.message) && !e.message.includes(KEY));
  assert.equal(w.calls.filter((c) => c.op === "upsert").length, 3);
  assert.deepEqual(w.delays, [300, 600], "після останньої невдалої спроби чекати нема чого");
  assert.deepEqual(s.load().map((c) => c.id), ["a"], "локальний кеш не губить запис, який SDK ще повторить сам");
  assert.ok(w.warnings.some((m) => m.includes("upsert boom")));
  for (const m of [...w.warnings, ...w.logs]) assert.ok(!m.includes(KEY), "ключ у консолі");
});

test("save скасовує відповідь, що летіла до запису: пізній SELECT не затирає щойно збережене", async () => {
  const w = world({ manualSelect: true });
  const s = w.create();
  await settle();
  assert.equal(w.pendingSelects.length, 1);                            // перше завантаження ще в дорозі
  await s.save([pin("mine")]);
  assert.deepEqual(s.load().map((c) => c.id), ["mine"]);
  w.pendingSelects[0]({ data: [row("stale")], error: null });          // …і приходить уже після запису
  await settle();
  assert.deepEqual(s.load().map((c) => c.id), ["mine"], "стара відповідь відкинута");
  const p = s.refresh();                                               // а наступне перечитування — вже діє
  await settle();
  w.pendingSelects[1]({ data: [row("mine"), row("other")], error: null });
  await p;
  assert.deepEqual(s.load().map((c) => c.id), ["mine", "other"]);
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
  /* Фільтра project_id тут нема навмисно: події DELETE несуть лише PK, і фільтр мовчки губив би видалення. Канал звужує
     перечитування (`fetchAll` з фільтром каналу), а не підписка. */
  assert.deepEqual(plain(ch.handlers[0].filter), { event: "*", schema: "public", table: "comments" });
});

test("подія realtime → (згладжування) → перечитування каналу → onChange з cfg і підписники отримують новий масив", async () => {
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
  assert.equal(w.selectCalls().length, 1, "перечитування не одразу, а після згладжування");
  assert.equal(w.runTimers(), 1);
  await settle();
  assert.equal(w.selectCalls().length, 2);
  assert.deepEqual(w.selectCalls()[1].filters, [["eq", "project_id", CHANNEL]], "перечитування — у межах каналу");
  assert.deepEqual(seenCfg.at(-1), ["a", "b"]);
  assert.deepEqual(seenSub.at(-1), ["a", "b"]);
  assert.deepEqual(s.load().map((c) => c.id), ["a", "b"]);
});

test("серія подій realtime дає ОДНЕ перечитування, через 100–150 мс після останньої події", async () => {
  const w = world({ rows: [row("a")] });
  const s = w.create();
  await s.ready;
  const cb = w.channels[0].handlers[0].cb;
  cb(); cb(); cb(); cb();                                              // upsert пачки рядків шле подію на кожен рядок
  const live = w.pending();
  assert.equal(live.length, 1, "термін посувається, а не множиться");
  assert.ok(live[0].ms >= 100 && live[0].ms <= 150, `згладжування ${live[0].ms} мс`);
  w.runTimers();
  await settle();
  assert.equal(w.selectCalls().length, 2, "одне перечитування на серію");
  cb();                                                                // нова подія після виконання — знову одне
  w.runTimers();
  await settle();
  assert.equal(w.selectCalls().length, 3);
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
  const w = world({ manualSelect: true });
  const s = w.create();
  const second = s.refresh();                                         // другий SELECT, поки перший ще в дорозі
  await settle();
  assert.equal(w.pendingSelects.length, 2);
  w.pendingSelects[1]({ data: [row("fresh")], error: null });
  await second;
  assert.deepEqual(s.load().map((c) => c.id), ["fresh"]);
  w.pendingSelects[0]({ data: [row("stale")], error: null });
  await settle();
  assert.deepEqual(s.load().map((c) => c.id), ["fresh"], "стара відповідь відкинута");
});

test("close: removeChannel(канал) рівно раз, потім закриття сокета realtime; підписники відпущені; повторний close — нічого", async () => {
  const w = world({ rows: [row("a")] });
  const seen = [];
  const s = w.create({ onChange: (c) => seen.push(c.length) });
  s.subscribe((c) => seen.push(c.length));
  await s.ready;
  const before = seen.length;
  s.close();
  assert.deepEqual(w.removedChannels, [w.channels[0]]);
  await settle();
  assert.equal(w.disconnects, 1, "removeChannel лише залишає канал: сокет і серцебиття закриває disconnect");
  w.channels[0].handlers[0].cb();
  w.runTimers();
  await settle();
  assert.equal(w.selectCalls().length, 1, "після close перечитувань нема");
  assert.equal(seen.length, before, "після close повідомлень нема");
  s.close();
  await settle();
  assert.equal(w.removedChannels.length, 1, "повторний close не знімає канал удруге");
  assert.equal(w.disconnects, 1);
});

test("close скасовує згладжену подію, що чекала: ні таймерів, ні перечитування", async () => {
  const w = world({ rows: [row("a")] });
  const s = w.create();
  await s.ready;
  w.channels[0].handlers[0].cb();
  assert.equal(w.pending().length, 1);
  s.close();
  assert.equal(w.pending().length, 0, "таймер скасовано");
  w.runTimers();
  await settle();
  assert.equal(w.selectCalls().length, 1);
});

test("close не кидає й не лишає необроблених відмов, що б не сталося з removeChannel чи disconnect", async () => {
  for (const o of [{ removeChannel: "reject" }, { removeChannel: "throw" }, { disconnect: "throw" }, { removeChannel: "reject", disconnect: "throw" }]) {
    const w = world(o);
    const s = w.create();
    await s.ready;
    s.close();                                                       // не кидає
    await settle();
    await settle();
    assert.equal(w.removedChannels.length, 1, JSON.stringify(o));
    assert.equal(w.disconnects, 1, `disconnect пробується й тоді: ${JSON.stringify(o)}`);
  }
});

test("close під час польоту SELECT: відповідь, що прийшла після нього, нікого не повідомляє", async () => {
  const w = world({ manualSelect: true });
  const seen = [];
  const s = w.create({ onChange: (c) => seen.push(c.length) });
  await settle();
  assert.equal(w.pendingSelects.length, 1);
  s.close();
  w.pendingSelects[0]({ data: [row("a")], error: null });
  await settle();
  assert.deepEqual(seen, []);
});

test("ключ іде лише в createClient: адаптер його ніде не друкує й не зберігає в глобальних іменах", async () => {
  const w = world({ rows: [row("a")], failUpserts: 99, failDelete: true });
  const s = w.create();
  await s.ready;
  await drive(w, s.save([pin("a")])).catch(() => {});
  await s.remove(["a"]);
  s.close();
  for (const m of [...w.warnings, ...w.logs]) assert.ok(!m.includes(KEY), m);
  assert.ok(!SRC.includes("localStorage") && !SRC.includes("document.cookie"), "адаптер не пише ключ у сховище браузера");
  assert.ok(!/XMLHttpRequest/.test(SRC), "XMLHttpRequest адаптер не чіпає");
  const withoutShot = SRC.replace(/function uploadShot[\s\S]*?\n    }\n/, "");
  assert.ok(!/\bfetch\s*\(/.test(withoutShot), "`fetch` — лише в uploadShot (скріншоти); решта мережі — supabase-js");
});

/* ------------------------------------------------------------------------------------------ скріншоти пінів */

const BUCKET = "overview-thumbs";
const DATA = "data:image/jpeg;base64,AAAA";

test("без shotsBucket у cfg uploadShot у сховища нема (і з порожнім, і з поганим іменем кошика)", async () => {
  for (const cfg of [{}, { shotsBucket: "" }, { shotsBucket: "A/B" }, { shotsBucket: "../x" }, { shotsBucket: "-x" }, { shotsBucket: 5 }, { shotsBucket: "x".repeat(64) }]) {
    const w = world();
    const s = w.create(cfg);
    await s.ready;
    assert.equal(typeof s.uploadShot, "undefined", JSON.stringify(cfg));
    assert.deepEqual(Object.keys(s).sort(), ["close", "load", "ready", "refresh", "remove", "save", "subscribe"]);
  }
});

test("з shotsBucket: uploadShot — один fetch(data:) і один POST у Storage з тією самою формою, що в старого адаптера ЛІГИ", async () => {
  const w = world();
  const s = w.create({ shotsBucket: BUCKET });
  await s.ready;
  assert.equal(typeof s.uploadShot, "function");
  const url = await s.uploadShot("c1", DATA);
  assert.equal(url, `${URL}/storage/v1/object/public/${BUCKET}/comment-shots/c1.jpg`);
  assert.equal(w.fetches.length, 2);
  assert.equal(w.fetches[0].url, DATA);
  const post = w.fetches[1];
  assert.equal(post.url, `${URL}/storage/v1/object/${BUCKET}/comment-shots/c1.jpg`);
  assert.equal(post.init.method, "POST");
  assert.deepEqual(plain(post.init.headers), {
    apikey: KEY, Authorization: `Bearer ${KEY}`, "Content-Type": "image/jpeg", "x-upsert": "true", "Cache-Control": "3600",
  });
  assert.deepEqual(plain(post.init.body), { blob: DATA }, "тіло — blob, отриманий з data:-адреси");
});

test("uploadShot: тип зображення береться з data:-адреси, а слеш у кінці адреси проєкту не дає подвійного", async () => {
  const w = world();
  const s = w.create({ shotsBucket: BUCKET, url: URL + "/" });
  await s.ready;
  const url = await s.uploadShot("c1", "data:image/png;base64,AAAA");
  assert.equal(url, `${URL}/storage/v1/object/public/${BUCKET}/comment-shots/c1.jpg`);
  assert.equal(w.fetches[1].url, `${URL}/storage/v1/object/${BUCKET}/comment-shots/c1.jpg`);
  assert.equal(w.fetches[1].init.headers["Content-Type"], "image/png");
});

test("uploadShot: не data:image, порожнє, null, чужий id → null без жодного fetch", async () => {
  const w = world();
  const s = w.create({ shotsBucket: BUCKET });
  await s.ready;
  for (const bad of ["https://x/y.png", "", null, undefined, 5, "data:text/html,<b>", "http://x"]) {
    assert.equal(await s.uploadShot("c1", bad), null, String(bad));
  }
  for (const id of ["../x", "a b", "", null, undefined, 5, "a/b", "-x", "x".repeat(201)]) {
    assert.equal(await s.uploadShot(id, DATA), null, String(id));
  }
  assert.deepEqual(w.fetches, [], "жодного запиту");
});

test("uploadShot: відповідь не ok → null + англійське попередження без ключа; відхилений fetch → null, не кидає", async () => {
  for (const upload of ["fail", "reject"]) {
    const w = world({ upload });
    const s = w.create({ shotsBucket: BUCKET });
    await s.ready;
    assert.equal(await s.uploadShot("c1", DATA), null, upload);
    assert.ok(w.warnings.length >= 1, upload);
    for (const m of w.warnings) {
      assert.ok(!m.includes(KEY), m);
      assert.ok(!/[Ѐ-ӿ]/.test(m), "англійською: " + m);
    }
  }
});

test("uploadShot після close() → null без fetch", async () => {
  const w = world();
  const s = w.create({ shotsBucket: BUCKET });
  await s.ready;
  s.close();
  assert.equal(await s.uploadShot("c1", DATA), null);
  assert.deepEqual(w.fetches, []);
});

/* ── Б2, поправка 8: запис різницею й realtime лише свого каналу ── */
const upserts = (w) => w.calls.filter((c) => c.op === "upsert");

test("запис різницею: save того самого списку, що прийшов із select, — жодного upsert", async () => {
  const w = world({ rows: [row("a"), row("b")] });
  const s = w.create();
  await s.ready;
  await s.save(plain(s.load()));
  assert.equal(upserts(w).length, 0);
  assert.deepEqual(s.load().map((c) => c.id), ["a", "b"], "кеш лишається");
});

test("запис різницею: змінено один пін (meta.assignee) — upsert рівно з ОДНИМ рядком", async () => {
  const w = world({ rows: [row("a"), row("b"), row("c")] });
  const s = w.create();
  await s.ready;
  const list = plain(s.load());
  list[1].meta = { ...list[1].meta, assignee: "claude" };
  await s.save(list);
  const up = upserts(w);
  assert.equal(up.length, 1);
  assert.deepEqual(up[0].rows.map((r) => r.id), ["b"]);
  assert.equal(plain(up[0].rows[0]).meta.assignee, "claude");
});

test("запис різницею: база віддала meta з іншим порядком ключів — save без змін нічого не шле", async () => {
  const w = world({ rows: [row("a", { meta: { seq: 1, version: "2" } })] });
  const s = w.create();
  await s.ready;
  await s.save([pin("a", { meta: { version: "2", seq: 1 } })]);
  assert.equal(upserts(w).length, 0, "порядок ключів jsonb не робить рядок зміненим");
});

test("запис різницею: після успішного запису повторний save мовчить; після невдалого — шле знову", async () => {
  const w = world();
  const s = w.create();
  await s.ready;
  await s.save([pin("a")]);
  assert.equal(upserts(w).length, 1);
  await s.save([pin("a")]);
  assert.equal(upserts(w).length, 1, "успішно записане вдруге не йде");
  const w2 = world({ failUpserts: 3 });
  const s2 = w2.create();
  await s2.ready;
  await assert.rejects(drive(w2, s2.save([pin("a")])), /supabase save failed/);
  assert.equal(upserts(w2).length, 3);
  await s2.save([pin("a")]);
  assert.equal(upserts(w2).length, 4, "невдалий запис не вважається записаним");
});

test("realtime: події чужого каналу не перечитують; свого — перечитують; DELETE — за id з кешу; незнайома форма — перечитує", async () => {
  const w = world({ rows: [row("a")] });
  const s = w.create();
  await s.ready;
  const cb = w.channels[0].handlers[0].cb;
  const fire = async (p) => {
    const before = w.selectCalls().length;
    cb(p);
    w.runTimers();
    await settle();
    return w.selectCalls().length - before;
  };
  assert.equal(await fire({ eventType: "INSERT", new: { project_id: "інший" } }), 0, "чужий INSERT");
  assert.equal(await fire({ eventType: "UPDATE", new: { project_id: CHANNEL } }), 1, "свій UPDATE");
  assert.equal(await fire({ eventType: "DELETE", old: { id: "a" } }), 1, "DELETE id з кешу");
  assert.equal(await fire({ eventType: "DELETE", old: { id: "чужий" } }), 0, "DELETE чужого id");
  assert.equal(await fire({}), 1, "незнайома форма");
});

test("запис різницею: remove(id) прибирає id зі знімка written — повторне створення того самого id пишеться знову", async () => {
  const w = world();
  const s = w.create();
  await s.ready;
  await s.save([pin("a")]);
  assert.equal(upserts(w).length, 1);
  await s.remove(["a"]);
  await s.save([pin("a")]);
  assert.equal(upserts(w).length, 2, "після видалення той самий рядок — знову новий для бази");
});

test("запис різницею: fetchAll скидає written до щойно прочитаного — те, чого база не віддала, пишеться знову", async () => {
  const w = world({ rows: [] });
  const s = w.create();
  await s.ready;
  await s.save([pin("a")]);
  assert.equal(upserts(w).length, 1);
  await drive(w, s.refresh());                           // база (все ще) порожня: знімок записаного застарів
  await s.save([pin("a")]);
  assert.equal(upserts(w).length, 2, "рядок, якого перечитування не знайшло, не вважається записаним");
});

test("запис різницею: коментар без необовʼязкового поля (undefined) після fetchAll → save того ж списку — жодного upsert", async () => {
  const w = world({ rows: [row("a", { resolved_v: null, resolve_reason: null, fp: null, born_v: null, text: null })] });
  const s = w.create();
  await s.ready;
  const mine = pin("a");
  delete mine.resolvedV; delete mine.resolveReason; delete mine.ts; delete mine.fp; delete mine.bornV; delete mine.text;      // у БД це null, у вікні — відсутнє поле
  mine.ts = "19.10.2026 10:00";
  await s.save([mine]);
  assert.equal(upserts(w).length, 0, "undefined і null — одне й те саме для порівняння");
  const w2 = world({ rows: [row("b", { author: null })] });
  const s2 = w2.create();
  await s2.ready;
  const c = pin("b"); delete c.author;
  await s2.save([c]);
  assert.equal(upserts(w2).length, 0, "відсутній author проти null з бази");
});
