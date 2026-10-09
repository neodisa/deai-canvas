/**
 * Живі тести перемикача ширини макета (вьюпорт): справжній Chromium по справжньому
 * серверу інструмента. Юніти на `app/viewport.js` перевіряють арифметику; тут —
 * рівно те, чого чистий модуль не бачить: чи ПОБАЧИВ макет усередині iframe нову
 * ширину, і чи не поламала сцена сусідні режими.
 *
 * Мапа «перевірка → запобіжник», знята мутаційно (прибери охорону — подивись, чи
 * червоніє). Без неї «зелено» не означає нічого:
 *
 *   A (медіа-запит усередині)  — сам факт, що ширина кладеться на рамку, а не на
 *                                щось поруч. Мутація «прибрати `body.vp-fixed
 *                                .cv-frame{width:var(--cv-vpw)}`» → рамка лишається
 *                                на всю сцену, `innerWidth` не міняється, червоно.
 *                                Це і є сенс фічі: макет мусить перекластись, а не
 *                                просто візуально стиснутись.
 *   B (перемикання НЕ           — відсутність `render()` у `setViewport`. `applyMode`
 *      перезавантажує макет)      на кожному рендері присвоює `frame.src`, а
 *                                присвоєння iframe навіть того самого рядка
 *                                перезавантажує документ. Мутація «дописати
 *                                `render()` у `setViewport`» → маркер у
 *                                `contentWindow` зникає, червоно. Ціна регресії
 *                                висока й невидима: прокрутка, відкриті меню й
 *                                набраний текст гинуть рівно тоді, коли дизайнер
 *                                хотів подивитись на ТОЙ САМИЙ екран іншим
 *                                пристроєм.
 *   C (сцена не накриває        — `stage.hidden = true` в `applyMode`. Мутація
 *      «Огляд»)                   «вернути `frame.hidden`, як було до сцени» → у
 *                                режимі «Огляд» сцена лишається `display:block` і
 *                                накриває полотно своєю підкладкою: у центрі
 *                                `elementFromPoint` дає сцену, а не кадр. Червоно.
 *                                ⚠️ Спершу тут стояв інший запобіжник —
 *                                `.cv-stage[hidden]{display:none}` у CSS, — і під
 *                                ВЛАСНОЮ мутацією ця перевірка лишалась зеленою:
 *                                на `.cv-stage` немає жодного `display`, тож
 *                                конфлікту з `hidden` не існує і страхування нічого
 *                                не страхувало. Мертве правило прибране, у CSS
 *                                лишився запис, ЧОМУ там не сміє з'явитись
 *                                `display` без такого рядка. Урок дорожчий за саму
 *                                перевірку: охоронець, який не може впасти,
 *                                виглядає точно як робочий.
 *   D (широка рамка лишається   — `margin:0 auto` замість flex-центрування.
 *      доступною прокруткою)      Мутація «`.cv-stage{display:flex;justify-content:
 *                                center}` + прибрати margin» → ліва частина макета
 *                                за нульовим `scrollLeft` недосяжна, червоно.
 *   E (вибір переживає          — `applyViewport()` до першого `render()` плюс
 *      перезавантаження)          персист у localStorage. Мутація «прибрати виклик»
 *                                → після reload рамка на всю ширину, червоно.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 9090;
const VIEW = { width: 1400, height: 900 };

/* Сторінка з ОДНИМ медіа-запитом і видимим наслідком. Порог 500 узятий так, щоб
   лежати між пресетами: планшет (768) його не вмикає, мобайл (375) вмикає —
   тобто перевірка бачить різницю пресетів, а не лише «ширина змінилась». */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  body{margin:0;font:16px system-ui}
  #box{height:200px;background:#0a0}
  @media (max-width:500px){ #box{background:#a00} }
</style></head><body><h1>${id}</h1><div id="box"></div>
<div style="height:1200px"></div></body></html>`;

/* Смуга (Task 3): старий `#vp-w` — тепер `input.vpw` (той самий елемент несе
   ще й `data-act="vpw"`), а сегменти пресетів — не `[data-vp="…"]`, а
   `[data-act="vp"][data-val="…"]`; підсвічений сегмент читається не класом
   `.on` (його більше нема в розмітці), а `aria-pressed="true"`. */
const vpInput = (page) => page.locator("input.vpw");
const vpBtn = (page, id) => page.locator(`[data-act="vp"][data-val="${id}"]`);

/** Робочий вид ітерації з відкритою сторінкою і завантаженим макетом. */
async function iteration(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await vpInput(page).waitFor();
  // чекаємо саме макет усередині: `#frame` існує від першого рендера, а нам
  // потрібен його документ, інакше `contentWindow.innerWidth` міряє about:blank
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return f && f.contentDocument && f.contentDocument.getElementById("box");
  });
  return page;
}

/** Ширина, яку бачить САМ макет, і колір, який з неї вийшов. */
const inner = (page) => page.evaluate(() => {
  const cw = document.getElementById("frame").contentWindow;
  return {
    width: cw.innerWidth,
    boxColor: cw.getComputedStyle(cw.document.getElementById("box")).backgroundColor,
  };
});

