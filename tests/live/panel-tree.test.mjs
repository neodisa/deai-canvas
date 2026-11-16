/**
 * Живі перевірки ДЕРЕВА шарів у справжньому браузері (B7): перший прогін усієї
 * фічі «теки / сторінки / стани» крізь реальні події, а не крізь юніти.
 *
 * Чому живий: юніти (`tree-model`, `tree-actions`) стережуть арифметику, а
 * вади, які знаходять ревʼю B1–B5, сидять у ПРОВОДЦІ: жест → перемальовка →
 * запит → rev → перемальовка. Кожна перевірка нижче — одна така вада.
 *
 * Мапа «перевірка → що перевіряє»:
 *   A ⌘G групує два стани, тека приймає стан кидком «всередину»
 *   B заборонений кидок каже причину, дерево на диску не змінилось
 *   C стан кинуто всередину ІНШОЇ сторінки (зона `inside`)
 *   D масове видалення двох вибраних видаляє ОБИДВА (без 409 на другому)
 *   E ітерацію перемкнули під час відкладеної дії дерева — без «Дерево змінилось»
 *   F ↓ з автоповтором: вибір іде, рамка НЕ перезавантажується, Enter відкриває
 *   G → / ← : перша дитина / батько / згорнути
 *   H Shift+↓ ×2 → три рядки
 *   I набір кирилиці у фільтр не губить фокус
 *   J «＋ тека»: без вибору — у корінь, у фокусі гілки — всередину
 *   K рядки не сплющені (display:contents на `.tree-body`)
 *   L склад контекстного меню (сторінка / стан / тека / мульти)
 *   M діалог видалення теки: обидва режими доходять до диска
 *   N ⌘G у полі фільтра НЕ групує
 *   O перемальовка посеред перетягування: підсвітка повертається, кидок — де підказка
 *   P колесо посеред перетягування: кидок за точкою відпускання
 *   Q Esc посеред жесту скасовує жест, а не закриває меню
 *   R клік без руху (<4px) лишається вибором
 *   S «Видалити» для сторінки без дітей питає В МЕНЮ (етап В): Esc / клік повз / «Ні» — нічого не видалено, «Видалити» — видалено;
 *     тека з вмістом — темна картка з переліком, не вбудоване питання
 */
import assert from "node:assert/strict";
import test from "node:test";
import { cpSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 12400;
const VIEW = { width: 1400, height: 900 };
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;
const MOD = "ControlOrMeta";

const idsOf = (nodes) => nodes.flatMap((n) => [n.id, ...idsOf(n.children ?? [])]);

/** Фікстура з довільним деревом: каталоги сторінок створює `taskFixture` за плоским переліком id. */
function withTree(nodes) {
  const { dir, it1 } = taskFixture({ html: PAGE, pages: idsOf(nodes) });
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({ pages: nodes }));
  return { dir, it1 };
}
const nestedTree = () => [
  { id: "kartka", name: "Картка", kind: "page", children: [
    { id: "s-err", name: "Помилка", kind: "state" },
    { id: "s-empty", name: "Порожньо", kind: "state" }] },
  { id: "osoba", name: "Особа", kind: "page" },
];
const nested = () => withTree(nestedTree());

const disk = (it1) => JSON.parse(readFileSync(path.join(it1, "pages.json"), "utf8")).pages;
const kidsOf = (nodes, id) => {
  for (const n of nodes) {
    if (n.id === id) return (n.children ?? []).map((c) => c.id);
    const deeper = kidsOf(n.children ?? [], id);
    if (deeper) return deeper;
  }
  return null;
};

async function until(fn, ok, ms = 5000) {
  const end = Date.now() + ms;
  let v;
  while (Date.now() < end) {
    v = await fn();
    if (ok(v)) return v;
    await new Promise((r) => setTimeout(r, 100));
  }
  return v;
}

/** Піднімає сервер і браузер; `open` розгортає `kartka`, якщо є що розгортати. */
async function boot(t, build, off, { expand = "kartka", route } = {}) {
  const { dir, it1 } = build();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await route?.(page);
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  if (expand) {
    const caret = page.locator(`.panel [data-page="${expand}"] [data-act="toggle"]`);
    if ((await caret.count()) && (await page.locator(`.panel [data-page="${expand}"]`).getAttribute("aria-expanded")) !== "true") {
      await caret.click();
    }
  }
  return { page, dir, it1, url };
}

const row = (page, id) => page.locator(`.panel [data-page="${id}"]`);
const rowIds = (page) => page.evaluate(() =>
  [...document.querySelectorAll(".panel [data-page]")].map((r) => r.dataset.page));
