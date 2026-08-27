// The service book. What was done, when, and what is next.
//
// Every item is scored on Honda's own Maintenance Minder scale, which counts
// down rather than up: 15% is book it, 5% is now, nought is past due. Whichever
// of the mileage interval and the time interval is further along is the one
// that decides — that is the manufacturer's rule and it is the right one,
// because brake fluid does not care how far you have driven.

import { h, store, dist, isoDate, grouped, lifeTone, U } from "../core.js";

export default function service(root) {
  const car = store.car;
  const s = car && car.service;
  if (!s) { root.appendChild(h("div.empty", "No service records.")); return; }
  const next = s.next;

  root.appendChild(h("section.sect",
    h("div.head", h("div", h("div.eyebrow", "Maintenance"),
      h("div.title", "Service schedule")),
      h("button.btn.right", { onclick: () => window.print() }, "Print"))));

  root.appendChild(h("div.card.tint-" + (lifeTone(next.life) || "ok"),
    h("div.eyebrow", "Next due"),
    h("div.row.wrapline", { style: { marginTop: "6px", alignItems: "baseline" } },
      h("div.title", { style: { fontSize: "1.5rem" } }, next.item),
      next.code ? h("span.pill", "Minder " + next.code) : null,
      h("div.title.right", { style: { fontSize: "1.5rem",
        color: `var(--${lifeTone(next.life) === "bad" ? "bad" : lifeTone(next.life) === "warn" ? "warn" : "ok"})` } },
        Math.max(0, next.life) + "%")),
    h("div.meter", { style: { marginTop: "10px" } },
      h("i", { style: { width: Math.max(0, next.life) + "%",
        background: `var(--${lifeTone(next.life) === "bad" ? "bad" : lifeTone(next.life) === "warn" ? "warn" : "ok"})` } })),
    h("p.lede", { style: { marginTop: "10px" } },
      [next.km_left !== null && next.km_left !== undefined
        ? (next.km_left < 0 ? "overdue by " + dist(Math.abs(next.km_left)) : "in " + dist(next.km_left))
        : null,
       next.due_on ? "by " + isoDate(next.due_on) : null,
       next.last_on ? `last done ${isoDate(next.last_on)}${next.last_km ? " at " + dist(next.last_km) : ""}` : null,
      ].filter(Boolean).join("   ·   ")),
    next.note ? h("p.muted", { style: { marginTop: "4px" } }, next.note) : null));

  const tbl = h("table.tbl",
    h("thead", h("tr",
      h("th", "Item"), h("th", "Minder"), h("th.num", "Life"),
      h("th.num", "Remaining"), h("th", "Due"), h("th", "Last done"), h("th", "Notes"))));
  const tb = h("tbody");
  for (const it of s.items) {
    const tone = lifeTone(it.life);
    tb.appendChild(h("tr",
      h("td", h("div", { style: { fontWeight: "600" } }, it.item),
        h("div.meter.thin", { style: { marginTop: "5px", maxWidth: "170px" } },
          h("i", { style: { width: Math.max(0, it.life) + "%",
            background: `var(--${tone === "bad" ? "bad" : tone === "warn" ? "warn" : "ok"})` } }))),
      h("td.muted", it.code || "—"),
      h("td.num", { style: { color: `var(--${tone === "bad" ? "bad" : tone === "warn" ? "warn" : "ok"})`,
                             fontWeight: "600" } }, Math.max(0, it.life) + "%"),
      h("td.num.muted", it.km_left === null || it.km_left === undefined ? "—"
        : it.km_left < 0 ? "over by " + dist(Math.abs(it.km_left)) : dist(it.km_left)),
      h("td.muted", it.due_on ? isoDate(it.due_on) : "—"),
      h("td.muted", it.last_on ? `${isoDate(it.last_on)}${it.last_km ? "  ·  " + dist(it.last_km) : ""}` : "—"),
      h("td.muted", { style: { maxWidth: "30ch" } }, it.note || "")));
  }
  tbl.appendChild(tb);
  root.appendChild(h("div.card",
    h("div.row", h("div.eyebrow", "The book"),
      h("span.muted.right", s.due ? `${s.due} due or due soon` : "nothing due")),
    h("div", { style: { marginTop: "10px", overflowX: "auto" } }, tbl)));

  root.appendChild(h("p.muted",
    "Whichever interval is further along decides — mileage or time. "
    + "That is the manufacturer's rule, and it is why brake fluid comes due "
    + "on a car that has barely moved."));
}
