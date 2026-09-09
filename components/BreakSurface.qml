import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Ui as Ui
import qs.Commons

PanelWindow {
    id: surface
    property var service: null
    readonly property int token: service?.view.attempt ?? -1
    property bool tearingDown: false
    visible: service?.view.breakVisible ?? false
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    color: Qt.rgba(Color.background.r, Color.background.g, Color.background.b, 1)
    WlrLayershell.namespace: "omadoro-break"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    function reportReady(): void {
        if (!visible || !backingWindowVisible || width <= 0 || height <= 0 || !service) return
        const current = token
        Qt.callLater(function() {
            if (!surface.tearingDown && surface.visible && surface.backingWindowVisible && surface.token === current)
                surface.service?.ready(current, surface.screen.name)
        })
    }
    function lost(): void { if (!tearingDown && visible) service?.coverageLost(token, screen.name) }
    onVisibleChanged: if (visible) { input.forceActiveFocus(); reportReady() }
    onTokenChanged: reportReady()
    onBackingWindowVisibleChanged: { if (backingWindowVisible) reportReady(); else lost() }
    onWidthChanged: reportReady()
    onHeightChanged: reportReady()
    onClosed: lost()
    onResourcesLost: lost()
    Component.onCompleted: { if (visible) input.forceActiveFocus(); reportReady() }
    Component.onDestruction: { lost(); tearingDown = true }
    FocusScope {
        id: input
        anchors.fill: parent
        focus: true
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Escape) {
                surface.service?.command("skip")
                event.accepted = true
            } else if (!surface.service?.view.canSkip || [Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space].indexOf(event.key) < 0)
                event.accepted = true
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            onPressed: mouse => { input.forceActiveFocus(); mouse.accepted = true }
            onWheel: wheel => { wheel.accepted = true }
        }
        Column {
            anchors.centerIn: parent
            spacing: Style.space(22)
            Label { anchors.horizontalCenter: parent.horizontalCenter; text: "󱅻"; font.pixelSize: Style.font.displayLarge * 2 }
            Label { anchors.horizontalCenter: parent.horizontalCenter; text: surface.service?.locking ? "Locking desktop…" : "Take a moment. Let your eyes rest."; font.pixelSize: Style.font.subtitle }
            Label { anchors.horizontalCenter: parent.horizontalCenter; text: surface.service?.view.preparing ? "Preparing…" : surface.service?.view.label ?? ""; font.pixelSize: Style.font.displayLarge * 2 }
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: surface.service?.locking ? "Wait for Omarchy’s lock screen before leaving."
                    : surface.service?.view.skipPolicy === "never" ? "Your desktop returns when the break ends."
                    : surface.service?.view.canSkip ? "Escape or Skip to return"
                    : "Skipping available in " + (surface.service?.view.skipLabel ?? "")
            }
            Ui.Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Skip"; focusable: true; bordered: true
                visible: (surface.service?.view.canSkip ?? false) && !surface.service?.locking
                onClicked: surface.service?.command("skip")
            }
        }
    }
}
