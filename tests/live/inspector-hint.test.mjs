/**
 * Живий тест ПІДКАЗКИ інспектора: «хардкод → токен» не сміє радити токен ЧУЖОЇ
 * категорії.
 *
 * ⛔ Чому ЖИВИЙ, а не юніт. Баг 17.09.2026 знайшли очима на макеті `bf360`
 * (`h1.hero__title`, рядок `font-weight: 700`, підказка «--fw-bold,
 * --z-tooltip») — при 907 зелених перевірках. Категорію токена ми виводимо з
 * ФАКТИЧНОГО вжитку в документі, а вжиток читається з живого CSSOM: які
 * властивості браузер перелічує в блоці, що він віддає для шортката з `var()`
 * (pending-substitution), як розкладає `background:` по лонгхендах. Усе це —
 * поведінка Chrome, а не наша арифметика; підробка CSSOM у node перевіряла б
 * НАШІ уявлення про браузер, а саме вони й були помилкові.
 *
 * Чистий відбір (`hintFor`, `propFamilies`) стереже `tests/inspector-core.test.mjs`
 * — там ціна перевірки мілісекунди. Тут ТІЛЬКИ те, чого юніт не бачить:
 * проводка `collectRules → buildTokenUsage → describe().hint`.
 *
 * Мапа «перевірка → запобіжник → що буде, якщо запобіжник прибрати»
 * (знята мутаційно, не написана з голови):
 *
 *   A (чужа категорія) — звірка родин у `hintFor`. Прибери її — у підказці про
 *                        `font-weight: 700` знову зʼявиться `--z-tooltip`
 *                        (значення в обох токенів `700`, тобто зворотний індекс
 *                        схлопує їх в один ключ — це доводить сам асерт про
 *                        «--fw-bold лишився»).
 *   B (не перефільтру- — та сама перевірка з іншого боку: законний токен ТІЄЇ
 *      вали)             САМОЇ родини мусить лишитись. Зроби фільтр надто
 *                        суворим (напр. звіряй голу властивість, а не родину) —
 *                        `--sp-a`, ужитий у `padding`, зникне з підказки для
 *                        `padding-top`, і фільтр із корисного стане шкідливим.
 *   C (порядок і відсів — `limit` усередині `hintFor` і те, що доведені стоять
 *      ПЕРЕД обрізанням)   попереду здогадних. Токени чужої родини
 *      обрізанням)        оголошені в `:root` ПЕРШИМИ навмисно: обріж до трьох
 *                        раніше, ніж відсієш, — і всі три місця зʼїдять
 *                        `--fs-16`, `--r-16`, а дизайнер побачить порожньо там,
 *                        де є три правильні токени.
 *   D (нуль недоторка-  — гілка `normalizeValue(computed) === '0px'` у
 *      ний)               `describe()`. Task 10.5 її НЕ чіпав, і перевірка тут
 *                        саме для того, щоб «не чіпав» лишалось правдою: нуль
 *                        мусить лишатись `unlinked`, а не стати `hardcode` з
 *                        підказкою.
 *   F (форма значення) — таблиця форм у `hintFor`. Єдина перевірка, яку на цій
 *                        сторінці більше ніщо не дублює: кандидат на `display`
 *                        не вжитий ніде і ім'ям нічого не заявляє. Прибери
 *                        звірку форми — і ключове слово `block` потягне за
 *                        собою токен, який просто має такий самий текст.
 *   E (здогад за       — рівень 'shape': невживаний токен, чия ФОРМА значення
 *      формою)            годиться властивості, пропонується — але позначений.
 *                        Прибери гілку здогадів — зникне колірна підказка;
 *                        прибери перевірку форми — той самий рядок почне
 *                        приймати будь-що, і перевірка A впаде першою.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу: `node --test` крутить файли ПАРАЛЕЛЬНО, а
   `startServer` бере `portBase + hrtime % 100`, тобто кожен сервер займає смугу
   в сто портів. Найвище зайняте — `WIRE_PORT_BASE` в `inspector-panel` (10390,
   зсуви до +10, тобто до 10499). 10590 лишає між нами й ним цілий вільний
   проміжок. */
const PORT_BASE = 10590;
const VIEW = { width: 1400, height: 900 };

