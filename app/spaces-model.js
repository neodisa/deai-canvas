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

/**
 * Стеля запиту, що ВИКОНУЄ `check` модуля (`module-check`, а також `module-enable|settings`: вони перевіряють після запису), мс.
 * Ядро дає `check` модуля `check_timeout_s` секунд (маніфест; типово 5 — `deai_modules.CHECK_TIMEOUT`), а `vercel-publish` у
 * режимі `cli` просить 130 (холодний `npx --yes vercel whoami`). Клієнт із 20 с (`FORM_POST_TIMEOUT_MS`) обірвав би запит
 * раніше за вердикт і показав «сервер не відповів», хоч сервер ще перевіряє. Стеля = `check_timeout_s` + запас
 * `CHECK_POST_MARGIN_S` (читання налаштувань, запис, відповідь); модуль без `check_timeout_s` у записі `GET /api/modules` —
 * як було, `FORM_POST_TIMEOUT_MS`. Інші запити діалогів стелі не міняють.
 */
export const CHECK_POST_MARGIN_S = 15;
export function checkPostTimeoutMs(entry) {
  const s = entry?.check_timeout_s;
  return Number.isInteger(s) && s > 0 ? Math.max(FORM_POST_TIMEOUT_MS, (s + CHECK_POST_MARGIN_S) * 1000) : FORM_POST_TIMEOUT_MS;
}

/**
 * Стеля запиту створення задачі, що справді клонує (`taskCreateClones`), мс; решта запитів — `FORM_POST_TIMEOUT_MS`.
 * Найгірший шлях сервера (`/api/task-new` із `vcs`): `validate` модуля
 * ≤ 5 с (`deai_modules.CHECK_TIMEOUT`) + клон ≤ 180 с (`git-sync/server.py: CLONE_TIMEOUT`) + для порожнього репо ще один клон
 * без `--branch` ≤ 180 с ≈ 365 с — 400 с лишає запас. Клієнт, що обірвав би раніше за відповідь, показав би «помилку» при
 * вже створеній задачі.
 */
export const TASK_VCS_POST_TIMEOUT_MS = 400000;

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
 * Чи є в просторі командний канал коментарів — вкладка «Команда», аудиторія `project`, режим `project`.
 * Його дає РОЛЬ `comments` (етап 2b-2): зашитий Supabase ЛІГА (`'legacy'`, простір з інтеграціями) або модуль
 * (`capabilities.comments` = id модуля — навіть у просторі без інтеграцій); явний `null` — нікого, лише локальні.
 *
 * Відсутність САМОГО ключа `comments` у `capabilities` — це «не знаємо», а не «нікого»: `capabilities` із форми 2а
 * (`{publish, tokens}`) віддає сервер, що ще не вміє роль `comments` (оновили `app.js`, а процес Python із попереднім
 * `serve.py` не перезапустили). Тоді, як і для відповідей без `capabilities`, рішення за `integrations`, рівно `=== false`:
 * простір без відомостей командного каналу в людини не краде (інакше ЛІГА мовчки втратила б «Команду»).
 *
 * ⚠️ Це НЕ `noNotify` (`app.js`): Teams-тиша тепер на ролі `notify` (`hasNotify`), дашборд команди — на ролі `dashboard`.
 * Простір із модулем коментарів без інтеграцій має команду коментарів, але Teams має лише за модулем `notify`.
 */
export const hasTeamComments = (space) => {
  const caps = space?.capabilities;
  return caps && typeof caps === "object" && "comments" in caps
    ? caps.comments != null
    : space?.integrations !== false;
};

/**
 * Канал коментарів, який справді ДІЄ. Простір без командного каналу (`hasTeamComments`) не має його:
 * `project` там сервер мовчки віддає як локальний режим БЕЗ рядка вкладок аудиторій
 * (`GET /commented`), а `/api/comment-config?ch=project` — 409. Тому вибраний
 * дизайнером `project` затискається в `local` при ВИКОРИСТАННІ, а збережене значення
 * (`localStorage`) не чіпається: у ЛІГА його вибір має пережити відвідини особистого
 * простору. Невідомий простір (`null`, шар вимкнено, стара форма без відомостей) каналу не відбирає.
 */
export const effectiveCommentMode = (space, mode) =>
  (!hasTeamComments(space) && mode === "project" ? "local" : mode);

/**
 * Чи є в просторі синхронізація з git (роль `vcs`, етап 4a). Є ключ `capabilities.vcs` — він і вирішує (`'legacy'` —
 * зашитий шлях ЛІГА, id модуля — модуль, `null` — нема). Ключа нема (стара форма відповіді, шар вимкнено, фікстури
 * `legacy-golden`) — за `integrations`, як було до 4a: простір без відомостей не краде в людини синк.
 * `hasVcs(null)` — `true`, як `hasTeamComments(null)`: невідомий простір (шар вимкнено) синк не відбирає.
 *
 * ⚠️ Це НЕ `noNotify` (`app.js`): Teams-тиша — на ролі `notify`, а синк із git дає роль `vcs` — простір із
 * модулем `git-sync` має синк і без інтеграцій.
 */
export const hasVcs = (space) => {
  const caps = space?.capabilities;
  return caps && typeof caps === "object" && "vcs" in caps ? caps.vcs != null : space?.integrations !== false;
};

