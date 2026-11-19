import assert from "node:assert/strict";
import test from "node:test";
import { SECTIONS, SEC_KEY, navItems, readSec, trustWaitingOf } from "../app/settings-model.js";

test("SECTIONS і SEC_KEY — як у спеці", () => {
  assert.deepEqual(SECTIONS, ["space", "mods", "agents", "app", "upd", "keys"]);
  assert.equal(SEC_KEY, "deai.settingsSec");
});

test("readSec: відомий розділ — як є, усе інше — mods", () => {
  for (const s of SECTIONS) assert.equal(readSec(s), s);
  for (const bad of [null, undefined, "", "nope", 3, {}, "MODS", "__proto__"]) assert.equal(readSec(bad), "mods");
});

test("navItems: порядок, групи, іконки, ключі підписів", () => {
  const it = navItems();
  assert.deepEqual(it.map((x) => x.id), ["space", "mods", "agents", "app", "upd", "keys"]);
  assert.deepEqual(it.map((x) => x.group), ["space", "space", "space", "app", "app", "app"]);
  assert.deepEqual(it.map((x) => x.icon), ["palette", "puzzle", "doc", "desktop", "refresh", "keyboard"]);
  assert.deepEqual(it.map((x) => x.labelKey),
    ["setSecSpace", "setSecMods", "setSecAgents", "setSecApp", "setSecUpd", "setSecKeys"]);
  assert.ok(it.every((x) => x.badge === undefined), "без аргументів бейджів нема");
});

test("navItems: бейдж-лічильник на «Модулі», крапка на «AGENTS.md»", () => {
  const it = navItems({ trustWaiting: 3, agentsOutdated: true });
  assert.deepEqual(it.find((x) => x.id === "mods").badge, { kind: "count", n: 3 });
  assert.deepEqual(it.find((x) => x.id === "agents").badge, { kind: "dot" });
  assert.deepEqual(it.filter((x) => x.badge).map((x) => x.id), ["mods", "agents"]);
  assert.equal(navItems({ trustWaiting: 0 }).find((x) => x.id === "mods").badge, undefined);
  assert.equal(navItems({ agentsOutdated: false }).find((x) => x.id === "agents").badge, undefined);
});

test("trustWaitingOf: лише свої модулі, що чекають довіри", () => {
  const own = (o) => ({ custom: true, runs: false, trust: "untrusted", ...o });
  assert.equal(trustWaitingOf(null), 0);
  assert.equal(trustWaitingOf([]), 0);
  assert.equal(trustWaitingOf([own({}), own({ trust: "trusted", runs: true }), { id: "b" }, own({ trust: "refused" })]), 1);
  assert.equal(trustWaitingOf([own({ trust: "changed", runs: true })]), 1, "змінений код теж чекає");
  assert.equal(trustWaitingOf([{ id: "b", trust: "changed" }]), 0, "вбудований модуль не «чекає довіри»");
});
