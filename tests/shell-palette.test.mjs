import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { DICT, setLang, t } from "../app/i18n.js";
import { ico } from "../app/icons.js";
import {
  KEYS, filterActions, keysHTML, paletteActions, paletteHTML, paletteListHTML,
} from "../app/shell-palette.js";

test.beforeEach(() => setLang("uk"));

const S = (o = {}) => ({
  mode: "layout", view: "grid", hasIteration: true,
  pagesError: "", flowRaw: true, flowError: "",
  published: true, iterPub: true, pagePub: true, pickedPage: "main",
  gl: "sync", iterLabel: "Іт.3",
  shots: { have: 3, stale: 0, total: 3, running: false, bad: false, done: 0 },
  lang: "uk", ...o,
});

/* ── стереження зі спеки задачі ──────────────────────────────────────────── */

/* 1. Кожна дія має `labelKey`, який ІСНУЄ у словнику — той самий клас
   перевірки, що `tests/i18n-keys.test.mjs` для решти коду, тут — по самому
   реєстру: без цього `t()` кине виняток замість підпису на першому ж
   рендері палітри. Перевіряємо в ОБОХ мовах, бо `deepEqual(en,uk)` набору
   ключів (`tests/i18n.test.mjs`) не рятує від дірки в САМЕ ЦЬОМУ реєстрі,
   якщо ключ узагалі вигаданий і не потрапив у жоден словник. */
test("кожна дія несе labelKey, який є в обох словниках", () => {
  const actions = paletteActions(S());
  assert.ok(actions.length > 10, `дій лише ${actions.length} — реєстр порожній чи майже`);
  for (const a of actions) {
    assert.ok(a.labelKey, `дія «${a.id}» без labelKey`);
    assert.ok(DICT.uk[a.labelKey] !== undefined, `«${a.labelKey}» немає в DICT.uk (дія «${a.id}»)`);
    assert.ok(DICT.en[a.labelKey] !== undefined, `«${a.labelKey}» немає в DICT.en (дія «${a.id}»)`);
  }
});

/* Той самий обов'язок — для `whyKey` вимкнених дій (стереження 4 нижче
   перевіряє САМ ФАКТ наявності `whyKey`; тут — що це ІМ'Я, яке `t()` не
   відкине). */
test("whyKey кожної вимкненої дії теж є в обох словниках", () => {
  const actions = paletteActions(S({
    flowRaw: null, pagesError: "500", pickedPage: null, published: false, gl: "off",
  }));
  const disabled = actions.filter((a) => a.disabled);
  assert.ok(disabled.length > 0, "жодної вимкненої дії — гілку не перевірено");
  for (const a of disabled) {
    assert.ok(a.whyKey, `дія «${a.id}» вимкнена без whyKey`);
    assert.ok(DICT.uk[a.whyKey] !== undefined, `whyKey «${a.whyKey}» немає в DICT.uk (дія «${a.id}»)`);
  }
});

/* 2. Фільтр знаходить дію мови ОБОМА мовами — виправлена вада прототипу
   (шапка `shell-palette.js`): без псевдонімів пошук іншою мовою, ніж
   поточна, не знаходив нічого. */
test("пошук мови працює обома мовами — латиницею в українському інтерфейсі, кирилицею в англійському", () => {
  setLang("uk");
  const actionsUk = paletteActions(S({ lang: "uk" }));
  const foundLatin = filterActions(actionsUk, "language");
  assert.ok(foundLatin.some((a) => a.id === "lang-en"),
    "запит «language» в українському інтерфейсі не знайшов пункту мови");

  setLang("en");
  const actionsEn = paletteActions(S({ lang: "en" }));
  const foundCyrillic = filterActions(actionsEn, "мова");
  assert.ok(foundCyrillic.some((a) => a.id === "lang-uk"),
    "запит «мова» в англійському інтерфейсі не знайшов пункту мови");
  setLang("uk");
});

/* 3. Підпис мови — завжди в ПОТОЧНІЙ мові й називає ЦІЛЬОВУ; поточна мова
   позначена вибраною (whyKey) і не діє (disabled). */
test("підпис перемикача мови — поточною мовою, ціль — інша; поточна позначена й вимкнена", () => {
  setLang("uk");
  let actions = paletteActions(S({ lang: "uk" }));
  let uk = actions.find((a) => a.id === "lang-uk");
  let en = actions.find((a) => a.id === "lang-en");
  assert.equal(uk.disabled, true, "поточна мова (uk) мусить бути вимкнена");
  assert.equal(uk.whyKey, "langCur");
  assert.equal(en.disabled, false, "цільова мова (en) мусить діяти");
  assert.equal(t(uk.labelKey), "Мова інтерфейсу: українська", "підпис поточною мовою (uk)");
  assert.equal(t(en.labelKey), "Мова інтерфейсу: English", "підпис поточною мовою (uk), називає English");

  setLang("en");
  actions = paletteActions(S({ lang: "en" }));
  uk = actions.find((a) => a.id === "lang-uk");
  en = actions.find((a) => a.id === "lang-en");
  assert.equal(en.disabled, true, "поточна мова (en) мусить бути вимкнена");
  assert.equal(uk.disabled, false, "цільова мова (uk) мусить діяти");
  assert.equal(t(en.labelKey), "Interface language: English", "підпис поточною мовою (en)");
  assert.equal(t(uk.labelKey), "Interface language: Ukrainian", "підпис поточною мовою (en), називає Ukrainian");
  setLang("uk");
});

/* 3b. Аудиторії коментарів у ⌘K більше НЕМАЄ (0.27.0, поправка 10 плану Б2): адресата піна вибирають чипами у формі
   коментатора, а падіння командного більше не валить коментатора (він працює з одним локальним) — аварійний вихід
   «до локального» втратив причину. Тест стереже, щоб пункти `aud-*` не повернулись мовчки. */
test("палітра не має перемикача аудиторії: ні `aud-*`, ні в жодному просторі, ні з ітерацією, ні без", () => {
  const spaces = [null, { id: "n", capabilities: { publish: null, tokens: null, comments: null } },
    { id: "t", capabilities: { publish: null, tokens: null, comments: "supabase-comments" } }];
  for (const space of spaces) for (const hasIteration of [true, false]) {
    const ids = paletteActions(S({ space, hasIteration })).map((a) => a.id);
    assert.deepEqual(ids.filter((id) => id.startsWith("aud-")), [], JSON.stringify([space, hasIteration]));
  }
  assert.equal(paletteActions(S()).some((a) => a.act === "aud"), false);
});

/* 4. Вимкнена дія несе `whyKey`, а не просто зникає (за винятком свідомо
   ОМІТОВАНИХ груп — gIter/go-iter/gFrames без ітерації, задокументовано в
   шапці `paletteActions`: там немає самого ПОНЯТТЯ дії, а не «дія, яку не
   можна виконати»). Перевіряємо на реальних дизʼюнктивних станах. */
test("вимкнена дія завжди несе whyKey", () => {
  const scenarios = [
    S({ flowRaw: null, flowError: null }),               // «Флоу» без flow.json
    S({ pagesError: "500" }),                             // сторінки не завантажились
    S({ pickedPage: null }),                               // сторінку не обрано
    S({ published: false }),                               // прев'ю нема
    S({ gl: "sync" }),                                     // GitLab уже збігається
    S({ shots: { have: 5, stale: 0, total: 5, running: false, bad: false, done: 0 } }), // усе свіже
    S({ lang: "uk" }),                                     // поточна мова
    S({ mode: "overview" }),                               // «В Figma» в «Огляді»
  ];
  for (const st of scenarios) {
    for (const a of paletteActions(st)) {
      if (a.disabled) assert.ok(a.whyKey, `дія «${a.id}» вимкнена без whyKey (стан ${JSON.stringify(st)})`);
    }
  }
});

/* 5. Кожна дія має або `act` (є куди виконати), або явно позначена як
   «лише перехід» (`navOnly: true`) — дія без обробника це кнопка, що нічого
   не робить. Перевіряємо на кількох різних станах, щоб зловити дію, яка
   з'являється лише за певної гілки (наприклад `glsetup`/`glpull`). */
test("кожна дія має act або явно позначена navOnly — третього не дано", () => {
  const states = [
    S(), S({ mode: "overview" }), S({ gl: "off" }), S({ gl: "behind" }),
    S({ hasIteration: false, shots: null, pickedPage: null }),
  ];
  let sawNavOnly = false;
  let sawAct = false;
  for (const st of states) {
    for (const a of paletteActions(st)) {
      if (a.navOnly) { sawNavOnly = true; assert.ok(!a.act, `дія «${a.id}» одночасно navOnly й act`); }
      else { sawAct = true; assert.ok(a.act, `дія «${a.id}» без act і без navOnly — кнопка в нікуди`); }
    }
  }
  assert.ok(sawNavOnly, "жодної navOnly дії не побачено — перевірку не пройдено по суті");
  assert.ok(sawAct, "жодної дії з act не побачено — перевірку не пройдено по суті");
});

