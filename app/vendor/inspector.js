/* Інспектор макета — UI. Свій shadow-host, окремий від comment-layer.
   Вантажиться обома снипетами serve.py на РОБОЧОМУ МІСЦІ дизайнера — і в
   аудиторії «Локальні · мені», і в «Проєкт» (`inspector=True` у
   `inject_comment_layer`). У `publish/` його немає й не мусить бути: це
   інструмент дизайнера, а не сторонього глядача. До 02.09.2026 друга
   половина цієї фрази читалась «лише локальним», і так було насправді —
   у режимі «Проєкт» кнопка інспектора в смузі тихо нічого не робила.
   Це ВЕРХНІЙ шар: він тільки малює й ловить події. Жодного рішення про
   токени тут немає — усе, що показується, приходить з inspector-dom.js. */
import { declsFor, describeAll, invalidate, pickWinner, setDsProfile, trail, label } from './inspector-dom.js';
import { between, measure } from './inspector-measure.js';
import { reportHTML } from './insp-report.js';
/* Свій екземпляр i18n — неминучий: оверлей живе в ДОКУМЕНТІ МАКЕТА, тобто в
   іншому модульному графі, ніж оболонка. Мову беремо зі сховища (`dc-lang`,
   origin спільний), а `setLabels` з батьківського вікна лишається сильнішим за
   неї — див. `init` і докстрінг `setLabels`. */
import { LANG_KEY, readStoredLang, setLang, t } from '../i18n.js';
/* База екранування — спільна з оболонкою (`app/esc.js`). Резолвиться крізь ту
   саму межу, що й `../i18n.js` рядком вище: ассети макета віддаються як
   `{origin}/app/vendor`. */
import { esc as escHTML } from '../esc.js';

/* НАПРЯМОК ЗАДАЧІ — з ПАРАМЕТРА ВЛАСНОГО URL (`inspector.js?ds=united`), а
   не з глобальної змінної й не з окремого тега.

   Документ макета про задачу не знає нічого: `profile` лежить у `tasks.json`,
   і бачить його лише сервер, який вставляє цей тег (`serve.py`). Передати
   можна було трьома шляхами, і два з них гірші:
     · окремий `<script>window.__ds=…</script>` — зайвий тег у сніпеті, де
       ПОРЯДОК ТЕГІВ несучий (див. `__clDown` у `serve.py`: банер мусить бути
       першим, це ловили живцем);
     · атрибут на самому тезі — у модулі `document.currentScript` вже `null`,
       тобто довелось би шукати свій тег селектором по всьому документу.
   `import.meta.url` же несе параметр без жодного зайвого байта в розмітці й
   без пошуку в DOM.

   Параметра немає (стороння сторінка, стара розмітка) — напрямок лишається
   невідомим, а невідомий напрямок ВИМИКАЄ звірку з ДС (`setDsProfile`,
   `inspector-dom.js`). Мовчазна звірка проти вгаданої ДС збрехала б про
   кожен токен сторінки. */
try {
  setDsProfile(new URL(import.meta.url).searchParams.get('ds'));
} catch (e) {
  setDsProfile(null);
}

const CL_HOST = '[data-comment-layer]';

/** Чим позначаємо переможця каскаду, який прийшов з атрибута `style`, а не з
 *  правила. `null` тут не годиться: він уже означає «ніхто не виграв» (жодної
 *  декларації не знайшли), а це зовсім інша порада читачеві пакета — шукати
 *  джерело самому. `[style]` же і сам по собі є селектором, який на цьому
 *  елементі справді збігається, тобто не бреше про те, де лежить значення.
 *  Ціна помилки, якщо в макеті колись буде ПРАВИЛО з таким селектором, —
 *  один зайвий погляд не туди; ціна злиття з `null` — мовчазна втрата того,
 *  що правку треба робити в розмітці, а не в CSS. */
const INLINE_RULE = '[style]';

/** Хости ОВЕРЛЕЇВ у документі макета — наш і comment-layer. Кандидатами в
 *  сусіди вони бути не можуть: міряти відстань до власного інструмента це
 *  безглуздя, а дизайнер побачив би число, якого в макеті немає. */
const OVERLAY_HOSTS = '[data-canvas-inspector],[data-comment-layer]';

/** Напрямки лінійки — той самий порядок і ті самі імена, що в `measure`. */
const DIRS = ['top', 'right', 'bottom', 'left'];

/** Екранування ВСЬОГО, що вставляється в розмітку. Імена класів, значення
 *  властивостей та імена токенів приходять із ЧУЖОГО макета — це недовірені
 *  дані, і `<img src=x onerror=...>` у class легко перетворив би тултип на
 *  виконання коду.
 *
 *  ШИРШЕ за спільний `esc` рівно на апостроф, і це лишається свідомим: тултип
 *  збирається шаблонним рядком, де атрибути колись напишуть і одинарними
 *  лапками, а значення сюди приходять з чужого макета — тобто ціна помилки
 *  тут вища, ніж у власній розмітці оболонки.
 *
 *  ⛔ Але таблиця символів більше НЕ переписується: база береться зі спільного
 *  `app/esc.js`, апостроф доліплюється поверх. До 18.09.2026 це була восьма
 *  незалежна копія екранування в `app/` (TD-12), і саме «ця майже така сама,
 *  тільки трошки інша» — найтихіший спосіб розійтися: правка в базових
 *  чотирьох символах не доїхала б сюди ніколи. Порядок склейки безпечний:
 *  `escHTML` уже перетворив `&` на `&amp;`, тож `&` всередині `&#39;`
 *  зʼявляється ПІСЛЯ нього й повторно не екранується — вихід побайтово той
 *  самий, що в старої однопрохідної таблиці (звірено `tests/esc.test.mjs`). */
function esc(v) {
  return escHTML(v).replace(/'/g, '&#39;');
}

/* `COLOR_PROP`/`CSS_SAFE` жили тут до 17.09.2026 — під квадратик кольору у
   власній розмітці звіту. Розмітку малює `insp-report.js`, і барʼєр переїхав
   туди разом із нею; тамтешній `CSS_SAFE` свідомо ВУЖЧИЙ за цей (без `\` і
   без `/`), тож лишити тут другу, слабшу копію означало б лишити й спокусу
   нею скористатись. */

/** Найглибша реальна ціль події: e.target ретаргетиться на хост shadow-дерева,
 *  тож без composedPath() набір тексту в полі comment-layer (воно живе у
 *  своєму shadow DOM) виглядав би як натискання по <div> — і гарячі клавіші
 *  спрацьовували б просто під час друку. */
function deepTarget(e) {
  const path = typeof e.composedPath === 'function' ? e.composedPath() : null;
  return (path && path.length ? path[0] : e.target) || null;
}

/** Активний елемент крізь усі shadow-дерева. */
function activeDeep() {
  let a = document.activeElement;
  while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  return a;
}

function isEditable(n) {
  if (!n || n.nodeType !== 1) return false;
  if (/^(input|textarea|select)$/i.test(n.localName || '')) return true;
  return !!n.isContentEditable;
}

/** Короткий шматок ВЛАСНОГО тексту елемента — одна з незалежних ознак, за
 *  якими Клод потім упізнає блок на вже переписаній сторінці.
 *
 *  Спершу свої текстові вузли, і лише коли їх немає — увесь `textContent`.
 *  Обгортка (`div` навколо картки) власного тексту не має зовсім, і без
 *  запасного шляху вона лишилась би взагалі без текстової ознаки — а саме
 *  обгортки найважче впізнати за підписом (`div.row` у макеті буває двадцять
 *  разів). Порядок саме такий, а не навпаки, бо власний текст — це текст
 *  САМОГО елемента: у картки з вкладеним `<b>` брати заразом і текст дитини
 *  означало б видавати чуже за своє.
 *
 *  80 символів: досить, щоб упізнати абзац, і замало, щоб затягнути в пакет
 *  пів сторінки тексту (`textContent` кореневої обгортки — це вся сторінка).
 *
 *  ⚠️ ЦІНА ФОЛБЕКА, зміряна, а не оцінена. `slice(0, 80)` обмежує РЕЗУЛЬТАТ, а
 *  не роботу: `el.textContent` спершу збирає ввесь текст піддерева, і вже
 *  потім з нього беруть 80 символів. Кличеться це з `identity()`, а її —
 *  `tuneEdits()` на кожну перемальовку панелі під вкладкою КАСКАДУ, тобто
 *  ~кожні 33мс, поки дизайнер тримає стрілку з автоповтором.
 *
 *  Зміряно 18.09.2026 живцем на справжньому важкому лендингу (`bf360`, it6:
 *  712 вузлів, 18 839 символів, 60 КБ розмітки), Chromium, пачками по 2000
 *  викликів (одиничний виклик виміряти не можна — `performance.now()`
 *  округлює до 0.1мс):
 *    · найважча реальна обгортка (252 вузли, 8 064 символи) — 0.031мс;
 *    · увесь `body` (692 вузли, 18 839 символів) — 0.079мс;
 *    · синтетика вдесятеро важча (188 390 символів) — 0.76мс.
 *  Тобто фолбек і Є майже вся вартість `identity()` без властивості — і все
 *  одно вона в 78 разів менша за `report()` (6.2мс), який іде на ТІЙ САМІЙ
 *  перемальовці. Кеша тут свідомо немає: він зрізав би частку відсотка
 *  бюджету, а коштував би новою поверхнею інвалідації (ознаки мусять
 *  зніматись ДО першого інлайн-запису — `tuneSet` в `app/app.js`). */
function ownText(el) {
  let mine = '';
  for (const n of Array.from(el.childNodes || [])) {
    if (n.nodeType === 3) mine += n.nodeValue;
  }
  const src = mine.trim() ? mine : (el.textContent || '');
  return src.replace(/\s+/g, ' ').trim().slice(0, 80);
}

/** Прямокутник, з яким можна рахувати. Живий DOM віддає й `Infinity`, і `NaN`
 *  (бувало на SVG у чужих макетах), а `measure` на такому КИДАЄ — і лінійка
 *  впала б цілком замість пропустити один елемент. */
/** Середина спільної смуги двох відрізків; немає спільної — край якоря
 *  (`fx`/`fy`), щоб кут «Г» сів на його межу, а не в порожнечу. */
function cross(a1, a2, b1, b2, f1, f2) {
  const lo = Math.max(a1, b1), hi = Math.min(a2, b2);
  if (lo < hi) return (lo + hi) / 2;
  return b1 >= a2 ? f2 : f1;          // ціль правіше/нижче — беремо далекий край
}

function finiteRect(r) {
  return !!r && DIRS.every((s) => Number.isFinite(r[s]));
}

/** Внутрішній край елемента: інсет на border і padding, тобто та сама межа, від
 *  якої дизайнер відміряє відступи в макеті.
 *
 *  `null`, якщо коробки нема або вона вивернулась. Це не параноя: `display:contents`
 *  коробки не створює (`getBoundingClientRect` → 0,0,0,0), а computed `padding`
 *  у такого елемента лишається заявленим — інсет дав би `right < left`, і
 *  `measure` кинув би «вивернутий», поваливши лінійку на цілком нормальному
 *  макеті з обгорткою-`display:contents`. */
function innerBox(host) {
  const r = host.getBoundingClientRect();
  if (!finiteRect(r)) return null;
  const cs = getComputedStyle(host);
  const n = (v) => parseFloat(v) || 0;
  const box = {
    top: r.top + n(cs.borderTopWidth) + n(cs.paddingTop),
    right: r.right - n(cs.borderRightWidth) - n(cs.paddingRight),
    bottom: r.bottom - n(cs.borderBottomWidth) - n(cs.paddingBottom),
    left: r.left + n(cs.borderLeftWidth) + n(cs.paddingLeft),
  };
  if (box.right - box.left <= 0 || box.bottom - box.top <= 0) return null;
  return box;
}

/** Просвіт між плашкою й тим, від чого вона відʼїхала (кінець напрямної, край
 *  екрана, сусідня плашка). Три пікселі: більше — і число відривається від своєї
 *  напрямної, менше — і читається як приклеєне. */
const PILL_PAD = 3;

/** Скільки разів пробувати розсунути плашки, що перетнулись навіть після виїзду
 *  за напрямну. Кожен прохід відсуває плашку на пів-розміру, тож чотирьох з
 *  головою: більше означало б, що число поїхало від елемента на сотню пікселів,
 *  і краще лишити перетин, ніж вести дизайнера в нікуди. */
const PILL_PASSES = 4;

/** Прямокутник плашки з її ЦЕНТРІВ: `at` — по осі вимірювання, `mid` — упоперек
 *  (плашка центрована `translate(-50%,-50%)`, тож центри це і є положення). */
function pillRect(p) {
  const half = p.len / 2;
  const side = p.thick / 2;
  return p.vert
    ? { left: p.mid - side, right: p.mid + side, top: p.at - half, bottom: p.at + half }
    : { left: p.at - half, right: p.at + half, top: p.mid - side, bottom: p.mid + side };
}

/** Дві плашки перетинаються ПЛОЩЕЮ. Дотик краями (нуль) перетином не вважаємо:
 *  розсовувати впритул поставлені числа немає за що. */
function pillsHit(a, b) {
  const ra = pillRect(a);
  const rb = pillRect(b);
  return Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left) > 0
    && Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top) > 0;
}

