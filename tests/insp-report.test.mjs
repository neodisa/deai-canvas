import assert from "node:assert/strict";
import test from "node:test";

import { measureHTML, reportHTML } from "../app/vendor/insp-report.js";
import { GROUPS } from "../app/vendor/inspector-dom.js";

const D = (o = {}) => ({ prop: "gap", computed: "8px", raw: "var(--sp-2)",
  token: "--sp-2", tokenValue: "8px", verdict: "token", hint: [], ...o });
const P = (o = {}) => ({ crumbs: ["body", "main", "div.mk-card"],
  groups: { box: [D()] }, blocked: false, partial: false, ...o });

/**
 * Звіт так, як його малює ПРАВА ПАНЕЛЬ ОБОЛОНКИ, — з ручками тюнера.
 *
 * Прапорець `tunable` зʼявився 18.09.2026 і типово ВИМКНЕНИЙ: рендерер
 * монтується у два документи, і в другому (shadow-корінь оверлея на сторінці
 * без канваса) ручку нікому провести — проводка й модель тюнера живуть у
 * батьківському вікні. Забутий прапорець мусить давати чесний текст, а не
 * мертву ручку, тому типове значення саме таке, а панель вмикає ручки явно
 * (`shell-inspect.js`). Тести нижче, що говорять про ручки, говорять ПРО
 * ПАНЕЛЬ — звідси хелпер; що віддає інший документ, перевіряє окремий блок
 * наприкінці файла.
 */
const panelHTML = (payload) => reportHTML(payload, { tunable: true });

test("крихти — кнопки з індексом предка, остання = сам елемент", () => {
  const h = reportHTML(P());
  assert.match(h, /data-act="inspcrumb" data-val="0"[^>]*>body</);
  assert.match(h, /data-act="inspcrumb" data-val="2"[^>]*>div\.mk-card</);
});

/* ── Вирок: КРАПКА в полі, імена — у титулі (T-39) ────────────────────────
   Бейдж із іменем токена стояв у рядку до T-39 і був однією з чотирьох
   причин, чому рядок переносився й ріс до 44px (разом із перекресленим
   «було», полем і одиницею). Тепер у рядку — крапка сталого розміру, а всі
   слова (токен, «хардкод», підказки) переїхали в титул поля. Перевіряємо
   ОБИДВА боки: що колір вироку видно на екрані і що слова не зникли. */

test("вирок token — зелена крапка, а імʼя токена в титулі поля", () => {
  const h = reportHTML(P());
  assert.match(h, /class="insp-dot insp-dot--tok"/);
  assert.match(h, /title="gap · 8px · --sp-2"/,
    "імʼя токена мусить лишитись читабельним — воно в титулі");
  assert.doesNotMatch(h, /insp-token/, "бейджа з іменем у рядку більше немає");
});

test("вирок hardcode — бурштинова крапка, підказки в титулі", () => {
  const h = reportHTML(P({ groups: { box: [D({ prop: "margin-top", verdict: "hardcode",
    token: null, tokenValue: null,
    hint: [{ name: "--sp-3", tier: "used" }, { name: "--gap-3", tier: "used" }] })] } }));
  assert.match(h, /class="insp-dot insp-dot--hard"/);
  assert.match(h, /хардкод → --sp-3, --gap-3/);
});

test("вирок unlinked — крапки немає зовсім: це не сигнал, а відсутність сигналу", () => {
  const h = reportHTML(P({ groups: { box: [D({ prop: "margin-top", computed: "0px",
    verdict: "unlinked", token: null })] } }));
  assert.doesNotMatch(h, /insp-dot/,
    "нуль відступу `unlinked` стоїть у кожному другому полі — крапка на "
    + "кожному з них перетворила б вирок із сигналу на тло");
});

