// Boot, the rail, the vehicle bar, and the router.
//
// Two clocks. The snapshot — codes, service, a year of driving — changes on
// the scale of minutes and is polled slowly. The live sample changes five
// times a second and is polled fast, but only while a view that shows it is
// on screen. A diagnostic tool that hammers the daemon while you read a
// service schedule is a tool that gets in the way of the thing it is watching.

import { h, clear, icon, store, U, api, toast, dist, grouped, since } from "./core.js";

import dash from "./views/dash.js";
import scan from "./views/scan.js";
import codes from "./views/codes.js";
import data from "./views/data.js";
import health from "./views/health.js";
import service from "./views/service.js";
import history from "./views/history.js";
import advisor from "./views/advisor.js";
import tests from "./views/tests.js";
import report from "./views/report.js";
import drive from "./views/drive.js";
import concernsView from "./views/concerns.js";
import live from "./views/live.js";

const ICONS = {
  dash: ["M3 12.5 12 4l9 8.5", "M5.5 10.6V20h13v-9.4"],
  scan: ["M3 7V4h3", "M21 7V4h-3", "M3 17v3h3", "M21 17v3h-3", "M7 12h10"],
  codes: ["M12 3.5 21 20H3z", "M12 10v4", "M12 17.2v.1"],
  data: ["M3 17l4-7 3.5 4L15 6l6 11", "M3 20h18"],
  health: ["M12 21s-7.5-4.7-7.5-10A4.5 4.5 0 0 1 12 7.6 4.5 4.5 0 0 1 19.5 11c0 5.3-7.5 10-7.5 10z"],
  concerns: ["M3.5 17.5 9 11l4 3.6 7.5-8.6", "M15.5 6h5v5"],
  service: ["M14.7 6.3a4 4 0 0 0 5 5L15 16l-3 3-3-3 4.7-4.7a4 4 0 0 0-5-5L12 3l3 3z"],
  history: ["M3.5 12a8.5 8.5 0 1 0 2.6-6.1", "M3 4v5h5", "M12 8v4.4l3 1.8"],
  tests: ["M5 12h3.2", "M15.8 12H19", "M12 5.2v13.6", "M8.2 8.6a5.4 5.4 0 0 0 0 6.8",
          "M15.8 8.6a5.4 5.4 0 0 1 0 6.8"],
  advisor: ["M12 3.2v3.1", "M12 17.7v3.1", "M4.6 7.6l2.7 1.5", "M16.7 14.9l2.7 1.5",
            "M4.6 16.4l2.7-1.5", "M16.7 9.1l2.7-1.5", "M12 9.4a2.6 2.6 0 1 0 0 5.2 2.6 2.6 0 0 0 0-5.2z"],
  report: ["M6.5 3h7.5l4 4v14h-11.5z", "M14 3v4.5h4", "M9 12.5h6", "M9 16h6"],
  live: ["M12 3a9 9 0 1 0 9 9", "M12 12l5-5"],
  drive: ["M4.5 13.5 6.2 8.4A2 2 0 0 1 8.1 7h7.8a2 2 0 0 1 1.9 1.4l1.7 5.1",
          "M4.5 13.5h15v3.8h-3v-1.6h-9v1.6h-3z", "M7.4 15.6h.1", "M16.5 15.6h.1"],
};

const VIEWS = [
  { id: "dash", label: "Home", title: "Overview", mount: dash, fast: true },
  { id: "scan", label: "Scan", title: "Full system scan", mount: scan },
  { id: "codes", label: "Codes", title: "Trouble codes", mount: codes, fast: true },
  { id: "advisor", label: "AI", title: "Advisor", mount: advisor, ai: true },
  { id: "data", label: "Data", title: "Data lab", mount: data, fast: true },
  { id: "tests", label: "Tests", title: "Functional tests", mount: tests, fast: true },
  { id: "health", label: "Health", title: "Readiness and on-board tests", mount: health },
  { id: "concerns", label: "Trends", title: "Areas of concern", mount: concernsView },
  { id: "service", label: "Service", title: "Service schedule", mount: service },
  { id: "history", label: "Log", title: "Drive history and records", mount: history },
  { id: "report", label: "Report", title: "Vehicle report", mount: report },
  { id: "live", label: "Live", title: "Cluster", mount: live, fast: true },
  { id: "drive", label: "Drive", title: "Drive mode", mount: drive, fast: true },
];

let current = null;
let unmount = null;
let fastTimer = null;

