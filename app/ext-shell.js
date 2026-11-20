/**
 * Оболонка ОПУБЛІКОВАНОГО превʼю: адаптер стану (`manifest.json` → те, що
 * чекають малювальники) плюс тонка проводка DOM.
 *
 * Світ, у якому цей модуль живе, відрізняється від інструмента трьома речами,
 * і з них виводиться все решта:
 *   · немає сервера — жодного `/api/*`; єдине джерело правди це
 *     `publish/manifest.json`, який пише публікація (`publish_manifest`);
 *   · немає прав — глядач нічого не міняє, тому панель іде з `readonly: true`,
 *     а смуга не везе ні GitLab, ні публікації, ні інспектора;
 *   · є гейт — і поки він закритий, оболонка не сміє ні показати рамку, ні
 *     назвати задачу.
 *
 * ⚠️ ЧОМУ ОДИН ФАЙЛ несе і чистий адаптер, і проводку (так його називає план:
 * «адаптер стану плюс тонка проводка»). Ціна цього рішення видна одразу:
 * підняття оболонки стоїть за перевіркою наявності `document` у самому кінці
 * файла — інакше `tests/ext-shell.test.mjs` не міг би імпортувати адаптер у
 * node, і кути маніфеста (битий, без кадрів, сторінка з теки, глибоке
 * посилання в нікуди) перевірялись би лише крізь браузер, тобто на одному
 * маніфесті, який зібрала фікстура.
 *
 * ⛔ Проводка КОНТРОЛІВ — ОДНА делегація на `document` і ОДИН реєстр
 * `EXT_ACTIONS`. Причина названа планом і вже сталась у Плані A: забутий рядок
 * проводки — це кнопка, що нічого не робить, і саме так колись кнопка палітри
 * (тепер її нема, ⌘K кличе `openPalette` напряму) опинилась мертвою (розмітка, модель
 * і реєстр були правильні, а рядок поклали в інший реєстр). Смуга й панель ходять через один реєстр саме тому, що імена
 * дій у них не перетинаються, а два реєстри — це два місця, куди можна не
 * дописати.
 *
 * ⚠️ Виняток названий вголос: полотно «Огляду» має СВОЮ проводку
 * (`wireCanvas`), і не тому, що так вийшло. Клік по картці треба відрізнити від
 * панорами, а делегація по атрибуту цього не може — обидва жести кінчаються
 * тим самим `click` на тій самій картці. Тому там pointer-жест із порогом, як
 * у холсті інструмента.
 *
 * ⚠️ ВИСОТИ КАДРІВ приходять ДВОМА дорогами, і це не дубль. Головна —
 * `w`/`h` у записі кадру з `publish/manifest.json` (їх кладе `publish_frames`
 * із того, що заміряла зʼємка): нею розкладка правдива ще ДО того, як приїхав
 * перший кадр. Запасна — сам знімок після завантаження (`onFrameLoad`), і вона
 * мусить лишитись, бо розміру може не бути: превʼю, зібране до 03.09.2026, або
 * запис, чий розмір не пройшов валідацію публікації. До 03.09.2026 запасна
 * дорога була єдиною, і ціну було видно: при вході в «Огляд» світ один раз
 * «сідав» під справжні пропорції, а на повільній мережі глядач якийсь час
 * бачив геометрію, яка брехала про розміри (розкид справжніх висот заміряний —
 * 900…8000px).
 */

import { ask } from "./ask.js";
import { applyClean, syncFrame } from "./clean-view.js";
import { fitBox, focusBox, quantScale, zoomAt } from "./camera.js";
import { GAP, HEAD, ROW_TITLE_TOP } from "./canvas-geom.js";
import { CMT_ACTS, CMT_EVENTS, createExtComments } from "./ext-comments.js";
import { extBarHTML } from "./ext-bar.js";
import { islandToolsHTML } from "./island.js";
import { LANG_KEY, readStoredLang, setLang, t } from "./i18n.js";
import { SPRITE, ico } from "./icons.js";
import { rowsLayout, worldBox } from "./layout.js";
import { buildRows } from "./rows-model.js";
import { kindOf } from "./tree-model.js";
import { panelHTML } from "./shell-panel.js";
import {
  CANVAS_PRESETS, CANVAS_W, PRESETS, frameKey, splitFrameKey,
} from "./viewport.js";

/* ── чистий адаптер ─────────────────────────────────────────────────────── */

/**
 * Сторінка з глибокого посилання (`#p=<it>/<сторінка>`), або `null`.
 *
 * Формат не новий і не наш: він уже розійшовся посиланнями, які менеджери
 * зберігали собі, тому регексп мусить читати `p=` і як ПЕРШИЙ параметр hash, і
 * як сусіда токена гейта (`#k=…&p=…`) — гейт зʼїдає лише свій `k=`, решту
 * лишає (`GATE_SNIPPET` у serve.py).
 */
