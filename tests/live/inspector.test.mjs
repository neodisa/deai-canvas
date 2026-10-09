/**
 * Живі тести інспектора: справжній Chromium по справжньому серверу інструмента,
 * сторінка відкрита ПРЯМО (`/commented?...`), без канваса й без iframe — саме так
 * інспектор і живе в макеті (його інжектить локальний снипет `serve.py`).
 *
 * Числа, з якими порівнюється лінійка, перевірка рахує САМА — з
 * `getBoundingClientRect` у самій сторінці й руками (`a.bottom − b.top`), а не
 * викликом `measure` чи внутрішніх функцій інспектора. Інакше вона порівнювала б
 * вивід лінійки із самим собою і була б зелена при будь-якій геометрії.
 *
 * Мапа «перевірка → запобіжник», знята мутаційно (прибери охорону — подивись, чи
 * червоніє). Без неї «зелено» не означає нічого:
 *
 *   A (режим)          — клавіша `M` у `_onKey` і те, що вона НЕ гасить інспектор.
 *   B (сусіди й межа)  — `top`/`bottom` тримає збір кандидатів узагалі; `bottom:70`
 *                        окремо тримає фільтр невидимого (`checkVisibility`): між
 *                        B і C лежить `#veil` з `visibility:hidden` за 40px, і без
 *                        фільтра лінійка показала б 40 замість 70. `left`/`right`
 *                        тримає інсет контейнера на border+padding: без нього
 *                        числа поїхали б на 32px (2 border + 30 padding).
 *   B2 (напрямна)      — геометрія лінії: від краю цілі до краю знайденого і в
 *                        межах смуги перетину. Плашка сама цього не стереже.
 *   C (без сусідів)    — Р2 цілком: елемент, у якого в жодному напрямку нікого,
 *                        мусить показати чотири числа до внутрішнього краю
 *                        контейнера, а не порожнечу.
 *   D (предок)         — виключення ПРЕДКІВ зі списку кандидатів. `#pop` зсунутий
 *                        `top:50px` за межі свого ж батька `#tiny`, тому `contains`
 *                        у чистому модулі його НЕ ловить (батько цілі не містить):
 *                        прибери виключення — і зверху зʼявиться 40 до `#tiny`
 *                        замість 50 до краю контейнера.
 *   E (нащадок)        — виключення НАЩАДКІВ. У `#tiny` дитина стирчить на 40px
 *                        нижче його ж коробки: прибери виключення — знизу буде 40
 *                        до `#pop` замість 550 до краю контейнера.
 *   F (fixed)          — гілка `position:fixed` → вьюпорт у `_containerBox`. На цій
 *                        сторінці body нижче за `#dock` НЕ доходить, тому мутація
 *                        (взяти батька, як для всіх) забирає саме нижню плашку:
 *                        `body.bottom − dock.bottom` відʼємний, а вьюпорт дає 30.
 *                        Тому `min-height:100vh` у body сторінки `holovna` НЕМА
 *                        свідомо — з ним обидві відповіді збіглися б на 30.
 *   G (плашка не ловить — `pointer-events:none` на плашках і напрямних. Точка —
 *      курсор)           центр плашки «25» у зазорі між `#a` і `#b`, тобто над
 *                        `#wrap`. Без охорони подія дістається нашому оверлею,
 *                        `_pageEl` вертає null, ховер лишається на `#b` — і лінійка
 *                        починає міряти те, на що курсор уже не показує.
 *   H (оверлеї в         — те, що обидва хости оверлеїв узагалі не доходять до
 *      переліку)           `measure`. Сама по собі ця перевірка запобіжника НЕ
 *                        стереже (перевірено мутаційно: прибери виключення — H
 *                        лишається зелена), бо в звичайному макеті обидва хости
 *                        нульового розміру — інспекторів 0×0 fixed, comment-layer
 *                        display:inline без вмісту — і їх однаково відсіює фільтр
 *                        порожніх коробок. Тримаємо як опис контракту; ловить
 *                        запобіжник перевірка M.
 *   M (оверлей із        — ВИКЛЮЧЕННЯ ОВЕРЛЕЇВ, по-справжньому. Нульовий розмір
 *      коробкою)           хоста це збіг верстки, а не контракт: у `body{display:grid}`
 *                        хост comment-layer стає елементом сітки й дістає рядок
 *                        на всю ширину. Сторінка `grid` у фікстурі саме така —
 *                        жодного правила про наш оверлей у її CSS немає, коробку
 *                        хосту дає сама верстка. Прибери виключення — і знизу
 *                        `#two` зʼявиться 0 до нашого ж інструмента.
 *   I (display:contents — охорона «порожня або вивернута коробка контейнера» у
 *      батько)           `innerBox`. `#bare` коробки не дає (`getClientRects()`
 *                        порожній, rect 0,0,0,0), а `padding:20px` у computed
 *                        лишається — інсет дав би `right < left`, і чистий модуль
 *                        кинув би «вивернутий», поваливши лінійку ЦІЛКОМ. З
 *                        охороною контейнером стає перший предок із коробкою.
 *   J (пін)            — лінійка на запіненому елементі не їде за курсором, і
 *                        каскадна панель у режимі лінійки не вилазить.
 *   K (режим туди й      — те, що каскадний режим лінійку ХОВАЄ, а не лише
 *      назад)              вмикає. ПЕРЕПИСАНО 17.09.2026 (Task 8): до того
 *                        перевірка тиснула кнопки чипа режимів
 *                        (`[data-mode]`) у хромі оверлея — чип прибрано, бо
 *                        видимий перемикач тепер один і живе в правій панелі
 *                        оболонки. Змінився ПРИСТРІЙ ВВЕДЕННЯ (клавіша `M`
 *                        замість кліку), предмет перевірки — ні: лінійка
 *                        мусить зʼявитись після перемикання і зникнути після
 *                        повернення в каскад. Сюди ж додано те, що чипа
 *                        справді НЕМАЄ: інакше «перевірку прибрали, бо вона
 *                        заважала» не відрізнити від «контракт змінили».
 *                        Клавішу `M` саму по собі стереже A — тут вона
 *                        інструмент, а не предмет.
 *   L (скрол)          — виклик `_ruler` у `_reflow`. Числа після скролу ті самі
 *                        (ціль і сусід їдуть разом), тому перевіряються не вони, а
 *                        те, що напрямна поїхала за елементом: без перемальовки
 *                        вона лишається висіти там, де макет був до скролу.
 *   Далі — розкладка плашок (`_spread`). У неї ТРИ окремі механізми, і мутація
 *   показала, що тримають вони різне; список знятий, а не написаний з голови:
 *
 *   N (дрібний елемент)— «жодні дві плашки не перетинаються» на іконці 20×20 із
 *                        зазорами 9px, тобто рівно той злиплий плюс, з якого
 *                        задача й виросла (26px² на пару). Тримають ДВА механізми
 *                        разом, і кожного окремо досить: прибери виїзд за
 *                        напрямну — розсування дотягне; постав `PILL_PASSES = 0`
 *                        — виїзд дотягне. Червоніє, коли немає обох.
 *   N2 (накриття цілі) — ВИЇЗД за напрямну, і тільки він. Елемент 36×36 із тими
 *                        самими зазорами 9px: плашки одна на одну там уже НЕ
 *                        лізуть (36 > порогу 32), розсуванню нічого чіпати — а
 *                        всі чотири накривали сам елемент по ~5px. Інструмент
 *                        вимірювання не має закривати те, що міряє.
 *   P (нульові зазори) — РОЗСУВАННЯ, і тільки воно. На елементі 10×10, що точно
 *                        заповнює контейнер, виїжджати нікуди: далекий кінець
 *                        напрямної там і є край елемента. `PILL_PASSES = 0` —
 *                        P червоніє (3px² на пару), N/N2/O зелені.
 *   O (край екрана)    — ОБМЕЖЕННЯ вьюпортом, і тільки воно. Зазор 0 до верхньої
 *                        межі: виїзд виносить плашку на y ≈ −13, і числа немає
 *                        взагалі. Прибери обмеження — O червоніє, решта зелена.
 *
 * Одна фікстура на всі перевірки: чотири макети (`holovna` — сусіди, межа, fixed;
 * `poshuk` — самотній елемент, предок/нащадок, display:contents; `grid` — оверлей
 * із коробкою; `tiny` — дрібні елементи й край екрана), кожна перевірка відкриває
 * свою вкладку в ОДНОМУ браузері.
 */
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу: `node --test` крутить файли паралельно, і спільна
   база з canvas.test.mjs (8890) чи shoot.test.mjs (8790) дала б колізію. */
