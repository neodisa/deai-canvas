/**
 * Живий тест ЗВІРКИ З ДИЗАЙН-СИСТЕМОЮ (T-40).
 *
 * ⛔ Чому ЖИВИЙ, а не юніт. Юніти вже стережуть саму логіку вироку
 * (`tests/ds-check.test.mjs`) — але вся вада, з якої T-40 почався, живе НЕ в
 * логіці, а в дорозі до неї: напрямок задачі лежить у `tasks.json`, його
 * бачить лише сервер, він дописує його параметром до тега інспектора, тег
 * виконується В ДОКУМЕНТІ МАКЕТА, і тільки там `getComputedStyle` знає, у що
 * насправді розкрилась `var()`. Обірви цей ланцюг у будь-якій ланці — і
 * інструмент не впаде: він просто мовчки перестане звіряти, показуючи ті самі
 * зелені крапки. Мовчазна відсутність звірки виглядає рівно як успішна
 * звірка, і побачити різницю можна лише звідси.
 *
 * Мапа «перевірка → запобіжник → що буде, якщо його прибрати» (знята
 * мутаційно):
 *
 *   A (напрямок доїхав) — `?ds=` у `INSPECTOR_TAG` (`serve.py`) і його
 *                         читання з `import.meta.url` (`inspector.js`).
 *                         Прибери будь-що з двох — жодного вироку про ДС не
 *                         буде взагалі, а панель покаже звичайні зелені
 *                         крапки: рівно стан ДО T-40.
 *   B (вигаданий токен) — гілка `off-ds` у `dsVerdict`. Прибери — і
 *                         `--bf-ink` знову зелений, тобто зелений колір знову
 *                         означає лише «автор написав var()».
 *   C (перевизначений)  — гілка `overridden` там же. Це єдиний стан, якого
 *                         око не ловить НІКОЛИ: імʼя з ДС, вжиток
 *                         правильний, а значення інше.
 *   D (звірка з ОГОЛО-  — `tokenDeclared` у `describe` (`inspector-dom.js`).
 *      шеним, не з         Візьми замість нього `computed` — і кожен токен,
 *      обчисленим)         записаний у ДС як `1rem`, стане «перевизначеним»
 *                         на сторінці, де він збігається дослівно.
 *   E (напрямок без ДС) — `known:false` у `ds()` + рядок `insp-note`.
 *                         Прибери словник — і 572 законні змінні лендінга
 *                         стануть «повз ДС»; прибери рядок — і дизайнер
 *                         вирішить, що їх перевірили.
 *   F (дорога назад)    — `snapHTML` + `BAR_ACTIONS.inspsnap`. Прибери — і
 *                         підказка знову стає інертним текстом, тобто
 *                         лишається рівно те питання власника, з якого все
 *                         почалось: «незрозуміло, як повернути до ДС».
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга портів: `node --test` крутить файли паралельно, і спільна база
   дала б колізію. Найвище зайняте — 11290 (`tuner.test.mjs`), тож 11390. */
const PORT_BASE = 11390;
/* Окрема смуга портів для канваса-простору: PORT_BASE + 50 перетинався з figma.test.mjs (11490) при паралельному test:live. */
const SPACE_PORT_BASE = 26000;
const VIEW = { width: 1400, height: 900 };

/**
 * Сторінка, зібрана під чотири вироки одразу. Значення взяті з РЕАЛЬНОЇ ДС
 * (united, коміт знімка), а не вигадані: тест про звірку з ДС, зроблений на
 * вигаданих значеннях, перевіряв би сам себе.
 *
 *   · `--color-primary-400: #025CFF` — токен ДС, значення збігається → 'token';
 *   · `--color-neutral-alpha-100: #fbfbff` — імʼя з ДС, значення інше
 *     (загублена альфа; ДС каже `#FBFBFF1A`) → 'overridden'. Це не вигадана
 *     ситуація: рівно таких у `courts` знайшлось 41;
 *   · `--bf-ink` — вигадана на місці змінна → 'off-ds';
 *   · `#hard` — літерал, що дорівнює значенню токена ДС → 'hardcode' із
 *     дорогою назад.
 */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
