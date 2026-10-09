import assert from "node:assert/strict";
import test from "node:test";

import {
  FIT_MAX_SCALE, FIT_MIN_SCALE, MAX_SCALE, MIN_SCALE, clamp, fitBox, focusBox,
  quantScale, step,
  zoomAt,
} from "../app/camera.js";

test("clamp тримає межі", () => {
  assert.equal(clamp(5, 0, 1), 1);
  assert.equal(clamp(-5, 0, 1), 0);
  assert.equal(clamp(0.5, 0, 1), 0.5);
});

test("точка під курсором не зʼїжджає при зумі", () => {
  const cam = { x: -300, y: -120, scale: 0.4 };
  const cursor = { cx: 500, cy: 300, delta: -120 };
  const world = { x: (cursor.cx - cam.x) / cam.scale, y: (cursor.cy - cam.y) / cam.scale };
  const next = zoomAt(cam, cursor);
  assert.ok(Math.abs(next.x + world.x * next.scale - cursor.cx) < 1e-6);
  assert.ok(Math.abs(next.y + world.y * next.scale - cursor.cy) < 1e-6);
});

test("велика дельта тачпада важить не більше за один щиглик мишею", () => {
  const cam = { x: 0, y: 0, scale: 1 };
  const notch = zoomAt(cam, { cx: 0, cy: 0, delta: 120 });
  const pinch = zoomAt(cam, { cx: 0, cy: 0, delta: 9000 });
  assert.equal(pinch.scale, notch.scale);
});

test("зум не виходить за межі", () => {
  let cam = { x: 0, y: 0, scale: MIN_SCALE };
  for (let i = 0; i < 50; i += 1) cam = zoomAt(cam, { cx: 0, cy: 0, delta: 120 });
  assert.equal(cam.scale, MIN_SCALE);
  cam = { x: 0, y: 0, scale: MAX_SCALE };
  for (let i = 0; i < 50; i += 1) cam = zoomAt(cam, { cx: 0, cy: 0, delta: -120 });
  assert.equal(cam.scale, MAX_SCALE);
});

test("згладжування доходить до цілі й каже про це", () => {
  let cam = { x: 0, y: 0, scale: 1 };
  const target = { x: -800, y: -400, scale: 0.35 };
  let frames = 0;
  let done = false;
  while (!done && frames < 400) {
    const next = step(cam, target, 16);
    done = next.done;
    cam = { x: next.x, y: next.y, scale: next.scale };
    frames += 1;
  }
  assert.ok(done, "цикл мусить завершитись, а не котитись вічно");
  assert.ok(frames < 120, `дійшов за ${frames} кадрів — надто мляво`);
  assert.deepEqual(cam, target);
});

test("крок не перескакує цілі", () => {
  const next = step({ x: 0, y: 0, scale: 1 }, { x: 100, y: 0, scale: 1 }, 16);
  assert.ok(next.x > 0 && next.x < 100);
});

test("вписати світ — центрує і не збільшує понад 1", () => {
  const cam = fitBox({ w: 4000, h: 2000 }, { w: 1200, h: 800 }, 60);
  assert.ok(cam.scale < 1);
  assert.ok(Math.abs((1200 - 4000 * cam.scale) / 2 - cam.x) < 1e-6);
  const small = fitBox({ w: 100, h: 100 }, { w: 1200, h: 800 }, 60);
  assert.equal(small.scale, 1);
});

test("порожній світ не дає NaN", () => {
  const cam = fitBox({ w: 0, h: 0 }, { w: 1200, h: 800 }, 60);
  assert.ok(Number.isFinite(cam.x) && Number.isFinite(cam.y) && Number.isFinite(cam.scale));
});

test("нескінченна ціль падає, а не крутить цикл вічно", () => {
  assert.throws(
    () => step({ x: 0, y: 0, scale: 1 }, { x: NaN, y: 0, scale: 1 }, 16),
    /ціль камери непридатна: x = NaN/
  );
  assert.throws(
    () => step({ x: 0, y: 0, scale: 1 }, { x: 0, y: Infinity, scale: 1 }, 16),
    /ціль камери непридатна: y = Infinity/
  );
});

test("нульовий масштаб камери падає, а не дає Infinity", () => {
  assert.throws(
    () => zoomAt({ x: 0, y: 0, scale: 0 }, { cx: 0, cy: 0, delta: 120 }),
    /масштаб камери непридатний: 0/
  );
  assert.throws(
    () => zoomAt({ x: 0, y: 0, scale: -0.5 }, { cx: 0, cy: 0, delta: 120 }),
    /масштаб камери непридатний/
  );
});

