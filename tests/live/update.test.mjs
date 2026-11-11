/**
 * Пігулка й діалог оновлення (0.23.0) — живе проведення.
 *
 * Юніти (`tests/update-*.test.mjs`) стережуть модель і розмітку; тут те, чого вони не бачать: що файл `update.json` справді доходить
 * до смуги на КОЖНОМУ екрані, що клік веде в діалог, що діалог без шва `DEAI_UPDATE_TEST_APPLY` не дає оновити (ізольований
 * сервер на справжньому коді), що «Перевірити оновлення» з ⌘K не падає, і що сторінка не ходить нікуди, крім 127.0.0.1.
 *
 * ⛔ Тут `apply` НЕ викликається: кнопка «Оновити» лише перевіряється на `disabled` і не натискається. Єдиний тест, що застосовує
 * оновлення, — `update-apply.test.mjs`, і лише у викидному клоні.
 */
import "./_env.mjs";
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 24000;
const LOCAL = new Set(["127.0.0.1", "localhost"]);

const HTML = () => "<!doctype html><h1>Фікстура</h1>";

/** Запис `update.json` у ТИМЧАСОВИЙ `DEAI_HOME` сервера (`GET /api/update` читає файл щоразу). */
const writeState = (deaiHome, state) => writeFileSync(path.join(deaiHome, "update.json"), JSON.stringify(state));
const OK = { checked_at: 1760000000, latest: "99.0.0", state: "ok", reason: "" };

