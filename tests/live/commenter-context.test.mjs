/**
 * 0.35, баги коментатора 2 і 3.
 * Баг 2: контекст піна (url, маршрут, відбиток, html, ctx) береться в мить ВИБОРУ цілі, а не збереження — SPA може
 *   змінити маршрут, поки людина друкує; ціль, перемальована за цей час, для знімка шукається наново.
 * Баг 3: у режимі хоста сторінку піна визначає тег версії (`"<ітерація>/<сторінка>"`), а не маршрут (у превʼю це адреса Deai);
 *   «показати» в хості ніколи не веде за `meta.url`.
 * Сервер Deai не потрібен: бандл + сховище в памʼяті; сторінка віддається через `page.route`, щоб працював `pushState`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BUNDLE = readFileSync(path.join(ROOT, "app", "vendor", "comment-layer.min.js"), "utf8");
const PAGE = '<!doctype html><html><head><meta charset="utf-8"><title>t</title></head><body style="margin:40px"><main>'
  + '<h1 id="t">Заголовок</h1><p id="p">Абзац для коментаря</p><p id="q">Другий абзац</p></main></body></html>';
const SHOT = "data:image/png;base64,iVBORw0KGgo=";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** `seed` — функція в сторінці (отримує `fp(sel)`), що повертає масив коментарів сховища. */
async function boot({ withHost, version = "1", seed = null, local = false }) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const serve = (r) => r.fulfill({ contentType: "text/html", body: PAGE });
  await page.route("http://dc.test/**", serve);
  await page.route("http://example.com/**", serve);
  await page.goto("http://dc.test/app");
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(({ withHost, version, seed, local }) => {
    window.__calls = [];
    window.html2canvas = (el, opts) => {
      window.__calls.push({ el, opts });
      const c = document.createElement("canvas"); c.width = 20; c.height = 10; return Promise.resolve(c);
    };
    const fp = (sel) => window.CommentLayer._algo.fingerprint(document.querySelector(sel), document.body);
    const mem = seed ? (0, eval)(`(${seed})`)(fp) : [];
    window.__mem = mem;
    window.__ev = [];
    const store = { load: () => mem.slice(), save: (l) => { mem.length = 0; mem.push(...l); } };
    const host = withHost ? { onReady() {}, onChange: (s) => window.__ev.push(s), onSelect() {}, onMode() {} } : undefined;
    window.CommentLayer.init({ projectId: "t", storage: store, version, user: { name: "Тест" }, host, local });
  }, { withHost, version, seed: seed && seed.toString(), local });
  return page;
}
const SH = "document.querySelector('[data-comment-layer]').shadowRoot";
const waitCompose = (page) => page.waitForFunction(`!!${SH}.querySelector('.compose textarea')`);
async function saveCompose(page, text) {
  await page.evaluate((t) => {
    const sh = document.querySelector("[data-comment-layer]").shadowRoot;
    const ta = sh.querySelector(".compose textarea");
    ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true }));
    sh.querySelector(".compose .save").click();
  }, text);
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text);
  return page.evaluate((t) => JSON.parse(JSON.stringify(window.__mem.find((c) => c.text === t))), text);
}
const push = (page, url) => page.evaluate((u) => history.pushState({}, "", u), url);

for (const withHost of [true, false]) {
  const tag = withHost ? "з host" : "без host";

  test(`${tag}, елемент: контекст — з кліку, а не зі збереження (pushState і зміна елемента між ними)`, async () => {
    const page = await boot({ withHost });
    await page.evaluate(() => window.CommentLayer.setCommentMode(true));
    const before = await page.evaluate(() => {
      const el = document.querySelector("#p");
      return { fp: JSON.parse(JSON.stringify(window.CommentLayer._algo.fingerprint(el, document.body))), url: location.href };
    });
    await page.click("#p");
    await waitCompose(page);
    await push(page, "/other#x");
    await page.evaluate(() => { document.querySelector("#p").textContent = "Зовсім інший текст"; });
    const c = await saveCompose(page, "елемент");
    assert.equal(c.meta.route, "/app");
    assert.equal(c.meta.url, before.url);
    // styleHash знято вже з підсвіткою наведення — повний відбиток не порівнюємо; текстові частини міняються разом зі змістом елемента.
    assert.equal(c.fp.text, before.fp.text);
    assert.equal(c.fp.textHash, before.fp.textHash);
    assert.equal(c.fp.text, "абзац для коментаря");
    assert.equal(c.htmlSnapshot.text, "Абзац для коментаря");
    assert.ok(c.htmlSnapshot.outerHTML.includes("Абзац для коментаря"));
    assert.equal(c.meta.mode, undefined, "режим елемента mode не пише");
    assert.equal(c.meta.ctx, undefined, "TD-36: заголовок у командний пін не потрапляє, навіть зняте при виборі");
    assert.equal(JSON.stringify(c).includes("Заголовок"), false);
    await page.close();
  });
}

