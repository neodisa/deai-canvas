/**
 * Модулі (Deai 1.0, етап 2а, Task 9) — живе проведення: справжній сервер в ізольованій «машині»
 * (тимчасові `HOME` і `DEAI_HOME`, реєстр пишеться заздалегідь), справжній Chromium.
 *
 * Юніти й сервер-тести (`tests/test_publish_module.py`, `tests/test_static_publish.py`, `tests/test_modules_api.py`,
 * `tests/inspector-space-ds.test.mjs`) доводять кожну ланку окремо; тут те, що їм недоступне, бо живе в
 * браузері: чи сторінка, опублікована в теку, ВІДКРИВАЄТЬСЯ в непрозорому origin пісочниці (модульні скрипти й
 * `fetch` обгортки вимагають CORS), чи плашка «Відкрити» веде туди, де справді лежить публікація, і чи
 * інспектор у документі макета впізнає токен простору, що прийшов у фоні ПІСЛЯ того, як елемент уже запінено.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   1 (публікація в теку) — `Access-Control-Allow-Origin` у `PUBLISHED_HEADERS` (`serve.py`): без нього обгортка
 *        в пісочниці не вантажить `shell/*.js` (`<script type=module>` — завжди CORS) і `manifest.json`, смуга
 *        не зʼявляється, `requestfailed` непорожній. Явний запис `static-publish` у `space.json` (0.22: новий простір
 *        пише його сам, наявні — стартовий крок `spaces.materialize_static_publish`): без нього у звичайному просторі публікувати нікому —
 *        кнопка зникає з моделі смуги.
 *        `sandbox …` у CSP (без `allow-same-origin`): без нього `POST` зі сторінки превʼю йшов би з origin
 *        канваса (200 і нова публікація), а не з `Origin: null` (403).
 *   2 (токени простору)   — `?sp=` у теґу інспектора (`inspector_ds_arg`), фонове завантаження й перемальовка
 *        запіненого (`_dsArrived`) у `inspector.js`, `/api/ds-tokens` і постачальник ролі `tokens`.
 *   3 (форма ЛІГА)        — `'legacy'` у `capabilities.publish`: ЛІГА-простір публікує зашитим шляхом (збірка З
 *        коментатором, жодного `static-publish` і теки `deai-published`), смуга лишає пароль/Teams/GitLab.
 *   4 (ізоляція)          — `HOME`/`DEAI_HOME` у `fixture.mjs`; справжні `~/.deai` і `~/deai-published` не торкнуто.
 *
 * ⛔ Лише Playwright Chromium: панель Browser застосунку Claude блокує скрипти пісочниці
 * (`ERR_BLOCKED_BY_CLIENT`), і сценарій 1 там червонів би з причини, що до коду не стосується.
 */
import assert from "node:assert/strict";
import {
  existsSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { REAL_DEAI, VIEW, guardRealDeai, postJson, sleep, spacesApi, stop, text, waitText, waitBarReady } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";
import { LIGA_SB_HOST, hermeticLiga } from "./_liga-supabase.mjs";

/* Своя смуга: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs` стереже, що жодна база не
   збігається з чужою). Тести ЦЬОГО файла йдуть послідовно, тож одна база на всіх. */
const PORT_BASE = 12700;

const PUBLISHED_CSP = "sandbox allow-scripts allow-forms allow-popups allow-modals";

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

/** Усі запити за межі машини з усіх сценаріїв — для підсумкового тесту. */
const OUTSIDE_ALL = [];

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* ── прилади ───────────────────────────────────────────────────────────────────────────────────────── */

const isLocal = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname);
};

/**
 * Сервер + контекст браузера. Контекст:
 *   · рахує КОЖЕН запит усіх своїх сторінок (`requests`) — і канваса, і вікна превʼю, і рамок у них;
 *   · не пускає нічого за межі машини (`route` → `abort`): якщо код колись піде назовні, тест не постукає на
 *     справжній хост, а запис у `outside` його видасть;
 *   · збирає, що пише консоль і що падає, окремо для канваса (`canvas`) і для сторінок, відкритих із нього
 *     (`popups`): CORS-відмови видно саме там.
 */
