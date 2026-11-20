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
 * (перші N upsert-ів падають; для відповідей — `failRepliesUpserts`, `failRepliesDelete`, `failReplies`; таблиця відповідей є лише з `replies`), `failDelete`, `removeChannel` (`"ok"` | `"reject"` | `"throw"`), `disconnect` (`"ok"` | `"throw"`),
 * `storage` (підставний sessionStorage), `upload` (відповідь підставного `fetch` на завантаження скріншота: `"ok"` | `"fail"` | `"reject"`).
 * Результат: `sandbox`, `calls`, `channels`, `removedChannels`, `disconnects`, `created`, `delays` (затримки всіх таймерів),
 * `timers`, `warnings`, `logs`.
 */
function world(opts = {}) {
  const w = {
    calls: [], fetches: [], channels: [], removedChannels: [], disconnects: 0, created: [], delays: [], warnings: [], logs: [], selects: 0,
    timers: [], nextTimer: 1, pendingSelects: [], pendingTargeted: [],
  };
  w.opts = { rows: [], failSelect: false, rejectSelect: false, manualSelect: false, failUpserts: 0, failDelete: false,
    removeChannel: "ok", disconnect: "ok", upload: "ok", failReplies: false, failRepliesUpserts: 0, failRepliesDelete: false, ...opts };
  const reply = (v) => ({ then: (res, rej) => Promise.resolve(v).then(res, rej) });   // thenable, як у PostgREST-білдера

  const client = {
    from(table) {
      return {
        select(cols) {
          const q = { op: "select", table, cols, filters: [], order: null };
          w.calls.push(q);
          if (table === "comment_replies") {
            /* Таблиця відповідей: `opts.replies` (масив чи функція) — вона є; без нього її нема (PGRST205, як віддає PostgREST), тож
               усі давні тести працюють у «старому проєкті без replies.sql». `failReplies` — інша помилка (повідомлення). */
            const rb = {
              eq(col, val) { q.filters.push(["eq", col, val]); return rb; },
              in(col, vals) { q.filters.push(["in", col, vals]); return rb; },
              order(col) { q.order = q.order ? [].concat(q.order, col) : col; return rb; },
              then(res, rej) {
                let out;
                if (w.opts.failReplies) out = { data: null, ...(typeof w.opts.failReplies === "object" ? w.opts.failReplies.top : {}), error: typeof w.opts.failReplies === "object" ? w.opts.failReplies.error : { message: w.opts.failReplies === true ? "replies boom" : w.opts.failReplies } };
                else if (w.opts.replies === undefined) out = { data: null, status: 404, error: { code: "PGRST205", message: "Could not find the table 'public.comment_replies' in the schema cache" } };
                else out = { data: typeof w.opts.replies === "function" ? w.opts.replies() : w.opts.replies, error: null };
                return Promise.resolve(out).then(res, rej);
              },
            };
            return rb;
          }
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
                const out = { data: src.filter((r) => inF[2].includes(r.id)), error: null };
                if (w.opts.gateTargeted) return new Promise((r) => w.pendingTargeted.push(() => r(out))).then(res, rej);   // відповідь чекає тесту
                return Promise.resolve(out).then(res, rej);
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
          if (table === "comment_replies") {
            const f = w.opts.failRepliesUpserts > 0;
            if (f) w.opts.failRepliesUpserts -= 1;
            return reply({ data: null, error: f ? { message: "replies upsert boom" } : null });
          }
          if (w.opts.hangUpserts > 0) { w.opts.hangUpserts -= 1; return new Promise(() => {}); }   // завислий запит
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
              if (table === "comment_replies") {
                w.repliesDeletes = (w.repliesDeletes || 0) + 1;
                if (w.opts.rejectRepliesDeleteAt === w.repliesDeletes) return Promise.reject(new Error("net down")).then(res, rej);
                if (w.opts.failRepliesDeleteCount > 0) { w.opts.failRepliesDeleteCount -= 1; return Promise.resolve({ error: { message: "delete boom" } }).then(res, rej); }
              }
              const byOwner = q.filters.some((f) => f[1] === "comment_id");
              const bad = table === "comment_replies" ? (w.opts.failRepliesDelete || (byOwner && w.opts.failRepliesByOwner)) : w.opts.failDelete;
              return Promise.resolve({ error: bad ? { message: "delete boom" } : null }).then(res, rej);
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
  w.selectCalls = () => w.calls.filter((c) => c.op === "select" && c.table === "comments" && !c.filters.some((f) => f[0] === "in"));
  w.targetedCalls = () => w.calls.filter((c) => c.op === "select" && c.table === "comments" && c.filters.some((f) => f[0] === "in"));
  w.repliesSelects = () => w.calls.filter((c) => c.op === "select" && c.table === "comment_replies");
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
  assert.deepEqual(Object.keys(s).sort(), ["close", "load", "loadError", "ready", "refresh", "remove", "repliesDown", "save", "subscribe", "supportsReplies"]);
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
  assert.deepEqual(w.delays.filter((d) => d !== 20000), [300, 600]);   // 20000 — запобіжний таймаут запиту
  assert.deepEqual(s.load().map((c) => c.id), ["a"]);
});

test("save: після трьох збоїв — відмова з текстом сервісу (без ключа), рівно 3 спроби й без марного очікування після останньої, кеш оптимістичний", async () => {
  const w = world({ failUpserts: 99 });
  const s = w.create();
  await s.ready;
  await assert.rejects(drive(w, s.save([pin("a")])), (e) => e.name === "Error" && /supabase save failed: upsert boom/.test(e.message) && !e.message.includes(KEY));
  assert.equal(w.calls.filter((c) => c.op === "upsert").length, 3);
  assert.deepEqual(w.delays.filter((d) => d !== 20000), [300, 600], "після останньої невдалої спроби чекати нема чого");
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
    assert.deepEqual(Object.keys(s).sort(), ["close", "load", "loadError", "ready", "refresh", "remove", "repliesDown", "save", "subscribe", "supportsReplies"]);
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

test("запис різницею: remove(id) — після видалення застарілий save з тим самим id НЕ воскрешає коментар (gone), written прибрано", async () => {
  const w = world();
  const s = w.create();
  await s.ready;
  await s.save([pin("a")]);
  assert.equal(upserts(w).length, 1);
  await s.remove(["a"]);
  await s.save([pin("a")]);
  assert.equal(upserts(w).length, 1, "після видалення save зі старим списком коментаря не воскрешає (раніше писав знову: remove обходив gone)");
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
/** Подія realtime + виконати ЛИШЕ таймер із затримкою `ms` (решта таймерів, зокрема наздоганяючий, чекає). */
const fireOnly = async (w, ev, ms, i = 0) => {
  w.channels[i].handlers[0].cb(ev);
  const t = w.pending().find((x) => x.ms === ms);
  t.live = false; t.fn();
  await settle();
};
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
  assert.deepEqual(plain(upsertsOf(w)[0].rows.map((r) => r.id)), ["a"]);
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
  await fireOnly(a.w, { eventType: "UPDATE", new: row("a", { text: "чуже" }) }, 120, 1);
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

test("злиття: збій цільового select — звичайний upsert з попередженням (користувача не блокуємо)", async () => {
  const a = await seededWorld({ failTargeted: true });
  await a.s2.save([pin("a", { text: "мій" })]);
  assert.equal(upsertsOf(a.w)[0].rows[0].text, "мій");
  assert.ok(a.w.warnings.some((m) => m.includes("merge check failed")));
  assert.equal(a.s2.load()[0].text, "мій");
});

test("воскресіння: пін, який колега видалив, не пишеться назад, зникає з load(), другий save його теж не вставляє; новий пін пишеться", async () => {
  const { w, s2, seen, st } = await seededWorld({ targeted: () => [] });
  await s2.save([pin("a", { text: "мій" }), pin("new")]);
  assert.equal(w.targetedCalls().length, 1);
  assert.deepEqual(plain(upsertsOf(w)[0].rows.map((r) => r.id)), ["new"], "лише новий; `a` видалено колегою");
  assert.deepEqual(plain(s2.load().map((c) => c.id)), ["new"]);
  assert.deepEqual(plain(seen.at(-1).map((c) => c.id)), ["new"], "споживачі бачать зникнення");
  assert.deepEqual(snapOf(st).rows.map((r) => r.id), ["new"]);
  await s2.save([pin("a", { text: "ще раз" }), pin("new")]);       // коментатор тримає `a` як _pending і шле знову
  assert.equal(upsertsOf(w).length, 1, "видалений id фільтрується завжди");
  assert.deepEqual(plain(s2.load().map((c) => c.id)), ["new"]);
});

test("воскресіння: усі змінені рядки видалені колегою — upsert не робиться", async () => {
  const { w, s2 } = await seededWorld({ targeted: () => [] });
  await s2.save([pin("a", { text: "мій" })]);
  assert.equal(upsertsOf(w).length, 0);
  assert.deepEqual(plain(s2.load()), []);
});

test("наздоганяюче читання: невдале чи витіснене — перепланується через TTL; витіснене читання realtime його не вбиває", async () => {
  const a = await seededWorld();
  a.w.opts.failSelect = true;
  a.w.runTimers();
  await settle();
  assert.equal(a.w.selectCalls().length, 2, "спроба була й впала");
  const again = a.w.pending();
  assert.equal(again.length, 1, "перепланувано");
  assert.equal(again[0].ms, TTL);
  a.w.opts.failSelect = false;
  a.w.runTimers();
  await settle();
  assert.equal(a.w.selectCalls().length, 3);
  assert.equal(a.w.pending().length, 0, "вдале читання — кінець");
  const c = await seededWorld();
  c.w.opts.failSelect = true;                             // невдале realtime-читання теж не скасовує наздоганяючого
  await fireOnly(c.w, { eventType: "UPDATE", new: row("a", { text: "чуже" }) }, 120, 1);
  assert.equal(c.w.selectCalls().length, 2);
  assert.ok(c.w.pending().some((t) => t.ms === TTL - 30000), "наздоганяюче досі чекає");
  const b = await seededWorld();
  b.w.opts.manualSelect = true;
  const catchT = b.w.pending().find((t) => t.ms === TTL - 30000);
  catchT.live = false; catchT.fn();                       // наздоганяюче вилетіло й чекає відповіді
  b.w.channels[1].handlers[0].cb({ eventType: "UPDATE", new: row("a", { text: "чуже" }) });
  b.w.pending().find((t) => t.ms === 120).fn();            // realtime-читання витісняє його (seq)
  await settle();
  b.w.pendingSelects[0]({ data: [row("a")], error: null });  // відповідь витісненого
  await settle();
  assert.equal(b.w.pending().filter((t) => t.ms === TTL).length, 1, "витіснене наздоганяюче перепланувано");
});

test("черга save: два записи одного рядка, у першого повільна звірка — upsert-и йдуть у порядку викликів, у кеші новіший", async () => {
  const { w, s2 } = await seededWorld({ gateTargeted: true, targeted: () => [row("a")] });
  const p1 = s2.save([pin("a", { text: "перший" })]);
  const p2 = s2.save([pin("a", { text: "другий" })]);
  for (let i = 0; i < 30 && w.pendingTargeted.length + upsertsOf(w).length < 2; i += 1) {
    await settle();
    const r = w.pendingTargeted.pop();                    // відповідаємо з КІНЦЯ: без черги другий випередив би перший
    if (r) r();
  }
  await Promise.all([p1, p2]);
  assert.deepEqual(plain(upsertsOf(w).map((u) => u.rows[0].text)), ["перший", "другий"]);
  assert.equal(s2.load()[0].text, "другий");
  await s2.save([pin("a", { text: "другий" })]);
  assert.equal(upsertsOf(w).length, 2, "written тримає новіший рядок");
});

test("черга save: відмова одного запису не ламає черги; промис кожного — власний", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st, failUpserts: 3 });
  const s = w.create();
  await s.ready;
  const p1 = s.save([pin("a", { text: "х" })]);
  const p2 = s.save([pin("a", { text: "у" })]);
  const r1 = drive(w, p1).then(() => "ok", () => "fail");
  assert.equal(await r1, "fail");
  assert.equal(await drive(w, p2).then(() => "ok", () => "fail"), "ok");
  assert.equal(upsertsOf(w).at(-1).rows[0].text, "у");
});

test("злиття: стан закриття — одна одиниця (status+resolved_v+resolve_reason): мішаної трійки не буває", async () => {
  const base = { status: "resolved", resolved_v: 2, resolve_reason: "R" };
  const theirs = row("a", { status: "open", resolved_v: null, resolve_reason: null });
  const st = fakeStorage();
  const w = world({ rows: [row("a", base)], storage: st, targeted: () => [theirs] });
  await w.create().ready;
  w.clock += 10;
  const s2 = w.create();
  await s2.ready;
  /* Ми змінили лише причину; вони перевідкрили (змінили всю трійку). Обидві сторони змінили трійку → наша ЦІЛА. */
  await s2.save([pin("a", { status: "resolved", resolvedV: 2, resolveReason: "R2" })]);
  const r = upsertsOf(w)[0].rows[0];
  assert.deepEqual([r.status, r.resolved_v, r.resolve_reason], ["resolved", 2, "R2"]);
  /* Ми правили лише текст (трійка = база) → їхня трійка ЦІЛА. */
  const w2 = world({ rows: [row("a", base)], storage: fakeStorage(), targeted: () => [theirs] });
  await w2.create().ready;
  w2.clock += 10;
  const t2 = w2.create();
  await t2.ready;
  await t2.save([pin("a", { ...{ status: "resolved", resolvedV: 2, resolveReason: "R" }, text: "мій" })]);
  const r2 = upsertsOf(w2)[0].rows[0];
  assert.deepEqual([r2.status, r2.resolved_v, r2.resolve_reason, r2.text], ["open", null, null, "мій"]);
});

test("звірка один раз: два save одного рядка до повного читання — один цільовий select", async () => {
  const { w, s2 } = await seededWorld({ targeted: () => [row("a")] });
  await s2.save([pin("a", { text: "1" })]);
  await s2.save([pin("a", { text: "2" })]);
  assert.equal(w.targetedCalls().length, 1);
  assert.equal(upsertsOf(w).length, 2);
  await s2.save([pin("a", { text: "2" }), pin("b")]);
  assert.equal(w.targetedCalls().length, 1, "`b` без written — звіряти нема з чим, а `a` уже звірено");
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

/* ------------------------------------------------------------------------------------- таймаут мережі й повторне сповіщення */

/** Виконати лише таймери із затримкою `ms`. */
const runMs = (w, ms) => { for (const t of w.pending().filter((x) => x.ms === ms)) { t.live = false; t.fn(); } };

test("таймаут: завислий upsert відхиляє save після 3 спроб; наступний у черзі save виконується й вдається; таймери не течуть", async () => {
  const w = world({ rows: [row("a")], storage: fakeStorage(), hangUpserts: 3 });
  const s = w.create();
  await s.ready;
  const p1 = s.save([pin("a", { text: "х" })]);
  const p2 = s.save([pin("a", { text: "у" })]);
  let first = null;
  p1.then(() => { first = "ok"; }, (e) => { first = e.message; });
  for (let i = 0; i < 60 && first === null; i += 1) {
    await settle();
    runMs(w, 20000); runMs(w, 300); runMs(w, 600);        // таймаут завислої спроби, потім затримка повтору
  }
  assert.match(first, /timeout/);
  await drive(w, p2);
  assert.equal(upsertsOf(w).at(-1).rows[0].text, "у", "наступний запис пройшов");
  assert.equal(w.pending().length, 0, "після завершення живих таймерів нема");
});

test("таймаут: завислий precheck → звичайний upsert (як помилка звірки)", async () => {
  const { w, s2 } = await seededWorld({ gateTargeted: true });
  const p = s2.save([pin("a", { text: "мій" })]);
  for (let i = 0; i < 20 && !upsertsOf(w).length; i += 1) { await settle(); runMs(w, 20000); }
  await p;
  assert.equal(upsertsOf(w)[0].rows[0].text, "мій");
  assert.ok(w.warnings.some((m) => m.includes("merge check failed")));
});

test("close() здає завислий запит, а не лишає таймер", async () => {
  const { w, s2 } = await seededWorld({ gateTargeted: true });
  const p = s2.save([pin("a", { text: "мій" })]);
  await settle();
  s2.close();
  await p.catch(() => {});
  assert.equal(w.pending().filter((t) => t.ms === 20000).length, 0);
});

test("повторне сповіщення: після save, що відкинув видалене колегою, підписник на наступному тіку отримує список без нього", async () => {
  const { w, s2, seen } = await seededWorld({ targeted: () => [] });
  await s2.save([pin("a", { text: "мій" }), pin("new")]);
  await settle();
  const n = seen.length;
  assert.ok(w.pending().some((t) => t.ms === 0), "друге сповіщення заплановано");
  runMs(w, 0);
  assert.equal(seen.length, n + 1);
  assert.deepEqual(plain(seen.at(-1).map((c) => c.id)), ["new"]);
  const ok = await seededWorld();
  await ok.s2.save([pin("a", { text: "x" })]);
  assert.ok(!ok.w.pending().some((t) => t.ms === 0), "без видаленого — другого сповіщення нема");
});

/* ------------------------------------------------------------------------------------------ відповіді (comment_replies, 0.34) */

/** Рядок `comment_replies` так, як його віддає PostgREST. */
const rrow = (id, cid, over = {}) => ({
  id, comment_id: cid, project_id: CHANNEL, author: "Іра", text: `відповідь ${id}`, ts: "20.11.2026 10:00",
  edited_ts: null, agent: false, created_at: "2026-11-20T10:00:00Z", ...over,
});
/** Відповідь у формі коментатора. */
const rep = (id, over = {}) => ({ id, author: "Іра", text: `відповідь ${id}`, ts: "20.11.2026 10:00", ...over });
const repUps = (w) => w.calls.filter((c) => c.op === "upsert" && c.table === "comment_replies");
const comUps = (w) => w.calls.filter((c) => c.op === "upsert" && c.table === "comments");
const deletes = (w) => w.calls.filter((c) => c.op === "delete");

test("відповіді: читаються обидві таблиці; відповіді — за created_at, липнуть до коментаря за comment_id, сироти зникають", async () => {
  const w = world({ rows: [row("a"), row("b"), row("c")], replies: [rrow("r1", "a"), rrow("r2", "b"), rrow("r3", "a"), rrow("ox", "ghost")] });
  const s = w.create();
  await s.ready;
  assert.deepEqual(plain(w.repliesSelects()), [{ op: "select", table: "comment_replies", cols: "*", filters: [["eq", "project_id", CHANNEL]], order: ["created_at", "id"] }]);
  assert.equal(w.selectCalls().length, 1);
  const [a, b, c] = plain(s.load());
  assert.deepEqual(a.replies.map((r) => r.id), ["r1", "r3"], "порядок — як віддала база");
  assert.deepEqual(b.replies.map((r) => r.id), ["r2"]);
  assert.ok(!("replies" in c), "коментар без відповідей не отримує поля replies");
  assert.deepEqual(a.replies[0], { id: "r1", author: "Іра", text: "відповідь r1", ts: "20.11.2026 10:00" }, "без editedTs/agent, коли їх нема");
  assert.ok(!JSON.stringify(s.load()).includes("ox"), "сирота не показується");
  assert.equal(s.supportsReplies, true);
  assert.equal(s.repliesDown, null);
  assert.equal(Object.keys(a).filter((k) => k !== "replies").length, 11, "рядок коментаря лишився 11 полів");
});

test("відповіді: таблиці нема (PGRST205 / 42P01 / HTTP 404) — коментарі на місці, supportsReplies=false, repliesDown='no-replies-schema', save не чіпає comment_replies, каналу clr- нема", async () => {
  for (const f of [undefined, { error: { code: "42P01", message: "relation does not exist" } }, { top: { status: 404 }, error: { message: "Not Found" } }]) {
    const w = world({ rows: [row("a")], ...(f ? { failReplies: f } : {}) });
    const s = w.create();
    await s.ready;
    assert.deepEqual(s.load().map((c) => c.id), ["a"]);
    assert.equal(s.loadError, null, "відповіді не псують loadError коментарів");
    assert.equal(s.supportsReplies, false);
    assert.equal(s.repliesDown, "no-replies-schema");
    assert.deepEqual(w.channels.map((ch) => ch.name), ["cl-" + CHANNEL]);
    await s.save([pin("a", { replies: [rep("r1")] }), pin("b")]);
    assert.equal(w.calls.filter((c) => c.table === "comment_replies" && c.op !== "select").length, 0);
    assert.equal(comUps(w).length, 1, "лише новий коментар b");
    await s.remove(["a"]);
    assert.equal(deletes(w).length, 1);
    assert.equal(deletes(w)[0].table, "comments");
  }
});

test("відповіді: інша помилка читання — repliesDown = її повідомлення, коментарі цілі, каналу clr- нема", async () => {
  const w = world({ rows: [row("a")], failReplies: "квота вичерпана" });
  const s = w.create();
  await s.ready;
  assert.equal(s.repliesDown, "квота вичерпана");
  assert.equal(s.supportsReplies, false);
  assert.deepEqual(s.load().map((c) => c.id), ["a"]);
  assert.equal(s.loadError, null);
  assert.equal(w.channels.length, 1);
});

test("відповіді: помилка читання КОМЕНТАРІВ — як раніше (loadError), результат відповідей ігнорується", async () => {
  const w = world({ rows: [row("a")], failSelect: true, replies: [rrow("r1", "a")] });
  const s = w.create();
  await s.ready;
  assert.equal(s.loadError, "select boom");
  assert.deepEqual(plain(s.load()), []);
  assert.equal(s.supportsReplies, false);
  assert.equal(w.channels.length, 1);
});

test("відповіді, запис різницею: нова відповідь до незмінного коментаря — рівно один upsert у comment_replies і жодного в comments", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")] });
  const s = w.create();
  await s.ready;
  const list = plain(s.load());
  await s.save(list);
  assert.equal(w.calls.filter((c) => c.op !== "select").length, 0, "без змін — без запитів");
  list[0].replies.push(rep("r2", { _pending: true, junk: 1 }));
  await s.save(list);
  assert.equal(comUps(w).length, 0);
  assert.equal(repUps(w).length, 1);
  assert.deepEqual(plain(repUps(w)[0].rows), [{ id: "r2", comment_id: "a", project_id: CHANNEL, author: "Іра", text: "відповідь r2", ts: "20.11.2026 10:00", edited_ts: null, agent: false }],
    "лише відомі поля: службові _pending/junk не доходять до бази");
  assert.deepEqual(plain(repUps(w)[0].opts), { onConflict: "id" });
  await s.save(list);
  assert.equal(repUps(w).length, 1, "записане вдруге не йде");
});

test("відповіді, запис різницею: правка тексту (editedTs) — один upsert лише цього рядка; видалення — delete in('id') у межах каналу", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a"), rrow("r2", "a")] });
  const s = w.create();
  await s.ready;
  const list = plain(s.load());
  list[0].replies[0].text = "виправлено";
  list[0].replies[0].editedTs = "20.11.2026 11:00";
  await s.save(list);
  assert.equal(repUps(w).length, 1);
  assert.deepEqual(plain(repUps(w)[0].rows.map((r) => [r.id, r.text, r.edited_ts])), [["r1", "виправлено", "20.11.2026 11:00"]]);
  list[0].replies = list[0].replies.filter((r) => r.id !== "r2");
  await s.save(list);
  assert.equal(repUps(w).length, 1);
  assert.deepEqual(plain(deletes(w)), [{ op: "delete", table: "comment_replies", filters: [["in", "id", ["r2"]], ["eq", "project_id", CHANNEL]] }]);
  await s.save(list);
  assert.equal(deletes(w).length, 1, "видалене вдруге не йде");
  list[0].replies = [];
  await s.save(list);
  assert.deepEqual(plain(deletes(w).at(-1).filters[0]), ["in", "id", ["r1"]]);
});

test("відповіді: видалення пачками по ≤100 id; відповіді коментаря, якого нема в списку save, не чіпаються", async () => {
  const many = Array.from({ length: 150 }, (_, i) => rrow(`r${i}`, "a"));
  const w = world({ rows: [row("a"), row("b")], replies: [...many, rrow("rb", "b")] });
  const s = w.create();
  await s.ready;
  const a = plain(s.load())[0];
  a.replies = [];
  await s.save([a]);                                   // b у списку нема — його відповідь лишається
  const d = deletes(w);
  assert.deepEqual(d.map((q) => q.filters[0][2].length), [100, 50]);
  assert.ok(d.every((q) => q.table === "comment_replies" && !q.filters[0][2].includes("rb")));
});

test("відповіді агента: agent:true доходить туди й назад; незмінена відповідь агента не переписується", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a", { agent: true }), rrow("r2", "a")] });
  const s = w.create();
  await s.ready;
  const list = plain(s.load());
  assert.equal(list[0].replies[0].agent, true);
  assert.ok(!("agent" in list[0].replies[1]), "agent лише коли true");
  await s.save(list);
  assert.equal(repUps(w).length, 0, "agent:true не робить рядок «зміненим»");
  list[0].replies.push(rep("r3", { agent: true }));
  await s.save(list);
  assert.equal(repUps(w)[0].rows[0].agent, true);
  assert.equal(s.load()[0].replies[2].agent, true);
});

test("відповіді: відповідь без рядкового id у сховище не потрапляє", async () => {
  const w = world({ rows: [row("a")], replies: [] });
  const s = w.create();
  await s.ready;
  await s.save([pin("a", { replies: [{ author: "x", text: "без id" }, { id: 5, text: "число" }, rep("ok")] })]);
  assert.deepEqual(plain(repUps(w)[0].rows.map((r) => r.id)), ["ok"]);
});

test("відповіді: збій upsert відповідей (3 спроби) — save відхиляється, наступний save шле знову; коментарі, що вже пішли, вважаються записаними", async () => {
  const w = world({ rows: [row("a")], replies: [], failRepliesUpserts: 3 });
  const s = w.create();
  await s.ready;
  const list = [pin("a", { text: "нове", replies: [rep("r1")] })];
  await assert.rejects(drive(w, s.save(list)), /replies save failed/);
  assert.equal(comUps(w).length, 1);
  assert.equal(repUps(w).length, 3);
  await s.save(list);
  assert.equal(comUps(w).length, 1, "коментар уже записано — вдруге не йде");
  assert.equal(repUps(w).length, 4);
});

test("відповіді: збій видалення відповіді — warn і відхилений save; наступний save повторює видалення", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")], failRepliesDelete: true });
  const s = w.create();
  await s.ready;
  const list = plain(s.load());
  list[0].replies = [];
  await assert.rejects(s.save(list), /replies save failed/);
  assert.ok(w.warnings.some((m) => m.includes("delete boom")));
  w.opts.failRepliesDelete = false;
  await s.save(list);
  assert.equal(deletes(w).length, 2);
});

test("відповіді: remove([id]) спершу видаляє відповіді (comment_id, у межах каналу), потім коментар", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")] });
  const s = w.create();
  await s.ready;
  await s.remove(["a"]);
  assert.deepEqual(plain(deletes(w)), [
    { op: "delete", table: "comment_replies", filters: [["in", "comment_id", ["a"]], ["eq", "project_id", CHANNEL]] },
    { op: "delete", table: "comments", filters: [["in", "id", ["a"]], ["eq", "project_id", CHANNEL]] },
  ]);
  assert.deepEqual(s.load(), []);
  await s.save([pin("a", { replies: [rep("r1")] })]);
  assert.equal(repUps(w).length, 0, "ні коментар, ні його відповіді застарілим save не воскресають");
  assert.equal(upserts(w).length, 0);
});

test("відповіді: remove багатьох коментарів — відповіді пачками по ≤10 id, усі ДО видалення коментарів", async () => {
  const w = world({ rows: [row("a")], replies: [] });
  const s = w.create();
  await s.ready;
  const ids = Array.from({ length: 25 }, (_, i) => `c${i}`);
  await s.remove(ids);
  const d = deletes(w);
  assert.deepEqual(d.map((q) => [q.table, q.filters[0][2].length]), [["comment_replies", 10], ["comment_replies", 10], ["comment_replies", 5], ["comments", 25]]);
});

test("відповіді: збій видалення відповідей НЕ блокує видалення коментаря (осиротіла відповідь нешкідлива)", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")], failRepliesDelete: true });
  const s = w.create();
  await s.ready;
  await s.remove(["a"]);
  assert.deepEqual(deletes(w).map((q) => q.table), ["comment_replies", "comment_replies", "comments"], "за comment_id, запасний за id, коментар");
  assert.deepEqual(plain(s.load()), []);
  assert.ok(w.warnings.some((m) => m.includes("replies delete failed")));
});

