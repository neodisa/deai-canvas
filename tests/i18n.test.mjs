import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { DICT, LANG_KEY, LANGS, getLang, readStoredLang, setLang, t } from "../app/i18n.js";

/* Безпека наступних тестів не має триматись на тому, що автор тесту №N не
   забуде повернути мову назад у `finally`/наприкінці. Скидаємо явно й
   централізовано перед кожним тестом. */
test.beforeEach(() => setLang("uk"));

/* Половина словника — це найдорожча помилка i18n: інтерфейс, який частину
   підписів показує чужою мовою, гірший за одномовний, бо виглядає зламаним.
   Тому набори ключів звіряються, а не «переглядаються очима». */
test("обидві мови мають той самий набір ключів", () => {
  const uk = Object.keys(DICT.uk).sort();
  const en = Object.keys(DICT.en).sort();
  assert.deepEqual(en, uk, "набори ключів розійшлись");
});

/* Значення буває рядком або функцією (коли в текст лізе число чи назва).
   Якщо в одній мові ключ — функція, а в другій рядок, інтерполяція тихо
   зникає: `t('pubStale', 2)` віддасть текст без двійки. Звіряємо і тип, і
   кількість аргументів. */
test("тип і арність значення однакові в обох мовах", () => {
  for (const k of Object.keys(DICT.uk)) {
    assert.equal(typeof DICT.en[k], typeof DICT.uk[k], `тип ключа «${k}»`);
    if (typeof DICT.uk[k] === "function") {
      assert.equal(DICT.en[k].length, DICT.uk[k].length, `арність ключа «${k}»`);
    }
  }
});

/* Мову перемикають на льоту (перемикач у хедері), і `t()` мусить одразу
   почати віддавати рядки нової мови — без перезавантаження модуля. */
test("t() віддає рядок поточної мови, setLang перемикає", () => {
  setLang("uk");
  assert.equal(getLang(), "uk");
  const uk = t("openFrame");
  setLang("en");
  assert.equal(getLang(), "en");
  assert.notEqual(t("openFrame"), uk);
  setLang("uk");
});

/* Невідомий ключ КИДАЄ, а не віддає своє імʼя. Тихий фолбек відправляє в
   інтерфейс підпис «openFrame» і живе там місяцями; виняток видно на першому
   ж рендері. Після зеленого тесту на повноту такий ключ узятись нізвідки. */
test("невідомий ключ кидає, а не підставляє себе", () => {
  assert.throws(() => t("немаТакогоКлюча"), /немаТакогоКлюча/);
});

/* LANGS і DICT — дві структури про одне й те саме, і розійтись їм легко:
   мову додають в одному місці, словник наповнюють у дев'яти інших. Без цієї
   звірки `setLang('fr')` проходить, а наступний `t()` кидає сирий TypeError
   на `DICT[lang]` — тобто помилка виявляється не там, де зроблена. Порядок
   теж фіксуємо: на нього спиратиметься перемикач мови. */
test("LANGS і DICT описують той самий набір мов, українська перша", () => {
  assert.deepEqual(LANGS, ["uk", "en"]);
  assert.deepEqual(Object.keys(DICT).sort(), [...LANGS].sort());
});

/* Невідома мова не має права мовчки стати поточною: `setLang` — єдине місце,
   де рядок із зовні (наприклад, зіпсоване значення в localStorage до появи
   readStoredLang) перевіряється проти LANGS. */
test("setLang кидає на невідомій мові", () => {
  assert.throws(() => setLang("fr"), /невідома мова/);
  assert.equal(getLang(), "uk", "мова не мала змінитись після відкинутого виклику");
});

/* Усе незрозуміле зі сховища — українська, а не крах застосунку. Значення
   могло лишитись від старої версії словника, бути очищене вручну чи просто
   не існувати (перший запуск). */
test("readStoredLang: відома мова проходить, усе інше — типова", () => {
  assert.equal(readStoredLang("en"), "en");
  assert.equal(readStoredLang("fr"), "uk");
  assert.equal(readStoredLang(null), "uk");
  assert.equal(readStoredLang(undefined), "uk");
});

test("LANG_KEY — рядок-ключ сховища, сам модуль localStorage не чіпає", () => {
  assert.equal(LANG_KEY, "dc-lang");
  assert.equal(typeof localStorage, "undefined", "localStorage не існує в node --test — модуль і не мав його викликати");
});

/* Гілка інтерполяції мусить бути доведена ДО того, як на неї ляжуть реальні
   рядки: значення-функція — це те, чим словник понесе числа й назви. Ключ
   заводимо в самому тесті й прибираємо після, щоб не тягти в словник нічого
   «на майбутнє». */
test("значення-функція викликається з аргументами", () => {
  DICT.uk.probeSum = (a, b) => `сума ${a + b}`;
  DICT.en.probeSum = (a, b) => `sum ${a + b}`;
  try {
    setLang("uk");
    assert.equal(t("probeSum", 2, 3), "сума 5");
    setLang("en");
    assert.equal(t("probeSum", 2, 3), "sum 5");
  } finally {
    delete DICT.uk.probeSum;
    delete DICT.en.probeSum;
    setLang("uk");
  }
});

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = fs.readFileSync(path.join(__dirname, "../app/i18n.js"), "utf8");

function extractBlock(name) {
  const m = SRC.match(new RegExp(`const ${name} = \\{([\\s\\S]*?)\\n\\};`));
  assert.ok(m, `не знайдено літерал ${name} у app/i18n.js`);
  return m[1];
}

/* Дублікат ключа в літералі JS не кидає — мовчки лишається останнє значення,
   і при 169 ключах із дев'яти задач це тихий перезапис, якого не побачить
   навіть тест на повноту (набори мов при дублікаті всередині однієї мови
   збігаються). Тому рахуємо ключі в тексті.
   Межа перевірки записана свідомо: рахуємо рядки РІВНО на базовому відступі
   блоку і тільки після вирізання блокових комментарів. Вкладений обʼєкт у тілі
   значення-функції має глибший відступ, тож законна плюралізація виду
   `pubAge: (n) => { const units = { … }; … }` хибної тривоги не дає. Того, що
   стоїть в один рядок (`a: 1, b: 2`), ця перевірка не бачить — і не мусить:
   такий стиль у цьому файлі не вживається. */
const BASE_INDENT = "  ";
function countKeyLines(block) {
  return block
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => new RegExp(`^${BASE_INDENT}(?:\\w+|'[\\w-]+')\\s*:`).test(line))
    .length;
}

test("жоден ключ не продубльовано в літералі UK/EN", () => {
  assert.equal(countKeyLines(extractBlock("UK")), Object.keys(DICT.uk).length, "дублікат ключа в UK");
  assert.equal(countKeyLines(extractBlock("EN")), Object.keys(DICT.en).length, "дублікат ключа в EN");
});
