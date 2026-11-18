/**
 * Чиста модель ТЮНЕРА: що дизайнер накрутив на макеті і в якому вигляді це
 * поїде Клоду.
 *
 * ⛔ ТЮНЕР НЕ ПИШЕ НІЧОГО — ні у файл макета, ні в шар коментарів. Ручка жива
 * (дизайнер бачить зміну одразу), а ВИХІД — пакет РЕКОМЕНДАЦІЙ: «елемент →
 * властивість → було/стало». Макет лишається джерелом правди рівно тому, що
 * тюнер у нього не пише; правку в код робить Клод, прочитавши пакет. Саме це
 * знімає заперечення, записане при випуску лінійки («редагування з оверлея ми
 * свідомо не брали — макет наше джерело правди»).
 *
 * Шкала ручки ВІЛЬНА: дизайнер крутить як бачить. Зведення значення до токена
 * дизайн-системи — робота КЛОДА, не тюнера: значення ДС приходять із проду, а
 * не з ока дизайнера (`ds-source-of-truth`). Тому пакет несе не «правильне
 * значення», а те, що дизайнер накрутив, плюс ПОХОДЖЕННЯ старого значення.
 *
 * Стан живе в БАТЬКІВСЬКОМУ вікні, не в документі макета: `render()` щоразу
 * переприсвоює `frame.src` і перевантажує макет (`app/app.js:129`), тож усе,
 * покладене в документ макета, тихо стирає будь-який клік у смузі. Сама модель
 * — чиста: ні DOM, ні мережі, ні сховища, ні годинника. Живе застосування до
 * елемента, UI, канал до сервера й збереження приходять окремими задачами; тут
 * їх немає свідомо.
 *
 * ── ДВА СЕЛЕКТОРИ, і плутати їх не можна ────────────────────────────────────
 * `selector` ЕЛЕМЕНТА — це ланцюжок предків із `identity()`, склеєний у шлях
 * (`body > div.wrap > p.card`). Він стабільний для всього елемента, і саме за
 * ним edits групуються та адресується `clearEdit`.
 * `rule` ПРАВКИ — селектор правила, що виграло каскад ДЛЯ ЦІЄЇ властивості
 * (`.card` для `padding`, `#target` для `color`). Він у кожної властивості
 * СВІЙ, тому живе всередині правки, а не в елемента: узявши його за ключ
 * елемента, ми розсипали б один блок на кілька «елементів» рівно тоді, коли
 * дизайнер крутить у ньому дві ручки, — тобто зламали б те, заради чого
 * групування й існує («цей блок — ось ці правки»).
 */
import { isSpaceProfile, normalizeValue } from './vendor/inspector-core.js';

/** Самоописовість пакета: читач приходить у ІНШІЙ сесії, без цього контексту. */
export const PKG_KIND = 'design-canvas.tuner.recommendations';
export const PKG_VERSION = 1;

/**
 * Стан пакета для ЧИТАЧА (T-39): `draft` — дизайнер іще крутить, `ready` — він
 * натиснув «Надіслати Клоду».
 *
 * ⛔ Навіщо це поле взагалі. Зберігається пакет АВТОМАТИЧНО, на кожну правку
 * (`saveTune`, `app/app.js`), і саме так і мусить: нічого не губиться. Але
 * читач від цього не міг відрізнити «дизайнер щойно крутнув ручку й крутить
 * далі» від «дизайнер закінчив» — на диску обидва стани виглядають однаково.
 * `status` і є тією єдиною різницею, якої бракувало; кнопка нічого не
 * надсилає (канал і так пише щоразу), вона СИГНАЛІЗУЄ завершення.
 *
 * ⚠️ БУДЬ-ЯКА наступна зміна вертає `draft`, і це не зручність, а той самий
 * закон, що й решта цього файла: пакет, який каже «готово», поки дизайнер
 * далі крутить ручки, бреше читачеві — а брехати про стан роботи тут
 * дорожче, ніж не мати поля зовсім.
 */
export const PKG_STATUS_DRAFT = 'draft';
export const PKG_STATUS_READY = 'ready';

/** Рівень підказки, коли `tier` не дійшов. Невідоме — це ЗДОГАД, не факт:
 *  назвати його 'used' означало б відмити здогад у доведення, а ціна саме цієї
 *  помилки вже виміряна (токен z-index, порекомендований для font-weight). */
