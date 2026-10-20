/**
 * ⌘K палітра команд (Task 6 Плану B) — реєстр дій і чисті функції розмітки,
 * той самий рядок думки, що в `bar-model.js`+`shell-bar.js`: жодного слухача,
 * жодного звернення до DOM, жоден оверлей сам себе не відкриває. Виконання
 * дій — за `app.js`, який кличе `BAR_ACTIONS`/`PANEL_ACTIONS` (Task 3/4) з
 * `act`/`val`, узятих звідси, — НЕ другу реалізацію тих самих кнопок.
 *
 * Навіщо палітра існує — спека задачі: смуга тримає 7 груп контролів проти
 * 16 колишніх, і частина дій рідкісна настільки, що місця в інтерфейсі не
 * варта взагалі (видалити ітерацію, підтягнути з GitLab, зняти кадри,
 * скопіювати посилання, перемкнути мову). Палітра — їхній дім і ДРУГИЙ шлях
 * до всього іншого.
 *
 * Джерело вигляду — затверджений прототип `docs/proto/shell.html`, функції
 * `actions()`/`renderPalette()`/`renderKeys()`. Форма реєстру тут НЕ
 * копіює прототипну буквально (`{g,i,t,k,a,v,off,why,alias,d}` із готовим
 * ПЕРЕКЛАДЕНИМ текстом `t`) — вона несе `labelKey`/`whyKey` (ІМ'Я ключа), за
 * тим самим контрактом, що `bar-model.js` вже встановив для смуги: цей
 * модуль (як і той) НЕ кличе `t()` у `paletteActions()`, лише називає ключі.
 * `t()` кличуть уже `paletteHTML()`/`paletteListHTML()`/`keysHTML()` — шар
 * розмітки, за патерном `shell-bar.js`.
 *
 * Три реальні вади прототипу, знайдені читанням його ж коду виконання
 * (`exec()`, `case 'pal'`), НЕ перенесені сюди:
 *
 *   1. `openPreview` у прототипному `actions()` не має `a` (act) ВЗАГАЛІ —
 *      рядок `{g:'gPub', i:'ext', t:t('openPreview'), off:!c.published,
 *      why:t('whyNoPublish')}` без `a:'openpreview'`. У прототипі це не
 *      страшно (`exec()` для `.a`-less пункту показує заглушку-тост), а в
 *      бою це була б кнопка, що нічого не робить, — рівно та вада, від якої
 *      застерігає задача (п.5 списку нижче). Тут `openpreview` несе
 *      `act:"openpreview"`, як і решта дій публікації.
 *   2. Живе фільтрування (`document.addEventListener('input', …)`,
 *      `docs/proto/shell.html`) малює список ДРУГИМ, окремим шматком
 *      розмітки — паралельно до `renderPalette()`, тим самим текстом
 *      `.pal-it`, зібраним наново. Два джерела одного рядка розійшлись би на
 *      першій же правці одного з них. Тут список — ОКРЕМА чиста функція
 *      (`paletteListHTML`), яку кличе і повний `paletteHTML()` (перший
 *      рендер), і `app.js` напряму (кожне натискання клавіші, живлення
 *      `.pal-list` без пересотворення `<input>` — фокус і курсор поля не
 *      мають смикатись при кожній літері).
 *   3. Колонка `kbd` прототипу обіцяла ВІСІМ акордів, яких сам прототип
 *      не мав: `⌘⇧T`/`⌘⇧I`/`⌘⇧P` (переходи), `⇧N`/`⇧P` (нова ітерація й
 *      сторінка), `⌘⏎` (публікація) — і ще два, `⌥M`/`⌘\`, які він таки мав.
 *      Перенос привіз усі вісім підказок і жодного обробника до перших
 *      шести. Передрелізний аудит 02.09.2026 їх виміряв, і рішення власника
 *      РІЗНЕ за напрямком, тому записане тут по пунктах:
 *        · `⌥M` і `⌘\` РЕАЛІЗОВАНО в `app.js` — прототип (затверджений
 *          дизайн) їх справді має, тобто загубився обробник, а не задум;
 *        · `⌘⏎` ПРИБРАНО з підказок і НЕ реалізовано: публікація деплоїть на
 *          Vercel, а одноклавішний деплой — погана ідея, якої ніхто не
 *          просив;
 *        · `⌘⇧T`/`⌘⇧I`/`⌘⇧P`/`⇧N`/`⇧P` ПРИБРАНО: власника немає, а `⇧P` ще й
 *          конфліктує з власною клавішею `p` коментатора — він слухає
 *          `c`/`p`/`h` у своєму захопленні й виходить лише на
 *          `meta`/`ctrl`/`alt`, тобто `⇧P` дійшла б до нього.
 *      У колонці `kbd` лишились три підказки, і в кожної є обробник: `⌥M`,
 *      `⌘\` (обидві — `app.js`) і `I` (інспектор, `vendor/inspector.js`).
 *      Інваріант «кожна підказка має обробника» — і для цієї колонки, і для
 *      `keysHTML()` — стереже `tests/shell-palette.test.mjs`, розбором самих
 *      джерел, а не переліком дозволених гліфів (перелік і був тим, що
 *      пропустило всі вісім).
 *
 * Фільтр працює ОБОМА мовами одразу (`ALIASES`): без цього запит «language»
 * в українському інтерфейсі чи «мова» в англійському не знаходив би пункту
 * мови — саме так поводився прототип до цього виправлення.
 *
 * Дії БЕЗ `act` («лише перехід» — `navOnly:true`) — це рівно два пункти
 * групи `gGo`: перейти до крихти ітерації чи розгорнути панель сторінок.
 * («Задачі» перестали бути переходом у батчі 1.52: це `act:"home"`, той самий
 * вхід, що логотип у смузі, — екран, а не дропдаун крихти.) Вони не належать `BAR_ACTIONS`/`PANEL_ACTIONS` (відкрити
 * дропдаун — не «дія смуги», а той самий `state.openDd`, яким керує клік по
 * самій крихті), тому `app.js` виконує їх напряму, тим самим станом. Кожна
 * інша дія несе `act` — тест `tests/shell-palette.test.mjs` стереже, що
 * третього варіанту («ні act, ні navOnly») не буває.
 */

