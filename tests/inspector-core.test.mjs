import assert from 'node:assert';
import {
  specificity, compareSpec, pickWinner,
  varsIn, splitTop, splitBox, normalizeValue, tokenIndex, verdict, splitTopLevel,
  propFamilies, hintFor, valueShape, nameClaims, dsIndex, dsVerdict,
} from '../app/vendor/inspector-core.js';

// специфічність: [id, клас/атрибут/псевдоклас, тег/псевдоелемент]
assert.deepStrictEqual(specificity('#a'), [1, 0, 0]);
assert.deepStrictEqual(specificity('.b.c'), [0, 2, 0]);
assert.deepStrictEqual(specificity('div'), [0, 0, 1]);
assert.deepStrictEqual(specificity('*'), [0, 0, 0]);
assert.deepStrictEqual(specificity('.card:hover'), [0, 2, 0]);
assert.deepStrictEqual(specificity('a::before'), [0, 0, 2]);
assert.deepStrictEqual(specificity('.a > .b'), [0, 2, 0]);
assert.deepStrictEqual(specificity('[data-x="y"]'), [0, 1, 0]);
assert.deepStrictEqual(specificity(':not(.x) div'), [0, 1, 1]); // :not сам не рахується, вміст — так

// список селекторів (кома верхнього рівня) — МАКСИМУМ по гілках, не сума
assert.deepStrictEqual(specificity('.a, .b'), [0, 1, 0]);
// :where() — вага НУЛЬ, і сам, і вміст ігноруються
assert.deepStrictEqual(specificity(':where(.theme) .btn'), [0, 1, 0]);
// :is()/:has() — не рахуються самі, але додають специфічність найспецифічнішої гілки
assert.deepStrictEqual(specificity(':is(#id, .a) .c'), [1, 1, 0]);
assert.deepStrictEqual(specificity(':has(.a, #b) span'), [1, 0, 1]);
// легасі псевдоелемент з ОДНІЄЮ двокрапкою рахується як тег, не як клас
assert.deepStrictEqual(specificity('a:before'), [0, 0, 2]);

assert.strictEqual(compareSpec([0, 1, 0], [0, 0, 9]), 1);
assert.strictEqual(compareSpec([0, 1, 0], [0, 1, 0]), 0);
assert.strictEqual(compareSpec([0, 0, 1], [1, 0, 0]), -1);

// каскад: !important > inline > специфічність > порядок
const rule = (v, spec, order, extra = {}) => ({ value: v, spec, order, ...extra });
assert.strictEqual(pickWinner([]), null);
assert.strictEqual(pickWinner([rule('8px', [0, 1, 0], 1)]).value, '8px');
assert.strictEqual(pickWinner([rule('8px', [0, 1, 0], 1), rule('9px', [0, 2, 0], 0)]).value, '9px');
assert.strictEqual(pickWinner([rule('8px', [0, 1, 0], 1), rule('9px', [0, 1, 0], 0)]).value, '8px');
assert.strictEqual(pickWinner([
  rule('8px', [0, 9, 0], 5),
  rule('9px', [0, 0, 0], 0, { inline: true }),
]).value, '9px');
assert.strictEqual(pickWinner([
  rule('8px', [0, 0, 0], 0, { inline: true }),
  rule('9px', [0, 1, 0], 1, { important: true }),
]).value, '9px');
assert.strictEqual(pickWinner([rule('', [0, 1, 0], 0), rule('8px', [0, 0, 1], 1)]).value, '8px');

// імена токенів у сирому значенні
assert.deepStrictEqual(varsIn('var(--s-100)'), ['--s-100']);
assert.deepStrictEqual(varsIn('var(--a) var(--b)'), ['--a', '--b']);
assert.deepStrictEqual(varsIn('calc(var(--a) * 2)'), ['--a']);
assert.deepStrictEqual(varsIn('13px'), []);
assert.deepStrictEqual(varsIn(null), []);
assert.deepStrictEqual(varsIn('var(--a) var(--a)'), ['--a']); // без дублікатів

// розбиття значення по верхньому рівню (дужки не ріжемо)
assert.deepStrictEqual(splitTop('var(--a) var(--b)'), ['var(--a)', 'var(--b)']);
assert.deepStrictEqual(splitTop('1px  solid   red'), ['1px', 'solid', 'red']);
assert.deepStrictEqual(splitTop('a) b'), ['a)', 'b']); // незбалансована дужка не ламає розбір

