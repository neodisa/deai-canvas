/**
 * Адаптер `supabase-comments` на СПРАВЖНІЙ вендореній збірці supabase-js 2.110.0 (`supabase.min.js`) — не на підставному
 * клієнті (`tests/supabase-comments-adapter.test.mjs`). Обидва файли модуля виконуються в `vm`-контексті в порядку
 * маніфесту, а мережа — заглушки `fetch` і `WebSocket` (з мінімальним протоколом realtime: join/leave/heartbeat/подія).
 *
 * Що це доводить, чого підставний клієнт довести не може:
 *   · ПРОВІД: які саме запити й заголовки шле справжній SDK (REST — адреса, `apikey`, `Authorization`, фільтр каналу в
 *     SELECT/upsert/DELETE; realtime — адреса сокета, тема `realtime:cl-<канал>`, `postgres_changes` на `comments` без фільтра);
 *   · ЖОДНИХ ВИТОКІВ: з `persistSession/autoRefreshToken/detectSessionInUrl: false` SDK не створює інтервалів, `BroadcastChannel`
 *     і записів сесії; а після `close()` — сокет закрито й жодного таймера не лишилось (віртуальний годинник дожито до тиші).
 * Таймери — віртуальні: `advance(ms)` виконує те, що настало, за порядком. Жодної мережі, жодного реального часу.
 */
import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "modules", "supabase-comments");
const BUNDLE = fs.readFileSync(path.join(DIR, "supabase.min.js"), "utf8");
const ADAPTER = fs.readFileSync(path.join(DIR, "adapter.js"), "utf8");
const MANIFEST = JSON.parse(fs.readFileSync(path.join(DIR, "module.json"), "utf8"));

const URL_ = "https://abcdefghijkl.supabase.co";
const KEY = "eyJhbGciOiJIUzI1NiJ9.TEST-payload.TEST-signature";
const CHANNEL = "deai/space-1/task-7";
const settle = () => new Promise((r) => setImmediate(r));

function world() {
  const w = { fetches: [], sockets: [], frames: [], intervals: 0, bcs: [], storage: [], listeners: [], timers: new Map(), now: 0, id: 1 };
  const add = (kind) => (fn, ms) => { const id = w.id++; w.timers.set(id, { kind, fn, ms, due: w.now + (ms || 0) }); if (kind === "interval") w.intervals += 1; return id; };
  const sandbox = {
    console, URL, URLSearchParams, TextEncoder, TextDecoder, AbortController, Headers, Request, Response, atob, btoa, queueMicrotask,
    setTimeout: add("timeout"), setInterval: add("interval"),
    clearTimeout: (id) => w.timers.delete(id), clearInterval: (id) => w.timers.delete(id),
    fetch: async (url, init = {}) => {
      w.fetches.push({ url: String(url), method: init.method || "GET", headers: Object.fromEntries(new Headers(init.headers)), body: init.body });
      if (String(url).includes("/rest/v1/comment_replies") && (init.method === "GET" || !init.method)) {
        if (w.replyRows === undefined) {                 // старий проєкт без replies.sql: PostgREST віддає 404 + PGRST205
          return new Response(JSON.stringify({ code: "PGRST205", details: null, hint: null, message: "Could not find the table 'public.comment_replies' in the schema cache" }),
            { status: 404, headers: { "content-type": "application/json" } });
        }
        return new Response(JSON.stringify(w.replyRows), { status: 200, headers: { "content-type": "application/json" } });
      }
      const rows = init.method === "GET" || !init.method ? w.rows : null;
      return new Response(rows === null ? null : JSON.stringify(rows), { status: rows === null ? 204 : 200, headers: { "content-type": "application/json" } });
    },
    WebSocket: class {
      constructor(url) { this.url = url; this.readyState = 0; w.sockets.push(this); setImmediate(() => { this.readyState = 1; this.onopen?.({}); }); }
      reply(jr, ref, topic, resp) { setImmediate(() => this.onmessage?.({ data: JSON.stringify([jr, ref, topic, "phx_reply", { status: "ok", response: resp }]) })); }
      send(data) {
        const [jr, ref, topic, event, payload] = JSON.parse(data);
        w.frames.push({ topic, event, payload });
        if (event === "phx_join") this.reply(jr, ref, topic, { postgres_changes: (payload.config.postgres_changes || []).map((b, i) => ({ ...b, id: i + 1 })) });
        else if (event === "phx_leave" || event === "heartbeat") this.reply(jr, ref, topic, {});
      }
      close() { this.readyState = 2; setImmediate(() => { this.readyState = 3; this.closed = true; this.onclose?.({ code: 1000 }); }); }
      push(topic, event, payload) { this.onmessage?.({ data: JSON.stringify([null, null, topic, event, payload]) }); }
    },
    localStorage: { getItem: (k) => { w.storage.push(k); return null; }, setItem: (k) => { w.storage.push(k); }, removeItem: (k) => { w.storage.push(k); } },
    BroadcastChannel: class { constructor(n) { w.bcs.push(n); } postMessage() {} close() {} addEventListener() {} },
    navigator: { userAgent: "vm" },
    document: { addEventListener: (t) => w.listeners.push(t), removeEventListener() {}, visibilityState: "visible", hidden: false },
    addEventListener: (t) => w.listeners.push(t), removeEventListener() {},
  };
  sandbox.window = sandbox; sandbox.self = sandbox; sandbox.globalThis = sandbox;
  w.rows = [];
  vm.createContext(sandbox);
  for (const name of MANIFEST.client) vm.runInContext(name === "supabase.min.js" ? BUNDLE : ADAPTER, sandbox, { filename: name });   // порядок маніфесту
  w.sandbox = sandbox;
  /** Віртуальний годинник: виконати все, що настає в найближчі `ms` (разом із тим, що воно ж і створить). */
  w.advance = async (ms) => {
    const end = w.now + ms;
    for (let guard = 0; guard < 500; guard += 1) {
      await settle();
      const due = [...w.timers].filter(([, t]) => t.due <= end).sort((a, b) => a[1].due - b[1].due)[0];
      if (!due) break;
      w.now = Math.max(w.now, due[1].due);
      if (due[1].kind === "timeout") w.timers.delete(due[0]); else due[1].due = w.now + due[1].ms;
      due[1].fn();
    }
    w.now = end;
    await settle();
  };
  return w;
}

