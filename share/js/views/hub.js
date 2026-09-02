// The car hub -- the screen you navigate from while sitting in the driver's seat.
//
// The workshop layout (a 44px rail of small icons down the left) is right at a
// desk with a mouse and wrong in a moving car: the targets are too small to hit
// without looking, and looking is the thing you cannot spend. This is the same
// application with the same data and a different set of physical assumptions --
// big targets, few of them, high contrast, and every tile carrying the one
// number that tells you whether it is worth opening at all.
//
// It is not a simplified OmaCar. Nothing is removed; the secondary row reaches
// every view the rail does. It is the same app laid out for a different hand.

import { h, store, dist, U } from "../core.js";
import { ICONS } from "../icons.js";
import { explain } from "../learn.js";
import { radio, radioPlayer } from "../radio.js";
import { LOOKS, savedLook, saveLook, applyLook, nextLook, lookById,
         mountLookEffect } from "../looks.js";

// Sunlight, not taste. A phone in a windscreen mount is competing with the sky,
// and the grey-on-black that reads as elegant indoors is unreadable at noon.
// White on near-black, and nothing dimmer than #C8 anywhere on this screen.
const PRIMARY = [
  { id: "drive",   label: "Drive",  hint: "Gauges" },
  { id: "codes",   label: "Codes",  hint: "Faults" },
  { id: "scan",    label: "Scan",   hint: "Full system" },
  { id: "data",    label: "Data",   hint: "Live values" },
  { id: "health",  label: "Health", hint: "Readiness" },
  { id: "advisor", label: "AI",     hint: "Ask" },
];

const SECONDARY = [
  { id: "dash", label: "Home" }, { id: "live", label: "Cluster" },
  { id: "tests", label: "Tests" }, { id: "concerns", label: "Trends" },
  { id: "service", label: "Service" }, { id: "history", label: "Log" },
  { id: "garage", label: "Garage" }, { id: "learn", label: "Learn" },
  { id: "resets", label: "Resets" }, { id: "replay", label: "Replay" },
  { id: "documents", label: "Docs" },
  { id: "report", label: "Report" },
];

function svg(paths, size) {
  const ns = "http://www.w3.org/2000/svg";
  const el = document.createElementNS(ns, "svg");
  el.setAttribute("viewBox", "0 0 24 24");
  el.setAttribute("width", size); el.setAttribute("height", size);
  el.setAttribute("aria-hidden", "true");
  for (const d of paths || []) {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", d); p.setAttribute("fill", "none");
    p.setAttribute("stroke", "currentColor"); p.setAttribute("stroke-width", "1.7");
    p.setAttribute("stroke-linecap", "round"); p.setAttribute("stroke-linejoin", "round");
    el.appendChild(p);
  }
  return el;
}

// The badge is the reason this is a dashboard and not a menu. A tile that says
// only "Codes" makes you open Codes to find out whether it matters; a tile that
// says "Codes / 2 active" has already answered the question from a glance.
function badgeFor(id, car) {
  if (!car) return null;
  const faults = car.active_faults || [];
  switch (id) {
    case "codes":
      return faults.length
        ? { text: `${faults.length} active`, tone: faults.some((f) => f.severity === "critical") ? "bad" : "warn" }
        : { text: "clear", tone: "ok" };
    case "health": {
      const r = car.readiness || {};
      const names = Object.keys(r);
      const done = names.filter((k) => r[k] === true || r[k] === "complete").length;
      return names.length ? { text: `${done}/${names.length} ready`, tone: done === names.length ? "ok" : "warn" } : null;
    }
    case "drive": {
      const sp = store.values && store.values.SPEED;
      return { text: store.connected ? (sp ? `${Math.round(sp)}` : "linked") : "no link",
               tone: store.connected ? "ok" : "warn" };
    }
    case "scan":
      return car.scanned_at ? { text: "ready", tone: "ok" } : null;
    case "advisor":
      return store.aiOn ? { text: "ready", tone: "ok" } : { text: "off", tone: "warn" };
    case "data": {
      const n = (store.sample.supported || car.supported || []).length;
      return n ? { text: `${n} PIDs`, tone: "ok" } : null;
    }
    default: return null;
  }
}

// Four numbers, chosen because they are the ones a driver actually glances at,
// and sized so they can be read without leaning in.
const VITALS = [
  { label: "Speed", unit: () => U.units.speed,
    get: (v) => (v.SPEED != null ? Math.round(v.SPEED * U.units.km) : "--") },
  { label: "RPM", unit: () => "",
    get: (v) => (v.RPM != null ? Math.round(v.RPM) : "--") },
  { label: "Coolant", unit: () => "°",
    get: (v) => (v.COOLANT_TEMP != null ? Math.round(v.COOLANT_TEMP) : "--") },
  { label: "Trip", unit: () => U.units.dist,
    get: (v, car) => (car.trip_km != null ? dist(car.trip_km, false) : "--") },
];

function effectLabel() { return lookById(savedLook()).label; }

// The effect canvas lives OUTSIDE the redraw cycle.
//
// The hub repaints on every live sample -- several times a second while
// driving. Rebuilding the canvas each time would restart the animation
// constantly and leak a requestAnimationFrame loop per repaint, which on this
// machine is exactly the kind of background cost that crashed the compositor
// once already. So it is mounted once, and only torn down when the effect
// changes or the view goes away.
let fxHost = null;
let fxStop = null;
let fxMode = null;

