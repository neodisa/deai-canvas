import assert from "node:assert/strict";
import test from "node:test";
import { DICT } from "../app/i18n.js";
import { PW_STATE_KEY, claudeRow, claudeToastKey, unhookToastKey, pwItem, pwLine, runCommand, shotsBlock, shq } from "../app/setup-model.js";

test("shotsBlock: бракує Playwright чи Chromium — рядок, причина й команда; без Node — без команди; решта — нічого не блокує", () => {
  const cmd = "cd /d && npm install && npx playwright install chromium";
  for (const state of ["no-playwright", "no-browser"]) {
    assert.deepEqual(shotsBlock({ state, command: cmd }), { lineKey: "frShotsNoBrowser", whyKey: "frShotsNoBrowserWhy", command: cmd });
  }
  assert.deepEqual(shotsBlock({ state: "no-node", command: null }), { lineKey: "frShotsNoNode", whyKey: "frShotsNoNodeWhy", command: "" });
  for (const s of [{ state: "ok" }, { state: "unknown" }, null, undefined, {}]) assert.equal(shotsBlock(s), null);
});

const MD = { code: "CLAUDE.md", textKey: "frClaudeWillMd" };
const HOOK = { code: ".claude/settings.local.json", textKey: "frClaudeWillHook" };
const row = (icon, textKey, items = [], button = null) => ({ icon, tone: icon === "check" ? "ok" : "warn", textKey, items, button });
const H = (state) => ({ state });

test("claudeRow, старий сервер без `hook`: як у 0.33.0 — текст про CLAUDE.md, «Підключити» для missing і no-import", () => {
  assert.deepEqual(claudeRow({ state: "ok" }), row("check", "frClaudeOk"));
  assert.deepEqual(claudeRow({ state: "missing" }), row("warn", "frClaudeMissing", [], "connect"));
  assert.deepEqual(claudeRow({ state: "no-import" }), row("warn", "frClaudeNoImport", [], "connect"));
  assert.deepEqual(claudeRow({ state: "ok" }, undefined), row("check", "frClaudeOk"));
  assert.deepEqual(claudeRow({ state: "ok" }, { state: "weird" }), row("check", "frClaudeOk"), "невідомий стан хука — як старий сервер");
});

test("claudeRow, стан 1: CLAUDE.md не підключено — список (CLAUDE.md і, коли хук missing/stale, хук), кнопка «Підключити»", () => {
  for (const cs of ["missing", "no-import"]) {
    assert.deepEqual(claudeRow({ state: cs }, H("missing")), row("warn", null, [MD, HOOK], "connect"));
    assert.deepEqual(claudeRow({ state: cs }, H("stale")), row("warn", null, [MD, HOOK], "connect"));
    for (const hs of ["ok", "elsewhere", "unreadable"]) {
      assert.deepEqual(claudeRow({ state: cs }, H(hs)), row("warn", null, [MD], "connect"), `${cs}/${hs}: хука в списку нема`);
    }
  }
});

test("claudeRow, стани 2–6: CLAUDE.md ok — хук missing / ok / stale / elsewhere / unreadable", () => {
  const ok = { state: "ok" };
  assert.deepEqual(claudeRow(ok, H("missing")), row("warn", null, [HOOK], "connect"));
  assert.deepEqual(claudeRow(ok, H("ok")), row("check", "frClaudeHookOk", [], "disconnect"));
  assert.deepEqual(claudeRow(ok, H("stale")), row("warn", "frClaudeHookStale", [], "update"));
  assert.deepEqual(claudeRow(ok, H("elsewhere")), row("warn", "frClaudeHookElsewhere"));
  assert.deepEqual(claudeRow(ok, H("unreadable")), row("warn", "frClaudeHookUnreadable"));
});

test("claudeRow: CLAUDE.md не читається — як зараз (без кнопки й списку), хук неважливий; стану нема — null", () => {
  for (const hook of [undefined, H("missing"), H("ok"), H("stale"), H("elsewhere"), H("unreadable")]) {
    assert.deepEqual(claudeRow({ state: "unreadable" }, hook), row("warn", "frClaudeUnreadable"));
  }
  assert.equal(claudeRow(undefined), null);
  assert.equal(claudeRow(undefined, H("ok")), null);
  assert.equal(claudeRow({ state: "weird" }, H("ok")), null);
});

test("claudeRow: усі ключі рядка є в обох мовах", () => {
  const keys = new Set(["frClaudeTitle", "frClaudeConnect", "frClaudeUpdate", "frClaudeDisconnect", "frClaudeConnected",
    "frClaudeFailed", "frHookConnected", "frHookDisconnected", "frHookFailed"]);
  for (const cs of ["ok", "missing", "no-import", "unreadable"]) {
    for (const hook of [undefined, H("ok"), H("missing"), H("stale"), H("elsewhere"), H("unreadable")]) {
      const r = claudeRow({ state: cs }, hook);
      if (r.textKey) keys.add(r.textKey);
      for (const i of r.items) keys.add(i.textKey);
    }
  }
  for (const lang of ["uk", "en"]) for (const k of keys) assert.ok(DICT[lang][k] !== undefined, `${lang}: немає ключа ${k}`);
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

test("claudeToastKey: збій хука (hookError) сильніший за ok; старий сервер і elsewhere/unreadable — тост CLAUDE.md", () => {
  assert.equal(claudeToastKey({ hookError: "changed", hook: { state: "ok" } }), "frHookFailed");
  assert.equal(claudeToastKey({ hookError: "unreadable", hook: { state: "missing" } }), "frHookFailed");
  assert.equal(claudeToastKey({ hook: { state: "ok" } }), "frHookConnected");
  assert.equal(claudeToastKey({ claude: { state: "ok" } }), "frClaudeConnected", "старий сервер без hook");
  for (const state of ["elsewhere", "unreadable", "missing", "stale"]) assert.equal(claudeToastKey({ hook: { state } }), "frClaudeConnected", state);
});

test("unhookToastKey: з hookError — збій, без нього — «Хук відключено»", () => {
  assert.equal(unhookToastKey({ hookError: "changed" }), "frHookFailed");
  assert.equal(unhookToastKey({ hook: { state: "missing" } }), "frHookDisconnected");
  assert.equal(unhookToastKey({}), "frHookDisconnected");
});
