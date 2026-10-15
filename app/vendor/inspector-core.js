/* Інспектор макета — чиста логіка. Нуль DOM: усе приймається аргументами.
   Живе в канвасі (локальний режим), не входить у publish. */

/** Розбити рядок на частини по РОЗДІЛЬНИКУ верхнього рівня (поза дужками).
 *  Експортується для inspector-dom.js: наївний `sel.split(',')` на селекторі
 *  калічить `:is(.a, .b) .c` (кома всередині дужок — не розділювач списку
 *  селекторів), а forgiving-парсер Chrome мовчки «зжує» обрізаний фрагмент
 *  замість кинути помилку — тобто це не втрата правила, а неправильна вага
 *  в каскаді. */
export function splitTopLevel(str, sepChar) {
  const out = [];
  let depth = 0, cur = '';
  for (const ch of str) {
    if (ch === '(') depth++;
    else if (ch === ')') depth = Math.max(0, depth - 1);
    if (depth === 0 && ch === sepChar) { out.push(cur); cur = ''; continue; }
    cur += ch;
  }
  out.push(cur);
  return out;
}

/** Перше входження :name(...) (name — одне з names) на верхньому рівні рядка.
 *  Повертає { start, end, inner } (end — індекс ПІСЛЯ закривної дужки) або null. */
function findPseudoFunc(str, names) {
  const re = /:([a-zA-Z-]+)\(/g;
  let m;
  while ((m = re.exec(str))) {
    const name = m[1].toLowerCase();
    if (!names.includes(name)) continue;
    const openIdx = m.index + m[0].length - 1;
    let depth = 1, i = openIdx + 1;
    while (i < str.length && depth > 0) {
      if (str[i] === '(') depth++;
      else if (str[i] === ')') depth--;
      i++;
    }
    return { start: m.index, end: i, inner: str.slice(openIdx + 1, i - 1) };
  }
  return null;
}

/** Специфічність ОДНОГО (без верхньорівневих ком) селектора. */
function specificityOne(sel) {
  let s = sel;
  let a = 0, b = 0, c = 0;

  // Легасі псевдоелементи (:before/:after/:first-line/:first-letter, 1 чи 2 двокрапки)
  // і сучасні ::pseudo — усі рахуються як тег.
  s = s.replace(/:{1,2}(before|after|first-line|first-letter)\b/gi, () => { c++; return ' '; });
  s = s.replace(/::[\w-]+/g, () => { c++; return ' '; });

  // :where(...) — вага НУЛЬ, сам і вміст ігноруються повністю.
  let found;
  while ((found = findPseudoFunc(s, ['where']))) {
    s = s.slice(0, found.start) + ' ' + s.slice(found.end);
  }

  // :is(...) / :has(...) — не рахуються самі, але додають специфічність
  // НАЙСПЕЦИФІЧНІШОЇ з (кома-розділених) гілок усередині.
  while ((found = findPseudoFunc(s, ['is', 'has']))) {
    const branches = splitTopLevel(found.inner, ',')
      .map((br) => br.trim())
      .filter(Boolean)
      .map((br) => specificity(br));
    const best = branches.reduce((bst, cur) => (compareSpec(cur, bst) > 0 ? cur : bst), [0, 0, 0]);
    a += best[0]; b += best[1]; c += best[2];
    s = s.slice(0, found.start) + ' ' + s.slice(found.end);
  }

  // :not(...) сам не рахується, а його вміст — так (просто повертаємо вміст назад у рядок).
  s = s.replace(/:not\(([^)]*)\)/gi, (_m, inner) => ` ${inner} `);

  const re = /(#[\w-]+)|(\.[\w-]+)|(\[[^\]]*\])|(:[\w-]+(?:\([^)]*\))?)|([a-zA-Z][\w-]*)|(\*)/g;
  let m;
  while ((m = re.exec(s))) {
    if (m[1]) a++;
    else if (m[2] || m[3] || m[4]) b++;
    else if (m[5]) c++;
  }
  return [a, b, c];
}

/** Специфічність селектора → [id, клас/атрибут/псевдоклас, тег/псевдоелемент].
 *  Список селекторів (кома верхнього рівня, напр. `.a, .b`) — це НЕ сума, а
 *  МАКСИМУМ специфічності серед гілок (кожна гілка — окремий, незалежний селектор). */
export function specificity(sel) {
  const s = String(sel == null ? '' : sel).trim();
  if (!s) return [0, 0, 0];
  const parts = splitTopLevel(s, ',').map((p) => p.trim()).filter(Boolean);
  if (!parts.length) return [0, 0, 0];
  if (parts.length === 1) return specificityOne(parts[0]);
  return parts
    .map(specificityOne)
    .reduce((best, cur) => (compareSpec(cur, best) > 0 ? cur : best));
}

/** -1 / 0 / 1 — порівняння двох специфічностей. */
export function compareSpec(x, y) {
  for (let i = 0; i < 3; i++) {
    if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0) ? 1 : -1;
  }
  return 0;
}

