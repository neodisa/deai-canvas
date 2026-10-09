/**
 * Фікстура T-45 (піни на «Огляді»): сторінки з fixed-шапкою, блоком 100vh,
 * кнопкою з data-testid і гридом карток. Піни сіються ЧЕСНО: відбиток рахує
 * справжній `CommentLayerAnchor.fingerprint` у bare-сторінці, не рука.
 * Спільна для живого тесту `overview-comments.test.mjs` і ручного огляду.
 */
import { mkdirSync, mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
export const ANCHOR = readFileSync(path.join(ROOT, "app", "vendor", "anchor.min.js"), "utf8");

const CSS = `body{margin:0;font:16px/1.45 -apple-system,system-ui,sans-serif;color:#1c2333}
header{position:fixed;top:0;left:0;right:0;height:56px;box-sizing:border-box;padding:16px 32px;background:#1f3a8a;color:#fff}
.hero{height:100vh;box-sizing:border-box;padding:120px 48px 48px;background:#eef2ff}
h1{margin:0 0 16px;font-size:44px} .hero p{max-width:640px;font-size:18px}
button{font:inherit;padding:12px 22px;border-radius:10px;border:0;background:#1f3a8a;color:#fff}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;padding:48px}
.card{padding:24px;border:1px solid #d5d9e6;border-radius:12px;background:#fff}
footer{padding:32px 48px;background:#101828;color:#cbd2e1}
.search{padding:120px 48px 48px} input{font:inherit;padding:12px;width:480px;border:1px solid #aab;border-radius:8px}
ol li{padding:14px 0;border-bottom:1px solid #e4e7ee}`;

export const PAGES = {
  holovna: `<!doctype html><html lang="uk"><head><meta charset="utf-8"><title>Головна</title><style>${CSS}</style></head><body>
<header><nav id="nav">Новини · Документи · Кабінет</nav></header>
<section class="hero"><h1>Юридичні новини тижня</h1>
<p>Огляд змін законодавства, судової практики й роз'яснень регуляторів для практикуючих юристів.</p>
<button data-testid="subscribe">Підписатися на розсилку</button></section>
<section class="grid">${[1, 2, 3, 4, 5, 6].map((i) =>
    `<div class="card"><h2>Матеріал ${i}</h2><p>Короткий опис матеріалу номер ${i} для огляду.</p></div>`).join("")}</section>
<footer><p>Підвал сайту · контакти · політика</p></footer></body></html>`,
  poshuk: `<!doctype html><html lang="uk"><head><meta charset="utf-8"><title>Пошук</title><style>${CSS}</style></head><body>
<header><nav>Новини · Документи · Кабінет</nav></header>
<section class="search"><input id="q" aria-label="Пошук по базі" placeholder="Пошук по базі">
<ol>${[1, 2, 3, 4].map((i) => `<li>Результат пошуку ${i}</li>`).join("")}</ol></section></body></html>`,
};

/** Що коментуємо: сторінка → CSS-селектори цілей (по них рахується відбиток). */
export const TARGETS = {
  holovna: ["#nav", "h1", "[data-testid=subscribe]", ".card:nth-child(2) h2", ".card:nth-child(5) p", "footer p"],
  poshuk: ["#q", "ol li:nth-child(2)"],
};

export function t45Task() {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-t45-"));
  const it1 = path.join(dir, "iterations", "it1");
  for (const [page, html] of Object.entries(PAGES)) {
    mkdirSync(path.join(it1, page), { recursive: true });
    writeFileSync(path.join(it1, page, "index.html"), html);
  }
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: "Головна", published: true }, { id: "poshuk", name: "Пошук", published: true }],
  }));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [{ id: "it1", date: "29.09.2026 12:00", note: "фікстура T-45", published: true }],
  }));
  return { dir, it1 };
}

/**
 * Посіяти піни в локальний канал через справжній ендпоінт. `browser` —
 * Playwright; відбитки рахуються в bare-сторінці тим самим бандлом, що бере
 * comment-layer у живому виді.
 */
export async function seedPins(browser, url, { width = 1280 } = {}) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  const comments = [];
  let seq = 0;
  for (const [pid, sels] of Object.entries(TARGETS)) {
    await page.goto(`${url}/commented?it=it1&page=${pid}&bare=1`);
    await page.addScriptTag({ content: ANCHOR });
    const fps = await page.evaluate((ss) => ss.map((s) => {
      const el = document.querySelector(s);
      return el ? window.CommentLayerAnchor.fingerprint(el, document.body) : null;
    }), sels);
    fps.forEach((fp, i) => {
      if (!fp) throw new Error(`немає цілі ${pid} ${sels[i]}`);
      seq += 1;
      comments.push({
        id: `t45-${pid}-${i}`, author: "Фікстура", text: `Правка №${seq}: ${sels[i]}`, status: "open", fp,
        htmlSnapshot: null, bornV: 1, ts: "29.09.2026 12:00",
        meta: { url: `${url}/commented?it=it1&page=${pid}&ch=local`, route: "/commented",
                version: `1/${pid}`, iteration: "1", viewport: { w: width, h: 900 }, seq, sel: sels[i] },
      });
    });
  }
  await page.close();
  /* «Привид»: пін сторінки holovna, чийого елемента на кадрі немає (макет
     змінився). Живий вид такого не ставить; «Огляд» кладе його в лічильник
     «поза кадром» (рішення власника 29.09.2026). */
  seq += 1;
  comments.push({
    id: "t45-ghost", author: "Фікстура", text: "Правка до блока, якого вже нема", status: "open",
    fp: { tag: "marquee", stableId: null, text: "зниклий банер акції", textHash: "x", structHash: "x", styleHash: "x", path: ["marquee[0]"] },
    htmlSnapshot: null, bornV: 1, ts: "29.09.2026 12:00",
    meta: { url: `${url}/commented?it=it1&page=holovna&ch=local`, route: "/commented", version: "1/holovna",
            iteration: "1", viewport: { w: width, h: 900 }, seq },
  });
  const r = await fetch(`${url}/api/local-comments`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comments }),
  });
  if (!r.ok) throw new Error(`посів пінів: ${r.status}`);
  return comments;
}

/** Зняти всі кадри ітерації й дочекатись кінця прогону. */
export async function shootAll(url, extra = {}) {
  const r = await fetch(`${url}/api/shoot`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ it: "it1", all: true, ...extra }),
  });
  const body = await r.json();
  if (!body.ok && !body.report) throw new Error(`зʼємка: ${JSON.stringify(body).slice(0, 300)}`);
  return body;
}
