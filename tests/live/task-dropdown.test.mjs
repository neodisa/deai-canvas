/**
 * Дропдаун задач не сплющує пункти, коли задач більше, ніж влазить у висоту.
 *
 * Скрин 09.10.2026 (31 задача, вікно ~1000px): назви й підписи пунктів лягали
 * одне на одне. Причина — `.dd` є flex-колонкою з `max-height` і прокруткою,
 * а пункти за замовчуванням `flex-shrink:1`: замість прокрутки flex стискав
 * кожен пункт нижче висоти його тексту, і рядки виповзали на сусідів.
 *
 * На короткій фікстурі (одна-дві задачі) вада не відтворюється взагалі —
 * тому тут 40 задач із двома рядками кожна у вікні 700px.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 16800;

test("40 задач у дропдауні: жоден пункт не стиснутий, сусіди не налазять, список прокручується", async (t) => {
  const { dir } = taskFixture({ html: () => "<!doctype html><h1>Фікстура</h1>" });
  const extraTasks = {};
  for (let i = 0; i < 40; i += 1) {
    extraTasks[`t${i}`] = { dir, jira: `LIGA-${10000 + i}`,
      title: `Задача ${i} · довга назва, що переноситься на другий рядок у дропдауні` };
  }
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, extraTasks });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1280, height: 700 } });
  await page.goto(`${url}/app/`);
  await page.click('[data-dd="task"]');
  await page.waitForSelector(".crumb-h.crumb--task .dd .dd-item");

  const g = await page.evaluate(() => {
    const dd = document.querySelector(".crumb-h.crumb--task .dd");
    /* Пункти задач — `[data-act="task"]`: футер «Усі задачі» теж `.dd-item`, але
       він не в списку. Прокручується тепер САМ список (`.dd-list`), а не весь
       дропдаун: пошук і футер лишаються на місці (батч 1.52, Task 5). */
    const list = dd.querySelector(".dd-list");
    const items = [...list.querySelectorAll('.dd-item[data-act="task"]')].map((el) => {
      const r = el.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, h: r.height, need: el.scrollHeight };
    });
    return { items, scrolls: list.scrollHeight > list.clientHeight + 1,
      ddFits: dd.getBoundingClientRect().bottom <= window.innerHeight };
  });

  assert.ok(g.ddFits, "дропдаун не виходить за нижній край вікна — футер видно");
  assert.equal(g.items.length, 41, "у дропдауні всі задачі");          // 40 + фікстура
  assert.ok(g.scrolls, "задач більше, ніж влазить, — список прокручується");
  const squashed = g.items.filter((x) => x.h + 0.5 < x.need);
  assert.deepEqual(squashed, [], "пункт нижчий за свій вміст — текст вилазить на сусіда");
  for (let i = 1; i < g.items.length; i += 1) {
    assert.ok(g.items[i].top + 0.5 >= g.items[i - 1].bottom, `пункт ${i} налазить на попередній`);
  }
});

/* ── Пошук і клавіатура (батч 1.52, Task 5) ───────────────────────────────── */

const ddHtml = () => "<!doctype html><h1>Фікстура</h1>";

/** Сервер із 10 задачами «Задача N» і однією з відсутньою текою. Порядок
 *  `extraTasks` — порядок списку (`opened` нема): t17 стоїть ПЕРЕД t7, тож на
 *  запит «Задача 7» (збігаються обидві) перша — t17, а t7 — друга. */
async function bootSearch(t, portBase) {
  const { dir } = taskFixture({ html: ddHtml });
  const extraTasks = {};
  for (let i = 0; i < 10; i += 1) {
    if (i === 7) extraTasks.t17 = { dir, jira: "LIGA-7020", title: "LIGA-7020 · Задача 17 для пошуку" };
    extraTasks[`t${i}`] = { dir, jira: `LIGA-${10000 + i}`, title: `Задача ${i} для пошуку` };
  }
  extraTasks.ghost = { dir: `${dir}-нема-на-цій-машині`, jira: "LIGA-7021", title: "Привид без теки" };
  const { child, url } = await startServer(dir, { portBase, extraTasks });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('[data-dd="task"]');
  return { page, url };
}

const ddIds = (page) => page.evaluate(() =>
  [...document.querySelectorAll('.crumb-h.crumb--task .dd [data-act="task"]')].map((b) => b.dataset.val));
const curTask = async (url) => (await (await fetch(`${url}/api/tasks`)).json()).current;
const focusedId = (page) => page.evaluate(() => document.activeElement?.id ?? null);

