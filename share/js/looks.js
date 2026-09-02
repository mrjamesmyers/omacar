// Looks — palette and background effect together, as one choice.
//
// These were nearly built as two controls: a theme picker and an effects
// picker. That would have been worse. Nobody wants the matrix rain over the
// normal palette, and nobody driving at night wants to set a red palette and
// then separately remember to turn the animation off. The combinations that
// make sense are few, and each has a name and an occasion.
//
// So: one control, five looks, each coherent.

import { mountEffect } from "./effects.js";

const KEY = "omacar.look";

export const LOOKS = [
  { id: "normal", label: "Normal", effect: "off",
    note: "Default palette, no background." },
  { id: "green", label: "Matrix", effect: "matrix",
    note: "Green palette with the rain behind it." },
  { id: "laser", label: "Lasers", effect: "lasers",
    note: "Default palette, beams from the bottom edge." },
  { id: "dim", label: "Night · dim", effect: "off",
    note: "Everything pulled down. For a lit cabin after dark." },
  { id: "red", label: "Night · red", effect: "off",
    note: "Red only, to protect dark adaptation on a long drive." },
];

export function savedLook() {
  try {
    const v = localStorage.getItem(KEY);
    return LOOKS.some((l) => l.id === v) ? v : "normal";
  } catch { return "normal"; }
}

export function saveLook(id) {
  try { localStorage.setItem(KEY, id); } catch { /* private mode */ }
}

export function lookById(id) {
  return LOOKS.find((l) => l.id === id) || LOOKS[0];
}

// The palette is applied to #app, NOT to the view.
//
// A look has to survive navigation -- the whole point of night red is that it
// stays red while you move between screens -- so it is set once on the app
// root and never touched by a view mount. Only the background canvas, which is
// genuinely per-view, is mounted and torn down with the hub.
export function applyLook(id) {
  const app = document.getElementById("app");
  if (!app) return;
  const look = lookById(id);
  if (look.id === "normal") app.removeAttribute("data-look");
  else app.setAttribute("data-look", look.id);
}

export function nextLook(id) {
  const i = LOOKS.findIndex((l) => l.id === id);
  return LOOKS[(i + 1) % LOOKS.length].id;
}

// Effect lifecycle, kept here so the hub does not have to know which looks
// carry an animation and which do not.
export function mountLookEffect(host, id) {
  return mountEffect(host, lookById(id).effect);
}