async function boot(t, { spaces, beforeOpen = null, supabase = false } = {}) {
  const server = await startServer(null, { portBase: PORT_BASE, spaces, supabase });
  t.after(() => stop(server.child));
  beforeOpen?.(server);
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());

  const requests = [];
  const outside = [];
  context.on("request", (r) => {
    requests.push(r.url());
    /* 0.27.0: рамка ЛІГИ з конфігом Supabase питає вигаданий хост завжди (командне сховище в кожній рамці); `hermeticLiga`
       відповідає за нього порожньо, тож це не «втеча» — рахуємо лише справжні запити за межі машини. */
    if (!isLocal(r.url()) && new URL(r.url()).hostname !== LIGA_SB_HOST) { outside.push(r.url()); OUTSIDE_ALL.push(r.url()); }
  });
  await hermeticLiga(context);

  const logs = { canvas: [], popups: [], failed: [], errors: [] };
  const watch = (page, bucket) => {
    page.on("console", (m) => { if (m.type() === "error") logs[bucket].push(m.text()); });
    page.on("pageerror", (e) => logs.errors.push(String(e.message ?? e)));
    page.on("requestfailed", (r) => logs.failed.push(`${r.url()} — ${r.failure()?.errorText ?? "?"}`));
  };
  const page = await context.newPage();
  watch(page, "canvas");
  context.on("page", (p) => { if (p !== page) watch(p, "popups"); });
  return { ...server, context, page, requests, outside, logs };
}

/** Відкрити канвас і дочекатись смуги. */
async function openCanvas(page, url) {
  await page.goto(`${url}/app/`);
  await waitBarReady(page, 15000);
}

const pubLabel = (page) => text(page, "#bar .lbl-pub");

/** Відкрити дропдаун публікації (якщо він ще закритий) і дочекатись його рядків. */
async function openPubDd(page) {
  if (!(await page.locator("#bar .dd--right").count())) await page.click('#bar [data-dd="pub"]');
  await page.waitForSelector('#bar .dd--right [data-act="togglepub"]');
}

/** Позначена чи ітерація для публікації — за вигляду галочки в дропдауні (те, що бачить дизайнер). */
async function iterMarked(page) {
  await openPubDd(page);
  return (await page.locator('#bar .dd--right [data-act="togglepub"] .chk--on').count()) === 1;
}

const iterFlag = (dir) => JSON.parse(readFileSync(path.join(dir, "iterations.json"), "utf8")).iterations[0].published;

async function waitFlag(dir, want) {
  for (let i = 0; i < 60; i += 1) {
    if (iterFlag(dir) === want) return;
    await sleep(100);
  }
  assert.fail(`iterations.json: published так і не став ${want}`);
}

/** Жодного запиту за межі машини — і свідок, що запити були (інакше «жодного» зеленіло б на порожнечі). */
function assertStayedHome({ requests, outside }, what) {
  assert.ok(requests.length > 10, `свідок: замало запитів (${requests.length}) — ${what}`);
  assert.deepEqual(outside, [], `${what}: запити за межі машини:\n${outside.join("\n")}`);
}

/* ── сценарій 1: публікація в теку ─────────────────────────────────────────────────────────────────── */

const MOCKUP = (id) => `<!doctype html><html lang="uk"><head><meta charset="utf-8"><title>Макет ${id}</title></head>
<body><h1>${id}</h1><p id="mark">модулі, сценарій 1</p></body></html>`;

