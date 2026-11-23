/**
 * Форма коментатора в токенах і мові оболонки (0.35): `host.theme` і `host.labels`. Сервер не потрібен: голий бандл
 * `app/vendor/comment-layer.min.js` на сторінці з `setContent`; `host.theme/labels` читають `window.__theme/__labels`,
 * тож тест міняє їх між відкриттями форм (як зміна кольору чи мови в оболонці).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BUNDLE = readFileSync(path.join(ROOT, "app", "vendor", "comment-layer.min.js"), "utf8");
const PAGE = '<!doctype html><html><body style="margin:40px"><main><h1 id="t">Заголовок</h1>'
  + '<p id="p">Абзац для коментаря</p><p id="x"></p></main>'
  + '<script>document.getElementById("x").textContent = "<img src=x onerror=alert(1)>";</script></body></html>';
const SH = 'document.querySelector("[data-comment-layer]").shadowRoot';

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** `theme`/`labels` — що віддадуть `host.theme()`/`host.labels()` (`undefined` — функції в `host` нема взагалі). */
async function boot({ theme, labels, withHost = true } = {}) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(({ theme, labels, withHost }) => {
    window.__theme = theme; window.__labels = labels;
    const host = withHost ? {
      onReady() {}, onChange() {}, onSelect() {}, onMode() {},
      ...(theme === undefined ? {} : { theme: () => window.__theme }),
      ...(labels === undefined ? {} : { labels: () => window.__labels }),
    } : undefined;
    window.CommentLayer.init({ projectId: "t", storage: { load: () => [], save() {} }, version: "2", user: { name: "Тест" }, host });
    window.CommentLayer.setCommentMode(true);
  }, { theme, labels, withHost });
  return page;
}
const q = (page, sel, fn) => page.evaluate(`(() => { const el = ${SH}.querySelector(${JSON.stringify(sel)}); return el ? (${fn})(el) : null; })()`);
const bg = (page, sel) => q(page, sel, "(el) => getComputedStyle(el).backgroundColor");
const open = async (page, sel = "#p") => { await page.click(sel); await page.waitForFunction(`!!${SH}.querySelector('.compose textarea')`); };
const cancel = (page) => page.evaluate(`${SH}.querySelector('.compose .cancel').click()`);
const themeStyles = (page) => page.evaluate(`${SH}.querySelectorAll('style[data-cl-theme]').length`);
const themed = (page) => page.evaluate(`${SH}.querySelector('.root').classList.contains('themed')`);

const THEME = { s2: "rgb(1, 2, 3)", sel: "rgb(4, 5, 6)", "on-sel": "rgb(7, 8, 9)", bogus: "x" };

test("host.theme: фон форми — s2, головна кнопка — sel, клас themed, один <style data-cl-theme>, чужий ключ не ставиться", async () => {
  const page = await boot({ theme: THEME });
  assert.equal(await themed(page), true, "тема прийнята вже при побудові");
  await open(page);
  assert.equal(await bg(page, ".compose"), "rgb(1, 2, 3)");
  assert.equal(await bg(page, ".compose .save"), "rgb(4, 5, 6)");
  assert.equal(await q(page, ".compose .save", "(el) => getComputedStyle(el).color"), "rgb(7, 8, 9)");
  assert.equal(await themeStyles(page), 1);
  await cancel(page); await open(page);
  assert.equal(await themeStyles(page), 1, "повторне відкриття не множить <style>");
  assert.equal(await q(page, ".compose", "(el) => el.style.getPropertyValue('--bogus')"), "");
  assert.equal(await q(page, ".compose", "(el) => el.style.getPropertyValue('--s2')"), "rgb(1, 2, 3)");
  assert.equal(await q(page, ".compose .csel", "(el) => getComputedStyle(el).fontStyle"), "normal", "цитата цілі — без курсиву");
  await page.close();
});

test("host.theme: шкідливе значення відкинуто — ні themed, ні <style>, ні токена", async () => {
  for (const bad of [{ s2: "red;}" }, { s2: "x".repeat(201) }, { s2: "a<b" }, { s2: "url(https://example.com/x)" }, { s2: "red\\" }, { s2: "/*x*/red" }, { s2: "image-set(x 1x)" }, { s2: "@import x" }, { s2: 5 }, { s2: "" }, { bogus: "red" }]) {
    const page = await boot({ theme: bad });
    await open(page);
    assert.equal(await themed(page), false, JSON.stringify(bad).slice(0, 40));
    assert.equal(await themeStyles(page), 0);
    assert.equal(await q(page, ".root", "(el) => el.getAttribute('style') || ''"), "");
    await page.close();
  }
});

