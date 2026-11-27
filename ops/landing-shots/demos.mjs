import { readFileSync } from "node:fs";

const stylesheet = (name) => readFileSync(new URL(`./${name}.css`, import.meta.url), "utf8");
const railCss = stylesheet("northline");
const checkoutCss = stylesheet("forma");

const html = (title, css, header, body) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title><style>${css}</style></head><body>${header}<main>${body}</main></body></html>`;

const railHeader = `<header class="top"><div class="bar">
  <a class="wordmark" href="../search/"><span class="railmark" aria-hidden="true"></span>Northline</a>
  <nav aria-label="Travel"><a class="current" href="../search/">Plan a trip</a><a href="../fares/">Fares</a><a href="../confirmation/">My trips</a></nav>
  <span class="currency">EN &nbsp;·&nbsp; EUR</span>
</div></header>`;

const railDate = "Fri, 18 Sep";
const train = (id, out, arrival, duration, fare, price) => `<article class="trip" id="${id}">
  <div><strong>${out}</strong><span class="meta">Wien Hbf</span></div>
  <div class="journey"><span>${duration}</span><i></i><span>Direct</span></div>
  <div><strong>${arrival}</strong><span class="meta">Zürich HB</span></div>
  <a class="price" href="../fares/"><strong>€${price}</strong><span class="meta">${fare}</span></a>