test("1: простір без інтеграцій — «Опублікувати» → плашка → «Відкрити» → /published/… відкривається, обгортка жива, CORS чистий, POST із пісочниці — 403", async (t) => {
  const X = taskFixture({ html: MOCKUP });
  const { page, context, url, home, logs, requests, outside } = await boot(t, {
    spaces: [{ name: "P", id: "p", color: "space-3", tasks: { blog: { dir: X.dir, title: "Задача блог" } } }],
  });
  await openCanvas(page, url);
  /* Кнопка стоїть на `capabilities.publish`: у просторі без інтеграцій її тримає неявний `static-publish`. */
  await page.waitForSelector('#bar [data-act="publish"]', { timeout: 15000 }).catch(() => assert.fail(
    "у смузі простору без інтеграцій немає «Опублікувати»: неявний static-publish не публікує"));
  assert.equal(await pubLabel(page), "Опублікувати", "свідок: ще нічого не опубліковано");

  /* Позначити ітерацію. Фікстура віддає її вже позначеною — знімаємо й ставимо назад ЧЕРЕЗ ІНТЕРФЕЙС, а
     не покладаємось на стартовий стан; між двома кліками — відмова «нічого не позначено»: публікація без
     позначених ітерацій не мовчить, а каже, що робити. */
  assert.equal(await iterMarked(page), true, "свідок: фікстурна ітерація позначена для публікації");
  await page.click('#bar .dd--right [data-act="togglepub"]');
  await waitFlag(X.dir, false);
  await page.keyboard.press("Escape");
  await page.click('#bar [data-act="publish"]');
  await page.waitForSelector(".cv-ask", { timeout: 10000 });
  assert.match(await page.locator(".cv-ask").innerText(), /Жодної ітерації не позначено/,
    "публікація без позначених ітерацій не назвала причини");
  await page.click('.cv-ask [data-a="ok"]');
  await page.waitForSelector(".cv-ask", { state: "detached" });
  assert.equal(await pubLabel(page), "Опублікувати", "кнопка лишилась «Публікую…» після відмови");
  assert.equal(await page.locator('.cv-notice[data-notice="publish-local"]').count(), 0, "плашка успіху на відмові");

  await page.locator('#bar [data-dd="pub"]').waitFor();
  assert.equal(await iterMarked(page), false, "галочка не знялась");
  await page.click('#bar .dd--right [data-act="togglepub"]');
  await waitFlag(X.dir, true);
  await page.keyboard.press("Escape");

  /* Публікація. Відповідь ловимо, щоб побачити, ДЕ лежить результат, а не лише що плашка зʼявилась. */
  const answered = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/publish" && r.request().method() === "POST");
  await page.click('#bar [data-act="publish"]');
  const res = await answered;
  assert.equal(res.status(), 200, `POST /api/publish: ${res.status()} ${await res.text()}`);
  const body = await res.json();
  assert.equal(body.ok, true);
  assert.equal(body.local.url, "/published/p/blog/", "адреса публікації не за <простір>/<задача>");
  const published = path.join(home, "deai-published", "p", "blog");
  assert.equal(realpathSync(body.local.path), realpathSync(published),
    "тека публікації — не `<домівка>/deai-published/<простір>/<задача>` ТИМЧАСОВОЇ домівки");
  assert.ok(!("url" in body) && !("deploy_error" in body), "модульна відповідь несе ЛІГА-поля (Vercel)");

  await page.waitForSelector('.cv-notice[data-notice="publish-local"]', { timeout: 10000 });
  assert.equal(await text(page, '.cv-notice[data-notice="publish-local"] span'), "Опубліковано локально");
  await waitText(page, "#bar .lbl-pub", "Оновити");
  assert.equal(await page.locator('.cv-ask').count(), 0, "діалог помилки на успішній публікації");

  /* Що лягло на диск: статична збірка БЕЗ коментатора (його Supabase ззовні не потрібен) і з маркером. */
  for (const f of [".deai-published", "index.html", "manifest.json", path.join("it1", "holovna", "index.html")]) {
    assert.ok(existsSync(path.join(published, f)), `у теці публікації немає ${f}`);
  }
  assert.equal(existsSync(path.join(published, "comment-layer")), false, "модульна публікація повезла коментатор");
  assert.ok(!/supabase|comment-layer/i.test(readFileSync(path.join(published, "it1", "holovna", "index.html"), "utf8")),
    "у сторінці превʼю лишився сніпет коментатора");

  /* «Відкрити» з плашки — нова вкладка на /published/p/blog/. */
  const [popup] = await Promise.all([
    context.waitForEvent("page"),
    page.click('.cv-notice[data-notice="publish-local"] button[data-act="open"]'),
  ]);
  await popup.waitForLoadState("load");
  assert.equal(new URL(popup.url()).pathname, "/published/p/blog/", `«Відкрити» веде не туди: ${popup.url()}`);

  /* Обгортка справді ЖИВА: смуга піднялась (її вантажить модульний скрипт, тобто CORS), рамка відкрила
     макет. Вміст рамки читаємо через Playwright: з пісочниці до неї не дістатись (два непрозорі origin). */
  try {
    await popup.locator("#bar .bar").waitFor({ timeout: 15000 });
  } catch (e) {
    assert.fail(`обгортка превʼю не піднялась (CORS у пісочниці?)\nконсоль: ${logs.popups.join(" | ")}\nвпало: ${logs.failed.join(" | ")}`);
  }
  assert.equal(await popup.title(), "Задача блог", "назва задачі у вкладці превʼю");
  const h1 = popup.frameLocator("#frame").locator("h1");
  await h1.waitFor({ timeout: 15000 });
  assert.equal(await h1.innerText(), "holovna", "рамка превʼю не показала макет");
  assert.equal(await popup.frameLocator("#frame").locator("#mark").isVisible(), true);

  /* Пісочниця: непрозорий origin — нема `localStorage` канваса, а `fetch` файла того ж сервера проходить
     лише завдяки ACAO (без нього тут було б TypeError). */
  assert.equal(await popup.evaluate(() => window.origin), "null", "сторінка превʼю не в пісочниці");
  assert.equal(await popup.evaluate(() => { try { return typeof localStorage.length; } catch (e) { return e.name; } }),
    "SecurityError", "сторінка превʼю бачить localStorage — origin не непрозорий");
  assert.equal(await popup.evaluate(() => fetch("manifest.json").then((r) => r.status, (e) => e.name)), 200,
    "fetch('manifest.json') із пісочниці не пройшов (CORS)");

  /* Заголовки роздачі — на обгортці, на файлі модуля, на внутрішній сторінці. Свідчення САМОГО сервера,
     окреме від того, що бачить браузер вище: заголовок може бути, а обгортка — не жити, і навпаки. */
  for (const rel of ["", "manifest.json", "it1/holovna/"]) {
    const r = await fetch(`${url}/published/p/blog/${rel}`);
    assert.equal(r.status, 200, `GET /published/p/blog/${rel}`);
    assert.equal(r.headers.get("content-security-policy"), PUBLISHED_CSP, `CSP на «${rel}»`);
    assert.equal(r.headers.get("access-control-allow-origin"), "*", `ACAO на «${rel}»`);
    assert.equal(r.headers.get("x-content-type-options"), "nosniff", `nosniff на «${rel}»`);
  }
  const wrapper = await (await fetch(`${url}/published/p/blog/`)).text();
  const shellJs = /src="(shell\/[^"]+\.js)"/.exec(wrapper)?.[1];
  assert.ok(shellJs, "свідок: обгортка не вантажить жодного shell/*.js (модульного скрипта)");
  const sj = await fetch(`${url}/published/p/blog/${shellJs}`);
  assert.equal(sj.headers.get("access-control-allow-origin"), "*", "модульний скрипт без ACAO не завантажиться в пісочниці");

  assert.deepEqual(logs.popups, [], `консоль превʼю не порожня (CORS?):\n${logs.popups.join("\n")}`);
  assert.deepEqual(logs.failed, [], `запити, що впали:\n${logs.failed.join("\n")}`);
  assert.deepEqual(logs.errors, [], `помилки сторінок:\n${logs.errors.join("\n")}`);
  /* Консоль канваса: єдине, що там МАЄ бути, — відмова 400 з кроку «нічого не позначено» вище. */
  const canvasNoise = logs.canvas.filter((m) => !/status of 400 \(no iterations marked for publish/.test(m));
  assert.deepEqual(canvasNoise, [], `консоль канваса не порожня:\n${canvasNoise.join("\n")}`);

  /* POST зі сторінки превʼю (її origin — `null`) відхиляється, і НІЧОГО не публікується. Збірку `publish/`
     задачі стираємо ПЕРЕД спробою: справжня публікація відтворила б її, відмова — ні.

     ⛔ Саму 403 сторінка прочитати НЕ може: відповідь на запит із чужого origin без ACAO браузер ховає від
     скрипта (`fetch` відхиляється `TypeError`), а Playwright бачить `requestfailed`, не `response`. Статус
     дивимось на мережевому рівні — CDP `Network.responseReceivedExtraInfo` (сире слово сервера), а що це
     запит із `Origin: null` — з його заголовків у `requestWillBeSentExtraInfo`. */
  rmSync(path.join(X.dir, "publish"), { recursive: true, force: true });
  const cdp = await context.newCDPSession(popup);
  await cdp.send("Network.enable");
  const sent = [];
  const wire = new Map();
  const raw = new Map();
  cdp.on("Network.requestWillBeSent", (e) => sent.push(e));
  cdp.on("Network.requestWillBeSentExtraInfo", (e) => wire.set(e.requestId, e));
  cdp.on("Network.responseReceivedExtraInfo", (e) => raw.set(e.requestId, e));
  const outcome = await popup.evaluate(() => fetch("/api/publish", { method: "POST" })
    .then((r) => ({ status: r.status }), (e) => ({ error: e.name })));
  let post = null;
  for (let i = 0; i < 50; i += 1) {
    post = sent.find((e) => new URL(e.request.url).pathname === "/api/publish") ?? null;
    if (post && raw.has(post.requestId) && wire.has(post.requestId)) break;
    await sleep(100);
  }
  assert.ok(post, "запит POST /api/publish зі сторінки превʼю не зафіксовано");
  assert.equal(post.request.method, "POST");
  assert.equal(wire.get(post.requestId)?.headers?.Origin, "null", "запит пішов не з непрозорого origin");
  assert.equal(raw.get(post.requestId)?.statusCode, 403, `відповідь сервера на POST із пісочниці: ${raw.get(post.requestId)?.statusCode}`);
  /* Відповідь 403 не має ACAO, тож сторінка бачить відмову CORS (`TypeError`) або саму 403 — але не успіх. */
  assert.ok(outcome.status === 403 || outcome.error === "TypeError", `сторінка превʼю отримала ${JSON.stringify(outcome)}`);
  assert.equal(existsSync(path.join(X.dir, "publish")), false, "POST із пісочниці запустив збірку");
  await cdp.detach();

  assertStayedHome({ requests, outside }, "простір без інтеграцій");
});

