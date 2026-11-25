import assert from "node:assert/strict";
import test from "node:test";
import { EMPTY_LOC, classifyTask, formatLocation, hasPlace, parseLocation, sameLocation } from "../app/location-model.js";

const L = (o) => ({ ...EMPTY_LOC, ...o });

test("порожній hash → порожнє місце; hasPlace false", () => {
  for (const h of ["", "#", undefined, null]) {
    assert.deepEqual(parseLocation(h), EMPTY_LOC);
  }
  assert.equal(hasPlace(EMPTY_LOC), false);
  assert.equal(formatLocation(EMPTY_LOC), "");
});

test("туди й назад: усі ключі в канонічному порядку", () => {
  const loc = L({ sp: "studio", t: "fb-01102026-7f7b6d", it: "it2", p: "holovna", st: "open", m: "o", v: "flow", h: "settings" });
  const hash = formatLocation(loc);
  assert.equal(hash, "#sp=studio&t=fb-01102026-7f7b6d&it=it2&p=holovna&st=open&m=o&v=flow&h=settings");
  assert.deepEqual(parseLocation(hash), loc);
});

test("кодування: id з `--`, пробілами, кирилицею, `&`, `=`, `#`", () => {
  const loc = L({ t: "my--task one", p: "Головна & Пошук=1#x", it: "it1" });
  const hash = formatLocation(loc);
  assert.ok(!hash.slice(1).includes(" "), "пробіл закодовано");
  assert.equal(hash.split("&").length, 3, "`&` у значенні не створив зайвого ключа");
  assert.deepEqual(parseLocation(hash), loc);
});

test("невідомі ключі, порожні значення й сміття ігноруються; останній дубль перемагає", () => {
  const loc = parseLocation("#zzz=1&t=a&=b&it=&p=x&p=y&k=gate");
  assert.deepEqual(loc, L({ t: "a", p: "y" }));
});

test("зіпсований відсоток не кидає: значення лишається як є (як у ext-shell)", () => {
  assert.equal(parseLocation("#p=%E0%A4%A").p, "%E0%A4%A");
});

test("m і v: лише відомі значення; v=flow без m=o не пишеться; st без p не пишеться", () => {
  assert.equal(parseLocation("#m=x&v=y&h=z").m, null);
  assert.equal(parseLocation("#m=x&v=y&h=z").v, null);
  assert.equal(parseLocation("#m=x&v=y&h=z").h, null);
  assert.equal(formatLocation(L({ t: "a", v: "flow" })), "#t=a");
  assert.equal(formatLocation(L({ t: "a", st: "s1" })), "#t=a");
  assert.equal(formatLocation(L({ t: "a", m: "o" })), "#t=a&m=o");
});

test("sameLocation: порівнює канонічно, а не за порядком ключів у рядку", () => {
  assert.equal(sameLocation(parseLocation("#p=a&t=b"), parseLocation("#t=b&p=a")), true);
  assert.equal(sameLocation(L({ t: "a" }), L({ t: "b" })), false);
  assert.equal(sameLocation(L({ t: "a", v: "flow" }), L({ t: "a" })), true, "v без m=o не значущий");
});

test("classifyTask: поточна/без задачі → current; одна жива → switch; нема, missing чи двозначна → unknown; збій запиту → error, не unknown", () => {
  const rows = [{ id: "a" }, { id: "gone", missing: true }, { id: "dup", space: "s1" }, { id: "dup", space: "s2" }];
  assert.equal(classifyTask(L({}), "cur", rows), "current");
  assert.equal(classifyTask(L({ t: "cur" }), "cur", null), "current", "поточна не потребує запиту");
  assert.equal(classifyTask(L({ t: "a" }), "cur", rows), "switch");
  assert.equal(classifyTask(L({ t: "nope" }), "cur", rows), "unknown");
  assert.equal(classifyTask(L({ t: "gone" }), "cur", rows), "unknown");
  assert.equal(classifyTask(L({ t: "dup", sp: "s1" }), "cur", rows), "unknown", "двозначний id: sp його не розвʼязує");
  assert.equal(classifyTask(L({ t: "a" }), "cur", null), "error", "збій запиту — не «нема»");
});

test("`p=` сумісний із превʼю: той самий ключ і той самий регексп читають однаково", () => {
  const h = formatLocation(L({ t: "a", p: "holovna" }));
  assert.match(h, /(?:^#|&)p=holovna(?:&|$)/);
});
