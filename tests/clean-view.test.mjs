/**
 * Чистий перегляд макета (fb-01102026-7f7b6d): акорд ⇧⌘\ (⇧⌃\ поза macOS).
 * `code`, а не `key`: із Shift клавіша `\` дає `key: '|'`, а українська розкладка —
 * взагалі іншу літеру; `code: 'Backslash'` однаковий скрізь.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { isCleanChord } from "../app/clean-view.js";

const ev = (o) => ({ metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, key: "", code: "", ...o });

test("⇧⌘\\ і ⇧⌃\\ — так; ⌘\\ (панель шарів) і ⌥ — ні", () => {
  assert.equal(isCleanChord(ev({ metaKey: true, shiftKey: true, key: "|", code: "Backslash" })), true);
  assert.equal(isCleanChord(ev({ ctrlKey: true, shiftKey: true, key: "|", code: "Backslash" })), true);
  assert.equal(isCleanChord(ev({ metaKey: true, key: "\\", code: "Backslash" })), false, "⌘\\ — це панель шарів");
  assert.equal(isCleanChord(ev({ metaKey: true, shiftKey: true, altKey: true, code: "Backslash" })), false);
  assert.equal(isCleanChord(ev({ shiftKey: true, key: "|", code: "Backslash" })), false, "без ⌘ — набір тексту");
});
