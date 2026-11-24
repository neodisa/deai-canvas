/**
 * Простори (Deai 1.0, етап 1, Task 8) — живі СЦЕНАРІЇ ПОВЕДІНКИ, які юніти й `spaces.test.mjs`
 * не бачать: що вкладка робить, коли простір міняється ПОЗА нею (агент, друге вікно, ручна
 * правка реєстру), що діалоги чесно тримають фокус і стан під запитом, що екран «Задачі»
 * оновлюється на поверненні до вікна й не стрибає від повторних запитів.
 *
 * Сервер справжній, «машина» ізольована (`startServer(…, {spaces})`: тимчасові `HOME` і
 * `DEAI_HOME`, реєстр пишеться заздалегідь), Chromium справжній. Сценарії перенесено зі скриптів
 * ревʼю Task 7 (`rev-t7{b,c,d,e,g,h}`): там вони лише друкували числа, тут — стверджують.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   T1 heal на старті     — ДВА незалежні запобіжники (`app.js`): `resetSpaceState` у `showNoTask` і
 *        `if (tuneRev === undefined) await loadTune()` у `render()`. Кожен окремо страхує другий (прибрати
 *        один — тест зелений, бо другий читає пакет), обидва разом — червоніє («рівно 2 GET» стає 1).
 *   T2 агент перемкнув    — `spaceChanged` у `render()`: скидання пер-просторового стану, пакет Y не береться з X.
 *   T3 повтор після збою  — `if (tuneRev === undefined) await loadTune()` у `render()` (T10 — теж).
 *   T4 space-2/space-3    — `defaultSpacePath(…, taken)`: вільна тека для кириличної назви.
 *   T5 зареєстрована тека — `peekRegistered` (слово сервера `registered` + запасне порівняння).
 *   T6 зайнята форма      — `setBusy` у `wizard.js` (крок 1 майстра: `aria-busy`, вимкнені «Скасувати» і «Далі»); T6b — `aria-invalid` + стиль.
 *   T6c стеля часу        — `formApi`/`FORM_POST_TIMEOUT_MS`: завислий запит не тримає канвас під підкладкою.
 *   T6d зайнятий діалог   — ДВА запобіжники «під запитом»: `if (e.key === 'Escape' && busy)` у `onKey` (`ask.js`) — Esc не
 *        закриває діалог «Назва й колір…», що чекає відповіді (без нього форма зникає, а простір «перейменовується» за
 *        закритим вікном); раннє повернення за `.cv-ask-scrim` в `openPalette` (`app.js`) — ⌘K поверх зайнятої форми не
 *        відкриває палітру (дія палітри йшла б просто під запитом, що летить). Живі свідки лишились тут після того, як
 *        діалог «Новий простір» став сторінкою майстра (там `aria-busy` перевіряє T6 і `wizard.test.mjs`, W3/W15, але вже
 *        без підкладки діалогу). Обидві мутації червонять лише T6d.
 *   T7 фокус              — `focusBackTarget` у `done` (`ask.js`; прибрати виклик — червоніє, «завжди вертати» —
 *        теж, через рамку макета) для діалогу «Назва й колір…» (Esc і «Скасувати» — окремі кроки (i-b1)/(i-b2), фокус
 *        на фішці ОДРАЗУ, без очікування); для майстра — `wizBack` (`app.js`: «Скасувати» → фішка; лише тут фокус
 *        ставиться після виходу зі сторінки, тож лише тут `chipFocused` чекає до 5 с).
 *        `focusChip` перед дією дублює `spaceDialogFocusBack`: окремо його не прибрати без вимірювання — сторожить
 *        юніт (`tests/spaces-wiring.test.mjs`).
 *   T7b сторінка майстра  — `refreshHomeOnReturn`: на `wiz` повернення до вікна її не перемальовує й нічого не питає.
 *   T8 повернення         — `refreshHomeOnReturn` + `shouldRefreshHome`: один запит на пару focus+visibilitychange.
 *   T8b «Спробувати ще»   — `homeForced`: фокус не перебиває примусовий повтор.
 *   T9 червона смуга      — успішний `loadHome` знімає смугу, виставлену ним самим.
 *   T10 перша задача      — агент завів задачу в порожньому просторі: екран оновився, запис тюнера з `base_rev`.
 *   T11 лічильники        — скільки `/api/*` коштує відкриття дропдауна, перемикання, вхід на екран.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import {
  VIEW, guardRealDeai, postJson, sleep, spacesApi, stop, waitText, waitBarReady, goTasks
} from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя база: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs` стереже, що
   жодна база не збігається з чужою). Тести ТЕКСТОВОГО файла йдуть послідовно, тож одна смуга. */
const PORT_BASE = 12600;

/** Сторінка з елементом, що має що крутити в тюнері (`#target` з відступом) і маркер задачі. */
const PAGE = (mark) => (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
:root{--sp-4:16px}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#wrap{margin:30px;padding:40px;background:#fff;display:flex;gap:24px}
.card{margin:0;padding:var(--sp-4);background:#eef;width:260px;height:160px;color:#123456}
</style></head><body data-mark="${mark}">
<div id="wrap" class="row"><p id="target" class="card">Картка ${mark}/${id}</p></div>
</body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* ── машини ────────────────────────────────────────────────────────────── */

/** Два простори P (задача x) і Q (задача y), поточний — перший; сторінка вже відкрита. */
async function twoSpaces(t, { open = true, extra = {} } = {}) {
  const X = taskFixture({ html: PAGE("X"), pages: ["holovna"] });
  const Y = taskFixture({ html: PAGE("Y"), pages: ["holovna"] });
  const server = await startServer(null, {
    portBase: PORT_BASE,
    spaces: [
      { name: "P", id: "p", color: "space-3", tasks: { x: { dir: X.dir, title: "X" } } },
      { name: "Q", id: "q", color: "space-4", tasks: { y: { dir: Y.dir, title: "Y" } } },
    ],
    ...extra,
  });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const page = await context.newPage();
  if (open) {
    await page.goto(`${server.url}/app/`);
    await waitBarReady(page);
  }
  return { X, Y, server, page, context, url: server.url, home: server.home };
}

/** Порожня машина: привітання. */
async function welcome(t) {
  const server = await startServer(null, { portBase: PORT_BASE, spaces: [] });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const page = await context.newPage();
  await page.goto(`${server.url}/app/`);
  await page.waitForSelector("#tasks-home .th-welcome");
  return { server, page, context, url: server.url, home: server.home };
}

/** Усі `/api/*` запити сторінки з моменту виклику: `["GET /api/spaces", …]`. */
function watchApi(page) {
  const seen = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith("/api/")) seen.push(`${r.method()} ${u.pathname}`);
  });
  return seen;
}
const count = (seen, what) => seen.filter((x) => x === what).length;

