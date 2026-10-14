/**
 * Модель UI просторів — чисті функції: ні DOM, ні `t()`, ні мережі, за патерном
 * `bar-model.js`/`tasks-model.js`. Усе, що тут буває ПІДПИСОМ, — це ІМʼЯ ключа
 * словника (`titleRequired`, `spaceErrTooBroad`…) рядком, а `t()` кличе вже
 * шар розмітки: тоді тест не залежить від мови, а ключ, якого нема в словнику,
 * ловить `tests/i18n-keys.test.mjs`, а не перший клік у живому застосунку.
 *
 * Що тут живе і чому саме тут:
 *   · id задачі з назви й правило його валідності — форма «Нова задача» мусить
 *     сказати «такий id уже є» ДО запиту, а не після 400 `task-exists` від
 *     сервера, і підставити вільний id сама;
 *   · слаг назви простору й тека за замовчуванням — діалог «Новий простір»
 *     підказує теку, поки людина друкує назву;
 *   · рядки перемикача просторів (`spaceRows`) — з відповіді `/api/spaces`;
 *   · коди помилок `/api/space-new|update` → ключі словника (`spaceErrKey`).
 *
 * ⚠️ Правило id СУВОРІШЕ за серверне, і це свідомо. Сервер перевіряє
 * `serve.NAME_RE = ^[\w-]+$` через `fullmatch` у Python, де `\w` — Unicode
 * (кирилиця проходить). Тут той самий вираз у JS БЕЗ прапорця `u`, де `\w` —
 * лише ASCII `[A-Za-z0-9_]`. Тобто все, що ця форма пропустила, сервер
 * прийме, а зворотне — ні: id кирилицею форма відхилить (`idBad`), хоча сервер
 * його б узяв. Ціна — трохи суворіша форма; вигода — id задачі стає ім'ям теки
 * на диску, у git і в URL превʼю, де не-ASCII — вічне джерело поломок. І ще
 * одне розходження в той самий бік: JS-`$` без прапорця `m` НЕ пропускає
 * хвостовий `\n` (Python-ський `$` пропускав — тому сервер і перейшов на
 * `fullmatch`).
 */

/** Правило id задачі. ASCII-слова й дефіс; див. шапку — чому суворіше за Python. */
export const NAME_RE = /^[\w-]+$/;

/** Найдовший id, який пропонує `taskIdFrom` (id — ім'я теки: довгі ламають шляхи й URL). */
export const ID_MAX = 60;

/** Кольори простору — ті самі `space-1…6`, що знає сервер (`spaces.COLORS`) і CSS-токени. */
export const SPACE_COLORS = ["space-1", "space-2", "space-3", "space-4", "space-5", "space-6"];

/**
 * Колір у ТОКЕН для `var(--…)`. Реєстр правлять руками, а токен іде в
 * `style="background:var(--…)"`: довільний рядок звідти — ін'єкція CSS у
 * атрибут (`esc` захищає лише від виходу з лапок). Невідоме → перший колір.
 */
export function spaceColorToken(color) {
  return typeof color === "string" && SPACE_COLORS.includes(color) ? color : SPACE_COLORS[0];
}

/**
 * ASCII-слаг: без діакритики (`Café` → `cafe`), нижній регістр, усе, що не
 * `[a-z0-9]`, — один дефіс, краї без дефісів. Кирилиця не транслітерується —
 * вона випадає, і слаг може вийти порожнім (тоді викликач бере запасний).
 */