import { figmaWhyKey, flowWhyKey, linkWhyKey } from "./bar-model.js";
import { hasPublish, hasTeamComments } from "./spaces-model.js";
import { t } from "./i18n.js";
import { esc } from "./esc.js";
import { ico } from "./icons.js";

/**
 * Склад реєстру зі стану екрана `state`:
 *   mode: 'layout'|'overview', view: 'grid'|'flow' — ті самі терміни, що
 *     `barState()` уже несе смузі.
 *   hasIteration: boolean — керує групами `gIter`/`gFrames` і пунктом
 *     `go-iter` (той самий інваріант, що крихта ітерації смуги: немає
 *     ітерації — немає й дій над нею, а не «є, але вимкнені»).
 *   pagesError, flowRaw, flowError — сирі поля для `flowWhyKey`
 *     (`bar-model.js`, той самий виклик, що робить сама смуга).
 *   published, iterPub, pagePub — сирі поля для `linkWhyKey`.
 *   figmaBusy: boolean — захоплення «В Figma» вже йде (`figmaWhyKey`).
 *   pickedPage: string|null — обрана зараз сторінка (дії `renpage`/
 *     `hidepage`/`delpage` діють на НЕЇ, той самий принцип, що дії над
 *     ітерацією діють на `curIter()`).
 *   pickedKind: 'folder'|'page'|'state'|null — тип ВИБРАНОГО в панелі вузла
 *     (одного елемента `panelSel`, інакше `pickedPage`); pickedHasParent:
 *     boolean — чи стоїть він не в корені (для «винести на рівень вище»);
 *     pickedHasChildren — чи є в нього діти (для «розгрупувати»); selCount —
 *     скільки рядків виділено в панелі.
 *   gl: 'off'|'sync'|'ahead'|'behind'|'error', iterLabel: string — той самий
 *     `state.iterLabel`, яким `shell-bar.js` (`ddGitlab`) підставляє номер
 *     ітерації в `t('glPush'|'glPull', iterLabel)`.
 *   shots: {have, stale, total, running, bad} | null — те, що `panelState()`
 *     кладе в `state.shots`; `null`, коли немає ітерації (той самий гейт).
 *   lang: 'uk'|'en' — поточна мова (`getLang()`).
 *   canInstall: boolean — Chrome віддав `beforeinstallprompt`, і подію ще не
 *     використано; standalone: boolean — вікно вже встановленого застосунку
 *     (`display-mode: standalone`). Пункт встановлення є лише за
 *     `canInstall && !standalone` (див. `installActions`).
 *   spaces: [{id, name, available?}] | undefined — перелік просторів з `/api/spaces`;
 *     без МАСИВУ пунктів просторів нема зовсім (шар вимкнено). spaceId: string|null —
 *     поточний простір (за його відсутності — `space.id`); поточний у переліку
 *     не пропонується. space: {id, integrations, capabilities}|null — поточний простір;
 *     `integrations === false` прибирає GitLab, а публікацію й командний канал — їхні
 *     постачальники: `capabilities.publish` і `capabilities.comments` (`hasPublish`,
 *     `hasTeamComments`; стара форма без `capabilities` — за `integrations`).
 */
/* Мова інтерфейсу — єдина група, що не залежить від задачі: її читає і звичайний
   реєстр, і екран «Задачі». Одна функція на обох, щоб два місця не розійшлись. */
function langActions(s) {
  return [
    {
      id: "lang-uk", group: "gSet", labelKey: "langUk", icon: "lang", act: "lang", val: "uk",
      disabled: s.lang === "uk", whyKey: s.lang === "uk" ? "langCur" : "",
    },
    {
      id: "lang-en", group: "gSet", labelKey: "langEn", icon: "lang", act: "lang", val: "en",
      disabled: s.lang === "en", whyKey: s.lang === "en" ? "langCur" : "",
    },
  ];
}

