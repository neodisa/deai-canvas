/**
 * Розмітка панелі шарів — стан на вході, рядок HTML на виході, і нічого крім
 * цього: та сама ідіома, що в `shell-bar.js` (Task 2 Плану B) — жодного
 * слухача, жодного звернення до DOM. Проводку (`data-act` → дія) робить
 * `app.js` однією делегацією, як для смуги; контекстне меню сторінки
 * (`pageMenu`, `app.js`) — окремий шар поверх `document.body`, цей модуль
 * його не малює, лише лишає в рядку кнопку-відкривач (`data-act="pagemenu"`).
 *
 * Джерело вигляду — затверджений прототип `docs/proto/shell.html`, функції
 * `renderPanel`/`renderShots`. Дерево (`flattenPages`, фільтр за
 * `expandedPages`) лишається в `app.js`: цей модуль отримує вже ГОТОВИЙ
 * плаский список рядків (`state.rows`) і лише перетворює його на розмітку —
 * рахувати вкладеність тут заново означало б тримати те саме дерево у двох
 * місцях.
 *
 * `state.panel` — `'open' | 'rail'`. Рейка (46px) не «менша копія» відкритої
 * панелі: з дерева там нема нічого, лишаються рівно два контроли — розгорнути
 * назад і зняти кадри (`data-act="panel"/"shoot"`). «＋ сторінку» прибрано:
 * сторінки створює Claude, панель лише організовує (рішення власника
 * 30.09.2026) — єдине «＋» живе в шапці дерева й створює ТЕКУ.
 *
 * `state.readonly` — панель у ОПУБЛІКОВАНОМУ превʼю (План B): статика, де
 * немає ні сервера, ні зʼємки, ні перейменування, і панель потрібна лише як
 * навігація по дереву сторінок. Прапорець, а НЕ другий модуль — і причина не
 * в економії рядків: розмітка рядків, каретки, класи глибини, три іконки,
 * позначка «у превью» й екранування назв мусять бути ДОСЛІВНО ті самі в обох
 * світах. Другий модуль розійшовся б із першим на першій же правці дерева, і
 * розходження було б видно не в тесті, а в чужому браузері за посиланням —
 * тобто там, куди ми не дивимось. Прапорець же прибирає рівно ТРИ речі
 * (`pagemenu`, `newfolder`, весь блок кадрів) і будь-яка правка дерева
 * автоматично доїжджає в обидва світи.
 *
 * Що readonly НЕ прибирає: згортання панелі (`data-act="panel"` у шапці, у
 * заповнювачі `.panel-fill` і на корені рейки). Це робота з місцем на екрані,
 * а не дія над даними — у превʼю рамка так само тісна, як в інструменті.
 */

import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

/**
 * Рядок дерева. `hasKids` дає каретку — і лише тоді; каретки без дітей
 * лишаються порожнім місцем сталої ширини (`.row-caret--none`), інакше назви
 * стрибали б на 18px залежно від того, чи є в сторінки стани.
 *
 * `isState` — це «дитина НЕ організатора» (стан сторінки: порожньо/помилка/
 * завантаження), а не «дитина взагалі» — дитина ОРГАНІЗАТОРА це звичайна
 * вкладена сторінка. Рахує це `app.js` (там і батько відомий), тут — лише
 * вибір іконки з готового прапорця.
 *
 * `data-page` — окремий атрибут-ідентичність рядка, СВІДОМО поруч із
 * `data-act="page" data-val="…"`: перший каже «це рядок сторінки Х» (за нього
 * тримається юніт і живий тест), другий — контракт делегації. Одна дія тут
 * несе обидва без дублювання розмітки.
 */
const MAX_INDENT = 7;   // глибше відступ не росте: у 246px назва інакше зникає

