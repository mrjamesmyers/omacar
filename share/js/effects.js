// Background effects for the car dashboard.
//
// WHY 2D CANVAS AND NOT WebGL.
//
// The reference implementations of this sort of thing are WebGL overlays, and
// WebGL would be the obvious choice on a desktop. This runs on a 2-core Yoga
// 710 with Intel graphics that has already had its compositor crash once in
// this project from CPU starvation, and it runs in a car where the machine is
// also polling a serial port. A 2D canvas with additive compositing produces
// the same beams-and-glow look for a fraction of the risk, with no shader
// compilation to fail on an old driver.
//
// EVERY EFFECT HERE IS SUBORDINATE TO THE CAR.
//
// This is decoration on a diagnostic tool. It must never be the reason a gauge
// stutters, so:
//   - 30fps, not 60. Nothing here benefits from the extra frames.
//   - Stops dead when the tab is hidden or the view unmounts.
//   - Honours prefers-reduced-motion by refusing to start.
//   - Particle counts scale with area, so a big screen does not mean a big
//     CPU bill.
//   - Draws behind content at low opacity: legibility wins every time.

const KEY = "omacar.effect";
export const EFFECTS = ["off", "matrix", "lasers"];

export function savedEffect() {
  try {
    const v = localStorage.getItem(KEY);
    return EFFECTS.includes(v) ? v : "off";
  } catch { return "off"; }
}

export function saveEffect(v) {
  try { localStorage.setItem(KEY, v); } catch { /* private mode */ }
}

function reducedMotion() {
  try { return matchMedia("(prefers-reduced-motion: reduce)").matches; }
  catch { return false; }
}

// Glyphs: half-width katakana, as the effect is known for, mixed with hex
// digits. The hex is not decoration -- this is a tool whose whole discovery
// story is hexadecimal identifiers, and the rain reads as belonging to it
// rather than being borrowed from a film.
const GLYPHS = "0123456789ABCDEF" +
  "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ";