/* «Встановити як застосунок» (PWA, P1) — ТЕЖ дія самого застосунку, не задачі, тож
   її читає і звичайний реєстр, і екран «Задачі», як мову. Пункт ОМІТУЄТЬСЯ, а не
   «вимикається з причиною», бо причини в користувача нема: без події
   `beforeinstallprompt` (`canInstall`) системному діалогу нема що показати, а у
   вже встановленому вікні (`standalone`) пропонувати встановлення нічого. Подія
   приходить від Chrome, коли він сам вирішить, що сторінку можна встановити, — тож
   пункт зʼявляється, коли «можна». Виконує `app.js` напряму (`act:"pwainstall"`),
   як `lang`: це не смуга й не панель. */
function installActions(s) {
  if (!s.canInstall || s.standalone) return [];
  return [{ id: "pwa-install", group: "gSet", labelKey: "pwaInstall", icon: "download", act: "pwainstall" }];
}

/* Простори (Deai 1.0, етап 1) — «Простір: X» для кожного ІНШОГО простору й «Новий
   простір…», у `gGo`: це переходи, а не налаштування. Читає і звичайний реєстр, і
   екран «Задачі» — простір не залежить від задачі, як мова. Лише коли є МАСИВ
   `s.spaces` (шар вимкнено — нема й пунктів, а не «Новий простір…» без реєстру,
   який його прийняв би).

   Ім'я простору — дані користувача, тож підпис — `labelKey` + `labelArgs`, а не
   готовий рядок: реєстр не кличе `t()` (шапка файла), `itemHTML`/`searchText`
   розгортають аргументи. Поточний простір не пропонуємо: перейти в те місце, де
   ти є, — дія, що нічого не робить. Поточний — `spaceId` або `space.id`.
   Недоступний (`available === false`) тут ВИМКНЕНИЙ з причиною, а в смузі лише
   приглушений і КЛІКАБЕЛЬНИЙ — і це не неузгодженість, а різні способи показати
   одну причину. У смузі рядок показує `spaceUnavailable`, але справжній текст
   («файл задач не читається», `tasksErrSpaceUnavailable`) людина побачить лише
   перейшовши в простір, тож клік мусить працювати. Палітра цей текст друкує
   САМА: `itemHTML` ставить `whyKey` на місце клавіші, і причину видно в списку,
   не відкриваючи нічого, — а пункт, що веде на екран помилки, там зайвий.

   `id` = `space-go-<id простору>`, а «Новий простір…» — `space-new`: простір із
   id `new` (сервер такий приймає) давав би два однакові `space-new`.

   «Підключення простору «X»» (`space-conn`, етап 3a) — вхід на екран підключень
   ПОТОЧНОГО простору: лише коли поточний є в переліку (без нього нема чого
   підключати й нема назви для підпису) і не на самій сторінці `conn` (дія, що
   нічого не робить). Його id не перетинається з `space-go-<id>`. */
function spaceActions(s) {
  if (!Array.isArray(s.spaces)) return [];
  const cur = s.spaceId ?? s.space?.id;
  const out = s.spaces.filter((x) => x.id !== cur).map((x) => ({
    id: `space-go-${x.id}`, group: "gGo", labelKey: "spaceGo", labelArgs: [x.name], icon: "folder",
    act: "space", val: x.id,
    ...(x.available === false ? { disabled: true, whyKey: "spaceUnavailable" } : {}),
  }));
  /* «Підключення» поточного простору (етап 3a). Не на самій сторінці (дія, що нічого не робить) і лише коли поточний
     є в переліку: без простору нема чого підключати. `space-conn` не перетинається з `space-go-<id>`. */
  const me = cur != null && s.homePage !== "conn" ? s.spaces.find((x) => x.id === cur) : null;
  if (me) out.push({ id: "space-conn", group: "gGo", labelKey: "spaceConn", labelArgs: [me.name], icon: "sliders", act: "conn" });
  out.push({ id: "space-new", group: "gGo", labelKey: "spaceNew", icon: "plus", act: "spacenew" });
  return out;
}

