// Omarchy Radio, in the dashboard.
//
// A native <audio> element rather than an iframe of radio.omarchy.org. The site
// has no X-Frame-Options so framing it would work, but an iframe would bring
// its layout into a screen designed for a moving car -- small controls, its own
// scroll, and a third-party page that can change shape without warning. The
// stream sends Access-Control-Allow-Origin: *, so we can play it directly and
// draw controls at the size a driver can actually hit.
//
// Nothing here autoplays. Browsers block it, and a dashboard that starts
// playing music the moment you plug in your car would deserve to be blocked
// anyway.

import { h } from "./core.js";

const STREAM = "https://radio.cliamp.stream/omarchy/stream";
const STATS = "https://radio.cliamp.stream/statistics";
const STATION = "omarchy";
const VOL_KEY = "omacar.radio.volume";

let audio = null;
let listeners = new Set();
let now = { title: "", artist: "", listeners: null };
let metaTimer = null;
let statsTimer = null;

function emit() { for (const fn of listeners) fn(); }

// ---------------------------------------------------------------- now playing
//
// The track name only exists inside the audio stream. Icecast interleaves it:
// every `icy-metaint` bytes of audio comes a length byte, then that many bytes
// of "StreamTitle='Artist - Title';". There is no separate endpoint -- the
// station's /statistics gives listener counts and nothing about the track, and
// the playlist manifest lists every track but not which one is playing.
//
// SAMPLE AND DISCONNECT, RATHER THAN LISTEN TWICE.
//
// Reading metadata means opening the stream a SECOND time, alongside the one
// the <audio> element is playing. Held open, that doubles the bandwidth --
// 128 kbps becomes 256, about 114 MB an hour, which is real money on a phone
// hotspot in a car.
//
// But the first metadata block arrives after only 8192 bytes, half a second of
// audio. So this connects, reads to the first block, and aborts: roughly 8.5 KB
// per sample. At one sample every 20 seconds that is ~0.4 KB/s instead of
// 16 KB/s, for information that only changes every few minutes.
async function sampleMetadata(signal) {
  const res = await fetch(STREAM, {
    headers: { "Icy-MetaData": "1" },
    signal,
    cache: "no-store",
  });
  const interval = parseInt(res.headers.get("icy-metaint") || "0", 10);
  if (!interval || !res.body) { res.body?.cancel?.(); return null; }

  const reader = res.body.getReader();
  let skipped = 0;
  let pending = new Uint8Array(0);

  const concat = (a, b) => {
    const out = new Uint8Array(a.length + b.length);
    out.set(a); out.set(b, a.length);
    return out;
  };

  try {
    // Walk past exactly `interval` bytes of audio, then the length byte, then
    // the metadata itself. Chunks do not align to any of those boundaries, so
    // everything is buffered rather than assumed.
    while (skipped < interval) {
      const { value, done } = await reader.read();
      if (done) return null;
      skipped += value.length;
      if (skipped > interval) pending = value.slice(value.length - (skipped - interval));
    }
    while (pending.length < 1) {
      const { value, done } = await reader.read();
      if (done) return null;
      pending = concat(pending, value);
    }
    const len = pending[0] * 16;
    pending = pending.slice(1);
    if (len === 0) return "";                 // no change since the last block
    while (pending.length < len) {
      const { value, done } = await reader.read();
      if (done) return null;
      pending = concat(pending, value);
    }
    const text = new TextDecoder("utf-8", { fatal: false })
      .decode(pending.slice(0, len));
    const m = /StreamTitle='([^']*)'/.exec(text);
    return m ? m[1].trim() : "";
  } finally {
    try { await reader.cancel(); } catch { /* already gone */ }
  }
}

function splitTitle(raw) {
  // Icecast convention is "Artist - Title", but plenty of stations send only a
  // title. Splitting on the FIRST " - " keeps hyphenated track names intact.
  if (!raw) return { artist: "", title: "" };
  const i = raw.indexOf(" - ");
  return i > 0
    ? { artist: raw.slice(0, i).trim(), title: raw.slice(i + 3).trim() }
    : { artist: "", title: raw.trim() };
}

