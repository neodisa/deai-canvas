import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { agentBlockHTML, introCardHTML, introHTML, kbdText, promptText, tourHTML } from "../app/first-run.js";
import { getLang, setLang } from "../app/i18n.js";
import { welcomeHTML } from "../app/space-dialogs.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CSS = readFileSync(path.join(ROOT, "app", "styles.css"), "utf8");
const CYR = /[а-яіїєґА-ЯІЇЄҐ]/;
const SETUP = { paths: { setup: "/Users/a/deai-canvas/SETUP.md" } };
setLang("uk");

test("kbdText: [[X]] → <kbd>X</kbd>, решта екранується", () => {
  assert.equal(kbdText("a [[C]] <b>"), "a <kbd>C</kbd> &lt;b&gt;");
});

test("промпт: абсолютний шлях SETUP.md з /api/setup і адреса канваса; без відповіді — описова фраза", () => {
  assert.equal(promptText(SETUP, "http://localhost:8765"),
    "Налаштуй Deai Canvas на цьому компʼютері за інструкцією /Users/a/deai-canvas/SETUP.md. Канвас уже працює: http://localhost:8765");
  assert.match(promptText(null, "http://localhost:8765"), /за інструкцією SETUP\.md у теці, де встановлено Deai Canvas\. Канвас уже працює: http:\/\/localhost:8765$/);
  const h = agentBlockHTML({ paths: { setup: "/x/<b>/SETUP.md" } }, "http://localhost:8765");
  assert.match(h, /<pre class="prompt" id="fr-prompt">[^<]*\/x\/&lt;b&gt;\/SETUP\.md/);
  assert.match(h, /<button type="button" class="ctl ctl--pri" data-th="frcopy">/);
});

test("знайомство: карта aria-hidden з 7 позначками, легенда <ol> з 7 пунктами, цикл з 5 карток", () => {
  const h = tourHTML(3);
  assert.match(h, /<div class="fr-map" aria-hidden="true">/);
  assert.equal((h.match(/class="fr-n"/g) ?? []).length, 7);
  const legend = h.match(/<ol class="fr-legend">([\s\S]*?)<\/ol>/)[1];
  assert.equal((legend.match(/<li>/g) ?? []).length, 7);
  const cycle = h.match(/<ol class="fr-cycle">([\s\S]*?)<\/ol>/)[1];
  assert.equal((cycle.match(/<li>/g) ?? []).length, 5);
  assert.match(h, /<h3 class="fr-h3">Цикл роботи<\/h3>/);
  assert.match(legend, /<kbd>⌘K<\/kbd>/);
  assert.match(introHTML(), /<section class="fr-intro" aria-labelledby="fr-intro-h"><h2 class="fr-h2" id="fr-intro-h">Знайомство<\/h2>/);
});

test("картка ⌘K: діалог із заголовком, «Закрити» = data-a=cancel; рядок демо — лише з demo", () => {
  const h = introCardHTML({ demo: true });
  assert.match(h, /<form class="fr-card" role="dialog" aria-modal="true" aria-labelledby="fr-card-t" novalidate>/);
  assert.match(h, /<h2 class="cv-ask-title" id="fr-card-t">Знайомство з канвасом<\/h2>/);
  assert.match(h, /<button type="button" class="icob" data-a="cancel" data-autofocus aria-label="Закрити"/);
  assert.match(h, /data-fr="demo"[^>]*>Відкрити демо<\/button>/);
  assert.doesNotMatch(introCardHTML({ demo: false }), /data-fr="demo"/);
  assert.match(h, /data-form-error/);
});

test("привітання: блок агента, «або без агента», кнопки майстра, знайомство; рядка welcomeAgent нема", () => {
  const h = welcomeHTML({ setup: SETUP, origin: "http://localhost:8765" });
  assert.match(h, /class="fr-agent"[\s\S]*class="fr-or">або без агента<[\s\S]*data-th="spacenew"[\s\S]*data-th="spaceopen"[\s\S]*class="fr-intro"/);
  assert.match(h, /Створити простір вручну/);
  assert.doesNotMatch(h, /th-welcome-agent|створи простір Клієнт X/);
});