test("відповіді, realtime: окремий канал clr-<канал> лише після вдалого читання; канал коментарів — рівно одна привʼязка на comments", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")] });
  const s = w.create();
  assert.deepEqual(w.channels.map((c) => c.name), ["cl-" + CHANNEL], "до читання відповідей каналу відповідей нема");
  await s.ready;
  assert.deepEqual(w.channels.map((c) => c.name), ["cl-" + CHANNEL, "clr-" + CHANNEL]);
  assert.equal(w.channels[0].handlers.length, 1, "на каналі коментарів — рівно одна привʼязка");
  assert.deepEqual(plain(w.channels[0].handlers[0].filter), { event: "*", schema: "public", table: "comments" });
  assert.equal(w.channels[1].handlers.length, 1);
  assert.equal(w.channels[1].handlers[0].type, "postgres_changes");
  assert.deepEqual(plain(w.channels[1].handlers[0].filter), { event: "*", schema: "public", table: "comment_replies" });
  assert.equal(w.channels[1].subscribed, 1);
  await drive(w, s.refresh());
  w.clock += TTL;
  await drive(w, s.refresh());
  assert.equal(w.channels.length, 2, "повторні читання канал не множать");
});

test("відповіді, realtime: подія чужого каналу ігнорується; свого — одне перечитування після згладжування; DELETE за id відповіді; невідома форма — перечитує", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")] });
  const s = w.create();
  await s.ready;
  const cb = w.channels[1].handlers[0].cb;
  const fireR = async (p) => {
    const before = w.selectCalls().length;
    cb(p);
    const waited = w.pending().some((t) => t.ms === 120);
    w.runTimers();
    await settle();
    return [w.selectCalls().length - before, waited];
  };
  assert.deepEqual(await fireR({ eventType: "INSERT", new: rrow("rx", "a", { project_id: "інший" }) }), [0, false], "чужий канал");
  assert.deepEqual(await fireR({ eventType: "INSERT", new: rrow("r9", "a") }), [1, true], "свій INSERT — після debounce");
  assert.deepEqual(await fireR({ eventType: "DELETE", old: { id: "r1" } }), [1, true], "DELETE відомої відповіді");
  assert.deepEqual(await fireR({ eventType: "DELETE", old: { id: "чужа" } }), [0, false]);
  assert.deepEqual(await fireR({}), [1, true], "невідома форма");
  assert.equal(w.repliesSelects().length, 4, "кожне перечитування читає й відповіді");
});

