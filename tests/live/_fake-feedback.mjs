/**
 * Підробний приймач відгуків для живих тестів (0.23.0): `http.createServer` на `127.0.0.1:0`, справжнього Supabase нема.
 *
 * Повторює рівно те, що чіпає `SupabaseSender` (`app/feedback.py`):
 *  · `POST /rest/v1/feedback` — перевіряє `apikey`, `Authorization: Bearer <ключ>`, `Prefer: return=minimal`, тіло — JSON-обʼєкт;
 *    зберігає рядок; повторний `id` → 409;
 *  · `POST /storage/v1/object/feedback-shots/<імʼя>` — перевіряє заголовки й `x-upsert: false`, зберігає байти; повтор → 409.
 * Режими: `up` (приймає) і `down` (503 на все, щоб відгук ліг у локальну чергу). Ключ — вигаданий тестовий.
 */
import http from "node:http";

export const FAKE_KEY = "sb_publishable_test";

export async function startFakeFeedback({ key = FAKE_KEY } = {}) {
  let mode = "up";
  const rows = [];
  const shots = new Map();
  const rejected = [];       // запити, що не пройшли перевірку заголовків: тест вимагає, щоб їх не було
  const hits = [];           // `метод шлях` усіх запитів, що дійшли

  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const body = Buffer.concat(chunks);
      const url = new URL(req.url, "http://127.0.0.1");
      hits.push(`${req.method} ${url.pathname}`);
      const send = (status, text = "") => {
        res.writeHead(status, { "Content-Type": "application/json" });
        res.end(text);
      };
      if (mode === "down") return send(503, '{"message":"down"}');
      const h = req.headers;
      const authOk = h.apikey === key && h.authorization === `Bearer ${key}`;
      if (req.method !== "POST") { rejected.push(`${req.method} ${url.pathname}: not POST`); return send(405); }
      if (url.pathname === "/rest/v1/feedback") {
        let row = null;
        try { row = JSON.parse(body.toString("utf8")); } catch { /* нижче */ }
        const ok = authOk && h.prefer === "return=minimal" && row && typeof row === "object" && !Array.isArray(row) && typeof row.id === "string";
        if (!ok) { rejected.push(`row: auth=${authOk} prefer=${h.prefer}`); return send(400, '{"message":"bad"}'); }
        if (rows.some((r) => r.id === row.id)) return send(409, '{"code":"23505"}');
        rows.push(row);
        return send(201);
      }
      const m = /^\/storage\/v1\/object\/feedback-shots\/([0-9a-f-]{36}\.(?:webp|png))$/.exec(url.pathname);
      if (m) {
        const ok = authOk && h["x-upsert"] === "false" && /^image\/(webp|png)$/.test(h["content-type"] || "");
        if (!ok) { rejected.push(`shot: auth=${authOk} upsert=${h["x-upsert"]} ct=${h["content-type"]}`); return send(400, '{"message":"bad"}'); }
        if (shots.has(m[1])) return send(409, '{"error":"Duplicate"}');
        shots.set(m[1], body);
        return send(200, "{}");
      }
      rejected.push(`unknown ${url.pathname}`);
      return send(404);
    });
  });

  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  const port = server.address().port;
  return {
    url: `http://127.0.0.1:${port}`,
    key,
    port,
    setMode: (m) => { mode = m; },
    rows: () => rows.map((r) => ({ ...r })),
    shots: () => new Map(shots),
    rejected: () => [...rejected],
    hits: () => [...hits],
    close: () => new Promise((done) => { server.closeAllConnections?.(); server.close(() => done()); }),
  };
}
