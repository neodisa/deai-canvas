import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { DICT } from "../app/i18n.js";
import {
  copyUrl, hasPublish, isLegacyPublish, isPublished, isRemotePublish, localPublishUrl, previewTarget, publishErr,
  pwView, remoteNoticeLines, remoteShareUrl, safeLocalUrl, safeRemoteUrl,
} from "../app/spaces-model.js";

/* Публікація за `capabilities.publish` (модулі 2а, Task 8) — чисті правила, які приймає `app.js`:
   хто публікує простір, чи задача опублікована, куди веде «Відкрити превью»/«Скопіювати
   посилання», що з паролем ЛІГА в просторі, де публікує модуль, і який текст людина бачить
   замість коду відмови. `app.js` у Node не імпортується (DOM на верхньому рівні), тому проводку
   стереже `tests/spaces-wiring.test.mjs`, а тут — самі правила.

   `capabilities` приходить від сервера ТОТАЛЬНО: `{publish: '<id модуля>' | 'legacy' | null,
   tokens: …[, error]}`. Стара форма відповіді (без `capabilities`) лишається валідною: тоді
   рішення — за `integrations`, як було до модулів. */

const MOD = { id: "p", integrations: false, capabilities: { publish: "static-publish", tokens: null } };
const LEG = { id: "liga", integrations: true, capabilities: { publish: "legacy", tokens: null } };
const NONE = { id: "n", integrations: false, capabilities: { publish: null, tokens: null } };

/* ── хто публікує ──────────────────────────────────────────────────────── */

test("hasPublish: модуль — так, legacy — так, null — ні", () => {
  assert.equal(hasPublish(MOD), true);
  assert.equal(hasPublish(LEG), true);
  assert.equal(hasPublish(NONE), false);
});

test("hasPublish: стара форма (без capabilities) — за `integrations`, невідомість публікації не краде", () => {
  assert.equal(hasPublish({ integrations: false }), false, "старий простір без інтеграцій: публікації нема");
  assert.equal(hasPublish({ integrations: true }), true);
  assert.equal(hasPublish({}), true, "відповідь без відомостей не краде публікацію");
  assert.equal(hasPublish(null), true);
  assert.equal(hasPublish(undefined), true);
});

test("hasPublish: capabilities ВАЖЧІ за integrations (простір без інтеграцій може публікувати модулем)", () => {
  assert.equal(hasPublish({ integrations: false, capabilities: { publish: "static-publish" } }), true);
  assert.equal(hasPublish({ integrations: true, capabilities: { publish: null } }), false,
    "модуль публікації вимкнено — публікації нема, хоч би інтеграції й були");
});

test("hasPublish: capabilities із помилкою (space.json не читається) — публікації нема", () => {
  assert.equal(hasPublish({ integrations: false, capabilities: { publish: null, tokens: null, error: "space-json-unreadable" } }), false);
});

test("isLegacyPublish: лише 'legacy' (або стара форма з інтеграціями)", () => {
  assert.equal(isLegacyPublish(LEG), true);
  assert.equal(isLegacyPublish(MOD), false);
  assert.equal(isLegacyPublish(NONE), false);
  assert.equal(isLegacyPublish({ integrations: true }), true);
  assert.equal(isLegacyPublish({ integrations: false }), false);
  assert.equal(isLegacyPublish({}), true);
  assert.equal(isLegacyPublish(null), true);
  assert.equal(isLegacyPublish({ integrations: true, capabilities: { publish: "static-publish" } }), false,
    "модуль замість ЛІГА: пароль превʼю ЛІГА там нічого не значить");
});

/* ── чи опублікована задача ────────────────────────────────────────────── */

test("isPublished: publish_url АБО publish_local", () => {
  assert.equal(isPublished({ publish_url: "https://x.example/" }), true);
  assert.equal(isPublished({ publish_local: { module: "static-publish", path: "/a/b", published_at: "2026-10-16T10:00:00Z" } }), true);
  assert.equal(isPublished({}), false);
  assert.equal(isPublished({ publish_url: null }), false);
  assert.equal(isPublished({ publish_url: "" }), false);
  assert.equal(isPublished(null), false);
  assert.equal(isPublished({ publish_local: null }), false);
  assert.equal(isPublished({ publish_local: "рядок" }), false, "publish_local — обʼєкт, не будь-яка правда");
});

/* ── адреса локальної публікації ───────────────────────────────────────── */

test("localPublishUrl: /published/<простір>/<задача>/, кожен сегмент через encodeURIComponent", () => {
  assert.equal(localPublishUrl({ id: "p" }, { id: "blog" }), "/published/p/blog/");
  assert.equal(localPublishUrl({ id: "a b/c" }, { id: "t#1?x" }), "/published/a%20b%2Fc/t%231%3Fx/");
});

test("localPublishUrl: без id простору чи задачі — null (адреси не вигадуємо)", () => {
  assert.equal(localPublishUrl(null, { id: "t" }), null);
  assert.equal(localPublishUrl({ id: "" }, { id: "t" }), null);
  assert.equal(localPublishUrl({ id: "p" }, {}), null);
  assert.equal(localPublishUrl({ id: "p" }, null), null);
});

