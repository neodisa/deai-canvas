/**
 * Етап В (0.28.0): проводка поповерів «Баг / ідея» і «Оновлення» в `app/app.js` (чисті шматки — `tests/ask-dialogs.test.mjs`,
 * поведінка в браузері — `tests/live/feedback.test.mjs` і `update.test.mjs`).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

test("«Баг / ідея»: якір лише з острівця, поповер над кнопкою; з палітри — модалка", () => {
  assert.match(app, /feedback: \(val, el\) => openFeedback\(el\?\.closest\?\.\('#hud'\) \? el : null\),/);
  assert.match(app, /async function openFeedback\(anchor = null\)/);
  assert.match(app, /anchor, place: 'above',/);
});

test("чернетка відгуку: у памʼяті вкладки, оновлюється на input/change, очищається після успішної відправки", () => {
  assert.match(app, /\.\.\.\(fbDraft \|\| \{\}\),/);
  assert.match(app, /const keep = \(\) => \{ fbDraft = fbDraftOf\(form\); \};/);
  assert.match(app, /form\.addEventListener\('input', keep\);\s*form\.addEventListener\('change', keep\);/);
  assert.match(app, /fbDraft = null;\s*return undefined;/);
  assert.match(app, /return \{ kind: v\.kind, text: v\.text, contact: v\.contact, includeDiag: v\.diag, includeShot: v\.shot \};/);
});

test("оновлення: якір лише з пігулки, поповер під нею; «Що нового» без якоря", () => {
  assert.match(app, /update: \(val, el\) => openUpdateDialog\(el\?\.classList\?\.contains\('upd-pill'\) \? el : null\),/);
  assert.match(app, /async function openUpdateDialog\(anchor = null\)/);
  assert.match(app, /anchor, place: 'below',/);
  assert.match(app, /updatenotes: \(\) => openUpdateDialog\(\),/);
});
