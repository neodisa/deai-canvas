import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
const norm = (s) => s.trim().replace(/\s*([>+~])\s*/g, " $1 ").replace(/\s+/g, " ");
const RULES = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ sels: m[1].split(",").map(norm), body: m[2] }));
const rule = (selector) => RULES.find((r) => r.sels.includes(norm(selector)))?.body ?? null;
const subjectOf = (sel) => sel.split(/\s*[>+~]\s*|\s+/).pop();
const isSubject = (cls) => RULES.some((r) => r.sels.some((s) => new RegExp(`\\.${cls}(?![\\w-])`).test(subjectOf(s))));

/** Тіла всіх `@media`-блоків із заданим умовним заголовком (з урахуванням вкладених дужок правил). */
const mediaBodies = (query) => {
  const out = [];
  const head = `@media ${query}{`;
  for (let at = css.indexOf(head); at !== -1; at = css.indexOf(head, at + 1)) {
    let depth = 1;
    let i = at + head.length;
    for (; i < css.length && depth > 0; i++) depth += css[i] === "{" ? 1 : css[i] === "}" ? -1 : 0;
    out.push(css.slice(at + head.length, i - 1));
  }
  return out;
};

test("кожен клас `wz-*` розмітки майстра має правило, де він — суб'єкт", () => {
  const src = read("wizard-view.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  const classes = new Set();
  for (const m of src.matchAll(/class="([^"]+)"/g)) {
    for (const c of m[1].replace(/\$\{[^}]*\}/g, " ").split(/\s+/)) if (/^wz-/.test(c) && !c.endsWith("-")) classes.add(c);
  }
  assert.ok(classes.size >= 25, `знайдено лише ${classes.size} класів — регексп зламано: ${[...classes]}`);
  const missing = [...classes].filter((c) => !isSubject(c));
  assert.deepEqual(missing, [], `класи без власного правила: ${missing.join(", ")}`);
});

test("стан кроку (`wz-step--done|cur|todo`) фарбує смужку: клас сам нічого не малює, лише вирішує колір `.wz-step-bar` всередині", () => {
  /* Розмітка збирає їх інтерполяцією (`wz-step--${st}`), тож з `class="…"` вони не видні — і суб'єктом правила не бувають
     (як `cn-res--ok` у `connections-css`): правило — «стан + смужка». Три різні кольори, інакше смужка не каже, де ми. */
  const fills = ["done", "cur", "todo"].map((k) => /background:([^;]+)/.exec(rule(`.wz-step--${k} .wz-step-bar`) ?? "")?.[1]);
  assert.ok(fills.every(Boolean), `нема правила «стан + смужка» для всіх трьох станів: ${fills}`);
  assert.equal(new Set(fills).size, 3, `стани кроку не розрізняються кольором: ${fills}`);
});

test("кружки кольору на темній сторінці мають власні правила (світлі правила діалогу — лише в `.cv-ask`)", () => {
  assert.match(rule(".wz .cv-color") ?? "", /width:28px/);
  assert.match(rule('.wz .cv-color[aria-checked=true] .ico') ?? "", /display:block/);
});

test("вибраний варіант підсвічений (:has(:checked)) і має видимий фокус", () => {
  assert.ok(rule(".wz-opt:has(input:checked)"), "нема підсвітки вибраного варіанта");
  assert.ok(rule(".wz-opt:has(input:focus-visible)"), "нема кільця фокуса на картці-мітці");
});

test("назви кроків візуально приховані, але лишаються для читача екрана (не display:none)", () => {
  const b = rule(".wz-step-name") ?? "";
  assert.match(b, /position:absolute/);
  assert.doesNotMatch(b, /display:none/);
});

test("вузьке вікно: колонка на всю ширину з полями 16px, дві колонки кроку 4 — одна", () => {
  const blocks = mediaBodies("(max-width:719px)").filter((b) => /\.wz\{/.test(b));
  assert.equal(blocks.length, 1, "рівно один @media (max-width:719px) із правилами майстра");
  assert.match(blocks[0], /\.wz\{[^}]*padding:[^}]*16px/);
  assert.match(blocks[0], /\.wz-two\{[^}]*grid-template-columns:1fr/);
});

test("майстер — частина `#tasks-home`: чистий перегляд ховає його разом з оверлеєм (окремого правила не треба)", () => {
  assert.match(css, /html\.cv-clean #tasks-home/);
});

test("поле теки кроку 4 справді ховається: `.cn-field{display:flex}` перебиває UA-правило `[hidden]`", () => {
  /* Без цього правила `#wz-from-f[hidden]` лишається видимим (виміряно в Chromium). Лише в майстрі — 3a не чіпаємо. */
  assert.match(rule(".wz .cn-field[hidden]") ?? "", /display:none/);
});

test("кнопки привітання не злиплі: `.th-welcome-act` має проміжок і переноситься", () => {
  const b = rule(".th-welcome-act") ?? "";
  assert.match(b, /gap:/);
  assert.match(b, /flex-wrap:wrap/);
});