const LOCAL = { module: "static-publish", path: "/h/deai-published/p/blog", published_at: "2026-10-16T10:30:00Z" };

test("previewTarget: простір з модулем — локальна адреса канваса і час публікації", () => {
  const tg = previewTarget({ id: "blog", publish_local: LOCAL }, MOD);
  assert.equal(tg.kind, "local");
  assert.equal(tg.url, "/published/p/blog/");
  assert.equal(tg.at, Date.parse("2026-10-16T10:30:00Z"));
});

test("previewTarget: ЛІГА — зовнішній URL, час не вигадуємо", () => {
  const tg = previewTarget({ id: "blog", publish_url: "https://pv-1.example.app" }, LEG);
  assert.deepEqual(tg, { kind: "external", url: "https://pv-1.example.app", at: null });
});

test("previewTarget: обидва сліди — перемагає той, що відповідає постачальнику простору", () => {
  const task = { id: "blog", publish_url: "https://pv-1.example.app", publish_local: LOCAL };
  assert.equal(previewTarget(task, MOD).kind, "local");
  assert.equal(previewTarget(task, LEG).kind, "external");
});

test("previewTarget: простір із модулем, де є лише старий publish_url, — відкриваємо його (слід не губимо)", () => {
  assert.equal(previewTarget({ id: "blog", publish_url: "https://pv-1.example.app" }, MOD).kind, "external");
});

test("previewTarget: нічого не публікувалось — null; локальна без id простору — null", () => {
  assert.equal(previewTarget({ id: "blog" }, MOD), null);
  assert.equal(previewTarget(null, MOD), null);
  assert.equal(previewTarget({ id: "blog", publish_local: LOCAL }, null), null, "адреси без простору не буде");
});

test("previewTarget: непридатний час публікації — at: null, а не NaN", () => {
  assert.equal(previewTarget({ id: "blog", publish_local: { ...LOCAL, published_at: "вчора" } }, MOD).at, null);
  assert.equal(previewTarget({ id: "blog", publish_local: { module: "static-publish", path: "/x" } }, MOD).at, null);
});

/* ── посилання, яке копіюють ───────────────────────────────────────────── */

test("copyUrl: локальна — абсолютна адреса канваса БЕЗ #k= (пароль модуля — секрет, UI його не знає)", () => {
  const tg = { kind: "local", url: "/published/p/blog/", at: null };
  const url = copyUrl(tg, { origin: "http://localhost:8765", pageId: "it1/home", password: "1100" });
  assert.equal(url, "http://localhost:8765/published/p/blog/");
  assert.ok(!url.includes("#"), "у локальному посиланні нема фрагмента");
  assert.ok(!url.includes("k="), "пароль не в посиланні");
  assert.ok(!url.includes("1100"), "ЛІГА-пароль не просочується в локальне посилання");
});

test("copyUrl: зовнішня — як було: <url>/#k=<пароль>&p=<сторінка>, обидва закодовані", () => {
  const tg = { kind: "external", url: "https://pv-1.example.app///", at: null };
  assert.equal(copyUrl(tg, { pageId: "it4/page 2", password: "p&w" }),
    "https://pv-1.example.app/#k=p%26w&p=it4%2Fpage%202");
  assert.equal(copyUrl(tg, { pageId: "it4" }), "https://pv-1.example.app/#k=&p=it4");
});

test("copyUrl: без цілі — null", () => {
  assert.equal(copyUrl(null, { origin: "http://x" }), null);
});

/* ── довіряти відповіді сервера, куди відкривати ───────────────────────── */

const ORIGIN = "http://127.0.0.1:8765";

test("safeLocalUrl: лише відносний шлях /published/…", () => {
  assert.equal(safeLocalUrl("/published/p/blog/", ORIGIN), "/published/p/blog/");
  assert.equal(safeLocalUrl("/published/a%20b/t/", ORIGIN), "/published/a%20b/t/");
  assert.equal(safeLocalUrl("/published/p/blog/?x=1#y", ORIGIN), "/published/p/blog/?x=1#y");
  for (const bad of ["https://evil.example/", "//evil.example/published/", "/other/p/t/", "published/p/t/", "",
    null, undefined, 42, "/published/", "/published/\\evil", "/published/p t/", "javascript:alert(1)"]) {
    assert.equal(safeLocalUrl(bad, ORIGIN), null, String(bad));
  }
});

test("safeLocalUrl: крапкові складові не виводять з /published/ (`..`, `%2e%2e` у будь-якому регістрі)", () => {
  /* Браузер зводить ці адреси в `/api/task` — вони ПОВИННІ відкидатись, хоч на вигляд і під /published/. */
  assert.equal(new URL("/published/../api/task", ORIGIN).pathname, "/api/task", "свідок: браузер справді зводить `..`");
  assert.equal(new URL("/published/%2e%2e/api/task", ORIGIN).pathname, "/api/task", "свідок: і `%2e%2e`");
  for (const bad of ["/published/../api/task", "/published/%2e%2e/api/task", "/published/%2E%2E/api/task",
    "/published/%2e./api/task", "/published/.%2E/api/task", "/published/./p/", "/published/p/./t/", "/published/p/../t/",
    "/published/p/..%2f..%2fapi/task", "/published/p/%2e%2e%2fapi/task", "/published/p%5c..%5capi/task",
    "/published/%2e/p/", "/published/p/t/..?x", "/published/p/t/%2e%2e#x", "/published/%zz/"]) {
    assert.equal(safeLocalUrl(bad, ORIGIN), null, bad);
  }
});