:root{
  --color-primary-400:#025CFF;
  --color-neutral-alpha-100:#fbfbff;
  --bf-ink:#123456;
}
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
#wrap{margin:30px;padding:40px;background:#fff;display:flex;gap:24px}
.card{margin:0;padding:16px;background:#eef;width:220px;height:120px}
#ok{color:var(--color-primary-400)}
#over{color:var(--color-neutral-alpha-100)}
#off{color:var(--bf-ink)}
#hard{color:#025CFF}
</style></head><body>
<div id="wrap">
  <p id="ok" class="card">Токен ${id}</p>
  <p id="over" class="card">Перевизначений ${id}</p>
  <p id="off" class="card">Повз ДС ${id}</p>
  <p id="hard" class="card">Хардкод ${id}</p>
</div>
</body></html>`;

async function openInspector(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  await page.click('#bar [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame")
    .contentWindow.CanvasInspector.on === true, null, { timeout: 3000 });
  return page;
}

async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction((s) => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return !!(api.pinned && api.pinned.id === s);
  }, sel.slice(1), { timeout: 3000 });
}

/** Клас крапки вироку в полі — тобто те, що дизайнер бачить очима. */
const dotOf = (page, prop) => page.evaluate((p) => {
  const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
  const dot = f && f.querySelector(".insp-dot");
  return dot ? dot.className : null;
}, prop);

/** Титул поля — усе, чого в самому полі не видно (вирок, приписане ДС). */
const titleOf = (page, prop) => page.evaluate((p) => {
  const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
  return f ? f.getAttribute("title") : null;
}, prop);

/* ⛔ Контракт Deai: статична ДС (`DS_PROFILES` у `ds-tokens.js`) у продукті ПОРОЖНЯ — знімок united лишився в Ліга-репо.
   Токени ДС приходять із простору: роль `tokens` (модуль `css-tokens`) → `GET /api/ds-tokens?space=<id>` → профіль
   `space:<id>`. Значення — з реальної ДС united (як і було), але тепер лежать у CSS-файлі, який читає модуль. */
const TOKENS_CSS = ":root{\n  --color-primary-400: #025CFF;\n  --color-neutral-alpha-100: #FBFBFF1A;\n}\n";

/** Канвас ПРОСТОРУ з увімкненим `css-tokens` і дочекані токени: панель каже «Звірено з токенами простору». */
async function withSpaceCanvas(body) {
  const { dir } = taskFixture({ html: PAGE, pages: ["holovna"] });
  const cssDir = mkdtempSync(path.join(tmpdir(), "dc-live-ds-"));
  const cssFile = path.join(cssDir, "tokens.css");
  writeFileSync(cssFile, TOKENS_CSS);
  const { child, url } = await startServer(null, {
    portBase: SPACE_PORT_BASE,
    spaces: [{ name: "Ds", id: "ds", color: "space-2", tasks: { lab: { dir, title: "Лабораторія" } } }],
  });
  const browser = await chromium.launch();
  try {
    const enabled = await (await fetch(`${url}/api/module-enable`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ space: "ds", id: "css-tokens", settings: { file: cssFile } }),
    })).json();
    assert.equal(enabled.ok, true, JSON.stringify(enabled));
    const page = await openInspector(browser, url);
    await body(page, url);
  } finally {
    await browser.close();
    child.kill();
    rmSync(cssDir, { recursive: true, force: true });
  }
}

/** Токени простору приходять у ФОНІ: чекаємо, поки панель це покаже, інакше вирок читав би порожню ДС. */
const tokensArrived = async (page) => {
  await pin(page, "#ok");
  await page.waitForFunction(() => /Звірено з токенами простору/
    .test(document.querySelector("#insp-panel .insp-note")?.textContent ?? ""), null, { timeout: 8000 });
};

async function withCanvas(profile, body) {
  const { dir } = taskFixture({ html: PAGE, pages: ["holovna"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, profile });
  const browser = await chromium.launch();
  try {
    const page = await openInspector(browser, url);
    await body(page, url, dir);
  } finally {
    await browser.close();
    child.kill();
  }
}

test("напрямок задачі доїжджає в документ макета, і звірка справді йде", async () => {
  await withCanvas("united", async (page) => {
    const info = await page.evaluate(() => document.getElementById("frame")
      .contentWindow.CanvasInspector.report.call(
        document.getElementById("frame").contentWindow.CanvasInspector) || null);
    // звіт без піна — null; питаємо напрямок напряму через тег інспектора
    const src = await page.frameLocator("#frame").locator("head")
      .evaluate(() => Array.from(document.scripts)
        .map((s) => s.src).find((s) => s.includes("inspector.js")) || "");
    assert.ok(src.includes("ds=united"),
      `тег інспектора приїхав без напрямку (${src}) — звірки з ДС не буде `
      + "взагалі, а панель покаже ті самі зелені крапки, що й до T-40");
    assert.equal(info, null);
  });
});

test("три різні вироки на трьох var() — а не одна зелена крапка на всі", async () => {
  await withSpaceCanvas(async (page) => {
    await tokensArrived(page);
    assert.match(await dotOf(page, "color"), /insp-dot--tok\b/,
      "токен ДС із правильним значенням мусить лишитись зеленим");

    await pin(page, "#off");
    assert.match(await dotOf(page, "color"), /insp-dot--offds\b/,
      "--bf-ink немає в ДС: зелена крапка тут і означала б лише «автор "
      + "написав var()» — рівно вада, з якої T-40 почався");
    assert.match(await titleOf(page, "color"), /--bf-ink/);

    await pin(page, "#over");
    assert.match(await dotOf(page, "color"), /insp-dot--over\b/,
      "імʼя з ДС із чужим значенням — найтяжчий вирок: код виглядає "
      + "бездоганно, а поводиться інакше");
    const title = await titleOf(page, "color");
    assert.match(title, /#FBFBFF1A/,
      `титул мусить сказати, ЩО приписує ДС, інакше дизайнер лишається з тим `
      + `самим питанням: ${title}`);
  });
});

test("напрямок без ДС каже про це словами і не звинувачує нікого", async () => {
  await withCanvas("seo", async (page) => {
    await pin(page, "#off");
    const note = await page.evaluate(() => {
      const n = document.querySelector("#insp-panel .insp-note");
      return n ? n.textContent : null;
    });
    assert.ok(note && note.includes("seo"),
      "мовчазна відсутність звірки виглядає рівно як успішна звірка");
    assert.match(await dotOf(page, "color"), /insp-dot--tok\b/,
      "у напрямку без ДС жоден токен не сміє бути позначений «повз ДС»: "
      + "сайтова тема живе поза ДС свідомо");
  });
});

test("крапка вироку веде НАЗАД у ДС — і повернення доїжджає в пакет Клоду",
  async () => {
    await withSpaceCanvas(async (page, url) => {
      await tokensArrived(page);
      await pin(page, "#hard");
      assert.match(await dotOf(page, "color"), /insp-dot--hard\b/);
      const snap = await page.evaluate(() => {
        const b = document.querySelector(
          '#insp-panel .insp-f[data-prop="color"] .insp-snap');
        return b ? { token: b.dataset.token, val: b.dataset.val } : null;
      });
      assert.ok(snap, "хардкод, що дорівнює значенню токена ДС, мусить мати "
        + "дорогу назад — інакше підказка лишається інертним текстом, тобто "
        + "рівно тим, на що скаржився власник");
      assert.equal(snap.token, "--color-primary-400");

      await page.click('#insp-panel .insp-f[data-prop="color"] .insp-snap');
      await page.waitForFunction(() => document
        .querySelector('#insp-panel .insp-f[data-prop="color"][data-tuned]'),
      null, { timeout: 3000 });

      /* ⛔ Найважливіше твердження файла. Пікселі від повернення до токена НЕ
         міняються (токен пропонується саме тому, що значення те саме), тож
         правило «те саме значення — не правка» скинуло б цю правку мовчки:
         дизайнер бачить реакцію, а Клод не отримує замовлення. */
      const body = await (await fetch(`${url}/api/tuner`)).json();
      /* Сервер віддає пакет під ключем `package` — саме в тому вигляді, у
         якому він лежить на диску (`/api/tuner`, `serve.py`). */
      const pkg = body.package || body;
      const edits = (pkg.elements || []).flatMap((e) => e.edits || []);
      const edit = edits.find((e) => e.prop === "color");
      assert.ok(edit, `правка-повернення не доїхала на диск: ${JSON.stringify(pkg)}`);
      /* Значення — те, що ЗАПРОПОНУВАВ інспектор (`data-val` кнопки), а колір —
         без регістру. З 1.41.0 діючий шар токена — прод (`united.prod.css`,
         `#025cff`), він перекриває Figma (`#025CFF`); той самий колір. Тест
         зашивав регістр Figma і червонів на main 1.41.1 при правильному пакеті
         (знайдено прогоном 29.09.2026). Стережене тут — ТОКЕН у пакеті. */
      assert.deepEqual(edit.snap,
        { token: "--color-primary-400", value: snap.val },
        "пакет мусить сказати, що дизайнер вибрав ТОКЕН, а не число: інакше "
        + "Клод впише літерал і додасть ще один хардкод повз ДС");
      assert.equal(snap.val.toLowerCase(), "#025cff");
      assert.equal(pkg.ds.profile, "space:ds");
      assert.equal(pkg.ds.known, true);
    });
  });
