#!/usr/bin/env node
/**
 * Знімки сторінок ітерації для канваса.
 *
 *   node bin/shoot.mjs --dir <тека ітерації> --it it6 --url http://localhost:8765 \
 *        [--all] [--only a,b] [--check] [--json] [--vp 375] [--motion]
 *
 * `--vp` — ширина, якою знімаємо. Кадр кожної ширини живе під СВОЇМ ключем
 * (`frameKey`), тому ширини не перетирають одна одну; типова (1280) лишається
 * без суфікса, і наявні знімки валідні без міграції.
 *
 * Перелік сторінок беремо З ЖИВОГО СЕРВЕРА (`/api/iteration-pages`), а не парсимо
 * `pages.json` самі: тоді знімки ніколи не можуть бути знімками іншого набору
 * сторінок, ніж той, що малює канвас.
 *
 * `--check` не відкриває браузер: перезважує штампи й пише stale у манифест. Це
 * єдина реалізація хешу в проєкті — `serve.py` штампи НЕ рахує, лише читає манифест.
 */
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readFlow, stateQuery } from "../app/flow-model.js";
import { kindOf } from "../app/tree-model.js";
import { CANVAS_PRESETS, CANVAS_W, MAX_W, MIN_W, frameKey, splitFrameKey } from "../app/viewport.js";
import { markStale, readManifest, shotSha, shotsDir, staleIds, writeManifest } from "./shots-manifest.mjs";
import { progressLine } from "./shots-progress.mjs";
import { captureGeo, geoMissingIds, writeGeo } from "./shots-geo.mjs";
import { folderStamp, TOOL_META } from "./shots-stamp.mjs";
import { BYTES_FLOOR, settle, shootStable, viewportFor } from "./shots-shutter.mjs";

const argOf = (name, argv = process.argv) => {
  const at = argv.indexOf(`--${name}`);
  return at >= 0 ? argv[at + 1] : undefined;
};

const getJson = async (url) => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json();
};

/**
 * Цілі зʼємки: сторінки ітерації, які реально відкриваються (у порядку дерева),
 * ПЛЮС стани екранів, описані у `flow.json`.
 *
 * Стан — це та сама сторінка з іншим URL, тому в нього СВІЙ ключ кадру
 * (`page~hash`, один на весь проєкт — `shotKey` в `app/flow-model.js`), але ТОЙ
 * САМИЙ штамп: файли на диску ті самі, і застарівають вони разом.
 *
 * Ціль — `{ key, page, name, rel, query }`. `key` — імʼя кадру й ключ манифеста,
 * `page` — що відкривати, `query` — хвіст URL стану.
 *
 * Повертає `{ nodes, problems }`, а НЕ голий масив, і це не косметика. `problems`
 * від `readFlow` — єдиний слід описки в `flow.json`: вузол на неіснуючу сторінку
 * вона викидає, кадр просто не зʼявляється, зʼємка виходить кодом 0, і дизайнер
 * шукає пропажу в інструменті замість одного рядка у файлі. Причепити `problems`
 * властивістю до масиву не можна: перший же `.filter()` чи прохід через JSON
 * зняв би її безшумно — рівно та тиха втрата, проти якої написаний цей конвеєр.
 */
