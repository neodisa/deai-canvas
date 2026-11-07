/**
 * Відтворюваність живих тестів у ТИМЧАСОВОМУ `HOME` (4d-4b): правило «кожен прогін — з тимчасовим HOME» ламало два місця, не пов'язані з кодом:
 *  · Playwright шукає браузери в кеші справжнього дому → без `PLAYWRIGHT_BROWSERS_PATH` запуск падає «Executable doesn't exist»;
 *  · `git commit` у фікстурах без ідентичності (нема `~/.gitconfig`) падає «Please tell me who you are».
 * Імпорт цього файла виправляє обидва: ПЕРШИМ — через `node --import ./tests/live/_env.mjs` (скрипт `test:live` і команда одного файла), бо
 * `playwright` читає кеш при ІМПОРТІ, а файли тестів імпортують його раніше за фікстуру; запасний — перший рядок у `fixture.mjs` та сусідів. кеш — за паролем ОС (`os.userInfo().homedir`, а НЕ `$HOME`),
 * ідентичність — окремий тимчасовий `.gitconfig` з вигаданим автором. Нічого, що вже задано, не перекриває; справжній `~/.gitconfig` не читає й не пише.
 * Кеш браузерів лише ЧИТАЄТЬСЯ (шлях до нього); у справжній дім цей файл нічого не пише.
 */
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

export function playwrightCache(osHome, platform = process.platform) {
  if (!osHome) return null;
  const sub = platform === "darwin" ? ["Library", "Caches", "ms-playwright"]
    : platform === "win32" ? ["AppData", "Local", "ms-playwright"] : [".cache", "ms-playwright"];
  const p = path.join(osHome, ...sub);
  return existsSync(p) ? p : null;
}

export function applyLiveEnv(env = process.env, osHome = (() => { try { return os.userInfo().homedir; } catch { return null; } })()) {
  if (!env.PLAYWRIGHT_BROWSERS_PATH) {
    const cache = playwrightCache(osHome);
    if (cache) env.PLAYWRIGHT_BROWSERS_PATH = cache;
  }
  const hasGlobal = env.GIT_CONFIG_GLOBAL || (env.HOME && existsSync(path.join(env.HOME, ".gitconfig")));
  if (!hasGlobal) {
    // ОДНЕ детерміноване місце (а не нова тека на кожен процес — вони б лишались у tmp): вміст сталий, тож гонка двох процесів нешкідлива
    const dir = path.join(os.tmpdir(), "live-gitcfg");
    const file = path.join(dir, "gitconfig");
    const body = "[user]\n\tname = Live\n\temail = live@example.invalid\n";
    let same = false;
    try { same = readFileSync(file, "utf8") === body; } catch { /* нема — створимо */ }
    if (!same) {
      mkdirSync(dir, { recursive: true });
      const part = `${file}.${process.pid}`;
      writeFileSync(part, body);
      renameSync(part, file);                    // атомарно: читач не побачить половину
    }
    env.GIT_CONFIG_GLOBAL = file;
  }
  return env;
}

applyLiveEnv();
