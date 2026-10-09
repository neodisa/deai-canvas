import assert from "node:assert/strict";
import test from "node:test";

import { between, measure } from "../app/vendor/inspector-measure.js";

/* Лінійка інспектора: чиста геометрія, нуль DOM — тому тестується в node.
   `measure(target, candidates, container)` → `{ top, right, bottom, left }`,
   де кожен напрямок або `null`, або `{ px, kind: 'element' | 'container', index }`
   (`index` — позиція кандидата у вхідному масиві, для контейнера `-1`).

   Прямокутники — у форматі `getBoundingClientRect`. Будуються хелпером
   `box(left, top, w, h)`, бо перелічувати чотири краї руками — це помилка в
   тесті, а не в коді. */
const box = (left, top, w, h) => ({ top, right: left + w, bottom: top + h, left });

/* Ціль усіх тестів, де не сказано інакше: 100..200 по X, 200..250 по Y. */
const target = box(100, 200, 100, 50);

test("сусід зверху й знизу — відстань від краю до краю", () => {
  /* Зазор, а не відстань між центрами: дизайнер міряє порожнє місце між
     обʼєктами, саме його він потім кладе в токен відступу. */
  const above = box(100, 100, 100, 40);   // bottom 140 → зазор 60
  const below = box(100, 300, 100, 40);   // top 300 → зазор 50
  const res = measure(target, [above, below], null);
  assert.deepEqual(res.top, { px: 60, kind: "element", index: 0 });
  assert.deepEqual(res.bottom, { px: 50, kind: "element", index: 1 });
  assert.equal(res.left, null, "збоку нікого немає — і контейнера теж");
  assert.equal(res.right, null);
});

test("сусід збоку, чиї проєкції не перетинаються, у результат не потрапляє (Р4)", () => {
  /* Це серце геометрії: без перевірки проєкцій «найближчим зверху» став би
     елемент десь збоку, і число було б правдою ні про що. */
  const aside = box(300, 100, 50, 40);    // вище і правіше цілі, проєкції розійшлись
  const res = measure(target, [aside], null);
  assert.equal(res.top, null, "по X проєкції не перетинаються — не сусід зверху");
  assert.equal(res.right, null, "по Y проєкції не перетинаються — не сусід справа");
  assert.equal(res.bottom, null);
  assert.equal(res.left, null);
});

test("перетин проєкцій рівно в одній точці — кутик до кутика — не сусід (Р4)", () => {
  /* Кандидат, що торкається цілі лише кутом, не має спільної смуги, якою можна
     провести напрямну: число було б, а показати його ніде. */
  const corner = box(0, 100, 100, 40);    // right 100 === target.left, bottom 140
  const res = measure(target, [corner], null);
  assert.equal(res.top, null, "перетин по X рівно 0 — це кут, не сусід зверху");
  assert.equal(res.left, null, "перетин по Y рівно 0 — це кут, не сусід злева");
});

test("з двох сусідів у тому самому напрямку беремо ближчого", () => {
  const far = box(100, 0, 100, 20);       // bottom 20 → зазор 180
  const near = box(100, 150, 100, 20);    // bottom 170 → зазор 30
  const res = measure(target, [far, near], null);
  assert.deepEqual(res.top, { px: 30, kind: "element", index: 1 });
  /* Той самий набір у зворотному порядку мусить дати те саме число: інакше
     показане дизайнеру залежало б від порядку обходу DOM. */
  const back = measure(target, [near, far], null);
  assert.deepEqual(back.top, { px: 30, kind: "element", index: 0 });
});

test("немає сусіда — міряємо до внутрішнього краю контейнера (Р2)", () => {
  /* «Відстані немає» — неправда: край контейнера це теж обʼєкт, і саме його
     показує референс. */
  const container = box(0, 0, 400, 400);
  const res = measure(target, [], container);
  assert.deepEqual(res.top, { px: 200, kind: "container", index: -1 });
  assert.deepEqual(res.right, { px: 200, kind: "container", index: -1 });
  assert.deepEqual(res.bottom, { px: 150, kind: "container", index: -1 });
  assert.deepEqual(res.left, { px: 100, kind: "container", index: -1 });
});

