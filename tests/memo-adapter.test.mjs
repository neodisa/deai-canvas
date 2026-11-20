/**
 * Адаптер тестового модуля `memo-comments` (еталон ролі `comments`, 2b-2): контракт сховища CommentLayer
 * `{ready, load, save, remove, subscribe, close}` поверх `fetch(cfg.endpoint + '/c/' + encodeURIComponent(cfg.channel))`.
 *
 * Файл виконується в ізольованому `vm`-контексті з підставними `fetch` і таймерами: жодної мережі, жодного реального
 * часу. Окремо доводиться, що адаптер не створює інших глобальних імен, ніж `window.DeaiComments`.
 */
import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const FILE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "modules", "memo-comments", "adapter.js");
const SRC = fs.readFileSync(FILE, "utf8");

/** Контекст із підставним сервером: `server.rows` — що віддає GET; `server.calls` — усі запити. */
function world({ rows = [], failGet = false, failPost = false } = {}) {
  const server = { rows, calls: [], failGet, failPost };
  const timers = new Map();
  let nextTimer = 1;
  const sandbox = {
    fetch: async (url, opts = {}) => {
      server.calls.push({ url, method: opts.method || "GET", headers: opts.headers || null, body: opts.body ?? null });
      if (opts.method === "POST") {
        return { ok: !server.failPost, status: server.failPost ? 500 : 200, json: async () => ({ ok: true }) };
      }
      if (server.failGet) return { ok: false, status: 503, json: async () => ({}) };
      return { ok: true, status: 200, json: async () => server.rows };
    },
    setInterval: (fn, ms) => { const id = nextTimer++; timers.set(id, { fn, ms }); return id; },
    clearInterval: (id) => { timers.delete(id); },
  };
  sandbox.window = sandbox;                       // `window.DeaiComments = …` у браузері — глобальний обʼєкт
  const before = new Set(Object.keys(sandbox));
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: FILE });
  return { sandbox, server, timers, before, tick: async () => { for (const t of [...timers.values()]) await t.fn(); await settle(); } };
}
/* Масиви з `vm`-контексту мають СВІЙ `Array.prototype`: `deepStrictEqual` порівняв би прототипи. Тому — копії в нашому світі. */
const ids = (rows) => Array.from(rows, (c) => c.id);
const plain = (x) => JSON.parse(JSON.stringify(x));
const settle = () => new Promise((r) => setImmediate(r));
const cfg = (o = {}) => ({ endpoint: "http://127.0.0.1:4000/", channel: "deai/liga/t-1", ...o });
const pin = (id, text = "x") => ({ id, author: "A", text, status: "open", fp: {}, htmlSnapshot: null, meta: null, bornV: "1", resolvedV: null, resolveReason: null, ts: "19.10.2026" });

test("файл реєструє лише window.DeaiComments.create і не створює інших глобальних імен", () => {
  const w = world();
  assert.deepEqual([...Object.keys(w.sandbox)].filter((k) => !w.before.has(k)), ["DeaiComments"]);
  assert.deepEqual(Object.keys(w.sandbox.DeaiComments), ["create"]);
  assert.equal(typeof w.sandbox.DeaiComments.create, "function");
});

test("create: ready чекає на перше читання каналу з правильної адреси (без подвійного слеша, канал закодовано)", async () => {
  const w = world({ rows: [pin("a"), pin("b")] });
  const s = w.sandbox.DeaiComments.create(cfg());
  assert.deepEqual(plain(s.load()), [], "до ready кешу ще нема");
  await s.ready;
  assert.deepEqual(w.server.calls.map((c) => [c.method, c.url]), [["GET", "http://127.0.0.1:4000/c/deai%2Fliga%2Ft-1"]]);
  assert.deepEqual(ids(s.load()), ["a", "b"]);
  assert.deepEqual(Object.keys(s).sort(), ["close", "load", "ready", "remove", "save", "subscribe", "supportsReplies"]);
});

test("create: збій першого читання не валить ready — кеш порожній", async () => {
  const w = world({ failGet: true });
  const s = w.sandbox.DeaiComments.create(cfg());
  await s.ready;
  assert.deepEqual(plain(s.load()), []);
  const w2 = world({ rows: { not: "an array" } });                        // відповідь не масив — теж порожньо
  const s2 = w2.sandbox.DeaiComments.create(cfg());
  await s2.ready;
  assert.deepEqual(plain(s2.load()), []);
});

test("save: кеш і підписники оновлюються одразу, на сервер іде весь масив простим text/plain-запитом", async () => {
  const w = world();
  const seen = [];
  const s = w.sandbox.DeaiComments.create(cfg({ onChange: (rows) => seen.push(["cfg", rows.length]) }));
  await s.ready;
  s.subscribe((rows) => seen.push(["sub", rows.length]));
  const list = [pin("a"), pin("b")];
  const done = s.save(list);
  assert.deepEqual(ids(s.load()), ["a", "b"], "кеш — до відповіді сервера");
  assert.deepEqual(seen, [["sub", 2], ["cfg", 2]]);
  await done;
  const post = w.server.calls.at(-1);
  assert.deepEqual([post.method, post.url], ["POST", "http://127.0.0.1:4000/c/deai%2Fliga%2Ft-1"]);
  assert.match(post.headers["Content-Type"], /^text\/plain/, "text/plain — без CORS-preflight");
  assert.deepEqual(JSON.parse(post.body), { comments: list });
  list.push(pin("c"));                                                   // правка вхідного масиву не псує кеш
  assert.equal(s.load().length, 2);
});

