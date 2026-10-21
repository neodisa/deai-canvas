import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
const norm = (s) => s.trim().replace(/\s*([>+~])\s*/g, " $1 ").replace(/\s+/g, " ");
const RULES = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ sels: m[1].split(",").map(norm), body: m[2] }));
const rule = (selector) => RULES.find((r) => r.sels.includes(norm(selector)))?.body ?? null;
/** Тіла УСІХ правил, у списку селекторів яких є `selector` (на відміну від `rule` — першого). */
const rules = (selector) => RULES.filter((r) => r.sels.includes(norm(selector))).map((r) => r.body).join(";");
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

/* ── контраст: токени з `:root`, формула WCAG — як у `css-guards.test.mjs` ───────────────────────────────────────────── */
const tok = (name, depth = 0) => {
  const m = css.match(new RegExp(`--${name}\\s*:\\s*(#[0-9a-fA-F]{6}|var\\(--([a-z0-9-]+)\\))`));
  if (!m) return null;
  if (m[2]) return depth < 5 ? tok(m[2], depth + 1) : null;
  const n = parseInt(m[1].slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const lum = ([r, g, b]) => [r, g, b].map((c) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
  .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const bgToken = (selector) => /background:var\(--([\w-]+)\)/.exec(rule(selector) ?? "")?.[1];

test("вибрана картка (`--s3`): дрібний приглушений текст світліє до `--mid` і тримає AA (на `--dim` там лише 4.30:1)", () => {
  for (const cls of [".wz-opt-instead", ".cn-tag", ".cn-why-detail"]) {
    assert.match(rules(`.wz-opt:has(input:checked) ${cls}`), /color:var\(--mid\)/, `${cls} у вибраній картці лишився на --dim`);
  }
  const bg = bgToken(".wz-opt:has(input:checked)");
  assert.ok(bg, "вибрана картка без `background:var(--…)` — контраст не порахувати");
  assert.ok(contrast(tok("mid"), tok(bg)) >= 4.5, `--mid на --${bg}: ${contrast(tok("mid"), tok(bg)).toFixed(2)}:1`);
});

test("помилка поля на картці кроку 3 (`--s2`): текст — примішка `--hi` до `--bad` з контрастом >= 4.5:1 (чистий `--bad` там 4.09:1)", () => {
  const body = rules(".wz-card .cn-field-err");
  const m = /color:color-mix\(in srgb,\s*var\(--([\w-]+)\)\s*(\d+)%,\s*var\(--([\w-]+)\)\)/.exec(body);
  assert.ok(m, `нема color-mix з двох токенів: «${body}»`);
  const [a, p, b] = [tok(m[1]), Number(m[2]) / 100, tok(m[3])];
  const mix = a.map((c, i) => c * p + b[i] * (1 - p));
  const bg = bgToken(".cn-card");
  assert.equal(bg, "s2", "картка змінила тло — перерахуйте охоронця");
  assert.ok(contrast(mix, tok(bg)) >= 4.5, `помилка на --${bg}: ${contrast(mix, tok(bg)).toFixed(2)}:1`);
});

test("крошка сторінки оверлею: `.crumb.crumb--page{max-width:none}` — два класи, бо глобальний `.crumb{max-width:110px}` пізніше в файлі", () => {
  assert.match(rule(".crumb.crumb--page") ?? "", /max-width:none/);
  /* `.crumb--flat` загалом ліміту не знімає: ним користується зовнішня оболонка превʼю (там обрізання — свідоме). */
  assert.doesNotMatch(rule(".crumb--flat") ?? "", /max-width/);
});

test("кружок кольору: кільце фокуса не накладається на кільце вибору, вимкнений виглядає вимкненим", () => {
  const off = Number(/outline-offset:(\d+)px/.exec(rule(".wz .cv-color:focus-visible") ?? "")?.[1]);
  assert.ok(off >= 5, `відступ кільця фокуса ${off}px: кільце вибору (box-shadow 2+4px) сягає 4px — має бути більше`);
  const dis = rule(".wz .cv-color:disabled") ?? "";
  assert.match(dis, /cursor:default/);
  assert.match(dis, /opacity:\.\d+/);
});

test("варіант модуля, що вимкнений (майстер зайнятий): курсор і прозорість — як у вимкнених контролів", () => {
  const b = rule(".wz-opt:has(input:disabled)") ?? "";
  assert.match(b, /cursor:default/);
  assert.match(b, /opacity:\.\d+/);
});

test("довга назва модуля без пробілів переноситься (`overflow-wrap:anywhere`) у «замість …» і в рядку «Без модуля»", () => {
  for (const sel of [".wz-opt-instead", ".wz-off > span"]) {
    const b = rules(sel);
    assert.match(b, /overflow-wrap:anywhere/, sel);
    assert.match(b, /min-width:0/, sel);
  }
});

/* ── жодних колірних літералів у правилах майстра: лише токени (`var(--…)`) і `color-mix` від них ───────────────────── */
const COLOUR_PROPS = /^(color|background(-color)?|border(-(top|right|bottom|left))?(-color)?|outline(-color)?|box-shadow|accent-color|fill|stroke|caret-color|text-decoration(-color)?)$/;
const KEYWORDS = new Set(["color-mix", "in", "srgb", "solid", "dashed", "dotted", "none", "transparent", "currentcolor", "inherit", "inset"]);
/** Що в колірних властивостях тіла правила не є токеном: `#hex`, `rgb()/hsl()/…`, іменований колір — будь-яке слово поза переліком. */
const colourLiterals = (body) => {
  const bad = [];
  for (const decl of body.split(";")) {
    const i = decl.indexOf(":");
    if (i < 0 || !COLOUR_PROPS.test(decl.slice(0, i).trim())) continue;
    const v = decl.slice(i + 1).replace(/var\(--[\w-]+\)/g, "");
    if (/#[0-9a-fA-F]{3,8}\b/.test(v)) bad.push(decl.trim());
    else for (const w of v.match(/[a-zA-Z][\w-]*/g) ?? []) if (!KEYWORDS.has(w.toLowerCase()) && !/^\d*(px|em|rem|vh|vw)$/.test(w)) bad.push(`${decl.trim()} → ${w}`);
  }
  return bad;
};

test("охоронець літералів сам ловить: hex, rgba, hsl, іменований колір — і пропускає токени та color-mix", () => {
  for (const body of ["color:#fff", "color:#A1B2C3", "box-shadow:0 0 0 1px rgba(0,0,0,.3)", "background:hsl(10 20% 30%)", "border:1px solid red",
    "outline:2px solid white", "background-color:oklch(0.5 0.1 200)"]) {
    assert.ok(colourLiterals(body).length > 0, `не спіймано: ${body}`);
  }
  for (const body of ["color:var(--hi)", "border:1px dashed var(--line2)", "box-shadow:0 0 0 2px var(--s1),0 0 0 4px var(--hi)",
    "color:color-mix(in srgb,var(--bad) 55%,var(--hi))", "outline:none", "background:transparent", "border-radius:6px", "width:28px"]) {
    assert.deepEqual(colourLiterals(body), [], body);
  }
});

test("правила майстра (`.wz…`) не містять колірних літералів — лише токени", () => {
  const mine = RULES.filter((r) => r.sels.some((x) => /\.wz(?![\w-])|\.wz-/.test(x)));
  assert.ok(mine.length >= 40, `знайдено лише ${mine.length} правил майстра — регексп зламано`);
  const bad = mine.flatMap((r) => colourLiterals(r.body).map((x) => `${r.sels.join(",")}{${x}}`));
  assert.deepEqual(bad, [], `колірні літерали замість токенів:\n${bad.join("\n")}`);
});