export function paletteActions(state) {
  const s = state || {};
  const hasIteration = !!s.hasIteration;
  const out = [];
  /* Простір без інтеграцій (`space.integrations === false`): палітра не пропонує
     того, чого немає в смузі, — GitLab (`bar-model.js`, «Вимикач»). ОМІТ, не «вимкнено
     з причиною» (той самий вибір, що для груп, безглуздих у режимі). Рівно `=== false`.
     Командний канал коментарів (`aud-project`) тут уже НЕ на інтеграціях (2b-2): його
     дає роль `comments` — `hasTeamComments(space)`, див. групу `gSet` нижче.
     ПУБЛІКАЦІЯ (`publish`, `togglepub`, `copylink`, `openpreview`) від інтеграцій більше
     не залежить (модулі 2а, Task 8): вона йде на `hasPublish` (`capabilities.publish`) —
     простір без інтеграцій публікує вбудованим модулем у теку, і з палітри її забирає
     лише відсутність постачальника (`publish: null`). Тому колишній спільний
     `if (!noOutward)` розщеплено нижче на два. */
  const noOutward = s.space?.integrations === false;

  /* Екран «Задачі» (`homeOpen`, батч 1.52): смуга в цьому стані не має ні
     публікації, ні «Макет/Огляд», ні ітерацій — і палітра не сміє пропонувати
     те, чого смуга не показує: «Опублікувати» діяло б на задачу, якої людина
     зараз не бачить. ОМІТ, а не «вимкнено з причиною» — той самий вибір, що для
     груп, безглуздих у режимі (`gIter` без ітерації, `inspector` в «Огляді»);
     причина поруч (принцип 2) потрібна контролу, що ЛИШАЄТЬСЯ в режимі. `go-tasks`
     теж не пропонуємо: людина вже там, а «відкрити екран, на якому ти є»
     значило б дію, що нічого не робить. */
  if (s.homeOpen) return [...spaceActions(s), ...langActions(s), ...installActions(s)];

  /* ── gGo: переходи. `go-iter`/`go-pages` — «лише перехід», немає в
     BAR_ACTIONS/PANEL_ACTIONS свідомо; `go-tasks` має `act` ───── */
  /* `act:"home"` — той самий вхід на екран «Задачі», що логотип у смузі
     (`BAR_ACTIONS.home`): друга реалізація «відкрити список задач» розійшлась
     би з першою. Раніше це був `navOnly` і розкривало дропдаун крихти. */
  out.push({ id: "go-tasks", group: "gGo", labelKey: "tasks", icon: "task", act: "home" });
  if (hasIteration) {
    // Без ітерації дропдаун крихти порожній (`crumbIter` у `shell-bar.js`
    // повертає '' — крихти немає взагалі): перехід був би кнопкою, що
    // відкриває нічого. Той самий інваріант, що ховає й саму крихту.
    out.push({ id: "go-iter", group: "gGo", labelKey: "iterations", icon: "iter", navOnly: true });
  }
  // «Сторінки», навпаки, ЗАВЖДИ доречні: панель сама пояснює порожній стан
  // (`panelNoIt`), тобто перехід сюди ніколи не є нопом.
  out.push({ id: "go-pages", group: "gGo", labelKey: "pages", icon: "page", navOnly: true });
  out.push(...spaceActions(s));

  /* ── gView: та сама зона 2, що в bar-model.js — тут не КЛИЧЕ barModel(),
     бо тому потрібен куди ширший стан (taskId, iterList…), не потрібний
     палітрі; замість цього — той самий, вужчий розгляд полів. ──────────── */
  out.push({
    id: "mode", group: "gView", labelKey: "modeToggle", icon: "layout", kbd: "⌥M",
    act: "mode", val: s.mode === "overview" ? "layout" : "overview",
  });
  if (s.mode === "overview") {
    const flowWhy = flowWhyKey(s);
    out.push({ id: "view-grid", group: "gView", labelKey: "viewGrid", icon: "grid", act: "view", val: "grid" });
    out.push({
      id: "view-flow", group: "gView", labelKey: "viewFlow", icon: "flow", act: "view", val: "flow",
      disabled: !!flowWhy, whyKey: flowWhy || "",
    });
  }
  out.push({ id: "vp-desktop", group: "gView", labelKey: "vpDesktop", icon: "desktop", act: "vp", val: "desktop" });
  out.push({ id: "vp-tablet", group: "gView", labelKey: "vpTablet", icon: "tablet", act: "vp", val: "tablet" });
  out.push({ id: "vp-mobile", group: "gView", labelKey: "vpMobile", icon: "mobile", act: "vp", val: "mobile" });
  if (s.mode === "layout") {
    // Інспектор працює по живому DOM макета — немає в «Огляді», той самий
    // гейт, що ховає кнопку інспектора зі смуги (`TIERS.view`, bar-model.js).
    out.push({ id: "inspector", group: "gView", labelKey: "inspector", icon: "inspect", kbd: "I", act: "inspector" });
  }
  out.push({ id: "panel", group: "gView", labelKey: "layers", icon: "panel", kbd: "⌘\\", act: "panel" });
  out.push({ id: "clean", group: "gView", labelKey: "cleanView", icon: "eye", kbd: "⇧⌘\\", act: "clean" });

  /* ── gIter: існує лише разом з ітерацією — ОМІТ, а не «вимкнено», той
     самий вибір, що для крихти ітерації в смузі (не «є, вимкнена», а немає
     взагалі: «задача без ітерацій» — реальний старт кожної нової задачі,
     bar-model.js, коментар над `barModel`). ──────────────────────────── */
  if (hasIteration) {
    out.push({ id: "newit", group: "gIter", labelKey: "newIteration", icon: "plus", act: "newit" });
    out.push({ id: "renit", group: "gIter", labelKey: "renameIteration", icon: "pencil", act: "renit" });
    out.push({ id: "dupit", group: "gIter", labelKey: "dupIteration", icon: "copy", act: "dupit" });
  }

  /* ── gPage: навпаки, ПРИЧИНА ВИДИМА — той самий вибір, що робить сама
     панель шарів для своїх порожніх станів (`panelNoIt`/`errPagesLoadFailed`,
     shell-panel.js), а не мовчазне зникнення. Три причини за пріоритетом:
     нема ітерації → перелік сторінок не прийшов → сторінку ще не обрано. */
  const pageWhy = !hasIteration ? "panelNoIt"
    : s.pagesError ? "whyPagesError"
      : !s.pickedPage ? "whyNoPageSelected" : "";
  out.push({
    /* Панель не створює сторінок (їх створює Claude), тож пункт веде на ТЕКУ. */
    id: "newfolder", group: "gPage", labelKey: "newFolder", icon: "folderplus", act: "newfolder",
    // «Нова тека» не потребує ЩОБ УЖЕ БУЛА обрана сторінка — лише щоб
    // існувала ітерація й перелік прочитався (той самий `canAddPage` у
    // `shell-panel.js`, `openHTML`).
    disabled: !hasIteration || !!s.pagesError,
    whyKey: !hasIteration ? "panelNoIt" : (s.pagesError ? "whyPagesError" : ""),
  });
  out.push({
    id: "renpage", group: "gPage", labelKey: "renamePage", icon: "pencil", act: "renpage",
    disabled: !!pageWhy, whyKey: pageWhy,
  });
  out.push({
    id: "hidepage", group: "gPage",
    // Підпис називає ДІЮ (той самий принцип, що прототипний
    // `f.p.pub === false ? t('showPage') : t('hidePage')`): коли сторінка
    // вже прибрана з превью, пункт пропонує повернути її, а не повторює
    // те саме «Прибрати».
    labelKey: s.pagePub === false ? "showPage" : "hidePage",
    icon: "eye", act: "hidepage",
    disabled: !!pageWhy, whyKey: pageWhy,
  });

  /* Дерево (B4): дії над ВИБРАНИМ вузлом — тим самим, що `renpage`/`hidepage`
     (`pickedPage`), але з урахуванням його типу й місця в дереві. Причину
     вимкнення несе кожна: команда, що мовчки зникає, лишає питання «чому». */
  /* Вузол «вибрано», коли відомий його тип: тека не є `pickedPage` (її не
     відкривають), але групувати/виносити/фокусувати її можна. `selCount` — скільки
     рядків виділено: дії над ОДНИМ шаром при кількох мовчки взяли б «відкриту
     сторінку», якої людина не виділяла. */
  const base = !hasIteration ? "panelNoIt" : (s.pagesError ? "whyPagesError" : "");
  const many = (s.selCount ?? 0) > 1;
  const treeWhy = base || (many ? "whySelectOne" : (!s.pickedKind ? "whyNoPageSelected" : ""));
  const groupWhy = base || ((s.selCount ?? 0) >= 1 || s.pickedKind ? "" : "whyNoPageSelected");
  out.push({ id: "groupsel", group: "gPage", labelKey: "menuGroup", icon: "folder", act: "groupsel",
    disabled: !!groupWhy, whyKey: groupWhy });
  const ungroupWhy = treeWhy || (s.pickedKind !== "folder" ? "whyNotFolder"
    : (!s.pickedHasChildren ? "whyEmptyFolder" : ""));
  out.push({ id: "ungroup", group: "gPage", labelKey: "menuUngroup", icon: "folder", act: "ungroup",
    disabled: !!ungroupWhy, whyKey: ungroupWhy });
  out.push({ id: "outdent", group: "gPage", labelKey: "menuOutdent", icon: "chevleft", act: "outdent",
    disabled: !!treeWhy || !s.pickedHasParent,
    whyKey: treeWhy || (!s.pickedHasParent ? "whyTopLevel" : "") });
  out.push({ id: "focusbranch", group: "gPage", labelKey: "menuFocus", icon: "chevright", act: "focusbranch",
    disabled: !!treeWhy, whyKey: treeWhy });
  /* Тека не перемикається в стан/сторінку: сервер відповів би `treeErrBadKind`,
     тож кажемо те саме наперед. */
  const kindWhy = treeWhy || (s.pickedKind === "folder" ? "treeErrBadKind" : "");
  out.push({ id: "togglekind", group: "gPage",
    labelKey: s.pickedKind === "state" ? "menuToPage" : "menuToState", icon: "state", act: "togglekind",
    disabled: !!kindWhy, whyKey: kindWhy });

  /* ── gFrames: ОДИН перемикач старт/стоп — той самий `PANEL_ACTIONS.shoot`,
     не два статичні пункти прототипу («Зняти»/«Оновити», обидва на act:
     'shoot'). Підписи БЕЗ числа (`shotsTakeBare`/`shotsUpdateBare`/
     `shotsStop`): аргументи `t()` форма дії тепер уміє (`labelArgs`, див.
     `spaceActions` — там імʼя простору), але лічильник кадрів заради
     рідкісної дії не вартий ні другого джерела правди про нього, ні
     перемальовки палітри на кожен кадр. Секція взагалі не існує без ітерації — той самий гейт, що ховає
     секцію «Кадри» в самій панелі (`state.hasIteration`, `openHTML`). */
  if (hasIteration && s.shots) {
    const { running, have, stale, bad } = s.shots;
    const staleKnown = stale !== null && stale !== undefined;
    const allFresh = !running && have > 0 && staleKnown && stale === 0 && !bad;
    out.push({
      id: "shoot", group: "gFrames",
      labelKey: running ? "shotsStop" : (have > 0 ? "shotsUpdateBare" : "shotsTakeBare"),
      icon: running ? "stop" : (have > 0 ? "refresh" : "camera"),
      act: "shoot",
      disabled: allFresh, whyKey: allFresh ? "whyFresh" : "",
    });
  }

  /* ── gPub: та сама зона 3, що bar-model.js (публікація й GitLab), і той
     самий вибір — жодного гейту на `hasIteration` (bar-model.js теж його не
     ставить: `published`/`iterPub`/`pagePub` уже самі падають у безпечний
     стан без ітерації). ──────────────────────────────────────────────── */
  /* «В Figma» (T-41) — та сама дія, що кнопка смуги (`act:"figma"`), і та сама
     причина вимкнення (`figmaWhyKey`, `bar-model.js`). Активація з клавіатури
     ⌘K теж доходить до рамки: Enter у палітрі — такий самий жест, як клік. */
  const figmaWhy = figmaWhyKey(s);
  out.push({
    id: "figma", group: "gPub", labelKey: "toFigma", icon: "figma", act: "figma",
    disabled: !!figmaWhy, whyKey: figmaWhy,
  });
  if (hasPublish(s.space)) {
    out.push({
      id: "publish", group: "gPub", labelKey: s.published ? "update" : "publish",
      icon: "up", act: "publish",
    });
    out.push({ id: "togglepub", group: "gPub", labelKey: "showInPreview", icon: "eye", act: "togglepub" });
    const linkWhy = linkWhyKey(s);
    out.push({
      id: "copylink", group: "gPub", labelKey: "copyLink", icon: "link", act: "copylink",
      disabled: !!linkWhy, whyKey: linkWhy,
    });
    out.push({
      id: "openpreview", group: "gPub", labelKey: "openPreview", icon: "ext", act: "openpreview",
      disabled: !s.published, whyKey: s.published ? "" : "whyNoPublish",
    });
  }
  if (!noOutward) {
    // Той самий трьохгілковий розгляд, що `glItems` у `bar-model.js`
    // (`barModel`): «off» — лише «Налаштувати», інакше «Підтягнути» з'являється
    // ЛИШЕ при «behind», «Надіслати» є завжди, вимкнене з причиною при «sync».
    if (s.gl === "off") {
      out.push({ id: "glsetup", group: "gPub", labelKey: "glSetup", icon: "cloud", act: "glsetup" });
    } else {
      if (s.gl === "behind") {
        out.push({
          id: "glpull", group: "gPub", labelKey: "glPull", icon: "down",
          act: "glpull", val: s.iterLabel,
        });
      }
      out.push({
        id: "glpush", group: "gPub", labelKey: "glPush", icon: "cloud",
        act: "glpush", val: s.iterLabel,
        disabled: s.gl === "sync", whyKey: s.gl === "sync" ? "glSync" : "",
      });
    }
  }

  /* ── gSet: мова інтерфейсу — дім якраз тут (спека задачі, крок 4). Дію
     `act:"lang"` виконує `app.js` напряму (`switchLang`): це не смуга й не
     панель, а `setLang()`+`localStorage` під `LANG_KEY`, тож у
     `BAR_ACTIONS`/`PANEL_ACTIONS` цього ключа немає — і не мало б бути. */
  out.push(...langActions(s));
  out.push(...installActions(s));

  /* Аудиторія коментарів — і це НЕ дубль вкладок у панелі коментатора, а
     АВАРІЙНИЙ ВИХІД. Записано тут, бо без цього абзацу наступний прибере
     «дубль» — і буде послідовним, але не правим.

     Дім аудиторії — вкладки «Клод»/«Команда» в панелі САМОГО коментатора
     (принцип 6 PRODUCT.md; `AUDIENCES_TMPL` у `serve.py`). Але коли
     коментатор не піднявся — заблокований CDN Supabase, банер `__clDown` у
     рамці, — разом із ним зникає ВСЯ його поверхня, вкладки включно. Зі смуги
     перемикач прибрано, тож вернутись у канал Клода стало б НІЧИМ: рамка
     тримає `ch=project`, `commentMode` лежить у localStorage, і єдиною
     «кнопкою» лишилась би консоль браузера. Палітра — саме те місце, де
     живуть рідкісні дії й аварійні виходи (шапка файла), і це рівно той
     «виняток із записаною причиною», який принцип 4 PRODUCT.md дозволяє.
     Живий сторож сценарію — третій тест у
     `tests/live/comment-audience.test.mjs`.

     ⛔ `act: "aud"` — ТА САМА реалізація, що в приймача `postMessage` від
     вкладок (`BAR_ACTIONS.aud` → `setAudience` в `app.js`), а не друга копія:
     інакше позначка в оболонці розійшлась би з тим, що показано в рамці.

     ⛔ Гейт `hasIteration` — той самий, що в `gIter`: без ітерації
     `projectId` (`dc/<задача>/<ітерація>[/internal]`) не існує, рамка стоїть
     на `about:blank`, і перемикати канал було б ні для чого. ОМІТ, не
     «вимкнено».

     Поточний канал позначено `disabled` + `whyKey`, як поточна мова поруч:
     третього способу позначки реєстр не має, і вигадувати його заради двох
     пунктів означало б розійтись із сусідом по групі. */
  if (hasIteration) {
    for (const [id, ch, labelKey, icon] of [
      ["aud-local", "local", "audLocal", "comment"],
      ["aud-project", "project", "audProject", "globe"],
    ]) {
      /* Командного каналу в просторі без постачальника ролі `comments` нема (`GET /comments`,
         `?ch=project` → 409): локальний — єдиний, і аварійний вихід «до локального» лишається.
         Постачальник — зашитий ЛІГА (інтеграції) АБО модуль, тож це `hasTeamComments`
         (`capabilities.comments`), а не `integrations`: простір без інтеграцій із модулем
         коментарів має канал `project`, хоч GitLab у нього й нема. */
      if (ch === "project" && !hasTeamComments(s.space)) continue;
      out.push({
        id, group: "gSet", labelKey, icon, act: "aud", val: ch,
        disabled: s.commentMode === ch, whyKey: s.commentMode === ch ? "audCur" : "",
      });
    }
  }

  /* ── gDanger ──────────────────────────────────────────────────────────── */
  if (hasIteration) {
    out.push({ id: "delit", group: "gDanger", labelKey: "delIteration", icon: "trash", act: "delit", danger: true });
  }
  out.push({
    id: "delpage", group: "gDanger", labelKey: "delPage", icon: "trash", act: "delpage", danger: true,
    disabled: !!pageWhy, whyKey: pageWhy,
  });

  return out;
}