</article>`;

const railPage = (title, body) => html(`${title} · Northline`, railCss, railHeader, body);

function railSearch(railPhoto, version) {
  return railPage("Plan a trip", `
    <section class="scenic">
      <img src="${railPhoto}" alt="Red train crossing a green Alpine valley">
      <div class="scenic-copy"><small>Travel by rail</small><h1>Take the<br>scenic route.</h1><p>Book trains across Europe, one journey at a time.</p></div>
    </section>
    <section class="booking" id="journey-form">
      <div class="booking-top"><h2>Plan a rail trip</h2><div class="trip-type"><span class="selected">One way</span><span>Round trip</span></div></div>
      <div class="fields">
        <div class="field"><span>From</span><strong>Vienna</strong></div>
        <div class="field"><span>To</span><strong>Zürich</strong></div>
        <div class="field" id="date-field"><span>Departure</span><strong>${railDate}</strong></div>
        <a class="primary" id="trip-search" href="#departures">Find trains <span aria-hidden="true">&nbsp;→</span></a>
      </div>
    </section>
    <section class="results" id="departures" aria-label="Departures">
      <div class="route-head"><div><h2 id="route-heading">${version === 1 ? "Available trains" : "Vienna → Zürich"}</h2><p class="meta">Friday, 18 September · 1 traveller</p></div><span class="meta">All times local</span></div>
      ${train("trip-saver", "09:28", "17:20", "7h 52m", "Saver", "69")}
      ${train("trip-flex", "13:28", "21:20", "7h 52m", "Flexible", "89")}
    </section>`);
}

function railFares(railPhoto) {
  const fare = (tier, price, sub, conditions) => `<article class="booking fare">
    <span class="meta">${sub}</span><h2>${tier}</h2><strong>€${price} <small>/ traveller</small></strong>
    <ul>${conditions.map((condition) => `<li>${condition}</li>`).join("")}</ul>
    <a class="primary" href="../passenger/">Select ${tier} &nbsp;→</a></article>`;
  return railPage("Choose a fare", `
    <section class="scenic fare-cover">
      <img src="${railPhoto}" alt="A passenger train travelling through an Alpine valley">
      <div class="scenic-copy"><small>Friday, 18 September</small><h1>Vienna to Zürich.</h1><p>09:28 → 17:20 &nbsp;·&nbsp; Direct</p></div>
    </section>
    <section class="fare-options"><h2 id="fare-heading">Choose a fare</h2><p class="meta">Both fares include a reserved seat and one carry-on bag.</p>
      <div class="fare-grid">
        ${fare("Saver", "69", "Lowest fare", ["Standard class", "No changes after booking", "Seat reservation included"])}
        ${fare("Flexible", "89", "More flexibility", ["Standard class", "Change before departure", "Seat reservation included"])}
      </div>
    </section>`);
}

const page = (id, name) => ({ id, name, kind: "page", published: true });
const state = (id, name) => ({ id, name, kind: "state" });

export function northline(railPhoto) {
  return {
    id: "northline",
    title: "Northline · Rail booking",
    tags: ["booking", "web"],
    iterations: ["First booking pass", "Updated results and fare labels"],
    tree: { pages: [
      { ...page("search", "Plan a trip"), children: [state("no-trains", "No departures")] },
      page("fares", "Choose a fare"),
      page("passenger", "Passenger details"),
      page("confirmation", "Booking confirmation"),
    ] },
    flow: { flows: [{ id: "booking", title: "Rail booking", nodes: [
      { id: "search", page: "search", pos: { col: 0, row: 0 } },
      { id: "fares", page: "fares", pos: { col: 1, row: 0 } },
      { id: "passenger", page: "passenger", pos: { col: 2, row: 0 } },
      { id: "confirmation", page: "confirmation", pos: { col: 3, row: 0 } },
      { id: "empty", page: "no-trains", pos: { col: 1, row: 1 } },
    ], edges: [
      { from: "search", to: "fares", label: "Select departure" },
      { from: "fares", to: "passenger", label: "Choose a fare" },
      { from: "passenger", to: "confirmation", label: "Confirm booking" },
      { from: "search", to: "empty", label: "No trains on date" },
    ] }] },
    pages(version) {
      return {
        search: railSearch(railPhoto, version),
        "no-trains": railPage("No departures", `<div class="passenger"><p class="meta">Vienna → Zürich</p><h1 class="page-title">No trains on this date</h1><p>Try the day before or after ${railDate}.</p><a class="primary" href="../search/">Change date</a></div>`),
        fares: railFares(railPhoto),
        passenger: railPage("Passenger details", `<div class="passenger"><p class="meta">Vienna → Zürich · ${railDate}</p><h1 class="page-title">Passenger details</h1><p>Use the name shown on your travel ID.</p><div class="field"><span>Full name</span><strong>Alex Rivera</strong></div><div class="field"><span>Email for your ticket</span><strong>alex@example.com</strong></div><a class="primary" href="../confirmation/">Confirm booking</a></div>`),
        confirmation: railPage("Booking confirmation", `<div class="passenger"><p class="meta">Booking NL-2186</p><h1 class="page-title">You’re ready to travel.</h1><p>Your ticket for ${railDate} is ready.</p>${train("booked-ride", "09:28", "17:20", "7h 52m", "Saver", "69")}<a class="primary" href="../search/">Plan another trip</a></div>`),
      };
    },
  };
}

const checkoutPage = (active, step, title, description, body) => html(`${title} · Forma`, checkoutCss,
  `<header class="top"><div class="bar"><a href="../cart/" class="wordmark">forma<i>.</i></a>
  <nav class="steps" aria-label="Checkout">${[["cart", "Bag"], ["delivery", "Delivery"], ["payment", "Payment"]].map(([id, name]) => `<a href="../${id}/"${id === active ? ' class="active" aria-current="step"' : ""}>${name}</a>`).join("")}</nav>
  <span class="order-id">Checkout · EUR</span></div></header>`,
  `<header class="page"><small>${step}</small><h1>${title}</h1><p>${description}</p></header>${body}`);

function orderSummary(action, next) {
  return `<aside class="panel"><h2>Order summary</h2><dl class="lines"><div><dt>Subtotal</dt><dd>€640.00</dd></div>
  <div><dt>Delivery</dt><dd>€24.00</dd></div><div class="total"><dt>Total</dt><dd>€664.00</dd></div></dl>
  ${action ? `<a class="primary" href="../${next}/">${action} &nbsp;→</a>` : ""}</aside>`;
}

const field = (id, label, value, wide = false) => `<div class="field${wide ? " wide" : ""}"><label for="${id}">${label}</label><input id="${id}" value="${value}"></div>`;

function paymentPage(declined = false) {
  return checkoutPage("payment", "Step 3 of 3", "Payment", "Enter a card to complete your order.", `
  <div class="grid"><section class="panel"><h2>Card details</h2>${declined ? '<p class="issue">Your card was declined. Try a different card.</p>' : ""}
  <div class="fields">${field("card", "Card number", "•••• •••• •••• 0472", true)}${field("expiry", "Expiry", "10 / 28")}${field("code", "Security code", "•••")}${field("name", "Name on card", "Alex Rivera", true)}</div>
  </section>${orderSummary(declined ? "Try payment again" : "Place order", "order-confirmed")}</div>`);
}

export function forma(chairPhoto) {
  return {
    id: "forma",
    title: "Forma · Store checkout",
    tags: ["checkout", "web"],
    iterations: ["Checkout and payment recovery"],
    tree: { pages: [
      { ...page("cart", "Checkout"), children: [state("delivery", "Delivery details"), state("payment", "Payment")] },
      { ...page("order-confirmed", "Payment result"), children: [state("card-declined", "Card declined")] },
    ] },
    flow: { flows: [{ id: "checkout", title: "Checkout flow", nodes: [
      { id: "bag", page: "cart", label: "Shopping bag", pos: { col: 0, row: 0 } },
      { id: "delivery", page: "delivery", pos: { col: 1, row: 0 } },
      { id: "payment", page: "payment", pos: { col: 2, row: 0 } },
      { id: "declined", page: "card-declined", pos: { col: 1, row: 1 } },
      { id: "confirmed", page: "order-confirmed", label: "Order confirmed", pos: { col: 2, row: 1 } },
    ], edges: [
      { from: "bag", to: "delivery", label: "Continue to delivery" },
      { from: "delivery", to: "payment", label: "Continue to payment" },
      { from: "payment", to: "confirmed", label: "Payment accepted" },
      { from: "payment", to: "declined", label: "Card declined" },
    ] }] },
    pages() {
      return {
        cart: checkoutPage("cart", "Step 1 of 3", "Shopping bag", "One item, shipping from our Berlin studio.", `
          <div class="grid"><div class="panel"><div class="item"><img src="${chairPhoto}" alt="Arc lounge chair in caramel upholstery">
          <div><h2>Arc Lounge Chair</h2><p><span class="swatch"></span>Caramel · Brushed chrome</p><small>Qty 1</small></div></div>
          <p class="notice">In stock · Ships in 3–5 business days</p></div>${orderSummary("Continue to delivery", "delivery")}</div>`),
        delivery: checkoutPage("delivery", "Step 2 of 3", "Delivery details", "Where should we deliver your order?", `
          <div class="grid"><section class="panel"><h2>Shipping address</h2><div class="fields">
          ${field("first-name", "First name", "Alex")}${field("last-name", "Last name", "Rivera")}${field("address", "Street address", "18 Linden Lane", true)}${field("postal", "Postal code", "10115")}${field("city", "City", "Berlin")}
          </div><p class="notice">Standard delivery · 3–5 business days</p></section>${orderSummary("Continue to payment", "payment")}</div>`),
        payment: paymentPage(),
        "card-declined": paymentPage(true),
        "order-confirmed": checkoutPage("", "Order FM-2048", "Thanks, Alex.", "Your Arc Lounge Chair will ship in 3–5 business days.", `
          <div class="grid"><section class="panel"><span class="check" aria-hidden="true">✓</span><div class="confirmation"><h2>Order confirmed</h2><p>The receipt was sent to alex@example.com.</p><p>We’ll email a tracking link once your chair ships.</p></div></section>${orderSummary()}</div>`),
      };
    },
  };
}

export const northlinePins = [
  { selector: "#date-field", text: "Show the full date so the departure day is easy to scan." },
  { selector: "#trip-search", text: "Keep Find trains visible when the form wraps on mobile.",
    replies: [{ id: "northline-reply-1", author: "AI", agent: true, ts: "16.09.2026 16:42",
      text: "Sticky bar at the bottom or a button under the form? I can do either — which one?" }] },
  { selector: "#route-heading", text: "Use the route as the heading above the departures.", resolution: "Changed the heading to Vienna → Zürich and kept the date beneath it." },
];

/** Small extra tasks so the task list of the Studio space is not sparse. */
const mini = (id, title, tags, iterations, pageName, make) => ({
  id, title, tags, iterations,
  tree: { pages: [page("home", pageName), page("details", `${pageName} · details`)] },
  pages: (version) => ({ home: make(version), details: make(version) }),
});

export function extraTasks() {
  return [
    mini("northline-mobile", "Northline · Mobile tickets", ["mobile", "tickets"],
      ["First ticket wallet", "Ticket list with offline state", "Boarding pass view"], "Ticket wallet",
      (v) => railPage("Tickets", `<div class="passenger"><p class="meta">Vienna → Zürich · ${railDate}</p><h1 class="page-title">Your tickets</h1><p>${v} saved for offline use.</p><a class="primary" href="../home/">Open boarding pass</a></div>`)),
    mini("forma-product", "Forma · Product page", ["product", "web"],
      ["Gallery and details", "Swatches and delivery note"], "Arc Lounge Chair",
      () => checkoutPage("", "Living room", "Arc Lounge Chair", "Caramel upholstery on a brushed chrome frame.", orderSummary("Add to bag", "home"))),
    mini("atlas-onboarding", "Atlas · Onboarding", ["onboarding", "app"],
      ["Welcome and workspace setup", "Invite teammates step"], "Welcome",
      () => checkoutPage("", "Step 1 of 3", "Welcome to Atlas", "Name your workspace to get started.", `<div class="grid"><section class="panel"><h2>Workspace</h2><div class="fields">${field("ws", "Workspace name", "Studio North", true)}</div></section>${orderSummary("Continue", "home")}</div>`)),
  ];
}
