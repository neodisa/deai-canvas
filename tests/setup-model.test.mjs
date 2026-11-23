import assert from "node:assert/strict";
import test from "node:test";
import { PW_STATE_KEY, claudeRow, pwItem, pwLine, runCommand, shotsBlock, shq } from "../app/setup-model.js";

test("shotsBlock: бракує Playwright чи Chromium — рядок, причина й команда; без Node — без команди; решта — нічого не блокує", () => {
  const cmd = "cd /d && npm install && npx playwright install chromium";
  for (const state of ["no-playwright", "no-browser"]) {
    assert.deepEqual(shotsBlock({ state, command: cmd }), { lineKey: "frShotsNoBrowser", whyKey: "frShotsNoBrowserWhy", command: cmd });
  }
  assert.deepEqual(shotsBlock({ state: "no-node", command: null }), { lineKey: "frShotsNoNode", whyKey: "frShotsNoNodeWhy", command: "" });
  for (const s of [{ state: "ok" }, { state: "unknown" }, null, undefined, {}]) assert.equal(shotsBlock(s), null);
});

test("claudeRow: чотири стани; «Підключити» лише для missing і no-import", () => {
  assert.deepEqual(claudeRow({ state: "ok" }), { icon: "check", tone: "ok", textKey: "frClaudeOk", connect: false });
  assert.deepEqual(claudeRow({ state: "missing" }), { icon: "warn", tone: "warn", textKey: "frClaudeMissing", connect: true });
  assert.deepEqual(claudeRow({ state: "no-import" }), { icon: "warn", tone: "warn", textKey: "frClaudeNoImport", connect: true });
  assert.deepEqual(claudeRow({ state: "unreadable" }), { icon: "warn", tone: "warn", textKey: "frClaudeUnreadable", connect: false });
  assert.equal(claudeRow(undefined), null);
  assert.equal(claudeRow({ state: "weird" }), null);
});

test("shq і runCommand: тека простору з шляху AGENTS.md; пробіли й лапки — у безпечних лапках", () => {
  assert.equal(shq("/Users/a/deai-work/p"), "/Users/a/deai-work/p");
  assert.equal(shq("/Users/a/My Work"), "'/Users/a/My Work'");
  assert.equal(shq("/x/it's"), "'/x/it'\\''s'");
  assert.equal(runCommand("/Users/a/deai-work/p/AGENTS.md"), "cd /Users/a/deai-work/p && claude");
  assert.equal(runCommand("/Users/a/Liga Tools/p/AGENTS.md"), "cd '/Users/a/Liga Tools/p' && claude");
  assert.equal(runCommand(""), "");
  assert.equal(runCommand(null), "");
});

const PUB = (settings, extra = {}) => ({ id: "static-publish", roles: ["publish"], enabled: true, status: "ok", settings, ...extra });
const PW = (set) => ({ key: "password", type: "secret", set });

test("pwLine: лише увімкнений постачальник publish із секретом password; три стани", () => {
  assert.deepEqual(pwLine(PUB([PW(true)])), { state: "set" });
  assert.deepEqual(pwLine(PUB([PW(false)])), { state: "unset" });
  assert.deepEqual(pwLine(PUB([PW(null)])), { state: "unknown" });
  assert.equal(pwLine(PUB([PW(true)], { enabled: false })), null);
  assert.equal(pwLine(PUB([PW(true)], { status: "missing" })), null);
  assert.equal(pwLine(PUB([PW(true)], { roles: ["tokens"] })), null);
  assert.equal(pwLine(PUB([{ key: "password", type: "string" }])), null);
  assert.equal(pwLine(PUB([{ key: "folder", type: "path" }])), null);
  assert.equal(pwLine(null), null);
});

test("pwItem: поле простору publish_password; нема поля — нема пункту", () => {
  assert.deepEqual(pwItem({ id: "p", publish_password: true }), { state: "set" });
  assert.deepEqual(pwItem({ id: "p", publish_password: false }), { state: "unset" });
  assert.deepEqual(pwItem({ id: "p", publish_password: null }), { state: "unknown" });
  assert.equal(pwItem({ id: "p" }), null);
  assert.equal(pwItem(null), null);
  assert.deepEqual(PW_STATE_KEY, { set: "frPwSet", unset: "frPwUnset", unknown: "frPwUnknown" });
});
