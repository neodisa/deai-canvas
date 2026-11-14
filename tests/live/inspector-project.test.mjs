/**
 * Живий тест: інспектор ДС мусить працювати в аудиторії «Проєкт».
 * (0.27.0: каналів нема — тест перевіряє, що інспектор живий у рамці робочого місця й за мертвого командного сховища.)
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

test("командне сховище мертве (адаптер модуля не вантажиться): інспектор живий, кнопка смуги його відкриває", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  const net = await hermeticLiga(page);
  await page.route(MODULE_ADAPTER_GLOB, (route) => route.abort());
  await page.goto(`${url}/app/`);

  /* 0.27.0: каналів нема — рамка робочого місця завжди комбінована (Claude + команда), а мертвий адаптер команди лишає
     коментатора живим на локальному (`store.teamDown`). Дочекатись рамки з піднятим коментатором (він на локальному) і
     інспектором ТУТ обовʼязково: інакше падіння нижче не відрізнило б «з мертвою командою інспектора немає» від «сервер
     узагалі не віддає vendor». Перемикання аудиторії через ⌘K (`setAudience`) зникло разом із самим перемикачем. */
  await page.waitForFunction(() => {
    const w = (document.getElementById("frame") || {}).contentWindow;
    return !!(w && w.document.readyState === "complete" && w.CommentLayer && w.CommentLayer._inited && w.CanvasInspector);
  }, null, { timeout: 15000 });

  assert.equal(
    await page.evaluate(() => typeof document.getElementById("frame").contentWindow.CanvasInspector),
    "object",
    "інспектора немає в рамці з мертвим командним сховищем — сніпет коментарів не везе inspector.js",
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

  /* Свідок, що адаптер справді мертвий: комбіноване сховище каже причину (`teamDown`), а банера `#cl-down` нема — з 0.27.0
     падіння команди показує смуга в панелі коментарів, банер лишився лише для падіння самого шару чи локального адаптера. */
  const st = await page.evaluate(() => {
    const w = document.getElementById("frame").contentWindow;
    return { down: w.CommentLayer.store.teamDown, banner: !!w.document.getElementById("cl-down") };
  });
  assert.equal(typeof st.down, "string", "адаптер зарізаний, а teamDown порожній — блокування не спрацювало, перевірка порожня");
  assert.ok(st.down.length > 0);
  assert.equal(st.banner, false, "банер «Коментарі недоступні» у робочому місці при падінні лише командного");
  assert.deepEqual(net.outside, [], `запити за межі машини:\n${net.outside.join("\n")}`);
});