const selIds = (page) => page.evaluate(() =>
  [...document.querySelectorAll('.panel [data-page][aria-selected="true"]')].map((r) => r.dataset.page));
async function center(page, id, fy = 0.5) {
  const b = await row(page, id).boundingBox();
  return { x: b.x + b.width / 2, y: b.y + b.height * fy };
}
/** Взяти рядок `id` і довести курсор у точку цілі (поки без відпускання). */
async function dragStart(page, id, to, steps = 8) {
  const from = await center(page, id);
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps });
}
/** Нормальне закриття питання: Enter у полі назви (типова назва лишається). */
async function confirmAsk(page) {
  await page.waitForSelector(".cv-ask input");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
}
/* Тиша панелі: замок дерева знято І розмітка не мінялась за два опитування поспіль.
   Окремого сигналу «дія й догрузка закінчились» нема: `panel--busy` гасне разом із
   відповіддю на POST, а перечитування дерева й перемальовка йдуть ПІСЛЯ нього. Для
   тесту, що береться за мишу одразу по дії, це єдина чесна умова «можна братись». */
async function quiet(page) {
  let prev = null;
  const end = Date.now() + 5000;
  while (Date.now() < end) {
    const cur = await page.evaluate(() => {
      const el = document.getElementById("pages-panel");
      return el.classList.contains("panel--busy") ? null : el.innerHTML;
    });
    if (cur !== null && cur === prev) return;
    prev = cur;
    await new Promise((r) => setTimeout(r, 120));
  }
  throw new Error("панель не втихла за 5 с");
}
/* Запити дерева, що пішли з сторінки: негативні перевірки («нічого не змінилось»)
   рахують їх замість сліпого сну — нуль POST після тиші і є доказом. */
function treePosts(page) {
  const out = [];
  page.on("request", (r) => {
    const m = /\/api\/(page-move|page-group|folder-add)/.exec(r.url());
    if (r.method() === "POST" && m) {
      let it = null;
      try { it = JSON.parse(r.postData() || "{}").it ?? null; } catch { /* не JSON */ }
      out.push({ path: m[1], it });
    }
  });
  return out;
}
const idle = (page) => page.waitForFunction(() =>
  !document.getElementById("pages-panel").classList.contains("panel--busy"));

test("A: ⌘G загортає два стани в теку, далі тека приймає стан перетягуванням «всередину»", async (t) => {
  const { page, it1 } = await boot(t, nested, 0);
  await row(page, "s-err").locator(".row-name").click({ modifiers: [MOD] });
  await row(page, "s-empty").locator(".row-name").click({ modifiers: [MOD] });
  await page.keyboard.press(`${MOD}+g`);
  await confirmAsk(page);
  const tree = await until(() => disk(it1), (p) => p[0].children?.[0]?.kind === "folder");
  const folder = tree[0].children[0];
  assert.deepEqual(folder.children.map((c) => c.id), ["s-err", "s-empty"], "⌘G не загорнув вибране");
  // Диск оновлюється РАНІШЕ за перемальовку панелі — чекаємо рядок теки, а не читаємо одразу.
  assert.equal(await until(() => page.locator(".panel .row[data-kind=folder]").count(), (n) => n === 1), 1);

  // друга половина: тека, що вже є, приймає ще один стан кидком у її середину.
  const folderId = folder.id;
  await page.waitForSelector(`.panel [data-page="${folderId}"]`);
  // виносимо один стан з теки на рівень вище (меню «Вище»), щоб було що кидати всередину
  await row(page, "s-empty").click({ button: "right" });
  await page.click('#cv-ctx [data-a="out"]');
  await until(() => disk(it1), (p) => !kidsOf(p, folderId)?.includes("s-empty"));
  /* Диск раніше за DOM, а перемальовка від ПОПЕРЕДНЬОЇ дії (назва теки) може
     прочитати вже нове дерево, поки запит «Вище» ще в дорозі, — тоді замок дерева
     зайнятий і `pointerdown` панелі мовчки ігнорується. Тому чекаємо обох: рівня
     «s-empty» як у теки й ЗНЯТОГО замка. */
  await page.waitForFunction((id) => {
    const depth = (x) => document.querySelector(`.panel [data-page="${x}"]`)?.className.match(/row--d(\d+)/)?.[1];
    return depth("s-empty") !== undefined && depth("s-empty") === depth(id)
      && !document.getElementById("pages-panel").classList.contains("panel--busy");
  }, folderId, { timeout: 5000 });
  await quiet(page);
  const dst = await center(page, folderId);
  await dragStart(page, "s-empty", dst);
  assert.equal(await page.locator(".row--in").count(), 1, "рамка «всередину» не з'явилась");
  await page.mouse.up();
  const after = await until(() => disk(it1), (p) => kidsOf(p, folderId)?.includes("s-empty"));
  assert.ok(kidsOf(after, folderId).includes("s-empty"), "тека не прийняла стан кидком «всередину»");
});

