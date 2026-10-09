/**
 * Живий тест зʼємки: справжній браузер по справжньому серверу інструмента.
 *
 * Фікстура сторінки навмисно містить три способи зробити брехливий кадр:
 * ліниву картинку (headless не скролиться → не завантажиться), нескінченну
 * анімацію (доказ стабільності ніколи не зійдеться) і поле у фокусі (каретка
 * блимає без анімації). Тест вимагає, щоб кадр вийшов стабільним попри все це.
 */
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { BYTES_FLOOR, MAX_PAGE_H } from "../../bin/shots-shutter.mjs";
import { readManifest } from "../../bin/shots-manifest.mjs";
import { runShoot } from "../../bin/shoot.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* База порту саме цього файлу: `node --test` крутить файли паралельно, і спільна
   база з canvas.test.mjs дала б колізію портів. */
const PORT_BASE = 8790;

const PAGE = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @keyframes spin { to { transform: rotate(360deg) } }
  .spinner { width: 40px; height: 40px; background: #333;
             animation: spin 1s linear infinite }
  body { font: 16px/1.4 sans-serif; margin: 40px; height: 1400px }
  /* Навмисно «неплаский» фон: плоский колір і зайва висота у WebP стискаються
     майже задарма, тому кадр фікстури тримався лише на 13-15% вище BYTES_FLOOR і
     падав під поріг від будь-якої правки markup. Градієнт із дрібним кроком дає
     стабільний запас у кілька разів. */
  .noise { height: 180px; background:
    repeating-linear-gradient(37deg, #e11 0 10px, #18a 10px 20px, #2c3 20px 30px, #fd0 30px 40px) }
</style></head><body>
<h1>${title}</h1>
<div class="spinner"></div>
<div class="noise"></div>
<img loading="lazy" width="120" height="80" alt=""
     src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='80'%3E%3Crect width='120' height='80' fill='%23c00'/%3E%3C/svg%3E">
<input id="q" autofocus value="текст у фокусі">
</body></html>`;

test("зʼємка дає стабільні кадри попри спінер, ліниву картинку й каретку", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
    launch: () => chromium.launch(),
  });

  assert.deepEqual(report.failed, [], `падіння: ${JSON.stringify(report.failed)}`);
  assert.deepEqual(report.shot.sort(), ["holovna", "poshuk"]);

  const manifest = readManifest(it1);
  for (const id of ["holovna", "poshuk"]) {
    const shot = manifest.shots[id];
    assert.equal(shot.stable, true, `${id}: кадр не встояв`);
    assert.equal(shot.w, 1280, `${id}: ширина кадру мусить дорівнювати CARD_W`);
    assert.ok(shot.h > 900, `${id}: сторінка вища за вьюпорт, кадр мусить бути на всю висоту`);
    assert.ok(shot.bytes > BYTES_FLOOR, `${id}: ${shot.bytes} байт — це порожня сторінка`);
    assert.equal(shot.stale, false);
    assert.equal(shot.emptyImages, 0, `${id}: у кадрі дірка замість картинки`);
    assert.ok(shot.pausedMidFlight >= 1, `${id}: нескінченний спінер мусив бути зупинений`);
    const file = path.join(it1, "shots", `${id}.webp`);
    assert.ok(readFileSync(file).length === shot.bytes);
  }
});

/* Макет із анімацією ВХОДУ ПО СКРОЛУ — той самий випадок, що приїхав фідбеком
   03.09.2026. Блок лежить нижче першого екрана і має `opacity:0`, поки
   `IntersectionObserver` не побачить його у вьюпорті. Без проходу скролом
   спостерігач не спрацьовує ніколи: сторінка в headless не скролиться, кадр
   робиться `captureBeyondViewport`, і блок їде в кадр невидимим. */
const PAGE_REVEAL = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body { font: 16px/1.4 sans-serif; margin: 40px }
  .spacer { height: 1200px }
  .noise { height: 180px; background:
    repeating-linear-gradient(37deg, #e11 0 10px, #18a 10px 20px, #2c3 20px 30px, #fd0 30px 40px) }
  .reveal { opacity: 0; transition: opacity .2s linear; height: 300px; padding: 20px;
            background: repeating-linear-gradient(90deg, #444 0 8px, #ccc 8px 16px) }
  .reveal.on { opacity: 1 }
</style></head><body>
<h1>${title}</h1>
<div class="noise"></div>
<div class="spacer"></div>
<div class="reveal"><h2>Блок, що зʼявляється по скролу</h2><p>Текст всередині блока.</p></div>
<script>
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) e.target.classList.add("on");
  }, { threshold: 0.1 });
  for (const el of document.querySelectorAll(".reveal")) io.observe(el);
</script>
</body></html>`;

test("блок, що зʼявляється по скролу, не їде в кадр невидимим", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE_REVEAL, pages: ["holovna"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, now: "03.09.2026 12:00",
    launch: () => chromium.launch(),
  });

  assert.deepEqual(report.failed, [], `падіння: ${JSON.stringify(report.failed)}`);
  const shot = readManifest(it1).shots.holovna;
  assert.ok(shot.scrolled > 0, "затвор мусить пройти сторінку скролом");
  assert.equal(shot.hiddenBlocks, 0, "reveal-блок лишився невидимим у кадрі");
  assert.equal(shot.problem, undefined);
});

