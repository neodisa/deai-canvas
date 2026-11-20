/**
 * Зовнішня оболонка на ЗІБРАНОМУ `publish/` — єдине місце, де перевіряється те,
 * чого не бачить жоден юніт: гейт, статика без сервера, `fetch('manifest.json')`
 * і проводка кліків.
 *
 * Чому саме зібраний артефакт, а не `app/index.html` з підміненим маніфестом:
 * половина ризиків цієї фічі — у САМІЙ ЗБІРЦІ (чи доїхали модулі в
 * `publish/shell/`, чи лежить маніфест у корені, чи не інлайнили його в
 * обгортку, чи не поїхав інспектор). Тест на підміненому стані сказав би
 * «оболонка працює» і на артефакті, якого немає.
 *
 * Чому власна фікстура, а не робоча задача: у `boss-interface` НІ ОДНА ітерація
 * не позначена опублікованою, тому `POST /api/publish` там відмовляє
 * («no iterations marked for publish») — тест мовчки не запустився б, а виглядав
 * би пропущеним.
 *
 * Чому статичний сервер, а не `file://`: маніфест приходить `fetch`-ем, і в
 * `file://` браузер блокує його CORS-ом — тобто тест падав би НЕ через бага.
 * Це не обхід межі, а точна модель бою: у Vercel `publish/` теж лежить під
 * HTTP-ом.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»:
 *
 *   гейт до пароля      — `if (window.__gateOpen) open(); else
 *                         window.__onGateOpen = open;` (`ext-shell.js`).
 *                         Перенеси `showPage()` у гілку попереднього
 *                         завантаження маніфеста — рамка поїде до пароля, і
 *                         глядач побачить ДРУГИЙ гейт усередині неї (ловили
 *                         живцем 03.08.2026): падає «рамка не вантажиться».
 *   назва у <title>     — `document.title` ставить лише `open()`, тобто вже під
 *                         відкритим гейтом. Постав його в `.then()` попереднього
 *                         завантаження — назва задачі опиниться у вкладці до
 *                         пароля (правило 30.07.2026): падає «title нейтральний».
 *   висоти до кадрів    — `card.h = frameCardH(card, ovW)` у `buildOverview`
 *                         плюс `w`/`h`, які везе `publish_frames`. Поверни
 *                         заглушку — світ стоїть 934px на картку й «сідає» під
 *                         справжні пропорції вже на очах глядача: падає
 *                         «розкладка правдива ДО приїзду кадрів».
 *   проводка смуги      — `EXT_ACTIONS[act]` + одна делегація. Забудь рядок —
 *                         кнопка мовчки нічого не робить (так у Плані A вмерла
 *                         кнопка палітри): падає «кожен контрол щось робить».
 *
 * ⛔ Свідомо НЕ перевіряється тут:
 *   mode[overview] — «Огляд» у ЦІЙ фікстурі ВИМКНЕНИЙ, бо кадрів немає (це
 *     окрема перевірка нижче, з причиною). Клікати вимкнену кнопку —
 *     перевіряти браузер, не наш код. Проводка режиму й саме полотно — у
 *     ДРУГОМУ наборі нижче («Огляд» на зібраному publish/ з кадрами): у нього
 *     своя фікстура, яку перед публікацією знімає справжня зʼємка.
 *   mode[layout] — активний на старті; клік по вже активному сегменту є
 *     свідомий ноп, і чекати від нього зміни означало б чекати там, де код
 *     обіцяє її не робити (те саме міркування, що в `tests/live/shell-bar.test.mjs`).
 *   vp[desktop] — так само активний типово.
 */
import assert from "node:assert/strict";
import test, { after, before, describe } from "node:test";
import { mkdirSync, writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import os from "node:os";

import { chromium } from "playwright";

import { HEAD } from "../../app/canvas-geom.js";
import { runShoot } from "../../bin/shoot.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Свій `portBase`: `node --test` крутить файли паралельно, і спільна база з
   іншими живими наборами (canvas=8890, viewport=9090, autoshoot=9190,
   overview-viewports=9290, shell-bar=9390, shell-panel=9490) дала б колізію.
   ДВІ бази, бо в цьому файлі два набори з окремими серверами: `portBase`
   розкидає порт у діапазоні `+0…+99`, тож 9590 і 9790 не перетинаються, а
   статика кожного стоїть на `+500` (10090 і 10290). */
const PORT_BASE = 10890;
const SHOT_PORT_BASE = 11190;
const VIEW = { width: 1400, height: 900 };
const PW = "1100";                                  // DEFAULT_PREVIEW_PW у serve.py
/**
 * Вхід ГЛИБОКИМ ПОСИЛАННЯМ на першу ітерацію.
 *
 * Типово превʼю відкриває ОСТАННЮ ітерацію (`startPage`), а весь вміст, на
 * який дивляться перевірки нижче, лежить в `it1`: дві сторінки, довга нотатка
 * й кадри. `it2` від `secondIteration` навмисно гола — вона там, щоб було чим
 * перемикати й на чому перевіряти «Огляд без кадрів». Тобто заходити сюди
 * треба так само, як заходить менеджер за скопійованою адресою, а не
 * підкручувати фікстуру під тест.
 */
const IT1 = `#p=${encodeURIComponent("it1/holovna")}`;
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8">`
  + `<title>Макет ${id}</title></head><body><h1>${id}</h1></body></html>`;

/* Сторінка для набору З КАДРАМИ: градієнт, а не білий лист. Порожній знімок
   стискається у WebP нижче `BYTES_FLOOR` і дістає `problem: «порожня
   сторінка»` — той самий прийом, що в `tests/live/shell-bar.test.mjs`.
   Висота ФІКСОВАНА (1200px) і це несуче: картка мусить вийти нижчою за
   заглушкові 900+34, інакше перевірка «висота з пропорції кадру» не змогла б
   відрізнити зміряну висоту від заглушки. */
const SHOT_PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8">`
  + `<title>Макет ${id}</title></head>`
  + `<body style="margin:0;height:1200px;background:repeating-linear-gradient(37deg,`
  + `#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)">`
  + `<h1 style="margin:0;font:700 40px system-ui">${id}</h1></body></html>`;

/** Нотатка it1 — ДОВГА, і це не косметика.
 *  З короткою («фікстура» з `fixture.mjs`) перевірка «примітка обрізається, а
 *  тег ні» вакуумно зелена: короткий рядок ніколи не впреться в
 *  `.txt--soft{max-width:112px}`, навіть якби межу прибрали. Той самий урок,
 *  що вже записаний у `longNoteFixture` (`tests/live/shell.test.mjs`).
 *  Слово «фікстура» лишається всередині — на нього дивиться перевірка мови. */
const IT1_NOTE = "фікстура з довгою нотаткою, яку дизайнер написав словами";

/** Друга опублікована ітерація — щоб крошка мала що перемикати.
 *  Фікстура з ОДНІЄЮ ітерацією не дає дропдауна свідомо (перемикати нема на
 *  що, юніт це стереже), тобто на ній проводку `iter` не перевірити взагалі. */
function secondIteration(dir) {
  const it2 = path.join(dir, "iterations", "it2", "nova");
  mkdirSync(it2, { recursive: true });
  writeFileSync(path.join(it2, "index.html"), PAGE("nova"));
  writeFileSync(path.join(dir, "iterations", "it2", "pages.json"),
    JSON.stringify({ pages: [{ id: "nova", name: "Нова", published: true }] }));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [
      { id: "it1", date: "24.08.2026 12:00", note: IT1_NOTE, published: true },
      { id: "it2", date: "25.08.2026 12:00", note: "друга", published: true },
    ],
  }));
}

