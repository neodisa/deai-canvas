/**
 * Стилі просторів (`app/styles.css`): токени кольорів, фішка й дропдаун, форми у вікні
 * питання, привітання. Сітку висот `css-guards.test.mjs` уже тримає (`ctl*`, `dd-item*`);
 * тут — те, чого вона не бачить: що кольори просторів ЄДИНІ для обох тем і лише шість,
 * що кожен клас, який малює розмітка просторів, має правило (розмітка без стилів —
 * тиха поломка, «кнопка без вигляду»), і що головна кнопка бере палітру оболонки.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { SPACE_COLORS } from "../app/spaces-model.js";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");

/** Тіло першого правила з цим селектором (точний збіг селектора, без списків). */
const rule = (selector) => {
  const esc = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = new RegExp(`(?:^|[}\\s])${esc}\\s*\\{([^{}]*)\\}`).exec(css);
  return m ? m[1] : null;
};

test("токени --space-1…6 є в :root, у OKLCH, і рівно шість", () => {
  const root = /:root\s*\{([^{}]*)\}/.exec(css)[1];
  for (let n = 1; n <= 6; n += 1) {
    assert.match(root, new RegExp(`--space-${n}\\s*:\\s*oklch\\(`), `--space-${n} немає в :root`);
  }
  assert.doesNotMatch(root, /--space-7/, "сьомого кольору модель не знає (`SPACE_COLORS`)");
  assert.equal(SPACE_COLORS.length, 6);
  for (const c of SPACE_COLORS) assert.match(root, new RegExp(`--${c}\\s*:`), `токен ${c} з моделі не оголошено`);
});

test("кольори просторів однакові для обох тем: поза першим :root токени не перевизначаються", () => {
  const redefined = [...css.matchAll(/--space-\d\s*:/g)].length;
  assert.equal(redefined, 6, "--space-N оголошено рівно раз кожен: друге оголошення (темна тема?) розвело б плитки смуги й діалогу");
});

test(".space-dot — плитка 10×10 із радіусом 3 і без стискання", () => {
  const body = rule(".space-dot");
  assert.ok(body, "правила .space-dot немає");
  assert.match(body, /width:10px/);
  assert.match(body, /height:10px/);
  assert.match(body, /border-radius:3px/);
  assert.match(body, /flex:none/);
});

test(".ctl--pri — палітра оболонки (--sel/--on-sel/--sel-hover), і ПІСЛЯ `.ctl:hover`", () => {
  const body = rule(".ctl--pri");
  assert.ok(body, "правила .ctl--pri немає");
  assert.match(body, /background:var\(--sel\)/);
  assert.match(body, /color:var\(--on-sel\)/);
  const hover = rule(".ctl--pri:hover");
  assert.ok(hover);
  assert.match(hover, /background:var\(--sel-hover\)/);
  assert.match(hover, /color:var\(--on-sel\)/);
  assert.ok(css.indexOf(".ctl--pri:hover") > css.indexOf(".ctl:hover{"),
    "однакова специфічність: фон ховера `.ctl--pri` мусить іти ПІСЛЯ `.ctl:hover`");
});

test(".space-h не стискається, а .space-chip має стелю — інакше на 1100px фішка лишалась «Клі…»", () => {
  assert.match(rule(".space-h"), /flex:none/);
  assert.match(rule(".space-chip"), /max-width:\d+px/);
});

test(".dd--spaces ≈300px; .dd-item--muted лише фарбує — жодних висот і відступів (сітка стереже dd-item*)", () => {
  assert.match(rule(".dd--spaces"), /width:300px/);
  for (const sel of [".dd-item--muted .dd-t", ".dd-item--muted .space-dot", ".dd-item--muted .dd-sub"]) {
    const body = rule(sel);
    assert.ok(body, `правила ${sel} немає`);
    assert.doesNotMatch(body, /height|padding|margin/, sel);
  }
  assert.equal(rule(".dd-item--muted"), null, "самому .dd-item--muted висот не даємо");
});

test(".th-head — ряд заголовка й кнопки; .th-h усередині без відступу", () => {
  const body = rule(".th-head");
  assert.match(body, /display:flex/);
  assert.match(body, /justify-content:space-between/);
  assert.match(body, /margin:0 0 14px/);
  assert.match(rule(".th-head .th-h"), /margin:0\s*(?:;|$)/, "відступ несе ряд, а не заголовок: `margin:0 0 14px` тут подвоїв би його");
});

