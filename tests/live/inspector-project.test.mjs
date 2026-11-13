/**
 * Живий тест: інспектор ДС мусить працювати в аудиторії «Проєкт».
 *
 * Вимір, з якого тест народився (02.09.2026, справжній браузер): при
 * `ch=project` `frame.contentWindow.CanvasInspector` === `undefined`, при
 * `ch=local` — обʼєкт. Причина одна — `inspector.js` вставлявся лише в
 * `LOCAL_COMMENT_SNIPPET`. Кнопка інспектора в смузі при цьому НЕ зникала:
 * `inspectorApi()` віддавав `null`, дія тихо нічого не робила, і дизайнер
 * бачив мертвий контрол без жодного слова про причину.
 *
 * Чому саме ЖИВИЙ тест, а не юніт: `tests/test_serve.py` стереже ТЕКСТ
 * сніпета (тег є, стоїть після коментарів, без `onerror`), але не те, що
 * модуль СПРАВДІ виконується в цьому документі — у нього два відносні
 * імпорти (`inspector-dom.js`, `inspector-measure.js`), а в сторінці макета
 * стоїть `<base href>`, і будь-яка помилка розвʼязання шляху дала б рівно
 * той самий мертвий контрол при цілком правильному тексті сніпета.
 *
 * ⛔ Адаптер коментарів тут ЗАБЛОКОВАНИЙ навмисно (4b-2: файл `supabase-comments/adapter.js` модуля; до 0.10.0 — CDN
 * Supabase), і це друга половина перевірки. ЛІГА має конфіг Supabase (`supabase: true`) — без нього сторінка каналу
 * лишалась би локальною з приміткою, і «мертвий Supabase» був би порожнім сценарієм.
 * Спека забороняє чіпляти на тег інспектора `onerror="window.__clDown(…)"`:
 * той банер каже «Коментарі недоступні», а інспектор до коментарів не має
 * стосунку. Зворотна залежність теж мусить не існувати — мертвий Supabase не
 * сміє забирати в дизайнера лінійку. Блокування дає це задарма й водночас
 * робить тест герметичним (жодної справжньої мережі, ~3с економії).
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { MODULE_ADAPTER_GLOB, hermeticLiga } from "./_liga-supabase.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя база порту: `node --test` крутить файли ПАРАЛЕЛЬНО (сусідні бази:
   shell.test=9790, shell-palette=9690, shell-inspect=9590). */
const PORT_BASE = 9890;
const VIEW = { width: 1400, height: 900 };