const PORT_BASE = 8990;
const VIEW = { width: 1400, height: 900 };

/* Макет із сусідами. Числа в CSS — навмисно різні й неокруглі одне до одного
   (25, 40, 50, 70), щоб перевірка не могла випадково зійтись на «майже тому
   самому» зазорі. `min-height` у body НЕМА — див. F у шапці. */
const HOLOVNA = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;background:#fff;font:14px/1.4 sans-serif}
#wrap{position:relative;width:600px;margin:40px 0 0 40px;padding:30px;
      border:2px solid #99a;background:#eef}
.card{width:400px;height:60px;margin-left:50px;background:#cde}
#a{margin-bottom:25px}
#b{margin-bottom:40px}
#veil{width:400px;height:20px;margin:0 0 10px 50px;background:#fee;visibility:hidden}
#ghost{position:absolute;left:502px;top:0;width:80px;height:80px;background:#fcc}
#dock{position:fixed;right:20px;bottom:30px;width:120px;height:40px;background:#fdd}
</style></head><body>
<div id="wrap">
  <div class="card" id="a">A</div>
  <div class="card" id="b">B</div>
  <div id="veil">veil</div>
  <div class="card" id="c">C</div>
  <div id="ghost">ghost</div>
</div>
<div id="dock">dock</div>
</body></html>`;

/* Макет без сусідів: `#solo` сам у коробці з падингом, `#tiny`/`#pop` — батько й
   дитина, що вилізли одне з одного, `#nest` — дитина батька без коробки. */
const POSHUK = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:#fff;font:14px/1.4 sans-serif}
#hold{width:400px;height:300px;margin:60px 0 0 80px;padding:50px 60px;
      border:1px solid #ccc;background:#ffe}
#solo{width:120px;height:70px;margin:20px 0 0 35px;background:#fdd}
#tiny{width:60px;height:10px;margin:40px 0 0 40px;background:#ddd}
#pop{position:relative;top:50px;width:80px;height:30px;background:#dfd}
#bare{display:contents;padding:20px}
#nest{width:90px;height:30px;margin:120px 0 0 300px;background:#cfc}
</style></head><body>
<div id="hold"><div id="solo">solo</div></div>
<div id="tiny"><div id="pop">pop</div></div>
<div id="bare"><div id="nest">nest</div></div>
</body></html>`;

/* Макет, у якому хост оверлея дістає КОРОБКУ від самої верстки: `display:inline`
   у гріді блокифікується, `grid-auto-rows` дає рядок, `justify-items` за
   замовчуванням (stretch) — ширину колонки. Правил про оверлей тут немає. */
const GRID = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;display:grid;grid-auto-rows:60px;background:#fff;font:14px/1.4 sans-serif}
#one{background:#cde}
#two{background:#dfd}
</style></head><body>
<div id="one">one</div>
<div id="two">two</div>
</body></html>`;

/* Дрібні елементи — те, що дизайнер міряє найчастіше (іконки, чипи, бейджі,
   кнопки). Обидві коробки тут із зазорами по 9px до внутрішнього краю
   контейнера, і РОЗМІР узятий не з голови:
     `#dot` 20×20 у кнопці 38×38 — рівно те, що в демо (іконка `.ic--chevron`
        у круглій кнопці каруселі), і рівно той розмір, на якому чотири плашки
        ПЕРЕТИНАЮТЬСЯ: плашка-контейнер 18.8×20.5, а кутові плашки налізають
        одна на одну, поки елемент вужчий за 2·18.8 − 9 = 28.6 і нижчий за
        2·20.5 − 9 = 32;
     `#chip` 36×36 у коробці 54×54 — розмір з опису задачі. Він уже ЗА порогом
        перетину (36 > 32), тож там плашки одна на одну не лізуть — але всі
        чотири накривають сам елемент, який міряють.
   Тому перевірок дві: N про перетин, N2 про накриття цілі.

   `#fill` — дрібний елемент, що ТОЧНО заповнює свій контейнер: чотири зазори по
   нулю, тобто виїжджати за напрямну нікуди (далекий кінець напрямної збігається
   з краєм елемента). Саме тут потрібне розсування плашок, які перетнулись і
   після виїзду. Розмір 10×10 не круглий і не випадковий: при нульовому зазорі
   кутові плашки налізають, лише поки елемент вужчий за 18.8 − 2·3 = 12.8 і
   нижчий за 20.5 − 2·3 = 14.5 (плашка мінус двічі просвіт). На 14×14 виїзду вже
   вистачає, і перевірка була б зелена завжди.

   `#edge` — той самий тісний зазор, але притиснутий до КРАЮ ЕКРАНА: виїжджати
   плашці нікуди, і без обмеження вьюпортом вона поїхала б за верхню межу. */
const TINY = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;background:#fff;font:14px/1.4 sans-serif}
.hold{position:absolute;border:0;padding:0;background:#eef;
      display:flex;align-items:center;justify-content:center}
#btn{left:400px;top:300px;width:38px;height:38px;border-radius:50%}
#dot{width:20px;height:20px;border-radius:50%;background:#cde}
#box{left:700px;top:300px;width:54px;height:54px}
#chip{width:36px;height:36px;background:#cde}
#snug{left:400px;top:500px;width:10px;height:10px}
#fill{width:10px;height:10px;background:#cde}
#edge{position:fixed;left:40px;top:0;width:200px;height:30px;background:#fdd}
/* Пара, що НАКЛАДАЄТСЯ: для парного виміру перекриття мусить читатись як
   перекриття, а не як зазор — інакше «12» прочитають як відступ. */
#lap1{position:absolute;left:900px;top:300px;width:100px;height:60px;background:#cde}
#lap2{position:absolute;left:940px;top:330px;width:100px;height:60px;background:#fed}
</style></head><body>
<div id="lap1">lap1</div><div id="lap2">lap2</div>
<button id="btn" class="hold"><span id="dot"></span></button>
<div id="box" class="hold"><span id="chip"></span></div>
<div id="snug" class="hold"><span id="fill"></span></div>
<div id="edge">edge</div>
</body></html>`;

const PAGE = (id) => (id === "holovna" ? HOLOVNA : POSHUK);

/** Дописати в фікстуру сторінки понад ті дві, що робить `taskFixture`. */
function addPages(it1) {
  const extra = [["grid", GRID, "Грід"], ["tiny", TINY, "Дрібні"]];
  for (const [id, html] of extra) {
    mkdirSync(path.join(it1, id), { recursive: true });
    writeFileSync(path.join(it1, id, "index.html"), html);
  }
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: "Головна", published: true },
            { id: "poshuk", name: "Пошук", published: true },
            ...extra.map(([id, , name]) => ({ id, name, published: true }))],
  }));
}

/** Що показує лінійка: по одній плашці на напрямок, із числом і видом краю. */
const readRuler = (page) => page.evaluate(() => {
  const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
  const out = {};
  for (const n of sh.querySelectorAll("[data-ruler-label]")) {
    if (!n.offsetParent && getComputedStyle(n).display === "none") continue;
    const r = n.getBoundingClientRect();
    if (!r.width) continue;
    out[n.getAttribute("data-ruler-label")] = {
      px: n.textContent.trim(),
      kind: n.getAttribute("data-kind"),
      mid: [r.left + r.width / 2, r.top + r.height / 2],
    };
  }
  return out;
});

/** Прямокутники напрямних (щоб перевірити, що лінія веде від краю до краю). */
const readGuides = (page) => page.evaluate(() => {
  const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
  const out = {};
  for (const n of sh.querySelectorAll("[data-ruler-line]")) {
    const r = n.getBoundingClientRect();
    if (!r.width && !r.height) continue;
    out[n.getAttribute("data-ruler-line")] = [r.left, r.top, r.right, r.bottom];
  }
  return out;
});

/** Плашки як ПРЯМОКУТНИКИ: площі перетинів між собою, з ціллю і виїзд за екран.
 *
 *  Площі рахуються в самій сторінці з `getBoundingClientRect`, а не «на око»:
 *  перетин на кутах у якісь 26px² виглядає як злиплий плюс, у якому не
 *  прочитати жодного з чотирьох чисел. */
const readPills = (page, target) => page.evaluate((sel) => {
  const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
  const pills = [];
  for (const n of sh.querySelectorAll("[data-ruler-label]")) {
    if (getComputedStyle(n).display === "none") continue;
    const r = n.getBoundingClientRect();
    if (!r.width) continue;
    pills.push({ dir: n.getAttribute("data-ruler-label"), px: n.textContent.trim(), r });
  }
  const over = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
    * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const pairs = [];
  for (let i = 0; i < pills.length; i += 1) {
    for (let j = i + 1; j < pills.length; j += 1) {
      const s = over(pills[i].r, pills[j].r);
      if (s > 0) pairs.push(`${pills[i].dir}×${pills[j].dir} ${Math.round(s)}px²`);
    }
  }
  const t = document.querySelector(sel).getBoundingClientRect();
  const root = document.documentElement;
  return {
    nums: Object.fromEntries(pills.map((p) => [p.dir, p.px])),
    pairs,
    onTarget: pills.filter((p) => over(p.r, t) > 0).map((p) => p.dir),
    offScreen: pills.filter((p) => p.r.left < 0 || p.r.top < 0
      || p.r.right > root.clientWidth || p.r.bottom > root.clientHeight).map((p) => p.dir),
    size: [Math.round(t.width), Math.round(t.height)],
  };
}, target);

/** Порівняти плашки з числами, порахованими в сторінці. */
function sameRuler(got, want, note) {
  const flat = (o) => Object.fromEntries(Object.entries(o)
    .map(([k, v]) => [k, `${v.px}/${v.kind}`]));
  assert.deepEqual(flat(got), want, note);
}

test("інспектор: режим лінійки", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  addPages(it1);
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());

  /** Макет із інспектором, готовим до роботи. */
  async function layout(pageId) {
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/commented?it=it1&page=${pageId}&ch=local`);
    await page.waitForFunction(() => !!(window.CanvasInspector && window.CanvasInspector._host));
    return page;
  }

  /** Увімкнути інспектор і режим лінійки СПРАВЖНІМИ клавішами. */
  async function ruler(pageId) {
    const page = await layout(pageId);
    await page.keyboard.press("i");
    await page.keyboard.press("m");
    return page;
  }

  /** Навести курсор у центр елемента. */
  async function hover(page, sel) {
    const box = await page.locator(sel).boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  }

  await t.test("A. клавіша M вмикає лінійку й не гасить інспектор", async () => {
    const page = await layout("holovna");
    await page.keyboard.press("i");
    assert.deepEqual(await page.evaluate(() => [CanvasInspector.on, CanvasInspector.mode]),
      [true, "cascade"], "інспектор мусить починати в каскадному режимі");
    await page.keyboard.press("m");
    assert.deepEqual(await page.evaluate(() => [CanvasInspector.on, CanvasInspector.mode]),
      [true, "ruler"], "M перемикає режим, а не гасить інспектор");
    await page.keyboard.press("m");
    assert.deepEqual(await page.evaluate(() => [CanvasInspector.on, CanvasInspector.mode]),
      [true, "cascade"], "повторна M вертає каскад");
    await page.keyboard.press("m");
    await page.keyboard.press("Escape");
    assert.deepEqual(await page.evaluate(() => [CanvasInspector.on, CanvasInspector.mode]),
      [true, "cascade"], "Escape вертає каскад, а не гасить інспектор");
  });

  await t.test("B. сусіди зверху й знизу, край контейнера збоку", async () => {
    const page = await ruler("holovna");
    await hover(page, "#b");

    /* Числа руками, у самій сторінці: край до краю для сусідів і border+padding
       для внутрішнього краю контейнера. */
    const want = await page.evaluate(() => {
      const q = (s) => document.querySelector(s).getBoundingClientRect();
      const b = q("#b");
      const w = document.querySelector("#wrap");
      const wr = w.getBoundingClientRect();
      const cs = getComputedStyle(w);
      const n = (v) => parseFloat(v);
      return {
        top: `${Math.round(b.top - q("#a").bottom)}/element`,
        bottom: `${Math.round(q("#c").top - b.bottom)}/element`,
        left: `${Math.round(b.left - (wr.left + n(cs.borderLeftWidth) + n(cs.paddingLeft)))}/container`,
        right: `${Math.round((wr.right - n(cs.borderRightWidth) - n(cs.paddingRight)) - b.right)}/container`,
      };
    });
    assert.deepEqual(want,
      { top: "25/element", bottom: "70/element", left: "50/container", right: "86/container" },
      "сама фікстура: якщо ці числа поїхали, поїхала верстка сторінки, не лінійка");
    sameRuler(await readRuler(page), want, "лінійка на #b");
  });

  await t.test("B2. напрямна веде від краю цілі до краю знайденого", async () => {
    const page = await ruler("holovna");
    await hover(page, "#b");
    const g = (await readGuides(page)).top;
    const want = await page.evaluate(() => {
      const q = (s) => document.querySelector(s).getBoundingClientRect();
      const a = q("#a"); const b = q("#b");
      return { from: a.bottom, to: b.top, l: Math.max(a.left, b.left), r: Math.min(a.right, b.right) };
    });
    assert.ok(g, "напрямної вгору немає взагалі");
    assert.ok(Math.abs(g[1] - want.from) <= 1 && Math.abs(g[3] - want.to) <= 1,
      `напрямна мусить іти від ${want.from} до ${want.to}, а йде ${g[1]}..${g[3]}`);
    assert.ok(g[0] >= want.l && g[2] <= want.r,
      `напрямна мусить лежати в смузі перетину ${want.l}..${want.r}, а лежить ${g[0]}..${g[2]}`);
  });

  await t.test("C. елемент без сусідів — чотири числа до краю контейнера", async () => {
    const page = await ruler("poshuk");
    await hover(page, "#solo");
    const want = await page.evaluate(() => {
      const s = document.querySelector("#solo").getBoundingClientRect();
      const h = document.querySelector("#hold");
      const hr = h.getBoundingClientRect();
      const cs = getComputedStyle(h);
      const n = (v) => parseFloat(v);
      const box = {
        top: hr.top + n(cs.borderTopWidth) + n(cs.paddingTop),
        right: hr.right - n(cs.borderRightWidth) - n(cs.paddingRight),
        bottom: hr.bottom - n(cs.borderBottomWidth) - n(cs.paddingBottom),
        left: hr.left + n(cs.borderLeftWidth) + n(cs.paddingLeft),
      };
      return {
        top: `${Math.round(s.top - box.top)}/container`,
        right: `${Math.round(box.right - s.right)}/container`,
        bottom: `${Math.round(box.bottom - s.bottom)}/container`,
        left: `${Math.round(s.left - box.left)}/container`,
      };
    });
    assert.deepEqual(want, { top: "20/container", right: "123/container",
      bottom: "108/container", left: "35/container" }, "сама фікстура");
    sameRuler(await readRuler(page), want, "лінійка на самотньому #solo");
  });

  await t.test("D. предок, що цілі не містить, сусідом не стає", async () => {
    const page = await ruler("poshuk");
    await hover(page, "#pop");
    const got = await readRuler(page);
    const want = await page.evaluate(() => {
      const p = document.querySelector("#pop").getBoundingClientRect();
      const t = document.querySelector("#tiny").getBoundingClientRect();
      return { container: Math.round(p.top - t.top), ancestor: Math.round(p.top - t.bottom) };
    });
    assert.deepEqual([want.container, want.ancestor], [50, 40], "сама фікстура");
    assert.deepEqual(got.top, { px: "50", kind: "container", mid: got.top && got.top.mid },
      `зверху мусить бути ${want.container} до краю контейнера, а не ${want.ancestor} до батька`);
  });

  await t.test("E. нащадок, що стирчить за межі цілі, сусідом не стає", async () => {
    const page = await ruler("poshuk");
    await hover(page, "#tiny");
    const got = await readRuler(page);
    const want = await page.evaluate(() => {
      const t = document.querySelector("#tiny").getBoundingClientRect();
      const p = document.querySelector("#pop").getBoundingClientRect();
      const b = document.body;
      const br = b.getBoundingClientRect();
      const cs = getComputedStyle(b);
      const inner = br.bottom - parseFloat(cs.borderBottomWidth) - parseFloat(cs.paddingBottom);
      return { container: Math.round(inner - t.bottom), child: Math.round(p.top - t.bottom) };
    });
    assert.deepEqual([want.container, want.child], [550, 40], "сама фікстура");
    assert.equal(got.bottom && `${got.bottom.px}/${got.bottom.kind}`, `${want.container}/container`,
      `знизу мусить бути ${want.container} до краю контейнера, а не ${want.child} до власної дитини`);
  });

  await t.test("F. position:fixed — контейнер це вьюпорт", async () => {
    const page = await ruler("holovna");
    await hover(page, "#dock");
    const want = await page.evaluate(() => {
      const d = document.querySelector("#dock").getBoundingClientRect();
      return {
        top: `${Math.round(d.top)}/container`,
        right: `${Math.round(window.innerWidth - d.right)}/container`,
        bottom: `${Math.round(window.innerHeight - d.bottom)}/container`,
        left: `${Math.round(d.left)}/container`,
      };
    });
    assert.deepEqual(want, { top: "830/container", right: "20/container",
      bottom: "30/container", left: "1260/container" }, "сама фікстура");
    sameRuler(await readRuler(page), want, "лінійка на fixed #dock");
  });

  await t.test("G. плашка з числом не ловить курсор", async () => {
    const page = await ruler("holovna");
    await hover(page, "#b");
    const [x, y] = (await readRuler(page)).top.mid;
    assert.equal(await page.evaluate(([px, py]) => {
      const el = document.elementFromPoint(px, py);
      return el && el.id;
    }, [x, y]), "wrap", "центр плашки мусить лежати в зазорі, тобто над #wrap");
    await page.mouse.move(x, y);
    assert.equal(await page.evaluate(() => CanvasInspector.hover && CanvasInspector.hover.id),
      "wrap", "ховер мусить перейти на елемент ПІД плашкою, а не застрягти на #b");
  });

  await t.test("H. оверлеї не потрапляють у перелік кандидатів", async () => {
    const page = await ruler("holovna");
    await hover(page, "#b");
    const got = await page.evaluate(() => {
      const { nodes } = CanvasInspector._candidates(document.querySelector("#b"));
      const sel = "[data-canvas-inspector],[data-comment-layer]";
      return {
        n: nodes.length,
        overlays: nodes.filter((x) => x.closest(sel)).map((x) => x.tagName),
        self: nodes.some((x) => x.id === "b"),
        hasGhost: nodes.some((x) => x.id === "ghost"),
        inDoc: document.querySelectorAll(
          "[data-canvas-inspector],[data-comment-layer]").length,
      };
    });
    assert.ok(got.inDoc >= 1, "оверлей мусить бути в документі, інакше перевірка ні про що");
    assert.deepEqual(got.overlays, [], "у переліку кандидатів не місце оверлеям");
    assert.equal(got.self, false, "сама ціль кандидатом не буває");
    assert.ok(got.hasGhost, "звичайний елемент сторінки в переліку мусить бути");
  });

  await t.test("I. батько без коробки (display:contents) не валить лінійку", async () => {
    const page = await ruler("poshuk");
    const errs = [];
    page.on("pageerror", (e) => errs.push(String(e)));
    await hover(page, "#nest");
    const want = await page.evaluate(() => {
      const n = document.querySelector("#nest").getBoundingClientRect();
      const h = document.querySelector("#hold").getBoundingClientRect();
      const br = document.body.getBoundingClientRect();
      return {
        top: `${Math.round(n.top - h.bottom)}/element`,
        right: `${Math.round(br.right - n.right)}/container`,
        bottom: `${Math.round(br.bottom - n.bottom)}/container`,
        left: `${Math.round(n.left - br.left)}/container`,
      };
    });
    assert.deepEqual(want, { top: "170/element", right: "1010/container",
      bottom: "400/container", left: "300/container" }, "сама фікстура");
    sameRuler(await readRuler(page), want, "лінійка на #nest");
    assert.deepEqual(errs, [], "лінійка не має падати на батькові без коробки");
  });

  await t.test("J. якір не злітає, коли дивишся на інші елементи", async () => {
    /* ПЕРЕПИСАНО 25.08.2026. Було: «піну лінійка не має їхати за курсором» —
       перевірка стерегла рівно те, що дизайнер попросив змінити (клік мусить
       робити елемент ЯКОРЕМ, а не заморожувати вимір). Числа тепер стереже Q;
       тут лишилось те, що досі важливо: якір не перескакує на те, куди дивишся,
       і каскадна панель у цьому режимі не вилазить. */
    const page = await ruler("holovna");
    await hover(page, "#b");
    const box = await page.locator("#b").boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await hover(page, "#c");
    assert.equal(await page.evaluate(() => CanvasInspector.pinned && CanvasInspector.pinned.id),
      "b", "якір мусить лишитись на тому, що вибрали кліком");
    assert.equal(await page.evaluate(() => {
      const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
      return sh.querySelector(".panel").classList.contains("hidden");
    }), true, "каскадна панель у режимі лінійки не потрібна");
  });

  await t.test("K. режим туди й назад: лінійка зʼявляється і зникає", async () => {
    const page = await layout("holovna");
    await page.keyboard.press("i");

    /* Чипа режимів в оверлеї більше немає (Task 8) — видимий перемикач один, і
       він у правій панелі оболонки. Стверджуємо це ПРЯМО: без такого рядка
       зникнення кнопок читалося б як мовчазне послаблення перевірки. */
    assert.equal(await page.evaluate(() => {
      const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
      return sh.querySelectorAll("[data-mode]").length;
    }), 0, "чип режимів в оверлеї не мусить існувати — перемикач живе в панелі");

    await page.keyboard.press("m");
    assert.deepEqual(await page.evaluate(() => [CanvasInspector.on, CanvasInspector.mode]),
      [true, "ruler"], "перемикання режиму не мусить гасити інспектор");
    await hover(page, "#b");
    assert.equal((await readRuler(page)).top.px, "25",
      "після перемикання лінійка мусить малювати");
    await page.keyboard.press("m");
    assert.equal(await page.evaluate(() => CanvasInspector.mode), "cascade");
    await hover(page, "#a");
    assert.deepEqual(await readRuler(page), {},
      "у каскадному режимі напрямних і плашок бути не має");
  });

  await t.test("L. скрол перемальовує лінійку", async () => {
    const page = await ruler("poshuk");
    await hover(page, "#solo");
    const before = (await readGuides(page)).top;
    await page.evaluate(() => {
      document.body.style.paddingBottom = "1500px";
      window.scrollTo(0, 300);
    });
    await page.waitForFunction(() => window.scrollY === 300);
    await page.waitForTimeout(100);   // один кадр `_schedule`
    const after = (await readGuides(page)).top;
    const want = await page.evaluate(() => {
      const s = document.querySelector("#solo").getBoundingClientRect();
      const h = document.querySelector("#hold");
      const hr = h.getBoundingClientRect();
      const cs = getComputedStyle(h);
      return { from: hr.top + parseFloat(cs.borderTopWidth) + parseFloat(cs.paddingTop),
               to: s.top };
    });
    assert.ok(Math.abs(before[1] - after[1] - 300) <= 1,
      `після скролу на 300 напрямна мусить поїхати з ${before[1]} на ${before[1] - 300}, а стоїть на ${after[1]}`);
    assert.ok(Math.abs(after[1] - want.from) <= 1 && Math.abs(after[3] - want.to) <= 1,
      `напрямна після скролу мусить іти від ${want.from} до ${want.to}, а йде ${after[1]}..${after[3]}`);
  });

  await t.test("M. оверлей із коробкою сусідом не стає", async () => {
    const page = await ruler("grid");
    const host = await page.evaluate(() => {
      const h = document.querySelector("[data-comment-layer]");
      const r = h && h.getBoundingClientRect();
      return r ? [Math.round(r.width), Math.round(r.height)] : null;
    });
    assert.ok(host && host[0] > 0 && host[1] > 0,
      `без коробки в хоста ця перевірка ні про що, а коробка ${JSON.stringify(host)}`);
    await hover(page, "#two");
    const want = await page.evaluate(() => {
      const t = document.querySelector("#two").getBoundingClientRect();
      const br = document.body.getBoundingClientRect();
      const h = document.querySelector("[data-comment-layer]").getBoundingClientRect();
      return { container: Math.round(br.bottom - t.bottom), overlay: Math.round(h.top - t.bottom) };
    });
    assert.deepEqual([want.container, want.overlay], [60, 0], "сама фікстура");
    const got = await readRuler(page);
    assert.equal(got.bottom && `${got.bottom.px}/${got.bottom.kind}`, `${want.container}/container`,
      "знизу мусить бути край контейнера, а не наш власний оверлей");
  });

  await t.test("N. чотири плашки на дрібному елементі не злипаються", async () => {
    const page = await ruler("tiny");
    await hover(page, "#dot");
    const got = await readPills(page, "#dot");
    assert.deepEqual(got.size, [20, 20], "сама фікстура: іконка мусить бути 20×20");
    assert.deepEqual(got.nums, { top: "9", right: "9", bottom: "9", left: "9" },
      "усі чотири числа мусять лишитись на місці: «не влізло, тому не показуємо» "
      + "це брехня про те, що відстані немає");
    assert.deepEqual(got.pairs, [],
      `плашки налізли одна на одну, числа не прочитати: ${got.pairs.join(", ")}`);
  });

  await t.test("N2. плашка не накриває елемент, який міряють", async () => {
    const page = await ruler("tiny");
    await hover(page, "#chip");
    const got = await readPills(page, "#chip");
    assert.deepEqual(got.size, [36, 36], "сама фікстура: чип мусить бути 36×36");
    assert.deepEqual(got.nums, { top: "9", right: "9", bottom: "9", left: "9" },
      "усі чотири числа мусять лишитись на місці");
    assert.deepEqual(got.pairs, [],
      `плашки налізли одна на одну: ${got.pairs.join(", ")}`);
    assert.deepEqual(got.onTarget, [],
      `плашка накриває той самий елемент, який міряють: ${got.onTarget.join(", ")}`);
  });

  await t.test("P. нульові зазори з усіх боків — плашки все одно розходяться", async () => {
    const page = await ruler("tiny");
    await hover(page, "#fill");
    const got = await readPills(page, "#fill");
    assert.deepEqual(got.size, [10, 10], "сама фікстура: елемент мусить бути 10×10");
    assert.deepEqual(got.nums, { top: "0", right: "0", bottom: "0", left: "0" },
      "сама фікстура: елемент мусить точно заповнювати контейнер, усі зазори нульові");
    assert.deepEqual(got.pairs, [],
      `виїжджати нікуди, а плашки мусять розійтись: ${got.pairs.join(", ")}`);
    assert.deepEqual(got.offScreen, [], `плашка поїхала за екран: ${got.offScreen.join(", ")}`);
  });

  await t.test("O. тісний зазор біля краю екрана — число лишається на екрані", async () => {
    const page = await ruler("tiny");
    await hover(page, "#edge");
    const want = await page.evaluate(() => {
      const e = document.querySelector("#edge").getBoundingClientRect();
      const root = document.documentElement;
      return {
        top: `${Math.round(e.top)}`, left: `${Math.round(e.left)}`,
        right: `${Math.round(root.clientWidth - e.right)}`,
        bottom: `${Math.round(root.clientHeight - e.bottom)}`,
      };
    });
    assert.deepEqual(want, { top: "0", left: "40", right: "1160", bottom: "870" },
      "сама фікстура");
    const got = await readPills(page, "#edge");
    assert.deepEqual(got.nums, want, "усі чотири числа до краю вьюпорта");
    assert.deepEqual(got.offScreen, [],
      `плашка поїхала за межі екрана, тобто числа просто немає: ${got.offScreen.join(", ")}`);
    assert.deepEqual(got.pairs, [],
      `плашки налізли одна на одну: ${got.pairs.join(", ")}`);
  });

  await t.test("Q. якір + ховер = відстань МІЖ ними", async () => {
    const page = await ruler("holovna");
    const box = await page.locator("#b").boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await hover(page, "#c");

    /* Число рахуємо САМІ, з коробок сторінки, а не з виводу лінійки. */
    const want = await page.evaluate(() => {
      const b = document.getElementById("b").getBoundingClientRect();
      const c = document.getElementById("c").getBoundingClientRect();
      return Math.round(c.top - b.bottom);
    });
    assert.equal(want, 70, "фікстура: 40 margin + 20 veil + 10 = 70");
    const got = await readRuler(page);
    const keys = Object.keys(got);
    assert.equal(keys.length, 1, `у зазорі одна напрямна, а не ${keys.length}: ${keys}`);
    assert.equal(got[keys[0]].px, String(want), "число мусить бути відстанню між якорем і ціллю");
    assert.equal(got[keys[0]].kind, "gap");

    /* Escape знімає ЯКІР (драбинка), і його рамка мусить зникнути разом із ним:
       рамка «це якір» без якоря — брехня на екрані. Без цього твердження мутація
       «не ховати рамку в режимі чотирьох» лишала всі перевірки зеленими. */
    await page.keyboard.press("Escape");
    await hover(page, "#c");
    assert.equal(await page.evaluate(() => CanvasInspector.pinned), null, "Escape мусить зняти якір");
    assert.equal(await page.evaluate(() => {
      const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
      return sh.querySelector(".anch").classList.contains("hidden");
    }), true, "рамка якоря мусить зникнути разом із якорем");
    assert.equal(Object.keys(await readRuler(page)).length, 4,
      "без якоря вертаємось до чотирьох найближчих");
  });

  await t.test("R. іконка ВСЕРЕДИНІ кнопки — чотири внутрішні відстані", async () => {
    /* Головний випадок фічі: дизайнер вибирає кнопку й наводить на іконку в ній.
       «Нуль» тут був би неправдою — це чотири відступи до внутрішніх країв. */
    const page = await ruler("tiny");
    const box = await page.locator("#btn").boundingBox();
    /* Кнопка КРУГЛА (`border-radius:50%`), а `border-radius` обрізає попадання:
       клік у кут її коробки провалюється до `body`, і якорем ставав він (перший
       прогін цього тесту саме так і впав — один зазор по Y до нульового `body`,
       бо на цій сторінці всі елементи поза потоком). Тому цілимось у центр по
       горизонталі й на 4px від верху: це в колі, але не на іконці 20×20, яка
       займає 9..29. */
    await page.mouse.move(box.x + box.width / 2, box.y + 4);
    await page.mouse.click(box.x + box.width / 2, box.y + 4);
    await hover(page, "#dot");
    const got = await readRuler(page);
    assert.deepEqual(Object.keys(got).sort(), ["bottom", "left", "right", "top"]);
    for (const [side, v] of Object.entries(got)) {
      assert.equal(v.px, "9", `${side}: іконка 20×20 у кнопці 38×38 = по 9 з боків`);
      assert.equal(v.kind, "inside");
    }
  });

  await t.test("S. перекриття читається як перекриття, а не як зазор", async () => {
    /* «12», подане зазором, дизайнер прочитає як відступ. Вид мусить бути видно. */
    const page = await ruler("tiny");
    const box = await page.locator("#lap1").boundingBox();
    await page.mouse.move(box.x + 4, box.y + 4);
    await page.mouse.click(box.x + 4, box.y + 4);
    await hover(page, "#lap2");
    const got = await readRuler(page);
    const kinds = [...new Set(Object.values(got).map((v) => v.kind))];
    assert.deepEqual(kinds, ["overlap"], `вид мусить бути overlap, а не ${kinds}`);
    assert.deepEqual(Object.values(got).map((v) => v.px).sort(),
      ["30", "60"], "перекриття 60 по X і 30 по Y");

    /* Атрибута мало: він у розмітці, а дизайнер дивиться на ЕКРАН. Без цього
       твердження мутація «малювати перекриття як зазор» лишала всі 22 перевірки
       зеленими — четвертий за цю фічу охоронець, який не міг упасти. */
    const look = await page.evaluate(() => {
      const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
      const lab = [...sh.querySelectorAll("[data-ruler-label]")]
        .find((n) => n.getBoundingClientRect().width);
      const line = [...sh.querySelectorAll("[data-ruler-line]")]
        .find((n) => !n.classList.contains("hidden"));
      return { lab: lab.className, line: line.className,
               colour: getComputedStyle(lab).backgroundColor };
    });
    assert.ok(/\blap\b/.test(look.lab), `плашка перекриття мусить виглядати інакше: ${look.lab}`);
    assert.ok(/\blap\b/.test(look.line), `лінія перекриття мусить виглядати інакше: ${look.line}`);
    assert.notEqual(look.colour, "rgb(42, 28, 5)", "колір не мусить бути таким, як у зазору до контейнера");
  });
});