test("B: заборона — стан у корінь не падає, а каже причину", async (t) => {
  const { page, it1 } = await boot(t, nested, 100);
  const before = JSON.stringify(disk(it1));
  const posts = treePosts(page);
  const b = await row(page, "osoba").boundingBox();
  await dragStart(page, "s-err", { x: b.x + b.width / 2, y: b.y + 2 }, 6);   // «перед Особою» = корінь
  assert.match(await page.locator("#pp-tip").textContent(), /сторінки/, "підказка не назвала причину");
  assert.equal(await page.locator("#pp-tip.drag-tip--no").count(), 1, "підказка не виглядає забороною");
  assert.equal(await page.locator(".row--nope").count(), 1, "рядок не позначено забороною");
  await page.mouse.up();
  await quiet(page);
  assert.deepEqual(posts, [], "заборонений кидок пішов на сервер");
  assert.equal(JSON.stringify(disk(it1)), before, "заборонений кидок змінив дерево");
  assert.equal(await page.locator(".row--in,.row--nope,#pp-ghost,#pp-tip").count(), 0, "лишились підказки");
});

test("C: стан перетягнуто всередину іншої сторінки", async (t) => {
  const { page, it1 } = await boot(t, nested, 200);
  const dst = row(page, "osoba");
  const b = await dst.boundingBox();
  await row(page, "s-err").dragTo(dst, { targetPosition: { x: b.width / 2, y: b.height / 2 } });
  const tree = await until(() => disk(it1), (p) => p[1].children?.length === 1);
  assert.deepEqual(tree[1].children.map((c) => c.id), ["s-err"]);
  assert.equal(await page.locator(".row--in,.row--nope,#pp-ghost,#pp-tip").count(), 0, "після кидка лишились підказки");
});

test("D: масове видалення двох вибраних вузлів видаляє ОБИДВА без 409", async (t) => {
  const { page, it1 } = await boot(t, nested, 300);
  await row(page, "s-err").locator(".row-name").click({ modifiers: [MOD] });
  await row(page, "s-empty").locator(".row-name").click({ modifiers: [MOD] });
  await row(page, "s-err").hover();
  await row(page, "s-err").locator('[data-act="pagemenu"]').click();
  await page.click('#cv-ctx [data-a="delete"]');
  await page.click('.cv-ask [data-a="all"]');
  const tree = await until(() => disk(it1), (p) => !(p[0].children?.length));
  assert.equal(tree[0].children?.length ?? 0, 0, `лишився вузол: ${JSON.stringify(tree[0].children)}`);
  await idle(page);
  assert.equal(await page.locator(".cv-ask").count(), 0,
    `після видалення висить повідомлення: ${await page.locator(".cv-ask").allTextContents()}`);
  assert.deepEqual(await until(() => rowIds(page), (r) => r.length === 2), ["kartka", "osoba"],
    "панель показує не те, що на диску");
});