test("перемикач ширини макета", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());

  await t.test("A. пресет доїжджає до медіа-запиту всередині макета", async () => {
    const page = await iteration(browser, url);

    const desktop = await inner(page);
    /* 246, не 220: панель шарів (Task 4 Плану B) стала ширшою — прототип
       (`docs/proto/shell.html`) задає `.panel{width:246px}`, і той самий
       токен `--panel-w` (app/styles.css) тепер зсуває сцену. */
    assert.equal(desktop.width, 1154, "десктоп — вільна ширина сцени (1400 − панель 246)");
    assert.equal(desktop.boxColor, "rgb(0, 170, 0)", "на десктопі медіа-запит не діє");

    await vpBtn(page, "tablet").click();
    const tablet = await inner(page);
    assert.equal(tablet.width, 768, "планшет — рівно 768 у самому макеті");
    assert.equal(tablet.boxColor, "rgb(0, 170, 0)",
      "768 НЕ вмикає max-width:500px — пресет реального пристрою, а не брейкпоінта");

    await vpBtn(page, "mobile").click();
    const mobile = await inner(page);
    assert.equal(mobile.width, 375, "мобайл — рівно 375");
    assert.equal(mobile.boxColor, "rgb(170, 0, 0)", "375 вмикає медіа-запит: макет перекладено");

    /* Підсвітка виводиться з ширини, тому активним мусить бути РІВНО один сегмент.
       Свій ввід не збігається з жодним пресетом — і тоді жоден не активний. */
    await vpInput(page).fill("640");
    await vpInput(page).press("Enter");
    assert.equal((await inner(page)).width, 640, "своя ширина застосовується");
    assert.equal(await page.locator('[data-act="vp"][aria-pressed="true"]').count(), 0,
      "ширина поза пресетами не смітє підсвічувати сегмент");
    await page.close();
  });

  await t.test("B. перемикання ширини НЕ перезавантажує макет", async () => {
    const page = await iteration(browser, url);
    // маркер живе в документі макета: він гине рівно тоді, коли документ новий
    await page.evaluate(() => {
      document.getElementById("frame").contentWindow.__alive = "той самий документ";
    });

    await vpBtn(page, "mobile").click();
    await vpBtn(page, "tablet").click();
    await vpInput(page).fill("500");
    await vpInput(page).press("Enter");

    const alive = await page.evaluate(() =>
      document.getElementById("frame").contentWindow.__alive || null);
    assert.equal(alive, "той самий документ",
      "три зміни ширини не сміють перезавантажити макет — інакше гинуть прокрутка й стан");
    assert.equal((await inner(page)).width, 500, "і ширина при цьому таки застосована");
    await page.close();
  });

  await t.test("C. сцена не накриває «Огляд»", async () => {
    const page = await iteration(browser, url);
    await vpBtn(page, "mobile").click();      // виходимо саме з вузької рамки
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.locator("#canvas:not([hidden])").waitFor();

    const seen = await page.evaluate(() => {
      const stage = document.getElementById("stage");
      const el = document.elementFromPoint(Math.round(innerWidth / 2), Math.round(innerHeight / 2));
      return {
        stageDisplay: getComputedStyle(stage).display,
        centerInStage: stage.contains(el),
        segments: document.querySelectorAll('[data-act="vp"]').length,
        freeWidthField: !!document.querySelector('[data-act="vpw"]'),
      };
    });
    assert.equal(seen.stageDisplay, "none", "у «Огляді» ховається САМА сцена, не лише рамка");
    assert.equal(seen.centerInStage, false, "у центрі полотна — кадр, а не сцена");
    /* ⚠️ Тут стояло `vpControl === false` з підписом «у «Огляді» ширину міняти
       нічим: там знімки, не iframe». Це був правдивий контракт T-33 і став
       НЕправдою в T-35 (01.09.2026): перемикач у «Огляді» тепер є, просто міняє
       він не ширину рамки, а ширину, якою знімаються кадри. Перевірку не
       викинуто — вона й далі стереже сцену (два твердження вище); змінилась
       лише та її частина, яку фіча свідомо переписала.
       Поля довільної ширини там немає, і це теж контракт: кожна ширина в
       «Огляді» — окремий набір знімків на диску й окремий прогін браузера, тож
       описка «7681» коштувала б 22 зайвих кадри. */
    assert.equal(seen.segments, 3, "у «Огляді» три пресети ширини кадрів");
    assert.equal(seen.freeWidthField, false, "але поля довільної ширини там немає");
    await page.close();
  });

  await t.test("D. рамка ширша за сцену лишається доступною прокруткою", async () => {
    const page = await iteration(browser, url);
    await vpInput(page).fill("2000");
    await vpInput(page).press("Enter");

    const geom = await page.evaluate(() => {
      const stage = document.getElementById("stage");
      const box = document.getElementById("frame").getBoundingClientRect();
      return { scrollW: stage.scrollWidth, clientW: stage.clientWidth,
               frameLeft: Math.round(box.left), stageLeft: Math.round(stage.getBoundingClientRect().left) };
    });
    assert.ok(geom.scrollW > geom.clientW, "ширша за сцену рамка мусить давати прокрутку");
    assert.equal(geom.frameLeft, geom.stageLeft,
      "за нульовим scrollLeft видно ЛІВИЙ край макета — flex-центрування зробило б його недосяжним");
    await page.close();
  });

  await t.test("E. вибір переживає перезавантаження", async () => {
    const page = await iteration(browser, url);
    await vpBtn(page, "mobile").click();
    await page.reload();
    await page.waitForFunction(() => {
      const f = document.getElementById("frame");
      return f && f.contentDocument && f.contentDocument.getElementById("box");
    });
    assert.equal((await inner(page)).width, 375, "після reload мобайл мусить бути вже застосований");
    assert.equal(await page.locator('[data-act="vp"][data-val="mobile"][aria-pressed="true"]').count(), 1,
      "і сегмент підсвічений");
    await page.close();
  });
});
