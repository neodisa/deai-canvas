import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

/* Рендерери звіту — СПРАВЖНІ, не копія їхньої розмітки: розділ E питає, що
   документ малює НАСПРАВДІ, і другий опис тієї самої розмітки тут розійшовся б
   із першим рівно так, як розходились два описи звіту до 17.09.2026. */
import { reportHTML } from "../app/vendor/insp-report.js";
import { panelHTML } from "../app/insp-panel.js";
import { FULL_MODEL, MIN_MODEL } from "./_insp-fixtures.mjs";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");
const CSS_PATH = path.join(APP, "styles.css");

function readCss() {
  return readFileSync(CSS_PATH, "utf8");
}

/* Вирізаємо /* … *­/ ПЕРШИМ кроком, перед будь-яким скануванням правил.
   Інакше приклад коду всередині коментаря (навіть буквально
   `.ctl--old{height:31px}`) читається сканером як живе правило — саме так
   одне зі «спрацювань» чернової сітки впало на текст усередині коментаря. */
function stripComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

// ---------- WCAG-контраст (relative luminance, той самий формула, що й у
// специфікації) — потрібен, щоб перевірка --dim не була просто «збігом
// записаних наперед цифр», а рахувала контраст із фактичного значення токена.
function hexToRgb(hex) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full.slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function relLuminance([r, g, b]) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function contrastRatio(hexA, hexB) {
  const la = relLuminance(hexToRgb(hexA));
  const lb = relLuminance(hexToRgb(hexB));
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
function rootVar(css, name, depth = 0) {
  /* Токени палітри бувають аліасами (`--bg:var(--g100)`): без слідування за
     `var()` охоронець контрасту мовчки отримав би null і пропустив би пару. */
  const m = css.match(new RegExp(`--${name}\\s*:\\s*(#[0-9a-fA-F]{3,8}|var\\(--([a-z0-9-]+)\\))`));
  if (!m) return null;
  if (m[2]) return depth < 5 ? rootVar(css, m[2], depth + 1) : null;
  return m[1];
}

/* ===================================================================
   A. --dim замість --lo для дрібного тексту
   -------------------------------------------------------------------
   --lo (#6E7681) на --s1 (#15181D) дає 3.87:1 — нижче за AA (4.5:1) для
   тексту дрібнішого за ~18px. Знайдено рівно одне живе правило, де --lo
   грає роль КОЛЬОРУ ТЕКСТУ такого розміру: `.cv-updated` (11px). --lo
   лишається токеном — але для меж і декору, не для тексту.
   =================================================================== */

test("--dim існує, не є аліасом --lo, і дає AA-контраст (>=4.5:1) на --s1", () => {
  const css = readCss();
  const dim = rootVar(css, "dim");
  const lo = rootVar(css, "lo");
  const s1 = rootVar(css, "s1");
  assert.ok(dim, "у :root немає токена --dim");
  assert.ok(s1, "у :root немає токена --s1 — нема з чим порівнювати контраст");
  assert.notEqual(
    dim, lo,
    "--dim не сміє дублювати значення --lo: у --lo і --dim різне призначення " +
      "(межі/декор проти тексту), і однакове значення означало б, що дефект " +
      "контрасту нікуди не подівся, лише сховався під новим імʼям"
  );
  const ratio = contrastRatio(dim, s1);
  assert.ok(
    ratio >= 4.5,
    `--dim (${dim}) на --s1 (${s1}) дає ${ratio.toFixed(2)}:1 — нижче за AA (4.5:1)`
  );
});

/* ===================================================================
   A2. Палітра оболонки зі шкали логотипа Deai Canvas (Task 7, 09.10.2026)
   -------------------------------------------------------------------
   Пари, на яких тримається читабельність нової палітри. Рахуємо з фактичних
   значень токенів, а не з цифр у специфікації: перефарбування :root, яке
   зламало б контраст, має падати тут, а не на очах у дизайнера.
   =================================================================== */

function pairRatio(fg, bg) {
  const css = readCss();
  const a = rootVar(css, fg);
  const b = rootVar(css, bg);
  assert.ok(a, `у :root немає токена --${fg}`);
  assert.ok(b, `у :root немає токена --${bg}`);
  return { a, b, ratio: contrastRatio(a, b) };
}

test("--on-sel на --sel: текст на акцентній заливці >= 4.5:1", () => {
  const { a, b, ratio } = pairRatio("on-sel", "sel");
  assert.ok(ratio >= 4.5, `--on-sel (${a}) на --sel (${b}) дає ${ratio.toFixed(2)}:1`);
});

test("--sel-ink на --bg: виділення поверх світлого контенту >= 3:1 (не текст)", () => {
  const { a, b, ratio } = pairRatio("sel-ink", "bg");
  assert.ok(ratio >= 3, `--sel-ink (${a}) на --bg (${b}) дає ${ratio.toFixed(2)}:1`);
});

test("--dim на --s2: дрібний текст на картках і полях >= 4.5:1", () => {
  const { a, b, ratio } = pairRatio("dim", "s2");
  assert.ok(ratio >= 4.5, `--dim (${a}) на --s2 (${b}) дає ${ratio.toFixed(2)}:1`);
});

test("--bad-ink на --card: рамка помилкового поля діалогу >= 3:1 (нетекстовий контраст); --bad для цього не годиться", () => {
  const { a, b, ratio } = pairRatio("bad-ink", "card");
  assert.ok(ratio >= 3, `--bad-ink (${a}) на --card (${b}) дає ${ratio.toFixed(2)}:1`);
  /* Свідок, що тест міряє справжню різницю: токен для ТЕМНОЇ поверхні на білій картці рамці не годиться. */
  assert.ok(pairRatio("bad", "card").ratio < 3, "--bad на білому вже ≥ 3:1: окремий --bad-ink став зайвим");
});

test("--muted на --bg і на --card: вторинний текст на світлому >= 4.5:1", () => {
  for (const bg of ["bg", "card"]) {
    const { a, b, ratio } = pairRatio("muted", bg);
    assert.ok(ratio >= 4.5, `--muted (${a}) на --${bg} (${b}) дає ${ratio.toFixed(2)}:1`);
  }
});

test("свої модулі (3c): замок «Потрібна довіра» — --open на --s2 і --s3 >= 3:1; «Забрати довіру» в діалозі — --bad-ink на --g50 >= 4.5:1", () => {
  for (const bg of ["s2", "s3"]) {
    const { a, b, ratio } = pairRatio("open", bg);
    assert.ok(ratio >= 3, `--open (${a}) на --${bg} (${b}) дає ${ratio.toFixed(2)}:1`);
  }
  const { a, b, ratio } = pairRatio("bad-ink", "g50");
  assert.ok(ratio >= 4.5, `--bad-ink (${a}) на --g50 (${b}) дає ${ratio.toFixed(2)}:1`);
});

test("літерали синього акценту не живуть поза :root — тільки токени", () => {
  /* Старий акцент (#025cff і сусіди) був розкиданий літералами по ~10 місцях:
     перефарбувати його без пропусків можна було лише пошуком. Тепер колір —
     токен (`--sel`, `--sel-ink`, `--sel-tint`…), а літерал сюди не повертається. */
  const body = stripComments(readCss()).replace(/:root\s*\{[^}]*\}/, "");
  const re = /#025cff|#0b63ff|rgba\(\s*2\s*,\s*92\s*,\s*255|rgba\(\s*45\s*,\s*106\s*,\s*227/gi;
  const hits = [...body.matchAll(re)].map((m) => {
    const line = body.slice(0, m.index).split("\n").length;
    return `рядок ~${line}: ${m[0]}`;
  });
  assert.deepEqual(hits, [], `літерали старого акценту поза :root:\n${hits.join("\n")}`);
});