const TIER_GUESS = 'shape';

/**
 * Інструкція всередині пакета. Англійською і в самих даних — свідомо:
 *  · читач — машина в наступній сесії, а не дизайнер, тож це не інтерфейс і
 *    не місце для словника (`t()` віддав би мову ПОТОЧНОГО вікна, і сенс
 *    пакета залежав би від того, якою мовою дизайнер читає панель);
 *  · без неї `tier: 'shape'` — просто слово в JSON. Саме через втрату цього
 *    рівня повертається дефект, який щойно полагодили: здогад читається як
 *    рекомендація і застосовується мовчки.
 */
const INSTRUCTIONS = [
  'Recommendations from the design-canvas tuner. The designer turned these values live in the inspector overlay. NOTHING was written to the mockup or to the comment layer: nothing here is applied yet, and the mockup is still the source of truth.',
  'An element is identified by several independent signals, because this package is read AFTER the page may have been rewritten: `trail` (ancestor labels, root first), `label` (the element itself), `text` (a snippet of its own text) and `selector` (that trail as a CSS path). Locate the element by agreement between them, not by `selector` alone.',
  'Inside an edit: `prop` is the CSS property; `from` is the value the browser showed before tuning; `to` is what the designer turned it to; `raw` is the value as written in CSS; `rule` is the selector of the rule that won the cascade for this property, that is WHERE to edit. `rule` equal to "[style]" means the winning declaration was the element inline style attribute; `rule` null means no rule of ours won and you have to find the source yourself.',
  '`to` is a free-scale value from the designer eye, NOT a design-system token. Reducing it to a token is YOUR job: design-system values come from production, not from this package.',
  '`verdict` describes the value BEFORE tuning: "token" - it came from a var() that resolved to what the browser showed; "hardcode" - a literal past the design system; "unlinked" - the source was not found or could not be proven.',
  '`hint` lists design-system tokens whose value matches the original one. tier "used" is a FACT: that token is already used in this document for this family of properties. tier "shape" is a GUESS: the token is declared but never used anywhere, and only the shape of its value matches - do NOT apply a "shape" hint without asking the designer to confirm it first.',
  'An empty `hint` means no token matched. Do not invent a nearest token; say that none exists.',
  'Each hint also carries `ds`: true means the token is a real design-system token for this track, false means it is only declared somewhere in the mockup. Two hints that look alike lead opposite ways - one back into the design system, the other into yet another home-made variable. Prefer `ds: true`.',
  '`verdict` "off-ds" means the value did come from a var(), but that variable is NOT in the design system - the mockup invented it. `verdict` "overridden" is the severe one: the variable name IS a design-system token, but the mockup redefined it with a different value, so the code looks correct everywhere while behaving differently; `dsValues` then lists what the design system prescribes for that name.',
  '`snap` is present when the designer pressed the verdict dot to go BACK to the design system. It means the designer chose a TOKEN, not a number: write `var(<snap.token>)` at `rule`, do NOT write the literal in `to`. `to` carries that token design-system value only so you can see what it will look like. When `snap` is present and `from` equals `to`, nothing changed visually and the whole point of the edit is the token.',
  'The design system checked against is named by `ds` at the top of this package. `ds.known` false means this track has no design system at all (the `seo` site theme lives outside it on purpose), so no verdict here says anything about the design system. A `ds.profile` of the form `space:<id>` is NOT a product track and NOT the production design system: it is the designer space own token file, named in `ds.source`, so a verdict there only means "matches the tokens of that file".',
  '`status` tells you whether the designer is done. "draft": they are still tuning, the package is saved after every single knob turn, so treat it as work in progress and do not act on it yet. "ready": they pressed "Send to AI" - this is the package they mean. Any edit after that flips it back to "draft", so "ready" always describes the package exactly as it stands.',
  'When you have applied the package to the mockup, clear it with one request: POST /api/tuner {"action": "clear"} on the design-canvas server. Do not edit or empty the file by hand: the designer tab picks the change up only through the server, and a stale "ready" left behind reads as "still waiting for Claude".',
];

