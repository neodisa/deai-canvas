/**
 * Відповіді в коментаторі (0.34, Task 3): `reply/editReply/removeReply` лише з хостом, `onReply` до першого `onChange`
 * з відповіддю, злиття відповідей «у польоті» із зовнішнім оновленням, рядок «N replies» у власній панелі.
 * Сервер не потрібен: голий бандл `app/vendor/comment-layer.min.js` і сховище в памʼяті.
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

const C = (id, extra = {}) => ({ id, author: "А", text: "т-" + id, status: "open", ts: "01.01.2026 10:00",
  meta: { seq: +id.replace(/\D/g, "") || 1, version: "2" }, ...extra });

/** `holdSave` — `save` повертає проміс, що його розв'язує тест (`window.__release()`); `window.__subscribe` — зовнішнє оновлення. */
async function boot({ withHost = true, seed = [], holdSave = false, syncNotify = false } = {}) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(({ withHost, seed, holdSave, syncNotify }) => {
    window.__ev = [];
    const mem = JSON.parse(JSON.stringify(seed));
    window.__saves = [];
    window.__resolvers = [];
    let sub = null;
    const store = {
      load: () => mem.slice(),
      subscribe: (cb) => { sub = cb; },
      save: (l) => {
        window.__saves.push(JSON.stringify(l));
        mem.length = 0; mem.push(...JSON.parse(JSON.stringify(l)));
        // як local-adapter.js: оптимістично сповіщає підписника просто всередині save
        if (syncNotify && sub) sub(JSON.parse(JSON.stringify(l)));
        if (holdSave) return new Promise((res, rej) => window.__resolvers.push({ res, rej }));
      },
    };
    window.__mem = mem;
    window.__ext = (list) => sub(JSON.parse(JSON.stringify(list)));
    window.__release = () => { window.__resolvers.splice(0).forEach((r) => r.res()); };
    window.__settle = (i, ok) => { const r = window.__resolvers[i]; if (ok) r.res(); else r.rej(new Error("збій запису")); };
    const host = withHost ? {
      onReady: () => window.__ev.push(["ready"]),
      onChange: (s) => window.__ev.push(["change", s]),
      onReply: (a) => window.__ev.push(["reply", a]),
    } : undefined;
    window.CommentLayer.init({ projectId: "t", storage: store, version: "2", user: { name: "Тест" }, host });
  }, { withHost, seed, holdSave, syncNotify });
  return page;
}
const snap = (page) => page.evaluate(() => window.CommentLayer.snapshot());
const kinds = (page) => page.evaluate(() => window.__ev.map((e) => e[0]));
const cardHTML = (page, id) => page.evaluate((i) => {
  window.CommentLayer.open();
  return document.querySelector("[data-comment-layer]").shadowRoot.querySelector("#c" + i)?.outerHTML ?? null;
}, id);

test("з host: reply емітить onReply до onChange з відповіддю; сховище без _pending; snapshot — копія", async () => {
  const page = await boot({ seed: [C("c1")] });
  await page.evaluate(() => { window.__ev.length = 0; });
  const rid = await page.evaluate(() => window.CommentLayer.reply("c1", "  Привіт  "));
  assert.ok(rid);
  const ev = await page.evaluate(() => window.__ev.map((e) => [e[0], e[0] === "change" ? (e[1].comments[0].replies || []).map((r) => r.id) : e[1]]));
  const iReply = ev.findIndex((e) => e[0] === "reply");
  const iFirstWith = ev.findIndex((e) => e[0] === "change" && e[1].includes(rid));
  assert.ok(iReply >= 0 && iFirstWith >= 0, JSON.stringify(ev));
  assert.ok(iReply < iFirstWith, "onReply має йти раніше: " + JSON.stringify(ev));
  assert.deepEqual(ev[iReply][1], { comment: "c1", reply: rid });
  await page.waitForFunction(() => window.__saves.length > 0);
  const saved = await page.evaluate(() => window.__saves[window.__saves.length - 1]);
  assert.ok(!saved.includes("_pending"), saved);
  const c = JSON.parse(saved)[0];
  assert.equal(c.replies.length, 1);
  assert.equal(c.replies[0].text, "Привіт");
  assert.equal(c.replies[0].author, "Тест");
  assert.match(c.replies[0].ts, /^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$/);
  assert.ok(!("agent" in c.replies[0]));
  // snapshot — копія
  await page.evaluate(() => { const s = window.CommentLayer.snapshot(); s.comments[0].replies[0].text = "ЗЛАМАНО"; s.comments[0].replies.push({ id: "x" }); });
  const s2 = await snap(page);
  assert.equal(s2.comments[0].replies.length, 1);
  assert.equal(s2.comments[0].replies[0].text, "Привіт");
  assert.ok(!("_pending" in s2.comments[0].replies[0]));
  const gc = await page.evaluate(() => { const g = window.CommentLayer.getComments(); g[0].replies[0].text = "Z"; return window.CommentLayer.getComments()[0].replies[0].text; });
  assert.equal(gc, "Привіт");
  await page.close();
});

