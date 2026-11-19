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
 *   b («Огляд»)             — гілка `cfg.module` у `start` (`overview-comments.js`): без неї «Огляд» не бере адаптера модуля
 *        (розтяжка не пускає нічого за межі машини) — червоніють b і f.
 *   c (превʼю в `/published`) — `publish_comments` → `build_preview(comments=<модуль>)` (`serve.py`): без модульного
 *        словника в `comment-layer/` нема адаптера, а сторінки без сніпета. Негативний контроль у тому ж сценарії: сервіс
 *        без `Access-Control-Allow-Origin` для `null` — пінів у пісочниці нема (доведено, що пін прийшов саме мережею).
 *   d (створення в UI)      — `save` і `subscribe` адаптера фікстури; друге вікно бачить пін без перезавантаження.
 *   e (ЛІГА = той самий модуль) — (4b-2) `'legacy'` у `_provider_for` (`deai_modules.py`) і `MODULE_COMMENT_SNIPPET` у `_commented`
 *        (`serve.py`): ЛІГА-сторінка несе МОДУЛЬНИЙ сніпет (`__deaiCommentsCfg` із каналом задачі й кошиком скріншотів,
 *        файли `supabase-comments`), без CDN Supabase і без `supabase-adapter`; Supabase — вигаданий хост із
 *        `tasks.json`, перехоплений у браузері; `memo`, увімкнений в ІНШОМУ просторі, не бачить від ЛІГА жодного запиту.
 *   e3 (ЛІГА без конфігу)   — `COMMENTS_UNCONFIGURED` / `inject_comment_notice` (`serve.py`): без `supabase_url` у `tasks.json`
 *        сторінка каналу — ЛОКАЛЬНА з банером `comments-unconfigured`, а `/api/comment-config` → 409; рамка робоча (піни
 *        ставляться локально) і до мережі не йде.
 *   e2 (зміна модуля)       — (фінальне ревʼю 0.5.0) `ovc.invalidate()` на початку `afterModulesChange` (`app.js`) і сам
 *        `invalidate()` у `overview-comments.js`: без нього коментатор «Огляду» тримає інстанс за ключем «ітерація|канал» і
 *        після зміни адреси на екрані «Підключення» його пін-шар лишається на СТАРОМУ сервісі (червоніє e2: піни A замість B,
 *        опитування A триває).
 *   f (ізоляція)            — розтяжка `route` → `abort`, `guardRealDeai`, знімок справжнього `~/deai-published`.
 *
 * ⛔ Лише Playwright Chromium: панель Browser застосунку Claude блокує скрипти пісочниці (`ERR_BLOCKED_BY_CLIENT`), і
 * сценарій c червонів би з причини, що до коду не стосується.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { userInfo } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { LIGA_SB_HOST, hermeticLiga } from "./_liga-supabase.mjs";
import { startMemo } from "./_memo.mjs";
import { ANCHOR, shootAll, t45Task } from "./_t45-fixture.mjs";
import { REAL_DEAI, VIEW, guardRealDeai, openCard, postJson, sleep, spacesApi, stop, goTasks } from "./_spaces-kit.mjs";
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
const MODULE_PATH = "/api/module-client/supabase-comments/";
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
 * другим і модуль вмикається лише в ньому. `ligaSupabase` (типово разом із `withLiga`) пише в корінь `tasks.json` ЛІГИ
 * вигаданий конфіг Supabase й перехоплює його хост у браузері (`hermeticLiga`: REST порожній, websocket закрито); `false` —
 * ЛІГА без конфігу (сценарій e3). Контекст:
 *   · рахує КОЖЕН свій запит (`requests`) і відповіді (`responses`);
 *   · не пускає нічого за межі машини (`abort`); запис у `outside` видасть кожну спробу. Єдиний виняток — `stub`
 *     (хости, чий запит ПІДМІНЯЄТЬСЯ порожнім скриптом і на мережу не виходить: CDN зашитого шляху ЛІГА у сценарії e).
 */
