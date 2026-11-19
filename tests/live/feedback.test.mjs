/**
 * Діалог відгуку (0.23.0) проти ПІДРОБНОГО приймача — живе проведення.
 *
 * Приймач (`_fake-feedback.mjs`) слухає лише `127.0.0.1:0`; сервер інструмента отримує його адресу й тестовий ключ через
 * `DEAI_FEEDBACK_URL`/`DEAI_FEEDBACK_KEY` (loopback `http` дозволений лише в ізольованому прогоні). Справжнього Supabase нема.
 *
 * Що доводить: кнопка й ⌘K на всіх екранах ведуть в один діалог; валідація нічого не шле; недоступний приймач → запис у
 * `<DEAI_HOME>/feedback/outbox/` (0600), доступний → рядок і `sent/`; до приймача доходить діагностика БЕЗ назви задачі, домашнього шляху
 * й імені теки простору, і це та сама діагностика, що в «Що буде надіслано»; знята галочка → `diag: {}`; знімок їде в Storage байт у байт;
 * помилка браузера потрапляє в кільце. Сторінка ходить лише на 127.0.0.1.
 *
 * Контракт черги (так працює код, а не «обидва надійшли»): запит надсилає ЛИШЕ свій запис, хвіст черги дочищає фоновий потік, а він в
 * ізольованому прогоні не стартує (`feedback.start_background`). Тому другий відгук при доступному приймачі йде сам, а перший
 * лишається в `outbox/`.
 */
import "./_env.mjs";
import assert from "node:assert/strict";
import { mkdirSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startFakeFeedback } from "./_fake-feedback.mjs";
import { startServer, taskFixture } from "./fixture.mjs";
import { waitBarReady, goTasks } from "./_spaces-kit.mjs";

const PORT_BASE = 24200;
const LOCAL = new Set(["127.0.0.1", "localhost"]);
const TITLE = "Секретна назва Зорблакс для клієнта";
const SPACE = "acme-zeta";
const TEXT = "Тестовий відгук про кнопку, достатньо довгий";

/** Мінімальний валідний за сигнатурою `RIFF….WEBP` (сервер перевіряє лише її й розмір). */
const WEBP = Buffer.concat([Buffer.from("RIFF"), Buffer.from([0x1a, 0, 0, 0]), Buffer.from("WEBPVP8 "), Buffer.alloc(18, 7)]);

