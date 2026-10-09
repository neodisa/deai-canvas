import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { manifestPath, markStale, readManifest, staleIds, writeManifest } from "../bin/shots-manifest.mjs";

const NOW = "24.08.2026 12:00";
const iter = () => mkdtempSync(path.join(tmpdir(), "dc-man-"));

test("манифеста немає — читається порожній, а не падає", () => {
  const m = readManifest(iter());
  assert.deepEqual(m.shots, {});
  assert.equal(m.checkedAt, null);
  assert.ok(m.contract.length > 40);
});

test("запис і читання ходять по колу", () => {
  const dir = iter();
  writeManifest(dir, { checkedAt: NOW, shots: { a: { stamp: "s1", w: 1280, h: 900 } } });
  assert.ok(existsSync(path.join(dir, "shots", "manifest.json")));
  assert.equal(readManifest(dir).shots.a.stamp, "s1");
});

test("застарілі — це немає знімка, немає штампа, або штамп розійшовся", () => {
  const manifest = { shots: { fresh: { stamp: "s1" }, old: { stamp: "s0" }, nostamp: {} } };
  const stamps = { fresh: "s1", old: "s1", nostamp: "s1", newpage: "s1" };
  assert.deepEqual(staleIds(manifest, stamps).sort(), ["newpage", "nostamp", "old"]);
});

test("markStale ставить прапорець і час, а зниклу сторінку викидає", () => {
  const manifest = { shots: { keep: { stamp: "s1" }, gone: { stamp: "s9" } } };
  const next = markStale(manifest, { keep: "s2" }, NOW);
  assert.equal(next.checkedAt, NOW);
  assert.equal(next.shots.keep.stale, true);
  assert.equal("gone" in next.shots, false);
});

test("свіжий знімок прапорця не отримує", () => {
  const next = markStale({ shots: { a: { stamp: "s1" } } }, { a: "s1" }, NOW);
  assert.equal(next.shots.a.stale, false);
});

test("кадр із проблемою застарілий за побудовою — інакше його ніхто не перезніме", () => {
  const manifest = { shots: {
    ok: { stamp: "s1" },
    broken: { stamp: "s1", problem: "знімок 812 байт — це порожня сторінка" },
  } };
  const stamps = { ok: "s1", broken: "s1" };
  assert.deepEqual(staleIds(manifest, stamps), ["broken"]);
});

test("markStale лишає problem на місці — причину не можна загубити при перезважуванні", () => {
  const manifest = { shots: { broken: { stamp: "s1", problem: "у кадрі дірки" } } };
  const out = markStale(manifest, { broken: "s1" }, NOW);
  assert.equal(out.shots.broken.problem, "у кадрі дірки");
  assert.equal(out.shots.broken.stale, true);
});

test("кожен запис бере ВЛАСНИЙ tmp і прибирає його за собою", () => {
  const dir = iter();
  const shots = path.join(dir, "shots");
  mkdirSync(shots, { recursive: true });
  // Тека на місці manifest.json валить renameSync. Імʼя tmp читаємо з `err.path`
  // самої помилки, а НЕ з того, що лишилось на диску: писар зобовʼязаний
  // прибирати за собою, тож канал спостереження не сміє залежати від сміття.
  // Спільний `manifest.json.tmp` дав би тут одне імʼя на два записи — у житті це
  // два прогони зʼємки, які обрізають кадр одне одного, і rename атомарно кладе
  // на місце вже зіпсоване.
  mkdirSync(manifestPath(dir));
  const tmps = [];
  for (let i = 0; i < 2; i++) {
    try {
      writeManifest(dir, { checkedAt: NOW, shots: { [`a${i}`]: { stamp: "s" } } });
      assert.fail("запис мусив упасти — на місці манифеста тека");
    } catch (e) {
      assert.equal(e.code, "EISDIR", `впало не там, де очікували: ${e.message}`);
      tmps.push(e.path);
    }
  }
  assert.equal(new Set(tmps).size, 2, `два записи мусять узяти ДВА різні tmp, а взяли: ${tmps}`);
  const left = readdirSync(shots).filter((f) => f.endsWith(".tmp"));
  assert.deepEqual(left, [], `невдалий запис лишив сміття, яке поїде колегам: ${left}`);
});

test("вдалий запис прибирає свій tmp — унікальні імена не сміють накопичуватись", () => {
  const dir = iter();
  writeManifest(dir, { checkedAt: NOW, shots: { a: { stamp: "s1" } } });
  writeManifest(dir, { checkedAt: NOW, shots: { a: { stamp: "s2" } } });
  const tmps = readdirSync(path.join(dir, "shots")).filter((f) => f.endsWith(".tmp"));
  assert.deepEqual(tmps, [], `tmp лишились на диску: ${tmps}`);
  assert.equal(readManifest(dir).shots.a.stamp, "s2");
});
