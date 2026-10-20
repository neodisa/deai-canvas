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
  assert.match(d, /top:var\(--h-bar\)/);
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