test("текстовий режим: маршрут і відбиток — з виділення", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => window.CommentLayer.setMode("text"));
  await page.evaluate(() => {
    const p = document.querySelector("#p");
    window.getSelection().selectAllChildren(p);
    p.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
  });
  await waitCompose(page);
  await push(page, "/other#x");
  const c = await saveCompose(page, "текст");
  assert.equal(c.meta.mode, "text");
  assert.equal(c.meta.route, "/app");
  assert.ok(c.meta.url.endsWith("/app"));
  await page.close();
});

test("режим області: маршрут — з моменту виділення", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => window.CommentLayer.setMode("area"));
  const r = await page.evaluate(() => { const b = document.querySelector("#p").getBoundingClientRect(); return { x: b.left, y: b.top }; });
  await page.mouse.move(r.x + 2, r.y + 2);
  await page.mouse.down();
  await page.mouse.move(r.x + 60, r.y + 14, { steps: 4 });
  await page.mouse.up();
  await waitCompose(page);
  await push(page, "/other#x");
  const c = await saveCompose(page, "область");
  assert.equal(c.meta.mode, "area");
  assert.equal(c.meta.route, "/app");
  await page.close();
});

test("multi: маршрут першого вибору; прибрали перший — знімається наново від нового першого", async () => {
  const page = await boot({ withHost: true });
  const saveMulti = async (text) => {
    await page.evaluate((t) => {
      const sh = document.querySelector("[data-comment-layer]").shadowRoot;
      const ta = sh.querySelector(".mcta"); ta.value = t; sh.querySelector(".mcsave").click();
    }, text);
    await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text);
    return page.evaluate((t) => JSON.parse(JSON.stringify(window.__mem.find((c) => c.text === t))), text);
  };
  await page.evaluate(() => window.CommentLayer.setMode("multi"));
  await page.click("#p");
  await push(page, "/b#1");
  await page.click("#q");
  const c1 = await saveMulti("multi-1");
  assert.equal(c1.meta.mode, "multi");
  assert.equal(c1.meta.count, 2);
  assert.equal(c1.meta.route, "/app", "маршрут першого вибору");
  // Другий заход: p (на /b#1), q, далі пересуваємось на /c#2 і прибираємо перший (p) → новий перший q, знято на /c#2.
  await page.click("#p");
  await page.click("#q");
  await push(page, "/c#2");
  await page.click("#p");
  await push(page, "/d#3");
  const c2 = await saveMulti("multi-2");
  assert.equal(c2.meta.count, 1);
  assert.equal(c2.meta.route, "/c#2", "після зняття першого — контекст нового першого, знятий у мить зняття");
  await page.close();
});

test("ціль перемальована між вибором і збереженням: html2canvas отримує приєднаний клон", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  await page.click("#p");
  await waitCompose(page);
  await page.evaluate(() => {
    const p = document.querySelector("#p");
    window.__orig = p;
    const clone = p.cloneNode(true);
    p.replaceWith(clone);
  });
  await saveCompose(page, "перемальовано");
  await page.waitForFunction(() => window.__calls.length > 0);
  const r = await page.evaluate(() => ({ connected: window.__calls[0].el.isConnected, sameAsOld: window.__calls[0].el === window.__orig }));
  assert.equal(r.connected, true, "знімок мусить бути з елемента, що в документі");
  assert.equal(r.sameAsOld, false);
  await page.close();
});

