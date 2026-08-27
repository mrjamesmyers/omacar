// Charts, drawn on a canvas because there is no chart library here and there
// should not be one. Four shapes cover the whole tool:
//
//   sparkline    a trend at a glance, no axes, no labels
//   bars         distance by month, with economy over it as a line
//   scope        the data lab: several channels, shared time axis, a cursor
//   dial         one value against its own range
//
// Every one of them takes values already converted to display units. Nothing
// in this file knows what a mile is.

const DPR = () => Math.max(1, Math.min(3, window.devicePixelRatio || 1));

function fit(canvas, cssHeight) {
  const w = canvas.clientWidth || canvas.parentElement.clientWidth || 600;
  const r = DPR();
  canvas.width = Math.round(w * r);
  canvas.height = Math.round(cssHeight * r);
  canvas.style.height = cssHeight + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(r, 0, 0, r, 0, 0);
  ctx.clearRect(0, 0, w, cssHeight);
  return { ctx, w, h: cssHeight };
}

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export const PALETTE = ["#4FA8E8", "#4ACE8A", "#E5B457", "#E85D4E",
                        "#8B7CF0", "#64D2FF", "#F09BC8", "#9AE66E"];

// ---------------------------------------------------------------- sparkline
export function sparkline(canvas, series, opts = {}) {
  const height = opts.height || 34;
  const { ctx, w, h } = fit(canvas, height);
  const pts = series.filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (pts.length < 2) return;
  const lo = opts.floor !== undefined ? Math.min(opts.floor, ...pts) : Math.min(...pts);
  const hi = Math.max(...pts);
  const span = hi - lo || 1;
  const x = (i) => (w - 2) * (i / (series.length - 1)) + 1;
  const y = (v) => h - 2 - (h - 5) * ((v - lo) / span);

  const tint = opts.tint || PALETTE[0];
  ctx.beginPath();
  let started = false;
  series.forEach((v, i) => {
    if (v === null || v === undefined) { started = false; return; }
    if (!started) { ctx.moveTo(x(i), y(v)); started = true; } else ctx.lineTo(x(i), y(v));
  });
  if (opts.fill !== false) {
    ctx.lineTo(x(series.length - 1), h);
    ctx.lineTo(x(0), h);
    ctx.closePath();
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, tint + "55");
    g.addColorStop(1, tint + "06");
    ctx.fillStyle = g;
    ctx.fill();
  }
  ctx.beginPath();
  started = false;
  series.forEach((v, i) => {
    if (v === null || v === undefined) { started = false; return; }
    if (!started) { ctx.moveTo(x(i), y(v)); started = true; } else ctx.lineTo(x(i), y(v));
  });
  ctx.strokeStyle = tint;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = "round";
  ctx.stroke();
}