test("підказка несе РІВЕНЬ: доведена — просто ім'я, здогадна — тьмяна й з титулом", () => {
  /* Рівні приходять із `hintFor` (`inspector-core.js`): 'used' — токен уже
     вживають у макеті для цієї ж родини властивостей, 'shape' — не вживають
     ніде, збіг лише за значенням. Панель, що малює їх однаково, видає здогад
     за факт — тобто повертає рівно ту брехню про токен, заради якої рівні й
     заводились. */
  const h = reportHTML(P({ groups: { box: [D({ prop: "margin-top", verdict: "hardcode",
    token: null, tokenValue: null, hint: [{ name: "--sp-3", tier: "used" },
      { name: "--gap-3", tier: "shape" }] })] } }));
  /* До T-39 різницю ніс клас (`insp-maybe`, тьмяніший бейдж). Бейджі пішли, і
     тепер її несе СЛОВО поруч з іменем — у титулі немає ні кольору, ні
     прозорості, а різниця мусить лишитись видимою. */
  assert.match(h, /--sp-3, --gap-3 \(здогад\)/,
    "здогадна підказка мусить бути позначена словом — у титулі іншого носія немає");
  assert.doesNotMatch(h, /--sp-3 \(здогад\)/, "доведену позначати нічим не треба");
});

test("недійсна підказка викидається — тим самим правилом, що в пакеті", () => {
  /* До 18.09.2026 тут перевірялось протилежне: голий рядок МАЛЮВАВСЯ, і то як
     ДОВЕДЕНА підказка, з поясненням «звіт міг зняти старіша версія оверлея».
     Такого випадку не існує: `insp-report.js` і `inspector.js` віддаються з
     одного `/app/vendor/` в одному завантаженні, а звіт ніде не зберігається.
     Зате існувала РОЗБІЖНІСТЬ: `hintOf` (`app/tuner-model.js`) ту саму форму
     викидає. Одна недійсна підказка — дизайнеру факт, Клоду нічого; для фічі,
     чий сенс у тому, щоб панель і пакет казали одне, це і є вада.
     Тепер правило спільне: немає імені — немає підказки. */
  const h = reportHTML(P({ groups: { box: [D({ verdict: "hardcode", token: null,
    tokenValue: null, hint: ["--sp-3", null, { tier: "used" },
      { name: "--gap-3", tier: "used" }] })] } }));
  assert.doesNotMatch(h, /--sp-3/, "голий рядок не має імені у формі підказки — "
    + "у пакет він не їде, отже й на екран не сміє");
  assert.doesNotMatch(h, /object Object/, "сміття не сміє ставати текстом");
  assert.match(h, /--gap-3/, "придатна підказка з того ж списку мусить лишитись");
});

test("невідомий рівень — ЗДОГАД, а не факт (той самий бік, що в пакеті)", () => {
  /* `hintOf` на невідомому `tier` ставить у пакет здогад. Дзеркальне правило
     «все, що не 'shape', — факт» давало б протилежне: Клоду здогад, дизайнеру
     факт. Розходитись ці два описи можуть лише в бік обережності. */
  const h = reportHTML(P({ groups: { box: [D({ prop: "margin-top", verdict: "hardcode",
    token: null, tokenValue: null, hint: [{ name: "--sp-9", tier: "новий-рівень" }] })] } }));
  assert.match(h, /--sp-9 \(здогад\)/);
});

test("unknown НЕ показує імені токена — інакше інструмент бреше про походження", () => {
  /* ⛔ Правило честі пережило переїзд бейджа в титул (T-39), і саме тут це
     перевіряється: у титулі місця вистачило б на все, і саме тому спокуса
     «показати хоч щось» там сильніша, ніж була в бейджі. */
  for (const verdict of ["unknown", "unlinked"]) {
    const h = reportHTML(P({ groups: { box: [D({ verdict,
      token: "--sp-2", tokenValue: "8px" })] } }));
    assert.doesNotMatch(h, /--sp-2/, verdict);
  }
  assert.match(reportHTML(P({ groups: { box: [D({ verdict: "unknown" })] } })),
    /insp-dot--unk/, "сіра крапка лишається: «не розібрали» — теж відповідь");
});

test("екранування: значення з розмітки не стає розміткою", () => {
  const h = reportHTML(P({ crumbs: ['<img src=x onerror=alert(1)>'],
    groups: { box: [D({ computed: '"><b>x</b>' })] } }));
  assert.doesNotMatch(h, /<img|<b>/);
  assert.match(h, /&lt;img/);
});

test("blocked і partial дають попередження, без них — жодного", () => {
  assert.match(reportHTML(P({ blocked: true })), /insp-warn/);
  assert.match(reportHTML(P({ partial: true })), /insp-warn/);
  assert.doesNotMatch(reportHTML(P()), /insp-warn/);
});

test("порожній payload (нічого не запінено) — порожній рядок, не порожня рамка", () => {
  assert.equal(reportHTML(null), "");
});