/* ── сценарій 2: токени простору в інспекторі ──────────────────────────────────────────────────────── */

const TOKENS_CSS = ":root{\n  --brand:#025CFF;\n  --ink:#111111;\n}\n";

/** Макет: три змінні з трьома різними долями й один літерал, що дорівнює значенню токена. */
const TOKEN_PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
:root{--brand:#025CFF;--ink:#222222;--mine:#123456}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#wrap{margin:30px;padding:40px;background:#fff;display:flex;gap:24px}
.card{margin:0;padding:16px;background:#eef;width:200px;height:120px}
#ok{color:var(--brand)}
#over{color:var(--ink)}
#off{color:var(--mine)}
#hard{color:#025CFF}
</style></head><body>
<div id="wrap">
  <p id="ok" class="card">Токен ${id}</p>
  <p id="over" class="card">Перевизначений ${id}</p>
  <p id="off" class="card">Повз ДС ${id}</p>
  <p id="hard" class="card">Хардкод ${id}</p>
</div></body></html>`;

async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction((s) => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return !!api.pinned && api.pinned.id === s;
  }, sel.slice(1), { timeout: 5000 });
}

/** Вирок поля (`data-verdict` обгортки) й титул поля — те, що дизайнер бачить очима (0.29.0: крапки й рядка про ДС
 *  у панелі властивостей нема, колір поля й чип — похідні від вироку). */
const verdictOf = (page, prop) => page.evaluate((p) => {
  const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
  return f ? f.getAttribute("data-verdict") : null;
}, prop);
const titleOf = (page, prop) => page.evaluate((p) => {
  const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
  return f ? f.getAttribute("title") : null;
}, prop);

test("2: css-tokens через POST /api/module-enable — інспектор упізнає токен простору, що приїхав ПІСЛЯ пінування", async (t) => {
  const { dir } = taskFixture({ html: TOKEN_PAGE, pages: ["holovna"] });
  const cssDir = mkdtempSync(path.join(tmpdir(), "dc-live-tokens-"));
  const cssFile = path.join(cssDir, "tokens.css");
  writeFileSync(cssFile, TOKENS_CSS);
  const { page, url, requests, outside } = await boot(t, {
    spaces: [{ name: "Tok", id: "tok", color: "space-2", tasks: { lab: { dir, title: "Лабораторія" } } }],
    /* Напрямок задачі — `tool`: статичної ДС у нього нема, тож до токенів простору інспектор чесно каже
       «ДС немає». Фікстура з `spaces` напрямку не бере (її `profile` ігнорується), тож пишемо його в
       `tasks.json` простору до першого запиту (4d-4a: напрямок задачі — лише `track`; `profile` рантайм не читає). */
    beforeOpen: (server) => {
      const file = path.join(server.spaces[0].path, "tasks.json");
      const cfg = JSON.parse(readFileSync(file, "utf8"));
      cfg.tasks.lab.track = "tool";
      writeFileSync(file, JSON.stringify(cfg));
    },
  });
  assert.equal((await spacesApi(url)).spaces[0].capabilities.vcs, null, "свідок: у звичайному просторі синку нема");

  /* До модуля токенів нема: сервер відповідає «профілю немає», а не помилкою. */
  assert.deepEqual(await (await fetch(`${url}/api/ds-tokens?space=tok`)).json(), { profile: null },
    "свідок: до вмикання css-tokens токени простору вже є");

  const enabled = await (await postJson(url, "/api/module-enable", {
    space: "tok", id: "css-tokens", settings: { file: cssFile },
  })).json();
  assert.equal(enabled.ok, true, JSON.stringify(enabled));
  assert.equal(enabled.module.id, "css-tokens");
  assert.equal(enabled.module.enabled, true);
  assert.equal(enabled.check.ok, true, `check модуля: ${JSON.stringify(enabled.check)}`);
  const served = await (await fetch(`${url}/api/ds-tokens?space=tok`)).json();
  assert.equal(served.profile, "space:tok");
  assert.equal(served.source, "tokens.css");
  assert.deepEqual(served.tokens, { "--brand": ["#025CFF"], "--ink": ["#111111"] });

  /* Токени приходять у фоні, ОДИН раз на завантаження рамки. Тримаємо відповідь, поки елемент не запінено:
     так перевіряється саме те, що відрізняє 2а від статичної ДС, — перемальовка вже запіненого. Без
     утримання сценарій залежав би від того, хто швидший: відповідь чи клік (гонка, яку й описав Task 7). */
  let release;
  const held = new Promise((done) => { release = done; });
  const asked = [];
  await page.route(/\/api\/ds-tokens\?space=/, async (route) => {
    asked.push(route.request().url());
    await held;
    await route.continue();
  });
  const arrived = page.waitForResponse((r) => /\/api\/ds-tokens\?space=tok/.test(r.url()), { timeout: 20000 });

  await openCanvas(page, url);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  const tag = await page.frameLocator("#frame").locator("head").evaluate(() => Array.from(document.scripts)
    .map((s) => s.src).find((s) => s.includes("inspector.js")) || "");
  assert.ok(tag.includes("sp=tok") && tag.includes("ds=tool"), `тег інспектора без простору чи напрямку: ${tag}`);

  await page.click('#hud [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame").contentWindow.CanvasInspector.on === true,
    null, { timeout: 3000 });
  const t0 = Date.now();

  /* ДО відповіді: профіль без ДС — рядок про це словами, жодних вироків «повз ДС». */
  await pin(page, "#over");
  assert.equal(await verdictOf(page, "color"), "token", "до токенів напрямок без ДС нікого не звинувачує");
  assert.equal(asked.length, 1, `запитів токенів до відповіді: ${asked.length} (рівно один на завантаження рамки)`);

  release();
  const answer = await arrived;
  assert.equal(answer.status(), 200);
  assert.ok(Date.now() - t0 < 6500, "відповідь тримали довше за тайм-аут інспектора (7 с): сценарій нічого не доводить");

  /* ПІСЛЯ: той самий пін перемальовується сам — без кліку. */
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="color"]')
    ?.getAttribute("data-verdict") === "overridden", null, { timeout: 8000 });
  assert.equal(await verdictOf(page, "color"), "overridden",
    "--ink у макеті #222222, у файлі #111111: «перевизначено» має зʼявитись на запіненому без повторного кліку");
  assert.match(await titleOf(page, "color"), /#111111/, "титул поля мусить казати, що приписує ДС простору");

  await pin(page, "#off");
  assert.equal(await verdictOf(page, "color"), "off-ds", "--mine немає у файлі токенів — повз ДС");
  assert.match(await titleOf(page, "color"), /--mine/);

  await pin(page, "#ok");
  assert.equal(await verdictOf(page, "color"), "token", "токен простору з тим самим значенням лишається зеленим");

  /* Дорога назад у ДС і тюнер: хардкод, що дорівнює значенню токена, веде до `--brand`, а пакет Клоду
     несе, що дизайнер вибрав ТОКЕН, і з якого файла токени (`ds.source`). */
  await pin(page, "#hard");
  assert.equal(await verdictOf(page, "color"), "hardcode");
  const snap = await page.evaluate(() => {
    const b = document.querySelector('#insp-panel .insp-f[data-prop="color"] .insp-snap');
    return b ? { token: b.dataset.token, val: b.dataset.val } : null;
  });
  assert.ok(snap, "хардкод, що дорівнює значенню токена простору, не має дороги назад");
  assert.equal(snap.token, "--brand");
  await page.click('#insp-panel .insp-f[data-prop="color"] .insp-snap');
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="color"][data-tuned]'),
    null, { timeout: 3000 });
  let pkg = null;
  for (let i = 0; i < 30 && !pkg; i += 1) {
    const got = await (await fetch(`${url}/api/tuner`)).json();
    const cand = got.package || got;
    if ((cand.elements || []).some((e) => (e.edits || []).some((x) => x.prop === "color"))) pkg = cand;
    else await sleep(100);
  }
  assert.ok(pkg, "правка-повернення не доїхала в пакет тюнера");
  const edit = pkg.elements.flatMap((e) => e.edits).find((x) => x.prop === "color");
  assert.deepEqual(edit.snap, { token: "--brand", value: snap.val }, "пакет не каже, що вибрано ТОКЕН");
  assert.equal(snap.val.toLowerCase(), "#025cff");
  assert.equal(pkg.ds.profile, "space:tok");
  assert.equal(pkg.ds.known, true);
  assert.equal(pkg.ds.source, "tokens.css", "пакет не каже, з якого файла токени простору");

  assertStayedHome({ requests, outside }, "інспектор із токенами простору");
});

/* ── сценарій 3: форма ЛІГА ────────────────────────────────────────────────────────────────────────── */

test("3: ЛІГА-простір — capabilities.publish 'legacy', смуга з GitLab/паролем/Teams, публікація не чіпає static-publish і не виходить назовні", async (t) => {
  const A = taskFixture({ html: MOCKUP });
  /* `supabase: true`: ЛІГА-превʼю несе шар коментатора лише з конфігом Supabase у `tasks.json` (4b-2; без нього публікація
     ЛІГИ — без командних коментарів). Хост вигаданий, а збірка (`build_only`) мережі не торкається. */
  const { page, url, home, requests, outside } = await boot(t, {
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { a: { dir: A.dir, title: "Задача A" } } }],
    supabase: true,
  });

  const reg = await spacesApi(url);
  const liga = reg.spaces.find((s) => s.id === "liga");
  assert.equal(liga.capabilities.publish, "vercel-publish", `capabilities простору ЛІГА (4d-4b: явний запис): ${JSON.stringify(liga.capabilities)}`);
  assert.equal(liga.compat?.vcs, "design-canvas", "свідок: ЛІГА-простір має явний запис vcs зі схемою ЛІГИ");

  await openCanvas(page, url);
  await page.waitForSelector('#bar [data-act="publish"]', { timeout: 15000 });
  const acts = await page.$$eval("#bar [data-act], #bar [data-dd]", (els) => els.map((e) => e.dataset.act || `dd:${e.dataset.dd}`));
  for (const want of ["dd:gl", "dd:pub", "publish"]) assert.ok(acts.includes(want), `у смузі ЛІГА немає «${want}» (${acts})`);
  await page.click('#bar [data-dd="pub"]');
  assert.deepEqual(await page.$$eval("#bar .dd--right [data-act]", (els) => els.map((e) => e.dataset.act)),
    ["togglepub", "openpreview", "copylink", "teamsnotify", "pubpw"],
    "дропдаун публікації ЛІГА: пароль превʼю й Teams мусять бути на місці");
  assert.equal(await page.locator("#bar .dd--right .dd-note").count(), 1, "застереження про публічне ЛІГА-посилання");
  await page.keyboard.press("Escape");

  /* Клік по «Опублікувати»: запит `POST /api/publish` перехоплюємо й відповідаємо ЗА сервер — справжній
     деплой (`npx vercel`) у живому тесті не запускається НІКОЛИ. Відповідь — успішний деплой ЛІГА (`url`,
     без `local`): інтерфейс має піти ЛІГА-гілкою, без плашки локальної публікації й без діалогу помилки. */
  const published = [];
  await page.route("**/api/publish", async (route) => {
    published.push(route.request().postData());
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ ok: true, dir: "/stub/publish", iterations: 1, frames: 0, url: "https://stub.invalid/liga-a" }),
    });
  });
  const before = outside.length;
  await page.click('#bar [data-act="publish"]');
  await page.waitForFunction(() => document.querySelector("#bar .lbl-pub")?.textContent.trim() !== "Публікую…", null, { timeout: 5000 });
  await sleep(500);                                   // відповідь, `render()` і те, що за ним, встигають піти в мережу
  assert.equal(published.length, 1, `запитів /api/publish від кліку: ${published.length}`);
  assert.equal(await page.locator('.cv-notice[data-notice="publish-local"]').count(), 0,
    "ЛІГА-публікація показала плашку локальної публікації");
  assert.equal(await page.locator(".cv-ask").count(), 0, "успішна ЛІГА-відповідь дала діалог помилки");
  assert.equal(outside.length, before, "клік «Опублікувати» вивів запит за межі машини");
  assert.equal(existsSync(path.join(A.dir, "publish")), false, "перехоплений запит дійшов до сервера");

  /* Справжній серверний шлях ЛІГА — але лише збірка (`build_only`): без деплою, без мережі. */
  const built = await (await postJson(url, "/api/publish", { build_only: true })).json();
  assert.equal(built.ok, true, JSON.stringify(built));
  assert.ok(!("local" in built) && !("url" in built) && !("deploy_error" in built), `збірка ЛІГА: ${JSON.stringify(built)}`);
  assert.ok(existsSync(path.join(built.dir, "comment-layer")), "ЛІГА-збірка без коментатора (це шлях модуля, не ЛІГА)");
  assert.ok(/comment-layer/i.test(readFileSync(path.join(built.dir, "it1", "holovna", "index.html"), "utf8")),
    "у сторінці ЛІГА-превʼю нема сніпета коментатора");
  assert.equal(existsSync(path.join(home, "deai-published")), false, "ЛІГА-публікація зайшла в static-publish");
  assert.equal(existsSync(path.join(home, "deai-published", "liga")), false);

  assertStayedHome({ requests, outside }, "ЛІГА-простір");
});

/* ── сценарій 4: ізоляція ──────────────────────────────────────────────────────────────────────────── */

test("4: жоден сценарій не вивів запит за межі машини, а справжній ~/deai-published не торкнуто", () => {
  assert.deepEqual(OUTSIDE_ALL, [], `запити за межі машини з усіх сценаріїв:\n${OUTSIDE_ALL.join("\n")}`);
  assert.deepEqual(realPublished(), REAL_PUBLISHED_BEFORE, `живий тест торкнувся справжнього ${REAL_PUBLISHED}`);
});

guardRealDeai("5: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