function redrawFx() {
  if (!fxHost) return;
  const want = savedLook();
  applyLook(want);
  if (want === fxMode) return;
  if (fxStop) { fxStop(); fxStop = null; }
  fxMode = want;
  fxStop = mountLookEffect(fxHost, want);
  const btn = document.querySelector(".hub-look");
  if (btn) btn.textContent = effectLabel();
}

// BUILT ONCE, UPDATED IN PLACE.
//
// This screen used to rebuild itself entirely -- title, vitals, the radio
// transport, six tiles and every SVG icon in them -- from inside a listener on
// `live`. That event fires every 250ms while a fast view is open, so four
// times a second the whole hub was destroyed and made again.
//
// That is what the blinking was. A new node has no history: hover states drop,
// every CSS transition restarts from its initial value, and the icons are
// re-decoded on each pass. It was worse than cosmetic -- the volume slider
// could not be dragged, because the element under your finger stopped existing
// four times a second.
//
// Four numbers and six badges actually change. Those are the only things this
// touches now; the structure is built once and left alone.
export default function hub(root) {
  fxHost = document.createElement("div");
  fxHost.className = "fx-host";
  root.appendChild(fxHost);
  fxMode = null;
  redrawFx();

  const title = h("div.hub-title", "OmaCar");
  const sub = h("div.hub-sub", "");

  const vitalEls = VITALS.map((spec) => {
    const unit = h("span.hub-vital-u", spec.unit());
    const value = h("div.hub-vital-v", "--");
    value.appendChild(unit);
    return { spec, value, unit,
             el: h("div.hub-vital", value, h("div.hub-vital-k", spec.label)) };
  });

  const tiles = PRIMARY.map((t) => {
    const el = h("button.hub-tile", {
      onclick: () => { location.hash = "#" + t.id; },
    });
    el.appendChild(h("div.hub-ico"));
    el.firstChild.appendChild(svg(ICONS[t.id], 34));
    el.appendChild(h("div.hub-label", t.label));
    el.appendChild(h("div.hub-hint", t.hint));
    return { t, el, badge: null };
  });

  // The radio keeps its own slot. It is rebuilt on radio events -- a play, a
  // pause, a track change -- which happen when somebody does something, not
  // four times a second.
  const radioSlot = h("div.hub-radio");
  radioSlot.appendChild(radioPlayer());

  root.appendChild(h("div.hub",
    h("div.hub-head",
      h("div", title, sub),
      h("div.row", { style: { gap: "8px" } },
        h("button.hub-exit.hub-look", {
          onclick: () => { saveLook(nextLook(savedLook())); redrawFx(); },
          title: lookById(savedLook()).note + "  (tap to change)",
        }, effectLabel()),
        h("button.hub-exit", {
          onclick: () => { location.hash = "#dash"; },
          title: "Leave car mode",
        }, "Workshop"))),

    h("div.hub-vitals", ...vitalEls.map((x) => x.el)),

    explain(h, "hub"),

    radioSlot,

    h("div.hub-grid", ...tiles.map((x) => x.el)),

    h("div.hub-more",
      ...SECONDARY.map((t) =>
        h("button.hub-chip", { onclick: () => { location.hash = "#" + t.id; } }, t.label)))));

  function update() {
    const car = store.car;
    const v = store.values || {};

    const name = car && car.name ? car.name : "OmaCar";
    if (title.textContent !== name) title.textContent = name;
    const state = store.connected
      ? (store.sample.protocol || "connected")
      : "not connected — plug in the adapter";
    if (sub.textContent !== state) sub.textContent = state;

    for (const x of vitalEls) {
      const text = String(x.spec.get(v, car || {}));
      // Written only when it differs. Assigning the same string still dirties
      // the node and costs a layout pass, four times a second, per number.
      if (x.value.firstChild.nodeValue !== text) x.value.firstChild.nodeValue = text;
      const u = x.spec.unit();
      if (x.unit.textContent !== u) x.unit.textContent = u;
    }

    for (const x of tiles) {
      const b = badgeFor(x.t.id, car);
      if (!b) {
        if (x.badge) { x.badge.remove(); x.badge = null; }
      } else {
        if (!x.badge) {
          x.badge = h("div.hub-badge");
          x.el.appendChild(x.badge);
        }
        if (x.badge.textContent !== b.text) x.badge.textContent = b.text;
        const cls = "hub-badge tone-" + b.tone;
        if (x.badge.className !== cls) x.badge.className = cls;
      }
      const label = x.t.label + (b ? ", " + b.text : "");
      if (x.el.getAttribute("aria-label") !== label) x.el.setAttribute("aria-label", label);
    }
  }

  function remountRadio() {
    radioSlot.replaceChildren(radioPlayer());
  }

  update();

  const offLive = store.on("live", update);
  const offCar = store.on("car", update);
  const offRadio = radio.on(remountRadio);
  return () => {
    offLive(); offCar(); offRadio();
    if (fxStop) { fxStop(); fxStop = null; }
    if (fxHost) { fxHost.remove(); fxHost = null; }
    fxMode = null;
  };
}