/* Переліт до одного кадру (клік по рядку панелі сторінок). Вписування ПО ШИРИНІ,
   а не по габариту: кадр буває 8000px високий, і вписаний по висоті він дає той
   самий bird-view, з якого людина й тікає, натискаючи рядок. */
test("переліт до кадру: масштаб по ширині, кадр по центру, верх видно", () => {
  const box = { x: 5504, y: 3200, w: 1280 };
  const view = { w: 1180, h: 854 };
  const cam = focusBox(box, view, 60);
  // Ширина кадру на екрані — рівно полотно без полів: масштаб рахований по ній
  assert.ok(Math.abs(box.w * cam.scale - (view.w - 120)) < 1e-6,
    `кадр на екрані ${box.w * cam.scale}px при полотні ${view.w}px`);
  // Центр кадру — у центрі полотна (кадр стоїть НЕ в нулі світу, тож зсув видно)
  const cx = cam.x + (box.x + box.w / 2) * cam.scale;
  assert.ok(Math.abs(cx - view.w / 2) < 1e-6, `центр кадру ${cx}, центр полотна ${view.w / 2}`);
  /* Верх кадру — на полі нижче верхнього краю: людина хоче побачити ПОЧАТОК
     екрана. По центру вертикально його ставити не можна — у високого кадру
     початок пішов би за верхній край. */
  assert.ok(Math.abs(cam.y + box.y * cam.scale - 60) < 1e-6,
    `верх кадру на ${cam.y + box.y * cam.scale}px, а мусив на 60`);
});

test("висота кадру на масштаб переліту не впливає", () => {
  const view = { w: 1180, h: 854 };
  const tall = focusBox({ x: 0, y: 0, w: 1280, h: 8000 }, view, 60);
  const short = focusBox({ x: 0, y: 0, w: 1280, h: 400 }, view, 60);
  assert.equal(tall.scale, short.scale, "висота кадру не сміє міняти масштаб");
  /* І це не те саме, що «вписати». Порівняння саме з `fitBox`: інакше перевірка
     не відрізняє переліт від bird-view, тобто фічі в ній немає. */
  assert.ok(tall.scale > fitBox({ w: 1280, h: 8000 }, view, 60).scale * 5,
    `${tall.scale} — це майже те саме, що «вписати все»`);
});

test("масштаб переліту тримається меж камери й не більший за 1", () => {
  const view = { w: 1180, h: 854 };
  // Вузький кадр міг би розтягтись — але кадр знято 1:1, більше нема чого показувати
  assert.equal(focusBox({ x: 0, y: 0, w: 200 }, view).scale, FIT_MAX_SCALE);
  // А у вьюпорті, вужчому за поля, формула дає нуль або мінус
  assert.equal(focusBox({ x: 0, y: 0, w: 1280 }, { w: 100, h: 100 }).scale, MIN_SCALE);
});

test("кадр нульової ширини не дає NaN", () => {
  const wide = focusBox({ x: 0, y: 0, w: 0 }, { w: 1180, h: 854 });
  assert.ok(Number.isFinite(wide.x) && Number.isFinite(wide.y) && Number.isFinite(wide.scale));
  /* А ось де `Math.max(box.w, 1)` справді несущий, і це знайдено мутаційно:
     нульова ширина В ПАРІ з полотном, не ширшим за поля, дає `0 / 0` — а `clamp`
     від NaN повертає NaN, тобто ціль камери стає непридатною. Сам по собі `w: 0`
     у нормальному полотні дає `Infinity`, який кламп зрізає до стелі, і мутація
     «прибрати Math.max» лишалась зеленою. */
  const narrow = focusBox({ x: 0, y: 0, w: 0 }, { w: 120, h: 120 });
  assert.ok(Number.isFinite(narrow.scale), `масштаб ${narrow.scale}`);
  assert.ok(Number.isFinite(narrow.x) && Number.isFinite(narrow.y),
    `камера ${narrow.x},${narrow.y}`);
});

/* Падати мусить САМ `focusBox`, і синхронно. `step` теж стереже ціль, але кидає
   вже ВСЕРЕДИНІ rAF-кадру: `camRaf` лишається непорожнім, тому наступний `camTo`
   не запустить нічого — камера мертва до перебудови холста, а в консолі одна
   помилка без викликача. */
test("непридатний кадр падає одразу, а не морозить камеру в rAF", () => {
  const view = { w: 1180, h: 854 };
  assert.throws(() => focusBox({ x: NaN, y: 0, w: 1280 }, view),
    /кадр непридатний: x = NaN/);
  assert.throws(() => focusBox({ x: 0, y: 0, w: undefined }, view),
    /кадр непридатний: w = undefined/);
});