test("safeLocalUrl: розвʼязана адреса лишається на оригіні канваса й під /published/", () => {
  // Нормальні id з крапкою всередині складової — не крапкова складова.
  assert.equal(safeLocalUrl("/published/p/blog.v2/", ORIGIN), "/published/p/blog.v2/");
  assert.equal(safeLocalUrl("/published/p/..blog/", ORIGIN), "/published/p/..blog/");
  // Недійсний оригін — не вгадуємо, а відмовляємо.
  assert.equal(safeLocalUrl("/published/p/blog/", "не оригін"), null);
});

/* ── пароль превʼю ─────────────────────────────────────────────────────── */

const GATE_TASK = (state, extra = {}) => ({
  id: "blog", publish_url: "https://pv-1.example.app", preview_password: "1100", preview_password_custom: true,
  preview_gate: { state, stale: 2, ungated: 3, inner_stale: 0, pages: 5 }, ...extra,
});

test("pwView: ЛІГА — як було (пароль, свій/типовий, stale, ungated)", () => {
  assert.deepEqual(pwView(GATE_TASK("stale"), LEG), { pw: "1100", pwCustom: true, pwStale: true, pwUngated: 0 });
  assert.deepEqual(pwView(GATE_TASK("ungated"), LEG), { pw: "1100", pwCustom: true, pwStale: false, pwUngated: 3 });
  assert.deepEqual(pwView(GATE_TASK("current"), LEG), { pw: "1100", pwCustom: true, pwStale: false, pwUngated: 0 });
});

test("pwView: stale/ungated лише для ОПУБЛІКОВАНОЇ в ЛІГА задачі (нема publish_url — нема тривоги)", () => {
  const t = GATE_TASK("stale", { publish_url: null });
  assert.equal(pwView(t, LEG).pwStale, false);
  assert.equal(pwView(GATE_TASK("ungated", { publish_url: null }), LEG).pwUngated, 0);
});

test("pwView: простір, де публікує модуль, — жодних попереджень про пароль і жодного пароля ЛІГА", () => {
  // `preview_password` у відповіді сервера лишається ЛІГА-шним навіть тут: показувати його — брехня.
  const t = GATE_TASK("module");
  assert.deepEqual(pwView(t, MOD), { pw: "", pwCustom: false, pwStale: false, pwUngated: 0 });
  // і коли лічильники виставлено, а стан — 'module', попереджень однаково нема
  assert.equal(pwView({ ...t, preview_gate: { state: "module", stale: 9, ungated: 9 } }, MOD).pwStale, false);
  assert.equal(pwView({ ...t, preview_gate: { state: "module", stale: 9, ungated: 9 } }, MOD).pwUngated, 0);
  // навіть якщо сервер раптом дасть 'stale', модульний простір пароля ЛІГА не показує
  assert.equal(pwView(GATE_TASK("stale"), MOD).pw, "");
  assert.equal(pwView(GATE_TASK("stale"), MOD).pwStale, false);
});

test("pwView: стан 'module' від сервера — не 'stale' і не 'ungated' навіть для legacy-подібного простору", () => {
  const v = pwView(GATE_TASK("module"), LEG);
  assert.equal(v.pwStale, false);
  assert.equal(v.pwUngated, 0);
});

test("pwView: немає задачі — порожньо", () => {
  assert.deepEqual(pwView(null, LEG), { pw: "", pwCustom: false, pwStale: false, pwUngated: 0 });
});

/* ── помилки публікації → людський текст ───────────────────────────────── */

const E = (code, extra = {}) => Object.assign(new Error(extra.message ?? "сире повідомлення сервера"), { code, ...extra });

test("publishErr: коди модульної публікації → окремі ключі словника", () => {
  assert.equal(publishErr(E("no-publish-module", { status: 409 })).key, "publishErrNoModule");
  assert.equal(publishErr(E("publish-busy", { status: 409 })).key, "publishErrBusy");
  assert.equal(publishErr(E("bad-task-id", { status: 400 })).key, "publishErrBadTaskId");
  assert.equal(publishErr(E("module-error", { status: 502 })).key, "publishErrModule");
  assert.equal(publishErr(E("bad-folder", { status: 409, message: "path-too-broad" })).key, "publishErrBadFolder");
});

