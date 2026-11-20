/**
 * Публікація на Vercel (Deai 0.3.0, етап 2b-1, Task 4) — живе проведення: справжній сервер в ізольованій «машині»
 * (тимчасові `HOME` і `DEAI_HOME`), справжній Chromium.
 *
 * Юніти (`tests/test_vercel_publish.py`, `tests/test_publish_module.py`, `tests/spaces-publish.test.mjs`,
 * `tests/bar-model.test.mjs`, `tests/spaces-wiring.test.mjs`) доводять кожну ланку окремо; тут те, що їм недоступне,
 * бо живе в браузері: плашка, вікно «Відкрити» (`noopener`, фрагмент `#k=` із паролем), буфер обміну, застереження в
 * дропдауні, діалог помилки з текстом сервера і гонка «опублікував — перейшов на іншу задачу».
 *
 * ⛔ Жодного звернення до Vercel, навіть невдалого. Модуль `vercel-publish` тут НЕ вмикається: `POST
 * /api/module-enable` викликав би його `check()`, а той ходить на `api.vercel.com` з ПРОЦЕСУ СЕРВЕРА — а розтяжка
 * мережі браузера туди не дотягується. Тому «простір із Vercel» підроблено у браузері:
 *   · `/api/task` переписується на льоту — `space.capabilities.publish = 'vercel-publish'` і поля, які справжній сервер
 *     віддавав би для такого модуля (`publish_gate`, `publish_gate_stale`, `publish_share_url`, `publish_remote`);
 *   · `POST /api/publish` виконує сам тест: відповідь заготовлена, а в гонці — утримується обіцянкою.
 * Сервер у публікації не бере участі взагалі; у кінці перевіряється, що модуль так і лишився вимкненим.
 * Те, що браузер НЕ виходить за межі машини, стереже розтяжка: `route` → `abort` для всього не-localhost і запис у
 * `outside`; єдиний дозволений виняток — вікно превʼю `https://pv-12345678.vercel.app` (його підміняє тест, у ньому
 * маленька сторінка).
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   a (плашка, «Відкрити», «Скопіювати») — `noopener` у плашці (`app.js`, дія `publish`): без нього `window.opener`
 *        вікна превʼю — канвас; `remoteOpenUrl` (посилання з `#k=`, а не голу адресу); `copyLinkText(share)`;
 *        `textContent` у `notice(…, lines)`: попередження модуля лягає ТЕКСТОМ, не розміткою.
 *   b (застереження) — `notes` у `bar-model.js` (`publish_gate === false` → `public`, `publish_gate_stale === true` →
 *        `stale`) і `.dd-note--<id>` у `shell-bar.js`; поле не прийшло — мовчимо.
 *   c (помилки) — `PUBLISH_ERR_KEYS`/`publishErr` (`spaces-model.js`): людський текст ПЛЮС текст сервера (`serverText`).
 *   d (гонка) — `publishReaction(r, sp0, sameTask())`: на іншій задачі — тост із назвою, без плашки й `render()`.
 *   e (форма ЛІГА) — `isLegacyPublish`: відповідь ЛІГА лишається «лише `render()`», розмітка дропдауна — як була.
 *
 * ⛔ Лише Playwright Chromium (панель Browser застосунку Claude блокує частину того, що тут потрібно).
 */
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, sleep, spacesApi, stop, text, waitText, waitBarReady } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs` стереже, що жодна база не
   збігається з чужою). Тести ЦЬОГО файла йдуть послідовно, тож одна база на всіх. */
const PORT_BASE = 13000;

const MODULE = "vercel-publish";
const STUB_HOST = "pv-12345678.vercel.app";
const SITE = `https://${STUB_HOST}`;
/* Пароль із символами, які ламають недбале склеювання посилання: пробіл, `@`, `/`. Сервер кодує його
   `quote(pw, safe='')` — те саме, що `encodeURIComponent`. */
const PW = "p@ss w/rd";
const FRAG = `#k=${encodeURIComponent(PW)}`;
const SHARE = `${SITE}${FRAG}`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Усі запити за межі машини з усіх сценаріїв — для підсумкового тесту. */
const OUTSIDE_ALL = [];

const isLocal = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname);
};

