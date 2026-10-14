/**
 * `askForm` (`app/ask.js`) — форма з кількох полів у тій самій оболонці, що `ask`/`askYesNo`/
 * `tell`/`askChoice`. Самі оверлеї без DOM не запустити (оболонка будує вузли й
 * слухачі на `document`), тож тут два шари, як у `tests/browser-dialogs.test.mjs`:
 *   · ЧИСТІ шматки, що в оболонці лежать окремими функціями, — `formValues` (що
 *     повертає форма) і `tabWrap` (куди йде Tab) — тестуються імпортом;
 *   · ПОВЕДІНКА оболонки, яку ламає тихо, — по джерелу: подвійна відправка, Esc
 *     посеред запиту, закриття на відмові сервера.
 * Повну поведінку в браузері (відправка Enter-ом, помилка на місці, пастка Tab)
 * покриває живий тест просторів (`tests/live/spaces.test.mjs`, Task 8).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { askForm, focusBackTarget, formValues, tabWrap } from "../app/ask.js";

const src = readFileSync(new URL("../app/ask.js", import.meta.url), "utf8");

/* ── formValues ────────────────────────────────────────────────────────── */

const f = (o) => ({ name: "x", type: "text", value: "", checked: false, disabled: false, ...o });

test("formValues: текстові поля — рядки як є, БЕЗ обрізання пробілів (це справа викликача)", () => {
  assert.deepEqual(formValues([f({ name: "name", value: "  Клієнт X " }), f({ name: "path", value: "~/a" })]),
    { name: "  Клієнт X ", path: "~/a" });
});

test("formValues: прихований вхід (колір) входить, безіменні й кнопки — ні", () => {
  assert.deepEqual(formValues([
    f({ name: "color", type: "hidden", value: "space-2" }),
    f({ name: "", value: "без імені" }),
    f({ name: undefined, value: "теж" }),
    f({ name: "go", type: "submit", value: "Створити" }),
    f({ name: "no", type: "button", value: "Скасувати" }),
    f({ name: "rs", type: "reset", value: "" }),
  ]), { color: "space-2" });
});

test("formValues: вимкнене поле — ні, readonly — так (його значення — відповідь сервера)", () => {
  assert.deepEqual(formValues([f({ name: "a", value: "1", disabled: true }), f({ name: "b", value: "2" })]),
    { b: "2" });
});

test("formValues: галочка — булеве завжди, радіо — значення вибраного або ключа нема", () => {
  assert.deepEqual(formValues([f({ name: "on", type: "checkbox", checked: true }),
    f({ name: "off", type: "checkbox", checked: false })]), { on: true, off: false });
  assert.deepEqual(formValues([
    f({ name: "c", type: "radio", value: "a", checked: false }),
    f({ name: "c", type: "radio", value: "b", checked: true }),
    f({ name: "c", type: "radio", value: "c", checked: false }),
  ]), { c: "b" });
  assert.deepEqual(formValues([f({ name: "c", type: "radio", value: "a", checked: false })]), {},
    "жодного вибраного — ключа нема, а не порожній рядок");
});

test("formValues: значення — завжди рядки; null/undefined — порожній рядок; нема переліку — {}", () => {
  assert.deepEqual(formValues([f({ name: "n", value: 5 }), f({ name: "z", value: null }), f({ name: "u", value: undefined })]),
    { n: "5", z: "", u: "" });
  assert.deepEqual(formValues(undefined), {});
  assert.deepEqual(formValues(null), {});
  assert.deepEqual(formValues([null, undefined]), {});
});

test("formValues: приймає й ітерований (HTMLFormControlsCollection-подібний) вхід", () => {
  const set = new Set([f({ name: "a", value: "1" })]);
  assert.deepEqual(formValues(set), { a: "1" });
});

/* ── tabWrap ───────────────────────────────────────────────────────────── */

test("tabWrap: Tab з останнього — на перший; Shift+Tab з першого — на останній", () => {
  assert.equal(tabWrap(4, 5, false), 0);
  assert.equal(tabWrap(0, 5, true), 4);
});

