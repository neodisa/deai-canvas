import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");

/* Усі правила файла як {sels, body}. `sels` — окремі селектори списку через кому, пробіли зведені: `a>b`, `a > b` і
   `a  >  b` — той самий ключ. Вкладений `@media` не заважає: його заголовок із `{` не збігається з «селектор{тіло}»
   (тіло не має вкладених дужок), і розбір підхоплює правило всередині. */
const norm = (s) => s.trim().replace(/\s*([>+~])\s*/g, " $1 ").replace(/\s+/g, " ");
const RULES = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ sels: m[1].split(",").map(norm), body: m[2] }));
/** Тіло ПЕРШОГО правила, у списку селекторів якого є `selector` (рівно такий, не частина складнішого). */
const rule = (selector) => RULES.find((r) => r.sels.includes(norm(selector)))?.body ?? null;
/** Останній складений селектор ланцюжка — «суб'єкт» правила: `.a .b > .c` → `.c`. */
const subjectOf = (sel) => sel.split(/\s*[>+~]\s*|\s+/).pop();
const isSubjectOfSomeRule = (cls) => {
  const re = new RegExp(`\\.${cls}(?![\\w-])`);
  return RULES.some((r) => r.sels.some((s) => re.test(subjectOf(s))));
};

/* Значок: ключі `BADGES` беремо з коду розмітки, а не з руки — новий різновид без правила мусить падати тут.
   `unchecked` і `off` навмисно без власного правила: це нейтральний базовий `.cn-badge`. */
const BASE_ONLY_BADGES = new Set(["unchecked", "off"]);
const badgeKinds = (src) => {
  const block = /const BADGES = \{([\s\S]*?)\n\};/.exec(src)?.[1] ?? "";
  return [...block.matchAll(/(\w+):\s*\[/g)].map((m) => m[1]);
};
/* Клас, якому правило потрібне лише «в контексті предка» (`.cn-res--ok .ico`): сам по собі він нічого не фарбує —
   лише вирішує колір значка всередині. Усім іншим класам потрібне правило, де вони — суб'єкт. */
const SCOPE_ONLY = new Set(["cn-res--ok", "cn-res--err"]);

test("кожен клас розмітки «Підключення» має правило в styles.css — як суб'єкт, а не лише як предок", () => {
  const viewSrc = read("connections-view.js");
  const src = viewSrc.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  const classes = new Set();
  for (const m of src.matchAll(/class="([^"]+)"/g)) {
    for (const c of m[1].replace(/\$\{[^}]*\}/g, " ").split(/\s+/)) {
      /* Фрагмент, що закінчується на «-», — статична голова класу з інтерполяцією (`cn-badge--${kind}`): сам по
         собі він не клас. Різновиди значка беремо з `BADGES` нижче. */
      if (/^cn-/.test(c) && !c.endsWith("-")) classes.add(c);
    }
  }
  const kinds = badgeKinds(viewSrc);
  assert.ok(kinds.length >= 3, `ключі BADGES не знайдено (${kinds}) — регексп зламано`);
  for (const k of kinds) if (!BASE_ONLY_BADGES.has(k)) classes.add(`cn-badge--${k}`);
  assert.ok(classes.size >= 25, `знайдено лише ${classes.size} класів — регексп зламано: ${[...classes]}`);
  const anywhere = (c) => new RegExp(`\\.${c}(?![\\w-])`).test(css);
  const missing = [...classes].filter((c) => !anywhere(c));
  assert.deepEqual(missing, [], `класи без правила: ${missing.join(", ")}`);
  const noSubject = [...classes].filter((c) => !SCOPE_ONLY.has(c) && !isSubjectOfSomeRule(c));
  assert.deepEqual(noSubject, [], `клас є лише предком у чужих правилах, власного правила нема: ${noSubject.join(", ")}`);
});

test("кнопка «Підключення» в голові «Задач»: ряд дій має правило", () => {
  assert.match(rule(".th-head-acts") ?? "", /display:flex/);
});

