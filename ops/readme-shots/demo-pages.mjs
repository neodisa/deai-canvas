/**
 * Demo content for the README screenshots: a made-up budgeting app ("Tally").
 * Everything here is fictional: no real company, product, person or data.
 * Page ids are folder names inside an iteration; `pagesJson(v)` is the tree shown in the Pages panel.
 */

const CSS = `
:root{--ink:#14211f;--muted:#5d6b68;--line:#dfe6e3;--bg:#f4f7f5;--card:#fff;--brand:#0f766e;--brand-d:#115e59;--warn:#b45309;--bad:#b42318;--ok:#15803d}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif;color:var(--ink);background:var(--bg);display:flex;min-height:100vh}
nav.side{width:224px;flex:none;background:#0b2b27;color:#cfe5e1;padding:24px 16px;display:flex;flex-direction:column;gap:4px}
nav.side .logo{font-weight:700;font-size:20px;color:#fff;margin:0 8px 24px;letter-spacing:.2px}
nav.side a{display:block;padding:9px 12px;border-radius:8px;color:inherit;text-decoration:none}
nav.side a.on{background:#134e47;color:#fff}
main{flex:1;padding:32px 40px 56px;min-width:0}
header.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}
h1{margin:0;font-size:26px}
.sub{color:var(--muted);margin:2px 0 0}
.btn{display:inline-block;border:0;border-radius:10px;background:var(--brand);color:#fff;font:600 14px/1 inherit;padding:12px 18px;cursor:pointer}
.btn.ghost{background:#fff;color:var(--brand-d);border:1px solid var(--line)}
.row{display:grid;gap:20px}
.c3{grid-template-columns:repeat(3,1fr)}
.c2{grid-template-columns:3fr 2fr}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px}
.card h2{margin:0 0 14px;font-size:16px}
.stat .k{color:var(--muted);font-size:13px}
.stat .v{font-size:30px;font-weight:700;margin:4px 0}
.stat .d{font-size:13px;color:var(--ok)} .stat .d.neg{color:var(--bad)}
.bar{display:grid;grid-template-columns:110px 1fr 70px;align-items:center;gap:12px;margin:10px 0;font-size:14px}
.bar i{display:block;height:10px;border-radius:6px;background:#e4ece9;position:relative;overflow:hidden}
.bar i b{position:absolute;inset:0 auto 0 0;background:var(--brand);border-radius:6px}
.bar i b.over{background:var(--bad)} .bar i b.near{background:var(--warn)}
.bar span:last-child{text-align:right;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;color:var(--muted);font-weight:500;padding:8px 0;border-bottom:1px solid var(--line)}
td{padding:11px 0;border-bottom:1px solid #eef2f0}
td.amt{text-align:right;font-variant-numeric:tabular-nums} td.amt.in{color:var(--ok)}
.tag{display:inline-block;padding:2px 9px;border-radius:99px;background:#e4f3f0;color:var(--brand-d);font-size:12px}
.empty{text-align:center;padding:72px 0;color:var(--muted)}
.empty h2{color:var(--ink);margin:12px 0 6px}
.empty .ico{width:64px;height:64px;border-radius:20px;background:#e4f3f0;margin:0 auto}
.bill{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid #eef2f0;font-size:14px}
.field{display:grid;gap:6px;margin-bottom:16px}
.field label{font-size:13px;color:var(--muted)}
.field input{font:inherit;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;max-width:420px}
.toggle{display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid #eef2f0}
.sw{width:40px;height:22px;border-radius:99px;background:#cbd5d1;position:relative} .sw.on{background:var(--brand)}
.sw::after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff} .sw.on::after{left:21px}
.filters{display:flex;gap:10px;margin-bottom:16px}
.pill{padding:8px 14px;border-radius:99px;border:1px solid var(--line);background:#fff;font-size:13px}
.pill.on{background:var(--brand);color:#fff;border-color:var(--brand)}
.banner{background:#fef3f2;border:1px solid #fecdca;color:var(--bad);border-radius:12px;padding:12px 16px;margin-bottom:20px}
`;

