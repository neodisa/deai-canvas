import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { shotKey, shotVersion } from "../app/flow-model.js";
import { CANVAS_PRESETS, CANVAS_W, frameKey } from "../app/viewport.js";
import { readManifest, shotSha, writeManifest } from "../bin/shots-manifest.mjs";
import { PROGRESS_MARK } from "../bin/shots-progress.mjs";
import { VIEWPORT, viewportFor } from "../bin/shots-shutter.mjs";
import { nodeList, runCheck, runShoot, stampTime, stampsFor } from "../bin/shoot.mjs";
import { GEO_VERSION } from "../bin/shots-geo.mjs";

/* Свіжий кадр після T-45 — це штамп, що збігся, І геометрія поточної версії:
   кадр без неї йде в перезйомку тихо (`geoMissingIds`). Фікстури «кадр уже
   знято й свіжий» несуть її, інакше описували б стан, якого інструмент більше
   не вважає свіжим. */
const GEO_OK = { v: GEO_VERSION, n: 1 };

const NOW = "24.08.2026 12:00";

/** Ітерація з двома сторінками й однією групою-організатором. */
function iterFixture() {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-shoot-"));
  for (const page of ["holovna", "poshuk"]) {
    mkdirSync(path.join(dir, page));
    writeFileSync(path.join(dir, page, "index.html"), `<h1>${page}</h1>`);
  }
  mkdirSync(path.join(dir, "shared"));
  writeFileSync(path.join(dir, "shared", "header.html"), "<header/>");
  return dir;
}

/**
 * Файли кадрів на диску.
 *
 * Відколи зниклий `.webp` робить кадр застарілим (`dropMissingShots` у
 * `bin/shoot.mjs`), фікстура, що пише лише ЗАПИСИ манифеста, описувала б стан,
 * якого в житті не буває: запис зʼявляється разом із файлом і тільки разом із
 * ним. Тому фікстури, яким потрібен «кадр уже знято», кладуть і файл.
 */
function touchShots(dir, ids) {
  mkdirSync(path.join(dir, "shots"), { recursive: true });
  for (const id of ids) writeFileSync(path.join(dir, "shots", `${id}.webp`), "байти");
}

const PAGES = {
  pages: [
    { id: "holovna", name: "Головна" },
    { id: "grupa", name: "Розділ", isGroup: true,
      children: [{ id: "poshuk", name: "Пошук" }] },
  ],
};

const fakeFetch = async () => PAGES;

test("тека за kind (без isGroup) теж не знімається, а діти — так", async () => {
  const pages = { pages: [
    { id: "holovna", name: "Головна" },
    { id: "grupa", name: "Розділ", kind: "folder",
      children: [{ id: "poshuk", name: "Пошук", kind: "page" }] }] };
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: async () => pages });
  assert.deepEqual(nodes.map((n) => n.key), ["holovna", "poshuk"]);
});

test("перелік вузлів пропускає групи-організатори й тримає порядок дерева", async () => {
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  assert.deepEqual(nodes.map((n) => n.key), ["holovna", "poshuk"]);
});

test("легасі-дитина (без kind) теки-isGroup знімається — kind іде вглиб обходу", async () => {
  const pages = { pages: [{ id: "grupa", name: "Р", isGroup: true,
    children: [{ id: "a", name: "A", children: [{ id: "b", name: "B" }] }] }] };
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: async () => pages });
  assert.deepEqual(nodes.map((n) => n.key), ["a", "b"]);
});

test("неявна main має порожній rel, звичайна сторінка — свій", async () => {
  const { nodes } = await nodeList({
    url: "http://x", it: "it1",
    fetchJson: async () => ({ pages: [{ id: "main", name: "Головна" }] }),
  });
  assert.equal(nodes[0].rel, "");
});

test("check пише stale у манифест і повертає перелік", async () => {
  const dir = iterFixture();
  const first = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(first.stale.sort(), ["holovna", "poshuk"]);
  assert.equal(readManifest(dir).checkedAt, NOW);
});

test("check на ще не знятій ітерації не створює записів, лише звітує", async () => {
  const dir = iterFixture();
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(report.stale.sort(), ["holovna", "poshuk"]);
  // Записів немає й бути не мусить: кадр з'явиться разом зі знімком, а не з перевіркою.
  assert.deepEqual(readManifest(dir).shots, {});
  assert.equal(readManifest(dir).checkedAt, NOW);
});

test("check не бачить застарілих, коли штампи збігаються", async () => {
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  touchShots(dir, nodes.map((n) => n.key));
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key] }])),
  });
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(report.stale, []);
});

test("порожній перелік сторінок — відмова, а не порожній манифест", async () => {
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key], w: 1280, h: 1400 }])),
  });
  await assert.rejects(
    () => runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: async () => ({ pages: [] }) }),
    /жодної сторінки/,
  );
  // Найважливіше: наявні записи манифеста мусили лишитись на місці
  assert.equal(Object.keys(readManifest(dir).shots).length, 2);
});

test("правка у shared робить застарілими обидві сторінки", async () => {
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key] }])),
  });
  writeFileSync(path.join(dir, "shared", "header.html"), "<header>v2</header>");
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(report.stale.sort(), ["holovna", "poshuk"]);
});