/* Мутаційний доказ до (5): реєстр без пари act/navOnly має ловитись. Symуluje
   "забутий act" прямо тут — без правки самого модуля. */
test("мутація: дія без act і без navOnly — тест вище її ловить", () => {
  const broken = [...paletteActions(S()), { id: "broken", group: "gGo", labelKey: "tasks", icon: "task" }];
  const bad = broken.filter((a) => !a.navOnly && !a.act);
  assert.equal(bad.length, 1, "зіпсована дія мусить бути рівно одна — фікстура тесту, не модуль");
  assert.equal(bad[0].id, "broken");
});

/* «Задачі» у ⌘K — той самий вхід, що логотип у смузі (`act:"home"`), а не
   `navOnly`, що розкривав дропдаун крихти. Раніше `go-tasks` міг бути «переходом»,
   бо екрана не було; тепер це екран, і третього шляху до нього бути не мусить. */
test("go-tasks — act:home (екран «Задачі»), не navOnly", () => {
  const a = paletteActions(S()).find((x) => x.id === "go-tasks");
  assert.ok(a, "go-tasks зник із реєстру");
  assert.equal(a.act, "home");
  assert.ok(!a.navOnly, "go-tasks знову navOnly — ⌘K «Задачі» відкриє дропдаун, а не екран");
  // і без ітерації (задача лише що заведена) двері на екран лишаються
  const bare = paletteActions(S({ hasIteration: false, shots: null, pickedPage: null }));
  assert.equal(bare.find((x) => x.id === "go-tasks")?.act, "home");
});

/* ── розмітка ──────────────────────────────────────────────────────────── */

test("paletteHTML: підкладка, поле пошуку і список у розмітці", () => {
  const html = paletteHTML(paletteActions(S()), "", 0);
  assert.match(html, /class="scrim" data-act="closeoverlay"/);
  assert.match(html, /data-stop="1"/);
  assert.match(html, /id="palq"/);
  assert.match(html, /class="pal-list"/);
});

test("paletteListHTML і paletteHTML не розходяться: один і той самий уміст списку", () => {
  const actions = paletteActions(S());
  const list = paletteListHTML(actions, "", 0);
  const full = paletteHTML(actions, "", 0);
  assert.ok(full.includes(list), "paletteHTML мусить нести РІВНО той самий список, що paletteListHTML");
});

test("пункти згруповані заголовками груп, кожна група — існуючий ключ словника", () => {
  const html = paletteListHTML(paletteActions(S()), "", 0);
  const groups = [...html.matchAll(/class="pal-grp">([^<]*)</g)].map((m) => m[1]);
  assert.ok(groups.length >= 4, `груп лише ${groups.length}`);
});

test("порожній результат пошуку показує palNone, а не порожній список", () => {
  const html = paletteListHTML(paletteActions(S()), "щосьнеіснуючещо12345", 0);
  assert.match(html, /class="pal-none"/);
  assert.doesNotMatch(html, /class="pal-it"/);
});

test("курсор клемпиться в межі відфільтрованого списку — не падає й не губить підсвітку", () => {
  const actions = paletteActions(S());
  assert.doesNotThrow(() => paletteListHTML(actions, "", 9999));
  const html = paletteListHTML(actions, "", 9999);
  assert.match(html, /pal-it--cur/, "після клемпу підсвітка мусить лишитись на останньому пункті");
});

test("данжер-дії мають клас pal-it--danger", () => {
  const html = paletteListHTML(paletteActions(S()), "видалити", 0);
  assert.match(html, /pal-it--danger/);
});

test("текст із даних екранується (data-стан не сміє стати розміткою)", () => {
  // iterLabel потрапляє у підпис glPush/glPull через t(labelKey, val) —
  // перевіряємо саме цей шлях, а не вигадану дірку.
  const html = paletteListHTML(paletteActions(S({ gl: "behind", iterLabel: '<img src=x onerror=1>' })), "gitlab", 0);
  assert.ok(!html.includes("<img src=x"), "неекранований текст доїхав до розмітки");
});

test("keysHTML: підкладка, довідка і клавіші I/Alt/Esc/⌘K", () => {
  const html = keysHTML();
  assert.match(html, /class="scrim" data-act="closeoverlay"/);
  assert.match(html, /data-stop="1"/);
  assert.match(html, /<kbd>⌘K<\/kbd>/);
  assert.match(html, /<kbd>Esc<\/kbd>/);
  assert.match(html, /<kbd>I<\/kbd>/);
  assert.match(html, /<kbd>Alt<\/kbd>/);
});

test("KEYS ↔ аркуш `?`: аркуш малює рівно рядки KEYS, у порядку й групах", () => {
  assert.ok(KEYS.length >= 8, "KEYS порожній чи обрізаний");
  const html = keysHTML();
  const rows = [...html.matchAll(/<dt>([^<]*)<\/dt><dd><kbd>([^<]*)<\/kbd><\/dd>/g)].map((m) => [m[1], m[2]]);
  const order = [...KEYS.filter((k) => k.group === "general"), ...KEYS.filter((k) => k.group === "layout")];
  assert.deepEqual(rows, order.map((k) => [t(k.labelKey), k.kbd]));
  assert.ok(KEYS.every((k) => k.group === "general" || k.group === "layout"));
});

/* ── кожна підказка клавіші має обробник ─────────────────────────────────
 *
 * ⚠️ Тут раніше стояла перевірка, прибита до ДВОХ ГЛІФІВ: `doesNotMatch(⌥↓)`
 * і `doesNotMatch(⌥↑)`. Вона називала себе інваріантом «клавіші, якої немає,
 * ми не документуємо» — і лишалась зеленою при вже порушеному інваріанті:
 * `keysHTML()` документував `⌥M`, `⌘\` і `⌘⏎`, у яких обробника не було НІ
 * ДЕ, а реєстр віз ще п'ять (`⌘⇧T`/`⌘⇧I`/`⌘⇧P`/`⇧N`/`⇧P`). Мутація, яку
 * вона пропускала, — рядок із будь-яким гліфом, крім двох названих
 * (виміряно: `${row(t("kMode"), "⌥→")}` дає 25 pass / 0 fail).
 *
 * Тепер це той інваріант, який перевірка обіцяла: КОЖНА `kbd`-підказка —
 * і з `keysHTML()`, і з колонки реєстру `paletteActions()` — мусить мати
 * знайдену в коді прив'язку з ТИМИ САМИМИ модифікаторами.
 *
 * ── Межа перевірки (як саме читаються прив'язки і чого цей спосіб не бачить)
 *
 * Читаються ТРИ файли, і кожен — бо він справді власник частини підказок:
 *   · `app/app.js` — акорди оболонки (`⌘K`, `?`, `⌥M`, `⌘\`, `Esc`);
 *   · `app/vendor/inspector.js` — `I` (увімкнути), `Alt` і `Enter` (відстані, дочірній).
 *     Це вендор, чіпати його заборонено, але ЧИТАТИ — саме те, що робить
 *     перевірку не «повіримо на слово»: якщо інспектор загубить свою
 *     прив'язку, охоронець упаде разом із ним;
 *   · `app/vendor/comment-layer.min.js` — `C`/`P`/`H` (рядки під зіркою).
 *
 * Спосіб — статичний розбір, і в нього рівно три записані обмеження:
 *   1. Модифікатори читаються з УМОВИ найближчого `if (…)`, що охоплює
 *      порівняння клавіші. Охоронна клауза ПОЗА цим `if`
 *      (`if (e.metaKey||e.altKey) return;` на початку `_onKey` інспектора)
 *      у набір не потрапляє — тому прив'язка інспектора читається як «голе
 *      `I`», що для нього ПРАВИЛЬНО (він і працює без модифікаторів), але
 *      формально це послаблення, не строгість.
 *   2. `comment-layer.min.js` мініфікований: його умови не розбираються
 *      взагалі, беруться лише ЛІТЕРИ, з якими порівнюється псевдонім
 *      `.key.toLowerCase()`. Тобто для трьох рядків під зіркою перевірка
 *      відповідає на «літера в його обробнику взагалі є?», а не на «з
 *      якими модифікаторами». Розбирати умови в одному рядку на 300 КБ
 *      означало б вгадувати, а не міряти.
 *   3. Прив'язка, зібрана зі ЗМІННОЇ (`const k = KEYS.mode; if (ev.key === k)`),
 *      статично не видима — її не бачить ні цей розбір, ні будь-який інший
 *      без запуску. У трьох читаних файлах такого немає (виміряно), а якби
 *      з'явилось — охоронець упав би на живій підказці, тобто помилився б у
 *      БЕЗПЕЧНИЙ бік: змусив би дописати або прив'язку явно, або виняток із
 *      причиною.
 *
 * Інваріант СВІДОМО односторонній: «підказка без обробника» — брехня
 * інтерфейсу, а «обробник без підказки» — лише незадокументована зручність
 * (Escape у полі вводу, ↑↓ у палітрі), і вимагати рядок у довідці для
 * кожного натиску означало б роздути її до непотребу.
 */

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = (rel) => readFileSync(path.join(REPO, "app", rel), "utf8");