test("E: ітерацію перемкнули під час відкладеної дії — нова панель без «Дерево змінилось», наступна дія проходить", async (t) => {
  let it2;
  const build = () => {
    const { dir, it1 } = nested();
    // друга ітерація — копія першої; остання за замовчуванням і є відкритою
    it2 = path.join(dir, "iterations", "it2");
    cpSync(it1, it2, { recursive: true });
    writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({ iterations: [
      { id: "it1", date: "24.08.2026 12:00", note: "перша", published: true },
      { id: "it2", date: "24.08.2026 13:00", note: "друга", published: true }] }));
    return { dir, it1 };
  };
  let release;
  const held = new Promise((r) => { release = r; });
  t.after(() => release());   // тест упав до release() — запит не мусить висіти до kill сервера
  let seen = false;
  const { page, it1 } = await boot(t, build, 400, {
    route: (p) => p.route("**/api/page-group", async (rt) => { seen = true; await held; await rt.continue(); }),
  });
  const posts = treePosts(page);
  // відкрито it2 (остання): групуємо два стани, запит зависає
  await row(page, "s-err").locator(".row-name").click({ modifiers: [MOD] });
  await row(page, "s-empty").locator(".row-name").click({ modifiers: [MOD] });
  await page.keyboard.press(`${MOD}+g`);
  await until(() => seen, (v) => v);
  assert.ok(seen, "запит групування не пішов");
  // перемикаємо ітерацію на it1, поки відповідь «в дорозі»
  await page.click('[data-dd="iter"]');
  await page.click('.dd [data-act="iter"][data-val="it1"]');
  await page.waitForFunction(() => document.querySelector('[data-dd="iter"] .txt--fix')?.textContent.trim() === "Іт.1");
  await page.waitForSelector('.panel [data-page="kartka"]');
  release();
  // запит дійшов до it2 на диску, і це не наше діло в it1
  const g2 = await until(() => JSON.parse(readFileSync(path.join(it2, "pages.json"), "utf8")).pages,
    (p) => p[0].children?.[0]?.kind === "folder");
  assert.equal(g2[0].children[0].kind, "folder", "відкладений запит не дійшов до it2");
  await idle(page);
  await quiet(page);
  assert.deepEqual(posts.filter((p) => p.it === "it1"), [], "відкладена дія it2 породила запит у it1");
  assert.equal(await page.locator(".cv-ask").count(), 0,
    `панель нової ітерації показала повідомлення: ${await page.locator(".cv-ask").allTextContents()}`);
  assert.equal(JSON.stringify(disk(it1)), JSON.stringify(nestedTree()), "it1 на диску змінилась");
  // наступна дія в it1 проходить зі свіжим rev
  await page.click('.panel [data-act="newfolder"]');
  await confirmAsk(page);
  const t1 = await until(() => disk(it1), (p) => p.length === 3);
  assert.equal(t1.length, 3, "наступна дія в it1 не пройшла");
  assert.equal(await page.locator(".cv-ask").count(), 0);
});

test("F: ↓ ×3 з автоповтором — вибір просунувся, рамка не перезавантажена, Enter відкриває", async (t) => {
  const { page } = await boot(t, nested, 500);
  await page.evaluate(() => {
    window.__loads = 0;
    document.addEventListener("load", (e) => { if (e.target.tagName === "IFRAME") window.__loads++; }, true);
  });
  const srcBefore = await page.locator("#frame").getAttribute("src");
  await row(page, "kartka").focus();
  for (let i = 0; i < 3; i++) await page.keyboard.down("ArrowDown");   // без up — автоповтор
  await page.keyboard.up("ArrowDown");
  await until(() => selIds(page), (s) => s[0] === "osoba");
  assert.deepEqual(await selIds(page), ["osoba"], "вибір не просунувся на 3 рядки");
  /* Негативна перевірка: `render()` асинхронний (спершу fetch задачі, потім `frame.src`),
     тож «нічого не сталось» можна довести лише вікном спостереження. Це не сон «щоб
     гонка встигла» — подію, якої не мусить бути, інакше не побачити; позитивні
     кроки цього тесту чекають на умову. */
  await page.waitForTimeout(700);
  assert.equal(await page.evaluate(() => window.__loads), 0, "стрілки перезавантажили рамку");
  assert.equal(await page.locator("#frame").getAttribute("src"), srcBefore, "стрілки перемкнули сторінку в рамці");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.page), "osoba", "фокус загубився");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.__loads >= 1);
  assert.match(await page.locator("#frame").getAttribute("src"), /osoba/, "Enter не відкрив вибране");
});

test("G: → веде до першої дитини, ← — до батька, ← на розгорнутому згортає", async (t) => {
  const tree = () => withTree([
    { id: "kartka", name: "Картка", kind: "page", children: [
      { id: "f1", name: "Тека", kind: "folder", children: [{ id: "s-err", name: "Помилка", kind: "state" }] }] },
    { id: "osoba", name: "Особа", kind: "page" }]);
  const { page } = await boot(t, tree, 600);   // kartka розгорнута, f1 згорнута
  await row(page, "kartka").focus();
  await page.keyboard.press("ArrowRight");
  await until(() => selIds(page), (s) => s[0] === "f1");
  assert.deepEqual(await selIds(page), ["f1"], "→ не повів до першої дитини");
  assert.equal(await row(page, "f1").getAttribute("aria-expanded"), "false");
  await page.keyboard.press("ArrowLeft");   // f1 згорнута, має батька → до батька
  await until(() => selIds(page), (s) => s[0] === "kartka");
  assert.deepEqual(await selIds(page), ["kartka"], "← на згорнутому не повів до батька");
  await page.keyboard.press("ArrowLeft");   // kartka розгорнута → згортається
  await until(() => row(page, "kartka").getAttribute("aria-expanded"), (v) => v === "false");
  assert.equal(await row(page, "kartka").getAttribute("aria-expanded"), "false", "← не згорнув розгорнуте");
});