test("пошук: відкриття фокусує поле, набір фільтрує наживо, ↓ Enter відкриває, Esc закриває", async (t) => {
  const { page, url } = await bootSearch(t, PORT_BASE + 100);
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q");
  assert.equal(await focusedId(page), "task-q", "поле пошуку одразу під фокусом");
  assert.equal((await ddIds(page)).length, 13, "порожній запит — усі задачі (10 + t17 + ghost + fixture)");
  assert.match(await page.textContent(".crumb-h.crumb--task .dd .dd-head"), /Нещодавні/);

  await page.keyboard.type("Задача 7");
  assert.deepEqual(await ddIds(page), ["t17", "t7"], "лише збіги за всіма словами");
  assert.equal(await page.inputValue("#task-q"), "Задача 7", "набір не стирається перемальовкою списку");
  assert.equal(await focusedId(page), "task-q");
  assert.equal(await page.locator(".dd-list mark").count() > 0, true, "збіги підсвічені");
  // перша активна одразу; ↓ — друга; Enter — відкрити її
  assert.equal(await page.getAttribute(".dd-item--cur", "data-val"), "t17");
  await page.keyboard.press("ArrowDown");
  assert.equal(await page.getAttribute(".dd-item--cur", "data-val"), "t7");
  await page.keyboard.press("Enter");
  await page.waitForFunction(async () => (await (await fetch("/api/tasks")).json()).current === "t7");
  assert.equal(await curTask(url), "t7");
  await page.waitForSelector(".crumb-h.crumb--task .dd", { state: "detached" });

  // Esc: відкрити знову → запит порожній (скинуто), Esc закриває
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q");
  assert.equal(await page.inputValue("#task-q"), "", "новий вхід — порожній запит");
  await page.keyboard.press("Escape");
  await page.waitForSelector(".crumb-h.crumb--task .dd", { state: "detached" });
});

test("пошук: ↓ доходить до футера «Усі задачі», Enter на ньому відкриває екран задач; порожня видача — текст", async (t) => {
  const { page } = await bootSearch(t, PORT_BASE + 200);
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q");
  await page.keyboard.type("Задача 7");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");          // далі футера не йде
  assert.equal(await page.getAttribute(".dd-item--cur", "data-act"), "home");
  await page.keyboard.press("ArrowUp");
  assert.equal(await page.getAttribute(".dd-item--cur", "data-val"), "t7");

  await page.keyboard.type(" zzzz");
  assert.deepEqual(await ddIds(page), []);
  assert.match(await page.textContent(".dd-list"), /Нічого не знайдено за «Задача 7 zzzz»/);
  /* Порожня видача: активного пункту нема, і Enter НІЧОГО не робить — інакше
     людина, що набрала помилковий запит і натиснула Enter, опинялась би на
     екрані «Задачі». Футер стає активним лише стрілкою вниз. */
  assert.equal(await page.locator(".dd-item--cur").count(), 0, "у порожній видачі активного пункту нема");
  await page.keyboard.press("Enter");
  assert.equal(await page.locator(".crumb-h.crumb--task .dd").count(), 1, "Enter на порожній видачі нічого не закрив");
  assert.equal(await page.locator(".logo-btn.ctl--on").count(), 0, "і не відкрив екран «Задачі»");
  await page.keyboard.press("ArrowDown");
  assert.equal(await page.getAttribute(".dd-item--cur", "data-act"), "home", "↓ входить на футер");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".logo-btn.ctl--on");   // екран «Задачі» відкрито
});

test("пошук: перемальовка смуги під час набору не губить значення, фокус і позицію курсора", async (t) => {
  const { page } = await bootSearch(t, PORT_BASE + 300);
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q");
  await page.keyboard.type("Задача 7");
  // курсор посередині, не в кінці: саме його губить `bar.innerHTML = …`
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  const before = await page.evaluate(() => {
    const q = document.getElementById("task-q");
    window.__q = q;
    return [q.selectionStart, q.selectionEnd];
  });
  assert.deepEqual(before, [6, 6]);

  /* Справжній тригер `paintBar()` — завантаження рамки: Claude змінив макет,
     автооновлення перезавантажило рамку, і її `load` перемальовує смугу ЦІЛКОМ
     (обробник `frame` 'load' в app.js). Нічого нового в застосунок не виставляємо.
     (До 1.54 тригером був опит статусу Клода — тепер він живе в острівці й смуги
     не чіпає.) */
  await page.evaluate(() => document.getElementById("frame").contentWindow.location.reload());
  await page.waitForFunction(() => !window.__q.isConnected, null, { timeout: 12000 });

  assert.equal(await page.evaluate(() => window.__q.isConnected), false,
    "смугу справді перемалювали (старе поле замінене) — інакше тест нічого не доводить");
  assert.equal(await focusedId(page), "task-q", "фокус повернувся в нове поле");
  assert.equal(await page.inputValue("#task-q"), "Задача 7");
  assert.deepEqual(await page.evaluate(() => {
    const q = document.getElementById("task-q");
    return [q.selectionStart, q.selectionEnd];
  }), [6, 6], "курсор на місці");
  assert.deepEqual(await ddIds(page), ["t17", "t7"], "фільтр зберігся");
  // і набір продовжується з того ж місця
  await page.keyboard.type("X");
  assert.equal(await page.inputValue("#task-q"), "ЗадачаX 7", "символ вставлено там, де стояв курсор");
});