async function boot(t) {
  const fake = await startFakeFeedback();
  t.after(() => fake.close());
  const { dir, it1 } = taskFixture({ html: () => "<!doctype html><h1>Фікстура</h1>" });
  /* Кадр першої сторінки: `shots/<node>.webp` + `manifest.json` (його читає `GET /api/shots`, і кнопка «Додати знімок» дізнається про кадр). */
  mkdirSync(path.join(it1, "shots"), { recursive: true });
  writeFileSync(path.join(it1, "shots", "holovna.webp"), WEBP);
  writeFileSync(path.join(it1, "shots", "manifest.json"), JSON.stringify({ checkedAt: "2026-11-11T10:00:00Z", shots: { holovna: { w: 1280, h: 800 } } }));
  const server = await startServer(dir, {
    portBase: PORT_BASE,
    env: { DEAI_FEEDBACK_URL: fake.url, DEAI_FEEDBACK_KEY: fake.key, DEAI_NO_UPDATE_CHECK: "1" },
    spaces: [{ name: SPACE, id: SPACE, color: "space-2", tasks: { fixture: { dir, title: TITLE } } }],
  });
  t.after(() => server.child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const hosts = new Set();
  context.on("request", (r) => {
    const u = new URL(r.url());
    if (/^(https?|wss?):$/.test(u.protocol)) hosts.add(u.hostname);
  });
  await context.route((u) => !LOCAL.has(u.hostname) && /^https?:$/.test(u.protocol), (route) => route.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  const open = async () => {
    await page.goto(`${server.url}/app/`);
    await waitBarReady(page, 15000);
    await page.waitForSelector('#hud [data-act="feedback"]', { timeout: 15000 });
  };
  return { ...server, fake, page, hosts, errors, open };
}

/* Етап В: з острівця форма — поповер `.cv-ask-pop`, з ⌘K — модальна `.cv-ask-scrim`; тут важить сама форма. */
const FORM = "form[data-form=feedback]";
const waitForm = (page) => page.waitForSelector(FORM, { timeout: 15000 });
const closeForm = async (page) => {
  await page.click(`${FORM} button[data-a="cancel"]`);
  await page.waitForSelector(".cv-ask-scrim, .cv-ask-pop", { state: "detached" });
};
/** Тост ПОКАЗАНО і говорить те саме (застарілий текст схованого тоста не рахується). */
const waitToast = (page, re) => page.waitForFunction((src) => {
  const el = document.getElementById("cv-toast");
  return Boolean(el) && el.classList.contains("show") && new RegExp(src).test(el.textContent ?? "");
}, re.source, { timeout: 15000 });
/** Дочекатись ПЕРЕГЛЯДУ (JSON у «Що буде надіслано») і повернути його розібраним. */
async function previewJson(page) {
  await page.waitForFunction(() => /^\s*\{/.test(document.querySelector("[data-fb-pre]")?.textContent ?? ""), null, { timeout: 15000 });
  return JSON.parse(await page.textContent("[data-fb-pre]"));
}
const dirOf = (deaiHome, bucket) => path.join(deaiHome, "feedback", bucket);
const ls = (p) => { try { return readdirSync(p).filter((n) => !n.startsWith(".")).sort(); } catch { return []; } };

test("діалог відгуку: екрани, валідація, черга й приймач, діагностика, знімок, кільце помилок", async (t) => {
  const s = await boot(t);
  const { page, fake, deaiHome } = s;

  await t.test("кнопка «Відгук» є на екрані задачі, «Задачах», «Підключеннях», у майстрі; ⌘K → «Баг / ідея» — той самий діалог", async () => {
    await s.open();
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    assert.match(await page.textContent(`${FORM} h2`), /Відгук про Deai Canvas/);
    await closeForm(page);

    await page.click('#tabs [data-act="home"]');
    await page.waitForSelector("#tasks-home .th-card", { timeout: 15000 });
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    await closeForm(page);

    await s.open();
    await goTasks(page);
    await page.click('#bar [data-dd="space"]');
    await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]', { timeout: 15000 });
    await page.click('.dd--spaces [data-act="conn"]');
    await page.waitForSelector('.mc[data-id="static-publish"]', { timeout: 15000 });
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    await closeForm(page);

    await s.open();
    await goTasks(page);
    await page.click('#bar [data-dd="space"]');
    await page.waitForSelector('.dd--spaces [data-act="spacenew"]', { timeout: 15000 });
    await page.click('.dd--spaces [data-act="spacenew"]');
    await page.waitForSelector("#tasks-home .wz", { timeout: 15000 });
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    await closeForm(page);

    await s.open();
    await page.keyboard.press("Control+k");
    await page.locator("#palq").waitFor({ state: "visible" });
    await page.fill("#palq", "Баг / ідея");
    await page.waitForFunction(() => document.querySelectorAll(".pal-it").length === 1, null, { timeout: 5000 });
    await page.keyboard.press("Enter");
    await waitForm(page);
    await closeForm(page);
    assert.deepEqual(fake.hits(), [], "відкриття діалогу не мусить нічого слати приймачеві");
  });

  await t.test("валідація: пусто й менше 10 знаків → помилка під полем, фокус у полі, нічого не надіслано", async () => {
    await s.open();
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    for (const text of ["", "коротко"]) {
      await page.fill("#fb-text", text);
      await page.click(`${FORM} button[data-a="ok"]`);
      await page.waitForFunction(() => { const e = document.getElementById("cv-form-err"); return e && !e.hidden && e.textContent.trim().length > 3; });
      assert.match(await page.textContent("#cv-form-err"), /щонайменше 10/);
      assert.equal(await page.evaluate(() => document.activeElement?.id), "fb-text", "фокус не в полі");
    }
    assert.deepEqual(fake.hits(), [], "невалідний відгук дійшов до приймача");
    assert.deepEqual(ls(dirOf(deaiHome, "outbox")), [], "невалідний відгук ліг у чергу");
    await closeForm(page);
  });

  let queuedId = null;
  await t.test("приймач down: «Збережено локально (№…)», в outbox/ один файл 0600", async () => {
    fake.setMode("down");
    await s.open();
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    await previewJson(page);
    await page.fill("#fb-text", TEXT);
    await page.click(`${FORM} button[data-a="ok"]`);
    await waitToast(page, /Збережено локально \(№[0-9a-f]{8}\)/);
    const files = ls(dirOf(deaiHome, "outbox"));
    assert.equal(files.length, 1, `в outbox/ ${files.length} файлів: ${files}`);
    assert.match(files[0], /^[0-9a-f-]{36}\.json$/);
    queuedId = files[0].replace(/\.json$/, "");
    assert.equal(statSync(path.join(dirOf(deaiHome, "outbox"), files[0])).mode & 0o777, 0o600, "файл відгуку не 0600");
    assert.equal(fake.rows().length, 0);
    assert.deepEqual(ls(dirOf(deaiHome, "sent")), []);
  });

  await t.test("приймач up: другий відгук надійшов; діагностика без назви задачі, дому й теки простору; те саме, що в «Що буде надіслано»", async () => {
    fake.setMode("up");
    await s.open();
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    const shown = await previewJson(page);
    await page.fill("#fb-text", `${TEXT} (другий)`);
    await page.click(`${FORM} button[data-a="ok"]`);
    await waitToast(page, /Дякуємо! Відгук №[0-9a-f]{8} надіслано/);
    const rows = fake.rows();
    assert.equal(rows.length, 1, "рядків у приймача");
    const row = rows[0];
    assert.equal(row.kind, "bug");
    assert.equal(row.text, `${TEXT} (другий)`);
    assert.equal(row.shot_path, null);
    assert.ok(!("created_at" in row), "клієнт не сміє слати created_at");
    const diag = row.diag;
    assert.equal(typeof diag.version, "string");
    assert.ok(diag.space && diag.space.roles && typeof diag.space.roles === "object", "нема space.roles");
    assert.equal(diag.task.id, "fixture");
    const raw = JSON.stringify(row);
    assert.doesNotMatch(raw, new RegExp(TITLE.slice(0, 12)), "у відгуку назва задачі");
    assert.doesNotMatch(raw, new RegExp(SPACE), "у відгуку імʼя теки простору");
    for (const forbidden of [s.home, path.dirname(s.home), "/Users/", "/private/var", "dc-live"]) {
      assert.ok(!raw.includes(forbidden), `у відгуку шлях: ${forbidden}`);
    }
    assert.deepEqual(diag, shown.diag, "«Що буде надіслано» ≠ те, що надійшло");
    /* Перший (записаний при down) лишається в черзі: хвіст дочищає фоновий потік, якого в ізольованому прогоні нема. */
    assert.deepEqual(ls(dirOf(deaiHome, "outbox")), [`${queuedId}.json`]);
    assert.equal(ls(dirOf(deaiHome, "sent")).length, 1);
    assert.ok(!fake.rows().some((r) => r.id === queuedId));
  });

  await t.test("знята галочка «Додати діагностику» → diag: {}", async () => {
    await s.open();
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    await previewJson(page);
    await page.uncheck("#fb-diag");
    await page.waitForFunction(() => JSON.parse(document.querySelector("[data-fb-pre]").textContent).diag
      && Object.keys(JSON.parse(document.querySelector("[data-fb-pre]").textContent).diag).length === 0);
    await page.fill("#fb-text", `${TEXT} (без діагностики)`);
    await page.click(`${FORM} button[data-a="ok"]`);
    await waitToast(page, /Дякуємо! Відгук/);
    const last = fake.rows().at(-1);
    assert.equal(last.text, `${TEXT} (без діагностики)`);
    assert.deepEqual(last.diag, {});
  });

  await t.test("знімок: чекбокс доступний, байти в Storage збігаються, shot_path = <id>.webp; без кадру чекбокс вимкнений з причиною", async () => {
    await s.open();
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    await previewJson(page);
    assert.equal(await page.locator("#fb-shot").isDisabled(), false, "знімок поточної сторінки не знайдено");
    await page.check("#fb-shot");
    const thumb = await page.getAttribute("[data-fb-thumb]", "src");
    assert.match(thumb, /^\/shot\?it=it1&node=holovna$/);
    await page.fill("#fb-text", `${TEXT} (зі знімком)`);
    await page.click(`${FORM} button[data-a="ok"]`);
    await waitToast(page, /Дякуємо! Відгук/);
    const row = fake.rows().at(-1);
    assert.equal(row.shot_path, `${row.id}.webp`);
    const bytes = fake.shots().get(`${row.id}.webp`);
    assert.ok(bytes, "приймач не дістав знімка");
    assert.ok(bytes.equals(WEBP), "байти знімка не збігаються");

    /* На «Задачах» поточної сторінки нема → знімка нема. */
    await s.open();
    await page.click('#tabs [data-act="home"]');
    await page.waitForSelector("#tasks-home .th-card", { timeout: 15000 });
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    await previewJson(page);
    assert.equal(await page.locator("#fb-shot").isDisabled(), true, "чекбокс знімка активний без кадру");
    assert.equal(await page.locator("#fb-shot-why").isVisible(), true);
    assert.ok((await page.textContent("#fb-shot-why")).trim().length > 5, "причина не показана");
    await closeForm(page);
  });

  await t.test("помилка браузера потрапляє в кільце: errors.client[0].msg — «boom»", async () => {
    await s.open();
    await page.evaluate(() => setTimeout(() => { throw new Error("boom"); }));
    await page.waitForTimeout(300);
    await page.click('#hud [data-act="feedback"]');
    await waitForm(page);
    const shown = await previewJson(page);
    assert.match(shown.diag.errors.client[0].msg, /^(Uncaught )?(Error: )?boom$/);
    await closeForm(page);
  });

  await t.test("поповер «Баг / ідея» (етап В): над кнопкою острівця, без підкладки; чернетка переживає закриття повз; другий клік по кнопці закриває; відправка чистить; ⌘K — модалка", async () => {
    fake.setMode("up");
    await s.open();
    const btn = page.locator('#hud [data-act="feedback"]');
    await btn.click();
    await waitForm(page);
    assert.equal(await page.locator(".cv-ask-pop .cv-ask--pop " + FORM).count(), 1, "форма не в поповері");
    assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "поповер не мусить мати підкладки");
    const box = await page.locator(".cv-ask--pop").boundingBox();
    const bb = await btn.boundingBox();
    assert.ok(box.y + box.height < bb.y, `картка не над кнопкою: низ ${box.y + box.height} ≥ верх кнопки ${bb.y}`);
    assert.equal(await page.evaluate(() => document.activeElement?.id), "fb-text", "фокус не в полі тексту");
    const bg = await page.evaluate(() => getComputedStyle(document.querySelector(".cv-ask--pop")).backgroundColor);
    assert.notEqual(bg, "rgb(255, 255, 255)", "картка біла");
    await page.fill("#fb-text", "Чернетка, що не мусить зникнути");
    await page.fill("#fb-contact", "me@example.test");
    // клік у макет (рамку) — повз поповер
    await page.mouse.click(Math.round(box.x + box.width / 2), 400);
    await page.waitForSelector(".cv-ask-pop", { state: "detached" });
    await btn.click();
    await waitForm(page);
    assert.equal(await page.inputValue("#fb-text"), "Чернетка, що не мусить зникнути", "чернетка тексту загублена");
    assert.equal(await page.inputValue("#fb-contact"), "me@example.test", "чернетка контакту загублена");
    // повторний клік по кнопці закриває і не відкриває знову
    await btn.click();
    await page.waitForSelector(".cv-ask-pop", { state: "detached" });
    await page.waitForTimeout(500);
    assert.equal(await page.locator(".cv-ask-pop").count(), 0, "клік по якорю відкрив форму знову");
    // відправка чистить чернетку
    await btn.click();
    await waitForm(page);
    await previewJson(page);
    await page.click(`${FORM} button[data-a="ok"]`);
    await waitToast(page, /Дякуємо! Відгук/);
    await page.waitForSelector(".cv-ask-pop", { state: "detached" });
    await btn.click();
    await waitForm(page);
    assert.equal(await page.inputValue("#fb-text"), "", "після відправки чернетка лишилась");
    await closeForm(page);
    // ⌘K → модальна картка з підкладкою
    await page.keyboard.press("Control+k");
    await page.locator("#palq").waitFor({ state: "visible" });
    await page.fill("#palq", "Баг / ідея");
    await page.waitForFunction(() => document.querySelectorAll(".pal-it").length === 1, null, { timeout: 5000 });
    await page.keyboard.press("Enter");
    await page.waitForSelector(".cv-ask-scrim " + FORM, { timeout: 15000 });
    assert.equal(await page.locator(".cv-ask-pop").count(), 0);
    await closeForm(page);
  });

  await t.test("високий поповер у низькому вікні (1280×420): картка у вікні, «Надіслати» досяжна прокруткою, хвостик не обрізано", async () => {
    await page.setViewportSize({ width: 1280, height: 420 });
    try {
      await s.open();
      await page.click('#hud [data-act="feedback"]');
      await waitForm(page);
      const box = await page.locator(".cv-ask--pop").boundingBox();
      assert.ok(box.y >= 0 && box.y + box.height <= 420 + 1, `картка виходить за вікно: y=${box.y} h=${box.height}`);
      const submit = page.locator(`${FORM} button[data-a="ok"]`);
      await submit.scrollIntoViewIfNeeded();
      const sb = await submit.boundingBox();
      assert.ok(sb.y >= 0 && sb.y + sb.height <= 420, `«Надіслати» поза вікном: y=${sb.y}`);
      assert.equal(await submit.isVisible(), true);
      const ov = await page.evaluate(() => getComputedStyle(document.querySelector(".cv-ask--pop")).overflow);
      assert.notEqual(ov, "auto", "прокрутка на рамці картки обрізала б хвостик");
      await closeForm(page);
    } finally {
      await page.setViewportSize({ width: 1440, height: 900 });
    }
  });

  assert.deepEqual(fake.rejected(), [], "приймач відхилив запити сервера (заголовки/ключ/Prefer/x-upsert)");
  assert.deepEqual(s.errors.filter((e) => !/boom/.test(e)), [], "помилки сторінки");
  assert.deepEqual([...s.hosts].filter((h) => !LOCAL.has(h)), [], "сторінка ходила не лише на 127.0.0.1");
});