async function boot(t, { withLiga = false, stub = [], enable = true, ligaSupabase = withLiga } = {}) {
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
    portBase: PORT_BASE, spaces, supabase: ligaSupabase,
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
  /* ЛІГА з конфігом: вигаданий хост Supabase відповідає порожньо (хост — у `stub`, тож його запити йдуть у `stubbed`). */
  const liga = ligaSupabase ? await hermeticLiga(context) : null;

  const logs = { errors: [], console: [], failed: [] };
  const watch = (page) => {
    page.on("pageerror", (e) => logs.errors.push(String(e.message ?? e)));
    page.on("console", (m) => { if (m.type() === "error") logs.console.push(m.text()); });
    page.on("requestfailed", (r) => logs.failed.push(`${r.url()} — ${r.failure()?.errorText ?? "?"}`));
  };
  context.on("page", watch);
  const page = await context.newPage();
  return { ...server, memo, context, page, requests, responses, outside, stubbed, liga, logs, taskDir: mod.dir };
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

/** Дочекатись, поки в рамці стоїть завершений документ із піднятою панеллю коментатора. З 0.27.0 канал не вибирається:
 *  рамка робочого місця (`host=1`) завжди несе комбіноване сховище (Claude + команда), а `ch=` у її адресі більше нема. */
function waitFrame(page) {
  return page.waitForFunction(() => {
    const w = (document.getElementById("frame") || {}).contentWindow;
    if (!(w && w.document.readyState === "complete")) return false;
    const host = w.document.querySelector("[data-comment-layer]");
    return !!(host && host.shadowRoot && host.shadowRoot.querySelector(".panel"));
  }, null, { timeout: 20000 });
}

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

test("a: простір без інтеграцій із модулем коментарів — рамка несе командне сховище (адаптер модуля вантажиться), посіяний пін видно", async (t) => {
  const env = await boot(t);
  const { page, url, memo, requests, responses, outside } = env;
  const seed = await seedPin(env);

  await page.goto(`${url}/app/`);
  await waitFrame(page).catch(async (e) => assert.fail(
    `рамка не підняла шар коментатора: ${JSON.stringify(await frameState(page))}; `
    + `відповіді адаптера: ${JSON.stringify(responses.filter((r) => r.url.includes("/api/module-client/")))}\n${e.message}`));
  /* 0.27.0: вибору каналу нема — командний постачальник є, тож рамка (`host=1`) одразу комбінована: адаптер модуля
     вантажиться разом зі сторінкою, а в адресі рамки немає `ch=`. */
  let st = await frameState(page);
  assert.match(st.href, /host=1/);
  assert.doesNotMatch(st.href, /[?&]ch=/, "рамка робочого місця ще несе ch=");

  /* Постачальник ролі (`capabilities.comments`), а не `integrations`, робить панель подвійною: сегмент «Кому» з'являється. */
  const caps = (await spacesApi(url)).spaces.find((s) => s.id === SPACE).capabilities;
  assert.equal(caps.comments, MODULE, `capabilities простору: ${JSON.stringify(caps)}`);
  await page.click('#hud [data-act="comments"]');
  await page.waitForSelector('#cmt-panel [data-act="cmtfilter"][data-val="project"]', { timeout: 10000 });
  assert.equal(await page.locator('#cmt-panel [data-act="cmtfilter"]').count(), 3, "у просторі з модулем коментарів нема сегмента «Кому» (Усі/Claude/Команда)");

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

  await page.goto(`${url}/app/`);
  await waitFrame(page);
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

/* ── e: ЛІГА — той самий модуль ────────────────────────────────────────────────────────────────────── */

test("e: ЛІГА-простір — модульний сніпет supabase-comments (конфіг із tasks.json), без CDN і зашитого адаптера; memo в іншому просторі не бачить запитів", async (t) => {
  const env = await boot(t, { withLiga: true, stub: [CDN, LIGA_SB_HOST] });
  const { page, url, memo, requests, outside, liga } = env;

  const spaces = (await spacesApi(url)).spaces;
  const ligaSpace = spaces.find((s) => s.id === "liga");
  assert.equal(ligaSpace.compat?.vcs, "design-canvas", "свідок: простір ЛІГА має явний запис vcs зі схемою ЛІГИ");
  assert.equal(ligaSpace.capabilities.comments, "supabase-comments", `capabilities ЛІГА (4d-4b: явний запис): ${JSON.stringify(ligaSpace.capabilities)}`);
  assert.equal(spaces.find((s) => s.id === SPACE).capabilities.comments, MODULE, "свідок: у `mod` модуль ввімкнено");
  assert.equal(memo.log.length, 0, "свідок: memo ще нічого не бачив");

  /* Сторінка каналу project у ЛІГА: модульний сніпет вбудованого `supabase-comments`; канал — задачі (`dc/<задача>`). */
  const target = `${url}/commented?it=it1&page=holovna&ch=project`;
  const html = await (await fetch(target)).text();
  assert.ok(html.includes("__deaiCommentsCfg") && html.includes(`${MODULE_PATH}adapter.js`) && html.includes(`${MODULE_PATH}supabase.min.js`),
    "ЛІГА-сторінка без модульного сніпета supabase-comments");
  for (const old of [CDN, "supabase-adapter", "CommentLayerSupabase", "cdn.jsdelivr"]) {
    assert.equal(html.includes(old), false, `ЛІГА-сторінка ще несе зашите «${old}»`);
  }
  const cfg = await (await fetch(`${url}/api/comment-config?ch=project&it=it1`)).json();
  assert.equal(cfg.channel, `dc/${TASK}`, `канал ЛІГА-задачі: ${JSON.stringify(cfg)}`);
  assert.equal(cfg.config.url, "https://abcdefghijkl.supabase.co");
  assert.equal(cfg.config.shotsBucket, "overview-thumbs", "кошик скріншотів ЛІГИ (картка Teams бере shotUrl звідти)");

  await page.goto(target);
  await until(async () => (await docState(page)).pins !== undefined && (await docState(page)).inited, "піднятий коментатор ЛІГИ");
  await until(() => liga.supabase.some((r) => r.startsWith("GET /rest/v1/")), "читання каналу з Supabase ЛІГИ (перехопленого)");
  const st = await docState(page);
  assert.equal(st.factory, "object", "ЛІГА-сторінка без window.DeaiComments (адаптер модуля не завантажився)");
  assert.equal(st.cfg.channel, `dc/${TASK}`, "канал у __deaiCommentsCfg");
  assert.equal(st.banner, false, "банер «Коментарі недоступні» на робочій ЛІГА-сторінці");
  assert.ok(requests.some((u) => u.endsWith(`${MODULE_PATH}adapter.js`)), "ЛІГА-сторінка не запитала адаптер модуля");
  assert.ok(requests.some((u) => u.endsWith(`${MODULE_PATH}supabase.min.js`)), "ЛІГА-сторінка не запитала supabase.min.js модуля");
  assert.equal(requests.some((u) => new URL(u).hostname === CDN), false, "ЛІГА-сторінка потягнула CDN");
  assert.equal(requests.some((u) => u.includes("supabase-adapter")), false, "ЛІГА-сторінка запитала зашитий supabase-adapter");
  assert.equal(requests.some((u) => u.startsWith(memo.url)), false, "ЛІГА-сторінка звернулась до сервісу memo");
  assert.equal(memo.log.length, 0, `memo бачив запити від ЛІГА: ${JSON.stringify(memo.log)}`);

  /* Усе поза localhost — лише вигаданий хост Supabase (перехоплений браузером, на мережу не виходило). */
  assert.deepEqual(liga.outside, [], `запити за межі машини, крім перехопленого Supabase:\n${liga.outside.join("\n")}`);
  assert.deepEqual(outside, [], `запити за межі машини:\n${outside.join("\n")}`);
});

/* ── e3: ЛІГА без конфігу Supabase ─────────────────────────────────────────────────────────────────── */

test("e3: ЛІГА без запису supabase-comments — сторінка каналу локальна, без модульного сніпета, рамка працює (локальний пін ставиться)", async (t) => {
  /* 4d-4b: «конфігу нема» = «запису нема» (оригіналів кореня рантайм не читає): ні банера `comments-unconfigured`, ні спільних адрес. */
  const env = await boot(t, { withLiga: true, ligaSupabase: false, enable: false, stub: [CDN] });
  const { page, url, memo, requests, outside } = env;

  const target = `${url}/commented?it=it1&page=holovna&ch=project`;
  const html = await (await fetch(target)).text();
  assert.ok(html.includes("local-adapter.js"), "без запису сторінка мусить бути локальною");
  assert.equal(html.includes("__deaiCommentsCfg") || html.includes("/api/module-client/"), false, "без запису сторінка отримала модульний сніпет");
  const res = await fetch(`${url}/api/comment-config?ch=project&it=it1`);
  assert.equal(res.status, 409, "/api/comment-config ЛІГИ без запису мусить відмовити (409)");
  assert.equal((await res.json()).code, "integrations-off");

  await page.goto(target);

  /* Рамка робоча: локальний шар піднято, пін ставиться (локально) — як у каналі «Клод». */
  await until(async () => (await docState(page)).inited, "піднятий локальний шар коментатора");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.mouse.move(600, 300);
  await page.keyboard.press("c");
  const box = await page.locator("h1").boundingBox();
  await page.mouse.move(box.x + 20, box.y + 10);
  await sleep(100);
  await page.mouse.down();
  await page.mouse.up();
  await until(() => page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea")),
    "композер локального піна");
  await page.keyboard.type("Локальний пін без Supabase");
  const save = await page.evaluate(() => {
    const r = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .save").getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  await page.mouse.move(save.x, save.y);
  await page.mouse.down();
  await page.mouse.up();
  const st = await until(async () => { const s = await docState(page); return s.pins === 1 ? s : null; }, "локальний пін на сторінці");
  assert.equal(st.ids.length, 1);

  assert.equal(requests.some((u) => u.includes("/api/module-client/")), false, "локальна сторінка запитала адаптер модуля");
  assert.equal(requests.some((u) => u.startsWith(memo.url)), false);
  assert.deepEqual(outside, [], `запити за межі машини:\n${outside.join("\n")}`);
});

/* ── e2: зміна адреси сервісу на екрані «Підключення» ──────────────────────────────────────────────── */

test("e2: адресу сервісу коментарів змінили на «Підключенні» — «Огляд» бере НОВИЙ сервіс: піни B, жодного запиту оболонки до A", async (t) => {
  const env = await boot(t);
  const { page, url, memo: A, outside } = env;
  const B = await startMemo();
  t.after(() => B.close());
  /* Два сервіси з РІЗНИМИ пінами на одному каналі: за тим, чий пін на полотні, видно, куди дивиться коментатор. */
  const seedA = await seedPin(env, "memo-seed-A");
  B.store.set(CHANNEL, [{ ...seedA, id: "memo-seed-B", text: "Пін із сервісу B" }]);
  const shot = await shootAll(url);
  assert.ok(shot.ok, `знімки «Огляду»: ${JSON.stringify(shot).slice(0, 300)}`);

  /* Рахуємо запити ОБОЛОНКИ (коментатор «Огляду»), а не рамки макета: рамка того самого походження має свій адаптер зі
     своїм опитуванням, і лічильник сервісу (`memo.log`) їх не розрізнив би. `request.frame()` кидає лише для запитів
     service worker-а — їх ігноруємо. */
  const shell = { A: [], B: [] };
  page.on("request", (r) => {
    let fr;
    try { fr = r.frame(); } catch { return; }
    if (fr !== page.mainFrame()) return;
    for (const [k, svc] of [["A", A], ["B", B]]) {
      if (r.url().startsWith(`${svc.url}/`)) shell[k].push(`${r.method()} ${new URL(r.url()).pathname}`);
    }
  });

  await page.goto(`${url}/app/`);
  await waitFrame(page);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  const idsOnCanvas = async () => {
    try { return (await overviewPins(page)).flatMap((p) => p.ids); } catch { return null; }   // шар ще не піднято
  };
  assert.deepEqual(await until(async () => { const ids = await idsOnCanvas(); return ids?.length ? ids : null; },
    "піни сервісу A на полотні «Огляду»", 20000), ["memo-seed-A"]);
  /* Свідки: коментатор «Огляду» справді ходить у A (інакше «жодного запиту до A» нічого не доводило б), у B — ні. */
  assert.ok(shell.A.length >= 1, `оболонка не звертається до A: ${JSON.stringify(shell)}`);
  assert.deepEqual(shell.B, [], "до зміни оболонка вже ходить у B");

  /* Екран «Підключення» (з дропдауна простору) → «Налаштувати» → нова адреса → «Зберегти». Секрети лишаються (порожнє = лишити). */
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]');
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector(`.mc[data-id="${MODULE}"]`);
  await openCard(page, MODULE);
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="endpoint"]');
  await page.fill('#cn-drawer [data-cn-field="endpoint"]', B.url);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  /* Перевірка пройшла (B живий) → панель закрилась; картка зайнята до кінця `afterModulesChange`, тож «Налаштувати» знову
     доступне лише коли перечитування модулів (а з ним `ovc.invalidate()`) уже позаду. */
  await page.waitForSelector("#cn-drawer", { state: "hidden" });
  await page.waitForSelector(`.mc[data-id="${MODULE}"]:not([aria-busy="true"])`);
  const cfg = await (await fetch(`${url}/api/comment-config?ch=project&it=it1`)).json();
  assert.equal(cfg.config.endpoint, B.url, "свідок: сервер уже віддає адресу B");
  const cutA = shell.A.length;

  /* Назад до задачі (вона на «Огляді»): піни — сервісу B. */
  await page.click('#tabs [data-act="tab"]');
  await page.locator(".cv-card img").first().waitFor();
  /* Чекаємо САМЕ пін B (а не «будь-який»): поки шар перебудовується, на полотні можуть на мить стояти й старі піни. Якщо
     коментатор лишився на старому сервісі, остання побачена відповідь — `["memo-seed-A"]`, і ця помилка так і скаже. */
  await until(async () => { const ids = await idsOnCanvas(); return ids && ids.length === 1 && ids[0] === "memo-seed-B" ? ids : null; },
    "піни сервісу B на полотні «Огляду» (старий сервіс A віддав би memo-seed-A)", 15000);
  assert.ok(shell.B.includes(`GET /c/${encodeURIComponent(CHANNEL)}`), `оболонка не читала канал із B: ${JSON.stringify(shell.B)}`);

  /* Старий сервіс більше не опитується: два періоди опитування адаптера (1 с) — і жодного нового запиту оболонки до A. */
  await sleep(2500);
  assert.deepEqual(shell.A.slice(cutA), [], "після зміни оболонка ще ходить у старий сервіс A");
  assert.deepEqual(outside, [], `запити за межі машини:\n${outside.join("\n")}`);
  assert.deepEqual(env.logs.errors, [], `помилки сторінок:\n${env.logs.errors.join("\n")}`);
});

/* ── f: ізоляція ───────────────────────────────────────────────────────────────────────────────────── */

test("f: жоден сценарій не вивів запит за межі машини, а справжній ~/deai-published не торкнуто", () => {
  assert.ok(REQUESTS_TOTAL > 100, `свідок: замало запитів (${REQUESTS_TOTAL}) — розтяжка могла нічого не бачити`);
  assert.deepEqual(OUTSIDE_ALL, [], `запити за межі машини з усіх сценаріїв:\n${OUTSIDE_ALL.join("\n")}`);
  assert.deepEqual([...new Set(STUBBED_ALL.map((u) => new URL(u).hostname))].sort(), [CDN, LIGA_SB_HOST].sort(),
    "підмінялись запити не лише до CDN (html2canvas) і вигаданого Supabase ЛІГИ (або не підмінялись зовсім)");
  assert.deepEqual(realPublished(), REAL_PUBLISHED_BEFORE, `живий тест торкнувся справжнього ${REAL_PUBLISHED}`);
});

guardRealDeai("g: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