test("пошук: задача без теки на цій машині — Enter каже причину і НЕ перемикає", async (t) => {
  const { page, url } = await bootSearch(t, PORT_BASE + 400);
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q");
  await page.keyboard.type("Привид");
  assert.deepEqual(await ddIds(page), ["ghost"]);
  assert.match(await page.textContent('.dd-item[data-val="ghost"]'), /теки немає на цій машині/);
  await page.keyboard.press("Enter");
  await page.waitForSelector("#cv-toast.show");
  assert.match(await page.textContent("#cv-toast"), /LIGA-7021/, "причина названа ключем задачі");
  assert.equal(await curTask(url), "fixture", "поточна задача не змінилась");
  assert.equal(await page.locator(".crumb-h.crumb--task .dd").count(), 1, "дропдаун лишився відкритим");

  // те саме кліком
  await page.evaluate(() => document.getElementById("cv-toast")?.classList.remove("show"));
  /* `force`: пункт має `aria-disabled` (для читача), а Playwright вважає такий
     «не enabled» і чекав би вічно; живий клік мишею він не блокує. */
  await page.click('.dd-item[data-val="ghost"]', { force: true });
  await page.waitForSelector("#cv-toast.show");
  assert.equal(await curTask(url), "fixture", "клік по задачі без теки теж не перемикає");
});

/* ── Усунення зауважень ревʼю (IME, прокрутка) ────────────────────────────── */

const compose = (page, type) => page.evaluate((ty) => {
  document.getElementById("task-q").dispatchEvent(new CompositionEvent(ty, { bubbles: true }));
}, type);

test("IME: дропдаун, закритий посеред композиції, відкривається й малюється знову", async (t) => {
  const { page } = await bootSearch(t, PORT_BASE + 500);
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q");
  await compose(page, "compositionstart");
  /* Esc БЕЗ `isComposing` (справжня клавіша) закриває дропдаун; на вилученому
     полі `compositionend` не прийде ніколи — рівно той випадок, що залишав
     `taskComposing = true` назавжди. */
  await page.keyboard.press("Escape");
  await page.waitForSelector(".crumb-h.crumb--task .dd", { state: "detached" });
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q", { timeout: 3000 });
  assert.equal(await focusedId(page), "task-q", "поле під фокусом");
  assert.equal((await ddIds(page)).length, 13, "список намальовано");
  await page.keyboard.type("Привид");
  assert.deepEqual(await ddIds(page), ["ghost"], "і набір знову фільтрує (прапорець не залип)");
});

test("IME: Esc під час композиції скасовує її, а не закриває дропдаун", async (t) => {
  const { page } = await bootSearch(t, PORT_BASE + 600);
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q");
  await compose(page, "compositionstart");
  await page.evaluate(() => document.getElementById("task-q").dispatchEvent(
    new KeyboardEvent("keydown", { key: "Escape", isComposing: true, bubbles: true })));
  assert.equal(await page.locator(".crumb-h.crumb--task .dd").count(), 1, "дропдаун лишився відкритим");
  await compose(page, "compositionend");
  await page.keyboard.press("Escape");
  await page.waitForSelector(".crumb-h.crumb--task .dd", { state: "detached" });
});

test("прокрутка: після перемальовки смуги активний пункт довгого списку лишається видимим", async (t) => {
  const { dir } = taskFixture({ html: ddHtml });
  const extraTasks = {};
  for (let i = 0; i < 40; i += 1) {
    extraTasks[`t${i}`] = { dir, jira: `LIGA-${10000 + i}`, title: `Задача ${i} для прокрутки` };
  }
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 700, extraTasks });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1280, height: 600 } });
  await page.goto(`${url}/app/`);
  await page.click('[data-dd="task"]');
  await page.waitForSelector("#task-q");
  for (let i = 0; i < 25; i += 1) await page.keyboard.press("ArrowDown");
  const geo = () => page.evaluate(() => {
    const l = document.querySelector(".dd-list").getBoundingClientRect();
    const a = document.querySelector(".dd-item--cur").getBoundingClientRect();
    return { top: document.querySelector(".dd-list").scrollTop, inView: a.top >= l.top - 1 && a.bottom <= l.bottom + 1 };
  });
  const before = await geo();
  assert.ok(before.top > 0 && before.inView, "передумова: список прокручено, активний видно");

  await page.evaluate(() => { window.__l = document.querySelector(".dd-list"); });
  // Тригер — завантаження рамки (див. тест курсора вище).
  await page.evaluate(() => document.getElementById("frame").contentWindow.location.reload());
  await page.waitForFunction(() => !window.__l.isConnected, null, { timeout: 12000 });
  assert.equal(await page.evaluate(() => window.__l.isConnected), false, "смугу справді перемалювали");
  const after = await geo();
  assert.ok(after.top > 0, "прокрутка списку не скинулась на 0");
  assert.ok(after.inView, "активний пункт виїхав за видиму частину списку");
});
