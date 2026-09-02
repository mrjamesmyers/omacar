// The car, drawn rather than set in a font.
//
// Same reasoning SteeringWheel.qml gives and it has not stopped being true:
// the nerd font's car glyphs differ between patched families, so the one that
// looks right today is a picture of somebody else's car after the next theme
// change. A canvas draws the same silhouette at whatever size the bar gives
// it, in whatever colour the theme is currently using.
//
// A side profile rather than a front three-quarter: at bar size -- ten or
// twelve pixels tall -- a three-quarter view is a smudge, while a profile
// stays readable because its outline is mostly horizontal.
//
// Drop-in for SteeringWheel: same `tint`, `running` and `spin` properties, so
// both call sites swap without touching anything around them. `running` fills
// the cabin the way the wheel filled its hub -- the same "lit" convention the
// rest of the bar uses -- and `spin` turns the wheels, which is the one place
// a car can honestly show motion.
import QtQuick

Canvas {
  id: root

  property color tint: "#ffffff"
  // Filled while the engine is turning.
  property bool running: false
  // Wheel rotation, in turns per second. 0 is stopped.
  property real spin: 0

  // Redrawn whenever anything it draws with changes. Without this the canvas
  // keeps the first frame it ever painted.
  onTintChanged: requestPaint()
  onRunningChanged: requestPaint()
  onWidthChanged: requestPaint()
  onHeightChanged: requestPaint()

  property real phase: 0
  onPhaseChanged: requestPaint()

  NumberAnimation on phase {
    running: root.spin > 0
    loops: Animation.Infinite
    from: 0
    to: Math.PI * 2
    // Faster spin = shorter loop. Clamped so a motorway speed does not become
    // a strobe at twelve pixels across.
    duration: Math.max(220, Math.round(1000 / Math.max(0.15, root.spin)))
  }

  onPaint: {
    const ctx = getContext("2d")
    const w = width, h = height
    ctx.reset()
    ctx.clearRect(0, 0, w, h)

    // Everything below is in units of the smaller dimension, so the drawing
    // scales with whatever box it is given.
    const s = Math.min(w, h)
    const lw = Math.max(1, s * 0.075)
    ctx.lineWidth = lw
    ctx.strokeStyle = root.tint
    ctx.fillStyle = root.tint
    ctx.lineJoin = "round"
    ctx.lineCap = "round"

    const cx = w / 2, cy = h / 2
    const bodyW = s * 0.86, bodyH = s * 0.30
    const left = cx - bodyW / 2, right = cx + bodyW / 2
    const beltline = cy + bodyH * 0.10          // where the cabin meets the body
    const sill = beltline + bodyH * 0.62
    const wheelR = s * 0.125
    const wheelY = sill
    const frontWheelX = right - bodyW * 0.24
    const rearWheelX = left + bodyW * 0.24

    // ---- cabin + body, one outline ----
    // A single path so the silhouette reads as one object at small sizes; two
    // strokes meeting at the beltline look like a crack.
    ctx.beginPath()
    ctx.moveTo(left, sill)
    ctx.lineTo(left, beltline)                                  // rear
    ctx.quadraticCurveTo(left + bodyW * 0.06, beltline,
                         left + bodyW * 0.18, beltline - bodyH * 0.62)  // rear screen
    ctx.lineTo(right - bodyW * 0.34, beltline - bodyH * 0.62)   // roof
    ctx.quadraticCurveTo(right - bodyW * 0.14, beltline - bodyH * 0.55,
                         right - bodyW * 0.04, beltline)        // windscreen + bonnet
    ctx.lineTo(right, beltline)
    ctx.lineTo(right, sill)
    ctx.closePath()

    if (root.running) {
      ctx.globalAlpha = 0.30
      ctx.fill()
      ctx.globalAlpha = 1
    }
    ctx.stroke()

    // ---- wheels ----
    // Drawn over the sill so the body appears to sit on them.
    for (const wx of [rearWheelX, frontWheelX]) {
      ctx.beginPath()
      ctx.arc(wx, wheelY, wheelR, 0, Math.PI * 2)
      ctx.stroke()

      // A single spoke is all that survives at bar size, and it is enough to
      // read as rotation. Anything more becomes a grey disc.
      if (root.spin > 0) {
        ctx.beginPath()
        ctx.moveTo(wx, wheelY)
        ctx.lineTo(wx + Math.cos(root.phase) * wheelR * 0.78,
                   wheelY + Math.sin(root.phase) * wheelR * 0.78)
        ctx.stroke()
      } else {
        // Parked: a hub dot, matching the wheel's own "stopped" look.
        ctx.beginPath()
        ctx.arc(wx, wheelY, Math.max(0.6, lw * 0.42), 0, Math.PI * 2)
        ctx.fill()
      }
    }
  }
}
