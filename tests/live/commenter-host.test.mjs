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
async function boot({ withHost, seed = [], version = "2", throwOnChange = false, spy = false, rightInset }) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(({ withHost, seed, version, throwOnChange, spy, rightInset }) => {
    window.__ev = [];
    const mem = seed.slice();
    const store = { load: () => mem.slice(), save: (l) => { mem.length = 0; mem.push(...l); } };
    window.__mem = mem;
    const host = withHost ? {
      ...(rightInset === undefined ? {} : { rightInset: () => rightInset }),
      onReady: () => window.__ev.push(["ready"]),
      onChange: (s) => { if (throwOnChange) throw new Error("хост зламався"); window.__ev.push(["change", s]); },
      onSelect: (id) => window.__ev.push(["select", id]),
      onMode: (on) => window.__ev.push(["mode", on]),
    } : undefined;
    window.__snapCalls = 0;
    if (spy) { const orig = window.CommentLayer.snapshot; window.CommentLayer.snapshot = function (...a) { window.__snapCalls++; return orig.apply(this, a); }; }
    window.CommentLayer.init({ projectId: "t", storage: store, version, user: { name: "Тест" }, host });
  }, { withHost, seed, version, throwOnChange, spy, rightInset });
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
    { id: "o1", author: "Тест", text: "з другої", status: "open", meta: { seq: 4, iteration: "2", version: "2", shot: "data:image/png;base64,iVBORw0KGgo=" }, ts: "12.11.2026 09:00" },
  ] });
  const before = (await lastSnap(page)).comments;
  assert.deepEqual(before.map((c) => [c.id, c.scope, c.iter]), [["o1", "earlier", "2"]]);
  const nEv = await page.evaluate(() => window.__ev.length);
  await page.evaluate(() => window.CommentLayer.focus("o1"));
  assert.equal(await page.evaluate((n) => window.__ev.slice(n).filter((e) => e[0] === "select").length, nEv), 0);
  // Без захисту нечіткий збіг не знайшов би елемента й відкрив би лайтбокс зі знімком чужого піна.
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".cllb")), false);
  await page.evaluate(() => window.CommentLayer.carry("o1"));
  const after = (await lastSnap(page)).comments;
  assert.equal(after.length, 2);
  assert.equal(after.find((c) => c.id !== "o1").scope, "current");
  assert.equal(after.find((c) => c.id === "o1").scope, "earlier");
  assert.equal(after.find((c) => c.id === "o1").where, "here");
  assert.equal(before[0].where, "here");
  await page.close();
});

test("без host: snapshot не викликається ні на init, ні на рендерах", async () => {
  const page = await boot({ withHost: false, spy: true, seed: [
    { id: "a1", author: "Тест", text: "один", status: "open", meta: { seq: 1, iteration: "2", version: "2" }, ts: "13.11.2026 10:00" },
  ] });
  await page.evaluate(() => window.CommentLayer.resolveComment("a1"));
  await page.evaluate(() => window.CommentLayer.reopenComment("a1"));
  assert.equal(await page.evaluate(() => window.__snapCalls), 0);
  await page.close();
});

test("з host: onChange, що кидає виняток, не ламає ні init, ні збереження піна", async () => {
  const page = await boot({ withHost: true, throwOnChange: true });
  assert.deepEqual(await page.evaluate(() => window.__ev.map((e) => e[0])), ["ready"]);
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  await addComment(page, "Пін попри збій хоста");
  assert.equal(await page.evaluate(() => window.__mem.length), 1);
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".pin")), true);
  await page.close();
});

test("з host.rightInset: композер біля правого краю не заходить під панель хоста (правий край ≤ innerWidth − 400)", async () => {
  const page = await boot({ withHost: true, rightInset: 400 });
  await page.evaluate(() => {
    const p = document.createElement("p");
    p.id = "r"; p.textContent = "Біля краю";
    p.style.cssText = "position:absolute;right:10px;top:200px;width:160px;margin:0";
    document.body.appendChild(p);
    window.CommentLayer.setCommentMode(true);
  });
  await page.click("#r");
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose"));
  const edge = await page.evaluate(() => ({
    right: document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose").getBoundingClientRect().right,
    w: window.innerWidth }));
  assert.ok(edge.right <= edge.w - 400 + 0.5, `композер заходить під панель хоста: right=${edge.right}, innerWidth=${edge.w}`);
  await page.close();
});