test("H: Shift+↓ ×2 вибирає три рядки", async (t) => {
  const { page } = await boot(t, nested, 700);
  await row(page, "kartka").locator(".row-name").click();   // опора діапазону
  await row(page, "kartka").focus();
  await page.keyboard.press("Shift+ArrowDown");
  await page.keyboard.press("Shift+ArrowDown");
  const got = await until(() => selIds(page), (s) => s.length === 3);
  assert.deepEqual(got, ["kartka", "s-err", "s-empty"], "діапазон не три рядки від опори");
});

test("I: набір кирилиці у фільтр не губить фокус і значення", async (t) => {
  const tree = () => withTree([
    { id: "kartka", name: "Картка", kind: "page" },
    { id: "sanctions", name: "Санкції", kind: "page" },
    { id: "osoba", name: "Особа", kind: "page" }]);
  const { page } = await boot(t, tree, 800, { expand: null });
  await page.click("#pp-filter");
  let typed = "";
  for (const ch of "сан") {
    await page.keyboard.type(ch);
    typed += ch;
    const st = await page.evaluate(() => ({ id: document.activeElement?.id,
      v: document.getElementById("pp-filter")?.value }));
    assert.equal(st.id, "pp-filter", `після «${typed}» фокус поза полем фільтра`);
    assert.equal(st.v, typed, "значення поля не збігається з набраним");
  }
  assert.deepEqual(await until(() => rowIds(page), (r) => r.length === 1), ["sanctions"]);
});

test("I2: IME-композиція у фільтрі — фокус на місці, фільтр застосовується лише після коміту", async (t) => {
  const tree = () => withTree([
    { id: "kartka", name: "Картка", kind: "page" },
    { id: "sanctions", name: "Санкції", kind: "page" },
    { id: "osoba", name: "Особа", kind: "page" }]);
  const { page } = await boot(t, tree, 850, { expand: null });
  const cdp = await page.context().newCDPSession(page);
  await page.click("#pp-filter");
  await cdp.send("Input.imeSetComposition", { text: "сан", selectionStart: 3, selectionEnd: 3 });
  const mid = await page.evaluate(() => ({ id: document.activeElement?.id,
    rows: document.querySelectorAll(".panel [data-page]").length }));
  assert.equal(mid.id, "pp-filter", "композиція забрала фокус із поля");
  assert.equal(mid.rows, 3, "фільтр застосувався ДО коміту композиції");
  await cdp.send("Input.insertText", { text: "сан" });
  assert.deepEqual(await until(() => rowIds(page), (r) => r.length === 1), ["sanctions"],
    "після коміту фільтр не застосувався");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "pp-filter", "після коміту фокус загубився");
});

test("J1: «＋ тека» без вибору й фокуса кладе теку в КОРІНЬ", async (t) => {
  const { page, it1 } = await boot(t, nested, 900);
  await page.click('.panel [data-act="newfolder"]');
  await confirmAsk(page);
  const tree = await until(() => disk(it1), (p) => p.length === 3);
  assert.equal(tree.length, 3, "теки в корені немає");
  assert.equal(tree[2].kind, "folder");
  assert.equal(kidsOf(tree, "kartka").length, 2, "тека потрапила не в корінь");
});

test("J2: «＋ тека» у фокусі гілки кладе теку всередину гілки", async (t) => {
  const { page, it1 } = await boot(t, nested, 1000);
  await row(page, "kartka").click({ button: "right" });
  await page.click('#cv-ctx [data-a="focus"]');
  await page.waitForSelector(".tree-crumbs .crumb");
  await page.click('.panel [data-act="newfolder"]');
  await confirmAsk(page);
  const tree = await until(() => disk(it1), (p) => (p[0].children ?? []).some((c) => c.kind === "folder"));
  assert.ok(kidsOf(tree, "kartka").length === 3 && tree.length === 2, `тека не в гілці: ${JSON.stringify(tree)}`);
});

test("K: рядки не сплющені — висота ≥ 28px при display:contents", async (t) => {
  const { page } = await boot(t, nested, 1100);
  const got = await page.evaluate(() => ({
    disp: getComputedStyle(document.querySelector(".tree-body")).display,
    hs: [...document.querySelectorAll(".panel .row")].map((r) => r.getBoundingClientRect().height),
  }));
  assert.equal(got.disp, "contents");
  assert.ok(got.hs.length >= 4);
  assert.ok(Math.min(...got.hs) >= 28, `сплющені рядки: ${got.hs}`);
});

