import assert from 'node:assert';
import { buildContextBundle, truncate, iterationOf } from '../src/context-bundle.js';

// truncate caps long strings and marks them
{
  const long = 'x'.repeat(7000);
  const out = truncate(long, 6000);
  assert.ok(out.length < 6100, 'truncated length near cap');
  assert.ok(out.endsWith('…[truncated]'), 'truncation marker present');
}
// short strings pass through untouched
{
  assert.equal(truncate('<div/>', 6000), '<div/>');
}
// bundle assembles htmlSnapshot + meta and normalizes text
{
  const b = buildContextBundle({
    outerHTML: '<div>hi</div>', text: '  hello   world  ',
    url: 'http://x/a', route: '/a', version: 'v3',
    viewport: { w: 100, h: 200 }, ts: '2026-07-01 10:00',
  });
  assert.equal(b.htmlSnapshot.outerHTML, '<div>hi</div>');
  assert.equal(b.htmlSnapshot.text, 'hello world');
  assert.equal(b.meta.url, 'http://x/a');
  assert.equal(b.meta.route, '/a');
  assert.equal(b.meta.version, 'v3');
  assert.deepEqual(b.meta.viewport, { w: 100, h: 200 });
  assert.equal(b.meta.ts, '2026-07-01 10:00');
}
// missing input is safe
{
  const b = buildContextBundle();
  assert.equal(b.htmlSnapshot.outerHTML, '');
  assert.equal(b.htmlSnapshot.text, '');
  assert.equal(b.meta.version, null);
}
// iterationOf: чисто числовий префікс тегу версії = ітерація; решта → null (legacy)
{
  assert.equal(iterationOf('3'), '3');
  assert.equal(iterationOf('3/stattia'), '3');
  assert.equal(iterationOf('2'), '2');
  assert.equal(iterationOf('12/hub-avtoriv'), '12');
  assert.equal(iterationOf('it1'), null);          // стара конвенція → legacy
  assert.equal(iterationOf('2026-07-01-1'), null); // дата-тег → legacy
  assert.equal(iterationOf(null), null);
  assert.equal(iterationOf(undefined), null);
  assert.equal(iterationOf(''), null);
}
console.log('context-bundle: OK');