test("англійська: жодної кирилиці в розмітці знайомства, картки й привітання", () => {
  const before = getLang();
  setLang("en");
  try {
    for (const h of [tourHTML(3), introCardHTML({ demo: true }), welcomeHTML({ setup: SETUP, origin: "http://localhost:8765" })]) {
      assert.ok(!CYR.test(h), h.match(/.{0,30}[а-яіїєґ].{0,30}/i)?.[0]);
    }
  } finally { setLang(before); }
});

test("кожен клас розмітки «Першого запуску» має правило в styles.css", () => {
  const html = [tourHTML(3), introHTML(), introCardHTML({ demo: true }), agentBlockHTML(SETUP, "x")].join("");
  const classes = new Set([...html.matchAll(/class="([^"]+)"/g)].flatMap((m) => m[1].split(/\s+/)).filter((c) => c.startsWith("fr-")));
  for (const c of classes) assert.ok(new RegExp(`\\.${c}(?![\\w-])`).test(CSS), `.${c} без правила`);
});

test("проводка ⌘K: картка через askForm без якоря, клік по підкладці закриває, демо — /api/demo-task з reuse", () => {
  const src = readFileSync(path.join(ROOT, "app", "app.js"), "utf8");
  const body = src.slice(src.indexOf("async function openIntro("), src.indexOf("async function openDemo("));
  assert.match(body, /askForm\(\(\) => introCardHTML\(\{ demo: /);
  assert.match(body, /e\.target === scrim/);
  const demo = src.slice(src.indexOf("async function openDemo("), src.indexOf("async function openDemo(") + 900);
  assert.match(demo, /post\('\/api\/demo-task', \{ space: spaceId, title: t\('frDemoTaskTitle'\), reuse: true \}\)/);
  assert.match(demo, /r\.existed \? switchTask\(r\.id\) : wizOpenTask\(r\)/);
});

test("пароль: меню веде в Модулі з шухлядою на полі пароля; картка — `pw` відкриває ту саму шухляду", async () => {
  const { barHTML } = await import("../app/shell-bar.js");
  const src = readFileSync(path.join(ROOT, "app", "app.js"), "utf8");
  assert.match(src, /\n  modpw: \(\) => \{ openDd = null; openPublishPassword\(\); \}/);
  assert.match(src, /act === 'pw'\) openCnDrawer\(e, 'edit', null, 'password'\)/);
  assert.match(src, /openCnDrawer\(e, 'edit', null, 'password'\)/);
  assert.match(src, /\[data-cn-field="\$\{CSS\.escape\(focusKey\)\}"\]/);
  assert.match(src, /\(want \?\? el\.querySelector\('\[data-cn-field\]'\)/, "фокус — на названому полі, а не на першому");
  assert.equal(typeof barHTML, "function");
});

test("пароль: намір `pw` ставиться в `enterConnections` ПІСЛЯ всіх ранніх виходів, а не в `openPublishPassword`", () => {
  const src = readFileSync(path.join(ROOT, "app", "app.js"), "utf8");
  const open = src.slice(src.indexOf("function openPublishPassword("), src.indexOf("function openPublishPassword(") + 200);
  assert.match(open, /enterConnections\('publish', \{ pw: true \}\)/);
  assert.doesNotMatch(open, /connPwPending = true/);
  const at = src.indexOf("async function enterConnections(");
  const fn = src.slice(at, src.indexOf("\n}\n", at));
  assert.match(fn, /async function enterConnections\(role = '', \{ pw = false \} = \{\}\)/);
  const guard = fn.indexOf("if (!currentSpace(spacesResp)) return;");
  const set = fn.indexOf("connPwPending = pw;");
  assert.ok(guard > 0 && set > guard, "`connPwPending = pw` — після останнього раннього виходу");
});
