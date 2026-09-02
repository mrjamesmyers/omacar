// Service resets and functional tests.
//
// This is the screen that decides whether OmaCar is a diagnostic tool or a
// gauge with opinions. Oil life, parking brake retract, steering angle,
// TPMS relearn, throttle relearn — these are the jobs that most often force
// somebody to pay a shop for ninety seconds of work.
//
// It is also the screen where being wrong costs the most, so two rules shape
// the whole thing:
//
// 1. CONFIDENCE IS SHOWN BEFORE THE BUTTON. A routine identifier is
//    manufacturer-specific, and the same number means different things on
//    different makes. A definition that has not been confirmed on a real car
//    says so in the place you cannot miss it, and looks different from one
//    that has.
//
// 2. AN EMPTY LIST IS A VALID ANSWER. When nothing is verified for this
//    vehicle, this screen says exactly that and explains how to contribute one.
//    It never fills the space with plausible-looking guesses, because a guessed
//    routine identifier is not a wrong number on a screen — it is a procedure
//    running on a car with somebody's hands in it.

import { h, store, api, toast, confirmDialog } from "../core.js";
import { explain } from "../learn.js";

const TONE = { verified: "ok", reported: "warn", unverified: "bad" };
const CONF_TEXT = {
  verified: "Confirmed on a real vehicle",
  reported: "Reported to work, not confirmed here",
  unverified: "Not confirmed — treat as experimental",
};