function route() {
  const id = (location.hash || "#dash").slice(1).split("/")[0];
  return VIEWS.find((v) => v.id === id) || VIEWS[0];
}

function go() {
  const view = route();
  if (current) noteManualNav(current.id, view.id);
  const stage = document.getElementById("stage");
  if (unmount) { try { unmount(); } catch { /* a view that fails to clean up must not block the next one */ } }
  unmount = null;
  clear(stage);
  current = view;
  paintRail();

  const wrap = h("div.wrap");
  stage.appendChild(wrap);
  stage.scrollTop = 0;
  try {
    unmount = view.mount(wrap, { arg: (location.hash || "").split("/")[1] || null }) || null;
  } catch (e) {
    wrap.appendChild(h("div.card.tint-bad",
      h("div.title", "That view failed to draw"),
      h("p.lede", String(e && e.message || e)),
      h("p.muted", "Everything else still works. The terminal has the same data: omacar doctor")));
    console.error(e);
  }

  // Only poll fast for views that show a live value.
  clearInterval(fastTimer);
  fastTimer = null;
  if (view.fast) {
    store.refreshLive();
    fastTimer = setInterval(() => store.refreshLive(), 250);
  }
  document.title = `OmaCar — ${view.title}`;
}

function paintRail() {
  const rail = document.getElementById("rail");
  clear(rail);
  const car = store.car || {};
  const issues = (car.active_faults || []).length;
  const svc = car.service && car.service.due ? car.service.due : 0;

  for (const v of VIEWS) {
    if (v.ai && !store.aiOn) continue;
    const btn = h("button.rail-item", {
      type: "button",
      title: v.title,
      "aria-current": current && current.id === v.id ? "page" : null,
      onclick: () => { location.hash = "#" + v.id; },
    }, icon(ICONS[v.id] || ICONS.dash, 19), h("span.lbl", v.label));

    if (v.id === "codes" && issues) btn.appendChild(h("span.pip", String(issues)));
    if (v.id === "service" && svc) btn.appendChild(h("span.pip.warn", String(svc)));
    if (v.id === "health" && car.readiness && !car.readiness.ready)
      btn.appendChild(h("span.pip.warn", "!"));
    rail.appendChild(btn);
  }
}

function paintBar() {
  const bar = document.getElementById("vbar");
  const car = store.car;
  clear(bar);
  if (!car) {
    bar.appendChild(h("div.id", h("div.name", "OmaCar"), h("div.sub", "connecting…")));
    return;
  }
  const state = store.state;
  const tone = state === "driving" ? "ok" : state === "idling" ? "warn"
    : state === "parked" ? "info" : "";

  bar.appendChild(h("div.id",
    h("div.name", car.name || "Unknown vehicle"),
    h("div.sub", [car.vehicle && car.vehicle.trim, car.vehicle && car.vehicle.engine,
                  car.vehicle && car.vehicle.vin].filter(Boolean).join("  ·  "))));

  bar.appendChild(h("div.spacer"));

  if (car.simulated) bar.appendChild(h("span.pill.info", "simulated car"));

  if (car.odometer) {
    bar.appendChild(h("div.stat",
      h("span.muted", "ODOMETER"),
      h("span.odo", dist(car.odometer))));
  }

  bar.appendChild(h("div.stat",
    h("span.dot" + (tone ? "." + tone : "") + (state === "driving" ? ".live" : "")),
    h("span", state === "driving"
      ? `${Math.round((store.values.SPEED || 0) * U.units.km)} ${U.units.speed}`
      : state)));

  bar.appendChild(h("div.stat",
    h("span.muted", car.live && car.live.protocol ? car.live.protocol : "no link")));
}

// ---------------------------------------------------------------- boot
// ------------------------------------------------------------- automatic drive
//
// On a tablet on a dashboard the app should already be showing the right thing
// when you get in. So: when the adapter answers — or when the car actually
// starts rolling, if you would rather — the app takes itself to drive mode,
// and goes back to the workshop when the link drops.
//
// The one rule that makes this bearable rather than infuriating: if you
// navigate away from drive mode by hand, it stays away. Software that keeps
// dragging you back to a screen you just left is software you end up fighting.
// The override lasts until the link cycles, which is the next time the
// question is genuinely open again.

let auto = { mode: "connect", back: true };
let wasConnected = null;
let wasMoving = false;
let overridden = false;