/**
 * Чи є в просторі сповіщення Teams (роль `notify`, етап 4c-3): пункт «Сповіщати Teams» у дропдауні публікації й опит
 * `/api/teams-mute`. Є ключ `capabilities.notify` — він і вирішує (`'legacy'` — зашитий шлях ЛІГА, id модуля — модуль,
 * `null` — нема). Ключа нема (стара форма відповіді, сервер без ролі, шар вимкнено, фікстури `legacy-golden`) — за
 * `integrations`, рівно `=== false`, як було до 4c-3: невідомість Teams у людини не краде (інакше ЛІГА мовчки втратила б
 * перемикач тиші). `hasNotify(null)` — `true`, як `hasVcs(null)`.
 *
 * ⚠️ Це вже НЕ «Teams лишається на `integrations`»: простір без інтеграцій, але з модулем `notify`, має і пункт, і опит;
 * простір з інтеграціями, де роль вимкнено (`notify: null`), їх не має — інакше пункт висів би вічним «перевіряю стан у
 * базі…», бо `/api/teams-mute` там відповідає 409 `notify-off`.
 */
export const hasNotify = (space) => {
  const caps = space?.capabilities;
  return caps && typeof caps === "object" && "notify" in caps ? caps.notify != null : space?.integrations !== false;
};

/** Синк простору — зашитий шлях ЛІГА (налаштовується в `tasks.json`, не на «Підключенні»). Правило ключа те саме, що в `hasVcs`. */
export const isLegacyVcs = (space) => {
  const caps = space?.capabilities;
  return caps && typeof caps === "object" && "vcs" in caps ? caps.vcs === "legacy" : space?.integrations !== false;
};

/**
 * Чи справді запит `POST /api/task-new` клонує репозиторій — лише такому потрібна довга стеля (`TASK_VCS_POST_TIMEOUT_MS`) і
 * рядок «Перший клон може тривати кілька хвилин». Сервер (`_task_new_write`: `if gitlab or (vcs and adopt_src is None)`) клонує, коли:
 *  - у тілі є `vcs` (форма шле його лише з непорожнім полем «Репозиторій» і ніколи не шле `from`);
 *  - або `gitlab` задає профіль: простір з `integrations` (`integrations_for`) завжди ставить `profile` «united» → профільний
 *    `gitlab`, і коли роль `vcs` є (`vcs_provider()` не `None`), сервер тягне макет за ним — чи роль веде зашитий шлях ЛІГА, чи
 *    явно ввімкнений `git-sync` (ЛІГА з модулем, поле «Репозиторій» порожнє). Без ролі (`capabilities.vcs == null`: у просторі з
 *    інтеграціями це лише роль «на папері» за своїм модулем, що не працює) `vcs_provider()` відмовляє одразу (`VcsError`, 409) — клону нема.
 * Звичайний простір (`integrations: false`) профілю не має: без `vcs` у тілі клону нема.
 *
 * Невідомий простір (`null`, стара форма відповіді без `integrations`/`capabilities`) — «клонує»: правило ключа те саме, що в
 * `hasVcs`/`isLegacyVcs` (синк не відбираємо), а довга стеля безпечніша за обрив посеред клону при вже створеній задачі.
 */
export const taskCreateClones = (space, body) =>
  (body != null && "vcs" in body) || (hasVcs(space) && space?.integrations !== false);

/**
 * Підпис репозиторію для інтерфейсу — ЄДИНИЙ нормалізатор: смуга, палітра й усі дії синку беруть підпис звідси. Білий
 * список `GitLab`/`GitHub`/`Git` (те, що віддає статус: `label`); усе інше — порожнє (опит упав, простір без цілі, статус
 * без `label`), довге, з переносом рядка, чужий текст свого модуля, службові імена обʼєкта — не показується, а замінюється:
 * у ЛІГІ (`isLegacyVcs`, невідомий простір теж) — «GitLab», як було, у звичайному просторі — нейтральним «Git»: сервер
 * підпису в стані помилки не знає, а вигадувати «GitLab» для GitHub-репо — брехня.
 * `Set`, а не обʼєкт: `{}['constructor']` дав би функцію замість «нема».
 */
const VCS_LABELS = new Set(["GitLab", "GitHub", "Git"]);
export const vcsLabel = (label, space) => (VCS_LABELS.has(label) ? label : (isLegacyVcs(space) ? "GitLab" : "Git"));

/** Підпис, коли він НЕ типовий («GitLab»): `'GitHub'`/`'Git'`, інакше `''` — тоді поля `brand` у смузі й `labelArgs` у палітрі нема. */
export const vcsBrand = (label, space) => { const l = vcsLabel(label, space); return l === "GitLab" ? "" : l; };

