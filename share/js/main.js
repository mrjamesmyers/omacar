// Boot, the rail, the vehicle bar, and the router.
//
// Two clocks. The snapshot — codes, service, a year of driving — changes on
// the scale of minutes and is polled slowly. The live sample changes five
// times a second and is polled fast, but only while a view that shows it is
// on screen. A diagnostic tool that hammers the daemon while you read a
// service schedule is a tool that gets in the way of the thing it is watching.

import { h, clear, icon, store, U, api, toast, dist, grouped, since } from "./core.js";

import { ICONS } from "./icons.js";
import { learn } from "./learn.js";
import { savedLook, applyLook } from "./looks.js";
import { privacy, vinShort as maskVinShort, person, odo as maskOdo } from "./privacy.js";
import { onboard, showOnboarding } from "./onboard.js";
import hub from "./views/hub.js";
import documentsView from "./views/documents.js";
import replayView from "./views/replay.js";
import resetsView from "./views/resets.js";
import learnView from "./views/learnview.js";
import garageView from "./views/garage.js";
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


const VIEWS = [
  // The hub is deliberately first: it is the landing screen in the car, and
  // route() falls back to VIEWS[0] for an unknown hash.
  { id: "hub", label: "Car", title: "Car hub", mount: hub, fast: true, car: true },
  { id: "dash", label: "Home", title: "Overview", mount: dash, primary: true, fast: true },
  { id: "scan", label: "Scan", title: "Full system scan", mount: scan, primary: true },
  { id: "codes", label: "Codes", title: "Trouble codes", mount: codes, primary: true, fast: true },
  { id: "advisor", label: "AI", title: "Advisor", mount: advisor, primary: true, ai: true },
  { id: "data", label: "Data", title: "Data lab", mount: data, primary: true, fast: true },
  { id: "tests", label: "Tests", title: "Functional tests", mount: tests, fast: true },
  { id: "health", label: "Health", title: "Readiness and on-board tests", mount: health },
  { id: "concerns", label: "Trends", title: "Areas of concern", mount: concernsView },
  { id: "service", label: "Service", title: "Service schedule", mount: service },
  { id: "resets", label: "Resets", title: "Service resets and functional tests", mount: resetsView },
  { id: "history", label: "Log", title: "Drive history and records", mount: history },
  { id: "replay", label: "Replay", title: "Replay a recorded drive", mount: replayView },
  { id: "documents", label: "Docs", title: "Receipts, registrations and records", mount: documentsView },
  { id: "garage", label: "Garage", title: "Every car you own", mount: garageView },
  { id: "learn", label: "Learn", title: "Learn the car, and the app", mount: learnView },
  { id: "report", label: "Report", title: "Vehicle report", mount: report },
  { id: "live", label: "Live", title: "Cluster", mount: live, fast: true },
  { id: "drive", label: "Drive", title: "Drive mode", mount: drive, primary: true, fast: true },
];

let current = null;
let unmount = null;
let fastTimer = null;

function route() {
  const id = (location.hash || "#dash").slice(1).split("/")[0];
  return VIEWS.find((v) => v.id === id) || VIEWS.find((v) => v.id === "dash");
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
  const lb = document.getElementById("btn-learn");
  if (lb) {
    lb.setAttribute("aria-pressed", learn.on ? "true" : "false");
    lb.classList.toggle("on", learn.on);
  }
}

function paintRail() {
  const rail = document.getElementById("rail");
  clear(rail);
  const car = store.car || {};
  const issues = (car.active_faults || []).length;
  const svc = car.service && car.service.due ? car.service.due : 0;

  // SIX IN THE RAIL, THE REST BEHIND "MORE".
  //
  // Seventeen destinations in a vertical strip is not navigation, it is a list
  // you have to read every time. The six here are the ones reached daily; the
  // other eleven are reached deliberately, when you already know what you want,
  // and a menu serves that better than eleven more icons to scan past.
  //
  // Nothing is hidden: More holds everything else, with the same badges, and
  // the current view is promoted into the rail so you can always see where you
  // are even when you are somewhere secondary.
  const badge = (v, btn) => {
    if (v.id === "codes" && issues) btn.appendChild(h("span.pip", String(issues)));
    if (v.id === "service" && svc) btn.appendChild(h("span.pip.warn", String(svc)));
    if (v.id === "health" && car.readiness && !car.readiness.ready)
      btn.appendChild(h("span.pip.warn", "!"));
    return btn;
  };

  const item = (v) => badge(v, h("button.rail-item", {
    type: "button",
    title: v.title,
    "aria-current": current && current.id === v.id ? "page" : null,
    onclick: () => { location.hash = "#" + v.id; },
  }, icon(ICONS[v.id] || ICONS.dash, 19), h("span.lbl", v.label)));

  const shown = VIEWS.filter((v) => v.primary && !(v.ai && !store.aiOn));
  const rest = VIEWS.filter((v) => !v.primary && !(v.ai && !store.aiOn));

  // Wherever you are should be visible in the rail, even if it lives in More.
  const here = current && rest.find((v) => v.id === current.id);
  for (const v of shown) rail.appendChild(item(v));
  if (here) rail.appendChild(item(here));

  const anyBadge = rest.some((v) =>
    (v.id === "service" && svc) ||
    (v.id === "health" && car.readiness && !car.readiness.ready));

  const more = h("button.rail-item.rail-more", {
    type: "button",
    title: "Everything else",
    "aria-haspopup": "menu",
    onclick: (e) => { e.stopPropagation(); openMore(rest, more, badge); },
  }, icon(["M6 12h.1", "M12 12h.1", "M18 12h.1"], 19), h("span.lbl", "More"));
  if (anyBadge) more.appendChild(h("span.pip.warn", "!"));
  rail.appendChild(more);
}

