/**
 * Командні коментарі через МОДУЛЬ ролі `comments` (Deai 0.4.0, етап 2b-2, Task 6) — живе проведення: справжній сервер
 * в ізольованій «машині» (тимчасові `HOME` і `DEAI_HOME`), справжній Chromium, справжній шар коментатора.
 *
 * Юніти й серверні тести (`tests/test_comments_role.py`, `tests/test_publish_module.py`, `tests/test_comments_agent.py`,
 * `tests/memo-adapter.test.mjs`, `tests/overview-comments-module.test.mjs`) доводять кожну ланку окремо; тут те, що
 * живе лише в браузері й складається з ланок докупи: адаптер модуля справді завантажується в сторінку, шар коментатора
 * справді малює піни з чужого сервісу, «Огляд» і опубліковане превʼю (непрозорий origin пісочниці) їх теж бачать.
 *
 * Сервіс коментарів — найменший із можливих, `memo`: `http` на `127.0.0.1`, протокол фікстури
 * `tests/fixtures/modules/memo-comments/` (`GET /c/<канал>` → масив; `POST /c/<канал>` ← `{comments}`; `…/remove` ← `{ids}`;
 * `…/resolve` ← `{id, reason}`; тіла — `text/plain`). Це й є доказ УНІВЕРСАЛЬНОСТІ ролі: ядро не знає про сервіс нічого,
 * крім того, що каже модуль. Сервер канваса стартує з `DEAI_EXTRA_MODULES=tests/fixtures/modules` (тестовий шов:
 * модулі звідти діють як вбудовані), модуль вмикається звичайним `POST /api/module-enable`.
 *
 * Пін СІЄТЬСЯ прямо в `memo` (відбиток рахує справжній `CommentLayerAnchor.fingerprint` у bare-сторінці): так сценарії a–c
 * детерміновані й не залежать від тіньового DOM композера. Створення піна справжнім інтерфейсом — окремий сценарій d.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   a («Команда» в канвасі) — `module_client_target` (`serve.py`, роздача `GET /api/module-client/…`): якщо вона відмовляє
 *        всім, сторінка каналу показує банер замість шару коментатора, і червоніють a, b, d (c лишається зеленим: превʼю
 *        бере файли адаптера з диска, а не з цього маршруту). `hasTeamComments` (`spaces-model.js`): без `capabilities` у
 *        ньому простір БЕЗ інтеграцій не має вкладки «Команда» — червоніють a і b.
 *   b («Огляд»)             — гілка `cfg.module` у `start` (`overview-comments.js`): без неї «Огляд» іде зашитим CDN Supabase
 *        (розтяжка його не пускає) — червоніють b і f.
 *   c (превʼю в `/published`) — `publish_comments` → `build_preview(comments=<модуль>)` (`serve.py`): без модульного
 *        словника в `comment-layer/` нема адаптера, а сторінки без сніпета. Негативний контроль у тому ж сценарії: сервіс
 *        без `Access-Control-Allow-Origin` для `null` — пінів у пісочниці нема (доведено, що пін прийшов саме мережею).
 *   d (створення в UI)      — `save` і `subscribe` адаптера фікстури; друге вікно бачить пін без перезавантаження.
 *   e (форма ЛІГА)          — `'legacy'` у `_provider_for` (`deai_modules.py`): без нього ЛІГА-сторінка не має зашитого
 *        сніпета; `memo`, увімкнений в ІНШОМУ просторі, не бачить від ЛІГА жодного запиту.
 *   f (ізоляція)            — розтяжка `route` → `abort`, `guardRealDeai`, знімок справжнього `~/deai-published`.
 *
 * ⛔ Лише Playwright Chromium: панель Browser застосунку Claude блокує скрипти пісочниці (`ERR_BLOCKED_BY_CLIENT`), і
 * сценарій c червонів би з причини, що до коду не стосується.
 */
import assert from "node:assert/strict";
import http from "node:http";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { userInfo } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { ANCHOR, shootAll, t45Task } from "./_t45-fixture.mjs";
import { REAL_DEAI, VIEW, guardRealDeai, postJson, sleep, spacesApi, stop } from "./_spaces-kit.mjs";
import { startServer } from "./fixture.mjs";

/* Своя смуга: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs` стереже, що жодна база не
   збігається з чужою). Тести ЦЬОГО файла йдуть послідовно, тож одна база на всіх. */
const PORT_BASE = 13200;

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "modules");