function rowHTML(row, readonly, tabbable = false, filtering = false) {
  /* Глибина йде в `--d`, `aria-level` і клас: чужий/недописаний рядок із
     `depth: undefined` дав би скрізь NaN, а `"2"` — конкатенацію замість суми. */
  const depth = Number(row.depth) || 0;
  const d = Math.min(depth, MAX_INDENT);
  const cls = `row row--d${depth}${row.selected ? " row--sel" : ""}${row.multi ? " row--multi" : ""}`;
  /* Під фільтром гілки розкриті примусово, тож шеврон «розгорнути/згорнути» не
     мав би що робити — кнопки нема, місце лишається (назви не стрибають). */
  const caret = row.hasKids && !filtering
    ? `<button class="row-caret" data-act="toggle" data-val="${esc(row.id)}"
        ${readonly ? "" : 'tabindex="-1"'}
        title="${esc(row.expanded ? t("collapseSubpages") : t("expandSubpages"))}"
        >${ico(row.expanded ? "chevdown" : "chevright", 14)}</button>`
    : '<span class="row-caret row-caret--none"></span>';
  /* `kind` — джерело іконки, коли він є; прапорці лишені для споживачів, що
     ще не передають `kind` (старі юніти, зовнішня оболонка до B4). */
  const raw = row.kind ?? (row.isGroup ? "folder" : row.isState ? "state" : "page");
  /* Білий список, а не лише `esc`: `kind` іде в атрибут і в CSS-селектор
     `[data-kind=…]`, тож чужий JSON не має права вигадати третє значення. */
  const kind = raw === "folder" || raw === "state" ? raw : "page";
  const icon = kind;
  const mark = row.mark
    ? `<span class="dot dot--ok row-mark" title="${esc(t("markPreview"))}"></span>`
    : "";
  /* «Де саме міняє» (ідея 02.09.2026): файли сторінки змінились за останні
     2 хв. Доказ ЗМІНИ з диска, а не заява — тому без прив'язки до статусу. */
  const recent = row.recent ? `<span class="row-recent-dot" title="${esc(t("pageRecent"))}"></span>` : "";
  /* Глибше за MAX_INDENT відступ не росте — рівень каже бейдж (номер з 1). */
  const deep = depth > MAX_INDENT
    ? `<span class="row-deep" title="${esc(t("levelBadge", depth + 1))}">${depth + 1}</span>` : "";
  const cnt = row.count
    ? `<span class="row-cnt"${row.countTitle ? ` title="${esc(row.countTitle)}"` : ""}>${esc(row.count)}</span>` : "";
  /* Нові командні коментарі сторінки — бурштиновий лічильник; окреме поле, не `count` (той про склад теки). */
  const news = row.news
    ? `<span class="row-news" title="${esc(t("rowNews", row.news))}">${row.news > 99 ? "99+" : row.news}</span>` : "";
  /* «⋯» — єдине в рядку, що МІНЯЄ дані (перейменувати / прибрати з превʼю /
     видалити). У статиці за ним нікуди йти, тож кнопка була б обіцянкою, яку
     нічим виконати. Решта рядка лишається байт у байт. */
  const more = readonly ? "" : `<button class="row-more" data-act="pagemenu" data-val="${esc(row.id)}"
      title="${esc(t("pageActions"))}" aria-haspopup="true">${ico("dots", 14)}</button>`;
  /* Перетягування — pointer-подіями в `app.js` (`wirePageDrag`): нативний
     `draggable` перехопив би жест і дав `pointercancel`. */
  /* `row--dN` лишено як гачок для тестів і селекторів, не для вигляду: відступ
     дає `--d`. aria-expanded — лише коли є діти (інакше «листок» обіцяв би
     розгортання) і ЛИШЕ тут, на рядку: кнопка-каретка його не дублює, бо два
     вузли з одним станом читач екрана озвучив би двічі. `tabindex` — roving:
     один рядок на все дерево (0), решта -1, фокус між ними ведуть стрілки. */
  /* У статичному превʼю клавіатурної моделі нема (там немає `app.js`), тож ні
     role, ні tabindex, ні aria-* не лишаємо: розмітка не обіцяє поведінки, якої
     не виконає. `ariaSelected` — вибір для читача, який рахує `app.js` (рядки
     вибору, а коли його нема, — відкрита сторінка); без нього — як виглядає. */
  const sel = row.ariaSelected ?? !!(row.selected || row.multi);
  const aria = readonly ? "" : `role="treeitem" aria-level="${depth + 1}" aria-selected="${!!sel}"`
    + (row.hasKids && !filtering ? ` aria-expanded="${!!row.expanded}"` : "");
  const tab = readonly ? "" : ` tabindex="${tabbable ? 0 : -1}"`;
  return `<div class="${cls}" style="--d:${d}" data-page="${esc(row.id)}" data-kind="${esc(kind)}"
      ${aria}${tab} data-act="page" data-val="${esc(row.id)}">
    ${caret}${ico(icon, 16, "ico row-ic")}
    <span class="row-name">${esc(row.name)}</span>${deep}${cnt}${news}${recent}${mark}
    ${more}
  </div>`;
}