/** Порожній стан. `pages` — щоб сусідні сторінки не бачили правок одна одної
 *  (дизайнер ходить по сторінках однієї ітерації, і правка з «Головної» в
 *  пакеті «Пошуку» була б неправдою про те, де він її бачив). */
export function emptyTune() {
  return { pages: {}, note: '', status: PKG_STATUS_DRAFT,
    ds: { profile: null, known: false } };
}

/** `ds` пакета з довільного входу (звіт інспектора, файл на диску): профіль і
 *  чи ДС відома — і, ЛИШЕ для профілю простору (`space:<id>`), `source`, імʼя
 *  файла, з якого читались токени.
 *
 *  Чому `source` їде в пакет: `space:<id>` каже, ЧИЯ це ДС, але не з чого вона
 *  зібрана, а Клод у наступній сесії читає пакет без канваса й без простору
 *  під руками. Статичний напрямок (`united`) у цьому не потребує нічого —
 *  його ДС відома всім, — тож форма `{profile, known}` для нього лишається
 *  рівно такою, якою була: `commit`/`figma` звіту інспектора в пакет не їдуть
 *  (їх читач не може перевірити), а `source`, що прийшов при статичному
 *  профілі, — чужа рука, і ігнорується. Непридатний `source` простору — порожній
 *  рядок, а не `undefined`: поле або є рядком, або його немає зовсім. */
function dsOf(info) {
  const profile = info && typeof info.profile === 'string' && info.profile
    ? info.profile : null;
  const known = !!(info && info.known);
  if (profile && isSpaceProfile(profile)) {
    return { profile, known, source: typeof info.source === 'string' ? info.source : '' };
  }
  return { profile, known };
}

/** Записати, під якою ДС читається ця сесія. Окремо від правок: це факт про
 *  ЗАДАЧУ, а не про елемент, і в кожній правці він повторювався б однаково. */
export function setDs(state, info) {
  const st = stateOf(state);
  const ds = dsOf(info);
  if (st.ds && st.ds.profile === ds.profile && st.ds.known === ds.known
      && st.ds.source === ds.source) return st;
  /* НЕ через `drafted`: напрямок задачі — не правка дизайнера, і скидати
     через нього «готово» означало б знімати завершення подією, якої людина
     не робила (та сама причина, що в `setNote` для незміненого тексту). */
  return { ...st, ds };
}

/** Стан пакета з довільного стану, і завжди в бік ОБЕРЕЖНОСТІ: усе, що не є
 *  дослівним `ready`, — чернетка. Старий стан (з диска, з версії до T-39)
 *  поля не має зовсім, і назвати таке «готовим» означало б підтвердити
 *  завершення, якого ніхто не оголошував. */
function statusOf(st) {
  return st.status === PKG_STATUS_READY ? PKG_STATUS_READY : PKG_STATUS_DRAFT;
}

/** Зміна пакета — це завжди повернення в чернетку. Одна функція на всі
 *  мутатори, бо «десь забули скинути `ready`» ззовні виглядає як тиша: панель
 *  показує «готово», читач вірить, а правка вже інша. */
function drafted(st, patch) {
  return { ...st, ...patch, status: PKG_STATUS_DRAFT };
}

/** Своя властивість, а не успадкована. Без цього `edits['constructor']` віддав
 *  би функцію з прототипу — тобто правку, якої ніхто не робив. */
function own(obj, key) {
  return !!obj && Object.prototype.hasOwnProperty.call(obj, key);
}

/** Сміття на вході не сміє валити модель, від якої залежить панель. */
function stateOf(state) {
  return state && typeof state === 'object' && state.pages && typeof state.pages === 'object'
    ? state
    : emptyTune();
}

function pageKey(page) {
  const p = typeof page === 'string' ? page.trim() : '';
  return p || null;
}

function str(v) {
  return v == null ? '' : String(v);
}

/**
 * Ключ елемента — шлях із крихт (`body > div.wrap > p.card`).
 *
 * Експортується навмисно: панель мусить уміти спитати «а чи є правки на ЦЬОМУ
 * елементі», і друга реалізація ключа поруч із цією розійшлася б на першій же
 * правці. Ланцюжок, а не самий підпис: `p.card` у макеті буває десять разів, і
 * правки десяти різних карток схлопнулись би в одну.
 */