test("save: відмова сервера — відхилений проміс", async () => {
  const w = world({ failPost: true });
  const s = w.sandbox.DeaiComments.create(cfg());
  await s.ready;
  await assert.rejects(s.save([pin("a")]), /save 500/);
});

test("remove: викидає названі id з кешу й шле їх на /remove", async () => {
  const w = world({ rows: [pin("a"), pin("b"), pin("c")] });
  const s = w.sandbox.DeaiComments.create(cfg());
  await s.ready;
  const seen = [];
  s.subscribe((rows) => seen.push(ids(rows)));
  const done = s.remove(["b", "zzz"]);
  assert.deepEqual(ids(s.load()), ["a", "c"]);
  assert.deepEqual(seen, [["a", "c"]]);
  await done;
  const post = w.server.calls.at(-1);
  assert.equal(post.url, "http://127.0.0.1:4000/c/deai%2Fliga%2Ft-1/remove");
  assert.deepEqual(JSON.parse(post.body), { ids: ["b", "zzz"] });
});

test("subscribe: один таймер на 1 с, опитування повідомляє лише про ЗМІНУ", async () => {
  const w = world({ rows: [pin("a")] });
  const s = w.sandbox.DeaiComments.create(cfg());
  await s.ready;
  const seen = [];
  s.subscribe((rows) => seen.push(ids(rows)));
  s.subscribe(() => {});
  assert.equal(w.timers.size, 1, "другий підписник не плодить таймерів");
  assert.equal([...w.timers.values()][0].ms, 1000);
  await w.tick();
  assert.deepEqual(seen, [], "нічого не змінилось — тиша");
  w.server.rows = [pin("a"), pin("n")];                                  // зовнішня зміна
  await w.tick();
  assert.deepEqual(seen, [["a", "n"]]);
  assert.deepEqual(ids(s.load()), ["a", "n"]);
  await w.tick();
  assert.deepEqual(seen, [["a", "n"]], "ті самі дані вдруге — тиша");
});

test("subscribe: опитування не перебиває запис у дорозі й переживає збій мережі", async () => {
  const w = world({ rows: [pin("a")] });
  const s = w.sandbox.DeaiComments.create(cfg());
  await s.ready;
  const seen = [];
  s.subscribe((rows) => seen.push(rows.length));
  let release;
  const gate = new Promise((r) => { release = r; });
  const realFetch = w.sandbox.fetch;
  w.sandbox.fetch = async (url, opts = {}) => { if (opts.method === "POST") await gate; return realFetch(url, opts); };
  const saving = s.save([pin("a"), pin("b")]);
  seen.length = 0;
  w.server.rows = [];                                                    // сервер ще не прийняв запис
  await w.tick();
  assert.deepEqual(seen, [], "поки запис у дорозі — опитування не затирає кеш");
  assert.equal(s.load().length, 2);
  release();
  await saving;
  w.server.failGet = true;
  await w.tick();                                                        // збій опитування не кидає
  assert.equal(s.load().length, 2);
});

test("close: зупиняє таймер і відпускає підписників", async () => {
  const w = world({ rows: [pin("a")] });
  const s = w.sandbox.DeaiComments.create(cfg());
  await s.ready;
  const seen = [];
  s.subscribe((rows) => seen.push(rows.length));
  s.close();
  assert.equal(w.timers.size, 0);
  w.server.rows = [pin("a"), pin("b")];
  await w.tick();
  await s.save([pin("z")]);
  assert.deepEqual(seen, [], "після close підписники мовчать");
  s.close();                                                             // повторний close — безпечний
});

test("підписник, що кидає виняток, не валить решту", async () => {
  const w = world();
  const s = w.sandbox.DeaiComments.create(cfg({ onChange: () => { throw new Error("cfg"); } }));
  await s.ready;
  const seen = [];
  s.subscribe(() => { throw new Error("first"); });
  s.subscribe((rows) => seen.push(rows.length));
  await s.save([pin("a")]);
  assert.deepEqual(seen, [1]);
});

test("supportsReplies === true, а replies їдуть із коментарем і вертаються з сервера (0.34)", async () => {
  const r = { id: "r1", author: "B", text: "відповідь", ts: "20.11.2026 10:00", editedTs: "20.11.2026 10:05", agent: true };
  const w = world();
  const s = w.sandbox.DeaiComments.create(cfg());
  await s.ready;
  assert.equal(s.supportsReplies, true);
  await s.save([{ ...pin("a"), replies: [r] }]);
  assert.deepEqual(JSON.parse(w.server.calls.at(-1).body).comments[0].replies, [r]);
  const w2 = world({ rows: [{ ...pin("a"), replies: [r] }] });
  const s2 = w2.sandbox.DeaiComments.create(cfg());
  await s2.ready;
  assert.deepEqual(plain(s2.load()[0].replies), [r]);
});
