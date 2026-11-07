import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { applyLiveEnv, playwrightCache } from "./live/_env.mjs";

const ENV_URL = new URL("./live/_env.mjs", import.meta.url).href;     // не залежить від cwd
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("test:live підключає _env.mjs через --import (playwright читає кеш при імпорті, раніше за фікстуру)", () => {
  const script = JSON.parse(readFileSync(path.join(ROOT, "package.json"), "utf8")).scripts["test:live"];
  assert.match(script, /--import \.\/tests\/live\/_env\.mjs\b/);
});

test("ідентичність git — одне детерміноване місце: повторні виклики не плодять тек", () => {
  const a = { HOME: mkdtempSync(path.join(tmpdir(), "h-")) };
  const b = { HOME: mkdtempSync(path.join(tmpdir(), "h-")) };
  applyLiveEnv(a, null);
  applyLiveEnv(b, null);
  assert.equal(a.GIT_CONFIG_GLOBAL, b.GIT_CONFIG_GLOBAL);
  assert.match(readFileSync(a.GIT_CONFIG_GLOBAL, "utf8"), /live@example\.invalid/);
});

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
  const r = spawnSync(process.execPath, ["-e", `import(${JSON.stringify(ENV_URL)}).then(()=>console.log(JSON.stringify({g:process.env.GIT_CONFIG_GLOBAL||null})))`],
    { env: { PATH: process.env.PATH, HOME: home }, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  assert.match(JSON.parse(r.stdout).g, /gitconfig$/);
});
