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

/** Підставний `sessionStorage`: `quota` — скільки перших `setItem` кидає QuotaExceededError (Infinity — завжди). */
function fakeStorage({ quota = 0 } = {}) {
  const m = new Map();
  const st = {
    m, touched: 0, quota,
    getItem(k) { st.touched++; return m.has(k) ? m.get(k) : null; },
    setItem(k, v) {
      st.touched++;
      if (st.quota > 0) { st.quota--; throw new Error("QuotaExceededError"); }
      m.set(k, String(v));
    },
    removeItem(k) { st.touched++; m.delete(k); },
    key(i) { return [...m.keys()][i] ?? null; },
    get length() { return m.size; },
  };
  return st;
}

/**
 * Світ. Параметри: `rows` — що віддає SELECT (масив або функція від номера запиту); `failSelect` (відповідь із помилкою),
 * `rejectSelect` (запит ВІДХИЛЯЄТЬСЯ), `manualSelect` (SELECT-и чекають: `w.pendingSelects[i]({data, error})`), `failTargeted`/`targeted` (цільовий select `in('id', …)` перед злиттям), `failUpserts`
 * (перші N upsert-ів падають), `failDelete`, `removeChannel` (`"ok"` | `"reject"` | `"throw"`), `disconnect` (`"ok"` | `"throw"`),
 * `storage` (підставний sessionStorage), `upload` (відповідь підставного `fetch` на завантаження скріншота: `"ok"` | `"fail"` | `"reject"`).
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
            in(col, vals) { q.filters.push(["in", col, vals]); return b; },
            order(col) { q.order = col; return b; },
            then(res, rej) {
              const inF = q.filters.find((f) => f[0] === "in");
              if (inF) {                                  // цільовий select перед злиттям: `opts.targeted(ids)` або рядки за id
                if (w.opts.failTargeted) return Promise.resolve({ data: null, error: { message: "targeted boom" } }).then(res, rej);
                const src = typeof w.opts.targeted === "function" ? w.opts.targeted(inF[2]) : (typeof w.opts.rows === "function" ? w.opts.rows(n) : w.opts.rows);
                return Promise.resolve({ data: src.filter((r) => inF[2].includes(r.id)), error: null }).then(res, rej);
              }
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
  /* Знімок каналу (0.27.0): підставні `sessionStorage` (`opts.storage`: обʼєкт з `fakeStorage()` або "throw" — доступ кидає),
     керований годинник `w.clock` (адаптер читає лише `Date.now`) і «чорна скринька» `localStorage`, яку ніхто не має торкатися. */
  w.clock = 1_000_000;
  sandbox.Date = { now: () => w.clock };
  w.localStorage = fakeStorage();
  sandbox.localStorage = w.localStorage;
  if (opts.storage === "throw") Object.defineProperty(sandbox, "sessionStorage", { get() { throw new Error("storage blocked"); } });
  else if (opts.storage) sandbox.sessionStorage = opts.storage;
  sandbox.window = sandbox;                               // `window.DeaiComments = …` у браузері — глобальний обʼєкт
  w.before = new Set(Object.keys(sandbox));
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: FILE });
  w.sandbox = sandbox;
  w.create = (cfg = {}) => sandbox.DeaiComments.create({ url: URL, key: KEY, channel: CHANNEL, ...cfg });
  w.selectCalls = () => w.calls.filter((c) => c.op === "select" && !c.filters.some((f) => f[0] === "in"));
  w.targetedCalls = () => w.calls.filter((c) => c.op === "select" && c.filters.some((f) => f[0] === "in"));
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
  assert.deepEqual(Object.keys(s).sort(), ["close", "load", "loadError", "ready", "refresh", "remove", "save", "subscribe"]);
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