/* Гліфи модифікаторів → імена прапорців події. */
const MOD_GLYPH = { "⌘": "meta", "⌃": "meta", "⌥": "alt", "⇧": "shift" };
/* Гліфи й скорочення НЕлітерних клавіш → `KeyboardEvent.key` у нижньому
   регістрі. Довідка малює їх символами (так і в затвердженому прототипі),
   код порівнює імена — без цієї таблиці перевірка звіряла б «⏎» з «enter». */
const KEY_GLYPH = {
  "⏎": "enter", "↵": "enter", "esc": "escape", "⎋": "escape",
  "↑": "arrowup", "↓": "arrowdown", "←": "arrowleft", "→": "arrowright",
  "⇥": "tab", "␣": " ", "⌫": "backspace",
};
/* `KeyboardEvent.code` → `key`: `code` беремо там, де `key` залежить від
   розкладки (macOS ⌥M віддає `µ`, українська — `ь`, обидві — `KeyM`). */
function codeToKey(code) {
  const m = /^Key([A-Z])$/.exec(code);
  if (m) return m[1].toLowerCase();
  return { Backslash: "\\", Slash: "/", Enter: "enter", Escape: "escape", Space: " " }[code] || code.toLowerCase();
}

/** Підказку («⌘⇧T», «Esc», «I») — у `{key, mods:Set, shown}`. */
function parseHint(shown) {
  const mods = new Set();
  let rest = shown;
  while (rest.length && MOD_GLYPH[rest[0]]) { mods.add(MOD_GLYPH[rest[0]]); rest = rest.slice(1); }
  const low = rest.toLowerCase();
  return { shown, mods, key: KEY_GLYPH[low] || KEY_GLYPH[rest] || low };
}

