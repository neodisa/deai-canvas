/**
 * Затвор: коли сторінку можна знімати.
 *
 * Порядок кроків не косметичний, кожен закриває свій спосіб збрехати:
 *   1. НЕ ЛІНИВО — ліниві картинки в headless не завантажаться ніколи, бо сторінка
 *      не скролиться. Двічі з паузою: компонент, що домалювався пізно, приносить
 *      свої ліниві картинки.
 *   1.5 ПРОКРУЧЕНО — прохід скролом до низу і назад. Затвор чесно доводив
 *      анімації, які СТАРТУВАЛИ, але анімації входу по скролу (IntersectionObserver,
 *      reveal-класи з `opacity:0` до появи) не стартують взагалі: сторінка не
 *      скролилась жодного разу, а кадр робиться `captureBeyondViewport`. Тому
 *      `getAnimations()` їх не бачив, чекання «усі дограли» проходило порожнім, і
 *      блок їхав у кадр невидимим. Два байт-ідентичні знімки це теж не ловлять:
 *      порожній блок стабільний (фідбек 03.09.2026).
 *   2. ЗАВАНТАЖЕНО — документ, непорожній текст, шрифти, кожна картинка.
 *      «readyState: complete» замало: сторінка буває complete з порожнім body.
 *   3. ПІДЛОГА — одноразову анімацію входу не можна зловити на пів дорозі.
 *   4. ЗАВЕРШЕНО — нескінченні анімації спершу на паузу (інакше чекання решти
 *      ніколи не скінчиться), потім чекаємо, поки решта дограє. Анімації саме
 *      ДОГРАЮТЬ, а не вимикаються: у кадрі мусить бути той дизайн, до якого
 *      анімація веде.
 *   5. ЗАМОРОЖЕНО — стиль-заморозка, пауза решти, blur: каретка блимає без
 *      жодної анімації й одна ламає доказ стабільності.
 *   6. СТАБІЛЬНО — два байт-ідентичні знімки. Найдешевший міцний доказ того, що
 *      сторінка справді стала: та, що ще їде, двічі однаково не вийде.
 *   7. ПОРАХОВАНО — скільки великих блоків із вмістом лишились невидимими попри
 *      все вище. Прохід скролом закриває типовий випадок, але не всі: reveal,
 *      прив'язаний до справжніх подій миші/клавіатури, лишиться прихованим. Такий
 *      блок мусить бути НАЗВАНИМ у манифесті, а не мовчазною дірою в кадрі.
 */
export const SETTLE_FLOOR_MS = 1200;
export const BYTES_FLOOR = 6000;
/**
 * ТИПОВИЙ вьюпорт зʼємки, а не єдиний. Ширина 1280 — це типова ширина картки
 * (`CARD_W` у `app/canvas-geom.js`): знятий нею кадр лягає в карточку 1:1, без
 * масштабу. Але полотно можна дивитись і в іншій ширині, і тоді затвор знімає
 * саме нею — `viewportFor(w)` і `shootOnce(page, w)`.
 * Висота лишається типовою за будь-якої ширини: вона не про пристрій, а про те,
 * скільки сторінки бачить браузер до розгортання на всю висоту.
 */
export const VIEWPORT = { width: 1280, height: 900 };
export const MAX_PAGE_H = 8000;
export const SETTLE_TIMEOUT_MS = 45000;

/** Вьюпорт заданої ширини. Висота лишається типовою — див. `VIEWPORT`. */
export function viewportFor(width) {
  return { width: width || VIEWPORT.width, height: VIEWPORT.height };
}

const UNLAZY = () => {
  for (const img of document.images) {
    img.loading = "eager";
    img.decoding = "sync";
  }
};

const FREEZE_CSS = "*,*::before,*::after{animation-play-state:paused!important;" +
  "animation-delay:0s!important;transition:none!important;caret-color:transparent!important}";

/**
 * Прохід скролом до низу і назад — щоб анімації входу СТАРТУВАЛИ.
 *
 * Крок — майже вьюпорт (0.9), щоб жоден блок не перестрибнули: `IntersectionObserver`
 * із порогом «видно 10%» на рівно-вьюпортному кроці може не спрацювати на межі.
 * Висоту читаємо на КОЖНІЙ ітерації: сторінка росте під час проходу, коли
 * підвантажується ліниве. `maxSteps` — стеля проти нескінченного скролу
 * (стрічка, що дописує вміст без кінця): кращий обрізаний прохід, ніж зависання.
 * Повертаємось у нуль: `captureBeyondViewport` знімає від початку документа, а
 * `position: sticky/fixed` малюється відносно поточного скролу — з середини
 * сторінки шапка лягла б у кадр посеред тексту.
 *
 * ⚠️ Прокручується ВІКНО. Макет, який скролиться всередині свого контейнера
 * (`overflow:auto` на обгортці — типово для SPA-оболонок), цим проходом не
 * зачепиться; такий випадок ловиться лічильником `hiddenBlocks` нижче.
 */