test("відповіді, realtime: луна власного запису (INSERT/UPDATE, що збігається з written) перечитування не планує; чужа правка — планує", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")] });
  const s = w.create();
  await s.ready;
  const list = plain(s.load());
  list[0].replies.push(rep("r2", { agent: true }));
  await s.save(list);
  const cb = w.channels[1].handlers[0].cb;
  cb({ eventType: "INSERT", new: rrow("r2", "a", { agent: true }) });
  assert.equal(w.pending().filter((t) => t.ms === 120).length, 0, "власна луна");
  cb({ eventType: "UPDATE", new: rrow("r2", "a", { agent: true, text: "чуже" }) });
  assert.equal(w.pending().filter((t) => t.ms === 120).length, 1, "чужа правка");
});

test("відповіді, realtime: close() знімає обидва канали й закриває сокет; подія після close нічого не питає", async () => {
  const w = world({ rows: [row("a")], replies: [] });
  const s = w.create();
  await s.ready;
  s.close();
  await settle();
  assert.deepEqual(w.removedChannels, [w.channels[0], w.channels[1]]);
  assert.equal(w.disconnects, 1);
  w.channels[1].handlers[0].cb({ eventType: "INSERT", new: rrow("r9", "a") });
  assert.equal(w.pending().length, 0);
  const w2 = world({ rows: [row("a")] });
  const s2 = w2.create();
  await s2.ready;
  s2.close();
  await settle();
  assert.deepEqual(w2.removedChannels, [w2.channels[0]], "без таблиці відповідей — один канал");
});

