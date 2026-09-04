// Keeping the screen on while the car is moving.
//
// The complaint this exists for: on a three-leg drive the screensaver kept
// coming up, and the only way to keep looking at the dashboard was to reach
// over and tap a key. That is a bad thing to ask of somebody who is driving,
// and it is the sort of small friction that decides whether a tool gets used
// at all.
//
// WHY A WAKE LOCK AND NOT A SETTING.
//
// The obvious fix is to tell the person to turn their screen timeout off. That
// is the wrong fix twice over: it changes the whole machine on behalf of one
// app, and they then have to remember to change it back, or spend the rest of
// the week watching the laptop sit lit and awake on a desk. A wake lock is
// scoped, temporary, and released the moment it stops being warranted.
//
// WHEN IT IS HELD.
//
// Not "whenever the app is open". A parked car in a garage with the tab left
// up should be allowed to sleep. The lock is taken while the page is visible
// AND something is actually happening: the car is connected, or the radio is
// playing. Both of those are things the person deliberately started, and both
// are states where a screen going black is an annoyance rather than a mercy.
//
// THE PART THAT CATCHES EVERYONE.
//
// A screen wake lock is released BY THE BROWSER whenever the document becomes
// hidden, and it is not given back when the document returns. Acquire it once
// at startup and it works perfectly until the first time you switch windows,
// after which it is silently gone for the rest of the session. So the
// visibility handler below is not a nicety; without it this feature quietly
// stops working after five minutes and nobody can say when it broke.

import { store } from "./core.js";
import { radio } from "./radio.js";

// Chromium treats http://127.0.0.1 and http://localhost as secure, so the
// normal case -- the app served on the same machine -- has the API. Reaching
// the same server from a tablet over the LAN by IP does NOT, and there the API
// is simply absent. That is a browser rule, not something this can argue with,
// so it is detected and reported rather than worked around.
const SUPPORTED = typeof navigator !== "undefined"
  && "wakeLock" in navigator
  && window.isSecureContext;

let lock = null;
let forced = false;
let last = null;

// Fresh enough that the car is plausibly still on the other end. The panel uses
// the same reasoning: a sample nobody has updated in half a minute is a file,
// not a connection.
const STALE = 30;

function carLive() {
  const s = store.sample || {};
  const t = Number(s.t) || 0;
  if (!t) return false;
  if ((Date.now() / 1000) - t > STALE) return false;
  return s.connected === true || s.status === "yielded";
}

function wanted() {
  if (document.hidden) return false;
  if (forced) return true;
  return carLive() || radio.playing;
}

async function apply() {
  const want = wanted();
  if (want === last && (!want || lock)) return;
  last = want;

  if (!want) {
    if (lock) {
      try { await lock.release(); } catch { /* already gone */ }
      lock = null;
    }
    return;
  }
  if (lock || !SUPPORTED) return;
  try {
    lock = await navigator.wakeLock.request("screen");
    // The browser drops the lock on its own when the document hides. Clearing
    // the handle here is what lets the visibility handler take a fresh one
    // instead of believing it still holds the old one.
    lock.addEventListener("release", () => { lock = null; });
  } catch {
    // Denied, or the tab lost focus mid-request. Nothing is broken; the screen
    // simply behaves as it normally would.
    lock = null;
  }
}

document.addEventListener("visibilitychange", apply);
store.on("live", apply);
store.on("car", apply);
radio.on(apply);

// A slow backstop. Everything above is event-driven, but "the car went quiet
// twenty seconds ago" is a state change that fires no event at all, and it is
// exactly the state where the lock should be given up.
setInterval(apply, 10000);
apply();

export const awake = {
  get supported() { return SUPPORTED; },
  get held() { return !!lock; },
  get forced() { return forced; },
  // For a UI toggle, once the navigation rework has settled and there is a
  // stable place to put one.
  set forced(v) { forced = !!v; apply(); },
  // Why the screen is or is not being kept on, in words, for a status line.
  get reason() {
    if (!SUPPORTED) {
      return window.isSecureContext
        ? "this browser has no wake lock"
        : "not a local connection — browsers only allow this over localhost";
    }
    if (forced) return "held on";
    if (document.hidden) return "app not visible";
    if (carLive()) return "car connected";
    if (radio.playing) return "radio playing";
    return "nothing running";
  },
};