test("відмови: reply на закритий/невідомий/порожній → null; editReply/removeReply на невідоме → false", async () => {
  const page = await boot({ seed: [C("c1"), C("c2", { status: "resolved" }), C("c3", { replies: [{ id: "r1", author: "А", text: "a", ts: "01.01.2026 10:00" }] })] });
  const r = await page.evaluate(() => {
    const L = window.CommentLayer;
    return [L.reply("c2", "x"), L.reply("nope", "x"), L.reply("c1", "   "), L.reply("c1", null),
      L.editReply("nope", "r1", "x"), L.editReply("c3", "nope", "x"), L.editReply("c3", "r1", " "),
      L.removeReply("nope", "r1"), L.removeReply("c3", "nope"), L.removeReply("c1", "r1")];
  });
  assert.deepEqual(r, [null, null, null, null, false, false, false, false, false, false]);
  assert.equal((await snap(page)).comments.find((c) => c.id === "c2").replies, undefined);
  await page.close();
});

test("editReply ставить editedTs і зберігає; removeReply прибирає і зберігає", async () => {
  const page = await boot({ seed: [C("c1", { replies: [{ id: "r1", author: "А", text: "a", ts: "01.01.2026 10:00" }, { id: "r2", author: "Б", text: "b", ts: "01.01.2026 10:05" }] })] });
  assert.equal(await page.evaluate(() => window.CommentLayer.editReply("c1", "r1", " нова ")), true);
  await page.waitForFunction(() => window.__mem[0].replies[0].text === "нова");
  const m = await page.evaluate(() => window.__mem[0].replies[0]);
  assert.match(m.editedTs, /^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$/);
  assert.equal(await page.evaluate(() => window.CommentLayer.removeReply("c1", "r2")), true);
  await page.waitForFunction(() => window.__mem[0].replies.length === 1);
  assert.deepEqual(await page.evaluate(() => window.__mem[0].replies.map((r) => r.id)), ["r1"]);
  assert.deepEqual((await snap(page)).comments[0].replies.map((r) => r.id), ["r1"]);
  await page.close();
});

test("без host: reply → null, editReply/removeReply → false; «N replies» на картці; без replies розмітка та сама", async () => {
  const rs = (n) => Array.from({ length: n }, (_, i) => ({ id: "r" + i, author: "А", text: "a", ts: "01.01.2026 10:0" + i }));
  const page = await boot({ withHost: false, seed: [C("c1", { replies: rs(2) }), C("c2", { replies: rs(1) }), C("c3"), C("c4", { replies: [] })] });
  assert.deepEqual(await page.evaluate(() => [window.CommentLayer.reply("c1", "x"), window.CommentLayer.editReply("c1", "r0", "x"), window.CommentLayer.removeReply("c1", "r0")]), [null, false, false]);
  const h1 = await cardHTML(page, "c1"), h2 = await cardHTML(page, "c2");
  assert.match(h1, /<div class="when">2 replies<\/div>/);
  assert.match(h2, /<div class="when">1 reply<\/div>/);
  // та сама картка (той самий id і seq) того ж бандла: без поля replies і з порожнім replies — байт-у-байт
  const h3 = await cardHTML(page, "c3");
  assert.ok(!/repl/.test(h3));
  const page2 = await boot({ withHost: false, seed: [C("c3", { meta: { seq: 3, version: "2" } })] });
  const page3 = await boot({ withHost: false, seed: [C("c3", { meta: { seq: 3, version: "2" }, replies: [] })] });
  const bare = await cardHTML(page2, "c3");
  assert.equal(await cardHTML(page3, "c3"), bare);
  assert.equal(h3, bare);
  await page3.close();
  await page.close(); await page2.close();
});