// позиційний розбір padding/margin: 1–4 значення
assert.deepStrictEqual(splitBox('4px'), { top: '4px', right: '4px', bottom: '4px', left: '4px' });
assert.deepStrictEqual(splitBox('4px 8px'), { top: '4px', right: '8px', bottom: '4px', left: '8px' });
assert.deepStrictEqual(splitBox('1px 2px 3px'), { top: '1px', right: '2px', bottom: '3px', left: '2px' });
assert.deepStrictEqual(splitBox('1px 2px 3px 4px'), { top: '1px', right: '2px', bottom: '3px', left: '4px' });
assert.strictEqual(splitBox('   '), null);
assert.strictEqual(splitBox('1px 2px 3px 4px 5px'), null); // більше 4 частин — не бокс

// нормалізація значень для порівняння
assert.strictEqual(normalizeValue('#FFF'), '#ffffff');
assert.strictEqual(normalizeValue('#ffffff'), '#ffffff');
assert.strictEqual(normalizeValue('rgb(0, 53, 148)'), '#003594');
assert.strictEqual(normalizeValue('rgba(0, 53, 148, 1)'), '#003594');
assert.strictEqual(normalizeValue('  "E-Ukraine",  sans-serif '), 'e-ukraine, sans-serif');
assert.strictEqual(normalizeValue('0'), '0px');
assert.strictEqual(normalizeValue('"E-Ukraine",sans-serif'), 'e-ukraine, sans-serif'); // пробіл після коми
assert.strictEqual(normalizeValue('.2'), '0.2'); // провідний нуль
assert.strictEqual(normalizeValue('#003594ff'), '#003594'); // 8-значний hex, альфа ff
assert.strictEqual(normalizeValue('transparent'), 'rgba(0, 0, 0, 0)');

// зворотний індекс «значення → токени»
const idx = tokenIndex([
  { name: '--n-100', value: '#FFF' },
  { name: '--white', value: '#ffffff' },
  { name: '--s-100', value: '8px' },
  { name: 'font-size', value: '8px' }, // не токен — ігнорується
]);
assert.deepStrictEqual(idx.get('#ffffff'), ['--n-100', '--white']);
assert.deepStrictEqual(idx.get('8px'), ['--s-100']);
assert.doesNotThrow(() => tokenIndex([null])); // null-елемент не кидає

// вирок для одного значення
assert.strictEqual(verdict({ raw: 'var(--s-100)', token: '--s-100', tokenValue: '8px', computed: '8px' }), 'token');
assert.strictEqual(verdict({ raw: 'var(--s-100)', token: '--s-100', tokenValue: '8px', computed: '12px' }), 'unlinked');
assert.strictEqual(verdict({ raw: '13px', token: null, tokenValue: null, computed: '13px' }), 'hardcode');
assert.strictEqual(verdict({ raw: '1em', token: null, tokenValue: null, computed: '16px' }), 'hardcode');
assert.strictEqual(verdict({ raw: null, token: null, tokenValue: null, computed: '8px' }), 'unlinked');
// verdict сама зводить raw ↔ token — не вірить викликачеві на слово
assert.strictEqual(verdict({ raw: '13px', token: '--s-100', tokenValue: '13px', computed: '13px' }), 'hardcode'); // літерал, хоч токен і підсунули
assert.strictEqual(verdict({ raw: 'var(--a)', token: '--b', tokenValue: '8px', computed: '8px' }), 'unlinked'); // чуже ім'я токена
assert.strictEqual(verdict({ raw: 'var(--s-100)', token: '--s-100', tokenValue: '', computed: '' }), 'unlinked'); // порожні НЕ збіг
assert.strictEqual(verdict({ raw: 'var(--unknown)', token: null, tokenValue: null, computed: '8px' }), 'unlinked'); // var() без знайденого токена — unlinked, не hardcode