/**
 * Синоніми пошуку, які НЕ залежать від поточної мови — виправлена вада
 * прототипу (шапка файла, п. «фільтр обома мовами»): без цього запит
 * «language» в українському інтерфейсі чи «мова» в англійському не
 * знаходив би пункту перемикання мови, бо `t(a.labelKey)` завжди повертає
 * ОДНУ, поточну мову.
 */
const ALIASES = {
  "lang-uk": "мова language lang",
  "lang-en": "мова language lang",
  /* Обома мовами — як `lang-*`: «install» знаходить пункт в українському
     інтерфейсі, «встановити» — в англійському. */
  "pwa-install": "встановити застосунок додаток install app pwa deai canvas",
  /* Аварійний вихід мусить бути ЗНАХОДЖУВАНИЙ: вихід, якого не знайти, — не
     вихід, а рядок у реєстрі. Тому обидві мови плюс слово «коментар», яким
     дизайнер це й називає («де перемикнути коментарі»), і саме імʼя каналу
     («локальні»/«команда»), яким його звали в смузі до переїзду. */
  "aud-local": "аудиторія audience коментар comment клод claude локальні local",
  "aud-project": "аудиторія audience коментар comment команда team проєкт project",
  /* Простір: обома мовами, як мова вище, — «space» в українському інтерфейсі й
     «простір» в англійському. Ключ — не `id` дії, а слово `space`: пункти просторів
     мають динамічні id, див. `aliasOf`. */
  space: "простір space workspace",
};