test("tabWrap: усередині списку браузер іде сам (null)", () => {
  assert.equal(tabWrap(2, 5, false), null);
  assert.equal(tabWrap(2, 5, true), null);
  assert.equal(tabWrap(0, 5, false), null);
  assert.equal(tabWrap(4, 5, true), null);
});

test("tabWrap: фокус ЗА межами форми (-1) втягується всередину в обох напрямках", () => {
  assert.equal(tabWrap(-1, 5, false), 0);
  assert.equal(tabWrap(-1, 5, true), 4);
});

test("tabWrap: єдиний елемент — обидва напрямки лишають його; порожньо — null", () => {
  assert.equal(tabWrap(0, 1, false), 0);
  assert.equal(tabWrap(0, 1, true), 0);
  assert.equal(tabWrap(0, 0, false), null);
  assert.equal(tabWrap(-1, 0, true), null);
});

/* ── focusBackTarget ───────────────────────────────────────────────────── */

const el = (o = {}) => ({ isConnected: true, disabled: false, tagName: "BUTTON", closest: () => null, ...o });

test("focusBackTarget: фокус втрачено — перший придатний (відкривач, потім запасний); не втрачено — null", () => {
  const opener = el({ id: "opener" });
  const spare = el({ id: "spare" });
  assert.equal(focusBackTarget(true, [opener, spare]), opener);
  assert.equal(focusBackTarget(false, [opener, spare]), null,
    "фокус уже переведено продовженням успіху (екран «Задачі», логотип) — не відбираємо");
});

test("focusBackTarget: відкривач, якого нема (перемальовано, схований екраном, body), пропускається", () => {
  const spare = el({ id: "spare" });
  assert.equal(focusBackTarget(true, [el({ isConnected: false }), spare]), spare, "вузол вилучено з документа");
  assert.equal(focusBackTarget(true, [el({ closest: (sel) => (sel === "[hidden]" ? {} : null) }), spare]), spare,
    "схований предком (екран «Задачі» закрито)");
  assert.equal(focusBackTarget(true, [el({ tagName: "BODY" }), spare]), spare, "body не відкривач: `focus()` на ньому нічого не дає");
  assert.equal(focusBackTarget(true, [el({ tagName: "HTML" }), spare]), spare);
  assert.equal(focusBackTarget(true, [el({ disabled: true }), spare]), spare, "вимкнену кнопку не сфокусувати");
  assert.equal(focusBackTarget(true, [null, undefined, spare]), spare, "порожні кандидати (запасного не дали) не кидають");
});

test("focusBackTarget: нікого придатного — null; без переліку — null", () => {
  assert.equal(focusBackTarget(true, [el({ isConnected: false })]), null);
  assert.equal(focusBackTarget(true, []), null);
  assert.equal(focusBackTarget(true, undefined), null);
  assert.equal(focusBackTarget(true, [el({ id: "x" })], () => false), null, "власний предикат придатності");
});

/* ── оболонка: що ламається тихо ───────────────────────────────────────── */

/** Тіло функції за збалансованими дужками — не за регекспом по рядках. */
function bodyOf(text, header) {
  const at = text.indexOf(header);
  assert.ok(at >= 0, `у джерелі нема «${header}»`);
  /* Перша `{` ПІСЛЯ списку параметрів: у `overlay(…, { value = '', … } = {})` вона стоїть
     раніше за тіло, і розбір від неї дав би шматок підпису. */
  const open = text.indexOf(") {", at) + 2;
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") { depth -= 1; if (depth === 0) return text.slice(open, i + 1); }
  }
  throw new Error(`немає закриття для «${header}»`);
}
const overlayBody = bodyOf(src, "function overlay(");

