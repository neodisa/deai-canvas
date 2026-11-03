import assert from "node:assert/strict";
import { appendFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { appendGuard } from "./live/_append-guard.mjs";

/* Охоронець чужого логу (`tests/live/_append-guard.mjs`): доводимо його на ТИМЧАСОВОМУ файлі, а не на справжньому логу машини. */
function tmpLog(t, initial) {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-guard-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "overview-sync.log");
  if (initial !== null) writeFileSync(file, initial);
  return file;
}

test("чужий рядок — не провал; наша мітка — провал, і повідомлення не друкує вміст логу", (t) => {
  const file = tmpLog(t, "старий рядок\n");
  const check = appendGuard(file, ["dc-live-home-", "DEMO-"]);
  check();                                              // нічого не дописано
  appendFileSync(file, "чужий процес: синхронізовано 7 проєктів\n");
  check();                                              // чужий хвіст без наших міток
  appendFileSync(file, "SECRET-LINE /var/folders/x/dc-live-home-abc/y\n");
  assert.throws(check, (e) => /мітка «dc-live-home-»/.test(e.message) && !/SECRET-LINE/.test(e.message) && !/var\/folders/.test(e.message));
});

test("мітка, що була ДО знімка, не рахується: читається лише дописаний хвіст", (t) => {
  const file = tmpLog(t, "стара згадка DEMO-1\n");
  const check = appendGuard(file, ["DEMO-"]);
  appendFileSync(file, "чужий рядок\n");
  check();
});

test("обрізання чи зникнення файла (ротація ззовні) — не провал", (t) => {
  const file = tmpLog(t, "x".repeat(100));
  const check = appendGuard(file, ["DEMO-"]);
  writeFileSync(file, "DEMO-1");                         // менший за знятий розмір: це вже не наш хвіст
  check();
  rmSync(file);
  check();
});

test("файла не було: нема й далі — ок; зʼявився — провал", (t) => {
  const file = tmpLog(t, null);
  const check = appendGuard(file, ["DEMO-"]);
  check();
  writeFileSync(file, "чужий рядок\n");
  assert.throws(check, /зʼявився/);
});

test("хвіст читається з обмеженням `cap`", (t) => {
  const file = tmpLog(t, "");
  const check = appendGuard(file, ["DEMO-"], { cap: 10 });
  appendFileSync(file, `${"a".repeat(50)}DEMO-1`);        // мітка за межею `cap` — не бачимо (навмисне обмеження)
  check();
});