// розбиття СПИСКУ СЕЛЕКТОРІВ по комі верхнього рівня — кома всередині :is()/:where()
// НЕ розділювач; наївний String.split(',') тут калічить селектор навпіл
assert.deepStrictEqual(splitTopLevel('.a, .b', ','), ['.a', ' .b']);
assert.deepStrictEqual(splitTopLevel(':is(.a, .b) .c', ','), [':is(.a, .b) .c']);
assert.deepStrictEqual(splitTopLevel(':is(.a, .b) .c, .d', ','), [':is(.a, .b) .c', ' .d']);
// ВІДОМА МЕЖА, зафіксована свідомо: рахуємо лише круглі дужки, тож кома в
// значенні атрибута рве селектор навпіл. Ризик мізерний (кома в [attr="…"]
// у макетах практично не трапляється), а лагодження зачепило б ядро, яке
// вже пройшло ревʼю. Хто це виправить — оновить і цей асерт.
assert.deepStrictEqual(splitTopLevel('[data-x="a,b"] .c', ','), ['[data-x="a', 'b"] .c']);

// ── підказка не сміє радити токен ЧУЖОЇ КАТЕГОРІЇ ─────────────────────────
// Кейс НЕ вигаданий: 17.09.2026 на макеті bf360, `h1.hero__title`, рядок
// `font-weight: 700` дістав підказку «хардкод → --fw-bold, --z-tooltip».
// `--z-tooltip: 700` — це z-index, запропонований як виправлення насиченості
// шрифту. Значення в токенів РІВНІ, тож зворотний індекс схлопує їх в один
// ключ — і саме це спершу доводимо, інакше перевірка нижче була б зелена й на
// макеті, де колізії просто немає.
const bf360 = tokenIndex([
  { name: '--fw-bold', value: '700' },
  { name: '--z-tooltip', value: '700' },
]);
assert.deepStrictEqual(bf360.get('700'), ['--fw-bold', '--z-tooltip']); // колізія РЕАЛЬНА

const names = (list) => list.map((h) => h.name);
const tiers = (list) => list.map((h) => h.tier);

// ⛔ ГОЛОВНЕ. Обидва токени в bf360 НІДЕ не вжиті (перевірено grep'ом по макету),
// тобто вжиток тут не рятує НІКОГО, а форма значення однакова — безрозмірне
// число. Розрізняє їх лише ім'я, і тільки на виключення: «--z-*» серед ваг
// шрифту заперечує себе сам.
assert.deepStrictEqual(hintFor('font-weight', bf360.get('700'), new Map(), '700'),
  [{ name: '--fw-bold', tier: 'shape' }]);
// дзеркально: для z-index виключається вже вага
assert.deepStrictEqual(hintFor('z-index', bf360.get('700'), new Map(), '700'),
  [{ name: '--z-tooltip', tier: 'shape' }]);

// Вжиток сильніший за ім'я: якщо документ каже, що токен вживають саме для ваги
// шрифту, це ФАКТ, і жодна ознака його не переважує.
const bfUse = new Map([
  ['--fw-bold', new Set(propFamilies('font-weight'))],
  ['--z-tooltip', new Set(propFamilies('z-index'))],
]);
assert.deepStrictEqual(hintFor('font-weight', bf360.get('700'), bfUse, '700'),
  [{ name: '--fw-bold', tier: 'used' }]);

// Форма значення сама по собі НЕ рятує — і це не здогад, а те, чому на
// безрозмірних числах довелось шукати ще одну ознаку.
assert.strictEqual(valueShape('700'), 'number');
assert.strictEqual(valueShape('700'), valueShape('700')); // z-index і вага — та сама форма

// ── рівень 2: невживаний токен, чия ФОРМА годиться властивості ─────────────
// Те, заради чого рівень і заведено: дизайнер захардкодив колір, а в ДС лежить
// готовий токен рівно з цим значенням — просто його ще ніде не вжили.
assert.deepStrictEqual(
  hintFor('background-color', ['--color-primary-100'], new Map(), '#f3f2ff'),
  [{ name: '--color-primary-100', tier: 'shape' }]);
// але колір НЕ пролізе туди, де кольору бути не може
assert.deepStrictEqual(hintFor('font-weight', ['--color-primary-100'], new Map(), '#f3f2ff'), []);
// а довжина — у вагу шрифту чи z-index
assert.deepStrictEqual(hintFor('z-index', ['--spacings-16'], new Map(), '16px'), []);
// родини з ключовими словами (display, font-family, shadow) здогадів не беруть
// узагалі: збіг тексту `none` нічого не доводить — саме так народилась порада
// «display: none → --shadow-s» на живому макеті.
assert.deepStrictEqual(hintFor('display', ['--shadow-s'], new Map(), 'none'), []);
assert.deepStrictEqual(hintFor('font-family', ['--ff-x'], new Map(), 'inter, sans-serif'), []);