/** Тіло стрілочної функції `const name = (…) => {…}`: перша `{` після заголовка. */
function arrowBody(text, header) {
  const at = text.indexOf(header);
  assert.ok(at >= 0, `у джерелі нема «${header}»`);
  const open = text.indexOf("{", at + header.length);
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") { depth -= 1; if (depth === 0) return text.slice(open, i + 1); }
  }
  throw new Error(`немає закриття для «${header}»`);
}

test("askForm: експорт; відмова — null (Esc, «Скасувати», перебитий оверлей), не false/undefined", () => {
  assert.equal(typeof askForm, "function");
  assert.match(src, /export const askForm\s*=/);
  assert.match(overlayBody, /kind === 'yesno' \? false : \(kind === 'tell' \? undefined : null\)/,
    "відмова форми лишилась null: форма не `yesno` і не `tell`");
});

test("askForm: розмітку вставляє лише для форми, і лише з `build()` викликача", () => {
  assert.match(overlayBody, /if \(isForm\) \{[\s\S]*?boxEl\.innerHTML = form\.build\(\);/);
  assert.equal([...src.matchAll(/\.innerHTML\s*=/g)].length, 1, "innerHTML у ask.js — рівно один, у гілці форми");
});

test("askForm: відправка нативна й одинарна — ДРУГА відправка під час запиту ігнорується", () => {
  assert.match(overlayBody, /formEl\.addEventListener\('submit', async \(ev\) => \{\s*ev\.preventDefault\(\);\s*if \(busy \|\| open !== api\) return;/);
  /* `busy` ставиться ДО `await onSubmit`, а кнопка вимикається тим самим кроком. */
  const i = overlayBody.indexOf("busy = true;");
  assert.ok(i > 0, "нема `busy = true`");
  assert.ok(i < overlayBody.indexOf("await form.onSubmit"), "`busy` має стояти ДО запиту");
  assert.ok(overlayBody.indexOf("ctl.busy(true)") < overlayBody.indexOf("await form.onSubmit"));
});

test("askForm: діалог закривається ЛИШЕ на успіх — відмова сервера лишається на місці", () => {
  assert.match(overlayBody, /if \(err\) ctl\.error\(err\); else done\(values\);/);
  /* Виняток із `onSubmit` теж стає текстом помилки, а не знімає діалог мовчки. */
  assert.match(overlayBody, /catch \(e\) \{ err = t\('errFailed'/);
});

test("askForm: Esc і «Скасувати» посеред запиту не закривають форму", () => {
  assert.match(overlayBody, /if \(e\.key === 'Escape' && busy\) \{ e\.stopPropagation\(\); return; \}/);
  assert.match(overlayBody, /\[data-a="cancel"\]'\)\?\.addEventListener\('click', \(\) => \{\s*if \(!busy\) done\(cancelled\);/);
  /* Порядок: перевірка `busy` — РАНІШЕ за звичайний вихід по Esc. */
  assert.ok(overlayBody.indexOf("e.key === 'Escape' && busy") < overlayBody.indexOf("if (e.key === 'Escape') {"));
});

test("askForm: фокус-пастка Tab — лише у формі, через `tabWrap`, з перехопленням стрілки Tab", () => {
  assert.match(overlayBody, /if \(e\.key === 'Tab' && formEl\) \{[\s\S]*?tabWrap\(list\.indexOf\(document\.activeElement\), list\.length, e\.shiftKey\)[\s\S]*?e\.preventDefault\(\);/);
  /* Кружки кольору — `button` із tabindex=-1: у перелік Tab-цілей вони не входять. */
  assert.match(src, /el\.tabIndex >= 0/);
  assert.match(src, /!el\.disabled/);
});

test("askForm: Enter на документі форма НЕ обробляє (відправка нативна), поле — як у `ask`", () => {
  /* Обробник Enter прив'язаний до `input` — а в формі його нема (`let input = null`). */
  assert.match(overlayBody, /if \(e\.key === 'Enter' && input\) \{/);
  assert.match(overlayBody, /let input = null;\s*if \(kind === 'ask'\) \{/);
});

test("askForm: стара відмова зникає, щойно людина правила поле", () => {
  assert.match(overlayBody, /formEl\.addEventListener\('input', \(\) => ctl\.error\(''\)\);/);
});

test("askForm: фокус — `[data-autofocus]` або перше текстове поле, `onMount` ДО фокуса", () => {
  const i = overlayBody.indexOf("form.onMount?.(formEl, ctl)");
  assert.ok(i > 0, "onMount не викликається");
  assert.ok(i < overlayBody.indexOf("[data-autofocus]"), "onMount мусить стояти до вибору поля фокуса");
  assert.match(overlayBody, /input:not\(\[type=hidden\]\)/);
});

test("askForm: відкривач запамʼятовується ПІСЛЯ скасування попереднього оверлея, фокус вертається лише коли втрачено", () => {
  /* Після `open.cancel()`: той, що закривається, щойно повернув фокус своєму відкривачу, і
     саме його успадковує наступний; до скасування фокус стояв би в підкладці, яку знімуть. */
  assert.ok(overlayBody.indexOf("if (open) open.cancel();") < overlayBody.indexOf("const opener = document.activeElement;"));
  const done = arrowBody(overlayBody, "const done = (result) =>");
  assert.match(done, /const lost = !a \|\| a === document\.body \|\| scrim\.contains\(a\);/);
  assert.ok(done.indexOf("const lost") < done.indexOf("scrim.remove()"), "«втрачено» міряється ДО зняття підкладки");
  assert.match(done, /focusBackTarget\(lost, \[opener, form\?\.focusBack\?\.\(\)\]\)\?\.focus\(\{ preventScroll: true \}\);/);
  assert.ok(done.indexOf("focusBackTarget(") < done.indexOf("resolve(result)"),
    "фокус повертається ДО resolve: продовження викликача (`.then`) бачить уже поставлений фокус і може його переставити");
  assert.match(src, /askForm = \(build, \{ onMount, onSubmit, focusBack \} = \{\}\) =>\s*overlay\('', 'form', \{ form: \{ build, onMount, onSubmit, focusBack \} \}\)/);
});

test("askForm: ctl.focus(імʼя) ставить aria-invalid на поле, ctl.error('') знімає з усіх; непорожня помилка не знімає", () => {
  assert.match(overlayBody, /focus\(name\) \{\s*const f = formEl\.elements\.namedItem\(name\);\s*if \(!f\) return;\s*f\.setAttribute\?\.\('aria-invalid', 'true'\);\s*f\.focus\?\.\(\);/);
  assert.match(overlayBody, /if \(!msg\) for \(const f of formEl\.querySelectorAll\('\[aria-invalid\]'\)\) f\.removeAttribute\('aria-invalid'\);/);
  /* Правка поля знімає стару відмову РАЗОМ із `aria-invalid` (обробник `input` кличе `ctl.error('')`). */
  assert.match(overlayBody, /formEl\.addEventListener\('input', \(\) => ctl\.error\(''\)\);/);
});

test("askForm: перебитий оверлей не лишає підкладки-сироти — done закриває лише поточний (open === api)", () => {
  const done = arrowBody(overlayBody, "const done = (result) =>");
  assert.match(done, /if \(open !== api\) return;/);
  assert.ok(done.indexOf("open = null;") < done.indexOf("scrim.remove();"));
  assert.match(done, /document\.removeEventListener\('keydown', onKey, true\);/, "слухач Esc/Tab іде разом із підкладкою");
  /* Новий оверлей спершу ЗАКРИВАЄ відкритий (його done зніме підкладку), потім відкривається сам. */
  assert.ok(overlayBody.indexOf("if (open) open.cancel();") < overlayBody.indexOf("document.body.appendChild(scrim);"));
  /* Кнопка «Скасувати» й Esc під час запиту — тільки через `busy`; сам `cancel()` оверлея (виклик
     НОВОГО питання) його не питає: перебиття не блокується, і сирота не виникає. */
  assert.match(overlayBody, /const api = \{ cancel: \(\) => done\(cancelled\) \};/);
});
