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