test("відповіді, знімок: старий формат (без масиву replies) не засіває — повне читання", async () => {
  const st = fakeStorage();
  st.m.set(SNAP_KEY, JSON.stringify({ t: 1_000_000, rows: [row("old")] }));
  const w = world({ rows: [row("new")], replies: [], storage: st });
  const s = w.create();
  await s.ready;
  assert.equal(w.selectCalls().length, 1);
  assert.deepEqual(s.load().map((c) => c.id), ["new"]);
  assert.ok(Array.isArray(snapOf(st).replies), "після читання знімок — уже нового формату");
});

test("відповіді, знімок: новий формат засіває коментарі й відповіді без читання; відкриває clr-; written відповідей засіяно", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a", { agent: true }), rrow("ox", "ghost")], storage: st });
  await w.create().ready;
  assert.equal(snapOf(st).replies.length, 1, "знімок — лише відповіді, що мають коментар (сирота не зберігається)");
  assert.equal(snapOf(st).rd, null);
  w.clock += 30000;
  const s2 = w.create();
  await s2.ready;
  assert.equal(w.selectCalls().length, 1);
  assert.equal(w.repliesSelects().length, 1, "знімок свіжий — відповіді теж не читаються");
  assert.equal(s2.supportsReplies, true);
  assert.equal(s2.repliesDown, null);
  assert.deepEqual(plain(s2.load())[0].replies.map((r) => [r.id, r.agent]), [["r1", true]]);
  assert.deepEqual(w.channels.map((c) => c.name), ["cl-" + CHANNEL, "clr-" + CHANNEL, "cl-" + CHANNEL, "clr-" + CHANNEL]);
  await s2.save(plain(s2.load()));
  assert.equal(w.calls.filter((c) => c.op !== "select").length, 0, "written відповідей засіяно: без змін — без запитів");
  const list = plain(s2.load());
  list[0].replies.push(rep("r2"));
  await s2.save(list);
  assert.equal(repUps(w).length, 1);
  assert.deepEqual(snapOf(st).replies.map((r) => r.id), ["r1", "r2"], "власний запис оновлює відповіді знімка (t не чіпаємо)");
});