/* Назва простору в голові — дані людини, а кнопок тепер дві («Підключення» й «Нова задача»). Без `flex-wrap` довга
   назва штовхала їх за край вузького вікна: ряд не переносить, а стискати кнопки нічого. З ним обгортка
   `.th-head-acts` іде під заголовок ЦІЛКОМ (вона один флекс-елемент), а `row-gap` не дає їй злипнутись із ним.
   Заголовок мусить уміти скластись: `min-width:0` (інакше флекс-елемент не менший за своє найдовше слово) і
   `overflow-wrap:anywhere` (довге слово без пробілів ламається, а не розпирає голову). Голова ЛІГА — голий `<h1>`
   без `.th-head`, цих правил не торкається. */
test(".th-head переноситься, а заголовок у ній складається: довга назва простору не виштовхує кнопки", () => {
  const body = rule(".th-head");
  assert.match(body, /flex-wrap:wrap/, "ряд не переносить — кнопки поїдуть за край");
  assert.match(body, /gap:\s*8px 12px/, "row-gap 8px: другий рядок не липне до заголовка; column-gap 12px — як був");
  const h = rule(".th-head .th-h");
  assert.match(h, /overflow-wrap:anywhere/, "довге слово без пробілів розпирає голову");
  assert.match(h, /min-width:0/, "флекс-елемент не стискається нижче свого найдовшого слова");
  assert.match(rule(".th-head-acts"), /display:flex/, "кнопки лишаються в одній обгортці — переносяться разом");
});

/* Кожен клас, який малює розмітка просторів, мусить мати правило в styles.css. Береться
   з РЕАЛЬНОГО джерела розмітки (а не зі списку тут): новий клас у `space-dialogs.js`
   чи `shell-bar.js` без стилю червонить цей тест. */
test("кожен клас розмітки просторів має правило в styles.css", () => {
  const classes = new Set();
  for (const f of ["space-dialogs.js", "shell-bar.js"]) {
    const src = read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
    for (const m of src.matchAll(/class="([^"$]+)"/g)) {
      for (const c of m[1].split(/\s+/)) {
        if (/^(?:space-|cv-form|cv-field|cv-lbl|cv-hint|cv-colors?$|cv-ask--form|th-welcome|dd--spaces|dd-item--muted)/.test(c)) classes.add(c);
      }
    }
  }
  assert.ok(classes.size >= 14, `знайдено лише ${classes.size} класів просторів — регексп зламано: ${[...classes]}`);
  const missing = [...classes].filter((c) => !new RegExp(`\\.${c}(?![\\w-])`).test(css));
  assert.deepEqual(missing, [], `класи розмітки без жодного правила: ${missing.join(", ")}`);
});

test("привітання: класи розмітки welcomeHTML мають правила, логотип великий", () => {
  assert.match(rule(".th-welcome-logo svg"), /width:76px/);
  for (const c of ["th-welcome", "th-welcome-logo", "th-welcome-lead", "th-welcome-act"]) {
    assert.ok(new RegExp(`\\.${c}(?![\\w-])`).test(css), `.${c} без правила`);
  }
});

test("форма у вікні питання: кружки перебивають `.cv-ask button` специфічністю, вибраний має галочку", () => {
  const body = rule(".cv-ask .cv-color");
  assert.ok(body, "правила .cv-ask .cv-color немає — кружок успадкував би падінг і рамку `.cv-ask button`");
  assert.match(body, /padding:0/);
  assert.match(body, /width:28px/);
  assert.match(rule(".cv-ask .cv-color .ico"), /display:none/);
  assert.match(rule(".cv-ask .cv-color[aria-checked=true] .ico"), /display:block/);
  assert.match(rule(".cv-ask .cv-color[aria-checked=true]"), /box-shadow/);
  /* Токени `--space-*` на картці без рамки зливаються з фоном: рамка 1px видима на КОЖНОМУ кружку (етап В: темна картка → `--line2`). */
  assert.match(body, /border:1px solid var\(--line2\)/, "кружок без видимої рамки: нетекстовий контраст < 3:1");
  assert.match(rule(".cv-ask--form label,.cv-ask--form p,.cv-ask--form .cv-lbl") ?? "", /white-space:normal/,
    "підписи форми не успадковують `pre-wrap` повідомлень");
});