/* ── тюнер: прилади ────────────────────────────────────────────────────── */

/** `GET`-и й `POST`-и `/api/tuner` — що саме вкладка читала й писала. */
function trackTuner(page) {
  const posts = [];
  const gets = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname !== "/api/tuner") return;
    if (r.method() === "POST") posts.push(JSON.parse(r.postData() || "{}")); else gets.push(r.url());
  });
  return { posts, gets };
}

/** Рамка завантажила сторінку задачі з цим маркером і в ній підвішено інспектор. `not` — документ рамки (handle), який
 *  НЕ рахується: той самий маркер, але документ, що от-от зміниться (див. `spaceNameOnTasks`). */
const markLoaded = (page, mark, { not = null } = {}) => page.waitForFunction(([m, old]) => {
  const f = document.getElementById("frame");
  const doc = f && f.contentDocument;
  return !!(doc && doc !== old && doc.body && doc.body.dataset.mark === m && f.contentWindow.CanvasInspector);
}, [mark, not], { timeout: 15000 });

/* Фішка простору (0.25.0) живе лише на смузі екрана «Задачі»: назву простору читаємо звідти й вертаємось на вкладку задачі.
   Повертає handle документа, що стояв у рамці під «Задачами». Вихід з екрана (`leaveHome`) знімає `home-open` одразу, а
   рамку перезавантажує пізніше — `render()` присвоює `frame.src` лише ПІСЛЯ `/api/task` і `/api/tasks`. Доти в рамці
   той самий документ із тим самим маркером: `markLoaded` без `{ not }` проходить по ньому, а перезавантаження влучає в
   наступні кроки (повний прогін 0.39.0, 24.11.2026: T1 → `turnInspectorOn` → «reading 'on'»). */
async function spaceNameOnTasks(page, want) {
  await goTasks(page);
  await waitText(page, "#bar .space-name", want);
  const stale = await page.evaluateHandle(() => document.getElementById("frame").contentDocument);
  await page.click('#tabs [data-act="tab"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  return stale;
}

/* Увімкнути інспектор у тому документі рамки, який лишиться на екрані. Стан оверлея живе в ДОКУМЕНТІ макета, а рамку
   перезавантажує кожен повний `render()` (`applyMode` → `frame.src`): новий документ народжується з вимкненим оверлеєм,
   і поки його модуль `inspector.js` не виконався, `CanvasInspector` у рамці нема зовсім. Тому предикати не читають `.on`
   з `undefined`, клікаємо лише по готовому документу з вимкненим оверлеєм (кнопка — перемикач), а якщо між кліком і
   підтвердженням рамка змінила документ — клацаємо ще раз, уже в новому. Стеля — `reloads` перезавантажень поспіль:
   більше — це цикл перезавантажень, тобто поломка, яку тест мусить показати, а не перечекати. */
async function turnInspectorOn(page, { timeout = 15000, reloads = 3 } = {}) {
  const deadline = Date.now() + timeout;
  const left = (cap = Infinity) => Math.max(1, Math.min(cap, deadline - Date.now()));
  for (let i = 0; i <= reloads; i += 1) {
    const api = await page.waitForFunction(() => {
      const f = document.getElementById("frame");
      const w = f && f.contentWindow;
      const ready = !!(w && w.CanvasInspector && f.contentDocument && f.contentDocument.readyState === "complete");
      return ready && w.CanvasInspector;
    }, null, { timeout: left() });
    const on = await page.evaluate((a) => {
      const cur = document.getElementById("frame").contentWindow?.CanvasInspector;
      return cur === a ? cur.on === true : null;
    }, api);
    if (on === true) return;
    if (on === null) continue;                            // документ змінився між двома запитами — беремо новий
    await page.click('#hud [data-act="inspector"]');
    const got = await page.waitForFunction((a) => {
      const cur = document.getElementById("frame").contentWindow?.CanvasInspector;
      if (cur !== a) return "reloaded";                   // новий документ: оверлей у ньому вимкнений, клік пропав
      return cur.on === true && "on";
    }, api, { timeout: left(5000) });
    if (await got.jsonValue() === "on") return;
  }
  throw new Error(`інспектор не увімкнувся: рамка перезавантажилась ${reloads + 1} рази поспіль`);
}

/** Закріпити елемент у рамці кліком по ньому. */
async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel}`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction((s) => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return !!api.pinned && api.pinned.id === s.replace("#", "");
  }, sel, { timeout: 5000 });
}

/** Крутнути ручку тюнера (Shift+↑ у полі властивості). */
/* ↕ і ↔ в панелі властивостей — ПАРИ: одна накрутка пише дві правки (top+bottom, left+right), тож лічильники нижче
   парні (0.29.0). */
async function bump(page, prop) {
  const field = `#insp-panel [data-act="insptune"][data-prop="${prop}"]`;
  await page.locator(field).waitFor({ timeout: 5000 });
  await page.focus(field);
  await page.keyboard.press("Shift+ArrowUp");
}

/** Пакет тюнера на диску задачі (`.dc-tuner.json`) або `null`. */
function pkg(dir) {
  const f = path.join(dir, ".dc-tuner.json");
  if (!existsSync(f)) return null;
  try { return JSON.parse(readFileSync(f, "utf8")); } catch { return null; }
}

/** Дочекатись, поки пакет на диску матиме `count` правок. */
async function waitPkg(page, dir, n) {
  for (let i = 0; i < 80; i += 1) {
    const p = pkg(dir);
    if (p && p.editCount === n) return p;
    await page.waitForTimeout(50);
  }
  const p = pkg(dir);
  assert.equal(p && p.editCount, n, `пакет у ${dir} не дочекався ${n} правок: ${JSON.stringify(p)}`);
  return p;
}

/** Властивості, які пакет записав, плоским переліком. */
const props = (p) => p.elements.flatMap((e) => e.edits.map((x) => x.prop));

/* ── діалоги: прилади ──────────────────────────────────────────────────── */

/** Крок 1 майстра відправлено — дочекатись кроку 2 й закрити майстер (тестам потрібен лише простір). */
async function closeWizard(page) {
  await page.waitForSelector('#tasks-home .wz[data-step="2"]', { timeout: 15000 });
  await page.click('#tasks-home .wz [data-wz="close"]');
}