// ── ім'я виключає, але не включає ─────────────────────────────────────────
assert.deepStrictEqual([...nameClaims('--z-tooltip')], ['z-index']);
assert.deepStrictEqual([...nameClaims('--fw-bold')], ['font-weight']);
assert.deepStrictEqual([...nameClaims('--corner-radius-12')], ['radius']);
assert.deepStrictEqual([...nameClaims('--bf-ink')], ['color']);
assert.deepStrictEqual([...nameClaims('--mystery-42')], []); // невпізнане ім'я мовчить
// заявлена чужа родина знімає кандидата…
assert.deepStrictEqual(hintFor('padding-top', ['--corner-radius-12'], new Map(), '12px'), []);
assert.deepStrictEqual(hintFor('margin-left', ['--shadow-z-index-eleveation-1-blur'],
  new Map(), '25px'), []);
assert.deepStrictEqual(hintFor('padding-top', ['--typo-sizes-h300'], new Map(), '14px'), []);
// знято з живого макета: `--blur-glass: 16px` пропонувався для `line-height`,
// бо ім'я нічого не заявляло — 'blur' у словнику це закрив
assert.deepStrictEqual(hintFor('line-height', ['--blur-glass'], new Map(), '16px'), []);
// …а мовчазне ім'я лишає рішення за формою — ім'я НЕ мусить нічого доводити
assert.deepStrictEqual(names(hintFor('padding-top', ['--mystery-42'], new Map(), '12px')),
  ['--mystery-42']);
// заявка буває широкою: `size` — і кегль, і габарит, тож габариту не заперечує
assert.deepStrictEqual(names(hintFor('width', ['--icon-size-16'], new Map(), '16px')),
  ['--icon-size-16']);

// ── вжиток б'є все ────────────────────────────────────────────────────────
// Токен, ужитий для ЧУЖОЇ родини, викидається без другого шансу: документ прямо
// каже, що це токен кегля, і форма значення цього не переважить.
const usedForFontSize = new Map([['--typo-sizes-h300', new Set(['font-size'])]]);
assert.deepStrictEqual(hintFor('padding-top', ['--typo-sizes-h300'], usedForFontSize, '14px'), []);
// а ужитий для СВОЄЇ — доведений, хай навіть ім'я невпізнане
assert.deepStrictEqual(hintFor('padding-top', ['--mystery-42'],
  new Map([['--mystery-42', new Set(['spacing'])]]), '12px'),
[{ name: '--mystery-42', tier: 'used' }]);

// ── порядок і обрізання ───────────────────────────────────────────────────
// Доведені йдуть ПЕРШИМИ: у пакеті для Клода перші три — це те, з чого він
// почне, тож здогад не сміє відтіснити факт.
const mix = ['--sp-guess-a', '--sp-used-a', '--sp-guess-b', '--sp-used-b'];
const mixUse = new Map([['--sp-used-a', new Set(['spacing'])],
  ['--sp-used-b', new Set(['spacing'])]]);
assert.deepStrictEqual(names(hintFor('padding-top', mix, mixUse, '16px')),
  ['--sp-used-a', '--sp-used-b', '--sp-guess-a']);
assert.deepStrictEqual(tiers(hintFor('padding-top', mix, mixUse, '16px')),
  ['used', 'used', 'shape']);

// Відсів мусить іти ПЕРЕД обрізанням до трьох: інакше чужі токени займають усі
// місця й витісняють правильні (у зворотному індексі порядок — порядок
// оголошення, тож чужі цілком можуть стояти першими).
const many = ['--z-a', '--z-b', '--z-c', '--sp-1', '--sp-2', '--sp-3', '--sp-4'];
const manyUse = new Map(many.map((n) => [n,
  new Set(propFamilies(n.startsWith('--z') ? 'z-index' : 'padding'))]));
assert.deepStrictEqual(names(hintFor('padding-top', many, manyUse, '16px')),
  ['--sp-1', '--sp-2', '--sp-3']);