/* Рахуємо через ту саму пару (селектор, тіло), що й сітка висот нижче: правило
   «мале й на --lo» шукаємо ЛИШЕ там, де font-size і color:var(--lo) стоять в
   ОДНОМУ оголошенні — так, як їх насправді записують у цьому файлі. Саме тому
   `.cv-vpw::placeholder{color:var(--lo)}` (розмір успадковує від `.cv-vpw`,
   12px, але в САМОМУ правилі font-size не записаний) під цей тест не підпадає:
   це інша, ширша перевірка (успадкований розмір), яку План B цього тіка не
   просив, а звужувати межу заднім числом — вносити правку вигляду поза тим,
   що дозволено в Task 9. */
function ruleUsesLoAsSmallText(body) {
  const fs = body.match(/font-size\s*:\s*([\d.]+)px/);
  const usesLo = /color\s*:\s*var\(--lo\)/.test(body);
  return !!(fs && usesLo && Number(fs[1]) < 13);
}

/* Сильніше й простіше за початкове правило. Спершу тест шукав `--lo` лише в
   правилах із `font-size` меншим за 13px — і мав задокументовану дірку: розмір
   часто успадковується, а не стоїть у тому самому оголошенні (так було з
   `.cv-vpw::placeholder`, 12px від батька). Вимір показав, що після фіксу
   `--lo` не є кольором тексту НІ В ОДНОМУ правилі — тож правило можна звести
   до інваріанту без винятків: `--lo` (#6E7681, 3.87:1 на --s1) живе для меж і
   декору, для тексту є `--dim` (#8A929C, 5.65:1). Ні розміри, ні успадкування
   більше не мають значення. */
test("--lo ніколи не є кольором тексту — тільки межі й декор", () => {
  const hits = [];
  for (const m of stripComments(readCss()).matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    if (/(?:^|;)\s*color\s*:\s*var\(--lo\)/.test(m[2])) hits.push(m[1].trim());
  }
  assert.deepEqual(hits, [],
    `--lo як колір тексту (3.87:1 — нижче AA), треба --dim:\n${hits.join("\n")}`);
});

/* ===================================================================
   B. Кейфрейми не стартують з opacity:0
   -------------------------------------------------------------------
   Охоронець уже НЕ профілактичний: План B приїхав і приніс рівно ті дві
   поверхні, заради яких його писали, — `@keyframes pal` (палітра) і
   `@keyframes dd` (дропдаун смуги). Обидва живі, обидва рухають лише
   `transform`, і саме це охоронець і тримає.

   Причина, чому правило таке: у прототипі ці ж оверлеї тримали видимість на
   анімації, що стартувала з `opacity:0`, і дропдаун приїжджав ПОРОЖНІМ у
   headless-рендері `bin/shoot.mjs` (Playwright не чекає на кадр анімації
   так, як людське око). Кожен наступний оверлей поїде тим самим шляхом —
   тож правило лишається загальним, а не переліком двох імен.
   =================================================================== */

function extractKeyframeBlocks(css) {
  // Ручний підрахунок дужок: усередині @keyframes живуть вкладені блоки
  // (`from{...}`, `to{...}`, `50%{...}`), і звичайний "не жадібний" регексп
  // на них ламається. Сітка висот (розділ C) навпаки навмисно НЕ вкладена —
  // тому там прощий парсер безпечний, а тут потрібен окремий, точний.
  const blocks = [];
  const re = /@keyframes\s+([\w-]+)\s*\{/g;
  let m;
  while ((m = re.exec(css))) {
    let depth = 1;
    let i = m.index + m[0].length;
    const start = i;
    while (i < css.length && depth > 0) {
      if (css[i] === "{") depth++;
      else if (css[i] === "}") depth--;
      i++;
    }
    blocks.push({ name: m[1], body: css.slice(start, i - 1) });
  }
  return blocks;
}

function startsInvisible(body) {
  const m = body.match(/(?:^|\s|,)(?:from|0%)\s*\{([^}]*)\}/);
  return !!(m && /opacity\s*:\s*0(?:\.0*)?\b/.test(m[1]));
}

test("кейфрейми не стартують з opacity:0 (headless не домальовує перший кадр)", () => {
  const css = stripComments(readCss());
  const blocks = extractKeyframeBlocks(css);
  for (const { name, body } of blocks) {
    assert.ok(
      !startsInvisible(body),
      `@keyframes ${name} стартує з opacity:0 — так дропдаун приїжджав ` +
        `порожнім у headless-знімку прототипу; видимість анімації мусить ` +
        `стартувати не з нуля`
    );
  }
});

