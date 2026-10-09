/**
 * Живий тест попереджень після «Опублікувати» (рішення власника 29.09.2026,
 * fb-29092026-69e9c7 + fb-29092026-210ec1).
 *
 * Превʼю спільної задачі — у ВЛАСНИКА. З чужої машини публікація йде у СВОЄ
 * превʼю, і канвас мусить сказати це вголос; домен із суфіксом (другий акаунт
 * Vercel) — теж. Відповідь сервера підмінена (`page.route`): тут стережеться
 * шлях КЛІКУ й те, що обидва попередження доходять до людини, а не деплой
 * (його логіку стережуть юніти `PreviewBelongsToOwner`).
 *
 * МУТАЦІЯ: прибрати `r.not_task_link` із масиву `warn` у `publish` (`app/app.js`)
 * — вікно без імені власника, тест червоніє.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 11990;
const VIEW = { width: 1400, height: 800 };

const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;height:900px"><h1>${id}</h1></body></html>`;

test("публікація з чужої машини каже, що це не посилання задачі", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });

  let published = 0;
  await page.route("**/api/publish", (r) => {
    published += 1;
    return r.fulfill({ json: { ok: true, url: "https://pv-11111111-abc.vercel.app",
      not_task_link: "Ольга Власниця",
      domain_warning: "Vercel видав pv-11111111-abc.vercel.app, а не pv-11111111.vercel.app" } });
  });
  await page.goto(`${url}/app/`);
  await page.click('[data-act="publish"]');

  const box = page.locator(".cv-ask");
  await box.waitFor({ timeout: 5000 });
  const text = await box.textContent();
  assert.equal(published, 1, "клік не дійшов до /api/publish");
  assert.match(text, /Ольга Власниця/, "не сказано, чиє посилання — справжнє");
  assert.match(text, /ТВОЄ превʼю/);
  assert.match(text, /pv-11111111-abc\.vercel\.app/);
  assert.match(text, /а не pv-11111111\.vercel\.app/, "попередження про домен загубилось");
});