export async function nodeList({ url, it, fetchJson = getJson }) {
  const { pages } = await fetchJson(`${url}/api/iteration-pages?it=${encodeURIComponent(it)}`);
  const out = [];
  const walk = (list, parentKind = null) => {
    for (const page of list ?? []) {
      const kind = kindOf(page, parentKind);
      // тека — організатор у панелі слоїв: не відкривається й не знімається
      if (kind !== "folder") {
        out.push({ key: page.id, page: page.id, name: page.name,
                   rel: page.id === "main" ? "" : page.id, query: "" });
      }
      walk(page.children, kind);
    }
  };
  walk(pages);

  /* Граф читаємо ПРОТИ вже зібраного плаского переліку сторінок — саме такий
     контракт у `readFlow`. Вузол на неіснуючу сторінку (чи на теку-групу, якої
     тут немає зовсім) вона викидає сама, тому `base` нижче завжди знаходиться:
     ціль зʼємки не може вказати на сторінку, якої немає на диску. */
  const { flow, error } = await fetchJson(`${url}/api/flow?it=${encodeURIComponent(it)}`);
  /* `error` — це «файл Є, але не читається» (`_flow_get` у serve.py: побитий JSON,
     тека замість файла, відібрані права). Взяти лише `flow` і піти далі не можна
     ДВІЧІ.
     По-перше, `readFlow(null, …)` виходить без скарг, тобто нечитний файл стає
     невідрізнимим від «флоу ще не описували» — гучність, яку сервер спеціально
     тримає, помирає в одній деструктуризації.
     По-друге, і це гірше: без файла ми не знаємо ключів КАДРІВ СТАНУ (`сторінка~хеш`
     існує лише у flow.json), тобто перелік вузлів усічений — а `markStale` викидає
     з манифеста кожен запис, чийого id немає в `stamps`. Прогін «успішно» звітував
     би «2 кадрів, застаріло 0» і мовчки з'їдав метадані кадру, чий .webp лежить на
     диску. Тому саме ВІДМОВА, а не скарга в `problems`: та сама причина й та сама
     форма, що в охороні «сервер не дав жодної сторінки» нижче — усічений перелік
     передавати в `markStale` не можна взагалі, а не «можна, але з попередженням».
     Описка ВНУТРІ читного файла (вузол на неіснуючу сторінку) лишається
     попередженням: там файл прочитано, і перелік станів повний. */
  if (error) throw new Error(`${error} — перелік кадрів неповний, манифест не чіпаємо`);
  const parsed = readFlow(flow, out.map((n) => ({ id: n.page, name: n.name })));
  const have = new Set(out.map((n) => n.key));
  for (const f of parsed.flows) {
    for (const node of f.nodes) {
      // Вузол без стану — це вже наявна сторінка; і той самий стан у двох смугах
      // це один кадр, а не два.
      if (have.has(node.key)) continue;
      have.add(node.key);
      const base = out.find((n) => n.page === node.page);
      out.push({ key: node.key, page: node.page, name: node.label,
                 rel: base.rel, query: stateQuery(node.state) });
    }
  }
  return { nodes: out, problems: parsed.problems };
}

/**
 * Штамп кожного КАДРУ: тека сторінки + `shared/` (там наші data-include віджети).
 * Для неявної `main` тека сторінки — корінь ітерації, тому НЕ рекурсивно: інакше в
 * штамп потрапили б теки всіх інших сторінок.
 *
 * ⛔ Ключі — по ВСІХ ширинах полотна, ЗАВЖДИ, незалежно від того, яку зараз
 * знімають. Це передумова `markStale`: вона видаляє з манифеста кожен запис,
 * чийого id немає в `stamps`. Дай їй штампи лише поточної ширини — і перемикання
 * «Огляду» на мобайл мовчки зітре метадані всіх десктопних кадрів, лишивши їхні
 * `.webp` сиротами на диску; дизайнер побачить «немає знімка» там, де знімок є.
 * Звужується НЕ це, а `stale` (лічильник) і `wanted` (цілі зʼємки) — див.
 * `runCheck`/`runShoot`. Дві величини, два різні охоплення.
 *
 * Штамп у всіх ширин ТОЙ САМИЙ, і це не спрощення: ширина не міняє файлів
 * сторінки, вона міняє лише те, як їх намалює браузер. Тож правка макета
 * робить застарілими кадри всіх ширин одночасно — саме так і треба.
 */
export function stampsFor(dir, nodes, widths = CANVAS_PRESETS.map((p) => p.w)) {
  const shared = { dir: path.join(dir, "shared"), label: "shared", recursive: true };
  /* КОРІНЬ ІТЕРАЦІЇ, нерекурсивно — спільні `landing.css`/`visual.css`, які
     підсторінки підключають через `../`. Без цієї частини правка спільного
     стилю не робила підсторінки застарілими: сторінка виглядає інакше, а
     помічена свіжою (знайдено живцем на bf360). Нерекурсивно — бо рекурсія
     втягнула б теки всіх інших сторінок і злила б їх в один штамп, тобто
     кожен прогін став би повним назавжди.
     ⚠️ Наслідок, названий уголос: правка будь-якого файла в корені застарює
     ВСІ кадри ітерації. Так і треба — файли справді спільні. */
  /* `skipNames` — службові файли інструмента (`TOOL_META`): перелік сторінок і
     граф флоу лежать тут же, але жодна сторінка їх не читає, тож на кадр вони
     не впливають. Без цього правка графа застарювала ВСІ кадри ітерації
     (TD-9, виміряний вужче, ніж вада насправді була). */
  const root = { dir, label: "root", recursive: false, skipNames: TOOL_META };
  const out = {};
  for (const node of nodes) {
    /* Ключ — `node.key`, а штамп рахуємо по `node.rel`: стан і його сторінка
       мають РІЗНІ ключі кадру, але ОДНАКОВИЙ штамп, бо файли ті самі. */
    const stamp = folderStamp([
      { dir: path.join(dir, node.rel), label: "page", recursive: node.rel !== "" },
      shared,
      root,
    ]);
    for (const w of widths) out[frameKey(node.key, w)] = stamp;
  }
  return out;
}