export async function scrollPass(page, { stepPause = 120, maxSteps = 24 } = {}) {
  return page.evaluate(async ({ stepPause, maxSteps }) => {
    const sleep = (ms) => new Promise((r) => { setTimeout(r, ms); });
    const step = Math.max(200, Math.round(window.innerHeight * 0.9));
    let y = 0;
    let steps = 0;
    while (steps < maxSteps) {
      const bottom = document.documentElement.scrollHeight - window.innerHeight;
      if (y >= bottom) break;
      y = Math.min(y + step, bottom);
      window.scrollTo(0, y);
      steps += 1;
      await sleep(stepPause);
    }
    window.scrollTo(0, 0);
    await sleep(stepPause);
    return steps;
  }, { stepPause, maxSteps });
}

/**
 * Великі блоки з вмістом, які лишились невидимими. Рахуємо ПІСЛЯ заморозки —
 * коли все, що мало догратись, уже дограло.
 *
 * Рахуємо лише ВЕРХНІ: у прихованого блока приховані й усі нащадки, і без цього
 * один невидимий екран давав би десятки. Поріг розміру відсікає технічні
 * дрібниці, а вимога вмісту — порожні обгортки, невидимість яких у кадрі ніяк не
 * видно.
 *
 * ⛔ Рахуємо лише елементи В ПОТОЦІ (`static`/`relative`/`sticky`). Це не
 * прискіпливість, а сама суть дефекту: діру в кадрі лишає той, хто ЗАЙМАЄ МІСЦЕ
 * в розкладці й не малюється. Спливні підказки й модалки — `absolute`/`fixed`,
 * вони місця не займають, сторінка без них зверстана однаково, і без цієї умови
 * будь-який тултип `opacity:0` давав би хибну тривогу на кожному макеті.
 *
 * ⛔ І не рахуємо вміст прихованого out-of-flow предка (fb-30092026-7bbc33):
 * `visibility` успадковується, тож список у підказці теж «невидимий і в потоці».
 */
export async function hiddenBlockCount(page) {
  return page.evaluate(() => {
    const IN_FLOW = new Set(["static", "relative", "sticky"]);
    const OUT_OF_FLOW = new Set(["absolute", "fixed"]);
    /* fb-30092026-7bbc33: `visibility` УСПАДКОВУЄТЬСЯ, тож static-нащадок
       прихованої спливної підказки сам «невидимий і в потоці» — у потоці
       підказки, а не сторінки. Вирішує найближчий out-of-flow предок: прихований
       він — і весь його вміст лише частина прихованої підказки. */
    const insideHiddenOverlay = (el) => {
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        const s = getComputedStyle(a);
        if (OUT_OF_FLOW.has(s.position)) return s.visibility === "hidden" || s.opacity === "0";
      }
      return false;
    };
    const invisible = [];
    for (const el of document.body.querySelectorAll("*")) {
      const r = el.getBoundingClientRect();
      if (r.width < 100 || r.height < 40) continue;
      const cs = getComputedStyle(el);
      if (cs.opacity !== "0" && cs.visibility !== "hidden") continue;
      if (!IN_FLOW.has(cs.position)) continue;
      if (insideHiddenOverlay(el)) continue;
      const hasContent = el.textContent.trim().length > 0
        || el.querySelector("img,svg,canvas,video,picture");
      if (!hasContent) continue;
      invisible.push(el);
    }
    return invisible.filter(
      (el) => !invisible.some((other) => other !== el && other.contains(el)),
    ).length;
  });
}

