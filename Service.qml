import QtQuick
import Quickshell
import Quickshell.Io
import "model/TimerModel.js" as TimerModel
import "model/SettingsModel.js" as SettingsModel
import "adapters"

Item {
    id: root
    readonly property string pluginId: "klaudworks.omadoro"
    property var shell: null
    property var manifest: null
    property var model: null
    property var view: ({ phase: "Stopped", status: "Initializing", label: "…", breakVisible: false, warning: false })
    property var saved: SettingsModel.normalize({}).value
    property string settingsIssue: ""
    property string saveStatus: ""
    readonly property string desktopIssue: desktop.error || (!desktop.healthy ? "Desktop timing unavailable" : desktop.sample?.locked === null ? "Lock state unavailable" : "")
    property bool reconciling: false
    property bool destroying: false
    property var pendingSave: null
    readonly property var entry: {
        const layout = shell?.barConfig?.layout
        if (layout) for (const section of ["left", "center", "right"])
            for (const item of (layout[section] || [])) if (item.id === pluginId) return item
        return null
    }
    function configure(): void {
        if (!entry) return
        const normalized = SettingsModel.normalize(entry)
        saved = normalized.value
        settingsIssue = normalized.issue
        if (model) model.configure(saved)
        initialize()
        reconcile()
    }
    onEntryChanged: configure()
    onShellChanged: initialize()
    onManifestChanged: initialize()
    function initialize(): void {
        if (model || !shell || !manifest || !entry || !desktop.sample) return
        model = TimerModel.create(saved, desktop.now(), desktop.inputs())
        publish()
    }
    function publish(): void { if (model) view = model.snapshot() }
    function reconcile(deferEligibility): void {
        if (destroying || reconciling) return
        initialize()
        if (!model) return
        reconciling = true
        model.reconcile(desktop.now(), desktop.inputs(), deferEligibility === true)
        publish()
        reconciling = false
    }
    function command(name: string): var {
        reconcile(true)
        if (!model) return { status: "rejected", reason: "Desktop service initializing" }
        const result = model.command(name)
        reconcile()
        return result
    }
    function ready(token: int, output: string): void {
        reconcile()
        if (model) model.ready(token, output)
        publish()
    }
    function coverageLost(token: int, output: string): void {
        if (destroying) return
        reconcile()
        if (model) model.coverageLost(token, output)
        publish()
    }
    function saveSettings(draft): var {
        const checked = SettingsModel.validate(draft, saved)
        if (!checked.ok) return checked
        if (!entry || !shell) return { ok: false, error: "Settings service unavailable" }
        const merged = SettingsModel.merge(entry, checked.value)
        if (JSON.stringify(checked.value) === JSON.stringify(saved) && !settingsIssue
            && entry.meetingDetectionEnabled === undefined && entry.meetingGraceSeconds === undefined) {
            saveStatus = "No changes"
            return { ok: true, value: saved }
        }
        // The host returns false for an unchanged entry too. Its scoped config
        // snapshot can lag the write, so verify the file for either result.
        shell.updateEntryInline(pluginId, merged)
        pendingSave = checked.value
        saveStatus = "Checking saved settings…"
        verifySave.restart()
        return { ok: true, value: checked.value }
    }
    Desktop {
        id: desktop
        observing: root.shell !== null && root.manifest !== null
        idleThreshold: root.saved.idleThresholdSeconds
        onChanged: root.reconcile()
        onLost: reason => {
            if (root.model) root.model.fail(reason)
            root.publish()
        }
    }
    FileView {
        id: diskConfig
        path: Quickshell.env("HOME") + "/.config/omarchy/shell.json"
        printErrors: false
        onLoaded: {
            if (!root.pendingSave) return
            try {
                const config = JSON.parse(text())
                let owned = null
                for (const section of ["left", "center", "right"])
                    for (const item of (config.bar?.layout?.[section] || []))
                        if (item.id === root.pluginId) owned = item
                const matches = owned && Object.keys(root.pendingSave).every(key => owned[key] === root.pendingSave[key])
                if (matches) {
                    root.saved = Object.assign({}, root.pendingSave)
                    root.settingsIssue = ""
                    if (root.model) root.model.configure(root.saved)
                    root.reconcile()
                }
                root.saveStatus = matches ? "Saved" : "Could not confirm settings on disk"
            } catch (error) { root.saveStatus = "Could not read saved settings" }
            root.pendingSave = null
        }
        onLoadFailed: error => { if (root.pendingSave) root.saveStatus = "Could not read saved settings" }
    }
    Timer { id: verifySave; interval: 500; onTriggered: diskConfig.reload() }
    IpcHandler {
        target: "omadoro"
        function status(): string { root.reconcile(); return JSON.stringify(root.view) }
        function action(name: string): string { return JSON.stringify(root.command(name)) }
        function settings(): string { return JSON.stringify(root.saved) }
        function configure(json: string): string {
            try { return JSON.stringify(root.saveSettings(JSON.parse(json))) }
            catch (error) { return JSON.stringify({ ok: false, error: "Invalid settings JSON" }) }
        }
    }
    Component.onDestruction: {
        destroying = true
        if (model) model.command("disable")
        publish()
    }
}
