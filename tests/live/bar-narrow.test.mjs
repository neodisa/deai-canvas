/**
 * Смуга на сторінках оверлею (Задачі, Підключення, майстер нового простору) у вузькому вікні — живий охоронець пріоритетів стиснення.
 *
 * Стара вада (знайдена в ревʼю 0.6.0): на 375px кнопка-логотип стискалась до ~2px, іконка крошки до 0, а підпис крошки вилазив за її межі й
 * малювався поверх «Назад». Вимоги, які тут стережуться на 320, 375 і 520px:
 *   (1) логотип тримає повну ціль натискання (≥ 28px);
 *   (2) підпис крошки ВИДИМИЙ: не менше 20px власне видимого тексту, і він не вилазить за крошку (інакше малюється поверх сусідів);
 *   (3) декоративна іконка крошки поступається першою: поки вона ще не нуль, підпис не обрізано;
 *   (4) смуга не переповнюється по горизонталі (`scrollWidth ≤ clientWidth`).
 *
 * Мапа «перевірка → запобіжник» (знято мутаційно; `.space-h` — лише на 320px):
 *   (1) `.logo-btn{flex:none}` у `styles.css`;
 *   (2) `.bar--home` (зона 1 бере всю смугу) + `overflow:hidden` і трикрапка на `.crumb--page`/`.crumb--page .txt`;
 *   (3) `.crumb--page .ico{flex:0 100 auto}`;
 *   (4) `.bar--home .zone-1>.space-h{flex:0 1 auto}` (фішка простору стискається, а не штовхає смугу за край на 320–375).
 */
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 25000;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Усе потрібне — одним викликом у сторінці: геометрія логотипа, іконки й підпису крошки та переповнення смуги. */
const measure = (page) => page.evaluate(() => {
  const bar = document.querySelector("#bar .bar");
  const crumb = bar.querySelector(".crumb");
  const lab = crumb.querySelector(".txt");
  const ico = crumb.querySelector(".ico, svg");
  const b = bar.getBoundingClientRect(), c = crumb.getBoundingClientRect(), l = lab.getBoundingClientRect();
  return {
    logo: bar.querySelector(".logo-btn").getBoundingClientRect().width,
    icon: ico.getBoundingClientRect().width,
    labCw: lab.clientWidth, labSw: lab.scrollWidth,
    visible: Math.min(l.right, c.right, b.right) - l.left,
    spill: l.right - c.right,
    overflow: bar.scrollWidth - bar.clientWidth,
    text: lab.textContent.trim(),
  };
});

const goHome = async (page) => {
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home", { state: "visible" });
};
const openSpaceDd = async (page) => {
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]');
};

for (const width of [320, 375, 520]) {
  test(`смуга сторінок оверлею на ${width}px: логотип цілий, підпис видно, іконка поступається першою, без переповнення`, async (t) => {
    const X = taskFixture({ html: () => "<!doctype html><html><body><h1>m</h1></body></html>" });
    const spaces = [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }];
    const server = await startServer(null, { portBase: PORT_BASE, spaces });
    t.after(() => stop(server.child));
    const context = await browser.newContext({ viewport: { width, height: 800 } });
    t.after(() => context.close());
    const page = await context.newPage();
    await page.goto(`${server.url}/app/`);
    await page.waitForSelector("#bar .space-chip", { timeout: 15000 });

    const seen = {};
    await goHome(page);
    seen.tasks = await measure(page);
    await openSpaceDd(page);
    await page.click('#bar [data-act="conn"]');
    await page.waitForSelector(".cn-card", { timeout: 15000 });
    seen.conn = await measure(page);
    await openSpaceDd(page);
    await page.click('.dd--spaces [data-act="spacenew"]');
    await page.waitForSelector("#tasks-home .wz", { timeout: 15000 });
    seen.wiz = await measure(page);

    for (const [name, m] of Object.entries(seen)) {
      const why = `${name}@${width}: ${JSON.stringify(m)}`;
      assert.ok(m.logo >= 28, `(1) логотип стиснуто: ${why}`);
      assert.ok(m.visible >= 20, `(2) підпис крошки не видно: ${why}`);
      assert.ok(m.spill <= 1, `(2) підпис вилазить за крошку: ${why}`);
      if (m.icon > 0.5) assert.ok(m.labSw - m.labCw <= 1, `(3) іконка жива, а підпис уже обрізано: ${why}`);
      assert.ok(m.overflow <= 0, `(4) смуга переповнена: ${why}`);
    }
  });
}
