// The tablet's camera, and an honest fallback when it cannot be used.
//
// `getUserMedia` requires a secure context. `http://127.0.0.1` counts as one —
// browsers treat loopback as secure — so this works in the kiosk and on the
// machine running OmaCar. A cockpit display reached over the LAN at
// `http://192.168.x.x` does NOT, and no browser will let it near a camera.
//
// That is a browser rule and not ours to argue with, so rather than showing a
// button that cannot work, the picker falls back to a file input — which on
// a phone or tablet still opens the camera app, and on a laptop lets somebody
// attach a photograph they already took.

import { h, clear, api, toast } from "./core.js";

export const canUseCamera = () =>
  window.isSecureContext && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

// Photographs go into the record, and a record is read on a phone as often as
// on a workshop screen. Full sensor resolution is several megabytes of detail
// nobody looks at, so they are scaled to something a person can actually see
// a perished hose in and no larger.
const MAX_EDGE = 1600;
const QUALITY = 0.82;

function shrink(source, w, h) {
  const scale = Math.min(1, MAX_EDGE / Math.max(w, h));
  const c = document.createElement("canvas");
  c.width = Math.round(w * scale);
  c.height = Math.round(h * scale);
  c.getContext("2d").drawImage(source, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", QUALITY);
}

async function fromFile(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((res, rej) => {
      const i = new Image();
      i.onload = () => res(i);
      i.onerror = rej;
      i.src = url;
    });
    return shrink(img, img.naturalWidth, img.naturalHeight);
  } finally {
    URL.revokeObjectURL(url);
  }
}

// A modal that shows the camera, takes one frame, and files it against
// whatever you were looking at when you opened it.
export function capturePhoto({ subject = "general", subjectId = "", onDone }) {
  const host = document.getElementById("modal-host");
  let stream = null;

  const close = () => {
    if (stream) for (const t of stream.getTracks()) t.stop();
    host.hidden = true;
    clear(host);
  };

  const note = h("input", { type: "text",
    placeholder: "What am I looking at? e.g. weeping at the flange" });
  const preview = h("div", { style: { display: "grid", gap: "10px" } });
  const box = h("div.modal", { role: "dialog", "aria-modal": "true" },
    h("div.title", "Photograph"),
    h("p.muted", subjectId ? `Filed against ${subject} ${subjectId}` : "Filed against this car"),
    preview, note);

  const file = h("input", { type: "file", accept: "image/*",
    capture: "environment", style: { display: "none" } });
  box.appendChild(file);

  async function send(dataUrl) {
    try {
      const p = await api.photo({
        image: dataUrl, subject, subject_id: subjectId, note: note.value.trim(),
      });
      toast("Photograph filed.");
      close();
      if (onDone) onDone(p);
    } catch (e) { toast(String(e.message || e), "bad"); }
  }

  file.addEventListener("change", async () => {
    if (!file.files || !file.files[0]) return;
    try { await send(await fromFile(file.files[0])); }
    catch { toast("Could not read that image.", "bad"); }
  });

  if (canUseCamera()) {
    const video = h("video", { autoplay: "", playsinline: "", muted: "",
      style: { width: "100%", borderRadius: "10px", background: "#000" } });
    preview.appendChild(video);
    const shoot = h("button.btn.primary", { onclick: () => {
      if (!video.videoWidth) { toast("The camera is not ready yet."); return; }
      send(shrink(video, video.videoWidth, video.videoHeight));
    } }, "Take it");
    box.appendChild(h("div.row", { style: { justifyContent: "flex-end" } },
      h("button.btn", { onclick: close }, "Cancel"),
      h("button.btn", { onclick: () => file.click() }, "Choose a file"),
      shoot));

    // The rear camera, because you are pointing it at an engine.
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" },
               width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    }).then((s) => { stream = s; video.srcObject = s; })
      .catch(() => {
        clear(preview);
        preview.appendChild(h("p.lede",
          "The camera would not open — it may be in use, or permission was "
          + "declined. You can still attach a picture."));
      });
  } else {
    preview.appendChild(h("p.lede",
      window.isSecureContext
        ? "This browser has no camera available."
        : "The camera needs a secure context, and this page was opened over "
          + "the network rather than on the machine itself — every browser "
          + "refuses camera access there. Attach a photograph instead; on a "
          + "phone or tablet that still opens the camera."));
    box.appendChild(h("div.row", { style: { justifyContent: "flex-end" } },
      h("button.btn", { onclick: close }, "Cancel"),
      h("button.btn.primary", { onclick: () => file.click() }, "Choose a photograph")));
  }

  clear(host);
  host.appendChild(box);
  host.hidden = false;
  host.onclick = (e) => { if (e.target === host) close(); };
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { document.removeEventListener("keydown", esc); close(); }
  });
}

// A strip of what has already been filed against something, with a button to
// add another. Dropped into any view that has a subject.
export function photoStrip({ subject, subjectId, title = "Photographs" }) {
  const strip = h("div.photos");
  const box = h("div.card",
    h("div.row",
      h("div.eyebrow", title),
      h("button.btn.sm.right", {
        onclick: () => capturePhoto({ subject, subjectId, onDone: load }),
      }, canUseCamera() ? "Photograph" : "Attach a photograph")),
    h("div", { style: { marginTop: "10px" } }, strip));

  async function load() {
    try {
      const { photos } = await api.photos({ subject, id: subjectId });
      clear(strip);
      if (!photos.length) {
        strip.appendChild(h("p.muted",
          "Nothing yet. A perished hose is not on the bus and a photograph of "
          + "it is half the diagnosis."));
        return;
      }
      for (const p of photos) strip.appendChild(thumb(p, load));
    } catch { clear(strip); }
  }
  load();
  return box;
}

export function thumb(p, onChange) {
  return h("figure.photo", { title: p.note || "" },
    h("img", { src: p.url, alt: p.note || "photograph", loading: "lazy",
      onclick: () => window.open(p.url, "_blank", "noopener,noreferrer") }),
    h("figcaption",
      h("span", p.note || new Date(p.at * 1000).toLocaleString()),
      h("button", { title: "remove", onclick: async () => {
        try {
          await api.photo({ action: "remove", id: p.id });
          toast("Removed.");
          if (onChange) onChange();
        } catch (e) { toast(String(e.message || e), "bad"); }
      } }, "×")));
}
