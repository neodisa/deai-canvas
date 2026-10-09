import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* Пароль превʼю з дропдауна публікації (ідея 02.09.2026, батч 1.52). Сервер
   (`tests/test_serve.py` e2/e3/e5) доводить, що пароль доїжджає в КОЖНУ
   сторінку; тут — що інтерфейс не бреше: типовий/свій, «превʼю ще зі старим»
   і вимкнене «Скопіювати посилання», поки посилання з новим ключем не
   відкрило б превʼю. */
const PORT_BASE = 16400;
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

test("пароль превʼю: задати з дропдауна, чесний стан до й після публікації", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-dd="pub"]');

  const item = async () => {
    await page.click('#bar [data-dd="pub"]');
    const el = page.locator('#bar [data-act="pubpw"]');
    await el.waitFor();
    const r = { text: await el.innerText(), cls: await el.getAttribute("class"),
      link: await page.locator('#bar [data-act="copylink"]').evaluate((b) => ({
        disabled: b.disabled, text: b.innerText })) };
    await page.keyboard.press("Escape");
    return r;
  };
  const answer = async (value, a = "ok") => {
    await page.waitForSelector(".cv-ask");
    if (value !== null) await page.fill("#cv-ask-input", value);
    const text = await page.locator(".cv-ask").innerText();
    await page.click(`.cv-ask [data-a="${a}"]`);
    await page.waitForSelector(".cv-ask", { state: "detached" });
    return text;
  };

  let st = await item();
  assert.match(st.text, /Пароль превью: 1100/);
  assert.match(st.text, /спільний типовий/);

  await page.click('#bar [data-dd="pub"]');
  await page.click('#bar [data-act="pubpw"]');
  const asked = await answer("live-55");
  assert.match(asked, /не захищає/, "питання не каже, чим пароль є насправді");
  assert.match(await answer(null), /з першою публікацією/);
  st = await item();
  assert.match(st.text, /Пароль превью: live-55/);
  assert.match(st.text, /лише на цій машині/);

  // Зібрали превʼю й «опублікували» (URL пишемо руками — без деплою).
  const built = await page.evaluate(async () =>
    (await fetch("/api/publish", { method: "POST", body: JSON.stringify({ build_only: true }) })).json());
  assert.ok(built.ok);
  const metaFile = path.join(dir, "iterations.json");
  const meta = JSON.parse(readFileSync(metaFile, "utf8"));
  meta.publish_url = "https://example.invalid";
  writeFileSync(metaFile, JSON.stringify(meta));
  await page.reload();
  await page.waitForSelector('#bar [data-dd="pub"]');
  st = await item();
  assert.doesNotMatch(st.cls, /dd-item--warn/);
  assert.equal(st.link.disabled, false);

  await page.click('#bar [data-dd="pub"]');
  await page.click('#bar [data-act="pubpw"]');
  await answer("live-66");
  assert.match(await answer(null, "cancel"), /СТАРИМ/, "зміна при живому превʼю мусить сказати про старий пароль");
  st = await item();
  assert.match(st.cls, /dd-item--warn/);
  assert.match(st.text, /ще не в превью/);
  assert.equal(st.link.disabled, true, "посилання з новим ключем старе превʼю не відкриє");
  assert.match(st.link.text, /пароль змінено/);

  // Повна збірка — і стан чесно стає «актуальний».
  await page.evaluate(() => fetch("/api/publish", { method: "POST", body: JSON.stringify({ build_only: true }) }));
  await page.reload();
  await page.waitForSelector('#bar [data-dd="pub"]');
  st = await item();
  assert.doesNotMatch(st.cls, /dd-item--warn/);
  assert.equal(st.link.disabled, false);
});