const row = (id) => ({ id, project_id: CHANNEL, author: "A", text: id, status: "open", fp: {}, html_snapshot: null, meta: null, born_v: 1, resolved_v: null, resolve_reason: null, ts: "x" });

test("справжній SDK: проводом іде рівно те, що задумано (REST із ключем у заголовках і фільтром каналу, realtime без фільтра)", async () => {
  const w = world();
  w.rows = [row("a")];
  const s = w.sandbox.DeaiComments.create({ url: URL_, key: KEY, channel: CHANNEL });
  await w.advance(50);
  await s.ready;
  assert.deepEqual(Array.from(s.load(), (c) => c.id), ["a"]);
  const get = w.fetches.find((f) => f.url.includes("/rest/v1/comments?"));
  assert.equal(get.method, "GET");
  assert.equal(get.url, `${URL_}/rest/v1/comments?select=*&project_id=eq.${encodeURIComponent(CHANNEL)}&order=id.asc`);
  assert.equal(get.headers.apikey, KEY);
  assert.equal(get.headers.authorization, `Bearer ${KEY}`);
  assert.equal(w.sockets.length, 1);
  assert.equal(w.sockets[0].url, `wss://abcdefghijkl.supabase.co/realtime/v1/websocket?apikey=${KEY}&vsn=2.0.0`);
  const join = w.frames.find((f) => f.event === "phx_join");
  assert.equal(join.topic, `realtime:cl-${CHANNEL}`);
  assert.deepEqual(JSON.parse(JSON.stringify(join.payload.config.postgres_changes)), [{ event: "*", schema: "public", table: "comments" }],
    "підписка на всю таблицю без фільтра project_id: події DELETE несуть лише PK");
  await s.save([{ id: "a", author: "A", text: "a", status: "open", fp: {}, bornV: 1 }]);
  const post = w.fetches.find((f) => f.method === "POST");
  const pq = new w.sandbox.URL(post.url);
  assert.equal(pq.pathname, "/rest/v1/comments");
  assert.equal(pq.searchParams.get("on_conflict"), "id", "upsert за id");
  assert.match(post.headers.prefer, /resolution=merge-duplicates/);
  assert.equal(JSON.parse(post.body)[0].project_id, CHANNEL);
  await s.remove(["a"]);
  const del = w.fetches.find((f) => f.method === "DELETE");
  const q = new w.sandbox.URL(del.url).searchParams;
  assert.match(q.get("id"), /^in\.\(.*a.*\)$/);
  assert.equal(q.get("project_id"), `eq.${CHANNEL}`, "видалення — лише в межах каналу");
  s.close();
  await w.advance(2000);
});

