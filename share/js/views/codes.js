// Trouble codes, and what to do about each one.
//
// The list is the easy half. The detail pane is the point: what the code
// means, what this car's own numbers say about it, which causes are worth
// checking in which order, the live values that separate them, and how to
// test. Smart Data is the piece that matters most — the tool picks the
// channels that prove or clear each cause, so nobody has to remember that a
// heater fault is settled by one Mode 06 result and a lean code is settled by
// comparing trim at idle against trim at cruise.

import { h, clear, store, api, toast, confirmDialog, sevTone, shortDate,
         fullDate, temp, speed, grouped, U } from "../core.js";
import { lookup, resolveSmart, PID_META } from "../knowledge.js";

export default function codes(root, { arg }) {
  const car = store.car;
  if (!car) { root.appendChild(h("div.card", h("div.skel"))); return; }

  const all = car.faults || [];
  const RANK = { critical: 0, warning: 1, normal: 2 };
  const active = all.filter((f) => f.active).sort((a, b) =>
    (RANK[a.severity] ?? 3) - (RANK[b.severity] ?? 3)
    || (b.last_seen || 0) - (a.last_seen || 0));
  const cleared = all.filter((f) => !f.active);
  let selected = arg || (active[0] && active[0].code) || (all[0] && all[0].code) || null;

  root.appendChild(h("section.sect",
    h("div.head",
      h("div", h("div.eyebrow", "Diagnostics"), h("div.title", "Trouble codes")),
      h("div.right.row",
        h("button.btn.danger", {
          onclick: async () => {
            const ok = await confirmDialog({
              title: "Clear all trouble codes?",
              body: h("div.sect",
                h("p.lede", "Clearing does not repair anything. It erases the stored "
                  + "codes and their freeze frames — the evidence you would use to "
                  + "diagnose them — and resets every readiness monitor."),
                h("p.lede", "The car will not pass an emissions test until those monitors "
                  + "have run again, which takes several complete drive cycles.")),
              confirm: "Clear codes",
            });
            if (!ok) return;
            try {
              const r = await api.clear();
              toast(`Cleared ${r.cleared} code(s). ${r.monitors_reset} readiness monitor(s) reset.`);
              await store.refreshCar();
              location.hash = "#codes";
              location.reload();
            } catch (e) { toast(String(e.message || e), "bad"); }
          },
        }, "Clear codes"))),
    h("p.lede",
      active.length
        ? `${active.length} active across ${new Set(active.map((f) => (f.module || {}).id)).size} module(s), `
          + `${cleared.length} in the history.`
        : "Nothing stored. Cleared codes are kept below as history.")));

  // A fixed list column and a detail column that may shrink. `1fr` alone has a
  // min-content floor, so a wide table in the detail pushed the grid past its
  // container and the list slid under it.
  const layout = h("div.grid.split", { style: {
    gridTemplateColumns: "300px minmax(0, 1fr)", alignItems: "start" } });
  const listCol = h("div.sect");
  const detailCol = h("div");
  layout.appendChild(listCol);
  layout.appendChild(detailCol);
  root.appendChild(layout);

  function paintList() {
    clear(listCol);
    const group = (title, items) => {
      if (!items.length) return;
      listCol.appendChild(h("div.eyebrow", title));
      const box = h("div", { style: { display: "grid", gap: "6px" } });
      for (const f of items) {
        box.appendChild(h("button.rowitem", {
          "aria-selected": f.code === selected ? "true" : "false",
          onclick: () => { selected = f.code; paintList(); paintDetail(); },
        },
          h("span.code", { style: { color: f.active
            ? (f.severity === "critical" ? "var(--bad)" : "var(--warn)") : "var(--faint)" } }, f.code),
          h("span.desc", f.descr),
          f.active ? h("span.pill." + (sevTone(f.severity) || "warn"), f.status) : null));
      }
      listCol.appendChild(box);
    };
    group("Active", active);
    group("History", cleared);
    if (!all.length) listCol.appendChild(h("div.empty", "No codes have ever been stored."));
  }

  function paintDetail() {
    clear(detailCol);
    const f = all.find((x) => x.code === selected);
    if (!f) { detailCol.appendChild(h("div.empty", "Select a code.")); return; }
    detailCol.appendChild(detail(f, car));
  }

  paintList();
  paintDetail();
}