/* ===================================================================
   C. Сітка висот нового словника оболонки — 24 / 28 / 32 / 46
   -------------------------------------------------------------------
   Звужено НАВМИСНО супроти першої чернетки правила: там з девʼяти спрацювань
   половина була хибними — `.cv-vpseg svg{height:16px}` (розмір ІКОНКИ, не
   висота цілі), `.cv-dot{height:6px}` (декоративна крапка сталого розміру,
   не контрол) і одне спрацювання на текст усередині коментаря. Охоронець, що
   бреше при першому законному використанні, знімають — і захист зникає.

   Тому сітка стереже ЛИШЕ новий словник оболонки, який приніс План B:
   .ctl, .seg, .icob, .dd-item, .cm-, .row. Легасі «.cv- та .pp-» — ВИКЛЮЧЕНІ
   свідомо: їх переписує План B, а ганятись за висотами, які самі скоро
   зникнуть, — робота в кошик (і саме там сьогодні лежать усі "46/24/30/34/
   28/18/16/6" смуги — вони живі, але поза межею цього охоронця).

   ⚠️ ЧОМУ ТУТ ЧИТАЮТЬСЯ ТОКЕНИ, А НЕ ЛИШЕ ЧИСЛА. Перша редакція міряла
   ТІЛЬКИ літеральний `height:NNpx` — і рівно з приходом Плану B перестала
   міряти будь-що: усі висоти нового словника стали токенами
   (`.ctl{height:var(--h-ctl)}`, `.seg button`/`.row`/`.row-caret`/
   `.row-more`/`.icob{height:var(--h-sm)}`), літеральних px-висот на цих
   селекторах не лишилось НІ ОДНОЇ, і масив спрацювань був порожній ЗА
   ПОБУДОВОЮ. Передрелізний аудит це виміряв: вивів за сітку ОДРАЗУ ВСІ три
   висоти (`--h-ctl:41px; --h-sm:37px; --h-xs:19px`) — тобто кожен контрол
   смуги, панелі й дерева одночасно — і файл дав 4 ok / 0 fail. Живий
   інваріант «ціль не менша за 28px» теж пропускав: 41 і 37 його
   задовольняють. Тому сітка тепер РОЗКРИВАЄ токен у число й міряє обидві
   форми запису — і рахує ЗМІРЯНІ висоти, а не розглянуті селектори (див.
   свідка в кінці тесту: попередній рахував саме селектори й тому мовчки
   підтверджував вакуумний прохід). */

const ALLOWED_HEIGHTS = new Set([24, 28, 32, 46]);
const NEW_PREFIXES = ["ctl", "seg", "icob", "dd-item", "cm-", "row"];
const LEGACY_PREFIXES = ["cv-", "pp-"];

/**
 * Кожен `--імʼя: NNpx` із `:root` — у числах.
 *
 * Беремо ВСІ px-токени, не лише родину `--h-*`: правило нового словника може
 * написати `height:var(--panel-w)`, і така висота мусить бути ЗМІРЯНА
 * (246px — поза сіткою), а не тихо пропущена як «незнайоме імʼя». Саме
 * «тихо пропущена» і було дефектом першої редакції, лише в іншій формі.
 *
 * `:root` розбираємо не жадібним `{…}` свідомо: коментарі вже вирізані
 * (`stripComments` кличеться до цього), а вкладених блоків у `:root` немає —
 * тож перша `}` і є кінцем блоку.
 */
function rootPxTokens(css) {
  const out = new Map();
  const root = css.match(/:root\s*\{([^{}]*)\}/);
  if (!root) return out;
  for (const m of root[1].matchAll(/--([\w-]+)\s*:\s*([\d.]+)px/g)) out.set(m[1], Number(m[2]));
  return out;
}

function classNames(selector) {
  return [...selector.matchAll(/\.([a-zA-Z0-9_-]+)/g)].map((m) => m[1]);
}
function startsWithAny(name, prefixes) {
  return prefixes.some((p) => name.startsWith(p));
}
function isNewVocab(names) {
  return names.some((n) => startsWithAny(n, NEW_PREFIXES));
}
function isLegacy(names) {
  return names.some((n) => startsWithAny(n, LEGACY_PREFIXES));
}
function isNestedSvgSelector(sel) {
  // «.ctl--probe svg» — розмір ІКОНКИ всередині контролу, не висота самого
  // контролу. Дивимось, що ОСТАННІЙ простий селектор ланцюжка — тег svg.
  return /(^|[\s>+~])svg$/i.test(sel);
}
function isDotSelector(names) {
  // Декоративна крапка сталого розміру (`.cv-dot`, і будь-який майбутній
  // «*-dot» у новому словнику) — не елемент керування, не мета цієї сітки.
  return names.some((n) => n === "dot" || /-dot$/.test(n));
}

/* Окремий охоронець на САМІ значення токенів — і він стоїть ПЕРШИМ свідомо.
   Родина `--h-*` за іменем І Є сіткою висот: токен цієї родини поза сіткою
   є дефектом незалежно від того, хто його читає, а якщо колись знадобиться
   висота ПОЗА сіткою (легасі-картка `.cv-card-head` тримає свої 34px
   літералом), вона не сміє називатись `--h-*`.

   Прохід по селекторах нижче ловить ту саму мутацію іншим шляхом — через
   розкриття токена в правилі. Дві дороги до одного факту тут не дубль:
   перша падає з іменем ТОКЕНА («сітка зламана в джерелі»), друга — з іменем
   СЕЛЕКТОРА («ось хто це читає»), і повідомлення про причину різні. */
test("токени висот у :root самі лежать у сітці 24/28/32/46", () => {
  const tokens = rootPxTokens(stripComments(readCss()));
  const hs = [...tokens].filter(([name]) => /^h-/.test(name));
  assert.ok(hs.length >= 3,
    `у :root знайдено лише ${hs.length} токенів родини --h-* — регексп/блок `
      + `:root зламані, а не «сітка чиста»`);
  /* `--h-tabs` (0.25.0) — висота РЯДКА вкладок над смугою, а не контрола: у сітку контролів не входить. */
  const bad = hs.filter(([name, px]) => name !== "h-tabs" && !ALLOWED_HEIGHTS.has(px))
    .map(([name, px]) => `--${name}:${px}px`);
  assert.deepEqual(bad, [],
    `токени родини --h-* поза сіткою (24/28/32/46):\n${bad.join("\n")}`);
});