export function elementKey(ident) {
  if (!ident || typeof ident !== 'object') return null;
  const trail = Array.isArray(ident.trail)
    ? ident.trail.filter((s) => typeof s === 'string' && s)
    : [];
  if (trail.length) return trail.join(' > ');
  return typeof ident.label === 'string' && ident.label ? ident.label : null;
}

/** Скільки ручок накручено ВСЬОГО (по всіх сторінках). Панелі — для лічильника
 *  на кнопці, тестам — для найдешевшого доказу, що правку прибрано насправді. */
export function editCount(state) {
  const st = stateOf(state);
  let n = 0;
  for (const elems of Object.values(st.pages)) {
    for (const el of Object.values(elems)) n += Object.keys(el.edits || {}).length;
  }
  return n;
}

/** Копія підказок із ЯВНИМ перенесенням `tier`. Розсип `...h` тут був би
 *  дірою в інший бік: у пакет поїхало б усе, що колись доліпили до підказки. */
function hintOf(hint) {
  if (!Array.isArray(hint)) return [];
  const out = [];
  for (const h of hint) {
    if (!h || typeof h.name !== 'string' || !h.name) continue;
    /* `ds` — чи цей кандидат із САМОЇ дизайн-системи, а не з токенів макета.
       Без нього дві підказки в пакеті виглядають однаково, хоча ведуть у
       протилежні боки: одна — назад у ДС, друга — в ще один самопальний
       токен. Типове значення `false`, і саме в цей бік: невідоме не сміє
       видавати себе за системне. */
    out.push({ name: h.name, tier: typeof h.tier === 'string' && h.tier ? h.tier : TIER_GUESS,
      ds: h.ds === true });
  }
  return out;
}

/**
 * Копія `snap` — адреси ДОРОГИ НАЗАД У ДС, з перевіркою поіменно (та сама
 * причина, що в `hintOf`: у пакет не сміє поїхати все, що колись доліпили).
 *
 * ⛔ ЧОМУ ЦЕ ОКРЕМЕ ПОЛЕ, А НЕ ПРОСТО ЗНАЧЕННЯ В `to`. Читач пакета мусить
 * знати, що дизайнер вибрав ТОКЕН, а не число: правка `color: #1A1C1F` і
 * правка «постав тут `var(--color-neutral-solid-1000)`» — це різний код, і
 * друга саме та, заради якої T-40 і робився. Без цього поля Клод вписав би
 * літерал і мовчки додав би ще один хардкод повз ДС.
 */
function snapOf(snap) {
  if (!snap || typeof snap !== 'object') return null;
  const token = typeof snap.token === 'string' && snap.token ? snap.token : null;
  if (!token || snap.value == null) return null;
  return { token, value: String(snap.value) };
}

/**
 * Записати накручене значення. Новий стан, старий не чіпаємо.
 *
 * @param {object} state  стан із `emptyTune()`
 * @param {string} page   id сторінки — межа видимості правок
 * @param {object} ident  пакет ознак елемента з `CanvasInspector.identity(prop)`
 * @param {object} decl   рядок звіту з `describe()` — звідти `from` і ПОХОДЖЕННЯ
 * @param {string} to     що дизайнер накрутив
 *
 * Два рішення, які легко зіпсувати непомітно:
 *
 *  1. `from` записується ОДИН РАЗ і далі не рухається. Повторний поворот ручки
 *     рухає лише `to`. Інакше після трьох поворотів «було» дорівнює «стало», і
 *     весь пакет перестає щось означати: Клод побачить правку з 18px на 18px.
 *  2. Повернення значення до початкового ПРИБИРАЄ правку зовсім, а не пише
 *     правку-пустушку. Звірка — через `normalizeValue`, тим самим міряльним
 *     інструментом, що й решта інспектора: інакше `#FFF` проти `#ffffff` (чи
 *     `0` проти `0px`) лишили б у пакеті привида, і Клод правив би код заради
 *     зміни, якої немає.
 */