/** Відкрити «Новий простір…» з дропдауна фішки — крок 1 майстра (рядки дропдауна дочекатись: див. `spaces.test.mjs`). */
async function openNewSpace(page, rows = 1) {
  await goTasks(page);
  await page.click("#bar .space-chip");
  await page.waitForFunction((n) => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length >= n,
    rows, { timeout: 15000 });
  await page.click('.dd--spaces [data-act="spacenew"]');
  await page.waitForSelector('form[data-form="space"][data-mode="new"]');
}

/** Що показує крок 1 майстра про вказану теку. */
const hints = (page) => page.evaluate(() => ({
  found: document.getElementById("sp-found").hidden ? null : document.getElementById("sp-found").textContent,
  reg: document.getElementById("sp-registered").hidden ? null : document.getElementById("sp-registered").textContent,
  nameRO: document.getElementById("sp-name").readOnly,
  colorsDisabled: document.querySelector(".cv-colors").getAttribute("aria-disabled"),
  path: document.getElementById("sp-path").value,
  name: document.getElementById("sp-name").value,
}));

/** Ввести теку й дочекатись, поки відповість peek (дебаунс 300 мс + запит). */
async function typePath(page, p) {
  await page.fill("#sp-path", p);
  await page.waitForTimeout(900);
  return hints(page);
}

/** Що зараз у фокусі: тег, id й клас — для повідомлень і порівнянь. */
const active = (page) => page.evaluate(() => {
  const a = document.activeElement;
  if (!a) return null;
  return { tag: a.tagName, id: a.id, cls: typeof a.className === "string" ? a.className : "", th: a.dataset?.th ?? null };
});

/* ═══════════════════════════ тюнер і зміна простору ═══════════════════════════ */

test("T1 висячий current на старті: екран лікується, рівно два GET тюнера, пакет вилікуваної задачі підхоплено, запис іде з base_rev", async (t) => {
  const { X, server, page, url } = await twoSpaces(t, { open: false });
  await page.goto(`${url}/app/`);
  await markLoaded(page, "X");
  await turnInspectorOn(page);
  await pin(page, "#target");
  await bump(page, "padding-top");
  await waitPkg(page, X.dir, 2);

  /* Реєстр вказує на простір, якого нема (ручна правка, видалений простір). */
  const regFile = path.join(server.deaiHome, "spaces.json");
  const reg = JSON.parse(readFileSync(regFile, "utf8"));
  reg.current = "ghost";
  writeFileSync(regFile, JSON.stringify(reg));

  const tr = trackTuner(page);
  await page.reload();
  await markLoaded(page, "X");
  await waitBarReady(page);
  await page.waitForTimeout(500);
  /* Перший GET — до першого рендера (задачі нема), другий — після лікування, коли пер-задачний
     стан скинуто й пакет читається ЗНОВУ. Третій означав би зайве читання, нуль чи один —
     що пакет вилікуваної задачі не прочитано взагалі. */
  assert.equal(tr.gets.length, 2, `GET /api/tuner після лікування: ${tr.gets.length} (очікувалось рівно 2)`);
  const stale = await spaceNameOnTasks(page, "P");
  await markLoaded(page, "X", { not: stale });         // свіжий X після виходу з «Задач», а не той, що стояв під ними

  await turnInspectorOn(page);
  await pin(page, "#target");
  await bump(page, "padding-left");
  const p = await waitPkg(page, X.dir, 4);
  assert.ok(tr.posts.length >= 1, "правка не записалась");
  assert.ok("base_rev" in tr.posts[0], "перший запис після лікування без base_rev: затер би пакет, якого вкладка не читала");
  assert.deepEqual(props(p).sort(), ["padding-bottom", "padding-left", "padding-right", "padding-top"], "стара правка зникла з пакета: його не підхоплено з диска");
});

test("T2 агент (або інша вкладка) перемкнув ПРОСТІР, поки вкладка відкрита: render() скидає пер-просторовий стан і читає пакет нової задачі", async (t) => {
  const { X, Y, page, url } = await twoSpaces(t);
  await page.waitForSelector("#frame");
  await markLoaded(page, "X");
  await turnInspectorOn(page);
  await pin(page, "#target");
  await bump(page, "padding-top");
  await waitPkg(page, X.dir, 2);

  const tr = trackTuner(page);
  const sw = await postJson(url, "/api/space-switch", { id: "q" });
  assert.equal(sw.status, 200);
  /* Вкладка про це не знає: бачить лише наступний `render()` — його дає перемикач режиму. */
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForTimeout(600);
  await page.click('#bar [data-act="mode"][data-val="layout"]');
  await markLoaded(page, "Y");
  assert.ok(tr.gets.length >= 1, "пакет нової задачі не читався після зміни простору");

  await turnInspectorOn(page);
  await pin(page, "#target");
  await bump(page, "padding-left");
  const py = await waitPkg(page, Y.dir, 2);
  assert.ok("base_rev" in tr.posts[tr.posts.length - 1], "запис у новому просторі без base_rev");
  assert.deepEqual(props(py).sort(), ["padding-left", "padding-right"], "правка з пакета ЧУЖОЇ задачі протекла в пакет Y");
  assert.equal(pkg(X.dir).editCount, 2, "пакет задачі старого простору хтось чіпав");
  await spaceNameOnTasks(page, "Q");                          // смуга «Задач» теж показує новий простір
});

test("T3 повтор після збою читання (смуга помилки → «Спробувати ще»): пакет перечитано, запис іде з base_rev, не затирає", async (t) => {
  const { X, server, page } = await twoSpaces(t);
  await markLoaded(page, "X");
  await turnInspectorOn(page);
  await pin(page, "#target");
  await bump(page, "padding-top");
  await waitPkg(page, X.dir, 2);

  const tasksFile = path.join(server.spaces[0].path, "tasks.json");
  const good = readFileSync(tasksFile, "utf8");
  writeFileSync(tasksFile, "{broken");
  await page.reload();
  await page.waitForSelector(".errbar", { timeout: 15000 });

  writeFileSync(tasksFile, good);
  const tr = trackTuner(page);
  await page.click('.errbar [data-act="retry"]');
  await markLoaded(page, "X");
  await page.waitForSelector(".errbar", { state: "detached", timeout: 15000 });
  assert.ok(tr.gets.length >= 1, "після повтору пакет не перечитано: tuneRev лишилась невизначеною");

  await turnInspectorOn(page);
  await pin(page, "#target");
  await bump(page, "padding-left");
  const p = await waitPkg(page, X.dir, 4);
  assert.ok("base_rev" in tr.posts[0], "запис після повтору без base_rev");
  assert.deepEqual(props(p).sort(), ["padding-bottom", "padding-left", "padding-right", "padding-top"], "повтор затер пакет, що лежав на диску");
});

