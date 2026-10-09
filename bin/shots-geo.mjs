/**
 * Геометрія кадру (T-45): де на знімку лежить кожен елемент сторінки — щоб піни
 * коментарів сіли на «Огляді» туди ж, куди в живому виді.
 *
 * ⛔ Знімається ТУТ, у затворі, а не в оболонці. Лише тут сторінка в тій самій
 * розкладці, що дала пікселі кадру: прокручено (`scrollPass`), ліниве
 * розморожено, анімації дограли й заморожені (`settle`), прокрутка знову в нулі.
 * Прихована копія сторінки в оболонці цього стану не повторить — reduced-motion
 * там не емулюється, reveal-анімації не стартують, — і пін сідав би поряд із
 * місцем, про яке коментар.
 *
 * Алгоритм — `window.CommentLayerAnchor` з `app/vendor/anchor.min.js`, тобто
 * ТОЙ САМИЙ відбиток, що бере comment-layer у живому виді. Своєї копії тут
 * немає свідомо: друга реалізація розійшлась би з першою мовчки.
 */
import { readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** Версія формату. Піднімаєш — усі кадри ТИХО перезнімуться (`geoMissingIds`). */
/* 2 (29.09.2026, етап 2 T-45): прапорці `hid`/`pe` для наведення. До випуску
   T-45 — кадри v1 існують лише на стендах гілки. */
export const GEO_VERSION = 2;

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const ANCHOR_BUNDLE = path.join(ROOT, "app", "vendor", "anchor.min.js");

/**
 * Геометрія відкритої сторінки. Кличеться ПІСЛЯ кадру: затвор уже заморозив
 * сторінку, прямокутники більше не їдуть.
 *
 * `<script>` лягає в `<head>`: шляхи елементів рахуються від `body`, тож
 * вставка їх не зсуває.
 */
export async function captureGeo(page) {
  await page.addScriptTag({ content: readFileSync(ANCHOR_BUNDLE, "utf8") });
  const g = await page.evaluate(() => window.CommentLayerAnchor.geometry(document.body));
  return { v: GEO_VERSION, els: g.els, truncated: g.truncated };
}

/** Атомарно: унікальний `.tmp` + rename, як `writeManifest` — битого JSON посеред
 *  прогону на диску не буває, навіть коли прогін убили. */
export function writeGeo(file, geo) {
  const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
  writeFileSync(tmp, JSON.stringify(geo));
  renameSync(tmp, file);
}

/**
 * Кадри, які Є, але без геометрії поточної версії.
 *
 * Окремо від `staleIds` навмисно. `stale` малює на картці бейдж «застаріло», а
 * дизайн тут не змінювався — змінився інструмент. Бейдж відправив би дизайнера
 * шукати правку, якої немає. Тому ці кадри йдуть лише в ПЕРЕЛІК на перезйомку
 * (`runCheck`/`runShoot`), а прапорець `stale` у манифесті лишається чесним.
 *
 * `geoProblem` — пробували на цьому штампі й не вийшло. Без цієї умови такий
 * кадр перезнімався б на кожному вході в «Огляд» вічно. Новий штамп (правка
 * макета) знімає кадр заново, і там геометрію спробують ще раз.
 */
export function geoMissingIds(manifest, ids) {
  const shots = (manifest && manifest.shots) || {};
  return ids.filter((id) => {
    const s = shots[id];
    return Boolean(s) && !s.geoProblem && (!s.geo || s.geo.v !== GEO_VERSION);
  });
}