export function hashPage(hash) {
  const m = /(?:^#|&)p=([^&]*)/.exec(String(hash || ""));
  if (!m || !m[1]) return null;
  try {
    return decodeURIComponent(m[1]);
  } catch (e) {
    /* `%` без пари — не наш формат, а чиясь обрізана адреса. Кидати тут
       означало б, що зіпсоване посилання не відкриває превʼю ВЗАГАЛІ, замість
       того щоб відкрити першу сторінку. */
    return m[1];
  }
}

/**
 * З чого починати показ: сторінка з посилання, інакше перша в ОСТАННІЙ ітерації.
 *
 * Сторінку могли зняти з превʼю ПІСЛЯ того, як посилання розійшлось, — тому
 * ідентифікатор із hash перевіряється по маніфесту, а не підставляється в
 * `src` рамки на віру (інакше глядач отримав би 404 замість макета).
 *
 * ⛔ Не `pages[0]`. Плаский перелік складає `published_pages` в порядку
 * ітерацій, тобто перша сторінка маніфесту — це НАЙСТАРІШИЙ макет: глядач
 * відкривав превʼю на Іт.1 і мусив сам здогадатись, що в крошці є новіші.
 * Інструмент так не робить давно (`render()` в `app.js` бере
 * `iterations[length-1]`), і превʼю мусить відкриватись так само — інакше
 * дизайнер і менеджер за одним посиланням бачать різні макети.
 *
 * Ідемо з КІНЦЯ `iters` і беремо першу ітерацію, у якій є сторінки. Зазвичай
 * це остання ж: `publish_manifest` кладе в `iters` лише ітерації зі
 * сторінками. Але маніфест — це файл на чужому сервері, старший або зібраний
 * іншою версією, і жодне з двох припущень («iters непорожній», «остання має
 * сторінки») не варте порожнього екрана замість макета. Без `iters` узагалі
 * лишається давня поведінка — перша сторінка.
 */
export function startPage(man, hash) {
  const pages = man?.pages ?? [];
  const want = hashPage(hash);
  if (want && pages.some((p) => p.id === want)) return want;
  const iters = man?.iters ?? [];
  for (let i = iters.length - 1; i >= 0; i -= 1) {
    const first = pages.find((p) => p.it === iters[i].id);
    if (first) return first.id;
  }
  return pages.length ? pages[0].id : null;
}

/**
 * Чому «Огляд» вимкнений: імʼя ключа причини або `''` (увімкнений).
 *
 * Кадри лежать статикою й знімаються в інструменті — тобто в ітерації, яку
 * ніхто не знімав, «Огляд» показав би порожнє полотно, а глядач не має ні
 * зʼємки, ні способу дізнатись причину. Вимкнена кнопка з видимим рядком
 * причини — те саме правило, що для вимкнених пунктів смуги інструмента.
 */
export function overviewWhyKey(man, it) {
  return Object.keys(man?.frames?.[it] ?? {}).length ? "" : "shotsNone";
}

/** Ширина рамки для пресета. `null` — вільна ширина вікна (десктоп). */
export function vpWidth(vp) {
  const p = PRESETS.find((x) => x.id === vp);
  return p ? p.w : null;
}

/**
 * Посилання для «Копіювати посилання»: `#k=<пароль>&p=<сторінка>`.
 *
 * `k=` тут не зручність, а те, що робить кнопку осмисленою: без токена
 * менеджер шле колезі адресу, яка просить пароль, якого в колеги немає. Та
 * сама модель, що вже в дашборді; пароль і так лежить у тексті сторінки
 * (гейт — оверлей у браузері, не серверний замок).
 */
export function copyUrl(loc, pw, page) {
  return `${loc.origin}${loc.pathname}${loc.search || ""}`
    + `#k=${encodeURIComponent(pw)}&p=${encodeURIComponent(page)}`;
}

/**
 * Батько кожного рядка — ІНДЕКСОМ у переліку, або `-1`.
 *
 * У маніфесті лежить ПЛАСКИЙ перелік із `depth` — дерева як структури там
 * немає (і не було в старій обгортці). Тому батько рядка рахується так само,
 * як рахував той код: найближчий попередній рядок МЕНШОЇ глибини.
 *
 * ⚠️ Функція одна на двох читачів — панель (`extRows`) і полотно «Огляду»
 * (`extTree`), — і це не економія рядків. Дерево в панелі й ряди на полотні
 * мусять групувати сторінки ОДНАКОВО: розійдись вони, і клік по рядку панелі
 * вів би до картки, яка на полотні стоїть в іншому ряду, ніж у дереві. Другий
 * прохід «майже такою» формулою — рівно та пара, що розходиться молча.
 *
 * Індекс, а не id: `extTree` мусить дістатись самого ВУЗЛА батька, а не лише
 * його імені, і пошук по id для цього означав би другу мапу.
 */
function depthParents(pages) {
  return pages.map((p, i) => {
    for (let j = i - 1; j >= 0; j -= 1) if (pages[j].depth < p.depth) return j;
    return -1;
  });
}

/**
 * Рядки дерева для `panelHTML()` зі сторінок маніфеста. Батьківство рахує
 * `depthParents` (див. його шапку: дерева як структури в маніфесті немає).
 *
 * Джерело — `outline` (теки Є, з явним `kind`) або, у старому превʼю, `pages`
 * (без тек).
 *
 * ⚠️ У старому превʼю рядок, у якого `depth > 0`, а батька в переліку НЕМА, — не
 * аномалія, а сторінка з ТЕКИ: тека в `pages` не їде, а її діти їдуть, зі своєю
 * глибиною. Такий рядок мусить лишитись ВИДИМИМ: сховати його «до розгортання
 * батька», якого не існує, означало б прибрати з превʼю опубліковану сторінку.
 *
 * Розгорнутість тримаємо як набір РОЗГОРНУТИХ (а не згорнутих): тоді «типово
 * стани сховані» виходить саме собою, і сторінка, додана в розкладку пізніше,
 * теж приїжджає згорнутою. Гілка ВИБРАНОЇ сторінки розгортається завжди —
 * інакше глибоке посилання на стан відкриває макет, а в дереві не підсвічено
 * нічого. Рахується це в КОПІЇ набору: адаптер чистий, і правити стан
 * викликача він не сміє (юніт це стереже).
 */
export function extRows(man, ui) {
  // outline (теки + стани з явним kind) — у новому превʼю; старе має лише pages
  const pages = (man?.outline ?? man?.pages ?? []).filter((p) => p.it === ui.it);
  const parent = depthParents(pages);
  const line = (i) => {
    const out = [];
    for (let a = parent[i]; a >= 0; a = parent[a]) out.push(pages[a].id);
    return out;
  };
  /* Тип — тим самим виводом, що в `extTree`/`buildRows` (`kindOf` від типу
     батька), щоб панель і сітка не розходились у тому, хто стан, на трьох і
     більше рівнях старого превʼю. */
  const kinds = [];
  pages.forEach((p, i) => { kinds[i] = kindOf(p, parent[i] >= 0 ? kinds[parent[i]] : null); });
  const open = new Set(ui.expanded);
  const picked = pages.findIndex((p) => p.id === ui.page);
  if (picked >= 0) for (const a of line(picked)) open.add(a);
  return pages
    .map((p, i) => ({ p, i }))
    .filter(({ i }) => line(i).every((a) => open.has(a)))
    .map(({ p, i }) => ({
      id: p.id,
      depth: p.depth,
      isGroup: p.kind === "folder",
      /* З outline тип явний; без нього — вивід за типом батька (дитина
         сторінки = стан, дитина стану чи сирітка з теки = сторінка). */
      isState: kinds[i] === "state",
      hasKids: !!pages[i + 1] && pages[i + 1].depth > p.depth,
      expanded: open.has(p.id),
      selected: p.id === ui.page,
      name: p.name,
      /* ⛔ Крапки «у превью» тут немає, і це рішення, а не пропуск: у маніфест
         їдуть ЛИШЕ опубліковані сторінки, тобто крапка стояла б на кожному
         рядку без винятку й не відрізняла б нічого. Позначку, що є в кожного,
         читають як декор — і наступного разу, коли вона щось означатиме, їй
         уже не повірять. */
      mark: false,
    }));
}

/** Стан для спільного `panelHTML()`. `readonly` — не опція, а весь сенс. */
export function extPanelState(man, ui) {
  const pages = man?.pages ?? [];
  return {
    panel: ui.collapsed ? "rail" : "open",
    hasIteration: pages.some((p) => p.it === ui.it),
    // Готовий до показу рядок, як `pagesError` в інструменті: перекладає
    // проводка, бо вона одна знає, що саме зламалось.
    pagesError: ui.error || "",
    rows: extRows(man, ui),
    /* Зʼємки в статиці не існує — рахувати кадри нема для чого. `readonly`
       і так не малює блок кадрів, але `null` тут не «про всяк випадок»: він
       каже читачеві, що величини просто немає, а не що вона нульова. */
    shots: null,
    shotsOpen: false,
    readonly: true,
  };
}

/* ── чистий адаптер «Огляду» ─────────────────────────────────────────────── */

/**
 * РЕАЛЬНИЙ режим: «Огляд» без кадрів схлопується в «Макет».
 *
 * ⛔ Не косметика. Досяжно це найзвичайнішим шляхом: глядач у «Огляді»
 * перемикає ітерацію, а тієї ніхто не знімав. Без цієї функції сегмент
 * лишається натиснутим на «Огляді», сцена схована, полотно порожнє — тобто
 * кнопка бреше про те, де людина, а на екрані немає нічого. Та сама ідіома, що
 * `effView()` в інструменті: стан ПРОСИТЬ, а показуємо те, що можемо.
 */
export function effMode(man, ui) {
  if (ui.mode !== "overview") return "layout";
  return overviewWhyKey(man, ui.it) ? "layout" : "overview";
}

/**
 * Ширина картки на полотні — з пресетів ПОЛОТНА (`CANVAS_PRESETS`), а не рамки.
 *
 * Різниця не косметична: у `PRESETS` «Десктоп» це `null` (вільна ширина вікна),
 * а на полотні вільної ширини не буває — кадр знято у фіксованих `CANVAS_W`, і
 * саме це число мусить стати шириною картки, інакше кадр 1:1 ліг би з
 * масштабом. Той самий поділ, що в інструменті (`canvasW` проти `vpWidth`).
 */
export function overviewCardW(vp) {
  return CANVAS_PRESETS.find((p) => p.id === vp)?.w ?? CANVAS_W;
}

/**
 * Висота картки, поки (або якщо) кадр не сказав свою.
 *
 * ⚠️ Число тут заглушкове, і воно те саме, що інструмент ставить картці без
 * запису (`h ?? 900` у `cardEl`). Сидіти на ньому не можна: розкид справжніх
 * висот заміряний по всіх трьох дзеркалах — 900…8000px, тобто заглушку видно з
 * першого погляду. Тому вона тепер справді ЗАПАСНА дорога (див. `frameCardH`),
 * а не єдина, як було до 03.09.2026.
 */
const FRAME_H_FALLBACK = 900;

/**
 * Запис кадру з маніфеста → `{ src, natW, natH }` (`natH === 0` — «розмір
 * невідомий», не «нуль»).
 *
 * ⛔ Форм ДВІ, і друга не для симетрії. `{path, w, h}` пише `publish_frames` із
 * 03.09.2026; РЯДКОМ (лише шлях) писала його перша версія. Живого превʼю зі
 * старою формою немає — маніфест узагалі існує тільки на цій невлитій гілці, я
 * заміряв історією, — але `ops/reseal_gate.py` перепечатує ЛИШЕ обгортку й
 * свідомо лишає маніфест від старої публікації. Тобто вже зібрана тека може
 * поїхати в деплой як є. Ціна прийняти обидві форми — один `typeof`; ціна не
 * прийняти — `img.src` дістає `[object Object]`, тобто битий кадр без імені
 * причини. Дорога «розміру немає — спитай знімок» усе одно мусить бути (запис,
 * що не пройшов валідацію публікації, розмірів не несе), і стара форма падає
 * рівно в неї, не додаючи гілки.
 *
 * Валідуємо ще раз ТУТ, хоч публікація вже валідувала: маніфест приїжджає
 * `fetch`-ем зі статики, тобто для оболонки він — чужі дані. `0` у знаменнику
 * пропорції дав би `Infinity`, рядок — `NaN`, і `rowsLayout` кинув би виняток
 * на світі, який глядач мав побачити.
 */
function frameShot(rec) {
  if (typeof rec === "string") return { src: rec, natW: 0, natH: 0 };
  if (!rec || typeof rec !== "object" || typeof rec.path !== "string") {
    return { src: null, natW: 0, natH: 0 };
  }
  /* Розмір — ПАРА: половина його не варта нічого (пропорція вимагає обох), а
     інваріант «або обидва, або жодного» не треба виводити заново в кожного,
     хто читає `natW`. Той самий вибір, що на python-боці (`_frame_size`). */
  const ok = (v) => typeof v === "number" && Number.isInteger(v) && v > 0;
  return ok(rec.w) && ok(rec.h)
    ? { src: rec.path, natW: rec.w, natH: rec.h }
    : { src: rec.path, natW: 0, natH: 0 };
}

/**
 * Висота картки з розміру, який заміряла зʼємка, — ДО завантаження кадру.
 *
 * ⛔ Ділимо на `natW`, а не беремо `natH` як є, і причина та сама, що в
 * `onFrameLoad`: кадр міг бути знятий із подвоєною щільністю, і тоді голе
 * `natH` дало б картку удвічі вищу за пропорцію. `natW` — ширина ЗНІМКА в
 * пікселях, `cardW` — ширина картки на полотні; ширина ВЬЮПОРТА до цієї
 * формули не входить узагалі (вона живе в ключі кадру).
 *
 * Розміру немає — повертаємо заглушку, а не вигадане число: світ мусить
 * визнати, що не знає, і дочекатись кадру (`onFrameLoad`).
 */
export function frameCardH(card, cardW) {
  return card.natW && card.natH
    ? Math.round((card.natH * cardW) / card.natW)
    : FRAME_H_FALLBACK;
}

/**
 * Дерево сторінок ітерації для `buildRows()` — із плаского маніфеста.
 *
 * `id` вузла — це `key` сторінки (база ключа КАДРУ), а не `id` у маніфесті: саме
 * його `buildRows` кладе в картку, а картці потрібен кадр. Шлях сторінки
 * (`id`/`path`) до картки додає `overviewRows` окремою мапою — злити ці два
 * рядки в один не можна, у неявної «Головної» вони розходяться назовсім
 * (`id` = `it1`, кадр лежить під `main`).
 *
 * `key` унікальний у межах ітерації (`validate` у `app/pages_model.py` цього
 * вимагає), тож мапа «key → сторінка» однозначна.
 */
export function extTree(man, it) {
  const pages = (man?.outline ?? man?.pages ?? []).filter((p) => p.it === it);
  const parent = depthParents(pages);
  const nodes = pages.map((p) => ({
    id: p.key,
    name: p.name,
    /* У маніфест їдуть ЛИШЕ видимі вузли (приховане піддерево сервер уже
       відсік), тобто схованих тут не буває. Ставимо явно, а не покладаємось на
       `!== false` усередині `buildRows`: поле несуче, і мовчазний дефолт зробив
       би наступну правку спільного модуля непомітною тут. */
    published: true,
    // з outline тека приїжджає явною; зі старого pages тек немає зовсім
    ...(p.kind ? { kind: p.kind } : {}),
    children: [],
  }));
  const roots = [];
  /* У старому превʼю сторінка з ТЕКИ приходить із `depth: 1` і без батька в
     переліку (теки в `pages` немає). З outline теки є, і вузол стає дитиною
     теки — `buildRows` спускається в неї сам. Сирота без батька
     стає КОРЕНЕМ, тобто дає свій ряд — рівно як в інструменті, де `visit` спускається
     в теку й кладе ряд на кожну справжню сторінку всередині. Приліпити його до
     попереднього кореня означало б показати чужу сторінку станом сусіда. */
  nodes.forEach((n, i) => {
    if (parent[i] >= 0) nodes[parent[i]].children.push(n);
    else roots.push(n);
  });
  return roots;
}

/**
 * Ряди «Огляду»: `[{ title, cards: [{ key, fkey, pageId, path, label, src, whyKey }] }]`.
 *
 * Склад ряду рахує СПІЛЬНИЙ `buildRows` (`app/rows-model.js`) — ряд це сторінка
 * й усе, що під нею. Другим аргументом іде порожній перелік вузлів графа, і це
 * не заглушка: `flow.json` у публікацію не їде взагалі, тобто СТАНІВ на
 * зовнішньому полотні немає за побудовою, і ряд схлопується до сторінки з
 * дітьми. Саме те, що `buildRows` і обіцяє робити без графа.
 *
 * `src` — шлях кадру зі статики або `null`; `whyKey` — імʼя ключа причини, чому
 * кадру немає (порожнє, коли кадр є). Причин ДВІ, і різні вони тому, що глядачу
 * треба різне: «цю ширину не знімали» рятує клік по сегменту ширин, «цю
 * сторінку не знімали» — не рятує нічим. Один спільний рядок відправляв би
 * половину людей тиснути кнопки без наслідку.
 */
export function overviewRows(man, ui) {
  const pages = (man?.pages ?? []).filter((p) => p.it === ui.it);
  const byKey = new Map(pages.map((p) => [p.key, p]));
  const frames = man?.frames?.[ui.it] ?? {};
  const w = overviewCardW(ui.vp);
  /* ⛔ Ширина живе в КЛЮЧІ кадру, і рахує його `frameKey` з `viewport.js` —
     та сама функція, що в інструменті, і той самий порт, що на python-боці
     (`split_frame_key` у `serve.py`). Своє правило тут означало б, що полотно
     шукає кадри під іменами, яких публікація не писала.
     `splitFrameKey` потрібен, щоб відрізнити «цієї ширини не знімали ЗОВСІМ»
     від «не знімали цю сторінку»: перше видно лише по ВСІХ ключах ітерації. */
  const anyOfWidth = Object.keys(frames).some((k) => splitFrameKey(k).w === w);
  return buildRows(extTree(man, ui.it), []).map((row) => ({
    title: row.title,
    cards: row.map((c) => {
      const fkey = frameKey(c.key, w);
      /* `natW`/`natH` — розмір, ЗАМІРЯНИЙ зʼємкою (`shots/manifest.json` →
         `publish_frames`). Ними висота картки відома ще до того, як кадр
         приїхав; `0` означає «невідомо», і тоді пропорцію повідомить сам
         знімок (`onFrameLoad`). Розбір форм — у `frameShot`. */
      const { src, natW, natH } = frameShot(frames[fkey]);
      const page = byKey.get(c.key);
      return {
        key: c.key,
        fkey,
        // Клік по картці відкриває СТОРІНКУ, тобто потрібен її шлях у publish.
        pageId: page?.id ?? null,
        path: page?.path ?? null,
        label: c.label,
        src,
        natW,
        natH,
        whyKey: src ? "" : (anyOfWidth ? "extNoFramePage" : "extNoFrameWidth"),
      };
    }),
  }));
}

/**
 * Розкладка й габарит світу «Огляду» — СПІЛЬНОЮ геометрією.
 *
 * ⛔ Жодного власного числа: `rowsLayout`/`worldBox` з `app/layout.js`,
 * константи з `app/canvas-geom.js`. Причина та сама, заради якої `canvas-geom`
 * узагалі існує: числа звідси видно НА ЕКРАНІ, і два місця, які їх рахують,
 * розходяться на першій же правці зазору — а тут другим місцем був би не тест,
 * а ЧУЖИЙ браузер, у який ніхто не дивиться.
 *
 * Зсув усіх рядів на `ROW_TITLE_TOP` — те саме, що в `gridPlaced()`
 * інструмента, і мусить бути ТУТ, бо його бачать обидва читачі розкладки
 * (розстановка карток і «вписати все»): порахований лише в одному, він зрізав
 * би низ останнього ряду. Потрібен він тому, що підпис стоїть НАД рядом, а
 * `#world` не має відʼємних координат — вище нуля камера не дивиться.
 *
 * `heightOf(card)` — висота КАДРУ без голови. Окремим параметром, а не полем
 * картки, свідомо: джерел у неї ДВА (розмір із маніфеста через `frameCardH` і
 * сам знімок через `onFrameLoad`), і чиста функція не мусить знати, котре з
 * них дало число цій картці.
 */
export function overviewWorld(rows, cardW, heightOf) {
  const placed = rowsLayout(
    rows.map((r) => r.cards.map((c) => ({ id: c.fkey, h: heightOf(c) }))),
    { cardW, gap: GAP, head: HEAD },
  ).map((p) => ({ ...p, y: p.y + ROW_TITLE_TOP }));
  return { placed, box: worldBox(placed, cardW) };
}

/**
 * Стан для `extBarHTML()`.
 *
 * Тег ітерації складається ТУТ, зі словника: маніфест везе `num` і `note`
 * окремо (`publish_manifest`), а «Іт.N»/«It.N» ліпить `iterTag` мовою
 * ГЛЯДАЧА. Доти сервер пік підпис цілком, і смуга показувала «Іт.1 ·
 * фікстура» поруч із «Layout / Overview / Copy link» — заміряно в браузері
 * 03.09.2026 при `dc-lang=en`. Мову вибирає той, хто дивиться; Python на
 * машині дизайнера її не знає й знати не може.
 *
 * Примітка йде ОКРЕМИМ полем, а не склеєна з тегом, бо розмітка поводиться з
 * ними по-різному: тег не обрізається ніколи, примітка обрізається завжди
 * (`.txt--fix` / `.txt--soft`) — див. `zone1()` в `ext-bar.js`. Склеєні, вони
 * дають крошку, у якій примітка зʼїдає номер версії.
 *
 * ⛔ Регекспу, який зрізає префікс із серверного підпису, тут НЕМА і бути не
 * може (охоронець — у `tests/ext-shell.test.mjs`). Інструмент такий регексп
 * тримає й мусить тримати кирилицею, бо розбирає `label_text` із `/api/task`;
 * скопійований сюди, він шукав би «Іт.3» у рядку «It.3» — не знаходив і тихо
 * лишав кирилицю в English-режимі, тобто відтворював рівно ту саму ваду.
 */
export function extBarState(man, ui) {
  const iters = man?.iters ?? [];
  const tag = (it) => t("iterTag", it.num);
  const cur = iters.find((x) => x.id === ui.it);
  return {
    task: man?.task ?? "",
    iterLabel: cur ? tag(cur) : "",
    iterNote: cur?.note ?? "",
    iters: iters.map((x) => ({
      id: x.id, label: tag(x), note: x.note ?? "", on: x.id === ui.it,
    })),
    openDd: ui.openDd,
    /* РЕАЛЬНИЙ режим, а не той, який просили (див. `effMode`): натиснутий
       сегмент «Огляд» над макетом — це контрол, що бреше про стан. */
    mode: effMode(man, ui),
    vp: ui.vp,
    overviewWhyKey: overviewWhyKey(man, ui.it),
    copied: !!ui.copied,
    error: ui.error || "",
  };
}

/* ── проводка ───────────────────────────────────────────────────────────── */

/** Згорнутість панелі памʼятається в браузері ГЛЯДАЧА: згорнув — лишилось. */
const COLLAPSE_KEY = "dc-ext-collapsed";

const ui = {
  it: null, page: null, mode: "layout", vp: "desktop", openDd: null,
  expanded: new Set(), collapsed: false, copied: false, error: "",
};
let man = null;
let copyTimer = null;

/**
 * Модель острівця превʼю (0.32.0). «Коментарі» зʼявляються лише коли збірка має командні коментарі (Task 3), «Інспектор» —
 * коли оболонка вміє його показати (Task 4): ці прапорці перемикають ті задачі, а «Сховати інтерфейс» є завжди.
 */
const island = { comments: false, inspector: false, last: null };

/** Панель командних коментарів (Task 3): створюється в `open()`, лише коли збірка їх має (`manifest.comments`). */
let cmt = null;

/** Набір кнопок острівця за прапорцями; порядок і роздільники — у `islandToolsHTML`. «Коментарі» — лише там, де є живий макет
 *  (в «Огляді» кадри — знімки, коментатора в них нема). */
function islandTools() {
  const live = effMode(man, ui) !== "overview";
  return [island.comments && live && "cmt", island.inspector && "insp", "clean"].filter(Boolean);
}

/** Закрити бічні панелі превʼю (коментарі, інспектор): «Сховати інтерфейс» їх закриває; інспектор докладе Task 4. */
function closeSidePanels() { cmt?.setOpen(false); }

/** Острівець унизу по центру: монтується в `#hud` обгортки (у старої обгортки точки нема — тоді нічого й не малюємо). */
function paintIsland() {
  const hud = el("hud");
  if (!hud) return;
  const html = `<div class="island" role="group" aria-label="${t("islandNav")}"><div class="isl-tools">`
    + `${islandToolsHTML({ tools: islandTools(), commentsOn: !!cmt?.isOpen(), commentsCount: cmt ? cmt.count() : 0 })}</div></div>`;
  if (html === island.last) return;
  island.last = html;
  hud.innerHTML = html;
}

const el = (id) => document.getElementById(id);
const pageById = (id) => (man?.pages ?? []).find((p) => p.id === id) ?? null;

/** Панель створюється РАЗ (як `#pages-panel` в інструменті), не щорендера. */
function panelNode() {
  let node = el("pages-panel");
  if (!node) {
    node = document.createElement("div");
    node.id = "pages-panel";
    document.body.appendChild(node);
  }
  return node;
}

function paint() {
  el("bar").innerHTML = extBarHTML(extBarState(man, ui));
  const node = panelNode();
  node.className = `panel${ui.collapsed ? " panel--rail" : ""}`;
  node.innerHTML = panelHTML(extPanelState(man, ui));
  cmt?.setActive(effMode(man, ui) !== "overview");
  paintIsland();
  document.body.classList.add("with-panel");
  document.body.classList.toggle("panel-collapsed", ui.collapsed);
}

/** Обрана ширина — у стиль, звідки її бере `body.vp-fixed .cv-frame`. */
function applyVp() {
  const w = vpWidth(ui.vp);
  document.body.classList.toggle("vp-fixed", w !== null);
  if (w === null) document.body.style.removeProperty("--cv-vpw");
  else document.body.style.setProperty("--cv-vpw", `${w}px`);
}

/* ── полотно «Огляду» ───────────────────────────────────────────────────── */

/** Ключ СВІТУ: інша ітерація чи інша ширина — інші кадри, інша розкладка. */
/* Розділювач — ЕКРАНОВАНИЙ `\u0000`, а не сам байт. Значення те саме,
   але сирий NUL робив файл бінарним для `file(1)`, а `grep` бінарні файли
   ТИХО пропускає — тобто будь-яка перевірка на grep-і переставала бачити
   цей модуль зовсім. Охоронець — `tests/no-control-bytes.test.mjs`. */
const worldKey = () => `${ui.it}\u0000${ui.vp}`;

let ovRows = [];            // ряди з `overviewRows`, картки в них несуть `h`/`el`
let ovCards = [];           // ті самі картки пласким переліком
let ovBox = { w: 0, h: 0 }; // габарит світу останньої розкладки
let ovW = CANVAS_W;         // ширина картки цього світу
let ovKey = null;           // `worldKey()` того світу, що зараз на полотні
/** Камеру рухала РУКА глядача — «вписати все» більше не перевписує її сама. */
let ovMoved = false;
const cam = { x: 0, y: 0, scale: 1 };
let camQuant = null;
let layoutRaf = null;

/**
 * Полотно створюється РАЗ і саме тут, а не в обгортці превʼю (`serve.py`).
 *
 * Причина: обгортка — тонкий каркас, і `#canvas`/`#world` у ньому були б
 * розміткою, потрібною лише одному з двох режимів. Та сама ідіома, що вже
 * стоїть для `#pages-panel` вище.
 */
function canvasNode() {
  let node = el("canvas");
  if (!node) {
    node = document.createElement("div");
    node.id = "canvas";
    node.className = "cv-canvas";
    node.hidden = true;
    const world = document.createElement("div");
    world.id = "world";
    world.className = "cv-world";
    node.appendChild(world);
    document.body.appendChild(node);
    wireCanvas(node);
  }
  return node;
}

/** Заглушка з ПРИЧИНОЮ замість порожнього прямокутника. */
function placeholder(body, reason) {
  const ph = document.createElement("div");
  ph.className = "cv-card-ph";
  // `textContent`: причина складається з ключа словника, але сусідній шлях
  // приходить із маніфеста — правило одне на все, що малює цей файл.
  ph.textContent = reason;
  body.innerHTML = "";
  body.appendChild(ph);
}

/** Один кадр на полотні. Розмітка — та сама, що в інструменті (спільний CSS). */
function ovCardNode(card) {
  const node = document.createElement("div");
  node.className = "cv-card";
  /* Шлях сторінки в `dataset` — щоб клік не шукав картку по координатах: та
     сама ідіома, що `data-key` в інструменті. */
  node.dataset.page = card.pageId ?? "";
  node.dataset.key = card.fkey;

  const head = document.createElement("div");
  head.className = "cv-card-head";
  /* Текстовим вузлом, не `innerHTML`: імʼя сторінки приходить із `pages.json`,
     який пишуть руками, — те саме правило, що на підписі ряду в інструменті.
     ⛔ Крапки «у превью» тут немає з тієї самої причини, що в дереві панелі: у
     маніфест їдуть лише опубліковані сторінки, тобто крапка стояла б на кожній
     картці й не відрізняла б нічого. */
  head.appendChild(document.createTextNode(card.label));
  const open = document.createElement("button");
  open.type = "button";
  open.className = "cv-open";
  open.title = t("cardOpenTitle");
  open.innerHTML = `${ico("ext", 14)}<span>${t("openFrame")}</span>`;
  head.appendChild(open);
  node.appendChild(head);

  const body = document.createElement("div");
  body.className = "cv-card-body";
  if (card.src) {
    const img = document.createElement("img");
    img.alt = "";
    /* `draggable=false` — не косметика: без нього кадр «відтягується» з полотна
       як файл (native drag браузера), і жест панорами часом кінчається привидом
       картинки в руці. */
    img.draggable = false;
    img.decoding = "async";
    /* ⛔ Ліниве завантаження тут НЕ оптимізація. Заміряно на `boss-interface/it3`
       02.09.2026: 66 кадрів / 15.3M, тобто ~237K на кадр. Без `lazy` вкладка
       глядача тягне все це відразу — і на «Огляді», у який він може й не зайти. */
    img.loading = "lazy";
    img.src = card.src;
    img.addEventListener("load", () => onFrameLoad(card, img));
    /* Запис у маніфесті є, а файл не доїхав: `publish/` збирається копіюванням,
       і кадр — окремий файл. Без цього обробника картка показує іконку битої
       картинки, тобто дірку без імені. */
    img.addEventListener("error", () => placeholder(body, t("badgeUnreadable")),
      { once: true });
    body.appendChild(img);
  } else {
    placeholder(body, t(card.whyKey, ovW));
  }
  node.appendChild(body);
  return node;
}

/**
 * Пропорція кадру — від самого знімка. ЗАПАСНА дорога, не єдина.
 *
 * Розмір, заміряний зʼємкою, приїжджає в маніфесті, і висоту картки ставить
 * `frameCardH` ще до завантаження. Цей обробник лишається тому, що розміру
 * може не бути: превʼю, зібране до 03.09.2026 (`frames[fid]` там рядок), або
 * запис, чий `w`/`h` не пройшов валідацію в `publish_frames`. Коли розмір є,
 * порахована тут висота з ним збігається — і `h === card.h` нижче гасить
 * зайвий перерахунок розкладки.
 *
 * Ділимо на `naturalWidth`, а не беремо `naturalHeight` як є: кадр міг бути
 * знятий із подвоєною щільністю, і тоді голе `naturalHeight` дало б картку
 * удвічі вищу за пропорцію. Та сама формула, що в `frameCardH`.
 */
function onFrameLoad(card, img) {
  if (!img.naturalWidth || !img.naturalHeight) return;
  const h = Math.round((img.naturalHeight * ovW) / img.naturalWidth);
  if (h === card.h) return;
  card.h = h;
  scheduleLayout();
}

/**
 * Розкладка не щокадру, а раз на анімаційний кадр.
 *
 * Кадри приїжджають по одному (`lazy`), а розкладка чіпає ВСІ картки: без цієї
 * склейки 66 знімків давали б 66 повних проходів по DOM, і кожен — синхронний
 * перерахунок стилю під рукою глядача.
 */
function scheduleLayout() {
  if (layoutRaf !== null) return;
  layoutRaf = requestAnimationFrame(() => {
    layoutRaf = null;
    layoutOverview();
    /* Камера, яку глядач не чіпав, мусить лишитись «вписати все» — інакше
       кадри, що доїжджають, розсувають світ під нерухомою камерою, і частина
       полотна тихо виїжджає за край. */
    if (!ovMoved) fitOverview();
  });
}

function buildOverview() {
  const world = canvasNode().querySelector("#world");
  world.innerHTML = "";
  ovW = overviewCardW(ui.vp);
  ovRows = overviewRows(man, ui);
  ovCards = [];
  for (const row of ovRows) {
    for (const card of row.cards) {
      /* Висота ВІДРАЗУ з маніфеста: інакше світ стоїть заглушкою й «сідає» під
         справжні пропорції, коли кадри доїдуть (на повільній мережі глядач
         якийсь час бачить геометрію, яка бреше про розміри). Кадр, чийого
         розміру в маніфесті немає, дістає заглушку — і його пропорцію
         донесе `onFrameLoad`. */
      card.h = frameCardH(card, ovW);
      card.el = ovCardNode(card);
      world.appendChild(card.el);
      ovCards.push(card);
    }
  }
  /* Ключ ставимо ТУТ, після побудови: помилка вище не сміє лишити його
     вказувати на світ, якого на полотні немає. */
  ovKey = worldKey();
  ovMoved = false;
  layoutOverview();
  fitOverview();
}

function layoutOverview() {
  const world = el("world");
  if (!world) return;
  const { placed, box } = overviewWorld(ovRows, ovW, (c) => c.h);
  ovBox = box;
  const at = new Map(placed.map((p) => [p.id, p]));
  for (const card of ovCards) {
    const p = at.get(card.fkey);
    if (!p) continue;
    card.x = p.x;
    card.y = p.y;
    card.el.style.cssText = `left:${p.x}px;top:${p.y}px;width:${ovW}px;height:${p.h}px`;
  }
  /* Підпис ряду — окреме дитя світу, а не вміст першої картки: він належить
     РЯДУ, стоїть ВИЩЕ за картки і живе поза їхніми межами (усередині картки
     його зрізала б сама картка). Малюється тут, бо `top` рахується від `y`
     ряду, а `y` зʼявляється лише після розкладки; підписи МИНУЛОЇ розкладки
     знімаємо рядком нижче, інакше кожен доїхавший кадр лишав би по підпису. */
  world.querySelectorAll(".cv-row-title").forEach((n) => n.remove());
  for (const row of ovRows) {
    const first = row.cards[0];
    if (!first) continue;   // `buildRows` завжди кладе саму сторінку — тотальність
    const label = document.createElement("div");
    label.className = "cv-row-title";
    label.style.cssText = `left:${first.x}px;top:${first.y - ROW_TITLE_TOP}px`;
    label.textContent = row.title;
    world.appendChild(label);
  }
}

function applyCam() {
  const world = el("world");
  if (!world) return;
  world.style.transform = `translate(${cam.x}px,${cam.y}px) scale(${cam.scale})`;
  /* Масштаб У СТИЛЬ — щоб підпис ряду вирахував свій кегль через `calc()` і не
     зникнув на дрібному зумі (він живе у світі, отже масштабується разом із
     ним). Змінна на `#world` УСПАДКОВУЄТЬСЯ, тобто кожен її запис інвалідує
     стиль усім карткам і підписам, тому пишемо лише на РЕАЛЬНІЙ зміні, а
     «реальну» рахуємо грубою сіткою `quantScale`. */
  const q = quantScale(cam.scale);
  if (q !== camQuant) {
    camQuant = q;
    world.style.setProperty("--cv-scale", q);
  }
}

/** Габарит полотна, або `null`, поки його немає (сховане, ще не в дереві). */
function canvasView() {
  const canvas = el("canvas");
  if (!canvas || canvas.hidden || !canvas.clientWidth || !canvas.clientHeight) return null;
  return { w: canvas.clientWidth, h: canvas.clientHeight };
}

function fitOverview() {
  const view = canvasView();
  if (!view) return;
  Object.assign(cam, fitBox(ovBox, view));
  applyCam();
}

/**
 * Привести камеру до кадру сторінки й підсвітити його: клік по рядку панелі.
 *
 * Масштаб рахує `focusBox` — по ШИРИНІ кадру, а не по габариту: кадр буває
 * 8000px високий, і вписаний цілком він дав би той самий bird-view, з якого
 * глядач і тікає, натискаючи рядок.
 */
function focusCard(pageId) {
  const card = ovCards.find((c) => c.pageId === pageId) ?? null;
  // Підсвітка — це «куди ми щойно полетіли», тому знімається з усіх решти.
  for (const c of ovCards) c.el.classList.toggle("sel", c === card);
  const view = canvasView();
  /* Сторінка без картки. Пройти цим шляхом сьогодні НІЩО не може: і рядки
     панелі, і картки полотна будуються з того самого `man.pages` тієї самої
     ітерації. Це охорона КОНТРАКТУ, живою перевіркою не покрита — сказано
     вголос, щоб її не рахували доведеною. */
  if (!card || !view) return;
  // Переліт — рух камери РУКОЮ, отже ресайз вікна більше не вписує все заново.
  ovMoved = true;
  Object.assign(cam, focusBox({ x: card.x, y: card.y, w: ovW }, view));
  applyCam();
}

/** Відкрити «Макет» на сторінці цієї картки. */
function openCard(target) {
  const node = target?.closest?.(".cv-card");
  if (!node || !node.dataset.page) return;
  ui.mode = "layout";
  goto(node.dataset.page);
}

/**
 * Проводка полотна — СВОЯ, не через `data-act`, і причина структурна: клік по
 * картці треба відрізнити від панорами, а делегація по атрибуту цього не може
 * (обидва жести кінчаються тим самим `click` на тій самій картці). Тому тут
 * pointer-жест із порогом, як у холсті інструмента.
 */
function wireCanvas(canvas) {
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => {
    /* Кнопка ВСЕРЕДИНІ кадру: не починаємо драг і не забираємо вказівник,
       інакше полотно дістає pointer capture, `click` народжується на ньому, а
       не на кнопці — і кнопка «працює» лише випадковим шляхом. */
    if (e.target.closest(".cv-open")) return;
    drag = { sx: e.clientX, sy: e.clientY, ox: cam.x, oy: cam.y, moved: false, t: e.target };
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add("dragging");
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.sx;
    const dy = e.clientY - drag.sy;
    // Поріг: тремтіння руки на кліку не сміє вважатись перетягуванням.
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; ovMoved = true; }
    cam.x = drag.ox + dx;
    cam.y = drag.oy + dy;
    applyCam();
  });
  canvas.addEventListener("pointerup", () => {
    if (!drag) return;
    const { moved, t: target } = drag;
    drag = null;
    canvas.classList.remove("dragging");
    if (!moved) openCard(target);        // клік без руху = відкрити
  });
  /* Скасований жест (системний свайп, вирване вікно) не сміє лишити полотно в
     стані «тягну»: інакше курсор лишається «в руці», а наступний рух мишею без
     кнопки продовжує панораму. */
  canvas.addEventListener("pointercancel", () => {
    drag = null;
    canvas.classList.remove("dragging");
  });
  /* Кнопка живе на `click`, а не на `pointerup` полотна: `click` народжується
     і від Enter/пробілу, тобто кнопка працює й з клавіатури. */
  canvas.addEventListener("click", (e) => {
    if (e.target.closest(".cv-open")) openCard(e.target);
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    ovMoved = true;
    const r = canvas.getBoundingClientRect();
    /* Зум навколо курсора рахує `zoomAt` — світова точка під курсором лишається
       під курсором. ⚠️ Згладжування (`camTo`/`step` в інструменті) тут свідомо
       НЕМА: план цих імен не називає, а rAF-цикл камери — це ще один стан, який
       може писати поверх руки. Зум застосовується синхронно, як робив холст
       інструмента до появи ощущалки. */
    Object.assign(cam, zoomAt(cam, {
      cx: e.clientX - r.left, cy: e.clientY - r.top, delta: e.deltaY,
    }));
    applyCam();
  }, { passive: false });
  /* Розгорнуте вікно лишало б полотно в куті на масштабі, порахованому для
     маленького. Лише поки камеру не чіпала рука — інакше ресайз відкидав би
     глядача з кадру назад у bird-view. */
  addEventListener("resize", () => { if (!ovMoved) fitOverview(); });
}