test("з host: клавіші з поля ХОСТА (textarea поза шаром) не належать коментатору — Esc лишає режим; зі своєї форми — шарований Esc", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => {
    const t = document.createElement("textarea"); t.id = "hostfield"; document.body.appendChild(t);
    window.CommentLayer.setCommentMode(true);
  });
  const modes = () => page.evaluate(() => window.__ev.filter((e) => e[0] === "mode").map((e) => e[1]));
  assert.deepEqual(await modes(), [true]);
  await page.focus("#hostfield");
  await page.keyboard.press("Escape");
  assert.deepEqual(await modes(), [true], "Esc із поля хоста вийшов із режиму коментування");
  // Власна форма коментатора: Esc закриває лише її, режим лишається; наступний Esc (фокус на сторінці) — виходить.
  await page.click("#p");
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose")), false);
  assert.deepEqual(await modes(), [true]);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press("Escape");
  assert.deepEqual(await modes(), [true, false]);
  await page.close();
});

test("з host: destroy() не кличе колбеків (хост сам почав знищення) — onMode(false) не летить", async () => {
  const page = await boot({ withHost: true });
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  const n = await page.evaluate(() => window.__ev.length);
  await page.evaluate(() => window.CommentLayer.destroy());
  assert.deepEqual(await page.evaluate((k) => window.__ev.slice(k), n), [], "destroy() у режимі хоста кликав колбеки");
  await page.close();
});

test("з host.rightInset: композер ТЕКСТОВОГО режиму (виділення біля правого краю) теж не заходить під панель хоста", async () => {
  const page = await boot({ withHost: true, rightInset: 400 });
  await page.evaluate(() => {
    const p = document.createElement("p");
    p.id = "r"; p.textContent = "Біля краю";
    p.style.cssText = "position:absolute;right:10px;top:200px;width:160px;margin:0";
    document.body.appendChild(p);
    window.CommentLayer.setCommentMode(true);
    document.querySelector("[data-comment-layer]").shadowRoot.querySelector('.mode[data-mode="text"]').click();
    const range = document.createRange(); range.selectNodeContents(p);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range);
  });
  await page.dispatchEvent("#r", "mouseup");
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose"));
  const edge = await page.evaluate(() => ({
    right: document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose").getBoundingClientRect().right,
    w: window.innerWidth }));
  assert.ok(edge.right <= edge.w - 400 + 0.5, `композер текстового режиму заходить під панель хоста: right=${edge.right}, innerWidth=${edge.w}`);
  await page.close();
});

test("з host + anchors (полотно): destroy() гасить armed(false) у постачальника, але onMode(false) хосту не летить", async () => {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(() => {
    window.__ev = []; window.__armed = [];
    const mem = [];
    const anchors = { place: () => [], subscribe: () => {}, active: () => true, armed: (on) => window.__armed.push(on) };
    window.CommentLayer.init({ projectId: "t", storage: { load: () => mem.slice(), save: () => {} }, version: "2",
      user: { name: "Тест" }, anchors,
      host: { onReady: () => window.__ev.push(["ready"]), onChange: () => {}, onSelect: () => {}, onMode: (on) => window.__ev.push(["mode", on]) } });
    window.CommentLayer.setCommentMode(true);
  });
  assert.deepEqual(await page.evaluate(() => window.__armed), [true]);
  const n = await page.evaluate(() => window.__ev.length);
  await page.evaluate(() => window.CommentLayer.destroy());
  assert.deepEqual(await page.evaluate(() => window.__armed), [true, false], "постачальник не дізнався, що режим вимкнено");
  assert.deepEqual(await page.evaluate((k) => window.__ev.slice(k), n), [], "destroy() кликав колбеки хоста");
  await page.close();
});

