import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";
import { freePort } from "./live/_port.mjs";

/**
 * Порт живого сервера — ВІЛЬНИЙ порт зі смуги `portBase…portBase+99`.
 *
 * ⛔ Навіщо. Раніше `startServer` брав `portBase + hrtime % 100`. На Apple Silicon годинник тікає кроком ~41.7 нс, тож `hrtime % 100` дає лише
 * 12 різних значень: другий сервер того ж файла (поки перший ще живий) приблизно раз на 12 стартів сідав на його порт, не міг забіндитись, а
 * проба готовності відповідала від ЧУЖОГО сервера. Так плавав `live-liga-migrate` #5/#6 у релізному прогоні 0.24.0: «немігрована ЛІГА» показувала
 * `publish: vercel-publish` мігрованого сервера з тестів 1–4.
 */
const BAND = 47300; // поза смугами живих тестів і поза ефемерними портами macOS (49152+)

function listen(port) {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.once("error", reject);
    s.listen(port, "127.0.0.1", () => resolve(s));
  });
}

async function occupy(ports) {
  const out = [];
  for (const p of ports) out.push(await listen(p));
  return out;
}

const closeAll = (servers) => Promise.all(servers.map((s) => new Promise((r) => s.close(r))));

test("зайняті порти смуги оминаються: з 99 зайнятих повертається єдиний вільний", async () => {
  const free = BAND + 37;
  const busy = await occupy(Array.from({ length: 100 }, (_, i) => BAND + i).filter((p) => p !== free));
  try {
    for (let i = 0; i < 5; i += 1) assert.equal(await freePort(BAND), free);
  } finally {
    await closeAll(busy);
  }
});

test("уся смуга зайнята — чесна помилка, а не зайнятий порт", async () => {
  const busy = await occupy(Array.from({ length: 100 }, (_, i) => BAND + i));
  try {
    await assert.rejects(() => freePort(BAND), /вільного порту/);
  } finally {
    await closeAll(busy);
  }
});

test("порти розкидані по всій смузі, а не по 12 значеннях годинника", async () => {
  const seen = new Set();
  for (let i = 0; i < 200; i += 1) {
    const p = await freePort(BAND);
    assert.ok(p >= BAND && p < BAND + 100, `поза смугою: ${p}`);
    seen.add(p);
  }
  assert.ok(seen.size >= 50, `лише ${seen.size} різних портів із 200 спроб`);
});
