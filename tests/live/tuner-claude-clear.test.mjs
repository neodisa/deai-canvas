/**
 * Живий тест: Клод застосував пакет тюнера й очистив його — вкладка канваса
 * НЕ повертає його назад і НЕ показує «чекає на Клода» на застосованому.
 *
 * ⛔ Звідки (fb-22092026-c11bff, 22.09.2026, задача lu-auth). Записка
 * звинувачувала сервер у кеші в памʼяті — його там немає: GET читає файл щоразу.
 * Механізм у БРАУЗЕРІ: вкладка читає пакет один раз на старті (`loadTune`),
 * тримає `ready` у памʼяті й пише ПОВНИЙ пакет на кожен поворот ручки. Клод
 * очистив файл — перший же запис вкладки клав старий пакет назад.
 *
 * Дві лінії захисту — два тести, бо ловлять різне:
 *   A (повернення у вкладку) — `syncTuneFromDisk` на `focus`/`visibilitychange`.
 *     МУТАЦІЯ: прибрати обидва слухачі. Червоніє A: позначка «готово — чекає
 *     на Клода» висить далі, хоча пакета на диску вже немає.
 *   B (вкладка й не втрачала фокусу) — `base_rev` у `saveTune` + 409 на сервері.
 *     МУТАЦІЯ: не слати `base_rev`. Червоніє B: поворот ручки відроджує
 *     очищений пакет на диску разом зі старою правкою.
 *     МУТАЦІЯ: у гілці 409 не кликати `adoptTune`. Червоніє B: список змін у
 *     панелі показує правку, якої на диску немає.
 *
 * Чому живий: обидві вади — про стан ВКЛАДКИ проти стану диска, тобто про
 * `fetch`, події вікна й перемальовку панелі разом. Юніт сервера (`test_serve`)
 * стереже лише половину — відмову; що вкладка з нею зробить, видно тільки тут.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { existsSync, writeFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 11790;
const VIEW = { width: 1400, height: 900 };

/* Та сама проста сторінка, що в `tuner.test.mjs`: відступ `#target` береться з
   правила класу, тож поворот ручки дає 16px → 17px. Градієнт — щоб знімок не
   числився порожнім і вхід не замовив зʼємку. */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#wrap{margin:30px;padding:40px;background:#fff;display:flex;gap:24px}
.card{margin:0;padding:16px;background:#eef;width:260px;height:160px;color:#123456}
</style></head><body>
<div id="wrap" class="row"><p id="target" class="card">Картка ${id}</p></div>
</body></html>`;

const SEL = "body > div.row > p.card";
/** Пакет «дизайнер натиснув «Надіслати Клоду»» — формат `packageJSON`. */
const READY_PKG = {
  kind: "design-canvas.tuner.recommendations", version: 1, status: "ready",
  page: null, note: "", editCount: 1, instructions: [],
  elements: [{ page: "it1/holovna", selector: SEL, label: "p.card",
    trail: ["body", "div.row", "p.card"], text: "Картка holovna",
    edits: [{ prop: "padding-top", from: "16px", to: "30px", rule: ".card", raw: "16px",
      token: null, tokenValue: null, verdict: "hardcode", hint: [] }] }],
};

async function openInspector(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  await page.click('#hud [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on === true, null, { timeout: 3000 });
  return page;
}

async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
}

/** Клод, застосувавши пакет, очищає його — тим запитом, який написаний у самому
 *  пакеті. З node, а НЕ зі сторінки: це інший учасник, не ця вкладка. */
const claudeClears = (url) => fetch(`${url}/api/tuner`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ action: "clear" }),
}).then((r) => r.json());

const readyShown = (page) => page.evaluate(() => !!document.querySelector("#insp-panel .insp-ready"));
const changeRows = (page) => page.evaluate(() =>
  document.querySelectorAll('#insp-panel [data-act="insptunedrop"]').length);

async function until(fn, want, ms = 4000) {
  const end = Date.now() + ms;
  let got;
  while (Date.now() < end) {
    got = await fn();
    if (got === want) return got;
    await new Promise((r) => setTimeout(r, 50));
  }
  return got;
}

test("A: Клод очистив пакет — на поверненні у вкладку «чекає на Клода» зникає", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  writeFileSync(path.join(dir, ".dc-tuner.json"), JSON.stringify(READY_PKG, null, 1));
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);
  await pin(page, "#target");

  /* Свідок: позначка СПРАВДІ висіла. Без цього тест зеленів би й тоді, коли
     панель не показує стан пакета взагалі. */
  assert.equal(await until(() => readyShown(page), true), true,
    "фікстура не відтворила стан: позначки «чекає на Клода» не було й до очищення");

  const r = await claudeClears(url);
  assert.equal(r.cleared, true, "сервер не очистив пакет — міряти вкладку нема чого");
  assert.equal(existsSync(path.join(dir, ".dc-tuner.json")), false);

  // Дизайнер вертається з термінала у вкладку.
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForFunction(() => document.getElementById("frame")
    ?.contentWindow?.CanvasInspector, null, { timeout: 15000 });
  assert.equal(await until(() => readyShown(page), false), false,
    "пакета на диску вже немає, а вкладка далі каже «чекає на Клода»");
  assert.equal(await changeRows(page), 0,
    "список змін показує правки з пакета, який Клод уже забрав");
  assert.equal(existsSync(path.join(dir, ".dc-tuner.json")), false,
    "повернення у вкладку відродило очищений пакет");
});

test("B: вкладка без фокусу пише поверх очищеного — відмова, диск цілий, сказано вголос", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 50 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);
  await pin(page, "#target");

  const field = '#insp-panel [data-act="insptune"][data-prop="padding-top"]';
  await page.focus(field);
  await page.keyboard.press("ArrowUp");
  const pkgOnDisk = () => page.evaluate(() => fetch("/api/tuner").then((r) => r.json()))
    .then((j) => !!j.package);
  assert.equal(await until(pkgOnDisk, true), true, "перший поворот ручки не доїхав на диск");

  await claudeClears(url);
  /* Жодного `focus`: дизайнер лишився у вкладці й крутить далі. Друга лінія —
     відмова запису. */
  await page.focus(field);
  await page.keyboard.press("ArrowUp");

  assert.equal(await until(() => page.evaluate(() =>
    !!document.querySelector(".cv-ask")), true), true,
  "відмову проковтнуто мовчки — дизайнер не знає, що правка не лягла");
  assert.equal(existsSync(path.join(dir, ".dc-tuner.json")), false,
    "запис вкладки відродив пакет, який Клод уже очистив");
  assert.equal(await until(() => changeRows(page), 0), 0,
    "панель показує правку, якої на диску немає — вкладка не взяла диск");
});
