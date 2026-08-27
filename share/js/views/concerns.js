// Areas of concern: what is trending somewhere it should not, what was
// captured when something looked wrong, and what it looked like.
//
// A scan tool tells you a test is passing. It is passing *today*. The useful
// question is for how much longer, and that needs the same measurement taken
// repeatedly and a line drawn through it — which is the one thing a tool that
// only ever sees a car for twenty minutes in a workshop can never do, and the
// one thing a tool that lives in the car does for free.

import { h, clear, store, api, toast, dist, econ, econVal, temp, shortDate,
         clockOf, fullDate, since, U } from "../core.js";
import { sparkline } from "../charts.js";
import { photoStrip, thumb, capturePhoto } from "../camera.js";

const TONE = { critical: "bad", warning: "warn", info: "" };

export default function concerns(root) {
  root.appendChild(h("section.sect",
    h("div.head",
      h("div", h("div.eyebrow", "Trends"), h("div.title", "Areas of concern")),
      h("div.right.row", { style: { gap: "8px" } },
        h("button.btn", { onclick: () => capturePhoto({
          subject: "general", onDone: () => location.reload() }) }, "Photograph"),
        h("button.btn.primary", { onclick: async () => {
          try {
            const s = await api.capture({ reason: "manual" });
            toast(`State captured as #${s.id}.`);
            location.reload();
          } catch (e) { toast(String(e.message || e), "bad"); }
        } }, "Capture the state now"))),
    h("p.lede",
      "Every figure here is one measurement taken over months. A self-test "
      + "passing at 95% of its limit has not failed and is going to; knowing "
      + "roughly when is the difference between planning a repair and being "
      + "stranded by one.")));

  const list = h("div.sect");
  list.appendChild(h("div.card", h("div.skel")));
  root.appendChild(list);

  const shots = h("div.sect");
  root.appendChild(shots);

  const gallery = h("div.sect");
  root.appendChild(gallery);

  api.concerns().then(({ concerns: found }) => {
    clear(list);
    if (!found || !found.length) {
      list.appendChild(h("div.card",
        h("div.title", "Nothing trending anywhere it should not"),
        h("p.lede", { style: { marginTop: "8px" } },
          "Trends need a few weeks of record before they mean anything, and "
          + "a line through three points is arithmetic rather than a warning. "
          + "Keep driving with the adapter in.")));
      return;
    }
    for (const c of found) list.appendChild(card(c));
  }).catch((e) => {
    clear(list);
    list.appendChild(h("div.card.tint-bad", h("p.lede", String(e.message || e))));
  });

  loadSnapshots(shots);
  gallery.appendChild(photoStrip({ subject: "general", title: "Photographs" }));
}

function card(c) {
  const tone = TONE[c.severity] || "";
  const cv = h("canvas");
  const hasSeries = (c.series || []).length > 3;

  const box = h("div.card" + (tone ? ".tint-" + tone : ""),
    h("div.row.wrapline",
      h("div", { style: { minWidth: "0" } },
        h("div.eyebrow", c.kind),
        h("div", { style: { fontSize: "1.05rem", fontWeight: "600", marginTop: "2px" } },
          c.title)),
      h("div.right.row.wrapline", { style: { gap: "8px" } },
        c.days_to_limit
          ? h("span.pill." + (tone || "info"), c.when)
          : (c.when ? h("span.pill", c.when) : null),
        h("span.pill", `${c.confidence}% fit`))),
    h("p.lede", { style: { marginTop: "8px" } }, c.detail));

  if (c.limit !== null && c.limit !== undefined) {
    const frac = Math.max(0, Math.min(1, Math.abs(c.value) / Math.abs(c.limit)));
    box.appendChild(h("div", { style: { marginTop: "12px" } },
      h("div.row", { style: { marginBottom: "6px" } },
        h("span.muted", `now ${fmt(c.value, c.unit)}`),
        h("span.muted.right", `limit ${fmt(c.limit, c.unit)}`)),
      h("div.meter", h("i", { style: { width: (frac * 100) + "%",
        background: `var(--${tone === "bad" ? "bad" : tone === "warn" ? "warn" : "ok"})` } }))));
  }

  if (hasSeries) {
    box.appendChild(h("div", { style: { marginTop: "12px" } }, cv));
    requestAnimationFrame(() => sparkline(cv, c.series.map((p) => p[1]),
      { height: 52, tint: tone === "bad" ? "#E85D4E" : tone === "warn" ? "#E5B457" : "#4FA8E8" }));
  }

  const row = h("div.row.wrapline", { style: { marginTop: "12px", gap: "8px" } });
  if (c.code) {
    row.appendChild(h("button.btn.sm", {
      onclick: () => { location.hash = "#codes/" + c.code; } }, "Open " + c.code));
  }
  row.appendChild(h("button.btn.sm", {
    onclick: () => capturePhoto({ subject: "concern", subjectId: c.id,
                                  onDone: () => location.reload() }) },
    "Photograph this"));
  if (store.aiOn) {
    row.appendChild(h("button.btn.ai.sm", { onclick: () => {
      location.hash = "#advisor";
      setTimeout(() => {
        const el = document.querySelector('input[type="text"]');
        if (el) {
          el.value = `${c.title}. ${c.detail} What should I do about this, and `
                   + `how would I confirm it?`;
          el.focus();
        }
      }, 350);
    } }, "Ask the advisor"));
  }
  box.appendChild(row);

  // Anything already photographed against this concern.
  const strip = h("div", { style: { marginTop: "10px", display: "flex",
                                    flexWrap: "wrap", gap: "8px" } });
  box.appendChild(strip);
  api.photos({ subject: "concern", id: c.id }).then(({ photos }) => {
    for (const p of photos || []) strip.appendChild(thumb(p, () => location.reload()));
  }).catch(() => {});

  return box;
}