test("правка спільного файла в КОРЕНІ ітерації робить застарілими підсторінки", async () => {
  /* `landing.css` у корені ітерації підключають усі сторінки через `../`. У
     штамп він входив ЛИШЕ для неявної `main` (для неї тека сторінки і є
     корінь), тому правка спільного стилю не робила підсторінки застарілими:
     вони виглядають інакше, а помічені свіжими — «Огляд» показував старі кадри
     як актуальні. Знайдено живцем на bf360 (флоу-сторінки після правок
     landing.css і visual.css). */
  const dir = iterFixture();
  writeFileSync(path.join(dir, "landing.css"), "body{color:#000}");
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key] }])),
  });
  writeFileSync(path.join(dir, "landing.css"), "body{color:#fff}");
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(report.stale.sort(), ["holovna", "poshuk"]);
});

test("тека однієї сторінки не чіпає штамп іншої", async () => {
  /* Зворотний бік попереднього: корінь у штампі не сміє злити всі сторінки в
     одну. Без цієї половини найпростіша «правка» (рекурсивний корінь) виглядала
     б як успіх, а насправді робила б кожен прогін повним назавжди. */
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  touchShots(dir, nodes.map((n) => n.key));
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key] }])),
  });
  writeFileSync(path.join(dir, "poshuk", "index.html"), "<h1>poshuk v2</h1>");
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(report.stale, ["poshuk"]);
});

test("зниклий файл кадру робить кадр застарілим, а не «знятим»", async () => {
  /* Свіжість рахувалась ВИКЛЮЧНО по манифесту, диск не питали взагалі. Тому
     видалити `.webp` було не досить, щоб сторінку зняли заново: запис зі
     збіжним штампом лишався, кадр вважався знятим, файла не було. Ловили
     живцем на bf360 — флоу-сторінки не переснімались, поки записи не прибрали
     з манифеста руками. */
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  mkdirSync(path.join(dir, "shots"), { recursive: true });
  writeFileSync(path.join(dir, "shots", "holovna.webp"), "байти");
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key], w: 1280, h: 900 }])),
  });
  // `poshuk.webp` на диск не клали — саме цей кадр мусить стати застарілим.
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(report.stale, ["poshuk"]);
  /* І запис іде геть: він описував файл, якого немає. Лишити його означало б
     сказати канвасу «знімок є» про те, чого на диску нема. */
  assert.deepEqual(Object.keys(readManifest(dir).shots), ["holovna"]);
});

test("кадр, чий файл на місці, зниклим не рахується", async () => {
  /* Свідок проти найпростішої «правки» — оголосити застарілим усе підряд. */
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  mkdirSync(path.join(dir, "shots"), { recursive: true });
  for (const n of nodes) writeFileSync(path.join(dir, "shots", `${n.key}.webp`), "байти");
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key], w: 1280, h: 900 }])),
  });
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(report.stale, []);
  assert.equal(Object.keys(readManifest(dir).shots).length, 2);
});

test("звіт зʼємки називає ширину прогону — мовчання читалось як «решта свіжа»", async () => {
  /* Прогін знімає ОДНУ ширину, а `left` перелічує кадри лише цієї ж ширини.
     Тобто кадри 390 і 768 після `{all:true}` без `vp` лишаються застарілими —
     законно, але зі звіту цього не видно взагалі, і виглядає воно як «зняли
     все». Саме так і прочитали на courts: пʼять кадрів свіжі, пʼять @390
     застарілі, звіт без жодного слова про ширину. */
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  touchShots(dir, nodes.map((n) => n.key));
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key] }])),
  });
  const launch = () => { throw new Error("браузер не мав запускатись"); };
  const report = await runShoot({ dir, it: "it1", url: "http://x", now: NOW,
                                  fetchJson: fakeFetch, launch });
  assert.equal(report.vp, CANVAS_W, "звіт не каже, якою шириною знімали");
});

/* --- нетипові ширини: манифест не сміє їх зʼїдати --- */

test("stampsFor роздає ключі і для ширини поза пресетами, коли її просять", () => {
  const dir = iterFixture();
  const nodes = [{ key: "holovna", page: "holovna", name: "Головна", rel: "holovna", query: "" }];
  const stamps = stampsFor(dir, nodes, [CANVAS_W, 1920]);
  assert.ok("holovna" in stamps, "типова ширина зникла");
  assert.ok("holovna@1920" in stamps, "ширина поза пресетами не отримала ключа");
  // Штамп у всіх ширин той самий: ширина не міняє файлів сторінки.
  assert.equal(stamps["holovna@1920"], stamps.holovna);
});

test("кадр нетипової ширини переживає перевірку, а не зникає з манифеста", async () => {
  /* Доказ із живого прогону (courts/it6): `POST /api/shoot {vp:1920}` клав
     пʼять `*@1920.webp` на диск, а в манифесті ключів @1920 не зʼявлялось
     ВЗАГАЛІ. Механізм: `stampsFor` роздавав ключі лише по `CANVAS_PRESETS`,
     а `markStale` за контрактом викидає кожен запис, чийого id немає в
     `stamps`. Далі стан не самолікувався: `staleIds` перебирає ключі `stamps`,
     тобто @1920 не міг застаріти ніколи, і повторний прогін звітував
     `shot:[]`. */
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes, [CANVAS_W, 1920]);
  touchShots(dir, nodes.map((n) => `${n.key}@1920`));
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [`${n.key}@1920`,
      { geo: GEO_OK, stamp: stamps[`${n.key}@1920`], w: 1920, h: 900 }])),
  });
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW,
                                 fetchJson: fakeFetch, vp: 1920 });
  const shots = readManifest(dir).shots;
  assert.deepEqual(Object.keys(shots).sort(), ["holovna@1920", "poshuk@1920"]);
  assert.deepEqual(report.stale, [], "свіжий кадр 1920 порахований застарілим");
});