test("справжній SDK: подія realtime доходить до адаптера й дає перечитування каналу", async () => {
  const w = world();
  const seen = [];
  const s = w.sandbox.DeaiComments.create({ url: URL_, key: KEY, channel: CHANNEL, onChange: (c) => seen.push(c.length) });
  await w.advance(50);
  assert.deepEqual(seen, [0]);
  w.rows = [row("a"), row("b")];
  w.sockets[0].push(`realtime:cl-${CHANNEL}`, "postgres_changes", { ids: [1], data: { schema: "public", table: "comments", type: "INSERT", commit_timestamp: "t", columns: [], errors: null, record: { id: "b" } } });
  await w.advance(200);
  assert.equal(w.fetches.filter((f) => f.method === "GET" && f.url.includes("/rest/v1/comments?")).length, 2);
  assert.deepEqual(seen, [0, 2]);
  s.close();
  await w.advance(2000);
});

test("справжній SDK без автентифікації користувача: жодного інтервалу, BroadcastChannel і запису сесії; після close — сокет закрито й таймерів нема", async () => {
  const w = world();
  const s = w.sandbox.DeaiComments.create({ url: URL_, key: KEY, channel: CHANNEL });
  await w.advance(50);
  await s.ready;
  assert.equal(w.intervals, 0, "жодного інтервалу (оновлення токена)");
  assert.deepEqual(w.bcs, [], "жодного BroadcastChannel");
  assert.deepEqual(w.storage.filter((k) => k.startsWith("sb-")), [], "сесію в сховище браузера не читаємо й не пишемо");
  assert.ok([...w.timers.values()].length > 0, "свідок: до close() SDK тримає таймери (серцебиття realtime)");
  s.close();
  await w.advance(11000);        // supabase-js `disconnect` лишає ОДНОРАЗОВИЙ порожній таймер на 10 с (не очищає його) — дожити й до нього
  assert.equal(w.sockets.length, 1);
  assert.equal(w.sockets[0].closed, true, "сокет realtime закрито");
  assert.deepEqual([...w.timers.values()].map((t) => `${t.kind}:${t.ms}`), [], "після close жодного таймера й інтервалу (серцебиття знято)");
  assert.ok(w.frames.some((f) => f.event === "phx_leave"), "канал залишено, а не обірвано");
});

test("справжній SDK: відповіді — таблиці нема (404 PGRST205) → repliesDown, без каналу clr-; таблиця є → читання за created_at,id і окремий канал", async () => {
  const w = world();
  w.rows = [row("a")];
  const s = w.sandbox.DeaiComments.create({ url: URL_, key: KEY, channel: CHANNEL });
  await w.advance(50);
  await s.ready;
  assert.equal(s.supportsReplies, false);
  assert.equal(s.repliesDown, "no-replies-schema", "supabase-js віддає code PGRST205 у error");
  assert.deepEqual(Array.from(s.load(), (c) => c.id), ["a"]);
  assert.deepEqual(w.frames.filter((f) => f.event === "phx_join").map((f) => f.topic), [`realtime:cl-${CHANNEL}`]);
  s.close();
  await w.advance(2000);
  const w2 = world();
  w2.rows = [row("a")];
  w2.replyRows = [{ id: "r1", comment_id: "a", project_id: CHANNEL, author: "B", text: "t", ts: "x", edited_ts: null, agent: false }];
  const s2 = w2.sandbox.DeaiComments.create({ url: URL_, key: KEY, channel: CHANNEL });
  await w2.advance(50);
  await s2.ready;
  assert.equal(s2.supportsReplies, true);
  assert.equal(s2.repliesDown, null);
  assert.equal(s2.load()[0].replies[0].id, "r1");
  const rq = w2.fetches.find((f) => f.url.includes("/rest/v1/comment_replies"));
  assert.equal(new w2.sandbox.URL(rq.url).searchParams.get("order"), "created_at.asc,id.asc");
  assert.equal(new w2.sandbox.URL(rq.url).searchParams.get("project_id"), `eq.${CHANNEL}`);
  const joins = w2.frames.filter((f) => f.event === "phx_join");
  assert.deepEqual(joins.map((f) => f.topic), [`realtime:cl-${CHANNEL}`, `realtime:clr-${CHANNEL}`]);
  assert.deepEqual(JSON.parse(JSON.stringify(joins[1].payload.config.postgres_changes)), [{ event: "*", schema: "public", table: "comment_replies" }]);
  s2.close();
  await w2.advance(2000);
});