const MODULE = "memo-comments";
const SPACE = "mod";
const TASK = "fixture";
const CHANNEL = `deai/${SPACE}/${TASK}`;
/* Приватний токен модуля НІКОЛИ не мусить опинитись у сторінках; публічний ключ — мусить (`"public": true`). */
const TOKEN = "TOKEN-PRIVATE-do-not-leak";
const PUBKEY = "PUBKEY-public-ok";
const CDN = "cdn.jsdelivr.net";
const PUBLISHED_CSP = "sandbox allow-scripts allow-forms allow-popups allow-modals";

/** Папка браузерів Playwright. Сервер канваса сидить в ізольованій домівці й без цього не знайшов би Chromium для
 *  знімків «Огляду» (читання справжнього кешу, не запис). */
function browsersPath() {
  if (process.env.PLAYWRIGHT_BROWSERS_PATH) return process.env.PLAYWRIGHT_BROWSERS_PATH;
  const home = userInfo().homedir;
  if (process.platform === "darwin") return path.join(home, "Library", "Caches", "ms-playwright");
  if (process.platform === "win32") return path.join(process.env.LOCALAPPDATA || path.join(home, "AppData", "Local"), "ms-playwright");
  return path.join(process.env.XDG_CACHE_HOME || path.join(home, ".cache"), "ms-playwright");
}

/* ── справжня домівка: `~/deai-published` не торкнуто ──────────────────────────────────────────────── */

const REAL_PUBLISHED = path.join(path.dirname(REAL_DEAI), "deai-published");
const realPublished = () => {
  try {
    return { exists: true, entries: readdirSync(REAL_PUBLISHED).sort(), mtime: statSync(REAL_PUBLISHED).mtimeMs };
  } catch {
    return { exists: false };
  }
};
/** Знімок ДО будь-якого сервера: файл імпортується до першого `startServer`. */
const REAL_PUBLISHED_BEFORE = realPublished();

/** Усі запити за межі машини з усіх сценаріїв і всі ПІДМІНЕНІ (CDN у сценарії e) — для підсумкового тесту. */
const OUTSIDE_ALL = [];
const STUBBED_ALL = [];
let REQUESTS_TOTAL = 0;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* ── найменший сервіс коментарів ───────────────────────────────────────────────────────────────────── */

/**
 * `memo` — протокол фікстури `memo-comments`. `allowOrigin` — що віддається в `Access-Control-Allow-Origin` (типово `*`,
 * як вимагає документ для авторів: пісочниця `/published` шле `Origin: null`); `log` — кожен запит із його `Origin`.
 */
async function startMemo() {
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

/* ── прилади ───────────────────────────────────────────────────────────────────────────────────────── */

const isLocal = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname);
};

/** Дочекатись істинного значення `fn()` (опитування), інакше — зрозуміле падіння. */
async function until(fn, what, ms = 15000) {
  const end = Date.now() + ms;
  let last;
  while (Date.now() < end) {
    last = await fn();
    if (last) return last;
    await sleep(100);
  }
  return assert.fail(`не дочекались: ${what} (останнє значення: ${JSON.stringify(last)})`);
}

/**
 * Сервер + `memo` + контекст браузера. Простір `mod` без інтеграцій із задачею `fixture` (`t45Task`: дві сторінки, на
 * `holovna` є кнопка `[data-testid=subscribe]`); `withLiga` додає ПЕРШИМ простір ЛІГА (поточний) — тоді `mod` лишається
 * другим і модуль вмикається лише в ньому. Контекст:
 *   · рахує КОЖЕН свій запит (`requests`) і відповіді (`responses`);
 *   · не пускає нічого за межі машини (`abort`); запис у `outside` видасть кожну спробу. Єдиний виняток — `stub`
 *     (хости, чий запит ПІДМІНЯЄТЬСЯ порожнім скриптом і на мережу не виходить: CDN зашитого шляху ЛІГА у сценарії e).
 */