test("ширина з манифеста переживає прогін ІНШОЇ ширини", async () => {
  /* Те саме, але з боку сусіда: знімаємо типову, а на диску вже лежать кадри
     1920 з попереднього прогону. Без «ширин, які вже є в манифесті» вони
     зникли б метаданими саме тоді, коли з ними все гаразд. */
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes, [CANVAS_W, 1920]);
  touchShots(dir, ["holovna", "holovna@1920"]);
  writeManifest(dir, {
    checkedAt: null,
    shots: {
      holovna: { geo: GEO_OK, stamp: stamps.holovna },
      "holovna@1920": { geo: GEO_OK, stamp: stamps["holovna@1920"], w: 1920, h: 900 },
    },
  });
  await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.ok("holovna@1920" in readManifest(dir).shots,
    "кадр 1920 зник із манифеста після прогону типової ширини");
});

test("кадри зниклої сторінки й далі прибираються — у ВСІХ ширинах", async () => {
  /* Передумова `markStale` лишається живою під НОВИМ набором ширин: запис
     викидається за ключем кадру цілком, тож сторінка, якої вже немає, зникає
     в усіх ширинах. ⚠️ Цей тест НЕ доводить звуження `widthsFor` до поточних
     вузлів — мутація «брати ширини з будь-якого запису» його не валить, бо
     ключ зниклої сторінки однаково відсутній у `stamps`. Звуження там —
     економія, і воно чесно так і підписане. */
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes, [CANVAS_W, 1920]);
  writeManifest(dir, {
    checkedAt: null,
    shots: {
      holovna: { geo: GEO_OK, stamp: stamps.holovna },
      "zniкла@1920": { stamp: "старий", w: 1920, h: 900 },
      zniкла: { stamp: "старий" },
    },
  });
  await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  const shots = readManifest(dir).shots;
  assert.ok(!("zniкла" in shots) && !("zniкла@1920" in shots),
    `кадри зниклої сторінки лишились у манифесті: ${Object.keys(shots).join(", ")}`);
});

/* --- ключ кадру мусить мінятись від САМОЇ перезйомки (блокер C2) --- */

/**
 * Підроблений браузер, який віддає РІВНО задані байти.
 *
 * Тут він потрібен саме тому, що справжній Chromium на незмінному макеті дає
 * ті самі байти — а перевіряємо ми протилежний випадок: сторінка намалювалась
 * ІНАКШЕ (перший кадр вийшов битим), тоді як файли макета не мінялись. Живий
 * тест такого не влаштує з розумною надійністю, а без нього залишався б
 * непокритим основний цикл: «Перезняти» → битий кадр → «Перезняти» ще раз.
 *
 * `waitForTimeout` — no-op: тест міряє ключі, а не затвор, і 1.6 секунди
 * очікування на кожен кадр тут були б платою ні за що. Усі `evaluate` віддають
 * 0: `scrollHeight` 0 дає висоту вьюпорта, зупинених анімацій нуль, дірок у
 * картинках нуль — тобто кадр без жодного `problem`.
 */
function fakeBrowser(buf) {
  const page = {
    goto: async () => ({ ok: () => true, status: () => 200 }),
    evaluate: async () => 0,
    waitForTimeout: async () => {},
    waitForFunction: async () => {},
    addStyleTag: async () => {},
    close: async () => {},
    // Ті самі байти на кожен затвор: інакше `shootStable` не зійде двічі підряд
    // і кадр приїхав би з `stable: false`.
    context: () => ({
      newCDPSession: async () => ({
        send: async () => ({ data: buf.toString("base64") }),
        detach: async () => {},
      }),
    }),
  };
  return { newPage: async () => page, close: async () => {} };
}

test("дві зʼємки поспіль із різними байтами дають РІЗНІ ключі кадру", async () => {
  const dir = iterFixture();
  /* Час беремо ТАК САМО, як CLI (`const now = stampTime()`), і НЕ підставляємо
     руками. У цьому весь сенс: `stampTime` має точність до ХВИЛИНИ, тож два
     прогони поспіль отримують ОДНАКОВИЙ `capturedAt` — виміряно,
     `stampTime(16:30:05) === stampTime(16:30:58)`. Живий тест K2 підставляв
     `now` руками й тому цю дірку не бачив за побудовою. */
  const shoot = (buf) => runShoot({
    dir, it: "it1", url: "http://x", all: true, now: stampTime(),
    fetchJson: fakeFetch, launch: () => fakeBrowser(buf),
  });

  // 8000 байт — вище BYTES_FLOOR, інакше кадр приїхав би з `problem`.
  await shoot(Buffer.alloc(8000, 0x61));
  const first = readManifest(dir).shots.holovna;
  await shoot(Buffer.alloc(8000, 0x62));
  const second = readManifest(dir).shots.holovna;

  // Передумова: це саме «перезняти те саме», а не «змінився макет».
  assert.equal(second.stamp, first.stamp, "файли сторінки не мінялись — штамп той самий");
  assert.notEqual(second.sha, first.sha, "байти кадру мусили розійтись");
  assert.notEqual(shotVersion(second), shotVersion(first));

  /* І ще раз — із ПРИРІВНЯНОЮ хвилиною. Не для краси: два прогони можуть лягти
     по різні боки межі хвилини, і тоді ключі розійшлись би самі, а тест ловив
     би баг лише інколи. Прирівняли годинник — і вимагаємо, щоб ключі розійшлись
     БЕЗ його допомоги. Мутація «повернути хвилинну точність» (прибрати `sha` з
     ключа) валить саме цей рядок завжди. */
  assert.notEqual(shotVersion({ ...second, capturedAt: first.capturedAt }),
                  shotVersion(first),
                  "ключ кадру не сміє триматись на годиннику: дві зйомки в одну "
                  + "хвилину з різними байтами дали б однаковий URL, а /shot "
                  + "віддається з immutable на рік");

  // Ключ мусить описувати саме те, що віддає `/shot` — файл на диску.
  assert.equal(shotSha(readFileSync(path.join(dir, "shots", "holovna.webp"))),
               second.sha, "`sha` в манифесті мусить бути хешем самого .webp");
});