/* Підпис дії мовою інтерфейсу: аргументи — `labelArgs` (ім'я простору), інакше
   `val` (номер ітерації для `glpush`/`glpull`). Одне місце на розмітку й пошук:
   розійдись вони — пошук знаходив би пункт за текстом, якого людина не бачить. */
const labelOf = (a) => t(a.labelKey, ...(a.labelArgs ?? [a.val]));

/* Пошукові псевдоніми. Пункти просторів мають динамічні id (`space-<id>`), тож
   для них — за `act`: «space»/«простір» знаходять їх обома мовами. */
const aliasOf = (a) => ALIASES[a.id] || (a.act === "space" || a.act === "spacenew" ? ALIASES.space : "");

const searchText = (a) => `${labelOf(a)} ${aliasOf(a)}`.toLowerCase();

/** Фільтр за запитом (порожній запит — усе). Пошук ігнорує регістр і пробіли з країв. */
export function filterActions(actions, query) {
  const q = String(query ?? "").trim().toLowerCase();
  if (!q) return actions;
  return actions.filter((a) => searchText(a).includes(q));
}

const itemHTML = (a, i, cur) => {
  const label = esc(labelOf(a));
  const sp = a.disabled ? esc(t(a.whyKey || "")) : esc(a.kbd || "");
  const cls = `pal-it${i === cur ? " pal-it--cur" : ""}${a.danger ? " pal-it--danger" : ""}`;
  return `<button class="${cls}" data-act="pal" data-val="${i}"${a.disabled ? " disabled" : ""}>
    ${ico(a.icon)}<span>${label}</span><span class="sp">${sp}</span></button>`;
};