/**
 * Ширини, ключі яких мусять бути в `stamps`: пресети полотна, ширина цього
 * прогону, і ширини, що ВЖЕ Є В МАНИФЕСТІ для поточних вузлів.
 *
 * Третій доданок — не зручність, а виправлення дефекту, який не самолікувався.
 * Поки набір був прибитий до `CANVAS_PRESETS`, зʼємка на 1920 клала `.webp` на
 * диск, а `markStale` того ж прогону видаляла їхні записи (вона викидає кожен
 * запис, чийого id немає в `stamps`). Далі `staleIds` перебирає ключі `stamps`
 * — тобто @1920 не міг застаріти НІКОЛИ, і повторна зʼємка звітувала `shot:[]`
 * при кадрах, що лежать поруч. Файли є, метаданих немає, перезнім — no-op.
 *
 * Звуження до ПОТОЧНИХ вузлів — економія, а не коректність, і записано це чесно
 * саме тому, що спершу тут стояло сильніше твердження («інакше манифест стане
 * звалищем»). Мутація його спростувала: `markStale` викидає запис за КЛЮЧЕМ
 * КАДРУ цілком, тож кадр видаленої сторінки зникає незалежно від того, чи
 * потрапила його ширина в набір — прибирання не ламається. Реальний ефект
 * звуження скромніший: набір ширин не росте від сміття, і ми не рахуємо зайвих
 * штампів. Тест «кадри зниклої сторінки прибираються» тримає ПЕРЕДУМОВУ
 * `markStale` під новим набором ширин, а не це звуження.
 */
export function widthsFor(manifest, nodes, vp = CANVAS_W) {
  const out = new Set(CANVAS_PRESETS.map((p) => p.w));
  out.add(vp);
  const alive = new Set(nodes.map((n) => n.key));
  for (const id of Object.keys(manifest.shots ?? {})) {
    const { key, w } = splitFrameKey(id);
    if (alive.has(key)) out.add(w);
  }
  return [...out];
}

/**
 * Манифест без записів, чиї `.webp` зникли з диска.
 *
 * Свіжість рахувалась ВИКЛЮЧНО по манифесту: запис зі збіжним штампом означав
 * «кадр знято», і диск ніхто не питав. Тому видалити файл кадру було не досить,
 * щоб сторінку зняли заново — інкрементальний прогін її не чіпав, а канвас
 * показував «немає знімка» поруч із бейджем «свіжий». Вийти можна було лише
 * руками, прибравши запис із манифеста (так і робили на bf360).
 *
 * Саме ВИДАЛЯЄМО запис, а не ставимо йому `stale: true`: запис описує файл —
 * його розмір, байти, час зйомки. Файла немає, отже й описувати нема чого, а
 * `staleIds` порахує відсутній запис застарілим сам («немає знімка»).
 */
export function dropMissingShots(dir, manifest) {
  const shots = {};
  for (const [id, shot] of Object.entries(manifest.shots ?? {})) {
    if (existsSync(path.join(shotsDir(dir), `${id}.webp`))) shots[id] = shot;
  }
  return { ...manifest, shots };
}

/**
 * `vp` — ширина, свіжість кадрів якої рахуємо. На `stamps` вона НЕ впливає (див.
 * `stampsFor`): звужується тільки `stale`, бо лічильник «застаріло N» мусить
 * називати кадри тієї ширини, яку дизайнер зараз дивиться, а не всі 3×N.
 */