test("перезйомка з тими самими байтами лишає ключ тим самим", async () => {
  /* Зворотний бік того самого твердження, і він не косметичний: ключ, що
     міняється від КОЖНОГО прогону, викидав би з вічного кешу цілий екран
     кадрів на кожну інкрементальну зʼємку. Саме тому в ключі хеш байтів, а не
     мітка часу з секундами. */
  const dir = iterFixture();
  const shoot = () => runShoot({
    dir, it: "it1", url: "http://x", all: true, now: stampTime(),
    fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(8000, 0x61)),
  });
  await shoot();
  const first = readManifest(dir).shots.holovna;
  await shoot();
  const second = readManifest(dir).shots.holovna;
  assert.equal(shotVersion({ ...second, capturedAt: first.capturedAt }),
               shotVersion(first));
});

test("запис без `sha` (манифест до фікса) лишається з робочим старим ключем", async () => {
  /* Старі манифести пережити мусимо без порожніх ключів: кадр, знятий до появи
     `sha`, ще носить лише штамп і хвилину. Перша ж перезйомка додасть `sha` —
     ключ зміниться сам, і кадр довантажиться. */
  assert.equal(shotVersion({ stamp: "s1", capturedAt: NOW }), `s1.${NOW}.`);
  assert.notEqual(shotVersion({ stamp: "s1", capturedAt: NOW, sha: "abc" }),
                  shotVersion({ stamp: "s1", capturedAt: NOW }));
});

test("зʼємка з невідомим --only падає, а не мовчить успіхом", async () => {
  const dir = iterFixture();
  // launch не мусить бути покликаний узагалі: перевірка стоїть до браузера
  const launch = () => { throw new Error("браузер не мав запускатись"); };
  await assert.rejects(
    () => runShoot({ dir, it: "it1", url: "http://x", only: ["nemaje"], now: NOW,
                     fetchJson: fakeFetch, launch }),
    /немає такого кадру — nemaje/,
  );
});

test("зʼємка на порожньому переліку сторінок падає, а не віддає порожній звіт", async () => {
  const dir = iterFixture();
  const launch = () => { throw new Error("браузер не мав запускатись"); };
  await assert.rejects(
    () => runShoot({ dir, it: "it9", url: "http://x", all: true, now: NOW,
                     fetchJson: async () => ({ pages: [] }), launch }),
    /жодної сторінки/,
  );
});

test("CLI --check справді працює запущений як команда", async () => {
  const dir = iterFixture();
  const server = createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    // Граф з опискою — щоб перевірити, що скарга переживає межу процесу й JSON.
    // Саме цим шляхом вона доходить до serve.py і до тоста в канвасі.
    res.end(JSON.stringify(req.url.includes("/api/flow")
      ? { flow: { flows: [{ id: "f", nodes: [{ id: "n1", page: "poshuk2" }], edges: [] }] } }
      : PAGES));
  });
  await new Promise((ready) => server.listen(0, "127.0.0.1", ready));
  const url = `http://127.0.0.1:${server.address().port}`;
  try {
    const cli = fileURLToPath(new URL("../bin/shoot.mjs", import.meta.url));
    /* НЕ spawnSync: він блокує event loop БАТЬКІВСЬКОГО процесу синхронно, а сервер
       вище живе в цьому ж процесі. Дочірній CLI чекає відповідь від сервера — сервер
       не може відповісти, доки spawnSync не поверне керування, а spawnSync не
       поверне керування, доки дочірній процес не завершиться. Класичний дедлок,
       підтверджений окремим прогоном: spawnSync висів, доки не спрацював зовнішній
       timeout. `spawn` — асинхронний, лишає event loop батька живим, і сервер встигає
       відповісти. */
    const child = spawn(process.execPath, [cli, "--dir", dir, "--it", "it1",
                                           "--url", url, "--check", "--json"]);
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    const status = await new Promise((resolve, reject) => {
      child.on("error", reject);
      child.on("close", resolve);
    });
    assert.equal(status, 0, stderr);
    // Головне: stdout НЕ порожній. Тихий no-op із кодом 0 — це той дефект,
    // проти якого цей тест існує.
    const report = JSON.parse(stdout);
    assert.equal(report.nodes, 2);
    assert.deepEqual(report.stale.sort(), ["holovna", "poshuk"]);
    assert.equal(readManifest(dir).checkedAt.length > 0, true);
    // Скарга на flow.json мусить бути В JSON, а не лише в пам'яті процесу.
    assert.equal(report.problems.length, 1, `problems: ${JSON.stringify(report.problems)}`);
    assert.match(report.problems[0], /poshuk2/);
    // І код виходу лишається 0: сторінки знялись, це попередження (перевірено вище).
  } finally {
    server.close();
  }
});