export async function settle(page) {
  await page.evaluate(UNLAZY);
  await page.waitForTimeout(400);
  await page.evaluate(UNLAZY);

  /* Прохід скролом СТАРТУЄ анімації входу — тому він тут, до чекання «усі
     анімації дограли»: інакше чекати не було б чого. Заодно добиває ліниві
     картинки, яких `UNLAZY` не дістав. */
  const scrolled = await scrollPass(page);

  /* «СТАЛО» = сторінка щось НАМАЛЮВАЛА, і текст тут не єдиний спосіб. Вимога
     непорожнього innerText висіла б усі 45 секунд на повноекранній ілюстрації або
     хіро-банері без підпису — легітимному типі макета — і потім кидала. Тому:
     текст АБО хоч одна завантажена картинка. Знайдено рев'ю на живому Chromium.

     І таймаут тут НЕ кидає: сторінка, яка так і не стала, мусить дати кадр із
     гучним прапорцем `neverSettled`, а не вбити прогін решти сторінок. Це той
     самий принцип, що вже стоїть на чеканні анімацій нижче. */
  const settled = await page.waitForFunction(() => document.readyState === "complete"
    && document.fonts.status === "loaded"
    && [...document.images].every((img) => img.complete)
    && (document.body.innerText.trim().length > 0
        || [...document.images].some((img) => img.naturalWidth > 0)),
  null, { timeout: SETTLE_TIMEOUT_MS }).then(() => true).catch(() => false);

  await page.waitForTimeout(SETTLE_FLOOR_MS);

  const pausedMidFlight = await page.evaluate(() => {
    let n = 0;
    for (const anim of document.getAnimations()) {
      if (anim.effect?.getComputedTiming?.().iterations === Infinity) {
        anim.pause();
        n += 1;
      }
    }
    return n;
  });
  // Не дограло за 9с — це нотатка в манифесті, а не причина не знімати.
  await page.waitForFunction(
    () => document.getAnimations().every((a) => a.playState !== "running"),
    null, { timeout: 9000 },
  ).catch(() => {});

  await page.addStyleTag({ content: FREEZE_CSS });
  await page.evaluate(() => {
    for (const anim of document.getAnimations()) anim.pause();
    for (const video of document.querySelectorAll("video")) video.pause();
    // Каретку гасять ОБА: `blur()` знімає ще й обводку фокуса й aria-стани, які
    // видно в кадрі, а `caret-color` у FREEZE_CSS — страховка, якщо щось поверне
    // фокус між цим кроком і затвором.
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  });

  const empty = await page.evaluate(() => [...document.images]
    .filter((img) => img.naturalWidth === 0 || img.naturalHeight === 0).length);
  const hiddenBlocks = await hiddenBlockCount(page);
  return { pausedMidFlight, emptyImages: empty, neverSettled: !settled,
           scrolled, hiddenBlocks };
}

/**
 * Один знімок, WebP через CDP: helper Playwright WebP не вміє. Знімаємо ВСЮ
 * сторінку (`captureBeyondViewport` + явний clip), бо картка в «Огляді» і сьогодні
 * показує макет на всю висоту — знімок вьюпорта був би втратою того, що вже є.
 */
export async function shootOnce(page, width = VIEWPORT.width) {
  const full = await page.evaluate(() => document.documentElement.scrollHeight);
  const height = Math.min(Math.max(full, VIEWPORT.height), MAX_PAGE_H);
  /* Сторінка вища за стелю — кадр буде ОБРІЗАНИЙ, і про це мусить бути сказано.
     Інакше на канвасі лежить кадр, який тихо показує менше, ніж є у макеті:
     формально манифест не бреше (`h` = 8000), але дизайнер бачить обрубану
     сторінку без жодної позначки. Знайдено на першому ж прогоні по справжньому
     макету — стаття блогу виявилась вищою за 8000px. */
  const truncated = full > MAX_PAGE_H;
  const cdp = await page.context().newCDPSession(page);
  try {
    const { data } = await cdp.send("Page.captureScreenshot", {
      format: "webp",
      quality: 92,
      captureBeyondViewport: true,
      clip: { x: 0, y: 0, width, height, scale: 1 },
    });
    return { buf: Buffer.from(data, "base64"), w: width, h: height, truncated, full };
  } finally {
    // Сесію відпускаємо і на помилці: shootStable кличе це до пʼяти разів підряд.
    await cdp.detach().catch(() => {});
  }
}

/** Знімаємо, поки два підряд не зійдуться байт у байт. `width` необовʼязкова:
    без неї затвор бере типову ширину — тому наявні виклики `shootStable(page)`
    працюють як і раніше. */
export async function shootStable(page, tries = 5, width) {
  let prev = null;
  for (let attempt = 1; attempt <= tries; attempt += 1) {
    const shot = await shootOnce(page, width);
    if (prev && prev.buf.equals(shot.buf)) return { ...shot, stable: true, tries: attempt };
    prev = shot;
    await page.waitForTimeout(600);
  }
  return { ...prev, stable: false, tries };
}
