import assert from "node:assert/strict";
import test from "node:test";

import {
  CANVAS_PRESETS, CANVAS_W, MAX_W, MIN_W, PRESETS,
  activePreset, frameKey, parseWidth, readStored, splitFrameKey, storeValue,
} from "../app/viewport.js";

/* Пресети — реальні пристрої, а не власні брейкпоінти макетів (рішення дизайнера
   01.09.2026). Сенс саме в розбіжності: макети в design-work мають
   `max-width:760px`, і планшет 768 його НЕ вмикає — перемикач мусить показати цю
   дірку, а не сховати її, підсунувши 760. */
test("пресети: десктоп без ширини, планшет 768, мобайл 375", () => {
  assert.deepEqual(PRESETS.map((p) => p.id), ["desktop", "tablet", "mobile"]);
  assert.deepEqual(PRESETS.map((p) => p.w), [null, 768, 375]);
});

/* `null` — це ПОВНОПРАВНЕ значення «десктоп, вільна ширина вікна», а не «нічого
   не вибрано». Тому підсвітка сегмента виводиться з однієї величини (ширини), а
   не з другого прапорця «режим»: два джерела правди тут розійшлися б на першому
   ж «вибрав пресет → ввів те саме число руками». */
test("активний сегмент виводиться з ширини, і null — це десктоп", () => {
  assert.equal(activePreset(null), "desktop");
  assert.equal(activePreset(768), "tablet");
  assert.equal(activePreset(375), "mobile");
});

test("ширина поза пресетами — це «своя», жоден сегмент не активний", () => {
  assert.equal(activePreset(900), null);
  assert.equal(activePreset(1), null);
});

test("довільна ширина: число з поля стає шириною", () => {
  assert.deepEqual(parseWidth("900"), { ok: true, w: 900, clamped: false });
  assert.deepEqual(parseWidth(1024), { ok: true, w: 1024, clamped: false });
});

/* «768px» — те, що людина копіює з девтулзів чи з медіа-запиту. Відкидати такий
   ввід означало б вимагати від дизайнера чистити рядок руками. */
test("хвіст px і пробіли не ламають ввід", () => {
  assert.deepEqual(parseWidth(" 768 px "), { ok: true, w: 768, clamped: false });
  assert.deepEqual(parseWidth("390PX"), { ok: true, w: 390, clamped: false });
});

test("дробове округлюється — пікселя 0.5 у ширини рамки не буває", () => {
  assert.deepEqual(parseWidth("390.4"), { ok: true, w: 390, clamped: false });
  assert.deepEqual(parseWidth("390.6"), { ok: true, w: 391, clamped: false });
});

/* Порожнє поле — НЕ «десктоп». Людина стерла число, щоб набрати нове; якби
   порожнє тлумачилось як десктоп, рамка б стрибала на повну ширину на кожному
   символі, який стирають. Тому це відмова, а не значення. */
test("порожній ввід — відмова, а не перехід на десктоп", () => {
  assert.deepEqual(parseWidth(""), { ok: false, reason: "empty" });
  assert.deepEqual(parseWidth("   "), { ok: false, reason: "empty" });
  assert.deepEqual(parseWidth(null), { ok: false, reason: "empty" });
});

test("нечисло — відмова з причиною, а не тихий NaN у ширині рамки", () => {
  assert.deepEqual(parseWidth("широко"), { ok: false, reason: "nan" });
  assert.deepEqual(parseWidth("12abc"), { ok: false, reason: "nan" });
  assert.deepEqual(parseWidth("1e5"), { ok: false, reason: "nan" });
});

/* Затискаємо, а не відкидаємо: «20» — це не помилка вводу, це намір «якнайвужче».
   Відмова лишила б поле з числом, якого немає на екрані, тобто поле брехало б.
   А `clamped` існує, щоб інтерфейс міг сказати вголос, що число підмінили. */
test("замала й завелика ширина затискаються, і це видно в результаті", () => {
  assert.deepEqual(parseWidth("20"), { ok: true, w: MIN_W, clamped: true });
  assert.deepEqual(parseWidth("0"), { ok: true, w: MIN_W, clamped: true });
  assert.deepEqual(parseWidth("-500"), { ok: true, w: MIN_W, clamped: true });
  assert.deepEqual(parseWidth("99999"), { ok: true, w: MAX_W, clamped: true });
});

test("межі діапазону самі затиску не підлягають", () => {
  assert.deepEqual(parseWidth(String(MIN_W)), { ok: true, w: MIN_W, clamped: false });
  assert.deepEqual(parseWidth(String(MAX_W)), { ok: true, w: MAX_W, clamped: false });
});

/* Персист мусить робити коло. Найтонше місце — саме десктоп: якби він зберігався
   як порожній рядок, то читання не відрізнило б «людина вибрала десктоп» від
   «у цьому браузері ще нічого не вибирали», і обидва випадки дали б однаковий
   результат лише випадково. Тому в сховищі лежить слово. */
