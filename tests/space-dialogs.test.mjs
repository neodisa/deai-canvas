/**
 * Розмітка й проводка діалогів просторів (`app/space-dialogs.js`).
 *
 * Розмітка — чисті рядки, тестується імпортом. Проводка (`wire*`) бере готовий вузол
 * форми й залежності зверху, тож їй досить мінімальної заглушки вузлів нижче — без
 * браузера: ловимо те, що ламається мовчки (тека не йде за назвою, відповідь peek
 * приїхала не в порядку, форма вже закрита, а таймер ще б'є). Решту — реальний
 * браузер, клавіатура, оболонка `askForm` — покриває живий тест просторів (Task 8).
 */
import assert from "node:assert/strict";
import test from "node:test";

import { getLang, setLang } from "../app/i18n.js";
import { SPACE_COLORS } from "../app/spaces-model.js";
import {
  parseTags, spaceDialogHTML, tagsFormHTML, taskFormHTML, welcomeHTML, wireSpaceDialog, wireTaskForm,
} from "../app/space-dialogs.js";

const CYR = /[а-яіїєґА-ЯІЇЄҐ]/;
const attr = (html, re) => re.exec(html)?.[1];
const tick = (ms = 30) => new Promise((done) => setTimeout(done, ms));

/* ── розмітка діалогу простору ─────────────────────────────────────────── */

test("діалог простору (`edit`): гачки на місці — назва, прихований колір, слот помилки, кнопки, фокус у назву", () => {
  const h = spaceDialogHTML({ name: "Клієнт", color: "space-3" });
  assert.match(h, /<form class="cv-form" data-form="space" data-mode="edit"/);
  assert.match(h, /<input id="sp-name" name="name" type="text" value="Клієнт"/);
  assert.match(h, /<input type="hidden" name="color" value="space-3">/);
  assert.match(h, /<p class="cv-form-err" id="cv-form-err" role="alert" data-form-error hidden><\/p>/);
  assert.match(h, /<button type="button" data-a="cancel">/);
  assert.match(h, /<button type="submit" data-a="ok">Зберегти<\/button>/);
  assert.match(h, /data-autofocus/, "фокус — у назву");
});