const NAV = [["dashboard", "Home"], ["transactions", "Transactions"], ["budgets", "Budgets"], ["settings", "Settings"]];

function shell(active, title, sub, action, body) {
  const nav = NAV.map(([id, label]) => `<a href="#"${id === active ? ' class="on"' : ""}>${label}</a>`).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${title}</title><style>${CSS}</style></head><body>
<nav class="side"><div class="logo">Tally</div>${nav}</nav>
<main><header class="top"><div><h1>${title}</h1><p class="sub">${sub}</p></div>${action}</header>${body}</main></body></html>`;
}

const TX = [
  ["12 Nov", "Greenfield Market", "Groceries", "-62.40"], ["12 Nov", "Salary — Northwind Studio", "Income", "+3,200.00"],
  ["11 Nov", "City Transit pass", "Transport", "-48.00"], ["10 Nov", "Bluebird Coffee", "Eating out", "-6.80"],
  ["09 Nov", "Streamly subscription", "Entertainment", "-11.99"], ["09 Nov", "Hillside Pharmacy", "Health", "-23.15"],
  ["08 Nov", "Rent", "Housing", "-980.00"], ["07 Nov", "Greenfield Market", "Groceries", "-41.25"],
  ["06 Nov", "Book Nook", "Shopping", "-27.90"], ["05 Nov", "Power & Light", "Utilities", "-74.60"],
];
const txRows = (n) => TX.slice(0, n).map(([d, m, c, a]) =>
  `<tr><td>${d}</td><td>${m}</td><td><span class="tag">${c}</span></td><td class="amt${a[0] === "+" ? " in" : ""}">${a}</td></tr>`).join("");

const CATS = [["Housing", 980, 1000], ["Groceries", 412, 500], ["Transport", 148, 150], ["Eating out", 236, 200], ["Entertainment", 61, 120], ["Health", 54, 150]];
const bars = () => CATS.map(([n, s, l]) => {
  const pct = Math.min(100, Math.round((s / l) * 100));
  const cls = s > l ? "over" : pct >= 95 ? "near" : "";
  return `<div class="bar"><span>${n}</span><i><b class="${cls}" style="width:${pct}%"></b></i><span>$${s}</span></div>`;
}).join("");

/** v = 1 or 2: the second iteration adds a savings-goal card and renames the main action. */
export function pages(v) {
  const addLabel = v === 1 ? "Add expense" : "Add transaction";
  const add = `<button class="btn" id="cta-add">${addLabel}</button>`;
  const goal = v === 2 ? `<div class="card" id="goal"><h2>Savings goal</h2><div class="bar"><span>Trip fund</span><i><b style="width:54%"></b></i><span>54%</span></div><p class="sub">$1,080 of $2,000 · on track for March</p></div>` : "";
  const dashboard = shell("dashboard", "Good morning", "Here is where your money stands on 12 Nov.", add, `
<div class="row c3"><div class="card stat" id="balance"><div class="k">Balance</div><div class="v">$4,820.40</div><div class="d">+ $312.00 vs last month</div></div>
<div class="card stat" id="spent"><div class="k">Spent this month</div><div class="v">$1,263.10</div><div class="d neg">+ 8% vs last month</div></div>
<div class="card stat"><div class="k">Saved</div><div class="v">$540.00</div><div class="d">Goal: $600</div></div></div>
<div class="row c2" style="margin-top:20px"><div class="card" id="by-category"><h2>Spending by category</h2>${bars()}</div>
<div style="display:grid;gap:20px;align-content:start"><div class="card"><h2>Upcoming bills</h2>
<div class="bill"><span>Rent</span><span>01 Dec · $980.00</span></div><div class="bill"><span>Streamly</span><span>09 Dec · $11.99</span></div><div class="bill"><span>Power &amp; Light</span><span>15 Dec · $74.60</span></div></div>${goal}</div></div>
<div class="card" style="margin-top:20px" id="recent"><h2>Recent transactions</h2><table><tr><th>Date</th><th>Merchant</th><th>Category</th><th style="text-align:right">Amount</th></tr>${txRows(5)}</table></div>`);
  const dashEmpty = shell("dashboard", "Good morning", "Nothing to show yet.", add, `
<div class="card empty"><div class="ico"></div><h2>No transactions yet</h2><p>Connect a bank or add your first expense to see your overview.</p><button class="btn">${addLabel}</button></div>`);
  const tx = shell("transactions", "Transactions", "November 2026 · 10 items", `<button class="btn ghost">Export CSV</button>`, `
<div class="filters"><span class="pill on">All</span><span class="pill">Income</span><span class="pill">Expenses</span><span class="pill">This month</span></div>
<div class="card"><table><tr><th>Date</th><th>Merchant</th><th>Category</th><th style="text-align:right">Amount</th></tr>${txRows(10)}</table></div>`);
  const txEmpty = shell("transactions", "Transactions", "No results", `<button class="btn ghost">Export CSV</button>`, `
<div class="card empty"><div class="ico"></div><h2>No matches</h2><p>Try another filter or a wider date range.</p></div>`);
  const budgets = shell("budgets", "Budgets", "Monthly limits per category", `<button class="btn">New budget</button>`, `
<div class="banner" id="over-banner">Eating out is over its limit by $36.</div>
<div class="row c2"><div class="card"><h2>This month</h2>${bars()}</div>
<div class="card"><h2>Rollover</h2><p class="sub">Unused budget moves to next month for these categories.</p><div class="toggle"><span>Groceries</span><span class="sw on"></span></div><div class="toggle"><span>Entertainment</span><span class="sw on"></span></div><div class="toggle"><span>Eating out</span><span class="sw"></span></div></div></div>`);
  const profile = shell("settings", "Profile", "Your account details", `<button class="btn">Save changes</button>`, `
<div class="card"><div class="field"><label>Display name</label><input value="Alex Sample"></div><div class="field"><label>Email</label><input value="alex@example.com"></div><div class="field"><label>Currency</label><input value="USD — US dollar"></div></div>`);
  const notif = shell("settings", "Notifications", "Choose what Tally sends you", `<button class="btn">Save changes</button>`, `
<div class="card"><div class="toggle"><span>Weekly summary</span><span class="sw on"></span></div><div class="toggle"><span>Budget limit reached</span><span class="sw on"></span></div><div class="toggle"><span>Upcoming bills</span><span class="sw"></span></div></div>`);
  return { dashboard, "dashboard-empty": dashEmpty, transactions: tx, "transactions-empty": txEmpty, budgets, profile, notifications: notif };
}

export const pagesJson = () => ({
  pages: [
    { id: "dashboard", name: "Home", kind: "page", published: true, children: [{ id: "dashboard-empty", name: "Empty", kind: "state" }] },
    { id: "transactions", name: "Transactions", kind: "page", published: true, children: [{ id: "transactions-empty", name: "No matches", kind: "state" }] },
    { id: "budgets", name: "Budgets", kind: "page", published: true },
    { id: "settings-folder", name: "Settings", kind: "folder", children: [
      { id: "profile", name: "Profile", kind: "page", published: true },
      { id: "notifications", name: "Notifications", kind: "page", published: true },
    ] },
  ],
});

/** The user flow of the first-run path, laid out on a grid. */
export const flowJson = () => ({ flows: [{ id: "first-run", title: "First run", nodes: [
  { id: "n-empty", page: "dashboard-empty", label: "Empty home", pos: { col: 0, row: 0 } },
  { id: "n-dash", page: "dashboard", label: "Home", pos: { col: 1, row: 0 } },
  { id: "n-tx", page: "transactions", label: "Transactions", pos: { col: 2, row: 0 } },
  { id: "n-budget", page: "budgets", label: "Budgets", pos: { col: 2, row: 1 } },
  { id: "n-prof", page: "profile", label: "Profile", pos: { col: 3, row: 0 } },
], edges: [
  { from: "n-empty", to: "n-dash", label: "Add first expense" },
  { from: "n-dash", to: "n-tx", label: "Open list" },
  { from: "n-dash", to: "n-budget", label: "Set a limit" },
  { from: "n-tx", to: "n-prof", label: "Change currency" },
] }] });
