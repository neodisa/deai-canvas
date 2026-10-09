/* Інспектор макета — шар читання документа. Дістає з CSSOM сирі декларації,
   з getComputedStyle — підсумкові значення, і зводить це у звіт про елемент. */
import {
  specificity, compareSpec, pickWinner, varsIn, splitTop, splitBox, normalizeValue,
  tokenIndex, verdict, splitTopLevel, propFamilies, hintFor, orderHints,
  dsIndex, dsVerdict, DS_NONE,
} from './inspector-core.js';
import { DS_PROFILES, DS_SOURCE } from './ds-tokens.js';

/** Групи властивостей для панелі. Порядок = порядок рядків у секції.
 *  flex показуємо і для grid-контейнера (обидва — контекст для align/justify/gap). */
export const GROUPS = {
  box: ['margin-top', 'margin-right', 'margin-bottom', 'margin-left',
        'padding-top', 'padding-right', 'padding-bottom', 'padding-left'],
  layout: ['display', 'width', 'height'],
  flex: ['flex-direction', 'align-items', 'justify-content', 'flex-wrap', 'gap'],
  type: ['font-family', 'font-size', 'font-weight', 'line-height', 'letter-spacing'],
  color: ['color', 'background-color', 'border-color', 'border-width', 'border-radius'],
};

/** Кеш ПО ДОКУМЕНТУ, не глобальний: макет часто живе в iframe, і кеш на
 *  один документ раніше підмішував правила батьківської сторінки в звіт
 *  про елемент фрейму. */
let cache = new WeakMap();

/** Скинути кеш правил (після resize — бо змінюються істинні @media). */
export function invalidate() { cache = new WeakMap(); }

function ruleKind(r) {
  return (r && r.constructor && r.constructor.name) || '';
}

/** Абсолютизувати селектор нативно-вкладеного правила відносно батьківського:
 *  явний `&` — заміна на `:is(<батько>)`; відносний селектор без комбінатора
 *  на початку — неявний нащадок (`& `+селектор); з комбінатором (`>`,`+`,`~`)
 *  — `&` приліплюється впритул. Без батька (верхній рівень) — селектор як є. */
function absolutize(selText, parentSel) {
  if (!parentSel) return selText;
  const parts = splitTopLevel(selText, ',').map((s) => s.trim()).filter(Boolean);
  const out = parts.map((p) => {
    const withAmp = p.includes('&') ? p : (/^[>+~]/.test(p) ? `&${p}` : `& ${p}`);
    return withAmp.replace(/&/g, `:is(${parentSel})`);
  });
  return out.join(', ');
}

/** Усі правила документа, чиї @media/@supports істинні ЗАРАЗ, у порядку появи.
 *  blocked=true — хоч одна таблиця (чи @import) з чужого origin (токени показувати не можна).
 *  partial=true — свідомо пропущений блок, чию застосовність ми не беремося
 *  вгадувати (@container/@scope — не знаємо розміру/меж без реального layout;
 *  @layer — наше ядро не моделює порядок шарів, а неправильний переможець
 *  гірший за чесне «не врахували»). Типи правил розрізняємо ЯВНО за
 *  іменем конструктора — попередній `else if (r.cssRules)` заходив у
 *  @supports/@container/@scope не перевіряючи умову зовсім. */
