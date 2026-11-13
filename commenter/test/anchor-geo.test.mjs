import assert from 'node:assert';
import { findMatchIn, GEO_TEXT_CAP, MATCH_THRESHOLD } from '../src/anchor.js';

// `findMatchIn` — той самий `findMatch`, але по записах геометрії кадру, а не по
// DOM (T-45: піни на «Огляді»). Кожен блок нижче — одне правило `findMatch`,
// переписане на записи. Розійдуться — пін на «Огляді» стоятиме не там, де в
// живому виді; повний паритет на справжньому DOM стереже живий тест канваса
// `tests/live/overview-comments.test.mjs`.

const E = (tag, path, text, stableId = null) => ({ tag, path, text, stableId });

// ── stableId, єдиний → score 1, навіть коли текст уже інший ────────────────
{
  const es = [E('div', ['div[0]'], 'a'), E('button', ['div[0]', 'button[0]'], 'купити', 'testid:buy')];
  assert.deepEqual(findMatchIn({ tag: 'button', stableId: 'testid:buy', text: 'інше', path: [] }, es),
    { i: 1, score: 1 }, 'unique stableId wins outright');
}

// ── stableId, кілька → 0.9, кращий за текстом ──────────────────────────────
{
  const es = [E('a', ['a[0]'], 'один', 'id:x'), E('a', ['a[1]'], 'два три', 'id:x')];
  assert.deepEqual(findMatchIn({ tag: 'a', stableId: 'id:x', text: 'два три', path: [] }, es),
    { i: 1, score: 0.9 }, 'duplicated stableId → best text among them');
}

// ── інший тег не кандидат; вага 0.25 шлях + 0.75 текст ─────────────────────
{
  const es = [E('p', ['p[0]'], 'привіт світ'), E('h1', ['h1[0]'], 'привіт світ'),
              E('h1', ['div[0]', 'h1[0]'], 'інше')];
  const m = findMatchIn({ tag: 'h1', text: 'привіт світ', path: ['h1[0]'] }, es);
  assert.equal(m.i, 1, 'same tag + same text + same path');
  assert.equal(m.score, 1);
}
{
  // Шлях збігся повністю, текст ні — проти тексту без шляху. 0.25 < 0.75: текст
  // важить утричі більше, тож виграє другий. Ваги 0.5/0.5 дали б нічию і
  // перший за порядком — тест червоніє.
  const es = [E('span', ['div[0]', 'span[0]'], 'зовсім інше'), E('span', ['p[4]', 'span[2]'], 'ціна 100')];
  const m = findMatchIn({ tag: 'span', text: 'ціна 100', path: ['div[0]', 'span[0]'] }, es);
  assert.equal(m.i, 1, 'text outweighs path 3:1');
  assert.equal(m.score, 0.75);
}

// ── нічого немає → i:-1, score:-1 (як {el:null, score:-1} у findMatch) ─────
assert.deepEqual(findMatchIn({ tag: 'div', text: 'x', path: [] }, []), { i: -1, score: -1 });
assert.deepEqual(findMatchIn(null, null), { i: -1, score: -1 }, 'tolerates missing fp / entries');

// ── довгий текст ріжеться ОДНАКОВО з обох боків ────────────────────────────
// Геометрія зберігає текст зрізаним (контейнер несе текст усіх нащадків). Якби
// відбиток піна порівнювався цілим, контейнер ніколи не збігся б сам із собою.
{
  const long = 'слово '.repeat(GEO_TEXT_CAP).trim() + ' хвіст-що-не-влазить';
  const es = [E('div', ['div[0]'], long.slice(0, GEO_TEXT_CAP))];
  assert.equal(findMatchIn({ tag: 'div', text: long, path: ['div[0]'] }, es).score, 1,
    'container must still match itself');
}

assert.ok(MATCH_THRESHOLD > 0 && MATCH_THRESHOLD < 1);
console.log('anchor-geo: OK');