test("нові класи оболонки тримають висоту в сітці 24/28/32/46", () => {
  const css = stripComments(readCss());
  const tokens = rootPxTokens(css);
  const violations = [];
  const blind = [];
  let measuredHeights = 0;

  // Спрощений парсер «селектор{тіло}» без вкладених блоків — CSS проєкту
  // сьогодні не має @media/@supports навколо цього словника; кейфрейми (єдиний
  // вкладений випадок) перевіряються окремо в розділі B саме через це.
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const rawSelector = m[1].trim();
    const body = m[2];
    for (const single of rawSelector.split(",").map((s) => s.trim()).filter(Boolean)) {
      const names = classNames(single);
      if (names.length === 0) continue;   // теги, *, :root — не словник оболонки
      if (isLegacy(names)) continue;      // .cv-*/.pp-* — межа Плану B, не ця сітка
      if (!isNewVocab(names)) continue;   // не з нового словника — не наша турбота

      if (isNestedSvgSelector(single)) continue; // розмір іконки, не ціль
      if (isDotSelector(names)) continue;         // декоративна крапка

      /* Негативний lookbehind відсікає line-height/max-height/min-height —
         це ІНШІ властивості, а не «height» з нетиповим написанням. Дві
         форми запису в одному регекспі: літеральні px і `var(--токен)`.
         Форми БЕЗ числа (`height:100%`, `auto`, `calc(…)`) не збігаються ні
         з тією, ні з тією, і це свідома межа: відсоток і `auto` — не
         значення сітки, а «займи батька» (у новому словнику таких сьогодні
         нема; три `height:100%` у файлі — рамка й картка легасі та
         `.prog i`). */
      for (const hm of body.matchAll(
        /(?<![-\w])height\s*:\s*(?:([\d.]+)px|var\(\s*--([\w-]+)\s*\))/gi)) {
        const [, lit, tok] = hm;
        let px = null;
        let shown = "";
        if (lit !== undefined) {
          px = Number(lit);
          shown = `height:${lit}px`;
        } else if (tokens.has(tok)) {
          px = tokens.get(tok);
          shown = `height:var(--${tok}) → ${px}px`;
        } else {
          /* Токен, якого в `:root` немає (або чиє значення не в px): зміряти
             його неможливо. Мовчки пропустити означало б вернути рівно той
             дефект, через який ця сітка й переписана, — тому це спрацювання,
             а не пропуск. */
          blind.push(`«${single}»: height:var(--${tok}) — у :root немає такого px-токена`);
          continue;
        }
        measuredHeights += 1;
        if (!ALLOWED_HEIGHTS.has(px)) {
          violations.push(`«${single}»: ${shown} поза сіткою (24/28/32/46)`);
        }
      }
    }
  }

  assert.deepEqual(
    violations, [],
    `висоти нового словника оболонки виходять за сітку:\n${violations.join("\n")}`
  );
  assert.deepEqual(
    blind, [],
    `висота нового словника, яку сітка не може зміряти:\n${blind.join("\n")}`
  );

  /* Незалежний свідок проти вакуумного проходу — за зразком пари
     rawCalls/used у tests/icons.test.mjs.

     ⚠️ Свідок рахує ЗМІРЯНІ ВИСОТИ, а не розглянуті селектори. Попередній
     рахував саме селектори (`consideredSelectors`) — і тому був істинний
     навіть тоді, коли жодної висоти не зміряно ні разу: селектори нового
     словника в CSS були, прохід їх бачив, отже `> 0`, отже «все гаразд».
     Свідок, який зеленіє при нулі вимірів, не свідок, а зайва впевненість:
     саме він і додав ваги порожньому `violations` під час аудиту.

     Тому вимога тепер пряма: якщо новий словник у CSS є (найпростіший
     ДРУГИЙ регексп, без урахування легасі/svg/dot-винятків), то хоч одну
     висоту сітка мусила ЗМІРЯТИ. Нуль вимірів при живому словнику — це не
     «висот поза сіткою нема», а «сітка нічого не бачить». */
  const rawNewVocabHits = (css.match(/\.(?:ctl|seg|icob|dd-item|cm-|row)[\w-]*/g) || []).length;
  assert.ok(
    rawNewVocabHits === 0 || measuredHeights > 0,
    `у CSS вже є ${rawNewVocabHits} згадок нового словника оболонки, а сітка `
      + `висот не зміряла ЖОДНОЇ висоти — регексп/фільтр зламані, а не `
      + `«нема висот поза сіткою»`
  );
});

/* ===================================================================
   Обрізання крошки — рівно там, де воно дозволене
   -------------------------------------------------------------------
   Довга назва задачі малювалась поверх сусідів (скріншот власника 09.09.2026):
   `max-width` стискає БОКС, а `overflow`+`text-overflow` жили лише в `.ctl .txt`
   і `.txt--soft`, тоді як плоска крошка навмисно не `.ctl` (v1.30.0). Фарбу
   стереже живий тест (`tests/live/ext-shell.test.mjs`).

   Тут — ЗВОРОТНИЙ бік, який фарбою не перевірити: обрізання не сміє розʼїхатись
   на всі плоскі крошки. `.crumb--flat .txt` і `.txt--fix` покривають ТЕГ
   ІТЕРАЦІЇ («Іт.3»), а «тег не обрізається НІКОЛИ» — несучий інваріант крошки:
   саме він відповідає на питання, яку версію бачить глядач. Негативний
   інваріант живим рендером не доводиться (не намалювати те, чого немає), тому
   правило читаємо з файла.
   =================================================================== */
test("обрізання тексту не висить на плоскій крошці загалом і не на .txt--fix", () => {
  const css = stripComments(readCss());
  const bad = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const [, sel, body] = m;
    if (!/text-overflow\s*:\s*ellipsis/.test(body)) continue;
    const s = sel.trim();
    if (/\.crumb--flat\s+\.txt\s*$/.test(s) || /\.txt--fix\s*$/.test(s)) {
      bad.push(s);
    }
  }
  assert.deepEqual(bad, [],
    `обрізання накрило тег ітерації — «Іт.N» зникне рівно там, де місця мало:\n${bad.join("\n")}`);
});