test("цілі зʼємки = сторінки ПЛЮС стани з flow.json", async () => {
  const flow = { flows: [{ id: "f", nodes: [
    { id: "n1", page: "poshuk" },
    { id: "n2", page: "poshuk", state: { state: "empty" } },
  ], edges: [] }] };
  const { nodes } = await nodeList({
    url: "http://x", it: "it1",
    fetchJson: async (u) => (u.includes("iteration-pages")
      ? { pages: [{ id: "holovna", name: "Головна" }, { id: "poshuk", name: "Пошук" }] }
      : { flow }),
  });
  assert.deepEqual(nodes.map((n) => n.key), ["holovna", "poshuk", shotKey("poshuk", { state: "empty" })]);
  const state = nodes.find((n) => n.key !== n.page);
  assert.equal(state.page, "poshuk", "стан знімає ту саму сторінку");
  assert.equal(state.query, "&state=empty");
});

test("стан ділить штамп зі своєю сторінкою: файли ті самі", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-stamp-"));
  mkdirSync(path.join(dir, "poshuk"), { recursive: true });
  writeFileSync(path.join(dir, "poshuk", "index.html"), "<h1>п</h1>");
  const stamps = stampsFor(dir, [
    { key: "poshuk", page: "poshuk", rel: "poshuk" },
    { key: "poshuk~deadbeef", page: "poshuk", rel: "poshuk" },
  ]);
  /* Спершу штамп мусить БУТИ. Без цього рядка тест зелений і на старому коді:
     той ключує по `node.id`, якого в цілі зʼємки вже немає, тож обидва пошуки
     дають undefined, і `undefined === undefined` проходить. Порожня рівність —
     не доказ спільного штампу. */
  assert.match(stamps["poshuk"], /^[0-9a-f]{16}$/, "штамп сторінки мусить бути порахований");
  assert.equal(stamps["poshuk"], stamps["poshuk~deadbeef"]);
});

test("неявна main і в стані рахує лише корінь, а не теки сусідніх сторінок", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-stamp-main-"));
  writeFileSync(path.join(dir, "index.html"), "<h1>головна</h1>");
  const nodes = [{ key: "main", page: "main", rel: "" }];
  const before = stampsFor(dir, nodes)["main"];
  // Сусідня сторінка — окрема тека в корені ітерації. Штамп main її не бачить:
  // інакше правка будь-якої сторінки перезнімала б головну.
  mkdirSync(path.join(dir, "susid"), { recursive: true });
  writeFileSync(path.join(dir, "susid", "index.html"), "<h1>сусід</h1>");
  assert.equal(stampsFor(dir, nodes)["main"], before);
});

test("немає flow.json — цілі це просто сторінки, без жодної помилки", async () => {
  const { nodes } = await nodeList({
    url: "http://x", it: "it1",
    fetchJson: async (u) => (u.includes("iteration-pages")
      ? { pages: [{ id: "holovna", name: "Головна" }] }
      : { flow: null }),
  });
  assert.deepEqual(nodes.map((n) => n.key), ["holovna"]);
});

/** Ітерація з описками у flow.json: вузол на неіснуючу сторінку. */
const FLOW_Z_OPYSKOJU = { flows: [{ id: "f", nodes: [
  { id: "n1", page: "poshuk2" },
], edges: [] }] };
const fetchWithFlow = (flow) => async (u) => (u.includes("iteration-pages") ? PAGES : { flow });

test("описка у flow.json доходить до звіту check, а не гине мовчки", async () => {
  const dir = iterFixture();
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW,
                                  fetchJson: fetchWithFlow(FLOW_Z_OPYSKOJU) });
  assert.equal(report.problems.length, 1, `problems: ${JSON.stringify(report.problems)}`);
  assert.match(report.problems[0], /n1/, "у скарзі мусить бути назва вузла");
  assert.match(report.problems[0], /poshuk2/, "і назва сторінки, якої немає");
  // Кадри при цьому цілі: описка в графі не сміє з'їдати сторінки ітерації
  assert.deepEqual(report.stale.sort(), ["holovna", "poshuk"]);
});

test("зʼємка теж несе problems — і коли знімати нема чого", async () => {
  const dir = iterFixture();
  const fetchJson = fetchWithFlow(FLOW_Z_OPYSKOJU);
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson });
  const stamps = stampsFor(dir, nodes);
  // Все свіже → браузер не запускається, але скарга мусить дійти однаково.
  // Файли кадрів — на диску: без них `dropMissingShots` слушно скаже «знімка
  // немає», зʼємка піде по-справжньому, і `launch` упаде не через баг.
  touchShots(dir, nodes.map((n) => n.key));
  writeManifest(dir, {
    checkedAt: null,
    shots: Object.fromEntries(nodes.map((n) => [n.key, { geo: GEO_OK, stamp: stamps[n.key] }])),
  });
  const launch = () => { throw new Error("браузер не мав запускатись"); };
  const report = await runShoot({ dir, it: "it1", url: "http://x", now: NOW, fetchJson, launch });
  assert.deepEqual(report.shot, []);
  assert.equal(report.problems.length, 1, `problems: ${JSON.stringify(report.problems)}`);
  assert.match(report.problems[0], /poshuk2/);
});

test("цілий flow.json не вигадує скарг", async () => {
  const dir = iterFixture();
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW,
    fetchJson: fetchWithFlow({ flows: [{ id: "f", nodes: [{ id: "n1", page: "poshuk" }], edges: [] }] }) });
  assert.deepEqual(report.problems, []);
});

/* --- нечитний flow.json: гучний, і манифеста НЕ ЧІПАЄ (ревʼю етапу 2) --- */

/** Так відповідає `_flow_get` у serve.py на побитий файл: `flow: null` ПЛЮС причина. */
const fetchBrokenFlow = async (u) => (u.includes("iteration-pages")
  ? PAGES
  : { flow: null, error: "flow.json не читається: Expecting ',' delimiter: line 3 column 5" });

