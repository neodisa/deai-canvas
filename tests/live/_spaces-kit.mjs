/**
 * Спільне для живих тестів просторів (`spaces.test.mjs`, `spaces-flows.test.mjs`).
 *
 * Файл НЕ `*.test.mjs` навмисно: `npm run test:live` бере `tests/live/*.test.mjs`, і helper
 * під таким іменем поїхав би в прогін окремим файлом без жодного тесту (так само `fixture.mjs`).
 *
 * Що тут: зупинка сервера, кілька чекань, JSON-POST, і ОХОРОНЕЦЬ справжнього `~/.deai`.
 * Охоронець — знімок справжнього реєстру, сховища секретів (`secrets.json`) і довіри своїм модулям (`trust.json`, `trusted/`)
 * ДО будь-якого сервера (модуль імпортується першим рядком тестового файла), а порівняння — окремим останнім тестом кожного модуля
 * (`guardRealDeai`). Домівка — з ОС (`os.userInfo().homedir`), а не з `process.env.HOME`: її
 * може підмінити хто завгодно, і тоді охоронець дивився б не туди. Статичний охоронець
 * `.mjs` не сканує (ревʼю Task 5), тож цей — єдиний, що бачить живий прогін.
 */
// 4d-4b: Playwright-кеш і git-ідентичність у тимчасовому HOME — ДО будь-якого запуску браузера/git
import "./_env.mjs";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { userInfo } from "node:os";
import path from "node:path";
import test from "node:test";

export const VIEW = { width: 1440, height: 900 };

/** Зупинити сервер і дочекатись виходу: наступний тест може випасти на той самий порт. */
export async function stop(child) {
  if (child.exitCode !== null || child.signalCode) return;
  const gone = new Promise((done) => child.once("exit", done));
  child.kill();
  const timer = setTimeout(() => child.kill("SIGKILL"), 4000);
  await gone;
  clearTimeout(timer);
}

/**
 * Смуга готова (0.25.0): рядок вкладок є, а в смузі — або фішка простору (екран «Задачі»), або назва задачі (вигляд задачі:
 * фішки простору там НЕМАЄ, вона живе лише на смузі «Задач»). Нікуди не переходить; хто чекає саме фішку — спершу `goTasks`.
 */
export async function waitBarReady(page, timeout = 15000) {
  await page.waitForSelector('#tabs [data-act="home"]', { timeout });
  await page.waitForFunction(
    () => !!(document.querySelector("#bar .space-chip") || document.querySelector("#bar .crumb--title")),
    null, { timeout },
  );
}

/** Іти на екран «Задачі» (де живе фішка простору), якщо ще не там; чекає фішку. */
export async function goTasks(page, timeout = 15000) {
  await waitBarReady(page, timeout);
  if (!(await page.locator("#bar .space-chip").count())) await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#bar .space-chip", { timeout });
}

/**
 * Розділ «Модулі» (етап Е): картка в сітці — `.mc[data-id]` з бейджем `.bdg--{ok|err|off|unchecked|trust|missing}`. Вимкнений ВБУДОВАНИЙ
 * модуль у сітці не показується (він лише в каталозі), тож його «картка» — це відсутність `.mc` (`waitGone`).
 */
export const BDG = { ok: "ok", error: "err", off: "off", unchecked: "unchecked", untrusted: "trust", missing: "missing" };
export const waitBadge = (page, id, kind, timeout = 15000) => page.waitForSelector(`.mc[data-id="${id}"] .bdg--${BDG[kind]}`, { timeout });
export const waitGone = (page, id, timeout = 15000) => page.waitForSelector(`.mc[data-id="${id}"]`, { state: "detached", timeout });
/** Клас бейджа картки (`bdg bdg--ok`). */
export const badgeClass = (page, id) => page.locator(`.mc[data-id="${id}"] .bdg`).getAttribute("class");
/** Каталог «Додати модуль»: відкрити з голови сторінки (`role` не задано) чи з пунктирної картки ролі; чекає діалог. */
export async function openCatalog(page, role = "", { dom = false } = {}) {
  const sel = role ? `.mc--empty[data-role="${role}"] [data-cn="cat"]` : '.th-head [data-cn="cat"]';
  /* `dom` — клік подією, а не мишею: відкрита шухляда налаштувань лежить поверх голови сторінки й перехоплює справжній клік. */
  if (dom) await page.locator(sel).dispatchEvent("click"); else await page.click(sel);
  await page.waitForSelector('.cv-ask form[data-form="catalog"] .cat');
}
/**
 * «Підключити» вимкненого вбудованого модуля — справжнім шляхом: «Додати модуль» → рядок каталогу. Далі — наявна шухляда в режимі
 * «Підключити» (модуль без налаштувань вмикається одразу). Кнопка каже «Підключити» або «Замінити {поточний}»: питання «Замінити?»
 * після неї вже нема (спека §3), крім випадку, коли тримачі ролі змінились, поки шухляда була відкрита.
 */