export async function runCheck({ dir, it, url, now, fetchJson, vp = CANVAS_W }) {
  const { nodes, problems } = await nodeList({ url, it, fetchJson });
  /* ПОРОЖНІЙ ПЕРЕЛІК — ВІДМОВА, А НЕ «нуль сторінок». `markStale` викидає з
     манифеста кожен запис, чийого id немає в `stamps`, тому усічений перелік
     означав би тихо забуті кадри, які насправді на місці. Ітерація без жодної
     відкриваної сторінки — це або збій, або порожня ітерація, і в обох випадках
     чіпати манифест нема за чим. */
  if (nodes.length === 0) throw new Error(`ітерація ${it}: сервер не дав жодної сторінки`);
  /* Манифест ЧИТАЄМО ПЕРШИМ: набір ширин виводиться і з нього теж (`widthsFor`),
     інакше кадр нетипової ширини лишився б без ключа й зник би назавжди. */
  const manifest = dropMissingShots(dir, readManifest(dir));
  // ВСІ ширини — передумова markStale
  const stamps = stampsFor(dir, nodes, widthsFor(manifest, nodes, vp));
  /* А ось `stale` — лише поточна ширина. Інакше вхід у «Огляд» на мобайлі
     рахував би застарілими ще й усі десктопні та планшетні кадри. */
  const want = new Set(nodes.map((n) => frameKey(n.key, vp)));
  /* Перезйомка = застарілі за дизайном (`staleIds`) + кадри без геометрії
     поточної версії (T-45, `geoMissingIds`). Лише ПЕРЕЛІК: прапорець `stale`
     у манифесті ставить `markStale` за самим дизайном, тож бейдж «застаріло» на
     кадрі без геометрії не зʼявиться — дизайн не змінювався. */
  const stale = [...new Set([...staleIds(manifest, stamps), ...geoMissingIds(manifest, [...want])])]
    .filter((id) => want.has(id));
  writeManifest(dir, markStale(manifest, stamps, now));
  /* `problems` поруч зі `stale`, а не замість коду виходу: описаний криво граф —
     це попередження, а не провал перевірки. Сторінки на місці, штампи пораховані. */
  return { nodes: nodes.length, stale, problems, vp };
}

/**
 * Знімає вузли й пише манифест. За замовчуванням — ЛИШЕ ЗАСТАРІЛІ: повний
 * перезнім не тільки довгий, він ще й робить застарілими всі коментарі на
 * полотні, тобто повертає рев'юеру роботу, яку той уже закрив.
 *
 * `launch` приходить зовні, щоб живий тест міг підставити свій браузер.
 *
 * `vp` — ширина прогону. Прогін ОДНІЄЇ ширини, і кадри інших ширин він не чіпає:
 * ключ кадру несе ширину суфіксом (`frameKey`), тому `holovna` і `holovna@375` —
 * два різні записи й два різні `.webp`. Але `stamps` однаково рахується по ВСІХ
 * ширинах, бо інакше фінальний `markStale` вимив би чужі записи (див. `stampsFor`).
 */