/**
 * Перейти на сторінку: стан, адреса й показ.
 *
 * `focus` — «глядач сам попросив цю сторінку» (рядок панелі, картка полотна).
 * У «Огляді» це не перебудова світу, а переліт камери до кадру; у «Макеті» —
 * той самий показ, що й без прапорця.
 */
function goto(id, { focus = false } = {}) {
  const p = pageById(id);
  if (!p) return;
  ui.page = id;
  ui.it = p.it;
  /* `replaceState`, не `pushState`: перемикання сторінок у превʼю — це не
     навігація по історії, і «назад» мусить вести туди, звідки глядач прийшов,
     а не через двадцять макетів. */
  try {
    history.replaceState(null, "",
      `${location.pathname}${location.search}#p=${encodeURIComponent(id)}`);
  } catch (e) { /* превʼю, відкрите з диска: hash не критичний */ }
  apply({ focus });
}

/**
 * Показати те, що зараз у стані: сцена або полотно, плюс перемалювати смугу.
 *
 * Режим береться `effMode`, а не з `ui.mode`: ітерація без кадрів схлопує
 * «Огляд» у «Макет», і робити це мусить ОДНЕ місце — інакше сцена й сегмент
 * смуги розійшлися б у тому, що показують.
 */
function apply({ focus = false } = {}) {
  const mode = effMode(man, ui);
  if (mode === "overview") {
    /* Ховаємо СЦЕНУ, а не рамку: рамка лежить у сцені, і сцена зі своєю
       підкладкою накрила б полотно світлим прямокутником (та сама причина, що
       в `applyMode` інструмента). */
    el("stage").hidden = true;
    const canvas = canvasNode();
    canvas.hidden = false;
    /* Світ перебудовується лише коли він СПРАВДІ інший (інша ітерація чи інша
       ширина — інші кадри). Інакше повернення в «Огляд» скидало б камеру, яку
       глядач щойно наставив рукою: те саме рішення, що `camWorld` в
       інструменті, лише ключ тут простіший — зʼємки й флоу в статиці немає. */
    if (ovKey !== worldKey()) buildOverview();
    else if (focus) focusCard(ui.page);
  } else {
    const canvas = el("canvas");
    if (canvas) canvas.hidden = true;
    el("stage").hidden = false;
    const p = pageById(ui.page);
    if (p) {
      /* Нова сторінка — старі картки з мертвими діями не лишаємо, доки вона не надішле свій список. */
      cmt?.dropFrame();
      el("frame").src = p.path;
    }
  }
  paint();
}

