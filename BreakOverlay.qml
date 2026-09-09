pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Ui as Ui
import qs.Commons
import "components"

Item {
    id: root
    property var shell: null
    property var service: null
    readonly property bool opened: (service?.view.breakVisible || service?.view.warning) ?? false
    function open(payload): void { }
    // The retained service owns presentation. Generic UI dismissal never
    // cancels a warning or bypasses an active skip policy.
    function close(): void { }
    Variants {
        model: Quickshell.screens
        BreakSurface {
            required property var modelData
            screen: modelData
            service: root.service
        }
    }
    Variants {
        model: Quickshell.screens
        PanelWindow {
            required property var modelData
            screen: modelData
            visible: root.service?.view.warning ?? false
            anchors { top: true; bottom: true; left: true; right: true }
            exclusionMode: ExclusionMode.Ignore
            color: "transparent"
            // Only the optional button accepts clicks; the rest of the
            // warning remains click-through and never takes keyboard focus.
            mask: Region {
                item: postponeButton.visible ? postponeButton : null
            }
            WlrLayershell.namespace: "omadoro-warning"
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            Rectangle {
                anchors.centerIn: parent
                width: content.implicitWidth + Style.space(64)
                height: content.implicitHeight + Style.space(40)
                color: Color.background
                border.color: Color.accent
                border.width: Style.space(2)
                radius: Style.space(10)
                Column {
                    id: content
                    anchors.centerIn: parent
                    spacing: Style.space(10)
                    Label { anchors.horizontalCenter: parent.horizontalCenter; text: "A moment to rest in"; font.pixelSize: Style.font.subtitle }
                    Label { anchors.horizontalCenter: parent.horizontalCenter; text: root.service?.view.warningLabel ?? ""; font.pixelSize: Style.font.displayLarge * 2 }
                    Label {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: !postponeButton.visible
                        text: "More time? Open Omadoro in the bar."
                    }
                    Ui.Button {
                        id: postponeButton
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: root.service?.saved.warningPostponeEnabled ?? false
                        text: "+5 min"
                        bordered: true
                        onClicked: {
                            if (root.service?.view.warning && root.service?.saved.warningPostponeEnabled)
                                root.service.command("add")
                        }
                    }
                }
            }
        }
    }
}