test("блок, який так і лишився невидимим, названо вголос", async (t) => {
  /* Протилежний бік тієї самої вимоги: прохід скролом закриває типовий випадок,
     але не всі. Те, що лишилось невидимим ПІСЛЯ нього, мусить бути названим —
     інакше порожнє місце в кадрі виглядає як задум дизайнера. */
  const html = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body { font: 16px/1.4 sans-serif; margin: 40px }
  .noise { height: 400px; background:
    repeating-linear-gradient(37deg, #e11 0 10px, #18a 10px 20px, #2c3 20px 30px, #fd0 30px 40px) }
  .ghost { opacity: 0; height: 300px; padding: 20px }
</style></head><body>
<h1>${title}</h1>
<div class="noise"></div>
<div class="ghost"><h2>Блок без жодного шансу зʼявитись</h2><p>Ані спостерігача, ані анімації.</p></div>
</body></html>`;
  const { dir, it1 } = taskFixture({ html, pages: ["holovna"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, now: "03.09.2026 12:00",
    launch: () => chromium.launch(),
  });

  assert.equal(report.failed.length, 1);
  assert.match(report.failed[0].problem, /невидим/);
  assert.equal(readManifest(it1).shots.holovna.hiddenBlocks, 1);
});

test("спливна підказка з opacity:0 не рахується дірою в кадрі", async (t) => {
  /* Межа правила: діру лишає той, хто ЗАЙМАЄ МІСЦЕ в розкладці. Тултип
     `absolute` місця не займає — сторінка без нього зверстана однаково, і
     тривога тут була б хибною на кожному другому макеті. */
  const html = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body { font: 16px/1.4 sans-serif; margin: 40px }
  .noise { height: 400px; background:
    repeating-linear-gradient(37deg, #e11 0 10px, #18a 10px 20px, #2c3 20px 30px, #fd0 30px 40px) }
  .host { position: relative }
  .tip { position: absolute; top: 0; left: 0; width: 240px; height: 90px;
         opacity: 0; background: #222; color: #fff; padding: 12px }
</style></head><body>
<h1>${title}</h1>
<div class="noise"></div>
<div class="host">Наведи мишу<span class="tip">Підказка, якої зараз не видно</span></div>
</body></html>`;
  const { dir, it1 } = taskFixture({ html, pages: ["holovna"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, now: "03.09.2026 12:00",
    launch: () => chromium.launch(),
  });

  assert.deepEqual(report.failed, [], `падіння: ${JSON.stringify(report.failed)}`);
  assert.equal(readManifest(it1).shots.holovna.hiddenBlocks, 0);
});

test("нащадок прихованої підказки (visibility успадковується) не рахується дірою (fb-30092026-7bbc33)", async (t) => {
  /* `opacity` не успадковується, а `visibility` — так: static-список усередині
     absolute-підказки з visibility:hidden сам «невидимий і в потоці» — у потоці
     ПІДКАЗКИ, а не сторінки. Діри сторінці він не лишає. */
  const html = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body { font: 16px/1.4 sans-serif; margin: 40px }
  .noise { height: 400px; background:
    repeating-linear-gradient(37deg, #e11 0 10px, #18a 10px 20px, #2c3 20px 30px, #fd0 30px 40px) }
  .host { position: relative }
  .tip { position: absolute; top: 0; left: 0; width: 260px; visibility: hidden;
         background: #222; color: #fff }
  .tip ul { margin: 0; padding: 12px 24px; height: 70px }
</style></head><body>
<h1>${title}</h1>
<div class="noise"></div>
<div class="host">Наведи мишу<div class="tip"><ul><li>Пункт один</li><li>Пункт два</li></ul></div></div>
</body></html>`;
  const { dir, it1 } = taskFixture({ html, pages: ["holovna"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, now: "02.10.2026 12:00",
    launch: () => chromium.launch(),
  });

  assert.deepEqual(report.failed, [], `падіння: ${JSON.stringify(report.failed)}`);
  assert.equal(readManifest(it1).shots.holovna.hiddenBlocks, 0);
});

test("сторінка без теки не стає кадром сторінки помилки", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  // Сторінка числиться в дереві, а теки немає — сервер віддасть 404, і без
  // перевірки статусу канвас отримав би «успішний» кадр сторінки помилки.
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: "Головна", published: true },
            { id: "poshuk", name: "Пошук", published: true },
            { id: "zniknula", name: "Зникла", published: true }],
  }));
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
    launch: () => chromium.launch(),
  });

  assert.deepEqual(report.shot.sort(), ["holovna", "poshuk"]);
  assert.equal(report.failed.length, 1);
  assert.equal(report.failed[0].id, "zniknula");
  assert.match(report.failed[0].problem, /404/);
  // Ні кадру на диску, ні запису в манифесті — канвас мусить сказати «немає знімка»
  assert.equal(existsSync(path.join(it1, "shots", "zniknula.webp")), false);
  assert.equal("zniknula" in readManifest(it1).shots, false);
});

test("другий прогін без правок не знімає нічого", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const opts = { dir: it1, it: "it1", url, now: "24.08.2026 12:00", launch: () => chromium.launch() };
  await runShoot({ ...opts, all: true });
  const again = await runShoot(opts);
  assert.deepEqual(again.shot, []);
  assert.deepEqual(again.left.sort(), ["holovna", "poshuk"]);
});

test("правка сторінки вибирає саму її, а не всі", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const opts = { dir: it1, it: "it1", url, now: "24.08.2026 12:00", launch: () => chromium.launch() };
  await runShoot({ ...opts, all: true });
  writeFileSync(path.join(it1, "poshuk", "index.html"), PAGE("Пошук v2"));
  const again = await runShoot(opts);
  assert.deepEqual(again.shot, ["poshuk"]);
  assert.deepEqual(again.left, ["holovna"]);
});

/* Окрема висока сторінка, а не правка PAGE(): три кейси вище тримаються рівно на
   висоті 1400px, і роздування її до 9000 зламало б їхні числа (наприклад
   `shot.h > 900` там і так проходить, але сенс тесту — саме звичайна висота). */
const TALL_PAGE = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body { font: 16px/1.4 sans-serif; margin: 40px; height: 9000px }</style>
</head><body><h1>${title}</h1></body></html>`;

/** Ітерація з однією сторінкою вищою за MAX_PAGE_H і однією звичайної висоти. */
function tallFixture() {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-live-tall-"));
  const it1 = path.join(dir, "iterations", "it1");
  mkdirSync(path.join(it1, "dovga"), { recursive: true });
  writeFileSync(path.join(it1, "dovga", "index.html"), TALL_PAGE("Довга"));
  mkdirSync(path.join(it1, "korotka"), { recursive: true });
  writeFileSync(path.join(it1, "korotka", "index.html"), PAGE("Коротка"));
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({
    pages: [{ id: "dovga", name: "Довга", published: true },
            { id: "korotka", name: "Коротка", published: true }],
  }));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [{ id: "it1", date: "24.08.2026 12:00", note: "фікстура", published: true }],
  }));
  return { dir, it1 };
}

test("сторінка вища за стелю позначена truncated, звичайна — ні", async (t) => {
  const { dir, it1 } = tallFixture();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
    launch: () => chromium.launch(),
  });

  assert.deepEqual(report.failed, [], `падіння: ${JSON.stringify(report.failed)}`);
  assert.deepEqual(report.shot.sort(), ["dovga", "korotka"]);

  const manifest = readManifest(it1);
  const tall = manifest.shots.dovga;
  assert.equal(tall.truncated, true, "сторінка вища за MAX_PAGE_H мусить бути позначена truncated");
  assert.equal(tall.h, MAX_PAGE_H, "кадр обрізаний рівно по стелі");
  assert.ok(tall.fullHeight > tall.h, `fullHeight (${tall.fullHeight}) мусить бути більшим за обрізаний h (${tall.h})`);

  const short = manifest.shots.korotka;
  assert.equal(short.truncated, false, "звичайна сторінка не мусить нести прапорець truncated");
  assert.equal(short.fullHeight, short.h, "без обрізання fullHeight і h — те саме число");
});

/* `holovna` навмисно занадто порожня для BYTES_FLOOR — крапка, а не зовсім
   `<body></body>`, бо `settle()` вимагає непорожній innerText АБО картинку,
   інакше чекав би усі 45с на `neverSettled` і ми довели б неправильну гілку
   `problem`. `poshuk` лишається звичайною (PAGE) — контроль, без якого тест не
   відрізнив би «перезняли саме битий кадр» від «перезняли взагалі все». */
const BROKEN_PAGE = `<!DOCTYPE html><html><body>.</body></html>`;

test("зіпсований кадр перезнімається сам — без --all і без правки файлів", async (t) => {
  const { dir, it1 } = taskFixture({
    html: (page) => (page === "holovna" ? BROKEN_PAGE : PAGE(page)),
  });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const opts = { dir: it1, it: "it1", url, now: "24.08.2026 12:00", launch: () => chromium.launch() };

  // 1. `--all` знімає обидві. `holovna` виходить биткою — запис у манифесті
  //    зі свіжим штампом і `problem`. Це доводить ПЕРШУ половину коміту: `problem`
  //    справді потрапляє в манифест зі справжнього прогону зʼємки, а не лише в
  //    ручний обʼєкт юніт-теста.
  const first = await runShoot({ ...opts, all: true });
  assert.deepEqual(first.shot.sort(), ["poshuk"]);
  assert.deepEqual(first.failed.map((f) => f.id), ["holovna"]);
  const brokenAfterFirst = readManifest(it1).shots.holovna;
  assert.match(brokenAfterFirst.problem, /порожня сторінка/);
  const stampAfterFirst = brokenAfterFirst.stamp;

  // 2. НЕСУЧИЙ КРОК. Другий прогін БЕЗ `--all`, файли сторінок НЕ чіпаємо —
  //    штамп `holovna` лишається той самий, що й після кроку 1. Якщо `problem`
  //    не робить запис застарілим ЗА ПОБУДОВОЮ (рівно дефект, який лікує цей
  //    коміт), `staleIds` мовчки погодиться зі свіжим штампом, і `holovna`
  //    піде в `left` — туди, де биті кадри лежали НАЗАВЖДИ до цього фікса.
  const second = await runShoot(opts);
  assert.equal(second.left.includes("holovna"), false,
    "битий кадр мусив піти в роботу знову, а не лишитись «начебто актуальним»");
  assert.equal(second.left.includes("poshuk"), true,
    "справний кадр удруге перезнімати не було причин — джерела не змінювались");
  assert.deepEqual(second.failed.map((f) => f.id), ["holovna"]);
  assert.equal(readManifest(it1).shots.holovna.stamp, stampAfterFirst,
    "джерела сторінки не мінялись — у роботу взяв саме `problem`, не розбіжність штампів");

  // 3. Полагодили сторінку — `problem` мусить ЗНИКНУТИ з запису, а не лишитись
  //    поряд зі свіжим `stale: false`: інакше бейдж на канвасі й далі носив би
  //    стару причину після того, як дизайнер її вже виправив.
  writeFileSync(path.join(it1, "holovna", "index.html"), PAGE("Головна (полагоджено)"));
  const third = await runShoot(opts);
  assert.deepEqual(third.shot, ["holovna"]);
  assert.equal("problem" in readManifest(it1).shots.holovna, false);
});

/* --- рух, якого `getAnimations()` не бачить: rAF-цикл --- */

/**
 * Сторінка з рухом на `requestAnimationFrame` — і з повагою до
 * `prefers-reduced-motion`, рівно як написані живі макети.
 *
 * ⛔ Чому не CSS-анімація: нескінченні WAAPI-анімації `settle()` вже ставить на
 * паузу (`pausedMidFlight`), тобто вони цієї дірки не показують. Болить саме
 * те, чого `document.getAnimations()` не бачить узагалі — GL-ефект чи
 * rAF-цикл: два знімки поспіль ФІЗИЧНО не можуть збігтися, кадр завжди виходить
 * `stable:false`, дістає `problem`, а запис із `problem` застарілий за
 * побудовою. Тобто кожен кадр макета з постійним рухом позначений
 * недостовірним НАЗАВЖДИ, і дизайнер перестає вірити бейджам (bf360, hero з GL).
 *
 * ⛔ Прапорець не «зупиняє рух» сам по собі — він ПИТАЄ сторінку. Зупиняється
 * лише та, що медіа-запит поважає. Тому фікстура його поважає: це той самий
 * контракт, який має живий макет, а не вигадана зручність.
 */
const PAGE_RAF = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body { font: 16px/1.4 sans-serif; margin: 40px; height: 1400px }
  .noise { height: 180px; background:
    repeating-linear-gradient(37deg, #e11 0 10px, #18a 10px 20px, #2c3 20px 30px, #fd0 30px 40px) }
</style></head><body>
<h1>${title}</h1>
<div class="noise"></div>
<canvas id="c" width="300" height="120"></canvas>
<script>
  const ctx = document.getElementById('c').getContext('2d');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let i = 0;
  function draw() {
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 300, 120);
    ctx.fillStyle = '#333'; ctx.fillRect((i % 260), 20, 40, 80);
    if (!still) { i += 7; requestAnimationFrame(draw); }
  }
  draw();
</script>
</body></html>`;

test("рух на rAF не робить кожен кадр недостовірним", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE_RAF, pages: ["holovna"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40 });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
    launch: () => chromium.launch(),
  });
  assert.deepEqual(report.failed, [], `падіння: ${JSON.stringify(report.failed)}`);
  const shot = readManifest(it1).shots.holovna;
  assert.equal(shot.stable, true, "кадр і далі не встояв — рух не зупинився");
  assert.equal(shot.problem, undefined, `кадр помічений проблемним: ${shot.problem}`);
  assert.equal(shot.stale, false);
});

test("`motion` знімає саме рух — і тоді кадр чесно не встоює", async (t) => {
  /* Зворотний бік: прапорець мусить бути ВИМИКАЧЕМ, а не написом. Без цієї
     половини реалізація «завжди reduce, параметр ігноруємо» виглядала б як
     успіх — і зняти анімацію, коли її й треба показати, стало б неможливо. */
  const { dir, it1 } = taskFixture({ html: PAGE_RAF, pages: ["holovna"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 60 });
  t.after(() => child.kill());

  const report = await runShoot({
    dir: it1, it: "it1", url, all: true, motion: true, now: "24.08.2026 12:00",
    launch: () => chromium.launch(),
  });
  const shot = readManifest(it1).shots.holovna;
  assert.equal(shot.stable, false, "з рухом кадр не міг би встояти — фікстура не рухається");
  assert.equal(report.failed.length, 1, `звіт мовчить про нестійкий кадр: ${JSON.stringify(report)}`);
});