/* ===================================================================
   E. Кожен клас, який малює ДОКУМЕНТ, стилізований у ЙОГО таблиці стилів
   -------------------------------------------------------------------
   Список класів НЕ переписаний руками. Класи звіту знімаються з РЕЗУЛЬТАТУ
   справжніх рендерерів (`reportHTML` кличеться тут же, на
   пейлоадах нижче), класи вкладки «Тюнер» — регекспом по `shell-inspect.js`.
   Так завтрашній новий клас сам потрапляє під перевірку, а не лишається
   нестилізованим до першого живого скріншота.

   ⚠️ ТАБЛИЦЬ СТИЛІВ ДВІ, і це не повнота заради повноти. `insp-report.js`
   монтується у ДВА документи (його ж шапка): у праву панель оболонки, яка
   бере `app/styles.css`, і в shadow-корінь оверлея на сторінці БЕЗ канваса,
   який бере літерал `STYLE` з `app/vendor/inspector.js`. До 18.09.2026 тут
   сканувався лише `styles.css` — і охоронець був СТРУКТУРНО сліпий на другий
   документ у обидва боки: не бачив ні класів, намальованих там без правил
   (`.insp-num`/`.insp-pick`/`.insp-unit`), ні правил, залишених там без
   розмітки (`.insp-kind*`). Обидві вади сиділи в релізі зеленими. Це той
   самий укус, який шапка цього ж розділу описувала для ФАЙЛІВ («список, який
   треба доповнювати руками, забудуть»), лише відтворений для таблиць стилів.

   ⛔ НАБОРИ КЛАСІВ У ДВОХ ДОКУМЕНТІВ РІЗНІ, і зводити їх до спільного не
   можна. Ручки тюнера (`tunable`, див. `reportHTML`) малюються лише там, де
   їх є кому провести, тобто в оболонці. Тому перевірка формулюється так: КОЖЕН клас, який ЦЕЙ
   документ справді малює, має правило в ТІЙ таблиці, яку цей документ читає.
   Спільний список зробив би одне з двох — або вимагав би від оверлея правил
   під розмітку, якої в ньому немає, або пропускав би ручки оболонки.

   Свідки. Кожен закриває свій спосіб мовчки позеленіти:
     · `classes.size > 0` на кожному наборі — зламаний екстрактор інакше
       пройшов би як «нема класів, нема що перевіряти»;
     · витягнутий STYLE мусить містити хоч `.insp-spec` — регексп, що вхопив
       не той шматок файла, інакше віддав би порожню таблицю, у якій «усе
       гаразд» за побудовою;
     · `documents === 2` літералом — обірваний перелік документів інакше
       підтвердив би сам себе (той самий прийом, що `scanned === 2` раніше);
     · набір, знятий із РЕНДЕРУ, звіряється з вокабуляром, знятим із ТЕКСТУ
       `insp-report.js`: клас, дописаний у гілку, якої пейлоади не проходять,
       інакше лишився б поза перевіркою — тобто рендер-підхід повернув би ту
       саму дірку «забутого списку», лише з іншого боку.
   =================================================================== */
const OVERLAY_JS = path.join(APP, "vendor", "inspector.js");

/** Таблиця стилів shadow-кореня оверлея — літерал `STYLE` у `inspector.js`.
 *  Дістати її виконанням модуля не можна: він чіпає `document` уже на
 *  імпорті, тобто в node не піднімається зовсім. */
function readOverlayCss() {
  const js = readFileSync(OVERLAY_JS, "utf8");
  const m = js.match(/const STYLE = `([\s\S]*?)`;/);
  assert.ok(m, "у inspector.js не знайдено літерала STYLE — оверлей лишився "
    + "без таблиці стилів, або змінилось її ім'я");
  assert.ok(m[1].includes(".insp-spec"),
    "витягнутий STYLE не містить навіть .insp-spec — регексп ухопив не той "
    + "шматок файла, і далі перевіряти нічого");
  return m[1];
}

function classesInMarkup(html) {
  const classes = new Set();
  for (const m of html.matchAll(/class="([^"]*)"/g)) {
    for (const c of m[1].trim().split(/\s+/)) {
      if (c) classes.add(c);
    }
  }
  return classes;
}

/* Пейлоади, зібрані так, щоб пройти КОЖНУ гілку розмітки звіту: три крапки
   вироку, здогадну підказку, застереження, смугу відступів (стрілки), пару з
   підписами, широкий рядок з іменем властивості, число з одиницею й без,
   суцільний колір (пікер), напівпрозорий колір (зразок), усічений текст і
   накручене поле. Чи справді вони покривають усе, перевіряє не око, а свідок
   про вокабуляр нижче. Поля — рівно ті, що описує докстрінг `reportHTML`.

   ⚠️ Смуга відступів і пари приїхали сюди з T-39 разом із розкладкою: без
   ПОВНОЇ четвірки margin-* пейлоад не намалював би ні `insp-quad`, ні
   `insp-lbl`, і охоронець мовчки лишився б сліпим на дві третини нової
   розмітки. */
const DECL = (o) => ({ prop: "gap", computed: "8px", raw: "var(--sp-2)",
  token: "--sp-2", tokenValue: "8px", verdict: "token", hint: [], ...o });

/* T-40: два нових вироки й дорога назад. Без цих полів жоден пейлоад не
   заходив би в гілки `insp-dot--offds`/`insp-dot--over`/`insp-snap`, і
   охоронець мовчки лишився б сліпим на всю нову розмітку — рівно той укус,
   який шапка цього розділу вже описує. `dsInfo` теж у ОБОХ випадках: є ДС і
   немає ДС — це два різні рядки, і другий (напрямок `seo`) малюється рівно
   тоді, коли перевіряти нічого. */
const REPORT_CASES = [
  { crumbs: ["body", "div.card"], blocked: true, partial: true,
    dsInfo: { profile: "united", known: true,
      commit: "5f7050d77ab5fe6ce9d0185bff703748202ede9f", figma: "UI LIBRARY v1.4" },
    groups: {
      box: [
        DECL({ prop: "margin-top", computed: "0px", verdict: "unlinked", token: null }),
        DECL({ prop: "margin-right", computed: "0px", verdict: "unlinked", token: null }),
        DECL({ prop: "margin-bottom", computed: "28px", verdict: "hardcode", token: null,
          hint: [{ name: "--sp-3", tier: "used" }, { name: "--gap-3", tier: "shape" }] }),
        DECL({ prop: "margin-left", computed: "0px", verdict: "unknown", token: null }),
        DECL({ prop: "padding-top", computed: "24px", verdict: "hardcode", token: null }),
        DECL({ prop: "padding-right", computed: "0px", verdict: "unlinked", token: null }),
        DECL({ prop: "padding-bottom", computed: "0px", verdict: "unlinked", token: null }),
        DECL({ prop: "padding-left", computed: "0px", verdict: "unlinked", token: null }),
      ],
      flex: [
        /* Токен, якого ДС не знає, — і з дорогою назад: у ДС знайшовся токен
           із тим самим значенням. */
        DECL({ prop: "gap", computed: "8px", raw: "var(--bf-gap)", token: "--bf-gap",
          tokenValue: "8px", verdict: "off-ds",
          hint: [{ name: "--spacings-8", tier: "shape", ds: true }],
          snap: { token: "--spacings-8", value: "8px" } }),
        /* Перевизначене ім'я з ДС — найтяжчий вирок, і теж із дорогою назад,
           але вона тут МІНЯЄ значення: повертає приписане дизайн-системою. */
        DECL({ prop: "align-items", computed: "#fbfbff", raw: "var(--color-neutral-alpha-100)",
          token: "--color-neutral-alpha-100", tokenValue: "#fbfbff",
          verdict: "overridden", ds: ["#FBFBFF1A"],
          snap: { token: "--color-neutral-alpha-100", value: "#FBFBFF1A" } }),
      ],
      layout: [
        DECL({ prop: "display", computed: "block", verdict: "hardcode", token: null }),
        DECL({ prop: "width", computed: "676.8px", verdict: "unlinked", token: null }),
        DECL({ prop: "height", computed: "261.5px", verdict: "unlinked", token: null }),
      ],
      type: [
        DECL({ prop: "font-family", computed: "e-Ukraine, system-ui, sans-serif" }),
        DECL({ prop: "font-size", computed: "44px", verdict: "hardcode", token: null }),
        DECL({ prop: "font-weight", computed: "700", verdict: "hardcode", token: null }),
        DECL({ prop: "line-height", computed: "47.5px", verdict: "unknown", token: null }),
        DECL({ prop: "letter-spacing", computed: "-0.88px", verdict: "unlinked", token: null }),
      ],
    },
    tuned: { "margin-bottom": { from: "0px", to: "28px" } } },
  { crumbs: ["body"], blocked: false, partial: false,
    dsInfo: { profile: "seo", known: false, commit: "", figma: "" },
    groups: { color: [
      DECL({ prop: "color", computed: "rgb(26, 28, 31)", verdict: "unlinked", token: null }),
      DECL({ prop: "background-color", computed: "rgba(0, 0, 0, 0.5)",
        verdict: "unlinked", token: null }),
    ] } },
];