test("сусід ближче за край контейнера — беремо сусіда, і навпаки", () => {
  const container = box(0, 0, 400, 400);  // зазор до верхнього краю 200
  const near = box(100, 150, 100, 40);    // bottom 190 → зазор 10
  const a = measure(target, [near], container);
  assert.deepEqual(a.top, { px: 10, kind: "element", index: 0 });

  /* Навпаки буває, коли кандидат лежить ЗА межами контейнера — а так і є в
     живому макеті: збирач бере елементи по всій сторінці, а контейнер це лише
     батько цілі. */
  const outside = box(100, -100, 100, 40); // bottom -60 → зазор 260, вище контейнера
  const b = measure(target, [outside], container);
  assert.deepEqual(b.top, { px: 200, kind: "container", index: -1 });

  /* Нічия між сусідом і краєм контейнера — сусід: конкретний обʼєкт корисніший
     за межу, до якої дизайнеру нічого не привʼязати. */
  const tie = box(100, 100, 100, 40);      // bottom 140 → зазор 60
  const c = measure(target, [tie], box(0, 140, 400, 400));
  assert.deepEqual(c.top, { px: 60, kind: "element", index: 0 });
});

test("прямокутник, що повністю містить цільовий, сусідом не вважається (Р3)", () => {
  /* Обгортка (і власний оверлей інспектора) лежить навколо цілі — відстань до
     неї не зазор, а нуль ні про що. */
  const wrapper = box(50, 150, 200, 200);
  const res = measure(target, [wrapper], null);
  assert.deepEqual(res, { top: null, right: null, bottom: null, left: null });
});

test("порожня ціль нульової висоти не міряє нуль до власної обгортки (Р3)", () => {
  /* Єдиний випадок, де правило «містить» справді працює окремо від Р4: у
     невиродженої цілі обгортку відкидає вже перевірка напрямку. */
  const empty = box(100, 200, 100, 0);
  const wrapper = box(100, 150, 100, 50);  // bottom 200 === empty.top, містить ціль
  const res = measure(empty, [wrapper], null);
  assert.equal(res.top, null, "обгортка не сусід, навіть коли її край збігся з ціллю");
});

test("кандидат нульового розміру ігнорується", () => {
  /* Схований (`display:none`) елемент дає нульовий прямокутник — міряти до
     нього означає показати відстань до того, чого не видно. */
  const flat = box(100, 150, 100, 0);      // нульова висота, зазор був би 50
  const gone = box(0, 0, 0, 0);
  const res = measure(target, [flat, gone], null);
  assert.equal(res.top, null);
  assert.equal(res.left, null);
});

test("елемент, що перетинає ціль, пропускається — не нуль і не мінус", () => {
  /* РІШЕННЯ: перекриття не подаємо нулем, а пропускаємо. Нуль завжди вигравав
     би `min` і затирав справжній зазор до реального сусіда — а сама відповідь
     «0 зверху» про елемент, що лежить ПОВЕРХ цілі, ще й неправдива: він не
     зверху, він на ній. */
  const overlap = box(100, 230, 100, 50);  // 230..280 налазить на 200..250
  const below = box(100, 290, 100, 20);    // top 290 → зазор 40
  const res = measure(target, [overlap, below], null);
  assert.deepEqual(res.bottom, { px: 40, kind: "element", index: 1 },
    "перекриття не мусить затирати справжній зазор нулем");
  assert.equal(res.top, null);
  assert.equal(res.left, null);
  assert.equal(res.right, null);
  for (const [dir, hit] of Object.entries(res)) {
    if (hit) assert.ok(hit.px >= 0, `${dir}: відʼємних чисел лінійка не показує`);
  }
});

