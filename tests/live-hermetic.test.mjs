import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

/* Охоронець герметичності живих тестів ЛІГИ. Від 0.27.0 робоче місце простору ЛІГА завжди читає командне сховище, тож живий тест
   із `supabase: true`, що відкриває сторінку без `hermeticLiga(…)`, ходить на справжній публічний `*.supabase.co`. Файл із
   `supabase: true` мусить викликати `hermeticLiga(` (і стверджувати порожній `outside`). Винятків немає: список нижче порожній навмисно,
   а кожен виняток — один рядок із причиною. */
const LIVE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "live");
const ALLOW = new Map(/** @type {[string, string][]} */ ([]));

test("кожен живий тест із `supabase: true` викликає hermeticLiga(", () => {
  const files = readdirSync(LIVE).filter((n) => n.endsWith(".test.mjs"));
  assert.ok(files.length > 10, "живі тести не знайдено — шлях до tests/live зламано");
  const bad = files.filter((n) => !ALLOW.has(n)
    && /supabase:\s*true/.test(readFileSync(path.join(LIVE, n), "utf8"))
    && !/hermeticLiga\(/.test(readFileSync(path.join(LIVE, n), "utf8")));
  assert.deepEqual(bad, [], `живі тести з supabase: true без hermeticLiga(: ${bad.join(", ")}`);
});