/** Посилання «Історія» — лише `http(s)`: `web` віддає свій модуль, а `javascript:`/`file:` у `window.open` — не історія. Інакше `null`. */
export const vcsWebUrl = (web) => (typeof web === "string" && /^https?:\/\//i.test(web) ? web : null);

/** Через скільки мс і скільки разів перепитати статус, коли він натрапив на `vcs-busy` (лок дзеркала): ≈5 с, кілька спроб. */
export const VCS_BUSY_RETRY_MS = 5000;
export const VCS_BUSY_MAX_TRIES = 4;

/**
 * Людський текст відмови ЗАПИТУ (`api()` кидає `Error` із `statusText`/`body`): HTML від `send_error` (нема ролі чи цілі,
 * `bad iteration`) несе причину в рядку статусу, а `message` — перші 200 знаків розмітки; JSON-помилка й мережа — своє `message`.
 */
export const requestErrText = (e) => (/^\s*</.test(String(e?.body ?? "")) && e?.statusText ? e.statusText : String(e?.message ?? ""));

/* Коди відмов дій «Відправити»/«Отримати» → ключі словника. Решта кодів (`vcs-error`, `module-error`…) тексту не мають: їхня
   причина вже в `error` відповіді, і вона йде в `glSyncFailedMsg`. */
const VCS_ERR_KEYS = new Map([
  ["vcs-offline", "vcsErrOffline"], ["vcs-auth", "vcsErrAuth"], ["vcs-busy", "vcsErrBusy"], ["vcs-bad-target", "vcsErrTarget"],
]);
/** Ключ словника для коду відмови синку або `null`, коли свого тексту код не має. */
export const vcsErrKey = (code) => VCS_ERR_KEYS.get(code) ?? null;

/**
 * Те саме для дій у конкретному просторі: у ЛІГІ ціль синку живе в `tasks.json`, а не на «Підключенні», тож `vcs-bad-target`
 * радити «виправ на Підключенні» там не можна — текст береться загальний (`glSyncFailedMsg`) із причиною сервера.
 */
export const vcsFailKey = (code, space) => { const k = vcsErrKey(code); return k === "vcsErrTarget" && isLegacyVcs(space) ? null : k; };

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
  /* Задача з наявної теки (`from`, майстер 3b): ключ — за КОДОМ відмови, ніколи за текстом повідомлення. */
  ["from-not-found", "wzErrFromNotFound"],
  ["from-no-index", "wzErrFromNoIndex"],
  ["from-contains-space", "wzErrFromContains"],
  ["from-too-big", "wzErrFromTooBig"],
  ["from-needs-plain-space", "wzErrFromPlain"],
  ["task-dir-exists", "wzErrTaskDirExists"],
  /* Ціль синку нової задачі (`vcs`, 4a). Адресу людина виправляє в полі «Репозиторій»; без ролі — підключити її на «Підключенні». */
  ["vcs-bad-target", "taskErrVcsTarget"],
  ["vcs-needs-role", "taskErrVcsRole"],
  /* Мітки задачі (4b-3): сервер відхилив їх за правилами (`bad-tags`) — людина виправляє в полі «Мітки». */
  ["bad-tags", "tagsBad"],
  /* Постачальник ролі відмовив (409 з кодом каркаса): готові тексти «Підключень», нових ключів не треба. */
  ["space-json-unreadable", "cnRefSpaceJson"],
  ["module-untrusted", "cnRefUntrusted"],
]);

/* Відмови, чия причина лише в тексті сервера: завислий (`check-timeout`, 504) чи зламаний (`module-error`, 502) модуль синку під
   час перевірки цілі, модуль, що не завантажився (`vcs-error`, 409). Власного ключа вони не мають: форма показує загальне «Не вдалося:
   <причина>» (`errFailed`), поле не підсвічує. Тут — код, а не ключ: `taskErrKey` для них лишається загальним. */
const TASK_ERR_REASON = new Set(["check-timeout", "module-error", "vcs-error"]);
/**
 * Чи показувати людині текст сервера як причину відмови створення задачі. Завжди — для `TASK_ERR_REASON`; а коли тіло запиту
 * несло `vcs` (`hadTarget`) — ще й для БУДЬ-ЯКОГО коду без власного ключа (`bad-settings`, `secrets-unreadable`, `bad-manifest`,
 * відмови каркаса й постачальника): загальне «Спробуй ще раз» там марне, повтор тієї ж відмови не зніме, а причина сервера —
 * єдине, що людина може виправити. Без `vcs` (звичайна задача, ЛІГА) поведінка стара: загальний текст.
 */
export const taskErrShowsReason = (code, hadTarget = false) =>
  TASK_ERR_REASON.has(code) || (hadTarget === true && !TASK_ERR_KEYS.has(code));

/** Ключ словника для відмови створення задачі; невідомий код (і мережа) — загальний. */
export const taskErrKey = (code) => TASK_ERR_KEYS.get(code) ?? "taskErrGeneric";

/* Ключі помилок, що стосуються поля «Тека» майстра (`from`). `wzErrFromPlain` сюди НЕ входить: простір без інтеграцій
   людина в майстрі не вибирає, тож це не помилка поля. */
const FROM_KEYS = new Set(["wzFromRequired", "wzErrFromNotFound", "wzErrFromNoIndex", "wzErrFromContains", "wzErrFromTooBig"]);

/** Поле форми задачі, про яке ключ помилки (`taskFormError`/`taskErrKey`): `title`, `id`, `repo` (адреса синку), `tags` (мітки), `from` (тека майстра) або `null`. */
export const taskErrField = (key) => (key === "titleRequired" ? "title"
  : (key === "idBad" || key === "idTaken" || key === "wzErrTaskDirExists") ? "id"
    : key === "taskErrVcsTarget" ? "repo"
      : key === "tagsBad" ? "tags"
        : FROM_KEYS.has(key) ? "from" : null);

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