test("шапка картки переноситься: назва не стискається до слів по літері, значок і «типово» йдуть на другий рядок", () => {
  /* Неявна картка («Публікація в теку» + «типово» + значок) стискала назву до ≈50px при картці 300px. */
  assert.match(rule(".cn-card-top") ?? "", /flex-wrap:wrap/);
  const n = rule(".cn-card-name") ?? "";
  assert.match(n, /flex:1 1 9em/);
  assert.match(n, /min-width:0/);
});

test("довгі рядки з даних не дають горизонтального скролу: перенос усюди, де текст не з нашого словника", () => {
  /* Назва ролі, модуля й підпис поля приходять із чужого маніфесту, шлях і текст помилки — з диска, назва простору
     (заголовок сторінки) — від людини. */
  const wrap = [".cn-in .th-h", ".cn-sec-h", ".cn-now", ".cn-lead", ".cn-lbl", ".cn-check", ".cn-err > span", ".cn-card-role",
    ".cn-card-name b", ".cn-dr-name b", ".cn-why-detail", ".cn-code"];
  const bad = wrap.filter((s) => !/overflow-wrap:anywhere/.test(rule(s) ?? ""));
  assert.deepEqual(bad, [], `без overflow-wrap:anywhere: ${bad.join(", ")}`);
  /* Текст помилки сторінки — flex-елемент поруч із кнопкою: без `min-width:0` він розпирає ряд, і «Повторити» вилазить. */
  const e = rule(".cn-err > span") ?? "";
  assert.match(e, /flex:1/);
  assert.match(e, /min-width:0/);
});