export async function runShoot({ dir, it, url, all = false, only = null, now, fetchJson, launch,
                                 vp = CANVAS_W, motion = false,
                                 onProgress = (ev) => process.stderr.write(progressLine(ev)) }) {
  const { nodes, problems } = await nodeList({ url, it, fetchJson });
  /* Та сама охорона, що в `runCheck`, і з тієї ж причини: помилка в `--it` чи `--url`
     інакше дає порожній звіт і код 0 — невідрізнимо від «усе свіже». */
  if (nodes.length === 0) throw new Error(`ітерація ${it}: сервер не дав жодної сторінки`);
  /* `--only` звіряємо з реальними КЛЮЧАМИ КАДРІВ ДО фільтрації. Інакше друкарська
     помилка тихо зникає: `wanted` порожній, звіт порожній, код 0 — дизайнер бачить
     те саме, що й людина, якій справді нема чого перезнімати. Запит, який ні в що не
     влучив, мусить падати гучно.
     Ключ, а не id сторінки: кадр стану інакше не можна попросити поіменно. Зворотний
     бік — `--only poshuk` бере САМЕ базовий кадр, а не сторінку з усіма її станами. */
  if (only) {
    /* Ключі ПОТОЧНОЇ ширини: на мобайлі кадр зветься `holovna@375`, і саме таке
       імʼя дизайнер бачить у звіті й у манифесті. Звіряти з ключами вузлів
       означало б приймати `--only holovna` під `--vp 375` і мовчки знімати не те,
       що попросили. */
    const known = new Set(nodes.map((n) => frameKey(n.key, vp)));
    const unknown = only.filter((key) => !known.has(key));
    /* «Кадру», а не «сторінки»: аргумент тепер ключ кадру, і стан виглядає як
       `poshuk~48d0ed7a`. Стара фраза відправляла б шукати описку в pages.json
       там, де насправді просто не той ключ. Тому ж підказуємо обидві форми. */
    if (unknown.length) {
      throw new Error(`--only: немає такого кадру — ${unknown.join(", ")}`
                      + " (кадр — це id сторінки або сторінка~стан зі звіту)");
    }
  }
  // ДО штампів — див. `widthsFor`; без записів, чиї файли зникли — `dropMissingShots`
  const manifest = dropMissingShots(dir, readManifest(dir));
  const stamps = stampsFor(dir, nodes, widthsFor(manifest, nodes, vp));
  /* Той самий поділ, що в `runCheck`: штампи повні, а цілі — лише поточної
     ширини. Інакше перемикання на мобайл перезнімало б заразом і десктоп. */
  const want = new Set(nodes.map((n) => frameKey(n.key, vp)));
  /* Перезйомка = застарілі за дизайном (`staleIds`) + кадри без геометрії
     поточної версії (T-45, `geoMissingIds`). Лише ПЕРЕЛІК: прапорець `stale`
     у манифесті ставить `markStale` за самим дизайном, тож бейдж «застаріло» на
     кадрі без геометрії не зʼявиться — дизайн не змінювався. */
  const stale = [...new Set([...staleIds(manifest, stamps), ...geoMissingIds(manifest, [...want])])]
    .filter((id) => want.has(id));
  const wanted = only ? nodes.filter((n) => only.includes(frameKey(n.key, vp)))
    : all ? nodes
      : nodes.filter((n) => stale.includes(frameKey(n.key, vp)));
  const wantedKeys = new Set(wanted.map((w) => frameKey(w.key, vp)));
  const report = {
    /* Ширина прогону — у звіті, і це не косметика. Прогін знімає ОДНУ ширину, а
       `left` перелічує кадри лише її ж; про кадри інших ширин звіт не казав
       нічого, і мовчання читалось як «решта свіжа». Саме так прочитали прогін
       `{all:true}` без `vp` на courts: пʼять кадрів стали свіжими, пʼять @390
       лишились застарілими, і виглядало це як баг обліку. */
    vp,
    shot: [],
    failed: [],
    // Скарги на сам `flow.json` — окремо від `failed`: там кадри, які намагались
    // зняти й не змогли, а тут вузли, які до зʼємки навіть не дійшли.
    problems,
    // Що НЕ перезняли — друкуємо завжди: тиха повнота це головний спосіб
    // збрехати про інкрементальний прогін. За ключем, а не за тожністю обʼєктів.
    left: nodes.filter((n) => !wantedKeys.has(frameKey(n.key, vp))).map((n) => frameKey(n.key, vp)),
  };
  /* `start` йде ДО раннього виходу: порожній прогін теж мусить мати початок і
     кінець, інакше «йде зʼємка» на боці канваса не згасне ніколи. */
  onProgress({ ev: "start", it, total: wanted.length });
  if (wanted.length === 0) {
    writeManifest(dir, markStale(manifest, stamps, now));
    onProgress({ ev: "done", shot: 0, failed: 0 });
    return report;
  }

  mkdirSync(shotsDir(dir), { recursive: true });
  const browser = await launch();
  try {
    /* `prefers-reduced-motion: reduce` ТИПОВО.
       `settle()` ставить на паузу анімації, які видно через `getAnimations()`,
       але руху на `requestAnimationFrame` (GL-ефект у хіро, лоадер) вона не
       бачить узагалі: два знімки поспіль фізично не можуть збігтися, кадр
       виходить `stable:false`, дістає `problem`, а запис із `problem`
       застарілий за побудовою. Тобто КОЖЕН кадр такого макета був позначений
       недостовірним назавжди — попередження стояло всюди, і дизайнер перестав
       йому вірити (bf360, 08.09.2026).
       ⚠️ Прапорець нічого не зупиняє сам: він ПИТАЄ сторінку. Зупиняється та,
       що поважає медіа-запит — живі макети його поважають. `motion: true`
       повертає рух, коли зняти треба саме його. */
    const page = await browser.newPage({
      viewport: viewportFor(vp),
      reducedMotion: motion ? "no-preference" : "reduce",
    });
    for (const node of wanted) {
      /* Ключ КАДРУ, а не вузла. Далі під ним ідуть усі чотири споживачі — імʼя
         `.webp`, запис манифеста, рядки звіту й події прогресу. Розійдуться —
         канвас шукатиме картку за одним ключем, а сервер віддаватиме інший. */
      const id = frameKey(node.key, vp);
      /* `node.page` — що відкривати, `node.query` — хвіст стану. Хвіст іде
         ОСТАННІМ і вже екранований (`stateQuery`), а зарезервовані наші
         параметри (`it`, `page`, `bare`…) стан перебити не може: це стереже
         `checkState` у `app/flow-model.js`. */
      const target = `${url}/commented?it=${encodeURIComponent(it)}` +
                     `&page=${encodeURIComponent(node.page)}&bare=1${node.query}`;
      /* КОЖНА СТОРІНКА У СВОЄМУ try/catch. Один збій CDP чи закрита сторінка не
         мусить убивати прогін решти: `shootStable` ретраїть розходження байтів, але
         НЕ винятки, і без цієї обгортки одна впала сторінка забирала б із собою всі
         наступні. Впала — це рядок у `failed`, а не кінець прогону. */
      try {
        const response = await page.goto(target, { waitUntil: "load" });
        /* СТАТУС ВІДПОВІДІ — ОБОВʼЯЗКОВА ПЕРЕВІРКА, і ось чому вона не зайва:
           Playwright НЕ кидає на HTTP 404, а сторінка помилки `http.server` має
           текст, не має анімацій і важить більше за BYTES_FLOOR — тобто проходить
           УСІ чотири перевірки `problem` і лягає на канвас «успішним» кадром
           макета. Це рівно та брехня, проти якої існує весь цей конвеєр: картинка,
           що пройшла всі перевірки і не є дизайном. Найпростіший спосіб на неї
           натрапити — сторінка, яка є в pages.json, а теки її вже немає.
           Знайдено живим прогоном у Task 5. */
        if (!response || !response.ok()) {
          const problem = `сторінка віддала ${response ? response.status() : "нічого"} — кадру немає`;
          report.failed.push({ id, problem });
          onProgress({ ev: "fail", i: report.shot.length + report.failed.length,
                       total: wanted.length, key: id, problem });
          continue;   // ні .webp, ні запису в манифесті: канвас скаже «немає знімка»
        }
        const { pausedMidFlight, emptyImages, neverSettled,
                scrolled, hiddenBlocks } = await settle(page);
        /* Ширина йде в затвор, а не лише у вьюпорт сторінки: `shootOnce` кладе її
           в `clip`, тож кадр виходить рівно 375 (а не 375 у вікні й 1280 у файлі). */
        const shot = await shootStable(page, 5, vp);
        writeFileSync(path.join(shotsDir(dir), `${id}.webp`), shot.buf);
        /* Геометрія — ПІСЛЯ кадру: сторінка вже заморожена затвором, прямокутники
           більше не їдуть, і вони описують рівно ці пікселі (T-45). Збій геометрії
           — не збій кадру: кадр лишається, пінів на ньому просто не буде, а
           причина лягає в манифест і обриває вічну перезйомку (`geoMissingIds`). */
        let geo = null, geoProblem = null;
        try {
          geo = await captureGeo(page);
          writeGeo(path.join(shotsDir(dir), `${id}.geo.json`), geo);
        } catch (err) {
          geo = null;
          geoProblem = `геометрія не знялась: ${err.message}`;
        }
        /* Причина рахується ДО запису й лягає В запис. Раніше вона жила лише в
           `report.failed` — тобто у виводі одного прогону: манифест зберігав
           свіжий штамп, кадр вважався актуальним, і перезняти його інкрементальний
           прогін не міг за побудовою. Тепер `problem` у манифесті робить запис
           застарілим (`staleIds`) і водночас дає канвасу назвати причину. */
        const problem = neverSettled ? "сторінка так і не стала — кадр знято на невідомому моменті"
          : !shot.stable ? "не дав двох однакових знімків — сторінка ще рухалась"
            : shot.buf.length < BYTES_FLOOR ? `знімок ${shot.buf.length} байт — це порожня сторінка`
              : emptyImages > 0 ? `${emptyImages} картинок не завантажились — у кадрі дірки`
                /* Невидимий блок — саме той дефект, що виглядає як задум: кадр
                   стабільний, важить достатньо, картинки на місці, а частина
                   макета порожня. Прохід скролом закриває типовий випадок; те, що
                   лишилось невидимим ПІСЛЯ нього, мусить бути названим уголос, а
                   не тихо поїхати на канвас (фідбек 03.09.2026). */
                : hiddenBlocks > 0
                  ? `${hiddenBlocks} блоків лишились невидимими — у кадрі порожні місця`
                  : null;
        manifest.shots[id] = {
          w: shot.w, h: shot.h, bytes: shot.buf.length, stable: shot.stable,
          tries: shot.tries, pausedMidFlight, emptyImages, neverSettled,
          scrolled, hiddenBlocks,
          truncated: shot.truncated, fullHeight: shot.full,
          capturedAt: now, stamp: stamps[id], stale: false,
          /* Хеш ЦИХ байтів, і саме з нього канвас робить ключ вічного кешу:
             `capturedAt` має точність до хвилини, а `stamp` — це хеш джерел,
             тож перезнятий кадр міг застрягти в кеші назавжди. Див. `shotSha`. */
          sha: shotSha(shot.buf),
          ...(geo ? { geo: { v: geo.v, n: geo.els.length, truncated: geo.truncated } } : {}),
          ...(geoProblem ? { geoProblem } : {}),
          ...(problem ? { problem } : {}),
        };
        const i = report.shot.length + report.failed.length + 1;
        if (problem) {
          report.failed.push({ id, problem });
          onProgress({ ev: "fail", i, total: wanted.length, key: id, problem });
        } else {
          report.shot.push(id);
          const rec = manifest.shots[id];
          /* Подія несе ВСІ ТРИ складові ключа кеша (`stamp`, `capturedAt`, `sha`),
             а не лише `sha`. Інакше канвас зібрав би `shotVersion({sha})` = «..abc»,
             а наступний повний рендер — «stamp.час.abc»: той самий файл під двома
             URL, тобто зайве перекачування повнорозмірного webp одразу після
             зʼємки. Кеш віддається з `immutable`, тож розбіжність не помилка —
             вона просто марна робота, і її видно на 22 кадрах. */
          onProgress({ ev: "frame", i, total: wanted.length, key: id, name: node.name,
                       sha: rec.sha, stamp: rec.stamp, capturedAt: rec.capturedAt,
                       w: shot.w, h: shot.h });
        }
        /* Пишемо ПО ХОДУ. Без цього рядка вбитий (чи зупинений дизайнером) прогін
           лишає .webp на диску, а манифест про них не знає — наступний прогін
           знімає все заново. Автостарт робить зупинку звичайною справою, тож це
           не оптимізація, а коректність.
           БЕЗ `markStale`, і причина НЕ та, яку тут спершу написали. Перша
           редакція стверджувала «у циклі немає повного переліку поточних вузлів» —
           це неправда: `stamps` рахується як `stampsFor(dir, nodes)` по ВСЬОМУ
           переліку вузлів, а не по `wanted`, тож передумова `markStale`
           («видаляє кожен запис, чийого id немає в stamps») у циклі виконується.
           Мутація це й показала: підміна цього рядка на `markStale(...)` лишає
           всі 29 тестів файлу ЗЕЛЕНИМИ, тобто спостережуваної шкоди сьогодні немає.

           Справжня причина інша й слабша, і саме тому записана чесно: `markStale`
           ще й ставить `checkedAt` (це «коли востаннє ПЕРЕЗВАЖУВАЛИ свіжість» —
           зʼємка цього не робить) і множить кількість місць, які залежать від
           віддаленої властивості «stamps повний». Сьогодні вона тримається рядком
           за сто рядків звідси; кликати функцію з руйнівною передумовою раз на
           прогін дешевше, ніж раз на кадр. Фінальний `markStale` — один, у кінці.

           Атомарність уже забезпечена (унікальний .tmp + rename), тож 22 записи —
           це 22 атомарні заміни, а не 22 вікна для побитого JSON. */
        writeManifest(dir, manifest);
      } catch (err) {
        const problem = `зʼємка впала: ${err.message}`;
        report.failed.push({ id, problem });
        onProgress({ ev: "fail", i: report.shot.length + report.failed.length,
                     total: wanted.length, key: id, problem });
      }
    }
    await page.close();
  } finally {
    /* Помилку закриття не піднімаємо: якщо браузер упав (OOM), кинуть і цикл, і
       `close()` — і без `.catch` назовні поїхала б причина закриття замість
       справжньої, а дизайнер побачив би в тості безглузде повідомлення. */
    await browser.close().catch((e) => console.error(`не вдалось закрити браузер: ${e.message}`));
  }
  writeManifest(dir, markStale(manifest, stamps, now));
  onProgress({ ev: "done", shot: report.shot.length, failed: report.failed.length });
  return report;
}