test("publishErr: bad-folder — людська причина зі словника просторів (`spaceErrKey`), а не сирий код", () => {
  const r = publishErr(E("bad-folder", { message: "path-too-broad" }));
  assert.equal(r.reasonKey, "spaceErrTooBroad");
  assert.deepEqual(r.args, [], "сирий код не їде поряд із людською причиною");
  for (const [code, key] of [["path-not-absolute", "spaceErrNotAbsolute"], ["path-system", "spaceErrSystem"],
    ["path-tool", "spaceErrTool"], ["path-registered", "spaceErrRegistered"], ["path-overlap", "spaceErrOverlap"],
    ["path-not-dir", "spaceErrNotDir"], ["path-unwritable", "spaceErrUnwritable"]]) {
    assert.equal(publishErr(E("bad-folder", { message: code })).reasonKey, key, code);
    assert.ok(DICT.uk[key] !== undefined && DICT.en[key] !== undefined, key);
  }
});

test("publishErr: bad-folder із кодом, якого словник просторів не знає, — сам код як запасний варіант", () => {
  for (const code of ["path-deai-home", "path-invalid", "spaces-unreadable"]) {
    assert.deepEqual(publishErr(E("bad-folder", { message: code })), { key: "publishErrBadFolder", args: [code] }, code);
  }
});

test("publishErr: bad-folder показує лише код path-*/spaces-*, а не будь-який текст сервера (і не `spaceErrGeneric`)", () => {
  for (const raw of ["/Users/ivan/Documents/секрет", "C:\\Users\\ivan", "path-x/../../etc", "path-", "", "щось ще",
    "path-too-broad і шлях /Users/ivan", "task-id-collision", "timeout", "name-required"]) {
    const r = publishErr(E("bad-folder", { message: raw }));
    assert.deepEqual(r, { key: "publishErrBadFolder", args: [""] }, `«${raw}» не мусить потрапити в текст`);
  }
});

test("publishErr: module-error не несе тексту модуля (там можуть бути шляхи)", () => {
  const r = publishErr(E("module-error", { status: 502, message: "boom at /Users/ivan/deai-published/p/blog" }));
  assert.deepEqual(r.args, []);
});

test("publishErr: 400 без коду з текстом «no iterations marked» (рядок статусу чи тіло) — окремий текст", () => {
  const real = "no iterations marked for publish - toggle the green dot first";
  for (const extra of [
    { statusText: real, message: "<!DOCTYPE HTML><html lang=\"en\"><head>…" },          // як у браузері: причина в рядку статусу
    { statusText: "", body: `<html><body><p>Message: ${real}.</p></body></html>`, message: "<!DOCTYPE HTML>" },
    { message: real },
  ]) {
    const r = publishErr(E(undefined, { status: 400, ...extra }));
    assert.equal(r.key, "publishErrNoIterations", JSON.stringify(extra));
    assert.deepEqual(r.args, []);
  }
});

test("publishErr: інший 400 без коду (`bad payload`) і 400 без тексту — загальна відмова, а не «нема ітерацій»", () => {
  for (const extra of [
    { statusText: "bad payload", message: "<!DOCTYPE HTML>…" },
    { statusText: "", body: "<p>Message: bad payload.</p>", message: "<!DOCTYPE HTML>…" },
    { message: "щось" },
  ]) {
    const r = publishErr(E(undefined, { status: 400, ...extra }));
    assert.equal(r.key, "errFailed", JSON.stringify(extra));
    assert.deepEqual(r.args, [extra.message]);
  }
});

test("publishErr: текст «no iterations marked» без статусу 400 чи з кодом — не підміняється", () => {
  assert.equal(publishErr(E(undefined, { status: 500, statusText: "no iterations marked" })).key, "errFailed");
  assert.equal(publishErr(E("bad-settings", { status: 400, statusText: "no iterations marked" })).key, "errFailed");
});

test("publishErr: решта — загальне «Не вдалося: …» із текстом сервера", () => {
  for (const [code, status] of [["secrets-unreadable", 409], ["space-json-unreadable", 409], ["bad-settings", 400],
    ["no-task", 404], ["constructor", 500], [undefined, 500], [undefined, undefined]]) {
    const r = publishErr(E(code, { status, message: "причина" }));
    assert.equal(r.key, "errFailed", `${code}/${status}`);
    assert.deepEqual(r.args, ["причина"]);
  }
  assert.equal(publishErr(null).key, "errFailed");
});

test("publishErr: кожен ключ є у словнику ОБОХ мов", () => {
  const keys = new Set();
  for (const e of [E("no-publish-module"), E("publish-busy"), E("bad-task-id"), E("module-error"),
    E("bad-folder", { message: "path-too-broad" }), E("bad-folder", { message: "path-invalid" }),
    E(undefined, { status: 400, statusText: "no iterations marked for publish" }), E("other")]) {
    const r = publishErr(e);
    keys.add(r.key);
    if (r.reasonKey) keys.add(r.reasonKey);
  }
  for (const k of keys) {
    assert.ok(DICT.uk[k] !== undefined && DICT.en[k] !== undefined, `«${k}» бракує в словнику`);
  }
});