function openMore(rest, anchor, badge) {
  const existing = document.querySelector(".rail-menu");
  if (existing) { existing.remove(); return; }

  const menu = h("div.rail-menu", { role: "menu" },
    ...rest.map((v) => badge(v, h("button.rail-menu-item", {
      type: "button", role: "menuitem",
      onclick: () => { location.hash = "#" + v.id; menu.remove(); },
    }, icon(ICONS[v.id] || ICONS.dash, 18),
       h("span", v.label),
       h("span.rail-menu-sub", v.title)))));

  document.body.appendChild(menu);
  const r = anchor.getBoundingClientRect();
  // Anchored to the button, then pulled back on screen if it would run off the
  // bottom -- More sits low in the rail, so on a short window it always would.
  menu.style.left = (r.right + 8) + "px";
  const top = Math.min(r.top, window.innerHeight - menu.offsetHeight - 12);
  menu.style.top = Math.max(8, top) + "px";

  const close = (e) => {
    if (menu.contains(e.target)) return;
    menu.remove();
    document.removeEventListener("click", close);
    document.removeEventListener("keydown", esc);
  };
  const esc = (e) => { if (e.key === "Escape") close({ target: document.body }); };
  setTimeout(() => {
    document.addEventListener("click", close);
    document.addEventListener("keydown", esc);
  }, 0);
  const first = menu.querySelector("button");
  if (first) first.focus();
}

// James -> James', Alex -> Alex's. Mirrors records.possessive() on the server;
// the rule is small enough that sharing it across two languages would cost
// more than stating it twice.
function possessive(name) {
  const n = String(name || "").trim();
  if (!n) return "";
  return n + (n.slice(-1).toLowerCase() === "s" ? "'" : "'s");
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

  // WHOSE CAR, THEN WHAT CAR.
  //
  // The bar said "2015 Honda" -- which is neither. It did not name the model,
  // because records.vehicle() was overwriting it, and it did not say whose car
  // this is, which is the thing that actually matters in a household with two
  // Hondas in it. "James' 2015 Honda CR-Z" answers both in one line.
  //
  // Composed here rather than taken from the server's `title` so the driver's
  // name goes through the same privacy masking as everything else in the bar.
  const v = car.vehicle || {};
  const who = person(v.owner || v.driver || "");
  const what = car.name || "Unknown vehicle";
  const title = who ? `${possessive(who)} ${what}` : what;

  bar.appendChild(h("div.id",
    h("div.name", title),
    h("div.sub", [v.trim, v.engine, maskVinShort(v.vin)].filter(Boolean).join("  ·  "))));

  bar.appendChild(h("div.spacer"));

  // Visible, not subtle. The failure that matters is thinking you are private
  // when you are not, and this is the one place always in frame.
  if (privacy.on) {
    bar.appendChild(h("button.pill.info.privacy-pill", {
      title: "Identifying details are hidden. Click to show them again.",
      onclick: () => { privacy.on = false; paintBar(); go(); },
    }, "VIN hidden"));
  }

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

// "hub" rather than "drive" as the arrival screen.
//
// Jumping straight to the gauges answers a question the driver did not ask.
// The hub is one tap from the gauges and also one tap from codes, scan and
// live data, and it carries the badges that say which of those is worth
// opening. Arriving on a screen that can route you beats arriving on a screen
// you have to leave.
const ARRIVE = "hub";

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

  const inCar = view === ARRIVE || view === "drive";
  if (want && !inCar && !overridden) {
    location.hash = "#" + ARRIVE;
  } else if (auto.back && !connected && wasConnected === true && inCar) {
    // Unplugged. Land on the overview rather than on a gauge reading nothing.
    location.hash = "#dash";
  }

  wasConnected = connected;
  wasMoving = moving;
}