/**
 * Манифест із трьома кадрами: дві сторінки ПЛЮС кадр стану — рівно те, що лежало
 * на диску в прогоні ревʼю (`holovna`, `poshuk`, `poshuk~48d0ed7a`). Ключ стану
 * тут головний: він з'являється в переліку вузлів ЛИШЕ з flow.json, тож нечитний
 * файл робить перелік усіченим, а `markStale` викидає з манифеста все, чого в
 * переліку немає.
 */
function manifestWithState(dir) {
  const key = shotKey("poshuk", { state: "empty" });
  writeManifest(dir, { checkedAt: null, shots: {
    holovna: { stamp: "старий", w: 1280, h: 900 },
    poshuk: { stamp: "старий", w: 1280, h: 900 },
    [key]: { stamp: "старий", w: 1280, h: 900 },
  } });
  return key;
}

test("нечитний flow.json скасовує перевірку, а не звітує бодрим успіхом", async () => {
  const dir = iterFixture();
  const key = manifestWithState(dir);
  await assert.rejects(
    () => runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fetchBrokenFlow }),
    /flow\.json не читається/,
  );
  /* Найважливіше — не текст помилки, а те, що манифест ЦІЛИЙ. Кадр стану
     існує лише у flow.json: не прочитавши файл, ми не знаємо його ключа, тобто
     передумову `markStale` («stamps — ПОВНИЙ перелік вузлів») виконати нічим.
     Записаний манифест забув би метадані кадру, чий .webp лежить на диску. */
  assert.deepEqual(Object.keys(readManifest(dir).shots).sort(), ["holovna", "poshuk", key].sort(),
    "манифест мусив лишитись цілим — кадр стану не вимивається");
  assert.equal(readManifest(dir).checkedAt, null, "перезважування не відбулось");
});

test("нечитний flow.json скасовує й зʼємку — до запуску браузера", async () => {
  const dir = iterFixture();
  const key = manifestWithState(dir);
  const launch = () => { throw new Error("браузер не мав запускатись"); };
  await assert.rejects(
    () => runShoot({ dir, it: "it1", url: "http://x", all: true, now: NOW,
                     fetchJson: fetchBrokenFlow, launch }),
    /flow\.json не читається/,
  );
  assert.deepEqual(Object.keys(readManifest(dir).shots).sort(), ["holovna", "poshuk", key].sort(),
    "манифест мусив лишитись цілим");
});

/* --- події прогресу зʼємки (Задача 3) --- */

/** Події, зібрані замість запису в stderr. */
function collector() {
  const lines = [];
  return { onProgress: (ev) => lines.push(ev), lines };
}

test("зʼємка видає start, кадр на кожну сторінку і done", async () => {
  const dir = iterFixture();
  const { onProgress, lines } = collector();
  await runShoot({
    dir, it: "it1", url: "http://x", all: true, now: NOW,
    fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(8000, 0x61)),
    onProgress,
  });
  assert.deepEqual(lines.map((e) => e.ev), ["start", "frame", "frame", "done"]);
  assert.equal(lines[0].total, 2, "start мусить нести, скільки всього буде");
  assert.deepEqual(lines.slice(1, 3).map((e) => e.key), ["holovna", "poshuk"]);
});

/* Канвас підміняє картинку картки на льоту, і ключ вічного кеша будується з
   `sha`. Подія без нього змусила б канвас чекати кінця прогону — тобто «бачити
   процес» перетворилось би на смужку-обіцянку. */
test("подія кадру несе те, чим канвас підмінить картинку", async () => {
  const dir = iterFixture();
  const { onProgress, lines } = collector();
  await runShoot({
    dir, it: "it1", url: "http://x", all: true, now: NOW,
    fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(8000, 0x61)),
    onProgress,
  });
  const frame = lines.find((e) => e.ev === "frame");
  const record = readManifest(dir).shots[frame.key];
  assert.equal(frame.sha, record.sha, "sha події = sha манифеста, одне джерело");
  assert.equal(frame.w, record.w);
  assert.equal(frame.h, record.h);
});

test("порожній прогін теж дає start і done — інакше «йде» не згасне", async () => {
  const dir = iterFixture();
  // перший прогін знімає все, другий не має чого знімати
  await runShoot({ dir, it: "it1", url: "http://x", all: true, now: NOW,
                   fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(8000, 0x61)) });
  const { onProgress, lines } = collector();
  await runShoot({ dir, it: "it1", url: "http://x", now: NOW,
                   fetchJson: fakeFetch,
                   launch: () => { throw new Error("браузер не мав запускатись"); },
                   onProgress });
  assert.deepEqual(lines.map((e) => e.ev), ["start", "done"]);
  assert.equal(lines[0].total, 0);
});

test("кадр із проблемою дає fail, а не frame", async () => {
  const dir = iterFixture();
  const { onProgress, lines } = collector();
  // 10 байт — нижче BYTES_FLOOR, тобто «порожня сторінка»
  await runShoot({
    dir, it: "it1", url: "http://x", all: true, now: NOW,
    fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(10, 0x61)),
    onProgress,
  });
  assert.deepEqual(lines.filter((e) => e.ev === "frame"), []);
  const fails = lines.filter((e) => e.ev === "fail");
  assert.equal(fails.length, 2);
  assert.match(fails[0].problem, /порожня сторінка/);
});

