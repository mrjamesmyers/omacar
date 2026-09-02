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
export const EFFECTS = ["off", "matrix", "aurora"];

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
  const cs = getComputedStyle(document.documentElement);
  const tok = (n, fb) => (cs.getPropertyValue(n) || "").trim() || fb;
  const HEAD = tok("--bright", "#BEFFDC");
  const TAIL = tok("--ok", "#4ACE8A");
  const GROUND = tok("--ground", "#070B0D");

  // The aurora's colours, also from tokens. Four semantic hues rather than a
  // hardcoded palette, so the drift is blue-violet on the desktop theme, all
  // greens under Matrix, and stays red-only under Night red -- where a stray
  // blue in the background would undo the entire point of the look.
  // Four DISTINCT roles. --accent and --info are the same value on plenty of
  // themes (they are both #7aa2f7 on Tokyo Night), and two blobs of one colour
  // is a two-colour gradient wearing a four-colour costume.
  const WASH = [tok("--ai", "#8B7CF0"), tok("--info", "#4FA8E8"),
                tok("--ok", "#4ACE8A"), tok("--warn", "#E5B457")];

  function rgbOf(v, fb) {
    const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec((v || "").trim());
    if (!m) return fb;
    let x = m[1];
    if (x.length === 3) x = x.split("").map((c) => c + c).join("");
    return [parseInt(x.slice(0, 2), 16), parseInt(x.slice(2, 4), 16),
            parseInt(x.slice(4, 6), 16)];
  }

  // Push a colour away from grey without making it lighter.
  //
  // A theme's semantic colours are picked to be READ as text, so they sit at a
  // sensible middle chroma. Added into a background at low alpha they arrive
  // washed, and the instinct is to turn the alpha up -- which buys visibility
  // with luminance, and luminance is the one thing the driving screen cannot
  // spare. Chroma is nearly free by comparison: the eye reads a saturated
  // violet as far more present than a pale one of the same brightness.
  //
  // So each channel is pushed away from the colour's own mean and the result
  // is renormalised back to that mean. Hue is preserved, brightness is not
  // raised, and only the colourfulness changes.
  function saturate(rgb, k) {
    const mean = (rgb[0] + rgb[1] + rgb[2]) / 3;
    const out = rgb.map((c) => mean + (c - mean) * k);
    // Renormalise: clipping a channel at 255 would otherwise drag the whole
    // colour lighter and undo the point of doing this instead of raising alpha.
    const m2 = (out[0] + out[1] + out[2]) / 3;
    const fix = m2 > 0 ? mean / m2 : 1;
    return out.map((c) => Math.max(0, Math.min(255, Math.round(c * fix))));
  }

  const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  let w = 0, h = 0, cols = 0, drops = [], blobs = [];
  const cell = 16;

  // THE AURORA IS DRAWN SMALL AND BLOWN UP.
  //
  // Four soft radial fills at 3840x2160 is a fill-rate bill this machine has
  // no business paying for a background. But the thing being drawn has no
  // detail in it -- it is four blurs -- so it is rendered into a buffer a
  // couple of hundred pixels across and scaled to fit. The bilinear upscale
  // costs one blit and, on a field this smooth, IS the blur: the softness that
  // would otherwise need a filter comes free with the interpolation.
  const LOW = 160;
  const buf = document.createElement("canvas");
  const bctx = buf.getContext("2d", { alpha: false });

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

    // The buffer keeps the viewport's shape so the blobs are not stretched.
    const long = Math.max(w, h) || 1;
    buf.width = Math.max(2, Math.round(LOW * w / long));
    buf.height = Math.max(2, Math.round(LOW * h / long));
  }

  // Four drifting fields, each on its own slow Lissajous path. Coprime-ish
  // periods so the arrangement never visibly repeats -- a background that
  // loops is a background you start watching, and this one has to stay
  // ignorable for the length of a drive.
  blobs = WASH.map((c, i) => ({
    rgb: saturate(rgbOf(c, [90, 140, 220]), 1.55),
    ax: 0.38 + i * 0.05,           // travel, as a fraction of the viewport
    ay: 0.32 + ((i * 7) % 5) * 0.035,
    sx: 0.047 + i * 0.011,         // radians a second: a full drift is ~2 min
    sy: 0.031 + ((i * 3) % 4) * 0.009,
    px: i * 1.7,
    py: i * 2.3 + 0.6,
    // Radius, as a fraction of the long edge. Deliberately smaller than the
    // travel: four wide fields all overlapping everywhere sum to one flat
    // wash, and adding a green to a warm additively makes olive, not aurora.
    // Tighter blobs that move further keep their own colour, which is both
    // prettier and cheaper -- less overlap is a lower peak for the same alpha.
    r: 0.44 + ((i * 5) % 3) * 0.09,
    // CORE ALPHA. THE ONE KNOB, AND WHAT IT COSTS.
    //
    // Turn this up to make the aurora more present. It is worth knowing what
    // is being spent, because the field sits behind the driving screen, whose
    // type is --bright on --ground and is read through a windscreen. Each step
    // below was rendered and the brightest point of the field sampled:
    //
    //   alpha  peak pixel        --bright holds
    //   0.12   rgb( 54, 53, 59)  11.8:1   too faint to be worth having
    //   0.30   rgb( 77, 83, 66)   7.8:1
    //   0.40   rgb(101,110, 85)   5.2:1   <- here
    //
    // 5.2:1 clears WCAG AA for normal text and the hub's type is neither
    // normal nor small -- it is large and bold by design. What it gives up is
    // glare margin: this is a brighter background than the sunlight-first
    // version, chosen deliberately.
    //
    // Two things make that affordable. saturate() above buys visibility with
    // chroma instead of luminance, and the radius is kept below the travel so
    // the blobs mostly do not stack -- at 0.30 the untightened version peaked
    // at rgb(112,110,117) for 4.9:1, WORSE than 0.40 is now while looking
    // duller. Reach for those two before reaching for this number.
    a: 0.40 - i * 0.045,
  }));

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

  function aurora(now) {
    const t = (now - t0) / 1000;
    const bw = buf.width, bh = buf.height;
    const long = Math.max(bw, bh);

    // The ground first, opaque: this is a background, not a veil over one.
    bctx.globalCompositeOperation = "source-over";
    bctx.fillStyle = GROUND;
    bctx.fillRect(0, 0, bw, bh);

    // Additive, so where two fields overlap they brighten into a third colour
    // rather than one covering the other. That blending is the whole effect --
    // painted normally these are four flat circles.
    bctx.globalCompositeOperation = "lighter";
    for (const b of blobs) {
      const x = (0.5 + Math.sin(t * b.sx + b.px) * b.ax) * bw;
      const y = (0.5 + Math.cos(t * b.sy + b.py) * b.ay) * bh;
      const r = b.r * long;
      const g = bctx.createRadialGradient(x, y, 0, x, y, r);
      const [cr, cg, cb] = b.rgb;
      g.addColorStop(0, `rgba(${cr}, ${cg}, ${cb}, ${b.a})`);
      g.addColorStop(0.55, `rgba(${cr}, ${cg}, ${cb}, ${b.a * 0.32})`);
      g.addColorStop(1, `rgba(${cr}, ${cg}, ${cb}, 0)`);
      bctx.fillStyle = g;
      bctx.fillRect(x - r, y - r, r * 2, r * 2);
    }
    bctx.globalCompositeOperation = "source-over";

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(buf, 0, 0, bw, bh, 0, 0, w, h);
  }

  const draw = mode === "matrix" ? matrix : aurora;

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