/**
 * Статус секції «Кадри» — ОДНЕ місце, звідки бере і статус-рядок, і підпис
 * кнопки, і клас тривоги: розійшлись би вони, підпис кнопки міг би сказати
 * одне, а рядок над нею — інше про той самий стан.
 *
 * П'ять станів, не чотири: чотири назвала спека Task 4 (кадрів немає / N
 * застаріли / знімаю N з M / манифест не читається), пʼятий («усе свіже» —
 * `stale === 0`, підтверджено сервером) — та сама «усі свіжі», що вже показує
 * прототип. `stale === null` (перевірка ЩЕ НЕ БІГАЛА для цієї ітерації) —
 * ШОСТИЙ, якого в прототипі нема (демо завжди знає точні числа): це типовий
 * стан щойно відкритої задачі чи іншої ітерації в «Макеті» — `freshen()`
 * кличуть лише вхід у «Огляд», а до нього `checkOf()` чесно каже «не знаю».
 * Змішати цей стан із «усе свіже» — та сама брехня, від якої `freshen()`
 * (`app.js`) явно рятує кнопку «Перезняти».
 *
 * `fresh`/`warn` — логічні протилежності В «ОГЛЯДІ»: усе, що НЕ підтверджено
 * свіжим (іде зʼємка, кадрів нема, свіжість невідома, застаріло щось, манифест
 * побитий), варте тривожного кольору. Поза «Оглядом» тривожить лише побитий
 * манифест — див. коментар біля `warn`.
 */
function shotsView(s) {
  const have = s.have > 0;
  const staleKnown = s.stale !== null && s.stale !== undefined;
  const stale = staleKnown ? s.stale : 0;
  const fresh = !s.running && have && staleKnown && stale === 0 && !s.bad;
  /* ⛔ Тривога — лише в «Огляді» (fb-22092026-c74093, спостереження власника:
     «збоку весь час тривожне "оновіть кадри", хоча в "Макеті" воно ні про
     що»). У «Макеті» перевірка свіжості НЕ БІГАЄ взагалі (`freshen()` кличе
     лише вхід в «Огляд»), тож помаранчевий там тривожив про стан, якого ніхто
     не міряв, — та сама брехня інтерфейсу, проти якої йшла хвиля 1.33. Блок
     при цьому НЕ ховаємо: з «Макета» лишається вхід у зʼємку, а рядок чесно
     каже «свіжість ще не перевірялась». Побитий манифест — ЗБІЙ, а не
     свіжість, і кричить у будь-якому режимі.
     `overview !== false`, а не `=== true`: хто не передав режиму (юніти,
     інші споживачі), бачить колишню поведінку. */
  const warn = s.bad || (!fresh && s.overview !== false);

  const line = s.bad ? t("shotsErr")
    : s.running ? t("shotsRun", s.done, s.total ?? null)
      : !have ? t("shotsNone")
        : !staleKnown ? t("shotsUnknown")
          : stale > 0 ? t("shotsStale", stale, s.total ?? s.have)
            : t("shotsFresh", s.total ?? s.have);

  /* Під час прогону кнопка каже «Стоп N/M», а не голе «Стоп»: число — єдине,
     що відрізняє «почалось» від «майже скінчилось», і саме воно вирішує,
     чекати далі чи спиняти. Підпис свідомо короткий («Стоп 12/34», не
     «Зупинити зʼємку») — так було в бою до переписування панелі, і
     переписування загубило лічильник. Знайдено падінням живих A/B/E/F у
     `autoshoot.test.mjs`, де число з кнопки і є вимірюваною величиною.
     «Знімаю…» — вікно між кінцем прогресу й відповіддю сервера: прогону вже
     не видно, але він ще не закритий, і мовчання тут читалось би як «зависло». */
  const label = s.running
    ? (s.done !== null && s.done !== undefined
      ? t("shootStopLabel", s.done, s.total ? `/${s.total}` : "")
      : t("shootCapturingLabel"))
    : !have ? (s.total ? t("shotsTake", s.total) : t("shotsTakeBare"))
      : !staleKnown ? t("shotsUpdateBare")
        : stale > 0 ? t("shotsUpdate", stale)
          /* Застарілих нуль — підпис іде БЕЗ числа. «Оновити кадри (0)» не
             стан, а артефакт підстановки нуля в шаблон із числом: воно
             показує лічильник рівно там, де лічити нічого. */
          : t("shotsUpdateBare");

  const icon = s.running ? "stop" : have ? "refresh" : "camera";
  const pct = s.running && s.total ? Math.round((s.done / s.total) * 100) : 0;
  /* `quiet` — «блок має право змовкнути»: свіжо, нічого не знімається,
     манифест читається. Три доданки, хоч `fresh` уже містить у собі
     `!running` і `!bad`, — свідомо: тихий стан ХОВАЄ кнопку зʼємки, тож
     умова, за якою він настає, мусить читатись сама, не через перехід до
     визначення `fresh` рядком вище. Це не косметика: згорнутий блок, що
     приховав прогін, лишає користувача зʼємкою, яку нічим спинити — той
     самий клас втрати «Стопа», що вже ловився падінням живих A/B/E/F у
     `autoshoot.test.mjs`, лише причина інша (там збій переліку сторінок,
     тут — збережений вибір «згорнуто»). */
  const quiet = fresh && !s.running && !s.bad;
  return { line, label, icon, pct, fresh, warn, quiet, running: !!s.running };
}