function autoDrive() {
  const view = route().id;
  const connected = store.connected;
  const moving = (store.values.SPEED || 0) > 3;

  // A fresh link is a fresh decision.
  if (connected && wasConnected === false) overridden = false;

  const want = auto.mode === "connect" ? connected
    : auto.mode === "moving" ? moving : false;

  if (want && view !== "drive" && !overridden) {
    location.hash = "#drive";
  } else if (auto.back && !connected && wasConnected === true && view === "drive") {
    // Unplugged. Land on the overview rather than on a gauge reading nothing.
    location.hash = "#dash";
  }

  wasConnected = connected;
  wasMoving = moving;
}

// Leaving drive mode by hand while the car is still connected is a decision,
// and it sticks. Arriving there by hand is not an override.
function noteManualNav(fromId, toId) {
  if (fromId === "drive" && toId !== "drive" && store.connected) overridden = true;
  if (toId === "drive") overridden = false;
}

// Arriving with a view already named in the URL is somebody asking for that
// view — a bookmark, a link from the dock card, a deep link out of another
// screen. Auto-drive is for the case where no view was asked for; it must not
// override one that was.
function honourInitialView() {
  const asked = (location.hash || "").slice(1).split("/")[0];
  if (asked && asked !== "drive" && VIEWS.some((v) => v.id === asked)) {
    overridden = true;
  }
}

export async function loadAuto() {
  try {
    const l = await api.driveLayout();
    auto = { mode: l.auto || "connect", back: l.auto_return !== false };
  } catch { /* the default is sensible and the app must start regardless */ }
}

// ---------------------------------------------------------------- the theme
//
// The palette comes from Omarchy, not from this app. An application on this
// desktop that ships its own colours is a guest who turned up in its own
// clothes — and when the theme changes, everything else on screen changes with
// it and a tool that did not would look broken rather than distinctive.
let themeStamp = -1;

async function applyTheme() {
  try {
    const { stamp, vars } = await api.theme();
    if (stamp === themeStamp) return;
    themeStamp = stamp;
    const root = document.documentElement;
    for (const [k, v] of Object.entries(vars)) {
      if (k === "mode") { root.style.colorScheme = v; continue; }
      root.style.setProperty("--" + k, v);
    }
    root.dataset.mode = vars.mode || "dark";
  } catch {
    // The stylesheet's own palette is the fallback, and it is the one the app
    // was designed against — so a missing theme is a non-event.
  }
}

async function boot() {
  document.getElementById("btn-units").addEventListener("click", async () => {
    // The server owns the unit choice, because the CLI, the dock card and this
    // app all read the same file. Flipping it here writes that file, so the
    // dock card changes with the app rather than drifting from it.
    const next = U.imperial ? "metric" : "imperial";
    try {
      await api.setUnits(next);
      await store.refreshCar();
      document.getElementById("btn-units").textContent = U.units.dist;
      go();
      toast(`Now in ${next === "imperial" ? "miles" : "kilometres"}. The dock card and the terminal follow.`);
    } catch (e) {
      toast("Could not change units: " + (e.message || e), "bad");
    }
  });

  window.addEventListener("hashchange", go);

  store.on("car", () => { paintBar(); paintRail(); });
  store.on("live", () => { paintBar(); autoDrive(); });
  // The snapshot poller is the only clock running when no view is asking for
  // live samples, so it has to be able to trigger the switch too.
  store.on("car", autoDrive);

  honourInitialView();
  await Promise.all([store.boot(), applyTheme(), loadAuto()]);
  document.getElementById("btn-units").textContent = U.units.dist;
  document.getElementById("app").dataset.booting = "0";
  paintBar();
  go();

  setInterval(() => store.refreshCar(), 20000);
  // Cheap: one stat on the server and a no-op unless the theme actually moved.
  setInterval(applyTheme, 5000);
  // The layout — and with it the auto-drive rule — can be changed from another
  // window or another device, so it is re-read rather than assumed.
  setInterval(loadAuto, 15000);

  // Keyboard: the numbers jump between sections the way a tablet's hard keys
  // would, because in a workshop a mouse is often not the thing in your hand.
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea")) return;
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= VIEWS.length) { location.hash = "#" + VIEWS[n - 1].id; return; }
    if (e.key === "r" && !e.metaKey && !e.ctrlKey) { store.refreshCar(); toast("Refreshed"); }
  });
}

boot().catch((e) => {
  document.getElementById("app").dataset.booting = "0";
  document.getElementById("stage").appendChild(
    h("div.wrap", h("div.card.tint-bad",
      h("div.title", "OmaCar could not start"),
      h("p.lede", String(e && e.message || e)),
      h("p.muted", "Is the server running? Try: omacar server status"))));
});