test("бічна панель: 420px, над оверлеєм і під смугою, схована атрибутом і поза оверлеєм", () => {
  const d = rule(".cn-drawer");
  assert.ok(d, "правила .cn-drawer немає");
  assert.match(d, /position:fixed/);
  assert.match(d, /top:var\(--h-top\)/);
  assert.match(d, /width:420px/);
  assert.match(d, /z-index:var\(--z-widget\)/);
  assert.match(rule(".cn-drawer[hidden]") ?? "", /display:none/);
  assert.match(rule("body:not(.home-open) .cn-drawer") ?? "", /display:none/);
  /* Повна ширина «менше за 720px» — тож 719, а не 720 (рівно 720 ще «широкий»). */
  assert.match(css, /@media\s*\(max-width:\s*719px\)\s*\{[^{}]*\.cn-drawer\s*\{[^{}]*width:100%/);
  assert.doesNotMatch(css, /@media\s*\(max-width:\s*720px\)\s*\{[^{}]*\.cn-drawer/);
});

test("чистий перегляд макета ховає й бічну панель", () => {
  /* `html.cv-clean` ховає оболонку; без цього відкрита панель висіла б над порожнім макетом. */
  assert.match(rule("html.cv-clean .cn-drawer") ?? "", /display:none/);
});

test("кольори правил .cn-* — лише токени (тінь може мати rgba)", () => {
  const bad = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/\.cn-/.test(m[1])) continue;
    const body = m[2].replace(/box-shadow:[^;]*;?/g, "");
    if (/#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i.test(body)) bad.push(m[1].trim());
  }
  assert.deepEqual(bad, [], `літерали кольорів у: ${bad.join(", ")}`);
});

test("3c (ревʼю Task 6): рамка «Забрати довіру» в панелі лишається червоною й на наведенні (`.ctl--out:hover` рівної специфічності, але раніший)", () => {
  assert.match(rule(".cn-dr-untrust") ?? "", /border-color:var\(--bad\)/);
  const hover = rule(".cn-dr-untrust:hover") ?? "";
  assert.match(hover, /border-color:var\(--bad\)/, "без власного :hover рамку забирав `.ctl--out:hover`");
  assert.match(hover, /color:var\(--hi\)/);
});

/* ── «Налаштування → Модулі» (етап Е): сітка карток `.mg` / `.mc` ── */

test("етап Е: кожен клас сітки модулів із розмітки (`mcardHTML`, `emptyCardHTML`, `gridHTML`) має правило як суб'єкт", () => {
  const src = read("connections-view.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  const want = ["mg", "mc", "mc-top", "mc-ic", "mc-name", "mc-tag", "mc-open", "mc-more", "mc-why", "mc-foot", "bdg", "mc--empty", "mc--ask", "sub"];
  for (const c of want) {
    assert.ok(new RegExp(`class="[^"]*\\b${c}\\b`).test(src) || src.includes(`"${c}"`), `розмітка не вживає клас ${c} — список застарів`);
    assert.ok(isSubjectOfSomeRule(c), `клас ${c} без власного правила`);
  }
  for (const k of ["ok", "err", "off", "trust", "missing"]) assert.ok(isSubjectOfSomeRule(`bdg--${k}`), `bdg--${k}`);
});

test("етап Е: картка — flex-колонка з фокус-кільцем, «⋯» має фокус-кільце, сітка — auto-fill від 250px, питання не клікабельне", () => {
  assert.match(rule(".mg") ?? "", /grid-template-columns:repeat\(auto-fill,minmax\(min\(250px,100%\),1fr\)\)/);
  assert.match(rule(".mc") ?? "", /display:flex[\s\S]*flex-direction:column/);
  /* a11y: картка сама не `role=button`; кнопка-назва розтягнута на неї, а «⋯» і дія стоять НАД розтягнутим шаром. */
  assert.match(rule(".mc") ?? "", /position:relative/);
  assert.match(rule(".mc-open::after") ?? "", /content:"";position:absolute;inset:0/);
  assert.match(rule(".mc-open:focus-visible::after") ?? "", /outline:2px solid var\(--sel\)/);
  assert.match(rule(".mc-more") ?? "", /position:relative;z-index:1/);
  assert.match(rule(".mc-foot .ctl") ?? "", /position:relative;z-index:1/);
  assert.match(rule(".mc-more:focus-visible") ?? "", /outline:2px solid var\(--sel\)/);
  assert.match(rule(".mc--empty") ?? "", /border-style:dashed/);
  assert.match(rule(".mc--ask") ?? "", /cursor:default/);
  assert.match(rule("h2.sub") ?? "", /text-transform:uppercase/);
});

test("етап Е: бейдж стану — крапка лише токенами; помилка й «Не встановлено» — червона крапка, а текст світлий (контраст на --s2)", () => {
  assert.match(rule(".bdg--ok::before") ?? "", /background:var\(--ok\)/);
  assert.match(rule(".bdg--err::before") ?? "", /background:var\(--bad\)/);
  assert.match(rule(".bdg--err") ?? "", /color:var\(--hi\)/, "червоний текст на --s2 дає лише ≈4.1:1 (див. шапку розділу)");
  assert.match(rule(".bdg--trust .ico") ?? "", /color:var\(--open\)/);
  for (const sel of [".mg", ".mc", ".mc-why", ".bdg", ".mc--ask", ".mc--empty"]) {
    assert.doesNotMatch(rule(sel) ?? "", /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i, `${sel}: літерал кольору замість токена`);
  }
});

/* ── «Додати модуль» (етап Е): діалог каталогу й «Свій модуль» (`catalog-view.js`) ── */

test("етап Е: кожен клас діалогу каталогу з розмітки має правило як суб'єкт; підсвічена група й пунктирний рядок — окремі правила", () => {
  const src = read("catalog-view.js").replace(/\/\*[\s\S]*?\*\//g, "");
  const found = new Set();
  for (const m of src.matchAll(/class="([^"]+)"/g)) for (const c of m[1].replace(/\$\{[^}]*\}/g, " ").split(/\s+/)) if (/^[a-z][\w-]*[a-z0-9]$/.test(c)) found.add(c);
  for (const c of ["cat-d", "cat-h", "cat-pg", "cat-b", "cat-b--pad", "cat-f", "cat-g", "cat", "cat--own", "steps", "ta", "prompt"]) {
    assert.ok(found.has(c) || src.includes(`"${c}"`) || src.includes(`${c}"`), `розмітка не вживає клас ${c} — список застарів`);
    assert.ok(isSubjectOfSomeRule(c), `клас ${c} без власного правила`);
  }
  assert.ok(src.includes("cat--hl"), "підсвічена група в розмітці");
  assert.ok(isSubjectOfSomeRule("cat--hl"), "cat--hl без правила");
  assert.match(rule(".cat--own") ?? "", /border:1px dashed var\(--line2\)/);
  assert.match(rule(".cat--hl") ?? "", /color-mix\(in srgb,var\(--sel\) 10%,transparent\)/);
  assert.match(rule(".cv-ask--form:has(.cat-d)") ?? "", /width:600px/);
  assert.match(rule(".cat-h [hidden]") ?? "", /display:none/, "`.icob` задає display — без цього правила схований «‹» усе одно видно");
  assert.match(rule(".cat-b") ?? "", /overflow-y:auto/, "довгий каталог прокручується, а не розтягує вікно");
  assert.match(rule(".ta:focus-visible") ?? "", /outline:2px solid var\(--sel\)/);
  for (const sel of [".cat", ".cat--hl", ".cat--own", ".ta", ".prompt"]) {
    assert.doesNotMatch(rule(sel) ?? "", /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i, `${sel}: літерал кольору замість токена`);
  }
});

/* Список каталогу обрізається рівно по межі рядка — «Свій модуль» унизу не видно, і нічого не каже, що список прокручується.
   Підказка — затухання нижнього краю маскою по вмісту (тінь поверх вмісту на темній поверхні діалогу практично невидима). Довжину
   затухання `--cat-fade` веде анімація від прокрутки списку: 32px, поки є що читати, і до 0 в останні 32px; без переповнення
   таймлайна нема, і `--cat-fade` лишається 0px. Без `animation-timeline` затухання нема. Без JS і без підписів. */
test("етап Е: `.cat-b` затухає знизу маскою, а довжину веде анімація від прокрутки самого списку (лише в @supports); старого трюку з фоном нема", () => {
  const outside = css.replace(/@supports \(animation-timeline:scroll\(\)\)\{[^]*?\}\s*\}/, "");
  const base = [...outside.matchAll(/(?:^|\})\s*\.cat-b\{([^{}]*)\}/g)].map((m) => m[1]).join(";");
  assert.match(base, /overflow-y:auto/, "прокрутка лишилась");
  assert.match(base, /(?<!-webkit-)mask-image:linear-gradient\(#000 calc\(100% - var\(--cat-fade\)\),transparent\)/, "маска: непрозорий вмістом, затухання на --cat-fade");
  assert.match(base, /-webkit-mask-image:linear-gradient\(#000 calc\(100% - var\(--cat-fade\)\),transparent\)/, "і з префіксом");
  assert.doesNotMatch(base, /radial-gradient|no-repeat|background:/, "старий трюк local/scroll знято");
  assert.match(rule("@property --cat-fade") ?? "", /syntax:'<length>';inherits:false;initial-value:0px/, "зареєстрована довжина, початково 0 — без анімації затухання нема");
  assert.match(css, /@keyframes cat-fade\{from\{--cat-fade:32px\}to\{--cat-fade:0px\}\}/, "від 32px до 0");
  /* Анімація — ЛИШЕ в @supports: без нього `animation-timeline` у старому браузері лишив би анімацію за часом (довгу, нескінченну в очах). */
  const sup = /@supports \(animation-timeline:scroll\(\)\)\{\s*\.cat-b\{([^{}]*)\}\s*\}/.exec(css)?.[1] ?? "";
  assert.match(sup, /animation:cat-fade linear both/);
  assert.match(sup, /animation-timeline:scroll\(self\)/);
  assert.ok(sup.indexOf("animation-timeline") > sup.indexOf("animation:"), "timeline ПІСЛЯ шортхенда animation, інакше той його скидає");
  assert.match(sup, /animation-range:calc\(100% - 32px\) 100%/, "затухання щезає в останні 32px прокрутки");
  assert.doesNotMatch(base, /animation/, "поза @supports анімації нема");
  assert.doesNotMatch(base, /#(?!000\b)[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i, "жодних інших літералів кольору");
});