/**
 * Секція «Кадри». `open` — чи розгорнув її користувач (`shotsOpen` у стані).
 *
 * Виміряно 02.09.2026 у живому браузері: при повній свіжості блок казав одне
 * й те саме ЧОТИРИ рази — заголовок «Кадри для огляду», рядок «22 кадрів,
 * усі свіжі», ВИМКНЕНУ кнопку «Оновити кадри (0)» і рядок «нічого не
 * застаріло». Коли робити нічого не треба, блок каже це один раз.
 *
 * Порядок доданків в умові нижче несучий: `v.quiet` стоїть ПЕРШИМ, тож будь-
 * яка проблема (застаріле, прогін, побитий манифест) розгортає блок
 * незалежно від збереженого вибору — інакше тихий блок ховав би саме те, про
 * що мусить кричати. Це, а не сама тиша, і є предмет трьох інваріантних
 * юнітів у `tests/shell-panel.test.mjs`.
 */
function shotsHTML(shots, open) {
  const v = shotsView(shots);
  if (v.quiet && !open) {
    /* Іконка `check`, а не `refresh`: рядок не пропонує оновлювати (нічого
       не застаріло), він лише КАЖЕ стан і відкриває решту. */
    return `<div class="shots shots--quiet">
    <button class="shots-quiet" data-act="shotsopen"
      title="${esc(t("shotsQuietWhy"))}">
      ${ico("check", 14)}<span>${esc(t("shotsQuiet", shots.total ?? shots.have))}</span>
    </button>
  </div>`;
  }
  const cls = shots.bad ? "shots-s--bad" : v.warn ? "shots-s--warn" : "";
  /* Заголовок стає КОНТРОЛОМ рівно тоді, коли блок має право змовкнути:
     інакше розгорнутий блок був би дорогою в один бік — тихий рядок його
     відкриває, а закрити його не було б чим, і «опціонально» (слова
     власника) перетворилось би на «один раз і назавжди».
     Коли `quiet` хибний (застаріле, прогін, побитий манифест), заголовок
     лишається звичайним текстом СВІДОМО: кнопка, яка на клік нічого не
     згорне (інваріант вище її не пустить), брехала б про свою дію — і той
     самий живий охоронець «кожен видимий контрол панелі щось робить на
     клік» (`tests/live/shell-panel.test.mjs`) чесно впав би на ній. */
  const head = v.quiet
    ? `<button class="shots-h shots-h--btn" data-act="shotsopen"
      title="${esc(t("shotsHide"))}"><b>${esc(t("frames"))}</b>${ico("chevdown", 12)}</button>`
    : `<div class="shots-h"><b>${esc(t("frames"))}</b></div>`;
  /* Причину «нічого не застаріло» несе ЛИШЕ `title` кнопки. Окремий `<p>` під
     нею був четвертим повтором того самого, і саме він робив блок гучним у
     стані, де робити нема чого. */
  return `<div class="shots">
    ${head}
    <p class="shots-s ${cls}">${esc(v.line)}</p>
    ${v.running ? `<div class="prog"><i style="width:${v.pct}%"></i></div>` : ""}
    <button class="ctl shots-btn${v.warn ? " ctl--warn" : ""}"
      data-act="shoot" ${v.fresh ? "disabled" : ""}
      title="${esc(v.fresh ? t("whyFresh") : v.line)}">
      ${ico(v.icon)}<span>${esc(v.label)}</span></button>
  </div>`;
}

