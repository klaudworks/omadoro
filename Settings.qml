pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as QQC
import qs.Ui as Ui
import qs.Commons
import "components"
import "model/SettingsModel.js" as SettingsModel

Item {
    id: root
    property var service: null
    property var draft: Object.assign({}, service?.saved || {})
    property string error: ""
    implicitHeight: form.implicitHeight
    signal back()
    function setValue(key: string, value): void {
        const next = Object.assign({}, draft)
        next[key] = value
        const result = service.saveSettings(next)
        error = result.ok ? "" : result.error.replace("breakSeconds", "break duration (up to 60 minutes, in whole-second increments)")
        if (result.ok) draft = Object.assign({}, result.value)
    }
    Flickable {
        anchors.fill: parent
        contentHeight: form.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        QQC.ScrollBar.vertical: QQC.ScrollBar {}
        Column {
            id: form
            width: parent.width - Style.space(12)
            spacing: Style.space(10)
            Item {
                width: form.width
                implicitHeight: Math.max(backButton.implicitHeight, heading.implicitHeight)
                Ui.Button {
                    id: backButton
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    iconText: ""
                    iconSize: Style.font.body
                    tooltipText: "Back"
                    focusable: true
                    horizontalPadding: Style.space(6)
                    onClicked: root.back()
                }
                Label {
                    id: heading
                    anchors.centerIn: parent
                    text: "Settings"
                    font.bold: true
                    font.pixelSize: Style.font.title
                }
            }
            Ui.PanelSeparator { }
            Repeater {
                model: [ { key: "workMinutes", label: "Work interval (minutes)" },
                    { key: "breakSeconds", label: "Break duration (minutes)" },
                    { key: "idleThresholdSeconds", label: "Idle after (seconds)" } ]
                Row {
                    required property var modelData
                    width: form.width
                    spacing: Style.space(8)
                    Label { width: parent.width - field.width - parent.spacing; wrapMode: Text.Wrap; text: parent.modelData.label; anchors.verticalCenter: parent.verticalCenter }
                    Ui.TextField {
                        id: field
                        width: Style.space(80)
                        Component.onCompleted: text = String(parent.modelData.key === "breakSeconds"
                            ? root.draft.breakSeconds / 60 : root.draft[parent.modelData.key])
                        inputMethodHints: Qt.ImhFormattedNumbersOnly
                        onEditingFinished: {
                            if (parent.modelData.key === "breakSeconds") {
                                root.setValue("breakSeconds", SettingsModel.minutesToSeconds(text))
                            } else root.setValue(parent.modelData.key, text)
                        }
                    }
                }
            }
            Ui.Dropdown {
                width: form.width
                label: "Skipping"
                value: root.draft.skipPolicy
                options: [{ value: "allow", label: "Allow skipping" }, { value: "wait", label: "Allow after waiting" }, { value: "never", label: "No skip" }]
                onChanged: value => root.setValue("skipPolicy", value)
            }
            Row {
                visible: root.draft.skipPolicy === "wait"
                width: form.width
                spacing: Style.space(8)
                Label { text: "Wait before skipping (seconds)"; width: parent.width - waitField.width - parent.spacing; wrapMode: Text.Wrap }
                Ui.TextField {
                    id: waitField
                    width: Style.space(80)
                    text: String(root.draft.skipWaitSeconds)
                    inputMethodHints: Qt.ImhDigitsOnly
                    onEditingFinished: root.setValue("skipWaitSeconds", text)
                }
            }
            Ui.PanelSeparator { }
            Repeater {
                model: [{ key: "autoStart", label: "Start timer on startup" },
                    { key: "warningEnabled", label: "Warn 15 seconds before a break" },
                    { key: "warningPostponeEnabled", label: "Offer +5 min in the warning" }]
                Ui.Button {
                    id: toggleRow
                    required property var modelData
                    readonly property bool checked: root.draft[modelData.key] === true
                    width: form.width
                    focusable: true
                    bordered: false
                    implicitHeight: Style.space(44)
                    onClicked: root.setValue(modelData.key, !checked)
                    Label {
                        anchors.left: parent.left
                        anchors.right: toggleSwitch.left
                        anchors.leftMargin: Style.spacing.rowPaddingX
                        anchors.rightMargin: Style.spacing.rowPaddingX
                        anchors.verticalCenter: parent.verticalCenter
                        text: toggleRow.modelData.label
                        font.pixelSize: Style.font.body
                        font.bold: false
                        elide: Text.ElideRight
                    }
                    Ui.ToggleSwitch {
                        id: toggleSwitch
                        anchors.right: parent.right
                        anchors.rightMargin: Style.spacing.rowPaddingX
                        anchors.verticalCenter: parent.verticalCenter
                        checked: toggleRow.checked
                        interactive: false
                    }
                }
            }
            Label { width: form.width; wrapMode: Text.Wrap; text: root.error || root.service?.saveStatus || ""; visible: text !== "" }
        }
    }
}