/** Статика на вільному порту — так само, як `publish/` лежить у Vercel. */
async function staticServer(root, port) {
  const child = spawn("python3", ["-m", "http.server", String(port),
    "--bind", "127.0.0.1", "-d", root], { stdio: "ignore" });
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    try {
      const res = await fetch(`${base}/manifest.json`);
      if (res.ok) return { child, base };
    } catch {}
    await new Promise((done) => setTimeout(done, 250));
  }
  child.kill();
  throw new Error("статичний сервер превʼю не піднявся");
}

describe("зовнішня оболонка на зібраному publish/", () => {
  let tool;
  let statics;
  let browser;
  let base;

  before(async () => {
    const { dir } = taskFixture({ html: PAGE });
    secondIteration(dir);
    tool = await startServer(dir, { portBase: PORT_BASE, liga: true });   // 4d-4b: збірка превʼю — через `vercel-publish` ЛІГИ
    const res = await fetch(`${tool.url}/api/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ build_only: true }),
    });
    const built = await res.json();
    assert.ok(built.ok, `публікація не зібралась: ${JSON.stringify(built)}`);
    statics = await staticServer(built.dir, PORT_BASE + 500);
    base = statics.base;
    browser = await chromium.launch();
  });

  after(async () => {
    await browser?.close();
    statics?.child.kill();
    tool?.child.kill();
  });

  /** Свій контекст на тест: гейт памʼятає вхід у `sessionStorage`, і спільний
   *  контекст зробив би перевірку «до пароля» зеленою назавжди. */
  const fresh = async () => {
    const ctx = await browser.newContext({
      viewport: VIEW, permissions: ["clipboard-read", "clipboard-write"],
    });
    return { ctx, page: await ctx.newPage() };
  };

  const unlock = async (page) => {
    await page.fill("#agpass", PW);
    await page.click("#authform button");
    await page.locator("#bar .bar").waitFor();
  };

  test("до пароля рамка не вантажиться, а вкладка не називає задачу", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(base);
    await page.locator("#authgate").waitFor();

    // ⛔ Рамка порожня: інакше внутрішня сторінка показала б СВІЙ гейт усередині
    // неї — рівно те, що ловили живцем 03.08.2026.
    assert.equal(await page.locator("#frame").getAttribute("src"), null,
      "рамка поїхала до пароля");
    assert.equal(await page.evaluate(() => document.getElementById("frame").contentWindow
      .location.href), "about:blank", "у рамці вже щось відкрито");

    // ⛔ Правило 30.07.2026: URL превʼю може потрапити кому завгодно.
    assert.equal(await page.title(), "Перегляд макета");
    const seen = await page.evaluate(() => document.body.innerText);
    assert.ok(!seen.includes("Фікстура"), `назва задачі видна до пароля: ${seen}`);
    assert.ok(!seen.includes("Головна"), "назви сторінок видні до пароля");
  });

  /* Ворота (0.32.0): темна картка Deai, а не біла на блідо-зеленому. Міряємо ОБЧИСЛЕНИЙ фон — розмітка без CSS
     лишила б картку білою, і перевірка на наявність елементів цього не побачила б. */
  test("ворота: картка видна до пароля й темна", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(base);
    await page.locator("#authform").waitFor({ state: "visible" });
    const card = await page.evaluate(() => {
      const lum = (c) => { const m = c.match(/[\d.]+/g).map(Number);
        const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
        return 0.2126 * f(m[0]) + 0.7152 * f(m[1]) + 0.0722 * f(m[2]); };
      const cs = (sel) => getComputedStyle(document.querySelector(sel));
      const r = document.querySelector("#authform").getBoundingClientRect();
      return { card: lum(cs("#authform").backgroundColor), page: lum(cs("#authgate").backgroundColor),
               w: r.width, h: r.height, logo: !!document.querySelector("#authform svg"),
               text: document.getElementById("authform").innerText,
               ph: document.getElementById("agpass").placeholder,
               err: cs("#agerr").display };
    });
    assert.ok(card.card < 0.1, `картка воріт не темна (яскравість ${card.card})`);
    assert.ok(card.page < 0.1, `тло воріт не темне (яскравість ${card.page})`);
    assert.ok(card.w > 200 && card.h > 150, `картки не видно: ${card.w}x${card.h}`);
    assert.ok(card.logo, "нема знака Deai");
    assert.ok(card.text.includes("Перегляд макета") && card.text.includes("внутрішній матеріал")
      && card.text.includes("Увійти"), card.text);
    assert.ok(!card.text.includes("Фікстура"), "назва задачі до пароля");
    assert.equal(card.ph, "Пароль");
    assert.equal(card.err, "none", "помилка видна до спроби");
    await page.screenshot({ path: process.env.ZH_GATE_SHOT || path.join(os.tmpdir(), "zh-gate.png") });
  });

  test("ворота: невірний пароль показує помилку й не пускає", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(base);
    await page.fill("#agpass", "не-той");
    await page.click("#authform button");
    await page.locator("#agerr").waitFor({ state: "visible" });
    assert.equal((await page.locator("#agerr").innerText()).trim(), "Невірний пароль");
    assert.equal(await page.locator("#authgate").count(), 1, "гейт пустив з невірним паролем");
    assert.equal(await page.locator("#bar .bar").count(), 0);
  });

  test("після пароля піднімається смуга, дерево й рамка", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(`${base}/${IT1}`);
    await unlock(page);

    assert.ok((await page.locator("#bar .zone").count()) === 3, "смуга не з трьох зон");
    assert.ok((await page.locator("#bar").innerText()).includes("Фікстура"),
      "назви задачі в смузі немає");
    // Дерево — спільним `panelHTML`, тобто рядки ті самі, що в інструменті.
    assert.equal(await page.locator("#pages-panel .row").count(), 2);
    // Назва задачі у вкладці — ЛИШЕ після входу.
    assert.equal(await page.title(), "Фікстура");
    // Рядка вкладок у превʼю нема — смуга стоїть під самим верхом, рамка й дерево — одразу під смугою.
    // До 0.28.2 зверху лишалась порожня смуга заввишки з рядок вкладок інструмента (36 px).
    const geo = await page.evaluate(() => {
      const r = (sel) => document.querySelector(sel).getBoundingClientRect();
      return { bar: r("#bar .bar").top, barBottom: r("#bar .bar").bottom,
               stage: r("#stage").top, tree: r("#pages-panel").top };
    });
    assert.equal(geo.bar, 0, `смуга не під самим верхом: ${JSON.stringify(geo)}`);
    assert.equal(geo.stage, geo.barBottom, `рамка не під смугою: ${JSON.stringify(geo)}`);
    assert.equal(geo.tree, geo.barBottom, `дерево не під смугою: ${JSON.stringify(geo)}`);
    // Рамка відкрила першу сторінку й справді завантажилась.
    await page.waitForFunction(() => {
      const f = document.getElementById("frame");
      return f?.contentWindow?.document?.querySelector("h1")?.textContent === "holovna";
    }, null, { timeout: 15000 });

    // ⛔ Панель у статиці — лише-читання: жодної дії над даними.
    for (const act of ["pagemenu", "newpage", "shoot"]) {
      assert.equal(await page.locator(`#pages-panel [data-act="${act}"]`).count(), 0,
        `«${act}» у статичному превʼю нікуди не веде`);
    }
    // ⛔ Інспектора в зовнішньому превʼю немає — межа, яку тримає publish.
    assert.equal(await page.locator('[data-act="inspector"]').count(), 0);
  });

  test("кожен видимий контрол смуги щось робить на клік", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(base);
    await unlock(page);

    /* Тільки ВИДИМІ й НЕ активні: активний сегмент — свідомий ноп (див. шапку),
       а вимкнений «Огляд» перевіряється окремим тестом нижче. */
    const acts = await page.evaluate(() => [...document.querySelectorAll(
      "#bar [data-act], #bar [data-dd]")]
      .filter((el) => el.offsetParent !== null && !el.disabled
        && el.getAttribute("aria-pressed") !== "true")
      .map((el) => el.dataset.dd
        ? `dd:${el.dataset.dd}`
        : `${el.dataset.act}${el.dataset.val ? `[${el.dataset.val}]` : ""}`));
    // Незалежний свідок: без нього цикл був би зелений і на порожній смузі.
    assert.ok(acts.length >= 4, `видимих контролів лише ${acts.length}: ${acts}`);

    /* Знімок «що взагалі є на екрані»: розмітка смуги, класи `body`, адреса
       рамки й наявність оверлея `ask()`. Останнє — не про запас: фолбек
       «Копіювати посилання» відкриває саме його, коли буфер обміну недоступний,
       і без цього доданку робоча кнопка виглядала б забутою в проводці. */
    const shot = () => page.evaluate(() => document.getElementById("bar").innerHTML
      + document.body.className + (document.getElementById("frame").src || "")
      + !!document.querySelector(".cv-ask-scrim"));

    for (const act of acts) {
      const sel = act.startsWith("dd:")
        ? `#bar [data-dd="${act.slice(3)}"]`
        : (act.includes("[")
          ? `#bar [data-act="${act.split("[")[0]}"][data-val="${act.slice(act.indexOf("[") + 1, -1)}"]`
          : `#bar [data-act="${act}"]`);
      const before = await shot();
      await page.locator(sel).first().click();
      /* Чекаємо зміну, а не читаємо одразу: `copylink` віддає підтвердження
         через проміс буфера обміну, тобто на такт пізніше за клік. Читання
         «в ту саму мілісекунду» падало б на РОБОЧІЙ кнопці. */
      try {
        await page.waitForFunction(([b]) => document.getElementById("bar").innerHTML
          + document.body.className + (document.getElementById("frame").src || "")
          + !!document.querySelector(".cv-ask-scrim") !== b, [before], { timeout: 4000 });
      } catch (e) {
        assert.fail(`клік по «${act}» не змінив нічого — забутий рядок у EXT_ACTIONS`);
      }
      // Дропдаун за собою закриваємо, інакше він накриє наступний контрол.
      if (act.startsWith("dd:")) await page.keyboard.press("Escape");
    }
  });

  /* 0.32.0 Task 2: острівець превʼю. До Task 3–4 він має ОДНУ кнопку — «Сховати інтерфейс»: ні «баг», ні стану AI. */
  const shownBox = (page, sel) => page.evaluate((q) => {
    const e = document.querySelector(q);
    return !!e && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0;
  }, sel);
  const cleanOn = (page) => page.evaluate(() => document.documentElement.classList.contains("cv-clean"));

  test("острівець: по центру внизу, одна кнопка «Сховати інтерфейс», без «баг» і AI", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(`${base}/${IT1}`);
    await unlock(page);
    const isl = page.locator("#hud .island");
    await isl.waitFor();
    const box = await isl.boundingBox();
    assert.ok(Math.abs(box.x + box.width / 2 - VIEW.width / 2) <= 2, `острівець не по центру: ${JSON.stringify(box)}`);
    assert.ok(VIEW.height - (box.y + box.height) < 40 && box.y + box.height <= VIEW.height, `острівець не внизу: ${JSON.stringify(box)}`);
    const acts = await page.evaluate(() => [...document.querySelectorAll("#hud [data-act]")].map((b) => b.dataset.act));
    assert.deepEqual(acts, ["clean"]);
    assert.equal(await page.locator('#hud [data-act="feedback"], #hud #claude-hud, #hud .isl-claude, #hud .isl-sep').count(), 0);
    const btn = page.locator('#hud [data-act="clean"]');
    assert.equal(await btn.getAttribute("aria-label"), "Сховати інтерфейс");
    assert.match(await btn.getAttribute("title"), /⇧⌘\\/);
    // Іконка справді намальована (symbol є в спрайті), а не порожній квадрат.
    assert.equal(await page.locator("#sprite #i-clean").count(), 1);
  });

  test("кожен видимий контрол острівця щось робить на клік", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(base);
    await unlock(page);
    const acts = await page.evaluate(() => [...document.querySelectorAll("#hud [data-act]")]
      .filter((el) => el.offsetParent !== null && !el.disabled).map((el) => el.dataset.act));
    assert.ok(acts.length >= 1, "острівець порожній");
    for (const act of acts) {
      const before = await page.evaluate(() => document.documentElement.className + !!document.querySelector(".cv-ask-scrim"));
      await page.locator(`#hud [data-act="${act}"]`).first().click();
      try {
        await page.waitForFunction((b) => document.documentElement.className + !!document.querySelector(".cv-ask-scrim") !== b,
          before, { timeout: 4000 });
      } catch (e) {
        assert.fail(`клік по «${act}» на острівці не змінив нічого — забутий рядок у EXT_ACTIONS`);
      }
      if (await cleanOn(page)) await page.click("#cv-unclean");
    }
  });

  test("«Сховати інтерфейс»: ховає смугу, дерево й острівець; «Показати інтерфейс» і ⇧⌘\\ (з обгортки й з рамки) повертають", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(`${base}/${IT1}`);
    await unlock(page);
    await page.waitForFunction(() => document.getElementById("frame")?.contentWindow?.document?.querySelector("h1"),
      null, { timeout: 15000 });
    const all = async () => ({ bar: await shownBox(page, "#bar .bar"), tree: await shownBox(page, "#pages-panel"),
      island: await shownBox(page, "#hud .island") });
    assert.deepEqual(await all(), { bar: true, tree: true, island: true });

    await page.click('#hud [data-act="clean"]');
    assert.deepEqual(await all(), { bar: false, tree: false, island: false }, "інтерфейс не сховався");
    assert.equal(await shownBox(page, "#cv-unclean"), true);

    await page.click("#cv-unclean");
    assert.deepEqual(await all(), { bar: true, tree: true, island: true }, "«Показати інтерфейс» не повернув");

    await page.keyboard.press("ControlOrMeta+Shift+Backslash");
    assert.equal(await cleanOn(page), true, "акорд з обгортки не сховав");
    await page.keyboard.press("ControlOrMeta+Shift+Backslash");
    assert.equal(await cleanOn(page), false, "акорд з обгортки не повернув");

    // З рамки: клік по макету віддає їй фокус — акорд ловить слухач документа рамки.
    await page.click('#hud [data-act="clean"]');
    await page.frameLocator("#frame").locator("h1").click();
    await page.keyboard.press("ControlOrMeta+Shift+Backslash");
    await page.waitForFunction(() => !document.documentElement.classList.contains("cv-clean"), null, { timeout: 3000 });
    assert.deepEqual(await all(), { bar: true, tree: true, island: true }, "акорд з рамки не повернув інтерфейс");
    await page.frameLocator("#frame").locator("h1").click();
    await page.keyboard.press("ControlOrMeta+Shift+Backslash");
    assert.equal(await cleanOn(page), true, "акорд з рамки не сховав");
  });

  test("перемикач ширин задає ширину рамки", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(base);
    await unlock(page);
    await page.click('#bar [data-act="vp"][data-val="tablet"]');
    assert.ok(await page.evaluate(() => document.body.classList.contains("vp-fixed")));
    assert.equal(await page.evaluate(() => document.body.style
      .getPropertyValue("--cv-vpw")), "768px");
    const w = await page.evaluate(() => document.getElementById("frame").clientWidth);
    assert.equal(w, 768, `рамка лишилась ${w}px — CSS ширину не взяв`);
  });

  test("безшовний вхід через #k= відкриває саму сторінку", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(`${base}/#k=${PW}&p=${encodeURIComponent("it1/poshuk")}`);
    await page.locator("#bar .bar").waitFor();
    assert.equal(await page.locator("#authgate").count(), 0, "гейт не пустив за токеном");
    await page.waitForFunction(() => document.getElementById("frame")
      ?.src.endsWith("it1/poshuk/index.html"), null, { timeout: 15000 });
    // Токен із hash прибраний, глибоке посилання лишилось — інакше пароль
    // мандрував би далі в кожній скопійованій адресі.
    assert.equal(await page.evaluate(() => location.hash), "#p=it1%2Fposhuk");
  });

  /**
   * Мова інтерфейсу — вибір ГЛЯДАЧА в його браузері (`dc-lang` у
   * localStorage), і зовнішня оболонка читає його сама (`ext-shell.js`).
   * Палітри ⌘K тут немає, тож єдиний шлях перемкнути мову — написати ключ
   * ДО завантаження модуля, звідси `addInitScript`.
   *
   * Заміряно 03.09.2026 на цій самій фікстурі: смуга йшла англійською
   * («Layout / Overview / Copy link»), панель теж («Layers / Pages»), а
   * крошка ітерації показувала «Іт.1 · фікстура» — `publish_manifest` клав у
   * маніфест ГОТОВИЙ підпис, спечений `iteration_label()` у Python, який про
   * мову глядача не знає й знати не може.
   *
   * ⛔ Мішень — ТЕГ (`.txt--fix`), не вся крошка. Примітка («фікстура») це
   * ДАНІ, які написав дизайнер, і вона лишається тією мовою, якою написана;
   * шукати кирилицю в усій крошці означало б вимагати перекладу даних.
   * `.txt--soft` тут же стоїть свідком: якби розділення класів зникло,
   * кирилиця примітки читалась би як кирилиця тега — і перевірка мовчки
   * перестала б бути перевіркою.
   */
  test("при dc-lang=en тег ітерації англійський, примітка лишається даними", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.addInitScript(() => {
      try { localStorage.setItem("dc-lang", "en"); } catch (e) { /* приватний режим */ }
    });
    await page.goto(`${base}/${IT1}`);
    await unlock(page);

    // Свідок ПЕРШИМ: без нього «It.1» нижче міг би бути випадковим — мова
    // просто не перемкнулась би, і тест шукав би не те, що думає.
    const bar = await page.locator("#bar").innerText();
    assert.ok(bar.includes("Overview"),
      `смуга не перемкнулась на англійську — перевірка тега випадкова: ${bar}`);

    const tag = await page.locator("#bar .crumb--iter .txt--fix").innerText();
    assert.equal(tag, "It.1", `тег ітерації не зі словника: «${tag}»`);
    assert.ok(!/[а-яіїєґА-ЯІЇЄҐ]/.test(tag), `кирилиця в тезі ітерації: «${tag}»`);

    // Другий свідок: примітка на місці й саме вона несе кирилицю — тобто
    // мішень вище справді тег, а не порожній вузол.
    const note = await page.locator("#bar .crumb--iter .txt--soft").innerText();
    assert.ok(note.includes("фікстура"), `примітки ітерації немає: «${note}»`);
  });

  /**
   * Те, ЗАРАДИ чого тег і примітка розведені по двох вузлах.
   *
   * `.txt--fix{flex:none}` не обрізається ніколи, `.txt--soft` обрізається
   * завжди (`.crumb--iter .txt--soft{max-width:112px}`). Одним вузлом довга
   * примітка зʼїдала номер версії — тобто крошка перестала відповідати на
   * питання, для якого вона й існує, рівно там, де місця мало.
   *
   * Заміряно 03.09.2026 на 1024 / 1180 / 1440 (пороги контейнерних запитів
   * смуги): смуга не ширша за вікно, тег «Іт.1» показаний ЦІЛКОМ (19px,
   * `scrollWidth == clientWidth`), примітка врізана 343 → 112px. Тобто
   * стискається саме та половина, якою можна пожертвувати.
   *
   * ⛔ Порівнюємо `scrollWidth` із `clientWidth`, а не тексти: `innerText`
   * віддає ПОВНИЙ рядок і для вузла, врізаного `text-overflow:ellipsis`, —
   * перевірка на текст була б зелена й тоді, коли тег на екрані зник.
   * Свідок проти вакууму — сама примітка: якщо ВОНА не врізана, то фікстура
   * закоротка, і про тег цей тест не довів нічого.
   */
  test("довга примітка тисне на примітку, а не на тег ітерації", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(`${base}/${IT1}`);
    await unlock(page);

    const bad = [];
    for (const width of [1024, 1180, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      // Повний цикл layout+paint після зміни розміру — те саме подієве
      // очікування, що в `tests/live/shell.test.mjs`, не голий таймаут.
      await page.evaluate(() => new Promise((r) => requestAnimationFrame(
        () => requestAnimationFrame(r))));
      const m = await page.evaluate(() => {
        const bar = document.getElementById("bar");
        const box = (sel) => {
          const el = document.querySelector(sel);
          return el && { sw: el.scrollWidth, cw: el.clientWidth, text: el.innerText };
        };
        return {
          barSW: bar.scrollWidth, win: window.innerWidth,
          fix: box("#bar .crumb--iter .txt--fix"),
          soft: box("#bar .crumb--iter .txt--soft"),
        };
      });
      if (m.barSW > m.win) bad.push({ width, why: "смуга ширша за вікно", ...m });
      if (!m.fix) bad.push({ width, why: "тега ітерації немає", ...m });
      else if (m.fix.sw > m.fix.cw) bad.push({ width, why: "ТЕГ обрізало", ...m });
      if (!m.soft) bad.push({ width, why: "примітки немає", ...m });
      else if (m.soft.sw <= m.soft.cw) {
        bad.push({ width, why: "примітка НЕ врізана — фікстура закоротка", ...m });
      }
    }
    assert.deepEqual(bad, [], `крошку стиснуло:\n${JSON.stringify(bad, null, 1)}`);
  });

  /**
   * ⛔ Чому це живий тест, а не лише юніт `startPage`. Юніт перевіряє ФУНКЦІЮ
   * на маніфесті, який написали руками; тут маніфест складає справжня
   * публікація, а сторінку відкриває справжня проводка (`open()` → `goto`).
   * Між ними рівно те, що вже ламалось: порядок ітерацій у `publish_manifest`
   * (`iters` — лише ті, де є сторінки) і hash, який гейт розбирає на вході.
   * Поверни `pages[0]` — тест червоніє і в крошці, і в адресі рамки.
   */
  test("типово превʼю відкриває ОСТАННЮ ітерацію, а не першу", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(base);
    await unlock(page);

    /* Свідок ПЕРШИМ: у маніфесті справді ДВІ ітерації, і `it1` у ньому перша.
       Без нього «остання» могла б збігтись із «єдиною», і перевірка була б
       зелена на фікстурі, де перемикати нема на що. */
    const iters = await page.evaluate(() => fetch("manifest.json")
      .then((r) => r.json()).then((m) => m.iters.map((x) => x.id)));
    assert.deepEqual(iters, ["it1", "it2"], `ітерації в маніфесті: ${iters}`);

    await page.waitForFunction(() => document.getElementById("frame")
      ?.src.endsWith("it2/nova/index.html"), null, { timeout: 15000 });
    const tag = await page.locator("#bar .crumb--iter .txt--fix").innerText();
    assert.equal(tag, "Іт.2", `крошка показує не останню ітерацію: «${tag}»`);
    // Панель пішла за ітерацією, а не лишилась деревом першої.
    assert.deepEqual(await page.locator("#pages-panel .row").allInnerTexts(), ["Нова"]);
  });

  test("«Огляд» без кадрів вимкнений і каже причину видимим текстом", async (t) => {
    const { ctx, page } = await fresh();
    t.after(() => ctx.close());
    await page.goto(base);
    await unlock(page);
    const btn = page.locator('#bar [data-act="mode"][data-val="overview"]');
    assert.equal(await btn.isDisabled(), true, "кадрів немає, а «Огляд» живий");
    assert.ok((await btn.innerText()).includes("кадрів ще немає"),
      "вимкнена кнопка мовчить про причину — читається як зламана");
  });
});