async function boot(t) {
  const { dir } = taskFixture({ html: HTML });
  const server = await startServer(dir, {
    portBase: PORT_BASE,
    spaces: [{ name: "Alpha", id: "alpha", color: "space-2", tasks: { fixture: { dir, title: "Фікстура" } } }],
  });
  t.after(() => server.child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const hosts = new Set();
  context.on("request", (r) => {
    const u = new URL(r.url());
    if (u.protocol === "http:" || u.protocol === "https:" || u.protocol === "ws:") hosts.add(u.hostname);
  });
  await context.route((u) => !LOCAL.has(u.hostname) && /^https?:$/.test(u.protocol), (route) => route.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  const open = async () => {
    await page.goto(`${server.url}/app/`);
    await page.waitForSelector("#bar .space-chip", { timeout: 15000 });
  };
  return { ...server, page, hosts, errors, open };
}

const pill = (page) => page.locator("#bar .upd-pill");
const waitPill = (page) => page.waitForSelector("#bar .upd-pill", { timeout: 15000 });
const noPillFor = async (page, ms = 1500) => {
  await page.waitForTimeout(ms);           // пігулка малюється після відповіді `GET /api/update`: даємо їй час зʼявитись, якщо вона є
  return pill(page).count();
};

test("пігулка й діалог оновлення: без файла — тиша; зі станом ok — пігулка на всіх екранах; діалог без шва не дає оновити; ⌘K", async (t) => {
  const s = await boot(t);
  const { page, deaiHome, url } = s;

  await t.test("без update.json пігулки нема", async () => {
    await s.open();
    assert.equal(await noPillFor(page), 0, "пігулка є до першої перевірки");
    assert.equal(await page.locator('#bar [data-act="feedback"]').count(), 1, "перевірка недійсна: смуга не малюється");
  });

  await t.test("стан ok + перезавантаження: пігулка «Оновлення 99.0.0» на екрані задачі, «Задачах» і «Підключеннях»", async () => {
    writeState(deaiHome, OK);
    const api = await (await fetch(`${url}/api/update`)).json();
    assert.equal(api.latest, "99.0.0");
    assert.equal(api.available, true, "перевірка недійсна: 99.0.0 не новіший за поточну");
    await s.open();
    await waitPill(page);
    assert.match(await pill(page).textContent(), /Оновлення 99\.0\.0/, "екран задачі");

    await page.click('#bar [data-act="home"]');
    await page.waitForSelector("#tasks-home .th-card", { timeout: 15000 });
    assert.equal(await pill(page).count(), 1, "екран «Задачі»");
    assert.match(await pill(page).textContent(), /99\.0\.0/);

    await s.open();
    await waitPill(page);
    await page.click('#bar [data-dd="space"]');
    await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]', { timeout: 15000 });
    await page.click('.dd--spaces [data-act="conn"]');
    await page.waitForSelector('.cn-card[data-id="static-publish"]', { timeout: 15000 });
    assert.equal(await pill(page).count(), 1, "екран «Підключення»");
    assert.match(await pill(page).textContent(), /99\.0\.0/);
  });

  await t.test("клік → діалог: версії, видима причина, «Оновити» вимкнена й не натискається", async () => {
    await s.open();
    await waitPill(page);
    await pill(page).click();
    const form = page.locator(".cv-ask-scrim form.up");
    await form.waitFor({ timeout: 15000 });
    const cur = (await (await fetch(`${url}/api/update`)).json()).current;
    assert.match(await form.locator(".up-ver").textContent(), new RegExp(`${cur.replace(/\./g, "\\.")}.*99\\.0\\.0`));
    /* Сервер ізольований і крутиться на справжньому коді, а не в викидному клоні: «Оновити» не доступна. Код причини залежить від
       чекаута (`worktree` у робочому дереві, `dirty`/`diverged`/… у головному) — тут лише, що вона ВИДИМА й непорожня. */
    const st = await (await fetch(`${url}/api/update`)).json();
    assert.ok(st.blocked, `перевірка недійсна: у цього чекаута оновлення не заблоковане (${st.blocked})`);
    assert.equal(await form.locator('button[data-a="ok"]').isDisabled(), true, "«Оновити» активна без шва");
    const why = (await form.locator(".up-why").textContent()).trim();
    assert.ok(why.length > 3, `причина не показана: «${why}»`);
    assert.equal(await form.locator('button[data-a="ok"]').getAttribute("aria-describedby"), "up-why");
    /* Блок «Що нового» доїздить (без мережі: причина «недоступно», а не вічне «Завантажую»). */
    await page.waitForFunction(() => !document.querySelector('[data-up-notes] [role="status"]'), null, { timeout: 15000 });
    assert.ok((await form.locator("[data-up-notes]").textContent()).trim().length > 0);
    await form.locator('button[data-a="cancel"]').click();
    await page.locator(".cv-ask-scrim").waitFor({ state: "detached" });
    /* Жоден `apply` не ішов: стан не змінився. */
    assert.equal((await (await fetch(`${url}/api/update`)).json()).current, cur);
  });

  await t.test("state offline у файлі — пігулки нема", async () => {
    writeState(deaiHome, { ...OK, state: "offline", reason: "unreachable" });
    await s.open();
    assert.equal(await noPillFor(page), 0, "пігулка при offline");
  });

  await t.test("⌘K → «Перевірити оновлення»: тост без помилки (перевірка вимкнена оточенням)", async () => {
    await s.open();
    await page.keyboard.press("Control+k");
    await page.locator("#palq").waitFor({ state: "visible" });
    await page.fill("#palq", "Перевірити оновлення");
    await page.waitForFunction(() => document.querySelectorAll(".pal-it").length === 1, null, { timeout: 5000 });
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => {
      const el = document.getElementById("cv-toast");
      return Boolean(el) && el.classList.contains("show") && /Не вдалося перевірити|остання версія|Знайдено оновлення/.test(el.textContent ?? "");
    }, null, { timeout: 15000 });
    const st = await (await fetch(`${url}/api/update`)).json();
    assert.equal(st.state, "disabled", "DEAI_NO_UPDATE_CHECK мусить дати state=disabled, а не похід у мережу");
  });

  assert.deepEqual(s.errors, [], "помилки сторінки");
  assert.deepEqual([...s.hosts].filter((h) => !LOCAL.has(h)), [], "сторінка ходила не лише на 127.0.0.1");
});
