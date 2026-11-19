import assert from "node:assert/strict";
import test from "node:test";
import { spaceBodyHTML, spaceReadOnly } from "../app/space-view.js";

const SP = { id: "p1", name: "Студія", color: "space-5", path: "/u/work/studio" };

test("«Простір»: назва, радіогрупа з шести плиток (одна в Tab-порядку, вибрана — з галочкою), тека з копіюванням", () => {
  const html = spaceBodyHTML(SP);
  assert.match(html, /<input class="cn-inp" id="set-sp-name" type="text" value="Студія"/);
  assert.match(html, /role="radiogroup" aria-labelledby="sp-color-h"/);
  assert.equal((html.match(/role="radio"/g) || []).length, 6);
  assert.equal((html.match(/tabindex="0"/g) || []).length, 1, "roving tabindex: рівно одна плитка в Tab-порядку");
  assert.match(html, /aria-checked="true" tabindex="0"[^>]*data-v="space-5"/);
  assert.equal((html.match(/aria-checked="true"/g) || []).length, 1);
  assert.match(html, /data-v="space-5"[^]*?Фіолетовий<svg/, "вибрана плитка з галочкою");
  assert.match(html, /<div class="sp-path"><span>\/u\/work\/studio<\/span><button[^>]*data-th="spcopy"/);
  for (let n = 1; n <= 6; n++) assert.match(html, new RegExp(`class="sw" role="radio"[^>]*data-val="space-${n}"`));
  assert.equal((html.match(/class="sw-pv"/g) || []).length, 6, "кожна плитка має мініатюру");
});

test("«Простір»: ворожа назва екранується; невідомий колір читається як перший; неявний простір (без теки) — лише читання", () => {
  const html = spaceBodyHTML({ ...SP, name: '<b>"x', color: "red;x" });
  assert.doesNotMatch(html, /<b>/);
  assert.match(html, /value="&lt;b&gt;&quot;x"/);
  assert.match(html, /aria-checked="true" tabindex="0"[^>]*data-v="space-1"/);
  const ro = spaceBodyHTML({ id: "legacy", name: "legacy", color: "space-1", path: "" });
  assert.equal(spaceReadOnly({ path: "" }), true);
  assert.equal(spaceReadOnly(SP), false);
  assert.match(ro, /id="set-sp-name"[^>]*disabled/);
  assert.equal((ro.match(/class="sw"[^>]*disabled/g) || []).length, 6);
  assert.doesNotMatch(ro, /sp-path/, "теки нема — рядка теки нема");
});