async function boot(t, { withLiga = false, stub = [], enable = true } = {}) {
  const memo = await startMemo();
  t.after(() => memo.close());
  const mod = t45Task();
  const spaces = [];
  if (withLiga) {
    const liga = t45Task();
    spaces.push({ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { [TASK]: { dir: liga.dir, title: "Задача ЛІГА" } } });
  }
  spaces.push({ name: "Mod", id: SPACE, color: "space-3", tasks: { [TASK]: { dir: mod.dir, title: "Задача" } } });
  const server = await startServer(null, {
    portBase: PORT_BASE, spaces,
    env: { DEAI_EXTRA_MODULES: MODULES_DIR, PLAYWRIGHT_BROWSERS_PATH: browsersPath() },
  });
  t.after(() => stop(server.child));
  const { url } = server;

  if (enable) {
    const en = await (await postJson(url, "/api/module-enable", {
      space: SPACE, id: MODULE, settings: { endpoint: memo.url }, secrets: { token: TOKEN, pubkey: PUBKEY },
    })).json();
    assert.equal(en.ok, true, `module-enable: ${JSON.stringify(en)}`);
    assert.equal(en.check?.ok, true, `check модуля: ${JSON.stringify(en.check)}`);
  }

  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const requests = [];
  const responses = [];
  const outside = [];
  const stubbed = [];
  context.on("request", (r) => {
    REQUESTS_TOTAL += 1;
    requests.push(r.url());
    if (isLocal(r.url())) return;
    if (stub.includes(new URL(r.url()).hostname)) { stubbed.push(r.url()); STUBBED_ALL.push(r.url()); return; }
    outside.push(r.url());
    OUTSIDE_ALL.push(r.url());
  });
  context.on("response", (r) => responses.push({ url: r.url(), status: r.status() }));
  await context.route((u) => !isLocal(u.href), (route) => (stub.includes(new URL(route.request().url()).hostname)
    ? route.fulfill({ status: 200, contentType: "application/javascript", body: "" })
    : route.abort("blockedbyclient")));

  const logs = { errors: [], console: [], failed: [] };
  const watch = (page) => {
    page.on("pageerror", (e) => logs.errors.push(String(e.message ?? e)));
    page.on("console", (m) => { if (m.type() === "error") logs.console.push(m.text()); });
    page.on("requestfailed", (r) => logs.failed.push(`${r.url()} — ${r.failure()?.errorText ?? "?"}`));
  };
  context.on("page", watch);
  const page = await context.newPage();
  return { ...server, memo, context, page, requests, responses, outside, stubbed, logs, taskDir: mod.dir };
}

/**
 * Посіяти ОДИН пін у `memo` (канал `deai/mod/fixture`), як це зробив би шар коментатора: відбиток кнопки
 * «Підписатися» рахує справжній `CommentLayerAnchor.fingerprint` у bare-сторінці (без шару коментатора).
 */
async function seedPin({ memo, url, context }, id = "memo-seed-1") {
  const bare = await context.newPage();
  await bare.goto(`${url}/commented?it=it1&page=holovna&bare=1`);
  await bare.addScriptTag({ content: ANCHOR });
  const fp = await bare.evaluate(() => window.CommentLayerAnchor.fingerprint(
    document.querySelector("[data-testid=subscribe]"), document.body));
  await bare.close();
  const comment = {
    id, author: "Фікстура", text: "Пін із сервісу memo", status: "open", fp, htmlSnapshot: null, bornV: 1,
    ts: "19.10.2026 12:00",
    meta: { url: `${url}/commented?it=it1&page=holovna&ch=project`, route: "/commented", version: "1/holovna",
            iteration: "1", viewport: { w: 1280, h: 900 }, seq: 1 },
  };
  memo.store.set(CHANNEL, [comment]);
  return comment;
}

/** Рамка макета в оболонці: стан шару коментатора. Піни шукаємо в ТІНЬОВОМУ корені хоста `[data-comment-layer]`. */
const frameState = (page) => page.evaluate(() => {
  const w = document.getElementById("frame").contentWindow;
  const cl = w.CommentLayer;
  const host = w.document.querySelector("[data-comment-layer]");
  const pins = host && host.shadowRoot ? [...host.shadowRoot.querySelectorAll(".pin")] : [];
  return {
    href: w.location.href,
    factory: typeof w.DeaiComments,
    cfg: w.__deaiCommentsCfg ?? null,
    inited: !!(cl && cl._inited),
    ids: cl && cl.comments ? cl.comments.map((c) => c.id) : [],
    pins: pins.length,
    boxes: pins.map((p) => { const r = p.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }),
    banner: !!w.document.getElementById("cl-down"),
    vw: w.innerWidth,
    vh: w.innerHeight,
  };
});

