/**
 * Живі тести оверлея інспектора (Alt-відстані): справжній Chromium по справжньому серверу, сторінка відкрита ПРЯМО
 * (`/commented?...`), без канваса й без iframe — так інспектор і живе в макеті (його інжектить снипет `serve.py`).
 *
 * 0.29.0: режим «Лінійка» (клавіша M, `measure()`, чотири сусіди навколо наведеного) ПРИБРАНО — його тести (A–P, окрім
 * нижче) втратили предмет і видалені разом із ним: сусіди й край контейнера (B, B2, C, D, E, F, G, H, I, M),
 * перемикач режиму (A, K), «лінійка за курсором» (J, L), «плашка не накриває ціль» (N2) і вьюпортне обмеження (O, воно стерегло `measure` без якоря).
 * Лишилась і переїхала на Alt геометрія ПАРНОГО виміру — відстань від вибраного (клік) до наведеного, з Alt:
 *
 *   Q (між ними)      — з Alt і якорем число = зазор між якорем і ціллю, одна напрямна; відпущений Alt ліній не має.
 *                       Запобіжник: вибір цілі в `_draw` (`hov` перед `_navParent`) — інакше міряє батька, а не ціль.
 *   R (всередині)     — іконка В кнопці: чотири внутрішні відстані, вид `inside`. Запобіжник: `data-kind` у `_pair`.
 *   S (перекриття)    — вид `overlap` і клас `lap` на плашці й лінії. Прибери `lap` — перекриття читається як зазор.
 *   N, P (плашки)     — розкладка `_spread`: плашки на дрібному елементі не налізають одна на одну, а при нульових
 *                       зазорах тримаються на екрані. Запобіжник: `PILL_PASSES` (=0 → обидва червоні); тіло `_spread` (усе в `edge` → червоний P).
 *                       Перевірку «плашка не накриває ціль» (N2) знято: вона належала режиму лінійки, де плашки йшли
 *                       ВІД цілі. У парному вимірі плашка їде від ЯКОРЯ, а для «іконка в кнопці» це всередину — на
 *                       ціль; `_spread` це документує («може налізти на сусіда чи контейнер, але не зникнути»).
 */
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу: `node --test` крутить файли паралельно. */
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

const PAGE = (id) => (id === "tiny" ? TINY : HOLOVNA);

/** Дописати в фікстуру сторінку `tiny` понад ті, що робить `taskFixture`. */
function addPages(it1) {
  mkdirSync(path.join(it1, "tiny"), { recursive: true });
  writeFileSync(path.join(it1, "tiny", "index.html"), TINY);
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: "Головна", published: true },
            { id: "poshuk", name: "Пошук", published: true },
            { id: "tiny", name: "Дрібні", published: true }],
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