test("loadError: збій ПЕРШОГО читання видно в полі (ready усе одно здається); вдале перечитування його скидає", async () => {
  const w = world({ rows: [row("a")], failSelect: true });
  const s = w.create();
  await s.ready;                                                       // не відхиляється: інші споживачі на це покладаються
  assert.equal(s.loadError, "select boom");
  w.opts.failSelect = false;
  await s.refresh();
  assert.equal(s.loadError, null, "вдале читання скидає");
  assert.deepEqual(s.load().map((c) => c.id), ["a"]);
  const w2 = world({ rejectSelect: true });
  const s2 = w2.create();
  await s2.ready;
  assert.equal(s2.loadError, "select rejected", "кинутий запит теж");
  const w3 = world({ rows: [] });
  const s3 = w3.create();
  await s3.ready;
  assert.equal(s3.loadError, null, "здорова база — без помилки");
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
    assert.deepEqual(Object.keys(s).sort(), ["close", "load", "loadError", "ready", "refresh", "remove", "save", "subscribe"]);
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

/* ------------------------------------------------------------------------------------------ знімок каналу (sessionStorage) */

const SNAP_KEY = `deai-comments:v1:abcdefghijkl.supabase.co:${CHANNEL}`;
const TTL = 120000;
const snapOf = (st, key = SNAP_KEY) => JSON.parse(st.getItem(key));
const upsertsOf = (w) => w.calls.filter((c) => c.op === "upsert");
const fire = async (w, ev, i = 0) => { w.channels[i].handlers[0].cb(ev); w.runTimers(); await settle(); };

test("знімок: другий create у межах TTL на тому ж url+каналі — 0 select; той самий load() і written (save без змін — без upsert)", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a"), row("b")], storage: st });
  const s1 = w.create();
  await s1.ready;
  assert.equal(w.selectCalls().length, 1);
  w.clock += TTL - 1;
  const seen = [];
  const s2 = w.create({ onChange: (c) => seen.push(c.map((x) => x.id)) });
  await s2.ready;
  assert.equal(w.selectCalls().length, 1, "засіяно знімком — читання з бази нема");
  assert.deepEqual(plain(s2.load()), plain(s1.load()));
  assert.equal(s2.loadError, null);
  assert.deepEqual(plain(seen), [["a", "b"]], "onChange повідомляється й при засіванні");
  assert.equal(w.channels.length, 2, "realtime підписується як завжди");
  assert.equal(w.channels[1].subscribed, 1);
  await s2.save([pin("a"), pin("b")]);
  assert.equal(upsertsOf(w).length, 0, "written засіяно: нічого не змінено — нічого не пишемо");
  await s2.save([pin("a", { text: "нове" }), pin("b")]);
  assert.equal(upsertsOf(w).length, 1);
  assert.deepEqual(upsertsOf(w)[0].rows.map((r) => r.id), ["a"]);
});

test("знімок: після TTL — рівно одне читання (і знімок оновлено)", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st });
  await w.create().ready;
  w.clock += TTL;
  await w.create().ready;
  assert.equal(w.selectCalls().length, 2);
  assert.equal(snapOf(st).t, w.clock, "вдале читання продовжує знімок");
});

test("знімок: інший канал чи інший хост url — окремі ключі, по одному читанню", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st });
  await w.create().ready;
  await w.create({ channel: "deai/space-1/task-8" }).ready;
  await w.create({ url: "https://zzzzzzzzzzzz.supabase.co" }).ready;
  assert.equal(w.selectCalls().length, 3);
  assert.equal(st.length, 3);
  assert.ok(!JSON.stringify([...st.m.keys()]).includes(KEY), "ключ не потрапляє в ім'я запису");
});

test("знімок: невдале перше читання нічого не пише; свіжий знімок не стирає і наступне читання (refresh) його не псує", async () => {
  const st = fakeStorage();
  const w1 = world({ failSelect: true, storage: st });
  const s0 = w1.create();
  await s0.ready;
  assert.equal(st.length, 0, "невдача — запису нема");
  const w = world({ rows: [row("a")], storage: st });
  const s1 = w.create();
  await s1.ready;
  const before = st.getItem(SNAP_KEY);
  w.opts.failSelect = true;
  w.clock += TTL;                                  // знімок застарів → refresh читає й падає
  await s1.refresh();
  assert.equal(st.getItem(SNAP_KEY), before, "невдале читання не торкається знімка");
  w.clock = 1_000_000 + 10;                        // а свіжий знімок переживає падіння іншого адаптера
  w.opts.failSelect = false;
  const w3 = world({ failSelect: true, storage: st });
  w3.clock = w.clock;
  const s3 = w3.create();
  await s3.ready;
  assert.equal(w3.selectCalls().length, 0, "свіжий знімок засіяв — читання не було");
  assert.equal(st.getItem(SNAP_KEY), before);
});