/**
 * Список пунктів (`.pal-list` уміст) — ОКРЕМА функція від `paletteHTML`
 * (шапка файла, п. про живе фільтрування): і повний рендер, і кожне
 * натискання клавіші в полі пошуку кличуть САМЕ ЦЮ функцію, тож список не
 * може розійтись сам із собою.
 *
 * `cursor` клемпиться СЮДИ (як `S.palCur` у прототипному `renderPalette()`):
 * список після фільтра коротший за той, на якому рахувався курсор, — без
 * клемпу підсвітка впала б за межі масиву чи лишилась на видаленому пункті.
 */
export function paletteListHTML(actions, query, cursor) {
  const list = filterActions(actions, query);
  if (!list.length) return `<div class="pal-none">${esc(t("palNone"))}</div>`;
  const cur = Math.max(0, Math.min(cursor, list.length - 1));
  let out = "";
  let g = null;
  list.forEach((a, i) => {
    if (a.group !== g) { g = a.group; out += `<div class="pal-grp">${esc(t(g))}</div>`; }
    out += itemHTML(a, i, cur);
  });
  return out;
}

/**
 * Уся палітра: підкладка (`data-act="closeoverlay"`, той самий контракт, що
 * контекстне меню сторінки використовує своїм `Escape`/клік-повз — тут це
 * робить `app.js`), поле пошуку і список. `data-stop="1"` на самій коробці
 * — клік усередині НЕ мусить закривати підкладку (той самий прийом, що
 * `pal`/`keysheet` прототипу).
 */
