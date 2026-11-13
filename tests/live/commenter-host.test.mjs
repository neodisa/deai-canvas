/**
 * Режим хоста коментатора (Deai 0.26.0): з `init({host})` ручка й панель коментатора сховані, C/P/H він не слухає,
 * про все повідомляє колбеками, а хост керує ним методами. Без `host` — як до 0.26.0. Сервер не потрібен: голий бандл
 * `app/vendor/comment-layer.min.js` на сторінці з `setContent`.
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
  + '<p id="p">Абзац для коментаря</p></main></body></html>';

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** `seed` — коментарі, що вже лежать у сховищі; `withHost` — чи передати `host`. */
async function boot({ withHost, seed = [], version = "2" }) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(({ withHost, seed, version }) => {
    window.__ev = [];
    const mem = seed.slice();
    const store = { load: () => mem.slice(), save: (l) => { mem.length = 0; mem.push(...l); } };
    window.__mem = mem;
    const host = withHost ? {
      onReady: () => window.__ev.push(["ready"]),
      onChange: (s) => window.__ev.push(["change", s]),
      onSelect: (id) => window.__ev.push(["select", id]),
      onMode: (on) => window.__ev.push(["mode", on]),
    } : undefined;
    window.CommentLayer.init({ projectId: "t", storage: store, version, user: { name: "Тест" }, host });
  }, { withHost, seed, version });
  return page;
}
const root = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(s);
  return el ? getComputedStyle(el).display : null;
}, sel);
const lastSnap = (page) => page.evaluate(() => [...window.__ev].reverse().find((e) => e[0] === "change")?.[1]);
async function addComment(page, text) {
  await page.click("#p");
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await page.evaluate((t) => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .save").click());
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text);
}

test("без host: ручку видно, клавіша C вмикає режим (поведінка до 0.26.0)", async () => {
  const page = await boot({ withHost: false });
  assert.notEqual(await root(page, ".handle"), "none");
  await page.keyboard.press("c");
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".modes.show")), true);
  await page.close();
});

test("з host: ручка й панель сховані, C не діє, ready і change приходять", async () => {
  const page = await boot({ withHost: true });
  assert.equal(await root(page, ".handle"), "none");
  assert.equal(await root(page, ".panel"), "none");
  const kinds = await page.evaluate(() => window.__ev.map((e) => e[0]));
  assert.deepEqual(kinds.slice(0, 2), ["ready", "change"]);
  const s = await lastSnap(page);
  assert.equal(s.version, "2");
  assert.equal(s.iteration, "2");
  assert.deepEqual(s.comments, []);
  await page.keyboard.press("c");
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".modes.show")), false);
  assert.equal(await page.evaluate(() => document.body.classList.contains("cl-shift")), false);
  await page.close();
});

test("з host: режим через API, пін через форму, знімок без fp/htmlSnapshot, select і Escape", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  assert.deepEqual(await page.evaluate(() => window.__ev.filter((e) => e[0] === "mode").map((e) => e[1])), [true]);
  assert.notEqual(await root(page, ".modes.show"), null);
  await addComment(page, "Зробити ширшим");
  const s = await lastSnap(page);
  assert.equal(s.comments.length, 1);
  const c = s.comments[0];
  assert.equal(c.n, 1);
  assert.equal(c.scope, "current");
  assert.equal(c.where, "here");
  assert.equal(c.text, "Зробити ширшим");
  assert.equal("fp" in c, false);
  assert.equal("htmlSnapshot" in c, false);
  assert.equal("_el" in c, false);
  await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".pin").click());
  assert.deepEqual(await page.evaluate(() => window.__ev.filter((e) => e[0] === "select").map((e) => e[1])), [c.id]);
  assert.equal(await root(page, ".panel"), "none");
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => window.__ev.filter((e) => e[0] === "mode").at(-1)[1]), false);
  await page.close();
});

test("з host: editComment, resolve/reopen, togglePins, openShot", async () => {
  const shot = "data:image/png;base64,iVBORw0KGgo=";
  const page = await boot({ withHost: true, seed: [
    { id: "a1", author: "Тест", text: "старий", status: "open", meta: { seq: 1, iteration: "2", version: "2", shot }, ts: "13.11.2026 10:00" },
  ] });
  assert.equal(await page.evaluate(() => window.CommentLayer.editComment("a1", "  новий  ")), true);
  assert.equal((await lastSnap(page)).comments[0].text, "новий");
  assert.equal(await page.evaluate(() => window.CommentLayer.editComment("a1", "   ")), false);
  await page.evaluate(() => window.CommentLayer.resolveComment("a1"));
  assert.equal((await lastSnap(page)).comments[0].status, "resolved");
  await page.evaluate(() => window.CommentLayer.reopenComment("a1"));
  assert.equal((await lastSnap(page)).comments[0].status, "open");
  assert.equal(await page.evaluate(() => window.CommentLayer.togglePins()), true);
  assert.equal((await lastSnap(page)).pinsHidden, true);
  await page.evaluate(() => window.CommentLayer.openShot("a1"));
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".cllb img")), true);
  await page.close();
});

test("з host: пін попередньої ітерації — scope earlier, carry переносить копією в поточну", async () => {
  const page = await boot({ withHost: true, version: "3", seed: [
    { id: "o1", author: "Тест", text: "з другої", status: "open", meta: { seq: 4, iteration: "2", version: "2" }, ts: "12.11.2026 09:00" },
  ] });
  const before = (await lastSnap(page)).comments;
  assert.deepEqual(before.map((c) => [c.id, c.scope, c.iter]), [["o1", "earlier", "2"]]);
  await page.evaluate(() => window.CommentLayer.carry("o1"));
  const after = (await lastSnap(page)).comments;
  assert.equal(after.length, 2);
  assert.equal(after.find((c) => c.id !== "o1").scope, "current");
  assert.equal(after.find((c) => c.id === "o1").scope, "earlier");
  await page.close();
});
