/**
 * Спільне для живих тестів просторів (`spaces.test.mjs`, `spaces-flows.test.mjs`).
 *
 * Файл НЕ `*.test.mjs` навмисно: `npm run test:live` бере `tests/live/*.test.mjs`, і helper
 * під таким іменем поїхав би в прогін окремим файлом без жодного тесту (так само `fixture.mjs`).
 *
 * Що тут: зупинка сервера, кілька чекань, JSON-POST, і ОХОРОНЕЦЬ справжнього `~/.deai`.
 * Охоронець — знімок справжнього реєстру ДО будь-якого сервера (модуль імпортується першим
 * рядком тестового файла), а порівняння — окремим останнім тестом кожного модуля
 * (`guardRealDeai`). Домівка — з ОС (`os.userInfo().homedir`), а не з `process.env.HOME`: її
 * може підмінити хто завгодно, і тоді охоронець дивився б не туди. Статичний охоронець
 * `.mjs` не сканує (ревʼю Task 5), тож цей — єдиний, що бачить живий прогін.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { userInfo } from "node:os";
import path from "node:path";
import test from "node:test";

export const VIEW = { width: 1440, height: 900 };

/** Зупинити сервер і дочекатись виходу: наступний тест може випасти на той самий порт. */
export async function stop(child) {
  if (child.exitCode !== null || child.signalCode) return;
  const gone = new Promise((done) => child.once("exit", done));
  child.kill();
  const timer = setTimeout(() => child.kill("SIGKILL"), 4000);
  await gone;
  clearTimeout(timer);
}

export const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

/** Текст першого збігу, обрізаний; `null`, коли вузла нема. */
export const text = (page, sel) => page.evaluate((s) => document.querySelector(s)?.textContent.trim() ?? null, sel);

/** Дочекатись, поки текст першого збігу дорівнює `want`. */
export const waitText = (page, sel, want) => page.waitForFunction(
  ([s, w]) => document.querySelector(s)?.textContent.trim() === w, [sel, want], { timeout: 15000 });

/** `POST` JSON на сервер напряму (як це робить агент), без сторінки. */
export const postJson = (url, p, body) => fetch(`${url}${p}`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const spacesApi = async (url) => (await fetch(`${url}/api/spaces`)).json();

/* ── охоронець справжнього ~/.deai ─────────────────────────────────────── */

export const REAL_DEAI = path.join(userInfo().homedir, ".deai");
const sha = (p) => {
  try { return createHash("sha256").update(readFileSync(p)).digest("hex"); } catch { return null; }
};
export const realDeai = () => ({
  exists: existsSync(REAL_DEAI),
  registry: sha(path.join(REAL_DEAI, "spaces.json")),
  backup: sha(path.join(REAL_DEAI, "spaces.json.bak")),
});
/** Знімок ДО будь-якого сервера: модуль імпортується до першого `startServer`. */
export const REAL_BEFORE = realDeai();

/** Останній тест модуля: справжній `~/.deai` не зʼявився і не змінився. */
export function guardRealDeai(name = "справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)") {
  test(name, () => {
    assert.deepEqual(realDeai(), REAL_BEFORE, `живий тест торкнувся справжнього ${REAL_DEAI}`);
  });
}
