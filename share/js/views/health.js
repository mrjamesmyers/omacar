// Readiness monitors and Mode 06 — the two screens nobody else bothers with.
//
// Readiness answers the question people actually walk into a shop with: will
// it pass. Mode 06 is the ECU showing its working — the measured value of each
// self-test next to the limit it was judged against. Every OBD-II car has had
// it since 1996 and almost no consumer tool surfaces it, which is a waste,
// because a catalyst test sitting at 95% of its limit has passed and is also
// about to stop passing, and that is a thing worth knowing a year early.

import { h, store, pct } from "../core.js";

export default function health(root) {
  const car = store.car;
  if (!car) { root.appendChild(h("div.card", h("div.skel"))); return; }
  const r = car.readiness || { monitors: [] };
  const m6 = car.mode06 || [];

  const supported = r.monitors.filter((m) => m.supported);
  const incomplete = supported.filter((m) => !m.complete);

  root.appendChild(h("section.sect",
    h("div.head", h("div", h("div.eyebrow", "Emissions"),
      h("div.title", "Readiness and on-board tests")))));

  // ---- the verdict ----
  root.appendChild(h("div.card.tint-" + (r.ready ? "ok" : "warn"),
    h("div.row.wrapline",
      h("div",
        h("div.eyebrow", "Emissions test"),
        h("div.title", { style: { fontSize: "1.4rem", marginTop: "2px" } },
          r.ready ? "Ready to test" : "Not ready"),
        h("p.lede", { style: { marginTop: "6px", maxWidth: "68ch" } },
          r.ready
            ? "Every supported monitor has run and completed. The car can be presented for a test."
            : `${incomplete.length} monitor${incomplete.length > 1 ? "s have" : " has"} not completed. `
              + "Most jurisdictions allow one incomplete non-continuous monitor on an OBD-II car "
              + "and none allow two.")),
      h("div.right",
        h("div.stat-tile", h("div.k", "Complete"),
          h("div.v" + (r.ready ? ".ok" : ".warn"),
            `${supported.length - incomplete.length}/${supported.length}`))))));

  // The reason a monitor has not run is the useful part, and it is nearly
  // always another fault standing in its way.
  const blocked = incomplete.filter((m) => m.why);
  if (blocked.length) {
    root.appendChild(h("div.card",
      h("div.eyebrow", "Why they have not completed"),
      h("div", { style: { marginTop: "10px", display: "grid", gap: "12px" } },
        blocked.map((m) => h("div",
          h("div.row", h("span.dot.warn"), h("span", { style: { fontWeight: "600" } }, m.name)),
          h("p.lede", { style: { marginTop: "4px", marginLeft: "18px" } }, m.why))))));
  }

  // ---- the monitors ----
  const grid = h("div.grid.g3");
  for (const m of r.monitors) {
    const tone = !m.supported ? "" : m.complete ? "ok" : "warn";
    grid.appendChild(h("div.card",
      { style: { opacity: m.supported ? "1" : ".45" } },
      h("div.row",
        h("span.dot" + (tone ? "." + tone : "")),
        h("span", { style: { fontWeight: "600", fontSize: ".82rem" } }, m.name)),
      h("div.row", { style: { marginTop: "6px" } },
        h("span.muted", m.kind === "continuous" ? "continuous" : "trip-based"),
        h("span.pill" + (tone ? "." + tone : "") + ".right",
          !m.supported ? "n/a" : m.complete ? "complete" : "incomplete"))));
  }
  root.appendChild(h("section.sect", h("div.eyebrow", "Monitors"), grid));

  // ---- Mode 06 ----
  if (m6.length) {
    root.appendChild(h("section.sect",
      h("div.head",
        h("div", h("div.eyebrow", "Mode 06"),
          h("div.title", { style: { fontSize: "1.05rem" } }, "On-board monitoring test results")),
        h("span.muted.right", `${m6.length} tests`)),
      h("p.lede",
        "The measured value of each self-test, next to the limit the ECU judged it "
        + "against. A test that has passed at 95% of its limit is a failure with a "
        + "date on it.")));

    const box = h("div.grid.g2");
    for (const t of m6) {
      const failed = t.pass === false;
      const marginal = !failed && t.headroom !== null && t.headroom !== undefined && t.headroom > 0.85;
      const tint = failed ? "var(--bad)" : marginal ? "var(--warn)" : "var(--ok)";
      const card = h("div.card" + (failed ? ".tint-bad" : marginal ? ".tint-warn" : ""),
        h("div.row.wrapline",
          h("span", { style: { fontWeight: "600", fontSize: ".84rem" } }, t.name),
          h("span.pill" + (failed ? ".bad" : marginal ? ".warn" : ".ok") + ".right",
            failed ? "failed" : marginal ? "marginal" : "pass")),
        h("div.row", { style: { marginTop: "2px" } },
          h("span.muted", t.component), h("span.muted.right", "TID " + t.mid)),
        h("div.range", { style: { marginTop: "12px" } },
          h("i", { style: { width: Math.max(2, Math.min(100, (t.headroom || 0) * 100)) + "%",
                            background: tint } }),
          // Where the limit sits on this track. Drawn even when the value is
          // past it, so an over-limit reading reads as "over" rather than as
          // a full bar that could just be a maximum.
          t.hi !== null && t.hi !== undefined ? h("b", { style: { left: "100%" } }) : null),
        h("div.row", { style: { marginTop: "8px" } },
          h("span.muted", t.lo !== null && t.lo !== undefined ? `min ${t.lo}` : ""),
          h("span", { style: { fontWeight: "700", fontSize: "1.05rem", color: tint,
                               margin: "0 auto" } }, `${t.value} ${t.unit}`),
          h("span.muted", t.hi !== null && t.hi !== undefined ? `max ${t.hi}` : "")),
        t.headroom !== null && t.headroom !== undefined
          ? h("p.muted", { style: { marginTop: "6px" } },
              `${Math.round(t.headroom * 100)}% of the limit`)
          : null,
        t.note ? h("p.muted", { style: { marginTop: "6px" } }, t.note) : null);
      box.appendChild(card);
    }
    root.appendChild(box);
  }
}