export async function pickFromCatalog(page, id, opts = {}) {
  await openCatalog(page, "", opts);
  await page.click(`.cat [data-cat-pick="${id}"]`);
  await page.waitForSelector('form[data-form="catalog"]', { state: "detached" });
}
/** Клік по картці (назва): увімкнений модуль → шухляда налаштувань. */
export async function openCard(page, id) {
  /* Картка з дією в польоті (`aria-busy`) на клік не відповідає — чекаємо, поки список перечитано. */
  await page.waitForSelector(`.mc[data-id="${id}"]:not([aria-busy="true"])`, { timeout: 15000 });
  await page.click(`.mc[data-id="${id}"] .mc-name b`);
}
/** «⋯» картки → пункт меню `act` (Налаштувати, Перевірити, Вимкнути…). */
export async function menuAct(page, id, act) {
  await page.click(`.mc-more[data-id="${id}"]`);
  await page.click(`#th-menu [data-cn="${act}"][data-id="${id}"]`);
}
/** «⋯» → «Вимкнути» → питання в картці (`.mc--ask`). */
export async function menuDisable(page, id) {
  await menuAct(page, id, "disable");
  await page.waitForSelector(`.mc--ask[data-id="${id}"]`);
}
export const askYes = (page, id) => page.click(`.mc--ask[data-id="${id}"] .cfm-yes`);
export const askNo = (page, id) => page.click(`.mc--ask[data-id="${id}"] .cfm-no`);
export const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

/** Текст першого збігу, обрізаний; `null`, коли вузла нема. */
export const text = (page, sel) => page.evaluate((s) => document.querySelector(s)?.textContent.trim() ?? null, sel);

/** Дочекатись, поки текст першого збігу дорівнює `want`. */
export const waitText = (page, sel, want) => page.waitForFunction(
  ([s, w]) => document.querySelector(s)?.textContent.trim() === w, [sel, want], { timeout: 15000 });

/** `POST` JSON на сервер напряму (як це робить агент), без сторінки. */
export const postJson = (url, p, body) => fetch(`${url}${p}`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const spacesApi = async (url) => (await fetch(`${url}/api/spaces`)).json();

/* ── охоронець справжнього ~/.deai ─────────────────────────────────────── */

export const REAL_DEAI = path.join(userInfo().homedir, ".deai");
const sha = (p) => {
  try { return createHash("sha256").update(readFileSync(p)).digest("hex"); } catch { return null; }
};
/** Імена підтек `trusted/` (відсортовані, через `\n`) або `null`, коли теки нема чи її не прочитати. */
const trustedNames = (p) => {
  try { return existsSync(p) ? readdirSync(p).sort().join("\n") : null; } catch { return null; }
};
export const realDeai = () => ({
  exists: existsSync(REAL_DEAI),
  registry: sha(path.join(REAL_DEAI, "spaces.json")),
  backup: sha(path.join(REAL_DEAI, "spaces.json.bak")),
  /* Секрети модулів (етап 3b: майстер пише їх у `secrets.json`): живий тест, що доповз до справжнього сховища, не сміє
     лишити там слід — а до реєстру він міг би й не дотягнутись. */
  secrets: sha(path.join(REAL_DEAI, "secrets.json")),
  /* Довіра своїм модулям (3c): живий тест пише `trust.json` і знімки `trusted/` — лише в тимчасовий `DEAI_HOME`. Для `trusted/`
     мало «існує чи ні»: запис у УЖЕ наявну справжню теку лишив би `existsSync` рівним `true` до й після — тому вміст (імена підтек). */
  trust: sha(path.join(REAL_DEAI, "trust.json")),
  trusted: trustedNames(path.join(REAL_DEAI, "trusted")),
  /* Журнали (`logs/`, напр. `dashboard-sync.log`): лише наявність і ПЕРЕЛІК імен, ніколи вміст — це лог справжньої машини; живий тест,
     що дописав у справжній журнал дашборда, додав би файл або теку, і це буде видно. */
  logs: existsSync(path.join(REAL_DEAI, "logs")),
  logsList: trustedNames(path.join(REAL_DEAI, "logs")),
});
/** Знімок ДО будь-якого сервера: модуль імпортується до першого `startServer`. */
export const REAL_BEFORE = realDeai();

/** Останній тест модуля: справжній `~/.deai` не зʼявився і не змінився. */
export function guardRealDeai(name = "справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)") {
  test(name, () => {
    assert.deepEqual(realDeai(), REAL_BEFORE, `живий тест торкнувся справжнього ${REAL_DEAI}`);
  });
}