test("за замовчуванням події йдуть у stderr з маркером", async () => {
  const dir = iterFixture();
  const written = [];
  const realWrite = process.stderr.write.bind(process.stderr);
  process.stderr.write = (chunk) => { written.push(String(chunk)); return true; };
  try {
    await runShoot({ dir, it: "it1", url: "http://x", all: true, now: NOW,
                     fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(8000, 0x61)) });
  } finally {
    process.stderr.write = realWrite;
  }
  const marked = written.filter((s) => s.startsWith(PROGRESS_MARK));
  assert.ok(marked.length >= 4, `очікували ≥4 рядки з маркером, є ${marked.length}`);
});

/* --- манифест пишеться по ходу (Задача 4) --- */

/* Скасування на 20-му кадрі з 22 не сміє викидати бухгалтерію 19 знятих: .webp
   уже на диску, і без запису наступний прогін зніме їх заново. Симулюємо
   вбивство винятком із третьої сторінки. */
test("манифест зберігає зняте, навіть якщо прогін обірвався", async () => {
  const dir = iterFixture();
  let n = 0;
  const dyingBrowser = () => {
    const good = fakeBrowser(Buffer.alloc(8000, 0x61));
    return {
      newPage: async () => {
        const page = await good.newPage();
        return { ...page,
          goto: async () => {
            n += 1;
            if (n > 1) throw new Error("процес убито");
            return { ok: () => true, status: () => 200 };
          },
          /* Обрив мусить вийти ПОЗА per-page try/catch, інакше цей тест зелений і
             без правки: виняток із `goto` цикл ловить сам (це його робота — одна
             впала сторінка не вбиває решту), прогін спокійно доходить до
             фінального `writeManifest`, і «обірвався» не сталось. `page.close()`
             лежить після циклу — саме там смерть браузера справді забирає з собою
             єдиний запис манифеста. */
          close: async () => { throw new Error("процес убито"); },
        };
      },
      close: async () => {},
    };
  };
  await assert.rejects(
    () => runShoot({ dir, it: "it1", url: "http://x", all: true, now: NOW,
                     fetchJson: fakeFetch, launch: dyingBrowser }),
    /процес убито/,
  );
  const shots = readManifest(dir).shots;
  assert.ok(shots.holovna, "перша сторінка мусить лишитись у манифесті");
  assert.equal(shots.holovna.stamp !== undefined, true, "зі штампом, а не порожнім записом");
});

/* Частковий прогін (`--only`) лишає в манифесті кадри сторінок, яких не чіпав.
 *
 * ⚠️ Це перевірка ПОВЕДІНКИ, а НЕ охоронець вибору «проміжний запис без
 * markStale» — і сказано це тут, щоб наступний читач не подумав інакше. Перша
 * редакція плану підписала її саме як охоронець, з обґрунтуванням «у циклі немає
 * повного переліку штампів». Мутація показала обидві неправди одразу: підміна
 * проміжного `writeManifest(dir, manifest)` на `writeManifest(dir,
 * markStale(manifest, stamps, now))` лишає всі 29 тестів файлу зеленими, бо
 * `stamps` рахується по ВСІХ вузлах (`stampsFor(dir, nodes)`), а не по `wanted`,
 * тобто передумова `markStale` у циклі виконується.
 *
 * Перевірку лишено: вона стереже спостережуваний контракт `--only` (сусідні
 * кадри не зникають) і червоніє, якщо його зламати. Але охоронцем рішення про
 * markStale вона не є — справжня причина того рішення записана в коментарі
 * `bin/shoot.mjs` біля самого рядка, і вона слабша за ту, що там стояла спершу. */
test("частковий прогін лишає в манифесті кадри сторінок, яких не чіпав", async () => {
  const dir = iterFixture();
  await runShoot({ dir, it: "it1", url: "http://x", all: true, now: NOW,
                   fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(8000, 0x61)) });
  // знімаємо ЛИШЕ одну сторінку — друга мусить лишитись у манифесті
  await runShoot({ dir, it: "it1", url: "http://x", only: ["holovna"], now: NOW,
                   fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(8000, 0x62)) });
  const shots = readManifest(dir).shots;
  assert.deepEqual(Object.keys(shots).sort(), ["holovna", "poshuk"]);
});

test("вьюпорт заданої ширини зберігає висоту вікна", () => {
  assert.deepEqual(viewportFor(768), { width: 768, height: VIEWPORT.height });
  assert.deepEqual(viewportFor(undefined), VIEWPORT, "без аргументу — типовий");
});

/* --- цілі й штампи по вьюпортах (Задача 3) --- */

/* ⛔ ЦЕНТРАЛЬНИЙ ІНВАРІАНТ ФІЧІ. `markStale` видаляє з манифеста кожен запис,
   чийого id немає в `stamps`. Дай їй штампи лише поточної ширини — і перемикання
   на мобайл зітре метадані ВСІХ десктопних кадрів, лишивши .webp сиротами на
   диску. Дизайнер побачить «немає знімка» там, де знімок є. */
test("штампи охоплюють УСІ ширини, навіть коли знімаємо одну", async () => {
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(iterFixture(), nodes);
  for (const w of CANVAS_PRESETS.map((p) => p.w)) {
    assert.ok(frameKey("holovna", w) in stamps, `немає штампа для ширини ${w}`);
  }
});

test("штамп однієї сторінки однаковий у всіх ширинах — файли ті самі", () => {
  const dir = iterFixture();
  const stamps = stampsFor(dir, [{ key: "holovna", page: "holovna", rel: "holovna", name: "Головна", query: "" }]);
  const vals = CANVAS_PRESETS.map((p) => stamps[frameKey("holovna", p.w)]);
  assert.equal(new Set(vals).size, 1, "ширина не міняє вміст сторінки, отже й штамп");
});