/**
 * «Огляд» — окремим набором зі СВОЄЮ фікстурою, бо йому потрібне те, чого
 * набір вище має не мати: кадри. Тримати одну фікстуру на два набори не можна
 * — перевірка «Огляд без кадрів вимкнений і каже причину» стала б зеленою
 * назавжди або червоною назавжди, залежно від того, хто знімає першим.
 *
 * ⛔ Зʼємка тут СПРАВЖНЯ (`runShoot` із `bin/shoot.mjs`), а не рукотворні
 * `.webp` поруч із рукописним `shots/manifest.json`. Рукотворні були б швидші,
 * але вони обходять рівно те, що в цій задачі найлегше зламати: чи ключі, під
 * якими зʼємка кладе кадри, збігаються з тими, під якими їх шукає полотно
 * (`frameKey` → `publish_frames` → `overviewRows`). Фікстура, у якій ключі
 * написані рукою, узгоджена сама з собою й молчить про розходження.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»:
 *
 *   карток стільки, скільки — `overviewRows` + `buildRows`. Прибери спуск у
 *   сторінок                  теку чи фільтр по ітерації — і полотно молча
 *                             показує менше сторінок, ніж превʼю має.
 *   кадр 1:1 без масштабу   — `overviewCardW` бере пресети ПОЛОТНА. Візьми
 *                             `PRESETS` (де «Десктоп» = `null`) — ширина
 *                             картки стає `null`, розкладка сипле NaN.
 *   висота з пропорції      — `onFrameLoad`. Прибери — усі картки стоять
 *                             заглушковими 900px, і кадр 6879px видно на 13%.
 *   ліниві кадри            — `img.loading`. Прибери — вкладка глядача тягне
 *                             всі кадри відразу (заміряно 15.3M на it3).
 *   колесо зумить           — `zoomAt` + `applyCam`. Прибери — полотно
 *                             мертве на 5% масштабу, і читати на ньому нічого.
 *   клік відкриває макет    — `openCard` + поріг у `wireCanvas`. Прибери
 *                             поріг — панорама кінчається відкритою сторінкою.
 */