export function collectRules(doc = document) {
  if (cache.has(doc)) return cache.get(doc);
  const rules = [];
  let blocked = false;
  let partial = false;
  const view = doc.defaultView || window;

  const walk = (list, parentSel) => {
    for (const r of Array.from(list || [])) {
      const kind = ruleKind(r);
      if (kind === 'CSSMediaRule') {
        let ok = true;
        try { ok = view.matchMedia(r.conditionText || r.media.mediaText).matches; } catch (e) { ok = true; }
        if (ok) walk(r.cssRules, parentSel);
      } else if (kind === 'CSSSupportsRule') {
        let ok = true;
        try { ok = view.CSS && view.CSS.supports ? view.CSS.supports(r.conditionText) : true; } catch (e) { ok = true; }
        if (ok) walk(r.cssRules, parentSel);
      } else if (kind === 'CSSContainerRule' || kind === 'CSSScopeRule') {
        partial = true; // розмір контейнера / межі :scope на льоту чесно не вгадуємо
      } else if (kind === 'CSSLayerBlockRule') {
        partial = true; // порядок шарів не моделюємо — пропускаємо шар цілком, див. звіт п.5
      } else if (kind === 'CSSImportRule') {
        if (r.styleSheet) {
          try { walk(r.styleSheet.cssRules, parentSel); } catch (e) { blocked = true; }
        }
      } else if (kind === 'CSSStyleRule' && r.selectorText && r.style) {
        const abs = absolutize(r.selectorText, parentSel);
        rules.push({ sel: abs, style: r.style, order: rules.length });
        if (r.cssRules && r.cssRules.length) walk(r.cssRules, abs); // нативна вкладеність
      }
      // інші типи (@keyframes, @font-face, @page, @property…) не несуть
      // декларацій, застосовних до довільного елемента — свідомо ігноруємо.
    }
  };

  for (const sheet of Array.from(doc.styleSheets || [])) {
    let list;
    try { list = sheet.cssRules; } catch (e) { blocked = true; continue; } // ЛИШЕ доступ у try — не ковтаємо чужі баги обходу
    walk(list, null);
  }
  const result = { rules, blocked, partial };
  cache.set(doc, result);
  return result;
}

/* ── Дизайн-система напрямку ────────────────────────────────────────────────

   Індекс будується ОДИН раз на модуль, а не на документ і тим паче не на
   елемент: знімок ДС (`ds-tokens.js`) не залежить ні від макета, ні від
   @media, тобто в кеші правил (`collectRules`), який скидається на resize,
   йому не місце — він би даремно перебудовувався на кожну зміну ширини.

   Напрямок приїжджає ззовні (`setDsProfile`, кличе `inspector.js` із
   параметра свого ж URL), бо документ макета про задачу не знає нічого:
   `profile` живе в `tasks.json`, і єдиний, хто його бачить, — сервер, що
   вставляє тег інспектора.

   ⛔ НАПРЯМОК БЕЗ ДС — ЦЕ ВІДПОВІДЬ, А НЕ ПОМИЛКА. У `seo` дизайн-системи
   немає свідомо: тема сайту живе поза нею (`ds-source-of-truth`). Порожній
   словник тут зробив би кожну з 589 змінних лендінга «повз ДС» — 198 із них
   законні, і інструмент, який 198 разів поспіль звинуватив невинного, більше
   не читають. Тому `known:false` ВИМИКАЄ звірку, а панель каже про це
   словами. */
let dsProfile = null;
let dsCache = null;

/** Напрямок задачі (`united`/`liga360`/`seo`/…). Порожнє — «не знаємо», і це
 *  той самий стан, що «ДС немає»: мовчазна звірка проти невідомої ДС гірша за
 *  чесне «не звіряли». */
export function setDsProfile(profile) {
  dsProfile = typeof profile === 'string' && profile ? profile : null;
  dsCache = null;
}

/** Індекс ДС для поточного напрямку. */
export function ds() {
  if (!dsCache) {
    const raw = dsProfile ? DS_PROFILES[dsProfile] : null;
    dsCache = raw ? dsIndex(dsProfile, raw) : { ...DS_NONE, profile: dsProfile };
  }
  return dsCache;
}

/** Що сказати про ДС у панелі: напрямок, чи є для нього ДС, і з чого знімок.
 *  Походження їде В ПАНЕЛЬ, а не лишається у файлі: вирок «перевизначено»
 *  спирається на конкретний коміт, і дизайнер має право спитати, на який. */
export function dsInfo() {
  const d = ds();
  return { profile: d.profile, known: d.known,
    commit: DS_SOURCE.commit, figma: DS_SOURCE.figma };
}

/** Значення зі списку ДС, яке нормалізується в `key`. Не `[0]`: у
 *  `--typo-sizes-*` значень кілька (@media), і знайшли ми токен саме за
 *  ОДНИМ із них — підставити інше означало б порадити не те, що збіглось. */
function dsValueMatching(d, name, key) {
  const list = (d.known && d.tokens.get(name)) || [];
  for (const v of list) if (normalizeValue(v) === key) return v;
  return list.length ? list[0] : null;
}

