// A proportion as a bar, with the unfilled part left visible as a track.
//
// The same reasoning as every other meter in this desktop: a bar with nothing
// behind it reads as a short bar rather than as an empty one, and half the
// point of a meter is knowing how much of it is left.
import QtQuick
import qs.Commons

Rectangle {
  id: root

  property real value: 0          // 0..1
  property color tint: "#30D158"
  property color foreground: Color.foreground

  implicitHeight: Style.space(5)
  radius: height / 2
  color: Qt.rgba(foreground.r, foreground.g, foreground.b, 0.13)

  Rectangle {
    height: parent.height
    radius: parent.radius
    width: Math.max(root.value > 0 ? parent.height : 0,
                    parent.width * Math.min(1, Math.max(0, root.value)))
    color: root.tint
    Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
    Behavior on color { ColorAnimation { duration: 320 } }
  }
}