/* ---- Deai 0.27.0: чипи адресата, колір піна за `_aud`, setMeta, uploadShot з піном ---- */
const AUDS = [{ id: "local", label: "L", color: "#7C6CF0" }, { id: "project", label: "P", note: "бачать колеги" }];

/** `store` пам'ятає і виклики `uploadShot` (третій аргумент теж); `__picked` — що почув `onAudiencePick`. */
async function bootAud({ withHost = true, audiences = AUDS, seed = [], defaultAudience = () => "project" } = {}) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(({ withHost, audiences, seed, hasDefault }) => {
    const mem = seed.slice();
    window.__mem = mem; window.__picked = []; window.__shots = [];
    const store = {
      load: () => mem.slice(),
      save: (l) => { mem.length = 0; mem.push(...l); },
      uploadShot: async (id, shot, c) => { window.__shots.push({ id, aud: c && c._aud, hasC: c !== undefined }); return null; },
    };
    const host = withHost ? {
      ...(hasDefault ? { defaultAudience: () => "project" } : {}),
      onAudiencePick: (id) => window.__picked.push(id),
    } : undefined;
    window.CommentLayer.init({ projectId: "t", storage: store, version: "2", user: { name: "Тест" }, audiences, host });
  }, { withHost, audiences, seed, hasDefault: !!defaultAudience });
  return page;
}
const SH = "document.querySelector('[data-comment-layer]').shadowRoot";
async function openForm(page) {
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  await page.click("#p");
  await page.waitForFunction(`!!${SH}.querySelector('.compose textarea')`);
}
const chipsOf = (page) => page.evaluate(`[...${SH}.querySelectorAll('.compose .caud-b')].map((b) => [b.textContent, b.getAttribute('aria-pressed')])`);

test("A: host + 2 аудиторії — чипи, натиснутий за defaultAudience, note, вибір іде в пін і в onAudiencePick", async () => {
  const page = await bootAud();
  await openForm(page);
  assert.deepEqual(await chipsOf(page), [["L", "false"], ["P", "true"]]);
  assert.equal(await page.evaluate(`${SH}.querySelector('.compose .caud-note').textContent`), "бачать колеги");
  await page.evaluate(`${SH}.querySelector('.compose .caud-b[data-pick="local"]').click()`);
  assert.deepEqual(await chipsOf(page), [["L", "true"], ["P", "false"]]);
  assert.equal(await page.evaluate(`${SH}.querySelector('.compose .caud-note').textContent`), "");
  await page.evaluate(`(() => { const ta = ${SH}.querySelector('.compose textarea'); ta.value = 'x'; ${SH}.querySelector('.compose .save').click(); })()`);
  await page.waitForFunction(() => window.__mem.some((c) => c.text === "x"));
  assert.equal(await page.evaluate(() => window.__mem.find((c) => c.text === "x")._aud), "local");
  assert.deepEqual(await page.evaluate(() => window.__picked), ["local"]);
  await page.close();
});