export function mountEffect(host, mode) {
  if (mode === "off" || reducedMotion()) return () => {};

  const canvas = document.createElement("canvas");
  canvas.className = "fx-canvas";
  host.appendChild(canvas);
  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) { canvas.remove(); return () => {}; }

  // Cap the pixel ratio. A HiDPI panel would otherwise quadruple the fill cost
  // for a background nobody is looking at directly.
  // Read the palette rather than hardcoding it. The rain used a near-white
  // head glyph, which is fine on the default look and wrong in green -- where
  // the whole point is that nothing is white. Taking the colours from the
  // tokens means the effect follows whatever look is active, including any
  // added later, with no further edits here.
  const cs = getComputedStyle(document.getElementById("app") || document.body);
  const tok = (n, fb) => (cs.getPropertyValue(n) || "").trim() || fb;
  const HEAD = tok("--bright", "#BEFFDC");
  const TAIL = tok("--ok", "#4ACE8A");
  const GROUND = tok("--ground", "#070B0D");

  const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  let w = 0, h = 0, cols = 0, drops = [], beams = [];
  const cell = 16;

  function resize() {
    const r = host.getBoundingClientRect();
    w = Math.max(1, Math.floor(r.width));
    h = Math.max(1, Math.floor(r.height));
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    cols = Math.ceil(w / cell);
    drops = new Array(cols).fill(0).map(() => Math.random() * -40);

    // Rays fan from points along a glowing emitter at the bottom edge. The
    // first attempt used soft parallel columns, which read as light shafts
    // rather than lasers -- a laser is a thin bright line with bloom around
    // it, not a wide gradient. So: a crisp core, a tight glow, and an angle.
    const n = Math.max(9, Math.min(30, Math.round(w / 62)));
    beams = new Array(n).fill(0).map(() => ({
      x: Math.random(),                       // origin along the emitter
      angle: (Math.random() - 0.5) * 0.95,    // radians from vertical
      sweep: (Math.random() - 0.5) * 0.28,    // how far it swings
      speed: 0.18 + Math.random() * 0.55,
      phase: Math.random() * Math.PI * 2,
      len: 0.55 + Math.random() * 0.5,        // fraction of height
      core: 0.7 + Math.random() * 1.5,        // core width in px
      hueOff: Math.random() * 40,
    }));
  }

  const ro = new ResizeObserver(resize);
  ro.observe(host);
  resize();

  let raf = 0;
  let last = 0;
  let t0 = performance.now();
  let stopped = false;
  const FRAME = 1000 / 30;

  function matrix(now) {
    // Trail rather than clear: the fade IS the effect.
    // The fade uses the look's own ground colour, so the trail dissolves into
    // the page instead of towards a dark teal that only suits one palette.
    ctx.globalAlpha = 0.10;
    ctx.fillStyle = GROUND;
    ctx.fillRect(0, 0, w, h);
    ctx.globalAlpha = 1;
    // A literal stack, NOT var(--mono). Canvas parses this string itself and
    // knows nothing about CSS custom properties: `var(--mono)` is invalid, the
    // assignment is silently ignored, and the glyphs fall back to 10px
    // sans-serif -- which at cell size reads as "the effect is broken".
    ctx.font = `${cell - 3}px "JetBrains Mono", ui-monospace, Menlo, monospace`;
    ctx.textBaseline = "top";
    for (let i = 0; i < cols; i++) {
      const y = drops[i] * cell;
      if (y > -cell) {
        const ch = GLYPHS[(Math.random() * GLYPHS.length) | 0];
        // The leading glyph is bright; the tail is the theme's signal green.
        ctx.fillStyle = HEAD;
        ctx.globalAlpha = 0.9;
        ctx.fillText(ch, i * cell, y);
        ctx.globalAlpha = 0.38;
        ctx.fillStyle = TAIL;
        ctx.fillText(GLYPHS[(Math.random() * GLYPHS.length) | 0], i * cell, y - cell);
        ctx.globalAlpha = 1;
      }
      drops[i] += 0.55;
      if (y > h && Math.random() > 0.975) drops[i] = Math.random() * -20;
    }
  }

  function lasers(now) {
    ctx.clearRect(0, 0, w, h);
    const t = (now - t0) / 1000;
    // One hue for the whole field, drifting. Per-beam colour reads as confetti.
    const hue = (t * 20) % 360;
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";

    for (const b of beams) {
      const x0 = b.x * w;
      const a = b.angle + Math.sin(t * b.speed + b.phase) * b.sweep;
      const len = h * b.len;
      const x1 = x0 + Math.sin(a) * len;
      const y1 = h - Math.cos(a) * len;
      const bh = (hue + b.hueOff) % 360;

      // Three passes: wide bloom, mid glow, then a near-white core. That
      // stacking is what makes a line look like it is EMITTING rather than
      // just being a coloured stroke -- a single stroke at any width reads
      // flat no matter how bright you make it.
      const g = ctx.createLinearGradient(x0, h, x1, y1);
      g.addColorStop(0, `hsla(${bh}, 100%, 62%, 0.55)`);
      g.addColorStop(0.55, `hsla(${bh}, 100%, 60%, 0.16)`);
      g.addColorStop(1, `hsla(${bh}, 100%, 60%, 0)`);

      ctx.strokeStyle = g;
      ctx.lineWidth = b.core * 7;
      ctx.beginPath(); ctx.moveTo(x0, h); ctx.lineTo(x1, y1); ctx.stroke();

      ctx.lineWidth = b.core * 2.4;
      ctx.beginPath(); ctx.moveTo(x0, h); ctx.lineTo(x1, y1); ctx.stroke();

      const core = ctx.createLinearGradient(x0, h, x1, y1);
      core.addColorStop(0, `hsla(${bh}, 100%, 92%, 0.95)`);
      core.addColorStop(0.7, `hsla(${bh}, 100%, 80%, 0.25)`);
      core.addColorStop(1, `hsla(${bh}, 100%, 80%, 0)`);
      ctx.strokeStyle = core;
      ctx.lineWidth = b.core;
      ctx.beginPath(); ctx.moveTo(x0, h); ctx.lineTo(x1, y1); ctx.stroke();

      // The hot spot where the ray leaves the emitter.
      const dot = ctx.createRadialGradient(x0, h, 0, x0, h, 26);
      dot.addColorStop(0, `hsla(${bh}, 100%, 88%, 0.75)`);
      dot.addColorStop(1, `hsla(${bh}, 100%, 70%, 0)`);
      ctx.fillStyle = dot;
      ctx.fillRect(x0 - 26, h - 26, 52, 26);
    }

    // The emitter itself: a bright line along the bottom with bloom above it,
    // so the rays visibly come FROM something.
    const bar = ctx.createLinearGradient(0, h, 0, h - 70);
    bar.addColorStop(0, `hsla(${hue}, 100%, 66%, 0.42)`);
    bar.addColorStop(1, `hsla(${hue}, 100%, 60%, 0)`);
    ctx.fillStyle = bar;
    ctx.fillRect(0, h - 70, w, 70);
    ctx.fillStyle = `hsla(${hue}, 100%, 88%, 0.85)`;
    ctx.fillRect(0, h - 2, w, 2);

    ctx.globalCompositeOperation = "source-over";
  }

  const draw = mode === "matrix" ? matrix : lasers;

  function loop(now) {
    if (stopped) return;
    raf = requestAnimationFrame(loop);
    if (now - last < FRAME) return;
    last = now;
    draw(now);
  }

  function onVisibility() {
    if (document.hidden) {
      cancelAnimationFrame(raf); raf = 0;
    } else if (!raf && !stopped) {
      last = 0;
      raf = requestAnimationFrame(loop);
    }
  }
  document.addEventListener("visibilitychange", onVisibility);
  raf = requestAnimationFrame(loop);

  return () => {
    stopped = true;
    cancelAnimationFrame(raf);
    document.removeEventListener("visibilitychange", onVisibility);
    ro.disconnect();
    canvas.remove();
  };
}