test("знімок: save і remove оновлюють рядки знімка, але НЕ t", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a"), row("b")], storage: st });
  const s = w.create();
  await s.ready;
  const t0 = snapOf(st).t;
  w.clock += 5000;
  await s.save([pin("a", { text: "нове" }), pin("b"), pin("c")]);
  let snap = snapOf(st);
  assert.equal(snap.t, t0, "save не продовжує життя знімка");
  assert.deepEqual(snap.rows.map((r) => [r.id, r.text]), [["a", "нове"], ["b", "текст b"], ["c", "текст c"]]);
  w.clock += 5000;
  await s.remove(["b"]);
  snap = snapOf(st);
  assert.equal(snap.t, t0, "remove теж");
  assert.deepEqual(snap.rows.map((r) => r.id), ["a", "c"]);
});

test("знімок: save без змін теж не чіпає t; невдалий save знімок не оновлює", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st, failUpserts: 99 });
  const s = w.create();
  await s.ready;
  const raw = st.getItem(SNAP_KEY);
  w.clock += 100;
  await drive(w, s.save([pin("a", { text: "x" })])).catch(() => {});
  assert.equal(st.getItem(SNAP_KEY), raw, "база не прийняла — знімок не бреше");
  await s.save([pin("a")]);                                // кеш = прочитане → без змін
  assert.equal(snapOf(st).t, 1_000_000);
});

test("луна власного запису не планує перечитування; чужа зміна — планує", async () => {
  const w = world({ rows: [row("a")] });
  const s = w.create();
  await s.ready;
  await s.save([pin("a", { text: "моє" })]);
  const mine = row("a", { text: "моє" });
  await fire(w, { eventType: "UPDATE", new: mine });
  assert.equal(w.selectCalls().length, 1, "луна власного upsert-а");
  await fire(w, { eventType: "UPDATE", new: row("a", { text: "чуже" }) });
  assert.equal(w.selectCalls().length, 2, "чужа зміна");
  await fire(w, { eventType: "UPDATE", new: { id: "a", project_id: CHANNEL } });
  assert.equal(w.selectCalls().length, 3, "обрізані стовпці не збігаються");
  await fire(w, { eventType: "INSERT" });
  assert.equal(w.selectCalls().length, 4, "без new — як раніше");
  await fire(w, { eventType: "INSERT", new: row("z") });
  assert.equal(w.selectCalls().length, 5, "невідомий id");
});

test("refresh: у межах TTL — без select; після TTL — з select", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st });
  const s = w.create();
  await s.ready;
  w.clock += TTL - 1;
  await s.refresh();
  assert.equal(w.selectCalls().length, 1);
  w.clock += 1;
  await s.refresh();
  assert.equal(w.selectCalls().length, 2);
  await s.refresh();
  assert.equal(w.selectCalls().length, 2, "знімок знову свіжий");
});

test("refresh: у засіяного адаптера теж за t знімка", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st });
  await w.create().ready;
  w.clock += TTL - 10;
  const s2 = w.create();
  await s2.ready;
  await s2.refresh();
  assert.equal(w.selectCalls().length, 1);
  w.clock += 10;
  await s2.refresh();
  assert.equal(w.selectCalls().length, 2);
});

