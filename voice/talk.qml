//@ pragma UseQApplication
// OmaTalk — one big button that types what you say.
//
// WHY A LAYER-SHELL SURFACE AND NOT A WINDOW.
//
// This is the whole design constraint, and getting it wrong makes the feature
// useless in a way that looks like it works. voxtype transcribes into whatever
// currently has KEYBOARD FOCUS, by synthesising key events with wtype. A normal
// window that you tap takes focus when you tap it — so the words would be typed
// into this button instead of into the terminal you were talking to.
//
// A Wayland layer-shell surface with keyboardFocus: None can never take focus.
// You tap it, the terminal behind it stays focused, and the text lands where
// you were already typing. That is the entire reason this is a Quickshell
// panel rather than the obvious little GTK app.
//
// WHY IT IS THIS BIG.
//
// Because the person using it is in a car. A 44px target is a desktop
// convention that assumes a mouse and a still hand; this is sized to be hit
// with a thumb, without aiming, while looking at the road. It is deliberately
// the largest thing on screen after the app itself.

import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
  PanelWindow {
    id: win

    // Bottom-right, floating clear of the edges. Not anchored to a full side:
    // it must not reserve space or push the app's layout around, which is what
    // exclusiveZone: 0 buys.
    anchors { bottom: true; right: true }
    margins { bottom: 28; right: 28 }
    implicitWidth: 220
    implicitHeight: 220
    color: "transparent"
    exclusiveZone: 0

    // THE LINE THAT MAKES THIS WORK AT ALL.
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    WlrLayershell.layer: WlrLayer.Overlay

    property string state: "idle"       // idle | recording | transcribing
    readonly property bool live: state === "recording"
    readonly property bool busy: state === "transcribing"

    // voxtype prints one word on stdout. Polled rather than subscribed because
    // there is no event to subscribe to, and twice a second is far below the
    // rate at which a person changes their mind about talking.
    Process {
      id: statusProc
      command: ["voxtype", "status"]
      stdout: StdioCollector {
        waitForEnd: true
        onStreamFinished: {
          var t = text.trim().toLowerCase()
          if (t.length > 0) win.state = t
        }
      }
    }
    Timer {
      interval: 500
      running: true
      repeat: true
      onTriggered: if (!statusProc.running) statusProc.running = true
    }

    Process {
      id: toggle
      command: ["voxtype", "record", "toggle"]
    }

    Rectangle {
      anchors.fill: parent
      radius: width / 2
      // Red while listening, amber while it thinks, and a calm dark when idle.
      // Colour carries the state because the word underneath is too small to
      // read at a glance from the driver's seat.
      color: win.live ? "#C0392B" : win.busy ? "#B9770E" : "#1B2A31"
      border.color: win.live ? "#F1948A" : win.busy ? "#F0C27B" : "#31454E"
      border.width: 3
      opacity: tap.pressed ? 0.82 : 1.0
      Behavior on color { ColorAnimation { duration: 140 } }

      Column {
        anchors.centerIn: parent
        spacing: 8
        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: win.live ? "⏺" : win.busy ? "⋯" : "🎤"
          color: "#FFFFFF"
          font.pixelSize: 64
        }
        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: win.live ? "LISTENING" : win.busy ? "TYPING" : "TALK"
          color: "#FFFFFF"
          font.pixelSize: 19
          font.letterSpacing: 2
          font.bold: true
        }
      }

      MouseArea {
        id: tap
        anchors.fill: parent
        onClicked: if (!toggle.running) toggle.running = true
      }
    }
  }
}