async function refreshNowPlaying() {
  const ctl = new AbortController();
  // A sample that hangs must not stack up behind the next one.
  const bail = setTimeout(() => ctl.abort(), 8000);
  try {
    const raw = await sampleMetadata(ctl.signal);
    if (raw === null) return;
    if (raw === "") return;                   // empty block: keep what we have
    const { artist, title } = splitTitle(raw);
    if (title !== now.title || artist !== now.artist) {
      now = { ...now, artist, title };
      emit();
      // Lock-screen and media-key integration, free if the browser has it.
      if ("mediaSession" in navigator && window.MediaMetadata) {
        try {
          navigator.mediaSession.metadata = new window.MediaMetadata({
            title: title || "Omarchy Radio",
            artist: artist || "Omarchy",
            album: "Omarchy Radio",
          });
        } catch { /* best effort */ }
      }
    }
  } catch { /* offline, aborted, or CORS -- the player still works */ }
  finally { clearTimeout(bail); }
}

async function refreshStats() {
  try {
    const res = await fetch(STATS, { cache: "no-store" });
    const d = await res.json();
    const n = d?.stations?.[STATION]?.active_listeners;
    if (typeof n === "number" && n !== now.listeners) {
      now = { ...now, listeners: n };
      emit();
    }
  } catch { /* not important enough to report */ }
}

function startPolling() {
  if (metaTimer) return;
  refreshNowPlaying();
  refreshStats();
  metaTimer = setInterval(refreshNowPlaying, 20000);
  statsTimer = setInterval(refreshStats, 60000);
}

function stopPolling() {
  // Nothing is sampled while paused. Polling a stream nobody is listening to
  // is pure waste, and this runs in a car.
  clearInterval(metaTimer); clearInterval(statsTimer);
  metaTimer = statsTimer = null;
}

function el() {
  if (audio) return audio;
  audio = new Audio();
  audio.preload = "none";          // no connection until asked
  audio.crossOrigin = "anonymous";
  audio.src = STREAM;
  let v = 0.8;
  try {
    const saved = parseFloat(localStorage.getItem(VOL_KEY));
    if (!Number.isNaN(saved)) v = Math.min(1, Math.max(0, saved));
  } catch { /* private mode */ }
  audio.volume = v;
  for (const e of ["playing", "pause", "waiting", "error", "stalled"]) {
    audio.addEventListener(e, emit);
  }
  return audio;
}

export const radio = {
  get playing() { return !!audio && !audio.paused; },
  get now() { return now; },
  get loading() { return !!audio && !audio.paused && audio.readyState < 3; },
  get failed() { return !!audio && !!audio.error; },
  get volume() { return audio ? audio.volume : 0.8; },
  set volume(v) {
    const a = el();
    a.volume = Math.min(1, Math.max(0, v));
    try { localStorage.setItem(VOL_KEY, String(a.volume)); } catch { /* ignore */ }
    emit();
  },
  async toggle() {
    const a = el();
    if (a.paused) {
      // A live stream that has been paused is stale; reloading rejoins at the
      // live edge instead of resuming minutes behind.
      if (a.currentTime > 0) a.load();
      try { await a.play(); } catch { /* autoplay policy or offline */ }
      startPolling();
    } else {
      a.pause();
      stopPolling();
    }
    emit();
  },
  stop() { if (audio) { audio.pause(); audio.load(); stopPolling(); emit(); } },
  on(fn) { listeners.add(fn); return () => listeners.delete(fn); },
};

// The player, sized for the car: a 64px transport button and a slider with a
// tall touch area, because a thin range input is unusable on a moving vehicle.
export function radioPlayer() {
  const status = radio.failed ? "offline"
    : radio.loading ? "connecting…"
    : radio.playing ? "live" : "paused";

  const btn = h("button.radio-play", {
    onclick: () => radio.toggle(),
    "aria-label": radio.playing ? "Pause radio" : "Play radio",
  }, radio.playing ? "❚❚" : "▶");

  const vol = h("input.radio-vol", {
    type: "range", min: "0", max: "100",
    value: String(Math.round(radio.volume * 100)),
    "aria-label": "Radio volume",
    oninput: (e) => { radio.volume = Number(e.target.value) / 100; },
  });

  const np = radio.now;
  const line2 = np.artist ? np.artist : status;

  return h("div.radio",
    btn,
    h("div.radio-meta",
      // The track when we have one, the station when we do not. A player that
      // shows "Omarchy Radio" while a named track is playing is wasting the
      // only line that tells you what you are hearing.
      h("div.radio-name", np.title || "Omarchy Radio"),
      h("div.radio-status" + (radio.failed ? ".bad" : ""),
        line2,
        np.listeners != null
          ? h("span.radio-count", `${np.listeners} listening`)
          : null)),
    vol);
}