test("знімок: помилка квоти на setItem — не кидає, чистить наші ключі, одна повторна спроба; адаптер працює", async () => {
  const st = fakeStorage({ quota: 1 });
  st.m.set(`deai-comments:v1:other:chan`, JSON.stringify({ t: 1_000_000, rows: [] }));
  st.m.set("чужий-ключ", "1");
  const w = world({ rows: [row("a")], storage: st });
  const s = w.create();
  await s.ready;
  assert.deepEqual(s.load().map((c) => c.id), ["a"]);
  assert.ok(st.getItem(SNAP_KEY), "повторна спроба вдалася");
  assert.equal(st.getItem("deai-comments:v1:other:chan"), null, "інші наші ключі прибрано");
  assert.equal(st.getItem("чужий-ключ"), "1", "чужі ключі не чіпаємо");
  const st2 = fakeStorage({ quota: Infinity });
  const w2 = world({ rows: [row("a")], storage: st2 });
  const s2 = w2.create();
  await s2.ready;
  await s2.save([pin("a", { text: "x" })]);
  assert.deepEqual(s2.load().map((c) => c.text), ["x"]);
  assert.equal(st2.length, 0);
});

test("знімок: sessionStorage, що кидає при доступі, — адаптер працює як раніше (кожен create читає, refresh читає)", async () => {
  const w = world({ rows: [row("a")], storage: "throw" });
  const s1 = w.create();
  await s1.ready;
  const s2 = w.create();
  await s2.ready;
  assert.equal(w.selectCalls().length, 2);
  await s2.refresh();
  assert.equal(w.selectCalls().length, 3);
  await s2.save([pin("a", { text: "x" })]);
  await s2.remove(["a"]);
  assert.deepEqual(s2.load(), []);
});

test("знімок: методи storage, що кидають, не валять адаптер", async () => {
  const st = fakeStorage();
  for (const m of ["getItem", "setItem", "removeItem"]) st[m] = () => { throw new Error("boom"); };
  const w = world({ rows: [row("a")], storage: st });
  const s = w.create();
  await s.ready;
  await s.save([pin("a", { text: "x" })]);
  await s.remove(["a"]);
  assert.equal(s.loadError, null);
});

test("знімок: нічого не пишеться в localStorage", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st });
  const s = w.create();
  await s.ready;
  await s.save([pin("a", { text: "x" })]);
  await s.remove(["a"]);
  await s.refresh();
  await w.create().ready;
  assert.equal(w.localStorage.touched, 0);
  assert.equal(w.localStorage.length, 0);
});

test("знімок: завеликий (> 2 000 000 символів) не зберігається, а старий запис ключа прибирається", async () => {
  const st = fakeStorage();
  st.m.set(SNAP_KEY, JSON.stringify({ t: 1, rows: [row("old")] }));
  const big = row("a", { html_snapshot: { outerHTML: "x".repeat(2_100_000) } });
  const w = world({ rows: [big], storage: st });
  const s = w.create();
  await s.ready;
  assert.equal(s.load().length, 1, "кеш у памʼяті є");
  assert.equal(st.getItem(SNAP_KEY), null);
  await w.create().ready;
  assert.equal(w.selectCalls().length, 2, "знімка нема — читаємо знову");
});

test("знімок: зіпсований запис ігнорується й видаляється; застарілі чужі знімки прибираються при записі", async () => {
  const st = fakeStorage();
  st.m.set(SNAP_KEY, "{не json");
  st.m.set("deai-comments:v1:old:x", JSON.stringify({ t: 1_000_000 - TTL - 1, rows: [] }));
  st.m.set("deai-comments:v1:young:x", JSON.stringify({ t: 1_000_000 - 5, rows: [] }));
  const w = world({ rows: [row("a")], storage: st });
  const s = w.create();
  assert.equal(st.getItem(SNAP_KEY), null, "зіпсований запис прибрано одразу");
  await s.ready;
  assert.equal(w.selectCalls().length, 1);
  assert.equal(st.getItem("deai-comments:v1:old:x"), null, "застарілий прибрано");
  assert.ok(st.getItem("deai-comments:v1:young:x"), "свіжий лишився");
  for (const bad of [{ t: "x", rows: [] }, { t: 1, rows: "x" }, { t: 1_000_000, rows: [{ noid: 1 }] }]) {
    st.m.set(SNAP_KEY, JSON.stringify(bad));
    const w2 = world({ rows: [row("a")], storage: st });
    w2.clock = 1_000_000;
    await w2.create().ready;
    assert.equal(w2.selectCalls().length, 1, JSON.stringify(bad));
  }
});