/** Вьюпорт — `clientWidth/Height` кореня, а не `innerWidth/Height`: у скролбара
 *  фіксовані елементи не стоять, і межа для них саме тут. */
function viewportBox() {
  const root = document.documentElement;
  return { top: 0, left: 0, right: root.clientWidth, bottom: root.clientHeight };
}

const STYLE = `
  :host{all:initial}
  .hl,.hl-pad{position:fixed;pointer-events:none;z-index:2147483000;box-sizing:border-box}
  .hl{background:rgba(246,178,107,.28);outline:1px dashed rgba(214,120,0,.9)}
  .hl-pad{background:rgba(147,196,125,.35);outline:1px solid rgba(56,118,29,.7)}
  .tip{position:fixed;z-index:2147483001;max-width:340px;pointer-events:none;
    background:#151a2d;color:#e7ecf5;border:1px solid #2b3350;border-radius:8px;
    padding:8px 10px;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
    box-shadow:0 8px 28px rgba(0,0,0,.45)}
  .tip b{color:#8fb7ff;font-weight:600}
  .tip .dim{color:#8b93ab}
  .btn{position:fixed;left:12px;bottom:16px;z-index:2147483002;
    display:inline-flex;align-items:center;gap:7px;padding:9px 13px;cursor:pointer;
    background:#151a2d;color:#e7ecf5;border:1px solid #2b3350;border-radius:9px;
    font:600 12.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    box-shadow:0 6px 20px rgba(0,0,0,.35)}
  .btn:hover{background:#1d2540}
  /* До 17.09.2026 тут стояло ще й bottom:60px — кнопка піднімалась над чипом
     режимів, що з'являвся на її місці. Чипа більше немає (перемикач режиму
     живе в панелі оболонки, а клавіша M працює скрізь), тож і підстрибувати
     нема від чого. (Лапок-зворотних тут не ставити: це шаблонний рядок.) */
  .btn.on{background:#025cff;border-color:#025cff}
  /* Лінійка. pointer-events:none тут не косметика: плашка лежить РІВНО в
     зазорі, який міряє, тобто просто під курсором. Якби вона ловила події,
     ховер зіскакував би на неї, _pageEl вертав би null — і лінійка міряла б
     не те, на що дизайнер показує. Той самий клас помилки, що оверлей у
     кандидатах. (Бекслеші й лапки-зворотні тут не ставити: це шаблонний рядок.) */
  .rul,.rg,.rlab{pointer-events:none}
  .rg{position:fixed;z-index:2147483001;box-sizing:border-box}
  .rg.v{border-left:1px dashed #025cff}
  .rg.h{border-top:1px dashed #025cff}
  /* Контейнерна напрямна ІНАКША за сусідську: інакше видно тільки «скільки», а
     не «до чого» — а це половина відповіді. */
  .rg.box.v{border-left-style:dotted;border-left-color:#d67800}
  .rg.box.h{border-top-style:dotted;border-top-color:#d67800}
  .rlab{position:fixed;z-index:2147483002;padding:1px 5px;border-radius:4px;
    transform:translate(-50%,-50%);white-space:nowrap;
    font:600 11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
    background:#025cff;color:#fff;box-shadow:0 2px 8px rgba(0,0,0,.35)}
  .rlab.box{background:#2a1c05;color:#ffc98f;border:1px solid #d67800}
  /* Перекриття — окремий вид, і воно мусить ВИГЛЯДАТИ інакше: «12», подане так
     само, як зазор, дизайнер прочитає як відступ. */
  .rg.lap.v{border-left:1px solid #d93025}
  .rg.lap.h{border-top:1px solid #d93025}
  .rlab.lap{background:#2a0606;color:#ffb4ad;border:1px solid #d93025}
  /* Якір парного виміру: стійке підсвічування, яке НЕ зникає, коли дивишся на
     інші елементи — інакше не видно, від чого рахується відстань. */
  .anch{position:fixed;pointer-events:none;z-index:2147483000;box-sizing:border-box;
    outline:2px solid #025cff;background:rgba(2,92,255,.10)}
  .panel{position:fixed;right:16px;top:16px;width:320px;max-height:calc(100vh - 32px);
    overflow:auto;z-index:2147483001;background:#151a2d;color:#e7ecf5;
    border:1px solid #2b3350;border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.5);
    font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;user-select:text}
  /* Плаваюче вікно малює ТОЙ САМИЙ insp-report.js, що й панель оболонки, тож
     і класи тут його — insp-*. Своїх .sec/.row/.tag/.crumbs більше немає:
     друга розмітка під ті самі дані була б другою правдою.
     Значення — власні: app/styles.css у цей shadow не долітає (і не мусить —
     то стилі оболонки, а тут темне вікно поверх чужого макета), тому темні
     кольори лишаються ті самі, що стояли в цьому файлі до 17.09.2026.
     (Лапок-зворотних тут не ставити: це шаблонний рядок.) */
  .panel{padding:10px 12px}
  .insp-crumbs{display:flex;flex-wrap:wrap;gap:2px;align-items:center;
    margin-bottom:10px;color:#8b93ab}
  .insp-crumbs button{background:none;border:0;color:#8fb7ff;cursor:pointer;
    font:inherit;padding:1px 3px;border-radius:4px}
  .insp-crumbs button:hover{background:#222a44}
  .insp-crumbs button:last-child{color:#e7ecf5;background:#222a44}
  .insp-spec{border-top:1px solid #222a44;padding:8px 0}
  .insp-spec:first-of-type{border-top:0;padding-top:0}
  .insp-spec h6{margin:0 0 6px;font:inherit;font-size:10px;font-weight:600;
    letter-spacing:.08em;text-transform:uppercase;color:#6f7996}
  /* Поле СТАЛОЇ висоти — та сама розкладка, що в панелі оболонки (T-39), бо
     малює її той самий insp-report.js. Значення свої: app/styles.css у цей
     shadow не долітає (і не мусить — то стилі оболонки, а тут темне вікно
     поверх чужого макета). */
  .insp-f{display:flex;align-items:center;gap:5px;min-width:0;height:26px;
    padding:0 6px;background:#1b2237;border:1px solid transparent;border-radius:6px}
  .insp-f[data-wide]{grid-column:1/-1}
  .insp-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
  .insp-quad{display:grid;grid-template-columns:repeat(4,1fr);gap:4px}
  .insp-quad .insp-f{padding:0 4px;gap:3px}
  .insp-lbl{margin:0 0 4px;color:#8b93ab}
  .insp-pairlbl{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:0 0 4px;
    color:#8b93ab}
  .insp-grid + .insp-grid{margin-top:6px}
  .insp-grid + .insp-lbl,.insp-quad + .insp-lbl{margin-top:7px}
  .insp-grid + .insp-pairlbl,.insp-quad + .insp-pairlbl{margin-top:7px}
  .insp-ico{flex:none;width:13px;text-align:center;color:#6f7996}
  .insp-quad .insp-ico{width:auto}
  .insp-nm{flex:none;color:#8b93ab}
  .insp-txt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap;color:#e7ecf5}
  .insp-sw{flex:none;width:11px;height:11px;border-radius:2px;border:1px solid #4b5573}
  /* Вирок крапкою — ті самі три рівні, що в панелі оболонки, і тут вони
     законні: малює їх reportHTML, тобто рівно той код, який читає цей
     документ. (Три правила .insp-kind* тут стояли до 18.09.2026 і були
     протилежним випадком — бейдж лінійки, якого цей файл не імпортує.) */
  .insp-dot{flex:none;width:7px;height:7px;border-radius:50%}
  .insp-dot--tok{background:#6ad09d}
  .insp-dot--hard{background:#fbbc55}
  .insp-dot--unk{background:#6f7996}
  /* T-40. Ті самі два вироки про ДС, що в панелі оболонки, і з тією самою
     різницею у вазі (чому — див. .insp-dot--over у app/styles.css). Кнопки
     повернення до токена тут НЕМАЄ і бути не може: проводка живе в
     батьківському вікні, а це інший документ — та сама межа, що в ручок
     тюнера (reportHTML, tunable=false).
     ⛔ ЖОДНОГО ЗВОРОТНОГО АПОСТРОФА В ЦЬОМУ КОМЕНТАРІ: він усередині
     шаблонного літерала STYLE, і перший же такий символ обриває літерал —
     модуль перестає парситись, а CanvasInspector у макеті просто не
     зʼявляється. Спіймано живим тестом 22.09.2026, юніти цього не бачили: у
     них цей файл читається текстом, а не виконується. */
  .insp-dot--over{background:#f37373}
  .insp-dot--offds{background:transparent;box-shadow:inset 0 0 0 2px #8a929c}
  .insp-note{margin:0 0 8px;color:#8a929c}
  .insp-warn{margin:0 0 8px;color:#ffc98f}
  /* Чого тут НЕМАЄ і чому. Бейджа виду виміру (.insp-kind*) у цьому корені не
     буває: його малює kindBadge() з measureHTML(), а цей файл імпортує з
     insp-report.js РІВНО reportHTML — підсумок лінійки їде в панель оболонки,
     не сюди. Разом із ним тут немає й каркаса dl/dt/dd: після T-39 на ньому
     лишився тільки підсумок лінійки, а звіт про елемент малюється полями.
     Ручок тюнера (.insp-num/.insp-pick/.insp-unit) теж немає — і теж не через
     забуті правила: рендерер їх у цьому документі не малює взагалі
     (прапорець tunable, див. _renderPanel). Правило без розмітки гірше за
     відсутнє: воно свідчить про спорідненість, якої немає, і наступний
     читач добудовує її далі. */
  .hidden{display:none !important}
`;