test("ціль, що вилазить за контейнер, не дає відʼємного числа", () => {
  /* Симетрично до перекриття елементів: край контейнера, який ЗА ціллю, це не
     зазор. Показати «-20» дизайнеру нічого не дає. */
  const container = box(0, 220, 400, 100); // top 220 нижче за target.top 200
  const res = measure(target, [], container);
  assert.equal(res.top, null, "ціль стирчить над контейнером — зазору зверху немає");
  assert.deepEqual(res.bottom, { px: 70, kind: "container", index: -1 });
});

test("ні сусідів, ні контейнера — усі чотири напрямки null, без падіння", () => {
  assert.deepEqual(measure(target, [], null), { top: null, right: null, bottom: null, left: null });
  /* Контейнер необовʼязковий: елемент у корені документа батька-обмежувача не
     має, і це не помилка викликача. */
  assert.deepEqual(measure(target, []), { top: null, right: null, bottom: null, left: null });
});

test("дробові координати не округлюються (Р5)", () => {
  /* Округлення — справа плашки, не геометрії: у живому макеті прямокутники
     дробові майже завжди. */
  const frac = box(10.25, 100.5, 50.5, 40.25);   // top 100.5
  const above = box(10.25, 50, 50.5, 20.25);     // bottom 70.25 → зазор 30.25
  const res = measure(frac, [above], null);
  assert.equal(res.top.px, 30.25);
});

test("порядок кандидатів не змінює число при однакових відстанях", () => {
  /* При нічиї перемагає ПЕРШИЙ у масиві — правило фіксоване, щоб напрямна не
     стрибала між двома однаково правильними сусідами при перемалюванні. */
  const a = box(100, 150, 100, 20);        // bottom 170 → зазор 30
  const b = box(150, 150, 100, 20);        // bottom 170 → зазор 30
  const straight = measure(target, [a, b], null);
  const reversed = measure(target, [b, a], null);
  assert.equal(straight.top.px, reversed.top.px, "число не залежить від порядку");
  assert.equal(straight.top.index, 0);
  assert.equal(reversed.top.index, 0, "нічию завжди бере перший — а не останній");
});

test("непридатна ціль кидає помилку з назвою", () => {
  /* Стиль `app/layout.js`: краще помилка, яка називає винного, ніж намальоване
     число, яке нічого не міряє. NaN у порівняннях тихо дає false, тобто
     кандидат просто зник би з лінійки — без жодної скарги. */
  assert.throws(() => measure(null, []), /цільовий прямокутник/);
  assert.throws(() => measure("100,200", []), /цільовий прямокутник/);
  assert.throws(() => measure({ ...target, top: NaN }, []), /цільовий прямокутник, top/);
  assert.throws(() => measure({ ...target, right: 50 }, []), /цільовий прямокутник.*вивернут/);
});