/* Градієнт, а не порожня сторінка — та сама причина, що в сусідніх живих
   тестах: порожній знімок стискається нижче `BYTES_FLOOR` і числився б
   «застарілим», тож вхід у макет міг би замовити справжню автозʼємку. Тут
   вона не потрібна взагалі: інспектор працює по живому DOM, не по кадрах.
   Блок із рамкою й відступом — щоб інспектору було що показати. */
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:900px;background:repeating-linear-gradient(37deg,#e11 0 10px,`
  + `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)">`
  + `<h1 id="t" style="margin:40px;padding:12px;border:2px solid #333">${id}</h1></body></html>`;

/**
 * Перемкнути аудиторію коментарів через ⌘K.
 *
 * ⛔ Не вкладками в панелі коментатора, хоч це і головний шлях: у ЦЬОМУ тесті
 * адаптер коментарів зарізаний (див. шапку), тобто коментатор не піднімається — і
 * вкладок немає разом із ним. Тут це не незручність хелпера, а рівно той
 * сценарій, заради якого аварійний вихід у палітрі й існує (коментар над
 * `gSet` у `app/shell-palette.js`).
 *
 * Дропдаун крошки ітерації (`data-act="cmode"`), що стояв тут до 02.09.2026,
 * прибрано принципом 6 PRODUCT.md: контролів коментатора у смузі немає.
 * Перевірки нижче не змінились — це той самий `setAudience()` в `app.js`.
 */
async function setAudience(page, mode) {
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible", timeout: 5000 });
  await page.fill("#palq", "аудитор");
  await page.locator(".pal-it", { hasText: mode === "local" ? "Клод" : "Команда" }).click();
}

test("аудиторія «Проєкт»: інспектор живий, кнопка смуги його відкриває", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  const net = await hermeticLiga(page);
  await page.route(MODULE_ADAPTER_GLOB, (route) => route.abort());
  await page.goto(`${url}/app/`);

  /* Стартовий стан — `local` (`commentMode` в `app.js`), і саме там інспектор
     працював завжди. Дочекатись його ТУТ обовʼязково: інакше падіння нижче не
     відрізнило б «у «Проєкті» немає» від «сервер узагалі не віддає vendor». */
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });

  await setAudience(page, "project");

  /* Чекаємо на ФАКТ: у рамці стоїть уже НОВИЙ документ (`ch=project`) і він
     догрузився ЦІЛКОМ. Читаємо `contentWindow.location.href`, а НЕ
     `getAttribute('src')`: атрибут міняється в ту ж мить, коли `applyMode`
     його присвоїв, а СТАРИЙ документ (аудиторія `local`, інспектор у ньому
     живий) висить у рамці ще кілька тиків і має `readyState === 'complete'`.
     Перша версія цієї умови читала саме атрибут — перевірка проходила по
     старому документу й зеленіла на мертвому «Проєкті», а падала аж на
     наступному рядку невиразним `Cannot read properties of undefined`.

     Далі перевірка НЕГАЙНА, без `waitForFunction` на самому `CanvasInspector`,
     — і це принципово: `type="module"` відкладений за визначенням, тобто до
     `load` документа він або вже виконався, або не виконається НІКОЛИ.
     Очікування з таймаутом тут не додало б надійності, зате перетворило б
     «тега немає взагалі» (баг 02.09.2026) на невиразний таймаут замість
     зрозумілого «інспектора немає в аудиторії «Проєкт»». */
  await page.waitForFunction(() => {
    const w = (document.getElementById("frame") || {}).contentWindow;
    return !!(w && /[?&]ch=project/.test(w.location.href)
      && w.document.readyState === "complete");
  }, null, { timeout: 15000 });

  assert.equal(
    await page.evaluate(() => typeof document.getElementById("frame")
      .contentWindow.CanvasInspector),
    "object",
    "інспектора немає в аудиторії «Проєкт» — сніпет коментарів не везе inspector.js",
  );

  await page.click('#hud [data-act="inspector"]');

  /* Обидві половини одного стану, і обидві негайно: `BAR_ACTIONS.inspector`
     синхронна, тож на момент повернення кліку і оверлей, і панель мусять уже
     бути на місці (той самий аргумент, що в `tests/live/shell-inspect.test.mjs`
     A). Негайність тут — не педантизм: поки в `app.js` стояло опитування
     (300мс, знято 17.09.2026), перевірка з таймаутом лишалась би зеленою й
     на забутій дії, бо опитування підмінило б її собою. Опитування немає, і
     негайність тепер стереже вже не його, а сам синхронний шлях. */
  assert.equal(
    await page.evaluate(() => document.getElementById("frame")
      .contentWindow.CanvasInspector.on),
    true,
    "кнопка смуги мусить увімкнути оверлей і в аудиторії «Проєкт»",
  );
  assert.equal(await page.locator("#insp-panel").isVisible(), true,
    "права панель інспектора мусить зʼявитись і в аудиторії «Проєкт»");

  /* Банер «Коментарі недоступні» МУСИТЬ висіти (адаптер ми зарізали) — саме він
     доводить, що інспектор піднявся НЕЗАЛЕЖНО від коментарів, а не тому, що
     блокування випадково не спрацювало і сторінка жила звичайним життям. */
  assert.equal(
    await page.evaluate(() => !!document.getElementById("frame")
      .contentWindow.document.getElementById("cl-down")),
    true,
    "адаптер зарізаний, а банера немає — блокування не спрацювало, перевірка порожня",
  );
  assert.deepEqual(net.outside, [], `запити за межі машини:\n${net.outside.join("\n")}`);
});
