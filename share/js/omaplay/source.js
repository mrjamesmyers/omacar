// OmaPlay — where the phone's screen comes from.
//
// WHAT OMAPLAY IS, AND WHAT IT IS NOT.
//
// It is a HOST for CarPlay and Android Auto, not a reimplementation of either.
// The phone renders those screens itself and hands over H.264 video; nobody
// gets to restyle Apple Maps, and any project claiming otherwise is confused
// about where the pixels come from. What we own is everything around and on
// top of that rectangle — the chrome, the layout, the now-playing panel, and
// the engine data overlaid on it, which is the one thing no head unit on the
// market can do.
//
// (And it is never called CarPlay or Android Auto in the interface. Those are
// Apple's and Google's marks and this repository is public.)
//
// WHY THERE IS A SOURCE ABSTRACTION AT ALL.
//
// Because the hardware is not here yet, and because waiting for it would mean
// designing the whole interface blind and then discovering the layout is wrong
// on the day the dongle arrives. A source is anything that emits the message
// shapes below and can paint into a canvas. The mock emits them from a script;
// the real one will emit them from a Carlinkit dongle over WebUSB. The layer
// above cannot tell the difference, which is the entire point.
//
// THE MESSAGE SHAPES ARE NOT INVENTED.
//
// They are transcribed from node-carplay's own source (MIT), src/web/
// CarplayWeb.ts and src/modules/messages/readable.ts, so that swapping the
// mock for the real driver is a substitution and not a rewrite:
//
//   { type: 'plugged' } | { type: 'unplugged' } | { type: 'failure' }
//   { type: 'video',   message: { width, height, flags, length, data } }
//   { type: 'audio',   message: AudioData }
//   { type: 'media',   message: { payload } }
//   { type: 'command', message: Command }
//
// and MediaData's payload is one of:
//
//   { type: 1, media: { MediaSongName, MediaAlbumName, MediaArtistName,
//                       MediaAPPName, MediaSongDuration, MediaSongPlayTime } }
//   { type: 3, base64Image }        // album art
//
// Those exact key names, capitals and all, are the wire format. They are ugly
// and they are not ours to tidy.

export const MEDIA_DATA = 1;
export const MEDIA_ALBUM_COVER = 3;

// The Carlinkit dongles node-carplay knows about, from DongleDriver.knownDevices.
// Here so the real source and the "is it plugged in" check agree.
export const KNOWN_DEVICES = [
  { vendorId: 0x1314, productId: 0x1520 },
  { vendorId: 0x1314, productId: 0x1521 },
];

// What the phone is asked to render into. node-carplay's DEFAULT_CONFIG is
// 800x640 at 20fps, which is a guess about somebody else's screen; the real
// source will override width/height/dpi from the element it is drawing into,
// because the phone renders to whatever shape it is told and there is no
// reason to letterbox our own panel.
export const DEFAULT_CONFIG = {
  width: 800, height: 640, fps: 20, dpi: 160,
  nightMode: false, boxName: "OmaPlay", mediaDelay: 300,
};

function bus() {
  const fns = new Set();
  return {
    on(fn) { fns.add(fn); return () => fns.delete(fn); },
    emit(msg) { for (const fn of [...fns]) { try { fn(msg); } catch { /* one bad listener must not stop the rest */ } } },
    clear() { fns.clear(); },
  };
}

// ---------------------------------------------------------------- the mock
//
// It does NOT pretend to be a phone. It cannot: producing convincing H.264 of
// a CarPlay screen would mean shipping a fake of somebody else's interface,
// which is both a trademark problem and exactly the invented-content this
// project forbids. So the mock paints something obviously synthetic and says
// MOCK across it, for the same reason demo mode wears an amber badge — the one
// unforgivable failure is somebody believing a fake is the real thing.
//
// What it IS faithful about is the message TIMING and SHAPES: a plug event
// after a delay, media metadata that changes track, a play position that
// advances, album art as base64. That is what the layout has to cope with, and
// that is what can be got right before the hardware exists.

const TRACKS = [
  { MediaSongName: "Mock Track One", MediaArtistName: "The Placeholders",
    MediaAlbumName: "Nothing Is Playing", MediaAPPName: "OmaPlay Mock",
    MediaSongDuration: 214 },
  { MediaSongName: "A Second Mock Track", MediaArtistName: "Test Signal",
    MediaAlbumName: "Nothing Is Playing", MediaAPPName: "OmaPlay Mock",
    MediaSongDuration: 178 },
  { MediaSongName: "Something With A Very Long Title That Has To Elide Somewhere",
    MediaArtistName: "An Artist With A Long Name Too", MediaAlbumName: "Edge Cases",
    MediaAPPName: "OmaPlay Mock", MediaSongDuration: 305 },
];