function shotsRailHTML(shots) {
  const v = shotsView(shots);
  return `<div class="shots">
    <button class="icob" data-act="shoot" title="${esc(v.line)}">${ico("camera")}</button>
  </div>`;
}

/**
 * Рейка — ОДНА ВЕЛИКА КНОПКА «розгорнути панель»: у 46px завширшки смужці
 * будь-яке місце, вільне від трьох її контролів, вертає панель. Слова
 * власника: «открывалась тоже на любое место нажав».
 *
 * Обгортка `.panel-rail`, а не атрибут на корені панелі, бо корінь
 * (`#pages-panel`) створює `app.js` — вішати дію звідти означало б проводити
 * одну фічу з двох файлів. Обгортка ж лишається дитиною `.panel`
 * (`display:flex;flex-direction:column`), тому й сама мусить бути такою
 * колонкою — див. `.panel-rail` у `styles.css`.
 *
 * Два контроли рейки (`panel`/`shoot`) обгортка не з'їдає й
 * перевіряти цього не треба: делегація бере НАЙБЛИЖЧИЙ предок із дією
 * (`closest('[data-act]')`, `wirePanelEvents`), а в кожного з трьох дія —
 * своя власна.
 */
function railHTML(state) {
  /* Зʼємка — єдине, що лишається на рейці; у статиці рейка — рівно ОДИН
     контрол (вхід назад): зʼємка там дія над даними. «＋» на рейці немає
     взагалі — організовує панель, сторінки створює Claude. */
  const showActs = state.hasIteration && !state.pagesError && !state.readonly;
  return `<div class="panel-rail" data-act="panel" title="${esc(t("expandPanel"))}">
    <div class="panel-top" style="justify-content:center">
      <button class="icob" data-act="panel" title="${esc(t("expandPanel"))}">${ico("chevright")}</button>
    </div>
    <div class="panel-body"></div>
    ${showActs ? shotsRailHTML(state.shots) : ""}
  </div>`;
}

/**
 * Тіло `.panel-body`: помилка переліку — ПЕРШИМ і ЄДИНИМ (панель, що мовчки
 * лишає стару розмітку під час збою сервера, привчає не вірити панелі), далі
 * — «нема ітерації» / «дерево порожнє» / самі рядки. Три РІЗНІ порожні стани,
 * і жоден не мовчить.
 */
