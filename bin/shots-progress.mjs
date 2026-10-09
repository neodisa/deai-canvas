/**
 * Формат події прогресу зʼємки. Половина контракту між процесами: тут ПИШУТЬ
 * (`bin/shoot.mjs`), а читають на боці Python (`app/shoot_progress.py`).
 *
 * Події йдуть у **stderr**, а не в stdout, і це несуче: контракт stdout —
 * ОДИН фінальний JSON, який парсить `_shoot`. Домішані туди рядки зламали б
 * `json.loads(out)`, і зламали б ТИХО — там уже стоїть `except JSONDecodeError`
 * з фолбеком у `raw`, тобто дизайнер побачив би «сервер не пояснив причини».
 *
 * Маркер потрібен, бо stderr не наш: туди пишуть Node, Playwright і Chromium.
 * Рядок без маркера мусить лишитись тим, чим є сьогодні, — текстом причини.
 */
export const PROGRESS_MARK = "@shot ";

/** Подія одним рядком. `JSON.stringify` екранує переноси всередині значень. */
export function progressLine(ev) {
  return `${PROGRESS_MARK}${JSON.stringify(ev)}\n`;
}