// ------------------------------------------------------------ bars + line
// Distance as bars, economy as a line over them. Two measures on one chart
// because the question is always both at once — did I drive more, and did it
// cost more per mile — and two charts would put the answer in two places.
export function barsAndLine(canvas, series, opts = {}) {
  const height = opts.height || 150;
  const { ctx, w, h } = fit(canvas, height);
  const n = series.length;
  if (!n) return;
  const labelH = 16;
  const plot = h - labelH;
  const gap = Math.max(2, (w / n) * 0.24);
  const bw = (w - gap * (n - 1)) / n;
  const peak = Math.max(1, ...series.map((s) => s.bar || 0));

  let lo = Infinity, hi = -Infinity;
  for (const s of series) {
    if (s.line === null || s.line === undefined) continue;
    lo = Math.min(lo, s.line); hi = Math.max(hi, s.line);
  }
  // The line is scaled to its own range, not to zero: the interesting part of
  // a year of economy is a spread of five, and anchoring at the origin
  // flattens it into a straight line that says nothing.
  const haveLine = Number.isFinite(lo) && hi > lo;
  const pad = haveLine ? (hi - lo) * 0.3 : 1;
  lo -= pad; hi += pad;

  const bx = (i) => i * (bw + gap);
  const by = (v) => plot - plot * 0.9 * (v / peak);
  const ly = (v) => plot * 0.1 + plot * 0.74 * (1 - (v - lo) / (hi - lo));

  const bar = opts.barTint || PALETTE[0];
  series.forEach((s, i) => {
    const y = by(s.bar || 0);
    const g = ctx.createLinearGradient(0, y, 0, plot);
    g.addColorStop(0, bar + "D0");
    g.addColorStop(1, bar + "38");
    ctx.fillStyle = g;
    const r = Math.min(bw / 2, 3), x = bx(i);
    ctx.beginPath();
    ctx.moveTo(x, plot);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.lineTo(x + bw - r, y);
    ctx.quadraticCurveTo(x + bw, y, x + bw, y + r);
    ctx.lineTo(x + bw, plot);
    ctx.closePath();
    ctx.fill();
  });

  if (haveLine) {
    const tint = opts.lineTint || PALETTE[2];
    ctx.strokeStyle = tint;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    let drawing = false;
    series.forEach((s, i) => {
      // A month the car did not move has no economy at all. Break the line
      // rather than dive to zero and invent a month of perfect driving.
      if (s.line === null || s.line === undefined) { drawing = false; return; }
      const px = bx(i) + bw / 2, py = ly(s.line);
      if (!drawing) { ctx.moveTo(px, py); drawing = true; } else ctx.lineTo(px, py);
    });
    ctx.stroke();
    ctx.fillStyle = tint;
    series.forEach((s, i) => {
      if (s.line === null || s.line === undefined) return;
      ctx.beginPath();
      ctx.arc(bx(i) + bw / 2, ly(s.line), 2.4, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  ctx.font = "10px " + css("--mono");
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  series.forEach((s, i) => {
    ctx.fillStyle = i === n - 1 ? css("--dim") : css("--ghost");
    ctx.fillText(s.label, bx(i) + bw / 2, plot + 4);
  });
}

// -------------------------------------------------------------- the scope
// Several channels on a shared time axis, each with its own vertical scale,
// because comparing engine speed against coolant temperature on one axis is
// how you get two flat lines. The cursor reports every channel at one instant,
// which is the whole reason a technician uses a scope rather than a gauge.
export function scope(canvas, opts) {
  const { rows, channels, height = 300 } = opts;
  const { ctx, w, h } = fit(canvas, height);
  if (!rows.length || !channels.length) {
    ctx.fillStyle = css("--ghost");
    ctx.font = "12px " + css("--mono");
    ctx.textAlign = "center";
    ctx.fillText("no samples in this span", w / 2, h / 2);
    return null;
  }

  const t0 = rows[0].t, t1 = rows[rows.length - 1].t;
  const span = Math.max(1, t1 - t0);
  const padL = 4, padR = 4, padT = 8, padB = 20;
  const plotW = w - padL - padR;
  const laneH = (h - padT - padB) / channels.length;

  // Time gridlines, spaced so there are always five or so however long the
  // span is.
  const gridN = 6;
  ctx.strokeStyle = "#101A1D";
  ctx.lineWidth = 1;
  ctx.font = "9px " + css("--mono");
  ctx.textBaseline = "top";
  ctx.textAlign = "center";
  for (let i = 0; i <= gridN; i++) {
    const x = padL + plotW * (i / gridN);
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, h - padB);
    ctx.stroke();
    const at = new Date((t0 + span * (i / gridN)) * 1000);
    ctx.fillStyle = css("--ghost");
    ctx.fillText(
      `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}:${String(at.getSeconds()).padStart(2, "0")}`,
      Math.min(w - 22, Math.max(22, x)), h - padB + 5);
  }

  const scales = [];
  channels.forEach((ch, ci) => {
    const vals = rows.map((r) => ch.get(r)).filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
    if (!vals.length) { scales.push(null); return; }
    let lo = ch.min !== undefined ? ch.min : Math.min(...vals);
    let hi = ch.max !== undefined ? ch.max : Math.max(...vals);
    if (hi - lo < 1e-6) { hi = lo + 1; }
    const pad = (hi - lo) * 0.12;
    lo -= pad; hi += pad;
    scales.push({ lo, hi });

    const top = padT + laneH * ci;
    const y = (v) => top + laneH - 6 - (laneH - 12) * ((v - lo) / (hi - lo));
    const x = (t) => padL + plotW * ((t - t0) / span);

    // The lane's own baseline, so several stacked channels read as several
    // instruments rather than as one tangle.
    ctx.strokeStyle = "#0D1518";
    ctx.beginPath();
    ctx.moveTo(padL, top + laneH - 3);
    ctx.lineTo(w - padR, top + laneH - 3);
    ctx.stroke();

    ctx.beginPath();
    let started = false;
    for (const r of rows) {
      const v = ch.get(r);
      if (v === null || v === undefined || Number.isNaN(v)) { started = false; continue; }
      const px = x(r.t), py = y(v);
      if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = ch.tint;
    ctx.lineWidth = 1.4;
    ctx.lineJoin = "round";
    ctx.stroke();

    ctx.fillStyle = css("--ghost");
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.font = "9px " + css("--mono");
    ctx.fillText(`${ch.label}  ${lo.toFixed(ch.dp || 0)} – ${hi.toFixed(ch.dp || 0)}`, padL + 3, top + 2);
  });

  // The lookup the cursor uses. Returned rather than bound, so the caller owns
  // the interaction and this stays a drawing function.
  return {
    t0, t1, padL, plotW,
    at(px) {
      const frac = Math.max(0, Math.min(1, (px - padL) / plotW));
      const t = t0 + span * frac;
      let best = rows[0], bd = Infinity;
      for (const r of rows) {
        const d = Math.abs(r.t - t);
        if (d < bd) { bd = d; best = r; }
      }
      return { row: best, x: padL + plotW * frac };
    },
  };
}

// ---------------------------------------------------------------- the dial
// One value against its own limits — used for Mode 06, where the whole point
// is where the measurement sits between the floor and the ceiling.
export function dial(canvas, { value, lo, hi, tint, height = 62 }) {
  const { ctx, w, h } = fit(canvas, height);
  const cx = w / 2, cy = h - 6, r = Math.min(w / 2 - 6, h - 12);
  const A0 = Math.PI, A1 = 2 * Math.PI;

  ctx.lineWidth = 7;
  ctx.lineCap = "round";
  ctx.strokeStyle = "#16222699";
  ctx.beginPath();
  ctx.arc(cx, cy, r, A0, A1);
  ctx.stroke();

  const bottom = lo !== null && lo !== undefined ? lo : 0;
  const top = hi !== null && hi !== undefined ? hi : Math.max(value * 1.4, 1);
  const frac = Math.max(0, Math.min(1, (value - bottom) / ((top - bottom) || 1)));
  ctx.strokeStyle = tint;
  ctx.beginPath();
  ctx.arc(cx, cy, r, A0, A0 + (A1 - A0) * frac);
  ctx.stroke();
}