function setCollapsed(v) {
  ui.collapsed = v;
  try { localStorage.setItem(COLLAPSE_KEY, v ? "1" : "0"); } catch (e) {}
  paint();
}

function copyLink() {
  const url = copyUrl(location, String(window.__extPw ?? ""), ui.page || "");
  const done = () => {
    ui.copied = true;
    paint();
    clearTimeout(copyTimer);
    copyTimer = setTimeout(() => { ui.copied = false; paint(); }, 1600);
  };
  /* Запасний шлях, коли буфер обміну недоступний (не-https, відмовлені права,
     сторінка не у фокусі): показуємо адресу, а не питаємо — поле лишається
     виділюваним, і глядач копіює руками. Той самий виклик, що в інструменті
     (`BAR_ACTIONS.copylink`), і свідомо НЕ `prompt()`: браузер уміє вимкнути
     всі три примітиви діалогів, після чого вони мовчки віддають `null` —
     тобто фолбек, який мав урятувати, тихо не показав би нічого. Це не наша
     обережність, а правило проєкту, і його стереже `tests/browser-dialogs.test.mjs`.
     Ціна — `ask.js` у переліку спільних модулів; він тягне лише `i18n.js`,
     тобто замкнутість переліку не змінилась. */
  const fallback = () => ask(t("askCopyLinkPrompt"), url, { readOnly: true });
  try {
    navigator.clipboard.writeText(url).then(done, fallback);
  } catch (e) {
    fallback();
  }
}