/* ------------------------------------------------------------------------------------- наздоганяюче читання і злиття */

/** Світ зі знімком, у якому засіяно другий екземпляр: перший прочитав `rows` у момент t0, другий стартує через `gap` мс. */
async function seededWorld(opts = {}, gap = 30000) {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st, ...opts });
  const s1 = w.create();
  await s1.ready;
  w.clock += gap;
  const seen = [];
  const s2 = w.create({ onChange: (c) => seen.push(plain(c)) });
  await s2.ready;
  return { w, st, s1, s2, seen };
}

test("наздоганяюче читання: засіяний екземпляр читає рівно один раз, у момент кінця життя знімка", async () => {
  const { w } = await seededWorld();
  assert.equal(w.selectCalls().length, 1);
  const live = w.pending();
  assert.equal(live.length, 1);
  assert.equal(live[0].ms, TTL - 30000, "TTL мінус вік знімка");
  w.runTimers();
  await settle();
  assert.equal(w.selectCalls().length, 2);
  assert.equal(w.pending().length, 0, "повторно не планується: далі realtime без прогалини");
});

test("наздоганяюче читання: скасовується раннім повним читанням (realtime і refresh після TTL) та close()", async () => {
  const a = await seededWorld();
  await fire(a.w, { eventType: "UPDATE", new: row("a", { text: "чуже" }) }, 1);
  assert.equal(a.w.selectCalls().length, 2, "realtime-перечитування");
  assert.equal(a.w.pending().length, 0, "наздоганяюче скасовано");
  const b = await seededWorld();
  b.w.clock += TTL;
  await b.s2.refresh();
  assert.equal(b.w.selectCalls().length, 2);
  assert.equal(b.w.pending().length, 0);
  const c = await seededWorld();
  c.s2.close();
  assert.equal(c.w.pending().length, 0);
  c.w.runTimers();
  await settle();
  assert.equal(c.w.selectCalls().length, 1, "після close читання нема");
});

test("наздоганяюче читання: без засівання таймера нема", async () => {
  const w = world({ rows: [row("a")], storage: fakeStorage() });
  await w.create().ready;
  assert.equal(w.pending().length, 0);
  const w2 = world({ rows: [row("a")] });                 // без storage
  await w2.create().ready;
  assert.equal(w2.pending().length, 0);
});

test("злиття: колега закрив пін, а ми правили текст — у рядку є обидва; споживачі отримують злитий стан", async () => {
  const remote = row("a", { status: "resolved", resolved_v: 3 });
  const { w, s2, seen, st } = await seededWorld({ targeted: () => [remote] });
  await s2.save([pin("a", { text: "мій" })]);
  assert.equal(w.targetedCalls().length, 1);
  assert.deepEqual(w.targetedCalls()[0].filters, [["in", "id", ["a"]], ["eq", "project_id", CHANNEL]]);
  const up = upsertsOf(w);
  assert.equal(up.length, 1);
  assert.equal(up[0].rows[0].text, "мій");
  assert.equal(up[0].rows[0].status, "resolved");
  assert.equal(up[0].rows[0].resolved_v, 3);
  const c = s2.load()[0];
  assert.deepEqual([c.text, c.status, c.resolvedV], ["мій", "resolved", 3]);
  assert.equal(plain(seen.at(-1))[0].status, "resolved", "onChange віддав злитий стан");
  assert.equal(snapOf(st).rows[0].status, "resolved");
  await s2.save([c]);
  assert.equal(upsertsOf(w).length, 1, "written оновлено злитим: повторний save мовчить");
});

test("злиття: обидва правили текст — виграє наше", async () => {
  const { w, s2 } = await seededWorld({ targeted: () => [row("a", { text: "їхній" })] });
  await s2.save([pin("a", { text: "мій" })]);
  assert.equal(upsertsOf(w)[0].rows[0].text, "мій");
});

