/**
 * Чиста модель флоу: ключ кадру, перевірка станів, ранги вузлів.
 * Ні DOM, ні fetch — модуль тестується юнітами і імпортується І браузером,
 * І `bin/shoot.mjs`. Саме тому ключ кадру живе тут, в ОДНІЙ реалізації.
 */
import { t } from "./i18n.js";
import { kindOf } from "./tree-model.js";

/** Наші власні параметри URL. Стан екрана не сміє їх захопити. */
export const RESERVED_Q = new Set(["it", "page", "bare", "ch", "v", "host"]);

/**
 * Ключ кадру: сторінка + стан. НЕ штамп вмісту — штампи рахує лише
 * `bin/shots-stamp.mjs`, і плутати їх не можна. Це просто безпечне для файлової
 * системи імʼя, стабільне між прогонами.
 */
export function shotKey(page, state) {
  const q = normalizeState(state);
  if (!q.length) return page;
  // FNV-1a 32 біт: короткий, детермінований, без залежностей.
  let h = 0x811c9dc5;
  for (const ch of q.map(pair).join("&")) {
    h ^= ch.codePointAt(0);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `${page}~${h.toString(16).padStart(8, "0")}`;
}

/**
 * Значення `v=` у `<img src="/shot?…">` — ключ ВІЧНОГО кешу кадру.
 *
 * Тут, а не в `app/app.js`, з тієї самої причини, що й `shotKey`: ключ мусить
 * мати ОДНУ реалізацію, і тест мусить питати саме ту, якою малює канвас.
 * `/shot` віддається з `immutable, max-age=31536000` (serve.py), тобто помилка
 * в цьому рядку — це кадр, застряглий у браузері на рік.
 *
 * Три складові, і жодна не зайва:
 *   • `sha` — хеш БАЙТІВ кадру. Єдина, що міняється від самої перезйомки, і
 *     саме заради неї цей ключ переписаний: `stamp` + `capturedAt` давали
 *     ІДЕНТИЧНИЙ URL двом зйомкам в одну хвилину з різними байтами (виміряно:
 *     `stampTime(16:30:05) === stampTime(16:30:58)`), а це основний цикл —
 *     «Перезняти» → кадр битий → «Перезняти» ще раз через 10 секунд.
 *   • `capturedAt` — записи, зняті ДО появи `sha`, інакше змінили б ключ на
 *     порожній і сходили б у мережу дарма; для них хвилинної точності
 *     принаймні не менше, ніж було.
 *   • `stamp` — з тієї ж причини сумісності зі старими манифестами.
 * Порядок і крапки фіксовані: ключ мусить бути стабільним між рендерами.
 */
export function shotVersion(shot) {
  const s = shot || {};
  return `${s.stamp || ""}.${s.capturedAt || ""}.${s.sha || ""}`;
}

/** Хвіст URL для стану, у стабільному порядку. Порожній стан — порожній рядок. */
export function stateQuery(state) {
  return normalizeState(state).map((kv) => `&${pair(kv)}`).join("");
}

/**
 * Один параметр стану — В ОДНОМУ вигляді і для ключа кадру, і для URL.
 *
 * Спільна функція тут не косметика. Поки `shotKey` хешував сирий `k=v`, а
 * `stateQuery` екранував, дві функції одного файла розходились у тому, що
 * вважають однаковим станом: `{a:"1", b:"2"}` і `{a:"1&b=2"}` давали ОДИН ключ.
 * Наслідок гірший за колізію кадру — `readFlow` звинувачував автора в дублі
 * екрана, якого той не робив, і викидав вузол. Цілком реально на `{q:"закон&право"}`.
 */
function pair([k, v]) {
  return `${encodeURIComponent(k)}=${encodeURIComponent(v)}`;
}

/**
 * Кидає, якщо стан не обʼєкт або намагається перевизначити наші параметри.
 *
 * Перевірка типу тут, а не «десь у викликачі»: найімовірніша описка автора —
 * `"state": "empty"` замість `"state": {"state": "empty"}`. Без неї
 * `Object.entries("empty")` мовчки розбирало рядок на літери, вузол діставав
 * URL `&0=e&1=m&2=p&3=t&4=y` і виглядав законним другим екраном, а `42` і `true`
 * так само тихо ставали «станом без ключів», тобто просто ще однією копією
 * сторінки. `problems` при цьому лишався порожній.
 */
export function checkState(state) {
  if (state !== undefined && state !== null
      && (typeof state !== "object" || Array.isArray(state))) {
    const got = Array.isArray(state) ? t("flowArray") : typeof state;
    throw new Error(t("flowStateNotObject", got));
  }
  for (const [k] of normalizeState(state)) {
    if (RESERVED_Q.has(k)) {
      throw new Error(t("flowStateReserved", k));
    }
  }
  return state;
}

/** Пари ключ-значення, відсортовані: {b:2,a:1} і {a:1,b:2} — той самий екран. */
function normalizeState(state) {
  return Object.entries(state ?? {})
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
}

/**
 * Ранг вузла = найдовший шлях від входу. Саме НАЙДОВШИЙ: якщо взяти перший
 * знайдений, то при a→b→c і a→c вузол `c` сяде в колонку 1 поруч із `b`, і
 * стрілка a→c піде назад — а зворотних стрілок у нас немає за домовленістю.
 *
 * Обхід — топологічний (Кан), і це не смак. Обхід у глибину з одним проходом
 * «підправити ранги» дає НЕПРАВИЛЬНИЙ результат, щойно вузли описані не в
 * порядку проходження: на ланцюгу a→b→c→d, записаному з кінця, він дає d=2
 * замість 3 (перевірено до написання коду). Топологічний порядок гарантує, що
 * ранг попередника вже остаточний, коли рахуємо наступника.
 *
 * Замкнене коло НЕ розкладаємо: ранг для нього не визначений, і будь-який
 * «розумний» вибір порядку дасть смугу, яка виглядає цілою й бреше. Кидаємо
 * помилку з самим колом у тексті, щоб було що виправляти.
 */
export function rankNodes(nodes, edges) {
  const ids = new Set(nodes.map((n) => n.id));
  const next = new Map(nodes.map((n) => [n.id, []]));
  const indeg = new Map(nodes.map((n) => [n.id, 0]));
  for (const e of edges) {
    if (!ids.has(e.from) || !ids.has(e.to)) continue;
    next.get(e.from).push(e.to);
    indeg.set(e.to, indeg.get(e.to) + 1);
  }

  const rank = new Map(nodes.map((n) => [n.id, 0]));
  const queue = nodes.filter((n) => indeg.get(n.id) === 0).map((n) => n.id);
  let seen = 0;
  while (queue.length) {
    const id = queue.shift();
    seen += 1;
    for (const to of next.get(id)) {
      // `Math.max`, а не присвоєння: за нинішньої FIFO-черги (`shift`) попередник
      // завжди готовий раніше за наступника, тож розбіжності не видно (57 тис.
      // випадкових DAG-ів — жодної). Але щойно `shift()` стане `pop()`, черга
      // піде в глибину, вузол оброблятиметься до того, як дорахували довший шлях
      // до нього, — і саме `Math.max` лишається єдиним, що тримає ранг правильним.
      // Не знімати, побачивши, що тести зелені й без нього.
      rank.set(to, Math.max(rank.get(to), rank.get(id) + 1));
      indeg.set(to, indeg.get(to) - 1);
      if (indeg.get(to) === 0) queue.push(to);
    }
  }
  // Не всі вузли вийшли з черги — лишилось коло.
  if (seen !== nodes.length) {
    throw new Error(t("flowLoop", findLoop(nodes, next, indeg)));
  }
  return rank;
}

/** Назвати саме коло, а не «десь є цикл»: інакше нема що виправляти. */
function findLoop(nodes, next, indeg) {
  const alive = new Set(nodes.filter((n) => indeg.get(n.id) > 0).map((n) => n.id));
  const seen = new Set();
  const walk = (id, path) => {
    const at = path.indexOf(id);
    if (at >= 0) return path.slice(at).concat(id);
    if (seen.has(id)) return null;
    seen.add(id);
    for (const to of next.get(id)) {
      if (!alive.has(to)) continue;
      const loop = walk(to, path.concat(id));
      if (loop) return loop;
    }
    return null;
  };
  for (const id of alive) {
    const loop = walk(id, []);
    if (loop) return loop.join(" → ");
  }
  // Запасний вихід. Недосяжний: `alive` — це вузли з ненульовим вхідним степенем після
  // Кана, тобто в них ЗАВЖДИ є цикл, який `walk` знаходить (6485 циклічних
  // графів у ревʼю — жодного влучання сюди). Лишається, щоб функція не могла
  // повернути undefined, якщо інваріант колись зміниться; це не жива гілка.
  return [...alive].join(", ");
}

/**
 * Прочитати `flow.json` проти справжнього переліку сторінок ітерації.
 *
 * Нічого не «лагодить» мовчки: усе викинуте потрапляє в `problems` дослівно, бо
 * граф, який тихо схуд на два вузли, виглядає цілим і бреше. Смуга із замкненим
 * колом падає САМА, не забираючи справні смуги — інакше одна помилка в описі
 * ховає всю решту роботи.
 *
 * ⚠️ `pages` — ПЛАСКИЙ перелік відкриваних сторінок: без дерева і без
 * організаторів (`isGroup`). Тобто те, що дає `pages_model.openable_pages`, а не
 * вміст `pages.json` як він лежить. Дерево сюди подавати НЕ можна: вкладені
 * сторінки не знайдуться і кожен вузол на них поїде в `problems` як зниклий, а
 * теки-групи навпаки стануть законними екранами. Сьогодні викликач дає саме
 * пласке — але передумова, яку ніде не написано, це майбутній баг.
 *
 * ⚠️ `ranks` у кожній смузі — це `Map`, і `JSON.stringify` робить із неї `{}`.
 * Якщо результат колись поїде через JSON (сервер → браузер, `postMessage`, кеш),
 * ранги зникнуть безшумно — колонки поїдуть, і ніхто не побачить чому.
 * Через межу JSON передавайте `[...ranks]`.
 */
export function readFlow(raw, pages) {
  const byId = new Map(pages.map((p) => [p.id, p]));
  const problems = [];
  const used = new Set();
  const flows = [];
  // `slice()`, а не `pages`: рання гілка не сміє віддавати масив викликача, поки
  // нормальний вихід віддає новий із `filter`. Дві гілки з різною власністю
  // результату — це те, на чому потім ловлять «хтось дописав у мій масив».
  const bail = (why) => {
    if (why) problems.push(why);
    return { flows, problems, orphans: pages.slice() };
  };

  // Немає файла — не помилка: флоу ще не описували.
  if (raw === undefined || raw === null) return bail();
  // А от файл, який Є, але з незрозумілим коренем, мовчати не має права. Інакше
  // описка в назві ключа (`flowz`) виглядає рівно як «флоу ще не описували», і
  // автор шукає причину в канвасі, а не в одній літері.
  if (typeof raw !== "object" || Array.isArray(raw)) {
    return bail(t("flowRootNotObject"));
  }
  if (!("flows" in raw)) {
    return bail(t("flowRootNoFlows"));
  }
  if (!Array.isArray(raw.flows)) return bail(t("flowFlowsNotList"));

  for (const [i, flow] of raw.flows.entries()) {
    const at = flow?.id ? t("flowAt", flow.id) : t("flowAtIndex", i + 1);
    // Побитий формат — це теж «що не так», а не привід померти цілком: кинутий
    // TypeError забрав би з собою і цілі смуги, і сам перелік проблем.
    if (typeof flow !== "object" || flow === null || Array.isArray(flow)) {
      problems.push(t("flowNotObject", at));
      continue;
    }
    const rawNodes = flow.nodes ?? [];
    if (!Array.isArray(rawNodes)) {
      problems.push(t("flowNodesNotList", at));
      continue;
    }
    const rawEdges = flow.edges ?? [];
    if (!Array.isArray(rawEdges)) {
      problems.push(t("flowEdgesNotList", at));
      continue;
    }

    const nodes = [];
    const seen = new Map();          // ключ кадру → id першого вузла
    const ids = new Set();           // id уже взятих вузлів цієї смуги
    const mine = new Set();          // сторінки ЦІЄЇ смуги, поки не зараховані
    for (const [j, node] of rawNodes.entries()) {
      const who = node?.id ? t("flowNode", node.id) : t("flowNodeIndex", j + 1, at);
      if (typeof node !== "object" || node === null || Array.isArray(node)) {
        problems.push(t("flowNodeNotObject", who));
        continue;
      }
      /* id мусить БУТИ, і ця перевірка стоїть ПЕРЕД дублями. Інакше вузол
         `{"page": "a"}` проходив як законний екран з `id: undefined` і без жодної
         скарги, а ДРУГИЙ такий діставав «id вже зайнятий у цій смузі» — скаргу на
         поле, якого автор ніколи не писав. Забути рядок `"id"` — найімовірніша
         описка в цьому файлі, і повідомлення мусить назвати саме її.
         Порожній рядок — те саме: за таким id не знайти вузол і не описати ребро. */
      if (typeof node.id !== "string" || node.id === "") {
        problems.push(t("flowNoId", who));
        continue;
      }
      // Далі id на дублі: щойно він повторився, кожне наступне повідомлення про цей
      // вузол вказує в двоє місць, а ребра з ним стають неоднозначні мовчки.
      if (ids.has(node.id)) {
        problems.push(t("flowDupId", who));
        continue;
      }
      const page = byId.get(node.page);
      if (!page) {
        problems.push(t("flowNoPage", who, node.page));
        continue;
      }
      // Дешева охорона контракту (див. вище): теку-організатор відкрити не можна,
      // знімка в неї немає. Перевірка тут коштує один `if`, а покладатись на те,
      // що кожен майбутній викликач сам відфільтрує групи, — не можна: у
      // `app/app.js` групи відсіює ОКРЕМИЙ рядок після `flattenPages`, і забути
      // його — питання часу.
      // kindOf, а не «isGroup || kind»: явний kind сильніший за легасі-isGroup
      // (kind:"page" + зайвий isGroup — сторінка), як у `pages_model.kind_of`
      if (kindOf(page) === "folder") {
        problems.push(t("flowIsGroup", who, node.page));
        continue;
      }
      try {
        checkState(node.state);
      } catch (e) {
        problems.push(`${who}: ${e.message}`);
        continue;
      }
      const key = shotKey(node.page, node.state);
      if (seen.has(key)) {
        problems.push(t("flowDupScreen", seen.get(key), node.id, node.page));
        continue;
      }
      seen.set(key, node.id);
      ids.add(node.id);
      mine.add(node.page);
      nodes.push({ ...node, key, label: node.label || page.name });
    }

    const edges = [];
    for (const [j, e] of rawEdges.entries()) {
      if (typeof e !== "object" || e === null || Array.isArray(e)) {
        problems.push(t("flowEdgeNotObject", j + 1, at));
        continue;
      }
      if (!ids.has(e.from) || !ids.has(e.to)) {
        problems.push(t("flowEdgeNoNode", e.from, e.to));
        continue;
      }
      // Самопосилання відсіюємо ТУТ, до рангів: для `rankNodes` це чесне коло, і
      // смуга померла б із текстом «замкнене коло: a → a», який нічого не
      // пояснює й забирає з собою решту стрілок. Одне зайве ребро — одна
      // проблема, а не втрачена смуга.
      if (e.from === e.to) {
        problems.push(t("flowEdgeSelf", e.from, e.to));
        continue;
      }
      edges.push(e);
    }

    let ranks;
    try {
      ranks = rankNodes(nodes, edges);
    } catch (e) {
      problems.push(`${at}: ${e.message}`);
      continue;                       // падає лише ця смуга
    }
    // Сторінки зараховуємо ЩОЙНО ТУТ, а не там, де перебирали вузли. Інакше
    // сторінки викинутої смуги лічились би використаними — і не потрапили б ні
    // в граф, ні в «не у флоу». Дві сторінки з макета зникли б з екрана зовсім,
    // а `problems` казав би лише про коло. Це рівно та тиха неправда, проти якої
    // написана вся ця функція; знайдено ревʼю Task 3.
    for (const page of mine) used.add(page);
    flows.push({ ...flow, nodes, edges, ranks });
  }

  return { flows, problems, orphans: pages.filter((p) => !used.has(p.id)) };
}