/* ═══════════════════════════ діалог простору: тека, зайнятість, помилки ═══════════════════════════ */

test("T4 друга й третя кирилична назва: тека вільна (space-2, space-3), крок 1 не заблоковано, простори створюються", async (t) => {
  const { page, url, home } = await welcome(t);
  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await page.waitForSelector('form[data-form="space"][data-mode="new"]');
  assert.equal(await page.inputValue("#sp-path"), "~/deai-work/personal");
  await page.click('form[data-form="space"] [data-a="ok"]');
  await closeWizard(page);
  await waitText(page, "#tasks-home h1.th-h", "Задачі · Особисте");
  await page.waitForFunction(() => !document.querySelector('form[data-form="space"]'));

  /* Друге «кириличне» ім'я: слаг порожній, `personal` уже зайнято першим простором. Раніше крок відкривався з тією
     ж текою й одразу заблокованим («у цій теці вже є простір»). */
  await openNewSpace(page);
  await page.fill("#sp-name", "Клієнт");
  await page.waitForTimeout(800);
  const h = await hints(page);
  assert.equal(h.path, "~/deai-work/space-2", "друга кирилична назва лягла на зайняту теку");
  assert.equal(h.found, null, "порожня тека названа знайденим простором");
  assert.equal(h.reg, null, "вільна тека названа вже доданою");
  assert.equal(h.nameRO, false, "поле назви заблоковане");
  assert.equal(h.colorsDisabled, null, "кружки кольору заблоковані");
  await page.click('form[data-form="space"] [data-a="ok"]');
  await closeWizard(page);
  await waitText(page, "#bar .space-name", "Клієнт");
  await page.waitForFunction(() => !document.querySelector('form[data-form="space"]'));
  const reg = await spacesApi(url);
  assert.deepEqual(reg.spaces.map((x) => x.path),
    [path.join(home, "deai-work", "personal"), path.join(home, "deai-work", "space-2")]);

  /* Третє — теж кирилицею: далі лічильник. */
  await openNewSpace(page, 2);
  await page.fill("#sp-name", "Інший");
  assert.equal(await page.inputValue("#sp-path"), "~/deai-work/space-3");
  await page.click('form[data-form="space"] [data-a="ok"]');
  await closeWizard(page);
  await waitText(page, "#bar .space-name", "Інший");
  assert.deepEqual((await spacesApi(url)).spaces.map((x) => path.basename(x.path)), ["personal", "space-2", "space-3"]);
});

test("T5 зареєстрована тека: «~», абсолютний, хвостовий слеш, //, NFD, варіант регістру — підказка «вже додано», а не «знайдено»", async (t) => {
  const { page, url, home } = await welcome(t);
  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await page.waitForSelector('form[data-form="space"][data-mode="new"]');
  await page.fill("#sp-name", "Київ");
  await page.fill("#sp-path", "~/deai-work/Київ");
  await page.click('form[data-form="space"] [data-a="ok"]');
  await closeWizard(page);
  await waitText(page, "#tasks-home h1.th-h", "Задачі · Київ");
  await page.waitForFunction(() => !document.querySelector('form[data-form="space"]'));

  await openNewSpace(page);
  const res = {};
  for (const [k, p] of [
    ["tilde", "~/deai-work/Київ"],
    ["tilde-slash", "~/deai-work/Київ/"],
    ["abs", `${home}/deai-work/Київ`],
    ["abs-slash", `${home}/deai-work/Київ/`],
    ["dblslash", `${home}/deai-work//Київ`],
    ["NFD", `${home}/deai-work/${"Київ".normalize("NFD")}`],
    ["NFD-tilde", `~/deai-work/${"Київ".normalize("NFD")}`],
    ["other", "~/deai-work/other"],
  ]) {
    const h = await typePath(page, p);
    res[k] = { reg: Boolean(h.reg), found: Boolean(h.found), nameRO: h.nameRO };
  }
  for (const k of ["tilde", "tilde-slash", "abs", "abs-slash", "dblslash", "NFD", "NFD-tilde"]) {
    assert.deepEqual(res[k], { reg: true, found: false, nameRO: false }, `${k}: зареєстрована тека показана не як «вже додано»`);
  }
  assert.deepEqual(res.other, { reg: false, found: false, nameRO: false }, "вільна тека названа доданою");

  /* Слово СЕРВЕРА (`registered` у відповіді peek): простір завів агент, вкладка про нього не знає —
     клієнтський реєстр цієї теки не бачить, а діалог мусить її впізнати. */
  const made = await postJson(url, "/api/space-new", { name: "CaseA", color: "space-1", path: path.join(home, "deai-work", "caseA") });
  assert.equal(made.status, 200, "агент не зміг завести простір");
  const exact = await typePath(page, `${home}/deai-work/caseA`);
  assert.ok(exact.reg, "тека простору, якого вкладка ще не бачила, не впізнана: слово сервера `registered` проігноровано");
  assert.equal(exact.found, null, "чужий простір названо знайденим");
  assert.equal(exact.nameRO, false);

  /* Варіант регістру: на macOS (APFS без урахування регістру) це та сама тека. Де ФС регістр розрізняє —
     це інша тека, і перевірка не про що. */
  if (existsSync(path.join(home, "deai-work", "CASEA"))) {
    const variant = await typePath(page, `${home}/deai-work/CASEa`);
    assert.ok(variant.reg, "варіант регістру зареєстрованої теки названо вільним (сервер відмовить path-registered)");
    assert.equal(variant.found, null, "варіант регістру показано як знайдений простір");
  }
});

test("T6 зайнята форма майстра: «Скасувати» і «Далі» вимкнені, Esc і клік під час запиту нічого не роблять, перехід один — на крок 2", async (t) => {
  const { page, url } = await twoSpaces(t);
  await page.route("**/api/space-new", async (route) => { await sleep(1500); await route.continue(); });
  const seen = watchApi(page);

  await openNewSpace(page, 2);
  await page.fill("#sp-name", "Client");
  seen.length = 0;
  await page.click('form[data-form="space"] [data-a="ok"]');
  await page.waitForFunction(() => document.querySelector('form[data-form="space"]')?.getAttribute("aria-busy") === "true");
  assert.equal(await page.locator('#tasks-home .wz [data-a="cancel"]').isDisabled(), true, "«Скасувати» не вимкнене під запитом");
  assert.equal(await page.locator('#tasks-home .wz [data-a="ok"]').isDisabled(), true, "«Далі» не вимкнена під запитом");
  await page.keyboard.press("Escape");
  await page.click('form[data-form="space"] [data-a="cancel"]', { force: true });
  assert.equal(await page.locator('form[data-form="space"]').count(), 1, "форму закрито під час запиту");
  await page.waitForSelector('#tasks-home .wz[data-step="2"]', { timeout: 15000 });
  await page.waitForTimeout(600);
  assert.equal(count(seen, "POST /api/space-new"), 1, `запитів на створення: ${count(seen, "POST /api/space-new")}`);
  assert.equal((await spacesApi(url)).current, "client", "перехід на створений простір не стався або стався не туди");
  assert.deepEqual((await spacesApi(url)).spaces.map((x) => x.id), ["p", "q", "client"]);
});