function bodyContent(state) {
  if (state.pagesError) {
    /* `state.pagesError` приходить уже ГОТОВИМ рядком для показу (адаптер
       `panelState()` в `app.js` кладе туди перекладений текст із префіксом,
       а не голе `e.message`) — цей модуль лишень малює, як і все інше в
       `state`. Юніт (`tests/shell-panel.test.mjs`) навмисно годує сюди
       сирий "500" саме тому: перевіряє РЕНДЕР, а не переклад. */
    return `<p class="shots-s shots-s--bad" style="padding:6px 4px">${esc(state.pagesError)}</p>`;
  }
  if (!state.hasIteration) {
    return `<p class="shots-s" style="padding:6px 4px">${esc(t("panelNoIt"))}</p>`;
  }
  if (state.rows.length === 0) {
    /* Порожній ФІЛЬТР — не порожнє дерево: людина шукала й нічого не
       знайшла, «сторінок ще нема» було б неправдою. */
    if (state.filter) {
      return `<p class="shots-s" style="padding:6px 4px">${esc(t("filterNone"))}</p>`;
    }
    return `<p class="shots-s" style="padding:6px 4px">${esc(t("emptyNoPagesBody"))}</p>`;
  }
  /* Стрілка, а не `map(rowHTML)`: `map` віддає другим аргументом ІНДЕКС, і
     прапорцем `readonly` став би він — рядок №0 малювався б інакше за решту. */
  /* Один tab-стоп на все дерево: рядок із `focus`, а коли споживач його не
     позначив — перший, інакше дерево було б недосяжне з Tab. */
  const hasFocus = state.rows.some((r) => r.focus);
  const rows = state.rows.map((r, i) => rowHTML(r, state.readonly, r.focus || (!hasFocus && i === 0), !!state.filter)).join("");
  return state.readonly ? `<div>${rows}</div>` : `<div role="tree">${rows}</div>`;
}

/**
 * Перемальовувана частина панелі: крихти + дерево (або порожній стан). Окремо
 * від `openHTML` НЕ для краси: поле фільтра стоїть ПОЗА цим шматком, і
 * `app.js` на кожне натискання підміняє лише його. Перемалювати все через
 * `innerHTML` означало б знищити `<input>` разом із фокусом, кареткою й
 * IME-композицією — кирилиця не набиралась би. Одне джерело розмітки на
 * повний і на точковий рендер, тож вони не розійдуться.
 */
export function treeBodyHTML(state) {
  return `${crumbsHTML(state)}${bodyContent(state)}`;
}

/**
 * Відкрита панель. Порожнє місце під деревом — ТЕЖ контрол «згорнути
 * панель»: `<div class="panel-fill" data-act="panel">`, остання дитина
 * `.panel-body`. Слова власника: «еще бы хотелось бы, чтобы эта левая панель
 * закрывалась по пустому месту».
 *
 * ⛔ ЖОДНОГО слухача на тлі панелі. Рішення тримається на тому, що делегація
 * (`wirePanelEvents`, `app.js`) бере НАЙБЛИЖЧИЙ предок із дією:
 * `ev.target.closest('[data-act]')`. Тому клік по рядку, каретці, «⋯», «+»,
 * кнопці зʼємки чи тихому рядку кадрів знаходить СВОЮ дію й до панелі не
 * доходить — задарма, без жодної перевірки «а чи не по кнопці я клікнув».
 * Слухач на тлі вимагав би СПИСКУ ВИНЯТКІВ, і кожен новий контрол мусив би
 * до нього дописуватись; забутий рядок означав би панель, що згортається
 * з-під кнопки.
 *
 * Два місця, де порядок несучий:
 *   · заповнювач стоїть ПІСЛЯ дерева й УСЕРЕДИНІ `.panel-body` — саме там і
 *     лежить порожнє місце, бо `.panel-body{flex:1}` забирає всю вільну
 *     висоту. Сусідом до тіла він накрив би нічого;
 *   · блок «Кадри» стоїть ПІСЛЯ заповнювача (нижче) — інакше він поїде вгору
 *     й відліпиться від низу панелі: вільну висоту тепер їсть заповнювач.
 *
 * Стрілка в шапці лишається на місці й з тією ж дією: заповнювач — це
 * зручність для мишки, а не заміна контролу, досяжного з клавіатури.
 */
/** Довгий шлях: перший › … › два останні. */
function squeeze(line) {
  return line.length <= 3 ? line : [line[0], { id: null, name: "…" }, ...line.slice(-2)];
}

/* У фокусі — «Усі шари» як вихід + шлях; без фокуса — лише шлях, і то коли
   він щось додає (з кореня крихти — шум). */