/** Те саме для довільного кадру Playwright (опублікована сторінка, `/commented` напряму). */
const docState = (frame) => frame.evaluate(() => {
  const cl = window.CommentLayer;
  const host = document.querySelector("[data-comment-layer]");
  const pins = host && host.shadowRoot ? [...host.shadowRoot.querySelectorAll(".pin")] : [];
  return {
    origin: window.origin,
    factory: typeof window.DeaiComments,
    cfg: window.__deaiCommentsCfg ?? null,
    inited: !!(cl && cl._inited),
    ids: cl && cl.comments ? cl.comments.map((c) => c.id) : [],
    pins: pins.length,
    banner: !!document.getElementById("cl-down"),
  };
});

/** Дочекатись, поки в рамці стоїть НОВИЙ документ потрібного каналу з піднятою панеллю коментатора
 *  (той самий прийом, що в `comment-audience.test.mjs`: читаємо `location` рамки, а не атрибут `src`). */
function waitChannel(page, ch) {
  return page.waitForFunction((want) => {
    const w = (document.getElementById("frame") || {}).contentWindow;
    if (!(w && new RegExp(`[?&]ch=${want}(&|$)`).test(w.location.href) && w.document.readyState === "complete")) return false;
    const host = w.document.querySelector("[data-comment-layer]");
    return !!(host && host.shadowRoot && host.shadowRoot.querySelector(".panel"));
  }, ch, { timeout: 20000 });
}

const openPanel = (page) => page.evaluate(() => document.getElementById("frame").contentWindow.CommentLayer.open());
const aud = (page, id) => page.frameLocator("#frame").locator(`[data-aud="${id}"]`);

/** Піни «полотна» на «Огляді» з тіньового кореня: ключ, ідентифікатори, кластер, «поза кадром», підпис. */
const overviewPins = (page) => page.evaluate(() => {
  const root = document.querySelector("#canvas [data-comment-layer]").shadowRoot;
  return [...root.querySelectorAll(".cp")].map((w) => ({
    ids: w._item.ids, cluster: w._item.cluster, off: w._item.off, vis: w._item.vis, text: w.firstChild.textContent,
  }));
});

/** Усі текстові файли збірки: приватний токен модуля не мусить бути в жодному. */
function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p)); else out.push(p);
  }
  return out;
}

/* ── a: «Команда» у сторінці канваса ───────────────────────────────────────────────────────────────── */