function detail(f, car) {
  const k = lookup(store.knowledge, f.code);
  const tone = f.active ? (f.severity === "critical" ? "bad" : "warn") : "";
  const out = h("div.sect");

  // ---- what it is ----
  out.appendChild(h("div.card" + (tone ? ".tint-" + tone : ""),
    h("div.row.wrapline",
      h("div.title", { style: { fontSize: "1.5rem", letterSpacing: ".03em" } }, f.code),
      h("span.pill" + (f.active ? "." + (sevTone(f.severity) || "warn") : ""), f.status),
      k.known ? null : h("span.pill.info", "decoded, not in the library"),
      h("span.muted.right", (f.module && f.module.name) || k.system || "")),
    h("div", { style: { marginTop: "8px", fontSize: "1.02rem", fontWeight: "600" } },
      k.title || f.descr),
    h("p.lede", { style: { marginTop: "8px" } }, k.meaning || f.detail || ""),
    f.detail && k.meaning ? h("p.lede", { style: { marginTop: "8px", color: "var(--dim)" } },
      h("span.eyebrow", "On this car  "), f.detail) : null,
    h("div.row.wrapline", { style: { marginTop: "12px", gap: "16px" } },
      f.count ? meta("Seen", `${f.count}×`) : null,
      f.first_seen ? meta("First", shortDate(f.first_seen)) : null,
      f.last_seen ? meta("Last", shortDate(f.last_seen)) : null,
      k.drivable ? meta("Drivable", k.drivable.split(".")[0]) : null,
      k.emissions !== undefined ? meta("Emissions", k.emissions ? "affects the test" : "not an emissions fault") : null)));

  // ---- what this car's own numbers say ----
  const smart = (k.smart || []).map((s) => resolveSmart(s, car)).filter(Boolean);
  if (smart.length) {
    const tbl = h("table.tbl",
      h("thead", h("tr", h("th", "Smart data"), h("th.num", "Reading"),
        h("th", "Expected"), h("th", "Why it matters"))));
    const tb = h("tbody");
    for (const s of smart) {
      const bad = s.pass === false;
      const marginal = s.headroom !== null && s.headroom !== undefined && s.headroom > 0.85 && s.pass !== false;
      tb.appendChild(h("tr",
        h("td", h("div", s.label), h("div.muted", s.source)),
        h("td.num", { style: { color: bad ? "var(--bad)" : marginal ? "var(--warn)" : "var(--ink)",
                               fontWeight: "600" } },
          formatSmart(s)),
        h("td.muted", s.expect || "—"),
        h("td.muted", { style: { maxWidth: "34ch" } }, s.why || "")));
    }
    tbl.appendChild(tb);
    out.appendChild(h("div.card",
      h("div.row", h("div.eyebrow", "What this car is reporting"),
        h("span.muted.right", "picked for this code")),
      h("div", { style: { marginTop: "10px" } }, tbl)));
  }

  // ---- freeze frame ----
  if (f.freeze) {
    const ff = f.freeze;
    const row = h("div.grid.g4");
    const add = (kk, vv) => vv === undefined || vv === null ? null
      : row.appendChild(h("div.stat-tile", h("div.k", kk), h("div.v", { style: { fontSize: "1.15rem" } }, vv)));
    add("Engine speed", ff.rpm !== undefined ? grouped(ff.rpm) + " rpm" : null);
    add("Vehicle speed", ff.speed !== undefined ? speed(ff.speed) : null);
    add("Coolant", ff.coolant !== undefined ? temp(ff.coolant) : null);
    add("Load", ff.load !== undefined ? ff.load + " %" : null);
    add("Long fuel trim", ff.ltft !== undefined ? "+" + ff.ltft + " %" : null);
    add("IMA charge", ff.soc !== undefined ? ff.soc + " %" : null);
    out.appendChild(h("div.card",
      h("div.eyebrow", "Freeze frame"),
      h("p.muted", { style: { margin: "4px 0 12px" } },
        "What the engine was doing the instant this code set. It is the difference "
        + "between “the sensor is bad” and “the sensor is bad on a cold start”."),
      row));
  }

  // ---- what usually fixes it ----
  if ((k.causes || []).length) {
    const box = h("div", { style: { display: "grid", gap: "10px", marginTop: "10px" } });
    for (const c of k.causes) {
      box.appendChild(h("div",
        h("div.row", h("span", { style: { fontWeight: "600" } }, c.what),
          h("span.muted.right", `${c.share}%`)),
        h("div.meter.thin", { style: { margin: "6px 0" } },
          h("i", { style: { width: c.share + "%", background: c.share >= 40 ? "var(--info)" : "var(--edge-2)" } })),
        c.note ? h("p.muted", c.note) : null,
        h("div.row.wrapline", { style: { gap: "12px", marginTop: "3px" } },
          c.part ? h("span.muted", `part ${c.part}`) : null,
          c.hours ? h("span.muted", `${c.hours} h labour`) : null)));
    }
    out.appendChild(h("div.card",
      h("div.row", h("div.eyebrow", "What usually fixes it"),
        h("span.muted.right", "ranked by share of repairs")),
      box,
      h("p.muted", { style: { marginTop: "12px" } },
        "Shares come from published repair-frequency data and service information, "
        + "not from a fleet we monitor. They are a starting order, not a diagnosis.")));
  }

  // ---- how to test ----
  if ((k.tests || []).length) {
    const box = h("div", { style: { display: "grid", gap: "14px", marginTop: "10px" } });
    for (const t of k.tests) {
      box.appendChild(h("div",
        h("div.row", h("span", { style: { fontWeight: "600" } }, t.name),
          t.tools ? h("span.pill.right", t.tools) : null),
        h("ol", { style: { margin: "8px 0 0", display: "grid", gap: "4px" } },
          t.steps.map((s, i) => h("li.muted", { style: { display: "flex", gap: "8px" } },
            h("span", { style: { color: "var(--ghost)" } }, String(i + 1) + "."), h("span", s)))),
        t.expect ? h("p", { style: { marginTop: "8px", fontSize: ".78rem" } },
          h("span.eyebrow", "Expect  "), t.expect) : null));
    }
    out.appendChild(h("div.card", h("div.eyebrow", "Guided tests"), box));
  }

  if (k.clearing) {
    out.appendChild(h("div.card.flat",
      h("div.eyebrow", "Before you clear it"),
      h("p.lede", { style: { marginTop: "6px" } }, k.clearing)));
  }

  if (store.aiOn) {
    out.appendChild(h("div.card.tint-ai",
      h("div.row.wrapline",
        h("span.pill.ai", "AI ADVISOR"),
        h("span.lede", { style: { flex: "1", minWidth: "220px" } },
          "Rank these causes against this car's own freeze frame, Mode 06 margins and trims."),
        h("button.btn.ai.right", {
          onclick: () => { location.hash = "#advisor/code:" + f.code; },
        }, "Diagnose " + f.code))));
  }

  return out;
}

function formatSmart(s) {
  if (s.value === null || s.value === undefined) return "—";
  if (s.unitKind === "temp") return temp(s.value);
  if (s.unitKind === "speed") return speed(s.value);
  if (s.unitKind && s.unitKind !== "%" && s.unitKind !== "V" && s.unitKind !== "g/s"
      && s.unitKind !== "rpm" && s.unitKind !== "°") return s.display;
  return s.display + (s.unitKind && s.unitKind !== "%" ? " " + s.unitKind : s.unitKind === "%" ? " %" : "");
}

function meta(k, v) {
  return h("div", h("div.eyebrow", k), h("div", { style: { fontSize: ".8rem" } }, v));
}
