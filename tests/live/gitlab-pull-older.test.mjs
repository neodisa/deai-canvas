/**
 * Живий тест тоста після «Підтягнути» (fb-29092026-d64d35, рішення власника 29.09.2026).
 *
 * Коли з GitLab приїжджає МОЯ, але старша версія, сервер кладе її історією і
 * заводить форк моєї найсвіжішої роботи (`gitlab_pull`, юніти в
 * `tests/test_gitlab_sync.py`). Без тоста це виглядало б як «ітерацій стало
 * дві, а я нічого не просив» — і дизайнер не знав би, з якої продовжує.
 *
 * Відповіді сервера підмінені (`page.route`): тут перевіряється шлях КЛІКУ —
 * дропдаун GitLab → «Підтягнути» → «так» → тост, а не git (його стережуть юніти).
 *
 * МУТАЦІЯ: прибрати гілку `r.continue_from` у `glpull` (`app/app.js`) — тоста
 * немає, `waitFor` не дочекається, тест червоніє.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 11890;
const VIEW = { width: 1400, height: 800 };

const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;height:900px"><h1>${id}</h1></body></html>`;

test("pull старшої своєї версії каже, з якої ітерації продовжуємо", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });

  let pulled = 0;
  await page.route("**/api/gitlab-status*", (r) => r.fulfill({
    json: { configured: true, behind: 1, unpushed: 0, dirty: false },
  }));
  await page.route("**/api/gitlab-pull", (r) => {
    pulled += 1;
    return r.fulfill({ json: { ok: true, iteration: { id: "it2" }, fork: { id: "it3" },
                               continue_from: "it1" } });
  });
  await page.goto(`${url}/app/`);
  await page.click('[data-dd="gl"]');
  await page.click('[data-act="glpull"]');
  await page.click('.cv-ask [data-a="ok"]');

  const toast = page.locator("#cv-toast.show");
  await toast.waitFor({ timeout: 5000 });
  const text = await toast.textContent();
  /* Свідок: запит справді пішов — інакше тост міг би взятись звідкись іще. */
  assert.equal(pulled, 1, "клік не дійшов до /api/gitlab-pull");
  assert.match(text, /старша версія/);
  assert.match(text, /Іт\.2/, "не сказано, яка ітерація лягла історією");
  assert.match(text, /Іт\.1/, "не сказано, з чиєї роботи продовжуємо");
  assert.match(text, /Іт\.3/, "не сказано, де копія");
});
