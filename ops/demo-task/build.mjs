/**
 * The demo task template (0.33.0, «Перший запуск»): files of `app/templates/demo/`, built from the README demo pages
 * (`ops/readme-shots/demo-pages.mjs`). Pure: no disk, no browser. `ops/demo-task.mjs` writes them;
 * `tests/demo-task.test.mjs` checks that the repo copy equals this output.
 */
import { flowJson, pages, pagesJson } from "../readme-shots/demo-pages.mjs";

/** Which variant of the README pages the demo uses (2 — the later iteration: "Add transaction", the savings goal). */
export const DEMO_VERSION = 2;

/** Root `index.html`: `POST /api/task-new {from}` needs one; the page tree comes from `pages.json`, so it only redirects. */
const INDEX = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Tally — demo</title>
<meta http-equiv="refresh" content="0; url=dashboard/"></head>
<body><a href="dashboard/">Tally demo</a></body></html>
`;

/** `{relative path: text}` of every template file. */
export function demoFiles() {
  const out = { "index.html": INDEX };
  const html = pages(DEMO_VERSION);
  for (const id of Object.keys(html)) out[`${id}/index.html`] = html[id];
  out["pages.json"] = `${JSON.stringify(pagesJson(), null, 1)}\n`;
  out["flow.json"] = `${JSON.stringify(flowJson(), null, 1)}\n`;
  return out;
}
