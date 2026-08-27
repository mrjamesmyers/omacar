// The page you hand somebody.
//
// A workshop that cannot produce a piece of paper has not finished the job.
// This is the pre-repair record — what the car arrived with, in one printable
// page, in language a car owner can read — and it is also the only artefact
// here that leaves the machine, so it says plainly which parts were measured
// and which were reasoned about.
//
// The advisor's owner-facing summary is included when one has already been
// run, and left out silently when it has not. A report should never be waiting
// on a language model.

import { h, clear, store, api, dist, econ, fullDate, isoDate, lifeTone,
         sevTone, shortDate, vol, money, U } from "../core.js";

export default function report(root) {
  const car = store.car;
  if (!car) { root.appendChild(h("div.card", h("div.skel"))); return; }

  const faults = car.faults || [];
  const active = faults.filter((f) => f.active);
  const cleared = faults.filter((f) => !f.active);
  const ready = car.readiness || {};
  const svc = car.service;
  const m6 = car.mode06 || [];
  const failed = m6.filter((t) => t.pass === false);
  const marginal = m6.filter((t) => t.pass !== false && t.headroom > 0.85);

  root.appendChild(h("div.row.wrapline.noprint", { style: { marginBottom: "4px" } },
    h("div", h("div.eyebrow", "Records"), h("div.title", "Vehicle report")),
    h("div.right.row", { style: { gap: "8px" } },
      h("button.btn", { onclick: () => store.refreshCar().then(() => location.reload()) }, "Refresh"),
      h("button.btn.primary", { onclick: () => window.print() }, "Print"))));

  // ---- the header ----
  root.appendChild(h("div.card",
    h("div.row.wrapline",
      h("div",
        h("div.eyebrow", "Vehicle inspection report"),
        h("div.title", { style: { fontSize: "1.45rem", marginTop: "3px" } },
          car.name || "Vehicle"),
        h("p.muted", { style: { marginTop: "4px" } },
          [car.vehicle && car.vehicle.trim, car.vehicle && car.vehicle.engine,
           car.vehicle && car.vehicle.vin].filter(Boolean).join("   ·   "))),
      h("div.right", { style: { textAlign: "right" } },
        h("div.eyebrow", "Odometer"),
        h("div.title", { style: { fontSize: "1.3rem" } },
          car.odometer ? dist(car.odometer) : "—"),
        h("p.muted", { style: { marginTop: "4px" } }, fullDate(Date.now() / 1000))))));

  // ---- the verdict ----
  const crit = active.filter((f) => f.severity === "critical").length;
  const tone = crit ? "bad" : (active.length || (svc && svc.overdue)) ? "warn" : "ok";
  root.appendChild(h("div.card.tint-" + tone,
    h("div.eyebrow", "Summary"),
    h("div", { style: { marginTop: "6px", fontSize: "1.1rem", fontWeight: "600" } },
      active.length
        ? `${active.length} fault${active.length > 1 ? "s" : ""} stored across `
          + `${new Set(active.map((f) => (f.module || {}).id)).size} control unit`
          + `${new Set(active.map((f) => (f.module || {}).id)).size > 1 ? "s" : ""}`
        : "No faults stored in any control unit"),
    h("div.grid.g3", { style: { marginTop: "14px" } },
      line("Emissions readiness", ready.ready ? "Ready to test"
        : `${ready.incomplete} monitor${ready.incomplete === 1 ? "" : "s"} incomplete`,
        ready.ready ? "ok" : "warn"),
      line("On-board self-tests", failed.length ? `${failed.length} past the limit`
        : marginal.length ? `${marginal.length} close to the limit` : "All within limits",
        failed.length ? "bad" : marginal.length ? "warn" : "ok"),
      line("Service", svc ? (svc.overdue ? `${svc.overdue} overdue`
        : svc.due ? `${svc.due} due soon` : "Up to date") : "—",
        svc && svc.overdue ? "bad" : svc && svc.due ? "warn" : "ok"))));

  // ---- codes ----
  if (active.length) {
    const tbl = table(["Code", "Control unit", "Description", "Status", "First seen", "Last seen"]);
    for (const f of active) {
      tbl.body.appendChild(h("tr",
        h("td", { style: { fontWeight: "700", color: f.severity === "critical" ? "var(--bad)" : "var(--warn)" } }, f.code),
        h("td.muted", (f.module && f.module.name) || f.system || ""),
        h("td", f.descr),
        h("td.muted", f.status),
        h("td.muted", shortDate(f.first_seen)),
        h("td.muted", shortDate(f.last_seen))));
    }
    root.appendChild(h("div.card", h("div.eyebrow", "Faults found"),
      h("div", { style: { marginTop: "10px", overflowX: "auto" } }, tbl.el)));
  }

  if (cleared.length) {
    root.appendChild(h("div.card.flat", h("div.eyebrow", "Previously recorded, now cleared"),
      h("p.muted", { style: { marginTop: "6px" } },
        cleared.map((f) => `${f.code} ${f.descr} (last seen ${shortDate(f.last_seen)})`).join(";  "))));
  }

  // ---- readiness ----
  const incomplete = (ready.monitors || []).filter((m) => m.supported && !m.complete);
  if (incomplete.length) {
    root.appendChild(h("div.card",
      h("div.eyebrow", "Why this vehicle would not pass an emissions test"),
      h("div", { style: { marginTop: "10px", display: "grid", gap: "10px" } },
        incomplete.map((m) => h("div",
          h("div", { style: { fontWeight: "600" } }, m.name + " monitor — not completed"),
          m.why ? h("p.muted", m.why) : null)))));
  }

  // ---- on-board tests worth flagging ----
  if (failed.length || marginal.length) {
    const tbl = table(["Self-test", "Component", "Measured", "Limit", "Verdict"]);
    for (const t of failed.concat(marginal)) {
      const bad = t.pass === false;
      tbl.body.appendChild(h("tr",
        h("td", t.name),
        h("td.muted", t.component),
        h("td.num", { style: { fontWeight: "600", color: bad ? "var(--bad)" : "var(--warn)" } },
          `${t.value} ${t.unit}`),
        h("td.num.muted", t.hi !== null && t.hi !== undefined ? `max ${t.hi}`
          : t.lo !== null && t.lo !== undefined ? `min ${t.lo}` : "—"),
        h("td", bad ? "Past the limit"
          : `Passing at ${Math.round(t.headroom * 100)}% of the limit`)));
    }
    root.appendChild(h("div.card", h("div.eyebrow", "On-board self-tests"),
      h("p.muted", { style: { marginTop: "4px" } },
        "The engine's own measurements against the manufacturer's limits. A test "
        + "passing close to its limit has not failed yet."),
      h("div", { style: { marginTop: "10px", overflowX: "auto" } }, tbl.el)));
  }

  // ---- service ----
  if (svc) {
    const due = svc.items.filter((i) => i.state !== "ok");
    const tbl = table(["Item", "Minder", "Life left", "Due", "Last done"]);
    for (const i of (due.length ? due : svc.items.slice(0, 4))) {
      tbl.body.appendChild(h("tr",
        h("td", i.item),
        h("td.muted", i.code || "—"),
        h("td.num", { style: { fontWeight: "600",
          color: `var(--${lifeTone(i.life) === "bad" ? "bad" : lifeTone(i.life) === "warn" ? "warn" : "ok"})` } },
          Math.max(0, i.life) + "%"),
        h("td.muted", [i.km_left !== null && i.km_left !== undefined
          ? (i.km_left < 0 ? "over by " + dist(Math.abs(i.km_left)) : "in " + dist(i.km_left))
          : null, i.due_on ? isoDate(i.due_on) : null].filter(Boolean).join("  ·  ")),
        h("td.muted", i.last_on ? isoDate(i.last_on) : "—")));
    }
    root.appendChild(h("div.card", h("div.eyebrow", "Maintenance"),
      h("div", { style: { marginTop: "10px", overflowX: "auto" } }, tbl.el)));
  }

  // ---- how it has been driven ----
  const p = car.perf;
  if (p && p.year) {
    root.appendChild(h("div.card", h("div.eyebrow", "Use since records began"),
      h("div.grid.g4", { style: { marginTop: "12px" } },
        line("This year", dist(p.year.km)),
        line("Average economy", econ(p.year.lphk)),
        line("Fuel", vol(p.year.litres) + (p.year.cost ? `  ·  ${money(p.year.cost)}` : "")),
        line("Records from", isoDate(p.since)))));
  }

  // ---- the owner-facing summary, if one exists ----
  const aiBox = h("div");
  root.appendChild(aiBox);
  if (store.aiOn) {
    api.aiHistory().then(({ records }) => {
      const owner = (records || []).find((r) => r.payload && r.payload.kind === "owner");
      if (!owner) {
        aiBox.appendChild(h("div.card.flat.noprint",
          h("div.eyebrow", "Plain-language summary"),
          h("p.lede", { style: { marginTop: "6px" } },
            "Run the advisor's owner explanation and it will be included here, "
            + "in the printed report as well."),
          h("div.row", { style: { marginTop: "10px" } },
            h("button.btn.ai", { onclick: () => { location.hash = "#advisor/owner"; } },
              "Write it"))));
        return;
      }
      aiBox.appendChild(h("div.card",
        h("div.row.wrapline",
          h("div.eyebrow", "Plain-language summary"),
          h("span.muted.right", "written by the AI advisor from the findings above")),
        h("p", { style: { marginTop: "8px", fontSize: ".92rem", lineHeight: "1.6" } },
          owner.payload.headline || owner.label)));
    }).catch(() => { /* the report stands without it */ });
  }

  // ---- provenance ----
  root.appendChild(h("div.card.flat",
    h("div.eyebrow", "How this report was produced"),
    h("p.muted", { style: { marginTop: "6px" } },
      "Every figure above was read from the vehicle's control units. "
      + (car.simulated
        ? "This vehicle is SIMULATED — the readings are generated by OmaCar's own model of a "
          + (car.name || "car") + " and are not from a real adapter."
        : `Read over ${(car.live && car.live.protocol) || "OBD-II"} using `
          + `${(car.live && car.live.adapter) || "an OBD-II adapter"}.`)),
    h("p.muted", { style: { marginTop: "6px" } },
      "Repair-share figures and test procedures come from published service "
      + "information, not from measurements of this vehicle. Anything written "
      + "by the advisor is labelled as such."),
    h("div.row.wrapline", { style: { marginTop: "18px", gap: "40px" } },
      sign("Inspected by"), sign("Date"))));
}

function line(k, v, tone) {
  return h("div.stat-tile",
    h("div.k", k),
    h("div.v" + (tone ? "." + tone : ""), { style: { fontSize: "1.05rem" } }, v));
}

function table(cols) {
  const body = h("tbody");
  const el = h("table.tbl", h("thead", h("tr", cols.map((c) => h("th", c)))), body);
  return { el, body };
}

function sign(label) {
  return h("div", { style: { flex: "1", minWidth: "180px" } },
    h("div", { style: { borderBottom: "1px solid var(--edge-2)", height: "26px" } }),
    h("div.muted", { style: { marginTop: "5px" } }, label));
}