/**
 * Що робить клік по рядку превʼю: тека (є лише в `outline`) розгортається, решта
 * — перехід. Теки нема в `pages`, тож `goto` на неї вів би на сторінку, якої не
 * існує; старе превʼю без `outline` теки не має й веде себе як раніше.
 */
export function rowAction(man, id) {
  return (man?.outline ?? []).find((p) => p.id === id)?.kind === "folder" ? "toggle" : "goto";
}

/**
 * Імʼя дії → функція. ОДИН реєстр на смугу й панель: імена не перетинаються, а
 * два реєстри — два місця, куди можна не дописати рядок (див. шапку).
 */
const EXT_ACTIONS = {
  /* `focus`: рядок панелі — це прохання глядача про САМЕ ЦЮ сторінку, тобто в
     «Огляді» камера летить до її кадру, а не лишається там, де стояла. */
  page: (val) => (rowAction(man, val) === "toggle" ? EXT_ACTIONS.toggle(val) : goto(val, { focus: true })),
  toggle: (val) => {
    if (ui.expanded.has(val)) ui.expanded.delete(val);
    else ui.expanded.add(val);
    paint();
  },
  panel: () => setCollapsed(!ui.collapsed),
  iter: (val) => {
    const first = (man?.pages ?? []).find((p) => p.it === val);
    if (first) goto(first.id);
  },
  mode: (val) => {
    if (val === ui.mode) return;
    ui.mode = val;
    apply();
  },
  vp: (val) => {
    if (val === ui.vp) return;
    ui.vp = val;
    applyVp();
    // Інша ширина — інші КАДРИ, не масштаб тих самих: `apply` побачить це по
    // `worldKey()` і збере світ заново.
    apply();
  },
  copylink: () => copyLink(),
  /* Кнопка острівця «Сховати інтерфейс» — той самий перемикач, що й акорд ⇧⌘\\. */
  clean: () => toggleClean(true),
  /* Перезавантаження, а не повторний `fetch`: маніфест не прочитався — це або
     недоїхала публікація, або мережа глядача, і в обох випадках чесніше
     перезібрати сторінку цілком, ніж лагодити половину стану. */
  retry: () => location.reload(),
};
/* Дії панелі коментарів — через ТОЙ САМИЙ реєстр і ту саму делегацію. Закрити/відкрити знову/доручити тут нема взагалі:
   дії, якої немає в реєстрі, не викличе й підроблена розмітка. */