test("поле з помилкою (`aria-invalid=true`) має червону рамку токеном --bad (темна картка, етап В), і вона сильніша за звичайну рамку поля", () => {
  const body = rule('.cv-field input[aria-invalid="true"]');
  assert.ok(body, "правила для [aria-invalid=true] немає: `ctl.focus(імʼя)` ставить атрибут, а видимої різниці нема");
  assert.match(body, /border-color:var\(--bad\)/);
  assert.match(css, /--bad\s*:\s*#[0-9a-fA-F]{3,8}/, "токена --bad нема в :root");
  /* Специфічність: `.cv-ask input:where(…)` (0,1,1) задає рамку звичайному полю; правило помилки (0,2,1) мусить її перебивати. */
  assert.match(rule(".cv-ask input:where(:not([type=checkbox]):not([type=radio]))"), /border:1px solid var\(--line2\)/);
  /* Один червоний для діалогів: літерал `#c2362e` не живе поза :root (токен, а не копія в кожному правилі). */
  const outside = css.replace(/:root\s*\{[^{}]*\}/, "");
  assert.doesNotMatch(outside, /#c2362e/i, "літерал червоного діалогів повернувся поза :root — розійдеться з токеном");
});

/* ── публікація на свій Vercel (2b-1, Task 3): стилі застережень і плашки ─────────────────────────
   Розмітка (`shell-bar.js` — `.dd-note--public/--stale`; `app.js` — `.cv-notice-body/.cv-notice-sub`) без правил — тиха
   поломка «рядок без вигляду». Кольори — лише токени оболонки, жодного hex/rgb. */
test("`.dd-note--stale` — колір попереджень (токен), `.dd-note--public` лишається звичайною приміткою", () => {
  const stale = rule(".dd-note--stale");
  assert.ok(stale, "правила .dd-note--stale немає");
  assert.match(stale, /color:var\(--open\)/);
  assert.doesNotMatch(stale, /#[0-9a-f]{3,8}\b|rgba?\(/i, "колір не токеном");
  assert.equal(rule(".dd-note--public"), null, "примітка «публічне» успадковує `.dd-note` — власного правила не треба");
  assert.ok(rule(".dd-note"), "базове `.dd-note` на місці");
});

test("плашка з додатковими рядками: `.cv-notice-body` — стовпчик, `.cv-notice-sub` — токен попередження й перенос довгих слів", () => {
  const body = rule(".cv-notice-body");
  assert.ok(body, "правила .cv-notice-body немає");
  assert.match(body, /flex-direction:column/);
  assert.match(body, /min-width:0/, "без цього довгий рядок розпирає плашку за 80vw");
  assert.match(body, /max-height:40vh/, "5 попереджень по 300 знаків + кнопки в один рядок — плашка не вище 40% екрана");
  assert.match(body, /overflow:auto/);
  const sub = rule(".cv-notice-sub");
  assert.ok(sub, "правила .cv-notice-sub немає");
  assert.match(sub, /color:var\(--open\)/);
  assert.match(sub, /overflow-wrap:anywhere/, "довга адреса в попередженні не мусить виходити за плашку");
  assert.doesNotMatch(`${body}${sub}`, /#[0-9a-f]{3,8}\b|rgba?\(/i, "колір не токеном");
  const btn = rule('.cv-notice[data-notice="publish-remote"] button');
  assert.ok(btn, "кнопки плашки Vercel без правила: «Скопіювати посилання» переноситься на два рядки");
  assert.match(btn, /white-space:nowrap/);
  assert.match(btn, /flex:none/);
});

test("ревʼю Task 7: рядок-статус довгого створення (.cv-form-note) і друга лінія помилки форми (pre-line) мають правила, лише токени", () => {
  const note = rule(".cv-form-note");
  assert.ok(note, ".cv-form-note без правила: `showCreateWait` (app.js) додає цей клас — без стилю він виглядав би голим абзацом");
  assert.match(note, /color:var\(--mid\)/, "колір — токеном палітри");
  assert.doesNotMatch(note, /#[0-9a-fA-F]{3,8}\b/, "літерал кольору замість токена");
  const err = rule(".cv-ask--form .cv-form-err");
  assert.ok(err, "правила для другого рядка помилки нема");
  assert.match(err, /white-space:pre-line/, "`.cv-ask--form p` скидає white-space у normal: без цього `\\n` у тексті помилки злипається");
});
