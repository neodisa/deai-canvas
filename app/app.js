// Design Canvas v2 — менеджер итераций макета.
// Открыл → текущий макет. «＋» фиксирует итерацию, зелёная точка = на превью.

import { initErrRing } from './err-ring.js';  // ПЕРШИЙ імпорт: кільце помилок ловить і збої завантаження наступних модулів
import { rowsLayout, worldBox } from './layout.js';
import { fitBox, focusBox, panBy, quantScale, step, wheelIntent, zoomAt } from './camera.js';
import {
  BAND_PAD_BOTTOM, BAND_PAD_TOP, BAND_PAD_X, FLOW_LEFT, FLOW_TOP, GAP, HEAD,
  ROW_TITLE_TOP,
} from './canvas-geom.js';
import { buildRows } from './rows-model.js';
import { flatten as flattenTree, pathOf, topIds, visibleIds, visibleRows, statsOf, stepRow, firstChildRow, rowRange, errKey } from './tree-model.js';
import { canMove } from './page-order.js';
import { readFlow, shotKey, shotVersion, stateQuery } from './flow-model.js';
import { flowLayout } from './flow-layout.js';
import { confirmHTML, confirmedId } from './inline-confirm.js';
import { ask, askChoice, askForm, askYesNo, formValues, makeFormCtl, tell, tellError } from './ask.js';
import { composeDeleteNote, deleteDialogModel, resolveDrop, shouldCommitDrop, shouldRefreshPanel, vanishedFolders, zoneOfHit, groupTargetIds, pageMenuItems, runSequential, treeBusyGate, treeTarget as pickTreeTarget } from './tree-actions.js';
import {
  CANVAS_PRESETS, CANVAS_W, MAX_W, MIN_W, PRESETS, activePreset, frameKey, parseWidth,
  readStored, splitFrameKey, storeValue,
} from './viewport.js';
import { LANG_KEY, getLang, readStoredLang, setLang, t } from './i18n.js';
import { reloadStep, shouldPollStamp } from './live-reload.js';
import { applyClean, syncFrame } from './clean-view.js';
import { SPRITE, ico } from './icons.js';
import { overviewComments } from './overview-comments.js';
import { esc } from './esc.js';
import { apiProblem } from './api-guard.js';
import { barModel } from './bar-model.js';
import { ISLAND_SHELL, applyBadge, badgeFor, islandParts } from './claude-status.js';
import { CAPTURE_DELAY_MS, captureToFigma, loadCapture } from './figma-capture.js';
import { barHTML } from './shell-bar.js';
import { cleanTitle, readHomeUi, relTime, taskKey } from './tasks-model.js';
import { effectiveTab, homeGridHTML, homeHTML, pruneFilters, thumbBrokenHTML } from './tasks-home.js';
import {
  FORM_POST_TIMEOUT_MS, TASK_VCS_POST_TIMEOUT_MS, checkPostTimeoutMs, VCS_BUSY_MAX_TRIES, VCS_BUSY_RETRY_MS, copyUrl, currentSpace, hasNotify, hasTeamComments, healTarget,
  cleanupWarning, commentsUnavailableCode, copyLinkRefused, hasVcs, isLegacyVcs, isPublished, isReadErrKey, needsWelcome, previewTarget, publishErr, publishReaction, pwUnreadable, pwView, readErrKey,
  remoteNoticeLines, remoteOpenUrl, remoteShareUrl, requestErrText, rovingIndex, safeLocalUrl, shouldRefreshHome, spaceChanged,
  spaceErrField, spaceErrKey, taskCreateClones, taskErrField, taskErrKey, taskErrShowsReason, taskFormError, vcsBrand, vcsFailKey, vcsLabel, vcsWebUrl,
} from './spaces-model.js';
import {
  parseTags, spaceDialogHTML, tagsFormHTML, taskFormHTML, welcomeHTML, wireSpaceDialog, wireTaskForm,
} from './space-dialogs.js';
import { createWizard } from './wizard.js';
import { panelHTML } from './shell-panel.js';
import { inspectHTML } from './shell-inspect.js';
import { alignWrites, buildModel } from './insp-model.js';
import {
  clearEdit, editCount, elementKey, emptyTune, fromPackage, markReady, packageJSON,
  setDs, setEdit, setNote,
} from './tuner-model.js';
import {
  filterActions, keysHTML, paletteActions, paletteHTML, paletteListHTML,
} from './shell-palette.js';
import { initPwa } from './pwa.js';
import { connPageHTML, drawerHTML, modName, roleTitle } from './connections-view.js';
import { TRUST_POST_TIMEOUT_MS, trustDialogHTML } from './trust-view.js';
import {
  RESTART_POLL_MS, UPDATE_POLL_MS, blockedHelp, bootBefore, codeOfBody, nextUpdateInfo, pillModel, waitRestart,
} from './update-model.js';
import { TABS_KEY, closeTab, pruneTabs, readTabs, tabsModel, upsertTab, writeTabs } from './tabs-model.js';
import { tabsHTML } from './tabs-view.js';
import { islandToolsHTML } from './island.js';
import { commentsPanelHTML } from './comments-view.js';
import { FILTERS, openCount } from './comments-model.js';
import { arrived, baseline, countNew, isNew, markSeen, newsByPage, readSeen, seenKey, teamOf, writeSeen } from './comment-news.js';
import { updateDialogHTML, updateNotesHTML } from './update-view.js';
import { createSession, errArg, errField, outcome, previewFromConflict, previewText, sentView, serverErrKey, shotState, validate } from './feedback-model.js';
import { feedbackDialogHTML } from './feedback-view.js';
import {
  disableConsequences, formFields, formPatch, initialForm, isDirty, missingRequired, refusalView, roleCardId, roleHolders,
  verdictText, writePayload,
} from './connections-model.js';

/* Спрайт мусить лежати в DOM ДО першого `<use>`: Safari не домальовує
   символи, які зʼявились у документі після посилання на них. Тому це
   найперша дія модуля, ще до читання мови й першого рендера. */
document.getElementById('sprite').innerHTML = SPRITE;

/* Мова читається тут, а не в `i18n.js`: модуль лишається чистим (ні DOM, ні
   сховище) за патерном `viewport.js` («сховище читає той, у кого воно є»).
   Найперша дія модуля, ДО першого рендера — інакше перший рендер уже пішов би
   типовою українською, а перемикання на збережену мову сталось би видимим
   миготінням підписів. `try/catch` — бо приватний режим і вимкнене сховище
   кидають на самому `getItem`. */
try { setLang(readStoredLang(localStorage.getItem(LANG_KEY))); } catch (e) {}

/* Застосунок «Deai Canvas» (PWA): реєстрація service worker і захоплення події
   встановлення для пункту ⌘K. ЛИШЕ локальний інструмент — оболонка превʼю цього
   модуля не імпортує. Тост `appinstalled` кличе `t()` у момент події, тож мова
   вже прочитана вище. */
const pwa = initPwa({ onInstalled: () => toast(t('pwaInstalled')) });

/* Розмір кадру мусить бути ЧИСЛОМ, і перевіряємо це ми: `manifest.json` лежить
   у теці ітерації, а тека приїжджає з GitLab із чужої машини — «там справді
   число» не наш інваріант. Непридатне значення ВИКИДАЄМО, а не екрануємо: воно
   однаково зіпсувало б і атрибут, і розкладку, а `esc()` лишив би у бейджі
   видимий сміттєвий рядок замість чесної відсутності числа.

   Живе НАГОРІ, спільним, бо шляхів до тих самих величин два: `cardEl` (запис із
   манифеста) і живий кадр автозʼємки `applyFrame` (подія прогресу). Другий
   зʼявився пізніше й писав `w`/`h` в innerHTML сирими — тобто мовчки скасував
   інваріант, записаний за сто рядків від нього. Дві копії перевірки розійшлися
   б так само тихо. */
const num = (v) => (Number.isFinite(v) && v > 0 ? v : null);

const bar = document.getElementById('bar');
const stage = document.getElementById('stage');
const frame = document.getElementById('frame');
const canvasEl = document.getElementById('canvas');
const world = document.getElementById('world');
/* Індикатор масштабу. У КАНВАСІ, а не у світі: він мусить стояти на місці й
   читатись на будь-якому зумі, а світ і їздить, і масштабується. */
const zoomEl = document.getElementById('cv-zoom');
/* Права панель інспектора (Task 5 Плану B) — контейнер уже в `index.html`
   (`hidden`), не створюється тут динамічно: на відміну від `#pages-panel`
   (Task 4) в неї немає стану «рейка», лише «є» чи «немає в розмітці зовсім»
   (`inspectHTML` віддає `''`), тож заводити гілку «створити при першому
   виклику» нема для чого — готовий вузол чекає в `index.html` заздалегідь. */
const inspEl = document.getElementById('insp-panel');
/* Панель «Коментарі» (0.26.0). Відкрита панель = увімкнений режим коментування (як у Figma). Знімок — від
   коментатора поточного виду (рамка в «Макеті», полотно в «Огляді»); сховища панель не читає (спека Б-Р4). */
const cmtEl = document.getElementById('cmt-panel');
let lastFrameSrc = null;   // адреса рамки на момент попереднього `applyMode`: змінилась — вибір/редагування панелі коментарів старого документа скидаються
let cmtTool = null;   // `CommentLayer.tool()` поточного виду для острівця (режими коментування, поправка 19)
let cmtDelAsk = null;   // id картки, де показано питання «Видалити назавжди?» (етап В)
let cmtOpen = false, cmtSnap = null, cmtSel = null, cmtQuery = '', cmtEditing = null, cmtDraft = null, frameCmtReady = false;
const cmtExpanded = { earlier: false, closed: false };
/** Фільтр панелі «Для Claude / Команда / Усі» (Б2) — памʼятається на вікно; типова — «Для Claude». */
let cmtFilter = (() => { try { const v = localStorage.getItem('dc-cmt-filter'); return FILTERS.includes(v) ? v : 'local'; } catch (e) { return 'local'; } })();
/** Причина, з якої командні недоступні (`L.store.teamDown`), або `null`. */
let cmtTeamDown = null;
/** «Нові від команди» цього відкриття панелі (поправка 13), id попереднього знімка (поправка 14), число нових для острівця. */
const cmtFresh = new Set();
let cmtPrevIds = null;
let cmtNewsN = 0;
let cmtNewsPages = {};
/** Ключ памʼяті адресата — спільний із рамкою (`HOST_ARG` у `serve.py`; пару приколює `test_comments_role`). */
const CMT_AUD_KEY = 'dc-cmt-aud';
/** колір піна коментатора (не CSS оболонки): пара з `DUAL_AUDIENCES_JS` у `serve.py` — приколює `test_comments_role`. */
const LOCAL_PIN_COLOR = '#7C6CF0';
const CMT_EVENTS = new Set(['ready', 'change', 'select', 'mode']);
let picked = null; // обрана ітерація (id); нормалізується в render() до останньої
let mode = 'single'; // 'single' — одна ітерація в iframe; 'canvas' — bird-view холст
// Вид холста «Огляд»: 'grid' — сітка кадрів, 'flow' — граф юзер-флоу з flow.json.
// Свідомо НЕ скидається при виході з «Огляду» в одну ітерацію й поверненні назад:
// `mode` теж не скидається (single↔canvas), і дизайнер, що дивився граф, чекає
// побачити граф і після короткого стрибка в макет, а не сітку заново.
let canvasView = 'grid';
let flowRaw = null;      // сирий flow.json обраної ітерації; null — нема файла/ще не завантажили
/* Чому графа немає, коли `flowRaw === null`. Саме ОКРЕМЕ поле, а не тост: без
   нього «файла немає» і «файл нечитний» виглядають однаково — а лікуються
   по-різному, і тост гасне за 3.2 секунди. */
let flowError = null;
/* Ітерація, чию зʼємку ми ведемо ЗАРАЗ, або `null`. Саме id, а не прапорець
   «йде/не йде»: прогрес у модулі один, а кнопка малюється для ОБРАНОЇ ітерації —
   тож булеве «йде» писало «Стоп 3/22» і на сусідній, яку дизайнер щойно вибрав у
   дропдауні. Натискання тоді клало в `autoShootStopped` НЕ ту ітерацію (вічна
   заборона автозʼємки тій, яку ніхто не зупиняв), а `POST /api/shoot-stop` не
   знаходив нічого — справжній прогін лишався без жодної кнопки, здатної його
   спинити.
   У МОДУЛІ, а не в DOM: `disabled` на кнопці — не замок, будь-який ре-рендер
   малює кнопку заново й воскрешає її (доведено ревʼю: другий Chromium на ту
   саму ітерацію). */
let shootingIt = null;
/* Ітерації, для яких автостарт вимкнено до наступної зміни штампів. Зупинена
   ВРУЧНУ зʼємка не сміє стартувати знову на першому ж поверненні в «Огляд» —
   інакше кнопку «Зупинити» не перемогти. Ключ — id ітерації, скидається у
   `freshen()`, коли перелік застарілих змінився. */
const autoShootOff = new Set();
/* Ітерації, де дизайнер зупинив зʼємку РУКАМИ. Окремо від `autoShootOff`, бо
   `freshen()` цей набір НЕ чистить: часткова зʼємка завжди міняє перелік
   застарілого, тож спільна позначка стиралась би тим самим `freshen()`, який
   біжить одразу після зупинки. Знімає лише явна воля — кнопка або зміна задачі. */
const autoShootStopped = new Set();
/** Підпис переліку застарілих на момент останньої відмови від автозʼємки. */
const autoShootSig = new Map();
/* Ітерація, чий автостарт ми ВІДКЛАЛИ через чужу зʼємку, що якраз ішла.
   `maybeAutoShoot` кличеться рівно у двох місцях — вхід у «Огляд» і зміна
   ітерації, — тож проста відмова означала «ніколи»: перемкнувся під час прогону
   й лишився з ітерацією без кадрів, яку вже ніхто не зніме. Одне значення, а не
   набір: відкласти можна тільки те, що дизайнер бачить зараз. */
let autoShootDeferred = null;
/* Кадри, уже підмінені з прогресу. Подія приходить у ПЕРЕЛІКУ (сервер віддає всі
   з початку прогону), тож без цього ми переставляли б `src` на кожному такті. */
let appliedFrames = new Set();
let progressTimer = null;
/** Останній знімок прогресу зʼємки або null. З нього живе підпис кнопки. */
let shootProgress = null;

/* ===== Смуга (Task 3 Плану B): стан, якого нема більш ніде ===== */
/** Який дропдаун смуги розкритий: `'iter'|'gl'|'pub'|'more'|'space'|null`. */
let openDd = null;
let iterDelAsk = false;   // дропдаун ітерації показує питання «Видалити Іт.N?» (етап В)
/* Відкритий екран «Задачі» (вхід — логотип у смузі). Прапорець ділять смуга
   (`barState().homeOpen` міняє її склад) і сам екран (`enterHome`/`leaveHome`
   нижче ставлять ще й клас `home-open` на `body`). */
let homeOpen = false;
/* Сторінка оверлею `#tasks-home`: `tasks` — «Задачі» (список задач / привітання), `conn` — «Підключення» (етап 3a),
   `wiz` — майстер нового простору (етап 3b). Один оверлей на всі екрани поза задачею: вхід, вихід, чистий перегляд і
   палітра в стані `homeOpen` — спільні. */
let homePage = 'tasks';
/* Стан сторінки «Підключення»: простір, чий список показано (знімок на момент запиту — кожен запис іде САМЕ туди),
   записи `GET /api/modules` (`null` — вантажиться), `notes` — примітки своїх модулів простору (3c, `[{folder, code}]`),
   збій читання і дії в польоті (id → 'check'|'disable'|'save'). `seq` відкидає відповіді, що прийшли після виходу
   зі сторінки чи після новішого запиту. */
const connState = { spaceId: null, list: null, notes: [], failed: null, busy: new Map(), seq: 0 };
/* Свіжий вхід на сторінку: після першого списку фокус — на першу кнопку першої картки. */
let connFocusPending = false;
/* Роль, до картки якої веде вхід («Налаштувати…» синку → `vcs`): після першого списку фокус іде на картку її модуля, а не першу.
   Порожньо — як завжди. Знімається разом із `connFocusPending` (`loadConn`) і чиститься кожним входом без ролі (`enterConnections`). */
let connFocusRole = '';
/* Лічильник входів на «Підключення»: `enterConnections` чекає перелік просторів, і за цей час людина могла піти (`enterHome` із явною
   сторінкою — логотип, майстер; `leaveHome` — відкрила задачу) або клікнути вдруге. Оголошено ТУТ з тієї самої причини, що `cnDrawer`:
   `enterHome` читає його з першого `render()`. Зміну задачі чи простору рахує `taskSwitchGen`. */
let connEntrySeq = 0;
/* Бічна панель «Підключення» (Task 7): `null` — закрита. Оголошено ТУТ, серед стану модуля, а не біля функцій панелі:
   `enterHome` (його кличе вже перший `render()`) читає її через `closeCnDrawer`, і `let` нижче за місцем виклику дав би
   TDZ-помилку на старті. */
let cnDrawer = null;   // {id, entry, mode: 'enable'|'edit', fields, init, form, busy: 'save'|'check'|false, result, errors, spaceId, opener}
/* «В Figma» (T-41): захоплення вже йде. Живе ТУТ, а не в документі макета, бо
   саме смуга показує «Копіюю…» і не пускає другий клік. Оголошено біля решти
   стану модуля, а не біля `copyToFigma`: `barState()` читає його на першому ж
   рендері, і `let` нижче за текстом дав би ReferenceError (TDZ). */
let figmaBusy = false;
/* Тиша Teams на канал задачі (батч 1.52): `null` — ще не питали, `{error}` —
   база недосяжна, інакше `{muted, muted_by, …}`. Питаємо при відкритті
   дропдауна публікації, а не на кожен render: це мережа до Supabase. */
let teamsMute = null;
/* Останній УСПІШНО завантажений `/api/task`/`/api/tasks`. `render()` пише сюди
   після кожного вдалого фетчу; `barState()` читає ЦІ змінні, а не локальні
   `task`/`taskList` `render()`, бо `paintBar()` (відкрити/закрити дропдаун)
   мусить перемалювати смугу БЕЗ мережевого запиту й БЕЗ перезавантаження
   iframe — а саме це зробив би повний `render()` (`applyMode` ставить
   `frame.src` на кожному виклику, і навіть той самий рядок перезавантажує
   документ, як пояснено в `setViewport` вище). */
let curTask = null;
let curTaskList = null;
/* ЄДИНЕ джерело «яка задача поточна зараз» для екрана «Задачі». `curTaskList`
   оновлює лише `render()`, а `homeData.current` — лише відповідь екрана, і
   екран при відкритті малює СТАРІ дані, поки нова відповідь у дорозі (запит
   команди може висіти ~3 с). Порівняння з будь-яким одним із них даватиме
   «уже поточна» на задачі, яку щойно покинули. Тому: пишемо тут на кожну
   відповідь `/api/tasks`, на відповідь екрана й на кожне успішне переключення. */
let currentTaskId = null;
/* Лічильник успішних переключень: відповідь екрана, що вилетіла ДО переключення,
   не сміє перезаписати `currentTaskId` старим значенням. */
let taskSwitchGen = 0;
/** Прапорець, який ставить `catch` у `render()` — стереже `errbar` під зонами. */
let tasksErr = false;
/* Причина помилки смуги, коли вона точніша за типову (`tasksErrPort`).
   Окремо від `tasksErr`: факт помилки і її причина — різні величини. */
let tasksErrKey = null;

/* ===== Простори (Deai 1.0, етап 1): стан, якого нема більш ніде ===== */
/* Остання відповідь `/api/spaces`: `{current, spaces:[{id,name,color,path,legacy,
   tasks,available}]}`; `{off:true,…}` — шар просторів вимкнено; `null` —
   ще не питали або реєстр не читається. Живе ТУТ, а не в `curTask.space`, бо потрібна
   й тоді, коли задачі нема зовсім (порожній простір, привітання, недоступний файл): без
   неї смузі не було б з чого намалювати фішку, а «просторів нема» не відрізнялось би
   від «ще не питали». Оновлюється при відкритті дропдауна й палітри, на екрані «Задачі»
   та після кожної дії над просторами — не на кожен `render()`. */
let spacesResp = null;
/* Лічильник запитів: відповідь, що вилетіла ДО новішого запиту, не перезаписує його. */
let spacesSeq = 0;
/* Дропдаун просторів був відкритий на ПОПЕРЕДНЬОМУ малюванні: відрізняє «щойно
   відкрили» (фокус на поточний рядок) від «перемалювали відкритий» (фокус лишається
   на тому рядку, де був). */
let spaceDdWasOpen = false;

/** Поточний простір (`{id, name, color, capabilities, …}`) або `null`: шар вимкнено,
 *  просторів нема. Джерело — задача, що відкрита (`curTask.space`), інакше реєстр. */
const spaceNow = () => curTask?.space ?? currentSpace(spacesResp);
/** Сповіщень Teams нема: роль `notify` (`hasNotify`: ключ `capabilities.notify`, без нього — не знаємо → не крадемо:
 *  невідомість красти в людини Teams не має, так само, як `bar-model.js`). Тиша там не опитується взагалі
 *  (публікація йде на `hasPublish`, командний канал коментарів — на `noTeamComments`, синк із git — на `noVcs`, нижче:
 *  їх дають ролі модулів). Просторів на машині немає зовсім (привітання) — теж без сповіщень: задач нема, і опитувати
 *  нікого (`loadTeamsMute` без цього питав би порожнечу). Простір із модулем `notify` Teams має,
 *  а з вимкненою роллю — ні (сервер там 409 `notify-off`). */
const noNotify = () => needsWelcome(spacesResp) || !hasNotify(spaceNow());
/** Синку з git нема: роль `vcs` (`hasVcs`: ключ `capabilities.vcs`, без нього — не знаємо → не крадемо). Це НЕ `noNotify`:
 *  Teams — на ролі `notify`, а простір із модулем `git-sync` має синк. Просторів нема зовсім
 *  (привітання) — теж без синку: `refreshGitlab` питав би порожнечу. */
const noVcs = () => needsWelcome(spacesResp) || !hasVcs(spaceNow());
/** Командного каналу коментарів нема: вкладки «Команда» й аудиторії `project` — теж. Це НЕ `noNotify`: канал дає
 *  роль `comments` (зашитий ЛІГА або модуль, `capabilities.comments`), і простір без інтеграцій, але з модулем
 *  коментарів його має. Просторів нема зовсім (привітання) — теж без каналу: задач і сторінок нема. */
const noTeamComments = () => needsWelcome(spacesResp) || !hasTeamComments(spaceNow());

/* Ширина рамки макета в робочому вигляді: число пікселів або `null` — вільна
   ширина вікна («Десктоп»). ОДНА величина на весь стан: який сегмент підсвічений,
   виводиться з неї (`activePreset`), а не тримається другим прапорцем — інакше
   «вибрав планшет» і «набрав 768 руками» стали б двома станами, які колись
   розійдуться. Персист у браузері: вибрав мобайл — вертаєшся
   в мобайл, бо адаптив дивляться серіями, а не по одному разу. */
let vpWidth = (() => { try { return readStored(localStorage.getItem('dc-viewport')); } catch (e) { return null; } })();

/* Ширина, у якій зараз дивимось «Огляд». Окремий ключ від робочого виду
   (`dc-viewport`) свідомо: там «Десктоп» = вільна ширина вікна, тут = 1280, і
   мовчазне перенесення означало б, що вибір в одному місці запускає браузерний
   прогін в іншому. */
let canvasW = (() => {
  try {
    const stored = readStored(localStorage.getItem('dc-canvas-viewport'));
    return CANVAS_PRESETS.some((p) => p.w === stored) ? stored : CANVAS_W;
  } catch (e) { return CANVAS_W; }
})();

/** Ширина картки на полотні. Дев'ять місць читають саме її, а не константу. */
const cardW = () => canvasW;

let pickedPage = null;   // обрана сторінка в обраній ітерації
/* Стан ЦІЄЇ сторінки: `{ключ: значення}` з вузла флоу або `null` — звичайний
   вигляд. Живе окремо від `pickedPage`, бо це не інша сторінка, а той самий
   екран з іншим параметром URL. Мусить скидатись усюди, де змінюється
   `pickedPage`: інакше «нічого не знайдено» прилипає до наступної відкритої
   сторінки, і дизайнер править не той екран, який бачить. */
let pickedState = null;
let panelPages = [];     // дерево сторінок обраної ітерації
let panelRev = '';       // відбиток pages.json, який бачить панель (409 → перечитати)
/* Для якої ітерації завантажено `panelPages`: порівнювати теки з деревом ІНШОЇ
   ітерації означало б тривогу на кожному перемиканні (fb-01102026-71980b). */
let panelPagesIt = null;
/* Дерево до чужого перезапису: `{ it, prev, folders }` або null. Живе, поки
   людина не відновила / не закрила плашку / не перейшла в іншу ітерацію.
   ⛔ Повторний перезапис НЕ підміняє `prev`: відновлювати треба організацію
   дизайнера, а не проміжний стан скрипта. */
let treeLost = null;
/* Оголошено ТУТ, біля решти стану модуля, а не біля опитувань нижче: `barState()`
   і адаптер панелі читають їх на першому ж рендері, і `let` нижче за текстом дав
   би ReferenceError (TDZ) — та сама пастка, що описана біля `figmaBusy`. */
/** Сторінки, змінені щойно (з `/api/it-stamp`). */
let recentPages = new Set();
/** Статус Клода з `/api/claude-status` або null (серцебиття згасло). */
let claudeView = null;
/** Чистий перегляд макета: оболонка й піни сховані (fb-01102026-7f7b6d). */
let cleanView = false;
let pagesError = null;
let shotManifest = { shots: {}, checkedAt: null };  // знімки обраної ітерації
/* Відповідь ОСТАННЬОЇ серверної перевірки свіжості (`freshen`): `{it, stale,
   problems}`, де `stale` — перелік застарілих КЛЮЧІВ КАДРІВ. Разом з ітерацією, а
   не окремим прапорцем: інакше цей стан довелось би скидати руками в кожному
   місці, де міняється `picked`, а `freshen()` кличуть ДО `render()` — скидання в
   `loadPages` зʼїло б щойно отриману відповідь. `null` — перевірка ще не бігала. */
let lastCheck = null;
// Згорнута панель = рейка 36px, а не «немає панелі», тому ключ новий: старий
// dc-panel-hidden значив інше, і тягнути його значення означало б показати
// рейку тому, хто колись просто сховав панель.
let panelCollapsed = (() => { try { return localStorage.getItem('dc-panel-collapsed') === '1'; } catch (e) { return false; } })();
/* Чи розгорнута секція «Кадри». Типове значення — ЗГОРНУТО: коли все свіже,
   блок каже це одним рядком, а керування зʼємкою з'являється кліком по
   ньому. Зберігаємо саме «розгорнуто», а не «згорнуто», з тієї ж причини,
   що й `expandedPages` нижче: тоді типовий стан («тихо») виходить сам собою
   і для тих, хто інструмент ще не відкривав.
   Прапорець дає право лише РОЗГОРНУТИ тиху секцію — сховати застаріле,
   прогін чи побитий манифест він не може (`shotsHTML` у `shell-panel.js`). */
let shotsOpen = (() => { try { return localStorage.getItem('dc-shots-open') === '1'; } catch (e) { return false; } })();

/* Які батьківські сторінки РОЗГОРНУТІ. Зберігаємо саме розгорнуті, а не
   згорнуті: тоді «за замовчуванням усе згорнуте» виходить само собою — і для
   задач, яких ще ніхто не відкривав, і для сторінок, доданих у розкладку
   пізніше. Зі списком «згорнутих» кожна нова сторінка приїжджала б розкритою,
   тобто дефолт ламався б від самого лише додавання екрана. */
let expandedPages = (() => {
  try { return new Set(JSON.parse(localStorage.getItem('dc-pages-expanded') || '[]')); }
  catch (e) { return new Set(); }
})();

/* Множинний вибір панелі (⌘/Ctrl+клік, Shift+клік). ОКРЕМО від `pickedPage`:
   той — сторінка, відкрита в рамці (мусить бути відкриваною), а вибір —
   те, над чим діятимуть «у теку», перетягування й меню (теки теж). */
let panelSel = new Set();
let panelAnchor = null;        // опора Shift-діапазону й roving-фокуса клавіатури
let panelFocus = null;         // «Показати лише цю гілку»; не зберігається між перезавантаженнями
let panelFilter = '';
/* Рядок, на якому стоїть КЛАВІАТУРНИЙ фокус: перемальовка дерева знищує вузол
   рядка разом із фокусом, і після неї його треба повернути. Скидається, щойно
   фокус пішов з дерева (мишею, у фільтр) — інакше перемальовка крала б його. */
let panelKbFocus = null;
/* Триває IME-композиція у фільтрі: до `compositionend` значення не застосовуємо. */
let panelComposing = false;

/* Шеврони каретки дерева (Task 4 Плану B) тепер зі спрайта — `ico('chevdown'
   | 'chevright')`, той самий набір, що вже малює каретку крошки в шапці
   (`shell-bar.js`). Хардкод SVG тут більше не потрібен: два літерали нижче
   були єдиним місцем, що його вживало. */

/**
 * Покласти обрану ширину у стиль. `--cv-vpw` на `body`, звідки її бере
 * `body.vp-fixed .cv-frame`.
 *
 * На десктопі змінну ВИДАЛЯЄМО, а не лишаємо старе значення під знятим класом:
 * значення, що лежить без діла, — це друге джерело правди, яке одного дня
 * розійдеться з класом, і рамка поїде в ширину, якої ніхто не вибирав.
 */
function applyViewport() {
  document.body.classList.toggle('vp-fixed', vpWidth !== null);
  if (vpWidth === null) document.body.style.removeProperty('--cv-vpw');
  else document.body.style.setProperty('--cv-vpw', `${vpWidth}px`);
}

/** Підсвітка сегментів і число в полі — без перерендеру смуги (див. `setViewport`).
 *  Лише РОБОЧИЙ вигляд: `setCanvasViewport` (полотно) сам кличе повний
 *  `render()`, у ці елементи взагалі не заглядає. Патчимо `aria-pressed`, а не
 *  клас `.on` — нова смуга підсвічує пресет саме атрибутом
 *  (`.seg button[aria-pressed=true]` у styles.css). */
function syncViewportBar() {
  const cur = activePreset(vpWidth);
  bar.querySelectorAll('[data-act="vp"]').forEach((b) => {
    b.setAttribute('aria-pressed', String(b.dataset.val === cur));
  });
  const inp = bar.querySelector('[data-act="vpw"]');
  // поле не перезаписуємо, поки в ньому набирають: інакше кожен символ затирався б
  if (inp && document.activeElement !== inp) inp.value = vpWidth === null ? '' : String(vpWidth);
}

/**
 * Обрати ширину. `w === null` — десктоп.
 *
 * ⛔ Свідомо БЕЗ `render()`. `applyMode` на кожному рендері присвоює `frame.src`,
 * а присвоєння iframe навіть того самого рядка перезавантажує документ — тобто
 * повний рендер тут скидав би прокрутку макета, відкриті меню, набраний у формі
 * текст і піни, які комментатор щойно розставив. Ширину міняють саме щоб
 * подивитись на ТОЙ САМИЙ екран іншим пристроєм, отже перезавантаження знищує
 * рівно те, за чим прийшли. Тому стан кладеться у стиль, а смуга правиться на місці.
 */
function setViewport(w) {
  vpWidth = w;
  try { localStorage.setItem('dc-viewport', storeValue(w)); } catch (e) {}
  applyViewport();
  syncViewportBar();
}

/**
 * Перемкнути ширину полотна. Кадри цієї ширини можуть бути ще не зняті — тоді
 * вони застарілі за побудовою, і автозʼємка (T-34) забере їх сама, з тим самим
 * лічильником і зупинкою. Окремої кнопки «зняти в цьому розмірі» не треба.
 *
 * ⛔ Тут, на відміну від `setViewport`, повний `render()` ОБОВʼЯЗКОВИЙ, і ціна
 * протилежна: у робочому виді він перезавантажив би iframe і зніс би те, за чим
 * прийшли, а в «Огляді» iframe немає взагалі — там від ширини залежать і
 * розкладка, і КЛЮЧІ КАДРІВ (`frameKey`), тобто `src` кожного знімка. Правка
 * «на місці», як у смузі робочого виду, лишила б на полотні кадри старої ширини.
 */
async function setCanvasViewport(w) {
  if (w === canvasW) return;
  canvasW = w;
  try { localStorage.setItem('dc-canvas-viewport', storeValue(w)); } catch (e) {}
  camWorld = null;              // інша ширина — інший світ, камеру вписуємо заново
  await freshen();
  render();
  maybeAutoShoot();
}

function saveExpanded() {
  try { localStorage.setItem('dc-pages-expanded', JSON.stringify([...expandedPages])); } catch (e) {}
}

/** Розгорнути гілку, у якій лежить сторінка, — інакше вибір був би невидимий. */
function revealPage(id) {
  // увесь ланцюжок предків: вибір на глибині інакше невидимий
  const line = pathOf(panelPages, id).slice(0, -1);
  if (!line.length) return;
  for (const a of line) expandedPages.add(a.id);
  saveExpanded();
}

/** Плаский обхід УСІХ рівнів: [{page, parent, depth, kind}] — `tree-model.flatten`. */
function flattenPages(pages) {
  return flattenTree(pages);
}

/** Плашка «дерево перезаписали ззовні» з кнопкою «Відновити» (fb-01102026-71980b). */
function showTreeLost() {
  notice('tree-lost', t('treeLost', treeLost.folders.map((f) => `«${f.name}»`).join(', ')),
    [{ act: 'restore', label: t('treeRestore'), run: restoreTree }],
    () => { treeLost = null; });
}
/* Через `treePost`: той самий замок, rev і 409 → «Дерево змінилось», що й у
   решти дій. Плашка лишається, поки сервер не підтвердив відновлення. */
async function restoreTree() {
  const lost = treeLost;
  if (!lost || picked !== lost.it) return;
  const r = await treePost('/api/page-restore', { prev: lost.prev }, { it: lost.it });
  if (!r || picked !== lost.it) return;
  treeLost = null;
  dropNotice('tree-lost');
  await loadPages(); render();
  toast(t('treeRestored', (r.restored || []).length));
}

async function loadPages() {
  if (!picked) { panelPages = []; panelRev = ''; panelPagesIt = null; pagesError = null; return; }
  const it = picked;                  // фіксуємо ДО await: два завантаження можуть дійти не в порядку
  try {
    const r = await api(`/api/iteration-pages?it=${encodeURIComponent(it)}`);
    if (picked !== it) return;        // відповідь про іншу ітерацію — не пишемо її сторінки й rev
    const lost = vanishedFolders({ prev: panelPages, next: r.pages || [], prevRev: panelRev, nextRev: r.rev || '',
      prevIt: panelPagesIt, it });
    if (treeLost && treeLost.it !== it) { treeLost = null; dropNotice('tree-lost'); }
    if (lost.length && !treeLost) treeLost = { it, prev: structuredClone(panelPages), folders: lost };
    panelPages = r.pages || [];
    panelRev = r.rev || '';
    panelPagesIt = it;
    pagesError = null;
    if (treeLost) showTreeLost();
    /* Вибір і фокус гілки не переживають зникнення вузлів (Claude міг
       прибрати/перенести їх, поки панель була відкрита). */
    const alive = new Set(flattenPages(panelPages).map((f) => f.page.id));
    panelSel = new Set([...panelSel].filter((id) => alive.has(id)));
    if (panelAnchor && !alive.has(panelAnchor)) panelAnchor = null;
    if (panelFocus && !alive.has(panelFocus)) panelFocus = null;
  } catch (e) {
    if (picked !== it) return;
    /* Причину зберігаємо, як це вже роблять манифест кадрів і граф нижче.
       Порожній `panelPages` виглядає ТОЧНО як «сторінок ще немає», хоч насправді
       сервер упав чи рестартує, — і дизайнер іде шукати пропажу в макеті.
       `pickedPage` НЕ чіпаємо: його скидання — реакція на «сторінки змінились»,
       а не на «сервер мовчить», інакше збій ще й перекидав би на іншу сторінку. */
    panelPages = [];
    panelRev = '';
    pagesError = e.message;
  }
  /* Нормалізацію `pickedPage` пропускаємо ЛИШЕ при `pagesError` — а не ВЕСЬ
     `loadPages()` раннім `return`, як було до ревʼю. Той ранній `return`
     виглядав безпечним («старі дані чесніші за вигадані порожні»), але
     тягнув за собою РЕГРЕСІЮ: він же пропускав запити `/api/shots` і
     `/api/flow` нижче, які від `panelPages` НЕ залежать і мусять лишатись
     синхронними з `picked`. Наслідок — транзиентний збій ЦЬОГО ендпойнта (сервер
     рестартує, файли на диску цілі) лишав `flowRaw` СТАРИМ; `buildCanvas`
     викликається безумовно, `readFlow` порівнює його вузли з ПОРОЖНІМ
     `panelPages` і позначає КОЖЕН як «немає сторінки», а `paintFlowProblems`
     малює цей вигаданий перелом на полотні — хоча `flow.json` цілий, просто не
     довантажився сусідній запит. Панель (нижче, `pp-err`) казала правду, а
     полотно поруч брехало. Від цього рятує `effView()` (гейт `!pagesError`),
     а тут лишається звужений скіп — саме ТОЙ шматок, що без дерева сторінок
     справді безглуздий.

     ⚠️ Сам факт, що `/api/shots` і `/api/flow` тут виконуються БЕЗУМОВНО, живим
     тестом окремо НЕ доведений: мутація «повернути ранній `return`» лишає
     живий прогін зеленим — поки `pagesError` стоїть, `effView()` однаково
     ховає різницю (граф не малюється в обох версіях), а щойно збій минає,
     `pagesError` уже `null`, і стара, і нова гілка виконують один і той самий
     код. Спостережного вікна для мутації просто нема. Цінність рядка — не в
     тому, що ЦЕЙ живий тест його ловить, а в тому, що `shotManifest`/`flowRaw`
     лишаються синхронними з `picked`, а не з тим, чи впав СУСІДНІЙ запит.
     Сказано вголос, щоб не рахувати доведеним те, що не перевірено. */
  if (!pagesError) {
    const flatAll = flattenPages(panelPages);
    const open = flatAll.filter((f) => f.kind !== 'folder');
    /* Розкриваємо гілку обраної сторінки ТУТ, а не в renderPanel: у рендері це
       означало б «розкривати на кожному перемальовуванні», і каретка переставала
       працювати, поки стоїш на дочірній сторінці — згорнув, а наступний рендер
       негайно розгорнув назад. Каретка виглядала зламаною. */
    if (pickedPage) revealPage(pickedPage);
    if (!open.some((f) => f.page.id === pickedPage)) {
      pickedPage = open.length ? open[0].page.id : null;
      /* Сторінку підмінили — стан старої до нової не липне. Це ДРУГИЙ замок, і він
         не декоративний: `#task-sel` і видалення ітерації скидають `picked`, а
         `pickedPage` лишають — тобто стан із чужої задачі доїхав би сюди, і рядок
         вище був би єдиним, хто це помітив. Живим тестом НЕ покритий (мутація
         лишає весь живий прогін зеленим): фікстура має одну задачу, а другий шлях
         вимагає видалити ітерацію, тобто зруйнувати спільну фікстуру для всіх
         наступних перевірок. Сказано вголос, щоб не рахувати його доведеним.

         `pagesError` вище — ТОЙ САМИЙ клас ризику з ІНШИМ тригером: поки він
         триває, цей блок узагалі не виконується, і `pickedPage`/`pickedState`
         лишаються тими, що були ДО збою. Відкриттю сторінки це не шкодить —
         серверний `_pick_page` (у `/commented`) сам шукає `pickedPage` в межах
         поточних `task+it` і падає на першу відкривану, якщо такої нема. Вузький
         залишковий ризик той самий: якщо сервер підставить ІНШУ сторінку, ніж
         та, на яку вказував застарілий `pickedPage`, `pickedState` (стан вузла
         флоу в URL кадру) може лишитись від старої сторінки поверх нової. Не
         лікуємо тут так само — лише називаємо вголос. */
      pickedState = null;
    }
  }
  // Манифест знімків — джерело розмірів кадру, тому канвасу не треба міряти iframe
  try {
    shotManifest = await api(`/api/shots?it=${encodeURIComponent(picked)}`);
  } catch (e) {
    /* Ковтати не можна: порожній манифест виглядає ТОЧНО як «кадрів ще немає», і
       кнопка бадьоро каже «Зняти кадри» там, де насправді не читається файл.
       serve.py спеціально НЕ ковтає PermissionError, щоб биті права були гучними —
       не гасимо цю гучність тут. */
    shotManifest = { shots: {}, checkedAt: null, error: e.message };
  }
  /* Той самий рядок думки, що й з манифестом кадрів вище: `GET /api/flow` ніколи
     не 404-ить — немає файла означає `{flow: null}`, а побитий файл лишається
     ЧУТНИМ через `error`, не мовчазним `null`.

     Причина йде в ПОЛЕ, а не в тост (`paintFlowProblems` показує її на полотні):
     тост живе 3.2 секунди, а після нього «файла немає», «файл є, але вузли не
     вцілили» і «файл нечитний» виглядають однаково — при тому, що перший стан
     нормальний, другий править автор графа, а третій — диск. */
  try {
    const r = await api(`/api/flow?it=${encodeURIComponent(picked)}`);
    flowRaw = r.flow;
    flowError = r.error || null;
  } catch (e) {
    // Сюди доходить лише збій самого запиту (сервер упав, 500): тіло з `error`
    // приходить статусом 200 і лежить у гілці вище.
    flowRaw = null;
    flowError = t('errFlowLoadFailed', e.message);
  }
}

/**
 * Вид «Огляду», яким його НАМАЛЮЄМО. Без `flow.json` граф малювати нема з чого,
 * і липкий `canvasView === 'flow'` мусить відступити: інакше кнопка неактивна (бо
 * файла немає), а холст лишився в графі з одних «не у флоу» — і вийти з нього
 * нічим.
 *
 * `!pagesError` — та сама відступна причина з ІНШОГО боку: `buildFlowView`
 * звіряє вузли графа зі справжнім переліком сторінок (`panelPages`), а поки
 * `pagesError` стоїть, той перелік ПОРОЖНІЙ не тому, що сторінки зникли, а
 * тому, що впав сусідній запит. Без цього гейту `readFlow` позначив би КОЖЕН
 * вузол цілого `flow.json` як «немає сторінки», і `paintFlowProblems` намалював
 * би на полотні гучний перелік ФЕЙКОВИХ проблем — та сама брехня, від якої
 * рятує задача 3, тільки голосніша за порожню сітку (K4 уже показує правду в
 * панелі; тут та сама правда мусить дійти й до полотна). Саме `canvasView` при
 * цьому не чіпаємо: перемикання ітерації туди-назад не сміє забувати вибір
 * дизайнера.
 */
const effView = () => (canvasView === 'flow' && flowRaw && !pagesError ? 'flow' : 'grid');

/**
 * Перезважити штампи кадрів обраної ітерації перед показом «Огляду».
 *
 * `stale` у манифесті — слепок ОСТАННЬОГО прогону зʼємки, а не стан «зараз»:
 * `GET /api/shots` лише читає файл, а рахувати штампи в serve.py заборонено
 * (єдина реалізація хешу — `bin/shots-stamp.mjs`). Без цього виклику канвас
 * показує застарілий кадр БЕЗ бейджа, а лічильник «Перезняти» бреше нулем.
 * Виміряно: 0.11с на 8 сторінках — чекати дешево. Саме ЧЕКАТИ, а не малювати
 * наперед: пізній ре-рендер скинув би `userMoved` і відібрав з рук почату панораму.
 *
 * Функція окрема, бо шляхів у «Огляд» ДВА: кнопка смуги і зміна ітерації в
 * дропдауні панелі (вона в «Огляді» видима). Ревʼю показало: коли перевірка
 * висіла тільки на кнопці, перемикання ітерації на холсті обходило її цілком —
 * застарілий кадр без бейджа й лічильник у нулі.
 */
async function freshen() {
  if (!picked) return;   // без ітерації serve.py дає NAME_RE.match(None) → 500 у лог
  // Ітерацію фіксуємо ДО await: дизайнер може перемкнутись, поки триває перевірка,
  // і тоді відповідь стосувалася б не тієї ітерації, під якою ми її запишемо.
  const it = picked;
  /* `vp` — ширина, СВІЖІСТЬ якої рахуємо, і фіксуємо її тут, поруч з ітерацією й
     з тієї ж причини: перемикання ширини під час перевірки інакше дало б перелік
     застарілого про один набір кадрів під ключем іншого. На штампи в манифесті
     вона не впливає (їх сервер рахує по ВСІХ ширинах — інакше зʼємка мобайла
     стерла б метадані десктопних кадрів); звужується лише `stale`, тобто число
     на кнопці й цілі зʼємки. */
  const res = await post('/api/shoot', { it, check: true, vp: canvasW })
    .catch((e) => ({ ok: false, error: e.message }));
  if (!res || res.ok === false) {
    // stderr теж: коли дитина падає ДО звіту (класика — не встановлений chromium),
    // причина приходить саме там, а `error` порожній.
    toast(res?.error || res?.stderr || t('toastFreshnessCheckFailed'));
    /* Стару відповідь тримати не можна: вона про стан ДО правок, і кнопка
       показувала б число, якого ніхто не перевіряв. Краще без числа. */
    if (lastCheck && lastCheck.it === it) lastCheck = null;
    return;
  }
  /* Запамʼятовуємо ПЕРЕЛІК КЛЮЧІВ, а не рахуємо своєю формулою: серверний `wanted`
     бере і кадри стану (`сторінка~хеш`), яких у переліку сторінок панелі немає
     ніколи. Тоді число на кнопці дорівнює тому, що зробить натискання, ЗА
     ВИЗНАЧЕННЯМ, а не за формулою-двійником, яка розійшлася з серверною, щойно
     зʼявився другий вид цілі зʼємки. `problems` звідси теж не викидаємо — вони
     єдиний слід описки в `flow.json` для того, хто дивиться на сітку. */
  const report = res.report || {};
  lastCheck = { it,
                stale: Array.isArray(report.stale) ? report.stale : [],
                problems: Array.isArray(report.problems) ? report.problems : [],
                /* `report.nodes` — рахунок ВСІХ кадрів цієї ширини (`runCheck`,
                   `bin/shoot.mjs`), не лише застарілих. Панель шарів (Task 4)
                   бере звідси «M» у «N з M застаріли»/«N кадрів, усі свіжі» —
                   те саме джерело правди, що й `stale` рядком вище, а не друга
                   формула по сторінках, яка вже раз розійшлася (див. коментар
                   над цим блоком). `num()` — той самий захист від сирого
                   значення з чужого процесу, що вгорі файла. */
                total: num(report.nodes) };
  /* Перелік застарілих змінився — значить макет правили, і попередня відмова
     від автозʼємки стосувалась іншої роботи. Блок знімаємо. */
  const sig = lastCheck.stale.slice().sort().join('|');
  if (autoShootSig.get(it) !== sig) { autoShootOff.delete(it); autoShootSig.set(it, sig); }
}

/** Відповідь перевірки свіжості, якщо вона про ОБРАНУ зараз ітерацію. */
const checkOf = () => (lastCheck && lastCheck.it === picked ? lastCheck : null);

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    /* Відмови дерева приходять JSON-ом `{ok:false, error, code}` (serve
       `_tree_error`): код — щоб показати причину мовою глядача, статус — щоб
       відрізнити «дерево змінилось» (409) від «так не можна» (400). */
    const txt = await res.text();
    let msg = txt;
    let code;
    try { const j = JSON.parse(txt); if (j && typeof j.error === 'string') { msg = j.error; code = j.code; } }
    catch (e) { /* не JSON — лишаємо сирий текст, як було */ }
    /* `statusText` і початок тіла — для відмов, у яких причина НЕ в `code`: `send_error(400, …)` кладе
       текст у рядок статусу й у розмітку, а `message` ріже розмітку по 200 знаків ДО причини
       (`publishErr`, `spaces-model.js`, розрізняє так «жодної ітерації не позначено» і `bad payload`). */
    throw Object.assign(new Error(msg.slice(0, 200) || String(res.status)),
      { status: res.status, code, statusText: res.statusText, body: txt.slice(0, 1000) });
  }
  /* ТИП ВІДПОВІДІ — ДО розбору. Без цього рядка чужий процес на нашому порту
     (у власника двічі: `python -m http.server`, IPv6-сокет виграє в
     `localhost`) віддає 404-HTML із кодом 200, `res.json()` падає на розборі,
     і причина складається так, ніби не читаються НАШІ файли. Ключ їде на
     помилці властивістю: смуга помилки називає причину точно, а не типовим
     «tasks.json не читається». */
  const key = apiProblem({ ok: res.ok, status: res.status,
                           contentType: res.headers.get('content-type') });
  if (key) throw Object.assign(new Error(t(key)), { key });
  return res.json();
}
const post = (path, body) => api(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});

/**
 * Запит діалогу просторів і «Нової задачі» — зі СТЕЛЕЮ часу (`FORM_POST_TIMEOUT_MS`). Поки форма
 * чекає відповіді, вона «зайнята»: Esc і «Скасувати» не діють, а підкладка накриває весь канвас.
 * Без стелі завислий сервер лишив би людину під нею назавжди. Минув строк — запит обривається
 * (`AbortController`: і очікування відповіді, і читання тіла) й падає з `code: 'timeout'`;
 * `spaceErrKey`/`taskErrKey` дають йому текст `formTimeout`, форма знову вільна й закривається.
 * Сервер за цей час міг устигнути виконати запит — текст про це й каже.
 */
function formApi(path, opts = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), FORM_POST_TIMEOUT_MS);
  return api(path, { ...opts, signal: ctl.signal })
    .catch((e) => { throw e?.name === 'AbortError' ? Object.assign(new Error('timeout'), { code: 'timeout' }) : e; })
    .finally(() => clearTimeout(timer));
}
const postForm = (path, body) => formApi(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});

/**
 * `POST` запиту, що ВИКОНУЄ `check` модуля `entry` (`module-check`, `module-enable|settings`), зі стелею `checkPostTimeoutMs(entry)`:
 * модуль із довгою перевіркою (`check_timeout_s` у записі `/api/modules`; `vercel-publish` у режимі `cli` — 130 с) інакше
 * отримав би обрив за `FORM_POST_TIMEOUT_MS` (20 с) раніше за вердикт. Модуль без `check_timeout_s` — та сама стеля, що в
 * `postForm`. Окрема функція, як `trustPost`/`taskPost`: тіло `formApi` дослівно стережуть тести. Обрив — `code: 'timeout'`.
 */
function checkPost(path, body, entry) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), checkPostTimeoutMs(entry));
  return api(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}), signal: ctl.signal,
  })
    .catch((e) => { throw e?.name === 'AbortError' ? Object.assign(new Error('timeout'), { code: 'timeout' }) : e; })
    .finally(() => clearTimeout(timer));
}

/**
 * `POST /api/task-new` зі стелею `TASK_VCS_POST_TIMEOUT_MS` (400 с) — для запиту, що справді клонує (`taskCreateClones`: `vcs` у тілі
 * чи простір з інтеграціями й роллю `vcs`):
 * перший клон репозиторію триває хвилини (модуль чекає до 180 с), а `formApi` (20 с) обірвав би запит посеред клону. Решті запитів
 * (порожнє поле, простір без синку, майстер) така стеля не потрібна: завислий сервер тримав би форму 400 с. Окрема функція, як
 * `trustPost`: тіло `formApi` дослівно стережуть тести. Обрив — `code: 'timeout'`, як у `formApi` (`taskErrKey` → `formTimeout`: сервер міг устигнути).
 */
function taskPost(body) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TASK_VCS_POST_TIMEOUT_MS);
  return api('/api/task-new', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}), signal: ctl.signal,
  })
    .catch((e) => { throw e?.name === 'AbortError' ? Object.assign(new Error('timeout'), { code: 'timeout' }) : e; })
    .finally(() => clearTimeout(timer));
}

/**
 * Довгий запит створення задачі (запит, що справді клонує: перший клон триває хвилини, а Esc і «Скасувати» на час запиту не діють):
 * підпис головної кнопки «Створюю…» і рядок-статус під полями — інакше форма стоїть нерухомо, без жодної ознаки життя. Рядок —
 * `role="status"`, додається в форму лише тут (розмітка форми не змінюється — ні ЛІГА, ні простору без клону); текст ставиться з
 * затримкою, бо щойно вставлену живу область читач не озвучує, а зміну тексту в ній — так. Запит НЕ обривається: сервер
 * однаково докловне й створить задачу, обрив дав би «помилку» при наявній задачі. Повертає `stop(restoreLabel)`: після відмови
 * підпис кнопки вертається (форма знову вільна), після успіху лишається — діалог закриється, а до того форма ще вимкнена.
 */
function showCreateWait(form) {
  const ok = form?.querySelector('button[data-a="ok"]');
  const label = ok?.textContent;
  if (ok) ok.textContent = t('wzCreating');
  const note = document.createElement('p');
  note.className = 'cv-form-note';
  note.setAttribute('role', 'status');
  const slot = form?.querySelector('[data-form-error]');
  if (slot) slot.before(note); else form?.append(note);
  const timer = setTimeout(() => { note.textContent = t('taskCreateWait'); }, 150);
  return (restoreLabel) => {
    clearTimeout(timer);
    note.remove();
    if (restoreLabel && ok && label != null) ok.textContent = label;
  };
}

// ненав'язливе повідомлення (нема змін / надіслано тощо)
function toast(msg) {
  let t = document.getElementById('cv-toast');
  if (!t) { t = document.createElement('div'); t.id = 'cv-toast'; t.className = 'cv-toast'; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove('show'), 3200);
}

/**
 * Стійка плашка з дією (батч 1.47). Одна на `id`: повторний виклик замінює текст.
 * `actions` — [{act, label, run}]; кнопка «Закрити» додається завжди, `onDismiss` —
 * що ще зробити при закритті. `data-h2d-ignore` — щоб «В Figma» не забрав плашку.
 * `lines` — додаткові рядки під основним (попередження модуля публікації): це ДАНІ, тож лише
 * `textContent`, ніколи розмітка. Без них розмітка плашки та сама, що була (один `span`).
 */
function notice(id, text, actions = [], onDismiss = null, lines = []) {
  let el = document.querySelector(`.cv-notice[data-notice="${id}"]`);
  if (!el) {
    el = document.createElement('div');
    el.className = 'cv-notice';
    el.dataset.notice = id;
    el.setAttribute('data-h2d-ignore', 'true');
    el.setAttribute('role', 'status');
    document.body.appendChild(el);
  }
  el.replaceChildren();
  const span = document.createElement('span');
  span.textContent = text;
  if (lines.length) {
    const body = document.createElement('div');
    body.className = 'cv-notice-body';
    body.appendChild(span);
    for (const line of lines) {
      const sub = document.createElement('span');
      sub.className = 'cv-notice-sub';
      sub.textContent = line;
      body.appendChild(sub);
    }
    el.appendChild(body);
  } else {
    el.appendChild(span);
  }
  const dismiss = { act: 'dismiss', label: t('noticeDismiss'), run: () => { dropNotice(id); onDismiss?.(); } };
  for (const a of [...actions, dismiss]) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.act = a.act;
    b.textContent = a.label;
    b.addEventListener('click', a.run);
    el.appendChild(b);
  }
}
function dropNotice(id) {
  document.querySelector(`.cv-notice[data-notice="${id}"]`)?.remove();
}

/* ===== Смуга (Task 3 Плану B): адаптер стану й легка перемальовка ===== */

/** Номер ітерації з id (`it4` → `4`) — той самий рядок думки, що раніше жив
 *  локальним `itNum` у `render()`, тепер потрібен ще й `barState()`. */
const itNum = (id) => String(id).replace(/^it/, '');

/**
 * Адаптер стану модуля в те, що чекає `barModel()`. Чиста функція: жодного
 * DOM, жодного fetch — лише читає змінні модуля й останній УСПІШНО
 * завантажений `curTask`/`curTaskList` (не локальні `task`/`taskList`
 * `render()`, бо цю функцію кличе і легкий `paintBar()` — відкриття
 * дропдауна не сміє чекати на мережу чи перезавантажувати iframe, як
 * пояснено над `setViewport` вище). Null-безпечна на `curTask === null`:
 * саме такий стан у `render()` до першого вдалого фетчу і при фатальному
 * `tasksErr` (жодного попереднього успіху не було).
 */
/** Відносний час локальної публікації для підпису («5 хв тому»); час невідомий (`null`) — порожньо. */
function pubWhenText(at) {
  if (typeof at !== 'number') return '';
  const r = relTime(at, Date.now());
  return t(r.key, r.n);
}

/* Стан оновлення інструмента (0.23.0): останній `GET /api/update` (`null` — ще не питали або сервер не відповів; тоді пігулки нема).
   Оголошено ДО `barState()`, що його читає: перше перемалювання смуги йде раніше за перший опит. */
let updateInfo = null;
/* Смугу вже намалював хтось, крім опиту оновлень (`render()`, «Задачі», дропдаун). До того опит лише запамʼятовує `updateInfo` —
   перший `paintBar()` іде від старту й підхопить його сам. ⛔ Інакше опит, що відповів раніше за задачу, малював смугу з НЕДОЗАВАНТАЖЕНИМ
   станом (дропдаун «Опублікувати» без пароля превʼю), і людина встигала його відкрити. */
let barSeeded = false;

function barState() {
  const its = (curTask && curTask.iterations) || [];
  /* Куди веде превʼю цієї задачі (ЛІГА-URL чи локальна адреса канваса) — одне рішення для смуги
     (`pubLocal`/`pubWhen`) і для дій «Відкрити»/«Скопіювати» (`BAR_ACTIONS`). */
  const pubTarget = previewTarget(curTask, spaceNow());
  const pickedIt = its.find((it) => it.id === picked) || null;
  const canvas = mode === 'canvas';
  // Пресет читаємо з РІЗНОЇ ширини залежно від виду — те саме розгалуження,
  // що й у старому шаблоні смуги (`CANVAS_PRESETS` проти `PRESETS`,
  // `canvasW` проти `vpWidth`): «Огляд» показує кадри полотна, а не рамку
  // робочого вигляду, і плутати їх — це та сама помилка, що вже виправляли
  // на ключі світу камери.
  const vp = canvas
    ? (CANVAS_PRESETS.find((p) => p.w === canvasW)?.id ?? null)
    : activePreset(vpWidth);
  const pickedPg = pickedPage
    ? (flattenPages(panelPages).find((f) => f.page.id === pickedPage)?.page ?? null)
    : null;
  /* GitLab: модель називає лише чотири стани (`sync`/`ahead`/`behind`/`off`),
     а `glCache.error` — пʼятий, рідкісний (git-команда впала, а не «не
     налаштовано»). Мапити його на «off» було б брехнею — репозиторій Є
     підключений, просто зараз не відповідає. Нетипове значення `'error'`
     `GL_DOT`/`glItems` у `shell-bar.js` читають як звичайний «підключений»
     стан (дропдаун з push/pull/історією; крапка сіріє через захисний
     `|| "off"` у `zoneGl`), а `glpush` у `BAR_ACTIONS` нижче першим ділом
     дивиться в кеш і каже РЕАЛЬНУ причину замість повторювати мережевий
     виклик, приречений на ту саму помилку. */
  const gl = !glCache || !glCache.configured ? 'off'
    : glCache.busy ? 'busy'
      : glCache.error ? 'error'
        : glCache.behind > 0 ? 'behind'
          : (glCache.unpushed > 0 || glCache.dirty) ? 'ahead'
            : 'sync';
  return {
    mode: canvas ? 'overview' : 'layout',
    view: canvasView,
    vp, vpw: vpWidth === null ? '' : String(vpWidth),
    // Крошка — ІДЕНТИФІКАТОР, не довгий заголовок (спека прототипу): jira,
    // коли є, інакше id задачі.
    taskId: curTask ? (curTask.jira || curTask.id || '') : '',
    taskTitle: curTask ? cleanTitle(curTask) : '',
    hasIteration: !!pickedIt,
    iterLabel: pickedIt ? t('iterTag', itNum(pickedIt.id)) : '',
    /* `label_text` із сервера вже несе повний підпис («Іт.3 · Категорія») —
       рахувати його ще раз тут значило б тримати ОДНЕ правило (яке з note
       лишити, який префікс зрізати) у двох мовах одразу, а докстрінг
       `iteration_label()` у `serve.py` прямо попереджає: це гарантовано
       розійдеться. Тому просто знімаємо вже відомий префікс `Іт.N`.
       ⛔ Обидва регеспи нижче лишаються КИРИЛИЦЕЮ і НЕ їдуть у словник:
       вони розбирають те, що написав `iteration_label()` у `serve.py`,
       а він пише українською незалежно від мови інтерфейсу. Замінити тут
       `Іт\.` на `t('iterTag', …)` значить у English-режимі шукати «It.3»
       у рядку «Іт.3 · Правки» — і лишити примітку з префіксом усередині. */
    iterNote: pickedIt
      ? (pickedIt.label_text || '').replace(
        new RegExp(`^Іт\\.${itNum(pickedIt.id)}\\s*(?:·\\s*)?`), '')
      : '',
    iterPub: !!(pickedIt && pickedIt.published),
    /* Автор і «своя/чужа». Ключ машини їде з сервера (`my_key` у `/api/task`):
       git-конфіг браузеру невідомий. Запис БЕЗ `author_key` — свій: уся
       історія до появи підписів не сміє раптом стати чужою. */
    iterAuthor: pickedIt?.author || '',
    iterMine: iterMine(pickedIt),
    iterOrigin: pickedIt?.origin || null,
    iterOnGl: !!(glCache && glCache.gitlab_it === picked),
    /* Підпис репозиторію з відповіді статусу ('GitLab' у ЛІГА, 'GitHub'/'Git'/'GitLab' від модуля) — СИРИЙ: нормалізує його
       `vcsBrand(label, space)` у смузі й палітрі (білий список; статус без `label` — «GitLab» у ЛІГІ, «Git» деінде). */
    glLabel: glCache?.label || '',
    /* Статус без помилки й без придатного `web` (file://, Gitea, Bitbucket → `web: null`; не `http(s)`): пункт «Історія» не
       показується. У помилці й поки статус «зайнято» (web ще невідомий) — лишається, як було: клік у «зайнято» каже про
       зайнятість (`glhistory`). `glCache` без `configured` — «Налаштувати», історії там нема. */
    glNoWeb: !!(glCache?.configured && !glCache.error && !glCache.busy && !vcsWebUrl(glCache.web)),
    /* Перелік ітерацій — щоб дропдаун крошки МІГ перемкнути, а не лише
       створити й видалити. Доти єдиним місцем вибору був `<select>` панелі;
       коли панель переписали, вибір зник із інструмента зовсім, бо `picked`
       більше нізвідки не встановлювався на не-останню ітерацію. */
    iterId: picked,
    iterList: (curTask?.iterations || []).map((x) => ({
      id: x.id,
      label: t('iterTag', itNum(x.id)),
      note: (x.label_text || '').replace(
        new RegExp(`^Іт\\.${itNum(x.id)}\\s*(?:·\\s*)?`), ''),
      pub: !!x.published,
      onGl: !!(glCache && glCache.gitlab_it === x.id),
      author: x.author || '', mine: iterMine(x), origin: x.origin || null,
    })),
    pagesError, flowRaw, flowError,
    right: inspectorApi()?.on ? 'inspector' : null,
    gl,
    /* Опублікована: у ЛІГА (`publish_url`) АБО локально модулем (`publish_local`) — `isPublished`
       (`spaces-model.js`). Куди веде превʼю й чи воно «локальне» — `previewTarget`. */
    published: isPublished(curTask),
    /* Застереження модуля «за адресою» (Vercel): рівно те, що віддав сервер (`/api/task`: `publish_gate` — чи
       ОПУБЛІКОВАНЕ превʼю з паролем, `publish_gate_stale` — пароль з того часу змінили). Для ЛІГА й модуля «у теку»
       полів нема — `undefined` доходить до моделі як є (нема поля — нема тривоги), а вона сама ЛІГА їх не читає. */
    pubGate: curTask?.publish_gate,
    pubGateStale: curTask?.publish_gate_stale === true,
    pubLocal: pubTarget?.kind === 'local',
    /* Відносний час («5 хв тому»), а не сирий ISO UTC з `publish_local.published_at`: той самий
       `relTime`, що в екрана «Задачі». Невідомий час — порожньо, підпис тоді просто «локально». */
    pubWhen: pubTarget?.kind === 'local' ? pubWhenText(pubTarget.at) : '',
    /* «Превью застаріло відносно ітерацій» — сигнал, якого жодна наявна
       точка API не рахує (треба порівнювати час публікації з часом останньої
       зміни кожної ітерації/сторінки, а такого поля ніде нема). Вигадувати
       наближення небезпечніше за його відсутність: хибне «застаріло» жене
       публікувати те, що публікувати не треба, хибне «свіже» — навпаки.
       Тому `false` завжди, як і в старій смузі (там цього сигналу не було
       взагалі) — іконка публікації просто ніколи не показує ⚠. */
    pubStale: false,
    /* Пароль превʼю, свій/типовий і чи ЗІБРАНЕ превʼю вже з ним на кожній сторінці
       (`preview_gate` рахує сервер — reseal міняв би лише обгортку, а сторінки лишались
       старими) — через `pwView` (`spaces-model.js`): стале/без-гейта лише для ОПУБЛІКОВАНОЇ
       в ЛІГА задачі (`publish/`, зібраний без деплою, нікому не роздано, і «превʼю зі старим
       паролем» там була б тривогою ні про що); а в просторі, де публікує МОДУЛЬ, пароль у
       відповіді сервера — ЛІГА-шний, і ні він, ні попередження про нього не показуються.
       «Сторінки БЕЗ гейта» (зібрані до фікса TD-37) — інша причина, інший підпис; посилання
       при цьому працює, тож його не вимикаємо. */
    ...pwView(curTask, spaceNow()),
    /* Секрети простору не читаються: пароль невідомий — замість пароля показуємо помилку (`pwUnreadable`, `spaces-model.js`). */
    pwError: pwUnreadable(curTask, spaceNow()),
    teams: teamsMute,
    pagePub: !pickedPg || visibleIds(panelPages).has(pickedPg.id),
    figmaBusy,
    tasksErr,
    tasksErrKey,
    openDd, iterDelAsk,
    homeOpen,
    /* Сторінка оверлею (`tasks`/`conn`/`wiz`) — для крихти смуги й пункту ⌘K; поза оверлеєм — `null`. */
    homePage: homeOpen ? homePage : null,
    /* Простір для фішки й дропдауна (див. «Простори» вгорі файла). Без `space`
       фішки в смузі нема зовсім: шар вимкнено або просторів ще нема. */
    space: spaceNow(),
    spaces: spacesResp && !spacesResp.off ? spacesResp.spaces : [],
    /* Оновлення інструмента: пігулка в рядку вкладок і дії ⌘K (`pillModel`). */
    update: updateInfo,
  };
}

/* Вкладки відкритих задач (0.25.0): клієнтський стан цього вікна (`tabs-model.js`, його шапка). */
let tabs = (() => { try { return readTabs(localStorage.getItem(TABS_KEY)); } catch (e) { return []; } })();
/* Опит нових на вкладках — лише при ЗМІНІ складу вкладок (а не на кожен `render`, що кличе `saveTabs`): інакше 25–60 запитів/хв
   у командну базу (її квоту вже вибирали). Стан опиту оголошено тут, нагорі, щоб жоден шлях `saveTabs` не вскочив у TDZ. */
let newsBusy = false;
let newsAgain = false;
let newsSetKey = null;
let newsLastAt = 0;
let newsCtxKey = null;
/* Примусові опити (зміна складу вкладок / активної задачі) зливаємо в ОДИН: швидке перемикання між вкладками
   не мусить слати по запиту на кожну з них при кожному кроці. Хвостовий debounce; поріг 30 с для не-force лишається. */
const NEWS_SOON_MS = 1500;
let newsSoonTimer = null;
function pollTabNewsSoon() {
  clearTimeout(newsSoonTimer);
  newsSoonTimer = setTimeout(() => { newsSoonTimer = null; pollTabNews(true); }, NEWS_SOON_MS);
}
function saveTabs() {
  try { localStorage.setItem(TABS_KEY, writeTabs(tabs)); } catch (e) {}
  const k = tabs.map((x) => `${x.space ?? ''}/${x.id}`).sort().join('|');
  if (k !== newsSetKey) { newsSetKey = k; pollTabNewsSoon(); }
}
/** `{ключ: {state, age_s}}` з `/api/claude-statuses` або `null` (стан Claude на вкладках). */
let claudeAll = null;
/** Нові командні на ІНШИХ вкладках: `{id задачі: n}` (опит `pollTabNews`, поправка 17 плану Б2). */
let tabNews = {};
const tabsEl = document.getElementById('tabs');
const hudEl = document.getElementById('hud');
const islTools = document.getElementById('isl-tools');
const islandEl = hudEl.querySelector('.island');
/** Скільки px знизу перекриває острівець над прямокутником `r` (рамка чи полотно) — для `host.bottomInset` коментатора. */
function islandInsetOver(r) {
  const isl = islandEl.getBoundingClientRect();
  return isl.height && r ? Math.max(0, Math.round(r.bottom - isl.top + 8)) : 0;
}
/* Рамка питає це через `HOST_ARG.bottomInset` (`serve.py`; пару приколює `test_comments_role`). */
window.__dcIslandInset = () => islandInsetOver(frame.getBoundingClientRect());
/**
 * Записати розмітку в контейнер, не гублячи фокус клавіатури: `innerHTML` знищує вузол, а з ним і фокус. Той самий рядок,
 * що й минулого разу, — нічого не пишемо взагалі (опит стану Claude та `paintBar` кличуть перемальовку часто); інакше
 * запамʼятовуємо `data-act`+`data-val` сфокусованої кнопки й вертаємо фокус на таку саму в новій розмітці.
 * Віддає `true`, коли DOM справді переписано.
 */
function writeKeepFocus(el, html, prev) {
  if (html === prev) return false;
  const a = document.activeElement;
  const had = a && a !== document.body && el.contains(a) && a.dataset && a.dataset.act
    ? { act: a.dataset.act, val: a.dataset.val } : null;
  el.innerHTML = html;
  if (had) {
    const same = [...el.querySelectorAll('[data-act]')].find((x) => x.dataset.act === had.act && x.dataset.val === had.val);
    if (same) same.focus({ preventScroll: true });
  }
  return true;
}
/** Ціль зміни задачі, що зараз летить (`BAR_ACTIONS.tab`), і остання ціль, яку клікнули за цей час. */
let tabSwitch = null;
let tabQueued = null;
let tabsHtmlLast = null;
let islHtmlLast = null;
let tabsActiveSeen = null;
/** Рядок вкладок: логотип, вкладки, «+», пігулка оновлення, шестерня. */
function paintTabs() {
  /* Активна вкладка числа не має (його показує острівець): перехід НА вкладку гасить число одразу. */
  if (currentTaskId && tabNews[currentTaskId]) { tabNews = { ...tabNews }; delete tabNews[currentTaskId]; }
  /* Зміна активної задачі чи простору міняє, які вкладки «інші»: один примусовий опит (не на кожен paintTabs). */
  const spNow = spaceNow()?.id ?? null;
  const ctx = `${spNow ?? ''}/${currentTaskId ?? ''}`;
  if (newsCtxKey !== null && ctx !== newsCtxKey) pollTabNewsSoon();
  newsCtxKey = ctx;
  /* Числа лише вкладок поточного простору: після перемикання простору числа старого не мусять висіти. */
  const newsHere = {};
  for (const x of tabs) if (tabNews[x.id] && (x.space ?? null) === spNow) newsHere[x.id] = tabNews[x.id];
  tabsEl.setAttribute('aria-label', t('tabsNav'));
  const html = tabsHTML(tabsModel({ tabs, activeId: currentTaskId, homeOpen, homePage, claude: claudeAll,
    update: pillModel(updateInfo), news: newsHere }));
  const list = tabsEl.querySelector('.tabs-list');
  const scrolled = list ? list.scrollLeft : 0;
  if (!writeKeepFocus(tabsEl, html, tabsHtmlLast)) return;
  tabsHtmlLast = html;
  const nl = tabsEl.querySelector('.tabs-list');
  /* Переписаний список скидає прокрутку: вертаємо, а до активної вкладки докручуємо лише коли вона щойно стала активною
     й опинилась поза видимою зоною (інакше ручна прокрутка людини вернулась би назад на кожен опит стану Claude). */
  if (nl) nl.scrollLeft = scrolled;
  const on = tabsEl.querySelector('[data-act="tab"][aria-current="page"]');
  const onId = on ? on.dataset.val : null;
  if (on && nl && onId !== tabsActiveSeen) {
    const r = on.getBoundingClientRect();
    const lr = nl.getBoundingClientRect();
    if (r.left < lr.left || r.right > lr.right) on.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
  tabsActiveSeen = onId;
}
/** Інструменти острівця (інспектор лише в «Макеті», баг/ідея скрізь); сегмент Claude веде `paintClaude`. */
function paintIsland() {
  islandEl.setAttribute('aria-label', t('islandNav'));
  const html = islandToolsHTML({ screen: homeOpen ? 'home' : 'task', mode: mode === 'canvas' ? 'overview' : 'layout',
    inspectorOn: !!inspectorApi()?.on, commentsOn: cmtOpen, commentsCount: openCount(cmtSnap), commentsNew: cmtNewsN,
    commentTool: cmtTool });
  if (writeKeepFocus(islTools, html, islHtmlLast)) islHtmlLast = html;
}
/** Відкрита задача — вкладка; задачі поточного простору, яких вже нема, — геть (чистка лише в межах простору, що його
 *  віддав `/api/tasks`: чужий простір чи задачу без теки не викидаємо — збій мережі не мусить закривати вкладки). */
function rememberTab(task, taskList) {
  const sp = task.space || null;
  const spId = sp?.id || null;
  const ids = (taskList.tasks || []).map((x) => x.id);
  tabs = pruneTabs(tabs, spId, ids);
  const id = taskList.current ?? currentTaskId;
  const entry = (taskList.tasks || []).find((x) => x.id === id);
  if (id) {
    tabs = upsertTab(tabs, { id, title: entry ? cleanTitle(entry) : cleanTitle(task), space: spId, color: sp?.color ?? null,
      jira: entry?.jira ?? task.jira ?? null });
  }
  saveTabs();
  paintTabs();
}

/**
 * Легка перемальовка ЛИШЕ смуги: без мережі, без iframe, без панелі. Для
 * відкриття/закриття дропдауна, підсвітки інспектора після клавіші `I`
 * всередині iframe — усього, що НЕ мусить чіпати `frame.src` (`applyMode`
 * робить це на кожному повному `render()`, і навіть той самий рядок
 * перезавантажує документ — див. коментар над `setViewport`). `barState()`
 * null-безпечна на `curTask === null`, тому окремого раннього виходу тут не
 * треба: до першого рендера клікнути смугу нема чим — у ній ще немає
 * жодного `[data-act]`/`[data-dd]`.
 *
 * Кличе й `paintInsp()` (Task 5 Плану B, означена нижче — `function`
 * піднімається, порядок у файлі значення не має): права панель інспектора
 * залежить від ТОГО САМОГО `inspectorApi()`, що й крапка кнопки в смузі
 * (`barState().right`), тож усюди, де могла змінитись одна, могла змінитись
 * і друга. Один виклик тут — і жодному з наявних місць `paintBar()`
 * (відкриття дропдауна, `BAR_ACTIONS.inspector`, завантаження iframe) не
 * треба окремо памʼятати про панель: забути другий виклик поруч із першим —
 * рівно та вада, від якої застерігає задача («два шляхи до одного стану»).
 */
function paintBar() {
  barSeeded = true;
  if (openDd !== 'iter') iterDelAsk = false;   // питання про видалення живе лише в відкритому дропдауні ітерації
  /* Фокус дропдауна просторів: `innerHTML` знищує вузол, а з ним і фокус.
     Запамʼятовуємо ІНДЕКС рядка (ідентичність вузла після перемальовки інша) і те,
     що фокус стояв на фішці. */
  const spDd = bar.querySelector('.dd--spaces');
  const spRow = spDd && spDd.contains(document.activeElement)
    ? [...spDd.querySelectorAll('.dd-item')].indexOf(document.activeElement) : -1;
  const chipHadFocus = !!document.activeElement
    && document.activeElement === bar.querySelector('.space-chip');
  const spFresh = openDd === 'space' && !spaceDdWasOpen;
  spaceDdWasOpen = openDd === 'space';
  const st = barState();
  bar.innerHTML = barHTML(barModel(st), st);
  paintTabs();
  paintIsland();
  paintInsp();
  if (openDd === 'space') {
    /* Щойно відкрили — фокус на ПОТОЧНИЙ рядок (там людина й так хоче почати); інакше —
       на той самий рядок, де стояв. Клавіатура далі йде по `.dd--spaces .dd-item`. */
    const rows = [...bar.querySelectorAll('.dd--spaces .dd-item')];
    const cur = rows.findIndex((r) => r.getAttribute('aria-current') === 'true');
    const at = spRow >= 0 ? spRow : (spFresh ? Math.max(cur, 0) : -1);
    if (rows[at]) rows[at].focus({ preventScroll: true });
    else if (chipHadFocus) bar.querySelector('.space-chip')?.focus({ preventScroll: true });
  } else if (chipHadFocus) {
    /* Дропдаун закрили (Esc, повторне натискання), коли фокус був на фішці, — вузол
       новий, фокус вертаємо. */
    bar.querySelector('.space-chip')?.focus({ preventScroll: true });
  }
}

/** `keepFrame: true` — не переприсвоювати `frame.src` (див. `applyMode`): лише `afterModulesChange` і лише поки оверлей
 *  відкритий (`keepFrame: homeOpen`) — рамка там схована, а документ однаково перезавантажить `render()` при виході
 *  (`leaveHome`). Без оверлея `afterModulesChange` рамку перезавантажує, бо виходу вже не буде. */
async function render({ keepFrame = false } = {}) {
  let task, taskList;
  try {
    task = await api('/api/task');
    taskList = await api('/api/tasks');
    /* Простір відповіді інший, ніж у задачі, яку ми показували: його змінив агент чи сусідня
       вкладка (клацання тут проходить через `afterSpaceChange`/`switchTask`, які скидають
       самі, і тоді `curTask` вже `null`). Усе, що належало тому простору, — пакет тюнера з
       ревізією, позначки зʼємки, кеш GitLab, фільтри екрана — належить не цій задачі:
       забуваємо ДО того, як хоч щось із нього буде прочитано. `loadTune()` усередині
       `resetPerTaskState` бере пакет НОВОЇ задачі (сервер уже в новому просторі) і ставить
       `tuneRev`; без цього перший поворот ручки пішов би без `base_rev` і затер би
       її `.dc-tuner.json`. Екран «Задачі», якщо відкритий, лишається екраном — як в
       `afterSpaceChange`. */
    if (curTask && spaceChanged(curTask.space?.id, task.space?.id)) {
      await resetSpaceState();
      if (homeOpen) enterHome({ spaces: false });
    }
    curTask = task; curTaskList = taskList; tasksErr = false; tasksErrKey = null;
    currentTaskId = taskList.current ?? currentTaskId;
    rememberTab(task, taskList);
    /* Пакет тюнера не читався для цієї задачі ні разу (`tuneRev` невизначена): задачі не
       було, коли стартував канвас або коли її «забув» `showNoTask`, і вона зʼявилась сама
       (агент). Запис без ревізії затер би чужий `.dc-tuner.json`, тож перечитуємо тут. */
    if (tuneRev === undefined) await loadTune();
  } catch (e) {
    /* У поточному просторі нема жодної задачі (щойно створений, порожній) або просторів
       нема зовсім — це не поломка, а місце для «Нової задачі» чи привітання. Тому не
       `tasksErr`: червона смуга «не читається» там брехала б. */
    if (e?.code === 'no-task') { await showNoTask(); return; }
    tasksErr = true;
    /* Причина: чужий процес на порту (`e.key`), файл задач простору не читається чи
       реєстр просторів битий (`e.code` — сервер шле його завжди разом з `error`).
       Невідомий код лишає типову причину смуги. */
    tasksErrKey = e?.key || readErrKey(e?.code) || null;
    /* Перше завантаження впало ЦІЛКОМ: `curTask` іще `null`, крихтам нема з
       чого малюватись, а `applyMode`/`renderPanel` нижче читають
       `task.iterations` і впали б на `null`. Малюємо саму смугу помилки й
       зупиняємось — той самий короткий вихід, що стояв тут до Task 3.
       Транзиентний збій ПІСЛЯ вдалого першого разу деградує інакше: крихти
       лишаються зі СТАРИМИ даними (`curTask` не чіпаємо), смуга помилки
       з'являється ПІД ними (`bar-model.js`, поле `error`), а не замість.
       Простори питаємо ТУТ: без задачі фішку нема з чого малювати, а саме з неї
       можна піти з недоступного простору в інший. Сцену чистимо — після переходу
       з іншого простору під смугою помилки стояв би ЧУЖИЙ макет. */
    if (!curTask) { await loadSpaces(); blankStage(); paintBar(); return; }
    task = curTask; taskList = curTaskList;
  }
  // picked = обрана ітерація (у ній працюєш). За замовч. — остання; нормалізуємо.
  if (!task.iterations.some((it) => it.id === picked)) {
    picked = task.iterations.length ? task.iterations[task.iterations.length - 1].id : null;
  }
  await loadPages();
  paintBar();
  applyMode(task, { keepFrame });
  renderPanel();
}

/* ===== Смуга (Task 3 Плану B): дії й одна делегація замість десятка
   `querySelector` ===== */

/** Обрана ітерація як обʼєкт із останнього УСПІШНО завантаженого `curTask`. */
const curIter = () => (curTask?.iterations || []).find((it) => it.id === picked) || null;

/**
 * Чи ітерація МОЯ — порт `iteration_is_mine` із `serve.py`, з тими ж межами.
 *
 * Порівняння по КЛЮЧУ (email), не по імені: тезки й перейменування не сміють
 * робити мою ітерацію чужою. Дві межі на користь «своя», бо «чужа» показує
 * мітку й забороняє пуш: запис без `author_key` (уся історія до підписів) і
 * машина без особи (`my_key` порожній).
 */
const iterMine = (it) => {
  const key = it?.author_key || '';
  const my = curTask?.my_key || '';
  return !key || !my || key === my;
};

/**
 * Нова ітерація — копія обраної, з приміткою. Тіло СПІЛЬНЕ для крошкових
 * `newit` і `dupit`: у поточному сервері обидва означають рівно одну дію
 * (`POST /api/iteration {from, note}`) — так само, як у старій смузі
 * ідентичну дію мали й «＋ ітерація» панелі, і «Дублювати» контекстного меню
 * пілюлі, лише під різними підписами. Вигадувати ДРУГУ, «тиху» операцію без
 * підтвердження під `dupit` означало б додати функціональність, якої немає
 * ніде в коді, — а не перенести наявну.
 */
async function dupIteration() {
  const it = curIter();
  if (!it) return;
  const from = it.id;
  const label = it.label_text || it.id;
  const note = await ask(t('menuDuplicateIterationPrompt', label));
  if (note === null) return;              // Esc — нічого не міняємо
  try {
    const r = await post('/api/iteration', { from, note });
    picked = r.iteration.id;
    await refreshGitlab(); render();
  } catch (e) { tellError(t('errTDupIter'), e.message); }
}

/**
 * Забути ВСЕ, що належить ОДНІЙ задачі. Кличе це перемикач задачі — і мусить
 * кликати будь-який майбутній другий вхід до зміни поточної задачі.
 *
 * ⛔ Чому окрема названа функція, а не три рядки в тілі перемикача (де вони й
 * жили). Ключі тут ПЕР-ЗАДАЧНІ й однакові на вигляд: `it1` є в кожній задачі,
 * `it1/holovna` — теж. Тому кожен стан, підписаний таким ключем, при
 * перемиканні мовчки переїжджає в чужу задачу: не падає, не свариться, просто
 * показує роботу з іншої задачі як свою. Забути тут один рядок — і інструмент
 * починає брехати. Список того, що є пер-задачним, мусить жити в ОДНОМУ
 * місці, щоб другий вхід не мав шансу забути його наполовину.
 *
 * Що саме забуваємо і чому:
 *   · позначки автозʼємки — пер-ітераційні, тобто «зупинив у задачі A» глушило
 *     б автостарт `it1` у задачі B (той самий клас помилки, що вже ловили на
 *     ключі світу камери, AB2);
 *   · пакет тюнера — ключ сторінки (`tunePage`) теж пер-задачний, тож без
 *     перечитування `reapplyTune` намалював би правки задачі A на макеті
 *     задачі B, а `saveTune` записав би їх у `.dc-tuner.json` задачі B, тобто
 *     ПРИПИСАВ би чужу роботу. Канал ще й пише повний пакет, тож без
 *     `loadTune()` перший же поворот ручки в новій задачі знищив би її власний
 *     файл — рівно та діра, від якої застерігає докстрінг `loadTune`;
 *   · відповідь перевірки свіжості (`lastCheck`) — вона про ітерацію ПОПЕРЕДНЬОЇ задачі: `it1`
 *     є в кожній, тож `checkOf()` (звіряє лише id ітерації) віддав би її новій задачі, і
 *     кнопка зʼємки показала б чуже число застарілих кадрів;
 *   · рядки останнього звіту — вони описують документ, якого вже немає.
 *     Це ГІГІЄНА, і сказати це чесно важливіше, ніж записати рядок у заслуги:
 *     `paintInsp` перебирає мапу наново на КОЖНІЙ перемальовці, а дістати з
 *     неї декларацію може лише ручка, яку та сама перемальовка й намалювала,
 *     тож живої вади прибирання не закриває (мутація «прибрати цей рядок»
 *     лишає охоронця зеленим — перевірено). Тримаємо його рівно за тим, що
 *     мапа тримає посилання на опис вузла з попереднього макета.
 *
 * `await` на `loadTune()` несучий: рамка макета вантажиться в `render()`, а
 * `reapplyTune` накладає правки на її `load`. Почни рендер раніше за читання —
 * і на макет ляже пакет ПОПЕРЕДНЬОЇ задачі.
 */
async function resetPerTaskState() {
  /* Плашка «Опубліковано локально» — про ТУ задачу, яку щойно опублікували (стійка, без таймера): на
     іншій задачі чи в іншому просторі вона бреше про те, що опубліковано. */
  dropNotice('publish-local');
  /* Те саме для плашки «Опубліковано на Vercel» (2b-1): вона про щойно опубліковану задачу, а не про наступну. */
  dropNotice('publish-remote');
  autoShootStopped.clear(); autoShootOff.clear(); autoShootSig.clear();
  tuneState = emptyTune();
  /* Ревізія — теж пер-задачна: з ревізією задачі A перший запис у задачі B
     дістав би 409 і «пакет змінено поза вкладкою» на рівному місці. */
  tuneRev = undefined;
  inspDecls = new Map();
  lastCheck = null;
  await loadTune();
  picked = null;
}

/**
 * Забути ВСЕ, що належить ОДНОМУ ПРОСТОРУ, — і дізнатись, у якому ми тепер. Кличуть
 * перемикач простору, створення простору й `switchTask`, коли `task-switch` перевів у
 * простір іншої задачі. Надмножина `resetPerTaskState`: задача простору — теж чужа.
 *
 * ⛔ Той самий клас пастки, що в `resetPerTaskState`: перелік того, що належить
 * простору, живе В ОДНОМУ місці, інакше другий вхід перепише половину. Що забуваємо:
 *   · задачу, список задач, дані екрана «Задачі» й `currentTaskId` — усе чуже;
 *   · лічильники `taskSwitchGen`/`homeSeq`: відповіді, що вилетіли ДО зміни простору
 *     (їх запити йшли до ІНШОГО файла задач), не сміють перемалювати екран;
 *   · кеш GitLab і стан тиші Teams — вони про репозиторій і канал ТІЄЇ задачі;
 *   · помилку смуги: «файл не читається» була про попередній простір;
 *   · фільтри екрана «Задачі» за напрямком і дизайнером та пошук — значення з даних
 *     ТОГО простору (`pruneFilters` лишив би їх, бо в порожньому новому просторі
 *     прибирати нема за чим), і список мовчки виглядав би порожнім.
 * Вкладку, сортування й статус не чіпаємо: це смак людини, а не дані простору.
 *
 * Наприкінці — `loadSpaces()` (крім `reload: false`: викликач щойно сам його перечитав,
 * `showNoTask` після лікування): фішка й дропдаун мусять бачити НОВИЙ поточний простір ще
 * до `render()`.
 */
async function resetSpaceState({ reload = true } = {}) {
  await resetPerTaskState();
  curTask = null; curTaskList = null; homeData = null; currentTaskId = null;
  taskSwitchGen += 1; homeSeq += 1;
  glCache = null; teamsMute = null;
  dropGlState();
  tasksErr = false; tasksErrKey = null;
  homeUi.q = ''; homeUi.tags.clear(); homeUi.designers.clear(); saveHomeUi();
  resetHomeEdit();
  if (reload) await loadSpaces();
}

/**
 * Перелік просторів машини (`/api/spaces`) у `spacesResp`. Не кидає: реєстр, що не
 * читається, — це `spacesResp = null` (фішки нема), а САМУ причину людині показує
 * `render()` (503 `spaces-unreadable` на `/api/task`).
 *
 * `heal` — лікувати ВИСЯЧИЙ `current` (його вилучили руками чи агентом — `healTarget`): сервер
 * у запиті бачить таке як «простору нема», тож `/api/task` дає `no-task`, екран «Задачі»
 * порожній, а фішки нема, щоб піти. Перемикаємо на перший доступний (так само робить
 * `active_space()` поза запитом) і перечитуємо. Лікують лише ті, хто й так вирішує, що
 * показати, — `render()` і `loadHome()`; відкриття дропдауна чи палітри лише ПОКАЗУЄ
 * перелік і сервер за людину не перемикає. Одна спроба: збій перемикання лишає реєстр як є,
 * а не крутить цикл.
 *
 * Повертає `true`, коли ЛІКУВАЛО і реєстр тепер не висить: відповідь викликача про «задачі
 * нема» застаріла, пер-задачний стан належав іншому простору. Явне значення, а не прапорець
 * модуля, який хтось мусив би скинути перед викликом і прочитати одразу після.
 */
async function loadSpaces({ heal = false } = {}) {
  const seq = ++spacesSeq;
  let r = null;
  try { r = await api('/api/spaces'); } catch (e) { r = null; }
  let healed = false;
  const to = heal ? healTarget(r) : null;
  if (to) {
    try {
      await post('/api/space-switch', { id: to });
      r = await api('/api/spaces');
      healed = healTarget(r) === null;
    } catch (e) { /* лишаємо як є: людина перемкне сама, фішка тепер без поточного */ }
  }
  if (seq === spacesSeq) spacesResp = r;
  return healed;
}

/**
 * Простір змінився (перемкнули, створили): забути старий, показати новий. Екран «Задачі»
 * (якщо відкритий) лишається екраном — людина перемикала простір ЗВІДТИ, і чекає список
 * задач нового, а не стрибок у макет. Без нього — `render()` сам вирішує: є задача —
 * малює її, нема — піднімає екран «Задачі» (`showNoTask`). Коли екран відкритий, `render()`
 * іде ще й ПІД ним: він тягне задачу нового простору, і кнопка «назад» (крошка задачі)
 * знову має куди вести.
 */
async function afterSpaceChange() {
  await resetSpaceState();
  /* Перелік просторів `resetSpaceState` щойно перечитав — екран його вдруге не питає. */
  if (homeOpen) enterHome({ spaces: false });
  await render();
  /* Статус GitLab нового простору — ПІСЛЯ рендера: його питають по обраній ітерації
     (`picked`), а вона нормалізується саме в `render()`. Без цього крапка GitLab у
     просторі з інтеграціями лишалась би «нема», доки щось інше не освіжить кеш
     (`resetSpaceState` його обнулив). Простір без ролі `vcs` `refreshGitlab` не питає. */
  await refreshGitlab();
  paintBar();
}

/**
 * У поточному просторі задачі нема (`404 no-task`): спершу полікувати висячий `current`
 * (`loadSpaces({heal})`), далі — екран «Задачі» (там і привітання, коли просторів нема
 * зовсім: `paintHome` його вибирає за `spacesResp`).
 *
 * Лікування — це зміна простору, якої ми не робили: пер-задачний стан (пакет тюнера, його
 * ревізія, позначки зʼємки) належав задачі, якої вже нема, а на старті не був прочитаний
 * зовсім (`loadTune` до першого рендера теж отримав `no-task`) — без `resetSpaceState`
 * перший поворот ручки в нової задачі пішов би БЕЗ `base_rev` і затер би її `.dc-tuner.json`.
 * Не вилікувано, а задача була — забуваємо й її пер-задачний стан: інакше він переїхав би в
 * наступну задачу, яка зʼявиться тут сама (агент створив).
 */
async function showNoTask() {
  const healed = await loadSpaces({ heal: true });
  if (healed) {
    await resetSpaceState({ reload: false });
    if (homeOpen) enterHome({ spaces: false });
    return render();
  }
  if (curTask) await resetPerTaskState();
  curTask = null; curTaskList = null; currentTaskId = null;
  tasksErr = false; tasksErrKey = null;
  blankStage();
  enterHome({ spaces: false });
  return undefined;
}

/**
 * Прибрати зі сцени й панелі все, що належало ЗАДАЧІ, якої більше нема на екрані (нема
 * задачі, простір недоступний). Без цього під смугою помилки стояв би макет з
 * ПОПЕРЕДНЬОГО простору — той, що вже не відповідає жодній відкритій задачі.
 */
function blankStage() {
  ovc.leave();
  canvasEl.hidden = true; stage.hidden = false;
  if (frame.getAttribute('src') !== 'about:blank') frame.src = 'about:blank';
  picked = null; pickedPage = null; pickedState = null;
  panelPages = []; panelRev = ''; panelPagesIt = null; pagesError = null;
  renderPanel();
}

/* ── діалоги просторів і нової задачі ────────────────────────────────────────
   Оболонку (одиночність, Esc, фокус-пастка, відправка, помилка на місці) дає
   `askForm`; розмітку й проводку полів — `space-dialogs.js`; правила (id з назви,
   коди відмов → ключі) — `spaces-model.js`. Тут лише мережа й стан модуля.
   ⛔ Запит іде ВСЕРЕДИНІ `onSubmit`, а не після закриття діалогу: відмова сервера
   («тека надто широка», «такий id уже є») мусить лишитись там, де людина щойно
   набрала значення, а не тостом поверх закритого вікна, з якого вона вже вийшла. */

/** Фішка простору в смузі (свіжий вузол: смуга міняє `innerHTML` цілком). */
const chipEl = () => bar.querySelector('.space-chip');
/** Фокус на фішку: після дропдауна, чий рядок щойно зник разом із ним, клавіатура лишилась би на `body`. */
const focusChip = () => chipEl()?.focus({ preventScroll: true });

/**
 * Куди повернути фокус після діалогу просторів, коли вузол, що його мав, перемальовано
 * (`askForm` сам запамʼятовує відкривача, це — запасний): фішка в смузі, а на привітанні, де
 * її ще нема, — кнопка «Створити простір».
 */
const spaceDialogFocusBack = () => chipEl() ?? homeNode()?.querySelector('[data-th="spacenew"]');

/* ── майстер нового простору (етап 3b) ─────────────────────────────────────────────────────────────────────
   Третя сторінка оверлею `#tasks-home` (`homePage === 'wiz'`). Стан і проводку тримає `wizard.js`; тут — лише входи
   й залежності. «Новий простір…» (дропдаун, ⌘K) і привітання ведуть сюди; діалог простору лишився для «Назва й колір…». */
const wiz = createWizard({
  node: () => ensureHome(),
  api: (p) => api(p),
  post: (p, body, entry) => (entry ? checkPost(p, body, entry) : postForm(p, body)),
  askYesNo,
  toast,
  spaces: () => spacesResp,
  peek: (p) => api(`/api/space-peek?path=${encodeURIComponent(p)}`),
  takenPaths: () => (spacesResp?.spaces ?? []).map((x) => x.path),
  takenTaskIds: () => formApi('/api/tasks?all=1').then((r) => (r.tasks || []).map((x) => x.id)).catch(() => []),
  afterSpaceCreated: () => afterSpaceChange(),
  afterSpaceEdited: (id, saved) => applySpaceMeta(id, saved),
  afterModulesChange: () => afterModulesChange(),
  openTrust: (entry, spaceId) => openTrust(entry, spaceId),
  openTask: (made) => wizOpenTask(made),
  exit: ({ back = false } = {}) => (back ? wizBack() : enterHome({ page: 'tasks' })),
  copy: (s) => navigator.clipboard.writeText(s),
});

/* Звідки майстер відкрили: `null` — полотно задачі (оверлей був закритий), інакше сторінка оверлею. Потрібно лише
   «Скасувати» до створення: простору нема, і людина вертається туди, де була. */
let wizFrom = null;
/* Кнопка привітання, якою відкрили майстер (`spacenew` чи `spaceopen`): «Скасувати» вертає фокус саме на неї. */
let wizOpener = 'spacenew';

/** Відкрити майстер на кроці 1. Шар просторів вимкнено — входу нема (як і «Новий простір…» у дропдауні). Бічна панель
 *  «Підключення» з незбереженим (там можуть бути секрети) спершу питає — як логотип: `enterHome` закрив би її мовчки. Без
 *  панелі `await` не виконується, і вхід лишається синхронним. */
async function openWizard({ folderFirst = false } = {}) {
  if (spacesResp?.off) return;
  if (cnDrawer && !(await dismissCnDrawer())) return;
  wizFrom = homeOpen ? homePage : null;
  wizOpener = folderFirst ? 'spaceopen' : 'spacenew';
  wiz.open({ folderFirst });
  enterHome({ page: 'wiz' });
  /* Майстер — нова сторінка: з верху, а не зі скролом списку задач (`wiz.paint` повертає скрол, що був у вузлі). */
  const home = homeNode();
  if (home) home.scrollTop = 0;
  wiz.focusStep();
}

/**
 * «Скасувати» до створення — туди, звідки прийшли: на полотно задачі (коли вона є) чи на сторінку оверлею; фокус — на
 * фішку простору, як після колишнього діалогу. На першому запуску фішки нема — на кнопку привітання, якою майстер відкрили.
 * `enterHome` на «Підключення» ставить `connFocusPending` (фокус на першу картку після завантаження списку) — тут це
 * крадіжка: людина щойно скасувала дію з фішки простору.
 */
async function wizBack() {
  if (wizFrom === null && currentTaskId) await leaveHome();
  else enterHome({ page: wizFrom === 'conn' ? 'conn' : 'tasks' });
  if (wizFrom === 'conn') connFocusPending = false;
  (chipEl() ?? homeNode()?.querySelector(`[data-th="${wizOpener}"]`))?.focus({ preventScroll: true });
}

/**
 * Задачу з кроку 4 створено (`task-new` уже зробив її простір і її поточними) — відкрити, як «Нова задача» на «Задачах»:
 * простір відповіді порівнюємо з відомим (`spaceChanged`), пер-задачний стан попередньої — чужий.
 */
async function wizOpenTask(made) {
  if (spaceChanged(spaceNow()?.id, made.space)) await resetSpaceState();
  else await resetPerTaskState();
  homeData = null;
  currentTaskId = made.id; taskSwitchGen += 1;
  await refreshGitlab(made.id);
  await leaveHome();
}

/** «Назва й колір…»: лише імʼя й колір поточного простору (`POST /api/space-update`); теку міняти не можна. */
async function openSpaceEdit() {
  const cur = spaceNow();
  if (!cur) return;
  await askForm(
    () => spaceDialogHTML({ name: cur.name, color: cur.color }),
    {
      onMount: (form) => wireSpaceDialog(form, { mode: 'edit' }),
      focusBack: spaceDialogFocusBack,
      onSubmit: async (vals, ctl) => {
        const name = vals.name.trim();
        if (!name) { ctl.focus('name'); return t('spaceErrName'); }
        let saved;
        try { saved = await postForm('/api/space-update', { id: cur.id, name, color: vals.color }); }
        catch (e) {
          const field = spaceErrField(e.code);
          if (field) ctl.focus(field);
          return t(spaceErrKey(e.code));
        }
        applySpaceMeta(cur.id, saved);
        return undefined;
      },
    });
}

/** Нова назва й колір — у всі місця, що їх показують, БЕЗ перезавантаження макета (`render()` перезавантажив би рамку). */
function applySpaceMeta(id, { name, color }) {
  const patch = (x) => (x && x.id === id ? { ...x, name, color } : x);
  if (spacesResp?.spaces) spacesResp = { ...spacesResp, spaces: spacesResp.spaces.map(patch) };
  if (curTask?.space) curTask = { ...curTask, space: patch(curTask.space) };
  if (homeData?.space) homeData = { ...homeData, space: patch(homeData.space) };
  paintBar();
  if (homeOpen) paintHome();
}

/**
 * «Нова задача» на екрані «Задачі»: назва + id (з назви, поки його не правили руками) →
 * `POST /api/task-new {id, title, space}` → задача стає поточною, виходимо з екрана.
 * `space` називаємо ЯВНО (поточний): без нього сервер пішов би в простір з інтеграціями
 * (потік dev-pipeline ЛІГА) і завів би «особисту» задачу в реєстр компанії.
 * Перелік зайнятих id — з усіх просторів (`?all=1`): id унікальний на машині. Він може
 * приїхати вже після відкриття форми — вона перерахує id, а відправка його дочекається.
 * Етап Д: форма стоїть у клітинці сітки (`openNewTaskCard`), а не діалогом; тіло відправки — тут, щоб його читали обидві
 * частини однаково. `ctx` — `{sp, withRepo, taken, trashIds}`; повертає текст помилки чи `undefined`.
 * Перехід до створеної задачі — ВСЕРЕДИНІ відправки: картку могли закрити, не дочекавшись кінця (Esc до клону не діє, але
 * екран може піти геть), а задачу вже створено, і екран лишився б без переходу.
 */
async function createTask(vals, ctl, { sp, withRepo, taken, trashIds }, isLive = () => true) {
  const key = taskFormError(vals, await taken, trashIds);
  if (key) { ctl.focus(taskErrField(key)); return t(key); }
  /* `vcs` — лише зі значенням: порожнє поле (чи самі пробіли) ключа в тілі не лишає, і задача бере типовий `repo` модуля. */
  const repo = withRepo ? String(vals.repo ?? '').trim() : '';
  /* `tags` — лише коли поле непорожнє (клієнт ріже по комах, решту правил перевіряє сервер: `bad-tags`). */
  const tags = parseTags(vals.tags);
  const body = { id: vals.id, title: vals.title.trim(), space: sp.id, ...(repo ? { vcs: { repo } } : {}), ...(tags.length ? { tags } : {}) };
  /* Сервер клонує, лише коли в тілі є `vcs` (форма шле його тільки зі значенням поля; без `from`) або коли простір з
     інтеграціями має роль `vcs` — профільний `gitlab` (`_task_new_write`: `if gitlab or (vcs and adopt_src is None)`), і то
     ТАКОЖ у ЛІГА з явним `git-sync` та порожнім полем; без ролі клону нема (`taskCreateClones`, spaces-model.js). Лише такий
     запит триває хвилини — довга стеля (`taskPost`) і рядок про клон мають сенс тільки йому. Порожнє поле у звичайному
     просторі, простір без синку — миттєвий запит (`postForm`, 20 с) без жодних ознак. Довгому Esc і «Скасувати» не діють
     (запит однаково долетить і задача зʼявиться), тож форма мусить сказати, що вона жива. */
  const clones = taskCreateClones(sp, body);
  let made;
  const stopWait = clones ? showCreateWait(ctl.form) : null;
  try { made = await (clones ? taskPost(body) : postForm('/api/task-new', body)); }
  catch (e) {
    stopWait?.(true);
    const key2 = taskErrKey(e.code);
    const field = taskErrField(key2);
    if (field) ctl.focus(field);
    const why = requestErrText(e);
    /* Адресу, гілку й теку відхиляє `validate` модуля: загальний текст про адресу + причина сервера другим рядком (дані — як
       текст у слоті помилки, не розмітка). Решта відмов без свого ключа (коди каркаса й постачальника, коли тіло несло `vcs`;
       завжди — `check-timeout`/`module-error`/`vcs-error`): «Не вдалося: <причина>» без підсвітки. */
    if (key2 === 'taskErrVcsTarget') return why ? `${t(key2)}\n${t('taskErrWhy', why)}` : t(key2);
    return taskErrShowsReason(e.code, 'vcs' in body) ? t('errFailed', why) : t(key2);
  }
  stopWait?.(false);
  /* Клон міг тривати хвилини, а людина — піти: відкрила іншу задачу, змінила простір, зайшла в «Команду». Форма вже не жива —
     задачу створено, але НЕ перехоплюємо навігацію: ні скидання поточної задачі чи простору, ні `leaveHome`; лише тост. */
  if (!isLive()) {
    homeData = null;
    toast(t('taskCreatedBg', body.title));
    return undefined;
  }
  /* Нова задача — поточна: усе пер-задачне попереднього чуже. Простір відповіді
     порівнюємо з відомим, як у `switchTask`. `homeData` — застарілий (задачі в
     ньому ще нема), тож не показуємо його при наступному вході. */
  try {
    if (spaceChanged(sp.id, made.space)) await resetSpaceState();
    else await resetPerTaskState();
    homeData = null;
    currentTaskId = made.id; taskSwitchGen += 1;
    await refreshGitlab(made.id);
    await leaveHome();
  } catch (e) { toast(t('errFailed', e.message)); }
  return undefined;
}

/** Підказка репозиторію: типовий `repo` з налаштувань увімкненого модуля ролі `vcs` (`GET /api/modules`); приїздить ПІСЛЯ
 *  відкриття (форма не чекає мережі), збій запиту — без підказки. Лише там, де є поле «Репозиторій». */
function mountRepoHint(form, sp, withRepo) {
  if (!withRepo) return;
  api(`/api/modules?space=${encodeURIComponent(sp.id)}`).then((r) => {
    const m = (r?.modules || []).find((e) => e.enabled === true && (e.roles || []).includes('vcs'));
    return m?.settings?.find((x) => x.key === 'repo')?.value || '';
  }).catch(() => '').then((hint) => {
    const field = form.querySelector('#tf-repo');
    /* Жива, а не «підключена»: на «Команді» чи в кошику форма законно відчеплена від DOM, але ще потрібна. */
    if (hint && field && newFormEl === form) field.setAttribute('placeholder', hint);
  });
}

/** Етап Д: картка «+» стає формою на місці. Жива `<form>` (`newFormEl`) тримається ПОЗА сіткою й вставляється в слот після
 *  кожної перемальовки (`mountNewForm`): сітка перемальовується через `innerHTML`, і набране інакше зникло б. */
async function openNewTaskCard() {
  const sp = spaceNow();
  if (!sp || homeEdit.newForm) return;
  /* Необовʼязкове поле «Репозиторій» (4a): лише у звичайному просторі з роллю `vcs`. У ЛІГА ціль синку живе в `tasks.json`
     (профіль задачі), тож форма там без поля. */
  const withRepo = hasVcs(sp) && !isLegacyVcs(sp);
  const taken = formApi('/api/tasks?all=1').then((r) => (r.tasks || []).map((x) => x.id)).catch(() => []);
  /* Ідентифікатори з кошика: їх займає запис кошика (повернення вимагає вільного id) — автопідстановка їх обходить. */
  const trashIds0 = (homeData?.trash || []).map((x) => x.id);
  const tpl = document.createElement('template');
  tpl.innerHTML = taskFormHTML({ inline: true, tags: true, ...(withRepo ? { repo: {} } : {}) }).trim();
  const form = tpl.content.firstChild;
  newFormEl = form;
  newFormCtx = { sp, withRepo, taken };
  wireTaskForm(form, { taken: taken.then((ids) => [...ids, ...trashIds0]) });
  /* Форма жива, поки вона — поточна форма відкритого екрана «Задачі». */
  const isLive = () => newFormEl === form && homeOpen && homePage === 'tasks';
  const ctl = makeFormCtl(form);
  let busy = false;
  form.addEventListener('input', () => ctl.error(''));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (busy) return;
    busy = true; ctl.busy(true); ctl.error('');
    try {
      /* Кошик — на момент відправки, не відкриття: за цей час задачу могли видалити чи повернути. */
      const trashIds = (homeData?.trash || []).map((x) => x.id);
      const msg = await createTask(formValues(form.elements), ctl, { ...(newFormCtx ?? { sp, withRepo, taken }), trashIds }, isLive);
      if (msg) ctl.error(msg);
      else {
        // задачу створено: форма не лишається в схованому DOM
        if (newFormEl === form) resetHomeEdit();
        form.remove();
      }
    } catch (e) {
      ctl.error(t('errFailed', requestErrText(e)));
    } finally { busy = false; ctl.busy(false); }
  });
  form.addEventListener('click', (ev) => { if (ev.target.closest('[data-a="cancel"]') && !busy) closeNewTaskCard(); });
  homeEdit = { ...homeEdit, newForm: true, ask: null, ren: null };
  paintHomeLower();
  form.querySelector('#tf-title')?.focus({ preventScroll: false });
  mountRepoHint(form, sp, withRepo);
}

/** Закрити форму: картка «+» вертається, фокус — на неї. */
function closeNewTaskCard() {
  homeEdit = { ...homeEdit, newForm: false };
  newFormEl = null; newFormCtx = null;
  paintHomeLower();
  homeNode()?.querySelector('[data-th="newtask"]')?.focus({ preventScroll: true });
}

/**
 * «Мітки» на картці «Моїх» (`data-th="tags"`, 4b-3): діалог з одним полем, заповненим поточними мітками задачі →
 * `POST /api/task-tags {id, tags}` (сервер сам знаходить простір, де лежить задача) → мітки в рядку екрана оновлюються на місці.
 * Мітки беремо з рядка `homeData.mine` (це те, що людина бачить на картці, включно з похідною міткою ЛІГИ): збереження
 * замінює їх власними. Помилка `bad-tags` — текст під полем, діалог лишається; будь-яка інша (задачу вилучено — 404, id у двох
 * просторах — 409, мережа) — тост, діалог закривається.
 * ⛔ Після збереження чистимо `pruneFilters`: прибрали останню задачу з вибраною міткою — фільтр без чипа лишив би екран
 * порожнім і невидимо для людини.
 */
async function editTaskTags(id) {
  const row = (homeData?.mine || []).find((y) => y.id === id);
  if (!row) return;
  await askForm(() => tagsFormHTML({ value: (row.tags || []).join(', ') }), {
    focusBack: () => homeNode()?.querySelector(`[data-th="tags"][data-id="${CSS.escape(id)}"]`),
    onSubmit: async (vals, ctl) => {
      let saved;
      try { saved = await postForm('/api/task-tags', { id, tags: parseTags(vals.tags) }); }
      catch (e) {
        if (e.code === 'bad-tags') { ctl.focus('tags'); return t(taskErrKey(e.code)); }
        toast(t('errFailed', requestErrText(e)));
        return undefined;
      }
      /* Екран міг змінитись, поки запит летів (інший простір, перечитані дані): правимо ті дані, що є зараз, і лише рядок цієї задачі. */
      if (homeReady() && Array.isArray(saved?.tags)) {
        homeData = { ...homeData, mine: homeData.mine.map((y) => (y.id === id ? { ...y, tags: saved.tags } : y)) };
        if (pruneFilters(homeUi, homeData)) saveHomeUi();
        if (homeOpen) paintHome();
      }
      return undefined;
    },
  });
}

/**
 * Ім'я дії (`data-act`) → функція. Делегація нижче кличе `BAR_ACTIONS[act]`
 * з `(val, el, ev)` — значенням контролу (`data-val`, де є), самим
 * DOM-елементом і подією. Тіла, перенесені зі старої смуги (`mode`, `view`,
 * `vp`, `publish`), лишають ЛОГІКУ й коментарі про вже виправлені баги без
 * змін — переписати їх заново означало б повернути ці баги.
 * Нові тіла (перемикання задачі, дії над ітерацією в її дропдауні, GitLab-
 * дропдаун, публікація-дропдаун) написані для Task 3, бо в старій смузі цих
 * контролів не було зовсім — їхня логіка складена з того, що вже робили
 * `pillMenu`/`#pp-newit`/`paintGitlab`/`#pp-copy` (перенесене СЮДИ, а не
 * звідти: `renderPanel()` — межа Task 4, її тіло не чіпаємо).
 */
/* ===== Панель «Коментарі» (0.26.0) ===== */

/** Живий коментатор поточного виду або `null` (ще вантажиться / виду нема). */
function cmtLayer() {
  if (mode === 'canvas') return ovc.layer || null;
  if (!frameCmtReady) return null;
  try { return frame.contentWindow?.CommentLayer || null; } catch (e) { return null; }
}
/** Інструмент коментатора поточного виду (`CommentLayer.tool()`, поправка 19) або `null`. Читаємо в `paintComments`, куди
 *  сходяться `ready`/`mode`/`change`, перемикання виду, відкриття панелі й втрата шару, — тож він ніколи не застаріває. */
function readTool(L) {
  try {
    const v = L && typeof L.tool === 'function' ? L.tool() : null;
    return v && Array.isArray(v.modes) ? { mode: String(v.mode), freeze: !!v.freeze, modes: v.modes.slice(), canFreeze: !!v.canFreeze } : null;
  } catch (e) { return null; }
}
/** Текст банера `__clDown` у рамці (коментатор не піднявся) — у панель, щоб людина бачила причину. */
function cmtDown() {
  if (mode === 'canvas') return null;
  try { return frame.contentDocument?.getElementById('cl-down')?.textContent || null; } catch (e) { return null; }
}
/* Клік повз питання в картці — «ні» (етап В). Capture: спрацює раніше за будь-який інший клік, що перемалює панель, а клік по
   іншій кнопці картки після цього відпрацює як звичайно. Клік у макеті (iframe) сюди не долітає — питання лишається,
   нічого не видаляючи. */
document.addEventListener('click', (ev) => {
  if (cmtDelAsk && !ev.target.closest?.('.cmt-acts--cfm')) { cmtDelAsk = null; paintComments(); }
}, true);
/* Клік у макет — це клік в iframe: до `document` він не долітає, зате вікно оболонки втрачає фокус. Фокус пішов у рамку —
   питання знімається, нічого не видаляючи (та сама ідея, що в поповері `ask.js`). */
window.addEventListener('blur', () => setTimeout(() => {
  if (cmtDelAsk && document.activeElement?.tagName === 'IFRAME') { cmtDelAsk = null; paintComments(); }
}, 0));
/** Зняти питання «Видалити назавжди?»; `refocus` — повернути фокус на кошик тієї картки (Esc, «Скасувати»), а не лишати на `body`. */
function closeDelAsk(refocus) {
  const id = cmtDelAsk;
  cmtDelAsk = null;
  paintComments();
  if (refocus && id) cmtEl.querySelector(`[data-act="cmtdel"][data-val="${CSS.escape(id)}"]`)?.focus();
}
function paintComments() {
  const html = cmtOpen && !homeOpen ? commentsPanelHTML({ snapshot: cmtSnap, query: cmtQuery, selectedId: cmtSel,
    editingId: cmtEditing, delAsk: cmtDelAsk, expanded: cmtExpanded, filter: cmtFilter, dual: !noTeamComments(), teamDown: cmtTeamDown,
    fresh: cmtFresh, down: cmtSnap ? null : cmtDown() }) : '';
  cmtTool = cmtOpen && !homeOpen ? readTool(cmtLayer()) : null;
  /* Фокус і каретку поля пошуку / редагування — назад після перезапису (той самий прийом, що в `paintInsp`). */
  const act = document.activeElement;
  const cfmSel = act && cmtEl.contains(act) && act.closest('.cmt-acts--cfm')
    ? `.cmt-acts--cfm .${act.classList.contains('cfm-yes') ? 'cfm-yes' : 'cfm-no'}` : null;   // фокус на кнопці питання «Видалити назавжди?»
  const keep = act && cmtEl.contains(act) && (act.id === 'cmt-q' || act.classList.contains('cmt-edit'))
    ? { sel: act.id === 'cmt-q' ? '#cmt-q' : '.cmt-edit', range: [act.selectionStart, act.selectionEnd] }
    : (cfmSel ? { sel: cfmSel, range: [0, 0] } : null);
  const top = cmtEl.querySelector('.cmt-body')?.scrollTop || 0;
  cmtEl.hidden = !html;
  const wasWith = document.body.classList.contains('with-cmt');
  document.body.classList.toggle('with-cmt', !!html);
  /* Панель стискає полотно БЕЗ події `resize` вікна, а коментатор «Огляду» міряє габарит лише на ній: стара ширина
     збивала б переліт до піна (центр — не центр видимого полотна). */
  if (wasWith !== !!html && mode === 'canvas') ovc.remeasure();
  cmtEl.innerHTML = html;
  const body = cmtEl.querySelector('.cmt-body');
  if (body && top) body.scrollTop = top;
  /* Чернетка редагування: шаблон малює textarea зі ЗБЕРЕЖЕНИМ текстом, а знімок коментатора приходить і сам (збереження
     піна, збагачення) — без цього набране мовчки поверталось би до старого. Тримаємо в `cmtDraft` (оновлює `input`). */
  if (cmtEditing && cmtDraft != null) { const ed = cmtEl.querySelector('.cmt-edit'); if (ed) ed.value = cmtDraft; }
  if (keep) {
    const el = cmtEl.querySelector(keep.sel);
    el?.focus(); try { el?.setSelectionRange(...keep.range); } catch (e) {}
  }
  if (cmtSel) cmtEl.querySelector(`[data-cid="${CSS.escape(cmtSel)}"]`)?.scrollIntoView({ block: 'nearest' });
  paintIsland();
}
/** Імʼя автора цього вікна — те, що пише коментатор (той самий origin); нема — «мого» нема (поправка 15). */
const myName = () => { try { return localStorage.getItem('comment-layer:user') || ''; } catch (e) { return ''; } };
const cmtSeenKey = () => seenKey(spaceNow()?.id, currentTaskId);
function loadSeen(key) { try { return readSeen(localStorage.getItem(key)); } catch (e) { return null; } }
function saveSeen(key, set) { try { localStorage.setItem(key, writeSeen(set)); } catch (e) {} }
/** Причина падіння командного з комбінованого сховища шару (`DeaiDualStore.teamDown`), або `null`. */
function readTeamDown(L) { try { const v = L && L.store && L.store.teamDown; return typeof v === 'string' && v ? v : null; } catch (e) { return null; } }
/** Свіжість локальних (Б2.1): комбіноване сховище перечитує локальні піни з диска (їх міг дописати Claude).
 *  Під екраном «Задачі» — тиша: макет схований, а вихід (`leaveHome` → `render()`) однаково перезавантажує рамку. */
const cmtRefreshLocal = () => { if (homeOpen) return; try { const st = cmtLayer()?.store; (st?.refreshLocal || st?.refresh)?.call(st); } catch (e) {} };
/** Знімок коментатора поточного виду змінився: маркер, свіжі, число острівця, дерево, тост. */
let cmtNewsTask = null;
let cmtNewsPagesKey = '{}';
function cmtNewsUpdate() {
  if (cmtNewsTask !== currentTaskId) { cmtNewsTask = currentTaskId; cmtFresh.clear(); cmtPrevIds = null; dropNotice('cmt-news'); }
  const all = cmtSnap && Array.isArray(cmtSnap.comments) ? cmtSnap.comments : null;
  if (!all || !currentTaskId) { cmtNewsN = 0; cmtNewsPages = {}; cmtNewsTree(); return; }
  const team = teamOf(all);
  const key = cmtSeenKey();
  let seen = loadSeen(key);
  /* Командного нема (впав чи не заведений) — знімок без команди порожній: базова лінія з нього зробила б «новими» усіх колег,
     коли команда повернеться. Маркер лишаємо незаданим: першим базовим стане перший справжній знімок команди. */
  if (!seen) { seen = baseline(team); if (!cmtTeamDown && !noTeamComments()) saveSeen(key, seen); }
  const fresh = team.filter((c) => isNew(c, seen, myName()));
  const came = arrived(cmtPrevIds, fresh);
  cmtPrevIds = new Set(all.map((c) => c.id));
  if (cmtOpen) {
    for (const c of fresh) cmtFresh.add(c.id);
    if (fresh.length) saveSeen(key, markSeen(seen, fresh.map((c) => c.id)));
    cmtNewsN = 0; cmtNewsPages = {};
    cmtNewsTree();
    return;
  }
  cmtNewsN = fresh.length;
  cmtNewsPages = newsByPage(fresh);
  cmtNewsTree();
  if (came.length) newsToast(came);
}
/** Число «нових» у дереві сторінок — перемальовуємо дерево лише коли воно справді змінилось. */
function cmtNewsTree() {
  const k = JSON.stringify(cmtNewsPages);
  if (k === cmtNewsPagesKey) return;
  cmtNewsPagesKey = k;
  if (curTask) renderPanel();
}
/** Вибір вкладки фільтра панелі: лише значення з FILTERS; памʼятається в `dc-cmt-filter`; перемальовує панель. */
function setCmtFilter(f) {
  if (!FILTERS.includes(f)) return;
  cmtFilter = f;
  try { localStorage.setItem('dc-cmt-filter', f); } catch (e) {}
  paintComments();
}
function newsToast(came) {
  const last = came[came.length - 1];
  notice('cmt-news', came.length === 1 ? t('cmtNewToast', last.author || '—') : t('cmtNewToastN', came.length), [{
    act: 'cmtshownew', label: t('cmtShowNew'),
    /* Новини — завжди командні: на «Для Claude» їх (недорученими) не видно, тож «Показати» веде на «Команду». */
    run: () => { dropNotice('cmt-news'); if (cmtFilter === 'local') setCmtFilter('project'); setCommentsOpen(true); cmtSel = last.id; paintComments(); cmtLayer()?.focus(last.id); },
  }]);
}
function setCommentsOpen(on) {
  on = !!on;
  /* Інспектор і коментарі — взаємно виключні: обидва ділять праву панель і обидва ловлять клік по макету. */
  if (on) { const api = inspectorApi(); if (api?.on) { api.set(false); paintBar(); } }
  cmtOpen = on;
  if (!on) { cmtSel = null; cmtEditing = null; cmtDraft = null; cmtDelAsk = null; cmtFresh.clear(); }
  else {
    /* Маркер «бачив» посуваємо ОДРАЗУ на відкритті: нові стають розділом «Нові від команди» цього відкриття (поправка 13). */
    const key = cmtSeenKey();
    const seen = loadSeen(key) || new Set();
    const fresh = teamOf(cmtSnap?.comments).filter((c) => isNew(c, seen, myName()));
    fresh.forEach((c) => cmtFresh.add(c.id));
    if (fresh.length) saveSeen(key, markSeen(seen, fresh.map((c) => c.id)));
    cmtNewsN = 0; cmtNewsPages = {}; cmtNewsTree();
    dropNotice('cmt-news');
    cmtRefreshLocal();
  }
  const L = cmtLayer();
  if (L && !!L.commentMode !== on) L.setCommentMode(on);
  paintComments();
}
/** Вид (Макет ↔ Огляд) змінився: панель показує коментатора НОВОГО виду — знімок, вибране, редагування й чернетка старого
 *  не про нього (дії йшли б у чужий шар із чужими id). Коментатор рамки на «Огляді» мовчить (режим вимкнено), а на
 *  поверненні перезвімкнеться, якщо панель відкрита. Той самий вид (повторний `render`) — нічого не скидає. */
let cmtView = null;
function cmtViewSwitch() {
  if (cmtView === mode) return;
  const was = cmtView;
  cmtView = mode;
  cmtSel = null; cmtEditing = null; cmtDraft = null; cmtDelAsk = null;
  cmtFresh.clear(); cmtPrevIds = null; dropNotice('cmt-news');
  if (mode === 'canvas') {
    if (was) try { const FL = frame.contentWindow?.CommentLayer; if (FL?.commentMode) FL.setCommentMode(false); } catch (e) {}
    cmtSnap = ovc.layer ? ovc.layer.snapshot() : null;
    cmtTeamDown = readTeamDown(ovc.layer);
  } else {
    const L = cmtLayer();
    cmtSnap = L ? L.snapshot() : null;
    cmtTeamDown = readTeamDown(L);
    if (L && cmtOpen && !L.commentMode) L.setCommentMode(true);
  }
  cmtNewsUpdate();
  paintComments();
}
/** Рамка втратила свого коментатора (нова адреса, чужий документ, сторінка без нього): старі картки з мертвими діями
 *  не лишаємо — панель показує «завантажується/недоступно». `sel`: ще й скинути вибір/редагування/чернетку (id належать
 *  старому документу чи каналу). У «Огляді» `cmtSnap` — полотна, його не чіпаємо. */
function dropFrameCmt({ sel = false } = {}) {
  frameCmtReady = false;
  if (mode !== 'canvas') { cmtSnap = null; cmtTeamDown = null; }
  if (sel) { cmtSel = null; cmtEditing = null; cmtDraft = null; cmtDelAsk = null; cmtFresh.clear(); cmtPrevIds = null; dropNotice('cmt-news'); }
  paintComments();
}
/** Відкритий модальний шар оболонки (палітра/довідка, будь-який діалог `askForm`): клавіші C/H тоді не наші. */
/* Питання чи форма канваса відкриті: модальна картка (`.cv-ask-scrim`) АБО поповер біля кнопки (`.cv-ask-pop`, етап В).
   Поповер не затемнює макет, але клавіатура йому належить так само: нічого глобального під ним не реагує. */
const askUp = () => !!document.querySelector('.cv-ask-scrim, .cv-ask-pop');
const shellModalOpen = () => !!paletteOverlay || askUp() || !!document.querySelector('[aria-modal="true"]');
/** Подія коментатора: `src` — 'frame' чи 'canvas'; чужий вид — ігнор (поправка 11). */
function onCommentsEvent(src, m) {
  if ((src === 'canvas') !== (mode === 'canvas')) return;
  /* `ev.source` не відрізняє документів (WindowProxy переживає навігацію): запізніла посилка СТАРОЇ сторінки після
     скидання рамки не мусить повернути старих карток. Коментатор завжди шле `ready` до першого `change`. */
  if (src === 'frame' && !frameCmtReady && m.ev !== 'ready') return;
  if (m.ev === 'ready') {
    if (src === 'frame') frameCmtReady = true;
    const L = cmtLayer();
    if (L) { cmtSnap = L.snapshot(); cmtTeamDown = readTeamDown(L); if (cmtOpen) L.setCommentMode(true); }
    cmtNewsUpdate();
    paintComments();
  } else if (m.ev === 'change') {
    if (m.snapshot && Array.isArray(m.snapshot.comments)) { cmtSnap = m.snapshot; cmtNewsUpdate(); paintComments(); }
  } else if (m.ev === 'select') {
    cmtSel = typeof m.id === 'string' ? m.id : null;
    if (!cmtOpen) setCommentsOpen(true); else paintComments();
  } else if (m.ev === 'mode') {
    if (!m.on && cmtOpen) { cmtOpen = false; cmtSel = null; cmtEditing = null; cmtDraft = null; cmtDelAsk = null; paintComments(); }
    else if (m.on && !cmtOpen) { cmtOpen = true; paintComments(); }
  }
}
/* Посилки коментатора з рамки (режим хоста, `host=1`). Правило джерела:
   ⛔ `ev.source === frame.contentWindow` — інакше чужа сторінка підсунула б панелі фальшиві картки. Плюс
   `ev.origin === location.origin`: рамка, що пішла на чужий сайт, лишається тим самим вікном (`source` збігається),
   але її посилки — не наші. */
window.addEventListener('message', (ev) => {
  if (ev.source !== frame.contentWindow || ev.origin !== location.origin) return;
  const m = ev.data;
  if (!m || m.type !== 'dc-comments' || !CMT_EVENTS.has(m.ev)) return;
  onCommentsEvent('frame', m);
});
/* C і H — клавіші оболонки (поправка 4): коментатор у режимі хоста їх не слухає, тож ловимо й тоді, коли фокус у макеті. */
/** Поле вводу чи contenteditable — за СПРАВЖНІМ походженням події й за глибоким активним елементом: форма й редагування
 *  коментатора живуть у його shadow DOM, де `ev.target` на вікні рамки ретаргетиться на хост (DIV). Те саме робить
 *  інспектор (`deepTarget`/`activeDeep`/`isEditable` у `vendor/inspector.js`). */
function typingIn(ev, doc) {
  const isEd = (n) => !!n && n.nodeType === 1 && (/^(input|textarea|select)$/i.test(n.localName || '') || !!n.isContentEditable);
  const o = (typeof ev.composedPath === 'function' && ev.composedPath()[0]) || ev.target;
  let a = null;
  try {
    a = doc?.activeElement || null;
    while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  } catch (e) { a = null; }
  return isEd(o) || isEd(a);
}
const frameTyping = (ev) => typingIn(ev, frame.contentDocument);
function frameCmtKey(ev) {
  if (ev.metaKey || ev.ctrlKey || ev.altKey || ev.shiftKey || ev.repeat || ev.isComposing) return;
  if (frameTyping(ev) || shellModalOpen()) return;
  const k = (ev.key || '').toLowerCase();
  if (k === 'c' || ev.code === 'KeyC') { ev.preventDefault(); ev.stopPropagation(); BAR_ACTIONS.comments(); }
  else if ((k === 'h' || ev.code === 'KeyH') && cmtOpen) { ev.preventDefault(); ev.stopPropagation(); BAR_ACTIONS.cmtpins(); }
}
frame.addEventListener('load', () => {
  let w = null;
  try { w = frame.contentWindow; w.addEventListener('keydown', frameCmtKey, true); } catch (e) {
    dropFrameCmt(); // чужий документ: коментатора там нема, старі картки з мертвими діями не лишаємо
    return;
  }
  // Той самий origin, але сторінка без коментатора (перейшли на статичний файл): те саме.
  if (!w.CommentLayer) dropFrameCmt();
  /* Поправка 15: коментатор у `_focusElement` переходить на `meta.url` піна, а в пінів до 0.26.0 там нема `host=1` —
     рамка піднялась би без колбеків і з власною ручкою. Дописуємо `host=1` без запису в історію. */
  try {
    const loc = w.location;
    const q = new URLSearchParams(loc.search);
    if (loc.pathname === '/commented' && q.get('host') !== '1') {
      frameCmtReady = false; cmtSnap = null;
      /* `set`, а не дописування: при `host=0` чи `host=&…` другий `host=1` не перебив би першого (його й читає сервер) —
         рамка йшла б у нескінченне перезавантаження. */
      q.set('host', '1');
      loc.replace(`${loc.pathname}?${q}${loc.hash}`);
    }
  } catch (e) { /* чужий документ */ }
});

/** Увімкнути/вимкнути чистий перегляд (⇧⌘\\, палітра, кнопка повернення).
 *  Інспектор при вході вимикаємо: його оверлей у рамці — теж інтерфейс. */
function toggleClean(on = !cleanView) {
  cleanView = on;
  if (on) { const api = inspectorApi(); if (api?.on) api.set(false); }
  if (on && cmtOpen) setCommentsOpen(false);   // панель коментарів — теж інтерфейс, як і інспектор
  applyClean(document, frame, on, { label: t('cleanExit'), title: t('cleanExitTitle'),
    onExit: () => toggleClean(false), onChord: () => toggleClean() });
}
frame.addEventListener('load', () => syncFrame(frame, cleanView, () => toggleClean()));

/**
 * Переключення поточної задачі: `POST /api/task-switch` і скидання пер-задачного
 * стану. Віддає `true`, коли переключило, `false` — коли ні (причину вже показав
 * `tell`). Перемальовку НЕ кличе: кличе викликач — `BAR_ACTIONS.tab` робить
 * `render()`, а вихід з екрана «Задачі» (`homeOpenTask`) — `leaveHome()`, який
 * теж робить один `render()`; два рендери поспіль перезавантажили б рамку двічі.
 */
async function switchTask(val) {
  try {
    const sw = await post('/api/task-switch', { id: val });
    /* Увесь пер-задачний стан — ОДНИМ викликом (`resetPerTaskState`, його
       докстрінг): перелік того, що належить задачі, не сміє лежати в тілі
       кнопки, інакше другий вхід перепише половину. Це ЄДИНИЙ вхід до зміни
       задачі в браузері: і вкладки рядка вкладок, і картки екрана «Задачі» ідуть
       через цю функцію (⌘K «Задачі» веде на екран, а не міняє задачу сам), а
       `POST /api/task-new` (бутстрап Liga Design Office) канвас не кличе
       взагалі — його зміну поточної задачі вкладка бачить лише після
       перезавантаження, де `loadTune()` і так читає файл нової задачі.

       Задача може бути з ІНШОГО простору (сервер перемикає й простір: `task-switch`
       шукає по всіх): тоді відповідь називає інший `space`, і забути треба не лише
       задачу, а й усе, що належить простору (`resetSpaceState`, його докстрінг).
       Порівнюємо з тим, що ми знали (`spaceNow`), а не просто скидаємо завжди:
       перемикання в межах простору не має чистити кеш GitLab і мигати смугою. */
    if (spaceChanged(spaceNow()?.id, sw?.space)) await resetSpaceState();
    else await resetPerTaskState();
    /* Сервер уже перемкнено на `val`, а `curTask` ще старий і `picked` скинуто: статус питаємо про ЦІЛЬОВУ задачу, а не
       про ту, що відкрита (`glKeyNow`, його докстрінг). */
    await refreshGitlab(val);
    currentTaskId = val; taskSwitchGen += 1;
    if (homeReady()) homeData = { ...homeData, current: val };
    return true;
  } catch (e) { tellError(t('errTOpenTask'), e.message); return false; }
}

const BAR_ACTIONS = {
  /* Логотип → екран «Задачі» (`enterHome` нижче: смуга, клас на `body`, запит
     `/api/tasks-overview`). Логотип з «Підключення» теж веде на «Задачі» — тому сторінка названа явно: без
     неї `enterHome` лишив би відкриту. Відкрита панель «Підключення» з незбереженими змінами спершу питає
     «Відкинути зміни?» (`dismissCnDrawer`; під запитом панелі — ігнор), без панелі — як було, синхронно. На сторінці
     майстра (3b) логотип — те саме, що «Закрити майстер» (до створення — «Скасувати»): питає про незбережене кроку 3. */
  home: async () => { if (homeOpen && homePage === 'wiz') { await wiz.requestExit(); return; } if (cnDrawer && !(await dismissCnDrawer())) return; enterHome({ page: 'tasks' }); },
  /* Вкладка (0.25.0): та сама зміна задачі, що й скрізь (`switchTask`); з «Задач» — через `homeOpenTask`, який і виходить
     з оверлею. Відмова (нема теки, збій) — причину вже показано тостом, вкладка лишається. */
  tab: async (val) => {
    if (!val) return;
    if (homeOpen) { if (cnDrawer && !(await dismissCnDrawer())) return; await homeOpenTask(val); return; }
    /* Зміна задачі вже летить: ще один `task-switch` не запускаємо. Клік по цілі, що вже летить, скасовує чергу (людина
       передумала), клік по іншій — заміщає чергу; перемикаємо на ОСТАННЮ вибрану, коли поточне завершиться. */
    if (tabSwitch) { tabQueued = val === tabSwitch ? null : val; return; }
    if (val === currentTaskId) return;
    if (refuseMissingTask(val)) return;
    tabSwitch = val;
    try { if (await switchTask(val)) render(); }
    finally { tabSwitch = null; }
    const q = tabQueued; tabQueued = null;
    if (q && q !== currentTaskId) await BAR_ACTIONS.tab(q);
  },
  tabclose: async (val) => {
    const hadFocus = tabsEl.contains(document.activeElement);
    const at = tabs.findIndex((x) => x.id === val);
    const r = closeTab(tabs, val, homeOpen ? null : currentTaskId);
    tabs = r.tabs; saveTabs(); paintTabs();
    if (r.next === 'home') enterHome({ page: 'tasks' });
    else if (r.next) {
      await BAR_ACTIONS.tab(r.next);
      /* Перемикання на сусіда не відбулось (нема теки, збій): людина лишилась на цій задачі, тож її вкладку вертаємо
         одразу, а не чекаємо наступної перемальовки. */
      if (!tabSwitch && !homeOpen && val === currentTaskId && !tabs.some((x) => x.id === val) && curTask && curTaskList) {
        rememberTab(curTask, curTaskList);
      }
    }
    if (!hadFocus) return;
    /* Кнопка, що мала фокус, зникла разом із вкладкою: без цього фокус падає на `body`. Нова активна вкладка, інакше
       сусід на тому самому місці (чи остання), інакше логотип. */
    const btns = [...tabsEl.querySelectorAll('[data-act="tab"]')];
    const target = (r.next && r.next !== 'home' ? tabsEl.querySelector('[data-act="tab"][aria-current="page"]') : null)
      || btns[Math.min(at, btns.length - 1)] || tabsEl.querySelector('[data-act="home"]');
    target?.focus({ preventScroll: true });
  },
  tabnew: () => BAR_ACTIONS.home(),
  /* Шестерня → «Налаштування» (сторінка `conn`; вхід — `enterConnections`, як у ⌘K) з тим самим захистом незбереженого, що в `home`. */
  settings: async () => {
    if (homeOpen && homePage === 'wiz') { await wiz.requestExit(); return; }
    if (cnDrawer && !(await dismissCnDrawer())) return;
    enterConnections();
  },
  clean: () => toggleClean(),

  /* Простори (Deai 1.0, етап 1). `space` — рядок дропдауна фішки (`data-val` = id) і
     пункт ⌘K; `spacenew`/`spaceedit` — його ж футер і привітання. Розкриває дропдаун
     `data-dd="space"` (делегація нижче), а не ці дії: `data-act` закривав би його й
     одразу відкривав. Недоступний простір ПЕРЕМИКАЄМО теж: сервер перемикає реєстр, а
     причину («файл не читається») людина бачить смугою помилки після `render()` —
     єдиний спосіб її дізнатись, тому рядок такого простору лише приглушений. */
  space: async (val) => {
    if (!val || val === spaceNow()?.id) return;
    try { await post('/api/space-switch', { id: val }); }
    catch (e) { tellError(t('errTSpaceSwitch'), e.message); return; }
    await afterSpaceChange();
  },
  spacenew: () => openWizard(),
  spaceedit: () => openSpaceEdit(),
  /* «Підключення» поточного простору (етап 3a): пункт дропдауна фішки, ⌘K і кнопка в голові «Задач». */
  conn: () => enterConnections(),

  mode: async (val) => {
    const wantCanvas = val === 'overview';
    if (wantCanvas === (mode === 'canvas')) return;
    mode = wantCanvas ? 'canvas' : 'single';
    /* Перемикач — НЕ побічна перебудова: людина свідомо вийшла з полотна (або
       вернулась на нього) і чекає побачити все спочатку, а не кадр, у якому
       колись зумнулась. Забути світ треба саме тут: `buildCanvas` переносить
       камеру, поки задача, ітерація й вид ті самі, а вихід і вхід їх не міняють,
       тож без цього рядка «зумнувся → вийшов → вернувся» віддавало б старий кадр
       (перевірка D).

       І саме тут, а НЕ в гілці виходу `applyMode`. Причина СТРУКТУРНА: обробник
       обнуляє світ на КОЖНОМУ кліку незалежно від напрямку, тож на момент
       `buildCanvas` `camWorld` вже `null` за будь-якого переплетення — і коли
       обидва кліки випереджають рендери, і коли повільний сценарій дає
       `render()` побачити `mode === 'single'`. Гілка ж виходу `applyMode`
       спрацьовує лише в другому. Ілюстрація виміром: два кліки поспіль (вийшов і
       одразу назад) не дають жодному `render()` побачити `single` — перший
       долітає до `applyMode` уже після другого кліку, тобто обидва йдуть гілкою
       канваса, і обнулення в `applyMode` лишало D червоною на scale 0.4138
       замість fit 0.3841.

       Єдина точка входу в «Огляд» — цей обробник (вийти можна ще кліком по
       кадру, але вернутись лише сюди), тому другого місця з `camWorld = null` не
       треба: воно було б тим самим дублем, який щойно прибрано з `saveNodePos`. */
    camWorld = null;
    if (mode === 'canvas') { await freshen(); maybeAutoShoot(); }
    render();
  },

  view: (val) => {
    if (val === canvasView) return;
    canvasView = val;
    render();
  },

  /* Пресет — це просто ширина, тому окремої гілки «пресет проти свого числа»
     немає. А от гілка ПО ВИДУ є, і вона несуща: у робочому виді ширина лягає у
     стиль рамки й коштує нуль, у «Огляді» вона міняє ключі кадрів і може
     запустити браузерний прогін. Один жест, дві різні ціни — дві точки входу.
     Пресети теж різні: у полотні «Десктоп» — ЧИСЛО (`CANVAS_PRESETS`), бо вікна,
     ширину якого можна взяти, там немає. */
  vp: (val) => {
    const canvas = mode === 'canvas';
    const p = (canvas ? CANVAS_PRESETS : PRESETS).find((x) => x.id === val);
    if (!p) return;
    if (canvas) { setCanvasViewport(p.w); return; }
    setViewport(p.w);
  },

  // Інспектор живе ВСЕРЕДИНІ iframe (він оверлей на макеті), а кнопка — тут, у
  // смузі: у макеті вона заважала й губилась серед його ж інтерфейсу. Керуємо
  // ним напряму — iframe тієї самої origin. На bird-view кнопки немає взагалі:
  // там макети вантажаться bare=1 з pointer-events:none, інспектора там нема.
  /* Панель «Коментарі» (0.26.0): дії над живим коментатором поточного виду (`cmtLayer()`); знімок вертає `change`. */
  comments: () => { if (!homeOpen && !cleanView) setCommentsOpen(!cmtOpen); },
  cmtshow: (id) => { cmtSel = id; cmtLayer()?.focus(id); paintComments(); },
  cmtres: (id) => { cmtLayer()?.resolveComment(id); },
  cmtreopen: (id) => { cmtLayer()?.reopenComment(id); },
  /* Кошик (етап В): спершу питання в картці, видаляє лише явне «Видалити». `{ confirmed: true }` — оболонка спитала сама,
     коментатор не показує браузерний `confirm()`. */
  cmtdel: (id) => { cmtDelAsk = id; paintComments(); cmtEl.querySelector('.cmt-acts--cfm .cfm-no')?.focus(); },
  cmtdelyes: (id) => { if (cmtDelAsk !== id) return; cmtDelAsk = null; cmtLayer()?.removeComment(id, { confirmed: true }); paintComments(); },
  cmtdelno: () => closeDelAsk(true),
  cmtedit: (id) => { cmtEditing = id; cmtDraft = null; paintComments(); cmtEl.querySelector('.cmt-edit')?.focus(); },
  cmteditsave: (id) => {
    const ta = cmtEl.querySelector('.cmt-edit');
    if (cmtLayer()?.editComment(id, ta?.value)) { cmtEditing = null; cmtDraft = null; }
    paintComments();
  },
  cmteditcancel: () => { cmtEditing = null; cmtDraft = null; paintComments(); },
  cmtcarry: (id) => { cmtLayer()?.carry(id); },
  cmtshot: (id) => { cmtLayer()?.openShot(id); },
  cmtsec: (k) => { if (k in cmtExpanded) { cmtExpanded[k] = !cmtExpanded[k]; paintComments(); } },
  cmtfilter: (f) => setCmtFilter(f),
  cmtassign: (id) => { cmtLayer()?.setMeta?.(id, { assignee: 'claude' }); },
  cmtunassign: (id) => { cmtLayer()?.setMeta?.(id, { assignee: null }); },
  cmtpins: () => { cmtLayer()?.togglePins(); },
  /* Режими й заморозка коментатора — в острівці (поправка 19); `data-val` — режим. */
  cmtmode: (m) => { const L = cmtLayer(); if (L && typeof L.setMode === 'function' && L.setMode(m)) { cmtTool = readTool(L); paintIsland(); } },
  cmtfreeze: () => { const L = cmtLayer(); if (cmtTool && L && typeof L.setFreeze === 'function' && L.setFreeze(!cmtTool.freeze)) { cmtTool = readTool(L); paintIsland(); } },

  inspector: () => {
    const api = inspectorApi();
    if (!api) return;                    // макет ще вантажиться
    if (!api.on && cmtOpen) setCommentsOpen(false);   // коментарі й інспектор — взаємно виключні
    api.set(!api.on);
    // Легка перемальовка замість `syncInspectorBtn`: та сама причина, що й
    // нижче в `frame`-обробнику завантаження — контрол іноді живе ще й
    // дублікатом у «⋯», і саме перемальовка ту другу копію теж підсвічує.
    // Той самий рядок гасить і панель (Task 5 Плану B): `paintBar()` кличе
    // `paintInsp()` усередині себе, тож ОДНА кнопка — «інспектор увімкнено» —
    // і в смузі, і в панелі лишається одним рішенням, а не двома.
    paintBar();
  },

  /* Крихта предка. Індекс резолвить САМ оверлей (`pinAt`): масив предків
     живий лише там, і передавати сюди елементи означало б дати панелі
     другий шлях до DOM макета. */
  inspcrumb: (val) => {
    inspectorApi()?.pinAt(val);
    paintInsp();
  },

  /* Поле панелі властивостей. Застосування — на Enter і на `change` (див. слухачі панелі нижче), не на кожну
     літеру: «Enter застосовує, Esc скасовує» (спека, розділ «Поле»). Усі шляхи ведуть в ОДИН `tuneSet` через
     `tuneWrite`: «накрутити» — одна дія, чим би її не зробили, і різні шляхи до інлайн-стилю розійшлися б у тому,
     що записано в пакет. `paintInsp()` тут не кличемо: панель перемальовує сам оверлей (`_tuned` → `_emit` →
     `onChange`), і другий виклик означав би дві перемальовки на одну правку. */
  insptune: (val, el) => inspCommit(el),
  insptunecolor: (val, el) => inspCommit(el),
  /* Кнопка «до ДС»: пише правку зі `snap` у КОЖНУ властивість поля (пара — дві). Повернення до токена мусить лягти
     в пакет тим самим шляхом, що будь-яка правка; відрізняє його лише `snap` — він каже читачеві, що вибрано ТОКЕН. */
  inspsnap: (val, el) => tuneWrite(String(el.dataset.props || el.dataset.prop).split(' ')
    .map((p) => [p, el.dataset.val, { token: el.dataset.token, value: el.dataset.val }])),
  /* «N поза ДС»: фокус на наступне бурштинове поле по колу. Курсор — модульна змінна, а не `activeElement`: клік по
     самій кнопці забирає фокус, і «наступне від активного» щоразу давало б перше. */
  inspnextoff: () => {
    const list = [...inspEl.querySelectorAll('.insp-f[data-off]')];
    if (!list.length) return;
    inspOffAt = (inspOffAt + 1) % list.length;
    const f = list[inspOffAt].querySelector('.insp-fi');
    f?.focus();
    f?.scrollIntoView?.({ block: 'nearest' });
  },
  inspalign: (val, el) => {
    const [c, r] = String(val).split(',').map(Number);
    tuneWrite(alignWrites(el.dataset.dir, c, r));
  },
  inspdir: (val) => tuneWrite([['flex-direction', val === 'column' ? 'column' : 'row']]),
  /* «+»: заливка пише `background-color`; обведення — три довгі властивості (рядка `border` у звіті немає). Токен, якщо
     колір узято з ДС, їде як `snap` (читач пакета бачить, що вибрано ТОКЕН). */
  inspadd: (val, el) => {
    const color = el.dataset.color || '';
    if (!/^#[0-9a-fA-F]{6}$/.test(color)) return;
    const snap = el.dataset.token ? { token: el.dataset.token, value: color } : null;
    if (val === 'fill') tuneWrite([['background-color', color, snap]]);
    else if (val === 'stroke') tuneWrite([['border-style', 'solid'], ['border-width', '1px'], ['border-color', color, snap]]);
  },
  inspsides: () => { inspSides = !inspSides; paintInsp(); },

  /* Ручки ПІДВАЛУ (Task 15, переїхав у T-39). Тіла — у `tuneDrop`/
     `tuneDropAll`/`tuneNote`/`tuneReady` поруч із `tuneSet`: усе, що міняє
     модель тюнера, лежить в одному місці, інакше «скинути» з двох різних
     поверхонь розійшлося б у тому, що саме лишається на макеті.
     `data-sel` — ключ ЕЛЕМЕНТА, `data-prop` — властивість: у списку змін
     нічого не запінено, тож адресувати правку більше нічим.

     ⛔ `insptuneoff` (скидання ОДНІЄЇ правки з рядка звіту) тут більше немає:
     разом із перекресленим «було» пішла й кнопка, якою те «було» й було.
     Скидання однієї правки лишилось РІВНО одне — хрестик у списку змін
     (`insptunedrop`), і це не втрата дії, а зникнення другого входу в неї. */
  insptunedrop: (val, el) => tuneDrop(el.dataset.sel, el.dataset.prop),
  insptuneall: () => tuneDropAll(),
  insptunenote: (val, el) => tuneNote(el.value),
  insptuneready: () => tuneReady(),

  publish: async (val, el) => {
    const lbl = el.querySelector('.lbl-pub');
    const prevText = lbl ? lbl.textContent : null;
    el.disabled = true;
    if (lbl) lbl.textContent = t('publishBusy');
    /* Публікація Vercel триває хвилини, і людина встигає перейти на іншу задачу чи в інший простір. Тому «хто, де й чия» захоплюється
       ДО запиту: рішення «ЛІГА чи модуль» — за простором ВИКЛИКУ (`sp0`), а не поточним (інакше модульна відповідь у ЛІГА-просторі нової
       задачі не давала б жодного підтвердження, а ЛІГА-відповідь у модульному — чужу плашку), і плашка з `render()` належать лише
       задачі, з якої публікували (`sameTask`); на іншій — короткий тост із назвою (`publishReaction`). */
    const t0 = currentTaskId;
    const sp0 = spaceNow();
    const label0 = curTask ? (curTask.jira || curTask.id || '') : '';
    const sameTask = () => currentTaskId === t0 && !spaceChanged(sp0?.id, spaceNow()?.id);
    try {
      const r = await post('/api/publish', {});
      // Обгортку превʼю збирає САМ сервер у момент публікації, тому правка в
      // app/*.py доїжджає на зовнішній URL лише після перезапуску канваса й
      // ПОВТОРНОЇ публікації. Сервер порівнює mtime свого коду з часом старту —
      // показуємо ГОЛОСНО і ДО решти реакції: на успішному деплої далі йде лише
      // render() з раннім return, і попередження не було б видно ніде
      // (фідбек 25.08.2026). Текст приходить з сервера — тому без t().
      /* Превʼю спільної задачі — у ВЛАСНИКА (рішення 29.09.2026): з чужої машини
         публікація йде у СВОЄ превʼю, і це треба сказати вголос, інакше
         дизайнер роздає менеджеру посилання, яке задачею не є. Домен із
         суфіксом — той самий клас з боку Vercel (fb-29092026-210ec1). Усе
         одним вікном: кілька `tell` підряд лягли б одне на одне. */
      /* Коментарі до превʼю не додано (модуль коментарів недоступний, 2b-2): публікація вдалась, але в превʼю їх нема —
         без цього рядка людина роздала б посилання й шукала б причину в консолі глядача. Код — з моделі (лише безпечні
         символи), текст — зі словника. */
      const cmtCode = commentsUnavailableCode(r);
      const warn = [r.code_stale,
        r.not_task_link && r.url ? t('publishNotTaskLink', r.not_task_link, r.url) : null,
        r.domain_warning,
        cleanupWarning(r),
        cmtCode ? t('publishCommentsUnavailable', cmtCode) : null].filter(Boolean);
      if (warn.length) tell(warn.join('\n\n'));
      const view = publishReaction(r, sp0, sameTask());
      /* Людина вже на іншій задачі: тост із назвою — і ВСЕ. Ні `render()`, ні плашки: вони належали б новій задачі. */
      if (view.show === 'toast') { toast(t(view.key, label0)); return; }
      /* ЛІГА (зашитий код) — рівно як було: лише `render()`. */
      if (view.kind === 'legacy') { render(); return; }
      if (view.kind === 'remote') {
        /* Модуль «за адресою» (Vercel, 2b-1): відповідь має `url` і не має `local`. Спершу оновлюємо задачу —
           сервер у ній уже склав `publish_share_url` (з фрагментом-паролем, коли превʼю з паролем), і обидві кнопки
           беруть посилання звідти: UI його не складає. Збій перемальовки — не збій публікації (вона вдалась): без
           `try` він потрапив би в `catch` нижче й показав «Не вдалося» без плашки. Плашка стійка (`notice`), бо тост за
           3 с зникав би раніше, ніж людина встигне натиснути; її гасить `resetPerTaskState`. «Відкрити» веде на посилання з
           паролем (власник не впирається в гейт), але лише коли воно безпечне (`remoteOpenUrl`: https, без облікових даних,
           ASCII), `noopener` — щоб відкрита сторінка не мала `window.opener`. Попередження модуля (`warnings`) чи
           нейтральна підказка (`verified: false`) — другим рядком, як текст. */
        try { await render(); } catch (e) { /* публікація вдалась; плашка нижче все одно потрібна */ }
        /* Перемальовка — це `await`: людина могла встигнути перейти, поки вона йшла. */
        const late = publishReaction(r, sp0, sameTask());
        if (late.show === 'toast') { toast(t(late.key, label0)); return; }
        const share = remoteShareUrl(curTask, r.url);
        const openUrl = remoteOpenUrl(share, r.url);
        const lines = remoteNoticeLines(r).map((l) => (l.key ? t(l.key) : l.text));
        notice('publish-remote', t(view.key), [
          ...(openUrl ? [{ act: 'open', label: t('publishOpen'), run: () => window.open(openUrl, '_blank', 'noopener') }] : []),
          { act: 'copy', label: t('copyLink'), run: () => copyLinkText(share) },
        ], null, lines);
        return;
      }
      /* Публікація МОДУЛЕМ (простір без інтеграцій, `static-publish`): відповідь без `url` і без `dir`,
         зате з `local` — адресою на оригіні канваса. Без цієї гілки вона падала б нижче в «Деплой не
         вдався: —», хоч публікація вдалась. Адресу з відповіді відкриваємо лише відносною
         (`safeLocalUrl`), а плашка з «Відкрити» — стійка (`notice`), бо тост за 3 с зникав би раніше,
         ніж людина встигне натиснути. */
      if (view.kind === 'local') {
        const local = safeLocalUrl(r.local?.url, location.origin);
        render();
        /* Плашка стійка, а значить може пережити свою задачу: її гасить `resetPerTaskState` (перемикання
           задачі й простору). `noopener` — відкрита сторінка (чужий код макета під пісочницею) не має
           доступу до `window.opener`, тобто до канваса. */
        notice('publish-local', t(view.key),
          local ? [{ act: 'open', label: t('publishOpen'), run: () => window.open(local, '_blank', 'noopener') }] : []);
        return;
      }
      tell(t('publishDeployFailed', r.iterations, r.dir, r.deploy_error || '—'));
    } catch (e) {
      /* Коди відмов модульної публікації — людським текстом (`publishErr`), решта — як було. */
      const m = publishErr(e);
      tell(t(m.key, ...(m.reasonKey ? [t(m.reasonKey)] : m.args)));
    } finally {
      /* Кнопка оживає на ВСІХ шляхах — і після раннього `return` (тост, ЛІГА, плашка), і коли `render()` чи `notice()` кинули:
         інакше стара кнопка (її не замінила перемальовка, бо та не відбулась) лишалась би вимкненою з «Публікую…» назавжди.
         Перемальована смуга дає нову кнопку, а цей `el` уже відчеплений, тож і там нічого не псується. */
      el.disabled = false;
      if (lbl) lbl.textContent = prevText;
    }
  },

  retry: () => { render(); },

  /* Оновлення інструмента (0.23.0): пігулка в смузі (`update`) і пункт ⌘K «Що нового» (`updatenotes`) відкривають той самий діалог;
     «Перевірити оновлення» (`updatecheck`) питає remote зараз. Логіка — `openUpdateDialog`/`checkUpdateNow` нижче. */
  /* З пігулки в рядку вкладок — поповер під нею (етап В); з ⌘K чи «Налаштувань» якоря нема — модальна картка. */
  update: (val, el) => openUpdateDialog(el?.classList?.contains('upd-pill') ? el : null),
  /* «Відгук» (смуга) і «Баг / ідея» (⌘K): той самий діалог, на будь-якому екрані й без задачі (`openFeedback`). */
  /* З кнопки острівця — поповер над нею (етап В); з ⌘K якоря нема — модальна картка. */
  feedback: (val, el) => openFeedback(el?.closest?.('#hud') ? el : null),
  updatenotes: () => openUpdateDialog(),
  updatecheck: () => checkUpdateNow(),

  // ── крошка ітерації: дії, яких у старій смузі не було зовсім (лише в
  // панелі) — логіка та сама, що в `pillMenu`/`#pp-newit`, написана тут
  // наново, бо `renderPanel()` — межа Task 4. ──────────────────────────────
  /* Перемкнути ітерацію. Гілка `freshen()`+`maybeAutoShoot()` — та сама, що
     була в обробнику `#pp-itsel` старої панелі: без неї перемикання в
     «Огляді» показувало б застарілі кадри без бейджів. Перенесена без змін. */
  iter: async (val) => {
    if (!val || val === picked) return;
    picked = val;
    pickedPage = null; pickedState = null;
    openDd = null;
    await loadPages();
    if (mode === 'canvas') { await freshen(); maybeAutoShoot(); }
    render();
  },
  newit: dupIteration,
  dupit: dupIteration,

  renit: async () => {
    const it = curIter();
    if (!it) return;
    const cur = it.label || (it.note || '').replace(/^\s*[A-Z]+-\d+\s*[·:-]\s*/, '');
    const next = await ask(t('menuRenameIterationPrompt', itNum(it.id)), cur);
    if (next === null) return;
    try { await post('/api/iteration-rename', { id: it.id, label: next }); render(); }
    catch (e) { tellError(t('errTRenameIter'), e.message); }
  },

  /* `val === 'confirmed'` — питання вже поставлено в дропдауні ітерації (`data-val` у розмітці смуги, етап В); з палітри
     ⌘K дія йде без значення — темна картка, як було. «Ні» в дропдауні — порожня дія: дропдаун уже закрито делегуванням. */
  delitno: () => {},
  delit: async (val) => {
    const it = curIter();
    if (!it) return;
    const label = it.label_text || it.id;
    /* `confirmed:<id>` — питання в дропдауні назвало саме цю ітерацію: коли «поточною» стала інша, не видаляємо нічого. */
    const pre = confirmedId(val);
    if (pre !== null && pre !== it.id) return;
    const go = pre !== null || await askYesNo(t('menuDeleteIterationConfirm', label), { yes: t('menuDeleteYes'), danger: true });
    if (!go) return;
    try {
      await post('/api/iteration-delete', { id: it.id });
      if (picked === it.id) picked = null;
      render();
    } catch (e) { tellError(t('errTDeleteIter'), e.message); }
  },

  // ── дропдаун синку з git: адреси `vcs-*` (старі, з префіксом gitlab, лишились псевдонімами для хука) ──────
  glpush: async () => {
    if (!glCache) return;
    /* Підпис репозиторію в текстах — той самий нормалізований, що в смузі й палітрі: у ЛІГА «GitLab» (тексти 0.7.0
       дослівно), у звичайному просторі — з відповіді статусу, а без нього нейтральний «Git». */
    const lbl = glLabelNow();
    /* Статус ще не відомий: перший опит натрапив на лок дзеркала (іде клон, відправка чи отримання). Далі нема чого
       питати в git — кажемо це й перепитуємо статус, щоб стан не лишився «зайнято» назавжди. */
    if (glCache.busy) { tell(t('vcsErrBusy')); await refreshGitlab(); render(); return; }
    /* Кеш уже каже, що останній запит статусу впав, — другий запит до git
       приречений на ту саму помилку. Кажемо ЇЇ, а не повторюємо виклик: код із власним текстом (немає мережі, ключ)
       — ним, решта — причиною як є. */
    if (glCache.error) { tell(glFailText(glCache, lbl, t('errFailed', glCache.error))); return; }
    try {
      const r = await post('/api/vcs-push', { it: picked });
      if (r.blocked === 'behind') tell(t('glBehindMsg', r.behind, lbl));
      /* Відмова «це чужа ітерація» мусить сказати ЧИЯ і що робити. Без цієї
         гілки вона падала в загальну «Синк не вдався: —»: у відповіді
         `foreign` немає поля `error`, тобто людина бачила прочерк замість
         причини. */
      else if (r.blocked === 'foreign') tell(t('glForeignMsg', r.author || '—'));
      /* Відмова git чи модуля — 200 `{ok: false, error, code}`: код із власним текстом (немає мережі, ключ, «іде
         синхронізація», погана ціль) каже людині, ЩО робити; решта кодів — загальне повідомлення з причиною сервера. */
      else if (!r.ok) tell(glFailText(r, lbl, t('glSyncFailedMsg', r.error || '—', lbl)));
      else if (r.catchup) toast(t('glCatchupToast', lbl));
      else if (r.changed === false) toast(t('glNothingToSendToast', lbl));
      else if (r.pushed) toast(t('glPushedToast', r.sha || '—', lbl));
    /* `requestErrText`: 400 від `send_error` (немає ролі чи цілі, погана ітерація) приходить HTML-ом, причина — в рядку статусу. */
    } catch (e) { tellError(t('errTVcsPush'), requestErrText(e)); }
    await refreshGitlab(); render();
  },

  glpull: async () => {
    const lbl = glLabelNow();
    const go = await askYesNo(t('glPullConfirmMsg', lbl), { yes: t('glPullConfirmYes') });
    if (!go) return;
    try {
      const r = await post('/api/vcs-pull', {});
      /* Pull, який упізнав власний вміст, ітерації не заводить — і мусить
         сказати це вголос. Без тоста кнопка виглядає зламаною: дизайнер
         натиснув, і НІЧОГО не сталось. */
      if (r.unchanged) toast(t('glPullUnchangedToast', r.same_as || '—', lbl));
      /* Своє, але старше за мою роботу: привезене — історія, робота йде з форка
         моєї найсвіжішої (рішення власника 29.09.2026, fb-29092026-d64d35). */
      else if (r.continue_from && r.fork) toast(t('glPullOlderToast',
        t('iterTag', itNum(r.iteration.id)), t('iterTag', itNum(r.continue_from)),
        t('iterTag', itNum(r.fork.id)), lbl));
      /* Відмова git приходить 200-ю `{ok: false, error, code}` (а «шлях не знайдено в репо» — без `code`), тож `catch`
         її не бачить: без цієї гілки pull, що не вдався, мовчав би — а мовчазна кнопка виглядає зламаною. */
      else if (r.ok === false) tell(glFailText(r, lbl, t('glSyncFailedMsg', r.error || '—', lbl)));
      await refreshGitlab(); render();
    } catch (e) { tellError(t('errTVcsPull'), requestErrText(e)); }
  },

  /* Синк із git у ЛІГА налаштовується правкою `tasks.json` (`gitlab_cfg()` у `serve.py`), а не на «Підключенні»: відкриття
     екрана підбивало б людину ввімкнути явний `git-sync`, що перекрив би зашитий шлях ЛІГА без `gitlab_ssh_key` (спека 4a,
     «Простір ЛІГА»). Кажемо РЕАЛЬНЕ місце правки, а не вигадуємо кнопку, якої нема. Деінде — звичайний простір: репозиторій
     задається на «Підключенні», на картці модуля ролі `vcs` (`enterConnections('vcs')` — фокус і прокрутка до неї). */
  glsetup: () => { if (isLegacyVcs(spaceNow())) tell(t('glSetupMsg')); else enterConnections('vcs'); },

  /* `web` віддає свій модуль: відкриваємо лише `http(s)` (`vcsWebUrl`) — `javascript:`/`file:` не історія, а смуга такого пункту не малює. */
  glhistory: () => {
    const web = vcsWebUrl(glCache?.web);
    if (web) { window.open(web, '_blank', 'noopener'); return; }
    /* Статус ще «зайнято»: куди вести — невідомо, і мовчати не можна (пункт показано саме тому, що web ще не знаємо). */
    if (glCache?.busy) tell(t('vcsErrBusy'));
  },

  // ── дропдаун публікації: `togglepub` — заміна старого `[data-toggle]`,
  // `openpreview`/`copylink` — нові контроли моделі (те, що робив `#pp-copy`
  // в панелі для сторінки, тут — для задачі/ітерації в смузі). ────────────
  togglepub: async () => {
    const it = curIter();
    if (!it) return;
    try { await post('/api/publish-toggle', { id: it.id }); render(); }
    catch (e) { tellError(t('errTPublish'), e.message); }
  },

  openpreview: () => {
    /* Ціль — з моделі: ЛІГА-URL, локальна адреса `/published/<простір>/<задача>/` канваса або адреса,
       яку опублікував модуль «за адресою» (Vercel): її відкриваємо лише після `safeRemoteUrl`, і саме за посиланням з паролем
       (`remoteOpenUrl`), щоб власник не впирався у власний гейт. */
    const target = previewTarget(curTask, spaceNow());
    if (!target) return;
    const url = target.remote ? remoteOpenUrl(target.share, target.url) : target.url;
    if (url) window.open(url, '_blank', 'noopener');
  },

  /* Тиша Teams на канал задачі. Вимкнути — спільна дія (тиша для ВСІХ, хто
     коментує цей проєкт), тому з підтвердженням; увімкнути — без. */
  teamsnotify: async () => {
    if (!teamsMute || teamsMute.error) return;
    const mute = !teamsMute.muted;
    if (mute && !(await askYesNo(t('askTeamsMute', teamsMute.channel), { yes: t('teamsMuteYes') }))) return;
    try {
      teamsMute = await post('/api/teams-mute', { muted: mute });
      /* Тост — зі СТАНУ, а не з наміру: тиша могла лишитись через батьківський
         канал (`via`), і «увімкнено» тоді було б неправдою (ревʼю 1.52). */
      if (teamsMute.muted === mute) toast(t(mute ? 'toastTeamsMuted' : 'toastTeamsOn'));
      else tell(t('teamsStillMuted', teamsMute.via || teamsMute.channel));
      paintBar();
    } catch (e) {
      tellError(t('errTTeamsMute'), e.message);
      teamsMute = null;
      paintBar();
      loadTeamsMute();
    }
  },

  /* Пароль превʼю (ідея 02.09.2026). Пишемо лише в tasks.json: гейт у зібраному
     превʼю міняє ПОВНА публікація (вона ж ставить його в кожну сторінку). Тому
     відповідь чесно ділиться на три: ще не публікувалось / той самий / превʼю
     зі старим — і в останньому випадку пропонуємо оновити публікацію одразу. */
  pubpw: async () => {
    openDd = null;
    const next = await ask(t('askPreviewPw'), curTask?.preview_password_custom ? curTask.preview_password : '');
    if (next === null) { render(); return; }
    let r;
    try { r = await post('/api/preview-password', { password: next }); }
    catch (e) { tellError(t('errTPreviewPw'), e.message); render(); return; }
    await render();
    const state = curTask?.publish_url ? r.preview_gate?.state : 'none';
    if (state === 'stale') {
      const go = await askYesNo(`${t('pwSavedRepublish')}\n\n${t('pwMachineNote')}`, { yes: t('update') });
      if (go) document.querySelector('#bar [data-act="publish"]')?.click();
      return;
    }
    tell(`${t(state === 'current' ? 'pwSavedSame' : 'pwSavedNotPublished')}\n\n${t('pwMachineNote')}`);
  },

  figma: () => copyToFigma(),

  copylink: async () => {
    const target = previewTarget(curTask, spaceNow());
    if (!target) return;
    /* Пароль невідомий (секрети не читаються) — посилання з порожнім ключем менеджеру б не відкрило превʼю: показуємо помилку, не копіюємо. */
    if (copyLinkRefused(curTask, spaceNow(), target)) { tell(t('pwUnreadable')); return; }
    const pageId = pickedPage && pickedPage !== 'main' ? `${picked}/${pickedPage}` : picked;
    /* Локальне посилання — адреса канваса БЕЗ фрагмента з паролем: пароль модуля — секрет, якого UI не
       знає (посилання збирає `copyUrl`, `spaces-model.js`); ЛІГА-посилання — як було, з паролем і сторінкою. */
    /* Публікація модулем «за адресою» (Vercel): `copyUrl` кладе `publish_share_url` ДОСЛІВНО — фрагмент із паролем
       склав сервер, і ЛІГА-шний `preview_password` тут не бере участі. */
    const url = copyUrl(target, { origin: location.origin, pageId, password: curTask.preview_password || '' });
    await copyLinkText(url);
  },
};

/**
 * Кладе посилання в буфер й каже про це тостом; спільний для «Скопіювати посилання» в дропдауні і в плашці
 * «Опубліковано на Vercel». `url` порожній — нічого не робимо (нема що копіювати).
 */
async function copyLinkText(url) {
  if (!url) return;
  try {
    await navigator.clipboard.writeText(url);
    toast(t('toastCopied'));
  } catch (e) {
    /* Фолбек, коли clipboard недоступний (не-https, відмовлені права):
       показуємо, а не питаємо. Поле лишається виділюваним для копіювання
       руками; на результат ніщо не спирається, тому без `await`. */
    ask(t('askCopyLinkPrompt'), url, { readOnly: true });
  }
}

// ===== Оновлення інструмента (0.23.0): пігулка, діалог «Що нового», опит після рестарту =====

/* Стеля запиту `POST /api/update-apply`: `fetch` тега (60 с) + merge (60 с) + самоперевірка (30 с) + дрібні виклики git. Обрив раніше
   сказав би «не відповів» про оновлення, яке ще тривало. */
const UPDATE_APPLY_TIMEOUT_MS = 240000;
/* Стеля `GET /api/update-notes` (там один `fetch` тега, 60 с) і окремого кроку опиту після рестарту (сервер може саме підніматись). */
const UPDATE_NOTES_TIMEOUT_MS = 90000;
const UPDATE_STEP_TIMEOUT_MS = 3000;
const UP_RF_KEY = 'dc-up-restart-told';

/** `GET /api/update` → стан або `null` (сервер мовчить / чужа відповідь). Без шуму: оновлення — не головна справа екрана. */
async function fetchUpdate() {
  try {
    const r = await api('/api/update');
    return r && typeof r === 'object' && typeof r.boot === 'string' ? r : null;
  } catch (e) { return null; }
}

/* Після невдалого рестарту — ОДИН тост на процес сервера (`boot`): без памʼяті він повторювався б кожні 30 хв. Памʼять — у
   `sessionStorage` (переживає перезавантаження вкладки), а коли сховища нема — у змінній. */
let upToldBoot = null;
let updateMisses = 0;
function tellRestartOnce(info) {
  if (!info || info.restart_failed !== true) return;
  let seen = upToldBoot;
  try { seen = sessionStorage.getItem(UP_RF_KEY) ?? seen; } catch (e) { /* без сховища — лише змінна */ }
  if (seen === info.boot) return;
  upToldBoot = info.boot;
  try { sessionStorage.setItem(UP_RF_KEY, info.boot); } catch (e) { /* див. вище */ }
  toast(t('upRestartManual'));
}

/** Знімає стан оновлення й перемальовує смугу, коли він змінився. */
async function pollUpdate() {
  const next = await fetchUpdate();
  /* Одна крапка мережі не прибирає пігулку: останній добрий стан тримається, доки не набралось кілька промахів поспіль. */
  const st = nextUpdateInfo(updateInfo, next, updateMisses);
  updateMisses = st.misses;
  const changed = JSON.stringify(st.info) !== JSON.stringify(updateInfo);
  updateInfo = st.info;
  tellRestartOnce(next);
  if (changed && barSeeded) paintBar();
  return next;
}

let updateChecking = false;
/** «Перевірити оновлення» (⌘K): `POST /api/update-check` → тост. Сервер віддає ту саму форму, що `GET /api/update`, плюс `ok`. */
async function checkUpdateNow() {
  if (updateChecking) return;
  updateChecking = true;
  toast(t('upChecking'));
  try {
    const r = await api('/api/update-check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (r && typeof r.boot === 'string') { updateInfo = r; paintBar(); tellRestartOnce(r); }
    const good = r && r.state === 'ok';
    toast(!good ? t('upCheckFailed') : (r.available ? t('upFound', r.latest) : t('upUpToDate', r.current)));
  } catch (e) {
    toast(t('upCheckFailed'));
  } finally {
    updateChecking = false;
  }
}

/** `fetch` зі стелею часу; `null` — мережа/обрив. JSON розбирається тут (тіло відмов оновлення — `{ok:false, code}` без `error`,
 *  тож `api()` з його `error`-логікою для відмов не годиться: код загубився б). */
async function updateFetch(path, opts, ms) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const res = await fetch(path, { ...opts, signal: ctl.signal, cache: 'no-store' });
    let body = null;
    try { body = await res.json(); } catch (e) { /* не JSON — лишається null */ }
    return { status: res.status, body };
  } catch (e) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/** Чекає, поки піднімається НОВИЙ процес сервера (`restartStep`): крок щосекунди, поки не `done`/`manual`/`fail`. Мережева помилка —
 *  це «сервер ще лежить», а не відмова. Цикл послідовний (наступний крок після попереднього), тож накладок нема. */
function waitForRestart(prevBoot, target) {
  return waitRestart({
    prevBoot, target, startedAt: Date.now(), now: Date.now,
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    fetchOnce: async () => {
      const r = await updateFetch('/api/update', {}, UPDATE_STEP_TIMEOUT_MS);
      const b = r && r.status === 200 && r.body && typeof r.body === 'object' ? r.body : null;
      return b ? { ok: true, boot: b.boot, current: b.current, restart_failed: b.restart_failed } : { ok: false };
    },
  });
}

/** Людський текст відмови `apply` (код → словник). Для `dirty`/`diverged` команду дописано в сам текст: діалог лишається відкритим, а
 *  кнопки «Копіювати» в рядку помилки нема. */
function updateErrText(code, latest) {
  const h = blockedHelp(code, latest);
  return h.command ? `${t(h.key, h.code)} ${h.command}` : t(h.key, h.code);
}

/**
 * Діалог «Оновлення»: малюється одразу (з `sections: null`), опис змін дотягується окремо й перемальовує ЛИШЕ свій блок
 * (`[data-up-notes]`) — опис не умова оновлення, його затримка чи відмова кнопку не блокує. «Оновити» → `POST /api/update-apply`:
 * `202` → «Оновлюю…» і опит нового процесу; `done` → перезавантаження сторінки. Форма на час запиту «зайнята» (`askForm`): Esc і
 * «Скасувати» не діють, тож опит не лишається без діалогу.
 */
let updateDialogOpen = false;
async function openUpdateDialog(anchor = null) {
  if (updateDialogOpen) return;
  updateDialogOpen = true;
  try {
    const info = (await pollUpdate()) || updateInfo;
    if (!info) { toast(t('upCheckFailed')); return; }
    let formEl = null;
    const loadNotes = async () => {
      const r = await updateFetch('/api/update-notes', {}, UPDATE_NOTES_TIMEOUT_MS);
      const b = r && r.status === 200 && r.body && typeof r.body === 'object' ? r.body : null;
      const view = !b || b.ok !== true ? { sections: [], reason: 'error' }
        : { sections: Array.isArray(b.sections) ? b.sections : [], reason: typeof b.reason === 'string' ? b.reason : null };
      const slot = formEl?.isConnected ? formEl.querySelector('[data-up-notes]') : null;
      if (slot) slot.innerHTML = updateNotesHTML(view);
    };
    const status = (text) => {
      const el = formEl?.querySelector('[data-up-status]');
      if (!el) return;
      el.textContent = text || '';
      el.hidden = !text;
    };
    await askForm(() => updateDialogHTML({
      current: info.current, latest: info.latest, blocked: info.blocked, state: info.state, reason: info.reason,
      sections: null, restartFailed: info.restart_failed === true,
    }), {
      /* Пігулку перемальовує смуга, а після оновлення вона може зникнути: фокус — на пігулку, а коли її нема, на двері в палітру. */
      anchor, place: 'below',
      focusBack: () => document.querySelector('#tabs .upd-pill') ?? document.querySelector('#tabs [data-act="home"]'),
      onMount(form) {
        formEl = form;
        /* «Копіювати» біля команди: буфер, а коли його нема (не-https, відмовлені права) — виділяємо команду, щоб скопіювати руками. */
        form.addEventListener('click', async (ev) => {
          const b = ev.target.closest?.('[data-copy]');
          if (!b) return;
          try {
            await navigator.clipboard.writeText(b.dataset.copy);
            b.textContent = t('upCopied');
          } catch (e) {
            const code = b.previousElementSibling;
            if (code) getSelection()?.selectAllChildren(code);
          }
        });
        loadNotes();
      },
      async onSubmit(_values, ctl) {
        status(t('upApplying'));
        /* Свіжий `boot` ПЕРЕД запитом: стан із моменту відкриття діалогу міг застаріти (сервер перезапускали вручну), і тоді опит
           прийняв би старий процес за новий. */
        const prevBoot = bootBefore(await fetchUpdate());
        if (!prevBoot) { status(''); return t('upErrNoAnswer'); }     // без свіжого boot запит НЕ шлемо (хибне `done` по застарілому)
        const r = await updateFetch('/api/update-apply', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
        }, UPDATE_APPLY_TIMEOUT_MS);
        if (!r) { status(''); return t('upErrNoAnswer'); }
        if (r.status !== 202 || !r.body || r.body.ok !== true) {
          status('');
          pollUpdate();
          return updateErrText(codeOfBody(r.body), info.latest);
        }
        if (r.body.restart === 'manual') {
          /* Windows: сервер сам не перезапускається. Нове оновлення вже на диску, тож «Оновити» вдруге нічого б не дало — ховаємо її. */
          status('');
          ctl.form.querySelector('button[data-a="ok"]')?.setAttribute('hidden', '');
          return t('upRestartManual');
        }
        const step = await waitForRestart(prevBoot, typeof r.body.to === 'string' ? r.body.to : info.latest);
        status('');
        if (step === 'done') { status(t('upDone')); location.reload(); return undefined; }
        if (step === 'manual') return t('upRestartManual');
        return t('upRestartLost');
      },
    });
  } finally {
    updateDialogOpen = false;
  }
}

/* ── Відгук (0.23.0) ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Діалог показує ТОЧНО те, що піде: `POST /api/feedback-preview` повертає діагностику й стан знімка, а `POST /api/feedback` збирає її
   тією ж функцією сервера. Кільце помилок браузера (`err-ring.js`) знімається ОДИН раз при відкритті (`createSession`): і перегляд, і
   відправка читають той самий масив. Усі рядки сервера потрапляють у DOM лише як `textContent`/через `esc` у розмітці. */
const FEEDBACK_TIMEOUT_MS = 30000;
const clientErrorList = initErrRing();   // `list()` кільця (слухачі вже стоять з імпорту; виклик ідемпотентний)
const jsonPost = (path, body) => updateFetch(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}, FEEDBACK_TIMEOUT_MS);

/** Контекст екрана для відгуку: задача, екран і (коли є знімок поточної сторінки) пара `it`/`node`. Нічого не обовʼязкове. */
function feedbackContext() {
  const ctx = { task: curTask?.id || currentTaskId || '', screen: homeOpen ? (homePage || 'tasks') : mode };
  if (!homeOpen && picked && pickedPage) {
    const key = frameKey(pickedPage, canvasW);
    if (shotManifest.shots?.[key]) { ctx.it = picked; ctx.node = key; }
  }
  return ctx;
}

/** `POST /api/feedback-preview` → тіло відповіді або `null` (мережа/відмова: діалог працює без «Що буде надіслано»). Без `diag_hash`
 *  відповідь не годиться: відправка з діагностикою без відбитка однаково дістала б 409. */
async function fetchFeedbackPreview(sess) {
  const r = await jsonPost('/api/feedback-preview', sess.previewBody());
  return r && r.status === 200 && r.body && r.body.ok === true && r.body.diag && typeof r.body.diag === 'object'
    && typeof r.body.diag_hash === 'string' && Number.isInteger(r.body.ring_seq) ? r.body : null;
}

let feedbackDialogOpen = false;
/* Чернетка відгуку (етап В): живе в памʼяті вкладки до успішної відправки — поповер закривається кліком повз,
   і набране не мусить пропадати. */
let fbDraft = null;
const fbDraftOf = (form) => {
  const v = formValues(form.elements);
  return { kind: v.kind, text: v.text, contact: v.contact, includeDiag: v.diag, includeShot: v.shot };
};
async function openFeedback(anchor = null) {
  if (feedbackDialogOpen) return;
  feedbackDialogOpen = true;
  try {
    const sess = createSession({ ctx: feedbackContext(), clientErrors: clientErrorList(), lang: getLang() });
    let preview = await fetchFeedbackPreview(sess);
    let previewSeq = 0;
    let formEl = null;
    const shownText = (p, includeDiag, includeShot) => (p
      ? previewText(sentView(p, { includeDiag, includeShot })) : t('fbPreviewFail'));
    const checked = (id) => !!formEl?.querySelector(id)?.checked;
    /* Стан знімка за свіжим переглядом: чекбокс (знову вмикається, коли знімок зʼявився), причина, мініатюра (лише коли прикладено). */
    const syncShot = () => {
      if (!formEl) return;
      const shot = shotState(preview);
      const cb = formEl.querySelector('#fb-shot');
      if (cb) { cb.disabled = !shot.available; if (!shot.available) cb.checked = false; }
      const why = formEl.querySelector('[data-fb-shot-why]');
      if (why) { why.textContent = t(shot.reasonKey || 'fbShotNone'); why.hidden = shot.available; }
      const thumb = formEl.querySelector('[data-fb-thumb]');
      if (thumb) thumb.hidden = !(shot.available && cb?.checked);
    };
    const paintPreview = () => {
      if (!formEl) return;
      syncShot();
      const diagWhy = formEl.querySelector('[data-fb-diag-why]');
      if (diagWhy) diagWhy.hidden = !!preview;
      const pre = formEl.querySelector('[data-fb-pre]');
      if (pre) pre.textContent = shownText(preview, checked('#fb-diag'), checked('#fb-shot'));
    };
    /* Перемалювати лише «Що буде надіслано» за свіжим переглядом; застарілу відповідь відкидаємо. */
    const repaint = async () => {
      const seq = ++previewSeq;
      const p = await fetchFeedbackPreview(sess);
      if (seq !== previewSeq || !formEl?.isConnected) return;
      preview = p;
      paintPreview();
    };
    await askForm(() => feedbackDialogHTML({
      ...(fbDraft || {}),
      shot: shotState(preview), shotUrl: sess.shotUrl(), previewFailed: !preview,
      previewText: preview ? previewText(sentView(preview, { includeDiag: true, includeShot: false })) : t('fbPreviewFail'),
    }), {
      anchor, place: 'above',
      focusBack: () => document.querySelector('#hud [data-act="feedback"]') ?? document.querySelector('#tabs [data-act="home"]'),
      onMount(form) {
        formEl = form;
        /* Чернетка (етап В): кожна правка запамʼятовується, закриття повз її не губить; відправка — очищає. */
        const keep = () => { fbDraft = fbDraftOf(form); };
        form.addEventListener('input', keep);
        form.addEventListener('change', keep);
        /* Перегляд не вдався: діагностика за замовчуванням ВИМКНЕНА (галочку знімає розмітка). Людина може ввімкнути — тоді `change` питає знову. */
        for (const id of ['#fb-diag', '#fb-shot']) form.querySelector(id)?.addEventListener('change', repaint);
        form.querySelector('#fb-shot')?.addEventListener('change', syncShot);
      },
      async onSubmit(vals, ctl) {
        const bad = validate({ kind: vals.kind, text: vals.text, contact: vals.contact });
        if (bad) { ctl.focus(errField(bad)); return t(bad, errArg(bad)); }
        const r = await jsonPost('/api/feedback', sess.sendBody({
          kind: vals.kind, text: vals.text, contact: vals.contact,
          includeDiag: vals.diag, includeShot: vals.shot, shotAvailable: shotState(preview).available, diagHash: preview?.diag_hash, ringSeq: preview?.ring_seq,
        }));
        if (!r) return t('fbErrGeneric', t('fbErrNoAnswer'));
        const b = r.body && typeof r.body === 'object' ? r.body : {};
        if (r.status === 409) {
          /* «Що показано = що піде»: діагностика змінилась (або перегляду не було). Показуємо НОВУ й просимо натиснути ще раз. */
          const fresh = previewFromConflict(preview, b);
          if (fresh) {
            previewSeq += 1;
            preview = fresh;
            paintPreview();
            const det = formEl?.querySelector('[data-fb-preview]');
            if (det) det.open = true;
            return t('fbDiagChanged');
          }
        }
        if (r.status === 400 && b.ok === false) {
          const key = serverErrKey(b.code);
          if (key) { ctl.focus(errField(key)); return t(key, errArg(key)); }
        }
        if (r.status !== 200 || b.ok !== true) return t('fbErrGeneric', String(b.error || r.status));
        const o = outcome(b);
        toast(t(o.key, ...o.args) + (o.suffixKey ? ` ${t(o.suffixKey)}` : ''));
        fbDraft = null;
        return undefined;
      },
    });
  } finally {
    feedbackDialogOpen = false;
  }
}

/* Стан тиші Teams для дропдауна публікації. Помилка — це стан («не знаю»),
   а не виняток: пункт показує причину замість вигаданого «увімкнено». */
async function loadTeamsMute() {
  /* Простір без ролі `notify`: сервер відповів би 409 `notify-off`, а `catch` нижче перетворив би це
     на «помилку» в дропдауні публікації. Тут стану тиші нема взагалі — без запиту. */
  if (noNotify()) { teamsMute = null; return; }
  try { teamsMute = await api('/api/teams-mute'); }
  catch (e) { teamsMute = { error: e.message }; }
  if (openDd === 'pub') paintBar();
}

// ===== «В Figma» (T-41): живий макет → буфер → ⌘V у Figma =====

/* Скільки тримати «Копіюю…». На успіх ми НЕ чекаємо: проміс `captureForDesign`
   при успіху розвʼязується лише коли людина закриє тулбар скрипта (успіх
   скрипт показує сам, своїм тостом). Стеля = затримка скрипта + сам захват
   із запасом; невдача, що прийде пізніше, однаково дійде до `tell()`. */
const FIGMA_BUSY_MAX_MS = CAPTURE_DELAY_MS + 2500;

/** Скільки правок тюнера ЛЕЖИТЬ на цьому документі макета зараз. Не всі
 *  правки пакета: ті, що не лягли (`tuneMissing`), на екрані не видно, тож і
 *  у Figma вони не поїдуть. Рішення власника 28.09.2026: копіюємо «як на
 *  екрані» і кажемо про правки в тості, а не знімаємо їх на час захоплення. */
function liveTuneCount() {
  const page = tunePage();
  if (!page) return 0;
  return Math.max(0, (packageJSON(tuneState, page).editCount || 0) - tuneMissing.length);
}

/** Вікно рамки, у якому зараз живий макет, або null. */
function mockupWindow() {
  if (mode === 'canvas' || !picked) return null;
  try {
    const w = frame.contentWindow;
    return w && w.document && w.location.pathname === '/commented' ? w : null;
  } catch (e) { return null; }
}

/**
 * Скопіювати поточний макет у буфер у форматі, який приймає Figma.
 *
 * ⛔ `captureToFigma` кличеться ПЕРШИМ рядком, синхронно з кліку: вона
 * фокусує рамку до будь-якого `await` (без фокуса скрипт висить вічно, а
 * вікно активації кліку живе ~5 с — `figma-capture.js`, факти 1–2).
 * Перемальовка смуги й тост — уже після.
 */
function copyToFigma() {
  if (figmaBusy) return;
  const w = mockupWindow();
  if (!w) return;
  const tuned = liveTuneCount();
  const run = captureToFigma(w);
  figmaBusy = true;
  paintBar();
  toast(tuned ? t('toastFigmaTuned', tuned) : t('toastFigmaStart'));
  const release = () => { if (figmaBusy) { figmaBusy = false; paintBar(); } };
  const cap = setTimeout(release, FIGMA_BUSY_MAX_MS);
  /* `captureToFigma` не відхиляється за контрактом; `.catch` — друга лінія на
     випадок, коли контракт колись порушать: невдача мусить дійти до людини. */
  run.then((res) => {
    clearTimeout(cap);
    release();
    if (!res.ok) tell(t(res.key, res.detail));
  }).catch((e) => {
    clearTimeout(cap);
    release();
    tell(t('figmaErrFailed', String(e?.message ?? e)));
  });
}

/* Підвантажити скрипт ДО кліку — на наведенні чи фокусі кнопки. Мережа тоді
   не з'їдає вікно активації кліку (~5 с). Без hash `#figmacapture` скрипт лише
   реєструє `window.figma` і нічого не захоплює. Помилку тут ковтаємо свідомо:
   це лише підготовка, а клік повторить спробу й скаже про невдачу вголос. */
function preloadFigma(ev) {
  if (!ev.target.closest?.('[data-act="figma"]')) return;
  const w = mockupWindow();
  if (w) loadCapture(w).catch(() => {});
}
bar.addEventListener('pointerover', preloadFigma);
bar.addEventListener('focusin', preloadFigma);

/* Одна делегація на всю смугу замість десятка `querySelector`. Причина не в
   стислості: кожен новий контрол інакше вимагає нового рядка проводки, а
   забутий рядок — це кнопка, що нічого не робить, і жоден юніт цього не
   бачить. Живий тест `tests/live/shell-bar.test.mjs` тисне кожен контрол саме
   тому. */
bar.addEventListener('click', (ev) => {
  const el = ev.target.closest('[data-act],[data-dd]');
  if (!el || el.disabled) return;
  if (el.dataset.dd) {
    openDd = openDd === el.dataset.dd ? null : el.dataset.dd;
    // Свіжий стан щоразу: канал залежить від задачі, і чужий «вимкнено» з
    // попередньої задачі на мить — теж неправда.
    if (openDd === 'pub') { teamsMute = null; loadTeamsMute(); }
    /* Перелік і лічильники задач у дропдауні просторів — свіжі на момент відкриття:
       простір міг зʼявитись чи зламатись поза вкладкою (агент, інша машина). Малюємо
       зразу з тим, що є, а коли відповідь прийде — перемальовуємо, якщо дропдаун ще
       відкритий. */
    if (openDd === 'space') loadSpaces().then(() => { if (openDd === 'space') paintBar(); });
    paintBar();
    return;
  }
  const act = el.dataset.act;
  /* «Видалити ітерацію» в дропдауні (етап В): дропдаун лишається відкритим і стає питанням. */
  if (act === 'delitask') { iterDelAsk = true; paintBar(); bar.querySelector('.dd--confirm .cfm-no')?.focus(); return; }
  const hadOpenDd = !!openDd;
  /* Рядок дропдауна просторів — фокус після закриття вернемо на фішку (див. нижче). */
  const fromSpaces = openDd === 'space' && !!el.closest('.dd--spaces');
  openDd = null;
  /* `publish` малює власний тимчасовий стан («Публікую…», `disabled`)
     СИНХРОННО до першого `await` — негайна перемальовка тут стерла б його
     раніше, ніж хтось встиг би побачити. Решта дій самі не тримають
     подібного тимчасового DOM, тому їм безпечно закрити дропдаун одразу —
     а закрити ТРЕБА: майже всі ці дії (крошка ітерації, GitLab, публікація)
     самі живуть УСЕРЕДИНІ дропдауна, який щойно був відкритий, щоб до них
     дотягнутись. */
  if (hadOpenDd && act !== 'publish') paintBar();
  /* Enter (чи клік) на рядку дропдауна просторів: рядок зник разом із ним, і фокус лишився б
     на `body` — клавіатурна людина губиться. Повертаємо на фішку, що дропдаун відкрила; діалог
     (`spacenew`/`spaceedit`) далі запамʼятає її як відкривача. */
  if (fromSpaces) focusChip();
  BAR_ACTIONS[act]?.(el.dataset.val, el, ev);
});

/* Рядок вкладок і острівець: той самий шлях, що в смуги, — `data-act` → `BAR_ACTIONS`. Відкритий дропдаун смуги закриває
   загальний клік по документу (нижче), тож тут його не чіпаємо. Середня кнопка по вкладці — закрити її. */
function onChromeClick(ev) {
  const el = ev.target.closest('[data-act]');
  if (!el || el.disabled) return;
  BAR_ACTIONS[el.dataset.act]?.(el.dataset.val, el, ev);
}
tabsEl.addEventListener('click', onChromeClick);
hudEl.addEventListener('click', onChromeClick);
tabsEl.addEventListener('auxclick', (ev) => {
  if (ev.button !== 1) return;
  const el = ev.target.closest('[data-act="tab"]');
  if (!el) return;
  ev.preventDefault();
  BAR_ACTIONS.tabclose(el.dataset.val);
});

/* Дропдаун закривається кліком повз нього. `.closest('.ddhost')` рятує від
   самозакриття: клік по самій кнопці-відкривачу теж долітає сюди (bubbling), і
   без цієї перевірки дропдаун відкривався б і тут-таки закривався. */
document.addEventListener('click', (ev) => {
  if (!openDd) return;
  if (ev.target.closest?.('.ddhost')) return;
  openDd = null;
  paintBar();
});
document.addEventListener('keydown', (ev) => {
  /* Esc під час IME-композиції скасовує ЇЇ, а не дропдаун: інакше людина, що
     передумала набирати, втрачала б ще й відкритий список. */
  if (ev.key === 'Escape' && openDd && !ev.isComposing) {
    const wasSpaces = openDd === 'space';
    openDd = null;
    /* Esc закрив дропдаун — він ЗАЙНЯТИЙ: бічна панель «Підключення» (слухач нижче по файлу) за той самий Esc не
       закривається (`defaultPrevented`). */
    ev.preventDefault();
    paintBar();
    /* З дропдауна просторів фокус вертається на фішку, що його відкрила: рядок, на
       якому він стояв, зник разом з дропдауном, і клавіатура лишилась би на `body`. */
    if (wasSpaces) focusChip();
  }
});

/* Клавіатура дропдауна просторів — справжній roving focus по `.dd--spaces .dd-item`:
   ↑/↓ ходять по рядках, Home/End — крайні, Enter/пробіл — нативний клік кнопки
   (делегація вище). З фішки ↓ відкриває дропдаун (патерн «меню-кнопка»), а в
   відкритому — веде на поточний рядок. Правило «куди йти» — `rovingIndex` (модель);
   чужу клавішу він повертає як `null`, і `preventDefault` її не гасить. */
bar.addEventListener('keydown', (ev) => {
  if (ev.isComposing || ev.altKey || ev.ctrlKey || ev.metaKey) return;
  const dd = ev.target.closest?.('.dd--spaces');
  if (dd) {
    const rows = [...dd.querySelectorAll('.dd-item')];
    const to = rovingIndex(rows.indexOf(document.activeElement), rows.length, ev.key);
    if (to === null) return;
    ev.preventDefault();
    rows[to].focus({ preventScroll: true });
    return;
  }
  const chip = ev.target.closest?.('.space-chip');
  if (chip && ev.key === 'ArrowDown') {
    ev.preventDefault();
    if (openDd !== 'space') { chip.click(); return; }
    const rows = [...bar.querySelectorAll('.dd--spaces .dd-item')];
    const cur = rows.findIndex((r) => r.getAttribute('aria-current') === 'true');
    rows[Math.max(cur, 0)]?.focus({ preventScroll: true });
  }
});

/**
 * Задача, чиєї теки нема на цій машині, — не перемикаємо: `/api/task-switch`
 * зробив би її поточною, і всі інші запити (`/api/task`, сторінки, зʼємка)
 * почали б падати на неіснуючій теці. Повертає `true`, якщо відмовили (і
 * сказала причину тостом). Єдине місце перевірки: клік по пункту, Enter у полі
 * пошуку й картка екрана «Задачі» йдуть через неї. Список — необовʼязковий
 * другий аргумент: екран «Задачі» перевіряє по СВОЇХ свіжих даних
 * (`/api/tasks-overview`, поле `missing` те саме), а смуга — по `curTaskList`.
 */
function refuseMissingTask(id, tasks = curTaskList && curTaskList.tasks) {
  const x = (tasks || []).find((y) => y.id === id);
  if (!x || !x.missing) return false;
  toast(t('folderMissingOpen', taskKey(x)));
  return true;
}

/* ── екран «Задачі» ──────────────────────────────────────────────────────────
   Розмітку збирає `tasks-home.js` (чисті рядки); тут — усе, що торкається
   сторінки: вузол, запит, фокус, клавіші, перемикання задачі. Екран живе у
   СВОЄМУ вузлі `#tasks-home` поряд зі сценою, а не замість неї: сцену ховає
   лише правило `body.home-open` (styles.css), тож `render()` під екраном
   нічого не відновлює (розбір там само). */
const HOME_KEY = 'dc-tasks-ui';
/** Стан екрана. Вкладка, сортування, статус і чіпи переживають закриття (модуль)
 *  і перезавантаження (localStorage, у try/catch — як інші `dc-*`); запит —
 *  ні: людина, що повернулась на екран, чекає побачити всі задачі, а не вчорашній
 *  пошук. */
const homeUi = (() => {
  /* Розбір — чиста `readHomeUi` (tasks-model.js): стан 0.10.0 зберігав `profiles`, нинішній — `tags`. */
  try { return readHomeUi(JSON.parse(localStorage.getItem(HOME_KEY) || 'null')); } catch (e) { return readHomeUi(null); }
})();
function saveHomeUi() {
  try {
    localStorage.setItem(HOME_KEY, JSON.stringify({
      tab: homeUi.tab, sort: homeUi.sort, status: homeUi.status,
      tags: [...homeUi.tags], designers: [...homeUi.designers],
    }));
  } catch (e) {}
}
/** Остання відповідь `/api/tasks-overview`; до першої — `{loading}`, після збою —
 *  `{failed}` (`homeHTML` розрізняє). */
let homeData = null;
/** Лічильник запитів: відповідь, що прийшла ПІСЛЯ виходу з екрана чи після
 *  новішого запиту, не сміє перемалювати екран. */
let homeSeq = 0;
/* IME-композиція в полі пошуку: перемальовка під час неї знищила б поле і
   обірвала набір (клас пастки `panelComposing`). */
let homeComposing = false;
let homePaintPending = false;
/* Задача відкривається (запит у дорозі): другий Enter/клік не запускає друге. */
let homeOpening = false;

/* Етап Д: тимчасовий стан екрана «Задачі» — НЕ зберігається (`homeUi` пишеться в localStorage, це — ні). Скидається на вході
   на екран і на зміні простору. `newForm`: відкрита форма «Нова задача» (жива `<form>` — `newFormEl`); `ren`: id задачі, назву
   якої правлять на картці; `ask`: питання в картці `{id, kind, claude}`; `trash`: вигляд кошика. */
let homeEdit = { newForm: false, ren: null, ask: null, trash: false };
let newFormEl = null;
let newFormCtx = null;
const resetHomeEdit = () => { homeEdit = { newForm: false, ren: null, ask: null, trash: false }; newFormEl = null; newFormCtx = null; };

const homeView = () => ({ ...homeUi, now: Date.now(), edit: homeEdit });
const homeReady = () => Array.isArray(homeData && homeData.mine);
const homeNode = () => document.getElementById('tasks-home');
const homeCards = () => [...(homeNode()?.querySelectorAll('.th-card:not(#th-new-slot)') || [])];

/** Селектор елемента, який був у фокусі, — щоб повернути фокус на ТОЙ САМИЙ
 *  після перемальовки (вузол новий, фокус на ньому пропав би). */
function focusKey(a) {
  if (!a || a === document.body) return null;
  if (a.id) return `#${CSS.escape(a.id)}`;
  if (a.classList.contains('th-card')) return `.th-card[data-id="${CSS.escape(a.dataset.id)}"]`;
  /* Кнопки карток «Підключення»: дія + модуль (`retry` id не має). */
  if (a.dataset.cn) {
    return `[data-cn="${a.dataset.cn}"]${a.dataset.id != null ? `[data-id="${CSS.escape(a.dataset.id)}"]` : ''}`;
  }
  if (a.dataset.th) {
    return `[data-th="${a.dataset.th}"]${a.dataset.v != null ? `[data-v="${CSS.escape(a.dataset.v)}"]` : ''}`
      + `${a.dataset.id != null ? `[data-id="${CSS.escape(a.dataset.id)}"]` : ''}`;
  }
  return null;
}
/** `redo()` перемальовує `root`; фокус, що був усередині, вертається.
 *  Селектор може збігатись з кількома вузлами: `data-th="newtask"` стоїть двічі в
 *  порожньому просторі (голова й порожній стан). Тому запамʼятовуємо ще й ПОРЯДКОВИЙ
 *  номер серед збігів — інакше фокус з нижньої кнопки перестрибував би на верхню. */
function keepFocus(root, redo) {
  const a = document.activeElement;
  const key = root.contains(a) && a !== root ? focusKey(a) : null;
  const nth = key ? [...root.querySelectorAll(key)].indexOf(a) : -1;
  const caret = key === '#th-q' ? [a.selectionStart, a.selectionEnd] : null;
  redo();
  if (!key) return;
  const all = root.querySelectorAll(key);
  const n = all[nth] ?? all[0];
  if (!n) {
    /* Кнопка картки «Підключення» зникла разом зі своєю дією (після запису «Підключити» стало «Налаштувати»): фокус — на
       іншу кнопку тієї ж картки, а не в нікуди (закриття панелі вертає його саме сюди, ще ДО перемальовки списку). */
    if (a.dataset?.cn && a.dataset.id != null) {
      root.querySelector(`[data-cn][data-id="${CSS.escape(a.dataset.id)}"]`)?.focus({ preventScroll: true });
    }
    return;
  }
  n.focus({ preventScroll: true });
  if (caret) { try { n.setSelectionRange(caret[0], caret[1]); } catch (e) {} }
}

/** Жива форма «Нова задача» — у свій слот після перемальовки сітки: поля й набране переживають `innerHTML` сітки.
 *  `held` — елемент форми, що мав фокус ДО перемальовки: вузол вилучено з DOM разом із фокусом, тож вертаємо його сюди. */
function mountNewForm(held = null) {
  const slot = document.getElementById('th-new-slot');
  if (!slot || !newFormEl) return;
  if (newFormEl.parentNode !== slot) slot.appendChild(newFormEl);
  if (held && newFormEl.contains(held)) held.focus({ preventScroll: true });
}
/** Елемент форми «Нова задача», що зараз у фокусі (до перемальовки), або `null`. */
const heldInNewForm = () => (newFormEl && newFormEl.contains(document.activeElement) ? document.activeElement : null);

/** Повна перемальовка (відкриття, вкладка, нові дані). */
function paintHome() {
  const el = homeNode();
  if (!el) return;
  if (homeComposing) { homePaintPending = true; return; }
  homePaintPending = false;
  /* Майстер (етап 3b) — раніше за привітання: на першому запуску просторів ще нема, а майстер уже відкритий. */
  if (homePage === 'wiz') { wiz.paint(); return; }
  const top = el.scrollTop;
  /* Просторів на машині нема зовсім — замість списку привітання (дорога звідси одна:
     створити перший простір). Рішає `spacesResp`, а не `homeData`: порожній `mine` без
     простору — це «нема де», а не «нічого не знайдено». */
  keepFocus(el, () => {
    const held = heldInNewForm();
    el.innerHTML = needsWelcome(spacesResp) ? welcomeHTML()
      : homePage === 'conn' ? connPageHTML(connView()) : homeHTML(homeView(), homeData);
    mountNewForm(held);
  });
  el.scrollTop = top;
}
/** Лише чіпи й сітка — поле пошуку лишається тим самим вузлом. */
function paintHomeLower() {
  const lower = document.getElementById('th-lower');
  if (!lower) return;
  keepFocus(lower, () => {
    const held = heldInNewForm();
    lower.innerHTML = homeGridHTML(homeView(), homeData);
    mountNewForm(held);
  });
}

/**
 * `spaces: false` — перелік просторів щойно перечитано (`afterSpaceChange`, `showNoTask`): другий
 * запит поспіль нічого б не додав.
 */
async function loadHome(refresh = false, { spaces = true } = {}) {
  const seq = ++homeSeq;
  const gen = taskSwitchGen;
  try {
    /* Простори — ПЕРШИМИ й послідовно: вони лікують висячий `current`, а відповідь
       екрана про задачі має бути вже про вилікуваний. Тут же вирішується привітання
       (просторів нема — списку нема що тягнути) й оновлюється фішка: екран — головне
       місце, де цей перелік міг змінитись без нашого відома (агент завів простір). */
    if (spaces) {
      const healed = await loadSpaces({ heal: true });
      if (seq !== homeSeq || !homeOpen) return;
      /* Лікування — зміна простору, якої ми не робили: задача й усе пер-просторове в
         памʼяті — з видаленого. Забуваємо й починаємо екран заново (він візьме список уже
         вилікуваного простору). */
      if (healed) { await resetSpaceState({ reload: false }); if (homeOpen) enterHome({ spaces: false }); return; }
    }
    paintBar();
    if (needsWelcome(spacesResp)) {
      homeData = { current: null, mine: [], team: null, space: null };
      paintHome();
      return;
    }
    const r = await api(`/api/tasks-overview${refresh ? '?refresh=1' : ''}`);
    if (seq !== homeSeq || !homeOpen) return;
    /* Переключили задачу, поки відповідь летіла, — її `current` застарів. */
    if (gen === taskSwitchGen) currentTaskId = r.current ?? currentTaskId;
    else r.current = currentTaskId;
    homeData = r;
  } catch (e) {
    if (seq !== homeSeq || !homeOpen) return;
    const why = (e && e.message) || String(e);
    /* Файл задач простору не читається / реєстр битий: причина мовою глядача — ще й
       смугою помилки (як на екрані задачі), а не лише сирим текстом сервера в банері. */
    const key = readErrKey(e?.code);
    if (key) { tasksErr = true; tasksErrKey = key; paintBar(); }
    /* Дані вже є — лишаємо їх і додаємо банер (`loadError`); `{failed}` лише коли
       показувати нічого. Повторний запит, що не вдався, не стирає екран. */
    homeData = homeReady() ? { ...homeData, loadError: why } : { failed: why };
    paintHome();
    return;
  }
  /* Огляд прочитався — простір читається: червона смуга про файл задач / реєстр, яку виставив
     попередній збій (цей самий `catch` вище або `render()`), більше не про правду. Інші
     причини (чужий процес на порту) від успіху огляду не минають — їх не чіпаємо. */
  if (tasksErr && isReadErrKey(tasksErrKey)) { tasksErr = false; tasksErrKey = null; paintBar(); }
  if (pruneFilters(homeUi, homeData)) saveHomeUi();
  paintHome();
}

/** `spaces: false` — не перепитувати перелік просторів (див. `loadHome`). `page` — `tasks` («Задачі») чи `conn`
 *  («Підключення»); без нього відкрита сторінка лишається, закрита відкривається на «Задачах». */
function enterHome({ spaces = true, page } = {}) {
  if (cmtOpen) setCommentsOpen(false);   // екран «Задачі» не про макет: панель і режим коментування закриваємо
  /* Явна сторінка — це навігація людини: вхід на «Підключення», що ще чекає перелік просторів, відступає (`enterConnections`). */
  if (page !== undefined) connEntrySeq += 1;
  /* Пішли із задачі на екран «Задачі»: відкладений повтор статусу синку не мусить опитувати й малювати смугу під оверлеєм
     (`leaveHome` поверне його, якщо стан лишився «зайнято»). */
  cancelGlRetry();
  const was = homeOpen;
  /* Сторінка: явна (`home` — «Задачі», `conn` — «Підключення»), інакше відкрита лишається відкритою (перемикання
     простору й запис модулів кличуть `enterHome` через `afterSpaceChange`, і людина лишається там, де була). */
  const next = page ?? (was ? homePage : 'tasks');
  /* Бічна панель належить лише «Підключенню»: вихід на «Задачі» її закриває (фокус не вертаємо — його бере екран). */
  if (next !== 'conn') closeCnDrawer({ focus: false });
  /* Пішли з майстра будь-яким шляхом (⌘K, агент) — його стан більше не потрібен: простір, якщо створено, уже є. */
  if (next !== 'wiz') wiz.reset();
  /* Секрети кроку 3 живуть лише у `.value` полів, а `reset()` DOM не чистить: розмітка майстра зникає разом зі
     сторінкою — ДО перемальовки нижче (і до будь-якого await). */
  if (homePage === 'wiz' && next !== 'wiz') homeNode()?.querySelector('.wz')?.remove();
  /* Свіжий вхід на сторінку (з-поза оверлею чи з іншої сторінки) — зі «вантажу», а не з чужого списку; повторний
     вхід на ту саму (`afterSpaceChange`) лишає показане, поки нове летить. */
  const fresh = !was || next !== homePage;
  homePage = next;
  /* Чистий перегляд ховає смугу, а екран під нею (`html.cv-clean #tasks-home`)
     теж — вхід із нього (⌘K) дав би порожній екран без дороги назад. */
  if (cleanView) toggleClean(false);
  homeComposing = false; homePaintPending = false;
  homeOpen = true;
  openDd = null;
  document.body.classList.add('home-open');
  if (!was) { homeUi.q = ''; resetHomeEdit(); }
  const el = ensureHome();
  el.hidden = false;
  paintBar();
  if (homePage === 'wiz') {
    /* Майстер малює себе сам (`wiz.paint` через `paintHome`); фокус ставить `openWizard`/крок. Запізніле `loadHome` не
       сміє перемалювати сторінку. */
    homeSeq += 1;
    paintHome();
    return;
  }
  if (homePage === 'conn') {
    /* Запізнілий `loadHome` (його відповідь летіла, поки людина йшла на «Підключення») не сміє перемалювати сторінку. */
    homeSeq += 1;
    /* Свіжий вхід забуває й ПРОСТІР попереднього візиту: «вантаження» малює заголовок поточного простору (`connSpace`
       без `spaceId` бере `currentSpace`), а `loadConn` побачить зміну й почистить решту (зайнятість, панель). */
    if (fresh) { connState.spaceId = null; connState.list = null; connState.failed = null; connFocusPending = true; }
    paintHome();
    loadConn({ spaces });
    return;
  }
  /* Старі дані (з попереднього відкриття) показуємо одразу, нові їх замінять:
     порожнє «вантажу» на кожен вхід — це блимання, яке нікому не потрібне. */
  /* `space` у «вантажу»: заголовок («Задачі · X») і ховання вкладки «Команда»
     вже тепер, без мигання, поки відповідь у дорозі (`homeHTML`, `loading`). */
  if (!homeReady()) homeData = { loading: true, space: spaceNow() };
  else if (currentTaskId) homeData = { ...homeData, current: currentTaskId };
  paintHome();
  (el.querySelector('#th-q') ?? el.querySelector('[data-th="spacenew"]'))?.focus({ preventScroll: true });
  loadHome(false, { spaces });
}

async function leaveHome() {
  closeCnDrawer({ focus: false });
  connEntrySeq += 1;                                         // вхід на «Підключення», що ще чекає перелік, відступає
  /* Майстер (3b): стан скинуто, а розмітку прибрано з DOM — оверлей лише ховається, і поля кроку 3 (секрети живуть у
     їхніх `.value`) лишились би в документі. ДО `await render()` нижче. */
  wiz.reset();
  homeNode()?.querySelector('.wz')?.remove();
  homeSeq += 1;
  homeComposing = false; homePaintPending = false;
  homeOpen = false;
  openDd = null;
  document.body.classList.remove('home-open');
  const el = homeNode();
  if (el) el.hidden = true;
  /* ⛔ Рамку тут НЕ перезавантажуємо окремо: `render()` присвоює `frame.src` обраної сторінки, а присвоєння і є
     перезавантаженням — тож документ із новим адаптером коментарів і токенами інспектора прийде сам (модулі могли
     змінитись, поки оверлей був відкритий: `afterModulesChange` рамку під ним не чіпає). Окремий `reloadFrame()` після
     `render()` перезавантажував СТАРИЙ документ поверх щойно відкритої іншої задачі (404 у рамці), а при простому
     «назад» ще й робив другий запит `/commented`. */
  await render();
  /* Вернулись до задачі, а статус синку лишився «зайнято» без відкладеного повтору (його скасував `enterHome`) — повертаємо. */
  if (glCache?.busy && !glBusyTimer) scheduleGlRetry(glKeyNow());
  /* Фокус вертається на активну вкладку (чи логотип) — те, чим екран відкривали: вузол, на якому він
     був (картка, поле), тепер схований, і клавіатура лишилась би «в нікуди». */
  (tabsEl.querySelector('[data-act="tab"][aria-current]') ?? tabsEl.querySelector('[data-act="home"]'))?.focus({ preventScroll: true });
}

/* Екран «Задачі» відкритий, а людина була деінде — у терміналі, де агент заводить простори й
   задачі тим самим API. Без перечитування привітання лишалось би «просторів нема», а список —
   старим, доки людина не клікне щось сама. `focus` вікна й `visibilitychange` приходять парою
   за одне повернення — `shouldRefreshHome` пропускає другий; застарілі відповіді відкидає
   сам `loadHome` (`homeSeq`). */
let homeRefreshedAt = 0;
/* «Спробувати ще» (`loadHome(true)`) у польоті: звичайне перечитування з фокуса його б перебило
   (`homeSeq`), і повтор лишився б без примусу. */
let homeForced = false;
async function retryHome() {
  homeForced = true;
  try { await loadHome(true); } finally { homeForced = false; }
}
function refreshHomeOnReturn() {
  const now = Date.now();
  if (!shouldRefreshHome({ open: homeOpen, visible: document.visibilityState === 'visible', last: homeRefreshedAt, now, forced: homeForced })) return;
  /* Майстер (3b) тримає свої дані сам. Штамп не витрачаємо: перечитування потрібне вже на «Задачах», куди людина вийде. */
  if (homePage === 'wiz') return;
  homeRefreshedAt = now;
  /* На «Підключенні» агент міг змінити модулі через API — перечитуємо їх, а не список задач. */
  homePage === 'conn' ? loadConn() : loadHome();
}
window.addEventListener('focus', refreshHomeOnReturn);
document.addEventListener('visibilitychange', refreshHomeOnReturn);

/** Відкрити задачу з картки: нема теки — причина тостом і ми лишаємось; уже
 *  поточна — просто вийти з екрана; інакше переключити й вийти. */
async function homeOpenTask(id) {
  if (homeOpening || !id) return;
  if (refuseMissingTask(id, homeData && homeData.mine)) return;
  homeOpening = true;
  try {
    /* Порівнюємо з `currentTaskId` (див. його опис): ні `curTaskList`, ні
       `homeData.current` самі по собі не свіжі — перший оновлює лише `render()`,
       другий лише відповідь екрана, яка при відкритті ще в дорозі. */
    if (id !== currentTaskId && !(await switchTask(id))) return;
    await leaveHome();
  } finally { homeOpening = false; }
}

function ensureHome() {
  let el = homeNode();
  if (el) return el;
  el = document.createElement('div');
  el.id = 'tasks-home';
  el.hidden = true;
  document.body.appendChild(el);
  wireHome(el);
  return el;
}

function wireHome(el) {
  el.addEventListener('click', (ev) => {
    /* Посилання «Превʼю ↗» — своя навігація в новій вкладці: без цього рядка клік
       по ньому долітав би до картки й ще й відкривав би задачу. */
    if (ev.target.closest('a')) return;
    /* Сторінка майстра (3b) — усі її кліки в контролері; обробники «Задач» і «Підключення» її не бачать. */
    if (homePage === 'wiz') { wiz.click(ev); return; }
    /* Кнопки карток і помилки сторінки «Підключення» (`data-cn` + `data-id`). */
    const c = ev.target.closest('[data-cn]');
    if (c) { connAction(c.dataset.cn, c.dataset.id); return; }
    const b = ev.target.closest('[data-th]');
    if (!b) return;
    const v = b.dataset.v;
    switch (b.dataset.th) {
      case 'open': homeOpenTask(b.dataset.id); break;
      case 'tab':
        /* Порівнюємо з вкладкою, що справді малюється (`effectiveTab`): у просторі без
           «Команди» збережена `team` читається як `mine`, і клік по єдиній вкладці
           «Мої» не має переписувати збережений вибір (він живий у ЛІГА). */
        if (effectiveTab(homeUi, homeData) === v) break;
        homeUi.tab = v; saveHomeUi();
        paintHome();
        break;
      case 'newtask': openNewTaskCard(); break;
      /* ⛔ «Мітки» — кнопка ВСЕРЕДИНІ картки `data-th="open"`: `closest('[data-th]')` вище бере найближчий — саме її, тож задача не відкривається. */
      case 'tags': editTaskTags(b.dataset.id); break;
      case 'conn': enterConnections(); break;
      case 'spacenew': openWizard(); break;
      case 'spaceopen': openWizard({ folderFirst: true }); break;
      case 'status': homeUi.status = v; saveHomeUi(); paintHomeLower(); break;
      case 'tag': case 'designer': {
        const set = b.dataset.th === 'tag' ? homeUi.tags : homeUi.designers;
        if (!set.delete(v)) set.add(v);
        saveHomeUi(); paintHomeLower();
        break;
      }
      case 'reset':
        homeUi.q = ''; homeUi.status = 'all'; homeUi.tags.clear(); homeUi.designers.clear();
        saveHomeUi(); paintHome();
        el.querySelector('#th-q')?.focus({ preventScroll: true });
        break;
      case 'retry': retryHome(); break;
    }
  });
  el.addEventListener('input', (ev) => {
    if (homePage === 'wiz') { wiz.input(ev); return; }
    if (ev.target.id !== 'th-q' || ev.isComposing) return;
    homeUi.q = ev.target.value;
    paintHomeLower();
  });
  el.addEventListener('compositionstart', (ev) => { if (ev.target.id === 'th-q') homeComposing = true; });
  el.addEventListener('compositionend', (ev) => {
    if (ev.target.id !== 'th-q') return;
    homeComposing = false;
    homeUi.q = ev.target.value;
    if (homePaintPending) paintHome(); else paintHomeLower();
  });
  /* Радіо кроків 2 і 4 майстра працюють на `change`, а не на `input`. */
  el.addEventListener('change', (ev) => {
    if (homePage === 'wiz') { wiz.input(ev); return; }
    if (ev.target.id !== 'th-sort') return;
    homeUi.sort = ev.target.value; saveHomeUi(); paintHomeLower();
  });
  /* Відправка форм майстра (Enter у полі й клік по головній кнопці — один шлях). */
  el.addEventListener('submit', (ev) => { if (homePage === 'wiz') wiz.submit(ev); });
  /* `error` не спливає — ловимо на захопленні. Кадр, що не завантажився
     (вічний кеш на файлі, якого вже нема), міняємо на заглушку, а не лишаємо
     картку зі значком зламаного зображення. */
  el.addEventListener('error', (ev) => {
    const im = ev.target;
    if (!im || !im.classList || !im.classList.contains('th-img')) return;
    const tpl = document.createElement('template');
    tpl.innerHTML = thumbBrokenHTML();
    im.replaceWith(tpl.content.firstChild);
  }, true);
}

/* ── сторінка «Підключення» (етап 3a) ────────────────────────────────────────────────────────────────────
   Друга сторінка оверлею `#tasks-home` (`homePage === 'conn'`): модулі поточного простору за ролями. Розмітку дають
   `connections-view.js` і `connections-model.js` (чисті, без мережі); тут — стан, запити й дії карток. Кожен запит
   несе ЯВНИЙ `space` (`connState.spaceId`): агент міг перемкнути активний простір паралельно, а запис мусить піти
   туди, що людина бачить. */

const connOpen = () => homeOpen && homePage === 'conn';
/* Простір, чиї картки на сторінці: запис реєстру за `connState.spaceId`. `currentSpace` — лише поки сторінка ще не
   знає свого простору (перший вхід). Не «поточний зараз»: `spacesResp` міг змінитись від дропдауна чи ⌘K без
   перечитування сторінки, і заголовок та «Зараз» чужого простору опинились би над картками цього. */
const connSpace = () => (connState.spaceId == null
  ? currentSpace(spacesResp)
  : (Array.isArray(spacesResp?.spaces) ? spacesResp.spaces : []).find((x) => x.id === connState.spaceId) ?? null);
const connView = () => ({ space: connSpace(), list: connState.list, notes: connState.notes, failed: connState.failed, busy: connState.busy });

/**
 * Вхід на «Підключення» поточного простору. Без простору входів нема (шар вимкнено, привітання). `role` — вести до картки модуля
 * цієї ролі («Налаштувати…» синку → `vcs`): після першого списку на неї сяде фокус (`focusConnLanding`), а сторінка прокрутиться;
 * без ролі — як завжди (перша кнопка першої картки). Прапорець ставимо й тоді, коли сторінка вже відкрита: `enterHome` ставить
 * його лише на свіжий вхід.
 *
 * Перелік просторів на свіжозавантаженій сторінці ніхто не читає (старт питає задачу й синк, а `/api/spaces` вантажать дропдаун,
 * палітра й екран «Задачі»): `spacesResp` порожній, а простір смуга знає з `curTask.space`. Вхід, що прийшов із такого стану
 * (`glsetup` зі смуги; кнопка «Підключення» на «Задачах», що ще вантажаться; клік по «Підключення…» в дропдауні, що випередив
 * власну відповідь), мовчав — тож порожній перелік ЧИТАЄМО тут. Готовий (навіть `{off:true}` чи без поточного простору) вирішує
 * сам: зайвого запиту нема, мовчання — як було. Щойно прочитаний перелік `loadConn` вдруге не питає (`spaces: false`, як після
 * `afterSpaceChange`).
 *
 * Поки перелік летить, людина могла піти: логотип чи майстер (`connEntrySeq`), інша задача чи простір (`taskSwitchGen`), другий
 * клік (його вхід — останній, перший відступає: навігація рівно одна). Тоді виходимо мовчки — вона вже вирішила інакше. Перелік,
 * що не прочитався (реєстр не читається, сервер мовчить), — не мовчання: людина клікнула й чекає, тож кажемо причину. Якщо ж
 * `spacesResp` порожній тому, що новіший запит переліку (дропдаун чи палітра) відкинув нашу відповідь через `spacesSeq`, — це не збій,
 * а чужий запит у польоті: теж мовчимо.
 */
async function enterConnections(role = '') {
  const seq = ++connEntrySeq;
  const cold = spacesResp === null;
  if (cold) {
    const gen = taskSwitchGen;
    const load = loadSpaces();
    const mine = spacesSeq;
    await load;
    if (seq !== connEntrySeq || gen !== taskSwitchGen) return;
    if (spacesResp === null) { if (spacesSeq === mine) tell(t('tasksErrSpaces')); return; }
  }
  if (!currentSpace(spacesResp)) return;
  connFocusRole = role;
  if (role) connFocusPending = true;
  enterHome(cold ? { page: 'conn', spaces: false } : { page: 'conn' });
}

/**
 * Куди сідає перший фокус сторінки «Підключення»: кнопка картки модуля ролі `role` (постачальник, інакше перша картка секції —
 * `roleCardId`; фокус із прокруткою до неї), а без ролі чи без такої картки — перша кнопка першої картки або «Спробувати ще»
 * (без прокрутки, як було до 4a).
 */
function focusConnLanding(role) {
  const home = homeNode();
  const id = role ? roleCardId(role, connSpace()?.capabilities, connState.list) : null;
  const card = id ? home?.querySelector(`.cn-card[data-id="${CSS.escape(id)}"]`) : null;
  const inCard = card?.querySelector('[data-cn]:not([disabled])') ?? null;
  (inCard ?? home?.querySelector('.cn-card [data-cn], [data-cn="retry"]'))?.focus({ preventScroll: !inCard });
}

/**
 * Список модулів поточного простору. `spaces: false` — перелік просторів щойно перечитано (`afterSpaceChange`).
 * Простору не стало (вилучили руками чи агентом) — на «Задачі»: там і лікування висячого `current`, і привітання.
 * Інший простір, ніж показаний (перемкнули фішкою чи агент), — спершу «вантажу», а не чужі картки під новою назвою.
 */
async function loadConn({ spaces = true } = {}) {
  const seq = ++connState.seq;
  if (spaces) {
    await loadSpaces();
    if (seq !== connState.seq || !connOpen()) return;
    paintBar();
  }
  const sp = currentSpace(spacesResp);
  if (!sp) { enterHome({ page: 'tasks' }); return; }
  if (sp.id !== connState.spaceId) {
    /* Панель, відкрита для іншого простору, не лишається: людина свідомо перейшла (питання не треба), а запис із неї
       пішов би в простір, якого вона вже не бачить. */
    closeCnDrawer({ focus: false });
    connState.spaceId = sp.id; connState.list = null; connState.notes = []; connState.failed = null; connState.busy.clear();
    paintHome();
  }
  try {
    const r = await api(`/api/modules?space=${encodeURIComponent(sp.id)}`);
    if (seq !== connState.seq || !connOpen()) return;
    connState.list = Array.isArray(r?.modules) ? r.modules : [];
    connState.notes = Array.isArray(r?.notes) ? r.notes : [];
    connState.failed = null;
  } catch (e) {
    if (seq !== connState.seq || !connOpen()) return;
    connState.failed = { code: e?.code ?? null, message: String(e?.message || e) };
  }
  paintHome();
  if (connFocusPending) {
    connFocusPending = false;
    const role = connFocusRole;
    connFocusRole = '';
    /* Не з-під палітри чи діалогу: їм фокус належить. */
    if (!paletteOverlay && !askUp()) focusConnLanding(role);
  }
}

/**
 * Клік по кнопці картки чи помилки сторінки (`data-cn`). Дія над модулем, що вже в польоті, — ігнор.
 *
 * Відкрита панель стоїть на заваді двом діям: ІНША панель (`enable`/`configure`) не мовчки з'їдає першу, а «Вимкнути»
 * модуля, чия панель відкрита, не лишає панель, що потім «зберегла» б налаштування вимкненого модуля. В обох випадках
 * панель спершу закривається — з тим самим питанням «Відкинути зміни?», коли форма брудна (`dismissCnDrawer`); під час
 * запиту панелі дія ігнорується. «Перевірити» панелі не заважає (перевіряється збережене, форма не чіпається), а
 * «Вимкнути» ІНШОГО модуля — теж (його панелі нема). Після питання світ міг змінитись (простір, список, зайнятість) —
 * картка перечитується зі свіжого списку, і дія йде далі лише в тому ж просторі.
 */
async function connAction(act, id) {
  if (act === 'retry') { loadConn(); return; }
  let e = (connState.list || []).find((x) => x.id === id);
  if (!e || connState.busy.has(id)) return;
  if (act === 'check') { connCheck(e); return; }
  if (cnDrawer && (act !== 'disable' || cnDrawer.id === id)) {
    const spaceId = connState.spaceId;
    if (!(await dismissCnDrawer())) return;
    if (!connOpen() || connState.spaceId !== spaceId) return;
    e = (connState.list || []).find((x) => x.id === id);
    if (!e || connState.busy.has(id)) return;
  }
  if (act === 'enable') openCnDrawer(e, 'enable');
  else if (act === 'configure') openCnDrawer(e, 'edit');
  else if (act === 'disable') connDisable(e);
  else if (act === 'trust' || act === 'trustinfo') connTrust(e);
}

/** «Перевірити» на картці: вердикт міняє лише `status` модуля — перечитуємо сторінку. */
async function connCheck(e) {
  const spaceId = connState.spaceId;
  connState.busy.set(e.id, 'check'); paintHome();
  try { await checkPost('/api/module-check', { space: connState.spaceId, id: e.id }, e); }
  catch (err) { const r = refusalView(err); tell([t(r.key), r.detail].filter(Boolean).join('\n\n')); }
  finally { connState.busy.delete(e.id); }
  await loadConn();
  if (connOpen() && connState.spaceId === spaceId) refocusCard(e.id, 'check');
}

/**
 * «Вимкнути»: питання з наслідками для ролей, які модуль зараз виконує; далі — як після будь-якої зміни модулів.
 *
 * ⛔ Простір береться ДО питання. Поки людина читає діалог, вікно може отримати фокус (`refreshHomeOnReturn` →
 * `loadConn`) і перевести сторінку в інший простір (агент перемкнув активний) — і `connState.spaceId` після відповіді
 * вказував би вже на ТОЙ простір: «Так» вимкнуло б у ньому вбудований модуль, якого людина не бачила. Тому знімок
 * `spaceId` (і запис простору для наслідків) — до `askYesNo`, а після нього сторінка мусить показувати той самий простір,
 * інакше не пишемо нічого (ні туди, ні сюди).
 */
async function connDisable(e) {
  const spaceId = connState.spaceId;
  const sp = connSpace();
  const lines = disableConsequences(e, sp).map((c) =>
    (c.consKey ? t(c.consKey) : t('cnDisableNone', roleTitle(c.role), c.noneKey ? t(c.noneKey) : '')));
  if (!(await askYesNo([t('cnDisableAsk', modName(e)), ...lines].join('\n\n'), { yes: t('cnDisable'), danger: true }))) return;
  if (!connOpen() || connState.spaceId !== spaceId) return;
  connState.busy.set(e.id, 'disable'); paintHome();
  try { await postForm('/api/module-disable', { space: spaceId, id: e.id }); }
  catch (err) {
    connState.busy.delete(e.id); paintHome();
    const r = refusalView(err); tell([t(r.key), r.detail].filter(Boolean).join('\n\n'));
    return;
  }
  /* Зайнятість знімаємо ПІСЛЯ перечитування: застаріла картка (з кнопкою «Вимкнути» вимкненого вже модуля) не
     клікається, поки свіжий список летить. */
  try { await afterModulesChange(); }
  finally {
    connState.busy.delete(e.id); paintHome();
    if (connOpen() && connState.spaceId === spaceId) refocusCard(e.id, 'disable');
  }
}

/**
 * Фокус на кнопку картки після перемальовки списку. Натиснута кнопка під час запиту вимикається (зайнятість) і
 * перемальовка її замінює — фокус пропадає на `body`, і клавіатура лишається «в нікуди». Повертаємо ЛИШЕ коли
 * він справді втрачений (не крадемо в того, хто вже клікнув деінде) і над сторінкою нема палітри чи діалогу.
 * Спершу та сама дія; її може вже не бути («Вимкнути» → лишилась «Підключити») — тоді будь-яка кнопка тієї ж картки.
 */
function refocusCard(id, act) {
  const a = document.activeElement;
  if ((a && a !== document.body && a.isConnected) || paletteOverlay || askUp()) return;
  const home = homeNode();
  const sel = CSS.escape(id);
  (home?.querySelector(`[data-cn="${act}"][data-id="${sel}"]:not([disabled])`)
    ?? home?.querySelector(`[data-cn][data-id="${sel}"]:not([disabled])`))?.focus({ preventScroll: true });
}

/**
 * Модулі змінились (вмикання, налаштування, вимкнення). Постачальник ролі й його налаштування — частина простору:
 * смуга (кнопки публікації) мусить побачити нові `capabilities`, а рамка (адаптер коментарів вбудовується в сторінку
 * при віддачі) й інспектор (токени) — новий документ. ПРОСТІР при цьому не змінився, тож це ЛЕГКИЙ шлях, а не
 * `afterSpaceChange`: той скидає пер-просторове (обрана ітерація, фільтри «Задач», плашки публікації), і людина, що
 * вимкнула модуль і повернулась до задачі, бачила б іншу ітерацію. Тут: простори перечитати → `render()` під оверлеєм
 * (той самий простір — нічого не скидає; свіжі `capabilities` → смуга; `keepFrame`: схована рамка не перезавантажується
 * вдруге) → список модулів. Рамку оновить сам `render()` при виході з оверлею (`leaveHome`): він присвоює `frame.src`
 * обраної сторінки — РІВНО один раз і саме тієї задачі, що відкрита. Якщо `render()` вже сам запустив `loadConn`
 * (задачі нема → `showNoTask` → `enterHome`), другого запиту не робимо.
 */
async function afterModulesChange() {
  /* ПЕРШИМ: коментатор «Огляду» тримає свій шар за ключем «ітерація | канал», а ключ не знає, що постачальник коментарів чи
     його адреса щойно змінились. Без цього рядка `render()` нижче (він у режимі «Огляд» кличе `ovc.enter()`) лишив би живий
     шар на старому сервісі, і нові піни йшли б туди до перезавантаження сторінки (фінальне ревʼю 0.5.0). Раніше за
     `loadSpaces`: інвалідація нічого не читає, а старий шар тим часом не повинен опитувати сервіс, якого вже нема. */
  ovc.invalidate();
  await loadSpaces();
  const seq = connState.seq;
  /* `keepFrame` — лише поки оверлей відкритий (`homeOpen`): рамка тоді схована, а при виході `leaveHome` → `render()` її
     однаково перезавантажить. Якщо людина встигла піти з оверлея, поки запис летів, ЖОДЕН подальший `leaveHome` уже не
     настане, а попередній `render()` взяв ще СТАРІ `capabilities` — рамку мусимо оновити тут. Саме `homeOpen`, а не
     `connOpen()`: з оверлея, відкритого на «Задачах», вихід теж іде через `leaveHome`, тож зайве друге перезавантаження
     було б марним. */
  await render({ keepFrame: homeOpen });
  /* Синк із git — ПІСЛЯ `render()`, не відразу за `loadSpaces()`: `spaceNow()` бере `curTask?.space`, який оновлює саме
     `render()`, тож раніше він читав би старі `capabilities` (щойно підключений модуль `git-sync` лишався б «без синку»,
     вимкнений — із застарілою зоною). Роль зникла — `refreshGitlab` скидає `glCache`. */
  await refreshGitlab();
  paintBar();
  if (connOpen() && connState.seq === seq) await loadConn({ spaces: false });
}

/* ── довіра своєму модулю (етап 3c) ──────────────────────────────────────────────────────────────────────
   Діалог — `askForm` з розміткою `trust-view.js`; ним користуються картки «Підключень» (`connTrust`) і крок 2 майстра
   (`deps.openTrust`). Межа «довіряє лише людина» — системне вікно ОС, яке сервер показує ПІСЛЯ «Довіряю» і чекає до
   120 с, тож запит іде через `trustPost` зі своєю стелею, а не через `formApi` (20 с). */

/** `POST /api/module-trust` зі стелею `TRUST_POST_TIMEOUT_MS`: обрив — `code: 'timeout'`, як у `formApi`. */
function trustPost(body) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TRUST_POST_TIMEOUT_MS);
  return api('/api/module-trust', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctl.signal,
  })
    .catch((e) => { throw e?.name === 'AbortError' ? Object.assign(new Error('timeout'), { code: 'timeout' }) : e; })
    .finally(() => clearTimeout(timer));
}

/**
 * Діалог довіри модулю `entry` простору `spaceId` (зафіксованого ВИКЛИКАЧЕМ до відкриття: агент, що перемкнув активний
 * простір, діалог не збиває). `true` — довіру видано (модулі вже перечитано, `afterModulesChange`).
 *   — «Довіряю» → рядок «Підтвердіть у системному вікні…» → `POST /api/module-trust {space, id, hash, lang}`;
 *   — `module-changed` (тека змінилась, поки діалог був відкритий) → діалог закривається й відкривається знову зі
 *     свіжими даними та рядком угорі; але лише коли діалог ще був НАШ: перебитий чужим `overlay()` посеред запиту
 *     (`interrupted`) знову не відкривається — він скасував би чужий оверлей (`tell`, який людина читала), тож лише
 *     перечитування модулів і `false`;
 *   — інша відмова (`trust-declined`, `trust-no-confirm`, `trust-busy`, `role-taken`…) → текст у діалозі, він лишається;
 *   — «Забрати довіру» → діалог закривається (питання поверх нього перебило б його), далі `untrustFlow`;
 *   — `state: trusted` (картка застаріла: довіру видали, поки йшло перечитування) → діалогу нема: лише `afterModulesChange`
 *     і `true`, системне вікно вдруге не питаємо;
 *   — `flight` — запит довіри в польоті: його результат дочікується й тоді, коли `askForm` вже віддав `null` (діалог
 *     перебито), бо сервер довіру міг видати; відмова перебитого діалогу тиха (`false`).
 * Усі `true` — модулі вже перечитано; усі `false` — довіри не видано (скасовано, відмова, відкликання виконано всередині).
 */
async function openTrust(entry, spaceId) {
  let reopened = false;
  for (;;) {
    let d;
    try {
      d = (await formApi(`/api/module-trust?space=${encodeURIComponent(spaceId)}&id=${encodeURIComponent(entry.id)}`))?.trust;
    } catch (err) {
      const r = refusalView(err); tell([t(r.key), r.detail].filter(Boolean).join('\n\n'));
      return false;
    }
    if (!d) return false;
    /* Картка застаріла: тека вже довірена (довіру видали, поки йшло перечитування модулів). Системне вікно вдруге
       питати нема сенсу — лише оновлюємо список. */
    if (d.state === 'trusted') { await afterModulesChange(); return true; }
    let again = false;
    let untrust = false;
    let granted = false;
    /* Запит довіри в польоті. `overlay()` може скасувати діалог посеред запиту (`askForm` тоді віддає `null`), а сервер
       довіру вже видав — тож результат запиту дочікуємо окремо, а не покладаємося на те, що `askForm` дочекався його. */
    let flight = null;
    /* `landed` — запит у польоті завершився (діалог дочекався `onSubmit`). Якщо `askForm` повернувся, а запит ще летить —
       діалог перебито ззовні (`interrupted` нижче): «Скасувати» під час запиту заблоковано `aria-busy`, а інакше `askForm`
       дочекається `onSubmit`. */
    let landed = false;
    await askForm(() => trustDialogHTML({ ...d, reopened }), {
      onMount: (form) => {
        /* «Забрати довіру» сама діалогу не відповідає: позначка + «Скасувати». Під час запиту (`aria-busy`) — нічого:
           «Скасувати» тоді не закриває, а позначка лишилась би й спрацювала б після успішної довіри. */
        form.querySelector('[data-tr="untrust"]')?.addEventListener('click', () => {
          if (form.getAttribute('aria-busy') === 'true') return;
          untrust = true;
          form.querySelector('[data-a="cancel"]')?.click();
        });
      },
      onSubmit: async (_vals, ctl) => {
        /* Нова відправка в тому самому діалозі (після відмови системного вікна) — новий політ: `landed` скидаємо. */
        landed = false;
        flight = (async () => {
          const wait = ctl.form.querySelector('[data-tr-wait]');
          if (wait) wait.hidden = false;
          try {
            await trustPost({ space: spaceId, id: d.id, hash: d.hash, lang: getLang() });
            granted = true;
            return undefined;
          } catch (err) {
            if (err?.code === 'module-changed') { again = true; return undefined; }
            const r = refusalView(err);
            /* Власні тексти відмов системного вікна вичерпні: технічна деталь сервера (англійською) в українському
               діалозі зайва. */
            if (['trust-declined', 'trust-no-confirm', 'trust-busy', 'trust-needs-ui', 'trust-unreadable'].includes(err?.code)) return t(r.key);
            /* Мережевий збій чи відповідь без впізнаваного коду: «Не вдалося зберегти» тут недоречне — нічого не зберігається. */
            if (r.key === 'cnRefGeneric') return t('errFailed', r.detail);
            return [t(r.key), r.detail].filter(Boolean).join(' — ');
          } finally {
            if (wait) wait.hidden = true;
            landed = true;
          }
        })();
        return flight;
      },
      focusBack: () => homeNode()?.querySelector(`[data-cn][data-id="${CSS.escape(entry.id)}"]:not([disabled])`) ?? null,
    });
    const interrupted = flight !== null && !landed;
    if (flight) await flight;
    if (untrust) { await untrustFlow(entry, spaceId); return false; }
    /* Діалог перебито чужим оверлеєм: відкривати знову не можна (скасує чужий оверлей) — лише свіжий список модулів. */
    if (again && interrupted) { await afterModulesChange(); return false; }
    if (again) { reopened = true; continue; }
    if (!granted) return false;
    toast(t('cnToastTrusted', modName(entry)));
    await afterModulesChange();
    return true;
  }
}

/**
 * «Забрати довіру»: питання (небезпечна дія; для ввімкненого — які ролі перестануть працювати), далі
 * `POST /api/module-untrust` у простір `spaceId`, зафіксований ДО питання (як `connDisable`). `space.json` не змінюється.
 */
async function untrustFlow(entry, spaceId) {
  const name = modName(entry);
  const roles = (entry.roles || []).map(roleTitle).join(', ');
  const lines = [t('cnUntrustAsk', name), ...(entry.enabled === true && roles ? [t('cnUntrustRole', roles)] : []), t('cnUntrustKeeps')];
  if (!(await askYesNo(lines.join('\n\n'), { yes: t('cnUntrust'), danger: true }))) return false;
  try { await postForm('/api/module-untrust', { space: spaceId, id: entry.id }); }
  catch (err) { const r = refusalView(err); tell([t(r.key), r.detail].filter(Boolean).join('\n\n')); return false; }
  toast(t('cnToastUntrusted', name));
  await afterModulesChange();
  return true;
}

/** «Довіритись…» / «Чому не можна…» на картці: діалог для простору сторінки (знімок до відкриття), потім фокус на картку. */
async function connTrust(e) {
  const spaceId = connState.spaceId;
  await openTrust(e, spaceId);
  if (connOpen() && connState.spaceId === spaceId) refocusCard(e.id, 'trust');
}

/* ── бічна панель «Підключення» (`#cn-drawer`) ───────────────────────────────────────────────────────────
   Окремий вузол поза `#tasks-home`: перемальовка сторінки (перечитування списку, «Перевіряю…» на картці) не
   сміє стирати введене в полях. Поки панель відкрита, значення полів живуть у DOM; `cnDrawer.form` — знімок для
   перемальовки самої панелі (зайнятість, результат, мова). ⛔ Секрет у знімку не тримаємо й у розмітку не пишемо:
   після будь-якої відповіді сервера поля паролів порожні. Стан `cnDrawer` оголошено вгорі файла (Task 6).
   `cnDrawer.busy` — ВИД зайнятості, а не прапорець: `'save'` (запис у `cnSubmit`) чи `'check'` (`cnDrawerCheck`);
   розмітка підписує за ним кнопки («Зберігаю й перевіряю…» лише для `'save'`, «Перевіряю…» лише для `'check'`). */

function cnDrawerNode() {
  let el = document.getElementById('cn-drawer');
  if (el) return el;
  el = document.createElement('aside');
  el.id = 'cn-drawer';
  el.className = 'cn-drawer';
  el.hidden = true;
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-labelledby', 'cn-dr-title');
  document.body.appendChild(el);
  wireCnDrawer(el);
  return el;
}

/** Поточні значення панелі з DOM: `{values, secrets, erase}` (мапи — `Object.fromEntries`: ключ `__proto__` — поле). */
function readCnForm(el) {
  const values = [];
  const secrets = [];
  for (const n of el.querySelectorAll('[data-cn-field]')) {
    const k = n.dataset.cnField;
    if (n.dataset.type === 'secret') secrets.push([k, n.value]);
    else if (n.dataset.type === 'bool') values.push([k, n.checked]);
    else values.push([k, n.value]);
  }
  const erase = [...el.querySelectorAll('[data-cn-dr="erase"][aria-pressed="true"]')].map((b) => b.dataset.key);
  return { values: Object.fromEntries(values), secrets: Object.fromEntries(secrets), erase };
}

/** Селектор контрола панелі, що тримає фокус: поле (`data-cn-field`) чи кнопка (`data-cn-dr`, для «Стерти» ще й ключ
 *  секрету). `null` — фокус поза панеллю чи на чомусь без гачка. */
function cnFocusKey(el, a) {
  if (!a || !el.contains(a)) return null;
  if (a.dataset.cnField != null) return `[data-cn-field="${CSS.escape(a.dataset.cnField)}"]`;
  if (a.dataset.cnDr) {
    return `[data-cn-dr="${a.dataset.cnDr}"]${a.dataset.key != null ? `[data-key="${CSS.escape(a.dataset.key)}"]` : ''}`;
  }
  return null;
}

/**
 * Перемалювати панель. `innerHTML` будує вузли заново — фокус, що стояв на старому контролі, падає на `body`, тож ключ
 * контрола, який його тримав, береться ДО перемальовки і вертається ПІСЛЯ: зайнятість («Зберігаю й перевіряю…»),
 * результат (невдала перевірка, відмова), мова. Контрол вимкнено чи його нема — перший доступний контрол тіла й футера
 * (поля, потім кнопки). Поки запит летить, УСЕ вимкнено, крім хрестика: фокус стає на нього, а бажаний контрол
 * лишається в `cnDrawer.focusWant` — наступна перемальовка (відповідь) вертає фокус туди, де людина була, а не лишає
 * на хрестику. Фокус поза панеллю (палітра мови, діалог питання) не чіпаємо.
 */
function paintCnDrawer() {
  const el = cnDrawerNode();
  if (!cnDrawer) { el.hidden = true; el.innerHTML = ''; return; }
  const sp = currentSpace(spacesResp);
  const live = cnFocusKey(el, document.activeElement);
  const want = cnDrawer.focusWant ?? live;
  el.innerHTML = drawerHTML({ ...cnDrawer, spaceName: sp && sp.id === cnDrawer.spaceId ? sp.name : cnDrawer.spaceId });
  el.hidden = false;
  syncCnDrawer();
  if (!want) return;
  const usable = (n) => n && !n.disabled;
  const back = el.querySelector(want);
  if (usable(back)) { cnDrawer.focusWant = null; back.focus({ preventScroll: true }); return; }
  const first = [...el.querySelectorAll('.cn-dr-body [data-cn-field], .cn-dr-foot button:not([data-cn-dr="untrust"])')].find(usable);
  if (first) { cnDrawer.focusWant = null; first.focus({ preventScroll: true }); return; }
  cnDrawer.focusWant = want;
  el.querySelector('[data-cn-dr="close"]')?.focus({ preventScroll: true });
}

/** Кнопки за станом форми: «Зберегти» вимкнена без змін (у правці), «Перевірити» — зі змінами (перевіряє збережене). */
function syncCnDrawer() {
  if (!cnDrawer) return;
  const el = cnDrawerNode();
  const dirty = isDirty(formPatch(cnDrawer.fields, cnDrawer.init, readCnForm(el)));
  const submit = el.querySelector('[data-cn-dr="submit"]');
  if (submit) submit.disabled = !!cnDrawer.busy || (cnDrawer.mode === 'edit' && !dirty);
  const check = el.querySelector('[data-cn-dr="check"]');
  if (check) { check.disabled = !!cnDrawer.busy || dirty; check.title = dirty ? t('cnCheckSavedFirst') : ''; }
}

function openCnDrawer(e, mode) {
  const fields = formFields(e);
  const init = initialForm(fields);
  cnDrawer = { id: e.id, entry: e, mode, fields, init, form: init, busy: false, result: null, errors: {},
    spaceId: connState.spaceId, opener: { act: mode === 'enable' ? 'enable' : 'configure', id: e.id } };
  paintCnDrawer();
  const el = cnDrawerNode();
  (el.querySelector('[data-cn-field]') ?? el.querySelector('[data-cn-dr="submit"]'))?.focus({ preventScroll: true });
}

/** Закрити без питань. Фокус — на кнопку картки, що відкрила панель (після запису дія могла змінитись: «Підключити» →
 *  «Налаштувати», тому запасний варіант — будь-яка кнопка тієї ж картки). */
function closeCnDrawer({ focus = true } = {}) {
  if (!cnDrawer) return;
  const op = cnDrawer.opener;
  cnDrawer = null;
  paintCnDrawer();
  if (!focus || !op) return;
  const home = homeNode();
  const id = CSS.escape(op.id);
  (home?.querySelector(`[data-cn="${op.act}"][data-id="${id}"]`) ?? home?.querySelector(`[data-cn][data-id="${id}"]`))
    ?.focus({ preventScroll: true });
}

/** Хрестик і Esc: з незбереженими змінами — спершу питання. Під час запиту панель не закривається. */
async function requestCloseCnDrawer() {
  if (!cnDrawer || cnDrawer.busy) return;
  const mine = cnDrawer;
  const dirty = isDirty(formPatch(mine.fields, mine.init, readCnForm(cnDrawerNode())));
  if (dirty && !(await askYesNo(t('cnDiscardAsk'), { yes: t('cnDiscard'), danger: true }))) return;
  if (cnDrawer === mine) closeCnDrawer();
}

/**
 * Панель стоїть на заваді іншій дії (відкрити іншу, вимкнути її модуль, вийти з екрана): закрити її — з питанням
 * «Відкинути зміни?», коли форма брудна. `true` — панелі більше нема, дію можна продовжувати; `false` — людина відмовилась
 * чи панель у запиті (тоді дію ігноруємо: запит не перебивається). Без панелі — `true` СИНХРОННО нічого не чекаючи.
 */
async function dismissCnDrawer() {
  if (!cnDrawer) return true;
  if (cnDrawer.busy) return false;
  await requestCloseCnDrawer();
  return !cnDrawer;
}

/**
 * «Стерти» секрет — без перемальовки (інакше зникли б інші введені секрети). Підпис кнопки СТАЛИЙ: стан — це
 * `aria-pressed` і видима примітка. Примітка читачеві екрана потрібна лише коли секрет позначено, тож її id
 * додається в `aria-describedby` ПОЛЯ рівно тоді (так само, як малює `fieldHTML`: після `-state`), а знімається
 * при поверненні; чужі id атрибута (`-state`, `-err`) лишаються.
 */
function toggleCnErase(btn) {
  const on = btn.getAttribute('aria-pressed') !== 'true';
  btn.setAttribute('aria-pressed', String(on));
  const el = cnDrawerNode();
  const key = btn.dataset.key;
  const note = el.querySelector(`[data-cn-erase-note="${CSS.escape(key)}"]`);
  if (note) note.hidden = !on;
  const field = el.querySelector(`[data-cn-field="${CSS.escape(key)}"]`);
  if (field && note?.id) {
    const ids = (field.getAttribute('aria-describedby') || '').split(/\s+/).filter((x) => x && x !== note.id);
    if (on) ids.splice(ids.findIndex((x) => x.endsWith('-state')) + 1, 0, note.id);
    if (ids.length) field.setAttribute('aria-describedby', ids.join(' '));
    else field.removeAttribute('aria-describedby');
  }
  syncCnDrawer();
}

/** Повернути введені секрети в щойно перемальовані поля паролів: лише властивість `.value` (DOM), без розмітки й стану. */
function restoreCnSecrets(secrets) {
  const el = cnDrawerNode();
  for (const [k, v] of Object.entries(secrets)) {
    const n = el.querySelector(`[data-cn-field="${CSS.escape(k)}"][data-type="secret"]`);
    if (n && v) n.value = v;
  }
  syncCnDrawer();
}

/** Ті самі власники ролі (за id, без порядку)? Для звірки «про кого питали» зі свіжим списком. */
const sameHolders = (a, b) => a.length === b.length && a.every((x) => b.some((y) => y.id === x.id));

/**
 * Показати результат у панелі, НЕ посилаючи нічого на сервер: введене лишається — значення полів у стані, секрети
 * повертаються в поля ВЛАСТИВІСТЮ `.value` (як при порожньому обовʼязковому полі: людина не вводить їх знову).
 */
function cnShowKept(mine, result) {
  const cur = readCnForm(cnDrawerNode());
  mine.form = { values: cur.values, secrets: {}, erase: cur.erase };
  mine.errors = {}; mine.result = result;
  paintCnDrawer();
  restoreCnSecrets(cur.secrets);
}

/**
 * Згода на заміну — СВІЖА. Питання «Замінити?» стоїть, поки людина читає, а агент (API) міг тим часом зайняти роль
 * іншим модулем — тоді її «Замінити» мовчки вимкнуло б і його. Тому після «так» список перечитується (`GET
 * /api/modules` простору панелі), і власники ролі звіряються з тими, про кого питали: ті самі — `replace: true`;
 * змінились — питаємо ще раз з новими назвами; вдруге змінились — відмова «роль уже зайнята», нічого не пишемо.
 * Роль тим часом звільнилась — заміняти нікого, і `replace` НЕ шлемо (власник, що зʼявиться між двома кроками, інакше
 * був би вимкнений мовчки: без `replace` сервер скаже `409 role-taken`).
 *
 * Повертає `true`/`false` (слати `replace` чи ні) або `null` — писати нічого: людина відмовилась, панель змінилась,
 * сервер не віддав список чи власники змінились вдруге (причина вже в панелі).
 */
async function cnConfirmReplace(mine) {
  let holders = roleHolders(mine.entry, connState.list);
  if (!holders.length) return false;
  mine.asking = true;
  try {
    for (let round = 0; ; round += 1) {
      const shared = (mine.entry.roles || []).filter((r) => holders.some((h) => (h.roles || []).includes(r)));
      const q = t('cnReplaceAsk', roleTitle(shared[0]), holders.map(modName).join(', '), modName(mine.entry));
      if (!(await askYesNo(q, { yes: t('cnReplace') }))) return null;
      if (cnDrawer !== mine) return null;
      let list;
      try { list = (await formApi(`/api/modules?space=${encodeURIComponent(mine.spaceId)}`))?.modules; }
      catch (err) {
        if (cnDrawer === mine) cnShowKept(mine, { kind: 'refused', ...refusalView(err) });
        return null;
      }
      if (cnDrawer !== mine) return null;
      if (!Array.isArray(list)) list = [];
      if (connOpen() && connState.spaceId === mine.spaceId) { connState.list = list; paintHome(); }
      const now = roleHolders(mine.entry, list);
      if (sameHolders(now, holders)) return true;
      if (!now.length) return false;
      if (round === 1) { cnShowKept(mine, { kind: 'refused', key: 'cnRefRoleTaken', detail: '' }); return null; }
      holders = now;
    }
  } finally { mine.asking = false; }
}

/** Людські назви модулів, вимкнених заміною (`replaced` відповіді): зі списку сторінки, а нема — сам id. */
function cnReplacedNames(r) {
  const ids = Array.isArray(r?.replaced) ? r.replaced : [];
  return ids.map((id) => {
    const e = (connState.list || []).find((x) => x.id === id);
    return e ? modName(e) : String(id);
  }).join(', ');
}

/** Картка модуля зайнята записом панелі (`'save'`) — лише коли сторінка ще показує той самий простір. Знявши, вертає
 *  фокус на кнопку картки, якщо він пропав: кнопки вимкнені на час зайнятості, і закриття панелі не мало куди його вернути. */
function cnCardBusy(spaceId, id, on) {
  if (!connOpen() || connState.spaceId !== spaceId) return;
  if (on) connState.busy.set(id, 'save'); else connState.busy.delete(id);
  paintHome();
  if (!on) refocusCard(id, 'configure');
}

/** Відмовлений запис (HTTP-відмова, тайм-аут) теж міг щось змінити: сервер пише секрети раніше за решту, а тайм-аут —
 *  це «невідомо». Прапорці `set` на картці й у панелі мусять відповідати диску — перечитуємо, якщо сторінка той самий простір. */
function cnRefreshAfterRefusal(spaceId) {
  if (connOpen() && connState.spaceId === spaceId) loadConn({ spaces: false });
}

/**
 * «Підключити» / «Зберегти». Обовʼязкові — до запиту. Підключення модуля, чиї ролі хтось тримає (зокрема неявний
 * `static-publish`), — спершу питання «Замінити?» зі СВІЖОЮ згодою (`cnConfirmReplace`), далі `replace: true` (сервер
 * міняє постачальника одним записом); тост після заміни називає вимкнені модулі.
 * Запис іде в простір, відкритий у панелі (`spaceId`), а не в активний зараз. Вердикт `ok` — панель закривається,
 * тост; `ok: false` — стан УЖЕ записано (так працює API), панель лишається з причиною й переходить у режим правки;
 * HTTP-відмова — нічого не збережено, причина в панелі.
 */
async function cnSubmit() {
  if (!cnDrawer || cnDrawer.busy || cnDrawer.asking) return;
  const el = cnDrawerNode();
  const cur = readCnForm(el);
  const miss = missingRequired(cnDrawer.fields, cur);
  if (miss.length) {
    cnDrawer.form = { values: cur.values, secrets: {}, erase: cur.erase };
    cnDrawer.errors = Object.fromEntries(miss.map((k) => [k, 'cnFieldRequired']));
    cnDrawer.result = null;
    paintCnDrawer();
    /* Перемальовка спорожнила поля паролів (у розмітку секрет не пишеться ніколи) — людина не мусить вводити їх знову
       через пропущене обовʼязкове поле: повертаємо введене ВЛАСТИВІСТЮ `.value`, а не розміткою чи станом. */
    restoreCnSecrets(cur.secrets);
    cnDrawerNode().querySelector('[aria-invalid="true"]')?.focus({ preventScroll: true });
    return;
  }
  const patch = formPatch(cnDrawer.fields, cnDrawer.init, cur);
  if (cnDrawer.mode === 'edit' && !isDirty(patch)) return;
  const mine = cnDrawer;
  let replace = false;
  if (mine.mode === 'enable') {
    const verdict = await cnConfirmReplace(mine);
    if (verdict === null) return;
    replace = verdict;
  }
  const body = writePayload(mine.spaceId, mine.id, patch, replace);
  mine.form = { values: cur.values, secrets: {}, erase: cur.erase };
  mine.errors = {}; mine.result = null; mine.busy = 'save';
  paintCnDrawer();
  let r;
  try {
    r = await checkPost(mine.mode === 'enable' ? '/api/module-enable' : '/api/module-settings', body, mine.entry);
  } catch (err) {
    cnRefreshAfterRefusal(mine.spaceId);
    if (cnDrawer !== mine) return;
    mine.busy = false; mine.result = { kind: 'refused', ...refusalView(err) };
    paintCnDrawer();
    return;
  }
  const name = modName(mine.entry);
  const off = cnReplacedNames(r);
  /* Картка зайнята від відповіді до кінця перечитування: список під нею ще СТАРИЙ, і «Налаштувати», натиснуте в цей
     проміжок, відкрило б колишній запис (стан секрету, значення). Як `connDisable`: знімаємо ПІСЛЯ перечитування. */
  cnCardBusy(mine.spaceId, mine.id, true);
  try {
    if (r?.check?.ok === true) {
      if (cnDrawer === mine) closeCnDrawer();
      toast(off ? t('cnToastReplaced', name, off) : t(mine.mode === 'enable' ? 'cnToastEnabled' : 'cnToastSaved', name));
    } else if (cnDrawer === mine) {
      const entry = r?.module ?? mine.entry;
      const fields = formFields(entry);
      const init = initialForm(fields);
      cnDrawer = { ...mine, entry, mode: 'edit', fields, init, form: init, busy: false,
        result: { kind: 'failed', ...verdictText(r?.check, entry) }, opener: { act: 'configure', id: mine.id } };
      paintCnDrawer();
    }
    await afterModulesChange();
  } finally {
    cnCardBusy(mine.spaceId, mine.id, false);
  }
}

/** «Перевірити» в панелі — по збереженому (зі змінами кнопка вимкнена): вердикт у панелі, сторінка перечитується. */
async function cnDrawerCheck() {
  if (!cnDrawer || cnDrawer.busy) return;
  const mine = cnDrawer;
  mine.form = { ...readCnForm(cnDrawerNode()), secrets: {} };
  mine.busy = 'check'; mine.result = null;
  paintCnDrawer();
  try {
    const r = await checkPost('/api/module-check', { space: mine.spaceId, id: mine.id }, mine.entry);
    if (cnDrawer !== mine) return;
    mine.result = { kind: r?.check?.ok === true ? 'ok' : 'check-failed', ...verdictText(r?.check, mine.entry) };
  } catch (err) {
    if (cnDrawer !== mine) return;
    mine.result = { kind: 'refused', ...refusalView(err) };
  } finally {
    mine.busy = false;
  }
  if (cnDrawer === mine) paintCnDrawer();
  loadConn();
}

/** «Забрати довіру» в панелі свого модуля: модуль і простір — з панелі ДО її закриття (питання «Відкинути?» могло
 *  висіти, а сторінка — перейти в інший простір), далі — те саме питання й запит, що з діалогу довіри. */
async function cnDrawerUntrust() {
  if (!cnDrawer || cnDrawer.busy) return;
  const { entry, spaceId } = cnDrawer;
  if (!(await dismissCnDrawer())) return;
  await untrustFlow(entry, spaceId);
}

function wireCnDrawer(el) {
  el.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-cn-dr]');
    if (!b || b.disabled) return;
    const a = b.dataset.cnDr;
    if (a === 'close') requestCloseCnDrawer();
    else if (a === 'check') cnDrawerCheck();
    else if (a === 'erase') toggleCnErase(b);
    else if (a === 'untrust') cnDrawerUntrust();
  });
  el.addEventListener('submit', (ev) => { ev.preventDefault(); cnSubmit(); });
  el.addEventListener('input', () => syncCnDrawer());
  el.addEventListener('change', () => syncCnDrawer());
}

/* Esc панелі: лише коли над нею нема діалогу питання й палітри (Esc тих — їхній) і коли цей Esc уже не закрив щось
   інше (відкритий дропдаун смуги: його слухач стоїть раніше й гасить подію через `preventDefault`). Не під час
   IME-композиції (`isComposing`): там Esc скасовує набране, а не закриває панель чи питає «Відкинути?». */
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !ev.isComposing && !ev.defaultPrevented && cnDrawer && !paletteOverlay && !askUp()) {
    ev.preventDefault();
    requestCloseCnDrawer();
  }
});

/** Клавіатура екрана. `/` — у пошук; в пошуку: Esc чистить, потім знімає фокус,
 *  ↓ — до першої картки, Enter — відкрити першу; на картці: стрілки ходять по
 *  сітці (стовпців стільки, скільки дає розкладка зараз), Enter/Пробіл
 *  відкривають, ↑ з першого ряду — назад у пошук. Палітра, діалог питання й
 *  IME-композиція клавіш екрана не віддають. */
document.addEventListener('keydown', (ev) => {
  if (!homeOpen || ev.isComposing || paletteOverlay || askUp()) return;
  if (homePage !== 'tasks') return;   // «Підключення» й майстер: клавіші списку задач не діють; Esc панелі — свій обробник
  const el = homeNode();
  if (!el) return;
  const a = document.activeElement;
  const q = el.querySelector('#th-q');
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  /* Esc у формі «Нова задача» вертає картку «+»; під час клону (`aria-busy`) не діє — запит однаково долетить. До гілки `typing`. */
  if (ev.key === 'Escape' && homeEdit.newForm && newFormEl && a && newFormEl.contains(a)) {
    ev.preventDefault();
    if (!newFormEl.hasAttribute('aria-busy')) closeNewTaskCard();
    return;
  }
  const typing = !!a && (['INPUT', 'TEXTAREA', 'SELECT'].includes(a.tagName) || a.isContentEditable);
  if (ev.key === '/' && !typing) { q?.focus(); ev.preventDefault(); return; }
  if (a && a === q) {
    if (ev.key === 'Escape') {
      if (homeUi.q) { homeUi.q = ''; q.value = ''; paintHomeLower(); } else q.blur();
      ev.preventDefault();
    } else if (ev.key === 'ArrowDown') {
      homeCards()[0]?.focus();
      ev.preventDefault();
    } else if (ev.key === 'Enter') {
      /* Перша ЗАДАЧА, а не перша картка: першою в сітці стоїть «+». */
      const first = homeCards().find((c) => c.dataset.th === 'open');
      if (first) homeOpenTask(first.dataset.id);
      ev.preventDefault();
    }
    return;
  }
  if (!a || !a.classList || !a.classList.contains('th-card')) return;
  const cards = homeCards();
  const i = cards.indexOf(a);
  if (ev.key === 'Enter' || ev.key === ' ') {
    ev.preventDefault();
    if (a.dataset.th === 'open') homeOpenTask(a.dataset.id);
    else if (a.dataset.th === 'newtask') openNewTaskCard();
    return;
  }
  const grid = el.querySelector('#th-grid');
  const cols = Math.max(1, grid ? getComputedStyle(grid).gridTemplateColumns.split(' ').length : 1);
  const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols }[ev.key];
  if (!step) return;
  ev.preventDefault();
  const next = cards[i + step];
  if (next) next.focus();
  else if (ev.key === 'ArrowUp') q?.focus();
}, false);

/* ── смуга: своя ширина макета (поле лишається, доки в ньому набирають) ── */
bar.addEventListener('input', (ev) => {
  const inp = ev.target.closest('[data-act="vpw"]');
  if (!inp) return;
  /* Живий перегляд, поки набирають: ширину міряють оком, а не арифметикою.
     Саме поле при цьому НЕ переписуємо (це стереже `syncViewportBar`) — інакше
     затиск на першій же цифрі не дав би набрати трицифрове число. */
  const r = parseWidth(inp.value);
  if (r.ok) setViewport(r.w);
});
function settleViewportInput(inp) {
  const r = parseWidth(inp.value);
  /* Порожнє поле НА КІНЕЦЬ вводу — це «авто» (так і підписано в плейсхолдері),
     тобто десктоп. Порожнє поле ПОСЕРЕД набору (обробник `input` вище) — ще не
     значення, там воно ігнорується, інакше рамка стрибала б на повну ширину на
     кожному стертому символі. Одна й та сама відмова модуля, два різні читання —
     рівно тому `parseWidth` і не вирішує це за викликача. */
  if (!r.ok) {
    if (r.reason === 'empty') { setViewport(null); return; }
    inp.value = vpWidth === null ? '' : String(vpWidth);
    toast(t('toastWidthNotNumber'));
    return;
  }
  setViewport(r.w);
  // поле мусить показувати те, що НА ЕКРАНІ: «20» при рамці 240 — це брехня поля
  inp.value = String(r.w);
  if (r.clamped) toast(t('toastWidthClamped', r.w, MIN_W, MAX_W));
}
/* `focusout`, а не `blur`: `blur` не спливає, а делегація на `bar` потребує
   бульбашки, щоб не вішати окремий слухач на поле, яке перемальовка
   пересотворює на кожному повному `render()`. */
bar.addEventListener('focusout', (ev) => {
  const inp = ev.target.closest('[data-act="vpw"]');
  if (inp) settleViewportInput(inp);
});
bar.addEventListener('keydown', (ev) => {
  const inp = ev.target.closest('[data-act="vpw"]');
  /* Enter окремо: у `type=number` `change`/`focusout` не завжди зручно чекати
     клавіатурою, а натиснути Enter і не побачити нормалізації дивно. */
  if (inp && ev.key === 'Enter') settleViewportInput(inp);
});

// --- GitLab-синхронизация (T-18) ---
// Статус кэшируем: смуга (Task 3) малює з кешу через `barState()`, мережу
// дьоргаємо лише на старті й після дій.
let glCache = null;
/* Ключ («простір|задача|ітерація»), для якого зібрано `glCache`. `resetPerTaskState` кеш навмисно не обнуляє (перемикання
   в межах простору не мигає смугою), тож без ключа чужий стан міг би пережити перемикання задачі. */
let glKey = null;
/* Номер останнього запиту статусу: відповідь старішого (повільний VPN, перемкнули задачу, вийшли з простору) відкидається. */
let glSeq = 0;
/* Відкладений повтор опиту після `vcs-busy`; ключ і лічильник спроб, до яких він прив'язаний. */
let glBusyTimer = null;
let glBusyFor = null;
let glBusyTries = 0;

/** Підпис репозиторію для текстів дій: той самий нормалізатор, що в смузі й палітрі (`vcsLabel`). */
function glLabelNow() { return vcsLabel(glCache?.label, spaceNow()); }

/** Текст відмови синку: код із власним текстом (`vcsFailKey`: у ЛІГІ `vcs-bad-target` його не має) — ним, інакше `plain`. */
function glFailText(r, lbl, plain) {
  const k = vcsFailKey(r.code, spaceNow());
  return k ? t(k, lbl) : plain;
}

/**
 * Ключ стану синку: простір, задача й ітерація, про які питає сервер. `task` — задача, до якої сервер ВЖЕ перемкнено, коли
 * `curTask` ще старий (`switchTask`, `wizOpenTask`, створення задачі питають статус ДО `render()`, `picked` тоді `null`);
 * без неї — відкрита зараз.
 */
function glKeyNow(task) { return `${spaceNow()?.id ?? ''}|${task ?? curTask?.id ?? ''}|${picked || ''}`; }

/** Скасувати відкладений повтор опиту (вийшли на екран «Задачі», простір змінився, відповідь прийшла). */
function cancelGlRetry() { clearTimeout(glBusyTimer); glBusyTimer = null; }

/** Забути стан синку без кешу: ключ, повтор, і запізнілі відповіді (`glSeq`) — вони були про простір, якого більше нема. */
function dropGlState() { glKey = null; glSeq += 1; cancelGlRetry(); }

/**
 * Відкладений повтор опиту після `vcs-busy`, не більше `VCS_BUSY_MAX_TRIES` разів на ключ. Повтор питає про те, що відкрито
 * ЗАРАЗ (`refreshGitlab` сам бере поточну задачу): у реальному потоці ключ запиту (`switchTask` питає ДО `render()`) інший, ніж
 * після нього, і звіряти ключі в таймері значило б, що повтор не спрацює ніколи. Не стріляє без ролі `vcs` і під екраном
 * «Задачі» (`leaveHome` поверне його, якщо стан лишився «зайнято»).
 */
function scheduleGlRetry(key) {
  cancelGlRetry();
  if (glBusyFor !== key) { glBusyFor = key; glBusyTries = 0; }
  if (glBusyTries >= VCS_BUSY_MAX_TRIES) return;
  glBusyTries += 1;
  glBusyTimer = setTimeout(async () => {
    glBusyTimer = null;
    if (noVcs() || homeOpen) return;
    await refreshGitlab();
    paintBar();
  }, VCS_BUSY_RETRY_MS);
}

/* `paintGitlab()` більше не існує: старий бар мав ПОРОЖНІЙ `<span id="gl-slot">`
   і патчив його руками (DOM без даних — без чого не показати статус). Нова
   смуга малює GitLab-дропдаун ЦІЛКОМ із `barState()`/`barModel()` при кожному
   `render()`/`paintBar()`, тобто фарбувати його ОКРЕМО — дублювати роботу, яку
   й так робить перемальовка. Дії (`glpush`/`glpull`/`glsetup`/`glhistory`)
   тепер у `BAR_ACTIONS`. */
async function refreshGitlab(task) {
  /* Простір без ролі `vcs` синку не має: статус там — «нема», а не запит, що
     повертає `configured:false` (і не мережа, і не рядок у журналі сервера). */
  if (noVcs()) { glCache = null; dropGlState(); return; }
  const seq = ++glSeq;
  const key = glKeyNow(task);
  try {
    const r = await api(`/api/vcs-status?it=${encodeURIComponent(picked || '')}`);
    /* Запізніла відповідь: за час запиту (`git fetch` через VPN — секунди) питали вдруге, перемкнули задачу чи вийшли з
       простору. Застосовується лише найновіший запит — інакше стан A малювався б для B, а «зайнято» старого ключа затирало б добрий стан. */
    if (seq !== glSeq) return;
    if (r.code === 'vcs-busy') {
      /* `vcs-busy` — не помилка, а «лок дзеркала тримає інша синхронізація (клон, відправка, отримання)». Власний стан
         ТОГО САМОГО ключа лишається (крапка не фарбується в помилку на кожен збіг у часі). Чужого стану — іншої задачі, ітерації
         чи простору — не лишаємо: він брехав би («збігається» там, де є незапушена робота). Тоді стан «зайнято»: ні
         помилка, ні «збігається», а дія в ньому каже `vcsErrBusy`. І один відкладений повтор, щоб стан не завис. */
      if (!(glCache && !glCache.busy && glKey === key)) glCache = { configured: true, busy: true };
      glKey = key;
      scheduleGlRetry(key);
    } else {
      glCache = r; glKey = key;
      cancelGlRetry(); glBusyFor = null; glBusyTries = 0;
    }
  } catch { if (seq === glSeq) { glCache = null; glKey = null; } }
}

// --- контекст-меню итерации: дублювати / видалити ---
// ⛔ БЕЗ ВИКЛИКІВ від Task 4 Плану B: єдиний виклик жив у старій панелі
// (`#pp-itmenu`), яку `renderPanel()` замінив цілком — ті самі дії
// (перейменувати/дублювати/видалити ітерацію) уже живуть у дропдауні крошки
// ітерації (`BAR_ACTIONS.renit`/`dupit`/`delit`, Task 3). Лишена НЕ вживаною
// свідомо, тим самим рядком думки, що й стара розмітка панелі (`.pp-*`,
// `app/styles.css`) — «мертвий код» прибирає Task 8, а не побічний ефект
// цього перенесення.
function pillMenu(ev, it, label) {
  document.getElementById('cv-ctx')?.remove();
  const m = document.createElement('div');
  m.id = 'cv-ctx';
  m.className = 'cv-ctx';
  m.style.left = `${ev.clientX}px`;
  m.style.top = `${ev.clientY}px`;
  m.innerHTML = `<button data-a="rename">${t('menuRename')}</button>
    <button data-a="dup">${t('menuDuplicateIteration')}</button>
    <button data-a="delete">${t('menuDeleteIteration')}</button>`;
  document.body.appendChild(m);
  const close = () => { m.remove(); document.removeEventListener('click', close); };
  setTimeout(() => document.addEventListener('click', close), 0);
  // Перейменування: коли ітерації — це різні СТОРІНКИ одного макета, «Іт.3» ні про що
  // не говорить. Порожній ввід прибирає підпис і вертає «Іт.N».
  m.querySelector('[data-a="rename"]').onclick = async () => {
    close();
    const cur = it.label || (it.note || '').replace(/^\s*[A-Z]+-\d+\s*[·:-]\s*/, '');
    const next = await ask(t('menuRenameIterationPrompt', String(it.id).replace(/^it/, '')), cur);
    if (next === null) return;                       // Esc — нічого не міняємо
    try { await post('/api/iteration-rename', { id: it.id, label: next }); render(); }
    catch (e) { tell(t('errFailed', e.message)); }
  };
  m.querySelector('[data-a="dup"]').onclick = async () => {
    close();
    const note = await ask(t('menuDuplicateIterationPrompt', label));
    if (note === null) return;        // скасування скасовує — див. «＋ ітерація» в renderPanel()
    try { const r = await post('/api/iteration', { from: it.id, note }); picked = r.iteration.id; await refreshGitlab(); render(); }
    catch (e) { tell(t('errFailed', e.message)); }
  };
  m.querySelector('[data-a="delete"]').onclick = async () => {
    close();
    const go = await askYesNo(t('menuDeleteIterationConfirm', label), { yes: t('menuDeleteYes'), danger: true });
    if (!go) return;
    try { await post('/api/iteration-delete', { id: it.id }); if (picked === it.id) picked = null; render(); }
    catch (e) { tell(t('errFailed', e.message)); }
  };
}

// ===== Панель шарів (Task 4 Плану B) =====
// Розмітка — чиста `panelHTML()` (`shell-panel.js`), проводка — ТА САМА
// ідіома, що в смузі (Task 3): один делегований `click` на контейнер,
// `data-act`/`data-val` — контракт між модулем розмітки й тілами дій тут.
// Дерево (`flattenPages`, фільтр за `expandedPages`) лишається тут, а не в
// `shell-panel.js` — модуль розмітки отримує вже ГОТОВИЙ плаский список.

/** Скільки записів манифеста належать ширині `w` — кадр стану теж кадр,
 *  тому рахуємо за записами, не за сторінками (та сама пастка, що вже
 *  ловив колишній `noShotsHere`: без фільтра по ширині перемикання на
 *  мобайл, де кадрів іще нема, показало б число застарілих кадрів десктопу). */
function shotsCountForWidth(shots, w) {
  return Object.keys(shots).filter((id) => splitFrameKey(id).w === w).length;
}

/**
 * Стан секції «Кадри» для `panelHTML()`. `null` лише коли ітерації нема —
 * рахувати кадри нема для чого (`panelState()` не кличе цю функцію тоді).
 *
 * `stale: null` — свіжість НЕВІДОМА: `checkOf()` порожній, поки `freshen()`
 * жодного разу не бігав для ЦІЄЇ ітерації (типовий стан у «Макеті» до
 * першого входу в «Огляд», не рідкісний кут). `shell-panel.js` показує це
 * окремим текстом, а не «усе свіже» чи «0 застаріло» — обидва були б
 * брехнею, від якої вже рятує кнопку «Перезняти» коментар над `freshen()`. */
function shotsState() {
  const have = shotsCountForWidth(shotManifest.shots || {}, canvasW);
  if (shootingHere()) {
    return { bad: false, running: true, have,
             done: shootProgress?.done ?? 0, total: shootProgress?.total ?? null,
             stale: null };
  }
  if (shotManifest.error) {
    return { bad: true, running: false, have, done: 0, total: null, stale: null };
  }
  const check = checkOf();
  return {
    bad: false, running: false, have, done: 0,
    stale: check ? check.stale.length : null,
    total: check ? check.total : null,
  };
}

/** Видимі рядки панелі за поточним станом модуля — одне місце для рендера й клавіатури. */
function panelRows() {
  return visibleRows(panelPages, { expanded: expandedPages, focus: panelFocus, filter: panelFilter });
}

/**
 * Адаптер стану модуля в те, що чекає `panelHTML()` — той самий рядок думки,
 * що `barState()` для смуги: чиста функція, жодного DOM, жодного fetch.
 */
function panelState() {
  const vis = panelRows();
  const flatAll = flattenPages(panelPages);
  const byId = new Map(flatAll.map((f) => [f.page.id, f]));
  const parentIds = new Set(flatAll.map((f) => f.parent).filter(Boolean));
  // «у превʼю» — та сама видимість ланцюжком, що на сервері й у сітці
  const visible = visibleIds(panelPages);
  /* Лічильник лише на ЗГОРНУТОМУ вузлі й не під фільтром (там гілки розкриті
     примусово). Теки з одними теками рахуємо теками, інакше рядок мовчав би. */
  const counted = (f) => {
    if (!parentIds.has(f.page.id) || expandedPages.has(f.page.id) || panelFilter) return null;
    return statsOf(f.page, byId.get(f.parent)?.kind ?? null);
  };
  /* Roving tabindex: опора вибору, якщо вона видима, інакше відкрита сторінка,
     інакше перший рядок (`shell-panel.js` сам підстрахує, коли жодного нема). */
  const ids = vis.map((f) => f.page.id);
  const tabId = ids.includes(panelKbFocus) ? panelKbFocus : ids.includes(panelAnchor) ? panelAnchor : ids.includes(pickedPage) ? pickedPage : ids[0];
  const rows = vis.map((f) => {
    const p = f.page;
    const s = counted(f);
    return {
      id: p.id,
      depth: f.depth,
      kind: f.kind,
      isGroup: f.kind === 'folder',
      isState: f.kind === 'state',
      hasKids: parentIds.has(p.id),
      expanded: !!panelFilter || expandedPages.has(p.id),
      selected: p.id === pickedPage,
      recent: recentPages.has(p.id),
      multi: panelSel.has(p.id) && p.id !== pickedPage,
      // для читача екрана: вибір — це рядки panelSel; коли його нема, — відкрита сторінка
      ariaSelected: panelSel.size ? panelSel.has(p.id) : p.id === pickedPage,
      focus: p.id === tabId,
      name: p.name,
      // Мітка «у превью» — лише для СПРАВЖНІХ сторінок: організатор сам по
      // собі не публікується (serve.py, `_page_publish_toggle`); приховування
      // діє на все піддерево (`visibleIds`).
      mark: f.kind !== 'folder' && visible.has(p.id),
      count: s ? [s.pages && t('countPages', s.pages), s.states && t('countStates', s.states),
        !s.pages && !s.states && s.folders && t('countFolders', s.folders)].filter(Boolean).join(' · ') : '',
      countTitle: s ? t('countTitle', s.pages, s.states, s.folders) : '',
      news: cmtNewsPages[p.id] || 0,
    };
  });
  const focusNode = panelFocus ? byId.get(panelFocus)?.page : null;
  const crumbOf = (id) => pathOf(panelPages, id).map((n) => ({ id: n.id, name: n.name }));
  return {
    panel: panelCollapsed ? 'rail' : 'open',
    hasIteration: !!curIter(),
    /* Переклад — ТУТ, а не в `shell-panel.js`: той модуль лише малює готовий
       рядок (див. його шапку), а `pagesError` — це голе `e.message` з
       `loadPages()` (може бути «Failed to fetch», може — текст відповіді
       сервера). Без префікса дизайнер читає мережеву помилку як щось
       незрозуміле; префікс ніс іще старий `.pp-err` до переписування панелі
       (Task 4 Плану B) — переписування його загубило, повернуто ревʼю (живий
       тест K4: панель мусить сказати «не завантажились», а не показати сирий
       текст фетча). */
    pagesError: pagesError ? t('errPagesLoadFailed', pagesError) : '',
    rows,
    filter: panelFilter,
    focus: focusNode ? { id: focusNode.id, name: focusNode.name } : null,
    crumbs: focusNode ? crumbOf(focusNode.id) : (pickedPage ? crumbOf(pickedPage) : []),
    /* `overview` — чи ми в «Огляді»: тривогу кадрів панель піднімає лише там, де
       свіжість справді міряють (`shotsView`, fb-22092026-c74093). */
    shots: curIter() ? { ...shotsState(), overview: mode === 'canvas' } : null,
    shotsOpen,
  };
}

/**
 * Панель шарів. Без параметра, як `paintBar()`: усе потрібне лежить у
 * змінних модуля, а `panelState()` їх читає. Ім'я й нуль аргументів лишаються
 * стабільними свідомо: `tests/i18n-literals.test.mjs` шукає РІВНО
 * `function renderPanel(` — виняток для кирилиці всередині її тіла (порожнього
 * тепер) знімає лише Task 8 Плану B, коли й смуга, і панель більше нізвідки
 * не звуться `render*`.
 *
 * `curTask` тут гарантовано не `null`: єдиний виклик з мережею (`render()`)
 * повертається раніше, ще до `applyMode`/`renderPanel`, якщо перше
 * завантаження впало цілком (див. коментар у `render()`); решта викликів
 * нижче — легкі перемальовки після ЛОКАЛЬНОЇ зміни (рейка, каретка, вибір
 * сторінки, такт прогресу зʼємки), а до першого рендера панелі їм узятись
 * нізвідки.
 *
 * Скрол `.panel-body` зберігаємо через перемальовку: секція «Кадри»
 * перемальовується щотакту зʼємки (`pollProgress`, 700ms), і без цього довге
 * дерево сторінок стрибало б нагору на кожному такті — той самий клас бага,
 * від якого раніше рятував куций `syncShootBtn`, патчаючи текст кнопки
 * нарізно від решти панелі. Тепер перемальовка одна на все, і саме тому їй
 * потрібне це збереження, якого точковий патч не потребував узагалі. */
function renderPanel() {
  let el = document.getElementById('pages-panel');
  if (!el) {
    el = document.createElement('div');
    el.id = 'pages-panel';
    wirePanelEvents(el);
    document.body.appendChild(el);
  }
  document.body.classList.add('with-panel');
  const st = panelState();
  document.body.classList.toggle('panel-collapsed', st.panel === 'rail');
  const body = el.querySelector('.panel-body');
  const scrollTop = body ? body.scrollTop : 0;
  el.className = `panel${st.panel === 'rail' ? ' panel--rail' : ''}${treeGate.busy ? ' panel--busy' : ''}`;
  const html = panelHTML(st);
  if (!patchAroundFilter(el, html, st.filter)) el.innerHTML = html;
  const newBody = el.querySelector('.panel-body');
  if (newBody) newBody.scrollTop = scrollTop;
  restoreRowFocus(el);
  dragRepaint?.();   // жест триває: нові вузли DOM — повернути підсвітку з пам'ятаних координат
}

/**
 * Перемалювати панель, НЕ чіпаючи `<input id="pp-filter">`. `innerHTML` на кожне
 * натискання знищив би поле разом із фокусом, кареткою й IME-композицією —
 * кирилиця з діакритикою не набиралась би. Тому живий вузол поля (а з ним його
 * батьків `.panel-body`) лишається, а підміняються лише сусіди: шапка, крихти з
 * деревом, заповнювач і секція кадрів. Переміщення самого `.panel-body` теж
 * зняло б фокус, тож сусідів вставляємо навколо нього, а не збираємо наново.
 * false — поля нема (рейка, помилка, перший рендер): тоді повний `innerHTML`.
 */
function patchAroundFilter(el, html, filterValue) {
  const oldBody = el.querySelector(':scope > .panel-body');
  const oldInput = oldBody?.querySelector('#pp-filter');
  if (!oldInput) return false;
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  const newBody = tmp.querySelector(':scope > .panel-body');
  if (!newBody?.querySelector('#pp-filter')) return false;
  const parts = ['.tree-head', '.tree-body', '.panel-fill'];
  if (parts.some((sel) => !oldBody.querySelector(`:scope > ${sel}`) || !newBody.querySelector(`:scope > ${sel}`))) return false;
  for (const sel of parts) oldBody.querySelector(`:scope > ${sel}`).replaceWith(newBody.querySelector(`:scope > ${sel}`));
  for (const c of [...el.children]) if (c !== oldBody) c.remove();
  let before = true;
  for (const c of [...tmp.children]) {
    if (c === newBody) { before = false; continue; }
    if (before) el.insertBefore(c, oldBody); else el.appendChild(c);
  }
  // значення міняємо лише коли воно розійшлось зі станом (скидання ззовні) і не посеред композиції
  if (!panelComposing && oldInput.value !== filterValue) oldInput.value = filterValue;
  return true;
}

/**
 * Повернути клавіатурний фокус на рядок після перемальовки — але лише коли
 * його знищила САМА перемальовка (фокус на `body` або в панелі). Якщо фокус
 * тим часом пішов деінде (рамка, поле), красти його назад не можна.
 */
function restoreRowFocus(el) {
  if (!panelKbFocus) return;
  const a = document.activeElement;
  if (a && a !== document.body && !el.contains(a)) return;
  [...el.querySelectorAll('[data-page]')].find((n) => n.dataset.page === panelKbFocus)?.focus();
}

/**
 * Ім'я дії → функція, той самий патерн, що `BAR_ACTIONS`. Делегація
 * (`wirePanelEvents`) кличе `PANEL_ACTIONS[act](val, el, ev)`.
 */
/**
 * Записати стан рейки й перемалювати панель — тіло, яке раніше жило лише
 * всередині `PANEL_ACTIONS.panel` (клік по стрілці). Винесено сюди Task 6
 * Плану B: пункт палітри «Сторінки» (`go-pages`) мусить РОЗГОРНУТИ панель,
 * а не ПЕРЕМКНУТИ її (`!panelCollapsed` затулила б панель, якби той якраз
 * був відкритий) — те саме тіло запису й перемальовки, інший виклик.
 */
function setPanelCollapsed(v) {
  panelCollapsed = v;
  try { localStorage.setItem('dc-panel-collapsed', panelCollapsed ? '1' : '0'); } catch (e) {}
  renderPanel();
}

const PANEL_ACTIONS = {
  panel: () => setPanelCollapsed(!panelCollapsed),

  /* Одна дія на ДВА контроли секції кадрів — тихий рядок (розгорнути) і
     заголовок розгорнутого блоку (згорнути назад). Саме перемикач, а не
     одностороннє відкриття: без дороги назад вибір «розгорнуто» неможливо
     було б скасувати нічим, крім сховища браузера. Який із двох контролів
     видно — вирішує `shotsHTML` (`shell-panel.js`), і він же не дає
     згорнути блок, у якому є про що кричати. */
  shotsopen: () => {
    shotsOpen = !shotsOpen;
    try { localStorage.setItem('dc-shots-open', shotsOpen ? '1' : '0'); } catch (e) {}
    renderPanel();
  },

  toggle: (val) => {
    if (expandedPages.has(val)) expandedPages.delete(val); else expandedPages.add(val);
    saveExpanded();
    renderPanel();
  },

  page: (val, el, ev) => {
    const f = flattenPages(panelPages).find((x) => x.page.id === val);
    if (!f) return;
    // ⌘/Ctrl — додати/зняти з вибору, нічого не відкриваючи
    if (ev && (ev.metaKey || ev.ctrlKey)) {
      if (panelSel.has(val)) panelSel.delete(val); else panelSel.add(val);
      panelAnchor = val;
      renderPanel();
      return;
    }
    // Shift — діапазон від опори по ВИДИМИХ рядках (згорнуте в діапазон не потрапляє)
    if (ev && ev.shiftKey && panelAnchor) {
      const ids = panelRows().map((r) => r.page.id);
      const [a, b] = [ids.indexOf(panelAnchor), ids.indexOf(val)].sort((x, y) => x - y);
      if (a >= 0) { panelSel = new Set(ids.slice(a, b + 1)); renderPanel(); return; }
    }
    // вибір поза гілкою фокуса виводить із фокуса — інакше обране зникло б з очей
    if (panelFocus && !pathOf(panelPages, val).some((n) => n.id === panelFocus)) panelFocus = null;
    panelSel = new Set([val]);
    panelAnchor = val;
    /* Тека не відкривається (кадру на полотні в неї нема) — її вибирають для дій
       над нею: меню, «у теку», перетягування. `pickedPage` НЕ міняємо: він мусить
       лишатись сторінкою, яку можна відкрити. */
    if (f.kind === 'folder') {
      /* У «Огляді» рядок, що не веде камеру, мусить сказати чому: інакше він виглядає
         зламаним (сусіди підлітають до кадру, цей мовчить). Вибір теки його дію не
         замінює — він лише відкриває меню/перетягування. */
      if (mode === 'canvas') toast(t('toastGroupNoFrame', f.page.name));
      renderPanel();
      return;
    }
    /* Стан скидаємо навіть коли рядок ТОЙ САМИЙ: сторінка не змінилась, тож
       охорона в `loadPages` тут не спрацює, а той, хто клікнув «Пошук», чекає
       звичайний пошук, а не «нічого не знайдено» з кадру флоу. */
    pickedPage = val; pickedState = null;
    /* У «Огляді» клік по рядку ВЕДЕ КАМЕРУ до кадру цієї сторінки й підсвічує
       його. Повного `render()` при цьому НЕ робимо: він перебудував би
       канвас і сів у `fitAll()`, тобто затер би щойно порахований переліт
       «вписати все». Перемальовуємо ЛИШЕ панель — вихід із «Огляду» відкриє
       саме цю сторінку, бо `applyMode` читає `pickedPage`. */
    if (mode === 'canvas') { focusPage(pickedPage); renderPanel(); return; }
    render();
  },

  // «⋯» рядка — той самий шар, що правий клік (нижче, `wirePanelEvents`), і
  // те саме меню (`pageMenu`): спека Task 4, п.1 вимагає ОБИДВА шляхи, не
  // лише правий клік. `el` тут — сама кнопка «⋯» (делегація передає елемент,
  // на якому знайшовся `data-act`), її `getBoundingClientRect()` і дає
  // якір — координати вікна, як уже працює в `pillMenu`.
  pagemenu: (val, el) => {
    const b = el.getBoundingClientRect();
    pageMenu({ x: b.left, y: b.bottom + 4 }, val);
  },

  /* Лише ТЕКА: сторінки створює Claude, панель організовує (рішення власника
     30.09.2026; `/api/page-new` лишається лише для сумісності — клієнта в нього
     нема, а CLI `bin/pages.py` пише файл сам, повз сервер). Куди: у вибраний контейнер,
     якщо він може вмістити теку (тобто не стан), інакше — у корінь. */
  newfolder: async () => {
    const it = picked;                // фіксуємо ДО await: дизайнер може перемкнути ітерацію
    /* Куди: єдиний вибраний вузол, що може вмістити теку (не стан) → всередину;
       інакше, у фокусі гілки, → у фокус; інакше корінь. До `pickedPage` НЕ
       відкочуємось: порожній чи множинний вибір не означає «у відкриту сторінку». */
    const one = panelSel.size === 1 ? flattenPages(panelPages).find((x) => x.page.id === [...panelSel][0]) : null;
    const parent = one && one.kind !== 'state' ? one.page.id : (panelFocus || null);
    const r = await treePost('/api/folder-add', { parent, name: t('newFolder') }, { it });
    if (!r) return;
    /* Ітерацію перемкнули, поки запит летів: вузол створено в ІНШІЙ ітерації, і
       чіпати вибір, фільтр чи розкриті гілки поточної було б брехнею. */
    if (picked !== it) return;
    // нова тека під діючим фільтром лишилась би невидимою — а поле назви вже просить її ім'я
    panelFilter = '';
    if (parent) { expandedPages.add(parent); saveExpanded(); }
    panelSel = new Set([r.node.id]);
    panelAnchor = r.node.id;
    await loadPages(); render();
    /* Поле назви лише коли ми ще в тій самій ітерації й теку справді видно в
       дереві: інакше `ask` питав би ім'я для вузла, якого людина вже не бачить. */
    if (picked !== it || !flattenPages(panelPages).some((f) => f.page.id === r.node.id)) return;
    renamePage(r.node.id);            // той самий `ask`, що й для сторінок
  },
  groupsel: () => groupSelection(),
  ungroup: () => { const id = treeTarget(); if (id) ungroupNode(id); },
  outdent: () => { const id = treeTarget(); if (id) outdentNode(id); },
  focusbranch: () => { const id = treeTarget(); if (id) PANEL_ACTIONS.focus(id); },
  togglekind: () => { const id = treeTarget(); if (id) toggleKind(id); },
  focus: (val) => { panelFocus = val; renderPanel(); },
  unfocus: () => { panelFocus = null; renderPanel(); },

  shoot: async () => {
    const it = picked;                   // фіксуємо ДО await — ідіома `freshen()`
    /* Зупиняємо, лише поки знімають САМЕ ЦЮ ітерацію — ту саму умову, за якою
       рахує стан кнопки `shotsState()`. Без звірки з `shootingIt` (стояло
       голе `shootProgress?.running`) кнопка сусідньої ітерації теж зупиняла:
       у `autoShootStopped` лягала ітерація, якої ніхто не знімав, а сервер на
       `shoot-stop` не знаходив нічого — прогін тривав, і спинити його з
       інтерфейсу вже не було чим. */
    if (shootingHere()) {
      /* Зупинка ВРУЧНУ вимикає автостарт для цієї ітерації — в ОКРЕМИЙ набір,
         а не в `autoShootOff`.
         ⛔ Різниця несуча, і вона куплена живим виміром. `autoShootOff` знімає
         `freshen()`, щойно перелік застарілого став іншим, — а часткова зʼємка
         міняє його ЗАВЖДИ: будь-який кадр, знятий до зупинки, зникає з переліку.
         Тому позначка в `autoShootOff` стиралась тим самим `freshen()`, який
         біжить одразу після зупинки, і повернення в «Огляд» починало все
         спочатку: виміряно на 4 сторінках — зупинка на першому кадрі, вихід,
         повернення → «Стоп 2/3». Тобто кнопку «Стоп» не можна було перемогти,
         хоч спека вимагала протилежного.
         Цей набір `freshen()` НЕ чистить. Знімає його лише явна воля людини:
         натиснути кнопку зʼємки руками або перемкнути задачу. */
      autoShootStopped.add(it);
      try {
        const r = await post('/api/shoot-stop', { it });
        /* `stopped:false` — сервер не знайшов живого прогону (добіг саме між
           тактом опитування й натисканням). Мовчати про це не можна: людина
           натиснула «Стоп» і за відсутності слова вирішить, що зупинка не
           спрацювала, — а вона просто спізнилась. Позначку автозʼємки лишаємо:
           той, хто тиснув «Стоп», більше зʼємки не хотів. */
        if (!r.stopped) toast(t('shootStopTooLate', it));
      } catch (e) { tell(t('errShootStopFailed', e.message)); }
      return;
    }
    // Натиснув руками — це і є явна воля, знімаємо обидві позначки.
    autoShootStopped.delete(it);
    autoShootOff.delete(it);
    shootWithProgress(it);
  },

  /* Три дії нижче — Task 6 Плану B: палітра команд (`app/shell-palette.js`)
     називає їх `renpage`/`hidepage`/`delpage`, дослівно ті самі рядки
     дій, що прототипний `pageMenu()` контекстного меню (нижче) вже виконує
     кнопками «Перейменувати…»/«Сховати/показати в превью»/«Видалити
     сторінку». Тому тіла НЕ ДРУГА реалізація: обидва входи (меню рядка й
     палітра) кличуть ОДНІ Й ТІ САМІ функції `renamePage`/`togglePagePublish`/
     `deletePage`, оголошені нижче перед `pageMenu()`, — різниця лише в тому,
     ЯКУ сторінку їм назвати. Контекстне меню знає її з кліку (`pageId`
     аргумент), палітра — рівно ту, що зараз обрана (`pickedPage`), той самий
     принцип, за яким `BAR_ACTIONS.renit`/`dupit`/`delit` діють на
     `curIter()`, а не на аргумент виклику. */
  renpage: () => { if (pickedPage) renamePage(pickedPage); },
  hidepage: () => { if (pickedPage) togglePagePublish(pickedPage); },
  delpage: () => { if (pickedPage) deletePage(pickedPage); },
};

/** Одна делегація на весь контейнер панелі, той самий патерн, що на `bar`
 *  (Task 3). Правий клік по рядку — ОКРЕМИЙ слухач: `contextmenu` не
 *  `click`, і делегувати його разом означало б перевіряти тип події на
 *  кожному кліку. Викликається РІВНО ОДИН РАЗ — при першому створенні
 *  `#pages-panel` у `renderPanel()`, а не на кожен рендер: `innerHTML`
 *  переписує дітей, але сам контейнер (і його слухачі) лишається тим самим
 *  DOM-вузлом. */
function wirePanelEvents(el) {
  el.addEventListener('click', (ev) => {
    const target = ev.target.closest('[data-act]');
    if (!target || target.disabled) return;
    PANEL_ACTIONS[target.dataset.act]?.(target.dataset.val, target, ev);
  });
  /* Фільтр: кожен символ перемальовує ЛИШЕ дерево (`patchAroundFilter`), а під
     час IME-композиції не фільтруємо взагалі — незавершений символ не назва.
     Значення застосовуємо на `compositionend`. */
  el.addEventListener('compositionstart', (ev) => { if (ev.target.id === 'pp-filter') panelComposing = true; });
  el.addEventListener('compositionend', (ev) => {
    if (ev.target.id !== 'pp-filter') return;
    panelComposing = false;
    panelFilter = ev.target.value;
    renderPanel();
  });
  el.addEventListener('input', (ev) => {
    if (ev.target.id !== 'pp-filter' || panelComposing || ev.isComposing) return;
    panelFilter = ev.target.value;
    renderPanel();
  });
  /* Клавіатура дерева: ↑/↓ — сусідній видимий рядок (вибір і фокус, як клік),
     ← — згорнути або до батька, → — розгорнути, Enter — як клік. Лише коли
     фокус на САМОМУ рядку: кнопка «⋯», каретка й поле фільтра мають власні клавіші. */
  el.addEventListener('keydown', (ev) => {
    const row = ev.target.closest?.('.row[data-page]');
    if (!row || ev.target !== row || ev.altKey || ev.ctrlKey || ev.metaKey) return;
    panelKeyNav(row.dataset.page, ev);
  });
  // клавіатурний фокус тримаємо, лише поки людина справді в дереві з клавіатури
  document.addEventListener('pointerdown', () => { panelKbFocus = null; }, true);
  el.addEventListener('focusin', (ev) => {
    const item = ev.target.closest?.('[role="treeitem"]');
    /* Фокус клавіатурою (Tab) на рядку — це і є клавіатурний фокус дерева: без
       запису стрілки стартували б не з того рядка, де стоїть фокус. Фокус від
       кліку (`:focus-visible` хибне) не рахуємо — його знімає pointerdown. */
    const kb = item && (item.matches?.(':focus-visible') ?? true);
    panelKbFocus = kb ? (item.dataset.page ?? null) : null;
  });
  el.addEventListener('contextmenu', (ev) => {
    const row = ev.target.closest('[data-page]');
    if (!row) return;
    ev.preventDefault();
    pageMenu({ x: ev.clientX, y: ev.clientY }, row.dataset.page);
  });
  wirePageDrag(el);
}

function panelKeyNav(rowId, ev) {
  const rows = panelRows();
  /* Поточний — ЗБЕРЕЖЕНИЙ клавіатурний фокус, а не вузол, на якому спрацювала
     подія: автоповтор клавіші може прийти до того, як перемальовка повернула
     фокус, і тоді `ev.target` застарів би — стрілка топталась би на місці. */
  const id = rows.some((r) => r.page.id === panelKbFocus) ? panelKbFocus : rowId;
  const f = rows.find((r) => r.page.id === id);
  if (!f) return;
  const kids = (f.page.children ?? []).length > 0;
  const open = !!panelFilter || expandedPages.has(id);   // під фільтром гілки розкриті примусово
  /* Стрілки переносять фокус і ВИБІР, але сторінку НЕ відкривають: відкриття —
     це `render()` із перезавантаженням рамки, і на кожне натискання автоповтору
     воно було б нестерпним. Відкриває Enter (як клік). Shift тягне діапазон від
     опори, не зрушуючи її. */
  const move = (target) => {
    if (!target) return;
    if (ev.shiftKey && panelAnchor) panelSel = new Set(rowRange(rows, panelAnchor, target) ?? [target]);
    else { panelSel = new Set([target]); panelAnchor = target; }
    panelKbFocus = target;
    renderPanel();
  };
  const flip = () => { panelKbFocus = id; PANEL_ACTIONS.toggle(id); };
  switch (ev.key) {
    case 'ArrowDown': move(stepRow(rows, id, 1)); break;
    case 'ArrowUp': move(stepRow(rows, id, -1)); break;
    case 'ArrowRight':
      if (kids && !open) flip();
      else if (kids) move(firstChildRow(rows, id));
      break;
    case 'ArrowLeft':
      if (kids && open && !panelFilter) flip();
      else if (f.parent && rows.some((r) => r.page.id === f.parent)) move(f.parent);
      break;
    case 'Enter': panelKbFocus = id; PANEL_ACTIONS.page(id); break;
    default: return;
  }
  ev.preventDefault();
}

/**
 * Перетягування рядків панелі — pointer-події (не HTML5 DnD): керований привид
 * і підказка «куди ляже / чому ні» біля курсора. Поріг 4px — клік без руху
 * лишається вибором. Зони рядка (`dropZone`): верх 25% — перед, середина —
 * всередину (лише контейнер), низ 25% — після; для стану 50/50. «Після»
 * розгорнутого контейнера з дітьми = перша дитина. Порожнє місце під деревом —
 * кінець кореня (у фокусі — кінець гілки).
 *
 * ⛔ Зміна вкладеності НІКОЛИ не тиха (свідома заміна межі з `page-order.js`):
 * «всередину» — рамка на весь рядок, «поруч» — лінія по краю; підказка
 * називає ціль; заборона каже причину. Куди саме — рахує `resolveDrop`
 * (`tree-actions.js` → `planMove`) тим самим правилом, що сервер.
 *
 * ⛔ Перемальовка (`renderPanel`) і прокрутка зсувають рядки під нерухомим
 * курсором: тому позицію курсора пам'ятаємо, підсвітку відновлюємо після
 * кожної перемальовки (`dragRepaint`) і прокрутки, а план при відпусканні
 * ЛІЧИМО НАНОВО з точки відпускання — кеш міг показувати вже неіснуючий рядок.
 *
 * Поза обсягом (свідомо): дотик (touch) — жест лише для миші/пера; автопрокрутка
 * біля краю панелі — довгий список тягнуть колесом.
 *
 * Делегація на корені панелі: рядки перемальовуються цілком, і слухачі на самих
 * рядках зникали б із кожною перемальовкою.
 */
let dragRepaint = null;   // хук для `renderPanel`: жест активний → відновити підсвітку
let dragActive = () => false;   // чи є жест (навіть до порогу руху): його ставить `wirePageDrag`
function wirePageDrag(el) {
  let d = null;          // {ids, x0, y0, cx, cy, on, pid, it, sig, openT, openId}
  dragActive = () => d !== null;
  let eatClick = false;  // клік, що завершує жест, не мусить ще й обрати рядок
  const mk = (id, cls) => document.getElementById(id)
    || Object.assign(document.body.appendChild(document.createElement('div')), { id, className: cls });
  const AIM = ['row--drop-before', 'row--drop-after', 'row--in', 'row--nope', 'panel-fill--drop'];
  const clearAim = () => el.querySelectorAll(`.${AIM.join(',.')}`).forEach((r) => r.classList.remove(...AIM));
  const hide = () => { document.getElementById('pp-ghost')?.remove(); document.getElementById('pp-tip')?.remove(); };
  const rowOf = (id) => el.querySelector(`[data-page="${CSS.escape(id)}"]`);
  const markDragged = () => { for (const id of d.ids) rowOf(id)?.classList.add('row--drag'); };
  const onEsc = (ev) => {
    if (ev.key !== 'Escape' || !d) return;
    // один Esc скасовує лише жест: не закриває заодно меню, палітру чи коментатор
    ev.preventDefault(); ev.stopPropagation();
    finish(false);
  };
  const onBlur = () => finish(false);
  const dragState = () => ({ expanded: expandedPages, filtering: !!panelFilter, focus: panelFocus });
  const hitAt = (x, y) => {
    const hit = document.elementFromPoint(x, y);
    const row = hit?.closest?.('#pages-panel [data-page]');
    if (row) {
      const r = row.getBoundingClientRect();
      return { kind: 'row', id: row.dataset.page, y, top: r.top, height: r.height };
    }
    return hit?.closest?.('.panel-fill') ? { kind: 'fill' } : null;
  };

  /* force — після перемальовки/прокрутки те саме «місце» вже інші вузли DOM. */
  const aim = (x, y, force = false) => {
    const hit = hitAt(x, y);
    const z = zoneOfHit(panelPages, hit, dragState());
    const sig = `${z.where}|${z.target}`;
    const tip = mk('pp-tip', 'drag-tip');
    tip.style.left = `${x + 14}px`; tip.style.top = `${y + 30}px`;
    if (!force && sig === d.sig) return;
    d.sig = sig;
    clearAim();
    const res = resolveDrop(panelPages, d.ids, hit, dragState());
    const all = flattenPages(panelPages);
    if (res.quiet) tip.style.display = 'none';
    else {
      const bad = !!res.plan?.err;
      const into = !bad && res.plan.parent ? all.find((r) => r.page.id === res.plan.parent)?.page.name : null;
      tip.textContent = bad ? t(errKey(res.plan.err) ?? 'treeErrNotFound') : into ? t('dropInto', into) : t('dropRoot');
      tip.className = `drag-tip${bad ? ' drag-tip--no' : ''}`;
      tip.style.display = '';
    }
    if (res.mark.row && res.mark.cls) rowOf(res.mark.row)?.classList.add(res.mark.cls);
    if (res.fill) el.querySelector('.panel-fill')?.classList.add('panel-fill--drop');
    // згорнутий контейнер розкривається при зависанні «всередину» 600 мс
    const f = hit?.kind === 'row' && all.find((r) => r.page.id === hit.id);
    if (res.where === 'inside' && f?.page.children?.length && !expandedPages.has(hit.id)) {
      if (d.openId !== hit.id) {
        clearTimeout(d.openT); d.openId = hit.id;
        d.openT = setTimeout(() => {
          if (d && d.openId === hit.id && picked === d.it) { expandedPages.add(hit.id); saveExpanded(); renderPanel(); }
        }, 600);
      }
    } else { clearTimeout(d.openT); d.openId = null; }
  };
  const repaint = () => { if (!d?.on) return; markDragged(); aim(d.cx, d.cy, true); };

  el.addEventListener('pointerdown', (ev) => {
    if (d?.on) return;                                      // другий вказівник посеред жесту
    if (ev.button !== 0) return;
    if (ev.shiftKey || ev.metaKey || ev.ctrlKey || ev.altKey) return;   // клік-вибір, не жест
    if (treeGate.busy) return;                              // запит у дорозі — рухати нічого
    const row = ev.target.closest?.('[data-page]');
    if (!row || ev.target.closest('button,input')) return;   // каретка, «⋯», фільтр — свої
    const id = row.dataset.page;
    d = { ids: panelSel.has(id) ? [...panelSel] : [id], x0: ev.clientX, y0: ev.clientY, cx: ev.clientX, cy: ev.clientY,
      on: false, pid: ev.pointerId, it: picked, sig: null };
  });
  el.addEventListener('pointermove', (ev) => {
    if (!d || ev.pointerId !== d.pid) return;
    d.cx = ev.clientX; d.cy = ev.clientY;
    if (!d.on) {
      if (Math.hypot(ev.clientX - d.x0, ev.clientY - d.y0) < 4) return;
      d.on = true;
      /* capture — лише ПІСЛЯ порогу: захоплений від pointerdown вказівник
         переносить ціль кліку на панель, і звичайний клік по рядку перестав би
         доходити до делегації `data-act`. */
      try { el.setPointerCapture(ev.pointerId); } catch { finish(false); return; }
      document.addEventListener('keydown', onEsc, true);
      window.addEventListener('blur', onBlur);
      dragRepaint = repaint;
      d.ids = topIds(panelPages, d.ids);
      markDragged();
      const first = flattenPages(panelPages).find((x) => x.page.id === d.ids[0]);
      mk('pp-ghost', 'drag-ghost').innerHTML = `${ico(first?.kind === 'folder' ? 'folder' : first?.kind === 'state' ? 'state' : 'page', 14)}<span>${esc(first?.page.name ?? '')}</span>${d.ids.length > 1 ? `<b>+${d.ids.length - 1}</b>` : ''}`;
    }
    const g = mk('pp-ghost', 'drag-ghost');
    g.style.left = `${ev.clientX + 14}px`; g.style.top = `${ev.clientY + 8}px`;
    aim(ev.clientX, ev.clientY);
  });
  // прокрутка не буває «bubbles» — слухаємо в capture; рядки поїхали під курсором
  el.addEventListener('scroll', (ev) => {
    if (d?.on && ev.target.classList?.contains('panel-body')) aim(d.cx, d.cy, true);
  }, true);
  const finish = async (commit, ev = null) => {
    const cur = d; d = null;
    if (!cur) return;
    dragRepaint = null;
    clearTimeout(cur.openT); clearAim(); hide();
    document.removeEventListener('keydown', onEsc, true);
    window.removeEventListener('blur', onBlur);
    el.querySelectorAll('.row--drag').forEach((r) => r.classList.remove('row--drag'));
    if (!cur.on) return;
    eatClick = true;
    /* Клік, що завершує жест, браузер шле лише коли pointerdown і pointerup на
       одному елементі; інакше прапор завис би й з'їв наступний справжній клік. */
    setTimeout(() => { eatClick = false; }, 0);
    /* План — з точки ВІДПУСКАННЯ, не з кешу руху (див. шапку). */
    const res = commit && ev ? resolveDrop(panelPages, cur.ids, hitAt(ev.clientX, ev.clientY), dragState()) : null;
    const plan = res?.plan ?? null;
    /* Ітерацію могли перемкнути посеред жесту: план лічили на старому дереві,
       тож у нову він не йде й розкриття не чіпає. */
    if (!shouldCommitDrop({ commit, plan, startIt: cur.it, currentIt: picked })) return;
    const r = await treePost('/api/page-move', { ids: plan.ids, parent: plan.parent, index: plan.index }, { it: cur.it });
    if (r && picked === cur.it) {
      // розкриваємо ціль лише ПІСЛЯ успішного переносу — відмова не лишає слід
      if (res.where === 'inside' || res.where === 'first') { expandedPages.add(res.target); saveExpanded(); }
      await loadPages(); render();
    }
  };
  el.addEventListener('pointerup', (ev) => finish(true, ev));
  el.addEventListener('pointercancel', () => finish(false));
  el.addEventListener('lostpointercapture', () => finish(false));
  el.addEventListener('click', (ev) => {
    if (eatClick) { eatClick = false; ev.stopPropagation(); ev.preventDefault(); }
  }, true);
}

/**
 * Позиціювання `.cv-ctx`: `position:fixed` із координатами від
 * `getBoundingClientRect()` — ТА САМА ідіома, що вже працює в `pillMenu`
 * (нижче). У прототипі це меню малюється дитиною рамки з `transform` на
 * предку (`docs/proto/shell.html`); у бою такого предка нема, а
 * `.panel-body` має `overflow:auto` й зрізала б `position:absolute` дитину —
 * звідси `fixed`, а не спроба повторити прототип буквально.
 *
 * Клемпінг — те, чого нема в `pillMenu`/старому `pageMenu`: обидва
 * відкривались лише правим кліком УСЕРЕДИНІ полотна, де вихід за край вікна
 * малоймовірний. Тут другий відкривач — кнопка «⋯» у панелі 246px (чи 46px
 * у рейці), і без клемпінгу меню поїхало б за правий (а в рейці й лівий)
 * край. Розмір міряємо ПІСЛЯ вставки в DOM — точніше за жорстко зашиту
 * константу прототипу (`W=230,H=210`, «на око»). */
function positionCtxMenu(el, { x, y }) {
  const maxX = Math.max(8, window.innerWidth - el.offsetWidth - 8);
  const maxY = Math.max(8, window.innerHeight - el.offsetHeight - 8);
  el.style.left = `${Math.min(Math.max(8, x), maxX)}px`;
  el.style.top = `${Math.min(Math.max(8, y), maxY)}px`;
}

// --- контекст-меню сторінки: перейменувати / сховати в превью / видалити ---
/**
 * Три тіла нижче — Task 6 Плану B: винесені з `pageMenu()` (де вони раніше
 * жили безіменними `onclick`), щоб палітра команд (`PANEL_ACTIONS.renpage`/
 * `hidepage`/`delpage`, `pickedPage` замість `pageId` контекстного меню)
 * кликала РІВНО ту саму дію, а не другу реалізацію поруч. Поведінка тут не
 * змінена — це чиста витяжка тіла з `onclick` у назване оголошення.
 */
async function renamePage(pageId) {
  const it = picked;                  // фіксуємо ДО await — див. «＋ стор.» у render()
  /* Поле — з ЧИННОЮ назвою (fb-22092026-31674a). Порожнє поле не показувало, що
     саме править дизайнер, а будь-яке «Гаразд» ЗАТИРАЛО назву. Ітерація свою
     назву в поле клала завжди (`renit`); сторінка — ні. `ask` сам виділяє
     значення, тож набір поверх замінює, а стрілка дає поправити частину. */
  const cur = flattenPages(panelPages).find((x) => x.page.id === pageId)?.page.name || '';
  const name = await ask(t('menuRenamePagePrompt'), cur);
  if (name === null) return;
  try { await post('/api/page-rename', { it, page: pageId, name }); await loadPages(); render(); }
  catch (e) { tellError(t('errTRenamePage'), e.message); }
}
/**
 * Переставити сторінку серед сусідів: `{delta: ±1}` із меню або `{index}` із
 * перетягування (fb-09092026-d4c51b). Одна дія на обидва входи — як
 * `renamePage` на меню й палітру: друга реалізація поруч розійшлася б.
 */
async function movePage(pageId, how) {
  const it = picked;                  // фіксуємо ДО await — див. «＋ стор.» у render()
  try { await post('/api/page-move', { it, page: pageId, ...how }); await loadPages(); render(); }
  catch (e) { tellError(t('errTMovePage'), e.message); }
}
/** Вузол, на якому діє меню/палітра: єдиний вибраний, інакше відкрита сторінка. */
function treeTarget() {
  return pickTreeTarget(panelSel, pickedPage);
}
/** Загорнути вибране (або відкриту сторінку) у нову теку й одразу дати назву. */
async function groupSelection() {
  const it = picked;
  const ids = groupTargetIds(panelSel, pickedPage);
  if (!ids.length) return;
  const r = await treePost('/api/page-group', { ids, name: t('newFolder') }, { it });
  if (!r || picked !== it) return;
  panelSel = new Set([r.node.id]);
  panelAnchor = r.node.id;
  expandedPages.add(r.node.id); saveExpanded();
  await loadPages(); render();
  if (picked !== it) return;
  renamePage(r.node.id);              // той самий `ask`, що й для нової теки
}
async function ungroupNode(id) {
  const it = picked;
  if (!(await treePost('/api/page-ungroup', { id }, { it })) || picked !== it) return;
  panelSel.delete(id);
  await loadPages(); render();
}
/** На рівень вище: стати сусідом батька, одразу після нього. */
async function outdentNode(id) {
  const it = picked;
  const line = pathOf(panelPages, id);
  if (line.length < 2) return;
  const parent = line[line.length - 2];
  const grand = line.length > 2 ? line[line.length - 3] : null;
  const sibs = grand ? grand.children : panelPages;
  const r = await treePost('/api/page-move', { ids: [id], parent: grand ? grand.id : null,
    index: sibs.findIndex((n) => n.id === parent.id) + 1 }, { it });
  if (r && picked === it) { await loadPages(); render(); }
}
/** Стан ↔ сторінка; теку не чіпаємо (сервер однаково відмовить). */
async function toggleKind(id) {
  const it = picked;
  const f = flattenPages(panelPages).find((x) => x.page.id === id);
  if (!f || f.kind === 'folder') return;
  const r = await treePost('/api/page-kind', { id, kind: f.kind === 'state' ? 'page' : 'state' }, { it });
  if (r && picked === it) { await loadPages(); render(); }
}
/**
 * Дія над деревом: той самий `post`, плюс `it` і `rev`, плюс ОДНЕ місце, де
 * відмова стає зрозумілим текстом. 409 — дерево змінилось під панеллю
 * (Claude додав сторінку): перечитуємо й просимо повторити, а не мовчки
 * накладаємо дію на чужий стан. Повертає відповідь або null (відмова вже
 * показана).
 */
/* Замок запитів дерева — `treeBusyGate` (чистий, зі знятим замком і на винятку).
   Клас ставимо на живий вузол без перемальовки: перемальовка на початку й в
   кінці КОЖНОГО запиту скидала б фокус рядка й позицію скролу. */
const treeGate = treeBusyGate((on) => {
  const el = document.getElementById('pages-panel');
  el?.classList.toggle('panel--busy', on);
  if (el) { if (on) el.setAttribute('aria-busy', 'true'); else el.removeAttribute('aria-busy'); }
});
const TREE_TIMEOUT_MS = 15000;
/**
 * `opts.it` — ітерація, В ЯКІЙ людина вирішила діяти: якщо до виклику (діалог,
 * попередній крок циклу) вона вже змінилась, запиту НЕ буде — інакше id старої
 * ітерації лягли б у нову (`treePostNow` читає `picked` свіжим).
 */
async function treePost(path, body, opts = {}) {
  if (opts.it !== undefined && picked !== opts.it) return null;
  /* Дії над деревом не перекриваються: другий запит із ТИМ САМИМ rev дав би 409
     на наш же перший запис. Мовчки ігнорувати не можна — тост пояснює. */
  if (treeGate.busy) { toast(t('treeBusy')); return null; }
  lastTreeError = '';
  return treeGate.run(() => treePostNow(path, body, opts.it ?? picked, !!opts.quiet));
}
/* Текст останньої відмови: масова дія збирає його в ОДНЕ повідомлення (`quiet`
   крок не показує свого, бо оверлей один і скасував би підсумок). */
let lastTreeError = '';
async function treePostNow(path, body, it, quiet = false) {
  const say = (msg) => { lastTreeError = msg; if (!quiet) tell(msg); };
  /* Завислий запит тримав би замок вічно — обриваємо за 15 с. */
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TREE_TIMEOUT_MS);
  try {
    const r = await api(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ it, rev: panelRev, ...body }), signal: ctl.signal,
    });
    /* Успіх означає: файл не мінявся від rev клієнта, тож новий rev — стан
       після НАШОЇ ж дії. Без цього цикл дій (масове видалення) ловив би 409
       уже на другому запиті — власним же попереднім записом. */
    if (typeof r?.rev === 'string' && picked === it) panelRev = r.rev;
    return r;
  } catch (e) {
    if (e.name === 'AbortError') {
      /* Невідомо, чи сервер встиг записати: перечитуємо дерево й чесно кажемо. */
      if (picked === it) { await loadPages(); render(); }
      say(t('treeTimeout'));
      return null;
    }
    /* Дизайнер міг перемкнути ітерацію, поки дія летіла: «дерево змінилось»
       про дерево, якого він уже не бачить, — брехня, а `loadPages` перетер би
       стан нової ітерації. Відмову тоді просто ковтаємо (null). */
    if (e.status === 409) {
      if (picked === it) { await loadPages(); render(); say(t('treeStale')); }
      return null;
    }
    const key = errKey(e.code);
    say(key ? t(key) : t('errFailed', e.message));
    return null;
  } finally {
    clearTimeout(timer);
  }
}
async function togglePagePublish(pageId) {
  try { await post('/api/page-publish-toggle', { it: picked, page: pageId }); await loadPages(); render(); }
  catch (e) { tellError(t('errTPagePublish'), e.message); }
}
/* Видалення — ОДНА дорога для одного й багатьох вузлів (`deleteDialogModel`):
   питання зі списком того, що зникне (до 30 назв + «…і ще N»); «прибрати лише
   теку, вміст підняти» — лише для однієї цілі з дітьми. Скасування — нічого. */
async function deleteNodes(ids, { confirmed = false } = {}) {
  const it = picked;                  // фіксуємо ДО await — ідіома `freshen()`
  /* Зайнято — кажемо ДО діалогу: інакше людина підтвердила б видалення й
     втратила його на «дерево зайняте». */
  if (treeGate.busy) { toast(t('treeBusy')); return; }
  const model = deleteDialogModel(panelPages, ids);
  if (!model) return;
  let mode = 'all';
  if (model.kind === 'yesno') {
    if (!confirmed && !(await askYesNo(t('menuDeletePageConfirm'), { yes: t('menuDeleteYes'), danger: true }))) return;
  } else {
    const names = model.more ? [...model.names, t('delMore', model.more)] : model.names;
    const choices = [{ a: 'all', label: t('delAll'), danger: true }];
    if (model.unwrap) choices.unshift({ a: 'unwrap', label: t('delUnwrap') });
    const choice = await askChoice(t(model.titleKey, ...model.titleArgs),
      { details: names, choices, detailsLabel: t('delListLabel') });
    if (!choice) return;
    mode = choice;
  }
  /* Діалог міг тривати довго: ітерацію могли перемкнути, а дерево — змінити. */
  if (picked !== it) return;
  /* Відкрита сторінка зникне разом із предком; при `unwrap` — лише якщо вона САМА
     й є прибраним вузлом (вміст нащадків лишається). */
  const { done, stopped } = await runSequential(model.ids,
    async (id) => !!(await treePost('/api/page-delete', { page: id, mode }, { it, quiet: true })),
    { stillValid: () => picked === it });
  if (picked !== it) return;          // відповідь про іншу ітерацію не чіпає нинішню
  /* Відкрита сторінка зникла, коли серед ВИДАЛЕНИХ є її предок (режим `all`) або
     вона сама (`unwrap` прибирає сам вузол; вміст нащадків лишається). Рахуємо
     по `done`, а не по цілях: частково виконана дія не мусить скидати сторінку. */
  if (pickedPage && done.some((id) => (mode === 'all'
    ? pathOf(panelPages, pickedPage).some((n) => n.id === id) : id === pickedPage))) {
    pickedPage = null; pickedState = null;
  }
  const left = model.ids.filter((id) => !done.includes(id));
  panelSel = new Set(left);           // не видалене лишається виділеним
  const note = composeDeleteNote(t, { done: done.length, total: model.ids.length,
    why: lastTreeError, stopped });
  if (note) tell(note);
  await loadPages(); render();
}
const deletePage = (pageId) => deleteNodes([pageId]);

// Два входи до ОДНОГО меню: «⋯» рядка (`PANEL_ACTIONS.pagemenu`) і правий
// клік по рядку (`wirePanelEvents`) — спека Task 4, п.1: дія, досяжна лише
// правим кліком, недосяжна з клавіатури. `anchor` — вже порахована точка
// `{x,y}` у координатах вікна, а не подія: два виклики рахують її по-різному
// (кут кнопки проти курсора), і рахує це той, хто кличе, а не це меню.
function pageMenu(anchor, pageId) {
  document.getElementById('cv-ctx')?.remove();
  const m = document.createElement('div');
  m.id = 'cv-ctx';
  m.className = 'cv-ctx';
  const f = flattenPages(panelPages).find((x) => x.page.id === pageId);
  const kind = f?.kind ?? 'page';
  const multi = panelSel.size > 1 && panelSel.has(pageId);
  const ids = pageMenuItems({
    kind, multi, hasChildren: (f?.page.children ?? []).length > 0, hasParent: !!f?.parent,
    /* «Підняти/Опустити» — лише коли є куди: пункт, що на клік нічого не
       робить, обіцяв би дію, якої немає (та сама умова, що й у заголовка кадрів). */
    canUp: canMove(panelPages, pageId, -1), canDown: canMove(panelPages, pageId, 1),
  });
  const LABEL = {
    folder: kind === 'page' ? t('newWidgetFolder') : t('newFolder'),
    rename: t('menuRename'), group: t('menuGroup'), ungroup: t('menuUngroup'),
    up: t('menuMoveUp'), down: t('menuMoveDown'), out: t('menuOutdent'), focus: t('menuFocus'),
    kind: kind === 'state' ? t('menuToPage') : t('menuToState'),
    pub: t('menuTogglePublish'), delete: t('menuDeletePage'),
  };
  m.innerHTML = ids.map((a) => `<button data-a="${a}">${esc(LABEL[a])}</button>`).join('');
  document.body.appendChild(m);
  positionCtxMenu(m, anchor);
  // Клік повз ЗАКРИВАЄ, Escape ЗАКРИВАЄ (спека Task 4, п.3) — жодного з двох
  // не мав ані цей менюшник, ані `pillMenu` раніше: обидва рятував лише клік
  // повз. `setTimeout(…,0)` — щоб клік, який ВІДКРИВ меню, не долетів сюди й
  // не закрив його тієї ж миті.
  const close = () => {
    m.remove();
    document.removeEventListener('click', close);
    document.removeEventListener('keydown', onKey);
  };
  const onKey = (ev) => { if (ev.key === 'Escape') close(); };
  setTimeout(() => {
    document.addEventListener('click', close);
    document.addEventListener('keydown', onKey);
  }, 0);
  /* Не кожен пункт є в кожному меню (залежить від типу вузла) — прив'язуємо
     лише наявні. */
  const on = (a, fn) => { const b = m.querySelector(`[data-a="${a}"]`); if (b) b.onclick = () => { close(); fn(); }; };
  on('folder', () => { panelSel = new Set([pageId]); PANEL_ACTIONS.newfolder(); });
  on('rename', () => renamePage(pageId));
  on('group', () => { if (!multi) panelSel = new Set([pageId]); groupSelection(); });
  on('ungroup', () => ungroupNode(pageId));
  on('up', () => movePage(pageId, { delta: -1 }));
  on('down', () => movePage(pageId, { delta: 1 }));
  on('out', () => outdentNode(pageId));
  on('focus', () => PANEL_ACTIONS.focus(pageId));
  on('kind', () => toggleKind(pageId));
  on('pub', () => togglePagePublish(pageId));
  /* «Видалити» (етап В): для одного вузла без дітей меню саме стає питанням — підтвердження там, де дія.
     Тека з вмістом чи кілька вузлів — темна картка з переліком (`askChoice`), як було: перелік у меню не вміщається. */
  const delBtn = m.querySelector('[data-a="delete"]');
  if (delBtn) delBtn.onclick = (ev) => {
    const ids = multi ? [...panelSel] : [pageId];
    const model = deleteDialogModel(panelPages, ids);
    if (!model || model.kind !== 'yesno') { close(); deleteNodes(ids); return; }
    ev.stopPropagation();
    const name = f?.page.name || '';
    const titleKey = kind === 'state' ? 'cfmDelState' : (kind === 'folder' ? 'cfmDelFolder' : 'cfmDelPage');
    m.classList.add('cv-ctx--confirm');
    m.innerHTML = confirmHTML({ title: t(titleKey, name), yes: t('menuDeleteYes'), no: t('cfmNo'),
      yesAttrs: 'data-a="delyes"', noAttrs: 'data-a="delno"' });
    /* Клік усередині питання — не «повз»: інакше документний слухач закрив би меню раніше за кнопку. */
    m.addEventListener('click', (e) => e.stopPropagation());
    m.querySelector('[data-a="delno"]').onclick = () => close();
    m.querySelector('[data-a="delyes"]').onclick = () => { close(); deleteNodes(ids, { confirmed: true }); };
    positionCtxMenu(m, anchor);
    m.querySelector('.cfm-no')?.focus();
  };
}

// ===== Режим «Огляд» — bird-view холст (T-23) =====
/* Розміри кадру, зазори й поля смуги — у `canvas-geom.js`: ті самі числа міряють
   живі перевірки, і поки вони лежали тут, кожна зміна зазору червоніла в них
   «1376 !== 1480», ніби зламалась фіча. */
let cvx = 0, cvy = 0, cvscale = 1, cards = [];
/* Режим коментування коментатора полотна (етап 2 T-45): клік по кадру тоді —
   коментар, а не «відкрити кадр». Прапорець ставить сам коментатор (`armed`). */
let commentArmed = false;
/* Коментарі прямо на «Огляді» (T-45): comment-layer у режимі «полотно». Оболонка
   дає йому камеру, кадри й канал — пінів сама не малює (принцип 6 PRODUCT.md).
   Усі залежності — замикання, а не знімки: їх читають на кожному кадрі камери. */
const ovc = overviewComments({
  canvasEl,
  cam: () => ({ x: cvx, y: cvy, scale: cvscale }),
  cards: () => cards,
  cardW,
  picked: () => picked,
  channel: () => (noTeamComments() ? 'local' : 'dual'),
  frameKeyOf: (card) => frameKey(card.id, canvasW),
  shotOf: (card) => shotManifest.shots?.[frameKey(card.id, canvasW)] || null,
  camTo: (target) => { userMoved = true; camTo(target); },
  focusCard: (card) => {
    userMoved = true;
    camTo(focusBox({ x: card.x, y: card.y, w: cardW() },
                   { w: canvasEl.clientWidth, h: canvasEl.clientHeight }));
  },
  /* Аудиторії піна на «Огляді» (поправки 11, 12, 20): без командного каналу — одна (чипів нема). */
  audiences: () => (noTeamComments() ? [] : [
    { id: 'local', label: t('audChipLocal'), icon: 'bot', color: LOCAL_PIN_COLOR, private: true },
    { id: 'project', label: t('audChipTeam'), icon: 'team', note: t('audChipTeamNote') },
  ]),
  onArmed: (on) => { commentArmed = !!on; canvasEl.classList.toggle('cv-commenting', commentArmed); },
  /* Панель коментарів — оболонки (0.26.0): коментатор полотна живе в цьому ж вікні й кличе приймач напряму. */
  host: {
    /* Скільки справа у вікні займає панель оболонки: композер коментатора не лягає під неї. */
    rightInset: () => (cmtOpen && !cmtEl.hidden ? cmtEl.getBoundingClientRect().width : 0),
    /* Скільки знизу полотна перекриває острівець: форма піна й «Кілька» лягають над ним. */
    bottomInset: () => islandInsetOver(canvasEl.getBoundingClientRect()),
    /* `onReady` летить ВСЕРЕДИНІ `init()`, коли `ovc.layer` ще не присвоєно (присвоєння — після повернення з `init`):
       мікрозадача дає присвоїти, і `cmtLayer()` уже бачить шар (знімок, режим коментування при відкритій панелі). */
    onReady: () => queueMicrotask(() => onCommentsEvent('canvas', { ev: 'ready' })),
    defaultAudience: () => { try { return localStorage.getItem(CMT_AUD_KEY); } catch (e) { return null; } },
    onAudiencePick: (id) => { try { localStorage.setItem(CMT_AUD_KEY, id); } catch (e) {} },
    onChange: (snapshot) => onCommentsEvent('canvas', { ev: 'change', snapshot }),
    onSelect: (id) => onCommentsEvent('canvas', { ev: 'select', id }),
    onMode: (on) => onCommentsEvent('canvas', { ev: 'mode', on: !!on }),
  },
  offLabel: (n) => t('pinsOffFrame', n),
  fail: (e) => toast(t('toastOverviewCommentsDown', (e && e.message) || String(e))),
});
/* Ряди сіткового виду з їхніми підписами: `[{title, cards: [...]}]`. Модульна
   змінна з тієї ж причини, що `flowBox`: склад рядів знає лише `buildGridView`,
   а потрібен він і `relayoutAll` (де ряди перетворюються на координати й
   підписи), і `fitAll` (де з них береться габарит світу). */
let gridRows = [];
let userMoved = false;
/* Який світ зараз на полотні: `{task, it, view}`. Потрібен рівно для одного
   рішення — чи можна перенести камеру через перебудову. Переносимо ЛИШЕ в межах
   того самого світу: інша задача, інша ітерація чи інший вид — це інші габарити
   й інша розкладка, і збережений там зум показував би порожнечу збоку від графа
   замість роботи. `null` — полотна ще не будували або з нього вийшли (див.
   `applyMode`), тобто переносити нема чого. Вид беремо саме `effView()`, а не
   `canvasView`: липкий вибір дизайнера мовчки відступає в сітку, поки не
   завантажився перелік сторінок, і по `canvasView` два РІЗНІ світи (граф і
   сітка) виглядали б одним.

   Задача в ключі ОБОВʼЯЗКОВА, і це не запас на майбутнє: id ітерацій ПЕР-ЗАДАЧНІ
   — `it1` є в кожній. Без неї перемикання задачі в «Огляді» нормалізує `picked` в
   `it1` НОВОЇ задачі, `camWorld.it === picked` виходить істинним, і камера
   переїжджає у світ чужої задачі (виміряно: зум 0.384 замість власного fit 0.229
   — дизайнер потрапляє в кадр, порахований для іншої роботи). Ключ мусить
   описувати світ ПОВНІСТЮ саме тут, бо будь-який новий шлях зміни задачі дістає
   захист безкоштовно, а обнулення в обробнику `#task-sel` було б черговим
   переліком місць, які треба не забути. */
let camWorld = null;
/* Габарит світу у флоу-виді. Модульний, бо рахує його `buildFlowView` (лише там
   відомі і смуги, і група «не у флоу»), а потрібен він `fitAll()`. `null` —
   вид сітковий або флоу ще не будували. */
let flowBox = null;

// ===== Інспектор: кнопка у смузі, сам оверлей — у iframe =====

/** API інспектора всередині макета, або null (макет ще не готовий / bare). */
function inspectorApi() {
  try { return frame.contentWindow?.CanvasInspector || null; } catch (e) { return null; }
}

/* ===== Тюнер: ручки в панелі, жива правка на макеті (Task 13+14) ===== */

/* Стан ТЮНЕРА — те, що дизайнер накрутив і що поїде Клоду пакетом
   рекомендацій. Живе ТУТ, у батьківському вікні, а не в документі макета:
   `applyMode` присвоює `frame.src` на кожному повному рендері (вище,
   `app.js:129`), тож будь-який клік, що перезавантажує рамку, тихо стер би
   всю роботу.
   ⛔ У МАКЕТ І В ШАР КОМЕНТАРІВ не пишеться нічого. На диск їде РІВНО пакет
   рекомендацій (`packageJSON` → `POST /api/tuner`, `saveTune`), і це окремий
   файл поруч із коментатором, а не всередині нього.
   Перезавантаження рамки стан не чіпає — і не мусить: інлайн-стилі, які воно
   знімає з макета, накладаються назад одразу після `load` (`reapplyTune`,
   Task 17). Доти це була відома межа Task 13/14: панель показувала правку,
   якої на макеті вже немає. */
let tuneState = emptyTune();

/**
 * Правки, які на ЦЬОМУ документі макета НЕ ЛЕЖАТЬ: список пар
 * `{selector, prop}`.
 *
 * ⛔ ЧОМУ ЦЕ НЕ В `tuner-model.js` І НЕ В ПАКЕТІ. Модель описує НАМІР
 * дизайнера — «цей блок, ця властивість, було/стало», — і рівно це їде на
 * диск і Клоду. «Лягло чи не лягло» наміром не є: це факт про ОДИН конкретний
 * документ, який щойно народився в рамці, і той самий пакет на сусідній
 * ітерації (чи після того, як Клод перепише сторінку) дасть іншу відповідь.
 * Поклади ми його в модель — він поїхав би у файл, тобто Клод читав би вчорашній
 * стан чужої вкладки як частину замовлення. Тому факт живе тут, помирає разом
 * із документом (`reapplyTune` перезбирає його на кожному `load`) і доїжджає
 * рівно до панелі — туди, де про нього питають очима.
 *
 * ⛔ І ПРАВКУ ВІН НЕ ПРИБИРАЄ. Не лягло — не означає «не було»: сторінку могли
 * переписати між двома відкриттями канваса, а замовлення дизайнера від цього
 * не зникає. Список лише дає панелі СКАЗАТИ про це замість малювати правку
 * так, ніби вона на екрані.
 *
 * Пари, а не ключ-рядок: другий формат ключа поруч із `elementKey` — це друга
 * реалізація тієї самої адреси, яка колись розійдеться з першою. Лінійний
 * пошук тут дешевий за побудовою: правок на сторінці — десятки.
 */
let tuneMissing = [];

const isMissing = (sel, prop) => tuneMissing
  .some((m) => m.selector === sel && m.prop === prop);

/** Правка лягла (або її більше немає) — факт про документ мусить це визнати.
 *  Без цього рядка панель бреше В ІНШИЙ БІК: дизайнер щойно крутнув ручку й
 *  побачив зміну, а поруч висить позначка «не лягло» з попереднього відкриття. */
function forgetMissing(sel, prop) {
  if (!isMissing(sel, prop)) return false;
  tuneMissing = tuneMissing.filter((m) => !(m.selector === sel && m.prop === prop));
  return true;
}

/* ⛔ ТУТ БІЛЬШЕ НЕМАЄ СТАНУ ПАНЕЛІ, і це головне, що T-39 прибрав із цього
   файла. Доти жили три поля — `inspTab` (яку вкладку тримає дизайнер),
   `inspModeWas` (останній бачений режим оверлея) і пара
   `inspFrameSeq`/`inspModeSeenAt` (покоління документа макета). Усі чотири
   існували заради ОДНІЄЇ умови: вкладок було три, режимів — два, тобто
   вкладка «Тюнер» не відповідала жодному режиму, мусила переживати
   перезавантаження рамки й при цьому не плутатись із «дизайнер натиснув M»
   (новий документ завжди починає з `cascade`, і без поколінь це виглядало
   однаково). Вміст тієї вкладки переїхав у підвал «Стилів» — умова зникла, і
   разом із нею зникла причина тримати друге джерело правди про те, що
   показано в панелі. Вкладка тепер і Є `CanvasInspector.mode`. */

/* Рядки ОСТАННЬОГО звіту, розкладені по властивостях. Звідси `setEdit` бере
   походження значення (`computed`, `raw`, токен, вирок, підказки). НЕ другий
   виклик `report()` у мить кручення: він порахував би каскад уже з накрученим
   інлайном і записав би в пакет сам тюнер замість джерела значення. */
let inspDecls = new Map();

/* Стан панелі властивостей. `inspSides` — дизайнер розкрив сторони відступів («окремо»); `inspOffAt` — курсор кола
   «N поза ДС» (скидається, коли вибрано інший елемент: `inspPinKey`); `inspScrub` — активне тягнення підпису. */
let inspSides = false;
let inspOffAt = -1;
let inspPinKey = '';
let inspScrub = null;

/** Сторінка як МЕЖА видимості правок: правка з «Головної» не сміє потрапити
 *  в пакет «Пошуку». Ключ збирається так само, як уже збирає `glpush`
 *  (`${picked}/${pickedPage}`) — другий спосіб назвати ту саму сторінку
 *  колись розійшовся б із першим. */
function tunePage() {
  if (!picked) return null;
  return pickedPage ? `${picked}/${pickedPage}` : picked;
}

/** Правки, записані на ЗАПІНЕНОМУ зараз елементі, або null.
 *  Ключ елемента рахує `elementKey` — рівно та сама функція, якою його рахує
 *  `setEdit` усередині моделі: друга реалізація ключа поруч із цією
 *  розійшлася б на першій же правці (докстрінг `elementKey`). */
function tuneEdits() {
  const api = inspectorApi();
  const page = tunePage();
  /* `identity()` БЕЗ властивості: тут потрібен лише ключ елемента (ланцюжок
     предків), а не переможець каскаду — тобто без `getComputedStyle` і без
     розбору каскаду (`pickWinner(declsFor(…))`, найдорожчої частини
     `identity(prop)`).

     ⚠️ «Обхід дерева» тут читалось як «вгору по предках», і це недоказувало:
     `ownText` має ФОЛБЕК — в елемента без власних текстових вузлів (а це
     будь-яка обгортка) він бере `el.textContent`, тобто весь текст піддерева.
     На запіненій кореневій обгортці це текст усієї сторінки, і кличеться воно
     на кожну перемальовку панелі ПІД ВКЛАДКОЮ КАСКАДУ (`rep` нижче) — тобто
     рівно там, де живуть ручки, і ~кожні 33мс, поки дизайнер тримає стрілку з
     автоповтором.

     ЗМІРЯНО 18.09.2026 живцем, на справжньому важкому лендингу (`bf360`, it6:
     712 вузлів, 18 839 символів тексту, 60 КБ розмітки), Chromium, по 2000
     викликів у пачці — бо `performance.now()` округлює до 0.1мс і один виклик
     виміряти неможливо взагалі:
       · найважча РЕАЛЬНА обгортка (252 вузли, 8 064 символи) — 0.033мс;
       · весь `body` сторінки (692 вузли, 18 839 символів) — 0.080мс;
       · лист із текстом — 0.004мс;
       · синтетика вдесятеро важча за найважчу справжню
         (6 930 вузлів, 188 390 символів) — 0.75мс.
     Для масштабу: на ТІЙ САМІЙ перемальовці `paintInsp` кличе `report()`, і він
     коштує 6.2мс — у 78 разів більше за найгірший реальний `identity()`.

     Тому кеша тут НЕМА і не треба: він зрізав би 1.3% того, що перемальовка
     витрачає й так, а купував би це новою поверхнею інвалідації — при тому, що
     ознаки мусять зніматись ДО першого інлайн-запису (див. `tuneSet`), і
     кешований пакет саме цю несучу умову й розмив би. Число нижче за поріг
     помітності: 0.08мс із бюджету 33мс — 0.24%. */
  const key = api ? elementKey(api.identity()) : null;
  if (!page || !key) return null;
  const elems = tuneState.pages[page];
  if (!elems || !Object.prototype.hasOwnProperty.call(elems, key)) return null;
  /* КОПІЯ, а не сам обʼєкт моделі: доліплюємо `missing` — факт про ЦЕЙ
     документ (`tuneMissing`), якого в моделі немає й не мусить бути. Модель
     їде на диск; позначка «не лягло» — ні. Копіюємо лише ту правку, якої це
     стосується: решта лишається тим самим обʼєктом, і зайвих алокацій на
     кожну перемальовку (а вона на кожен поворот ручки) не зʼявляється. */
  const out = {};
  for (const [prop, e] of Object.entries(elems[key].edits)) {
    out[prop] = isMissing(key, prop) ? { ...e, missing: true } : e;
  }
  return out;
}

/**
 * Накрутити одну властивість запіненого елемента: жива зміна на макеті +
 * запис у модель. Один шлях на всі ручки — стрілку, пікер і скидання.
 *
 * ⚠️ ПОРЯДОК ПЕРШИЙ, і він несучий. `identity(prop)` питаємо ДО того, як
 * `applyTune` напише інлайн-стиль. Інлайн ВИГРАЄ каскад, тож після першого ж
 * запису той самий виклик віддав би `selector: '[style]'` — і пакет радив би
 * Клоду правити атрибут, який щойно створив сам тюнер, замість правила, що
 * виграло насправді. Пастка тиха: усе працює, а в пакет їде неправда.
 *
 * ⚠️ ПОРЯДОК ДРУГИЙ. `tuneState` присвоюємо ДО `applyTune`: успішний
 * `applyTune` сам будить батька (`_tuned` → `_emit` → `paintBar` →
 * `paintInsp`), тобто панель малюється ВСЕРЕДИНІ цього виклику — і зі старою
 * моделлю намалювала б рядок без позначки «накручено». Відмову відкочуємо, і
 * панель тоді не чіпаємо взагалі: у полі лишається те, що дизайнер набрав.
 */
function tuneSet(prop, value, snap = null, opts = {}) {
  const api = inspectorApi();
  const decl = inspDecls.get(prop);
  const page = tunePage();
  if (!api || !decl || !page) return false;
  const ident = api.identity(prop);        // ⛔ ДО першого інлайн-запису
  if (!ident) return false;
  const key = elementKey(ident);
  const next = setEdit(tuneState, page, ident, decl, value, { snap });
  /* `setEdit` САМА прибирає правку, коли значення вернулось до початкового
     (звірка через `normalizeValue`, тобто `#FFF` і `#ffffff` — одне й те
     саме). Тоді й на макеті нічого не мусить лишитись: інакше в розмітці
     висів би інлайн, якого в пакеті вже немає. */
  const elems = next.pages[page];
  const kept = !!elems && Object.prototype.hasOwnProperty.call(elems, key)
    && Object.prototype.hasOwnProperty.call(elems[key].edits, prop);
  const was = tuneState;
  /* ⛔ ПОРЯДОК ТРЕТІЙ, і він той самий, що й у присвоєння `tuneState` вище:
     вдалий `applyTune` малює панель УСЕРЕДИНІ свого виклику, тож позначку «не
     лягло» треба зняти ДО нього — інакше дизайнер крутить ручку, бачить зміну
     на макеті й поруч читає, що її там немає. Відмову відкочуємо цілком: не
     лягло — позначка правдива. */
  const wasMissing = forgetMissing(key, prop);
  tuneState = next;
  if (!(kept ? api.applyTune(prop, value) : api.clearTune(prop))) {
    tuneState = was;
    if (wasMissing) tuneMissing = [...tuneMissing, { selector: key, prop }];
    return false;
  }
  /* Запис — ПІСЛЯ вдалого накладання і тільки після нього: пакет не сміє
     обіцяти Клоду зміну, якої дизайнер на макеті не побачив (браузер ковтає
     непридатне значення тихо, і саме тому `applyTune` віддає прапорець). */
  if (opts.save !== false) saveTune();
  return true;
}

/**
 * Записати кілька властивостей одним жестом: `[[prop, value, snap?], …]`. Пара полів (↔) — дві правки, матриця — дві,
 * «+» обведення — три. Запис пакета — ОДИН у кінці (`saveTune` зливає й так, але зайвий POST на кожну властивість
 * жодного сенсу не має). `save:false` — для скрабу: пакет пишеться лише на відпусканні.
 */
function tuneWrite(list, opts = {}) {
  const api = inspectorApi();
  const page = tunePage();
  const was = tuneState;
  const wasMissing = tuneMissing;
  const key = api && page ? elementKey(api.identity()) : null;
  const done = [];
  for (const [prop, value, snap] of list) {
    if (tuneSet(prop, value, snap || null, { save: false })) { done.push(prop); continue; }
    /* Дія атомарна: збій однієї властивості відкочує вже накладені в ЦІЙ дії — на макеті й у моделі. Інакше «+»
       обведення лишав би стиль без ширини, а пакет — обіцянку, якої дизайнер не побачив. Відкат — той самий
       `applyTune`/`clearTune`, що й у одиночного запису: правка, якої до дії не було, знімається, а що була — вертається. */
    const prior = (key && was.pages[page] && was.pages[page][key] && was.pages[page][key].edits) || {};
    for (const p of done) {
      if (Object.prototype.hasOwnProperty.call(prior, p)) api.applyTune(p, prior[p].to);
      else api.clearTune(p);
    }
    tuneState = was;
    tuneMissing = wasMissing;
    paintInsp();
    return false;
  }
  if (done.length && opts.save !== false) saveTune();
  return done.length > 0;
}


/* ===== Канал тюнера на диск (Task 16) ===== */

/* Чи йде зараз запис, і чи назбиралось нове, поки він ішов. Разом вони і є
   вся механіка збереження. */
let tuneSaving = false;
let tunePendingSave = false;

/**
 * Записати пакет на диск. Власник просив «записується ОДРАЗУ», тож кнопки
 * експорту тут немає: пише кожна правка й кожна літера записки.
 *
 * ⚠️ ЧОМУ БЕЗ ТАЙМЕРА (ні дебаунса, ні «запис у простої»), хоч стрілка з
 * автоповтором народжує правку кожні ~33мс. Таймер — це вікно, у якому остання
 * правка існує ТІЛЬКИ в памʼяті вкладки; закрий її всередині вікна — і
 * зникає саме той поворот ручки, на якому дизайнер зупинився, тобто рівно та
 * тиха брехня, від якої ця фіча й лікується. Ціна відмови від нього мала:
 * файл — кілька кілобайт, сервер свій і локальний, запис атомарний
 * (`atomic_write_json`).
 *
 * ⚠️ ЩО РОБИТЬ ЗЛИТТЯ (`tunePendingSave`), і це не оптимізація, а
 * КОРЕКТНІСТЬ. Без нього два поспіль повороти ручки дають два паралельні
 * POST, і порядок їхнього прибуття на сервер не гарантований нічим — старіший
 * пакет має повне право лягти ПОВЕРХ новішого, і на диску лишиться значення,
 * якого на екрані вже немає. Тут у польоті завжди рівно один запис, а все, що
 * назбиралось під час нього, зливається в ОДИН наступний.
 *
 * ⚠️ І ЧОМУ НАСТУПНИЙ ЗАПИС НЕ ГУБИТЬ ОСТАННЄ: пакет збирається В МИТЬ
 * ВІДПРАВКИ (`packageJSON(tuneState)` нижче), а не в мить постановки в чергу.
 * Тобто відкладений запис несе стан на момент відправки — найсвіжіший, який
 * існує. «Остання правка виграє» тут виходить за побудовою, а не щасливо.
 *
 * Пакет — ПОВНИЙ (без фільтра сторінки): на диску лежить уся робота над
 * задачею, і кожен елемент несе свою `page`. Сторінка — межа видимості у
 * ПАНЕЛІ, а не межа того, що поїде Клоду.
 *
 * Помилку ковтаємо мовчки, і це свідомо: сервер свій, падіння тут означає, що
 * канвас уже не працює цілком (смуга помилки покаже це голосніше), а тост на
 * кожну натиснуту стрілку зробив би роботу неможливою.
 */
/**
 * Підняти пакет із диска в памʼять — один раз, на старті канваса.
 *
 * ⛔ Не зручність, а умова того, щоб канал не ЗАТИРАВ. Пише він повний пакет
 * (`saveTune`), тож без цього читання перший же поворот ручки після ⌘R лягав
 * би на диск пакетом з однієї правки — тобто мовчки зносив би роботу, яку
 * дизайнер уважав збереженою. Це рівно та тиха брехня, від якої фіча й
 * лікується, лише з іншого кінця.
 *
 * Мовчазний `catch`: старого пакета могло не бути ніколи, а починати сесію з
 * повідомлення про порожній файл — гірше за тишу. Сервер на побитому файлі й
 * сам віддає `package: null`, не помилку.
 */
async function loadTune() {
  try {
    const r = await api('/api/tuner');
    if (r && r.package) tuneState = fromPackage(r.package);
    tuneRev = r ? (r.rev ?? null) : null;
  } catch (e) { /* немає пакета — і не мусить бути */ }
}

/* Ревізія файла пакета, поверх якої пише ЦЯ вкладка (`_tuner_rev`, `serve.py`).
   `undefined` — ще не читали: тоді пишемо без неї, як до появи ревізій, бо
   відмова без жодного прочитаного стану не мала б із чим звіряти. */
let tuneRev;

/**
 * Прийняти те, що лежить на диску, замість того, що в памʼяті вкладки.
 *
 * ⛔ fb-22092026-c11bff: Клод застосував пакет і очистив його, а вкладка далі
 * показувала «готово — чекає на Клода» і першим же записом клала старий
 * пакет назад. Тепер чужа зміна перемагає: макет після Клода однаково інший
 * (правки лягли в код), тож рамку перезавантажуємо — інлайн-стилі старого
 * пакета з неї зникають разом зі станом, з якого їх накладали.
 */
function adoptTune(pkg, rev) {
  tuneState = pkg ? fromPackage(pkg) : emptyTune();
  tuneRev = rev ?? null;
  inspDecls = new Map();
  render();
}

async function saveTune() {
  if (tuneSaving) { tunePendingSave = true; return; }
  tuneSaving = true;
  try {
    const body = packageJSON(tuneState);
    if (tuneRev !== undefined) body.base_rev = tuneRev;
    const res = await fetch('/api/tuner', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (res.status === 409) {
      /* Файл змінив хтось інший (Клод забрав пакет, або правила сусідня
         вкладка). Затерти його ми не маємо права, а тихо проковтнути відмову —
         означало б показувати дизайнерові правку, якої на диску немає. Тому
         беремо диск і КАЖЕМО, що останній поворот ручки не збережено. */
      const cur = await res.json();
      tunePendingSave = false;
      adoptTune(cur.package, cur.rev);
      tell(t('tuneTakenElsewhere'));
      return;
    }
    if (res.ok) tuneRev = (await res.json()).rev ?? null;
  } catch (e) { /* див. докстрінг: гучність тут дорожча за тишу */ } finally {
    tuneSaving = false;
    if (tunePendingSave) { tunePendingSave = false; saveTune(); }
  }
}

/**
 * Звірити пакет із диском, коли дизайнер ПОВЕРТАЄТЬСЯ у вкладку.
 *
 * Типовий шлях Клода: дизайнер натиснув «Надіслати Клоду», пішов у термінал,
 * Клод застосував і очистив пакет, дизайнер вернувся. Без цього читання панель
 * до перезавантаження показувала б пакет, якого вже немає. Звіряємо ревізію, а
 * не вміст: однакова ревізія — нічого не сталось, і рамку не чіпаємо.
 * Відмова, що прийде на запис (`saveTune`, 409), лишається другою лінією для
 * випадку, коли вкладка й не втрачала фокусу.
 */
async function syncTuneFromDisk() {
  if (tuneSaving || tuneRev === undefined) return;
  const seen = tuneRev;
  try {
    const r = await api('/api/tuner');
    /* ⛔ Поки ця відповідь летіла, вкладка могла сама записати поворот ручки —
       і тоді відповідь описує диск ДО нашого запису. Прийняти її означало б
       відкотити власну правку, тому звіряємо з ревізією НА СТАРТІ запиту. */
    if (tuneSaving || tuneRev !== seen) return;
    const rev = r ? (r.rev ?? null) : null;
    if (rev !== seen) adoptTune(r.package, rev);
  } catch (e) { /* сервер лежить — смуга помилки скаже про це голосніше */ }
}
/**
 * Те саме для дерева сторінок: Клод чи `bin/pages.py` могли переписати
 * `pages.json`, поки вкладка була в тіні, — без цього панель показувала б старе
 * дерево, а перша ж дія дала б `stale`. Звіряємо `rev`, а не вміст: той самий
 * rev — нічого не сталось, панель не чіпаємо. Рішення «чи можна» — чиста
 * `shouldRefreshPanel` (ДО запиту і ПІСЛЯ: за час запиту могли почати жест чи
 * запис, а підміна дерева посеред дії її зламала б).
 */
let panelRefreshing = false;
async function refreshPanelFromDisk() {
  /* Екран «Задачі» відкритий: сцена схована, а `render()` у «Огляді» запустив би
     `ovc.enter()` на полотні нульового розміру й автозʼємку невидимого. Вихід з
     екрана робить повний `render()` і наздожене все сам. */
  if (homeOpen) return;
  const it = picked;
  const quiet = () => ({ busy: treeGate.busy, dragging: dragActive(),
    askOpen: askUp() });
  if (panelRefreshing || !shouldRefreshPanel({ it, current: picked, ...quiet() })) return;
  panelRefreshing = true;
  try {
    const r = await api(`/api/iteration-pages?it=${encodeURIComponent(it)}`);
    if (!shouldRefreshPanel({ it, current: picked, ...quiet(), rev: r?.rev ?? '', seenRev: panelRev })) return;
    const before = pickedPage;
    // loadPages зводить вибір, фокус і відкриту сторінку з новим деревом (одне місце)
    await loadPages();
    if (picked !== it) return;
    // «Огляд» малює картки з дерева — без повного render() нова картка не зʼявиться
    if (mode === 'canvas' || pickedPage !== before) render(); else renderPanel();
  } catch (e) { /* сервер лежить — смуга помилки скаже про це голосніше */ }
  finally { panelRefreshing = false; }
}
window.addEventListener('focus', () => { syncTuneFromDisk(); refreshPanelFromDisk(); });
/* Свіжість локальних піни (Б2.1): Claude міг дописати їх на диск, поки вікно не мало фокуса. */
window.addEventListener('focus', cmtRefreshLocal);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') { syncTuneFromDisk(); refreshPanelFromDisk(); }
});

/* ===== Автооновлення рамки (fb-01102026-309e3b) =====
   Опитуємо відбиток ВМІСТУ ітерації, поки вкладка видима й відкритий робочий
   вид. Рішення — `reloadStep` (тиша QUIET_MS, «в руках» → плашка). */
const STAMP_EVERY_MS = 2000;
let reloadState = null;

/* ===== Статус Клода (ідея 02.09.2026; острівець і бейдж — 12.10.2026) =====
   Сервер віддає статус лише поки серцебиття від мода pipeline-band свіже (TTL у
   `serve.claude_view`), тож тут ми нічого не «знімаємо» — просто питаємо. Острівець
   оновлюється НА МІСЦІ: жива область — постійний `#claude-hud`, і підпис стану
   переписуємо лише тоді, коли він справді змінився (вік — `aria-hidden`).
   ⛔ Опит іде і в ПРИХОВАНОМУ вікні: бейдж на іконці дивляться саме тоді, коли вікно
   канваса перекрите вікном Claude. Пропуск прихованих (як було до 1.54) заморожував
   би бейдж у старому стані — «працює» після того, як Клод зупинився. Запит легкий
   (удари — у памʼяті сервера; `tasks.json` читається, але він малий); у фоні Chrome
   сам рідшає таймери (до ~1 хв). */
const CLAUDE_EVERY_MS = 5000;
const claudeHud = document.getElementById('claude-hud');  // сегмент Claude в острівці (`#hud`)
/** Останній застосований вид бейджа (`badgeFor`): API не смикаємо кожні 5 с. */
let claudeBadge = null;
function paintClaude(force = false) {
  const p = islandParts(claudeView);
  if (!p) claudeHud.replaceChildren();
  else {
    if (!claudeHud.firstElementChild) claudeHud.innerHTML = ISLAND_SHELL;
    const el = claudeHud.firstElementChild;
    el.className = `claude-island claude-island--${p.state}`;
    const lbl = el.querySelector('.lbl-claude');
    if (lbl.textContent !== p.label) lbl.textContent = p.label;
    /* Без пробілу попереду: відступ уже дає `gap` острівця, інакше перед «·» дві щілини. */
    el.querySelector('.claude-age').textContent = p.age ? `· ${p.age}` : '';
  }
  const kind = badgeFor(claudeView);
  if (force || kind !== claudeBadge) { claudeBadge = kind; applyBadge(navigator, kind); }
}
async function pollClaude() {
  let r;
  try { r = await api('/api/claude-status'); } catch (e) { r = null; }
  const next = r && r.state ? r : null;
  if (JSON.stringify(next) === JSON.stringify(claudeView)) return;
  claudeView = next;
  paintClaude();
}
/* Бейдж належить ЗАСТОСУНКУ, а не вікну: закрили одне вікно канваса — воно зняло
   бейдж за всіх. Решта вікон чує це й ставлять свій стан знову. */
const badgeChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('deai-canvas-badge') : null;
badgeChannel?.addEventListener('message', () => paintClaude(true));
/* Стан Claude на вкладках: один запит на всі задачі, лише коли відкрита хоч одна вкладка. Той самий таймер, що й `pollClaude`. */
async function pollClaudeAll() {
  /* Крапки на вкладках приховане вікно не бачить; `visibilitychange` опитує одразу, коли воно знову видиме. */
  if (document.visibilityState !== 'visible') return;
  if (!tabs.length) { if (claudeAll) { claudeAll = null; paintTabs(); } return; }
  let r; try { r = await api('/api/claude-statuses'); } catch (e) { r = null; }
  const next = r && r.tasks && typeof r.tasks === 'object' ? r.tasks : null;
  if (JSON.stringify(next) === JSON.stringify(claudeAll)) return;
  claudeAll = next; paintTabs();
}
/* Нові командні на ІНШИХ вкладках (поправка 17): лише вкладки поточного простору, крім активної (її рахує острівець), лише
   коли вікно видиме; одразу при зміні складу вкладок (`saveTabs`) і на `focus`, далі раз на 90 с. Маркер «бачив» — той самий,
   що в острівця. Маркер-основу пишемо ЛИШЕ з відповіді `supported:true`: впала/відсутня команда не мусить лишити порожній
   маркер, після якого кожен коментар колеги став би «новим». */
const NEWS_EVERY_MS = 90000;
async function pollTabNews(force = false) {
  if (document.visibilityState !== 'visible') return;
  const now = Date.now();
  /* focus / visibilitychange / таймер — не частіше разу на 30 с; зміна складу вкладок чи активної задачі — `force`. */
  if (!force && now - newsLastAt < 30000) return;
  if (newsBusy) { newsAgain = newsAgain || (force ? 'force' : true); return; }
  newsLastAt = now;
  newsBusy = true;
  try {
    const sp = spaceNow()?.id ?? null;
    const next = {};
    for (const x of tabs) {
      if (x.id === currentTaskId || (x.space ?? null) !== sp) continue;
      let r = null;
      try { r = await api(`/api/comment-news?task=${encodeURIComponent(x.id)}`); } catch (e) { r = null; }
      /* `error` при supported:true — команда впала (квота/мережа): порожній список НЕ основа, інакше після одужання усе «нове». */
      if (!r || !r.supported || r.error || !Array.isArray(r.items)) continue;
      const key = seenKey(sp, x.id);
      let seen = loadSeen(key);
      if (!seen) { seen = baseline(r.items); saveSeen(key, seen); }
      const n = countNew(r.items, seen, myName());
      if (n && x.id !== currentTaskId) next[x.id] = n;
    }
    /* Простір перемкнули, поки ішов опит: чужі числа не малюємо (новий опит уже в черзі від paintTabs). */
    if (sp !== (spaceNow()?.id ?? null)) return;
    if (JSON.stringify(next) !== JSON.stringify(tabNews)) { tabNews = next; paintTabs(); }
  } finally {
    newsBusy = false;
    if (newsAgain) { const f = newsAgain === 'force'; newsAgain = false; pollTabNews(f); }
  }
}
setInterval(pollTabNews, NEWS_EVERY_MS);
/* Окремий слухач (не в наявних `focus`: їх приколюють регекс-охоронці). */
window.addEventListener('focus', () => { pollTabNews(); });
setInterval(pollClaude, CLAUDE_EVERY_MS);
setInterval(pollClaudeAll, CLAUDE_EVERY_MS);
/* Старт: спершу ЗНЯТИ бейдж, що міг лишитись від упалого вікна (`pagehide` тоді не
   прийшов), — інакше перший опит з «нічого» дорівнював би початковому `null`, і
   застарілий бейдж висів би, поки статус не зміниться. Потім — перший опит одразу. */
paintClaude(true);
pollClaude();
pollClaudeAll();
/* Оновлення інструмента: перший знімок одразу, ще один — коли сервер вже встиг першу перевірку тегів (вона стартує за кілька секунд
   після запуску; без цього пігулка зʼявилась би лише за півгодини), далі раз на півгодини. Сам remote питає сервер, не вкладка. */
pollUpdate();
setTimeout(pollUpdate, 20000);
setInterval(pollUpdate, UPDATE_POLL_MS);
/* Повернулись до вікна — правду одразу, не через 5 с; бейдж — ще раз, якщо система
   його скинула. */
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') { paintClaude(true); pollClaude(); pollClaudeAll(); pollTabNews(); }
});
/* Вікно закрили — опитувати більше нікому, і бейдж без нагляду брехав би. Решту вікон
   канваса про це сповіщаємо: бейдж спільний, вони поставлять його знову. */
addEventListener('pagehide', () => {
  claudeBadge = 'none';
  applyBadge(navigator, 'none');
  badgeChannel?.postMessage('gone');
});
/* Сторінку повернули з bfcache — бейдж знято на pagehide, а відповідь сервера та
   сама, тож `pollClaude` його б не повернув. Опитуємо й одразу: `claudeView` у
   відновленої сторінки може бути годинної давнини. */
addEventListener('pageshow', (e) => { if (e.persisted) { paintClaude(true); pollClaude(); pollClaudeAll(); } });
/** Чи є в рамці щось, що перезавантаження знищило б: відкритий інспектор
 *  (запінений елемент) або набір коментаря. Не можемо подивитись — вважаємо,
 *  що є: зайва плашка дешевша за знищений текст. Стан тюнера живе тут, у
 *  батьківському вікні, і переживає перезавантаження сам (`reapplyTune`). */
function frameHeld() {
  try {
    if (inspectorApi()?.on) return true;
    const host = frame.contentDocument?.querySelector('[data-comment-layer]');
    return !!host?.shadowRoot?.querySelector('.compose');
  } catch (e) { return true; }
}
/** Точки «Змінено щойно» — НА МІСЦІ, без `renderPanel()`. Повна перемальовка
 *  кожні 2 с, щойно Клод правив сторінку, рвала б жест у панелі й скидала фокус
 *  рядка (так і впав живий тест panel-click під навантаженням). Наступний
 *  справжній `renderPanel()` намалює ті самі точки з `recentPages` сам. */
function paintRecentDots() {
  for (const row of document.querySelectorAll('#pages-panel [data-page]')) {
    const want = recentPages.has(row.dataset.page);
    const dot = row.querySelector('.row-recent-dot');
    if (want && !dot) {
      const s = document.createElement('span');
      s.className = 'row-recent-dot';
      s.title = t('pageRecent');
      row.querySelector('.row-name')?.after(s);
    } else if (!want && dot) {
      dot.remove();
    }
  }
}

/** Перезавантажити ЛИШЕ документ рамки. Не `render()`: той перебудовує смугу й
 *  панель і присвоює `frame.src`, а потрібен тільки новий макет.
 *  Прокрутку НЕ відновлюємо руками: `location.reload()` зберігає її сам — живий
 *  тест B лишався зеленим і без власного `scrollTo` (мутація 02.10.2026), тож
 *  такий рядок охороняв би лише себе. Фолбек `src` прокрутку губить — він на
 *  випадок, коли до документа рамки не дістатись. */
function reloadFrame() {
  try { frame.contentWindow.location.reload(); } catch (e) { frame.src = frame.src; }
}
frame.addEventListener('load', () => dropNotice('frame-changed'));
setInterval(async () => {
  if (!shouldPollStamp({ mode, picked, visible: document.visibilityState === 'visible', home: homeOpen })) return;
  const it = picked, pg = pickedPage || '';
  let r;
  try { r = await api(`/api/it-stamp?it=${encodeURIComponent(it)}`); } catch (e) { return; }
  if (picked !== it || (pickedPage || '') !== pg || mode === 'canvas') return;
  /* «Де саме міняє»: сторінки, чиї файли змінились за 2 хв (сервер рахує з диска). */
  const rec = new Set(Array.isArray(r?.recent) ? r.recent : []);
  if (rec.size !== recentPages.size || [...rec].some((id) => !recentPages.has(id))) {
    recentPages = rec;
    paintRecentDots();
  }
  const step = reloadStep(reloadState, { it, page: pg, stamp: r?.stamp, now: Date.now(), held: frameHeld() });
  reloadState = step.state;
  if (step.action === 'reload') reloadFrame();
  else if (step.action === 'notice') {
    notice('frame-changed', t('frameChanged'),
      [{ act: 'reload', label: t('frameReload'), run: () => { dropNotice('frame-changed'); reloadFrame(); } }]);
  }
}, STAMP_EVERY_MS);

/**
 * Скинути ОДНУ правку зі списку вкладки «Тюнер».
 *
 * ⚠️ Чому це не `tuneSet(prop, edit.from)`, як робить хрестик у рядку звіту:
 * той шлях крутить ЗАПІНЕНИЙ елемент, а на вкладці тюнера не запінено нічого —
 * дизайнер дивиться в список, а не на макет. Тому елемент адресується ключем
 * (`selector` пакета), а інлайн знімається `clearBySelector` — тим самим, чим
 * його зніме перезавантаження рамки.
 *
 * Модель ПЕРША, макет другий, і порядок тут протилежний до `tuneSet` навмисно:
 * там `applyTune` може відмовити (браузер не прийняв значення), і відкочувати
 * доводиться модель. ЗНЯТТЯ не відмовляє: властивості, якої немає, немає і
 * після `removeProperty`. Єдине, чого `clearBySelector` не може, — знайти
 * елемент, якого вже немає в документі; і тоді правку все одно треба прибрати
 * зі списку, інакше вона висітиме там вічно.
 */
function tuneDrop(selector, prop) {
  const page = tunePage();
  if (!page) return;
  const next = clearEdit(tuneState, page, selector, prop);
  if (next === tuneState) return;         // такої правки немає — нічого не сталось
  tuneState = next;
  /* Правки немає — немає й факту про те, що вона не лягла: інакше позначка
     пережила б власний рядок і чекала б на правку з тим самим імʼям. */
  forgetMissing(selector, prop);
  inspectorApi()?.clearBySelector(selector, prop);
  saveTune();
  paintInsp();
}

/** Скинути ВСЕ накручене на цій сторінці. Записка лишається: вона про задачу
 *  цілком, а не про правки, і губити її разом із ними було б несподіванкою
 *  (про це прямо каже й питання підтвердження). */
async function tuneDropAll() {
  const page = tunePage();
  const elems = page ? tuneState.pages[page] : null;
  if (!elems) return;
  /* Перелік знімаємо ДО запитання: поки відкрите вікно підтвердження, дизайнер
     може крутити далі (воно не модальне для макета), і скидати треба рівно те,
     що було показано в списку, який він бачив. */
  const todo = [];
  for (const el of Object.values(elems)) {
    for (const prop of Object.keys(el.edits || {})) todo.push([el.selector, prop]);
  }
  if (!todo.length) return;
  /* ⛔ Питаємо. Дія незворотна (моделі «відмінити» в тюнері немає) і зносить
     роботу цілої сесії — єдине місце фічі, де ціна помилкового кліка не
     дорівнює одному повороту ручки назад. */
  if (!await askYesNo(t('inspTunerResetAllAsk', todo.length), { danger: true })) return;
  for (const [selector, prop] of todo) tuneDrop(selector, prop);
}

/**
 * Записка Клоду. Панель НЕ перемальовуємо на кожну літеру: розмітка
 * переписується цілком (`paintInsp`), тобто перемальовка на кожне натискання
 * знищувала б поле, у якому дизайнер саме пише.
 *
 * ⚠️ Виняток рівно один — коли записка ЗНЯЛА «готово» (T-39). Тоді на екрані
 * висить позначка «готово — чекає на Клода», якої модель уже не підтверджує,
 * а це саме та тиха брехня, проти якої `status` і заводили. Перемальовка тут
 * безпечна: вона стається один раз на перехід `ready → draft`, а не на
 * літеру, і `paintInsp` вертає в записку і фокус, і каретку.
 */
function tuneNote(text) {
  const was = tuneState.status;
  tuneState = setNote(tuneState, text);
  saveTune();
  if (tuneState.status !== was) paintInsp();
}

/**
 * «Надіслати Клоду»: позначити пакет готовим.
 *
 * ⛔ НЕ НАДСИЛАЄ і не зберігає — зберігається все й так, на кожну правку
 * (`saveTune`). Єдине, що тут стається: `status` стає `ready`, тобто читач
 * пакета отримує відповідь на питання «дизайнер іще крутить чи вже
 * закінчив». `saveTune()` нижче потрібен саме тому, що сам `status` — теж
 * частина пакета, і без запису він лишився б у памʼяті вкладки.
 *
 * Порожній пакет позначати нічим: кнопки в цьому стані й немає (підвал не
 * малюється), але дія лишається чесною й без UI — вона просто нічого не
 * робить, замість оголошувати готовою порожнечу.
 */
function tuneReady() {
  const page = tunePage();
  if (!page) return;
  const pkg = packageJSON(tuneState, page);
  if (!pkg.editCount && !editCount(tuneState) && !tuneState.note) return;
  const next = markReady(tuneState);
  if (next === tuneState) return;         // уже готовий — перемальовувати нічого
  tuneState = next;
  saveTune();
  paintInsp();
}

/**
 * Накласти накручене заново — після кожного завантаження рамки (Task 17).
 *
 * ⛔ ЦЕ ЗАКРИВАЄ ЄДИНУ БРЕХНЮ, ЯКОЮ ФІЧА МОЖЕ ЗІПСУВАТИСЬ. `applyMode`
 * переприсвоює `frame.src` на кожному повному рендері (`app.js:129`), і навіть
 * той самий рядок перезавантажує документ: усі інлайн-стилі тюнера зникають
 * разом із ним. Модель при цьому живе в батьківському вікні й переживає все —
 * тобто БЕЗ цього виклику панель показувала б правку, якої на макеті вже
 * немає, а пакет обіцяв би Клоду зміну, якої дизайнер більше не бачить. Саме
 * ця розбіжність і була відомою відкритою межею Task 13/14.
 *
 * Накладаємо ТІЛЬКИ поточну сторінку: правки інших сторінок до цього документа
 * стосунку не мають (сторінка — межа видимості, `tunePage`), і застосовувати
 * їх тут означало б фарбувати чужий екран за чужим селектором.
 *
 * Селектор, який більше не резолвиться, `applyBySelector` пропускає мовчки, і
 * правку ми при цьому НЕ прибираємо: вона описує те, що дизайнер справді
 * зробив, і мусить доїхати Клоду разом із рештою. Мовчання тут — не ковтання
 * помилки: сторінку могли переписати між двома відкриттями канваса, і це
 * звичайний хід роботи, а не збій. АЛЕ мовчить тут лише КОД: те, що не лягло,
 * доїжджає в `tuneMissing` і панель про це каже (`tuneFootHTML`).
 *
 * ⛔ ОДНІЄЇ СПРОБИ НА `load` МАЛО, і це вада, зловлена живцем 18.09.2026 на
 * справжньому макеті (`bf360`, it6/main, `h1.hero__title`). Ключ елемента
 * несе до двох класів (`label`, `inspector-dom.js`), а класи макетові дописує
 * ЙОГО ВЛАСНИЙ скрипт — уже після `load` (`split-ready`, `is-split-in`). У мить
 * `load` селектор `…h1.hero__title.split-ready` не збігається ні з чим,
 * `applyBySelector` мовчки пропускає — і правка, піднята з диска, не лягає, доки
 * канвас відкритий. Правки ЦІЄЇ сесії при цьому живі (їх кладе `applyTune` на
 * запінений елемент), тож вада видно лише на ХОЛОДНОМУ старті: панель показує
 * зміну, якої на макеті немає. Рівно та брехня, проти якої фіча й заведена.
 *
 * ЧОМУ ОБМЕЖЕНІ ПОВТОРИ, А НЕ `MutationObserver`. Спостерігач за всім
 * документом макета коштував би стільки, скільки макет рухається (анімації,
 * лінива підвантажка, каретки), і жив би весь час, поки відкрита сторінка, —
 * заради факту, який треба дізнатись ОДИН раз, на початку. Ще й гасити його
 * довелось би руками на кожному перезавантаженні рамки, тобто зʼявилась би
 * друга річ, яку легко забути. Тут — фіксована, названа стеля: макет має
 * `REAPPLY_BUDGET_MS`, щоб добудуватись, далі ми припиняємо й КАЖЕМО про те,
 * що не лягло. Повторюємо ЛИШЕ те, що не лягло: те, що вже стоїть, чіпати
 * вдруге нема чого.
 */

/* Крок між спробами й СТЕЛЯ загалом. Стеля названа свідомо: «повторюємо, поки
   не вийде» — це не бюджет, а вічний цикл, який ховає мертвий селектор замість
   того, щоб про нього сказати.

   ⚠️ 9 секунд ЗМІРЯНІ, а не вибрані на око — і перша спроба (1с) виявилась
   короткою рівно на тому макеті, заради якого все й робиться. `bf360`, it6/main,
   Chromium: клас `split-ready` зʼявляється через 3.2с після завантаження рамки,
   бо `js/split-text.js` чекає спершу `document.fonts.ready`, потім поки піде
   лоадер (опитує його стан кожні 100мс), і лише тоді +260мс паузи. Власна
   страховка того ж скрипта ставить стелю на 6с — тобто найпізніший законний
   момент появи класу ≈6.3с, і бюджет мусить бути ЗА ним, інакше ми знову
   обіцяємо те, чого не зробили.

   Ціна повторів нульова за побудовою: кожна спроба — це один `querySelector`
   на КОЖНУ ще не накладену правку (їх одиниці), і черга гасне тієї ж миті, як
   усе лягло. Платить лише той випадок, у якому правка не ляже ніколи, — а він
   і закінчується чесним «не лягло» в панелі. */
const REAPPLY_STEP_MS = 150;
const REAPPLY_BUDGET_MS = 9000;
const REAPPLY_TRIES = Math.round(REAPPLY_BUDGET_MS / REAPPLY_STEP_MS);

/* Хвіст повторів попереднього документа. Гаситься на кожному `load`: інакше
   стара черга добивала б у рамку, у якій уже інша сторінка. */
let reapplyTimer = 0;

/** Один прохід накладання. `only` — список пар, які ще не лягли (null на
 *  першому проході). Вертає ті, що не лягли ЦЬОГО разу. */
function reapplyPass(api, elems, only) {
  const missed = [];
  for (const el of Object.values(elems)) {
    for (const e of Object.values(el.edits || {})) {
      if (only && !only.some((m) => m.selector === el.selector && m.prop === e.prop)) continue;
      if (!api.applyBySelector(el.selector, e.prop, e.to)) {
        missed.push({ selector: el.selector, prop: e.prop });
      }
    }
  }
  return missed;
}

function reapplyTune(api) {
  /* Нова рамка — нова правда про те, що на ній лежить: і чергу, і факт
     починаємо з чистого аркуша. */
  if (reapplyTimer) { clearTimeout(reapplyTimer); reapplyTimer = 0; }
  tuneMissing = [];
  const page = tunePage();
  if (!api || !page || !tuneState.pages[page]) return;

  const step = (tryNo, only) => {
    reapplyTimer = 0;
    /* Документ міг змінитись, поки ми чекали: у рамці вже інший `CanvasInspector`,
       а наш — від сторінки, якої на екрані немає. Мовчки виходимо: свій `load`
       новий документ уже отримав і власну чергу завів сам. */
    if (inspectorApi() !== api) return;
    /* Модель перечитуємо на КОЖНІЙ спробі, а не знімаємо знімок на вході:
       поки черга чекає, дизайнер міг скинути ту саму правку хрестиком — і
       відкладена спроба намалювала б на макеті те, чого в пакеті вже немає.
       Це та сама брехня, лише навиворіт. */
    const elems = tunePage() === page ? tuneState.pages[page] : null;
    if (!elems) return;
    const missed = reapplyPass(api, elems, only);
    const changed = missed.length !== tuneMissing.length;
    tuneMissing = missed;
    if (missed.length && tryNo < REAPPLY_TRIES) {
      reapplyTimer = setTimeout(() => step(tryNo + 1, missed), REAPPLY_STEP_MS);
    }
    /* Перший прохід панель не чіпає: його кличе обробник `load`, за яким
       одразу йде `paintBar()` — і той малює вже з новим `tuneMissing`. Другий
       і далі приходять поза будь-якою перемальовкою, тож мусять розбудити її
       самі, інакше позначка «не лягло» лишиться висіти на правці, яка щойно
       лягла. */
    if (tryNo && changed) paintInsp();
  };
  step(0, null);
}

/** Без хвоста з плаваючої точки: `0.1 + 0.2` не сміє поїхати в макет як
 *  `0.30000000000000004` — ні на екран, ні в пакет для Клода. */
const tuneRound = (n) => String(Math.round(n * 1000) / 1000);

/** Застосувати поле панелі (Enter / change). Порожнє, недобране й незмінене — не значення; «Різні» порожнім не перетираємо. */
function inspCommit(el) {
  const props = String(el.dataset.props || el.dataset.prop || '').split(' ').filter(Boolean);
  if (!props.length) return;
  if (el.dataset.act === 'insptunecolor') {
    let h = el.value.trim().replace(/^#/, '');
    if (/^[0-9a-f]{3}$/i.test(h)) h = h.replace(/./g, '$&$&');
    if (!/^[0-9a-f]{6}$/i.test(h) || h.toUpperCase() === el.defaultValue.toUpperCase()) return;
    tuneWrite(props.map((p) => [p, `#${h.toUpperCase()}`]));
    return;
  }
  if (el.tagName === 'SELECT') { tuneWrite(props.map((p) => [p, el.value])); return; }
  const raw = el.value.trim().replace(',', '.');
  const n = Number(raw);
  if (raw === '' || !Number.isFinite(n) || raw === el.defaultValue.trim()) return;
  const min = el.dataset.min === undefined ? null : Number(el.dataset.min);
  const delta = Number(el.dataset.delta || 0);
  /* W/H показують РЕНДЕРЕНИЙ розмір; у CSS іде «введене − delta» (рамка/відступи content-box). ↑/↓ і скраб теж
     сходяться сюди й у `inspScrubApply`. Мінімум клампимо ПІСЛЯ віднімання: 10 при відступах 48 дає 0px, а не -38px,
     яке браузер мовчки відкине. */
  const css = min === null ? n - delta : Math.max(min, n - delta);
  tuneWrite(props.map((p) => [p, tuneRound(css) + (el.dataset.unit || '')]));
}

/** ↑/↓ у полі: крок поля (`data-step`) × множник (Shift = ×10). Порожнє поле (`normal`, «Різні») крокує від `data-base` або 0. */
function inspStep(el, mult) {
  const step = Number(el.dataset.step) || 1;
  const cur = parseFloat(String(el.value).replace(',', '.'));
  const base = Number.isFinite(cur) ? cur : (Number(el.dataset.base) || 0);
  const min = el.dataset.min === undefined ? null : Number(el.dataset.min);
  let v = Math.round((base + mult * step) * 100) / 100;
  if (min !== null) v = Math.max(min, v);
  el.value = String(v);
  inspCommit(el);
}

/* `syncInspectorBtn()` більше не існує: старий бар мав фіксований `#insp-toggle`
   і патчив на ньому клас `.on` руками. Нова смуга малює кнопку інспектора (і її
   дублікат у «⋯», коли ширина ховає основну) із моделі при кожному
   `paintBar()` — підсвітити кнопку «за реальним станом оверлея» тепер значить
   просто перемалювати смугу, `barState()` сам читає `inspectorApi()?.on`. */

// Кожне завантаження макета — новий документ, отже новий екземпляр інспектора:
// ховаємо його власну кнопку (керуємо зі смуги) і підписуємось на зміни, щоб
// клавіша `I` всередині макета теж підсвічувала кнопку. Слухач вішається один
// раз на модуль, а не в render(), інакше на кожну перемальовку смуги
// накопичувались би дублікати.
frame.addEventListener('load', () => {
  const api = inspectorApi();
  if (api) {
    api.setChrome(false);
    /* Підписи власного хрому оверлея — ЗГОРИ: він живе в документі макета,
       тобто свій імпорт `i18n.js` дав йому ОКРЕМИЙ екземпляр модуля з власним
       `lang` (докстрінг `setLabels`). Ключі — ключі СЛОВНИКА, ті самі, що в
       `data-lbl` розмітки оверлея.

       Лишився один підпис: чип режимів прибрано (Task 8), перемикач живе в
       правій панелі. Сам оверлей з Task 8 читає мову зі сховища (`dc-lang`)
       і збирає дефолти через `t()`, тобто цей виклик уже не рятує від
       кириличної кнопки в англійському інтерфейсі, а лишається ОВЕРРАЙДОМ:
       правда про мову в канвасі — тут, у оболонки, а не в сховищі.
       Штовхаємо на завантаження макета: кожне завантаження — новий документ,
       тобто новий екземпляр оверлея. */
    api.setLabels({ inspector: t('inspector') });
    /* Esc поступається відкритому питанню/поповеру/формі оболонки (`askUp()`, палітра, модальні): драбина інспектора
       — найнижча сходинка Esc. */
    api.yieldEsc = () => shellModalOpen();
    /* Накручене — НАЗАД на макет (Task 17). Тут і тільки тут: документ щойно
       народився, і це перша мить, коли є на що накладати. До `api.onChange`
       нижче — щоб панель, яку розбудить найближчий сигнал, малювалась уже по
       макету з накладеними правками, а не по голому. */
    reapplyTune(api);
    /* `paintBar` — і цього досить на ВСІ зміни стану оверлея, включно зі
       зміною піна: він сам кличе `paintInsp()` останнім рядком (його
       докстрінг). Другий, явний `paintInsp()` поруч виглядав би надійніше, а
       коштував би на КОЖНУ подію другого `report()` (це `getComputedStyle` по
       пʼятьох групах) і другого перезапису `innerHTML` панелі — разом із
       виділенням тексту, яке дизайнер у ній щойно зробив; від цього ж
       береже й порівняння сигнатур у `_emit`. Що виклик у `paintBar` не
       зникне непоміченим, стереже перевірка A в `tests/live/shell-inspect`. */
    api.onChange = paintBar;
  }
  paintBar();
});

/**
 * Права панель інспектора (Task 5 Плану B). Стан рахує РІВНО те, що написано
 * в докстрінгу `inspectHTML` (`shell-inspect.js`): `shellMode` — той самий
 * термін, що вже несе `barState().mode`, і `on`/`mode` — напряму з
 * `inspectorApi()`, БЕЗ власної копії — другого джерела правди тут і не
 * мало б зʼявитись (задача прямо про це попереджає).
 *
 * Перемальовка БЕЗУМОВНА (як `paintBar()`/`renderPanel()`, а не з охороною
 * «нічого не змінилось»): охорона тут виглядала б природно, але коштувала б
 * реального бага — перемикання мови (`setLang`) не міняє ЖОДНОГО з полів
 * стану, і кешована охорона тут лишила б панель зі старим текстом після зміни
 * мови, поки щось інше не зрушить `on`/`mode`. `paintBar()`/`renderPanel()`
 * цього репозиторію теж ніколи не кешують — той самий принцип. Від зайвих
 * викликів береже не ця функція, а `_emit` оверлея: він порівнює сигнатуру
 * `on|mode|_pinSeq|_measSig` (його власний докстрінг — джерело правди про неї)
 * і на рух курсора не сигналить узагалі.
 */
function paintInsp() {
  /* Під час скрабу панель не перемальовується: оновлюється лише значення в самому полі (слухачі нижче). */
  const api = inspectorApi();
  /* Скраб, якому не прийшов pointerup (Esc вимкнув інспектор, вікно втратило фокус), не сміє заморозити панель до
     перезавантаження: коли інспектор вимкнено чи панелі вже немає — жест кинуто, а те, що встигли накрутити, мусить
     лягти в пакет одним записом. */
  if (inspScrub && (!(api && api.on) || inspEl.hidden || !inspEl.isConnected)) inspScrubEnd();
  if (inspScrub) return;
  /* Звіт коштує `getComputedStyle` по пʼятьох групах на кожну перемальовку — тобто на кожен поворот ручки, — тож
     питаємо його лише при увімкненому інспекторі. */
  const rep = api && api.on ? api.report() : null;
  /* Рядки звіту — у мапу по властивості, для `tuneSet`. Знімаємо саме ТУТ, бо
     тут звіт уже порахований і ще не зіпсований накрученим: другий `report()`
     у мить кручення побачив би інлайн, який щойно поклав сам тюнер. */
  inspDecls = new Map();
  if (rep) {
    for (const items of Object.values(rep.groups)) {
      for (const d of items) inspDecls.set(d.prop, d);
    }
    /* `border-style` та інші властивості, яких немає в групах, але які пише «+» біля обведення. */
    for (const d of (rep.facts && rep.facts.extra) || []) inspDecls.set(d.prop, d);
    /* Яка ДС стоїть за цими вироками — у стан пакета, а не в кожну правку:
       це факт про ЗАДАЧУ. Без нього читач пакета не відрізнить «жодного
       порушення» від «ДС для цього напрямку немає, тому й не перевіряли».
       `setDs` віддає ТОЙ САМИЙ обʼєкт, коли нічого не змінилось, тож
       перезапису на кожну перемальовку не буває. */
    tuneState = setDs(tuneState, rep.dsInfo);
  }
  /* Пакет ЦІЄЇ сторінки — те саме, що поїде Клоду, лише звужене до сторінки,
     на яку дизайнер зараз дивиться. Рахує його чиста модель (`packageJSON`),
     панель лише малює — той самий принцип, що зі звітом і лінійкою.
     `tuneOther` — решта пакета, яка на цю сторінку не потрапила: без цього
     числа підвал мовчки казав би «це все», а сторінка — лише МЕЖА ВИДИМОСТІ
     правок, а не межа пакета.
     ⚠️ Рахуємо його ЗАВЖДИ, а не лише під однією вкладкою, як було до T-39:
     підвал живе під «Стилями», тобто рівно там, де крутять ручки, і кожен
     поворот ручки мусить одразу оновити список змін під ним. Ціна виміряна
     на порядок величин: `packageJSON` — це прохід по правках у памʼяті
     (десятки), а `report()` поруч — `getComputedStyle` по пʼятьох групах
     (6.2мс на важкому лендингу). */
  const tunePkg = packageJSON(tuneState, tunePage());
  const pinKey = rep ? rep.crumbs.join('>') : '';
  if (pinKey !== inspPinKey) { inspPinKey = pinKey; inspOffAt = -1; }
  const st = {
    shellMode: mode === 'canvas' ? 'overview' : 'layout',
    on: !!(api && api.on),
    tune: tunePkg,
    tuneOther: editCount(tuneState) - tunePkg.editCount,
    /* Що з пакета НЕ лягло на цей документ (`tuneMissing`). Окремим полем, а
       не всередині пакета: пакет — намір дизайнера й те, що їде на диск, а це
       факт про рамку, яка зараз на екрані. Без нього підвал малює правку, якої
       на макеті немає, рівно так само впевнено, як і всі інші. */
    tuneMissing,
    /* Модель панелі: звіт рахує САМ оверлей (`report()`) усередині iframe — єдиний, хто бачить живий DOM макета, —
       а чистий збирач (`insp-model.js`) робить із нього поля. `edits` доліплює БАТЬКО, а не оверлей: модель тюнера
       живе тут (рамка перезавантажується, вона — ні), і оверлей про неї не знає нічого. */
    model: rep ? buildModel(rep, { edits: tuneEdits(), sides: inspSides }) : null,
  };
  const html = inspectHTML(st);
  /* Прокрутку тіла панелі знімаємо ДО перезапису розмітки й вертаємо після.
     Не косметика: пінують КЛІКОМ, тобто в мить піна `:hover` іще активний і
     бейджі токенів на кнопках/посиланнях/картках виходять порожні; оверлей
     перечитує звіт правдиво, щойно курсор зійде (`_repaintPinned`), — і це
     ДРУГА подія на той самий пін. Без збереження перше, що бачить дизайнер
     після піна, — стрибок панелі на початок, посеред читання. Оверлей робить
     рівно це для СВОГО вікна (там же, `_repaintPinned`: читає `scrollTop` до,
     вертає після) — беремо той самий прийом, а не вигадуємо другий. */
  const top = inspEl.querySelector('.insp-body')?.scrollTop || 0;
  /* ФОКУС вертаємо разом із прокруткою, і з тієї ж причини: перезапис
     `innerHTML` знищує саме те поле, у якому дизайнер зараз крутить, а панель
     перемальовується на КОЖЕН поворот ручки (`_tuned` в оверлеї). Без цього
     друга стрілка поспіль уже не доїхала б нікуди — а стрілки тут основний
     спосіб роботи. Тримаємо пару «дія + властивість», а не сам вузол: до
     перемальовки той вузол не доживає, і `data-prop` є і в крутилки, і в
     кнопки скидання поруч.
     Поля — текстові, тож каретку теж відновлюємо (`selectionStart`): без цього курсор стрибав би в кінець
     посеред набору. */
  const act = document.activeElement;
  const mine = act && act !== document.body && inspEl.contains(act) && act.dataset;
  /* Записка Клоду (Task 15) — другий контрол, який мусить пережити
     перемальовку, і він відновлюється ІНАКШЕ. Крутилку адресує пара
     «дія + властивість»; у записки властивості немає й бути не може (вона про
     задачу цілком), зате є КАРЕТКА: у `<textarea>` `selectionStart` не кидає,
     і без неї курсор стрибав би в кінець тексту з середини речення. Сама
     перемальовка посеред набору — подія рідкісна (записка панель не малює), але
     від сусіднього сигналу оверлея вона стається, а текст тоді псується тихо. */
  const keep = mine && act.dataset.act === 'insptunenote'
    ? { act: 'insptunenote', prop: null, sel: [act.selectionStart, act.selectionEnd] }
    : (mine && act.dataset.act && act.dataset.prop
      ? { act: act.dataset.act, prop: act.dataset.prop,
        sel: act.tagName === 'INPUT' && act.type === 'text' ? [act.selectionStart, act.selectionEnd] : null } : null);
  inspEl.hidden = !html;
  document.body.classList.toggle('with-insp', !!html);
  inspEl.innerHTML = html;
  const body = inspEl.querySelector('.insp-body');
  if (body && top) body.scrollTop = top;
  if (keep) {
    const q = keep.prop === null
      ? `[data-act="${keep.act}"]`
      : `[data-act="${keep.act}"][data-prop="${CSS.escape(keep.prop)}"]`;
    const el = inspEl.querySelector(q);
    el?.focus();
    if (el && keep.sel) el.setSelectionRange(keep.sel[0], keep.sel[1]);
  }
}

/* Делегація панелі — ОКРЕМИЙ слухач (контейнер `#insp-panel` живе поза
   `#bar`, куди дивиться `bar.addEventListener` вище), але кличе ТУ САМУ
   мапу `BAR_ACTIONS`: кнопка закриття тут (`data-act="inspector"`) — той
   самий рядок коду, що й кнопка відкриття в смузі, не друга реалізація
   «увімкнено/вимкнено» поруч із першою. */
inspEl.addEventListener('click', (ev) => {
  const el = ev.target.closest('[data-act]');
  if (!el || el.disabled) return;
  /* Поля вводу мають СВОЇ події (`input` у крутилки й записки, `change` у
     пікера), а клік по них — це лише постановка каретки чи відкриття вибору
     кольору. Пропускаємо його тут: інакше кожен клік у поле перемальовував би
     панель разом із самим полем — під курсором, який щойно в нього цілився.
     `TEXTAREA` поруч із `INPUT` не про майбутнє: записка Клоду (Task 15) — це
     `<textarea>`, і без цього рядка клік у неї йшов би в `BAR_ACTIONS` і
     переписував би модель тим самим текстом на кожну постановку каретки. */
  if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') return;
  BAR_ACTIONS[el.dataset.act]?.(el.dataset.val, el, ev);
});

/* Записка Клоду — на КОЖНУ літеру (власник просив «записується одразу»). Поля властивостей на `input` НЕ пишуть:
   значення застосовує Enter або вихід із поля (`change`). */
inspEl.addEventListener('input', (ev) => {
  const note = ev.target.closest?.('[data-act="insptunenote"]');
  if (note) BAR_ACTIONS.insptunenote(note.value, note, ev);
});
inspEl.addEventListener('change', (ev) => {
  const el = ev.target.closest?.('[data-act="insptune"],[data-act="insptunecolor"]');
  if (el) inspCommit(el);
});
/* Enter застосовує, Esc скасовує введене й знімає фокус, ↑/↓ — ±1, Shift — ±10 (крок поля — `data-step`). */
inspEl.addEventListener('keydown', (ev) => {
  const el = ev.target.closest?.('[data-act="insptune"],[data-act="insptunecolor"]');
  if (!el || el.tagName !== 'INPUT') return;
  if (ev.key === 'Enter') { ev.preventDefault(); inspCommit(el); return; }
  if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); el.value = el.defaultValue; el.blur(); return; }
  if (el.dataset.act !== 'insptune') return;
  const dir = ev.key === 'ArrowUp' ? 1 : (ev.key === 'ArrowDown' ? -1 : 0);
  if (!dir) return;
  ev.preventDefault();
  inspStep(el, dir * (ev.shiftKey ? 10 : 1));
});

/* Скраб: тягнути підпис поля вліво-вправо. 3 px руху — один крок, Shift — десять. Правка застосовується не частіше
   разу на кадр (rAF), а пакет пишеться ОДИН раз — на відпусканні. Поки йде жест, панель не перемальовується
   (`paintInsp` виходить рано): оновлюється лише значення в самому полі. */
function inspScrubApply(s) {
  if (s.next === null || s.applied === s.next) return;
  s.applied = s.next;
  const css = s.min === null ? s.next - s.delta : Math.max(s.min, s.next - s.delta);   // кламп ПІСЛЯ delta
  tuneWrite(s.props.map((p) => [p, tuneRound(css) + s.unit]), { save: false });
}
inspEl.addEventListener('pointerdown', (ev) => {
  const lab = ev.target.closest?.('[data-scrub]');
  const inp = lab && lab.parentElement.querySelector('input[data-act="insptune"]');
  if (!inp || ev.button !== 0) return;
  ev.preventDefault();
  lab.setPointerCapture(ev.pointerId);
  const cur = parseFloat(String(inp.value).replace(',', '.'));
  inspScrub = { inp, props: String(inp.dataset.props || inp.dataset.prop).split(' '), x0: ev.clientX,
    v0: Number.isFinite(cur) ? cur : (Number(inp.dataset.base) || 0), step: Number(inp.dataset.step) || 1,
    min: inp.dataset.min === undefined ? null : Number(inp.dataset.min), unit: inp.dataset.unit || '',
    delta: Number(inp.dataset.delta || 0), next: null, applied: undefined, raf: 0 };
});
inspEl.addEventListener('pointermove', (ev) => {
  const s = inspScrub;
  if (!s) return;
  let v = Math.round((s.v0 + Math.round((ev.clientX - s.x0) / 3) * s.step * (ev.shiftKey ? 10 : 1)) * 100) / 100;
  if (s.min !== null) v = Math.max(s.min, v);
  s.inp.value = String(v);
  s.next = v;
  if (!s.raf) s.raf = requestAnimationFrame(() => { s.raf = 0; inspScrubApply(s); });
});
const inspScrubEnd = () => {
  const s = inspScrub;
  if (!s) return;
  if (s.raf) { cancelAnimationFrame(s.raf); s.raf = 0; }
  inspScrubApply(s);                       // останній кадр жесту
  inspScrub = null;
  if (s.applied !== undefined) saveTune(); // ОДИН запис пакета на весь жест; нічого не крутили — нічого й не пишемо
  paintInsp();
};
inspEl.addEventListener('pointerup', inspScrubEnd);
inspEl.addEventListener('pointercancel', inspScrubEnd);
/* Захоплення вказівника могло зникнути без pointerup (елемент прибрано, вікно втратило фокус): жест закінчується й тоді. */
inspEl.addEventListener('lostpointercapture', inspScrubEnd);

/* Клавіші інспектора, коли фокус в ОБОЛОНЦІ, а не в рамці: Alt, Esc, Enter, ← →, Alt+←/→/↑. Рамка слухає їх сама
   (`_onKey` оверлея); тут — той самий `handleKey`, одна логіка на обидва шляхи. Стрілки й Enter віддаємо лише коли
   нічого не сфокусовано (`target === body`): на кнопці чи в дереві шарів вони належать їм. Поле вводу, питання, палітра
   й дропдаун — теж не наші. */
function inspShellKey(ev) {
  const api = inspectorApi();
  if (!api || !api.on || mode === 'canvas' || homeOpen) return;
  if (ev.isComposing || ev.defaultPrevented || ev.metaKey || ev.ctrlKey) return;
  if (shellModalOpen() || openDd || cnDrawer || typingIn(ev, document)) return;
  if (ev.key === 'Alt') { api.setAlt(true); return; }
  if (ev.shiftKey) return;                 // Shift+←/→ — виділення тексту, не навігація
  if (ev.target !== document.body) return;
  if (api.handleKey(ev.key, { alt: ev.altKey })) ev.preventDefault();
}
document.addEventListener('keydown', inspShellKey);
document.addEventListener('keyup', (ev) => { if (ev.key === 'Alt') inspectorApi()?.setAlt(false); });
window.addEventListener('blur', () => inspectorApi()?.setAlt(false));

/* Делегація панелі «Коментарі» — окремий слухач (контейнер `#cmt-panel` живе поза `#bar`), як у `#insp-panel`. */
cmtEl.addEventListener('click', (ev) => {
  const el = ev.target.closest('[data-act]');
  if (!el || el.disabled) return;
  if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return;
  BAR_ACTIONS[el.dataset.act]?.(el.dataset.val, el, ev);
});
cmtEl.addEventListener('input', (ev) => {
  if (ev.target.classList?.contains('cmt-edit')) { cmtDraft = ev.target.value; return; }
  if (ev.target.id !== 'cmt-q') return;
  cmtQuery = ev.target.value;
  paintComments();
});
/* ⌘/Ctrl+Enter зберігає редагування, Esc скасовує; `stopPropagation`, щоб глобальний Esc не закрив панель. */
cmtEl.addEventListener('keydown', (ev) => {
  const ta = ev.target.closest?.('.cmt-edit');
  if (!ta) return;
  if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); BAR_ACTIONS.cmteditsave(ta.dataset.val); }
  else if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); BAR_ACTIONS.cmteditcancel(); }
});
cmtEl.setAttribute('aria-label', t('cmtTitle'));

/* Опитування (300мс) тут стояло до 17.09.2026, бо `CanvasInspector` кликав
   `onChange` лише з `set()`, і про клавішу `M` усередині iframe дізнатись не
   було як. Тепер оверлей емітить на КОЖНУ зміну стану (`_emit`), тож другий
   механізм на той самий стан більше не потрібен — а два механізми на один
   стан рано чи пізно розходяться. Живий тест «клавіша M оновлює панель»
   стереже саме це. */

// ===== Автозʼємка: старт на вході в «Огляд», лічильник, живі кадри, зупинка =====

/**
 * Чи знімають САМЕ ту ітерацію, яку зараз видно. Одне місце на цю звірку, бо
 * від неї залежать і підпис кнопки, і її підсвітка, і те, кого зупинить
 * натискання — розійдуться вони, і «Стоп» знову битиме не по тій ітерації.
 * `Boolean(shootingIt)` не зайвий: без жодної ітерації `picked` теж `null`, і
 * гола рівність зробила б «знімають» із «нема чого знімати».
 */
const shootingHere = () => Boolean(shootingIt) && shootingIt === picked;

/* Підпис кнопки зʼємки, підрахунок «немає кадрів цієї ширини» й точкове
   патчання `#pp-shoot` (`shootBtnLabel`/`noShotsHere`/`syncShootBtn`) жили
   тут до Task 4 Плану B. Нова панель (`shotsCountForWidth`/`shotsState`,
   вище) рахує те саме зі свіжими підписами прототипу, а й перемальовується
   ЦІЛКОМ (`renderPanel()`) замість точкового патча — окремого «синка» для
   самої лише кнопки більше не треба. */

/** Підмінити знімок однієї картки на льоту, без перебудови полотна. */
function applyFrame(f) {
  if (!f || !f.key || appliedFrames.has(`${f.key}:${f.sha}`)) return;
  appliedFrames.add(`${f.key}:${f.sha}`);
  /* querySelectorAll, а не querySelector: у флоу-виді той самий екран може стояти
     в ДВОХ смугах законно — `readFlow` тримає `seen` у межах однієї смуги, тож
     дві картки з тим самим `data-key` не помилка. З одиничним пошуком живий кадр
     проявлявся б лише в першій, а друга чекала б кінця прогону. */
  // `els`, а не `cards`: модульний `cards` — це ЗАПИСИ карток, і нижче нам
  // потрібні саме вони, щоб оновити висоту.
  const els = world.querySelectorAll(`.cv-card[data-key="${CSS.escape(f.key)}"]`);
  if (!els.length) return;               // картки може не бути у цьому виді
  /* Ключ кеша будує ТОЙ САМИЙ `shotVersion`, що й `cardEl`: другого джерела
     правди для URL кадру не заводимо — саме через нього кадр колись і застряг
     у вічному кеші. */
  const v = shotVersion({ stamp: f.stamp, capturedAt: f.capturedAt, sha: f.sha });
  // Через ту саму перевірку, що й у `cardEl`: подія прогресу — не привід вірити
  // числу на слово (див. `num` нагорі файла).
  const w = num(f.w);
  const h = num(f.h);
  const img = `<img alt="" draggable="false"`
    + (w ? ` width="${w}"` : '') + (h ? ` height="${h}"` : '')
    + ` decoding="async" loading="lazy"`
    + ` src="/shot?it=${encodeURIComponent(picked)}&node=${encodeURIComponent(f.key)}`
    + `&v=${encodeURIComponent(v)}">`;
  for (const card of els) {
    const body = card.querySelector('.cv-card-body');
    if (!body) continue;
    body.innerHTML = img;
    // Кадр щойно знято — бейдж «застаріло» на ньому вже неправда.
    card.querySelector('.cv-badge')?.remove();
  }
  /* Висота КАРТКИ під живий кадр — тим самим правилом, що в `cardEl`/`rowsLayout`
     (`head + h`), і через МОДЕЛЬ, а не прямим записом у стиль: картка, що
     виросла з заглушкових 900 до 3406, накрила б наступний ряд, тож ряди мусить
     розсунути `relayoutAll`. Без цього на ітерації без жодного кадру (де
     автостарт найцінніший) весь прогін видно кадр, стиснутий до чверті.

     У флоу-виді не чіпаємо нічого: там координати ставить чиста `flowLayout` на
     побудові, а перерахувати її без перебудови полотна нічим — перебудова ж
     скидає камеру просто під рукою дизайнера. Кадр там лишається стиснутим до
     кінця прогону: свідомий борг, а не недогляд. */
  if (!h || effView() === 'flow') return;
  let grew = false;
  for (const card of cards) {
    /* ПʼЯТИЙ споживач ключа кадру, і він поза `cardEl` — тому його легко
       проґавити (таблиця в плані T-35 його не називає). `card.id` — ключ ВУЗЛА
       (`holovna`), бо запис у `cards` описує екран: поруч лежать `page` і
       `state`, які ширини не знають. А `f.key` приїхав із прогресу зʼємки, тобто
       це ключ КАДРУ (`holovna@390`). Порівняти їх напряму — значить на будь-якій
       не-типовій ширині не збігтись ЖОДНОГО разу: висота картки лишилась би
       заглушковою (900), і весь прогін кадр було б видно стиснутим до чверті
       саме там, де кадрів ще немає й автостарт найцінніший. */
    if (frameKey(card.id, canvasW) !== f.key || card.h === h) continue;
    card.h = h;
    grew = true;
  }
  if (grew) relayoutAll();
}

/** Один такт опитування. Повертає `true`, поки зʼємка триває. */
async function pollProgress(it) {
  let snap;
  try {
    snap = await api(`/api/shoot-progress?it=${encodeURIComponent(it)}`);
  } catch (e) {
    return false;                        // сервер не відповів — не крутимо вічно
  }
  if (it !== picked) return false;       // дизайнер перемкнув ітерацію
  /* Такт, що завис на `fetch`, приземляється ПІСЛЯ того, як `shootWithProgress`
     уже все закрив: `clearInterval` не скасовує колбек, який уже виконується.
     Без цього рядка такий такт воскрешав би `shootProgress` із мертвим знімком —
     охорона нижче на порожньому стані дає `0 >= 0` і пропускає його.
     Звіряємо ІТЕРАЦІЮ, а не голе «йде зʼємка»: пізній такт минулого прогону
     інакше проходив би тут наскрізь, поки йде наступний, і писав би у спільний
     `shootProgress` чужий знімок. */
  if (shootingIt !== it) return false;
  (snap.frames || []).forEach(applyFrame);
  /* ⚠️ Сервер знімає запис із реєстру `_SHOOTS` ДО того, як віддасть відповідь на
     `POST /api/shoot` — виміряно живою пробою під час виконання Задачі 5. Такт
     опитування, що приземлився в це вікно, приносить ПОРОЖНІЙ знімок
     (`running:false, done:0`). Без цієї охорони лічильник блимнув би «0 з 8»
     рівно на фініші, тобто збрехав би саме там, де людина дивиться на результат.
     Підсумок канвас усе одно бере з відповіді на POST, а не звідси. */
  if (snap.running || (snap.done ?? 0) >= (shootProgress?.done ?? 0)) shootProgress = snap;
  renderPanel();
  return Boolean(snap.running);
}

/**
 * Запустити зʼємку й вести прогрес. POST свідомо БЕЗ `await` у гілці опитування:
 * він блокує до кінця прогону (хвилини), а прогрес мусить бути видно вже зараз.
 * Сервер — ThreadingHTTPServer, тож опитування йде паралельно тому ж процесу.
 */
async function shootWithProgress(it, { auto = false } = {}) {
  if (shootingIt) {
    /* Мовчазна відмова гірша за відмову: кнопка ітерації, яку НЕ знімають, тепер
       чесно каже «Оновити кадри (N)» (див. `shotsState()`), і натискання, після
       якого не відбувається нічого, читається як зламана кнопка. Автостарту
       казати нема чого — його ніхто не просив, і його відкладає `maybeAutoShoot`. */
    if (!auto) toast(t('toastShootBusy', shootingIt));
    return;
  }
  shootingIt = it;
  appliedFrames = new Set();
  shootProgress = { running: true, total: null, done: 0, frames: [], failed: [] };
  renderPanel();

  /* Хендл таймера — ЛОКАЛЬНИЙ, а `progressTimer` лише дзеркалить його для
     наступного прогону. Колбек читає змінну модуля вже ПІСЛЯ свого `await`, тож
     такт, що завис на `fetch` минулого прогону, приземлявся під час наступного
     (`shootingIt` знову зайнятий, тобто охорона в `pollProgress` не рятує) і
     гасив ЧУЖИЙ таймер — другий прогін ішов наосліп, без лічильника й без живих
     кадрів. Гасимо лише свій: `progressTimer === ticking`. */
  clearInterval(progressTimer);
  let pollDone;
  const polling = new Promise((resolve) => { pollDone = resolve; });
  const ticking = setInterval(async () => {
    if (await pollProgress(it)) return;
    clearInterval(ticking);
    if (progressTimer === ticking) progressTimer = null;
    pollDone();
  }, 700);
  progressTimer = ticking;

  /* Ширина прогону — та, у якій зараз стоїть полотно. Читається СИНХРОННО від
     входу у функцію (жодного `await` вище), тобто це та сама ширина, під яку
     дизайнер щойно натиснув, — рівно як `it` вище. Прогін однієї ширини кадрів
     інших не чіпає: ключ кадру несе ширину суфіксом. */
  const done = post('/api/shoot', { it, vp: canvasW })
    .catch((e) => ({ ok: false, error: e.message }));
  const res = await done;
  /* Приєднались до чужого прогону (сервер зводить другу спробу на ту саму
     ітерацію до наявної): відповідь приходить МИТТЄВО, а зʼємка йде далі, і
     кадри на диск кладе вона. Тому таймер тут НЕ гасимо, а чекаємо, поки
     опитування саме скаже «скінчилось»: інакше лічильник і живі кадри згасали б
     ще до першого такту — ця вкладка не бачила б ані прогресу, ані кадрів, ані
     слова. (Доти тут стояв коментар «прогрес уже було видно» — неправда за
     побудовою: відповідь `already` випереджає перший такт.) */
  if (res.already) {
    if (res.progress) { shootProgress = res.progress; renderPanel(); }
    await polling;
  }
  clearInterval(ticking);
  if (progressTimer === ticking) progressTimer = null;
  shootingIt = null;
  /* Скільки кадрів СПРАВДІ лягло на диск — читаємо ДО обнулення прогресу. Перша
     редакція обнуляла його рядком вище й казала «знято 0» саме тоді, коли зняти
     встигли найбільше; виправлення того нуля дало протилежну брехню — бралось
     `done`, а сервер рахує ним і `frame`, і `fail`. SIGTERM на зупинці вбиває
     Chromium, але не node, тож решта сторінок перетворюється на швидкі `fail`
     (виміряно живою перевіркою C у `tests/live/autoshoot.test.mjs`) — і зупинка
     на 2-му з 22 давала тост «зупинено, знято 22». Рахуємо `frames`.
     Беремо БІЛЬШЕ з двох спостережень: знімок у відповіді сервера знято після
     `finish()`, тобто він останнє слово на зупинці, а наш локальний свіжіший у
     гілці `already`, де відповідь приїхала на самому початку чужого прогону. */
  const frameCount = (snap) => (Array.isArray(snap?.frames) ? snap.frames.length : 0);
  const shotCount = Math.max(frameCount(shootProgress), frameCount(res.progress));
  shootProgress = null;

  const r = res.report || {};
  if (res.stopped) {
    toast(t('toastShootStopped', it, shotCount));
  } else if (res.already) {
    toast(t('toastShootAlready', it, shotCount));
  } else if (!res.ok) {
    /* Автостарт не сміє кидати модалку в обличчя: дизайнер її не просив. Ручний
       перезнім — навпаки, там `tell`, бо людина натиснула й чекає відповіді. */
    const msg = r.failed?.length
      ? t('errShootPartial', it, r.shot?.length ?? 0)
        + r.failed.map((f) => t('errShootFailedItem', f.id, f.problem)).join('\n')
      : t('errShootCrashed', it)
        + (res.error || res.stderr || r.raw || t('errShootNoReason'));
    if (auto) toast(r.failed?.length ? t('toastShootAutoFailedCount', r.failed.length) : t('toastShootAutoFailedGeneric'));
    else tell(msg);
  } else {
    toast(t('toastShootDone', it, r.shot?.length ?? 0)
          + (r.left?.length ? t('toastShootLeftAlone', r.left.length) : ''));
  }
  await freshen();
  render();
  /* Автостарт, який цей прогін проковтнув (див. `maybeAutoShoot`): перевіряємо
     ще раз ЗАРАЗ, коли `shootingIt` уже порожній, — іншого приводу не буде,
     дизайнер уже й у «Огляді», і на своїй ітерації. Циклу немає: позначку
     `autoShootOff` ставить сам `maybeAutoShoot` ДО запуску, а сюди ми потрапляємо
     лише з ітерацією, чий автостарт справді відклали, і рівно один раз. */
  const deferred = autoShootDeferred;
  autoShootDeferred = null;
  if (deferred === picked && mode === 'canvas') maybeAutoShoot();
}

/**
 * Автостарт: після перевірки свіжості зняти те, що застаріло.
 *
 * ⛔ РІВНО ОДИН автостарт на набір застарілого. Позначку ставимо ДО запуску, а
 * знімає її `freshen()`, коли перелік застарілих СТАВ ІНШИМ (тобто макет
 * правили). Без цього сторінка, яка стабільно не знімається, давала б нову
 * зʼємку на КОЖЕН вхід у «Огляд»: `shootWithProgress` наприкінці кличе
 * `freshen()`, перелік лишається тим самим, а `autoShootOff` порожній — і
 * дизайнер отримує браузерний прогін щоразу, коли просто зайшов подивитись.
 * Ручна кнопка при цьому лишається доступна завжди: позначка глушить лише
 * автоматичний запуск, не людський.
 */
function maybeAutoShoot() {
  const check = checkOf();
  if (!check || !check.stale.length) return;
  /* Зʼємка ІНШОЇ ітерації — не привід забути автостарт цієї, а привід відкласти
     його. Кличуть нас лише вхід у «Огляд» і зміна ітерації, тож проста відмова
     означала «ніколи»: перемкнувся під час прогону — і лишився з ітерацією, де
     кадрів немає, а зняти їх уже ніхто не запропонує. Кінець прогону перевірить
     це місце ще раз (`shootWithProgress`). */
  if (shootingIt) { autoShootDeferred = picked; return; }
  if (autoShootOff.has(picked) || autoShootStopped.has(picked)) return;
  autoShootOff.add(picked);
  shootWithProgress(picked, { auto: true });
}

/* `keepFrame` — лише в «робочому вигляді»: рамка не переприсвоюється (кожне присвоєння `frame.src` перезавантажує
   документ). Для «Огляду» не діє: полотно перебудовується завжди, рамка там схована. */
function applyMode(task, { keepFrame = false } = {}) {
  if (mode === 'canvas') {
    // ховаємо СЦЕНУ, а не рамку: рамка лежить у сцені, і сцена зі своєю підкладкою
    // накрила б полотно «Огляду» світлим прямокутником
    stage.hidden = true; canvasEl.hidden = false;
    buildCanvas(task);
    cmtViewSwitch();
    ovc.enter();
    if (cmtOpen && ovc.layer && !ovc.layer.commentMode) ovc.layer.setCommentMode(true);   // шару ще нема — його `onReady` зробить те саме
  } else {
    ovc.leave();
    canvasEl.hidden = true; stage.hidden = false;
    /* Хвіст стану — ОСТАННІМ і вже екранованим (`stateQuery`), рівно як у
       `bin/shoot.mjs`: інакше живий вид і кадр показували б різні екрани. Наші
       параметри стан перебити не може — це стереже `checkState`. */
    if (!keepFrame) {
      frame.src = (picked && pickedPage)
        ? `/commented?it=${encodeURIComponent(picked)}&page=${encodeURIComponent(pickedPage)}`
          + `&host=1${stateQuery(pickedState)}`
        : (picked ? `/commented?it=${encodeURIComponent(picked)}&host=1` : 'about:blank');
      /* Нова сторінка в рамці — новий коментатор: старий знімок і готовність уже не про неї (`ready` поверне нове). */
      /* Змінилась адреса (ітерація/канал/сторінка) — вибір, редагування й чернетка належать старому документу. */
      const srcNow = frame.getAttribute('src');
      dropFrameCmt({ sel: srcNow !== lastFrameSrc });
      lastFrameSrc = srcNow;
    }
    cmtViewSwitch();
  }
}

// Камера: `cvx/cvy/cvscale` — ДЕ ми зараз, `camTarget` — куди їдемо. Один rAF-цикл
// тягне перше до другого, тому колесо, стрибок і «вписати все» відчуваються однаково.
let camTarget = null, camRaf = null, camLast = 0;

/* Останнє, що ми ПОКЛАЛИ в `--cv-scale` і в індикатор. Тримаємо самі, а не
   питаємо DOM: читання `style.getPropertyValue` посеред кадру — це той самий
   доступ до стилю, від якого ми й ховаємось. */
let cvScaleVar = null, cvZoomText = null;

function applyT() {
  world.style.transform = `translate(${cvx}px,${cvy}px) scale(${cvscale})`;
  /* Масштаб У СТИЛЬ — щоб підпис смуги міг вирахувати свій кегль через `calc()` і
     не зникнути на дрібному зумі (він живе у світі, отже масштабується разом із
     ним). Змінна на `#world` УСПАДКОВУЄТЬСЯ, тобто кожен її запис інвалідує стиль
     усім кадрам і підписам світу — тому пишемо лише коли значення СПРАВДІ інше, а
     «інше» рахуємо по грубій сітці (`quantScale`): згладжування камери міняє
     масштаб на мільйонні частки навіть на хвості, коли на екрані вже нічого не
     рухається. На панорамі масштаб не змінюється зовсім, тобто записів нуль. */
  const q = quantScale(cvscale);
  if (q !== cvScaleVar) {
    cvScaleVar = q;
    world.style.setProperty('--cv-scale', q);
  }
  /* Індикатор зуму — ТУТ, а не окремим таймером: єдине місце, де камера справді
     стає новою, вже є, і будь-який другий шлях показував би відсоток, якого немає.
     Текст пишемо теж лише на зміні: цілий відсоток не міняється більшу частину
     кадрів згладжування. */
  const zoomText = `${Math.round(cvscale * 100)}%`;
  if (zoomEl && zoomText !== cvZoomText) {
    cvZoomText = zoomText;
    zoomEl.textContent = zoomText;
  }
  /* Піни — у ТОМУ Ж виклику, що трансформ світу, а не своїм rAF: драг пише
     трансформ прямо з `pointermove`, і пін, що їде наступним кадром, відставав
     би від кадру на кожному русі. */
  ovc.tick();
}

function camTick(now) {
  const dt = camLast ? now - camLast : 16;
  camLast = now;
  const next = step({ x: cvx, y: cvy, scale: cvscale }, camTarget, dt);
  cvx = next.x; cvy = next.y; cvscale = next.scale;
  applyT();
  if (next.done) { camRaf = null; camTarget = null; camLast = 0; return; }
  camRaf = requestAnimationFrame(camTick);
}

/** Поставити ціль камери. Цикл сам зупиниться, коли доїде. */
function camTo(target) {
  camTarget = target;
  // Хендл обнуляється в кінці циклу, а не лише скасовується: інакше «скасовано»
  // і «не запущено» стають нерозрізнимими, і другий виклик не запустить нічого.
  if (camRaf === null) { camLast = 0; camRaf = requestAnimationFrame(camTick); }
}

/** Убити живий цикл камери. Викликається там, де камера задається авторитетно
    (рука на драгу, `fitAll()`): цикл, що доїжджає до старої цілі, інакше пише
    cvx/cvy поверх щойно порахованих і виглядає це як стрибок. */
function camStop() {
  if (camRaf !== null) cancelAnimationFrame(camRaf);
  camRaf = null; camTarget = null; camLast = 0;
}

/**
 * Розкладка сіткового виду — з місцем під підписи рядів.
 *
 * Зсув на `ROW_TITLE_TOP` живе ТУТ, а не в циклі розстановки карток, бо його
 * мусять бачити ОБИДВА читачі розкладки: і `relayoutAll` (де стоять картки), і
 * `fitAll` (звідки береться габарит світу). Порахований в одному з них, він
 * зрізав би низ останнього ряду на «вписати все»: `worldBox` рахує габарит по
 * КАРТКАХ, тобто по вже зсунутих координатах, і недобір там нічим не видно,
 * поки він менший за поле `fitBox`.
 *
 * Зсув потрібен узагалі тому, що підпис стоїть НАД рядом, а `#world` не має
 * відʼємних координат: без зсуву підпис першого ряду сідає вище нуля, а вище
 * нуля камера не дивиться (та сама причина, що в `FLOW_TOP`).
 */
function gridPlaced() {
  const placed = rowsLayout(gridRows.map((r) => r.cards),
                            { cardW: cardW(), gap: GAP, head: HEAD });
  return placed.map((p) => ({ ...p, y: p.y + ROW_TITLE_TOP }));
}

function relayoutAll() {
  /* У флоу-виді координати вже проставила чиста розкладка (`flowLayout`), і
     сіткова тут не «перевпорядкувала» б граф, а розкидала його: колонки рангів
     і смуги зникли б, лишились би ряди сторінок. */
  if (effView() === 'flow') return;
  const placed = gridPlaced();
  const byId = new Map(placed.map((p) => [p.id, p]));
  for (const card of cards) {
    const p = byId.get(card.id);
    if (!p) continue;
    card.x = p.x;
    card.y = p.y;
    card.el.style.cssText = `left:${p.x}px;top:${p.y}px;width:${cardW()}px;height:${p.h}px`;
  }
  /* Підпис ряду — окреме дитя світу, як `.cv-band-title` у флоу, а не вміст
     першої картки: він належить РЯДУ, стоїть ВИЩЕ за картки (над їхніми головами)
     і живе поза їхніми межами — усередині картки його зрізала б сама картка.

     Малюється тут, а не в `buildGridView`, бо `top` підпису рахується від `y`
     ряду, а `y` зʼявляється лише після розкладки.

     Підписи МИНУЛОЇ розкладки знімаємо рядком нижче. Доти тут стояло «дублів не
     буде: єдиний викликач — `buildCanvas`, який щойно почистив `world`» — це
     більше не так: живий кадр автозʼємки (`applyFrame`) міняє висоту картки й
     мусить розсунути ряди, тобто кличе розкладку по ходу прогону. Без прибирання
     кожен такий кадр лишав би по підпису на ряд — видимою плямою. */
  world.querySelectorAll('.cv-row-title').forEach((n) => n.remove());
  for (const row of gridRows) {
    /* Порожнього ряду тут не буває: `rowFor` завжди кладе САМУ сторінку, і це не
       здогад, а покритий тест `rows-model`. Тому охорони на `row.cards[0]` немає
       — вона не змогла б назвати, що саме зробило ряд порожнім, тобто була б
       охороною без ЧОМУ (на відміну від такої ж гілки в `rowsLayout`: та стереже
       контракт ЧИСТОЇ функції, у якої свій вхід і свій тест). */
    const label = document.createElement('div');
    label.className = 'cv-row-title';
    label.style.cssText = `left:${row.cards[0].x}px;top:${row.cards[0].y - ROW_TITLE_TOP}px`;
    // `textContent`, а не `innerHTML`: імʼя сторінки приходить із `pages.json`,
    // який пишуть руками, — те саме правило, що на підписі кадру.
    label.textContent = row.title;
    world.appendChild(label);
  }
}

function fitAll() {
  /* Гасимо цикл ДО охорони на порожній канвас: інваріант «fitAll завжди вбиває
     живий цикл» мусить бути справжнім, інакше на нього не можна спиратися.

     Це НЕСУЩА охорона, і ось виміряний шлях, де вона єдина (ревʼю 24.08.2026):
     колесо → вихід із «Огляду» кнопкою смуги → одразу назад. Жодного pointerdown
     на холсті, тому запобіжник у драгу не спрацьовує, і без цього рядка камера
     сідає не у fit: scale 0.483573 замість 0.399096 — інший зум на 21% і сотні
     px зсуву. Живих циклів тепер заводять ДВА викликачі — колесо (`camTo` у
     `wheel`) і переліт до кадру (`focusPage`), — тобто «зумнув і пішов» уже не
     єдиний шлях сюди: «клікнув рядок панелі й одразу вийшов з Огляду» рівно
     такий самий. */
  camStop();
  if (!cards.length) return;
  /* У флоу-виді габарит бере `buildFlowView`, а не `worldBox` по картках: у світі
     є ще смуги з лейнами під стрілки й підписи смуг, яких у переліку карток нема.
     Порахувати межі по самих кадрах означало б зрізати камерою рівно ті лейни, у
     яких Task 9 малює стрілки. */
  const box = effView() === 'flow'
    ? (flowBox || { w: 0, h: 0 })
    : worldBox(gridPlaced(), cardW());
  const cam = fitBox(box, { w: canvasEl.clientWidth, h: canvasEl.clientHeight });
  cvx = cam.x; cvy = cam.y; cvscale = cam.scale;
  applyT();
}

/**
 * Привести камеру до кадру цієї сторінки й підсвітити його: клік по рядку панелі
 * сторінок у «Огляді».
 *
 * ЧЕРЕЗ ЦІЛЬ (`camTo`), а не прямим записом `cvx/cvy`: переліт мусить відчуватись
 * тією ж ощущалкою, що колесо. Це ДРУГИЙ викликач `camTo` — через нього `camStop()`
 * у драгу й у `fitAll()` стереже вже не теоретичний випадок.
 *
 * Математика — у `app/camera.js` (`focusBox`), тут лишається знайти кадр і взяти
 * габарит полотна.
 */
function focusPage(pageId) {
  const mine = cards.filter((c) => c.page === pageId);
  /* Сторінка без кадру. Сьогодні цим шляхом не проходить НІЩО, і це не здогад:
     кадри будуються з того самого дерева, що й рядки панелі, — у сітці ряд
     кладе САМУ сторінку завжди (`buildRows`), а у флоу все, що в граф не
     потрапило, іде групою «не у флоу», навіть сторінка, чий вузол викинув
     `readFlow`. Тека-організатор кадру справді не має, але її рядок сюди не
     доходить (див. обробник кліку). Тобто це охорона КОНТРАКТУ, живою
     перевіркою не покрита — сказано вголос, щоб її не рахували доведеною.
     Мовчати тут однаково не можна: рядок, який не робить нічого, виглядає як
     зламана фіча. */
  if (!mine.length) {
    toast(t('toastNoFrameForPage'));
    return;
  }
  /* Кадрів у сторінки буває кілька, і тепер В ОБОХ видах: у флоу той самий екран
     буває у двох смугах, у сітці поруч зі сторінкою стоять її СТАНИ (той самий
     `page`, інший ключ кадру). Ведемо до першого в порядку читання (вище, а при
     рівних — лівіше), тобто в сітці — до самої сторінки, бо стани стоять правіше
     за неї. Саме детермінований порядок, а не «найближчий до камери»: інакше
     повторний клік по тому ж рядку кидав би камеру між копіями. «Перебирати копії
     кліками» — інша фіча, і її ніхто не просив. */
  const card = mine.reduce((a, b) => ((b.y < a.y || (b.y === a.y && b.x < a.x)) ? b : a));
  /* Підсвітка — це «куди ми щойно полетіли», а не «яка сторінка обрана»: тому
     ставиться тут, а не в `cardEl` по `pickedPage`. Інакше вхід у «Огляд»
     обводив би перший кадр завжди — сигнал без події за ним. Перебудова холста
     її знімає разом із самими елементами, і це те саме, що діється з камерою. */
  for (const c of cards) c.el.classList.toggle('sel', c === card);
  /* Переліт — це рух камери РУКОЮ людини, отже `userMoved`. Без цього рядка
     `buildCanvas` лишає прапорець збитим, і перший же ресайз вікна вписує все
     заново — тобто відкидає людину з кадру назад у bird-view. */
  userMoved = true;
  camTo(focusBox({ x: card.x, y: card.y, w: cardW() },
                 { w: canvasEl.clientWidth, h: canvasEl.clientHeight }));
}

/**
 * Розмітка бейджа кадру — ОДНЕ місце на тег `em` і клас `cv-badge`. Початкова
 * побудова нижче і `onerror`-обробник кадру, який не доїхав, малюють бейдж У
 * ДВОХ різних точках коду; без спільної функції вони мусили б погоджувати тег
 * і клас окремо, і перша ж зміна розмітки (напр. `em` → `span`) розійшлася б
 * між ними мовчки — саме ту гілку, яку живцем стереже K3, ніхто не помітив би.
 * `esc()` завжди: `shot.problem` — рядок із чужого `manifest.json`.
 */
const badgeHTML = (text, warn) => `<em class="cv-badge${warn ? ' cv-badge-warn' : ''}">${esc(text)}</em>`;

/**
 * Один кадр на полотні. `key` — ключ ВУЗЛА (сторінка або сторінка+стан), тобто
 * який це екран; ключ КАДРУ (з шириною полотна) рахується всередині — див.
 * `fkey` нижче. `label` — підпис у голові. Однаковий у сітці й у флоу: кадр той
 * самий, різна лише розкладка.
 *
 * Параметра `page` тут НЕМАЄ, хоч 8a лишив його «на виріст під флоу»: id сторінки
 * потрібен не картці, а запису в `cards` — його читає `openCard`, коли вирішує,
 * що відкривати. Кадр про сторінку не знає нічого, крім ключа знімка.
 */
function cardEl({ key, label, published }) {
  /* ⛔ Ключів тут ДВА, і плутати їх не можна. `key` — ключ ВУЗЛА (`holovna`,
     `poshuk~48d0ed7a`): він приходить із дерева сторінок і `flow.json` і каже,
     який це ЕКРАН. `fkey` — ключ КАДРУ (`holovna@390`): знімок цього екрана в
     ТІЙ ширині, у якій зараз стоїть полотно, і саме під ним лежать `.webp`,
     запис манифеста й події прогресу зʼємки.

     Споживачів ключа кадру рівно чотири, і перейти на нього мусять УСІ, бо
     половинчаста заміна дає три різні НА ВИГЛЯД баги: запис манифеста (інакше
     картка каже «немає знімка» при наявному кадрі), `dataset.key` (інакше
     `applyFrame` не знайде картку — кадри перестануть проявлятись по одному),
     `src` кадру (інакше 404 замість знімка) і звірка з подією прогресу, яка
     ключ кадру вже несе (`bin/shoot.mjs`) — вона зійдеться лише якщо `data-key`
     теж ключ кадру.

     Ключ ВУЗЛА при цьому лишається в записі `cards` (`id`), як і `page`/`state`:
     він про екран, і його читають ті, кого ширина не обходить. */
  const fkey = frameKey(key, canvasW);
  const shot = shotManifest.shots?.[fkey] || null;
  // Розміри з манифеста — через спільний `num` нагорі файла (там і причина, чому
  // непридатне число викидається, а не екранується).
  const w = shot ? num(shot.w) : null;
  const h = shot ? num(shot.h) : null;
  // Немає знімка — картка все одно є, але каже про це: полотно, яке вдає
  // повноту, гірше за полотно, яке називає свої дірки.
  // `problem` — ПЕРШИЙ після відсутності кадру: битий кадр і застарілий кадр
  // вимагають різних дій, а «застаріло» на битому кадрі відправляє дизайнера
  // шукати зміну в макеті, якої не було. Через це ж `shot.stable === false`
  // нижче для СВІЖИХ записів мертва за побудовою: `bin/shoot.mjs` завжди кладе
  // `problem` поруч із `stable: false`, і ця гілка дотягне до бейджа лише
  // запис, зроблений ДО цього фікса — її лишили живою саме для такого запису.
  const badge = !shot ? badgeHTML(t('badgeNoShot'), false)
    : shot.problem ? badgeHTML(shot.problem, true)
      : shot.stale ? badgeHTML(t('badgeStale'), true)
        : shot.stable === false ? badgeHTML(t('badgeUnstable'), true)
          /* Обрізаний кадр мусить казати про це вголос: інакше він тихо показує
             менше, ніж є у макеті, і виглядає при цьому нормальним. Висота — лише
             уточнення до цього сигналу, тому непридатна відбирає уточнення, а не
             сам сигнал. */
          : shot.truncated
            ? badgeHTML(t('badgeTruncated', h), true) : '';
  const el = document.createElement('div');
  el.className = 'cv-card';
  /* Ключ кадру в DOM — щоб подія прогресу могла знайти саме цю картку й
     підмінити знімок, не перебудовуючи полотно. Перебудова тут неприпустима:
     вона скидає камеру й рве панораму просто під рукою дизайнера. */
  el.dataset.key = fkey;
  el.innerHTML = `<div class="cv-card-head">${published ? '<i class="cv-dot"></i>' : ''}${esc(label)}`
    + ` <small>${published ? t('cardPublishedLabel') : t('cardDraftLabel')}</small>${badge}`
    + `<button class="cv-open" type="button" title="${t('cardOpenTitle')}">${ico('ext', 14)}<span>${t('openFrame')}</span></button></div>`
    + `<div class="cv-card-body">${shot
      /* `draggable="false"` — не косметика: кадр без нього «відтягується» з полотна
         як файл (native drag браузера), і жест, яким пануть холст, часом кінчається
         привидом картинки в руці. Виділення це не лікує — `user-select` про
         перетягування картинок не знає нічого, це окремий механізм. */
      ? `<img alt="" draggable="false"${w ? ` width="${w}"` : ''}${h ? ` height="${h}"` : ''} decoding="async"`
        /* Нативне лінивe завантаження браузера: «Огляд» малює картки для ВСІХ
           сторінок одразу, а користувач бачить лише ту частину полотна, куди
           панорамить камера — без цього браузер тягнув би повнорозмірні webp
           і поза екраном. Свого механізму лінивого монтування тут більше
           немає (`updateLazy()` прибрали ще на етапі 1 флоу-канваса) — тобто
           конфлікту двох реалізацій нема, `loading="lazy"` єдина. */
        + ' loading="lazy"'
        /* Ключ кадру рахує `shotVersion` — ОДНА реалізація на канвас і на тести.
           Головна його складова — хеш байтів знімка: ні штамп (хеш ДЖЕРЕЛ), ні
           `capturedAt` (точність до ХВИЛИНИ) не міняються при перезйомці того
           самого макета двічі поспіль, а кадр віддається з `immutable`. */
        + ` src="/shot?it=${encodeURIComponent(picked)}&node=${encodeURIComponent(fkey)}`
        + `&v=${encodeURIComponent(shotVersion(shot))}">`
      : `<div class="cv-card-ph">${esc(label)}</div>`}</div>`;
  // Висота КАДРУ для розкладки: без придатного числа беремо ту саму заглушку, що
  // й для картки без знімка, інакше `NaN` доїхав би до `style.height` і кадр
  // лишився б без висоти зовсім.
  /* Кадр міг не доїхати, хоч запис у манифесті є: тека ітерації приїжджає з
     GitLab з чужої машини, і `manifest.json` та `.webp` — окремі файли. Без цього
     обробника картка показує іконку битої картинки, тобто дірку без імені. */
  const img = el.querySelector('img');
  if (img) {
    img.addEventListener('error', () => {
      const body = el.querySelector('.cv-card-body');
      if (body) body.innerHTML = `<div class="cv-card-ph">${esc(label)}</div>`;
      // Один виклик `badgeHTML` — розмітка тегу й класу йде з ТОГО САМОГО
      // місця, що й початковий бейдж вище, тож замінити наявний чи вставити
      // новий однаково безпечно: обидві гілки малюють ідентичний бейдж.
      const newBadge = badgeHTML(t('badgeUnreadable'), true);
      const b = el.querySelector('.cv-badge');
      if (b) b.outerHTML = newBadge;
      else el.querySelector('.cv-card-head')?.insertAdjacentHTML('beforeend', newBadge);
    }, { once: true });
  }
  return { el, h: h ?? 900 };
}

/**
 * Сітковий вид «Огляду»: ряд = сторінка й усе, що під нею.
 *
 * Склад ряду рахує `buildRows` (без DOM, покрито `tests/rows-model.test.mjs`),
 * тут лишається тільки малювання. Стани беруться з ГРАФА, але ряд від графа не
 * залежить: немає файла, файл побитий, вузол в нікуди — ряд схлопується до
 * сторінки з дітьми, і полотно працює. Це навмисно: у задачі 3 батчу v1.25.0
 * протилежна помилка (ранній вихід лишав `flowRaw` старим) змушувала полотно
 * малювати фейковий перелік «немає сторінки».
 *
 * ⚠️ Два входи, і кожен потрібен саме такий. `pageTree` — ДЕРЕВО (`panelPages`),
 * бо ряд це «сторінка й усе під нею», тобто `buildRows` потрібен звʼязок «батько
 * → діти», якого плоский перелік уже не має. `openable` — той самий плоский
 * перелік ВІДКРИВАНИХ сторінок, що й у флоу-виді (`srcPages`), бо його чекає
 * `readFlow`. Порахувати другий із першого тут ЗАМАНЛИВО, але `buildCanvas` уже
 * порахував — і другий прохід розійшовся б із першим у фільтрі тек саме тихо.
 */
function buildGridView(pageTree, openable) {
  const nodes = flowNodesForGrid(openable);
  const rows = buildRows(pageTree, nodes);
  const cards = [];
  gridRows = [];
  for (const row of rows) {
    const built = row.map((c) => {
      const { el, h } = cardEl({ key: c.key, label: c.label, published: c.published });
      world.appendChild(el);
      /* `page` тут НЕСУЩИЙ, і в ряду зі станами вже НЕ дорівнює `id`: `openCard`
         читає саме його, бо ключ кадру стану — це `сторінка~хеш`. Прибери `page`
         — і «Відкрити» кладе в `pickedPage` `undefined`, після чого `loadPages()`
         мовчки відкриває першу сторінку замість тієї, по якій клікнули (ловить
         I3). `raw` — вузол у сирому `flow.json`; у сітці вузли не тягаються
         мишею, тому null, але поле лишається, щоб запис сітки й запис флоу мали
         ОДНАКОВІ поля: інакше наступний читач вирішить, що стан буває лише у
         флоу, і напише розвилку по виду там, де її не треба. */
      return { id: c.key, page: c.page, state: c.state, el, h, x: 0, y: 0, raw: null };
    });
    gridRows.push({ title: row.title, cards: built });
    cards.push(...built);
  }
  return cards;
}

/**
 * Вузли графа для сітки — або порожньо, якщо графа немає чи він не читається.
 *
 * Ковтати помилку тут МОЖНА і треба саме тут: у сітці граф — джерело ДОДАТКОВИХ
 * кадрів, а не умова показу. Причина не зникає — її показує `paintFlowProblems`
 * (перелік про ФАЙЛ, а не про вид, і в сітці він лишається свідомо).
 *
 * `openable` подається ГОТОВИМ і саме таким, як його описує контракт `readFlow`
 * (`app/flow-model.js`): плоский перелік відкриваних сторінок, без тек. Обидва
 * викликачі `readFlow` мусять годувати його однаково — інакше «що ця функція
 * приймає» доводиться вивчати по викликачах, а не по її ж докстрінгу.
 */
function flowNodesForGrid(openable) {
  if (!flowRaw) return [];
  try {
    const parsed = readFlow(flowRaw, openable.map((f) => ({ id: f.page.id, name: f.page.name })));
    /* Скарги розбору — у ту саму скриньку, що й у флоу-виді. Доти сітка їх
       мовчки викидала, а `paintFlowProblems` пояснював це тим, що «свій
       `readFlow` канвас там не кличе взагалі», — після появи цієї функції
       неправда. Дірка не теоретична: у `catch` `freshen()` стоїть
       `lastCheck = null`, і тоді в сітці не лишається ЖОДНОГО джерела скарг.

       Але ЛИШЕ коли переліку сторінок можна вірити. На транзиентному збої
       `/api/iteration-pages` (сервер рестартує, файли на диску цілі) `openable`
       порожній, і `readFlow` чесно скаржиться на КОЖЕН вузол «немає сторінки» —
       брехня, бо зник перелік, а не сторінки. Рівно її Task 3 прибрав з полотна
       гейтом `!pagesError` в `effView()`; без цього рядка вона вернулась би
       панеллю скарг. Знайдено не міркуванням, а червоним живим тестом
       «полотно не малює фейкові „немає сторінки“». */
    if (!pagesError) nodeProblems = parsed.problems;
    return parsed.flows.flatMap((f) => f.nodes);
  } catch (e) {
    return [];
  }
}

/**
 * Мітка на СИРОМУ вузлі `flow.json`: значення — сам цей вузол. Ставиться ДО
 * розбору, а доїжджає до кадру сама, бо `readFlow` копіює вузол спредом
 * (`{...node}`), а спред переносить власні енумеровні СИМВОЛЬНІ поля — тобто
 * чистий модуль правити не треба.
 *
 * Символ, а не звичайне поле, ще й тому, що `JSON.stringify` символьних ключів
 * не бачить: мітка не потрапить у `flow.json`, який ми ж і записуємо.
 *
 * Навіщо взагалі: інакше драг мусив би шукати «свій» вузол по ключу кадру в
 * УСІХ смугах — і писав би `pos` у кожну, де трапилась та сама сторінка (так
 * робив план). Одна сторінка в двох сценаріях — річ звичайна, а поїхав би при
 * цьому і той кадр, якого дизайнер не торкався.
 */
const RAW_NODE = Symbol('rawNode');

/**
 * Флоу-вид: кадри стоять там, де сказала чиста розкладка, а все, що в граф не
 * потрапило, іде окремою групою «не у флоу» під смугами — не зникає. Зникла
 * сторінка на полотні гірша за зайву: її просто перестають помічати.
 */
function buildFlowView(srcPages) {
  const vis = visibleIds(panelPages);
  const pages = srcPages.map((f) => ({ id: f.page.id, name: f.page.name,
                                       published: vis.has(f.page.id) }));
  const byId = new Map(pages.map((p) => [p.id, p]));
  // Мітки — ДО розбору (див. `RAW_NODE`). Формат тут не перевіряємо: побитий
  // корінь чи `nodes`, що не список, — робота `readFlow`, і скаржитись двічі
  // означало б розписати ту саму перевірку у двох місцях.
  for (const f of Array.isArray(flowRaw?.flows) ? flowRaw.flows : []) {
    for (const nd of Array.isArray(f?.nodes) ? f.nodes : []) {
      if (nd && typeof nd === 'object' && !Array.isArray(nd)) nd[RAW_NODE] = nd;
    }
  }
  const parsed = readFlow(flowRaw, pages);
  /* Малює їх `buildCanvas` ПІСЛЯ побудови — разом зі скаргами сервера й причиною
     нечитного файла. Показувати звідси означало б мати два малювальники однієї
     панелі, і той, хто малює другим, забирав би перелік першого. */
  nodeProblems = parsed.problems;

  /* Id вузла унікальний лише В МЕЖАХ смуги — рівно так його й перевіряє
     `readFlow`. Тому ОДНА спільна мапа «id → кадр» на всі смуги (як було в плані)
     склеює вузли з однаковим id у різних сценаріях: `appendChild` не копіює, а
     ПЕРЕНОСИТЬ елемент, тож кадр зникає з першої смуги, а `flowLayout` дістає для
     нього чужу висоту. Робимо id глобальними ДО розкладки — ребра й ранги
     переїжджають разом, інакше вони вказували б у порожнечу. */
  const built = new Map();          // глобальний id → {node, el, h}
  const flows = parsed.flows.map((flow, i) => {
    const uid = (id) => `${i}\u0000${id}`;
    for (const node of flow.nodes) {
      built.set(uid(node.id), { node, ...cardEl({ key: node.key, label: node.label,
                                                  published: byId.get(node.page).published }) });
    }
    return {
      ...flow,
      nodes: flow.nodes.map((n) => ({ ...n, id: uid(n.id) })),
      edges: flow.edges.map((e) => ({ ...e, from: uid(e.from), to: uid(e.to) })),
      ranks: new Map([...flow.ranks].map(([id, r]) => [uid(id), r])),
    };
  });

  /* Відстань між смугами — їхні ПОЛЯ плюс зазор: підкладка виступає за габарит
     кадрів на `BAND_PAD_*`, і без цього доданка поля сусідніх смуг перекривались
     (на демо-графі блогу — на 40px, підкладки злипались у пляму). Розкладка про
     поля не знає навмисно: там чиста геометрія, а поля — це DOM. */
  const { bands, box } = flowLayout(flows, (id) => built.get(id).h,
                                    { cardW: cardW(), gap: GAP, head: HEAD,
                                      bandGap: BAND_PAD_BOTTOM + BAND_PAD_TOP + GAP });

  /* Спершу ВСІ смуги, потім усі кадри. Домішувати смугу другого сценарію після
     кадрів першого не можна: у DOM пізніший малюється поверх, і фон смуги ліг би
     на підпис і лейни попередньої. */
  for (const band of bands) {
    const bandEl = document.createElement('div');
    bandEl.className = 'cv-band';
    /* Ширина ЧИСЛОМ, а не `width:100%`: `#world` спозиційований абсолютно, а всі
       його діти теж абсолютні й у ширину не додають — тобто вона нуль, і смуга
       на 100% була б нульової ширини, тобто невидимою. */
    const w = Math.max(0, ...band.placed.map((p) => p.x + p.w));
    /* Смуга — це вміст ПЛЮС поля, і росте вона всередину світу, а не назовні:
       кадри вже зсунуті на `FLOW_LEFT`/`FLOW_TOP`, тому підкладка починається
       рівно в нулі й ліворуч від нуля не лізе. Відʼємних координат світ не має —
       «вписати все» рахує габарит від нуля, і все, що вище чи ліворуч, камера
       зрізає (жива перевірка I). */
    bandEl.style.cssText = `left:${FLOW_LEFT - BAND_PAD_X}px;`
      + `top:${FLOW_TOP + band.y - BAND_PAD_TOP}px;`
      + `width:${w + BAND_PAD_X * 2}px;height:${band.h + BAND_PAD_TOP + BAND_PAD_BOTTOM}px`;
    world.appendChild(bandEl);
  }

  const out = [];
  for (const band of bands) {
    for (const p of band.placed) {
      const { el, node } = built.get(p.id);
      const x = FLOW_LEFT + p.x;
      const y = FLOW_TOP + band.y + p.y;
      el.style.cssText = `left:${x}px;top:${y}px;width:${p.w}px;height:${p.h}px`;
      world.appendChild(el);
      // `h` — висота КАДРУ без голови, як і в сітці: `fitAll` і Task 9 рахують від неї.
      // `raw` — вузол у сирому `flow.json`, тобто те місце, куди драг пише `pos`.
      out.push({ id: node.key, page: node.page, state: node.state ?? null, el,
                 h: p.h - HEAD, x, y, raw: node[RAW_NODE] ?? null });
    }
    drawEdges(band);
  }

  /* Підписи смуг — ОСТАННІМИ, окремими дітьми світу, а не всередині підкладки.
     Причина видна оком: у DOM пізніший малюється поверх, а на дрібному зумі кегль
     підпису рахується від масштабу (`--cv-scale`), тобто у світових пікселях підпис
     РОСТЕ і неминуче накриває верх кадрів — і поки він жив у підкладці (тобто ПЕРЕД
     кадрами), кадр зʼїдав його хвіст: на демо-графі блогу з «Читач шукає статтю»
     лишалось «Читач шукає ст». Підняти саму підкладку z-index-ом не можна — вона
     заллє кадри своїм фоном.

     Координати — у світі: ліве поле смуги і третина верхнього. Третина, а не
     середина: підпис росте ВНИЗ (див. стилі), і від верху смуги його треба
     відсунути настільки, щоб на людському зумі він стояв у полі осмислено, але не
     настільки, щоб на дрібному вилізти ВИЩЕ нуля світу — туди камера не дивиться, і
     «вписати все» зрізало б підпис першої смуги. */
  for (const band of bands) {
    if (!band.title) continue;
    const label = document.createElement('div');
    label.className = 'cv-band-title';
    label.style.cssText = `left:${FLOW_LEFT}px;`
      + `top:${FLOW_TOP + band.y - BAND_PAD_TOP + Math.round(BAND_PAD_TOP / 3)}px`;
    // `textContent`, а не `innerHTML`: підпис приходить із `flow.json`, який пишуть
    // руками, — те саме правило, що на підписі кадру й у переліку скарг.
    label.textContent = band.title;
    world.appendChild(label);
  }

  /* Габарит світу — вміст ПЛЮС поля з обох боків: праве й нижнє поле остатньої
     смуги теж частина малюнка, і без них камера зрізала б рівно ту рамку, яку ми
     щойно намалювали. */
  let worldW = FLOW_LEFT + box.w + BAND_PAD_X;
  let worldH = FLOW_TOP + box.h + BAND_PAD_BOTTOM;
  // «Не у флоу» — рядком під смугами, тим самим кадром, лише блідішим.
  if (parsed.orphans.length) {
    /* Подвійний зазор, а не потрійний: над рядком росте вгору його підпис (кегль у
       нього від масштабу, стеля 260px, тобто до ~312px рядка), і подвійного вистачає
       з запасом. Кожні зайві 200px тут — це 200px висоти світу, а «вписати все» на
       демо-задачі стоїть майже впритул до підлоги масштабу. */
    const top = worldH + GAP * 2;
    const title = document.createElement('div');
    title.className = 'cv-orphans-title';
    /* Підпис росте ВГОРУ від цієї лінії (`translateY(-100%)` у стилях): кегль у
       нього теж від масштабу, і рости вниз означало б лізти на кадри рівно на
       дрібному зумі. Місця над рядком — подвійний зазор мінус ці 40px, тобто 360px
       проти щонайбільших ~312px рядка. */
    title.style.cssText = `left:${FLOW_LEFT}px;top:${top - 40}px`;
    // `textContent`, а не `innerHTML`: рядок наш, але правило одне на весь файл.
    title.textContent = t('canvasOrphansHeading', parsed.orphans.length);
    world.appendChild(title);
    parsed.orphans.forEach((p, i) => {
      const { el, h } = cardEl({ key: p.id, label: p.name, published: p.published });
      el.classList.add('cv-orphan');
      const x = FLOW_LEFT + i * (cardW() + GAP);
      el.style.cssText = `left:${x}px;top:${top}px;width:${cardW()}px;height:${h + HEAD}px`;
      world.appendChild(el);
      /* `raw: null` — у графі цієї сторінки НЕМА, тобто драгу нема куди писати
         позицію. Поле лишаємо, щоб запис був тієї самої форми, а `saveNodePos`
         сказав про це вголос, а не збрехав «збережено». */
      out.push({ id: p.id, page: p.id, state: null, el, h, x, y: top, raw: null });
      /* Поля тут не смуги (підкладки в рядка «не у флоу» немає), а КРАЙ СВІТУ:
         камера вписує габарит, і без них останній кадр стояв би врівень із межею. */
      worldW = Math.max(worldW, x + cardW() + BAND_PAD_X);
      worldH = Math.max(worldH, top + h + HEAD + BAND_PAD_BOTTOM);
    });
  }
  flowBox = { w: worldW, h: worldH };
  return out;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
/* Довжина і піврозмах наконечника — у координатах СВІТУ, тобто на дрібному зумі
   він меншає разом із кадрами. Тримати його немасштабованим, як лінію, нічим:
   заливку з-під трансформу не виводить ніщо, а обведений трикутник на 250% зумі
   був би лопухом на волосині. */
const HEAD_L = 26, HEAD_W = 9;
/* Поля плашки під підписом ребра і її заокруглення — у координатах СВІТУ, як і
   кегль підпису: плашка мусить лежати на тексті як лежала, на будь-якому зумі. */
const LABEL_PAD_X = 12, LABEL_PAD_Y = 7, LABEL_RX = 10;

const round1 = (v) => Math.round(v * 10) / 10;
/** Точки → `d`. Числа коротшаємо: 17 знаків після коми ніхто не читає. */
const dOf = (points) => points
  .map(([x, y], i) => `${i ? 'L' : 'M'}${round1(x)},${round1(y)}`).join(' ');

/**
 * Шар стрілок смуги. SVG кладемо У СВІТ, поруч із кадрами: спільний трансформ —
 * єдиний спосіб гарантувати, що стрілка не відʼїде від кадру на зумі чи пані.
 * Ціна: товщина лінії масштабується разом зі світом, тому лінію окремо виводимо
 * з-під масштабу (`vector-effect:non-scaling-stroke` у стилях) — інакше на 6%
 * зумі стрілки зникнуть, а на 250% стануть брусками.
 *
 * Точки ребер уже порахувала чиста розкладка (`flowLayout`) у координатах СМУГИ,
 * тож тут лишається поставити шар туди ж, де стоїть сама смуга, і домалювати
 * наконечники.
 */
function drawEdges(band) {
  if (!band.edges.length) return;
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'cv-edges');
  /* Габарит — рівно габарит смуги, і `top` із тим самим `FLOW_TOP`, що й кадри:
     точки ребер рахувались від верху смуги, а смуга у світі зсунута вниз на
     місце під свій підпис. Без цього доданка весь шар висить на 40px вище за
     граф, і кожна стрілка мимо кадру рівно на цю висоту.

     Ширина ЧИСЛОМ і по вмісту смуги, а не «щедрою» константою (у плані стояло
     40000): `#world` абсолютний, ширини не має — а елемент, ширший за весь світ,
     видно і камері («вписати все» вимагає, щоб жоден шматок світу не лишився за
     краєм — це стереже перевірка I), і будь-кому, хто колись рахуватиме межі по
     DOM. Підпис, що виступає за смугу, тримає `overflow:visible`. */
  const w = Math.max(1, ...band.placed.map((p) => p.x + p.w));
  svg.setAttribute('viewBox', `0 0 ${w} ${band.h}`);
  svg.style.cssText = `left:${FLOW_LEFT}px;top:${FLOW_TOP + band.y}px;`
    + `width:${w}px;height:${band.h}px`;
  /* У світ ДО підписів, а не після всього: плашку під підпис міряє сам браузер
     (`getBBox()` живого тексту — єдиний спосіб знати, скільки місця займе рядок
     цим шрифтом), а міряє він лише те, що справді в документі. У відчепленого
     елемента габарит суцільно нульовий. */
  world.appendChild(svg);

  /* Спершу ВСІ лінії й наконечники, і лише потім усі підписи. У SVG порядок
     документа — це порядок малювання, тож підпис, домальований одразу за своїм
     ребром (як стояло тут раніше), опинявся ПІД лінією наступного ребра: плашка
     має суцільну заливку, і чужа стрілка креслила її наскрізь. Два паси — єдине,
     що робить «підписи поверх усіх ліній» правдою, а не збігом порядку опису. */
  for (const e of band.edges) {
    svg.appendChild(edgePath('cv-edge', dOf(e.points)));
    svg.appendChild(edgePath('cv-arrow', arrowHead(e.points)));
  }

  for (const e of band.edges) {
    if (!e.label) continue;
    /* Підпис — на СЕРЕДИНІ відрізка, і по обох осях: план брав `y` початку
       відрізка, але пряме ребро між кадрами різної висоти похиле, і підпис
       відлітав від нього рівно на піврізниці висот.

       Якого саме відрізка — СЕРЕДНЬОГО. Шлях ребра завжди симетричний (нога,
       стояк, головна лінія, стояк, нога), тож середній відрізок і є тією лінією,
       яку підпис називає: у прямого ребра (2 точки) це сам зазор між колонками,
       у ребра в одній колонці (4) — стояк у зазорі, у довгого (6) — лейн під
       смугою. Індекс писати числом («довге → 1») не можна: довге ребро стало
       шести-точковим, коли стояки лейна пішли в зазори, і підпис із індексом 1
       поїхав би на стояк спуску, за сотні px убік від лейна, який називає. */
    const mid = (e.points.length - 1) >> 1;
    const [x1, y1] = e.points[mid];
    const [x2, y2] = e.points[mid + 1];
    const text = document.createElementNS(SVG_NS, 'text');
    text.setAttribute('x', round1((x1 + x2) / 2));
    text.setAttribute('y', round1((y1 + y2) / 2 - 10));
    text.setAttribute('text-anchor', 'middle');
    // `textContent`, а не `innerHTML`: підпис приходить із `flow.json`, який
    // пишуть руками, — те саме правило, що й на підписі кадру.
    text.textContent = e.label;
    svg.appendChild(text);
    /* ПЛАШКА під підписом — суцільна підкладка, а не «гало» з товстого обведення,
       яке стояло тут до раунду правок 25.08.2026: обведення лишає між літерами
       просвіти фону, і на кадрі підпис читається плямами. Розмір беремо з
       `getBBox()` ПІСЛЯ вставки тексту: ширина рядка залежить від шрифту, а не від
       кількості літер, і вгадувати її означало б або різати підпис, або малювати
       плашку в пів-екрана.
       Порожній габарит буває в одному випадку — холст схований (`display:none`),
       і тоді підпису однаково не видно; малюємо його без плашки, а не з плашкою
       нульового розміру. */
    const box = text.getBBox();
    if (!box.width) continue;
    const plate = document.createElementNS(SVG_NS, 'rect');
    plate.setAttribute('class', 'cv-edge-plate');
    plate.setAttribute('x', round1(box.x - LABEL_PAD_X));
    plate.setAttribute('y', round1(box.y - LABEL_PAD_Y));
    plate.setAttribute('width', round1(box.width + LABEL_PAD_X * 2));
    plate.setAttribute('height', round1(box.height + LABEL_PAD_Y * 2));
    plate.setAttribute('rx', LABEL_RX);
    // Перед текстом: пізніший у документі малюється поверх, а плашка мусить бути ПІД.
    svg.insertBefore(plate, text);
  }
}

function edgePath(cls, d) {
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('class', cls);
  path.setAttribute('d', d);
  return path;
}

/**
 * Трикутник на кінці ребра, повернутий уздовж ОСТАННЬОГО відрізка: у прямого
 * ребра він дивиться в лівий край цілі, у довгого — вгору, бо та лінія приходить
 * знизу, з лейна.
 *
 * Це `<path>` у координатах смуги, а не `<marker>`, як стояло в плані. Маркер
 * живе в `<defs>`, а `<defs>`, `<marker>` і його вміст — елементи БЕЗ бокса:
 * `getBoundingClientRect()` дає їм суцільні нулі, тобто «лівий верхній кут
 * документа». Перевірка I обходить УСІХ дітей світу й вимагає, щоб камера не
 * лишила нікого за краєм, — і на трьох таких нулях червоніє (виміряно). Слабшати
 * перевірку заради невидимих елементів було б розміном справжньої охорони на
 * зручність; звичайний трикутник не коштує нічого і чесно має свій габарит.
 */
function arrowHead(points) {
  const [px, py] = points[points.length - 2];
  const [ex, ey] = points[points.length - 1];
  // Нульова довжина відрізка тут не буває (точки різні), але ділити на неї все
  // одно не можна: одне зіпсоване число дало б `d` з NaN і німий наконечник.
  const len = Math.hypot(ex - px, ey - py) || 1;
  const ux = (ex - px) / len, uy = (ey - py) / len;
  const bx = ex - ux * HEAD_L, by = ey - uy * HEAD_L;
  // Нормаль до напряму — це (-uy, ux): основа трикутника перпендикулярна лінії.
  return `${dOf([[ex, ey], [bx - uy * HEAD_W, by + ux * HEAD_W],
                 [bx + uy * HEAD_W, by - ux * HEAD_W]])} z`;
}

/** Що викинув наш `readFlow` у ЦІЙ побудові графа; у сітці — порожньо. */
let nodeProblems = [];

/**
 * Єдина постійна поверхня скарг на `flow.json`. Саме перелік, а не «граф має
 * помилки»: дизайнер мусить бачити, який вузол зник і чому, інакше полотно
 * виглядає цілим і бреше.
 *
 * Джерел три, і всі троє мусять доходити до людини:
 *   • `flowError` — сервер не дав графа (нечитний файл, відібрані права);
 *   • `problems` серверної перевірки свіжості — джерело, яке доїжджає й тоді,
 *     коли наш розбір узагалі не відбувся (`freshen` викидав їх разом з усім
 *     звітом, і скарга гинула);
 *   • `nodeProblems` — те, що викинув наш `readFlow` під час цієї побудови графа,
 *     і у флоу-виді, і в сітці (`flowNodesForGrid`). Сітка теж мусить: коли
 *     серверна перевірка впала, це тут ЄДИНЕ джерело.
 *
 * Перелік показуємо в ОБОХ видах: скарга про файл, а не про вид, і лічильник
 * «Перезняти» рахує той самий граф навіть коли на екрані сітка. Дублі знімаємо
 * множиною — модуль розбору один, тож рядки з сервера й наші збігаються дослівно.
 */
function paintFlowProblems() {
  const check = checkOf();
  const list = [...new Set([
    ...(flowError ? [flowError] : []),
    ...(check ? check.problems : []),
    ...nodeProblems,
  ])];
  let el = document.getElementById('cv-flow-problems');
  // Нема скарг — нема панелі. Саме тут, ДО створення: інакше порожня рамка
  // висіла б над цілим графом і виглядала б як «щось не так».
  if (!list.length) { el?.setAttribute('hidden', ''); return; }
  if (!el) {
    el = document.createElement('div');
    el.id = 'cv-flow-problems';
    el.className = 'cv-flow-problems';
    canvasEl.appendChild(el);
  }
  el.innerHTML = `<b>${t('canvasFlowProblemsHeading', list.length)}</b><ul>`
    + list.map((p) => `<li>${esc(p)}</li>`).join('') + '</ul>';
  el.hidden = false;
}

function buildCanvas(task) {
  // у «Огляді» кожна картка — сторінка обраної ітерації (picked), а не сама ітерація;
  // теки (kind folder) не показуємо; підсторінка й стани — окремі ряди сітки
  const srcPages = flattenPages(panelPages).filter((f) => f.kind !== 'folder');
  world.innerHTML = '';
  /* Скарги ЦІЄЇ побудови — з нуля: перелік минулого разу (чи іншої ітерації) інакше
     висів би над чистим графом і брехав. Малюємо після побудови, коли `buildFlowView`
     уже сказав, що викинув `readFlow`. */
  nodeProblems = [];
  flowBox = null;
  /* Ряди — теж стан МИНУЛОГО світу, і тримати їх до побудови не можна. Вузьке
     вікно виміряне: `effView()` відступає в сітку, поки не приїхав перелік
     сторінок, тож `resize` між відповіддю й перебудовою встигає покликати
     `fitAll()` — а той порахував би габарит по рядах ІНШОЇ ітерації й вписав
     камеру у світ, якого на полотні немає. Плюс до перебудови ці ряди тримають
     посилання на вузли, які `world.innerHTML = ''` нижче вже знищив. */
  gridRows = [];
  const view = effView();
  /* Камера переживає перебудову. Раніше `buildCanvas` завжди кінчався
     `userMoved = false; fitAll()`, а `render()` у режимі канваса кличуть чекбокс
     «на превью», перемикач режиму коментарів, `gl-sync` і `gl-pull` — тобто
     дизайнера, який зумнувся в кадр, викидало у bird-view будь-яким кліком у
     смузі. `saveNodePos` обходив це в себе; тут той самий обхід став загальним, і
     кол-сайти `render()`, яких ще нема, дістають його безкоштовно.

     Переносимо тільки те, що дизайнер наставив САМ (`userMoved`): камера, яка й
     так у fit, мусить перерахуватись — світ після правки міняє габарит. І тільки
     в межах того самого світу; інакше лишається `fitAll()`, бо стара камера в
     чужих габаритах не значить нічого. */
  const sameWorld = camWorld && camWorld.task === task.id
    && camWorld.it === picked && camWorld.view === view;
  const keep = (userMoved && sameWorld) ? { x: cvx, y: cvy, scale: cvscale } : null;
  /* Світ записуємо ТУТ, до побудови, а не в кінці: усе, чим він визначається, уже
     відоме, і жодна помилка нижче не лишить `camWorld` вказувати на світ, якого
     на полотні вже немає.

     Задачу беремо з `task` — того самого обʼєкта, з якого щойно побудовано
     полотно, а не з окремої змінної модуля: ключ тоді описує РІВНО той світ, що
     на екрані, і синхронізувати його ні з чим не треба. */
  camWorld = { task: task.id, it: picked, view };
  // Курсор-ручка на голові кадру — лише у флоу-виді: у сітці тягати вузли нема
  // куди, `pos` там не має сенсу. Без підказки ручку не знайти: тіло кадру
  // пановане, і виглядає це однаково.
  canvasEl.classList.toggle('cv-flow', view === 'flow');
  /* Сітці потрібні ОБА джерела: дерево — щоб зібрати ряди, плоский `srcPages` —
     щоб звірити граф зі сторінками рівно тим переліком, яким це робить флоу
     (див. `buildGridView`). Флоу з дерева не дістав би нічого. */
  cards = view === 'flow' ? buildFlowView(srcPages) : buildGridView(panelPages, srcPages);
  paintFlowProblems();
  userMoved = false;
  relayoutAll();
  wireCanvas();
  if (keep) {
    camStop();          // цикл, що доїжджає до старої цілі, інакше пише поверх
    /* `userMoved = true` — не лише «щоб наступна перебудова теж перенесла». Це
       зміна поведінки й поза перебудовою: обробник `resize` вписує все лише поки
       `!userMoved`, тож після побічної перебудови розгортання вікна більше не
       перевписує камеру, наставлену рукою. Семантично так і треба — рука її
       наставила й нічого не забувала, — але назвати це треба вголос. */
    cvx = keep.x; cvy = keep.y; cvscale = keep.scale; userMoved = true;
    applyT();
  } else {
    fitAll();
  }
  // Кадри й розкладка нові — точки пінів теж (канал чи ітерація могли змінитись).
  ovc.rebuild();
}

function cardOf(el) { return cards.find((x) => x.el === el?.closest?.('.cv-card')); }
/**
 * Відкрити те, що НА КАДРІ. Саме `c.page`, а не `c.id`: у флоу-виді `id` — ключ
 * знімка (`poshuk~a1b2c3d4`), сторінки з таким іменем не існує, і `loadPages()`
 * мовчки скидала вибір на першу — кадр показував одне, живий вид інше.
 */
function openCard(c) {
  pickedPage = c.page; pickedState = c.state || null; mode = 'single'; render();
}

/**
 * Колонка кадру за його світовим x — тим самим кроком, яким їх ставить розкладка.
 *
 * `FLOW_LEFT` віднімаємо, бо вміст флоу зсунутий на ліве поле смуги. Без цього
 * номер колонки лічився б від краю світу, а не від краю смуги: поки поле менше за
 * піврозміру кроку, `Math.round` це проковтне, але поле й крок задаються окремо, і
 * тиха залежність «поле мусить бути меншим за півкрок» рано чи пізно ламається
 * саме там, де її ніхто не шукає — у записі `pos` на диск.
 */
const colAt = (card) => Math.max(0, Math.round((card.x - FLOW_LEFT) / (cardW() + GAP)));

/** Номер смуги в СИРОМУ `flow.json`, де лежить вузол цього кадру; -1 — немає. */
function bandOf(card) {
  if (!card.raw) return -1;
  const flows = Array.isArray(flowRaw?.flows) ? flowRaw.flows : [];
  return flows.findIndex((f) => Array.isArray(f?.nodes) && f.nodes.includes(card.raw));
}

/**
 * Ряд кадру = скільки кадрів ТІЄЇ Ж смуги і тієї ж колонки стоять вище за нього.
 *
 * Саме тієї ж смуги: кадри лежать у спільному `#world` зі СВІТОВИМИ
 * координатами, смуга їм сусід, а не батько. Без цієї умови (як у плані) вузли
 * сусіднього сценарію і група «не у флоу» лічились би «вище», ряд вийшов би
 * завеликим — і кадр після драгу поїхав би в хвіст колонки, а не туди, куди його
 * поклали.
 */
function rowAt(card) {
  const col = colAt(card), band = bandOf(card);
  return cards.filter((c) => c !== card && c.y < card.y
    && colAt(c) === col && bandOf(c) === band).length;
}

/**
 * Записати руками поставлену позицію вузла у `flow.json`.
 *
 * Позицією В КОЛОНЦІ (`{col, row}`), а не пікселем: інакше перезнятий довший
 * кадр зсунув би всі руками поставлені вузли, і робота дизайнера пропала б без
 * жодної помилки.
 */
async function saveNodePos(card) {
  /* Камеру руками тут більше не тримаємо: `buildCanvas` переносить її сам, поки
     ітерація й вид ті самі, — а драг вузла не міняє ні того, ні того. Два
     механізми на одну відповідальність розійшлися б при першій же правці одного
     з них, і розходження було б тихим: холст стрибав би у «вписати все» рівно
     посеред розкладання графа, тобто саме там, де дизайнер зумнувся. */
  const redraw = () => render();
  /* Кадр не з графа (група «не у флоу») або вузол, якого `readFlow` викинув:
     писати нема куди. Кажемо вголос і перемальовуємо — кадр стане на місце, і
     буде видно ЧОМУ. Мовчазне «Позицію збережено» тут було б найгіршим: наступне
     перезавантаження все повертає, а дизайнер не знає причини. */
  if (!card.raw) {
    toast(t('toastNodeNotInFlow'));
    await redraw();
    return;
  }
  card.raw.pos = { col: colAt(card), row: rowAt(card) };
  let bad = null;
  try {
    const r = await post('/api/flow-save', { it: picked, flow: flowRaw });
    /* Помилку диска сервер віддає ТІЛОМ `{ok:false, error}` зі статусом 200 —
       щоб канвас бачив причину, а не обірване зʼєднання. Отже `post` тут НЕ
       кидає, і без цієї перевірки збій запису виглядав би як успіх: тост
       «збережено», а на диску старий граф. Саме та мовчазна втрата, проти якої
       написано все інше в цій функції. */
    if (r && r.ok === false) bad = r.error || t('errGraphSaveFailed');
  } catch (e) {
    bad = e.message;
  }
  // Перемальовуємо в обох випадках: після вдалого запису кадр стає на свій ряд,
  // після невдалого — вертається туди, де був на диску.
  await redraw();
  // ГУЧНО, як усі сусідні обробники панелі: тост згас би за 3.2 секунди, і втрата
  // роботи лишилась би незауваженою — а вона тут найдорожча.
  if (bad) tell(t('errPositionNotSaved', bad));
  else toast(t('toastPositionSaved'));
}

function wireCanvas() {
  if (canvasEl.dataset.wired) return;
  canvasEl.dataset.wired = '1';
  // На холсті макети заморожені (bare, pointer-events:none). Тягни — рух, колесо — зум,
  // клік по макету — відкрити його в повний розмір (там уже живий інтерактив і коментарі).
  let drag = null;
  // Драг ВУЗЛА — окремий стан від драгу світу: жести різні (ручка проти панорами),
  // і закінчуються різним (запис у файл проти нічого).
  let nodeDrag = null;
  canvasEl.addEventListener('pointerdown', (e) => {
    /* Порядок: спершу гасимо цикл, потім виходимо на кнопці. Це ДЕШЕВА ДРУГА
       охорона, а не несуща — перевірено чотирма варіантами (ревʼю 24.08.2026):
       з перевернутим порядком камера все одно сідає у fit, бо `fitAll()` гасить
       цикл сам. Шкода настає лише коли немає ОБОХ охорон. Тримаємо порядок таким,
       бо він нічого не коштує, але не приписуємо йому чужої заслуги. */
    // Драг має ПЕРЕБИВАТИ живий цикл камери. Інакше звичайний жест «зумнув колесом
    // і одразу потягнув» дає стрибок: цикл ще їде до старої цілі й перезаписує
    // cvx/cvy поверх руки — виміряно ~20-30px у бік, протилежний драгу, і ще
    // кілька кадрів боротьби. До Task 11 цього не було, бо зум застосовувався
    // синхронно за один тік.
    camStop();
    // Кнопка ВСЕРЕДИНІ кадру: не починаємо драг і не забираємо вказівник, інакше
    // холст отримає pointer capture, mouseup прийде на нього, і click народиться
    // на ХОЛСТІ, а не на кнопці — обробник кнопки не вистрілить (виміряно
    // мутаційно), і вона «працює» лише завдяки випадковому шляху через pointerup.
    // Те саме для «Вмістити все» (`#cv-zoom`): без виходу її клік теж народжувався б на холсті.
    if (e.target.closest('.cv-open, .cv-zoom')) return;
    /* Шар коментатора живе в `#canvas` (T-45), тож його події доходять сюди.
       `setPointerCapture` нижче забрав би в піна/панелі і `pointerup`, і
       `click` — клік не дійшов би ніколи (та сама пастка, що з `.cv-open`). */
    if (e.target.closest('[data-comment-layer]')) return;
    /* У флоу-виді голова кадру — РУЧКА вузла, а тіло лишається пановою поверхнею:
       інакше перетягнути полотно, ткнувши в кадр, стало б неможливо, а це основний
       жест холста (по ньому ходять усі живі перевірки). У сітці ручки немає
       взагалі — там кадри розкладає `rowsLayout` рядами сторінок, і `pos` нема куди
       прикласти. Кнопку «Відкрити» відсіяв рядок вище, `camStop()` — теж: цикл
       камери, що доїжджає до старої цілі, інакше пише поверх руки. */
    if (effView() === 'flow' && e.target.closest('.cv-card-head')) {
      const c = cardOf(e.target);
      if (c) {
        nodeDrag = { c, sx: e.clientX, sy: e.clientY, ox: c.x, oy: c.y, moved: false };
        canvasEl.setPointerCapture(e.pointerId);
        return;
      }
    }
    drag = { sx: e.clientX, sy: e.clientY, ox: cvx, oy: cvy, moved: false, t: e.target };
    canvasEl.setPointerCapture(e.pointerId);
    canvasEl.classList.add('dragging');
  });
  canvasEl.addEventListener('pointermove', (e) => {
    if (nodeDrag) {
      const dx = e.clientX - nodeDrag.sx, dy = e.clientY - nodeDrag.sy;
      // Той самий поріг, що в панорами: тремтіння руки на кліку не сміє вважатись
      // перетягуванням і писати `pos` у файл.
      if (Math.abs(dx) + Math.abs(dy) > 4) nodeDrag.moved = true;
      if (!nodeDrag.moved) return;
      /* Рух миші переводимо у СВІТОВІ координати (`/cvscale`), інакше на дрібному
         зумі кадр тікає від курсора: у «вписати все» масштаб буває 0.06. */
      nodeDrag.c.x = nodeDrag.ox + dx / cvscale;
      nodeDrag.c.y = nodeDrag.oy + dy / cvscale;
      nodeDrag.c.el.style.left = `${nodeDrag.c.x}px`;
      nodeDrag.c.el.style.top = `${nodeDrag.c.y}px`;
      ovc.tick();   // піни їдуть разом із вузлом, а не чекають дропу (ревʼю T-45, D5)
      return;
    }
    if (!drag) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; userMoved = true; }
    cvx = drag.ox + dx; cvy = drag.oy + dy; applyT();
  });
  canvasEl.addEventListener('pointerup', () => {
    if (nodeDrag) {
      const { c, moved } = nodeDrag;
      nodeDrag = null;
      /* Клік без руху = відкрити, рівно як на тілі кадру. Голова ручкою бути не
         перестала, але тиснути в підпис і не отримати нічого — це втрата наявної
         поведінки, а не нова фіча. */
      if (moved) saveNodePos(c); else openCard(c);
      return;
    }
    if (!drag) return;
    canvasEl.classList.remove('dragging');
    // клік без руху = відкрити; у режимі коментування цей клік — коментатора (етап 2 T-45)
    if (!drag.moved && !commentArmed) { const c = cardOf(drag.t); if (c) openCard(c); }
    drag = null;
  });
  /* Скасований жест (системний свайп, вирване вікно) не сміє лишати ручку в руці:
     інакше наступний рух мишею БЕЗ кнопки тягне кадр, а `pointerup` пише позицію
     у файл. Панорами це не стосується — вона лише домалює трансформ до наступного
     `pointerdown`, на диск не пише нічого. */
  canvasEl.addEventListener('pointercancel', () => { nodeDrag = null; });
  // Кнопка живе на `click`, а не на `pointerup` холста: `click` народжується і від
  // Enter/пробілу, тому кнопка працює й з клавіатури, а не лише під мишею.
  canvasEl.addEventListener('click', (e) => {
    const btn = e.target.closest('.cv-open');
    if (!btn) return;
    const card = cardOf(btn);
    if (card) openCard(card);
  });
  canvasEl.addEventListener('wheel', (e) => {
    /* Колесо над панеллю скарг — це ЇЇ прокрутка, а не рух полотна: у панелі є
       стеля висоти й власний скрол, а `preventDefault` нижче забрав би в неї
       колесо цілком — і скарги за стелею стали б недосяжні, тобто стеля просто
       ховала б частину переліку. Панель лежить у канвасі (щоб не їздити зі
       світом), тому її подія сюди й доходить. */
    if (e.target.closest?.('#cv-flow-problems')) return;
    /* Колесо над панеллю коментатора — ЇЇ прокрутка; над піном — рух і зум полотна, як
       над кадром: пін не сміє красти основний жест. Справжня ціль — всередині
       shadow root, тому `composedPath()[0]`, а не ретаргетований `target`. */
    if (e.target.closest?.('[data-comment-layer]') && !e.composedPath()[0]?.closest?.('.cp')) return;
    e.preventDefault(); userMoved = true;
    const r = canvasEl.getBoundingClientRect();
    /* Рахуємо від ЦІЛІ, якщо цикл ще їде, а не від того, де камера зараз. Інакше
       щиглики не накопичуються: кожен новий рахується від позиції, яку камера вже
       покинула, і вони частково гасять один одного. Виміряно на справжньому графі
       блогу: ті самі 12 щигликів давали 10.0× повільно (з доїздом між ними) і лише
       1.81× швидко — розбіжність у 5.5 раза, тобто флік трекпадом виглядав як
       мертвий. Один щиглик після зупинки не змінюється: тоді `camTarget` порожній
       і формула та сама.

       Ціль тепер буває не лише зумом, а й перельотом до кадру — тобто колесо
       посеред перельоту зумить навколо курсора В ЦІЛЬОВІЙ камері, а не в тій, що
       на екрані, і точка під курсором трохи зʼїде. Це свідомий обмін: рахувати
       від того, де камера ЗАРАЗ, ламає накопичення щигликів (перевірка P,
       розбіжність була 5.5 раза), а зʼїзд на пів секунди перельоту людина
       довертає тим самим колесом. */
    const w = wheelIntent(e, r.height);
    if (w.kind === 'pan') {
      /* Рух — МИТТЄВО, тим самим шляхом, що й тягнення мишею (`cvx/cvy` + `applyT`),
         а не через `camTo`: згладжування (~90мс «хвіст») на трекпаді, де події йдуть
         щокадру, давало б відчуття, що полотно пливе за пальцями. Накопичення при
         цьому лишається правильним: якщо камера ще їде (зум чи переліт), зсуваємо
         на (dx, dy) і ПОТОЧНУ позицію, і ЦІЛЬ — цикл доїде туди, куди їхав, але вже
         зі зсувом, без стрибка, і наступний зум рахується від сумісної цілі. */
      const now = panBy({ x: cvx, y: cvy, scale: cvscale }, w.dx, w.dy);
      cvx = now.x; cvy = now.y;
      if (camTarget) camTarget = panBy(camTarget, w.dx, w.dy);
      applyT();
      return;
    }
    const from = camTarget || { x: cvx, y: cvy, scale: cvscale };
    camTo(zoomAt(from, { cx: e.clientX - r.left, cy: e.clientY - r.top, delta: w.delta }));
  }, { passive: false });

  // Вписати заново при зміні розміру вікна: без цього розгорнуте вікно лишає
  // полотно в куті на тому масштабі, який був порахований для маленького.
  addEventListener('resize', () => { if (!userMoved && !homeOpen) fitAll(); });
}

/* ===== ⌘K палітра команд (Task 6 Плану B) =====
 *
 * Проводка `app/shell-palette.js`: `paletteActions`/`paletteHTML`/
 * `paletteListHTML`/`keysHTML` — чисті функції реєстру й розмітки (жодного
 * DOM, жодного слухача, див. шапку модуля); усе, що ТУТ, — стан і виконання,
 * той самий поділ, що вже стоїть для смуги (`bar-model.js`/`shell-bar.js`) і
 * панелі. Виконання дії йде через ТІ САМІ `BAR_ACTIONS`/`PANEL_ACTIONS`
 * (Task 3/4) — палітра не несе другої реалізації жодної з них.
 *
 * ── Драбинка Escape: чому два ОКРЕМІ слухачі, а не один ────────────────────
 * Палітра/довідка клавіш закриваються СВОЇМ, окремим document-слухачем У
 * ФАЗІ ЗАХОПЛЕННЯ (`{capture:true}` — третій аргумент нижче), а не бульбашки,
 * як лишається чинний закривач дропдауна смуги (Task 3, вище за файлом).
 * Причина — та сама, що вже документує `app/ask.js` (`overlay()`, коментар
 * над `onKey`): `comment-layer.min.js` вішає СВІЙ обробник `Escape` в фазі
 * захоплення НЕ лише на iframe макета, а й на `window` БАТЬКІВСЬКОГО
 * документа (конструктор іде вгору по `i.parent`, поки не впреться в
 * себе-таки, — цей файл сюди пише) і, коли коментування заморожене
 * (`freeze`) чи відкрите вікно вводу/лайтбокс/панель, гасить подію
 * (`stopImmediatePropagation`) РАНІШЕ, ніж вона дійде бодай до фази
 * бульбашки на `document`. Бульбашковий слухач у ТАКИХ станах Escape не
 * побачив би ВЗАГАЛІ — рівно тому чинний закривач дропдауна (бульбашка)
 * ніколи не намагався перебити коментатора: він просто не встигав.
 *
 * Слухач на `document` у фазі захоплення стоїть МІЖ `window`-захопленням
 * коментатора і рештою документа: якщо коментатор гасить подію (заморожене
 * коментування, відкрите вікно вводу) — наш слухач її НЕ бачить, і палітра
 * лишається чіпляти лише Escape, вільний від конфлікту, — рівно вимога
 * задачі «не сміє перебивати Escape коментатора». Якщо коментатор НЕ гасить
 * (озброєне, але не заморожене коментування — `_armComment(false)` тоді
 * виконується, а подія летить далі) — наш слухач усе одно спрацьовує, і
 * палітра закривається РАЗОМ із розброюванням коментатора на той самий
 * натиск; це не нова вада ЦІЄЇ задачі, а вже наявна поведінка чинного
 * закривача дропдауна в тому самому стані (перевірено читанням
 * `comment-layer.min.js`, розділ звіту).
 *
 * Порядок самої драбинки («палітра → дропдаун») тримається на природному
 * порядку фаз, а не на ручному `if/else` в одному спільному обробнику:
 * capture ЗАВЖДИ виконується РАНІШЕ за bubble для того самого натиску, тож
 * поки `paletteOverlay` не `null`, наш `stopPropagation()` не дає Escape-у
 * дійти до бульбашкового закривача `openDd` — другий крок драбинки бачить
 * Escape лише тоді, коли перший уже нічого не закрив. Відкриття палітри
 * (`openPalette`) саме чистить `openDd` (нижче) — тому насправді обидва
 * ніколи не стоять відкритими одночасно, і про порядок фаз дбати доводиться
 * лише про людське око, не про реальну гонку.
 *
 * ── Мова інтерфейсу ──────────────────────────────────────────────────────
 * `setLang()`/`getLang()` — `i18n.js` (чистий модуль, без сховища за
 * патерном `viewport.js`); запис у `localStorage` під `LANG_KEY` і повний
 * перемальовок трьох поверхонь (`paintBar`/`renderPanel`/`paintInsp`) —
 * тут, у `switchLang`. Дія `act:"lang"` СВІДОМО не лежить у `BAR_ACTIONS`/
 * `PANEL_ACTIONS`: вона не належить ні смузі, ні панелі, а самому
 * застосунку — додавати її в одну з двох мап означало б брехати, чия це дія.
 */

let paletteOverlay = null; // null | 'pal' | 'keys'
let palQuery = '';
let palCursor = 0;
let overlayEl = null;

/** Стан для `paletteActions()` — той самий рядок думки, що `barState()`/
 *  `panelState()`: чиста функція, лише читає модульні змінні й останній
 *  успішний `curTask`. Докладний опис полів — докстрінг `paletteActions`
 *  у `shell-palette.js`. */
/** Тип і місце вузла, на який діють команди дерева (`treeTarget`). */
function paletteTreeTarget() {
  const id = treeTarget();
  const f = id ? flattenPages(panelPages).find((x) => x.page.id === id) : null;
  return { pickedKind: f ? f.kind : null, pickedHasParent: !!f?.parent,
    pickedHasChildren: (f?.page.children ?? []).length > 0, selCount: panelSel.size };
}
function paletteState() {
  const st = barState();
  return {
    mode: st.mode, view: st.view, hasIteration: st.hasIteration,
    homeOpen: st.homeOpen,
    homePage: st.homePage,
    pagesError: st.pagesError, flowRaw: st.flowRaw, flowError: st.flowError,
    published: st.published, iterPub: st.iterPub, pagePub: st.pagePub,
    figmaBusy: st.figmaBusy,
    pickedPage,
    ...paletteTreeTarget(),
    gl: st.gl, glBrand: vcsBrand(st.glLabel, st.space), iterLabel: st.iterLabel,
    shots: curIter() ? shotsState() : null,
    lang: getLang(),
    canInstall: pwa.canInstall(),
    standalone: pwa.isStandalone(),
    /* Простори для ⌘K: МАСИВ лише коли шар увімкнено (`off` / не питали — `undefined`,
       і пунктів просторів нема зовсім, а не «Новий простір…» без реєстру). `space` —
       вимикач: синк із git палітра показує за роллю `vcs` (`capabilities.vcs`), публікацію й командний канал — за їхніми
       постачальниками (`capabilities.publish`/`capabilities.comments`). */
    spaces: spacesResp && !spacesResp.off ? spacesResp.spaces : undefined,
    spaceId: st.space?.id ?? null,
    space: st.space ? { id: st.space.id, capabilities: st.space.capabilities, compat: st.space.compat } : null,
    update: st.update,
  };
}

/** Перемкнути мову інтерфейсу, записати в `localStorage`, перемалювати три
 *  поверхні шкаралупи. Викликається лише з палітри (`act:"lang"`), але
 *  оголошена іменованою функцією, а не інлайном у `execPaletteAction`, —
 *  щоб мутація «забув перемалювати панель/інспектор після зміни мови» була
 *  видима одним рядком, а не похована в гілці виконання. */
/* Підпис і підказка полотна «Огляду»: текст ставить код, а не розмітка, щоб мова перемикалась без перезавантаження. */
function paintCanvasChrome() {
  const hint = document.getElementById('canvas-hint');
  if (hint) hint.textContent = t('canvasHint');
  if (zoomEl) { zoomEl.title = t('fitAll'); zoomEl.setAttribute('aria-label', t('fitAll')); }
}
paintCanvasChrome();
// «Вмістити все»: як після перемикання вигляду — камера знову слідкує за вікном.
if (zoomEl) zoomEl.addEventListener('click', () => { userMoved = false; fitAll(); });

function switchLang(v) {
  if (v === getLang()) return;      // дропдаун-пункт і так вимкнений, але подвійна безпека дешева
  setLang(v);
  try { localStorage.setItem(LANG_KEY, v); } catch (e) {}
  toast(t('langDone'));
  paintBar(); paintClaude(); renderPanel(); paintInsp(); paintCanvasChrome();
  cmtEl.setAttribute('aria-label', t('cmtTitle')); paintComments();
  /* Екран «Задачі» — окремий вузол зі своєю розміткою: без цього він лишався б
     старою мовою, поки його щось не змусить перемалюватись. */
  if (homeOpen) paintHome();
  /* Відкрита бічна панель «Підключення» — теж окремий вузол. У розмітку секрети не пишуться ніколи, тож введені
     повертаються в поля ВЛАСТИВІСТЮ `.value` (як при порожньому обовʼязковому полі): зміна мови не стирає набране. */
  if (cnDrawer && !cnDrawer.busy) {
    const cur = readCnForm(cnDrawerNode());
    cnDrawer.form = { ...cur, secrets: {} };
    paintCnDrawer();
    restoreCnSecrets(cur.secrets);
  }
}

function onOverlayClick(ev) {
  const closeBtn = ev.target.closest('[data-act="closeoverlay"]');
  if (closeBtn && !ev.target.closest('[data-stop]')) { closeOverlay(); return; }
  const it = ev.target.closest('[data-act="pal"]');
  if (it && !it.disabled) {
    const list = filterActions(paletteActions(paletteState()), palQuery);
    execPaletteAction(list[+it.dataset.val]);
  }
}

/** Контейнер оверлея створюється РАЗ (як `#pages-panel` у `renderPanel()`) і
 *  переживає відкриття/закриття — слухачі вішаються рівно один раз, а не на
 *  кожен `paintOverlay()`. */
function ensureOverlayEl() {
  if (overlayEl) return overlayEl;
  overlayEl = document.createElement('div');
  overlayEl.addEventListener('click', onOverlayClick);
  /* Живе фільтрування живить ЛИШЕ `.pal-list` (`repaintPaletteList`), не
     весь оверлей: пересотворення `<input>` на кожен символ скидало б фокус
     і позицію курсора в полі — той самий клас пастки, що вже стереже
     `syncViewportBar()` для `vpw`. */
  overlayEl.addEventListener('input', (ev) => {
    if (ev.target.id !== 'palq') return;
    palQuery = ev.target.value; palCursor = 0;
    repaintPaletteList();
  });
  document.body.appendChild(overlayEl);
  return overlayEl;
}

function repaintPaletteList() {
  const list = overlayEl?.querySelector('.pal-list');
  if (!list) return;
  list.innerHTML = paletteListHTML(paletteActions(paletteState()), palQuery, palCursor);
}

function paintOverlay() {
  if (!paletteOverlay) { overlayEl?.remove(); overlayEl = null; return; }
  const el = ensureOverlayEl();
  if (paletteOverlay === 'keys') { el.innerHTML = keysHTML(); return; }
  el.innerHTML = paletteHTML(paletteActions(paletteState()), palQuery, palCursor);
  document.getElementById('palq')?.focus();
}

function openPalette() {
  /* Під відкритим діалогом (`.cv-ask-scrim`: форма простору, «Нова задача», питання) палітра не
     відкривається: підкладка ловить кліки, але не клавіатуру, і ⌘K поверх зайнятої форми
     дозволив би виконати дію палітри (перемкнути простір) просто під запитом, що вже летить. */
  if (askUp()) return;
  document.getElementById('cv-ctx')?.remove(); // контекстне меню сторінки не сміє висіти під палітрою
  paletteOverlay = 'pal'; palQuery = ''; palCursor = 0;
  if (openDd) { openDd = null; paintBar(); }    // дропдаун смуги закритий ДО відкриття — драбинці нема з чим змагатись
  paintOverlay();
  /* Перелік просторів у палітрі — свіжий, як і в дропдауні: малюємо одразу з відомим,
     перемальовуємо список, коли відповідь прийде (якщо палітра ще відкрита). */
  loadSpaces().then(() => { if (paletteOverlay === 'pal') repaintPaletteList(); });
}
function openKeys() { paletteOverlay = 'keys'; paintOverlay(); }
function closeOverlay() { paletteOverlay = null; paintOverlay(); }

/**
 * Виконати обрану дію. `navOnly` — три пункти `gGo` без `act` (шапка
 * `shell-palette.js`): виконує САМ `app.js`, тим самим станом, яким керує
 * клік по крихті/панелі (`openDd`/`panelCollapsed`), а не другою розміткою
 * дропдауна. `act:"lang"` — див. докстрінг секції вище. Решта — пряме
 * звернення до `BAR_ACTIONS`/`PANEL_ACTIONS`, БЕЗ жодної логіки поміж:
 * забути тут якийсь `act` означає забути в РЕЄСТРІ (`shell-palette.js`), а
 * не тут — тому цей диспетчер такий короткий.
 */
function execPaletteAction(a) {
  if (!a || a.disabled) return;
  closeOverlay();
  if (a.navOnly) {
    if (a.id === 'go-iter') { openDd = 'iter'; paintBar(); }
    else if (a.id === 'go-pages') { setPanelCollapsed(false); }
    return;
  }
  if (a.act === 'lang') { switchLang(a.val); return; }
  /* Встановлення — теж дія самого застосунку (як мова): викликається прямо з
     жесту (клік/Enter у палітрі), без якого Chrome відхилить `prompt()`. */
  if (a.act === 'pwainstall') { pwa.install(); return; }
  (BAR_ACTIONS[a.act] || PANEL_ACTIONS[a.act])?.(a.val);
}

document.addEventListener('keydown', (ev) => {
  const meta = ev.metaKey || ev.ctrlKey;
  if (meta && ev.key.toLowerCase() === 'k') {
    ev.preventDefault();
    openPalette();
    return;
  }
  /* ⌘G / Ctrl+G — «загорнути в теку». Не в полі вводу й не під відкритим
     діалогом чи палітрою: там це «знайти далі»/звичайний набір. */
  if (meta && !ev.shiftKey && !ev.altKey && ev.key.toLowerCase() === 'g'
      && !homeOpen && !paletteOverlay && !askUp()
      && !ev.target.closest?.('input,textarea,[contenteditable]')) {
    /* Спершу рахуємо ціль: нема що групувати — гарячу клавішу браузера
       («знайти далі») не відбираємо. Автоповтор не запускає другу теку. */
    if (!groupTargetIds(panelSel, pickedPage).length) return;
    ev.preventDefault();
    if (ev.repeat) return;
    groupSelection();
    return;
  }
  if (paletteOverlay === 'pal') {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      const list = filterActions(paletteActions(paletteState()), palQuery);
      const max = Math.max(0, list.length - 1);
      palCursor = Math.max(0, Math.min(max, palCursor + (ev.key === 'ArrowDown' ? 1 : -1)));
      repaintPaletteList();
      overlayEl?.querySelector('.pal-it--cur')?.scrollIntoView({ block: 'nearest' });
      return;
    }
    if (ev.key === 'Enter') {
      ev.preventDefault();
      const list = filterActions(paletteActions(paletteState()), palQuery);
      execPaletteAction(list[palCursor]);
      return;
    }
    return; // палітра відкрита — інші клавіші (зокрема «?») їй не належать, фокус усе одно в полі пошуку
  }
  if (paletteOverlay) return; // довідка клавіш відкрита — так само не мовчить лише про Escape (капчер-слухач нижче)
  /* Глибока перевірка (як у рамці): на «Огляді» форма коментатора — у тіньовому DOM ЦЬОГО документа, і `ev.target` тут —
     її хост (DIV), а не textarea: без цього «с»/«р» у тексті коментаря перемикали б панель і знищували форму. */
  if (typingIn(ev, document)) return;
  if (!meta && !ev.altKey && ev.key === '?') { openKeys(); return; }
  /* Екран «Задачі»: усе нижче — ⌥M, ⇧⌘\\, ⌘\\ — діє на задачу, якої людина зараз
     не бачить (режим, чистий перегляд, панель під екраном). ⌘G вище має власну
     умову на `homeOpen`; `I`/`M` інспектора й клавіші коментатора живуть у рамці,
     яка схована й фокус не бере. */
  if (homeOpen) return;

  /* Коментарі (0.26.0): `C` — панель (і режим коментування), `H` — сховати піни, поки панель відкрита, `Esc` — закрити.
     Після `typing` вище: у полі пошуку панелі `c` друкується. */
  const cmtFree = !ev.repeat && !ev.isComposing && !ev.defaultPrevented && !shellModalOpen();
  if (cmtFree && !meta && !ev.altKey && !ev.shiftKey && (ev.key.toLowerCase() === 'c' || ev.code === 'KeyC')) {
    ev.preventDefault(); BAR_ACTIONS.comments(); return;
  }
  if (cmtFree && cmtOpen && !meta && !ev.altKey && !ev.shiftKey && (ev.key.toLowerCase() === 'h' || ev.code === 'KeyH')) {
    ev.preventDefault(); BAR_ACTIONS.cmtpins(); return;
  }
  /* Esc при питанні «Видалити назавжди?» (етап В) знімає лише питання — панель лишається. */
  if (cmtFree && cmtOpen && cmtDelAsk && ev.key === 'Escape') { ev.preventDefault(); closeDelAsk(true); return; }
  if (cmtFree && cmtOpen && ev.key === 'Escape') { setCommentsOpen(false); return; }

  /* ⌥M (режим) і ⌘\ (панель шарів) — акорди із ЗАТВЕРДЖЕНОГО прототипу
   * (`docs/proto/shell.html`, обробник клавіш: `ev.altKey && k === 'm'` і
   * `(ev.metaKey || ev.ctrlKey) && ev.key === '\\'`). Перенос у бій привіз
   * їхні ПІДКАЗКИ — і в довідку клавіш, і в колонку `kbd` реєстру палітри, —
   * а обробники загубив: до 02.09.2026 їх не було НІ ДЕ (`grep altKey` по
   * `app/*.js` давав один рядок, і той про «?»). Довідка обіцяла клавіші,
   * яких не існує, — рівно те, чого цей інструмент не сміє робити. Тепер
   * обіцянка виконується, а `tests/shell-palette.test.mjs` стереже інваріант
   * «кожна підказка має обробника» — односторонньо і свідомо: підказка без
   * обробника це брехня, обробник без підказки — лише незадокументована
   * зручність (там же, у докстрінгу того тесту, записано чому).
   *
   * ⛔ Порядок і гейти тут не косметика:
   *   · стоять ПІСЛЯ `paletteOverlay`-виходу — при відкритій палітрі клавіші
   *     належать їй, не екрану (той самий вибір, що для «?»);
   *   · стоять ПІСЛЯ `typing` — інакше ⌥M у полі ширини вьюпорта
   *     перемикав би режим замість набору;
   *   · Escape не чіпають узагалі — драбинка (докстрінг секції вище) лишається
   *     цілою;
   *   · з коментатором і інспектором конфлікту немає СТРУКТУРНО: обидва
   *     виходять зі свого обробника першим же рядком, якщо натиснуто
   *     `metaKey||ctrlKey||altKey` (`_keyHandler` у `comment-layer.min.js`,
   *     `_onKey` у `vendor/inspector.js`), тож їхні власні `C`/`P`/`H` та
   *     `I`/`M` живуть у голих літерах і на ці два акорди не претендують.
   *
   * `ev.code` поруч із `ev.key` — не подвійна перевірка про запас, а два різні
   * розкладки-випадки: на macOS ⌥M віддає `key:'µ'` (Option — модифікатор
   * ВВОДУ, не лише прапорець), а українська розкладка віддає `key:'ь'`. Обидва
   * лишають `code:'KeyM'`. Той самий прийом, яким `vendor/inspector.js` уже
   * ловить свої `ш`/`ь` — тільки там перелічені літери, тут `code`. */
  if (ev.altKey && !meta && (ev.key.toLowerCase() === 'm' || ev.code === 'KeyM')) {
    ev.preventDefault();
    BAR_ACTIONS.mode(mode === 'canvas' ? 'layout' : 'overview');
    return;
  }
  /* ⇧⌘\\ — чистий перегляд (fb-01102026-7f7b6d). ПЕРЕД ⌘\\ і з `code`: із Shift
     клавіша дає `key: '|'`, а ⌘\\ нижче явно без Shift — інакше спрацювали б обидва. */
  if (meta && ev.shiftKey && !ev.altKey && ev.code === 'Backslash') {
    ev.preventDefault();
    toggleClean();
    return;
  }
  if (meta && !ev.shiftKey && !ev.altKey && (ev.key === '\\' || ev.code === 'Backslash')) {
    ev.preventDefault();
    PANEL_ACTIONS.panel();
  }
});

/* Escape — капчер, окремим слухачем: причина й наслідки — докстрінг секції
   вище («Драбинка Escape»). */
document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Escape' || !paletteOverlay) return;
  ev.stopPropagation();
  closeOverlay();
}, true);

// Ширина зі сховища мусить лягти у стиль ДО першого рендера: інакше макет
// встигне вималюватись на повну ширину й перекластись, тобто вибраний мобайл
// повернувся б стрибком, а не одразу.
applyViewport();

/* render() нормалізує picked → потім статус GitLab по обраній ітерації.
   `paintBar()` після — легка перемальовка ЛИШЕ смуги: `curTask` уже є
   (перший `render()` відбувся), мережа не потрібна, iframe не чіпаємо. Без
   неї GitLab-дропдаун лишався б порожнім до першої дії, що й так кличе
   `render()`. */
/* `loadTune()` — ПЕРЕД першим рендером, і саме `await`, а не «паралельно»:
   пакет мусить лежати в памʼяті ДО першої правки, інакше та правка запише на
   диск пакет БЕЗ усього, що там уже було. Вікно між стартом і відповіддю
   виглядає невеликим (дизайнер спершу мусить дочекатись макета, увімкнути
   інспектор і запінити елемент), але це саме вікно, а не його відсутність —
   а ціна тут один запит до того ж локального сервера, з якого `render()`
   однаково починається. Сервер лежить — `loadTune` ковтає це сам і не
   затримує нічого. */
loadTune().then(render).then(async () => { await refreshGitlab(); paintBar(); });