export function setEdit(state, page, ident, decl, to, opts = {}) {
  const st = stateOf(state);
  const p = pageKey(page);
  const key = elementKey(ident);
  const prop = decl && typeof decl.prop === 'string' && decl.prop ? decl.prop : null;
  // Правка, яку нікуди прикласти, — це не правка. Тихо: клік по елементу, що
  // саме зник із документа, не помилка дизайнера.
  if (!p || !key || !prop) return st;

  const pageElems = own(st.pages, p) ? st.pages[p] : null;
  const elem = pageElems && own(pageElems, key) ? pageElems[key] : null;
  const was = elem && own(elem.edits, prop) ? elem.edits[prop] : null;

  const from = was ? was.from : str(decl.computed);
  const value = str(to);
  const snap = snapOf(opts.snap);
  /* ⛔ ВИНЯТОК ІЗ ПРАВИЛА «те саме значення — не правка», і він несучий.
     Повернення до токена ДС здебільшого НЕ МІНЯЄ ЖОДНОГО ПІКСЕЛЯ: токен
     пропонується саме тому, що його значення дорівнює поточному. Змінюється
     інше — те, ЧИМ це значення записано в коді (`#1A1C1F` → `var(--…)`), і
     це і є вся правка. Скинути її як пустушку означало б, що кнопка
     «повернути до ДС» натискається, а в пакет не їде нічого: дизайнер бачить
     реакцію, Клод не отримує замовлення. Коли ж дизайнер просто відкрутив
     ручку назад (без `snap`), стара поведінка лишається дослівно. */
  if (!snap && normalizeValue(value) === normalizeValue(from)) {
    return clearEdit(st, p, key, prop);
  }

  /* Походження знімається з ПЕРШОГО повороту й далі не перечитується: тюнер у
     макет не пише, тож ні `raw`, ні переможець каскаду від кручення ручки не
     міняються — а от перезняти їх пізніше означало б підмішати в пакет стан
     іншої миті (курсор уже на іншому елементі, `:hover` уже інший). */
  /* `snap` переприсвоюється ЗАВЖДИ, зокрема в null: дизайнер, що після
     повернення до токена крутнув ручку далі, вибрав уже не токен, і
     застарілий `snap` у пакеті велів би Клоду вписати `var()` зі старим
     значенням — тобто зробити не те, що людина бачить на екрані. */
  const edit = was ? { ...was, to: value, snap } : {
    prop,
    from,
    to: value,
    rule: typeof ident.selector === 'string' && ident.selector ? ident.selector : null,
    raw: decl.raw == null ? null : String(decl.raw),
    token: decl.token == null ? null : String(decl.token),
    tokenValue: decl.tokenValue == null ? null : String(decl.tokenValue),
    verdict: typeof decl.verdict === 'string' ? decl.verdict : null,
    /* Що ДС приписує імені — лише для 'overridden'; для решти вироків це
       null, і в пакеті поля просто не буде значущого вмісту. */
    dsValues: Array.isArray(decl.ds) ? decl.ds.map((v) => String(v)) : null,
    hint: hintOf(decl.hint),
    snap,
  };

  /* Нова правка вертає пакет у чернетку (`drafted` нижче) — навіть якщо
     дизайнер щойно натиснув «Надіслати»: він крутить далі, отже «готово» вже
     не про цей пакет. */
  const pages = { ...st.pages };
  const elems = { ...(pageElems || {}) };
  elems[key] = elem
    ? { ...elem, edits: { ...elem.edits, [prop]: edit } }
    : {
      selector: key,
      label: typeof ident.label === 'string' ? ident.label : '',
      trail: Array.isArray(ident.trail) ? ident.trail.filter((s) => typeof s === 'string') : [],
      text: typeof ident.text === 'string' ? ident.text : '',
      edits: { [prop]: edit },
    };
  pages[p] = elems;
  return drafted(st, { pages });
}

/**
 * Прибрати ОДНУ правку — не весь елемент.
 *
 * @param {string} selector ключ ЕЛЕМЕНТА (поле `selector` у пакеті), не `rule`
 *                          правки — див. шапку файла.
 *
 * Елемент і сторінка зникають самі, коли в них не лишилось правок: порожній
 * елемент у пакеті читався б як «тут щось крутили», а це неправда.
 */