test("T6b помилка сервера лишається на кроці 1: рамка й aria-invalid — на ТОМУ полі, фокус там, знімається правкою; текстова помилка — про інше поле", async (t) => {
  const { page } = await twoSpaces(t);
  await openNewSpace(page, 2);
  await page.fill("#sp-name", "Dup");
  await page.fill("#sp-path", "relative/path");
  const before = await page.evaluate(() => getComputedStyle(document.getElementById("sp-path")).borderTopColor);
  await page.click('form[data-form="space"] [data-a="ok"]');
  await page.waitForFunction(() => {
    const e = document.getElementById("wz-err");
    return Boolean(e && !e.hidden && e.textContent.trim());
  });
  const st = await page.evaluate(() => ({
    path: document.getElementById("sp-path").getAttribute("aria-invalid"),
    name: document.getElementById("sp-name").getAttribute("aria-invalid"),
    focus: document.activeElement.id,
    border: getComputedStyle(document.getElementById("sp-path")).borderTopColor,
    other: getComputedStyle(document.getElementById("sp-name")).borderTopColor,
  }));
  assert.equal(st.path, "true", "поле теки не позначено aria-invalid");
  assert.equal(st.name, null, "чуже поле позначено aria-invalid");
  assert.equal(st.focus, "sp-path", "фокус не на полі з помилкою");
  assert.notEqual(st.border, before, "поле з помилкою не змінило рамку: aria-invalid без видимого вигляду");
  /* Точний колір не фіксуємо: майстер — темна сторінка, рамка помилки там — `--bad`, а не `--bad-ink` світлого діалогу.
     Важить інше: вона відрізняється і від звичайної рамки цього поля, і від рамки сусіднього. */
  assert.notEqual(st.other, st.border, "чуже поле теж червоне");

  /* Правка поля знімає відмову разом з рамкою. */
  await page.fill("#sp-path", "~/deai-work/dup");
  assert.equal(await page.getAttribute("#sp-path", "aria-invalid"), null);
  assert.equal(await page.evaluate(() => getComputedStyle(document.getElementById("sp-path")).borderTopColor), before, "рамка лишилась червоною після правки");

  /* Помилка про назву — на назві, а не на тецi (стара відмова поля теки не повертається). */
  await page.fill("#sp-name", "");
  await page.click('form[data-form="space"] [data-a="ok"]');
  await page.waitForFunction(() => { const e = document.getElementById("wz-err"); return e && !e.hidden; });
  assert.equal(await page.getAttribute("#sp-name", "aria-invalid"), "true");
  assert.equal(await page.getAttribute("#sp-path", "aria-invalid"), null);
  assert.equal(await page.evaluate(() => document.activeElement.id), "sp-name");
});

test("T6c завислий сервер не тримає канвас під підкладкою: за 20 с запит обривається, форма вільна й каже про це, повтор працює", async (t) => {
  const { page, url } = await twoSpaces(t);
  await page.route("**/api/space-new", () => { /* ніколи не відповідає: ні continue, ні fulfill */ });
  const seen = watchApi(page);
  await openNewSpace(page, 2);
  await page.fill("#sp-name", "Slow");
  await page.click('form[data-form="space"] [data-a="ok"]');
  await page.waitForFunction(() => document.querySelector('form[data-form="space"]')?.getAttribute("aria-busy") === "true");

  /* Під запитом Esc форму не закриває (сервер міг би створити простір за закритим вікном). */
  await page.keyboard.press("Escape");
  assert.equal(await page.locator('form[data-form="space"]').count(), 1, "Esc закрив зайняту форму");
  const started = Date.now();

  /* Стеля: форма знову вільна — і каже чому. */
  await page.waitForFunction(() => document.querySelector('form[data-form="space"]')?.getAttribute("aria-busy") !== "true",
    null, { timeout: 40000 });
  const waited = Date.now() - started;
  assert.ok(waited >= 15000 && waited <= 35000, `стеля спрацювала за ${waited} мс (очікувалось близько 20 с)`);
  const msg = await page.textContent("#wz-err");
  assert.match(msg, /не відповів вчасно/, `текст про завислий запит: ${msg}`);
  assert.equal(await page.evaluate(() => document.querySelector('form[data-form="space"] [data-a="ok"]').disabled), false, "«Створити» лишилась вимкненою");
  assert.equal(await page.locator("[data-form-invalid], [aria-invalid]").count(), 0, "таймаут — не вина поля: aria-invalid не ставиться");
  assert.equal((await spacesApi(url)).spaces.length, 2, "запит, якого сервер не отримав, щось створив");

  /* Повтор у ТІЙ САМІЙ формі: сервер тепер відповідає — простір створюється, майстер іде на крок 2. */
  await page.unroute("**/api/space-new");
  seen.length = 0;
  await page.click('form[data-form="space"] [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="2"]', { timeout: 15000 });
  assert.equal(count(seen, "POST /api/space-new"), 1, "повтор після таймауту пішов не одним запитом");
  assert.deepEqual((await spacesApi(url)).spaces.map((x) => x.id), ["p", "q", "slow"]);
});