test("злиття: відповідь у польоті переживає зовнішнє оновлення без неї; після save — не pending", async () => {
  const page = await boot({ seed: [C("c1"), C("c2")], holdSave: true });
  const rid = await page.evaluate(() => window.CommentLayer.reply("c1", "у польоті"));
  assert.ok(rid);
  assert.equal((await snap(page)).comments[0].pending, true);
  // зовнішній список: c2 змінився, c1 є, але без відповіді
  await page.evaluate(() => window.__ext([
    { id: "c1", author: "А", text: "т-c1", status: "open", ts: "01.01.2026 10:00", meta: { seq: 1, version: "2" } },
    { id: "c2", author: "А", text: "ЗМІНЕНО", status: "open", ts: "01.01.2026 10:00", meta: { seq: 2, version: "2" } }]));
  let s = await snap(page);
  const c1 = s.comments.find((c) => c.id === "c1");
  assert.deepEqual(c1.replies.map((r) => r.id), [rid]);
  assert.equal(s.comments.find((c) => c.id === "c2").text, "ЗМІНЕНО");
  // зовнішня копія вже має чужу відповідь і стару версію нашої: чужа лишається, наша — локальна, порядок за ts
  await page.evaluate((rid) => window.__ext([
    { id: "c1", author: "А", text: "т-c1", status: "open", ts: "01.01.2026 10:00", meta: { seq: 1, version: "2" },
      replies: [{ id: "z", author: "Х", text: "чужа", ts: "01.01.2020 09:00" }, { id: rid, author: "Тест", text: "стара", ts: "01.01.2026 10:00" }] }]), rid);
  s = await snap(page);
  assert.deepEqual(s.comments[0].replies.map((r) => r.id), ["z", rid]);
  assert.equal(s.comments[0].replies[1].text, "у польоті");
  await page.evaluate(() => window.__release());
  await page.waitForFunction(() => window.CommentLayer.snapshot().comments[0].pending === false);
  s = await snap(page);
  assert.equal(s.comments[0].replies.some((r) => r.pending), false);
  // після підтвердження зовнішнє без відповіді її вже не воскрешає
  await page.evaluate(() => window.__ext([{ id: "c1", author: "А", text: "т-c1", status: "open", ts: "01.01.2026 10:00", meta: { seq: 1, version: "2" } }]));
  assert.equal((await snap(page)).comments[0].replies, undefined);
  await page.close();
});

test("carry не копіює відповіді", async () => {
  const page = await boot({ seed: [C("c1", { replies: [{ id: "r1", author: "А", text: "a", ts: "01.01.2026 10:00" }] })] });
  await page.evaluate(() => window.CommentLayer.carry("c1"));
  await page.waitForFunction(() => window.__mem.length === 2);
  const [orig, copy] = await page.evaluate(() => window.__mem);
  assert.equal(orig.replies.length, 1);
  assert.equal(copy.replies, undefined);
  assert.equal(copy.meta.carriedFrom.id, "c1");
  await page.close();
});

test("agent: true у відповіді переживає reply і збереження без змін", async () => {
  const seedReply = { id: "ra", author: "Агент", text: "від агента", ts: "01.01.2026 09:00", agent: true };
  const page = await boot({ seed: [C("c1", { replies: [seedReply] })] });
  const rid = await page.evaluate(() => window.CommentLayer.reply("c1", "людська"));
  await page.waitForFunction(() => window.__mem[0].replies.length === 2);
  const reps = await page.evaluate(() => window.__mem[0].replies);
  assert.deepEqual(reps[0], seedReply);
  assert.equal(reps[1].id, rid);
  assert.ok(!("agent" in reps[1]));
  assert.equal((await snap(page)).comments[0].replies[0].agent, true);
  await page.close();
});

const PEND = (page) => page.evaluate(() => window.CommentLayer.snapshot().comments[0]);
const EXT = (extra = {}) => ({ id: "c1", author: "А", text: "т-c1", status: "open", ts: "01.01.2026 10:00", meta: { seq: 1, version: "2" }, ...extra });