// Leaving drive mode by hand while the car is still connected is a decision,
// and it sticks. Arriving there by hand is not an override.
function noteManualNav(fromId, toId) {
  // Leaving car mode by hand is the decision that sticks. Moving BETWEEN the
  // hub and the gauges is not leaving it -- both are car screens, and treating
  // a tap on "Drive" as an override would stop the app ever bringing you back.
  const carScreens = (id) => id === ARRIVE || id === "drive";
  if (carScreens(fromId) && !carScreens(toId) && store.connected) overridden = true;
  if (carScreens(toId)) overridden = false;
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
let themeSheet = null;

// APPLIED AS A STYLESHEET, NOT AS INLINE PROPERTIES.
//
// This used to do root.style.setProperty() for every token. An inline style on
// an element beats every rule in every stylesheet, so the theme silently
// outranked the `:root[data-look="..."]` palettes -- and a look could only
// change the four tokens the theme happens not to emit (--hair, --track, and
// until now --bright/--bright-2). Matrix and Night-red repainted a couple of
// meters and left the rail, the vehicle bar, the cards and the stage sitting
// in the desktop theme, which is exactly what "the theme does not carry over
// into the nav and top bar" looks like.
//
// A <style> appended after app.css gives the intended three-layer cascade:
//   app.css :root      the shipped default        (0,1,0), first
//   this sheet :root   the Omarchy theme          (0,1,0), later — wins
//   app.css :root[..]  the look the user picked   (0,2,0) — wins over both
// so an untouched app follows the desktop, and choosing a look overrides it
// deliberately, which is the whole reason a look exists.
async function applyTheme() {
  try {
    const { stamp, vars } = await api.theme();
    if (stamp === themeStamp) return;
    themeStamp = stamp;
    const root = document.documentElement;
    if (!themeSheet) {
      themeSheet = document.createElement("style");
      themeSheet.id = "omarchy-theme";
      document.head.appendChild(themeSheet);
    }
    const decls = Object.entries(vars)
      .filter(([k]) => k !== "mode")
      .map(([k, v]) => `--${k}:${v}`)
      .join(";");
    themeSheet.textContent = `:root{color-scheme:${vars.mode || "dark"};${decls}}`;
    root.dataset.mode = vars.mode || "dark";
  } catch {
    // The stylesheet's own palette is the fallback, and it is the one the app
    // was designed against — so a missing theme is a non-event.
  }
}

async function boot() {
  // Learn mode is a local preference, not a server one: it changes nothing
  // about the car or the data, only how much of the app explains itself. No
  // round trip, so it toggles instantly.
  // The mark at the top of the rail goes to the car dashboard.
  //
  // Seventeen rail items is too many to scan, and "Car" reads as just another
  // section rather than as the screen everything else hangs off. A logo that
  // goes home is the one navigation convention every user already has.
  const hubBtn = document.getElementById("btn-hub");
  if (hubBtn) hubBtn.addEventListener("click", () => { location.hash = "#hub"; });

  const privBtn = document.getElementById("btn-privacy");
  const paintPriv = () => {
    privBtn.setAttribute("aria-pressed", privacy.on ? "true" : "false");
    privBtn.classList.toggle("on", privacy.on);
    privBtn.textContent = privacy.on ? "◉" : "◎";
  };
  privBtn.addEventListener("click", () => {
    const now = privacy.toggle();
    paintPriv();
    paintBar();
    go();
    toast(now ? "VIN, plate and name hidden — safe to photograph."
              : "Identifying details visible again.");
  });
  paintPriv();

  const learnBtn = document.getElementById("btn-learn");
  const paintLearn = () => {
    learnBtn.setAttribute("aria-pressed", learn.on ? "true" : "false");
    learnBtn.classList.toggle("on", learn.on);
  };
  learnBtn.title = "Learn — what this car is, and what everything here means";
  learnBtn.addEventListener("click", () => { location.hash = "#learn"; });
  paintLearn();

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
  // Before the first paint. A night-red look that arrives a beat late is a
  // flash of full-brightness white at the exact moment it matters most.
  applyLook(savedLook());

  await Promise.all([store.boot(), applyTheme(), loadAuto()]);
  document.getElementById("btn-units").textContent = U.units.dist;
  document.getElementById("app").dataset.booting = "0";
  // Plugin screens, loaded at boot.
  //
  // Dynamically imported rather than bundled, because there is no bundler and
  // a plugin is a directory somebody dropped in. Each one is loaded on its own
  // and a failure is contained: a plugin that throws on import loses its own
  // screen and nothing else, which is the difference between a broken plugin
  // and a broken application.
  try {
    const r = await api.plugins();
    for (const v of r.views || []) {
      try {
        const mod = await import(v.src);
        if (typeof mod.default !== "function") continue;
        VIEWS.push({ id: v.id, label: v.label, title: v.title,
                     mount: mod.default, plugin: true });
      } catch (e) {
        console.warn("plugin view failed to load:", v.id, e);
      }
    }
    if ((r.views || []).length) paintRail();
  } catch { /* no plugins, or the endpoint is unavailable */ }

  paintBar();
  go();

  // First run. After the app has drawn, not before: opening on a blank page
  // makes it look like the tour IS the application, and the point of the tour
  // is to describe the thing behind it.
  if (!onboard.done) {
    showOnboarding(document.getElementById("modal-host"), { onClose: go });
  }

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