test("T6d зайнятий діалог «Назва й колір…»: Esc, клік «Скасувати» і ⌘K під запитом нічого не роблять — форма на місці, палітри нема, запит один", async (t) => {
  const { page } = await twoSpaces(t);
  await page.route("**/api/space-update", async (route) => { await sleep(1500); await route.continue(); });
  const seen = watchApi(page);
  await goTasks(page);
  await page.click("#bar .space-chip");
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 2);
  await page.click('.dd--spaces [data-act="spaceedit"]');
  await page.waitForSelector('form[data-mode="edit"]');
  await page.fill("#sp-name", "P2");
  seen.length = 0;
  await page.click('form[data-mode="edit"] [data-a="ok"]');
  await page.waitForFunction(() => document.querySelector('form[data-mode="edit"]')?.getAttribute("aria-busy") === "true");

  const frames = () => page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
  await page.keyboard.press("Escape");                       // запобіжник `ask.js`: Esc не закриває зайняту форму
  await frames();
  assert.equal(await page.locator('form[data-mode="edit"]').count(), 1, "Esc закрив зайняту форму");
  await page.click('form[data-mode="edit"] [data-a="cancel"]', { force: true });
  await frames();
  assert.equal(await page.locator('form[data-mode="edit"]').count(), 1, "клік «Скасувати» закрив зайняту форму");
  await page.keyboard.press("Control+k");                    // запобіжник `openPalette`: палітра не лізе поверх діалогу
  await frames();
  assert.equal(await page.locator(".pal, #palq").count(), 0, "⌘K відкрив палітру поверх зайнятого діалогу");
  assert.equal(await page.locator('form[data-mode="edit"]').count(), 1, "форму закрито під час запиту");

  /* Відповідь прийшла: форма закрилась, простір перейменовано, запит один. */
  await page.waitForFunction(() => !document.querySelector('form[data-mode="edit"]'), null, { timeout: 15000 });
  await waitText(page, "#bar .space-name", "P2");
  assert.equal(count(seen, "POST /api/space-update"), 1, `запитів на правку: ${count(seen, "POST /api/space-update")}`);
  assert.equal(await page.locator(".pal, #palq").count(), 0, "палітра зʼявилась уже після закриття діалогу");

  /* Контроль: без діалогу той самий ⌘K палітру відкриває (інакше «палітри нема» вище збігалось би й зі зламаною клавішею). */
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.keyboard.press("Escape");
  await page.waitForSelector(".pal", { state: "detached" });
});

/* ═══════════════════════════ фокус після діалогів ═══════════════════════════ */

test("T7 фокус після діалогу: фішка («Скасувати» майстра; Esc, «Скасувати» й «Зберегти» діалогу «Назва й колір…»), кнопка «Нова задача» на екрані, рамка макета свого фокуса не віддає", async (t) => {
  const { page } = await twoSpaces(t);
  await page.waitForSelector("#frame");
  /* Діалоги вертають фокус на фішку ОДРАЗУ (`done` → `focusBackTarget`): читаємо без очікування. Лише майстер — сторінка:
     його фокус ставить `wizBack` ПІСЛЯ повернення на полотно (`leaveHome`), тож там (`settle`) чекаємо до 5 с, а не читаємо зразу. */
  const chipFocused = async (what, { settle = false } = {}) => {
    if (settle) {
      await page.waitForFunction(() => document.activeElement?.classList.contains("space-chip"), null, { timeout: 5000 }).catch(() => {});
    }
    const a = await active(page);
    assert.ok(a && a.cls.split(" ").includes("space-chip"), `${what}: фокус не на фішці простору, а на ${JSON.stringify(a)}`);
  };
  const openDd = async () => {
    await goTasks(page);
    await page.waitForSelector("#tasks-home .th-card");        // екран догрузив огляд — смуга далі не перемальовується
    await page.click("#bar .space-chip");
    await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 2);
  };

  /* (i) дропдаун → «Новий простір…» клавіатурою → крок 1 майстра → «Скасувати» → полотно задачі, фокус на фішці
     (Esc майстер не закриває — це сторінка, а не діалог). */
  await openDd();
  await page.focus('.dd--spaces [data-act="spacenew"]');
  await page.keyboard.press("Enter");
  await page.waitForSelector('form[data-form="space"]');
  await page.click('#tasks-home .wz [data-a="cancel"]');
  await page.waitForFunction(() => !document.querySelector('form[data-form="space"]'));
  await chipFocused("«Скасувати» на кроці 1 майстра", { settle: true });

  /* (i-b1) «Назва й колір…» → Esc (свідок Esc-шляху діалогу: майстер Esc не закривав, а діалог — так). */
  await openDd();
  await page.focus('.dd--spaces [data-act="spaceedit"]');
  await page.keyboard.press("Enter");
  await page.waitForSelector('form[data-mode="edit"]');
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector('form[data-mode="edit"]'));
  await chipFocused("Esc з діалогу правки");

  /* (i-b2) «Назва й колір…» → «Скасувати». */
  await openDd();
  await page.focus('.dd--spaces [data-act="spaceedit"]');
  await page.keyboard.press("Enter");
  await page.waitForSelector('form[data-mode="edit"]');
  await page.click('form[data-mode="edit"] [data-a="cancel"]');
  await page.waitForFunction(() => !document.querySelector('form[data-mode="edit"]'));
  await chipFocused("«Скасувати» в діалозі правки");

  /* (i-c) збереження: смуга перемальована (вузол фішки — новий), фокус усе одно на ній. */
  await openDd();
  await page.focus('.dd--spaces [data-act="spaceedit"]');
  await page.keyboard.press("Enter");
  await page.waitForSelector('form[data-mode="edit"]');
  await page.fill("#sp-name", "P2");
  await page.click('form[data-mode="edit"] [data-a="ok"]');
  await page.waitForFunction(() => !document.querySelector('form[data-mode="edit"]'));
  await waitText(page, "#bar .space-name", "P2");
  await chipFocused("збереження в діалозі правки");

  /* (ii) екран «Задачі»: картка «+» → «Скасувати» — фокус на картці, якою форму відкрили. */
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-new-slot form[data-form="task"]');
  await page.click('#th-new-slot form[data-form="task"] [data-a="cancel"]');
  await page.waitForFunction(() => !document.querySelector('form[data-form="task"]'));
  assert.equal((await active(page))?.th, "newtask", `після «Скасувати» у формі задачі фокус не на картці «+»: ${JSON.stringify(await active(page))}`);

  /* (iii) фокус НЕ крадеться: діалог (що лишився, — «Назва й колір…») закривається, фокус лишається там, куди людина його віддала.
     З 0.25.0 фішка простору живе лише на екрані «Задачі», а діалог відкривається тільки нею, тож рамки макета під діалогом нема
     (вона схована) — фокус віддаємо картці задачі на тому ж екрані. «Новий простір» тут уже не діалог, а сторінка майстра. */
  await openDd();
  await page.click('.dd--spaces [data-act="spaceedit"]');
  await page.waitForSelector('form[data-mode="edit"]');
  await page.evaluate(() => document.querySelector("#tasks-home .th-card").focus());
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains("th-card")), true, "свідок: фокус не перейшов на картку");
  await page.evaluate(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  await page.waitForFunction(() => !document.querySelector('form[data-mode="edit"]'));
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains("th-card")), true, "діалог украв фокус у картки задачі");
});