/**
 * Сторінка з РЕАЛЬНОЮ колізією значень, знятою з `bf360`: `--fw-bold: 700`
 * (вага шрифту) і `--z-tooltip: 700` (рівень накладання).
 *
 * Пара `--fw-bold`/`--z-tooltip` тут НІДЕ не вжита — рівно як у bf360, і це
 * головне в сторінці: обидва токени безрозмірні `700`, тобто ні вжиток, ні
 * форма значення їх не розрізняють. Друга пара, `--fw-heavy`/`--z-top` (обидві
 * `800`), навпаки, вжита — щоб та сама безрозмірна колізія перевірилась і на
 * шляху, де категорію доводить ФАКТ.
 *
 * Правила `.uses-*` навмисно не висять на жодному елементі: категорію ми
 * читаємо з ПРАВИЛ документа, а не з застосованих стилів — так вжиток видно
 * навіть там, куди цей клас сьогодні не потрапив. Якщо колись почнемо читати
 * лише застосоване, ця сторінка почервоніє першою, і це правильно.
 *
 * Порядок у `:root` теж навмисний: чужі родини (`--fs-16`, `--r-16`) оголошені
 * ПЕРЕД відступами, бо зворотний індекс тримає кандидатів у порядку оголошення
 * — тобто при «обрізати, потім відсіяти» вони зʼїли б усі три місця (охорона C).
 *
 * Градієнт у `body` — з тієї ж причини, що в сусідніх живих тестах: порожній
 * знімок стискається нижче `BYTES_FLOOR`, числився б застарілим, і вхід у макет
 * замовив би справжню зʼємку.
 */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
:root{
  --fs-16: 16px; --r-16: 16px; --sp-guess: 16px;
  --sp-a: 16px; --sp-b: 16px; --sp-c: 16px; --sp-d: 16px;
  --fw-bold: 700; --z-tooltip: 700;
  --fw-heavy: 800; --z-top: 800;
  --c-ink: #123456;
  --color-primary-100: #f3f2ff;
  --mystery-block: block;
}
.uses-fs{ font-size: var(--fs-16) }
.uses-r{ border-radius: var(--r-16) }
.uses-a{ padding: var(--sp-a) }
.uses-b{ margin: var(--sp-b) }
.uses-c{ gap: var(--sp-c) }
.uses-d{ padding-left: var(--sp-d) }
.uses-weight{ font-weight: var(--fw-heavy) }
.uses-z{ position: fixed; z-index: var(--z-top) }
body{ margin: 0; height: 900px; font: 14px/1.4 sans-serif;
  background: repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px) }
#target{ margin: 0; padding-top: 16px; font-weight: 700; color: var(--c-ink);
  background-color: #f3f2ff; width: 320px; height: 160px; display: block }
