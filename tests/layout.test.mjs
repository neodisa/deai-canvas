import assert from "node:assert/strict";
import test from "node:test";

import { CARD_W } from "../app/canvas-geom.js";
import { rowsLayout, worldBox } from "../app/layout.js";
import { CANVAS_W } from "../app/viewport.js";

const ROPTS = { cardW: 1280, gap: 96, head: 34 };
const row = (...heights) => heights.map((h, i) => ({ id: `c${i}`, h }));

test("ряди різної довжини: крок усередині ряду, наступний ряд нижче", () => {
  const placed = rowsLayout([row(900, 900, 900, 900), row(600)], ROPTS);
  assert.deepEqual(placed.map((p) => p.x), [0, 1376, 2752, 4128, 0]);
  // перший ряд заввишки 934 (head+900), далі зазор 96 → 1030
  assert.deepEqual(placed.map((p) => p.y), [0, 0, 0, 0, 1030]);
});

test("висота ряду — під найвищу карточку В НЬОМУ, картка лишається своєю", () => {
  const placed = rowsLayout([row(400, 1200), row(500)], ROPTS);
  assert.deepEqual(placed.map((p) => p.h), [434, 1234, 534]);
  assert.deepEqual(placed.map((p) => p.y), [0, 0, 1330]);
});

test("порожні ряди не займають місця і не ламають розкладку", () => {
  const placed = rowsLayout([[], row(500), []], ROPTS);
  assert.deepEqual(placed.map((p) => p.id), ["c0"]);
  assert.deepEqual(placed.map((p) => p.y), [0]);
});

test("порожній перелік рядів дає порожню розкладку і нульовий світ", () => {
  assert.deepEqual(rowsLayout([], ROPTS), []);
  /* Порожній світ ловиться саме тут: без охорони `worldBox` пішов би в
     `Math.max()` БЕЗ аргументів і віддав -Infinity — габарит, який каже, що
     світ менший за ніщо.
     Наслідок названо чесно, бо перша редакція цього коментаря обіцяла
     «NaN-камеру», якої не буває: `fitBox` затискає `Math.max(box.w, 1)`, тож
     -Infinity дає РІВНО ту саму камеру, що й нуль (`{x:699.5, y:449.5,
     scale:1}` на 1400×900 — виміряно). До камери воно сьогодні й не доходить:
     `fitAll()` має власну охорону `if (!cards.length) return`. Пришпилюється
     тут КОНТРАКТ функції — розмір не буває відʼємним, — щоб наступний
     викликач, у якого своєї охорони не буде, не успадкував -Infinity. */
  assert.deepEqual(worldBox([], ROPTS.cardW), { w: 0, h: 0 });
});

test("непридатна висота кидає, а не малює негативний прямокутник", () => {
  // Повне повідомлення, а не саме лише «непридатна»: сенс охорони — сказати, ЯКА
  // картка і ЯКЕ значення зламали манифест, тож із тексту не можна дати викинути
  // ні id, ні значення.
  assert.throws(() => rowsLayout([[{ id: "bad", h: NaN }]], ROPTS), /картка bad: висота NaN непридатна/);
  assert.throws(() => rowsLayout([[{ id: "bad", h: -5 }]], ROPTS), /картка bad: висота -5 непридатна/);
  // Погана картка НЕ перша в НЕ першому ряді: цикл тут дворівневий, і на
  // одноелементному вході «перевіряю лише row[0]» та «лише rows[0]» лишились би
  // зеленими — обхід обох рівнів пришпилено саме цією позицією.
  assert.throws(
    () => rowsLayout([row(500), [{ id: "ok", h: 100 }, { id: "bad", h: -5 }]], ROPTS),
    /картка bad: висота -5 непридатна/
  );
});

test("worldBox обіймає найправішу й найнижчу карточку рядів", () => {
  const placed = rowsLayout([row(900, 900), row(400)], ROPTS);
  assert.deepEqual(worldBox(placed, ROPTS.cardW), { w: 2656, h: 1464 });
});

/* Два числа в різних файлах означають одне: ширину, якою знімається типовий
   кадр. Розійдуться — знімки поїдуть в одній ширині, а картки стануть іншої, і
   виглядатиме це як «кадр не влазить», а не як розсинхрон констант. */
test("типова ширина полотна і ширина картки — одне число", () => {
  assert.equal(CANVAS_W, CARD_W);
});