test("виняток у host.theme / host.labels — форма відкривається без теми й з англійськими рядками", async () => {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(() => {
    window.CommentLayer.init({ projectId: "t", storage: { load: () => [], save() {} }, version: "2", user: { name: "Тест" },
      host: { onReady() {}, onChange() {}, onSelect() {}, onMode() {},
        theme: () => { throw new Error("x"); }, labels: () => { throw new Error("y"); } } });
    window.CommentLayer.setCommentMode(true);
  });
  await open(page);
  assert.equal(await themed(page), false);
  assert.equal(await themeStyles(page), 0);
  assert.equal(await q(page, ".compose textarea", "(el) => el.getAttribute('placeholder')"), "Leave a change request…");
  assert.equal(await q(page, ".compose .save", "(el) => el.textContent"), "Comment");
  await page.close();
});

test("токени теми — лише на формах: піни, .pinpop і решта шару лишаються з власною палітрою", async () => {
  const page = await boot({ theme: { ...THEME, s1: "rgb(9, 9, 9)", hi: "rgb(250, 0, 0)", "line2": "rgb(0, 250, 0)" } });
  await open(page);
  assert.equal(await bg(page, ".compose"), "rgb(1, 2, 3)", "форма має значення оболонки");
  assert.equal(await bg(page, ".compose textarea"), "rgb(9, 9, 9)", "поле форми — s1 оболонки");
  assert.equal(await bg(page, ".pinpop"), "rgb(21, 24, 29)", ".pinpop не мусить брати --s1 теми");
  assert.equal(await q(page, ".pinpop", "(el) => getComputedStyle(el).borderTopColor"), "rgb(57, 65, 76)");
  assert.equal(await q(page, ".root", "(el) => el.getAttribute('style') || ''"), "", "на .root токенів нема");
  await cancel(page);
  await page.evaluate(() => window.CommentLayer.setMode("multi"));
  assert.equal(await bg(page, ".mcompose"), "rgb(1, 2, 3)");
  assert.equal(await bg(page, ".pinpop"), "rgb(21, 24, 29)");
  // тему прибрано — токенів немає й на формах
  await page.evaluate(() => { window.__theme = {}; window.CommentLayer.setMode("element"); window.CommentLayer.setMode("multi"); });
  assert.equal(await q(page, ".mcompose", "(el) => /--/.test(el.getAttribute('style') || '')"), false, "після зняття теми токени лишилися на .mcompose");
  await page.close();
});

test("host.labels: placeholder і кнопки з підписів; цільовий текст і шаблон екрановані", async () => {
  const labels = { placeholder: "Що змінити?", cancel: "Скасувати", submit: "Коментувати", target: "{tag} «{text}»", quote: "«{text}»", area: "область · {target}",
    multiTitle: "Елементів: {n}", clear: "Очистити" };
  const page = await boot({ labels });
  await open(page);
  assert.equal(await q(page, ".compose textarea", "(el) => el.getAttribute('placeholder')"), "Що змінити?");
  assert.equal(await q(page, ".compose .cancel", "(el) => el.textContent"), "Скасувати");
  assert.equal(await q(page, ".compose .save", "(el) => el.textContent"), "Коментувати");
  assert.equal(await q(page, ".compose .csel", "(el) => el.textContent"), "<p> «Абзац для коментаря»");
  assert.equal(await themeStyles(page), 0, "без theme тема не вмикається");
  assert.equal(await q(page, ".compose .csel", "(el) => !!el.querySelector('code')"), false);
  await cancel(page);
  // зловмисний текст елемента: `<img onerror>` лишається текстом
  await open(page, "#x");
  assert.equal(await q(page, ".compose .csel", "(el) => !!el.querySelector('img')"), false, "<img> із тексту цілі став елементом");
  assert.equal(await q(page, ".compose .csel", "(el) => el.textContent"), "<p> «<img src=x onerror=alert(1)>»");
  await cancel(page);
  // розмітка в самому шаблоні — теж текст
  await page.evaluate(() => { window.__labels = { target: "<b>{tag}</b> {text}", placeholder: '"><i>ph', submit: "<u>ok</u>" }; });
  await open(page);
  assert.equal(await q(page, ".compose .csel", "(el) => !!el.querySelector('b')"), false);
  assert.equal(await q(page, ".compose .csel", "(el) => el.textContent"), "<b><p></b> Абзац для коментаря");
  assert.equal(await q(page, ".compose .save", "(el) => el.textContent"), "<u>ok</u>");
  assert.equal(await q(page, ".compose textarea", "(el) => el.getAttribute('placeholder')"), '"><i>ph');
  assert.equal(await q(page, ".compose", "(el) => !!el.querySelector('i,u')"), false);
  await page.close();
});