/** Що НАСПРАВДІ малює документ: рендеримо тими самими викликами, якими його
 *  малює сам документ, і знімаємо класи з результату. */
function renderedClasses({ tunable }) {
  const out = new Set();
  for (const p of REPORT_CASES) {
    for (const c of classesInMarkup(reportHTML(p, { tunable }))) out.add(c);
  }
  return out;
}

/* Два документи, кожен зі своїм рендером і своєю таблицею.
   `extra` — рендерери, які малюють ЛИШЕ в цей документ (вкладка «Тюнер» —
   розмітка `shell-inspect.js`); з них класи знімаються з тексту, як і
   раніше. */
/** Класи, які малює нова панель властивостей: усі гілки моделі (повна, найменша, grid, розкриті сторони). */
function panelClasses() {
  const out = new Set();
  const full = FULL_MODEL();
  const grid = FULL_MODEL();
  grid.layout = { kind: "grid", dir: "row", ax: -1, ay: -1, gap: full.layout.gap };
  const sides = FULL_MODEL();
  const side = (p) => ({ ...full.size.w, props: [p], id: p });
  sides.spacing = { ...sides.spacing, sides: true, forced: true,
    pad: { top: side("padding-top"), right: side("padding-right"), bottom: side("padding-bottom"), left: side("padding-left") },
    mar: { top: side("margin-top"), right: side("margin-right"), bottom: side("margin-bottom"), left: side("margin-left") } };
  for (const m of [full, MIN_MODEL(), grid, sides]) {
    for (const c of classesInMarkup(panelHTML(m))) out.add(c);
  }
  return out;
}

const DOCUMENTS = [
  { name: "права панель оболонки", css: () => readCss(),
    render: null, panel: true,
    /* `insp-hint` малює не інспектор, а панель «Коментарі» (`comments-view.js`), яка ділить із ним CSS: перелік
       явний, бо класи з сирця шаблонів `comments-view.js` екстрактор читає з шумом. */
    alsoDrawn: ["insp-hint"],
    extra: [path.join(APP, "shell-inspect.js"), path.join(APP, "insp-panel.js")] },
  { name: "shadow-корінь оверлея (сторінка без канваса)", css: readOverlayCss,
    render: { tunable: false }, extra: [] },
];

/** Усе, що документ справді малює: рендер плюс розмітка «своїх» файлів. */
function drawnClasses(doc) {
  const drawn = doc.render ? renderedClasses(doc.render) : new Set();
  for (const file of doc.extra) {
    for (const c of classesInMarkup(readFileSync(file, "utf8"))) drawn.add(c);
  }
  if (doc.panel) for (const c of panelClasses()) drawn.add(c);
  for (const c of doc.alsoDrawn || []) drawn.add(c);
  return drawn;
}

test("кожен клас, який малює документ, має правило в ЙОГО таблиці стилів", () => {
  let documents = 0;
  for (const doc of DOCUMENTS) {
    /* `stripComments` ОБОВʼЯЗКОВИЙ, і це не гігієна. Перевірка «є правило» —
       це підрядок `.ім'я`, а коментар, який ПЕРЕЛІЧУЄ класи (у STYLE оверлея
       якраз такий: «чого тут немає і чому»), дає цей підрядок без жодного
       правила. Без цього рядка мутація «вернути ручки в оверлей» лишалась
       зеленою: `.insp-num` знаходився в тексті коментаря. Той самий укус, що
       вже описаний у шапці `stripComments` для сітки висот. */
    const css = stripComments(doc.css());
    const classes = drawnClasses(doc);
    assert.ok(classes.size > 0,
      `рендер для «${doc.name}» не дав жодного класу — зламані пейлоади чи `
        + "екстрактор, а не «стилізувати нічого не треба»");
    const missing = [...classes].filter((c) => !css.includes(`.${c}`));
    assert.deepEqual(
      missing, [],
      `«${doc.name}» малює класи без правил у своїй таблиці: `
        + `${missing.map((c) => `.${c}`).join(", ")}`
    );
    documents += 1;
  }
  /* Підлога ЛІТЕРАЛОМ, а не `DOCUMENTS.length`: інакше порожній (чи
     обірваний) перелік сам себе й підтвердив би — той самий свідок, що в
     охоронці «панель не читає DOM макета» (`tests/shell-inspect.test.mjs`). */
  assert.equal(documents, 2,
    `просканованих документів ${documents}, а не 2 — перелік порожній або обірваний`);
});

/** Імена класів словника `insp-*`, які таблиця справді СТИЛІЗУЄ. Коментарі
 *  зрізає викликач: перелік класів у коментарі — це не правило. */
function styledInspClasses(css) {
  return new Set([...css.matchAll(/\.(insp-[\w-]+)/g)].map((m) => m[1]));
}