test("відповіді, знімок: rd='no-replies-schema' — supportsReplies=false, repliesDown, каналу clr- нема, save відповідей не пише", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], storage: st });
  await w.create().ready;
  assert.equal(snapOf(st).rd, "no-replies-schema");
  assert.deepEqual(snapOf(st).replies, []);
  w.clock += 30000;
  const s2 = w.create();
  await s2.ready;
  assert.equal(s2.supportsReplies, false);
  assert.equal(s2.repliesDown, "no-replies-schema");
  assert.deepEqual(w.channels.map((c) => c.name), ["cl-" + CHANNEL, "cl-" + CHANNEL]);
  await s2.save([pin("a", { replies: [rep("r1")] })]);
  assert.equal(repUps(w).length, 0);
  const st2 = fakeStorage();
  st2.m.set(SNAP_KEY, JSON.stringify({ t: 1_000_000, rows: [row("a")], replies: [rrow("r1", "a")], rd: null }));
  const w3 = world({ rows: [], storage: st2 });
  const s3 = w3.create();
  await s3.ready;
  assert.equal(w3.calls.filter((c) => c.op === "select").length, 0, "рукотворний знімок нового формату засіває");
  assert.equal(s3.load()[0].replies[0].id, "r1");
});

test("відповіді: злиття (adopted) зберігає replies коментаря й пише нові відповіді", async () => {
  const { w, s2 } = await seededWorld({ replies: [rrow("r1", "a")], targeted: () => [row("a", { status: "resolved", resolved_v: 3 })] });
  const list = plain(s2.load());
  list[0].text = "мій";
  list[0].replies.push(rep("r2"));
  await s2.save(list);
  const c = s2.load()[0];
  assert.deepEqual([c.text, c.status], ["мій", "resolved"], "злиття відбулось");
  assert.deepEqual(plain(c.replies.map((r) => r.id)), ["r1", "r2"], "відповіді пережили злиття");
  assert.equal(repUps(w).length, 1);
  assert.equal(repUps(w)[0].rows[0].id, "r2");
});