test("host.labels: нестрокові й порожні значення — англійський текст; без тексту цілі — лише тег", async () => {
  const page = await boot({ labels: { placeholder: "", cancel: 5, submit: null, target: "{tag} «{text}»" } });
  await open(page, "#x");   // є текст
  assert.equal(await q(page, ".compose textarea", "(el) => el.getAttribute('placeholder')"), "Leave a change request…");
  assert.equal(await q(page, ".compose .cancel", "(el) => el.textContent"), "Cancel");
  assert.equal(await q(page, ".compose .save", "(el) => el.textContent"), "Comment");
  await cancel(page);
  await page.evaluate(() => { document.getElementById("p").textContent = ""; });
  await open(page, "#t");
  await cancel(page);
  await page.evaluate(() => { document.getElementById("t").textContent = ""; document.getElementById("t").style.minHeight = "20px"; });
  await open(page, "#t");
  assert.equal(await q(page, ".compose .csel", "(el) => el.textContent"), "<h1>", "без тексту — самий тег");
  await page.close();
});

test("тема + підписи: тег цілі — чипом <code>", async () => {
  const page = await boot({ theme: THEME, labels: { target: "{tag} «{text}»" } });
  await open(page);
  assert.equal(await q(page, ".compose .csel code", "(el) => el.textContent"), "p");
  await page.close();
});

test("форма «Кілька»: підпис із лічильником, що живий; тема на .mcompose", async () => {
  const page = await boot({ theme: THEME, labels: { multiTitle: "Коментар до елементів: {n}", placeholder: "Що змінити?", clear: "Очистити", submit: "Коментувати" } });
  await page.evaluate(() => window.CommentLayer.setMode("multi"));
  const head = () => q(page, ".mchead", "(el) => el.textContent");
  assert.equal(await head(), "Коментар до елементів: 0");
  await page.click("#t"); await page.click("#p");
  await page.waitForFunction(`${SH}.querySelector('.mccount').textContent === '2'`);
  assert.equal(await head(), "Коментар до елементів: 2");
  assert.equal(await q(page, ".mcta", "(el) => el.getAttribute('placeholder')"), "Що змінити?");
  assert.equal(await q(page, ".mccancel", "(el) => el.textContent"), "Очистити");
  assert.equal(await q(page, ".mcsave", "(el) => el.textContent"), "Коментувати");
  assert.equal(await bg(page, ".mcompose"), "rgb(1, 2, 3)");
  assert.equal(await bg(page, ".mcsave"), "rgb(4, 5, 6)");
  await page.click("#t");   // знімає вибір
  await page.waitForFunction(`${SH}.querySelector('.mccount').textContent === '1'`);
  assert.equal(await head(), "Коментар до елементів: 1");
  // підписи зникли (мова без ключа) — англійський текст вертається, лічильник живий
  await page.evaluate(() => { window.__labels = {}; window.CommentLayer.setMode("element"); window.CommentLayer.setMode("multi"); });
  assert.equal(await head(), "Comment on 0 element(s)");
  await page.click("#t");
  await page.waitForFunction(`${SH}.querySelector('.mccount').textContent === '1'`);
  assert.equal(await q(page, ".mccancel", "(el) => el.textContent"), "Clear");
  await page.close();
});

test("без theme і labels: жодного <style data-cl-theme>, англійські рядки, клас themed немає", async () => {
  for (const opts of [{ withHost: false }, {}, { theme: undefined, labels: undefined }]) {
    const page = await boot(opts);
    await open(page);
    assert.equal(await themeStyles(page), 0);
    assert.equal(await themed(page), false);
    assert.equal(await page.evaluate(`${SH}.querySelectorAll('style').length`), 1, "лишається лише STYLE");
    assert.equal(await q(page, ".compose textarea", "(el) => el.getAttribute('placeholder')"), "Leave a change request…");
    assert.equal(await q(page, ".compose .cancel", "(el) => el.textContent"), "Cancel");
    assert.equal(await q(page, ".compose .csel", "(el) => el.textContent"), "on <p> · “Абзац для коментаря”");
    await page.close();
  }
});

test("зміна теми й мови в оболонці діє на наступну форму", async () => {
  const page = await boot({ theme: { s2: "rgb(1, 2, 3)", sel: "rgb(4, 5, 6)" }, labels: { placeholder: "Що змінити?" } });
  await open(page);
  assert.equal(await bg(page, ".compose"), "rgb(1, 2, 3)");
  await cancel(page);
  await page.evaluate(() => { window.__theme = { s2: "rgb(10, 20, 30)" }; window.__labels = { placeholder: "What should change?" }; });
  await open(page);
  assert.equal(await bg(page, ".compose"), "rgb(10, 20, 30)");
  assert.equal(await q(page, ".compose textarea", "(el) => el.getAttribute('placeholder')"), "What should change?");
  assert.equal(await q(page, ".compose", "(el) => el.style.getPropertyValue('--sel')"), "", "токен, якого більше нема, знято");
  assert.equal(await themeStyles(page), 1);
  await cancel(page);
  await page.evaluate(() => { window.__theme = {}; });
  await open(page);
  assert.equal(await themed(page), false);
  assert.equal(await themeStyles(page), 0);
  await page.close();
});