test("інспектор: Alt-відстані", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  addPages(it1);
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());

  async function layout(pageId) {
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/commented?it=it1&page=${pageId}&ch=local`);
    await page.waitForFunction(() => !!(window.CanvasInspector && window.CanvasInspector._host));
    await page.keyboard.press("i");
    return page;
  }
  const at = async (page, sel, dx, dy) => {
    const box = await page.locator(sel).boundingBox();
    return [box.x + (dx ?? box.width / 2), box.y + (dy ?? box.height / 2)];
  };
  /** Вибрати якір кліком, затиснути Alt і навести на ціль. */
  async function altOver(page, anchor, target, anchorAt = []) {
    const [ax, ay] = await at(page, anchor, ...anchorAt);
    await page.mouse.move(ax, ay);
    await page.mouse.click(ax, ay);
    await page.keyboard.down("Alt");
    const [tx, ty] = await at(page, target);
    await page.mouse.move(tx, ty);
  }

  await t.test("Q. якір + Alt + ховер = відстань МІЖ ними; без Alt ліній немає", async () => {
    const page = await layout("holovna");
    await altOver(page, "#b", "#c");
    const want = await page.evaluate(() => Math.round(document.getElementById("c").getBoundingClientRect().top
      - document.getElementById("b").getBoundingClientRect().bottom));
    assert.equal(want, 70, "фікстура: 40 margin + 20 veil + 10 = 70");
    const got = await readRuler(page);
    const keys = Object.keys(got);
    assert.equal(keys.length, 1, `у зазорі одна напрямна, а не ${keys.length}: ${keys}`);
    assert.equal(got[keys[0]].px, String(want), "число — відстань між якорем і ціллю");
    assert.equal(got[keys[0]].kind, "gap");
    assert.equal(await page.evaluate(() => CanvasInspector.pinned && CanvasInspector.pinned.id), "b",
      "якір лишається на вибраному, поки дивишся на інші");
    await page.keyboard.up("Alt");
    assert.deepEqual(await readRuler(page), {}, "відпущений Alt прибирає плашки");
  });

  await t.test("R. іконка ВСЕРЕДИНІ кнопки — чотири внутрішні відстані", async () => {
    const page = await layout("tiny");
    /* Кнопка КРУГЛА: клік у кут коробки провалюється до `body`, тож цілимось у центр по горизонталі й на 4px від
       верху — це в колі, але не на іконці 20×20 (вона займає 9..29). */
    await altOver(page, "#btn", "#dot", [undefined, 4]);
    const got = await readRuler(page);
    assert.deepEqual(Object.keys(got).sort(), ["bottom", "left", "right", "top"]);
    for (const [side, v] of Object.entries(got)) {
      assert.equal(v.px, "9", `${side}: іконка 20×20 у кнопці 38×38 = по 9 з боків`);
      assert.equal(v.kind, "inside");
    }
  });

  await t.test("S. перекриття читається як перекриття, а не як зазор", async () => {
    const page = await layout("tiny");
    await altOver(page, "#lap1", "#lap2", [4, 4]);
    const got = await readRuler(page);
    const kinds = [...new Set(Object.values(got).map((v) => v.kind))];
    assert.deepEqual(kinds, ["overlap"], `вид мусить бути overlap, а не ${kinds}`);
    assert.deepEqual(Object.values(got).map((v) => v.px).sort(), ["30", "60"], "перекриття 60 по X і 30 по Y");
    /* Атрибута мало: дивляться на ЕКРАН, а не на розмітку. */
    const look = await page.evaluate(() => {
      const sh = document.querySelector("[data-canvas-inspector]").shadowRoot;
      const lab = [...sh.querySelectorAll("[data-ruler-label]")].find((n) => n.getBoundingClientRect().width);
      const line = [...sh.querySelectorAll("[data-ruler-line]")].find((n) => !n.classList.contains("hidden"));
      return { lab: lab.className, line: line.className };
    });
    assert.ok(/\blap\b/.test(look.lab), `плашка перекриття мусить виглядати інакше: ${look.lab}`);
    assert.ok(/\blap\b/.test(look.line), `лінія перекриття мусить виглядати інакше: ${look.line}`);
  });

  await t.test("N. чотири плашки на дрібному елементі не злипаються", async () => {
    const page = await layout("tiny");
    await altOver(page, "#btn", "#dot", [undefined, 4]);
    const got = await readPills(page, "#dot");
    assert.deepEqual(got.size, [20, 20], "сама фікстура: іконка 20×20");
    assert.deepEqual(got.nums, { top: "9", right: "9", bottom: "9", left: "9" }, "усі чотири числа на місці");
    assert.deepEqual(got.pairs, [], `плашки налізли одна на одну: ${got.pairs.join(", ")}`);
  });

  await t.test("P. нульові зазори з усіх боків — плашки все одно розходяться", async () => {
    const page = await layout("tiny");
    await altOver(page, "#snug", "#fill", [1, 1]);
    const got = await readPills(page, "#fill");
    assert.deepEqual(got.size, [10, 10], "сама фікстура: 10×10");
    assert.deepEqual(got.nums, { top: "0", right: "0", bottom: "0", left: "0" });
    assert.deepEqual(got.pairs, [], `плашки мусять розійтись: ${got.pairs.join(", ")}`);
    assert.deepEqual(got.offScreen, [], `плашка поїхала за екран: ${got.offScreen.join(", ")}`);
  });
});