function fmt(v, unit) {
  if (v === null || v === undefined) return "—";
  if (unit === "°C") return temp(v);
  if (unit === "L/100km") return econ(v);
  return `${Number(v).toFixed(Math.abs(v) < 10 ? 2 : 0)}${unit ? " " + unit : ""}`;
}

function loadSnapshots(host) {
  const box = h("div.card");
  box.appendChild(h("div.row",
    h("div.eyebrow", "Captured states"),
    h("span.muted.right",
      "taken by hand, and automatically whenever the watchdog raises something")));
  const list = h("div", { style: { marginTop: "10px", display: "grid", gap: "6px" } });
  list.appendChild(h("div.skel"));
  box.appendChild(list);
  host.appendChild(box);

  api.snapshots(20).then(({ snapshots }) => {
    clear(list);
    if (!snapshots || !snapshots.length) {
      list.appendChild(h("div.empty",
        "Nothing captured yet. A coolant spike on a climb is gone by the time "
        + "you open the app; a snapshot is the evidence it happened."));
      return;
    }
    for (const s of snapshots) {
      const p = s.payload || {};
      list.appendChild(h("button.rowitem", {
        onclick: () => showSnapshot(s),
      },
        h("span.pill" + (p.reason === "manual" ? "" : ".warn"), p.reason || "state"),
        h("span.desc", s.label || ""),
        p.odometer ? h("span.muted", dist(p.odometer)) : null,
        h("span.muted", `${shortDate(s.at)}  ${clockOf(s.at)}`)));
    }
  }).catch(() => { clear(list); list.appendChild(h("div.empty", "Unavailable.")); });
}

function showSnapshot(s) {
  const p = s.payload || {};
  const host = document.getElementById("modal-host");
  const close = () => { host.hidden = true; clear(host); };
  const rows = [];
  const add = (k, v) => v !== undefined && v !== null && v !== "" && rows.push([k, v]);
  const L = p.live || {};
  add("Captured", fullDate(s.at));
  add("Odometer", p.odometer ? dist(p.odometer) : null);
  add("State", p.status);
  add("Speed", L.SPEED !== undefined ? `${Math.round(L.SPEED * U.units.km)} ${U.units.speed}` : null);
  add("Engine", L.RPM !== undefined ? `${Math.round(L.RPM)} rpm` : null);
  add("Coolant", L.COOLANT_TEMP !== undefined ? temp(L.COOLANT_TEMP) : null);
  add("Battery", L.CONTROL_MODULE_VOLTAGE !== undefined ? `${L.CONTROL_MODULE_VOLTAGE.toFixed(1)} V` : null);
  add("Long trim", L.LONG_FUEL_TRIM_1 !== undefined ? `${L.LONG_FUEL_TRIM_1.toFixed(1)} %` : null);
  add("Short trim", L.SHORT_FUEL_TRIM_1 !== undefined ? `${L.SHORT_FUEL_TRIM_1.toFixed(1)} %` : null);
  add("Economy", p.economy_lphk ? econ(p.economy_lphk) : null);
  add("Codes", (p.codes || []).map((c) => c.code).join(", ") || "none");
  add("Emissions", p.readiness ? (p.readiness.ready ? "ready" : `${(p.readiness.incomplete || []).length} incomplete`) : null);

  const box = h("div.modal", { role: "dialog", "aria-modal": "true",
                               style: { maxWidth: "640px" } },
    h("div.title", s.label || "Captured state"),
    h("table.tbl", h("tbody", rows.map(([k, v]) =>
      h("tr", h("td.muted", k), h("td", { style: { textAlign: "right" } }, String(v)))))),
    h("div.row", { style: { justifyContent: "flex-end", gap: "8px" } },
      h("button.btn", {
        onclick: () => capturePhoto({ subject: "snapshot", subjectId: String(s.id) }),
      }, "Photograph"),
      h("button.btn.primary", { onclick: close }, "Close")));
  clear(host);
  host.appendChild(box);
  host.hidden = false;
  host.onclick = (e) => { if (e.target === host) close(); };
}