test("у таблиці немає правил під розмітку, якої цей документ не малює", () => {
  /* ЗВОРОТНИЙ бік перевірки вище, і він не симетрична забаганка. Правило без
     розмітки не ламає екран — воно бреше ЧИТАЧЕВІ: у STYLE оверлея три
     правила `.insp-kind*` стояли з коментарем «ті самі три рівні, що в панелі
     оболонки», хоча бейдж виду виміру малює `measureHTML`, якого цей файл не
     імпортує взагалі. Паритет, якого не могло існувати, — і наступний читач
     добудовує його далі.

     Межа перевірки — словник `insp-*`, тобто рівно те, що малюють спільні
     рендерери звіту й панель інспектора. Решта обох таблиць (свій хром
     оверлея — `.panel`, `.rlab`, `.hidden`; уся оболонка в `styles.css`)
     малюється іншими файлами, і вимагати для неї того самого тут означало б
     не знахідку, а фальштривогу. */
  let documents = 0;
  for (const doc of DOCUMENTS) {
    const styled = styledInspClasses(stripComments(doc.css()));
    const drawn = drawnClasses(doc);
    assert.ok(styled.size > 0,
      `у таблиці «${doc.name}» не знайдено жодного правила insp-* — регексп зламаний`);
    const dead = [...styled].filter((c) => !drawn.has(c)).sort();
    assert.deepEqual(
      dead, [],
      `у таблиці «${doc.name}» лежать правила під розмітку, якої цей документ `
        + `не малює: ${dead.map((c) => `.${c}`).join(", ")}`
    );
    documents += 1;
  }
  assert.equal(documents, 2,
    `просканованих документів ${documents}, а не 2 — перелік порожній або обірваний`);
});

test("жоден клас звіту не лишився поза рендером — пейлоади покривають розмітку", () => {
  /* Зворотний бік рендер-підходу. Класи знімаються з РЕЗУЛЬТАТУ, тож клас,
     дописаний у гілку, якої жоден пейлоад не проходить, мовчки лишився б поза
     перевіркою вище — рівно та «забута руками» дірка, від якої весь розділ і
     лікується. Тому вокабуляр рендера звіряється з вокабуляром ТЕКСТУ.

     Регексп по тексту читає й коментарі, тож приклад атрибута `class` у
     докстрінгу теж стане «класом» — і це не вада, а причина, чому в
     `insp-report.js` імена класів виписані повними літералами в кожній гілці
     (див. коментарі в `row()` і `dotHTML()`). Розійшлись набори — виправляти
     треба пейлоади, а не цю перевірку. */
  const source = classesInMarkup(
    readFileSync(path.join(APP, "vendor", "insp-report.js"), "utf8"));
  assert.ok(source.size > 0, "екстрактор не знайшов жодного class=\"…\" у insp-report.js");
  /* `reportHTML` вміє `tunable: true` (ручки) і `tunable: false` (власна панель оверлея) — вокабуляр звіряється
     з ОБОМА гілками рендера, а не з однією. Бейджа виміру більше немає (лінійку прибрано, 0.29.0). */
  const rendered = new Set([
    ...renderedClasses({ tunable: true }),
    ...renderedClasses({ tunable: false }),
  ]);
  const unrendered = [...source].filter((c) => !rendered.has(c)).sort();
  assert.deepEqual(unrendered, [],
    "у розмітці insp-report.js є класи, яких не малює ЖОДЕН пейлоад: "
      + `${unrendered.join(", ")} — допиши пейлоад у REPORT_CASES, `
      + "інакше ці класи не перевіряє ніхто");
});

test("ручки тюнера існують РІВНО в тому документі, де їх є кому провести", () => {
  /* Пряме формулювання вади, окремо від перевірки правил: нестилізована ручка
     — це наслідок, а вада — сама мертва ручка. На голій сторінці макета їх
     стояло 15 крутилок і 3 пікери, і жодна ні на що не реагувала: проводка
     (`BAR_ACTIONS`) живе в батьківському вікні, а оверлей — в іншому
     документі. Підроблена ручка гірша за чесний текст (докстрінг `NUMERIC`).

     ⚠️ РУЧОК ТУТ ДВІ, А НЕ ТРИ (T-39). `insptuneoff` — «скинути цю правку»,
     і жила вона на перекресленому старому значенні в рядку звіту. Старе
     значення пішло з рядка разом із 28px висоти, які воно коштувало, а
     скидання однієї правки лишилось РІВНО одне — хрестик у списку змін
     (`insptunedrop`, розмітка `app/shell-inspect.js`). Тобто зник не спосіб
     скинути, а другий вхід у нього; перелік звужено свідомо, а не «щоб
     проходило». */
  const KNOBS = ["insptune", "insptunecolor"];
  const panel = panelHTML(FULL_MODEL());
  const overlay = REPORT_CASES.map((p) => reportHTML(p, { tunable: false })).join("");
  for (const act of KNOBS) {
    assert.ok(panel.includes(`data-act="${act}"`),
      `панель оболонки втратила ручку ${act} — пейлоади чи рендерер зламані`);
    assert.ok(!overlay.includes(`data-act="${act}"`),
      `оверлей малює ручку ${act}, яку нікому провести`);
  }
  assert.ok(!panel.includes("insptuneoff"),
    "скидання однієї правки мусить лишитись одне — у списку змін підвалу");
  assert.ok(overlay.includes(`class="insp-txt">676.8px<`),
    "замість ручки оверлей мусить показати ЧЕСНИЙ ТЕКСТ значення");
  assert.ok(!overlay.includes("<input"),
    "у shadow-корені оверлея не сміє лишитись ЖОДНОГО поля вводу: там немає "
      + "ні делегації, ні моделі тюнера, тобто нікому їх слухати");
});

test("жоден клас insp-panel.js не лишився поза фікстурами — вокабуляр сирця = вокабуляр рендеру", () => {
  const source = classesInMarkup(readFileSync(path.join(APP, "insp-panel.js"), "utf8"));
  assert.ok(source.size > 10, "екстрактор не знайшов класів у insp-panel.js");
  const unrendered = [...source].filter((c) => !panelClasses().has(c)).sort();
  assert.deepEqual(unrendered, [],
    `у insp-panel.js є класи, яких не малює жодна фікстура: ${unrendered.join(", ")} — допиши фікстуру в tests/_insp-fixtures.mjs`);
});

/* B2 (ревʼю): напрямні рівнів — це background-image рядка; шорткат
   `background` на hover/виділенні скидає його, і напрямні зникають саме там,
   де око по них веде. Лише `background-color`. */
test("стани рядка дерева не скидають напрямні (background-color, не background)", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
  for (const sel of [".row:hover", ".row--sel", ".row--multi", ".row--multi:hover"]) {
    const m = new RegExp(`(^|\\n)${sel.replace(/[.:]/g, "\\$&")}\\{([^}]*)\\}`).exec(css);
    assert.ok(m, `правила ${sel} немає`);
    assert.doesNotMatch(m[2], /(^|;)\s*background\s*:/, `${sel} скидає напрямні шорткатом background`);
  }
});

