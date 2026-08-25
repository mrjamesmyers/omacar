import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// OmaCar bar widget.
//
// The bar button owns its own state so the icon stays honest while the
// panel is closed — `omacar state` is polled once at startup and again
// whenever the panel opens. Keep that contract: a widget that only knows
// what it saw when it was last opened reads as broken.
Panel {
  id: root
  moduleName: "omacar"
  ipcTarget: "omacar"
  manageIpc: false

  readonly property string cmd: Quickshell.env("HOME") + "/.local/bin/omacar"

  property var info: ({})
  property bool active: false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function run(c) { proc.command = ["sh", "-c", c]; proc.running = true }
  function refresh() { stateProc.running = true }

  Process { id: proc }

  Process {
    id: stateProc
    command: [root.cmd, "state"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var out = {}
        text.split("\n").forEach(function (line) {
          var i = line.indexOf("=")
          if (i > 0) out[line.slice(0, i)] = line.slice(i + 1)
        })
        root.info = out
        root.active = out["active"] === "1"
      }
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰀻"
    active: root.active
    tooltipText: "OmaCar"
    onPressed: function (b) { root.toggle() }
  }

  onOpenedChanged: if (opened) refresh()
  Component.onCompleted: refresh()
}