const MOCKUP = (id) => `<!doctype html><html lang="uk"><head><meta charset="utf-8"><title>Макет ${id}</title></head>
<body><h1>${id}</h1><p>Публікація на Vercel.</p></body></html>`;
const PREVIEW_HTML = `<!doctype html><html lang="uk"><head><meta charset="utf-8"><title>Превʼю</title></head>
<body><p id="stub">підставне превʼю</p></body></html>`;

/**
 * Сервер + контекст браузера + підробка Vercel.
 *   · контекст рахує КОЖЕН свій запит (`requests`) і не пускає нічого за межі машини (`abort`); запис у `outside`
 *     видасть кожну спробу. Єдине, що дозволено, — вікно превʼю на `STUB_HOST`: його перехоплює `route`, зареєстрований
 *     ПІЗНІШЕ за «блокувальний» (Playwright запускає маршрути від останнього до першого) і віддає маленьку сторінку;
 *   · `fake` — стан підробки; `/api/task` і `POST /api/publish` описані в шапці. `legacy: true` — простір ЛІГА, де
 *     НІЧОГО не підроблено (сценарій e).
 * Дві задачі (`a`, `b`) у просторі: гонці є куди перейти.
 */
async function boot(t, { legacy = false, fakeVercel = !legacy } = {}) {
  const A = taskFixture({ html: MOCKUP });
  const B = taskFixture({ html: MOCKUP });
  const tasks = { a: { dir: A.dir, title: "Задача A" }, b: { dir: B.dir, title: "Задача B" } };
  const space = legacy
    ? { name: "Liga", id: "liga", color: "space-2", legacy: true, tasks, roles: ["vcs", "publish", "notify"] }     // 4d-4b: мігрована ЛІГА — явні записи
    : { name: "P", id: "p", color: "space-3", tasks };
  const server = await startServer(null, { portBase: PORT_BASE, spaces: [space] });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW, permissions: ["clipboard-read", "clipboard-write"] });
  t.after(() => context.close());

  const requests = [];
  const outside = [];
  context.on("request", (r) => {
    requests.push(r.url());
    if (!isLocal(r.url())) { outside.push(r.url()); OUTSIDE_ALL.push(r.url()); }
  });
  await context.route((u) => !isLocal(u.href), (route) => route.abort("blockedbyclient"));
  const previewHits = [];
  await context.route((u) => u.hostname === STUB_HOST, (route) => {
    previewHits.push(route.request().url());
    return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: PREVIEW_HTML });
  });

  const logs = { errors: [], console: [] };
  const page = await context.newPage();
  page.on("pageerror", (e) => logs.errors.push(String(e.message ?? e)));
  page.on("console", (m) => { if (m.type() === "error") logs.console.push(m.text()); });

  const fake = {
    /* `publish_gate` до публікації: чи заданий пароль зараз. `undefined` — сервер поля не дав (модуль «у теку»). */
    gate: true,
    /* Слід публікації за id задачі: `{url, gated, stale, share}`. Нема — ще не публікувалась. */
    tasks: {},
    /* id задачі з останньої відповіді `/api/task` — «хто була поточною» в момент клику. */
    last: null,
    posts: [],
    /* Що відповісти на `POST /api/publish`. */
    reply: { status: 200, body: { ok: true, url: SITE, verified: true, iterations: 1, frames: 2 } },
    /* Утримання відповіді (гонка): `hold` — обіцянка, яку треба розв'язати; `arrived` — кличеться, коли запит дійшов. */
    hold: null,
    arrived: null,
  };

  if (fakeVercel) {
    await page.route((u) => u.pathname === "/api/task", async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      fake.last = body.id;
      body.space = { ...body.space, capabilities: { ...body.space.capabilities, publish: MODULE } };
      const own = fake.tasks[body.id];
      if (own) {
        /* Рівно те, що віддає `task_publish_share` + `/api/task` після публікації модулем «за адресою». */
        body.publish_url = own.url;
        body.published_at = "17.10.2026 12:00";
        body.publish_remote = {
          module: MODULE, url: own.url, gated: own.gated, published_at: "2026-10-17T10:00:00Z",
          state: { project: "pv-12345678", project_id: "prj_test", deployment: "dpl_test", task: body.id },
        };
        body.publish_gate = own.gated;
        if (own.stale) body.publish_gate_stale = true;
        body.publish_share_url = own.share;
      } else if (fake.gate !== undefined) {
        body.publish_gate = fake.gate;
      }
      await route.fulfill({ status: res.status(), contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.route((u) => u.pathname === "/api/publish", async (route) => {
      if (route.request().method() !== "POST") { await route.continue(); return; }
      const who = fake.last;
      fake.posts.push({ who, body: route.request().postData() });
      fake.arrived?.();
      if (fake.hold) await fake.hold;
      const { status, body } = fake.reply;
      if (status === 200) {
        const gated = fake.gate === true;
        fake.tasks[who] = { url: SITE, gated, stale: false, share: gated ? SHARE : SITE };
      }
      await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    });
  }
  return { ...server, context, page, requests, outside, previewHits, logs, fake, A, B };
}

/** Відкрити канвас і дочекатись смуги з кнопкою публікації. */
async function openCanvas(page, url) {
  await page.goto(`${url}/app/`);
  await waitBarReady(page, 15000);
  await page.waitForSelector('#bar [data-act="publish"]', { timeout: 15000 });
}

const pubLabel = (page) => text(page, "#bar .lbl-pub");

/** Відкрити дропдаун публікації (якщо він ще закритий) і дочекатись його рядків. */
async function openPubDd(page) {
  if (!(await page.locator("#bar .dd--right").count())) await page.click('#bar [data-dd="pub"]');
  await page.waitForSelector('#bar .dd--right [data-act="togglepub"]');
}

/** Класи застережень у відкритому дропдауні публікації — те, що бачить людина. */
const ddNotes = (page) => page.$$eval("#bar .dd--right .dd-note", (els) => els.map((e) => e.className));

const PLASH = '.cv-notice[data-notice="publish-remote"]';

/** Знімок буфера обміну сторінки. */
const clip = (page) => page.evaluate(() => navigator.clipboard.readText());

/** Дочекатись, поки буфер стане рівно `want` (запис асинхронний). */
const waitClip = (page, want) => page.waitForFunction(
  async (w) => (await navigator.clipboard.readText()) === w, want, { timeout: 5000 });

/** Клік, що відкриває нове вікно: повертає сторінку. */
async function popupOf(context, click) {
  const [popup] = await Promise.all([context.waitForEvent("page"), click()]);
  await popup.waitForLoadState("load");
  return popup;
}

/** Жодного запиту за межі машини — і свідок, що запити були (інакше «жодного» зеленіло б на порожнечі). */
function assertStayedHome({ requests, outside }, what) {
  assert.ok(requests.length > 10, `свідок: замало запитів (${requests.length}) — ${what}`);
  assert.deepEqual(outside, [], `${what}: запити за межі машини:\n${outside.join("\n")}`);
}

/** Консоль без очікуваних відмов `fetch` на підставні 4xx/5xx і без помилок сторінок. */
function assertQuiet({ logs }, what, allowStatus = []) {
  assert.deepEqual(logs.errors, [], `${what}: помилки сторінок:\n${logs.errors.join("\n")}`);
  const noise = logs.console.filter((m) => !allowStatus.some((s) => m.includes(`status of ${s}`)));
  assert.deepEqual(noise, [], `${what}: консоль не порожня:\n${noise.join("\n")}`);
}

/** Модуль Vercel так і лишився вимкненим: його `check()` ходив би в мережу з процесу сервера. */
async function assertModuleUntouched(url, space = "p") {
  const { modules } = await (await fetch(`${url}/api/modules?space=${space}`)).json();
  const m = modules.find((x) => x.id === MODULE);
  assert.ok(m, "свідок: модуль vercel-publish є в каталозі");
  assert.equal(m.enabled, false, "тест УВІМКНУВ vercel-publish: його check() пішов би в мережу з процесу сервера");
}

/* ── a: гейтована публікація → плашка → «Відкрити» → «Скопіювати» ────────────────────────────────────── */

const W1 = "Захист Deployment Protection увімкнено — відкрийте превʼю й перевірте.";
const W2 = "<b>Прибирання</b> не вдалося: 500 <img src=x>";

test("a: публікація з паролем — плашка «Опубліковано на Vercel», «Відкрити» (#k=, noopener), «Скопіювати» = посилання, попередження текстом", async (t) => {
  const env = await boot(t);
  const { page, context, url, fake, previewHits } = env;
  fake.gate = true;
  fake.reply = { status: 200, body: { ok: true, url: SITE, verified: true, iterations: 1, frames: 2, warnings: [W1, W2] } };
  await openCanvas(page, url);
  assert.equal(await pubLabel(page), "Опублікувати", "свідок: ще нічого не опубліковано");
  await openPubDd(page);
  assert.deepEqual(await ddNotes(page), [], "пароль заданий: застереження «превʼю публічне» зайве");
  await page.keyboard.press("Escape");

  await page.click('#bar [data-act="publish"]');
  await page.waitForSelector(PLASH, { timeout: 10000 });
  assert.equal(fake.posts.length, 1, `запитів /api/publish: ${fake.posts.length}`);
  assert.deepEqual(JSON.parse(fake.posts[0].body), {}, "тіло запиту публікації");
  assert.equal(await text(page, `${PLASH} span`), "Опубліковано на Vercel");
  assert.equal(await page.locator(".cv-ask").count(), 0, "діалог помилки на успішній публікації");
  assert.equal(await page.locator('.cv-notice[data-notice="publish-local"]').count(), 0, "плашка локальної публікації");
  await waitText(page, "#bar .lbl-pub", "Оновити");

  /* Попередження модуля — рядки під основним, ТЕКСТОМ: розмітка з відповіді не стає розміткою. */
  assert.deepEqual(await page.$$eval(`${PLASH} .cv-notice-sub`, (els) => els.map((e) => e.textContent)), [W1, W2],
    "попередження модуля не показані дослівно");
  assert.equal(await page.locator(`${PLASH} b, ${PLASH} img`).count(), 0, "попередження модуля стало розміткою");
  assert.deepEqual(await page.$$eval(`${PLASH} button`, (els) => els.map((e) => e.dataset.act)), ["open", "copy", "dismiss"]);

  /* «Відкрити»: вікно на ПОСИЛАННЯ З ПАРОЛЕМ (власник не впирається у власний гейт) і без звʼязку з канвасом. */
  const popup = await popupOf(context, () => page.click(`${PLASH} button[data-act="open"]`));
  const opened = new URL(popup.url());
  assert.equal(opened.origin, SITE, `«Відкрити» веде не туди: ${popup.url()}`);
  assert.equal(opened.hash, FRAG, `у посиланні немає пароля (#k=): ${popup.url()}`);
  assert.ok(popup.url().includes("#k="));
  assert.equal(await popup.evaluate(() => window.opener === null), true,
    "вікно превʼю має window.opener: відкрите без noopener, чужа сторінка дістала б канвас");
  assert.equal(await popup.locator("#stub").count(), 1, "свідок: вікно показало підставне превʼю");
  await popup.close();
  await page.bringToFront();

  /* «Скопіювати»: у буфері рівно посилання, яке склав сервер (`publish_share_url`) — не голу адресу. */
  await page.evaluate(() => navigator.clipboard.writeText("sentinel"));
  assert.equal(await clip(page), "sentinel", "свідок: буфер читається");
  await page.click(`${PLASH} button[data-act="copy"]`);
  await waitClip(page, SHARE);
  assert.equal(await clip(page), SHARE);
  await page.waitForSelector("#cv-toast.show", { timeout: 3000 });

  /* Дропдаун публікації: ті самі дві дії ведуть туди ж. */
  await openPubDd(page);
  assert.deepEqual(await page.$$eval("#bar .dd--right [data-act]", (els) => els.map((e) => e.dataset.act)),
    ["togglepub", "openpreview", "copylink", "modpw"],
    "дропдаун Vercel-публікації: Teams і пароль задачі — лише для ЛІГА; «Пароль превʼю» модуля (0.33.0) — є");
  assert.deepEqual(await ddNotes(page), [], "опубліковано з паролем, пароль не змінювали");
  const popup2 = await popupOf(context, () => page.click('#bar .dd--right [data-act="openpreview"]'));
  assert.equal(new URL(popup2.url()).origin, SITE);
  assert.equal(new URL(popup2.url()).hash, FRAG, `дропдаун: у посиланні немає пароля: ${popup2.url()}`);
  assert.equal(await popup2.evaluate(() => window.opener === null), true, "дропдаун: вікно без noopener");
  await popup2.close();
  await page.bringToFront();
  await page.evaluate(() => navigator.clipboard.writeText("sentinel"));
  await openPubDd(page);
  await page.click('#bar .dd--right [data-act="copylink"]');
  await waitClip(page, SHARE);

  await page.click(`${PLASH} button[data-act="dismiss"]`);
  await page.waitForSelector(PLASH, { state: "detached" });

  /* Лише навмисні вікна вийшли за межі машини; до `api.vercel.com` не дійшло нічого. */
  assert.ok(previewHits.length >= 2, `свідок: вікон превʼю відкрито ${previewHits.length}`);
  assert.deepEqual([...new Set(env.outside.map((u) => new URL(u).hostname))], [STUB_HOST],
    `назовні вийшло не лише підставне превʼю:\n${env.outside.join("\n")}`);
  assert.ok(env.requests.length > 10, "свідок: замало запитів");
  assertQuiet(env, "a");
  await assertModuleUntouched(url);
});

/* ── b: застереження в дропдауні ─────────────────────────────────────────────────────────────────────── */

test("b: без пароля — .dd-note--public; пароль змінили — .dd-note--stale; поле не прийшло — мовчимо", async (t) => {
  const env = await boot(t);
  const { page, url, fake } = env;
  const notes = async () => { await openPubDd(page); const n = await ddNotes(page); await page.keyboard.press("Escape"); return n; };
  const reopen = async () => {
    await page.reload();
    await page.waitForSelector('#bar [data-act="publish"]', { timeout: 15000 });
  };

  /* 1. Ще не публікували, пароля нема: превʼю БУДЕ публічним. */
  fake.gate = false;
  await openCanvas(page, url);
  await openPubDd(page);
  assert.deepEqual(await ddNotes(page), ["dd-note dd-note--public"], "без пароля: застереження про публічне превʼю");
  assert.match(await text(page, "#bar .dd--right .dd-note--public"), /публічне: будь-хто з посиланням його бачить/);
  assert.equal(await page.locator("#bar .dd--right .dd-note--stale").count(), 0);
  await page.keyboard.press("Escape");

  /* 2. Пароль заданий, ще не публікували: застережень нема. */
  fake.gate = true;
  await reopen();
  assert.deepEqual(await notes(), [], "пароль заданий — тривоги нема");

  /* 3. Сервер поля не дав (модуль «у теку» чи старий сервер): мовчимо, а не лякаємо. */
  fake.gate = undefined;
  await reopen();
  assert.deepEqual(await notes(), [], "поле publish_gate не прийшло — а застереження зʼявилось");

  /* 4. Опубліковано З паролем, а пароль потім змінили: перепублікувати. Превʼю з паролем — «публічне» не про нього. */
  fake.tasks.a = { url: SITE, gated: true, stale: true, share: SITE };
  await reopen();
  assert.deepEqual(await notes(), ["dd-note dd-note--stale"], "пароль змінили: підказка перепублікувати");
  await openPubDd(page);
  assert.match(await text(page, "#bar .dd--right .dd-note--stale"), /Пароль змінено — перепублікуйте/);
  await page.keyboard.press("Escape");

  /* 5. Опубліковано БЕЗ пароля, потім пароль задали: превʼю й далі публічне (там ще нема гейта) І застаріле. */
  fake.tasks.a = { url: SITE, gated: false, stale: true, share: SITE };
  await reopen();
  assert.deepEqual(await notes(), ["dd-note dd-note--public", "dd-note dd-note--stale"],
    "опубліковано без пароля, пароль задали потім: обидві підказки");

  /* 6. Опубліковано без пароля, нічого не міняли: публічне. */
  fake.tasks.a = { url: SITE, gated: false, stale: false, share: SITE };
  await reopen();
  assert.deepEqual(await notes(), ["dd-note dd-note--public"]);

  assertStayedHome(env, "b");
  assertQuiet(env, "b");
  await assertModuleUntouched(url);
});

/* ── c: помилки публікації ───────────────────────────────────────────────────────────────────────────── */

test("c: vercel-auth, module-error («видаліть вручну») і vercel-busy — діалог із людським текстом і деталями сервера, кнопка повертається", async (t) => {
  const env = await boot(t);
  const { page, url, fake } = env;
  await openCanvas(page, url);

  const AUTH = "Vercel відмовив у доступі (HTTP 403): токен без прав на цю команду";
  const MANUAL = "збірка ERROR; проєкт pv-12345678 не видалено — видаліть вручну в панелі Vercel";
  const cases = [
    { status: 409, code: "vercel-auth", error: AUTH, human: /Vercel відмовив у доступі — перевірте вхід у Vercel \(токен або vercel login\) і команду/, detail: AUTH },
    { status: 502, code: "module-error", error: MANUAL, human: /Модуль публікації відмовив — перевірте його налаштування/, detail: MANUAL },
    { status: 409, code: "vercel-busy", error: "rate limit", human: /Vercel тимчасово відмовляє/, detail: null },
  ];
  for (const c of cases) {
    fake.reply = { status: c.status, body: { ok: false, code: c.code, error: c.error } };
    await page.click('#bar [data-act="publish"]');
    await page.waitForSelector(".cv-ask", { timeout: 10000 });
    /* Етап В: перший рядок тексту — заголовок, решта (деталі сервера) — абзац; склеюємо назад, як було одним текстом. */
    const body = [await page.locator(".cv-ask-title").textContent(), ...(await page.locator(".cv-ask-text").allTextContents())].join("\n\n");
    assert.match(body, c.human, `${c.code}: людський текст — ${body}`);
    if (c.detail) {
      /* Другий абзац — текст сервера дослівно: саме він каже, що виправити (права токена, видалити проєкт вручну). */
      const [head, ...rest] = body.split("\n\n");
      assert.ok(head.length > 0 && rest.join("\n\n") === c.detail, `${c.code}: деталі сервера не показані: ${JSON.stringify(body)}`);
    } else {
      assert.ok(!body.includes(c.error), `${c.code}: текст сервера не мав потрапити в діалог: ${body}`);
    }
    await page.click('.cv-ask [data-a="ok"]');
    await page.waitForSelector(".cv-ask", { state: "detached" });
    assert.equal(await pubLabel(page), "Опублікувати", `${c.code}: кнопка лишилась «Публікую…»`);
    assert.equal(await page.locator('#bar [data-act="publish"]').isDisabled(), false, `${c.code}: кнопка лишилась вимкненою`);
    assert.equal(await page.locator(PLASH).count(), 0, `${c.code}: плашка успіху на відмові`);
  }
  assert.equal(fake.posts.length, cases.length, "по запиту на кожну відмову");
  assert.deepEqual(fake.tasks, {}, "відмова не лишила сліду публікації");

  assertStayedHome(env, "c");
  assertQuiet(env, "c", [409, 502]);
  await assertModuleUntouched(url);
});

/* ── d: гонка «опублікував — перейшов на іншу задачу» ────────────────────────────────────────────────── */

test("d: публікація довга, людина перейшла на іншу задачу — тост із назвою, плашки на новій задачі нема", async (t) => {
  const env = await boot(t);
  const { page, url, fake } = env;
  let release;
  fake.hold = new Promise((done) => { release = done; });
  const arrived = new Promise((done) => { fake.arrived = done; });
  await openCanvas(page, url);
  assert.equal(await text(page, "#bar .crumb--title .txt"), "Задача A", "свідок: публікуємо задачу a");

  await page.click('#bar [data-act="publish"]');
  await arrived;
  assert.equal(fake.posts.length, 1);
  assert.equal(fake.posts[0].who, "a");
  assert.equal(await pubLabel(page), "Публікую…", "свідок: публікація триває");

  /* Перехід на b — поки запит висить. */
  await page.click('#tabs [data-act="home"]');
  await page.click('#tasks-home .th-card[data-id="b"]');
  await page.waitForFunction(() => document.querySelector("#bar .crumb--title .txt")?.textContent.trim() === "Задача B", null, { timeout: 10000 });
  await waitText(page, "#bar .lbl-pub", "Опублікувати");
  assert.equal(fake.last, "b", "свідок: канвас уже на задачі b");

  release();
  await page.waitForSelector("#cv-toast.show", { timeout: 10000 });
  assert.equal(await text(page, "#cv-toast"), "Опубліковано на Vercel: a", "тост без назви задачі, яку публікували");
  await sleep(600);                                       // запізніла перемальовка чи плашка встигли б зʼявитись
  assert.equal(await page.locator(PLASH).count(), 0, "плашка про публікацію задачі a висить на задачі b");
  assert.equal(await page.locator(".cv-ask").count(), 0, "діалог помилки на успішній публікації");
  assert.equal(await text(page, "#bar .crumb--title .txt"), "Задача B", "публікація перекинула канвас на іншу задачу");
  assert.equal(await pubLabel(page), "Опублікувати", "задача b стала «опублікованою» чужою публікацією");
  assert.equal(fake.posts.length, 1);

  assertStayedHome(env, "d");
  assertQuiet(env, "d");
  await assertModuleUntouched(url);
});

/* ── e: простір ЛІГА без змін ────────────────────────────────────────────────────────────────────────── */

test("e: ЛІГА-простір — жодних застережень Vercel, відповідь деплою ЛІГА дає лише render() без плашок", async (t) => {
  const env = await boot(t, { legacy: true });
  const { page, url } = env;
  const reg = await spacesApi(url);
  assert.equal(reg.spaces.find((s) => s.id === "liga").capabilities.publish, "vercel-publish", "свідок: форма ЛІГА (4d-4b: явний запис, а не 'legacy')");

  await openCanvas(page, url);
  await page.click('#bar [data-dd="pub"]');
  await page.waitForSelector('#bar .dd--right [data-act="togglepub"]');
  assert.deepEqual(await page.$$eval("#bar .dd--right [data-act]", (els) => els.map((e) => e.dataset.act)),
    ["togglepub", "openpreview", "copylink", "teamsnotify", "pubpw"], "дропдаун ЛІГА: пароль превʼю й Teams на місці");
  assert.deepEqual(await ddNotes(page), ["dd-note"], "ЛІГА: рівно одне застереження (про публічне посилання), без модифікаторів");
  assert.equal(await page.locator("#bar .dd--right .dd-note--public, #bar .dd--right .dd-note--stale").count(), 0);
  await page.keyboard.press("Escape");

  /* Справжній деплой (`npx vercel`) у живому тесті не запускається НІКОЛИ: відповідаємо ЗА сервер. */
  const published = [];
  await page.route("**/api/publish", async (route) => {
    published.push(route.request().postData());
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ ok: true, dir: "/stub/publish", iterations: 1, frames: 0, url: "https://stub.invalid/liga-a" }),
    });
  });
  await page.click('#bar [data-act="publish"]');
  await page.waitForFunction(() => document.querySelector("#bar .lbl-pub")?.textContent.trim() !== "Публікую…", null, { timeout: 5000 });
  await sleep(500);                                       // `render()` і те, що за ним, встигають піти в мережу
  assert.equal(published.length, 1, `запитів /api/publish від кліку: ${published.length}`);
  assert.equal(await page.locator(PLASH).count(), 0, "ЛІГА-публікація показала плашку Vercel");
  assert.equal(await page.locator('.cv-notice[data-notice="publish-local"]').count(), 0, "ЛІГА-публікація показала плашку локальної публікації");
  assert.equal(await page.locator(".cv-ask").count(), 0, "успішна ЛІГА-відповідь дала діалог помилки");
  assert.equal(await page.locator("#cv-toast.show").count(), 0, "ЛІГА-відповідь на тій самій задачі дала тост");

  assertStayedHome(env, "e");
  assertQuiet(env, "e");
});

/* ── підсумок: ізоляція ──────────────────────────────────────────────────────────────────────────────── */

test("f: жоден сценарій не вийшов за межі машини, крім навмисних вікон превʼю на підставну адресу", () => {
  const hosts = [...new Set(OUTSIDE_ALL.map((u) => new URL(u).hostname))];
  assert.deepEqual(hosts.filter((h) => h !== STUB_HOST), [], `запити за межі машини з усіх сценаріїв:\n${OUTSIDE_ALL.join("\n")}`);
  assert.ok(!OUTSIDE_ALL.some((u) => /vercel\.com/.test(new URL(u).hostname)), "хоч раз постукали на справжній vercel.com");
});

guardRealDeai("g: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