test("T7b майстер не перемальовується на focus вікна: привітання → майстер → focus → той самий вузол, нуль перечитувань → «Скасувати» → фокус на кнопці привітання", async (t) => {
  const { page } = await welcome(t);
  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await page.waitForSelector('form[data-form="space"]');
  await page.fill("#sp-name", "Чернетка");
  await page.evaluate(() => { window.__wz = document.querySelector("#tasks-home .wz"); });
  await page.waitForTimeout(900);                            // gap повернення до вікна (800 мс) від відкриття
  const seen = watchApi(page);
  await page.evaluate(() => { window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); });
  await page.waitForTimeout(700);
  assert.equal(await page.evaluate(() => window.__wz.isConnected), true, "майстер перемальовано поверненням до вікна (вузол відчеплено)");
  assert.equal(await page.inputValue("#sp-name"), "Чернетка", "набране зникло");
  const refetched = seen.filter((x) => /^GET \/api\/(spaces|tasks-overview|modules)$/.test(x));
  assert.deepEqual(refetched, [], `повернення до вікна на майстрі перечитало: ${refetched.join(", ")}`);
  await page.click('#tasks-home .wz [data-a="cancel"]');
  await page.waitForSelector("#tasks-home .th-welcome");
  const a = await active(page);
  assert.equal(a?.th, "spacenew", `фокус не на кнопці привітання: ${JSON.stringify(a)}`);
  assert.equal(await page.evaluate(() => document.activeElement.isConnected), true);
});

/* ═══════════════════════════ екран «Задачі»: повернення до вікна ═══════════════════════════ */

test("T8 повернення до вікна: простір, який завів агент, зʼявляється; пара focus+visibilitychange — один запит, серія — теж", async (t) => {
  const { page, url, home } = await welcome(t);
  const seen = watchApi(page);
  /* Агент заводить простір, поки екран привітання відкритий. */
  const made = await postJson(url, "/api/space-new", { name: "Agent", color: "space-1", path: path.join(home, "deai-work", "agentspace") });
  assert.equal(made.status, 200);

  seen.length = 0;
  await page.evaluate(() => { window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); });
  await waitText(page, "#tasks-home h1.th-h", "Задачі · Agent");
  await page.waitForTimeout(500);
  assert.equal(count(seen, "GET /api/spaces"), 1, `пара focus+visibilitychange: GET /api/spaces ×${count(seen, "GET /api/spaces")}`);
  assert.equal(count(seen, "GET /api/tasks-overview"), 1, `пара focus+visibilitychange: GET /api/tasks-overview ×${count(seen, "GET /api/tasks-overview")}`);
  assert.equal(await page.locator("#tasks-home .th-welcome").count(), 0, "привітання лишилось після того, як простір зʼявився");

  /* Серія focus поспіль (alt-tab кілька разів) — теж один запит: gap 800 мс. */
  await page.waitForTimeout(900);
  seen.length = 0;
  for (let i = 0; i < 3; i += 1) await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForTimeout(600);
  assert.equal(count(seen, "GET /api/tasks-overview"), 1, `серія з трьох focus: GET /api/tasks-overview ×${count(seen, "GET /api/tasks-overview")}`);

  /* Через gap — знову один (оновлення не заглухло назавжди). */
  await page.waitForTimeout(900);
  seen.length = 0;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForTimeout(600);
  assert.equal(count(seen, "GET /api/tasks-overview"), 1, "після gap повернення до вікна не оновило екран");
});

test("T8b «Спробувати ще» (`loadHome(true)`) у польоті — перечитування з фокуса його не перебиває: один запит, з refresh=1", async (t) => {
  const { page } = await twoSpaces(t);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");

  /* Збій огляду: дані вже є — зверху банер із кнопкою повтору. */
  await page.route("**/api/tasks-overview*", (r) => r.abort());
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForSelector('#tasks-home [data-th="retry"]', { timeout: 10000 });
  await page.unroute("**/api/tasks-overview*");

  /* Повтор іде повільно: поки він у польоті, людина повертається до вікна. */
  const reqs = [];
  await page.route("**/api/tasks-overview*", async (route) => {
    reqs.push(route.request().url());
    await sleep(1500);
    await route.continue();
  });
  await page.waitForTimeout(900);   // gap від попереднього оновлення
  await page.click('#tasks-home [data-th="retry"]');
  await page.waitForTimeout(300);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForSelector('#tasks-home [data-th="retry"]', { state: "detached", timeout: 10000 });
  await page.waitForTimeout(300);
  assert.equal(reqs.length, 1, `під час повтору пішло ще ${reqs.length - 1} запит(ів) огляду: фокус перебив примусовий повтор`);
  assert.match(reqs[0], /refresh=1/, "повтор пішов без примусу");
});

test("T9 червона смуга «простір не читається» знімається, щойно екран «Задачі» успішно перечитав огляд", async (t) => {
  const { page, server } = await twoSpaces(t);
  const tasksFile = path.join(server.spaces[0].path, "tasks.json");
  const good = readFileSync(tasksFile, "utf8");
  writeFileSync(tasksFile, "{broken");
  await page.reload();
  await page.waitForSelector(".errbar", { timeout: 15000 });

  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home", { state: "visible" });
  await page.waitForTimeout(800);
  assert.equal(await page.locator(".errbar").count(), 1, "свідок: смуга помилки зникла ще до виправлення файла");

  writeFileSync(tasksFile, good);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForSelector("#tasks-home .th-card", { timeout: 10000 });
  await page.waitForFunction(() => !document.querySelector(".errbar"), null, { timeout: 5000 })
    .catch(() => { throw new Error("червона смуга лишилась після успішного перечитування екрана «Задачі»"); });
});

/* ═══════════════════════════ порожній простір, лічильники запитів ═══════════════════════════ */