function slug(text) {
  return String(text ?? "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

/** Множина зайнятих id без регістру: на macOS і Windows `Foo` і `foo` — одна тека. */
const lowerSet = (ids) => new Set(Array.from(ids ?? [], (x) => String(x).toLowerCase()));

/**
 * Вільний id задачі з її назви. Слаг назви; зайнятий — `-2`, `-3`…; слаг
 * порожній (назва кирилицею) — `task-N` з першим ВІЛЬНИМ N (не з кількості
 * зайнятих: при `task-1` і `task-3` кількість дала б колізію з `task-3`).
 * Довжина ≤ `ID_MAX` і з суфіксом: слаг обрізається ПІД суфікс, і краї знову
 * без дефіса. Результат завжди проходить `validTaskId`.
 */
export function taskIdFrom(title, taken = []) {
  const used = lowerSet(taken);
  const base = slug(title).slice(0, ID_MAX).replace(/-+$/, "");
  if (base) {
    if (!used.has(base)) return base;
    for (let n = 2; ; n += 1) {
      const suffix = `-${n}`;
      const cand = base.slice(0, ID_MAX - suffix.length).replace(/-+$/, "") + suffix;
      if (!used.has(cand)) return cand;
    }
  }
  for (let n = 1; ; n += 1) {
    if (!used.has(`task-${n}`)) return `task-${n}`;
  }
}

/** Чи годиться `id` як ідентифікатор задачі (див. шапку: ASCII, суворіше за сервер). */
export const validTaskId = (id) => typeof id === "string" && NAME_RE.test(id);

/**
 * Помилка форми «Нова задача» — КЛЮЧ словника або `null`. Порядок несучий:
 * спершу назва (без неї id нічого не значить, і форма не має кричати про id,
 * який людина ще не встигла побачити), потім форма id, потім зайнятість.
 * Зайнятість без регістру — див. `lowerSet`.
 */
export function taskFormError({ title, id } = {}, taken = []) {
  if (!String(title ?? "").trim()) return "titleRequired";
  if (!validTaskId(id)) return "idBad";
  if (lowerSet(taken).has(id.toLowerCase())) return "idTaken";
  return null;
}

/** Слаг назви простору для теки; назва без латиниці дає порожній рядок. */
export const spaceSlug = (name) => slug(name);

/* Шлях для порівняння теки з реєстром: без хвостових слеш і в NFC — так само, як сервер
   (`check_new_path` рівняє `_nfc(a) == _nfc(b)`). Регістр НЕ чіпаємо: рядкове порівняння
   сервера його теж не чіпає, а підказка не має відмовляти там, де сервер дозволить. */
const folderKey = (p) => String(p ?? "").normalize("NFC").replace(/[\\/]+$/, "");

/**
 * Чи ця тека вже ЗАРЕЄСТРОВАНА як простір. `taken` — шляхи просторів з `/api/spaces`
 * (абсолютні), `path` — те, що віддав `/api/space-peek` (вона розкриває «~» сама, тож
 * збігається з реєстром дослівно, з точністю до хвостового слеша). Порожній шлях — ні.
 */
export function isRegisteredPath(path, taken = []) {
  const p = folderKey(path);
  return !!p && Array.from(taken ?? [], folderKey).includes(p);
}

/**
 * Тека простору за замовчуванням: `<дім>/deai-work/<слаг>`, і ВІЛЬНА — не та, що вже
 * в реєстрі (`taken`, шляхи просторів): друга теж «Особисте» лягла б на теку першого, і
 * діалог відкривався б із відмовою «тека вже додана». Перебір: слаг, `слаг-2`, `слаг-3`…;
 * порожній слаг (назва кирилицею — «Особисте») → `personal`, далі `space-2`, `space-3`…
 * (кирилицю в шляхах не множимо з тієї ж причини, що й в id задач; `personal-2` для
 * клієнтського простору читався б як брехня).
 * `home` — як його знає викликач; `~` сервер розкриє сам. Реєстр же віддає шляхи вже
 * розкритими, тож при `home === "~"` порівнюємо за хвостом (`/deai-work/<імʼя>`, без
 * регістру): краще пропустити вільну теку, ніж запропонувати зайняту.
 */
export function defaultSpacePath(name, home, taken = []) {
  const h = String(home || "~").replace(/[\\/]+$/, "");
  const used = Array.from(taken ?? [], (x) => folderKey(x).toLowerCase());
  const tilde = h === "~";
  const isFree = (leaf) => {
    const rel = `/deai-work/${leaf}`.toLowerCase();
    return !used.some((u) => u === `${h}${rel}`.toLowerCase() || (tilde && u.endsWith(rel)));
  };
  const slugged = spaceSlug(name);
  const first = slugged || "personal";
  const leaf = isFree(first) ? first : (() => {
    const stem = slugged || "space";
    for (let n = 2; ; n += 1) if (isFree(`${stem}-${n}`)) return `${stem}-${n}`;
  })();
  return `${h}/deai-work/${leaf}`;
}

/**
 * Рядки перемикача просторів з відповіді `/api/spaces`. `on` — поточний
 * (галочка), `muted` — файл задач недоступний (`available === false`; поле
 * відсутнє = доступний), `sub` — дані для підпису «N задач · шлях» (число й
 * шлях, не текст: мову вибирає глядач). Порядок реєстру зберігається.
 * `{off: true}`/`null`/нема масиву — порожньо: шар просторів вимкнено.
 */
export function spaceRows(info) {
  const { current, spaces } = info ?? {};
  return (Array.isArray(spaces) ? spaces : []).map((x) => ({
    id: x.id, name: x.name, color: x.color,
    on: x.id === current,
    muted: x.available === false,
    sub: { n: x.tasks ?? 0, path: x.path ?? "" },
  }));
}

/* Коди відмов `/api/space-new|update` (`code` у JSON) → ключі словника. `Map`, а не
   об'єкт: `spaceErrKey("constructor")` не має знайти функцію з прототипа. */
const ERR_KEYS = new Map([
  ["path-not-absolute", "spaceErrNotAbsolute"],
  ["path-too-broad", "spaceErrTooBroad"],
  ["path-system", "spaceErrSystem"],
  ["path-tool", "spaceErrTool"],
  ["path-registered", "spaceErrRegistered"],
  ["path-overlap", "spaceErrOverlap"],
  ["path-not-dir", "spaceErrNotDir"],
  ["path-unwritable", "spaceErrUnwritable"],
  ["task-id-collision", "spaceErrCollision"],
  ["name-required", "spaceErrName"],
  /* Не код сервера, а наш: запит діалогу обірвано за `FORM_POST_TIMEOUT_MS` (`postForm`, `app.js`). */
  ["timeout", "formTimeout"],
]);

/**
 * Скільки діалог (`space-new`/`space-update`/`task-new`) чекає відповіді сервера, мс. Форма на
 * цей час «зайнята»: Esc і «Скасувати» не діють, а підкладка накриває весь канвас, — тож
 * завислий запит без стелі лишив би людину під нею назавжди. Минув строк — запит
 * обривається, форма показує `formTimeout` і знову закривається.
 */
export const FORM_POST_TIMEOUT_MS = 20000;

/** Ключ словника для коду помилки сервера; невідомий (і `spaces-*`) — загальний. */
export const spaceErrKey = (code) => ERR_KEYS.get(code) ?? "spaceErrGeneric";

/**
 * Яке поле діалогу простору зачепила відмова: `name`, `path` або `null` (загальна: реєстр
 * не пишеться, мережа). Поле дістає фокус і `aria-invalid`; помилка, що не про поле, не
 * сміє позначати чужу (`spaces-unwritable` — не вина шляху, який людина набрала).
 */
export const spaceErrField = (code) => {
  const c = String(code ?? "");
  if (c === "name-required") return "name";
  return c.startsWith("path-") || c === "task-id-collision" ? "path" : null;
};

/* ── що додав Task 7: рішення, які приймає `app.js` і які мусять бути видні тесту ─────
   Усе нижче — ЧИСТІ функції. Проводка (DOM, мережа, стан модуля) лишається в `app.js`
   й `space-dialogs.js`; сюди винесено лише ті ПРАВИЛА, помилка в яких мовчки спотворює
   стан, а не кидає: який канал коментарів діє, чи змінився простір, куди вести після
   «задачі нема», який колір пропонувати новому простору. */

/**
 * Канал коментарів, який справді ДІЄ. Простір без інтеграцій не має командного каналу:
 * `project` там сервер мовчки віддає як локальний режим БЕЗ рядка вкладок аудиторій
 * (`GET /commented`), а `/api/comment-config?ch=project` — 409. Тому вибраний
 * дизайнером `project` затискається в `local` при ВИКОРИСТАННІ, а збережене значення
 * (`localStorage`) не чіпається: у ЛІГА його вибір має пережити відвідини особистого
 * простору. Рівно `integrations === false`, як скрізь: невідомий простір (`null`, шар
 * вимкнено) каналу не відбирає.
 */
export const effectiveCommentMode = (space, mode) =>
  (space?.integrations === false && mode === "project" ? "local" : mode);

/**
 * Чи змінився простір між «що ми знали» і «що відповів сервер» (`task-switch`,
 * `task-new`). `null`/`undefined`/відсутнє — одне й те саме («шар вимкнено»): інакше
 * кожне перемикання задачі з вимкненим шаром скидало б увесь стан простору.
 */
export const spaceChanged = (prevId, nextId) => (prevId ?? null) !== (nextId ?? null);

/** Простір з відповіді `/api/spaces`, що є поточним, або `null` (немає / `current` висить / шар вимкнено). */
export function currentSpace(info) {
  const { current, spaces } = info ?? {};
  return (Array.isArray(spaces) ? spaces : []).find((x) => x.id === current) ?? null;
}

/**
 * Куди перемкнути, коли `current` реєстру вказує на простір, якого нема (його вилучили
 * руками чи агентом). Сервер у запиті бачить таке як «простору нема» — `/api/task` дає
 * 404 `no-task`, а екран «Задачі» порожній, і без фішки перемкнутись нема чим. Беремо
 * ПЕРШИЙ ДОСТУПНИЙ (інакше перший), як і сам `active_space()` поза запитом. `null` —
 * лікувати нічого: шар вимкнено, просторів нема, `current` на місці.
 */
export function healTarget(info) {
  const { spaces, current, off } = info ?? {};
  if (off || !Array.isArray(spaces) || !spaces.length) return null;
  if (spaces.some((x) => x.id === current)) return null;
  return (spaces.find((x) => x.available !== false) ?? spaces[0]).id;
}

/**
 * Чи показувати привітання: шар увімкнено і просторів ще нема. Невідомість (`null`) — ні.
 * `legacy_error` (старий `tasks.json` є, але не читається, і простору з нього нема) — теж ні:
 * порожній список тут не «чиста машина», а зіпсований файл із задачами людини, і замість
 * привітання (з пропозицією завести простір поруч) має зʼявитись смуга помилки.
 */
export const needsWelcome = (info) =>
  !!info && !info.off && !info.legacy_error && Array.isArray(info.spaces) && info.spaces.length === 0;

/* Відмови читання `/api/task|tasks` (`code`) → причина в смузі. `Map`, не обʼєкт (як `ERR_KEYS`). */
const READ_ERR_KEYS = new Map([
  ["space-unavailable", "tasksErrSpaceUnavailable"],
  ["spaces-unreadable", "tasksErrSpaces"],
]);

/** Ключ словника для причини, чому не прочиталась задача простору; невідомий код — `null` (типова причина смуги). */
export const readErrKey = (code) => READ_ERR_KEYS.get(code) ?? null;

/**
 * Чи ключ причини в смузі — саме про ЧИТАННЯ простору (файл задач / реєстр). Успішне
 * читання (`loadHome`) знімає лише такі: причина, виставлена чимось іншим (чужий процес на
 * порту, `tasksErrPort`), не про простір і від успіху огляду не минає.
 */
export const isReadErrKey = (key) => [...READ_ERR_KEYS.values()].includes(key);

/**
 * Чи перечитувати екран «Задачі», коли людина повернулась до вікна (`focus`,
 * `visibilitychange`): простір міг зʼявитись чи змінитись поза вкладкою (агент завів
 * його тим самим API), а привітання / список без цього лишались би застарілими до першого
 * кліку. `focus` і `visibilitychange` приходять парою за одне повернення, тож другий
 * виклик у межах `gap` мс ігнорується — один запит, а не два.
 *
 * `forced` — поки летить примусове перечитування («Спробувати ще», `loadHome(true)`), звичайне
 * його б ПЕРЕБИЛО: нове `loadHome` обнуляє відповідь попереднього (`homeSeq`), і людина, що
 * саме натиснула повтор, отримала б огляд без примусу, а не той, якого просила.
 */
export function shouldRefreshHome({ open, visible, last = 0, now = 0, gap = 800, forced = false } = {}) {
  return !!open && !!visible && !forced && !(now - last < gap);
}

/* Відмови `POST /api/task-new` (`code`) → ключі словника. Лише ті, що людина може
   виправити в самій формі або мусить прочитати окремо; решта — загальна. */
const TASK_ERR_KEYS = new Map([
  ["task-exists", "idTaken"],
  ["bad-task-id", "idBad"],
  ["no-space", "taskErrSpaceGone"],
  ["unknown-space", "taskErrSpaceGone"],
  ["space-unavailable", "tasksErrSpaceUnavailable"],
  ["timeout", "formTimeout"],
]);

/** Ключ словника для відмови створення задачі; невідомий код (і мережа) — загальний. */
export const taskErrKey = (code) => TASK_ERR_KEYS.get(code) ?? "taskErrGeneric";

/** Поле форми «Нова задача», про яке ключ помилки (`taskFormError`/`taskErrKey`): `title`, `id` або `null`. */
export const taskErrField = (key) => (key === "titleRequired" ? "title" : (key === "idBad" || key === "idTaken" ? "id" : null));

/**
 * Колір для нового простору: перший з шести, якого ще не використано, — щоб фішки в смузі
 * різнились з першого дня. Коли зайнято всі — по колу від кількості. Невідомі кольори
 * в реєстрі (рукописний файл) за зайняті не рахуються.
 */
export function freeColor(spaces) {
  const list = Array.isArray(spaces) ? spaces : [];
  const used = new Set(list.map((x) => x?.color));
  return SPACE_COLORS.find((c) => !used.has(c)) ?? SPACE_COLORS[list.length % SPACE_COLORS.length];
}

/**
 * Куди йде фокус у списку при стрілці (roving focus дропдауна просторів): `index` —
 * де він зараз (`-1` — поза списком), `count` — скільки рядків. ↓ — наступний, ↑ —
 * попередній (з краю не обертається: меню, не колесо), Home/End — крайні. З `-1` ↓
 * входить на перший, ↑ — на останній. Інша клавіша або порожній список — `null`
 * («не моє»), щоб викликач не гасив `preventDefault` чужим клавішам.
 */
export function rovingIndex(index, count, key) {
  if (!(count > 0)) return null;
  const at = Number.isInteger(index) ? index : -1;
  switch (key) {
    case "ArrowDown": return at < 0 ? 0 : Math.min(at + 1, count - 1);
    case "ArrowUp": return at < 0 ? count - 1 : Math.max(at - 1, 0);
    case "Home": return 0;
    case "End": return count - 1;
    default: return null;
  }
}

/**
 * Наступний колір для стрілок у групі кружків (`role="radiogroup"`). На відміну від
 * дропдауна, група кружків — КОЛО: →/↓ далі, ←/↑ назад, з краю на інший край (так
 * поводиться native radio). Невідомий колір вважається першим; інша клавіша — `null`.
 */
export function colorStep(color, key) {
  const dir = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[key];
  if (!dir) return null;
  const at = Math.max(0, SPACE_COLORS.indexOf(color));
  return SPACE_COLORS[(at + dir + SPACE_COLORS.length) % SPACE_COLORS.length];
}

/**
 * Відповідь `/api/space-peek` у те, що підставляє діалог: тека вже ПРОСТІР (є `space.json`
 * з назвою) → `{name, color, tasks}`, інакше `null` («звичайна тека, поле лишається як є»).
 * Колір — токен (`spaceColorToken`): файл правлять руками, а значення піде в `style`.
 * Помилка peek (`error`) — теж `null`: підказка про шлях — справа валідації сервера при
 * «Створити», не мерехтіння під час набору.
 *
 * `taken` — шляхи просторів, що вже в реєстрі. Тека, яка там є, — НЕ «знайдений простір»:
 * це той самий простір, що вже підключений, а не новий, який можна підхопити. Інакше
 * діалог блокував би назву й колір і обіцяв «його задачі підхопляться» для теки, яку сервер
 * однаково відхилить (`path-registered`). Діалог показує для такої теки окрему підказку
 * (`peekRegistered`) і лишає форму редагованою.
 */
export function peekFound(res, taken = []) {
  if (!res || res.error || typeof res.name !== "string" || !res.name.trim()) return null;
  if (peekRegistered(res, taken)) return null;
  return { name: res.name, color: spaceColorToken(res.color), tasks: Number.isFinite(res.tasks) ? res.tasks : 0 };
}

/**
 * Чи тека з відповіді `/api/space-peek` уже ЗАРЕЄСТРОВАНА як простір. Слово сервера — перше:
 * `registered: true` він ставить, порівнявши теки самою ФС (`samefile`), тож упізнає й
 * варіант регістру на macOS (`…/CASEa` проти `…/caseA`), якого клієнтське порівняння рядків
 * не бачить. Ключа нема (не зареєстрована, реєстр не прочитати, шар вимкнено) — то
 * запасне порівняння за переліком `taken` (`isRegisteredPath`). Помилка peek — ні.
 */
export function peekRegistered(res, taken = []) {
  if (!res || res.error) return false;
  return res.registered === true || isRegisteredPath(res.path, taken);
}
