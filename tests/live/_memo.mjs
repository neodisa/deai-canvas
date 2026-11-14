/**
 * Найменший сервіс командних коментарів `memo` — протокол фікстури `tests/fixtures/modules/memo-comments/` (спільний для
 * `comments.test.mjs` і `comments-team.test.mjs`). Файл НЕ `*.test.mjs` навмисно: `npm run test:live` бере лише їх.
 */
import http from "node:http";

/* ── найменший сервіс коментарів ───────────────────────────────────────────────────────────────────── */

/**
 * `memo` — протокол фікстури `memo-comments`. `allowOrigin` — що віддається в `Access-Control-Allow-Origin` (типово `*`,
 * як вимагає документ для авторів: пісочниця `/published` шле `Origin: null`); `log` — кожен запит із його `Origin`.
 */
export async function startMemo() {
  const store = new Map();
  const log = [];
  const memo = { store, log, allowOrigin: "*", url: "" };
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, "http://memo.local");
    log.push({ method: req.method, path: u.pathname, origin: req.headers.origin ?? null });
    res.setHeader("Access-Control-Allow-Origin", memo.allowOrigin);
    res.setHeader("Cache-Control", "no-store");
    if (req.method === "OPTIONS") {
      res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
      res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
      res.writeHead(204).end();
      return;
    }
    const m = /^\/c\/([^/]+)(\/remove|\/resolve)?$/.exec(u.pathname);
    if (!m) { res.writeHead(404).end("not found"); return; }
    const channel = decodeURIComponent(m[1]);
    const rows = store.get(channel) ?? [];
    let body = "";
    req.on("data", (d) => { body += d; });
    req.on("end", () => {
      let data = {};
      try { data = body ? JSON.parse(body) : {}; } catch { res.writeHead(400).end("bad json"); return; }
      if (req.method === "GET" && !m[2]) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(rows));
        return;
      }
      if (req.method !== "POST") { res.writeHead(405).end("method"); return; }
      if (!m[2]) {
        for (const c of data.comments ?? []) {
          const i = rows.findIndex((r) => r.id === c.id);
          if (i >= 0) rows[i] = c; else rows.push(c);
        }
      } else if (m[2] === "/remove") {
        store.set(channel, rows.filter((r) => !(data.ids ?? []).includes(r.id)));
      } else {
        const row = rows.find((r) => r.id === data.id);
        if (row) Object.assign(row, { status: "resolved", resolveReason: data.reason ?? "" });
      }
      if (!store.has(channel)) store.set(channel, rows);
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ ok: true }));
    });
  });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  memo.url = `http://127.0.0.1:${server.address().port}`;
  memo.close = () => new Promise((done) => { server.closeAllConnections?.(); server.close(done); });
  return memo;
}