test("B: колір піна — з audiences[i].color, нешкідливий; без color інлайн-фону нема; data-aud", async () => {
  // Піни створюємо справжньою формою: DOM-пін без fp у сіді не має якоря й не малюється.
  const make = async (page, target, aud, text) => {
    await page.click(target);
    await page.waitForFunction(`!!${SH}.querySelector('.compose textarea')`);
    await page.evaluate(`(() => { ${SH}.querySelector('.compose .caud-b[data-pick="${aud}"]').click();
      ${SH}.querySelector('.compose textarea').value = '${text}'; ${SH}.querySelector('.compose .save').click(); })()`);
    await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text);
  };
  const pins = (page) => page.evaluate(`[...${SH}.querySelectorAll('.pin')].map((p) => [p.dataset.aud, p.style.background])`);
  const run = async (audiences) => {
    const page = await bootAud({ audiences });
    await page.evaluate(() => window.CommentLayer.setCommentMode(true));
    await make(page, "#t", "local", "l");
    await make(page, "#p", "project", "p");
    await page.waitForFunction(`${SH}.querySelectorAll('.pin').length === 2`);
    const got = await pins(page);
    await page.close();
    return got;
  };
  const got = await run(AUDS);
  assert.deepEqual(got.map((x) => x[0]), ["local", "project"]);
  assert.match(got[0][1], /rgb\(124, 108, 240\)/);
  assert.equal(got[1][1], "");
  // Не-hex колір ігнорується. `red` браузер би прийняв як фон — це ловить відсутність регекспа; `red;x` сам би відкинув
  // присвоєнням у style, тож його перевіряємо на самій функції.
  const bad = await run([{ id: "local", label: "L", color: "red" }, { id: "project", label: "P" }]);
  assert.deepEqual(bad.map((x) => x[1]), ["", ""]);
  const inj = await bootAud({ audiences: [{ id: "local", label: "L", color: "red;x" }, { id: "project", label: "P" }] });
  assert.equal(await inj.evaluate(() => window.CommentLayer._audColor({ _aud: "local" })), null);
  await inj.close();
});

test("C: без host чипів нема навіть при двох аудиторіях (форма як була)", async () => {
  const page = await bootAud({ withHost: false });
  await page.keyboard.press("c");
  await page.click("#p");
  await page.waitForFunction(`!!${SH}.querySelector('.compose textarea')`);
  assert.equal((await chipsOf(page)).length, 0);
  await page.close();
});

test("D: host + одна аудиторія — чипів нема", async () => {
  const page = await bootAud({ audiences: [AUDS[0]] });
  await openForm(page);
  assert.equal((await chipsOf(page)).length, 0);
  await page.close();
});

test("E: setMeta додає/знімає ключ meta і повертає false на невідомий id", async () => {
  const seed = [{ id: "a1", author: "Т", text: "l", status: "open", meta: { seq: 1, iteration: "2", version: "2" }, ts: "13.11.2026 10:00" }];
  const page = await bootAud({ seed });
  assert.equal(await page.evaluate(() => window.CommentLayer.setMeta("a1", { assignee: "claude" })), true);
  assert.equal(await page.evaluate(() => window.__mem[0].meta.assignee), "claude");
  assert.equal(await page.evaluate(() => window.CommentLayer.setMeta("a1", { assignee: null })), true);
  assert.equal(await page.evaluate(() => "assignee" in window.__mem[0].meta), false);
  assert.equal(await page.evaluate(() => window.CommentLayer.setMeta("nope", { assignee: "x" })), false);
  await page.close();
});

test("F: uploadShot отримує пін третім аргументом (_aud доходить до сховища)", async () => {
  const page = await bootAud();
  // Захоплення скріншота в голій сторінці недоступне — підміняємо _captureShot, решта шляху (форма → _finishComment) справжня.
  await page.evaluate(() => { window.CommentLayer._captureShot = async () => "data:image/png;base64,iVBORw0KGgo="; });
  await openForm(page);
  await page.evaluate(`(() => { const ta = ${SH}.querySelector('.compose textarea'); ta.value = 'y'; ${SH}.querySelector('.compose .save').click(); })()`);
  await page.waitForFunction(() => window.__shots.length > 0);
  assert.deepEqual(await page.evaluate(() => window.__shots[0].aud), "project");
  assert.equal(await page.evaluate(() => window.__shots[0].hasC), true);
  await page.close();
});

test("G: carry переносить _aud у копію", async () => {
  const page = await bootAud({ seed: [{ id: "a1", author: "Т", text: "p", status: "open", _aud: "project", meta: { seq: 1, iteration: "1", version: "1" }, ts: "13.11.2026 10:00" }] });
  await page.evaluate(() => window.CommentLayer.carry("a1"));
  assert.deepEqual(await page.evaluate(() => window.__mem.map((c) => c._aud)), ["project", "project"]);
  await page.close();
});