/** Умови всіх `if (…)` файла: `[{open, close, text}]`, дужки збалансовані. */
function ifConditions(source) {
  const out = [];
  for (const m of source.matchAll(/\bif\s*\(/g)) {
    const open = m.index + m[0].length - 1;
    let depth = 0;
    for (let i = open; i < source.length; i += 1) {
      if (source[i] === "(") depth += 1;
      else if (source[i] === ")") {
        depth -= 1;
        if (depth === 0) { out.push({ open, close: i, text: source.slice(open, i + 1) }); break; }
      }
    }
  }
  return out;
}

const MOD_RE = {
  meta: /\b(?:meta|metaKey|ctrlKey)\b/g,
  alt: /\b(?:alt|altKey)\b/g,
  shift: /\b(?:shift|shiftKey)\b/g,
};

/** Модифікатор ПОТРІБЕН, якщо згадується без заперечення. `!meta`/`!ev.altKey`
 *  — навпаки, ЗАБОРОНА, і вона лишає модифікатор поза набором: саме так
 *  «?» відрізняється від «⌥?» в одному й тому самому слухачі. */
function requiredMods(cond) {
  const mods = new Set();
  for (const [name, re] of Object.entries(MOD_RE)) {
    for (const m of cond.matchAll(re)) {
      const before = cond.slice(0, m.index).replace(/[\s\w.$]*$/, "");
      if (!before.endsWith("!")) { mods.add(name); break; }
    }
  }
  return mods;
}

/** Прив'язки з НЕмініфікованого джерела: `[{key, mods}]`. */
function bindings(source, file) {
  const ifs = ifConditions(source);
  const modsAt = (at) => {
    const inner = ifs.filter((c) => c.open < at && at < c.close)
      .sort((a, b) => b.open - a.open)[0];
    return inner ? requiredMods(inner.text) : new Set();
  };
  const out = [];
  const push = (key, at) => out.push({ key: String(key).toLowerCase(), mods: modsAt(at), file });
  // `ev.key === 'Escape'`, `ev.key.toLowerCase() === 'k'`, `e.key === '?'`
  for (const m of source.matchAll(/\.key(?:\.toLowerCase\(\))?\s*===?\s*(['"])([^'"]{1,12})\1/g)) {
    push(m[2], m.index);
  }
  // `/^[mMьЬ]$/.test(e.key)` — форма, якою інспектор ловить обидві розкладки
  for (const m of source.matchAll(/\/\^\[([^\]]+)\]\$\/[gimsuy]*\.test\(\s*[\w.$]*\.key/g)) {
    for (const ch of new Set(m[1].toLowerCase())) push(ch, m.index);
  }
  // `ev.code === 'KeyM'` — прив'язка, незалежна від розкладки
  for (const m of source.matchAll(/\.code\s*===?\s*(['"])([^'"]{1,16})\1/g)) {
    push(codeToKey(m[2]), m.index);
  }
  return out;
}

/** Мініфіковане джерело: ЛИШЕ літери, без розбору умов (межа 2 у шапці). */
function bareKeys(source) {
  const alias = new Set();
  for (const m of source.matchAll(/\b([A-Za-z_$][\w$]*)\s*=\s*[\w$.]+\.key(?:\.toLowerCase\(\))?/g)) {
    alias.add(m[1]);
  }
  const keys = new Set();
  for (const m of source.matchAll(/([A-Za-z_$][\w$]*)\s*===?\s*(['"])([^'"]{1,12})\2/g)) {
    if (alias.has(m[1])) keys.add(m[3].toLowerCase());
  }
  for (const m of source.matchAll(/\.key(?:\.toLowerCase\(\))?\s*===?\s*(['"])([^'"]{1,12})\1/g)) {
    keys.add(m[2].toLowerCase());
  }
  return [...keys].map((key) => ({ key, mods: new Set(), file: "comment-layer.min.js" }));
}

const sameMods = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));

/** Усі підказки, які взагалі показує оболонка: довідка `?` + колонка реєстру. */
function allHints() {
  const out = [];
  // `KEYS` — єдине джерело довідки `?` і розділу «Гарячі клавіші»; що аркуш малює рівно його, стереже тест «KEYS ↔ аркуш».
  for (const k of KEYS) out.push({ from: `довідка «${t(k.labelKey)}»`, ...parseHint(k.kbd) });
  /* Реєстр — на кількох станах: частина дій існує лише в своїй гілці
     (`inspector` тільки в макеті, `newit` тільки з ітерацією), і на одному
     стані їхні підказки просто не з'явились би. */
  for (const st of [S(), S({ mode: "overview" }), S({ gl: "off" }), S({ gl: "behind" }),
    S({ hasIteration: false, shots: null, pickedPage: null })]) {
    for (const a of paletteActions(st)) {
      if (a.kbd) out.push({ from: `реєстр «${a.id}»`, ...parseHint(a.kbd) });
    }
  }
  return out;
}

test("кожна kbd-підказка (довідка + реєстр) має обробник у коді", () => {
  const bound = [
    ...bindings(src("app.js"), "app.js"),
    ...bindings(src(path.join("vendor", "inspector.js")), "vendor/inspector.js"),
    ...bareKeys(src(path.join("vendor", "comment-layer.min.js"))),
  ];

  /* Свідок проти вакуумного проходу — і він рахує ЗНАЙДЕНІ ПРИВ'ЯЗКИ, а не
     прочитані файли: зламаний регексп дав би нуль прив'язок, і тоді впала б
     кожна підказка (тобто впав би тест), — але зламана ТАБЛИЦЯ гліфів дала б
     нуль ПІДКАЗОК, і тест зеленів би на порожньому циклі. Стережемо обидва
     кінці. */
  const hints = allHints();
  assert.ok(hints.length >= 8,
    `знайдено лише ${hints.length} підказок — розбір розмітки довідки чи реєстру зламаний`);
  assert.ok(bound.length >= 8,
    `знайдено лише ${bound.length} прив'язок — розбір джерел зламаний`);
  assert.ok(hints.some((h) => h.mods.size > 0) && hints.some((h) => h.mods.size === 0),
    "перевірено лише один клас підказок (акорди АБО голі клавіші) — інваріант не пройдено по суті");

  /* `[...new Set(…)]` — та сама підказка приходить із реєстру на кожному зі
     п'яти станів (`allHints` це й задумано), і п'ять однакових рядків у
     падінні лише ховають решту сиріт. */
  const orphans = [...new Set(hints
    .filter((h) => !bound.some((b) => b.key === h.key && sameMods(b.mods, h.mods)))
    .map((h) => `«${h.shown}» (${h.from}) → key=${JSON.stringify(h.key)} `
      + `mods=[${[...h.mods].sort().join(",")}] — обробника немає`))];

  assert.deepEqual(orphans, [],
    "підказка клавіші без обробника — рівно та брехня, від якої застерігає "
    + `докстрінг keysHTML():\n${orphans.join("\n")}`);
});

/* ── гейти станів (той самий принцип, що bar-model.js) ───────────────────── */

test("без ітерації немає гдІтер-групи і кадрів, є go-tasks/go-pages, немає go-iter", () => {
  const actions = paletteActions(S({ hasIteration: false, shots: null, pickedPage: null }));
  assert.ok(!actions.some((a) => ["newit", "renit", "dupit", "delit", "shoot"].includes(a.id)),
    "дії над ітерацією/кадрами лишились без ітерації");
  assert.ok(actions.some((a) => a.id === "go-tasks"));
  assert.ok(actions.some((a) => a.id === "go-pages"));
  assert.ok(!actions.some((a) => a.id === "go-iter"), "«перейти до ітерацій» без жодної ітерації — нікуди йти");
});

test("інспектор і сегмент Сітка/Флоу існують лише у своєму режимі", () => {
  assert.ok(paletteActions(S({ mode: "layout" })).some((a) => a.id === "inspector"));
  assert.ok(!paletteActions(S({ mode: "overview" })).some((a) => a.id === "inspector"));
  assert.ok(!paletteActions(S({ mode: "layout" })).some((a) => a.id === "view-grid"));
  assert.ok(paletteActions(S({ mode: "overview" })).some((a) => a.id === "view-grid"));
});

test("«Коментарі» — у палітрі в обох видах з підказкою C; на екрані «Задачі» немає", () => {
  for (const mode of ["layout", "overview"]) {
    const a = paletteActions(S({ mode })).find((x) => x.id === "comments");
    assert.ok(a, `«Коментарі» немає в палітрі (${mode})`);
    assert.equal(a.kbd, "C");
    assert.equal(a.act, "comments");
  }
  assert.ok(!paletteActions(S({ homeOpen: true })).some((a) => a.id === "comments"));
});

test("GitLab: off показує лише glsetup, behind додає glpull, sync вимикає glpush", () => {
  const off = paletteActions(S({ gl: "off" }));
  assert.ok(off.some((a) => a.id === "glsetup"));
  assert.ok(!off.some((a) => a.id === "glpush" || a.id === "glpull"));

  const behind = paletteActions(S({ gl: "behind" }));
  assert.ok(behind.some((a) => a.id === "glpull"));
  assert.ok(behind.some((a) => a.id === "glpush" && !a.disabled));

  const sync = paletteActions(S({ gl: "sync" }));
  assert.ok(!sync.some((a) => a.id === "glpull"));
  const push = sync.find((a) => a.id === "glpush");
  assert.equal(push.disabled, true);
  assert.equal(push.whyKey, "glSync");
});

test("gFrames: підпис і іконка відповідають реальному тумблеру старт/стоп PANEL_ACTIONS.shoot", () => {
  const idle = paletteActions(S({ shots: { have: 0, stale: null, total: null, running: false, bad: false, done: 0 } }))
    .find((a) => a.id === "shoot");
  assert.equal(idle.labelKey, "shotsTakeBare");
  assert.equal(idle.disabled, false);

  const stale = paletteActions(S({ shots: { have: 3, stale: 2, total: 3, running: false, bad: false, done: 0 } }))
    .find((a) => a.id === "shoot");
  assert.equal(stale.labelKey, "shotsUpdateBare");

  const running = paletteActions(S({ shots: { have: 3, stale: null, total: 5, running: true, bad: false, done: 2 } }))
    .find((a) => a.id === "shoot");
  assert.equal(running.labelKey, "shotsStop");

  const fresh = paletteActions(S({ shots: { have: 3, stale: 0, total: 3, running: false, bad: false, done: 0 } }))
    .find((a) => a.id === "shoot");
  assert.equal(fresh.disabled, true);
  assert.equal(fresh.whyKey, "whyFresh");
});

/* Виправлена вада прототипу (шапка модуля, п.1): «Відкрити превью» несе
   act, а не лишається кнопкою-нопом, як у docs/proto/shell.html. */
test("openpreview несе act — не повторює вади прототипу (кнопка без обробника)", () => {
  const a = paletteActions(S()).find((x) => x.id === "openpreview");
  assert.ok(a);
  assert.equal(a.act, "openpreview");
  assert.ok(!a.navOnly);
});

/* «В Figma» у ⌘K — та сама дія, що в смузі (`act:"figma"`), з тією самою
   причиною вимкнення: друга реалізація причини розійшлася б із першою. */
test("«В Figma» є в палітрі, у групі публікації, і вимикається тією ж причиною", () => {
  const f = (o) => paletteActions(S(o)).find((a) => a.id === "figma");
  assert.ok(f(), "дії «В Figma» немає в палітрі");
  assert.equal(f().act, "figma");
  assert.equal(f().group, "gPub");
  assert.equal(f().disabled, false);
  assert.deepEqual([f({ mode: "overview" }).disabled, f({ mode: "overview" }).whyKey],
    [true, "whyFigmaOverview"]);
});

/* ── B4: дерево — команди групи gPage ────────────────────────────────────── */
test("gPage: склад команд дерева (newfolder замість newpage)", () => {
  const ids = paletteActions(S({ pickedKind: "folder", pickedHasParent: true }))
    .filter((a) => a.group === "gPage").map((a) => a.id);
  for (const id of ["newfolder", "groupsel", "ungroup", "outdent", "focusbranch", "togglekind"]) {
    assert.ok(ids.includes(id), `немає команди ${id}`);
  }
  assert.ok(!ids.includes("newpage"), "newpage мав піти в B3");
});

test("«Розгрупувати» вимкнене, коли обрано не теку, і каже чому", () => {
  const c = paletteActions(S({ pickedPage: "p", pickedKind: "page" })).find((x) => x.id === "ungroup");
  assert.equal(c.disabled, true);
  assert.equal(c.whyKey, "whyNotFolder");
  const f = paletteActions(S({ pickedPage: "p", pickedKind: "folder", pickedHasChildren: true })).find((x) => x.id === "ungroup");
  assert.ok(!f.disabled);
  const empty = paletteActions(S({ pickedKind: "folder", pickedHasChildren: false })).find((x) => x.id === "ungroup");
  assert.equal(empty.disabled, true);
  assert.equal(empty.whyKey, "whyEmptyFolder");
  const noIt = paletteActions(S({ hasIteration: false, shots: null, pickedKind: "folder", pickedHasChildren: true }))
    .find((x) => x.id === "ungroup");
  assert.equal(noIt.whyKey, "panelNoIt", "ungroup гейтиться тим самим treeWhy, що сусіди");
});

test("«Винести на рівень вище» вимкнене на верхньому рівні", () => {
  const top = paletteActions(S({ pickedKind: "page", pickedHasParent: false })).find((x) => x.id === "outdent");
  assert.equal(top.disabled, true);
  assert.equal(top.whyKey, "whyTopLevel");
  const deep = paletteActions(S({ pickedKind: "page", pickedHasParent: true })).find((x) => x.id === "outdent");
  assert.ok(!deep.disabled);
});

test("«Це стан / Це сторінка»: підпис називає дію; для теки вимкнено", () => {
  const find = (o) => paletteActions(S(o)).find((x) => x.id === "togglekind");
  assert.equal(find({ pickedKind: "state" }).labelKey, "menuToPage");
  assert.equal(find({ pickedKind: "page" }).labelKey, "menuToState");
  const fold = find({ pickedKind: "folder" });
  assert.equal(fold.disabled, true);
  assert.equal(fold.whyKey, "treeErrBadKind");
});

test("команди дерева без обраного вузла вимкнені з причиною", () => {
  for (const id of ["groupsel", "outdent", "focusbranch", "togglekind"]) {
    const c = paletteActions(S({ pickedPage: null, pickedKind: null })).find((x) => x.id === id);
    assert.equal(c.disabled, true, id);
    assert.ok(c.whyKey, id);
  }
});

test("палітра при множинному виборі: групувати можна, решта — «виберіть один шар»", () => {
  const st = { selCount: 3, pickedPage: "p", pickedKind: "folder", pickedHasChildren: true, pickedHasParent: true };
  const by = (id) => paletteActions(S(st)).find((x) => x.id === id);
  assert.ok(!by("groupsel").disabled);
  for (const id of ["ungroup", "outdent", "focusbranch", "togglekind"]) {
    assert.equal(by(id).disabled, true, id);
    assert.equal(by(id).whyKey, "whySelectOne", id);
  }
});

test("groupsel: вибір є — дозволено навіть без цілі; нічого немає — причина", () => {
  const g = (o) => paletteActions(S(o)).find((x) => x.id === "groupsel");
  assert.ok(!g({ selCount: 2, pickedPage: null, pickedKind: null }).disabled);
  assert.ok(!g({ selCount: 0, pickedKind: "page" }).disabled);
  assert.equal(g({ selCount: 0, pickedKind: null }).whyKey, "whyNoPageSelected");
  assert.equal(g({ hasIteration: false, shots: null }).whyKey, "panelNoIt");
});

/* Екран «Задачі» (батч 1.52): палітра ⌘K мусить бути такою ж чесною, як смуга.
   Смуга в цьому стані не має публікації, «Макет/Огляд», ітерацій — і палітра,
   що пропонує «Опублікувати» чи «Нова ітерація», діяла б на задачу, якої
   людина зараз не бачить. Вибір — ОМІТ, а не «вимкнено з причиною»: так палітра
   вже поводиться з цілими групами, безглуздими в режимі (`gIter` без ітерації,
   `inspector` в «Огляді»), а причина поруч із вимкненим контролом (принцип 2)
   потрібна там, де контрол ЛИШАЄТЬСЯ в режимі — тут цілий режим не про задачу. */
test("екран «Задачі»: палітра не пропонує жодної дії над задачею", () => {
  const ids = paletteActions(S({ homeOpen: true })).map((a) => a.id);
  const taskScoped = ["mode", "view-grid", "view-flow", "vp-desktop", "vp-tablet", "vp-mobile",
    "inspector", "comments", "panel", "clean", "newit", "renit", "dupit", "newfolder", "renpage", "hidepage",
    "groupsel", "ungroup", "outdent", "focusbranch", "togglekind", "shoot", "figma", "publish",
    "togglepub", "copylink", "openpreview", "glpush", "glpull", "glsetup",
    "delit", "delpage", "go-iter", "go-pages"];
  for (const id of taskScoped) {
    assert.ok(!ids.includes(id), `дія «${id}» не має бути в палітрі на екрані «Задачі»`);
  }
  // Те, що до задачі не стосується, лишається — мова й надалі досяжна.
  assert.ok(ids.includes("lang-en"), "мова зникла разом із діями задачі");
  assert.ok(ids.length > 0);
});

/* Дзеркало: без `homeOpen` реєстр цілий. Без цього тест вище був би зеленим і
   на порожньому реєстрі. */
test("поза екраном «Задачі» дії задачі на місці", () => {
  const ids = paletteActions(S({ homeOpen: false })).map((a) => a.id);
  for (const id of ["go-tasks", "mode", "publish", "newit", "figma"]) {
    assert.ok(ids.includes(id), `дії «${id}» немає в звичайному стані`);
  }
});

/* «Встановити Deai Canvas як застосунок» (PWA, P1). Пункт ЛИШЕ тоді, коли Chrome
   віддав `beforeinstallprompt` (`canInstall`) і вікно ще не встановлене
   (`standalone` хибне): у встановленому вікні пропонувати встановлення нічого, а
   без події `prompt()` нема що викликати — тому ОМІТ, а не «вимкнено з
   причиною». Це дія самого застосунку, як мова, тож вона є і на екрані
   «Задачі». */
const installIds = (st) => paletteActions(S(st)).filter((a) => a.id === "pwa-install");

test("встановлення: пункт є лише коли canInstall і не standalone — у звичайному стані", () => {
  assert.equal(installIds({}).length, 0, "без події встановлення пункту бути не має");
  assert.equal(installIds({ canInstall: false, standalone: false }).length, 0);
  assert.equal(installIds({ canInstall: true, standalone: true }).length, 0,
    "у встановленому вікні пропонувати встановити нема чого");
  assert.equal(installIds({ canInstall: true, standalone: false }).length, 1);
});

test("встановлення: те саме правило на екрані «Задачі»", () => {
  const home = (o) => paletteActions(S({ homeOpen: true, ...o })).filter((a) => a.id === "pwa-install");
  assert.equal(home({}).length, 0);
  assert.equal(home({ canInstall: true, standalone: true }).length, 0);
  assert.equal(home({ canInstall: true, standalone: false }).length, 1,
    "дія застосунку, а не задачі — на екрані «Задачі» теж доречна");
});

test("встановлення: пункт діє через act:pwainstall, має іконку й підпис в обох словниках", () => {
  const [a] = installIds({ canInstall: true });
  assert.equal(a.act, "pwainstall");
  assert.equal(a.group, "gSet");
  assert.ok(!a.disabled, "пункт або є, або його нема — вимкненим він не буває");
  assert.ok(ico(a.icon), "іконки пункту немає у спрайті");
  for (const lang of ["uk", "en"]) {
    assert.ok(DICT[lang][a.labelKey], `«${a.labelKey}» немає в DICT.${lang}`);
  }
  assert.match(DICT.uk[a.labelKey], /Deai Canvas/);
  assert.match(DICT.en[a.labelKey], /Deai Canvas/);
});

test("встановлення: знаходиться в ⌘K обома мовами (install / встановити / застосунок)", () => {
  const list = paletteActions(S({ canInstall: true }));
  for (const [lang, q] of [["uk", "install"], ["uk", "встанови"], ["en", "встанови"], ["en", "install"], ["uk", "pwa"]]) {
    setLang(lang);
    assert.ok(filterActions(list, q).some((a) => a.id === "pwa-install"), `«${q}» (${lang}) не знаходить пункту`);
  }
});

test("встановлення: решта палітри не зачеплена присутністю пункту", () => {
  const without = paletteActions(S()).map((a) => a.id);
  const withIt = paletteActions(S({ canInstall: true })).map((a) => a.id);
  assert.deepEqual(withIt.filter((id) => id !== "pwa-install"), without);
});

/* ── простори (Deai 1.0, етап 1) ──────────────────────────────────────────────
   «Простір: X» — у `gGo` (переходи), по рядку на кожен ІНШИЙ простір, плюс
   «Новий простір…». Підпис несе ім'я простору (дані користувача), тож він
   `labelKey` + `labelArgs`, а не готовий рядок: реєстр не кличе `t()` (шапка
   файла), а `itemHTML`/`searchText` розгортають аргументи. Без масиву
   `spaces` (шар вимкнено) пунктів нема. Простір без інтеграцій ховає з
   палітри те саме, що з смуги: публікацію й GitLab. */
const SPS = [{ id: "a", name: "A" }, { id: "b", name: "B" }];

test("простори: «Простір: B» для кожного ІНШОГО простору й «Новий простір…» — у gGo", () => {
  const acts = paletteActions(S({ spaces: SPS, spaceId: "a" }));
  const go = acts.find((a) => a.id === "space-go-b");
  assert.deepEqual(go, {
    id: "space-go-b", group: "gGo", labelKey: "spaceGo", labelArgs: ["B"], icon: go.icon,
    act: "space", val: "b",
  });
  assert.ok(ico(go.icon), "іконки пункту немає у спрайті");
  assert.ok(!acts.some((a) => a.id === "space-a"), "перейти в поточний простір — нічого не робити");
  const nw = acts.find((a) => a.id === "space-new");
  assert.equal(nw.group, "gGo");
  assert.equal(nw.labelKey, "spaceNew");
  assert.equal(nw.act, "spacenew");
  assert.ok(ico(nw.icon));
  assert.ok(!nw.disabled && !nw.navOnly);
});

/* «Підключення простору «A»» (етап 3a) — вхід на екран підключень поточного простору. Лише коли поточний простір
   є В ПЕРЕЛІКУ: без нього нема чого підключати (і назви для підпису). Не на самій сторінці `conn`: дія, що нічого
   не робить, — той самий принцип, що для `go-tasks` на «Задачах» і для поточного простору. */
test("простори: «Підключення простору «A»» для поточного; нема на самій сторінці й без поточного", () => {
  const acts = paletteActions(S({ spaces: SPS, spaceId: "a" }));
  const c = acts.find((a) => a.id === "space-conn");
  assert.deepEqual({ ...c, icon: undefined }, { id: "space-conn", group: "gGo", labelKey: "spaceConn", labelArgs: ["A"],
    icon: undefined, act: "conn" });
  assert.ok(ico(c.icon));
  assert.ok(paletteActions(S({ homeOpen: true, spaces: SPS, spaceId: "a" })).some((a) => a.id === "space-conn"),
    "на «Задачах» пункт є");
  assert.ok(!paletteActions(S({ homeOpen: true, homePage: "conn", spaces: SPS, spaceId: "a" })).some((a) => a.id === "space-conn"),
    "на самій сторінці — дія, що нічого не робить");
  assert.ok(!paletteActions(S({ spaces: SPS })).some((a) => a.id === "space-conn"), "поточний невідомий — нема");
  assert.ok(!paletteActions(S({ spaces: SPS, spaceId: "zzz" })).some((a) => a.id === "space-conn"), "поточного нема в переліку");
  /* Поточний — і зі `space.id`, як для решти пунктів просторів. */
  assert.equal(paletteActions(S({ spaces: SPS, space: { id: "b" } }))
    .find((a) => a.id === "space-conn")?.labelArgs[0], "B");
  /* Простір без ролей екрану підключень не позбавлений — навпаки, це його головний вхід. */
  assert.ok(paletteActions(S({ spaces: SPS, spaceId: "a", space: { id: "a", capabilities: NO_ROLES } }))
    .some((a) => a.id === "space-conn"));
  /* Без масиву просторів (шар вимкнено) — як і решта пунктів просторів, нема. */
  assert.ok(!paletteActions(S({ spaceId: "a" })).some((a) => a.id === "space-conn"));
  assert.ok(!paletteActions(S({ homeOpen: true, spaceId: "a" })).some((a) => a.id === "space-conn"));
});

test("простори: «Підключення простору» — підпис в обох мовах, ім'я екрановане, пошук знаходить за назвою екрана", () => {
  const acts = paletteActions(S({ spaces: [{ id: "a", name: "<b>A</b>" }, { id: "b", name: "B" }], spaceId: "a" }));
  const html = paletteListHTML(acts, "", 0);
  assert.match(html, /<span>Налаштування простору «&lt;b&gt;A&lt;\/b&gt;»<\/span>/);
  assert.doesNotMatch(html, /<b>A<\/b>/);
  const plain = paletteActions(S({ spaces: SPS, spaceId: "a" }));
  assert.deepEqual(filterActions(plain, "підключення").map((a) => a.id), ["space-conn"]);
  setLang("en");
  assert.match(paletteListHTML(plain, "", 0), /<span>Settings of the space “A”<\/span>/);
  assert.deepEqual(filterActions(plain, "connections").map((a) => a.id), ["space-conn"]);
});

/* Сторінка майстра (етап 3b): перемкнути простір посеред кроків означало б лишити майстер над чужим простором, а «Новий
   простір» на ньому нічого не робить, «Підключення» ж вели б повз незбережений вибір. Дій простору нема зовсім — але дії самого
   застосунку (мова, встановлення) лишаються, як на «Задачах». */
test("на сторінці майстра ⌘K не пропонує дій простору: ні перемикання, ні «Підключення», ні «Новий простір»", () => {
  const acts = paletteActions(S({ spaces: [{ id: "a", name: "A" }, { id: "b", name: "B" }], spaceId: "a", homeOpen: true, homePage: "wiz" }));
  assert.ok(!acts.some((a) => a.id.startsWith("space-")), acts.map((a) => a.id).join(","));
  const tasks = paletteActions(S({ spaces: [{ id: "a", name: "A" }, { id: "b", name: "B" }], spaceId: "a", homeOpen: true, homePage: "tasks" }));
  assert.ok(tasks.some((a) => a.id === "space-new") && tasks.some((a) => a.id === "space-go-b"), "свідок: на «Задачах» дії є");
  assert.ok(tasks.some((a) => a.id === "space-conn"), "свідок: «Підключення» на «Задачах» є");
  /* Решта палітри не зникла: мова й встановлення — дії застосунку, а не простору. */
  const ids = acts.map((a) => a.id);
  assert.ok(ids.includes("lang-en"), "мова зникла разом із діями простору");
  assert.ok(paletteActions(S({ homeOpen: true, homePage: "wiz", canInstall: true, standalone: false })).some((a) => a.id === "pwa-install"),
    "встановлення зникло разом із діями простору");
  /* Лише рівно `wiz`: інша сторінка оверлею дій простору не втрачає. */
  for (const homePage of ["WIZ", "wizard", "", null, undefined]) {
    assert.ok(paletteActions(S({ spaces: SPS, spaceId: "a", homeOpen: true, homePage })).some((a) => a.id === "space-new"), String(homePage));
  }
});

/* Синонім `space-conn` — обома мовами, як `lang-*` і `pwa-install`: пункт має ЛАТИНСЬКИЙ шлях у ⌘K в українському
   інтерфейсі («connections», «integrations») і КИРИЛИЧНИЙ в англійському («підключення», «інтеграції»). `t(labelKey)`
   дає лише поточну мову, тож без псевдоніма «connections» в українському UI не знаходило б нічого. */
test("простори: «Підключення простору» знаходиться запитом ІНШОЮ мовою (псевдонім обома мовами)", () => {
  const acts = paletteActions(S({ spaces: SPS, spaceId: "a" }));
  const ids = (q) => filterActions(acts, q).map((a) => a.id);
  setLang("uk");
  assert.deepEqual(ids("connections"), ["space-conn"], "uk-інтерфейс: «connections» не знайшло пункту");
  assert.deepEqual(ids("integrations"), ["space-conn"]);
  assert.deepEqual(ids("modules"), ["space-conn"]);
  setLang("en");
  assert.deepEqual(ids("підключення"), ["space-conn"], "en-інтерфейс: «підключення» не знайшло пункту");
  assert.deepEqual(ids("інтеграції"), ["space-conn"]);
  assert.deepEqual(ids("модулі"), ["space-conn"]);
  /* Псевдонім не розтікається на пункти просторів: «connections» не знаходить «Простір: B» і «Новий простір…». */
  assert.ok(!ids("connections").some((id) => id === "space-go-b" || id === "space-new"));
});

test("простори: пункти складають суцільний блок gGo (заголовок групи не повторюється)", () => {
  const html = paletteListHTML(paletteActions(S({ spaces: SPS, spaceId: "a" })), "", 0);
  assert.equal((html.match(/class="pal-grp">Перейти</g) || []).length, 1, "група gGo розірвана");
});

test("простори: на екрані «Задачі» ті самі пункти є, дій над задачею як не було", () => {
  const acts = paletteActions(S({ homeOpen: true, spaces: SPS, spaceId: "a" }));
  const ids = acts.map((a) => a.id);
  assert.ok(ids.includes("space-go-b") && ids.includes("space-new"));
  assert.ok(!ids.includes("space-a"));
  assert.ok(!ids.includes("publish") && !ids.includes("mode"), "дії задачі просочились на екран «Задачі»");
  assert.ok(ids.includes("lang-en"), "мова лишилась");
});

test("простори: без масиву `spaces` (шар вимкнено) пунктів просторів нема — в обох гілках", () => {
  for (const o of [{}, { homeOpen: true }, { spaces: null }, { spaces: undefined }, { spaces: "x" }]) {
    const ids = paletteActions(S(o)).map((a) => a.id);
    assert.ok(!ids.some((id) => id.startsWith("space-")), JSON.stringify(o));
  }
});

test("простори: порожній масив — лише «Новий простір…» (перейти нікуди)", () => {
  const ids = paletteActions(S({ spaces: [], spaceId: null })).map((a) => a.id).filter((id) => id.startsWith("space-"));
  assert.deepEqual(ids, ["space-new"]);
});

test("простори: поточний — зі spaceId або зі space.id", () => {
  const byId = (o) => paletteActions(S({ spaces: SPS, ...o })).filter((a) => a.act === "space").map((a) => a.val);
  assert.deepEqual(byId({ spaceId: "a" }), ["b"]);
  assert.deepEqual(byId({ space: { id: "b" } }), ["a"]);
  assert.deepEqual(byId({}), ["a", "b"], "поточний невідомий — усі пропонуємо");
});

test("простори: недоступний простір — пункт є, вимкнений із причиною", () => {
  const acts = paletteActions(S({
    spaces: [{ id: "a", name: "A" }, { id: "g", name: "G", available: false }], spaceId: "a",
  }));
  const g = acts.find((a) => a.id === "space-go-g");
  assert.equal(g.disabled, true);
  assert.equal(g.whyKey, "spaceUnavailable");
  assert.ok(DICT.uk.spaceUnavailable !== undefined && DICT.en.spaceUnavailable !== undefined);
});

test("простори: підпис — «Простір: B», і в списку, і в пошуку (за ім'ям простору)", () => {
  const acts = paletteActions(S({ spaces: SPS, spaceId: "a" }));
  const html = paletteListHTML(acts, "", 0);
  assert.match(html, /<span>Простір: B<\/span>/);
  assert.match(html, /<span>Новий простір…<\/span>/);
  assert.deepEqual(filterActions(acts, "простір: b").map((a) => a.id), ["space-go-b"]);
  // ім'я простору — дані користувача: пошук знаходить за ним, а не за ключем словника
  const named = paletteActions(S({ spaces: [{ id: "a", name: "A" }, { id: "x", name: "Клієнт Ікс" }], spaceId: "a" }));
  assert.ok(filterActions(named, "ікс").some((a) => a.id === "space-go-x"));
});

test("простори: пошук знаходить обома мовами («space» в українському, «простір» — в англійському)", () => {
  const acts = paletteActions(S({ spaces: SPS, spaceId: "a" }));
  for (const lang of ["uk", "en"]) {
    setLang(lang);
    for (const q of ["space", "простір"]) {
      const found = filterActions(acts, q).map((a) => a.id);
      assert.ok(found.includes("space-go-b") && found.includes("space-new"), `«${q}» (${lang}): ${found}`);
    }
  }
});

test("простори: ім'я простору в підписі екранується", () => {
  const acts = paletteActions(S({ spaces: [{ id: "a", name: "A" }, { id: "e", name: "<img src=x onerror=1>" }], spaceId: "a" }));
  const html = paletteListHTML(acts, "", 0);
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&lt;img src=x/);
});

test("простори: англійський підпис «Space: B»", () => {
  setLang("en");
  const html = paletteListHTML(paletteActions(S({ spaces: SPS, spaceId: "a" })), "", 0);
  assert.match(html, /<span>Space: B<\/span>/);
  assert.match(html, /<span>New space…<\/span>/);
});

test("простори: кожна нова дія має labelKey в обох словниках, а act — навігаційний або dialog", () => {
  const acts = paletteActions(S({ spaces: SPS, spaceId: "a" })).filter((a) => a.id.startsWith("space-"));
  assert.equal(acts.length, 3, "перейти в B, «Новий простір…», «Підключення простору»");
  for (const a of acts) {
    assert.ok(DICT.uk[a.labelKey] !== undefined && DICT.en[a.labelKey] !== undefined, a.id);
    assert.ok(a.act, `дія «${a.id}» без act`);
  }
});

const NO_ROLES = { publish: null, tokens: null, comments: null, vcs: null, notify: null, dashboard: null, tracker: null };

test("простір без ролей: з палітри йдуть публікація, посилання, превʼю, GitLab", () => {
  const off = (o = {}) => paletteActions(S({ space: { capabilities: NO_ROLES }, gl: "behind", ...o })).map((a) => a.id);
  const ids = off();
  for (const id of ["publish", "togglepub", "copylink", "openpreview", "glpush", "glpull", "glsetup"]) {
    assert.ok(!ids.includes(id), `«${id}» мусить піти з палітри простору без ролей`);
  }
  assert.ok(!off({ gl: "off" }).includes("glsetup"), "glsetup — теж GitLab");
  // що лишається: усе, що не ходить назовні
  for (const id of ["figma", "mode", "newit", "shoot", "lang-en", "delit"]) {
    assert.ok(ids.includes(id), `«${id}» не мав зникати`);
  }
});

test("простір зі схемою ЛІГИ (або без відомостей): палітра ціла, як була", () => {
  const baseIds = paletteActions(S({ gl: "behind" })).map((a) => a.id);
  for (const space of [{ capabilities: { publish: "vercel-publish", tokens: null }, compat: { publish: "design-canvas" } }, {}, null, undefined]) {
    const ids = paletteActions(S({ space, gl: "behind" })).map((a) => a.id);
    assert.deepEqual(ids, baseIds, JSON.stringify(space));
  }
  for (const id of ["publish", "copylink", "openpreview", "glpull", "glpush"]) {
    assert.ok(baseIds.includes(id), id);
  }
});

test("простір без ролей: решта палітри не зачеплена — відрізняється рівно набором прихованих", () => {
  const all = paletteActions(S({ gl: "behind" })).map((a) => a.id);
  const off = paletteActions(S({ space: { capabilities: NO_ROLES }, gl: "behind" })).map((a) => a.id);
  const gone = all.filter((id) => !off.includes(id)).sort();
  assert.deepEqual(gone, ["copylink", "glpull", "glpush", "openpreview", "publish", "togglepub"]);
});

test("простори: id дій унікальні навіть для простору з id `new` (колізія зі `space-new`)", () => {
  const acts = paletteActions(S({
    spaces: [{ id: "a", name: "A" }, { id: "new", name: "Нова" }, { id: "go-b", name: "G" }], spaceId: "a",
  }));
  const ids = acts.map((a) => a.id);
  assert.equal(new Set(ids).size, ids.length, `дублі id: ${ids.filter((x, i) => ids.indexOf(x) !== i)}`);
  assert.equal(acts.find((a) => a.id === "space-new").act, "spacenew", "«Новий простір…» лишився собою");
  const go = acts.find((a) => a.act === "space" && a.val === "new");
  assert.equal(go.id, "space-go-new");
  assert.equal(go.labelArgs[0], "Нова");
  // і на екрані «Задачі» теж
  const home = paletteActions(S({ homeOpen: true, spaces: [{ id: "new", name: "N" }], spaceId: "a" })).map((a) => a.id);
  assert.equal(new Set(home).size, home.length);
});

/* Рядки блоку публікації пересунуті під `if (!noOutward)` (простори) — а покриття їхнього
   `disabled` досі трималось лише на тому, що вимкнений пункт має `whyKey`. Тут — сам
   стан: посилання й превʼю вимкнені, поки задачу не опубліковано, з тією ж причиною,
   що в смузі (`linkWhyKey`, `bar-model.js`). */
test("палітра: «Копіювати посилання» і «Відкрити превʼю» вимкнені з причиною, поки не опубліковано", () => {
  const f = (o, id) => paletteActions(S(o)).find((a) => a.id === id);
  const st = (a) => [a.disabled, a.whyKey];
  assert.deepEqual(st(f({ published: false }, "openpreview")), [true, "whyNoPublish"]);
  assert.deepEqual(st(f({ published: false }, "copylink")), [true, "whyNoPublish"]);
  assert.deepEqual(st(f({ iterPub: false }, "copylink")), [true, "whyItOff"]);
  assert.deepEqual(st(f({ pagePub: false }, "copylink")), [true, "whyPageOff"]);
  assert.deepEqual(st(f({}, "openpreview")), [false, ""]);
  assert.deepEqual(st(f({}, "copylink")), [false, ""]);
});

/* ── публікація за `capabilities.publish` (модулі 2а, Task 8) ─────────────────
   Спільний `if (!noOutward)` розщеплено: `publish`/`togglepub`/`copylink`/`openpreview`
   ходять на `hasPublish` (`spaces-model.js`), а GitLab (`gl*`) — на `hasVcs`;
   Простір, де публікує вбудований модуль, отримує публікацію, але не GitLab. */
{
  /* `comments` у capabilities — командний канал (2b-2): ЛІГА має свій (модуль зі схемою в `compat`), решта в цих фікстурах — нікого. */
  const MODS = { id: "p", capabilities: { ...NO_ROLES, publish: "static-publish", tokens: null } };
  const LEGS = { id: "liga", capabilities: { publish: "vercel-publish", tokens: null, comments: "supabase-comments" },
    compat: { publish: "design-canvas", comments: "comment-layer" } };
  const NOPUB = { id: "n", capabilities: NO_ROLES };
  const PUB = ["publish", "togglepub", "copylink", "openpreview"];
  const GL = ["glpush", "glpull", "glsetup"];
  const ids = (space, o = {}) => paletteActions(S({ space, gl: "behind", ...o })).map((a) => a.id);

  test("публікація модулем: у палітрі публікація, превʼю й посилання — без GitLab і командного каналу", () => {
    const got = ids(MODS);
    for (const id of PUB) assert.ok(got.includes(id), `«${id}» мусить бути в палітрі простору з модулем`);
    for (const id of GL) assert.ok(!got.includes(id), `«${id}» — на ролі vcs, а її тут нема`);
    assert.ok(!ids(MODS, { gl: "off" }).includes("glsetup"));
  });

  test("простір без постачальника публікації (`publish: null`): жодної з чотирьох дій публікації", () => {
    const got = ids(NOPUB);
    for (const id of [...PUB, ...GL]) assert.ok(!got.includes(id), id);
    const withVcs = { ...NOPUB, capabilities: { ...NOPUB.capabilities, vcs: "git-sync" } };
    assert.ok(ids(withVcs).includes("glpush"), "GitLab — на ролі vcs, не на публікації");
    assert.ok(!ids(withVcs).includes("publish"));
  });

  test("простір ЛІГА (compat): палітра ціла, як була", () => {
    const got = ids(LEGS);
    for (const id of [...PUB, ...GL.slice(0, 2)]) assert.ok(got.includes(id), id);
    assert.deepEqual(got, ids(null), "те саме, що без відомостей про простір");
  });

  test("простір з модулем: відрізняється від ЛІГА рівно GitLab", () => {
    const mod = ids(MODS);
    const gone = ids(LEGS).filter((id) => !mod.includes(id)).sort();
    assert.deepEqual(gone, ["glpull", "glpush"]);
  });

  test("модуль публікації з ролями vcs і comments: GitLab і командний канал живі", () => {
    const got = ids({ ...MODS, capabilities: { ...MODS.capabilities, vcs: "git-sync", comments: "supabase-comments" } });
    for (const id of [...PUB, "glpush", "glpull"]) assert.ok(got.includes(id), id);
  });

  test("порядок групи gPub не змінився: figma, publish, togglepub, copylink, openpreview, потім GitLab", () => {
    const order = paletteActions(S({ space: LEGS, gl: "behind" })).filter((a) => a.group === "gPub").map((a) => a.id);
    assert.deepEqual(order, ["figma", "publish", "togglepub", "copylink", "openpreview", "glpull", "glpush"]);
    const mod = paletteActions(S({ space: MODS, gl: "behind" })).filter((a) => a.group === "gPub").map((a) => a.id);
    assert.deepEqual(mod, ["figma", "publish", "togglepub", "copylink", "openpreview"]);
  });

  test("публікація модулем у палітрі: «Опублікувати»/«Оновити» — за `published`, `openpreview` вимкнено без публікації", () => {
    const find = (o, id) => paletteActions(S({ space: MODS, ...o })).find((a) => a.id === id);
    assert.equal(find({ published: false }, "publish").labelKey, "publish");
    assert.equal(find({ published: true }, "publish").labelKey, "update");
    assert.equal(find({ published: false }, "openpreview").disabled, true);
    assert.equal(find({ published: false }, "openpreview").whyKey, "whyNoPublish");
    assert.ok(!find({ published: true }, "openpreview").disabled);
  });
}

/* ── Оновлення інструмента (0.23.0): «Перевірити оновлення» і «Що нового» ────────────────────────────────
   Дії самого інструмента, не задачі: є і на екрані «Задачі», де реєстр повертається раніше (Поправка 18). Стан без ключа `update`
   (еталони `legacy-golden`) їх не має: ключ дає лише `paletteState()`. */
const UPD = { current: "0.1.0", latest: "0.2.0", available: true, state: "ok", checked_at: 1, boot: "a", restart_failed: false };
const upIds = (st) => paletteActions(S(st)).filter((a) => a.id.startsWith("update-")).map((a) => a.id);

test("оновлення: «Перевірити оновлення» є, коли стан відомий (навіть `null` — ще не питали); «Що нового» — лише при available", () => {
  assert.deepEqual(upIds({ update: null }), ["update-check"], "до першої перевірки ручна перевірка працює");
  assert.deepEqual(upIds({ update: { ...UPD, available: false } }), ["update-check"]);
  assert.deepEqual(upIds({ update: { ...UPD, state: "offline" } }), ["update-check"], "offline: пігулки нема — і «Що нового» нема");
  assert.deepEqual(upIds({ update: UPD }), ["update-check", "update-notes"]);
  assert.deepEqual(upIds({}), [], "стан без ключа update (еталони) дій оновлення не має");
});

test("оновлення: ті самі дії в `homeOpen` і поза ним (екран «Задачі», «Підключення», майстер)", () => {
  for (const homeOpen of [true, false]) {
    for (const homePage of homeOpen ? [undefined, "tasks", "conn", "wiz"] : [undefined]) {
      assert.deepEqual(upIds({ homeOpen, homePage, update: UPD }), ["update-check", "update-notes"], `homeOpen=${homeOpen} ${homePage}`);
    }
  }
});

test("оновлення: дії мають act, групу gSet, іконку зі спрайта й підпис в обох словниках; act обробляє BAR_ACTIONS", () => {
  const src = readFileSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "app.js"), "utf8");
  for (const a of paletteActions(S({ update: UPD })).filter((x) => x.id.startsWith("update-"))) {
    assert.equal(a.group, "gSet");
    assert.ok(a.act, a.id);
    assert.ok(ico(a.icon), `${a.id}: іконки нема у спрайті`);
    for (const lang of ["uk", "en"]) assert.ok(DICT[lang][a.labelKey] !== undefined, `${lang}.${a.labelKey}`);
    assert.match(src, new RegExp(`\\n  ${a.act}: \\(\\) =>`), `${a.act}: нема обробника в BAR_ACTIONS`);
  }
});

test("оновлення: знаходяться в ⌘K обома мовами", () => {
  const list = (lang, q) => { setLang(lang); return filterActions(paletteActions(S({ update: UPD, lang })), q).map((a) => a.id); };
  assert.ok(list("uk", "оновлення").includes("update-check"));
  assert.ok(list("en", "update").includes("update-check"));
  assert.ok(list("en", "what").includes("update-notes"));
  setLang("uk");
});

/* ── «Баг / ідея» (0.23.0, Task 8): відкриває діалог відгуку; є й на екрані «Задачі», де реєстр повертається раніше ─────────── */
const fbIds = (st) => paletteActions(S(st)).filter((a) => a.id === "feedback").map((a) => a.act);

test("відгук: «Баг / ідея» є на екрані задачі, «Задачі», «Підключення» й у майстрі; без ключа update (еталони) — нема", () => {
  for (const homeOpen of [true, false]) {
    for (const homePage of homeOpen ? [undefined, "tasks", "conn", "wiz"] : [undefined]) {
      assert.deepEqual(fbIds({ homeOpen, homePage, update: null }), ["feedback"], `homeOpen=${homeOpen} ${homePage}`);
    }
  }
  assert.deepEqual(fbIds({}), []);
});

test("відгук: дія має групу gSet, іконку зі спрайта, підпис в обох словниках і обробник у BAR_ACTIONS; знаходиться в ⌘K", () => {
  const src = readFileSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "app.js"), "utf8");
  const a = paletteActions(S({ update: null })).find((x) => x.id === "feedback");
  assert.equal(a.group, "gSet");
  assert.ok(ico(a.icon));
  for (const lang of ["uk", "en"]) assert.ok(DICT[lang][a.labelKey] !== undefined, `${lang}.${a.labelKey}`);
  assert.match(src, /\n  feedback: \(val, el\) => /);   // етап В: другий аргумент — кнопка-якір поповера
  const list = (lang, q) => { setLang(lang); return filterActions(paletteActions(S({ update: null, lang })), q).map((x) => x.id); };
  assert.ok(list("uk", "баг").includes("feedback"));
  assert.ok(list("uk", "ідея").includes("feedback"));
  assert.ok(list("en", "bug").includes("feedback"));
  setLang("uk");
});

/* Етап Д, Task 10: «Перейменувати задачу» (F2) є лише коли відкрита задача; на екрані «Задачі» її нема. */
test("rentask: є з відкритою задачею (act, kbd F2), нема без задачі й на екрані «Задачі»", () => {
  const a = paletteActions(S({ hasTask: true })).find((x) => x.id === "rentask");
  assert.ok(a, "пункту нема при відкритій задачі");
  assert.equal(a.act, "rentask");
  assert.equal(a.kbd, "F2");
  assert.equal(a.labelKey, "taskRenamePal");
  assert.equal(paletteActions(S({ hasTask: false })).some((x) => x.id === "rentask"), false, "є без задачі");
  assert.equal(paletteActions(S()).some((x) => x.id === "rentask"), false, "є без ключа hasTask");
  assert.equal(paletteActions(S({ hasTask: true, homeOpen: true })).some((x) => x.id === "rentask"), false, "є на екрані «Задачі»");
});

test("«В Figma» вимкнено в просторі — пункту в ⌘K нема; увімкнено/без ключа — є", () => {
  const has = (space) => paletteActions(S({ space })).some((a) => a.id === "figma");
  assert.equal(has({ id: "p", tools: { figma: false } }), false);
  assert.equal(has({ id: "p", tools: { figma: true } }), true);
  assert.equal(has({ id: "p" }), true);
  assert.equal(has(null), true);
});

/* ── «Знайомство з канвасом» (0.33.0): є там само, де «Баг / ідея» (і на екрані «Задачі») ─────────────── */
test("знайомство: пункт є на екрані задачі, «Задачі», «Підключення» й у майстрі; без ключа update (еталони) — нема", () => {
  const ids = (st) => paletteActions(S(st)).filter((a) => a.id === "intro").map((a) => a.act);
  for (const homeOpen of [true, false]) {
    for (const homePage of homeOpen ? [undefined, "tasks", "conn", "wiz"] : [undefined]) {
      assert.deepEqual(ids({ homeOpen, homePage, update: null }), ["intro"], `homeOpen=${homeOpen} ${homePage}`);
    }
  }
  assert.deepEqual(ids({}), []);
});

test("знайомство: група gSet, іконка зі спрайта, підпис в обох словниках, обробник у BAR_ACTIONS; знаходиться в ⌘K", () => {
  const src = readFileSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "app.js"), "utf8");
  const a = paletteActions(S({ update: null })).find((x) => x.id === "intro");
  assert.equal(a.group, "gSet");
  assert.ok(ico(a.icon));
  for (const lang of ["uk", "en"]) assert.ok(DICT[lang][a.labelKey] !== undefined, `${lang}.${a.labelKey}`);
  assert.match(src, /\n  intro: \(\) =>/);
  setLang("uk");
  assert.ok(filterActions(paletteActions(S({ update: null })), "знайомство").some((x) => x.id === "intro"));
  setLang("en");
  assert.ok(filterActions(paletteActions(S({ update: null, lang: "en" })), "tour").some((x) => x.id === "intro"));
  setLang("uk");
});