test("L: склад контекстного меню для сторінки / стану / теки / мульти-вибору", async (t) => {
  const tree = () => withTree([
    { id: "kartka", name: "Картка", kind: "page", children: [
      { id: "s-err", name: "Помилка", kind: "state" },
      { id: "s-empty", name: "Порожньо", kind: "state" }] },
    { id: "fold", name: "Тека", kind: "folder", children: [{ id: "osoba", name: "Особа", kind: "page" }] }]);
  const { page } = await boot(t, tree, 1200);
  await row(page, "fold").locator('[data-act="toggle"]').click();
  const items = async (id) => {
    await row(page, id).click({ button: "right" });
    const got = await page.evaluate(() =>
      [...document.querySelectorAll("#cv-ctx [data-a]")].map((b) => b.dataset.a));
    await page.waitForTimeout(50);   // слухачі меню вішаються через setTimeout(0), див. panel-pages B+C
    await page.keyboard.press("Escape");
    await page.waitForSelector("#cv-ctx", { state: "detached" });
    return got;
  };
  assert.deepEqual(await items("kartka"),
    ["folder", "rename", "group", "down", "focus", "kind", "pub", "delete"], "меню сторінки");
  assert.deepEqual(await items("s-err"),
    ["rename", "group", "down", "out", "kind", "pub", "delete"], "меню стану (без «＋ теки» і «фокус»)");
  assert.deepEqual(await items("fold"),
    ["folder", "rename", "group", "ungroup", "up", "focus", "pub", "delete"],
    "меню теки (є «розгрупувати», немає «у стан/сторінку»)");
  await row(page, "s-err").locator(".row-name").click({ modifiers: [MOD] });
  await row(page, "s-empty").locator(".row-name").click({ modifiers: [MOD] });
  assert.deepEqual(await items("s-err"), ["group", "delete"], "меню мульти-вибору");
});

test("M: діалог видалення теки — «прибрати, вміст підняти» доходить до диска", async (t) => {
  const tree = () => withTree([
    { id: "fold", name: "Тека", kind: "folder", children: [
      { id: "kartka", name: "Картка", kind: "page" }, { id: "osoba", name: "Особа", kind: "page" }] }]);
  const { page, it1 } = await boot(t, tree, 1300, { expand: "fold" });
  await row(page, "fold").click({ button: "right" });
  await page.click('#cv-ctx [data-a="delete"]');
  const items = await page.locator(".cv-ask-list li").allTextContents();
  assert.deepEqual(items, ["Картка", "Особа"], "діалог не перелічив вміст");
  await page.click('.cv-ask [data-a="unwrap"]');
  const got = await until(() => disk(it1), (p) => p.length === 2);
  assert.deepEqual(got.map((n) => n.id), ["kartka", "osoba"], "вміст не піднято в корінь");
});

test("M2: діалог видалення теки — «видалити все» теж доходить до диска", async (t) => {
  const tree = () => withTree([
    { id: "fold", name: "Тека", kind: "folder", children: [
      { id: "kartka", name: "Картка", kind: "page" }] },
    { id: "osoba", name: "Особа", kind: "page" }]);
  const { page, it1 } = await boot(t, tree, 1400, { expand: "fold" });
  await row(page, "fold").click({ button: "right" });
  await page.click('#cv-ctx [data-a="delete"]');
  await page.click('.cv-ask [data-a="all"]');
  const got = await until(() => disk(it1), (p) => p.length === 1);
  assert.deepEqual(got.map((n) => n.id), ["osoba"], "тека з вмістом не видалена цілком");
});

test("N: ⌘G у полі фільтра НЕ групує", async (t) => {
  const { page, it1 } = await boot(t, nested, 1500);
  await row(page, "s-err").locator(".row-name").click({ modifiers: [MOD] });
  await row(page, "s-empty").locator(".row-name").click({ modifiers: [MOD] });
  await page.click("#pp-filter");
  const before = JSON.stringify(disk(it1));
  const posts = treePosts(page);
  await page.keyboard.press(`${MOD}+g`);
  await quiet(page);
  assert.deepEqual(posts, [], "⌘G у фільтрі послав запит групування");
  assert.equal(await page.locator(".cv-ask").count(), 0, "⌘G у фільтрі відкрив діалог групування");
  assert.equal(JSON.stringify(disk(it1)), before, "⌘G у фільтрі згрупував");
});