/** dd.mm.yyyy hh:mm — той самий формат, що в iterations.json. */
export function stampTime(date = new Date()) {
  const two = (n) => String(n).padStart(2, "0");
  return `${two(date.getDate())}.${two(date.getMonth() + 1)}.${date.getFullYear()} ` +
         `${two(date.getHours())}:${two(date.getMinutes())}`;
}

/* Чи запустили ЦЕЙ файл як команду. Наївне `import.meta.url === `file://${process.argv[1]}``
   тут не працює, і мовчки: `import.meta.url` кодує пробіл (`Liga%20Tools`), а `argv[1]`
   лишає буквальний, і на відносному виклику `argv[1]` це взагалі `bin/shoot.mjs`. Рядки
   ніколи не збігаються, CLI тихо нічого не робить і віддає код 0. Знайдено на живому
   прогоні в Task 3. */
const invokedDirectly = process.argv[1]
  && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);

if (invokedDirectly) {
  const dir = argOf("dir");
  const it = argOf("it");
  const url = argOf("url") ?? "http://localhost:8765";
  const asJson = process.argv.includes("--json");
  if (!dir || !it) {
    console.error("треба --dir <тека ітерації> і --it <itN>");
    process.exit(2);
  }
  /* `--vp` валідуємо ГУЧНО, а не підставляємо типову ширину мовчки. Тихий дефолт
     тут — найгірший клас брехні в цьому конвеєрі: `viewportFor(NaN)` віддає 1280
     (бо NaN хибний), тобто кадр знявся б десктопною шириною й ліг під ключем
     `holovna@abc`. Знімок не тієї ширини під імʼям тієї — і жодна перевірка далі
     цього вже не побачить. Межі ті самі, що в полі ширини робочого вида. */
  const vpRaw = argOf("vp");
  const vp = vpRaw === undefined ? CANVAS_W : Number(vpRaw);
  if (!Number.isInteger(vp) || vp < MIN_W || vp > MAX_W) {
    console.error(`--vp: треба ціле число ${MIN_W}…${MAX_W}, а не ${JSON.stringify(vpRaw)}`);
    process.exit(2);
  }
  const now = stampTime();
  /* ОБИДВІ гілки під одним try: цей stderr побачить дизайнер у тості канваса
     (Task 7), і сирий стек undici там нічого не скаже. Обгортка з'явилась у Task 3
     для `--check` — при розширенні хвоста її легко втратити, тому вона тут. */
  try {
    if (process.argv.includes("--check")) {
      const report = await runCheck({ dir, it, url, now, vp });
      if (asJson) {
        console.log(JSON.stringify(report));
      } else {
        /* «кадрів», а не «сторінок»: відколи в перелік входять стани, це число
           більше не дорівнює кількості сторінок ітерації — `poshuk~48d0ed7a`
           сторінкою не є. */
        console.log(`${report.nodes} кадрів, застаріло ${report.stale.length}` +
                    (report.stale.length ? `: ${report.stale.join(", ")}` : ""));
        // У stdout, а не в stderr: це не збій прогону, це зауваження до файла.
        for (const bad of report.problems) console.log(`FLOW.JSON: ${bad}`);
      }
      /* Код виходу лишається 0 навіть зі скаргами: сторінки на місці, штампи
         пораховані, перевірка зробила свою роботу. Крива смуга у графі — привід
         сказати вголос, а не привід оголосити перевірку невдалою. */
      process.exit(0);
    }
    const { chromium } = await import("playwright");
    const only = argOf("only")?.split(",").map((s) => s.trim()).filter(Boolean) ?? null;
    const report = await runShoot({
      dir, it, url, now, only, vp,
      all: process.argv.includes("--all"),
      // Типово знімаємо з `prefers-reduced-motion: reduce`; `--motion` повертає рух.
      motion: process.argv.includes("--motion"),
      launch: () => chromium.launch(),
    });
    if (asJson) {
      console.log(JSON.stringify(report));
    } else {
      console.log(`знято ${report.shot.length} (ширина ${report.vp}): `
                  + `${report.shot.join(", ") || "—"}`);
      // Кадри інших ширин цей прогін не чіпав — сказати вголос, бо мовчання
      // читається як «решта свіжа».
      console.log("кадри інших ширин не чіпали — щоб оновити їх, потрібен свій прогін");
      if (report.left.length) console.log(`лишили в спокої ${report.left.length}: ${report.left.join(", ")}`);
      for (const bad of report.failed) console.log(`ПРОБЛЕМА ${bad.id}: ${bad.problem}`);
      // Скарги на граф — після кадрів і окремим префіксом: це інший файл і інша
      // причина, ніж кадр, що не знявся, і злипнутись вони не мусять.
      for (const bad of report.problems) console.log(`FLOW.JSON: ${bad}`);
    }
    process.exit(report.failed.length ? 1 : 0);
  } catch (err) {
    console.error(`не вийшло зняти ітерацію ${it} (${url}): ${err.message}`);
    process.exit(1);
  }
}