function crumbsHTML(state) {
  if (state.focus) {
    const tail = squeeze(state.crumbs ?? []);
    return `<div class="tree-crumbs">
      <button class="crumb-all" data-act="unfocus">${esc(t("crumbsAll"))}</button>
      ${tail.map((c) => `<span class="crumb-sep">›</span><span class="crumb">${esc(c.name)}</span>`).join("")}
    </div>`;
  }
  const line = state.crumbs ?? [];
  if (line.length < 2) return "";
  return `<div class="tree-crumbs">${squeeze(line)
    .map((c, i) => `${i ? '<span class="crumb-sep">›</span>' : ""}<span class="crumb">${esc(c.name)}</span>`).join("")}</div>`;
}

function openHTML(state) {
  const canAdd = state.hasIteration && !state.pagesError && !state.readonly;
  return `<div class="panel-top">
      <button class="icob" data-act="panel" title="${esc(t("collapsePanel"))}">${ico("chevleft")}</button>
      <span class="panel-title">${esc(t("layers"))}</span>
    </div>
    <div class="panel-body">
      <div class="tree-head"><span>${esc(t("pages"))}</span>
        ${canAdd ? `<button class="icob" data-act="newfolder" title="${esc(t("newFolder"))}"
          >${ico("folderplus", 14)}</button>` : ""}
      </div>
      ${state.hasIteration && !state.pagesError && !state.readonly ? `<label class="tree-filter">${ico("search", 14)}
        <input id="pp-filter" type="search" value="${esc(state.filter ?? "")}"
          aria-label="${esc(t("filterPlaceholder"))}"
          placeholder="${esc(t("filterPlaceholder"))}" autocomplete="off"></label>` : ""}
      <div class="tree-body">${treeBodyHTML(state)}</div>
      <div class="panel-fill" data-act="panel" title="${esc(t("collapsePanel"))}"></div>
    </div>
    ${/* Секція кадрів ховається разом із деревом, коли перелік сторінок не
          прийшов, — і це правильно: лічильник «N з M застаріли» рахується по
          сторінках, тобто без переліку він недостовірний.
          АЛЕ під час активного прогону кнопка каже «Стоп N/M», і це число з
          прогресу зʼємки, а не з переліку. Ховати її означало б лишити
          користувача з прогоном, який нічим спинити: панель перемальовується
          щотакту (700мс), тож транзиєнтний збій переліку забирав «Стоп»
          посеред роботи. Стара панель цього не мала, бо патчила кнопку
          точково (`syncShootBtn`), а не перемальовувала все.
          Знайдено падінням живих A/B/E/F у `autoshoot.test.mjs`.
          А в статичному превʼю (`state.readonly`) не малюється ВЕСЬ блок, не
          лише кнопка: зʼємки там не існує, тож заголовок, рядок стану, прогрес
          і навіть тихий рядок «Кадри · N свіжі» розповідали б глядачеві про
          механізм, якого в його світі немає, — та й «свіжість» кадрів у
          статиці нічим не перевірити. */ ""}
    ${state.readonly ? "" : state.hasIteration && (!state.pagesError || state.shots?.running)
      ? shotsHTML(state.shots, state.shotsOpen) : ""}`;
}

/**
 * `panelHTML(state)`. `state`:
 *   panel: 'open' | 'rail'
 *   hasIteration: boolean
 *   pagesError: string ('' — нема помилки)
 *   rows: [{ id, depth, kind, isGroup, isState, hasKids, expanded, selected, multi,
 *     name, mark, count, countTitle, focus }] (focus — roving tabindex)
 *   filter: string, crumbs: [{ id, name }], focus: { id, name } | null
 *   shots: { bad, running, have, done, total, stale } | null (null лише коли
 *     !hasIteration — рахувати «кадри» нема для чого)
 *   shotsOpen: boolean — чи розгорнув користувач секцію кадрів. ЛИШЕ право
 *     розгорнути тиху секцію: сховати проблему цей прапорець не може, див.
 *     `shotsHTML`.
 *   readonly: boolean — панель у статичному превʼю. Прибирає рівно дії над
 *     даними («⋯», «+», весь блок кадрів); дерево, каретки, іконки, позначку
 *     й згортання панелі лишає незмінними. Відсутній або `false` — панель
 *     інструмента дослівно та сама, що до появи прапорця.
 */
export function panelHTML(state) {
  return state.panel === "rail" ? railHTML(state) : openHTML(state);
}