test("словник: підписи локальної публікації — обидві мови, без сирого ISO", () => {
  for (const k of ["publishLocalDone", "publishOpen", "publishLocalSub", "publishLocalLinkSub",
    "publishErrNoModule", "publishErrBadFolder", "publishErrBusy", "publishErrBadTaskId", "publishErrModule",
    "publishErrNoIterations"]) {
    assert.ok(DICT.uk[k] !== undefined && DICT.en[k] !== undefined, `«${k}» бракує в словнику`);
  }
  assert.match(DICT.uk.publishLocalSub("5 хв тому"), /локально/);
  assert.match(DICT.uk.publishLocalSub("5 хв тому"), /5 хв тому/);
  assert.match(DICT.en.publishLocalSub("5 min ago"), /local/);
  assert.equal(DICT.uk.publishLocalSub(""), "локально", "без часу — лише позначка, без висячого «·»");
  assert.equal(DICT.en.publishLocalSub(""), "local");
  assert.match(DICT.uk.publishErrBadFolder("ТЕКСТ-ПРИЧИНИ"), /ТЕКСТ-ПРИЧИНИ/);
  assert.match(DICT.en.publishErrBadFolder("REASON-TEXT"), /REASON-TEXT/);
  assert.doesNotMatch(DICT.uk.publishErrBadFolder(""), /\(\)|:\s*$/, "без причини — без порожніх дужок і висячого двокрапка");
  assert.doesNotMatch(DICT.en.publishErrBadFolder(""), /\(\)|:\s*$/);
});

/* Тексти не обіцяють того, чого в 2а нема: керування модулями в UI — етап 3 (у 2а лише API), а публікація
   у просторі без інтеграцій ПРАЦЮЄ (у локальну теку) — і «зʼявиться з модулями» про неї вже неправда. */
test("словник: ні публікація «зʼявиться з модулями», ні «налаштування простору» як дверей, яких нема", () => {
  for (const lang of ["uk", "en"]) {
    const d = DICT[lang];
    assert.doesNotMatch(d.integrationsOff, lang === "uk" ? /публікація, GitLab/ : /publishing, GitLab/, `${lang}: integrationsOff`);
    assert.match(d.integrationsOff, lang === "uk" ? /публікація йде в локальну теку/ : /publishing goes to a local folder/);
    assert.match(d.integrationsOff, /GitLab/);
    for (const k of ["publishErrNoModule", "publishErrBadFolder"]) {
      const text = typeof d[k] === "function" ? d[k]("") : d[k];
      assert.doesNotMatch(text, /налаштуваннях простору|space settings|You can turn/i, `${lang}: ${k} обіцяє UI налаштувань`);
    }
  }
  assert.match(DICT.uk.publishErrNoModule, /вимкнено для цього простору/);
  assert.match(DICT.en.publishErrNoModule, /turned off for this space/);
});

test("словник: publishErrBadTaskId називає зарезервовані імена Windows (обидві мови)", () => {
  for (const lang of ["uk", "en"]) {
    for (const name of ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"]) {
      assert.ok(DICT[lang].publishErrBadTaskId.includes(name), `${lang}: нема ${name}`);
    }
  }
});

/* ── публікація на свій Vercel (2b-1, Task 3): модуль «за адресою» ─────────────────────────────
   `capabilities.publish === 'vercel-publish'`; сервер (Tasks 1–2) віддає в `/api/task`
   `publish_remote = {module, state, published_at, url, gated}`, `publish_url`, `publish_gate`,
   `publish_gate_stale` і `publish_share_url` (= `publish_url` + `#k=<пароль>`, СКЛАДЕНИЙ сервером).
   UI нічого не складає сам: «Скопіювати» кладе `publish_share_url` дослівно. */

const VER = { id: "v", integrations: false, capabilities: { publish: "vercel-publish", tokens: null } };
const VURL = "https://pv-12345678.vercel.app";
const REMOTE = (o = {}) => ({
  module: "vercel-publish", state: { project: "pv-12345678" }, published_at: "2026-10-16T10:00:00Z", url: VURL, gated: true, ...o,
});
const VTASK = (o = {}) => ({
  id: "blog", publish_url: VURL, published_at: "16.10.2026 12:30", publish_remote: REMOTE(), publish_gate: true,
  publish_share_url: `${VURL}#k=1100`, ...o,
});

