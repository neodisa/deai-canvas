import assert from "node:assert/strict";
import test from "node:test";
import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* Тиша Teams на канал задачі (батч 1.52). База тут — `DC_TEAMS_FAKE` (локальний
   JSON): живий канал команди з тесту не чіпаємо НІКОЛИ, і сервер це гарантує
   сам (`notify_call` відмовляє при підміненому конфігу). Справжню поведінку бази
   (замовчаний не шле, незамовчаний і незмапований — шле) доведено пробою в
   транзакції з відкатом 07.10.2026 — див. ops/supabase-policies.sql. */
const PORT_BASE = 16600;
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

test("Teams: вимкнути з підтвердженням, увімкнути без, стан пережив перезавантаження", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const fake = path.join(mkdtempSync(path.join(tmpdir(), "dc-teams-")), "mute.json");
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, env: { DC_TEAMS_FAKE: fake }, supabase: true });   // 4d-4b: сповіщення веде явний запис `supabase-teams` мігрованої ЛІГИ
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-dd="pub"]');

  const row = async () => {
    await page.click('#bar [data-dd="pub"]');
    const el = page.locator('#bar [data-act="teamsnotify"]');
    await page.waitForFunction(() => {
      const b = document.querySelector('#bar [data-act="teamsnotify"]');
      return b && !b.disabled;
    }, null, { timeout: 10000 });
    return el;
  };

  let el = await row();
  assert.equal(await el.locator(".chk--on").count(), 1, "типово — шумимо");
  assert.match(await el.innerText(), /dc\/fixture/);
  await el.click();
  await page.waitForSelector(".cv-ask");
  assert.match(await page.locator(".cv-ask").innerText(), /ВСІХ/);
  await page.click('.cv-ask [data-a="cancel"]');
  assert.ok(!existsSync(fake) || !readFileSync(fake, "utf8").includes("dc/fixture"),
    "скасування не мало нічого писати");

  el = await row();
  await el.click();
  await page.click('.cv-ask [data-a="ok"]');
  await page.waitForSelector(".cv-ask", { state: "detached" });
  await page.waitForTimeout(300);
  assert.ok(JSON.parse(readFileSync(fake, "utf8"))["dc/fixture"], "тиша не записалась");

  await page.reload();
  await page.waitForSelector('#bar [data-dd="pub"]');
  el = await row();
  assert.equal(await el.locator(".chk--on").count(), 0, "після перезавантаження — вимкнено");
  assert.match(await el.innerText(), /вимкнено для всіх/);
  await el.click();   // увімкнути — без питання
  await page.waitForTimeout(300);
  assert.equal(await page.locator(".cv-ask").count(), 0);
  assert.equal(JSON.parse(readFileSync(fake, "utf8"))["dc/fixture"], undefined);
});

test("Teams: база недосяжна — пункт вимкнений із причиною, а не «увімкнено»", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 100 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.click('#bar [data-dd="pub"]');
  await page.waitForFunction(() => /стан невідомий/.test(
    document.querySelector('#bar [data-act="teamsnotify"]')?.innerText || ""), null, { timeout: 10000 });
  const el = page.locator('#bar [data-act="teamsnotify"]');
  assert.equal(await el.isDisabled(), true);
  assert.equal(await el.locator(".chk--on").count(), 0);
});