export function clearEdit(state, page, selector, prop) {
  const st = stateOf(state);
  const p = pageKey(page);
  if (!p || !own(st.pages, p)) return st;
  const elems0 = st.pages[p];
  if (typeof selector !== 'string' || !own(elems0, selector)) return st;
  const elem = elems0[selector];
  if (typeof prop !== 'string' || !own(elem.edits, prop)) return st;

  const edits = { ...elem.edits };
  delete edits[prop];
  const elems = { ...elems0 };
  if (Object.keys(edits).length) elems[selector] = { ...elem, edits };
  else delete elems[selector];
  const pages = { ...st.pages };
  if (Object.keys(elems).length) pages[p] = elems;
  else delete pages[p];
  return drafted(st, { pages });
}

/** Записка Клоду вільним текстом. Окреме поле пакета, а не ще одна «правка»:
 *  вона про задачу цілком («зроби це щільніше»), а не про одну властивість.
 *
 *  ⚠️ Той самий текст — НЕ зміна, і повертати через нього пакет у чернетку не
 *  можна: панель шле сюди значення поля, а поле віддає його й тоді, коли
 *  дизайнер нічого не набрав (клік, вставка того ж тексту). Інакше «готово»
 *  знімалось би подією, якої не було. */
export function setNote(state, note) {
  const st = stateOf(state);
  const text = typeof note === 'string' ? note : '';
  if (st.note === text) return st;
  return drafted(st, { note: text });
}

/**
 * «Надіслати Клоду»: сказати, що пакет у тому вигляді, який дизайнер мав на
 * увазі.
 *
 * ⛔ НІЧОГО НЕ НАДСИЛАЄ і нічого не зберігає: збереження автоматичне й
 * незмінне (`saveTune`, `app/app.js`), пакет на диску вже свіжий. Єдине, що
 * тут стається, — читач отримує відповідь на питання, якої в нього досі не
 * було: «дизайнер іще крутить чи вже закінчив».
 */
export function markReady(state) {
  const st = stateOf(state);
  if (statusOf(st) === PKG_STATUS_READY) return st;
  return { ...st, status: PKG_STATUS_READY };
}

/**
 * Пакет із ДИСКА назад у стан — зворотний бік `packageJSON`.
 *
 * Навіщо взагалі зворотний бік. Пакет пишеться на кожну правку (`saveTune`,
 * `app/app.js`), і файл переживає перезавантаження САМОГО канваса. Без
 * читання назад перший же поворот ручки після ⌘R записав би поверх файла
 * пакет із однієї правки — тобто мовчки стер би роботу, яку дизайнер уважав
 * збереженою. Канал, у який лише пишуть, не зберігає: він затирає.
 *
 * ⚠️ Вхід — ФАЙЛ, тобто не наші дані: його міг зіпсувати редактор, обірваний
 * запис чи чужа рука. Тому кожне поле перевіряється поіменно, а непридатний
 * запис ПРОПУСКАЄТЬСЯ, а не валить розбір: одна побита правка не сміє
 * коштувати всіх інших. `page`/`selector`/`prop` обовʼязкові — без них правку
 * нікуди прикласти (та сама умова, що в `setEdit`).
 *
 * Дзеркальність до `packageJSON` не декоративна: її стереже тест
 * «packageJSON → fromPackage → packageJSON дає те саме».
 */