test("злиття: колега додав meta.assignee, ми змінили текст — і те, й те; ключ, що ми прибрали, іде, лише якщо їхній лишився базовим", async () => {
  const base = { version: "2/x", seq: 3 };
  const a = await seededWorld({ targeted: () => [row("a", { meta: { ...base, assignee: "Іра" } })] });
  await a.s2.save([pin("a", { text: "мій" })]);
  assert.deepEqual(plain(upsertsOf(a.w)[0].rows[0].meta), { version: "2/x", seq: 3, assignee: "Іра" });
  assert.equal(upsertsOf(a.w)[0].rows[0].text, "мій");
  const b = await seededWorld({ targeted: () => [row("a")] });
  await b.s2.save([pin("a", { meta: { version: "2/x" } })]);
  assert.deepEqual(plain(upsertsOf(b.w)[0].rows[0].meta), { version: "2/x" }, "їхній seq базовий — наше видалення чинне");
  const c = await seededWorld({ targeted: () => [row("a", { meta: { version: "2/x", seq: 4 } })] });
  await c.s2.save([pin("a", { meta: { version: "2/x" } })]);
  assert.deepEqual(plain(upsertsOf(c.w)[0].rows[0].meta), { version: "2/x", seq: 4 }, "їхній seq змінено — не видаляємо");
});

test("злиття: пропущеної зміни нема — рівно один цільовий select, без злиття й без emit; після повного читання цільових нема", async () => {
  const { w, s2, seen } = await seededWorld({ targeted: () => [row("a")] });
  await s2.save([pin("a", { text: "мій" })]);
  assert.equal(w.targetedCalls().length, 1);
  assert.equal(upsertsOf(w)[0].rows[0].text, "мій");
  assert.equal(seen.length, 1, "лише засівання: злиття не було — emit не потрібен");
  w.clock += TTL;
  await s2.refresh();
  await s2.save([pin("a", { text: "ще" })]);
  assert.equal(w.targetedCalls().length, 1, "власне повне читання зроблено — запис більше не питає");
  const w2 = world({ rows: [row("a")], storage: fakeStorage() });
  const s = w2.create();
  await s.ready;
  await s.save([pin("a", { text: "x" })]);
  assert.equal(w2.targetedCalls().length, 0, "екземпляр, що сам читав, не питає");
});

test("злиття: збій цільового select — звичайний upsert з попередженням; рядок, якого в базі вже нема, пишеться як є", async () => {
  const a = await seededWorld({ failTargeted: true });
  await a.s2.save([pin("a", { text: "мій" })]);
  assert.equal(upsertsOf(a.w)[0].rows[0].text, "мій");
  assert.ok(a.w.warnings.some((m) => m.includes("merge check failed")));
  const b = await seededWorld({ targeted: () => [] });
  await b.s2.save([pin("a", { text: "мій" })]);
  assert.equal(upsertsOf(b.w).length, 1);
});

test("syncSnap: екземпляр, чий знімок чужий-новіший, не затирає його своїми рядками (рядки й t — другого)", async () => {
  const st = fakeStorage();
  let n = 0;
  const w = world({ rows: () => (n++ === 0 ? [row("a")] : [row("a"), row("b")]), targeted: () => [row("a")], storage: st });
  await w.create().ready;                                  // t1
  w.clock += 1000;
  const A = w.create();
  await A.ready;                                           // засіяно на t1
  w.clock += TTL;                                          // знімок застарів; наздоганяюче A ще не відпрацювало
  const B = w.create();
  await B.ready;                                           // повне читання на t2
  const t2 = w.clock;
  await A.save([pin("a", { text: "A правив" })]);
  const snap = snapOf(st);
  assert.equal(snap.t, t2);
  assert.deepEqual(snap.rows.map((r) => r.id), ["a", "b"], "рядки B, а не старіші A");
  assert.equal(snap.rows[0].text, "текст a");
});
