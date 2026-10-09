/**
 * Геометрія кадру (T-45): які кадри треба перезняти, бо в них немає
 * прямокутників елементів для пінів «Огляду».
 *
 * Мапа «перевірка → запобіжник» (мутаційно):
 *   «без геометрії → перезйомка»  — `!s.geo`. Мутація «прибрати» червонить A.
 *   «стара версія → перезйомка»   — `s.geo.v !== GEO_VERSION`. Мутація червонить A.
 *   «geoProblem не зациклює»      — `!s.geoProblem`. Мутація червонить A.
 *   «немає кадру — не наша справа» — `Boolean(s)`. Мутація червонить B.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { GEO_VERSION, geoMissingIds } from "../bin/shots-geo.mjs";

test("A: кадр без геометрії чи зі старою — у перезйомку; з поточною чи з geoProblem — ні", () => {
  const m = { shots: {
    a: { stamp: "s" },
    b: { stamp: "s", geo: { v: GEO_VERSION, n: 3 } },
    c: { stamp: "s", geo: { v: GEO_VERSION - 1, n: 3 } },
    // пробували на цьому штампі — і не вийшло; без цього кадр перезнімався б
    // на кожному вході в «Огляд» вічно
    d: { stamp: "s", geoProblem: "впала" },
  } };
  assert.deepEqual(geoMissingIds(m, ["a", "b", "c", "d", "e"]).sort(), ["a", "c"]);
});

test("B: кадру немає взагалі — це звичайна перезйомка (`staleIds`), не «без геометрії»", () => {
  assert.deepEqual(geoMissingIds({ shots: {} }, ["x"]), []);
  assert.deepEqual(geoMissingIds({}, ["x"]), []);
});