describe("«Огляд» на зібраному publish/ з кадрами", () => {
  let tool;
  let statics;
  let browser;
  let base;
  let man;
  let pages;

  before(async () => {
    const { dir, it1 } = taskFixture({ html: SHOT_PAGE });
    /* Друга ітерація потрібна саме тут: у неї кадрів немає НІКОЛИ (її ніхто не
       знімає), і рівно на ній перевіряється, що «Огляд» без кадрів вибиває в
       «Макет», а не в порожнє полотно. */
    secondIteration(dir);
    tool = await startServer(dir, { portBase: SHOT_PORT_BASE, liga: true });
    /* Справжня зʼємка фікстури: після неї в `iterations/it1/shots/` лежать
       `.webp` і манифест, які публікація повезе в `publish/it1/_frames/`. */
    await runShoot({ dir: it1, it: "it1", url: tool.url, all: true,
                     now: "24.08.2026 12:00", launch: () => chromium.launch() });
    const res = await fetch(`${tool.url}/api/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ build_only: true }),
    });
    const built = await res.json();
    assert.ok(built.ok, `публікація не зібралась: ${JSON.stringify(built)}`);
    statics = await staticServer(built.dir, SHOT_PORT_BASE + 500);
    base = statics.base;
    man = await (await fetch(`${base}/manifest.json`)).json();
    /* Сторінки ПЕРШОЇ ітерації — саме її кадри знято, і саме в неї заходить
       `open()` глибоким посиланням (типовий вхід веде в останню, `it2`).
       `man.pages` плаский і несе ще й сторінку `it2`, тобто рахувати картки
       полотна по ньому означало б чекати на одну зайву назавжди. */
    pages = man.pages.filter((p) => p.it === "it1");
    /* Незалежний свідок фікстури: без кадрів у маніфесті весь набір нижче
       перевіряв би вимкнену кнопку й зеленів би ні про що. */
    assert.ok(Object.keys(man.frames.it1 || {}).length >= pages.length,
      `зʼємка не поклала кадрів: ${JSON.stringify(man.frames)}`);
    browser = await chromium.launch();
  });

  after(async () => {
    await browser?.close();
    statics?.child.kill();
    tool?.child.kill();
  });

  /** Свій контекст на тест — гейт памʼятає вхід у `sessionStorage`. */
  const open = async () => {
    const ctx = await browser.newContext({ viewport: VIEW });
    const page = await ctx.newPage();
    // Глибоким посиланням: типовий вхід веде в `it2`, яку ніхто не знімав.
    await page.goto(`${base}/${IT1}`);
    await page.fill("#agpass", PW);
    await page.click("#authform button");
    await page.locator("#bar .bar").waitFor();
    return { ctx, page };
  };

  /** Зайти в «Огляд» і дочекатись, поки всі кадри доїдуть і сядуть у розкладку. */
  const overview = async (page) => {
    await page.click('#bar [data-act="mode"][data-val="overview"]');
    await page.waitForFunction(() => !document.getElementById("canvas").hidden);
    await page.waitForFunction((n) => {
      const cards = [...document.querySelectorAll("#world .cv-card")];
      return cards.length === n
        && cards.every((c) => c.querySelector("img")?.complete);
    }, pages.length, { timeout: 30000 });
    /* ⚠️ `complete` НЕ означає, що розкладка вже перерахована. Висоту картки
       ставить `onFrameLoad` (маніфест її не несе), а саму розкладку — склеєний
       rAF: кадри приїжджають по одному, і повний прохід по DOM на кожен був би
       синхронним перерахунком стилю під рукою глядача. За специфікацією
       `complete` і подія `load` трапляються в ОДНІЙ задачі, тож після
       `complete` висоти вже записані — лишається пропустити той самий
       анімаційний кадр. Двох досить, і це не «на всяк випадок»: перший віддає
       склеєну розкладку, другий гарантує, що вона вже в стилі.
       Без цих двох рядків перевірка висот падала на РОБОЧОМУ коді (виміряно:
       читала 934px, тобто заглушку, поки rAF ще не відпрацював). */
    await page.evaluate(() => new Promise((done) => {
      requestAnimationFrame(() => requestAnimationFrame(done));
    }));
  };

  const scaleOf = (page) => page.evaluate(() => {
    const m = /scale\(([\d.]+)\)/.exec(document.getElementById("world").style.transform);
    return m ? Number(m[1]) : null;
  });

  test("карток стільки, скільки сторінок, і кожна несе лінивий кадр", async (t) => {
    const { ctx, page } = await open();
    t.after(() => ctx.close());
    await overview(page);

    assert.equal(await page.locator("#world .cv-card").count(), pages.length);
    // Сцена схована: інакше її підкладка накрила б полотно (див. `applyMode`).
    assert.equal(await page.evaluate(() => document.getElementById("stage").hidden), true);
    // Підпис РЯДУ — окреме дитя світу, по одному на верхньорівневу сторінку.
    assert.equal(await page.locator("#world .cv-row-title").count(),
      pages.filter((p) => p.depth === 0).length);

    // ⛔ Ліниве завантаження — не оптимізація: 66 кадрів по ~237K на it3.
    assert.deepEqual([...new Set(await page.evaluate(() => [
      ...document.querySelectorAll("#world .cv-card img")].map((i) => i.loading)))],
      ["lazy"]);
    // Заглушок немає: кадри знято, отже кожна картка мусить показувати знімок.
    assert.equal(await page.locator("#world .cv-card-ph").count(), 0);

    /* ⛔ Висота картки з ПРОПОРЦІЇ кадру, а не заглушкова: фікстура — сторінка
       на 1200px у кадрі 1280px завширшки, тобто картка мусить бути НИЖЧОЮ за
       заглушкові 900+34. Без `onFrameLoad` тут стоїть рівно 934. */
    const heights = await page.evaluate(() => [
      ...document.querySelectorAll("#world .cv-card")].map((c) => c.offsetHeight));
    for (const h of heights) {
      assert.ok(h > 0 && h !== 934,
        `картка ${h}px — висота лишилась заглушковою, пропорцію кадру не спитали`);
    }

    /* Габарит світу справді вписаний: масштаб між підлогою і стелею камери, і
       ні краю світу за межами полотна. */
    const scale = await scaleOf(page);
    assert.ok(scale > 0 && scale <= 1, `масштаб ${scale} поза межами «вписати все»`);
  });

  test("колесо змінює масштаб полотна", async (t) => {
    const { ctx, page } = await open();
    t.after(() => ctx.close());
    await overview(page);
    const before = await scaleOf(page);
    const box = await page.locator("#canvas").boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, -400);
    await page.waitForFunction((b) => {
      const m = /scale\(([\d.]+)\)/.exec(document.getElementById("world").style.transform);
      return m && Number(m[1]) !== b;
    }, before, { timeout: 4000 });
    assert.ok(await scaleOf(page) > before, "колесо вгору мусить збільшувати");
  });

  test("клік по картці відкриває «Макет» на ТІЙ сторінці", async (t) => {
    const { ctx, page } = await open();
    t.after(() => ctx.close());
    await overview(page);

    /* Беремо НЕ першу сторінку: перша й так відкрита на старті, тож збіг був би
       випадковим — тест зеленів би і на «клік завжди веде на першу». */
    const want = pages[pages.length - 1];
    await page.locator(`#world .cv-card[data-page="${want.id}"] .cv-card-body`).click();
    await page.waitForFunction((p) => document.getElementById("frame")?.src.endsWith(p),
      want.path, { timeout: 15000 });
    assert.equal(await page.evaluate(() => document.getElementById("canvas").hidden), true);
    assert.equal(await page.locator('#bar [data-act="mode"][data-val="layout"]')
      .getAttribute("aria-pressed"), "true", "сегмент лишився на «Огляді»");
  });

  test("кнопка «Відкрити» в голові кадру робить те саме", async (t) => {
    const { ctx, page } = await open();
    t.after(() => ctx.close());
    await overview(page);
    const want = pages[pages.length - 1];
    await page.locator(`#world .cv-card[data-page="${want.id}"] .cv-open`).click();
    await page.waitForFunction((p) => document.getElementById("frame")?.src.endsWith(p),
      want.path, { timeout: 15000 });
  });

  test("панорама не відкриває сторінку — жест із порогом", async (t) => {
    const { ctx, page } = await open();
    t.after(() => ctx.close());
    await overview(page);
    const before = await page.evaluate(() => document.getElementById("frame").src);
    /* ⛔ Тягнемо САМЕ З КАРТКИ, а не з середини полотна. Виміряно мутаційно: із
       середини перевірка лишалась зеленою навіть із прибраним порогом жесту —
       на «вписати все» центр припадає в зазор між рядами, `openCard` не
       знаходить `.cv-card` і виходить сам. Тобто охоронець перевіряв не поріг,
       а те, що в тій точці кадру немає. */
    const box = await page.locator("#world .cv-card").first().boundingBox();
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    await page.mouse.move(cx - 180, cy - 60, { steps: 8 });
    await page.mouse.up();
    assert.equal(await page.evaluate(() => document.getElementById("canvas").hidden), false,
      "протяг по полотну відкрив сторінку — порогу жесту немає");
    assert.equal(await page.evaluate(() => document.getElementById("frame").src), before);
    // Світ поїхав за рукою — інакше «нічого не відкрилось» означало б «нічого
    // не сталось», і тест був би зеленим на мертвому полотні.
    assert.ok(await page.evaluate(() => /translate\(-?\d/.test(
      document.getElementById("world").style.transform)));
  });

  test("перемикач ширин у «Огляді» бере ІНШІ кадри, а не масштабує ті самі", async (t) => {
    const { ctx, page } = await open();
    t.after(() => ctx.close());
    await overview(page);
    const deskKeys = await page.evaluate(() => [
      ...document.querySelectorAll("#world .cv-card")].map((c) => c.dataset.key));

    await page.click('#bar [data-act="vp"][data-val="tablet"]');
    await page.waitForFunction(() => [...document.querySelectorAll("#world .cv-card")]
      .every((c) => c.dataset.key.endsWith("@768")), null, { timeout: 15000 });
    const tabKeys = await page.evaluate(() => [
      ...document.querySelectorAll("#world .cv-card")].map((c) => c.dataset.key));
    assert.notDeepEqual(tabKeys, deskKeys);
    assert.deepEqual(tabKeys, deskKeys.map((k) => `${k}@768`));

    /* Кадрів 768 фікстура не знімала (`runShoot` без `--vp` знімає типову
       ширину), тобто кожна картка мусить стати ЗАГЛУШКОЮ З ПРИЧИНОЮ, а не
       порожнім прямокутником. Рівно те правило, що вимикає «Огляд» без кадрів. */
    assert.equal(await page.locator("#world .cv-card-ph").count(), pages.length);
    const why = await page.locator("#world .cv-card-ph").first().innerText();
    assert.ok(why.includes("768"), `заглушка мовчить про причину: «${why}»`);
    // І ширина картки справді інша — кадр 1:1, не стиснутий десктопний.
    assert.equal(await page.evaluate(() => document.querySelector("#world .cv-card")
      .offsetWidth), 768);
  });

  /* ⛔ ЦЕНТРАЛЬНА перевірка правки 03.09.2026, і зробити її можна ЛИШЕ живою:
     вона про те, що глядач бачить, поки кадри ЩЕ НЕ приїхали. Кадри тут
     затримані назавжди (запит висить, `route` не відповідає), тобто
     `onFrameLoad` не спрацює ні разу — а розкладка мусить бути вже правдива, з
     `w`/`h` у маніфесті.
     Мутація, якою доведено: у `buildOverview` повернути `card.h =
     FRAME_H_FALLBACK` (або в `frameCardH` віддавати заглушку завжди) — усі
     картки стають 934px, і перевірка червоніє по суті, а не на селекторі.
     Заглушкових 934 тут бути не сміє: фікстура — сторінка на 1200px. */
  test("розкладка правдива ДО приїзду кадрів — висоти з маніфеста", async (t) => {
    const ctx = await browser.newContext({ viewport: VIEW });
    t.after(() => ctx.close());
    const page = await ctx.newPage();
    /* Кадр не доїде НІКОЛИ: обіцянку `route` свідомо не завершуємо. `abort()`
       тут не годиться — він робить `img.complete === true` і кидає `error`,
       тобто моделював би БИТИЙ кадр, а нам треба ПОВІЛЬНИЙ. */
    await page.route("**/_frames/**", () => {});
    // Свій вхід, а не `open()`: маршрут треба поставити ДО завантаження. Тому
    // й глибоке посилання тут повторюється — кадри є лише в `it1`.
    await page.goto(`${base}/${IT1}`);
    await page.fill("#agpass", PW);
    await page.click("#authform button");
    await page.locator("#bar .bar").waitFor();
    await page.click('#bar [data-act="mode"][data-val="overview"]');
    await page.waitForFunction((n) => document.querySelectorAll("#world .cv-card")
      .length === n, pages.length, { timeout: 15000 });
    await page.evaluate(() => new Promise((done) => {
      requestAnimationFrame(() => requestAnimationFrame(done));
    }));

    // Незалежний свідок: жоден кадр справді не завантажився.
    assert.deepEqual([...new Set(await page.evaluate(() => [
      ...document.querySelectorAll("#world .cv-card img")].map((i) => i.complete)))],
      [false], "кадр усе-таки приїхав — перевірка міряла б не те, що обіцяє");

    /* Очікуване рахуємо з МАНІФЕСТА тією ж пропорцією, що й код: `h * cardW /
       w`, плюс голова картки. Числа не зашиті — інакше перевірка була б
       переказом реалізації й зеленіла б разом із нею. */
    const got = await page.evaluate(() => [
      ...document.querySelectorAll("#world .cv-card")].map((c) => ({
        key: c.dataset.key, h: c.offsetHeight, w: c.offsetWidth })));
    assert.equal(got.length, pages.length);
    for (const card of got) {
      const rec = man.frames.it1[card.key];
      assert.ok(rec?.w > 0 && rec?.h > 0,
        `маніфест не несе розміру кадру ${card.key}: ${JSON.stringify(rec)}`);
      assert.equal(card.h, Math.round((rec.h * card.w) / rec.w) + HEAD,
        `картка ${card.key} стоїть не за розміром із маніфеста`);
      assert.notEqual(card.h, 934,
        `картка ${card.key} лишилась заглушковою — розмір із маніфеста не спитали`);
    }

    /* Габарит світу вписаний уже ЗАРАЗ: сенс правки не в числах на картках, а
       в тому, що камера більше не «сідає» під справжні пропорції на очах. */
    const scale = await scaleOf(page);
    assert.ok(scale > 0 && scale <= 1, `масштаб ${scale} поза межами «вписати все»`);
  });

  test("ітерація без кадрів вибиває з «Огляду» в «Макет», а не в порожнє полотно",
    async (t) => {
      const { ctx, page } = await open();
      t.after(() => ctx.close());
      await overview(page);
      // `it2` додає `secondIteration` — сторінка є, кадрів немає ніколи.
      await page.click('#bar [data-dd="iter"]');
      await page.click('#bar [data-act="iter"][data-val="it2"]');
      await page.waitForFunction(() => document.getElementById("canvas").hidden,
        null, { timeout: 4000 });
      assert.equal(await page.evaluate(() => document.getElementById("stage").hidden), false);
      const seg = page.locator('#bar [data-act="mode"][data-val="overview"]');
      assert.equal(await seg.getAttribute("aria-pressed"), "false",
        "сегмент лишився натиснутим на «Огляді», якого на екрані немає");
      assert.equal(await seg.isDisabled(), true);
    });
});

/**
 * КРОШКА ЗАДАЧІ з назвою, яка не влазить — окремим набором зі СВОЄЮ фікстурою.
 *
 * Чому не в наборі вище: там назва задачі коротка навмисно (на неї дивляться
 * перевірки «до пароля назви не видно» і «після пароля вона в смузі»), а
 * геометрію переповнення на короткій назві не відтворити взагалі — рівно той
 * самий урок, що вже записаний для довгої нотатки ітерації.
 *
 * Що ловимо (спостереження власника зі скріншота 09.09.2026): «Business Forum
 * 360 · лендинг» вилазив за свій бокс і накривав іконку та крошку ітерації.
 * Механізм: `.crumb--task .txt{max-width:150px}` стискає БОКС, а пара
 * `overflow:hidden;text-overflow:ellipsis` живе лише в `.ctl .txt` і
 * `.txt--soft` — плоска крошка ж навмисно НЕ `.ctl` (рішення v1.30.0: `.ctl`
 * брехав би курсором і підсвіткою). Гліфи малюються поверх сусідів, і
 * `.txt--fix{flex:none}` не дає вузлу стиснутись.
 *
 * ⛔ Перевірка ГЕОМЕТРИЧНА, а не на розмітку: переповнення живе в геометрії, і
 * тест на наявність CSS-правила лишився б зеленим після будь-якої правки, яка
 * правило зберегла, а ефект втратила (напр. перебила специфічністю).
 *
 * ⛔ Тег ітерації перевіряємо тим самим прогоном: «тег не обрізається НІКОЛИ» —
 * несучий інваріант крошки, і найприродніша «правка» (повісити обрізання на
 * `.crumb--flat .txt` загалом) його ламає. Без цієї половини тест схвалив би
 * саме ту реалізацію, проти якої записка застерігає.
 */
const CRUMB_PORT_BASE = 10990;
/** Назва зі скріншота власника — довша за `max-width:150px` у кілька разів. */
const LONG_TITLE = "Business Forum 360 · лендинг і внутрішні сторінки";

describe("довга назва задачі не вилазить із крошки", () => {
  let tool;
  let statics;
  let browser;
  let base;

  before(async () => {
    const { dir } = taskFixture({ html: PAGE });
    secondIteration(dir);
    tool = await startServer(dir, { portBase: CRUMB_PORT_BASE, title: LONG_TITLE, liga: true });
    const res = await fetch(`${tool.url}/api/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ build_only: true }),
    });
    const built = await res.json();
    assert.ok(built.ok, `публікація не зібралась: ${JSON.stringify(built)}`);
    statics = await staticServer(built.dir, CRUMB_PORT_BASE + 500);
    base = statics.base;
    browser = await chromium.launch();
  });

  after(async () => {
    await browser?.close();
    statics?.child.kill();
    tool?.child.kill();
  });

  /**
   * ⛔ ЧОМУ ПІКСЕЛІ, А НЕ ПРЯМОКУТНИКИ. Перша редакція цього тесту міряла
   * `getBoundingClientRect()` крошки й тексту — рівно так, як пропонувала
   * записка. Вона була ЗЕЛЕНА на несправному коді, і це не випадковість:
   * `max-width` дає боксу 150px, `getBoundingClientRect` віддає саме БОКС, а
   * гліфи, що не влізли, малюються ПОВЕРХ сусідів уже на етапі фарбування.
   * Тобто прямокутниками цей дефект не видно в принципі, і такий охоронець був
   * би фікцією — він не міг би впасти.
   *
   * Тому міряємо фарбу. Ховаємо `visibility:hidden` усе в смузі (видимість
   * зберігає розкладку, тобто нічого не зсувається) і лишаємо видимим ОДИН
   * вузол — назву задачі. Далі два знімки однієї й тієї ж смужки праворуч від
   * крошки: з назвою і без неї. Збіглись байт-у-байт → праворуч від крошки
   * назва не малює нічого. Розійшлись → малює, тобто накриває сусідів.
   *
   * Свідок проти вакууму — другий знімок, уже ВСЕРЕДИНІ крошки: там байти
   * ЗОБОВʼЯЗАНІ розійтись. Без нього тест був би зелений і на порожній смузі,
   * і на зламаному способі вимірювання.
   */
  test("назва не малює нічого праворуч від крошки", async (t) => {
    const ctx = await browser.newContext({ viewport: VIEW });
    const page = await ctx.newPage();
    t.after(() => ctx.close());
    await page.goto(base);
    await page.fill("#agpass", PW);
    await page.click("#authform button");
    await page.locator("#bar .bar").waitFor();

    /* Видимість, а не `display`: `display:none` прибрав би вузли з потоку,
       крошка ітерації поїхала б ліворуч, і знімки розійшлись би від зсуву
       розкладки, а не від дефекту. */
    const geom = await page.evaluate(() => {
      const style = document.createElement("style");
      style.id = "ink-probe";
      style.textContent = "#bar *{visibility:hidden}"
        + "#bar .crumb--task .txt{visibility:visible}";
      document.head.appendChild(style);
      const c = document.querySelector("#bar .crumb--task").getBoundingClientRect();
      const t2 = document.querySelector("#bar .crumb--task .txt").getBoundingClientRect();
      return { crumb: { x: c.x, y: c.y, w: c.width, h: c.height },
               txt: { x: t2.x, y: t2.y, w: t2.width, h: t2.height },
               sw: document.querySelector("#bar .crumb--task .txt").scrollWidth,
               cw: document.querySelector("#bar .crumb--task .txt").clientWidth };
    });
    /* Свідок проти закороткої фікстури: назва мусить не влазити у свій бокс,
       інакше перевіряти нема чого. */
    assert.ok(geom.sw > geom.cw,
      `назва влазить у бокс (${geom.sw} ≤ ${geom.cw}) — фікстура закоротка`);

    const round = (r) => ({ x: Math.round(r.x), y: Math.round(r.y),
                            width: Math.round(r.w), height: Math.round(r.h) });
    // Смужка ПРАВОРУЧ від крошки — саме туди вилазили гліфи на скріншоті власника.
    const right = round({ x: geom.crumb.x + geom.crumb.w + 1, y: geom.crumb.y,
                          w: 220, h: geom.crumb.h });
    const inside = round(geom.txt);

    const withName = { right: await page.screenshot({ clip: right }),
                       inside: await page.screenshot({ clip: inside }) };
    await page.evaluate(() => {
      document.getElementById("ink-probe").textContent += "#bar .crumb--task .txt{visibility:hidden}";
    });
    const blank = { right: await page.screenshot({ clip: right }),
                    inside: await page.screenshot({ clip: inside }) };

    assert.ok(!withName.inside.equals(blank.inside),
      "усередині крошки нічого не намальовано — міряємо не те, тест вакуумний");
    assert.ok(withName.right.equals(blank.right),
      "назва задачі малює гліфи ПРАВОРУЧ від своєї крошки — накриває сусідів");
  });

  test("повну назву несе title, тож обрізане можна прочитати", async (t) => {
    const ctx = await browser.newContext({ viewport: VIEW });
    const page = await ctx.newPage();
    t.after(() => ctx.close());
    await page.goto(base);
    await page.fill("#agpass", PW);
    await page.click("#authform button");
    await page.locator("#bar .bar").waitFor();
    assert.equal(await page.locator("#bar .crumb--task").getAttribute("title"), LONG_TITLE);
  });
});

/**
 * Назва задачі НЕ обрізається, коли вона звичайної довжини (0.32.0). Раніше `.crumb{max-width:110px}` різав крошку ще до
 * `.txt{max-width:150px}`, і «Онбординг клієнта» (17 знаків) ставала «Онбординг клі…». Власна фікстура з такою назвою:
 * у наборі вище назва «Фікстура» закоротка, щоб це зловити.
 */
const TITLE_PORT_BASE = 31000;
const MID_TITLE = "Онбординг клієнта";

describe("назва задачі звичайної довжини не обрізається в смузі превʼю", () => {
  let tool;
  let statics;
  let browser;
  let base;

  before(async () => {
    const { dir } = taskFixture({ html: PAGE });
    secondIteration(dir);
    tool = await startServer(dir, { portBase: TITLE_PORT_BASE, title: MID_TITLE, liga: true });
    const res = await fetch(`${tool.url}/api/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ build_only: true }),
    });
    const built = await res.json();
    assert.ok(built.ok, `публікація не зібралась: ${JSON.stringify(built)}`);
    statics = await staticServer(built.dir, TITLE_PORT_BASE + 500);
    base = statics.base;
    browser = await chromium.launch();
  });

  after(async () => {
    await browser?.close();
    statics?.child.kill();
    tool?.child.kill();
  });

  test("scrollWidth не більший за clientWidth", async (t) => {
    const ctx = await browser.newContext({ viewport: VIEW });
    const page = await ctx.newPage();
    t.after(() => ctx.close());
    await page.goto(base);
    await page.fill("#agpass", PW);
    await page.click("#authform button");
    await page.locator("#bar .bar").waitFor();
    const m = await page.evaluate(() => {
      const el = document.querySelector("#bar .crumb--task .txt");
      const crumb = el.closest(".crumb--task");
      return { text: el.textContent, sw: el.scrollWidth, cw: el.clientWidth,
               csw: crumb.scrollWidth, ccw: crumb.clientWidth,
               over: el.getBoundingClientRect().right - crumb.getBoundingClientRect().right };
    });
    assert.equal(m.text, MID_TITLE);
    assert.ok(m.cw > 0, "вузол назви без ширини — міряємо не те");
    assert.ok(m.sw <= m.cw, `назву обрізано: ${m.sw} > ${m.cw}`);
    /* Друга половина — КРОШКА: `.crumb{max-width:110px;overflow:hidden}` різав її зовні, а `.txt` зсередини цього не бачить. */
    assert.ok(m.csw <= m.ccw, `крошку обрізано: ${m.csw} > ${m.ccw}`);
    assert.ok(m.over <= 0.5, `текст виходить за крошку на ${m.over}px`);
  });
});