const HOST_SEED = (fp) => [
  { id: "a-poshuk", author: "А", text: "інша сторінка", status: "open", ts: "13.11.2026 10:00",
    fp: fp("#p"), meta: { seq: 1, iteration: "1", version: "1/poshuk", route: "/app", url: "http://dc.test/app" } },
  { id: "b-same", author: "Б", text: "та сама сторінка", status: "open", ts: "13.11.2026 10:01",
    fp: fp("#q"), meta: { seq: 2, iteration: "1", version: "1/holovna", route: "/commented", url: "http://example.com/commented" } },
  { id: "c-nover", author: "В", text: "без тегу, інший маршрут", status: "open", ts: "13.11.2026 10:02",
    fp: fp("#t"), meta: { seq: 3, iteration: "1", route: "/other", url: "http://dc.test/other" } },
  { id: "d-shot", author: "Г", text: "інша сторінка зі знімком", status: "open", ts: "13.11.2026 10:03",
    fp: fp("#t"), meta: { seq: 4, iteration: "1", version: "1/poshuk", route: "/app", url: "http://example.com/poshuk", shot: "data:image/png;base64,iVBORw0KGgo=" } },
];

test("хост: where за тегом версії; піни інших сторінок не малюються", async () => {
  const page = await boot({ withHost: true, version: "1/holovna", seed: HOST_SEED });
  const where = await page.evaluate(() => Object.fromEntries(window.CommentLayer.snapshot().comments.map((c) => [c.id, c.where])));
  assert.equal(where["a-poshuk"], "elsewhere");
  assert.notEqual(where["b-same"], "elsewhere", "та сама сторінка: маршрут не порівнюється");
  assert.equal(where["c-nover"], "elsewhere", "без тегу — старе порівняння маршруту");
  assert.equal(where["d-shot"], "elsewhere");
  const pins = await page.evaluate(`${SH}.querySelectorAll('.pin').length`);
  assert.equal(pins, 2, "малюються лише піни поточної сторінки (b-same, c-nover); a-poshuk і d-shot — ні");
  await page.close();
});

test("хост: focus піна тієї ж сторінки не веде за meta.url, а блимає елементом; інша сторінка — лайтбокс без переходу", async () => {
  const page = await boot({ withHost: true, version: "1/holovna", seed: HOST_SEED });
  const href = await page.evaluate(() => location.href);
  await page.evaluate(() => window.CommentLayer.focus("b-same"));
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(() => location.href), href, "навігації за meta.url бути не може");
  assert.equal(await page.evaluate(() => document.querySelector("#q").classList.contains("cl-el-flash")), true);
  assert.equal(await page.evaluate(`!!${SH}.querySelector('.cllb')`), false);
  await page.evaluate(() => window.CommentLayer.focus("d-shot"));
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(() => location.href), href);
  assert.equal(await page.evaluate(`!!${SH}.querySelector('.cllb img')`), true, "інша сторінка зі знімком — лайтбокс");
  await page.close();
});

test("без host: пін з іншим маршрутом — картка власної панелі показує .otherpage, як і раніше", async () => {
  const page = await boot({ withHost: false, version: "1/holovna", seed: (fp) => [
    { id: "e1", author: "А", text: "інший маршрут", status: "open", ts: "13.11.2026 10:00", fp: fp("#p"),
      meta: { seq: 1, iteration: "1", version: "1/holovna", route: "/other", url: "http://dc.test/other" } },
  ] });
  await page.evaluate(() => window.CommentLayer._openPanel());
  assert.equal(await page.evaluate(`!!${SH}.querySelector('.c .otherpage')`), true);
  await page.close();
});

/** Відбиток елемента без службових класів — еталон для `fp`, знятого при виборі (з наведенням/вибором). */
const cleanFp = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s);
  el.classList.remove("cl-hl", "cl-msel");
  return JSON.parse(JSON.stringify(window.CommentLayer._algo.fingerprint(el, document.body)));
}, sel);