test("відповіді: remove — коли DELETE за comment_id відхилено (сторож 100 рядків), відповіді, відомі адаптеру, видаляються за id пачками ≤100, а коментар усе одно видаляється", async () => {
  const many = Array.from({ length: 250 }, (_, i) => rrow(`r${i}`, "a"));
  const w = world({ rows: [row("a"), row("b")], replies: [...many, rrow("rb", "b")], failRepliesByOwner: true });
  const s = w.create();
  await s.ready;
  await s.remove(["a"]);
  const d = deletes(w);
  assert.deepEqual(d.map((q) => [q.table, q.filters[0][1], q.filters[0][2].length]),
    [["comment_replies", "comment_id", 1], ["comment_replies", "id", 100], ["comment_replies", "id", 100], ["comment_replies", "id", 50], ["comments", "id", 1]]);
  assert.ok(d.every((q) => q.filters.some((f) => f[0] === "eq" && f[1] === "project_id" && f[2] === CHANNEL)), "кожне видалення — у межах каналу");
  const ids = d.filter((q) => q.filters[0][1] === "id" && q.table === "comment_replies").flatMap((q) => q.filters[0][2]);
  assert.equal(new Set(ids).size, 250);
  assert.ok(!ids.includes("rb"), "відповідь іншого коментаря не зачеплено");
  assert.deepEqual(plain(s.load().map((c) => c.id)), ["b"]);
});

/* ------------------------------------------------------------------------------------------ гонки відповідей (ревʼю 13f6617) */

/** Крутити мікрозадачі й таймери, КРІМ згладжування realtime (120 мс): перечитування не стартує, доки тест не скаже. */
async function driveNoFetch(w, p) {
  let done = false;
  p.then(() => { done = true; }, () => { done = true; });
  for (let i = 0; i < 100 && !done; i += 1) {
    await settle();
    for (const t of w.pending().filter((x) => x.ms !== 120).sort((a, b) => a.ms - b.ms)) if (t.live) { t.live = false; t.fn(); }
  }
  await settle();
  return p;
}
const edit = (list, text) => { const l = plain(list); l[0].text = text; return l; };

test("гонка (a): застарілий save із черги НЕ видаляє чужу відповідь, що прийшла після його виклику; вона лишається в load() і сповіщається", async () => {
  let reps = [rrow("r1", "a")];
  const w = world({ rows: [row("a")], replies: () => reps, hangUpserts: 1 });
  const seen = [];
  const s = w.create({ onChange: (c) => seen.push(plain(c)) });
  await s.ready;
  const view = plain(s.load());
  const p1 = s.save(edit(view, "edit1"));                 // S1 у польоті (висить)
  await settle();
  const p2 = s.save(edit(view, "edit2"));                 // S2 у черзі; його список не знає r2
  reps = [rrow("r1", "a"), rrow("r2", "a")];              // інший клієнт додав r2
  await s.refresh();                                      // читання лягає, поки S1 висить
  assert.deepEqual(plain(s.load()[0].replies.map((r) => r.id)), ["r1", "r2"]);
  await drive(w, Promise.all([p1, p2]));
  assert.equal(deletes(w).length, 0, "r2 не видалено");
  assert.deepEqual(plain(s.load()[0].replies.map((r) => r.id)), ["r1", "r2"], "r2 лишилась у кеші після save");
  assert.deepEqual(plain(seen.at(-1)[0].replies.map((r) => r.id)), ["r1", "r2"], "і про це повідомлено");
});

test("власне додавання-потім-видалення через чергу: Rn, що ще не дійшла до бази, видаляється РІВНО раз після обох save", async () => {
  const w = world({ rows: [row("a")], replies: [], hangUpserts: 1 });
  const s = w.create();
  await s.ready;
  const l1 = edit(s.load(), "edit1"); l1[0].replies = [rep("rn")];
  const l2 = edit(s.load(), "edit2");                      // Rn уже видалено користувачем
  const p1 = s.save(l1);
  await settle();
  const p2 = s.save(l2);
  await drive(w, Promise.all([p1, p2]));
  assert.equal(repUps(w).length, 1);
  assert.deepEqual(plain(deletes(w)), [{ op: "delete", table: "comment_replies", filters: [["in", "id", ["rn"]], ["eq", "project_id", CHANNEL]] }]);
});