export function mockSource(opts = {}) {
  const b = bus();
  let raf = 0;
  let timer = 0;
  let canvas = null;
  let ctx = null;
  let t0 = 0;
  let track = 0;
  let elapsed = 0;
  let running = false;

  function pushTrack() {
    const media = { ...TRACKS[track % TRACKS.length], MediaSongPlayTime: Math.floor(elapsed) };
    b.emit({ type: "media", message: { payload: { type: MEDIA_DATA, media } } });
  }

  function paint() {
    if (!running) return;
    raf = requestAnimationFrame(paint);
    if (!ctx || !canvas.width) return;
    const w = canvas.width, h = canvas.height;
    const t = (performance.now() - t0) / 1000;

    // Deliberately not a phone screen. Moving bars so dropped frames and
    // stretched aspect ratios are visible at a glance, which is what this is
    // for while the layout is being built.
    const g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, "#101820");
    g.addColorStop(1, "#1a2630");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    const bars = 12;
    for (let i = 0; i < bars; i++) {
      const p = (i / bars + t * 0.08) % 1;
      ctx.fillStyle = `hsl(${200 + i * 6} 45% ${18 + 10 * Math.sin(t + i)}%)`;
      ctx.fillRect(p * w, 0, w / bars / 2, h);
    }
    // A moving box gives the eye something to judge smoothness by.
    const bx = (w - 90) * (0.5 + 0.5 * Math.sin(t * 0.9));
    const by = (h - 90) * (0.5 + 0.5 * Math.cos(t * 0.7));
    ctx.fillStyle = "#3d5a6c";
    ctx.fillRect(bx, by, 90, 90);

    ctx.fillStyle = "rgba(255,255,255,.82)";
    ctx.font = `600 ${Math.max(16, Math.round(w / 22))}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText("MOCK PHONE SCREEN", w / 2, h / 2 - 6);
    ctx.font = `400 ${Math.max(11, Math.round(w / 46))}px system-ui, sans-serif`;
    ctx.fillStyle = "rgba(255,255,255,.55)";
    ctx.fillText(`${w}×${h}  ·  no dongle connected`, w / 2, h / 2 + Math.round(w / 32));
  }

  return {
    kind: "mock",
    get running() { return running; },
    on: b.on,

    start(el) {
      if (running) return;
      canvas = el;
      ctx = canvas.getContext("2d");
      running = true;
      t0 = performance.now();
      // A real dongle takes a few seconds to hand the phone over. Emitting
      // `plugged` immediately would let a "connecting" state ship untested.
      setTimeout(() => { if (running) b.emit({ type: "plugged" }); },
                 opts.plugDelay ?? 1200);
      timer = setInterval(() => {
        if (!running) return;
        elapsed += 1;
        const dur = TRACKS[track % TRACKS.length].MediaSongDuration;
        if (elapsed >= dur) { elapsed = 0; track += 1; }
        pushTrack();
      }, 1000);
      raf = requestAnimationFrame(paint);
    },

    stop() {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      if (timer) clearInterval(timer);
      raf = timer = 0;
      b.emit({ type: "unplugged" });
    },

    // The real driver takes touch and key commands back over USB. The mock
    // accepts and ignores them, so the input plumbing above can be written
    // and exercised now rather than after the hardware lands.
    send() { return false; },
  };
}

// ------------------------------------------------------------- the real one
//
// Deliberately a stub that REFUSES rather than a half-implementation that
// silently does nothing. It needs the node-carplay driver vendored and a
// Carlinkit CPC200-CCPA or CPC200-Autokit on the other end, plus a udev rule
// granting WebUSB access to vendor 0x1314. Until all three exist this must be
// unmistakably unavailable, because a source that quietly produces no frames
// looks exactly like a bug in the layer above it.

export function usbSource() {
  return {
    kind: "usb",
    running: false,
    on() { return () => {}; },
    start() {
      throw new Error(
        "OmaPlay's USB source is not wired up yet. It needs the node-carplay "
        + "driver vendored, a Carlinkit dongle, and a udev rule for vendor "
        + "0x1314. Use the mock source until then.");
    },
    stop() {},
    send() { return false; },
  };
}

export async function usbAvailable() {
  if (!navigator.usb) return false;
  try {
    const devices = await navigator.usb.getDevices();
    return devices.some((d) => KNOWN_DEVICES.some(
      (k) => k.vendorId === d.vendorId && k.productId === d.productId));
  } catch {
    return false;
  }
}