test("a: простір без інтеграцій із модулем коментарів — вкладка «Команда», адаптер модуля вантажиться, посіяний пін видно", async (t) => {
  const env = await boot(t);
  const { page, url, memo, requests, responses, outside } = env;
  const seed = await seedPin(env);

  await page.goto(`${url}/app/`);
  await waitChannel(page, "local");
  /* Локальний канал адаптера модуля не вантажить: спільна поверхня одна, а фабрика зʼявляється лише з «Командою». */
  let st = await frameState(page);
  assert.equal(st.factory, "undefined", "у локальному каналі вже є window.DeaiComments");
  assert.equal(requests.some((u) => u.includes("/api/module-client/")), false, "адаптер завантажено до вибору «Команди»");

  /* Вкладка «Команда» є в просторі БЕЗ інтеграцій, бо є постачальник ролі (`capabilities.comments`), а не `integrations`. */
  const caps = (await spacesApi(url)).spaces.find((s) => s.id === SPACE).capabilities;
  assert.equal(caps.comments, MODULE, `capabilities простору: ${JSON.stringify(caps)}`);
  await openPanel(page);
  assert.equal(await aud(page, "project").count(), 1, "у просторі з модулем коментарів немає вкладки «Команда»");
  await aud(page, "project").click();
  await waitChannel(page, "project").catch(async (e) => assert.fail(
    `сторінка каналу project не підняла шар коментатора: ${JSON.stringify(await frameState(page))}; `
    + `відповіді адаптера: ${JSON.stringify(responses.filter((r) => r.url.includes("/api/module-client/")))}\n${e.message}`));

  st = await until(async () => { const s = await frameState(page); return s.pins >= 1 ? s : null; }, "пін у тіньовому корені шару коментатора");
  assert.equal(st.factory, "object", "сторінка каналу project не має window.DeaiComments");
  assert.equal(st.inited, true);
  assert.equal(st.banner, false, "шар коментатора показав банер «Коментарі недоступні»");
  assert.deepEqual(st.ids, [seed.id], "у шарі не той набір коментарів");
  assert.equal(st.pins, 1, "піни: рівно один (посіяний)");
  const box = st.boxes[0];
  assert.ok(box.w > 0 && box.h > 0 && box.x >= 0 && box.y >= 0 && box.x + box.w <= st.vw && box.y + box.h <= st.vh,
    `пін не на екрані рамки: ${JSON.stringify(box)} у ${st.vw}×${st.vh}`);

  /* Публічна конфігурація: адреса сервісу, публічний ключ і канал, який будує ЯДРО. Токен — ні. */
  assert.deepEqual(st.cfg, { endpoint: memo.url, pubkey: PUBKEY, channel: CHANNEL }, "client_config сторінки");
  const html = await (await fetch(`${url}/commented?it=it1&page=holovna&ch=project`)).text();
  assert.ok(html.includes(PUBKEY), "публічний ключ не дійшов до сторінки");
  assert.equal(html.includes(TOKEN), false, "приватний токен модуля потрапив у сторінку");
  const cfgText = await (await fetch(`${url}/api/comment-config?ch=project&it=it1`)).text();
  assert.equal(cfgText.includes(TOKEN), false, "приватний токен модуля потрапив у /api/comment-config");

  /* Адаптер роздано ЯДРОМ: 200, javascript, nosniff — і браузер справді його запитав. */
  const adapterUrl = `${url}/api/module-client/${MODULE}/adapter.js`;
  assert.ok(requests.includes(adapterUrl), "браузер не запитав адаптер модуля");
  assert.equal(responses.find((r) => r.url === adapterUrl)?.status, 200, "адаптер модуля не віддався (200)");
  const direct = await fetch(adapterUrl);
  assert.equal(direct.status, 200);
  assert.match(direct.headers.get("content-type") ?? "", /^text\/javascript/);
  assert.equal(direct.headers.get("x-content-type-options"), "nosniff");

  /* Сховище справді ходить у сервіс модуля: GET каналу задачі з origin канваса. */
  const canvasOrigin = new URL(url).origin;
  assert.ok(memo.log.some((l) => l.method === "GET" && l.path === `/c/${encodeURIComponent(CHANNEL)}` && l.origin === canvasOrigin),
    `memo не бачив GET каналу з origin канваса: ${JSON.stringify(memo.log)}`);

  assert.equal(requests.some((u) => new URL(u).hostname === CDN), false, "канал модуля потягнув зашитий CDN Supabase");
  assert.deepEqual(outside, [], `запити за межі машини:\n${outside.join("\n")}`);
  assert.deepEqual(env.logs.errors, [], `помилки сторінок:\n${env.logs.errors.join("\n")}`);
});

/* ── b: «Огляд» ────────────────────────────────────────────────────────────────────────────────────── */

test("b: «Огляд» показує той самий пін — адаптер модуля вантажиться в оболонку, а не зашитий CDN", async (t) => {
  const env = await boot(t);
  const { page, url, memo, requests, outside } = env;
  const seed = await seedPin(env);
  const shot = await shootAll(url);
  assert.ok(shot.ok, `знімки «Огляду»: ${JSON.stringify(shot).slice(0, 300)}`);

  /* Канал «Команда» запамʼятовує оболонка; кладемо вибір до першого скрипта СТОРІНКИ — лише в оболонці
     (рамка того самого походження, `addInitScript` виконується і в ній). */
  await page.addInitScript(() => {
    if (window !== window.top) return;
    try { localStorage.setItem("dc-comment-mode", "project"); } catch { /* приватний режим */ }
  });
  await page.goto(`${url}/app/`);
  await waitChannel(page, "project");
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  const pins = await until(async () => {
    const has = await page.evaluate(() => {
      const h = document.querySelector("#canvas [data-comment-layer]");
      return Boolean(h && h.shadowRoot && h.shadowRoot.querySelectorAll(".cp").length);
    });
    return has ? overviewPins(page) : null;
  }, "піни на полотні «Огляду»", 20000);

  assert.equal(pins.length, 1, `піни на «Огляді»: ${JSON.stringify(pins)}`);
  assert.deepEqual(pins[0].ids, [seed.id]);
  assert.equal(pins[0].off, false, "пін «Огляду» без місця на кадрі");
  assert.equal(pins[0].text, "1");

  /* «Огляд» узяв адаптер модуля: скрипт у документі оболонки (не лише в рамці) і відповідь `module` від центру конфігурації. */
  const shellScripts = await page.evaluate(() => [...document.scripts].map((s) => s.src).filter((s) => s.includes("/api/module-client/")));
  assert.deepEqual(shellScripts, [`${url}/api/module-client/${MODULE}/adapter.js`], "оболонка не вантажила адаптер модуля");
  const cfg = await (await fetch(`${url}/api/comment-config?ch=project&it=it1`)).json();
  assert.equal(cfg.module, MODULE);
  assert.equal(cfg.channel, CHANNEL);
  assert.deepEqual(cfg.config, { endpoint: memo.url, pubkey: PUBKEY });

  assert.equal(requests.some((u) => new URL(u).hostname === CDN), false, "«Огляд» потягнув зашитий CDN Supabase");
  assert.deepEqual(outside, [], `запити за межі машини:\n${outside.join("\n")}`);
});