test("гонка (b) через читання: відповідь, видалену кимось (читання її вже не віддало), застарілий save не воскрешає", async () => {
  let reps = [rrow("r1", "a")];
  const w = world({ rows: [row("a")], replies: () => reps, hangUpserts: 1 });
  const s = w.create();
  await s.ready;
  const view = plain(s.load());
  const p1 = s.save(edit(view, "edit1"));
  await settle();
  const l2 = edit(view, "edit2"); l2[0].replies[0].text = "правка";
  const p2 = s.save(l2);
  reps = [];                                               // колега видалив r1
  await s.refresh();
  await drive(w, Promise.all([p1, p2]));
  assert.equal(repUps(w).length, 0, "r1 не воскресла");
  assert.equal(deletes(w).length, 0);
});

test("гонка (b) через подію realtime DELETE (old:{id}, без new) ДО перечитування: відповідь не воскресає", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")], hangUpserts: 1 });
  const s = w.create();
  await s.ready;
  const view = plain(s.load());
  const p1 = s.save(edit(view, "edit1"));
  await settle();
  const l2 = edit(view, "edit2"); l2[0].replies[0].text = "правка";
  const p2 = s.save(l2);
  w.channels[1].handlers[0].cb({ eventType: "DELETE", old: { id: "r1" } });
  await driveNoFetch(w, Promise.all([p1, p2]));
  assert.equal(repUps(w).length, 0, "r1 не воскресла");
  assert.equal(w.selectCalls().length, 1, "перечитування ще не було: працює надгробок від події");
});

test("remove + застарілий save із черги: ні коментар, ні його відповіді вдруге не пишуться", async () => {
  const w = world({ rows: [row("a"), row("b")], replies: [rrow("r1", "a")], hangUpserts: 1 });
  const s = w.create();
  await s.ready;
  const view = plain(s.load());
  const l1 = plain(view); l1[1].text = "edit-b";
  const p1 = s.save(l1);                                   // висить на коментарі b
  await settle();
  const l2 = plain(view); l2[0].text = "edit-a"; l2[0].replies[0].text = "правка";
  const p2 = s.save(l2);
  await s.remove(["a"]);
  await drive(w, Promise.all([p1, p2]));
  assert.ok(comUps(w).every((c) => c.rows.every((r) => r.id !== "a")), "коментар a не воскрес");
  assert.equal(repUps(w).length, 0, "відповідь r1 не воскресла");
  assert.deepEqual(plain(s.load().map((c) => c.id)), ["b"]);
});

test("знімок: відповідь, що впала при записі, у знімок НЕ потрапляє — після перезавантаження вона йде в базу", async () => {
  const st = fakeStorage();
  const w = world({ rows: [row("a")], replies: [], failRepliesUpserts: 3, storage: st });
  const s = w.create();
  await s.ready;
  const list = [pin("a", { replies: [rep("rX")] })];
  await assert.rejects(drive(w, s.save(list)), /replies save failed/);
  assert.deepEqual(snapOf(st).replies, [], "у знімку лише підтверджене базою");
  const w2 = world({ rows: [row("a")], replies: [], storage: st });
  const s2 = w2.create();
  await s2.ready;
  assert.equal(w2.selectCalls().length, 0, "знімок засіяв");
  await s2.save(plain(list));
  assert.deepEqual(plain(repUps(w2).map((c) => c.rows.map((r) => r.id))), [["rX"]]);
});

test("некоректна відповідь (author/text не рядок) пропускається з одним попередженням; решта зберігається, save завершується", async () => {
  const w = world({ rows: [row("a")], replies: [] });
  const s = w.create();
  await s.ready;
  const list = [pin("a", { replies: [{ id: "bad", author: "x" }, { id: "bad2", author: null, text: "t" }, rep("ok")] })];
  await s.save(list);
  assert.deepEqual(plain(repUps(w)[0].rows.map((r) => r.id)), ["ok"]);
  await s.save(list);
  assert.equal(repUps(w).length, 1);
  assert.equal(w.warnings.filter((m) => m.includes("bad")).length, 2, "по одному попередженню на id");
  list[0].replies = [{ id: "bad", author: "x" }];            // ok зникла, некоректна лишилась
  await s.save(list);
  assert.deepEqual(plain(deletes(w).map((q) => q.filters[0][2])), [["ok"]], "зниклу видаляємо як звичайно; некоректну несемо, її не чіпаємо");
});

test("тимчасова помилка читання відповідей: відомі відповіді лишаються (й на екрані), запис призупинено; після відновлення — норма й надгробок для видаленого за час збою", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")] });
  const s = w.create();
  await s.ready;
  w.opts.failReplies = "мережа лягла";
  await s.refresh();
  assert.equal(s.supportsReplies, false);
  assert.equal(s.repliesDown, "мережа лягла");
  assert.deepEqual(plain(s.load()[0].replies.map((r) => r.id)), ["r1"], "відповідь не зникла з кешу");
  const l = plain(s.load()); l[0].replies.push(rep("r2"));
  await assert.rejects(s.save(l), /replies unavailable/);
  assert.equal(repUps(w).length, 0, "поки лежить — відповіді не пишемо");
  w.opts.failReplies = false;
  w.opts.replies = [];                                     // r1 видалено за час збою
  await s.refresh();
  assert.equal(s.supportsReplies, true);
  assert.equal(s.repliesDown, null);
  const l2 = plain(l); l2[0].replies[0].text = "правка";
  await s.save(l2);
  assert.deepEqual(plain(repUps(w).map((c) => c.rows.map((r) => r.id))), [["r2"]], "r1 не воскресла (надгробок), r2 — нова");
});

test("відхилений (reject) проміс пачки видалення відповідей = помилка пачки: попередні пачки записано, наступний save шле лише решту", async () => {
  const many = Array.from({ length: 250 }, (_, i) => rrow(`r${i}`, "a"));
  const w = world({ rows: [row("a")], replies: many, rejectRepliesDeleteAt: 2 });
  const s = w.create();
  await s.ready;
  const l = plain(s.load()); l[0].replies = [];
  await assert.rejects(s.save(l), /replies save failed/);
  assert.deepEqual(deletes(w).map((q) => q.filters[0][2].length), [100, 100], "друга пачка відхилена, третьої нема");
  const first = new Set(deletes(w)[0].filters[0][2]);
  await s.save(l);
  const again = deletes(w).slice(2);
  assert.deepEqual(again.map((q) => q.filters[0][2].length), [100, 50]);
  assert.ok(again.every((q) => q.filters[0][2].every((id) => !first.has(id))), "перша пачка вже записана — вдруге не йде");
});

