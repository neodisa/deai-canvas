/*!
 * Вхід бандла `dist/anchor.min.js` → `window.CommentLayerAnchor`.
 * Для тих, хто не ESM: затвор канваса кладе його в сторінку (`page.addScriptTag`)
 * і знімає геометрію кадру, оболонка «Огляду» бере тегом і шукає піни по ній.
 * Одна реалізація алгоритму на три місця — див. шапку `anchor.js`.
 */
import * as A from './anchor.js';

window.CommentLayerAnchor = Object.freeze({ ...A });