test("діалог: шість кружків role=radio, вибраний рівно один, і він єдиний у Tab-порядку", () => {
  const h = spaceDialogHTML({ color: "space-4" });
  assert.match(h, /role="radiogroup" aria-labelledby="sp-color-l"/);
  const radios = [...h.matchAll(/<button type="button" class="cv-color" role="radio"[\s\S]*?<\/button>/g)].map((m) => m[0]);
  assert.equal(radios.length, 6);
  assert.deepEqual(radios.map((r) => attr(r, /data-val="([^"]+)"/)), SPACE_COLORS);
  assert.deepEqual(radios.map((r) => attr(r, /aria-checked="([^"]+)"/)), ["false", "false", "false", "true", "false", "false"]);
  assert.deepEqual(radios.map((r) => attr(r, /tabindex="([^"]+)"/)), ["-1", "-1", "-1", "0", "-1", "-1"]);
  radios.forEach((r, i) => assert.match(r, new RegExp(`style="background:var\\(--space-${i + 1}\\)"`)));
  for (const r of radios) assert.match(r, /aria-label="[^"]+"/, "кожен кружок має імʼя для читача");
  assert.match(radios[0], /<svg[^>]*><use href="#i-check"/, "галочка всередині: колір сам стан не оголошує");
});

test("діалог: без теки, назва кнопки й заголовок «Назва й колір», без підводки про теку", () => {
  const h = spaceDialogHTML({ name: "ЛІГА", color: "space-2" });
  assert.match(h, /data-mode="edit"/);
  assert.doesNotMatch(h, /sp-path|name="path"/, "теку простору міняти не можна");
  assert.doesNotMatch(h, /sp-found|sp-registered/, "підказки про теку — лише в кроці 1 майстра");
  assert.match(h, /<h2 class="cv-form-h" id="sp-h">Назва й колір<\/h2>/);
  assert.match(h, /data-a="ok">Зберегти<\/button>/);
  assert.doesNotMatch(h, /cv-form-lead/);
  assert.match(h, /value="ЛІГА"/);
});

test("діалог: початкова помилка — текст зі словника за ключем, слот видимий", () => {
  const h = spaceDialogHTML({ errorKey: "spaceErrTooBroad" });
  assert.match(h, /<p class="cv-form-err" id="cv-form-err" role="alert" data-form-error>Це надто широка тека/);
  assert.doesNotMatch(h, /data-form-error hidden/);
});

test("діалог: поле назви посилається на слот помилки (aria-describedby), id слота один; форма задачі — теж", () => {
  const h = spaceDialogHTML({ name: "X" });
  assert.equal([...h.matchAll(/id="cv-form-err"/g)].length, 1);
  const input = /<input id="sp-name"[^>]*>/.exec(h)[0];
  assert.match(input, /aria-describedby="[^"]*\bcv-form-err\b[^"]*"/, "sp-name не повʼязаний зі слотом помилки");
  const task = taskFormHTML({});
  for (const id of ["tf-title", "tf-id"]) {
    assert.match(new RegExp(`<input id="${id}"[^>]*aria-describedby="cv-form-err"`).exec(task)?.[0] ?? "", /cv-form-err/, id);
  }
  /* aria-invalid ставить лише `ctl.focus(імʼя)` на помилку; у розмітці його нема — поле чисте. */
  assert.doesNotMatch(h, /aria-invalid/);
  assert.doesNotMatch(task, /aria-invalid/);
});

test("діалог: усе, що приходить із даних, екранується; колір — лише токен", () => {
  const evil = `"><img src=x onerror=alert(1)>`;
  const h = spaceDialogHTML({ name: evil, color: "red;position:fixed" });
  assert.doesNotMatch(h, /<img/, "розмітка з даних не стала тегом");
  assert.ok(h.includes("&quot;&gt;&lt;img src=x onerror=alert(1)&gt;"));
  assert.doesNotMatch(h, /position:fixed/);
  assert.match(h, /name="color" value="space-1"/);
});

/* ── форма задачі й привітання ─────────────────────────────────────────── */

test("форма задачі: гачки Task 8, значення екрануються, id й назва — окремі поля", () => {
  const h = taskFormHTML({ title: `<b>"x"</b>`, id: "a-b" });
  assert.match(h, /<form class="cv-form" data-form="task"/);
  assert.match(h, /<input id="tf-title" name="title" type="text" value="&lt;b&gt;&quot;x&quot;&lt;\/b&gt;"/);
  assert.match(h, /<input id="tf-id" name="id" type="text" value="a-b"/);
  assert.match(h, /<h2 class="cv-form-h" id="tf-h">Нова задача<\/h2>/);
  assert.match(h, /data-a="ok">Створити задачу<\/button>/);
  assert.match(h, /data-form-error hidden/);
  assert.match(h, /for="tf-title"[^>]*>Назва задачі/);
  assert.match(h, /for="tf-id"[^>]*>Ідентифікатор/);
  assert.match(taskFormHTML({ errorKey: "idTaken" }), /data-form-error>Такий ідентифікатор уже є/);
});

test("форма задачі: поле «Репозиторій» — лише коли передано repo; без нього розмітка дослівно як була", () => {
  const plain = taskFormHTML({});
  assert.equal(taskFormHTML(), plain, "виклик без аргументів — те саме");
  assert.equal(taskFormHTML({ repo: null }), plain, "repo: null — поля нема");
  assert.doesNotMatch(plain, /tf-repo|name="repo"|Репозиторій/);
  assert.ok(plain.includes('aria-describedby="cv-form-err">\n    </div>\n    <p class="cv-form-err" id="cv-form-err"'),
    "стик «поле id → слот помилки» без жодного зайвого рядка: розмітка без repo побайтно та, що була в 0.7.0");
  const h = taskFormHTML({ repo: { placeholder: "git@x:y.git" } });
  assert.match(h, /<input id="tf-repo" name="repo" type="text" value=""[^>]*placeholder="git@x:y\.git"/);
  assert.match(h, /for="tf-repo"[^>]*>Репозиторій \(необовʼязково\)/);
  assert.match(/<input id="tf-repo"[^>]*>/.exec(h)[0], /aria-describedby="cv-form-err"/, "помилка адреси читається зчитувачем");
  assert.ok(h.indexOf('id="tf-id"') < h.indexOf('id="tf-repo"') && h.indexOf('id="tf-repo"') < h.indexOf("data-form-error"),
    "поле — після id, до слота помилки");
  assert.equal([...h.matchAll(/id="cv-form-err"/g)].length, 1, "слот помилки один");
  assert.match(taskFormHTML({ repo: {} }), /placeholder="типовий з «Підключення»"/, "без підказки — загальний текст зі словника");
  assert.match(taskFormHTML({ repo: { placeholder: "" } }), /placeholder="типовий з «Підключення»"/);
});

test("форма задачі: підказка репозиторію екранується (дані з налаштувань модуля — не розмітка)", () => {
  const evil = `"><img src=x onerror=alert(1)>`;
  const h = taskFormHTML({ repo: { placeholder: evil } });
  assert.doesNotMatch(h, /<img/);
  assert.ok(h.includes("&quot;&gt;&lt;img src=x onerror=alert(1)&gt;"));
});

test("форма задачі: поле «Репозиторій» англійською — без кирилиці", () => {
  const before = getLang();
  setLang("en");
  try {
    const h = taskFormHTML({ repo: {} });
    assert.ok(!CYR.test(h), `кирилиця в англійській розмітці: ${h.match(/.{0,30}[а-яіїєґ].{0,30}/i)?.[0]}`);
    assert.match(h, /Repository \(optional\)/);
    assert.match(h, /placeholder="the default from Connections"/);
  } finally { setLang(before); }
});

test("форма задачі: поле «Мітки» — лише коли tags: true; без нього розмітка побайтно та, що була; поле — після id і репо, до слота помилки", () => {
  const plain = taskFormHTML({});
  assert.equal(taskFormHTML({ tags: false }), plain);
  assert.doesNotMatch(plain, /tf-tags|name="tags"|Мітки/);
  const h = taskFormHTML({ tags: true });
  assert.match(h, /<label for="tf-tags">Мітки, через кому<\/label>/);
  assert.match(/<input id="tf-tags"[^>]*>/.exec(h)[0], /name="tags" type="text" value="" autocomplete="off" placeholder="напр\. alpha, beta" aria-describedby="cv-form-err"/);
  assert.ok(h.indexOf('id="tf-id"') < h.indexOf('id="tf-tags"') && h.indexOf('id="tf-tags"') < h.indexOf("data-form-error"));
  const both = taskFormHTML({ repo: {}, tags: true });
  assert.ok(both.indexOf('id="tf-repo"') < both.indexOf('id="tf-tags"') && both.indexOf('id="tf-tags"') < both.indexOf("data-form-error"),
    "після поля репозиторію");
  assert.equal([...both.matchAll(/id="cv-form-err"/g)].length, 1, "слот помилки один");
  assert.equal(taskFormHTML({ repo: {} }).replace(/\s+/g, " "), both.replace(/<div class="cv-field">\s*<label for="tf-tags">[^]*?<\/div>/, "").replace(/\s+/g, " "),
    "«Мітки» нічого більше не чіпають у формі");
});

test("діалог міток: форма data-form=tags, поле #tg-tags із поточним значенням (екранується), слот помилки, кнопки", () => {
  const h = tagsFormHTML({ value: `alpha, <b>"x"</b>` });
  assert.match(h, /<form class="cv-form" data-form="tags"/);
  assert.match(h, /<h2 class="cv-form-h" id="tg-h">Мітки задачі<\/h2>/);
  assert.match(h, /<label for="tg-tags">Мітки, через кому<\/label>/);
  assert.match(h, /<input id="tg-tags" name="tags" type="text" value="alpha, &lt;b&gt;&quot;x&quot;&lt;\/b&gt;"/);
  assert.doesNotMatch(h, /<b>/);
  assert.match(h, /aria-labelledby="tg-h"/);
  assert.match(h, /data-autofocus/);
  assert.match(h, /data-form-error hidden/);
  assert.match(h, /data-a="cancel"/);
  assert.match(h, /<button type="submit" data-a="ok">Зберегти<\/button>/);
  assert.match(tagsFormHTML(), /id="tg-tags" name="tags" type="text" value=""/, "без аргументів — порожнє поле");
  assert.match(tagsFormHTML({ errorKey: "tagsBad" }), /data-form-error>Мітка — до 32 знаків, без коми; не більше 10/);
});

test("діалог міток і поле «Мітки» англійською — без кирилиці", () => {
  const before = getLang();
  setLang("en");
  try {
    for (const h of [tagsFormHTML({ value: "alpha" }), taskFormHTML({ tags: true }), tagsFormHTML({ errorKey: "tagsBad" })]) {
      assert.ok(!CYR.test(h), `кирилиця: ${h.match(/.{0,30}[а-яіїєґ].{0,30}/i)?.[0]}`);
    }
    assert.match(tagsFormHTML(), /Task tags/);
    assert.match(taskFormHTML({ tags: true }), /Tags, comma-separated/);
  } finally { setLang(before); }
});

test("parseTags: по комах, обрізає, порожні відкидає; дублікати, регістр і межі — справа сервера", () => {
  assert.deepEqual(parseTags("a, b,, A ,"), ["a", "b", "A"]);
  assert.deepEqual(parseTags("  alpha  "), ["alpha"]);
  assert.deepEqual(parseTags("a b, c"), ["a b", "c"], "пробіл усередині мітки лишається");
  assert.deepEqual(parseTags("a, a, A"), ["a", "a", "A"], "дублікати не прибираємо: це робить сервер");
  assert.deepEqual(parseTags(`${"x".repeat(40)}`), ["x".repeat(40)], "довжину не міряємо: bad-tags приходить із сервера");
  for (const x of ["", "   ", ",", " , ,", null, undefined]) assert.deepEqual(parseTags(x), [], JSON.stringify(x));
  assert.deepEqual(parseTags(5), ["5"]);
});

test("привітання: кнопка data-th=spacenew, заголовок, підводка про агента, логотип", () => {
  const h = welcomeHTML();
  assert.match(h, /<button class="ctl ctl--pri" data-th="spacenew">/);
  assert.match(h, /<button class="ctl ctl--out" data-th="spaceopen">/);
  assert.match(h, /Відкрити наявну теку простору/);
  assert.match(h, /<h1 class="th-h">Вітаю в Deai Canvas<\/h1>/);
  assert.match(h, /створи простір Клієнт X/);
  assert.match(h, /<svg class="logo"/);
  assert.match(h, /class="th-in th-welcome"/);
});

test("англійська: жодної кирилиці в розмітці з порожніх даних (усе — зі словника)", () => {
  const before = getLang();
  setLang("en");
  try {
    for (const h of [spaceDialogHTML({}), spaceDialogHTML({ name: "X" }), taskFormHTML({}), welcomeHTML()]) {
      assert.ok(!CYR.test(h), `кирилиця в англійській розмітці: ${h.match(/.{0,30}[а-яіїєґ].{0,30}/i)?.[0]}`);
    }
    assert.match(taskFormHTML({}), /New task/);
  } finally { setLang(before); }
});

/* ── проводка: заглушка вузлів ─────────────────────────────────────────── */

function node(init = {}) {
  const handlers = new Map();
  const attrs = new Map();
  const n = {
    value: "", readOnly: false, hidden: false, textContent: "", tabIndex: 0, dataset: {}, isConnected: true,
    ...init,
    addEventListener(type, fn) { if (!handlers.has(type)) handlers.set(type, []); handlers.get(type).push(fn); },
    fire(type, ev = {}) {
      const e = { target: n, ...ev, preventDefault() { e.prevented = true; } };
      for (const fn of handlers.get(type) ?? []) fn(e);
      return e;
    },
    setAttribute(k, v) { attrs.set(k, String(v)); },
    getAttribute(k) { return attrs.has(k) ? attrs.get(k) : null; },
    removeAttribute(k) { attrs.delete(k); },
    closest() { return null; },
    focus() { n.focused = true; },
  };
  return n;
}

function spaceForm({ mode = "new", name = "", path = "~/deai-work/personal", color = "space-1" } = {}) {
  const nameI = node({ value: name });
  const pathI = node({ value: path });
  const hint = node({ hidden: true });
  const regHint = node({ hidden: true });
  const group = node();
  const colorI = node({ value: color });
  const swatches = SPACE_COLORS.map((c) => {
    const s = node({ dataset: { val: c }, tabIndex: c === color ? 0 : -1 });
    s.setAttribute("aria-checked", String(c === color));
    s.closest = (sel) => (sel === ".cv-color" ? s : null);
    return s;
  });
  const map = {
    "#sp-name": nameI, "#sp-path": mode === "new" ? pathI : null, "#sp-found": hint, "#sp-registered": regHint,
    ".cv-colors": group, 'input[name="color"]': colorI,
  };
  const form = {
    isConnected: true,
    querySelector: (sel) => map[sel] ?? null,
    querySelectorAll: (sel) => (sel === ".cv-color" ? swatches : []),
  };
  return { form, nameI, pathI, hint, regHint, group, colorI, swatches };
}

test("кружки: клік вибирає — значення, aria-checked і tabindex рухаються разом", () => {
  const d = spaceForm({ color: "space-1" });
  wireSpaceDialog(d.form, { mode: "edit" });
  d.group.fire("click", { target: d.swatches[2] });
  assert.equal(d.colorI.value, "space-3");
  assert.deepEqual(d.swatches.map((s) => s.getAttribute("aria-checked")), ["false", "false", "true", "false", "false", "false"]);
  assert.deepEqual(d.swatches.map((s) => s.tabIndex), [-1, -1, 0, -1, -1, -1]);
});

test("кружки: стрілки ходять по колу, фокус іде за вибором; чужа клавіша не гаситься", () => {
  const d = spaceForm({ color: "space-6" });
  wireSpaceDialog(d.form, { mode: "edit" });
  const e = d.group.fire("keydown", { key: "ArrowRight" });
  assert.equal(d.colorI.value, "space-1", "з кінця — на початок");
  assert.equal(e.prevented, true);
  assert.equal(d.swatches[0].focused, true);
  const back = d.group.fire("keydown", { key: "ArrowLeft" });
  assert.equal(d.colorI.value, "space-6");
  assert.equal(back.prevented, true);
  const tab = d.group.fire("keydown", { key: "Tab" });
  assert.equal(tab.prevented, undefined, "Tab — браузерний, `preventDefault` не чіпає");
  assert.equal(d.colorI.value, "space-6");
});

test("кружки: у знайденому просторі (aria-disabled) клік і стрілки нічого не міняють", () => {
  const d = spaceForm({ color: "space-2" });
  wireSpaceDialog(d.form, { mode: "edit" });
  d.group.setAttribute("aria-disabled", "true");
  d.group.fire("click", { target: d.swatches[4] });
  const e = d.group.fire("keydown", { key: "ArrowRight" });
  assert.equal(d.colorI.value, "space-2");
  assert.equal(e.prevented, undefined);
});

test("кружки: невідомий data-val у кліку — токен space-1, а не довільне значення", () => {
  const d = spaceForm({ color: "space-2" });
  wireSpaceDialog(d.form, { mode: "edit" });
  const evil = node({ dataset: { val: "red;position:fixed" } });
  evil.closest = (sel) => (sel === ".cv-color" ? evil : null);
  d.group.fire("click", { target: evil });
  assert.equal(d.colorI.value, "space-1");
});

test("`edit`: теки нема — лише кружки, жодного peek (навіть коли поле теки в формі раптом є)", async () => {
  let calls = 0;
  const peek = async () => { calls += 1; return {}; };
  /* Заглушка `mode: "new"` дає й поле теки: перевіряємо, що рішення «не питати» тримається
     на РЕЖИМІ, а не лише на відсутності поля в розмітці. */
  const d = spaceForm({ mode: "new" });
  wireSpaceDialog(d.form, { mode: "edit", peek, debounceMs: 1 });
  d.pathI.value = "~/x";
  d.pathI.fire("input");
  d.nameI.value = "Нова назва";
  d.nameI.fire("input");
  const plain = spaceForm({ mode: "edit" });
  wireSpaceDialog(plain.form, { mode: "edit", peek, debounceMs: 1 });
  await tick(25);
  assert.equal(calls, 0);
  assert.equal(d.pathI.value, "~/x", "у режимі edit тека за назвою не йде");
});

test("`new`: тека йде за назвою, доки її не правили руками", async () => {
  const d = spaceForm({ name: "", path: "~/deai-work/personal" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({}), debounceMs: 1 });
  d.nameI.value = "Client X";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/deai-work/client-x");
  d.pathI.value = "~/mine/x";
  d.pathI.fire("input");
  d.nameI.value = "Client Y";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/mine/x", "після ручної правки тека назві не підкоряється");
  await tick(20);
});

test("`new`: поле назви тільки для читання (знайдений простір) теку не рухає", async () => {
  const d = spaceForm({ name: "Знайдений", path: "~/found" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({}), debounceMs: 1 });
  d.nameI.readOnly = true;
  d.nameI.value = "хтось набрав";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/found");
  await tick(20);
});

test("`new`: назва кирилицею дає теку personal (слаг порожній)", async () => {
  const d = spaceForm({ name: "", path: "" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({}), debounceMs: 1 });
  d.nameI.value = "Особисте";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/deai-work/personal");
  await tick(20);
});

test("`new`: тека за назвою — ВІЛЬНА: зайняту реєстром (`taken`) пропускає", async () => {
  const taken = ["/Users/me/deai-work/personal", "/Users/me/deai-work/klient"];
  const d = spaceForm({ name: "", path: "" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({}), debounceMs: 1, taken });
  d.nameI.value = "Особисте";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/deai-work/space-2", "personal зайнятий першим простором");
  d.nameI.value = "Klient";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/deai-work/klient-2");
  await tick(20);
});

test("`new`: `taken` — функція, що читається при кожному використанні (реєстр міг оновитись, поки діалог відкритий)", async () => {
  let list = [];
  const d = spaceForm({ name: "", path: "" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({}), debounceMs: 1, taken: () => list });
  d.nameI.value = "Особисте";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/deai-work/personal");
  list = ["/Users/me/deai-work/personal"];          // агент завів простір, поки діалог був відкритий
  d.nameI.value = "Особисте ";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/deai-work/space-2");
  await tick(20);
});

test("peek: ЗАРЕЄСТРОВАНА тека — не «знайдений простір»: форма редагована, підказка «вже додано»", async () => {
  const d = spaceForm({ name: "Моє", color: "space-5", path: "~/deai-work/personal" });
  const peek = async () => ({ path: "/Users/me/deai-work/personal", exists: true, name: "Особисте", color: "space-2", tasks: 3 });
  wireSpaceDialog(d.form, { mode: "new", peek, debounceMs: 5, taken: ["/Users/me/deai-work/personal/"] });
  await tick(40);
  assert.equal(d.nameI.value, "Моє", "назву чужого простору не підставлено");
  assert.equal(d.nameI.readOnly, false, "поле назви не заблоковано");
  assert.equal(d.colorI.value, "space-5");
  assert.equal(d.group.getAttribute("aria-disabled"), null, "кружки не заблоковано");
  assert.equal(d.hint.hidden, true, "обіцянки «його задачі підхопляться» нема");
  assert.equal(d.regHint.hidden, false);
  assert.match(d.regHint.textContent, /вже додано/);
});

test("peek: `registered: true` від сервера — теж «вже додано», хоч клієнтський реєстр цієї теки не знає (варіант регістру на macOS)", async () => {
  const d = spaceForm({ name: "Моє", color: "space-5", path: "~/deai-work/CASEa" });
  const peek = async () => ({ path: "/Users/me/deai-work/CASEa", exists: true, name: "Чужа", color: "space-2", tasks: 2, registered: true });
  wireSpaceDialog(d.form, { mode: "new", peek, debounceMs: 5, taken: ["/Users/me/deai-work/caseA"] });
  await tick(40);
  assert.equal(d.regHint.hidden, false, "підказка «вже додано» не зʼявилась: форма вважає теку новою");
  assert.match(d.regHint.textContent, /вже додано/);
  assert.equal(d.nameI.value, "Моє", "назву чужого простору не підставлено");
  assert.equal(d.nameI.readOnly, false);
  assert.equal(d.hint.hidden, true, "обіцянки «його задачі підхопляться» нема");
  assert.equal(d.group.getAttribute("aria-disabled"), null);
});

test("peek: без `registered` клієнт сам порівнює з реєстром (запасний шлях); `registered` без `true` слова сервера не дає", async () => {
  const d = spaceForm({ name: "Моє", color: "space-5", path: "~/a" });
  const answers = [
    { path: "/Users/me/a", exists: true, name: "Чужа", color: "space-2" },
    { path: "/Users/me/b", exists: true, name: "Інша", color: "space-3", registered: false },
  ];
  wireSpaceDialog(d.form, { mode: "new", peek: async () => answers.shift(), debounceMs: 5, taken: ["/Users/me/a"] });
  await tick(30);
  assert.equal(d.regHint.hidden, false, "запасний шлях: реєстр клієнта знає теку");
  d.pathI.value = "~/b"; d.pathI.fire("input");
  await tick(30);
  assert.equal(d.regHint.hidden, true);
  assert.equal(d.nameI.value, "Інша", "`registered: false` — не слово сервера про реєстрацію");
});

test("peek: підказка «вже додано» знімається, щойно тека інша; не зареєстрована знайдена — як раніше", async () => {
  const d = spaceForm({ name: "Моє", color: "space-5", path: "~/a" });
  const answers = [
    { path: "/Users/me/a", exists: true, name: "Чужа", color: "space-2" },
    { path: "/Users/me/b", exists: true, name: "Інша", color: "space-3" },
    { path: "/Users/me/c", exists: true },
  ];
  wireSpaceDialog(d.form, { mode: "new", peek: async () => answers.shift(), debounceMs: 5, taken: ["/Users/me/a"] });
  await tick(30);
  assert.equal(d.regHint.hidden, false);
  d.pathI.value = "~/b"; d.pathI.fire("input");
  await tick(30);
  assert.equal(d.regHint.hidden, true);
  assert.equal(d.regHint.textContent, "");
  assert.equal(d.nameI.value, "Інша", "справжній знайдений простір (не в реєстрі) підхоплюється");
  assert.equal(d.nameI.readOnly, true);
  d.pathI.value = "~/c"; d.pathI.fire("input");
  await tick(30);
  assert.equal(d.nameI.value, "Моє");
  assert.equal(d.regHint.hidden, true);
});

test("peek: помилка шляху (`error`) не вважається зареєстрованою текою", async () => {
  const d = spaceForm({ path: "/x" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({ path: "/x", exists: false, error: "path-not-absolute" }), debounceMs: 5, taken: ["/x"] });
  await tick(30);
  assert.equal(d.regHint.hidden, true);
});

test("peek: дебаунс — серія правок дає ОДИН запит із останнім значенням", async () => {
  const d = spaceForm();
  const seen = [];
  wireSpaceDialog(d.form, { mode: "new", peek: async (p) => { seen.push(p); return {}; }, debounceMs: 15 });
  for (const v of ["~/a", "~/ab", "~/abc"]) { d.pathI.value = v; d.pathI.fire("input"); }
  await tick(60);
  assert.deepEqual(seen, ["~/abc"], "перший (початковий) запит поглинуто дебаунсом разом з усіма проміжними");
});

test("peek: початкова тека питається при відкритті", async () => {
  const d = spaceForm({ path: "~/deai-work/personal" });
  const seen = [];
  wireSpaceDialog(d.form, { mode: "new", peek: async (p) => { seen.push(p); return {}; }, debounceMs: 5 });
  await tick(40);
  assert.deepEqual(seen, ["~/deai-work/personal"]);
});

test("peek: знайдений простір підставляє назву й колір, блокує поля; інша тека — повертає людське", async () => {
  const d = spaceForm({ name: "Моє", color: "space-5", path: "~/a" });
  const answers = [
    { exists: true, name: "Чужа", color: "space-2", tasks: 4 },
    { exists: true },
  ];
  wireSpaceDialog(d.form, { mode: "new", peek: async () => answers.shift(), debounceMs: 5 });
  await tick(40);
  assert.equal(d.nameI.value, "Чужа");
  assert.equal(d.nameI.readOnly, true);
  assert.equal(d.colorI.value, "space-2");
  assert.equal(d.group.getAttribute("aria-disabled"), "true");
  assert.equal(d.hint.hidden, false);
  assert.match(d.hint.textContent, /«Чужа»/);

  d.pathI.value = "~/b";
  d.pathI.fire("input");
  await tick(40);
  assert.equal(d.nameI.value, "Моє", "набране людиною повернулось");
  assert.equal(d.nameI.readOnly, false);
  assert.equal(d.colorI.value, "space-5");
  assert.equal(d.group.getAttribute("aria-disabled"), null);
  assert.equal(d.hint.hidden, true);
  assert.equal(d.hint.textContent, "");
});

test("peek: перехід від знайденого до іншого знайденого не затирає стерті людські значення", async () => {
  const d = spaceForm({ name: "Моє", color: "space-5", path: "~/a" });
  const answers = [
    { exists: true, name: "Перша", color: "space-2" },
    { exists: true, name: "Друга", color: "space-3" },
    { exists: true },
  ];
  wireSpaceDialog(d.form, { mode: "new", peek: async () => answers.shift(), debounceMs: 5 });
  await tick(30);
  d.pathI.value = "~/b"; d.pathI.fire("input");
  await tick(30);
  assert.equal(d.nameI.value, "Друга");
  d.pathI.value = "~/c"; d.pathI.fire("input");
  await tick(30);
  assert.equal(d.nameI.value, "Моє", "людське значення пережило ДВА знайдені підряд");
  assert.equal(d.colorI.value, "space-5");
});

test("peek: відповідь, що приїхала ПІЗНІШЕ за новішу, відкидається (гонка)", async () => {
  const d = spaceForm({ name: "Моє", path: "~/slow" });
  const slowDone = [];
  const peek = (p) => (p === "~/slow"
    ? new Promise((resolve) => { slowDone.push(() => resolve({ exists: true, name: "Повільна", color: "space-2" })); })
    : Promise.resolve({ exists: true }));
  wireSpaceDialog(d.form, { mode: "new", peek, debounceMs: 3 });
  await tick(20);                       // перший запит (початкова тека) полетів і висить
  d.pathI.value = "~/fast"; d.pathI.fire("input");
  await tick(20);                       // другий уже відповів (не знайдено)
  slowDone[0]();                        // і лише тепер відповідає перший
  await tick(20);
  assert.equal(d.nameI.value, "Моє", "стара відповідь не підставила чужу назву");
  assert.equal(d.nameI.readOnly, false);
});

test("peek: форма вже закрита (isConnected=false) — запит не йде, відповідь не пишеться", async () => {
  const d = spaceForm({ path: "~/a" });
  let calls = 0;
  wireSpaceDialog(d.form, { mode: "new", peek: async () => { calls += 1; return { exists: true, name: "X" }; }, debounceMs: 10 });
  d.form.isConnected = false;
  await tick(40);
  assert.equal(calls, 0, "таймер після закриття діалогу не б'є в мережу");

  const d2 = spaceForm({ name: "Моє", path: "~/a" });
  wireSpaceDialog(d2.form, { mode: "new", peek: async () => { d2.form.isConnected = false; return { exists: true, name: "Чужа" }; }, debounceMs: 3 });
  await tick(30);
  assert.equal(d2.nameI.value, "Моє", "відповідь по закритій формі не торкається вузлів");
});

test("peek: збій мережі не кидає й нічого не підставляє", async () => {
  const d = spaceForm({ name: "Моє" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => { throw new Error("мережа"); }, debounceMs: 3 });
  await tick(30);
  assert.equal(d.nameI.value, "Моє");
  assert.equal(d.nameI.readOnly, false);
});

/* ── проводка форми задачі ─────────────────────────────────────────────── */

function taskForm(id = "") {
  const title = node();
  const idI = node({ value: id });
  const map = { "#tf-title": title, "#tf-id": idI };
  return { form: { isConnected: true, querySelector: (sel) => map[sel] ?? null }, title, idI };
}

test("форма задачі: id іде за назвою (вільний, без регістру), порожня назва — порожній id", () => {
  const d = taskForm();
  wireTaskForm(d.form, { taken: ["landing-page-v2"] });
  d.title.value = "Landing page v2";
  d.title.fire("input");
  assert.equal(d.idI.value, "landing-page-v2-2", "зайнятий — наступний вільний");
  d.title.value = "Головна";
  d.title.fire("input");
  assert.equal(d.idI.value, "task-1", "назва кирилицею — task-N");
  d.title.value = "   ";
  d.title.fire("input");
  assert.equal(d.idI.value, "");
});

test("форма задачі: ручна правка id зупиняє автопідстановку; очистка поля вертає її", () => {
  const d = taskForm();
  wireTaskForm(d.form, { taken: [] });
  d.title.value = "Alpha";
  d.title.fire("input");
  assert.equal(d.idI.value, "alpha");
  d.idI.value = "mine";
  d.idI.fire("input");
  d.title.value = "Beta";
  d.title.fire("input");
  assert.equal(d.idI.value, "mine", "id, який людина написала, не перетирається");
  d.idI.value = "";
  d.idI.fire("input");
  assert.equal(d.idI.value, "beta", "очистила — автопідстановка повернулась");
});

test("форма задачі: форма відкрилась з готовим id — це вже «правлений руками»", () => {
  const d = taskForm("preset");
  wireTaskForm(d.form, { taken: [] });
  d.title.value = "Other";
  d.title.fire("input");
  assert.equal(d.idI.value, "preset");
});

test("форма задачі: зайняті id приїхали ПІСЛЯ відкриття — id перераховується", async () => {
  const d = taskForm();
  let resolve;
  const taken = new Promise((r) => { resolve = r; });
  wireTaskForm(d.form, { taken });
  d.title.value = "Alpha";
  d.title.fire("input");
  assert.equal(d.idI.value, "alpha", "поки перелік у дорозі — id без нього");
  resolve(["alpha"]);
  await tick(5);
  assert.equal(d.idI.value, "alpha-2");
});

test("форма задачі: перелік приїхав, а id уже правлено руками — не чіпаємо; відхилений перелік не кидає", async () => {
  const d = taskForm();
  let resolve;
  wireTaskForm(d.form, { taken: new Promise((r) => { resolve = r; }) });
  d.idI.value = "mine";
  d.idI.fire("input");
  resolve(["mine"]);
  await tick(5);
  assert.equal(d.idI.value, "mine");

  const d2 = taskForm();
  wireTaskForm(d2.form, { taken: Promise.reject(new Error("мережа")) });
  await tick(5);
  d2.title.value = "Alpha";
  d2.title.fire("input");
  assert.equal(d2.idI.value, "alpha");
});

test("форма задачі: форма вже закрита — перелік, що приїхав, id не пише", async () => {
  const d = taskForm();
  let resolve;
  wireTaskForm(d.form, { taken: new Promise((r) => { resolve = r; }) });
  d.title.value = "Alpha";
  d.title.fire("input");
  d.form.isConnected = false;
  resolve(["alpha"]);
  await tick(5);
  assert.equal(d.idI.value, "alpha", "закрита форма не перераховується");
});

test("`new` з `pathTouched: true`: тека за назвою не йде (перемальовка майстра не скидає ручну правку)", async () => {
  const d = spaceForm({ name: "", path: "~/mine/x" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({}), debounceMs: 1, pathTouched: true });
  d.nameI.value = "Client";
  d.nameI.fire("input");
  assert.equal(d.pathI.value, "~/mine/x");
  await tick(20);
});

test("форма задачі з `idTouched: false`: непорожній id (автопідстановка до перемальовки) і далі йде за назвою", () => {
  const d = taskForm("alpha");
  wireTaskForm(d.form, { taken: [], idTouched: false });
  d.title.value = "Beta";
  d.title.fire("input");
  assert.equal(d.idI.value, "beta");
});

test("форма задачі з `idTouched: true`: порожній id (правили й стерли до перемальовки) не підставляється за назвою", () => {
  const d = taskForm("");
  wireTaskForm(d.form, { taken: [], idTouched: true });
  d.title.value = "Beta";
  d.title.fire("input");
  assert.equal(d.idI.value, "", "людина свідомо лишила id порожнім — не чіпаємо");
});

test("`new` без `pathTouched`: тека йде за назвою (типово не змінилось)", async () => {
  const d = spaceForm({ name: "", path: "~/deai-work/personal" });
  wireSpaceDialog(d.form, { mode: "new", peek: async () => ({}), debounceMs: 1 });
  d.nameI.value = "Client";
  d.nameI.fire("input");
  assert.notEqual(d.pathI.value, "~/deai-work/personal");
  assert.match(d.pathI.value, /client/);
  await tick(20);
});
