pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons
import "components"

Item {
    id: root
    property var service: null
    property bool opened: false
    property bool settingsOpen: false
    property string commandError: ""
    implicitHeight: settingsOpen ? settingsLoader.item?.implicitHeight ?? 0 : main.implicitHeight
    onOpenedChanged: if (!opened) { settingsOpen = false; commandError = "" }
    function run(name: string): void {
        const result = service.command(name)
        commandError = result.status === "rejected" ? result.reason : ""
    }
    Column {
        id: main
        width: parent.width
        spacing: Style.space(10)
        visible: !root.settingsOpen
        Ui.PanelHero {
            width: parent.width
            title: "Omadoro"
            meta: root.service?.view.status ?? "Initializing…"
            iconComponent: Label {
                text: "󱅻"
                font.pixelSize: Style.font.display * 1.25
            }
            trailingControl: Label {
                text: root.service?.view.phase === "Stopped" ? "" : root.service?.view.label ?? ""
                font.pixelSize: Style.font.title
            }
        }
        Ui.PanelSeparator { }
        Label {
            width: parent.width
            wrapMode: Text.Wrap
            visible: text !== ""
            text: root.commandError || root.service?.view.error || root.service?.settingsIssue || root.service?.desktopIssue || ""
        }
        Flow {
            width: parent.width
            spacing: Style.space(6)
            Repeater {
                model: !root.service ? [] : root.service.view.phase === "Stopped"
                    ? [{ text: "Start", action: "start" }, { text: "Break now", action: "break" }]
                    : root.service.view.phase === "Breaking" ? [] : [
                        { text: root.service.view.phase === "Paused" ? "Resume" : "Pause", action: root.service.view.phase === "Paused" ? "resume" : "pause" },
                        { text: "Break now", action: "break" }]
                Ui.Button {
                    required property var modelData
                    text: modelData.text
                    focusable: true
                    bordered: false
                    selected: modelData.action === "start" || modelData.action === "resume" || modelData.action === "pause"
                    horizontalPadding: Style.space(8)
                    verticalPadding: Style.space(4)
                    onClicked: root.run(modelData.action)
                }
            }
        }
        Ui.PanelSeparator { }
        RowLayout {
            width: parent.width
            spacing: Style.space(6)
            Ui.Button {
                text: "+5 min"; focusable: true
                bordered: false
                visible: root.service?.view.phase === "Working" || root.service?.view.phase === "Paused"
                fontSize: Style.font.bodySmall
                horizontalPadding: Style.space(6); verticalPadding: Style.space(3)
                onClicked: root.run("add")
            }
            Ui.Button {
                text: "Reset timer"; focusable: true
                bordered: false
                visible: root.service?.view.phase === "Working" || root.service?.view.phase === "Paused"
                fontSize: Style.font.bodySmall
                horizontalPadding: Style.space(6); verticalPadding: Style.space(3)
                onClicked: root.run("reset")
            }
            Item { Layout.fillWidth: true }
            Ui.Button {
                text: "Settings"; focusable: true; enabled: root.service !== null
                fontSize: Style.font.bodySmall
                horizontalPadding: Style.space(6); verticalPadding: Style.space(3)
                onClicked: root.settingsOpen = true
            }
        }
    }
    Loader {
        id: settingsLoader
        anchors.fill: parent
        active: root.settingsOpen
        sourceComponent: Settings {
            service: root.service
            onBack: root.settingsOpen = false
        }
    }
}