test("елемент з активним наведенням: fp.styleHash і html піна — без cl-hl; клас на елементі лишається", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  await page.click("#p");
  await waitCompose(page);
  assert.equal(await page.evaluate(() => document.querySelector("#p").classList.contains("cl-hl")), true, "захват у _openCompose вже відбувся — клас має бути повернутий на елемент");
  const c = await saveCompose(page, "наведення");
  assert.equal(JSON.stringify(c).includes("cl-hl"), false, "cl-hl не потрапляє в пін");
  const ref = await cleanFp(page, "#p");
  assert.equal(c.fp.styleHash, ref.styleHash);
  assert.deepEqual(c.fp, ref);
  await page.close();
});

test("multi: fp першого елемента і html — без cl-msel; клас на вибраних лишається до збереження", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => window.CommentLayer.setMode("multi"));
  await page.click("#p");
  assert.equal(await page.evaluate(() => document.querySelector("#p").classList.contains("cl-msel")), true);
  await page.click("#q");
  assert.equal(await page.evaluate(() => document.querySelector("#p").classList.contains("cl-msel")), true, "клас повернуто після захвату");
  await page.evaluate(() => {
    const sh = document.querySelector("[data-comment-layer]").shadowRoot;
    sh.querySelector(".mcta").value = "мульті-клас"; sh.querySelector(".mcsave").click();
  });
  await page.waitForFunction(() => window.__mem.some((c) => c.text === "мульті-клас"));
  const c = await page.evaluate(() => JSON.parse(JSON.stringify(window.__mem.find((x) => x.text === "мульті-клас"))));
  assert.equal(JSON.stringify(c).includes("cl-msel"), false);
  const ref = await cleanFp(page, "#p");
  assert.equal(c.fp.styleHash, ref.styleHash);
  const refQ = await cleanFp(page, "#q");
  assert.equal(c.meta.fps.length, 2);
  assert.equal(c.meta.fps[0].styleHash, ref.styleHash, "meta.fps[0] — без cl-msel");
  assert.equal(c.meta.fps[1].styleHash, refQ.styleHash, "meta.fps[1] — без cl-msel");
  await page.close();
});

test("збій захоплення контексту: форма відкривається, multi-лічильник не з'їжджає, пін зберігається старим шляхом", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => { window.CommentLayer._captureAt = () => { throw new Error("збій"); }; });
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  await page.click("#p");
  await waitCompose(page);
  await push(page, "/other#x");
  const c = await saveCompose(page, "без at");
  assert.equal(c.meta.route, "/other#x", "без at — контекст у мить збереження, як до 0.35");
  await page.evaluate(() => window.CommentLayer.setMode("multi"));
  await page.click("#p");
  await page.click("#q");
  assert.equal(await page.evaluate(`${SH}.querySelector('.mccount').textContent`), "2");
  await page.evaluate(() => {
    const sh = document.querySelector("[data-comment-layer]").shadowRoot;
    sh.querySelector(".mcta").value = "multi без at"; sh.querySelector(".mcsave").click();
  });
  await page.waitForFunction(() => window.__mem.some((x) => x.text === "multi без at"));
  await page.close();
});

test("хост: regenerated() не вирішує й не переякорює пін іншої сторінки", async () => {
  const page = await boot({ withHost: true, version: "1/holovna", seed: HOST_SEED });
  const before = await page.evaluate(() => JSON.stringify(window.__mem.find((c) => c.id === "a-poshuk").fp));
  await page.evaluate(() => { document.querySelector("#p").remove(); window.CommentLayer.regenerated(); });
  const after = await page.evaluate(() => { const c = window.__mem.find((x) => x.id === "a-poshuk"); return { status: c.status, fp: JSON.stringify(c.fp) }; });
  assert.equal(after.status, "open");
  assert.equal(after.fp, before);
  await page.close();
});

test("TD-36, позитив: локальний пін тримає заголовок у meta.ctx, знятий при виборі", async () => {
  const page = await boot({ withHost: true, local: true });
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  await page.click("#p");
  await waitCompose(page);
  await push(page, "/other#x");
  const c = await saveCompose(page, "локальний");
  assert.equal(c.meta.route, "/app");
  assert.equal(c.meta.ctx && c.meta.ctx.heading, "Заголовок");
  await page.close();
});
