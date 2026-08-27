// The ambient ring, lifted whole from the cluster it started as.
//
// It borrows the CR-Z's own language: blue in NORMAL and ECON, greening as you
// drive efficiently, committing to red in SPORT. Colour is efficiency, the
// bright arc is road speed, and a slim inner arc is engine speed.
//
// The shader declares `precision highp float`. At mediump the hash collapses on
// this machine's integrated GPU and the ring renders black — and software or
// headless GL renders it correctly, which hides the bug. Do not "simplify" this
// to mediump, and verify changes on the real display.

export const VERT =
  "attribute vec2 p; varying vec2 uv;" +
  "void main(){ uv = p; gl_Position = vec4(p, 0.0, 1.0); }";

// highp is load-bearing — see the note above.
const FRAG = [
    "precision highp float;",
    "varying vec2 uv;",
    "uniform float uEff;",    // 0..1 efficiency
    "uniform float uSpeed;",  // 0..1 of MAX_SPEED_KPH
    "uniform float uRpm;",    // 0..1 of MAX_RPM
    "uniform float uSport;",  // 0..1 blend toward the sport palette
    "uniform float uLive;",   // 0 when disconnected: everything goes cold
    "",
    "const float PI = 3.14159265;",
    "const float SWEEP = 4.712389;",           // 270 degrees
    "const float START = 2.356194;",           // 135 degrees, opening at the bottom
    "",
    "float band(float d, float w, float soft){",
    "  return smoothstep(w + soft, w, abs(d));",
    "}",
    "",
    "void main(){",
    "  vec2 q = uv;",
    "  float r = length(q);",
    "  float a = atan(-q.x, -q.y);",          // 0 at the bottom, growing clockwise
    "  if (a < 0.0) a += 2.0 * PI;",
    "  float t = (a + START - PI) / SWEEP;",  // 0..1 along the sweep
    "",
    "  vec3 cold  = vec3(0.243, 0.486, 0.769);",
    "  vec3 frugal= vec3(0.290, 0.808, 0.541);",
    "  vec3 hot   = vec3(0.878, 0.282, 0.231);",
    "  vec3 col = mix(cold, frugal, clamp(uEff, 0.0, 1.0));",
    "  col = mix(col, hot, uSport);",
    "  col = mix(vec3(0.16, 0.20, 0.21), col, uLive);",
    "",
    "  float R = 0.74, W = 0.030;",
    "  float ring = band(r - R, W, 0.010);",
    "  float inSweep = step(0.0, t) * step(t, 1.0);",
    "",
    "  // Ambient: the whole arc breathes at low intensity, always.",
    "  float amb = ring * inSweep * 0.22;",
    "",
    "  // Speed: the bright leading arc.",
    "  float prog = step(t, clamp(uSpeed, 0.0, 1.0)) * inSweep;",
    "  float lead = ring * prog;",
    "",
    "  // Tick marks, brighter where the arc has reached.",
    "  float ticks = 0.0;",
    "  float td = fract(t * 24.0);",
    "  float major = step(0.94, fract(t * 4.8));",
    "  float tw = 0.0035 + major * 0.0030;",
    "  float tr = band(r - (R - 0.075), 0.028 + major * 0.014, 0.006);",
    "  ticks = tr * band(min(td, 1.0 - td) / 24.0, tw, 0.0016) * inSweep;",
    "  ticks *= mix(0.10, 0.75, prog);",
    "",
    "  // Tacho: a slim inner arc.",
    "  float rr = band(r - (R - 0.135), 0.011, 0.007);",
    "  float rprog = step(t, clamp(uRpm, 0.0, 1.0)) * inSweep;",
    "  float tach = rr * rprog * 0.55;",
    "",
    "  // Outward bloom from the lit arc.",
    "  float glow = exp(-abs(r - R) * 9.0) * (0.16 + 0.44 * prog) * inSweep;",
    "",
    "  float i = amb + lead + ticks + tach + glow;",
    "  vec3 rgb = col * i;",
    "  // A touch of core whitening so the lit arc reads as emissive.",
    "  rgb += vec3(1.0) * lead * 0.16 * uLive;",
    "  gl_FragColor = vec4(rgb, clamp(i * 1.6, 0.0, 1.0));",
    "}"
  ].join("\n");

export function makeRing(canvas) {
  const gl = canvas.getContext("webgl", { antialias: true, alpha: true });
  if (!gl) return null;
  const compile = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(s));
      return null;
    }
    return s;
  };
  const v = compile(gl.VERTEX_SHADER, VERT), f = compile(gl.FRAGMENT_SHADER, FRAG);
  if (!v || !f) return null;
  const prog = gl.createProgram();
  gl.attachShader(prog, v); gl.attachShader(prog, f); gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.error(gl.getProgramInfoLog(prog));
    return null;
  }
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER,
    new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "p");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

  const U = {};
  const uni = (name) => {
    if (!(name in U)) U[name] = gl.getUniformLocation(prog, name);
    return U[name];
  };

  return function draw({ eff, speed, rpm, sport, live, maxSpeed, maxRpm }) {
    const w = Math.round((canvas.clientWidth || 400) * (window.devicePixelRatio || 1));
    if (canvas.width !== w) { canvas.width = canvas.height = w; }
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform1f(uni("uEff"), eff);
    gl.uniform1f(uni("uSpeed"), Math.min(1, speed / maxSpeed));
    gl.uniform1f(uni("uRpm"), Math.min(1, rpm / maxRpm));
    gl.uniform1f(uni("uSport"), sport ? 1 : 0);
    gl.uniform1f(uni("uLive"), live ? 1 : 0);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  };
}