test("isRemotePublish: так лише коли постачальник — модуль, а слід `publish_remote` саме його і саме на цю адресу", () => {
  assert.equal(isRemotePublish(VTASK(), VER), true);
  assert.equal(isRemotePublish(VTASK(), LEG), false, "ЛІГА: слід модуля — не про ЛІГА-публікацію");
  assert.equal(isRemotePublish(VTASK({ publish_remote: REMOTE({ module: "legacy" }) }), LEG), false,
    "навіть якщо слід назвав постачальника «legacy»: у ЛІГА свій шлях посилання (`#k=` у `copyUrl`)");
  assert.equal(isRemotePublish(VTASK(), MOD), false, "інший модуль-постачальник (static-publish): слід Vercel не його");
  assert.equal(isRemotePublish(VTASK(), NONE), false);
  assert.equal(isRemotePublish(VTASK({ publish_remote: REMOTE({ module: "other-publish" }) }), VER), false);
  assert.equal(isRemotePublish(VTASK({ publish_url: "https://інша.example/" }), VER), false,
    "адресу виправили вручну чи перезаписала ЛІГА — слід модуля більше не її");
  assert.equal(isRemotePublish(VTASK({ publish_remote: REMOTE({ url: undefined }) }), VER), false);
  assert.equal(isRemotePublish({ id: "blog", publish_url: VURL }, VER), false, "нема `publish_remote`");
  assert.equal(isRemotePublish(VTASK({ publish_url: "" }), VER), false);
  assert.equal(isRemotePublish(VTASK({ publish_remote: "рядок" }), VER), false, "`publish_remote` — обʼєкт");
  assert.equal(isRemotePublish(VTASK({ publish_remote: [REMOTE()] }), VER), false);
  assert.equal(isRemotePublish(null, VER), false);
  assert.equal(isRemotePublish(VTASK(), null), false);
  assert.equal(isRemotePublish(VTASK(), { id: "x", integrations: false }), false, "стара форма: постачальник невідомий");
});

test("previewTarget: модуль «за адресою» — зовнішня адреса з `publish_url` і готовим посиланням для колег", () => {
  const tg = previewTarget(VTASK(), VER);
  assert.deepEqual(tg, { kind: "external", url: VURL, at: null, remote: true, share: `${VURL}#k=1100` });
});

test("previewTarget: модуль без пароля — `publish_share_url` = сама адреса (так її й віддає сервер)", () => {
  const tg = previewTarget(VTASK({ publish_gate: false, publish_share_url: VURL, publish_remote: REMOTE({ gated: false }) }), VER);
  assert.equal(tg.share, VURL);
  assert.ok(!tg.share.includes("#k="));
});

test("previewTarget: нема `publish_share_url` (чи він чужий) — ділимось голою адресою, не вигадуємо пароль", () => {
  assert.equal(previewTarget(VTASK({ publish_share_url: undefined }), VER).share, VURL);
  assert.equal(previewTarget(VTASK({ publish_share_url: 42 }), VER).share, VURL);
  assert.equal(previewTarget(VTASK({ publish_share_url: "https://інша.example/#k=1" }), VER).share, VURL,
    "посилання не на цю адресу — не копіюємо");
});

test("previewTarget: слід Vercel + старий слід static-publish — перемагає той, що відповідає постачальнику (Vercel)", () => {
  const task = VTASK({ publish_local: LOCAL });
  assert.equal(previewTarget(task, VER).kind, "external");
  assert.equal(previewTarget(task, VER).remote, true);
  assert.equal(previewTarget(task, MOD).kind, "local", "постачальник знову static-publish: його слід, як і було");
});

test("previewTarget: ЛІГА зі слідом модуля — як було (зовнішня, без `remote`, без `share`)", () => {
  assert.deepEqual(previewTarget(VTASK(), LEG), { kind: "external", url: VURL, at: null });
});

test("previewTarget: модуль, але `publish_url` не від нього — стара поведінка 0.2.0 (відкриваємо, `remote` нема)", () => {
  const tg = previewTarget({ id: "blog", publish_url: "https://pv-1.example.app" }, VER);
  assert.deepEqual(tg, { kind: "external", url: "https://pv-1.example.app", at: null });
});

