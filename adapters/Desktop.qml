import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

Item {
    id: root
    property bool observing: false
    property int idleThreshold: 60
    property bool healthy: false
    property var sample: null
    property string error: ""
    property real receivedAt: 0
    property real clockAnchor: 0
    property real bootOffset: 0
    property bool rawIdle: false
    property real idleSince: 0
    property real observationBaseline: 0
    property real lastActivity: 0
    readonly property var outputs: Quickshell.screens.map(s => s.name)
    signal changed()
    signal lost(string reason)
    function now(): var {
        // Keep a fixed monotonic origin. Re-anchoring to every asynchronous
        // sample could move model time backward by its delivery latency.
        const running = sample ? clockAnchor + elapsed.elapsedMs() / 1000 : 0
        return { mono: running, boot: sample ? running + bootOffset : 0 }
    }
    function inputs(): var {
        return { outputs: outputs, available: healthy && sample?.locked !== null && sample?.logindHealthy === true,
            locked: sample?.locked === true, sleeping: sample?.sleeping === true,
            idle: rawIdle, idleSince: idleSince }
    }
    function resetIdle(): void {
        rawIdle = false
        observationBaseline = now().boot
        lastActivity = observationBaseline
        idleMonitor.enabled = false
        Qt.callLater(function() { idleMonitor.enabled = root.observing })
    }
    onIdleThresholdChanged: resetIdle()
    onOutputsChanged: changed()
    onObservingChanged: {
        if (observing) {
            elapsed.restartMs()
            error = ""
            resetIdle()
        } else healthy = false
    }
    ElapsedTimer { id: elapsed }
    IdleMonitor {
        id: idleMonitor
        enabled: root.observing
        timeout: root.idleThreshold
        respectInhibitors: false
        onIsIdleChanged: {
            if (!root.observing || !root.sample) return
            root.rawIdle = isIdle
            if (isIdle) root.idleSince = Math.max(root.observationBaseline, root.lastActivity, root.now().boot - root.idleThreshold)
            else root.lastActivity = root.now().boot
            root.changed()
        }
    }
    Process {
        id: helper
        command: ["python", decodeURIComponent(Qt.resolvedUrl("desktop.py").toString().replace(/^file:\/\//, ""))]
        running: root.observing
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                try {
                    const value = JSON.parse(data)
                    if (!Number.isFinite(value.monoMs) || !Number.isFinite(value.bootMs)) throw new Error("Invalid desktop clock sample")
                    const first = root.sample === null
                    if (first) root.clockAnchor = value.monoMs / 1000 - elapsed.elapsedMs() / 1000
                    // Linux's boottime-minus-monotonic difference increases on
                    // resume. Ignore sub-millisecond backwards sampling noise.
                    root.bootOffset = first ? (value.bootMs - value.monoMs) / 1000
                        : Math.max(root.bootOffset, (value.bootMs - value.monoMs) / 1000)
                    root.sample = value
                    root.receivedAt = elapsed.elapsedMs()
                    root.healthy = true
                    if (first) root.resetIdle()
                    root.error = value.error || ""
                    root.changed()
                } catch (exception) {
                    root.healthy = false
                    root.error = String(exception)
                    root.lost(root.error)
                }
            }
        }
        stderr: SplitParser { onRead: data => { root.error = data } }
        onRunningChanged: {
            if (!running && root.observing) {
                root.healthy = false
                root.lost("Desktop adapter stopped. Reload Omadoro to reconnect.")
            }
        }
    }
    // Health watchdog only; elapsed clocks, not callback counts, drive phases.
    Timer {
        interval: 2000
        repeat: true
        running: root.observing
        onTriggered: {
            if (!root.sample || elapsed.elapsedMs() - root.receivedAt > 4000) {
                root.healthy = false
                root.lost("Desktop timing unavailable. Reload Omadoro to reconnect.")
            }
        }
    }
}