/** Переможець каскаду серед декларацій ОДНІЄЇ властивості.
 *  decl = { value, spec:[a,b,c], order, inline?, important? } */
export function pickWinner(decls) {
  const list = (decls || []).filter((d) => d && d.value != null && String(d.value).trim() !== '');
  if (!list.length) return null;
  const weight = (d) => (d.important ? (d.inline ? 4 : 3) : (d.inline ? 2 : 1));
  return list.reduce((best, d) => {
    if (!best) return d;
    if (weight(d) !== weight(best)) return weight(d) > weight(best) ? d : best;
    const s = compareSpec(d.spec || [0, 0, 0], best.spec || [0, 0, 0]);
    if (s !== 0) return s > 0 ? d : best;
    return (d.order || 0) >= (best.order || 0) ? d : best;
  }, null);
}

/** Імена CSS-змінних, ужитих у сирому значенні (без дублікатів, у порядку появи). */
export function varsIn(raw) {
  const out = [];
  const seen = new Set();
  const re = /var\(\s*(--[\w-]+)/g;
  let m;
  while ((m = re.exec(String(raw == null ? '' : raw)))) {
    if (!seen.has(m[1])) { seen.add(m[1]); out.push(m[1]); }
  }
  return out;
}

/** Розбити значення на частини по ПРОБІЛАХ верхнього рівня (var(...) лишається цілим).
 *  Призначено для позиційних шорткатів (padding/margin/border-radius), НЕ для значень
 *  із комами як розділювачем (box-shadow-список, font-family) — там розділювач інший. */
export function splitTop(raw) {
  const out = [];
  let depth = 0, cur = '';
  for (const ch of String(raw == null ? '' : raw)) {
    if (ch === '(') depth++;
    else if (ch === ')') depth = Math.max(0, depth - 1);
    if (depth === 0 && /\s/.test(ch)) { if (cur) { out.push(cur); cur = ''; } continue; }
    cur += ch;
  }
  if (cur) out.push(cur);
  return out;
}

/** Позиційний розбір шортката padding/margin (1–4 значення) на сторони.
 *  Більше 4 частин — це вже не валідний бокс-шорткат, повертаємо null. */
export function splitBox(raw) {
  const p = splitTop(raw);
  if (!p.length || p.length > 4) return null;
  const [a, b = a, c = a, d = b] = p;
  return { top: a, right: b, bottom: c, left: d };
}

/** Канонічний вигляд значення для порівняння: кольори → #rrggbb, лапки геть, регістр вниз,
 *  пробіли навколо ком і провідний нуль у дробах — нормалізовані.
 *  Покриття кольорів НЕПОВНЕ: rgb() із відсотковими компонентами (напр. `rgb(0% 50% 100%)`)
 *  і альфа у відсотках НЕ розпізнаються — повертаються як є (лише в нижньому регістрі). */
export function normalizeValue(v) {
  let s = String(v == null ? '' : v).trim().toLowerCase().replace(/["']/g, '').replace(/\s+/g, ' ');
  s = s.replace(/\s*,\s*/g, ', ');
  s = s.replace(/(?<![\d.])\.(\d)/g, '0.$1');
  if (s === 'transparent') return 'rgba(0, 0, 0, 0)';
  const m3 = s.match(/^#([0-9a-f])([0-9a-f])([0-9a-f])$/);
  if (m3) return `#${m3[1]}${m3[1]}${m3[2]}${m3[2]}${m3[3]}${m3[3]}`;
  const m8 = s.match(/^#([0-9a-f]{6})ff$/);
  if (m8) return `#${m8[1]}`;
  const rgb = s.match(/^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)\s*(?:[,/]\s*1(?:\.0+)?\s*)?\)$/);
  if (rgb) return '#' + [1, 2, 3].map((i) => Number(rgb[i]).toString(16).padStart(2, '0')).join('');
  if (/^0(px|rem|em)?$/.test(s)) return '0px';
  return s;
}

/** Зворотний індекс «нормалізоване значення → [імена токенів]».
 *  vars = [{ name, value }] — зібрані UI з правил :root/html.
 *  Ключ НЕ унікальний для різних одиниць/запису одного й того ж значення
 *  (напр. `0`, `0px`, `0em` схлопуються після normalizeValue) — споживач має
 *  показувати ВСІХ кандидатів під ключем, а не брати перший-ліпший. */
export function tokenIndex(vars) {
  const map = new Map();
  for (const v of vars || []) {
    if (!v) continue;
    const name = String(v.name || '');
    if (!name.startsWith('--')) continue;
    const key = normalizeValue(v.value);
    if (!key) continue;
    if (!map.has(key)) map.set(key, []);
    const arr = map.get(key);
    if (!arr.includes(name)) arr.push(name);
  }
  return map;
}

/** Родина властивостей — груба «шкала» дизайн-системи: набір властивостей, між
 *  якими ОДИН І ТОЙ САМИЙ токен доречний (відступи ділять шкалу з gap, кольори
 *  тексту й фону — одну палітру). Властивість, якої в таблиці немає, сама собі
 *  родина (`font-weight` → 'font-weight', `z-index` → 'z-index'): це навмисно
 *  найвужчий дефолт — краще не порадити нічого, ніж порадити не те.
 *
 *  Шорткат може належати ОДРАЗУ кільком родинам (`border: <товщина> solid
 *  <колір>`) — і це не робить підказку брехливою: кандидати беруться зі
 *  зворотного індексу ЗА ЗНАЧЕННЯМ, а частини одного шортката мають різні
 *  значення, тож колір `#ccc` фізично не потрапить у кандидати для
 *  `border-width: 1px`.
 *
 *  Родини — НЕ імена токенів. Імена в макетах самопальні (`ds-source-of-truth`),
 *  а перелік властивостей CSS — спільний словник, однаковий у всіх макетах.
 *
 *  Зсувів позиціонування (`inset`, `top`/`left`…) у шкалі відступів НЕМАЄ
 *  свідомо: їх справді часто беруть із тієї ж шкали, але «часто» — це здогад,
 *  а здогад тут коштує неправильної правки в коді. Вони лишаються кожен сам
 *  собі родиною; захочемо інакше — це рішення, яке треба ухвалити окремо. */
const FAMILY = {
  margin: ['spacing'], padding: ['spacing'],
  gap: ['spacing'], 'row-gap': ['spacing'], 'column-gap': ['spacing'],
  'border-radius': ['radius'],
  'border-width': ['line-width'], 'outline-width': ['line-width'],
  border: ['line-width', 'color'], outline: ['line-width', 'color'],
  color: ['color'], 'background-color': ['color'], background: ['color'],
  'border-color': ['color'], 'outline-color': ['color'], 'caret-color': ['color'],
  'text-decoration-color': ['color'], 'accent-color': ['color'],
  'column-rule-color': ['color'],
  fill: ['color'], stroke: ['color'], // SVG: stroke — це КОЛІР, товщина зветься stroke-width
  'box-shadow': ['shadow'], 'text-shadow': ['shadow'],
  width: ['size'], height: ['size'], 'flex-basis': ['size'],
  'min-width': ['size'], 'max-width': ['size'],
  'min-height': ['size'], 'max-height': ['size'],
  font: ['font-family', 'font-size', 'font-weight', 'line-height'],
};

/** Звести сторону/напрямок до базової властивості: `padding-inline-start` і
 *  `padding-left` — та сама шкала відступів, `border-top-width` — та сама шкала
 *  товщини. Без цього токен, ужитий у `padding-left`, не пропонувався б для
 *  `padding-top` — і фільтр з корисного став би шкідливим. */
function canonicalProp(p) {
  return p
    .replace(/^(margin|padding|inset|scroll-margin|scroll-padding)-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?$/, '$1')
    .replace(/^border-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?-(width|color|style)$/, 'border-$1')
    .replace(/^border-(?:(?:top|bottom)-(?:left|right)|(?:start|end)-(?:start|end))-radius$/, 'border-radius');
}

/** Властивість → родини, до яких вона належить. Порожній масив — «категорії
 *  немає»: так ми відповідаємо на ОГОЛОШЕННЯ кастомної властивості
 *  (`--fg: var(--brand)`). Псевдонім не каже про категорію `--brand` нічого —
 *  щоб дізнатись її, довелось би розкручувати ланцюжок псевдонімів, а той, хто
 *  в сторінці реально вжитий (`--fg`), і є чесніша порада. */
export function propFamilies(prop) {
  const p = String(prop == null ? '' : prop).trim().toLowerCase();
  if (!p || p.startsWith('--')) return [];
  const c = canonicalProp(p);
  return FAMILY[c] || [c];
}

/** ФОРМА значення: 'color' | 'length' | 'number' | 'other'. Груба, навмисно:
 *  вона відповідає на одне питання — чи МОЖЕ таке значення бути значенням такої
 *  властивості. Колір не буває вагою шрифту, довжина не буває z-index. */
export function valueShape(v) {
  const s = normalizeValue(v);
  if (!s) return 'other';
  if (/^#[0-9a-f]{6}$/.test(s) || /^rgba?\(/.test(s)) return 'color';
  if (/^-?\d*\.?\d+(px|rem|em|%|vh|vw|vmin|vmax|ch|ex|pt|pc|cm|mm|in)$/.test(s)) return 'length';
  if (/^-?\d*\.?\d+$/.test(s)) return 'number';
  return 'other';
}

/** Які форми значень бувають у родини. Родини, якої тут немає (`display`,
 *  `font-family`, `shadow`, `flex-direction`…), у таблиці немає СВІДОМО: її
 *  значення — ключові слова й складені списки, а збіг такого тексту не доводить
 *  нічого. Саме звідти приходила порада `display: none → --shadow-s`. */
const FAMILY_SHAPES = {
  spacing: ['length'], radius: ['length'], 'line-width': ['length'], size: ['length'],
  color: ['color'],
  'font-size': ['length'], 'letter-spacing': ['length'],
  'line-height': ['length', 'number'],
  'font-weight': ['number'], 'z-index': ['number'], opacity: ['number'],
};

/** Що ІМ'Я токена заявляє про його родину. Словник навмисно з ОДНИХ лише
 *  впізнаваних сегментів; невпізнане ім'я не заявляє нічого — і це нормальна,
 *  найчастіша відповідь.
 *
 *  Заявка буває ШИРОКОЮ (`size` → і кегль, і габарит; `font` → уся типографіка)
 *  — і це навмисно в той бік, що безпечніший: ім'я вміє лише ВИКЛЮЧАТИ (див.
 *  hintFor), тож ширша заявка виключає МЕНШЕ. Помилитись тут = втратити одну
 *  пораду, а не порадити чуже. */
const NAME_CLAIM = {
  z: ['z-index'], zindex: ['z-index'], layer: ['z-index'],
  fw: ['font-weight'], weight: ['font-weight'],
  radius: ['radius'], radii: ['radius'], corner: ['radius'], rounded: ['radius'],
  spacing: ['spacing'], spacings: ['spacing'], space: ['spacing'], spaces: ['spacing'],
  sp: ['spacing'], gap: ['spacing'], margin: ['spacing'], padding: ['spacing'],
  inset: ['spacing'],
  size: ['font-size', 'size'], sizes: ['font-size', 'size'], fs: ['font-size'],
  lh: ['line-height'], leading: ['line-height'],
  ls: ['letter-spacing'], tracking: ['letter-spacing'],
  color: ['color'], colors: ['color'], colour: ['color'], palette: ['color'],
  bg: ['color'], fg: ['color'], ink: ['color'], tint: ['color'],
  shadow: ['shadow'], shadows: ['shadow'], elevation: ['shadow'],
  blur: ['shadow'], // радіус розмиття — з тієї ж шухляди, що й тіні/фільтри
  opacity: ['opacity'], alpha: ['opacity'],
  width: ['size', 'line-width'], height: ['size'],
  border: ['line-width', 'color'], stroke: ['line-width', 'color'], bw: ['line-width'],
  font: ['font-family', 'font-size', 'font-weight', 'line-height'],
  typo: ['font-family', 'font-size', 'font-weight', 'line-height', 'letter-spacing'],
  duration: ['duration'], delay: ['duration'], easing: ['easing'], ease: ['easing'],
};

/** Родини, які заявляє ім'я токена. Ріжемо по всьому, що не літера: так
 *  `--typo-sizes-h300` дає ['typo','sizes','h'], а `--shadow-z-index-…-blur` —
 *  і 'shadow', і 'z'. */
export function nameClaims(name) {
  const out = new Set();
  for (const seg of String(name == null ? '' : name).toLowerCase().split(/[^a-z]+/)) {
    for (const f of NAME_CLAIM[seg] || []) out.add(f);
  }
  return out;
}

/** Підказка «є токен із таким значенням» — з кандидатів лишаємо тих, кому є
 *  чим відповісти на питання «а чи ти взагалі з цієї шухляди?».
 *
 *  ЧОМУ взагалі фільтр (виміряно живцем на `bf360` 17.09.2026): `font-weight: 700`
 *  діставав підказку «--fw-bold, --z-tooltip», бо зворотний індекс знає лише
 *  значення — а `700` це і вага шрифту, і рівень накладання. Той самий клас уже
 *  кусався на `margin: 0` → `--corner-0` (радіус для відступу), і тоді залатали
 *  окремий випадок нуля, а не причину. У Task 11 `hint` їде в JSON-пакет, з якого
 *  Клод РЕАЛЬНО править код, тож порада не тієї категорії перестає бути невдалою
 *  порадою і стає неправильною правкою.
 *
 *  ДВА РІВНІ ВПЕВНЕНОСТІ, і кожен їде в даних (`tier`), а не лише в кольорі
 *  бейджа — бо споживач пакета не бачить кольорів:
 *
 *   'used'  — токен уже вживають у цьому документі для ЦІЄЇ родини
 *             властивостей. Це факт, знятий із правил, а не здогад. Такі йдуть
 *             ПЕРШИМИ і не проходять жодних додаткових перевірок: вжиток
 *             сильніший за будь-яку ознаку.
 *   'shape' — токен не вжитий ніде, але його значення ФОРМОЮ годиться цій
 *             властивості (колір — кольору, довжина — довжині), а ім'я не
 *             заявляє чужої родини. Це здогад, і він мусить виглядати як
 *             здогад.
 *
 *  Токен, ужитий для ЧУЖОЇ родини, викидаємо без другого шансу: документ прямо
 *  каже, що це токен кегля (чи радіуса), і форма значення цього не переважить.
 *
 *  ⛔ ЧОМУ форми НЕ досить, і що стоїть замість неї на безрозмірних числах.
 *  `--z-tooltip: 700` і `font-weight: 700` — обидва безрозмірні числа, тобто
 *  форма їх не розрізняє в принципі, а саме з цієї пари задача й почалась.
 *  Діапазон теж не рятує: у Figma-дампах z-index'и якраз і виглядають як
 *  100…900. Лишається ім'я — і ми беремо його ТІЛЬКИ ЩОБ ВИКЛЮЧАТИ:
 *  ім'я, що виразно заявляє іншу родину, знімає кандидата; ім'я, що не заявляє
 *  нічого, не додає йому ваги. Асиметрія тут не стилістична: помилкове
 *  виключення коштує однієї ненаписаної поради, помилкове ВКЛЮЧЕННЯ — брехні
 *  про токен, тобто того самого багу. Імена самопальні (`ds-source-of-truth`),
 *  тому вони й не можуть нічого ДОВОДИТИ — але «--z-*» серед ваг шрифту
 *  заперечує себе сам.
 *
 *  limit=3 живе ТУТ, а не у виклику: відсів і впорядкування мусять іти ПЕРЕД
 *  обрізанням, інакше три чужі (або три здогадні) токени зайняли б усі місця й
 *  витіснили доведений. */
export function hintFor(prop, candidates, usage, computed, limit = 3) {
  const want = propFamilies(prop);
  if (!want.length) return [];
  const shapes = new Set();
  for (const f of want) for (const sh of FAMILY_SHAPES[f] || []) shapes.add(sh);
  const shapeOk = shapes.has(valueShape(computed));
  const used = [];
  const guess = [];
  for (const name of candidates || []) {
    const fams = usage && typeof usage.get === 'function' ? usage.get(name) : null;
    if (fams && fams.size) {
      if (want.some((f) => fams.has(f))) used.push({ name, tier: 'used' });
      continue;
    }
    if (!shapeOk) continue;
    const claims = nameClaims(name);
    if (claims.size && !want.some((f) => claims.has(f))) continue;
    guess.push({ name, tier: 'shape' });
  }
  return used.concat(guess).slice(0, limit);
}

/** Вирок для одного значення елемента. Сама зводить `raw` ↔ `token` — не вірить на слово.
 *  'token'    — `raw` дійсно містить `var(--token)`, І значення токена звірилось з computed;
 *  'unlinked' — джерела не знайшли, токен не звірився, або назва токена не з цього `raw`;
 *  'hardcode' — у `raw` немає жодного var() — літерал повз дизайн-систему. */
export function verdict({ raw, token, tokenValue, computed }) {
  if (raw == null || String(raw).trim() === '') return 'unlinked';
  const vars = varsIn(raw);
  if (!vars.length) return 'hardcode';
  if (!token || !vars.includes(token)) return 'unlinked';
  const a = normalizeValue(tokenValue);
  const b = normalizeValue(computed);
  return a && b && a === b ? 'token' : 'unlinked';
}

/* ── Звірка з ДИЗАЙН-СИСТЕМОЮ (T-40) ────────────────────────────────────────

   До T-40 вирок 'token' означав рівно одне: «значення прийшло з якоїсь
   змінної CSS». Виміряно 22.09.2026, чим це обернулось на справжніх макетах:
   у `bgSanctions` із 66 оголошених змінних у ДС є 7 — решта 59 (89%) вигадані
   на місці, і всі 59 світились зеленою крапкою «токен». Тобто зелений колір
   не означав нічого, крім «автор написав var()».

   Тому питань тепер ДВА, і вони незалежні:
     1. Звідки прийшло значення (це лишається `verdict` вище);
     2. Чи є те джерело дизайн-системою (це — тут).

   ⛔ І ТРЕТІЙ ВИПАДОК, гірший за обидва. Макет може ПЕРЕВИЗНАЧИТИ ім'я з ДС
   іншим значенням: у `courts` таких 110, зокрема `--color-neutral-alpha-100:
   #fbfbff` там, де ДС каже `#FBFBFF1A` — альфа загублена, і токен, який має
   бути напівпрозорим, малюється глухим. Ім'я правильне, вжиток правильний,
   код виглядає бездоганно — а поводиться інакше. Це єдиний із трьох станів,
   якого око не ловить ніколи, тому він і названий окремо.

   ⚠️ ЗНАЧЕНЬ У ІМЕНІ БУВАЄ КІЛЬКА, і це не неохайність ДС: `--typo-sizes-h450`
   оголошений тричі (базово, з 768px і з 1440px) і на широкому екрані справді
   інший. Тому «перевизначено» ставиться лише тоді, коли макетне значення не
   збіглось із ЖОДНИМ приписаним. Один «канонічний» варіант дав би фальшиве
   звинувачення на кожній широкій сторінці — а фальшиве звинувачення тут
   коштує дорожче за пропущене: після двох таких дизайнер перестає вірити
   крапкам узагалі.

   ⚠️ ПОРІВНЮЄМО НЕ З computed. Значення токена в макеті беремо тим, яким його
   віддає `getPropertyValue('--x')` — тобто ПІДСТАВЛЕНИМ, але не зведеним до
   пікселів. Це навмисно: ДС пише `1rem`, браузер порахував би `16px`, і
   звірка з обчисленим оголосила б «перевизначено» кожен розмірний токен
   макета, який насправді збігається дослівно. */

/** Порожня (невідома) ДС — коли для напрямку її немає взагалі (`seo`) або
 *  напрямок не приїхав. `known:false` мусить ВИМИКАТИ звірку цілком, а не
 *  давати порожній словник: словник без імен оголосив би кожен токен
 *  сторінки «повз ДС», тобто збрехав би 198 разів на одному лендінгу. */
export const DS_NONE = { known: false, profile: null, tokens: new Map(), byValue: new Map() };

/**
 * Індекс ДС для одного напрямку з сирої мапи `{ім'я: [значення…]}`.
 * `byValue` — зворотний бік, «нормалізоване значення → імена токенів ДС»: саме
 * він відповідає на питання «а чим це має бути в ДС», заради якого T-40 і
 * почався.
 */
export function dsIndex(profile, tokens) {
  if (!profile || !tokens) return DS_NONE;
  const map = new Map();
  const byValue = new Map();
  for (const [name, values] of Object.entries(tokens)) {
    const list = Array.isArray(values) ? values.slice() : [String(values)];
    map.set(name, list);
    for (const v of list) {
      const key = normalizeValue(v);
      if (!key) continue;
      if (!byValue.has(key)) byValue.set(key, []);
      const arr = byValue.get(key);
      if (!arr.includes(name)) arr.push(name);
    }
  }
  return { known: true, profile, tokens: map, byValue };
}

/* ── Токени ДС ПРОСТОРУ (етап 2а, Task 7) ──────────────────────────────────

   Окрім статичного знімка напрямку (`ds-tokens.js`, ключ — напрямок задачі)
   у простору може бути свій постачальник токенів (модуль `css-tokens` читає
   CSS-файл), і сервер віддає їх на `GET /api/ds-tokens?space=<id>`. Профіль
   такої ДС має вигляд `space:<id>` — і береться ЛИШЕ з відповіді сервера, ніколи
   зі статики: знімок на диску про токени простору знати не може.

   Функції нижче ЧИСТІ (ні DOM, ні мережі, ні стану модуля): стан і запит живуть
   у `inspector-dom.js`, а тут — лише рішення «що це за відповідь» і «з чого
   будувати індекс», щоб їх можна було перевірити без браузера. */

const SPACE_PREFIX = 'space:';

/** Профіль ДС простору (`space:<id>`), а не напрямку (`united`). */
export function isSpaceProfile(profile) {
  return typeof profile === 'string' && profile.length > SPACE_PREFIX.length
    && profile.startsWith(SPACE_PREFIX);
}

/**
 * Відповідь `/api/ds-tokens` → `{ profile, tokens, source }` або `null`.
 *
 * `null` — це «токенів простору немає», і це ОДИН стан для всього, що не є
 * придатною відповіддю: `{profile:null}` (постачальника нема), `{profile:null,
 * error}` (модуль упав), відповідь про ІНШИЙ простір, порожня мапа, значення не
 * списком. Сервер уже перевіряє форму (`_token_map`), але інспектор не довіряє
 * наосліп те, що тримає між собою й вироком «повз ДС» на кожен токен сторінки.
 *
 * ⛔ ПОРОЖНЯ МАПА — теж `null`, не «ДС без токенів»: словник без імен оголосив
 * би кожну змінну сторінки повз дизайн-систему (див. `DS_NONE`).
 * А ось токен з порожнім СПИСКОМ значень — валідний: імʼя відоме, значення ні
 * (`var()`, що не розкрилась); вирок для нього — `dsVerdict`.
 */
export function spaceTokensFrom(body, sp) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null;
  if (typeof sp !== 'string' || !sp || body.profile !== SPACE_PREFIX + sp) return null;
  const tokens = body.tokens;
  if (!tokens || typeof tokens !== 'object' || Array.isArray(tokens)) return null;
  const names = Object.keys(tokens);
  if (!names.length) return null;
  for (const n of names) {
    const v = tokens[n];
    if (!Array.isArray(v) || !v.every((x) => typeof x === 'string')) return null;
  }
  return { profile: body.profile, tokens, source: typeof body.source === 'string' ? body.source : '' };
}

/**
 * Сира мапа `{імʼя: [значення…]}` для профілю, або `null` — «ДС невідома».
 *   · `space:<id>` — з `live` (відповідь сервера, пройшла `spaceTokensFrom`),
 *     і лише якщо вона про ТОЙ САМИЙ профіль; статика цього профілю не знає;
 *   · напрямок (`united`) — зі статичного знімка `statics`, ВЛАСНА властивість:
 *     `statics['constructor']` без цієї перевірки віддав би функцію `Object`, і
 *     `dsIndex` зібрав би з неї «відому» ДС без жодного токена.
 */
export function pickDsRaw(profile, live, statics) {
  if (typeof profile !== 'string' || !profile) return null;
  if (isSpaceProfile(profile)) return live && live.profile === profile ? live.tokens : null;
  if (!statics || !Object.prototype.hasOwnProperty.call(statics, profile)) return null;
  return statics[profile] || null;
}

/**
 * Другий вирок: чи є джерело значення дизайн-системою.
 *   'token'      — ім'я знає ДС, і макетне значення збіглось із приписаним;
 *   'off-ds'     — імені ДС не знає (`--bf-ink`);
 *   'overridden' — ім'я з ДС, але макет дав йому інше значення.
 *
 * `want` — що ДС приписує (список), або null. Потрібен не для вироку, а для
 * ТЕКСТУ: сказати «перевизначено» і не сказати, чим воно має бути, означає
 * лишити дизайнера з тим самим питанням, з якого все почалось.
 */
export function dsVerdict(ds, token, value) {
  if (!ds || !ds.known || !token) return { state: 'token', want: null };
  const want = ds.tokens.get(token);
  if (!want) return { state: 'off-ds', want: null };
  /* ПОРОЖНІЙ список — імʼя ДС знає, а що воно приписує, ні (токен простору з
     `var()`, яку модуль не розкрив). Порівнювати нема з чим, і «перевизначено»
     без приписаного значення — звинувачення, яке нічим підперти: гірше за
     пропущене (див. шапку вище). Тому 'token'; `want` лишається порожнім, і
     панель нічого не дописує. */
  if (!want.length) return { state: 'token', want };
  const have = normalizeValue(value);
  if (have && want.some((v) => normalizeValue(v) === have)) return { state: 'token', want };
  return { state: 'overridden', want };
}

/**
 * Впорядкувати підказки, зібрані з ДВОХ джерел (токени ДС і токени макета).
 *
 * ⛔ ДОВЕДЕНЕ ПОПЕРЕДУ ЗДОГАДНОГО — і це сильніше за «системне попереду
 * самопального». Спокуса протилежна: підказку з дизайн-системи хочеться
 * показати першою просто тому, що вона з ДС. Але `tier` відповідає на питання
 * «наскільки ми це ДОВЕЛИ», а `ds` — лише на «куди воно веде»; поставивши
 * друге поперед першого, ми відмиваємо здогад у доведення — рівно той дефект,
 * від якого лікувався T-38 (токен z-index, порекомендований для font-weight).
 *
 * Стабільно: усередині одного рівня порядок джерел зберігається, тобто ДС
 * лишається попереду макета там, де обидва однаково доведені.
 */
export function orderHints(list) {
  const rank = (h) => (h && h.tier === 'used' ? 0 : 1);
  return (list || [])
    .map((h, i) => ({ h, i }))
    .sort((a, b) => (rank(a.h) - rank(b.h)) || (a.i - b.i))
    .map((x) => x.h);
}