test("гонка записів: старіший save не знімає «в польоті» нової відповіді; провал нового не губить її", async () => {
  const page = await boot({ seed: [C("c1")], holdSave: true });
  const a = await page.evaluate(() => window.CommentLayer.reply("c1", "A"));
  const b = await page.evaluate(() => window.CommentLayer.reply("c1", "B"));
  assert.ok(a && b);
  assert.equal(await page.evaluate(() => window.__resolvers.length), 2);
  await page.evaluate(() => window.__settle(0, true));
  await page.evaluate(() => new Promise((r) => setTimeout(r, 50)));
  await page.evaluate(() => window.__settle(1, false));
  await page.evaluate(() => new Promise((r) => setTimeout(r, 50)));
  let c = await PEND(page);
  assert.equal(c.pending, true);
  assert.equal(c.replies.find((r) => r.id === b).text, "B");
  // зовнішня копія без B: B лишається
  await page.evaluate((e) => window.__ext([e]), EXT());
  c = await PEND(page);
  assert.ok(c.replies.some((r) => r.id === b), JSON.stringify(c.replies));
  await page.close();
});

test("надгробок: видалена у польоті відповідь не воскресає зі застарілої зовнішньої копії", async () => {
  const rr = { id: "r1", author: "А", text: "a", ts: "01.01.2026 10:00" };
  const page = await boot({ seed: [C("c1", { replies: [rr] })], holdSave: true });
  assert.equal(await page.evaluate(() => window.CommentLayer.removeReply("c1", "r1")), true);
  await page.evaluate((e) => window.__ext([e]), EXT({ replies: [rr] }));
  assert.equal((await PEND(page)).replies.length, 0);
  await page.evaluate((e) => window.__ext([e]), EXT({ replies: [rr] }));   // і вдруге
  assert.equal((await PEND(page)).replies.length, 0);
  assert.ok(!JSON.stringify(await PEND(page)).includes("_goneReplies"));
  await page.evaluate(() => window.__release());
  await page.waitForFunction(() => window.CommentLayer.snapshot().comments[0].pending === false);
  await page.evaluate((e) => window.__ext([e]), EXT());
  assert.ok(!((await PEND(page)).replies || []).some((r) => r.id === "r1"));
  const saved = await page.evaluate(() => JSON.stringify(window.__mem));
  assert.ok(!saved.includes("_goneReplies"));
  await page.close();
});

test("порядок із реалістичним сховищем: onReply передує КОЖНОМУ change з відповіддю (save сповіщає синхронно)", async () => {
  const page = await boot({ seed: [C("c1")], syncNotify: true });
  await page.evaluate(() => { window.__ev.length = 0; });
  const rid = await page.evaluate(() => window.CommentLayer.reply("c1", "x"));
  const ev = await page.evaluate(() => window.__ev.map((e) => [e[0], e[0] === "change" ? (e[1].comments[0].replies || []).map((r) => r.id) : null]));
  const iReply = ev.findIndex((e) => e[0] === "reply");
  const withIdx = ev.map((e, i) => (e[0] === "change" && e[1].includes(rid) ? i : -1)).filter((i) => i >= 0);
  assert.ok(iReply >= 0 && withIdx.length >= 1, JSON.stringify(ev));
  assert.ok(withIdx.every((i) => i > iReply), JSON.stringify(ev));
  await page.close();
});

test("биті записи в replies (null, число) відкидаються, нічого не кидає", async () => {
  const page = await boot({ seed: [C("c1", { replies: [null, 5, { id: "r1", author: "А", text: "a", ts: "01.01.2026 10:00" }] })] });
  assert.deepEqual((await snap(page)).comments[0].replies.map((r) => r.id), ["r1"]);
  assert.ok(await page.evaluate(() => window.CommentLayer.reply("c1", "ok")));
  await page.waitForFunction(() => window.__mem[0].replies.length === 2);
  assert.deepEqual(await page.evaluate(() => window.__mem[0].replies.map((r) => r.id).length), 2);
  await page.close();
});

test("рядок «N replies» є і на закритій картці", async () => {
  const page = await boot({ withHost: false, seed: [C("c1", { status: "resolved", replies: [{ id: "r1", author: "А", text: "a", ts: "01.01.2026 10:00" }] })] });
  await page.evaluate(() => window.CommentLayer.open());
  await page.evaluate(() => { const sh = document.querySelector("[data-comment-layer]").shadowRoot; [...sh.querySelectorAll("button")].find((b) => /^Closed/.test(b.textContent)).click(); });
  const html = await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.innerHTML);
  assert.match(html, /<div class="when">1 reply<\/div>/);
  assert.match(html, /badge resolved/);
  await page.close();
});