test("O: перемальовка посеред перетягування повертає підсвітку, кидок іде туди, куди показує підказка", async (t) => {
  const { page, it1 } = await boot(t, nested, 1600);
  await dragStart(page, "s-err", await center(page, "osoba"));
  assert.equal(await page.locator('.row--in[data-page="osoba"]').count(), 1);
  // перемальовка дерева: ті самі рядки, але вже нові вузли DOM
  await page.evaluate(() => {
    window.__old = document.querySelector('.panel [data-page="osoba"]');
    document.getElementById("pp-filter").dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.waitForFunction(() => document.querySelector('.panel [data-page="osoba"]') !== window.__old,
    null, { timeout: 3000 });
  assert.equal(await page.locator('.row--in[data-page="osoba"]').count(), 1, "підсвітка не повернулась на нові вузли");
  assert.equal(await page.locator("#pp-ghost").count(), 1, "привид зник");
  assert.match(await page.locator("#pp-tip").textContent(), /Особа/, "підказка не називає ціль");
  await page.mouse.up();
  const tree = await until(() => disk(it1), (p) => p[1].children?.length === 1);
  assert.deepEqual(kidsOf(tree, "osoba"), ["s-err"], "кидок пішов не туди, куди показувала підказка");
});

test("P: колесо посеред перетягування — кидок за точкою відпускання", async (t) => {
  const many = () => withTree([
    ...nestedTree(),
    ...Array.from({ length: 40 }, (_, i) => ({ id: `p${String(i).padStart(2, "0")}`, name: `Сторінка ${i}`, kind: "page" }))]);
  const { page, it1 } = await boot(t, many, 1700);
  const scrollable = await page.evaluate(() => {
    const b = document.querySelector(".panel-body");
    return b.scrollHeight > b.clientHeight + 200;
  });
  assert.ok(scrollable, "панель не прокручується — перевірка беззмістовна");
  const aimAt = await center(page, "p03");
  await dragStart(page, "s-err", aimAt);
  /* Крок прокрутки — рівно ціле число рядків: інакше курсор опиниться на межі рядків
     (зона «перед» кореня), і заборона «стан у корінь» — правильна відповідь на
     МІЙ вибір точки, а не на жест. */
  const pitch = (await row(page, "p04").boundingBox()).y - (await row(page, "p03").boundingBox()).y;
  await page.mouse.wheel(0, Math.round(pitch * 10));
  // що опинилось під курсором після прокрутки — туди й мусить піти кидок
  const under = await until(() => page.evaluate(([x, y]) =>
    document.elementFromPoint(x, y)?.closest("#pages-panel [data-page]")?.dataset.page, [aimAt.x, aimAt.y]),
  (v) => v && v !== "p03");
  assert.ok(under && under !== "p03", `прокрутка не зсунула рядки під курсором (під ним ${under})`);
  await page.waitForFunction((id) => document.querySelector(".row--in")?.dataset.page === id, under,
    { timeout: 3000 });
  await page.mouse.up();
  const tree = await until(() => disk(it1), (p) => kidsOf(p, under)?.length === 1);
  assert.deepEqual(kidsOf(tree, under), ["s-err"], `кидок пішов не в ${under}`);
  assert.deepEqual(kidsOf(tree, "p03"), [], "кидок пішов у рядок, що був під курсором ДО прокрутки");
});

test("Q: Esc посеред жесту скасовує перетягування, а відкрите меню лишає", async (t) => {
  const { page, it1 } = await boot(t, nested, 1800);
  const before = JSON.stringify(disk(it1));
  const posts = treePosts(page);
  await row(page, "osoba").click({ button: "right" });
  await page.waitForSelector("#cv-ctx");
  await dragStart(page, "s-err", await center(page, "s-empty", 0.9), 10);
  assert.equal(await page.locator("#pp-ghost").count(), 1, "жест не почався");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#pp-ghost,#pp-tip,.row--drag,.row--in,.row--nope").count(), 0,
    "Esc не скасував перетягування");
  assert.equal(await page.locator("#cv-ctx").count(), 1, "той самий Esc закрив ще й меню");
  // контроль: другий Esc (жесту вже нема) меню таки закриває — слухачі були живі
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#cv-ctx").count(), 0, "другий Esc не закрив меню");
  await page.mouse.up();
  await quiet(page);
  assert.deepEqual(posts, [], "скасований жест пішов на сервер");
  assert.equal(JSON.stringify(disk(it1)), before, "скасований жест змінив дерево");
});

test("R: клік без руху (<4px) лишається вибором рядка", async (t) => {
  const { page, it1 } = await boot(t, nested, 1900);
  const before = JSON.stringify(disk(it1));
  const posts = treePosts(page);
  const p = await center(page, "s-err");
  await page.mouse.move(p.x, p.y);
  await page.mouse.down();
  await page.mouse.move(p.x + 2, p.y + 1, { steps: 2 });
  assert.equal(await page.locator("#pp-ghost").count(), 0, "рух <4px почав жест");
  await page.mouse.up();
  await until(() => selIds(page), (s) => s[0] === "s-err");
  assert.deepEqual(await selIds(page), ["s-err"], "клік без руху не вибрав рядок");
  await quiet(page);
  assert.deepEqual(posts, [], "клік без руху послав запит дерева");
  assert.equal(JSON.stringify(disk(it1)), before);
});

test("S: «Видалити» для сторінки без дітей питає в самому меню; видаляє лише явне «Видалити»", async (t) => {
  const { page, it1 } = await boot(t, nested, 2000);
  const alive = () => existsSync(path.join(it1, "osoba", "index.html")) && idsOf(disk(it1)).includes("osoba");
  const openAsk = async () => {
    await row(page, "osoba").click({ button: "right" });
    await page.click('#cv-ctx [data-a="delete"]');
    await page.waitForSelector("#cv-ctx .cfm", { timeout: 5000 });
    assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "питання вийшло модальним, а не в меню");
    assert.equal(await page.evaluate(() => document.activeElement?.classList.contains("cfm-no")), true, "фокус не на «Ні»");
    assert.match(await page.textContent("#cv-ctx .cfm-t"), /Видалити сторінку «Особа»\?/);
    assert.equal(await page.locator("#cv-ctx .cfm p").count(), 1, "у питанні є щось, крім самого питання");
  };
  const gone = (why) => assert.equal(alive(), true, `видалено: ${why}`);
  // (a) Esc
  await openAsk();
  await page.keyboard.press("Escape");
  await page.waitForSelector("#cv-ctx", { state: "detached" });
  await quiet(page);
  gone("Esc");
  // (b) клік повз
  await openAsk();
  await page.locator(".panel").first().click({ position: { x: 2, y: 2 } });
  await page.waitForSelector("#cv-ctx", { state: "detached" });
  await quiet(page);
  gone("клік повз");
  // (c) «Ні»
  await openAsk();
  await page.click("#cv-ctx .cfm-no");
  await page.waitForSelector("#cv-ctx", { state: "detached" });
  await quiet(page);
  gone("«Ні»");
  assert.deepEqual(await rowIds(page), ["kartka", "s-err", "s-empty", "osoba"], "дерево змінилось без підтвердження");
  // (d) «Видалити»: без другого вікна
  await openAsk();
  await page.click("#cv-ctx .cfm-yes");
  const left = await until(() => idsOf(disk(it1)), (ids) => !ids.includes("osoba"));
  assert.equal(left.includes("osoba"), false, "«Видалити» не дійшло до диска");
  assert.equal(existsSync(path.join(it1, "osoba")), false, "тека сторінки лишилась на диску");
  await idle(page);
  assert.equal(await page.locator(".cv-ask").count(), 0, "після видалення висить друге питання чи повідомлення");
  assert.deepEqual(await until(() => rowIds(page), (r) => !r.includes("osoba")), ["kartka", "s-err", "s-empty"], "панель показує не те, що на диску");
});