test("T10 агент завів першу задачу в порожньому поточному просторі: екран оновився на фокусі, картка відкривається, запис тюнера з base_rev", async (t) => {
  const server = await startServer(null, { portBase: PORT_BASE, spaces: [{ name: "P", id: "p", color: "space-3", tasks: {} }] });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const page = await context.newPage();
  const tr = trackTuner(page);
  await page.goto(`${server.url}/app/`);
  await page.waitForSelector("#tasks-home .th-empty--space");
  assert.equal(await page.locator("#tasks-home .th-card[data-id]").count(), 0, "свідок: у порожньому просторі вже є картки задач (картка «+» — не задача)");

  const made = await postJson(server.url, "/api/task-new", { id: "t1", title: "T1", space: "p" });
  assert.equal(made.status, 200, `агент не зміг завести задачу: ${await made.text()}`);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForSelector('#tasks-home .th-card[data-id="t1"]', { timeout: 10000 });

  await page.click('#tasks-home .th-card[data-id="t1"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"));
  await waitText(page, "#bar .crumb--title .txt", "T1");
  await turnInspectorOn(page);
  const box = await page.frameLocator("#frame").locator("h1").boundingBox();
  assert.ok(box, "стартовий макет задачі без заголовка: нема що закріпити");
  await page.mouse.click(box.x + 5, box.y + 5);
  await page.waitForFunction(() => Boolean(document.getElementById("frame").contentWindow.CanvasInspector.pinned), null, { timeout: 5000 });
  const field = '#insp-panel [data-act="insptune"]';
  await page.locator(field).first().waitFor({ timeout: 5000 });
  await page.locator(field).first().focus();
  await page.keyboard.press("Shift+ArrowUp");
  for (let i = 0; i < 80 && !tr.posts.length; i += 1) await page.waitForTimeout(50);
  assert.ok(tr.posts.length >= 1, "правка тюнера не записалась");
  assert.ok("base_rev" in tr.posts[0], "перший запис у щойно відкритій задачі без base_rev");
});

test("T11 лічильники запитів: дропдаун, перемикання простору, вхід на екран — без зайвих перечитувань реєстру", async (t) => {
  const { page } = await twoSpaces(t);
  await page.waitForTimeout(1500);
  const seen = watchApi(page);
  const spacesN = () => count(seen, "GET /api/spaces");

  /* Фішка простору (0.25.0) — лише на екрані «Задачі»: вхід на екран (його запити міряє третій крок) — окремо від дропдауна. */
  await goTasks(page);
  await page.waitForSelector("#tasks-home .th-card");
  await page.waitForTimeout(800);
  seen.length = 0;
  await page.click("#bar .space-chip");
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 2);
  await page.waitForTimeout(300);
  assert.equal(spacesN(), 1, `відкриття дропдауна: GET /api/spaces ×${spacesN()}`);

  seen.length = 0;
  await page.click('.dd--spaces .dd-item[data-val="q"]');
  await waitText(page, "#bar .space-name", "Q");
  await page.waitForTimeout(1200);
  assert.equal(count(seen, "POST /api/space-switch"), 1, "перемикання — не один space-switch");
  assert.equal(spacesN(), 1, `одне перемикання простору — ${spacesN()}× GET /api/spaces (було 5)`);
  assert.equal(count(seen, "GET /api/task"), 1, `перемикання: GET /api/task ×${count(seen, "GET /api/task")}`);

  seen.length = 0;
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.waitForTimeout(800);
  assert.equal(spacesN(), 1, `вхід на екран: GET /api/spaces ×${spacesN()}`);
  assert.equal(count(seen, "GET /api/tasks-overview"), 1, `вхід на екран: GET /api/tasks-overview ×${count(seen, "GET /api/tasks-overview")}`);

  /* Перемикання, коли екран «Задачі» відкритий: він лишається екраном і не питає зайвого. */
  await goTasks(page);
  await page.click("#bar .space-chip");
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 2);
  seen.length = 0;
  await page.click('.dd--spaces .dd-item[data-val="p"]');
  await waitText(page, "#bar .space-name", "P");
  await page.waitForTimeout(1200);
  assert.equal(spacesN(), 1, `перемикання на екрані «Задачі»: GET /api/spaces ×${spacesN()}`);
  assert.equal(count(seen, "GET /api/tasks-overview"), 1, `перемикання на екрані: GET /api/tasks-overview ×${count(seen, "GET /api/tasks-overview")}`);
});

test("T11b привітання не опитує нічого назовні, а створення з привітання через майстер — один простір і один перехід", async (t) => {
  const { page } = await welcome(t);
  const seen = watchApi(page);
  await page.waitForTimeout(3000);
  const polled = [...new Set(seen)].filter((x) => !/\/api\/(spaces|tasks-overview|claude-status|shoot-progress)$/.test(x.split(" ")[1]));
  assert.deepEqual(polled, [], `привітання щось опитує: ${polled.join(", ")}`);

  await page.click('#tasks-home .th-welcome [data-th="spacenew"]');
  await page.waitForSelector('form[data-form="space"]');
  await page.waitForTimeout(600);
  seen.length = 0;
  await page.click('form[data-form="space"] [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="2"]', { timeout: 15000 });
  await page.waitForTimeout(1200);
  /* Стелі перевиміряно під майстер (стабільно 3 прогони поспіль). Знімок — ДО «Закрити майстер»: створення міряється саме
     по собі, а читання, що їх робить сам вихід, — окремо нижче. Створення: `GET /api/spaces` — не більше двох
     (`resetSpaceState` у `afterSpaceChange` і `loadSpaces({heal})` у `showNoTask` — нова порожня задача → `no-task`; так було
     й під діалогом); `GET /api/tasks-overview` — НУЛЬ: сторінка майстра списку задач не просить (під діалогом їх було до
     двох); `GET /api/modules` — один, крок 2. Стеля, а не вимога: зростання вище — це вже зайве перечитування. */
  const SPACES = "GET /api/spaces";
  const OVERVIEW = "GET /api/tasks-overview";
  const MODULES = "GET /api/modules";
  const made = { [SPACES]: count(seen, SPACES), [OVERVIEW]: count(seen, OVERVIEW), [MODULES]: count(seen, MODULES) };
  assert.equal(count(seen, "POST /api/space-new"), 1);
  assert.ok(made[SPACES] <= 2, `створення з привітання: ${SPACES} ×${made[SPACES]}`);
  assert.equal(made[OVERVIEW], 0, `створення з привітання: ${OVERVIEW} ×${made[OVERVIEW]}`);
  assert.equal(made[MODULES], 1, `крок 2: ${MODULES} ×${made[MODULES]}`);

  /* «Закрити майстер» читає свої: простори (`enterHome` → `loadHome`) і огляд задач — по одному, модулі не чіпає. */
  await closeWizard(page);
  await page.waitForFunction(() => document.querySelector("#tasks-home h1.th-h")?.textContent.includes("Особисте"));
  await page.waitForTimeout(1200);
  assert.equal(count(seen, "POST /api/space-new"), 1, "вихід із майстра не створює простору вдруге");
  const closing = (what) => count(seen, what) - made[what];
  assert.ok(closing(SPACES) <= 1, `«Закрити майстер»: ${SPACES} ×${closing(SPACES)}`);
  assert.ok(closing(OVERVIEW) <= 1, `«Закрити майстер»: ${OVERVIEW} ×${closing(OVERVIEW)}`);
  assert.equal(closing(MODULES), 0, `«Закрити майстер»: ${MODULES} ×${closing(MODULES)}`);
});

guardRealDeai();