test("кожна група GROUPS має заголовок у словнику", () => {
  for (const k of Object.keys(GROUPS)) {
    assert.doesNotThrow(() => reportHTML(P({ groups: { [k]: [D()] } })), k);
  }
});

test("кольорова плитка — лише для color-властивостей, і рівно ОДНА", () => {
  /* Плиток у рядку мусить бути одна: пікер ПІДМІНЯЄ собою зразок, а не стає
     поруч із ним — два кольорові квадрати читались би як два різні кольори.
     Тому перевіряємо обидві гілки разом, а не саму лише наявність зразка. */
  const solid = panelHTML(P({ groups: { color: [D({ prop: "background-color",
    computed: "rgb(0, 0, 0)", verdict: "unlinked", token: null })] } }));
  assert.match(solid, /insp-pick/, "суцільний колір мусить давати пікер");
  assert.doesNotMatch(solid, /insp-sw/, "пікер і зразок разом — дві плитки в рядку");

  /* Альфу нативний пікер не вміє (він знає лише `#rrggbb`), тож там лишається
     старий зразок: пікер, що мовчки згубив би прозорість, збрехав би про
     значення. */
  const alpha = panelHTML(P({ groups: { color: [D({ prop: "background-color",
    computed: "rgba(0, 0, 0, 0.5)", verdict: "unlinked", token: null })] } }));
  assert.match(alpha, /insp-sw/, "напівпрозорий колір лишається зі зразком");
  assert.doesNotMatch(alpha, /insp-pick/, "пікер не вміє альфи — не сміє вдавати, що вміє");

  const num = panelHTML(P({ groups: { color: [D({ prop: "border-width",
    computed: "1px" })] } }));
  assert.doesNotMatch(num, /insp-sw|insp-pick/, "число — не колір");
});

/* ── Розкладка звіту (T-39) ────────────────────────────────────────────────
   Затверджений макет — `docs/proto/tuner-panel.html`, варіант А. Вимога, з
   якої все почалось, ВИСОТОЮ не перевіряється в node (її міряє браузер, див.
   `tests/live/tuner.test.mjs`), зате перевіряється все, ЧИМ вона досягнута:
   чотири відступи однією смугою, парні властивості у дві колонки, одиниця
   всередині поля, усічений текст плюс повне значення в титулі.

   ⛔ Найдорожча помилка нової розкладки — не косметична: властивість, яку
   таблиця `LAYOUT` не назвала і яку рендерер забув би домалювати «рештою»,
   зникає зі звіту мовчки. Перша перевірка нижче саме про це. */

const FULL = () => ({
  crumbs: ["body"], blocked: false, partial: false,
  groups: {
    box: ["margin-top", "margin-right", "margin-bottom", "margin-left",
      "padding-top", "padding-right", "padding-bottom", "padding-left"]
      .map((prop) => D({ prop, computed: "0px", verdict: "unlinked", token: null })),
    layout: [D({ prop: "display", computed: "block", verdict: "hardcode", token: null }),
      D({ prop: "width", computed: "676.8px", verdict: "unlinked", token: null }),
      D({ prop: "height", computed: "261.5px", verdict: "unlinked", token: null })],
    flex: [D({ prop: "gap", computed: "24px" }),
      D({ prop: "align-items", computed: "center", verdict: "hardcode", token: null })],
    type: [D({ prop: "font-family", computed: "e-Ukraine, system-ui, sans-serif" }),
      D({ prop: "font-size", computed: "44px", verdict: "hardcode", token: null }),
      D({ prop: "font-weight", computed: "700", verdict: "hardcode", token: null }),
      D({ prop: "line-height", computed: "47.5px", verdict: "unlinked", token: null }),
      D({ prop: "letter-spacing", computed: "-0.88px", verdict: "unlinked", token: null })],
    color: [D({ prop: "color", computed: "rgb(26, 28, 31)", verdict: "unlinked", token: null }),
      D({ prop: "background-color", computed: "rgba(0, 0, 0, 0.5)",
        verdict: "unlinked", token: null }),
      D({ prop: "border-color", computed: "rgb(0, 0, 0)", verdict: "unlinked", token: null }),
      D({ prop: "border-width", computed: "0px", verdict: "unlinked", token: null }),
      D({ prop: "border-radius", computed: "0px", verdict: "unlinked", token: null })],
  },
});