/* ── що додав Task 8 (модулі 2а): публікація за `capabilities.publish` ──────────────────
   До модулів «публікація» й «усе назовні» були одним питанням — `integrations`: простір без
   інтеграцій не мав ні GitLab, ні кнопки «Опублікувати». Тепер у такому просторі публікує
   вбудований `static-publish` (локальна тека, `/published/<простір>/<задача>/`), тож питань
   стало два: чи є ХТОСЬ, хто публікує (`hasPublish`), і чи це саме ЛІГА (`isLegacyPublish`).
   Teams від 4c-3 — на `capabilities.notify` (`hasNotify`, вище); синк із git від 4a — на `capabilities.vcs` (`hasVcs`, вище); командний канал і вкладка «Команда» від 2b-2 — на
   `capabilities.comments` (`hasTeamComments`, нижче: рішення за роллю `comments`, не за `integrations`).

   Сервер віддає `capabilities` ТОТАЛЬНО (`{publish: '<id модуля>' | 'legacy' | null, tokens,
   [error]}`): нечитабельний `space.json` лягає в `capabilities.error`, а не в 5xx. Відповіді
   СТАРОЇ форми (без `capabilities`) лишаються валідними — тоді рішення за `integrations`, рівно
   `=== false`, як скрізь: простір без відомостей публікації в людини не краде. */

/** Чи є в просторі постачальник публікації (модуль або ЗАШИТИЙ код ЛІГА). Предикат зі спеки 2а. */
export const hasPublish = (space) =>
  (space?.capabilities ? !!space.capabilities.publish : space?.integrations !== false);

/**
 * Чи публікує саме ЛІГА (Vercel, пароль превʼю в `tasks.json`, Teams-канал задачі). Лише тоді мають
 * сенс пароль превʼю та його попередження: модуль має свій пароль — СЕКРЕТ, якого UI не знає, —
 * а `preview_password` у відповіді `/api/task` лишається ЛІГА-шним і в модульному просторі
 * показав би чужий пароль під чужою публікацією.
 */
export const isLegacyPublish = (space) =>
  (space?.capabilities ? space.capabilities.publish === "legacy" : space?.integrations !== false);

/** Слід ЛОКАЛЬНОЇ публікації з `/api/task` (`{module, path, published_at}`) — обʼєкт або `null`. */
const localOf = (task) => {
  const p = task?.publish_local;
  return p && typeof p === "object" && !Array.isArray(p) ? p : null;
};

/** Задача опублікована: у ЛІГА (`publish_url`) або локально модулем (`publish_local`). */
export const isPublished = (task) => !!task?.publish_url || !!localOf(task);

/** Слід публікації модулем «за адресою» з `/api/task` (`{module, state, published_at, url, gated}`) — обʼєкт або `null`. */
const remoteOf = (task) => {
  const p = task?.publish_remote;
  return p && typeof p === "object" && !Array.isArray(p) ? p : null;
};

/**
 * Чи превʼю задачі опублікував МОДУЛЬ «за адресою» (Vercel, 2b-1) — саме той, що є постачальником
 * простору, і саме на ту адресу, що зараз у `publish_url`. Рівно ця умова стоїть і на сервері перед
 * `publish_share_url`: слід ІНШОГО модуля, адреса, яку правили вручну чи перезаписала ЛІГА, — не наша
 * публікація, і посилання з паролем про неї було б вигадкою. ЛІГА — завжди ні: її публікація має свій
 * шлях (`preview_password`, `#k=` у `copyUrl`).
 */
export function isRemotePublish(task, space) {
  const provider = space?.capabilities?.publish;
  if (isLegacyPublish(space) || typeof provider !== "string" || !provider) return false;
  const r = remoteOf(task);
  const url = typeof task?.publish_url === "string" ? task.publish_url : "";
  return !!r && !!url && r.module === provider && r.url === url;
}

/**
 * Адреса локальної публікації на ОРИГІНІ КАНВАСА: `/published/<простір>/<задача>/` (так її і віддає
 * сервер у `local.url`). Для `/api/task` будуємо її самі зі ЗНАНИХ id — сегменти через
 * `encodeURIComponent`, як `quote(…, safe="")` на сервері. Нема id простору чи задачі — `null`:
 * адреси не вигадуємо.
 */
export function localPublishUrl(space, task) {
  const sid = space?.id;
  const tid = task?.id;
  if (typeof sid !== "string" || !sid || typeof tid !== "string" || !tid) return null;
  return `/published/${encodeURIComponent(sid)}/${encodeURIComponent(tid)}/`;
}

/**
 * Куди веде «Відкрити превью» / «Скопіювати посилання»: `{kind: 'local' | 'external', url, at}` або
 * `null`. `at` — мілісекунди публікації для ЛОКАЛЬНОЇ (`published_at` у ISO UTC; не розбирається —
 * `null`), для ЗОВНІШНЬОЇ — `null` (її `published_at` — локальний `ДД.ММ.РРРР ГГ:ХХ`, і сервер
 * цього поля в UI не потребує). Коли є обидва сліди, перемагає той, що відповідає постачальнику
 * простору: модуль → локальна, ЛІГА → зовнішня. Другий лишається запасним: простір міг змінити
 * постачальника після публікації, а слід, на який людина ще може клікнути, не губимо.
 *
 * Виняток із «модуль → локальна» — модуль «за адресою» (Vercel): коли `publish_remote` належить
 * саме постачальнику простору й адресі (`isRemotePublish`), перемагає ВІН, навіть якщо від колишнього
 * `static-publish` лишився `publish_local`. Така ціль несе `remote: true` і `share` — посилання для колег,
 * яке склав СЕРВЕР (`publish_share_url`, з `#k=<пароль>`, коли превʼю з паролем): UI його не складає.
 */
