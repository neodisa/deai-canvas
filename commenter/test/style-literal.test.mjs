import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/*
 * The stylesheet lives in a TEMPLATE LITERAL, so a backtick inside it — in a
 * comment, most likely, since that is where prose goes — silently ends the
 * literal and the rest of the CSS becomes JavaScript.
 *
 * The build does catch this. It just does not SAY it: esbuild reports the first
 * token it choked on, which reads like `Expected ";" but found "open"` pointing
 * at the middle of a Ukrainian sentence. That cost two debugging cycles twice
 * over. This test exists for the message, not for the detection — it names the
 * rule so the next person spends a second instead of ten minutes.
 *
 * The project convention for quoting inside comments is «guillemets», which is
 * also what the i18n literal guard in design-canvas relies on.
 */
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
  '..', 'src', 'comment-layer.js');
const src = readFileSync(SRC, 'utf8');

const OPEN = 'const STYLE = `';
const start = src.indexOf(OPEN);
assert.notEqual(start, -1, 'STYLE literal not found — did it get renamed?');
const bodyStart = start + OPEN.length;
const end = src.indexOf('\n  `;', bodyStart);
assert.notEqual(end, -1, 'end of the STYLE literal not found');

const offenders = src.slice(bodyStart, end).split('\n')
  .map((line, i) => [i + 1, line])
  .filter(([, line]) => line.includes('`'));

assert.deepEqual(offenders, [],
  'backtick inside the STYLE template literal — it ends the literal and turns '
  + 'the rest of the CSS into JavaScript. Use «guillemets» in comments:\n'
  + offenders.map(([n, l]) => `  +${n}: ${l.trim()}`).join('\n'));

console.log('style-literal: OK');