/* ── c: опубліковане превʼю ────────────────────────────────────────────────────────────────────────── */

test("c: static-publish → /published/<простір>/<задача>/ — превʼю несе адаптер і показує пін у пісочниці (Origin: null)", async (t) => {
  const env = await boot(t);
  const { page, url, home, memo, requests, outside, logs } = env;
  const seed = await seedPin(env);

  const res = await postJson(url, "/api/publish", {});
  const body = await res.json();
  assert.equal(res.status, 200, `POST /api/publish: ${JSON.stringify(body)}`);
  assert.equal(body.ok, true);
  assert.equal(body.local.url, `/published/${SPACE}/${TASK}/`);
  assert.ok(!("comments_unavailable" in body), `публікація скаржиться на коментарі: ${body.comments_unavailable}`);

  /* Що лягло на диск: шар і ЛИШЕ файли адаптера, збірка модуля (`build: module`), приватного токена ніде. */
  const out = path.join(home, "deai-published", SPACE, TASK);
  assert.deepEqual(readdirSync(path.join(out, "comment-layer")).sort(), ["adapter.js", "comment-layer.min.js"],
    "у comment-layer/ не те, що оголошено в `client` + шар ядра");
  assert.equal(JSON.parse(readFileSync(path.join(out, "manifest.json"), "utf8")).build, "module", "збірка не позначена як модульна");
  const inner = readFileSync(path.join(out, "it1", "holovna", "index.html"), "utf8");
  assert.match(inner, /\.\.\/\.\.\/comment-layer\/adapter\.js/, "сторінка превʼю не вантажить адаптер за відносним шляхом");
  assert.ok(inner.includes(PUBKEY) && inner.includes(memo.url), "публічна конфігурація не вшита в сторінку превʼю");
  const leaked = walk(out).filter((f) => readFileSync(f).includes(TOKEN));
  assert.deepEqual(leaked, [], `приватний токен модуля лежить у збірці: ${leaked.join(", ")}`);
  assert.equal(inner.includes(CDN), false, "превʼю модуля тягне зашитий CDN Supabase");

  /* Відкриваємо локальну копію: пісочниця з непрозорим origin, `allow-modals` у CSP. */
  const open = async (pg) => {
    await pg.goto(`${url}${body.local.url}`);
    const frame = await until(() => pg.frames().find((f) => /\/it1\/holovna\/index\.html$/.test(f.url())) ?? null,
      "внутрішня сторінка превʼю в рамці");
    await frame.waitForLoadState("load");
    await until(async () => (await docState(frame)).inited, "шар коментатора в опублікованій сторінці");
    return frame;
  };
  let frame = await open(page);
  let st = await docState(frame);
  assert.equal(st.origin, "null", "превʼю відкрилось не в пісочниці з непрозорим origin");
  assert.equal(st.factory, "object", "опублікована сторінка не має window.DeaiComments");
  assert.deepEqual(st.cfg, { endpoint: memo.url, pubkey: PUBKEY, channel: CHANNEL }, "client_config опублікованої сторінки");
  st = await until(async () => { const s = await docState(frame); return s.pins >= 1 ? s : null; }, "пін в опублікованій сторінці");
  assert.deepEqual(st.ids, [seed.id]);
  assert.equal(st.pins, 1);
  assert.equal(st.banner, false, "опублікована сторінка показала банер «Коментарі недоступні»");

  const base = `${url}/published/${SPACE}/${TASK}`;
  for (const f of ["comment-layer/adapter.js", "comment-layer/comment-layer.min.js"]) {
    assert.ok(requests.includes(`${base}/${f}`), `превʼю не запитало ${f}`);
    const r = await fetch(`${base}/${f}`);
    assert.equal(r.status, 200, f);
    assert.equal(r.headers.get("access-control-allow-origin"), "*", `ACAO на ${f}`);
    assert.equal(r.headers.get("content-security-policy"), PUBLISHED_CSP, `CSP на ${f}`);
  }
  /* Сервіс бачив запит із `Origin: null` — тобто пін прийшов саме тим шляхом, який документ радить дозволити. */
  assert.ok(memo.log.some((l) => l.method === "GET" && l.origin === "null"), `memo не бачив запиту з Origin: null: ${JSON.stringify(memo.log)}`);

  /* Негативний контроль: сервіс, що НЕ дозволяє `null`, — пінів у пісочниці немає (на справжньому хостингу запити йдуть з
     origin сторінки, але локальний вигляд мусить це вимагати, і документ про це каже). */
  memo.allowOrigin = "http://127.0.0.1:1";
  const failedBefore = logs.failed.length;
  const page2 = await env.context.newPage();
  frame = await open(page2);
  st = await docState(frame);
  assert.equal(st.pins, 0, "пін показано всупереч CORS — перевірка нічого не доводила");
  assert.equal(st.ids.length, 0);
  assert.ok(logs.failed.length > failedBefore && logs.failed.slice(failedBefore).some((m) => m.startsWith(memo.url)),
    `браузер не відмовив у CORS на запит до сервісу: ${JSON.stringify(logs.failed.slice(failedBefore))}`);
  memo.allowOrigin = "*";

  assert.deepEqual(outside, [], `запити за межі машини:\n${outside.join("\n")}`);
});