export function previewTarget(task, space) {
  const local = localOf(task) ? localPublishUrl(space, task) : null;
  const ext = typeof task?.publish_url === "string" && task.publish_url ? task.publish_url : null;
  const asLocal = () => {
    const ms = Date.parse(localOf(task).published_at);
    return { kind: "local", url: local, at: Number.isFinite(ms) ? ms : null };
  };
  const asExternal = () => ({ kind: "external", url: ext, at: null });
  if (isLegacyPublish(space)) return ext ? asExternal() : (local ? asLocal() : null);
  /* Зовнішня адреса в просторі, де публікує НЕ ЛІГА, і не слід цього модуля (залишок: простір перемкнули з Vercel на
     `static-publish`, чи інший модуль, а `publish_url` лишився): ціль позначена `leftover` — `copyUrl` не дописує до неї ЛІГА-шний
     `#k=<preview_password>&p=…` (пароль ЛІГА до цієї адреси не належить), лише саму адресу, і лише безпечну. */
  const asLeftover = () => ({ ...asExternal(), leftover: true });
  if (isRemotePublish(task, space)) {
    /* Слід модуля з адресою, яку не можна відкривати (`javascript:`, `http:` — файл правили вручну), цілі не дає: ні «Відкрити», ні
       копіювання. Лишається запасна локальна, якщо вона є. */
    if (safeRemoteUrl(ext)) return { ...asExternal(), remote: true, share: remoteShareUrl(task, ext) };
    return local ? asLocal() : null;
  }
  return local ? asLocal() : (ext ? asLeftover() : null);
}

/**
 * Посилання, яке кладуть у буфер. ЗОВНІШНЄ ЛІГА — як було до модулів: `<url>/#k=<пароль>&p=<сторінка>`
 * (обидва значення закодовано); ЛІГА-шний фрагмент — ЛИШЕ для цілі, яку `previewTarget` дав постачальнику `legacy`.
 * ЗАЛИШОК (`leftover`: адреса не від поточного постачальника — простір перемкнули з Vercel на `static-publish` чи інший
 * модуль) — сама адреса без фрагмента й лише безпечна (`safeRemoteUrl`; небезпечної — `null`, копіювати нічого). ЛОКАЛЬНЕ —
 * абсолютна адреса канваса БЕЗ фрагмента: пароль модуля — секрет, UI його не знає, а ЛІГА-шний сюди не належить; хто відкриє,
 * введе його сам (якщо гейт увімкнено). МОДУЛЬ «за адресою» — готове `target.share` від сервера, дослівно.
 */
export function copyUrl(target, { origin = "", pageId = "", password = "" } = {}) {
  if (!target) return null;
  if (target.kind === "local") return `${origin}${target.url}`;
  if (target.leftover) return safeRemoteUrl(target.url);
  /* Модуль «за адресою» (Vercel): посилання склав сервер — `publish_share_url`, з `#k=<пароль>` лише для
     збірки з паролем, що не змінився. Кладемо ДОСЛІВНО: `password` тут — ЛІГА-шний (`preview_password`), чужий для цієї
     публікації, а друге `#k=` зіпсувало б посилання. */
  if (target.remote) return target.share || target.url;
  return `${target.url.replace(/\/+$/, "")}/#k=${encodeURIComponent(password)}&p=${encodeURIComponent(pageId)}`;
}

/**
 * Адреса з ВІДПОВІДІ сервера, яку можна відкрити вікном: відносний шлях `/published/<…>` на ТОМУ САМОМУ
 * оригіні. Лише регекспу мало: `/published/../api/task` і `/published/%2e%2e/api/task` схожі на публікацію,
 * але браузер зводить `..` (і `%2e%2e`) і веде в `/api/task`. Тому, крім форми, адресу РОЗВʼЯЗУЄМО (`new URL`
 * від `origin`) і вимагаємо: оригін не змінився, шлях розвʼязаного лишився під `/published/`, а жодна
 * складова вхідного шляху — навіть після розкодування — не є `.` чи `..` (так відсікаємо й `..%2f..`, який
 * браузер не зводить, а сервер міг би розкодувати). Решту (абсолютний URL, `//хост`, `javascript:`, пробіли,
 * зворотний слеш) відкидаємо ще регекспом. `origin` — оригін канваса (`location.origin`); у Node-тестах його
 * передають явно.
 */