for (const act of CMT_ACTS) EXT_ACTIONS[act] = (val, node, ev) => cmt?.actions[act]?.(val, node, ev);

function wire() {
  document.addEventListener("click", (ev) => {
    const target = ev.target.closest("[data-act],[data-dd]");
    if (!target || target.disabled) {
      // Клік мимо контрола закриває дропдаун — інакше він висить над макетом.
      if (ui.openDd) { ui.openDd = null; paint(); }
      return;
    }
    if (target.dataset.dd) {
      ui.openDd = ui.openDd === target.dataset.dd ? null : target.dataset.dd;
      paint();
      return;
    }
    ui.openDd = null;
    EXT_ACTIONS[target.dataset.act]?.(target.dataset.val, target, ev);
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && ui.openDd) { ui.openDd = null; paint(); }
    /* C — панель коментарів; поле вводу, модальний шар (діалог імені, питання) і модифікатори — не наші. */
    if (cmt && !ev.metaKey && !ev.ctrlKey && !ev.altKey && !ev.shiftKey && !ev.repeat && !ev.isComposing && !ev.defaultPrevented
        && (ev.key || "").toLowerCase() === "c" && !document.querySelector(".cv-ask-scrim, .cv-ask-pop")
        && !/^(input|textarea|select)$/i.test(ev.target?.localName || "") && !ev.target?.isContentEditable
        && effMode(man, ui) !== "overview" && !clean) {
      ev.preventDefault();
      cmt.toggle();
    }
    /* ⇧⌘\\ — чистий перегляд макета, як у канвасі (fb-01102026-7f7b6d). */
    if ((ev.metaKey || ev.ctrlKey) && ev.shiftKey && !ev.altKey && ev.code === "Backslash") {
      ev.preventDefault();
      toggleClean();
    }
  });
  /* Новий документ рамки — свій слухач акорду і сховані піни, якщо режим увімкнено. */
  el("frame")?.addEventListener("load", () => {
    syncFrame(el("frame"), clean, () => toggleClean());
    cmt?.onFrameLoad();
  });
  /* Посилки коментатора з рамки (режим хоста превʼю). Джерело й origin перевіряє сам контролер. */
  window.addEventListener("message", (ev) => {
    const m = ev.data;
    if (cmt && m && m.type === "dc-comments" && CMT_EVENTS.has(m.ev)) cmt.onMessage(ev);
  });
  /* Скільки знизу рамки перекриває острівець: форма коментаря в макеті лягає над ним (`PREVIEW_HOST_ARG.bottomInset`). */
  window.__dcIslandInset = () => {
    const f = el("frame")?.getBoundingClientRect();
    const i = el("hud")?.querySelector(".island")?.getBoundingClientRect();
    return i && i.height && f ? Math.max(0, Math.round(f.bottom - i.top + 8)) : 0;
  };
}