test("«Усі шари» — ціль не нижча за --h-sm і читабельний колір", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
  const m = /\n\.crumb-all\{([^}]*)\}/.exec(css);
  assert.ok(m, ".crumb-all без правила");
  assert.match(m[1], /min-height:var\(--h-sm\)/);
  assert.match(m[1], /align-items:center/);
  assert.doesNotMatch(m[1], /color:var\(--sel\)/, "#025CFF на --s1 не дає 4.5:1 для 11px");
});

test("фільтр має видиме кільце фокуса", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.tree-filter:focus-within\{outline:2px solid var\(--sel\)/);
});

/* B4 Step 0: «відкрита» (row--sel) і «вибране» (row--multi) не можуть виглядати
   однаково, інакше множинний вибір ховає, яка сторінка відкрита. */
test("row--sel і row--multi розрізняються: смужка проти тла", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
  const rule = (sel) => new RegExp(`(^|\\n)${sel.replace(/[.:]/g, "\\$&")}\\{([^}]*)\\}`).exec(css)?.[2] ?? "";
  const sel = rule(".row--sel"), multi = rule(".row--multi");
  assert.match(sel, /box-shadow:\s*inset/, "відкрита сторінка — смужка");
  assert.doesNotMatch(sel, /background-color/, "відкрита не фарбує тло — це знак вибраного");
  assert.match(multi, /background-color/);
  assert.doesNotMatch(multi, /box-shadow/);
});

/* B7: поле фільтра — ціль кліку на всю висоту рамки (живий `shell` №6 міряє ≥28px). */
test("фільтр: input розтягнутий на висоту рамки, відступ переїхав в input", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
  const rule = (sel) => new RegExp(`(^|\\n)${sel.replace(/[.\s]/g, (c) => `\\${c}`)}\\{([^}]*)\\}`).exec(css)?.[2] ?? "";
  const inp = rule(".tree-filter input");
  assert.match(inp, /align-self:stretch/);
  assert.match(inp, /margin:-1px 0/, "мінус рамка: інакше input 26px");
  assert.match(inp, /padding:0 8px 0 0/);
  assert.match(rule(".tree-filter"), /padding:0 0 0 8px/);
});

/* ===================================================================
   0.25.0 — макет рядка вкладок і острівця
   ------------------------------------------------------------------
   Висоти верху — лише токенами (`--h-top` = вкладки + смуга); цілі кліку
   ≥ 28px; рядок вкладок не розпирає вікно; шар острівця — між віджетами
   й смугою. Кожну перевірку доведено мутацією одного рядка CSS.
   =================================================================== */
function cssRuleBodies(css, sel) {
  const esc = sel.replace(/[.#:[\]()>+~*]/g, "\\$&");
  const re = new RegExp(`(?:^|[}{;\\n])\\s*${esc}\\s*\\{([^}]*)\\}`, "g");
  return [...stripComments(css).matchAll(re)].map((m) => m[1]);
}
function cssRule(css, sel) {
  const bodies = cssRuleBodies(css, sel);
  assert.ok(bodies.length, `у styles.css немає правила ${sel}`);
  return bodies.join(";");
}
function cssPx(body, prop) {
  const m = new RegExp(`(?:^|[;\\s])${prop}\\s*:\\s*(\\d+(?:\\.\\d+)?)px`).exec(body);
  return m ? Number(m[1]) : null;
}

test("жоден селектор не фіксує верх числом 46px — лише токени висот", () => {
  const css = stripComments(readCss());
  const hits = css.split("\n").filter((l) => /\btop\s*:\s*46px/.test(l));
  assert.deepEqual(hits, [], `top:46px живе в селекторі: ${hits.join(" | ")}`);
});

test("поверхні під рядками верху стоять на var(--h-top)", () => {
  const css = readCss();
  for (const sel of [".cv-stage", ".cv-canvas", ".pages-panel", ".errbar", ".panel", ".insp", "#tasks-home", ".cn-drawer"]) {
    assert.match(cssRule(css, sel), /top\s*:\s*var\(--h-top\)/, `${sel} не стоїть на var(--h-top)`);
  }
});

test("рядок вкладок: висота — токен, список не розпирає вікно", () => {
  const css = readCss();
  assert.match(cssRule(css, ".tabs"), /(?:^|[;\s])height\s*:\s*var\(--h-tabs\)/);
  const list = cssRule(css, ".tabs-list");
  assert.match(list, /overflow-x\s*:\s*auto/, ".tabs-list не прокручується вбік");
  assert.match(list, /min-width\s*:\s*0/, ".tabs-list без min-width:0 розпирає flex-батька");
});

test("цілі кліку острівця, хрестика вкладки й «Вмістити все» не нижчі за 28px", () => {
  const css = readCss();
  const isl = cssRule(css, ".isl-btn"), x = cssRule(css, ".tab-x"), z = cssRule(css, ".cv-zoom");
  for (const [name, body, props] of [[".isl-btn", isl, ["width", "height"]], [".tab-x", x, ["width", "height"]]]) {
    for (const p of props) {
      const v = cssPx(body, p);
      assert.ok(v !== null && v >= 28, `${name} ${p}: ${v}px < 28px`);
    }
  }
  const zh = Math.max(cssPx(z, "min-height") ?? 0, cssPx(z, "height") ?? 0);
  assert.ok(zh >= 28, `.cv-zoom min-height/height: ${zh}px < 28px`);
});

test("острівець: смужка крізь порожнє пропускає клік, сам острівець його приймає", () => {
  const css = readCss();
  assert.match(cssRule(css, ".cv-hud"), /pointer-events\s*:\s*none/);
  assert.match(cssRule(css, ".island"), /pointer-events\s*:\s*auto/);
});

test("шар острівця: вище за --z-widget, нижче за --z-bar (випадаючі меню його накривають)", () => {
  const css = readCss();
  const z = (n) => Number((new RegExp(`--${n}\\s*:\\s*(\\d+)`).exec(stripComments(css)) || [])[1]);
  const widget = z("z-widget"), bar = z("z-bar");
  assert.ok(widget > 0 && bar > widget, `токени шарів не розібрано: widget=${widget} bar=${bar}`);
  const m = /z-index\s*:\s*calc\(\s*var\(--z-widget\)\s*\+\s*(\d+)\s*\)/.exec(cssRule(css, ".cv-hud"));
  assert.ok(m, ".cv-hud має z-index calc(var(--z-widget) + N)");
  const hud = widget + Number(m[1]);
  assert.ok(hud > widget && hud < bar, `шар острівця ${hud} поза (${widget}, ${bar})`);
});