export function paletteHTML(actions, query, cursor) {
  return `<div class="scrim" data-act="closeoverlay"><div class="pal" data-stop="1">
    <div class="pal-in">${ico("search", 18)}
      <input id="palq" placeholder="${esc(t("palPlaceholder"))}" value="${esc(query ?? "")}"
        autocomplete="off" spellcheck="false"></div>
    <div class="pal-list">${paletteListHTML(actions, query, cursor)}</div>
  </div></div>`;
}

/**
 * Довідка клавіш (`?`). Джерело — прототипний `renderKeys()`, але вже НЕ
 * дослівно, і межа тут коштувала релізу, тому записана повністю.
 *
 * Перша редакція прибрала звідси «Наступну/Попередню сторінку»
 * (`kNextPage`/`kPrevPage`, `⌥↓`/`⌥↑`), бо такого перемикача в бою немає, —
 * і присягалась у цьому ж докстрінгу: «документувати клавішу, якої нема,
 * означало б обманювати саме там, де інструмент обіцяє протилежне». Далі
 * вона документувала `⌥M`, `⌘\` і `⌘⏎`, у яких обробника не було НІ ДЕ.
 * Тобто знайшла одну пару відсутніх клавіш і пропустила три; ще п'ять
 * їхало колонкою `kbd` реєстру (шапка файла, п.3). Обіцянка була, перевірки
 * не було.
 *
 * Фактичний стан ЗАРАЗ — і кожен рядок нижче має живого власника:
 *   · `⌘K`, `?`, `⌥M`, `⌘\`, `Esc` — `app.js` (обробники `keydown` у секції
 *     ⌘K-палітри; `⌥M`/`⌘\` дописані 02.09.2026 саме через цей аудит);
 *   · `I` і `M` — `vendor/inspector.js` (`_onKey`). Вони працюють, поки
 *     фокус у РАМЦІ макета: інспектор слухає своє `window` і за межі iframe
 *     не виходить — те саме структурне обмеження, що вже описане в `app.js`
 *     («Драбинка Escape»);
 *   · `C`/`P`/`H` — коментатор, і вони лишаються ІНФОРМАЦІЙНИМ рядком під
 *     зіркою (`keysWidget`): «коментатор лишається окремим» — той самий
 *     принцип, що тримає перемикач аудиторії осторонь від смуги
 *     (`shell-bar.js`, коментар над `crumbIter`). Довідка ЗГАДУЄ його
 *     клавіші, не КЕРУЄ ними.
 *
 * `⌘⏎` (публікація) звідси прибрано СВІДОМО і не реалізовано: публікація
 * деплоїть на Vercel, одноклавішний деплой — погана ідея, власник його не
 * просив. Разом із рядком пішов і ключ `kPublish` зі словника: підпис без
 * рядка — той самий мертвий вантаж, лише в іншому файлі.
 *
 * ⛔ Не додавай тут рядка, поки не додав обробника: `tests/shell-palette.test.mjs`
 * вичитує прив'язки з `app.js` і зі двох вендорних обробників і звіряє з
 * КОЖНОЮ `kbd` цієї функції та реєстру. Це інваріант, а не список гліфів —
 * попередня перевірка стерегла рівно два символи (`⌥↓`/`⌥↑`) і тому лишалась
 * зеленою при вже порушеному інваріанті.
 */
export function keysHTML() {
  const row = (label, kbd) => `<dt>${esc(label)}</dt><dd><kbd>${esc(kbd)}</kbd></dd>`;
  return `<div class="scrim" data-act="closeoverlay"><div class="keysheet" data-stop="1">
    <h3>${esc(t("keysTitle"))}</h3>
    <div class="keysheet-grid">
      <div><h6>${esc(t("keysGeneral"))}</h6><dl>
        ${row(t("kPalette"), "⌘K")}${row(t("kKeys"), "?")}${row(t("kMode"), "⌥M")}
        ${row(t("kPanel"), "⌘\\")}${row(t("kClean"), "⇧⌘\\")}${row(t("kEsc"), "Esc")}</dl></div>
      <div><h6>${esc(t("keysLayout"))}</h6><dl>
        ${row(t("kInspector"), "I")}${row(`${t("inspCascade")} / ${t("inspRuler")}`, "M")}
        ${row(`${t("cmArm")} *`, "C")}${row(`${t("comments")} *`, "P")}
        ${row(`${t("cmHidePins")} *`, "H")}</dl></div>
    </div>
    <p class="cm-note" style="margin:16px 0 0">* ${esc(t("keysWidget"))}</p>
  </div></div>`;
}