/** Чистий перегляд у превʼю: оболонка й піни сховані, кнопка повернення — завжди. */
let clean = false;
function toggleClean(on = !clean) {
  clean = on;
  if (on) closeSidePanels();
  applyClean(document, el("frame"), on, { label: t("cleanExit"), title: t("cleanExitTitle"),
    onExit: () => toggleClean(false), onChord: () => toggleClean() });
}

/**
 * Показати оболонку. Кличе це ЛИШЕ гейт — і в цьому весь запобіжник:
 *
 * ⛔ рамка не сміє поїхати до пароля. Внутрішні сторінки превʼю теж під
 *    гейтом (з 03.08.2026, після того як пряме посилання на них минало
 *    пароль), тож завантажена наперед рамка показала б глядачеві ДРУГИЙ гейт
 *    усередині першого — це вже ловили живцем.
 * ⛔ назва задачі не сміє потрапити у `<title>` до пароля (правило
 *    30.07.2026: URL превʼю може потрапити кому завгодно, контекст — лише за
 *    паролем). Тому `document.title` ставиться саме тут, а не в обробнику
 *    завантаження маніфеста: маніфест вантажиться НАПЕРЕД, ще під закритим
 *    гейтом, і присвоєння назви в його `then` світило б задачу у вкладці.
 */