/* ── d: створення піна в інтерфейсі ────────────────────────────────────────────────────────────────── */

test("d: пін, створений у сторінці каналу project, потрапляє в сервіс модуля й зʼявляється в другому вікні без перезавантаження", async (t) => {
  /* Шар коментатора при створенні піна підтягує `html2canvas` з jsDelivr (знімок «до» в `meta.shot`; уже було до модулів).
     Підміняємо порожнім скриптом: на мережу не виходить, знімка нема — і це не заважає коментарю (шар «м'яко» падає). */
  const env = await boot(t, { stub: [CDN] });
  const { page, url, memo, outside, stubbed } = env;
  const seed = await seedPin(env);

  /* Сторінка каналу напряму (її малює оболонка в рамці): ввімкнути коментування `c`, клік по заголовку, текст, «Зберегти». */
  const target = `${url}/commented?it=it1&page=holovna&ch=project`;
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(target);
  await until(async () => (await docState(page)).pins >= 1, "посіяний пін на сторінці");

  /* Друге вікно — ще один рецензент: бачить лише посіяний. */
  const second = await env.context.newPage();
  await second.setViewportSize({ width: 1280, height: 900 });
  await second.goto(target);
  await until(async () => (await docState(second)).pins === 1, "посіяний пін у другому вікні");

  await page.mouse.move(600, 300);
  await page.keyboard.press("c");
  const box = await page.locator("h1").boundingBox();
  await page.mouse.move(box.x + 20, box.y + 10);
  await sleep(100);
  await page.mouse.down();
  await page.mouse.up();
  const compose = () => page.evaluate(() => {
    const r = document.querySelector("[data-comment-layer]").shadowRoot;
    return !!r.querySelector(".compose textarea");
  });
  await until(compose, "композер коментаря");
  await page.keyboard.type("Створено в інтерфейсі модульного каналу");
  const save = await page.evaluate(() => {
    const r = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .save").getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  await page.mouse.move(save.x, save.y);
  await page.mouse.down();
  await page.mouse.up();

  /* У сервісі: канал задачі, текст, відкритий, відбиток заголовка; посіяний на місці. */
  const row = await until(() => (memo.store.get(CHANNEL) ?? []).find((c) => c.text === "Створено в інтерфейсі модульного каналу") ?? null,
    "створений пін у сервісі memo");
  assert.equal(row.status, "open");
  assert.equal(row.fp?.tag, "h1", "відбиток не заголовка");
  assert.match(row.id, /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/, "id не з білого списку агента (UUID чи c-…): `resolve` його не прийме");
  assert.deepEqual((memo.store.get(CHANNEL) ?? []).map((c) => c.id).sort(), [seed.id, row.id].sort());
  assert.equal(memo.log.some((l) => l.method === "POST" && l.path === `/c/${encodeURIComponent(CHANNEL)}`), true);

  /* Друге вікно отримує пін через `subscribe` (опитування адаптера раз на секунду), без перезавантаження. */
  const got = await until(async () => { const s = await docState(second); return s.pins === 2 ? s : null; }, "створений пін у другому вікні (subscribe)");
  assert.deepEqual(got.ids.sort(), [seed.id, row.id].sort());
  assert.deepEqual(stubbed, [`https://${CDN}/npm/html2canvas@1.4.1/dist/html2canvas.min.js`],
    "єдиний звернений поза localhost ресурс — html2canvas шару коментатора (і той підмінено)");
  assert.deepEqual(outside, [], `запити за межі машини:\n${outside.join("\n")}`);
});

/* ── e: форма ЛІГА без змін ────────────────────────────────────────────────────────────────────────── */

test("e: ЛІГА-простір — зашитий шлях (спільний CDN), жодного модульного сніпета; memo в іншому просторі не бачить запитів", async (t) => {
  const env = await boot(t, { withLiga: true, stub: [CDN] });
  const { page, url, memo, requests, outside, stubbed } = env;

  const spaces = (await spacesApi(url)).spaces;
  const liga = spaces.find((s) => s.id === "liga");
  assert.equal(liga.integrations, true, "свідок: простір ЛІГА має інтеграції");
  assert.equal(liga.capabilities.comments, "legacy", `capabilities ЛІГА: ${JSON.stringify(liga.capabilities)}`);
  assert.equal(spaces.find((s) => s.id === SPACE).capabilities.comments, MODULE, "свідок: у `mod` модуль ввімкнено");
  assert.equal(memo.log.length, 0, "свідок: memo ще нічого не бачив");

  /* Сторінка каналу project у ЛІГА: зашитий шлях. */
  const target = `${url}/commented?it=it1&page=holovna&ch=project`;
  const html = await (await fetch(target)).text();
  assert.ok(html.includes(CDN) && html.includes("supabase-adapter.min.js"), "ЛІГА-сторінка втратила зашитий сніпет Supabase");
  assert.equal(html.includes("__deaiCommentsCfg") || html.includes("/api/module-client/"), false, "ЛІГА-сторінка отримала модульний сніпет");
  const cfg = await (await fetch(`${url}/api/comment-config?ch=project&it=it1`)).json();
  assert.equal("module" in cfg, false, "/api/comment-config ЛІГА відповів формою модуля");

  await page.goto(target);
  await until(() => requests.some((u) => new URL(u).hostname === CDN), "запит до зашитого CDN (ЛІГА)");
  await sleep(1500);                                  // шар встигає піднятись (з порожнім CDN — з банером), `memo` встигає озватись, якби мав
  const st = await docState(page);
  assert.equal(st.factory, "undefined", "ЛІГА-сторінка має window.DeaiComments");
  assert.equal(st.cfg, null, "ЛІГА-сторінка має window.__deaiCommentsCfg");
  assert.equal(requests.some((u) => u.includes("/api/module-client/")), false, "ЛІГА-сторінка запитала адаптер модуля");
  assert.equal(requests.some((u) => u.startsWith(memo.url)), false, "ЛІГА-сторінка звернулась до сервісу memo");
  assert.equal(memo.log.length, 0, `memo бачив запити від ЛІГА: ${JSON.stringify(memo.log)}`);

  /* Усе, що пішло за межі localhost, — лише підміна CDN (порожній скрипт; на мережу не виходило). */
  assert.ok(stubbed.length >= 1, "свідок: зашитий шлях ЛІГА не звертався до CDN — сценарій не про те");
  assert.deepEqual([...new Set(stubbed.map((u) => new URL(u).hostname))], [CDN]);
  assert.deepEqual(outside, [], `запити за межі машини, крім підміненого CDN:\n${outside.join("\n")}`);
});

/* ── f: ізоляція ───────────────────────────────────────────────────────────────────────────────────── */

test("f: жоден сценарій не вивів запит за межі машини, а справжній ~/deai-published не торкнуто", () => {
  assert.ok(REQUESTS_TOTAL > 100, `свідок: замало запитів (${REQUESTS_TOTAL}) — розтяжка могла нічого не бачити`);
  assert.deepEqual(OUTSIDE_ALL, [], `запити за межі машини з усіх сценаріїв:\n${OUTSIDE_ALL.join("\n")}`);
  assert.deepEqual([...new Set(STUBBED_ALL.map((u) => new URL(u).hostname))], [CDN],
    "підмінялись запити не лише до CDN ЛІГА (або не підмінялись зовсім)");
  assert.deepEqual(realPublished(), REAL_PUBLISHED_BEFORE, `живий тест торкнувся справжнього ${REAL_PUBLISHED}`);
});

guardRealDeai("g: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
