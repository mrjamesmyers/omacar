// Twelve months of driving: distance as bars, economy as a line over them.
//
// Two measures on one chart because the question is always both at once —
// "did I drive more, and did it cost me more per mile" — and two charts
// stacked would put the answer in two places. The bars are the volume you
// covered and the line is how well; they share only the x axis, and the line
// carries its own scale, printed at the ends so nobody has to guess it.
//
// Months with no driving are drawn as a gap in the line rather than a dive to
// zero: a car that sat still has no economy figure at all, and plotting one
// invents a month of imaginary perfect driving.
import QtQuick
import qs.Commons

Canvas {
  id: root

  // [{ label, dist, econ }] oldest first. Already in display units.
  property var series: []
  property color foreground: Color.foreground
  property color accent: "#0A84FF"
  property color line: "#FF9F0A"
  property real labelSize: Style.font.caption

  onSeriesChanged: requestPaint()
  onForegroundChanged: requestPaint()
  onWidthChanged: requestPaint()
  onHeightChanged: requestPaint()

  onPaint: {
    var ctx = getContext("2d")
    ctx.reset()
    var n = series.length
    if (n < 1 || width < 20 || height < 20) return

    var labelH = Math.round(labelSize * 1.7)
    var plotH = height - labelH
    var gap = Math.max(2, width / n * 0.22)
    var bw = (width - gap * (n - 1)) / n

    var peak = 1
    for (var i = 0; i < n; i++) peak = Math.max(peak, series[i].dist || 0)

    // Economy is scaled to its own range rather than to zero: the interesting
    // part of a year of mpg is a spread of five, and anchoring the axis at the
    // origin flattens it into a straight line.
    var lo = Infinity, hi = -Infinity
    for (var j = 0; j < n; j++) {
      var e = series[j].econ
      if (e === null || e === undefined || isNaN(e)) continue
      lo = Math.min(lo, e); hi = Math.max(hi, e)
    }
    var haveLine = isFinite(lo) && hi > lo
    var pad = haveLine ? (hi - lo) * 0.25 : 1
    lo -= pad; hi += pad

    function bx(i) { return i * (bw + gap) }
    function by(v) { return plotH - plotH * 0.92 * (v / peak) }
    function ly(v) { return plotH * 0.10 + (plotH * 0.72) * (1 - (v - lo) / (hi - lo)) }

    // Bars.
    for (var k = 0; k < n; k++) {
      var h = plotH - by(series[k].dist || 0)
      var grad = ctx.createLinearGradient(0, by(series[k].dist || 0), 0, plotH)
      grad.addColorStop(0, Qt.rgba(accent.r, accent.g, accent.b, 0.85))
      grad.addColorStop(1, Qt.rgba(accent.r, accent.g, accent.b, 0.28))
      ctx.fillStyle = grad
      var r = Math.min(bw / 2, Style.space(3))
      var x = bx(k), y = by(series[k].dist || 0)
      ctx.beginPath()
      ctx.moveTo(x, plotH)
      ctx.lineTo(x, y + r)
      ctx.quadraticCurveTo(x, y, x + r, y)
      ctx.lineTo(x + bw - r, y)
      ctx.quadraticCurveTo(x + bw, y, x + bw, y + r)
      ctx.lineTo(x + bw, plotH)
      ctx.closePath()
      ctx.fill()
    }

    // The economy line, broken across months the car did not move.
    if (haveLine) {
      ctx.strokeStyle = line
      ctx.lineWidth = Math.max(1.4, Style.space(2))
      ctx.lineJoin = "round"
      ctx.lineCap = "round"
      var drawing = false
      ctx.beginPath()
      for (var m = 0; m < n; m++) {
        var v = series[m].econ
        if (v === null || v === undefined || isNaN(v)) { drawing = false; continue }
        var px = bx(m) + bw / 2, py = ly(v)
        if (!drawing) { ctx.moveTo(px, py); drawing = true }
        else ctx.lineTo(px, py)
      }
      ctx.stroke()

      for (var p = 0; p < n; p++) {
        var vv = series[p].econ
        if (vv === null || vv === undefined || isNaN(vv)) continue
        ctx.beginPath()
        ctx.arc(bx(p) + bw / 2, ly(vv), Math.max(1.6, Style.space(2)), 0, Math.PI * 2)
        ctx.fillStyle = line
        ctx.fill()
      }
    }

    // Month initials under the bars, and the current month called out.
    ctx.font = Math.round(labelSize) + "px sans-serif"
    ctx.textAlign = "center"
    ctx.textBaseline = "top"
    for (var q = 0; q < n; q++) {
      var last = q === n - 1
      ctx.fillStyle = last ? foreground
        : Qt.rgba(foreground.r, foreground.g, foreground.b, 0.42)
      ctx.fillText(series[q].label, bx(q) + bw / 2, plotH + Style.space(4))
    }
  }
}