async function open() {
  man = await loading;
  paint();
  if (ui.error) return;
  if (man?.task) document.title = man.task;
  /* Командні коментарі — лише коли збірка їх має (`manifest.comments`); без них ні кнопки, ні панелі. */
  if (man?.comments && typeof man.comments === "object") {
    let mount = el("cmt-panel");
    if (!mount) {          // обгортка до 0.32.0 точки не має — створюємо сами (нова оболонка в старій обгортці)
      mount = document.createElement("div");
      mount.id = "cmt-panel";
      mount.className = "insp cmt";
      mount.hidden = true;
      document.body.appendChild(mount);
    }
    cmt = createExtComments({ frame: el("frame"), mount, channel: String(man.comments.channel || ""), onChange: paintIsland,
      canToggle: () => !clean && effMode(man, ui) !== "overview" });
    island.comments = true;
    paintIsland();
  }
  applyVp();
  const first = startPage(man, location.hash);
  if (first) goto(first);
}

/**
 * Маніфест — окремим файлом і `fetch`-ем, НЕ інлайном в обгортку.
 *
 * Причина знайдена виконанням: `ops/reseal_gate.py` перезбирає ЛИШЕ
 * `publish/index.html` і кадрів не рахує взагалі. Інлайнений стан означав би,
 * що після кожного перепечатування гейту обгортка везе НОВИЙ скрипт і СТАРІ
 * дані — тихо, без жодної ознаки. Окремий файл пише лише публікація, тож
 * reseal не має чого зістарити.
 *
 * Вантажиться одразу, а показується під відкритим гейтом (див. `open`): дві
 * фази замість однієї, щоб пароль не оплачувався ще й очікуванням мережі.
 */
let loading = null;

function load() {
  return fetch("manifest.json")
    .then((res) => {
      if (!res.ok) throw new Error(String(res.status));
      return res.json();
    })
    .catch((e) => {
      /* Мовчазна гілка тут була б найгіршою: оболонка піднялась, дерево
         порожнє, і ніде жодного слова про причину — а глядач не має ні
         консолі, ні наміру в неї дивитись. */
      ui.error = t("errPagesLoadFailed", String(e?.message || e));
      return null;
    });
}

function start() {
  el("sprite").innerHTML = SPRITE;
  // Мова — з локального сховища, як в `app.js`: `i18n.js` чистий і сам
  // localStorage не читає.
  try { setLang(readStoredLang(localStorage.getItem(LANG_KEY))); } catch (e) {}
  try { ui.collapsed = localStorage.getItem(COLLAPSE_KEY) === "1"; } catch (e) {}
  loading = load();
  wire();
  if (window.__gateOpen) open();
  else window.__onGateOpen = open;
}

/* ⚠️ Межа, через яку цей файл узагалі можна імпортувати юнітом: у node немає
   DOM, і без цієї перевірки `tests/ext-shell.test.mjs` падав би на першому ж
   `getElementById`, тобто адаптер лишився б без юнітів. У браузері умова
   істинна завжди. */
if (typeof document !== "undefined") start();
