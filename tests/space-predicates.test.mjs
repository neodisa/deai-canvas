import test from "node:test";
import assert from "node:assert/strict";
import { hasNotify, hasPublish, hasTeamComments, hasVcs, isLegacyPublish, isLegacyVcs, taskCreateClones } from "../app/spaces-model.js";
import { LIGA_SPACE, plainSpace } from "./_space-fixtures.mjs";

test("роль без запису: плоский простір нічого не має", () => {
  const s = plainSpace();
  for (const f of [hasPublish, hasVcs, hasNotify, hasTeamComments]) assert.equal(f(s), false, f.name);
  assert.equal(isLegacyVcs(s), false);
  assert.equal(isLegacyPublish(s), false);
});

test("ЛІГА — це compat, а не значення 'legacy' і не прапорець", () => {
  assert.equal(isLegacyVcs(LIGA_SPACE), true);
  assert.equal(isLegacyPublish(LIGA_SPACE), true);
  for (const f of [hasPublish, hasVcs, hasNotify, hasTeamComments]) assert.equal(f(LIGA_SPACE), true, f.name);
  /* значення 'legacy' сервер не шле, і клієнт його не знає */
  assert.equal(isLegacyVcs({ capabilities: { vcs: "legacy" } }), false);
  assert.equal(isLegacyPublish({ capabilities: { publish: "legacy" } }), false);
});

test("невідомий простір (null, стара форма без capabilities) — як було: нічого не відбираємо", () => {
  for (const s of [null, undefined, { id: "x" }]) {
    for (const f of [hasPublish, hasVcs, hasNotify, hasTeamComments, isLegacyVcs, isLegacyPublish]) assert.equal(f(s), true, `${f.name} ${JSON.stringify(s)}`);
  }
});

test("taskCreateClones: клон — коли в тілі є vcs або простір зі схемою ЛІГИ й роллю vcs", () => {
  assert.equal(taskCreateClones(plainSpace({ vcs: "git-sync" }), {}), false);
  assert.equal(taskCreateClones(plainSpace({ vcs: "git-sync" }), { vcs: { repo: "g/r" } }), true);
  assert.equal(taskCreateClones(LIGA_SPACE, {}), true);
  assert.equal(taskCreateClones(plainSpace(), {}), false);
  assert.equal(taskCreateClones(null, {}), true);
});