test("непридатний кандидат кидає помилку з його НОМЕРОМ", () => {
  /* Номер у тексті — щоб автор збирача знав, який елемент віддав криве число:
     кандидатів у макеті сотні. */
  assert.throws(() => measure(target, null), /список кандидатів/);
  assert.throws(() => measure(target, [box(0, 0, 10, 10), { ...target, bottom: "250" }]),
    /кандидат #1, bottom/);
  assert.throws(() => measure(target, [{ ...target, bottom: 100 }]), /кандидат #0.*вивернут/);
});

test("непридатний контейнер кидає помилку з назвою", () => {
  assert.throws(() => measure(target, [], { ...target, left: Infinity }),
    /прямокутник контейнера, left/);
  assert.throws(() => measure(target, [], { ...target, top: 999 }),
    /прямокутник контейнера.*вивернут/);
});

/* ─────────────────────────────────────────────────────────────────────────────
   Парне вимірювання: `between(a, b)` — відстань МІЖ двома вибраними
   прямокутниками (механіка VisBug: клік по одному, наведення на другий).

   Форма результату: `{ kind, outer, guides }`.
   `guides` — рівно ті напрямні, які треба намалювати: кожна це
   `{ axis: 'x' | 'y', px, from: { rect, side }, to: { rect, side } }`, де
   `from`/`to` називають два краї, між якими лежить число, а `from` — завжди край
   з МЕНШОЮ координатою (тому `px` ніколи не відʼємне).
   `kind`: 'gap' (одна напрямна) | 'diagonal' (дві, Г) | 'overlap' (дві)
   | 'inside' (чотири), `outer` — 'a' | 'b' для 'inside', інакше `null`. */
const pair = box(100, 200, 100, 50);   // та сама ціль: 100..200 × 200..250

const at = (rect, side) => ({ rect, side });

test("between: спільна смуга по X — один вертикальний зазор", () => {
  /* Випадок 1 брифа: прямокутники перетинаються по X, отже існує вертикальна
     смуга, якою можна провести ОДНУ напрямну. Одне число, не два. */
  const below = box(120, 300, 60, 40);       // X 120..180 у смузі, Y 300..340
  assert.deepEqual(between(pair, below), {
    kind: "gap",
    outer: null,
    guides: [{ axis: "y", px: 50, from: at("a", "bottom"), to: at("b", "top") }],
  });
});

test("between: спільна смуга по Y — один горизонтальний зазор", () => {
  const aside = box(260, 210, 40, 30);       // X 260..300, Y 210..240 у смузі
  assert.deepEqual(between(pair, aside), {
    kind: "gap",
    outer: null,
    guides: [{ axis: "x", px: 60, from: at("a", "right"), to: at("b", "left") }],
  });
});

test("between: дотик краями — зазор рівно 0, як і в `measure`", () => {
  /* Конвенція мусить бути ОДНА на два режими: у лінійці дотик краями це сусід
     із зазором 0, отже й тут це зазор 0, а не «перекриття». */
  const touching = box(200, 200, 50, 50);    // left 200 === pair.right
  assert.deepEqual(between(pair, touching), {
    kind: "gap",
    outer: null,
    guides: [{ axis: "x", px: 0, from: at("a", "right"), to: at("b", "left") }],
  });
});

test("between: по діагоналі — ДВА числа на Г-подібну напрямну", () => {
  /* Випадок 3 брифа: спільної смуги немає ні по X, ні по Y — одного числа не
     існує. Віддаємо дві напрямні (спершу X, тоді Y): рівно те, що малює VisBug
     кутом. */
  const diag = box(260, 300, 40, 40);
  assert.deepEqual(between(pair, diag), {
    kind: "diagonal",
    outer: null,
    guides: [
      { axis: "x", px: 60, from: at("a", "right"), to: at("b", "left") },
      { axis: "y", px: 50, from: at("a", "bottom"), to: at("b", "top") },
    ],
  });
});

test("between: дотик кутом — діагональ із двома нулями, а не зазор", () => {
  /* `measure` кутовий дотик сусідом НЕ вважає (спільної смуги нема). Тут ми не
     шукаємо мінімум, тому не мовчимо — але й не брешемо, що це зазор по одній
     осі: два нулі. */
  const corner = box(200, 250, 40, 40);      // left 200 === right, top 250 === bottom
  assert.deepEqual(between(pair, corner), {
    kind: "diagonal",
    outer: null,
    guides: [
      { axis: "x", px: 0, from: at("a", "right"), to: at("b", "left") },
      { axis: "y", px: 0, from: at("a", "bottom"), to: at("b", "top") },
    ],
  });
});

test("between: смуга нульової товщини по одній осі — теж діагональ", () => {
  /* Краї збіглися по Y (250 === 250), тобто смуги для горизонтальної напрямної
     немає — Р4 лінійки. Отже це не «зазор 60 справа», а Г з нульовим коліном. */
  const grazing = box(260, 250, 40, 40);
  const res = between(pair, grazing);
  assert.equal(res.kind, "diagonal");
  assert.deepEqual(res.guides.map((g) => [g.axis, g.px]), [["x", 60], ["y", 0]]);
});

test("between: перекриття не пропускаємо — кажемо, на скільки налізло", () => {
  /* У `measure` перекриття СВІДОМО пропущено: нуль вигравав би пошук мінімуму й
     затирав справжній зазор. Тут пошуку мінімуму немає — дизайнер сам вибрав
     обидва елементи й має право знати, що вони перетинаються і на скільки.
     Числа лишаються ДОДАТНІ (глибина перекриття), а знак несе `kind`. */
  const over = box(150, 230, 100, 60);       // X 150..250, Y 230..290
  assert.deepEqual(between(pair, over), {
    kind: "overlap",
    outer: null,
    guides: [
      { axis: "x", px: 50, from: at("b", "left"), to: at("a", "right") },
      { axis: "y", px: 20, from: at("b", "top"), to: at("a", "bottom") },
    ],
  });
});

test("between: перекриття, де по одній осі b цілком у смузі a", () => {
  /* Обидві межі смуги — краї ОДНОГО прямокутника; форма це витримує, бо кожна
     напрямна називає свої два краї сама. */
  const over = box(120, 230, 60, 60);        // X 120..180 всередині 100..200
  assert.deepEqual(between(pair, over).guides[0],
    { axis: "x", px: 60, from: at("b", "left"), to: at("b", "right") });
});

test("between: вироджений прямокутник у смузі — перекриття, а не зазор 0", () => {
  /* Пастка: спільна смуга по Y тут нульової ТОВЩИНИ (b нульової висоти всередині
     a), але прямокутники таки налізають один на одного — саме цей випадок
     `measure` пропускає як перекриття. Якби ми розрізняли випадки за знаком
     перетину, а не за розділеністю, тут вийшов би брехливий «зазор 0». */
  const flat = box(150, 220, 100, 0);        // Y 220..220 всередині 200..250
  const res = between(pair, flat);
  assert.equal(res.kind, "overlap", "нульова товщина смуги — це не зазор");
  assert.deepEqual(res.guides[1], { axis: "y", px: 0, from: at("b", "top"), to: at("b", "bottom") });
});

test("between: b повністю всередині a — чотири внутрішні відстані", () => {
  /* Випадок 5 брифа й найзвичайніший для цієї фічі: іконка в кнопці. Відповідь
     «нуль» тут була б безглузда — потрібні чотири напрямні до внутрішніх країв,
     у порядку top, right, bottom, left. */
  const button = box(100, 200, 200, 60);     // X 100..300, Y 200..260
  const icon = box(120, 216, 24, 24);        // X 120..144, Y 216..240
  assert.deepEqual(between(button, icon), {
    kind: "inside",
    outer: "a",
    guides: [
      { axis: "y", px: 16, from: at("a", "top"), to: at("b", "top") },
      { axis: "x", px: 156, from: at("b", "right"), to: at("a", "right") },
      { axis: "y", px: 20, from: at("b", "bottom"), to: at("a", "bottom") },
      { axis: "x", px: 20, from: at("a", "left"), to: at("b", "left") },
    ],
  });
});

test("between: внутрішній край, що збігся — 0 усередині, а не 'overlap'", () => {
  const button = box(100, 200, 200, 60);
  const icon = box(100, 216, 24, 24);        // left збігся з лівим краєм кнопки
  const res = between(button, icon);
  assert.equal(res.kind, "inside");
  assert.deepEqual(res.guides[3], { axis: "x", px: 0, from: at("a", "left"), to: at("b", "left") });
});

test("between: вироджений вкладений прямокутник — теж чотири відстані", () => {
  /* Рядок тексту нульової висоти всередині кнопки. `measure` кандидатів
     нульового розміру відкидає (їх не видно), але тут його вибрав дизайнер
     власним кліком — відкидати чужий вибір нема за що. */
  const button = box(100, 200, 200, 60);
  const line = box(120, 230, 60, 0);
  const res = between(button, line);
  assert.equal(res.kind, "inside");
  assert.deepEqual(res.guides.map((g) => g.px), [30, 120, 30, 20]);
});

test("between: однакові прямокутники — вкладення з чотирма нулями", () => {
  /* Кожен містить кожного; роль зовнішнього дістається `a` — правило фіксоване,
     щоб напрямні не стрибали. Числа при цьому нульові з обох боків. */
  const res = between(pair, { ...pair });
  assert.equal(res.kind, "inside");
  assert.equal(res.outer, "a");
  assert.deepEqual(res.guides.map((g) => g.px), [0, 0, 0, 0]);
});

test("between: симетрична за числами, дзеркальна за мітками", () => {
  /* `between(a, b)` і `between(b, a)` мусять давати ТІ САМІ числа й той самий
     порядок напрямних; відрізняються лише мітки прямокутників (`a` ↔ `b`) —
     напрямок вимірювання. */
  const flip = (e) => ({ rect: e.rect === "a" ? "b" : "a", side: e.side });
  const mirror = (r) => ({
    kind: r.kind,
    outer: r.outer === null ? null : r.outer === "a" ? "b" : "a",
    guides: r.guides.map((g) => ({ axis: g.axis, px: g.px, from: flip(g.from), to: flip(g.to) })),
  });
  const layouts = [
    box(120, 300, 60, 40),      // зазор по вертикалі
    box(260, 210, 40, 30),      // зазор по горизонталі
    box(200, 200, 50, 50),      // дотик краями
    box(260, 300, 40, 40),      // діагональ
    box(200, 250, 40, 40),      // дотик кутом
    box(150, 230, 100, 60),     // перекриття
    box(120, 210, 30, 30),      // вкладення
    box(0, 0, 400, 400),        // pair всередині кандидата
  ];
  for (const other of layouts) {
    const straight = between(pair, other);
    assert.deepEqual(mirror(between(other, pair)), straight,
      `${straight.kind}: перестановка аргументів змінила відповідь`);
    for (const g of straight.guides) {
      assert.ok(g.px >= 0, `${straight.kind}/${g.axis}: відʼємних чисел не показуємо`);
    }
  }
});

test("between: a всередині b — зовнішнім названо саме b", () => {
  const res = between(pair, box(0, 0, 400, 400));
  assert.equal(res.kind, "inside");
  assert.equal(res.outer, "b", "роль визначає геометрія, а не порядок аргументів");
  assert.deepEqual(res.guides.map((g) => g.px), [200, 200, 150, 100]);
});

test("between: непридатні прямокутники кидають помилку з назвою", () => {
  /* Той самий охоронець, що в `measure`: краще помилка, яка називає винного, ніж
     напрямна в нікуди — NaN у порівняннях тихо дає false. */
  assert.throws(() => between(null, pair), /перший прямокутник/);
  assert.throws(() => between(pair), /другий прямокутник/);
  assert.throws(() => between(pair, "100,200"), /другий прямокутник/);
  assert.throws(() => between({ ...pair, bottom: NaN }, pair), /перший прямокутник, bottom/);
  assert.throws(() => between(pair, { ...pair, right: 50 }), /другий прямокутник.*вивернут/);
});

test("between: краї збіглися — нічию завжди бере ПЕРШИЙ аргумент", () => {
  /* ЗНАХІДКА про межу симетрії: коли два краї лежать на одній координаті, обидва
     однаково правильно обмежують смугу, і мітка вже не може бути дзеркальною —
     нічия детерміновано дістається першому аргументу. Числа при цьому однакові,
     а детермінізм важливіший за дзеркальність: інакше підпис напрямної стрибав
     би між двома правильними варіантами при кожному перемалюванні. */
  const sameLeft = box(100, 230, 150, 60);   // left 100 === pair.left, налазить знизу
  const straight = between(pair, sameLeft);
  const swapped = between(sameLeft, pair);
  assert.deepEqual(straight.guides[0],
    { axis: "x", px: 100, from: at("a", "left"), to: at("a", "right") });
  assert.deepEqual(swapped.guides[0],
    { axis: "x", px: 100, from: at("a", "left"), to: at("b", "right") },
    "нічия по left і після перестановки називає перший аргумент");
  assert.equal(straight.guides[0].px, swapped.guides[0].px, "числа лишаються ті самі");

  /* Те саме на дальньому краї смуги: збіглися `right`. */
  const sameRight = box(150, 230, 50, 60);   // right 200 === pair.right
  assert.deepEqual(between(pair, sameRight).guides[0],
    { axis: "x", px: 50, from: at("b", "left"), to: at("a", "right") });
});