export function fromPackage(pkg) {
  const st = emptyTune();
  if (!pkg || typeof pkg !== 'object') return st;
  if (typeof pkg.note === 'string') st.note = pkg.note;
  /* Стан читаємо ДОСЛІВНО і лише `ready`: файл могла записати старіша версія
     інструмента (поля немає) або чужа рука (будь-що), і в обох випадках
     чернетка — єдина чесна відповідь. */
  if (pkg.status === PKG_STATUS_READY) st.status = PKG_STATUS_READY;
  if (pkg.ds && typeof pkg.ds === 'object') st.ds = dsOf(pkg.ds);
  const elements = Array.isArray(pkg.elements) ? pkg.elements : [];
  for (const el of elements) {
    if (!el || typeof el !== 'object') continue;
    const p = pageKey(el.page);
    const key = typeof el.selector === 'string' && el.selector ? el.selector : null;
    if (!p || !key) continue;
    const edits = {};
    for (const e of Array.isArray(el.edits) ? el.edits : []) {
      if (!e || typeof e !== 'object') continue;
      const prop = typeof e.prop === 'string' && e.prop ? e.prop : null;
      if (!prop) continue;
      edits[prop] = {
        prop,
        from: str(e.from),
        to: str(e.to),
        rule: e.rule == null ? null : String(e.rule),
        raw: e.raw == null ? null : String(e.raw),
        token: e.token == null ? null : String(e.token),
        tokenValue: e.tokenValue == null ? null : String(e.tokenValue),
        verdict: typeof e.verdict === 'string' ? e.verdict : null,
        dsValues: Array.isArray(e.dsValues) ? e.dsValues.map((v) => String(v)) : null,
        hint: hintOf(e.hint),
        snap: snapOf(e.snap),
      };
    }
    // Елемент без жодної придатної правки не заводимо: порожній елемент у
    // стані читався б як «тут щось крутили» — та сама неправда, від якої
    // `clearEdit` прибирає елемент, коли правок не лишилось.
    if (!Object.keys(edits).length) continue;
    const pageElems = own(st.pages, p) ? st.pages[p] : (st.pages[p] = {});
    /* Той самий ключ ЗАКОННО трапляється двічі: `packageJSON` розкладає стан
       у плоский список, і дві сторінки з однаковим селектором дають два
       записи. Зливаємо правки, а не затираємо елемент цілком. */
    const was = own(pageElems, key) ? pageElems[key] : null;
    pageElems[key] = {
      selector: key,
      label: typeof el.label === 'string' ? el.label : (was ? was.label : ''),
      trail: Array.isArray(el.trail)
        ? el.trail.filter((s) => typeof s === 'string')
        : (was ? was.trail : []),
      text: typeof el.text === 'string' ? el.text : (was ? was.text : ''),
      edits: was ? { ...was.edits, ...edits } : edits,
    };
  }
  return st;
}

/**
 * Пакет рекомендацій — те, що поїде Клоду.
 *
 * @param {?string} page фільтр: лише ця сторінка. `null` — усі, і тоді кожен
 *                       елемент несе свою `page` (пакет мусить лишатись
 *                       читабельним і коли дизайнер крутив по кількох екранах).
 *
 * Групування ПО ЕЛЕМЕНТУ — бо так його й читатимуть: «цей блок — ось ці
 * правки». Плоский список правок змусив би читача збирати блок назад руками.
 *
 * Пакет НЕ ділить жодного посилання зі станом (підказки копіюються поіменно):
 * той, хто його отримав, має право його м'яти, і модель від цього не сміє
 * поїхати.
 */
export function packageJSON(state, page = null) {
  const st = stateOf(state);
  const only = pageKey(page);
  const elements = [];
  for (const [p, elems] of Object.entries(st.pages)) {
    if (only && p !== only) continue;
    for (const el of Object.values(elems)) {
      const edits = Object.values(el.edits || {}).map((e) => ({
        ...e,
        dsValues: e.dsValues ? e.dsValues.slice() : null,
        hint: (e.hint || []).map((h) => ({ name: h.name, tier: h.tier, ds: h.ds })),
        /* Поіменно, як і підказки: пакет не ділить зі станом жодного
           посилання — той, хто його отримав, має право його мʼяти. */
        snap: e.snap ? { token: e.snap.token, value: e.snap.value } : null,
      }));
      if (!edits.length) continue;
      elements.push({
        page: p,
        selector: el.selector,
        label: el.label,
        trail: (el.trail || []).slice(),
        text: el.text,
        edits,
      });
    }
  }
  return {
    kind: PKG_KIND,
    version: PKG_VERSION,
    /* Поруч із `kind`/`version`, а не всередині елементів: стан описує ПАКЕТ
       цілком — те, чи дизайнер його вже вважає готовим, — а не окрему
       правку. */
    status: statusOf(st),
    page: only,
    /* Яка саме ДС стоїть за вироками цього пакета. Без цього рядка читач не
       може відрізнити «жодного порушення ДС» від «ДС для цього напрямку
       немає, тому й не перевіряли» — дві протилежні відповіді, що на диску
       виглядають однаково. */
    ds: st.ds || { profile: null, known: false },
    note: st.note,
    editCount: elements.reduce((n, e) => n + e.edits.length, 0),
    instructions: INSTRUCTIONS.slice(),
    elements,
  };
}
