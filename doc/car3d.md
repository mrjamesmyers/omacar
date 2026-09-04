# The 3D car

## The short answer

**No photorealistic 2015 Honda CR-Z model ships with this change, and none can.**
Not because the viewer is unfinished — the viewer is done and works — but because
a photorealistic model of a specific trademarked car is a *thing you acquire*,
not a thing you write. There is no arrangement of code in this repository that
turns into a car Honda would recognise as theirs.

What ships is the other half: a three.js viewer that a real model drops into,
and an honest fallback that shows the same flat car the Qt panel already draws
when no model is present. `share/js/car3d.js` contains **zero car geometry**.
That is deliberate. A box-and-cylinder car written out of primitives is exactly
the "cheap looking" outcome that was rejected, and shipping one while calling it
photorealistic would be the fake content this project has repeatedly forbidden.

**The recommendation is photogrammetry of the actual car.** You own a 2015 CR-Z.
A hundred and fifty phone photographs on an overcast afternoon produce a model of
*your* car — your gunmetal paint, your wheels, your plate — with no marketplace
licence, no trademark question about somebody else's mesh, and a far better
answer to "completely real" than any generic asset. The full procedure is in
[Route C](#route-c--photogrammetry-of-your-own-car-recommended).

---

## What was checked, and how confidently

Marketplaces block automated fetching (TurboSquid, CGTrader and Free3D all
returned HTTP 403 to a direct fetch), so this document separates two things:

- **Verified** — the page was actually retrieved and read.
- **Reported** — the figure came from a search index summarising the page, and
  was *not* confirmed against the listing. Treat every reported price as a
  starting point to check yourself, not as a quote.

Nothing here is invented. Where a number could not be confirmed it says so.

---

## Route A — buy a model from a marketplace

### What exists

| Listing | Verified? | Notes |
|---|---|---|
| [Honda CR-Z EX 2015 — CGTrader](https://www.cgtrader.com/3d-models/car/sport-car/honda-cr-z-ex-2015) | Reported | The only listing found that names **2015** specifically. ~650k polygons; formats reported as 3ds Max/V-Ray, FBX, OBJ, DWG — **no glTF/GLB**. The search index reported the listing as *not currently available for purchase*. Price unknown. |
| [Honda CR-Z models — TurboSquid](https://www.turbosquid.com/3d-model/honda/cr-z) | Reported | Several listings; prices reported in the range **$33–$119** (individual figures reported: $33, $57.14, $69, $79, $119). Years given as 2011 / 2014 where stated. Page returns 403 to automated fetch — check prices and the licence badge on each listing yourself. |
| [Honda CR-Z (ZF1) 2013 — 3dmodels.org](https://3dmodels.org/3d-models/honda-cr-z/) | Reported | Reported at **$94–$95** and reported to offer **GLB / glTF 2.0** — the only paid listing found that reports a native glTF export. 403 to automated fetch. |
| [Honda CR-Z — 3DCADBrowser](https://www.3dcadbrowser.com/3d-model/honda-cr-z) | Not checked | Subscription-model site; listed for completeness. |

### The year problem, which is not pedantry

Almost every CR-Z model on the market is the **2011 ZF1**, and your car is a 2015.
Honda facelifted the CR-Z for the **2013** model year: a new front bumper, revised
grille, a new rear diffuser, new wheels on the upper trims, and LED daytime
running lights ([Honda's own 2013 release](https://hondanews.com/en-US/releases/release-e84471d091354cebbb325a69ed68ec05-2013-honda-cr-z-sport-hybrid-coupe-gets-performance-enhancements-fresh-styling-and-host-of-feature-upgrades)).
There was a further minor refresh for 2016. The body shell is unchanged
throughout, so a 2011 model is *close* — but the face is not your car's face, and
the face is the part you look at. A model sold as "Honda CR-Z" with no year, or
dated 2011, will read as wrong to you specifically, every time you open the app.

### The licence problem, which is the actual blocker

**This project is open source and public on GitHub. That single fact rules out
committing any purchased model.** It is not a grey area:

> "re-distribute, publish, or make 3D Models available to any third party except
> in the form of a permitted Creation" — prohibited. Models incorporated into a
> product must "not [be] in an open format which would allow others access to the
> underlying 3D Model's data."
> — [TurboSquid 3D Model License](https://blog.turbosquid.com/turbosquid-3d-model-license/)

A `.glb` sitting in a public repository is the textbook case of both: it is
redistribution, and a GLB is an open format from which anyone can extract the
mesh. CGTrader's Royalty Free licence carries an equivalent restriction (its help
article also 403s to automated fetch — read it before buying).

Second, and separately: many vehicle listings carry **"Editorial Uses Only"**,
which TurboSquid describes as covering products that depict "another party's
intellectual property … a real-world manufacturer's logo, trademark, or other
protected IP such as ornamental designs in the geometry." Under that label the
model "may not be used on any item/product for re-sale, such as a video game",
and — importantly — "may not be modified so that it no longer contains Depicted
Intellectual Property", so filing the badges off is not an escape hatch
([TurboSquid Associated Brands Information](https://support.turbosquid.com/hc/en-us/articles/230097087-Associated-Brands-Information),
[Editorial licence announcement](https://blog.turbosquid.com/2010/04/08/turbosquid-editorial-license/)).

**Where that leaves buying:** perfectly viable for a model that lives only on your
own laptop, and unusable for anything committed to the repo. Which is why the
viewer is built to load the car from `share/models/`, a directory that should be
in `.gitignore` and is not part of the distribution — see
[Installing a model](#installing-a-model-once-you-have-one).

---

## Route B — free and Creative Commons sources

### What genuinely exists

These four were checked directly on Sketchfab and the figures below are verified:

| Model | Author | Licence | Size |
|---|---|---|---|
| [Honda CR-Z](https://sketchfab.com/3d-models/honda-cr-z-758396c4fdc746488b2cae0e85104d96) | Racing Carz U3D | **CC BY 4.0** | 11.9k triangles, 7.3k verts |
| [2011 Honda CR-Z](https://sketchfab.com/3d-models/2011-honda-cr-z-f0c58b5b2dcc4c9dad39fe8ebe65a02c) | Ddiaz Design | **CC BY-NC-SA** | 38k triangles, 22.7k verts |
| [2012 Honda CR-Z ZF2](https://sketchfab.com/3d-models/2012-honda-cr-z-zf2-1f2c19a623db47d1863c7992acdfaccb) | SIU Car Garage | **CC BY-NC** | 10.8k triangles, 7.1k verts |
| [Honda CR-Z 2011](https://sketchfab.com/3d-models/honda-cr-z-2011-d5af69ef34834f43a65b4aac78ca8929) | Nieve5677 | not checked | — |

Also found: [Viz-People's free Honda CR-Z](https://www.viz-people.com/portfolio/free-3d-model-honda-cr-z/),
whose page states "free for commercial use". It is prepared for 3ds Max and
V-Ray, so it would need converting, and I could not retrieve their full terms
page (404) to check whether *redistribution* is permitted separately from *use* —
those are different permissions and free-asset sites routinely grant the second
and withhold the first.

### Why "free CR-Z model" is a red flag, not a result

Three separate problems, any one of which is disqualifying for a public repo:

1. **10k–38k triangles is a game LOD, not a photorealistic model.** For scale, the
   one 2015-specific commercial listing reports 650k polygons. A 11.9k-triangle
   car has no panel gaps, no door shut lines, and a roofline that is visibly
   faceted at any size worth showing. Lit beautifully, it still looks like what it
   is. This is the "cheap looking" failure arriving by a different road.

2. **Non-commercial licences are non-starters here.** CC BY-NC and CC BY-NC-SA
   cover two of the four above. Even setting the NC question aside, the ShareAlike
   term on the second one would attempt to reach into anything derived from it.

3. **A Creative Commons licence cannot grant what the uploader does not own.**
   This is the important one and it is explicit in the licence text: "Patent and
   trademark rights are not licensed under this Public License"
   ([CC BY 4.0 legal code, §2(b)(2)](https://creativecommons.org/licenses/by/4.0/legalcode.en)),
   and Creative Commons state plainly that their licences "do not license rights
   other than copyright … they do not license trademark or patent rights"
   ([CC FAQ](https://creativecommons.org/faq/)). The Honda wordmark, the H badge
   and arguably the CR-Z's trade dress are Honda's. A hobbyist stamping CC BY on a
   Honda-shaped mesh is licensing their *copyright in the mesh they made* — which
   they may or may not actually hold, since a great many "free" car models on
   sharing sites are extracted from games — and is licensing nothing at all about
   the badge on the bonnet. CC material is offered "AS IS" with no warranty that
   the uploader had the rights they claim, so the risk stays with whoever ships it.

**Conclusion for Route B: do not use a free CR-Z model in this repository.** One
of them is fine to download and look at on your own machine. None of them belongs
in a public git history, and none of them is photorealistic anyway.

---

## Route C — photogrammetry of your own car (recommended)

This is the recommendation, and it is not a consolation prize. It is the only
route that produces a model of **your** car — the right model year, the right
wheels, the right gunmetal paint under the right sky, the stone chip on the
bonnet — rather than a generic CR-Z that is nearly your car. "Completely real"
is exactly what photogrammetry means.

It also disposes of the entire licence chapter above. You photographed your own
property; you authored the photographs and the mesh derived from them. There is
no marketplace licence, no ShareAlike, no editorial restriction. (The Honda badge
in the geometry is still Honda's trademark — see [the trademark note](#a-note-on-trademarks)
— but that is a far smaller and more manageable question than redistributing
somebody else's asset.)

### Cost

**£0 in software** on the free routes below, plus an afternoon. Optional and
genuinely useful: a circular polarising filter if you shoot with a real camera
(roughly £20–£40 for a decent one; unnecessary on a phone), and a step ladder you
probably already own.

### The one hard problem: your paint is a mirror

Photogrammetry works by finding the same physical point in three or more
photographs. Glossy automotive clearcoat does not have physical points — it has
reflections, and a reflection *moves when you move*, which is precisely the
signal the solver is trying to use. This is the entire difficulty and everything
below is a way of managing it.

The standard mitigations, in order of how much they help:

- **Shoot on a fully overcast day.** Cloud is the best diffuser that exists and
  it is free. This matters more than the camera, the software, or the number of
  photos. Bright sun produces hard specular highlights that shift across every
  frame and the reconstruction will fail on the panels.
  ([Sketchfab: lighting in photogrammetry](https://sketchfab.com/blogs/community/lighting-in-photogrammetry/),
  [Sketchfab: capturing reflective objects](https://sketchfab.com/blogs/community/capturing-reflective-objects-in-3d/))
- **Move the car into the open.** Away from walls, hedges, and other cars — those
  are what the paint will be reflecting, and a flank reflecting a hedge in one
  frame and a fence in the next is a flank with no matchable features.
- **Give the solver something to hold on to.** Scatter high-contrast objects on
  the ground around the car — sheets of newspaper, gaffer tape crosses, anything
  visually busy. A featureless grey flank is the worst case for the solver, and
  a well-textured ground plane in the same frames rescues the camera alignment
  even where the panel itself contributes nothing.
- **A circular polariser** on the lens cuts sky glare off the panels. It is a
  partial fix outdoors: full cross-polarisation needs a polarised light source as
  well, which is a studio technique, and it costs several stops of light.
- **Do not use matte spray on your own car.** It is the textbook fix and it is a
  textbook fix for props, not for a car you drive.

Expect **glass and chrome to fail regardless.** Windows, headlight lenses and the
badge will come back as holes or noise. That is normal and it is patched in
Blender afterwards.

### The capture

1. **Clean and dry the car.** Water beads are moving specular highlights.
2. **Overcast, flat light, no direct sun.** Reshoot rather than compromise on this.
3. **Put a metre rule or a tape measure on the ground in shot** so the model can
   be scaled to reality later.
4. **Walk three complete orbits**, at three heights:
   - knee height (sills, arches, lower bumpers)
   - chest height (the main body, waistline, glass)
   - above the roof — a step ladder, or arms overhead with the phone tilted down
     (roof, bonnet, boot lid, which are otherwise entirely missing)
5. **Step, do not sweep.** Take a photo, take two paces, take another. Aim for
   **60–80% overlap** between consecutive frames: every point on the car must
   appear in at least three photographs, which is what that overlap buys
   ([why 3+ views / ~2/3 overlap](https://peterfalkingham.com/2019/01/16/small-object-photogrammetry-how-to-take-photos/)).
6. **150–250 photographs** for the orbits. More than about 300 stops improving
   the mesh ([OpenScan's measurements](https://openscan.eu/blogs/news/optimizing-3d-scans-how-many-photos-do-you-really-need)),
   and coverage matters far more than the count.
7. **A detail pass**: closer frames of the wheels, mirrors, lights, grille, the
   badge, and the tail. These are where the eye goes.
8. **Do not move the car**, and do not change lens, exposure mode or aspect ratio
   part-way through. Lock focus and exposure if the phone will let you.

### The software

| Tool | Licence / cost | Platform | Honest note |
|---|---|---|---|
| **[RealityScan Mobile](https://play.google.com/store/apps/details?id=com.epicgames.realityscan)** (Epic) | Free | iOS / Android | Easiest path by a distance. Capture and process on the phone. This is where to start. |
| **[RealityScan 2](https://www.realityscan.com/)** (desktop, ex-RealityCapture) | Free under $1M annual revenue | Windows | The strongest free desktop reconstructor. Windows only — a real obstacle given both your machines run Arch. |
| **[Meshroom / AliceVision](https://github.com/alicevision/Meshroom)** | **MPL-2.0**, fully open source | Linux / Windows | The open-source answer, and it runs natively on Arch. **Caveat that matters here: the default dense-reconstruction pipeline wants an NVIDIA CUDA GPU.** The Yoga's Intel HD 620 and the omarchy box's AMD part both fall outside that, so expect to use the draft/CPU meshing path and expect it to be slow. Test on a small object before committing an afternoon of photographs to it. |
| **[COLMAP](https://colmap.github.io/)** | BSD | Linux | Excellent, scriptable, same GPU appetite for the dense stage. |
| **Polycam / Scaniverse** | Free tiers; Polycam has paid tiers (check current pricing) | iOS / Android | Cloud or on-device processing, which sidesteps the GPU problem entirely. Read the terms on what rights you grant by uploading. |

Given the GPU situation on both of your machines, **start with RealityScan Mobile
on the phone.** If you want the whole pipeline to be open source and local,
Meshroom is the answer, with the CUDA caveat above understood before you begin.

### The cleanup, in Blender (free, GPL)

1. Import the reconstruction. It will be a single enormous noisy mesh sitting in
   a bowl of reconstructed driveway.
2. Delete the ground, and everything that is not the car.
3. Patch the glass and lights — these will be holes. A separate simple glass
   surface with a transmissive material is both easier and better-looking than
   trying to reconstruct a window.
4. **Decimate to roughly 100k–150k triangles.** More than that buys nothing on an
   Intel HD 620 and costs frames.
5. **Resize textures to 2048×2048** (4096 at the absolute most). The baked colour
   from photogrammetry already carries the lighting it was shot under, which is
   part of why flat overcast light matters so much.
6. Apply all transforms; **+Y up**; the car facing however you like — the viewer
   centres and rescales whatever it is given.
7. Export **glTF 2.0 Binary (`.glb`)**. Do not enable Draco compression unless you
   are prepared to vendor a Draco decoder as well; an uncompressed GLB under about
   15 MB loads instantly from local disk and needs no extra files.

### A different technology worth knowing about

**Gaussian splatting** (3DGS) reconstructs a scene as millions of view-dependent
blobs rather than a mesh, and it handles glossy paint *dramatically* better than
photogrammetry does — because it stores how the surface changes with viewing
angle instead of trying to pretend it does not. Scaniverse and Polycam both
produce splats from a phone.

The honest catch: **a splat is not a GLB and this viewer cannot load one.** It
needs a different renderer entirely. If the photogrammetry route produces a
disappointing car because of the paint, this is the direction to look next, and
it is a separate piece of work.

---

## Route D — commission one

A modeller builds a 2015 CR-Z to your reference photographs, and — this is the
part that matters and the part a marketplace cannot sell you — **you negotiate
the redistribution rights in the contract**, which is the only way a car model
ever legitimately lands in a public repository.

I have no verified figures for what that costs and will not guess; get quotes. It
is materially more than a marketplace licence. It is worth knowing the option
exists, and it is almost certainly not worth it here when you own the car.

---

## A note on trademarks

Not legal advice, and I am not a lawyer. Stating what the sources say:

- The Honda wordmark and the H badge are registered trademarks. A CC or
  royalty-free licence on a mesh does not touch them; CC say so explicitly in the
  licence text quoted above.
- Trade dress can extend to a vehicle's distinctive appearance, which is why
  marketplaces attach the "Editorial Uses Only" label to branded vehicles at all.
- A **personal, non-commercial diagnostic tool for your own car**, showing your
  own car, is about as far from a trademark problem as you can stand. Publishing
  the *source* of that tool is fine. Publishing somebody else's licensed Honda
  mesh inside it is a different act with a different answer.
- The architecture here reflects that: the model lives in `share/models/`, which
  is a local directory, not a distributed one. **Whatever route you take, do not
  commit the `.glb`.** It keeps the repository clean of a licence question
  entirely, and as a bonus it keeps 15 MB of binary out of git history.

---

## What was actually built

`share/js/car3d.js` and `share/css/car3d.css`.

### The viewer

- **three.js r185, pinned and vendored.** Not a CDN. The app is served from the
  laptop's own disk and is expected to work in a car park with no signal; a CDN
  script tag is a viewer that works on the sofa and is a blank box at the
  roadside.
- **Lighting is a hand-built studio rig, not three's `RoomEnvironment`.** Clearcoat
  is a mirror with colour behind it, so what you see on a car's flank is the
  *shape of the light source* stretched along the body. Long horizontal softbox
  strips make a car read as a car; scattered blobs make it read as a plastic toy.
  The rig is one broad overhead softbox, two long side strips at deliberately
  unequal brightness (an evenly lit car has no bright side and therefore no
  shape), a low rear rim strip, a dark floor and a mid-grey shell, rendered once
  into a PMREM environment map and discarded. No HDRI to download, no addon to
  vendor, no licence to read.
- **ACES filmic tone mapping**, exposure 0.95. Untone-mapped, the specular streaks
  along a flank clip to flat white and the body loses its shape exactly where the
  shape is most legible.
- **A 30° lens.** Manufacturers photograph cars at 100mm and longer for a reason:
  a wide lens on a four-metre object makes the near wheel enormous and the far
  one tiny, and the car reads as a caricature of itself.
- **The camera orbits; the car stands still.** Rotating the model would be one
  line shorter and wrong — the reflections would sweep the wrong way and the
  painted contact shadow would swing round with the car and give it away.
- **A painted contact shadow, not a shadow map.** A shadow map is a second render
  pass every frame on the machine that must not have one. The car does not move
  relative to the ground, so the shadow does not change, so it is one texture.
- **The canvas is transparent** and the scene has no background, so the card
  behind it stays whatever the current theme says — which matters because
  `lib/theme.py` regenerates palettes and `main.js` swaps the sheet under a
  running page.
- **Materials are not guessed at.** The only thing applied unconditionally is
  `envMapIntensity`, which is exposure, not appearance. Everything else comes
  from an optional sidecar file keyed by material name (below). Walking the model
  looking for a mesh called "body" to paint gunmetal would be inventing the car's
  appearance, and would make a good model look worse.

### How it protects the laptop

Every one of these ends at the flat car rather than at a black rectangle:

| Condition | How it is detected |
|---|---|
| No model file | `HEAD /models/crz.glb` before anything is downloaded |
| three.js not vendored, or no import map | the dynamic `import()` throws and is caught |
| No WebGL | a throwaway context, immediately released |
| Software GL (llvmpipe, SwiftShader) | `WEBGL_debug_renderer_info`, where the browser exposes it |
| GPU context lost | `webglcontextlost` — a frozen last frame looks like a working picture and is not |
| Simply too slow | render time is averaged; pixel ratio steps 1.5 → 1.0 → 0.75, then it gives up |

Plus: capped at 30fps, stopped entirely when scrolled off screen
(`IntersectionObserver`) or when the tab is hidden, auto-rotation refused under
`prefers-reduced-motion`, and `forceContextLoss()` on unmount — browsers cap
live WebGL contexts at around sixteen and silently kill the oldest, so in an app
whose whole navigation model is mount/unmount/mount, leaking one per visit breaks
the car after a dozen trips through the view and takes an unrelated canvas with
it.

### The fallback

With no model, the viewer draws the **same silhouette `plugin/Car.qml` draws**,
from the same artwork and the same source, coloured from the theme tokens so it
follows every look. There is no apology banner, no "3D unavailable" caption and
no spinner that never resolves — the flat car is a legitimate picture of the car
in its own right and it is what the panel already shows. A `data-car3d` attribute
on the host records *why* (`no-model`, `no-webgl`, `software-gl`, `no-viewer`,
`context-lost`, `too-slow`) for whoever is debugging; a driver never sees it.

---

## Installing a model once you have one

### 1. Vendor three.js r185 — five files, ~915 KB

```
share/vendor/three/three.module.min.js                    (366 KB)
share/vendor/three/three.core.min.js                      (385 KB)  ← the module imports this
share/vendor/three/addons/loaders/GLTFLoader.js           (115 KB)
share/vendor/three/addons/utils/BufferGeometryUtils.js     (38 KB)  ← GLTFLoader imports this
share/vendor/three/addons/utils/SkeletonUtils.js           (12 KB)  ← and this
```

From the pinned tag, so this fetches r185 and nothing else:

```sh
cd share/vendor/three
B=https://raw.githubusercontent.com/mrdoob/three.js/r185
curl -O $B/build/three.module.min.js
curl -O $B/build/three.core.min.js
mkdir -p addons/loaders addons/utils
curl -o addons/loaders/GLTFLoader.js       $B/examples/jsm/loaders/GLTFLoader.js
curl -o addons/utils/BufferGeometryUtils.js $B/examples/jsm/utils/BufferGeometryUtils.js
curl -o addons/utils/SkeletonUtils.js       $B/examples/jsm/utils/SkeletonUtils.js
```

three.js is MIT licensed, so vendoring it is unambiguous — keep the licence
header that is already at the top of `three.module.min.js`.

### 2. Add the import map to `share/app.html`

**It must come before any `<script type="module">` on the page**, or the browser
will have already resolved modules without it. This file is the orchestrator's to
edit, not this change's.

```html
<script type="importmap">
{"imports":{"three":"/vendor/three/three.module.min.js","three/addons/":"/vendor/three/addons/"}}
</script>
<link rel="stylesheet" href="/css/car3d.css">
```

Bare specifiers are used deliberately: importing the core by URL here while
letting `GLTFLoader` import it by name would produce **two** copies of three.js,
and every `instanceof` between them would be false.

### 3. Drop the model in

```
share/models/crz.glb
```

Add `share/models/` to `.gitignore`. See [the trademark note](#a-note-on-trademarks)
for why that is the architecture and not an oversight.

Budget for this hardware: **≤150k triangles, textures ≤2048², GLB under ~15 MB,
no Draco.** The viewer measures whatever it is given and rescales it into its own
stage, so units (metres, centimetres, inches) and position do not matter.

### 4. Optionally tune the materials

`share/models/crz.materials.json`, keyed by material name exactly as it appears in
Blender's material list:

```json
{
  "CarPaint":  { "clearcoat": 1.0, "clearcoatRoughness": 0.06, "roughness": 0.32 },
  "Glass":     { "transmission": 0.95, "roughness": 0.05, "ior": 1.5 },
  "TyreRubber":{ "roughness": 0.92, "metalness": 0.0 }
}
```

Only a fixed allowlist of properties is applied (`clearcoat`,
`clearcoatRoughness`, `roughness`, `metalness`, `envMapIntensity`, `transmission`,
`ior`, `iridescence`, `reflectivity`, `sheen`, `sheenRoughness`, `opacity`,
`transparent`, `side`) — anything else is dropped, so a typo cannot quietly turn
the paint into rubber. Absent the file, nothing is overridden.

> The material names above are **placeholders showing the file's shape**. They are
> not the material names in any real CR-Z model, because there is no real CR-Z
> model here. Read the actual names out of whatever asset you end up with.

### 5. Use it

```js
import { mountCar } from "../car3d.js";

// returns an unmount function, the convention every view here follows
const off = mountCar(hostEl, { rotate: true, drag: true });
```

Nothing in the app calls it yet — wiring it into a view is a separate change and
touches files this one does not own.

### 6. Get the colour right

When you match the paint — whether you are tuning a bought model or checking a
scan — **read the paint code off the sticker in the driver's door jamb** rather
than trusting anyone's idea of "gunmetal grey", this document's included. It is
the only source that is actually about your car.

---

## Recommendation, in one paragraph

Do the photogrammetry. Overcast afternoon, phone, RealityScan Mobile, 200 photos
in three orbits at three heights, newspaper on the ground for the solver to grip,
then Blender to decimate and export a GLB into `share/models/`. It costs nothing,
it produces *your* car rather than a 2011 approximation of it, and it is the only
route with no licence chapter attached. If it comes out disappointing because of
the paint, try a Gaussian splat before you try buying anything — and if you do
buy, buy it for your own machine and keep it out of the repository.