const Inspector = {
  on: false,
  mode: 'cascade',  // 'cascade' — каскад і токени, 'ruler' — відстані до сусідів
  pinned: null,
  hover: null,
  /* `(on) => void` — ЄДИНИЙ сигнал стану назовні. Кличе його тільки `_emit`,
     і не лише на увімкнення/вимкнення: так само на зміну РЕЖИМУ (кнопка
     режимів, клавіша `M`) і на зміну ЗВІТУ про запінений елемент (новий пін,
     зняття піна, перечитування звіту після виходу курсора). Аргумент — і далі
     `on`, бо історично він так і читався; усе інше підписник бере з `report()`
     і полів `on`/`mode`. Що НЕ є подією: рух курсора. Ховер у сигнатуру не
     входить (див. `_emit`), тож підписатись сюди дешево. */
  onChange: null,

  /* Покоління ЗВІТУ про запінений елемент. Рахує не лише зміну самого
     елемента (`_paint`), а й той єдиний випадок, коли для того самого піна
     міняється ЗМІСТ звіту, — перечитування після виходу курсора
     (`_repaintPinned`).
     Лічильник, а не сам елемент у сигнатурі, і це не стилістика: сигнатура
     зберігається між викликами, тож елемент у ній тримав би ЖИВЕ посилання на
     вузол чужого макета доти, доки хтось не запінить інший — вилучений із
     дерева вузол не звільнився б. Лічильник, крім того, розрізняє пін →
     зняття → пін ТОГО САМОГО елемента: для панелі це три різні стани, а
     порівняння за тотожністю дало б два. */
  _pinSeq: 0,
  /* Пін, за яким лічильник рахували минулого разу. Посилання тут теж є, але
     воно живе рівно стільки, скільки `pinned`: `_paint(null)` на знятті піна
     обнуляє обидва (див. лічильник на початку `_paint`). */
  _pinWas: null,
  /* Остання ВИДАНА назовні сигнатура, не поточна: різниця між ними — це і є
     подія. `null` — ще нічого не видавали, тож перший же виклик спрацює. */
  _lastSig: null,

  /* Хром оверлея (власна кнопка + плаваюче вікно звіту). За замовчуванням
     УВІМКНЕНИЙ — бо типовий випадок цього файла це сторінка, відкрита без
     канваса: там кнопка єдина, чим інспектор можна ввімкнути. Канвас гасить
     хром сам (`setChrome(false)` на кожне завантаження макета, `app.js`). */
  _chrome: true,

  /* Підсумок лінійки, який ЩОЙНО намальовано (`_setMeas`), і його підпис для
     `_emit`. Не «те, що можна порахувати на запит»: панель мусить показувати
     рівно ті числа, що стоять на напрямних, а другий перерахунок на інший
     момент часу дав би інші. */
  _meas: null,
  _measSig: '',

  init() {
    if (this._host) return this;
    /* Мова — ЗІ СХОВИЩА, до першого малювання. Свій екземпляр `i18n.js` у цьому
       документі стартує з `uk` і про вибір у канвасі не знає нічого; ключ
       спільний (`dc-lang`), бо iframe того самого origin ділить `localStorage`
       з оболонкою. `setLabels` згори лишається сильнішим — його кличуть після
       `init` і він перезаписує те, що зібрано тут.
       try/catch не про всяк випадок: у приватному вікні `localStorage` кидає
       на самому ЗВЕРТАННІ, і впав би весь оверлей — інструмент, який ще
       нічого не встиг намалювати. Мова тоді лишається типовою. */
    try { setLang(readStoredLang(localStorage.getItem(LANG_KEY))); } catch (e) { /* лишаємо типову */ }
    const host = document.createElement('div');
    host.setAttribute('data-canvas-inspector', '');
    // :host{all:initial} у shadow-стилі програє правилам зовнішнього дерева
    // (так каскад працює для хоста), тож дублюємо ізоляцію інлайном з
    // !important — інакше `div{margin:…}` у макеті дістав би наш хост.
    host.style.setProperty('all', 'initial', 'important');
    // …але `all:initial` робить хост звичайним інлайновим елементом, і як
    // останній нащадок body він ставав повноцінним учасником розкладки:
    // на `body{display:flex;gap:40px;justify-content:center}` вміст їхав на
    // −20px, а правило макета `body > :last-child` мовчки переставало діяти.
    // Для інструмента ВИМІРЮВАННЯ зсувати те, що міряєш, — неприпустимо, тим
    // паче що хост створюється на завантаженні незалежно від того, увімкнено
    // інспектор чи ні. Вилучаємо хост із потоку: все всередині нього і так
    // position:fixed. Порядок важливий — ці декларації йдуть ПІСЛЯ `all`.
    // …і саме тому потрібен явний z-index: у Chrome `position:fixed` створює
    // ОКРЕМИЙ контекст накладання навіть із `z-index:auto`, а такий контекст
    // малюється на рівні 0. Тобто z-index панелі всередині shadow перестає
    // конкурувати зі сторінкою, і будь-яка липка шапка макета (тут — nav
    // z-index:2000, header z-index:1000) закриває собою ВЕСЬ оверлей.
    for (const [k, v] of [['position', 'fixed'], ['width', '0'], ['height', '0'],
                          ['top', '0'], ['left', '0'], ['z-index', '2147483000']]) {
      host.style.setProperty(k, v, 'important');
    }
    document.body.appendChild(host);
    const sh = host.attachShadow({ mode: 'open' });
    const st = document.createElement('style');
    st.textContent = STYLE;
    sh.appendChild(st);
    const box = document.createElement('div');
    sh.appendChild(box);
    box.innerHTML = `
      <div class="hl hidden"></div>
      <div class="hl-pad hidden"></div>
      <div class="anch hidden"></div>
      <div class="tip hidden"></div>
      <div class="rul hidden">${DIRS.map((d) =>
        `<div class="rg hidden" data-ruler-line="${d}"></div>`
        + `<div class="rlab hidden" data-ruler-label="${d}"></div>`).join('')}</div>
      <button class="btn"><span aria-hidden="true">◎</span> <span data-lbl="inspector"></span></button>
      <div class="panel hidden"></div>`;
    this._host = host;
    this._hl = sh.querySelector('.hl');
    this._pad = sh.querySelector('.hl-pad');
    this._anch = sh.querySelector('.anch');
    this._tip = sh.querySelector('.tip');
    this._btn = sh.querySelector('.btn');
    this._btn.onclick = () => this.toggle();
    /* Розміткові дефолти підписів — через `t()`, а не літералами в шаблоні.
       Літерали були українські назавжди: сторінку макета відкривають і без
       канваса, і там `setLabels` не покличе ніхто ніколи, тобто англійський
       інтерфейс отримував кириличну кнопку. Кличемо ТОЙ САМИЙ `setLabels`, а
       не другий шлях запису: у нього вже є охорона порожнього значення, і
       розійтися двом реалізаціям буде ніде.
       Назва клавіші в `title` (` — I`) лишається літералом — це ім'я клавіші,
       однакове в обох мовах, той самий виняток, що `<kbd>I</kbd>` у панелі. */
    this.setLabels({ inspector: t('inspector') });
    this._btn.title = `${t('inspector')} — I`;
    this._rul = sh.querySelector('.rul');
    this._rline = {};
    this._rlab = {};
    for (const d of DIRS) {
      this._rline[d] = sh.querySelector(`[data-ruler-line="${d}"]`);
      this._rlab[d] = sh.querySelector(`[data-ruler-label="${d}"]`);
    }
    this._panel = sh.querySelector('.panel');
    this._crumbEls = [];
    /* Крихта несе `data-act="inspcrumb" data-val="i"` — розмітку малює
       `insp-report.js`, той самий рендерер, що й для панелі оболонки, і
       контракт індексу тут той самий (`pinAt`). Свого `data-up` більше немає:
       два імені для однієї кнопки означали б, що рендерер мусить знати, куди
       його вішають. */
    this._panel.addEventListener('click', (e) => {
      e.stopPropagation();
      const node = e.target;
      if (!node || !node.closest) return;
      const b = node.closest('[data-act="inspcrumb"]');
      if (b) this.pinAt(b.getAttribute('data-val'));
    });

    // Слухаємо на window у фазі capture — це РАНІШЕ за document-capture
    // comment-layer, тож поки інспектор увімкнено, він гасить події сторінки.
    window.addEventListener('mousemove', (e) => this._onMove(e), true);
    window.addEventListener('mousedown', (e) => this._onDown(e), true);
    window.addEventListener('click', (e) => this._onDown(e), true);
    window.addEventListener('keydown', (e) => this._onKey(e), true);
    window.addEventListener('scroll', () => this._schedule(), true);
    window.addEventListener('resize', () => { invalidate(); this._schedule(); });

    // Макет живий: ітерацію можуть перемалювати, і елемент під підсвіткою
    // зникне. Без цього рамка лишалась би висіти над порожнім місцем.
    if (typeof MutationObserver === 'function') {
      this._mo = new MutationObserver(() => {
        if (!this.on) return;
        let gone = false;
        if (this.pinned && !this.pinned.isConnected) { this.pinned = null; gone = true; }
        if (this.hover && !this.hover.isConnected) { this.hover = null; gone = true; }
        if (gone) this._paint(this.pinned || this.hover);
      });
      this._mo.observe(document.documentElement, { childList: true, subtree: true });
    }
    return this;
  },

  toggle() { this.set(!this.on); },

  /** Режим оверлея. Це РЕЖИМ, а не другий інструмент: ховер, `deepTarget`,
   *  Escape, перемалювання на скрол і ресайз уже написані й перевірені один
   *  раз — другий оверлей дублював би їх усі. */
  setMode(m) {
    this.mode = m === 'ruler' ? 'ruler' : 'cascade';
    /* Підсвітки власного чипа режимів тут більше немає — чипа немає теж
       (17.09.2026): видимий перемикач живе в панелі оболонки, а на голій
       сторінці режим перемикає клавіша `M`. Усе, що лишилось, — перемалювати
       й сказати про це нагору. */
    this._paint(this.pinned || this.hover);
    /* `_paint` вище вже сигналить, і цей виклик у нормальному ході — порожній.
       Стоїть він тут не «про всяк випадок», а тому що інакше подія про зміну
       РЕЖИМУ трималася б на побічному ефекті чужого методу: досить комусь у
       Task 8 забрати з `_paint` малювання панелі разом із сигналом — і клавіша
       `M` мовчки перестала б доходити до батьківського вікна, а сам оверлей
       виглядав би цілком справним. Ціна порожнього виклику — одне порівняння
       рядків. */
    this._emit();
    return this;
  },

  toggleMode() { return this.setMode(this.mode === 'ruler' ? 'cascade' : 'ruler'); },

  /** Сховати/показати ВЛАСНИЙ хром оверлея — кнопку і плаваюче вікно звіту.
   *  Канвас тримає і перемикач, і звіт у своїй правій панелі (у макеті вони
   *  заважали й губились серед його ж інтерфейсу) і кличе `setChrome(false)`
   *  на кожне завантаження макета. Сторінка, відкрита без канваса, лишається
   *  зі своєю кнопкою — інакше вмикати було б нічим — і зі своїм вікном
   *  звіту: показати каскад там більше нема де.
   *
   *  Стан ЗАПАМʼЯТОВУЄТЬСЯ (`_chrome`), а не лише застосовується разово: вікно
   *  народжується пізніше за цей виклик — на першому ж піні (`_renderPanel`),
   *  і без памʼяті воно спокійно вилізло б поверх макета в канвасі. */
  setChrome(on) {
    this._chrome = !!on;
    if (this._btn) this._btn.classList.toggle('hidden', !this._chrome);
    if (!this._chrome && this._panel) this._panel.classList.add('hidden');
    return this;
  },

  /**
   * Підписи власного хрому оверлея — ЗГОРИ. Оверлей живе в документі макета,
   * тобто імпорт `i18n.js` дав би йому ОКРЕМИЙ екземпляр модуля з власним
   * `lang`, і перемикання мови в канвасі до нього б не дійшло. Мова одна —
   * батьківська; сюди приїжджають уже перекладені рядки.
   *
   * Ключі мапи — це ключі СЛОВНИКА (`inspector`, `inspCascade`, `inspRuler`),
   * а вузли позначені `data-lbl` із тим самим ключем. Зайвий рівень імен
   * («btn», «mode1») був би третім словником між двома наявними, і кожен
   * новий підпис коштував би правку в трьох місцях замість одного атрибута.
   *
   * Ключа в мапі немає — лишається РОЗМІТКОВИЙ дефолт, і це несуча вимога, а
   * не ввічливість: сторінку макета відкривають і без канваса (`/commented?…`
   * прямо в браузері), там `setLabels` не покличе НІХТО ніколи, і затирання
   * порожнім значенням лишило б дизайнера з голим значком «◎» замість кнопки,
   * якою інспектор узагалі вмикають.
   *
   * Значок кнопки (`◎`) винесено в ОКРЕМИЙ `<span aria-hidden>` поруч із
   * підписом, і обидва стоять в ОДНОМУ рядку розмітки. Перше — щоб підпис
   * можна було замінити, не втративши значок (`textContent` на всій кнопці
   * зніс би і його). Друге — бо перенос рядка між ними лишається в
   * `textContent` сирим переводом рядка з відступом, і кожен, хто читає
   * підпис кнопки, мусив би його чистити.
   *
   * Атрибути `title` свідомо НЕ чіпаємо: у словнику немає ключів під їхню
   * розгорнуту форму («Каскад і токени», «Відстані до сусідів — M»), а
   * вигадати їх тут означало б завести в цьому файлі нові кириличні літерали
   * — рівно те, від чого його зараз вичищають.
   */
  setLabels(map) {
    if (!map || !this._host || !this._host.shadowRoot) return this;
    for (const n of this._host.shadowRoot.querySelectorAll('[data-lbl]')) {
      const v = map[n.getAttribute('data-lbl')];
      if (typeof v === 'string' && v) n.textContent = v;
    }
    return this;
  },

  /**
   * Серіалізовний звіт про ЗАПІНЕНИЙ елемент, або null. Те саме, що малює
   * `_renderPanel`, але без жодного вузла DOM у результаті: панель живе в
   * ІНШОМУ документі, і віддавати їй елементи означало б дати їй другий шлях
   * до DOM макета — рівно те, від чого застерігає докстрінг `shell-inspect.js`.
   * Тому з `describeAll` беремо поля поіменно, а не розсипаємо обʼєкт: у
   * нього є ще й `el` (`inspector-dom.js`), і `...rep` протягнув би сам вузол.
   *
   * `_crumbEls` лишається ТУТ і саме він відповідає індексам `crumbs`, за
   * якими потім прийде `pinAt`.
   *
   * Про ціну: всередині `describeAll` — `getComputedStyle` і звірка каскаду по
   * пʼятьох групах. Це НЕ те, що можна кликати на кожен рух курсора, і саме
   * тому звіт віддається окремим методом, а не полем: кличе його батько, і
   * кличе рівно на подію `_emit`, яка на ховер не спрацьовує.
   */
  report() {
    const el = this.pinned;
    /* `isConnected` не параноя: пін із вилученого елемента знімає
       MutationObserver, а він АСИНХРОННИЙ — між вилученням вузла і його
       колбеком батько встигає спитати звіт, і `describeAll` порахував би
       каскад для привида, якого в макеті вже немає. Чесна відповідь тут —
       «нічого не запінено». */
    if (!el || !el.isConnected) return null;
    const rep = describeAll(el);
    this._crumbEls = trail(el, document.body);
    return {
      crumbs: this._crumbEls.map((n) => label(n)),
      groups: rep.groups,
      blocked: rep.blocked,
      partial: rep.partial,
      /* Поіменно, як і решта: `dsInfo` — плоский обʼєкт примітивів, але
         розсипати сюди `...rep` однаково не можна (там `el`). */
      dsInfo: rep.dsInfo,
    };
  },

  /**
   * Пакет ОЗНАК запіненого елемента для тюнера, або null, якщо нічого не
   * запінено. Усе — примітиви й рядки: жодного вузла DOM, та сама межа, що в
   * `report()`.
   *
   * ⛔ ЧОМУ ПАКЕТ, А НЕ ШЛЯХ У DOM. Пакет рекомендацій читає Клод у ІНШІЙ
   * сесії — і, як правило, ПІСЛЯ того, як сам же переписав сторінку. Голий
   * `div > div:nth-child(3)` на ту мить не показує вже нікуди: досить
   * додати обгортку чи поміняти порядок дітей. Тому ознак кілька і вони
   * НЕЗАЛЕЖНІ — блок упізнається за їх збігом, а не за однією стрічкою:
   *   · `trail` — підписи предків від кореня (той самий ланцюжок, що в
   *     крихтах панелі); переживає перейменування класів у самому елементі;
   *   · `label` — підпис самого елемента (тег + до двох класів);
   *   · `selector` — селектор правила, що виграло каскад ДЛЯ ЦІЄЇ
   *     властивості, тобто «де правити»; у кожної властивості він свій, тому
   *     аргумент `prop` тут обовʼязковий по суті, а не для зручності;
   *   · `text` — шматок власного тексту; переживає будь-яку зміну розмітки,
   *     бо його пише не верстальник, а автор контенту.
   *
   * `selector` порожній у двох різних випадках, і плутати їх не можна:
   * `[style]` — виграв атрибут `style` (правити треба розмітку), `null` —
   * не виграв ніхто, кого ми бачимо (жодного оголошення, або джерело
   * лишилось за межею нашої моделі каскаду: @layer, @container). Друге —
   * чесне «шукай сам», і саме тому воно не вдає із себе селектор.
   */
  identity(prop) {
    const el = this.pinned;
    /* Той самий `isConnected`, що й у `report()`, і з тієї ж причини: пін із
       вилученого вузла знімає АСИНХРОННИЙ MutationObserver, тож устигнути
       спитати про привида можна. Ознаки такого привида поїхали б у пакет
       рекомендацій як опис живого блоку. */
    if (!el || !el.isConnected) return null;
    const win = typeof prop === 'string' && prop ? pickWinner(declsFor(el, prop)) : null;
    return {
      trail: trail(el, document.body).map((n) => label(n)),
      label: label(el),
      selector: win ? (win.inline ? INLINE_RULE : (win.sel || null)) : null,
      text: ownText(el),
    };
  },

  /**
   * Накрутити значення ЖИВЦЕМ — інлайн-стилем запіненого елемента.
   *
   * ⛔ ТЮНЕР НЕ ПИШЕ НІКУДИ, крім живого DOM цієї вкладки: інлайн видно
   * миттєво і він не торкається ні файла макета, ні sidecar-шару коментарів
   * (шапка `app/tuner-model.js`). Ручка жива, ВИХІД — рекомендація; правку в
   * код робить Клод, прочитавши пакет. Саме тому макет лишається джерелом
   * правди.
   *
   * `important` — не перестраховка, а умова того, щоб ручка взагалі крутилась.
   * Інлайн БЕЗ пріоритету програє авторському `!important` зі сторінки
   * (`pickWinner`: вага 3 проти 2), а такі правила в макетах є — утилітарні
   * класи, скинуті плагіни, чужі теми. Ручка, яку мовчки перебиває сторінка,
   * для інструмента «побач зміну одразу» гірша за відсутню: дизайнер крутить,
   * нічого не відбувається, і він вирішує, що зламався інструмент. Сліду по
   * собі пріоритет не лишає — `clearTune` знімає властивість разом із ним, а
   * порожній атрибут `style` прибирає цілком.
   *
   * ⚠️ ПОРЯДОК ІЗ `identity()`, і це справжня пастка. Інлайн-оголошення ВИГРАЄ
   * каскад, тож після першого ж запису `identity(prop).selector` віддає
   * `[style]` — тобто «правити розмітку», хоча правити треба те правило, що
   * виграло ДО кручення. Ознаки для пакета знімає той, хто кличе, і знімає їх
   * ПЕРЕД першим `applyTune` для ЦІЄЇ властивості (`tuneSet`, `app/app.js`).
   * Звідси й те, чому цей метод сам не чіпає моделі тюнера: він не має права
   * вирішувати, чи вже пізно питати походження.
   *
   * Барʼєра на значення тут немає свідомо, і це не недогляд: `setProperty`
   * ПАРСИТЬ значення, а не склеює атрибут, тож ні другої декларації, ні виходу
   * за межі властивості з нього не зібрати. Регексп `CSS_SAFE`
   * (`insp-report.js`) стереже інший випадок — значення, що йде в АТРИБУТ
   * `style` рядком.
   *
   * @returns {boolean} значення справді лягло. `false` — браузер його не
   *   прийняв (від'ємний `padding`, `16qq`, порожнє поле): CSSOM тихо ковтає
   *   непридатне оголошення, а записати таку правку в пакет означало б
   *   пообіцяти Клоду зміну, якої дизайнер на макеті не бачив.
   */
  applyTune(prop, value) {
    const el = this.pinned;
    /* Той самий `isConnected`, що в `report()`/`identity()`, і з тієї ж
       причини: пін із вилученого вузла знімає АСИНХРОННИЙ MutationObserver,
       тож устигнути накрутити на привида можна — і зміни не побачив би ніхто,
       а в пакет вона поїхала б як справжня. */
    if (!el || !el.isConnected || typeof prop !== 'string' || !prop) return false;
    /* Старе знімаємо ПЕРЕД записом, щоб «прийняв / не прийняв» читалось по
       порожньому полю, а не по значенню, що лишилось від попереднього повороту
       ручки: інакше друга, непридатна спроба виглядала б успішною. Придатне
       старе повертаємо на місце — відмова не сміє нічого зіпсувати. */
    const was = el.style.getPropertyValue(prop);
    const wasPrio = el.style.getPropertyPriority(prop);
    el.style.removeProperty(prop);
    el.style.setProperty(prop, String(value == null ? '' : value), 'important');
    if (el.style.getPropertyValue(prop) === '') {
      if (was) el.style.setProperty(prop, was, wasPrio);
      return false;
    }
    this._tuned();
    return true;
  },

  /**
   * Зняти накручене — рівно одну властивість, не весь атрибут.
   *
   * Порожній `style=""` після зняття прибираємо цілком: тюнер обіцяє не
   * лишати слідів у розмітці, а атрибут — це слід, видимий і в DevTools, і в
   * збереженій сторінці. На модель каскаду він не впливає ніяк (`declsFor`
   * бере інлайн лише коли в ньому є значення), тобто це саме про чистоту. І
   * лише коли не лишилось НІЧОГО: власний `style` макета не наш.
   */
  clearTune(prop) {
    const el = this.pinned;
    if (!el || !el.isConnected || typeof prop !== 'string' || !prop) return false;
    el.style.removeProperty(prop);
    if (!el.style.length) el.removeAttribute('style');
    this._tuned();
    return true;
  },

  /**
   * Накласти накручене на елемент, знайдений ЗА СЕЛЕКТОРОМ, без піна.
   *
   * ⛔ ЗАРАДИ ЧОГО ВОНО ІСНУЄ. Оболонка переприсвоює `frame.src` на кожному
   * повному рендері (`applyMode`, `app/app.js:129`), і навіть той самий рядок
   * перезавантажує документ. Разом із документом зникають ВСІ інлайн-стилі,
   * які поклав тюнер, — а модель тюнера живе в батьківському вікні й
   * перезавантаження переживає. Без повторного накладання панель показувала б
   * накручене, якого на макеті вже немає: та єдина брехня, якою ця фіча може
   * зіпсуватись («покрутив, а воно не доїхало»), лише в дзеркальному вигляді.
   * Пін тут не годиться нічим: після перезавантаження запінено НІЧОГО, а
   * накласти треба все — і по кількох елементах одразу.
   *
   * Селектор — ключ ЕЛЕМЕНТА з моделі (`elementKey`, `app/tuner-model.js`):
   * ланцюжок підписів предків (`body > div.wrap > p.card`), який водночас є
   * придатним CSS-селектором. `!important` — та сама причина, що в
   * `applyTune`: без пріоритету накручене програє авторському `!important`
   * зі сторінки, і ручка мовчки перестає діяти саме там, де вона найпотрібніша.
   *
   * ⚠️ ВІДОМА МЕЖА, і вона не в цьому методі: два однакові на вигляд блоки в
   * одному батькові (`p.card` двічі в `div.row`) дають ОДНАКОВИЙ ключ, тобто
   * модель зводить їх в один елемент іще на записі (`elementKey`). Тут це
   * видно як «беремо перший збіг» — але зникає різниця раніше, в моделі, і
   * лікується вона теж там.
   *
   * `_tuned()` НЕ кличемо: після перезавантаження нічого не запінено, звіт
   * порожній, а панель батько перемальовує сам — одним викликом на всі
   * накладені правки, а не одним на кожну.
   *
   * @returns {boolean} елемент знайдено і значення браузер прийняв.
   */
  applyBySelector(selector, prop, value) {
    if (typeof selector !== 'string' || !selector) return false;
    if (typeof prop !== 'string' || !prop) return false;
    let el = null;
    /* `querySelector` КИДАЄ на непридатному селекторі (клас із `:` або `/` —
       звичайна річ у макетах з утилітарними класами). Тихий пропуск тут
       правильний: елемента могло не стати в новій версії сторінки, і це не
       помилка дизайнера. Правку при цьому НЕ прибираємо — вона лишається в
       пакеті для Клода, бо описує те, що дизайнер справді зробив. */
    try { el = document.querySelector(selector); } catch (e) { el = null; }
    if (!el) return false;
    el.style.setProperty(prop, String(value == null ? '' : value), 'important');
    // Те саме читання назад, що в `applyTune`: CSSOM ковтає непридатне
    // оголошення мовчки, і «наклали» мусить означати «браузер прийняв».
    return el.style.getPropertyValue(prop) !== '';
  },

  /**
   * Зняти накручене з елемента, знайденого ЗА СЕЛЕКТОРОМ, без піна.
   *
   * Навіщо друга двері поруч із `clearTune`: на вкладці «Тюнер» (Task 15)
   * дизайнер скидає правку зі СПИСКУ, а не з макета — у ту мить не запінено
   * нічого, і `clearTune` (він працює з `this.pinned`) не має на чому
   * спрацювати взагалі. Списком правки й адресуються: ключ елемента —
   * ланцюжок підписів предків (`body > div.wrap > p.card`, `elementKey` в
   * `app/tuner-model.js`), і він же є придатним CSS-селектором.
   *
   * ⚠️ `querySelector` КИДАЄ на непридатному селекторі (клас із `:` чи `/` —
   * у макетах з утилітарними класами таке звичайне), тому try/catch, і не
   * порожній: тихо пропустити тут правильно. Елемент міг зникнути з документа
   * між тим, як дизайнер побачив список, і тим, як натиснув хрестик, — це не
   * помилка, і панель у такому разі все одно мусить прибрати правку зі свого
   * боку (`tuneDrop`, `app/app.js`).
   *
   * Порожній `style=""` прибираємо цілком — тією ж рукою й з тієї ж причини,
   * що `clearTune`: тюнер обіцяв не лишати слідів у розмітці.
   *
   * @returns {boolean} елемент знайдено і властивість знято.
   */
  clearBySelector(selector, prop) {
    if (typeof selector !== 'string' || !selector) return false;
    if (typeof prop !== 'string' || !prop) return false;
    let el = null;
    try { el = document.querySelector(selector); } catch (e) { el = null; }
    if (!el) return false;
    el.style.removeProperty(prop);
    if (!el.style.length) el.removeAttribute('style');
    /* `_tuned()` кличемо лише коли елемент ЗАПІНЕНИЙ: метод рухає покоління
       звіту й перемальовує рамку саме запіненого: для чужого елемента це була
       б подія «звіт змінився» там, де звіт не змінювався. Коли ж скидають
       якраз запінене (дизайнер пінив елемент, потім пішов у список) — звіт про
       нього справді став іншим, і без сигналу панель показувала б старе. */
    if (el === this.pinned) this._tuned();
    return true;
  },

  /**
   * Звіт змінився, хоч пін той самий — розбудити батька.
   *
   * Без цього рядка панель лишалась би зі СТАРИМ числом, і фіча провалювалась
   * би мовчки. `_emit` порівнює сигнатуру `on|mode|_pinSeq|_measSig`, а
   * кручення ручки не міняє в ній нічого: ні режиму, ні піна інлайн-стиль не
   * чіпає. Самого `_paint` теж не досить — він рахує покоління ЛИШЕ коли
   * змінився САМ елемент (`pinned !== _pinWas`), а тут елемент той самий.
   * Тому покоління рухаємо тут, руками: це рівно той випадок, заради якого
   * лічильник і став «поколінням ЗВІТУ», а не «поколінням піна», — його вже
   * рухає з тієї ж причини `_repaintPinned` (пін не змінився, а те, що про
   * нього треба показати, — змінилось).
   *
   * `_paint`, а не самий `_emit`: змінюється не лише число у звіті, а й
   * ГЕОМЕТРІЯ елемента (накрутили padding — рамка оверлея мусить переїхати
   * разом із ним), і власне летюче вікно звіту для сторінки, відкритої без
   * канваса. `_emit` `_paint` кличе останнім рядком сам.
   */
  _tuned() {
    this._pinSeq += 1;
    this._paint(this.pinned);
  },

  /**
   * Серіалізовний підсумок ЛІНІЙКИ, або null. Симетрично до `report()`, з
   * тією ж межею: жодного вузла DOM назовні — панель живе в іншому документі.
   *
   * Віддає те, що намальовано ОСТАННІМ (`_setMeas`), а не рахує наново, і це
   * головне рішення тут: геометрію в цьому інструменті рахують в ОДНОМУ місці
   * (`_ruler`/`_pair`), тож панель і напрямні на макеті — два показники одного
   * виміру, а не два виміри. Перерахунок «на запит» стався б на іншу мить
   * (курсор уже зрушив, сторінка вже прокрутилась) і дав би числа, яких на
   * макеті ніхто не бачив.
   *
   * Форма — див. докстрінг `measureHTML` (`insp-report.js`), який її й читає:
   *   { mode: 'nearest' | 'pair', kind, rows: [{ key, px, kind }] }
   * `mode` розрізняє дві живі механіки лінійки (чотири найближчі сусіди без
   * якоря — і вимір «якір ↔ ховер»), бо одна одну не заміняє, і подати їх
   * панелі однаковими означало б збрехати, на яке саме питання відповідь.
   * Полів понад те, що рахують `measure()`/`between()`, тут немає жодного.
   */
  measure() {
    return this._meas;
  },

  /** Запамʼятати намальований підсумок і його підпис для `_emit`.
   *
   *  Підпис — на ОКРУГЛЕНИХ числах, тобто рівно на тому, що показується. На
   *  сирих дробових кожен піксель прокрутки на дробовій розкладці міняв би
   *  сигнатуру, і панель перемальовувалась би щокадру заради 15.98 → 15.99 —
   *  разом із виділенням тексту, яке дизайнер у ній щойно зробив (та сама
   *  причина, з якої в сигнатурі немає ховера). */
  _setMeas(meas) {
    this._meas = meas;
    this._measSig = meas
      ? `${meas.mode}:${meas.kind || ''}:` + meas.rows
        .map((r) => `${r.key}${Math.round(r.px)}${r.kind || ''}`).join(',')
      : '';
  },

  /** Запінити предка за індексом крихти. Індекс — у тому самому масиві,
   *  що віддав `report()`; іншого джерела в панелі немає й бути не мусить.
   *
   *  Порядок «спершу `report()`, тоді `pinAt()`» звідси НЕ видно й гарантувати
   *  його цей метод не може: `_crumbEls` — знімок, а макет живий. Тому дві
   *  охорони. `_crumbEls[Number(i)]` порожній (панель ще нічого не питала, або
   *  індекс — сміття, або крихт стало менше після піна предка) — не робимо
   *  нічого: тихо, бо клацання по крихті, якої вже немає, це не помилка
   *  дизайнера. `isConnected` — знімок застарів, елемент уже вилучили з
   *  макета: запінити його означало б підсвітити порожнє місце і віддати
   *  звіт про вузол поза документом. */
  pinAt(i) {
    const el = this._crumbEls && this._crumbEls[Number(i)];
    if (!el || !el.isConnected) return;
    this.pinned = el;
    this._paint(el);
  },

  set(on) {
    this.on = !!on;
    this._btn.classList.toggle('on', this.on);
    /* Чип режимів стояв тут до 17.09.2026 — він єдиний жив ПОЗА `setChrome`,
       бо в канвасі режим треба було чимось перемикати. Тепер перемикач є в
       панелі оболонки, і окремий виняток із хрому більше не потрібен. */
    if (!this.on) { this.pinned = null; this.hover = null; this._paint(null); }
    // Гасимо режим коментування, щоб його панель не висіла даремно.
    if (this.on && window.CommentLayer && typeof window.CommentLayer.setCommentMode === 'function') {
      window.CommentLayer.setCommentMode(false);
    }
    // Стан міняє не лише кнопка: клавіша `I` і Esc теж. Хто тримає власний
    // перемикач (канвас) — дізнається звідси, а не вгадує. Виклик `onChange`
    // ПРЯМО звідси прибрано свідомо: поки він стояв тут, `set(false)` по
    // кліку в інтерфейс comment-layer (`_onDown`) смикав батька навіть тоді,
    // коли інспектор і так був вимкнений, а зміну РЕЖИМУ й ПІНА батько не
    // бачив узагалі. Одні двері на всі три зміни — `_emit`.
    this._emit();
  },

  /**
   * Один сигнал стану для батьківського вікна.
   *
   * Порівняння сигнатур — щоб рух курсора не перемальовував панель: `_paint`
   * кличеться на КОЖНІЙ зміні елемента під курсором (`_onMove`), тобто
   * десятки разів на секунду, а звіт залежить від ЗАПІНЕНОГО елемента, не від
   * наведеного. Без порівняння батько на кожен рух перечитував би `report()`
   * (а це `getComputedStyle` по пʼятьох групах) і переписував би `innerHTML`
   * панелі — разом із виділенням тексту, яке дизайнер у ній щойно зробив.
   *
   * У сигнатурі рівно те, від чого залежить вигляд панелі: `on`, `mode`,
   * покоління ЗВІТУ (`_pinSeq` — тобто і зміна запіненого елемента, і
   * перечитування звіту про нього) і, з 17.09.2026, підпис намальованого
   * підсумку ЛІНІЙКИ.
   *
   * Лінійка додана в сигнатуру не для повноти. У режимі лінійки числа
   * міняються від РУХУ КУРСОРА (вимір «якір ↔ ховер») і від ПРОКРУТКИ —
   * тобто саме від того, про що `_emit` мовчить у каскаді. Без цього поля
   * панель показувала б числа, зняті в мить входу в режим, і мовчки
   * розходилася б із напрямними на макеті — найгірша можлива несправність
   * інструмента вимірювання. Ховер як такий у сигнатуру НЕ входить і тут:
   * входить результат виміру, і поки числа ті самі (курсор їздить по одному
   * елементу, прокрутка не зрушила рамок) подія не народжується.
   */
  _emit() {
    const sig = `${this.on}|${this.mode}|${this._pinSeq}|${this._measSig}`;
    if (sig === this._lastSig) return;
    /* Запис ДО виклику, не після: колбек батька має повне право змінити стан
       у відповідь (клік по крихті → `pinAt` → `_paint` → знову сюди), і зі
       старою сигнатурою в полі це був би нескінченний спуск. */
    this._lastSig = sig;
    if (typeof this.onChange !== 'function') return;
    /* Сигнатура, яку НЕ доставили, не сміє лишитись записаною як доставлена:
       інакше виняток у батька (а панель малює чужий payload, тобто впасти
       може) назавжди ховає саме той стан, на якому вона й застрягла — і
       вирівняється вона хіба випадково, коли зміниться інше поле сигнатури.
       Обнулення повертає систему в «нічого не видавали», тож найближчий же
       `_emit` — хоч і з тим самим станом, наприклад з руху курсора —
       доставить його ще раз. Виняток і далі не летить у макет: падати через
       чужу панель оверлей не має права. */
    try { this.onChange(this.on); } catch (e) { this._lastSig = null; }
  },

  /** Елемент сторінки під курсором, або null — якщо це наш чи чужий оверлей. */
  _pageEl(e) {
    /* `node`, а не `t`: `t` у цьому файлі — функція перекладу (`../i18n.js`). */
    const node = e.target;
    if (!node || node.nodeType !== 1) return null;
    if (node === this._host || (node.closest && node.closest('[data-canvas-inspector]'))) return null;
    if (node.closest && node.closest(CL_HOST)) return null;
    return node;
  },

  _onMove(e) {
    if (!this.on) return;
    const el = this._pageEl(e);
    if (!el) return;                       // над чужим оверлеєм — не втручаємось
    e.stopPropagation();
    this._pt = { x: e.clientX, y: e.clientY };
    if (this.pinned) {
      /* У режимі лінійки пін — це ЯКІР, а не заморозка: ховер лишається живим,
         і лінійка показує відстань МІЖ якорем і тим, на що дивишся. Так просив
         дизайнер, і так працює референс (VisBug). Перевірка J раніше стерегла
         протилежне — переписана. */
      if (this.mode === 'ruler') {
        if (el !== this.hover) { this.hover = el; this._paint(this.pinned); }
        return;
      }
      // Пінування нічого не перемикає — крім одного: коли курсор нарешті
      // зійшов із запіненого елемента, його :hover згас, і звіт треба
      // перечитати (див. _repaintPinned). Рівно ОДИН перемальунок на вихід:
      // _pinLeftFor памʼятає, для якого саме елемента ми це вже зробили,
      // тож повернення курсора назад знову озброює перевірку, а зміна
      // запіненого елемента скидає її сама собою.
      if (el === this.pinned || this.pinned.contains(el)) this._pinLeftFor = null;
      else if (this._pinLeftFor !== this.pinned) { this._pinLeftFor = this.pinned; this._repaintPinned(); }
      return;
    }
    if (el !== this.hover) { this.hover = el; this._paint(el); } else { this._place(); }
  },

  /** Перечитати запінений елемент, коли курсор його ПОКИНУВ.
   *  Пінують кліком, тобто в момент звіту курсор стоїть НА елементі і його
   *  :hover активний: computed приходить із ховер-стану, а каскад ми рахуємо
   *  БЕЗ :hover-правил (щоб не видати ховер-токен за базовий) — звірка падає,
   *  і на кнопках, посиланнях та картках (найчастіші цілі інспектування)
   *  background-color/color лишались без бейджа зовсім. Щойно курсор пішов,
   *  елемент повертається в базовий стан і звіт стає правдивим.
   *  Прокрутку панелі зберігаємо — користувач може вже читати її вміст. */
  _repaintPinned() {
    const el = this.pinned;
    if (!el) return;
    // У режимі лінійки перечитувати нічого: каскадної панелі там немає, а
    // геометрія від того, куди пішов курсор, не залежить.
    if (this.mode === 'ruler') return;
    const top = this._panel.scrollTop;
    /* Сигнал батькові звідси — ДОДАНО понад план Task 4, свідомо. Весь сенс
       цього методу в тому, що звіт, знятий у мить піна, НЕПРАВДИВИЙ (див.
       докстрінг вище), а правдивим стає рівно тут. Сигнатура `_emit` від
       самого перечитування не міняється — тобто панель у батьківському вікні
       застрягла б саме на тій версії звіту, заради виправлення якої цей метод
       і написаний, і Task 5/6 полагодити це вже не змогли б: інших подій у них
       немає. Тому покоління рахує не лише зміну ЕЛЕМЕНТА (`_paint`), а й зміну
       самого ЗВІТУ про нього. Шторму це не робить: `_pinLeftFor` (`_onMove`)
       впускає сюди рівно один раз на кожен вихід курсора за межі запіненого
       елемента — не на кожен рух.

       `finally` — з тієї самої причини, що в `_paint`: `_renderPanel` ходить
       по живому CSSOM чужого макета, тобто впасти може, а батько мусить
       дізнатись про стан у будь-якому разі. Наступного заходу сюди без нового
       виходу курсора не буде взагалі, тож пропущений тут сигнал — це
       пропущений НАЗАВЖДИ. */
    try {
      this._renderPanel();
      this._panel.scrollTop = top;
    } finally {
      this._pinSeq += 1;
      this._emit();
    }
  },

  _onDown(e) {
    if (!this.on) return;
    const el = this._pageEl(e);
    if (!el) {
      // Клік по інтерфейсу comment-layer = користувач перемкнувся на інший інструмент.
      // Подію НЕ гасимо — вона має дійти до comment-layer.
      if (e.target && e.target.closest && e.target.closest(CL_HOST)) this.set(false);
      return;
    }
    e.stopPropagation();
    e.preventDefault();
    if (e.type !== 'click') return;
    this.pinned = this.pinned === el ? null : el;
    this._paint(this.pinned || el);
  },

  _onKey(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    // Набір тексту (у т.ч. в полі comment-layer усередині його shadow DOM)
    // не має вмикати інспектор і не має ловитись Esc.
    if (isEditable(deepTarget(e)) || isEditable(activeDeep())) return;
    // Регексп, а не чотири порівняння: та сама форма, що рядком нижче для `M`
    // — і рівно з тієї ж причини, з якої та форма там уже стоїть. Кирилична
    // розкладка мусить працювати, але кирилиця в СТРОКОВОМУ літералі — це
    // майбутнє спрацювання охоронця i18n (він свідомо не заглядає в регекспи,
    // бо там кирилиця означає розкладку клавіші, а не напис для людини).
    if (/^[iIшШ]$/.test(e.key)) {
      this.toggle(); e.stopPropagation(); e.preventDefault(); return;
    }
    // Режим перемикає ТІЛЬКИ ввімкнений інспектор: інакше `M` у вимкненому
    // стані з'їдалася б у макета даремно (а вмикати нею інспектор — сюрприз).
    if (this.on && /^[mMьЬ]$/.test(e.key)) {
      this.toggleMode(); e.stopPropagation(); e.preventDefault(); return;
    }
    if (!this.on || e.key !== 'Escape') return;
    // Драбинка: спершу з лінійки в каскад, тоді знімаємо пін, і лише тоді гасимо.
    /* Драбинка: у лінійці спершу знімаємо ЯКІР (він тепер несе сенс режиму), і
       лише наступним Escape виходимо в каскад. */
    if (this.mode === 'ruler' && this.pinned) { this.pinned = null; this._paint(this.hover); }
    else if (this.mode === 'ruler') this.setMode('cascade');
    else if (this.pinned) { this.pinned = null; this._paint(this.hover); }
    else this.set(false);
    e.stopPropagation();
  },

  /** Не більше ОДНОГО перерахунку на кадр (як обіцяє спека). Слухач scroll
   *  стоїть у фазі capture на window, тобто ловить скрол КОЖНОГО вкладеного
   *  контейнера, а кожен _reflow — це getBoundingClientRect, getComputedStyle
   *  і 12 записів у стиль. Частіше за кадр підсвітку однаково ніхто не
   *  побачить, тож кадр — природна межа. */
  _schedule() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this._reflow(); });
  },

  /** Тільки геометрія — без перебудови розмітки: скрол може йти сотнями подій.
   *
   *  `finally` з `_emit` — той самий прийом, що в `_paint`, але тут він несе
   *  ще й нову роботу: прокрутка МІНЯЄ ЧИСЛА ЛІНІЙКИ, і без сигналу звідси
   *  панель лишалась би з тими, що були до скролу. Шторму це не робить —
   *  `_emit` порівнює сигнатуру, а в каскаді скрол її не чіпає взагалі, тож
   *  колбек батька там не кличеться жодного разу. */
  _reflow() {
    if (!this.on) return;
    try {
      const el = this.pinned || this.hover;
      if (!this._frame(el)) { this._hide(); return; }
      // Лінійка це чиста геометрія, тобто саме те, що скрол і ресайз ламають:
      // перерахунок тут обовʼязковий, і він у межах кадру (виміряно: 0.9 мс на
      // найважчій сторінці демо, 954 елементи).
      if (this.mode === 'ruler') { this._ruler(el); return; }
      this._place();
    } finally { this._emit(); }
  },

  _hide() {
    [this._hl, this._pad, this._tip, this._panel, this._rul, this._anch]
      .forEach((n) => n && n.classList.add('hidden'));
    /* Сховані напрямні — це відсутній вимір, а не старий: лишити тут числа
       означало б показувати в панелі відстані до елемента, якого на екрані
       вже немає. */
    this._setMeas(null);
  },

  /**
   * Кандидати в сусіди для `el`: видимі елементи документа з коробкою.
   *
   * Виключення тут, а не в `measure`: чистий модуль про DOM не знає й знати не
   * мусить. Прибрати будь-який рядок цього фільтра — і лінійка почне показувати
   * числа, яких у макеті немає:
   *
   *  — сам елемент, його ПРЕДКИ і НАЩАДКИ. Правило «повністю містить ціль» у
   *    `measure` це майже покриває, але саме що МАЙЖЕ: батько, з якого дитина
   *    вилізла (`position:relative`, `top:50px`), цілі вже не містить — і без
   *    цього рядка ставав би її «сусідом зверху»;
   *  — ОВЕРЛЕЇ (наш і comment-layer): міряти відстань до власного інструмента
   *    безглуздо. Сьогодні обидва хости нульового розміру й їх однаково відсіяв
   *    би фільтр порожніх — але це збіг верстки, а не контракт: у
   *    `body{display:grid}` хост дістає коробку рядка;
   *  — НЕВИДИМЕ. На живій сторінці блогу це 246 елементів із 693 (виміряно):
   *    згорнуті меню, схований пошук. Показати відстань до `visibility:hidden`
   *    означає збрехати про зазор, який дизайнер бачить очима;
   *  — порожні коробки й непридатні числа (`NaN`/`Infinity` з SVG): останнє
   *    `measure` не пропустив би, а КИНУВ, і замість пропуску одного елемента
   *    лінійка зникла б цілком.
   */
  _candidates(el) {
    const nodes = [];
    const rects = [];
    for (const cand of document.querySelectorAll('*')) {
      if (cand === el || el.contains(cand) || cand.contains(el)) continue;
      if (cand.closest(OVERLAY_HOSTS)) continue;
      if (typeof cand.checkVisibility === 'function' && !cand.checkVisibility(
        { visibilityProperty: true, opacityProperty: true, contentVisibilityAuto: true })) continue;
      const r = cand.getBoundingClientRect();
      if (!finiteRect(r) || r.right - r.left <= 0 || r.bottom - r.top <= 0) continue;
      nodes.push(cand);
      rects.push(r);
    }
    return { nodes, rects };
  },

  /** Внутрішній край КОНТЕЙНЕРА цілі, або null (контейнера немає).
   *
   *  Контейнер — той, чиї межі тримають елемент: для `fixed` це вьюпорт (батько
   *  в потоці може бути де завгодно вище, і його край не пояснює нічого), для
   *  `absolute` — коробка, від якої елемент відлічує свої `top/left`, для решти
   *  — батько. Обгортки без власної коробки (`display:contents`) проходимо далі
   *  вгору: контейнером вони не є. */
  _containerBox(el) {
    const pos = getComputedStyle(el).position;
    if (pos === 'fixed') return viewportBox();
    let host = pos === 'absolute' ? el.offsetParent : el.parentElement;
    while (host && host.nodeType === 1) {
      const box = innerBox(host);
      if (box) return box;
      host = host.parentElement;
    }
    return pos === 'absolute' ? viewportBox() : null;
  },

  /** Намалювати лінійку для елемента: пунктирна напрямна в кожен бік і плашка з
   *  цілим числом на ній (дробові пікселі — справа `measure`, Р5).
   *
   *  Три проходи, і порядок тут не стилістика: розкласти плашки не можна, не
   *  знаючи їхнього РОЗМІРУ, а розмір залежить від числа, яке саме зараз і
   *  пишеться. Тому спершу всі записи, потім усі читання, потім знову записи —
   *  інакше кожна плашка коштувала б окремий forced layout, а це кадр скролу
   *  (`_reflow` крутиться на кожній події прокрутки). */
  _ruler(el) {
    /* Є якір і курсор на ІНШОМУ елементі — міряємо між ними. Немає якоря —
       чотири найближчі, як було: обидві механіки корисні, тому одна не заміняє
       другу. */
    if (this.mode === 'ruler' && this.pinned && this.hover
        && this.hover !== this.pinned) {
      this._pair(this.pinned, this.hover);
      return;
    }
    this._anch.classList.add('hidden');   // без якоря його рамки бути не мусить
    /* `tr`, а не `t`: імʼя `t` у цьому файлі віддане функції перекладу
       (`../i18n.js` — імпорт приходить разом із прибиранням власного хрому),
       і локальний прямокутник з таким іменем тихо затуляв би її для всієї
       функції. */
    const tr = el.getBoundingClientRect();
    if (!finiteRect(tr)) { this._rul.classList.add('hidden'); this._setMeas(null); return; }
    const { rects } = this._candidates(el);
    const box = this._containerBox(el);
    const found = measure(tr, rects, box);
    this._rul.classList.remove('hidden');
    const plan = [];
    /* Підсумок для панелі збирається ТУТ, з тих самих `hit`, що йдуть на
       плашки, — не другим проходом по геометрії: два проходи це два трохи
       різні числа про те саме. */
    const rows = [];
    for (const dir of DIRS) {
      const hit = found[dir];
      const line = this._rline[dir];
      const lab = this._rlab[dir];
      if (!hit) { line.classList.add('hidden'); lab.classList.add('hidden'); continue; }
      rows.push({ key: dir, px: hit.px, kind: hit.kind });
      const other = hit.kind === 'container' ? box : rects[hit.index];
      const vert = dir === 'top' || dir === 'bottom';
      /* Напрямна стоїть посередині СМУГИ ПЕРЕТИНУ цілі й знайденого — саме там,
         де зазор існує. Для контейнера смуга це сама ціль. */
      const lo = vert ? Math.max(tr.left, other.left) : Math.max(tr.top, other.top);
      const hi = vert ? Math.min(tr.right, other.right) : Math.min(tr.bottom, other.bottom);
      const mid = (lo + hi) / 2;
      /* Край, до якого веземо: у сусіда це край, ОБЕРНЕНИЙ до цілі, у
         контейнера — край ТОГО САМОГО боку (його межа, а не протилежна). */
      const near = hit.kind === 'container' ? other[dir]
        : other[{ top: 'bottom', bottom: 'top', left: 'right', right: 'left' }[dir]];
      const from = Math.min(tr[dir], near);
      const px = (v) => `${v}px`;
      line.className = `rg ${vert ? 'v' : 'h'}${hit.kind === 'container' ? ' box' : ''}`;
      Object.assign(line.style, vert
        ? { left: px(mid), top: px(from), width: '0px', height: px(hit.px) }
        : { left: px(from), top: px(mid), width: px(hit.px), height: '0px' });
      lab.className = `rlab${hit.kind === 'container' ? ' box' : ''}`;
      lab.textContent = String(Math.round(hit.px));
      lab.setAttribute('data-kind', hit.kind);
      lab.setAttribute('data-ruler-label', dir);   // парний режим міняє ключ — вертаємо свій
      lab.classList.remove('hidden');
      /* `away` — куди «від елемента» по осі вимірювання: вгору й ліворуч це
         мінус, униз і праворуч плюс. */
      plan.push({ lab, vert, mid, gap: hit.px, edge: tr[dir],
                  away: dir === 'top' || dir === 'left' ? -1 : 1 });
    }
    /* `kind: null` — тут його НЕМАЄ на весь вимір: кожен напрямок знайшов
       своє (сусіда чи межу контейнера), і спільного виду в чотирьох чисел
       просто не існує. Виставляємо ДО виходу «нема чого малювати»: порожній
       набір — теж чесна відповідь, і панель мусить бачити саме її, а не
       попередній вимір. */
    this._setMeas({ mode: 'nearest', kind: null, rows });
    if (!plan.length) return;
    for (const p of plan) {
      const r = p.lab.getBoundingClientRect();
      p.len = p.vert ? r.height : r.width;    // розмір ПО ОСІ вимірювання
      p.thick = p.vert ? r.width : r.height;  // …і впоперек неї
    }
    this._spread(plan);
    for (const p of plan) {
      Object.assign(p.lab.style, p.vert
        ? { left: `${p.mid}px`, top: `${p.at}px` }
        : { left: `${p.at}px`, top: `${p.mid}px` });
    }
  },

  /** Парний вимір: відстань між ЯКОРЕМ (клік) і тим, на що дивишся.
   *
   *  Малює рівно ті напрямні, які віддав `between` — модуль сам вирішив, скільки
   *  їх і що вони означають: один зазор, Г-подібний кут із двох (коли спільної
   *  смуги немає ні по X, ні по Y, і одного числа просто не існує), два числа
   *  глибини перекриття, або чотири внутрішні відстані, коли одне цілком у
   *  другому (іконка в кнопці — найчастіший випадок цієї фічі).
   *
   *  Вид (`kind`) їде в `data-kind` і в клас плашки: «12», подане зазором,
   *  дизайнер прочитає як відступ, тому перекриття мусить виглядати інакше. */
  _pair(anchor, target) {
    const a = anchor.getBoundingClientRect();
    const b = target.getBoundingClientRect();
    if (!finiteRect(a) || !finiteRect(b)) {
      this._rul.classList.add('hidden'); this._setMeas(null); return;
    }
    const res = between(a, b);
    /* Підсумок для панелі — з того самого `res`, що йде на напрямні.
       `kind` у парного виміру ОДИН на весь вимір (так його й рахує `between`),
       тому він нагорі, а не в кожному рядку. Ключ рядка — той самий, що ключ
       плашки нижче: для вкладення це БІК (дизайнер читає «зверху 9»), для
       решти боку не існує взагалі, і чесно назвати можна лише вісь. */
    this._setMeas({
      mode: 'pair',
      kind: res.kind,
      rows: res.guides.map((g) => ({
        key: res.kind === 'inside' ? g.from.side : g.axis, px: g.px,
      })),
    });
    Object.assign(this._anch.style, { left: `${a.left}px`, top: `${a.top}px`,
                                      width: `${a.width}px`, height: `${a.height}px` });
    this._anch.classList.remove('hidden');
    this._rul.classList.remove('hidden');
    for (const d of DIRS) {
      this._rline[d].classList.add('hidden');
      this._rlab[d].classList.add('hidden');
    }
    const px = (v) => `${v}px`;
    const rect = { a, b };
    const plan = [];
    res.guides.forEach((g, i) => {
      const slot = DIRS[i];
      if (!slot) return;                       // напрямних більше за слоти не буває
      const line = this._rline[slot];
      const lab = this._rlab[slot];
      const vert = g.axis === 'y';
      const p1 = rect[g.from.rect][g.from.side];
      const p2 = rect[g.to.rect][g.to.side];
      const lo = Math.min(p1, p2);
      /* Поперек осі: середина СПІЛЬНОЇ смуги, якщо вона є. Немає (діагональ) —
         край якоря, тобто кут «Г» сідає на його межу, а не в порожнечу. */
      const band = vert
        ? cross(a.left, a.right, b.left, b.right, a.left, a.right)
        : cross(a.top, a.bottom, b.top, b.bottom, a.top, a.bottom);
      line.className = `rg ${vert ? 'v' : 'h'}${res.kind === 'overlap' ? ' lap' : ' box'}`;
      Object.assign(line.style, vert
        ? { left: px(band), top: px(lo), width: '0px', height: px(g.px) }
        : { left: px(lo), top: px(band), width: px(g.px), height: '0px' });
      line.classList.remove('hidden');
      lab.className = `rlab${res.kind === 'overlap' ? ' lap' : ' box'}`;
      lab.textContent = String(Math.round(g.px));
      lab.setAttribute('data-kind', res.kind);
      /* Ключ плашки: для вкладення це бік (дизайнер читає «зверху 9»), для
         решти — вісь, бо боку в них немає. */
      lab.setAttribute('data-ruler-label',
        res.kind === 'inside' ? g.from.side : `${g.axis}${i}`);
      lab.classList.remove('hidden');
      /* Плашка від'їжджає ВІД ЯКОРЯ: `edge` — його край на цій напрямній. */
      const fromA = g.from.rect === 'a';
      plan.push({ lab, vert, mid: band, gap: g.px,
                  edge: fromA ? p1 : p2, away: fromA ? 1 : -1 });
    });
    if (!plan.length) return;
    for (const p of plan) {
      const r = p.lab.getBoundingClientRect();
      p.len = p.vert ? r.height : r.width;
      p.thick = p.vert ? r.width : r.height;
    }
    this._spread(plan);
    for (const p of plan) {
      Object.assign(p.lab.style, p.vert
        ? { left: `${p.mid}px`, top: `${p.at}px` }
        : { left: `${p.at}px`, top: `${p.mid}px` });
    }
  },

  /** Куди поставити центри плашок по осі вимірювання (`at` у кожному пункті).
   *
   *  Задум був простий: плашка стоїть посередині зазору, який міряє. На дрібному
   *  елементі він розсипається — зазор 9px, плашка 20px: чотири плашки складались
   *  у злиплий плюс поверх самої кнопки, і не читалась ЖОДНА. Іконки, чипи,
   *  бейджі, кнопки — саме те, що дизайнер міряє найчастіше, тож це не косметика.
   *
   *  Правило: плашка лишається в зазорі, ПОКИ в нього влазить, а не влазить —
   *  виїжджає за ДАЛЕКИЙ від елемента кінець своєї напрямної. Так вона
   *   — лишається на осі напрямної, впритул за її кінцем: видно, до чого
   *     належить число (як виносна лінія в креслярському розмірі);
   *   — не накриває елемент, який міряють, — а накривала, і саме тому 36×36 із
   *     зазорами 9px виглядав зіпсованим ще до того, як плашки почали злипатись;
   *   — розходиться з рештою трьох: кожна відʼїжджає на (зазор + пів-розміру),
   *     і кутові пари, які злипались, розводяться.
   *
   *  Чого тут НЕМА і не буде: «не влізло, тому не показуємо». Зникле число
   *  дизайнер прочитає як «відстані немає» — це та сама тиха неправда, від якої
   *  бережеться вся інша геометрія лінійки. Тому плашка може налізти на сусіда
   *  чи на власний контейнер, але не зникнути й не поїхати за екран. */
  _spread(plan) {
    const vp = viewportBox();
    /* Притиснути центр так, щоб плашка лишилась на екрані ЦІЛОЮ. Один піксель
       відступу — щоб не зливалася з межею. */
    const hold = (p, at) => {
      const half = p.len / 2;
      const room = p.vert ? vp.bottom : vp.right;
      return Math.max(half + 1, Math.min(room - half - 1, at));
    };
    for (const p of plan) {
      p.at = hold(p, p.gap >= p.len
        ? p.edge + p.away * (p.gap / 2)                    // влазить — посередині
        : p.edge + p.away * (p.gap + PILL_PAD + p.len / 2));  // ні — за напрямну
    }
    /* Лишок: на елементі з НУЛЬОВИМИ зазорами (іконка, що точно заповнює свій
       контейнер) виїжджати нікуди — далекий кінець напрямної там збігається з
       краєм елемента, і кутові плашки перетинаються навіть після виїзду. Тоді
       відсуваємо ПІЗНІШУ в порядку DIRS ще на крок від елемента. Порядок
       фіксований, щоб число не стрибало між двома однаково правильними
       положеннями при кожному перемалюванні. */
    for (let pass = 0; pass < PILL_PASSES; pass += 1) {
      let moved = false;
      for (let i = 0; i < plan.length; i += 1) {
        for (let j = i + 1; j < plan.length; j += 1) {
          if (!pillsHit(plan[i], plan[j])) continue;
          const p = plan[j];
          const at = hold(p, p.at + p.away * (p.len / 2 + PILL_PAD));
          if (at === p.at) continue;   // упритул до краю екрана — далі нікуди
          p.at = at;
          moved = true;
        }
      }
      if (!moved) break;
    }
  },

  /** Підсвітка margin-боксу і padding-боксу. false — показувати нічого. */
  _frame(el) {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const n = (v) => parseFloat(v) || 0;
    const m = { t: n(cs.marginTop), r: n(cs.marginRight), b: n(cs.marginBottom), l: n(cs.marginLeft) };
    const p = { t: n(cs.paddingTop), r: n(cs.paddingRight), b: n(cs.paddingBottom), l: n(cs.paddingLeft) };
    Object.assign(this._hl.style, {
      left: `${r.left - m.l}px`, top: `${r.top - m.t}px`,
      width: `${r.width + m.l + m.r}px`, height: `${r.height + m.t + m.b}px`,
    });
    Object.assign(this._pad.style, {
      left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px`,
      borderStyle: 'solid', borderColor: 'transparent',
      borderTopWidth: `${p.t}px`, borderRightWidth: `${p.r}px`,
      borderBottomWidth: `${p.b}px`, borderLeftWidth: `${p.l}px`,
    });
    this._hl.classList.remove('hidden');
    this._pad.classList.remove('hidden');
    this._rect = r;
    this._cs = cs;
    return true;
  },

  /**
   * Намалювати підсвітку + вміст тултипа для елемента (null — сховати все) і
   * СКАЗАТИ про це батьківському вікну.
   *
   * Обгортка навколо `_draw`, а не лічильник у трьох місцях самого малювання,
   * і причина конкретна: `_draw` виходить достроково у двох гілках
   * (`_frame` не дав коробки; режим лінійки). Лічильник у кінці тіла
   * пропустив би найважливіший випадок — `set(false)` знімає пін і кличе
   * `_paint(null)`, тобто вихід саме через `_hide()`. `_pinWas` лишився б
   * указувати на старий елемент, і наступний пін ТОГО САМОГО елемента
   * (найчастіший сценарій: вимкнув інспектор, увімкнув, клацнув туди ж)
   * не змінив би сигнатуру — панель батька лишилась би порожньою.
   */
  _paint(el) {
    if (this.pinned !== this._pinWas) {
      this._pinWas = this.pinned;
      this._pinSeq += 1;
    }
    /* `finally`: якщо малювання впало на чужому макеті (а воно ходить по
       живому CSSOM), батько все одно мусить дізнатись про стан — мовчазний
       сигнал розійшовся б із реальністю назавжди, бо наступного `_paint` без
       руху курсора може не бути. Виняток `finally` не ковтає. */
    try { this._draw(el); } finally { this._emit(); }
  },

  /** Власне малювання. Кличеться ЛИШЕ з `_paint` — саме він рахує покоління
   *  звіту й сигналить назовні. */
  _draw(el) {
    if (!this._frame(el)) { this._hide(); return; }
    // Режим лінійки: ні тултипа, ні каскадної панелі. Тултип ходить за курсором
    // рівно там, де лежать плашки, а панель (320px праворуч) накриває той самий
    // макет, у якому дизайнер зараз читає праву напрямну.
    if (this.mode === 'ruler') {
      this._tip.classList.add('hidden');
      this._panel.classList.add('hidden');
      this._ruler(el);
      return;
    }
    this._rul.classList.add('hidden');
    /* Напрямні сховано — отже, виміру немає. Лишити тут числа означало б
       показувати в панелі лінійку, вимкнену на самому макеті. */
    this._setMeas(null);
    const r = this._rect;
    const cs = this._cs;
    this._tip.innerHTML = `<b>${esc(label(el))}</b> <span class="dim">${Math.round(r.width)} × ${Math.round(r.height)}</span><br>`
      + `<span class="dim">font</span> ${esc(cs.fontWeight)} ${esc(cs.fontSize)}/${esc(cs.lineHeight)} ${esc(cs.fontFamily.split(',')[0])}<br>`
      + `<span class="dim">color</span> ${esc(cs.color)}`;
    this._tip.classList.remove('hidden');
    this._place();
    if (this.pinned) { this._tip.classList.add('hidden'); this._renderPanel(); }
    else this._panel.classList.add('hidden');
  },

  /**
   * Плаваюче вікно звіту — для сторінки, відкритої БЕЗ канваса.
   *
   * Малює його `reportHTML` — ТОЙ САМИЙ рендерер, що й права панель оболонки.
   * Один рендерер, один payload (`report()`), дві точки монтування. До
   * 17.09.2026 тут стояла друга, власна розмітка з власними заголовками
   * секцій (`_titles`) і власними бейджами (`_badge`): два описи одного звіту
   * розходяться не «колись», а на першій же правці — і розійшлись би тим
   * помітніше, що одна копія перекладається, а друга була українською назавжди.
   *
   * ⛔ У КАНВАСІ вікна немає взагалі (`_chrome`): звіт там показує права
   * панель оболонки, а плаваюче вікно накривало б собою правий край того
   * самого макета, який дизайнер зараз вимірює. На голій сторінці воно
   * лишається — там більше нема кому показати каскад.
   *
   * Кнопки «закрити» (`✕`) у вікні більше немає: її малювала саме та власна
   * розмітка, а знімає пін і без неї `Escape` (драбинка в `_onKey`) або
   * повторний клік по тому самому елементу (`_onDown`).
   *
   * ⛔ `tunable: false`, і другого шляху проводки сюди НЕ буде. Ручки тюнера
   * веде `BAR_ACTIONS` (`app/app.js`), тобто БАТЬКІВСЬКЕ вікно, а модель
   * тюнера живе там свідомо: рамка макета перезавантажується, модель — ні. У
   * цього документа батька може не бути взагалі (голу сторінку відкривають
   * прямо), тож ручці тут нема ні кого слухати, ні куди писати. До 18.09.2026
   * рендерер малював їх безумовно, і на `/commented?…` стояло 15 крутилок і 3
   * пікери, жодна з яких ні на що не реагувала. Чесний текст замість мертвої
   * ручки — не деградація, а єдина правда, яку цей документ може сказати.
   * Прапорець тут ЯВНИЙ, хоч типове значення й так `false`: читач цього
   * методу не мусить знати типове значення чужого модуля, щоб побачити межу.
   */
  _renderPanel() {
    if (!this._chrome) { this._panel.classList.add('hidden'); return; }
    const html = reportHTML(this.report(), { tunable: false });
    if (!html) { this._panel.classList.add('hidden'); return; }
    this._panel.innerHTML = html;
    this._panel.scrollTop = 0;
    this._panel.classList.remove('hidden');
  },

  _place() {
    const pt = this._pt || { x: 20, y: 20 };
    const b = this._tip.getBoundingClientRect();
    const x = Math.min(pt.x + 16, window.innerWidth - b.width - 8);
    const y = Math.min(pt.y + 18, window.innerHeight - b.height - 8);
    this._tip.style.left = `${Math.max(8, x)}px`;
    this._tip.style.top = `${Math.max(8, y)}px`;
  },
};

window.CanvasInspector = Inspector;
if (document.readyState !== 'loading') Inspector.init();
else document.addEventListener('DOMContentLoaded', () => Inspector.init());
