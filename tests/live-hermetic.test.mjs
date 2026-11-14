import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

/* Охоронець герметичності живих тестів ЛІГИ. Від 0.27.0 робоче місце простору ЛІГА завжди читає командне сховище, тож живий тест,
   що будує ЛІГУ з Supabase-ролею й відкриває сторінку без `hermeticLiga(…)`, ходить на справжній публічний `*.supabase.co`.
   Ознаки такого файла (будь-яка): `supabase: true`; id модуля `supabase-comments`; вигаданий хост/ключ (`abcdefghijkl`, `LIGA_SB`,
   `LIGA_SUPABASE_ORIGINALS`); простір із `roles: […"comments"…]` (мігрована ЛІГА з командним каналом). Такий файл мусить
   викликати `hermeticLiga(` (і стверджувати порожній `outside`). Винятків немає: список нижче порожній навмисно,
   а кожен виняток — один рядок із причиною. */
const LIVE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "live");
const ALLOW = new Map(/** @type {[string, string][]} */ ([]));
const SUPABASE_COMMENTS = /supabase:\s*true|supabase-comments|abcdefghijkl|\bLIGA_SB\b|LIGA_SB_HOST|LIGA_SUPABASE_ORIGINALS|roles:[^\n]*["']comments["']/;

test("кожен живий тест із Supabase-каналом коментарів ЛІГИ викликає hermeticLiga(", () => {
  const files = readdirSync(LIVE).filter((n) => n.endsWith(".test.mjs"));
  assert.ok(files.length > 10, "живі тести не знайдено — шлях до tests/live зламано");
  const bad = files.filter((n) => !ALLOW.has(n)
    && SUPABASE_COMMENTS.test(readFileSync(path.join(LIVE, n), "utf8"))
    && !/hermeticLiga\(/.test(readFileSync(path.join(LIVE, n), "utf8")));
  assert.deepEqual(bad, [], `живі тести з Supabase-каналом ЛІГИ без hermeticLiga(: ${bad.join(", ")}`);
});