test("copyUrl: модуль «за адресою» — `publish_share_url` ДОСЛІВНО, фрагмент `#k=` UI не складає і не дописує вдруге", () => {
  const tg = previewTarget(VTASK(), VER);
  const url = copyUrl(tg, { origin: "http://localhost:8765", pageId: "it1/home", password: "ЛІГА-пароль" });
  assert.equal(url, `${VURL}#k=1100`);
  assert.equal((url.match(/#/g) || []).length, 1, "один фрагмент");
  assert.equal((url.match(/k=/g) || []).length, 1, "`k=` один раз");
  assert.ok(!url.includes("ЛІГА-пароль") && !url.includes("&p="), "ні пароль ЛІГА, ні сторінка не дописуються");
});

test("copyUrl: модуль без пароля — гола адреса без жодного фрагмента, навіть коли UI знає пароль ЛІГА", () => {
  const tg = previewTarget(VTASK({ publish_gate: false, publish_share_url: VURL, publish_remote: REMOTE({ gated: false }) }), VER);
  assert.equal(copyUrl(tg, { pageId: "it1", password: "1100" }), VURL);
});

test("copyUrl: ЛІГА і зовнішня без `remote` — як було (`#k=…&p=…`)", () => {
  const tg = previewTarget(VTASK(), LEG);
  assert.equal(copyUrl(tg, { pageId: "it4", password: "1100" }), `${VURL}/#k=1100&p=it4`);
});

test("safeRemoteUrl: лише абсолютний https:// без облікових даних і лише ASCII", () => {
  for (const ok of [VURL, "https://pv-1.vercel.app/", "https://example.com:8443/a/b?x=1", "https://xn--e1afmkfd.xn--p1ai/"]) {
    assert.equal(safeRemoteUrl(ok), ok, ok);
  }
  for (const bad of [
    "javascript:alert(1)", "JAVASCRIPT:alert(1)", "data:text/html,<b>", "http://pv-1.vercel.app", "HTTP://x.example/",
    "//evil.example/", "/published/p/t/", "ftp://x.example/", "vercel.app", "https:", "https://", "https:///x", "https://?x", "https://#x",
    "https://user:pw@pv-1.vercel.app/", "https://user@pv-1.vercel.app/", "https://@pv-1.vercel.app/", "https://:@pv-1.vercel.app/",
    "https://pv-1.vercel.app\\@evil.example/", "https://pv 1.vercel.app/", "https://pv-1.vercel.app/ x", " https://pv-1.vercel.app/",
    "https://pv-1.vercel.app/\n", "https://pv-1.vercel.app/\t", "https://пв-1.vercel.app/", "https://pv-1.vercel.app/привіт",
    "https://pv-1.vercel.app:port/", "https://pv-1.vercel.app:99999/",
    "", null, undefined, 42, {}, ["https://pv-1.vercel.app"],
  ]) {
    assert.equal(safeRemoteUrl(bad), null, JSON.stringify(bad));
  }
});

test("remoteShareUrl: `publish_share_url` оновленої задачі, коли він про цю адресу; інакше сама адреса з відповіді", () => {
  assert.equal(remoteShareUrl({ publish_share_url: `${VURL}#k=1100` }, VURL), `${VURL}#k=1100`);
  assert.equal(remoteShareUrl({ publish_share_url: VURL }, VURL), VURL);
  assert.equal(remoteShareUrl({}, VURL), VURL, "задачу не оновили — без пароля");
  assert.equal(remoteShareUrl(null, VURL), VURL);
  assert.equal(remoteShareUrl({ publish_share_url: "https://стара.example/#k=1" }, VURL), VURL,
    "посилання від ПОПЕРЕДНЬОЇ адреси (оновлення задачі не вдалось) не копіюємо");
  assert.equal(remoteShareUrl({ publish_share_url: 7 }, VURL), VURL);
  assert.equal(remoteShareUrl({}, ""), null);
  assert.equal(remoteShareUrl({}, undefined), null);
});

test("remoteNoticeLines: `warnings` — рядки плашки (як є, як ТЕКСТ), без попереджень і `verified: false` — нейтральна підказка", () => {
  assert.deepEqual(remoteNoticeLines({ warnings: ["Увімкнено Deployment Protection", "Старі публікації не прибрано"], verified: false }),
    [{ text: "Увімкнено Deployment Protection" }, { text: "Старі публікації не прибрано" }]);
  assert.deepEqual(remoteNoticeLines({ verified: false }), [{ key: "publishRemoteUnverified" }]);
  assert.deepEqual(remoteNoticeLines({ verified: false, warnings: [] }), [{ key: "publishRemoteUnverified" }]);
  assert.deepEqual(remoteNoticeLines({ verified: true }), []);
  assert.deepEqual(remoteNoticeLines({ verified: true, warnings: ["щось"] }), [{ text: "щось" }], "попередження показуємо й при verified");
  assert.deepEqual(remoteNoticeLines({}), [], "модуль не сказав про перевірку — мовчимо, а не лякаємо");
  assert.deepEqual(remoteNoticeLines(null), []);
});

test("remoteNoticeLines: розмітка в попередженні — просто текст; сміття й надлишок відсікаються", () => {
  const html = "<img src=x onerror=alert(1)>";
  assert.deepEqual(remoteNoticeLines({ warnings: [html] }), [{ text: html }], "екранує вставка (textContent), модель текст не чіпає");
  assert.deepEqual(remoteNoticeLines({ warnings: ["", "  ", 5, null, {}, "  ок  "] }), [{ text: "ок" }]);
  assert.deepEqual(remoteNoticeLines({ warnings: "не масив", verified: false }), [{ key: "publishRemoteUnverified" }]);
  assert.equal(remoteNoticeLines({ warnings: Array.from({ length: 9 }, (_, i) => `w${i}`) }).length, 5, "не більше п'яти");
  assert.equal(remoteNoticeLines({ warnings: ["я".repeat(900)] })[0].text.length, 300, "не довше 300 символів");
});

test("publishErr: `vercel-busy` — свій людський текст, без тексту сервера", () => {
  const b = publishErr(E("vercel-busy", { status: 409, message: "Too many requests, token=abc123" }));
  assert.deepEqual(b, { key: "publishErrVercelBusy", args: [] });
});

test("publishErr: `vercel-auth` — свій ключ і ТЕКСТ СЕРВЕРА другим абзацом (причину 403 людина може виправити)", () => {
  const msg = "Vercel відмовив у доступі (HTTP 403): токен без прав на команду";
  assert.deepEqual(publishErr(E("vercel-auth", { status: 409, message: msg })), { key: "publishErrVercelAuth", args: [msg] });
  assert.deepEqual(publishErr(E("vercel-auth", { status: 409, message: "" })), { key: "publishErrVercelAuth", args: [""] },
    "без тексту — без другого абзацу, але й без падіння");
  assert.deepEqual(publishErr(E("vercel-auth", { status: 409, message: undefined })).args, [""]);
});

test("publishErr: `vercel-auth` — повний `error` із тіла (api() ріже `message` по 200), ≤ 300, без керівних символів", () => {
  const long = `Vercel відмовив у доступі (HTTP 403): ${"я".repeat(400)}`;
  const body = JSON.stringify({ ok: false, code: "vercel-auth", error: long });
  const r = publishErr(E("vercel-auth", { status: 409, message: long.slice(0, 200), body }));
  assert.equal(r.args[0].length, 300, "текст із тіла (не обрізаний api() до 200), але не довше 300");
  assert.ok(r.args[0].startsWith("Vercel відмовив у доступі (HTTP 403): яя"));
  const ctl = publishErr(E("vercel-auth", { status: 409, message: "a\u0000b\nc\u001bd" }));
  assert.equal(ctl.args[0], "a b c d", "керівні символи → пробіл");
  /* тіло не JSON чи без `error` — лишається `message` */
  assert.deepEqual(publishErr(E("vercel-auth", { message: "текст", body: "<html>" })).args, ["текст"]);
  assert.deepEqual(publishErr(E("vercel-auth", { message: "текст", body: JSON.stringify({ ok: false }) })).args, ["текст"]);
  assert.deepEqual(publishErr(E("vercel-auth", { message: "текст", body: JSON.stringify({ error: 5 }) })).args, ["текст"]);
});

test("publishErr: текст сервера не потрапляє в розмітку — `tell` кладе його `textContent` (проводка, `ask.js`)", () => {
  const ask = readFileSync(new URL("../app/ask.js", import.meta.url), "utf8");
  assert.match(ask, /head\.textContent = text;/);
  assert.match(ask, /export const tell = \(message\) => overlay\(message, 'tell'\);/);
});

test("словник: плашка й застереження Vercel — обидві мови; тексти обіцяють лише наявне", () => {
  const text = (lang, k, ...a) => (typeof DICT[lang][k] === "function" ? DICT[lang][k](...a) : DICT[lang][k]);
  for (const k of ["publishRemoteDone", "publishRemoteUnverified", "publishPublicWarn", "publishGateStale",
    "publishErrVercelAuth", "publishErrVercelBusy"]) {
    for (const lang of ["uk", "en"]) {
      assert.equal(typeof text(lang, k, ""), "string", `${lang}: «${k}» бракує або це не рядок`);
      assert.ok(text(lang, k, "").length > 8, `${lang}: «${k}» порожній`);
    }
  }
  assert.equal(DICT.uk.publishRemoteDone, "Опубліковано на Vercel");
  assert.equal(DICT.en.publishRemoteDone, "Published on Vercel");
  assert.match(DICT.uk.publishPublicWarn, /публічн/);
  assert.match(DICT.en.publishPublicWarn, /public/i);
  assert.match(DICT.uk.publishGateStale, /перепублікуйте/);
  assert.match(DICT.en.publishGateStale, /republish/i);
  for (const lang of ["uk", "en"]) {
    const a = text(lang, "publishErrVercelAuth", "");
    assert.match(a, /token|токен/i, `${lang}: «токен» не названо`);
    assert.match(a, /team|команд/i, `${lang}: «команду» не названо — 403 буває й через неї`);
    /* `vercel-auth` — не лише відхилений токен (403: права, тариф, команда): не стверджуємо «токен не прийнято». */
    assert.doesNotMatch(a, /не прийня|not accept|rejected|invalid|недійсн/i, `${lang}: стверджує, що токен не прийнято`);
    /* Екрана налаштувань модулів у 0.3.0 нема (етап 3): керують через API чи агента — не обіцяємо кнопки. */
    assert.doesNotMatch(a, /натисніть|press|click|кнопк|button|екран|screen/i, `${lang}: обіцяє екран налаштувань`);
  }
  assert.match(DICT.uk.publishErrVercelAuth(""), /API|агент/);
  assert.match(DICT.en.publishErrVercelAuth(""), /API|agent/i);
  assert.match(DICT.uk.publishErrVercelAuth(""), /^Vercel відмовив у доступі/);
  assert.match(DICT.en.publishErrVercelAuth(""), /^Vercel denied access/);
});

test("словник: `publishErrVercelAuth(why)` — текст сервера другим абзацом; без нього — без висячих абзаців", () => {
  for (const lang of ["uk", "en"]) {
    const f = DICT[lang].publishErrVercelAuth;
    assert.ok(f("HTTP 403: причина-ТЕКСТ").endsWith("\n\nHTTP 403: причина-ТЕКСТ"), lang);
    assert.doesNotMatch(f(""), /\n\n|\n$/, `${lang}: без причини — без порожнього абзацу`);
    assert.doesNotMatch(f(""), /undefined|null/);
  }
});

test("publishErr: нові ключі є у словнику обох мов", () => {
  for (const code of ["vercel-auth", "vercel-busy"]) {
    const k = publishErr(E(code)).key;
    assert.ok(DICT.uk[k] !== undefined && DICT.en[k] !== undefined, k);
  }
});
