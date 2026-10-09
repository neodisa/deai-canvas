import assert from "node:assert/strict";
import test from "node:test";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const LIVE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "live");

/**
 * Жоден порт живих тестів не сміє збігтися з чужим.
 *
 * ⛔ Навіщо. `node --test` крутить файли ПАРАЛЕЛЬНО, а `startServer`
 * (`tests/live/fixture.mjs`) бере `portBase + hrtime % 100`, тобто кожна база
 * володіє смугою у 100 портів. Два файли з однією базою рано чи пізно
 * піднімають сервер на одному порту — і падає той, кому не пощастило, на
 * перевірці, яка до портів стосунку не має. Саме так і виглядала решта
 * «червоної бази» після TD-13: `shell-bar` і `shell-palette` падали в
 * повному прогоні й зеленіли поодинці.
 *
 * Номери досі обирали очима по сусідньому файлу — і тричі взяли зайнятий
 * (9590, 9690, 9790 стояли по двічі кожен). Око тут не працює, бо бази
 * розкидані по 23 файлах, а дві з них ще й не звуться `PORT_BASE`.
 */
const RE = /const\s+([A-Z_]*PORT_BASE)\s*=\s*(\d+)\s*;/g;

function bases() {
  const out = [];
  for (const f of readdirSync(LIVE).filter((x) => x.endsWith(".test.mjs"))) {
    const src = readFileSync(path.join(LIVE, f), "utf8");
    for (const m of src.matchAll(RE)) out.push({ file: f, name: m[1], port: Number(m[2]) });
  }
  return out;
}

test("бази портів живих тестів не перетинаються", () => {
  const all = bases();
  // Свідок: зламаний регексп знайшов би нуль баз і тест зеленів би на порожнечі.
  assert.ok(all.length >= 20,
    `знайдено лише ${all.length} баз портів — регексп перестав їх бачити`);

  const seen = new Map();
  const clash = [];
  for (const b of all) {
    const prev = seen.get(b.port);
    if (prev) clash.push(`${b.port}: ${prev.file}:${prev.name} і ${b.file}:${b.name}`);
    else seen.set(b.port, b);
  }
  assert.deepEqual(clash, [], `бази портів збігаються:\n${clash.join("\n")}`);
});

test("сусідні бази рознесені щонайменше на смугу в 100 портів", () => {
  /* `startServer` бере `portBase + hrtime % 100`, тож база володіє рівно
     сотнею. Крок менший за 100 означає, що верх однієї смуги залазить у низ
     наступної — рідший, але той самий збіг. */
  const ports = [...new Set(bases().map((b) => b.port))].sort((a, b) => a - b);
  const tight = [];
  for (let i = 1; i < ports.length; i++) {
    if (ports[i] - ports[i - 1] < 100) tight.push(`${ports[i - 1]} → ${ports[i]}`);
  }
  assert.deepEqual(tight, [], `смуги налазять одна на одну: ${tight.join(", ")}`);
});
