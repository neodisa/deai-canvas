/**
 * Етап В (0.28.0): вбудоване підтвердження видалення — розмітка й проводка у трьох місцях (меню сторінки, дропдаун
 * ітерації, картка коментаря). Поведінку в браузері (Esc, клік повз, «Ні» — нічого не видалено) покривають живі тести.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { confirmHTML, confirmedId } from "../app/inline-confirm.js";

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

test("фаза И (Р6): «Видалити» в меню рядка питає на місці (iterUi.del), «Видалити» питання — deleteIteration; закриття дропдауна скидає iterUi", () => {
  assert.match(app, /if \(act === 'itdel'\) \{ iterUi = \{ \.\.\.IT_NONE, del: el\.dataset\.val \}; paintBar\(\);/);
  assert.match(app, /if \(act === 'itdelyes'\) \{ deleteIteration\(el\.dataset\.val\); return; \}/);
  assert.match(app, /if \(openDd !== 'iter'\) iterUi = IT_NONE;/);
  assert.doesNotMatch(app, /iterDelAsk\s*=|delitask/);
});

test("confirmedId: лише `confirmed:<id>`; голе `confirmed`, порожнє й чуже — null (питання не пропускається)", () => {
  assert.equal(confirmedId("confirmed:it3"), "it3");
  assert.equal(confirmedId("confirmed:"), "");
  for (const v of ["confirmed", "", undefined, null, 5, "it3", "xconfirmed:it3"]) assert.equal(confirmedId(v), null, String(v));
});

test("фаза И: єдиний шлях видалення ітерації — deleteIteration (кошик + «Повернути»); ⌘K `delit` лише відкриває питання", () => {
  assert.equal((app.match(/\/api\/iteration-delete/g) || []).length, 1);
  const del = app.slice(app.indexOf("async function deleteIteration("), app.indexOf("async function restoreIteration("));
  assert.match(del, /\/api\/iteration-delete/);
  assert.match(del, /toast\(t\('iterDeleted', label\), \{ ms: 8000, action: \{ label: t\('iterRestore'\)/);
  const cmdK = app.slice(app.indexOf("  delit: () => {"), app.indexOf("  ithist:"));
  assert.doesNotMatch(cmdK, /api\/iteration-delete|askYesNo|deleteIteration\(/, "⌘K `delit` не видаляє сам: лише відкриває питання");
  assert.match(cmdK, /\.length <= 1\) return;/, "єдину ітерацію ⌘K не пропонує видаляти");
  assert.match(cmdK, /iterUi = \{ \.\.\.IT_NONE, del: picked \}/);
});

test("фаза И (Р5): перейменування — без діалогів; Esc скидає стан ДО перемальовки, blur під час перемальовки й повторний blur не зберігають", () => {
  const bars = app.slice(app.indexOf("  newit: () => createIteration(picked),"), app.indexOf("  ithist:"));
  assert.doesNotMatch(bars, /\bask\(/);
  const save = app.slice(app.indexOf("async function saveItRen("), app.indexOf("async function deleteIteration("));
  assert.ok(save.indexOf("if (iterUi.ren !== id) return;") < save.indexOf("iterUi = IT_NONE;"), "охоронець повторного/скасованого збереження");
  assert.ok(save.indexOf("iterUi = IT_NONE;") < save.indexOf("/api/iteration-rename"));
  assert.match(app, /if \(barRepainting \|\| ev\.target\.id !== 'it-ren-in'\) return;/);
  assert.match(app, /iterUi = IT_NONE; paintBar\(\);\n\s+bar\.querySelector\('\.it-row \.dd-item--on'\)/);
});

test("фаза И: перемальовка смуги не губить набране в полі назви (значення й виділення вертаються)", () => {
  const paint = app.slice(app.indexOf("function paintBar() {"), app.indexOf("paintTabs();", app.indexOf("function paintBar() {")));
  assert.match(paint, /renKeep/);
  assert.match(paint, /inp\.value = renKeep\.v;/);
  assert.match(paint, /setSelectionRange\(renKeep\.a, renKeep\.b\)/);
});


/* Фаза И, фінальний раунд: проводка в app.js, що перевіряється лише по джерелу. */
const fn = (name, next) => app.slice(app.indexOf(name), app.indexOf(next, app.indexOf(name) + 1));

test("createIteration: охоронець від подвійного кліку знімається в finally", () => {
  const f = fn("async function createIteration(", "/** Відкрити поле назви");
  assert.match(app, /^let creatingIt = false;/m);
  assert.match(f, /if \(!from \|\| creatingIt\) return;\n\s+creatingIt = true;/);
  assert.match(f, /finally \{ creatingIt = false; \}/);
});

test("«Повернути» йде в задачу, де видалили: id задачі береться при видаленні й їде заголовком X-Canvas-Task", () => {
  const del = fn("async function deleteIteration(", "async function restoreIteration(");
  assert.match(del, /const taskId = currentTaskId;/);
  assert.match(del, /restoreIteration\(r\.trash, label, taskId\)/);
  const res = fn("async function restoreIteration(", "/**\n * Забути ВСЕ");
  assert.match(res, /'X-Canvas-Task': taskId/);
  assert.match(res, /\/api\/iteration-restore/);
  assert.match(res, /taskId === currentTaskId\) \{ picked = r\.id; await render\(\); \}/, "чужу задачу не перемальовуємо");
});

test("права панель одна: історія закривається при відкритті коментарів, модуля, інспектора (кнопка й клавіша `I`) і події `mode` коментатора", () => {
  assert.match(app.slice(app.indexOf("function setCommentsOpen("), app.indexOf("function setCommentsOpen(") + 400), /if \(on\) closeHistory\(\);/);
  assert.match(app.slice(app.indexOf("function openModTool("), app.indexOf("function openModTool(") + 700), /\n  closeHistory\(\);/);
  assert.match(app, /  inspector: \(\) => \{[\s\S]{0,400}if \(!api\.on\) closeHistory\(\);/);
  assert.match(app, /if \(api && api\.on && histOpen\) closeHistory\(\);/);
  assert.match(app, /else if \(m\.on && !cmtOpen\) \{ closeHistory\(\); cmtOpen = true;/);
});

test("openHistory відкидає застарілу відповідь і в успіху, і в помилці", () => {
  const f = fn("async function openHistory(", "/** Закрити історію");
  assert.equal((f.match(/if \(histOpen\?\.seq !== seq\) return;/g) || []).length, 2);
  const [ok, bad] = f.split("} catch (e) {");
  assert.match(ok, /histOpen\?\.seq !== seq\) return;[\s\S]*histHTML\(\{ label, entries: r\.entries/);
  assert.match(bad, /histOpen\?\.seq !== seq\) return;[\s\S]*degraded: true/);
});

test("Р1: тост «теки немає» називає задачу назвою, а не ключем", () => {
  assert.match(app, /toast\(t\('folderMissingOpen', cleanTitle\(x\)\)\)/);
});