#heavy{ margin: 0; font-weight: 800; background: #fff; width: 320px; height: 120px }
</style></head><body>
<p id="target" class="card">${id}</p>
<p id="heavy" class="card">${id}</p>
</body></html>`;

/** Канвас із живим інспектором і ввімкненим інспектором — тим же шляхом, що й
 *  дизайнер (кнопка смуги). */
async function openInspector(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  await page.click('#bar [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on === true, null, { timeout: 3000 });
  return page;
}

/** Рядок звіту по імені властивості, з усіх груп разом. */
function row(rep, prop) {
  for (const rows of Object.values(rep.groups)) {
    const hit = rows.find((d) => d.prop === prop);
    if (hit) return hit;
  }
  return null;
}

test("підказка бере токени ТІЄЇ САМОЇ категорії — і бере їх ДО обрізання", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openInspector(browser, url);

  /* Пінуємо фізичним кліком: саме так звіт народжується в дизайнера. */
  const box = await page.frameLocator("#frame").locator("#target").boundingBox();
  assert.ok(box, "не знайшов #target у макеті");
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);

  const rep = await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.report());
  assert.ok(rep, "клік мусить запінити елемент і дати звіт");

  /* A. Той самий рядок, що збрехав на bf360. ПРИЙМАЛЬНА перевірка задачі:
     обидва токени тут невживані й обидва — безрозмірні `700`, тобто ні вжиток,
     ні форма їх не розрізняють. Лишається ім'я, і тільки на виключення. */
  const fw = row(rep, "font-weight");
  assert.equal(fw.verdict, "hardcode", "font-weight: 700 — це літерал, вирок не змінювався");
  /* `ds: false` у кожній підказці — T-40: кандидат прийшов із токенів МАКЕТА,
     а не з дизайн-системи. У цієї фікстури напрямку немає зовсім, тобто ДС
     невідома, і `false` тут не «не перевірили», а «системним не є» — типове
     значення навмисно в цей бік (`hintOf`, `app/tuner-model.js`). */
  assert.deepEqual(fw.hint, [{ name: "--fw-bold", tier: "shape", ds: false }],
    "у підказці про вагу шрифту не сміє бути токена z-index із тим самим значенням");

  /* B + C. Законні кандидати лишились, їх не витіснили чужі, і доведені стоять
     ПЕРЕД здогадними: `--sp-a`…`--sp-d` вживають у макеті, `--fs-16`/`--r-16`
     теж, але для чужих родин. */
  const pt = row(rep, "padding-top");
  assert.equal(pt.verdict, "hardcode");
  assert.deepEqual(pt.hint, [
    { name: "--sp-a", tier: "used", ds: false },
    { name: "--sp-b", tier: "used", ds: false },
    { name: "--sp-c", tier: "used", ds: false },
  ], "відступи мусять лишитись (родина, а не гола властивість) і зайняти всі три місця");
  assert.ok(!pt.hint.some((h) => h.name === "--sp-guess"),
    "`--sp-guess` теж годиться відступам, але він лише ЗДОГАД (ніде не вжитий) "
    + "і оголошений ПЕРШИМ — якщо він проліз у трійку, значить здогади стали "
    + "попереду доведених");

  /* E. Рівень 2 живий: колірний токен, який НІДЕ не вжитий, усе одно
     пропонується для кольору — і позначений як здогад. Саме заради цього
     випадку власник і просив не викидати невживані токени. */
  const bg = row(rep, "background-color");
  assert.equal(bg.verdict, "hardcode");
  assert.deepEqual(bg.hint, [{ name: "--color-primary-100", tier: "shape", ds: false }],
    "оголошений, але не вжитий колірний токен мусить пропонуватись — як ЗДОГАД");

  /* D. Нуль як був `unlinked`, так і лишився — Task 10.5 його не чіпав. */
  for (const prop of ["margin-top", "margin-left"]) {
    const z = row(rep, prop);
    assert.equal(z.verdict, "unlinked", `${prop}: нуль не буває «повз дизайн-систему»`);
    assert.deepEqual(z.hint, [], `${prop}: у нуля підказки немає`);
  }

  /* F. Форма значення — ЄДИНЕ, що стоїть тут на дорозі: `--mystery-block: block`
     ніде не вжитий, а ім'я його не заявляє нічого, тож ані вжиток, ані словник
     імен цього кандидата не знімуть. Знімає його те, що в `display` значення —
     ключове слово, а збіг тексту `block` не доводить нічого (так само народилась
     колись порада «display: none → --shadow-s»). */
  const dsp = row(rep, "display");
  assert.equal(dsp.verdict, "hardcode", "display: block оголошено літералом — це хардкод");
  assert.deepEqual(dsp.hint, [],
    "значення-ключове-слово не дає здогадів: збіг тексту — не доказ родини");

  /* І контроль того, що інспектор узагалі при памʼяті: токен, ужитий через
     var(), як і раніше впізнається як токен. Без цього рядка «зелено» могло б
     означати «звіт порожній». */
  assert.equal(row(rep, "color").verdict, "token");
  assert.equal(row(rep, "color").token, "--c-ink");

  /* Та сама безрозмірна колізія (`800`), але на парі, яку в макеті ВЖИВАЮТЬ:
     тут категорію доводить факт, а не ім'я, і рівень мусить бути 'used'. Без
     цього блоку перевірка не відрізнила б «вжиток працює» від «усе тримається
     на словнику імен». */
  const hv = await page.frameLocator("#frame").locator("#heavy").boundingBox();
  assert.ok(hv, "не знайшов #heavy у макеті");
  await page.mouse.click(hv.x + hv.width / 2, hv.y + hv.height / 2);
  const rep2 = await page.evaluate(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.report());
  assert.deepEqual(row(rep2, "font-weight").hint, [{ name: "--fw-heavy", tier: "used", ds: false }],
    "ужитий токен ваги — доведений; ужитий токен z-index із тим самим значенням — геть");
});