const ROOTISH_RE = /^(?::root|html)(?:[.:#[][^\s>+~]*)?$/;

/** Токени, оголошені в :root/html (включно з темізованими :root[data-theme]/html.dark),
 *  → [{name, value}]. Значення беремо ЖИВЕ, з getComputedStyle кореня, а не сирий
 *  текст декларації — так автоматично враховується, яка з кількох тематичних
 *  переоголошень зараз реально активна (той самий каскад, що бачить браузер),
 *  замість змішування різних тем під одним іменем. */
export function collectTokens(doc = document) {
  const { rules } = collectRules(doc);
  const view = doc.defaultView || window;
  const rootCs = view.getComputedStyle(doc.documentElement);
  const names = new Set();
  for (const r of rules) {
    const parts = splitTopLevel(r.sel, ',').map((s) => s.trim());
    if (!parts.some((s) => ROOTISH_RE.test(s))) continue;
    for (const name of Array.from(r.style)) {
      if (name.startsWith('--')) names.add(name);
    }
  }
  return Array.from(names, (name) => ({ name, value: rootCs.getPropertyValue(name).trim() }));
}

/** Індекс «значення → токени» для підказки «є токен з таким значенням».
 *  Кешується у тому ж об'єкті, що й правила (invalidate() скидає обидва разом):
 *  describe() кличе це для КОЖНОЇ хардкодженої властивості (до ~20 на елемент),
 *  і без кешу довелось би щоразу заново перебудовувати Map. describeAll()
 *  на практиці кличеться на КЛІК (не на кожен рух миші), але кеш все одно
 *  того вартий — у панелі відкривають кілька елементів поспіль. */
export function buildTokenIndex(doc = document) {
  const c = collectRules(doc);
  if (!c.tokenIdx) c.tokenIdx = tokenIndex(collectTokens(doc));
  return c.tokenIdx;
}

/** Декларації блоку як `[ім'я, значення]` — з `cssText`, а НЕ з переліку
 *  властивостей (`Array.from(style)`).
 *
 *  ЧОМУ саме так (виміряно в Chrome 17.09.2026, а не взято з голови): перелік
 *  віддає ЛОНГХЕНДИ, а значення шортката з `var()` не розкладається по них
 *  (pending-substitution) — воно лежить лише під іменем шортката. `gap:
 *  var(--sp)` перелічується як `row-gap`/`column-gap` з ПОРОЖНІМИ значеннями,
 *  `place-items` — як `align-items`/`justify-items`, `inset` — як
 *  `top`/`right`/…, `columns` — як `column-width`/`column-count`. Спроба
 *  вгадати власника відкушуванням хвоста імені (`row-gap` → `row`) на всіх цих
 *  випадках промахується, і токен відступу, ужитий у `gap`, зник би з мапи
 *  вжитку — тобто фільтр підказок почав би різати СВОЇХ. Зловлено живим
 *  тестом `tests/live/inspector-hint.test.mjs`, не міркуванням.
 *
 *  `cssText` же віддає декларацію так, як її написали (`gap: var(--sp);`), і
 *  тримає ім'я разом зі значенням — саме та пара, яка нам потрібна.
 *
 *  Відома межа: розділювачі рахуємо з урахуванням дужок і лапок, але екранована
 *  лапка всередині рядка (`content: "a\"b"`) розбір зіб'є. У значеннях макетів
 *  такого не буває, а ціна помилки — зайва/загублена родина в мапі вжитку, не
 *  неправильний вирок. */
function declsOf(style) {
  const text = (style && style.cssText) || '';
  const parts = [];
  let depth = 0, quote = '', cur = '';
  for (const ch of text) {
    if (quote) { cur += ch; if (ch === quote) quote = ''; continue; }
    if (ch === '"' || ch === "'") { quote = ch; cur += ch; continue; }
    if (ch === '(') depth += 1;
    else if (ch === ')') depth = Math.max(0, depth - 1);
    if (ch === ';' && depth === 0) { parts.push(cur); cur = ''; continue; }
    cur += ch;
  }
  parts.push(cur);
  const out = [];
  for (const part of parts) {
    const i = part.indexOf(':');
    if (i < 0) continue;
    const name = part.slice(0, i).trim().toLowerCase();
    if (name) out.push([name, part.slice(i + 1).trim()]);
  }
  return out;
}

/** Де токени РЕАЛЬНО вжиті: `ім'я токена → Set(родин властивостей)`.
 *  Це і є КАТЕГОРІЯ токена — виведена з документа, а не з його імені.
 *
 *  Родину беремо з властивості, у якій написано `var(--x)`, тож `font-weight:
 *  var(--fw-bold)` робить `--fw-bold` токеном ваги шрифту, а `z-index:
 *  var(--z-tooltip)` — токеном рівня накладання, хоч значення в обох `700`.
 *  Оголошення токенів (`--a: var(--b)`) у мапу не йдуть: propFamilies віддає на
 *  них порожній масив (чому саме — там же, у коментарі).
 *
 *  Кешується в тому ж об'єкті, що й правила та зворотний індекс, тобто
 *  invalidate() скидає всі три РАЗОМ. Це не економія, а вимога правильності:
 *  скидання після resize існує тому, що міняються істинні @media, а разом із
 *  ними — і набір правил, з яких мапа зібрана. Мапа, що пережила б зміну
 *  медіа-запиту, показувала б категорії неіснуючого вжитку. */
export function buildTokenUsage(doc = document) {
  const c = collectRules(doc);
  if (!c.tokenUse) {
    const map = new Map();
    for (const r of c.rules) {
      for (const [prop, raw] of declsOf(r.style)) {
        if (!raw.includes('var(')) continue;
        const fams = propFamilies(prop);
        if (!fams.length) continue;
        for (const name of varsIn(raw)) {
          let set = map.get(name);
          if (!set) { set = new Set(); map.set(name, set); }
          for (const f of fams) set.add(f);
        }
      }
    }
    c.tokenUse = map;
  }
  return c.tokenUse;
}

const BOX = /^(margin|padding)-(top|right|bottom|left)$/;
// стан-псевдокласи роблять звіт залежним від того, де зараз курсор миші в
// МОМЕНТ виклику (describeAll кличеться з кліку) — за замовчуванням такі
// частини селектора не беремо до уваги, щоб :hover-правило не підмінило
// собою базовий стан. opts.states=true — колись увімкнути перемикачем у панелі.
const STATE_RE = /:(?:hover|active|target|focus(?:-visible|-within)?)\b/;

/** Значення властивості з ОДНОГО блоку декларацій: спершу лонгхенд —
 *  він вже несе прямий текст, якщо шорткат того ж блоку був БЕЗ var()
 *  (браузер сам розкладає такий шорткат по лонгхендах у CSSOM). Якщо
 *  лонгхенд порожній — це майже завжди означає, що в цьому ж блоці
 *  шорткат МІСТИТЬ var() (тоді CSSOM НЕ розкладає його — «pending-
 *  substitution value» зберігається лише під іменем шортката). Для
 *  margin/padding tоді падаємо на позиційний розбір шортката —
 *  ЯК ЧАСТИНУ каскаду для цього конкретного правила (з його ж spec/order/
 *  important), а не як загальний фолбек «якщо взагалі ніхто не переміг». */
function readDecl(style, prop) {
  const v = style.getPropertyValue(prop);
  if (v) return { value: v.trim(), important: style.getPropertyPriority(prop) === 'important' };
  const m = prop.match(BOX);
  if (!m) return null;
  const shVal = style.getPropertyValue(m[1]);
  if (!shVal) return null;
  const box = splitBox(shVal.trim());
  if (!box) return null;
  return { value: box[m[2]], important: style.getPropertyPriority(m[1]) === 'important' };
}

/* `pickWinner` живе в ядрі, але назовні його віддає ЦЕЙ модуль — разом із
   `declsFor`, від якого він невіддільний: декларації без переможця ні про що не
   говорять, а переможець без декларацій нізвідки не береться. Верхній шар
   (`inspector.js`) свідомо знає лише одні двері до моделі — ті самі, крізь які
   вже ходять `describeAll`/`trail`/`label`; другий імпорт, прямо з ядра, зробив
   би з «UI нічого не вирішує» напівправду. Поведінку не чіпаємо — це рівно та
   сама функція. */
export { pickWinner };

/** Усі декларації властивості, що застосовні до елемента (+ інлайн).
 *
 *  Кожна декларація несе `sel` — селектор ПРАВИЛА, з якого вона взята (у
 *  інлайну правила немає, тому `null`). Поле додане для `identity()`
 *  (`inspector.js`): пакет рекомендацій мусить сказати Клоду не лише ЩО
 *  змінити, а й ДЕ, а «де» — це саме те правило, яке виграло каскад для цієї
 *  властивості. Селектор беремо як є, цілим списком (`.a, .b`), бо це і є
 *  правило; звужувати його до гілки, що збіглась, означало б показувати не те,
 *  що написано у файлі. На вибір переможця поле не впливає ніяк —
 *  `pickWinner` дивиться на `important`/`inline`/`spec`/`order`. */
export function declsFor(el, prop, opts = {}) {
  const { rules } = collectRules(el.ownerDocument);
  const out = [];
  for (const r of rules) {
    const read = readDecl(r.style, prop);
    if (!read) continue;
    let best = null;
    for (const part of splitTopLevel(r.sel, ',')) {
      const s = part.trim();
      if (!s) continue;
      if (!opts.states && STATE_RE.test(s)) continue;
      let hit = false;
      try { hit = el.matches(s); } catch (e) { hit = false; }
      if (!hit) continue;
      const sp = specificity(s);
      if (!best || compareSpec(sp, best) > 0) best = sp;
    }
    if (!best) continue;
    out.push({ value: read.value, spec: best, order: r.order, important: read.important, inline: false, sel: r.sel });
  }
  const iv = el.style && readDecl(el.style, prop);
  if (iv) {
    // Інлайн: правила немає взагалі, тож `sel` чесно порожній — про те, що
    // декларація прийшла з атрибута `style`, каже `inline`.
    out.push({ value: iv.value, spec: [0, 0, 0], order: Number.MAX_SAFE_INTEGER, important: iv.important, inline: true, sel: null });
  }
  return out;
}

/** Сире значення, яке ВИГРАЛО каскад (шорткат уже врахований усередині declsFor). */
export function rawFor(el, prop, opts = {}) {
  const w = pickWinner(declsFor(el, prop, opts));
  return w ? w.value : null;
}

/** Для лонгхендів, що НЕ мають позиційного розбору (кольори з background/border) —
 *  раз ми не знайшли пряме оголошення, дивимось у сирий текст цього шортката. */
const SHORTHAND_FALLBACK = {
  'background-color': 'background',
  'border-color': 'border',
  'border-width': 'border',
};

const REL_UNIT_RE = /^(-?[\d.]+)(rem|em)$/;
const UNITLESS_RE = /^\d*\.?\d+$/; // без цього /^[\d.]+$/ пропускало б "1.2.3" → NaNpx

/** rem/em-значення → px, відносно кореня (rem) чи самого елемента (em).
 *  line-height часто задають безрозмірним множником — теж зводимо до px,
 *  інакше звірка з computed завжди падала б і токен ховався б даремно.
 *  Розкриваємо ЛИШЕ те, що вміємо порахувати точно: `%`, `auto`, `calc()`
 *  лишаються як є — і чесно доходять до вироку 'unknown'.
 *  Застосовується і до значення токена, і до сирої декларації: та сама
 *  звірка з computed, той самий масштаб. */
function resolveUnits(prop, raw, cs, rootCs) {
  if (!raw) return raw;
  if (prop === 'line-height' && UNITLESS_RE.test(raw)) {
    return `${Number(raw) * parseFloat(cs.fontSize)}px`;
  }
  const m = REL_UNIT_RE.exec(raw);
  if (m) {
    const base = m[2] === 'rem' ? parseFloat(rootCs.fontSize) : parseFloat(cs.fontSize);
    return `${Number(m[1]) * base}px`;
  }
  return raw;
}

/** Звіт про одну властивість елемента. */
export function describe(el, prop, opts = {}) {
  const view = el.ownerDocument.defaultView || window;
  const cs = view.getComputedStyle(el);
  const rootCs = view.getComputedStyle(el.ownerDocument.documentElement);
  const computed = cs.getPropertyValue(prop).trim();

  let raw = rawFor(el, prop, opts);
  if (raw == null) {
    const sh = SHORTHAND_FALLBACK[prop];
    if (sh) raw = rawFor(el, sh, opts);
  }

  // Токен — НЕ перша-ліпша var() у raw (border-radius: var(--a) var(--b) і
  // шорткати типу border: var(--w) solid var(--c) можуть містити кілька var()
  // на РІЗНІ призначення). Перевіряємо кожну позиційну частину і беремо ту,
  // чий var() дійсно розкривається в те саме, що бачить браузер. Не збіглось
  // з жодною — token/tokenValue лишаються null (verdict нижче сам зведе це
  // до 'unlinked', а не видасть неправильного «token»).
  let token = null;
  let tokenValue = null;
  /* Значення токена ДО зведення одиниць — саме ним звіряємось із ДС нижче:
     ДС пише `1rem`, браузер порахував би `16px`, і звірка з обчисленим
     оголосила б «перевизначено» кожен розмірний токен, що збігається
     дослівно. Для вироку 'token' (нижче) потрібне, навпаки, зведене. */
  let tokenDeclared = null;
  if (raw) {
    for (const part of splitTop(raw)) {
      const names = varsIn(part);
      if (!names.length) continue;
      const candToken = names[0];
      const declared = cs.getPropertyValue(candToken).trim();
      const candValue = resolveUnits(prop, declared, cs, rootCs);
      if (candValue && normalizeValue(candValue) === normalizeValue(computed)) {
        token = candToken;
        tokenValue = candValue;
        tokenDeclared = declared;
        break;
      }
    }
  }

  let v = verdict({ raw, token, tokenValue, computed });
  // Запобіжник: verdict сказав 'hardcode' (у raw немає var()), але сам raw НЕ
  // збігається з тим, що показує браузер — значить, ми визначили переможця
  // каскаду неправильно (пропущений @layer/@container, нативна вкладеність,
  // яку не розпізнали, чи інша прогалина нашої моделі — включно з тими, яких
  // ми ще не знайшли). Чесніше сказати «не розібрали», ніж упевнено
  // звинуватити дизайнера в хардкоді.
  // raw проганяємо через ТЕ САМЕ розкриття одиниць, що й значення токена:
  // без нього `1rem` проти computed `16px` виглядало б як розбіжність, і
  // запобіжник ковтав би найчастіший хардкод rem-макета (кожен рядок
  // типографіки) під сірим «?». Те, що не розкривається (`%`, `auto`,
  // `calc()`), і далі чесно доходить до 'unknown'.
  const rawResolved = resolveUnits(prop, raw, cs, rootCs);
  if (v === 'hardcode' && normalizeValue(rawResolved) !== normalizeValue(computed)) v = 'unknown';

  // Нуль не буває «повз дизайн-систему»: жодна ДС не вимагає токена, щоб
  // написати 0, а зворотний індекс на нулі схлопує токени всіх категорій разом
  // — виміряно живцем: `margin: 0` радив `--corner-0`, тобто токен РАДІУСА для
  // відступу. Порада не тієї категорії гірша за відсутність поради.
  if (v === 'hardcode' && normalizeValue(computed) === '0px') v = 'unlinked';

  // Ключ індексу не унікальний, тож показуємо ВСІХ кандидатів (до трьох), а не
  // перший-ліпший — інакше з трьох токенів з однаковим значенням дизайнер
  // побачить довільний. Але не будь-яких: індекс знає САМІ ЗНАЧЕННЯ, а `700` —
  // це і вага шрифту, і z-index. hintFor лишає доведених вжитком (tier 'used')
  // і, за ними, здогадних за формою значення (tier 'shape'); там же — чому
  // форми не досить на безрозмірних числах.
  // `computed` іде в hintFor не для пошуку (за ним уже знайдено), а щоб вона
  // бачила ФОРМУ значення: ключ індексу — це рівно нормалізований computed,
  // тобто значення в усіх кандидатів те саме, що й у властивості.
  /* ДРУГЕ ПИТАННЯ (T-40): джерело знайшли — а чи воно з дизайн-системи?
     Питається ЛИШЕ на 'token': 'hardcode'/'unlinked'/'unknown' про токен
     нічого не стверджують, і дописувати їм вирок про ДС означало б назвати
     ім'я там, де ми самі не довели походження (та сама межа, що в
     `verdictText`, `insp-report.js`). */
  const d = ds();
  let dsWant = null;
  if (v === 'token') {
    const got = dsVerdict(d, token, tokenDeclared);
    v = got.state;
    dsWant = got.want;
  }

  const doc = el.ownerDocument;
  const key = normalizeValue(computed);
  /* Підказки тепер і для 'off-ds': питання «чим це має бути в ДС» доречне
     саме там, де значення прийшло з вигаданої змінної. Джерел кандидатів
     два, і порядок несучий: спершу токени САМОЇ ДС (це і є відповідь «як
     повернутись»), за ними — токени макета (стара поведінка, яку T-40 не
     чіпає). Обидва проходять той самий відсів `hintFor`: збіг за значенням
     нічого не доводить (`700` — і вага, і z-index), і від того, що кандидат
     приїхав із ДС, це не міняється. */
  let hint = [];
  if (v === 'hardcode' || v === 'off-ds') {
    const usage = buildTokenUsage(doc);
    const fromDs = d.known
      ? hintFor(prop, d.byValue.get(key) || [], usage, computed)
        .map((h) => ({ ...h, ds: true }))
      : [];
    const local = v === 'hardcode'
      ? hintFor(prop, buildTokenIndex(doc).get(key) || [], usage, computed)
        .filter((h) => !fromDs.some((x) => x.name === h.name))
        .map((h) => ({ ...h, ds: d.known && d.tokens.has(h.name) }))
      : [];
    /* ПОРЯДОК: спершу ДОВЕДЕНІ вжитком ('used'), і лише за ними здогадні
       ('shape') — те саме правило, що всередині `hintFor`, і порушити його
       тут не можна: голий `fromDs.concat(local)` поставив би ЗДОГАД із ДС
       поперед ФАКТУ з макета, тобто відмив би здогад у доведення саме тим
       способом, від якого лікувався T-38. Належність до ДС — другий ключ, не
       перший: вона каже, куди підказка веде, а не наскільки вона доведена. */
    hint = orderHints(fromDs.concat(local)).slice(0, 3);
  }

  /* ДОРОГА НАЗАД У ДС — те, чого в інспекторі не було зовсім: підказка була
     інертним текстом, і на питання «як повернути значення до системного»
     інструмент не відповідав ніяк. `snap` — адреса цієї дороги: токен ДС і
     значення, яке ДС йому приписує. Проводить її панель (кнопка в полі), а
     їде вона тим самим шляхом, що й будь-яка ручка тюнера.

     ⛔ Пропонуємо ЛИШЕ токен, який справді є в ДС: підказка з макетного
     токена, самого повз ДС, — це дорога не туди. Тому `h.ds`. */
  let snap = null;
  if (v === 'overridden' && token && dsWant && dsWant.length) {
    snap = { token, value: dsWant[0] };
  } else {
    const back = hint.find((h) => h.ds);
    if (back) {
      const value = dsValueMatching(d, back.name, key);
      if (value) snap = { token: back.name, value };
    }
  }

  return { prop, computed, raw, token, tokenValue, verdict: v, hint, ds: dsWant, snap };
}

/** Звіт по всіх групах. Секція flex — для flex- і grid-контейнера. */
export function describeAll(el, opts = {}) {
  const view = el.ownerDocument.defaultView || window;
  const display = view.getComputedStyle(el).display;
  const groups = {};
  for (const [name, props] of Object.entries(GROUPS)) {
    if (name === 'flex' && !/flex|grid/.test(display)) continue;
    groups[name] = props.map((p) => describe(el, p, opts));
  }
  const { blocked, partial } = collectRules(el.ownerDocument);
  return { el, groups, blocked, partial, dsInfo: dsInfo() };
}

/** Ланцюжок предків для хлібних крихт: від кореня до самого елемента.
 *  Якщо root не є предком el узагалі — цикл однаково впирається в
 *  n.ownerDocument.body і коректно падає назад на нього. */
export function trail(el, root) {
  const out = [];
  let n = el;
  while (n && n.nodeType === 1) {
    out.unshift(n);
    if (n === root || n === n.ownerDocument.body) break;
    n = n.parentElement;
  }
  return out;
}

/** Короткий підпис елемента: тег + до двох класів. localName, не tagName —
 *  інакше SVG-теги на кшталт clipPath показувались би як CLIPPATH/clippath. */
export function label(el) {
  const cls = Array.from(el.classList || []).slice(0, 2).map((c) => `.${c}`).join('');
  return el.localName + cls;
}