test("remove: відповіді видалено, а видалення коментаря впало — застарілий save не воскрешає ВІДПОВІДІ (надгробки)", async () => {
  const w = world({ rows: [row("a")], replies: [rrow("r1", "a")], failDelete: true });
  const s = w.create();
  await s.ready;
  const view = plain(s.load());
  await s.remove(["a"]);
  assert.ok(w.warnings.some((m) => m.includes("delete boom")));
  view[0].replies[0].text = "правка";
  await s.save(view);
  assert.equal(repUps(w).length, 0, "відповідь, яку ми щойно видалили, не пишеться знову");
});

/* ------------------------------------------------------------------------------------------ дрібні доробки після ревʼю 06f1328 */

test("невдале видалення відповіді повторюється: save, викликаний ДО збою, але виконаний після, видаляє її знову; відповідь не зʼявляється знову", async () => {
  const w = world({ rows: [row("a")], replies: [], hangUpserts: 1, failRepliesDeleteCount: 1 });
  const seen = [];
  const s = w.create({ onChange: (c) => seen.push(plain(c)) });
  await s.ready;
  const l1 = edit(s.load(), "e1"); l1[0].replies = [rep("rn")];
  const p1 = s.save(l1);
  await settle();
  const p2 = s.save(edit(s.load(), "e2"));               // без rn: видалення впаде
  const p3 = s.save(edit(s.load(), "e3"));               // викликаний ДО збою S2: у його базі rn нема
  const out = await drive(w, Promise.allSettled([p1, p2, p3]));
  assert.deepEqual(out.map((o) => o.status), ["fulfilled", "rejected", "fulfilled"]);
  assert.equal(deletes(w).length, 2, "спроба, що впала, і повтор");
  assert.deepEqual(plain(s.load()[0].replies || []), [], "відповідь не повернулась у кеш");
  assert.ok(seen.slice(1).every((c) => !(c[0].replies || []).some((r) => r.id === "rn")), "у жодному сповіщенні після першого rn не зʼявляється");
});

test("невдале видалення, що повторно падає: відповідь, яку користувач видалив, не «воскресає» в кеші як чужа", async () => {
  const w = world({ rows: [row("a")], replies: [], hangUpserts: 1, failRepliesDeleteCount: 2 });
  const s = w.create();
  await s.ready;
  const l1 = edit(s.load(), "e1"); l1[0].replies = [rep("rn")];
  const p1 = s.save(l1);
  await settle();
  const p2 = s.save(edit(s.load(), "e2"));
  const p3 = s.save(edit(s.load(), "e3"));
  const out = await drive(w, Promise.allSettled([p1, p2, p3]));
  assert.deepEqual(out.map((o) => o.status), ["fulfilled", "rejected", "rejected"]);
  assert.deepEqual(plain(s.load()[0].replies || []), [], "rn не повернулась");
  await s.save(edit(s.load(), "e4"));
  assert.equal(deletes(w).length, 3, "і наступний save знову пробує");
});

test("витіснене save-ом читання, запущене подією ззовні, перепланується: рівно одне ще читання, чужа зміна видна", async () => {
  const w = world({ rows: [], manualSelect: true });
  const s = w.create();
  await settle();
  w.pendingSelects[0]({ data: [row("a")], error: null });
  await s.ready;
  w.channels[0].handlers[0].cb({ eventType: "INSERT", new: { project_id: CHANNEL } });
  w.runTimers();
  await settle();
  assert.equal(w.pendingSelects.length, 2, "читання в польоті");
  await s.save([pin("a", { text: "моє" })]);             // save завершився, поки читання летіло
  w.pendingSelects[1]({ data: [row("a"), row("b")], error: null });   // відповідь витіснена: save збільшив seq
  await settle();
  assert.deepEqual(plain(s.load().map((c) => c.id)), ["a"], "витіснену відповідь не застосовано");
  assert.equal(w.pending().filter((t) => t.ms === 120).length, 1, "перечитування перепаковано в згладжування");
  w.runTimers();
  await settle();
  assert.equal(w.pendingSelects.length, 3, "рівно одне ще читання");
  w.pendingSelects[2]({ data: [row("a", { text: "моє" }), row("b")], error: null });
  await settle();
  assert.deepEqual(plain(s.load().map((c) => c.id)), ["a", "b"], "чужа зміна видна");
  assert.equal(w.pending().filter((t) => t.ms === 120).length, 0, "без циклу");
});

test("відповіді недоступні тимчасово: save з новою відповіддю ВІДХИЛЯЄТЬСЯ (коментарі записано), після відновлення відповідь іде в базу", async () => {
  const w = world({ rows: [row("a")], replies: [] });
  const s = w.create();
  await s.ready;
  w.opts.failReplies = "лежить";
  await s.refresh();
  const list = [pin("a", { text: "нове", replies: [rep("r1")] })];
  await assert.rejects(s.save(list), /replies unavailable/);
  assert.equal(comUps(w).length, 1, "коментар записано");
  assert.equal(repUps(w).length, 0);
  await assert.rejects(s.save(list), /replies unavailable/, "повтор під час збою знову відхиляється, а не мовчки ковтає");
  assert.equal(comUps(w).length, 1);
  w.opts.failReplies = false;
  await s.refresh();
  await s.save(list);
  assert.deepEqual(plain(repUps(w).map((c) => c.rows.map((r) => r.id))), [["r1"]]);
});

test("відповіді: таблиці нема назавжди — save з відповіддю завершується, у comment_replies нічого, попередження одне", async () => {
  const w = world({ rows: [row("a")] });
  const s = w.create();
  await s.ready;
  const list = [pin("a", { replies: [rep("r1")] })];
  await s.save(list);
  await s.save(list);
  assert.equal(w.calls.filter((c) => c.table === "comment_replies" && c.op !== "select").length, 0);
  assert.equal(w.warnings.filter((m) => m.includes("replies dropped")).length, 1);
});

test("повтор видалення знімається, коли застосоване читання вже не бачить відповіді: однойменна чужа відповідь, що зʼявилась згодом, не видаляється", async () => {
  let reps = [rrow("rn", "a")];
  const w = world({ rows: [row("a")], replies: () => reps, hangUpserts: 1, failRepliesDeleteCount: 1 });
  const s = w.create();
  await s.ready;
  const l0 = plain(s.load()); l0[0].replies = [];
  await assert.rejects(s.save(l0), /replies save failed/);          // видалення впало: rn у повторі
  reps = [];
  await s.refresh();                                               // база без rn: повторювати нічого
  const view = plain(s.load());
  const p1 = s.save(edit(view, "e1"));                              // висить
  await settle();
  const p2 = s.save(edit(view, "e2"));                              // не знає rn
  reps = [rrow("rn", "a")];                                        // rn зʼявилась знову (чужа)
  await s.refresh();
  await drive(w, Promise.all([p1, p2]));
  assert.equal(deletes(w).length, 1, "лише перша, що впала; нове видалення не йде");
  assert.deepEqual(plain(s.load()[0].replies.map((r) => r.id)), ["rn"]);
});