// Родина, а не гола властивість: відступи — одна шкала ДС, тож токен, ужитий у
// `margin`, доречний і в `padding-top`, і в `gap`. Без цього фільтр із
// корисного став би шкідливим — у макеті токен відступу вживають то там, то там.
const spacing = new Map([['--sp-2', new Set(propFamilies('margin'))]]);
for (const prop of ['padding-top', 'margin-left', 'padding-inline-start', 'gap', 'column-gap']) {
  assert.deepStrictEqual(names(hintFor(prop, ['--sp-2'], spacing, '8px')), ['--sp-2'], prop);
}
// але не в чужу шкалу: радіус, товщина рамки й розмір шрифту — інші шкали
for (const prop of ['border-radius', 'border-width', 'font-size', 'width']) {
  assert.deepStrictEqual(hintFor(prop, ['--sp-2'], spacing, '8px'), [], prop);
}

// Кольори теж одна родина: токен із `color` доречний у `background-color` і
// `border-color` — це та сама палітра.
const ink = new Map([['--c-ink', new Set(propFamilies('color'))]]);
assert.deepStrictEqual(names(hintFor('background-color', ['--c-ink'], ink, '#123456')), ['--c-ink']);
assert.deepStrictEqual(names(hintFor('border-top-color', ['--c-ink'], ink, '#123456')), ['--c-ink']);

// Шорткат належить кільком родинам одразу (`border: <товщина> solid <колір>`) —
// і це безпечно: кандидати добираються за ЗНАЧЕННЯМ, а частини шортката мають
// різні значення, тож колір не опиниться в кандидатах для товщини.
assert.deepStrictEqual(propFamilies('border'), ['line-width', 'color']);
const inBorder = new Map([['--bw', new Set(propFamilies('border'))]]);
assert.deepStrictEqual(names(hintFor('border-width', ['--bw'], inBorder, '1px')), ['--bw']);

// Оголошення кастомної властивості (`--fg: var(--brand)`) — НЕ вжиток: категорії
// псевдоніма ми не знаємо, а той псевдонім, що в сторінці реально вжитий, і є
// чеснішою порадою.
assert.deepStrictEqual(propFamilies('--fg'), []);
assert.deepStrictEqual(hintFor('--fg', ['--brand'],
  new Map([['--brand', new Set(['color'])]]), '#123456'), []);
// властивість, якої немає в таблиці родин, сама собі родина — найвужчий дефолт
assert.deepStrictEqual(propFamilies('letter-spacing'), ['letter-spacing']);
assert.deepStrictEqual(propFamilies('z-index'), ['z-index']);

// Порожні/криві входи не кидають — describe() кличе це на кожну властивість
assert.deepStrictEqual(hintFor('font-weight', ['--fw-bold'], null, '700'),
  [{ name: '--fw-bold', tier: 'shape' }]);
assert.deepStrictEqual(hintFor('font-weight', null, new Map(), '700'), []);
assert.deepStrictEqual(hintFor('font-weight', ['--x'], new Map(), null), []);

// dsVerdict: токен ДС із ПОРОЖНІМ списком значень (var(), що не розкрилась —
// імʼя відоме, значення ні) — це 'token', а не 'overridden': порівнювати нема з
// чим, і звинувачувати макет у перевизначенні, не знаючи приписаного, — брехня.
const dsE = dsIndex('space:s', { '--a': [], '--b': ['#ffffff'] });
assert.deepStrictEqual(dsVerdict(dsE, '--a', '#123456'), { state: 'token', want: [] });
assert.strictEqual(dsVerdict(dsE, '--b', '#123456').state, 'overridden'); // контроль: непорожній — як раніше
assert.strictEqual(dsVerdict(dsE, '--b', '#ffffff').state, 'token');
assert.strictEqual(dsVerdict(dsE, '--zzz', '#ffffff').state, 'off-ds');
assert.deepStrictEqual(dsVerdict(dsE, null, '#ffffff'), { state: 'token', want: null });
assert.deepStrictEqual(dsE.tokens.get('--a'), []);
assert.strictEqual(dsE.byValue.size, 1, 'порожній список у зворотний індекс нічого не кладе');

console.log('inspector-core: OK');