/* ===== Квантований масштаб для CSS-змінної на `#world` =====

   Підпис смуги живе у СВІТІ, тобто масштабується разом із ним і на дрібному зумі
   зникає. Лікує це кегль через `calc()` від масштабу — а ціна рішення була відома
   ще зі спеки: «якщо колись зʼявиться CSS-змінна зуму — писати її лише при
   реальній зміні значення, інакше інвалідується стиль усім спадкоємцям щокадру».
   Звідси квантування: масштаб сідає на сітку, і `applyT` пише змінну лише коли
   КЛІТКА змінилась, а не коли змінився масштаб. */

test("квант масштабу не видно оком", () => {
  /* Найгірший випадок — рівно посередині клітки. Допуск 5%: кегль підпису
     відхиляється на стільки ж, а 5% на 22px — це 1px, якого не побачити. */
  for (let s = MIN_SCALE; s <= MAX_SCALE; s *= 1.017) {
    const q = quantScale(s);
    assert.ok(Math.abs(q / s - 1) < 0.05,
      `масштаб ${s.toFixed(4)} став ${q.toFixed(4)} — це видно оком`);
  }
});

test("сітка квантування груба: значень десятки, а не тисячі", () => {
  /* Уся суть у ЦЬОМУ: дрібний дрейф масштабу (хвіст згладжування, півщиглика
     колеса) не сміє давати нове значення змінної. Мутація «вертати масштаб як є»
     дає тисячі значень і червоніє тут. Нижня межа — проти мутації «вертати 1»:
     одне значення на весь діапазон читне так само погано, як і жодного. */
  const seen = new Set();
  for (let s = MIN_SCALE; s <= MAX_SCALE; s *= 1.002) seen.add(quantScale(s));
  assert.ok(seen.size <= 64, `клітків ${seen.size} — сітка не груба`);
  assert.ok(seen.size >= 20, `клітків ${seen.size} — сітка глушить сама фічу`);
});

test("квант стабільний і не перевертає порядок", () => {
  let prev = 0;
  for (let s = MIN_SCALE; s <= MAX_SCALE; s *= 1.01) {
    const q = quantScale(s);
    // Ідемпотентність: інакше значення, вже покладене в змінну, дало б ще один запис.
    assert.equal(quantScale(q), q, `квант ${q} не сидить на своїй клітці`);
    assert.ok(q >= prev, `масштаб ріс, а квант упав: ${prev} → ${q}`);
    prev = q;
  }
});

test("непридатний масштаб падає, а не тече в CSS", () => {
  /* Той самий контракт, що в `zoomAt`: нуль і NaN до `calc()` доходити не сміють —
     кегль стає `Infinity`/`NaN`, недійсне оголошення браузер викидає, і підпис
     лишається без розміру зовсім. */
  assert.throws(() => quantScale(0), /масштаб непридатний: 0/);
  assert.throws(() => quantScale(NaN), /масштаб непридатний: NaN/);
  assert.throws(() => quantScale(-1), /масштаб непридатний: -1/);
});

test("«вписати все» мусить ВПИСАТИ, а не впертися в підлогу колеса", () => {
  /* Виміряно на демо-задачі (сторінка висотою 8000px): світ 18079px, і на вікні
     804px «вписати все» лишало 54px за краєм, на 654px — 129px, а масштаб в усіх
     випадках стояв на 0.05, тобто на MIN_SCALE. Полотно мовчки показувало менше,
     ніж є — рівно та неправда, проти якої написаний увесь інструмент.

     Підлога колеса й підлога вписування — РІЗНІ речі: перша не дає зникнути
     макету під рукою, друга мусить пускати камеру так далеко, як треба, щоб усе
     справді влізло. */
  const box = { w: 3000, h: 18079 };
  const cam = fitBox(box, { w: 1700, h: 804 });
  assert.ok(cam.scale < MIN_SCALE, `масштаб ${cam.scale} не пройшов нижче підлоги колеса`);
  assert.ok(box.h * cam.scale <= 804, `світ ${Math.round(box.h * cam.scale)}px не влазить у 804px`);
  assert.ok(cam.scale >= FIT_MIN_SCALE, "нижче власної підлоги вписування падати не мусить");
});

test("вписування не роздуває дрібний світ понад 1:1", () => {
  // Стеля лишається як була: кадр знято 1:1, роздувати нема чого.
  assert.equal(fitBox({ w: 100, h: 100 }, { w: 1700, h: 900 }).scale, FIT_MAX_SCALE);
});