test("персист робить коло, і десктоп зберігається словом", () => {
  assert.equal(storeValue(null), "desktop");
  assert.equal(storeValue(768), "768");
  assert.equal(readStored(storeValue(null)), null);
  assert.equal(readStored(storeValue(768)), 768);
  assert.equal(readStored(storeValue(900)), 900);
});

test("побите сховище читається як десктоп, а не валить інструмент", () => {
  assert.equal(readStored(null), null);
  assert.equal(readStored(undefined), null);
  assert.equal(readStored(""), null);
  assert.equal(readStored("{}"), null);
});

/* Сховище пережило зміну діапазону (або його правили руками) — читаємо через ту
   саму воронку, що й ввід, інакше в `--cv-vpw` потрапило б 99999px і рамка
   поїхала б за край без жодної помилки. */
test("значення зі сховища проходять той самий затиск, що й ввід", () => {
  assert.equal(readStored("99999"), MAX_W);
  assert.equal(readStored("1"), MIN_W);
});

/* Суфікс ЛИШЕ для не-типової ширини. Це не косметика: саме через це наявні
   знімки й манифести лишаються валідними, і фіча не тягне за собою міграцію
   й масовий перезнім тисяч уже знятих кадрів. */
test("типова ширина не додає суфікса — наявні ключі не змінюються ані на символ", () => {
  assert.equal(frameKey("holovna", CANVAS_W), "holovna");
  assert.equal(frameKey("poshuk~48d0ed7a", CANVAS_W), "poshuk~48d0ed7a");
  assert.equal(CANVAS_W, 1280, "типова = та, якою знімали досі");
});

test("не-типова ширина додає суфікс, і кадр стану теж", () => {
  assert.equal(frameKey("holovna", 768), "holovna@768");
  assert.equal(frameKey("poshuk~48d0ed7a", 390), "poshuk~48d0ed7a@390");
});

test("розбір ключа назад — рівно те, з чого його зібрали", () => {
  assert.deepEqual(splitFrameKey("holovna"), { key: "holovna", w: CANVAS_W });
  assert.deepEqual(splitFrameKey("holovna@768"), { key: "holovna", w: 768 });
  assert.deepEqual(splitFrameKey("poshuk~48d0ed7a@390"), { key: "poshuk~48d0ed7a", w: 390 });
});

/* Коло мусить замикатись на всіх ширинах, інакше лічильник і зʼємка рахували б
   різні множини кадрів — саме той клас розходження, через який у цьому проєкті
   вже переписували формулу лічильника. */
test("frameKey і splitFrameKey — обернені одне одному", () => {
  for (const w of [CANVAS_W, 768, 375]) {
    for (const k of ["holovna", "main", "poshuk~48d0ed7a"]) {
      assert.deepEqual(splitFrameKey(frameKey(k, w)), { key: k, w });
    }
  }
});

/* `@` у id сторінки бути не може: слаг збирається з `[^a-z0-9]+` як роздільником,
   а `NAME_RE` — `[\w-]+`. Тому роздільник однозначний. Але ключ приїжджає ще й з
   манифеста, який лежить у теці задачі з чужої машини, — тож сміття не сміє
   прикидатись шириною. */
test("сміття замість ширини не стає шириною", () => {
  assert.deepEqual(splitFrameKey("holovna@"), { key: "holovna@", w: CANVAS_W });
  assert.deepEqual(splitFrameKey("holovna@abc"), { key: "holovna@abc", w: CANVAS_W });
  assert.deepEqual(splitFrameKey("holovna@0"), { key: "holovna@0", w: CANVAS_W });
});

/* У «Огляді» поля довільної ширини немає — там кожна ширина це окремий набір
   знімків на диску й окремий прогін браузера (див. §E спеки). */
test("пресети полотна — три, і десктоп у них ЧИСЛО, а не null", () => {
  assert.deepEqual(CANVAS_PRESETS.map((p) => p.id), ["desktop", "tablet", "mobile"]);
  assert.deepEqual(CANVAS_PRESETS.map((p) => p.w), [CANVAS_W, 768, 375]);
});

/* Ревʼю 29.09.2026 (D8): підказка пресета — теж число, і вона казала «390px», коли
   пресет уже був 375, жоден тест цього б не помітив. Звіряємо текст підказки з
   САМИМ пресетом у обох мовах, а не з літералом. */
test("підказка мобайла називає ту ж ширину, що й пресет — в обох мовах", async () => {
  const { setLang } = await import("../app/i18n.js");
  const mobile = PRESETS.find((p) => p.id === "mobile");
  for (const lang of ["uk", "en"]) {
    setLang(lang);
    assert.match(mobile.hint, new RegExp(`\\b${mobile.w}px\\b`), `${lang}: ${mobile.hint}`);
  }
  setLang("uk");
});
