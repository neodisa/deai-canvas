import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { applyLiveEnv, playwrightCache } from "./live/_env.mjs";

test("кеш Playwright береться з дому ОС, а не з $HOME", () => {
  const osHome = mkdtempSync(path.join(tmpdir(), "osh-"));
  assert.equal(playwrightCache(osHome, "darwin"), null, "нема кешу — null");
  mkdirSync(path.join(osHome, "Library", "Caches", "ms-playwright"), { recursive: true });
  assert.equal(playwrightCache(osHome, "darwin"), path.join(osHome, "Library", "Caches", "ms-playwright"));
  mkdirSync(path.join(osHome, ".cache", "ms-playwright"), { recursive: true });
  assert.equal(playwrightCache(osHome, "linux"), path.join(osHome, ".cache", "ms-playwright"));
  assert.equal(playwrightCache(null), null);
});

test("тимчасовий HOME без .gitconfig отримує вигадану ідентичність і кеш; задане не перекривається", () => {
  const osHome = mkdtempSync(path.join(tmpdir(), "osh-"));
  for (const sub of [[".cache", "ms-playwright"], ["Library", "Caches", "ms-playwright"], ["AppData", "Local", "ms-playwright"]]) {
    mkdirSync(path.join(osHome, ...sub), { recursive: true });       // той, що відповідає платформі прогону, знайдеться
  }
  const env = { HOME: mkdtempSync(path.join(tmpdir(), "h-")) };
  applyLiveEnv(env, osHome);
  assert.equal(env.PLAYWRIGHT_BROWSERS_PATH, playwrightCache(osHome));
  assert.match(readFileSync(env.GIT_CONFIG_GLOBAL, "utf8"), /live@example\.invalid/);
  const mine = { HOME: env.HOME, PLAYWRIGHT_BROWSERS_PATH: "/x", GIT_CONFIG_GLOBAL: "/y" };
  applyLiveEnv(mine, osHome);
  assert.deepEqual([mine.PLAYWRIGHT_BROWSERS_PATH, mine.GIT_CONFIG_GLOBAL], ["/x", "/y"]);
  const withCfg = { HOME: mkdtempSync(path.join(tmpdir(), "h-")) };
  writeFileSync(path.join(withCfg.HOME, ".gitconfig"), "[user]\n\tname = A\n");
  applyLiveEnv(withCfg, null);
  assert.equal(withCfg.GIT_CONFIG_GLOBAL, undefined, "наявний .gitconfig у HOME не підміняємо");
});

test("імпорт у дочірньому процесі з тимчасовим HOME виставляє обидві змінні", () => {
  const home = mkdtempSync(path.join(tmpdir(), "h-"));
  const r = spawnSync(process.execPath, ["-e", `import("${path.resolve("tests/live/_env.mjs")}").then(()=>console.log(JSON.stringify({g:process.env.GIT_CONFIG_GLOBAL||null})))`],
    { env: { PATH: process.env.PATH, HOME: home }, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  assert.match(JSON.parse(r.stdout).g, /gitconfig$/);
});
