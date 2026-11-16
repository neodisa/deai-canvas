/**
 * Етап В (0.28.0): вбудоване підтвердження видалення — розмітка й проводка у трьох місцях (меню сторінки, дропдаун
 * ітерації, картка коментаря). Поведінку в браузері (Esc, клік повз, «Ні» — нічого не видалено) покривають живі тести.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { confirmHTML } from "../app/inline-confirm.js";

const app = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

test("confirmHTML: лише питання, «Ні» перед «Видалити», атрибути викликача, тексти екрановано", () => {
  const html = confirmHTML({ title: "Видалити «<b>»?", yes: "Видалити", no: "Ні",
    yesAttrs: 'data-a="delyes"', noAttrs: 'data-a="delno"' });
  assert.match(html, /^<div class="cfm" role="group" aria-label="Видалити «&lt;b&gt;»\?">/);
  assert.match(html, /<p class="cfm-t">Видалити «&lt;b&gt;»\?<\/p><div class="cfm-row">/);
  assert.ok(html.indexOf('class="cfm-no"') < html.indexOf('class="cfm-yes"'));
  assert.match(html, /<button type="button" class="cfm-no" data-a="delno">Ні<\/button>/);
  assert.match(html, /<button type="button" class="cfm-yes" data-a="delyes">Видалити<\/button>/);
});

test("меню сторінки: «Видалити» для yesno питає в меню, «Так» кличе deleteNodes з confirmed; choice — як було", () => {
  const body = app.slice(app.indexOf("function pageMenu("), app.indexOf("// ===== Режим «Огляд»"));
  assert.match(body, /model\.kind !== 'yesno'\) \{ close\(\); deleteNodes\(ids\); return; \}/);
  assert.match(body, /deleteNodes\(ids, \{ confirmed: true \}\)/);
  assert.match(body, /\.cfm-no'\)\?\.focus\(\)/);
  assert.equal(/on\('delete'/.test(body), false);
});

test("deleteNodes: confirmed пропускає лише питання yesno", () => {
  const body = app.slice(app.indexOf("async function deleteNodes("), app.indexOf("const deletePage ="));
  assert.match(body, /async function deleteNodes\(ids, \{ confirmed = false \} = \{\}\)/);
  assert.match(body, /if \(!confirmed && !\(await askYesNo\(t\('menuDeletePageConfirm'\)/);
});