test("жодна властивість payload не загубилась і жодна не намальована двічі", () => {
  const html = panelHTML(FULL());
  const props = Object.values(FULL().groups).flat().map((d) => d.prop);
  for (const prop of props) {
    const n = (html.match(new RegExp(`title="${prop} `, "g")) || []).length;
    assert.equal(n, 1,
      `${prop} намальовано ${n} разів — розкладка (LAYOUT) зʼїла або здублювала `
      + "рядок звіту, і зовні це видно лише тим, що чогось бракує");
  }
});

test("чотири відступи — ОДНІЄЮ смугою зі стрілками, а не чотирма рядками", () => {
  const html = panelHTML(FULL());
  assert.equal((html.match(/class="insp-quad"/g) || []).length, 2,
    "смуг мусить бути дві — зовнішні відступи й внутрішні");
  for (const glyph of ["↑", "→", "↓", "←"]) {
    assert.ok(html.includes(`<span class="insp-ico">${glyph}</span>`), glyph);
  }
  /* Імені властивості в смузі немає — його каже стрілка. Але для читача з
     екрана стрілка не каже нічого, тому повне імʼя лишається в `aria-label`
     і в титулі. */
  assert.match(html, /title="margin-bottom · 0px ·/);
  assert.match(html, /aria-label="margin-bottom"/);
});

test("парні властивості стоять у дві колонки під спільними підписами", () => {
  const html = panelHTML(FULL());
  const pairs = html.match(/<div class="insp-pairlbl">[\s\S]*?<\/div>/g) || [];
  assert.equal(pairs.length, 4,
    "пар чотири: ширина|висота, кегль|інтерліньяж, насиченість|трекінг, рамка|радіус");
  assert.ok(pairs.some((x) => x.includes("Ширина") && x.includes("Висота")));
  assert.ok(pairs.some((x) => x.includes("Кегль") && x.includes("Інтерліньяж")));
});

test("одиниця — ВСЕРЕДИНІ поля, і саме тому ширина поля не залежить від значення", () => {
  const html = panelHTML(FULL());
  /* `insp-unit` стоїть ПІСЛЯ поля й усередині того самого `insp-f`: до T-39
     він був сусідом поля в комірці, тож рядок ріс від довжини значення. */
  assert.match(html, /data-prop="font-size"[^>]*><span class="insp-unit">px<\/span>/);
  /* А у СМУЗІ відступів одиниці немає свідомо: getComputedStyle віддає
     margin/padding завжди в px, тобто там це стала, і чотири поля в рядок
     інакше не лишають місця числу. Правда при цьому не губиться — повне
     значення з одиницею стоїть у титулі. */
  assert.doesNotMatch(html,
    /data-prop="margin-top"[^>]*><span class="insp-unit">/,
    "у смузі з чотирьох полів одиниця зʼїла б саме число");
  assert.match(html, /title="margin-top · 0px ·/);
});

test("титул ОДИН на поле — підказка ручки не накриває собою походження", () => {
  /* Титул на полі й титул на полі вводу всередині нього — два різні спливні
     написи, і виграє внутрішній: він накриває майже всю площу поля. Тобто
     походження значення, заради якого титул у T-39 і заводили, дизайнер
     бачив би лише навівшись на тонку смужку падингу. */
  const h = panelHTML(P());
  assert.doesNotMatch(h, /<input[^>]*title=/,
    "у контрола зʼявився власний титул — він накриє титул поля");
  assert.match(h, /title="gap · 8px · --sp-2 · Крутити значення[^"]*"/,
    "підказка про ручку мусить бути в титулі ПОЛЯ, разом із рештою");
});

test("довге значення усікається класом, а повне лежить у титулі", () => {
  const long = "e-Ukraine, system-ui, sans-serif";
  const html = panelHTML(FULL());
  assert.match(html, new RegExp(`title="font-family · ${long}`),
    "повне значення мусить лишитись досяжним — інакше усічення це втрата");
  assert.match(html, new RegExp(`class="insp-txt">${long}<`),
    "значення мусить малюватись саме тим класом, що усікає (insp-txt)");
});

test("широкий рядок несе ІМʼЯ властивості — інакше три кольори не розрізнити", () => {
  const html = panelHTML(FULL());
  for (const prop of ["color", "background-color", "border-color"]) {
    assert.ok(html.includes(`<span class="insp-nm">${prop}</span>`), prop);
  }
});

test("властивість поза розкладкою не зникає — малюється широким рядком", () => {
  /* Уся група `flex` (і будь-яка майбутня в GROUPS) у таблиці розкладки не
     названа: там немає пар, і вигадувати їх не треба. Але й губитись вона не
     сміє. */
  const html = panelHTML(FULL());
  assert.match(html, /<span class="insp-nm">align-items<\/span>/);
  assert.match(html, /data-prop="gap"/);
});

/* ── Ручки тюнера в рядках (Task 14) ───────────────────────────────────────
   Ручка ЖИВА, але нікуди не пише: інлайн-стиль на макеті, вихід — пакет
   рекомендацій. Тут перевіряється рівно розмітка ручок; що вона справді
   крутить макет, доводить `tests/live/tuner.test.mjs`. */

test("числове значення — редаговане поле з кроком", () => {
  const h = panelHTML(P());
  assert.match(h, /data-act="insptune" data-prop="gap"/);
  assert.match(h, /value="8"/, "у полі мусить стояти саме число, без одиниці");
  assert.match(h, /insp-unit">px</, "одиниця лишається підписом, а не частиною поля");
});

test("крок — того ж порядку, що шкала властивості", () => {
  /* Крок 1 на вазі шрифту не означає нічого (шкала ваг — сотнями), а цілий
     крок на `line-height: 1.5` — це вдвічі-втричі. Ручка з чужим кроком або
     нічого не робить, або перестрибує все. */
  const w = panelHTML(P({ groups: { type: [D({ prop: "font-weight",
    computed: "400", raw: "400", token: null, verdict: "hardcode" })] } }));
  assert.match(w, /step="100"/);
  const lh = panelHTML(P({ groups: { type: [D({ prop: "line-height",
    computed: "1.5", raw: "1.5", token: null, verdict: "hardcode" })] } }));
  assert.match(lh, /step="0.1"/);
  assert.match(panelHTML(P()), /step="1"/, "піксель крутиться пікселем");
});

test("накручене поле позначене СТАНОМ, а старе значення — в титулі", () => {
  const h = panelHTML(P({ tuned: { gap: { from: "8px", to: "12px" } } }));
  assert.match(h, /<div class="insp-f"[^>]*data-tuned=""/,
    "накручене поле мусить бути позначене — інакше не видно, що ти тут крутив");
  assert.match(h, /title="gap · 8px · було 8px · --sp-2 ·/,
    "старе значення мусить лишитись досяжним — воно в титулі й у списку змін");
  /* Поле показує `computed`, тобто правду про МАКЕТ, а не `to` з моделі: якщо
     вони розійшлись (макет перезавантажили), чесніше показати браузерне. */
  assert.match(h, /data-act="insptune"[^>]*value="8"/);
  assert.doesNotMatch(panelHTML(P()), /data-tuned/, "нічого не крутили — позначати нічого");
});

/* ⛔ Правка, якої на ЦЬОМУ документі немає (`missing`), — поле мусить це
   СКАЗАТИ. Знайдено живцем 18.09.2026 (`bf360`, it6/main): пакет піднявся з
   диска, селектор елемента ніс клас, який дописує власний скрипт макета, і в
   мить `load` не збігся ні з чим. Поле при цьому показувало недоторкане
   число сторінки під синім тлом «накручено» — тобто стверджувало зміну,
   якої на макеті немає. МУТАЦІЯ: прибрати `data-miss`/рядок титулу у
   `fieldHTML` — перевірка червоніє, бо від накрученого-й-накладеного цей
   стан не відрізнити нічим. */
test("правка, яка НЕ лягла на цю сторінку, позначена й пояснена в титулі", () => {
  const miss = panelHTML(P({ tuned: { gap: { from: "8px", to: "12px", missing: true } } }));
  assert.match(miss, /<div class="insp-f"[^>]*data-miss=""/,
    "поле мусить казати, що правки на макеті немає — інакше воно бреше тлом");
  assert.match(miss, /data-tuned=""/,
    "правка з пакета нікуди не ділась — поле лишається накрученим");
  assert.match(miss, /title="[^"]*(Не лягло|Not applied)/,
    "позначку без пояснення прочитають як «правку загублено»");
  /* Зворотний бік: накручене-й-накладене позначки НЕ отримує, інакше вона
     стоїть на всьому і не означає нічого. */
  const ok = panelHTML(P({ tuned: { gap: { from: "8px", to: "12px" } } }));
  assert.doesNotMatch(ok, /data-miss/);
  assert.doesNotMatch(ok, /Не лягло|Not applied/);
});

test("у рядку звіту НЕМАЄ ні перекресленого «було», ні кнопки скидання", () => {
  /* ⛔ Свідома зміна контракту (T-39), а не послаблення. Перекреслене старе
     значення було ЧЕТВЕРТИМ елементом рядка (поруч із полем, одиницею й
     бейджем) і не влазило в колонку 185px: рядок переносився і ріс із 16px до
     44px, зсуваючи все нижче. Воно дублювало список змін унизу панелі — там
     воно й лишилось, разом із хрестиком «скинути цю правку»
     (`insptunedrop`). Тобто зникла не можливість, а другий її вхід. */
  const h = panelHTML(P({ tuned: { gap: { from: "8px", to: "12px" } } }));
  assert.doesNotMatch(h, /insp-was/);
  assert.doesNotMatch(h, /insptuneoff/);
});

test("накручене береться лише ВЛАСНЕ, не з прототипу", () => {
  /* `tuned['constructor']` без перевірки власності віддав би функцію з
     прототипу — тобто правку, якої ніхто не робив, на кожному полі. */
  const h = panelHTML(P({ groups: { box: [D({ prop: "constructor" })] },
    tuned: {} }));
  assert.doesNotMatch(h, /data-tuned/);
});

test("нечислове значення не отримує степера", () => {
  for (const v of ["Georgia, serif", "block", "normal", "1px solid rgb(0, 0, 0)", "auto"]) {
    const h = panelHTML(P({ groups: { type: [D({ prop: "font-family",
      computed: v, raw: null, token: null, verdict: "unlinked" })] } }));
    assert.doesNotMatch(h, /data-act="insptune"/, v);
  }
});

test("колір отримує пікер із розкритим у #rrggbb значенням", () => {
  const h = panelHTML(P({ groups: { color: [D({ prop: "color",
    computed: "rgb(26, 28, 31)", raw: null, token: null, verdict: "unlinked" })] } }));
  assert.match(h, /data-act="insptunecolor" data-prop="color"/);
  assert.match(h, /value="#1a1c1f"/,
    "нативний пікер знає лише #rrggbb — інакше він відкриється не на тому кольорі");
  assert.doesNotMatch(h, /data-act="insptune"/, "колір крутять пікером, а не кроком");
});

test("ворожому значенню зразок не малюється взагалі", () => {
  for (const bad of ['red;background:url(//evil.example/x)', 'red" onmouseover="x',
                     'red\\3a x', 'url(http://evil.example/x)']) {
    const h = panelHTML(P({ groups: { color: [D({ prop: "color", computed: bad,
      verdict: "unlinked", token: null })] } }));
    assert.doesNotMatch(h, /insp-sw/, bad);
  }
});

test("порожній computed дає прочерк, а не порожнє поле", () => {
  for (const v of ["", null]) {
    assert.match(reportHTML(P({ groups: { box: [D({ computed: v })] } })),
      /class="insp-txt">—</);
  }
});

/* ── Два документи: де ручки живі, а де їх не буває ────────────────────────
   Рендерер монтується у ДВА документи (шапка `insp-report.js`): права панель
   оболонки і shadow-корінь оверлея на сторінці БЕЗ канваса. Проводка ручок
   (`data-act="insptune…"` → `BAR_ACTIONS` → модель тюнера) живе в
   БАТЬКІВСЬКОМУ вікні — у другого документа її немає і бути не може.
   До 18.09.2026 ручки малювались безумовно, і на `/commented?…` стояло 15
   крутилок і 3 пікери, жодна з яких ні на що не реагувала. Це рівно та вада,
   від якої застерігає докстрінг `NUMERIC`, лише застосована не до значень, а
   до документів: дизайнер не розрізняє «крок не існує» і «натиснути нікуди» —
   він бачить мертву стрілку і далі не вірить жодній ручці в панелі. */

test("без tunable ручок немає ЗОВСІМ — ні крутилки, ні пікера, ні скидання", () => {
  const payload = P({
    groups: { color: [D({ prop: "color", computed: "rgb(26, 28, 31)",
      raw: null, token: null, verdict: "unlinked" })], box: [D()] },
    tuned: { gap: { from: "8px", to: "12px" } },
  });
  const overlay = reportHTML(payload);
  for (const act of ["insptune", "insptunecolor", "insptuneoff"]) {
    assert.doesNotMatch(overlay, new RegExp(`data-act="${act}"`), act);
  }
  assert.doesNotMatch(overlay, /<input/, "поле вводу без слухача — мертва ручка");
  assert.doesNotMatch(overlay, /insp-tuned/,
    "позначка «накручено» без кнопки скидання — напис «щось змінено, вернути нічим»");
});

test("типове значення tunable — ВИМКНЕНО: забутий прапорець дає текст, не мертву ручку", () => {
  /* Напрямок типового значення несучий. Забути прапорець у документі з
     проводкою = втратити ручки (видно одразу); забути в документі без неї =
     намалювати мертві (видно лише живцем, і то не одразу). */
  assert.equal(reportHTML(P()), reportHTML(P(), { tunable: false }));
  assert.notEqual(reportHTML(P()), panelHTML(P()));
});

test("без tunable значення лишається ЧЕСНИМ ТЕКСТОМ, а вирок і зразок — на місці", () => {
  /* Відмова від ручки не сміє забрати те, заради чого звіт і читають:
     значення, походження і кольорову плитку. */
  const overlay = reportHTML(P({ groups: { color: [D({ prop: "color",
    computed: "rgb(26, 28, 31)", raw: null, token: null, verdict: "unlinked" })] } }));
  assert.match(overlay, /class="insp-txt">rgb\(26, 28, 31\)</,
    "значення мусить лишитись читабельним");
  assert.match(overlay, /insp-sw/,
    "зразок кольору підміняв собою пікер — без пікера він мусить вернутись");
  assert.match(reportHTML(P()), /insp-dot--tok/, "вирок не залежить від ручок");
  assert.match(reportHTML(P()), /title="gap · 8px · --sp-2"/,
    "і походження в титулі теж: воно про значення, а не про ручку");
});

/* ── measureHTML: числа лінійки ────────────────────────────────────────────
   Той самий контракт, що в `reportHTML`: payload на вході, рядок на виході,
   жодного DOM. Payload сюди кладе оверлей із того, що САМ намалював
   напрямними (`_setMeas`, `app/vendor/inspector.js`), тому перевірки нижче
   говорять полями `measure()`/`between()` (`inspector-measure.js`) і нічим
   іншим: вигаданий `kind` тут був би вигаданим і там. */

const M = (o = {}) => ({ mode: "nearest", kind: null,
  rows: [{ key: "top", px: 12, kind: "element" }], ...o });

test("лінійка: без виміру — порожній рядок, а не порожня таблиця", () => {
  assert.equal(measureHTML(null), "");
  assert.equal(measureHTML(undefined), "");
  assert.equal(measureHTML(M({ rows: [] })), "",
    "нічого не виміряно — панель мусить показати підказку, а не пусту рамку");
});

test("лінійка: чотири найближчі — напрямок, число і вид у кожному рядку", () => {
  const h = measureHTML(M({ rows: [
    { key: "top", px: 25, kind: "element" },
    { key: "left", px: 16, kind: "container" },
  ] }));
  assert.match(h, /<dt>Зверху<\/dt><dd>25 px/);
  assert.match(h, /<dt>Ліворуч<\/dt><dd>16 px/);
  assert.match(h, /insp-kind">сусід</, "сусід мусить бути названий");
  assert.match(h, /insp-kind--box">контейнер</, "межа контейнера — окремим видом");
});

test("лінійка: дві механіки мають РІЗНІ заголовки — вони відповідають на різне", () => {
  const near = measureHTML(M());
  const pair = measureHTML(M({ mode: "pair", kind: "gap",
    rows: [{ key: "x", px: 24 }] }));
  const head = (h) => h.match(/<h6>([\s\S]*?)<\/h6>/)[1];
  assert.notEqual(head(near), head(pair));
});

test("лінійка: вид ПАРНОГО виміру стоїть у заголовку, а не в кожному рядку", () => {
  const h = measureHTML(M({ mode: "pair", kind: "inside", rows: [
    { key: "top", px: 9 }, { key: "right", px: 9 },
  ] }));
  assert.equal((h.match(/insp-kind/g) || []).length, 1,
    "`between()` рахує ОДИН вид на весь вимір — повторити його в рядках означало б "
    + "показати, ніби в кожної напрямної свій");
  assert.match(h.match(/<h6>([\s\S]*?)<\/h6>/)[1], /усередині/);
});

test("лінійка: перекриття фарбується інакше за зазор — це єдина вада серед видів", () => {
  const lap = measureHTML(M({ mode: "pair", kind: "overlap",
    rows: [{ key: "x", px: 12 }] }));
  const gap = measureHTML(M({ mode: "pair", kind: "gap",
    rows: [{ key: "x", px: 12 }] }));
  assert.match(lap, /insp-kind--bad/);
  assert.doesNotMatch(gap, /insp-kind--bad/, "звичайний зазор вадою не є");
});

test("лінійка: осі підписані осями — боку в зазорі/діагоналі не існує", () => {
  const h = measureHTML(M({ mode: "pair", kind: "diagonal",
    rows: [{ key: "x", px: 60 }, { key: "y", px: 40 }] }));
  assert.match(h, /<dt>По X<\/dt><dd>60 px/);
  assert.match(h, /<dt>По Y<\/dt><dd>40 px/);
});

test("лінійка: дробові пікселі округлює панель — як і плашка на макеті (Р5)", () => {
  const h = measureHTML(M({ rows: [{ key: "top", px: 15.98, kind: "element" }] }));
  assert.match(h, /<dd>16 px/);
  assert.doesNotMatch(h, /15\.98/,
    "сирі дробові в панелі розійшлися б із числом на напрямній");
});

test("лінійка: невідомий ключ і невідомий вид не валять усю панель", () => {
  const h = measureHTML(M({ rows: [{ key: "хтозна", px: 5, kind: "новий" }] }));
  assert.match(h, /insp-spec/);
  assert.match(h, /5 px/);
});

test("лінійка: секція та сама, що у звіту — один каркас, не два", () => {
  assert.match(measureHTML(M()), /<section class="insp-spec"><h6>/);
});

/* ── Рядок про ДС: токени ПРОСТОРУ (етап 2а, Task 7) ───────────────────────
   Знімок ДС напрямку називає коміт; токени простору коміту не мають — вони
   читаються з файла на льоту, і єдине, що можна сказати про їхнє походження,
   — ЯКИЙ файл. Профіль `space:<id>` у текст не їде: id простору — внутрішній
   ключ, а не те, що дизайнер упізнає. */

test("рядок про ДС простору — файл, а не коміт і не id простору", () => {
  const h = reportHTML(P({ dsInfo: { profile: "space:s1", known: true, source: "tokens.css" } }));
  assert.match(h, /<p class="insp-note">[^<]*tokens\.css[^<]*<\/p>/);
  assert.doesNotMatch(h, /space:s1/);
  assert.doesNotMatch(h, /знімок/, "знімка в токенів простору немає");
});

test("рядок про ДС простору без імені файла — речення без дірки", () => {
  const h = reportHTML(P({ dsInfo: { profile: "space:s1", known: true, source: "" } }));
  const note = h.match(/<p class="insp-note">([^<]+)<\/p>/);
  assert.ok(note, "рядок є");
  assert.doesNotMatch(note[1], /\(\)|«»|undefined|null/);
});

test("імʼя файла з розмітки екранується", () => {
  const h = reportHTML(P({ dsInfo: { profile: "space:s1", known: true, source: '<b>"x"</b>.css' } }));
  assert.doesNotMatch(h, /<b>"x"/);
  assert.match(h, /&lt;b&gt;/);
});

test("рядок про ДС напрямку — як був: коміт знімка", () => {
  const h = reportHTML(P({ dsInfo: { profile: "united", known: true,
    commit: "5f7050d77ab5fe6ce9d0185bff703748202ede9f", figma: "UI" } }));
  assert.match(h, /«united»/);
  assert.match(h, /5f7050d77ab5/);
});

test("рядок про ДС простору — англійською теж", async () => {
  const { setLang } = await import("../app/i18n.js");
  setLang("en");
  try {
    const h = reportHTML(P({ dsInfo: { profile: "space:s1", known: true, source: "tokens.css" } }));
    assert.match(h, /tokens\.css/);
    assert.doesNotMatch(h, /Звірено/);
  } finally {
    setLang("uk");
  }
});