export function safeLocalUrl(url, origin = globalThis.location?.origin ?? "http://localhost") {
  if (typeof url !== "string" || !/^\/published\/[^/\\\s][^\\\s]*$/.test(url)) return null;
  let resolved;
  let base;
  try { base = new URL(origin); resolved = new URL(url, base); } catch { return null; }
  if (resolved.origin !== base.origin || !resolved.pathname.startsWith("/published/")) return null;
  const pathPart = url.split(/[?#]/)[0];
  for (const seg of pathPart.split("/")) {
    let plain;
    try { plain = decodeURIComponent(seg); } catch { return null; }
    if (plain.split(/[\\/]/).some((x) => x === "." || x === "..")) return null;
  }
  return url;
}

/* Хост — DNS-імʼя, а не IP: рівно правило ядра (`serve._url_host_ok`). Дві й більше непорожні мітки (`a.b`; одномітковий
   `localhost` і десяткове `2130706433` — ні), кожна — літери/цифри/дефіс, не з дефіса й не на дефіс, ≤ 63; ≤ 253 усього; ОСТАННЯ
   мітка починається з літери (TLD: `app`, `xn--p1ai`) — тож `127.0.0.1`, `0x7f.1`, `169.254.169.254` не проходять. */
const HOST_LABEL_RE = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i;
function isDnsHost(host) {
  if (typeof host !== "string" || !host || host.length > 253) return false;
  const labels = host.split(".");
  return labels.length >= 2 && labels.every((l) => HOST_LABEL_RE.test(l)) && /^[a-z]/i.test(labels[labels.length - 1]);
}

/**
 * Зовнішня адреса з ВІДПОВІДІ сервера, яку можна відкрити вікном: абсолютний `https://` з хостом-DNS-імʼям (не IP-адреса в
 * жодній формі — `127.0.0.1`, `2130706433`, `0x7f.1`, `[::1]` — і не одномітковий `localhost`; ті самі правила, що в ядра), БЕЗ
 * облікових даних (`user:pw@`, навіть порожніх) і лише друковний ASCII — без пробілів, керівних, зворотного слеша
 * (який браузер читає як `/`) і кирилиці (IDN лише як punycode). Усе інше — `null`, і кнопки «Відкрити» нема: сервер
 * свою адресу вже перевірив (Task 1), але відповідь модуля й слід у `iterations.json` — дані, а не наказ, і
 * `javascript:`/`data:` у `window.open` — вже не посилання. Повертає РЯДОК як є (не нормалізований).
 */
export function safeRemoteUrl(url) {
  if (typeof url !== "string" || !/^https:\/\/[\x21-\x5b\x5d-\x7e]+$/.test(url)) return null;
  const authority = url.slice("https://".length).split(/[/?#]/, 1)[0];
  if (!authority || authority.includes("@")) return null;
  /* Хост — ТАК, ЯК НАПИСАНО, а не як його нормалізує `URL`: `0x7f.1` і `2130706433` браузер зведе до `127.0.0.1`, а `%2e` у хості —
     до крапки (ядро бачить `hostname` буквально й такі форми відхиляє). Лише ASCII-мітки, остання — з літери: нормалізація
     з такого запису IP зробити не може. */
  const written = authority.startsWith("[") ? authority : authority.split(":")[0];
  if (!isDnsHost(written)) return null;
  try {
    const u = new URL(url);
    if (u.protocol !== "https:" || !u.hostname || u.username || u.password) return null;
  } catch { return null; }
  return url;
}

/**
 * Посилання для колег після публікації модулем «за адресою»: `publish_share_url` ОНОВЛЕНОЇ задачі (сервер уже
 * дописав `#k=<пароль>`), але лише коли воно про ЦЮ адресу (`url` з відповіді публікації): якщо оновлення задачі не
 * вдалось, у `task` лишилось посилання від попередньої публікації — його не копіюємо. Нема — сама адреса. Нема й її — `null`.
 */
export function remoteShareUrl(task, url) {
  const u = typeof url === "string" && url ? url : null;
  return u && isShareOf(task?.publish_share_url, u) ? task.publish_share_url : u;
}

/* Посилання `share` — це ЦЯ адреса `url`: або вона сама, або вона з фрагментом (`url#…`). Просто `startsWith(url)` пропустило б
   `https://pv-1.vercel.app.evil.example/…` (адреса — префікс чужого хоста), тому межа — рівно кінець рядка чи `#`. */
const isShareOf = (share, url) => typeof share === "string" && (share === url || share.startsWith(`${url}#`));

/**
 * Куди веде «Відкрити» після публікації модулем «за адресою»: на ПОСИЛАННЯ З ПАРОЛЕМ (`share`, з `#k=`), щоб власник не впирався в
 * власний гейт, коли воно про цю адресу й саме безпечне (`safeRemoteUrl`: ASCII-фрагмент без пробілів); інакше — на адресу, якщо
 * безпечна; інакше `null`. Адреса небезпечна — не відкриваємо нічого, навіть посилання: його база — та сама адреса.
 */
export function remoteOpenUrl(share, url) {
  const u = safeRemoteUrl(url);
  if (!u) return null;
  return isShareOf(share, u) && safeRemoteUrl(share) ? share : u;
}

/* Скільки попереджень модуля й якої довжини показує плашка: сервер уже тримає ≤ 5 по ≤ 300, але відповідь — дані. */
const NOTICE_MAX_LINES = 5;
const NOTICE_MAX_LEN = 300;

/**
 * Додаткові рядки плашки «Опубліковано на Vercel»: `[{text}]` — попередження модуля (як ТЕКСТ: `app.js` кладе їх
 * через `textContent`, розмітки тут немає), а коли попереджень нема, але перевірка превʼю без входу не вдалась
 * (`verified === false`) — одна нейтральна підказка `[{key}]`. `verified` не названо взагалі — мовчимо: тривога без
 * підстави гірша за її відсутність.
 */
export function remoteNoticeLines(r) {
  const warns = (Array.isArray(r?.warnings) ? r.warnings : [])
    .filter((w) => typeof w === "string" && w.trim())
    .slice(0, NOTICE_MAX_LINES)
    .map((w) => ({ text: w.trim().slice(0, NOTICE_MAX_LEN) }));
  if (warns.length) return warns;
  return r?.verified === false ? [{ key: "publishRemoteUnverified" }] : [];
}

/**
 * Код, яким сервер каже «коментарі до превʼю не додано» (`comments_unavailable` у відповіді публікації), або `null`. Це код
 * відмови модуля коментарів (`module-error`, `space-json-unreadable`, `bad-settings`…), без тексту й значень; відповідь —
 * дані, тож код іде в текст лише коли має вигляд коду (`[A-Za-z0-9_-]`, до 64 знаків), а не як довільний рядок сервера.
 */
export function commentsUnavailableCode(r) {
  const c = r?.comments_unavailable;
  return typeof c === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(c) ? c : null;
}

/**
 * Попередження прибирання старих публікацій (`cleanup_warning` у відповіді публікації ЛІГИ, 4b-1) або `null`. Лише сторож: непорожній
 * рядок — як є, решта (немає ключа, не рядок) — `null`. Текст — від модуля, готова фраза («Старі публікації не прибрано: <причина>»); `app.js`
 * показує його СИРИМ поруч із `domain_warning`, без `t()` і без розбору (рішення 30.10.2026: текст сервера не парсимо).
 */
export function cleanupWarning(r) {
  const raw = r?.cleanup_warning;
  return typeof raw === "string" && raw !== "" ? raw : null;
}

/** Id вбудованого модуля публікації на Vercel — єдиний, чиє імʼя можна називати в текстах UI. */
const VERCEL_MODULE = "vercel-publish";

/** Чи публікує простір саме Vercel-модулем: слово «Vercel» у плашці й тості — лише тоді (`isRemotePublish` — для будь-якого url-модуля). */
export const isVercelPublish = (space) => space?.capabilities?.publish === VERCEL_MODULE;

/**
 * Що показати людині, коли відповідь `POST /api/publish` прийшла: `{kind, show, key?}`.
 *   · `kind` — `legacy` (ЛІГА: `url`), `remote` (модуль «за адресою»: `url`), `local` (модуль у теку: `local`), `failed` (решта — ЛІГА без
 *     деплою тощо);
 *   · `show` — `render` (ЛІГА: лише перемальована смуга), `plash` (стійка плашка з діями), `toast` (короткий тост із назвою задачі),
 *     `dialog` (діалог «деплой не вдався»);
 *   · `key` — ключ словника тексту плашки чи тосту.
 * `space` — простір, у якому публікацію ВИКЛИКАЛИ, а не поточний: Vercel-публікація триває хвилини, і людина встигає перейти на іншу
 * задачу чи в інший простір; рішення «ЛІГА чи модуль» за ПОТОЧНИМ простором показало б чужу плашку (або ніякої — для ЛІГА). `sameTask` —
 * чи людина досі на тій самій задачі (рівно `true`): плашка й `render()` належать лише їй, інакше — тост із назвою, а нова задача
 * лишається недоторканою.
 */
export function publishReaction(r, space, sameTask) {
  const here = sameTask === true;
  if (r?.url) {
    if (isLegacyPublish(space)) return here ? { kind: "legacy", show: "render" } : { kind: "legacy", show: "toast", key: "publishToastDone" };
    const vercel = isVercelPublish(space);
    return here
      ? { kind: "remote", show: "plash", key: vercel ? "publishRemoteDone" : "publishRemoteDoneGeneric" }
      : { kind: "remote", show: "toast", key: vercel ? "publishToastRemote" : "publishToastDone" };
  }
  if (r?.local) {
    return here ? { kind: "local", show: "plash", key: "publishLocalDone" } : { kind: "local", show: "toast", key: "publishToastLocal" };
  }
  return { kind: "failed", show: "dialog" };
}

/**
 * Пароль превʼю й попередження про нього. Живе окремо від `barState`, бо «чий це пароль» — правило:
 * у просторі, де публікує МОДУЛЬ, `preview_password` у відповіді сервера — це ЛІГА-шний, і ні він, ні
 * `stale`/`ungated` (лічильники ЛІГА-збірки; для модуля сервер віддає `preview_gate.state ===
 * 'module'`) не про цю публікацію. Для ЛІГА — рівно як було: попередження лише для ОПУБЛІКОВАНОЇ
 * в ЛІГА задачі (`publish_url`): `publish/`, зібраний без деплою, нікому не роздано.
 */
export function pwView(task, space) {
  if (!task || !isLegacyPublish(space)) return { pw: "", pwCustom: false, pwStale: false, pwUngated: 0 };
  const gate = task.preview_gate;
  return {
    pw: task.preview_password || "",
    pwCustom: !!task.preview_password_custom,
    pwStale: !!task.publish_url && gate?.state === "stale",
    pwUngated: task.publish_url && gate?.state === "ungated" ? gate.ungated : 0,
  };
}

/* Відмови `POST /api/publish` (`code`) → ключі словника. `Map`, не обʼєкт (як `ERR_KEYS`). */
const PUBLISH_ERR_KEYS = new Map([
  ["no-publish-module", "publishErrNoModule"],
  ["bad-folder", "publishErrBadFolder"],
  ["publish-busy", "publishErrBusy"],
  ["bad-task-id", "publishErrBadTaskId"],
  ["module-error", "publishErrModule"],
  ["module-untrusted", "publishErrUntrusted"],
  /* Код `vercel-auth` — контракт саме Vercel-модуля (ядро знає лише його статус), тож слово «Vercel» у тексті відмови доречне
     без звірки з постачальником простору; плашка ж і тост, які буває показує ЛЮБИЙ url-модуль, називають Vercel лише тоді,
     коли постачальник — `vercel-publish` (`publishReaction`, `isVercelPublish`). */
  ["vercel-auth", "publishErrVercelAuth"],
  ["vercel-busy", "publishErrVercelBusy"],
  /* Вхід через системний Vercel CLI (`auth: cli`, 4b-1): немає Node/npx, CLI не увійшов, немає доступу до команди (scope),
     деплой відхилено (текст сервера), деплой не надрукував адресу. */
  ["no-node", "publishErrNoNode"],
  ["vercel-login", "publishErrVercelLogin"],
  ["vercel-scope", "publishErrVercelScope"],
  ["vercel-deploy", "publishErrVercelDeploy"],
  ["vercel-no-url", "publishErrVercelNoUrl"],
]);

/* Текст відмови з відповіді сервера для другого абзацу: `error` із тіла JSON (`api()` ріже `message` по 200 знаків, а тіло
   лишає до 1000), інакше `message`; керівні символи — пробілом, не довше 300. Це лише ТЕКСТ: `tell` кладе його через
   `textContent`. */
const DETAIL_MAX = 300;
function serverText(e) {
  let text = typeof e?.message === "string" ? e.message : "";
  try {
    const j = JSON.parse(e?.body);
    if (typeof j?.error === "string") text = j.error;
  } catch { /* тіло не JSON — лишаємо `message` */ }
  return text.replace(/[\x00-\x1f\x7f]+/g, " ").trim().slice(0, DETAIL_MAX);
}

/* Код теки, який можна показати: `path-…` (відмова `folder_ok`) або `spaces-…`. Усе інше — це могла б
   бути сама тека, а шляхи в тексті відмови нам не потрібні. */
const FOLDER_CODE_RE = /^(?:path|spaces)-[a-z-]{1,30}$/;

/* Текст, яким сервер каже «жодної ітерації не позначено»: `send_error(400, …)` — НЕ JSON, а розмітка, і
   причина лежить у рядку статусу (`statusText`) та тілі, а не в `code`. `api()` (`app.js`) кладе їх на помилку. */
const NO_ITERATIONS_RE = /no iterations marked/i;

/**
 * Що сказати людині, коли публікація впала: `{key, args, reasonKey?}`; `app.js` робить
 * `t(key, ...(reasonKey ? [t(reasonKey)] : args))`. Відомі коди модульної публікації мають свій людський
 * текст; `bad-folder` несе причину: для `path-*`, які
 * знає діалог просторів, — його ж людський текст (`spaceErrKey`, `reasonKey`), для решти (`path-deai-home`,
 * `path-invalid`, `spaces-unreadable`) — сам код як запасний варіант, і більш нічого з відповіді.
 * `vercel-auth`, `vercel-deploy` і `module-error` несуть ТЕКСТ СЕРВЕРА (`args: [текст]`, ≤ 300): ядро й модуль уже вирізали з нього секрети, а причина
 * («Vercel відмовив у доступі (HTTP 403): …», «збірка ERROR; проєкт видалено») — те, що людина може виправити чи перевірити.
 * 400 БЕЗ коду — це `send_error`: «жодної ітерації не позначено» лише коли ТЕКСТ це каже (рядок статусу чи
 * тіло), а інший 400 (`bad payload`) — загальна відмова. Решта — «Не вдалося: …» з текстом сервера.
 */
export function publishErr(e) {
  const code = e?.code;
  const key = typeof code === "string" ? PUBLISH_ERR_KEYS.get(code) : undefined;
  /* `vercel-auth` — єдина модульна відмова з другим абзацом: «Vercel відмовив у доступі (HTTP 403): …» — причина, яку
     людина може виправити (права токена, тариф, команда), а сервер уже вирізав із неї секрети й обмежив довжину. */
  if (key === "publishErrVercelAuth" || key === "publishErrModule" || key === "publishErrVercelDeploy") return { key, args: [serverText(e)] };
  if (key === "publishErrBadFolder") {
    const why = FOLDER_CODE_RE.test(e?.message ?? "") ? e.message : "";
    const reasonKey = why ? spaceErrKey(why) : "spaceErrGeneric";
    return reasonKey !== "spaceErrGeneric" ? { key, args: [], reasonKey } : { key, args: [why] };
  }
  if (key) return { key, args: [] };
  if (e?.status === 400 && !code && NO_ITERATIONS_RE.test(`${e.statusText ?? ""}\n${e.body ?? ""}\n${e.message ?? ""}`)) {
    return { key: "publishErrNoIterations", args: [] };
  }
  return { key: "errFailed", args: [e?.message ?? ""] };
}