export default function resets(root) {
  let defs = [];
  let procs = [];
  let armed = false;

  const wrap = h("div.resets");
  root.appendChild(wrap);

  async function load() {
    try {
      const r = await api.resets();
      defs = r.resets || [];
      armed = !!r.write_armed;
    } catch (e) {
      defs = [];
      toast("Could not load reset definitions: " + (e.message || e), "bad");
    }
    try {
      procs = (await api.procedures()).procedures || [];
    } catch {
      procs = [];
    }
    draw();
  }

  // Owner procedures: instructions, not requests. Nothing here touches the car,
  // which is why they render as something you read rather than a button you
  // press — and why a make with no OBD routines can still be well served.
  function procedure(p) {
    return h("details.proc",
      h("summary",
        h("span.proc-name", p.name),
        p.symptom ? h("span.proc-sym", p.symptom) : null),
      h("div.proc-body",
        // The most useful sentence on the whole screen when it applies: this
        // is not your problem, do not spend an afternoon on it.
        p.not_for
          ? h("div.proc-notfor",
              h("strong", "Not this, if: "), p.not_for)
          : null,
        h("ol.proc-steps", ...(p.steps || []).map((s) => h("li", s))),
        (p.notes || []).length
          ? h("div.proc-notes", ...(p.notes || []).map((n) => h("p.lede", n)))
          : null,
        h("p.sub", "Source: " + (p.source || "unstated"))));
  }

  async function run(spec) {
    const ok = await confirmDialog({
      title: spec.name,
      body: h("div.sect",
        h("p.lede", spec.warning || "This writes to the car."),
        (spec.preconditions || []).length
          ? h("div",
              h("div.eyebrow", "Before you run this"),
              h("ul.tight", ...(spec.preconditions || []).map((p) => h("li", p))))
          : null,
        h("p.lede.sub", "Source: " + (spec.source || "unstated")),
        h("p.lede", "Confirming also arms write mode for fifteen minutes. It will "
          + "still refuse if the car is moving or the battery is low.")),
      confirm: "Run " + spec.name,
    });
    if (!ok) return;
    try {
      await api.writeMode(true, 15);
      const r = await api.runReset(spec.id, spec.header || undefined);
      const bad = (r.steps || []).find((s) => s.kind === "negative");
      if (bad) {
        toast(`The module refused: ${bad.detail}`, "bad");
      } else {
        toast(`${r.reset} completed.`);
      }
      await store.refreshCar();
      load();
    } catch (e) {
      toast(String(e.message || e), "bad");
    }
  }

  function card(spec) {
    const conf = spec.confidence || "unverified";
    return h("section.card",
      h("div.row.wrapline",
        h("div", { style: { minWidth: "0" } },
          h("div.title", spec.name),
          h("div.sub", spec.category || "")),
        h("div.right.row.wrapline", { style: { gap: "8px" } },
          h("span.pill." + (TONE[conf] || "bad"), CONF_TEXT[conf] || conf),
          h("button.btn" + (conf === "verified" ? ".primary" : ""), {
            onclick: () => run(spec),
          }, "Run"))),
      h("p.lede", { style: { marginTop: "10px" } }, spec.warning || ""),
      (spec.confirmed_on || []).length
        ? h("div.sub", "Confirmed on: " + spec.confirmed_on.join(", "))
        : h("div.sub.warn", "Not yet confirmed on any vehicle."));
  }

  function draw() {
    while (wrap.firstChild) wrap.removeChild(wrap.firstChild);

    const ex = explain(h, "resets");
    if (ex) wrap.appendChild(ex);

    wrap.appendChild(h("section.card",
      h("div.eyebrow", armed ? "Write mode armed" : "Write mode disarmed"),
      h("div.title", "Service resets and functional tests"),
      h("p.lede", "These write to the car. Each one states what it does before it "
        + "runs, and every one refuses while the car is moving or the battery is "
        + "below 12.2 volts.")));

    const service = defs.filter((d) => d.category !== "clear");
    const clears = defs.filter((d) => d.category === "clear");

    if (!service.length) {
      // The honest empty state. See the note at the top of this file.
      wrap.appendChild(h("section.card.tint-warn",
        h("div.title", "No service resets are verified for this vehicle yet"),
        h("p.lede", "Oil life, parking brake, steering angle, TPMS and throttle "
          + "relearn are all manufacturer-specific routines, and the identifiers "
          + "are not published."),
        h("p.lede", "They also cannot be discovered by sweeping, the way readable "
          + "values can. A routine is a procedure the module runs — guessing its "
          + "number could spin a fan, cycle an ABS pump, or retract a parking "
          + "brake. So OmaCar ships only what somebody has confirmed on a real "
          + "car, and shows you this instead of a list of guesses."),
        h("p.lede", "If you have a service manual procedure or a verified capture "
          + "for your make, adding it is a small JSON file — see doc/RESETS.md. "
          + "One person's contribution covers that model for everybody.")));
    } else {
      for (const s of service) wrap.appendChild(card(s));
    }

    if (clears.length) {
      wrap.appendChild(h("div.eyebrow", { style: { marginTop: "22px" } }, "Clearing"));
      for (const s of clears) wrap.appendChild(card(s));
    }

    if (procs.length) {
      const list = h("div.procs");
      const paint = (q) => {
        while (list.firstChild) list.removeChild(list.firstChild);
        // Match against the symptom too, not just the name. People arrive here
        // knowing what went wrong, not what the procedure is called -- "window"
        // and "after battery" should both find the auto-up relearn.
        const needle = (q || "").trim().toLowerCase();
        const hits = !needle ? procs : procs.filter((p) =>
          [p.name, p.symptom, p.category, (p.notes || []).join(" "),
           (p.steps || []).join(" ")]
            .join(" ").toLowerCase().includes(needle));
        if (!hits.length) {
          list.appendChild(h("p.lede", `Nothing matches “${q}”. `
            + "Procedures are contributed — see doc/RESETS.md to add one."));
          return;
        }
        for (const p of hits) list.appendChild(procedure(p));
      };

      const search = h("input.input", {
        type: "search",
        placeholder: "Search — try “battery”, “window”, “code”, “light”",
        "aria-label": "Search procedures",
        oninput: (e) => paint(e.target.value),
      });

      wrap.appendChild(h("section.card",
        h("div.eyebrow", { style: { marginTop: "10px" } }, "No tool needed"),
        h("div.title", "Procedures you do yourself"),
        h("p.lede", "A surprising amount of what people buy a scan tool for is not "
          + "a diagnostic operation at all — it is a sequence of buttons on your own "
          + "dashboard. These need nothing plugged in."),
        h("div", { style: { marginTop: "12px" } }, search),
        list));
      paint("");
    }
  }

  draw();
  load();
}