/* Друга половина розділення: лічильник і цілі зʼємки бачать ЛИШЕ запитану
   ширину. Інакше вхід у «Огляд» на мобайлі рахував би 66 застарілих кадрів і
   знімав усе підряд. */
test("check по одній ширині віддає stale лише цієї ширини", async () => {
  const dir = iterFixture();
  const r = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch, vp: 390 });
  assert.ok(r.stale.every((id) => id.endsWith("@390")), `чужі ширини в stale: ${r.stale}`);
  assert.deepEqual(r.stale.sort(), ["holovna@390", "poshuk@390"]);
});

test("check типової ширини віддає ключі БЕЗ суфікса", async () => {
  const dir = iterFixture();
  const r = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch, vp: CANVAS_W });
  assert.deepEqual(r.stale.sort(), ["holovna", "poshuk"]);
});

/* Найдорожча перевірка задачі: прогін однієї ширини не сміє зачепити чужі записи. */
test("зʼємка мобайла лишає десктопні записи недоторканими", async () => {
  const dir = iterFixture();
  const shot = (vp) => runShoot({
    dir, it: "it1", url: "http://x", all: true, now: NOW, vp,
    fetchJson: fakeFetch, launch: () => fakeBrowser(Buffer.alloc(8000, 0x61)),
  });
  await shot(CANVAS_W);
  const desktopBefore = { ...readManifest(dir).shots };
  await shot(390);
  const after = readManifest(dir).shots;
  for (const [id, rec] of Object.entries(desktopBefore)) {
    assert.deepEqual(after[id], rec, `запис ${id} змінився після зʼємки іншої ширини`);
  }
  assert.ok(after["holovna@390"], "а мобільний кадр мусив зʼявитись");
});

/* ⛔ ОБІЦЯНКА «БЕЗ МІГРАЦІЇ», і це єдине місце, де вона справді перевіряється.
   Манифест, зроблений ДО появи вьюпортів, має ключі БЕЗ суфікса (`holovna`).
   Нова версія мусить визнати такий кадр своїм і не перезнімати — інакше перший
   же вхід у «Огляд» після оновлення інструмента запустив би перезнім усього, що
   в проєкті вже знято, і зробив би застарілими всі коментарі на полотні.

   Манифест пишемо РУКАМИ, а не через `runShoot`, і це несуче: `runShoot` кладе
   ключі через `frameKey`, тобто мутація «суфікс завжди» переписала б і сам
   засів — перевірка лишилась би зеленою на самоузгодженому стані. Штамп беремо
   зі `stampsFor` як ЗНАЧЕННЯ (він однаковий для всіх ширин вузла), тому спосіб
   іменування ключів на засів не впливає.
   Виміряно: під мутацією `frameKey` (суфікс завжди) ця перевірка червоніє, а
   жива перевірка «повернення на десктоп не перезнімає» лишається ЗЕЛЕНОЮ —
   тому вона там позначена як перевірка поведінки, а не як охоронець. */
test("манифест СТАРОГО формату (без суфікса) не вважається застарілим", async () => {
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  const shots = {};
  for (const node of nodes) {
    // ключ БЕЗ суфікса — рівно так писала версія до вьюпортів
    shots[node.key] = {
      w: 1280, h: 900, bytes: 8000, stable: true, capturedAt: NOW,
      stamp: Object.values(stamps).find((_, i) => i >= 0) && stampOf(stamps, node.key),
      stale: false, sha: "0123456789abcdef",
      /* Геометрія — окрема міграція (T-45) з власним тестом нижче: тут
         стережемо лише те, що зміна ФОРМАТУ КЛЮЧА перезйомки не замовляє. */
      geo: GEO_OK,
    };
  }
  touchShots(dir, Object.keys(shots));
  writeManifest(dir, { checkedAt: NOW, shots });
  const r = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(r.stale, [],
    `старі кадри мусять лишитись своїми, а не поїхати на перезнім: ${r.stale}`);
});

/** Штамп вузла зі словника штампів, незалежно від того, як названі ключі. */
function stampOf(stamps, key) {
  for (const [id, stamp] of Object.entries(stamps)) {
    if (id === key || id.startsWith(`${key}@`)) return stamp;
  }
  return undefined;
}

/* T-45. Кадр, знятий ДО геометрії, мусить перезнятись — інакше пінів на ньому
   не буде ніколи. Але ТИХО: дизайн не змінювався, і бейдж «застаріло» відправив
   би дизайнера шукати правку, якої немає. Мутації: прибрати `geoMissingIds` з
   `runCheck` — червоніє перша перевірка; пустити його в `markStale` — друга. */
test("кадр без геометрії йде в перезйомку, але манифест лишає його НЕ застарілим", async () => {
  const dir = iterFixture();
  const { nodes } = await nodeList({ url: "http://x", it: "it1", fetchJson: fakeFetch });
  const stamps = stampsFor(dir, nodes);
  touchShots(dir, nodes.map((n) => n.key));
  writeManifest(dir, { checkedAt: null, shots: {
    holovna: { stamp: stamps.holovna, w: 1280, h: 900 },               // до T-45
    poshuk: { stamp: stamps.poshuk, w: 1280, h: 900, geo: GEO_OK },    // уже з геометрією
  } });
  const report = await runCheck({ dir, it: "it1", url: "http://x", now: NOW, fetchJson: fakeFetch });
  assert.deepEqual(report.stale, ["holovna"], "кадр без геометрії не потрапив у перезйомку");
  assert.equal(readManifest(dir).shots.holovna.stale, false, "бейдж «застаріло» на незміненому дизайні");
});

