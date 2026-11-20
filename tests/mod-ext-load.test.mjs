/* `loadModExt` (app.js): збій не стирає список і не закриває панель; закриває лише успішна відповідь без інструмента. */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { modToolKey } from "../app/module-host.js";

const SRC = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");
const start = SRC.indexOf("async function loadModExt()");
const body = SRC.slice(start, SRC.indexOf("\n}\n", start) + 3);

function mk(over = {}) {
  const log = { closed: 0, paint: 0, bar: 0 };
  const env = {
    log, modToolKey, modExtKey: "", modExtSeq: 0,
    modExt: { spaceId: "s", tools: [{ module: "m", id: "t" }], actions: [] },
    modOpen: { key: "m/t" }, space: "s", reply: null,
    spaceNow: () => ({ id: env.space }),
    api: async () => { if (env.reply instanceof Error) throw env.reply; return env.reply; },
    closeModTool: () => { log.closed += 1; env.modOpen = null; },
    paintIsland: () => { log.paint += 1; },
    paintBar: () => { log.bar += 1; },
    modExtNow: () => (env.modExt.spaceId === (env.spaceNow()?.id ?? null) ? env.modExt : { tools: [], actions: [] }),
    ...over,
  };
  // eslint-disable-next-line no-new-func
  env.run = new Function("env", `with (env) { ${body}\nreturn loadModExt; }`)(env);
  return env;
}

test("збій: список того ж простору лишається, панель не закривається, ключ скинуто для повтору", async () => {
  const e = mk({ reply: new Error("net") });
  await e.run();
  assert.equal(e.modExt.tools.length, 1);
  assert.equal(e.log.closed, 0);
  assert.equal(e.modExtKey, "");
});

test("збій для ІНШОГО простору: старий список не показується", async () => {
  const e = mk({ reply: new Error("net"), space: "other" });
  await e.run();
  assert.deepEqual(e.modExt, { spaceId: "other", tools: [], actions: [] });
});

test("успішна відповідь без відкритого інструмента закриває панель; з ним — ні", async () => {
  const e = mk({ reply: { tools: [], actions: [] } });
  await e.run();
  assert.equal(e.log.closed, 1);
  const f = mk({ reply: { tools: [{ module: "m", id: "t" }], actions: [] } });
  await f.run();
  assert.equal(f.log.closed, 0);
  assert.equal(f.modExtKey, "s");
});

test("змінений список → paintBar (смуга з дропдауном ітерації); той самий — лише острівець", async () => {
  const act = { module: "m", id: "a", label: "A", where: ["iteration"] };
  const e = mk({ reply: { tools: [{ module: "m", id: "t" }], actions: [act] } });
  await e.run();
  assert.deepEqual([e.log.bar, e.log.paint], [1, 0]);
  const same = mk({ reply: { tools: [{ module: "m", id: "t" }], actions: [] } });
  await same.run();
  assert.deepEqual([same.log.bar, same.log.paint], [0, 1]);
});