test("S2: тека з вмістом — темна картка з переліком, а не питання в меню; тло не біле", async (t) => {
  const tree = () => withTree([
    { id: "fold", name: "Тека", kind: "folder", children: [{ id: "kartka", name: "Картка", kind: "page" }] },
    { id: "osoba", name: "Особа", kind: "page" }]);
  const { page, it1 } = await boot(t, tree, 2100, { expand: "fold" });
  await row(page, "fold").click({ button: "right" });
  await page.click('#cv-ctx [data-a="delete"]');
  await page.waitForSelector(".cv-ask-scrim .cv-ask-list li");
  assert.equal(await page.locator("#cv-ctx .cfm").count(), 0, "для теки з вмістом питання вбудоване в меню");
  const looks = await page.evaluate(() => ({
    card: getComputedStyle(document.querySelector(".cv-ask")).backgroundColor,
    del: getComputedStyle(document.querySelector('.cv-ask [data-a="all"]')).backgroundColor,
    cancel: getComputedStyle(document.querySelector('.cv-ask [data-a="cancel"]')).backgroundColor,
    focus: document.activeElement?.dataset?.a,
  }));
  for (const [k, v] of Object.entries({ card: looks.card, del: looks.del, cancel: looks.cancel })) {
    assert.notEqual(v, "rgb(255, 255, 255)", `${k}: тло біле`);
  }
  assert.equal(looks.focus, "cancel", "фокус не на «Скасувати»");
  await page.keyboard.press("Escape");
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  await quiet(page);
  assert.deepEqual(idsOf(disk(it1)), ["fold", "kartka", "osoba"], "Esc у картці видалив");
});
