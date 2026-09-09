import QtQuick
import qs.Ui as Ui
import qs.Commons
import "components"

Ui.BarWidget {
    id: root
    moduleName: "klaudworks.omadoro"
    readonly property var service: bar?.shell?.serviceFor(moduleName) ?? null
    readonly property bool paused: service?.view.phase === "Paused"
    property bool popupOpen: false
    function close(): void { popupOpen = false }
    function open(): void { if (!service?.view.breakVisible) popupOpen = true }
    implicitWidth: vertical ? barSize : content.implicitWidth
    implicitHeight: barSize
    Connections {
        target: root.service
        function onViewChanged() {
            if (root.service.view.phase === "Breaking") root.close()
            else if (root.service.view.error) root.popupOpen = true
        }
    }
    FontMetrics {
        id: labelMetrics
        font: statusLabel.font
    }
    Row {
        id: content
        anchors.centerIn: parent
        Ui.BarIconButton {
            bar: root.bar
            text: "󱅻"
            fontSize: Style.bar.iconFont * 1.25
            onPressed: button => { if (button === Qt.LeftButton) root.popupOpen = !root.popupOpen }
        }
        Label {
            id: statusLabel
            visible: !root.vertical
            anchors.verticalCenter: parent.verticalCenter
            width: root.paused ? Style.space(18)
                : Math.ceil(Math.max(implicitWidth, labelMetrics.advanceWidth("00m"))) + Style.space(4)
            elide: Text.ElideRight
            text: !root.service ? "…" : root.service.view.phase === "Stopped" ? "Off"
                : root.paused ? "Ⅱ" : root.service.view.label
            font.pixelSize: Style.font.bodySmall
            MouseArea { anchors.fill: parent; onClicked: root.popupOpen = !root.popupOpen }
        }
    }
    Ui.KeyboardPanel {
        id: popup
        anchorItem: root
        bar: root.bar
        owner: root
        focusTarget: dashboard
        open: root.popupOpen
        contentWidth: fittedContentWidth(Style.space(dashboard.settingsOpen ? 370 : 280))
        contentHeight: fittedContentHeight(dashboard.implicitHeight)
        Dashboard {
            id: dashboard
            anchors.fill: parent
            service: root.service
            opened: root.popupOpen
            Keys.onEscapePressed: root.close()
        }
    }
}
