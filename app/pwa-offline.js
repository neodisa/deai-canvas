/**
 * Сторінка «Канвас не запущено» — те, що service worker (`sw.js`) віддає замість
 * канваса, коли навігація не дійшла до сервера (сервер не піднято, мережі нема).
 *
 * ⛔ ЧОМУ СТОРІНКУ ЗБИРАЄ КОД, А НЕ ЛЕЖИТЬ ГОТОВИЙ `offline.html`.
 *  · Тексту дозволено бути лише в `i18n.js` (охоронець `tests/i18n-literals`
 *    забороняє кирилицю в літералах решти `app/**`), а мов у застосунку дві.
 *    Статичний HTML або дублював би словник, або був би однією мовою.
 *  · Готовому файлу довелось би кудись ЛЕЖАТИ, поки сервера нема, тобто у
 *    CacheStorage. Тоді worker уже не «лише мережа»: з'являється кеш із версіями,
 *    інвалідацією й можливістю показати застарілу сторінку. Тут кешу нема зовсім:
 *    модуль статично імпортується з `sw.js`, а браузер зберігає імпортовані
 *    модулі разом зі скриптом worker і перевіряє їх при кожному оновленні.
 *  · Логотип — той самий `LOGO_SVG`, що в смузі, інлайном: окремий значок-файл
 *    теж довелось би кешувати.
 *
 * Модуль ЧИСТИЙ (ні DOM, ні `self`, ні сховища) — як `i18n.js`: його імпортує і
 * worker, і юніт у Node. Мову обирає не він, а крихітний скрипт у самій сторінці:
 * worker не бачить `localStorage`, а документ — бачить. Тому сторінка несе ОБИДВІ
 * мови, і видимою лишається та, що в `dc-lang`.
 *
 * Самодостатня за конструкцією: жодного `<link>`, `<img>`, `src`, `url()` —
 * ресурсу, який можна було б завантажити без сервера, нема. Це стереже юніт.
 */
import { LANGS, LANG_KEY, getLang, setLang, t } from "./i18n.js";
import { esc } from "./esc.js";
import { LOGO_SVG } from "./logo.js";

/* Кольори — з погодженої палітри оболонки (`styles.css`): фон `--s1`, текст
   `--hi`/`--mid`, чіп коду `--s2`, межа `--line`, кнопка — моно-акцент `--sel`
   із темним `--on-sel`. Власна таблиця, а не `styles.css`: файл теж лежить на
   сервері, якого нема. Класи без префіксів сітки висот (`ctl`/`seg`/…), бо це
   окрема сторінка, а не частина оболонки. */
const STYLE = `
:root{color-scheme:dark;--bg:#29332E;--hi:#F3F8F5;--mid:#CBD3CF;--s2:#323C36;--line:#3C4741;
  --sel:#E2EAE6;--sel-hover:#F2F6F4;--on-sel:#1A231E;--logo:#969F9A;--logo-in:#fff}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;display:grid;place-items:center;padding:24px;background:var(--bg);color:var(--hi);
  font:14px/1.5 system-ui,sans-serif}
main{width:min(480px,100%)}
.logo{display:block;width:64px;height:64px;margin:0 0 28px;color:var(--logo)}
h1{margin:0 0 8px;font-size:22px;font-weight:600;line-height:1.25}
p{margin:0 0 20px;color:var(--mid)}
ul{margin:0 0 24px;padding:0;list-style:none;display:grid;gap:10px;color:var(--mid)}
code{display:inline-block;white-space:nowrap;padding:1px 8px;border:1px solid var(--line);border-radius:6px;
  background:var(--s2);color:var(--hi);font:13px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
button{height:32px;padding:0 16px;border:0;border-radius:8px;background:var(--sel);color:var(--on-sel);
  font:inherit;font-weight:600;cursor:pointer}
button:hover{background:var(--sel-hover)}
button:focus-visible{outline:2px solid var(--sel);outline-offset:2px}
[hidden]{display:none}
`;

/* Вибір мови — у самій сторінці. `LANGS[0]` — типова (так порядок описано в
   `i18n.js`); невідоме чи відсутнє значення дає її ж, як і `readStoredLang`.
   Заголовок вкладки береться з видимого `<h1>`, щоб не нести другого джерела. */
const SCRIPT = `(function(){
  var langs=${JSON.stringify(LANGS)},v=null;
  try{v=localStorage.getItem(${JSON.stringify(LANG_KEY)});}catch(e){}
  var lang=langs.indexOf(v)>=0?v:langs[0];
  document.documentElement.lang=lang;
  var secs=document.querySelectorAll("section[lang]");
  for(var i=0;i<secs.length;i++){
    secs[i].hidden=secs[i].lang!==lang;
    if(!secs[i].hidden)document.title=secs[i].querySelector("h1").textContent;
  }
  var btns=document.querySelectorAll("button");
  for(var j=0;j<btns.length;j++)btns[j].addEventListener("click",function(){location.reload();});
})();`;

/** Один блок тексту однією мовою. Мову перемикаємо тимчасово — `t()` читає
 *  глобальну, — і повертаємо назад: модуль не сміє лишати слід у чистому
 *  `i18n.js`, навіть коли його кличе тест у спільному процесі. */
function section(lang) {
  const prev = getLang();
  setLang(lang);
  try {
    return `<section lang="${lang}"${lang === LANGS[0] ? "" : " hidden"}>
<h1>${esc(t("pwaOffTitle"))}</h1>
<p>${esc(t("pwaOffLead"))}</p>
<ul>
<li>${esc(t("pwaOffMac"))} <code>start.command</code></li>
<li>${esc(t("pwaOffWin"))} <code>python app/serve.py</code></li>
</ul>
<button type="button">${esc(t("pwaOffRetry"))}</button>
</section>`;
  } finally {
    setLang(prev);
  }
}

/** Повний HTML сторінки. Заголовок вкладки — українська (типова) до спрацювання
 *  скрипта; скрипт замінює його на видимий `<h1>`. */
export function offlineHTML() {
  const prev = getLang();
  setLang(LANGS[0]);
  let title;
  try { title = esc(t("pwaOffTitle")); } finally { setLang(prev); }
  return `<!DOCTYPE html><html lang="${LANGS[0]}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<style>${STYLE}</style></head><body>
<main>
${LOGO_SVG}
${LANGS.map(section).join("\n")}
</main>
<script>${SCRIPT}</script>
</body></html>`;
}
